"""Profile creation + security audit log.

Log lines are key=value so fail2ban or a log server can parse them, e.g.
  LOGIN_FAILED user="bob" ip=10.0.0.5
Passwords are never logged.
"""
import logging

from axes.helpers import get_client_ip_address
from axes.signals import user_locked_out
from django.conf import settings
from django.contrib.auth.signals import (
    user_logged_in, user_logged_out, user_login_failed)
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile

log = logging.getLogger('security')


def _ip(request):
    try:
        return (get_client_ip_address(request) if request else None) or '-'
    except Exception:  # never let logging break a login
        return '-'


def _clean(value):
    return str(value or '').replace('"', "'").replace('\n', ' ')[:150]


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    log.info('LOGIN_OK user="%s" ip=%s', _clean(user.get_username()), _ip(request))


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    name = (credentials or {}).get('username', '')
    log.warning('LOGIN_FAILED user="%s" ip=%s', _clean(name), _ip(request))


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    log.info('LOGOUT user="%s" ip=%s',
             _clean(user.get_username() if user else ''), _ip(request))


@receiver(user_locked_out)
def on_locked_out(sender, request, username=None, ip_address=None, **kwargs):
    log.error('LOCKOUT user="%s" ip=%s', _clean(username), ip_address or _ip(request))
