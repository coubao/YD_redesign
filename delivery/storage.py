"""A dedicated engine keeps delivery data out of the website's SQLite database."""

import os
from pathlib import Path

from flask import current_app, g
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker


_engines = {}


def database_url():
    configured = current_app.config.get('DELIVERY_DATABASE_URL') or os.environ.get('DELIVERY_DATABASE_URL')
    if configured:
        return configured
    if current_app.config.get('TESTING') or current_app.debug:
        local_db = Path(current_app.instance_path) / 'delivery_dev.db'
        return f'sqlite:///{local_db}'
    return None


def engine():
    url = database_url()
    if not url:
        raise RuntimeError('DELIVERY_DATABASE_URL must be configured for the delivery system')
    if url not in _engines:
        connect_args = {'check_same_thread': False} if url.startswith('sqlite:') else {}
        value = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
        if url.startswith('sqlite:'):
            @event.listens_for(value, 'connect')
            def enable_foreign_keys(connection, _record):
                connection.execute('PRAGMA foreign_keys=ON')
        _engines[url] = value
    return _engines[url]


def session() -> Session:
    if 'delivery_session' not in g:
        g.delivery_session = sessionmaker(bind=engine(), expire_on_commit=False)()
    return g.delivery_session


def close_session(_error=None):
    value = g.pop('delivery_session', None)
    if value:
        value.close()
