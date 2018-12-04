# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2018/2/11
"""

import json
import time
import logging
from functools import wraps
from contextlib import contextmanager

import redis

from redis_lru.utils import sha1, get_my_caller


logger = logging.getLogger(__name__)


def redis_lru_cache(max_size=1024, expiration=15 * 60, node=None,
                    cache=None):
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
    node = node or redis.StrictRedis()

    def wrapper(func):
        if not cache:
            unique_key = '{}#{}'.format(func.__module__, func.__name__)
            lru_cache = RedisLRUCacheDict(unique_key, max_size,
                                          expiration, node)
        else:
            lru_cache = cache

        def inner(*args, **kwargs):
            key = repr((args, kwargs))
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
        key = 'lru-value:{}{}{}'.format(
            self.unique_key, RedisLRUCacheDict.KEY_DELIMITER, key
        )
        return method(self, key, *args, **kwargs)
    return wrapper


@contextmanager
def redis_pipeline(node):
    p = node.pipeline()
    yield p
    p.execute()


class RedisLRUCacheDict(object):
    """ A dictionary-like object, supporting LRU caching semantics.
    >>> d = RedisLRUCacheDict('unique_key', max_size=3, expiration=1)
    >>> d['foo'] = 'bar'
    >>> import sys
    >>> PY3 = sys.version_info >= (3,)
    >>> if PY3:
    ...     x = d['foo']
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

    EXPIRATION_STAT_KEY = 30 * 86400  # 30 day

    HIT = 'HIT'
    MISS = 'MISS'
    POP = 'POP'
    SET = 'SET'
    DEL = 'DEL'
    DUMPS_ERROR = 'DUMPS_ERROR'
    LOADS_ERROR = 'LOADS_ERROR'

    KEY_DELIMITER = '#=#'

    ONCE_CLEAN_RATIO = 0.1

    def __init__(self, unique_key=None, max_size=1024, expiration=15*60,
                 node=None, clear_stat=False):
        if unique_key:
            try:
                unique_key = str(unique_key)
                assert self.KEY_DELIMITER not in unique_key
            except Exception:
                raise ValueError('Invalid unique key: {}'.format(unique_key))
            self.unique_key = unique_key
        else:
            self.unique_key = self.generate_unique_key()
            logger.warning('Generate `unique key`: {}'.format(self.unique_key))

        self.max_size = max_size
        self.expiration = expiration
        self.node = node or redis.StrictRedis()

        self.access_key = 'lru-access:{}'.format(self.unique_key)  # sorted set
        self.stat_key = 'lru-stat:{}'.format(self.unique_key)      # hash set

        self.once_clean_size = int(self.max_size * self.ONCE_CLEAN_RATIO)

        if clear_stat:
            self.node.delete(self.stat_key)

    def report_usage(self):
        return self.node.hgetall(self.stat_key)

    @property
    def size(self):
        return self.node.zcard(self.access_key)

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

        keys = self.node.zrange(self.access_key, 0, self.once_clean_size)

        with redis_pipeline(self.node) as p:
            for k in keys:
                p.delete(k)
                p.zrem(self.access_key, k)
            p.hincrby(self.stat_key, self.POP, len(keys))

        return False

    @joint_key
    def __setitem__(self, key, value):
        try:
            value = json.dumps(value)
        except Exception:  # here too broad exception clause, just ignore it
            with redis_pipeline(self.node) as p:
                p.hincrby(self.stat_key, self.DUMPS_ERROR, 1)
                p.expire(self.stat_key, self.EXPIRATION_STAT_KEY)
            return

        self._ensure_room()

        with redis_pipeline(self.node) as p:
            p.setex(key, self.expiration, value)

            p.zadd(self.access_key, time.time(), key)
            p.expire(self.access_key, self.expiration)

            p.hincrby(self.stat_key, self.SET, 1)
            p.expire(self.stat_key, self.EXPIRATION_STAT_KEY)

    @joint_key
    def __delitem__(self, key):
        with redis_pipeline(self.node) as p:
            p.delete(key)
            p.zrem(self.access_key, key)
            p.expire(self.access_key, self.expiration)

            p.hincrby(self.stat_key, self.DEL, 1)
            p.expire(self.stat_key, self.EXPIRATION_STAT_KEY)

    @joint_key
    def __getitem__(self, key):
        value = self.node.get(key)
        if value is None:
            with redis_pipeline(self.node) as p:
                p.hincrby(self.stat_key, self.MISS, 1)
                p.expire(self.stat_key, self.EXPIRATION_STAT_KEY)
                p.execute()

            real_key = key.split(self.KEY_DELIMITER, 1)[1]
            raise KeyError(real_key)
        else:
            try:
                if type(value) is bytes:
                    value = json.loads(value.decode('utf-8'))
                else:
                    value = json.loads(value)
            except Exception:
                with redis_pipeline(self.node) as p:
                    p.delete(key)
                    p.hincrby(self.stat_key, self.LOADS_ERROR, 1)
                    p.expire(self.stat_key, self.EXPIRATION_STAT_KEY)
                raise KeyError(key)

            with redis_pipeline(self.node) as p:
                p.zadd(self.access_key, time.time(), key)
                p.expire(self.access_key, self.expiration)

                p.hincrby(self.stat_key, self.HIT, 1)
                p.expire(self.stat_key, self.EXPIRATION_STAT_KEY)

            return value

    @joint_key
    def __contains__(self, key):
        return bool(self.node.exist(key))

    @classmethod
    def generate_unique_key(cls):
        filename, line_number, function_name, lines, index = get_my_caller(3)
        logger.warning(
            'caller: {} -> {}:{}'.format(filename, function_name, line_number)
        )
        return sha1(filename, line_number, function_name, lines, index)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
