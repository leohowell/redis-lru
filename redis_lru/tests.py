# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2018/2/14
"""

import time
import unittest

from redis_lru import redis_lru_cache, RedisLRUCacheDict


class RedisLRUCacheDecoratorTestCase(unittest.TestCase):
    def setUp(self):
        self.test_cache_working_flag = 0
        self.test_expire_working_flag = 0

    @redis_lru_cache(max_size=3, expiration=2)
    def foo(self):
        self.test_cache_working_flag += 1
        self.test_expire_working_flag += 1

        return {'content_type': 'text/html; charset=UTF-8'}

    def test_cache_working(self):
        content_type1 = self.foo()
        content_type2 = self.foo()
        self.assertEqual(content_type1, content_type2)
        self.assertEqual(self.test_cache_working_flag, 1)

    def test_expire_working(self):
        content_type1 = self.foo()
        content_type2 = self.foo()
        time.sleep(2)
        content_type3 = self.foo()
        self.assertEqual(content_type1, content_type2)
        self.assertEqual(content_type1, content_type3)
        self.assertEqual(self.test_expire_working_flag, 2)


class RedisLRUCacheDictTestCase(unittest.TestCase):
    def test_cache_dict_basic(self):
        cache = RedisLRUCacheDict(max_size=3, expiration=2)
        value = 'aaa'
        cache['a'] = value
        self.assertEqual(cache['a'], value)

    def test_expire(self):
        cache = RedisLRUCacheDict(max_size=3, expiration=2)
        value = 'aaa'
        cache['a'] = value
        self.assertEqual(cache['a'], value)
        time.sleep(2)
        with self.assertRaises(KeyError):
            print(cache['a'])

    def test_max_size(self):
        cache = RedisLRUCacheDict(max_size=3, expiration=2)
        cache['a'] = 'aaa'
        cache['b'] = 'bbb'
        cache['c'] = 'ccc'
        cache['d'] = 'ddd'
        self.assertEqual(cache['b'], 'bbb')
        self.assertEqual(cache['c'], 'ccc')
        self.assertEqual(cache['d'], 'ddd')
        with self.assertRaises(KeyError):
            print(cache['a'])


if __name__ == '__main__':
    unittest.main()
