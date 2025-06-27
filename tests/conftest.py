"""
Pytest configuration and fixtures for s3peat tests.
"""

import os
import tempfile
from unittest.mock import Mock

import boto3
import pytest
from moto import mock_aws


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def mock_aws_s3(aws_credentials):
    """
    Mock all AWS interactions using moto
    """
    with mock_aws():
        # Create a bucket for tests that need it
        s3_client = boto3.client("s3", region_name="us-east-1")
        s3_client.create_bucket(Bucket="test-bucket")
        yield s3_client


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
