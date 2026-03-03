"""
LiteLLM OAuth Integration for CAI

This module provides OAuth token injection for litellm API calls,
enabling seamless use of Claude Code and Codex OAuth credentials.
"""

from __future__ import annotations

import os
import asyncio
from typing import Optional, Dict, Any, Tuple

from .oauth import get_oauth_manager, OAuthCredentials


def is_anthropic_model(model: str) -> bool:
    """Check if the model is an Anthropic/Claude model."""
    model_lower = model.lower()
    return any(keyword in model_lower for keyword in [
        "claude",
        "anthropic",
        "claude-3",
        "claude-sonnet",
        "claude-opus",
        "claude-haiku",
    ])


def is_openai_model(model: str) -> bool:
    """Check if the model is an OpenAI model (not via other providers)."""
    model_lower = model.lower()

    # Exclude models that go through other providers
    excluded_providers = [
        "ollama", "deepseek", "anthropic", "claude",
        "openrouter", "huggingface", "together",
        "groq", "mistral", "cohere", "alias"
    ]

    for provider in excluded_providers:
        if provider in model_lower:
            return False

    # Check for OpenAI model patterns
    openai_patterns = [
        "gpt-", "gpt4", "o1-", "o3-",
        "text-davinci", "text-curie", "text-babbage", "text-ada",
        "chatgpt", "openai/"
    ]

    return any(pattern in model_lower for pattern in openai_patterns)


def get_oauth_api_key_for_model(model: str) -> Optional[str]:
    """
    Get OAuth API key for the specified model.

    This function checks if OAuth credentials are available for the model
    and returns the access token if valid.

    Args:
        model: The model name/identifier

    Returns:
        OAuth access token if available and valid, None otherwise
    """
    manager = get_oauth_manager()

    if is_anthropic_model(model):
        creds = manager.get_claude_credentials()
        if creds and not creds.is_expired:
            return creds.access_token

    elif is_openai_model(model):
        creds = manager.get_codex_credentials()
        if creds and not creds.is_expired:
            return creds.access_token

    return None


async def get_oauth_api_key_for_model_async(model: str) -> Optional[str]:
    """
    Get OAuth API key for the specified model (async version with refresh).

    This function checks if OAuth credentials are available for the model,
    refreshes if needed, and returns the access token.

    Args:
        model: The model name/identifier

    Returns:
        OAuth access token if available and valid, None otherwise
    """
    manager = get_oauth_manager()

    if is_anthropic_model(model):
        creds = await manager.get_claude_credentials_async()
        if creds:
            return creds.access_token

    elif is_openai_model(model):
        creds = await manager.get_codex_credentials_async()
        if creds:
            return creds.access_token

    return None


def inject_oauth_to_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inject OAuth API key into litellm kwargs if available.

    This function modifies the kwargs dict in-place to include
    the OAuth access token if available for the specified model.

    Args:
        kwargs: The litellm.acompletion kwargs dict

    Returns:
        Modified kwargs dict (same object, modified in-place)
    """
    # Don't override if api_key is already explicitly set
    if "api_key" in kwargs and kwargs["api_key"]:
        return kwargs

    model = kwargs.get("model", "")
    if not model:
        return kwargs

    oauth_key = get_oauth_api_key_for_model(str(model))
    if oauth_key:
        kwargs["api_key"] = oauth_key

    return kwargs


async def inject_oauth_to_kwargs_async(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inject OAuth API key into litellm kwargs if available (async version).

    This function modifies the kwargs dict in-place to include
    the OAuth access token if available for the specified model,
    and will refresh tokens if needed.

    Args:
        kwargs: The litellm.acompletion kwargs dict

    Returns:
        Modified kwargs dict (same object, modified in-place)
    """
    # Don't override if api_key is already explicitly set
    if "api_key" in kwargs and kwargs["api_key"]:
        return kwargs

    model = kwargs.get("model", "")
    if not model:
        return kwargs

    oauth_key = await get_oauth_api_key_for_model_async(str(model))
    if oauth_key:
        kwargs["api_key"] = oauth_key

    return kwargs


def get_oauth_status_for_model(model: str) -> Dict[str, Any]:
    """
    Get OAuth status information for the specified model.

    Args:
        model: The model name/identifier

    Returns:
        Dict with OAuth status information
    """
    manager = get_oauth_manager()

    if is_anthropic_model(model):
        creds = manager.get_claude_credentials()
        provider = "claude"
    elif is_openai_model(model):
        creds = manager.get_codex_credentials()
        provider = "codex"
    else:
        return {
            "provider": "unknown",
            "oauth_available": False,
            "using_oauth": False,
        }

    return {
        "provider": provider,
        "oauth_available": creds is not None,
        "using_oauth": creds is not None and not creds.is_expired,
        "expires_in_seconds": creds.expires_in_seconds if creds else None,
        "scopes": creds.scopes if creds else [],
    }


def setup_oauth_environment() -> Tuple[bool, bool]:
    """
    Set up OAuth tokens as environment variables for litellm.

    This is an alternative approach that sets environment variables
    so that litellm can pick them up automatically.

    Returns:
        Tuple of (anthropic_set, openai_set) indicating which were set
    """
    manager = get_oauth_manager()
    anthropic_set = False
    openai_set = False

    # Set Anthropic token if available and not already set
    claude_creds = manager.get_claude_credentials()
    if claude_creds and not claude_creds.is_expired:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = claude_creds.access_token
            anthropic_set = True

    # Set OpenAI token if available and not already set
    codex_creds = manager.get_codex_credentials()
    if codex_creds and not codex_creds.is_expired:
        if not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = codex_creds.access_token
            openai_set = True

    return anthropic_set, openai_set
