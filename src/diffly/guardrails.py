"""
Diffly Guardrails & Sanitization Engine.

Provides deterministic pre-flight sanitizers and post-flight egress guards to defend against:
1. Invisible Unicode / Trojan Source prompt injection attacks (zero-width characters, bidi overrides).
2. OOM & Token exhaustion from lockfiles, minified bundles, and massive diffs.
3. Markdown image data exfiltration pingbacks.
"""

import re
from typing import NamedTuple

# Regex matching zero-width spaces, bidi overrides, and invisible Unicode formatting
INVISIBLE_UNICODE_PATTERN = re.compile(
    r"[\u200B-\u200D\u200E\u200F\u202A-\u202E\u2060-\u206F\uFEFF]"
)

# Denylisted file patterns (lockfiles, minified bundles, images, binaries)
DENYLIST_EXTENSIONS = (
    ".min.js",
    ".min.css",
    ".map",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".wasm",
    ".pdf",
    ".bin",
)

DENYLIST_FILENAMES = (
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "poetry.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "go.sum",
)

# Regex matching markdown images: ![alt](url)
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\((https?://[^\)]+)\)", re.IGNORECASE)

# Regex matching raw HTML <img> tags
HTML_IMAGE_PATTERN = re.compile(r"<img\s+[^>]*src=[\"'](https?://[^\"']+)[\"'][^>]*>", re.IGNORECASE)

# Line threshold cap for deep specialist scans
MAX_DIFF_LINES = 1500


class SanitizedDiffResult(NamedTuple):
    clean_diff: str
    filtered_files: list[str]
    was_truncated: bool


def strip_invisible_unicode(text: str) -> str:
    """Strip zero-width characters and bidirectional overrides from untrusted text."""
    return INVISIBLE_UNICODE_PATTERN.sub("", text)


def filter_diff_content(raw_diff: str) -> SanitizedDiffResult:
    """
    Process raw git diff:
    1. Strip invisible Unicode (Trojan Source defense).
    2. Filter out denylisted lockfiles and binary/minified files.
    3. Cap diff length to prevent runaway token spend / OOM.
    """
    clean_text = strip_invisible_unicode(raw_diff)

    # Split into file diff blocks
    # Unified diff blocks start with "diff --git a/..."
    if not clean_text.startswith("diff --git"):
        # Not a multi-file unified diff or headerless diff
        lines = clean_text.splitlines()
        was_truncated = len(lines) > MAX_DIFF_LINES
        if was_truncated:
            clean_text = (
                "\n".join(lines[:MAX_DIFF_LINES])
                + f"\n\n[Diff truncated: exceeded {MAX_DIFF_LINES} lines guardrail. Only top {MAX_DIFF_LINES} lines reviewed.]"
            )
        return SanitizedDiffResult(clean_diff=clean_text, filtered_files=[], was_truncated=was_truncated)

    raw_blocks = clean_text.split("diff --git ")
    accepted_blocks: list[str] = []
    filtered_files: list[str] = []

    for block in raw_blocks:
        if not block.strip():
            continue

        # Header line: "a/path/to/file b/path/to/file"
        header_line = block.splitlines()[0].strip()
        # Extract filename from b/ path
        parts = header_line.split(" b/")
        target_path = parts[-1] if len(parts) > 1 else header_line

        filename = target_path.split("/")[-1]

        # Check denylists
        is_denylisted = (
            filename in DENYLIST_FILENAMES
            or any(target_path.endswith(ext) for ext in DENYLIST_EXTENSIONS)
        )

        if is_denylisted:
            filtered_files.append(target_path)
        else:
            accepted_blocks.append("diff --git " + block)

    reconstructed_diff = "".join(accepted_blocks)
    lines = reconstructed_diff.splitlines()
    was_truncated = len(lines) > MAX_DIFF_LINES

    if was_truncated:
        reconstructed_diff = (
            "\n".join(lines[:MAX_DIFF_LINES])
            + f"\n\n[Diff truncated: exceeded {MAX_DIFF_LINES} lines guardrail. Only top {MAX_DIFF_LINES} lines reviewed.]"
        )

    return SanitizedDiffResult(
        clean_diff=reconstructed_diff,
        filtered_files=filtered_files,
        was_truncated=was_truncated,
    )


def sanitize_review_output(text: str) -> str:
    """
    Sanitize generated review comments and summary to prevent markdown/HTML data exfiltration.
    Strips external image tags that could pingback third-party tracking servers.
    """
    # Replace markdown images ![alt](url) with safe placeholder
    sanitized = MARKDOWN_IMAGE_PATTERN.sub(r"[External Image Suppressed: \1]", text)
    # Replace HTML <img> tags with safe placeholder
    sanitized = HTML_IMAGE_PATTERN.sub(r"[External Image Suppressed]", sanitized)
    return sanitized
