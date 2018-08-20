# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2018/2/14
"""

import logging


def init_logger():
    logger = logging.getLogger('redis_lru')
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(levelname)1.1s %(asctime)s %(module)s.'
                                  '%(funcName)s:%(lineno)d] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.WARNING)
