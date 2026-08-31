# مرحله ۶ مهاجرت Authentication — پاک‌سازی Basic Auth قدیمی

## هدف

بعد از حذف `auth_basic` و Mount فایل `htpasswd` در مرحله ۵، فایل‌های Credential قدیمی دیگر کاربردی ندارند. مرحله ۶ آن‌ها را فقط پس از اثبات سلامت Login داخل Flask پاک می‌کند.

## فایل‌های حذف‌شده

روی Ubuntu Origin:

```text
/opt/seo-auditor/nginx/htpasswd
```

روی AlmaLinux Controller:

```text
08_ansible_automation/public/.secrets/basic_auth_password
08_ansible_automation/public/generated_basic_auth_credentials.txt
```

اگر پوشه زیر بعد از حذف Password خالی باشد، خود پوشه نیز حذف می‌شود:

```text
08_ansible_automation/public/.secrets/
```

## فایل‌هایی که حذف نمی‌شوند

```text
app_auth/.secrets/app_admin_password
generated_app_admin_credentials.txt
/opt/seo-auditor/secrets/flask_secret_key.txt
/opt/seo-auditor/secrets/app_admin_password.txt
/opt/seo-auditor/secrets/db_password.txt
/etc/letsencrypt/
MariaDB volume
users table
```

## کنترل‌های ایمنی پیش از حذف

Playbook فقط وقتی حذف را انجام می‌دهد که:

1. `enable_basic_auth` برابر `false` باشد.
2. `nginx -T` هیچ `auth_basic` نداشته باشد.
3. Compose و Container فعال هیچ Mount مربوط به `htpasswd` نداشته باشند.
4. HTTPS بین آروان و Origin سالم باشد.
5. Login، Session، CSRF و Logout داخل Flask موفق باشند.

## نتیجه

پس از این مرحله:

```text
Nginx Basic Auth: حذف‌شده
Flask Login: فعال
Session: فعال
CSRF: فعال
Origin TLS: فعال
```
