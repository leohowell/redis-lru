# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2018/2/14
"""

import sys
import hashlib
import logging
import inspect


PY3 = sys.version_info >= (3,)


def get_my_caller(level=2):
    """
    >>> def foo():
    ...     get_my_caller(2)  # return function `xxx` info
    ...     get_my_caller(3)  # return function `yyy` info
    ...
    >>> def xxx():
    ...     foo()
    ...
    >>> def yyy():
    ...     xxx()
    """
    current_frame = inspect.currentframe()
    _, filename, line_number, function_name, lines, index = \
        inspect.getouterframes(current_frame)[level]
    return filename, line_number, function_name, lines, index


def to_bytes(s):
    if isinstance(s, bytes):
        return s

    if PY3:
        s = s.encode('utf-8')

    return bytes(s)


def sha1(*s):
    string = '#'.join([str(item) for item in s])
    return hashlib.sha1(to_bytes(string)).hexdigest()


def init_logger():
    logger = logging.getLogger('redis_lru')
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(levelname)1.1s %(asctime)s %(module)s.'
                                  '%(funcName)s:%(lineno)d] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.WARNING)
