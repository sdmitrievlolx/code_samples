from django.shortcuts import render
from rest_framework import viewsets, mixins, generics, views
from shelter.models import Shelter, ShelterPost, AdoptionPost
from shelter.models import ShelterPostComment
from social.serializers.post import ShelterPostSerializer, AdoptionPostSerializer
from im.models import Message, MessageCRMSyncSerializer
from auth.models import PetuniUser, CRMPetuniUserSerializer
from rest_framework.response import Response 
from crm.permissions import CRMDjangoModelPermissions, CRMEnabledAndIsAdminPermissions
from core.pagination import JSONPaginator
from core.models import Address, Pet
from core.serializers import PetSerializer
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from social.serializers.post import PostSerializer, ClinicReviewSerializer
from social.serializers.comment import CommentSerializer
from social.models import Post, Comment, ClinicReview
from shelter.serializers.comment import ShelterPostCommentSerializer
from shelter.models import CRMShelterSerializer #TODO delete from shelter.serializers
from django.utils.translation import ugettext_lazy as _
from api.espo_api_client import EspoClientMixin, EspoAPI404Error, EspoAPIError
from shops.utils import get_object_or_none
from django.conf import settings
from rest_framework import status
from clinic.models import ClinicSchedule, CRMServiceOffer, Service, Clinic
from clinic.serializers import CRMClinicScheduleSerializer, CRMServiceOfferSerializer
from clinic.serializers import CRMClinicSerializer
from django.http import Http404
from notification.models import Notification
from django.db import IntegrityError
from django.core.exceptions import SuspiciousOperation, ObjectDoesNotExist


class UndestroyMixin():
    def undestroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.undelete()
        instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class UndeleteModelMixin(UndestroyMixin):
    def undelete(self, request, *args, **kwargs):
        return self.undestroy(request, *args, **kwargs)


class CRMSyncGenericView(UndeleteModelMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CRMDjangoModelPermissions]
    http_method_names = ['get', 'post', 'patch', 'put', 'delete', 'undelete']


class CRMBaseView(EspoClientMixin, generics.GenericAPIView):
    permission_classes = [CRMEnabledAndIsAdminPermissions]
    http_method_names = ['post']
    lookup_field = 'crm_id'

    def get_object(self):
        """
        Отдает объект или None
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Perform the lookup filtering.
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        assert lookup_url_kwarg in self.kwargs, (
            'Expected view %s to be called with a URL keyword argument '
            'named "%s". Fix your URL conf, or set the `.lookup_field` '
            'attribute on the view correctly.' %
            (self.__class__.__name__, lookup_url_kwarg)
        )

        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        queryset = queryset.filter(crm_id=self.kwargs[lookup_url_kwarg]).select_for_update()
        obj = get_object_or_none(queryset)

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)# TODO check if obj==None

        return obj

    def instance_perform_delete(self, instance):
        instance.delete()
        return True

    def save_via_pk(self, data):
        """
        Сохраняет объект по pk
        """
        pk = data.get('petuniId')
        queryset = self.get_queryset()
        try:
            instance = queryset.get(pk=pk)
            serializer = self.get_serializer(instance, data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return serializer
        except ObjectDoesNotExist:
            return None
 
    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        action = f'{self.serializer_class.Meta.model.crm_api_path}/{kwargs["crm_id"]}'
        try:
            data = self.client.request('GET', action=action)
            serializer = self.save_via_pk(data)
            if serializer is None:
                if instance is not None:
                    serializer = self.get_serializer(instance, data)
                else:
                    serializer = self.get_serializer(data=data)
                serializer.is_valid(raise_exception=True)
                serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        except EspoAPI404Error: # if status code 404 delete the instance
            if instance is not None:
                if self.instance_perform_delete(instance):
                    return Response(status=status.HTTP_204_NO_CONTENT)
            return Response(status=status.HTTP_200_OK)
        except Exception as err:
            self.client.request('PATCH', action=action,
                                params={'syncFailed': str(err)})
            raise err


class CRMContactView(CRMBaseView):
    serializer_class = CRMPetuniUserSerializer
    queryset = PetuniUser.objects.all()

    def instance_perform_delete(self, instance):
        pass
        return False


class CRMAccountScheduleView(CRMBaseView):
    serializer_class = CRMClinicScheduleSerializer
    queryset = ClinicSchedule.objects.all()


class CRMClinicServiceOfferView(CRMBaseView):
    serializer_class = CRMServiceOfferSerializer
    queryset = CRMServiceOffer.objects.all()


class CRMAccountPullView(EspoClientMixin, views.APIView):
    permission_classes = [CRMEnabledAndIsAdminPermissions]
    type_dict = {
        'Приют для животных': {
            'serializer': CRMShelterSerializer,
            'model': Shelter,
            'queryset': Shelter.objects.all(),
            'instance': None,
            'pk_field': 'shelterPetuniId',
        },
        'Ветеринарная клиника': {
            'serializer': CRMClinicSerializer,
            'model': Clinic,
            'queryset': Clinic.objects.all(),
            'instance': None,
            'pk_field': 'clinicPetuniId',
        }
    }

    def get_account_data(self, crm_id):
        """
        По Account.crm_id вернем данные запроса и список accountCategories.name
        (список имен категорий аккаунта, как они представлены в crm)
        """
        try:
            account_data = self.client.request('GET', action=f'Account/{crm_id}')
        except EspoAPI404Error as err: # Если срм ответила 404, удалим приют и клинику
            Shelter.objects.filter(crm_id=crm_id).delete()
            Clinic.objects.filter(crm_id=crm_id).delete()
            raise err
        categories_data = self.client.request('GET', action=f'Account/{crm_id}/accountCategories')['list']
        return account_data, categories_data
    
    def save_via_pk(self, data, category_name):
        pk = data.get(self.type_dict[category_name]['pk_field'])
        queryset = self.type_dict[category_name]['queryset']
        serializer_class = self.type_dict[category_name]['serializer']
        try:
            instance = queryset.get(pk=pk)
            serializer = serializer_class(instance, data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return serializer
        except ObjectDoesNotExist:
            return None
    
    @staticmethod
    def is_for_sync(account_data, category_data):
        """
        Проверка исключений, при которых синхронизация не проводится
        """
        if category_data['name'] == 'Приют для животных':
            return account_data['djangoShelter'] # and account_data['shelterApprovalStatus'] == 'Approved'
        return True

    def post(self, request, *args, **kwargs):
        crm_id = self.kwargs['crm_id']
        types = self.type_dict.copy()
        for val in types.values():
            queryset = val['queryset'].filter(crm_id=crm_id).select_for_update()
            try:
                val['instance'] = queryset.get()
            except val['model'].DoesNotExist:
                val['instance'] = None
        action = f'Account/{crm_id}'
        try:
            account_data, categories_data = self.get_account_data(crm_id)
            # self.address_restruct(account_data)
            is_category_valid = False # Проверка на наличие типа аккаунта, клиника или приют
            for category_data in categories_data:
                if not self.is_for_sync(account_data, category_data):
                    continue
                category_name = category_data['name']
                if category_name in types:
                    is_category_valid = True
                    serializer = self.save_via_pk(account_data, category_name)
                    if serializer is None:
                        serializer_class = types[category_name]['serializer']
                        if types[category_name]['instance']:
                            serializer = serializer_class(types[category_name]['instance'],
                                                        account_data)
                        else:
                            serializer = serializer_class(data=account_data)
                        serializer.is_valid(raise_exception=True)
                        serializer.save()
            if not is_category_valid: # если категория не приют и не клиника отправим репорт
                self.client.request(
                    'PATCH',
                    action=action,
                    params={'syncFailed': "account type not specified. choose clinic or shelter"}
                )
                return Response(status=status.HTTP_400_BAD_REQUEST)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except EspoAPI404Error:
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as err:
            self.client.request('PATCH', action=action, params={'syncFailed': str(err)})
            raise err
            

class CRMPetuniUserView(CRMSyncGenericView):
    serializer_class = CRMPetuniUserSerializer
    queryset = PetuniUser.objects.all()
    pagination_class = JSONPaginator
    http_method_names = ['get', 'patch', 'put']


class CRMPetuniUserWarnView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['post']
    queryset = PetuniUser.objects.all()
    serializer_class = CRMPetuniUserSerializer

    def check_permissions(self, request):
        super().check_permissions(request)
        if not request.user.has_perm('petuni_auth.change_petuniuser'):
            self.permission_denied(request, message=_("user hasn't permissions to change"))

    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        Notification.objects.create(
            user=instance,
            html=_('You are warned')
        )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class CRMShelterApproveView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['post']
    queryset = Shelter.objects.all()
    serializer_class = CRMShelterSerializer

    def check_permissions(self, request):
        super().check_permissions(request)
        if not request.user.has_perm('shelter.change_shelter'):
            self.permission_denied(request, message=_("user hasn't permissions to change"))

    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        if kwargs['action'] == 'approve':
            instance.approve()
        elif kwargs['action'] == 'reject':
            instance.reject()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class CRMPostView(CRMSyncGenericView):
    serializer_class = PostSerializer
    permission_classes = [IsAuthenticated] 

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method == 'DELETE' and not request.user.has_perm('social.delete_post'):
            self.permission_denied(request, message=_("user hasn't permissions to delete post"))
        elif request.method == 'UNDELETE' and not request.user.has_perm('social.undelete_post'):
            self.permission_denied(request, message=_("user hasn't permissions to undelete post"))
        elif ((request.method == 'PUT' or request.method == 'PATCH')
               and not request.user.has_perm('social.change_post')):
            self.permission_denied(request, message=_("user hasn't permissions to change post"))
        elif request.method == 'GET' and not request.user.has_perm('social.view_post'):
            self.permission_denied(request, message=_("user hasn't permissions to view post"))

    def get_queryset(self):
        if self.kwargs['post_type'] == 'adoptionpost':
            class_ = AdoptionPost
        elif self.kwargs['post_type'] == 'shelterpost':
            class_ = ShelterPost
        elif self.kwargs['post_type'] == 'clinicreview':
            class_ = ClinicReview
        if self.request.method == 'UNDELETE':
            return class_.all_objects.all()
        return class_.objects.all()

    def get_serializer_class(self):
        if self.kwargs['post_type'] == 'adoptionpost':
            return AdoptionPostSerializer
        if self.kwargs['post_type'] == 'shelterpost':
            return ShelterPostSerializer
        if self.kwargs['post_type'] == 'clinicreview':
            return ClinicReviewSerializer


class CRMCommentView(CRMSyncGenericView):
    serializer_class = CommentSerializer
    queryset = Comment.objects.all()
    permission_classes = [IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method == 'DELETE' and not request.user.has_perm('social.delete_comment'):
            self.permission_denied(request, message=_("user hasn't permissions to delete comment"))
        elif request.method == 'UNDELETE' and not request.user.has_perm('social.undelete_comment'):
            self.permission_denied(request, message=_("user hasn't permissions to undelete comment"))
        elif ((request.method == 'PUT' or request.method == 'PATCH')
               and not request.user.has_perm('social.change_comment')):
            self.permission_denied(request, message=_("user hasn't permissions to change comment"))
        elif request.method == 'GET' and not request.user.has_perm('social.view_comment'):
            self.permission_denied(request, message=_("user hasn't permissions to view comment"))
    
    def get_queryset(self):
        if self.kwargs['comment_type'] == 'comment':
            class_ = ShelterPostComment
        if self.request.method == 'UNDELETE':
            return class_.all_objects.all()
        return class_.objects.all()

    def get_serializer_class(self):
        if self.kwargs['comment_type'] == 'comment':
            return ShelterPostCommentSerializer


class CRMPetDeleteView(CRMSyncGenericView):
    http_method_names = ['delete']
    queryset = Pet.objects.all()
    serializer_class = PetSerializer

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method == 'DELETE' and not request.user.has_perm('core.delete_pet'):
            self.permission_denied(request, message=_("user hasn't permissions to delete pet"))
