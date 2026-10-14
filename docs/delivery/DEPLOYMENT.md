# 交付系统部署准备

本轮仅完成代码和本地隔离测试。没有改动 ECS、官网生产数据库或正式域名。

## staging 准备

1. 创建与官网 SQLite 无关的 PostgreSQL 数据库、数据库用户和仅该数据库的权限。不要复制真实客户数据。生产和 staging 的数据库、账号、密钥及备份目录须分别配置。
2. 使用 Python 3.11+ 环境安装 `pip install -r requirements-delivery.txt`。现有官网仍可只安装 `requirements.txt`。
3. 设置 `SECRET_KEY` 为独立随机值（至少 32 字符）、`DELIVERY_DATABASE_URL=postgresql+psycopg2://...`、`DELIVERY_ENV=staging`。官网 `DATABASE_URL` 继续指向原有 SQLite。数据库 URL 与密钥只放在受限环境文件或密钥服务中，不能提交到 Git。
4. 在 staging 执行 `python -m flask --app app delivery-db-upgrade`；以交互方式执行 `python -m flask --app app delivery-create-admin <account>`。CLI 不接收命令行密码。
5. 通过原有 Gunicorn `app:app` 和 HTTPS Nginx 服务 `/delivery/login`。Nginx 必须拒绝明文访问并设置合理的请求体上限；`SECRET_KEY` 稳定且各环境不同，生产必须设置 `SESSION_COOKIE_SECURE=true`、`SESSION_COOKIE_HTTPONLY=true`、`SESSION_COOKIE_SAMESITE=Lax`。
   当 `DELIVERY_ENV=production` 时，代码会拒绝非 PostgreSQL 交付库或未启用安全 Session Cookie 的配置。
6. 仅使用虚构数据验收员工、家长隔离、CSRF、任务更新、审计、备份与恢复。确认后另行审批真实资料导入及生产发布。

## 上线前门槛

- 在真正的 PostgreSQL staging 空库运行迁移，做一次备份恢复演练，并完成手机及微信内置浏览器人工验收。
- 测试 parent A 无法查看 parent B 项目、未公开任务和内部备注；停用账号后旧会话必须立即失效。
- 核对 `DELIVERY_DATABASE_URL` 与官网 `DATABASE_URL` 指向不同目标，且无生产客户数据混入 staging。
- 现有官网 `/admin` 缺乏鉴权，是原有问题；上线前应独立安排官网后台安全整改，避免同域服务仍有公开管理入口。
- `delivery-db-upgrade` 和真实资料导入命令在 `DELIVERY_ENV=production` 下主动拒绝执行。正式生产迁移须在备份和 staging 演练后，经单独审批发布控制放行；本轮不提供绕过参数。

## 回滚

应用代码回滚到发布前版本不会更改独立交付数据库。若交付模块必须停用，移除 `DELIVERY_DATABASE_URL` 后仅 `/delivery` 返回 503，官网业务继续运行。数据库回滚应优先恢复已验证的备份；不要对包含真实业务记录的生产库运行 Alembic `downgrade`。导入批次的受保护回滚命令只用于未发生后续业务操作的本地或 staging 数据。
