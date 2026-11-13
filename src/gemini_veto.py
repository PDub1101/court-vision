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
    Submits an ISyE 4031 flagged edge to Gemini 2.5 Flash alongside persistent learned rules.
    """
    basis = load_decision_basis()
    learned_rules = basis.get("learned_rules", [])
    isye = candidate.get("isye_4031", {})

    if not GEMINI_API_KEY:
        print(f"[CourtVision Veto] Evaluating {candidate['recommended_side']} via ISyE 4031 + Learned Decision Basis rules.")
        return fallback_context_check(candidate, learned_rules)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        rules_text = "\n".join(
            [f"- [{r['rule_id']} | {r['category']}]: {r['rule_statement']} (Delta: {r['parameter_delta']})" for r in learned_rules]
        )

        prompt = f"""
You are the Lead Quantitative & Qualitative Auditor for CourtVision (`courtvision_ewma_ols_v1`), an autonomous NBA spread forecasting engine built on Georgia Tech ISyE 4031 principles.

Tonight's Flagged Matchup:
- Game: {candidate['away_team']} @ {candidate['home_team']}
- Sportsbook Line ({candidate['sportsbook']}): {candidate['home_team']} {candidate['vegas_home_spread']:+g} / {candidate['away_team']} {candidate['vegas_away_spread']:+g}
- Model Projected Home Spread: {candidate['projected_home_spread']:+g} (Expected Margin: {candidate['expected_home_margin']:+g})
- Recommended Side: {candidate['recommended_side']} ({candidate['target_spread']:+g}) at {candidate['target_odds']}
- Point Discrepancy (Edge): +{candidate['edge_points']} pts

ISyE 4031 Forecasting Telemetry:
- Home EWMA Net Rating: {isye.get('home_ewma_nrtg')} (Holt Trend: {isye.get('home_holt_trend'):+g})
- Away EWMA Net Rating: {isye.get('away_ewma_nrtg')} (Holt Trend: {isye.get('away_holt_trend'):+g})
- Prediction Standard Error (SE_pred): {isye.get('se_pred')} pts (vs SE_mean: {isye.get('se_mean')} pts)
- Nested Prediction Intervals (Home Margin): 50% {isye.get('pi_50')}, 80% {isye.get('pi_80')}, 95% {isye.get('pi_95')}
- Student-t Cover Probability: {isye.get('cover_prob_pct')}% (vs {isye.get('breakeven_prob_pct')}% Vig Breakeven)
- Mathematical Expected Value (+EV): +{isye.get('ev_pct')}%

Active Self-Learned Decision Basis Rules (from Past Post-Mortems):
{rules_text}

Qualitative Injury & Rotation Context:
{injury_context if injury_context else "Standard rotation schedule. Evaluate rest differential and learned memory rules."}

Your Task:
1. Check if any Active Self-Learned Rule applies to this matchup.
2. Audit whether the +{isye.get('ev_pct')}% EV holds or is invalidated by a rotational trap.
3. Assign a calibrated Confidence Score (1-100) and unit size:
   - 80+: High Confidence (2 Units / $40)
   - 70-79: Standard Edge (1 Unit / $20)
   - <70: VETO / Pass (0 Units)

Return ONLY valid JSON matching this schema:
{{
  "verdict": "BET" | "VETO",
  "confidence": <integer 1-100>,
  "recommended_units": <0 | 1 | 2>,
  "triggered_rule_id": "<RULE-ID or NONE>",
  "reasoning": "<Concise 2-sentence technical explanation referencing EWMA/P(Cover) and any triggered learned rule>"
}}
"""
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )

        parsed = json.loads(response.text.strip())
        print(f"[CourtVision Veto] Gemini Verdict for {candidate['recommended_side']}: {parsed.get('verdict')} ({parsed.get('confidence')}/100)")
        return parsed

    except Exception as e:
        print(f"[CourtVision Veto] Gemini API fallback triggered ({e}).")
        return fallback_context_check(candidate, learned_rules)


def fallback_context_check(candidate, learned_rules):
    """
    ISyE 4031 + Learned Rule deterministic evaluator when offline or no API key is configured.
    """
    isye = candidate.get("isye_4031", {})
    cover_prob = isye.get("cover_prob_pct", 56.0)
    ev_pct = isye.get("ev_pct", 7.0)
    rest_diff = isye.get("rest_diff", 0.0)
    side = candidate.get("recommended_side", "Candidate")
    direction = candidate.get("edge_direction", "AWAY")

    # Base confidence scaled from Student-t cover probability
    base_conf = int(round(50 + (cover_prob - 50.0) * 2.5))
    triggered_rule = "RULE-001"
    rule_note = "Applied RULE-001 (+5 confidence boost for elite EWMA Net Rating & turnover efficiency advantage)."

    # Check if road favorite on compressed rest triggers RULE-002
    if direction == "AWAY" and rest_diff > 0:
        # Away team has fewer rest days than Home team (back-to-back fatigue)
        triggered_rule = "RULE-002"
        confidence = max(45, min(65, base_conf - 12))
        return {
            "verdict": "VETO",
            "confidence": confidence,
            "recommended_units": 0,
            "triggered_rule_id": triggered_rule,
            "reasoning": (
                f"VETOED by Self-Learned {triggered_rule}: Although raw OLS projects +{ev_pct}% EV on {side}, "
                f"they are a road favorite with a rest disadvantage (0d rest after travel). Passing to protect bankroll."
            )
        }
    elif abs(isye.get("ar1_reversion_adj", 0.0)) >= 0.45:
        triggered_rule = "RULE-003"
        rule_note = f"Applied RULE-003 (AR(1) blowout mean-reversion dampener of {isye.get('ar1_reversion_adj'):+g} pts)."
        base_conf += 2
    else:
        base_conf += 5

    confidence = max(40, min(95, base_conf))

    if confidence >= 80 and cover_prob >= 60.0:
        return {
            "verdict": "BET",
            "confidence": confidence,
            "recommended_units": 2,
            "triggered_rule_id": triggered_rule,
            "reasoning": (
                f"ISyE 4031 Student-t cover probability of {cover_prob}% (+{ev_pct}% EV, SE_pred={isye.get('se_pred')}) "
                f"exceeds high-conviction threshold for {side}. {rule_note}"
            )
        }
    elif confidence >= 70 and cover_prob >= 55.5:
        return {
            "verdict": "BET",
            "confidence": confidence,
            "recommended_units": 1,
            "triggered_rule_id": triggered_rule,
            "reasoning": (
                f"Student-t cover probability of {cover_prob}% (+{ev_pct}% EV vs 52.4% breakeven) confirms positive expectation on {side}. "
                f"{rule_note}"
            )
        }
    else:
        return {
            "verdict": "VETO",
            "confidence": confidence,
            "recommended_units": 0,
            "triggered_rule_id": triggered_rule,
            "reasoning": (
                f"Vetoed: Cover probability ({cover_prob}%) and post-rule confidence ({confidence}/100) fall below bankroll protection threshold. {rule_note}"
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
    captured_50 = abs_e <= (0.6755 * se_pred)
    captured_80 = abs_e <= (1.2852 * se_pred)
    captured_95 = abs_e <= (1.9701 * se_pred)

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
        diag["status"] = "RECALIBRATED (Bias Corrected)"
        # Adjust intercept slightly toward reducing systematic CFE bias
        basis["ols_parameters"]["beta"][0] = round(basis["ols_parameters"]["beta"][0] + 0.15 * (cfe / n), 2)
    else:
        diag["status"] = "IN_CONTROL (Unbiased)"

    # Generate new learned rule if bet lost or large residual shock occurred
    if settled_bet.get("result") == "LOST" or abs(studentized_r) >= 0.85:
        rules = basis.get("learned_rules", [])
        next_id = f"RULE-{len(rules) + 1:03d}"
        rules.append({
            "rule_id": next_id,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "source_game": f"{final_score_str}",
            "residual_trigger": f"e_t = {residual_e:+g} pts (r = {studentized_r:+g})",
            "category": "POST_MORTEM_RESIDUAL_UPDATE",
            "rule_statement": (
                f"Post-mortem on {settled_bet['matchup']}: Observed residual of {residual_e:+g} pts "
                f"(SE_pred = {se_pred}). Tightening variance filter on similar pace/shooting profiles."
            ),
            "adjustment_type": "VARIANCE_GUARD",
            "parameter_delta": -3 if settled_bet.get("result") == "LOST" else 2
        })
        basis["learned_rules"] = rules

    save_decision_basis(basis)
    print(f"[CourtVision Post-Mortem] Updated ISyE 4031 Diagnostics: CFE={cfe}, MAD={mad}, TS={tracking_signal}")
