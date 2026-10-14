# 瀛动申请交付系统 V1.0：仓库审查与接入方案

## 已知事实（2026-10-14，只读审查）

- 官网为 Flask 3.1.0 + Jinja2 + Flask-SQLAlchemy 3.1.1 单体应用；入口 `app.py`。全站公共导航使用 Bootstrap CDN 和 `static/styles.css`，部分独立页面加载 Tailwind CDN。
- 现有 `Ranking`、`Booking` 使用 `DATABASE_URL`，默认 Flask instance 目录中的 SQLite `rankings.db`。没有 Alembic、用户表、角色和登录中间件。
- 现有 `/admin`、预约后台和资料下载路由不具备账号鉴权；启动时的 `ensure_ranking_schema()` 使用 SQLite `PRAGMA` 和直接补列。该数据库不能直接改为 PostgreSQL 供新模块共用。
- 当前仓库没有生产 Nginx/systemd 配置、Preview 环境、GitHub Actions 或生产数据库凭据；实际 ECS 状态无法从仓库验证。
- 四份参考文件只读检查：V1.1 主表有 5 个学生、120 条学生任务、四组共 96 条模板。个案旧表的 24 条任务与 V1.1 重复，状态没有冲突。V0.2 HTML 的 120 条任务与 V1.1 重复，状态没有冲突；HTML 把真实资料放在 `SEED` 并使用浏览器 `localStorage`，不具备账号隔离或多端同步。《瀛动申请交付 OS｜V1.0.xlsx》实际填充单元格仅有表头，不能作为数据来源。SOP 文本未提供。
- 审查时 Git 工作树干净，原有测试为 20 项。真实学生资料未复制到仓库。

## 集成选择

同一 Flask 应用注册 `/delivery` Blueprint，沿用官网域名与基本视觉体系；交付系统使用 `DELIVERY_DATABASE_URL` 独立数据库和独立 SQLAlchemy engine。公共预约 SQLite 的 schema 与业务逻辑不改动。交付路径跳过旧的 SQLite `PRAGMA` 启动补列，避免新模块请求触碰官网数据库。

代码边界：

| 层 | 文件 | 责任 |
| --- | --- | --- |
| HTTP/权限 | `delivery/routes.py` | 登录、RBAC、项目归属、表单 CSRF、员工和家长视图 |
| 持久化 | `delivery/models.py`, `delivery/storage.py` | 独立引擎、事务、模型 |
| 迁移 | `delivery/migrations/` | Alembic 版本化 schema |
| 原始数据 | `delivery/importer.py`, `delivery/commands.py` | 只读预览、摘要确认、原子导入与受保护回滚 |
| 呈现 | `templates/delivery/`, `static/delivery.css` | 员工工作台、手机优先家长门户 |

## 数据与权限

实体包括用户、学生、家长授权、项目、模板、任务、负责人、里程碑、任务变更、附件元信息、导入批次与管理审计。家长须同时满足账号 `parent`、学生授权、任务 `parent_visible`，才能看到任务。内部备注、导入原文和变更细节永不传给家长视图。员工只访问自己负责的项目；管理员管理全部项目及授权。任务完成度不使用简单百分比；家长页按阶段、公开任务状态和公开里程碑展示。

模板从 V1.1 导入时一律 `pending_review`。管理员审核为 `standard` 后，才会为新项目自动生成任务。条件任务和个案任务不会自动生成。真实资料只可在私有数据库通过人工确认导入；公开仓库只保存映射代码与虚构测试数据。

原始资料的完整字段映射与异常处理见 [SOURCE_MAPPING.md](SOURCE_MAPPING.md)。

## 最小部署改动

现有 Gunicorn 入口仍是 `app:app`，无需替换 Nginx 路由。只有启用交付模块的环境需要安装 `requirements-delivery.txt`，设置独立数据库 URL 与强 `SECRET_KEY`，执行 Alembic 迁移。未完成配置时 `/delivery` 返回 503；官网原有页面不受影响。
