"""Authenticated staff and family views over the same delivery records."""

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from secrets import compare_digest, token_urlsafe

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session as web_session, url_for
from sqlalchemy import func, select
from werkzeug.security import check_password_hash, generate_password_hash

from .models import AdminEvent, AuthEvent, Milestone, ParentAccess, Project, Student, Task, TaskChange, TemplateTask, User
from .storage import close_session, database_url, session as db_session


bp = Blueprint('delivery', __name__, template_folder='../templates')
ROLES = {'admin', 'staff', 'parent'}
SERVICE_TYPES = {'本科', '硕士', '博士', '硕博联申'}
STATUSES = ('未开始', '进行中', '等待学生', '等待家长', '内部审核中', '已完成', '已阻塞', '已取消')
RISK_LEVELS = ('待确认', '绿', '黄', '红')


def security_ready():
    secret = current_app.config.get('SECRET_KEY') or ''
    url = database_url()
    if len(secret) < 32 or secret == 'change-me-in-production' or not url:
        return False
    if os.environ.get('DELIVERY_ENV', '').lower() == 'production':
        return url.startswith('postgresql') and current_app.config.get('SESSION_COOKIE_SECURE') is True
    return True


@bp.before_request
def protect_module():
    if not security_ready():
        return '交付系统尚未配置独立数据库及强密钥。', 503
    g.delivery_user = None
    user_id = web_session.get('delivery_user_id')
    if user_id:
        user = db_session().get(User, user_id)
        if user and user.active:
            g.delivery_user = user
        else:
            web_session.pop('delivery_user_id', None)
    if request.method == 'POST':
        expected = web_session.get('delivery_csrf', '')
        provided = request.form.get('_csrf', '')
        if not expected or not compare_digest(expected, provided):
            abort(400, '表单已过期，请刷新页面后重试。')


@bp.after_request
def security_headers(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; base-uri 'none'"
    return response


@bp.teardown_request
def teardown(_error):
    close_session()


@bp.app_context_processor
def csrf_context():
    def get_token():
        if 'delivery_csrf' not in web_session:
            web_session['delivery_csrf'] = token_urlsafe(32)
        return web_session['delivery_csrf']
    return {'delivery_csrf': get_token}


def require_role(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.delivery_user:
                return redirect(url_for('delivery.login', next=request.path))
            if g.delivery_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorate


def project_or_404(project_id):
    project = db_session().get(Project, project_id)
    if not project:
        abort(404)
    user = g.delivery_user
    if user.role == 'parent':
        access = db_session().scalar(select(ParentAccess).where(
            ParentAccess.user_id == user.id,
            ParentAccess.student_id == project.student_id,
        ))
        if not access:
            abort(404)
    elif user.role == 'staff' and project.manager_id != user.id:
        abort(404)
    return project


def log_auth(username, event):
    db_session().add(AuthEvent(
        username=username[:120], event=event,
        address=(request.remote_addr or '')[:80],
    ))
    db_session().commit()


def audit(action, entity, entity_id, details=None):
    db_session().add(AdminEvent(actor_id=g.delivery_user.id, action=action, entity=entity,
                                entity_id=entity_id, details_json=json.dumps(details or {}, ensure_ascii=False)))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if g.delivery_user:
        return redirect(url_for('delivery.index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()[:120]
        password = request.form.get('password', '')
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=15)
        failures = db_session().scalar(select(func.count()).select_from(AuthEvent).where(
            AuthEvent.username == username, AuthEvent.event == 'login_failure',
            AuthEvent.created_at >= cutoff,
        )) or 0
        user = db_session().scalar(select(User).where(User.username == username))
        if failures >= 10 or not user or not user.active or not check_password_hash(user.password_hash, password):
            log_auth(username, 'login_failure')
            flash('账号或密码不正确，或登录暂不可用。', 'error')
        else:
            web_session.clear()
            web_session['delivery_user_id'] = user.id
            web_session['delivery_csrf'] = token_urlsafe(32)
            log_auth(username, 'login_success')
            return redirect(url_for('delivery.index'))
    return render_template('delivery/login.html')


@bp.post('/logout')
@require_role(*ROLES)
def logout():
    log_auth(g.delivery_user.username, 'logout')
    web_session.clear()
    return redirect(url_for('delivery.login'))


@bp.get('/')
@require_role(*ROLES)
def index():
    user = g.delivery_user
    query = select(Project).order_by(Project.id.desc())
    if user.role == 'staff':
        query = query.where(Project.manager_id == user.id)
    elif user.role == 'parent':
        query = query.join(ParentAccess, ParentAccess.student_id == Project.student_id).where(ParentAccess.user_id == user.id)
    projects = db_session().scalars(query).all()
    return render_template('delivery/index.html', projects=projects)


@bp.get('/projects/<int:project_id>')
@require_role(*ROLES)
def project_detail(project_id):
    project = project_or_404(project_id)
    all_tasks = db_session().scalars(select(Task).where(Task.project_id == project.id).order_by(Task.due_date, Task.id)).all()
    milestones = db_session().scalars(select(Milestone).where(Milestone.project_id == project.id).order_by(Milestone.due_date, Milestone.id)).all()
    if g.delivery_user.role == 'parent':
        tasks = [task for task in all_tasks if task.parent_visible and not task.review_required and task.status != '已取消']
        milestones = [m for m in milestones if m.parent_visible]
        return render_template('delivery/parent_project.html', project=project, tasks=tasks, milestones=milestones)
    changes = db_session().scalars(select(TaskChange).join(Task).where(Task.project_id == project.id).order_by(TaskChange.id.desc()).limit(30)).all()
    return render_template('delivery/staff_project.html', project=project, tasks=all_tasks, milestones=milestones, today=date.today(),
                           changes=changes, statuses=STATUSES, risk_levels=RISK_LEVELS,
                           staff=db_session().scalars(select(User).where(User.role.in_(['admin','staff']), User.active.is_(True))).all())


@bp.post('/projects/<int:project_id>/tasks')
@require_role('admin', 'staff')
def create_task(project_id):
    project = project_or_404(project_id)
    name = request.form.get('name', '').strip()
    if not name or len(name) > 250:
        abort(400)
    task = Task(project_id=project.id, name=name, phase=request.form.get('phase', '').strip()[:120],
                status='未开始', parent_visible=False)
    db_session().add(task)
    db_session().flush()
    db_session().add(TaskChange(task_id=task.id, actor_id=g.delivery_user.id,
                                changes_json=json.dumps({'created': name}, ensure_ascii=False)))
    audit('task_created', 'task', task.id)
    db_session().commit()
    return redirect(url_for('delivery.project_detail', project_id=project.id))


@bp.post('/tasks/<int:task_id>')
@require_role('admin', 'staff')
def update_task(task_id):
    task = db_session().get(Task, task_id)
    if not task:
        abort(404)
    project_or_404(task.project_id)
    action = request.form.get('action', 'update')
    if action == 'complete':
        changes = {'status': '已完成'}
    elif action == 'quick_status':
        status = request.form.get('status', '')
        if status not in STATUSES:
            abort(400)
        changes = {'status': status}
    else:
        status = request.form.get('status', task.status)
        if status not in STATUSES:
            abort(400)
        due_text = request.form.get('due_date', '')
        try:
            due = date.fromisoformat(due_text) if due_text else None
        except ValueError:
            abort(400)
        changes = {'status': status, 'due_date': due,
                   'risk_level': request.form.get('risk_level', task.risk_level),
                   'blocked_reason': request.form.get('blocked_reason', '').strip()[:2000],
                   'public_note': request.form.get('public_note', '').strip()[:2000],
                   'parent_visible': request.form.get('parent_visible') == 'on',
                   'assignee_id': int(request.form['assignee_id']) if request.form.get('assignee_id', '').isdigit() else None}
        if changes['assignee_id']:
            assignee = db_session().get(User, changes['assignee_id'])
            if not assignee or not assignee.active or assignee.role not in {'admin', 'staff'}:
                abort(400)
        if changes['risk_level'] not in RISK_LEVELS:
            abort(400)
    if task.review_required:
        changes['review_required'] = False
    diff = {}
    for key, value in changes.items():
        previous = getattr(task, key)
        if previous != value:
            diff[key] = {'from': str(previous) if previous is not None else None,
                         'to': str(value) if value is not None else None}
            setattr(task, key, value)
    if diff:
        db_session().add(TaskChange(task_id=task.id, actor_id=g.delivery_user.id,
                                    changes_json=json.dumps(diff, ensure_ascii=False)))
        db_session().commit()
    return redirect(url_for('delivery.project_detail', project_id=task.project_id) + f'#task-{task.id}')


@bp.post('/projects/<int:project_id>/match-text')
@require_role('admin', 'staff')
def match_text(project_id):
    project = project_or_404(project_id)
    source = request.form.get('source_text', '')[:4000]
    codes = set(re.findall(r'\b[A-Za-z]{2,4}-\d{1,3}\b', source.upper()))
    tasks = db_session().scalars(select(Task).where(Task.project_id == project.id, Task.source_code.in_(codes))).all() if codes else []
    matches = sorted(tasks, key=lambda task: task.source_code or '')
    suggested = next((item for item in STATUSES if item in source), '')
    return render_template('delivery/match_text.html', project=project, matches=matches,
                           suggested=suggested, statuses=STATUSES)


@bp.post('/projects/<int:project_id>/phase')
@require_role('admin', 'staff')
def update_phase(project_id):
    project = project_or_404(project_id)
    phase = request.form.get('current_phase', '').strip()
    risk = request.form.get('risk_level', project.risk_level)
    if not phase or len(phase) > 120 or risk not in RISK_LEVELS:
        abort(400)
    if project.current_phase != phase or project.risk_level != risk:
        old = project.current_phase
        old_risk = project.risk_level
        project.current_phase = phase
        project.risk_level = risk
        audit('project_updated', 'project', project.id,
              {'phase_from': old, 'phase_to': phase, 'risk_from': old_risk, 'risk_to': risk})
        db_session().commit()
    return redirect(url_for('delivery.project_detail', project_id=project_id))


@bp.post('/projects/<int:project_id>/milestones')
@require_role('admin', 'staff')
def create_milestone(project_id):
    project_or_404(project_id)
    title = request.form.get('title', '').strip()
    if not title or len(title) > 250:
        abort(400)
    due_text = request.form.get('due_date', '')
    try:
        due = date.fromisoformat(due_text) if due_text else None
    except ValueError:
        abort(400)
    milestone = Milestone(project_id=project_id, title=title, due_date=due,
                          parent_visible=request.form.get('parent_visible') == 'on')
    db_session().add(milestone)
    db_session().flush()
    audit('milestone_created', 'milestone', milestone.id)
    db_session().commit()
    return redirect(url_for('delivery.project_detail', project_id=project_id))


@bp.post('/milestones/<int:milestone_id>/complete')
@require_role('admin', 'staff')
def complete_milestone(milestone_id):
    milestone = db_session().get(Milestone, milestone_id)
    if not milestone:
        abort(404)
    project_or_404(milestone.project_id)
    if not milestone.completed_at:
        milestone.completed_at = datetime.now(timezone.utc)
        audit('milestone_completed', 'milestone', milestone.id)
        db_session().commit()
    return redirect(url_for('delivery.project_detail', project_id=milestone.project_id))


@bp.route('/projects/new', methods=['GET', 'POST'])
@require_role('admin')
def new_project():
    if request.method == 'POST':
        name = request.form.get('student_name', '').strip()
        service = request.form.get('service_type', '')
        manager_id = request.form.get('manager_id', '')
        manager = db_session().get(User, int(manager_id)) if manager_id.isdigit() else None
        if not name or len(name) > 120 or service not in SERVICE_TYPES or not manager or not manager.active or manager.role not in {'admin','staff'}:
            abort(400)
        season = request.form.get('intake_year', '').strip()[:32]
        duplicate = db_session().scalar(select(Project).join(Student).where(
            Student.name == name, Project.service_type == service, Project.intake_year == season))
        if duplicate:
            flash('已存在同姓名、服务类型和入学季的项目，请先核对。', 'error')
            return redirect(url_for('delivery.new_project'))
        student = Student(name=name)
        db_session().add(student)
        db_session().flush()
        project = Project(student_id=student.id, service_type=service,
                          intake_year=season, manager_id=manager.id)
        db_session().add(project)
        db_session().flush()
        templates = db_session().scalars(select(TemplateTask).where(
            TemplateTask.service_type == service, TemplateTask.classification == 'standard')).all()
        for item in templates:
            db_session().add(Task(project_id=project.id, source_code=item.source_code,
                                  name=item.name, phase=item.phase, owner_label=item.role_label))
        audit('project_created', 'project', project.id)
        db_session().commit()
        return redirect(url_for('delivery.project_detail', project_id=project.id))
    staff = db_session().scalars(select(User).where(User.role.in_(['admin','staff']), User.active.is_(True))).all()
    return render_template('delivery/new_project.html', staff=staff, service_types=sorted(SERVICE_TYPES))


@bp.route('/users', methods=['GET', 'POST'])
@require_role('admin')
def users():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role', '')
        if not username or len(username) > 120 or len(password) < 12 or role not in ROLES:
            abort(400)
        if db_session().scalar(select(User).where(User.username == username)):
            flash('账号已存在。', 'error')
        else:
            user = User(username=username, password_hash=generate_password_hash(password), role=role)
            db_session().add(user)
            db_session().flush()
            audit('user_created', 'user', user.id, {'role': role})
            db_session().commit()
            flash('账号已创建。', 'success')
        return redirect(url_for('delivery.users'))
    people = db_session().scalars(select(User).order_by(User.id)).all()
    students = db_session().scalars(select(Student).order_by(Student.id)).all()
    accesses = db_session().scalars(select(ParentAccess).order_by(ParentAccess.id)).all()
    return render_template('delivery/users.html', people=people, students=students, accesses=accesses,
                           user_names={item.id: item.username for item in people},
                           student_names={item.id: item.name for item in students})


@bp.post('/users/<int:user_id>/password')
@require_role('admin')
def reset_password(user_id):
    user = db_session().get(User, user_id)
    password = request.form.get('password', '')
    if not user or len(password) < 12:
        abort(400)
    user.password_hash = generate_password_hash(password)
    audit('password_reset', 'user', user.id)
    db_session().commit()
    flash('密码已重置。', 'success')
    return redirect(url_for('delivery.users'))


@bp.post('/users/<int:user_id>/role')
@require_role('admin')
def set_user_role(user_id):
    user = db_session().get(User, user_id)
    role = request.form.get('role', '')
    if not user or user.id == g.delivery_user.id or role not in ROLES:
        abort(400)
    if user.role != role:
        old = user.role
        user.role = role
        if role != 'parent':
            for access in db_session().scalars(select(ParentAccess).where(ParentAccess.user_id == user.id)):
                db_session().delete(access)
        audit('user_role_changed', 'user', user.id, {'from': old, 'to': role})
        db_session().commit()
    return redirect(url_for('delivery.users'))


@bp.post('/users/<int:user_id>/active')
@require_role('admin')
def set_user_active(user_id):
    user = db_session().get(User, user_id)
    if not user or user.id == g.delivery_user.id:
        abort(400)
    active = request.form.get('active') == 'true'
    if user.active != active:
        user.active = active
        audit('user_enabled' if active else 'user_disabled', 'user', user.id)
        db_session().commit()
    return redirect(url_for('delivery.users'))


@bp.post('/parents/access')
@require_role('admin')
def grant_access():
    user_id = request.form.get('user_id', '')
    student_id = request.form.get('student_id', '')
    if not user_id.isdigit() or not student_id.isdigit():
        abort(400)
    user = db_session().get(User, int(user_id))
    student = db_session().get(Student, int(student_id))
    if not user or user.role != 'parent' or not student:
        abort(400)
    existing = db_session().scalar(select(ParentAccess).where(
        ParentAccess.user_id == user.id, ParentAccess.student_id == student.id))
    if not existing:
        db_session().add(ParentAccess(user_id=user.id, student_id=student.id))
        audit('parent_access_granted', 'student', student.id, {'user_id': user.id})
        db_session().commit()
    return redirect(url_for('delivery.users'))


@bp.post('/parents/access/revoke')
@require_role('admin')
def revoke_access():
    access_id = request.form.get('access_id', '')
    access = db_session().get(ParentAccess, int(access_id)) if access_id.isdigit() else None
    if not access:
        abort(404)
    db_session().delete(access)
    audit('parent_access_revoked', 'student', access.student_id, {'user_id': access.user_id})
    db_session().commit()
    return redirect(url_for('delivery.users'))


@bp.post('/projects/<int:project_id>/manager')
@require_role('admin')
def assign_manager(project_id):
    project = project_or_404(project_id)
    user_id = request.form.get('manager_id', '')
    manager = db_session().get(User, int(user_id)) if user_id.isdigit() else None
    if not manager or not manager.active or manager.role not in {'admin', 'staff'}:
        abort(400)
    if project.manager_id != manager.id:
        old = project.manager_id
        project.manager_id = manager.id
        audit('manager_changed', 'project', project.id, {'from': old, 'to': manager.id})
        db_session().commit()
    return redirect(url_for('delivery.project_detail', project_id=project_id))


@bp.get('/templates')
@require_role('admin')
def templates():
    rows = db_session().scalars(select(TemplateTask).order_by(TemplateTask.service_type, TemplateTask.source_code)).all()
    return render_template('delivery/templates.html', rows=rows)


@bp.get('/audit')
@require_role('admin')
def audit_log():
    events = db_session().scalars(select(AdminEvent).order_by(AdminEvent.id.desc()).limit(100)).all()
    auth_events = db_session().scalars(select(AuthEvent).order_by(AuthEvent.id.desc()).limit(100)).all()
    names = {person.id: person.username for person in db_session().scalars(select(User)).all()}
    return render_template('delivery/audit.html', events=events, auth_events=auth_events, names=names)


@bp.post('/templates/<int:template_id>')
@require_role('admin')
def classify_template(template_id):
    row = db_session().get(TemplateTask, template_id)
    if not row:
        abort(404)
    value = request.form.get('classification', '')
    note = request.form.get('condition_note', '').strip()[:1000]
    if value not in {'standard', 'conditional', 'case_specific', 'pending_review'} or (value == 'conditional' and not note):
        abort(400)
    if row.classification != value or row.condition_note != note:
        row.classification = value
        row.condition_note = note
        audit('template_classified', 'template', row.id, {'classification': value})
        db_session().commit()
    return redirect(url_for('delivery.templates') + f'#template-{row.id}')


@bp.get('/progress/<int:project_id>.txt')
@require_role('admin', 'staff')
def progress_text(project_id):
    project = project_or_404(project_id)
    tasks = db_session().scalars(select(Task).where(Task.project_id == project.id, Task.parent_visible.is_(True),
                                             Task.review_required.is_(False), Task.status != '已取消')).all()
    lines = [f'{project.student.name} · {project.service_type}申请进度', f'当前阶段：{project.current_phase or "待确认"}']
    for title, statuses in (
        ('已完成', {'已完成'}), ('正在推进', {'进行中', '内部审核中'}),
        ('需要配合', {'等待学生', '等待家长'}), ('阻塞事项', {'已阻塞'}),
    ):
        matched = [t for t in tasks if t.status in statuses]
        lines.append(f'{title}：' + ('；'.join(t.public_note or t.name for t in matched) if matched else '待确认'))
    return '\n'.join(lines), 200, {'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'private, no-store'}
