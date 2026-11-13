"""
CourtVision ISyE 4031 Quantitative Forecasting & +EV Engine (courtvision_ewma_ols_v1)
Implements:
1. Layer 1: Holt's Trend-Adjusted Exponential Smoothing (EWMA Level + Momentum Trend) & AR(1) Reversion.
2. Layer 2: First-Principles Multivariate OLS Matrix Projection & SE_pred vs SE_mean Contrast.
3. Layer 3: Strict Nested Prediction Intervals (50%, 80%, 95%) with Runtime Nesting Assertion.
4. Layer 4: Student-t Cover Probability, Implied Vig Breakeven, and Mathematical Expected Value (+EV%).
"""

import os
import json
import math

DECISION_BASIS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "decision_basis.json")

EDGE_THRESHOLD = 2.5
MIN_COVER_PROB = 0.555  # 55.5% cover probability threshold (vs 52.38% at -110)

# Student-t critical values for df = 235
T_CRIT_50 = 0.6755
T_CRIT_80 = 1.2852
T_CRIT_95 = 1.9701


def load_decision_basis():
    """
    Loads ISyE 4031 model parameters, OLS coefficients, and learned rules.
    """
    if os.path.exists(DECISION_BASIS_PATH):
        with open(DECISION_BASIS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def compute_holt_ewma(series, alpha=0.25, beta=0.10):
    """
    ISyE 4031 Lecture 17: Holt's Linear Exponential Smoothing.
    L_t = alpha * Y_t + (1 - alpha) * (L_{t-1} + T_{t-1})
    T_t = beta * (L_t - L_{t-1}) + (1 - beta) * T_{t-1}
     Forecast 1-step-ahead: Y_hat_{t+1|t} = L_t + T_t
    """
    if not series or len(series) == 0:
        return 0.0, 0.0, 0.0
    if len(series) == 1:
        val = float(series[0])
        return val, 0.0, val

    level = float(series[0])
    trend = float(series[1] - series[0]) * 0.5

    for y in series[1:]:
        y_val = float(y)
        prev_level = level
        level = alpha * y_val + (1.0 - alpha) * (prev_level + trend)
        trend = beta * (level - prev_level) + (1.0 - beta) * trend

    forecast_next = level + trend
    return round(level, 2), round(trend, 2), round(forecast_next, 2)


def student_t_cdf(t_val, df=235):
    """
    High-precision Student-t Cumulative Distribution Function F_t(t_val; df)
    using Peizer-Pratt / Cornish-Fisher normal transformation on math.erf.
    """
    if df <= 0:
        df = 235
    z = t_val * (1.0 - 1.0 / (4.0 * df)) / math.sqrt(1.0 + (t_val * t_val) / (2.0 * df))
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def compute_implied_breakeven(american_odds):
    """
    Computes sportsbook implied breakeven win probability from American odds.
    e.g., -110 -> 110 / 210 = 0.5238 (52.38%).
    """
    if american_odds < 0:
        return abs(american_odds) / (abs(american_odds) + 100.0)
    else:
        return 100.0 / (american_odds + 100.0)


def compute_decimal_profit_multiplier(american_odds):
    """
    Net profit per $1 risked on a winning wager.
    """
    if american_odds < 0:
        return 100.0 / abs(american_odds)
    else:
        return american_odds / 100.0


def calculate_matchup_projection(game, team_metrics, basis=None):
    """
    Executes the 4-layer ISyE 4031 forecasting model for a single NBA matchup.
    """
    if basis is None:
        basis = load_decision_basis()

    smoothing = basis.get("smoothing_parameters", {})
    alpha = smoothing.get("alpha_level", 0.25)
    beta_param = smoothing.get("beta_trend", 0.10)
    phi1 = smoothing.get("phi1_ar1_reversion", -0.08)

    ols = basis.get("ols_parameters", {})
    betas = ols.get("beta", [2.20, 0.94, 1.35, 0.42, 1.15])
    xtx_inv_diag = ols.get("xtx_inv_diag", [0.0045, 0.00038, 0.0021, 0.00095, 0.0032])
    s_residual = basis.get("model_metadata", {}).get("residual_se_s", 10.42)
    df = basis.get("model_metadata", {}).get("df", 235)

    home_team = game["home_team"]
    away_team = game["away_team"]

    default_metric = {
        "net_rating": 0.0,
        "net_rating_series": [0.0] * 8,
        "efg_pct": 54.5,
        "tov_pct": 13.5,
        "pace": 98.5,
        "rest_days": 1,
        "last_margin_shock": 0.0
    }
    home_stats = team_metrics.get(home_team, default_metric)
    away_stats = team_metrics.get(away_team, default_metric)

    # Layer 1: Holt's Exponential Smoothing on chronological Net Rating series
    home_series = home_stats.get("net_rating_series", [home_stats.get("net_rating", 0.0)] * 8)
    away_series = away_stats.get("net_rating_series", [away_stats.get("net_rating", 0.0)] * 8)

    home_level, home_trend, home_ewma_nrtg = compute_holt_ewma(home_series, alpha=alpha, beta=beta_param)
    away_level, away_trend, away_ewma_nrtg = compute_holt_ewma(away_series, alpha=alpha, beta=beta_param)

    # Game Pace
    game_pace = (home_stats.get("pace", 98.5) + away_stats.get("pace", 98.5)) / 2.0

    # Construct OLS Feature Vector x_0 = [1, x_1, x_2, x_3, x_4]
    x_1_nrtg_diff = (home_ewma_nrtg - away_ewma_nrtg) * (game_pace / 100.0)
    x_2_trend_diff = home_trend - away_trend
    x_3_four_factors_diff = (
        (home_stats.get("efg_pct", 54.5) - away_stats.get("efg_pct", 54.5))
        - 0.8 * (home_stats.get("tov_pct", 13.5) - away_stats.get("tov_pct", 13.5))
    )
    x_4_rest_diff = float(home_stats.get("rest_days", 1) - away_stats.get("rest_days", 1))

    x_vec = [1.0, x_1_nrtg_diff, x_2_trend_diff, x_3_four_factors_diff, x_4_rest_diff]

    # AR(1) Blowout Mean-Reversion Adjustment
    ar1_reversion = phi1 * (home_stats.get("last_margin_shock", 0.0) - away_stats.get("last_margin_shock", 0.0))

    # Layer 2: First-Principles OLS Point Forecast (Expected Home Margin)
    ols_margin = sum(b * x for b, x in zip(betas, x_vec)) + ar1_reversion
    expected_home_margin = round(ols_margin, 2)

    # Compute Leverage h_0 = x_0' (X'X)^(-1) x_0
    h_0 = sum(d * (x * x) for d, x in zip(xtx_inv_diag, x_vec))
    se_mean = round(s_residual * math.sqrt(max(1e-6, h_0)), 2)
    se_pred = round(s_residual * math.sqrt(1.0 + max(1e-6, h_0)), 2)

    # Compute Nested Prediction Intervals (50%, 80%, 95%) for Home Margin
    l50 = round(expected_home_margin - T_CRIT_50 * se_pred, 1)
    u50 = round(expected_home_margin + T_CRIT_50 * se_pred, 1)
    l80 = round(expected_home_margin - T_CRIT_80 * se_pred, 1)
    u80 = round(expected_home_margin + T_CRIT_80 * se_pred, 1)
    l95 = round(expected_home_margin - T_CRIT_95 * se_pred, 1)
    u95 = round(expected_home_margin + T_CRIT_95 * se_pred, 1)

    # ISyE 4031 Homework 4 Strict Nesting Assertion
    assert l95 <= l80 <= l50 <= expected_home_margin <= u50 <= u80 <= u95, (
        f"Prediction interval nesting violated for {away_team} @ {home_team}"
    )

    # Model Projected Spreads (e.g. +4.3 margin means Home -4.3 spread)
    projected_home_spread = round(-expected_home_margin, 1)
    projected_away_spread = round(-projected_home_spread, 1)

    vegas_home_spread = game["home_spread"]
    vegas_away_spread = game["away_spread"]
    home_odds = game.get("home_spread_odds", -110)
    away_odds = game.get("away_spread_odds", -110)

    # Point Discrepancies (Edges)
    home_edge = round(vegas_home_spread - projected_home_spread, 1)
    away_edge = round(vegas_away_spread - projected_away_spread, 1)

    # Layer 3: Student-t Cover Probability & Expected Value (+EV%)
    # Home covers vegas_home_spread if ActualHomeMargin + vegas_home_spread > 0
    t_score_home = (expected_home_margin + vegas_home_spread) / se_pred
    prob_home_cover = student_t_cdf(t_score_home, df=df)
    prob_away_cover = 1.0 - prob_home_cover

    home_breakeven = compute_implied_breakeven(home_odds)
    away_breakeven = compute_implied_breakeven(away_odds)

    home_b = compute_decimal_profit_multiplier(home_odds)
    away_b = compute_decimal_profit_multiplier(away_odds)

    home_ev_pct = (prob_home_cover * home_b - (1.0 - prob_home_cover)) * 100.0
    away_ev_pct = (prob_away_cover * away_b - (1.0 - prob_away_cover)) * 100.0

    # Determine Recommended Side
    recommended_side = None
    target_spread = None
    target_odds = None
    max_edge = max(home_edge, away_edge)
    edge_direction = "NONE"

    if home_edge >= away_edge:
        best_prob = prob_home_cover
        best_breakeven = home_breakeven
        best_ev_pct = home_ev_pct
        best_b = home_b
        if home_edge >= EDGE_THRESHOLD and prob_home_cover >= MIN_COVER_PROB:
            recommended_side = home_team
            target_spread = vegas_home_spread
            target_odds = home_odds
            edge_direction = "HOME"
    else:
        best_prob = prob_away_cover
        best_breakeven = away_breakeven
        best_ev_pct = away_ev_pct
        best_b = away_b
        if away_edge >= EDGE_THRESHOLD and prob_away_cover >= MIN_COVER_PROB:
            recommended_side = away_team
            target_spread = vegas_away_spread
            target_odds = away_odds
            edge_direction = "AWAY"

    has_edge = recommended_side is not None

    # Quarter-Kelly Optimal Bankroll Fraction
    full_kelly = max(0.0, (best_prob * best_b - (1.0 - best_prob)) / best_b)
    quarter_kelly_pct = round(full_kelly * 0.25 * 100.0, 2)

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
        "expected_home_margin": round(expected_home_margin, 1),
        "home_edge": home_edge,
        "away_edge": away_edge,
        "has_edge": has_edge,
        "edge_points": round(max_edge, 1),
        "recommended_side": recommended_side,
        "target_spread": target_spread,
        "target_odds": target_odds,
        "edge_direction": edge_direction,
        "isye_4031": {
            "model_id": "courtvision_ewma_ols_v1",
            "classification": "prospective nowcast",
            "home_ewma_nrtg": home_ewma_nrtg,
            "home_holt_trend": home_trend,
            "away_ewma_nrtg": away_ewma_nrtg,
            "away_holt_trend": away_trend,
            "four_factors_diff": round(x_3_four_factors_diff, 2),
            "rest_diff": x_4_rest_diff,
            "ar1_reversion_adj": round(ar1_reversion, 2),
            "se_pred": se_pred,
            "se_mean": se_mean,
            "pi_50": [l50, u50],
            "pi_80": [l80, u80],
            "pi_95": [l95, u95],
            "cover_prob_pct": round(best_prob * 100.0, 1),
            "breakeven_prob_pct": round(best_breakeven * 100.0, 1),
            "ev_pct": round(best_ev_pct, 2),
            "quarter_kelly_pct": quarter_kelly_pct
        }
    }


def analyze_slate(games, team_metrics):
    """
    Evaluates an entire slate of games using the ISyE 4031 forecasting engine.
    """
    basis = load_decision_basis()
    projections = []
    flagged_candidates = []

    for game in games:
        proj = calculate_matchup_projection(game, team_metrics, basis=basis)
        projections.append(proj)
        if proj["has_edge"]:
            flagged_candidates.append(proj)

    return projections, flagged_candidates
