# Backup, Point-in-Time Recovery, and Data Reconciliation

A backup is only valuable if it can be restored successfully and the restored data is verified. In PostgreSQL, a data protection strategy typically combines a base backup, continuous Write-Ahead Log (WAL) archiving, integrity checks, and recovery drills. When accidental deletions, erroneous updates, or bad deployments occur, Point-in-Time Recovery (PITR) lets you rebuild a PostgreSQL cluster up to a specific timestamp or named marker in history.

Point-in-time recovery generally restores the entire database cluster to a past state. Consequently, after restoring, you must reconcile business metrics, identify which transactions were rolled back, and inspect side effects that already occurred outside PostgreSQL. A restore that succeeds technically is not guaranteed to match the desired business state.

This lesson covers backup models, WAL archiving, logical and physical backup methods, PITR workflows, data verification, and organizing recovery drills.

## 1. Recovery Objectives and Data Protection Models

### RPO and RTO

Before choosing tools or backup schedules, agree on two objectives:

- **RPO (Recovery Point Objective):** the maximum amount of data loss the organization tolerates, usually expressed in time. A 5-minute RPO means the target is losing at most roughly the last 5 minutes of data during an outage.
- **RTO (Recovery Time Objective):** the maximum acceptable duration to restore service to normal operation. A 30-minute RTO means recovery, verification, and application cutover must complete within that window.

RPO and RTO are business requirements—they are not automatically guaranteed merely because `archive_mode` is enabled or a dump exists.

| Need | Common Mechanism | Key Limitations |
|---|---|---|
| Restoring one database or object group | Logical backup via `pg_dump`/`pg_restore` | Does not provide a continuous WAL stream for PITR |
| Rebuilding an entire PostgreSQL cluster | Physical base backup | Requires matching WAL and compatible environment |
| Restoring right before an erroneous operation | Base backup + WAL archive | Must hold an unbroken WAL chain from backup to recovery target |
| Reducing downtime on server failure | Standby/replication + backups | Replicas also replicate accidental deletions or bad writes |
| Verifying recoverability | Periodic restore drills | Must test in an isolated environment and measure real duration |

### Three Components of PITR

PITR relies on three components:

1. **Base backup:** a consistent copy of PostgreSQL data files taken when the backup began.
2. **WAL archive:** a continuous stream of WAL segments needed to replay every change since the base backup.
3. **Recovery target:** the stopping point for WAL replay, such as a timestamp, named restore point, LSN, or transaction ID.

The process flows as follows:

~~~text
Base backup
    |
    v
WAL segment A -> WAL segment B -> WAL segment C -> WAL segment D
                                                  |
                                                  v
                                     Chosen recovery target
                                                  |
                                                  v
                                 PostgreSQL stops WAL replay
                                                  |
                                                  v
                                  Verification and reconciliation
                                                  |
                                                  v
                                         Promote / cutover
~~~

The base backup must precede the recovery target. The WAL archive must hold every segment needed to advance the backup to that target. A base backup without subsequent WAL cannot recover to arbitrary points after the backup.

### Backups Do Not Replace Replication

Streaming replication maintains a standby server and cuts failover time when the primary crashes. However, replication faithfully propagates both valid changes and mistakes. If an application runs an accidental delete and commits, the standby replays that delete too.

Backups and WAL archives let you rewind to a pre-incident state. Replicas provide high availability. Production systems need both when business requirements demand low downtime alongside data recoverability.

## 2. Choosing a Backup Method

### Logical Backups with `pg_dump`

A logical backup exports schema and data as SQL statements or PostgreSQL archive formats. This works well when you need to:

- Back up a single database.
- Migrate data across supported PostgreSQL major versions.
- Selectively restore a single schema, table, or object group.
- Seed or inspect data in another environment.

Example creating a custom-format dump:

~~~bash
pg_dump -Fc -f /backups/appdb.dump appdb
~~~

The custom format lets `pg_restore` list contents, filter objects, and control restore ordering.

List archive contents:

~~~bash
pg_restore --list /backups/appdb.dump
~~~

Create the target database and restore:

~~~bash
createdb appdb_restore
pg_restore --exit-on-error --verbose -d appdb_restore /backups/appdb.dump
~~~

To preserve role ownership and privileges, matching roles must exist on the target cluster. `pg_dump` excludes cluster-wide objects such as roles and tablespaces. Back up globals separately:

~~~bash
pg_dumpall --globals-only > /backups/globals.sql
~~~

Restore globals before restoring the database if the dump depends on those roles or tablespaces:

~~~bash
psql -X -d postgres -f /backups/globals.sql
~~~

The globals file may contain role credentials depending on configuration and access privileges. Protect it as sensitive data—restrict read permissions and encrypt at rest and in transit.

A logical backup captures a consistent snapshot as of the dump start, but provides no WAL stream for arbitrary point-in-time recovery. Cluster-wide PITR requires a physical base backup and WAL archiving.

### Physical Backups with `pg_basebackup`

A physical backup copies a PostgreSQL cluster's data files using PostgreSQL's built-in consistent backup protocol. It is the standard foundation for PITR and rebuilding entire instances.

Example creating a plain-directory base backup while streaming WAL during the backup:

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backups/base-2026-11-14 \
  -F plain \
  -X stream \
  -P
~~~

Option meanings:

- `-h`, `-p`: source PostgreSQL host and port.
- `-U`: role granted replication privileges.
- `-D`: target directory; must be prepared per `pg_basebackup` requirements.
- `-F plain`: stores output as a standard data directory tree.
- `-X stream`: streams WAL generated while the base backup runs.
- `-P`: displays progress.

Hostnames, paths, and roles above are illustrative. In production, use secure authentication such as a restricted `.pgpass` file or secret manager; avoid passing passwords on the command line or storing them in shell history.

`pg_basebackup` must connect to a server configured with sufficient `max_wal_senders`, a `REPLICATION`-privileged role, and matching `pg_hba.conf` rules. Omit `-R` when taking a standalone backup intended for PITR; `-R` writes standby configuration.

The `-X stream` option includes only the WAL required for consistency of the base backup itself. It does not replace continuous WAL archiving after the backup finishes. Recovering to later timestamps still requires the subsequent WAL archive chain.

### Filesystem or Storage Snapshot Backups

Volume snapshots can be effective when storage infrastructure supports atomic, consistent snapshots. However, never copy a live running data directory with plain file copy tools and treat it as a valid physical backup.

Physical snapshots must follow a consistent backup method supported by PostgreSQL and your storage layer. When snapshots span multiple volumes or tablespaces across filesystems, all volumes must be snapshotted at a synchronized point in time, paired with the corresponding WAL for recovery.

If using a dedicated backup tool such as pgBackRest or WAL-G, follow that tool's conventions for stanzas/repositories, retention, encryption, `archive-push`, `archive-get`, and verification. Never mix restore commands across tools or assume archive formats are interchangeable.

### Comparison Table

| Criterion | Logical Backup | Physical Base Backup + WAL |
|---|---|---|
| Scope | Single database and logical objects | Entire PostgreSQL cluster |
| Restoring a single table | Can select individual objects during restore | Must restore cluster elsewhere, then extract needed data |
| Continuous PITR | Not built-in | Yes, when WAL chain is complete |
| Major version upgrades | Supported across compatible source/target versions | Generally requires the same major version |
| Restore speed | Can be slow on huge datasets | Usually faster for full clusters, depending on backup and WAL size |
| Dependencies | `pg_dump`/`pg_restore`, roles, extensions | Base backup, WAL, compatible config and platform |

In practice, teams often keep periodic logical dumps for selective object recovery alongside physical backups and WAL archiving for full-cluster PITR.

## 3. Preparing WAL Archiving

### What Is WAL?

PostgreSQL logs changes to WAL before modified data pages are flushed to data files. When recovering after a crash, PostgreSQL replays WAL to bring data files back to a consistent state.

WAL is divided into segments—typically 16 MB by default, though configurable at compile/init time. When archive mode is enabled, PostgreSQL invokes `archive_command` or an archive module to copy completed segments into durable archive storage.

WAL archives are not logs of SQL statements. They are binary recovery log records. Never edit WAL contents, rename files arbitrarily, or delete segments simply because they look old.

### Basic Configuration

Parameters to check:

~~~sql
SHOW wal_level;
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
~~~

For physical backups and WAL archiving, `wal_level` must be `replica` or `logical`, and `archive_mode` must be enabled. `archive_command` must invoke a tool capable of durably storing WAL segments.

Illustrative example using an uncompressed local archive directory:

~~~conf
wal_level = replica
archive_mode = on
archive_command = 'cp %p /srv/pg_wal_archive/%f'
~~~

Here `%p` is the source WAL segment path and `%f` is the segment filename. The `cp` example only demonstrates the mechanism in a controlled test environment. Production systems should use a proper archive manager providing error checking, durability guarantees, retries, access controls, encryption, and monitoring.

The archive directory must exist, PostgreSQL must have write permission, and archive storage should reside on fault-independent storage separate from the data volume. If the database and WAL archive share one volume, a volume failure destroys both live data and recovery logs.

Changing `archive_mode` requires a server restart. After configuring, verify runtime values and check PostgreSQL logs to confirm segments archive cleanly.

### Monitoring Archiver Activity

The `pg_stat_archiver` view exposes archiving metrics:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Fields to monitor:

- `archived_count`: WAL segments successfully archived since stats reset.
- `last_archived_wal` and `last_archived_time`: most recent successfully archived segment and timestamp.
- `failed_count`: number of failed archive attempts.
- `last_failed_wal` and `last_failed_time`: most recent failed segment and timestamp.

If `failed_count` climbs, inspect server logs, write permissions, repository free space, network connectivity, and archive manager errors. A stale `last_archived_time` may indicate broken archiving, though compare it against actual WAL generation rate.

Counters in `pg_stat_archiver` are cumulative since `stats_reset`. Do not inspect them just once; sample periodically and alert on rising failures or archive lag exceeding your RPO target.

### WAL Archives Must Be Continuous and Complete

Recovering from a base backup to a target requires every WAL segment spanning that interval. A single missing, corrupted, or unreadable segment can halt recovery before reaching the target.

Common causes of broken WAL chains:

- Prolonged `archive_command` failures with no alerting.
- Archive storage running out of space.
- Retention scripts deleting segments still needed by older base backups.
- Truncated file copies or partial uploads to archive storage.
- Timeline switches after failover without preserving timeline history files.
- Manual operations renaming or moving segments outside the backup tool.

Never purge WAL archives purely by file age. Retention must be driven by retained base backups, required recovery windows, backup tool metadata, and active restore dependencies. An older base backup may rely on very old WAL segments to reach a target.

### Recording Metadata After a Base Backup

Once a base backup finishes, record:

- Backup start and completion timestamps.
- Backup identifier, storage location, and checksum/manifest.
- PostgreSQL major version.
- Associated tablespaces and data paths.
- Starting WAL segment and timeline required for recovery.
- Archive health throughout and after the backup.

Store this metadata alongside the backup. When using a backup manager, run its `info`/`check` commands to verify which backups are valid and which WAL segments remain protected.

## 4. Validating Backups Before You Need Them

### Verifying the Backup Manifest

Modern PostgreSQL versions generate a backup manifest listing files and checksums in a base backup. For backups created with `pg_basebackup`, run `pg_verifybackup`:

~~~bash
pg_verifybackup /backups/base-2026-11-14
~~~

This checks backup contents against the manifest and file checksums. Use a `pg_verifybackup` binary compatible with the backup's major version and resolve any warnings or errors before marking a backup restorable.

Manifest verification does not replace restore drills. A backup can pass file checksums yet fail to restore due to missing WAL, misconfiguration, missing extensions, or deployment issues.

### Checking Logical Backup Readability

For custom-format dumps, run `pg_restore --list` to confirm the archive is readable and displays its table of contents. Then test restoring into a scratch database:

~~~bash
createdb appdb_restore_test
pg_restore --exit-on-error -d appdb_restore_test /backups/appdb.dump
~~~

Inspect tables, privileges, extensions, views, and row data post-restore. If the dump depends on specific roles or tablespaces, pre-create them or adjust intentionally in the test environment.

### Protecting Backups

A resilient backup must:

- Reside in storage independent of the source PostgreSQL host.
- Maintain copies across fault domains or separate storage accounts to guard against simultaneous loss.
- Be encrypted in transit and at rest when storing sensitive data.
- Enforce strict read/write/delete permissions and access auditing.
- Follow retention aligned with legal and business mandates.
- Include checksums/manifests or integrity validation.
- Undergo periodic restore verification.

Apply redundancy across copies, media, and isolated failure domains. If database admin accounts can delete both backups and WAL archives, a security compromise or operator mistake can wipe out every recovery point. Separate backup creation, backup deletion, and database admin roles whenever possible.

## 5. Point-in-Time Recovery (PITR)

### When Is PITR Needed?

PITR fits scenarios where:

- An erroneous `UPDATE` or `DELETE` transaction committed.
- A buggy application release wrote corrupted data over a time window.
- A batch import introduced bad records.
- Operators must rewind prior to a structural or data mutation.
- Investigators need a forensic cluster matching database state before an incident.

Physical PITR restores the entire PostgreSQL cluster. It does not restore a single table directly into a running database. When only one table is needed, restore the cluster into an isolated environment, extract the required table or rows via `pg_dump`/SQL, and import them into the live system in a controlled manner.

### Recovery Target Types

PostgreSQL supports several recovery target modes:

- `recovery_target_time`: a specific timestamp.
- `recovery_target_name`: a previously created named restore point.
- `recovery_target_lsn`: a WAL Log Sequence Number.
- `recovery_target_xid`: a specific transaction ID.

Only one target mode is specified per recovery run. The target must fall within the available, readable WAL chain. Choosing a timestamp before the base backup or beyond the last archived WAL makes the target unreachable.

### Creating a Restore Point Before Major Changes

Before a major deployment or critical batch job, create a named restore point:

~~~sql
SELECT pg_create_restore_point('before_monthly_import');
~~~

PostgreSQL returns the restore point's LSN. Log the name, LSN, timestamp, application version, and operator in your deployment record. The WAL segment holding the restore point must be archived successfully before that name can be used in future recovery.

A restore point writes a marker into WAL; it does not take a standalone backup. You still need a valid base backup and the full WAL chain.

### Preparing the Recovery Environment

A safe workflow restores onto an isolated host or separate data directory:

1. Select a base backup taken prior to the target and verify its manifest/checksums.
2. Confirm the WAL archive holds all segments from backup start through the target.
3. Provision the target host with a compatible major version, extensions, libraries, and required config.
4. Ensure the target data directory is empty or freshly initialized per admin procedure.
5. Restore base backup files into the target data directory, preserving ownership and permissions.
6. Configure `restore_command` and the recovery target.
7. Create `recovery.signal` inside the data directory (PostgreSQL 12+).
8. Start the instance and tail logs until the target is reached.

Never overwrite a live primary's data directory to attempt PITR. Restoring into an isolated environment keeps the current primary intact, allows verifying data before cutting over, and avoids compounding data loss.

### Configuring Recovery to a Timestamp

Suppose you want to recover to 10:15 AM on November 14, 2026 in Vietnam time:

~~~conf
restore_command = 'cp /srv/pg_wal_archive/%f "%p"'
recovery_target_time = '2026-11-14 10:15:00+07'
recovery_target_inclusive = true
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

This example assumes an uncompressed local filesystem WAL archive. In production, replace `restore_command` with your WAL manager's `archive-get` command. The command must return exit code 0 when a file is retrieved and non-zero when a file is absent or unrecoverable. Never use sample `cp` if your archive is compressed, encrypted, or managed by a backup tool.

Settings explained:

- `recovery_target_time`: timestamp at which WAL replay stops.
- `recovery_target_inclusive`: determines whether transactions committing at the exact target instant are included (`true` is default).
- `recovery_target_timeline`: `'latest'` follows the newest timeline available along the recovery chain.
- `recovery_target_action`: `'pause'` pauses the server upon reaching the target so operators can inspect data first.

Always include an explicit time zone offset. Omitting the offset makes interpretation depend on server timezone configuration. WAL records transaction commit timestamps; time-based recovery aligns with commit records, so do not assume millisecond-exact stopping at arbitrary instants without checking commit boundaries. Anchor targets against known transaction timestamps, application logs, audit trails, or restore points.

For a named restore point target:

~~~conf
recovery_target_name = 'before_monthly_import'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

For an LSN target:

~~~conf
recovery_target_lsn = '0/7A1200'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

The LSN above is illustrative. In real operations, use the exact LSN captured from a restore point or incident log.

After configuring, create the recovery signal file:

~~~bash
touch /var/lib/postgresql/data/recovery.signal
~~~

The path must match the target instance's actual `PGDATA`. PostgreSQL 12 and later require `recovery.signal` to trigger archive recovery; older versions used `recovery.conf`. Never mix configuration styles across major versions.

### Starting and Monitoring Recovery

Start the target instance using your environment's service manager. Watch PostgreSQL logs and verify:

- The server detected `recovery.signal`.
- `restore_command` successfully retrieves required WAL segments.
- Zero checksum errors, format errors, or missing segments occur.
- PostgreSQL replays WAL sequentially.
- The recovery target is reached and the server pauses as configured.

During recovery, inspect state with:

~~~sql
SELECT pg_is_in_recovery();
~~~

While recovering, this returns `true`. Once paused at the target, you can connect and run read-only queries to inspect data prior to promotion. Never route application writes to an instance still in recovery.

After data reconciliation confirms the target state and cutover is approved, promote the server:

~~~sql
SELECT pg_promote();
~~~

Or run `pg_ctl promote` against the target data directory. Post-promotion, verify:

~~~sql
SELECT pg_is_in_recovery();
~~~

Returning `false` confirms the server exited recovery and became a writable primary (subject to roles and `pg_hba.conf`). Setting `recovery_target_action = 'promote'` auto-promotes upon reaching the target; whenever pre-cutover verification is needed, `'pause'` keeps the server read-only during inspection.

### Timelines After Failover

Whenever a server promotes, PostgreSQL creates a new timeline. Timeline history files map which WAL branch the server followed. When recovering across multiple historical failovers, ensure both WAL segments and `.history` files reside in the archive.

`recovery_target_timeline = 'latest'` is generally appropriate when following the newest available timeline. To recover onto a specific branch instead, verify the desired timeline ID and target it intentionally. Never guess timelines solely from WAL filenames.

### Common Recovery Errors

| Symptom | Possible Cause | What to Check |
|---|---|---|
| WAL segment not found | Missing archive file, wrong `restore_command`, or read permission denied | PostgreSQL logs, archive path, file permissions |
| Recovery stops before target | Missing WAL, recent segments not archived yet, or target outside available range | Inventory WAL sequence, base backup timestamp, and last archived timestamp |
| Timeline error | Missing `.history` file or wrong WAL branch selected | Inspect history files and backup timeline |
| Target time differs from expectations | Timezone mismatch, target missed commit timestamp, or `inclusive` setting mismatch | Cross-check commit times, app logs, and timezone settings |
| Server does not enter recovery | Missing `recovery.signal`, file placed in wrong `PGDATA`, or config not loaded | Check data directory, startup logs, and major version |
| Server starts but data is missing | Wrong base backup, missing WAL, or target chosen too early | Verify backup selection, WAL chain, and chosen target |

When recovery fails, preserve logs and the partially restored instance for root-cause analysis. Never delete WAL or keep tweaking targets blindly without recording each attempt's state.

## 6. Restoring Logical Backups

PITR excels for whole clusters, whereas logical restores fit restoring a single database or subset of objects.

### Restoring a Database from a Custom Dump

On the target cluster, first create required roles, extensions, and tablespaces. Then create the database and restore:

~~~bash
createdb -T template0 appdb_restore
pg_restore --exit-on-error --verbose \
  -d appdb_restore \
  /backups/appdb.dump
~~~

If the dump references extensions, ensure those extensions are installed on the target server. Verify object owners, grants, default privileges, collations, and locales. Avoid blindly passing `--no-owner` or `--no-privileges` when the application depends on source permissions.

You can restore individual schemas or tables using `--schema`, `--table`, or TOC lists. When restoring a single table, check dependencies such as sequences, custom types, functions, triggers, foreign keys, and referenced rows. A table that loads cleanly may still fail to function independently.

### Restoring from Plain SQL Dumps

Plain-text SQL dumps load via `psql`:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f /backups/appdb.sql
~~~

`-X` ignores the user's `.psqlrc`, keeping restores unaffected by personal defaults. `-v ON_ERROR_STOP=1` halts `psql` immediately on SQL errors instead of continuing silently.

Capture `stdout`/`stderr` logs and the exit code. If a restore aborts mid-way, inspect which objects were created before deciding whether to drop and recreate the target database.

### Comparing Logical Restore vs. PITR

Logical restores let you pick objects, yet cannot reconstruct exact cluster-wide physical state at an arbitrary point in time. Physical PITR reconstructs the entire cluster via WAL, yet lacks an option to restore a single table while keeping newer changes elsewhere.

To recover a single accidentally dropped table:

1. Restore a temporary cluster from a base backup + WAL up to right before the drop.
2. Verify the data inside the temporary cluster.
3. Export the table and dependent definitions using `pg_dump` or `COPY`.
4. Inspect keys, sequences, constraints, and relationships with live rows.
5. Import back into the live database inside a controlled transaction or migration.

Never replace an entire live production cluster with an older PITR snapshot when the business only needs to recover a subset of data; doing so discards valid transactions committed after the target.

## 7. Reconciling Data After Recovery

### Technical Verification vs. Business Reconciliation

Technical verification answers: does PostgreSQL boot, did WAL finish replaying, are tables readable, and do extensions work?

Business reconciliation answers: does data match the intended recovery point, which transactions were lost, do financial totals tie out, and can the application safely resume from this state?

Both checks are mandatory. A cluster that starts cleanly can still hold data misaligned with recovery goals.

### Anchoring the Reconciliation Baseline

Before comparing numbers, align on:

- Exact recovery target and time zone.
- Last transaction or batch expected to be present.
- First transaction expected to be excluded.
- Time window to reconcile.
- Independent verification sources such as audit logs, ledgers, payment gateways, or event logs.

Never compare counts from two systems taken at different timestamps and conclude data is missing. For continuously changing datasets, pin both sides to the same cutoff timestamp or business sequence watermark.

### High-Level Database Checks

Post-restore, inspect the database and key tables:

~~~sql
SELECT
    current_database() AS database_name,
    current_timestamp AS checked_at,
    pg_is_in_recovery() AS is_in_recovery;

SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
~~~

`pg_stat_user_tables` reports estimated tuple counts, not exact counts. Run `COUNT(*)` on critical tables or partitions needing exact verification, mindful of read cost on huge tables.

Example checking daily order totals:

~~~sql
SELECT
    created_at::date AS order_date,
    count(*) AS order_count,
    sum(total_amount) AS total_amount
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-15 00:00:00'
GROUP BY created_at::date
ORDER BY order_date;
~~~

Compare outputs against confirmed reports, audit records, or independent business systems. For monetary figures, use exact `numeric` types and match application rounding rules.

### Checking Keys and Referential Integrity

Verify primary keys, unique constraints, and foreign keys are active and valid. Example finding orphaned orders in a system where every order must map to a customer:

~~~sql
SELECT count(*) AS orphan_orders
FROM orders o
LEFT JOIN customers c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

If the count is non-zero, investigate whether those rows reflect valid model semantics or restore/import corruption. Never delete or patch rows automatically just to force the count to zero.

On large tables, run checks per partition, key range, or business date to bound load. Log exact queries, timestamps, and outputs so subsequent drills can compare baselines.

### Reconciling Against External Systems

A transactional database routinely interacts with external systems:

- Payment gateways may have captured funds even though the order transaction rolled back under PITR.
- Message brokers may have already published events prior to the recovery timestamp.
- Sent emails or notifications do not vanish when the database rewinds.
- Data warehouses or BI pipelines may have ingested rows prior to PITR.
- Accounting ledgers may contain entries absent from the restored database.

Consequently, reconcile database state against external sources and build a list of events requiring compensation, replay, or business reversal. Never blindly re-send payments, emails, or events simply because a row disappeared after PITR; check idempotency keys and downstream state at the receiving system first.

### Checking Sequences and Identity Columns

Under physical PITR, sequence states recover along with WAL. Under logical dumps, sequence states are generally saved in the dump, though manual imports or selective restores can leave sequences out of sync with table rows.

Verify sequences after partial data imports. Never blindly reset a sequence to `MAX(id)` if the sequence is shared across tables, IDs are pre-allocated, or concurrent writes occur. Once you confirm a sequence trails the table's max ID and writes are paused, synchronize it per application policy.

Example for a table whose `id` column owns a dedicated sequence:

~~~sql
SELECT setval(
    pg_get_serial_sequence('public.orders', 'id'),
    COALESCE((SELECT max(id) FROM public.orders), 1),
    EXISTS (SELECT 1 FROM public.orders)
);
~~~

This assumes the sequence is bound exclusively to `id` and writes are quiesced during repair. If a sequence serves multiple tables or the application allocates IDs externally, follow allocation rules before adjusting. Advancing a sequence can leave ID gaps; gaps are normal and not data corruption.

### Writing a Reconciliation Report

Every recovery should produce a reconciliation record containing:

| Section | Evidence to Record |
|---|---|
| Recovery source | Base backup name, checksum/manifest, WAL archive location |
| Recovery target | Timestamp with timezone, restore point/LSN if used, timeline |
| Technical outcomes | Recovery logs, `pg_is_in_recovery()` status, promotion result |
| Data reconciliation | `COUNT`s, monetary sums, min/max timestamps, keys and integrity checks |
| External reconciliation | Payments, messages, audit logs, events, and downstream systems |
| Discrepancies | List of records/events requiring follow-up action |
| Sign-off | Business approver, operator, and cutover timestamp |

This report gives teams clear visibility into exactly where data rewound and which side effects still need handling.

## 8. Cutting Over Applications to the Restored Cluster

### Keep the Cluster Isolated During Verification

During recovery and reconciliation:

- Block application writes to the recovering instance.
- Keep the old primary fenced or disconnected from write paths to prevent dual primaries.
- Restrict connections strictly to operators and verification tooling.
- Pause background jobs, schedulers, and consumers that write data or emit events.
- Record every configuration change applied.

This keeps data frozen during reconciliation and prevents split-brain post-promotion.

### Pre-Cutover Checklist

Before pointing application endpoints to the restored cluster, confirm:

1. Recovery reached the exact target with zero WAL errors in logs.
2. Technical verification and business reconciliation passed.
3. Required roles, grants, extensions, functions, triggers, and jobs function properly.
4. Applications connect cleanly and pass read/smoke checks.
5. External side effects are accounted for with compensation/replay plans ready.
6. The old primary is blocked from accepting writes.
7. Fresh backups and WAL archiving are configured on the restored primary.
8. Monitoring, alerts, and rollback/cutover procedures are ready.

Post-promotion, confirm `pg_is_in_recovery()` returns `false`, new archiving works, and any standbys are rebuilt or resynchronized onto the new timeline. Never let a standby linger on an old WAL branch if it cannot follow the new timeline; rebuild or reseed per your replication procedure.

## 9. Designing Backup Schedules and Retention

### Aligning Schedules to RPO and RTO

Base backup and WAL archive schedules depend on database size, write churn, restore speed, and storage capacity.

For instance, a system targeting a 5-minute RPO might:

- Archive WAL continuously with monitored archive delay.
- Take daily physical base backups (or at a cadence matching RTO).
- Retain enough backups and WAL to cover the required recovery window.
- Take periodic logical dumps for critical databases or objects.
- Run restore drills to measure real-world timings.

This schedule is illustrative only. Actual RPO also depends on WAL generation timing, `archive_command` execution, transfer latency to durable storage, and alerting speed on archive failures. Never promise an RPO solely from an `archive_timeout` setting.

### Retention Must Preserve Complete WAL Chains

When pruning old backups, check which WAL segments are still needed by surviving backups. Dedicated backup tools track these dependencies via catalogs and retention policies. If writing custom scripts, track exact backup start/end points, WAL start/end boundaries, and timelines.

Never delete WAL files with naive commands like "delete everything older than N days" without verifying backup dependencies. A single old WAL segment may be the critical link required to restore a base backup still inside retention.

### Monitoring Archive Capacity and Latency

Track:

- Hourly/daily WAL volume generated.
- Free space remaining in the archive repository.
- Timestamp of the latest successful archive.
- Failed archive attempt count.
- Latency from WAL segment completion to durable archive storage.
- Valid backup count and age of the newest backup.
- Verification and restore drill outcomes.

Alert well before archive repositories or local filesystems fill up. When archiving stalls, `pg_wal` retains unarchived segments and grows until disk exhaustion halts the database.

## 10. Periodic Recovery Drills

### Why Run Drills?

Backups can suffer corruption, missing WAL, missing roles, or misconfigurations—issues that typically surface only during an actual restore. Periodic drills prove the organization can:

- Locate the right backup.
- Fetch the complete WAL chain.
- Boot PostgreSQL in the target environment.
- Recover to the exact requested target.
- Reconcile data accurately.
- Restore application service within RTO.

### Sample Drill Workflow

~~~text
Select backup and recovery target
          |
          v
Verify manifest and WAL chain
          |
          v
Restore into isolated environment
          |
          v
Monitor recovery through target
          |
          v
Run technical checks & business reconciliation
          |
          v
Measure duration, log gaps & lessons
          |
          v
Tear down test environment per policy
~~~

Drills should pull backups from real archive storage rather than restoring a fresh backup just taken on the same host. Whenever possible, practice losing the source host and restoring onto a separate host.

### Measuring Outcomes

Record:

- Time to locate and download the backup.
- Time to extract or restore the base backup.
- Time to replay WAL to target.
- Time spent reconciling data.
- Total end-to-end time until application readiness.
- Required disk space.
- Errors encountered or manual interventions needed.

If total recovery exceeds RTO, improve workflows, storage bandwidth, backup cadence, or data partitioning. If the target was unreachable due to missing WAL, fix archiving and retention before claiming RPO compliance.

## 11. Scenario Walkthrough: Recovering Before a Bad Import

A batch import started at 10:00. By 10:12, operators noticed duplicate order records. The batch committed multiple transactions while live traffic also kept placing new orders. The goal is to reconstruct pre-batch state to investigate and recover clean data.

### Gathering Timeline Markers

Record:

- Batch start time and first batch transaction timestamp.
- Batch completion timestamp.
- Timestamp when the bug was detected.
- Batch ID, request ID, or import identifier.
- Legitimate live transactions committed during the same window.
- Outbound events already sent to payment gateways or message brokers.

If a named restore point was created prior to the batch, use that name to avoid guessing timestamps. Otherwise, choose `recovery_target_time` from commit logs and audit trails with an explicit time zone.

### Standing Up the Recovery Cluster

Select the latest base backup taken before the target. Verify its manifest and WAL chain. Restore into a separate host or data directory, configure `restore_command` and the target, create `recovery.signal`, and start PostgreSQL.

Set `recovery_target_action = 'pause'` so the cluster holds at recovery state upon reaching the target. Read logs to confirm WAL replayed cleanly to the marker. Then inspect order counts, totals, and batch-related records.

### Reconciling and Extracting Data

Once the recovered cluster matches pre-batch state, compare against audit trails and external systems. Identify which orders existed before the batch and which payments were captured. Do not overwrite live production with the old database if legitimate post-target orders must be preserved.

You can export the clean pre-batch dataset from the temporary cluster, deduplicate by business keys, and merge back into the live cluster via an idempotent workflow. If business leadership instead approves rewinding the entire system back before 10:00, obtain formal sign-off on losing post-target transactions and prepare external compensation plans.

### Cutover

Promote and cut over applications to the recovered cluster only if the business decision is full replacement of current state. If the goal is selective data recovery, keep the live cluster running and import only the extracted data. After any full cutover, immediately take a fresh base backup and verify WAL archiving on the new timeline.

## 12. Mistakes to Avoid

| Mistake | Consequence | Proper Practice |
|---|---|---|
| Relying solely on `pg_dump` while expecting PITR | No continuous WAL stream to rewind to arbitrary points | Use physical base backups + WAL archiving for PITR |
| Copying `PGDATA` directly while the server runs | Backup copy may be inconsistent/corrupted | Use `pg_basebackup` or PostgreSQL-supported snapshot workflows |
| Ignoring failed archive alerts | Missing WAL prevents recovery from reaching target | Monitor `pg_stat_archiver`, logs, and archive storage |
| Deleting WAL strictly by file age | Breaks WAL chains still needed by retained base backups | Use a retention-aware backup manager |
| Restoring over a live primary | Risks permanent data loss and split-brain | Restore into an isolated environment before deciding on cutover |
| Choosing `recovery_target_time` without a timezone | Risk recovering to the wrong hour | Always specify explicit timezone offsets or UTC |
| Promoting immediately when recovery stops | Skips data reconciliation | Pause, inspect, reconcile, and promote only after verification |
| Treating a replica as a backup | Replicas immediately apply accidental deletes | Maintain independent backups and WAL archives |
| Checking only whether PostgreSQL starts | Misses business data discrepancies | Reconcile row counts, totals, integrity, and external systems |
| Skipping restore drills | Missing backups or broken WAL surface only during real outages | Run regular restore drills and measure actual RTO/RPO |

## 13. Command Reference

The commands below are starting points for verification. Adapt database names, roles, paths, versions, and privileges to your environment.

**Check version and WAL configuration**

~~~sql
SELECT version();
SHOW wal_level;
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
~~~

**Monitor the archiver**

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

**Create a restore point before a change**

~~~sql
SELECT pg_create_restore_point('before_release_2026_11_14');
~~~

**Create a logical backup**

~~~bash
pg_dump -Fc -f /backups/appdb.dump appdb
pg_dumpall --globals-only > /backups/globals.sql
pg_restore --list /backups/appdb.dump
~~~

**Create a physical base backup**

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backups/base-2026-11-14 \
  -F plain \
  -X stream \
  -P
~~~

**Verify a physical backup**

~~~bash
pg_verifybackup /backups/base-2026-11-14
~~~

**Check status during/after recovery**

~~~sql
SELECT pg_is_in_recovery();
~~~

**Promote after reconciliation**

~~~sql
SELECT pg_promote();
~~~

Never run restore, promote, or endpoint-change commands in production simply because these examples succeeded in a lab. Always use verified backups, targets, hosts, credentials, and cutover procedures.

## 14. Recommended Operational Sequence

When designing or executing PostgreSQL recovery, follow this order:

1. Define RPO, RTO, and required recovery scope.
2. Choose logical backups, physical backups, or a combination of both.
3. Configure WAL archiving and monitor archive health.
4. Take base backups, verify manifests, and store metadata.
5. Maintain retention policies that protect full backup + WAL chains.
6. During an incident, choose a clear timezone/timeline target and restore into an isolated environment.
7. Monitor recovery, confirm target attainment, and keep the server paused while inspecting.
8. Perform technical verification, business reconciliation, and external side-effect checks.
9. Decide between full-cluster cutover vs. selective data extraction.
10. Promote/cut over per plan, then configure fresh backups and WAL archiving for the new primary.
11. Drill periodically, record actual RTO/RPO, and refine procedures.

A system is truly recoverable only when the organization can prove that backups are readable, WAL chains are complete, recovery targets are reachable, restored data is reconciled, and applications resume within target recovery times.
