"""Security service providing SSRF validation, authentication, tokens, and sanitization."""

from __future__ import annotations

import base64
import collections
import hashlib
import hmac
import ipaddress
import re
import socket
import threading
import time
from urllib.parse import urlparse

from app.logging_config import get_logger

logger = get_logger(__name__)


def verify_bearer_token(token: str, expected: str) -> bool:
    """Verify bearer token in constant time to prevent timing attacks.

    Args:
        token: Incoming token string.
        expected: Expected token string.

    Returns:
        bool: True if tokens match, False otherwise.
    """
    if not token and not expected:
        return True
    if not token or not expected:
        return False
    return hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))


def _is_ip_disallowed(ip_str: str) -> bool:
    """Check if an IP address is private, loopback, link-local, reserved, or invalid."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        return True


def validate_url(url: str, allowed_hosts: list[str]) -> tuple[bool, str]:
    """Validate a user-provided URL against SSRF attacks and domain allowlist.

    Checks:
    1. Scheme must be HTTPS
    2. URL must not contain username/password
    3. Hostname must be present and match allowed_hosts
    4. Hostname must not resolve to loopback, private, link-local, or cloud metadata IPs

    Args:
        url: The media URL to validate.
        allowed_hosts: List of permitted domain hostnames.

    Returns:
        tuple[bool, str]: (is_valid, error_reason)
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty"

    stripped_url = url.strip()
    try:
        parsed = urlparse(stripped_url)
    except Exception as exc:
        return False, f"Malformed URL: {exc}"

    # 1. Scheme check (HTTPS only)
    if not parsed.scheme or parsed.scheme.lower() != "https":
        return False, "Only HTTPS scheme is allowed"

    # 2. Reject credentials in URL
    if parsed.username or parsed.password:
        return False, "Credentials in URL are forbidden"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must contain a valid hostname"

    hostname = hostname.lower()

    # Reject literal disallowed IP formats (e.g. 127.0.0.1, 10.0.0.1, [::1], 0.0.0.0)
    try:
        ip_obj = ipaddress.ip_address(hostname)
        if _is_ip_disallowed(str(ip_obj)):
            return False, f"Direct IP address {hostname} is forbidden"
    except ValueError:
        pass

    # 3. Hostname allowlist check
    # Normalize allowed hosts
    normalized_allowed = [h.lower() for h in allowed_hosts]
    host_allowed = False
    for allowed in normalized_allowed:
        if hostname == allowed or hostname.endswith("." + allowed):
            host_allowed = True
            break

    if not host_allowed:
        return False, f"Host '{hostname}' is not in the allowed media hosts list"

    # 4. Resolve DNS to ensure no private/metadata IP rebinding
    port = parsed.port or 443
    try:
        addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, socket.herror, OSError) as exc:
        return False, f"Failed to resolve hostname '{hostname}': {exc}"

    if not addr_info:
        return False, f"No DNS records found for host '{hostname}'"

    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        if _is_ip_disallowed(ip_str):
            logger.warning("SSRF blocked: Host resolved to restricted IP", extra={"host": hostname, "ip": ip_str})
            return False, f"Host resolves to restricted or private IP address"

    return True, ""


def generate_download_token(job_id: str, secret: str, ttl_seconds: int = 300) -> str:
    """Generate a tamper-proof, time-limited single-purpose download token.

    Format: URL-safe base64 of "{job_id}:{expires_at}:{hmac_digest}"

    Args:
        job_id: The job ID granted download access.
        secret: HMAC secret key.
        ttl_seconds: Validity lifetime in seconds.

    Returns:
        str: URL-safe download token string.
    """
    expires_at = int(time.time()) + ttl_seconds
    payload = f"{job_id}:{expires_at}"
    signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    raw_token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(raw_token.encode("utf-8")).decode("utf-8")


def validate_download_token(token: str, secret: str) -> tuple[bool, str | None]:
    """Validate a download token's signature, structure, and expiration.

    Args:
        token: Base64-encoded download token.
        secret: HMAC secret key.

    Returns:
        tuple[bool, str | None]: (is_valid, job_id)
    """
    if not token or not isinstance(token, str):
        return False, None

    try:
        # Support both padded and unpadded base64
        padded_token = token + "=" * (-len(token) % 4)
        raw_token = base64.urlsafe_b64decode(padded_token.encode("utf-8")).decode("utf-8")
    except Exception:
        return False, None

    parts = raw_token.split(":")
    if len(parts) != 3:
        return False, None

    job_id, expires_at_str, signature = parts

    try:
        expires_at = int(expires_at_str)
    except ValueError:
        return False, None

    # Check expiration
    if time.time() > expires_at:
        return False, None

    # Verify HMAC signature
    payload = f"{job_id}:{expires_at}"
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return False, None

    return True, job_id


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Sanitize arbitrary user- or media-derived filename to prevent path traversal.

    Args:
        name: Raw filename string.
        max_length: Maximum allowed length for the base + extension.

    Returns:
        str: Safe filename.
    """
    if not name or not name.strip():
        return "audio"

    # Remove null bytes, control characters, and slashes
    clean = re.sub(r"[\x00-\x1f\x7f\\/<>:\"|?*]", "_", name)

    # Split extension
    parts = clean.rsplit(".", 1)
    if len(parts) == 2 and parts[1].strip():
        base = parts[0]
        ext = "." + parts[1].strip()
    else:
        base = clean
        ext = ""

    # Remove path traversal tokens like '..'
    base = re.sub(r"\.{2,}", "_", base)
    base = re.sub(r"^[.\s]+|[.\s]+$", "", base)
    base = re.sub(r"_+", "_", base).strip("_ ")

    if not base:
        base = "audio"

    # Truncate base to ensure total length with ext does not exceed max_length
    max_base_len = max(1, max_length - len(ext))
    base = base[:max_base_len].rstrip("._ ")

    if not base:
        base = "audio"

    final_name = f"{base}{ext}"
    # Ensure no leading dots
    final_name = final_name.lstrip(".")
    if not final_name:
        final_name = "audio"

    return final_name[:max_length]


class RateLimiter:
    """Sliding-window in-memory rate limiter per client IP."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def check(self, client_id: str) -> bool:
        """Check whether the request for client_id is allowed.

        Args:
            client_id: Unique client identifier (e.g. client IP address).

        Returns:
            bool: True if request is allowed, False if limit exceeded.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            queue = self._requests[client_id]
            # Discard timestamps outside the current sliding window
            while queue and queue[0] < cutoff:
                queue.popleft()

            if len(queue) >= self.max_requests:
                return False

            queue.append(now)
            return True

    def reset(self) -> None:
        """Clear all stored rate limit history."""
        with self._lock:
            self._requests.clear()
