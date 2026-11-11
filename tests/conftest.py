"""Shared pytest fixtures for hermetic database isolation."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import db as db_module


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirects SQLite engine and SessionLocal to a per-test temporary database."""
    db_file = tmp_path / "test_sysadmin.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # All backend modules access SQLite through backend.db helpers, isolating tests from root sysadmin_ai.db.
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSessionLocal)
    db_module.init_db()
    yield
    test_engine.dispose()
