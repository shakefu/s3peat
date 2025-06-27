"""
Pytest configuration and fixtures for s3peat tests.
"""

import os
import tempfile
from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_boto_s3(mocker):
    """Mock boto3 S3 resource and related operations."""
    # Mock the S3 resource
    mock_s3_resource = Mock()
    mock_bucket = Mock()
    mock_object = Mock()
    mock_acl = Mock()
    mock_client = Mock()

    # Set up the resource chain
    mock_s3_resource.Bucket.return_value = mock_bucket
    mock_s3_resource.meta.client = mock_client
    mock_bucket.Object.return_value = mock_object
    mock_bucket.put_object.return_value = None
    mock_object.Acl.return_value = mock_acl

    # Mock boto3.resource
    mocker.patch("boto3.resource", return_value=mock_s3_resource)

    return {
        "resource": mock_s3_resource,
        "bucket": mock_bucket,
        "object": mock_object,
        "acl": mock_acl,
        "client": mock_client,
    }


@pytest.fixture
def temp_directory():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        test_files = [
            "file1.txt",
            "file2.txt",
            "subdir/file3.txt",
            "subdir/nested/file4.txt",
        ]

        for file_path in test_files:
            full_path = os.path.join(tmpdir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(f"Test content for {file_path}")

        yield tmpdir


@pytest.fixture
def s3_bucket_config():
    """Standard S3 bucket configuration for tests."""
    return {
        "name": "test-bucket",
        "key": "test-key",
        "secret": "test-secret",
        "public": True,
    }


@pytest.fixture
def mock_counter():
    """Mock counter function for tracking uploads."""
    return Mock()


@pytest.fixture
def mock_output():
    """Mock output stream for testing progress output."""
    return Mock()
