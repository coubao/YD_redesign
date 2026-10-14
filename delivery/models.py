from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'delivery_user'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Student(Base):
    __tablename__ = 'delivery_student'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    external_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('delivery_import_batch.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ParentAccess(Base):
    __tablename__ = 'delivery_parent_access'
    __table_args__ = (UniqueConstraint('user_id', 'student_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('delivery_user.id', ondelete='CASCADE'))
    student_id: Mapped[int] = mapped_column(ForeignKey('delivery_student.id', ondelete='CASCADE'))


class Project(Base):
    __tablename__ = 'delivery_project'
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('delivery_student.id'))
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('delivery_import_batch.id'))
    service_type: Mapped[str] = mapped_column(String(32), nullable=False)
    intake_year: Mapped[str] = mapped_column(String(32), default='')
    current_phase: Mapped[str] = mapped_column(String(120), default='待确认')
    risk_level: Mapped[str] = mapped_column(String(24), default='待确认')
    manager_id: Mapped[int | None] = mapped_column(ForeignKey('delivery_user.id'))
    status: Mapped[str] = mapped_column(String(32), default='active')
    source_status: Mapped[str] = mapped_column(String(40), default='')
    source_file: Mapped[str] = mapped_column(String(250), default='')
    source_sheet: Mapped[str] = mapped_column(String(120), default='')
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_payload: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    student: Mapped[Student] = relationship()
    manager: Mapped[User | None] = relationship()


class TemplateTask(Base):
    __tablename__ = 'delivery_template_task'
    __table_args__ = (UniqueConstraint('service_type', 'source_code'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    service_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    phase: Mapped[str] = mapped_column(String(120), default='')
    role_label: Mapped[str] = mapped_column(String(120), default='')
    classification: Mapped[str] = mapped_column(String(24), default='pending_review')
    condition_note: Mapped[str] = mapped_column(Text, default='')
    source_file: Mapped[str] = mapped_column(String(250), default='')
    source_sheet: Mapped[str] = mapped_column(String(120), default='')
    source_row: Mapped[int | None] = mapped_column(Integer)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('delivery_import_batch.id'))


class Task(Base):
    __tablename__ = 'delivery_task'
    __table_args__ = (UniqueConstraint('project_id', 'source_code'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('delivery_project.id', ondelete='CASCADE'))
    source_code: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    phase: Mapped[str] = mapped_column(String(120), default='')
    owner_label: Mapped[str] = mapped_column(String(120), default='')
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey('delivery_user.id'))
    status: Mapped[str] = mapped_column(String(24), default='未开始')
    source_status: Mapped[str] = mapped_column(String(24), default='')
    review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(24), default='待确认')
    due_date: Mapped[date | None] = mapped_column(Date)
    parent_visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    public_note: Mapped[str] = mapped_column(Text, default='')
    internal_note: Mapped[str] = mapped_column(Text, default='')
    blocked_reason: Mapped[str] = mapped_column(Text, default='')
    source_file: Mapped[str] = mapped_column(String(250), default='')
    source_sheet: Mapped[str] = mapped_column(String(120), default='')
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_payload: Mapped[str] = mapped_column(Text, default='')
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('delivery_import_batch.id'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    project: Mapped[Project] = relationship()
    assignee: Mapped[User | None] = relationship()


class Milestone(Base):
    __tablename__ = 'delivery_milestone'
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('delivery_project.id', ondelete='CASCADE'))
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class TaskChange(Base):
    __tablename__ = 'delivery_task_change'
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('delivery_task.id', ondelete='CASCADE'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('delivery_user.id'))
    changes_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    actor: Mapped[User] = relationship()


class AttachmentMeta(Base):
    __tablename__ = 'delivery_attachment_meta'
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('delivery_task.id', ondelete='CASCADE'))
    label: Mapped[str] = mapped_column(String(250), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ImportBatch(Base):
    __tablename__ = 'delivery_import_batch'
    id: Mapped[int] = mapped_column(primary_key=True)
    source_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_file: Mapped[str] = mapped_column(String(250), nullable=False)
    student_count: Mapped[int] = mapped_column(Integer, nullable=False)
    task_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuthEvent(Base):
    __tablename__ = 'delivery_auth_event'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    address: Mapped[str] = mapped_column(String(80), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AdminEvent(Base):
    __tablename__ = 'delivery_admin_event'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('delivery_user.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
