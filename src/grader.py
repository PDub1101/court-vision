"""
CourtVision Morning Auto-Grader
Pulls official NBA final scores to grade and settle any open paper bets.
"""

from datetime import datetime, timedelta
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
        matchup = bet["matchup"] # e.g. "Boston Celtics @ New York Knicks"
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
    Fetches yesterday and today's final scores via NBA endpoints or live API.
    """
    scores = {}
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
    except Exception as e:
        print(f"[CourtVision Grader] nba_api live scoreboard fetch note: {e}")

    return scores


if __name__ == "__main__":
    grade_active_bets()
