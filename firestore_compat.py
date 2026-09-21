# Firestore compatibility layer for the existing Flask/SQLAlchemy-style app.
import datetime as dt
import os
import sys
from functools import total_ordering

import firebase_admin
from firebase_admin import firestore

try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(options={
        "projectId": os.getenv("GOOGLE_CLOUD_PROJECT") or "staff-housing"
    })

db = firestore.client()

MODEL_REGISTRY = {}
COLLECTIONS = {
    "Apartment": "apartments",
    "Resident": "residents",
    "ProjectInfo": "project_info",
    "FieldDef": "field_defs",
    "Custody": "custodies",
    "CustodyLine": "custody_lines",
}

class _Type:
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return self.name

Integer = _Type("Integer")
String = _Type("String")
Float = _Type("Float")
Text = _Type("Text")
Date = _Type("Date")
Boolean = _Type("Boolean")

class ForeignKey:
    def __init__(self, target):
        self.target = target

class Expr:
    def __init__(self, fn):
        self.fn = fn
    def __call__(self, obj):
        return self.fn(obj)
    def __and__(self, other):
        return Expr(lambda obj: self(obj) and other(obj))
    def __or__(self, other):
        return Expr(lambda obj: self(obj) or other(obj))

@total_ordering
class SortKey:
    def __init__(self, field, reverse=False):
        self.field = field
        self.reverse = reverse
    def key(self, obj):
        return getattr(obj, self.field.name, None)
    def __eq__(self, other):
        return isinstance(other, SortKey) and self.field.name == other.field.name and self.reverse == other.reverse
    def __lt__(self, other):
        return False

class Column:
    def __init__(self, type_=None, *args, **kwargs):
        self.type_ = type_
        self.default = kwargs.get("default", None)
        self.name = None
    def __set_name__(self, owner, name):
        self.name = name
    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return obj.__dict__.get(self.name)
    def __set__(self, obj, value):
        obj.__dict__[self.name] = value
    def _expr(self, fn):
        return Expr(fn)
    def __eq__(self, value):
        return self._expr(lambda obj: getattr(obj, self.name, None) == value)
    def __ne__(self, value):
        return self._expr(lambda obj: getattr(obj, self.name, None) != value)
    def __lt__(self, value):
        return self._expr(lambda obj: (getattr(obj, self.name, None) is not None and getattr(obj, self.name) < value))
    def __le__(self, value):
        return self._expr(lambda obj: (getattr(obj, self.name, None) is not None and getattr(obj, self.name) <= value))
    def __gt__(self, value):
        return self._expr(lambda obj: (getattr(obj, self.name, None) is not None and getattr(obj, self.name) > value))
    def __ge__(self, value):
        return self._expr(lambda obj: (getattr(obj, self.name, None) is not None and getattr(obj, self.name) >= value))
    def isnot(self, value):
        return self._expr(lambda obj: getattr(obj, self.name, None) is not value)
    def is_(self, value):
        return self._expr(lambda obj: getattr(obj, self.name, None) is value)
    def in_(self, values):
        values = set(values)
        return self._expr(lambda obj: getattr(obj, self.name, None) in values)
    def desc(self):
        return SortKey(self, True)
    def asc(self):
        return SortKey(self, False)

class Relationship:
    def __init__(self, target, **kwargs):
        self.target = target
        self.name = None
    def __set_name__(self, owner, name):
        self.name = name
    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        owner_name = type(obj).__name__
        if owner_name == "Apartment" and self.name == "residents":
            return Query(_new_session(), MODEL_REGISTRY["Resident"]).filter_by(apartment_id=obj.id).all()
        if owner_name == "Resident" and self.name == "apartment":
            return _load_model(MODEL_REGISTRY["Apartment"], obj.apartment_id) if obj.apartment_id else None
        if owner_name == "Custody" and self.name == "lines":
            return RelationshipCollection(obj, MODEL_REGISTRY["CustodyLine"], "custody_id")
        if owner_name == "CustodyLine" and self.name == "custody":
            return _load_model(MODEL_REGISTRY["Custody"], obj.custody_id) if obj.custody_id else None
        if owner_name == "CustodyLine" and self.name == "apartment":
            return _load_model(MODEL_REGISTRY["Apartment"], obj.apartment_id) if obj.apartment_id else None
        return None
    def __set__(self, obj, value):
        if value is None:
            return
        if self.name == "apartment" and hasattr(value, "id"):
            obj.apartment_id = value.id
        elif self.name == "custody" and hasattr(value, "id"):
            obj.custody_id = value.id

def relationship(target, **kwargs):
    return Relationship(target, **kwargs)

class _Metadata:
    def create_all(self, *args, **kwargs):
        return None

class Base:
    metadata = _Metadata()
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        MODEL_REGISTRY[cls.__name__] = cls
    def __init__(self, **kwargs):
        for name, col in _columns(type(self)).items():
            if name in kwargs:
                value = kwargs[name]
            elif col.default is not None:
                value = col.default() if callable(col.default) else col.default
            else:
                value = None
            setattr(self, name, value)

def declarative_base():
    return Base

def _columns(model_cls):
    out = {}
    for cls in reversed(model_cls.__mro__):
        for name, value in cls.__dict__.items():
            if isinstance(value, Column):
                out[name] = value
    return out

def _collection_for(model_cls):
    return COLLECTIONS[model_cls.__name__]

def _serialize(value):
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value

def _deserialize(value, column):
    if value is None:
        return None
    if column.type_ is Date and isinstance(value, str):
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value

def _model_to_dict(obj):
    data = {}
    for name, col in _columns(type(obj)).items():
        data[name] = _serialize(getattr(obj, name, None))
    return data

def _doc_to_model(model_cls, snap):
    if not snap.exists:
        return None
    raw = snap.to_dict() or {}
    values = {}
    for name, col in _columns(model_cls).items():
        values[name] = _deserialize(raw.get(name), col)
    if values.get("id") is None:
        try:
            values["id"] = int(snap.id)
        except ValueError:
            values["id"] = snap.id
    return model_cls(**values)

def _load_model(model_cls, obj_id):
    if obj_id is None:
        return None
    snap = db.collection(_collection_for(model_cls)).document(str(obj_id)).get()
    return _doc_to_model(model_cls, snap)

def _save_model(obj):
    collection = _collection_for(type(obj))
    if getattr(obj, "id", None) is None:
        obj.id = _next_id(collection)
    db.collection(collection).document(str(obj.id)).set(_model_to_dict(obj), merge=False)
    return obj

def _delete_model(obj):
    db.collection(_collection_for(type(obj))).document(str(obj.id)).delete()

def _new_session():
    return SessionFactory()

def _next_id(collection):
    ref = db.collection("counters").document(collection)
    transaction = db.transaction()
    @firestore.transactional
    def increment(transaction):
        snap = ref.get(transaction=transaction)
        current = int((snap.to_dict() or {}).get("value", 0))
        new_value = current + 1
        transaction.set(ref, {"value": new_value}, merge=True)
        return new_value
    return increment(transaction)

class RelationshipCollection:
    def __init__(self, parent, model_cls, foreign_key):
        self.parent = parent
        self.model_cls = model_cls
        self.foreign_key = foreign_key
    def _items(self):
        return Query(_new_session(), self.model_cls).filter_by(**{self.foreign_key: self.parent.id}).all()
    def append(self, obj):
        setattr(obj, self.foreign_key, self.parent.id)
        _save_model(obj)
    def __iter__(self):
        return iter(self._items())
    def __len__(self):
        return len(self._items())
    def __getitem__(self, item):
        return self._items()[item]

class Query:
    def __init__(self, session, model_cls, items=None):
        self.session = session
        self.model_cls = model_cls
        self.predicates = []
        self.sort_keys = []
        self._items_cache = items
    def _all_raw(self):
        if self._items_cache is not None:
            return list(self._items_cache)
        collection = _collection_for(self.model_cls)
        return [_doc_to_model(self.model_cls, snap) for snap in db.collection(collection).stream()]
    def filter_by(self, **kwargs):
        self.predicates.extend([Expr(lambda obj, k=k, v=v: getattr(obj, k, None) == v) for k, v in kwargs.items()])
        return self
    def filter(self, *exprs):
        self.predicates.extend(exprs)
        return self
    def order_by(self, *keys):
        self.sort_keys.extend(keys)
        return self
    def _materialize(self):
        items = [x for x in self._all_raw() if x is not None]
        for expr in self.predicates:
            if isinstance(expr, Expr):
                items = [x for x in items if expr(x)]
            elif callable(expr):
                items = [x for x in items if expr(x)]
        for key in reversed(self.sort_keys):
            if isinstance(key, SortKey):
                items.sort(key=key.key, reverse=key.reverse)
            elif isinstance(key, Column):
                items.sort(key=lambda x, k=key: (getattr(x, k.name, None) is None, getattr(x, k.name, None)))
        for item in items:
            self.session.track(item)
        return items
    def all(self):
        return self._materialize()
    def first(self):
        items = self._materialize()
        return items[0] if items else None
    def first_or_404(self):
        item = self.first()
        if item is None:
            from flask import abort
            abort(404)
        return item
    def count(self):
        return len(self._materialize())
    def delete(self, synchronize_session=False, **kwargs):
        items = self._materialize()
        for item in items:
            self.session.delete(item)
        return len(items)

class Session:
    def __init__(self):
        self._tracked = {}
        self._deleted = set()
    def query(self, model_cls):
        return Query(self, model_cls)
    def add(self, obj):
        _save_model(obj)
        self.track(obj)
    def delete(self, obj):
        if obj is None:
            return
        name = type(obj).__name__
        if name == "Apartment":
            for resident in Query(self, MODEL_REGISTRY["Resident"]).filter_by(apartment_id=obj.id).all():
                self.delete(resident)
            for line in Query(self, MODEL_REGISTRY["CustodyLine"]).filter_by(apartment_id=obj.id).all():
                self.delete(line)
        if name == "Custody":
            for line in Query(self, MODEL_REGISTRY["CustodyLine"]).filter_by(custody_id=obj.id).all():
                self.delete(line)
        _delete_model(obj)
        self._deleted.add((name, getattr(obj, "id", None)))
    def track(self, obj):
        key = (type(obj).__name__, getattr(obj, "id", None))
        if key[1] is not None:
            self._tracked[key] = obj
    def commit(self):
        for key, obj in list(self._tracked.items()):
            if key not in self._deleted:
                _save_model(obj)
    def close(self):
        return None
    def execute(self, statement):
        return None
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        self.close()

class SessionFactory:
    def __call__(self):
        return Session()
    def configure(self, **kwargs):
        return None
    def remove(self):
        return None

def sessionmaker(*args, **kwargs):
    return SessionFactory()

def scoped_session(factory):
    return factory

def create_engine(*args, **kwargs):
    return db

def select(*args, **kwargs):
    return object()

class _Func:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None
func = _Func()

def or_(*exprs):
    return Expr(lambda obj: any(e(obj) if isinstance(e, Expr) else bool(e) for e in exprs))

def and_(*exprs):
    return Expr(lambda obj: all(e(obj) if isinstance(e, Expr) else bool(e) for e in exprs))
