"""
CourtVision Morning Auto-Grader
Pulls official NBA final scores (via ESPN Public Scoreboard API + nba_api)
to grade and settle any open paper bets and trigger ISyE 4031 post-mortems.
"""

from datetime import datetime, timedelta, timezone
import requests
from src.bankroll_manager import load_bankroll_state, settle_bet


def grade_active_bets():
    """
    Checks each active bet in the ledger against official final scores.
    """
    state = load_bankroll_state()
    active_bets = state.get("active_bets", [])

    if not active_bets:
        print("[CourtVision Grader] No active bets pending settlement.")
        return 0

    print(f"[CourtVision Grader] Found {len(active_bets)} active bets to grade...")

    settled_count = 0
    scores_dict = fetch_recent_nba_scores()

    for bet in list(active_bets):
        matchup = bet["matchup"]  # e.g. "Boston Celtics @ New York Knicks"
        if " @ " not in matchup:
            continue
        away, home = matchup.split(" @ ")

        matchup_key = f"{away.strip()} @ {home.strip()}"
        if matchup_key in scores_dict:
            game_result = scores_dict[matchup_key]
            if game_result.get("is_final", False):
                home_pts = game_result["home_pts"]
                away_pts = game_result["away_pts"]
                margin = home_pts - away_pts
                score_str = f"{away} {away_pts} - {home} {home_pts}"

                print(f"[CourtVision Grader] Grading {bet['bet_id']}: Final {score_str} (Margin: {margin})")
                if settle_bet(bet["bet_id"], margin, score_str):
                    settled_count += 1
            else:
                print(f"[CourtVision Grader] Game {matchup_key} is not final yet.")
        else:
            print(f"[CourtVision Grader] Score for {matchup_key} not found yet.")

    return settled_count


def fetch_recent_nba_scores():
    """
    Fetches yesterday and today's final scores via ESPN's public scoreboard API
    (reliable on GitHub Actions runners with zero key required) and nba_api fallback.
    """
    scores = {}

    # 1. Query ESPN Public Scoreboard for yesterday and today
    now_utc = datetime.now(timezone.utc)
    dates_to_check = [
        (now_utc - timedelta(days=1)).strftime("%Y%m%d"),
        now_utc.strftime("%Y%m%d")
    ]

    for date_str in dates_to_check:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_str}"
            resp = requests.get(url, timeout=10)
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
                        home_name = home_c.get("team", {}).get("displayName", "")
                        away_name = away_c.get("team", {}).get("displayName", "")
                        home_pts = int(home_c.get("score", 0) or 0)
                        away_pts = int(away_c.get("score", 0) or 0)
                        key = f"{away_name} @ {home_name}"
                        scores[key] = {
                            "away_pts": away_pts,
                            "home_pts": home_pts,
                            "is_final": is_final
                        }
        except Exception as e:
            print(f"[CourtVision Grader] ESPN scoreboard check note ({date_str}): {e}")

    # 2. Supplement with nba_api live scoreboard if available
    try:
        from nba_api.live.nba.endpoints import scoreboard
        board = scoreboard.ScoreBoard()
        games = board.get_dict().get("scoreboard", {}).get("games", [])
        for g in games:
            away_team_name = g["awayTeam"]["teamCity"] + " " + g["awayTeam"]["teamName"]
            home_team_name = g["homeTeam"]["teamCity"] + " " + g["homeTeam"]["teamName"]
            status_text = g.get("gameStatusText", "")
            is_final = "Final" in status_text or g.get("gameStatus", 0) == 3

            key = f"{away_team_name} @ {home_team_name}"
            scores[key] = {
                "away_pts": g["awayTeam"].get("score", 0),
                "home_pts": g["homeTeam"].get("score", 0),
                "is_final": is_final
            }
    except Exception:
        pass

    return scores


if __name__ == "__main__":
    grade_active_bets()
