# XDU 搭子云端部署

这个版本支持两种数据库：

- 本地开发：不设置 `DATABASE_URL`，自动使用 `xdu_partner.db`。
- 云端部署：设置 `DATABASE_URL`，自动使用 PostgreSQL 云数据库。

## 推荐：Supabase + Vercel

1. 在 Supabase 创建项目。
2. 进入 Supabase 的数据库连接页面，复制 PostgreSQL 连接串。
3. 在 Vercel 导入这个 GitHub 仓库。
4. Framework Preset 选择 `Other`。
5. 在 Vercel 的环境变量里填写：

```bash
DATABASE_URL=你的 Supabase PostgreSQL 连接串
```

6. 点击 Deploy，部署完成后访问 Vercel 提供的公网 URL。

如果部署平台不支持 IPv6，优先使用 Supabase 的 Session Pooler 连接串。Supabase 连接串通常还需要带上 `sslmode=require`。

Vercel 部署使用：

- `vercel.json`：把请求转发到 Python API。
- `api/index.py`：Flask serverless 后端，同时提供静态页面和 API。
- `requirements.txt`：安装 Flask 和 PostgreSQL 驱动。

## 备选：Render

## 其他云平台

在 Railway、Fly.io、阿里云、腾讯云或任意云服务器上部署时，需要：

1. 安装依赖：`pip install -r requirements.txt`
2. 配置环境变量：`DATABASE_URL`
3. 启动服务：`python -u server.py`

服务会读取平台提供的 `PORT` 并监听 `0.0.0.0`，用户注册、发布招募、接受/拒绝都会写入云端 PostgreSQL。
