from petuni_main.celery import app
from crm.models import CRMSignalMixin
from api.espo_api_client import EspoAPIError


def get_all_subclasses(class_):
    result = {}
    for subclass in class_.__subclasses__():
        result[subclass.__name__] = subclass
        result.update(get_all_subclasses(subclass))
    return result

SUBCLASSES = get_all_subclasses(CRMSignalMixin)

@app.task(name='crm.crm_sync', autoretry_for=(EspoAPIError,), retry_backoff=True,
          retry_backoff_max=6000, max_retries=None)
def crm_sync(class_name, instance_id):
    sync_class = SUBCLASSES[class_name]
    try:
        instance = sync_class.get_queryset().get(pk=instance_id)
        instance.crm_push()
    except sync_class.DoesNotExist:
        print(f'Instance of {sync_class.__name__} with pk {instance_id} does not exist')

@app.task(name='crm.crm_sync_delete', autoretry_for=(EspoAPIError,), retry_backoff=True,
          retry_backoff_max=6000, max_retries=None)
def crm_sync_delete(instance):
    instance.crm_sync_delete()
