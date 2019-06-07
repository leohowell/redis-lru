# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2019-06-07
"""

import unittest

import time
import redis

from lru import RedisLRU


class RedisLRUTest(unittest.TestCase):
    @classmethod
    def get_cache(cls):
        client = redis.StrictRedis('127.0.0.1', 6379)
        return RedisLRU(client, clear_on_exit=True)

    def test_lru_cache(self):
        cache = self.get_cache()
        flag = 0

        @cache
        def foo(x, y=10):
            nonlocal flag
            flag += 1
            return x + y

        result1 = foo(10)
        self.assertEqual(result1, 20)
        self.assertEqual(flag, 1)

        result2 = foo(10)
        self.assertEqual(result2, 20)
        self.assertEqual(flag, 1)

    def test_ttl(self):
        cache = self.get_cache()

        flag = 0

        @cache(ttl=1)
        def bar(x, y=10):
            nonlocal flag
            flag += 1
            return x + y

        result1 = bar(10)
        self.assertEqual(result1, 20)
        self.assertEqual(flag, 1)

        result2 = bar(10)
        self.assertEqual(result2, 20)
        self.assertEqual(flag, 1)

        time.sleep(1.1)
        result3 = bar(10)
        self.assertEqual(result3, 20)
        self.assertEqual(flag, 2)


if __name__ == '__main__':
    unittest.main()
