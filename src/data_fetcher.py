"""
CourtVision Data Fetcher
Retrieves real-time odds from legal US sportsbooks via The Odds API
and advanced team efficiency metrics via nba_api.
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
    Pulls today's NBA game odds (spreads, moneylines, totals) from The Odds API.
    Falls back to mock data if no API key is provided or if network fails.
    """
    if not ODDS_API_KEY:
        print("[CourtVision] No THE_ODDS_API_KEY detected. Using realistic live fallback slate.")
        return get_mock_odds_slate()

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
            print(f"[CourtVision] Successfully retrieved {len(events)} games. Requests remaining: {remaining_requests}")
            return parse_odds_response(events)
        else:
            print(f"[CourtVision] The Odds API error ({response.status_code}): {response.text}")
            return get_mock_odds_slate()
    except Exception as e:
        print(f"[CourtVision] Request to The Odds API failed: {e}. Falling back to sample slate.")
        return get_mock_odds_slate()


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

        # Find best available bookmaker in priority order
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

        # Extract spreads
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

        # Extract moneylines
        home_ml = None
        away_ml = None
        if h2h_data:
            for outcome in h2h_data:
                if outcome.get("name") == home_team:
                    home_ml = outcome.get("price")
                elif outcome.get("name") == away_team:
                    away_ml = outcome.get("price")

        # Extract over/under total
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
    Pulls team Net Rating, Offensive Rating, Defensive Rating, and Pace
    using nba_api or cached reference baselines.
    """
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
            metrics[team_name] = {
                "net_rating": row.get("NET_RATING", 0.0),
                "off_rating": row.get("OFF_RATING", 110.0),
                "def_rating": row.get("DEF_RATING", 110.0),
                "pace": row.get("PACE", 98.5)
            }
        if metrics:
            return metrics
    except Exception as e:
        print(f"[CourtVision] nba_api fetch failed or throttled ({e}). Using normalized current power ratings.")
    
    return get_default_team_metrics()


def get_mock_odds_slate():
    """
    Provides a realistic sample slate of games with DraftKings/FanDuel lines.
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
            "home_ml": 110,
            "away_ml": -130,
            "total": 224.5
        },
        {
            "game_id": "nba_20261112_den_phx",
            "commence_time": "2026-11-13T01:00:00Z",
            "home_team": "Phoenix Suns",
            "away_team": "Denver Nuggets",
            "sportsbook": "FanDuel",
            "home_spread": 2.5,
            "home_spread_odds": -108,
            "away_spread": -2.5,
            "away_spread_odds": -112,
            "home_ml": 120,
            "away_ml": -142,
            "total": 228.0
        },
        {
            "game_id": "nba_20261112_gsw_lal",
            "commence_time": "2026-11-13T03:00:00Z",
            "home_team": "Los Angeles Lakers",
            "away_team": "Golden State Warriors",
            "sportsbook": "BetMGM",
            "home_spread": -1.5,
            "home_spread_odds": -110,
            "away_spread": 1.5,
            "away_spread_odds": -110,
            "home_ml": -120,
            "away_ml": 102,
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
    Default normalized team metrics (Net Rating, Pace) for standard fallback.
    """
    return {
        "Boston Celtics": {"net_rating": 8.8, "off_rating": 121.5, "def_rating": 112.7, "pace": 98.2},
        "New York Knicks": {"net_rating": 2.1, "off_rating": 116.4, "def_rating": 114.3, "pace": 96.4},
        "Denver Nuggets": {"net_rating": 4.5, "off_rating": 118.0, "def_rating": 113.5, "pace": 97.8},
        "Phoenix Suns": {"net_rating": 1.2, "off_rating": 115.8, "def_rating": 114.6, "pace": 99.1},
        "Golden State Warriors": {"net_rating": 3.4, "off_rating": 117.2, "def_rating": 113.8, "pace": 101.2},
        "Los Angeles Lakers": {"net_rating": 0.8, "off_rating": 114.9, "def_rating": 114.1, "pace": 100.5},
        "Milwaukee Bucks": {"net_rating": 3.8, "off_rating": 117.6, "def_rating": 113.8, "pace": 99.8},
        "Miami Heat": {"net_rating": 0.5, "off_rating": 113.2, "def_rating": 112.7, "pace": 96.8},
        "Oklahoma City Thunder": {"net_rating": 9.2, "off_rating": 119.8, "def_rating": 110.6, "pace": 99.6},
        "Minnesota Timberwolves": {"net_rating": 4.8, "off_rating": 115.5, "def_rating": 110.7, "pace": 97.4},
        "Dallas Mavericks": {"net_rating": 3.6, "off_rating": 117.8, "def_rating": 114.2, "pace": 98.0},
        "Philadelphia 76ers": {"net_rating": 1.5, "off_rating": 114.5, "def_rating": 113.0, "pace": 97.5}
    }
