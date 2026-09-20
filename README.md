# نظام سكن الموظفين — Web

نسخة Web من برنامج نظام سكن الموظفين، مبنية بـ Flask + SQLAlchemy + Excel/PDF.

## مهم قبل الإنتاج على Vercel

Vercel يدعم Flask مباشرة بدون `vercel.json` في المشروع الحالي. الكود يستخدم `/tmp` فقط كمساحة تشغيل مؤقتة على Vercel، لكن **قاعدة البيانات والملفات المرفوعة لا يجب أن تعتمد على Vercel filesystem**.

يوجد endpoint للتشخيص: `/health` لا يحتاج قاعدة بيانات، فإذا أعاد `status=ok` فهذا يعني أن Flask runtime بدأ بنجاح.

للحفظ الدائم:

1. أنشئ PostgreSQL Database (مثلاً Supabase أو Neon).
2. أضف في Vercel Environment Variables:
   - `DATABASE_URL` = PostgreSQL connection string
   - `SECRET_KEY` = قيمة عشوائية طويلة
   - `ADMIN_USER` = اسم مستخدم المدير
   - `ADMIN_PASSWORD` = كلمة مرور المدير
3. أعد Deploy.

بدون `DATABASE_URL` سيعمل المشروع محلياً بـ SQLite، وعلى Vercel سيستخدم SQLite داخل `/tmp` مؤقتاً فقط للاختبار؛ البيانات قد تختفي عند إعادة تشغيل الـ Function.

## تشغيل محلياً

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

ثم افتح `http://127.0.0.1:5000`.

## GitHub + Vercel

ارفع محتويات هذا المجلد إلى Repository في GitHub، ثم استورد الـ Repository داخل Vercel.

لا ترفع أي `.env` أو قاعدة بيانات أو ملفات مرفوعة حقيقية إلى GitHub.
