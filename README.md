# CourtVision: Autonomous AI NBA Spread Tracker & Paper Bankroll

> **CourtVision** is a fully automated quantitative sports analytics engine and $1,000 paper betting simulation. It ingests live betting lines from regulated sportsbooks (DraftKings, FanDuel, BetMGM), models expected margins of victory using advanced NBA metrics, applies qualitative context checks via Google Gemini 2.5 Flash (injuries, fatigue, rotations), and transparently tracks an auditable $1,000 paper bankroll across the season.

---

## 🌟 Key Features

1. **Live Sportsbook Ingestion:** Pulls real-time spreads, moneylines, and over/unders from licensed US bookmakers via **The Odds API**.
2. **Quantitative Spread Model:** Calculates projected point spreads using rolling 10-game Net Ratings, Pace, and Home Court Advantage adjustments.
3. **Gemini 2.5 Flash Context Veto:** Audits flagged statistical discrepancies against official afternoon NBA injury reports and back-to-back rest fatigue to eliminate "trap lines."
4. **$1,000 Paper Bankroll Ledger:** Automatically places 1-unit ($20) or 2-unit ($40) simulated bets, accounting for realistic juice (-110 odds) and pushes.
5. **Overnight Auto-Grader:** Wakes up every morning, compares official NBA box scores against active wagers, grades outcomes (`WON`, `LOST`, `PUSH`), and updates P&L and ROI.
6. **30-Day Forward Forecast Simulator:** Interactive Monte Carlo simulation engine that projects bankroll growth over the next 30 days for any starting capital ($X).
7. **Zero-Maintenance GitHub Pages Hosting:** Runs hands-free twice daily via GitHub Actions; updates an interactive dark-mode dashboard without requiring a paid server.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│                   DATA INGESTION                       │
│  - The Odds API: Spreads & Moneylines (DraftKings, etc)│
│  - nba_api: 10-game Net Rating, Pace, Rest Days        │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                QUANTITATIVE SPREAD MODEL               │
│  - Expected Margin = (NetDiff * Pace / 100) + HCA      │
│  - Discrepancy Filter: |Model Spread - Vegas| >= 2.5   │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                 GEMINI 2.5 FLASH VETO                  │
│  - Analyzes injury reports, shootaround news & fatigue │
│  - Returns structured BET/VETO decision + confidence   │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                $1,000 BANKROLL ENGINE                  │
│  - Staking: 1 Unit ($20 / 2%) or 2 Units ($40 / 4%)    │
│  - Persists state in data/bankroll_state.json          │
│  - Auto-grades morning final scores & tracks ATS ROI   │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│               GITHUB PAGES DASHBOARD                   │
│  - Tab 1: Today's Action & AI Recommendations          │
│  - Tab 2: Live $1,000 Simulation Monitor               │
│  - Tab 3: Interactive 30-Day Projection Simulator      │
└────────────────────────────────────────────────────────┘
```

---

## 🚀 Quickstart & Local Setup

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/<your-username>/court-vision.git
cd court-vision
pip install -r requirements.txt
```

### 2. Configure Environment Variables (Optional for Live Data)
Create a `.env` file in the root directory:
```env
THE_ODDS_API_KEY=your_the_odds_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```
*(Note: If API keys are not provided, CourtVision automatically uses built-in realistic mock data and rule-based heuristics so you can test the entire pipeline immediately!)*

### 3. Run Pipeline Locally
```bash
python update_model.py
```

---

## ⚙️ Automated GitHub Actions Setup

To enable hands-free daily automation:
1. Push this repository to GitHub.
2. In your repository, go to **Settings** > **Secrets and variables** > **Actions**.
3. Add two repository secrets:
   - `THE_ODDS_API_KEY`: Get a free key at [the-odds-api.com](https://the-odds-api.com) (500 requests/month free).
   - `GEMINI_API_KEY`: Get a free key at [Google AI Studio](https://aistudio.google.com).
4. Go to **Settings** > **Pages** > Set Source to **Deploy from a branch** > branch: `main`, folder: `/docs`.
5. The scheduled action (`.github/workflows/daily_courtvision.yml`) will run automatically at 4:00 PM EST and 8:00 AM EST every day.
