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
            key_prefix = NAMESPACE_DELIMITER.join(
                x.encode().replace(b'.', NAMESPACE_DELIMITER)
                for x in (func.__module__, func.__qualname__)
            )
            lru_cache = RedisLRUCacheDict(
                key_prefix=key_prefix, max_size=max_size, expiration=expiration,
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
        return method(self, self.value_key_prefix + key.encode(), *args, **kwargs)
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

    def __init__(self, key_prefix=None, max_size=1024, expiration=15 * 60,
                 client=None, clear_stat=False, eviction_size=None):

        if key_prefix is not None:
            if isinstance(key_prefix, str):
                key_prefix = key_prefix.encode()

            if PREFIX_DELIMITER in key_prefix:
                raise ValueError('Invalid unique key: {}'.format(key_prefix))

        else:
            key_prefix = uuid.uuid4().bytes
            logger.debug('Generated `unique key`: {}'.format(key_prefix))

        self.value_key_prefix = (
                b'lru-value' + NAMESPACE_DELIMITER + key_prefix + PREFIX_DELIMITER
        )
        self.max_size = max_size
        self.expiration = expiration
        self.client = client or redis.StrictRedis()

        self.access_key = b'lru-access:' + key_prefix  # sorted set
        self.stat_key = b'lru-stat:' + key_prefix      # hash set

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

        value = json.dumps(value)

        with redis_pipeline(self.client) as p:
            p.setex(key, self.expiration, value)

            p.zadd(self.access_key, time.time(), key)
            p.expire(self.access_key, self.expiration)

    @joint_key
    def __delitem__(self, key):
        with redis_pipeline(self.client) as p:
            p.delete(key)

            p.zrem(self.access_key, key)
            p.expire(self.access_key, self.expiration)

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
