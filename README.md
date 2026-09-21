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
