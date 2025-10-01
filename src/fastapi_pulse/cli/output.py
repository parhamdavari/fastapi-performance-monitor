"""Output formatters for FastAPI Pulse CLI."""

from __future__ import annotations

import json
from typing import Any, Dict, List

try:
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class OutputFormatter:
    """Base class for output formatters."""

    @staticmethod
    def format_results(results: List[Dict[str, Any]], format_type: str = "table") -> str:
        """Format probe results according to the specified format type.

        Args:
            results: List of probe result dictionaries
            format_type: Output format ("json", "table", or "summary")

        Returns:
            Formatted output string
        """
        if format_type == "json":
            return JSONFormatter.format(results)
        elif format_type == "summary":
            return SummaryFormatter.format(results)
        else:  # default to table
            return TableFormatter.format(results)


class JSONFormatter:
    """JSON output formatter."""

    @staticmethod
    def format(results: List[Dict[str, Any]]) -> str:
        """Format results as JSON.

        Args:
            results: List of probe result dictionaries

        Returns:
            JSON string
        """
        summary = _calculate_summary(results)
        output = {
            "summary": summary,
            "endpoints": results,
        }
        return json.dumps(output, indent=2)


class SummaryFormatter:
    """Summary output formatter."""

    @staticmethod
    def format(results: List[Dict[str, Any]]) -> str:
        """Format results as a brief summary.

        Args:
            results: List of probe result dictionaries

        Returns:
            Summary string
        """
        summary = _calculate_summary(results)

        # Use emoji/symbols for visual feedback
        healthy_symbol = "✓" if RICH_AVAILABLE else "OK"
        warning_symbol = "⚠" if RICH_AVAILABLE else "WARN"
        critical_symbol = "✗" if RICH_AVAILABLE else "FAIL"
        skipped_symbol = "○" if RICH_AVAILABLE else "SKIP"

        output_lines = [
            f"{healthy_symbol} {summary['healthy']} healthy  "
            f"{warning_symbol} {summary['warning']} warnings  "
            f"{critical_symbol} {summary['critical']} critical  "
            f"{skipped_symbol} {summary['skipped']} skipped",
            f"Total: {summary['total']} endpoints",
        ]

        if summary.get("avg_latency_ms"):
            output_lines.append(f"Avg latency: {summary['avg_latency_ms']:.1f}ms")

        return "\n".join(output_lines)


class TableFormatter:
    """Table output formatter using Rich library."""

    @staticmethod
    def format(results: List[Dict[str, Any]]) -> str:
        """Format results as a table.

        Args:
            results: List of probe result dictionaries

        Returns:
            Table string
        """
        if not RICH_AVAILABLE:
            return TableFormatter._format_simple(results)

        console = Console()
        table = Table(title="FastAPI Pulse - Endpoint Health Check", show_header=True)

        table.add_column("Endpoint", style="cyan", no_wrap=True)
        table.add_column("Status", style="bold")
        table.add_column("Latency", justify="right")
        table.add_column("Code", justify="center")
        table.add_column("Error", style="dim", max_width=40)

        for result in results:
            endpoint_id = result["endpoint_id"]
            status = result["status"]
            latency_ms = result.get("latency_ms")
            status_code = result.get("status_code")
            error = result.get("error", "")

            # Color-coded status
            if status == "healthy":
                status_display = Text("✓ healthy", style="green")
            elif status == "warning":
                status_display = Text("⚠ warning", style="yellow")
            elif status == "critical":
                status_display = Text("✗ critical", style="red")
            else:  # skipped
                status_display = Text("○ skipped", style="dim")

            # Format latency
            latency_str = f"{latency_ms:.1f}ms" if latency_ms is not None else "-"

            # Format status code
            code_str = str(status_code) if status_code is not None else "-"

            # Truncate error message
            error_str = (error[:37] + "..." if len(error) > 40 else error) if error else ""

            table.add_row(
                endpoint_id,
                status_display,
                latency_str,
                code_str,
                error_str,
            )

        # Capture table output
        with console.capture() as capture:
            console.print(table)

        output = capture.get()

        # Add summary
        summary = _calculate_summary(results)
        summary_text = (
            f"\n[bold]Summary:[/bold] "
            f"[green]{summary['healthy']} healthy[/green]  "
            f"[yellow]{summary['warning']} warnings[/yellow]  "
            f"[red]{summary['critical']} critical[/red]  "
            f"[dim]{summary['skipped']} skipped[/dim]"
        )

        if summary.get("avg_latency_ms"):
            summary_text += f"  |  Avg latency: {summary['avg_latency_ms']:.1f}ms"

        with console.capture() as capture:
            console.print(summary_text)

        output += capture.get()

        return output

    @staticmethod
    def _format_simple(results: List[Dict[str, Any]]) -> str:
        """Fallback simple table format without Rich library.

        Args:
            results: List of probe result dictionaries

        Returns:
            Simple table string
        """
        lines = []
        lines.append("-" * 80)
        lines.append(f"{'Endpoint':<35} {'Status':<12} {'Latency':<12} {'Code':<8}")
        lines.append("-" * 80)

        for result in results:
            endpoint_id = result["endpoint_id"][:34]
            status = result["status"]
            latency_ms = result.get("latency_ms")
            status_code = result.get("status_code")

            latency_str = f"{latency_ms:.1f}ms" if latency_ms is not None else "-"
            code_str = str(status_code) if status_code is not None else "-"

            lines.append(f"{endpoint_id:<35} {status:<12} {latency_str:<12} {code_str:<8}")

        lines.append("-" * 80)

        summary = _calculate_summary(results)
        lines.append(
            f"Summary: {summary['healthy']} healthy, {summary['warning']} warnings, "
            f"{summary['critical']} critical, {summary['skipped']} skipped"
        )

        return "\n".join(lines)


def _calculate_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate summary statistics from probe results.

    Args:
        results: List of probe result dictionaries

    Returns:
        Summary dictionary
    """
    total = len(results)
    healthy = sum(1 for r in results if r["status"] == "healthy")
    warning = sum(1 for r in results if r["status"] == "warning")
    critical = sum(1 for r in results if r["status"] == "critical")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    latencies = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
    avg_latency_ms = sum(latencies) / len(latencies) if latencies else None

    return {
        "total": total,
        "healthy": healthy,
        "warning": warning,
        "critical": critical,
        "skipped": skipped,
        "avg_latency_ms": avg_latency_ms,
    }


__all__ = ["OutputFormatter", "JSONFormatter", "TableFormatter", "SummaryFormatter"]
