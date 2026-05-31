# XDU 搭子云端部署

这个版本支持两种数据库：

- 本地开发：不设置 `DATABASE_URL`，自动使用 `xdu_partner.db`。
- 云端部署：设置 `DATABASE_URL`，自动使用 PostgreSQL 云数据库。

## Render 一键部署思路

1. 把本项目推送到 GitHub。
2. 在 Render 新建 Blueprint，选择这个仓库。
3. Render 会读取 `render.yaml`，自动创建 Web Service 和 PostgreSQL 数据库。
4. 部署完成后访问 Render 提供的公网 URL。

## 其他云平台

在 Railway、Fly.io、阿里云、腾讯云或任意云服务器上部署时，需要：

1. 安装依赖：`pip install -r requirements.txt`
2. 配置环境变量：`DATABASE_URL`
3. 启动服务：`python -u server.py`

服务会读取平台提供的 `PORT` 并监听 `0.0.0.0`，用户注册、发布招募、接受/拒绝都会写入云端 PostgreSQL。
