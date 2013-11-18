import json
from urlparse import urljoin
from urlparse import urlparse
import uuid

from dateutil import parser as date_parser
import requests

from .resources import Resource


class Field(object):
    def __init__(self,
                 blank=False,
                 nullable=False,
                 readonly=False,
                 unique=False,
                 required=False,
                 help_text=""):
        """Fields are individual data elements of a Resource.

        The init kwargs here will mean the same things as they do in TastyPie.

        Args:
            blank: Whether or not the field can be blank
            nullable: Whether or not the field can be null
            readonly: If the Field is read-only
            unique: If the Field is unique among all Resources
            required: If the Field is required for object creation
            help_text: Any help text given

        Fields use __get__ and some metaclass magic to work like typical Django
        style fields.
        """
        self.name = None
        self.owner = None  # Owner is the class that contains the field.
                           # Set as a convenience via `contribute_to_class`

        self.blank = blank
        self.nullable = nullable
        self.readonly = readonly
        self.unique = unique
        self.required = required
        self.help_text = help_text

    def contribute_to_class(self, cls, name):
        """Add the appropriately named attribute to the class.

        Args:
            cls: The class to which to add this Field as an attribute
            name: The name of this field

        This was done to mimic Django's neat way of auto-naming attributes.
        Without this, you'd have to do something like

        class MyResource(Resource):
            primary_key = UUIDField('primary_key')
            username = CharField('username')

        This method allows the name parameter to be figured out automatically
        with help from the ResourceMetaClass, so you can do the nicer:

        class MyResource(Resource):
            primary_key = UUIDField()
            username = CharField()
        """
        if not self.name:
            self.name = name
        self.owner = cls
        setattr(self.owner, name, self)
        # TODO: Update docstring and __init__ kwargs for owner

    def __get__(self, instance, owner):
        """Get the value for this Field.

        Args:
            instance: The instance of the Field requested
            owner: The class which owns this Field
        Returns the backing representation for this Field.

        This method is the intermediary between the backing Field class and
        the externally exposed representation of its data.

        Use these simple Resources as an example:

        class UserResource(Resource):
            username = CharField()
            blag_posts = ToManyField(BlagResource)

        class BlagResource(Resource):
            title = CharField()
            body = CharField()

        For a CharField, you'd probably rather just return the string
        representation of the data, rather than return a CharField to the user.

        > user = UserResource(
        ...    usename='sbuss', blag_posts=['/blag/1', '/blag/2'])
        > user.username
        'sbuss'

        But for something like a ToManyField, exposing the list of related
        resources directly as a list of strings probably isn't want you want.

        > user.blag_posts
        ['/blag/1', '/blag/2']  # Oh, no! Those aren't BlagPosts!

        If you check out ToManyField's `__get__` you'll see that it actually
        returns self:

        > user.blag_posts
        <ToManyField at 0x...>

        Now if you start accessing the blag posts for this user, you'll get
        proper BlagResources back:

        > user.blag_posts[0]
        <BlagPost at 0x...>
        """
        if self.name not in instance.__dict__:
            raise AttributeError(
                "'%s' object has no attribute '%s'" %
                (owner.__name__, self.name))
        return instance.__dict__[self.name]

    def __set__(self, instance, value):
        """Convert the value to a Field object.

        Args:
            instance: The instance of the Field requested
            value: The external representation of the Field.

        This intercepts attempts to set the value of a Field so that the data
        can be munged correctly.

        For example:

        class UserResource(Resource):
            username = CharField()
            blag_posts = ToManyField(BlagResource)

        class BlagResource(Resource):
            title = CharField()
            body = CharField()

        When you set the set the value of these attributes on instances of
        these Resources, you don't actually want to change the type of the
        Resources.

        > user = UserResource()
        > user.username = 'sbuss'  # username should still be a CharField,
                                   # not a string!

        Say you wanted a UnicodeField to convert all strings to unicode. You'd
        implement __set__ something like this:

        class UnicodeField(Field):
            def __set__(self, instance, value):
                super(UnicodeField, self).__set__(instance, unicode(value))

        Now every object given to this field will be converted to unicode.

        > user.username = 'sbuss'
        > user.username
        u'sbuss'
        > user.username = True
        > user.username
        u'True'
        """
        if not self.nullable and value is None:
            raise ValueError("'%s' on '%s' is non-nullable" %
                             (self.name, self.owner.__name__))
        #if not self.blank and not value:
        #    raise ValueError("'%s' on '%s' cannot be blank" %
        #                     (self.name, self.owner.__name__))
        if (self.readonly and
                self.name in instance.__dict__ and
                instance.__dict__[self.name] is not None):
            raise ValueError("'%s' on '%s' is read-only" %
                             (self.name, self.owner.__name__))

        instance.__dict__[self.name] = value


class UUIDField(Field):
    def __set__(self, instance, value):
        if not value or isinstance(value, uuid.UUID):
            super(UUIDField, self).__set__(instance, value)
            return
        elif isinstance(value, basestring):
            super(UUIDField, self).__set__(instance, uuid.UUID(value))
            return
        else:
            raise ValueError("%s cannot be converted to a UUID." % value)


class CharField(Field):
    def __set__(self, instance, value):
        if not value:
            value = ''
        super(CharField, self).__set__(instance, unicode(value))


class BooleanField(Field):
    def __set__(self, instance, value):
        if isinstance(value, basestring):
            if value.lower() == 'false':
                value = False
            value = True
        elif value is not None:
            value = bool(value)
        super(BooleanField, self).__set__(instance, value)


class DateTimeField(Field):
    def __set__(self, instance, value):
        """Expects the DateTime to be in isoformat."""
        if value:
            try:
                value = date_parser.parse(value)
            except AttributeError:
                raise ValueError("Cannot parse datetime %s" % value)
        super(DateTimeField, self).__set__(instance, value)


class DeferredList(list):
    """
    DeferredLists hold the necessary state to do lists of DeferredFields.

    TODO This is ugly :(
    """
    def __init__(self, deferred_fields, instance, owner):
        self.deferred_fields = deferred_fields
        self.instance = instance
        self.owner = owner

    def __len__(self):
        return len(self.deferred_fields)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [resource.__get__(self.instance, self.owner)
                    for resource in self.deferred_fields[index]]
        else:
            return self.deferred_fields[index].__get__(
                self.instance, self.owner)

    def __repr__(self):
        return "DeferredList(%s)" % ",".join(
            resource.__repr__() for resource in self.deferred_fields)

    def __str__(self):
        return self.__repr__()


class ToManyField(Field):
    """A deferred relation from one to many objects.

    This is just a list of DeferredFields.
    """
    def __init__(self, related_resource_class=None, *args, **kwargs):
        """Initialize the ToManyField.

        Args:
            related_resource_class: The `Resource` subclass you want to
                instanstiate with this deferred data, passed to DeferredField.
        """
        super(ToManyField, self).__init__(*args, **kwargs)
        self.related_resource_class = related_resource_class
        self.base_url = None

    def __set__(self, instance, value):
        if not value:
            super(ToManyField, self).__set__(instance, value)
            return

        self.base_url = instance.base_url
        if not isinstance(value, list):
            raise ValueError("ToManyFields must get a list")
        deferreds = []
        for count, resource_url in enumerate(value):
            field = DeferredField(self.related_resource_class)
            field.name = "_deferred_%s_%s" % (self.name, count)
            field.__set__(instance, resource_url)
            deferreds.append(field)
        super(ToManyField, self).__set__(
            instance, DeferredList(deferreds, instance, self.owner))


class DeferredField(Field):
    """DeferredFields are related fields that need another network request."""
    def __init__(self, related_resource_class=None, *args, **kwargs):
        """Initialize the DeferredField.

        Args:
            related_resource_class: The `Resource` subclass you want to
                instanstiate with this deferred data.

        If related_resource_class is not given, it will be figured out at
        runtime by trying to match the given deferred url to a known
        Resource's list_endpoint.
        """
        super(DeferredField, self).__init__(*args, **kwargs)
        self.instance = None  # TODO: Is `instance` here a bug?
        self.related_resource_class = related_resource_class

    @classmethod
    def get_related_resource_class(cls, uri):
        """Try to figure out the related resource class.

        Args:
            uri: The full URI of the related resource.

        uri is going to look something like
        http://example.com/blog/api/v1/entry/<entry_id>?filter_param=1
        while the list_endpoint on a Resource will be /blog/api/v1/entry
        so we can use this knowledge to try to guess the correct resource.
        """
        parsed_uri = urlparse(uri)
        subclasses = Resource.__subclasses__()
        for subclass in subclasses:
            if parsed_uri.path.startswith(subclass.list_endpoint):
                return subclass
            subclasses.extend(subclass.__subclasses__())
        return None

    def __get__(self, instance, owner):
        if self.instance:
            return self.instance

        value = super(DeferredField, self).__get__(instance, owner)
        if not value:
            return value

        # First make sure that the deferred URL is gettable
        if not urlparse(value).netloc:
            # Default to using the currently known base url
            value = urljoin(instance.base_url, value)
        # We haven't gotten this object yet, so fetch it and try to instantiate
        data = json.loads(requests.get(value).content)
        if not self.related_resource_class:
            self.related_resource_class = self.get_related_resource_class(
                value)
        self.instance = self.related_resource_class(
            base_url=instance.base_url, **data)
        return self.instance

    def __set__(self, instance, value):
        """DeferredFields expect `value` to be a URL."""
        if not isinstance(value, basestring):
            raise ValueError("DeferredFields should bet set as a URL")
        # Don't forget to clean up after the last get
        self.__delete__(instance)
        super(DeferredField, self).__set__(instance, value)

    def __delete__(self, instance):
        """Deleting a DeferredField only clears its cache.

        If you request the attribute again, it will make the network request
        again."""
        self.instance = None
