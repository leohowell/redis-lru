# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2018/2/11
"""

from redis_lru.lru import redis_lru_cache, RedisLRUCacheDict
from redis_lru.utils import init_logger


__all__ = ['redis_lru_cache', 'RedisLRUCacheDict']


init_logger()
