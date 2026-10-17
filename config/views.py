import logging

from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_check(request):
    return JsonResponse({'status': 'ok'})


def database_health_check(request):
    """Run a trivial query. Used by the scheduled keep-alive job: it keeps the
    Supabase free project active and reports when the database is unreachable.
    Reveals nothing beyond up or down."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        logger.exception('Database health check failed')
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})
