# Content extraction

The goal of this phase is a structured inventory of every page on the Wix site — not finished HTML, just the data. Phase 2 turns data into pages; keeping them separate is what lets you regenerate 40 pages from one template edit instead of hand-patching each one.

## Step 1: Get the real page list from the sitemap

Never enumerate pages by browsing the site's own navigation or blog listing. Wix blog index pages are commonly paginated or capped, showing a handful of recent posts while the sitemap lists everything. On a real migration this difference was 4 visible posts vs. 44 actual posts — a 10× gap that would have silently dropped 90% of the content if the navigation had been trusted.

```bash
curl -s https://<domain>/sitemap.xml
```

Wix's sitemap is usually an index pointing at sub-sitemaps (`pages-sitemap.xml`, `blog-posts-sitemap.xml`, etc.) rather than a flat list. Follow every `<loc>` in the index, then extract every `<loc>` from each sub-sitemap. `scripts/discover_wix_pages.py` does this and writes a flat URL list.

Cross-check the count with the user: "The sitemap lists 44 blog posts — does that match what you'd expect?" If the site has a page type the sitemap doesn't cover (some Wix apps register their own routes outside the standard sitemap), the user will know.

## Step 2: Extract rendered content, not raw HTML

Wix pages are client-side rendered. A plain `curl` returns the initial HTML shell — enough to read `<title>` and `og:` meta tags, but the article body is populated by JavaScript after load and will not be in that response.

```bash
curl -s https://example.com/post/some-slug | grep -o '<meta property="og:description"[^>]*>'
```

This works for meta tags but the `og:description` Wix generates is truncated (~500 characters, often cut mid-word) — treat it as a fallback for the meta description on the new page, never as the article body.

For the actual body, render the page and read the DOM after JS executes — and capture more than plain text while you're in there. `scripts/extract_wix_content.py` does this with a headless browser (Playwright): it walks the `<article>` element's children and produces a list of typed blocks (`heading`, `paragraph`, `image`) instead of one flattened string. Extracting only `innerText`, the tempting shortcut, silently throws away every subheading, inline link, and embedded image in the post — real content loss that isn't obvious until someone compares the new page against the old one line by line. If a headless browser isn't available in the current environment, drive it interactively instead: navigate to the URL, wait for load, and read the rendered DOM the same way — the result is the same, just page-by-page instead of batched.

Batch requests where possible rather than one page load per round trip — loading several pages back-to-back before extracting is significantly faster than a strict navigate-then-extract-then-navigate loop, especially across dozens of pages.

## Step 3: Store as structured data

One record per page, not per finished file:

```json
{
  "old_url": "https://example.com/post/some-slug",
  "old_slug": "some-slug",
  "new_slug": "english-readable-slug",
  "title": "Post title",
  "category": "Category label",
  "og_image": "https://static.wixstatic.com/media/...",
  "body_blocks": [
    {"type": "heading", "level": 2, "text": "A subheading"},
    {"type": "paragraph", "html": "Text with a <a href=\"...\">link</a> and <strong>emphasis</strong>."},
    {"type": "image", "src": "https://static.wixstatic.com/media/...", "alt": "..."}
  ]
}
```

Three fields matter beyond the obvious:

- **`old_url`/`old_slug`** — needed later to generate the 301 redirect map (Phase 6). Losing this means re-deriving it from scratch, which is fully avoidable by capturing it now.
- **`new_slug`** — pick a stable, readable, ASCII slug per page at extraction time (transliterate or translate the old slug's meaning, don't just percent-decode it). Deciding this once here, rather than ad hoc during site generation, keeps the old→new mapping unambiguous.
- **`body_blocks`** — replaces a flat paragraph list. Paragraph `html` is pre-sanitized to a small inline allow-list (`a`, `strong`, `b`, `em`, `i`, `br`) at extraction time, stripping Wix's presentational wrapper spans/classes while keeping the handful of tags that carry real meaning. Headings stay separate from paragraphs so the rebuild can render them as actual `<h2>`/`<h3>` elements, not flattened prose.

## Step 4: Download referenced images before generating pages

`og_image` and every `image`-type block still point at Wix's CDN (`static.wixstatic.com`) at this point — `scripts/download_images.py` downloads each one to a local folder and rewrites those fields to local paths, in place:

```bash
python download_images.py content.json --output-dir img/
```

Skipping this step means the rebuilt site either ships with no images, or keeps silently hotlinking `static.wixstatic.com` — which doesn't actually leave Wix, and breaks if the user's Wix account is ever closed or the media reorganized.

Two things worth knowing before running it:

- **Wix serves resized variants at URLs like `.../media/<id>~mv2.jpg/v1/fill/w_800,h_600,al_c/name.jpg`.** The script strips the `/v1/...` transform segment to fetch the original-resolution file at the bare `.../media/<id>~mv2.jpg` path instead of whatever one page happened to request — otherwise every image ends up capped at its smallest on-site usage size.
- **This is a real download loop against Wix's servers, not local file copying.** It runs with a small delay between requests by default and reports failures explicitly rather than leaving a broken path silently in place — a handful of failures usually means a deleted or made-private Wix media ID, worth a manual check rather than a retry.

Run `generate_site.py` (Phase 2) only after this step — pass it `--img-prefix` matching each output directory's depth relative to `img/` (empty string at the site root, `../` for pages one level down, e.g. under `blog/`).

## Common issues

**A fetched URL returns a 404 or unrelated content.** Usually a slug decoding mismatch, or the site returning a soft-404 page instead of an HTTP error — check the page title in the response before trusting the body. Retry with a short wait; occasionally a batch of rapid navigations in the same tab causes one request to resolve before the previous page fully unloaded.

**Special characters in URLs (non-Latin scripts, ampersands, etc.).** URL-encode when constructing requests, but keep the decoded, human-readable form in your data — you'll need the decoded form later for the raw (non-percent-encoded) redirect source in `firebase.json` (see `references/seo-checklist.md`).
