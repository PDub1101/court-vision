"""
CourtVision Data Fetcher
Retrieves real-time odds from legal US sportsbooks via The Odds API
and advanced team efficiency metrics & chronological game series via nba_api.
"""

import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
PREFERRED_BOOKMAKERS = ["draftkings", "fanduel", "betmgm", "williamhill_us"]


def get_live_nba_odds():
    """
    Pulls today's NBA game odds (spreads, moneylines, totals):
    1. Uses The Odds API if THE_ODDS_API_KEY is configured.
    2. Otherwise automatically pulls live NBA games and DraftKings/ESPN Bet lines
       from ESPN's public NBA Scoreboard API (zero API key required).
    3. Falls back to the baseline sample slate if no games are scheduled today.
    """
    if ODDS_API_KEY:
        url = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "spreads,h2h,totals",
            "oddsFormat": "american",
            "dateFormat": "iso"
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                events = response.json()
                remaining_requests = response.headers.get("x-requests-remaining", "N/A")
                print(f"[CourtVision] Retrieved {len(events)} games via The Odds API. Remaining: {remaining_requests}")
                parsed = parse_odds_response(events)
                if parsed:
                    return parsed
        except Exception as e:
            print(f"[CourtVision] The Odds API request failed: {e}.")

    # Zero-key live feed via ESPN Public NBA Scoreboard API
    espn_games = get_espn_public_nba_slate()
    if espn_games:
        print(f"[CourtVision] Retrieved {len(espn_games)} live NBA games & spreads via ESPN Public API.")
        return espn_games

    print("[CourtVision] Using baseline NBA slate.")
    return get_mock_odds_slate()


def get_espn_public_nba_slate():
    """
    Fetches today's real NBA schedule and sportsbook spreads from ESPN's public JSON API.
    Works 24/7 on GitHub Actions without requiring an API key.
    """
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        events = data.get("events", [])
        parsed = []
        for ev in events:
            comp = (ev.get("competitions") or [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue

            home_comp = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away_comp = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

            home_team = home_comp.get("team", {}).get("displayName", "Home Team")
            away_team = away_comp.get("team", {}).get("displayName", "Away Team")
            commence_time = ev.get("date", "")
            game_id = f"espn_nba_{ev.get('id', '')}"

            odds_list = comp.get("odds", [])
            home_spread = -2.5
            sportsbook = "DraftKings / Consensus"
            over_under = 224.5

            if odds_list:
                odd_obj = odds_list[0]
                sportsbook = odd_obj.get("provider", {}).get("name", "DraftKings")
                over_under = odd_obj.get("overUnder", 224.5)
                details = odd_obj.get("details", "")  # e.g. "BOS -4.5"
                home_abbr = home_comp.get("team", {}).get("abbreviation", "")
                away_abbr = away_comp.get("team", {}).get("abbreviation", "")
                if details and " " in details:
                    parts = details.split()
                    fav_abbr = parts[0].strip()
                    try:
                        line_val = float(parts[-1])
                        if fav_abbr == home_abbr:
                            home_spread = line_val
                        elif fav_abbr == away_abbr:
                            home_spread = -line_val
                    except ValueError:
                        pass

            parsed.append({
                "game_id": game_id,
                "commence_time": commence_time,
                "home_team": home_team,
                "away_team": away_team,
                "sportsbook": sportsbook,
                "home_spread": round(float(home_spread), 1),
                "home_spread_odds": -110,
                "away_spread": round(float(-home_spread), 1),
                "away_spread_odds": -110,
                "home_ml": None,
                "away_ml": None,
                "total": over_under
            })
        return parsed
    except Exception as e:
        print(f"[CourtVision] ESPN public feed note: {e}")
        return []


def parse_odds_response(events):
    """
    Parses and standardizes The Odds API response across sportsbooks.
    """
    parsed_games = []
    for event in events:
        home_team = event.get("home_team")
        away_team = event.get("away_team")
        commence_time = event.get("commence_time")
        game_id = event.get("id")

        bookmakers = event.get("bookmakers", [])
        if not bookmakers:
            continue

        selected_book = None
        for pref in PREFERRED_BOOKMAKERS:
            for b in bookmakers:
                if b.get("key") == pref:
                    selected_book = b
                    break
            if selected_book:
                break
        
        if not selected_book:
            selected_book = bookmakers[0]

        bookmaker_name = selected_book.get("title", selected_book.get("key"))
        spread_data = None
        h2h_data = None
        total_data = None

        for market in selected_book.get("markets", []):
            if market.get("key") == "spreads":
                spread_data = market.get("outcomes", [])
            elif market.get("key") == "h2h":
                h2h_data = market.get("outcomes", [])
            elif market.get("key") == "totals":
                total_data = market.get("outcomes", [])

        home_spread = None
        away_spread = None
        home_spread_odds = -110
        away_spread_odds = -110

        if spread_data:
            for outcome in spread_data:
                if outcome.get("name") == home_team:
                    home_spread = outcome.get("point")
                    home_spread_odds = outcome.get("price", -110)
                elif outcome.get("name") == away_team:
                    away_spread = outcome.get("point")
                    away_spread_odds = outcome.get("price", -110)

        home_ml = None
        away_ml = None
        if h2h_data:
            for outcome in h2h_data:
                if outcome.get("name") == home_team:
                    home_ml = outcome.get("price")
                elif outcome.get("name") == away_team:
                    away_ml = outcome.get("price")

        over_under = None
        if total_data and len(total_data) > 0:
            over_under = total_data[0].get("point")

        if home_spread is not None:
            parsed_games.append({
                "game_id": game_id,
                "commence_time": commence_time,
                "home_team": home_team,
                "away_team": away_team,
                "sportsbook": bookmaker_name,
                "home_spread": home_spread,
                "home_spread_odds": home_spread_odds,
                "away_spread": away_spread,
                "away_spread_odds": away_spread_odds,
                "home_ml": home_ml,
                "away_ml": away_ml,
                "total": over_under
            })

    return parsed_games


def get_team_advanced_metrics():
    """
    Pulls team Net Rating, Offensive Rating, Defensive Rating, eFG%, TOV%, and Pace
    using nba_api or cached chronological baselines for ISyE 4031 EWMA smoothing.
    """
    defaults = get_default_team_metrics()
    try:
        from nba_api.stats.endpoints import leaguedashteamstats
        print("[CourtVision] Fetching rolling NBA metrics from nba_api...")
        stats = leaguedashteamstats.LeagueDashTeamStats(
            measure_type_detailed_defense='Advanced',
            last_n_games=10,
            headers={
                'Host': 'stats.nba.com',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://www.nba.com/'
            },
            timeout=10
        )
        data = stats.get_normalized_dict()
        teams_data = data.get('LeagueDashTeamStats', [])
        
        metrics = {}
        for row in teams_data:
            team_name = row.get("TEAM_NAME")
            base = defaults.get(team_name, {})
            net_rtg = row.get("NET_RATING", base.get("net_rating", 0.0))
            series = base.get("net_rating_series", [net_rtg] * 8)
            series = series[:-1] + [net_rtg]
            metrics[team_name] = {
                "net_rating": net_rtg,
                "net_rating_series": series,
                "off_rating": row.get("OFF_RATING", base.get("off_rating", 114.0)),
                "def_rating": row.get("DEF_RATING", base.get("def_rating", 114.0)),
                "efg_pct": row.get("EFG_PCT", base.get("efg_pct", 0.545)) * 100.0 if row.get("EFG_PCT", 1) <= 1.0 else row.get("EFG_PCT", 54.5),
                "tov_pct": row.get("TM_TOV_PCT", base.get("tov_pct", 0.135)) * 100.0 if row.get("TM_TOV_PCT", 1) <= 1.0 else row.get("TM_TOV_PCT", 13.5),
                "pace": row.get("PACE", base.get("pace", 98.5)),
                "rest_days": base.get("rest_days", 1),
                "last_margin_shock": base.get("last_margin_shock", 0.0)
            }
        if metrics:
            return metrics
    except Exception as e:
        print(f"[CourtVision] nba_api fetch failed or throttled ({e}). Using chronological ISyE 4031 team profiles.")
    
    return defaults


def get_mock_odds_slate():
    """
    Provides a realistic sample slate of games with DraftKings/FanDuel/BetMGM lines.
    """
    return [
        {
            "game_id": "nba_20261112_bos_nyk",
            "commence_time": "2026-11-12T23:30:00Z",
            "home_team": "New York Knicks",
            "away_team": "Boston Celtics",
            "sportsbook": "DraftKings",
            "home_spread": 1.5,
            "home_spread_odds": -110,
            "away_spread": -1.5,
            "away_spread_odds": -110,
            "home_ml": 105,
            "away_ml": -125,
            "total": 224.5
        },
        {
            "game_id": "nba_20261112_den_phx",
            "commence_time": "2026-11-13T01:00:00Z",
            "home_team": "Phoenix Suns",
            "away_team": "Denver Nuggets",
            "sportsbook": "FanDuel",
            "home_spread": 0.5,
            "home_spread_odds": -108,
            "away_spread": -0.5,
            "away_spread_odds": -112,
            "home_ml": 100,
            "away_ml": -118,
            "total": 228.0
        },
        {
            "game_id": "nba_20261112_gsw_lal",
            "commence_time": "2026-11-13T03:00:00Z",
            "home_team": "Los Angeles Lakers",
            "away_team": "Golden State Warriors",
            "sportsbook": "BetMGM",
            "home_spread": 1.0,
            "home_spread_odds": -110,
            "away_spread": -1.0,
            "away_spread_odds": -110,
            "home_ml": 102,
            "away_ml": -122,
            "total": 231.5
        },
        {
            "game_id": "nba_20261112_mil_mia",
            "commence_time": "2026-11-13T00:30:00Z",
            "home_team": "Miami Heat",
            "away_team": "Milwaukee Bucks",
            "sportsbook": "DraftKings",
            "home_spread": 3.0,
            "home_spread_odds": -110,
            "away_spread": -3.0,
            "away_spread_odds": -110,
            "home_ml": 130,
            "away_ml": -155,
            "total": 218.0
        }
    ]


def get_default_team_metrics():
    """
    Chronological 10-game Net Rating series and Four-Factors metrics (CS 2316 + ISyE 4031).
    Series are ordered chronologically from oldest (t-9) to most recent (t).
    """
    return {
        "Boston Celtics": {
            "net_rating": 8.8,
            "net_rating_series": [6.5, 7.2, 8.0, 7.4, 8.9, 9.2, 8.5, 9.6, 10.1, 10.4],
            "off_rating": 121.5,
            "def_rating": 112.7,
            "efg_pct": 57.8,
            "tov_pct": 11.9,
            "pace": 98.2,
            "rest_days": 2,
            "last_margin_shock": 3.5
        },
        "New York Knicks": {
            "net_rating": 2.1,
            "net_rating_series": [3.4, 2.8, 2.5, 1.9, 2.2, 1.8, 1.5, 1.9, 1.4, 1.6],
            "off_rating": 116.4,
            "def_rating": 114.3,
            "efg_pct": 54.2,
            "tov_pct": 13.2,
            "pace": 96.4,
            "rest_days": 1,
            "last_margin_shock": -2.0
        },
        "Denver Nuggets": {
            "net_rating": 4.5,
            "net_rating_series": [3.8, 4.1, 4.6, 5.0, 4.2, 4.8, 5.1, 4.4, 4.7, 3.9],
            "off_rating": 118.0,
            "def_rating": 113.5,
            "efg_pct": 56.1,
            "tov_pct": 12.8,
            "pace": 97.8,
            "rest_days": 0,
            "last_margin_shock": -9.8
        },
        "Phoenix Suns": {
            "net_rating": 1.2,
            "net_rating_series": [0.5, 0.9, 1.4, 1.1, 1.8, 1.0, 1.5, 1.2, 1.4, 1.3],
            "off_rating": 115.8,
            "def_rating": 114.6,
            "efg_pct": 55.0,
            "tov_pct": 14.1,
            "pace": 99.1,
            "rest_days": 1,
            "last_margin_shock": 1.5
        },
        "Golden State Warriors": {
            "net_rating": 5.4,
            "net_rating_series": [3.2, 4.0, 4.5, 5.1, 4.8, 5.6, 6.0, 5.8, 6.4, 6.8],
            "off_rating": 118.4,
            "def_rating": 113.0,
            "efg_pct": 56.9,
            "tov_pct": 13.4,
            "pace": 101.2,
            "rest_days": 2,
            "last_margin_shock": 4.2
        },
        "Los Angeles Lakers": {
            "net_rating": 0.8,
            "net_rating_series": [1.5, 1.2, 0.9, 1.4, 0.6, 0.8, 0.4, 0.9, 0.5, 0.3],
            "off_rating": 114.9,
            "def_rating": 114.1,
            "efg_pct": 54.1,
            "tov_pct": 13.8,
            "pace": 100.5,
            "rest_days": 1,
            "last_margin_shock": -3.1
        },
        "Milwaukee Bucks": {
            "net_rating": 3.8,
            "net_rating_series": [2.9, 3.1, 3.5, 4.0, 3.7, 3.9, 4.2, 3.8, 4.1, 4.0],
            "off_rating": 117.6,
            "def_rating": 113.8,
            "efg_pct": 56.0,
            "tov_pct": 12.9,
            "pace": 99.8,
            "rest_days": 1,
            "last_margin_shock": 1.0
        },
        "Miami Heat": {
            "net_rating": 0.5,
            "net_rating_series": [1.0, 0.8, 0.4, 0.6, 0.2, 0.5, 0.7, 0.3, 0.6, 0.4],
            "off_rating": 113.2,
            "def_rating": 112.7,
            "efg_pct": 53.4,
            "tov_pct": 12.5,
            "pace": 96.8,
            "rest_days": 1,
            "last_margin_shock": -1.2
        },
        "Oklahoma City Thunder": {
            "net_rating": 9.2,
            "net_rating_series": [7.8, 8.2, 8.5, 9.0, 8.8, 9.4, 9.1, 9.6, 9.8, 10.5],
            "off_rating": 119.8,
            "def_rating": 110.6,
            "efg_pct": 57.5,
            "tov_pct": 11.4,
            "pace": 99.6,
            "rest_days": 2,
            "last_margin_shock": 9.4
        },
        "Minnesota Timberwolves": {
            "net_rating": 4.8,
            "net_rating_series": [4.0, 4.2, 4.5, 4.9, 4.6, 5.1, 4.8, 5.0, 5.2, 5.4],
            "off_rating": 115.5,
            "def_rating": 110.7,
            "efg_pct": 55.8,
            "tov_pct": 13.6,
            "pace": 97.4,
            "rest_days": 1,
            "last_margin_shock": 7.0
        },
        "Dallas Mavericks": {
            "net_rating": 3.6,
            "net_rating_series": [3.0, 3.2, 3.5, 3.8, 3.4, 3.7, 3.9, 3.5, 3.8, 3.7],
            "off_rating": 117.8,
            "def_rating": 114.2,
            "efg_pct": 56.2,
            "tov_pct": 12.6,
            "pace": 98.0,
            "rest_days": 1,
            "last_margin_shock": 0.5
        },
        "Philadelphia 76ers": {
            "net_rating": 1.5,
            "net_rating_series": [1.8, 1.6, 1.4, 1.5, 1.2, 1.7, 1.3, 1.5, 1.4, 1.5],
            "off_rating": 114.5,
            "def_rating": 113.0,
            "efg_pct": 53.9,
            "tov_pct": 13.1,
            "pace": 97.5,
            "rest_days": 1,
            "last_margin_shock": -0.8
        }
    }
