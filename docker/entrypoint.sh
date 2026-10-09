#!/bin/sh
set -e

if [ "$1" != "serve" ]; then
  exec "$@"
fi

python manage.py migrate --noinput
python manage.py criar_perfis

if [ "$BACKOFFICE_SEED" = "1" ]; then
  python manage.py seed_demo
fi

if [ "$DJANGO_DEBUG" = "1" ]; then
  exec python manage.py runserver 0.0.0.0:8000
fi

python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --access-logfile -
