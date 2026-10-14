# V1.0 本地验收记录（2026-10-14）

| 项目 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| 官网原有功能测试 | PASS | 原有 20 项测试通过 |
| 独立数据库空库迁移 | PASS | Alembic 在临时 SQLite 空库建表，`alembic check` 无 schema 漂移；交付路由跳过官网 SQLite 初始化 |
| 员工与家长登录 | PASS | 本地虚构账号测试通过；弱密钥配置下模块拒绝开放 |
| 家长项目隔离 | PASS | 未授权项目返回 404；家长访问管理员和员工接口被拒绝 |
| 未公开内容不外泄 | PASS | 未公开任务及内部备注不出现在家长响应中 |
| 任务更新同步 | PASS | 员工完成任务后，家长下一次读取立即看到公开状态 |
| 重复更新 | PASS | 重复「完成」不新增任务变更记录 |
| CSRF | PASS | 缺少有效令牌的 POST 返回 400 |
| 导入预览 | PASS | V1.1、Daniel、V0.2 重叠与冲突数量已核对；未写入真实数据 |
| 导入回滚 | PASS | 虚构工作簿导入、原始状态保留与受保护回滚通过 |
| 本地测试总数 | PASS | 31 项，其中新模块 11 项、原有官网 20 项 |
| 本地备份恢复演练 | PASS | 虚构 SQLite 数据在线备份到独立测试库；用户 3、学生 1、项目 1、任务 4、迁移版本 1 均与源库一致，`integrity_check=ok` |
| GitHub Actions | PASS | 功能分支 run 38541241369：依赖安装、编译、31 项测试、临时 PostgreSQL 迁移及 schema 检查均通过 |
| PostgreSQL 空库迁移 | PASS | GitHub Actions 的临时 PostgreSQL 16 从空库迁移并通过 Alembic schema 检查 |
| 独立 staging PostgreSQL | NOT TESTED | 尚未提供隔离 staging 环境；CI 临时库不等同于 staging |
| 手机浏览器布局 | PASS | 本地 414px 视口下员工、家长页面可浏览且无横向溢出；桌面视口亦无溢出 |
| 微信内置浏览器 | NOT TESTED | 需人工实机检查 |
| 正式 HTTPS / Nginx / Gunicorn | NOT TESTED | 本轮未连接或更改 ECS |
| PostgreSQL 备份恢复 | NOT TESTED | 未建立 staging PostgreSQL；未接触生产数据库 |
| 真实资料导入 | NOT TESTED | 仅完成只读预览；需人工审核和单独授权 |

上述 PASS 是本地功能验收，不表示生产上线批准。当前仍需 PostgreSQL staging、安全验收和备份恢复演练。
