from flask import Flask, abort, render_template, request, redirect, url_for, flash, send_file

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
from secrets import token_urlsafe
from intake_schema import (
    ACADEMIC_RECORD_FIELDS,
    ACTIVITY_CATEGORIES,
    ACTIVITY_FIELDS,
    INTAKE_SECTIONS,
    MATERIAL_OPTIONS,
    TESTING_RECORD_FIELDS,
    build_intake_docx,
    load_intake_data,
    parse_intake_form,
    validate_intake_data,
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rankings.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    created_at: Mapped[str] = mapped_column(String(32), default=lambda: datetime.now().isoformat(timespec='seconds'))


BOOKING_STATUS_PENDING_INTAKE = 'pending_intake'
BOOKING_STATUS_CONFIRMED = 'confirmed'
BOOKING_STATUS_LABELS = {
    BOOKING_STATUS_PENDING_INTAKE: '待填写资料',
    BOOKING_STATUS_CONFIRMED: '已确认',
}
BOOKING_SLOT_DURATION_MINUTES = 120
BOOKING_SLOT_STEP_MINUTES = 120
BOOKING_BUFFER_MINUTES = 0
BOOKING_DAILY_WINDOWS = [
    ('morning', '上午', 10 * 60, 12 * 60),
    ('afternoon', '下午', 14 * 60, 16 * 60),
]

BOOKING_TARGET_COUNTRIES = ['美国', '英国', '加拿大', '澳大利亚', '新加坡&香港', '多国联申', '暂未确定']
BOOKING_STAGES = ['低龄申请', '本科申请', '硕士申请', '博士申请', '转学/转专业', '背景提升规划', '其他']
WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


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


def build_booking_days(days_count=14):
    start = date.today()
    days = []
    offset = 0
    while len(days) < days_count:
        current = start + timedelta(days=offset)
        offset += 1
        if current.weekday() == 6:
            continue
        days.append({
            'value': current.isoformat(),
            'label': current.strftime('%m月%d日'),
            'day_number': current.strftime('%d'),
            'month_label': current.strftime('%m月'),
            'weekday': WEEKDAY_LABELS[current.weekday()],
            'is_today': current == date.today(),
        })
    return days


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

            if slot in booked_slots:
                state = 'booked'
                label = '已预约'
            elif day_value == today_value and slot_start <= current_minutes:
                state = 'past'
                label = '已过期'
            elif any(booking_slots_conflict(slot, booked_slot) for booked_slot in booked_slots):
                state = 'booked'
                label = '已预约'

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

    default_date = next((item['value'] for item in available_days if item['available_count'] > 0), available_days[0]['value'])
    return {
        'available_days': available_days,
        'time_slots': BOOKING_TIME_SLOTS,
        'slot_groups': BOOKING_SLOT_GROUPS,
        'slot_status_map': slot_status_map,
        'default_date': default_date,
        'target_countries': BOOKING_TARGET_COUNTRIES,
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
        intake_sections=INTAKE_SECTIONS,
        academic_record_fields=ACADEMIC_RECORD_FIELDS,
        testing_record_fields=TESTING_RECORD_FIELDS,
        activity_categories=ACTIVITY_CATEGORIES,
        activity_fields=ACTIVITY_FIELDS,
        material_options=MATERIAL_OPTIONS,
        saved=saved,
        errors=errors or [],
    )


def save_intake_form(booking_record):
    intake_data = parse_intake_form(request.form)
    errors = validate_intake_data(intake_data)
    if errors:
        return False, intake_data, errors
    booking_record.intake_data = json.dumps(intake_data, ensure_ascii=False)
    booking_record.intake_submitted_at = datetime.now().isoformat(timespec='seconds')
    booking_record.status = BOOKING_STATUS_CONFIRMED
    db.session.commit()
    flash('咨询前信息采集表已提交，预约已确认。', 'success')
    return True, intake_data, []



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
    db.session.commit()

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

@app.route('/booking', methods=['GET', 'POST'])
def booking():
    context = build_booking_context()

    if request.method == 'GET':
        return render_template('booking.html', **context)

    form_data = {
        'booking_date': request.form.get('booking_date', '').strip(),
        'time_slot': request.form.get('time_slot', '').strip(),
        'name': request.form.get('name', '').strip(),
        'contact': request.form.get('contact', '').strip(),
        'target_country': request.form.get('target_country', '').strip(),
        'stage': request.form.get('stage', '').strip(),
        'question': request.form.get('question', '').strip(),
    }
    available_days = build_booking_days()
    allowed_dates = {item['value'] for item in available_days}
    errors = []

    if form_data['booking_date'] not in allowed_dates:
        errors.append('请选择可预约日期。')
    if form_data['time_slot'] not in BOOKING_TIME_SLOTS:
        errors.append('请选择可预约时间段。')
    elif form_data['booking_date'] in allowed_dates:
        slot_status = build_slot_status_map([form_data['booking_date']]).get(form_data['booking_date'], {}).get(form_data['time_slot'])
        if not slot_status or slot_status['state'] != 'available':
            errors.append('该时间段暂不可预约，请选择绿色可预约时段。')
    for field, label in [
        ('name', '姓名'),
        ('contact', '联系方式'),
        ('target_country', '目标国家'),
        ('stage', '申请阶段'),
        ('question', '咨询问题'),
    ]:
        if not form_data[field]:
            errors.append(f'请填写{label}。')

    if not errors and Booking.query.filter_by(
        booking_date=form_data['booking_date'],
        time_slot=form_data['time_slot'],
    ).first():
        errors.append('该时间段刚刚被预约，请选择其他时间。')

    if errors:
        context = build_booking_context(form_data)
        return render_template('booking.html', errors=errors, **context), 400

    booking_record = Booking(**form_data, meeting_method='腾讯会议', status=BOOKING_STATUS_PENDING_INTAKE)
    try:
        db.session.add(booking_record)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        context = build_booking_context(form_data)
        return render_template('booking.html', errors=['该时间段刚刚被预约，请选择其他时间。'], **context), 409

    return redirect(url_for('booking_success', booking_id=booking_record.id, token=ensure_booking_token(booking_record)))


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
        is_valid, intake_data, errors = save_intake_form(booking_record)
        if not is_valid:
            return render_intake_form(booking_record, intake_data, errors=errors), 400
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
    upcoming_count = sum(1 for booking_record in bookings if booking_record.booking_date >= date.today().isoformat())
    return render_template(
        'admin_bookings.html',
        bookings=bookings,
        total=total,
        confirmed_count=confirmed_count,
        pending_intake_count=pending_intake_count,
        upcoming_count=upcoming_count,
        status_labels=BOOKING_STATUS_LABELS,
        status_confirmed=BOOKING_STATUS_CONFIRMED,
    )


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
