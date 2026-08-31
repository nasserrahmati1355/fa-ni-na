# مرحله ۲ مهاجرت Authentication

## هدف

Login داخل Flask اضافه می‌شود، ولی Basic Authentication موجود در Nginx
موقتاً فعال باقی می‌ماند.

جریان فعلی بعد از Deploy:

```text
Basic Auth popup
      ↓
Flask Login page
      ↓
SEO Auditor dashboard
```

## پیش‌نیاز قطعی

مرحله Origin TLS باید کامل شده باشد:

```text
Overall end-to-end TLS verification: PASSED
```

همچنین در ابر آروان:

```text
Origin Protocol: HTTPS
Origin Port: 443
```

## فایل‌های این مرحله

```text
04_docker/
├── Dockerfile
├── .dockerignore
├── .env.example
├── docker-compose.yml
├── app/
│   ├── auth.py
│   ├── bootstrap_admin.py
│   ├── hello.py
│   ├── requirements.txt
│   └── templates/
│       ├── base.html
│       ├── login.html
│       ├── csrf_error.html
│       └── index.html
├── scripts/
│   └── init_local_auth.sh
└── tests/
    └── test_auth.py

08_ansible_automation/public/app_auth/
├── .gitignore
├── requirements.yml
├── deploy_app_auth.yml
├── verify_app_auth.yml
├── site_deploy_app_auth.yml
├── site_verify_app_auth.yml
├── run_deploy_app_auth.sh
├── run_verify_app_auth.sh
├── vars/
│   └── app_auth.yml
└── templates/
    └── docker-compose.app-auth-origin-tls.yml.j2
```

## ۱. بررسی Syntax

```bash
cd ~/naserrahmati_kubernetes_02/02_ansible_setup

ansible-galaxy collection install \
  -r ../08_ansible_automation/public/app_auth/requirements.yml

ansible-playbook \
  -i inventories/public.ini \
  ../08_ansible_automation/public/app_auth/site_deploy_app_auth.yml \
  --syntax-check
```

## ۲. اجرای Deployment

```bash
cd ~/naserrahmati_kubernetes_02

chmod +x \
  08_ansible_automation/public/app_auth/run_deploy_app_auth.sh

./08_ansible_automation/public/app_auth/run_deploy_app_auth.sh
```

در Prompt، رمز `sudo` کاربر `rahmati` روی Ubuntu را وارد کنید.

اگر SSH با Password است:

```bash
ASK_SSH_PASSWORD=1 \
./08_ansible_automation/public/app_auth/run_deploy_app_auth.sh
```

خروجی موفق:

```text
unreachable=0
failed=0
Nginx Basic Auth remains active and Flask application login works.
```

## ۳. مشاهده Credentials اپلیکیشن

```bash
cat \
  08_ansible_automation/public/app_auth/generated_app_admin_credentials.txt
```

نمونه:

```text
URL=https://nhref.ir/login
Username=admin
Password=<generated-password>
```

این Credential با Credential مربوط به Nginx Basic Auth متفاوت است.

## ۴. ورود با Browser

1. `https://nhref.ir` را باز کنید.
2. در Popup اول، Credential مربوط به `seo-admin` را وارد کنید.
3. در صفحه Login اپلیکیشن، Credential مربوط به `admin` را وارد کنید.
4. Dashboard نمایش داده می‌شود.
5. Logout داخل اپلیکیشن با دکمه «خروج» انجام می‌شود.

## ۵. Verification مستقل

```bash
cd ~/naserrahmati_kubernetes_02

chmod +x \
  08_ansible_automation/public/app_auth/run_verify_app_auth.sh

./08_ansible_automation/public/app_auth/run_verify_app_auth.sh
```

نتیجه مطلوب:

```text
Overall layered authentication verification: PASSED
```

گزارش:

```text
08_ansible_automation/public/app_auth/app_auth_verification.txt
```

## تست محلی اختیاری

```bash
cd ~/naserrahmati_kubernetes_02/04_docker

./scripts/init_local_auth.sh

cp -n .env.example .env

docker compose \
  --env-file .env \
  -f docker-compose.yml \
  build backend

docker compose \
  --env-file .env \
  -f docker-compose.yml \
  up -d --wait --wait-timeout 300 db backend proxy

docker compose \
  --env-file .env \
  -f docker-compose.yml \
  --profile tools \
  run --rm --no-deps admin-bootstrap
```

آدرس محلی:

```text
http://127.0.0.1:8080/login
```

چون تست محلی HTTP است، `.env.example` مقدار زیر را دارد:

```text
SESSION_COOKIE_SECURE=false
```

روی Production این مقدار در Template انسیبل `true` باقی می‌ماند.

## اجرای تست‌های واحد داخل Image

```bash
docker run \
  --rm \
  --entrypoint python \
  --volume "$PWD/app:/app-under-test:ro" \
  --volume "$PWD/tests:/tests:ro" \
  --env PYTHONPATH=/app-under-test \
  nginx-flask-mysql-backend:1.2 \
  -m unittest discover -s /tests -v
```

## Secretها

این فایل‌ها نباید Commit شوند:

```text
04_docker/secrets/db_password.txt
04_docker/secrets/flask_secret_key.txt
04_docker/secrets/app_admin_password.txt

08_ansible_automation/public/app_auth/.secrets/
08_ansible_automation/public/app_auth/generated_app_admin_credentials.txt
```

## نکته درباره Nginx

Basic Auth عمداً حذف نشده است. Configuration فقط برای سازگاری CSRF این
تغییر را دریافت می‌کند:

```text
Referrer-Policy: no-referrer
→
Referrer-Policy: same-origin
```

همچنین فقط Real IP پاک‌سازی‌شده توسط Nginx به Flask منتقل می‌شود.

## اجرای Automation قدیمی Public

تا زمان ادغام کامل این Stage در `public/site_public.yml`، اجرای Automation
قدیمی ممکن است Backend نسخه قبلی یا Compose قبلی را Deploy کند. پس از آن
باید Stageهای زیر دوباره اجرا شوند:

```text
origin_tls/run_enable_origin_tls.sh
app_auth/run_deploy_app_auth.sh
```

## Git

```bash
git add \
  04_docker \
  08_ansible_automation/public/app_auth \
  08_ansible_automation/public/templates/10-seo-auditor.conf.j2 \
  08_ansible_automation/public/origin_tls/templates/10-seo-auditor-acme.conf.j2 \
  08_ansible_automation/public/origin_tls/templates/10-seo-auditor-origin-tls.conf.j2 \
  09_documentation/features/application_authentication.md

git commit -m \
  "feat(auth): add Flask session authentication"

git push
```
