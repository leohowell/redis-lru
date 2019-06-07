# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2018-12-31
"""

import time
import types
import atexit
import pickle
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
                 clear_on_exit=False):
        self.client = client
        self.max_size = max_size
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl

        if clear_on_exit:
            atexit.register(self.clear_all_cache)

    def __call__(self, ttl=60 * 15):
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
                    result = func(*args, **kwargs)
                    self.set(key, result, ttl)
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
            for arg in args:
                hash(arg)
            for value in kwargs.values():
                hash(value)
        except TypeError:
            raise ArgsUnhashable()

        return '{}:{}:{}{!r}:{!r}'.format(self.key_prefix, func.__module__,
                                          func.__qualname__, args, kwargs)




# from diskcache import Cache
# client = redis.StrictRedis()
#
# cache = RedisLRU(client, 0)
#
# cache['x'] = 10
#
#
# @cache(ttl=10)
# def foo(x):
#     print('foo ', x)
#     return x + 1
#
#
# @cache
# def bar():
#     print('bar')
#     pass
#
#
# print(foo(1))
# print(bar())
