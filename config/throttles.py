from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class GenerateRateThrottle(UserRateThrottle):
    scope = "generate"


class AuthRateThrottle(AnonRateThrottle):
    scope = "auth"
