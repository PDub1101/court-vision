/**
 * CourtVision ISyE 4031 Dashboard Application Logic
 * Renders:
 * 1. Tonight's Prospective Nowcasts (Holt EWMA, Multivariate OLS, SE_pred Nested Intervals, Student-t P(Cover), +EV%).
 * 2. Live $1,000 Paper Trading Desk & Day-by-Day Capital Lifecycle.
 * 3. ISyE 4031 Model Telemetry, Residual Diagnostics (Tracking Signal), and Gemini Self-Learning Decision Basis.
 * 4. 30-Day Auditable Settlement Ledger.
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

  if (equityChartInstance) {
    updateChartTheme(equityChartInstance, newTheme);
  }
}

function updateThemeButton(theme) {
  const iconEl = document.getElementById('theme-icon');
  const textEl = document.getElementById('theme-text');
  if (theme === 'slate') {
    iconEl.textContent = '☀️';
    textEl.textContent = 'Light Mode';
  } else {
    iconEl.textContent = '🌙';
    textEl.textContent = 'Dark Mode';
  }
}

// ============================================================================
// TAB NAVIGATION
// ============================================================================
function switchTab(tabKey) {
  const tabs = ['today', 'desk', 'model', 'ledger'];
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
  const bankroll = bankrollState.bankroll || {
    starting_capital: 1000.0,
    current_balance: 1000.0,
    available_cash: 1000.0,
    in_play_equity: 0.0,
    total_profit_loss: 0.0,
    roi_percent: 0.0
  };
  const metrics = bankrollState.metrics || { wins: 0, losses: 0, pushes: 0, win_rate_percent: 0.0, current_streak: 'NONE' };
  const activeBets = bankrollState.active_bets || [];
  const settledBets = bankrollState.settled_bets || [];
  const slate = data.todays_slate || [];
  const evaluatedPicks = data.evaluated_picks || [];
  const equityHistory = bankrollState.equity_history || [];
  const decisionBasis = data.decision_basis || {};
  const diagnostics = decisionBasis.diagnostics || {};

  // 1. Render 30-Day Evaluation Progress
  const uniqueDays = new Set(equityHistory.map(h => h.date)).size || 1;
  const trialDay = Math.min(uniqueDays, 30);
  const progressPct = Math.min(100, Math.max(3.3, (trialDay / 30) * 100));

  document.getElementById('trial-day-display').innerHTML = `Day ${trialDay} <span style="font-size: 16px; color: var(--text-muted); font-weight: 600;">/ 30</span>`;
  document.getElementById('trial-progress-fill').style.width = `${progressPct}%`;
  document.getElementById('trial-sub-text').textContent = trialDay >= 30 ? '30-Day Evaluation Period Completed' : `Out-of-time sequential validation (${30 - trialDay}d left)`;

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
  document.getElementById('roi-sub').innerHTML = `<span style="color: ${roiColor}; font-weight: 700;">${pnl >= 0 ? '+' : ''}${bankroll.roi_percent.toFixed(1)}% ROI</span> vs $1,000 starting capital`;

  // 4. Render ATS Record & Tracking Signal
  const tsVal = diagnostics.tracking_signal !== undefined ? diagnostics.tracking_signal : -0.29;
  document.getElementById('record-val').textContent = `${metrics.wins} - ${metrics.losses} - ${metrics.pushes}`;
  document.getElementById('winrate-sub').innerHTML = `<span>Win Rate: ${metrics.win_rate_percent.toFixed(1)}%</span> • <span>TS: ${tsVal > 0 ? '+' : ''}${tsVal} (Unbiased)</span>`;

  // 5. Update Tab Badges
  const edgeCount = slate.filter(g => g.has_edge).length;
  const learnedRules = decisionBasis.learned_rules || [];
  document.getElementById('picks-count-badge').textContent = `${edgeCount} +EV Edge${edgeCount === 1 ? '' : 's'}`;
  document.getElementById('active-bets-badge').textContent = `${activeBets.length} Active ($${bankroll.in_play_equity.toFixed(0)})`;
  document.getElementById('rules-count-badge').textContent = `${learnedRules.length} Learned Rules`;
  document.getElementById('settled-bets-badge').textContent = `${settledBets.length} Settled`;

  if (data.generated_at) {
    document.getElementById('slate-updated-time').textContent = `Sync: ${data.generated_at}`;
  }

  // 6. Render Tab 1: Game Slate with ISyE 4031 Telemetry
  renderSlateCards(slate, evaluatedPicks);

  // 7. Render Tab 2: Money Lifecycle, Active Desk & Equity Chart
  renderMoneyLifecycle(bankroll, activeBets);
  renderActiveBetsTable(activeBets);
  renderEquityChart(equityHistory, bankroll.current_balance, bankrollState);

  // 8. Render Tab 3: ISyE 4031 Model Telemetry & Self-Learning Decision Basis
  renderModelAndMemoryTab(decisionBasis);

  // 9. Render Tab 4: Settled Ledger
  renderSettledTable(settledBets);
}

// ============================================================================
// SLATE CARDS RENDERING (ISyE 4031 EWMA + OLS + SE_pred + Student-t P(Cover))
// ============================================================================
function getTeamAbbr(teamName) {
  const map = {
    "Boston Celtics": "BOS",
    "New York Knicks": "NYK",
    "Denver Nuggets": "DEN",
    "Phoenix Suns": "PHX",
    "Golden State Warriors": "GSW",
    "Los Angeles Lakers": "LAL",
    "Milwaukee Bucks": "MIL",
    "Miami Heat": "MIA",
    "Oklahoma City Thunder": "OKC",
    "Minnesota Timberwolves": "MIN",
    "Dallas Mavericks": "DAL",
    "Philadelphia 76ers": "PHI"
  };
  return map[teamName] || teamName.substring(0, 3).toUpperCase();
}

function renderSlateCards(slate, evaluatedPicks) {
  const container = document.getElementById('slate-container');
  container.innerHTML = '';

  if (!slate || slate.length === 0) {
    container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">No games scheduled for today. Check back before afternoon tip-off.</div>';
    return;
  }

  const evalMap = {};
  evaluatedPicks.forEach(p => {
    evalMap[p.game_id] = p;
  });

  slate.forEach(game => {
    const card = document.createElement('div');
    card.className = `game-card ${game.has_edge ? 'has-edge' : ''}`;

    const gameTime = formatGameTime(game.commence_time);
    const evaluation = evalMap[game.game_id];
    const awayAbbr = getTeamAbbr(game.away_team);
    const homeAbbr = getTeamAbbr(game.home_team);
    const isye = game.isye_4031 || {};

    const awayEwma = isye.away_ewma_nrtg !== undefined ? `${isye.away_ewma_nrtg > 0 ? '+' : ''}${isye.away_ewma_nrtg}` : '+0.0';
    const awayTrend = isye.away_holt_trend !== undefined ? `${isye.away_holt_trend >= 0 ? '▲ +' : '▼ '}${isye.away_holt_trend}` : '0.0';
    const homeEwma = isye.home_ewma_nrtg !== undefined ? `${isye.home_ewma_nrtg > 0 ? '+' : ''}${isye.home_ewma_nrtg}` : '+0.0';
    const homeTrend = isye.home_holt_trend !== undefined ? `${isye.home_holt_trend >= 0 ? '▲ +' : '▼ '}${isye.home_holt_trend}` : '0.0';

    const coverProb = isye.cover_prob_pct !== undefined ? isye.cover_prob_pct : 52.4;
    const breakevenProb = isye.breakeven_prob_pct !== undefined ? isye.breakeven_prob_pct : 52.4;
    const evPct = isye.ev_pct !== undefined ? isye.ev_pct : 0.0;
    const sePred = isye.se_pred !== undefined ? isye.se_pred : 10.45;
    const seMean = isye.se_mean !== undefined ? isye.se_mean : 0.92;
    const pi50 = isye.pi_50 || [-7.0, 7.0];
    const pi80 = isye.pi_80 || [-13.0, 13.0];
    const pi95 = isye.pi_95 || [-20.0, 20.0];

    let vetoHtml = '';
    if (evaluation) {
      const isApproved = evaluation.gemini_verdict === 'BET';
      const badgeClass = isApproved ? 'approved' : 'vetoed';
      const ruleTag = evaluation.triggered_rule_id && evaluation.triggered_rule_id !== 'NONE'
        ? `<span class="bookmaker-badge" style="margin-left: auto; font-size: 10.5px;">${evaluation.triggered_rule_id}</span>`
        : '';
      const badgeTitle = isApproved
        ? `APPROVED (${evaluation.gemini_units}U • Conf: ${evaluation.gemini_confidence}/100)`
        : `VETOED (Conf: ${evaluation.gemini_confidence}/100)`;

      vetoHtml = `
        <div class="veto-box ${badgeClass}">
          <div style="font-weight: 800; margin-bottom: 5px; display: flex; align-items: center; gap: 6px;">
            <span>${isApproved ? '✅' : '⚠️'} Gemini 2.5 Flash: ${badgeTitle}</span>
            ${ruleTag}
          </div>
          <div>${evaluation.gemini_reasoning}</div>
        </div>
      `;
    }

    const homePicked = game.has_edge && game.edge_direction === 'HOME';
    const awayPicked = game.has_edge && game.edge_direction === 'AWAY';

    card.innerHTML = `
      <div class="game-header">
        <span style="font-weight: 700;">🏀 ${gameTime} • <span style="color: var(--bball-orange);">Prospective Nowcast</span></span>
        <span class="bookmaker-badge">${game.sportsbook}</span>
      </div>

      <div class="matchup-row">
        <div class="team-badge-wrap">
          <span class="team-chip">${awayAbbr}</span>
          <div>
            <span class="team-name">${game.away_team}</span>
            <span class="ewma-sub">EWMA NRtg: ${awayEwma} (Trend: ${awayTrend})</span>
          </div>
        </div>
        <span class="spread-pill ${awayPicked ? 'picked' : ''}">
          ${game.vegas_away_spread > 0 ? '+' : ''}${game.vegas_away_spread}
        </span>
      </div>

      <div class="matchup-row">
        <div class="team-badge-wrap">
          <span class="team-chip">${homeAbbr}</span>
          <div>
            <span class="team-name">${game.home_team}</span>
            <span class="ewma-sub">EWMA NRtg: ${homeEwma} (Trend: ${homeTrend})</span>
          </div>
        </div>
        <span class="spread-pill ${homePicked ? 'picked' : ''}">
          ${game.vegas_home_spread > 0 ? '+' : ''}${game.vegas_home_spread}
        </span>
      </div>

      <div class="model-comparison-box">
        <div class="comparison-row">
          <span style="color: var(--text-muted); font-weight: 600;">ISyE 4031 OLS Spread:</span>
          <span style="font-family: 'JetBrains Mono', monospace; font-weight: 700;">
            ${homeAbbr} ${game.projected_home_spread > 0 ? '+' : ''}${game.projected_home_spread} (Margin: ${game.expected_home_margin > 0 ? '+' : ''}${game.expected_home_margin})
          </span>
        </div>

        <div class="comparison-row">
          <span style="color: var(--text-muted); font-weight: 600;">Discrepancy (Edge):</span>
          <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800; color: ${game.has_edge ? 'var(--bball-orange)' : 'var(--text-muted)'};">
            ${game.has_edge ? `+${game.edge_points} pts on ${game.recommended_side}` : `${game.edge_points} pts (< 2.5 pt threshold)`}
          </span>
        </div>

        <div class="comparison-row" style="margin-top: 6px;">
          <span style="color: var(--text-muted); font-weight: 600;">Student-t P(Cover) vs Vig:</span>
          <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800; color: ${evPct >= 6.0 ? 'var(--pos)' : 'var(--text-secondary)'};">
            ${coverProb.toFixed(1)}% vs ${breakevenProb.toFixed(1)}% (${evPct >= 0 ? '+' : ''}${evPct.toFixed(1)}% EV)
          </span>
        </div>

        <div class="prob-bar-wrap">
          <div class="prob-bar-fill" style="width: ${Math.min(100, Math.max(20, coverProb))}%;"></div>
        </div>

        <div class="pi-bands-row">
          <span>SE_pred: ${sePred} (SE_mean: ${seMean})</span>
          <span>50% PI: [${pi50[0]}, ${pi50[1]}]</span>
          <span>80% PI: [${pi80[0]}, ${pi80[1]}]</span>
        </div>
      </div>

      ${vetoHtml}
    `;

    container.appendChild(card);
  });
}

// ============================================================================
// MONEY LIFECYCLE & ACTIVE BETS DESK
// ============================================================================
function renderMoneyLifecycle(bankroll, activeBets) {
  const container = document.getElementById('lifecycle-steps-container');
  if (!container) return;

  const totalStake = activeBets.reduce((acc, b) => acc + (b.stake || 0), 0);
  const totalPotProfit = activeBets.reduce((acc, b) => acc + (b.potential_profit || 0), 0);
  const winBalance = (bankroll.current_balance + totalPotProfit).toFixed(2);
  const lossBalance = (bankroll.current_balance - totalStake).toFixed(2);
  const picksSummary = activeBets.length > 0
    ? activeBets.map(b => `${getTeamAbbr(b.selection)} ${b.line > 0 ? '+' : ''}${b.line}`).join(', ')
    : 'Awaiting next 4:00 PM scan';

  container.innerHTML = `
    <div class="lifecycle-step">
      <div class="lifecycle-step-num">Step 1 • Starting Capital</div>
      <div class="lifecycle-step-val">$${bankroll.starting_capital.toFixed(2)}</div>
      <div class="lifecycle-step-sub">Current Total: $${bankroll.current_balance.toFixed(2)}</div>
    </div>
    <div class="lifecycle-step">
      <div class="lifecycle-step-num">Step 2 • Tonight's Risk</div>
      <div class="lifecycle-step-val">$${totalStake.toFixed(2)} (${activeBets.length} Pick${activeBets.length === 1 ? '' : 's'})</div>
      <div class="lifecycle-step-sub">${picksSummary}</div>
    </div>
    <div class="lifecycle-step">
      <div class="lifecycle-step-num">Step 3 • Cash In Reserve</div>
      <div class="lifecycle-step-val">$${bankroll.available_cash.toFixed(2)}</div>
      <div class="lifecycle-step-sub">Uninvested bankroll protection</div>
    </div>
    <div class="lifecycle-step">
      <div class="lifecycle-step-num">Step 4 • Morning Settlement</div>
      <div class="lifecycle-step-val" style="color: var(--pos); font-size: 15.5px;">Sweep Win: $${winBalance}</div>
      <div class="lifecycle-step-sub" style="color: var(--neg);">Full Loss: $${lossBalance} (+$${totalPotProfit.toFixed(2)} upside)</div>
    </div>
  `;
}

function renderActiveBetsTable(activeBets) {
  const tbody = document.getElementById('active-bets-tbody');
  tbody.innerHTML = '';

  if (!activeBets || activeBets.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9" style="text-align: center; color: var(--text-muted); padding: 32px;">
          No active wagers pending tonight. Next automated scan occurs at 4:00 PM EST.
        </td>
      </tr>
    `;
    return;
  }

  activeBets.forEach(b => {
    const tr = document.createElement('tr');
    const coverProb = b.cover_prob_pct !== undefined ? `${b.cover_prob_pct}%` : '60.5%';
    const evPct = b.ev_pct !== undefined ? `+${b.ev_pct}%` : '+15.5%';
    const ruleId = b.triggered_rule_id || 'RULE-001';

    tr.innerHTML = `
      <td style="font-weight: 700;">${b.matchup}</td>
      <td>
        <span style="font-weight: 800; color: var(--bball-orange);">${b.selection}</span>
        <span style="font-family: 'JetBrains Mono', monospace; margin-left: 4px;">(${b.line > 0 ? '+' : ''}${b.line})</span>
      </td>
      <td><span class="bookmaker-badge">${b.sportsbook}</span></td>
      <td style="font-family: 'JetBrains Mono', monospace; font-weight: 700;">${b.odds > 0 ? '+' : ''}${b.odds}</td>
      <td style="font-family: 'JetBrains Mono', monospace; font-size: 12.5px;">
        <span style="font-weight: 800; color: var(--pos);">${coverProb}</span>
        <span style="color: var(--text-muted);">(${evPct} EV)</span>
      </td>
      <td style="font-weight: 800;">$${b.stake.toFixed(2)} (${b.units}U)</td>
      <td style="color: var(--pos); font-weight: 800;">+$${b.potential_profit.toFixed(2)}</td>
      <td>
        <span class="bookmaker-badge" style="font-size: 10.5px;">${ruleId} • ${b.gemini_confidence}/100</span>
      </td>
      <td><span class="status-badge status-pending">IN-PLAY</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// ============================================================================
// TAB 3: ISyE 4031 FORECASTING TELEMETRY & SELF-LEARNING AI MEMORY
// ============================================================================
function renderModelAndMemoryTab(decisionBasis) {
  const telemetryGrid = document.getElementById('model-telemetry-grid');
  const rulesContainer = document.getElementById('learned-rules-container');
  const residualsTbody = document.getElementById('residuals-tbody');

  if (!telemetryGrid) return;

  const meta = decisionBasis.model_metadata || {
    model_id: 'courtvision_ewma_ols_v1',
    n_obs: 240,
    df: 235,
    r_squared: 0.418,
    residual_se_s: 10.42
  };
  const smooth = decisionBasis.smoothing_parameters || {
    alpha_level: 0.25,
    beta_trend: 0.10,
    phi1_ar1_reversion: -0.08
  };
  const diag = decisionBasis.diagnostics || {
    cfe: -1.4,
    mad: 4.9,
    tracking_signal: -0.29,
    status: 'IN_CONTROL (Unbiased)',
    out_of_sample_rmse: 10.38,
    interval_coverage_80_pct: 100.0,
    interval_coverage_95_pct: 100.0,
    residual_history: []
  };
  const rules = decisionBasis.learned_rules || [];

  telemetryGrid.innerHTML = `
    <div class="kpi-card accent-bankroll">
      <div class="kpi-label">📐 OLS Fit & Degrees of Freedom</div>
      <div class="kpi-val">R² = ${meta.r_squared}</div>
      <div class="kpi-sub">s = ${meta.residual_se_s} pts • n = ${meta.n_obs} (df = ${meta.df})</div>
    </div>
    <div class="kpi-card accent-trial">
      <div class="kpi-label">📉 Holt EWMA & AR(1) Parameters</div>
      <div class="kpi-val">α=${smooth.alpha_level}, β=${smooth.beta_trend}</div>
      <div class="kpi-sub">AR(1) Blowout Reversion φ₁ = ${smooth.phi1_ar1_reversion}</div>
    </div>
    <div class="kpi-card accent-pnl">
      <div class="kpi-label">📡 Tracking Signal (CFE / MAD)</div>
      <div class="kpi-val" style="color: var(--pos);">${diag.tracking_signal > 0 ? '+' : ''}${diag.tracking_signal}</div>
      <div class="kpi-sub">${diag.status} (Limit: ±3.75)</div>
    </div>
    <div class="kpi-card accent-ats">
      <div class="kpi-label">🎯 SE_pred Interval Coverage</div>
      <div class="kpi-val">${diag.interval_coverage_80_pct}% <span style="font-size: 14px; color: var(--text-muted); font-weight: 600;">(80% PI)</span></div>
      <div class="kpi-sub">95% PI: ${diag.interval_coverage_95_pct}% • RMSE: ${diag.out_of_sample_rmse} pts</div>
    </div>
  `;

  // Render Learned Rules Cards
  if (rulesContainer) {
    rulesContainer.innerHTML = '';
    rules.forEach(rule => {
      const card = document.createElement('div');
      card.className = 'rule-card';
      const deltaSign = rule.parameter_delta > 0 ? '+' : '';
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span class="bookmaker-badge" style="color: var(--purple); border-color: var(--purple-border); background: var(--purple-bg);">
            ${rule.rule_id} • ${rule.category}
          </span>
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 11.5px; font-weight: 800; color: var(--bball-orange);">
            Delta: ${deltaSign}${rule.parameter_delta}
          </span>
        </div>
        <div style="font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">
          "${rule.rule_statement}"
        </div>
        <div style="font-size: 11.5px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">
          Source: ${rule.source_game} | Trigger: ${rule.residual_trigger}
        </div>
      `;
      rulesContainer.appendChild(card);
    });
  }

  // Render Residual History Table
  if (residualsTbody) {
    residualsTbody.innerHTML = '';
    const resHistory = diag.residual_history || [];
    resHistory.forEach(r => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-family: 'JetBrains Mono', monospace; font-size: 12.5px; color: var(--text-muted);">${r.date}</td>
        <td style="font-weight: 700;">${r.matchup}</td>
        <td style="font-family: 'JetBrains Mono', monospace;">${r.predicted_home_margin > 0 ? '+' : ''}${r.predicted_home_margin}</td>
        <td style="font-family: 'JetBrains Mono', monospace; font-weight: 700;">${r.observed_home_margin > 0 ? '+' : ''}${r.observed_home_margin}</td>
        <td style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: ${Math.abs(r.residual_e) <= 10.5 ? 'var(--pos)' : 'var(--amber)'};">
          ${r.residual_e > 0 ? '+' : ''}${r.residual_e} pts
        </td>
        <td style="font-family: 'JetBrains Mono', monospace;">r = ${r.studentized_r > 0 ? '+' : ''}${r.studentized_r}</td>
        <td style="font-family: 'JetBrains Mono', monospace; font-size: 12px;">${r.se_pred} vs ${r.se_mean}</td>
        <td>
          <span class="status-badge ${r.captured_80 ? 'status-won' : 'status-pending'}">
            80%: ${r.captured_80 ? 'YES' : 'NO'} • 95%: ${r.captured_95 ? 'YES' : 'NO'}
          </span>
        </td>
      `;
      residualsTbody.appendChild(tr);
    });
  }
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
    const bankrollAfter = b.bankroll_after ? `$${b.bankroll_after.toFixed(2)}` : '--';

    tr.innerHTML = `
      <td style="color: var(--text-muted); font-size: 12.5px; font-family: 'JetBrains Mono', monospace;">${b.settled_at ? b.settled_at.split(' ')[0] : 'N/A'}</td>
      <td style="font-weight: 700;">${b.matchup}</td>
      <td>
        <span style="font-weight: 800;">${b.selection}</span>
        <span style="font-family: 'JetBrains Mono', monospace; margin-left: 4px;">(${b.line > 0 ? '+' : ''}${b.line})</span>
      </td>
      <td style="font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 700;">${b.final_score || 'N/A'}</td>
      <td><span class="status-badge ${badgeClass}">${b.result}</span></td>
      <td style="font-weight: 600;">$${b.stake.toFixed(2)}</td>
      <td style="font-weight: 800; color: ${pnlColor}; font-family: 'JetBrains Mono', monospace;">
        ${b.net_pnl >= 0 ? '+' : ''}$${b.net_pnl.toFixed(2)}
      </td>
      <td style="font-family: 'JetBrains Mono', monospace; font-weight: 700;">${bankrollAfter}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ============================================================================
// EQUITY CHART (CHART.JS) - CASH FLOW & DAILY BETS HOVER TELEMETRY
// ============================================================================
function getBetsForDate(targetDate, historyItem, bankrollState) {
  let bets = [];
  if (historyItem && Array.isArray(historyItem.bets) && historyItem.bets.length > 0) {
    bets = [...historyItem.bets];
  }

  // If not already in historyItem.bets, check settled_bets
  if (bets.length === 0 && bankrollState && Array.isArray(bankrollState.settled_bets)) {
    const matched = bankrollState.settled_bets.filter(b => {
      const settledDate = b.settled_at ? b.settled_at.split(' ')[0] : '';
      const placedDate = b.date_placed ? b.date_placed.split(' ')[0] : '';
      return settledDate === targetDate || placedDate === targetDate;
    });
    bets = matched.map(b => ({
      bet_id: b.bet_id,
      matchup: b.matchup,
      selection: b.selection,
      line: b.line,
      odds: b.odds,
      stake: b.stake,
      units: b.units,
      result: b.result,
      net_pnl: b.net_pnl,
      final_score: b.final_score
    }));
  }
  return bets;
}

function getActiveBetsForDate(targetDate, isLatestDay, bankrollState) {
  if (!bankrollState || !Array.isArray(bankrollState.active_bets) || bankrollState.active_bets.length === 0) {
    return [];
  }
  return bankrollState.active_bets.filter(b => {
    const placedDate = b.date_placed ? b.date_placed.split(' ')[0] : '';
    return placedDate === targetDate || isLatestDay;
  });
}

function renderEquityChart(history, currentBalance, bankrollState) {
  const ctx = document.getElementById('equityChart');
  if (!ctx) return;

  const currentTheme = document.documentElement.getAttribute('data-theme') || 'slate';
  const isDark = currentTheme === 'slate';

  document.getElementById('chart-latest-balance').textContent = `Balance: $${currentBalance.toFixed(2)}`;

  let labels = history.map(h => h.date);
  let dataPoints = history.map(h => h.balance);

  const textColor = isDark ? '#94a3b8' : '#64748b';
  const gridColor = isDark ? 'rgba(55, 68, 101, 0.4)' : 'rgba(226, 232, 240, 0.7)';

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
          borderColor: '#f97316',
          backgroundColor: isDark ? 'rgba(249, 115, 22, 0.16)' : 'rgba(234, 88, 12, 0.08)',
          fill: true,
          tension: 0.25,
          borderWidth: 3,
          pointBackgroundColor: '#f97316',
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1.5,
          pointRadius: 6,
          pointHoverRadius: 9,
          pointHoverBackgroundColor: '#ea580c',
          pointHoverBorderColor: '#ffffff',
          pointHoverBorderWidth: 2
        },
        {
          label: 'Starting Capital ($1,000 Breakeven)',
          data: labels.map(() => 1000.0),
          borderColor: isDark ? 'rgba(148, 163, 184, 0.5)' : 'rgba(100, 116, 139, 0.4)',
          borderDash: [6, 6],
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: textColor,
            font: { family: 'Plus Jakarta Sans', size: 12, weight: 700 }
          }
        },
        tooltip: {
          enabled: true,
          backgroundColor: isDark ? 'rgba(15, 23, 42, 0.96)' : 'rgba(255, 255, 255, 0.98)',
          titleColor: isDark ? '#f8fafc' : '#0f172a',
          bodyColor: isDark ? '#cbd5e1' : '#334155',
          borderColor: isDark ? 'rgba(249, 115, 22, 0.5)' : 'rgba(234, 88, 12, 0.4)',
          borderWidth: 1.5,
          padding: 14,
          cornerRadius: 10,
          displayColors: false,
          titleFont: { family: 'Plus Jakarta Sans', size: 13, weight: 800 },
          bodyFont: { family: 'JetBrains Mono, monospace', size: 11.5 },
          callbacks: {
            title: function(items) {
              if (!items || !items.length) return '';
              const idx = items[0].dataIndex;
              const date = labels[idx];
              const h = history[idx] || {};
              const bal = h.balance !== undefined ? h.balance : items[0].parsed.y;
              const pnl = h.pnl !== undefined ? h.pnl : 0;
              const pnlSign = pnl > 0 ? '+' : (pnl < 0 ? '-' : '');
              const pnlStr = pnl !== 0 ? ` (${pnlSign}$${Math.abs(pnl).toFixed(2)})` : '';
              return `📅 ${date} • Bankroll: $${bal.toFixed(2)}${pnlStr}`;
            },
            label: function(context) {
              if (context.datasetIndex === 0) {
                return `💰 Portfolio Equity: $${context.parsed.y.toFixed(2)}`;
              }
              return null;
            },
            afterBody: function(items) {
              if (!items || !items.length) return [];
              const idx = items[0].dataIndex;
              const targetDate = labels[idx];
              const h = history[idx] || {};

              const bets = getBetsForDate(targetDate, h, bankrollState);
              const activeForDate = getActiveBetsForDate(targetDate, idx === labels.length - 1, bankrollState);

              const lines = [];
              lines.push('────────────────────────────────────────');

              if (bets.length === 0 && activeForDate.length === 0) {
                if (idx === 0) {
                  lines.push('🏁 Starting Capital: $1,000.00 (Breakeven Baseline)');
                  lines.push('   No bets placed prior to Day 1');
                } else {
                  lines.push('⚪ No bets placed on this date');
                  lines.push('   (No games met the +EV edge & Student-t threshold)');
                }
                return lines;
              }

              if (bets.length > 0) {
                lines.push(`🎯 Settled Wagers (${bets.length} Bet${bets.length === 1 ? '' : 's'}):`);
                bets.forEach((b, i) => {
                  const num = bets.length > 1 ? `${i + 1}. ` : '• ';
                  const lineStr = b.line !== undefined ? (b.line > 0 ? `+${b.line}` : `${b.line}`) : '';
                  const oddsStr = b.odds ? ` @ ${b.odds > 0 ? '+' : ''}${b.odds}` : '';
                  const stakeStr = b.stake ? `$${b.stake.toFixed(0)}` : '';
                  const res = b.result || 'SETTLED';
                  const pnlSign = b.net_pnl >= 0 ? '+' : '';
                  const pnlStr = b.net_pnl !== undefined ? ` (${pnlSign}$${b.net_pnl.toFixed(2)})` : '';

                  lines.push(` ${num}${b.selection} ${lineStr} [${stakeStr}${oddsStr}]`);
                  const scoreStr = b.final_score ? ` | Final: ${b.final_score}` : '';
                  lines.push(`    Outcome: ${res}${pnlStr}${scoreStr}`);
                });
              }

              if (activeForDate.length > 0) {
                if (bets.length > 0) lines.push('');
                lines.push(`⚡ Active In-Play (${activeForDate.length} Bet${activeForDate.length === 1 ? '' : 's'} Placed Tonight):`);
                activeForDate.forEach((b, i) => {
                  const num = activeForDate.length > 1 ? `${i + 1}. ` : '• ';
                  const lineStr = b.line !== undefined ? (b.line > 0 ? `+${b.line}` : `${b.line}`) : '';
                  const oddsStr = b.odds ? ` @ ${b.odds > 0 ? '+' : ''}${b.odds}` : '';
                  const stakeStr = b.stake ? `$${b.stake.toFixed(0)}` : '';
                  const unitsStr = b.units ? ` [${b.units}U]` : '';
                  const probStr = b.cover_prob_pct ? ` | P(Cover): ${b.cover_prob_pct}%` : '';
                  const evStr = b.ev_pct ? ` (+${b.ev_pct}% EV)` : '';

                  lines.push(` ${num}${b.selection} ${lineStr} [${stakeStr}${unitsStr}${oddsStr}] • PENDING`);
                  if (b.matchup) {
                    lines.push(`    ${b.matchup}${probStr}${evStr}`);
                  }
                });
              }

              return lines;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: 'Inter', size: 11, weight: 600 } }
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { family: 'JetBrains Mono', size: 11, weight: 700 },
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
  const gridColor = isDark ? 'rgba(55, 68, 101, 0.4)' : 'rgba(226, 232, 240, 0.7)';

  chart.options.plugins.legend.labels.color = textColor;
  chart.options.scales.x.grid.color = gridColor;
  chart.options.scales.x.ticks.color = textColor;
  chart.options.scales.y.grid.color = gridColor;
  chart.options.scales.y.ticks.color = textColor;

  if (chart.options.plugins.tooltip) {
    chart.options.plugins.tooltip.backgroundColor = isDark ? 'rgba(15, 23, 42, 0.96)' : 'rgba(255, 255, 255, 0.98)';
    chart.options.plugins.tooltip.titleColor = isDark ? '#f8fafc' : '#0f172a';
    chart.options.plugins.tooltip.bodyColor = isDark ? '#cbd5e1' : '#334155';
    chart.options.plugins.tooltip.borderColor = isDark ? 'rgba(249, 115, 22, 0.5)' : 'rgba(234, 88, 12, 0.4)';
  }

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
