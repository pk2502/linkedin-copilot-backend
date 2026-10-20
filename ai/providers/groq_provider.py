import json
import os
from groq import Groq
from typing import Generator

_client = None


def _get_client() -> Groq:
    """Create the Groq client on first use.

    Building it at import time made every module that imports the URL conf
    (health check, tests, management commands) fail when GROQ_API_KEY was
    absent. Production still requires the key at startup via settings.
    """
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _client


# llama-3.3-70b-versatile was shut down by Groq on 2026-08-16. Override with the
# GROQ_MODEL environment variable when Groq retires or replaces this model.
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_COMPLETION_TOKENS = 1024


def _model() -> str:
    return os.environ.get("GROQ_MODEL", "").strip() or DEFAULT_MODEL


def _completion_options(prompt: str) -> dict:
    model = _model()
    options = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
    }
    if model.startswith("openai/gpt-oss"):
        # Short outreach messages need little reasoning; keep the model's
        # reasoning out of the reply and out of the SSE stream.
        options["reasoning_effort"] = "low"
        options["include_reasoning"] = False
    return options

TONE_INSTRUCTIONS = {
    "formal": "Use a formal, professional tone. Structured sentences, no contractions.",
    "friendly": "Use a warm, friendly tone. Conversational and approachable.",
    "concise": "Be extremely concise. Short sentences, no filler words, get to the point fast.",
}


def _get_tone_line(tone: str) -> str:
    instruction = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["friendly"])
    return f"Tone: {instruction}"


def _chat(prompt: str) -> str:
    response = _get_client().chat.completions.create(**_completion_options(prompt))
    return (response.choices[0].message.content or "").strip()


def _stream_chat(prompt: str) -> Generator[str, None, None]:
    stream = _get_client().chat.completions.create(
        **_completion_options(prompt), stream=True
    )
    for chunk in stream:
        if not chunk.choices:
            continue
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


# --- Structured output (drafts and tweaks) ---

class ProviderResponseError(Exception):
    """The model answered, but not in the requested format."""


def structured_chat(messages, schema, schema_name, max_completion_tokens=1500):
    """Run a chat completion constrained to a JSON schema and return the parsed object.

    Groq supports strict structured outputs for the gpt-oss models; streaming is
    not available in this mode.
    """
    model = _model()
    options = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
    }
    if model.startswith("openai/gpt-oss"):
        options["reasoning_effort"] = "low"
        options["include_reasoning"] = False
    response = _get_client().chat.completions.create(**options)
    content = response.choices[0].message.content or ""
    try:
        return json.loads(content)
    except ValueError as exc:
        raise ProviderResponseError("Model returned invalid JSON") from exc
