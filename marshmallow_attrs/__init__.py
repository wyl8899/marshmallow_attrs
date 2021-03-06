"""
This library allows the conversion of python 3.7's :mod:`dataclasses`
to :mod:`marshmallow` schemas.

It takes a python class, and generates a marshmallow schema for it.

Simple example::

    from marshmallow import Schema
    from marshmallow_attrs import dataclass

    @dataclass
    class Point:
      x:float
      y:float

    point = Point(x=0, y=0)
    point_json = Point.Schema().dumps(point)

Full example::

    from marshmallow import Schema
    from dataclasses import field
    from marshmallow_attrs import dataclass
    import datetime

    @dataclass
    class User:
      birth: datetime.date = attr.ib(metadata= {
        "required": True # A parameter to pass to marshmallow's attr.ib
      })
      website:str = attr.ib(metadata = {
        "marshmallow_field": marshmallow.fields.Url() # Custom marshmallow field
      })
      Schema: ClassVar[Type[Schema]] = Schema # For the type checker
"""
import collections.abc
import datetime
import decimal
import inspect
import uuid
from enum import Enum
from enum import EnumMeta
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Dict
from typing import List
from typing import Mapping
from typing import NewType
from typing import Optional
from typing import Tuple
from typing import Type
from typing import cast

import attr
import marshmallow
import typing_inspect


__all__ = ["dataclass", "add_schema", "class_schema", "field_for_schema"]

NoneType = type(None)


# _cls should never be specified by keyword, so start it with an
# underscore.  The presence of _cls is used to detect if this
# decorator is being called with parameters or not.
def dataclass(
    _cls: type = None,
    *,
    these=None,
    repr_ns=None,
    repr=True,
    cmp=True,
    hash=None,
    init=True,
    slots=False,
    frozen=False,
    weakref_slot=True,
    str=False,
    kw_only=False,
    cache_hash=False,
    auto_exc=False,
) -> type:
    """
    This decorator does the same as attr.dataclass, but also applies :func:`add_schema`.
    It adds a `.Schema` attribute to the class object

    >>> @dataclass
    ... class Artist:
    ...    name: str
    >>> Artist.Schema
    <class 'marshmallow.schema.Artist'>

    >>> from marshmallow import Schema
    >>> @dataclass
    ... class Point:
    ...   x:float
    ...   y:float
    ...   Schema: ClassVar[Type[Schema]] = Schema # For the type checker
    ...
    >>> Point.Schema().load({'x':0, 'y':0}) # This line can be statically type checked
    Point(x=0.0, y=0.0)
    """
    dc = attr.dataclass(
        _cls,
        these=these,
        repr_ns=repr_ns,
        repr=repr,
        cmp=cmp,
        hash=hash,
        init=init,
        slots=slots,
        frozen=frozen,
        weakref_slot=weakref_slot,
        str=str,
        kw_only=kw_only,
        cache_hash=cache_hash,
        auto_exc=auto_exc,
    )
    return add_schema(dc) if _cls else lambda cls: add_schema(dc(cls))


def add_schema(clazz: type) -> type:
    """
    This decorator adds a marshmallow schema as the 'Schema' attribute in a dataclass.
    It uses :func:`class_schema` internally.

    >>> @add_schema
    ... @attr.dataclass
    ... class Artist:
    ...    name: str
    >>> artist = Artist.Schema().loads('{"name": "Ramirez"}')
    >>> artist
    Artist(name='Ramirez')
    """
    clazz.Schema = class_schema(clazz)
    return clazz


def class_schema(clazz: type) -> Type[marshmallow.Schema]:
    """
    Convert a class to a marshmallow schema

    :param clazz: A python class (may be a dataclass)
    :return: A marshmallow Schema corresponding to the dataclass

    .. note::
        All the arguments supported by marshmallow field classes are can
        be passed in the `metadata` dictionary of a field.


    If you want to use a custom marshmallow field
    (one that has no equivalent python type), you can pass it as the
    ``marshmallow_field`` key in the metadata dictionary.

    >>> Meters = NewType('Meters', float)
    >>> @attr.dataclass()
    ... class Building:
    ...   height: Optional[Meters]
    ...   name: str = attr.ib(default="anonymous")
    ...   class Meta: # marshmallow meta attributes are supported
    ...     ordered = True
    ...
    >>> class_schema(Building) # Returns a marshmallow schema class (not an instance)
    <class 'marshmallow.schema.Building'>

    >>> @attr.dataclass()
    ... class City:
    ...   name: str = attr.ib(metadata={'required':True})
    ...   best_building: Building # Reference to another attr. A schema will be created for it too.
    ...   other_buildings: List[Building] = attr.ib(factory=list)
    ...
    >>> citySchema = class_schema(City)()
    >>> city = citySchema.load({"name":"Paris", "best_building": {"name": "Eiffel Tower"}, "other_buildings": []})
    >>> city
    City(name='Paris', best_building=Building(height=None, name='Eiffel Tower'), other_buildings=[])

    >>> citySchema.load({"name":"Paris"})
    Traceback (most recent call last):
        ...
    marshmallow.exceptions.ValidationError: {'best_building': ['Missing data for required field.']}

    >>> city_json = class_schema(Building)().dump(city.best_building)
    >>> city_json # We get an OrderedDict because we specified order = True in the Meta class
    OrderedDict([('height', None), ('name', 'Eiffel Tower')])

    >>> @attr.dataclass()
    ... class Person:
    ...   name: str = attr.ib(default="Anonymous")
    ...   friends: List['Person'] = attr.ib(factory=list) # Recursive field
    ...
    >>> person = class_schema(Person)().load({
    ...     "friends": [{"name": "Roger Boucher"}]
    ... })
    >>> person
    Person(name='Anonymous', friends=[Person(name='Roger Boucher', friends=[])])

    # >>> @attr.dataclass()
    # ... class C:
    # ...   important: int = attr.ib(init=True, default=0)
    # ...   unimportant: int = attr.ib(init=False, default=0) # Only fields that are in the __init__ method will be added:
    # ...
    # >>> c = class_schema(C)().load({
    # ...     "important": 9, # This field will be imported
    # ...     "unimportant": 9 # This field will NOT be imported
    # ... })
    # >>> c
    # C(important=9, unimportant=0)

    >>> @attr.dataclass
    ... class Website:
    ...  url:str = attr.ib(metadata = {
    ...    "marshmallow_field": marshmallow.fields.Url() # Custom marshmallow field
    ...  })
    ...
    >>> class_schema(Website)().load({"url": "I am not a good URL !"})
    Traceback (most recent call last):
        ...
    marshmallow.exceptions.ValidationError: {'url': ['Not a valid URL.']}

    >>> @attr.dataclass
    ... class NeverValid:
    ...     @marshmallow.validates_schema
    ...     def validate(self, data, **kwargs):
    ...         raise marshmallow.ValidationError('never valid')
    ...
    >>> _ = class_schema(NeverValid)().load({})
    Traceback (most recent call last):
      ...
    marshmallow.exceptions.ValidationError: {'_schema': ['never valid']}

    >>> # noinspection PyTypeChecker
    >>> class_schema(None)  # unsupported type
    Traceback (most recent call last):
      ...
    TypeError: None is not a dataclass and cannot be turned into one.
    """

    try:
        # noinspection PyDataclass
        fields: Tuple[attr.ib] = attr.fields(clazz)
    except TypeError:  # Not a dataclass
        try:
            return class_schema(attr.dataclass(clazz))
        except Exception:
            raise TypeError(
                f"{getattr(clazz, '__name__', repr(clazz))} is not a dataclass and cannot be turned into one."
            )

    # Copy all public members of the dataclass to the schema
    attributes = {k: v for k, v in inspect.getmembers(clazz) if not k.startswith("_")}
    # Update the schema members to contain marshmallow fields instead of dataclass fields
    attributes.update(
        (
            field.name,
            field_for_schema(field.type, _get_field_default(field), field.metadata),
        )
        for field in fields
        if field.init
    )

    schema_class = type(clazz.__name__, (_base_schema(clazz),), attributes)
    return cast(Type[marshmallow.Schema], schema_class)


_native_to_marshmallow: Dict[type, Type[marshmallow.fields.Field]] = {
    int: marshmallow.fields.Integer,
    float: marshmallow.fields.Float,
    str: marshmallow.fields.String,
    bool: marshmallow.fields.Boolean,
    dict: marshmallow.fields.Dict,
    datetime.datetime: marshmallow.fields.DateTime,
    datetime.time: marshmallow.fields.Time,
    datetime.timedelta: marshmallow.fields.TimeDelta,
    datetime.date: marshmallow.fields.Date,
    decimal.Decimal: marshmallow.fields.Decimal,
    uuid.UUID: marshmallow.fields.UUID,
    Any: marshmallow.fields.Raw,
}


def field_for_schema(
    typ: type, default=marshmallow.missing, metadata: Mapping[str, Any] = None
) -> marshmallow.fields.Field:
    """
    Get a marshmallow Field corresponding to the given python type.
    The metadata of the dataclass field is used as arguments to the marshmallow Field.

    >>> int_field = field_for_schema(int, default=9, metadata=dict(required=True))
    >>> int_field.__class__
    <class 'marshmallow.fields.Integer'>

    >>> int_field.default
    9

    >>> int_field.required
    True

    >>> field_for_schema(Dict[str,str]).__class__
    <class 'marshmallow.fields.Dict'>

    >>> field_for_schema(Callable[[str],str]).__class__
    <class 'marshmallow.fields.Function'>

    >>> field_for_schema(str, metadata={"marshmallow_field": marshmallow.fields.Url()}).__class__
    <class 'marshmallow.fields.Url'>

    >>> field_for_schema(Optional[str]).__class__
    <class 'marshmallow.fields.String'>

    >>> field_for_schema(NewType('UserId', int)).__class__
    <class 'marshmallow.fields.Integer'>

    >>> field_for_schema(NewType('UserId', int), default=0).default
    0

    >>> class Color(Enum):
    ...   red = 1
    >>> field_for_schema(Color).__class__
    <class 'marshmallow_enum.EnumField'>

    >>> field_for_schema(Any).__class__
    <class 'marshmallow.fields.Raw'>
    """

    metadata = {} if metadata is None else dict(metadata)
    if default is not marshmallow.missing:
        metadata.setdefault("default", default)
        # metadata.setdefault("missing", default)
        metadata.setdefault("required", False)
    else:
        metadata.setdefault("required", True)

    # If the field was already defined by the user
    predefined_field = metadata.get("marshmallow_field")
    if predefined_field:
        return predefined_field

    # Base types
    if typ in _native_to_marshmallow:
        return _native_to_marshmallow[typ](**metadata)

    # Generic types
    origin: type = typing_inspect.get_origin(typ)

    if origin in (list, List):
        list_elements_type = typing_inspect.get_args(typ, True)[0]
        return marshmallow.fields.List(field_for_schema(list_elements_type), **metadata)
    elif origin in (dict, Dict):
        key_type, value_type = typing_inspect.get_args(typ, True)
        return marshmallow.fields.Dict(
            keys=field_for_schema(key_type),
            values=field_for_schema(value_type),
            **metadata,
        )
    elif origin in (collections.abc.Callable, Callable):
        return marshmallow.fields.Function(**metadata)
    elif typing_inspect.is_optional_type(typ):
        subtyp = next(t for t in typing_inspect.get_args(typ) if t is not NoneType)
        # Treat optional types as types with a None default
        metadata["default"] = metadata.get("default", None)
        metadata["missing"] = metadata.get("missing", None)
        metadata["required"] = False
        return field_for_schema(subtyp, metadata=metadata)
    # typing.NewType returns a function with a __supertype__ attribute
    newtype_supertype = getattr(typ, "__supertype__", None)
    if newtype_supertype and inspect.isfunction(typ):
        metadata.setdefault("description", typ.__name__)
        return field_for_schema(newtype_supertype, metadata=metadata, default=default)

    # enumerations
    if type(typ) is EnumMeta:
        import marshmallow_enum

        return marshmallow_enum.EnumField(typ, **metadata)

    # Nested attr
    forward_reference = getattr(typ, "__forward_arg__", None)
    nested = forward_reference or class_schema(typ)
    return marshmallow.fields.Nested(nested, **metadata)


def _base_schema(clazz: type) -> Type[marshmallow.Schema]:
    class BaseSchema(marshmallow.Schema):
        @marshmallow.post_load
        def make_data_class(self, data, **kwargs):
            return clazz(**data)

    return BaseSchema


def _get_field_default(field: attr.ib):
    """
    Return a marshmallow default value given a dataclass default value

    >>> @dataclass
    ... class A:
    ...     x: int = attr.ib()
    >>> _get_field_default(attr.fields(A).x)
    <marshmallow.missing>
    """
    if isinstance(field.default, attr.Factory):
        return field.default.factory
    elif field.default is attr.NOTHING:
        return marshmallow.missing
    return field.default
