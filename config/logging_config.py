def montar_logging(nivel: str) -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "padrao": {"format": "%(asctime)s %(levelname)-7s %(name)s %(message)s"},
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "padrao"},
        },
        "loggers": {
            "backoffice": {"handlers": ["console"], "level": nivel, "propagate": False},
            "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
            "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        },
        "root": {"handlers": ["console"], "level": "WARNING"},
    }
