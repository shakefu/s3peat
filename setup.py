import multiprocessing, logging # Fix atexit bug
from setuptools import setup, find_packages


def readme():
    try:
        return open('README.rst').read()
    except:
        pass
    return ''


setup(
        name='s3peat',
        version='0.1.1',
        author="Jacob Alheid",
        author_email="jake@about.me",
        description="Fast uploader to S3",
        long_description=readme(),
        url='http://github.com/shakefu/s3peat',
        packages=find_packages(exclude=['test']),
        # install_requires=['simplejson >= 3.2.0'],
        # test_suite='nose.collector',
        # tests_require=[
        #     'nose',
        #     'mock',
        #    ],
        )

