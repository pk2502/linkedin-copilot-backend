from django.contrib.auth.models import User
from django.db import models
from django.db.models import Value


class Generation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    generation_type = models.CharField(max_length=50)
    input_data = models.JSONField()
    # First (or only) draft; kept for history search and older clients.
    output = models.TextField()
    # All drafts returned for one request (3 for /api/drafts/, 1 for a tweak,
    # empty for generations made by the original endpoints).
    # db_default keeps inserts from code that predates this column working
    # while a release rolls out (migration first, then deploy).
    variants = models.JSONField(default=list, db_default=Value([], output_field=models.JSONField()), blank=True)
    # A tweak points at the draft it rewrote. Deleting that draft keeps the tweak.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="tweaks"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.generation_type} - {self.user.username}"
