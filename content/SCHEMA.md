# 新知 content schema

> Adapted from joeseesun/xnews (MIT).

Daily updates (parent routine, Asia/Shanghai 08:00) should **fetch with X tools + WebFetch** (no scrapers in this repo), read [`EDITORIAL_PROMPT.md`](./EDITORIAL_PROMPT.md), rewrite text **and source media** into natural, faithful Chinese (third-person editor voice, no persona), then write one JSON file per article and rebuild.

## File

`content/articles/<id>.json`

`id`: kebab-case slug, unique. Example: `karpathy-hackertube`.

## Fields

```json
{
  "id": "karpathy-hackertube",
  "date": "2026-11-01",
  "published_at": "2026-11-01T18:14:46+00:00",
  "ingested_at": "2026-11-06T00:42:37+08:00",
  "source": {
    "type": "x_post | x_article | youtube | web",
    "url": "https://x.com/... or https://www.youtube.com/watch?v=...",
    "author": "Display name",
    "handle": "karpathy",
    "title_en": "Original English title or first line",
    "related_url": "optional secondary link"
  },
  "title": "中文标题",
  "dek": "一句话导读",
  "tags": ["AI coding", "product"],
  "original": {
    "lang": "en",
    "title": "original title or first line",
    "text_md": "full original text as Markdown (preserve line breaks; for X posts include full tweet text; for X Articles full article; for YouTube use title + description / transcript excerpt if available)",
    "media": [
      {"id": "media_stable_id", "type": "image|video|audio|youtube|x_video", "url": "https://...", "alt": "optional verified source alt", "poster": "optional source thumbnail"}
    ]
  },
  "body_md": "完整中文改写正文（Markdown），不混入英文原文；媒体位置用 rewrite_media 描述。",
  "rewrite_media": [
    {
      "media_id": "media_stable_id",
      "placement": "after_body",
      "placement_note": "原文附带媒体；未核验其与具体段落的对应关系。",
      "evidence": "source_metadata_only"
    }
  ]
}
```


### Dates

- `date` / `published_at`: **original source** calendar day and timestamp. Keep these when backfilling older English posts. RSS `pubDate` continues to use them.
- `ingested_at`: **first time this article was published on 新知** as an ISO-8601 timestamp with offset (prefer Asia/Shanghai, `+08:00`). Homepage, `/archive`, and RSS *item order* sort by this field descending. Set it once when the article is first committed for publication; ordinary copy edits must not change it, and rebuild time must never become the sort key.
- Historical rows without a recorded site time were backfilled from the Git commit that first added `content/articles/<id>.json`. Do not invent dates. Missing or invalid `ingested_at` sorts after valid ones, then by `id`.
- Do not reuse `updated_at` (optional correction marker in search metadata) as a homepage sort key.

### `original` (required)

- Store and display the **source** text and any images / video / audio.
- `media` may be `[]` if none.
- Prefer durable HTTPS media URLs from X media / YouTube (no binary downloads into the repo unless tiny and necessary).
- Do **not** invent media. If a known attachment has no usable URL, preserve available metadata and account for it with an explicit `rewrite_media[].omit_reason`; never fabricate a URL.
- Keep `body_md` as the Chinese rewrite only.
- Optional `original.note`: a short, visible, factual note about how the stored original differs from the page (for example inline images moved into `media`). Never use it for opinions.
- **Inline data-URI media** (the source embeds images only as `data:` URIs, so no upstream HTTPS URL exists): decode once into repo `media/<id>.<ext>` (copied to `public/media/` by the build), set `url` to the site's own HTTPS copy, add `"source_note"` explaining it is a byte-for-byte copy of the inline original, and replace the data URI in `text_md` with a short bracketed figure marker. Record this in `original.note`.

### `rewrite_media` (required for editorial output)

Ordered references to `original.media`, not a second copy of the asset. Use `[]` when the source has no media. The build fails if an available original attachment is silently missing, referenced twice, unknown, or imprecisely anchored. One source attachment is rendered at most once **per section**; the rewrite and original remain independently readable, including in RSS.

- Stable identity: `original.media[].id` if present (regex `[A-Za-z][A-Za-z0-9_-]{0,63}`); otherwise `m_` + the first 16 lowercase hexadecimal characters of SHA-256(`type + "\n" + url`, UTF-8). No array-position IDs. History backfill does not modify original objects. Preserve an explicit ID across URL refreshes.
- Known semantic position: `{ "media_id": "...", "placement": "after_paragraph", "after_md": "complete unique Markdown paragraph from body_md", "evidence": "source_position_verified" }`. The anchor must match one complete top-level Markdown paragraph, exactly once; headings, list items, quotations, table cells and fenced code are not paragraph anchors. A change to the text must update its anchor. Reference-style links and multiline paragraphs are supported. Multiple references at one anchor render in array order. Malformed/removed HTML that prevents safe insertion fails the build instead of silently losing the media. Verified placement does not claim video/audio was viewed.
- Unknown semantic position: `{ "media_id": "...", "placement": "after_body", "placement_note": "原文附带媒体；未核验其与具体段落的对应关系。", "evidence": "source_metadata_only" }`. Render a clearly labeled source-media block after the complete Chinese body; do not infer scene/caption/paragraph relationships.
- Exceptional omission: `{ "media_id": "...", "omit_reason": "specific verified reason" }`; the reason is visible in the Chinese page and RSS, and the stored original remains intact. An empty reason is invalid. “It is in the original tab” is not a valid editorial reason.
- Keep every paragraph in `body_md`; do not duplicate body text into media references. Do not add unsupported Markdown placeholders.
- `image`, `video`, `x_video`, `audio`, `youtube` all participate. Unknown future media types retain their original URL as a link instead of disappearing.
- Native video/audio are manual-only (`controls`, `preload=none`); hidden tabs/closed sheets pause media and unload embeds. Always retain an original-open fallback. A poster or HTTP 200 is not evidence that playback worked.
- UI-only small image cache: `src/media-manifest.json` maps verified public source image/poster URLs to `public/media/`. Original JSON and RSS continue to use upstream HTTPS URLs; the build performs no network fetching.


## Build & deploy

```bash
bash publish.sh            # npm test (build + tests), commit, push to GitHub Pages, verify live
bash publish.sh --build-only
```

Outputs: `public/index.html`, `public/a/<id>.html`, fingerprinted `public/read/` payloads, `public/feed.xml`, `public/articles.json`, `public/CNAME`. Deployment: [`DEPLOYMENT.md`](../DEPLOYMENT.md).

## Style

Read [`EDITORIAL_PROMPT.md`](./EDITORIAL_PROMPT.md) and its stable reviewed addon [`EDITORIAL_ADDON.md`](./EDITORIAL_ADDON.md) first. Its fidelity/natural-Chinese rules override generic style templates. The writing-style/tropes references may help expression, but do not require questions, analogies, short-line emphasis or grand endings. Show the Chinese body **with its source-media references**, then **原文** (unaltered original text + media), then 原文链接. The same reference plan renders the Chinese RSS section. Do not ship Chinese KOL digests here.

## Markdown rendering contract

Both `body_md` and `original.text_md` use the same CommonMark parser, with tables and strikethrough enabled, across article pages, reader payloads and RSS HTML. This includes headings, nested lists, blockquotes, fenced/indented code, inline code, images, and inline/reference-style links. Preserve source newlines and code indentation in JSON strings. Tables need a header, a delimiter row, and one newline per row; escape literal cell pipes as `\|`. Do not flatten tables into prose or guess missing row boundaries. This is not a promise to support every Markdown extension (e.g. math, Mermaid or footnotes).

HTML is sanitized with an allowlist. Source scripts, event handlers, arbitrary styles and embeds are removed; validated `rewrite_media` remains the way to insert playable media. Table alignment is preserved, long tables/code scroll within the article on narrow screens, and code indentation is retained. Reference definitions apply across the whole document even when media is inserted between paragraphs. Images load lazily; no browser Markdown parser or additional client dependency is required.

Optional `original.markdown_base_url` must be an absolute HTTPS source document URL, ideally pinned to a revision. It only resolves relative source links/images; it is **not** a switch for Markdown support. Without a base URL, relative URLs are dropped rather than guessed against the website. Absolute links remain available. Original source text is never rewritten by rendering.

# RSS 双版本协议（v1）

复杂来源 Markdown（例如完整 GitHub README）可以设置 `original.markdown_base_url`，值为固定版本的 HTTPS 文档地址。所有正文统一使用 CommonMark + 表格解析和 HTML 白名单净化；该可选字段只决定相对地址的基准。GitHub 图片相对路径解析到该版本的 raw 文件，文档链接解析到同版本页面。原始 `text_md` 不作替换，代码块中的 HTML 仍保留为代码。Python 依赖在 `requirements.txt` 固定版本。

视频可用性需区分未加载、请求失败和实际播放。X CDN 在本轮实测中对带外站 Referer 的媒体请求返回 403，不带 Referer 的公开请求返回视频；本站通过 HTTP 头和 HTML meta 使用 `no-referrer`。RSS 消费端的请求策略由其宿主控制，不能依赖视频标签上的非标准属性覆盖；YouTube iframe 保留自身 referrerpolicy，以满足播放器识别来源的要求。媒体地址和原始 fallback 链接保持不变。

`https://news.nofeetbird.tech/feed.xml` 是 RSS 2.0。标准 `description` 和
`content:encoded` 保持兼容：它们包含完整「中文改写 + 原文」，**不能当作独立原文保存**。
支持双版本的阅读器应读取每个 `item` 中唯一的 `xinzhi:versions`：

```xml
<rss version="2.0" xmlns:xinzhi="https://news.nofeetbird.tech/ns/rss/1.0" ...>
  <channel>
    <item>
      <xinzhi:versions><![CDATA[{"version":1,"original":{"title":"Original title","url":"https://example.com/source","lang":"en","html":"<p>Original text.</p>"},"rewrite":{"title":"中文标题","markdown":"已发布的中文改写。","html":"<p>已发布的中文改写。</p>"}}]]></xinzhi:versions>
    </item>
  </channel>
</rss>
```

上例仅示意字段。JSON 精确结构为：

```ts
{
  version: 1;
  original: { title: string; url: string; lang: string; html: string };
  rewrite: { title: string; markdown: string; html: string };
}
```

- 命名空间 URI 固定为 `https://news.nofeetbird.tech/ns/rss/1.0`；按 URI + 本地名识别字段，不依赖 XML 前缀。JSON 使用 Unicode，CDATA 终止序列会安全拆分；先解析 XML，再解析 JSON。
- `original.html` 只来自 `original.text_md`、原文媒体、来源/相关链接及完整性说明，不包含 `body_md`。无文字时明确显示「暂未保存原文文字」，绝不回退到中文改写；摘录仍标明不是完整逐字稿。原文标题依次使用 `original.title`、`source.title_en`、`Original source`；语言缺失使用 `und`。`original.url` 为 `source.url`，不是本站文章地址。
- `rewrite.title` 为已发布中文标题；`rewrite.html` 使用本站改写渲染器及 `rewrite_media` 的相同位置/遗漏规则，并使用上游绝对媒体 URL，适合外站嵌入。它不包含原文英文正文。`rewrite.markdown` 保留 `body_md` 与媒体位置、说明：图片用 Markdown 图片，音频/视频/YouTube 用明确媒体链接；不会编造转写。
- 两份 HTML 的图片使用 `img`，视频使用带 `controls`、`playsinline`、`preload="none"` 的 `video` 并保留已存 `poster`，音频使用带 `controls`、`preload="none"` 的 `audio`。YouTube 使用 `youtube-nocookie.com/embed/…` iframe，全部媒体保留原始链接作为 fallback，无自动播放。未知媒体类型保留链接；缺失 URL 明确标注。上游媒体可用性及嵌入许可不由本站保证。
- 阅读器应分别保存两份 HTML，安全净化后显示，允许合法媒体标签/属性及受信任的嵌入地址；Markdown 用于复制/上下文。不要将标准混合全文再写入原文，也不要对已发布改写再次调用 AI。旧阅读器可忽略扩展继续使用标准全文；未知协议版本应降级为普通全文，并避免把混合全文标记为独立原文。
