import os
import mimetypes
import logging
from datetime import datetime, date
from dateutil.tz import tzutc
import dateutil.parser

from sqlalchemy import and_, or_, func, asc as ascending, desc as descending, event
from sqlalchemy.types import *
from sqlalchemy.sql.functions import coalesce
from sqlalchemy.orm import scoped_session, sessionmaker, relationship, aliased, mapper
from sqlalchemy.orm.collections import attribute_mapped_collection
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.schema import UniqueConstraint, Table, Column
from batteries.model import Model, initialize_model
from batteries.model.hashable import Hashable, HashableReference, HashableKey, HashableAssociation
from batteries.model.serializable import Serializable
from batteries.model.identifiable import Identifiable
from batteries.model.recordable import Recordable
from batteries.model.types import UTCDateTime, Ascii


logger = logging.getLogger(__name__)
_session = None

Model.metadata.naming_convention = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s'
}

def get_session():
    return _session


def initialize(engine, create=False, drop=False):
    global _session

    _session = scoped_session(sessionmaker())
    initialize_model(_session, engine)

    if drop:
        logger.warning("dropping all tables in {engine.url!s}".format(engine=engine))
        Model.metadata.drop_all()

    if create:
        logger.info("creating tables in {engine.url!s}".format(engine=engine))
        Model.metadata.create_all(engine)

    return _session


def _handle_property(instance, name):
    mapper = instance.__mapper__
    if (mapper.has_property(name) or
            hasattr(instance.__class__, name) or
            not hasattr(instance, '_sa_instance_state') or
            'AssociationProxy' in name):
        return False
    else:
        return True


class PropertyContainer(object):
    def __getattr__(self, k):
        if _handle_property(self, k):
            if k in self._properties:
                return self._properties[k].value
            else:
                raise AttributeError(k)
        else:
            return Model.__getattribute__(self, k)

    def __setattr__(self, k, v):
        if _handle_property(self, k):
            if k in self._properties:
                self._properties[k].value = v
            else:
                self._properties[k] = Property(name=k, value=v)
        else:
            Model.__setattr__(self, k, v)


class Site(Hashable, Identifiable, Model):
    __identifiers__ = ('slug', 'name')
    named_with = ('slug',)

    _key = HashableKey()
    _slug = Column('slug', Ascii(100), unique=True)
    name = Column(UnicodeText, unique=True)
    url = Column(UnicodeText)
    _content = relationship('Content', lazy='dynamic')
    _assets = relationship('Asset', lazy='dynamic')
    _properties = relationship('Property',
                            secondary='site_property',
                            collection_class=attribute_mapped_collection('name'),
                            single_parent=True,
                            cascade='all, delete-orphan')

    @property
    def content(self):
        return PropertyQuery(self._content, Content, content_property)

    @property
    def assets(self):
        return PropertyQuery(self._assets, Asset, asset_property)

    @property
    def tags(self):
        return Tag.query.distinct().\
                         join(Tag.content).\
                         filter(Content.site_key == self.key).\
                         order_by(Tag.name.asc())


class Content(Hashable, Identifiable, PropertyContainer, Model, Recordable):
    __identifiers__ = ('slug', 'title')
    named_with = ('title',)

    _key = HashableKey()
    site_key = HashableReference('site', name='site_key_constraint')
    _slug = Column('slug', Ascii(100), unique=True)

    title = Column(UnicodeText, nullable=False)
    body = Column(UnicodeText, nullable=False)

    publish_time = Column(UTCDateTime)
    path = Column(UnicodeText, nullable=False)

    # checksum = Column(Integer)

    site = relationship('Site')
    tags = relationship('Tag', secondary='content_tag')

    _properties = relationship('Property',
                           secondary='content_property',
                           collection_class=attribute_mapped_collection('name'),
                           single_parent=True,
                           cascade='all, delete-orphan')

    def as_dict(self):
        d = {}
        for k in ('key', 'slug', 'title', 'body', 'publish_time', 'path'):
            d[k] = getattr(self, k)

        d['tags'] = [t.name for t in self.tags]
        # d.update(self.properties)
        d.update({k: p.value for k, p in self._properties.items()})
        return d


class Asset(Hashable, Identifiable, PropertyContainer, Model, Recordable):
    __identifiers__ = ('slug', 'path')
    named_with = ('filename',)

    _key = HashableKey()
    site_key = HashableReference('site', name='site_key_constraint')
    _slug = Column('slug', Ascii(100), unique=True)
    type = Column(Ascii(100))

    body = Column(UnicodeText)
    path = Column(UnicodeText, nullable=False)

    checksum = Column(Integer, nullable=False)

    site = relationship('Site')
    tags = relationship('Tag', secondary='asset_tag')

    _properties = relationship('Property',
                           secondary='asset_property',
                           collection_class=attribute_mapped_collection('name'),
                           single_parent=True,
                           cascade='all, delete-orphan')

    @property
    def filename(self):
        basename = os.path.basename(self.path)
        return os.path.splitext(basename)

    @property
    def mimetype(self):
        m = mimetypes.guess_type('.'.join(self.filename))
        return m

    def as_dict(self):
        d = {}
        for k in ('key', 'slug', 'body', 'path', 'mimetype'):
            d[k] = getattr(self, k)

        d['tags'] = [t.name for t in self.tags]
        d.update({k: p.value for k, p in self._properties.items()})
        return d

    @staticmethod
    def on_before_insert(mapper, connection, target):
        m = target.mimetype[0]
        if m:
            target.type = m.split('/')[0]


class Tag(Hashable, Identifiable, Model):
    __identifiers__ = ('slug', 'name')
    named_with = ('name',)

    _key = HashableKey()
    _slug = Column('slug', Ascii(100), unique=True)
    name = Column(UnicodeText, nullable=False)

    content = relationship('Content', secondary='content_tag')

    def as_dict(self):
        d = {}
        for k in ('key', 'slug', 'name'):
            d[k] = getattr(self, k)
        return d


class Property(Hashable, Model):
    __identifiers__ = ('name', 'value')
    serializable = ('content_key', 'name', 'value', 'type')

    _key = HashableKey()
    name = Column(Unicode(100), nullable=False, primary_key=True)

    bool_value = Column(Boolean(name='bool_value_constraint'))
    int_value = Column(Integer)
    float_value = Column(Numeric(24, scale=6))
    date_value = Column(Date)
    datetime_value = Column(UTCDateTime)
    str_value = Column(UnicodeText)

    @property
    def type(self):
        if self.bool_value:
            return bool

        if self.int_value:
            return int

        if self.float_value:
            return float

        if self.date_value:
            return date

        if self.datetime_value:
            return datetime

        if self.str_value:
            return unicode

    def _reset_value(self):
        for k in ('bool', 'date', 'datetime', 'int', 'float', 'str'):
            prop = k + '_value'
            setattr(self, prop, None)

    @hybrid_property
    def value(self):
        for k in ('bool', 'date', 'datetime', 'int', 'float', 'str'):
            prop = k + '_value'
            v = getattr(self, prop)
            if v is not None:
                return v

        return None

    @value.setter
    def value(self, v):
        self._reset_value()

        # null
        if v is None:
            return

        # bool
        elif isinstance(v, bool):
            self.bool_value = v
            return

        elif isinstance(v, basestring):
            # literal false values
            if v.lower() in ('false', 'no', 'off'):
                self.bool_value = False

            # literal true values
            elif v.lower() in ('true', 'yes', 'on'):
                self.bool_value = True

            # quoted string
            elif (v.startswith('"') and v.endswith('"')) or\
                (v.startswith("'") and v.endswith("'")):
                self.str_value = v[1:-1]
                return

        # int
        try:
            v = int(v)
            self.int_value = v
            return
        except ValueError:
            pass

        # float
        try:
            v = float(v)
            self.float_value = v
            return
        except ValueError:
            pass

        # date
        try:
            v = datetime.strptime(v, '%Y-%m-%d').date()
            self.date_value = v
            return
        except ValueError:
            pass

        # datetime
        try:
            v = dateutil.parser.parse(v)
            if v.tzinfo is None:
                v = v.replace(tzinfo=tzutc())
            self.datetime_value = v
            return
        except ValueError:
            pass

        # default str
        self.str_value = v

    def as_dict(self):
        d = {}
        for k in ('content_key', 'name', 'value', 'type'):
            d[k] = getattr(self, k)
        return d


class PropertyQuery(object):
    def __init__(self, relationship, model, assoc_table):
        self.query = relationship.join(model._properties)
        self.model = model
        self.assoc_table = assoc_table

    @classmethod
    def _derive_property_type(cls, v):
        if isinstance(v, bool):
            return Property.bool_value
        if isinstance(v, int):
            return Property.int_value
        if isinstance(v, float):
            return Property.float_value
        if isinstance(v, date):
            return Property.date_value
        if isinstance(v, datetime):
            return Property.datetime_value
        if isinstance(v, basestring):
            return Property.str_value
        if isinstance(v, (list, tuple)):
            return map(cls._derive_property_type, v)[0]
        if isinstance(v, dict):
            return map(cls._derive_property_type, v.values())[0]
        raise ValueError(type(v))

    @classmethod
    def _parse_numeric_criteria(cls, column, c):
        if isinstance(c, (int, float)):
            return column == c
        if isinstance(c, list):
            return column.in_(c)
        if isinstance(c, dict):
            clauses = []
            for k, v in c.items():
                if k == 'eq':
                    clauses.append(column == v)
                if k == 'neq':
                    clauses.append(column != v)
                if k == 'gt':
                    clauses.append(column > v)
                if k == 'gteq':
                    clauses.append(column >= v)
                if k == 'lt':
                    clauses.append(column < v)
                if k == 'lteq':
                    clauses.append(column <= v)
            return and_(*clauses)
        raise ValueError(c)

    @classmethod
    def _parse_temporal_criteria(cls, column, c):
        if isinstance(c, basestring):
            c = dateutil.parser.parse(c)
            return column == c
        if isinstance(c, (date, datetime)):
            return column == c
        if isinstance(c, list):
            return column.in_(c)
        if isinstance(c, dict):
            clauses = []
            for k, v in c.items():
                if k == 'is':
                    clauses.append(column == v)
                if k == 'isnot':
                    clauses.append(column != v)
                if k == 'after':
                    clauses.append(column > v)
                if k == 'on_after':
                    clauses.append(column >= v)
                if k == 'before':
                    clauses.append(column < v)
                if k == 'on_before':
                    clauses.append(column <= v)
            return and_(*clauses)
        raise ValueError(c)

    @classmethod
    def _parse_textual_criteria(cls, column, c):
        if isinstance(c, (basestring)):
            return column == c
        if isinstance(c, list):
            return column.in_(c)
        if isinstance(c, dict):
            insensitive = c.get('insensitive')
            if insensitive:
                column = func.lower(column)

            clauses = []
            for k, v in c.items():
                if k == 'is':
                    if insensitive:
                        v = v.lower()
                    clauses.append(column == v)
                if k == 'in':
                    v = [s.lower() if insensitive else s for s in v]
                    clauses.append(column.in_(v))
                if k == 'contains':
                    if insensitive:
                        v = v.lower()
                    clauses.append(column.contains(v))
                if k == 'startswith':
                    if insensitive:
                        v = v.lower()
                    clauses.append(column.startswith(v))
                if 'endswith' in criteria:
                    if insensitive:
                        v = v.lower()
                    clauses.append(column.endswith(v))
            return and_(*clauses)
        raise ValueError(c)

    @classmethod
    def _parse_criteria(cls, column, c):
        if column.key == 'bool_value':
            return column == c

        if column.key in ('int_value', 'float_value'):
            return cls._parse_numeric_criteria(column, c)

        if column.key in ('date_value', 'datetime_value'):
            return cls._parse_temporal_criteria(column, c)

        if column.key in ('str_value'):
            return cls._parse_textual_criteria(column, c)

        if column.key in ('key',):
            if isinstance(c, list):
                return column.in_(c)
            return column == c
        if column.key in ('title', 'body', 'path'):
            return cls._parse_textual_criteria(column, c)
        if column.key in ('publish_time',):
            return cls._parse_temporal_criteria(column, c)
        if column.key in ('type',):
            return and_(column == c)

        raise ValueError(column.key)

    def filter(self, **kwargs):
        for k, v in kwargs.items():
            if self.model.__mapper__.has_property(k):
                if k not in ('tags',):
                    column = getattr(self.model, k)
                    c = PropertyQuery._parse_criteria(column, v)
                    self.query = self.query.filter(c)

                elif k in ('tags',):
                    if not isinstance(v, list):
                        v = [v]

                    tag_keys = []
                    for t in v:
                        if isinstance(t, Tag):
                            tag_keys.append(t.key)
                        else:
                            t = Tag.get(slug=t.lower())
                            if t:
                                tag_keys.append(t.key)

                    clauses = [Tag.key == k for k in tag_keys]
                    clause = and_(*(self.model.tags.any(c) for c in clauses))
                    self.query = self.query.filter(clause).group_by(self.model.key)

            else:
                clause = []
                clause.append(Property.name == k)
                column = PropertyQuery._derive_property_type(v)
                clause.append(PropertyQuery._parse_criteria(column, v))
                self.query = self.query.filter(and_(*clause))

        return self

    def all(self):
        return self.query.all()

    def one(self):
        return self.query.one()

    def limit(self, l):
        self.query = self.query.limit(l)
        return self

    def offset(self, o):
        self.query = self.query.offset(o)
        return self

    def order_by(self, asc=None, desc=None):
        if asc:
            if not isinstance(asc, list):
                asc = [asc]
        else:
            asc = []

        if desc:
            if not isinstance(desc, list):
                desc = [desc]
        else:
            desc = []

        sorts = []
        for c in asc + desc:
            if self.model.__mapper__.has_property(c):
                column = getattr(self.model, c)
                sorts.append(column)
            else:
                aliased_assoc = aliased(self.assoc_table)
                aliased_property = aliased(Property, name=c)
                fk_name = '_'.join(self.assoc_table.name.split('_')[:-1] + ['key'])
                fk = getattr(aliased_assoc.c, fk_name)
                self.query = self.query.\
                        outerjoin(aliased_assoc,
                                  fk == self.model.key).\
                        outerjoin(aliased_property,
                                  and_(aliased_assoc.c.property_key == Property.key,
                                       Property.name == c))

                sorts.append((c, aliased_property))

        for s in sorts:
            if isinstance(s, tuple):
                c, alias = s
                if c in asc:
                    f = ascending
                if c in desc:
                    f = descending

                ordering = f(coalesce(
                                alias.bool_value,
                                alias.int_value,
                                alias.float_value,
                                alias.date_value,
                                alias.datetime_value,
                                alias.str_value))
                self.query = self.query.order_by(ordering)
            else:
                if s.key in asc:
                    self.query = self.query.order_by(s.asc())
                if s.key in desc:
                    self.query = self.query.order_by(s.desc())

        return self

    def __unicode__(self):
        return unicode(self.query)

    def __str__(self):
        return str(self.query)


content_tag = HashableAssociation('content', 'tag')
asset_tag = HashableAssociation('asset', 'tag')
content_property = HashableAssociation('content', 'property')
asset_property = HashableAssociation('asset', 'property')
site_property = HashableAssociation('site', 'property')
