"""Command-line interface for FastAPI Pulse.

This module provides a standalone CLI tool for health checking FastAPI applications
without requiring the pulse monitoring to be integrated into the application itself.
"""

import sys
from typing import Optional

import click

from .commands import check


@click.group()
@click.version_option(package_name="fastapi-pulse")
def cli():
    """FastAPI Pulse CLI - Health check your FastAPI endpoints from the command line.

    This tool allows you to probe your FastAPI application's endpoints and get
    instant health status reports, perfect for CI/CD pipelines and development workflows.
    """
    pass


cli.add_command(check)


def main():
    """Entry point for the pulse-cli command."""
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


__all__ = ["cli", "main"]
