from unittest.mock import patch
from unittest import skip
from django.test import TestCase, TransactionTestCase, override_settings
from django.conf import settings
from shelter.tests import ShelterCreationMixin, AdoptionPostCreationMixin
from shelter.models import Shelter, AdoptionPost, ShelterPostComment
import requests
from auth.models import PetuniUser
from celery.exceptions import Retry
from im.models import Message, Chat, ChatMembership, MessageCRMSyncSerializer
from django.urls import reverse
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient
from im.tests import ChatCreateMixin
from auth.tests import UsersCreationMixin
from notification.models import Notification, NotificationAction
from report.models import PostReport, CommentReport, Comment
from api.fcm import pushes_outbox
from clinic.tests import ClinicCreationMixin
from clinic.models import Clinic
import responses
from core.models import Pet
from core.tests.mock_responses import *
from core.tests.mixins import CountryMixin
from report.models import PetReport, MessageReport
from im.tests import ChatCreateMixin


class UndeleteAPIClient(APIClient):
    def undelete(self, path, data=None, format=None, content_type=None, **extra):
        data, content_type = self._encode_data(data, format, content_type)
        return self.generic('UNDELETE', path, data, content_type, **extra)


class CRMSyncTestCase(ShelterCreationMixin, TransactionTestCase):
    @responses.activate
    @override_settings(CRM_ENABLED=True, CRM_API_KEY='kekw',
                       CRM_URL = 'https://aaa.com', CRM_SHELTER_CATEGORY='troll')
    def test_user_without_crm_id_shelter_save(self):
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True
            user = PetuniUser.objects.create(
                name='Pew',
                email='www@fff.com',
                phone=70087654321
            )
            user.crm_id = None
            request.return_value.json = lambda: {'id': 'pewpew2'}
            responses.add(
                responses.GET,
                'https://maps.googleapis.com/maps/api/place/details/json',
                status=200,
                json=GMAPS_PLACE_RESPONSE_MOSCOW_HQ                
            )            
            shelter = Shelter.objects.create(
                name = 'Shelter',
                logo=self.image_square,
                owner=user,
                address=self.address_moscow_hq,
                site_url='https://example.com',
                phone=71234567890,
                description='lorem ispum',
                legal_name='asdk asda',
                ogrn=1224455666,
                approval_status='A',
            )
            user.refresh_from_db()
            shelter.refresh_from_db()
            self.assertEqual(user.crm_id, 'pewpew')
            self.assertEqual(shelter.crm_id, 'pewpew2')

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='kekw', CRM_URL = 'https://aaa.com')
    def test_user_save_update_and_serializer(self):

        params = ('petuniId', 'firstName', 'phoneNumber', 'isActive', 'emailAddress', 'type')

        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True
            user = PetuniUser.objects.create(
                name='Pew',
                email='www@fff.com',
                phone=70007654321
            )
            user.refresh_from_db()
            self.assertEqual(user.crm_id, 'pewpew')
            args, kwargs = request.call_args
            for param in params:
                self.assertTrue(param in kwargs['json'])
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True            
            user.name = 'Wew'
            user.save()
            user.refresh_from_db()
            args, kwargs = request.call_args
            self.assertEqual(args[0], 'PATCH')
            self.assertEqual(user.name, 'Wew')
            self.assertEqual(user.crm_id, 'pewpew')
    
    def address_asserts(self, kwargs):
        self.assertEqual(kwargs['json']['shippingAddressCity'], 'Moskva')
        self.assertEqual(kwargs['json']['shippingAddressStreet'], 'Krasnaya ploshad, 2')

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='kekw',
                       CRM_URL='https://aaa.com', CRM_SHELTER_CATEGORY='troll')
    @responses.activate
    def test_shelter_save_update_and_serializer(self):
        params = ('shelterPetuniId', 'name', 'ownerId', 'ogrn', 'website', 'phoneNumber',
                'description', 'legalName', 'shelterApprovalStatus','shippingAddressCity',
                 'shippingAddressState', 'shippingAddressStreet')
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew2'}
            request.return_value.content = True
            user = PetuniUser.objects.create(
                name='Pew',
                email='www@fff.com',
                phone=70000654321
            )
            user.refresh_from_db()
        responses.add(
            responses.GET,
            'https://maps.googleapis.com/maps/api/place/details/json',
            status=200,
            json=GMAPS_PLACE_RESPONSE
        )
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True
            shelter = Shelter(
                name = 'Shelter',
                logo=self.image_square,
                owner=user,
                address=self.address_moscow_center,
                site_url='https://example.com',
                phone=71234567890,
                description='lorem ispum',
                legal_name='asdk asda',
                ogrn=1456456457,
                approval_status='A',
            )
            shelter.save()
            shelter.refresh_from_db()
            self.assertEqual(shelter.crm_id, 'pewpew')
            args, kwargs = request.call_args_list[0]
            for param in params:
                self.assertTrue(param in kwargs['json'])
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True
            shelter.refresh_from_db()
            shelter.name = 'Helter'
            shelter.save()
            args, kwargs = request.call_args_list[0]
            shelter.refresh_from_db()
            self.assertEqual(args[0], 'PATCH')
            self.assertEqual(kwargs['json']['name'], 'Helter')
            self.assertEqual(shelter.crm_id, 'pewpew')
            self.assertEqual(kwargs['json']['shippingAddressCity'], 'Moskva')
            self.assertEqual(kwargs['json']['shippingAddressStreet'], 'Krasnaya ploshad, 2')
    
    @override_settings(CRM_ENABLED=True, CRM_API_KEY='kekw',
                       CRM_URL='https://aaa.com', CRM_CLINIC_CATEGORY='patrol')
    @responses.activate
    def test_clinic_save_update_and_serializer(self):
        params = ('id', 'name', 'description', 'website', 'clinicPetuniId',
                  'isHidden', 'shippingAddressCity', 'shippingAddressState',
                  'shippingAddressStreet', 'ratingData')
        responses.add(
            responses.GET,
            'https://maps.googleapis.com/maps/api/place/details/json',
            status=200,
            json=GMAPS_PLACE_RESPONSE
        )
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True
            # проверим адрес с гугл айди
            self.address_moscow_center.google_place_id = 'ChIJc33-ZFdKtUYRcByEgKgfGuU'
            self.address_moscow_center.save()
            clinic = Clinic(
                name = 'Clinic',
                address=self.address_moscow_center,
                website='https://example.com',
                description='lorem ispum',
            )
            clinic.save()
            clinic.refresh_from_db()
            self.assertEqual(clinic.crm_id, 'pewpew')
            args, kwargs = request.call_args_list[0]
            for param in params:
                self.assertTrue(param in kwargs['json'])
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True
            clinic.refresh_from_db()
            clinic.name = 'Helter'
            clinic.save()
            args, kwargs = request.call_args_list[0]
            clinic.refresh_from_db()
            self.assertEqual(args[0], 'PATCH')
            self.assertEqual(kwargs['json']['name'], 'Helter')
            self.assertEqual(clinic.crm_id, 'pewpew')
            self.address_asserts(kwargs)
            self.assertEqual(kwargs['json']['shippingAddressCity'], 'Moskva')
            self.assertEqual(kwargs['json']['shippingAddressStreet'], 'Krasnaya ploshad, 2')

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='0f2b63a73779fb657cf56e266272955a', CRM_URL = 'https://aaa.com')
    @skip
    def test_celery_retry(self):
        """
        В случае отличного от 200 кода ответа от crm celery повторяет задачу.
        """
        with patch('requests.request') as request:
            request.return_value.status_code = 409
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True
            with self.assertRaises(Retry):
                user = PetuniUser.objects.create(
                    name='Pew',
                    email='www@fff.com',
                    phone=70987654321
                )            
        with patch('requests.request') as request:
            def raise_exception():
                raise requests.exceptions.Timeout
            request.side_effects = raise_exception
            with self.assertRaises(Retry):
                user = PetuniUser.objects.create(
                    name='Wew',
                    email='wwwa@fffa.com',
                    phone=70987654321
                )

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='0f2b63a73779fb657cf56e266272955a', CRM_URL = 'https://aaa.com')
    def test_save_message(self):
        chat = Chat.objects.create()
        params = ('post', 'parentType', 'parentId', 'type')
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True
            user = PetuniUser.objects.create(
                name='Pew',
                email='www@fff.com',
                phone=70000054321
            )
            user.refresh_from_db()
            request.return_value.json = lambda: {'id': 'pewpew2'}
            superuser = PetuniUser.objects.create_superuser(
                    username="superu",
                    email='perespimka@yandex.ru',
                    password='123456567A',
            )
        settings.SUPPORT_USER_PK = str(superuser.pk)
        try:
            cm1 = ChatMembership.objects.create(
                chat=chat,
                user=superuser
            )
            cm2 = ChatMembership.objects.create(
                chat=chat,
                user=user
            )
            with patch('requests.request') as request:
                request.return_value.status_code = 200
                request.return_value.json = lambda: {'id': 'pewpew3'}
                request.return_value.content = True
                message = Message.objects.create(
                    chat=chat,
                    author=user,
                    text='‏ni hao',
                )
                message.refresh_from_db()
                args, kwargs = request.call_args
                self.assertEqual(message.crm_id, 'pewpew3')
                # Проверим данные
                for param in params:
                    self.assertTrue(param in kwargs['json'])
            # Сообщуха от стаффа не должна синкаться
            with patch('requests.request') as request:
                request.return_value.status_code = 200
                request.return_value.json = lambda: {'id': 'pewpew4'}
                request.return_value.content = True
                message = Message.objects.create(
                    chat=chat,
                    author=superuser,
                    text='‏ni hao',
                )
                with self.assertRaises(AssertionError):
                    request.assert_called()
                self.assertFalse(message.crm_id)
            # Летит ли запрос в случае, если сообщение отправлено не стаффу
            cm1.delete()
            cm1 = ChatMembership.objects.create(
                chat=chat,
                user=self.john
            )
            with patch('requests.request') as request:
                request.return_value.status_code = 200
                request.return_value.json = lambda: {'id': 'pewpew5'}
                request.return_value.content = True
                message = Message.objects.create(
                    chat=chat,
                    author=user,
                    text='‏ni hao',
                )
                with self.assertRaises(AssertionError):
                    request.assert_called()
                self.assertFalse(message.crm_id)
        except Exception as e:
            raise e
        finally:
            settings.SUPPORT_USER_PK = None


class CRMReportsSyncTestCase(AdoptionPostCreationMixin, ChatCreateMixin, TransactionTestCase):
    @override_settings(CRM_ENABLED=True, CRM_API_KEY='0f2b63a73779faaadcf56e266272955a',
                       CRM_URL = 'https://aaa.com')
    def test_reports_crm_sync(self):
        """
        Тестируем сохранение PostReport & CommentReport
        """
        # test adoption_post report
        params = ('created', 'reportedText', 'petuniId', 'reportAuthor',
                       'contentAuthor', 'objectType', 'objectId', 'objectText', 
                       'imageURLList')
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True
            post_report = PostReport.objects.create(
                reported_object=self.adoption_post1,
                author=self.bob,
                text='wtf bruh'
            )
            post_report.refresh_from_db()
            # Проверим, создается ли нотификация
            self.assertTrue(Notification.objects.filter(
                                user=self.bob,
                                html='Ваша жалоба принята на рассмотрение администратором Петюни'
                            ).exists())
            args, kwargs = request.call_args
            self.assertEqual(post_report.crm_id, 'pewpew')
            for param in params:
                self.assertTrue(param in kwargs['json'].keys())
            self.assertEqual(kwargs['json']['objectText'], 
                             f'{self.adoption_post1.name}\n{self.adoption_post1.text}')
            self.assertEqual(kwargs['json']['objectType'], 'adoptionpost')
        #test image urls @ shelterpost
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew2'}
            request.return_value.content = True
            post_report = PostReport.objects.create(
                reported_object=self.shelter_post,
                author=self.bob,
                text='psss'
            )
            post_report.refresh_from_db()
            self.assertEqual(post_report.crm_id, 'pewpew2')
            args, kwargs = request.call_args
            self.assertEqual(len(kwargs['json']['imageURLList']), 2)
            self.assertEqual(kwargs['json']['objectType'], 'shelterpost')
            pic_url = self.shelter_post.images.last().pk
            self.assertIn(
                str(pic_url),
                kwargs['json']['imageURLList'][0]
            )

        # test comment sync
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew3'}
            request.return_value.content = True
            comment = Comment.objects.create(
                author=self.john,
                text='fu bitch',
            )
            comment.images.add(self.image)
            request.return_value.json = lambda: {'id': 'pewpew4'}
            comment_report = CommentReport.objects.create(
                reported_object=comment,
                author=self.bob,
                text='oioioi'
            )
            comment_report.refresh_from_db()
            args, kwargs = request.call_args
            for param in params:
                self.assertTrue(param in kwargs['json'])
            self.assertEqual(comment_report.crm_id, 'pewpew4')
            self.assertEqual(len(kwargs['json']['imageURLList']), 2)
            pic_url = comment.images.last().pk
            self.assertEqual(kwargs['json']['objectType'], 'comment')
            self.assertEqual(kwargs['json']['objectId'], str(comment.pk))
            self.assertIn(
                str(pic_url),
                kwargs['json']['imageURLList'][0]
            )
    
    @responses.activate
    @override_settings(CRM_ENABLED=True, CRM_API_KEY='0f2b63a73779faaadcf56e266272955a',
                       CRM_URL = 'https://aaa.com')
    def test_pet_report_sync(self):
        responses.add(
            responses.POST,
            'https://aaa.com/api/v1/PetuniReport',
            status=200,
            json={'id': 'add23'}
        )
        responses.add(
            responses.POST,
            'https://aaa.com/api/v1/Contact',
            status=200,
            json={'id': '55555'}
        )
        pet_report = PetReport.objects.create(reported_object=self.bob_dog, author=self.john)
        pet_report.refresh_from_db()
        self.assertEqual(pet_report.crm_id, 'add23')
        delete_pet_permission = Permission.objects.get(
            content_type__app_label='core',
            content_type__model='pet',
            codename='delete_pet'
        )
        new_user = PetuniUser.objects.create(
            name='new_user',
            phone=79261236549,
            email='vzhuuuh@puuh.com'
        )
        new_user.user_permissions.add(
            delete_pet_permission
        )
        new_user_client = APIClient()
        new_user_client.force_authenticate(user=new_user)
        pk = self.bob_dog.pk
        url = reverse('crm:pet-delete', kwargs={'pk': pk})
        response = new_user_client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Pet.objects.filter(pk=pk).exists())
        response = new_user_client.delete(url)
        self.assertEqual(response.status_code, 404)
        response = new_user_client.post(url)
        self.assertEqual(response.status_code, 403)

    @responses.activate
    @override_settings(CRM_ENABLED=True, CRM_API_KEY='0f2b63a73779faaadcf56e266272955a',
                       CRM_URL = 'https://aaa.com')
    def test_message_report(self):        
        responses.add(
            responses.POST,
            'https://aaa.com/api/v1/PetuniReport',
            status=200,
            json={'id': 'add23'}
        )
        responses.add(
            responses.POST,
            'https://aaa.com/api/v1/Contact',
            status=200,
            json={'id': '55555'}
        )
        message = MessageReport.objects.create(
            reported_object=self.message_first,
            author=self.john,
            text='sdfsdfds'
        )
        message.refresh_from_db()
        self.assertEqual(message.crm_id, 'add23')


class CRMPetuniUserViewSetTestCase(UsersCreationMixin, TestCase):
    def test_request_and_permission(self):
        change_user_permission = Permission.objects.get(
            content_type__app_label='petuni_auth',
            content_type__model='petuniuser',
            codename='change_petuniuser'
        )
        add_user_permission = Permission.objects.get(
            content_type__app_label='petuni_auth',
            content_type__model='petuniuser',
            codename='add_petuniuser'
        )
        new_user = PetuniUser.objects.create(
            name='new_user',
            phone=79261236549,
            email='vzhuuuh@puuh.com'
        )
        new_user.user_permissions.add(
            change_user_permission,
            add_user_permission
        )
        self.assertTrue(new_user.has_perm('petuni_auth.change_petuniuser'))
        self.assertTrue(new_user.has_perm('petuni_auth.add_petuniuser'))
        new_user_client = APIClient()
        new_user_client.force_authenticate(user=new_user)
        # warning test
        before_count = self.user.notification_counter
        response = new_user_client.post(reverse('crm:user-warn',
                                                kwargs={'pk': self.user.pk}))
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.notification_counter, before_count+1)
        response = self.client.post(reverse('crm:user-warn',
                                                kwargs={'pk': self.user.pk}))
        self.assertEqual(response.status_code, 403)
        response = self.john_client.post(reverse('crm:user-warn',
                                                kwargs={'pk': self.user.pk}))
        self.assertEqual(response.status_code, 403)

class CRMContactViewTestCase(UsersCreationMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('crm:contact', kwargs={'crm_id': '12345678901234567'})
        self.bob.crm_id = '12345678901234567'
        self.bob.save()
        self.john.is_superuser = True
        self.john.is_staff = True
        self.john.save()
        self.response_data = {
            'id': '12345678901234567',
            'petuniId': self.bob.pk,
            'firstName': 'bobah',
            'isActive': True,
            'phoneNumber': 72282282280,
            'emailAddress': 'example@example.com',
            'type': ['aaa', 'bbb'], # не сохраняем в модельку
            'isResponsible': True, # не сохраняем в модельку
            'createdAt': '2020-10-20T05:50',
            'modifiedAt': '2020-10-20T05:50',
        }

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='0f2b63a73779fb657cf56e266272955a',
                       CRM_URL = 'https://aaa.com')
    def test_update(self):
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: self.response_data
            request.return_value.content = True
            response = self.john_client.post(self.url)
            self.assertEqual(response.status_code, 200)
            self.bob.refresh_from_db()
            self.assertEqual(self.bob.name, 'bobah')

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='0f2b63a73779fb657cf56e266272955a',
                       CRM_URL = 'https://aaa.com')
    def test_create(self):
        new_url = reverse('crm:contact', kwargs={'crm_id': '09876543211234567'})
        self.response_data['id'] = '09876543211234567'
        self.response_data['petuniId'] = None
        users_count = PetuniUser.objects.count()
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: self.response_data
            request.return_value.content = True
            response = self.john_client.post(new_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(users_count + 1, PetuniUser.objects.count())
            self.assertTrue(PetuniUser.objects.filter(crm_id='09876543211234567').exists())

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='0f2b63a73779fb657cf56e266272955a',
                       CRM_URL = 'https://aaa.com')
    def test_delete_do_nothing(self):
        with patch('requests.request') as request:
            bob_pk = self.bob.pk
            request.return_value.status_code = 404
            request.return_value.json = lambda: self.response_data
            request.return_value.content = True
            response = self.john_client.post(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(PetuniUser.objects.filter(pk=bob_pk).exists())      
    

class CRMShelterApproveViewTestCase(ShelterCreationMixin, TransactionTestCase):
    @override_settings(CRM_ENABLED=True, SUPPORT_USER_PK='support-uuid',
                       CRM_API_KEY='zzz',
                       CRM_URL = 'https://aaa',
                       CRM_SHELTER_CATEGORY='troll')

    @responses.activate                   
    def test_permissions_and_request_methods(self):
        with patch('requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.json = lambda: {'id': 'pewpew'}
            request.return_value.content = True
            change_shelter_permission = Permission.objects.get(
                content_type__app_label='shelter',
                content_type__model='shelter',
                codename='change_shelter'
            )
            new_user = PetuniUser.objects.create(
                name='new_user',
                phone=79261236549,
                email='vzhuuuh@puuh.com'
            )
            new_user.user_permissions.add(
                change_shelter_permission,
                )
            self.assertTrue(new_user.has_perm('shelter.change_shelter'))
            new_user_client = UndeleteAPIClient()
            new_user_client.force_authenticate(user=new_user)
            # approval_status switch
            responses.add(
                responses.GET,
                'https://maps.googleapis.com/maps/api/place/details/json',
                status=200,
                json=GMAPS_PLACE_RESPONSE_MOSCOW_HQ                
            )
            request.return_value.json = lambda: {'id': 'pewpew1'}
            self.shelter.approval_status = 'N'
            self.shelter.save()
            pushes_outbox.clear()
            response = new_user_client.post(
                reverse(
                    'crm:shelter-registration-request',
                    kwargs={
                        'pk': self.shelter.pk,
                        'action': 'approve'
                    }
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(pushes_outbox[0].notification.title, 'Запрос одобрен')
            notification = Notification.objects.get(user=self.john)
            self.assertTrue(notification.html.endswith('одобрен'))
            notification.delete()
            self.shelter.refresh_from_db()
            self.assertTrue(self.shelter.is_approved)
            self.shelter.approval_status = 'N'
            self.shelter.save()
            pushes_outbox.clear()
            response = new_user_client.post(
                reverse(
                    'crm:shelter-registration-request',
                    kwargs={
                        'pk': self.shelter.pk,
                        'action': 'reject'
                    }
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(pushes_outbox[0].notification.title, 'Запрос отклонен')
            notification = Notification.objects.get(user=self.john)
            self.assertTrue(notification.html.endswith('обращайтесь в службу поддержки'))
            # Кнопка обращения в саппорт не должна создасться, если не указан сотрудник саппорта
            if settings.SUPPORT_USER_PK is None:
                self.assertFalse(NotificationAction.objects.filter(notification=notification).exists())
            self.assertFalse(self.shelter.is_approved)
            # Проверим с созданным саппорт юзером
            notification.delete()
            request.return_value.json = lambda: {'id': 'pewpew2'}
            superuser = PetuniUser.objects.create_superuser(
                    username="superuu",
                    email='perespimka1@yandex.ru',
                    password='123456567A',
            )
            settings.SUPPORT_USER_PK = str(superuser.pk)
            self.shelter.approval_status = 'N'
            self.shelter.save()        
            self.shelter.refresh_from_db()
            pushes_outbox.clear()
            response = new_user_client.post(
                reverse(
                    'crm:shelter-registration-request',
                    kwargs={
                        'pk': self.shelter.pk,
                        'action': 'reject'
                    }
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(pushes_outbox[0].notification.title, 'Запрос отклонен')
            notification = Notification.objects.get(user=self.john)
            self.assertTrue(notification.html.endswith('обращайтесь в службу поддержки'))
            self.assertTrue(NotificationAction.objects.filter(notification=notification).exists())


class CRMAccountPullViewTestCase(ShelterCreationMixin, CountryMixin, ClinicCreationMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.account_crm_id = '5fd8d943595116918'
        self.url = reverse('crm:account-pull', kwargs={'crm_id': self.account_crm_id})
        self.bob.crm_id = 'okthxbye'
        self.bob.save()
        self.john.is_superuser = True
        self.john.is_staff = True
        self.john.save()
        self.response_data = {
            'id': self.account_crm_id,
            'name': 'КривоХвост',
            'phoneNumber': 79225556663,
            'website': 'ppl.com',
            'emailAddress': None,
            'shippingAddressStreet': 'Солнцевский проспект, 6',
            'shippingAddressCity': 'Москва',
            'shippingAddressState': 'Москва',
            'description': 'ффывфыв  sdfsdf',
            'isHidden': False,
            'shelterPetuniId': None,
            'clinicPetuniId': None,
            'djangoShelter': False,
            'legalName': 'loloe',
            'ownerId': self.bob.crm_id,
            'list': [
                {
                    'name': 'Приют для животных'
                },
                {
                    'name': 'Ветеринарная клиника'
                }
            ]
        }

    @responses.activate
    def crm_account_request_mock(self, response_data, geocoding_resp=GMAPS_GEOCODING_RESPONSE,
                                place_resp=GMAPS_PLACE_RESPONSE, status_code=200):
        """
        Мокаем запрос в срм сущности Account
        """
        responses.add(
            responses.GET,
            'https://maps.googleapis.com/maps/api/geocode/json',
            json=geocoding_resp,
            status=200,
        )
        responses.add(
            responses.GET,
            'https://maps.googleapis.com/maps/api/place/details/json',
            status=200,
            json=place_resp
        )  
        with patch('requests.request') as request:
            request.return_value.status_code = status_code
            request.return_value.json = lambda: response_data
            request.return_value.content = True

            return self.john_client.post(self.url)
        self.assertEqual(len(responses.calls), 2)

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='omgwtf', CRM_URL = 'https://aaa.com')
    def test_address_serialization_wo_address_fields(self):
        self.response_data.pop('shippingAddressState')
        response = self.crm_account_request_mock(self.response_data)
        self.assertEqual(response.status_code, 200)
        self.response_data.pop('shippingAddressCity')
        response = self.crm_account_request_mock(self.response_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['shippingAddressCity'], 'Moskva')
        self.response_data['shippingAddressCity'] = 'Москва'
        self.response_data.pop('shippingAddressStreet')
        response = self.crm_account_request_mock(self.response_data)
        self.assertEqual(response.status_code, 200)

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='omgwtf', CRM_URL = 'https://aaa.com')
    def test_geocode_returns_empty_list(self):
        response = self.crm_account_request_mock(self.response_data, geocoding_resp={'status': 'ZERO_RESULTS'})
        self.assertEqual(response.status_code, 400)

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='omgwtf', CRM_URL = 'https://aaa.com')
    def test_account_sync_without_shelter(self):
        response = self.crm_account_request_mock(self.response_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Clinic.objects.filter(crm_id=self.account_crm_id).exists()
        )
        self.assertFalse(
            Shelter.objects.filter(crm_id=self.account_crm_id).exists()
        )
        clinic = Clinic.objects.get(crm_id=self.account_crm_id)
        self.assertEqual(clinic.address.google_place_id, "ChIJc33-ZFdKtUYRcByEgKgfGuU")
        self.assertEqual

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='omgwtf', CRM_URL = 'https://aaa.com')
    def test_account_sync_with_shelter(self):
        self.response_data['djangoShelter'] = True
        self.shelter_spb.approval_status = 'R'
        self.shelter_spb.save()
        self.shelter_spb.delete()
        response = self.crm_account_request_mock(self.response_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Clinic.objects.filter(crm_id=self.account_crm_id).exists()
        )
        self.assertTrue(
            Shelter.objects.filter(crm_id=self.account_crm_id).exists()
        )
        # test address save
        clinic = Clinic.objects.get(crm_id=self.account_crm_id)
        shelter = Shelter.objects.get(crm_id=self.account_crm_id)
        self.assertEqual(clinic.address.google_place_id, "ChIJc33-ZFdKtUYRcByEgKgfGuU")
        self.assertEqual(shelter.address.google_place_id, "ChIJc33-ZFdKtUYRcByEgKgfGuU")
        self.assertEqual(clinic.address.user_input_point.x, 37.621114)
        self.assertEqual(shelter.address.user_input_point.x, 37.621114)

    
    def test_not_ok_gmaps_response(self):
        self.response_data['djangoShelter'] = True
        self.shelter_spb.approval_status = 'R'
        self.shelter_spb.save()
        self.shelter_spb.delete()
        response = self.crm_account_request_mock(self.response_data)



    @override_settings(CRM_ENABLED=True, CRM_API_KEY='omgwtf', CRM_URL = 'https://aaa.com')
    def test_not_staff_user_account_request(self):
        self.john.is_superuser = False
        self.john.is_staff = False
        self.john.save()
        response = self.crm_account_request_mock(self.response_data)
        self.assertEqual(response.status_code, 403)

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='omgwtf', CRM_URL = 'https://aaa.com')
    def test_wrong_owner(self):
        self.response_data['djangoShelter'] = True
        self.response_data['list'] = [
                {
                    'name': 'Приют для животных'
                },
            ]
        self.shelter_spb.approval_status = 'R'
        self.response_data['ownerId'] = 'blobloololo'
        response = self.crm_account_request_mock(self.response_data)
        self.assertEqual(response.status_code, 400)

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='omgwtf', CRM_URL = 'https://aaa.com')
    def test_no_categories(self):
        self.response_data['list'] = []
        response = self.crm_account_request_mock(self.response_data)
        self.assertEqual(response.status_code, 400)

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='omgwtf', CRM_URL = 'https://aaa.com')
    def test_wrong_category(self):
        self.response_data['list'] = [
            {
                'name': 'Свиноферма',
            }
        ]
        response = self.crm_account_request_mock(self.response_data)
        self.assertEqual(response.status_code, 400)

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='omgwtf', CRM_URL = 'https://aaa.com')
    def test_update_without_crm_id(self):
        """
        Проверка синка по петюни айди для случаев, когда crm_id не успел сохранится в джанго.
        """
        self.response_data['djangoShelter'] = True
        self.response_data['list'] = [
                {
                    'name': 'Приют для животных'
                },
        ]
        self.response_data['shelterPetuniId'] = self.shelter_spb.pk
        response = self.crm_account_request_mock(self.response_data)
        self.assertEqual(response.status_code, 200)
        self.shelter_spb.refresh_from_db()
        self.assertEqual(self.shelter_spb.name, 'КривоХвост')

    @override_settings(CRM_ENABLED=True, CRM_API_KEY='omgwtf', CRM_URL = 'https://aaa.com')
    def test_delete(self):
        self.response_data['djangoShelter'] = True
        self.response_data['list'] = [
                {
                    'name': 'Приют для животных'
                },
        ]
        self.response_data['shelterPetuniId'] = self.shelter_spb.pk
        response = self.crm_account_request_mock(self.response_data, status_code=404)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Shelter.objects.filter(crm_id=self.account_crm_id).exists())

