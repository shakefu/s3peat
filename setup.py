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
        # Make sure to also update the version in s3peat/__init__.py
        version='0.4.6',
        author="Jacob Alheid",
        author_email="jake@about.me",
        description="Fast uploader to S3",
        long_description=readme(),
        url='http://github.com/shakefu/s3peat',
        packages=find_packages(exclude=['test']),
        install_requires=[
            'boto',
            'pytool',
            ],
        entry_points={
            'console_scripts': {
                "s3peat = s3peat.scripts:Main.console_script",
                },
            },
        # test_suite='nose.collector',
        # tests_require=[
        #     'nose',
        #     'mock',
        #    ],
        )

