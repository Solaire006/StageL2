#!/usr/bin/env bash
# Run a Django management command on the server with the production settings.
# Examples:
#   sudo -u jobsapp /srv/jobsapp/app/deploy/manage.sh migrate
#   sudo -u jobsapp /srv/jobsapp/app/deploy/manage.sh createsuperuser
#   sudo -u jobsapp /srv/jobsapp/app/deploy/manage.sh check --deploy
set -euo pipefail
ENV_FILE=/etc/jobsapp/jobsapp.env
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
export DJANGO_DEBUG=0
cd /srv/jobsapp/app
exec /srv/jobsapp/venv/bin/python manage.py "$@"
