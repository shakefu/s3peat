"""
Tests for the CLI script (Main class).
"""

from unittest.mock import Mock, patch

import pytest

from s3peat.scripts import Main


def test_main_help():
    """Test CLI help output."""
    with pytest.raises(SystemExit) as exc_info:
        Main().start(["--help"])

    assert exc_info.value.code == 0


def test_main_version():
    """Test CLI version output."""
    with pytest.raises(SystemExit) as exc_info:
        Main().start(["--version"])

    assert exc_info.value.code == 0


def test_main_missing_required_args():
    """Test CLI with missing required arguments."""
    with pytest.raises(SystemExit) as exc_info:
        Main().start(["/test/directory"])

    # Should exit with error code for missing bucket argument
    assert exc_info.value.code != 0


def test_main_invalid_concurrency(capsys):
    """Test CLI with invalid concurrency value."""
    argv = ["--bucket", "test-bucket", "--concurrency", "0", "/test/directory"]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "Concurrency must be positive" in captured.err


@patch("s3peat.scripts.s3peat.S3Uploader")
@patch("s3peat.scripts.s3peat.S3Bucket")
def test_main_successful_upload(mock_bucket_class, mock_uploader_class, temp_directory):
    """Test successful upload through CLI."""
    # Mock the bucket and uploader
    mock_bucket = Mock()
    mock_bucket_class.return_value = mock_bucket

    mock_uploader = Mock()
    mock_uploader.upload.return_value = []  # No failures
    mock_uploader_class.return_value = mock_uploader

    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        temp_directory,
    ]

    # Should exit with code 0 for successful upload
    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)
    assert exc_info.value.code == 0

    # Verify bucket was created correctly
    mock_bucket_class.assert_called_once_with(
        "test-bucket", "test-key", "test-secret", True
    )

    # Verify uploader was created and called
    mock_uploader_class.assert_called_once()
    mock_uploader.upload.assert_called_once()


@patch("s3peat.scripts.s3peat.S3Uploader")
@patch("s3peat.scripts.s3peat.S3Bucket")
def test_main_upload_with_failures(
    mock_bucket_class, mock_uploader_class, temp_directory, capsys
):
    """Test upload with failures through CLI."""
    # Mock the bucket and uploader
    mock_bucket = Mock()
    mock_bucket_class.return_value = mock_bucket

    mock_uploader = Mock()
    mock_uploader.upload.return_value = ["failed_file1.txt", "failed_file2.txt"]
    mock_uploader_class.return_value = mock_uploader

    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        temp_directory,
    ]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "Error uploading files:" in captured.err
    assert "failed_file1.txt" in captured.err
    assert "failed_file2.txt" in captured.err


@patch("s3peat.scripts.s3peat.S3Uploader")
@patch("s3peat.scripts.s3peat.S3Bucket")
def test_main_upload_ioerror(mock_bucket_class, mock_uploader_class, capsys):
    """Test upload with IOError through CLI."""
    # Mock the bucket and uploader
    mock_bucket = Mock()
    mock_bucket_class.return_value = mock_bucket

    mock_uploader = Mock()
    mock_uploader.upload.side_effect = IOError("Directory does not exist")
    mock_uploader_class.return_value = mock_uploader

    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "/nonexistent",
    ]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "Directory does not exist" in captured.err


def test_main_dry_run_basic(temp_directory, mock_boto_s3, capsys):
    """Test basic dry run functionality."""
    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "--dry-run",
        temp_directory,
    ]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "files found" in captured.out


def test_main_dry_run_verbose(temp_directory, mock_boto_s3, capsys):
    """Test verbose dry run."""
    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "--dry-run",
        "--verbose",
        "--verbose",
        temp_directory,
    ]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "Finding files" in captured.out
    assert "files found" in captured.out


def test_main_dry_run_no_files(mock_boto_s3, capsys):
    """Test dry run with no files found."""
    # Create empty directory
    import tempfile

    with tempfile.TemporaryDirectory() as empty_dir:
        argv = [
            "--bucket",
            "test-bucket",
            "--key",
            "test-key",
            "--secret",
            "test-secret",
            "--dry-run",
            empty_dir,
        ]

        with pytest.raises(SystemExit) as exc_info:
            Main().start(argv)

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "No files found" in captured.err


def test_main_dry_run_connection_error(temp_directory, mocker, capsys):
    """Test dry run with S3 connection error."""
    # Mock S3Bucket.get_new to raise an exception
    mock_bucket = mocker.Mock()
    mock_bucket.get_new.side_effect = Exception("Connection failed")
    mocker.patch("s3peat.scripts.s3peat.S3Bucket", return_value=mock_bucket)

    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "--dry-run",
        "--verbose",
        temp_directory,
    ]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "Error connecting to S3 bucket" in captured.err


def test_main_with_include_exclude(temp_directory, mock_boto_s3):
    """Test CLI with include and exclude filters."""
    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "--include",
        r"\.txt$",
        "--exclude",
        "file2",
        "--dry-run",
        temp_directory,
    ]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)
    assert exc_info.value.code == 0


def test_main_private_bucket(temp_directory, mock_boto_s3):
    """Test CLI with private bucket flag."""
    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "--private",
        "--dry-run",
        temp_directory,
    ]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)
    assert exc_info.value.code == 0


def test_main_with_prefix(temp_directory, mock_boto_s3):
    """Test CLI with prefix."""
    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "--prefix",
        "my/prefix",
        "--dry-run",
        temp_directory,
    ]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)
    assert exc_info.value.code == 0


def test_main_with_concurrency(temp_directory, mock_boto_s3):
    """Test CLI with concurrency setting."""
    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "--concurrency",
        "3",
        "--dry-run",
        temp_directory,
    ]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)
    assert exc_info.value.code == 0


def test_regex_helper():
    """Test the regex helper function."""
    main = Main()

    # Valid regex
    result = main.regex(r"\.txt$")
    assert result.pattern == r"\.txt$"

    # Invalid regex
    with pytest.raises(ValueError):
        main.regex(r"[invalid")


def test_main_verbose_logging(temp_directory, mock_boto_s3):
    """Test verbose logging levels."""
    # Test -vvv (very verbose)
    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "--verbose",
        "--verbose",
        "--verbose",
        "--dry-run",
        temp_directory,
    ]

    with patch("logging.basicConfig") as mock_logging:
        with pytest.raises(SystemExit) as exc_info:
            Main().start(argv)
        assert exc_info.value.code == 0
        mock_logging.assert_called()


def test_main_extra_verbose_logging(temp_directory, mock_boto_s3):
    """Test extra verbose logging levels."""
    # Test -vvvv (extra verbose)
    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "-v",
        "-v",
        "-v",
        "-v",
        "--dry-run",
        temp_directory,
    ]

    with patch("logging.basicConfig"), patch("logging.getLogger") as mock_get_logger:
        with pytest.raises(SystemExit) as exc_info:
            Main().start(argv)
        assert exc_info.value.code == 0
        mock_get_logger.assert_called()


def test_main_dry_run_verbose_with_connection(temp_directory, mock_boto_s3, capsys):
    """Test verbose dry run with successful S3 connection."""
    argv = [
        "--bucket",
        "test-bucket",
        "--key",
        "test-key",
        "--secret",
        "test-secret",
        "--dry-run",
        "--verbose",
        temp_directory,
    ]

    with pytest.raises(SystemExit) as exc_info:
        Main().start(argv)
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "Connected to S3 bucket 'test-bucket' OK" in captured.out
