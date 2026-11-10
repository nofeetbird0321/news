# 新知

AI、Web3 与数据领域的海外一手长文（作者长帖、X Articles、个人与官方博客）→ **完整、忠实的中文改写**，保留原文、原媒体与原链接，附全文 RSS。

- Live: https://news.nofeetbird.tech
- RSS: https://news.nofeetbird.tech/feed.xml
- Hosting: GitHub Pages（`gh-pages` 分支，自定义域名 `news.nofeetbird.tech`，Cloudflare DNS 仅解析、不代理）

改编自 [joeseesun/xnews](https://github.com/joeseesun/xnews)（MIT），见 [LICENSE](./LICENSE)。

## 开发

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
npm ci
PATH="$PWD/.venv/bin:$PATH" npm test     # build + python tests + jsdom reader tests
npm run preview -- --port 33205
```

## 每日更新（给例行任务）

1. 选题：过去 24 到 72 小时内 AI、Web3、数据领域的英文一手内容（作者本人长帖 / X Articles / 个人或官方博客）。跳过已收录的 `source.url`。
2. 取原文：只用现成的 X 工具（`get_posts_by_id` 等，长帖取 `note_tweet`，媒体取 `attachments.media_keys`）和 WebFetch / curl 读公开页面。**不新增爬虫**。
3. 读 [`content/EDITORIAL_PROMPT.md`](./content/EDITORIAL_PROMPT.md)、[`content/EDITORIAL_ADDON.md`](./content/EDITORIAL_ADDON.md)、[`content/SCHEMA.md`](./content/SCHEMA.md)，写 `content/articles/<id>.json`：完整 `original.text_md` + `original.media`，完整中文 `body_md`，逐个对账的 `rewrite_media`，`ingested_at` 填本次首次收录时间（`+08:00`），之后不改。
4. `python3 tools/lock_sources.py` 锁定新文章的来源字段哈希。
5. `bash publish.sh`：跑全部测试 → 提交并推送 `main` → 把 `public/` 同步到 `gh-pages` → 核实线上首页和 `feed.xml` 出现最新文章。退出码：0 成功，1 构建或测试失败，3 无 GitHub 凭据或推送失败，4 线上核实失败。
6. 建议时间：每日 08:00（中国标准时间，UTC+8）。

## 许可

MIT。文章内容版权归原作者，本站保留署名与原始链接。
