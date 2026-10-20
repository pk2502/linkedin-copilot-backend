from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


class GenerateRateThrottle(UserRateThrottle):
    scope = "generate"


class TweakRateThrottle(UserRateThrottle):
    scope = "tweak"


class ProfileParseRateThrottle(UserRateThrottle):
    scope = "profile_parse"


class AuthRateThrottle(AnonRateThrottle):
    scope = "auth"


class LogoutRateThrottle(SimpleRateThrottle):
    """Per-IP limit for logout, kept apart from the login/register budget."""

    scope = "logout"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
