import os

from typing import Any, cast

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import (
    AllowedHostsOriginValidator,
)
from django.core.asgi import get_asgi_application


os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

django_asgi_application = get_asgi_application()

# Import after Django has initialized its application registry.
from games.routing import websocket_urlpatterns  # noqa: E402


application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(
                    cast(
                        Any,
                        websocket_urlpatterns,
                    )
                )
            )
        ),
    }
)