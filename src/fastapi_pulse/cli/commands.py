"""Click commands for FastAPI Pulse CLI."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

import click

from .output import OutputFormatter
from .standalone_probe import StandaloneProbeClient


@click.command()
@click.argument("base_url")
@click.option(
    "--endpoints",
    multiple=True,
    help="Specific endpoint IDs to check (can be used multiple times). If not specified, all endpoints will be checked.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table", "summary"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--timeout",
    type=float,
    default=10.0,
    help="Request timeout in seconds (default: 10.0)",
)
@click.option(
    "--header",
    "custom_headers",
    multiple=True,
    help='Custom headers in "Key: Value" format (can be used multiple times). Example: --header "Authorization: Bearer token"',
)
@click.option(
    "--concurrency",
    type=int,
    default=10,
    help="Maximum concurrent probe requests (default: 10)",
)
@click.option(
    "--watch",
    is_flag=True,
    help="Continuous monitoring mode - repeatedly check endpoints",
)
@click.option(
    "--interval",
    type=int,
    default=10,
    help="Watch mode interval in seconds (default: 10)",
)
@click.option(
    "--fail-on-error",
    is_flag=True,
    help="Exit with code 1 if any endpoint has warnings or failures",
)
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True, path_type=Path),
    help="Configuration file path (YAML format)",
)
@click.option(
    "--asgi-app",
    "asgi_app_path",
    type=str,
    default=None,
    help="Import path to ASGI app or factory (module:attribute). "
    "If provided, requests run in-process via ASGI transport.",
)
def check(
    base_url: str,
    endpoints: Tuple[str, ...],
    output_format: str,
    timeout: float,
    custom_headers: Tuple[str, ...],
    concurrency: int,
    watch: bool,
    interval: int,
    fail_on_error: bool,
    config_file: Optional[Path],
    asgi_app_path: Optional[str],
):
    """Check health of FastAPI endpoints.

    BASE_URL is the base URL of your FastAPI application (e.g., http://localhost:8000)

    Examples:

    \b
    # Quick check all endpoints
    pulse-cli check http://localhost:8000

    \b
    # Check with custom format
    pulse-cli check http://localhost:8000 --format json

    \b
    # Check specific endpoints only
    pulse-cli check http://localhost:8000 --endpoints "GET /api/users" --endpoints "POST /api/orders"

    \b
    # Continuous monitoring
    pulse-cli check http://localhost:8000 --watch --interval 30

    \b
    # CI/CD usage with failure detection
    pulse-cli check http://localhost:8000 --format json --fail-on-error
    """
    # Load config file if provided
    config = {}
    if config_file:
        config = _load_config(config_file)

    # Merge config with CLI options (CLI options take precedence)
    merged_config = _merge_config(
        config,
        base_url=base_url,
        timeout=timeout,
        output_format=output_format,
        custom_headers=custom_headers,
        concurrency=concurrency,
        endpoints=endpoints,
    )

    if asgi_app_path:
        merged_config["asgi_app"] = asgi_app_path

    asgi_app = None
    if merged_config.get("asgi_app"):
        try:
            asgi_app = _load_asgi_app(merged_config["asgi_app"])
        except Exception as exc:
            raise click.ClickException(
                f"Failed to load ASGI app '{merged_config['asgi_app']}': {exc}"
            ) from exc

    # Parse custom headers
    headers_dict = _parse_headers(merged_config["custom_headers"])

    # Run probe (with watch mode if enabled)
    try:
        if watch:
            _run_watch_mode(
                merged_config["base_url"],
                merged_config["timeout"],
                headers_dict,
                merged_config["concurrency"],
                merged_config["endpoints"],
                merged_config["output_format"],
                interval,
                fail_on_error,
                asgi_app,
            )
        else:
            exit_code = asyncio.run(
                _run_probe(
                    merged_config["base_url"],
                    merged_config["timeout"],
                    headers_dict,
                    merged_config["concurrency"],
                    merged_config["endpoints"],
                    merged_config["output_format"],
                    fail_on_error,
                    asgi_app,
                )
            )
            sys.exit(exit_code)
    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


async def _run_probe(
    base_url: str,
    timeout: float,
    headers: dict,
    concurrency: int,
    specific_endpoints: List[str],
    output_format: str,
    fail_on_error: bool,
    asgi_app: Optional[Any] = None,
) -> int:
    """Run the probe operation.

    Args:
        base_url: Base URL of the FastAPI application
        timeout: Request timeout
        headers: Custom headers
        concurrency: Max concurrent requests
        specific_endpoints: List of specific endpoint IDs to check
        output_format: Output format type
        fail_on_error: Whether to exit with error code on failures
        asgi_app: Optional ASGI app instance to run requests in-process

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    client = StandaloneProbeClient(
        base_url=base_url,
        timeout=timeout,
        concurrency=concurrency,
        custom_headers=headers,
        asgi_app=asgi_app,
    )

    try:
        # Fetch available endpoints
        all_endpoints = await client.fetch_endpoints()

        # Filter to specific endpoints if requested
        if specific_endpoints:
            endpoint_ids = set(specific_endpoints)
            endpoints_to_check = [
                ep for ep in all_endpoints if ep["id"] in endpoint_ids
            ]
            missing = endpoint_ids - {ep["id"] for ep in all_endpoints}
            if missing:
                click.echo(f"Warning: Endpoints not found: {', '.join(missing)}", err=True)
        else:
            endpoints_to_check = all_endpoints

        if not endpoints_to_check:
            click.echo("No endpoints to check", err=True)
            return 1

        # Probe endpoints
        results = await client.probe_endpoints(endpoints_to_check)

        # Convert to dictionaries
        result_dicts = [r.to_dict() for r in results]

        # Format and display output
        output = OutputFormatter.format_results(result_dicts, output_format)
        click.echo(output)

        # Determine exit code
        if fail_on_error:
            has_issues = any(
                r["status"] in {"warning", "critical"} for r in result_dicts
            )
            return 1 if has_issues else 0

        return 0

    except Exception as e:
        click.echo(f"Probe failed: {e}", err=True)
        return 1


def _run_watch_mode(
    base_url: str,
    timeout: float,
    headers: dict,
    concurrency: int,
    specific_endpoints: List[str],
    output_format: str,
    interval: int,
    fail_on_error: bool,
    asgi_app: Optional[Any] = None,
):
    """Run probe in watch mode (continuous monitoring).

    Args:
        base_url: Base URL of the FastAPI application
        timeout: Request timeout
        headers: Custom headers
        concurrency: Max concurrent requests
        specific_endpoints: List of specific endpoint IDs to check
        output_format: Output format type
        interval: Seconds between checks
        fail_on_error: Whether to exit with error code on failures
        asgi_app: Optional ASGI app to run in-process requests
    """
    click.echo(f"Starting watch mode (checking every {interval} seconds). Press Ctrl+C to stop.\n")

    iteration = 0
    while True:
        iteration += 1
        click.echo(f"--- Check #{iteration} at {time.strftime('%H:%M:%S')} ---")

        exit_code = asyncio.run(
            _run_probe(
                base_url,
                timeout,
                headers,
                concurrency,
                specific_endpoints,
                output_format,
                fail_on_error,
                asgi_app,
            )
        )

        if fail_on_error and exit_code != 0:
            click.echo("\nExiting due to failures (--fail-on-error is set)", err=True)
            sys.exit(exit_code)

        click.echo(f"\nNext check in {interval} seconds...\n")
        time.sleep(interval)


def _parse_headers(header_strings: Tuple[str, ...]) -> dict:
    """Parse header strings into a dictionary.

    Args:
        header_strings: Tuple of "Key: Value" strings

    Returns:
        Dictionary of headers
    """
    headers = {}
    for header_str in header_strings:
        if ":" not in header_str:
            click.echo(
                f'Warning: Invalid header format "{header_str}". Expected "Key: Value"',
                err=True,
            )
            continue
        key, value = header_str.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def _load_asgi_app(import_path: str):
    """Import an ASGI app or factory from a module path like module:attribute."""
    module_path, sep, attr_path = import_path.partition(":")
    if not module_path or not sep or not attr_path:
        raise ValueError("Import path must be in the format 'module:attribute'")

    module = importlib.import_module(module_path)
    target: Any = module
    for part in attr_path.split("."):
        if not hasattr(target, part):
            raise AttributeError(f"Attribute '{part}' not found while resolving '{import_path}'")
        target = getattr(target, part)

    if inspect.iscoroutinefunction(target):
        return asyncio.run(target())  # type: ignore[arg-type]
    if inspect.iscoroutine(target):
        return asyncio.run(target)  # type: ignore[arg-type]
    if callable(target):
        return target()
    return target


def _load_config(config_path: Path) -> dict:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    try:
        import yaml

        with config_path.open("r") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        click.echo(
            "Warning: PyYAML not installed. Install with: pip install pyyaml",
            err=True,
        )
        return {}
    except Exception as e:
        click.echo(f"Warning: Failed to load config file: {e}", err=True)
        return {}


def _merge_config(
    file_config: dict,
    base_url: str,
    timeout: float,
    output_format: str,
    custom_headers: Tuple[str, ...],
    concurrency: int,
    endpoints: Tuple[str, ...],
) -> dict:
    """Merge file config with CLI options (CLI takes precedence).

    Args:
        file_config: Configuration from file
        base_url: CLI base URL argument
        timeout: CLI timeout option
        output_format: CLI output format option
        custom_headers: CLI custom headers
        concurrency: CLI concurrency option
        endpoints: CLI specific endpoints

    Returns:
        Merged configuration dictionary
    """
    # Start with file config
    merged = {
        "base_url": file_config.get("base_url", base_url),
        "timeout": file_config.get("timeout", timeout),
        "output_format": file_config.get("output", {}).get("format", output_format),
        "custom_headers": tuple(
            file_config.get("auth", {}).get("headers", {}).items()
        )
        or custom_headers,
        "concurrency": file_config.get("concurrency", concurrency),
        "asgi_app": file_config.get("transport", {}).get("asgi_app"),
        "endpoints": list(endpoints) or file_config.get("endpoints", {}).get("include", []),
    }

    # CLI options override file config
    if base_url:
        merged["base_url"] = base_url
    if custom_headers:
        merged["custom_headers"] = custom_headers

    return merged


__all__ = ["check"]
