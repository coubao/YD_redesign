from flask import Flask, Response, abort, render_template, request, redirect, url_for, flash, send_file

try:
    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy import Integer, String, Float, Text, UniqueConstraint, text as sql_text
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Mapped, mapped_column
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "Missing dependency: flask_sqlalchemy. Run: make init (or pip install -r requirements.txt)"
    ) from exc
import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import json
import os
import hmac
from secrets import token_urlsafe
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from intake_schema import (
    APPLICATION_STAGES,
    INTAKE_FORM_CONFIGS,
    build_intake_docx,
    load_intake_data,
    parse_intake_form,
    validate_intake_data,
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///rankings.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['BOOKING_WECHAT_WEBHOOK_URL'] = os.environ.get('BOOKING_WECHAT_WEBHOOK_URL', '').strip()
app.config['BOOKING_WECHAT_MENTIONED_MOBILES'] = [
    mobile.strip()
    for mobile in os.environ.get('BOOKING_WECHAT_MENTIONED_MOBILES', '').split(',')
    if mobile.strip()
]
app.config['ADMIN_USERNAME'] = os.environ.get('ADMIN_USERNAME', '').strip()
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', '')

db = SQLAlchemy(app)




def render_home_with_fallback(offer_slides, offer_count):
    html = render_template('home.html', offer_slides=offer_slides, offer_count=offer_count)
    if '/* Design System v2 */' in html[:1200]:
        html = render_template('home_safe.html', offer_slides=offer_slides, offer_count=offer_count)
    return html

def get_offer_images():
    offers_dir = Path(app.static_folder) / 'offers'
    image_suffixes = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.jfif'}

    def natural_key(name: str):
        return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', name)]

    offer_images = []
    if offers_dir.exists():
        offer_images = [
            f'offers/{fp.name}'
            for fp in offers_dir.iterdir()
            if fp.is_file() and fp.suffix.lower() in image_suffixes
        ]
        offer_images.sort(key=natural_key)
    return offer_images
class Ranking(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    school_name: Mapped[str] = mapped_column(String(200), nullable=False)
    english_name: Mapped[str] = mapped_column(String(200), default='')
    region: Mapped[str] = mapped_column(String(200), default='')
    qs: Mapped[float] = mapped_column(Float, default=0.0)
    usnews: Mapped[float] = mapped_column(Float, default=0.0)
    the: Mapped[float] = mapped_column(Float, default=0.0)
    arwu: Mapped[float] = mapped_column(Float, default=0.0)
    history_data: Mapped[str] = mapped_column(Text, default='')


class Booking(db.Model):
    __tablename__ = 'booking'
    __table_args__ = (
        UniqueConstraint('booking_date', 'time_slot', name='uq_booking_date_time_slot'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_date: Mapped[str] = mapped_column(String(20), nullable=False)
    time_slot: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact: Mapped[str] = mapped_column(String(160), nullable=False)
    target_country: Mapped[str] = mapped_column(String(120), nullable=False)
    stage: Mapped[str] = mapped_column(String(120), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    meeting_method: Mapped[str] = mapped_column(String(80), default='腾讯会议')
    status: Mapped[str] = mapped_column(String(40), default='pending_intake')
    intake_token: Mapped[str] = mapped_column(String(80), default=lambda: token_urlsafe(24))
    intake_data: Mapped[str] = mapped_column(Text, default='')
    intake_submitted_at: Mapped[str] = mapped_column(String(32), default='')
    notification_status: Mapped[str] = mapped_column(String(40), default='pending')
    notification_sent_at: Mapped[str] = mapped_column(String(32), default='')
    notification_error: Mapped[str] = mapped_column(Text, default='')
    consulted_at: Mapped[str] = mapped_column(String(32), default='')
    created_at: Mapped[str] = mapped_column(String(32), default=lambda: datetime.now().isoformat(timespec='seconds'))


BOOKING_STATUS_PENDING_INTAKE = 'pending_intake'
BOOKING_STATUS_CONFIRMED = 'confirmed'
BOOKING_STATUS_LABELS = {
    BOOKING_STATUS_PENDING_INTAKE: '待填写资料',
    BOOKING_STATUS_CONFIRMED: '已确认',
}
BOOKING_SLOT_DURATION_MINUTES = 60
BOOKING_SLOT_STEP_MINUTES = 60
BOOKING_BUFFER_MINUTES = 30
BOOKING_ADVANCE_DAYS = 30
BOOKING_DAILY_WINDOWS = [
    ('morning', '上午', 10 * 60, 12 * 60),
    ('afternoon', '下午', 14 * 60, 16 * 60),
]
BOOKING_STAGES = APPLICATION_STAGES
WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
CALENDAR_WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日']


def format_booking_minutes(minutes):
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def parse_booking_time(time_text):
    hour, minute = time_text.split(':', 1)
    return int(hour) * 60 + int(minute)


def parse_booking_slot(slot):
    start_text, end_text = slot.split('-', 1)
    return parse_booking_time(start_text), parse_booking_time(end_text)


def build_booking_slot_groups():
    groups = []
    all_slots = []
    for key, label, start, end in BOOKING_DAILY_WINDOWS:
        slots = []
        current = start
        while current + BOOKING_SLOT_DURATION_MINUTES <= end:
            slot = f'{format_booking_minutes(current)}-{format_booking_minutes(current + BOOKING_SLOT_DURATION_MINUTES)}'
            slots.append(slot)
            all_slots.append(slot)
            current += BOOKING_SLOT_STEP_MINUTES
        groups.append({
            'key': key,
            'label': label,
            'window': f'{format_booking_minutes(start)}-{format_booking_minutes(end)}',
            'slots': slots,
        })
    return all_slots, groups


BOOKING_TIME_SLOTS, BOOKING_SLOT_GROUPS = build_booking_slot_groups()


def build_booking_day_item(current):
    return {
        'value': current.isoformat(),
        'label': current.strftime('%m月%d日'),
        'day_number': current.strftime('%d'),
        'month_label': current.strftime('%m月'),
        'weekday': WEEKDAY_LABELS[current.weekday()],
        'is_closed': False,
        'is_today': current == date.today(),
    }


def build_booking_days(days_count=BOOKING_ADVANCE_DAYS):
    start = date.today()
    return [
        build_booking_day_item(start + timedelta(days=offset))
        for offset in range(days_count)
    ]


def recurring_placeholder_name(day_date, slot):
    weekday = day_date.weekday()
    slot_start, _ = parse_booking_slot(slot)
    is_morning = slot_start < 12 * 60
    is_afternoon = slot_start >= 14 * 60

    if weekday == 6:
        return 'XX同学'
    if weekday == 2 and is_afternoon:
        return 'XX同学'
    if weekday == 3 and is_morning:
        return 'XX同学'
    return ''


def build_calendar_months(available_days):
    if not available_days:
        return []

    day_lookup = {item['value']: item for item in available_days}
    first_day = date.fromisoformat(available_days[0]['value'])
    last_day = date.fromisoformat(available_days[-1]['value'])
    current_month = date(first_day.year, first_day.month, 1)
    final_month = date(last_day.year, last_day.month, 1)
    months = []

    while current_month <= final_month:
        if current_month.month == 12:
            next_month = date(current_month.year + 1, 1, 1)
        else:
            next_month = date(current_month.year, current_month.month + 1, 1)

        month_end = next_month - timedelta(days=1)
        grid_start = current_month - timedelta(days=current_month.weekday())
        grid_end = month_end + timedelta(days=6 - month_end.weekday())
        days = []
        cursor = grid_start

        while cursor <= grid_end:
            value = cursor.isoformat()
            source = day_lookup.get(value)
            if source:
                day_item = dict(source)
                day_item['is_in_booking_window'] = True
            else:
                day_item = build_booking_day_item(cursor)
                day_item['available_count'] = 0
                day_item['is_full'] = True
                day_item['is_in_booking_window'] = False
            day_item['is_outside_month'] = cursor.month != current_month.month
            days.append(day_item)
            cursor += timedelta(days=1)

        months.append({
            'title': f'{current_month.year}年{current_month.month}月',
            'days': days,
        })
        current_month = next_month

    return months


def get_booked_slots_by_date(day_values):
    bookings = Booking.query.filter(Booking.booking_date.in_(day_values)).all()
    booked = {}
    for item in bookings:
        booked.setdefault(item.booking_date, []).append(item.time_slot)
    return booked


def booking_slots_conflict(candidate_slot, booked_slot):
    candidate_start, candidate_end = parse_booking_slot(candidate_slot)
    booked_start, booked_end = parse_booking_slot(booked_slot)
    blocked_start = booked_start - BOOKING_BUFFER_MINUTES
    blocked_end = booked_end + BOOKING_BUFFER_MINUTES
    return candidate_start < blocked_end and candidate_end > blocked_start


def build_slot_status_map(day_values):
    booked_map = get_booked_slots_by_date(day_values)
    today_value = date.today().isoformat()
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    status_map = {}

    for day_value in day_values:
        booked_slots = booked_map.get(day_value, [])
        slot_statuses = {}
        for slot in BOOKING_TIME_SLOTS:
            slot_start, _ = parse_booking_slot(slot)
            state = 'available'
            label = '可预约'
            day_date = date.fromisoformat(day_value)
            placeholder_name = recurring_placeholder_name(day_date, slot)

            if placeholder_name:
                state = 'booked'
                label = f'{placeholder_name}已预约'
            elif slot in booked_slots:
                state = 'booked'
                label = '已预约'
            elif day_value < today_value:
                state = 'past'
                label = '已过期'
            elif day_value == today_value and slot_start <= current_minutes:
                state = 'past'
                label = '已过期'
            elif any(booking_slots_conflict(slot, booked_slot) for booked_slot in booked_slots):
                state = 'booked'
                label = 'XX同学已预约'

            slot_statuses[slot] = {
                'state': state,
                'label': label,
                'disabled': state != 'available',
            }
        status_map[day_value] = slot_statuses

    return status_map


def build_booking_context(form_data=None):
    available_days = build_booking_days()
    day_values = [item['value'] for item in available_days]
    slot_status_map = build_slot_status_map(day_values)

    for day_item in available_days:
        statuses = slot_status_map.get(day_item['value'], {})
        available_count = sum(1 for item in statuses.values() if item['state'] == 'available')
        day_item['available_count'] = available_count
        day_item['is_full'] = available_count == 0

    default_date = next(
        (item['value'] for item in available_days if item['available_count'] > 0),
        available_days[0]['value'],
    )
    return {
        'available_days': available_days,
        'calendar_months': build_calendar_months(available_days),
        'calendar_weekdays': CALENDAR_WEEKDAY_LABELS,
        'time_slots': BOOKING_TIME_SLOTS,
        'slot_groups': BOOKING_SLOT_GROUPS,
        'slot_status_map': slot_status_map,
        'default_date': default_date,
        'stages': BOOKING_STAGES,
        'form': form_data or {},
    }


def ensure_booking_token(booking_record):
    if not booking_record.intake_token:
        booking_record.intake_token = token_urlsafe(24)
        db.session.commit()
    return booking_record.intake_token


def render_intake_form(booking_record, intake_data, saved=False, errors=None):
    return render_template(
        'booking_intake.html',
        booking=booking_record,
        intake=intake_data,
        intake_form_configs=INTAKE_FORM_CONFIGS,
        stages=BOOKING_STAGES,
        saved=saved,
        errors=errors or [],
    )


def render_new_booking_form(booking_date, time_slot, form_data=None, intake_data=None, errors=None):
    return render_template(
        'booking_intake.html',
        booking={
            'id': '待生成',
            'booking_date': booking_date,
            'time_slot': time_slot,
            'meeting_method': '腾讯会议',
        },
        booking_form=form_data or {},
        intake=intake_data or {},
        intake_form_configs=INTAKE_FORM_CONFIGS,
        stages=BOOKING_STAGES,
        saved=False,
        errors=errors or [],
        is_new_booking=True,
    )


def save_intake_form(booking_record):
    intake_data = parse_intake_form(request.form)
    errors = validate_intake_data(intake_data)
    if errors:
        return False, intake_data, errors
    booking_record.name = intake_data.get('name', booking_record.name)
    booking_record.contact = intake_data.get('contact', booking_record.contact)
    booking_record.target_country = intake_data.get('target_region', '')
    booking_record.stage = intake_data.get('application_stage', booking_record.stage)
    booking_record.question = intake_data.get('consultation_questions', '')
    booking_record.intake_data = json.dumps(intake_data, ensure_ascii=False)
    booking_record.intake_submitted_at = datetime.now().isoformat(timespec='seconds')
    booking_record.status = BOOKING_STATUS_CONFIRMED
    db.session.commit()
    flash('咨询前信息采集表已提交，预约已确认。', 'success')
    return True, intake_data, []


def build_booking_notification_text(booking_record, intake_data):
    stage = intake_data.get('application_stage') or booking_record.stage
    target_region = intake_data.get('target_region') or '未填写'
    return '\n'.join([
        '【超哥留学 & Grace 新预约提醒】',
        f'预约编号：#{booking_record.id}',
        f'学生姓名：{booking_record.name}',
        f'申请阶段：{stage}',
        f'咨询时间：{booking_record.booking_date} {booking_record.time_slot}',
        f'咨询方式：{booking_record.meeting_method}',
        f'目标国家/地区：{target_region}',
        f'客户联系方式：{booking_record.contact}',
        '请登录预约管理后台查看完整资料。',
        '提醒对象：超哥留学负责人 / Grace',
    ])


def send_booking_wechat_notification(booking_record, intake_data):
    webhook_url = app.config.get('BOOKING_WECHAT_WEBHOOK_URL', '')
    if not webhook_url:
        booking_record.notification_status = 'not_configured'
        booking_record.notification_error = 'BOOKING_WECHAT_WEBHOOK_URL 未配置'
        db.session.commit()
        app.logger.warning('Booking #%s saved; WeChat webhook is not configured.', booking_record.id)
        return False

    payload = {
        'msgtype': 'text',
        'text': {
            'content': build_booking_notification_text(booking_record, intake_data),
            'mentioned_mobile_list': app.config.get('BOOKING_WECHAT_MENTIONED_MOBILES', []),
        },
    }
    request_data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    webhook_request = Request(
        webhook_url,
        data=request_data,
        headers={'Content-Type': 'application/json; charset=utf-8'},
        method='POST',
    )

    try:
        with urlopen(webhook_request, timeout=8) as response:
            response_data = json.loads(response.read().decode('utf-8') or '{}')
        if response_data.get('errcode', 0) != 0:
            raise ValueError(response_data.get('errmsg') or f'微信接口错误：{response_data}')
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        booking_record.notification_status = 'failed'
        booking_record.notification_error = str(exc)[:1000]
        db.session.commit()
        app.logger.exception('Booking #%s WeChat notification failed.', booking_record.id)
        return False

    booking_record.notification_status = 'sent'
    booking_record.notification_sent_at = datetime.now().isoformat(timespec='seconds')
    booking_record.notification_error = ''
    db.session.commit()
    return True


def migrate_july_15_bookings_to_july_16(booking_cols):
    if not {'booking_date', 'time_slot'}.issubset(booking_cols):
        return

    migration_key = 'move_2026_07_15_bookings_to_2026_07_16'
    db.session.execute(sql_text(
        "CREATE TABLE IF NOT EXISTS app_migration (migration_key VARCHAR(100) PRIMARY KEY, applied_at VARCHAR(32))"
    ))
    existing = db.session.execute(
        sql_text("SELECT migration_key FROM app_migration WHERE migration_key = :migration_key"),
        {'migration_key': migration_key},
    ).first()
    if existing:
        return

    db.session.execute(sql_text(
        """
        UPDATE booking
        SET booking_date = '2026-07-16'
        WHERE booking_date = '2026-07-15'
          AND NOT EXISTS (
            SELECT 1
            FROM booking AS existing
            WHERE existing.booking_date = '2026-07-16'
              AND existing.time_slot = booking.time_slot
          )
        """
    ))
    db.session.execute(
        sql_text("INSERT INTO app_migration (migration_key, applied_at) VALUES (:migration_key, :applied_at)"),
        {'migration_key': migration_key, 'applied_at': datetime.now().isoformat(timespec='seconds')},
    )


def ensure_ranking_schema():
    # Lightweight SQLite schema patching for users upgrading from older columns
    db.create_all()
    cols = {row[1] for row in db.session.execute(sql_text("PRAGMA table_info(ranking)")).fetchall()}

    ddl = []
    if cols and 'school_name' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN school_name VARCHAR(200) DEFAULT ''")
    if cols and 'english_name' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN english_name VARCHAR(200) DEFAULT ''")
    if cols and 'region' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN region VARCHAR(200) DEFAULT ''")
    if cols and 'qs' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN qs FLOAT DEFAULT 0")
    if cols and 'usnews' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN usnews FLOAT DEFAULT 0")
    if cols and 'the' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN the FLOAT DEFAULT 0")
    if cols and 'arwu' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN arwu FLOAT DEFAULT 0")
    if cols and 'history_data' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN history_data TEXT DEFAULT ''")

    for stmt in ddl:
        db.session.execute(sql_text(stmt))

    # Backfill school_name from old column if present and new column empty
    if cols and 'school' in cols:
        db.session.execute(sql_text("UPDATE ranking SET school_name = school WHERE (school_name IS NULL OR school_name = '') AND school IS NOT NULL"))
    if cols and 'location' in cols:
        db.session.execute(sql_text("UPDATE ranking SET region = location WHERE (region IS NULL OR region = '') AND location IS NOT NULL"))

    booking_cols = {row[1] for row in db.session.execute(sql_text("PRAGMA table_info(booking)")).fetchall()}
    booking_ddl = []
    if booking_cols and 'intake_token' not in booking_cols:
        booking_ddl.append("ALTER TABLE booking ADD COLUMN intake_token VARCHAR(80) DEFAULT ''")
    if booking_cols and 'intake_data' not in booking_cols:
        booking_ddl.append("ALTER TABLE booking ADD COLUMN intake_data TEXT DEFAULT ''")
    if booking_cols and 'intake_submitted_at' not in booking_cols:
        booking_ddl.append("ALTER TABLE booking ADD COLUMN intake_submitted_at VARCHAR(32) DEFAULT ''")
    if booking_cols and 'notification_status' not in booking_cols:
        booking_ddl.append("ALTER TABLE booking ADD COLUMN notification_status VARCHAR(40) DEFAULT 'pending'")
    if booking_cols and 'notification_sent_at' not in booking_cols:
        booking_ddl.append("ALTER TABLE booking ADD COLUMN notification_sent_at VARCHAR(32) DEFAULT ''")
    if booking_cols and 'notification_error' not in booking_cols:
        booking_ddl.append("ALTER TABLE booking ADD COLUMN notification_error TEXT DEFAULT ''")
    if booking_cols and 'consulted_at' not in booking_cols:
        booking_ddl.append("ALTER TABLE booking ADD COLUMN consulted_at VARCHAR(32) DEFAULT ''")
    for stmt in booking_ddl:
        db.session.execute(sql_text(stmt))

    refreshed_booking_cols = {row[1] for row in db.session.execute(sql_text("PRAGMA table_info(booking)")).fetchall()}
    if 'status' in refreshed_booking_cols:
        if 'intake_submitted_at' in refreshed_booking_cols:
            db.session.execute(sql_text(
                "UPDATE booking SET status = 'confirmed' "
                "WHERE intake_submitted_at IS NOT NULL AND intake_submitted_at != '' "
                "AND (status IS NULL OR status = '' OR status = 'pending' OR status = 'pending_intake')"
            ))
        db.session.execute(sql_text(
            "UPDATE booking SET status = 'pending_intake' "
            "WHERE status IS NULL OR status = '' OR status = 'pending'"
        ))
    migrate_july_15_bookings_to_july_16(refreshed_booking_cols)
    db.session.commit()

@app.before_request
def protect_admin_routes():
    if not request.path.startswith('/admin'):
        return None

    admin_username = app.config.get('ADMIN_USERNAME', '')
    admin_password = app.config.get('ADMIN_PASSWORD', '')
    if not admin_username or not admin_password:
        return Response(
            '后台访问凭据尚未配置。请设置 ADMIN_USERNAME 和 ADMIN_PASSWORD。',
            status=503,
            content_type='text/plain; charset=utf-8',
        )

    auth = request.authorization
    username_matches = bool(auth) and hmac.compare_digest(auth.username or '', admin_username)
    password_matches = bool(auth) and hmac.compare_digest(auth.password or '', admin_password)
    if username_matches and password_matches:
        return None

    return Response(
        '需要后台登录。',
        status=401,
        headers={'WWW-Authenticate': 'Basic realm="YD Education Admin", charset="UTF-8"'},
        content_type='text/plain; charset=utf-8',
    )


@app.before_request
def init_db_once():
    ensure_ranking_schema()

@app.get('/')
def home():
    offer_images = get_offer_images()
    slides = [offer_images[i:i + 6] for i in range(0, len(offer_images), 6)]
    return render_home_with_fallback(slides, len(offer_images))


@app.get('/debug/render-home')
def debug_render_home():
    offer_images = get_offer_images()
    slides = [offer_images[i:i + 6] for i in range(0, len(offer_images), 6)]
    html = render_home_with_fallback(slides, len(offer_images))
    marker = '/* Design System v2 */'
    idx = html.find(marker)
    return {
        'has_css_dump_marker': idx != -1,
        'marker_index': idx,
        'html_preview_head': html[:500],
        'html_preview_tail': html[-500:],
    }

@app.get('/ranking')
def index():
    school_name = request.args.get('school_name', '').strip()
    english_name = request.args.get('english_name', '').strip()
    region = request.args.get('region', '').strip()

    query = Ranking.query
    if school_name:
        query = query.filter(Ranking.school_name.ilike(f'%{school_name}%'))
    if english_name:
        query = query.filter(Ranking.english_name.ilike(f'%{english_name}%'))
    if region:
        query = query.filter(Ranking.region.ilike(f'%{region}%'))

    rankings = query.order_by(Ranking.rank.asc()).all()
    return render_template('index.html', rankings=rankings, school_name=school_name, english_name=english_name, region=region)


@app.get('/guide')
def guide():
    return render_template('guide.html')

@app.get('/services')
def services():
    return render_template('services.html')

@app.get('/contact')
def contact_page():
    return render_template('contact.html')

def validate_booking_selection(booking_date, time_slot):
    available_days = build_booking_days()
    allowed_dates = {item['value'] for item in available_days}
    errors = []

    if booking_date not in allowed_dates:
        errors.append('请选择可预约日期。')
    if time_slot not in BOOKING_TIME_SLOTS:
        errors.append('请选择可预约时间段。')
    elif booking_date in allowed_dates:
        slot_status = build_slot_status_map([booking_date]).get(booking_date, {}).get(time_slot)
        if not slot_status or slot_status['state'] != 'available':
            errors.append('该时间段暂不可预约，请选择绿色可预约时段。')
    return errors


@app.get('/booking')
def booking():
    context = build_booking_context()
    return render_template('booking.html', **context)


@app.route('/booking/details', methods=['GET', 'POST'])
def booking_details():
    if request.method == 'GET':
        booking_date = request.args.get('booking_date', '').strip()
        time_slot = request.args.get('time_slot', '').strip()
        errors = validate_booking_selection(booking_date, time_slot)
        if errors:
            context = build_booking_context({'booking_date': booking_date, 'time_slot': time_slot})
            return render_template('booking.html', errors=errors, **context), 400
        return render_new_booking_form(booking_date, time_slot)

    form_data = {
        'booking_date': request.form.get('booking_date', '').strip(),
        'time_slot': request.form.get('time_slot', '').strip(),
        'stage': request.form.get('stage', '').strip(),
    }
    errors = validate_booking_selection(form_data['booking_date'], form_data['time_slot'])
    intake_data = parse_intake_form(request.form)
    errors.extend(validate_intake_data(intake_data))

    if not errors and Booking.query.filter_by(
        booking_date=form_data['booking_date'],
        time_slot=form_data['time_slot'],
    ).first():
        errors.append('该时间段刚刚被预约，请选择其他时间。')

    if errors:
        return render_new_booking_form(
            form_data['booking_date'],
            form_data['time_slot'],
            form_data=form_data,
            intake_data=intake_data,
            errors=errors,
        ), 400

    booking_record = Booking(
        booking_date=form_data['booking_date'],
        time_slot=form_data['time_slot'],
        name=intake_data.get('name', ''),
        contact=intake_data.get('contact', ''),
        target_country=intake_data.get('target_region', ''),
        stage=intake_data.get('application_stage', ''),
        question=intake_data.get('consultation_questions', ''),
        meeting_method='腾讯会议',
        status=BOOKING_STATUS_CONFIRMED,
        intake_data=json.dumps(intake_data, ensure_ascii=False),
        intake_submitted_at=datetime.now().isoformat(timespec='seconds'),
    )
    try:
        db.session.add(booking_record)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return render_new_booking_form(
            form_data['booking_date'],
            form_data['time_slot'],
            form_data=form_data,
            intake_data=intake_data,
            errors=['该时间段刚刚被预约，请返回重新选择其他时间。'],
        ), 409

    send_booking_wechat_notification(booking_record, intake_data)
    return redirect(url_for('booking_confirmed', booking_id=booking_record.id, token=ensure_booking_token(booking_record)))


@app.get('/consultation')
def consultation():
    return redirect(url_for('booking'))


@app.get('/booking/success/<int:booking_id>')
def booking_success_legacy(booking_id):
    abort(404)


@app.get('/booking/success/<int:booking_id>/<token>')
def booking_success(booking_id, token):
    booking_record = Booking.query.get_or_404(booking_id)
    if not booking_record.intake_token or token != booking_record.intake_token:
        abort(404)
    if booking_record.status == BOOKING_STATUS_CONFIRMED:
        return redirect(url_for('booking_confirmed', booking_id=booking_record.id, token=booking_record.intake_token))
    return render_template('booking_success.html', booking=booking_record)


@app.route('/booking/<int:booking_id>/intake/<token>', methods=['GET', 'POST'])
def booking_intake(booking_id, token):
    booking_record = Booking.query.get_or_404(booking_id)
    if not booking_record.intake_token or token != booking_record.intake_token:
        abort(404)
    intake_data = load_intake_data(booking_record.intake_data)

    if request.method == 'POST':
        was_confirmed = booking_record.status == BOOKING_STATUS_CONFIRMED
        is_valid, intake_data, errors = save_intake_form(booking_record)
        if not is_valid:
            return render_intake_form(booking_record, intake_data, errors=errors), 400
        if not was_confirmed:
            send_booking_wechat_notification(booking_record, intake_data)
        return redirect(url_for('booking_confirmed', booking_id=booking_record.id, token=booking_record.intake_token))

    return render_intake_form(booking_record, intake_data, request.args.get('saved') == '1')


@app.get('/booking/<int:booking_id>/confirmed/<token>')
def booking_confirmed(booking_id, token):
    booking_record = Booking.query.get_or_404(booking_id)
    if not booking_record.intake_token or token != booking_record.intake_token:
        abort(404)
    if booking_record.status != BOOKING_STATUS_CONFIRMED:
        return redirect(url_for('booking_intake', booking_id=booking_record.id, token=booking_record.intake_token))
    return render_template('booking_confirmed.html', booking=booking_record)


@app.route('/admin/bookings/<int:booking_id>/intake', methods=['GET', 'POST'])
def admin_booking_intake(booking_id):
    booking_record = Booking.query.get_or_404(booking_id)
    ensure_booking_token(booking_record)
    intake_data = load_intake_data(booking_record.intake_data)

    if request.method == 'POST':
        is_valid, intake_data, errors = save_intake_form(booking_record)
        if not is_valid:
            return render_intake_form(booking_record, intake_data, errors=errors), 400
        return redirect(url_for('admin_booking_intake', booking_id=booking_record.id, saved=1))

    return render_intake_form(booking_record, intake_data, request.args.get('saved') == '1')

@app.get('/offers')
def offers():
    return redirect(url_for('home') + '#offers-wall')


@app.get('/us-map')
def us_map():
    data_path = Path(app.static_folder) / 'data' / 'us_states_universities.json'
    state_cards = []
    if data_path.exists():
        state_cards = json.loads(data_path.read_text(encoding='utf-8')).get('states', [])
    return render_template('us_map.html', state_cards=state_cards)


def load_study_maps():
    data_path = Path(app.static_folder) / 'data' / 'study_maps.json'
    if not data_path.exists():
        return []
    return json.loads(data_path.read_text(encoding='utf-8')).get('maps', [])


@app.get('/study-maps')
def study_maps_index():
    maps = load_study_maps()
    return render_template('maps_index.html', maps=maps)


@app.get('/study-map/<slug>')
def study_map(slug: str):
    maps = load_study_maps()
    target = next((m for m in maps if m.get('slug') == slug), None)
    if not target:
        flash('未找到该留学地图', 'warning')
        return redirect(url_for('study_maps_index'))
    return render_template('study_map.html', map_data=target)

@app.get('/admin')
def admin():
    rankings = Ranking.query.order_by(Ranking.rank.asc()).all()
    total = len(rankings)
    avg_score = round(sum(r.qs for r in rankings) / total, 1) if total else 0
    total_locations = len({r.region for r in rankings if r.region})
    return render_template('admin.html', rankings=rankings, total=total, avg_score=avg_score, total_locations=total_locations)


@app.get('/admin/bookings')
def admin_bookings():
    bookings = Booking.query.order_by(Booking.booking_date.desc(), Booking.time_slot.desc(), Booking.id.desc()).all()
    total = len(bookings)
    confirmed_count = sum(1 for booking_record in bookings if booking_record.status == BOOKING_STATUS_CONFIRMED)
    pending_intake_count = sum(1 for booking_record in bookings if booking_record.status != BOOKING_STATUS_CONFIRMED)
    consulted_count = sum(1 for booking_record in bookings if booking_record.consulted_at)
    upcoming_count = sum(1 for booking_record in bookings if booking_record.booking_date >= date.today().isoformat())
    return render_template(
        'admin_bookings.html',
        bookings=bookings,
        total=total,
        confirmed_count=confirmed_count,
        pending_intake_count=pending_intake_count,
        consulted_count=consulted_count,
        upcoming_count=upcoming_count,
        status_labels=BOOKING_STATUS_LABELS,
        status_confirmed=BOOKING_STATUS_CONFIRMED,
    )


@app.post('/admin/bookings/<int:booking_id>/consulted')
def toggle_booking_consulted(booking_id):
    booking_record = Booking.query.get_or_404(booking_id)
    if request.form.get('action') == 'clear':
        booking_record.consulted_at = ''
    else:
        booking_record.consulted_at = datetime.now().isoformat(timespec='seconds')
    db.session.commit()
    return redirect(url_for('admin_bookings'))


@app.get('/admin/bookings/<int:booking_id>/download-intake')
def download_booking_intake(booking_id):
    booking_record = Booking.query.get_or_404(booking_id)
    intake_data = load_intake_data(booking_record.intake_data)
    docx_buffer = build_intake_docx(booking_record, intake_data)
    safe_name = re.sub(r'[^\w\u4e00-\u9fff-]+', '_', booking_record.name).strip('_') or f'booking_{booking_record.id}'
    return send_file(
        docx_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        as_attachment=True,
        download_name=f'咨询前信息采集表_{safe_name}_{booking_record.booking_date}.docx',
    )



def to_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def to_float(value, default=0.0):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default
@app.post('/admin/add')
def add_ranking():
    row = Ranking(
        rank=to_int(request.form.get('rank', 0)),
        school_name=request.form.get('school_name', '').strip(),
        english_name=request.form.get('english_name', '').strip(),
        region=request.form.get('region', '').strip(),
        qs=to_float(request.form.get('qs', 0), 0),
        usnews=to_float(request.form.get('usnews', 0), 0),
        the=to_float(request.form.get('the', 0), 0),
        arwu=to_float(request.form.get('arwu', 0), 0),
        history_data=request.form.get('history_data', '').strip(),
    )
    if not row.school_name or row.rank <= 0:
        flash('Rank 和 School 为必填项', 'danger')
        return redirect(url_for('admin'))

    try:
        db.session.add(row)
        db.session.commit()
        flash('新增成功', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'新增失败: {exc}', 'danger')
    return redirect(url_for('admin'))

@app.post('/admin/update/<int:row_id>')
def update_ranking(row_id: int):
    row = Ranking.query.get_or_404(row_id)
    row.rank = to_int(request.form.get('rank', row.rank), row.rank)
    row.school_name = request.form.get('school_name', row.school_name).strip()
    row.english_name = request.form.get('english_name', row.english_name).strip()
    row.region = request.form.get('region', row.region).strip()
    row.qs = to_float(request.form.get('qs', row.qs), row.qs)
    row.usnews = to_float(request.form.get('usnews', row.usnews), row.usnews)
    row.the = to_float(request.form.get('the', row.the), row.the)
    row.arwu = to_float(request.form.get('arwu', row.arwu), row.arwu)
    row.history_data = request.form.get('history_data', row.history_data).strip()

    try:
        db.session.commit()
        flash('更新成功', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'更新失败: {exc}', 'danger')
    return redirect(url_for('admin'))

@app.post('/admin/delete/<int:row_id>')
def delete_ranking(row_id: int):
    row = Ranking.query.get_or_404(row_id)
    db.session.delete(row)
    db.session.commit()
    flash('删除成功', 'success')
    return redirect(url_for('admin'))

@app.post('/admin/upload-csv')
def upload_csv():
    f = request.files.get('csv_file')
    if not f:
        flash('请上传CSV文件', 'danger')
        return redirect(url_for('admin'))

    data = io.StringIO(f.stream.read().decode('utf-8-sig'))
    reader = csv.DictReader(data)

    Ranking.query.delete()
    count = 0
    for r in reader:
        try:
            row = Ranking(
                rank=int(r.get('rank', 0)),
                school_name=(r.get('school_name') or '').strip(),
                english_name=(r.get('english_name') or '').strip(),
                region=(r.get('region') or '').strip(),
                qs=float(r.get('qs', 0) or 0),
                usnews=float(r.get('usnews', 0) or 0),
                the=float(r.get('the', 0) or 0),
                arwu=float(r.get('arwu', 0) or 0),
                history_data=(r.get('history_data') or '').strip(),
            )
            if row.rank > 0 and row.school_name:
                db.session.add(row)
                count += 1
        except Exception:
            continue
    db.session.commit()
    flash(f'CSV 导入完成，共 {count} 条记录', 'success')
    return redirect(url_for('admin'))

@app.get('/admin/template.csv')
def download_template():
    sample = 'rank,school_name,english_name,region,qs,usnews,the,arwu,history_data\n1,示例大学,Sample University,美国,98.2,92.5,88.0,85.5,2023:95|2024:97|2025:98\n'
    return send_file(
        io.BytesIO(sample.encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='ranking_template.csv'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
