# -*- coding: UTF-8
"""
Implementation of the code executed when an HTTP client reach /admin/fields URI.
"""
from __future__ import unicode_literals

from storm.exceptions import DatabaseError
from twisted.internet.defer import inlineCallbacks

from globaleaks import models
from globaleaks.handlers.base import BaseHandler
from globaleaks.handlers.authentication import authenticated, transport_security_check
from globaleaks.models import Field, Step
from globaleaks.rest import errors, requests
from globaleaks.settings import transact, transact_ro
from globaleaks.utils.utility import log

def admin_serialize_field(field, language):
    """
    Serialize a field, localizing its content depending on the language.

    :param: field: the field object to be serialized
    :param: language: the language in which to localize data
    :return: a serialization of the object
    """
    return {
        'id': field.id,
        'label': field.label,
        'description': field.description,
        'hint': field.hint,
        'multi_entry': field.multi_entry,
        'required': field.required,
        'preview': False,
        'stats_enabled': field.stats_enabled,
        'type': field.type,
        'x': field.x,
        'y': field.y,
        'options': field.options or {},
        'children': [f.id for f in field.children],
    }

@transact
def create_field(store, request, language):
    """
    Add a new field to the store, then return the new serialized object.
    :param: store: the store reference
    :param: request: the field definition dict
    :param: language: the language of the field definition dict
    :return: a serialization of the object
    """
    field = Field.new(store, request)
    return admin_serialize_field(field, language)

@transact
def update_field(store, field_id, request, language):
    """
    Updates the specified field with the details.
    raises :class:`globaleaks.errors.FieldIdNotFound` if the field does
    not exist.
    :param: store: the store reference
    :param: field_id: the field_id of the field to update
    :param: request: the field definition dict
    :param: language: the language of the field definition dict
    :return: a serialization of the object
    """
    errmsg = 'Invalid or not existent field ids in request.'

    field = Field.get(store, field_id)
    try:
        if not field:
            raise errors.InvalidInputFormat(errmsg)

        field.update(request)

        # children handling:
        #  - old children are cleared
        #  - new provided childrens are evaluated and added
        children = request['children']
        if children and field.type != 'fieldgroup':
            raise errors.InvalidInputFormat(errmsg)
   
        ancestors = set(fieldtree_ancestors(store, field.id))
        field.children.clear()
        for child_id in children:
            child = Field.get(store, child_id)
            # check child do exists and graph is not recursive
            if not child or child.id in ancestors:
                raise errors.InvalidInputFormat(errmsg)
            field.children.add(child)

    except DatabaseError as dberror:
        log.err('Unable to update field {f}: {e}'.format(
            f=field.label, e=dberror))
        raise errors.InvalidInputFormat(dberror)

    return admin_serialize_field(field, language)

@transact_ro
def get_field_list(store, language):
    """
    Serialize all the fields of the node, localizing their content depending on the language.

    :return: the current field list serialized.
    :param language: the language of the field definition dict
    :rtype: list of dict
    """
    return [admin_serialize_field(f, language) for f in store.find(Field)]

@transact_ro
def get_field(store, field_id, language):
    """
    Serialize a speficied field, localizing its content depending on the language.

    :param field_id: the id corresponding to the field.
    :param language: the language in which to localize data
    :return: the currently configured field.
    :rtype: dict
    """
    field = Field.get(store, field_id)
    if not field:
        log.err('Invalid field requested')
        raise errors.FieldIdNotFound
    return admin_serialize_field(field, language)

@transact
def delete_field(store, field_id):
    """
    Remove the field object corresponding to field_id from the store.

    If the field has children, remove them as well.
    If the field is immediately attached to a step object, remove it as well.

    :param field_id: the id corresponding to the field.
    :raise: FieldIdNotFound: if no such field is found.
    """
    field = Field.get(store, field_id)
    if not field:
        raise errors.FieldIdNotFound
    field.delete(store)

@transact
def get_context_fieldtree(store, context_id):
    """
    Return the serialized field tree belonging to a specific context.

    :param context_id: the id corresponding to the context.
    :return dict: a nested dictionary represending the tree.
    """
    #  context = Context.get(store, context_id)
    steps = store.find(Step, Step.context_id == context_id).order_by(Step.number)
    ret = []
    for step in steps:
        field = FieldGroup.get(store, step.field_id)
        ret.append(FieldGroup.serialize(store, field.id))
    return ret

def fieldtree_ancestors(store, field_id):
    """
    Given a field_id, recursively extract its parents.

    :param store: appendix to access to the database.
    :param field_id: the parent id.
    :return: a generator of Field.id
    """
    yield field_id
    parents = store.find(models.FieldField, models.FieldField.child_id == field_id)
    for parent in parents:
        if parent.parent_id != field_id:
            yield parent.parent_id
            for grandpa in fieldtree_ancestors(store, parent.parent_id): yield grandpa
    else:
        return

class FieldsCollection(BaseHandler):
    """
    /admin/fields
    """
    @transport_security_check('admin')
    @authenticated('admin')
    @inlineCallbacks
    def get(self, *uriargs):
        """
        Return a list of all the fields available.

        Parameters: None
        Response: adminFieldList
        Errors: None
        """
        # XXX TODO REMIND: is pointless define Response format because we're not
        # making output validation
        response = yield get_field_list(self.request.language)
        self.set_status(200)
        self.finish(response)

    @transport_security_check('admin')
    @authenticated('admin')
    @inlineCallbacks
    def post(self, *uriargs):
        """
        Create a new field.

        Request: adminFieldDesc
        Response: adminFieldDesc
        Errors: InvalidInputFormat, FieldIdNotFound
        """

        request = self.validate_message(self.request.body,
                                        requests.adminFieldDesc)
        response = yield create_field(request, self.request.language)
        self.set_status(201)
        self.finish(response)


class FieldInstance(BaseHandler):
    """
    Operation to iterate over a specific requested Field

    /admin/field/field_id
    """
    @transport_security_check('admin')
    @authenticated('admin')
    @inlineCallbacks
    def get(self, field_id, *uriargs):
        """
        Get the field identified by field_id

        :param field_id:
        :rtype: adminFieldDesc
        :raises FieldIdNotFound: if there is no field with such id.
        :raises InvalidInputFormat: if validation fails.
        """
        response = yield get_field(field_id, self.request.language)
        self.set_status(200)
        self.finish(response)

    @transport_security_check('admin')
    @authenticated('admin')
    @inlineCallbacks
    def put(self, field_id, *uriargs):
        """
        Update a single field's attributes.

        Request: adminFieldDesc
        Response: adminFieldDesc
        Errors: InvalidInputFormat, FieldIdNotFound
        """
        request = self.validate_message(self.request.body,
                                        requests.adminFieldDesc)
        response = yield update_field(field_id, request, self.request.language)
        self.set_status(202) # Updated
        self.finish(response)

    @transport_security_check('admin')
    @authenticated('admin')
    @inlineCallbacks
    def delete(self, field_id, *uriargs):
        """
        Delete a single field.

        Request: None
        Response: None
        Errors: InvalidInputFormat, FieldIdNotFound
        """
        yield delete_field(field_id)
        self.set_status(200)
