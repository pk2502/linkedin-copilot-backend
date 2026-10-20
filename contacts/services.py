"""Finding and updating contacts from drafts and extension events."""
import re
from urllib.parse import urlsplit

from contacts.models import Contact

_PROFILE_PATH = re.compile(r"^/in/([^/?#]+)")


def normalize_linkedin_url(url):
    """Canonical profile URL (https://www.linkedin.com/in/<slug>/) or "" if not a profile."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return ""
    match = _PROFILE_PATH.match(parts.path)
    if not match:
        return ""
    slug = match.group(1).lower()[:200]
    return f"https://www.linkedin.com/in/{slug}/"


def _clip(value, length=150):
    return (value or "").strip()[:length]


def find_or_create(user, name, company="", role="", linkedin_url=""):
    """The user's contact for this person: matched by profile URL when known,
    otherwise by name and company. Fills in empty details; never changes status."""
    name, company, role = _clip(name), _clip(company), _clip(role)
    url = normalize_linkedin_url(linkedin_url)
    contacts = Contact.objects.filter(user=user)

    contact = contacts.filter(linkedin_url=url).first() if url else None
    if contact is None and name:
        same = contacts.filter(name__iexact=name, company__iexact=company)
        # Never merge two different profiles that share a name.
        contact = (same.filter(linkedin_url="") if url else same).first()
    if contact is None:
        if not name:
            return None
        return Contact.objects.create(user=user, name=name, company=company, role=role, linkedin_url=url)

    changed = []
    for field, value in (("name", name), ("company", company), ("role", role), ("linkedin_url", url)):
        if value and not getattr(contact, field):
            setattr(contact, field, value)
            changed.append(field)
    if changed:
        contact.save(update_fields=[*changed, "updated_at"])
    return contact


def contact_for_draft(user, generation_type, fields, linkedin_url=""):
    name = fields.get("recruiter_name") if generation_type == "recruiter_reply" else fields.get("name")
    return find_or_create(user, name, fields.get("company", ""), fields.get("role", ""), linkedin_url)


def record_event(contact, event):
    """Apply an extension event. Done contacts are left alone."""
    if contact.status == Contact.DONE:
        return contact
    if event == "sent":
        contact.mark_sent()
    elif event == "replied":
        if contact.status == Contact.REPLIED:
            return contact
        contact.mark_replied()
    contact.save()
    return contact
