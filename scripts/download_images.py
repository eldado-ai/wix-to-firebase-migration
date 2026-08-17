#!/usr/bin/env python3
"""
Download every image referenced in extracted content (og_image + inline
body_blocks images) to a local folder, and rewrite content.json in place so
those fields point at local paths instead of Wix's CDN.

Run this between extract_wix_content.py and generate_site.py. Skipping it
means the rebuilt site either has no images, or silently keeps hotlinking
images from static.wixstatic.com -- which doesn't fully leave Wix, and can
break later if the user's Wix account is ever closed or the media is moved.

Usage:
    python download_images.py content.json --output-dir img/

Content JSON shape expected (output of extract_wix_content.py):
    {
      "og_image": "https://static.wixstatic.com/media/...",
      "body_blocks": [
        {"type": "image", "src": "https://static.wixstatic.com/media/...", "alt": "..."},
        ...
      ]
    }

After running, image fields hold root-relative local paths like "img/abc123.jpg".
Pass the matching --img-prefix to generate_site.py for each output directory
depth (e.g. "" for pages at the site root, "../" for pages under blog/) --
see references/content-extraction.md.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse

UA = "Mozilla/5.0 (compatible; wix-to-firebase-migration-skill/1.0)"


def original_wix_url(url: str) -> str:
    """
    Wix serves resized/compressed variants at URLs like:
      https://static.wixstatic.com/media/<id>~mv2.jpg/v1/fill/w_800,h_600,al_c,q_80/name.jpg
    The unmodified original usually lives at the bare media path, without the
    /v1/... transform segment:
      https://static.wixstatic.com/media/<id>~mv2.jpg
    Strip it when present so downloaded images aren't stuck at whatever
    resolution one particular page happened to request. Leave non-Wix URLs
    (or ones that don't match this shape) untouched.
    """
    m = re.match(r"(https://static\.wixstatic\.com/media/[^/]+)(/v1/.*)?$", url)
    return m.group(1) if m else url


def local_filename(url: str, seen: dict) -> str:
    name = os.path.basename(urlparse(url).path) or "image"
    if name not in seen:
        seen[name] = url
        return name
    if seen[name] == url:
        return name
    # Same filename, different URL (rare, but Wix ids can collide across
    # differently-cased paths) -- disambiguate rather than overwrite.
    stem, ext = os.path.splitext(name)
    i = 2
    while f"{stem}-{i}{ext}" in seen and seen[f"{stem}-{i}{ext}"] != url:
        i += 1
    disambiguated = f"{stem}-{i}{ext}"
    seen[disambiguated] = url
    return disambiguated


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("content_json", help="Structured content JSON (edited in place)")
    ap.add_argument("--output-dir", default="img", help="Local folder to save images into (default: img)")
    ap.add_argument("--delay", type=float, default=0.2, help="Seconds between downloads (default: 0.2)")
    args = ap.parse_args()

    with open(args.content_json, encoding="utf-8") as f:
        items = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    seen_names = {}       # local filename -> source url (for dedup/collision handling)
    url_to_local = {}      # source url -> "img/<filename>" (root-relative)
    downloaded = 0
    failed = []

    def ensure_local(url: str) -> str:
        nonlocal downloaded
        if not url:
            return ""
        if url in url_to_local:
            return url_to_local[url]
        fetch_url = original_wix_url(url)
        filename = local_filename(fetch_url, seen_names)
        out_path = os.path.join(args.output_dir, filename)
        local_path = f"{args.output_dir}/{filename}"
        if os.path.exists(out_path):
            url_to_local[url] = local_path
            return local_path
        try:
            req = urllib.request.Request(fetch_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            with open(out_path, "wb") as f:
                f.write(data)
            downloaded += 1
            url_to_local[url] = local_path
            time.sleep(args.delay)
            return local_path
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            failed.append((url, str(e)))
            return url  # leave the original URL in place rather than a broken local path

    for item in items:
        if item.get("og_image"):
            item["og_image"] = ensure_local(item["og_image"])
        for block in item.get("body_blocks", []):
            if block.get("type") == "image" and block.get("src"):
                block["src"] = ensure_local(block["src"])

    with open(args.content_json, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"Downloaded {downloaded} images to {args.output_dir}/ ({len(url_to_local) - downloaded} already present or deduped)")
    if failed:
        print(f"\n{len(failed)} FAILED -- these still point at the original Wix URL in {args.content_json}:", file=sys.stderr)
        for url, err in failed:
            print(f"  {url} -- {err}", file=sys.stderr)
        print("\nCheck these by hand: often a Wix media ID that's been deleted or made private.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
