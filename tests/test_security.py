"""Tests for the security service.

Covers: SSRF protection, URL validation, token generation/validation,
filename sanitization, rate limiting, and bearer token verification.
"""

from __future__ import annotations

import time

import pytest

from app.services.security import (
    RateLimiter,
    generate_download_token,
    sanitize_filename,
    validate_download_token,
    validate_url,
    verify_bearer_token,
)


class TestBearerTokenVerification:
    """Tests for constant-time bearer token comparison."""

    def test_valid_token(self):
        assert verify_bearer_token("my-secret-token", "my-secret-token") is True

    def test_invalid_token(self):
        assert verify_bearer_token("wrong-token", "my-secret-token") is False

    def test_empty_token(self):
        assert verify_bearer_token("", "my-secret-token") is False

    def test_empty_expected(self):
        assert verify_bearer_token("any-token", "") is False

    def test_both_empty(self):
        assert verify_bearer_token("", "") is True

    def test_near_miss_token(self):
        assert verify_bearer_token("my-secret-toke", "my-secret-token") is False


class TestURLValidation:
    """Tests for URL validation with SSRF protection."""

    ALLOWED = ["instagram.com", "www.instagram.com", "instagr.am", "www.instagr.am"]

    def test_valid_instagram_url(self):
        is_valid, reason = validate_url("https://www.instagram.com/reel/ABC123/", self.ALLOWED)
        assert is_valid is True
        assert reason == ""

    def test_valid_instagr_am_url(self):
        is_valid, reason = validate_url("https://instagr.am/p/ABC123/", self.ALLOWED)
        assert is_valid is True

    def test_reject_youtube_url(self):
        is_valid, reason = validate_url("https://www.youtube.com/watch?v=test123", self.ALLOWED)
        assert is_valid is False
        assert "not supported" in reason.lower()

    def test_reject_youtu_be_url(self):
        is_valid, reason = validate_url("https://youtu.be/test123", self.ALLOWED)
        assert is_valid is False
        assert "not supported" in reason.lower()

    def test_reject_http_scheme(self):
        is_valid, reason = validate_url("http://www.instagram.com/reel/test123", self.ALLOWED)
        assert is_valid is False
        assert "https" in reason.lower() or "scheme" in reason.lower()

    def test_reject_ftp_scheme(self):
        is_valid, reason = validate_url("ftp://www.instagram.com/reel/test", self.ALLOWED)
        assert is_valid is False

    def test_reject_javascript_scheme(self):
        is_valid, reason = validate_url("javascript:alert(1)", self.ALLOWED)
        assert is_valid is False

    def test_reject_disallowed_host(self):
        is_valid, reason = validate_url("https://evil.com/video", self.ALLOWED)
        assert is_valid is False
        assert "host" in reason.lower() or "allowed" in reason.lower()

    def test_reject_localhost(self):
        is_valid, reason = validate_url("https://localhost/admin", self.ALLOWED)
        assert is_valid is False

    def test_reject_127_0_0_1(self):
        is_valid, reason = validate_url("https://127.0.0.1/admin", self.ALLOWED)
        assert is_valid is False

    def test_reject_private_10_network(self):
        is_valid, reason = validate_url("https://10.0.0.1/internal", self.ALLOWED)
        assert is_valid is False

    def test_reject_private_172_network(self):
        is_valid, reason = validate_url("https://172.16.0.1/internal", self.ALLOWED)
        assert is_valid is False

    def test_reject_private_192_network(self):
        is_valid, reason = validate_url("https://192.168.1.1/internal", self.ALLOWED)
        assert is_valid is False

    def test_reject_link_local(self):
        is_valid, reason = validate_url("https://169.254.169.254/metadata", self.ALLOWED)
        assert is_valid is False

    def test_reject_cloud_metadata(self):
        """Specifically test AWS metadata endpoint."""
        is_valid, reason = validate_url("https://169.254.169.254/latest/meta-data/", self.ALLOWED)
        assert is_valid is False

    def test_reject_ipv6_loopback(self):
        is_valid, reason = validate_url("https://[::1]/admin", self.ALLOWED)
        assert is_valid is False

    def test_reject_empty_url(self):
        is_valid, reason = validate_url("", self.ALLOWED)
        assert is_valid is False

    def test_reject_no_host(self):
        is_valid, reason = validate_url("https:///path", self.ALLOWED)
        assert is_valid is False

    def test_reject_url_with_credentials(self):
        is_valid, reason = validate_url("https://user:pass@www.instagram.com/reel/test", self.ALLOWED)
        assert is_valid is False

    def test_reject_zero_ip(self):
        is_valid, reason = validate_url("https://0.0.0.0/", self.ALLOWED)
        assert is_valid is False


class TestDownloadTokens:
    """Tests for short-lived download token generation and validation."""

    SECRET = "test-hmac-secret-key"
    TTL = 300  # 5 minutes

    def test_generate_and_validate(self):
        token = generate_download_token("job-123", self.SECRET, self.TTL)
        is_valid, job_id = validate_download_token(token, self.SECRET)
        assert is_valid is True
        assert job_id == "job-123"

    def test_expired_token(self):
        token = generate_download_token("job-123", self.SECRET, ttl_seconds=0)
        # Token with 0 TTL should expire immediately
        time.sleep(1)
        is_valid, job_id = validate_download_token(token, self.SECRET)
        assert is_valid is False
        assert job_id is None

    def test_invalid_token_string(self):
        is_valid, job_id = validate_download_token("not-a-valid-token", self.SECRET)
        assert is_valid is False
        assert job_id is None

    def test_empty_token(self):
        is_valid, job_id = validate_download_token("", self.SECRET)
        assert is_valid is False

    def test_wrong_secret(self):
        token = generate_download_token("job-123", self.SECRET, self.TTL)
        is_valid, job_id = validate_download_token(token, "wrong-secret")
        assert is_valid is False

    def test_tampered_token(self):
        token = generate_download_token("job-123", self.SECRET, self.TTL)
        # Tamper with the token
        tampered = token[:-4] + "XXXX"
        is_valid, job_id = validate_download_token(tampered, self.SECRET)
        assert is_valid is False

    def test_different_job_ids(self):
        token1 = generate_download_token("job-1", self.SECRET, self.TTL)
        token2 = generate_download_token("job-2", self.SECRET, self.TTL)

        _, id1 = validate_download_token(token1, self.SECRET)
        _, id2 = validate_download_token(token2, self.SECRET)

        assert id1 == "job-1"
        assert id2 == "job-2"
        assert token1 != token2


class TestFilenameSanitization:
    """Tests for filename sanitization."""

    def test_normal_filename(self):
        result = sanitize_filename("My Song.mp3")
        assert result == "My Song.mp3"

    def test_path_traversal_unix(self):
        result = sanitize_filename("../../../etc/passwd")
        assert "/" not in result
        assert ".." not in result or result.startswith("..") is False

    def test_path_traversal_windows(self):
        result = sanitize_filename("..\\..\\system32\\config")
        assert "\\" not in result

    def test_null_bytes(self):
        result = sanitize_filename("song\x00.mp3")
        assert "\x00" not in result

    def test_control_characters(self):
        result = sanitize_filename("song\x01\x02\x03.mp3")
        assert "\x01" not in result

    def test_empty_string(self):
        result = sanitize_filename("")
        assert result == "audio"

    def test_only_dots(self):
        result = sanitize_filename("...")
        assert result != ""
        assert result != "..."

    def test_very_long_filename(self):
        long_name = "a" * 500 + ".mp3"
        result = sanitize_filename(long_name, max_length=200)
        assert len(result) <= 200

    def test_preserves_extension(self):
        result = sanitize_filename("song name here.mp3")
        assert result.endswith(".mp3")

    def test_special_characters(self):
        result = sanitize_filename('song<>:"|?*.mp3')
        # All special chars should be replaced or removed
        for char in '<>:"|?*':
            assert char not in result

    def test_leading_trailing_spaces(self):
        result = sanitize_filename("  song  .mp3  ")
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_leading_dots(self):
        result = sanitize_filename(".hidden_file.mp3")
        assert not result.startswith(".")


class TestRateLimiter:
    """Tests for the sliding window rate limiter."""

    def test_allows_under_limit(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert limiter.check("client1") is True

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            assert limiter.check("client1") is True
        assert limiter.check("client1") is False

    def test_separate_clients(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        assert limiter.check("client1") is True
        assert limiter.check("client1") is True
        assert limiter.check("client1") is False
        # Different client should still be allowed
        assert limiter.check("client2") is True

    def test_window_expiry(self):
        limiter = RateLimiter(max_requests=1, window_seconds=1)
        assert limiter.check("client1") is True
        assert limiter.check("client1") is False
        time.sleep(1.1)
        assert limiter.check("client1") is True
