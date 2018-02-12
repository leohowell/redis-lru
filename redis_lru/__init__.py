# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2018/2/11
"""

import json
import time
from functools import wraps

import redis


class RedisLRUCacheException(Exception):
    pass


class LRUSerializeError(RedisLRUCacheException):
    pass


def redis_lru_cache_function(max_size=1024, expiration=15 * 60,
                             node=None, cache=None):
    """
    >>> @redis_lru_cache_function(20, 1)
    ... def f(x):
    ...    print("Calling f(" + str(x) + ")")
    ...    return x
    >>> f(3)
    Calling f(3)
    3
    >>> f(3)
    3
    """
    node = node or redis.StrictRedis()

    def wrapper(func):
        if not cache:
            unique_key = '{}#{}'.format(func.__module__, func.__name__)
            lru_cache = RedisLRUCacheDict(
                unique_key, max_size, expiration, node
            )
        else:
            lru_cache = cache

        def inner(*args, **kwargs):
            key = repr((args, kwargs))
            try:
                return lru_cache[key]
            except (KeyError, LRUSerializeError):
                value = func(*args, **kwargs)
                try:
                    lru_cache[key] = value
                except TypeError as err:
                    raise LRUSerializeError(err)
                return value
        return inner

    return wrapper


def joint_key(method):
    @wraps(method)
    def wrapper(self, key, *args, **kwargs):
        key = 'lru-value:{}#{}'.format(self.unique_key, key)
        return method(self, key, *args, **kwargs)
    return wrapper


class RedisLRUCacheDict(object):
    """ A dictionary-like object, supporting LRU caching semantics.
    >>> d = RedisLRUCacheDict('unique_key', max_size=3, expiration=1)
    >>> d['foo'] = 'bar'
    >>> import sys
    >>> PY3 = sys.version_info >= (3,)
    >>> if PY3:
    ...     x = d['foo'].decode('utf-8')
    ... else:
    ...     x = d['foo']
    >>> print(x)
    bar
    >>> import time
    >>> time.sleep(1.1) # 1.1 seconds > 1 second cache expiry of d
    >>> d['foo']
    Traceback (most recent call last):
        ...
    KeyError: 'foo'
    >>> d['a'] = 'A'
    >>> d['b'] = 'B'
    >>> d['c'] = 'C'
    >>> d['d'] = 'D'
    >>> d['a'] # Should return value error, since we exceeded the max cache size
    Traceback (most recent call last):
        ...
    KeyError: 'a'
    """

    STAT_KEY_EXPIRATION = 30 * 24 * 60 * 60  # 30 day

    def __init__(self, unique_key, max_size=1024, expiration=15*60,
                 node=None, clear_stat=False, hidden_exception=True):
        self.max_size = max_size
        self.expiration = expiration
        self.unique_key = unique_key
        self.batch_size = (self.max_size // 10) or 1
        self.hidden_exception = hidden_exception

        self.cache = node or redis.StrictRedis()

        self.access_key = 'lru-access:{}'.format(unique_key)  # sorted set
        self.stat_key = 'lru-stat:{}'.format(unique_key)      # hash set

        if clear_stat:
            self.cache.delete(self.stat_key)

    def report_usage(self):
        stat = self.cache.hgetall(self.stat_key)
        access = stat.get('hit', 0) + stat.get('miss', 0)
        stat['access'] = access
        return stat

    @property
    def size(self):
        return self.cache.zcard(self.access_key)

    @joint_key
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def _ensure_room(self):
        current_size = self.size
        if current_size < self.max_size:
            return True

        keys = self.cache.zrange(self.access_key, 0, self.batch_size)
        p = self.cache.pipeline()
        for k in keys:
            p.delete(k)
            p.zrem(self.access_key, k)
        p.execute()
        return False

    @joint_key
    def __setitem__(self, key, value):
        try:
            value = json.dumps(value)
        except TypeError as err:
            p1 = self.cache.pipeline()
            p1.hincrby(self.stat_key, 'serialize_error', 1)
            p1.expire(self.stat_key, self.STAT_KEY_EXPIRATION)
            p1.execute()
            if not self.hidden_exception:
                raise LRUSerializeError(err)
            return None

        self._ensure_room()
        p = self.cache.pipeline()
        p.setex(key, self.expiration, value)

        # update access zset
        p.zadd(self.access_key, time.time(), key)
        p.expire(self.access_key, self.expiration)

        # update stat hset
        p.hincrby(self.stat_key, 'set', 1)
        p.expire(self.stat_key, self.STAT_KEY_EXPIRATION)

        p.execute()

    @joint_key
    def __delitem__(self, key):
        p = self.cache.pipeline()
        p.delete(key)
        p.zrem(self.access_key, key)
        p.expire(self.access_key, self.expiration)

        # update stat hset
        p.hincrby(self.stat_key, 'del', 1)
        p.expire(self.stat_key, self.STAT_KEY_EXPIRATION)

        p.execute()

    @joint_key
    def __getitem__(self, key):
        value = self.cache.get(key)
        if value is None:
            key = key.rsplit('#', 1)[1]

            # update stat hset
            p1 = self.cache.pipeline()
            p1.hincrby(self.stat_key, 'miss', 1)
            p1.expire(self.stat_key, self.STAT_KEY_EXPIRATION)
            p1.execute()

            raise KeyError(key)
        else:
            p2 = self.cache.pipeline()
            p2.zadd(self.access_key, time.time(), key)
            p2.expire(self.access_key, self.expiration)

            # update stat hset
            p2.hincrby(self.stat_key, 'hit', 1)
            p2.expire(self.stat_key, self.STAT_KEY_EXPIRATION)

            p2.execute()

            try:
                value = json.loads(value)
            except (TypeError, ValueError) as err:
                if not self.hidden_exception:
                    raise LRUSerializeError(err)
                else:
                    raise KeyError(key)
            return value

    @joint_key
    def __contains__(self, key):
        return bool(self.cache.exist(key))


if __name__ == "__main__":
    import doctest

    doctest.testmod()
