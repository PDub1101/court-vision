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

# P2 Fractional Kelly & Hard Bankroll Risk Controls
MAX_SINGLE_BET_PCT = 0.02        # 2.0% hard cap per wager
MIN_SINGLE_BET_PCT = 0.005       # 0.5% floor for approved +EV wagers
MIN_STAKE_DOLLARS = 5.0
MAX_IN_PLAY_EXPOSURE_PCT = 0.10  # 10.0% max simultaneous in-play exposure
DRAWDOWN_THROTTLE_PCT = 15.0     # Halve bet sizing once drawdown >= 15%
DRAWDOWN_HALT_PCT = 25.0         # Halt new wagers once drawdown >= 25%


def compute_current_drawdown_pct(state):
    """
    Computes current peak-to-trough drawdown percentage (>= 0.0) across starting capital,
    equity history, and current balance.
    """
    bankroll = state.get("bankroll", {})
    start_cap = float(bankroll.get("starting_capital", 1000.0))
    current_balance = float(bankroll.get("current_balance", start_cap))
    peak = max(start_cap, current_balance)
    for h in state.get("equity_history", []):
        bal = float(h.get("balance", start_cap))
        if bal > peak:
            peak = bal
    if peak <= 0.0:
        return 0.0
    return round(max(0.0, ((peak - current_balance) / peak) * 100.0), 2)


def calculate_risk_managed_stake(state, isye_telemetry):
    """
    Computes a bankroll-proportional stake using Quarter-Kelly sizing constrained by:
    - 2.0% single-bet hard cap (0.5% floor when +EV)
    - 10.0% simultaneous in-play exposure cap
    - 15% drawdown throttle (halves size) and 25% drawdown circuit-breaker halt
    Returns (stake_dollars, units, risk_status, reason).
    """
    current_dd = compute_current_drawdown_pct(state)
    if current_dd >= DRAWDOWN_HALT_PCT:
        return (
            0.0,
            0.0,
            "DRAWDOWN_HALT",
            f"Drawdown circuit breaker triggered ({current_dd:.1f}% >= {DRAWDOWN_HALT_PCT:.1f}% halt).",
        )

    bankroll = state.get("bankroll", {})
    current_balance = float(bankroll.get("current_balance", 0.0))
    in_play = float(bankroll.get("in_play_equity", 0.0))
    available_cash = float(bankroll.get("available_cash", 0.0))

    q_kelly_frac = float(isye_telemetry.get("quarter_kelly_pct", 0.0)) / 100.0
    if q_kelly_frac <= 0.0:
        return (
            0.0,
            0.0,
            "ZERO_KELLY",
            "Quarter-Kelly fraction is <= 0% (insufficient calibrated edge).",
        )

    bet_frac = min(MAX_SINGLE_BET_PCT, max(MIN_SINGLE_BET_PCT, q_kelly_frac))
    if current_dd >= DRAWDOWN_THROTTLE_PCT:
        bet_frac *= 0.5
        risk_status = "DRAWDOWN_THROTTLED"
    else:
        risk_status = "NORMAL"

    raw_stake = round(current_balance * bet_frac, 2)
    max_exposure = round(current_balance * MAX_IN_PLAY_EXPOSURE_PCT, 2)
    remaining_room = round(max_exposure - in_play, 2)

    if remaining_room < MIN_STAKE_DOLLARS:
        return (
            0.0,
            0.0,
            "EXPOSURE_CAP",
            f"Simultaneous in-play exposure (${in_play:.2f}) leaves ${remaining_room:.2f} below ${max_exposure:.2f} (10% cap).",
        )

    stake = round(min(raw_stake, remaining_room, available_cash), 2)
    if stake < MIN_STAKE_DOLLARS:
        return (
            0.0,
            0.0,
            "MIN_STAKE",
            f"Available/capped stake (${stake:.2f}) is below ${MIN_STAKE_DOLLARS:.2f} minimum.",
        )

    units = round(stake / max(1.0, current_balance * 0.01), 2)  # 1.0U = 1% of current bankroll
    return (
        stake,
        units,
        risk_status,
        f"Quarter-Kelly={q_kelly_frac * 100:.2f}%, Capped={bet_frac * 100:.2f}%, DD={current_dd:.1f}%, Status={risk_status}",
    )


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

    # Check if game_id OR same (matchup, date) is already settled so we never re-bet a finished game
    game_id = candidate["game_id"]
    cand_matchup = f"{candidate['away_team']} @ {candidate['home_team']}"
    cand_date = (candidate.get("commence_time") or datetime.now(timezone.utc).isoformat())[:10]
    for settled in state.get("settled_bets", []):
        if settled.get("game_id") == game_id or (
            settled.get("matchup") == cand_matchup
            and (settled.get("date_placed") or "")[:10] == cand_date
        ):
            print(f"[Bankroll] Skipping {candidate['recommended_side']} ({game_id} already settled).")
            return None

    # Check if an active bet already exists for this game_id or same matchup today
    for idx, active in enumerate(state.get("active_bets", [])):
        if active["game_id"] == game_id or (
            active.get("matchup") == cand_matchup
            and (active.get("date_placed") or "")[:10] == cand_date
        ):
            if active["selection"] == candidate["recommended_side"]:
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
            else:
                print(f"[Bankroll] Active bet already exists for {game_id} on {active['selection']}; skipping opposite side.")
            return active

    # Guard against past-posting games that have already tipped off
    commence_str = candidate.get("commence_time", "")
    if commence_str:
        try:
            tipoff_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > tipoff_dt:
                print(f"[Bankroll] Skipping {candidate['recommended_side']} (tipoff {commence_str} already passed).")
                return None
        except Exception:
            pass

    units = veto_verdict.get("recommended_units", 1)
    if units <= 0 or veto_verdict.get("verdict") != "BET":
        print(f"[Bankroll] No bet placed on {candidate['recommended_side']} (Vetoed or 0 units).")
        return None

    stake, units, risk_status, risk_note = calculate_risk_managed_stake(state, isye)
    if stake <= 0.0:
        print(f"[Bankroll] Risk Gate ({risk_status}) blocked {candidate['recommended_side']}: {risk_note}")
        return None

    current_balance = float(state["bankroll"]["current_balance"])
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
        "quarter_kelly_pct": isye.get("quarter_kelly_pct", 0.0),
        "bet_bankroll_pct": round((stake / current_balance) * 100.0, 2) if current_balance > 0 else 0.0,
        "risk_status": risk_status,
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
    recompute_metrics(state)

    save_bankroll_state(state)
    print(f"[Bankroll] Placed {units}U (${stake:.2f}, {risk_status}) on {new_bet['selection']} ({new_bet['line']:+g}) at {odds}. Cash: ${state['bankroll']['available_cash']}")
    return new_bet


def settle_bet(bet_id, actual_margin, final_score_str, closing_info=None):
    """
    Settles a pending bet given actual game margin (Home Score - Away Score),
    records real Closing Line Value (CLV) if closing_info is provided,
    and triggers the ISyE 4031 post-mortem residual diagnostic.
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

    # Real Closing Line Value (CLV) tracking
    clv_fields = {}
    if closing_info and closing_info.get("home_close") is not None and closing_info.get("away_close") is not None:
        closing_line = float(closing_info["home_close"] if is_home_pick else closing_info["away_close"])
        clv_points = round(float(line) - closing_line, 2)
        beat_clv = True if clv_points > 0 else (False if clv_points < 0 else None)
        clv_fields = {
            "closing_line": closing_line,
            "clv_points": clv_points,
            "beat_clv": beat_clv,
            "closing_provider": closing_info.get("provider", "DraftKings"),
        }

    settled_entry = {
        **bet,
        **clv_fields,
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

    recompute_metrics(state)
    save_bankroll_state(state)
    sign = "+" if pnl >= 0 else "-"
    print(f"[Bankroll] Settled {bet_id} as {result} ({sign}${abs(pnl):.2f}). New balance: ${state['bankroll']['current_balance']:.2f}")

    # Trigger ISyE 4031 Morning Post-Mortem & Self-Learning Rule Update
    try:
        update_decision_basis_post_mortem(settled_entry, actual_margin, final_score_str)
    except Exception as e:
        print(f"[Bankroll] Post-mortem update warning: {e}")

    return True


def recompute_metrics(state):
    """
    Recomputes all bankroll performance metrics directly from settled_bets and equity_history
    so max_drawdown_percent, streaks, average_edge_points, and win_rate are never stale.
    """
    settled_desc = state.get("settled_bets", [])
    settled_chron = list(reversed(settled_desc))

    wins = sum(1 for b in settled_chron if b.get("result") == "WON")
    losses = sum(1 for b in settled_chron if b.get("result") == "LOST")
    pushes = sum(1 for b in settled_chron if b.get("result") == "PUSH")
    decided = wins + losses

    longest_w = 0
    longest_l = 0
    cur_type = ""
    cur_len = 0
    for b in settled_chron:
        res = b.get("result")
        if res == "WON":
            cur_len = (cur_len + 1) if cur_type == "W" else 1
            cur_type = "W"
            longest_w = max(longest_w, cur_len)
        elif res == "LOST":
            cur_len = (cur_len + 1) if cur_type == "L" else 1
            cur_type = "L"
            longest_l = max(longest_l, cur_len)

    # True peak-to-trough max drawdown across equity_history
    start_cap = float(state.get("bankroll", {}).get("starting_capital", 1000.0))
    peak = start_cap
    max_dd_pct = 0.0
    for h in state.get("equity_history", []):
        bal = float(h.get("balance", start_cap))
        if bal > peak:
            peak = bal
        if peak > 0:
            dd = ((bal - peak) / peak) * 100.0  # negative percentage
            if dd < max_dd_pct:
                max_dd_pct = dd

    edges = [float(b["edge_points"]) for b in settled_chron if b.get("edge_points") is not None]
    avg_edge = round(sum(edges) / len(edges), 2) if edges else 0.0

    # Only report CLV if bets actually have recorded closing_line values
    clv_decided = [b for b in settled_chron if b.get("beat_clv") is not None]
    if clv_decided:
        clv_beats = sum(1 for b in clv_decided if b.get("beat_clv") is True)
        clv_rate = round((clv_beats / len(clv_decided)) * 100.0, 1)
    else:
        clv_rate = None

    clv_pts_list = [float(b["clv_points"]) for b in settled_chron if b.get("clv_points") is not None]
    avg_clv_pts = round(sum(clv_pts_list) / len(clv_pts_list), 2) if clv_pts_list else None

    current_bal = float(state.get("bankroll", {}).get("current_balance", 0.0))
    in_play = float(state.get("bankroll", {}).get("in_play_equity", 0.0))

    metrics = state.setdefault("metrics", {})
    metrics["total_bets"] = len(settled_chron)
    metrics["wins"] = wins
    metrics["losses"] = losses
    metrics["pushes"] = pushes
    metrics["win_rate_percent"] = round((wins / decided) * 100.0, 1) if decided > 0 else 0.0
    metrics["current_streak"] = f"{cur_type}{cur_len}" if cur_type else ""
    metrics["longest_win_streak"] = longest_w
    metrics["longest_loss_streak"] = longest_l
    metrics["max_drawdown_percent"] = round(max_dd_pct, 2)
    metrics["current_drawdown_percent"] = compute_current_drawdown_pct(state)
    metrics["in_play_exposure_percent"] = round((in_play / current_bal) * 100.0, 2) if current_bal > 0 else 0.0
    metrics["average_edge_points"] = avg_edge
    metrics["clv_beat_rate_percent"] = clv_rate
    metrics["average_clv_points"] = avg_clv_pts
    return metrics
