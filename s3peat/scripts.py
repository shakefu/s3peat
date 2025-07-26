from __future__ import print_function

import logging
import os
import re
import sys
from builtins import str

from pytool.cmd import Command

import s3peat


class Main(Command):
    """
    s3peat console command.

    See s3peat --help for more information.

    Example usage::

        s3peat -p some/key -b mybucket -k [AWS Key] -s [AWS Secret] my/dir/

    """

    def __init__(self, *args, **kwargs):
        super(Main, self).__init__(*args, **kwargs)
        # Pre-compile common regex patterns for better performance
        self._regex_cache = {}

    def set_opts(self):
        """Configure command line options."""
        self.opt("--prefix", "-p", metavar="", help="s3 key prefix")
        self.opt(
            "--bucket", "-b", metavar="BUCKET", required=True, help="s3 bucket name"
        )
        self.opt("--key", "-k", metavar="", help="AWS key id")
        self.opt("--secret", "-s", metavar="", help="AWS secret")
        self.opt(
            "--concurrency",
            "-c",
            metavar="",
            type=int,
            default=1,
            help="number of threads to use (default: 1, max: 100)",
        )

        self.opt(
            "--exclude",
            "-e",
            action="append",
            type=self.regex,
            metavar="",
            help="exclusion regex",
        )

        self.opt(
            "--include",
            "-i",
            action="append",
            type=self.regex,
            metavar="",
            help="inclusion regex",
        )

        self.opt("--private", "-r", action="store_true", help="do not set ACL public")

        self.opt(
            "--dry-run",
            "-d",
            action="store_true",
            help="print files matched and exit, do not upload",
        )

        self.opt(
            "--verbose",
            "-v",
            action="count",
            default=0,
            help="increase verbosity (-vvv means more verbose) ",
        )

        self.opt("--version", action="version", version=s3peat.version())

        self.opt("directory", help="directory to be uploaded")

    def run(self):
        """
        Do option prep and verbosity triggering, and then either start the
        dry run or the actual upload.

        """
        a = self.args  # Shorthand
        
        # Validate and optimize concurrency setting
        if a.concurrency < 1:
            print("Concurrency must be positive.", file=sys.stderr)
            sys.exit(1)
        
        # Cap concurrency to prevent resource exhaustion
        if a.concurrency > 100:
            print("Warning: Concurrency capped at 100 for optimal performance.", file=sys.stderr)
            a.concurrency = 100

        # Set up logging based on verbosity
        self._setup_logging(a.verbose)

        # If we have a dry run, do it
        if a.dry_run:
            self._dry_run()
            # The dry run call exits the program when done

        # If we've gotten here then we're actually uploading
        output = sys.stdout if a.verbose else None
        
        # Create our bucket with optimized connection pooling
        max_pool_connections = min(a.concurrency * 2, 100)
        bucket = s3peat.S3Bucket(a.bucket, a.key, a.secret, not a.private, max_pool_connections)
        
        # Create our uploader instance
        uploader = s3peat.S3Uploader(
            directory=a.directory,
            prefix=a.prefix,
            bucket=bucket,
            include=a.include,
            exclude=a.exclude,
            concurrency=a.concurrency,
            output=output,
        )

        try:
            # Start the upload
            filenames = uploader.upload()
        except IOError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nUpload interrupted by user.", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"Unexpected error during upload: {exc}", file=sys.stderr)
            sys.exit(1)

        if filenames:
            # If any files were returned, that means they failed to upload
            print("Error uploading files:", file=sys.stderr)
            print("\n".join(filenames), file=sys.stderr)
            sys.exit(1)

        # Success!
        if a.verbose:
            print("Upload completed successfully.")

    def _setup_logging(self, verbosity):
        """Set up logging based on verbosity level."""
        if verbosity > 2:
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            logging.getLogger().setLevel(1)
            logging.getLogger("boto").setLevel(logging.INFO)
            # Reduce urllib3 logging noise
            logging.getLogger("urllib3").setLevel(logging.WARNING)

        if verbosity > 3:
            logging.getLogger("boto").setLevel(1)
            logging.getLogger("botocore").setLevel(logging.DEBUG)

    def _dry_run(self):
        """
        Do a dry run, just printing a list of filenames to upload.

        """
        a = self.args  # Shorthand
        if a.verbose > 1:
            print("Finding files in {} ...".format(os.path.realpath(a.directory)))
            print()

        # Use a dummy bucket and uploader to get the file names
        bucket = None
        uploader = s3peat.S3Uploader(
            a.directory, a.prefix, bucket, include=a.include, exclude=a.exclude
        )
        
        try:
            filenames = uploader.get_filenames()
        except OSError as exc:
            print(f"Error accessing directory: {exc}", file=sys.stderr)
            sys.exit(1)

        if a.verbose > 1 and filenames:
            print("\n".join(filenames))
            print()

        if filenames:
            print("{} files found.".format(uploader.total))
        else:
            print("No files found.", file=sys.stderr)
            sys.exit(1)

        if a.verbose > 1:
            print()

        # Test the connection to S3 only if we have credentials
        if a.bucket:
            bucket = s3peat.S3Bucket(a.bucket, a.key, a.secret)
            try:
                bucket.get_new()
            except Exception as exc:
                print(
                    "Error connecting to S3 bucket {!r}.".format(a.bucket), file=sys.stderr
                )

                if a.verbose > 1:
                    print("   ", "\n    ".join(repr(exc).split("\n")), file=sys.stderr)
                elif a.verbose:
                    print("   ", repr(exc).split("\n")[0], file=sys.stderr)

                sys.exit(1)
            else:
                if a.verbose:
                    print("Connected to S3 bucket {!r} OK.".format(a.bucket))

        self.stop()

    def regex(self, value):
        """
        Helper for regex types on the command line with caching for performance.
        
        """
        # Use cache to avoid recompiling the same patterns
        if value in self._regex_cache:
            return self._regex_cache[value]
            
        try:
            compiled_regex = re.compile(value)
            self._regex_cache[value] = compiled_regex
            return compiled_regex
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern '{value}': {exc}")
        except Exception:
            raise ValueError(f"Failed to compile regex pattern '{value}'")
