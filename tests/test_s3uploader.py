"""
Tests for the S3Uploader class.
"""

import re
import signal
import sys
from unittest.mock import Mock, patch

import pytest

from s3peat import S3Bucket, S3Uploader


def test_s3uploader_initialization(s3_bucket_config, temp_directory):
    """Test S3Uploader initialization."""
    bucket = S3Bucket(**s3_bucket_config)

    uploader = S3Uploader(
        directory=temp_directory,
        prefix="test-prefix",
        bucket=bucket,
        include=[re.compile(r"\.txt$")],
        exclude=[re.compile(r"ignore")],
        concurrency=5,
        output=sys.stdout,
        handle_signals=False,
    )

    assert uploader.directory == temp_directory
    assert uploader.prefix == "test-prefix"
    assert uploader.bucket == bucket
    assert len(uploader.include) == 1
    assert len(uploader.exclude) == 1
    assert uploader.concurrency == 5
    assert uploader.output == sys.stdout
    assert not uploader.handle_signals
    assert uploader.total == 0
    assert uploader.count == 0
    assert uploader.errors == 0
    assert uploader.queues == []


def test_s3uploader_initialization_defaults(s3_bucket_config, temp_directory):
    """Test S3Uploader initialization with defaults."""
    bucket = S3Bucket(**s3_bucket_config)

    uploader = S3Uploader(directory=temp_directory, prefix="test-prefix", bucket=bucket)

    assert uploader.include is None
    assert uploader.exclude is None
    assert uploader.concurrency == 1
    assert uploader.output is None
    assert uploader.handle_signals


def test_get_filenames_no_filters(temp_directory, s3_bucket_config):
    """Test getting all filenames without filters."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket)

    filenames = uploader.get_filenames()

    # Should find all 4 test files created by temp_directory fixture
    assert uploader.total == 4
    assert len(filenames) == 4

    # Check that all expected files are found
    expected_files = ["file1.txt", "file2.txt", "file3.txt", "file4.txt"]
    for expected in expected_files:
        assert any(expected in f for f in filenames)


def test_get_filenames_with_include_filter(temp_directory, s3_bucket_config):
    """Test getting filenames with include filter."""
    bucket = S3Bucket(**s3_bucket_config)

    # Include only files ending with '1.txt' or '2.txt'
    include_pattern = re.compile(r"[12]\.txt$")
    uploader = S3Uploader(temp_directory, "prefix", bucket, include=[include_pattern])

    filenames = uploader.get_filenames()

    assert uploader.total == 2
    assert len(filenames) == 2
    assert all("1.txt" in f or "2.txt" in f for f in filenames)


def test_get_filenames_with_exclude_filter(temp_directory, s3_bucket_config):
    """Test getting filenames with exclude filter."""
    bucket = S3Bucket(**s3_bucket_config)

    # Exclude files in subdirectories
    exclude_pattern = re.compile(r"subdir")
    uploader = S3Uploader(temp_directory, "prefix", bucket, exclude=[exclude_pattern])

    filenames = uploader.get_filenames()

    assert uploader.total == 2  # Only file1.txt and file2.txt in root
    assert len(filenames) == 2
    assert all("subdir" not in f for f in filenames)


def test_get_filenames_with_include_and_exclude(temp_directory, s3_bucket_config):
    """Test getting filenames with both include and exclude filters."""
    bucket = S3Bucket(**s3_bucket_config)

    # Include .txt files but exclude files with 'file2' in the name
    include_pattern = re.compile(r"\.txt$")
    exclude_pattern = re.compile(r"file2")
    uploader = S3Uploader(
        temp_directory,
        "prefix",
        bucket,
        include=[include_pattern],
        exclude=[exclude_pattern],
    )

    filenames = uploader.get_filenames()

    # Should find 3 files (all .txt except file2.txt)
    assert uploader.total == 3
    assert len(filenames) == 3
    assert all("file2" not in f for f in filenames)


def test_get_filenames_split(temp_directory, s3_bucket_config):
    """Test getting filenames split into groups for concurrency."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket, concurrency=2)

    filename_groups = uploader.get_filenames(split=True)

    assert len(filename_groups) == 2  # Should split into 2 groups

    # All groups should be lists
    assert all(isinstance(group, list) for group in filename_groups)

    # Total files should be distributed across groups
    total_files = sum(len(group) for group in filename_groups)
    assert total_files == uploader.total == 4


def test_counter_success(s3_bucket_config, temp_directory, mock_output):
    """Test counter method for successful uploads."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket, output=mock_output)
    uploader.total = 5  # Set a total for testing

    # Call counter for success
    uploader.counter()

    assert uploader.count == 1
    assert uploader.errors == 0

    # Should call _output
    mock_output.write.assert_called()


def test_counter_error(s3_bucket_config, temp_directory, mock_output):
    """Test counter method for failed uploads."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket, output=mock_output)
    uploader.total = 5

    # Call counter for error
    uploader.counter(error=True)

    assert uploader.count == 1
    assert uploader.errors == 1

    # Should call _output
    mock_output.write.assert_called()


def test_counter_multiple_calls(s3_bucket_config, temp_directory):
    """Test multiple counter calls."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket)

    # Call counter multiple times
    uploader.counter()  # success
    uploader.counter(error=True)  # error
    uploader.counter()  # success

    assert uploader.count == 3
    assert uploader.errors == 1


def test_output_formatting(s3_bucket_config, temp_directory, mock_output):
    """Test progress output formatting."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket, output=mock_output)
    uploader.total = 100
    uploader.count = 42
    uploader.errors = 3

    uploader._output()

    # Should have written progress information
    mock_output.write.assert_called_once()
    written_text = mock_output.write.call_args[0][0]

    assert "42/100" in written_text
    assert "files uploaded" in written_text
    assert "3 error" in written_text


def test_output_no_errors(s3_bucket_config, temp_directory, mock_output):
    """Test progress output without errors."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket, output=mock_output)
    uploader.total = 10
    uploader.count = 5
    uploader.errors = 0

    uploader._output()

    written_text = mock_output.write.call_args[0][0]
    assert "5/10" in written_text
    assert "files uploaded" in written_text
    assert "error" not in written_text


def test_output_no_stream(s3_bucket_config, temp_directory):
    """Test output method when no output stream is provided."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket, output=None)

    # Should not raise an exception
    uploader._output()


def test_upload_nonexistent_directory(s3_bucket_config):
    """Test upload with nonexistent directory."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader("/nonexistent/path", "prefix", bucket)

    with pytest.raises(IOError) as exc_info:
        uploader.upload()

    assert "does not exist" in str(exc_info.value)


def test_upload_bucket_connection_failure(
    mock_aws_s3, s3_bucket_config, temp_directory
):
    """Test upload when bucket connection fails."""
    # Mock boto3.resource to fail outside of moto context
    from unittest.mock import Mock, patch

    with patch("boto3.resource") as mock_resource:
        mock_s3_resource = Mock()
        mock_resource.return_value = mock_s3_resource
        mock_s3_resource.meta.client.head_bucket.side_effect = Exception(
            "Connection failed"
        )

        bucket = S3Bucket(**s3_bucket_config)
        uploader = S3Uploader(temp_directory, "prefix", bucket)

        # Should return early without uploading
        result = uploader.upload()
        assert result is None


def test_stop_method(s3_bucket_config, temp_directory, capsys):
    """Test stop method for signal handling."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket)

    # Create mock queues with filenames
    mock_queue1 = Mock()
    mock_queue1.filenames = ["file1.txt", "file2.txt"]
    mock_queue2 = Mock()
    mock_queue2.filenames = ["file3.txt"]

    uploader.queues = [mock_queue1, mock_queue2]

    # Should exit with code 1
    with pytest.raises(SystemExit) as exc_info:
        uploader.stop()

    assert exc_info.value.code == 1

    # Should clear all queue filenames
    assert mock_queue1.filenames == []
    assert mock_queue2.filenames == []

    # Should print stopping message
    captured = capsys.readouterr()
    assert "Stopping..." in captured.err


@patch("time.sleep")  # Mock sleep to speed up test
def test_upload_successful(mock_sleep, mock_aws_s3, s3_bucket_config, temp_directory):
    """Test successful upload process."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket, concurrency=2)

    # Mock the queues to simulate completion
    with patch.object(uploader, "counter"):
        result = uploader.upload()

    # Should return empty list for no failures
    assert result == []

    # Should have created queues
    assert len(uploader.queues) > 0

    # All queues should be daemon threads
    for queue in uploader.queues:
        assert queue.daemon


def test_upload_with_signal_handling(mock_aws_s3, s3_bucket_config, temp_directory):
    """Test upload with signal handling enabled."""
    bucket = S3Bucket(**s3_bucket_config)
    uploader = S3Uploader(temp_directory, "prefix", bucket, handle_signals=True)

    with patch("signal.signal") as mock_signal, patch(
        "time.sleep"
    ):  # Mock sleep to speed up test
        uploader.upload()

        # Should set up signal handler
        mock_signal.assert_called_once_with(signal.SIGINT, uploader.stop)
