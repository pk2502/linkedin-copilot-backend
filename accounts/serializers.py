from django.contrib.auth.models import User
from rest_framework import serializers

from accounts.models import Profile


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


class ProfileSerializer(serializers.ModelSerializer):
    completeness = serializers.IntegerField(read_only=True)

    class Meta:
        model = Profile
        fields = [
            "headline",
            "summary",
            "skills",
            "target_roles",
            "experience",
            "writing_sample",
            "completeness",
            "updated_at",
        ]
        read_only_fields = ["completeness", "updated_at"]
