# Base Backups Combined with WAL Archiving in PostgreSQL

## 1. Why Isn't Copying the Data Directory Enough?

A running PostgreSQL database continuously modifies pages, WAL, control metadata, and relation files. Simply copying the data directory while the server is running using an ordinary file-copy command can capture an inconsistent set of files across different points in time. One page might be copied before a change and another after a change; the WAL needed for recovery might also be missing from the copy.

PostgreSQL solves physical backups using a **consistent base backup** combined with **WAL (Write-Ahead Logging)**. The base backup provides a complete starting point; the WAL archive supplies the sequence of changes needed to bring the copy to a consistent state and/or a desired recovery point.

```text
                 PRIMARY POSTGRESQL
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Base backup                WAL stream
       (base snapshot)            (segments)
             |                       |
             v                       v
      Backup repository       WAL archive repository
             |                       |
             +-----------+-----------+
                         |
                         v
              Restore + WAL replay
                         |
                         v
              Consistent recovery point
                         |
                         v
                  Application online
```

A strategy combining base backups and WAL archiving supports:

- Recovering after disk loss or node loss.
- Recovering to a point in time right before a user accidentally deleted data.
- Creating a consistent database copy to restore onto another machine.
- Building a standby from a base backup and continuing to receive WAL.
- Meeting measurable RPO/RTO targets.
- Retaining timeline-based incident investigation capability when matching backups and WAL exist.

**The base backup is the starting point; continuous WAL is what advances to the recovery point.** Having one without the other means PITR capability may not exist.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish physical backups, logical backups, base backups, and WAL archives.
2. Explain why online backups must be created through a consistency-preserving procedure.
3. Understand WAL segments, WAL records, LSNs, timelines, and checkpoints operationally.
4. Configure fundamental parameters for WAL archiving.
5. Use `pg_basebackup` to create physical base backups.
6. Understand WAL method options: `stream`, `fetch`, and `none`.
7. Design retry-safe, lossless `archive_command`/`archive_library` workflows.
8. Monitor `pg_stat_archiver` and archive backlogs.
9. Establish retention policies keeping sufficient WAL for every supported base backup.
10. Restore from a base backup and replay WAL to a specific point in time.
11. Understand `recovery.signal`, `restore_command`, and recovery targets.
12. Handle timelines after failover/promotion.
13. Protect backups using encryption, access control, checksums, and offsite copies.
14. Measure RPO/RTO and organize restore drills.
15. Distinguish a technically successful backup from proven restorability.

---

## 2. Physical Backup vs. Logical Backup

PostgreSQL has two common backup families.

| Category | Tools / Examples | Data Captured | Purpose |
|---|---|---|---|
| Physical backup | `pg_basebackup`, supported snapshots | Cluster physical files or supported scope | Cluster restore, standby, PITR with WAL |
| Logical backup | `pg_dump`, `pg_dumpall` | SQL/custom/archive representation of objects/data | Schema/data migration, object-level backups |

### 2.1. Physical Backup

Physical backups copy PostgreSQL's storage layout, including relation files, metadata, and required components. To take a consistent backup while the server is running, use PostgreSQL's backup protocol/tools or a documented snapshot procedure.

Physical base backups are normally tied to one PostgreSQL major version and platform/build compatibility requirements. Do not assume you can take a PG 16 data directory and start PG 17 directly on it. Major upgrades require procedures such as `pg_upgrade` or an appropriate logical migration.

### 2.2. Logical Backup

Example:

```bash
pg_dump -Fc -d appdb -f appdb.dump
pg_dumpall --globals-only -f globals.sql
```

Logical backups are useful when:
- You only need one database/schema/table.
- You want to migrate across major versions.
- You want fine-grained control over restored objects.
- You need more portable exports than physical files.

However, a logical dump is not a WAL archive and does not provide continuous point-in-time recovery for individual commits after the dump timestamp.

### 2.3. The Two Can Complement Each Other

A strategy may combine:
- Physical base backups + WAL archive for disaster recovery and PITR.
- Periodic logical dumps for portability, object-level recovery, or independent verification.
- Key data exports according to business needs.

Do not substitute logical dumps for a WAL archive when recovery to arbitrary moments within a continuous window is required.

## 3. What Is a Base Backup?

A base backup is a consistent physical copy of a cluster or PostgreSQL-supported backup scope captured across a defined start/end interval.

A base backup can contain:
- Cluster data files.
- System catalogs and relation files.
- Required tablespace mappings.
- Backup metadata/manifest.
- WAL needed to make the backup consistent, depending on creation method.

When backing up a live server, pages may be copied at different instants. PostgreSQL records backup start/stop points and uses WAL to replay necessary changes, bringing the copy to a consistent state.

### 3.1. A Base Backup Is Not an Instantaneous Millisecond Snapshot

A physical backup is usually a sustained copy operation. Restorability depends on the WAL needed to finish recovery. Therefore, you cannot inspect a backup folder's file count alone and conclude the server can boot.

### 3.2. Base Backups and WAL Must Belong to the Same History

WAL needed for a backup must be continuous and on the right timeline. If a middle segment is missing, recovery may halt before the desired target or fail to complete.

### 3.3. Backup Consistency Is Managed by the PostgreSQL Protocol

Use `pg_basebackup` or a PostgreSQL-supported snapshot solution. Never copy a running `PGDATA` with `robocopy`/`cp` and call it a valid base backup.

## 4. What Is WAL?

WAL is an ordered change log used by PostgreSQL for crash recovery, replication, and backup/recovery workflows.

When transactions modify data, PostgreSQL emits WAL records describing the required changes. Under write-ahead logging rules, WAL must be durably persisted before the corresponding data pages are flushed to disk.

```text
SQL INSERT / UPDATE / DELETE
             |
             v
      Buffer / heap changes
             |
             v
        WAL records
             |
             v
       WAL flush at commit
             |
             v
       Commit acknowledged
             |
             v
     Data pages written later
```

### 4.1. WAL Record

A WAL record describes an internal change or group of changes. It is not a literal SQL statement meant to be replayed like a SQL script.

### 4.2. WAL Segment

WAL is split into segment files whose size is determined by build/configuration. Segment filenames encode the timeline and WAL position; do not rename them by date.

A common segment size in many builds is 16 MiB, though you must check the actual server—such as via `pg_controldata` or appropriate tools. Never hard-code this size in archival systems.

### 4.3. LSN

An LSN (Log Sequence Number) identifies a position in the WAL stream, typically displayed as:

```text
0/16B6C50
```

An LSN is a log position, not a timestamp. You can use `pg_wal_lsn_diff` to compute the byte distance between two LSNs.

### 4.4. WAL Is Not an Audit Log

WAL serves recovery/replication. Do not use it as a human-readable business audit table. If you need actor, business timestamp, and action details, design dedicated audit/event records.

## 5. What Is Continuous Archiving?

WAL archiving copies completed WAL segments from `pg_wal` to a durable archive repository.

When archiving is enabled, PostgreSQL invokes the archive mechanism once a segment is ready. If `archive_command`/`archive_library` fails, PostgreSQL retries according to server rules.

```text
PostgreSQL primary
    |
    +-- pg_wal/segment A
    |       |
    |       v
    |    archive process
    |       |
    |       v
    |    durable archive storage
    |
    +-- pg_wal/segment B
            |
            v
         archive process
            |
            v
         durable archive storage
```

### 5.1. WAL Archiving Is Not Streaming Replication

- Streaming replication ships WAL to a live standby over the replication protocol.
- WAL archiving persists segments into an archive repository for backup/recovery.
- Both mechanisms can run side by side for different purposes.

### 5.2. Archiving Has Latency

A WAL segment is normally archived when filled or switched. Hence, the newest WAL may still sit inside the active open segment in `pg_wal`.

`archive_timeout` can force WAL switches periodically on low-write workloads, but does not turn every transaction into a separate archived file.

### 5.3. PITR Requires Continuous WAL

To restore a base backup to a target time, you need every required WAL segment from the start of recovery up to the target, plus associated timeline history files.

## 6. Required Configuration Settings

Core settings typically include:

```conf
wal_level = replica
archive_mode = on
archive_command = '...'
```

### 6.1. `wal_level`

`wal_level` controls how much information is written to WAL for features like replication/archiving. For standard physical streaming replication and WAL archiving, `replica` is the common choice.

### 6.2. `archive_mode`

`archive_mode = on` enables WAL archiving on a primary/standalone server. Changing this parameter usually requires a PostgreSQL restart, not just a reload.

Some versions support `archive_mode = always` to archive WAL during recovery/standby operation. Enable it only if you understand multi-node/timeline archive architectures and filename collision/overwrite risks.

### 6.3. `archive_command` or `archive_library`

`archive_command` executes an external command to archive each segment. Newer versions support `archive_library` for library-based archiving. The two options have distinct semantics/configurations depending on version.

### 6.4. Inspecting Current Configuration

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'archive_mode',
    'archive_command',
    'archive_library',
    'archive_timeout',
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_wal_size',
    'min_wal_size',
    'full_page_writes'
)
ORDER BY name;
```

Not every server version has every setting; adapt the query to your actual `pg_settings`.

## 7. Configuring `archive_command`

PostgreSQL provides two standard placeholders:

- `%p`: full path to the WAL file to archive.
- `%f`: WAL filename.

Illustrative example in a Unix lab environment:

```conf
archive_mode = on
archive_command = 'test ! -f /srv/pgarchive/%f && cp %p /srv/pgarchive/%f'
```

This is a minimal example, not a complete production script. You must pre-create the directory, set proper permissions, and handle durability/atomicity.

### 7.1. Exit Status Is Critical

- Exit code 0: PostgreSQL treats the file as successfully archived.
- Non-zero exit code: PostgreSQL treats the archive attempt as failed and retries.

Never return 0 before the file is genuinely durably persisted at the destination per system guarantees.

### 7.2. `archive_command` Must Be Idempotent

PostgreSQL may invoke archiving again for the same WAL file after an error or restart. The archive script must handle the case where the destination file already exists:

- If the destination file is identical to the source, it can treat it as already archived.
- If the destination file differs in content, it must fail and trigger investigation.
- Never silently overwrite an archive file with different content.

### 7.3. Never Trust Unvalidated Paths

WAL filenames are provided by PostgreSQL. Even so, scripts should properly quote/validate shell arguments and avoid unsafe string concatenation.

### 7.4. Atomic Copy

A robust workflow typically:
1. Copies to a temporary file on the same filesystem/repository.
2. Verifies size/checksum.
3. Flushes/persists durably per storage guarantees.
4. Atomically renames to the final target name.
5. Returns exit 0 only after required steps finish.

For object storage, use multipart/commit upload semantics and verify object completeness; do not assume simple copy commands share identical semantics.

### 7.5. Never Delete Source WAL Inside `archive_command`

PostgreSQL manages WAL inside `pg_wal`. `archive_command` must only copy; never delete source segments or modify WAL files actively used by the server.

## 8. Archive Storage: Local, Network, and Object Storage

WAL archives can be stored on:
- A separate filesystem on the same host.
- A different storage volume.
- Supported and tested NFS/SMB shares.
- A backup server on a private network.
- Object storage via appropriate clients/libraries.
- Managed backup services.

### 8.1. Same Host Does Not Protect Against Disasters

If `PGDATA` and the archive sit on the same disk/VM/region, one physical outage or accidental wipe can destroy both.

### 8.2. Offsite/Independent Failure Domains

The archive should reside in a separate failure domain aligned with DR requirements: another host, separate storage, another region, or an immutable backup repository.

### 8.3. Archive Storage Needs Durability and Availability

An archive store that is full, out of quota, missing credentials, or timing out causes the archiver to fail. Monitor capacity, permissions, and upload errors.

### 8.4. Object Storage Needs Dedicated Semantics

Ensure object uploads complete cleanly, prevent unintended overwrites, verify checksums, and ensure lifecycle policies do not delete WAL required by valid base backups.

## 9. Securing `archive_command` and Credentials

`archive_command` typically runs under the PostgreSQL server's OS user. Therefore:

- Grant only necessary permissions on directories/archive clients.
- Never hard-code cloud secrets in broadly readable config files.
- Use appropriate credential providers/secret stores.
- Protect `.pgpass` if passwords are used for backup connections.
- Restrict network egress/ingress per architecture.
- Log errors without logging secrets/tokens.
- Separate archive write/read permissions from retention deletion permissions where possible.

### 9.1. Encryption at Rest and in Transit

WAL archives contain sensitive data in physical form. Protect them using:
- Encryption at rest at the storage layer or client-side encryption.
- TLS when transferring over networks.
- Key management independent of the database server.
- Key rotation and decryption verification during restore drills.

Encryption does not replace checksums, access controls, or restore tests.

### 9.2. Immutable/WORM Storage

Against ransomware/credential compromise, consider object lock/immutable retention or separate backup accounts. A backup administrator should not hold single-key power to wipe both production and DR copies.

### 9.3. Backups Are Production Data Too

Base backups and WAL archives hold even more data than a typical query result. Apply data classification, access logging, retention, and secure disposal.

## 10. `pg_basebackup`: Creating Physical Base Backups

`pg_basebackup` is PostgreSQL's client utility using the replication protocol to take a base backup from a running server.

Plain-format example:

```bash
pg_basebackup \
  -h db-primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backup/postgres/base/2026-11-14T010000Z \
  -F plain \
  -X stream \
  -P \
  -v
```

This syntax is illustrative. Paths, hosts, users, and credentials must be tailored to the real environment.

### 10.1. Primary Parameters

| Parameter | Meaning |
|---|---|
| `-h` | PostgreSQL host |
| `-p` | Port |
| `-U` | Backup user |
| `-D` | Destination directory |
| `-F plain` | Writes directory structure matching the data directory |
| `-F tar` | Writes tar archives |
| `-X stream` | Streams needed WAL during the base backup |
| `-X fetch` | Fetches needed WAL at the end of backup from server/archive per conditions |
| `-X none` | Does not collect WAL via this method; caller must ensure required WAL |
| `-P` | Displays progress |
| `-v` | Verbose |
| `-c fast` | Requests a fast checkpoint instead of spread |
| `-R` | Writes config so the backup directory can run as a standby per tool/version semantics |
| `-C -S name` | Creates a named replication slot in compatible setups |

### 10.2. Choosing a WAL Method

`stream` is convenient for standalone base backups because required WAL is streamed concurrently into the backup. It requires adequate WAL sender capacity and can open an additional replication connection.

`fetch` gathers required WAL at the end; segments must remain available on the server or archive per tool conditions. If WAL is recycled before fetch runs, the backup can fail.

`none` does not ensure the backup contains enough WAL to finish recovery. Use only when another workflow guarantees WAL continuity.

### 10.3. Do Not Confuse `-R` with PITR

`-R` configures a backup as a standby—for example creating `standby.signal` and connection settings. It does not configure `recovery_target_time` to recover an independent database to a chosen historical point.

### 10.4. Tar vs. Plain Format

- Plain format writes a backup directory tree; convenient for direct physical restores after preparing the target directory.
- Tar format writes archive files, convenient for storage/transfer; must be extracted properly on restore.

Check version-specific docs for tar filenames, WAL tar files, and tablespace mappings.

## 11. Creating a Backup User and Connection Privileges

`pg_basebackup` uses the replication protocol. The backup user needs appropriate privileges—typically `REPLICATION` and `LOGIN`—plus a matching rule in `pg_hba.conf`.

SQL example:

```sql
CREATE ROLE backup_user
    WITH LOGIN REPLICATION;
```

`pg_hba.conf` example for a restricted subnet:

```conf
host    replication    backup_user    10.20.30.40/32    scram-sha-256
```

The IP address is illustrative. Restrict to specific backup hosts, enforce TLS where appropriate, and manage passwords securely.

### 11.1. Replication Connections Need Capacity

Check:
- `max_wal_senders`.
- `max_replication_slots`.
- Active standbys/CDC/backup jobs consuming senders.
- User connection limits.
- Network throughput.

### 11.2. Never Put Passwords on the Command Line

Use `.pgpass` with strict permissions on Unix or the environment's secure credential mechanism. Never expose passwords in scripts/logs/process lists.

### 11.3. Separate the Backup Role from Superuser

Do not grant superuser solely to run `pg_basebackup` when a replication role and necessary privileges suffice per version/configuration.

## 12. Replication Slots and `pg_basebackup`

You can instruct `pg_basebackup` to use/create a replication slot when appropriate.

Slots retain WAL needed by a consumer, though slots do not themselves archive WAL to backup storage.

### 12.1. Slots Are a Retention Constraint

If a consumer stops operating, its slot can pin WAL and grow `pg_wal`. Monitor inactive slots and retained WAL.

### 12.2. Temporary Slots vs. Permanent Slots

`pg_basebackup` offers slot options depending on version. Temporary slots have a different lifecycle from permanent slots. Verify exact behavior when using slot creation/selection options.

### 12.3. Do Not Create Unmonitored Slots for Every Backup

Long-lived slots pin WAL indefinitely if consumers fail to advance. Backup jobs must clean up their slots per policy on completion or failure, without dropping slots belonging to standbys/CDC.

### 12.4. `max_slot_wal_keep_size`

Some versions support capping WAL retained by replication slots via this parameter. Hitting the cap can invalidate a slot if the consumer is too slow; it does not replace monitoring.

## 13. Checkpoints and Base Backup Impact

To start a backup, PostgreSQL needs an appropriate checkpoint. `pg_basebackup` offers checkpoint behavior options:

- `fast`: requests a rapid checkpoint, which can cause an I/O burst.
- `spread`: spreads checkpoint work per server rules, smoothing spikes on some workloads though taking longer.

Review related settings and choose based on SLOs.

### 13.1. Backups Can Increase I/O

Base backups read large volumes of data, competing with production queries for cache and storage bandwidth. Measure read throughput, database latency, CPU/network, WAL generation, replica lag, and completion duration.

### 13.2. Pick Windows Around Workloads

If a full backup reads 4 TB and storage provides only 300 MB/s available, minimum duration alone is already substantial before overhead. Schedule around actual load and capacity.

### 13.3. Do Not Force `fast` Checkpoints Every Time

`fast` checkpoints can trigger heavy write bursts. Choose based on workload tolerance rather than assuming faster is always better.

## 14. Backup Manifests and Verifying Base Backups

Modern PostgreSQL versions generate a backup manifest listing files/sizes/checksums for supported base backups.

You can run:

```bash
pg_verifybackup /backup/postgres/base/2026-11-14T010000Z
```

This checks consistency of the backup against its manifest and checksums per tool/version capabilities. It is a valuable verification step.

### 14.1. Verify Does Not Equal a Restore Test

A valid manifest does not prove:
- The WAL archive is complete up to a recovery target.
- The restore host has enough disk/permissions.
- Credentials/KMS keys work.
- The application can connect and business data is valid.
- Timeline/recovery target selection is accurate.

### 14.2. WAL Verification

Some versions/invocations provide options to verify associated WAL. Read `pg_verifybackup --help` and version-specific docs; never assume external WAL archives are automatically verified by the default command alone.

### 14.3. Checksums and Manifests

Checksums detect unexpected file corruption or tampering. They do not replace encryption, immutable storage, or semantic data checks.

## 15. Base Backup Consistency and Required WAL

While a base backup copies files, some pages are written before changes and others afterward. WAL holds the information recovery needs to bring these files to a consistent state.

Required WAL is bounded by the backup process and its start/stop markers. A backup is unrecoverable if mandatory WAL needed to finish consistency recovery is missing.

### 15.1. Base Backups and Archive Chains

A valid base backup normally needs WAL from the backup/recovery start marker to the backup end marker, plus subsequent WAL up to the target time for deeper PITR.

### 15.2. Never Delete Old WAL Simply by Age

WAL retention must account for:
- Which base backups are still retained.
- The recovery window that must be supported.
- Which timelines are needed.
- Standby/replication consumers.
- The backup catalog/retention policy.

A segment older than 7 days may still be mandatory for a base backup kept for 30 days.

### 15.3. A Backup Chain Is a Unit

When expiring a base backup, you can only free WAL exclusively required by that backup if no other backup/consumer needs it. Compute dependencies from metadata, not guesses from file timestamps.

## 16. Archive Command Retries and Failure Handling

If `archive_command` fails, PostgreSQL retries via the archiver loop. Prolonged failures prevent normal WAL recycling and can fill up `pg_wal`.

Causes:
- Archive filesystem out of space.
- Network/object storage outage.
- Expired credentials.
- Permission denied.
- Missing destination path.
- Destination file exists with differing content.
- Script timeout or process crash.
- Transient archive server errors.

### 16.1. Checking Archiver Status

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

### 16.2. Increasing `failed_count` Demands Investigation

Inspect PostgreSQL logs and archive tool logs. Never just reset statistics to turn dashboards green; determine which file failed to archive and why.

### 16.3. An Old `last_archived_time` Is Not Always an Error

If a database generates almost no WAL, there are no new segments to archive. Combine write rates, `archive_timeout`, current WAL segment, and archive queue metrics.

### 16.4. `pg_wal` Growing Continuously

If the archiver falls behind, source WAL cannot be recycled. Check filesystem free space, archive failures, replication slots, and WAL retention settings.

## 17. Monitoring WAL Archiving

A dashboard query:

```sql
SELECT
    archived_count,
    failed_count,
    last_archived_wal,
    last_archived_time,
    last_failed_wal,
    last_failed_time,
    now() - last_archived_time AS time_since_last_archive
FROM pg_stat_archiver;
```

Monitor alongside:
- `pg_wal` disk usage.
- Archive destination growth.
- Archive upload latency/failures.
- WAL generation rate.
- Replication slot retention.
- Streaming replica lag.
- Backup job status.
- Alerts if archive failures persist or backlogs grow.

### 17.1. Do Not Infer Backlog Size Solely from `pg_stat_archiver`

This view provides counters and last success/failure, not a full queue of every pending segment. Pair it with archive storage metrics, server logs, and WAL directory monitoring.

### 17.2. WAL Generation Rate

On the primary, measure LSN delta:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn;
```

Sample over time and compute differences with `pg_wal_lsn_diff`. This measures WAL generated between samples, not exact archive backlog size.

### 17.3. Monitoring Must Produce Actionable Alerts

Alerts should state:
- Database/primary.
- Last successful archive.
- Failure count delta.
- Disk usage.
- Oldest pending segment or estimated backlog.
- Current RPO exposure window.
- Owner/runbook link.

## 18. `archive_timeout` and WAL Switches

`archive_timeout` forces PostgreSQL to switch WAL segments after the configured interval if relevant write activity occurred, ensuring newer WAL gets archived more frequently on low-traffic workloads.

Example:

```conf
archive_timeout = '5min'
```

### 18.1. Not a Commit Timeout

`archive_timeout` does not make transactions wait 5 minutes and is not a transaction durability timeout.

### 18.2. Archived Segments Can Consume Storage

Frequent switches on low-write workloads produce many partially filled segments that still occupy fixed segment size on storage.

### 18.3. Choose Based on RPO and Storage

If maximum archive freshness of 5 minutes is needed, consider an appropriate `archive_timeout`, while measuring resulting WAL volume and archive costs.

### 18.4. `pg_switch_wal`

In labs or investigations, `pg_switch_wal()` can switch to a new segment, making the prior segment eligible for archiving where appropriate:

```sql
SELECT pg_switch_wal();
```

Do not call it continuously in production just to generate extra archive files. Doing so adds overhead/storage without genuinely improving recovery.

## 19. WAL Archive and Streaming Replication

```text
                 PRIMARY
                   |
          +--------+--------+
          |                 |
          v                 v
   Streaming WAL        Archive WAL
          |                 |
          v                 v
      Standby          Archive storage
          |                 |
          +--------+--------+
                   |
              Recovery/DR
```

### 19.1. Streaming Replication

WAL ships nearly continuously to a standby over a replication connection. Latency can be low, yet standbys remain dependent on network, primary, replication settings, and retention.

### 19.2. WAL Archive

The archive holds segments for long-term recovery per retention. It supports standalone restores or standby catch-up fallback when needed.

### 19.3. `archive_timeout` and Replica Lag Differ

Archived segments may wait for segment switches; streaming replication receives WAL earlier. Never use the last archive timestamp as an exact measure of standby replay lag.

### 19.4. Standbys Need Timelines and WAL Continuity

When a standby promotes or fails over, a new timeline emerges. Backups/archives must preserve timeline history files so recovery follows the right history branch.

## 20. Timelines and Timeline History Files

PostgreSQL uses timeline IDs to distinguish branches of WAL history after promotion/recovery.

```text
Timeline 1
    |
    +-- failover / promote
             |
             v
        Timeline 2
             |
             +-- further recovery
                      |
                      v
                  Timeline 3
```

A timeline history file describes where the new branch diverged from the previous timeline.

### 20.1. Why Keep History Files?

When a recovery target specifies `latest` or a specific timeline, PostgreSQL needs to understand branch relationships. Missing history files can select the wrong WAL branch or halt recovery.

### 20.2. Keep More Than Just WAL Segments

Retention must preserve:
- Required WAL segments.
- Timeline history files.
- Base backup metadata/manifests.
- Metadata defining base backups and recovery ranges.

### 20.3. Never Stitch WAL Across Timelines by Renaming

WAL filenames embed the timeline ID. Never rename segments to make a chain appear continuous. Use proper recovery timeline settings and history files.

## 21. What Is PITR?

Point-in-Time Recovery (PITR) restores a base backup and replays WAL up to a chosen timestamp, transaction ID, named restore point, or LSN, per supported recovery targets.

Business example:
- 10:00 backup finishes.
- 10:15 user accidentally deletes data.
- 10:20 error is discovered.
- 10:30 DBA restores base backup and replays WAL to 10:14:59.
- Database is recovered to just before the deletion.

```text
Base backup
   |
   v
Replay WAL 10:00 -> 10:14:59
   |
   v
Pause / promote at target
   |
   v
Recovered database
```

### 21.1. PITR Is Not Rolling Back a Live Transaction

PITR produces a recovered cluster/data directory at the target. It is not an undo command for one transaction inside a running production database.

### 21.2. Recovery Targets Must Be Chosen Carefully

Too late a target includes the destructive operation. Too early a target loses valid transactions afterward. Record timestamp/timezone, LSN, and target events precisely.

### 21.3. Use an Isolated Restore Instance First

In many cases, restore onto a separate host/port/network to inspect data before cutting over production or extracting needed rows.

## 22. Configuring `restore_command`

During recovery, PostgreSQL needs to fetch WAL segments from the archive. `restore_command` is invoked to retrieve requested WAL/history files by name.

Unix example:

```conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
```

- `%f`: filename to retrieve.
- `%p`: destination path requested by PostgreSQL.

This example fits only simple local stores; object storage archives need dedicated clients/tools with retries, credentials, and checksums.

### 22.1. Exit Status

The command must exit 0 upon successful retrieval. If the file does not exist or cannot be fetched, return an appropriate failure status so recovery can check alternative sources or conclude per semantics.

### 22.2. Never Return a File from the Wrong Timeline

The archive tool must fetch the exact requested filename—never substitute the latest segment or alter timeline IDs.

### 22.3. Integrity Checks

Verify checksums/sizes in the archive repository and log source objects. Never recover from truncated or partially uploaded files.

## 23. Recovery Signals and Control Files

From PostgreSQL 12 onward, recovery configuration uses signal files rather than the legacy `recovery.conf`.

A standalone PITR restore typically places `recovery.signal` in the data directory alongside appropriate recovery settings.

```text
restored-data-directory/
  PG_VERSION
  global/
  base/
  pg_wal/
  recovery.signal
  postgresql.auto.conf (may hold settings written by tools)
```

### 23.1. `standby.signal` vs. `recovery.signal`

- `standby.signal`: instructs the server to run as a standby and continue recovery/streaming per config.
- `recovery.signal`: instructs archive recovery/PITR from backup/WAL per settings.

Do not place the wrong signal file expecting the server to guess your intent.

### 23.2. Older PostgreSQL Used `recovery.conf`

Versions prior to PostgreSQL 12 used `recovery.conf` with different configuration rules. Always consult docs for your exact major version.

### 23.3. Signal Files Do Not Generate WAL

You must already possess the base backup and needed WAL archive. Creating `recovery.signal` without required segments does not grant recoverability.

## 24. Example Recovery Settings for PITR

Illustrative configuration:

```conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
recovery_target_time = '2026-11-14 10:14:59+07'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
```

Meaning:
- `restore_command`: fetches WAL/history from the archive.
- `recovery_target_time`: timestamp to stop replay.
- `recovery_target_timeline`: selects the timeline branch.
- `recovery_target_action`: action upon reaching target, such as `pause`.

### 24.1. Explicit Timezone Required

PITR timestamps should specify an explicit timezone. Never enter bare local times and leave the system guessing.

### 24.2. Inclusive/Exclusive Targets

PostgreSQL provides options controlling inclusive/exclusive target boundaries for certain targets. Understand your version's exact semantics before selecting transaction boundaries.

### 24.3. `recovery_target_action`

Common choices include `pause`, `promote`, or `shutdown`, depending on version. `pause` helps inspect state before continuing/promoting; `promote` opens a new timeline; `shutdown` stops the server after reaching target per semantics.

### 24.4. Pausing to Inspect

If recovery pauses at the target, you can connect read-only to verify data per procedure. Before letting applications write, decide on promotion/completion of recovery properly.

## 25. Types of Recovery Targets

Depending on PostgreSQL version, you can use:

| Target | Meaning |
|---|---|
| `recovery_target_time` | Stop at timestamp |
| `recovery_target_xid` | Stop at transaction ID |
| `recovery_target_name` | Stop at named restore point |
| `recovery_target_lsn` | Stop at LSN |
| `recovery_target = immediate` | Stop as soon as the first consistent state is reached per semantics |

### 25.1. Named Restore Point

Before a notable event, create one with:

```sql
SELECT pg_create_restore_point('before_release_2026_11_14');
```

Restore points write a named marker into WAL; the archive must retain the WAL containing that restore point and required preceding segments.

### 25.2. A Restore Point Is Not a Backup

A restore point copies no data files. It merely marks a location in WAL history for recovery.

### 25.3. Transaction ID Target

XID targets have internal semantics and require identifying the exact transaction. Do not confuse database XIDs with application order IDs.

### 25.4. LSN Target

LSN targets are helpful when a specific WAL position was logged. The LSN must belong to the matching cluster/timeline history.

## 26. Timeline Selection After Failover

When recovering onto a new timeline, you may need:

```conf
recovery_target_timeline = 'latest'
```

`latest` asks PostgreSQL to pick the newest timeline reachable via history files. During DR, ensure you know which timeline is authoritative so you do not replay the wrong branch after a failover.

### 26.1. Keep Timeline History

Archive all `.history` files alongside WAL segments. Do not prune them merely because they are tiny or old.

### 26.2. Never Promote Multiple Restored Copies on the Same Branch into Production

Promoting a restored copy creates a new timeline. If multiple copies exist, track timeline/cluster identities strictly to prevent split-brain and archive collisions.

### 26.3. Update the Backup Plan After Promotion

A promoted primary will begin archiving WAL on its new timeline. Verify `archive_mode`, `archive_command`, replication slots, and standby reconfiguration.

## 27. Restoring a Base Backup: General Procedure

A physical/PITR recovery workflow typically follows these steps:

1. Select a valid base backup covering the required WAL window.
2. Verify manifest/checksums and metadata.
3. Prepare host, matching PostgreSQL major version, and storage.
4. Stop the target server if running.
5. Restore the data directory from backup.
6. Restore tablespaces to proper locations/ownership.
7. Configure `restore_command` and recovery targets.
8. Create `recovery.signal` for archive recovery.
9. Start PostgreSQL inside an isolated network.
10. Monitor logs and WAL replay.
11. Inspect data at the target.
12. Pause/promote according to plan.
13. Verify applications/constraints/sequences/replication.
14. Open traffic once consistency and routing are confirmed.

### 27.1. Never Restore Over a Running Data Directory

Verify the target server is stopped and the target path is right. Never overwrite a live cluster.

### 27.2. Ownership and Permissions

Files must have owner/group and permissions matching the PostgreSQL OS user. Tablespace symlinks must point to valid, accessible storage.

### 27.3. Configuration Does Not Always Live Inside `PGDATA`

Some deployments place `postgresql.conf`, `pg_hba.conf`, certificates, and tablespaces outside the data directory. Backup/DR documentation must inventory these dependencies.

### 27.4. Never Open Applications Automatically Upon Server Start

Recovery may not have reached target yet, may be paused, or may sit on the wrong timeline. Open traffic only after verification.

## 28. Tablespaces and External Dependencies

Base backups can include tablespace metadata/mappings. When restoring onto another host, tablespace paths must be prepared appropriately.

A backup plan must record:
- Tablespace names/locations.
- Mapping between source and destination paths.
- Permissions/ownership.
- Mount points and storage classes.
- Capacity.
- Encryption/key dependencies.
- Symlink handling and restore tooling.

### 28.1. `pg_basebackup` and Tablespace Mapping

`pg_basebackup` provides options to map tablespaces to new locations where appropriate. Verify `--tablespace-mapping` and format/version behavior before restoring.

### 28.2. Do Not Back Up Only `PGDATA`

If relation files live in external tablespaces, copying `PGDATA` while skipping tablespaces loses data.

### 28.3. External Files

Large objects reside inside PostgreSQL storage, yet applications may rely on file uploads, object storage, secrets, certificates, or external configs. DR plans must cover these dependencies if full application operation is expected.

## 29. WAL Retention and Backup Retention

A retention policy must guarantee every retained base backup has enough WAL to restore across its committed recovery window.

```text
Base backup A ---------------------> WAL A1 A2 A3 A4 A5
        |                                      |
        +-- restore target needs up to A5 -----+
                                                 
Base backup B ---------------------> WAL B1 B2 B3
        |                                      |
        +-- restore target needs up to B3 -----+
```

### 29.1. Do Not Delete WAL Simply by Age

An old segment can still be mandatory for an older base backup that remains valid. Retention engines must understand backup-to-WAL dependencies.

### 29.2. Backup Expiry

Once a base backup expires, you can delete that backup and WAL no longer required by any retained backup or consumer. Compute deletions from metadata and timelines.

### 29.3. Recovery Window

If policy promises 14-day PITR, ensure:
- Base backups go back far enough to cover the whole window.
- WAL is continuous up to the present.
- Timeline history files are complete.
- Archive storage has sufficient capacity.
- Restore tooling and encryption keys remain functional.

### 29.4. Full/Incremental Backups

Some PostgreSQL versions support incremental base backups with corresponding tools and combine procedures. Incremental chains require metadata and every ancestor backup; never delete a base/parent backup while a child incremental still depends on it.

## 30. WAL Archiving and Disk Pressure in `pg_wal`

If archiving fails, WAL segments can accumulate in `pg_wal` because PostgreSQL cannot recycle them until archived.

Risks:
- Filesystem fills up.
- PostgreSQL cannot write new WAL.
- Transactions/applications fail.
- Replication slows down.
- Backup windows fail.
- The cluster may require emergency intervention.

### 30.1. Capacity Monitoring

Track:
- Filesystem capacity for `PGDATA`/`pg_wal`.
- WAL generation rate.
- `pg_stat_archiver.failed_count`.
- Replication slot retention.
- `max_wal_size`/checkpoint activity.
- Archive destination capacity.

### 30.2. `max_wal_size` Is Not a Hard Cap for All WAL

`max_wal_size` is a soft target governing checkpoints/WAL volume, not a hard quota preventing `pg_wal` from exceeding it. Archive failures or replication slots can pin much more WAL.

### 30.3. Never Manually Delete Files in `pg_wal`

Directly deleting WAL files can break recovery/replication and prevent the cluster from starting. Use PostgreSQL tools/settings and resolve the underlying archiver/slot blocker.

### 30.4. Never Delete Archives to Fix a Full `pg_wal`

The archive and `pg_wal` are separate locations. Resolve the archiver/slot/retention blocker; deleting the archive destroys PITR without solving the root cause.

## 31. Backup Consistency and Filesystem Snapshots

Some platforms offer storage snapshots. They can fit into a backup strategy if PostgreSQL-supported procedures are followed.

### 31.1. Snapshotting One Volume May Not Be Enough

If data files and tablespaces span multiple volumes, snapshots must be consistent across all volumes. Use appropriate quiesce/freeze or backup mode/snapshot coordination.

### 31.2. WAL Must Be Retained

Physical snapshots still require appropriate WAL to recover to a consistent state. Never treat a crash-inconsistent snapshot as a complete backup without a verified recovery workflow.

### 31.3. Managed Database Snapshots

Managed services provide automated backups/PITR. Check provider retention limits, cross-region restore capabilities, encryption key handling, and realistic RTO.

### 31.4. Do Not Force `pg_basebackup` Workflows onto Restricted Services

Some managed services do not expose OS/replication access. Use the service's official backup/restore mechanisms.

## 32. RPO and RTO

Two essential operational objectives:

- **RPO (Recovery Point Objective):** maximum acceptable data loss, usually expressed in time.
- **RTO (Recovery Time Objective):** maximum acceptable time to restore service.

Example:
- RPO = 5 minutes.
- RTO = 60 minutes.

To achieve a 5-minute RPO, WAL archiving/replication must persist required data safely within tight latency; `archive_timeout=5min` alone does not prove a 5-minute RPO.

To achieve a 60-minute RTO, measure end-to-end:
- Host/storage provisioning.
- Base backup transfer/restore.
- WAL replay duration.
- Verification.
- DNS/routing/application startup.
- Data reconciliation and sign-off.

### 32.1. Backup Duration Is Not RTO

A base backup taking 2 hours does not tell you how long restore takes. Only restore tests measure RTO.

### 32.2. Archive Lag Is Not Complete RPO

RPO also depends on commit durability, WAL archiving success, storage guarantees, failure detection, and the target failure scenario.

### 32.3. Measure P95 Restore Time

Run multiple restore drills on representative sizes/datasets to build reliable estimates.

## 33. Restore Drills: Proving Backups Are Usable

An untested backup is merely an assumption.

A drill can:
1. Pick a base backup from the repository.
2. Pick a target time/LSN/restore point.
3. Provision an isolated environment.
4. Restore files and tablespaces.
5. Replay WAL.
6. Confirm the recovery target.
7. Verify schemas, row counts, constraints, and application smoke tests.
8. Record durations per phase.
9. Verify keys/credentials/permissions.
10. Clean up the drill environment per policy.

### 33.1. Test Restores Must Use Real Archives

Testing with a specially curated standalone archive does not prove the production archive has complete segments/timelines/permissions.

### 33.2. Test Failure Cases Too

- Missing WAL segment.
- Corrupted object checksum.
- Expired credentials.
- Missing tablespace.
- Recovery target past the last available WAL.
- Missing timeline history.
- Insufficient disk space.
- Wrong PostgreSQL major version.

The goal is uncovering gaps while there is still time to fix them.

### 33.3. Never Let Drills Touch Production Traffic

The restored instance must stay isolated so applications cannot accidentally write to it or read stale restored data as live production.

### 33.4. Record Results

Log backup ID, target, start/end timestamps, WAL range, timeline, verification results, issues found, and operator name.

## 34. Backup Catalog and Metadata

A minimal backup catalog should track:

- Backup ID/label.
- PostgreSQL version/major.
- Source cluster/system identifier.
- Start/end timestamps.
- Start/stop LSN if available.
- Timeline.
- Backup format.
- Base backup path/object IDs.
- Manifest/checksum status.
- Required WAL range.
- Tablespace mappings.
- Encryption key reference.
- Retention expiry.
- Verification/restore drill status.

### 34.1. System Identifier

The system identifier tracks cluster lineage. Inspect it with `pg_controldata` on compatible data directories/backups. Never mix backups/WAL from different clusters simply because database names match.

### 34.2. Backup Labels and Manifests

Preserve metadata files created by backup tools. Never rename/delete them without understanding the impact on restore/verification.

### 34.3. Backup IDs Must Be Immutable

Never reuse a fixed folder name that overwrites an older base backup. Use unique IDs/timestamps and a catalog to track status.

## 35. Full, Incremental, and WAL-Only Retention

A strategy may include:
- Periodic base backups.
- Incremental backups if supported by version/tooling.
- Continuous WAL archive.
- Logical dumps on a separate schedule.

### 35.1. Full Base Backups

Easy to understand and usually the simplest baseline, though higher in storage/network/time cost.

### 35.2. Incremental Backups

Can reduce copied data, though restores must combine chains properly with matching tools. Keep all required ancestors/base backups.

### 35.3. WAL-Only Is Not a Complete Backup

Keeping WAL without a valid base backup provides no starting point to rebuild a cluster from scratch.

### 35.4. Full Backup Without WAL Archive

Can restore to the backup's consistency point if backup-internal WAL is packaged per workflow, but cannot perform continuous PITR to later timestamps.

## 36. Archive Cleanup and `pg_archivecleanup`

`pg_archivecleanup` helps delete archived WAL older than a specified segment in certain standby/archive cleanup workflows.

Usage example:

```bash
pg_archivecleanup /srv/pgarchive 0000000200000000000000A5
```

This is illustrative; never run it on an archive repository serving multiple base backups/PITR consumers without computing dependencies first.

### 36.1. Cleanup Needs to Know the Oldest Required WAL

If the oldest retained base backup needs WAL starting at segment A1, never delete A1 simply because a standby has already replayed past A5.

### 36.2. Multiple Consumers Require Unified Retention

An archive may serve multiple standbys, base backups, and PITR windows. Cleanup must retain segments needed by whichever consumer has the longest requirement.

### 36.3. Object Storage Lifecycle Policies Can Be Dangerous

An automated lifecycle rule deleting objects after 7 days can break a 30-day backup. Object store retention must align with the backup catalog.

## 37. Backups with a Standby

You can take base backups from a standby in supported configurations/versions to offload reads from the primary. However, understand:
- WAL receiver/replay state.
- WAL sender capacity on the standby.
- Backup consistency and WAL availability.
- Tablespace paths.
- Replication lag.
- Failover/timeline history.
- Backup tool limitations when sourcing from a standby.

### 37.1. Standby Backups Do Not Replace Primary WAL Archiving

Ensure WAL archives and timeline history suffice for restore objectives. Depending on point and workflow, a standby backup may need WAL from primary/archive.

### 37.2. Backing Up from a Standby Does Not Eliminate I/O

The standby still reads data files and can impact queries/reporting running on that replica.

### 37.3. Measure Standby Load Separately

Monitor replica query latency, replay lag, and backup throughput.

## 38. WAL Archive Encryption and Key Lifecycle

If client-side encrypting the WAL archive:
- Use appropriate authenticated encryption.
- Attach metadata identifying key version/nonce/algorithm per object/file.
- Store keys outside the archive repository.
- Maintain key rotation without breaking decryption of older retained files.
- Ensure restore hosts have scoped access to fetch keys.
- Test decryption during restore drills.
- Protect logs so plaintext/credentials never leak.

### 38.1. Losing Keys Means Losing Backups

An object with an intact checksum that cannot be decrypted still fails recovery. Key recovery is mandatory in DR.

### 38.2. Cloud Encryption at Rest Does Not Mitigate Every Threat

If an attacker steals credentials with object read access, the service decrypts plaintext for them. Consider client-side encryption and separation of duties.

### 38.3. Never Silently Change Archive Formats

Changing encryption/compression wrappers must preserve readability of every backup still inside its retention window.

## 39. Compression and Bandwidth

WAL archives can be compressed via:
- External archival tools.
- Object storage compression if supported.
- Built-in WAL compression for certain WAL contents, depending on settings/versions.

Distinguish `wal_compression` from whole-file WAL archive compression: `wal_compression` primarily compresses full-page images inside WAL records, rather than gzipping entire segment files.

### 39.1. Compression Trade-Offs

- Reduces storage/network usage.
- Increases CPU usage.
- Adds decompression steps on restore.
- Requires version/format compatibility.
- Requires post-decompression integrity verification.

### 39.2. Measuring Compression Ratios

Track raw vs. compressed sizes by segment/time to know actual savings. WAL holds varied record types with differing compressibility.

### 39.3. Restore Throughput

An archive that compresses tightly yet decompresses slowly can hurt RTO. Measure end-to-end, not just storage savings.

## 40. Failure Scenarios and Responses

| Incident | Symptoms | Action |
|---|---|---|
| `archive_command` failing | `failed_count`/log errors rising | Fix permissions/network/storage, check pending WAL |
| Archive storage full | Upload/copy failures, capacity alert | Add capacity/clean up per dependencies, never delete blindly |
| Missing WAL segment | Recovery halts at missing segment | Check alternate copies/replicas/archives, document true RPO |
| Corrupted base backup | Manifest/checksum mismatch | Use another backup, investigate storage pipeline |
| Lost encryption key | Archive fails decryption | Recover key via escrow/KMS DR |
| Slow/long backup | I/O and latency spikes | Adjust windows/throttling/checkpoint settings |
| Abnormal `pg_wal` growth | Filesystem usage climbing | Check archiver and replication slots |
| Timeline mismatch | Recovery misses WAL branch | Inspect `.history` files and `recovery_target_timeline` |
| Restored to wrong target | Unwanted post-incident data remains | Pick earlier target, re-run isolated restore |
| Restore host out of disk | Copy/replay fails | Capacity plan; never start live traffic |
| Standby lag | Replay LSN falling behind | Inspect network, WAL sender, I/O, replay workload |
| Retention deleted needed WAL | PITR window broken | Halt cleanup, check replicas/offsite copies, fix policy |

### 40.1. Resolve Archive Failures Before `pg_wal` Fills Up

Alerts must fire early enough for DBAs to intervene before filesystem exhaustion. Monitor both WAL generation rate and remaining free space.

### 40.2. Never Manually Delete WAL

Never run `rm`/file managers to delete files inside `pg_wal`. For archives, prune strictly through a dependency-aware retention engine.

### 40.3. When WAL Is Missing, Do Not Pretend PITR Is Intact

You may still recover up to just before the missing segment if the base backup and prior WAL chain are valid. State true RPO and potential data loss explicitly.

## 41. Runbook: Creating and Verifying Base Backups

**Step 1 — Verify source**

- Cluster/version/system identifier.
- Primary/standby source.
- Tablespaces and data directory.
- WAL/archive health.

**Step 2 — Verify destination**

- Free space.
- Access permissions.
- Encryption/credentials.
- Independent failure domain.
- Unique backup ID.

**Step 3 — Run `pg_basebackup`**

Select matching format and WAL method; log progress, start/end times, and exit status.

**Step 4 — Verify backup**

- Manifest/checksums.
- File inventory.
- Tablespace mappings.
- WAL coverage.
- Catalog metadata.

**Step 5 — Record in catalog**

Save ID, version, timeline, LSN range, retention expiry, and verification result.

**Step 6 — Restore drill**

Execute regularly in an isolated environment to measure RTO and verify the WAL chain.

## 42. Runbook: Handling Archive Failures

1. Check `pg_stat_archiver` and PostgreSQL logs.
2. Identify `last_failed_wal`, failure timestamp, and failure count delta.
3. Check archive destination capacity.
4. Check permissions, credentials, network, and object store health.
5. Check whether `archive_command` returns proper exit codes.
6. Check if destination file already exists and whether checksums match.
7. Fix the root cause.
8. Let PostgreSQL retry or use supported procedures to restore archive state.
9. Verify `archived_count` advances and `last_archived_wal` updates.
10. Verify `pg_wal` usage stabilizes.
11. Document archive outage duration and RPO exposure.

Never reset statistics or delete WAL to mask an incident.

## 43. Runbook: PITR After Accidental Data Deletion

1. Stop or isolate the application issuing destructive writes to prevent further damage.
2. Record event timestamp and timezone.
3. Determine a target preceding the destructive transaction.
4. Pick the latest base backup with continuous WAL coverage up to the target.
5. Verify manifest, timeline, and encryption keys.
6. Restore onto an isolated host/data directory.
7. Configure `restore_command`, `recovery.signal`, and target settings.
8. Start the server and monitor WAL replay and logs.
9. Pause at target if inspection is required.
10. Verify data, constraints, sequences, roles, and application queries.
11. Decide between full cluster recovery or selective data extraction.
12. Promote/complete recovery per plan.
13. Reconfigure replication and archiving for the new timeline.
14. Switch traffic only after validation and operational approval.

### 43.1. Why Restore to a Separate Environment First?

You may only need to extract specific rows or inspect data without replacing all of production. Isolated restores prevent overwriting valid writes made after the target.

### 43.2. What If Applications Kept Writing After the Incident?

Reconciliation is required: keep valid writes, extract lost records from the restored copy, or cut over at a clean boundary. PITR does not automatically merge two histories.

## 44. Backup/DR Checklist

| Item | What to Confirm |
|---|---|
| Base backup | Created with `pg_basebackup` or supported snapshot procedure |
| WAL archiving | `archive_mode` and `archive_command`/`archive_library` healthy |
| WAL continuity | No missing segments/history in recovery window |
| Backup manifest | Present and verified where supported |
| System identity | Matches target cluster/version |
| Tablespaces | Paths/mappings documented |
| Credentials | Backup/archive accessible in DR |
| Encryption keys | Escrow/KMS recovery and decryption tested |
| Offsite | Independent failure domain |
| Immutability | Protected against accidental deletion/ransomware |
| Retention | Keeps required base backups and WAL dependencies |
| Archive monitoring | Alerts on `failed_count`/last archived/queue |
| `pg_wal` capacity | Alerts before filesystem fills |
| Replication slots | Monitors inactive slots and retained WAL |
| Timeline history | Preserves `.history` files |
| `restore_command` | Tested against real archive |
| Recovery target | Timestamp/LSN/timezone specified |
| Restore drills | Recorded with real measured RTO |
| RPO | Archive freshness and commit durability match target |
| RTO | Host, transfer, replay, and validation measured |
| Application | Post-restore smoke tests exist |
| Roles/config | Globals and required external configs backed up |
| Runbook | Owner, escalation, and verification steps defined |

## 45. Practice Exercises with Answers

### Exercise 1. What is a base backup?

**Answer:** A consistent physical copy of a cluster/supported scope that can combine with WAL to complete recovery.

### Exercise 2. Why not copy a running `PGDATA` with ordinary file-copy commands?

**Answer:** Files can be copied at inconsistent instants; without the backup protocol/WAL consistency, the copy may be unrecoverable.

### Exercise 3. How do physical backups and logical backups differ?

**Answer:** Physical backups copy storage-level cluster files; logical backups export objects/data into a restorable/importable representation.

### Exercise 4. Does `pg_dump` provide continuous PITR?

**Answer:** No. `pg_dump` creates logical dumps and does not replace base backups + continuous WAL archives.

### Exercise 5. What is WAL?

**Answer:** The Write-Ahead Log recording ordered changes for recovery/replication.

### Exercise 6. Is an LSN a timestamp?

**Answer:** No. An LSN is a position inside the WAL stream.

### Exercise 7. What is a common WAL segment size?

**Answer:** Many builds default to 16 MiB, though you must verify the exact build/server size.

### Exercise 8. Are WAL archiving and streaming replication identical?

**Answer:** No. One stores segments in an archive repository; the other streams WAL to a live standby.

### Exercise 9. Does `archive_mode = on` usually require a restart?

**Answer:** Yes, changing `archive_mode` typically requires a server restart.

### Exercise 10. What are `%p` and `%f` in `archive_command`?

**Answer:** `%p` is the full source path; `%f` is the WAL filename.

### Exercise 11. What does returning exit 0 from `archive_command` mean?

**Answer:** PostgreSQL treats the segment as successfully archived; return 0 only after the file is durably persisted as required.

### Exercise 12. Why must `archive_command` be idempotent?

**Answer:** PostgreSQL may retry the same file after errors/restarts; it must neither corrupt files nor overwrite silently.

### Exercise 13. Does archive storage on the same disk as `PGDATA` protect against disasters?

**Answer:** No. One disk/host failure can destroy both.

### Exercise 14. What does `pg_basebackup -X stream` do?

**Answer:** Streams required WAL during the base backup, bundling necessary WAL under that method.

### Exercise 15. Does `-X none` guarantee PITR?

**Answer:** No. Another workflow must ensure required WAL and continuity.

### Exercise 16. Does `pg_basebackup -R` mean PITR to a timestamp?

**Answer:** No. It generates configuration to run the backup as a standby per tool/version semantics.

### Exercise 17. What privileges does a backup user need?

**Answer:** Typically `LOGIN` and `REPLICATION` plus matching `pg_hba` rules; details vary by version/config.

### Exercise 18. Should passwords be passed on the command line?

**Answer:** No. Use protected credential stores/password files or secret providers.

### Exercise 19. Do replication slots archive WAL automatically?

**Answer:** No. Slots retain WAL for consumers; the archive process copies WAL into the archive repository.

### Exercise 20. Can an inactive slot retain WAL?

**Answer:** Yes. Slots can pin `restart_lsn`/`xmin` and increase resource usage.

### Exercise 21. Does `pg_verifybackup` prove complete restorability?

**Answer:** No. It checks backups against manifests/checksums; restore drills are needed to prove WAL chains, keys, tablespaces, and application functionality.

### Exercise 22. Does `pg_stat_archiver` show the entire archive queue?

**Answer:** No. It provides counters and last success/failure; storage/log/WAL monitoring is also needed.

### Exercise 23. What can a prolonged archive failure do to `pg_wal`?

**Answer:** WAL fails to recycle on schedule and `pg_wal` can grow until the filesystem fills up.

### Exercise 24. Is `max_wal_size` a hard quota?

**Answer:** No. It is a soft checkpoint target; slots/archive failures can push WAL past it.

### Exercise 25. Is `archive_timeout` a transaction timeout?

**Answer:** No. It forces WAL segment switches to archive newer WAL more frequently.

### Exercise 26. Should `pg_switch_wal()` be called continuously?

**Answer:** No. Switching too often increases segment count/archive volume and overhead.

### Exercise 27. What is PITR?

**Answer:** Restoring a base backup and replaying WAL to a specific recovery target.

### Exercise 28. Is PITR a rollback of a single production transaction?

**Answer:** No. It normally creates a cluster recovered to the target; you extract data or cut over per procedure.

### Exercise 29. How does `restore_command` use `%f` and `%p`?

**Answer:** `%f` is the requested filename; `%p` is the destination path requested by PostgreSQL.

### Exercise 30. Which file does PostgreSQL 12+ use for archive recovery?

**Answer:** `recovery.signal`; standbys use `standby.signal`. Prior versions used `recovery.conf`.

### Exercise 31. Should `recovery_target_time` include a timezone?

**Answer:** Yes. Specify an explicit timezone to avoid picking the wrong moment.

### Exercise 32. What does `recovery_target_timeline = 'latest'` do?

**Answer:** Instructs PostgreSQL to pick the newest reachable timeline per history files; still verify the intended DR branch.

### Exercise 33. Is a restore point a base backup?

**Answer:** No. It marks a location in WAL.

### Exercise 34. Why must `.history` files be preserved?

**Answer:** They describe relationships between timelines so recovery selects the correct WAL branch.

### Exercise 35. Can WAL archives be deleted after 7 days if base backups are kept for 30 days?

**Answer:** No if base backups still need WAL older than 7 days to recover; retention must track dependencies.

### Exercise 36. Is `VACUUM FULL` related to backups?

**Answer:** It is not a backup; it rewrites tables and generates I/O/WAL whose impact on backups/replication must be considered.

### Exercise 37. How does RPO differ from RTO?

**Answer:** RPO is maximum acceptable data loss; RTO is maximum time to restore service.

### Exercise 38. Does `archive_timeout=5min` prove a 5-minute RPO?

**Answer:** No. RPO also depends on archive success, storage durability, commit behavior, and failure mode.

### Exercise 39. Is a backup that succeeded yet never restored trustworthy?

**Answer:** No. Regular restore drills with real archives are needed.

### Exercise 40. What should a restore drill measure?

**Answer:** Backup ID, target, WAL range/timeline, transfer/restore/replay/verification durations, errors, RTO, and data/application checks.

### Exercise 41. What if an archive file already exists with a different checksum from the source?

**Answer:** Never overwrite silently or return success; fail and investigate collision/corruption.

### Exercise 42. Should you manually delete WAL files in `pg_wal` when disk is nearly full?

**Answer:** No. That can break recovery/replication and corrupt the cluster.

### Exercise 43. What must be done for a base backup with tablespaces outside `PGDATA`?

**Answer:** Record/map and restore all tablespaces to proper paths, ownership, and permissions.

### Exercise 44. What happens if an encryption key is lost while the backup checksum is valid?

**Answer:** The backup cannot be decrypted; key recovery is a mandatory part of DR.

### Exercise 45. Does a fast-replaying standby mean the archive also saved the WAL?

**Answer:** No. Streaming replication and archiving are separate paths; monitor both.

### Exercise 46. Does `wal_compression` gzip entire WAL archive files?

**Answer:** No. It mainly compresses full-page images inside WAL records; archive file compression is separate.

### Exercise 47. Can an older PG major version restore directly from a newer major version's data directory?

**Answer:** Not via normal startup; physical backups require major-version compatibility, and major upgrades use dedicated workflows.

### Exercise 48. Once PITR finishes, should traffic open immediately?

**Answer:** No. Verify target/timeline, data, sequences, roles, application behavior, and replication first.

## 46. Backup + WAL Policy Design Checklist

| Question | Required Evidence |
|---|---|
| Which tool creates base backups? | `pg_basebackup`/managed snapshot procedure |
| Does the backup match cluster/version? | Version and system identifier |
| What WAL method is used? | `stream`/`fetch`/`none` and rationale |
| Is `archive_command`/`archive_library` retry-safe? | Exit status/idempotency tests |
| Is archive storage in an independent failure domain? | Architecture/network/storage |
| Is there an offsite/immutable copy? | Retention/immutability policy |
| Do encryption keys have DR? | Escrow/KMS recovery test |
| Are WAL segments continuous? | Archive inventory/monitoring |
| Is timeline history preserved? | `.history` objects |
| Are backup manifests verified? | `pg_verifybackup` output |
| Are tablespaces mapped? | Backup catalog/runbook |
| Does retention preserve required WAL? | Dependency graph/catalog |
| Is `pg_wal` disk monitored? | Filesystem alerts |
| Are archive failures alerted? | `pg_stat_archiver`/logs |
| Are replication slots monitored? | Slot inventory/retention |
| Has RPO been measured? | Archive lag/durability evidence |
| Has RTO been measured? | Restore drill durations |
| Do restore targets specify timezone? | Runbook |
| Do restore drills use isolated networking? | DR test environment |
| Are application checks run post-restore? | Smoke tests/data validation |
| Does the backup catalog have full metadata? | Backup ID/LSN/timeline/keys |
| Was restore tested against real archives? | Drill report |

## 47. Official PostgreSQL Documentation

- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html) — base backups, WAL archiving, PITR, and restores.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — creating physical base backups.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html) — verifying base backup manifests/checksums.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — `wal_level`, `archive_mode`, `archive_timeout`, and WAL settings.
- [Archive Recovery Settings](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET) — recovery targets and restore settings.
- [pg_stat_archiver](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ARCHIVER-VIEW) — archive statistics.
- [pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html) — slot states and retained WAL.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — logical backups.
- [pg_dumpall](https://www.postgresql.org/docs/current/app-pg-dumpall.html) — globals and multiple databases.
- [WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html) — WAL records, segments, and LSNs.
- [pg_create_restore_point](https://www.postgresql.org/docs/current/functions-admin.html) — creating named restore points.

Syntax, recovery parameters, `archive_library`, incremental backups, and certain view fields vary by PostgreSQL version. Before applying, verify `server_version`, `pg_settings`, `pg_basebackup --help`, and documentation for the exact major version in production.

## 48. Summary

```text
1. Create a consistent physical base backup
              |
              v
2. Continuously archive WAL segments
              |
              v
3. Retain sufficient WAL + timeline history per policy
              |
              v
4. Verify manifests/checksums and archive continuity
              |
              v
5. Restore base backup on the target environment
              |
              v
6. Use restore_command to fetch WAL
              |
              v
7. Replay to recovery target / PITR
              |
              v
8. Verify data, applications, and RPO/RTO
```

Key principles to remember:

1. **The base backup is the starting point; the WAL archive is the sequence of changes.** PITR requires both, and WAL must be continuous.
2. **Never arbitrarily copy a running `PGDATA`.** Use `pg_basebackup` or a supported snapshot procedure.
3. **WAL archiving differs from streaming replication.** Monitor and design retention for both paths.
4. **`archive_command` returns success only after the file is durably stored.** It must be retry-safe, idempotent, and detect collisions.
5. **Never delete WAL solely by age.** Retain every segment/timeline history required by active base backups.
6. **Choose `pg_basebackup`'s WAL method intentionally.** `stream`, `fetch`, and `none` have distinct requirements.
7. **Monitor archive failures and `pg_wal` capacity.** A prolonged archive outage can fill the filesystem.
8. **Timeline history is part of the recovery chain.** Never rename or splice WAL across branches.
9. **PITR requires explicit targets/timezones.** Restore into an isolated environment and verify before cutover.
10. **Encryption keys, tablespaces, roles, and configs are part of DR too.** Backup files alone are insufficient.
11. **RPO/RTO must be measured through restore drills.** `pg_verifybackup` is one verification step, not a substitute for test restores.
12. **Retention must understand dependencies.** Delete base backups/WAL only when no recovery consumer needs them.

**One sentence to remember:** *A base backup lays the recovery foundation; the WAL archive bridges that foundation to later points in time. Only when the backup chain, WAL, timelines, keys, and restore procedures are verified together does PostgreSQL have a trustworthy PITR strategy.*
