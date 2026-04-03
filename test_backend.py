"""
test_backend.py — Quick smoke-test for the RecapAI backend
===========================================================
Run:  python test_backend.py

Requires .env to be configured (see .env.example).
"""

from backend import summarize_transcript

SAMPLE_TRANSCRIPT = """\
Alice: Good morning everyone. Let's get started. First item — the Q3 marketing budget.

Bob: I've reviewed the numbers. I think we should increase digital ad spend by 15% and cut print by 10%.

Alice: That sounds reasonable. Any objections? … Okay, let's go with that.

Carol: I'll update the budget spreadsheet by Friday and send it to finance.

Bob: Also, are we still planning the product launch event for October 12th?

Alice: That's still TBD — we need to confirm the venue. Carol, can you check availability at the Marriott and the Hilton?

Carol: Sure, I'll have options by next Wednesday.

Alice: Great. One more thing — Dave mentioned he wants to revisit the onboarding flow, but he's out today. Let's table that for the next meeting.

Bob: Agreed. Should we invite the design team to that discussion?

Alice: Good idea, but let's decide that when Dave is here. Alright, meeting adjourned.
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