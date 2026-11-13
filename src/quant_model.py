"""
CourtVision Quantitative Model
Computes objective expected margins of victory, projected spreads,
and identifies statistically significant value edges (Edge >= 2.5 points).
"""

HOME_COURT_ADVANTAGE = 2.2
EDGE_THRESHOLD = 2.5


def calculate_matchup_projection(game, team_metrics):
    """
    Calculates expected spread and edge for a single matchup.
    """
    home_team = game["home_team"]
    away_team = game["away_team"]

    default_team_metric = {"net_rating": 0.0, "pace": 98.5}
    home_stats = team_metrics.get(home_team, default_team_metric)
    away_stats = team_metrics.get(away_team, default_team_metric)

    # Average game pace
    game_pace = (home_stats.get("pace", 98.5) + away_stats.get("pace", 98.5)) / 2.0

    # Net rating differential
    net_diff = home_stats.get("net_rating", 0.0) - away_stats.get("net_rating", 0.0)

    # Expected Home Margin of Victory: positive means home team wins by X
    expected_home_margin = (net_diff * (game_pace / 100.0)) + HOME_COURT_ADVANTAGE

    # Model projected home spread (e.g. margin of +5.5 means home is -5.5 favorite)
    projected_home_spread = round(-expected_home_margin, 1)
    projected_away_spread = round(-projected_home_spread, 1)

    # Vegas spreads
    vegas_home_spread = game["home_spread"]
    vegas_away_spread = game["away_spread"]

    # Calculate Edge
    # If Vegas has Home at +4.5 and Model has Home at -2.0, Edge for Home is:
    # (+4.5) - (-2.0) = +6.5 points on Home.
    # If Vegas has Home at -7.0 and Model has Home at -2.0, Edge for Away is:
    # (-2.0) - (-7.0) = +5.0 points on Away (+7.0).
    home_edge = round(vegas_home_spread - projected_home_spread, 1)
    away_edge = round(vegas_away_spread - projected_away_spread, 1)

    recommended_side = None
    target_spread = None
    target_odds = None
    max_edge = 0.0

    if home_edge >= EDGE_THRESHOLD:
        recommended_side = home_team
        target_spread = vegas_home_spread
        target_odds = game.get("home_spread_odds", -110)
        max_edge = home_edge
        edge_direction = "HOME"
    elif away_edge >= EDGE_THRESHOLD:
        recommended_side = away_team
        target_spread = vegas_away_spread
        target_odds = game.get("away_spread_odds", -110)
        max_edge = away_edge
        edge_direction = "AWAY"
    else:
        edge_direction = "NONE"
        max_edge = max(abs(home_edge), abs(away_edge))

    return {
        "game_id": game["game_id"],
        "commence_time": game["commence_time"],
        "home_team": home_team,
        "away_team": away_team,
        "sportsbook": game["sportsbook"],
        "vegas_home_spread": vegas_home_spread,
        "vegas_away_spread": vegas_away_spread,
        "projected_home_spread": projected_home_spread,
        "projected_away_spread": projected_away_spread,
        "home_edge": home_edge,
        "away_edge": away_edge,
        "has_edge": max_edge >= EDGE_THRESHOLD,
        "edge_points": max_edge,
        "recommended_side": recommended_side,
        "target_spread": target_spread,
        "target_odds": target_odds,
        "edge_direction": edge_direction
    }


def analyze_slate(games, team_metrics):
    """
    Evaluates an entire slate of games and returns projections and flagged edges.
    """
    projections = []
    flagged_candidates = []

    for game in games:
        proj = calculate_matchup_projection(game, team_metrics)
        projections.append(proj)
        if proj["has_edge"]:
            flagged_candidates.append(proj)

    return projections, flagged_candidates
