from flask import Flask, render_template, request, redirect, url_for, flash, send_file

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
    status: Mapped[str] = mapped_column(String(40), default='pending')
    created_at: Mapped[str] = mapped_column(String(32), default=lambda: datetime.now().isoformat(timespec='seconds'))


BOOKING_TIME_SLOTS = [
    '10:00-11:00',
    '11:30-12:30',
    '14:00-15:00',
    '15:30-16:30',
    '19:00-20:00',
]

BOOKING_TARGET_COUNTRIES = ['美国', '英国', '加拿大', '澳大利亚', '新加坡&香港', '多国联申', '暂未确定']
BOOKING_STAGES = ['低龄申请', '本科申请', '硕士申请', '博士申请', '转学/转专业', '背景提升规划', '其他']
WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def build_booking_days(days_count=14):
    start = date.today() + timedelta(days=1)
    days = []
    for offset in range(days_count):
        current = start + timedelta(days=offset)
        days.append({
            'value': current.isoformat(),
            'label': current.strftime('%m月%d日'),
            'weekday': WEEKDAY_LABELS[current.weekday()],
        })
    return days


def get_booked_slots_by_date(day_values):
    bookings = Booking.query.filter(Booking.booking_date.in_(day_values)).all()
    booked = {}
    for item in bookings:
        booked.setdefault(item.booking_date, []).append(item.time_slot)
    return booked


def build_booking_context(form_data=None):
    available_days = build_booking_days()
    day_values = [item['value'] for item in available_days]
    return {
        'available_days': available_days,
        'time_slots': BOOKING_TIME_SLOTS,
        'booked_map': get_booked_slots_by_date(day_values),
        'target_countries': BOOKING_TARGET_COUNTRIES,
        'stages': BOOKING_STAGES,
        'form': form_data or {},
    }



def ensure_ranking_schema():
    # Lightweight SQLite schema patching for users upgrading from older columns
    db.create_all()
    cols = {row[1] for row in db.session.execute(sql_text("PRAGMA table_info(ranking)")).fetchall()}
    if not cols:
        return

    ddl = []
    if 'school_name' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN school_name VARCHAR(200) DEFAULT ''")
    if 'english_name' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN english_name VARCHAR(200) DEFAULT ''")
    if 'region' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN region VARCHAR(200) DEFAULT ''")
    if 'qs' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN qs FLOAT DEFAULT 0")
    if 'usnews' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN usnews FLOAT DEFAULT 0")
    if 'the' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN the FLOAT DEFAULT 0")
    if 'arwu' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN arwu FLOAT DEFAULT 0")
    if 'history_data' not in cols:
        ddl.append("ALTER TABLE ranking ADD COLUMN history_data TEXT DEFAULT ''")

    for stmt in ddl:
        db.session.execute(sql_text(stmt))

    # Backfill school_name from old column if present and new column empty
    if 'school' in cols:
        db.session.execute(sql_text("UPDATE ranking SET school_name = school WHERE (school_name IS NULL OR school_name = '') AND school IS NOT NULL"))
    if 'location' in cols:
        db.session.execute(sql_text("UPDATE ranking SET region = location WHERE (region IS NULL OR region = '') AND location IS NOT NULL"))
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

    booking_record = Booking(**form_data, meeting_method='腾讯会议')
    try:
        db.session.add(booking_record)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        context = build_booking_context(form_data)
        return render_template('booking.html', errors=['该时间段刚刚被预约，请选择其他时间。'], **context), 409

    return redirect(url_for('booking_success', booking_id=booking_record.id))


@app.get('/consultation')
def consultation():
    return redirect(url_for('booking'))


@app.get('/booking/success/<int:booking_id>')
def booking_success(booking_id):
    booking_record = Booking.query.get_or_404(booking_id)
    return render_template('booking_success.html', booking=booking_record)

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
