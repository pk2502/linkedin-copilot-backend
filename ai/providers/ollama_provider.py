from ollama import chat


def _chat(prompt: str) -> str:
    response = chat(
        model="qwen2.5:7b",
        messages=[{"role": "user", "content": prompt}],
    )
    return response["message"]["content"].strip()


def generate_connection_request(name, company, role, sender_name=""):
    sender_line = f"Your Name (the sender): {sender_name}" if sender_name else ""
    prompt = f"""
Generate a professional LinkedIn connection request message.

Recipient Name: {name}
Recipient Company: {company}
Recipient Role: {role}
{sender_line}

Rules:
- Maximum 300 characters
- Professional and friendly
- No emojis
- No placeholders like [Your Name] — use the actual sender name if provided, otherwise omit sign-off
- Write as if you are the sender reaching out
- Return only the message, nothing else
"""
    return _chat(prompt)


def generate_referral_request(name, company, role, job_title, your_background, sender_name=""):
    sender_line = f"Your Name (the sender): {sender_name}" if sender_name else ""
    prompt = f"""
Generate a professional LinkedIn referral request message.

Recipient Name: {name}
Recipient Company: {company}
Recipient Role: {role}
Job Title I'm applying for: {job_title}
My Background: {your_background}
{sender_line}

Rules:
- Maximum 500 characters
- Professional and concise
- No emojis
- No placeholders — use actual sender name if provided
- Mention the specific job title
- Briefly highlight why I'm a good fit based on my background
- Return only the message, nothing else
"""
    return _chat(prompt)


def generate_recruiter_reply(recruiter_name, company, job_title, your_background, interest_level, sender_name=""):
    sender_line = f"Your Name (the sender): {sender_name}" if sender_name else ""
    prompt = f"""
Generate a professional LinkedIn reply to a recruiter message.

Recruiter Name: {recruiter_name}
Company: {company}
Job Title: {job_title}
My Background: {your_background}
My Interest Level: {interest_level}
{sender_line}

Rules:
- Maximum 500 characters
- Professional and warm
- No emojis
- No placeholders — use actual sender name if provided
- Match tone to interest level (enthusiastic if interested, polite if not)
- Return only the message, nothing else
"""
    return _chat(prompt)


def generate_followup(name, company, role, context, days_since, sender_name=""):
    sender_line = f"Your Name (the sender): {sender_name}" if sender_name else ""
    prompt = f"""
Generate a professional LinkedIn follow-up message.

Recipient Name: {name}
Recipient Company: {company}
Recipient Role: {role}
Previous Interaction Context: {context}
Days Since Last Contact: {days_since}
{sender_line}

Rules:
- Maximum 400 characters
- Professional and friendly
- No emojis
- No placeholders — use actual sender name if provided
- Reference the previous interaction naturally
- Return only the message, nothing else
"""
    return _chat(prompt)
