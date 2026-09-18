# نظام سكن الموظفين — Web

تم تحويل برنامج `staff_housing_template.py` المكتبي (Tkinter/JSON) إلى تطبيق Web مبني بـ Flask + SQLAlchemy.

## الوظائف الموجودة
- الشقق والكامب كقسمين مستقلين
- بيانات المشروع (الكود والاسم)
- إضافة/تعديل/إنهاء/حذف الوحدات
- إدارة الأعمدة وإضافة أعمدة مخصصة
- الموظفون: إضافة، تسكين، إخلاء، أرشيف
- مرفقات العقود والموظفين
- بحث شامل
- استيراد Excel للشقق والموظفين مع aliases
- تنزيل قوالب Excel
- مطالبة السكن الشهرية
- العقود القريبة من الانتهاء
- الإشغال والشواغر
- ملخص التكلفة حسب الفئة والمنطقة
- حركة الموظفين
- العهدات: إنشاء، بنود استهلاك، تعديل، حذف، Excel، PDF، إغلاق وأرشيف
- API بسيطة للـ dashboard

## تشغيل محلي
```bash
python -m venv .venv
.venv\\Scripts\\activate   # Windows
pip install -r requirements.txt
set ADMIN_USER=admin
set ADMIN_PASSWORD=admin123
python app.py
```
ثم افتح `http://127.0.0.1:5000`.

## GitHub + Vercel
1. ارفع الملفات إلى repository جديد.
2. في Vercel اختر Import Project من GitHub.
3. أضف Environment Variables: `SECRET_KEY`, `ADMIN_USER`, `ADMIN_PASSWORD`, `DATABASE_URL`.
4. استخدم PostgreSQL production database. SQLite مناسب للتجربة المحلية فقط.
5. ملفات الرفع المحلية داخل Vercel ليست storage دائمًا؛ استخدم Storage خارجي قبل الاعتماد على النظام في الإنتاج.

## ملاحظة مهمة
هذه النسخة تنقل وظائف البرنامج إلى Web مع قاعدة بيانات. تصميم PDF/Excel التفصيلي للعهدة قد يحتاج مطابقة شكل النماذج الورقية الأصلية إذا أردت نفس الشكل 100%.
