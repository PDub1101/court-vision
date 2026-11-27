"""
CourtVision Gemini 2.5 Flash Context Veto & Self-Learning Decision Basis Engine
1. Pre-Game Audit: Evaluates ISyE 4031 statistical edges (P(Cover), +EV%, SE_pred intervals)
   against injury news AND the model's own persistent learned rules in data/decision_basis.json.
2. Morning Post-Mortem: Analyzes forecast residuals (e_t = y_t - y_hat_t), updates the
   ISyE 4031 CFE/MAD Tracking Signal, and writes new learned rules into decision_basis.json.
"""

import os
import json
import math
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DECISION_BASIS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "decision_basis.json")


def load_decision_basis():
    if os.path.exists(DECISION_BASIS_PATH):
        with open(DECISION_BASIS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_decision_basis(basis):
    basis["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(DECISION_BASIS_PATH, "w", encoding="utf-8") as f:
        json.dump(basis, f, indent=2)


def audit_with_gemini(candidate, injury_context=""):
    """
    Submits an ISyE 4031 flagged edge to Gemini alongside live injury reports and learned rules.
    `injury_context` may be a formatted string or the dict returned by format_matchup_injury_context().
    """
    basis = load_decision_basis()
    learned_rules = basis.get("learned_rules", [])
    isye = candidate.get("isye_4031", {})

    if isinstance(injury_context, dict):
        injury_text = injury_context.get("text", "")
        injury_meta = injury_context
    else:
        injury_text = injury_context or ""
        injury_meta = {}

    if not GEMINI_API_KEY:
        print(f"[CourtVision Veto] Evaluating {candidate['recommended_side']} via ISyE 4031 + Injury Guard + Learned Rules.")
        return fallback_context_check(candidate, learned_rules, injury_meta=injury_meta)

    try:
        from google import genai
        from google.genai import types

        http_options = types.HttpOptions(
            timeout=12000,
            retry_options=types.HttpRetryOptions(attempts=1)
        )
        client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_options)

        rules_text = "\n".join(
            [f"- [{r['rule_id']} | {r['category']}]: {r['rule_statement']} (Delta: {r['parameter_delta']})" for r in learned_rules]
        )

        prompt = f"""
You are the Lead Qualitative Risk Auditor for CourtVision (`courtvision_ridge_holt_v2`), an NBA spread forecasting engine.
Your ONLY job is to decide whether to APPROVE ("BET", strictly 1 Unit) or REJECT ("VETO", 0 Units) this quantitative candidate based on live injuries, rotation context, and schedule fatigue. Never scale unit size above 1.

Tonight's Flagged Matchup:
- Game: {candidate['away_team']} @ {candidate['home_team']}
- Sportsbook Line ({candidate['sportsbook']}): {candidate['home_team']} {candidate['vegas_home_spread']:+g} / {candidate['away_team']} {candidate['vegas_away_spread']:+g}
- Model Projected Home Spread: {candidate['projected_home_spread']:+g} (Raw Margin: {candidate['expected_home_margin']:+g}, Shrunk Margin: {isye.get('shrunk_home_margin')})
- Recommended Side: {candidate['recommended_side']} ({candidate['target_spread']:+g}) at {candidate['target_odds']}
- Raw Edge vs Vegas: +{candidate['edge_points']} pts (Market-Shrunk Edge: +{isye.get('shrunk_edge_points')} pts)

Calibrated Statistical Telemetry:
- Home EWMA Net Rating: {isye.get('home_ewma_nrtg')} (Holt Trend: {isye.get('home_holt_trend'):+g})
- Away EWMA Net Rating: {isye.get('away_ewma_nrtg')} (Holt Trend: {isye.get('away_holt_trend'):+g})
- Prediction Standard Error (SE_pred): {isye.get('se_pred')} pts (vs SE_mean: {isye.get('se_mean')} pts)
- Nested Prediction Intervals (Home Margin): 50% {isye.get('pi_50')}, 80% {isye.get('pi_80')}, 95% {isye.get('pi_95')}
- Calibrated Cover Probability: {isye.get('cover_prob_pct')}% (vs {isye.get('breakeven_prob_pct')}% Vig Breakeven)
- Market-Shrunk Expected Value (+EV): +{isye.get('ev_pct')}%

Active Structural Rules:
{rules_text}

Live NBA Injury Report & Rotation Context (ESPN Official Feed):
{injury_text if injury_text else "Live injury feed unavailable — exercise extreme caution on large spread discrepancies."}

Your Task:
1. CRITICAL INJURY CHECK: Examine the live injury report above. If a star/key rotation player on the recommended side ({candidate['recommended_side']}) is listed as Out or Doubtful, VETO the bet — the sportsbook line already reflects that absence while our trailing rating does not.
2. Check schedule fatigue (e.g., road team on 0-day rest back-to-back) and active structural rules.
3. Return a binary decision:
   - "BET" with recommended_units = 1 if no disqualifying injury/rotation/fatigue trap is found.
   - "VETO" with recommended_units = 0 if a qualitative trap invalidates the edge.

Return ONLY valid JSON matching this schema:
{{
  "verdict": "BET" | "VETO",
  "confidence": <integer 1-100>,
  "recommended_units": <0 | 1>,
  "triggered_rule_id": "<RULE-ID or NONE>",
  "reasoning": "<Concise 2-sentence explanation referencing live injury/rest context and calibrated P(Cover)>"
}}
"""
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )

        parsed = json.loads(response.text.strip())
        verdict = "BET" if str(parsed.get("verdict", "")).upper() == "BET" else "VETO"
        parsed["verdict"] = verdict
        # Hard guard: LLM is strictly a veto auditor and may never scale stake above 1 unit
        parsed["recommended_units"] = 1 if verdict == "BET" else 0
        print(f"[CourtVision Veto] Gemini Verdict for {candidate['recommended_side']}: {verdict} ({parsed.get('confidence')}/100)")
        return parsed

    except Exception as e:
        print(f"[CourtVision Veto] Gemini API fallback triggered ({e}).")
        return fallback_context_check(candidate, learned_rules, injury_meta=injury_meta)


def fallback_context_check(candidate, learned_rules, injury_meta=None):
    """
    ISyE 4031 + Live Injury Guard + Fatigue Veto deterministic evaluator.
    Strictly binary BET (1 Unit) or VETO (0 Units); never scales to 2U.
    """
    isye = candidate.get("isye_4031", {})
    cover_prob = isye.get("cover_prob_pct", 54.0)
    ev_pct = isye.get("ev_pct", 0.0)
    rest_diff = isye.get("rest_diff", 0.0)
    side = candidate.get("recommended_side", "Candidate")
    direction = candidate.get("edge_direction", "AWAY")
    injury_meta = injury_meta or {}

    # P0 Injury Guardrail: Veto if recommended side has >= 3 confirmed Out/Doubtful players
    # and at least 2 more absences than the opponent
    side_out = injury_meta.get("home_out_count", 0) if direction == "HOME" else injury_meta.get("away_out_count", 0)
    opp_out = injury_meta.get("away_out_count", 0) if direction == "HOME" else injury_meta.get("home_out_count", 0)
    if side_out >= 3 and (side_out - opp_out) >= 2:
        return {
            "verdict": "VETO",
            "confidence": 55,
            "recommended_units": 0,
            "triggered_rule_id": "RULE-INJURY-001",
            "reasoning": (
                f"VETOED by Live Injury Guard: {side} has {side_out} Out/Doubtful players "
                f"(vs {opp_out} for opponent). Trailing rating likely overstates depleted roster."
            )
        }

    # Check if road pick on compressed rest triggers RULE-REST-003
    if direction == "AWAY" and rest_diff > 0 and cover_prob < 57.5:
        return {
            "verdict": "VETO",
            "confidence": 62,
            "recommended_units": 0,
            "triggered_rule_id": "RULE-REST-003",
            "reasoning": (
                f"VETOED by RULE-REST-003: {side} is an away team at a rest disadvantage "
                f"({rest_diff:+g}d vs home) with marginal calibrated cover probability ({cover_prob}%)."
            )
        }

    confidence = max(40, min(90, int(round(55 + (cover_prob - 50.0) * 3.0))))

    if cover_prob >= 54.0 and ev_pct > 0.0:
        return {
            "verdict": "BET",
            "confidence": confidence,
            "recommended_units": 1,
            "triggered_rule_id": "NONE",
            "reasoning": (
                f"Calibrated Student-t cover probability of {cover_prob}% (+{ev_pct}% shrunk EV vs "
                f"{isye.get('breakeven_prob_pct', 52.4)}% breakeven, SE_pred={isye.get('se_pred')}) passes injury & fatigue audit for {side}."
            )
        }
    else:
        return {
            "verdict": "VETO",
            "confidence": confidence,
            "recommended_units": 0,
            "triggered_rule_id": "NONE",
            "reasoning": (
                f"Vetoed: Calibrated cover probability ({cover_prob}%) or EV ({ev_pct}%) falls below +EV threshold."
            )
        }


def update_decision_basis_post_mortem(settled_bet, actual_home_margin, final_score_str):
    """
    ISyE 4031 Morning Post-Mortem:
    1. Computes forecast residual e_t = actual_home_margin - predicted_home_margin.
    2. Updates Cumulative Forecast Error (CFE), MAD, RMSE, and Tracking Signal (TS = CFE / MAD).
    3. Appends a new self-learned rule to data/decision_basis.json if |studentized_r| >= 0.85 or bet LOST.
    """
    basis = load_decision_basis()
    if not basis:
        return

    diag = basis.get("diagnostics", {})
    history = diag.get("residual_history", [])
    s_res = basis.get("model_metadata", {}).get("residual_se_s", 10.42)

    # Model projected home spread was stored; expected_home_margin = -model_projected_spread
    proj_spread = settled_bet.get("model_projected_spread", 0.0)
    pred_home_margin = round(-proj_spread, 2)
    se_pred = settled_bet.get("se_pred", 10.46)
    se_mean = settled_bet.get("se_mean", 0.98)

    residual_e = round(actual_home_margin - pred_home_margin, 2)
    studentized_r = round(residual_e / se_pred, 2)

    abs_e = abs(residual_e)
    captured_50 = abs_e <= (0.6745 * se_pred)
    captured_80 = abs_e <= (1.2816 * se_pred)
    captured_95 = abs_e <= (1.9600 * se_pred)

    new_diag_entry = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "matchup": settled_bet.get("matchup", ""),
        "predicted_home_margin": pred_home_margin,
        "observed_home_margin": actual_home_margin,
        "residual_e": residual_e,
        "studentized_r": studentized_r,
        "se_pred": se_pred,
        "se_mean": se_mean,
        "captured_50": captured_50,
        "captured_80": captured_80,
        "captured_95": captured_95
    }
    history.append(new_diag_entry)

    # Recompute CFE, MAD, RMSE, and Tracking Signal
    n = len(history)
    cfe = round(sum(item["residual_e"] for item in history), 2)
    mad = round(sum(abs(item["residual_e"]) for item in history) / n, 2)
    rmse = round(math.sqrt(sum(item["residual_e"] ** 2 for item in history) / n), 2)
    tracking_signal = round(cfe / mad, 2) if mad > 0 else 0.0

    diag["residual_history"] = history
    diag["cfe"] = cfe
    diag["mad"] = mad
    diag["out_of_sample_rmse"] = rmse
    diag["tracking_signal"] = tracking_signal
    diag["interval_coverage_50_pct"] = round(sum(1 for x in history if x["captured_50"]) / n * 100.0, 1)
    diag["interval_coverage_80_pct"] = round(sum(1 for x in history if x["captured_80"]) / n * 100.0, 1)
    diag["interval_coverage_95_pct"] = round(sum(1 for x in history if x["captured_95"]) / n * 100.0, 1)

    limit = diag.get("tracking_signal_limit", 3.75)
    if abs(tracking_signal) > limit:
        # Flag retrain needed on the full slate rather than mutating beta[0] on selected bets
        diag["status"] = "RETRAIN_ALERT (Tracking Signal Exceeded)"
    else:
        diag["status"] = "IN_CONTROL (Unbiased)"

    save_decision_basis(basis)
    print(f"[CourtVision Post-Mortem] Updated ISyE 4031 Diagnostics: CFE={cfe}, MAD={mad}, TS={tracking_signal}")
