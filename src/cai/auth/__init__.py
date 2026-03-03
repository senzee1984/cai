"""
CAI OAuth Authentication Module

Supports OAuth authentication for:
- Claude Code (Anthropic)
- Codex (OpenAI)

While also maintaining backward compatibility with API key authentication.

Environment Variables:
- CAI_AUTH_METHOD: "oauth", "api_key", or "auto" (default: "auto")
- CAI_OAUTH_PROVIDER: "claude", "codex", or "auto" (default: "auto")

Usage:
    from cai.auth import get_oauth_manager, inject_oauth_to_kwargs_async

    # Check OAuth status
    manager = get_oauth_manager()
    status = manager.get_status()

    # Inject OAuth into litellm kwargs
    kwargs = await inject_oauth_to_kwargs_async(kwargs)
"""

from .oauth import (
    OAuthCredentials,
    ClaudeOAuthProvider,
    CodexOAuthProvider,
    OAuthManager,
    get_oauth_manager,
    get_anthropic_token,
    get_openai_token,
    AuthMethod,
)

from .litellm_integration import (
    is_anthropic_model,
    is_openai_model,
    get_oauth_api_key_for_model,
    get_oauth_api_key_for_model_async,
    inject_oauth_to_kwargs,
    inject_oauth_to_kwargs_async,
    get_oauth_status_for_model,
    setup_oauth_environment,
)

__all__ = [
    # OAuth core
    "OAuthCredentials",
    "ClaudeOAuthProvider",
    "CodexOAuthProvider",
    "OAuthManager",
    "get_oauth_manager",
    "get_anthropic_token",
    "get_openai_token",
    "AuthMethod",
    # LiteLLM integration
    "is_anthropic_model",
    "is_openai_model",
    "get_oauth_api_key_for_model",
    "get_oauth_api_key_for_model_async",
    "inject_oauth_to_kwargs",
    "inject_oauth_to_kwargs_async",
    "get_oauth_status_for_model",
    "setup_oauth_environment",
]
