# Steam original recovery: EK canary

Approval required before staging on s85, stopping the unit, downloading there, or using `--apply`. The Steam sync operator owns s85 during this window; stop if another operator is present. This is a source-only repair: do not change the playable/default pointer, enqueue a translation, or rewrite any old object.

## Verified preflight

- `steam-workshop-sync.service`: `workshop-sync:workshop-sync`, `/srv/steam-workshop-sync/.venv/bin/python3 /srv/steam-workshop-sync/main.py`, Python 3.14, `ProtectSystem=strict`, `UMask=0077`. Writable application paths already include `/srv/steam-workshop-sync/downloads`, `/var/lib/workshop-sync`, and `/var/lib/workshop-steamcmd`.
- Steam app `647960`, anonymous login, `/var/lib/workshop-steamcmd/steamcmd.sh`. The shared install's ACF retained an older EK installed timestamp (`1787224316`) and a pending newer timestamp (`1795178181`, downloaded bytes `0`). The Steam logs show a failed EK download because a different cached item (`3760752874`) had missing files in the same shared tree. Do not clear or reuse the live cache/ACF. The release supplies a fresh `+force_install_dir` for each attempt and only accepts its final `steamapps/workshop/content/647960/2749712324`, the installed (not pending) ACF timestamp, a successful SteamCMD result, and a nonempty CRC-verified archive. A path outside that fresh root is a hard stop, not a fallback.
- EK Workshop `2749712324`, asset `f6cfde86-0c07-420c-a232-7cd50a9de692`, observed DB build epoch `1795178181`. Default file `a01952e3-91f2-4d71-9cb4-e4e38a3f800c` points to a 5,414,332-byte translated object; the separate legacy Steam original is 22 bytes and there was no `steam_source`. Observed sync state `syncing`, without a new-format lease. Re-read these before applying; the Steam revision/default may have legitimately changed.

## Stage and run (after approval only)

Local, from the Steam nested Git worktree. The parent is a gitlink **without** a `.gitmodules` mapping; do not deploy the parent archive or a dirty checkout. The host isn't deployed by Git checkout. Stage only the four changed runtime files, with a manifest:

```bash
set -eu
files='main.py database.py services/mod_sync.py services/r2_service.py'
bundle=$(mktemp -d "$HOME/.hermes/cache/scratch/steam-release.XXXXXXXX")
git archive --format=tar HEAD $files | tar -xf - -C "$bundle"
(cd "$bundle"; shasum -a 256 $files > SHA256SUMS)
stage=$(ssh s85 'umask 077; mktemp -d /root/steam-source-release.XXXXXXXX')
(cd "$bundle"; tar -cf - $files SHA256SUMS) | ssh s85 "tar -xf - -C '$stage'"
printf 'stage=%s\n' "$stage"
```

On s85, set `stage` to that printed path. Record the unit state and stop it. Snapshot the four exact preimages and their hashes before installing; do not copy `.env`, `.venv`, `data`, `downloads`, unit config or Steam state. Compare preimage hashes against the approved preflight before replacement: `main.py` `e88f84ca76e3547162ab87462c093046b8fb13602cd4e7de0465ca5ca2be3438`, `database.py` `2648544942b9b9044aafff92df4a7f60373a13e889fe807f87ee5eb5d0391333`, `services/mod_sync.py` `e64e4cc84f35ede0dee7daca0c6b4c90cf952c1eb86a6eee3a62174bb5d2fe88`, `services/r2_service.py` `8ea914444014b5804a729962abcb37eb9a9c7e741351b8322ef543b867286ed5`.

```bash
set -eu
app=/srv/steam-workshop-sync
files='main.py database.py services/mod_sync.py services/r2_service.py'
(cd "$stage"; sha256sum -c SHA256SUMS)
systemctl stop steam-workshop-sync.service
test "$(systemctl show steam-workshop-sync.service -p MainPID --value)" = 0
backup=$(mktemp -d /root/steam-source-rollback.XXXXXXXX)
(cd "$app"; sha256sum $files | tee "$backup/SHA256SUMS"; cp --parents -p $files "$backup")
printf 'backup=%s\n' "$backup"
# Proceed only after matching all four preimages against this runbook.
for file in $files; do
  install -o root -g workshop-sync -m 0640 "$stage/$file" "$app/$file.new"
  mv -T "$app/$file.new" "$app/$file"
done
(cd "$app"; sha256sum -c "$stage/SHA256SUMS")
```

Keep the daemon stopped. Reproduce as the service account in the service working directory; `.env` is read in place. The default recovery mode does not write DB/R2, but SteamCMD writes Steam logs/cache and an isolated temporary download tree, so this step still needs s85 approval. Rerun with `--apply` only after the dry-run emits a nonempty size, expected workshop epoch, and SHA. If SteamCMD fails on fresh paths, inspect only the new log tail (do not print raw credentials); do not switch to a translated object, old Steam manifest, or staging folder. If Steam shows a newer build than the saved scrape, have the authorized metadata sync refresh that exact item and re-read before retrying.

```bash
cd /srv/steam-workshop-sync
item=2749712324
asset=f6cfde86-0c07-420c-a232-7cd50a9de692
run_source() {
  runuser -u workshop-sync -- env HOME=/var/lib/workshop-sync \
    /srv/steam-workshop-sync/.venv/bin/python3 main.py "$@"
}
run_source --recover-source "$item" --asset-id "$asset"
# Separate approval gate after inspecting dry-run output:
run_source --recover-source "$item" --asset-id "$asset" --apply
```

The apply output is produced only after reading back the exact DB source file, source metadata, `completed` row and unchanged default. Repeat a read-only verification of the legacy and translated object lengths and relevant ETags; no legacy key should have changed. Exercise the API consumer separately: Original must resolve the new key and actual archive bytes/SHA, Translate must still resolve the old translated key when selected, and default must be unchanged. ZIP CRC and nonempty bytes do not alone prove gameplay; inspect `mod-info.txt`/payload with a known Rusted Warfare reader or run an install smoke test before declaring canary success.

## Rollback and follow-on

- On apply failure the asset/source transaction rolls back; the exact status may record an attempt. A verified immutable object can remain orphaned after an upload or failed DB commit; leave it for dedupe/inventory. If a commit succeeds but API verification fails, preserve data unless the exact source rollback is authorized. Restore only the prior `metadata.steam_source` value and exact status snapshot under row lock after comparing the current source hash/status against the applied result; leave default, unrelated metadata, file rows and objects untouched. Do not roll back using a wholesale DB dump.
- Code rollback: keep unit stopped; for the same four files `install -o root -g workshop-sync -m 0640 "$backup/$file" "$app/$file.new"` then `mv -T "$app/$file.new" "$app/$file"`; run `(cd "$app"; sha256sum -c "$backup/SHA256SUMS")`. **Do not restart old code with Mod Sync enabled**: it resumes empty ZIP overwrites. Keep stopped or use an approved temporary unit `Environment=STEAM_WORKSHOP_SYNC_MOD_ENABLED=false` override (`load_dotenv()` does not override the service environment) and restart metadata-only after `systemctl daemon-reload`. No DB DDL is needed.
- After canary approval start the fixed service: `systemctl start steam-workshop-sync.service`; verify `systemctl is-active steam-workshop-sync.service`, loaded code hashes, and a new fixed source/completion or a bounded failed status. The automatic queue handles pending/current builds only; old `syncing`/`failed` rows without a new-format lease are not blindly reset. Failures retry after 15 minutes, stale new-format leases after 90 minutes, maximum three attempts per scraped build (an exact operator recovery intentionally starts a new series). Existing assets never have their `file_id`, title, description or images replaced by this writer; a new asset starts with its source as default.
- Inventory legacy candidates without DB/R2 writes: `run_source --legacy-candidates 20 --check-empty` (paginate using `--after LAST_ITEM_ID`). Recorded DB sizes are only hints; `is_empty_legacy_zip=true` means the actual object matched the 22-byte ZIP signature. Review/allowlist exact pairs; run dry-run then approved `--apply` one at a time with one writer. Pilot only a few confirmed empty originals before increasing scope. Items with a genuinely empty **default** need a separately approved fallback/default fix, not a blanket pointer swap. Do not garbage-collect any previous canonical, default, translated, or legacy object in this rollout.
