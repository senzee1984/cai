"""
OAuth command for CAI REPL.
This module provides commands for managing OAuth authentication.
"""
import os
from datetime import datetime
from typing import List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from cai.repl.commands.base import Command, register_command
from cai.auth import (
    get_oauth_manager,
    AuthMethod,
    is_anthropic_model,
    is_openai_model,
    get_oauth_status_for_model,
)

console = Console()


class OAuthCommand(Command):
    """Command for managing OAuth authentication."""

    def __init__(self):
        """Initialize the oauth command."""
        super().__init__(
            name="/oauth",
            description="Manage OAuth authentication (Claude Code, Codex)",
            aliases=["/auth"]
        )
        self.add_subcommand("status", "Show OAuth status for all providers", self.handle_status)
        self.add_subcommand("refresh", "Force refresh OAuth tokens", self.handle_refresh)
        self.add_subcommand("clear", "Clear cached OAuth credentials", self.handle_clear)
        self.add_subcommand("help", "Show OAuth help information", self.handle_help)

    def handle(self, args: Optional[List[str]] = None) -> bool:
        """Handle the oauth command.

        Args:
            args: Optional list of command arguments

        Returns:
            True if the command was handled successfully, False otherwise
        """
        if not args:
            return self.handle_status(None)
        return super().handle(args)

    def handle_status(self, args: Optional[List[str]] = None) -> bool:
        """Display OAuth status for all providers.

        Args:
            args: Optional list of command arguments

        Returns:
            True if the command was handled successfully
        """
        manager = get_oauth_manager()
        status = manager.get_status()

        # Create status table
        table = Table(
            title="OAuth Authentication Status",
            show_header=True,
            header_style="bold magenta"
        )
        table.add_column("Provider", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Expires In", style="yellow")
        table.add_column("Credentials Path", style="dim")

        # Auth method
        auth_method = status["auth_method"]
        method_display = {
            "auto": "[blue]Auto[/blue] (OAuth preferred, API key fallback)",
            "oauth": "[green]OAuth Only[/green]",
            "api_key": "[yellow]API Key Only[/yellow]"
        }.get(auth_method, auth_method)

        console.print(f"\n[bold]Authentication Method:[/bold] {method_display}")
        console.print()

        # Claude status
        claude = status["claude"]
        if claude["available"]:
            if claude["expired"]:
                claude_status = "[red]Expired[/red]"
            else:
                claude_status = "[green]Valid[/green]"

            expires_in = claude["expires_in_seconds"]
            if expires_in is not None:
                hours = expires_in // 3600
                minutes = (expires_in % 3600) // 60
                expires_display = f"{hours}h {minutes}m"
            else:
                expires_display = "Unknown"
        else:
            claude_status = "[dim]Not configured[/dim]"
            expires_display = "-"

        table.add_row(
            "Claude Code",
            claude_status,
            expires_display,
            claude["credentials_path"]
        )

        # Codex status
        codex = status["codex"]
        if codex["available"]:
            if codex["expired"]:
                codex_status = "[red]Expired[/red]"
            else:
                codex_status = "[green]Valid[/green]"

            expires_in = codex["expires_in_seconds"]
            if expires_in is not None:
                hours = expires_in // 3600
                minutes = (expires_in % 3600) // 60
                expires_display = f"{hours}h {minutes}m"
            else:
                expires_display = "Unknown"
        else:
            codex_status = "[dim]Not configured[/dim]"
            expires_display = "-"

        table.add_row(
            "Codex (OpenAI)",
            codex_status,
            expires_display,
            codex["credentials_path"]
        )

        console.print(table)

        # Current model and active OAuth
        current_model = os.environ.get("CAI_MODEL", "gpt-4o")
        console.print(f"\n[bold]Current Model:[/bold] [cyan]{current_model}[/cyan]")

        # Determine which OAuth will be used
        if is_anthropic_model(current_model):
            target_provider = "Claude Code"
            provider_available = claude["available"] and not claude.get("expired", False)
            provider_key = "claude"
        elif is_openai_model(current_model):
            target_provider = "Codex (OpenAI)"
            provider_available = codex["available"] and not codex.get("expired", False)
            provider_key = "codex"
        else:
            target_provider = "Unknown"
            provider_available = False
            provider_key = None

        # Show active authentication
        console.print(f"[bold]Target OAuth Provider:[/bold] [cyan]{target_provider}[/cyan]")

        if auth_method == "api_key":
            auth_source = "[yellow]API Key (OAuth disabled)[/yellow]"
        elif provider_available:
            auth_source = f"[green]OAuth ({target_provider})[/green]"
        else:
            # Check if fallback API key is available
            if provider_key == "claude" and status["fallback"]["anthropic_api_key"]:
                auth_source = "[yellow]API Key (OAuth unavailable, using fallback)[/yellow]"
            elif provider_key == "codex" and status["fallback"]["openai_api_key"]:
                auth_source = "[yellow]API Key (OAuth unavailable, using fallback)[/yellow]"
            else:
                auth_source = "[red]None (No OAuth or API key available!)[/red]"

        console.print(f"[bold]Active Authentication:[/bold] {auth_source}")

        # Fallback status
        console.print("\n[bold]API Key Fallback:[/bold]")
        fallback = status["fallback"]
        anthropic_key = "[green]Set[/green]" if fallback["anthropic_api_key"] else "[dim]Not set[/dim]"
        openai_key = "[green]Set[/green]" if fallback["openai_api_key"] else "[dim]Not set[/dim]"
        console.print(f"  ANTHROPIC_API_KEY: {anthropic_key}")
        console.print(f"  OPENAI_API_KEY: {openai_key}")

        return True

    def handle_refresh(self, args: Optional[List[str]] = None) -> bool:
        """Force refresh OAuth tokens.

        Args:
            args: Optional list of command arguments (provider name)

        Returns:
            True if the command was handled successfully
        """
        import asyncio

        manager = get_oauth_manager()
        provider = args[0] if args else "all"

        async def refresh_tokens():
            results = {}

            if provider in ("all", "claude"):
                console.print("[cyan]Refreshing Claude OAuth token...[/cyan]")
                creds = await manager.get_claude_credentials_async(force_refresh=True)
                if creds:
                    results["claude"] = "[green]Success[/green]"
                else:
                    results["claude"] = "[red]Failed (no credentials or refresh failed)[/red]"

            if provider in ("all", "codex"):
                console.print("[cyan]Refreshing Codex OAuth token...[/cyan]")
                creds = await manager.get_codex_credentials_async(force_refresh=True)
                if creds:
                    results["codex"] = "[green]Success[/green]"
                else:
                    results["codex"] = "[red]Failed (no credentials or refresh failed)[/red]"

            return results

        try:
            results = asyncio.get_event_loop().run_until_complete(refresh_tokens())
        except RuntimeError:
            # If no event loop exists, create one
            results = asyncio.run(refresh_tokens())

        console.print("\n[bold]Refresh Results:[/bold]")
        for prov, result in results.items():
            console.print(f"  {prov}: {result}")

        return True

    def handle_clear(self, args: Optional[List[str]] = None) -> bool:
        """Clear cached OAuth credentials.

        Args:
            args: Optional list of command arguments

        Returns:
            True if the command was handled successfully
        """
        manager = get_oauth_manager()
        manager.clear_cache()
        console.print("[green]OAuth credential cache cleared[/green]")
        console.print("[dim]Note: This only clears the in-memory cache, not the credential files.[/dim]")
        return True

    def handle_help(self, args: Optional[List[str]] = None) -> bool:
        """Display OAuth help information.

        Args:
            args: Optional list of command arguments

        Returns:
            True if the command was handled successfully
        """
        help_text = """
[bold cyan]OAuth Authentication for CAI[/bold cyan]

CAI supports OAuth authentication from Claude Code and Codex CLI tools,
allowing you to use your existing subscriptions without separate API keys.

[bold]Credential Locations:[/bold]
  Claude Code: ~/.claude/.credentials.json
  Codex:       ~/.codex/auth.json

[bold]Setup:[/bold]
  1. Install and authenticate with Claude Code or Codex CLI
     - Claude: Run 'claude' and complete browser login
     - Codex:  Run 'codex' and complete browser login
  2. CAI will automatically detect and use OAuth credentials

[bold]Environment Variables:[/bold]
  CAI_AUTH_METHOD  - Authentication method preference:
                     'auto'    - Use OAuth if available, fallback to API key (default)
                     'oauth'   - OAuth only (fail if not available)
                     'api_key' - API key only (ignore OAuth)

[bold]Commands:[/bold]
  /oauth status   - Show current OAuth status
  /oauth refresh  - Force refresh OAuth tokens
  /oauth clear    - Clear cached credentials
  /oauth help     - Show this help

[bold yellow]Warning:[/bold yellow]
  Anthropic may restrict OAuth token usage in third-party tools.
  API key authentication is recommended for production use.
"""
        console.print(Panel(help_text, title="OAuth Help", border_style="blue"))
        return True


# Register the command
register_command(OAuthCommand())
