# -*- coding: utf-8 -*-

"""
@author: leohowell
@date: 2018/2/12
"""

import setuptools
from distutils.core import setup

description = (
    'LRU cache for Python. Use Redis as backend. '
    'Provides a dictionary-like object as well as a method decorator.'
)

with open('README.rst') as fd:
    long_description = fd.read()

with open('CHANGES.txt') as fd:
    long_description = '{}\n\n{}'.format(long_description, fd.read())

setup(
    name='redis-lru',
    version='0.1.0',
    description=description,
    long_description=long_description,
    long_description_content_type='text/x-rst',
    author='Leo Howell',
    author_email='leohowell.com@gmail.com',
    license='BSD',
    url='https://github.com/leohowell/redis-lru',
    packages=['redis_lru'],
    install_requires=['redis'],
    python_requires='>=3.4',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: Web Environment',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
)
