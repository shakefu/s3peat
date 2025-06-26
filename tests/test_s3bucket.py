"""
Tests for the S3Bucket class.
"""

import pytest
from boto.exception import NoAuthHandlerFound

from s3peat import S3Bucket


def test_s3bucket_initialization(s3_bucket_config):
    """Test S3Bucket initialization with various parameters."""
    bucket = S3Bucket(
        s3_bucket_config["name"],
        s3_bucket_config["key"],
        s3_bucket_config["secret"],
        s3_bucket_config["public"],
    )

    assert bucket.name == s3_bucket_config["name"]
    assert bucket.key == s3_bucket_config["key"]
    assert bucket.secret == s3_bucket_config["secret"]
    assert bucket.public == s3_bucket_config["public"]


def test_s3bucket_initialization_defaults():
    """Test S3Bucket initialization with default public=True."""
    bucket = S3Bucket("test-bucket", "test-key", "test-secret")

    assert bucket.name == "test-bucket"
    assert bucket.key == "test-key"
    assert bucket.secret == "test-secret"
    assert bucket.public


def test_s3bucket_str_representation(s3_bucket_config):
    """Test string representation of S3Bucket."""
    bucket = S3Bucket(
        s3_bucket_config["name"], s3_bucket_config["key"], s3_bucket_config["secret"]
    )

    assert str(bucket) == s3_bucket_config["name"]


def test_get_new_successful_connection(mock_boto_s3, s3_bucket_config):
    """Test successful bucket connection."""
    bucket = S3Bucket(
        s3_bucket_config["name"], s3_bucket_config["key"], s3_bucket_config["secret"]
    )

    result = bucket.get_new()

    # Verify boto was called with correct credentials
    import boto

    boto.connect_s3.assert_called_once_with(
        s3_bucket_config["key"], s3_bucket_config["secret"]
    )

    # Verify get_bucket was called with correct bucket name
    mock_boto_s3["conn"].get_bucket.assert_called_once_with(s3_bucket_config["name"])

    # Should return the mocked bucket
    assert result == mock_boto_s3["bucket"]


def test_get_new_no_auth_handler(mocker, s3_bucket_config, capsys):
    """Test handling of NoAuthHandlerFound exception."""
    # Mock boto.connect_s3
    mock_conn = mocker.Mock()
    mock_conn.get_bucket.side_effect = NoAuthHandlerFound()
    mocker.patch("boto.connect_s3", return_value=mock_conn)

    bucket = S3Bucket(
        s3_bucket_config["name"], s3_bucket_config["key"], s3_bucket_config["secret"]
    )

    # Should exit with code 1
    with pytest.raises(SystemExit) as exc_info:
        bucket.get_new()

    assert exc_info.value.code == 1

    # Check error message was printed to stderr
    captured = capsys.readouterr()
    assert "AWS credentials not properly configured" in captured.err
    assert "--key and --secret arguments" in captured.err
