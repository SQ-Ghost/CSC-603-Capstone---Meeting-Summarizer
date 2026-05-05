"""
test_backend.py — Quick smoke-test for the RecapAI backend
===========================================================
Run:  python test_backend.py

Requires .env to be configured (see .env.example).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from backend import summarize_transcript

SAMPLE_TRANSCRIPT = """\
Okay so let's just get going, we're already like five minutes late. Yeah sorry, I was on another call. So what are we starting with? The budget stuff. I sent the numbers around yesterday, did everyone get a chance to look? I did, and honestly I think we should just go with the digital increase, print's not doing anything for us. Agreed, let's cut print by ten and move it over. We good on that? Okay moving on. Hey quick thing, someone needs to update the spreadsheet and get it over to finance before Friday. Yeah I can do that, I'll have it over by Friday no problem. Cool. Uh what about the October launch event, are we still on for the 12th? That's still up in the air, we haven't locked down a venue yet. Can you check on the Marriott and maybe one other option and get back to us by next week? Sure, I'll have something by Wednesday. Okay good. Last thing, Dave wanted to talk about the onboarding flow but he's out today so let's just push that to next time. Should we loop in the design team for that conversation? Probably yeah but let's wait until Dave's back and decide then. Alright that's everything I think, talk soon.
"""


def main():
    print("=" * 60)
    print("RecapAI Backend — Smoke Test")
    print("=" * 60)

    result = summarize_transcript(SAMPLE_TRANSCRIPT)

    print("\n✅  Result keys:", list(result.keys()))
    print()

    # Summary
    print("── Summary ──")
    print(result["summary"])
    print()

    # Decisions
    print("── Decisions ──")
    for d in result.get("decisions", []):
        print(f"  • {d}")
    if not result.get("decisions"):
        print("  (none)")
    print()

    # Tasks
    print("── Assigned Tasks ──")
    for t in result.get("assigned_tasks", []):
        print(f"  • {t['who']}: {t['what']} (Due: {t['due']})")
    if not result.get("assigned_tasks"):
        print("  (none)")
    print()

    # Open questions
    print("── Open Questions ──")
    for q in result.get("open_questions", []):
        print(f"  • {q}")
    if not result.get("open_questions"):
        print("  (none)")
    print()

    # Schema validation
    print("── Schema check ──")
    assert isinstance(result["summary"], str), "summary should be str"
    assert isinstance(result["decisions"], list), "decisions should be list"
    assert isinstance(result["assigned_tasks"], list), "assigned_tasks should be list"
    assert isinstance(result["open_questions"], list), "open_questions should be list"
    for t in result["assigned_tasks"]:
        assert "who" in t and "what" in t and "due" in t, f"task missing keys: {t}"
    print("  All assertions passed ✓")
    print()


if __name__ == "__main__":
    main()