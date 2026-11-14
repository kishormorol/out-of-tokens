"""Turn a built idea page into a PDF with a headless Chrome or Chromium.

The PDF is the page printed through the print stylesheet. The browser does the
text layout, so every script the browser can show (Bangla, Arabic, CJK) comes
out right, and the project needs no PDF library. GitHub's Ubuntu runners ship
Chrome. Where no browser is found the site is built without PDF files and the
pages offer the browser's own "print to PDF" instead.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


def find_chrome() -> str | None:
    """Path of a usable browser, or None. OOT_CHROME overrides the search."""
    override = os.environ.get("OOT_CHROME")
    for name in (override,) if override else CANDIDATES:
        found = shutil.which(name) or (name if Path(name).is_file() else None)
        if found:
            return found
    return None


def html_to_pdf(html: Path, out: Path, chrome: str, timeout: int = 90) -> None:
    """Print ``html`` (a file on disk) to ``out``. Raises RuntimeError on failure."""
    with tempfile.TemporaryDirectory() as profile:
        command = [
            chrome,
            "--headless",
            "--disable-gpu",
            "--disable-extensions",
            "--no-first-run",
            f"--user-data-dir={profile}",  # never touch a person's own browser profile
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",  # the same switch under its older name
            f"--print-to-pdf={out}",
        ]
        if os.environ.get("CI"):
            # Hosted runners do not allow the browser's sandbox. The pages
            # printed here are our own static HTML.
            command.append("--no-sandbox")
        try:
            done = subprocess.run(
                command + [html.resolve().as_uri()],
                capture_output=True,
                text=True,
                timeout=timeout,
                # The browser gets no secrets, whatever the caller's environment holds.
                env={k: v for k, v in os.environ.items() if "TOKEN" not in k and "SECRET" not in k},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"could not print {html.name} to PDF: {exc}") from exc
    if done.returncode != 0 or not out.is_file() or out.stat().st_size < 1000:
        raise RuntimeError(f"could not print {html.name} to PDF: {done.stderr.strip()[-400:]}")
