# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2019-06-07
"""

import datetime
import unittest
import time
import redis

from lru import RedisLRU


class RedisLRUTest(unittest.TestCase):
    @classmethod
    def get_cache(cls, **kwargs):
        client = redis.StrictRedis('127.0.0.1', 6379)
        return RedisLRU(client, clear_on_exit=True, **kwargs)

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

    def test_lru_dict_value(self):
        cache = self.get_cache()
        flag = 0

        @cache
        def foo(x, y=10):
            nonlocal flag
            flag += 1
            return {x: y}

        result1 = foo(10)
        self.assertEqual(result1, {10: 10})
        self.assertEqual(flag, 1)

        result2 = foo(10)
        self.assertEqual(result2, {10: 10})
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

    def test_exclude(self):
        cache = self.get_cache(exclude_values={20})

        flag = 0

        @cache
        def baz(x, y=10):
            nonlocal flag
            flag += 1
            return x + y

        result1 = baz(10)
        self.assertEqual(result1, 20)
        self.assertEqual(flag, 1)

        result2 = baz(10)
        self.assertEqual(result2, 20)
        self.assertEqual(flag, 2)

        result3 = baz(20)
        self.assertEqual(result3, 30)
        self.assertEqual(flag, 3)

        result4 = baz(20)
        self.assertEqual(result4, 30)
        self.assertEqual(flag, 3)

    def test_expire_on(self):
        _time = (datetime.datetime.now() + datetime.timedelta(seconds=5)).time()
        cache = self.get_cache(expire_on=_time)
        flag = 0

        @cache
        def qux(x, y=10):
            nonlocal flag
            flag += 1
            return x + y

        # call first time, init cache and expect flag to be 1
        self.assertEqual(qux(10), 20)
        self.assertEqual(flag, 1)

        # call second time, flag value should be as before (1)
        self.assertEqual(qux(10), 20)
        self.assertEqual(flag, 1)

        # wait for 5 seconds, ttl should be expired and function is processed
        time.sleep(5)
        self.assertEqual(qux(10), 20)
        self.assertEqual(flag, 2)

    def test_expire_on_decorator(self):
        _time = (datetime.datetime.now() + datetime.timedelta(seconds=10)).time()
        cache = self.get_cache(default_ttl=1)  # default ttl=1 should be overwritten by decorator params
        flag = 0

        @cache(expire_on=_time)
        def moo(x, y=10):
            nonlocal flag
            flag += 1
            return x + y

        # call first time, init cache and expect flag to be 1
        self.assertEqual(moo(10), 20)
        self.assertEqual(flag, 1)

        # call second time, flag value should be as before (1)
        self.assertEqual(moo(10), 20)
        self.assertEqual(flag, 1)

        # wait for 5 seconds, flag value should be as before (1), as a custom expire_on date is passed with the decorator
        time.sleep(5)
        self.assertEqual(moo(10), 20)
        self.assertEqual(flag, 1)

        # wait for 7 seconds, ttl should be expired now
        time.sleep(7)
        self.assertEqual(moo(10), 20)
        self.assertEqual(flag, 2)


if __name__ == '__main__':
    unittest.main()
