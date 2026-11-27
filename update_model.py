"""
CourtVision Master Pipeline Script (update_model.py)
Automates daily end-to-end execution of the ISyE 4031 Forecasting & +EV Engine:
1. Grade finished bets from overnight & run Post-Mortem residual diagnostics.
2. Ingest live sportsbook lines (The Odds API) and NBA team metrics (nba_api).
3. Execute `courtvision_ewma_ols_v1`: Holt EWMA, Multivariate OLS, SE_pred Nested Intervals, Student-t P(Cover), +EV%.
4. Apply Gemini 2.5 Flash context audit + Self-Learning Decision Basis rules.
5. Place simulated bets from the $1,000 paper bankroll.
6. Export web-ready payload to data/courtvision_data.js and docs/courtvision_data.js.
"""

import os
import json
from datetime import datetime, timezone

from src.grader import grade_active_bets
from src.data_fetcher import (
    get_live_nba_odds,
    get_team_advanced_metrics,
    get_live_nba_injuries,
    format_matchup_injury_context,
)
from src.quant_model import analyze_slate, load_decision_basis
from src.gemini_veto import audit_with_gemini
from src.bankroll_manager import load_bankroll_state, place_simulated_wager, recompute_metrics, save_bankroll_state
from src.forecaster import run_30day_monte_carlo, estimate_shrunk_win_rate


DATA_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "courtvision_data.js")
DOCS_DATA_PATH = os.path.join(os.path.dirname(__file__), "docs", "courtvision_data.js")
ROOT_DATA_PATH = os.path.join(os.path.dirname(__file__), "courtvision_data.js")


def run_pipeline():
    print("=" * 72)
    print(" CourtVision ISyE 4031 Forecasting & +EV Engine (courtvision_ewma_ols_v1) ")
    print("=" * 72)

    # Step 1: Grade any pending bets from overnight games
    print("\n[Step 1/5] Running Morning Auto-Grader & Residual Post-Mortems...")
    settled = grade_active_bets()
    print(f"Settled {settled} completed bets.")

    # Step 2: Fetch current live lines, chronological 30-team metrics & live injury reports
    print("\n[Step 2/5] Fetching Sportsbook Odds, Chronological 30-Team Metrics & Live Injuries...")
    games = get_live_nba_odds()
    metrics = get_team_advanced_metrics()
    injuries = get_live_nba_injuries()
    print(f"Loaded {len(games)} games, {len(metrics)}/30 live team series, and injury reports for {len(injuries)} teams.")

    # Step 3: Run ISyE 4031 Quantitative Spread & Student-t +EV Engine
    print("\n[Step 3/5] Executing ISyE 4031 Damped Holt + Ridge + Market-Shrinkage Engine...")
    all_projections, flagged_edges = analyze_slate(games, metrics)
    skipped_missing = sum(1 for p in all_projections if p.get("data_missing"))
    blocked_sanity = sum(1 for p in all_projections if p.get("edge_sanity_blocked"))
    print(f"Analyzed {len(all_projections)} matchups ({skipped_missing} skipped for missing data, {blocked_sanity} blocked by edge sanity cap).")
    print(f"Identified {len(flagged_edges)} positive-EV edges (3.0-7.5 pts & P(Cover) >= 54.0%).")

    # Step 4: Run Gemini Context Veto + Live Injury Report + Learned Decision Basis & Place Simulated Bets
    print("\n[Step 4/5] Executing Gemini Context Veto & Live Injury Check...")
    evaluated_picks = []

    for candidate in flagged_edges:
        isye = candidate.get("isye_4031", {})
        injury_ctx = format_matchup_injury_context(
            candidate["home_team"], candidate["away_team"], injuries
        )
        print(
            f"Auditing: {candidate['recommended_side']} ({candidate['target_spread']:+g}) | "
            f"P(Cover)={isye.get('cover_prob_pct')}% | EV=+{isye.get('ev_pct')}% | SE_pred={isye.get('se_pred')} | "
            f"Out/Doubtful: Away={injury_ctx['away_out_count']}, Home={injury_ctx['home_out_count']}"
        )
        veto_result = audit_with_gemini(candidate, injury_context=injury_ctx)

        evaluated_item = {
            **candidate,
            "gemini_verdict": veto_result.get("verdict", "BET"),
            "gemini_confidence": veto_result.get("confidence", 78),
            "gemini_units": veto_result.get("recommended_units", 1),
            "triggered_rule_id": veto_result.get("triggered_rule_id", "NONE"),
            "gemini_reasoning": veto_result.get("reasoning", "")
        }
        evaluated_picks.append(evaluated_item)

        if veto_result.get("verdict") == "BET":
            place_simulated_wager(candidate, veto_result)

    # Step 5: Export Web Data Bundle
    print("\n[Step 5/5] Exporting Dashboard State, ISyE 4031 Diagnostics & Decision Basis...")
    bankroll_state = load_bankroll_state()
    recompute_metrics(bankroll_state)
    save_bankroll_state(bankroll_state)
    decision_basis = load_decision_basis()
    current_balance = bankroll_state["bankroll"]["current_balance"]
    metrics_data = bankroll_state.get("metrics", {})
    wins = int(metrics_data.get("wins", 0))
    losses = int(metrics_data.get("losses", 0))
    decided = wins + losses
    raw_wr = (wins / decided) if decided > 0 else None
    shrunk_wr = estimate_shrunk_win_rate(wins, losses, prior_win_rate=0.50, prior_strength=100)

    n_settled = len(bankroll_state.get("settled_bets", []))
    n_days = len(bankroll_state.get("equity_history", []))
    emp_bets_per_day = min(3.5, max(0.5, n_settled / max(1, n_days))) if n_settled > 0 else 1.5

    kelly_pcts = [
        float(p.get("isye_4031", {}).get("quarter_kelly_pct", 0.0)) / 100.0
        for p in evaluated_picks
        if p.get("gemini_verdict") == "BET"
    ]
    avg_bet_pct = (
        min(0.02, max(0.005, sum(kelly_pcts) / len(kelly_pcts)))
        if kelly_pcts
        else 0.0125
    )

    forecast_30d = run_30day_monte_carlo(
        starting_capital=current_balance,
        days=30,
        bets_per_day=round(emp_bets_per_day, 2),
        win_rate=shrunk_wr,
        odds=-110,
        unit_pct=round(avg_bet_pct, 4),
        raw_win_rate=raw_wr,
        sample_size=decided,
    )

    web_payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "bankroll_state": bankroll_state,
        "decision_basis": decision_basis,
        "todays_slate": all_projections,
        "evaluated_picks": evaluated_picks,
        "forecast_30d": forecast_30d
    }

    js_content = f"// Auto-generated by CourtVision ISyE 4031 daily pipeline\nwindow.COURTVISION_DATA = {json.dumps(web_payload, indent=2)};\n"
    
    os.makedirs(os.path.dirname(DATA_OUTPUT_PATH), exist_ok=True)
    with open(DATA_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(js_content)

    os.makedirs(os.path.dirname(DOCS_DATA_PATH), exist_ok=True)
    with open(DOCS_DATA_PATH, "w", encoding="utf-8") as f:
        f.write(js_content)

    with open(ROOT_DATA_PATH, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"Successfully exported web payload to {DOCS_DATA_PATH}")
    print("\n[CourtVision] Pipeline completed successfully.")


if __name__ == "__main__":
    run_pipeline()
