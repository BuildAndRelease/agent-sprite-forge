#!/usr/bin/env python3
"""
Generate a raw sprite-sheet PNG via the Nano Banana Pro API
(gemini-3-pro-image-preview through aiapi.uu.cc).

Usage:
    python3 nanobananagen.py \
        --prompt "A 2x2 pixel art idle sheet ..." \
        --output /path/to/raw-sheet.png \
        [--model gemini-3-pro-image-preview] \
        [--api-key sk-...]

The API key is read from env var AIAPI_UU_CC_KEY by default.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_MODEL = "gemini-3-pro-image-preview"
BASE_URL = "https://aiapi.uu.cc/v1/chat/completions"


def generate_image(prompt: str, model: str, api_key: str) -> bytes:
    """Call Nano Banana Pro API and return raw PNG bytes."""
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        BASE_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"API error {exc.code}: {body}") from exc

    # Extract base64-encoded image from response
    # The model returns markdown like: ![image](data:image/png;base64,<b64>)
    content = ""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected response shape: {json.dumps(data)[:500]}") from exc

    match = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", content)
    if not match:
        raise RuntimeError(
            f"No base64 image found in response. Content preview: {content[:300]}"
        )

    return base64.b64decode(match.group(1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True, help="Full generation prompt for the sprite sheet")
    parser.add_argument("--output", required=True, type=Path, help="Output PNG file path")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key (default: AIAPI_UU_CC_KEY env var)",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("AIAPI_UU_CC_KEY", "")
    if not api_key:
        print(
            "ERROR: No API key provided. Set AIAPI_UU_CC_KEY env var or use --api-key.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[nanobananagen] model={args.model}", file=sys.stderr)
    print(f"[nanobananagen] prompt={args.prompt[:120]}...", file=sys.stderr)

    png_bytes = generate_image(args.prompt, args.model, api_key)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(png_bytes)
    print(f"[nanobananagen] saved {len(png_bytes)} bytes -> {args.output}", file=sys.stderr)
    # Print output path to stdout for pipeline use
    print(str(args.output.resolve()))


if __name__ == "__main__":
    main()
