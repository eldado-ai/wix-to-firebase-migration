#!/usr/bin/env python3
"""
Extract rendered content from Wix pages (blog posts, static pages) into
structured JSON -- including the light structure (headings, inline links/
emphasis, images) that a plain-text extraction throws away.

Wix pages are client-side rendered -- the article body is populated by
JavaScript after load, so a plain HTTP fetch only returns the page shell.
This script uses a headless browser (Playwright) to render each page and
walk the DOM after JS has run.

If Playwright isn't available in the current environment, don't fight it --
this same extraction works fine done interactively through a browser
automation tool instead (navigate, wait for load, read the rendered DOM),
just page-by-page instead of batched. See references/content-extraction.md.

Setup (one-time):
    pip install playwright
    playwright install chromium

Usage:
    python extract_wix_content.py urls.txt -o content.json
    python extract_wix_content.py urls.txt -o content.json --selector "article"

Input: a text file with one URL per line (output of discover_wix_pages.py).
Output: a JSON array of {url, title, meta_description, og_image, body_blocks}.

body_blocks is a list of {"type": "heading"|"paragraph"|"image", ...} --
see references/content-extraction.md for the exact shape and why blocks
replace a flat list of paragraph strings. Feed this straight into
scripts/download_images.py before generate_site.py, so images are on disk
and body_blocks/og_image point at local paths by the time you generate pages.

This intentionally does NOT invent a "new_slug" or "category" for you --
those are content decisions. Fill them in as a second pass once you've
looked at the extracted titles, or hand this file to Claude to do it in
context of the rest of the migration.
"""
import argparse
import json
import re
import sys
import time


# Allow-list inline sanitizer for paragraph HTML captured from the user's own
# Wix site. This is NOT safe for arbitrary/untrusted HTML -- it's a regex
# strip, not a real parser -- but the input here is always the user's own
# published content, not third-party or attacker-controlled input, so that
# tradeoff is fine. It exists to drop Wix's own presentational wrapper spans
# (which carry inline styles/classes you don't want) while keeping the
# handful of inline tags that actually carry meaning: links and emphasis.
_ALLOWED_INLINE = {"a", "strong", "b", "em", "i", "br"}
_TAG_RE = re.compile(r"<(/?)([a-zA-Z0-9]+)([^>]*)>")


def sanitize_inline_html(html: str) -> str:
    def repl(m):
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if tag not in _ALLOWED_INLINE:
            return ""
        if tag == "a" and not closing:
            href_m = re.search(r'href\s*=\s*"([^"]*)"', attrs) or re.search(r"href\s*=\s*'([^']*)'", attrs)
            href = href_m.group(1) if href_m else ""
            return f'<a href="{href}">' if href else ""
        return f"</{tag}>" if closing else f"<{tag}>"

    cleaned = _TAG_RE.sub(repl, html)
    # Collapse whitespace left behind by stripped block-level wrappers (Wix
    # nests spans/divs inside paragraphs more than you'd expect).
    return re.sub(r"\s+", " ", cleaned).strip()


_EXTRACT_JS = """
(sel) => {
  const el = document.querySelector(sel) || document.body;
  const blocks = [];
  el.querySelectorAll(':scope > *').forEach((child) => {
    const tag = child.tagName.toLowerCase();
    if (/^h[1-6]$/.test(tag)) {
      const text = (child.innerText || '').trim();
      if (text) blocks.push({type: 'heading', level: parseInt(tag[1], 10), text});
      return;
    }
    if (tag === 'img') {
      blocks.push({type: 'image', src: child.src, alt: child.alt || ''});
      return;
    }
    if (tag === 'figure') {
      const img = child.querySelector('img');
      if (img) blocks.push({type: 'image', src: img.src, alt: img.alt || ''});
      return;
    }
    // Anything else: treat as a paragraph-ish block, but first pull out any
    // images nested inside it (Wix sometimes wraps an image in a plain div
    // alongside caption text) so they aren't lost.
    child.querySelectorAll('img').forEach((img) => {
      blocks.push({type: 'image', src: img.src, alt: img.alt || ''});
    });
    const text = (child.innerText || '').trim();
    if (text) blocks.push({type: 'paragraph', html: child.innerHTML});
  });
  return blocks;
}
"""


def extract_one(page, url: str, selector: str) -> dict:
    page.goto(url, wait_until="networkidle", timeout=30000)
    # Give client-side rendering a moment to settle beyond "networkidle" --
    # Wix sometimes finishes a late render pass just after network activity quiets.
    page.wait_for_timeout(500)

    title = page.title()

    meta_description = page.evaluate(
        """() => {
            const m = document.querySelector('meta[name="description"], meta[property="og:description"]');
            return m ? m.getAttribute('content') : '';
        }"""
    )

    og_image = page.evaluate(
        """() => {
            const m = document.querySelector('meta[property="og:image"]');
            return m ? m.getAttribute('content') : '';
        }"""
    )

    raw_blocks = page.evaluate(_EXTRACT_JS, selector)

    blocks = []
    for b in raw_blocks:
        if b["type"] == "paragraph":
            b = {"type": "paragraph", "html": sanitize_inline_html(b["html"])}
            if not b["html"]:
                continue
        blocks.append(b)

    return {
        "url": url,
        "title": title,
        "meta_description": meta_description or "",
        "og_image": og_image or "",
        "body_blocks": blocks,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls_file", help="Text file with one URL per line")
    ap.add_argument("-o", "--output", default="content.json")
    ap.add_argument("--selector", default="article", help="CSS selector for the content container (default: article)")
    ap.add_argument("--delay", type=float, default=0.3, help="Seconds to wait between page loads (default: 0.3)")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright isn't installed in this environment.\n\n"
            "Install it with:\n"
            "    pip install playwright && playwright install chromium\n\n"
            "Or skip this script and extract interactively instead, using whatever\n"
            "browser automation tool is available in this session -- navigate to each\n"
            "URL, wait for it to load, and read the rendered DOM. Same result, just\n"
            "one page at a time instead of batched. See references/content-extraction.md.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(args.urls_file, encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"Extracting {len(urls)} pages...", file=sys.stderr)

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for i, url in enumerate(urls, 1):
            print(f"  [{i}/{len(urls)}] {url}", file=sys.stderr)
            try:
                results.append(extract_one(page, url, args.selector))
            except Exception as e:
                print(f"    FAILED: {e}", file=sys.stderr)
                results.append({"url": url, "title": "", "meta_description": "", "og_image": "", "body_blocks": [], "error": str(e)})
            time.sleep(args.delay)
        browser.close()

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    failed = sum(1 for r in results if r.get("error"))
    image_count = sum(1 for r in results for b in r.get("body_blocks", []) if b["type"] == "image")
    image_count += sum(1 for r in results if r.get("og_image"))
    print(f"\nWrote {len(results)} pages to {args.output} ({failed} failed)", file=sys.stderr)
    print(f"Found {image_count} image references -- run download_images.py next, before generate_site.py.", file=sys.stderr)
    if failed:
        print("Review failed entries -- often a slug encoding mismatch or a soft-404.", file=sys.stderr)


if __name__ == "__main__":
    main()
