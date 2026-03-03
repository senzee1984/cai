"""
OAuth Authentication Provider for CAI

Supports:
- Claude Code OAuth (Anthropic) - reads from ~/.claude/.credentials.json
- Codex OAuth (OpenAI) - reads from ~/.codex/auth.json

Both OAuth and API key authentication can coexist. OAuth is used when:
1. CAI_AUTH_METHOD=oauth is set, OR
2. OAuth credentials exist and CAI_AUTH_METHOD is not explicitly set to "api_key"

Environment Variables:
- CAI_AUTH_METHOD: "oauth", "api_key", or "auto" (default: "auto")
- CAI_OAUTH_PROVIDER: "claude", "codex", or "auto" (default: "auto")
- ANTHROPIC_API_KEY: Fallback API key for Anthropic
- OPENAI_API_KEY: Fallback API key for OpenAI
"""

from __future__ import annotations

import json
import os
import time
import threading
import platform
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import httpx


class AuthMethod(Enum):
    """Authentication method selection."""
    AUTO = "auto"       # Prefer OAuth if available, fallback to API key
    OAUTH = "oauth"     # OAuth only (will fail if not available)
    API_KEY = "api_key" # API key only


@dataclass
class OAuthCredentials:
    """OAuth credentials container."""
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[int] = None  # Unix timestamp in milliseconds
    scopes: list[str] = field(default_factory=list)
    provider: str = "unknown"

    @property
    def is_expired(self) -> bool:
        """Check if the access token is expired."""
        if self.expires_at is None:
            return False
        # Add 5 minute buffer before actual expiration
        buffer_ms = 5 * 60 * 1000
        return time.time() * 1000 >= (self.expires_at - buffer_ms)

    @property
    def expires_in_seconds(self) -> Optional[int]:
        """Return seconds until token expires, or None if no expiration."""
        if self.expires_at is None:
            return None
        remaining_ms = self.expires_at - (time.time() * 1000)
        return max(0, int(remaining_ms / 1000))


class OAuthProvider(ABC):
    """Abstract base class for OAuth providers."""

    @abstractmethod
    def get_credentials_path(self) -> Path:
        """Return the path to the credentials file."""
        pass

    @abstractmethod
    def load_credentials(self) -> Optional[OAuthCredentials]:
        """Load OAuth credentials from storage."""
        pass

    @abstractmethod
    def save_credentials(self, credentials: OAuthCredentials) -> bool:
        """Save OAuth credentials to storage."""
        pass

    @abstractmethod
    async def refresh_token(self, credentials: OAuthCredentials) -> Optional[OAuthCredentials]:
        """Refresh the OAuth token."""
        pass

    @abstractmethod
    def get_api_header(self, credentials: OAuthCredentials) -> Dict[str, str]:
        """Return the API header for authentication."""
        pass


class ClaudeOAuthProvider(OAuthProvider):
    """
    Claude Code OAuth Provider.

    Reads credentials from ~/.claude/.credentials.json

    Expected format:
    {
        "claudeAiOauth": {
            "accessToken": "sk-ant-oat01-...",
            "refreshToken": "sk-ant-ort01-...",
            "expiresAt": 1748658860401,
            "scopes": ["user:inference", "user:profile"]
        }
    }
    """

    CREDENTIALS_KEY = "claudeAiOauth"
    REFRESH_URL = "https://console.anthropic.com/v1/oauth/token"

    def __init__(self, credentials_path: Optional[Path] = None):
        self._credentials_path = credentials_path
        self._lock = threading.Lock()

    def get_credentials_path(self) -> Path:
        """Return the path to Claude credentials file."""
        if self._credentials_path:
            return self._credentials_path

        # On macOS, credentials might be in Keychain, but we check file first
        home = Path.home()
        return home / ".claude" / ".credentials.json"

    def load_credentials(self) -> Optional[OAuthCredentials]:
        """Load Claude OAuth credentials."""
        creds_path = self.get_credentials_path()

        if not creds_path.exists():
            return None

        try:
            with open(creds_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            oauth_data = data.get(self.CREDENTIALS_KEY)
            if not oauth_data:
                return None

            return OAuthCredentials(
                access_token=oauth_data.get("accessToken", ""),
                refresh_token=oauth_data.get("refreshToken"),
                expires_at=oauth_data.get("expiresAt"),
                scopes=oauth_data.get("scopes", []),
                provider="claude"
            )
        except (json.JSONDecodeError, IOError, KeyError) as e:
            print(f"[OAuth] Failed to load Claude credentials: {e}")
            return None

    def save_credentials(self, credentials: OAuthCredentials) -> bool:
        """Save Claude OAuth credentials."""
        creds_path = self.get_credentials_path()

        try:
            # Read existing data
            existing_data = {}
            if creds_path.exists():
                with open(creds_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)

            # Update OAuth section
            existing_data[self.CREDENTIALS_KEY] = {
                "accessToken": credentials.access_token,
                "refreshToken": credentials.refresh_token,
                "expiresAt": credentials.expires_at,
                "scopes": credentials.scopes,
            }

            # Ensure directory exists
            creds_path.parent.mkdir(parents=True, exist_ok=True)

            # Write with restricted permissions
            with self._lock:
                with open(creds_path, "w", encoding="utf-8") as f:
                    json.dump(existing_data, f, indent=2)
                os.chmod(creds_path, 0o600)

            return True
        except (IOError, OSError) as e:
            print(f"[OAuth] Failed to save Claude credentials: {e}")
            return False

    async def refresh_token(self, credentials: OAuthCredentials) -> Optional[OAuthCredentials]:
        """Refresh Claude OAuth token."""
        if not credentials.refresh_token:
            print("[OAuth] No refresh token available for Claude")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.REFRESH_URL,
                    json={
                        "grant_type": "refresh_token",
                        "refresh_token": credentials.refresh_token,
                    },
                    headers={
                        "Content-Type": "application/json",
                    },
                    timeout=30.0
                )

                if response.status_code != 200:
                    print(f"[OAuth] Claude token refresh failed: {response.status_code}")
                    return None

                data = response.json()

                new_credentials = OAuthCredentials(
                    access_token=data.get("access_token", ""),
                    refresh_token=data.get("refresh_token", credentials.refresh_token),
                    expires_at=int(time.time() * 1000) + (data.get("expires_in", 3600) * 1000),
                    scopes=data.get("scope", "").split() if data.get("scope") else credentials.scopes,
                    provider="claude"
                )

                # Save refreshed credentials
                self.save_credentials(new_credentials)

                return new_credentials

        except Exception as e:
            print(f"[OAuth] Claude token refresh error: {e}")
            return None

    def get_api_header(self, credentials: OAuthCredentials) -> Dict[str, str]:
        """Return Anthropic API headers for OAuth authentication."""
        return {
            "Authorization": f"Bearer {credentials.access_token}",
            "anthropic-version": "2023-06-01",
        }


class CodexOAuthProvider(OAuthProvider):
    """
    Codex (OpenAI) OAuth Provider.

    Reads credentials from ~/.codex/auth.json

    Expected format:
    {
        "accessToken": "...",
        "refreshToken": "...",
        "expiresAt": 1748658860401,
        ...
    }
    """

    REFRESH_URL = "https://auth.openai.com/oauth/token"

    def __init__(self, credentials_path: Optional[Path] = None):
        self._credentials_path = credentials_path
        self._lock = threading.Lock()

    def get_credentials_path(self) -> Path:
        """Return the path to Codex credentials file."""
        if self._credentials_path:
            return self._credentials_path

        # Check CODEX_HOME environment variable
        codex_home = os.environ.get("CODEX_HOME")
        if codex_home:
            return Path(codex_home) / "auth.json"

        return Path.home() / ".codex" / "auth.json"

    def load_credentials(self) -> Optional[OAuthCredentials]:
        """Load Codex OAuth credentials."""
        creds_path = self.get_credentials_path()

        if not creds_path.exists():
            return None

        try:
            with open(creds_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Handle Codex actual format with nested "tokens" object
            tokens = data.get("tokens", {})

            # Try nested tokens first, then top-level
            access_token = (
                tokens.get("access_token") or
                tokens.get("accessToken") or
                data.get("accessToken") or
                data.get("access_token") or
                ""
            )
            refresh_token = (
                tokens.get("refresh_token") or
                tokens.get("refreshToken") or
                data.get("refreshToken") or
                data.get("refresh_token")
            )

            # Try to get expiration from various sources
            expires_at = (
                tokens.get("expiresAt") or
                tokens.get("expires_at") or
                data.get("expiresAt") or
                data.get("expires_at")
            )

            # If no explicit expiration, try to parse from JWT access_token
            if not expires_at and access_token:
                expires_at = self._extract_exp_from_jwt(access_token)

            # If expires_at is in seconds (not milliseconds), convert
            if expires_at and expires_at < 10000000000:
                expires_at = int(expires_at * 1000)

            if not access_token:
                return None

            return OAuthCredentials(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scopes=data.get("scopes", []),
                provider="codex"
            )
        except (json.JSONDecodeError, IOError, KeyError) as e:
            print(f"[OAuth] Failed to load Codex credentials: {e}")
            return None

    def _extract_exp_from_jwt(self, token: str) -> Optional[int]:
        """Extract expiration time from JWT token."""
        try:
            import base64
            # JWT format: header.payload.signature
            parts = token.split(".")
            if len(parts) != 3:
                return None

            # Decode payload (add padding if needed)
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding

            decoded = base64.urlsafe_b64decode(payload)
            payload_data = json.loads(decoded)

            # Get exp claim (in seconds)
            exp = payload_data.get("exp")
            if exp:
                return int(exp * 1000)  # Convert to milliseconds
            return None
        except Exception:
            return None

    def save_credentials(self, credentials: OAuthCredentials) -> bool:
        """Save Codex OAuth credentials."""
        creds_path = self.get_credentials_path()

        try:
            # Read existing data
            existing_data = {}
            if creds_path.exists():
                with open(creds_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)

            # Update credentials
            existing_data.update({
                "accessToken": credentials.access_token,
                "refreshToken": credentials.refresh_token,
                "expiresAt": credentials.expires_at,
                "scopes": credentials.scopes,
            })

            # Ensure directory exists
            creds_path.parent.mkdir(parents=True, exist_ok=True)

            # Write with restricted permissions
            with self._lock:
                with open(creds_path, "w", encoding="utf-8") as f:
                    json.dump(existing_data, f, indent=2)
                os.chmod(creds_path, 0o600)

            return True
        except (IOError, OSError) as e:
            print(f"[OAuth] Failed to save Codex credentials: {e}")
            return False

    async def refresh_token(self, credentials: OAuthCredentials) -> Optional[OAuthCredentials]:
        """Refresh Codex OAuth token."""
        if not credentials.refresh_token:
            print("[OAuth] No refresh token available for Codex")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.REFRESH_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": credentials.refresh_token,
                        "client_id": "codex-cli",
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    timeout=30.0
                )

                if response.status_code != 200:
                    print(f"[OAuth] Codex token refresh failed: {response.status_code}")
                    return None

                data = response.json()

                new_credentials = OAuthCredentials(
                    access_token=data.get("access_token", ""),
                    refresh_token=data.get("refresh_token", credentials.refresh_token),
                    expires_at=int(time.time() * 1000) + (data.get("expires_in", 3600) * 1000),
                    scopes=data.get("scope", "").split() if data.get("scope") else credentials.scopes,
                    provider="codex"
                )

                # Save refreshed credentials
                self.save_credentials(new_credentials)

                return new_credentials

        except Exception as e:
            print(f"[OAuth] Codex token refresh error: {e}")
            return None

    def get_api_header(self, credentials: OAuthCredentials) -> Dict[str, str]:
        """Return OpenAI API headers for OAuth authentication."""
        return {
            "Authorization": f"Bearer {credentials.access_token}",
        }


class OAuthManager:
    """
    Central OAuth manager for CAI.

    Manages OAuth credentials for both Claude and Codex,
    with automatic token refresh and fallback to API keys.
    """

    def __init__(self):
        self._claude_provider = ClaudeOAuthProvider()
        self._codex_provider = CodexOAuthProvider()
        self._claude_credentials: Optional[OAuthCredentials] = None
        self._codex_credentials: Optional[OAuthCredentials] = None
        self._auth_method = self._get_auth_method()
        self._callbacks: list[Callable[[str, OAuthCredentials], None]] = []

    def _get_auth_method(self) -> AuthMethod:
        """Get configured authentication method from environment."""
        method = os.environ.get("CAI_AUTH_METHOD", "auto").lower()
        try:
            return AuthMethod(method)
        except ValueError:
            return AuthMethod.AUTO

    def register_callback(self, callback: Callable[[str, OAuthCredentials], None]) -> None:
        """Register a callback to be notified when credentials are refreshed."""
        self._callbacks.append(callback)

    def _notify_callbacks(self, provider: str, credentials: OAuthCredentials) -> None:
        """Notify all registered callbacks of credential changes."""
        for callback in self._callbacks:
            try:
                callback(provider, credentials)
            except Exception as e:
                print(f"[OAuth] Callback error: {e}")

    def get_claude_credentials(self, force_refresh: bool = False) -> Optional[OAuthCredentials]:
        """
        Get Claude OAuth credentials.

        Args:
            force_refresh: Force a token refresh even if not expired

        Returns:
            OAuthCredentials if available and valid, None otherwise
        """
        if self._auth_method == AuthMethod.API_KEY:
            return None

        # Load credentials if not cached
        if self._claude_credentials is None:
            self._claude_credentials = self._claude_provider.load_credentials()

        if self._claude_credentials is None:
            return None

        # Check if refresh is needed
        if force_refresh or self._claude_credentials.is_expired:
            # Note: refresh_token is async, caller should use async version
            return None  # Indicate refresh needed

        return self._claude_credentials

    async def get_claude_credentials_async(self, force_refresh: bool = False) -> Optional[OAuthCredentials]:
        """
        Get Claude OAuth credentials with async token refresh.

        Args:
            force_refresh: Force a token refresh even if not expired

        Returns:
            OAuthCredentials if available and valid, None otherwise
        """
        if self._auth_method == AuthMethod.API_KEY:
            return None

        # Load credentials if not cached
        if self._claude_credentials is None:
            self._claude_credentials = self._claude_provider.load_credentials()

        if self._claude_credentials is None:
            return None

        # Check if refresh is needed
        if force_refresh or self._claude_credentials.is_expired:
            refreshed = await self._claude_provider.refresh_token(self._claude_credentials)
            if refreshed:
                self._claude_credentials = refreshed
                self._notify_callbacks("claude", refreshed)
            else:
                # Refresh failed, credentials may be invalid
                return None

        return self._claude_credentials

    def get_codex_credentials(self, force_refresh: bool = False) -> Optional[OAuthCredentials]:
        """
        Get Codex OAuth credentials.

        Args:
            force_refresh: Force a token refresh even if not expired

        Returns:
            OAuthCredentials if available and valid, None otherwise
        """
        if self._auth_method == AuthMethod.API_KEY:
            return None

        # Load credentials if not cached
        if self._codex_credentials is None:
            self._codex_credentials = self._codex_provider.load_credentials()

        if self._codex_credentials is None:
            return None

        # Check if refresh is needed
        if force_refresh or self._codex_credentials.is_expired:
            return None  # Indicate refresh needed

        return self._codex_credentials

    async def get_codex_credentials_async(self, force_refresh: bool = False) -> Optional[OAuthCredentials]:
        """
        Get Codex OAuth credentials with async token refresh.

        Args:
            force_refresh: Force a token refresh even if not expired

        Returns:
            OAuthCredentials if available and valid, None otherwise
        """
        if self._auth_method == AuthMethod.API_KEY:
            return None

        # Load credentials if not cached
        if self._codex_credentials is None:
            self._codex_credentials = self._codex_provider.load_credentials()

        if self._codex_credentials is None:
            return None

        # Check if refresh is needed
        if force_refresh or self._codex_credentials.is_expired:
            refreshed = await self._codex_provider.refresh_token(self._codex_credentials)
            if refreshed:
                self._codex_credentials = refreshed
                self._notify_callbacks("codex", refreshed)
            else:
                return None

        return self._codex_credentials

    def get_anthropic_api_key(self) -> Optional[str]:
        """
        Get Anthropic API key/token for API calls.

        Priority:
        1. OAuth access token (if available and CAI_AUTH_METHOD != api_key)
        2. ANTHROPIC_API_KEY environment variable
        """
        if self._auth_method != AuthMethod.API_KEY:
            creds = self.get_claude_credentials()
            if creds and not creds.is_expired:
                return creds.access_token

        return os.environ.get("ANTHROPIC_API_KEY")

    async def get_anthropic_api_key_async(self) -> Optional[str]:
        """
        Get Anthropic API key/token for API calls (async version with refresh).

        Priority:
        1. OAuth access token (if available and CAI_AUTH_METHOD != api_key)
        2. ANTHROPIC_API_KEY environment variable
        """
        if self._auth_method != AuthMethod.API_KEY:
            creds = await self.get_claude_credentials_async()
            if creds:
                return creds.access_token

        return os.environ.get("ANTHROPIC_API_KEY")

    def get_openai_api_key(self) -> Optional[str]:
        """
        Get OpenAI API key/token for API calls.

        Priority:
        1. OAuth access token (if available and CAI_AUTH_METHOD != api_key)
        2. OPENAI_API_KEY environment variable
        """
        if self._auth_method != AuthMethod.API_KEY:
            creds = self.get_codex_credentials()
            if creds and not creds.is_expired:
                return creds.access_token

        return os.environ.get("OPENAI_API_KEY")

    async def get_openai_api_key_async(self) -> Optional[str]:
        """
        Get OpenAI API key/token for API calls (async version with refresh).

        Priority:
        1. OAuth access token (if available and CAI_AUTH_METHOD != api_key)
        2. OPENAI_API_KEY environment variable
        """
        if self._auth_method != AuthMethod.API_KEY:
            creds = await self.get_codex_credentials_async()
            if creds:
                return creds.access_token

        return os.environ.get("OPENAI_API_KEY")

    def get_status(self) -> Dict[str, Any]:
        """Get OAuth status for all providers."""
        claude_creds = self._claude_provider.load_credentials()
        codex_creds = self._codex_provider.load_credentials()

        return {
            "auth_method": self._auth_method.value,
            "claude": {
                "available": claude_creds is not None,
                "expired": claude_creds.is_expired if claude_creds else None,
                "expires_in_seconds": claude_creds.expires_in_seconds if claude_creds else None,
                "scopes": claude_creds.scopes if claude_creds else [],
                "credentials_path": str(self._claude_provider.get_credentials_path()),
            },
            "codex": {
                "available": codex_creds is not None,
                "expired": codex_creds.is_expired if codex_creds else None,
                "expires_in_seconds": codex_creds.expires_in_seconds if codex_creds else None,
                "scopes": codex_creds.scopes if codex_creds else [],
                "credentials_path": str(self._codex_provider.get_credentials_path()),
            },
            "fallback": {
                "anthropic_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
                "openai_api_key": bool(os.environ.get("OPENAI_API_KEY")),
            }
        }

    def clear_cache(self) -> None:
        """Clear cached credentials (forces reload on next access)."""
        self._claude_credentials = None
        self._codex_credentials = None


# Global singleton instance
_oauth_manager: Optional[OAuthManager] = None


def get_oauth_manager() -> OAuthManager:
    """Get the global OAuth manager instance."""
    global _oauth_manager
    if _oauth_manager is None:
        _oauth_manager = OAuthManager()
    return _oauth_manager


def get_anthropic_token() -> Optional[str]:
    """Convenience function to get Anthropic API token."""
    return get_oauth_manager().get_anthropic_api_key()


def get_openai_token() -> Optional[str]:
    """Convenience function to get OpenAI API token."""
    return get_oauth_manager().get_openai_api_key()
