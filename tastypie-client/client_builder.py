"""Build a client module for this revision.

Clients are versioned by date, by default.
"""
from datetime import datetime
from operator import itemgetter
from urlparse import urljoin
from urlparse import urlparse
import json
import sys

import requests


class Client(object):
    def __init__(self, base_url):
        parsed_url = urlparse(base_url)
        self.base_host = parsed_url.scheme + "://" + parsed_url.netloc
        self.base_url = base_url


class ClientBuilder(object):
    def __init__(self, base_url):
        self.client = Client(base_url)

    def _get_entry_points(self):
        """Return a list of all top-level entry points.

        These top-level entry points will correspond with generated Resources.
        """
        data = json.loads(requests.get(self.client.base_url).content)
        return data

    def _write_import_block(self, outstream):
        with CodeGeneratorBackend(outstream=outstream) as cg:
            cg.write("from tastypieclient.fields import CharField")
            cg.write("from tastypieclient.fields import BooleanField")
            cg.write("from tastypieclient.fields import DateTimeField")
            cg.write("from tastypieclient.fields import DeferredField")
            cg.write("from tastypieclient.fields import ToManyField")
            cg.write("from tastypieclient.fields import UUIDField")
            cg.write("from tastypieclient.resources import Resource")
            cg.write("")

    def _write_resource(self, outstream, resource):
        resource._write_generated_source(outstream)
        with CodeGeneratorBackend(outstream=outstream) as cg:
            cg.write("")
            cg.write("")

    def generate_client(self, name):
        """Generate the client module for the base_url."""
        entry_points = self._get_entry_points()
        resources = [Resource(self.client, name, **entry_point)
                     for (name, entry_point) in entry_points.iteritems()]
        # Now we have our resources, let's write them out
        fname = '%s.py.%s' % (name, datetime.utcnow().strftime("%s"))
        with open(fname, 'w') as fp:
            self._write_import_block(fp)
            for resource in resources:
                self._write_resource(fp, resource)


class Resource(object):
    def __init__(self, client, name, list_endpoint, schema):
        """Initialize a Resource object.

        Args:
            name: The unicode name of this Resource
            list_endpoint: The URL to use for fetching a list
            schema: The schema URL or Schema object for this Resource
        """
        self.client = client
        self.name = name
        self.list_endpoint = list_endpoint
        if isinstance(schema, Schema):
            self.schema = Schema
        else:
            self.schema = Schema(self.client, schema)

    def _write_class_constants(self, code_generator_backend):
        cg = code_generator_backend
        cg.write("list_endpoint = '%s'" % self.list_endpoint)
        cg.write("default_format = '%s'" % self.schema.default_format)
        cg.write("default_limit = %s" % self.schema.default_limit)
        cg.write("")

    def _write_fields(self, code_generator_backend):
        cg = code_generator_backend
        for field_name, field in self.schema.field_list:
            field.write_field(cg)

    def _write_generated_source(self, outstream):
        with CodeGeneratorBackend(outstream=outstream) as cg:
            cg.write("class %s(Resource):" %
                     self.name.title().replace("_", ""))
            cg.indent()

            self._write_class_constants(cg)
            self._write_fields(cg)

            #for (field_name, field) in self.schema.field_list:
            #    cg.indent()
            #    cg.dedent()
            #    cg.write("")

            cg.dedent()


class Schema(object):
    def __init__(self, client, schema_url):
        """Initialize a Schema object from a TastyPie schema declaration."""
        self.client = client

        data = json.loads(requests.get(
            urljoin(self.client.base_host, schema_url)).content)
        self.detail_methods = data['allowed_detail_http_methods']
        self.list_methods = data['allowed_list_http_methods']
        self.default_format = data['default_format']
        self.default_limit = data['default_limit']
        self.fields = {key: Field(client, name=key, **value) for key, value in
                       data['fields'].iteritems()}

    @property
    def field_list(self):
        return sorted(self.fields.items(), key=itemgetter(0))


class Field(object):
    def __init__(self, client, name,
                 type, related_type=None,  # only used for type=="related"
                 default=None, blank=False, nullable=False,
                 unique=False, readonly=False, help_text=""):
        """Initialize a Field from a TastyPie schema field."""
        self.client = client
        self.name = name
        self.type = type
        self.related_type = related_type
        self.help_text = help_text
        self.default = default
        self.blank = blank
        self.nullable = nullable
        self.readonly = readonly
        self.unique = unique

    def write_field(self, code_generator_backend):
        cg = code_generator_backend

        field_types = {
            'boolean': 'BooleanField',
            'string': 'CharField',
            'to_one': 'DeferredField',
            'to_many': 'ToManyField',
            'datetime': 'DateTimeField',
        }
        if self.name.endswith("uuid"):
            field_cls = "UUIDField"
        elif self.type == "related":
            field_cls = field_types[self.related_type]
        else:
            field_cls = field_types[self.type]

        cg.write("{name} = {field}(".format(
            name=self.name,
            field=field_cls))
        cg.indent()
        cg.write('help_text="%s",' %
                 self.help_text.replace('"', '\\"'))
        cg.write("blank=%s," % self.blank)
        cg.write("nullable=%s," % self.nullable)
        cg.write("readonly=%s," % self.readonly)
        cg.write("unique=%s)" % self.unique)
        cg.dedent()


class CodeGeneratorBackend(object):
    """
    From http://effbot.org/zone/python-code-generator.htm and modified a bit
    """
    def __init__(self, tab_chars=" " * 4, outstream=sys.stdout):
        self.code = []
        self.tab_chars = tab_chars
        self.level = 0
        self.outstream = outstream

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.outstream.writelines(self.code)

    def write(self, string):
        self.code.append(self.tab_chars * self.level + string + "\n")

    def indent(self):
        self.level = self.level + 1

    def dedent(self):
        if self.level == 0:
            raise SyntaxError("internal error in code generator")
        self.level = self.level - 1
