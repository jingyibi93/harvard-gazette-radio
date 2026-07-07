# 哈佛公报电台

一个可安装的双语 PWA。GitHub Actions 每天从 163 邮箱以只读 IMAP
方式读取最新 Harvard Gazette 邮件，抓取来源页面，生成中英文节目、
字幕、封面和音频。Vercel 托管 PWA 外壳并代理媒体请求，节目数据存放在
Supabase Storage。

## 安全设计

- GitHub 只保存轻量的 PWA 页面与生成脚本，不保存每日音频和图片。
- 节目 JSON、字幕、音频和图片保存在公开的 Supabase Storage bucket。
- 邮件正文与生成中的 Markdown 简报只存在于临时运行目录。
- 已生成的节目独立存放在 Supabase，之后删除邮箱原邮件不会影响节目。
- 往期和 Supabase 媒体采用滚动十个自然日保留策略，过期文件自动删除。
- 邮箱地址、163 授权密码和 Agnes API Key 只从 GitHub Actions Secrets 读取。
- 新闻链接发布前移除查询参数和邮件收件人追踪标识。
- 任一故事缺少来源链接、封面或音频时，任务失败并保留上一期节目。

## GitHub 设置

在仓库的 **Settings → Secrets and variables → Actions** 中添加：

- `MAIL163_USER`
- `MAIL163_AUTH_CODE`
- `AGNES_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

`SUPABASE_SERVICE_ROLE_KEY` 只能存在于 GitHub Secrets，绝不能写入网页
或提交到仓库。工作流会自动创建名为 `harvard-radio` 的公开 bucket；
公开 bucket 只允许访客读取，上传与删除仍需要服务密钥。

首次部署时，在本机运行 `python3 scripts/configure_cloud.py`。脚本会从
macOS 钥匙串读取已有的 163 与 Agnes 凭据，提示输入 Supabase Project
URL 和 `sb_secret_...` Secret Key，然后把历史节目迁移到 Storage，并通过标准输入
写入 GitHub Secrets。密钥不会出现在命令参数、日志或仓库文件中。

PWA 由 Vercel 部署。第一次可在 **Actions → Daily Harvard Gazette Radio**
中点击 **Run workflow** 手动测试；以后每天北京时间 20:30 自动生成节目，
23:30 再补查一次延迟到达的邮件，并将节目文件同步到 Supabase Storage。
如果当天检查时没有找到可用于生成下一期节目的新 Harvard Gazette 邮件，
工作流不会覆盖旧节目，也不会发送失败邮件；它会正常结束并保留上一期节目。
