"""Explicit administration commands. None run during normal website startup."""

import getpass
import json
import os
from pathlib import Path

import click
from flask import current_app
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from .importer import import_master, preview, rollback_import
from .models import User
from .storage import database_url, session as db_session


def alembic_config():
    from alembic.config import Config
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / 'delivery' / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'delivery' / 'migrations'))
    url = database_url()
    if not url:
        raise click.ClickException('Set DELIVERY_DATABASE_URL before running migrations')
    config.set_main_option('sqlalchemy.url', url.replace('%', '%%'))
    return config


def ensure_nonproduction():
    if os.environ.get('DELIVERY_ENV', '').lower() == 'production':
        raise click.ClickException('Production writes require a separate reviewed release procedure')


def register_commands(app):
    @app.cli.command('delivery-db-upgrade')
    def db_upgrade():
        from alembic import command
        ensure_nonproduction()
        command.upgrade(alembic_config(), 'head')
        click.echo('Delivery database upgraded')

    @app.cli.command('delivery-db-check')
    def db_check():
        from alembic import command
        command.check(alembic_config())
        click.echo('Delivery schema matches migration head')

    @app.cli.command('delivery-create-admin')
    @click.argument('username')
    def create_admin(username):
        ensure_nonproduction()
        secret = current_app.config.get('SECRET_KEY', '')
        if len(secret) < 32 or secret == 'change-me-in-production':
            raise click.ClickException('Set a strong SECRET_KEY before creating accounts')
        username = username.strip().lower()
        if not username or len(username) > 120:
            raise click.ClickException('Invalid username')
        password = getpass.getpass('New admin password (12+ characters): ')
        if len(password) < 12:
            raise click.ClickException('Password must have at least 12 characters')
        db = db_session()
        if db.scalar(select(User).where(User.username == username)):
            raise click.ClickException('Username already exists')
        db.add(User(username=username, role='admin', password_hash=generate_password_hash(password)))
        db.commit()
        click.echo('Admin created')

    @app.cli.command('delivery-preview')
    @click.argument('sources', nargs=-1, type=click.Path(exists=True, path_type=Path))
    @click.option('--report', type=click.Path(path_type=Path), help='Write a non-PII JSON summary')
    def preview_command(sources, report):
        if not sources:
            raise click.ClickException('Provide at least one XLSX or V0.2 HTML source')
        result = preview(sources)
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        click.echo(rendered)
        if report:
            report.write_text(rendered + '\n', encoding='utf-8')

    @app.cli.command('delivery-import-master')
    @click.argument('source', type=click.Path(exists=True, path_type=Path))
    @click.option('--sha256', required=True, help='SHA-256 from the read-only preview')
    def import_command(source, sha256):
        ensure_nonproduction()
        if source.suffix.lower() != '.xlsx':
            raise click.ClickException('Only a reviewed V1.1 master XLSX can be imported')
        batch_id, students, tasks, templates = import_master(db_session(), source, sha256)
        click.echo(f'Import batch {batch_id}: {students} students, {tasks} tasks, {templates} templates pending review')

    @app.cli.command('delivery-rollback-import')
    @click.argument('batch_id', type=int)
    def rollback_command(batch_id):
        ensure_nonproduction()
        rollback_import(db_session(), batch_id)
        click.echo(f'Import batch {batch_id} rolled back')
