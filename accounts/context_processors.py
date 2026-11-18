from django.conf import settings


def auth_settings(request):
    return {'ALLOW_SIGNUP': settings.ALLOW_SIGNUP}
