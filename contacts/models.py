import datetime

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Contact(models.Model):
    """Someone the user is reaching out to, tracked from first draft to reply.

    Created and moved along automatically: a draft creates it (Drafted), the
    extension's Insert marks it Sent, and opening a conversation where they
    wrote last marks it Replied. The user can change any of it by hand.
    """

    DRAFTED = "drafted"
    SENT = "sent"
    REPLIED = "replied"
    DONE = "done"
    STATUSES = [(DRAFTED, "Drafted"), (SENT, "Sent"), (REPLIED, "Replied"), (DONE, "Done")]
    OUTCOMES = [("", "Not set"), ("positive", "Worked out"), ("negative", "Didn't work out")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=150)
    company = models.CharField(max_length=150, blank=True, default="")
    role = models.CharField(max_length=150, blank=True, default="")
    # Canonical https://www.linkedin.com/in/<slug>/ when known; empty for web drafts.
    linkedin_url = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUSES, default=DRAFTED)
    outcome = models.CharField(max_length=16, choices=OUTCOMES, blank=True, default="")
    notes = models.TextField(max_length=2000, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    follow_up_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["user", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "linkedin_url"],
                condition=~Q(linkedin_url=""),
                name="contact_unique_linkedin_url_per_user",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def follow_up_due(self) -> bool:
        return (
            self.status == self.SENT
            and self.follow_up_on is not None
            and self.follow_up_on <= timezone.localdate()
        )

    @property
    def days_since_sent(self):
        if not self.sent_at:
            return None
        return (timezone.now() - self.sent_at).days

    def mark_sent(self, now=None):
        now = now or timezone.now()
        self.status = self.SENT
        self.sent_at = now
        self.follow_up_on = timezone.localdate(now) + datetime.timedelta(days=settings.FOLLOW_UP_DAYS)

    def mark_replied(self, now=None):
        self.status = self.REPLIED
        self.replied_at = now or timezone.now()
        self.follow_up_on = None

    def mark_done(self):
        self.status = self.DONE
        self.follow_up_on = None
