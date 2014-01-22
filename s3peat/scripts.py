import os
import re
import sys
import logging

from pytool.cmd import Command

import s3peat


class Main(Command):
    """
    s3peat console command.

    See s3peat --help for more information.

    Example usage::

        s3peat -p some/key -b mybucket -k [AWS Key] -s [AWS Secret] my/dir/

    """
    def set_opts(self):
        """ Configure command line options. """
        self.opt('--prefix', '-p', metavar='', help="s3 key prefix")
        self.opt('--bucket', '-b', metavar='BUCKET', required=True,
                help="s3 bucket name")
        self.opt('--key', '-k', metavar='', help="AWS key id")
        self.opt('--secret', '-s', metavar='', help="AWS secret")
        self.opt('--concurrency', '-c', metavar='', type=int, default=1,
                help="number of threads to use")

        self.opt('--exclude', '-e', action='append', type=self.regex,
                metavar='', help="exclusion regex")

        self.opt('--include', '-i', action='append', type=self.regex,
                metavar='', help="inclusion regex")

        self.opt('--private', '-r', action='store_true',
                help="do not set ACL public")

        self.opt('--dry-run', '-d', action='store_true',
                help="print files matched and exit, do not upload")

        self.opt('--verbose', '-v', action='count', default=0,
                help="increase verbosity (-vvv means more verbose) ")

        self.opt('--version', action='version', version=s3peat.__version__)

        self.opt('directory', help="directory to be uploaded")

    def run(self):
        """
        Do option prep and verbosity triggering, and then either start the
        dry run or the actual upload.

        """
        a = self.args  # Shorthand
        if a.concurrency < 1:
            print >>sys.stderr, "Concurrency must be positive."
            sys.exit(1)

        if a.verbose > 2:
            logging.basicConfig()
            logging.getLogger().setLevel(1)
            logging.getLogger('boto').setLevel(logging.INFO)

        if a.verbose > 3:
            logging.getLogger('boto').setLevel(1)

        # If we have a dry run, do it
        if a.dry_run:
            self._dry_run()
            # The dry run call exits the program when done

        # If we've gotten here then we're actually uploading
        output = sys.stdout if a.verbose else None
        # Create our bucket so we can get connections to it later
        bucket = s3peat.S3Bucket(a.bucket, a.key, a.secret, not a.private)
        # Create our uploader instance
        uploader = s3peat.S3Uploader(
                directory=a.directory,
                prefix=a.prefix,
                bucket=bucket,
                include=a.include,
                exclude=a.exclude,
                concurrency=a.concurrency,
                output=output)

        try:
            # Start the upload
            filenames = uploader.upload()
        except IOError, exc:
            print >>sys.stderr, str(exc)
            sys.exit(1)

        if filenames:
            # If any files were returned, that means they failed to upload
            print >>sys.stderr, "Error uploading files:"
            print >>sys.stderr, "\n".join(filenames)
            sys.exit(1)

        # This call isn't really necessary, but whatevs
        self.stop()

    def _dry_run(self):
        """
        Do a dry run, just printing a list of filenames to upload.

        :param directory: Directory to use
        :param include: Inclusion regex (optional)
        :param exclude: Exclusion regex (optional)

        """
        a = self.args  # Shorthand
        if a.verbose > 1:
            print "Finding files in {} ...".format(
                    os.path.realpath(a.directory))
            print

        # Use a dummy bucket and uploader to get the file names
        bucket = None
        uploader = s3peat.S3Uploader(a.directory, a.prefix, bucket,
                include=a.include, exclude=a.exclude)
        filenames = uploader.get_filenames()

        if a.verbose > 1:
            print '\n'.join(filenames)
            print

        if filenames:
            print "{} files found.".format(uploader.total)
        else:
            print >>sys.stderr, "No files found."
            sys.exit(1)

        if a.verbose > 1:
            print

        # Test the connection to S3
        bucket = s3peat.S3Bucket(a.bucket, a.key, a.secret)
        try:
            bucket.get_new()
        except Exception, exc:
            print >>sys.stderr, "Error connecting to S3 bucket {!r}.".format(
                    a.bucket)

            if a.verbose > 1:
                print >>sys.stderr, '   ', '\n    '.join(repr(exc).split('\n'))
            elif a.verbose:
                print >>sys.stderr, '   ', repr(exc).split('\n')[0]

            sys.exit(1)
        else:
            if a.verbose:
                print "Connected to S3 bucket {!r} OK.".format(a.bucket)

        self.stop()

    def regex(self, value):
        """ Helper for regex types on the command line. """
        try:
            return re.compile(value)
        except:
            raise ValueError


