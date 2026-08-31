# حذف Nginx Basic Auth

در این مرحله `auth_basic` و `auth_basic_user_file` از Nginx حذف می‌شوند و Login داخل Flask تنها لایه تعاملی احراز هویت خواهد بود.

```text
Browser -> ArvanCloud -> Nginx -> Flask Login -> Dashboard
```

Playbook سه مورد را کنترل می‌کند:

1. `nginx -T` فاقد `auth_basic` باشد.
2. Docker Compose دیگر فایل `htpasswd` را Mount نکند.
3. `/login` بدون Popup مرورگر باز شود و `/` برای کاربر بدون Session به `/login` Redirect شود.

فایل قدیمی `htpasswd` و Password محلی تا مرحله ۶ فقط برای Rollback نگهداری می‌شوند، اما دیگر توسط Container استفاده نمی‌شوند.
