"""
CourtVision Morning Auto-Grader & CLV Capture Engine
Pulls official NBA final scores & closing spreads (via ESPN Public API + nba_api)
to grade and settle open paper bets, record real Closing Line Value (CLV),
and trigger ISyE 4031 post-mortems.
Matches strictly by game_id or (date_utc, normalized_matchup) to prevent
back-to-back series double-grading collisions.
"""

from datetime import datetime, timedelta, timezone
from src.data_fetcher import _build_http_session, normalize_team_name
from src.bankroll_manager import load_bankroll_state, settle_bet


def _candidate_game_dates(bet):
    """
    Returns acceptable UTC date strings (YYYY-MM-DD) for matching a bet's game.
    Checks the bet's date_placed (and +1 day to handle evening EST games rolling past UTC midnight).
    """
    date_placed = (bet.get("date_placed") or "")[:10]
    if not date_placed:
        return []
    try:
        dt = datetime.strptime(date_placed, "%Y-%m-%d").date()
        return [dt.strftime("%Y-%m-%d"), (dt + timedelta(days=1)).strftime("%Y-%m-%d")]
    except ValueError:
        return [date_placed]


def _parse_espn_close_line(line_str):
    """Parses ESPN closing spread strings such as '+1.5', '-3.5', 'EVEN', 'PK'."""
    if line_str is None:
        return None
    s = str(line_str).strip().upper()
    if s in ("EVEN", "PK", "PICK"):
        return 0.0
    try:
        return round(float(s.replace("+", "")), 1)
    except ValueError:
        return None


def fetch_espn_closing_spread(espn_event_id, session=None):
    """
    Fetches the pre-tip closing spread from ESPN's summary pickcenter for a completed game.
    Returns {"home_close": float, "away_close": float, "provider": str} or None.
    """
    if not espn_event_id:
        return None
    session = session or _build_http_session()
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={espn_event_id}"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        pickcenter = resp.json().get("pickcenter", [])
        if not pickcenter:
            return None
        p0 = pickcenter[0]
        ps = p0.get("pointSpread", {})
        home_close = _parse_espn_close_line(ps.get("home", {}).get("close", {}).get("line"))
        away_close = _parse_espn_close_line(ps.get("away", {}).get("close", {}).get("line"))
        if home_close is None or away_close is None:
            return None
        return {
            "home_close": home_close,
            "away_close": away_close,
            "provider": p0.get("provider", {}).get("name", "DraftKings"),
        }
    except Exception as e:
        print(f"[CourtVision Grader] Closing line fetch note (event {espn_event_id}): {e}")
        return None


def grade_active_bets():
    """
    Checks each active bet in the ledger against official final scores and closing lines.
    """
    state = load_bankroll_state()
    active_bets = state.get("active_bets", [])

    if not active_bets:
        print("[CourtVision Grader] No active bets pending settlement.")
        return 0

    print(f"[CourtVision Grader] Found {len(active_bets)} active bets to grade...")

    settled_count = 0
    session = _build_http_session()
    scores_by_id, scores_by_date_matchup = fetch_recent_nba_scores(session=session)

    for bet in list(active_bets):
        matchup = bet.get("matchup", "")
        if " @ " not in matchup:
            continue
        away_raw, home_raw = matchup.split(" @ ", 1)
        away = normalize_team_name(away_raw)
        home = normalize_team_name(home_raw)
        matchup_key = f"{away} @ {home}"

        # 1. Exact game_id match (strongest, zero ambiguity)
        game_result = scores_by_id.get(bet.get("game_id", ""))

        # 2. Date-scoped (date_utc, matchup) match (prevents back-to-back series collision)
        if game_result is None:
            for d_str in _candidate_game_dates(bet):
                candidate_res = scores_by_date_matchup.get((d_str, matchup_key))
                if candidate_res is not None:
                    game_result = candidate_res
                    break

        if game_result is not None:
            if game_result.get("is_final", False):
                home_pts = game_result["home_pts"]
                away_pts = game_result["away_pts"]
                margin = home_pts - away_pts
                score_str = f"{away} {away_pts} - {home} {home_pts}"
                closing_info = fetch_espn_closing_spread(
                    game_result.get("espn_event_id"), session=session
                )

                print(f"[CourtVision Grader] Grading {bet['bet_id']}: Final {score_str} (Margin: {margin})")
                if settle_bet(bet["bet_id"], margin, score_str, closing_info=closing_info):
                    settled_count += 1
            else:
                print(f"[CourtVision Grader] Game {matchup_key} is not final yet.")
        else:
            print(f"[CourtVision Grader] Score for {matchup_key} ({bet.get('date_placed', '')[:10]}) not found yet.")

    return settled_count


def fetch_recent_nba_scores(session=None):
    """
    Fetches recent final scores via ESPN's public scoreboard API (up to 5 days back)
    and nba_api fallback. Returns two dicts:
      - scores_by_id: { "espn_nba_<id>": {...} }
      - scores_by_date_matchup: { ("YYYY-MM-DD", "Away @ Home"): {...} }
    """
    session = session or _build_http_session()
    scores_by_id = {}
    scores_by_date_matchup = {}

    now_utc = datetime.now(timezone.utc)
    dates_to_check = [
        (now_utc - timedelta(days=i)).strftime("%Y%m%d") for i in range(5)
    ]

    for date_str in dates_to_check:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_str}"
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                events = resp.json().get("events", [])
                for ev in events:
                    comp = (ev.get("competitions") or [{}])[0]
                    status_type = comp.get("status", {}).get("type", {})
                    is_final = bool(status_type.get("completed", False))
                    competitors = comp.get("competitors", [])
                    if len(competitors) >= 2:
                        home_c = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                        away_c = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                        home_name = normalize_team_name(home_c.get("team", {}).get("displayName", ""))
                        away_name = normalize_team_name(away_c.get("team", {}).get("displayName", ""))
                        home_pts = int(home_c.get("score", 0) or 0)
                        away_pts = int(away_c.get("score", 0) or 0)

                        ev_date_utc = (ev.get("date") or "")[:10]
                        if not ev_date_utc:
                            ev_date_utc = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

                        ev_id_raw = str(ev.get("id", ""))
                        entry = {
                            "espn_event_id": ev_id_raw,
                            "away_pts": away_pts,
                            "home_pts": home_pts,
                            "is_final": is_final,
                            "game_date_utc": ev_date_utc,
                        }
                        espn_id = f"espn_nba_{ev_id_raw}"
                        scores_by_id[espn_id] = entry
                        scores_by_date_matchup[(ev_date_utc, f"{away_name} @ {home_name}")] = entry
        except Exception as e:
            print(f"[CourtVision Grader] ESPN scoreboard check note ({date_str}): {e}")

    # Supplement with nba_api live scoreboard if available (keyed by today's UTC date)
    try:
        from nba_api.live.nba.endpoints import scoreboard
        board = scoreboard.ScoreBoard(timeout=4)
        games = board.get_dict().get("scoreboard", {}).get("games", [])
        today_utc = now_utc.strftime("%Y-%m-%d")
        for g in games:
            away_team_name = normalize_team_name(g["awayTeam"]["teamCity"] + " " + g["awayTeam"]["teamName"])
            home_team_name = normalize_team_name(g["homeTeam"]["teamCity"] + " " + g["homeTeam"]["teamName"])
            status_text = g.get("gameStatusText", "")
            is_final = "Final" in status_text or g.get("gameStatus", 0) == 3
            game_date_utc = (g.get("gameTimeUTC") or today_utc)[:10]

            key = (game_date_utc, f"{away_team_name} @ {home_team_name}")
            if key not in scores_by_date_matchup:
                scores_by_date_matchup[key] = {
                    "espn_event_id": None,
                    "away_pts": g["awayTeam"].get("score", 0),
                    "home_pts": g["homeTeam"].get("score", 0),
                    "is_final": is_final,
                    "game_date_utc": game_date_utc,
                }
    except Exception:
        pass

    return scores_by_id, scores_by_date_matchup


if __name__ == "__main__":
    grade_active_bets()
