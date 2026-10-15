# 独立数据库备份与恢复

## PostgreSQL staging / production

交付库与官网预约 SQLite 分开备份。使用独立数据库账号，并确保备份文件仅备份管理员可读取，不能进入网站静态目录或 Git 仓库。

```bash
pg_dump --format=custom --no-owner --file=/secure-backups/delivery-$(date +%F).dump "$DELIVERY_PG_DSN"
```

恢复演练只能使用全新测试数据库，不得覆盖生产库：

```bash
createdb delivery_restore_check
pg_restore --no-owner --dbname=delivery_restore_check /secure-backups/delivery-YYYY-MM-DD.dump
psql delivery_restore_check -c "SELECT version_num FROM alembic_version"
psql delivery_restore_check -c "SELECT COUNT(*) FROM delivery_task"
```

`DELIVERY_PG_DSN` 使用 libpq 接受的 `postgresql://...` 格式，而应用的 `DELIVERY_DATABASE_URL` 使用 SQLAlchemy 的 `postgresql+psycopg2://...` 格式。对比源库与恢复库的表数量、关键实体行数和 `alembic_version`；再用虚构账号验证登录与项目读取。演练后销毁测试数据库，并记录演练日期、操作人和结果。生产备份应定期执行，至少保留一份异地副本并定期测试恢复。连接串可能含密码，避免写入 shell history 或日志；实际命令应从受限环境文件读取。

## 本地 SQLite

本地开发库可用 SQLite 在线备份 API 或停机后复制数据库文件。不要直接复制正在写入的 SQLite 文件。官网 `instance/rankings.db` 不属于交付系统备份范围。

本轮已用虚构数据执行 SQLite 在线备份及独立测试库恢复：源库与恢复库的用户、学生、项目、任务、迁移版本数量一致，SQLite `integrity_check` 为 `ok`。尚未执行 PostgreSQL 备份恢复，因为本机没有 PostgreSQL 服务，且没有获授权的 staging 目标。
