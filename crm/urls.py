from django.urls import path, re_path, register_converter
from .views import *
from core.routers import PetuniRouter
from .converters import CRMIdConverter


app_name = 'crm'
register_converter(CRMIdConverter, 'crmid')
router = PetuniRouter()

urlpatterns = [
    path('contact/<crmid:crm_id>/pull/', CRMContactView.as_view(), name='contact'),
    path('account/<crmid:crm_id>/pull/', CRMAccountPullView.as_view(), name='account-pull'),
    path('account-schedule/<crmid:crm_id>/pull/', CRMAccountScheduleView.as_view(),
         name='account_schedule'),
    path('clinic-service-offer/<crmid:crm_id>/pull/', CRMClinicServiceOfferView.as_view(),
         name='clinic_service_offer'),
    path('user/<uuid:pk>/', CRMPetuniUserView.as_view(), name='user-detail'),
    path('user/<uuid:pk>/warn/', CRMPetuniUserWarnView.as_view(), name='user-warn'),
    re_path(r'shelter/(?P<pk>[0-9a-f-]+)/registration-request-(?P<action>(approve)|(reject))/$',
        CRMShelterApproveView.as_view(), name='shelter-registration-request'),
    re_path(r'(?P<post_type>(adoptionpost)|(shelterpost)|(clinicreview))/(?P<pk>[0-9a-f-]+)/$',
        CRMPostView.as_view(), name='post_delete'),
    re_path(r'(?P<comment_type>(comment))/(?P<pk>[0-9a-f-]+)/$',
        CRMCommentView.as_view(), name='comment-detail'),
    path('pet/<uuid:pk>/', CRMPetDeleteView.as_view(), name='pet-delete'),
]
urlpatterns += router.urls
