from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import subprocess
from types import SimpleNamespace
import zipfile

from botocore.exceptions import ClientError
import pytest
from services.mod_sync import ModSyncService


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv('STEAM_WORKSHOP_SYNC_APP_ID', '647960')
    monkeypatch.setenv('STEAM_WORKSHOP_SYNC_DOWNLOAD_DIR', str(tmp_path))
    return ModSyncService()


def test_empty_download_is_never_uploaded(service, tmp_path, monkeypatch):
    empty = tmp_path / 'empty'
    empty.mkdir()
    (empty / 'subdir').mkdir()
    @contextmanager
    def download(*_args, **_kwargs):
        yield empty

    monkeypatch.setattr(service, 'download_mod_with_steamcmd', download)

    def upload(*_args, **_kwargs):
        pytest.fail('empty download reached the object store')

    monkeypatch.setattr(service.asset_r2, 'put_immutable_source', upload, raising=False)
    assert not service.sync_mod(SimpleNamespace(id='2749712324', updated_at=datetime.fromtimestamp(123, timezone.utc)))


@pytest.mark.parametrize('outcome', ['ok', 'colored_success', 'colored_error', 'empty', 'partial', 'false_success', 'wrong_build'])
def test_steamcmd_requires_fresh_final_content(service, monkeypatch, outcome):
    def steamcmd(cmd, **_kwargs):
        from pathlib import Path

        root = Path(cmd[cmd.index('+force_install_dir') + 1]) / 'steamapps/workshop'
        path = root / ('downloads' if outcome == 'partial' else 'content') / '647960/2749712324'
        path.mkdir(parents=True)
        if outcome != 'empty':
            (path / 'mod-info.txt').write_text('[mod]\ntitle: EK\n')
        epoch = 123 if outcome != 'wrong_build' else 122
        (root / 'appworkshop_647960.acf').write_text(
            f'"AppWorkshop" {{ "WorkshopItemsInstalled" {{ "2749712324" {{ "timeupdated" "{epoch}" }} }} }}'
        )
        output = f'Success. Downloaded item 2749712324 to "{path}" (18 bytes)\n'
        if outcome in {'colored_success', 'colored_error'}:
            output = '\x1b[0m' + output
        if outcome == 'colored_error':
            output += '\x1b[31mERROR!\x1b[0m another error from SteamCMD.\n'
        if outcome == 'false_success':
            output = 'ERROR! Download item 2749712324 failed (Failure).\n'
        return subprocess.CompletedProcess(cmd, 0, output, '')

    monkeypatch.setattr(subprocess, 'run', steamcmd)
    with service.download_mod_with_steamcmd('2749712324', steam_time_updated=123) as path:
        assert bool(path) == (outcome in {'ok', 'colored_success'})
        if path:
            assert (path / 'mod-info.txt').is_file()


def test_upload_returns_verified_identity_from_real_archive(service, monkeypatch):
    @contextmanager
    def download(*_args, **_kwargs):
        path = service.download_dir / 'mod'
        path.mkdir()
        (path / 'mod-info.txt').write_bytes(b'[mod]\ntitle: EK\n')
        yield path

    def upload(path, key, sha256):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha256
        assert key == f'steam/2749712324/source/{sha256}.rwmod'
        with zipfile.ZipFile(path) as archive:
            assert archive.read('mod-info.txt') == b'[mod]\ntitle: EK\n'
        return True

    monkeypatch.setattr(service, 'download_mod_with_steamcmd', download)
    monkeypatch.setattr(service.asset_r2, 'put_immutable_source', upload, raising=False)
    source = service.sync_mod(SimpleNamespace(
        id='2749712324', title='EK', updated_at=datetime.fromtimestamp(123, timezone.utc)
    ))
    assert source.steam_time_updated == 123
    assert source.size > 22


@pytest.mark.parametrize('existing,valid', [(False, True), (True, True), (True, False)])
def test_object_put_is_create_only_and_read_back(service, tmp_path, existing, valid):
    data = b'archive'
    path = tmp_path / 'mod.rwmod'
    path.write_bytes(data)
    calls = []

    def put_object(**kw):
        assert kw['IfNoneMatch'] == '*'
        assert kw['Body'].read() == data
        calls.append('put')
        if existing:
            raise ClientError({'Error': {'Code': 'PreconditionFailed'}, 'ResponseMetadata': {'HTTPStatusCode': 412}}, 'PutObject')

    def get_object(**_kw):
        calls.append('get')
        return {'Body': BytesIO(data if valid else b'corrupt'), 'ContentLength': len(data)}

    service.asset_r2._client = SimpleNamespace(put_object=put_object, get_object=get_object)
    assert service.asset_r2.put_immutable_source(path, 'key', hashlib.sha256(data).hexdigest()) == valid
    assert calls == ['put', 'get']


@pytest.mark.parametrize('valid', [True, False])
def test_legacy_empty_zip_check_reads_actual_object(service, valid):
    def head_object(**_kw):
        return {'ContentLength': 22, 'ETag': '"etag"'}

    def get_object(**kw):
        assert kw['IfMatch'] == '"etag"'
        data = b'PK\x05\x06' + bytes(18) if valid else bytes(22)
        return {'Body': BytesIO(data), 'ContentLength': 22}

    service.asset_r2._client = SimpleNamespace(head_object=head_object, get_object=get_object)
    assert service.asset_r2.is_empty_legacy_zip('steam/123/123.rwmod') == valid
