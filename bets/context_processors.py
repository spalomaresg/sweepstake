from django.conf import settings


def web_title(request):
    return {'web_title': settings.WEB_TITLE}
