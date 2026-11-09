# YD Education Website

Flask website for Yingdong Education, including the home page, application services, study maps, offer gallery, guide pages, contact page, and ranking tools.

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:8080
```

## Production

Recommended production stack:

- Gunicorn for the Flask application
- Nginx as the reverse proxy and static file server
- systemd for process supervision
- HTTPS certificate configured in Nginx

Example Gunicorn command:

```bash
gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
```

## Project Structure

```text
app.py              Flask application
templates/         Jinja2 templates
static/            CSS, images, maps, offer images, QR code
requirements.txt   Python dependencies
instance/          Runtime SQLite database directory
```

Runtime database files under `instance/` are intentionally ignored by Git.

## Admin Access

All `/admin` routes require HTTP Basic authentication. Configure
`ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` in the production service
environment before deploying; without both values, admin routes return 503.
Create the hash with the production virtual environment's Werkzeug:

```bash
/var/www/vivy/.venv/bin/python -c 'from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass("Admin password: ")))'
```

Store the generated hash in a root-owned, mode 0600 systemd environment file
outside the repository. Do not put the plaintext password or hash in Git, shell
history, or screenshots. Keep HTTPS enabled because Basic authentication sends
credentials with each request. Both `/admin/bookings` and
`/admin/bookings/` serve the booking dashboard.

## Booking WeChat Notifications

New bookings can notify a WeCom group robot. Create a group containing the
service owner and Grace, add a group robot, then configure the webhook in the
systemd service:

```ini
Environment="BOOKING_WECHAT_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
Environment="BOOKING_WECHAT_MENTIONED_MOBILES=YOUR_MOBILE"
```

After changing the service file:

```bash
sudo systemctl daemon-reload
sudo systemctl restart vivy
```

The public WeChat API cannot send a message directly to an arbitrary personal
phone number or WeChat ID. Both recipients must be members of the configured
WeCom group (or later provide an official-account/WeCom application identity).
When no webhook is configured, the booking is still saved and the admin page
shows `微信提醒待配置`.
