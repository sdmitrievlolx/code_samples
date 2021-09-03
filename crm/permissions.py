from rest_framework.permissions import DjangoModelPermissions, IsAdminUser
from django.conf import settings

class CRMDjangoModelPermissions(DjangoModelPermissions):
    """
    Расширяет дрфный DjangoModelPermissions методом undelete.
    Разрешения создаются в соответствующих моделях в Meta
    и находятся в модели django.contrib.auth.models.Permission
    """
    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': [],
        'HEAD': [],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
        'UNDELETE': ['%(app_label)s.undelete_%(model_name)s']
    } 


class CRMEnabledAndIsAdminPermissions(IsAdminUser):
    def has_permission(self, request, view):
        if settings.CRM_ENABLED:
            return super().has_permission(request, view)
        return False