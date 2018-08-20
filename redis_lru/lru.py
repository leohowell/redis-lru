# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2018/2/11
"""

import json
import time
import logging
import uuid
from functools import wraps
from contextlib import contextmanager

import redis


STAT_KEY_EXPIRATION = 30 * 24 * 60 * 60  # 30 days
NAMESPACE_DELIMITER = b':'
PREFIX_DELIMITER = NAMESPACE_DELIMITER * 2


logger = logging.getLogger(__name__)


def redis_lru_cache(max_size=1024, expiration=15 * 60, client=None,
                    cache=None, eviction_size=None, typed_hash_args=False):
    """
    >>> @redis_lru_cache(20, 1)
    ... def f(x):
    ...    print("Calling f(" + str(x) + ")")
    ...    return x
    >>> f(3)
    Calling f(3)
    3
    >>> f(3)
    3
    """

    def _hash_args(args, kwargs):
        return hash(
            (hash(args),
             hash(frozenset(kwargs.items()))
             )
        )

    def _typed_hash_args(args, kwargs):
        return hash((
            _hash_args(args, kwargs),
            hash(type(x) for x in args),
            hash(type(x) for x in kwargs.values()),
        ))

    def wrapper(func):
        if cache is None:
            unique_key = NAMESPACE_DELIMITER.join(
                x.encode().replace(b'.', NAMESPACE_DELIMITER)
                for x in (func.__module__, func.__qualname__)
            )
            lru_cache = RedisLRUCacheDict(
                unique_key=unique_key, max_size=max_size, expiration=expiration,
                client=client, eviction_size=eviction_size
            )
        else:
            lru_cache = cache

        _arg_hasher = _typed_hash_args if typed_hash_args else _hash_args

        @wraps(func)
        def inner(*args, **kwargs):
            try:
                key = hex(_arg_hasher(args, kwargs))
            except TypeError:
                raise RuntimeError(
                    'All arguments to lru-cached functions must be hashable.'
                )

            try:
                return lru_cache[key]
            except KeyError:
                value = func(*args, **kwargs)
                lru_cache[key] = value
                return value

        return inner

    return wrapper


def joint_key(method):
    @wraps(method)
    def wrapper(self, key, *args, **kwargs):
        key = b'lru-value:' + self.unique_key + PREFIX_DELIMITER + key.encode()
        return method(self, key, *args, **kwargs)
    return wrapper


@contextmanager
def redis_pipeline(client):
    p = client.pipeline()
    yield p
    p.execute()


class RedisLRUCacheDict:
    """ A dictionary-like object, supporting LRU caching semantics.
    >>> d = RedisLRUCacheDict('unique_key', max_size=3, expiration=1)
    >>> d['foo'] = 'bar'
    >>> x = d['foo']
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

    def __init__(self, unique_key=None, max_size=1024, expiration=15*60,
                 client=None, clear_stat=False, eviction_size=None):

        if unique_key is not None:
            if isinstance(unique_key, str):
                unique_key = unique_key.encode()

            if PREFIX_DELIMITER in unique_key:
                raise ValueError('Invalid unique key: {}'.format(unique_key))
            self.unique_key = unique_key

        else:
            self.unique_key = unique_key = uuid.uuid4().bytes
            logger.debug('Generated `unique key`: {}'.format(self.unique_key))

        self.max_size = max_size
        self.expiration = expiration
        self.client = client or redis.StrictRedis()

        self.access_key = b'lru-access:{}' + unique_key  # sorted set
        self.stat_key = b'lru-stat:{}' + unique_key      # hash set

        if eviction_size is None:
            self.eviction_range = int(self.max_size * 0.1)
        else:
            self.eviction_range = eviction_size - 1

        if clear_stat:
            self.client.delete(self.stat_key)

    def report_usage(self):
        return self.client.hgetall(self.stat_key)

    @joint_key
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    @joint_key
    def __setitem__(self, key, value):
        if self.client.zcard(self.access_key) >= self.max_size:
            keys = self.client.zrange(self.access_key, 0, self.eviction_range)
            with redis_pipeline(self.client) as p:
                p.delete(*keys)
                p.zrem(self.access_key, *keys)
                p.hincrby(self.stat_key, 'POP', len(keys))

        value = json.dumps(value)

        with redis_pipeline(self.client) as p:
            p.setex(key, self.expiration, value)

            p.zadd(self.access_key, time.time(), key)
            p.expire(self.access_key, self.expiration)

            p.hincrby(self.stat_key, 'SET', 1)
            p.expire(self.stat_key, STAT_KEY_EXPIRATION)

    @joint_key
    def __delitem__(self, key):
        with redis_pipeline(self.client) as p:
            p.delete(key)

            p.zrem(self.access_key, key)
            p.expire(self.access_key, self.expiration)

            p.hincrby(self.stat_key, 'DEL', 1)
            p.expire(self.stat_key, STAT_KEY_EXPIRATION)

    @joint_key
    def __getitem__(self, key):
        value = self.client.get(key)
        if value is None:
            with redis_pipeline(self.client) as p:
                p.hincrby(self.stat_key, 'MISS', 1)
                p.expire(self.stat_key, STAT_KEY_EXPIRATION)

            real_key = key.split(PREFIX_DELIMITER, 1)[1]
            raise KeyError(real_key.decode())
        else:
            value = json.loads(value)

            with redis_pipeline(self.client) as p:
                p.zadd(self.access_key, time.time(), key)
                p.expire(self.access_key, self.expiration)

                p.hincrby(self.stat_key, 'HIT', 1)
                p.expire(self.stat_key, STAT_KEY_EXPIRATION)

            return value

    @joint_key
    def __contains__(self, key):
        return bool(self.client.exists(key))


if __name__ == "__main__":
    import doctest

    doctest.testmod()
