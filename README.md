# استقرار خودکار اپلیکیشن وب با Docker و Ansible

## معرفی پروژه

این پروژه یک سناریوی کامل DevOps برای استقرار خودکار یک Web Application چندسرویسی است. اپلیکیشن اولیه از نمونه رسمی `docker/awesome-compose` با نام `nginx-flask-mysql` انتخاب شده و برای اجرای امن‌تر و قابل‌تکرار، ساختار Dockerfile، Docker Compose، Nginx، SSL/TLS و Playbookهای Ansible آن توسعه داده شده‌اند.

اجزای اصلی پروژه:

- **AlmaLinux Controller** برای نگهداری پروژه و اجرای Ansible
- **Ubuntu 22.04.5 LTS Target Server** برای اجرای سرویس‌های Production/Lab
- **Nginx Container** به‌عنوان Reverse Proxy و نقطه ورود HTTP/HTTPS
- **Flask + Gunicorn Container** به‌عنوان Backend
- **MariaDB Container** به‌عنوان Database
- **Docker Compose** برای مدیریت سرویس‌ها، Networkها، Volume و Secret
- **Ansible** برای آماده‌سازی سرور، انتقال فایل‌ها، Build، Run، Nginx، SSL و Verification
- **Self-Signed Certificate** برای فعال‌سازی HTTPS آزمایشی

## مشخصات محیط

| مورد | مقدار |
|---|---|
| Controller OS | AlmaLinux |
| Controller User | `naser` |
| Ansible Community | `14.3.1` |
| Ansible Core | `2.21.3` |
| Controller Python | `3.12.13` |
| Target OS | Ubuntu 22.04.5 LTS |
| Target Hostname | `local20054` |
| Target IP | `192.168.200.54` |
| Target SSH User | `rahmati` |
| Application Domain | `myapp.test` |
| Deployment Directory | `/opt/nginx-flask-mysql` |
| HTTP Port | `80` |
| HTTPS Port | `443` |
| Backend Port | `8000` داخلی |
| Database Port | `3306` داخلی |

## معماری کلی

```text
AlmaLinux Controller
        |
        | Ansible over SSH
        v
Ubuntu 22.04 Target Server
        |
        | Docker Compose
        v
+--------------------------------------------------+
|                    frontnet                      |
|                                                  |
|  Client --> Nginx :80/:443 --> Flask :8000      |
|                                  |               |
+----------------------------------|---------------+
                                   |
                                   | backnet
                                   v
                              MariaDB :3306
                                   |
                              Named Volume
```

## قابلیت‌های پیاده‌سازی‌شده

- Clone و بررسی پروژه از GitHub
- Dockerfile چندمرحله‌ای برای Backend
- اجرای Backend با Gunicorn
- اجرای Backend با کاربر Non-root و UID/GID ثابت `10001`
- استفاده از MariaDB با Named Volume
- جداسازی Networkهای `frontnet` و `backnet`
- عدم انتشار مستقیم پورت Backend و Database
- مدیریت Password دیتابیس با File-based Docker Secret
- Health Check برای Database، Backend و Nginx
- Nginx به‌صورت Container
- تنظیم Reverse Proxy Headerها
- Redirect از HTTP به HTTPS
- Self-Signed Certificate دارای SAN برای Domain و IP
- بازکردن پورت‌های `22`، `80` و `443` در UFW
- Automation کامل با Ansible
- Verification و ذخیره خروجی‌های اجرایی در فایل

## پیش‌نیازها

### روی AlmaLinux Controller

- دسترسی شبکه به سرور Ubuntu
- SSH Client
- Python 3.12
- `pipx`
- Ansible
- Git
- Docker Engine و Docker Compose برای تست محلی
- `curl`
- `openssl`

بررسی:

```bash
python3.12 --version
pipx --version
ansible --version
ansible-playbook --version
docker --version
docker compose version
git --version
curl --version
openssl version
```

### روی Ubuntu Target

در شروع فقط موارد زیر لازم‌اند:

- Ubuntu 22.04 LTS
- SSH
- Python 3
- کاربر دارای دسترسی `sudo`

سایر ابزارها توسط Ansible نصب و تنظیم می‌شوند.

## نصب Ansible روی Controller

```bash
sudo dnf install -y python3.12 python3.12-pip git openssh-clients

python3.12 -m pip install --user --upgrade pipx
python3.12 -m pipx ensurepath

export PATH="$HOME/.local/bin:$PATH"

pipx install \
  --python /usr/bin/python3.12 \
  --include-deps \
  ansible
```

بررسی:

```bash
ansible --version
ansible-community --version
```

## آماده‌سازی SSH

```bash
ssh-keygen -t ed25519
ssh-copy-id rahmati@192.168.200.54
ssh rahmati@192.168.200.54
```

روی Target بررسی کنید:

```bash
whoami
python3 --version
sudo -v
```

## اجرای مرحله آماده‌سازی سرور

```bash
cd ~/naserrahmati_kubernetes_02/02_ansible_setup

ansible-galaxy collection install -r requirements.yml

ansible -i inventory deployment_servers \
  -m ansible.builtin.ping \
  2>&1 | tee ping_test.txt

ansible -i inventory deployment_servers \
  -m ansible.builtin.setup \
  2>&1 | tee facts.txt
```

اجرای Playbook:

```bash
set -o pipefail

ansible-playbook \
  -i inventory \
  server_setup.yml \
  --ask-become-pass \
  2>&1 | tee playbook_output.txt
```

Verification:

```bash
ansible-playbook \
  -i inventory \
  verification.yml \
  --ask-become-pass \
  2>&1 | tee verification.txt
```

## تست محلی Docker

```bash
cd ~/naserrahmati_kubernetes_02/04_docker

docker compose \
  --env-file .env \
  -f docker-compose.yml \
  config --quiet

docker compose \
  --env-file .env \
  -f docker-compose.yml \
  build backend

docker compose \
  --env-file .env \
  -f docker-compose.yml \
  up -d --wait --wait-timeout 180
```

بررسی:

```bash
docker compose \
  --env-file .env \
  -f docker-compose.yml \
  ps --all

curl -i http://127.0.0.1:8080/
```

## استقرار نهایی با Ansible

Collectionهای مورد نیاز:

```bash
cd ~/naserrahmati_kubernetes_02/02_ansible_setup

ansible-galaxy collection install \
  -r ../08_ansible_automation/requirements.yml
```

بررسی Syntax:

```bash
ansible-playbook \
  -i inventory \
  ../08_ansible_automation/site.yml \
  --syntax-check
```

اجرای کامل:

```bash
cd ~/naserrahmati_kubernetes_02

chmod +x 08_ansible_automation/run_automation.sh
./08_ansible_automation/run_automation.sh
```

یا اجرای مستقیم:

```bash
cd ~/naserrahmati_kubernetes_02/02_ansible_setup

set -o pipefail

ansible-playbook \
  -i inventory \
  ../08_ansible_automation/site.yml \
  --ask-become-pass \
  -v \
  2>&1 | tee ../08_ansible_automation/playbook_output.txt
```

خروجی موفق در `PLAY RECAP`:

```text
unreachable=0
failed=0
```

## تنظیم Domain آزمایشی

روی AlmaLinux Controller:

```bash
echo "192.168.200.54 myapp.test" |
sudo tee -a /etc/hosts
```

بررسی:

```bash
getent hosts myapp.test
```

## استفاده و تست

### تست Redirect

```bash
curl -I http://myapp.test/
```

خروجی مورد انتظار:

```text
HTTP/1.1 301 Moved Permanently
Location: https://myapp.test/
```

### تست HTTPS

```bash
curl -k -I https://myapp.test/
```

خروجی مورد انتظار:

```text
HTTP/1.1 200 OK
```

### تست کامل

```bash
curl -k -L http://myapp.test/
```

نمونه پاسخ:

```html
<div>   Hello  Blog post #1</div>
<div>   Hello  Blog post #2</div>
<div>   Hello  Blog post #3</div>
<div>   Hello  Blog post #4</div>
```

### بررسی Containerها روی Target

```bash
ssh rahmati@192.168.200.54

cd /opt/nginx-flask-mysql

docker compose ps
docker compose logs --tail 100
docker compose exec -T proxy nginx -t
```

## Configuration

متغیرهای اصلی در فایل‌های زیر قرار دارند:

```text
02_ansible_setup/inventory
08_ansible_automation/app_vars.yml
08_ansible_automation/nginx_vars.yml
08_ansible_automation/templates/app.env.j2
08_ansible_automation/templates/docker-compose.yml.j2
08_ansible_automation/templates/nginx.conf.j2
```

متغیرهای مهم:

| متغیر | مقدار فعلی |
|---|---|
| `ansible_host` | `192.168.200.54` |
| `ansible_user` | `rahmati` |
| `deployment_dir` | `/opt/nginx-flask-mysql` |
| `application_domain` | `myapp.test` |
| `http_port` | `80` |
| `https_port` | `443` |
| `backend_port` | `8000` |
| `mariadb_database` | `example` |
| `backend_uid` | `10001` |
| `backend_gid` | `10001` |

## ساختار پروژه

```text
naserrahmati_kubernetes_02/
├── README.md
├── 01_environment/
│   ├── server_info.md
│   └── server_connection.txt
├── 02_ansible_setup/
│   ├── ansible.cfg
│   ├── inventory
│   ├── requirements.yml
│   ├── server_setup.yml
│   ├── verification.yml
│   ├── ping_test.txt
│   ├── facts.txt
│   ├── playbook_output.txt
│   └── verification.txt
├── 03_project_clone/
│   ├── awesome-compose/
│   ├── project_structure.txt
│   └── project_info.md
├── 04_docker/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── .env.example
│   ├── docker-compose.yml
│   ├── dockerfile_explanation.md
│   ├── compose_explanation.md
│   ├── build_log.txt
│   ├── container_status.txt
│   ├── test_results.txt
│   ├── app/
│   ├── nginx/
│   └── secrets/
├── 05_deployment/
├── 06_nginx/
├── 07_ssl/
├── 08_ansible_automation/
│   ├── automation_design.md
│   ├── deploy_app.yml
│   ├── app_vars.yml
│   ├── deploy_nginx.yml
│   ├── nginx_vars.yml
│   ├── verify.yml
│   ├── site.yml
│   ├── requirements.yml
│   ├── run_automation.sh
│   └── templates/
└── 09_documentation/
    ├── architecture.md
    ├── deployment_guide.md
    └── troubleshooting.md
```

## مدیریت سرویس‌ها

### مشاهده وضعیت

```bash
cd /opt/nginx-flask-mysql
docker compose ps
```

### مشاهده Logها

```bash
docker compose logs --no-color --tail 200
```

### Restart کردن Stack

```bash
docker compose restart
```

### توقف بدون حذف Volume

```bash
docker compose down
```

### اجرای مجدد

```bash
docker compose up -d --wait --wait-timeout 180
```

> از `docker compose down --volumes` فقط زمانی استفاده کنید که حذف کامل اطلاعات MariaDB موردنظر باشد.

## امنیت

- فایل Secret دیتابیس داخل Git ثبت نمی‌شود.
- Secret روی Target با `root:appcontainer` و Permission `0640` نگهداری می‌شود.
- Backend با UID/GID برابر `10001` اجرا می‌شود.
- Private Key مربوط به SSL با `root:root` و Permission `0600` نگهداری می‌شود.
- Database و Backend پورت عمومی ندارند.
- فقط Nginx پورت‌های `80` و `443` را Publish می‌کند.
- Network مربوط به Database با `internal: true` ایزوله شده است.
- Certificate فعلی Self-Signed و فقط مناسب Lab است.

## Troubleshooting سریع

### خطای دسترسی Docker Socket

```text
permission denied while trying to connect to the docker API
```

راه‌حل:

```bash
sudo usermod -aG docker "$USER"
exit
```

پس از Login مجدد:

```bash
docker ps
```

### Backend Unhealthy و Secret غیرقابل خواندن

بررسی:

```bash
docker compose exec -T backend id
sudo ls -ln secrets/db_password.txt
```

مقادیر مورد انتظار:

```text
Backend UID/GID: 10001
Secret owner/group: 0:10001
Secret mode: 0640
```

اصلاح:

```bash
sudo chown root:10001 secrets/db_password.txt
sudo chmod 0640 secrets/db_password.txt
```

### خطای `No such image: sha256:...`

Compose Plugin را روی Target ارتقا دهید:

```bash
sudo apt update
sudo apt install --only-upgrade docker-compose-plugin
docker compose version
```

در صورت باقی‌ماندن Containerهای قدیمی:

```bash
docker compose down --remove-orphans
docker compose up -d --build --wait --wait-timeout 180
```

Volume را حذف نکنید.

### هشدار Self-Signed Certificate

برای تست:

```bash
curl -k https://myapp.test/
```

در Production باید Certificate معتبر نصب شود.

## مستندات تکمیلی

- [معماری سیستم](09_documentation/architecture.md)
- [راهنمای استقرار](09_documentation/deployment_guide.md)
- [راهنمای رفع اشکال](09_documentation/troubleshooting.md)

## مستندات قابلیت‌ها

- [راهنمای قابلیت SEO Auditor](09_documentation/features/seo_auditor.md)
