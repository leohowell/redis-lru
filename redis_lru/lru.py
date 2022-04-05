# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2018-12-31
"""

import datetime
import time
import types
import atexit
import pickle
from collections.abc import Hashable
from functools import wraps

import redis


class ArgsUnhashable(Exception):
    pass


class RedisLRU:
    def __init__(self,
                 client: redis.StrictRedis,
                 max_size=2 ** 20,
                 default_ttl=15 * 60,
                 key_prefix='RedisLRU',
                 clear_on_exit=False,
                 exclude_values=None,
                 expire_on=None
                 ):
        self.client = client
        self.max_size = max_size
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self.exclude_values = exclude_values if type(exclude_values) is set else set()
        self.expire_on = expire_on

        if clear_on_exit:
            atexit.register(self.clear_all_cache)

    def __call__(self, ttl=None, expire_on=None):
        func = None

        def inner(*args, **kwargs):
            try:
                key = self._decorator_key(func, *args, **kwargs)
            except ArgsUnhashable:
                return func(*args, **kwargs)
            else:
                try:
                    return self[key]
                except KeyError:
                    if expire_on is not None:
                        _ttl = self._get_ttl_from_expiry_date(expire_on)
                    elif self.expire_on is not None:
                        _ttl = self._get_ttl_from_expiry_date(self.expire_on)
                    else:
                        _ttl = ttl
                    result = func(*args, **kwargs)
                    self.set(key, result, _ttl)
                    return result

        # decorator without arguments
        if callable(ttl):
            func = ttl
            ttl = 60 * 15
            return wraps(func)(inner)

        # decorator with arguments
        def wrapper(f):
            nonlocal func
            func = f
            return wraps(func)(inner)

        return wrapper

    def __setitem__(self, key, value):
        self.set(key, value)

    def __getitem__(self, key):
        if not self.client.exists(key):
            raise KeyError()
        else:
            result = self.client.get(key)
            return pickle.loads(result)

    def set(self, key, value, ttl=None):
        if isinstance(value, Hashable) and value in self.exclude_values:
            return
        ttl = ttl or self.default_ttl
        value = pickle.dumps(value)
        return self.client.setex(key, ttl, value)

    def get(self, key, default=None):
        """
        Fetch a given key from the cache. If the key does not exist, return
        default, which itself defaults to None.
        """

        try:
            return self[key]
        except KeyError:
            return default

    def clear_all_cache(self):
        def delete_keys(items):
            pipeline = self.client.pipeline()
            for item in items:
                pipeline.delete(item)
            pipeline.execute()

        match = '{}*'.format(self.key_prefix)
        keys = []
        for key in self.client.scan_iter(match, count=100):
            keys.append(key)
            if len(keys) >= 100:
                delete_keys(keys)
                keys = []
                time.sleep(0.01)
        else:
            delete_keys(keys)

    def _decorator_key(self, func: types.FunctionType, *args, **kwargs):
        try:
            hash_arg = tuple([hash(arg) for arg in args])
            hash_kwargs = tuple([hash(value) for value in kwargs.values()])
        except TypeError:
            raise ArgsUnhashable()

        return '{}:{}:{}{!r}:{!r}'.format(self.key_prefix, func.__module__,
                                          func.__qualname__, hash_arg, hash_kwargs)

    def _get_ttl_from_expiry_date(self, expire_on):
        if expire_on is None:
            return self.default_ttl
        else: # calculate the seconds until the datetime <expire_on> is reached
            now = datetime.datetime.now()
            return round((datetime.timedelta(hours=24) - (now - now.replace(
                hour=expire_on.hour,
                minute=expire_on.minute,
                second=expire_on.second,
                microsecond=expire_on.microsecond))).total_seconds() % (24 * 3600))
