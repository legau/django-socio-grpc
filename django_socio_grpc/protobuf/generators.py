import io
from collections import OrderedDict

from django.db import models
from rest_framework.utils import model_meta
from rest_framework.utils.field_mapping import ClassLookupDict


class ModelProtoGenerator:
    type_mapping = {
        # Numeric
        models.AutoField: 'int32',
        models.SmallIntegerField: 'int32',
        models.IntegerField: 'int32',
        models.BigIntegerField: 'int64',
        models.PositiveSmallIntegerField: 'int32',
        models.PositiveIntegerField: 'int32',
        models.FloatField: 'float',
        models.DecimalField: 'string',
        # Boolean
        models.BooleanField: 'bool',
        models.NullBooleanField: 'bool',
        # Date and time
        models.DateField: 'string',
        models.TimeField: 'string',
        models.DateTimeField: 'string',
        models.DurationField: 'string',
        # String
        models.CharField: 'string',
        models.TextField: 'string',
        models.EmailField: 'string',
        models.SlugField: 'string',
        models.URLField: 'string',
        models.UUIDField: 'string',
        models.GenericIPAddressField: 'string',
        models.FilePathField: 'string',
        # Default
        models.Field: 'string',
    }
    

    def __init__(self, model, field_names=None, package=None, filepath=None):
        """
        Check init paramaters
        """
        from utils.utils import getAppList
        
        self.fieldsReference = []
        self.dataBaseObject  = None
        self.model           = model
        self.field_names     = field_names
        self.filepath        = filepath
        if not package:
            package = model.__name__.lower()
        self.package = package
        self.type_mapping = ClassLookupDict(self.type_mapping)
        
        # -----------------------------------------------------
        # -- check if Package name exist in Django app List ---
        # -----------------------------------------------------
        self._status = True
        self._message = ''
        dicApp = getAppList(mode='dic')
        if not package in dicApp:
            self._status = False
            self._message =  "Invalid Django Package %s" % package
        
        # -------------------------------------------------------------------
        # Retrieve metadata about fields & relationships on the model class.
        # -------------------------------------------------------------------
        self.field_info = model_meta.get_field_info(model)
        self._writer = _CodeWriter()
        
    def status_proto(self):
        return self._status

    def message_proto(self):
        return self._message
        

    def get_proto(self):
        """
        Generator the protobuf file
        """
        from django_grpc_framework.models import grcpDataBases, grcpProtoBuf, grcpProtoBufFields
        from utils.utils import getModel, getAppList
        
        self._writer.write_line('syntax = "proto3";')
        self._writer.write_line('')
        self._writer.write_line('package %s;' % self.package)
        self._writer.write_line('')
        self._writer.write_line('import "google/protobuf/empty.proto";')
        self._writer.write_line('')
        self._generate_service()
        self._writer.write_line('')
        self._generate_message()
        
        # -------------------------------------------
        # ---- store in Proto Database            ---
        # -------------------------------------------
        if self.status_proto():
            modelClass     = self.model.__name__
            # ---------------------------------
            # ---  Database Record          --- 
            dataBaseObject = grcpDataBases.objects.filter(django=self.package, database=modelClass)
            if not dataBaseObject:
                dataBaseObject = grcpDataBases.objects.create(django=self.package, database=modelClass)
            else:
                dataBaseObject = dataBaseObject[0]
            # ----------------------------
            # --- protoBuf Record      --- 
            protoObjects   = grcpProtoBuf.objects.filter(protobuf='%s.proto' % self.package, service=dataBaseObject)
            if not protoObjects:
                protoObjects = grcpProtoBuf.objects.create(protobuf='%s.proto' % self.package, service=dataBaseObject, file=self.filepath)
            else:
                protoObjects = protoObjects[0]
            # --------------------------------
            # --- ProtoBuf Field reference ---
            if protoObjects:
                protoFieldsObject = grcpProtoBufFields.objects.filter(protobuf=protoObjects)
                if protoFieldsObject:
                    protoFieldsObject.delete()
                ctrField = 0
                for eachField in self.fieldsReference:
                    ctrField += 1
                    (fieldName, fieldType) = eachField
                    protoFieldsObject = grcpProtoBufFields.objects.create(
                        database       = dataBaseObject,    
                        protobuf       = protoObjects,  
                        field          = fieldName,
                        is_query       = False,
                        field_sequence = ctrField,
                        query_sequence = 1,
                    )
        
        return self._writer.get_code()

    def _generate_service(self):
        self._writer.write_line('service %sController {' % self.model.__name__)
        with self._writer.indent():
            self._writer.write_line(
                'rpc List(%sListRequest) returns (stream %s) {}' %
                (self.model.__name__, self.model.__name__)
            )
            self._writer.write_line(
                'rpc Create(%s) returns (%s) {}' %
                (self.model.__name__, self.model.__name__)
            )
            self._writer.write_line(
                'rpc Retrieve(%sRetrieveRequest) returns (%s) {}' %
                (self.model.__name__, self.model.__name__)
            )
            self._writer.write_line(
                'rpc Update(%s) returns (%s) {}' %
                (self.model.__name__, self.model.__name__)
            )
            self._writer.write_line(
                'rpc Destroy(%s) returns (google.protobuf.Empty) {}' %
                self.model.__name__
            )
        self._writer.write_line('}')

    def _generate_message(self):
        self._writer.write_line('message %s {' % self.model.__name__)
        
        with self._writer.indent():
            number = 0
            # -------------------------------------------
            # -- extract and valid Models Fields name ---
            fieldsList = self.get_fields().items()
            self.fieldsReference = fieldsList
            if not self.status_proto():
                return
            
            for field_name, proto_type in fieldsList:
                number += 1
                self._writer.write_line('%s %s = %s;' % (proto_type, field_name, number))
                
        self._writer.write_line('}')
        self._writer.write_line('')
        self._writer.write_line('message %sListRequest {' % self.model.__name__)
        self._writer.write_line('}')
        self._writer.write_line('')
        self._writer.write_line('message %sRetrieveRequest {' % self.model.__name__)
        
        
        with self._writer.indent():
            pk_field_name = self.field_info.pk.name
            pk_proto_type = self.build_proto_type(
                pk_field_name, self.field_info, self.model
            )
            self._writer.write_line(
                '%s %s = 1;' %
                (pk_proto_type, pk_field_name)
            )
        self._writer.write_line('}')

    def get_fields(self):
        """
        Return the dict of field names -> proto types.
        """
        if model_meta.is_abstract_model(self.model):
            raise ValueError('Cannot generate proto for abstract model.')
        fields = OrderedDict()
        for field_name in self.get_field_names():
            if field_name in fields:
                continue
            fields[field_name] = self.build_proto_type(field_name, self.field_info, self.model)
            if not self.status_proto():
                break
        return fields

    def get_field_names(self):
        field_names = self.field_names
        if not field_names:
            field_names = (
                [self.field_info.pk.name]
                + list(self.field_info.fields)
                + list(self.field_info.forward_relations)
            )
        return field_names

    def build_proto_type(self, field_name, field_info, model_class):
        self._status = True
        if field_name in field_info.fields_and_pk:
            model_field = field_info.fields_and_pk[field_name]
            return self._build_standard_proto_type(model_field)
        elif field_name in field_info.relations:
            relation_info = field_info.relations[field_name]
            return self._build_relational_proto_type(relation_info)
        else:
            self._status = False
            self._message = 'Field name `%s` is not valid for model `%s`.' % (field_name, model_class.__name__)

    def _build_standard_proto_type(self, model_field):
        if model_field.one_to_one and model_field.primary_key:
            info = model_meta.get_field_info(model_field.related_model)
            return self.build_proto_type(
                info.pk.name, info, model_field.related_model
            )
        else:
            return self.type_mapping[model_field]

    def _build_relational_proto_type(self, relation_info):
        info = model_meta.get_field_info(relation_info.related_model)
        to_field = info.pk.name
        if relation_info.to_field and not relation_info.reverse:
            to_field = relation_info.to_field
        proto_type = self.build_proto_type(
            to_field, info, relation_info.related_model
        )
        if relation_info.to_many:
            proto_type = 'repeated ' + proto_type
        return proto_type


class _CodeWriter:
    def __init__(self):
        self.buffer = io.StringIO()
        self._indent = 0

    def indent(self):
        return self

    def __enter__(self):
        self._indent += 1
        return self

    def __exit__(self, *args):
        self._indent -= 1

    def write_line(self, line):
        for i in range(self._indent):
            self.buffer.write("    ")
        print(line, file=self.buffer)

    def get_code(self):
        return self.buffer.getvalue()