import importlib
import os
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import resolve


class ProductionSettingsHardeningTests(SimpleTestCase):
    def _reload_settings(self, **env_overrides):
        environment = {
            "DJANGO_ENV": "production",
            "SECRET_KEY": "test-only-production-secret-key-for-config-validation-0123456789",
            "DEBUG": "False",
            "ALLOWED_HOSTS": "api.example.com",
            "DATABASE_URL": "",
            "DB_NAME": "prod_db",
            "DB_USER": "prod_user",
            "DB_PASSWORD": "prod_password",
            "DB_HOST": "db.example.com",
            "DB_PORT": "5432",
            "GROQ_API_KEY": "test-groq-key",
            "CORS_ALLOWED_ORIGINS": "https://connect-pilot.vercel.app",
            "CSRF_TRUSTED_ORIGINS": "https://connect-pilot.vercel.app",
        }
        environment.update(env_overrides)
        with mock.patch.dict(os.environ, environment, clear=False):
            import config.settings as settings_module
            return importlib.reload(settings_module)

    def test_invalid_environment_name_raises_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(
                DJANGO_ENV="staging",
                SECRET_KEY="a-valid-production-secret-that-is-long-enough",
                ALLOWED_HOSTS="api.example.com",
                DB_NAME="prod_db",
                DB_USER="prod_user",
                DB_PASSWORD="prod_password",
                DB_HOST="db.example.com",
            )

    def test_missing_environment_name_raises_improperly_configured(self):
        for value in ("", "   "):
            with self.subTest(DJANGO_ENV=value):
                with self.assertRaises(ImproperlyConfigured):
                    self._reload_settings(DJANGO_ENV=value)

    def test_missing_production_secret_raises_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(
                DJANGO_ENV="production",
                SECRET_KEY="",
                ALLOWED_HOSTS="api.example.com",
                DB_NAME="prod_db",
                DB_USER="prod_user",
                DB_PASSWORD="prod_password",
                DB_HOST="db.example.com",
            )

    def test_placeholder_production_secret_raises_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(
                DJANGO_ENV="production",
                SECRET_KEY="replace-with-a-strong-production-secret-of-at-least-32-characters",
                ALLOWED_HOSTS="api.example.com",
                DB_NAME="prod_db",
                DB_USER="prod_user",
                DB_PASSWORD="prod_password",
                DB_HOST="db.example.com",
            )

    def test_short_production_secret_raises_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(SECRET_KEY="too-short")

    def test_low_diversity_production_secret_raises_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(SECRET_KEY="a" * 50)

    def test_missing_production_allowed_hosts_raises_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(
                DJANGO_ENV="production",
                SECRET_KEY="a-valid-production-secret-that-is-long-enough",
                ALLOWED_HOSTS="",
                DB_NAME="prod_db",
                DB_USER="prod_user",
                DB_PASSWORD="prod_password",
                DB_HOST="db.example.com",
            )

    def test_wildcard_or_malformed_allowed_hosts_raise_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(
                DJANGO_ENV="production",
                SECRET_KEY="a-valid-production-secret-that-is-long-enough",
                ALLOWED_HOSTS="*",
                DB_NAME="prod_db",
                DB_USER="prod_user",
                DB_PASSWORD="prod_password",
                DB_HOST="db.example.com",
            )

        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(
                DJANGO_ENV="production",
                SECRET_KEY="a-valid-production-secret-that-is-long-enough",
                ALLOWED_HOSTS="bad host",
                DB_NAME="prod_db",
                DB_USER="prod_user",
                DB_PASSWORD="prod_password",
                DB_HOST="db.example.com",
            )

        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(ALLOWED_HOSTS="api.example.com:")

    def test_missing_production_database_configuration_raises_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(
                DJANGO_ENV="production",
                SECRET_KEY="a-valid-production-secret-that-is-long-enough",
                ALLOWED_HOSTS="api.example.com",
                DB_NAME="",
                DB_USER="prod_user",
                DB_PASSWORD="prod_password",
                DB_HOST="db.example.com",
            )

    def test_production_requires_explicit_false_debug(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(DEBUG="")
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(DEBUG="True")

        settings_module = self._reload_settings(DEBUG="False")
        self.assertFalse(settings_module.DEBUG)

    def test_production_requires_groq_credentials(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(GROQ_API_KEY="")

    def test_production_database_url_is_parsed_with_tls(self):
        settings_module = self._reload_settings(
            DATABASE_URL="postgresql://prod_user:encoded%40password@db.example.com:5432/prod_db"
        )
        database = settings_module.DATABASES["default"]
        self.assertEqual(database["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(database["NAME"], "prod_db")
        self.assertEqual(database["PASSWORD"], "encoded@password")
        self.assertEqual(database["OPTIONS"]["sslmode"], "require")

    def test_production_rejects_database_url_without_tls(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(
                DATABASE_URL=(
                    "postgresql://prod_user:prod_password@db.example.com/prod_db?sslmode=disable"
                )
            )

    def test_production_rejects_invalid_database_port(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload_settings(DB_PORT="70000")

    def test_local_development_uses_safe_defaults(self):
        settings_module = self._reload_settings(
            DJANGO_ENV="development",
            SECRET_KEY="",
            DEBUG="",
            ALLOWED_HOSTS="",
        )
        self.assertTrue(settings_module.DEBUG)
        self.assertIn("localhost", settings_module.ALLOWED_HOSTS)
        self.assertTrue(settings_module.SECRET_KEY)

    def test_health_endpoint_returns_only_ok_status(self):
        middleware = [
            path for path in settings.MIDDLEWARE
            if path != "whitenoise.middleware.WhiteNoiseMiddleware"
        ]
        with override_settings(MIDDLEWARE=middleware):
            response = Client().get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_cors_origin_regexes_default_to_none(self):
        settings_module = self._reload_settings(CORS_ALLOWED_ORIGIN_REGEXES="")
        self.assertEqual(settings_module.CORS_ALLOWED_ORIGIN_REGEXES, [])

    def test_cors_origin_regexes_accept_anchored_https_patterns(self):
        preview = r"^https://linkedin-copilot-frontend-[a-z0-9-]+-pk2502s-projects\.vercel\.app$"
        settings_module = self._reload_settings(CORS_ALLOWED_ORIGIN_REGEXES=f"  {preview}\n")
        self.assertEqual(settings_module.CORS_ALLOWED_ORIGIN_REGEXES, [preview])

    def test_cors_origin_regexes_reject_unsafe_patterns(self):
        for pattern in (
            r"https://app\.vercel\.app$",          # not anchored at start
            r"^https://app\.vercel\.app",          # not anchored at end
            r"^http://app\.vercel\.app$",          # not HTTPS
            r"^https://.*$",                        # unescaped dot
            r"^https://app.vercel\.app$",           # unescaped dot
            r"^https://a\.com$|evil",               # alternation escapes the anchors
            r"^https://[a-z\.com$",                 # does not compile
        ):
            with self.subTest(pattern=pattern):
                with self.assertRaises(ImproperlyConfigured):
                    self._reload_settings(CORS_ALLOWED_ORIGIN_REGEXES=pattern)

    def test_daily_limits_default_and_can_be_configured(self):
        default = self._reload_settings(GENERATE_DAILY_LIMIT="", TWEAK_DAILY_LIMIT="")
        rates = default.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertEqual((rates["generate"], rates["tweak"]), ("20/day", "40/day"))

        custom = self._reload_settings(GENERATE_DAILY_LIMIT="50", TWEAK_DAILY_LIMIT="100")
        rates = custom.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertEqual((rates["generate"], rates["tweak"]), ("50/day", "100/day"))

    def test_daily_limits_reject_invalid_values(self):
        for value in ("abc", "0", "-5"):
            with self.subTest(value=value):
                with self.assertRaises(ImproperlyConfigured):
                    self._reload_settings(GENERATE_DAILY_LIMIT=value)

    def test_existing_api_routes_remain_unchanged(self):
        route_names = {
            "/api/auth/login/": "token_obtain_pair",
            "/api/auth/refresh/": "token_refresh",
            "/api/auth/register/": "register",
            "/api/auth/me/": "me",
            "/api/generate/connection-request/": "generate_connection_request",
            "/api/history/": "generation_list",
        }
        for route, expected_name in route_names.items():
            with self.subTest(route=route):
                self.assertEqual(resolve(route).url_name, expected_name)


class DatabaseHealthCheckTests(TestCase):
    def test_returns_ok_when_database_answers(self):
        response = Client().get("/health/db/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_returns_503_without_details_when_database_fails(self):
        with mock.patch("config.views.connection") as connection:
            connection.cursor.side_effect = RuntimeError("could not connect to server: secret-host")
            with self.assertLogs("config.views", level="ERROR"):
                response = Client().get("/health/db/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotIn(b"secret-host", response.content)


class PreviewCorsTests(SimpleTestCase):
    PREVIEW = r"^https://linkedin-copilot-frontend-[a-z0-9-]+-pk2502s-projects\.vercel\.app$"

    def preflight(self, origin):
        return Client().options(
            "/api/auth/login/",
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

    def test_matching_preview_origin_is_allowed(self):
        origin = "https://linkedin-copilot-frontend-7txq3lngv-pk2502s-projects.vercel.app"
        with override_settings(CORS_ALLOWED_ORIGIN_REGEXES=[self.PREVIEW]):
            response = self.preflight(origin)
        self.assertEqual(response["Access-Control-Allow-Origin"], origin)

    def test_other_vercel_origins_are_not_allowed(self):
        with override_settings(CORS_ALLOWED_ORIGIN_REGEXES=[self.PREVIEW]):
            response = self.preflight("https://evil-pk2502s-projects.vercel.app")
        self.assertNotIn("Access-Control-Allow-Origin", response)
