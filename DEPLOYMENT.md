# 部署

- 源码分支 `main`：`content/`、`scripts/`、`src/`、`tests/`、已测试的 `public/`。
- 站点分支 `gh-pages`：`public/` 的内容（含 `CNAME`=`news.nofeetbird.tech`、`.nojekyll`）。GitHub Pages 以 legacy 模式从 `gh-pages` 根目录发布。
- DNS：Cloudflare 区域 `nofeetbird.tech` 中 `news` CNAME → `nofeetbird0321.github.io`，关闭代理（DNS only），与 `jobs` 相同。
- 发布：`bash publish.sh`（使用盒子上已登录的 `gh` 账号 `nofeetbird0321` 作为 git 凭据助手，不在仓库中保存任何凭据）。
- 回滚：在 `gh-pages` 上 `git revert` 最近的 `site …` 提交并推送。旧的 `/static/` 与 `/read/` 指纹文件会保留在 `public/` 中供缓存页面引用。
