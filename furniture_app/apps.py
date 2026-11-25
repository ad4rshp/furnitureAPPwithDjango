from django.apps import AppConfig


class FurnitureAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'furniture_app'

    def ready(self):
        import furniture_app.signals  # noqa: F401
