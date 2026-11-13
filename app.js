/**
 * CourtVision Dashboard Application Logic
 * Renders daily sportsbook lines, $1,000 paper bankroll performance,
 * Gemini context veto reasoning, and 30-day trial progress.
 */

let equityChartInstance = null;

// ============================================================================
// THEME MANAGEMENT (Light Base & Soft Slate Dark Mode)
// ============================================================================
function initTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'slate';
  updateThemeButton(currentTheme);
}

// Support seamless theme synchronization from parent site (pdub1101.github.io)
window.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SET_THEME') {
    const newTheme = event.data.theme;
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeButton(newTheme);
    if (equityChartInstance) {
      updateChartTheme(equityChartInstance, newTheme);
    }
  }
});

function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'slate';
  const newTheme = currentTheme === 'slate' ? 'light' : 'slate';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
  updateThemeButton(newTheme);

  // Re-render chart with appropriate colors
  if (equityChartInstance) {
    updateChartTheme(equityChartInstance, newTheme);
  }
}

function updateThemeButton(theme) {
  const iconEl = document.getElementById('theme-icon');
  const textEl = document.getElementById('theme-text');
  if (theme === 'slate') {
    iconEl.textContent = '☀️';
    textEl.textContent = 'Light';
  } else {
    iconEl.textContent = '🌙';
    textEl.textContent = 'Dark';
  }
}

// ============================================================================
// TAB NAVIGATION
// ============================================================================
function switchTab(tabKey) {
  const tabs = ['today', 'desk', 'ledger'];
  const tabBtns = document.querySelectorAll('.tab-btn');
  
  tabs.forEach((key, index) => {
    const pane = document.getElementById(`pane-${key}`);
    if (pane) {
      if (key === tabKey) {
        pane.classList.add('active');
        if (tabBtns[index]) tabBtns[index].classList.add('active');
      } else {
        pane.classList.remove('active');
        if (tabBtns[index]) tabBtns[index].classList.remove('active');
      }
    }
  });

  if (tabKey === 'desk' && equityChartInstance) {
    equityChartInstance.resize();
  }
}

// ============================================================================
// DATA RENDERING
// ============================================================================
function renderDashboard() {
  const data = window.COURTVISION_DATA;
  if (!data) {
    console.error("[CourtVision] No COURTVISION_DATA bundle found.");
    return;
  }

  const bankrollState = data.bankroll_state || {};
  const bankroll = bankrollState.bankroll || { current_balance: 1000.0, available_cash: 1000.0, in_play_equity: 0.0, total_profit_loss: 0.0, roi_percent: 0.0 };
  const metrics = bankrollState.metrics || { wins: 0, losses: 0, pushes: 0, win_rate_percent: 0.0, current_streak: 'NONE' };
  const activeBets = bankrollState.active_bets || [];
  const settledBets = bankrollState.settled_bets || [];
  const slate = data.todays_slate || [];
  const evaluatedPicks = data.evaluated_picks || [];
  const equityHistory = bankrollState.equity_history || [];

  // 1. Render 30-Day Evaluation Progress
  const uniqueDays = new Set(equityHistory.map(h => h.date)).size || 1;
  const trialDay = Math.min(uniqueDays, 30);
  const progressPct = Math.min(100, Math.max(3.3, (trialDay / 30) * 100));

  document.getElementById('trial-day-display').innerHTML = `Day ${trialDay} <span style="font-size: 16px; color: var(--text-muted); font-weight: 500;">/ 30</span>`;
  document.getElementById('trial-progress-fill').style.width = `${progressPct}%`;
  document.getElementById('trial-sub-text').textContent = trialDay >= 30 ? '30-Day Evaluation Period Completed' : `Tracking live accuracy (${30 - trialDay} days remaining)`;

  // 2. Render Bankroll KPI
  document.getElementById('bankroll-val').textContent = `$${bankroll.current_balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById('bankroll-split').innerHTML = `<span>Cash: $${bankroll.available_cash.toFixed(2)}</span> • <span>In-Play: $${bankroll.in_play_equity.toFixed(2)}</span>`;

  // 3. Render Net Profit / Loss KPI
  const pnl = bankroll.total_profit_loss;
  const pnlValEl = document.getElementById('pnl-val');
  const pnlSign = pnl >= 0 ? '+' : '-';
  pnlValEl.textContent = `${pnlSign}$${Math.abs(pnl).toFixed(2)}`;
  pnlValEl.style.color = pnl >= 0 ? 'var(--pos)' : 'var(--neg)';

  const roiColor = pnl >= 0 ? 'var(--pos)' : 'var(--neg)';
  document.getElementById('roi-sub').innerHTML = `<span style="color: ${roiColor}; font-weight: 700;">${pnl >= 0 ? '+' : ''}${bankroll.roi_percent.toFixed(1)}% ROI</span> vs $1,000 start`;

  // 4. Render ATS Record
  document.getElementById('record-val').textContent = `${metrics.wins} - ${metrics.losses} - ${metrics.pushes}`;
  document.getElementById('winrate-sub').innerHTML = `<span>Win Rate: ${metrics.win_rate_percent.toFixed(1)}%</span> • <span>Streak: ${metrics.current_streak}</span>`;

  // 5. Update Tab Badges
  const edgeCount = slate.filter(g => g.has_edge).length;
  document.getElementById('picks-count-badge').textContent = `${edgeCount} Edge${edgeCount === 1 ? '' : 's'}`;
  document.getElementById('active-bets-badge').textContent = `${activeBets.length} Active`;
  document.getElementById('settled-bets-badge').textContent = `${settledBets.length} Settled`;

  if (data.generated_at) {
    document.getElementById('slate-updated-time').textContent = `Updated: ${data.generated_at}`;
  }

  // 6. Render Tab 1: Game Slate
  renderSlateCards(slate, evaluatedPicks);

  // 7. Render Tab 2: Active Desk & Equity Chart
  renderActiveBetsTable(activeBets);
  renderEquityChart(equityHistory, bankroll.current_balance);

  // 8. Render Tab 3: Settled Ledger
  renderSettledTable(settledBets);
}

// ============================================================================
// SLATE CARDS RENDERING
// ============================================================================
function renderSlateCards(slate, evaluatedPicks) {
  const container = document.getElementById('slate-container');
  container.innerHTML = '';

  if (!slate || slate.length === 0) {
    container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">No games scheduled for today. Check back before afternoon tip-off.</div>';
    return;
  }

  // Create lookup for evaluated picks
  const evalMap = {};
  evaluatedPicks.forEach(p => {
    evalMap[p.game_id] = p;
  });

  slate.forEach(game => {
    const card = document.createElement('div');
    card.className = `game-card ${game.has_edge ? 'has-edge' : ''}`;

    const gameTime = formatGameTime(game.commence_time);
    const evaluation = evalMap[game.game_id];

    let vetoHtml = '';
    if (evaluation) {
      const isApproved = evaluation.gemini_verdict === 'BET';
      const badgeClass = isApproved ? 'approved' : 'vetoed';
      const badgeTitle = isApproved ? `APPROVED (${evaluation.gemini_units}U • ${evaluation.gemini_confidence}/100)` : `VETOED (${evaluation.gemini_confidence}/100)`;
      vetoHtml = `
        <div class="veto-box ${badgeClass}">
          <div style="font-weight: 700; margin-bottom: 3px;">
            ${isApproved ? '✅' : '⚠️'} Gemini Context: ${badgeTitle}
          </div>
          <div>${evaluation.gemini_reasoning}</div>
        </div>
      `;
    }

    const homePicked = game.has_edge && game.edge_direction === 'HOME';
    const awayPicked = game.has_edge && game.edge_direction === 'AWAY';

    card.innerHTML = `
      <div class="game-header">
        <span>${gameTime}</span>
        <span class="bookmaker-badge">${game.sportsbook}</span>
      </div>

      <div class="matchup-row">
        <span class="team-name">${game.away_team}</span>
        <span class="spread-pill ${awayPicked ? 'picked' : ''}">
          ${game.vegas_away_spread > 0 ? '+' : ''}${game.vegas_away_spread}
        </span>
      </div>

      <div class="matchup-row">
        <span class="team-name">${game.home_team}</span>
        <span class="spread-pill ${homePicked ? 'picked' : ''}">
          ${game.vegas_home_spread > 0 ? '+' : ''}${game.vegas_home_spread}
        </span>
      </div>

      <div class="model-comparison-box">
        <div class="comparison-row">
          <span style="color: var(--text-muted);">Model Projected Spread:</span>
          <span style="font-family: 'JetBrains Mono', monospace; font-weight: 600;">
            ${game.home_team} ${game.projected_home_spread > 0 ? '+' : ''}${game.projected_home_spread}
          </span>
        </div>
        <div class="comparison-row">
          <span style="color: var(--text-muted);">Statistical Edge:</span>
          <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: ${game.has_edge ? 'var(--pos)' : 'var(--text-muted)'};">
            ${game.has_edge ? `+${game.edge_points} pts on ${game.recommended_side}` : 'None (< 2.5 pts)'}
          </span>
        </div>
      </div>

      ${vetoHtml}
    `;

    container.appendChild(card);
  });
}

// ============================================================================
// ACTIVE BETS TABLE
// ============================================================================
function renderActiveBetsTable(activeBets) {
  const tbody = document.getElementById('active-bets-tbody');
  tbody.innerHTML = '';

  if (!activeBets || activeBets.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 32px;">
          No active wagers pending tonight. Next automated scan occurs at 4:00 PM EST.
        </td>
      </tr>
    `;
    return;
  }

  activeBets.forEach(b => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="font-weight: 600;">${b.matchup}</td>
      <td>
        <span style="font-weight: 700; color: var(--accent-primary);">${b.selection}</span>
        <span style="font-family: 'JetBrains Mono', monospace; margin-left: 4px;">(${b.line > 0 ? '+' : ''}${b.line})</span>
      </td>
      <td><span class="bookmaker-badge">${b.sportsbook}</span></td>
      <td style="font-family: 'JetBrains Mono', monospace;">${b.odds > 0 ? '+' : ''}${b.odds}</td>
      <td style="font-weight: 700;">$${b.stake.toFixed(2)} (${b.units}U)</td>
      <td style="color: var(--pos); font-weight: 700;">+$${b.potential_profit.toFixed(2)}</td>
      <td>
        <span style="font-family: 'JetBrains Mono', monospace; font-size: 12px;">
          ${b.gemini_confidence}/100
        </span>
      </td>
      <td><span class="status-badge status-pending">IN-PLAY</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// ============================================================================
// SETTLED LEDGER TABLE
// ============================================================================
function renderSettledTable(settledBets) {
  const tbody = document.getElementById('settled-bets-tbody');
  tbody.innerHTML = '';

  if (!settledBets || settledBets.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 32px;">
          No bets settled yet. Morning auto-grader will settle tonight's picks after games complete.
        </td>
      </tr>
    `;
    return;
  }

  settledBets.forEach(b => {
    const tr = document.createElement('tr');
    let badgeClass = 'status-pending';
    if (b.result === 'WON') badgeClass = 'status-won';
    else if (b.result === 'LOST') badgeClass = 'status-lost';
    else if (b.result === 'PUSH') badgeClass = 'status-push';

    const pnlColor = b.net_pnl > 0 ? 'var(--pos)' : (b.net_pnl < 0 ? 'var(--neg)' : 'var(--text-muted)');

    tr.innerHTML = `
      <td style="color: var(--text-muted); font-size: 12.5px;">${b.settled_at ? b.settled_at.split(' ')[0] : 'N/A'}</td>
      <td style="font-weight: 600;">${b.matchup}</td>
      <td>
        <span style="font-weight: 700;">${b.selection}</span>
        <span style="font-family: 'JetBrains Mono', monospace; margin-left: 4px;">(${b.line > 0 ? '+' : ''}${b.line})</span>
      </td>
      <td style="font-family: 'JetBrains Mono', monospace; font-size: 13px;">${b.final_score || 'N/A'}</td>
      <td><span class="status-badge ${badgeClass}">${b.result}</span></td>
      <td>$${b.stake.toFixed(2)}</td>
      <td style="font-weight: 700; color: ${pnlColor}; font-family: 'JetBrains Mono', monospace;">
        ${b.net_pnl >= 0 ? '+' : ''}$${b.net_pnl.toFixed(2)}
      </td>
      <td style="font-family: 'JetBrains Mono', monospace;">--</td>
    `;
    tbody.appendChild(tr);
  });
}

// ============================================================================
// EQUITY CHART (CHART.JS)
// ============================================================================
function renderEquityChart(history, currentBalance) {
  const ctx = document.getElementById('equityChart');
  if (!ctx) return;

  const currentTheme = document.documentElement.getAttribute('data-theme') || 'slate';
  const isDark = currentTheme === 'slate';

  document.getElementById('chart-latest-balance').textContent = `Balance: $${currentBalance.toFixed(2)}`;

  // Default initial point if history is minimal
  let labels = history.map(h => h.date);
  let dataPoints = history.map(h => h.balance);

  if (labels.length === 1) {
    labels = ['Start', labels[0]];
    dataPoints = [1000.0, dataPoints[0]];
  }

  const textColor = isDark ? '#94a3b8' : '#64748b';
  const gridColor = isDark ? 'rgba(51, 62, 84, 0.4)' : 'rgba(226, 232, 240, 0.7)';

  if (equityChartInstance) {
    equityChartInstance.destroy();
  }

  equityChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'CourtVision Bankroll ($)',
          data: dataPoints,
          borderColor: '#3b82f6',
          backgroundColor: isDark ? 'rgba(59, 130, 246, 0.15)' : 'rgba(59, 130, 246, 0.08)',
          fill: true,
          tension: 0.25,
          borderWidth: 2.5,
          pointBackgroundColor: '#3b82f6',
          pointRadius: 4,
          pointHoverRadius: 6
        },
        {
          label: 'Breakeven Baseline ($1,000)',
          data: labels.map(() => 1000.0),
          borderColor: isDark ? 'rgba(148, 163, 184, 0.5)' : 'rgba(100, 116, 139, 0.4)',
          borderDash: [5, 5],
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: textColor,
            font: { family: 'Inter', size: 12 }
          }
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              return ` ${context.dataset.label}: $${context.parsed.y.toFixed(2)}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: 'Inter', size: 11 } }
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { family: 'JetBrains Mono', size: 11 },
            callback: function(value) {
              return '$' + value;
            }
          }
        }
      }
    }
  });
}

function updateChartTheme(chart, theme) {
  const isDark = theme === 'slate';
  const textColor = isDark ? '#94a3b8' : '#64748b';
  const gridColor = isDark ? 'rgba(51, 62, 84, 0.4)' : 'rgba(226, 232, 240, 0.7)';

  chart.options.plugins.legend.labels.color = textColor;
  chart.options.scales.x.grid.color = gridColor;
  chart.options.scales.x.ticks.color = textColor;
  chart.options.scales.y.grid.color = gridColor;
  chart.options.scales.y.ticks.color = textColor;
  chart.update();
}

function formatGameTime(isoString) {
  if (!isoString) return 'Tonight';
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return 'Tonight';
  }
}

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  renderDashboard();
});
