"""Load and parse SOP markdown files."""

import glob
import html
import os
import re
from dataclasses import dataclass


@dataclass
class SOP:
    id: str
    title: str
    body: str
    summary: str = ""
    source_pdf: str = ""
    page_count: int = 0
    images: list = None  # list of image filenames found in this SOP

    def __post_init__(self):
        if self.images is None:
            self.images = []


def _extract_summary(markdown_body: str, max_length: int = 150) -> str:
    """Extract a brief summary from markdown body — first non-heading paragraph."""
    lines = markdown_body.split('\n')
    for line in lines:
        stripped = line.strip()
        # Skip empty lines, headings, and horizontal rules
        if stripped and not stripped.startswith('#') and stripped not in ('---', '---', '***', '___'):
            # Truncate to max_length if needed
            summary = stripped if len(stripped) <= max_length else stripped[:max_length].rsplit(' ', 1)[0] + '…'
            return summary
    return ""


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract frontmatter fields and body from a markdown file with YAML frontmatter."""
    if not text.startswith('---'):
        return {}, text.strip()

    parts = text.split('---', 2)
    frontmatter_raw = html.unescape(parts[1])
    body = parts[2].strip() if len(parts) > 2 else ''

    # Parse key-value pairs with regex instead of YAML to handle unquoted special chars
    meta = {}
    for match in re.finditer(r'^(\w+):\s*(.+)$', frontmatter_raw, re.MULTILINE):
        key = match.group(1)
        value = match.group(2).strip()
        # Remove outer quotes if fully quoted
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        meta[key] = value

    return meta, body


def load_sops(sops_dir: str = None) -> list[SOP]:
    """Load all SOP-*.md files from the sops directory."""
    if sops_dir is None:
        sops_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sops')

    images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
    existing_images = set(os.listdir(images_dir)) if os.path.isdir(images_dir) else set()

    files = sorted(glob.glob(os.path.join(sops_dir, 'SOP-*.md')))
    sops = []

    for filepath in files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        meta, body = _parse_frontmatter(content)

        # Derive title from source_pdf field, stripping .pdf extension
        title = meta.get('source_pdf', os.path.basename(filepath).replace('.md', ''))
        if title.lower().endswith('.pdf'):
            title = title[:-4].strip()

        summary = _extract_summary(body)
        raw_source_pdf = meta.get('source_pdf', '')
        try:
            page_count = int(meta.get('page_count', 0))
        except (ValueError, TypeError):
            page_count = 0

        # Extract image filenames referenced in this SOP — only those that exist on disk
        all_images = re.findall(r'!\[.*?\]\(\.\./images/([^)]+)\)', body)
        images = [f for f in all_images if f in existing_images]

        sops.append(SOP(
            id=meta.get('id', os.path.basename(filepath).replace('.md', '')),
            title=title,
            body=body,
            summary=summary,
            source_pdf=raw_source_pdf,
            page_count=page_count,
            images=images,
        ))

    print(f"Loaded {len(sops)} SOPs. Ready.")
    return sops
