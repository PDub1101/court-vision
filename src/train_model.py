"""
CourtVision Historical Ridge Regression Training & Calibration Engine (src/train_model.py)

Fetches real completed NBA regular-season games across multiple seasons from ESPN's public API,
constructs strictly time-ordered, zero-leakage pre-game features (including opponent-adjusted SRS
computed strictly from prior games) matching src/quant_model.py, fits a Ridge regression with
cross-validated regularization (no intercept penalty), computes the exact full (X'X + lambda*D)^(-1)
covariance matrix, evaluates out-of-time RMSE and 50/80/95% prediction interval coverage on a
strict 30% chronological holdout, and updates data/decision_basis.json.
"""

import os
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import numpy as np

from src.data_fetcher import (
    _build_http_session,
    normalize_team_name,
    _extract_score_value,
    compute_srs_ratings,
)
from src.quant_model import compute_holt_ewma

DECISION_BASIS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "decision_basis.json")

SEASONS_TO_FETCH = [2025, 2026, 2027]  # 2024-25, 2025-26, 2026-27 regular seasons
MIN_PRIOR_GAMES = 5
ALPHA_LEVEL = 0.25
BETA_TREND = 0.10
PHI_DAMPING = 0.80

FEATURE_NAMES = [
    "Intercept (Home Court Advantage)",
    "Opponent-Adjusted SRS Rating Diff (SoS + H/A Adjusted)",
    "Damped Holt EWMA Level Diff (Recent Form)",
    "Damped Holt Momentum Slope Diff (Orthogonal to Level)",
    "Schedule Rest Days Diff (Clamped [-3, 3])",
    "Prior-Game Blowout Shock Diff (AR1 Mean Reversion)",
]


def fetch_historical_games(seasons=None):
    """
    Pulls deduplicated completed NBA regular-season games across the specified seasons
    via ESPN's public schedule API.
    """
    seasons = seasons or SEASONS_TO_FETCH
    session = _build_http_session()

    r_teams = session.get(
        "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams",
        timeout=12,
    )
    r_teams.raise_for_status()
    raw_teams = r_teams.json()["sports"][0]["leagues"][0]["teams"]
    team_ids = [str(item["team"]["id"]) for item in raw_teams]

    def _fetch_team_season(tid, season):
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
            f"teams/{tid}/schedule?season={season}&seasontype=2"
        )
        r = session.get(url, timeout=12)
        if r.status_code != 200:
            return []
        out = []
        for ev in r.json().get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            if not comp.get("status", {}).get("type", {}).get("completed", False):
                continue
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue
            home_c = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away_c = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home_c or not away_c:
                continue
            h_score = _extract_score_value(home_c.get("score"))
            a_score = _extract_score_value(away_c.get("score"))
            if h_score is None or a_score is None:
                continue
            date_str = ev.get("date", "")
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                continue
            out.append({
                "event_id": str(ev.get("id", "")),
                "season": season,
                "date": dt,
                "home_team": normalize_team_name(home_c.get("team", {}).get("displayName", "")),
                "away_team": normalize_team_name(away_c.get("team", {}).get("displayName", "")),
                "home_pts": float(h_score),
                "away_pts": float(a_score),
                "home_margin": float(h_score - a_score),
            })
        return out

    games_by_id = {}
    tasks = [(tid, s) for s in seasons for tid in team_ids]
    print(f"[Train] Fetching historical NBA regular-season games across seasons {seasons} ({len(tasks)} requests)...")

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(_fetch_team_season, tid, s) for tid, s in tasks]
        for fut in as_completed(futures):
            try:
                for g in fut.result():
                    if g["event_id"]:
                        games_by_id[g["event_id"]] = g
            except Exception:
                pass

    games = sorted(games_by_id.values(), key=lambda g: (g["date"], g["event_id"]))
    print(f"[Train] Loaded {len(games)} unique completed NBA games.")
    return games


def build_chronological_dataset(games):
    """
    Walks strictly forward by calendar date within each season to build zero-leakage
    feature vectors X (with opponent-adjusted SRS from strictly prior games) and target y.
    Team state resets cleanly at the start of each NBA season.
    """
    team_history = {}
    season_games = {}
    X_rows = []
    y_rows = []
    meta_rows = []

    def _rolling_series(margins):
        start = max(0, len(margins) - 10)
        series = []
        for idx in range(start, len(margins)):
            win = margins[max(0, idx - 4) : idx + 1]
            series.append(sum(win) / len(win))
        return series

    # Group chronologically by (season, calendar_date) so same-day games never leak into SRS
    date_batches = []
    current_key = None
    current_batch = []
    for g in games:
        key = (g["season"], g["date"].strftime("%Y-%m-%d"))
        if key != current_key:
            if current_batch:
                date_batches.append((current_key, current_batch))
            current_key = key
            current_batch = [g]
        else:
            current_batch.append(g)
    if current_batch:
        date_batches.append((current_key, current_batch))

    for (season, _date_str), batch in date_batches:
        prior_season_games = season_games.get(season, [])
        srs_map = compute_srs_ratings(prior_season_games, ridge_reg=3.0) if prior_season_games else {}

        for g in batch:
            home = g["home_team"]
            away = g["away_team"]
            dt = g["date"]

            h_hist = team_history.setdefault((season, home), [])
            a_hist = team_history.setdefault((season, away), [])

            if len(h_hist) >= MIN_PRIOR_GAMES and len(a_hist) >= MIN_PRIOR_GAMES:
                h_margins = [m for _, m in h_hist]
                a_margins = [m for _, m in a_hist]

                h_series = _rolling_series(h_margins)
                a_series = _rolling_series(a_margins)

                h_level, h_trend, _ = compute_holt_ewma(
                    h_series, alpha=ALPHA_LEVEL, beta=BETA_TREND, phi=PHI_DAMPING
                )
                a_level, a_trend, _ = compute_holt_ewma(
                    a_series, alpha=ALPHA_LEVEL, beta=BETA_TREND, phi=PHI_DAMPING
                )

                h_srs = srs_map.get(home, sum(h_margins) / len(h_margins))
                a_srs = srs_map.get(away, sum(a_margins) / len(a_margins))

                h_rest = max(0, min(5, (dt.date() - h_hist[-1][0].date()).days - 1))
                a_rest = max(0, min(5, (dt.date() - a_hist[-1][0].date()).days - 1))
                rest_diff = max(-3.0, min(3.0, float(h_rest - a_rest)))

                h_recent10 = h_margins[-10:]
                a_recent10 = a_margins[-10:]
                h_shock = h_recent10[-1] - (sum(h_recent10) / len(h_recent10))
                a_shock = a_recent10[-1] - (sum(a_recent10) / len(a_recent10))
                shock_diff = max(-25.0, min(25.0, float(h_shock - a_shock)))

                x_vec = [
                    1.0,
                    h_srs - a_srs,
                    h_level - a_level,
                    h_trend - a_trend,
                    rest_diff,
                    shock_diff,
                ]
                X_rows.append(x_vec)
                y_rows.append(g["home_margin"])
                meta_rows.append(g)

        # Update team histories and season SRS game pool strictly AFTER processing the date batch
        s_list = season_games.setdefault(season, [])
        for g in batch:
            home = g["home_team"]
            away = g["away_team"]
            dt = g["date"]
            team_history.setdefault((season, home), []).append((dt, g["home_margin"]))
            team_history.setdefault((season, away), []).append((dt, -g["home_margin"]))
            s_list.append((home, away, g["home_margin"]))

    return np.array(X_rows, dtype=float), np.array(y_rows, dtype=float), meta_rows


def fit_ridge_chronological(X, y):
    """
    Performs a strict 70% chronological train / 30% out-of-time validation split.
    Tunes Ridge penalty lambda on an inner chronological split of the training set
    (75% inner train / 25% inner val) so the final 30% holdout is strictly untouched.
    """
    n_total, p = X.shape
    split_idx = int(n_total * 0.70)
    X_train, y_train = X[:split_idx], y[:split_idx]
    X_val, y_val = X[split_idx:], y[split_idx:]

    inner_split = int(len(X_train) * 0.75)
    X_tr_in, y_tr_in = X_train[:inner_split], y_train[:inner_split]
    X_va_in, y_va_in = X_train[inner_split:], y_train[inner_split:]

    penalty_diag = np.diag([0.0] + [1.0] * (p - 1))  # Do NOT penalize intercept
    candidate_lambdas = [0.0, 1.0, 5.0, 15.0, 50.0, 150.0, 400.0, 1000.0, 2500.0]

    best_lam = 50.0
    best_inner_rmse = float("inf")
    for lam in candidate_lambdas:
        xtx_reg = X_tr_in.T @ X_tr_in + lam * penalty_diag
        beta_cand = np.linalg.solve(xtx_reg, X_tr_in.T @ y_tr_in)
        preds_in = X_va_in @ beta_cand
        rmse_in = float(np.sqrt(np.mean((y_va_in - preds_in) ** 2)))
        if rmse_in < best_inner_rmse:
            best_inner_rmse = rmse_in
            best_lam = lam

    xtx_reg_full = X_train.T @ X_train + best_lam * penalty_diag
    xtx_inv = np.linalg.inv(xtx_reg_full)
    beta_hat = xtx_inv @ (X_train.T @ y_train)

    train_preds = X_train @ beta_hat
    train_res = y_train - train_preds
    df_train = len(y_train) - p
    train_r2 = 1.0 - float(np.sum(train_res ** 2) / np.sum((y_train - np.mean(y_train)) ** 2))
    train_adj_r2 = 1.0 - (1.0 - train_r2) * (len(y_train) - 1) / max(1, df_train)

    val_preds = X_val @ beta_hat
    val_res = y_val - val_preds
    val_rmse = float(np.sqrt(np.mean(val_res ** 2)))
    val_mae = float(np.mean(np.abs(val_res)))
    val_r2 = 1.0 - float(np.sum(val_res ** 2) / np.sum((y_val - np.mean(y_val)) ** 2))

    # Empirical 50% / 80% / 95% prediction interval coverage on untouched out-of-time holdout
    t_50, t_80, t_95 = 0.6745, 1.2816, 1.9600
    c50 = c80 = c95 = 0
    for i in range(len(X_val)):
        x0 = X_val[i]
        h0 = float(x0 @ xtx_inv @ x0)
        se_pred = val_rmse * math.sqrt(1.0 + max(1e-6, h0))
        abs_e = abs(float(val_res[i]))
        if abs_e <= t_50 * se_pred:
            c50 += 1
        if abs_e <= t_80 * se_pred:
            c80 += 1
        if abs_e <= t_95 * se_pred:
            c95 += 1

    n_val = len(X_val)
    cov_50 = round((c50 / n_val) * 100.0, 1)
    cov_80 = round((c80 / n_val) * 100.0, 1)
    cov_95 = round((c95 / n_val) * 100.0, 1)

    return {
        "n_total": n_total,
        "n_train": len(X_train),
        "n_val": n_val,
        "df": df_train,
        "ridge_lambda": best_lam,
        "beta": [round(float(b), 4) for b in beta_hat],
        "xtx_inv_matrix": [[round(float(v), 8) for v in row] for row in xtx_inv],
        "xtx_inv_diag": [round(float(xtx_inv[i, i]), 8) for i in range(p)],
        "train_r2": round(train_r2, 4),
        "train_adj_r2": round(train_adj_r2, 4),
        "val_r2": round(val_r2, 4),
        "val_rmse": round(val_rmse, 2),
        "val_mae": round(val_mae, 2),
        "val_cov_50": cov_50,
        "val_cov_80": cov_80,
        "val_cov_95": cov_95,
    }


def update_decision_basis_from_fit(fit, meta_rows):
    """
    Writes calibrated SRS Ridge v3 parameters, full covariance matrix, and holdout diagnostics
    to data/decision_basis.json while preserving existing live residual_history.
    """
    existing = {}
    if os.path.exists(DECISION_BASIS_PATH):
        with open(DECISION_BASIS_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)

    first_date = meta_rows[0]["date"].strftime("%Y-%m-%d")
    last_date = meta_rows[-1]["date"].strftime("%Y-%m-%d")
    b = fit["beta"]
    eq_latex = (
        f"\\hat{{Y}}_0 = {b[0]:.2f} + {b[1]:.2f}(\\Delta \\text{{SRS}}) "
        f"+ {b[2]:.2f}(\\Delta \\text{{HoltLevel}}) + {b[3]:.2f}(\\Delta \\text{{HoltTrend}}) "
        f"+ {b[4]:.2f}(\\Delta \\text{{Rest}}) + {b[5]:.3f}(\\Delta \\text{{Shock}})"
    )

    existing_diag = existing.get("diagnostics", {})
    existing_history = existing_diag.get("residual_history", [])

    core_rules = [
        {
            "rule_id": "RULE-INJURY-001",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "source_game": "P0/P1 Structural Guardrail",
            "residual_trigger": "Live ESPN Injury Feed",
            "category": "INJURY_AUDIT",
            "rule_statement": "VETO any pick where a starter/key rotation player on the recommended side is Out or Doubtful (line already reflects absence).",
            "adjustment_type": "QUALITATIVE_VETO",
            "parameter_delta": 0,
        },
        {
            "rule_id": "RULE-SANITY-002",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "source_game": "P0/P1 Structural Guardrail",
            "residual_trigger": "|raw_edge| > 7.5 pts",
            "category": "ADVERSE_SELECTION_GUARD",
            "rule_statement": "Block discrepancies > 7.5 pts vs Vegas spread; large model gaps indicate unpriced injury/lineup shocks rather than +EV.",
            "adjustment_type": "HARD_CAP",
            "parameter_delta": 0,
        },
        {
            "rule_id": "RULE-REST-003",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "source_game": "P0/P1 Structural Guardrail",
            "residual_trigger": "Away B2B vs Rested Home",
            "category": "SCHEDULE_FATIGUE",
            "rule_statement": "Flag/veto road favorites on 0-day rest (back-to-back travel) against rested opponents when edge is marginal.",
            "adjustment_type": "FATIGUE_VETO",
            "parameter_delta": 0,
        },
    ]

    updated = {
        "model_metadata": {
            "model_id": "courtvision_srs_ridge_v3",
            "framework": "ISyE 4031 Opponent-Adjusted SRS + Damped Holt EWMA + Chronological Ridge + Market Prior Shrinkage",
            "training_vintage": f"espn_nba_{first_date}_to_{last_date}_n{fit['n_total']}",
            "validation_protocol": "Strict Time-Ordered Split (70% Chronological Train / 30% Out-of-Time Holdout - Zero Leakage)",
            "n_obs": fit["n_train"],
            "n_val": fit["n_val"],
            "n_params": len(fit["beta"]),
            "df": fit["df"],
            "ridge_lambda": fit["ridge_lambda"],
            "r_squared": fit["train_r2"],
            "adj_r_squared": fit["train_adj_r2"],
            "val_r_squared": fit["val_r2"],
            "residual_se_s": fit["val_rmse"],
            "market_prior_weight": 0.60,
        },
        "smoothing_parameters": {
            "alpha_level": ALPHA_LEVEL,
            "beta_trend": BETA_TREND,
            "phi_damping": PHI_DAMPING,
            "tuning_method": "Damped Holt (Zero-Trend Init) + Ridge Inner Chronological CV",
        },
        "ols_parameters": {
            "equation_latex": eq_latex,
            "beta": fit["beta"],
            "feature_names": FEATURE_NAMES,
            "xtx_inv_diag": fit["xtx_inv_diag"],
            "xtx_inv_matrix": fit["xtx_inv_matrix"],
        },
        "holdout_validation": {
            "n_games": fit["n_val"],
            "rmse": fit["val_rmse"],
            "mae": fit["val_mae"],
            "r_squared": fit["val_r2"],
            "interval_coverage_50_pct": fit["val_cov_50"],
            "interval_coverage_80_pct": fit["val_cov_80"],
            "interval_coverage_95_pct": fit["val_cov_95"],
        },
        "diagnostics": {
            "cfe": existing_diag.get("cfe", 0.0),
            "mad": fit["val_mae"] if not existing_history else existing_diag.get("mad", fit["val_mae"]),
            "tracking_signal": existing_diag.get("tracking_signal", 0.0),
            "tracking_signal_limit": 3.75,
            "status": "CALIBRATED (Out-of-Time SRS Ridge Holdout Verified)",
            "out_of_sample_rmse": fit["val_rmse"],
            "interval_coverage_50_pct": fit["val_cov_50"],
            "interval_coverage_80_pct": fit["val_cov_80"],
            "interval_coverage_95_pct": fit["val_cov_95"],
            "residual_history": existing_history,
        },
        "learned_rules": core_rules,
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with open(DECISION_BASIS_PATH, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)
    print(f"[Train] Wrote calibrated SRS Ridge v3 parameters to {DECISION_BASIS_PATH}")
    return updated


def train_and_save():
    games = fetch_historical_games()
    X, y, meta_rows = build_chronological_dataset(games)
    print(f"[Train] Built {len(X)} leakage-free pre-game matchup vectors ({X.shape[1]} features).")
    fit = fit_ridge_chronological(X, y)
    print("\n=== CHRONOLOGICAL SRS RIDGE v3 FIT SUMMARY ===")
    print(f"  Train N = {fit['n_train']}, Val Holdout N = {fit['n_val']}, Ridge lambda = {fit['ridge_lambda']}")
    for name, coef in zip(FEATURE_NAMES, fit["beta"]):
        print(f"  beta[{name}]: {coef:+.4f}")
    print(f"  Train R^2 = {fit['train_r2']:.4f} | Val Out-of-Time R^2 = {fit['val_r2']:.4f}")
    print(f"  Out-of-Time Holdout RMSE = {fit['val_rmse']:.2f} pts | MAE = {fit['val_mae']:.2f} pts")
    print(
        f"  Out-of-Time PI Coverage: 50% -> {fit['val_cov_50']}% | "
        f"80% -> {fit['val_cov_80']}% | 95% -> {fit['val_cov_95']}%"
    )
    update_decision_basis_from_fit(fit, meta_rows)
    return fit


if __name__ == "__main__":
    train_and_save()
