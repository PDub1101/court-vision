"""
CourtVision 30-Day Forward Forecast Engine
Simulates forward trajectories for an arbitrary starting capital ($X)
over a 30-day period using Monte Carlo simulations based on model parameters.
"""

import numpy as np


def run_30day_monte_carlo(
    starting_capital=1000.0,
    days=30,
    bets_per_day=2.0,
    win_rate=0.565,
    odds=-110,
    unit_pct=0.02,
    num_simulations=1000
):
    """
    Simulates `num_simulations` paths over `days` using geometric or fixed bankroll staking.
    
    Returns:
    - day_indices: [0, 1, 2, ..., 30]
    - median_curve: 50th percentile balance over time
    - bull_curve: 90th percentile balance over time (favorable variance)
    - bear_curve: 10th percentile balance over time (adverse variance)
    - expected_roi: projected ROI percentage
    """
    total_bets = int(round(days * bets_per_day))
    
    # Net profit multiplier on a win with -110 odds: 100/110 = 0.90909
    if odds < 0:
        win_multiplier = 100.0 / abs(odds)
    else:
        win_multiplier = odds / 100.0

    simulated_final_balances = []
    daily_paths = np.zeros((num_simulations, days + 1))
    daily_paths[:, 0] = starting_capital

    np.random.seed(42)

    for sim in range(num_simulations):
        current_bankroll = starting_capital
        bet_outcomes = np.random.rand(total_bets) < win_rate
        
        # Distribute bets across days
        bets_placed = 0
        for day in range(1, days + 1):
            day_bets = int(bets_per_day) + (1 if (np.random.rand() < (bets_per_day - int(bets_per_day))) else 0)
            for _ in range(day_bets):
                if bets_placed < total_bets:
                    is_win = bet_outcomes[bets_placed]
                    stake = current_bankroll * unit_pct
                    if is_win:
                        current_bankroll += stake * win_multiplier
                    else:
                        current_bankroll -= stake
                    bets_placed += 1
            daily_paths[sim, day] = current_bankroll
        
        simulated_final_balances.append(current_bankroll)

    median_path = np.percentile(daily_paths, 50, axis=0)
    bull_path = np.percentile(daily_paths, 90, axis=0)
    bear_path = np.percentile(daily_paths, 10, axis=0)

    return {
        "starting_capital": starting_capital,
        "days": days,
        "assumed_win_rate": round(win_rate * 100, 1),
        "days_series": list(range(days + 1)),
        "median_curve": [round(val, 2) for val in median_path.tolist()],
        "bull_curve": [round(val, 2) for val in bull_path.tolist()],
        "bear_curve": [round(val, 2) for val in bear_path.tolist()],
        "median_final": round(float(median_path[-1]), 2),
        "bull_final": round(float(bull_path[-1]), 2),
        "bear_final": round(float(bear_path[-1]), 2),
        "median_profit": round(float(median_path[-1] - starting_capital), 2),
        "median_roi_pct": round(float(((median_path[-1] - starting_capital) / starting_capital) * 100.0), 2)
    }
