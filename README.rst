redis-lru
=========

Installation
------------

.. code-block:: bash

    pip install redis-lru


Introduction
------------

It's often useful to have an lru redis cache. Of course, it's also desirable not to have the cache grow too large, and cache expiration is often desirable.
This module provides such a cache.

redis-lru supports CPython 3.4+

For the most part, you can just use it like this:

.. code-block:: python

    import redis
    from redis_lru import RedisLRU

    client = redis.StrictRedis()
    cache = RedisLRU(client)

    @cache
    def f(x):
        print("Calling f({})".format(x))
        return x


    f(3) # This will print "Calling f(3)", will return 3
    f(3) # This will not print anything, but will return 3 (unless 15 minutes have passed between the first and second function call).

