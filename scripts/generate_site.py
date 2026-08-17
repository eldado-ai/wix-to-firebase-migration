#!/usr/bin/env python3
"""
Generate static HTML pages from structured content JSON + one HTML template.

The core idea: keep exactly one template file with placeholder tokens, and
regenerate every page from it. When the user asks for a nav/footer/design
change, edit the template once and rerun this script -- never hand-patch
individual generated pages, which guarantees drift across dozens of files
the moment a second change request comes in.

Run this after download_images.py, not before -- body_blocks/og_image need
to already hold local image paths, not Wix CDN URLs, by the time pages
are generated.

Usage:
    python generate_site.py content.json template.html -o output_dir/ \\
        --slug-field new_slug --img-prefix ""

    # for pages one directory deeper than the site root (e.g. blog/*.html),
    # pass the relative path back up to where img/ actually lives:
    python generate_site.py content.json template.html -o blog/ \\
        --slug-field new_slug --img-prefix "../"

Template placeholders (customize the --token-* flags if your template uses
different names):
    __TITLE__      -> content item's title
    __META__       -> meta description
    __SLUG__       -> the item's slug (for canonical/og:url construction)
    __TAG__        -> a category/tag label, if present in the content JSON
    __OG_IMAGE__   -> og_image path (already prefixed), or "" if none
    __BODY__       -> body_blocks rendered as HTML (headings, paragraphs
                      with inline links/emphasis preserved, and <img> tags)

Content JSON shape expected (one object per page; this is exactly what
extract_wix_content.py + download_images.py produce):
    {
      "new_slug": "some-page",
      "title": "Page Title",
      "meta_description": "...",
      "og_image": "img/hero.jpg",                     (optional, local path)
      "category": "Category",                          (optional)
      "body_blocks": [
        {"type": "heading", "level": 2, "text": "..."},
        {"type": "paragraph", "html": "text with <a href=...> and <strong>"},
        {"type": "image", "src": "img/inline.jpg", "alt": "..."}
      ]
    }
"""
import argparse
import html
import json
import os
import re


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def blocks_to_html(blocks: list[dict], img_prefix: str = "") -> str:
    """
    Render body_blocks to HTML. Paragraph 'html' is already sanitized to a
    small inline allow-list (a/strong/b/em/i/br) by extract_wix_content.py --
    it is intentionally NOT re-escaped here, only inserted as-is, since
    escaping it would turn '<a href="...">' back into visible text.
    """
    parts = []
    for b in blocks:
        t = b.get("type")
        if t == "heading":
            level = min(max(int(b.get("level", 2)), 2), 3)  # h1 is the page title; clamp body headings to h2/h3
            parts.append(f"<h{level}>{esc(b.get('text', ''))}</h{level}>")
        elif t == "paragraph":
            parts.append(f"<p>{b.get('html', '')}</p>")
        elif t == "image":
            src = b.get("src", "")
            if not src:
                continue
            parts.append(f'<img src="{esc(img_prefix + src)}" alt="{esc(b.get("alt", ""))}" loading="lazy">')
    return "".join(parts)


def make_meta(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 3].rsplit(" ", 1)[0]
    return cut + "..."


def render(template: str, item: dict, slug_field: str, tag_field: str, img_prefix: str) -> str:
    slug = item.get(slug_field, item.get("new_slug", ""))
    title = item.get("title", "")
    body_blocks = item.get("body_blocks", [])
    first_text = next(
        (b.get("text") or re.sub("<[^>]+>", "", b.get("html", "")) for b in body_blocks if b.get("type") in ("heading", "paragraph")),
        "",
    )
    meta = item.get("meta_description") or make_meta(first_text or title)
    tag = item.get(tag_field, item.get("category", ""))
    og_image = item.get("og_image", "")

    out = template
    out = out.replace("__TITLE__", esc(title))
    out = out.replace("__META__", esc(meta))
    out = out.replace("__SLUG__", slug)
    out = out.replace("__TAG__", esc(tag))
    out = out.replace("__OG_IMAGE__", esc(img_prefix + og_image) if og_image else "")
    out = out.replace("__BODY__", blocks_to_html(body_blocks, img_prefix))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("content_json", help="Structured content JSON (array of page objects)")
    ap.add_argument("template", help="HTML template file with __TOKEN__ placeholders")
    ap.add_argument("-o", "--output-dir", required=True)
    ap.add_argument("--slug-field", default="new_slug", help="JSON field to use as the output filename (default: new_slug)")
    ap.add_argument("--tag-field", default="category", help="JSON field to use for __TAG__ (default: category)")
    ap.add_argument("--img-prefix", default="", help="Relative path back to where img/ lives from this output dir, e.g. '../' for blog/ (default: '')")
    args = ap.parse_args()

    with open(args.content_json, encoding="utf-8") as f:
        items = json.load(f)

    with open(args.template, encoding="utf-8") as f:
        template = f.read()

    os.makedirs(args.output_dir, exist_ok=True)

    slugs_seen = set()
    written = 0
    for item in items:
        slug = item.get(args.slug_field)
        if not slug:
            print(f"SKIPPING item with no '{args.slug_field}': {item.get('title', '(untitled)')}")
            continue
        if slug in slugs_seen:
            print(f"WARNING: duplicate slug '{slug}' -- later item overwrites earlier one")
        slugs_seen.add(slug)

        page_html = render(template, item, args.slug_field, args.tag_field, args.img_prefix)
        out_path = os.path.join(args.output_dir, f"{slug}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page_html)
        written += 1

    print(f"Wrote {written} pages to {args.output_dir}/")
    if written != len(items):
        print(f"({len(items) - written} items skipped -- see warnings above)")


if __name__ == "__main__":
    main()
