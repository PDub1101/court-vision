"""
CourtVision Bankroll Manager
Manages the $1,000 paper trading bankroll, unit allocation,
active open wagers, and settled ledger accounting.
"""

import os
import json
from datetime import datetime, timezone

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
    Places a paper bet if approved by Gemini veto engine.
    """
    state = load_bankroll_state()

    # Avoid duplicate active bets on same game and side
    game_id = candidate["game_id"]
    for active in state.get("active_bets", []):
        if active["game_id"] == game_id and active["selection"] == candidate["recommended_side"]:
            print(f"[Bankroll] Bet already active for {candidate['recommended_side']}. Skipping duplicate.")
            return None

    units = veto_verdict.get("recommended_units", 1)
    if units <= 0 or veto_verdict.get("verdict") != "BET":
        print(f"[Bankroll] No bet placed on {candidate['recommended_side']} (Vetoed or 0 units).")
        return None

    stake = UNIT_2_AMOUNT if units == 2 else UNIT_1_AMOUNT
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
        "gemini_confidence": veto_verdict.get("confidence", 75),
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
    Settles a pending bet given actual game margin.
    actual_margin: Home Score - Away Score.
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

    # Determine spread cover:
    # If picking Home +3.5: Home covers if (Home - Away) + 3.5 > 0
    # If picking Away -2.5: Away covers if (Away - Home) - 2.5 > 0 -> (-(Home - Away)) - 2.5 > 0
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

    # Metrics update
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

    # Move from active to settled
    del state["active_bets"][bet_idx]
    now_utc = datetime.now(timezone.utc)
    settled_entry = {
        **bet,
        "result": result,
        "final_score": final_score_str,
        "cover_margin": round(cover_diff, 1),
        "net_pnl": pnl,
        "settled_at": now_utc.strftime("%Y-%m-%d %H:%M:%S")
    }
    state["settled_bets"].insert(0, settled_entry)

    # Log to equity history
    state["equity_history"].append({
        "date": now_utc.strftime("%Y-%m-%d"),
        "balance": state["bankroll"]["current_balance"],
        "pnl": pnl,
        "note": f"{result}: {bet['selection']} ({final_score_str})"
    })

    save_bankroll_state(state)
    print(f"[Bankroll] Settled {bet_id} as {result} ({pnl:+$g}). New balance: ${state['bankroll']['current_balance']}")
    return True
