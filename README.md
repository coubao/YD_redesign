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

