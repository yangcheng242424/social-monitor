# Social Monitor — GitHub 部署指南

完全免费，Mac 关机/断网不影响运行。GitHub Actions 免费额度每月 2000 分钟（私有仓库），公开仓库无限制。

---

## 部署步骤

### 第一步：创建 GitHub 仓库

1. 打开 https://github.com，登录账号
2. 右上角 **+** → **New repository**
   - Repository name：`social-monitor`
   - Visibility：**Private**
   - 不勾选任何初始化选项
3. 点 **Create repository**

---

### 第二步：上传文件

把以下文件全部上传到仓库：

```
social_monitor.py
requirements.txt
seen_posts.json
.github/workflows/monitor.yml
```

> 可以使用 git 命令行推送，或在仓库页面点 **Add file** → **Upload files** 上传。
> 注意：`.github/workflows/monitor.yml` 需要先创建对应的目录结构。

---

### 第三步：设置 Secrets

进入仓库页面 → **Settings** → 左侧 **Secrets and variables** → **Actions** → **New repository secret**

添加以下 Secret：

| Name | Value |
|---|---|
| `SERVERCHAN_KEY` | 你的 Server酱 SendKey |

> GitHub Actions 使用内置的 `GITHUB_TOKEN` 自动推送，无需额外配置 Push Token。

---

### 第四步：启用 Actions 并手动触发验证

1. 进入仓库页面 → **Actions** 标签页
2. 如果看到提示，点击 **I understand my workflows, go ahead and enable them**
3. 左侧选择 **Social Monitor** workflow
4. 点击 **Run workflow** → **Run workflow** 手动触发一次

查看运行日志：
- 出现 `完毕，本次推送 X 条新内容` → 脚本正常运行 ✅
- 微信收到通知 → 全部完成 ✅

之后每天北京时间 **08:00 和 20:00** 自动运行。

---

## 常见问题

**Q：Actions 日志里显示 push 失败怎么办？**
检查仓库 **Settings** → **Actions** → **General** → **Workflow permissions** 是否设置为 **Read and write permissions**。

**Q：想改成其他时间怎么办？**
编辑 `.github/workflows/monitor.yml` 中的 `cron` 表达式。格式是标准 cron（UTC 时区）。
例如每天北京时间 09:00 运行一次：`0 1 * * *`（UTC 时间 01:00）

**Q：为什么定时任务没有准时运行？**
GitHub Actions 的 schedule 触发可能有几分钟到几十分钟的延迟，这是正常现象。
