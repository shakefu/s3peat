s3peat
======

s3peat is a Python module to help upload directories to S3 using parallel
threads.

The source is hosted at `<http://github.com/shakefu/s3peat/>`_.

**Installing**:

s3peat can be installed from PyPI to get the latest release. If you'd like
development code, you can check out the git repo.

.. code-block:: bash

   # Install from PyPI
   pip install s3peat

   # Install from GitHub
   git clone http://github.com/shakefu/s3peat.git
   cd s3peat
   python setup.py install

**Command line usage**:

When installed via ``pip`` or ``python setup.py install``, a command called
``s3peat`` will be added. This command can be used to upload files easily.

.. code-block:: bash

   $ s3peat --help
   usage: s3peat [--prefix] --bucket  --key  --secret  [--concurrency]
         [--exclude] [--include] [--dry-run] [--verbose] [--version]
         [--help] directory

   positional arguments:
     directory            directory to be uploaded

   optional arguments:
     --prefix , -p        s3 key prefix
     --bucket , -b        s3 bucket name
     --key , -k           AWS key id
     --secret , -s        AWS secret
     --concurrency , -c   number of threads to use
     --exclude , -e       exclusion regex
     --include , -i       inclusion regex
     --dry-run, -d        print files matched and exit, do not upload
     --verbose, -v        increase verbosity (-vvv means more verbose)
     --version            show program's version number and exit
     --help               display this help and exit

**Exmaple**:

.. code-block:: bash

   s3peat -b my/bucket -p my/s3/key/prefix -k KEY -s SECRET -c 25 -v .


**Python API**:

**Example**:

.. code-block:: python

    from s3peat import S3Bucket, sync_to_s3

    # Create a S3Bucket instance, which is used to create connections to S3
    bucket = S3Bucket('my-bucket', AWS_KEY, AWS_SECRET)

    # Call the sync_to_s3 method
    failures = sync_to_s3(directory='my/directory', prefix='my/key',
        bucket=bucket, concurrency=50)

    # A list of filenames will be returned if there were failures in uploading
    if not failures:
        print "No failures"
    else:
        print "Failed:", failures


