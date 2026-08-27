# توسعه MVP بررسی سئوی سایت

## هدف

این توسعه، صفحه نمونه Blog را به یک ابزار کوچک بررسی فنی سئو تبدیل می‌کند. کاربر یک URL وارد می‌کند و برنامه تعداد محدودی از صفحات داخلی همان Host را Crawl می‌کند.

## قابلیت‌ها

- دریافت URL از طریق فرم وب فارسی و RTL
- Crawl ترتیبی حداکثر ۲۵ صفحه داخلی
- شناسایی پاسخ‌های `404` و سایر خطاهای HTTP
- شناسایی صفحات بدون `H1`
- شناسایی صفحات دارای بیش از یک `H1`
- شناسایی نبودن `Title`
- گزارش طول کوتاه یا بلند Title بر اساس معیار داخلی ابزار
- شناسایی نبودن Meta Description
- گزارش طول کوتاه یا بلند Meta Description بر اساس معیار داخلی ابزار
- شناسایی نبودن Canonical
- شناسایی `noindex`
- نمایش زمان پاسخ هر URL
- نمایش صفحه‌ای که لینک از آن کشف شده است
- ذخیره خلاصه آخرین بررسی‌ها در MariaDB
- Health endpoint مستقل در `/health`

## محدودیت‌های عمدی MVP

- فقط لینک‌های داخلی همان Host بررسی می‌شوند؛ لینک‌های خارجی Crawl نمی‌شوند.
- JavaScript اجرا یا Render نمی‌شود.
- تعداد صفحات، حجم HTML، Redirect و Timeout محدود شده‌اند.
- معیارهای طول Title و Meta Description، قواعد داخلی این ابزار هستند و قانون قطعی موتور جستجو محسوب نمی‌شوند.
- این نسخه برای Lab و بررسی سایت‌های تحت مالکیت یا دارای مجوز است.
- برای انتشار عمومی باید Authentication، Rate Limiting، Queue، Egress Policy و حفاظت قوی‌تر در برابر DNS Rebinding اضافه شود.

## کنترل‌های امنیتی ورودی URL

- فقط Schemeهای HTTP و HTTPS
- فقط پورت‌های 80 و 443
- عدم پذیرش URL دارای Username یا Password
- عدم پذیرش IP مستقیم
- رد دامنه‌ای که به IP خصوصی، Loopback، Link-local یا Reserved Resolve شود
- اعتبارسنجی مقصد هر Redirect
- غیرفعال‌کردن Proxyهای Environment در Requests
- محدودیت ۲ مگابایت برای هر HTML
- محدودیت ۵ Redirect
- Crawl ترتیبی با Delay کوتاه

## فایل‌های تغییرکرده

```text
04_docker/
├── Dockerfile
├── .dockerignore
├── .env.example
├── docker-compose.yml
├── app/
│   ├── hello.py
│   ├── seo_auditor.py
│   ├── requirements.txt
│   └── templates/
│       └── index.html
├── nginx/
│   └── default.conf
└── tests/
    └── test_seo_auditor.py

08_ansible_automation/
├── deploy_app.yml
├── app_vars.yml
├── verify.yml
└── templates/
    ├── app.env.j2
    ├── docker-compose.yml.j2
    └── nginx.conf.j2
```

## اعمال فایل‌ها روی پروژه

ابتدا Branch جدید بسازید:

```bash
cd ~/naserrahmati_kubernetes_02

git status

git switch -c feature/seo-auditor
```

فایل ZIP را در یک پوشه موقت استخراج کنید و سپس فایل‌ها را روی پروژه کپی کنید:

```bash
mkdir -p /tmp/seo-auditor-mvp

unzip seo_auditor_mvp.zip \
  -d /tmp/seo-auditor-mvp

cp -a \
  /tmp/seo-auditor-mvp/seo_auditor_mvp/04_docker/. \
  ~/naserrahmati_kubernetes_02/04_docker/

cp -a \
  /tmp/seo-auditor-mvp/seo_auditor_mvp/08_ansible_automation/. \
  ~/naserrahmati_kubernetes_02/08_ansible_automation/
```

این عملیات فایل `.env` و Password واقعی دیتابیس را جایگزین نمی‌کند؛ آن فایل‌ها در بسته وجود ندارند.

## تست واحد

روی Controller:

```bash
cd ~/naserrahmati_kubernetes_02/04_docker

python3 -m unittest discover \
  -s tests \
  -v
```

خروجی مورد انتظار:

```text
Ran 4 tests
OK
```

## تست Local Docker

فایل `.env` موجود را نگه دارید. در صورت نیاز متغیرهای جدید را از `.env.example` به آن اضافه کنید:

```bash
cd ~/naserrahmati_kubernetes_02/04_docker

cp .env .env.backup
```

Permission فایل Secret:

```bash
sudo chown root:10001 secrets/db_password.txt
sudo chmod 0640 secrets/db_password.txt
```

اعتبارسنجی Compose:

```bash
docker compose \
  --env-file .env \
  -f docker-compose.yml \
  config --quiet
```

Build:

```bash
docker compose \
  --env-file .env \
  -f docker-compose.yml \
  build \
  --no-cache \
  backend
```

اجرا:

```bash
docker compose \
  --env-file .env \
  -f docker-compose.yml \
  up \
  --detach \
  --wait \
  --wait-timeout 300
```

بررسی:

```bash
docker compose \
  --env-file .env \
  -f docker-compose.yml \
  ps --all

curl -i http://127.0.0.1:8080/health
curl -i http://127.0.0.1:8080/
```

خروجی Health:

```json
{"status":"ok"}
```

صفحه اصلی باید فرم «بررسی فنی سئوی سایت» را نمایش دهد.

## استقرار با Ansible

بررسی Syntax:

```bash
cd ~/naserrahmati_kubernetes_02/02_ansible_setup

ansible-playbook \
  -i inventory \
  ../08_ansible_automation/site.yml \
  --syntax-check
```

اجرای کامل:

```bash
set -o pipefail

ansible-playbook \
  -i inventory \
  ../08_ansible_automation/site.yml \
  --ask-become-pass \
  -v \
  2>&1 | tee ../08_ansible_automation/playbook_output.txt
```

خروجی موفق:

```text
unreachable=0
failed=0
```

تست از Controller:

```bash
curl -k -I https://myapp.test/
curl -k https://myapp.test/ | grep -F "SEO Auditor"
```

## Commit و Push

ابتدا تغییرات را بررسی کنید:

```bash
cd ~/naserrahmati_kubernetes_02

git status --short

git diff --stat
```

فایل‌های این قابلیت را Stage کنید:

```bash
git add \
  04_docker/Dockerfile \
  04_docker/.dockerignore \
  04_docker/.env.example \
  04_docker/docker-compose.yml \
  04_docker/app \
  04_docker/nginx/default.conf \
  04_docker/tests \
  08_ansible_automation/deploy_app.yml \
  08_ansible_automation/app_vars.yml \
  08_ansible_automation/verify.yml \
  08_ansible_automation/templates/app.env.j2 \
  08_ansible_automation/templates/docker-compose.yml.j2 \
  08_ansible_automation/templates/nginx.conf.j2
```

اطمینان از عدم Stage شدن Secret:

```bash
git diff --cached --name-only | \
  grep -E '(^|/)(\.env|db_password\.txt)$|\.(key|pem|p12|pfx)$' \
  && echo "ERROR: secret staged" \
  || echo "OK: no secret staged"
```

Commit:

```bash
git commit -m \
  "feat(app): add limited SEO audit crawler"
```

قبل از Push اتصال GitHub را بررسی کنید:

```bash
ssh -T git@github.com
```

Push Branch:

```bash
git push -u origin feature/seo-auditor
```

پس از Review و تست، Branch را در `main` Merge کنید.

## Rollback سریع

در صورت نیاز:

```bash
git switch main

git branch -D feature/seo-auditor
```

برای بازگرداندن Deployment به آخرین Commit موجود در `main`، فایل‌های همان Commit را Deploy کرده و `site.yml` را دوباره اجرا کنید.
