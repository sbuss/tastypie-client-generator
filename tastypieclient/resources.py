class ResourceMetaClass(type):
    def __new__(cls, name, bases, attrs):
        super_new = super(ResourceMetaClass, cls).__new__

        # Create the class.
        module = attrs.pop('__module__')
        new_class = super_new(cls, name, bases, {'__module__': module})

        # Now add all of the attributes as fields on the Resource
        new_class._fields = {}
        for obj_name, obj in attrs.items():
            new_class.add_to_class(obj_name, obj)

        # Give the class a docstring
        if new_class.__doc__ is None:
            new_class.__doc__ = "{class_name}({fields})".format(
                class_name=new_class.__name__,
                fields=", ".join(sorted(new_class._fields.keys())))
        return new_class

    def add_to_class(cls, name, value):
        """Add an attribute to the class.

        Args:
            cls: The class to add an attribute to
            name: The name of the attribute to add
            value: The value to associate with this attribute.

        This is a great pattern stolen from Django.

        If the attribute implements `contribute_to_class`, that will be used,
        since Fields have some special logic in there to make working with
        them a bit easier. Otherwise the gettable is just added as an
        attribute to cls.
        """
        if hasattr(value, 'contribute_to_class'):
            value.contribute_to_class(cls, name)
            if not name.startswith('_'):
                cls._fields[name] = value
        else:
            setattr(cls, name, value)


class Resource(object):
    __metaclass__ = ResourceMetaClass

    def __init__(self, base_url, **kwargs):
        """Initialize a Resource.

        Args:
            base_url: The base url to use for this Resource.
            kwargs: Kwargs for the Resource subclass, as defined by that
                Resource's fields.

        TastyPie typically just returns the relative path for a resource,
        so if we don't keep track of the base uri we won't know how to properly
        fetch new resources.
        """
        self.base_url = base_url
        for field_name, field in self._fields.iteritems():
            if field.required and field_name not in kwargs:
                raise ValueError("'%s' is a required kwarg" % field_name)
            setattr(self, field_name, kwargs.get(field_name, None))
        super(Resource, self).__init__()


class Client(object):
    def __init__(self, base_url):
        # Map a resource to each available endpoint
        # Support getting and slicing, etc
        pass
