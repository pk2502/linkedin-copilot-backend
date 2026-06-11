import os
from groq import Groq
from typing import Generator

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

TONE_INSTRUCTIONS = {
    "formal": "Use a formal, professional tone. Structured sentences, no contractions.",
    "friendly": "Use a warm, friendly tone. Conversational and approachable.",
    "concise": "Be extremely concise. Short sentences, no filler words, get to the point fast.",
}


def _get_tone_line(tone: str) -> str:
    instruction = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["friendly"])
    return f"Tone: {instruction}"


def _chat(prompt: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    return response.choices[0].message.content.strip()


def _stream_chat(prompt: str) -> Generator[str, None, None]:
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def _build_connection_prompt(name, company, role, sender_name="", tone="friendly"):
    sender_line = f"Your Name (the sender): {sender_name}" if sender_name else ""
    return f"""
Generate a professional LinkedIn connection request message.
Recipient Name: {name}
Recipient Company: {company}
Recipient Role: {role}
{sender_line}
Rules:
- Maximum 300 characters
- No emojis
- No placeholders like [Your Name]
- Write as if you are the sender reaching out
- Return only the message, nothing else
- {_get_tone_line(tone)}
"""


def _build_referral_prompt(name, company, role, job_title, your_background, sender_name="", tone="friendly"):
    sender_line = f"Your Name (the sender): {sender_name}" if sender_name else ""
    return f"""
Generate a professional LinkedIn referral request message.
Recipient Name: {name}
Recipient Company: {company}
Recipient Role: {role}
Job Title I'm applying for: {job_title}
My Background: {your_background}
{sender_line}
Rules:
- Maximum 500 characters
- No emojis
- Return only the message, nothing else
- {_get_tone_line(tone)}
"""


def _build_recruiter_prompt(recruiter_name, company, job_title, your_background, interest_level, sender_name="", tone="friendly"):
    sender_line = f"Your Name (the sender): {sender_name}" if sender_name else ""
    return f"""
Generate a professional LinkedIn reply to a recruiter message.
Recruiter Name: {recruiter_name}
Company: {company}
Job Title: {job_title}
My Background: {your_background}
My Interest Level: {interest_level}
{sender_line}
Rules:
- Maximum 500 characters
- No emojis
- Match tone to interest level
- Return only the message, nothing else
- {_get_tone_line(tone)}
"""


def _build_followup_prompt(name, company, role, context, days_since, sender_name="", tone="friendly"):
    sender_line = f"Your Name (the sender): {sender_name}" if sender_name else ""
    return f"""
Generate a professional LinkedIn follow-up message.
Recipient Name: {name}
Recipient Company: {company}
Recipient Role: {role}
Previous Interaction Context: {context}
Days Since Last Contact: {days_since}
{sender_line}
Rules:
- Maximum 400 characters
- No emojis
- Return only the message, nothing else
- {_get_tone_line(tone)}
"""


# --- Non-streaming ---

def generate_connection_request(name, company, role, sender_name="", tone="friendly"):
    return _chat(_build_connection_prompt(name, company, role, sender_name, tone))

def generate_referral_request(name, company, role, job_title, your_background, sender_name="", tone="friendly"):
    return _chat(_build_referral_prompt(name, company, role, job_title, your_background, sender_name, tone))

def generate_recruiter_reply(recruiter_name, company, job_title, your_background, interest_level, sender_name="", tone="friendly"):
    return _chat(_build_recruiter_prompt(recruiter_name, company, job_title, your_background, interest_level, sender_name, tone))

def generate_followup(name, company, role, context, days_since, sender_name="", tone="friendly"):
    return _chat(_build_followup_prompt(name, company, role, context, days_since, sender_name, tone))


# --- Streaming ---

def stream_connection_request(name, company, role, sender_name="", tone="friendly"):
    return _stream_chat(_build_connection_prompt(name, company, role, sender_name, tone))

def stream_referral_request(name, company, role, job_title, your_background, sender_name="", tone="friendly"):
    return _stream_chat(_build_referral_prompt(name, company, role, job_title, your_background, sender_name, tone))

def stream_recruiter_reply(recruiter_name, company, job_title, your_background, interest_level, sender_name="", tone="friendly"):
    return _stream_chat(_build_recruiter_prompt(recruiter_name, company, job_title, your_background, interest_level, sender_name, tone))

def stream_followup(name, company, role, context, days_since, sender_name="", tone="friendly"):
    return _stream_chat(_build_followup_prompt(name, company, role, context, days_since, sender_name, tone))
