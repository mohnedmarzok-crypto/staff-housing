# نظام سكن الموظفين — Web
نظام Web عربي RTL لإدارة سكن الموظفين، مبني على Flask + SQLAlchemy.

## ما تم تجهيزه
- تسجيل دخول
- مساحتان: الشقق والكامب
- لوحة تحكم وإحصائيات
- إدارة الوحدات والعقود والمقيمين
- أرشيف وبحث
- استيراد Excel وقوالب Excel
- تقارير Excel للمطالبة الشهرية وانتهاء العقود والإشغال والتكلفة والحركة
- العهد والاستهلاكات مع Excel وPDF
- إعدادات المشروع والحقول المخصصة
- واجهة عربية RTL متجاوبة
- Health checks لـ Vercel وقاعدة البيانات

## التشغيل المحلي
```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```
ثم افتح http://127.0.0.1:5000.

## النشر على Vercel
أضف Environment Variables: DATABASE_URL و SECRET_KEY و ADMIN_USER و ADMIN_PASSWORD.
استخدم PostgreSQL مستديمة للإنتاج؛ لا تعتمد على SQLite أو /tmp لحفظ بيانات الإنتاج على Vercel.


## Firebase / Firestore deployment

The application now uses Firestore through the Firebase Admin SDK and is designed to run on Cloud Run.

### Required Cloud Run environment variables
- `SECRET_KEY`
- `ADMIN_USER`
- `ADMIN_PASSWORD`
- `GOOGLE_CLOUD_PROJECT=staff-housing`

The Cloud Run service account must have permission to read and write the Firestore database (Cloud Datastore User / `roles/datastore.user`).

### Deploy
Build the Docker image and deploy the service as `staff-housing` in `us-central1`. Firebase Hosting is configured to rewrite requests to that Cloud Run service.

Firestore database:
- Database ID: `(default)`
- Location: `nam5`
- Mode: Firestore Native
