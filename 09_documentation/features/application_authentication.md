# احراز هویت داخل اپلیکیشن Flask

## هدف

در این مرحله یک لایه احراز هویت مبتنی بر Session داخل Flask اضافه شده است.
Basic Authentication موجود در Nginx عمداً حذف نشده و موقتاً به‌عنوان لایه
بیرونی باقی می‌ماند.

جریان ورود فعلی:

```text
Browser
   |
   | 1. Nginx Basic Auth
   v
Nginx Container
   |
   | 2. Flask Login Form
   v
Flask-Login + CSRF
   |
   v
MariaDB users table
```

در مرحله بعد و پس از اطمینان از عملکرد Login داخلی، Basic Auth از Nginx
حذف خواهد شد.

## قابلیت‌های اضافه‌شده

- صفحه Login اختصاصی
- Login و Logout
- Session-based Authentication
- Cookie امن با `Secure`، `HttpOnly` و `SameSite=Lax`
- CSRF Protection برای Login، Logout و اجرای Audit
- ذخیره Password فقط به‌صورت Hash
- قفل موقت حساب پس از چند تلاش ناموفق
- فعال/غیرفعال‌بودن کاربر
- Role اولیه `admin`
- اتصال گزارش‌های SEO به `user_id`
- نمایش تاریخچه تمام کاربران برای Admin
- جلوگیری از Open Redirect در پارامتر `next`
- محدودکردن Hostهای معتبر
- پشتیبانی صحیح از Proxy Headerها
- ساخت خودکار اولین کاربر Admin با Ansible

## Routeها

| Route | Method | دسترسی |
|---|---|---|
| `/health` | GET | عمومی |
| `/login` | GET, POST | عمومی پس از Basic Auth |
| `/logout` | POST | کاربر واردشده |
| `/` | GET | کاربر واردشده |
| `/audit` | POST | کاربر واردشده |

Logout با `GET` پیاده‌سازی نشده است تا عملیات تغییر وضعیت فقط با `POST`
و CSRF Token انجام شود.

## جدول users

```text
users
├── id
├── username
├── password_hash
├── role
├── is_active
├── failed_login_attempts
├── locked_until
├── last_login_at
├── created_at
└── updated_at
```

Password خام داخل MariaDB ذخیره نمی‌شود.

## ارتباط Audit با User

ستون زیر به جدول `seo_audits` اضافه می‌شود:

```text
user_id
```

داده‌های قدیمی حذف نمی‌شوند و مقدار `user_id` رکوردهای Legacy می‌تواند
`NULL` باقی بماند.

## Secretهای جدید

روی Ubuntu Origin:

```text
/opt/seo-auditor/secrets/flask_secret_key.txt
/opt/seo-auditor/secrets/app_admin_password.txt
```

Permission:

```text
owner: root
group: appcontainer
mode: 0640
```

Flask Session Secret از طریق مسیر زیر داخل Backend قرار می‌گیرد:

```text
/run/secrets/flask-secret-key
```

Password اولیه Admin از مسیر زیر فقط به Bootstrap Service داده می‌شود:

```text
/run/secrets/app-admin-password
```

## فایل Credentials روی Controller

```text
08_ansible_automation/public/app_auth/
generated_app_admin_credentials.txt
```

این فایل:

- Permission برابر `0600` دارد.
- توسط `.gitignore` نادیده گرفته می‌شود.
- نباید در Git، Ticket یا Chat عمومی منتشر شود.

## Session Security

تنظیمات اصلی:

```text
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax
SESSION_COOKIE_DOMAIN=None
SESSION_LIFETIME_MINUTES=480
```

Secret مربوط به امضای Session Cookie به‌صورت تصادفی و خارج از Git تولید
می‌شود.

## CSRF و Referrer Policy

Flask-WTF برای تمام درخواست‌های تغییردهنده CSRF Token بررسی می‌کند.

چون برنامه روی HTTPS اجرا می‌شود، Referrer Policy مربوط به Nginx از:

```text
no-referrer
```

به:

```text
same-origin
```

تغییر می‌کند تا Browser برای Formهای Same-origin، Referer لازم برای
بررسی سخت‌گیرانه CSRF را ارسال کند.

## Forwarded Headers

Nginx پس از اعتبارسنجی IPهای ابر آروان، مقدار Client IP را در
`$remote_addr` قرار می‌دهد. سپس Backend فقط یک مقدار پاک‌سازی‌شده دریافت
می‌کند:

```nginx
proxy_set_header X-Forwarded-For $remote_addr;
```

Flask از `ProxyFix` با تعداد Proxy مشخص استفاده می‌کند.

## Account Lockout

مقادیر پیش‌فرض:

```text
AUTH_MAX_FAILED_ATTEMPTS=5
AUTH_LOCKOUT_MINUTES=15
```

بعد از پنج تلاش ناموفق، حساب برای ۱۵ دقیقه قفل می‌شود. پاسخ Login عمداً
مشخص نمی‌کند Username وجود دارد، غیرفعال است یا قفل شده است.

## ساخت Admin با Ansible

Automation:

1. Password تصادفی را روی Controller ایجاد یا بازیابی می‌کند.
2. Password را با Permission محدود به Origin منتقل می‌کند.
3. `admin-bootstrap` را به‌صورت One-shot اجرا می‌کند.
4. جدول `users` را ایجاد می‌کند.
5. Password را Hash می‌کند.
6. کاربر `admin` را ایجاد یا به‌روزرسانی می‌کند.
7. Backend و Nginx را Recreate می‌کند.
8. Login، Session، CSRF و Logout را تست می‌کند.

## تست دستی

ابتدا Basic Auth مربوط به Nginx را وارد کنید. سپس صفحه زیر نمایش داده
می‌شود:

```text
https://nhref.ir/login
```

Credentials اپلیکیشن:

```bash
cat \
  08_ansible_automation/public/app_auth/generated_app_admin_credentials.txt
```

## Verification

فایل:

```text
08_ansible_automation/public/app_auth/app_auth_verification.txt
```

نتیجه موفق:

```text
Overall layered authentication verification: PASSED
```

Verification این موارد را بررسی می‌کند:

- Origin TLS
- Health Endpoint
- دریافت `401` بدون Nginx Basic Auth
- نمایش فرم Flask Login با Basic Auth
- وجود CSRF Token
- ورود موفق
- دسترسی به Dashboard
- Logout با POST و CSRF
- Redirect مجدد به Login پس از Logout

## مرحله بعد

بعد از تأیید Login داخلی:

1. Basic Auth از Nginx حذف می‌شود.
2. فایل `htpasswd` و Password قدیمی Rotate یا حذف می‌شوند.
3. Verification فقط Login داخل Flask را بررسی می‌کند.
4. در صورت نیاز مدیریت User، تغییر Password و Roleها اضافه می‌شود.
