"""
s3peat - Fast uploading directories to S3

.. rubric:: Example usage

.. code-block:: python

    from s3peat import S3Bucket, sync_to_s3

    # Create a S3Bucket instance, which is used to create connections to S3
    bucket = S3Bucket('my-bucket', AWS_KEY, AWS_SECRET)

    # Call the sync_to_s3 method
    failures = sync_to_s3(directory='my/directory', prefix='my/key,
        bucket=bucket, concurrency=50)

    # A list of filenames will be returned if there were failures in uploading
    if not failures:
        print "No failures"
    else:
        print "Failed:", failures


"""
import os
import logging
from threading import Thread

import boto


_log = logging.getLogger(__name__)


class S3Bucket(object):
    """
    Create new connections to an S3 bucket.

    This object mostly exists to make the :class:`S3Queue` API cleaner, but it
    can be reused anywhere.

    :param name: S3 bucket name to upload to
    :param key: AWS key
    :param secret: AWS secret
    :param public: Whether uploads should be public (default: ``True``)
    :type name: str
    :type aws_key: str
    :type aws_secret: str

    """
    def __init__(self, name, key, secret, public=True):
        self.name = name
        self.key = key
        self.secret = secret
        self.public = public

    def get_new(self):
        """
        Return a new :class:`boto.s3.bucket.Bucket` with its own connection.

        """
        conn = boto.connect_s3(self.key, self.secret)
        return conn.get_bucket(self.name)

    def __str__(self):
        return self.name


class S3Queue(Thread):
    """
    Take a list of `filenames` and upload them to S3 with leading key `prefix`.

    :param prefix: S3 key prefix
    :param filenames: Iterable of filenames
    :param bucket: A :class:`S3Bucket` instance
    :param strip_path: Leading path to strip (optional)
    :type prefix: str
    :type filenames: list
    :type bucket: :class:`S3Bucket`
    :type strip_path: str

    If `strip_path` is specified, `strip_path` will be stripped from the front
    of each filename before composing the uploaded key.

    If there are any exceptions raised while uploading a file, that filename
    will be available in the :attr:`~S3Queue.failed` list. An empty list means
    there were no exceptions raised during upload.

    This runs as a single thread and one can :meth:`join` it to wait for it to
    finish.

    The iterable object `filenames` shouldn't be modified or referenced by
    other threads, as that would not be thread-safe.

    """
    def __init__(self, prefix, filenames, bucket, strip_path=None, **kwargs):
        kwargs.setdefault('name', "S3Queue.{}:{}".format(bucket, id(self)))

        super(S3Queue, self).__init__(**kwargs)

        self.log = logging.getLogger(self.name)
        self.prefix = prefix.strip('/')
        self.filenames = filenames
        self.failed = []
        self.bucket = bucket
        self.strip_path = strip_path

    def run(self):
        """ Run method for the threading API. """
        bucket = self.bucket.get_new()
        # Iterate over the filenames attempting to upload them
        for filename in self.filenames:
            self._upload(filename, bucket)

    def _upload(self, filename, bucket):
        """
        Upload `filename` to `bucket`.

        :param filename: Filename to upload
        :param bucket: A :class:`boto.s3.bucket.Bucket` instance
        :type filename: str
        :type bucket: :class:`boto.s3.bucket.Bucket`

        """
        # Get a new key in this bucket, set its name and upload to it
        try:
            key = self._key(filename)
            s3key = boto.s3.key.Key(bucket)
            s3key.key = key
            s3key.set_contents_from_filename(filename)

            # Set the access for this key
            if self.bucket.public:
                s3key.set_acl('public-read')
            else:
                s3key.set_acl('authenticated-read')
        except:
            self.log.error("Failed %r", key)
            self.log.debug("Oops!", exc_info=True)
            self.failed.append(filename)
        else:
            self.log.debug("Uploaded %r", key)

    def _key(self, filename):
        """
        Return a S3 key from `filename`.

        :param filename: A filename
        :type filename: str

        """
        # Remove the leading path if necessary
        if self.strip_path and filename.startswith(self.strip_path):
            filename = filename[len(self.strip_path):]

        # Strip the filename of leading slashies
        filename = filename.lstrip('/')
        # Join it to the prefix and go!
        return '/'.join((self.prefix, filename))

    def __str__(self):
        return self.name


def sync_to_s3(directory, prefix, bucket, include=None, exclude=None,
        concurrency=1):
    """
    Uploads `directory` to S3 with `prefix` to the key names in `bucket`.

    :param directory: Directory to sync
    :param prefix: S3 key prefix
    :param bucket: A :class:`S3Bucket` instance
    :param exclude: A filename regex to exclude (optional)
    :param include: A filename regex to include (optional)
    :param concurrency: Number of concurrent uploads to use (default: 1)
    :type directory: str
    :type prefix: str
    :type bucket: :class:`S3Bucket`
    :type exclude: regex instance
    :type include: regex instance
    :type concurrency: int

    """
    filenames = [list() for i in xrange(concurrency)]
    count = 0
    for path, dirs, files in os.walk(directory):
        for filename in files:
            filename = os.path.join(path, filename)
            if include and not include.search(filename):
                continue
            if exclude and exclude.search(filename):
                continue
            filenames[count % concurrency].append(filename)
            count += 1

    queues = []
    for queue in filenames:
        queue = S3Queue(prefix, queue, bucket, directory)
        queues.append(queue)
        queue.start()

    failures = []
    for queue in queues:
        queue.join()
        failures.extend(queue.failed)

    return failures



