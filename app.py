import os, io, json, csv, re, uuid, datetime as dt
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, abort, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from firestore_compat import create_engine, Column, Integer, String, Float, Text, Date, ForeignKey, Boolean, select, func, or_, and_, declarative_base, relationship, sessionmaker, scoped_session, db

APP_NAME='نظام سكن الموظفين'
COMPANY_NAME='Hassan Allam Construction'
WORKSPACES={'apartments':'الشقق','camp':'الكامب'}
CONSUMPTION_TYPES=['كهرباء','مياه','غاز','نظافة','أخرى']
BASE=Path(__file__).resolve().parent
# Vercel deployments are immutable/read-only. Runtime writes must use /tmp.
IS_VERCEL=bool(os.getenv('VERCEL'))
RUNTIME_BASE=Path('/tmp/staff_housing') if IS_VERCEL else BASE
RUNTIME_BASE.mkdir(parents=True, exist_ok=True)
UPLOAD=RUNTIME_BASE/'uploads'
UPLOAD.mkdir(parents=True, exist_ok=True)
# SQLite is fine for local development only. On Vercel, set DATABASE_URL to a
# persistent PostgreSQL database (Supabase/Neon/Railway/etc.). The /tmp fallback
# exists only so a fresh deployment can boot before the database is configured.
DB_URL=(os.getenv('DATABASE_URL') or '').strip()
if DB_URL.startswith('postgres://'):
    DB_URL=DB_URL.replace('postgres://','postgresql+psycopg://',1)
elif DB_URL.startswith('postgresql://'):
    DB_URL=DB_URL.replace('postgresql://','postgresql+psycopg://',1)
elif not DB_URL:
    DB_URL=f'sqlite:///{RUNTIME_BASE / "staff_housing.db"}'
engine=db
Session=scoped_session(sessionmaker())
Base=declarative_base()

def get_engine():
    return db

class Apartment(Base):
    __tablename__='apartments'
    id=Column(Integer,primary_key=True)
    workspace=Column(String(30),default='apartments',index=True)
    contract_no=Column(String(120),index=True)
    norm_contract=Column(String(120),index=True)
    landlord=Column(String(200)); district=Column(String(200)); building_no=Column(String(100)); apt_no=Column(String(100))
    rooms=Column(String(50)); category=Column(String(50)); insurance_amount=Column(Float,default=0); rent_amount=Column(Float,default=0); capacity=Column(Integer,default=0)
    contract_start=Column(Date); contract_end=Column(Date); status=Column(String(30),default='active'); closed_date=Column(Date)
    contract_file=Column(String(500)); extra_json=Column(Text,default='{}')
    residents=relationship('Resident',back_populates='apartment',cascade='all, delete-orphan')
class Resident(Base):
    __tablename__='residents'
    id=Column(Integer,primary_key=True); workspace=Column(String(30),default='apartments',index=True); apartment_id=Column(Integer,ForeignKey('apartments.id'))
    resident_name=Column(String(200),index=True); employee_code=Column(String(100)); card_no=Column(String(100)); job_title=Column(String(200)); employment_type=Column(String(80))
    move_in_date=Column(Date); move_out_date=Column(Date); attachment=Column(String(500)); extra_json=Column(Text,default='{}')
    apartment=relationship('Apartment',back_populates='residents')
class ProjectInfo(Base):
    __tablename__='project_info'
    id=Column(Integer,primary_key=True); workspace=Column(String(30),unique=True); code=Column(String(100)); name=Column(String(250))
class FieldDef(Base):
    __tablename__='field_defs'
    id=Column(Integer,primary_key=True); workspace=Column(String(30),index=True); key=Column(String(100)); label=Column(String(200)); field_type=Column(String(30),default='text'); enabled=Column(Boolean,default=True); sort_order=Column(Integer,default=0)
class Custody(Base):
    __tablename__='custodies'
    id=Column(Integer,primary_key=True); workspace=Column(String(30),index=True); custody_no=Column(String(100)); delegate_name=Column(String(200)); housing_officer=Column(String(200))
    period_start=Column(Date); period_end=Column(Date); handover_date=Column(Date); receive_date=Column(Date); status=Column(String(30),default='draft'); created_at=Column(Date,default=dt.date.today); closed_at=Column(Date)
    lines=relationship('CustodyLine',back_populates='custody',cascade='all, delete-orphan')
class CustodyLine(Base):
    __tablename__='custody_lines'
    id=Column(Integer,primary_key=True); custody_id=Column(Integer,ForeignKey('custodies.id')); apartment_id=Column(Integer,ForeignKey('apartments.id'))
    consumption_type=Column(String(100)); invoice_date=Column(Date); meter_code=Column(String(150)); previous_reading=Column(Float,default=0); current_reading=Column(Float,default=0); quantity=Column(Float,default=0); amount=Column(Float,default=0); notes=Column(Text)
    custody=relationship('Custody',back_populates='lines'); apartment=relationship('Apartment')
DB_INITIALIZED=False

def ensure_db():
    global DB_INITIALIZED
    if DB_INITIALIZED:
        return
    db_engine=get_engine()
    Base.metadata.create_all(db_engine)
    seed_fields()
    DB_INITIALIZED=True

DEFAULT_FIELDS=[('contract_no','كود الوحدة / رقم العقد *','text'),('landlord','اسم المؤجر','text'),('district','المنطقة','text'),('building_no','رقم العقار','text'),('apt_no','رقم الشقة','text'),('rooms','عدد الغرف','text'),('category','فئة السكن','text'),('insurance_amount','قيمة التأمين','number'),('rent_amount','قيمة الإيجار','number'),('capacity','الطاقة الاستيعابية','number'),('contract_start','بداية التعاقد','date'),('contract_end','نهاية التعاقد','date')]

def seed_fields():
    s=Session()
    for ws in WORKSPACES:
        if not s.query(FieldDef).filter_by(workspace=ws).count():
            for i,(k,l,t) in enumerate(DEFAULT_FIELDS): s.add(FieldDef(workspace=ws,key=k,label=l,field_type=t,sort_order=i))
        if not s.query(ProjectInfo).filter_by(workspace=ws).first(): s.add(ProjectInfo(workspace=ws,code='',name=''))
    s.commit(); s.close()

def dparse(v):
    if not v: return None
    if isinstance(v,dt.datetime): return v.date()
    if isinstance(v,dt.date): return v
    s=str(v).strip()
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%m/%d/%Y'):
        try:return dt.datetime.strptime(s,fmt).date()
        except:pass
    return None

def num(v):
    try:return float(str(v).replace(',',''))
    except:return 0

def extras(obj):
    try:return json.loads(obj.extra_json or '{}')
    except:return {}

def set_extra(obj,key,value):
    e=extras(obj); e[key]=value; obj.extra_json=json.dumps(e,ensure_ascii=False)

def active_residents(s,apt):
    today=dt.date.today()
    return [r for r in apt.residents if r.move_out_date is None]

def login_required(f):
    @wraps(f)
    def w(*a,**kw):
        if not session.get('user'): return redirect(url_for('login',next=request.path))
        return f(*a,**kw)
    return w

def ws_required(f):
    @wraps(f)
    def w(*a,**kw):
        if session.get('workspace') not in WORKSPACES: return redirect(url_for('workspace'))
        return f(*a,**kw)
    return w

def get_ws(): return session.get('workspace','apartments')
def project(s): return s.query(ProjectInfo).filter_by(workspace=get_ws()).first()
def fields(s): return s.query(FieldDef).filter_by(workspace=get_ws(),enabled=True).order_by(FieldDef.sort_order,FieldDef.id).all()

def allowed_file(fn): return Path(fn).suffix.lower() in {'.pdf','.jpg','.jpeg','.png','.xlsx','.doc','.docx'}

def save_upload(fileobj, prefix):
    if not fileobj or not fileobj.filename:return None
    if not allowed_file(fileobj.filename): raise ValueError('نوع الملف غير مسموح')
    name=f'{prefix}_{uuid.uuid4().hex}{secure_filename(fileobj.filename)}'
    path=UPLOAD/name; fileobj.save(path)
    return name

def project_payload(p): return {'code':p.code or '','name':p.name or ''}

app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','change-this-secret-in-production')
app.config['MAX_CONTENT_LENGTH']=25*1024*1024

DB_REQUIRED_ENDPOINTS={
    'dashboard','project_settings','columns','apartment_new','apartment_edit','apartment_detail',
    'apartment_close','apartment_delete','apartment_delete_all','resident_new','move_out','files',
    'archive','reopen','search','import_apartments','import_residents','template_download',
    'monthly_report','expiry_report','occupancy_report','cost_report','movement_report',
    'custodies','custody_new','custody_detail','custody_line','custody_line_delete','custody_export','custody_pdf'
}

@app.before_request
def initialize_database():
    # Login/health must remain available even if the database is not configured yet.
    if request.endpoint in {'health','login','static'} or request.endpoint not in DB_REQUIRED_ENDPOINTS:
        return None
    try:
        ensure_db()
    except Exception as exc:
        app.logger.exception('Database initialization failed')
        return jsonify({'error':'Database initialization failed','details':str(exc),'hint':'Set a valid DATABASE_URL PostgreSQL connection string in Vercel Environment Variables.'}), 503

@app.get('/health')
def health():
    return jsonify({'status':'ok','vercel':bool(os.getenv('VERCEL')),'python':'flask'})

@app.get('/health/db')
def health_db():
    try:
        ensure_db()
        with Session() as s:
            s.execute(select(1))
        return jsonify({'status':'ok','database':'reachable'})
    except Exception as exc:
        app.logger.exception('Database health check failed')
        return jsonify({'status':'error','database':'unreachable','details':str(exc)}), 503

app.jinja_env.globals['getattr']=getattr
app.jinja_env.globals['today']=dt.date.today
app.jinja_env.globals['extras']=extras
@app.teardown_appcontext
def shutdown(exc=None): Session.remove()

@app.context_processor
def inject():
    p=None
    if session.get('user') and session.get('workspace') in WORKSPACES:
        try:
            p=project(Session())
        except Exception:
            p=None
    return {'APP_NAME':APP_NAME,'COMPANY_NAME':COMPANY_NAME,'WORKSPACES':WORKSPACES,'current_ws':get_ws(),'project':p}

@app.route('/')
def home():
    if not session.get('user'): return redirect(url_for('login'))
    if not session.get('workspace'): return redirect(url_for('workspace'))
    return redirect(url_for('dashboard'))
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=request.form.get('username','').strip(); p=request.form.get('password','')
        au=os.getenv('ADMIN_USER','admin'); ap=os.getenv('ADMIN_PASSWORD','admin123')
        ok=(u==au and (p==ap or check_password_hash(ap,p) if ap.startswith('scrypt:') or ap.startswith('pbkdf2:') else p==ap))
        if ok: session['user']=u; return redirect(request.args.get('next') or url_for('workspace'))
        flash('اسم المستخدم أو كلمة المرور غير صحيحة','danger')
    return render_template('login.html')
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))
@app.route('/workspace',methods=['GET','POST'])
@login_required
def workspace():
    if request.method=='POST': session['workspace']=request.form.get('workspace'); return redirect(url_for('dashboard'))
    return render_template('workspace.html')
@app.route('/switch/<ws>')
@login_required
def switch(ws):
    if ws not in WORKSPACES: abort(404)
    session['workspace']=ws; return redirect(url_for('dashboard'))

@app.route('/settings/project',methods=['GET','POST'])
@login_required
@ws_required
def project_settings():
    s=Session(); p=project(s)
    if request.method=='POST': p.code=request.form.get('code','').strip(); p.name=request.form.get('name','').strip(); s.commit(); flash('تم حفظ بيانات المشروع','success'); return redirect(url_for('dashboard'))
    return render_template('project_settings.html',p=p)

@app.route('/columns',methods=['GET','POST'])
@login_required
@ws_required
def columns():
    s=Session(); fs=s.query(FieldDef).filter_by(workspace=get_ws()).order_by(FieldDef.sort_order,FieldDef.id).all()
    if request.method=='POST':
        for f in fs: f.enabled=bool(request.form.get(f'active_{f.id}')); f.label=request.form.get(f'label_{f.id}',f.label).strip() or f.label
        # add new custom field
        label=request.form.get('new_label','').strip(); key=request.form.get('new_key','').strip()
        if label and key and not s.query(FieldDef).filter_by(workspace=get_ws(),key=key).first(): s.add(FieldDef(workspace=get_ws(),key=key,label=label,field_type='text',sort_order=len(fs)))
        s.commit(); flash('تم تحديث الأعمدة','success'); return redirect(url_for('columns'))
    return render_template('columns.html',fields=fs)

@app.route('/dashboard')
@login_required
@ws_required
def dashboard():
    s=Session(); ws=get_ws(); a=s.query(Apartment).filter_by(workspace=ws,status='active').order_by(Apartment.norm_contract).all(); res=s.query(Resident).filter_by(workspace=ws).all()
    active_res=[r for r in res if not r.move_out_date]; cap=sum(a.capacity or 0 for a in a); exp=[]
    for x in a:
        if x.contract_end and 0 <= (x.contract_end-dt.date.today()).days <= 60: exp.append(x)
    return render_template('dashboard.html',apartments=a,residents=active_res,total_units=len(a),total_residents=len(active_res),capacity=cap,free=max(cap-len(active_res),0),expiring=exp)

@app.route('/apartments/new',methods=['GET','POST'])
@login_required
@ws_required
def apartment_new():
    s=Session(); fs=fields(s)
    if request.method=='POST':
        contract=request.form.get('contract_no','').strip()
        if not contract: flash('كود الوحدة / رقم العقد مطلوب','danger'); return render_template('apartment_form.html',apt=None,fields=fs)
        if s.query(Apartment).filter_by(workspace=get_ws(),norm_contract=contract).first(): flash('كود الوحدة موجود بالفعل','danger'); return render_template('apartment_form.html',apt=None,fields=fs)
        a=Apartment(workspace=get_ws(),contract_no=contract,norm_contract=contract,status='active',insurance_amount=num(request.form.get('insurance_amount')),rent_amount=num(request.form.get('rent_amount')),capacity=int(num(request.form.get('capacity'))))
        for k in ['landlord','district','building_no','apt_no','rooms','category']: setattr(a,k,request.form.get(k,'').strip())
        a.contract_start=dparse(request.form.get('contract_start')); a.contract_end=dparse(request.form.get('contract_end'))
        for f in fs:
            if f.key not in {'contract_no','landlord','district','building_no','apt_no','rooms','category','insurance_amount','rent_amount','capacity','contract_start','contract_end'}: set_extra(a,f.key,request.form.get(f.key,''))
        try:a.contract_file=save_upload(request.files.get('contract_file'),'contract')
        except ValueError as e: flash(str(e),'danger'); return render_template('apartment_form.html',apt=a,fields=fs)
        s.add(a); s.commit(); flash('تمت إضافة الشقة','success'); return redirect(url_for('apartment_detail',apt_id=a.id))
    return render_template('apartment_form.html',apt=None,fields=fs)

@app.route('/apartments/<int:apt_id>/edit',methods=['GET','POST'])
@login_required
@ws_required
def apartment_edit(apt_id):
    s=Session(); a=s.query(Apartment).filter_by(id=apt_id,workspace=get_ws()).first_or_404(); fs=fields(s)
    if request.method=='POST':
        old=a.contract_no; a.contract_no=request.form.get('contract_no','').strip(); a.norm_contract=a.contract_no
        for k in ['landlord','district','building_no','apt_no','rooms','category']: setattr(a,k,request.form.get(k,'').strip())
        a.insurance_amount=num(request.form.get('insurance_amount')); a.rent_amount=num(request.form.get('rent_amount')); a.capacity=int(num(request.form.get('capacity'))); a.contract_start=dparse(request.form.get('contract_start')); a.contract_end=dparse(request.form.get('contract_end'))
        for f in fs:
            if f.key not in {'contract_no','landlord','district','building_no','apt_no','rooms','category','insurance_amount','rent_amount','capacity','contract_start','contract_end'}: set_extra(a,f.key,request.form.get(f.key,''))
        if request.files.get('contract_file') and request.files['contract_file'].filename:
            try:a.contract_file=save_upload(request.files['contract_file'],'contract')
            except ValueError as e: flash(str(e),'danger')
        s.commit(); flash(f'تم تعديل الوحدة {old}','success'); return redirect(url_for('apartment_detail',apt_id=a.id))
    return render_template('apartment_form.html',apt=a,fields=fs)

@app.route('/apartments/<int:apt_id>')
@login_required
@ws_required
def apartment_detail(apt_id):
    s=Session(); a=s.query(Apartment).filter_by(id=apt_id,workspace=get_ws()).first_or_404(); return render_template('apartment_detail.html',apt=a,residents=active_residents(s,a),all_residents=a.residents,extra=extras(a))

@app.post('/apartments/<int:apt_id>/close')
@login_required
@ws_required
def apartment_close(apt_id):
    s=Session(); a=s.query(Apartment).filter_by(id=apt_id,workspace=get_ws()).first_or_404(); a.status='closed'; a.closed_date=dparse(request.form.get('closed_date')) or dt.date.today(); s.commit(); flash('تم إنهاء/تعليق العقد ونقله للأرشيف','success'); return redirect(url_for('dashboard'))
@app.post('/apartments/<int:apt_id>/delete')
@login_required
@ws_required
def apartment_delete(apt_id):
    s=Session(); a=s.query(Apartment).filter_by(id=apt_id,workspace=get_ws()).first_or_404(); s.delete(a); s.commit(); flash('تم حذف الوحدة نهائيًا','success'); return redirect(url_for('dashboard'))
@app.post('/apartments/delete-all')
@login_required
@ws_required
def apartment_delete_all():
    s=Session(); s.query(Apartment).filter_by(workspace=get_ws()).delete(synchronize_session=False); s.commit(); flash('تم حذف كل الوحدات','success'); return redirect(url_for('dashboard'))

@app.route('/residents/new',methods=['GET','POST'])
@login_required
@ws_required
def resident_new():
    s=Session(); apts=s.query(Apartment).filter_by(workspace=get_ws(),status='active').order_by(Apartment.norm_contract).all()
    if request.method=='POST':
        a=s.query(Apartment).filter_by(id=int(request.form.get('apartment_id')),workspace=get_ws(),status='active').first()
        if not a: flash('الوحدة غير موجودة','danger'); return render_template('resident_form.html',apts=apts)
        r=Resident(workspace=get_ws(),apartment=a,resident_name=request.form.get('resident_name','').strip(),employee_code=request.form.get('employee_code','').strip(),card_no=request.form.get('card_no','').strip(),job_title=request.form.get('job_title','').strip(),employment_type=request.form.get('employment_type','معين'),move_in_date=dparse(request.form.get('move_in_date')) or dt.date.today())
        try:r.attachment=save_upload(request.files.get('attachment'),'employee')
        except ValueError as e: flash(str(e),'danger'); return render_template('resident_form.html',apts=apts)
        s.add(r); s.commit(); flash('تمت إضافة الموظف','success'); return redirect(url_for('apartment_detail',apt_id=a.id))
    return render_template('resident_form.html',apts=apts)
@app.post('/residents/<int:rid>/move-out')
@login_required
@ws_required
def move_out(rid):
    s=Session(); r=s.query(Resident).filter_by(id=rid,workspace=get_ws()).first_or_404(); r.move_out_date=dparse(request.form.get('move_out_date')) or dt.date.today(); s.commit(); flash('تم تسجيل الإخلاء ونقل الموظف للأرشيف','success'); return redirect(request.referrer or url_for('dashboard'))

@app.route('/files/<kind>/<name>')
@login_required
@ws_required
def files(kind,name):
    if not re.match(r'^[\w. -]+$',name): abort(404)
    s=Session(); allowed=False
    if kind=='contract': allowed=s.query(Apartment).filter_by(workspace=get_ws(),contract_file=name).first() is not None
    if kind=='employee': allowed=s.query(Resident).filter_by(workspace=get_ws(),attachment=name).first() is not None
    if not allowed: abort(404)
    return send_file(UPLOAD/name,as_attachment=False)

@app.route('/archive')
@login_required
@ws_required
def archive():
    s=Session(); a=s.query(Apartment).filter_by(workspace=get_ws(),status='closed').order_by(Apartment.closed_date.desc()).all(); r=s.query(Resident).filter_by(workspace=get_ws()).filter(Resident.move_out_date.isnot(None)).order_by(Resident.move_out_date.desc()).all(); return render_template('archive.html',apartments=a,residents=r)
@app.post('/archive/<int:apt_id>/reopen')
@login_required
@ws_required
def reopen(apt_id):
    s=Session(); a=s.query(Apartment).filter_by(id=apt_id,workspace=get_ws()).first_or_404(); a.status='active'; a.closed_date=None; s.commit(); flash('تمت إعادة تفعيل الوحدة','success'); return redirect(url_for('archive'))

@app.route('/search')
@login_required
@ws_required
def search():
    s=Session(); q=request.args.get('q','').strip(); a=s.query(Apartment).filter_by(workspace=get_ws()).order_by(Apartment.norm_contract).all();
    if q:
        low=q.lower(); a=[x for x in a if low in ' '.join([str(x.contract_no or ''),str(x.landlord or ''),str(x.district or ''),*(r.resident_name or '' for r in x.residents)]).lower()]
    return render_template('search.html',results=a,q=q)

# Excel import/export
@app.route('/import/apartments',methods=['GET','POST'])
@login_required
@ws_required
def import_apartments():
    from openpyxl import load_workbook
    if request.method=='POST':
        f=request.files.get('file'); s=Session()
        if not f: flash('اختر ملف Excel','danger'); return redirect(url_for('import_apartments'))
        wb=load_workbook(f); ws=wb.active; rows=list(ws.iter_rows(values_only=True)); headers=[str(x).strip() if x is not None else '' for x in rows[0]] if rows else []
        labelmap={x.label.strip():x.key for x in fields(s)}; cmap={i:labelmap[h] for i,h in enumerate(headers) if h in labelmap}; added=skipped=0
        if 'contract_no' not in cmap: flash("لازم يكون فيه عمود 'كود الوحدة / رقم العقد *'",'danger'); return redirect(url_for('import_apartments'))
        for row in rows[1:]:
            rec={cmap[i]:row[i] for i in cmap if i<len(row) and row[i] is not None}; c=str(rec.get('contract_no','')).strip()
            if not c or s.query(Apartment).filter_by(workspace=get_ws(),norm_contract=c).first(): skipped+=1; continue
            a=Apartment(workspace=get_ws(),contract_no=c,norm_contract=c,status='active',insurance_amount=num(rec.get('insurance_amount')),rent_amount=num(rec.get('rent_amount')),capacity=int(num(rec.get('capacity'))))
            for k in ['landlord','district','building_no','apt_no','rooms','category']: setattr(a,k,str(rec.get(k,'')))
            a.contract_start=dparse(rec.get('contract_start')); a.contract_end=dparse(rec.get('contract_end')); s.add(a); added+=1
        s.commit(); flash(f'تم استيراد {added} وحدة وتخطي {skipped}','success'); return redirect(url_for('dashboard'))
    return render_template('import.html',kind='apartments')

ALIASES={'resident_name':['اسم الموظف *','اسم الموظف','اسماء المقيمين','اسماء المقيمين رباعى','الاسم','اسم المقيم'],'employee_code':['كود الموظف','كود المقيمين','الكود الوظيفى'],'card_no':['رقم البطاقة','رقم البطاقه','رقم بطاقة'],'job_title':['الوظيفة','وظيفة المقيمين','الوظيفه'],'employment_type':['نوع التعيين','معين /يومى','معين/يومى','معين / يومى'],'contract_no':['كود الوحدة / رقم العقد (الشقة) *','كود الوحدة / رقم العقد *','كود الوحدة','رقم العقد','كود الشقه','كود الشقة'],'move_in_date':['تاريخ التسكين * (YYYY-MM-DD)','تاريخ التسكين'],'move_out_date':['تاريخ الخروج (اختياري YYYY-MM-DD)','تاريخ الخروج','تاريخ الخروج (من السكن)']}
def normhead(x): return str(x).strip().replace(' *','').replace('  ',' ')
@app.route('/import/residents',methods=['GET','POST'])
@login_required
@ws_required
def import_residents():
    from openpyxl import load_workbook
    if request.method=='POST':
        f=request.files.get('file'); s=Session()
        if not f: flash('اختر ملف Excel','danger'); return redirect(url_for('import_residents'))
        wb=load_workbook(f); ws=wb.active; rows=list(ws.iter_rows(values_only=True)); alias={normhead(n):k for k,v in ALIASES.items() for n in v}; best=(-1,0,{})
        for ri,row in enumerate(rows[:10]):
            cmap={i:alias[normhead(v)] for i,v in enumerate(row) if normhead(v) in alias}; score=len(set(cmap.values()))
            if score>best[0]:best=(score,ri,cmap)
        _,ri,cmap=best; added=skipped=unresolved=0; apts={a.norm_contract:a for a in s.query(Apartment).filter_by(workspace=get_ws()).all()}
        for row in rows[ri+1:]:
            if all(v is None for v in row):continue
            rec={cmap[i]:row[i] for i in cmap if i<len(row) and row[i] is not None}; name=rec.get('resident_name'); c=str(rec.get('contract_no','')).strip(); mi=dparse(rec.get('move_in_date'))
            if not name or not c or not mi: skipped+=1; continue
            a=apts.get(c)
            if not a: unresolved+=1; continue
            r=Resident(workspace=get_ws(),apartment=a,resident_name=str(name),employee_code=str(rec.get('employee_code','') or ''),card_no=str(rec.get('card_no','') or ''),job_title=str(rec.get('job_title','') or ''),employment_type=str(rec.get('employment_type','معين') or 'معين'),move_in_date=mi,move_out_date=dparse(rec.get('move_out_date'))); s.add(r); added+=1
        s.commit(); flash(f'تم استيراد {added} موظف، تخطي {skipped}، وأرقام وحدات غير موجودة {unresolved}','success'); return redirect(url_for('dashboard'))
    return render_template('import.html',kind='residents')

@app.route('/templates/download/<kind>')
@login_required
@ws_required
def template_download(kind):
    from openpyxl import Workbook
    s=Session(); wb=Workbook(); ws=wb.active; ws.sheet_view.rightToLeft=True
    if kind=='apartments': ws.title='شقق'; ws.append([f.label for f in fields(s)]) ; name='قالب_استيراد_الشقق.xlsx'
    else: ws.title='موظفين'; ws.append(['اسم الموظف *','كود الموظف','رقم البطاقة','الوظيفة','نوع التعيين','كود الوحدة / رقم العقد (الشقة) *','تاريخ التسكين * (YYYY-MM-DD)','تاريخ الخروج (اختياري YYYY-MM-DD)']); name='قالب_استيراد_الموظفين.xlsx'
    bio=io.BytesIO(); wb.save(bio); bio.seek(0); return send_file(bio,download_name=name,as_attachment=True)

# Reports
MONTHS=['','يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر']
def make_xlsx(title,headers,rows,filename,sheets=None):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    wb=Workbook(); ws=wb.active; ws.title=title; ws.sheet_view.rightToLeft=True; ws.append(headers)
    for r in rows: ws.append(r)
    for c in ws[1]: c.font=Font(bold=True); c.alignment=Alignment(horizontal='right')
    for i in range(1,len(headers)+1): ws.column_dimensions[chr(64+i) if i<=26 else 'A'].width=18
    if sheets:
        for sh,hd,rs in sheets:
            w=wb.create_sheet(sh); w.sheet_view.rightToLeft=True; w.append(hd); [w.append(r) for r in rs]
            for c in w[1]: c.font=Font(bold=True)
    b=io.BytesIO(); wb.save(b); b.seek(0); return send_file(b,download_name=filename,as_attachment=True)
@app.route('/reports/monthly',methods=['GET','POST'])
@login_required
@ws_required
def monthly_report():
    if request.method=='GET': return render_template('report_form.html',kind='monthly')
    month=int(request.form.get('month')); year=int(request.form.get('year')); start=dt.date(year,month,1); end=dt.date(year+1,1,1)-dt.timedelta(days=1) if month==12 else dt.date(year,month+1,1)-dt.timedelta(days=1); s=Session(); p=project(s); rows=[]
    for a in s.query(Apartment).filter_by(workspace=get_ws(),status='active').order_by(Apartment.norm_contract):
        rr=[r for r in a.residents if r.move_in_date and r.move_in_date<=end and (not r.move_out_date or r.move_out_date>=start)]
        if not rr:continue
        rent=a.rent_amount or 0; per=round(rent/len(rr),2) if rr else 0
        for i,r in enumerate(sorted(rr,key=lambda x:x.move_in_date)):
            rows.append([(p.code if i==0 else ''),(p.name if i==0 else ''),MONTHS[month],a.contract_no,(a.landlord or '') if i==0 else '',(a.district or '') if i==0 else '',(a.building_no or '') if i==0 else '',(a.apt_no or '') if i==0 else '',(a.rooms or '') if i==0 else '',(a.category or '') if i==0 else '',a.insurance_amount if i==0 else '',rent if i==0 else '',per if i==0 else '',a.capacity if i==0 else '',len(rr) if i==0 else '',max((a.capacity or 0)-len(rr),0) if i==0 else '',str(a.contract_start or '') if i==0 else '',str(a.contract_end or '') if i==0 else '',i+1,r.card_no or r.employee_code or '',r.resident_name,r.job_title or '',r.employment_type or ''])
    hd=['كود المشروع','اسم المشروع','شهر','كود الوحدة','اسم المؤجر','المنطقة','رقم العقار','رقم الشقة','عدد الغرف','فئة السكن','قيمة التأمين','قيمة الإيجار','القيمة الايجارية للفرد','الطاقة الاستيعابية','عدد المقيمين','العدد المتاح','بداية التعاقد','نهاية التعاقد','م','الكود الوظيفى / رقم البطاقة','اسم الموظف','الوظيفة','نوع المستخدم']
    return make_xlsx('مطالبة السكن',hd,rows,f'مطالبة_السكن_{MONTHS[month]}_{year}.xlsx')
@app.route('/reports/expiry',methods=['GET','POST'])
@login_required
@ws_required
def expiry_report():
    if request.method=='GET': return render_template('report_form.html',kind='expiry')
    days=int(request.form.get('days',60)); today=dt.date.today(); cutoff=today+dt.timedelta(days=days); s=Session(); rows=[]
    for a in s.query(Apartment).filter_by(workspace=get_ws(),status='active'):
        if a.contract_end and today<=a.contract_end<=cutoff: rows.append([a.contract_no,a.landlord or '',a.district or '',a.contract_end.isoformat(),(a.contract_end-today).days,len(active_residents(s,a)),a.rent_amount or 0])
    return make_xlsx('عقود قريبة من الانتهاء',['كود الوحدة','اسم المؤجر','المنطقة','نهاية التعاقد','أيام متبقية','عدد المقيمين حاليًا','قيمة الإيجار'],rows,f'عقود_قريبة_من_الانتهاء_{today.isoformat()}.xlsx')
@app.route('/reports/occupancy')
@login_required
@ws_required
def occupancy_report():
    s=Session(); rows=[]; cap=occ=vac=0
    for a in s.query(Apartment).filter_by(workspace=get_ws(),status='active').order_by(Apartment.norm_contract):
        n=len(active_residents(s,a)); c=a.capacity or 0; free=max(c-n,0); pct=round(n/c*100,1) if c else 0; st='فاضية تمامًا' if n==0 else ('مكتملة' if free==0 else 'متاح فيها'); rows.append([a.contract_no,a.landlord or '',a.district or '',a.category or '',c,n,free,pct,st]); cap+=c;occ+=n;vac+= n==0
    rows.append(['الإجمالي','','','',cap,occ,max(cap-occ,0),round(occ/cap*100,1) if cap else 0,f'{vac} شقة فاضية تمامًا'])
    return make_xlsx('الإشغال والشواغر',['كود الوحدة','اسم المؤجر','المنطقة','فئة السكن','الطاقة الاستيعابية','عدد المقيمين','الأماكن المتاحة','نسبة الإشغال %','الحالة'],rows,f'تقرير_الإشغال_{dt.date.today().isoformat()}.xlsx')
@app.route('/reports/cost')
@login_required
@ws_required
def cost_report():
    s=Session(); apts=s.query(Apartment).filter_by(workspace=get_ws(),status='active').all(); cats={}; regs={}
    for a in apts:
        n=len(active_residents(s,a));
        for d,k in ((cats,a.category or 'غير محدد'),(regs,a.district or 'غير محدد')):
            g=d.setdefault(k,[0,0,0,0]); g[0]+=1;g[1]+=n;g[2]+=a.rent_amount or 0;g[3]+=a.insurance_amount or 0
    def rows(d): return [[k,*v,round(v[2]/v[1],2) if v[1] else 0] for k,v in sorted(d.items())]
    hd=['التصنيف','عدد الشقق','عدد المقيمين','إجمالي الإيجار الشهري','إجمالي التأمين','متوسط الإيجار للفرد']; return make_xlsx('التكلفة حسب الفئة',hd,rows(cats),f'ملخص_التكلفة_{dt.date.today().isoformat()}.xlsx',sheets=[('التكلفة حسب المنطقة',hd,rows(regs))])
@app.route('/reports/movement',methods=['GET','POST'])
@login_required
@ws_required
def movement_report():
    if request.method=='GET': return render_template('report_form.html',kind='movement')
    start=dparse(request.form.get('start')); end=dparse(request.form.get('end')); s=Session(); rows=[]
    for r in s.query(Resident).filter_by(workspace=get_ws()).all():
        if r.move_in_date and start<=r.move_in_date<=end: rows.append(['تسكين',r.move_in_date.isoformat(),r.resident_name,r.employee_code or '',r.apartment.contract_no if r.apartment else '',r.apartment.landlord if r.apartment else '',r.job_title or ''])
        if r.move_out_date and start<=r.move_out_date<=end: rows.append(['إخلاء',r.move_out_date.isoformat(),r.resident_name,r.employee_code or '',r.apartment.contract_no if r.apartment else '',r.apartment.landlord if r.apartment else '',r.job_title or ''])
    rows.sort(key=lambda x:x[1]); return make_xlsx('حركة الموظفين',['نوع الحركة','التاريخ','اسم الموظف','كود الموظف','كود الوحدة','اسم المؤجر','الوظيفة'],rows,f'حركة_الموظفين_{start}_{end}.xlsx')

# Custody
@app.route('/custodies')
@login_required
@ws_required
def custodies():
    s=Session(); return render_template('custodies.html',custodies=s.query(Custody).filter_by(workspace=get_ws()).order_by(Custody.id.desc()).all())
@app.route('/custodies/new',methods=['GET','POST'])
@login_required
@ws_required
def custody_new():
    s=Session(); draft=s.query(Custody).filter_by(workspace=get_ws(),status='draft').first()
    if draft: flash('يوجد عهدة مفتوحة بالفعل','warning'); return redirect(url_for('custody_detail',cid=draft.id))
    if request.method=='POST':
        c=Custody(workspace=get_ws(),custody_no=request.form.get('custody_no','').strip(),delegate_name=request.form.get('delegate_name','').strip(),housing_officer=request.form.get('housing_officer','').strip(),period_start=dparse(request.form.get('period_start')),period_end=dparse(request.form.get('period_end')),handover_date=dparse(request.form.get('handover_date')),receive_date=dparse(request.form.get('receive_date')),status='draft'); s.add(c); s.commit(); return redirect(url_for('custody_detail',cid=c.id))
    return render_template('custody_form.html')
@app.route('/custodies/<int:cid>',methods=['GET','POST'])
@login_required
@ws_required
def custody_detail(cid):
    s=Session(); c=s.query(Custody).filter_by(id=cid,workspace=get_ws()).first_or_404(); apts=s.query(Apartment).filter_by(workspace=get_ws(),status='active').order_by(Apartment.norm_contract).all()
    if request.method=='POST':
        c.custody_no=request.form.get('custody_no',c.custody_no); c.delegate_name=request.form.get('delegate_name',''); c.housing_officer=request.form.get('housing_officer',''); c.period_start=dparse(request.form.get('period_start')); c.period_end=dparse(request.form.get('period_end')); c.handover_date=dparse(request.form.get('handover_date')); c.receive_date=dparse(request.form.get('receive_date')); s.commit(); flash('تم حفظ بيانات العهدة','success'); return redirect(url_for('custody_detail',cid=cid))
    return render_template('custody_detail.html',custody=c,apts=apts)
@app.post('/custodies/<int:cid>/line')
@login_required
@ws_required
def custody_line(cid):
    s=Session(); c=s.query(Custody).filter_by(id=cid,workspace=get_ws(),status='draft').first_or_404(); a=s.query(Apartment).filter_by(id=int(request.form.get('apartment_id')),workspace=get_ws()).first_or_404(); prev=num(request.form.get('previous_reading')); cur=num(request.form.get('current_reading')); qty=num(request.form.get('quantity')) or max(cur-prev,0); amount=num(request.form.get('amount')); c.lines.append(CustodyLine(apartment=a,consumption_type=request.form.get('consumption_type'),invoice_date=dparse(request.form.get('invoice_date')) or dt.date.today(),meter_code=request.form.get('meter_code',''),previous_reading=prev,current_reading=cur,quantity=qty,amount=amount,notes=request.form.get('notes',''))); s.commit(); return redirect(url_for('custody_detail',cid=cid))
@app.post('/custodies/<int:cid>/line/<int:lid>/delete')
@login_required
@ws_required
def custody_line_delete(cid,lid):
    s=Session(); x=s.query(CustodyLine).filter_by(id=lid,custody_id=cid).first_or_404(); s.delete(x); s.commit(); return redirect(url_for('custody_detail',cid=cid))
@app.route('/custodies/<int:cid>/export')
@login_required
@ws_required
def custody_export(cid):
    s=Session(); c=s.query(Custody).filter_by(id=cid,workspace=get_ws()).first_or_404(); p=project(s); hd=['العهدة','المندوب','مسؤول السكن','كود الوحدة','نوع الاستهلاك','تاريخ الفاتورة','كود العداد/المشترك','قراءة سابقة','قراءة حالية','الكمية','القيمة','ملاحظات']; rows=[]
    for l in c.lines: rows.append([c.custody_no,c.delegate_name,c.housing_officer,l.apartment.contract_no,l.consumption_type,str(l.invoice_date or ''),l.meter_code,l.previous_reading,l.current_reading,l.quantity,l.amount,l.notes or ''])
    resp=make_xlsx('بيانات العهدة',hd,rows,f'عهدة_{c.custody_no}.xlsx'); c.status='closed'; c.closed_at=dt.date.today(); s.commit(); return resp
@app.route('/custodies/<int:cid>/pdf')
@login_required
@ws_required
def custody_pdf(cid):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    s=Session(); c=s.query(Custody).filter_by(id=cid,workspace=get_ws()).first_or_404(); b=io.BytesIO(); doc=SimpleDocTemplate(b,pagesize=landscape(A4)); styles=getSampleStyleSheet(); story=[Paragraph(f'{APP_NAME} — عهدة {c.custody_no}',styles['Title']),Spacer(1,10),Paragraph(f'المندوب: {c.delegate_name or ""} | مسؤول السكن: {c.housing_officer or ""}',styles['Normal']),Spacer(1,10)]; data=[['الوحدة','النوع','التاريخ','العداد','الكمية','القيمة','ملاحظات']]+[[l.apartment.contract_no,l.consumption_type,str(l.invoice_date or ''),l.meter_code,l.quantity,l.amount,l.notes or ''] for l in c.lines]; t=Table(data,repeatRows=1); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#34495e')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.5,colors.grey),('ALIGN',(0,0),(-1,-1),'RIGHT')])); story.append(t); doc.build(story); b.seek(0); return send_file(b,download_name=f'عهدة_{c.custody_no}.pdf',as_attachment=True)

# Combined quick API for future frontend/mobile use
@app.get('/api/dashboard')
@login_required
@ws_required
def api_dashboard():
    s=Session(); a=s.query(Apartment).filter_by(workspace=get_ws(),status='active').all(); return jsonify({'workspace':get_ws(),'units':len(a),'residents':sum(len(active_residents(s,x)) for x in a),'capacity':sum(x.capacity or 0 for x in a)})

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')),debug=True)
