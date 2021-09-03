from django.db import models, transaction
from django.dispatch import receiver
from django.db.models.signals import post_delete
from api.espo_api_client import EspoClientMixin
from django.conf import settings
from petuni_main.celery import app


CRM_DO_NOTHING = 0
CRM_SOFT_DELETE = 1
CRM_TRUE_DELETE = 2


class CRMSignalMixin(EspoClientMixin, models.Model):
    crm_id = models.CharField(max_length=18, null=True, blank=True, unique=True)
    crm_api_path = None
    serializer_class = None
    request_type = None
    queryset = None
    sync_delete = CRM_DO_NOTHING # 0 не делаем ничего, 1 - шлем PATCH, 2 - шлем DELETE

    
    def get_crm_api_action(self):
        """
        Возвращает action для запроса EspoApi
        """
        assert self.crm_api_path is not None, f'crm_api_path for {self.__class__.__name__} is undefined'
        if self.crm_id:
            return f'{self.crm_api_path}/{self.crm_id}'
        return self.crm_api_path
    
    @classmethod
    def get_queryset(cls):
        if cls.queryset is None:
            return cls.objects.all()
        return cls.queryset

    @classmethod
    def get_crm_serializer_class(cls):
        """
        Возвращает сериализатор для запроса EspoApi
        """
        assert cls.serializer_class is not None, f'serializer for {cls.__name__} is undefined'
        return cls.serializer_class

    def get_request_type(self):
        """
        Возвращает method для запроса EspoApi
        """
        if self.crm_id:
            return 'PATCH'
        return 'POST'

    def get_sync_delete(self):
        """
        Если sync_delete == True, будет отправлена таска на удаление в crm,
        иначе обновление (для неудаляемых записей с safe-delete)
        """
        assert self.sync_delete is not None, f'sync_delete for {self.__class__.__name__} is undefined'
        return self.sync_delete

    def crm_sync_delete(self):
        """
        Синхронизация удаления
        """
        method = 'DELETE'
        data = {}
        action = self.get_crm_api_action()
        response = self.client.request(method, action, data)

    def send_espo_request(self, *args, **kwargs):
        """
        Синхронизация сохранения модели с crm
        """
        queryset = self.get_queryset()
        queryset = queryset.select_for_update()
        with transaction.atomic():
            instance = queryset.get(pk=self.pk) # TODO теперь мы берем инстанс в самой таске.
                                                # можно переделать через селф
            serializer_ = instance.get_crm_serializer_class()
            data = serializer_(instance).data
            data['skipDuplicateCheck'] = True
            method = instance.get_request_type()
            action = instance.get_crm_api_action()
            response = self.client.request(method, action, data)
            if not instance.crm_id:
                instance.crm_id = response.get('id')
                instance.save(*args, dont_sync=True, **kwargs)
    
    def crm_request_related_link(self, category_id, link):
        """
        Для создания связи между сущностями в срм. link - имя сущности,
        category_id - айди записи этой сущности.
        """
        self.refresh_from_db()
        assert self.crm_id is not None, "impossible to relate without crm_id"
        params = {'id': category_id}
        action = self.get_crm_api_action()
        link_action = f'{action}/{link}'
        self.client.request('POST', link_action, params=params)        

    def crm_push(self, *args, **kwargs):
        """
        Вызов синхронизации с crm
        """
        self.send_espo_request(*args, **kwargs)

    def save(self, *args, **kwargs):
        dont_sync = kwargs.pop('dont_sync', False)
        with transaction.atomic():
            super().save(*args, **kwargs)
            if (dont_sync != True and settings.CRM_ENABLED and
                             self.get_queryset().filter(pk=self.pk).exists()):
                s = app.signature(
                    'crm.crm_sync',
                    kwargs={
                        'instance_id': self.pk,
                        'class_name': self.__class__.__name__
                    }
                )
                transaction.on_commit(lambda: s.apply_async())

    class Meta:
        abstract = True


@receiver(post_delete)
def crm_sync_delete(sender, instance, **kwargs):
    if isinstance(instance, CRMSignalMixin) and instance.sync_delete == CRM_TRUE_DELETE:
        with transaction.atomic():
            s = app.signature(
                    'crm.crm_sync_delete',
                    kwargs={
                        'instance': instance
                    }       
            )
            transaction.on_commit(lambda:s.apply_async())