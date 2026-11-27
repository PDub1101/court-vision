"""
CourtVision Data Fetcher
Retrieves real-time odds from legal US sportsbooks via The Odds API (or ESPN public fallback),
live 30-team chronological game logs & box-score efficiency metrics via ESPN Public API (+ optional nba_api),
and live NBA injury reports via ESPN Public Injuries API.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
PREFERRED_BOOKMAKERS = ["draftkings", "fanduel", "betmgm", "williamhill_us"]

# Normalize team name discrepancies between The Odds API, nba_api, and ESPN
TEAM_NAME_ALIASES = {
    "Los Angeles Clippers": "LA Clippers",
    "L.A. Clippers": "LA Clippers",
    "L.A. Lakers": "Los Angeles Lakers",
}


def normalize_team_name(name):
    """Standardizes NBA team display names across data providers."""
    if not name:
        return ""
    cleaned = name.strip()
    return TEAM_NAME_ALIASES.get(cleaned, cleaned)


def _build_http_session():
    """Creates a requests Session with automatic retries for transient SSL/network errors."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    return session


def get_live_nba_odds():
    """
    Pulls today's live NBA game odds (spreads, moneylines, totals):
    1. Uses The Odds API if THE_ODDS_API_KEY is configured.
    2. Otherwise pulls live NBA games and sportsbook lines from ESPN's public NBA Scoreboard API.
    3. Never falls back to fabricated mock games (returns [] if no live games/odds are available).
    """
    session = _build_http_session()

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
            response = session.get(url, params=params, timeout=12)
            if response.status_code == 200:
                events = response.json()
                remaining_requests = response.headers.get("x-requests-remaining", "N/A")
                print(f"[CourtVision] Retrieved {len(events)} games via The Odds API. Remaining: {remaining_requests}")
                parsed = parse_odds_response(events)
                if parsed:
                    return parsed
        except Exception as e:
            print(f"[CourtVision] The Odds API request failed: {e}.")

    espn_games = get_espn_public_nba_slate(session=session)
    if espn_games:
        print(f"[CourtVision] Retrieved {len(espn_games)} live NBA games & spreads via ESPN Public API.")
        return espn_games

    print("[CourtVision] No live NBA games with valid spreads found today.")
    return []


def get_espn_public_nba_slate(session=None):
    """
    Fetches today's real NBA schedule and sportsbook spreads from ESPN's public JSON API.
    Skips any game without a valid parseable spread (never substitutes a fake default spread).
    """
    session = session or _build_http_session()
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    try:
        resp = session.get(url, timeout=12)
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

            home_team = normalize_team_name(home_comp.get("team", {}).get("displayName", ""))
            away_team = normalize_team_name(away_comp.get("team", {}).get("displayName", ""))
            commence_time = ev.get("date", "")
            game_id = f"espn_nba_{ev.get('id', '')}"

            odds_list = comp.get("odds", [])
            if not odds_list:
                continue

            odd_obj = odds_list[0]
            sportsbook = odd_obj.get("provider", {}).get("name", "DraftKings")
            over_under = odd_obj.get("overUnder")
            details = (odd_obj.get("details") or "").strip()  # e.g. "BOS -4.5" or "EVEN"
            home_abbr = (home_comp.get("team", {}).get("abbreviation") or "").upper()
            away_abbr = (away_comp.get("team", {}).get("abbreviation") or "").upper()

            home_spread = None
            if details.upper() in ("EVEN", "PK", "PICK"):
                home_spread = 0.0
            elif " " in details:
                parts = details.split()
                fav_abbr = parts[0].strip().upper()
                try:
                    line_val = float(parts[-1])
                    if fav_abbr == home_abbr:
                        home_spread = line_val
                    elif fav_abbr == away_abbr:
                        home_spread = -line_val
                except ValueError:
                    home_spread = None

            # Fallback to numeric spread field if present on odd_obj
            if home_spread is None and odd_obj.get("spread") is not None:
                try:
                    home_spread = float(odd_obj["spread"])
                except (TypeError, ValueError):
                    home_spread = None

            if home_spread is None:
                print(f"[CourtVision] Skipping {away_team} @ {home_team}: unparseable ESPN spread '{details}'.")
                continue

            parsed.append({
                "game_id": game_id,
                "commence_time": commence_time,
                "home_team": home_team,
                "away_team": away_team,
                "sportsbook": sportsbook,
                "home_sportsbook": sportsbook,
                "away_sportsbook": sportsbook,
                "home_spread": round(float(home_spread), 1),
                "consensus_home_spread": round(float(home_spread), 1),
                "home_spread_odds": -110,
                "away_spread": round(float(-home_spread), 1),
                "away_spread_odds": -110,
                "home_ml": None,
                "away_ml": None,
                "total": over_under
            })
        return parsed
    except Exception as e:
        print(f"[CourtVision] ESPN public feed error: {e}")
        return []


def parse_odds_response(events):
    """
    Parses The Odds API response with cross-book line shopping:
    selects the best available spread & vig independently for Home and Away
    across all US sportsbooks, and computes the market consensus median spread.
    """
    parsed_games = []
    for event in events:
        home_team = normalize_team_name(event.get("home_team", ""))
        away_team = normalize_team_name(event.get("away_team", ""))
        commence_time = event.get("commence_time")
        game_id = event.get("id")

        bookmakers = event.get("bookmakers", [])
        if not bookmakers:
            continue

        # Choose preferred bookmaker for ML / Totals metadata
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

        h2h_data = None
        total_data = None
        for market in selected_book.get("markets", []):
            if market.get("key") == "h2h":
                h2h_data = market.get("outcomes", [])
            elif market.get("key") == "totals":
                total_data = market.get("outcomes", [])

        # Cross-book spread shopping across ALL available bookmakers
        home_offers = []
        away_offers = []
        all_home_points = []

        for book in bookmakers:
            b_name = book.get("title", book.get("key", "Book"))
            for market in book.get("markets", []):
                if market.get("key") != "spreads":
                    continue
                b_home_pt = None
                for outcome in market.get("outcomes", []):
                    out_name = normalize_team_name(outcome.get("name", ""))
                    pt = outcome.get("point")
                    price = outcome.get("price", -110)
                    if pt is None:
                        continue
                    if out_name == home_team:
                        home_offers.append((float(pt), int(price), b_name))
                        b_home_pt = float(pt)
                    elif out_name == away_team:
                        away_offers.append((float(pt), int(price), b_name))
                if b_home_pt is not None:
                    all_home_points.append(b_home_pt)

        if not home_offers or not away_offers:
            continue

        best_home_spread, best_home_odds, home_book = max(home_offers, key=lambda x: (x[0], x[1]))
        best_away_spread, best_away_odds, away_book = max(away_offers, key=lambda x: (x[0], x[1]))
        consensus_home_spread = round(float(np.median(all_home_points)), 1) if all_home_points else round(best_home_spread, 1)
        sportsbook_label = home_book if home_book == away_book else f"{home_book} / {away_book}"

        home_ml = None
        away_ml = None
        if h2h_data:
            for outcome in h2h_data:
                out_name = normalize_team_name(outcome.get("name", ""))
                if out_name == home_team:
                    home_ml = outcome.get("price")
                elif out_name == away_team:
                    away_ml = outcome.get("price")

        over_under = None
        if total_data and len(total_data) > 0:
            over_under = total_data[0].get("point")

        parsed_games.append({
            "game_id": game_id,
            "commence_time": commence_time,
            "home_team": home_team,
            "away_team": away_team,
            "sportsbook": sportsbook_label,
            "home_sportsbook": home_book,
            "away_sportsbook": away_book,
            "home_spread": round(best_home_spread, 1),
            "consensus_home_spread": consensus_home_spread,
            "home_spread_odds": best_home_odds,
            "away_spread": round(best_away_spread, 1),
            "away_spread_odds": best_away_odds,
            "home_ml": home_ml,
            "away_ml": away_ml,
            "total": over_under
        })

    return parsed_games


def compute_srs_ratings(games_list, ridge_reg=3.0):
    """
    Computes opponent- and home/road-adjusted Simple Rating System (SRS) ratings
    by solving regularized least squares: (M'M + lambda*D) theta = M'y
    where theta = [r_0, ..., r_{N-1}, hca]. Team ratings are mean-centered to 0.0.
    `games_list` is an iterable of (home_team, away_team, home_margin) tuples.
    """
    if not games_list:
        return {}

    teams = sorted({t for h, a, _ in games_list for t in (h, a)})
    n_teams = len(teams)
    if n_teams < 2:
        return {t: 0.0 for t in teams}

    team_idx = {t: i for i, t in enumerate(teams)}
    n_games = len(games_list)
    M = np.zeros((n_games, n_teams + 1), dtype=float)
    y = np.zeros(n_games, dtype=float)

    for row_i, (home_t, away_t, margin) in enumerate(games_list):
        M[row_i, team_idx[home_t]] = 1.0
        M[row_i, team_idx[away_t]] = -1.0
        M[row_i, n_teams] = 1.0  # Home-court advantage column (unpenalized)
        y[row_i] = float(margin)

    D = np.diag([float(ridge_reg)] * n_teams + [0.0])
    theta = np.linalg.solve(M.T @ M + D, M.T @ y)
    ratings = theta[:n_teams] - np.mean(theta[:n_teams])
    return {t: round(float(ratings[i]), 2) for i, t in enumerate(teams)}


def _extract_score_value(score_field):
    """Extracts numeric score from ESPN's score dict or scalar value."""
    if isinstance(score_field, dict):
        val = score_field.get("value")
        if val is not None:
            return float(val)
        disp = score_field.get("displayValue")
        if disp is not None:
            return float(disp)
    elif score_field is not None:
        return float(score_field)
    return None


def _fetch_single_espn_team_profile(session, team_id, team_name):
    """
    Fetches real chronological game margins, rest days, last-game shock, and box-score
    Four Factors (eFG%, TOV%, Pace) for one NBA team from ESPN's public API.
    """
    # 1. Team season box-score statistics -> eFG%, TOV%, Pace
    efg_pct = None
    tov_pct = None
    pace = None
    off_pts = None

    stats_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/statistics"
    r_stats = session.get(stats_url, timeout=10)
    if r_stats.status_code == 200:
        cats = r_stats.json().get("results", {}).get("stats", {}).get("categories", [])
        stat_map = {}
        for c in cats:
            for st in c.get("stats", []):
                if st.get("value") is not None:
                    stat_map[st["name"]] = float(st["value"])

        fgm = stat_map.get("avgFieldGoalsMade")
        fga = stat_map.get("avgFieldGoalsAttempted")
        tpm = stat_map.get("avgThreePointFieldGoalsMade")
        fta = stat_map.get("avgFreeThrowsAttempted")
        orb = stat_map.get("avgOffensiveRebounds")
        tov = stat_map.get("avgTurnovers")
        off_pts = stat_map.get("avgPoints")

        if fgm is not None and fga and fga > 0 and tpm is not None:
            efg_pct = round(((fgm + 0.5 * tpm) / fga) * 100.0, 2)

        if fga is not None and fta is not None and tov is not None:
            denom = fga + 0.44 * fta + tov
            if denom > 0:
                tov_pct = round((tov / denom) * 100.0, 2)
            if orb is not None:
                # Dean Oliver possession estimate per game
                est_poss = fga - orb + tov + 0.44 * fta
                if 80.0 <= est_poss <= 120.0:
                    pace = round(est_poss, 2)

    if pace is None:
        pace = 98.5

    # 2. Team schedule -> completed chronological games -> real Net Rating series & rest days
    sched_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/schedule"
    r_sched = session.get(sched_url, timeout=10)
    if r_sched.status_code != 200:
        return None, []

    events = r_sched.json().get("events", [])
    completed_games = []
    season_game_records = []
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        if not comp.get("status", {}).get("type", {}).get("completed", False):
            continue
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue

        my_score = None
        opp_score = None
        for c in competitors:
            c_id = str(c.get("team", {}).get("id", ""))
            sc = _extract_score_value(c.get("score"))
            if c_id == str(team_id):
                my_score = sc
            else:
                opp_score = sc

        if my_score is None or opp_score is None:
            continue

        date_str = ev.get("date", "")
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            continue

        home_c = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away_c = next((c for c in competitors if c.get("homeAway") == "away"), None)
        ev_id = str(ev.get("id", ""))
        if home_c and away_c and ev_id:
            h_sc = _extract_score_value(home_c.get("score"))
            a_sc = _extract_score_value(away_c.get("score"))
            if h_sc is not None and a_sc is not None:
                season_game_records.append((
                    ev_id,
                    normalize_team_name(home_c.get("team", {}).get("displayName", "")),
                    normalize_team_name(away_c.get("team", {}).get("displayName", "")),
                    float(h_sc - a_sc),
                ))

        margin = my_score - opp_score
        # Convert raw game margin to per-100-possession Net Rating estimate
        game_nrtg = round(margin * (100.0 / pace), 2)
        completed_games.append((dt, margin, game_nrtg, my_score, opp_score))

    completed_games.sort(key=lambda x: x[0])
    if len(completed_games) < 3:
        return None, season_game_records

    # Build a true chronological rolling 5-game Net Rating series over the last 10 games
    # so Holt's EWMA tracks real team strength trajectory without exploding on single-game noise
    all_nrtgs = [g[2] for g in completed_games]
    rolling_series = []
    start_idx = max(0, len(all_nrtgs) - 10)
    for i in range(start_idx, len(all_nrtgs)):
        win_start = max(0, i - 4)  # 5-game trailing window ending at game i
        window = all_nrtgs[win_start : i + 1]
        rolling_series.append(round(sum(window) / len(window), 2))

    recent = completed_games[-10:]
    nrtg_series = rolling_series
    margins = [g[1] for g in recent]
    avg_nrtg = round(sum(g[2] for g in recent) / len(recent), 2)
    season_nrtg = round(sum(all_nrtgs) / len(all_nrtgs), 2)
    avg_margin = sum(margins) / len(margins)
    last_margin_shock = round(margins[-1] - avg_margin, 2)

    last_game_dt = completed_games[-1][0]
    now_utc = datetime.now(timezone.utc)
    days_since = (now_utc.date() - last_game_dt.date()).days
    rest_days = max(0, min(5, days_since - 1))

    avg_pts_for = sum(g[3] for g in recent) / len(recent)
    avg_pts_against = sum(g[4] for g in recent) / len(recent)
    off_rating = round(avg_pts_for * (100.0 / pace), 2)
    def_rating = round(avg_pts_against * (100.0 / pace), 2)

    profile = {
        "net_rating": avg_nrtg,
        "season_net_rating": season_nrtg,
        "net_rating_series": nrtg_series,
        "off_rating": off_rating,
        "def_rating": def_rating,
        "efg_pct": efg_pct if efg_pct is not None else 54.5,
        "tov_pct": tov_pct if tov_pct is not None else 13.5,
        "pace": pace,
        "rest_days": rest_days,
        "last_game_date": last_game_dt.isoformat(),
        "last_margin_shock": last_margin_shock,
        "games_played": len(completed_games),
        "source": "espn_live",
    }
    return profile, season_game_records


def get_team_advanced_metrics():
    """
    Pulls live chronological 10-game Net Rating series, true rest days, last-game shock,
    opponent-adjusted SRS ratings, and Four-Factors metrics for all 30 NBA teams.
    """
    session = _build_http_session()
    metrics = {}
    unique_games_by_id = {}

    try:
        r_teams = session.get(
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams",
            timeout=12
        )
        if r_teams.status_code == 200:
            raw_teams = r_teams.json()["sports"][0]["leagues"][0]["teams"]
            team_list = [
                (str(item["team"]["id"]), normalize_team_name(item["team"]["displayName"]))
                for item in raw_teams
            ]
            print(f"[CourtVision] Fetching live 30-team schedules & box-score stats from ESPN...")

            with ThreadPoolExecutor(max_workers=10) as pool:
                future_to_team = {
                    pool.submit(_fetch_single_espn_team_profile, session, tid, tname): tname
                    for tid, tname in team_list
                }
                for fut in as_completed(future_to_team):
                    tname = future_to_team[fut]
                    try:
                        profile, team_games = fut.result()
                        if profile:
                            metrics[tname] = profile
                        for ev_id, h_t, a_t, h_m in team_games:
                            unique_games_by_id[ev_id] = (h_t, a_t, h_m)
                    except Exception as e:
                        print(f"[CourtVision] Failed to fetch ESPN profile for {tname}: {e}")

            if unique_games_by_id:
                srs_map = compute_srs_ratings(list(unique_games_by_id.values()), ridge_reg=3.0)
                for tname, prof in metrics.items():
                    prof["srs_rating"] = srs_map.get(tname, 0.0)
                print(
                    f"[CourtVision] Loaded live chronological metrics & opponent-adjusted SRS "
                    f"for {len(metrics)}/30 NBA teams ({len(unique_games_by_id)} unique games)."
                )
            else:
                print(f"[CourtVision] Loaded live chronological metrics for {len(metrics)}/30 NBA teams.")
    except Exception as e:
        print(f"[CourtVision] ESPN 30-team metrics fetch failed: {e}")

    # Optional nba_api enrichment for exact rolling 10-game Pace/eFG%/TOV% (non-blocking)
    if metrics:
        try:
            from nba_api.stats.endpoints import leaguedashteamstats
            stats = leaguedashteamstats.LeagueDashTeamStats(
                measure_type_detailed_defense="Advanced",
                last_n_games=10,
                headers={
                    "Host": "stats.nba.com",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://www.nba.com/"
                },
                timeout=5
            )
            teams_data = stats.get_normalized_dict().get("LeagueDashTeamStats", [])
            enriched = 0
            for row in teams_data:
                tname = normalize_team_name(row.get("TEAM_NAME", ""))
                if tname in metrics:
                    efg_raw = row.get("EFG_PCT")
                    tov_raw = row.get("TM_TOV_PCT")
                    pace_raw = row.get("PACE")
                    if efg_raw is not None:
                        metrics[tname]["efg_pct"] = round(efg_raw * 100.0 if efg_raw <= 1.0 else efg_raw, 2)
                    if tov_raw is not None:
                        metrics[tname]["tov_pct"] = round(tov_raw * 100.0 if tov_raw <= 1.0 else tov_raw, 2)
                    if pace_raw is not None:
                        metrics[tname]["pace"] = round(float(pace_raw), 2)
                    metrics[tname]["source"] = "espn_live+nba_api"
                    enriched += 1
            if enriched:
                print(f"[CourtVision] Enriched {enriched} teams with rolling 10-game nba_api Four Factors.")
        except Exception as e:
            print(f"[CourtVision] nba_api enrichment skipped ({e}). Using ESPN live box-score metrics.")

    return metrics


def get_live_nba_injuries():
    """
    Fetches live NBA injury reports for all teams from ESPN's public Injuries API.
    Returns dict: {normalized_team_name: [{"player": str, "status": str, "comment": str}, ...]}
    """
    session = _build_http_session()
    injuries_by_team = {}
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
    try:
        resp = session.get(url, timeout=12)
        if resp.status_code != 200:
            return injuries_by_team
        data = resp.json()
        for team_entry in data.get("injuries", []):
            team_name = normalize_team_name(team_entry.get("displayName", ""))
            entries = []
            for inj in team_entry.get("injuries", []):
                status = (inj.get("status") or "").strip()
                athlete = (inj.get("athlete") or {}).get("displayName", "Unknown")
                comment = (inj.get("shortComment") or "").strip()
                if status in ("Out", "Doubtful", "Questionable", "Day-To-Day"):
                    entries.append({
                        "player": athlete,
                        "status": status,
                        "comment": comment,
                    })
            if team_name:
                injuries_by_team[team_name] = entries
        total_listed = sum(len(v) for v in injuries_by_team.values())
        print(f"[CourtVision] Loaded live injury report: {total_listed} players across {len(injuries_by_team)} teams.")
    except Exception as e:
        print(f"[CourtVision] Live injury fetch failed: {e}")

    return injuries_by_team


def format_matchup_injury_context(home_team, away_team, injuries_by_team):
    """
    Formats a concise, structured injury briefing for a matchup to pass into the veto engine.
    Also returns counts of confirmed OUT/Doubtful players for each side.
    """
    home_key = normalize_team_name(home_team)
    away_key = normalize_team_name(away_team)
    home_inj = injuries_by_team.get(home_key, [])
    away_inj = injuries_by_team.get(away_key, [])

    def _fmt(team_label, inj_list):
        if not inj_list:
            return f"{team_label}: No listed injuries."
        priority = {"Out": 0, "Doubtful": 1, "Questionable": 2, "Day-To-Day": 3}
        sorted_inj = sorted(inj_list, key=lambda x: priority.get(x["status"], 9))
        lines = [f"- {i['player']} ({i['status']}): {i['comment']}" for i in sorted_inj[:8]]
        return f"{team_label} Injuries ({len(inj_list)} listed):\n" + "\n".join(lines)

    text = _fmt(away_key, away_inj) + "\n" + _fmt(home_key, home_inj)
    home_out = sum(1 for i in home_inj if i["status"] in ("Out", "Doubtful"))
    away_out = sum(1 for i in away_inj if i["status"] in ("Out", "Doubtful"))
    return {
        "text": text,
        "home_out_count": home_out,
        "away_out_count": away_out,
        "home_injuries": home_inj,
        "away_injuries": away_inj,
    }
