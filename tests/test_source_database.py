from datetime import datetime
import os
from uuid import UUID

import pytest
from services.mod_sync import SteamSource
from sqlalchemy import text
from sqlalchemy.engine import make_url

ITEM = '2749712324'
ASSET = 'f6cfde86-0c07-420c-a232-7cd50a9de692'
DEFAULT = 'a01952e3-91f2-4d71-9cb4-e4e38a3f800c'
EPOCH = 1795178181
BUILD = datetime(2026, 11, 20, 12, 36, 21)
SOURCE = SteamSource(f'steam/{ITEM}/source/{"a"*64}.rwmod', 'a'*64, 300, EPOCH)


@pytest.fixture
def db(monkeypatch):
    # Use only an explicitly supplied, isolated disposable PostgreSQL database.
    url = os.getenv('STEAM_TEST_DATABASE_URL', '')
    if not url:
        pytest.skip('set STEAM_TEST_DATABASE_URL to a disposable PostgreSQL database')
    target = make_url(url)
    if target.host not in {'127.0.0.1', 'localhost', '::1'} or target.database != 'steam_source_test':
        pytest.fail('destructive fixtures require the local disposable steam_source_test database')
    monkeypatch.setenv('STEAM_WORKSHOP_SYNC_DATABASE_URL', url)
    import database as db

    if db.engine.url != target:
        pytest.fail('database engine was already bound to a different database')
    with db.engine.begin() as conn:
        conn.execute(text('''
            CREATE SCHEMA IF NOT EXISTS asset;
            CREATE TABLE IF NOT EXISTS public.files (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid, object_key text, name text,
              mime_type text, size integer, status text);
            CREATE TABLE IF NOT EXISTS asset.assets (
              id uuid PRIMARY KEY DEFAULT gen_random_uuid(), file_id uuid REFERENCES public.files(id),
              creator_id uuid, title jsonb, description jsonb, updated_at timestamp,
              created_at timestamp, published_at timestamp, version text, status text, visibility text,
              cover_file_id uuid, screenshot_file_ids uuid[], deleted_at timestamp, metadata jsonb);
            CREATE TABLE IF NOT EXISTS asset.asset_stats (asset_id uuid PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS public.steam_sync_status (
              workshop_item_id text PRIMARY KEY, asset_id uuid REFERENCES asset.assets(id), status text,
              error_message text, synced_at timestamp, created_at timestamp DEFAULT CURRENT_TIMESTAMP,
              updated_at timestamp DEFAULT CURRENT_TIMESTAMP);
        '''))
    db.init_db()
    with db.engine.begin() as conn:
        conn.execute(text('TRUNCATE public.steam_sync_status, asset.asset_stats, asset.assets, public.files, public.workshop_items'))
        conn.execute(text('''INSERT INTO public.workshop_items(id,url,title,coverview_url,author,author_profile,file_size,images,updated_at,synced_at)
            VALUES (:id, '', 'EK', '', '', '', 3978498, ARRAY[]::varchar[], :updated, CURRENT_TIMESTAMP)'''),
                     {'id': ITEM, 'updated': BUILD})
    return db


def seed_existing(db):
    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO public.files (id, object_key, size) VALUES (:id, 'steam-translated/current.rwmod', 5414332)"), {'id': DEFAULT})
        conn.execute(text('''INSERT INTO asset.assets (id, file_id, creator_id, metadata)
            VALUES (:asset, :default, :owner, jsonb_build_object('steam_workshop_id', :item, 'translated', true))'''),
                     {'asset': ASSET, 'default': DEFAULT, 'owner': db.STEAM_USER_ID, 'item': ITEM})
        conn.execute(text("INSERT INTO public.steam_sync_status (workshop_item_id, asset_id, status) VALUES (:id, :asset, 'syncing')"),
                     {'id': ITEM, 'asset': ASSET})


def test_atomic_publish_preserves_translated_default_and_reuses_source(db):
    seed_existing(db)
    item = db.get_workshop_item(ITEM)
    for _ in range(2):
        claim = db.claim_source(item, expected_asset_id=ASSET)
        assert db.commit_source(item, SOURCE, claim) == ASSET
    with db.engine.connect() as conn:
        pointer, metadata = conn.execute(text('SELECT file_id, metadata FROM asset.assets')).one()
        source_id, size = conn.execute(text('SELECT id,size FROM public.files WHERE object_key=:key'), {'key': SOURCE.object_key}).one()
        status, error = conn.execute(text('SELECT status,error_message FROM public.steam_sync_status')).one()
    assert pointer == UUID(DEFAULT)
    assert metadata['translated'] is True
    assert metadata['steam_source'] == {
        'file_id': str(source_id), 'sha256': SOURCE.sha256, 'object_key': SOURCE.object_key, 'steam_time_updated': EPOCH,
    }
    assert size == 300 and status == 'completed' and error is None


def test_publish_rolls_back_insert_when_asset_update_fails(db):
    seed_existing(db)
    item = db.get_workshop_item(ITEM)
    claim = db.claim_source(item, expected_asset_id=ASSET)
    with db.engine.begin() as conn:
        conn.execute(text("ALTER TABLE asset.assets ADD CONSTRAINT reject_source CHECK (NOT (metadata ? 'steam_source'))"))
    try:
        with pytest.raises(Exception, match='reject_source'):
            db.commit_source(item, SOURCE, claim)
        with db.engine.connect() as conn:
            assert conn.execute(text('SELECT count(*) FROM public.files')).scalar_one() == 1
            assert 'steam_source' not in conn.execute(text('SELECT metadata FROM asset.assets')).scalar_one()
            assert conn.execute(text('SELECT status FROM public.steam_sync_status')).scalar_one() == 'syncing'
    finally:
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE asset.assets DROP CONSTRAINT reject_source'))


def test_claim_retries_are_bounded_across_processes(db):
    item = db.get_workshop_item(ITEM)
    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO public.steam_sync_status (workshop_item_id,status) VALUES (:id,'pending')"), {'id': ITEM})
    for attempt in range(1, 4):
        assert db.get_pending_sync_items()[0].id == ITEM
        claim = db.claim_source(item)
        assert claim.attempt == attempt
        assert db.claim_source(item) is None
        db.fail_source(item, claim, 'test failure')
        assert db.get_pending_sync_items() == []
        with db.engine.begin() as conn:
            conn.execute(text("UPDATE public.steam_sync_status SET updated_at=updated_at-interval '2 hours'"))
    assert db.get_pending_sync_items() == []
    assert db.claim_source(item) is None


def test_stale_claim_cannot_publish_after_reclaim(db):
    item = db.get_workshop_item(ITEM)
    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO public.steam_sync_status (workshop_item_id,status) VALUES (:id,'pending')"), {'id': ITEM})
    first = db.claim_source(item)
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE public.steam_sync_status SET updated_at=updated_at-interval '2 hours'"))
    second = db.claim_source(item)
    assert second.attempt == 2
    with pytest.raises(RuntimeError, match='claim'):
        db.commit_source(item, SOURCE, first)
    assert db.commit_source(item, SOURCE, second)
    with db.engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM public.files')).scalar_one() == 1
        assert conn.execute(text('SELECT file_id FROM asset.assets')).scalar_one() == conn.execute(text('SELECT id FROM public.files')).scalar_one()


def test_exact_recovery_does_not_touch_other_queue_rows(db, capsys):
    seed_existing(db)
    import main

    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO public.steam_sync_status (workshop_item_id,status) VALUES ('123','pending')"))

    class Service:
        def sync_mod(self, item, *, upload):
            assert item.id == ITEM and upload is True
            return SOURCE

    assert main.run_one_source(Service(), ITEM, ASSET, apply=True) == 0
    assert SOURCE.sha256 in capsys.readouterr().out
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM public.steam_sync_status WHERE workshop_item_id='123'")).scalar_one() == 'pending'


def test_exact_recovery_dry_run_leaves_source_and_status_unmodified(db, capsys):
    seed_existing(db)
    import main

    class Service:
        def sync_mod(self, item, *, upload):
            assert item.id == ITEM and upload is False
            return SOURCE

    assert main.run_one_source(Service(), ITEM, ASSET, apply=False) == 0
    assert SOURCE.sha256 in capsys.readouterr().out
    with db.engine.connect() as conn:
        assert conn.execute(text('SELECT status FROM public.steam_sync_status')).scalar_one() == 'syncing'
        assert 'steam_source' not in conn.execute(text('SELECT metadata FROM asset.assets')).scalar_one()


def test_legacy_candidate_scan_reports_only_unpublished_hints_without_mutation(db):
    seed_existing(db)
    candidates = db.list_legacy_candidates(10)
    assert [(row['item_id'], row['asset_id'], row['status']) for row in candidates] == [(ITEM, ASSET, 'syncing')]
    assert db.list_legacy_candidates(10, after=ITEM) == []
    assert db.get_sync_status(ITEM)['status'] == 'syncing'


def test_final_crashed_claim_is_terminal_without_requeuing_legacy_rows(db):
    seed_existing(db)
    assert db.expire_final_source_claims() == 0
    with db.engine.begin() as conn:
        conn.execute(text("""UPDATE public.steam_sync_status SET error_message='source-v1 attempt=3; in progress',
                          updated_at=CURRENT_TIMESTAMP-interval '2 hours'"""))
    assert db.expire_final_source_claims() == 1
    assert db.get_sync_status(ITEM)['status'] == 'failed'
    assert db.get_pending_sync_items() == []
