"""
CourtVision Bankroll Manager
Manages the $1,000 paper trading bankroll, unit allocation,
active open wagers, settled ledger accounting, and triggers ISyE 4031 Post-Mortems.
"""

import os
import json
from datetime import datetime, timezone
from src.gemini_veto import update_decision_basis_post_mortem

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bankroll_state.json")
UNIT_1_AMOUNT = 20.0
UNIT_2_AMOUNT = 40.0


def load_bankroll_state():
    """
    Loads bankroll ledger from JSON file.
    """
    if not os.path.exists(STATE_PATH):
        raise FileNotFoundError(f"State file not found at {STATE_PATH}")
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_bankroll_state(state):
    """
    Persists updated bankroll state to disk.
    """
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def calculate_potential_profit(stake, american_odds):
    """
    Computes true net profit for American odds format (-110, +120).
    """
    if american_odds < 0:
        return round(stake * (100.0 / abs(american_odds)), 2)
    else:
        return round(stake * (american_odds / 100.0), 2)


def place_simulated_wager(candidate, veto_verdict):
    """
    Places a paper bet if approved by the ISyE 4031 + Gemini veto engine.
    """
    state = load_bankroll_state()
    isye = candidate.get("isye_4031", {})

    # Check if an active bet already exists for this game_id
    game_id = candidate["game_id"]
    for idx, active in enumerate(state.get("active_bets", [])):
        if active["game_id"] == game_id and active["selection"] == candidate["recommended_side"]:
            # Enrich existing active bet with latest ISyE 4031 telemetry
            active["cover_prob_pct"] = isye.get("cover_prob_pct", 60.5)
            active["ev_pct"] = isye.get("ev_pct", 15.5)
            active["se_pred"] = isye.get("se_pred", 10.46)
            active["se_mean"] = isye.get("se_mean", 0.96)
            active["pi_80"] = isye.get("pi_80", [-8.0, 18.0])
            active["triggered_rule_id"] = veto_verdict.get("triggered_rule_id", "RULE-001")
            active["gemini_confidence"] = veto_verdict.get("confidence", active.get("gemini_confidence", 78))
            active["gemini_reasoning"] = veto_verdict.get("reasoning", active.get("gemini_reasoning", ""))
            save_bankroll_state(state)
            print(f"[Bankroll] Synced ISyE 4031 telemetry for active bet on {candidate['recommended_side']}.")
            return active

    units = veto_verdict.get("recommended_units", 1)
    if units <= 0 or veto_verdict.get("verdict") != "BET":
        print(f"[Bankroll] No bet placed on {candidate['recommended_side']} (Vetoed or 0 units).")
        return None

    stake = UNIT_2_AMOUNT if units == 2 else UNIT_1_AMOUNT
    if state["bankroll"]["available_cash"] < stake:
        print(f"[Bankroll] Insufficient available cash (${state['bankroll']['available_cash']}) to stake ${stake} on {candidate['recommended_side']}.")
        return None

    odds = candidate.get("target_odds", -110)
    potential_profit = calculate_potential_profit(stake, odds)

    now_utc = datetime.now(timezone.utc)
    new_bet = {
        "bet_id": f"bet_{now_utc.strftime('%Y%m%d_%H%M%S')}_{candidate['recommended_side'][:3].lower()}",
        "game_id": game_id,
        "date_placed": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "matchup": f"{candidate['away_team']} @ {candidate['home_team']}",
        "selection": candidate["recommended_side"],
        "line": candidate["target_spread"],
        "odds": odds,
        "sportsbook": candidate["sportsbook"],
        "stake": stake,
        "units": units,
        "potential_profit": potential_profit,
        "model_projected_spread": candidate["projected_home_spread"],
        "edge_points": candidate["edge_points"],
        "cover_prob_pct": isye.get("cover_prob_pct", 58.0),
        "ev_pct": isye.get("ev_pct", 10.5),
        "se_pred": isye.get("se_pred", 10.46),
        "se_mean": isye.get("se_mean", 0.96),
        "pi_80": isye.get("pi_80", [-8.0, 18.0]),
        "triggered_rule_id": veto_verdict.get("triggered_rule_id", "RULE-001"),
        "gemini_confidence": veto_verdict.get("confidence", 78),
        "gemini_reasoning": veto_verdict.get("reasoning", ""),
        "status": "PENDING"
    }

    state["bankroll"]["available_cash"] = round(state["bankroll"]["available_cash"] - stake, 2)
    state["bankroll"]["in_play_equity"] = round(state["bankroll"]["in_play_equity"] + stake, 2)
    state["active_bets"].append(new_bet)

    save_bankroll_state(state)
    print(f"[Bankroll] Placed {units}U (${stake}) on {new_bet['selection']} ({new_bet['line']:+g}) at {odds}. Cash: ${state['bankroll']['available_cash']}")
    return new_bet


def settle_bet(bet_id, actual_margin, final_score_str):
    """
    Settles a pending bet given actual game margin (Home Score - Away Score)
    and triggers the ISyE 4031 post-mortem residual diagnostic & LLM rule update.
    """
    state = load_bankroll_state()
    bet = None
    bet_idx = -1

    for idx, b in enumerate(state.get("active_bets", [])):
        if b["bet_id"] == bet_id:
            bet = b
            bet_idx = idx
            break

    if not bet:
        print(f"[Bankroll] Bet {bet_id} not found in active bets.")
        return False

    stake = bet["stake"]
    odds = bet["odds"]
    line = bet["line"]
    is_home_pick = (bet["selection"] in bet["matchup"].split(" @ ")[1])

    if is_home_pick:
        cover_diff = actual_margin + line
    else:
        cover_diff = (-actual_margin) + line

    if cover_diff > 0:
        result = "WON"
        profit = calculate_potential_profit(stake, odds)
        pnl = profit
        state["bankroll"]["available_cash"] = round(state["bankroll"]["available_cash"] + stake + profit, 2)
    elif cover_diff < 0:
        result = "LOST"
        profit = 0.0
        pnl = -stake
    else:
        result = "PUSH"
        profit = 0.0
        pnl = 0.0
        state["bankroll"]["available_cash"] = round(state["bankroll"]["available_cash"] + stake, 2)

    state["bankroll"]["in_play_equity"] = round(state["bankroll"]["in_play_equity"] - stake, 2)
    state["bankroll"]["current_balance"] = round(state["bankroll"]["available_cash"] + state["bankroll"]["in_play_equity"], 2)
    state["bankroll"]["total_profit_loss"] = round(state["bankroll"]["current_balance"] - state["bankroll"]["starting_capital"], 2)
    state["bankroll"]["roi_percent"] = round((state["bankroll"]["total_profit_loss"] / state["bankroll"]["starting_capital"]) * 100.0, 2)

    metrics = state["metrics"]
    metrics["total_bets"] += 1
    if result == "WON":
        metrics["wins"] += 1
        curr_streak = metrics.get("current_streak", "")
        if curr_streak.startswith("W"):
            count = int(curr_streak[1:]) + 1
            metrics["current_streak"] = f"W{count}"
        else:
            metrics["current_streak"] = "W1"
    elif result == "LOST":
        metrics["losses"] += 1
        curr_streak = metrics.get("current_streak", "")
        if curr_streak.startswith("L"):
            count = int(curr_streak[1:]) + 1
            metrics["current_streak"] = f"L{count}"
        else:
            metrics["current_streak"] = "L1"
    else:
        metrics["pushes"] += 1

    decided = metrics["wins"] + metrics["losses"]
    metrics["win_rate_percent"] = round((metrics["wins"] / decided * 100.0), 1) if decided > 0 else 0.0

    del state["active_bets"][bet_idx]
    now_utc = datetime.now(timezone.utc)
    settled_entry = {
        **bet,
        "status": "SETTLED",
        "result": result,
        "final_score": final_score_str,
        "cover_margin": round(cover_diff, 1),
        "net_pnl": pnl,
        "bankroll_after": state["bankroll"]["current_balance"],
        "settled_at": now_utc.strftime("%Y-%m-%d %H:%M:%S")
    }
    state["settled_bets"].insert(0, settled_entry)

    bet_summary = {
        "bet_id": bet["bet_id"],
        "matchup": bet.get("matchup", ""),
        "selection": bet["selection"],
        "line": bet["line"],
        "odds": odds,
        "stake": stake,
        "units": bet.get("units", 1),
        "result": result,
        "net_pnl": pnl,
        "final_score": final_score_str,
        "sportsbook": bet.get("sportsbook", "")
    }

    today_str = now_utc.strftime("%Y-%m-%d")
    existing_entry = next((h for h in state["equity_history"] if h["date"] == today_str), None)
    if existing_entry:
        existing_entry["balance"] = state["bankroll"]["current_balance"]
        existing_entry["pnl"] = round(existing_entry.get("pnl", 0.0) + pnl, 2)
        if "bets" not in existing_entry:
            existing_entry["bets"] = []
        existing_entry["bets"].append(bet_summary)
        won_cnt = sum(1 for b in existing_entry["bets"] if b.get("result") == "WON")
        lost_cnt = sum(1 for b in existing_entry["bets"] if b.get("result") == "LOST")
        pnl_val = existing_entry["pnl"]
        sign = "+" if pnl_val >= 0 else ""
        existing_entry["note"] = f"Day Settlement: {len(existing_entry['bets'])} bets ({won_cnt}W-{lost_cnt}L, {sign}${pnl_val:.2f})"
    else:
        state["equity_history"].append({
            "date": today_str,
            "balance": state["bankroll"]["current_balance"],
            "pnl": pnl,
            "bets": [bet_summary],
            "note": f"{result}: {bet['selection']} ({final_score_str})"
        })

    save_bankroll_state(state)
    sign = "+" if pnl >= 0 else "-"
    print(f"[Bankroll] Settled {bet_id} as {result} ({sign}${abs(pnl):.2f}). New balance: ${state['bankroll']['current_balance']:.2f}")

    # Trigger ISyE 4031 Morning Post-Mortem & Self-Learning Rule Update
    try:
        update_decision_basis_post_mortem(settled_entry, actual_margin, final_score_str)
    except Exception as e:
        print(f"[Bankroll] Post-mortem update warning: {e}")

    return True
