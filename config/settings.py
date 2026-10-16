from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta
import ipaddress
import os
import re
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

_HOSTNAME_LABEL_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$')
_INSECURE_SECRET_VALUES = {
    'django-insecure-fallback',
    'dev-secret-key-change-me',
    'replace-with-a-long-random-dev-secret',
    'replace-with-a-strong-production-secret-of-at-least-32-characters',
    'change-me',
    'changeme',
    'secret',
    'example',
    'placeholder',
}


def _as_bool(value, default=False):
    if value is None or str(value).strip() == '':
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _as_csv(value, default=""):
    raw = value if value is not None else default
    return [item.strip() for item in str(raw).split(',') if item.strip()]


def _validate_host_value(host: str) -> str:
    value = host.strip()
    if not value:
        raise ImproperlyConfigured('ALLOWED_HOSTS entries cannot be empty.')
    if value == '*':
        raise ImproperlyConfigured('Production ALLOWED_HOSTS cannot contain wildcard "*".')

    if value.startswith('['):
        end = value.find(']')
        if end == -1:
            raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}')
        inner = value[1:end]
        remainder = value[end + 1:]
        if remainder:
            if not remainder.startswith(':'):
                raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}')
            port = remainder[1:]
            if not port or not port.isdigit() or not (1 <= int(port) <= 65535):
                raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}')
        try:
            ipaddress.ip_address(inner)
        except ValueError as exc:
            raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}') from exc
        return value

    if ':' in value:
        host_part, port = value.rsplit(':', 1)
        if not host_part or not port:
            raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}')
        if port and (not port.isdigit() or not (1 <= int(port) <= 65535)):
            raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}')
        value = host_part

    if '/' in value or ' ' in value:
        raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}')

    try:
        ipaddress.ip_address(value)
        return host
    except ValueError:
        pass

    if value.lower() == 'localhost':
        return host

    labels = value.split('.')
    if not labels or any(not label for label in labels):
        raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}')

    for label in labels:
        if label.startswith('-') or label.endswith('-'):
            raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}')
        if len(label) > 63 or not _HOSTNAME_LABEL_RE.fullmatch(label):
            raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}')

    if not any(ch.isalpha() for ch in value):
        raise ImproperlyConfigured(f'Malformed host entry in ALLOWED_HOSTS: {host!r}')

    return host


def _validate_production_hosts(raw_hosts):
    hosts = _as_csv(raw_hosts)
    if not hosts:
        raise ImproperlyConfigured(
            'Production requires ALLOWED_HOSTS to be configured explicitly.'
        )
    return [_validate_host_value(host) for host in hosts]


def _require_production_setting(name, value):
    if not value:
        raise ImproperlyConfigured(
            f"Production requires {name} to be configured explicitly. "
            "Set it in the environment before running Django in production."
        )


def _validate_production_secret(secret_value):
    value = secret_value.strip()
    if not value:
        raise ImproperlyConfigured('Production requires SECRET_KEY to be configured explicitly.')
    if len(value) < 50:
        raise ImproperlyConfigured(
            'Production requires SECRET_KEY to be set to a strong value with at least 50 characters.'
        )
    if len(set(value)) < 5:
        raise ImproperlyConfigured('Production SECRET_KEY must contain at least five distinct characters.')
    if value.lower() in _INSECURE_SECRET_VALUES:
        raise ImproperlyConfigured('Production SECRET_KEY uses an insecure placeholder or default value.')
    if 'replace-with' in value.lower() or 'change-me' in value.lower():
        raise ImproperlyConfigured('Production SECRET_KEY uses a placeholder value.')


def _production_database_config():
    database_url = os.environ.get('DATABASE_URL', '').strip()
    if database_url:
        try:
            parsed = urlsplit(database_url)
            port = parsed.port or 5432
        except ValueError as exc:
            raise ImproperlyConfigured('DATABASE_URL is malformed.') from exc

        if parsed.scheme not in {'postgres', 'postgresql'}:
            raise ImproperlyConfigured('DATABASE_URL must use the postgres or postgresql scheme.')

        name = unquote(parsed.path.lstrip('/'))
        user = unquote(parsed.username or '')
        password = unquote(parsed.password or '')
        host = parsed.hostname or ''
        if not all((name, user, password, host)):
            raise ImproperlyConfigured(
                'DATABASE_URL must include a database, username, password, and host.'
            )

        sslmode = parse_qs(parsed.query).get('sslmode', ['require'])[0]
        if sslmode not in {'require', 'verify-ca', 'verify-full'}:
            raise ImproperlyConfigured('Production database connections must use TLS.')

        database_config = {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': name,
            'USER': user,
            'PASSWORD': password,
            'HOST': host,
            'PORT': port,
            'OPTIONS': {'sslmode': sslmode},
        }
        if port == 6543:
            database_config['DISABLE_SERVER_SIDE_CURSORS'] = True
        return database_config

    required_db_vars = ['DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST']
    missing_db_vars = [name for name in required_db_vars if not os.environ.get(name, '').strip()]
    if missing_db_vars:
        raise ImproperlyConfigured(
            'Production requires DATABASE_URL or the following database settings: '
            + ', '.join(missing_db_vars)
        )

    database_port = os.environ.get('DB_PORT', '5432').strip() or '5432'
    if not database_port.isdigit() or not (1 <= int(database_port) <= 65535):
        raise ImproperlyConfigured('DB_PORT must be a valid TCP port.')

    database_host = os.environ['DB_HOST'].strip()
    if any(character.isspace() for character in database_host) or '/' in database_host:
        raise ImproperlyConfigured('DB_HOST is malformed.')

    database_config = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'].strip(),
        'USER': os.environ['DB_USER'].strip(),
        'PASSWORD': os.environ['DB_PASSWORD'].strip(),
        'HOST': database_host,
        'PORT': database_port,
        'OPTIONS': {'sslmode': 'require'},
    }
    if database_config['PORT'] == '6543':
        database_config['DISABLE_SERVER_SIDE_CURSORS'] = True
    return database_config


# DJANGO_ENV has no default: a deployed server that forgets to set it must fail
# at startup instead of silently running with development settings.
ENVIRONMENT = os.environ.get('DJANGO_ENV', '').strip().lower()
if not ENVIRONMENT:
    raise ImproperlyConfigured(
        "DJANGO_ENV is not set. Set DJANGO_ENV=development for local work "
        "(see .env.example) or DJANGO_ENV=production on the server."
    )
VALID_ENVIRONMENTS = {'development', 'production'}
if ENVIRONMENT not in VALID_ENVIRONMENTS:
    raise ImproperlyConfigured("DJANGO_ENV must be set to either 'development' or 'production'.")
IS_PRODUCTION = ENVIRONMENT == 'production'

if IS_PRODUCTION:
    SECRET_KEY = os.environ.get('SECRET_KEY', '').strip()
    _validate_production_secret(SECRET_KEY)
    debug_value = os.environ.get('DEBUG', '').strip().lower()
    if debug_value not in {'0', 'false', 'no', 'off'}:
        raise ImproperlyConfigured('Production requires DEBUG to be explicitly set to False.')
    DEBUG = False
    ALLOWED_HOSTS = _validate_production_hosts(os.environ.get('ALLOWED_HOSTS', ''))

    groq_api_key = os.environ.get('GROQ_API_KEY', '').strip()
    _require_production_setting('GROQ_API_KEY', groq_api_key)
    if 'replace-with' in groq_api_key.lower() or 'your-' in groq_api_key.lower():
        raise ImproperlyConfigured('Production GROQ_API_KEY uses a placeholder value.')
    DATABASES = {'default': _production_database_config()}
else:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me').strip() or 'dev-secret-key-change-me'
    DEBUG = _as_bool(os.environ.get('DEBUG', 'True'), default=True)
    ALLOWED_HOSTS = _as_csv(os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]'))
    if not ALLOWED_HOSTS:
        ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'linkedin_copilot'),
            'USER': os.environ.get('DB_USER', 'paritosh'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }

_default_origins = (
    'https://li-copilot.vercel.app'
    if IS_PRODUCTION
    else 'https://li-copilot.vercel.app,http://localhost:3000,http://127.0.0.1:3000'
)
CORS_ALLOWED_ORIGINS = _as_csv(
    os.environ.get('CORS_ALLOWED_ORIGINS', _default_origins)
)
CSRF_TRUSTED_ORIGINS = _as_csv(
    os.environ.get('CSRF_TRUSTED_ORIGINS', _default_origins)
)

SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = IS_PRODUCTION
SECURE_HSTS_SECONDS = 31536000 if IS_PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',

    # allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    # dj-rest-auth
    'dj_rest_auth',
    'dj_rest_auth.registration',

    'accounts',
    'ai',
    'generations',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10/hour",
        "user": "100/day",
        "generate": "20/day",
        "auth": "10/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

# --- Allauth ---
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID'),
            'secret': os.environ.get('GOOGLE_CLIENT_SECRET'),
            'key': '',
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'FETCH_USERINFO': True,
    }
}

REST_AUTH = {
    'USE_JWT': True,
    'JWT_AUTH_COOKIE': None,
    'JWT_AUTH_REFRESH_COOKIE': None,
    # Return the refresh token in the response body (as /api/auth/login/ does).
    # dj-rest-auth defaults to True, which strips it from the Google login
    # response and forced Google users to sign in again every 30 minutes.
    'JWT_AUTH_HTTPONLY': False,
}
