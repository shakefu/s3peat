"""
This is a very slow test that actually uses S3.

"""
import logging

import s3peat


def test():
    import re
    import time
    path = 'test'
    bucket = s3peat.S3Bucket('aboutme-sandbox', AWS_KEY, AWS_SECRET)
    prefix = 'testing-{}/'.format(time.time())
    failures = s3peat.sync_to_s3(path, prefix, bucket, concurrency=500)
    if not failures:
        print "No failures"
    else:
        print "Failed:", failures


if __name__ == '__main__':
    logging.basicConfig()
    logging.getLogger().setLevel(1)
    logging.getLogger('boto').setLevel(logging.INFO)
    globals().update({
        'AWS_KEY': 'AKIAIETDO256VZTFZM6Q',
        'AWS_SECRET': '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'
        })
    test()

