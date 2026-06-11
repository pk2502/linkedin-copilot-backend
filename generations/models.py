from django.db import models
from django.contrib.auth.models import User

class Generation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    generation_type = models.CharField(max_length=50)
    input_data = models.JSONField()
    output = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.generation_type} - {self.user.username}"