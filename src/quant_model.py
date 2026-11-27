"""
CourtVision ISyE 4031 Quantitative Forecasting & +EV Engine (courtvision_srs_ridge_v3)
Implements:
1. Layer 1: Opponent-Adjusted SRS + Damped Holt's Exponential Smoothing (Orthogonal Level & Trend).
2. Layer 2: Chronological Ridge Regression with Full (X'X + lambda*D)^(-1) Leverage & Out-of-Time SE_pred.
3. Layer 3: Strict Nested Prediction Intervals (50%, 80%, 95%) with Runtime Nesting Assertion.
4. Layer 4: Consensus Market-Line Shrinkage, Shopped-Book Push-Aware Student-t P(Cover), and +EV%.
"""

import os
import json
import math
from datetime import datetime, timezone
from src.data_fetcher import normalize_team_name

DECISION_BASIS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "decision_basis.json")

EDGE_THRESHOLD = 3.0
MAX_PLAUSIBLE_EDGE = 7.5  # Guardrail: >7.5 pt gap vs Vegas almost always signals missing injury/lineup info
MIN_COVER_PROB = 0.540    # 54.0% calibrated cover probability after 60% market-line shrinkage (~+3.1% EV at -110)
DEFAULT_MARKET_PRIOR_WEIGHT = 0.60

# Large-df Student-t critical values (calibrated for multi-season NBA sample)
T_CRIT_50 = 0.6745
T_CRIT_80 = 1.2816
T_CRIT_95 = 1.9600


def load_decision_basis():
    """
    Loads ISyE 4031 model parameters, Ridge coefficients, covariance matrix, and rules.
    """
    if os.path.exists(DECISION_BASIS_PATH):
        with open(DECISION_BASIS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def compute_holt_ewma(series, alpha=0.25, beta=0.10, phi=0.80):
    """
    ISyE 4031 Lecture 17: Damped Holt's Linear Exponential Smoothing.
    L_t = alpha * Y_t + (1 - alpha) * (L_{t-1} + phi * T_{t-1})
    T_t = beta * (L_t - L_{t-1}) + (1 - beta) * phi * T_{t-1}
    Forecast 1-step-ahead: Y_hat_{t+1|t} = L_t + phi * T_t
    Initializes trend to 0.0 so early single-game noise cannot explode the slope.
    """
    if not series or len(series) == 0:
        return 0.0, 0.0, 0.0
    if len(series) == 1:
        val = float(series[0])
        return val, 0.0, val

    level = float(series[0])
    trend = 0.0

    for y in series[1:]:
        y_val = float(y)
        prev_level = level
        level = alpha * y_val + (1.0 - alpha) * (prev_level + phi * trend)
        trend = beta * (level - prev_level) + (1.0 - beta) * (phi * trend)

    forecast_next = level + phi * trend
    return round(level, 2), round(trend, 2), round(forecast_next, 2)


def student_t_cdf(t_val, df=1500):
    """
    High-precision Student-t Cumulative Distribution Function F_t(t_val; df)
    using Peizer-Pratt / Cornish-Fisher normal transformation on math.erf.
    """
    if df <= 0:
        df = 1500
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


def _evaluate_side_cover(shrunk_side_margin, side_spread, side_b, se_pred, df):
    """
    Computes push-aware Student-t cover probability, push probability, and EV%
    for a single side given its shrunk expected margin and shopped spread/odds.
    """
    is_integer_spread = abs(side_spread - round(side_spread)) < 1e-6
    if is_integer_spread:
        p_win = student_t_cdf((shrunk_side_margin + side_spread - 0.5) / se_pred, df=df)
        p_loss = 1.0 - student_t_cdf((shrunk_side_margin + side_spread + 0.5) / se_pred, df=df)
        p_push = max(0.0, 1.0 - p_win - p_loss)
        decided = max(1e-6, p_win + p_loss)
        p_cover = p_win / decided
        ev_pct = (p_win * side_b - p_loss) * 100.0
    else:
        p_push = 0.0
        p_cover = student_t_cdf((shrunk_side_margin + side_spread) / se_pred, df=df)
        ev_pct = (p_cover * side_b - (1.0 - p_cover)) * 100.0
    return p_cover, p_push, ev_pct


def calculate_matchup_projection(game, team_metrics, basis=None):
    """
    Executes the 4-layer ISyE 4031 SRS + Damped Holt + Ridge + Market-Shrinkage model.
    """
    if basis is None:
        basis = load_decision_basis()

    smoothing = basis.get("smoothing_parameters", {})
    alpha = smoothing.get("alpha_level", 0.25)
    beta_param = smoothing.get("beta_trend", 0.10)
    phi_damping = smoothing.get("phi_damping", 0.80)

    ols = basis.get("ols_parameters", {})
    betas = ols.get("beta", [1.75, 0.55, 0.18, -0.05, 0.45, 0.03])
    xtx_inv_diag = ols.get("xtx_inv_diag", [0.0008, 0.00004, 0.00005, 0.0005, 0.0004, 0.00001])
    xtx_inv_matrix = ols.get("xtx_inv_matrix")
    s_residual = basis.get("model_metadata", {}).get("residual_se_s", 15.00)
    df = basis.get("model_metadata", {}).get("df", 1500)
    market_prior_w = basis.get("model_metadata", {}).get("market_prior_weight", DEFAULT_MARKET_PRIOR_WEIGHT)

    home_team = normalize_team_name(game["home_team"])
    away_team = normalize_team_name(game["away_team"])

    home_stats = team_metrics.get(home_team)
    away_stats = team_metrics.get(away_team)

    # P0 Guardrail: Never silently substitute dummy 0.0 team metrics
    if (
        not home_stats
        or not away_stats
        or len(home_stats.get("net_rating_series", [])) < 3
        or len(away_stats.get("net_rating_series", [])) < 3
    ):
        missing = []
        if not home_stats or len(home_stats.get("net_rating_series", [])) < 3:
            missing.append(home_team)
        if not away_stats or len(away_stats.get("net_rating_series", [])) < 3:
            missing.append(away_team)
        reason = f"Skipped: missing live chronological metrics for {', '.join(missing)}"
        print(f"[QuantModel] {away_team} @ {home_team} -> {reason}")
        return {
            "game_id": game["game_id"],
            "commence_time": game["commence_time"],
            "home_team": home_team,
            "away_team": away_team,
            "sportsbook": game["sportsbook"],
            "vegas_home_spread": game["home_spread"],
            "vegas_away_spread": game["away_spread"],
            "projected_home_spread": None,
            "projected_away_spread": None,
            "expected_home_margin": None,
            "home_edge": 0.0,
            "away_edge": 0.0,
            "has_edge": False,
            "edge_points": 0.0,
            "recommended_side": None,
            "target_spread": None,
            "target_odds": None,
            "edge_direction": "NONE",
            "data_missing": True,
            "edge_sanity_blocked": False,
            "skip_reason": reason,
            "isye_4031": {}
        }

    # Compute exact rest days relative to tip-off date when last_game_date is available
    def _calc_rest_days(stats_obj, commence_iso):
        last_iso = stats_obj.get("last_game_date")
        if last_iso and commence_iso:
            try:
                tip_dt = datetime.fromisoformat(commence_iso.replace("Z", "+00:00"))
                last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
                return max(0, min(5, (tip_dt.date() - last_dt.date()).days - 1))
            except Exception:
                pass
        return stats_obj.get("rest_days", 1)

    home_rest = _calc_rest_days(home_stats, game.get("commence_time", ""))
    away_rest = _calc_rest_days(away_stats, game.get("commence_time", ""))

    # Layer 1: Damped Holt Exponential Smoothing on real chronological Net Rating series
    home_series = home_stats["net_rating_series"]
    away_series = away_stats["net_rating_series"]

    home_level, home_trend, home_ewma_nrtg = compute_holt_ewma(
        home_series, alpha=alpha, beta=beta_param, phi=phi_damping
    )
    away_level, away_trend, away_ewma_nrtg = compute_holt_ewma(
        away_series, alpha=alpha, beta=beta_param, phi=phi_damping
    )

    game_pace = (home_stats.get("pace", 98.5) + away_stats.get("pace", 98.5)) / 2.0
    pace_scale = game_pace / 100.0

    # Construct 6-feature Ridge vector matching src/train_model.py (all on point-margin scale)
    home_srs = home_stats.get("srs_rating")
    away_srs = away_stats.get("srs_rating")
    if home_srs is not None and away_srs is not None:
        x_1_srs_diff = float(home_srs) - float(away_srs)  # Already in point-margin units
    else:
        home_season = home_stats.get("season_net_rating", home_stats.get("net_rating", 0.0))
        away_season = away_stats.get("season_net_rating", away_stats.get("net_rating", 0.0))
        x_1_srs_diff = (home_season - away_season) * pace_scale

    x_2_level_diff = (home_level - away_level) * pace_scale
    x_3_trend_diff = (home_trend - away_trend) * pace_scale
    x_4_rest_diff = max(-3.0, min(3.0, float(home_rest - away_rest)))
    x_5_shock_diff = max(
        -25.0,
        min(25.0, float(home_stats.get("last_margin_shock", 0.0) - away_stats.get("last_margin_shock", 0.0))),
    )

    x_vec = [1.0, x_1_srs_diff, x_2_level_diff, x_3_trend_diff, x_4_rest_diff, x_5_shock_diff]

    # Four Factors retained strictly for dashboard telemetry (not double-counted in Ridge)
    four_factors_diff = (
        (home_stats.get("efg_pct", 54.5) - away_stats.get("efg_pct", 54.5))
        - 0.8 * (home_stats.get("tov_pct", 13.5) - away_stats.get("tov_pct", 13.5))
    )

    # Layer 2: Chronological Ridge Point Forecast (Expected Home Margin)
    raw_home_margin = sum(b * x for b, x in zip(betas, x_vec))
    expected_home_margin = round(raw_home_margin, 2)
    ar1_reversion = (betas[5] * x_5_shock_diff) if len(betas) > 5 else 0.0

    # Compute Exact Full-Covariance Leverage h_0 = x_0' (X'X + lambda*D)^(-1) x_0
    p = len(x_vec)
    if (
        xtx_inv_matrix
        and len(xtx_inv_matrix) == p
        and all(len(row) == p for row in xtx_inv_matrix)
    ):
        h_0 = sum(
            x_vec[i] * xtx_inv_matrix[i][j] * x_vec[j]
            for i in range(p)
            for j in range(p)
        )
    else:
        h_0 = sum(d * (x * x) for d, x in zip(xtx_inv_diag, x_vec))

    h_0 = max(1e-6, h_0)
    se_mean = round(s_residual * math.sqrt(h_0), 2)
    se_pred = round(s_residual * math.sqrt(1.0 + h_0), 2)

    # Compute Nested Prediction Intervals (50%, 80%, 95%) for Pure Model Home Margin
    l50 = round(expected_home_margin - T_CRIT_50 * se_pred, 1)
    u50 = round(expected_home_margin + T_CRIT_50 * se_pred, 1)
    l80 = round(expected_home_margin - T_CRIT_80 * se_pred, 1)
    u80 = round(expected_home_margin + T_CRIT_80 * se_pred, 1)
    l95 = round(expected_home_margin - T_CRIT_95 * se_pred, 1)
    u95 = round(expected_home_margin + T_CRIT_95 * se_pred, 1)

    # ISyE 4031 Strict Nesting Assertion
    assert l95 <= l80 <= l50 <= expected_home_margin <= u50 <= u80 <= u95, (
        f"Prediction interval nesting violated for {away_team} @ {home_team}"
    )

    # Pure Model Projected Spreads (e.g. +4.3 margin means Home -4.3 spread)
    projected_home_spread = round(-expected_home_margin, 1)
    projected_away_spread = round(-projected_home_spread, 1)

    vegas_home_spread = game["home_spread"]
    vegas_away_spread = game["away_spread"]
    consensus_home_spread = game.get("consensus_home_spread", vegas_home_spread)
    home_odds = game.get("home_spread_odds", -110)
    away_odds = game.get("away_spread_odds", -110)

    # Raw Point Discrepancies (Model vs Best Shopped Line)
    home_edge = round(vegas_home_spread - projected_home_spread, 1)
    away_edge = round(vegas_away_spread - projected_away_spread, 1)

    # Layer 4: Consensus Market-Line Shrinkage + Independent Shopped-Line Cover Probability & +EV%
    vegas_home_margin = -float(consensus_home_spread)
    shrunk_home_margin = round(
        (1.0 - market_prior_w) * expected_home_margin + market_prior_w * vegas_home_margin,
        2,
    )
    shrunk_away_margin = round(-shrunk_home_margin, 2)
    shrunk_edge_home = round(shrunk_home_margin + vegas_home_spread, 2)
    shrunk_edge_away = round(shrunk_away_margin + vegas_away_spread, 2)

    home_breakeven = compute_implied_breakeven(home_odds)
    away_breakeven = compute_implied_breakeven(away_odds)
    home_b = compute_decimal_profit_multiplier(home_odds)
    away_b = compute_decimal_profit_multiplier(away_odds)

    prob_home_cover, home_push_prob, home_ev_pct = _evaluate_side_cover(
        shrunk_home_margin, vegas_home_spread, home_b, se_pred, df
    )
    prob_away_cover, away_push_prob, away_ev_pct = _evaluate_side_cover(
        shrunk_away_margin, vegas_away_spread, away_b, se_pred, df
    )

    # Determine Recommended Side (with P0 edge-sanity cap & P1 calibrated probability/EV gates)
    recommended_side = None
    target_spread = None
    target_odds = None
    max_edge = max(home_edge, away_edge)
    edge_direction = "NONE"
    edge_sanity_blocked = False
    skip_reason = None
    selected_book = game["sportsbook"]

    if home_edge >= away_edge:
        best_prob = prob_home_cover
        best_push_prob = home_push_prob
        best_breakeven = home_breakeven
        best_ev_pct = home_ev_pct
        best_b = home_b
        shrunk_edge_points = shrunk_edge_home
        if home_edge > MAX_PLAUSIBLE_EDGE:
            edge_sanity_blocked = True
            skip_reason = (
                f"Sanity Cap Blocked: {home_team} edge (+{home_edge} pts) exceeds "
                f"{MAX_PLAUSIBLE_EDGE} pt cap (likely unpriced injury/lineup shock)."
            )
            print(f"[QuantModel] {skip_reason}")
        elif home_edge >= EDGE_THRESHOLD and prob_home_cover >= MIN_COVER_PROB and home_ev_pct > 0.0:
            recommended_side = home_team
            target_spread = vegas_home_spread
            target_odds = home_odds
            edge_direction = "HOME"
            selected_book = game.get("home_sportsbook", game["sportsbook"])
    else:
        best_prob = prob_away_cover
        best_push_prob = away_push_prob
        best_breakeven = away_breakeven
        best_ev_pct = away_ev_pct
        best_b = away_b
        shrunk_edge_points = shrunk_edge_away
        if away_edge > MAX_PLAUSIBLE_EDGE:
            edge_sanity_blocked = True
            skip_reason = (
                f"Sanity Cap Blocked: {away_team} edge (+{away_edge} pts) exceeds "
                f"{MAX_PLAUSIBLE_EDGE} pt cap (likely unpriced injury/lineup shock)."
            )
            print(f"[QuantModel] {skip_reason}")
        elif away_edge >= EDGE_THRESHOLD and prob_away_cover >= MIN_COVER_PROB and away_ev_pct > 0.0:
            recommended_side = away_team
            target_spread = vegas_away_spread
            target_odds = away_odds
            edge_direction = "AWAY"
            selected_book = game.get("away_sportsbook", game["sportsbook"])

    has_edge = recommended_side is not None

    # Quarter-Kelly Optimal Bankroll Fraction (push-aware via calibrated EV)
    full_kelly = max(0.0, (best_ev_pct / 100.0) / best_b)
    quarter_kelly_pct = round(full_kelly * 0.25 * 100.0, 2)

    return {
        "game_id": game["game_id"],
        "commence_time": game["commence_time"],
        "home_team": home_team,
        "away_team": away_team,
        "sportsbook": selected_book,
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
        "data_missing": False,
        "edge_sanity_blocked": edge_sanity_blocked,
        "skip_reason": skip_reason,
        "isye_4031": {
            "model_id": "courtvision_srs_ridge_v3",
            "classification": "prospective nowcast",
            "home_srs": home_srs,
            "away_srs": away_srs,
            "consensus_home_spread": consensus_home_spread,
            "home_ewma_nrtg": home_ewma_nrtg,
            "home_holt_trend": home_trend,
            "away_ewma_nrtg": away_ewma_nrtg,
            "away_holt_trend": away_trend,
            "four_factors_diff": round(four_factors_diff, 2),
            "rest_diff": x_4_rest_diff,
            "ar1_reversion_adj": round(ar1_reversion, 2),
            "shrunk_home_margin": shrunk_home_margin,
            "shrunk_edge_points": shrunk_edge_points,
            "market_prior_weight": market_prior_w,
            "push_prob_pct": round(best_push_prob * 100.0, 1),
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
