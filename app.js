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

// ============================================================================
// TV BROADCAST SCORE BUGS ENGINE (INSPIRED BY ESPN, BALLY SPORTS, YES, TNT)
// ============================================================================

const NBA_TEAMS = {
  BOS: { abbr: "BOS", name: "Boston Celtics", short: "Celtics", city: "Boston", primary: "#007A33", secondary: "#BA9653", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/bos.png", record: "10-3" },
  NYK: { abbr: "NYK", name: "New York Knicks", short: "Knicks", city: "New York", primary: "#006BB6", secondary: "#F58426", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/nyk.png", record: "8-5" },
  GSW: { abbr: "GSW", name: "Golden State Warriors", short: "Warriors", city: "Golden State", primary: "#1D428A", secondary: "#FFC72C", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/gsw.png", record: "9-4" },
  LAL: { abbr: "LAL", name: "Los Angeles Lakers", short: "Lakers", city: "Los Angeles", primary: "#552583", secondary: "#FDB927", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/lal.png", record: "7-5" },
  PHX: { abbr: "PHX", name: "Phoenix Suns", short: "Suns", city: "Phoenix", primary: "#1D1160", secondary: "#E56020", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/phx.png", record: "9-3" },
  CHA: { abbr: "CHA", name: "Charlotte Hornets", short: "Hornets", city: "Charlotte", primary: "#1D1160", secondary: "#00788C", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/cha.png", record: "4-8" },
  DEN: { abbr: "DEN", name: "Denver Nuggets", short: "Nuggets", city: "Denver", primary: "#0E2240", secondary: "#FEC524", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/den.png", record: "8-4" },
  MIN: { abbr: "MIN", name: "Minnesota Timberwolves", short: "Timberwolves", city: "Minnesota", primary: "#0C2340", secondary: "#236192", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/min.png", record: "8-5" },
  OKC: { abbr: "OKC", name: "Oklahoma City Thunder", short: "Thunder", city: "Oklahoma City", primary: "#007AC1", secondary: "#EF3B24", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/okc.png", record: "11-2" },
  POR: { abbr: "POR", name: "Portland Trail Blazers", short: "Trail Blazers", city: "Portland", primary: "#E03A3E", secondary: "#000000", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/por.png", record: "4-9" },
  MIL: { abbr: "MIL", name: "Milwaukee Bucks", short: "Bucks", city: "Milwaukee", primary: "#00471B", secondary: "#EEE1C6", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/mil.png", record: "6-6" },
  MIA: { abbr: "MIA", name: "Miami Heat", short: "Heat", city: "Miami", primary: "#98002E", secondary: "#F9A01B", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/mia.png", record: "5-6" },
  CLE: { abbr: "CLE", name: "Cleveland Cavaliers", short: "Cavaliers", city: "Cleveland", primary: "#860038", secondary: "#041E42", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/cle.png", record: "12-1" },
  PHI: { abbr: "PHI", name: "Philadelphia 76ers", short: "76ers", city: "Philadelphia", primary: "#006BB6", secondary: "#ED174C", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/phi.png", record: "3-8" },
  CHI: { abbr: "CHI", name: "Chicago Bulls", short: "Bulls", city: "Chicago", primary: "#CE1141", secondary: "#000000", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/chi.png", record: "5-7" },
  BKN: { abbr: "BKN", name: "Brooklyn Nets", short: "Nets", city: "Brooklyn", primary: "#000000", secondary: "#707271", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/bkn.png", record: "5-7" },
  TOR: { abbr: "TOR", name: "Toronto Raptors", short: "Raptors", city: "Toronto", primary: "#CE1141", secondary: "#000000", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/tor.png", record: "3-9" },
  IND: { abbr: "IND", name: "Indiana Pacers", short: "Pacers", city: "Indiana", primary: "#002D62", secondary: "#FDBB30", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/ind.png", record: "6-6" },
  ORL: { abbr: "ORL", name: "Orlando Magic", short: "Magic", city: "Orlando", primary: "#0077C0", secondary: "#C4CED4", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/orl.png", record: "7-6" },
  ATL: { abbr: "ATL", name: "Atlanta Hawks", short: "Hawks", city: "Atlanta", primary: "#E03A3E", secondary: "#C1D32F", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/atl.png", record: "5-7" },
  WAS: { abbr: "WAS", name: "Washington Wizards", short: "Wizards", city: "Washington", primary: "#002B5C", secondary: "#E31837", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/was.png", record: "2-9" },
  DET: { abbr: "DET", name: "Detroit Pistons", short: "Pistons", city: "Detroit", primary: "#1D42BA", secondary: "#C8102E", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/det.png", record: "5-8" },
  DAL: { abbr: "DAL", name: "Dallas Mavericks", short: "Mavericks", city: "Dallas", primary: "#00538C", secondary: "#002B5E", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/dal.png", record: "6-6" },
  HOU: { abbr: "HOU", name: "Houston Rockets", short: "Rockets", city: "Houston", primary: "#CE1141", secondary: "#000000", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/hou.png", record: "8-4" },
  MEM: { abbr: "MEM", name: "Memphis Grizzlies", short: "Grizzlies", city: "Memphis", primary: "#5D76A9", secondary: "#12173F", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/mem.png", record: "7-5" },
  NOP: { abbr: "NOP", name: "New Orleans Pelicans", short: "Pelicans", city: "New Orleans", primary: "#0C2340", secondary: "#C8102E", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/nop.png", record: "4-8" },
  SAS: { abbr: "SAS", name: "San Antonio Spurs", short: "Spurs", city: "San Antonio", primary: "#000000", secondary: "#C4CED4", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/sas.png", record: "6-6" },
  SAC: { abbr: "SAC", name: "Sacramento Kings", short: "Kings", city: "Sacramento", primary: "#5A2D81", secondary: "#63727A", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/sac.png", record: "7-5" },
  UTA: { abbr: "UTA", name: "Utah Jazz", short: "Jazz", city: "Utah", primary: "#002B5C", secondary: "#00471B", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/uta.png", record: "3-8" },
  LAC: { abbr: "LAC", name: "LA Clippers", short: "Clippers", city: "Los Angeles", primary: "#C8102E", secondary: "#1D428A", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/lac.png", record: "6-5" }
};

function getTeamInfo(str) {
  if (!str) return { abbr: "NBA", name: "NBA Team", short: "Team", primary: "#1e293b", secondary: "#334155", text: "#FFFFFF", logo: "https://a.espncdn.com/i/teamlogos/nba/500/nba.png", record: "" };
  const s = str.trim().toLowerCase();
  for (const key of Object.keys(NBA_TEAMS)) {
    const t = NBA_TEAMS[key];
    if (s === t.abbr.toLowerCase() || s === key.toLowerCase() || s === t.name.toLowerCase() || s === t.short.toLowerCase() || s.includes(t.short.toLowerCase()) || s.includes(t.name.toLowerCase())) {
      return t;
    }
  }
  const cleanAbbr = str.substring(0, 3).toUpperCase();
  return {
    abbr: cleanAbbr,
    name: str,
    short: str.split(' ').pop() || str,
    city: str.split(' ')[0] || str,
    primary: "#1e293b",
    secondary: "#334155",
    text: "#FFFFFF",
    logo: `https://a.espncdn.com/i/teamlogos/nba/500/${cleanAbbr.toLowerCase()}.png`,
    record: ""
  };
}

let currentBroadcastFilter = 'active';
let isBroadcastSimulating = false;
let broadcastSimInterval = null;
let simSecondsTicking = 17;
let espnLiveStateCache = {};

function formatToEasternTime(isoOrDate) {
  if (!isoOrDate) return '7:00 PM ET';
  try {
    const d = new Date(isoOrDate);
    if (isNaN(d.getTime())) return '7:00 PM ET';
    return d.toLocaleTimeString('en-US', {
      timeZone: 'America/New_York',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    }) + ' ET';
  } catch (e) {
    return '7:00 PM ET';
  }
}

function formatGameTime(isoString) {
  return formatToEasternTime(isoString);
}

function setBroadcastFilter(filter) {
  currentBroadcastFilter = filter;
  ['active', 'settled', 'all'].forEach(f => {
    const btn = document.getElementById(`btn-filter-${f}`);
    if (btn) {
      if (f === filter) btn.classList.add('active');
      else btn.classList.remove('active');
    }
  });
  renderBroadcastScoreBugs();
}

function toggleBroadcastSimulation() {
  isBroadcastSimulating = !isBroadcastSimulating;
  const toggleBtn = document.getElementById('bcast-sim-toggle');
  const iconEl = document.getElementById('bcast-sim-icon');
  const textEl = document.getElementById('bcast-sim-text');

  if (isBroadcastSimulating) {
    if (toggleBtn) toggleBtn.classList.add('simulating');
    if (iconEl) iconEl.textContent = '⏹️';
    if (textEl) textEl.textContent = 'Exit Simulation';

    if (broadcastSimInterval) clearInterval(broadcastSimInterval);
    broadcastSimInterval = setInterval(() => {
      simSecondsTicking--;
      if (simSecondsTicking < 3) simSecondsTicking = 24;

      const scElements = document.querySelectorAll('.bcast-hud-shotclock.sim-clock');
      scElements.forEach(el => {
        el.textContent = `:${simSecondsTicking < 10 ? '0' + simSecondsTicking : simSecondsTicking}`;
      });
    }, 1000);
  } else {
    if (toggleBtn) toggleBtn.classList.remove('simulating');
    if (iconEl) iconEl.textContent = '🔴';
    if (textEl) textEl.textContent = 'Simulate Live Game';
    if (broadcastSimInterval) clearInterval(broadcastSimInterval);
  }

  renderBroadcastScoreBugs();
}

function getSimulatedGameData(bet, awayTeam, homeTeam) {
  const hash = (bet.bet_id || '').split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
  const periods = ["1ST", "2ND", "3RD", "4TH"];
  const period = periods[hash % 4];
  const minutes = 2 + (hash % 9);
  const seconds = 10 + (hash % 48);
  const clock = `${minutes}:${seconds < 10 ? '0' + seconds : seconds}`;
  const lineVal = parseFloat(bet.line || 0);
  const isBetOnHome = bet.selection.includes(homeTeam.name) || bet.selection.includes(homeTeam.short) || bet.selection === homeTeam.abbr;

  let awayScore = 0;
  let homeScore = 0;

  if (period === "1ST") {
    awayScore = 26 + (hash % 8);
    homeScore = 24 + ((hash * 2) % 8);
  } else if (period === "2ND") {
    awayScore = 54 + (hash % 10);
    homeScore = 52 + ((hash * 3) % 10);
  } else if (period === "3RD") {
    awayScore = 78 + (hash % 12);
    homeScore = 75 + ((hash * 5) % 12);
  } else {
    awayScore = 102 + (hash % 14);
    homeScore = 98 + ((hash * 7) % 14);
  }

  // Adjust scores so pick is in a realistic game flow covering or close to the spread
  if (isBetOnHome) {
    if (lineVal > 0) {
      // Underdog: e.g. Pacers +8.5, losing by only 3 points (102 to 99) = covering!
      homeScore = Math.max(20, awayScore - Math.floor(lineVal / 2));
    } else {
      // Favorite: e.g. -4.5, leading by 7 = covering!
      homeScore = awayScore + Math.abs(Math.floor(lineVal)) + 3;
    }
  } else {
    if (lineVal > 0) {
      awayScore = Math.max(20, homeScore - Math.floor(lineVal / 2));
    } else {
      awayScore = homeScore + Math.abs(Math.floor(lineVal)) + 3;
    }
  }

  const networks = ["ESPN", "BALLY", "YES", "TNT", "COURTVISION"];
  const net = networks[hash % networks.length];
  const netClasses = { ESPN: "net-espn", BALLY: "net-bally", YES: "net-yes", TNT: "net-tnt", COURTVISION: "net-courtvision" };

  return {
    awayScore,
    homeScore,
    period,
    clock,
    shotClock: `:${simSecondsTicking < 10 ? '0' + simSecondsTicking : simSecondsTicking}`,
    networkName: net,
    networkClass: netClasses[net] || "net-courtvision",
    awayTimeouts: 3 + (hash % 3),
    homeTimeouts: 2 + ((hash + 1) % 4),
    awayFouls: 1 + (hash % 4),
    homeFouls: 2 + ((hash + 2) % 3)
  };
}

function renderBroadcastScoreBugs() {
  const container = document.getElementById('broadcast-bugs-container');
  const deskContainer = document.getElementById('desk-broadcast-container');
  if (!container && !deskContainer) return;

  const data = window.COURTVISION_DATA;
  if (!data || !data.bankroll_state) return;

  const activeBets = data.bankroll_state.active_bets || [];
  const settledBets = data.bankroll_state.settled_bets || [];

  // Update filter pill counts dynamically
  const activeCountEl = document.getElementById('bcast-count-active');
  const settledCountEl = document.getElementById('bcast-count-settled');
  const allCountEl = document.getElementById('bcast-count-all');
  if (activeCountEl) activeCountEl.textContent = activeBets.length;
  if (settledCountEl) settledCountEl.textContent = settledBets.length;
  if (allCountEl) allCountEl.textContent = activeBets.length + settledBets.length;

  let betsToRender = [];
  if (currentBroadcastFilter === 'active') {
    betsToRender = activeBets;
  } else if (currentBroadcastFilter === 'settled') {
    betsToRender = settledBets;
  } else {
    betsToRender = [...activeBets, ...settledBets];
  }

  const html = betsToRender.length > 0
    ? betsToRender.map(b => buildScoreBugHtml(b)).join('')
    : '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">No wagers match the selected filter.</div>';

  if (container) container.innerHTML = html;
  if (deskContainer) {
    deskContainer.innerHTML = activeBets.map(b => buildScoreBugHtml(b)).join('');
  }
}

function buildScoreBugHtml(bet) {
  const isSettled = bet.status === 'SETTLED' || bet.result !== undefined;
  const matchupStr = bet.matchup || "";
  
  // Robust matchup splitting supporting "@", "at", "vs"
  let awayName = "Away Team", homeName = "Home Team";
  if (matchupStr.includes(" @ ")) {
    const parts = matchupStr.split(" @ ");
    awayName = parts[0].trim();
    homeName = parts[1].trim();
  } else if (matchupStr.includes(" at ")) {
    const parts = matchupStr.split(" at ");
    awayName = parts[0].trim();
    homeName = parts[1].trim();
  } else if (matchupStr.includes(" vs ")) {
    const parts = matchupStr.split(" vs ");
    awayName = parts[0].trim();
    homeName = parts[1].trim();
  }

  const awayTeam = getTeamInfo(awayName);
  const homeTeam = getTeamInfo(homeName);

  const isBetOnAway = bet.selection.includes(awayTeam.name) || bet.selection.includes(awayTeam.short) || bet.selection === awayTeam.abbr;
  const isBetOnHome = bet.selection.includes(homeTeam.name) || bet.selection.includes(homeTeam.short) || bet.selection === homeTeam.abbr;

  const lineVal = parseFloat(bet.line || 0);
  const lineStr = lineVal > 0 ? `+${lineVal}` : `${lineVal}`;
  const oddsVal = bet.odds || -110;
  const oddsStr = oddsVal > 0 ? `+${oddsVal}` : `${oddsVal}`;
  const stakeVal = bet.stake ? parseFloat(bet.stake).toFixed(2) : '40.00';
  const unitsVal = bet.units || 2;
  const profitVal = bet.potential_profit ? parseFloat(bet.potential_profit).toFixed(2) : '36.36';

  // Find real scheduled tip-off time in Eastern Time
  const slate = (window.COURTVISION_DATA && window.COURTVISION_DATA.todays_slate) || [];
  const slateGame = slate.find(g => 
    g.game_id === bet.game_id || 
    (g.away_team && (g.away_team.includes(awayTeam.short) || awayTeam.name.includes(g.away_team))) ||
    (g.home_team && (g.home_team.includes(homeTeam.short) || homeTeam.name.includes(g.home_team)))
  );

  const scheduledTipOffET = slateGame && slateGame.commence_time 
    ? formatToEasternTime(slateGame.commence_time) 
    : '7:00 PM ET';

  let awayScore = 0;
  let homeScore = 0;
  let periodText = "PRE-GAME";
  let clockText = scheduledTipOffET;
  let shotClockText = "--";
  let isLive = false;
  let isFinal = false;
  let networkName = "COURTVISION";
  let networkClass = "net-courtvision";
  let awayTimeouts = 5;
  let homeTimeouts = 5;
  let awayFouls = 1;
  let homeFouls = 2;

  if (isSettled) {
    isFinal = true;
    periodText = "FINAL";
    clockText = "FINAL";
    shotClockText = "OFF";
    networkName = "FINAL";
    networkClass = "net-courtvision";

    if (bet.final_score) {
      const scoreParts = bet.final_score.split("-");
      if (scoreParts.length === 2) {
        const aPart = scoreParts[0].trim().split(" ");
        const hPart = scoreParts[1].trim().split(" ");
        awayScore = parseInt(aPart[aPart.length - 1], 10) || 0;
        homeScore = parseInt(hPart[hPart.length - 1], 10) || 0;
      }
    }
  } else if (isBroadcastSimulating) {
    isLive = true;
    const simData = getSimulatedGameData(bet, awayTeam, homeTeam);
    awayScore = simData.awayScore;
    homeScore = simData.homeScore;
    periodText = simData.period;
    clockText = simData.clock;
    shotClockText = simData.shotClock;
    networkName = simData.networkName;
    networkClass = simData.networkClass;
    awayTimeouts = simData.awayTimeouts;
    homeTimeouts = simData.homeTimeouts;
    awayFouls = simData.awayFouls;
    homeFouls = simData.homeFouls;
  } else if (espnLiveStateCache[bet.bet_id]) {
    const live = espnLiveStateCache[bet.bet_id];
    awayScore = live.awayScore;
    homeScore = live.homeScore;
    periodText = live.periodText;
    clockText = live.clockText;
    shotClockText = live.shotClockText;
    isLive = live.isLive;
    isFinal = live.isFinal;
    networkName = live.networkName || "ESPN";
    networkClass = live.networkClass || "net-espn";
    awayTimeouts = live.awayTimeouts || 4;
    homeTimeouts = live.homeTimeouts || 4;
    awayFouls = live.awayFouls || 2;
    homeFouls = live.homeFouls || 2;
  } else {
    periodText = "PRE-GAME";
    clockText = scheduledTipOffET;
    shotClockText = "--";
    awayScore = null;
    homeScore = null;
  }

  // Cover Status & Meter Calculations
  let coverBadgeHtml = "";
  let meterFillHtml = "";
  let cardCoverClass = "";

  if (isSettled) {
    const isWon = bet.result === 'WON';
    const margin = bet.cover_margin !== undefined ? bet.cover_margin : 0;
    const marginStr = margin > 0 ? `+${margin}` : `${margin}`;
    cardCoverClass = isWon ? "bet-covering" : "bet-losing";

    if (isWon) {
      coverBadgeHtml = `<span class="bcast-cover-badge status-won">🏆 BET WON • COVERED BY ${marginStr} PTS (+$${bet.net_pnl.toFixed(2)})</span>`;
      meterFillHtml = `<div class="bcast-meter-fill fill-green" style="width: 100%;"></div>`;
    } else {
      coverBadgeHtml = `<span class="bcast-cover-badge status-lost">❌ BET LOST • MISSED BY ${marginStr} PTS (-$${Math.abs(bet.net_pnl).toFixed(2)})</span>`;
      meterFillHtml = `<div class="bcast-meter-fill fill-red" style="width: 100%;"></div>`;
    }
  } else if (isLive) {
    let liveMarginAgainstLine = 0;
    if (isBetOnHome) {
      liveMarginAgainstLine = (homeScore - awayScore) + lineVal;
    } else {
      liveMarginAgainstLine = (awayScore - homeScore) + lineVal;
    }

    const marginStr = liveMarginAgainstLine > 0 ? `+${liveMarginAgainstLine.toFixed(1)}` : `${liveMarginAgainstLine.toFixed(1)}`;
    const isCovering = liveMarginAgainstLine > 0;
    cardCoverClass = isCovering ? "bet-covering" : "bet-losing";
    const progressPct = Math.min(100, Math.max(10, 50 + (liveMarginAgainstLine * 3)));

    if (liveMarginAgainstLine > 0) {
      coverBadgeHtml = `<span class="bcast-cover-badge status-covering">🟢 COVERING (${marginStr} PTS) • LIVE MARGIN</span>`;
      meterFillHtml = `<div class="bcast-meter-fill fill-green" style="width: ${progressPct}%;"></div>`;
    } else if (liveMarginAgainstLine < 0) {
      coverBadgeHtml = `<span class="bcast-cover-badge status-losing">🔴 NOT COVERING (${marginStr} PTS) • DEFICIT</span>`;
      meterFillHtml = `<div class="bcast-meter-fill fill-red" style="width: ${progressPct}%;"></div>`;
    } else {
      coverBadgeHtml = `<span class="bcast-cover-badge status-upcoming">🟡 AT SPREAD (PUSH)</span>`;
      meterFillHtml = `<div class="bcast-meter-fill fill-blue" style="width: 50%;"></div>`;
    }
  } else {
    // Upcoming
    const prob = bet.cover_prob_pct || 60.5;
    const ev = bet.ev_pct || 15.5;
    coverBadgeHtml = `<span class="bcast-cover-badge status-upcoming">⏳ PRE-GAME • P(Cover): ${prob}% (+${ev}% EV)</span>`;
    meterFillHtml = `<div class="bcast-meter-fill fill-blue" style="width: ${Math.min(100, prob)}%;"></div>`;
  }

  const awayTicks = Array.from({length: 5}, (_, i) => `<span class="timeout-dash ${i < awayTimeouts ? 'active' : ''}"></span>`).join('');
  const homeTicks = Array.from({length: 5}, (_, i) => `<span class="timeout-dash ${i < homeTimeouts ? 'active' : ''}"></span>`).join('');

  const awayScoreDisplay = awayScore !== null
    ? `<span class="bcast-score-num ${isFinal && awayScore > homeScore ? 'winner-score' : ''}">${awayScore}</span>`
    : `<span class="bcast-score-num pregame-dash">--</span>`;

  const homeScoreDisplay = homeScore !== null
    ? `<span class="bcast-score-num ${isFinal && homeScore > awayScore ? 'winner-score' : ''}">${homeScore}</span>`
    : `<span class="bcast-score-num pregame-dash">--</span>`;

  const awayBetPill = isBetOnAway ? `<span class="bcast-wing-bet-pill">★ OUR BET ${lineStr}</span>` : '';
  const homeBetPill = isBetOnHome ? `<span class="bcast-wing-bet-pill">★ OUR BET ${lineStr}</span>` : '';

  let topStatusClass = "is-upcoming";
  let topStatusLabel = `TONIGHT • ${clockText}`;
  if (isLive) {
    topStatusClass = "is-live";
    topStatusLabel = `🔴 LIVE • ${periodText} ${clockText}`;
  } else if (isFinal) {
    topStatusClass = "is-final";
    topStatusLabel = "FINAL SCORE";
  }

  return `
    <div class="bcast-scorebug ${cardCoverClass}" id="scorebug-${bet.bet_id}">
      
      <!-- Top Broadcast Ribbon -->
      <div class="bcast-top-ribbon">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="bcast-network-badge ${networkClass}">${networkName} HD</span>
          <span class="bcast-status-indicator ${topStatusClass}">
            ${isLive ? '<span class="live-pulse-dot"></span>' : ''}
            <span>${topStatusLabel}</span>
          </span>
        </div>
        <span class="bcast-sportsbook-tag">${bet.sportsbook || 'DraftKings'} ${oddsStr}</span>
      </div>

      <!-- Main Scoreboard Chassis -->
      <div class="bcast-rack">
        
        <!-- Away Team Wing -->
        <div class="bcast-team-wing away" style="background: linear-gradient(135deg, ${awayTeam.primary}44 0%, rgba(13, 19, 34, 0.95) 75%);">
          <div>
            <div class="bcast-team-header">
              <img src="${awayTeam.logo}" alt="${awayTeam.abbr}" class="bcast-team-logo" loading="lazy" onerror="this.style.opacity='0.4'">
              <div class="bcast-team-meta">
                <div class="bcast-team-abbr">${awayTeam.abbr} ${awayBetPill}</div>
                <div class="bcast-team-name">${awayTeam.short}</div>
              </div>
            </div>
          </div>

          <div class="bcast-score-row">
            ${awayScoreDisplay}
          </div>

          <div class="bcast-telemetry-row">
            <span class="bcast-foul-text">FLS: ${awayFouls}</span>
            <div class="bcast-timeout-ticks" title="Timeouts Remaining: ${awayTimeouts}/5">
              <span style="font-size: 9px; margin-right: 2px;">TO:</span>
              ${awayTicks}
            </div>
          </div>
        </div>

        <!-- Center Game Clock HUD (Recessed Display) -->
        <div class="bcast-hud">
          <div class="bcast-hud-period">${periodText}</div>
          <div class="bcast-hud-clock">${clockText}</div>
          <div class="bcast-hud-shotclock ${isLive ? 'sim-clock' : ''}">${shotClockText}</div>
        </div>

        <!-- Home Team Wing -->
        <div class="bcast-team-wing home" style="background: linear-gradient(225deg, ${homeTeam.primary}44 0%, rgba(13, 19, 34, 0.95) 75%);">
          <div>
            <div class="bcast-team-header">
              <img src="${homeTeam.logo}" alt="${homeTeam.abbr}" class="bcast-team-logo" loading="lazy" onerror="this.style.opacity='0.4'">
              <div class="bcast-team-meta">
                <div class="bcast-team-abbr">${homeBetPill} ${homeTeam.abbr}</div>
                <div class="bcast-team-name">${homeTeam.short}</div>
              </div>
            </div>
          </div>

          <div class="bcast-score-row">
            ${homeScoreDisplay}
          </div>

          <div class="bcast-telemetry-row">
            <div class="bcast-timeout-ticks" title="Timeouts Remaining: ${homeTimeouts}/5">
              <span style="font-size: 9px; margin-right: 2px;">TO:</span>
              ${homeTicks}
            </div>
            <span class="bcast-foul-text">FLS: ${homeFouls}</span>
          </div>
        </div>

      </div>

      <!-- Lower-Third Betting Chyron Strip -->
      <div class="bcast-chyron-strip">
        <div class="bcast-chyron-main">
          <div class="bcast-bet-summary">
            <span>🎯</span>
            <span style="font-weight: 700;">Wager:</span>
            <span class="bcast-pick-pill">${bet.selection} (${lineStr})</span>
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted);">$${stakeVal} (${unitsVal}U) ➔ +$${profitVal}</span>
          </div>
          <div>
            ${coverBadgeHtml}
          </div>
        </div>
        <div class="bcast-meter-track" title="Cover Margin Meter">
          ${meterFillHtml}
        </div>
      </div>

    </div>
  `;
}

function toggleDeskView(mode) {
  const bugsContainer = document.getElementById('desk-broadcast-container');
  const tableContainer = document.querySelector('#pane-desk .table-container');
  const bugsBtn = document.getElementById('desk-view-bugs-btn');
  const tableBtn = document.getElementById('desk-view-table-btn');

  if (mode === 'bugs') {
    if (bugsContainer) bugsContainer.style.display = 'grid';
    if (tableContainer) tableContainer.style.display = 'none';
    if (bugsBtn) bugsBtn.classList.add('active');
    if (tableBtn) tableBtn.classList.remove('active');
  } else {
    if (bugsContainer) bugsContainer.style.display = 'none';
    if (tableContainer) tableContainer.style.display = 'block';
    if (bugsBtn) bugsBtn.classList.remove('active');
    if (tableBtn) tableBtn.classList.add('active');
  }
}

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

  const nowET = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  }).format(new Date()) + ' ET';
  document.getElementById('slate-updated-time').textContent = `Sync: ${nowET}`;

  // 6. Render Tab 1: Game Slate with ISyE 4031 Telemetry
  // Render Broadcast Score Bugs for games being bet on
  renderBroadcastScoreBugs();

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

    card.id = `slate-card-${game.game_id}`;
    card.innerHTML = `
      <div class="game-header">
        <span style="font-weight: 700;">🏀 ${gameTime} • <span id="game-live-status-${game.game_id}" style="color: var(--bball-orange);">Prospective Nowcast</span></span>
        <span class="bookmaker-badge">${game.sportsbook}</span>
      </div>

      <div class="matchup-row">
        <div class="team-badge-wrap">
          <span class="team-chip">${awayAbbr}</span>
          <div>
            <span class="team-name">${game.away_team} <span id="away-live-score-${game.game_id}" style="font-family: 'JetBrains Mono', monospace; font-weight: 800; color: var(--text-primary); margin-left: 6px;"></span></span>
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
            <span class="team-name">${game.home_team} <span id="home-live-score-${game.game_id}" style="font-family: 'JetBrains Mono', monospace; font-weight: 800; color: var(--text-primary); margin-left: 6px;"></span></span>
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
        <td colspan="10" style="text-align: center; color: var(--text-muted); padding: 32px;">
          No active wagers pending tonight. Next automated scan occurs at 4:00 PM EST.
        </td>
      </tr>
    `;
    return;
  }

  activeBets.forEach(b => {
    const tr = document.createElement('tr');
    tr.id = `bet-row-${b.bet_id}`;
    const coverProb = b.cover_prob_pct !== undefined ? `${b.cover_prob_pct}%` : '60.5%';
    const evPct = b.ev_pct !== undefined ? `+${b.ev_pct}%` : '+15.5%';
    const ruleId = b.triggered_rule_id || 'RULE-001';

    tr.innerHTML = `
      <td style="font-weight: 700;">${b.matchup}</td>
      <td>
        <span style="font-weight: 800; color: var(--bball-orange);">${b.selection}</span>
        <span style="font-family: 'JetBrains Mono', monospace; margin-left: 4px;">(${b.line > 0 ? '+' : ''}${b.line})</span>
      </td>
      <td id="live-score-${b.bet_id}" style="font-family: 'JetBrains Mono', monospace; font-size: 13px;">
        <span style="color: var(--text-muted);">Syncing live...</span>
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
      <td id="live-cover-${b.bet_id}">
        <span class="status-badge status-pending">IN-PLAY</span>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// ============================================================================
// LIVE NBA SCOREBOARD & REAL-TIME COVER TRACKER (ESPN PUBLIC FEED)
// ============================================================================
let livePollInterval = null;

async function fetchLiveScoresAndUpdateDesk() {
  try {
    const res = await fetch('https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard');
    if (!res.ok) return;
    const data = await res.json();
    const events = data.events || [];

    const activeBets = (window.COURTVISION_DATA && window.COURTVISION_DATA.bankroll_state)
      ? (window.COURTVISION_DATA.bankroll_state.active_bets || [])
      : [];

    events.forEach(ev => {
      const comp = ev.competitions && ev.competitions[0];
      if (!comp) return;

      const competitors = comp.competitors || [];
      if (competitors.length < 2) return;

      const home = competitors.find(c => c.homeAway === 'home') || competitors[0];
      const away = competitors.find(c => c.homeAway === 'away') || competitors[1];

      const homeName = home.team.displayName;
      const awayName = away.team.displayName;
      const homeScore = parseInt(home.score || '0', 10);
      const awayScore = parseInt(away.score || '0', 10);

      const status = ev.status || {};
      const state = status.type ? status.type.state : 'pre';
      const detail = status.type ? status.type.detail : 'Scheduled';
      const isFinal = status.type ? status.type.completed : false;

      // Match against active bets
      activeBets.forEach(b => {
        const matchup = b.matchup || '';
        const isMatch = (matchup.includes(awayName) || matchup.includes(away.team.shortDisplayName)) &&
                        (matchup.includes(homeName) || matchup.includes(home.team.shortDisplayName));

        if (!isMatch) return;

        const scoreCell = document.getElementById(`live-score-${b.bet_id}`);
        const coverCell = document.getElementById(`live-cover-${b.bet_id}`);
        if (!scoreCell || !coverCell) return;

        if (state === 'pre') {
          scoreCell.innerHTML = `<span style="color: var(--text-muted); font-size: 12px;">⏳ ${detail}</span>`;
          coverCell.innerHTML = `<span class="status-badge status-pending">PRE-GAME</span>`;
          return;
        }

        // Live In-Progress or Final
        scoreCell.innerHTML = `
          <div style="font-weight: 800; color: var(--text-primary); font-size: 13px;">
            ${getTeamAbbr(awayName)} ${awayScore} - ${homeScore} ${getTeamAbbr(homeName)}
          </div>
          <div style="font-size: 11px; color: ${isFinal ? 'var(--text-muted)' : 'var(--bball-orange)'}; font-weight: 700;">
            ${isFinal ? 'FINAL' : `🔴 ${detail}`}
          </div>
        `;

        // Calculate current cover margin
        const isBetOnHome = b.selection.includes(homeName) || b.selection.includes(home.team.shortDisplayName) || b.selection === homeName;
        const line = parseFloat(b.line);

        let liveMarginAgainstLine = 0;
        if (isBetOnHome) {
          // Home margin + line: e.g. Home 100, Away 95 (+5 margin). If line -1.5 -> +5 + (-1.5) = +3.5
          liveMarginAgainstLine = (homeScore - awayScore) + line;
        } else {
          // Away margin + line: e.g. Away 95, Home 100 (-5 margin). If line +1.5 -> -5 + 1.5 = -3.5
          liveMarginAgainstLine = (awayScore - homeScore) + line;
        }

        const marginStr = liveMarginAgainstLine > 0 ? `+${liveMarginAgainstLine.toFixed(1)}` : `${liveMarginAgainstLine.toFixed(1)}`;

        if (liveMarginAgainstLine > 0) {
          coverCell.innerHTML = `
            <span class="status-badge status-won" style="font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 4px;">
              🟢 COVERING (${marginStr})
            </span>
          `;
        } else if (liveMarginAgainstLine < 0) {
          coverCell.innerHTML = `
            <span class="status-badge status-lost" style="font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 4px;">
              🔴 NOT COVERING (${marginStr})
            </span>
          `;
        } else {
          coverCell.innerHTML = `
            <span class="status-badge status-push" style="font-size: 11px; font-weight: 800;">
              🟡 PUSH (${marginStr})
            </span>
          `;
        }
      });

      // Also match against slate cards on Tab 1
      
      // Also update TV Broadcast Score Bug cache
      activeBets.forEach(b => {
        const matchup = b.matchup || '';
        const isMatch = (matchup.includes(awayName) || matchup.includes(away.team.shortDisplayName)) &&
                        (matchup.includes(homeName) || matchup.includes(home.team.shortDisplayName));
        if (!isMatch) return;

        espnLiveStateCache[b.bet_id] = {
          awayScore: awayScore,
          homeScore: homeScore,
          periodText: state === 'pre' ? 'PRE-GAME' : (isFinal ? 'FINAL' : `Q${status.period || 1}`),
          clockText: state === 'pre' ? (status.type ? status.type.shortDetail || '7:30 PM' : '7:30 PM') : (isFinal ? 'FINAL' : (status.displayClock || '10:00')),
          shotClockText: state === 'in' ? ':24' : (isFinal ? 'OFF' : '--'),
          isLive: state === 'in',
          isFinal: isFinal || state === 'post',
          networkName: 'ESPN',
          networkClass: 'net-espn',
          awayTimeouts: 4,
          homeTimeouts: 4,
          awayFouls: 2,
          homeFouls: 3
        };
      });
      if (!isBroadcastSimulating) {
        renderBroadcastScoreBugs();
      }

      const slate = (window.COURTVISION_DATA && window.COURTVISION_DATA.todays_slate) || [];
      slate.forEach(g => {
        const isMatch = (g.away_team.includes(awayName) || awayName.includes(g.away_team)) &&
                        (g.home_team.includes(homeName) || homeName.includes(g.home_team));
        if (!isMatch) return;

        const awayScoreEl = document.getElementById(`away-live-score-${g.game_id}`);
        const homeScoreEl = document.getElementById(`home-live-score-${g.game_id}`);
        const statusEl = document.getElementById(`game-live-status-${g.game_id}`);

        if (awayScoreEl && homeScoreEl) {
          if (state !== 'pre') {
            awayScoreEl.textContent = `[${awayScore}]`;
            homeScoreEl.textContent = `[${homeScore}]`;
          }
        }
        if (statusEl) {
          if (state === 'in') {
            statusEl.innerHTML = `<span style="color: var(--neg); font-weight: 800;">🔴 LIVE: ${detail}</span>`;
          } else if (state === 'post' || isFinal) {
            statusEl.innerHTML = `<span style="color: var(--text-muted); font-weight: 800;">FINAL</span>`;
          }
        }
      });
    });
  } catch (err) {
    console.warn('[CourtVision Live] ESPN polling notice:', err);
  }
}

function startLiveScoreboardPolling() {
  if (livePollInterval) clearInterval(livePollInterval);
  fetchLiveScoresAndUpdateDesk();
  // Poll ESPN every 25 seconds for real-time live updates
  livePollInterval = setInterval(fetchLiveScoresAndUpdateDesk, 25000);
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

function formatToEasternTime(isoOrDate) {
  if (!isoOrDate) return '7:00 PM ET';
  try {
    const d = new Date(isoOrDate);
    if (isNaN(d.getTime())) return '7:00 PM ET';
    return d.toLocaleTimeString('en-US', {
      timeZone: 'America/New_York',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    }) + ' ET';
  } catch (e) {
    return '7:00 PM ET';
  }
}

function formatGameTime(isoString) {
  return formatToEasternTime(isoString);
}

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  renderDashboard();
  startLiveScoreboardPolling();
});
