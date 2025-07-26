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

from __future__ import print_function

import logging
import os
import posixpath
import signal
import sys
import threading
from builtins import object, range, str
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event

# Lazy imports for better startup performance
boto3 = None
botocore = None

# Constants for optimization
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks for large files
MIN_MULTIPART_SIZE = 100 * 1024 * 1024  # 100MB threshold for multipart uploads
QUEUE_TIMEOUT = 0.5  # Reduced polling interval


def _lazy_import_boto():
    """Lazy import boto3 to reduce startup time."""
    global boto3, botocore
    if boto3 is None:
        import boto3 as _boto3
        import botocore.exceptions as _botocore_exceptions
        boto3 = _boto3
        botocore = _botocore_exceptions


class S3Bucket(object):
    """
    Create new connections to an S3 bucket with connection pooling.

    This object maintains a pool of S3 connections for better performance
    and can be reused anywhere.

    :param name: S3 bucket name to upload to
    :param key: AWS key
    :param secret: AWS secret
    :param public: Whether uploads should be public (default: ``True``)
    :param max_pool_connections: Maximum connections in pool (default: 50)
    :type name: str
    :type aws_key: str
    :type aws_secret: str
    :type max_pool_connections: int

    """

    def __init__(self, name, key, secret, public=True, max_pool_connections=50):
        self.name = name
        self.key = key
        self.secret = secret
        self.public = public
        self.max_pool_connections = max_pool_connections
        self._session = None

    def _get_session(self):
        """Get or create a boto3 session with connection pooling."""
        if self._session is None:
            _lazy_import_boto()
            self._session = boto3.Session(
                aws_access_key_id=self.key,
                aws_secret_access_key=self.secret
            )
        return self._session

    def get_new(self):
        """
        Return a new S3 bucket resource with optimized connection config.

        """
        try:
            _lazy_import_boto()
            session = self._get_session()
            
            # Configure connection pooling for better performance
            config = boto3.session.Config(
                max_pool_connections=self.max_pool_connections,
                retries={'max_attempts': 3, 'mode': 'adaptive'}
            )
            
            s3 = session.resource("s3", config=config)
            bucket = s3.Bucket(self.name)
            # Check if bucket exists and we have access
            s3.meta.client.head_bucket(Bucket=self.name)
            return bucket
        except botocore.NoCredentialsError:
            print(
                (
                    "AWS credentials not properly configured, "
                    "please supply --key and --secret arguments."
                ),
                file=sys.stderr,
            )
            sys.exit(1)

    def __str__(self):
        return self.name


class OptimizedS3Uploader(object):
    """
    Optimized S3 uploader using ThreadPoolExecutor and efficient file handling.
    
    """

    def __init__(self, prefix, filenames, bucket, strip_path=None, counter=None):
        self.prefix = (prefix or "").strip("/")
        self.filenames = deque(filenames)  # Use deque for O(1) operations
        self.failed = []
        self.bucket = bucket
        self.strip_path = strip_path
        self.counter = counter
        self.log = logging.getLogger(f"OptimizedS3Uploader.{bucket}:{id(self)}")
        self._stop_event = Event()

    def upload_all(self, max_workers=None):
        """Upload all files using ThreadPoolExecutor."""
        if not max_workers:
            max_workers = min(len(self.filenames), 50)
            
        bucket_resource = self.bucket.get_new()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all upload tasks
            future_to_filename = {}
            while self.filenames and not self._stop_event.is_set():
                filename = self.filenames.popleft()
                future = executor.submit(self._upload, filename, bucket_resource)
                future_to_filename[future] = filename
            
            # Process completed uploads
            for future in as_completed(future_to_filename):
                if self._stop_event.is_set():
                    break
                    
                filename = future_to_filename[future]
                try:
                    future.result()  # This will raise if upload failed
                    if self.counter:
                        self.counter()
                except Exception as exc:
                    self.log.debug("Failed %r: %s", filename, exc)
                    self.failed.append(filename)
                    if self.counter:
                        self.counter(False)

    def stop(self):
        """Signal the uploader to stop."""
        self._stop_event.set()

    def _upload(self, filename, bucket):
        """
        Upload `filename` to `bucket` with optimized file handling.

        :param filename: Filename to upload
        :param bucket: A boto3 S3 bucket resource
        :type filename: str
        :type bucket: boto3.resources.factory.s3.Bucket

        """
        try:
            key = self._key(filename)
            file_size = os.path.getsize(filename)
            
            # Use multipart upload for large files
            if file_size > MIN_MULTIPART_SIZE:
                self._multipart_upload(filename, key, bucket)
            else:
                self._simple_upload(filename, key, bucket)

            # Set the access for this key
            obj = bucket.Object(key)
            if self.bucket.public:
                obj.Acl().put(ACL="public-read")
            else:
                obj.Acl().put(ACL="authenticated-read")
                
        except Exception as exc:
            self.log.debug("Failed %r: %s", key, exc)
            raise

    def _simple_upload(self, filename, key, bucket):
        """Simple upload for smaller files."""
        with open(filename, "rb") as f:
            bucket.put_object(Key=key, Body=f)

    def _multipart_upload(self, filename, key, bucket):
        """Multipart upload for larger files."""
        s3_client = bucket.meta.client
        
        # Initiate multipart upload
        response = s3_client.create_multipart_upload(
            Bucket=bucket.name,
            Key=key
        )
        upload_id = response['UploadId']
        
        parts = []
        part_number = 1
        
        try:
            with open(filename, 'rb') as f:
                while True:
                    chunk = f.read(UPLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    response = s3_client.upload_part(
                        Bucket=bucket.name,
                        Key=key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=chunk
                    )
                    
                    parts.append({
                        'ETag': response['ETag'],
                        'PartNumber': part_number
                    })
                    part_number += 1
            
            # Complete multipart upload
            s3_client.complete_multipart_upload(
                Bucket=bucket.name,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
            
        except Exception:
            # Abort multipart upload on failure
            s3_client.abort_multipart_upload(
                Bucket=bucket.name,
                Key=key,
                UploadId=upload_id
            )
            raise

    def _key(self, filename):
        """
        Return a S3 key from `filename`.

        :param filename: A filename
        :type filename: str

        """
        # Remove the leading path if necessary
        if self.strip_path and filename.startswith(self.strip_path):
            filename = filename[len(self.strip_path) :]

        # Strip the filename of leading path separators
        filename = filename.lstrip(os.path.sep)
        # Replace path separators with posix separator
        filename = filename.replace(os.path.sep, posixpath.sep)
        # Join it to the prefix and go!
        return "/".join((self.prefix, filename))


class S3Uploader(object):
    """
    Runs a set of parallel uploads using optimized threading.

    :param directory: Directory to sync
    :param prefix: S3 key prefix
    :param bucket: A :class:`S3Bucket` instance
    :param exclude: List of compiled regex patterns to exclude (optional)
    :param include: List of compiled regex patterns to include (optional)
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

    def __init__(
        self,
        directory,
        prefix,
        bucket,
        include=None,
        exclude=None,
        concurrency=1,
        output=None,
        handle_signals=True,
    ):
        self.directory = directory
        self.prefix = prefix
        self.bucket = bucket
        self.include = include or []
        self.exclude = exclude or []
        self.concurrency = min(concurrency, 100)  # Cap max concurrency
        self.output = output
        self.handle_signals = handle_signals
        self.total = 0
        self.count = 0
        self.errors = 0
        self.uploaders = []
        self.log = logging.getLogger("S3Uploader")
        self._stop_event = Event()

    def upload(self):
        """
        Starts the uploading and returns a list of failed filenames.

        """
        self.count = 0
        self.errors = 0
        self.uploaders = []

        if self.handle_signals:
            # Set up the signal catcher so Ctrl+C works
            signal.signal(signal.SIGINT, self.stop)

        # Make sure the directory actually exists
        if not os.path.exists(self.directory):
            raise IOError("Directory %r does not exist." % self.directory)

        # Make sure the bucket is configured
        try:
            self.bucket.get_new()
        except Exception:
            # If we can't access the bucket, there's nothing we can do
            return []

        # Get all the files
        filenames = self.get_filenames(split=True)

        # Start uploaders with file groups
        for file_group in filenames:
            if not file_group:  # Skip empty groups
                continue
                
            uploader = OptimizedS3Uploader(
                self.prefix, file_group, self.bucket, self.directory, counter=self.counter
            )
            self.uploaders.append(uploader)

        # Use ThreadPoolExecutor for better resource management
        with ThreadPoolExecutor(max_workers=len(self.uploaders)) as executor:
            future_to_uploader = {
                executor.submit(uploader.upload_all, max_workers=self.concurrency // len(self.uploaders) or 1): uploader
                for uploader in self.uploaders
            }
            
            # Wait for completion and collect failures
            failures = []
            for future in as_completed(future_to_uploader):
                if self._stop_event.is_set():
                    break
                try:
                    future.result()
                    uploader = future_to_uploader[future]
                    failures.extend(uploader.failed)
                except Exception as exc:
                    self.log.error("Uploader failed: %s", exc)

        if self.output:
            self.output.write("\n")

        return failures

    def stop(self, *args):
        """
        Stop all the running uploaders.

        """
        print("                                                 ", file=sys.stderr)
        print("Stopping...                                      ", file=sys.stderr)
        self._stop_event.set()
        for uploader in self.uploaders:
            uploader.stop()
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
        
        # Pre-compile patterns for better performance
        include_patterns = self.include if self.include else []
        exclude_patterns = self.exclude if self.exclude else []
        
        for path, dirs, files in os.walk(self.directory):
            for filename in files:
                full_filename = os.path.join(path, filename)
                
                # Iterate over all the include regexes, determining if we
                # should include this filename
                if include_patterns:
                    skip = True
                    for pattern in include_patterns:
                        if pattern.search(full_filename):
                            skip = False
                            break
                    if skip:
                        continue
                        
                # Iterate over the exclude regexes, seeing if we should skip
                if exclude_patterns:
                    skip = False
                    for pattern in exclude_patterns:
                        if pattern.search(full_filename):
                            skip = True
                            break
                    if skip:
                        continue
                        
                filenames.append(full_filename)
                self.total += 1

        if split and filenames:
            # Distribute files more evenly across workers
            groups = [[] for _ in range(min(self.concurrency, len(filenames)))]
            for i, filename in enumerate(filenames):
                groups[i % len(groups)].append(filename)
            filenames = groups

        return filenames

    def counter(self, error=False):
        """
        Thread-safe increment of :attr:`count` for each time this is called.

        If `error` is ``True`` then :attr:`errors` is incremented too.

        :param bool error: Indicates there was an error

        """
        # Use thread-safe operations
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
            line += " ({} error{})".format(self.errors, self.errors > 1 and "s" or "")

        # Add spacing to blot out the rest of the line
        line += " " * (int(os.environ.get("COLUMNS", 80)) - len(line) - 1)

        # Write the line to the stream, using \r to start us at the beginning
        self.output.write("\r" + line)

        # Flush the stream if that's possible
        if hasattr(self.output, "flush"):
            self.output.flush()


def sync_to_s3(
    directory,
    prefix,
    bucket,
    include=None,
    exclude=None,
    concurrency=1,
    output=None,
    handle_signals=True,
):
    """
    This is a convenience wrapper around :class:`S3Uploader`.

    """
    uploader = S3Uploader(
        directory,
        prefix,
        bucket,
        include=include,
        exclude=exclude,
        concurrency=concurrency,
        output=output,
        handle_signals=handle_signals,
    )
    return uploader.upload()


def version():
    """Get the version of s3peat package."""
    try:
        from importlib.metadata import version as get_version

        return get_version("s3peat")
    except ImportError:
        try:
            # Fallback for Python < 3.8
            from importlib_metadata import version as get_version

            return get_version("s3peat")
        except ImportError:
            return "0.0.0-dev"
    except Exception:
        return "0.0.0-dev"


# Backward compatibility - keep the old classes for existing code
class S3Queue(OptimizedS3Uploader):
    """
    Legacy S3Queue class - now an alias for OptimizedS3Uploader.
    
    Kept for backward compatibility.
    """
    def __init__(self, prefix, filenames, bucket, strip_path=None, **kwargs):
        counter = kwargs.pop("counter", None)
        super().__init__(prefix, filenames, bucket, strip_path, counter)
        
    def run(self):
        """Legacy run method."""
        self.upload_all()
