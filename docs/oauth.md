# OAuth Authentication

CAI supports OAuth authentication from Claude Code and Codex CLI tools, allowing you to use your existing subscriptions without separate API keys.

## Overview

OAuth authentication enables CAI to use credentials from:

- **Claude Code** (Anthropic) - Uses Claude Pro/Max subscription
- **Codex** (OpenAI) - Uses ChatGPT Plus/Pro subscription

This feature is **optional** and works alongside traditional API key authentication.

## How It Works

1. CAI checks for OAuth credentials at startup
2. If valid OAuth tokens are found, they are used for API calls
3. If OAuth is unavailable or expired, CAI falls back to API keys
4. Tokens are automatically refreshed when they expire

## Credential Locations

| Provider | Credential Path |
|----------|-----------------|
| Claude Code | `~/.claude/.credentials.json` |
| Codex | `~/.codex/auth.json` |

## Setup

### Claude Code OAuth

1. Install Claude Code CLI:
   ```bash
   # Follow instructions at https://claude.ai/code
   ```

2. Authenticate with Claude Code:
   ```bash
   claude
   # Complete browser login flow
   ```

3. Verify credentials exist:
   ```bash
   cat ~/.claude/.credentials.json
   ```

### Codex OAuth

1. Install Codex CLI:
   ```bash
   npm install -g @openai/codex
   ```

2. Authenticate with Codex:
   ```bash
   codex
   # Complete browser login flow
   ```

3. Verify credentials exist:
   ```bash
   cat ~/.codex/auth.json
   ```

## Configuration

### Environment Variables

| Variable | Values | Description |
|----------|--------|-------------|
| `CAI_AUTH_METHOD` | `auto`, `oauth`, `api_key` | Authentication method preference |

**Values:**
- `auto` (default): Use OAuth if available, fallback to API key
- `oauth`: OAuth only (will fail if not available)
- `api_key`: API key only (ignore OAuth credentials)

### Example Configuration

```bash
# .env file

# Use OAuth when available, fallback to API key
CAI_AUTH_METHOD=auto

# API keys as fallback
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

## CLI Commands

CAI provides the `/oauth` command for managing OAuth authentication:

```bash
# Show OAuth status
/oauth status

# Force refresh OAuth tokens
/oauth refresh

# Refresh specific provider
/oauth refresh claude
/oauth refresh codex

# Clear cached credentials
/oauth clear

# Show OAuth help
/oauth help
```

## Credential Format

### Claude Code (`~/.claude/.credentials.json`)

```json
{
  "claudeAiOauth": {
    "accessToken": "sk-ant-oat01-...",
    "refreshToken": "sk-ant-ort01-...",
    "expiresAt": 1748658860401,
    "scopes": ["user:inference", "user:profile"]
  }
}
```

### Codex (`~/.codex/auth.json`)

```json
{
  "accessToken": "...",
  "refreshToken": "...",
  "expiresAt": 1748658860401,
  "scopes": []
}
```

## Token Lifecycle

- **Access tokens** expire after 8-12 hours
- **Refresh tokens** are used to obtain new access tokens
- CAI automatically refreshes tokens 5 minutes before expiration
- If refresh fails, authentication falls back to API keys

## Security Considerations

1. **Credential files** contain sensitive tokens - never commit them to version control
2. **Permissions**: Credential files should have restricted permissions (chmod 600)
3. **Fallback**: Always configure API keys as fallback for production use

## Troubleshooting

### OAuth Not Working

1. Check credential files exist:
   ```bash
   ls -la ~/.claude/.credentials.json
   ls -la ~/.codex/auth.json
   ```

2. Verify CAI_AUTH_METHOD:
   ```bash
   echo $CAI_AUTH_METHOD
   ```

3. Check OAuth status in CAI:
   ```
   /oauth status
   ```

### Token Expired

Force refresh the token:
```
/oauth refresh
```

Or re-authenticate with the CLI tool:
```bash
claude  # for Claude Code
codex   # for Codex
```

### Authentication Errors

If you see 401 errors, Anthropic may have blocked OAuth usage in third-party tools. Use API key authentication instead:

```bash
export CAI_AUTH_METHOD=api_key
export ANTHROPIC_API_KEY=sk-ant-...
```

## Policy Warning

Anthropic has historically restricted OAuth token usage in third-party tools. While this feature is implemented for convenience, **API key authentication is recommended for production use**.

If OAuth stops working, switch to API key authentication:

```bash
# In .env or shell
CAI_AUTH_METHOD=api_key
ANTHROPIC_API_KEY=your-api-key
```

## API Reference

### Python API

```python
from cai.auth import (
    get_oauth_manager,
    get_anthropic_token,
    get_openai_token,
    AuthMethod,
)

# Get OAuth manager
manager = get_oauth_manager()

# Check status
status = manager.get_status()
print(status)

# Get tokens
anthropic_token = get_anthropic_token()
openai_token = get_openai_token()

# Async token refresh
async def get_fresh_token():
    token = await manager.get_anthropic_api_key_async()
    return token
```

### LiteLLM Integration

```python
from cai.auth import inject_oauth_to_kwargs_async

# Inject OAuth into litellm kwargs
kwargs = {
    "model": "claude-sonnet-4-20250514",
    "messages": [{"role": "user", "content": "Hello"}],
}

# OAuth token will be injected if available
kwargs = await inject_oauth_to_kwargs_async(kwargs)
```
