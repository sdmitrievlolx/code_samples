from rest_framework import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from rest_framework.utils import model_meta
from django.conf import settings
from core.models import Address
from api.gmaps import gmaps_client
from rest_framework.settings import api_settings


class CrmIdRelatedField(serializers.RelatedField):
    """
    Аналог PkRelatedField по полю crm_id
    """
    default_error_messages = {
        'required': _('This field is required.'),
        'does_not_exist': _('Invalid pk "{crm_id_value}" - object does not exist.'),
        'incorrect_type': _('Incorrect type. Expected pk value, received {data_type}.'),
    }

    def to_representation(self, value):
        return value.crm_id

    def to_internal_value(self, data):
        try:
            return self.get_queryset().get(crm_id=data)
        except ObjectDoesNotExist:
            self.fail('does_not_exist', crm_id_value=data)
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)


class CRMAddressSerializerMixin:
    """
    В crm используются три строковых поля для адреса:
    shippingAddressCity, shippingAddressState, shippingAddressStreet
    Данный миксин проводит проверку на наличие и заполненность этих полей и преобразует
    их во внутренний формат адреса и обратно.
    """
    def to_internal_value(self, data):
        """
        Преобразует адрес из срм в значения для AddressSerializer
        """
        if any((
            data.get('shippingAddressState', None),
            data.get('shippingAddressCity', None),
            data.get('shippingAddressStreet', None)
        )):
            city = data.get('shippingAddressCity')
            state = data.get('shippingAddressState')
            street = data.get('shippingAddressStreet')
            if state:
                address_string = f'{state}, {city}, {street}'
            else:
                address_string = f'{city}, {street}'
            data['address'] = Address.get_address_from_string(address_string)
        else:
            data['address'] = Address.get_address_from_string('Russia, Moscow')
        return super().to_internal_value(data)
        
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if hasattr(instance, 'address'):
            if instance.address.google_place_id:
                address_dict = Address.get_values_from_list(instance.address.place['address_components'])
                if address_dict.get('state'):
                    ret['shippingAddressState'] = address_dict['state']
                else:
                    ret['shippingAddressState'] = address_dict.get('city')
                ret['shippingAddressCity'] = address_dict.get('city')
                if address_dict.get('building') and address_dict.get('street'):
                    ret['shippingAddressStreet'] = f'{address_dict["street"]}, {address_dict.get("building")}'
                elif address_dict.get('street'):
                    ret['shippingAddressStreet'] = address_dict.get('street')
                else:
                    ret['shippingAddressStreet'] = address_dict.get('city')
            else:
                ret['shippingAddressState'] = instance.address.state
                if not instance.address.state:
                    ret['shippingAddressState'] = instance.address.city
                ret['shippingAddressCity'] = instance.address.city
                if instance.address.building and instance.address.street:
                    ret['shippingAddressStreet'] = f'{instance.address.street}, {instance.address.building}'
                else:
                    ret['shippingAddressStreet'] = instance.address.street
        return ret


class CRMSerializerMixin:  # TODO написать докстринги
    def create(self, validated_data):
        """
        Переписанный дефолтный метод ModelSerializer. Использует save вместо objects create
        для передачи параметра dont_sync
        """
        serializers.raise_errors_on_nested_writes('create', self, validated_data)

        ModelClass = self.Meta.model

        # Remove many-to-many relationships from validated_data.
        # They are not valid arguments to the default `.create()` method,
        # as they require that the instance has already been saved.
        info = model_meta.get_field_info(ModelClass)
        many_to_many = {}
        for field_name, relation_info in info.relations.items():
            if relation_info.to_many and (field_name in validated_data):
                many_to_many[field_name] = validated_data.pop(field_name)

        try:
            instance = ModelClass(**validated_data)
            instance.save()
        except TypeError:
            tb = serializers.traceback.format_exc()
            msg = _((
                'Got a `TypeError` when calling `%s.%s.create()`. '
                'This may be because you have a writable field on the '
                'serializer class that is not a valid argument to '
                '`%s.%s.create()`. You may need to make the field '
                'read-only, or override the %s.create() method to handle '
                'this correctly.\nOriginal exception was:\n %s')) % (
                    ModelClass.__name__,
                    ModelClass._default_manager.name,
                    ModelClass.__name__,
                    ModelClass._default_manager.name,
                    self.__class__.__name__,
                    tb
                )
            raise TypeError(msg)

        # Save many-to-many relationships after the instance is created.
        if many_to_many:
            for field_name, value in many_to_many.items():
                field = getattr(instance, field_name)
                field.set(value)

        return instance

    def update(self, instance, validated_data):
        """
        Переписанный дефолтный метод ModelSerializer. Использует save вместо objects create
        для передачи параметра dont_sync
        """
        serializers.raise_errors_on_nested_writes('update', self, validated_data)
        info = model_meta.get_field_info(instance)

        # Simply set each attribute on the instance, and then save it.
        # Note that unlike `.create()` we don't need to treat many-to-many
        # relationships as being a special case. During updates we already
        # have an instance pk for the relationships to be associated with.
        m2m_fields = []
        for attr, value in validated_data.items():
            if attr in info.relations and info.relations[attr].to_many:
                m2m_fields.append((attr, value))
            else:
                setattr(instance, attr, value)

        instance.save(dont_sync=True)

        # Note that many-to-many fields are set after updating instance.
        # Setting m2m fields triggers signals which could potentially change
        # updated instance and we do not want it to collide with .update()
        for attr, value in m2m_fields:
            field = getattr(instance, attr)
            field.set(value)

        return instance

    def to_internal_value(self, data):
        """
        Переписываем нулевые значение в пустые строки
        """

        for field in self._writable_fields:
            if isinstance(field, serializers.CharField) and field.get_value(data) is None:
                data[field.field_name] = ''
        return super().to_internal_value(data)
