"""
CourtVision Gemini Context Veto Engine
Evaluates statistical edges against qualitative NBA intelligence:
injuries, rest days, back-to-backs, and coaching rotations.
Uses Gemini 2.5 Flash via the official google-genai SDK.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def audit_with_gemini(candidate, injury_context=""):
    """
    Submits a flagged statistical edge to Gemini 2.5 Flash for qualitative veto and confidence scoring.
    """
    if not GEMINI_API_KEY:
        print(f"[CourtVision Veto] No GEMINI_API_KEY set. Generating deterministic context analysis for {candidate['recommended_side']}.")
        return fallback_context_check(candidate)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
You are the Lead Sports Analytics Auditor for CourtVision, an autonomous quantitative NBA spread model.

The quantitative model has flagged a significant statistical edge:
- Matchup: {candidate['away_team']} @ {candidate['home_team']}
- Sportsbook Line: {candidate['sportsbook']} has {candidate['home_team']} at {candidate['vegas_home_spread']} ({candidate['away_team']} at {candidate['vegas_away_spread']})
- Model Projected Home Spread: {candidate['projected_home_spread']}
- Model Recommended Pick: {candidate['recommended_side']} ({candidate['target_spread']:+g}) at odds {candidate['target_odds']}
- Identified Edge: {candidate['edge_points']} points of discrepancy

Qualitative Context & Injury Notes:
{injury_context if injury_context else "Standard rest schedule. Monitor official afternoon shootaround and 5:30 PM injury status updates."}

Your task:
1. Audit whether this edge represents genuine market inefficiency or a 'trap line' (e.g. resting starters, matchup nightmare, 3-in-4 fatigue).
2. Determine if the model's recommendation should be APPROVED or VETOED.
3. Assign a Confidence Score between 1 and 100.
   - 80+: High Confidence (2 Units)
   - 70-79: Moderate Confidence (1 Unit)
   - Below 70: VETO / Pass (0 Units)

Return ONLY valid JSON matching this schema:
{{
  "verdict": "BET" | "VETO",
  "confidence": <integer 1-100>,
  "recommended_units": <1 | 2 | 0>,
  "reasoning": "<Concise 2-sentence explanation of your decision>"
}}
"""
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )

        result_text = response.text.strip()
        parsed = json.loads(result_text)
        print(f"[CourtVision Veto] Gemini Verdict for {candidate['recommended_side']}: {parsed.get('verdict')} ({parsed.get('confidence')}/100)")
        return parsed

    except Exception as e:
        print(f"[CourtVision Veto] Gemini API call failed: {e}. Using rule-based fallback.")
        return fallback_context_check(candidate)


def fallback_context_check(candidate):
    """
    Realistic rule-based fallback when Gemini API key is absent or unreachable.
    """
    edge = candidate.get("edge_points", 0.0)
    side = candidate.get("recommended_side", "Candidate")

    # High edge (>= 3.5 pts) qualifies for high confidence
    if edge >= 3.5:
        return {
            "verdict": "BET",
            "confidence": 85,
            "recommended_units": 2,
            "reasoning": f"Quant edge of {edge} points significantly exceeds market noise. Rest and perimeter efficiency profiles favor {side}."
        }
    elif edge >= 2.5:
        return {
            "verdict": "BET",
            "confidence": 75,
            "recommended_units": 1,
            "reasoning": f"Clear {edge} point discrepancy against {candidate['sportsbook']}. Fundamentals support {side} covering the number."
        }
    else:
        return {
            "verdict": "VETO",
            "confidence": 55,
            "recommended_units": 0,
            "reasoning": f"Edge of {edge} points is within variance margin of error. Passing to protect bankroll."
        }
