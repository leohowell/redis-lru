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

redis-lru supports CPython 2.7, 3.4+

For the most part, you can just use it like this:

.. code-block:: python

    from redis_lru import redis_lru_cache_function

    client = redis.StrictRedis()

    @redis_lru_cache_function(max_size=1024, expiration=15*60, node=client)
    def f(x):
        print("Calling f({})".format(str(x)))
        return x


    f(3) # This will print "Calling f(3)", will return 3
    f(3) # This will not print anything, but will return 3 (unless 15 minutes have passed between the first and second function call).


One can also create an `RedisLRUCacheDict` object, which have a redis backend behind with LRU eviction semantics:

.. code-block:: python

    from redis_lru import RedisLRUCacheDict

    client = redis.StrictRedis()

    d = RedisLRUCacheDict('unique_key', max_size=3, expiration=3, node=client)

    d['foo'] = 'bar'
    print(d['foo']) # prints "bar"

    import time
    time.sleep(4) # 4 seconds > 3 second cache expiry of d
    print(d['foo']) # KeyError

In order to configure the decorator in a more detailed manner, or share a cache across functions, one can create a cache and pass it in as an argument to the cached function decorator:


.. code-block:: python

    d = RedisLRUCacheDict(max_size=3, expiration=3, node=client)

    @redis_lru_cache_function(cache=d)
    def f(x):
        return x/2


The doctests in the code provide more examples.
