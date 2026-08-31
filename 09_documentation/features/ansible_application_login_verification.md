# مرحله ۷ مهاجرت Authentication — Verification بر پایه Application Login

## هدف

تمام Verificationهای Ansible از Credential قدیمی Nginx Basic Auth مستقل می‌شوند و یک قرارداد مشترک برای Login داخل Flask به کار می‌برند.

## Entry Pointهای اصلاح‌شده

```text
08_ansible_automation/public/verify_public.yml
08_ansible_automation/public/origin_tls/verify_after_arvan.yml
08_ansible_automation/public/app_auth/verify_app_auth.yml
```

هر سه فایل از Task Set مشترک زیر استفاده می‌کنند:

```text
08_ansible_automation/public/app_auth/tasks/verify_application_login.yml
```

و جریان واقعی Login توسط این اسکریپت انجام می‌شود:

```text
08_ansible_automation/public/app_auth/scripts/verify_application_auth.sh
```

## کنترل‌های انجام‌شده

- عدم وجود `auth_basic` و `auth_basic_user_file` در Nginx فعال
- عدم وجود Mount فایل `htpasswd`
- Healthy بودن `db`، `backend` و `proxy`
- معتبر بودن Docker Compose و Nginx
- TLS آروان تا Origin
- TLS مستقیم Origin با SNI صحیح
- صفحه عمومی `/login` بدون Basic Auth
- Redirect کاربر واردنشده از `/` به `/login`
- رد شدن Login فاقد CSRF با Status 400
- Login صحیح با CSRF
- ایجاد Cookie نشست با `Secure`، `HttpOnly` و `SameSite=Lax`
- دسترسی به Dashboard با Session معتبر
- Logout دارای CSRF
- بی‌اعتبار شدن Session پس از Logout
- تطابق Session Lifetime و CSRF Lifetime فعال با Variables
- بررسی هر دو مسیر Public CDN و Direct Origin
- محدود بودن Rate Limit به `POST /audit`

## نتیجه معماری

```text
Nginx Basic Auth Verification: حذف‌شده
Flask Application Login Verification: فعال
Public CDN Path: تست‌شده
Direct Origin TLS Path: تست‌شده
```
