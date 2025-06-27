"""
Tests for the sync_to_s3 convenience function.
"""

import sys
from unittest.mock import Mock, patch

import pytest

from s3peat import S3Bucket, sync_to_s3


def test_sync_to_s3_basic(mock_aws_s3, s3_bucket_config, temp_directory):
    """Test basic sync_to_s3 functionality."""
    bucket = S3Bucket(**s3_bucket_config)

    with patch("time.sleep"):  # Mock sleep to speed up test
        result = sync_to_s3(
            directory=temp_directory, prefix="test-prefix", bucket=bucket
        )

    # Should return empty list for no failures
    assert result == []


def test_sync_to_s3_with_all_parameters(mock_aws_s3, s3_bucket_config, temp_directory):
    """Test sync_to_s3 with all parameters."""
    bucket = S3Bucket(**s3_bucket_config)

    import re

    include_pattern = re.compile(r"\.txt$")
    exclude_pattern = re.compile(r"file2")

    with patch("time.sleep"):  # Mock sleep to speed up test
        result = sync_to_s3(
            directory=temp_directory,
            prefix="test-prefix",
            bucket=bucket,
            include=[include_pattern],
            exclude=[exclude_pattern],
            concurrency=2,
            output=sys.stdout,
            handle_signals=False,
        )

    # Should return empty list for no failures
    assert result == []


def test_sync_to_s3_with_failures(
    mock_aws_s3, s3_bucket_config, temp_directory, mocker
):
    """Test sync_to_s3 when some uploads fail."""
    bucket = S3Bucket(**s3_bucket_config)

    # Mock the put_object method to make uploads fail after moto setup
    # We need to patch the actual boto3 method that gets called
    with patch("boto3.resource") as mock_resource:
        mock_s3_resource = Mock()
        mock_bucket = Mock()
        mock_resource.return_value = mock_s3_resource
        mock_s3_resource.Bucket.return_value = mock_bucket
        mock_s3_resource.meta.client.head_bucket.return_value = None
        mock_bucket.put_object.side_effect = Exception("Upload failed")

        with patch("time.sleep"):  # Mock sleep to speed up test
            result = sync_to_s3(
                directory=temp_directory, prefix="test-prefix", bucket=bucket
            )

    # Should return list of failed files
    assert isinstance(result, list)
    assert len(result) > 0  # Some files should have failed


def test_sync_to_s3_nonexistent_directory(s3_bucket_config):
    """Test sync_to_s3 with nonexistent directory."""
    bucket = S3Bucket(**s3_bucket_config)

    with pytest.raises(IOError) as exc_info:
        sync_to_s3(directory="/nonexistent/path", prefix="test-prefix", bucket=bucket)

    assert "does not exist" in str(exc_info.value)
