# مرحله ۱ مهاجرت احراز هویت — فعال‌سازی HTTPS تا Origin

## هدف

این مرحله ارتباط زیر را ایجاد می‌کند:

```text
Browser
   |
   | HTTPS
   v
ArvanCloud Edge
   |
   | HTTPS :443
   v
Ubuntu Origin
   |
   v
Nginx Container -> Flask SEO Auditor -> MariaDB
```

Basic Authentication فعلی در این مرحله حذف نمی‌شود. ابتدا مسیر TLS سرتاسری
ایمن می‌شود و در مرحله بعد Login داخل اپلیکیشن اضافه خواهد شد.

## پیش‌نیاز پنل آروان

در زمان اجرای `run_enable_origin_tls.sh` تنظیم Origin آروان باید همچنان باشد:

```text
Origin protocol: HTTP
Origin port: 80
```

بعد از موفقیت Playbook و Direct Origin Test آن را به این مقادیر تغییر دهید:

```text
Origin protocol: HTTPS
Origin port: 443
```

## پیش‌نیاز Firewall

قبل از اجرا، پورت TCP شماره `443` را در Firewall یا Security Group
ارائه‌دهنده VPS باز کنید.

برای تست اولیه می‌توانید آن را موقتاً عمومی باز کنید. پس از موفقیت کامل،
دسترسی Origin را به CIDRهای آروان و IP مدیریتی خود محدود کنید.

Playbook پورت `443` را در UFW نیز باز می‌کند.

## فایل‌های ایجادشده

```text
08_ansible_automation/public/origin_tls/
├── .gitignore
├── README.md
├── requirements.yml
├── site_enable_origin_tls.yml
├── enable_origin_tls.yml
├── site_verify_after_arvan.yml
├── verify_after_arvan.yml
├── run_enable_origin_tls.sh
├── run_verify_after_arvan.sh
├── vars/
│   └── origin_tls.yml
└── templates/
    ├── docker-compose.origin-tls.yml.j2
    ├── 10-seo-auditor-acme.conf.j2
    ├── 10-seo-auditor-origin-tls.conf.j2
    └── reload-nginx-after-renew.sh.j2
```

## مرحله A — بررسی Syntax

```bash
cd ~/naserrahmati_kubernetes_02/02_ansible_setup

ansible-galaxy collection install \
  -r ../08_ansible_automation/public/origin_tls/requirements.yml

ansible-playbook \
  -i inventories/public.ini \
  ../08_ansible_automation/public/origin_tls/site_enable_origin_tls.yml \
  --syntax-check
```

## مرحله B — صدور Certificate و فعال‌سازی HTTPS روی Origin

```bash
cd ~/naserrahmati_kubernetes_02

chmod +x \
  08_ansible_automation/public/origin_tls/run_enable_origin_tls.sh

./08_ansible_automation/public/origin_tls/run_enable_origin_tls.sh
```

این Playbook:

1. Certbot را با Snap نصب می‌کند.
2. پورت 443 را در UFW باز می‌کند.
3. ACME Webroot را ایجاد می‌کند.
4. مسیر Challenge را مستقیم و از طریق آروان تست می‌کند.
5. Certificate معتبر Let's Encrypt برای `nhref.ir` می‌گیرد.
6. Certificate را Read-only داخل Nginx Container Mount می‌کند.
7. Nginx را روی پورت‌های 80 و 443 اجرا می‌کند.
8. Direct Origin HTTPS را با SNI صحیح تست می‌کند.
9. Renewal Hook را نصب می‌کند.
10. `certbot renew --dry-run` را اجرا می‌کند.

خروجی موفق:

```text
Direct Origin TLS is ready.
```

گزارش:

```text
08_ansible_automation/public/origin_tls/origin_tls_enable_report.txt
```

## مرحله C — تغییر پنل آروان

پس از موفق‌شدن مرحله B:

```text
CDN -> nhref.ir -> Origin settings
```

مقادیر را تغییر دهید:

```text
Protocol: HTTPS
Port: 443
```

Host Header باید همان `nhref.ir` باقی بماند.

در این مرحله Redirect عمومی HTTP به HTTPS همچنان روی آروان باقی می‌ماند.

## مرحله D — اثبات ارتباط HTTPS آروان تا Origin

```bash
cd ~/naserrahmati_kubernetes_02

chmod +x \
  08_ansible_automation/public/origin_tls/run_verify_after_arvan.sh

./08_ansible_automation/public/origin_tls/run_verify_after_arvan.sh
```

Verification مسیر زیر را تست می‌کند:

```text
https://nhref.ir/origin-tls-health
```

این Route فقط در Server Block پورت 443 روی Origin وجود دارد. بنابراین پاسخ
`origin-tls-ok` اثبات می‌کند آروان درخواست را از طریق HTTPS به Origin
فرستاده است.

نتیجه موفق:

```text
Overall end-to-end TLS verification: PASSED
```

گزارش:

```text
08_ansible_automation/public/origin_tls/origin_tls_verification.txt
```

## تست دستی Direct Origin HTTPS

```bash
curl \
  --resolve nhref.ir:443:185.192.114.171 \
  -I \
  https://nhref.ir/
```

با فعال بودن Basic Auth، پاسخ مورد انتظار:

```text
HTTP/1.1 401 Unauthorized
```

این پاسخ نشان می‌دهد Certificate، SNI و Nginx Origin درست کار می‌کنند.

## نکته مهم درباره Deploymentهای بعدی

فایل Compose و Nginx روی سرور مقصد در این مرحله TLS-aware می‌شوند. تا زمانی
که Templateهای اصلی `public/` نیز با این مرحله ادغام نشده‌اند، اجرای مجدد
`public/site_public.yml` ممکن است Configuration HTTP-only را روی Origin
برگرداند.

پس بعد از هر اجرای کامل `site_public.yml`، فایل زیر را نیز اجرا کنید:

```bash
./08_ansible_automation/public/origin_tls/run_enable_origin_tls.sh
```

در مرحله بعدی مهاجرت Authentication، Templateهای اصلی با Origin TLS
یکپارچه خواهند شد.

## Git

فایل‌های این پوشه را Commit کنید:

```bash
git add \
  08_ansible_automation/public/origin_tls

git commit -m \
  "feat(tls): enable HTTPS between ArvanCloud and origin"

git push
```

گزارش‌های Runtime توسط `.gitignore` Commit نمی‌شوند.
