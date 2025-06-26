"""
Tests for the S3Queue class.
"""

import os

from s3peat import S3Bucket, S3Queue


def test_s3queue_initialization(s3_bucket_config, mock_counter):
    """Test S3Queue initialization."""
    bucket = S3Bucket(**s3_bucket_config)
    filenames = ["file1.txt", "file2.txt"]

    queue = S3Queue(
        prefix="test-prefix",
        filenames=filenames,
        bucket=bucket,
        strip_path="/some/path",
        counter=mock_counter,
    )

    assert queue.prefix == "test-prefix"
    assert queue.filenames == filenames
    assert queue.bucket == bucket
    assert queue.strip_path == "/some/path"
    assert queue.counter == mock_counter
    assert queue.failed == []
    assert "S3Queue." in queue.name


def test_s3queue_initialization_no_prefix(s3_bucket_config):
    """Test S3Queue initialization with None prefix."""
    bucket = S3Bucket(**s3_bucket_config)
    filenames = ["file1.txt"]

    queue = S3Queue(prefix=None, filenames=filenames, bucket=bucket)

    assert queue.prefix == ""


def test_s3queue_initialization_empty_prefix(s3_bucket_config):
    """Test S3Queue initialization with empty prefix."""
    bucket = S3Bucket(**s3_bucket_config)
    filenames = ["file1.txt"]

    queue = S3Queue(prefix="  //", filenames=filenames, bucket=bucket)

    # The prefix strips only forward slashes, not all whitespace
    assert queue.prefix == "  "


def test_s3queue_key_generation(s3_bucket_config):
    """Test S3 key generation from filenames."""
    bucket = S3Bucket(**s3_bucket_config)
    filenames = []

    queue = S3Queue(prefix="my-prefix", filenames=filenames, bucket=bucket)

    # Test basic key generation
    assert queue._key("file.txt") == "my-prefix/file.txt"

    # Test with subdirectory
    assert queue._key("dir/file.txt") == "my-prefix/dir/file.txt"

    # Test with leading separators
    assert queue._key("/dir/file.txt") == "my-prefix/dir/file.txt"


def test_s3queue_key_generation_with_strip_path(s3_bucket_config):
    """Test S3 key generation with strip_path."""
    bucket = S3Bucket(**s3_bucket_config)
    filenames = []

    queue = S3Queue(
        prefix="my-prefix", filenames=filenames, bucket=bucket, strip_path="/base/path"
    )

    # Test stripping path
    assert queue._key("/base/path/file.txt") == "my-prefix/file.txt"
    assert queue._key("/base/path/dir/file.txt") == "my-prefix/dir/file.txt"

    # Test file that doesn't start with strip_path
    assert queue._key("/other/path/file.txt") == "my-prefix/other/path/file.txt"


def test_s3queue_key_generation_windows_paths(s3_bucket_config):
    """Test S3 key generation with Windows-style paths."""
    bucket = S3Bucket(**s3_bucket_config)
    filenames = []

    queue = S3Queue(prefix="my-prefix", filenames=filenames, bucket=bucket)

    # Test the actual behavior - on Unix, backslashes are treated as filename characters
    # This test validates that behavior rather than mocking Windows
    assert queue._key("dir\\file.txt") == "my-prefix/dir\\file.txt"


def test_s3queue_successful_upload(
    mock_boto_s3, s3_bucket_config, temp_directory, mock_counter
):
    """Test successful file upload."""
    bucket = S3Bucket(**s3_bucket_config)

    # Create a test file
    test_file = os.path.join(temp_directory, "test.txt")

    queue = S3Queue(
        prefix="test-prefix", filenames=[test_file], bucket=bucket, counter=mock_counter
    )

    # Run the upload
    queue.run()

    # Verify the upload was attempted
    mock_boto_s3["key"].set_contents_from_filename.assert_called_once_with(test_file)

    # Verify ACL was set to public-read (bucket.public=True by default)
    mock_boto_s3["key"].set_acl.assert_called_once_with("public-read")

    # Verify counter was called for success
    mock_counter.assert_called_once_with()

    # Verify no failures
    assert queue.failed == []

    # Verify filenames list is empty (all processed)
    assert queue.filenames == []


def test_s3queue_successful_upload_private_bucket(
    mock_boto_s3, temp_directory, mock_counter
):
    """Test successful file upload to private bucket."""
    bucket = S3Bucket("test-bucket", "test-key", "test-secret", public=False)

    # Create a test file
    test_file = os.path.join(temp_directory, "test.txt")

    queue = S3Queue(
        prefix="test-prefix", filenames=[test_file], bucket=bucket, counter=mock_counter
    )

    # Run the upload
    queue.run()

    # Verify ACL was set to authenticated-read for private bucket
    mock_boto_s3["key"].set_acl.assert_called_once_with("authenticated-read")


def test_s3queue_upload_failure(
    mock_boto_s3, s3_bucket_config, temp_directory, mock_counter
):
    """Test handling of upload failure."""
    bucket = S3Bucket(**s3_bucket_config)

    # Create a test file
    test_file = os.path.join(temp_directory, "test.txt")

    # Make the upload fail
    mock_boto_s3["key"].set_contents_from_filename.side_effect = Exception(
        "Upload failed"
    )

    queue = S3Queue(
        prefix="test-prefix", filenames=[test_file], bucket=bucket, counter=mock_counter
    )

    # Run the upload
    queue.run()

    # Verify the upload was attempted
    mock_boto_s3["key"].set_contents_from_filename.assert_called_once_with(test_file)

    # Verify counter was called with False for failure
    mock_counter.assert_called_once_with(False)

    # Verify failure was recorded
    assert queue.failed == [test_file]

    # Verify filenames list is empty (all processed)
    assert queue.filenames == []


def test_s3queue_multiple_files(
    mock_boto_s3, s3_bucket_config, temp_directory, mock_counter
):
    """Test uploading multiple files."""
    bucket = S3Bucket(**s3_bucket_config)

    # Create test files
    test_files = [
        os.path.join(temp_directory, "file1.txt"),
        os.path.join(temp_directory, "file2.txt"),
        os.path.join(temp_directory, "file3.txt"),
    ]

    queue = S3Queue(
        prefix="test-prefix",
        filenames=test_files[:],  # Copy the list
        bucket=bucket,
        counter=mock_counter,
    )

    # Run the upload
    queue.run()

    # Verify all files were uploaded (called 3 times)
    assert mock_boto_s3["key"].set_contents_from_filename.call_count == 3

    # Verify counter was called for each success
    assert mock_counter.call_count == 3

    # Verify no failures
    assert queue.failed == []

    # Verify filenames list is empty
    assert queue.filenames == []


def test_s3queue_mixed_success_failure(
    mock_boto_s3, s3_bucket_config, temp_directory, mock_counter
):
    """Test uploading with some successes and some failures."""
    bucket = S3Bucket(**s3_bucket_config)

    # Create test files
    test_files = [
        os.path.join(temp_directory, "file1.txt"),
        os.path.join(temp_directory, "file2.txt"),
        os.path.join(temp_directory, "file3.txt"),
    ]

    # Make the second upload fail
    def side_effect(filename):
        if "file2.txt" in filename:
            raise Exception("Upload failed")

    mock_boto_s3["key"].set_contents_from_filename.side_effect = side_effect

    queue = S3Queue(
        prefix="test-prefix",
        filenames=test_files[:],  # Copy the list
        bucket=bucket,
        counter=mock_counter,
    )

    # Run the upload
    queue.run()

    # Verify all files were attempted
    assert mock_boto_s3["key"].set_contents_from_filename.call_count == 3

    # Verify counter was called - 2 successes + 1 failure
    assert mock_counter.call_count == 3

    # Verify one failure was recorded
    assert len(queue.failed) == 1
    assert any("file2.txt" in f for f in queue.failed)

    # Verify filenames list is empty
    assert queue.filenames == []


def test_s3queue_str_representation(s3_bucket_config):
    """Test string representation of S3Queue."""
    bucket = S3Bucket(**s3_bucket_config)
    filenames = ["file1.txt"]

    queue = S3Queue(prefix="test-prefix", filenames=filenames, bucket=bucket)

    assert str(queue) == queue.name
    assert "S3Queue." in str(queue)
