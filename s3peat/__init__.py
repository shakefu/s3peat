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
import sys
import time
import signal
import logging
from threading import Thread

import boto
from boto.exception import NoAuthHandlerFound


__version__ = '0.4.6'


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
        try:
            return conn.get_bucket(self.name)
        except NoAuthHandlerFound:
            print >>sys.stderr, ("AWS credentials not properly configured, "
                    "please supply --key and --secret arguments.")
            sys.exit(1)

    def __str__(self):
        return self.name


class S3Queue(Thread):
    """
    Take a list of `filenames` and upload them to S3 with leading key `prefix`.

    If `counter` is specified, it will be called once with no arguments for
    each successful upload, and once with ``False`` as its only argument for
    each failed upload.

    :param prefix: S3 key prefix
    :param filenames: Iterable of filenames
    :param bucket: A :class:`S3Bucket` instance
    :param strip_path: Leading path to strip (optional)
    :param counter: This is called once for each upload (optional)
    :type prefix: str
    :type filenames: list
    :type bucket: :class:`S3Bucket`
    :type strip_path: str
    :type counter: callable

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
        # Get the counting callback if it's set
        self.counter = kwargs.pop('counter', None)

        kwargs.setdefault('name', "S3Queue.{}:{}".format(bucket, id(self)))

        super(S3Queue, self).__init__(**kwargs)

        self.log = logging.getLogger(self.name)
        self.prefix = (prefix or '').strip('/')
        self.filenames = filenames
        self.failed = []
        self.bucket = bucket
        self.strip_path = strip_path

    def run(self):
        """ Run method for the threading API. """
        bucket = self.bucket.get_new()
        # Iterate over the filenames attempting to upload them
        while self.filenames:
            # We need to peek at and upload the last filename
            self._upload(self.filenames[-1], bucket)
            # We don't pop off the list until after the filename is finished
            # uploading or has failed, otherwise the program will exit early
            self.filenames.pop()


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
            self.log.debug("Failed %r", key, exc_info=True)
            self.failed.append(filename)
            if self.counter:
                self.counter(False)
        else:
            self.log.debug("Uploaded %r", key)
            if self.counter:
                self.counter()

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


class S3Uploader(object):
    """
    Runs a set of parallel uploads.

    :param directory: Directory to sync
    :param prefix: S3 key prefix
    :param bucket: A :class:`S3Bucket` instance
    :param exclude: List of filename regexes to exclude (optional)
    :param include: List of filename regexes to include (optional)
    :param concurrency: Number of concurrent uploads to use (default: 1)
    :param output: File or stream to output progress to (optional)
    :type directory: str
    :type prefix: str
    :type bucket: :class:`S3Bucket`
    :type exclude: list
    :type include: list
    :type concurrency: int
    :type output: file

    """
    def __init__(self, directory, prefix, bucket, include=None, exclude=None,
            concurrency=1, output=None):
        self.directory = directory
        self.prefix = prefix
        self.bucket = bucket
        self.include = include
        self.exclude = exclude
        self.concurrency = concurrency
        self.output = output
        self.total = 0
        self.count = 0
        self.errors = 0
        self.queues = []
        self.log = logging.getLogger('S3Uploader')

    def upload(self):
        """
        Starts the uploading and returns a list of failed filenames.

        """
        self.count = 0
        self.errors = 0
        self.queues = []

        # Set up the signal catcher so Ctrl+C works
        signal.signal(signal.SIGINT, self.stop)

        # Make sure the directory actually exists
        if not os.path.exists(self.directory):
            raise IOError("Directory %r does not exist." % self.directory)

        # Make sure the bucket is configured
        if not self.bucket.get_new():
            return

        # Get all the files
        filenames = self.get_filenames(split=True)

        # Start a queue with each group of files
        for queue in filenames:
            queue = S3Queue(self.prefix, queue, self.bucket, self.directory,
                    counter=self.counter)
            self.queues.append(queue)
            queue.daemon = True
            queue.start()

        # Wait for the queues to all finish
        failures = []
        while True:
            remaining = sum([len(q.filenames) for q in self.queues])
            if not remaining:
                break
            time.sleep(0.1)

        for queue in self.queues:
            failures.extend(queue.failed)

        if self.output:
            self.output.write('\n')

        return failures

    def stop(self, *args):
        """
        Stop all the running queues.

        It works by clearing all the queues list of files left to process,
        which means the current files will finish.

        """
        print >>sys.stderr, "                                                 "
        print >>sys.stderr, "Stopping...                                      "
        for queue in self.queues:
            queue.filenames = []
        sys.exit(1)

    def get_filenames(self, split=False):
        """
        Return a list of filenames to upload, filtered by :attr:`include` and
        :attr:`exclude`, if set.

        If `split` is ``True``, then this method returns a list of lists, where
        filenames are evenly divided into :attr:`concurrency` groups.

        After running this method, :attr:`total` will be set to the number of
        filenames found.

        """
        filenames = []
        self.total = 0
        for path, dirs, files in os.walk(self.directory):
            for filename in files:
                filename = os.path.join(path, filename)
                # Iterate over all the include regexes, determining if we
                # should include this filename
                if self.include:
                    skip = True
                    for reg in self.include:
                        if reg.search(filename):
                            skip = False
                            break
                    if skip:
                        continue
                # Iterate over the exclude regexes, seeing if we should skip
                if self.exclude:
                    skip = False
                    for reg in self.exclude:
                        if reg.search(filename):
                            skip = True
                            break
                    if skip:
                        continue
                filenames.append(filename)
                self.total += 1

        if split:
            groups = [list() for i in xrange(self.concurrency)]
            for i in xrange(len(filenames)):
                groups[i % self.concurrency].append(filenames[i])
            filenames = groups

        return filenames

    def counter(self, error=False):
        """
        Increment :attr:`count` for each time this is called.

        If `error` is ``True`` then :attr:`errors` is incremented too.

        :param bool error: Indicates there was an error

        """
        # XXX: We may need a lock around this
        if error:
            self.errors += 1
        self.count += 1
        self._output()

    def _output(self):
        """
        Print the current progress.

        """
        if not self.output:
            # Exit out if we don't have a stream to output to
            return

        # Get the total count as a string, so we can find its length
        total = str(self.total)
        # Compose a format specifier using the length of the total
        count = "{:" + str(len(total)) + "d}"
        # Format the count nicely with our specifier, which pads with spaces
        count = count.format(self.count)
        # Compose our whole line
        line = count + "/" + total + " files uploaded"

        # Add the error count if we have one
        if self.errors:
            line += " ({} error{})".format(self.errors,
                    self.errors > 1 and 's' or '')

        # Add spacing to blot out the rest of the line
        line += " " * (int(os.environ.get('COLUMNS', 80)) - len(line) - 1)

        # Write the line to the stream, using \r to start us at the beginning
        self.output.write('\r' + line)

        # Flush the stream if that's possible
        if hasattr(self.output, 'flush'):
            self.output.flush()


def sync_to_s3(directory, prefix, bucket, include=None, exclude=None,
        concurrency=1, output=None):
    """
    This is a convenience wrapper around :class:`S3Uploader`.

    """
    uploader = S3Uploader(directory, prefix, bucket, include=include,
            exclude=exclude, concurrency=concurrency, output=output)
    return uploader.upload()

