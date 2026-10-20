"""Manual quality check for draft prompts. MAKES REAL GROQ CALLS (costs a little).

Never run in CI or tests. Usage, from the repository root:

    GROQ_API_KEY=... python scripts/eval_drafts.py            # new prompt, 3 drafts each
    GROQ_API_KEY=... python scripts/eval_drafts.py --compare  # also the original prompt

Uses five fictional recipients and one fictional sender profile; prints drafts
with their length and any banned phrases found, so prompt changes can be
compared side by side.
"""
import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.prompts import BANNED_PHRASES, DRAFTS_SCHEMA, build_draft_messages  # noqa: E402
from ai.providers import groq_provider  # noqa: E402

SENDER = SimpleNamespace(
    headline="Senior Frontend Engineer",
    skills="React, TypeScript, Next.js, design systems, accessibility",
    target_roles="Staff Frontend Engineer, Frontend Platform Lead",
    summary="Frontend engineer with 8 years of experience, mostly in fintech.",
    experience=(
        "Led the move of a 40-screen banking app from Angular to React. "
        "Built and maintained a design system used by 6 product teams. "
        "Cut page load time by 35% through code splitting and caching."
    ),
    writing_sample="Thanks for the quick reply. Happy to share more - the short version is that I like hard UI problems.",
)
SENDER.background = f"{SENDER.summary}\n\n{SENDER.experience}"

CASES = [
    ("connection_request", {"name": "Meera Iyer", "company": "Northwind Pay", "role": "Head of Frontend Platform"}),
    ("referral_request", {"name": "Rahul Verma", "company": "Contoso Cloud", "role": "Engineering Manager",
                          "job_title": "Staff Frontend Engineer"}),
    ("recruiter_reply", {"recruiter_name": "Ana Gomez", "company": "Fabrikam", "job_title": "Senior React Developer",
                         "interest_level": "somewhat interested"}),
    ("followup", {"name": "Li Wei", "company": "Tailspin", "role": "Product Designer",
                  "context": "Spoke after her talk on accessible forms at a design meetup", "days_since": 9}),
    ("connection_request", {"name": "Omar Haddad", "company": "Adatum", "role": "Developer Advocate"}),
]


def banned_in(text):
    lower = text.lower()
    return [p for p in BANNED_PHRASES if p.lower() in lower]


def show(label, text):
    flags = banned_in(text)
    print(f"  [{label}] {len(text)} chars" + (f"  BANNED: {flags}" if flags else ""))
    print("   " + text.replace("\n", "\n   "))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--compare", action="store_true", help="also run the original single-draft prompt")
    args = parser.parse_args()
    if not os.environ.get("GROQ_API_KEY"):
        sys.exit("Set GROQ_API_KEY. This script makes real, billed API calls.")

    for generation_type, fields in CASES:
        print(f"\n=== {generation_type}: {fields.get('name') or fields.get('recipient_name')} ===")
        messages = build_draft_messages(generation_type, fields, "friendly", "Arjun Mehta", SENDER)
        result = groq_provider.structured_chat(messages, DRAFTS_SCHEMA, "drafts")
        for i, draft in enumerate(result["drafts"], 1):
            show(f"new {i}", draft)
        if args.compare:
            old = _old_prompt(generation_type, fields)
            show("original", old)


def _old_prompt(generation_type, fields):
    background = SENDER.background
    if generation_type == "connection_request":
        return groq_provider.generate_connection_request(sender_name="Arjun Mehta", **fields)
    if generation_type == "referral_request":
        return groq_provider.generate_referral_request(your_background=background, sender_name="Arjun Mehta", **fields)
    if generation_type == "recruiter_reply":
        return groq_provider.generate_recruiter_reply(your_background=background, sender_name="Arjun Mehta", **fields)
    return groq_provider.generate_followup(sender_name="Arjun Mehta", **fields)


if __name__ == "__main__":
    main()
