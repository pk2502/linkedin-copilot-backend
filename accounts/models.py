from django.conf import settings
from django.db import models


class Profile(models.Model):
    """What the user tells us about themselves, used to personalise every draft.

    All fields are optional free text; nothing is fetched from LinkedIn.
    """

    LIMITS = {
        "headline": 150,
        "summary": 1500,
        "skills": 500,
        "target_roles": 300,
        "experience": 4000,
        "writing_sample": 1500,
    }

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    headline = models.CharField(max_length=LIMITS["headline"], blank=True, default="")
    summary = models.TextField(max_length=LIMITS["summary"], blank=True, default="")
    skills = models.CharField(max_length=LIMITS["skills"], blank=True, default="")
    target_roles = models.CharField(max_length=LIMITS["target_roles"], blank=True, default="")
    experience = models.TextField(max_length=LIMITS["experience"], blank=True, default="")
    writing_sample = models.TextField(max_length=LIMITS["writing_sample"], blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    # Rough weights for the completeness meter: the fields that most improve
    # drafts count most.
    WEIGHTS = {
        "headline": 15,
        "summary": 20,
        "skills": 10,
        "target_roles": 10,
        "experience": 30,
        "writing_sample": 15,
    }

    @property
    def completeness(self) -> int:
        return sum(weight for field, weight in self.WEIGHTS.items() if getattr(self, field).strip())

    @property
    def background(self) -> str:
        """The sender's background as one text block for prompts."""
        parts = [self.summary.strip(), self.experience.strip()]
        return "\n\n".join(p for p in parts if p)

    def __str__(self):
        return f"Profile of {self.user}"
