"""
CourtVision 30-Day Forward Forecast Engine
Simulates forward trajectories for an arbitrary starting capital ($X)
over a 30-day period using Empirical-Bayes shrunk win rates and Monte Carlo
simulations matched to bankroll_manager.py's capped Quarter-Kelly + risk controls.
"""

import numpy as np


def estimate_shrunk_win_rate(wins, losses, prior_win_rate=0.50, prior_strength=100):
    """
    Empirical Bayes Beta-Binomial shrinkage toward a 50% ATS market prior.
    Prevents small-sample hot streaks from projecting unrealistic win rates.
    """
    decided = max(0, int(wins) + int(losses))
    return (float(wins) + float(prior_strength) * float(prior_win_rate)) / (
        float(decided) + float(prior_strength)
    )


def run_30day_monte_carlo(
    starting_capital=1000.0,
    days=30,
    bets_per_day=1.5,
    win_rate=0.5238,
    odds=-110,
    unit_pct=0.0125,
    num_simulations=1000,
    max_exposure_pct=0.10,
    drawdown_throttle_pct=15.0,
    drawdown_halt_pct=25.0,
    raw_win_rate=None,
    sample_size=0,
):
    """
    Simulates `num_simulations` paths over `days` using proportional staking matched
    to CourtVision's risk limits (daily exposure cap + 15% drawdown throttle + 25% halt).
    """
    if odds < 0:
        win_multiplier = 100.0 / abs(odds)
    else:
        win_multiplier = odds / 100.0

    simulated_final_balances = []
    daily_paths = np.zeros((num_simulations, days + 1))
    daily_paths[:, 0] = starting_capital
    dd_15_count = 0

    rng = np.random.default_rng(42)

    for sim in range(num_simulations):
        current_bankroll = float(starting_capital)
        peak_bankroll = float(starting_capital)
        hit_dd_15 = False

        for day in range(1, days + 1):
            dd_pct = (
                ((peak_bankroll - current_bankroll) / peak_bankroll) * 100.0
                if peak_bankroll > 0.0
                else 0.0
            )
            if dd_pct >= drawdown_throttle_pct:
                hit_dd_15 = True

            if dd_pct >= drawdown_halt_pct or current_bankroll <= 0.0:
                daily_paths[sim, day] = current_bankroll
                continue

            eff_pct = (unit_pct * 0.5) if dd_pct >= drawdown_throttle_pct else unit_pct

            base_bets = int(bets_per_day)
            frac_bet = bets_per_day - base_bets
            day_bets = base_bets + (1 if rng.random() < frac_bet else 0)

            # Simultaneous daily slate subject to max_exposure_pct cap
            max_day_stake = current_bankroll * max_exposure_pct
            total_day_stake = 0.0
            day_pnl = 0.0

            for _ in range(day_bets):
                desired_stake = current_bankroll * eff_pct
                remaining_cap = max(0.0, max_day_stake - total_day_stake)
                stake = min(desired_stake, remaining_cap)
                if stake <= 0.0:
                    break
                total_day_stake += stake
                if rng.random() < win_rate:
                    day_pnl += stake * win_multiplier
                else:
                    day_pnl -= stake

            current_bankroll = max(0.0, current_bankroll + day_pnl)
            if current_bankroll > peak_bankroll:
                peak_bankroll = current_bankroll
            daily_paths[sim, day] = current_bankroll

        if hit_dd_15:
            dd_15_count += 1
        simulated_final_balances.append(current_bankroll)

    median_path = np.percentile(daily_paths, 50, axis=0)
    bull_path = np.percentile(daily_paths, 90, axis=0)
    bear_path = np.percentile(daily_paths, 10, axis=0)

    prob_profit = round(
        sum(1 for b in simulated_final_balances if b > starting_capital) / num_simulations * 100.0,
        1,
    )
    prob_dd_15 = round((dd_15_count / num_simulations) * 100.0, 1)

    return {
        "starting_capital": starting_capital,
        "days": days,
        "assumed_win_rate": round(win_rate * 100, 1),
        "empirical_win_rate_pct": round(raw_win_rate * 100, 1) if raw_win_rate is not None else None,
        "sample_size": int(sample_size),
        "staking_model": "capped_quarter_kelly_with_drawdown_guard",
        "days_series": list(range(days + 1)),
        "median_curve": [round(val, 2) for val in median_path.tolist()],
        "bull_curve": [round(val, 2) for val in bull_path.tolist()],
        "bear_curve": [round(val, 2) for val in bear_path.tolist()],
        "median_final": round(float(median_path[-1]), 2),
        "bull_final": round(float(bull_path[-1]), 2),
        "bear_final": round(float(bear_path[-1]), 2),
        "median_profit": round(float(median_path[-1] - starting_capital), 2),
        "median_roi_pct": round(float(((median_path[-1] - starting_capital) / starting_capital) * 100.0), 2),
        "prob_profit_pct": prob_profit,
        "prob_drawdown_15_pct": prob_dd_15,
    }
