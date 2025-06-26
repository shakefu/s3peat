"""
Pytest configuration and fixtures for s3peat tests.
"""

import os
import tempfile
from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_boto_s3(mocker):
    """Mock boto.connect_s3 and related S3 operations."""
    # Mock the connection
    mock_conn = Mock()
    mock_bucket = Mock()
    mock_key = Mock()

    # Set up the connection chain
    mock_conn.get_bucket.return_value = mock_bucket

    # Mock boto.connect_s3
    mocker.patch("boto.connect_s3", return_value=mock_conn)

    # Mock boto.s3.key.Key
    mocker.patch("boto.s3.key.Key", return_value=mock_key)

    return {"conn": mock_conn, "bucket": mock_bucket, "key": mock_key}


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
