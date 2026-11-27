# Monitoring Backup Failures and Organizing Recovery Drills in PostgreSQL

## 1. Backups Only Have Value When Recoverable

A PostgreSQL system can report that a backup job succeeded, yet that does not prove the database can recover. A backup file might miss required WAL, archiving might have stalled, the manifest might be invalid, the encryption key might be unreachable, or the backup might come from a different cluster. An issue discovered only when a restore is needed turns a backup into an unverified assumption.

Backup management therefore requires two parallel control loops:

1. **Monitoring backup creation and protection:** did the job run on schedule, produce complete artifacts, archive WAL continuously, store metadata/checksums, and retain data per retention policy?
2. **Verifying recoverability:** can a PostgreSQL instance be spun up from the backup, replay WAL to the intended target, pass database and application checks, and measure real duration?

This lesson focuses on detecting failures early, understanding monitoring signals, investigating root causes, and organizing evidence-backed recovery drills. It applies to physical base backups, WAL archiving/PITR, and logical backups like `pg_dump`, while highlighting differences across backup types.

### 1.1. Learning Outcomes

After this lesson, you will be able to:

1. Define RPO/RTO targets and translate them into backup, archive, and restore test schedules.
2. Distinguish physical base backups, WAL archives, and logical backups.
3. Identify key signals in `pg_stat_archiver`, `pg_stat_wal`, replication views, and PostgreSQL logs.
4. Monitor job status, backup catalogs, manifests, checksums, and retention.
5. Classify backup failures by scheduling, permissions, storage, networking, archiving, WAL continuity, and restore.
6. Detect archive backlogs, WAL-pinning replication slots, and disk exhaustion risks.
7. Verify base backups and WAL chains with appropriate tools.
8. Organize restore tests, PITR drills, failover/disaster recovery drills, and tabletop exercises.
9. Measure actual RTO/RPO, store evidence, and remediate post-drill findings.
10. Write runbooks for backup or recovery failures.

### 1.2. Operational Principles

- A successful backup job does not guarantee a successful restore.
- Having a base backup without required WAL means you may fail to recover to the desired target.
- Having a WAL archive without a matching base backup is insufficient to rebuild a cluster.
- A restore that boots PostgreSQL does not mean the application has valid data or can serve traffic.
- Drills must measure timings and verify outcomes—not merely check off a checklist.
- Never test restores over production during a routine drill.
- Never manually delete WAL, backups, or replication slots solely to lower disk usage.

---

## 2. Backup Types and Recovery Scope

### 2.1. Physical Base Backup

A physical backup is a physical copy of the PostgreSQL cluster/data directory made via a supported method. An appropriate base backup combined with required WAL can recover the cluster to a point within a continuous WAL window.

The standard PostgreSQL tool is `pg_basebackup`; production systems may also use backup managers or storage snapshots integrated with the PostgreSQL backup protocol. Backup creation must guarantee consistency and capture required metadata.

### 2.2. WAL Archiving

A WAL archive stores completed WAL segments in a separate repository so they can replay after a base backup. For continuous archiving/PITR, the system requires:

- A valid base backup.
- A continuous WAL chain from the backup to the recovery target.
- Necessary timeline history when promotions/failovers occurred.
- Proper recovery configuration/target.
- Accessible and decryptable archive storage.

Missing one mandatory segment can stop recovery before the target even if the base backup and all other segments exist.

### 2.3. Logical Backup

`pg_dump` creates a logical dump of database objects/data; `pg_dumpall` dumps cluster-wide globals and database definitions separately. Logical backups fit:
- Restoring selected databases or objects.
- Migrating across compatible versions/architectures.
- Independent schema/data inspection.
- Recovering specific objects where full-cluster physical restore is overly broad.

A logical dump **is not a physical base backup** and does not produce a WAL archive chain for PITR via the same mechanism. A logical backup can be snapshot-consistent within its scope, yet does not replace physical recovery plans when RTO/RPO demands rebuilding an entire cluster.

### 2.4. Storage Snapshots

Volume/VM snapshots can be helpful when the snapshot workflow coordinates properly with PostgreSQL consistency, WAL, and storage semantics. A crash-consistent snapshot does not automatically equal a valid base backup. Verify provider guarantees, quiesce/freeze procedures, snapshot consistency groups, and restore instructions.

### 2.5. Comparison Table

| Method | Scope | PITR Capability | Best Used For |
|---|---|---|---|
| Physical base backup + WAL archive | Whole cluster/physical files | Yes, with continuous WAL chain | Disaster recovery, PITR, standby seeding |
| `pg_dump` | One database/logical objects | Not via WAL archive chain | Logical restore, migration, object-level recovery |
| `pg_dumpall` | Globals and databases via logical dump | Does not replace physical PITR | Cluster logical export |
| Properly integrated storage snapshot | Volume/instance per snapshot design | Depends on WAL integration | Fast recovery/cloning when consistency is guaranteed |
| Replica/standby | Continuously updated copy | Not an independent backup | HA/failover, lowering RTO when eligible |

### 2.6. Replicas Do Not Replace Backups

Replicas replicate accidental `DELETE`s, bad `UPDATE`s, logical corruption, and committed destructive operations. A replicated operator mistake can destroy data on both primary and standby right along with WAL. You need independent backups, retention, and recovery to a point before the incident.

### 2.7. Matching Requirements to Incident Types

| Incident | Mechanism to Consider |
|---|---|
| Loss of one database/object | Logical restore or object-level recovery from dump |
| Primary host failure/loss | Physical base backup + WAL or eligible standby |
| Accidental deletion of committed data | PITR to before deletion, or restore into isolated environment to extract data |
| Storage/region failure | Offsite backup, WAL archive, and provisioning workflow at another site |
| Schema/deployment error | PITR or isolated restore for comparison; may require application rollback |
| Ransomware/credential compromise | Immutable/offline backups, separated permissions, and clean-room recovery |

---

## 3. RPO, RTO, and Data Protection Objectives

### 3.1. RPO — Recovery Point Objective

**RPO** is the maximum data loss an organization tolerates, typically expressed in time. With a 15-minute RPO, the goal during an incident is recovering to a point no older than 15 minutes before the incident, per the organization's agreed measurement rules.

RPO must be set per system/dataset. Not every database needs zero RPO; targets must balance cost, architecture, and business impact.

### 3.2. RTO — Recovery Time Objective

**RTO** is the maximum acceptable time to bring a service back to an operational state under defined criteria. Define measurement start and end points clearly:

- Start: when the incident is declared or when the service went down?
- End: when the PostgreSQL process starts, when the app connects, or when users complete critical transactions?

Business RTO usually includes infrastructure, restore, WAL replay, validation, DNS/routing, secrets/configs, smoke tests, and opening traffic.

### 3.3. RPO Is More Than Backup Scheduling

Suppose base backups run nightly and WAL archiving runs continuously. RPO can be far lower than 24 hours if WAL archives safely and continuously. Conversely, running hourly full backups does not guarantee a 1-hour RPO if backup jobs or WAL archiving fail silently for hours.

### 3.4. RTO Is More Than Backup Read Speed

Restore time depends on:
- Data directory size.
- Storage/network throughput.
- Volume of WAL segments to replay.
- Target host CPU and I/O.
- Recovery target.
- Extensions, tablespaces, configurations, and credentials.
- Data/application validation duration.
- DNS, routing, failover, and access-granting procedures.

### 3.5. Setting Measurable Targets

Example for a hypothetical service:

| Metric | Illustrative Target |
|---|---|
| RPO | No more than 15 minutes |
| RTO | No more than 90 minutes |
| Base backup | Daily |
| WAL archive | Continuous, monitor backlog by minute |
| Restore drill | Monthly |
| PITR drill | Quarterly and after backup pipeline changes |
| Offsite copy | Independent copy per policy |
| Restore check | Automated minimum per new backup sample; periodic full restore |

These numbers merely illustrate translating targets into schedules. Each organization must choose based on business impact and actual capabilities.

### 3.6. Measuring Actual RPO

One way to estimate current RPO is finding the timestamp of the latest WAL safely persisted in the archive or an accessible recovery location, then comparing to now. Timestamps alone can be insufficient: verify the WAL chain is continuous on the right timeline.

Actual RPO at a point in time should reflect:
1. Archive/backup metadata.
2. LSN/timeline continuity.
3. Corresponding timestamps where determinable.
4. Actual restore/PITR verification.

### 3.7. Measuring Actual RTO

Measure from recovery workflow start until defined **service recovery criteria** are met. Log milestones separately:
- Provision infrastructure.
- Fetch/decrypt backup.
- Restore base backup.
- Replay WAL.
- Start PostgreSQL.
- Validate database.
- Validate application.
- Route traffic.
- Business sign-off.

This breakdown reveals whether bottlenecks lie in storage, recovery, validation, or coordination.

---

## 4. Backup Lifecycle and Observation Points

### 4.1. Physical Backup Flow

~~~text
Schedule / Orchestrator
        |
        v
Start base backup
        |
        +----> Copy data files / tablespaces
        |
        +----> Capture backup metadata / manifest
        |
        v
Complete base backup
        |
        v
Verify files, checksums, catalog
        |
        +---------------------------+
        |                           |
        v                           v
Archive WAL continuously       Copy to offsite/immutable storage
        |                           |
        +-------------+-------------+
                      |
                      v
             Retention / lifecycle
                      |
                      v
             Restore & recovery drills
                      |
                      v
              Evidence / sign-off
~~~

### 4.2. Job States Go Beyond Success/Failure

A backup job should track granular states for investigation:

- `scheduled`: scheduled to run.
- `started`: started.
- `running`: actively running.
- `completed`: process exited cleanly.
- `verified`: artifacts passed integrity checks.
- `cataloged`: metadata recorded in backup catalog.
- `replicated/offsite`: copy reached independent storage.
- `restore_tested`: successfully restored in a recent test.
- `failed`: job failed.
- `partial`: some artifacts succeeded while others are missing.
- `expired/pruned`: past retention and deleted per policy.

Not every tool exposes all of these natively; map them into an internal job catalog.

### 4.3. Every Backup Needs Metadata

Record at least:
- Unique backup ID.
- Cluster/system identifier.
- PostgreSQL major version and build/tool versions.
- Backup type (physical/logical/snapshot).
- Start/end timestamps.
- Start/stop LSNs if available.
- Timeline.
- Source host/cluster/environment.
- Tablespaces and manifest/checksum metadata.
- WAL range required for backup recovery.
- Encryption/key identifier (never store secrets).
- Storage locations and object versions.
- Retention/expiration date.
- Verification result and restore drill reference.

### 4.4. Backup Catalog

The backup catalog tracks backup sets, dependencies, WAL ranges, status, and retention. It may reside inside a backup manager or dedicated management system.

The catalog should:
- Assign unique, non-reused backup IDs.
- Be backed up/replicated independently.
- Store enough metadata to pick base backups and WAL chains.
- Distinguish in-progress uploads from verified copies.
- Log failure history and remediation.
- Never treat old success metadata as proof files still exist in object storage.

### 4.5. Artifact Inventory

On each backup, reconcile expected files/objects against what actually exists. Check:
- Plausible file counts/sizes.
- Complete tablespace links/objects.
- Manifest present and readable.
- Checksums/sizes match.
- Required WAL present.
- Timeline history preserved.
- Encryption metadata/key versions available.

### 4.6. End-to-End Ownership

A job spans scheduler, backup agent, database, archive process, object storage, and catalog. Assign clear ownership per step. A component logging "request accepted" never means the artifact is durable at the destination.

---

## 5. Signal Sources Inside PostgreSQL

### 5.1. `pg_stat_archiver`

The `pg_stat_archiver` view tracks WAL archiver status. Example:

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

Key columns:
- `archived_count`: successful archives recorded since stats reset.
- `last_archived_wal`: name of the most recently archived WAL file.
- `last_archived_time`: timestamp of the most recent successful archive.
- `failed_count`: failed archive attempts recorded.
- `last_failed_wal` and `last_failed_time`: WAL file/timestamp of the latest failure.
- `stats_reset`: timestamp counters were reset.

### 5.2. Counters Do Not Replace Freshness Alerts

An increasing `archived_count` shows successes occur, yet does not prove archiving is keeping pace. During high WAL generation, archive successes can coincide with a growing backlog. Also monitor:
- Elapsed time since `last_archived_time`.
- Current WAL position.
- Pending WAL segment/file queue if reported by archive tooling.
- Disk usage of `pg_wal`.
- Archive destination health.
- Failure counters and log events.

### 5.3. Stats Resets

Counters can be reset; post-reset, `failed_count=0` does not prove no prior failures occurred. Record `stats_reset` and treat counters as reset-aware time series.

### 5.4. `pg_stat_wal`

~~~sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    wal_write,
    wal_sync,
    stats_reset
FROM pg_stat_wal;
~~~

Columns can differ across major versions. Use it to track WAL volume/rates and write/sync activity; take two samples over time to compute deltas. These are cluster-wide counters, not attributed to a single job when other workloads run.

### 5.5. `pg_stat_progress_basebackup`

On supported PostgreSQL versions, `pg_stat_progress_basebackup` observes running base backups on the server:

~~~sql
SELECT
    pid,
    phase,
    backup_total,
    backup_streamed,
    tablespaces_total,
    tablespaces_streamed
FROM pg_stat_progress_basebackup;
~~~

Some columns/phases depend on version. This view helps show whether a backup is progressing and its current phase; it does not prove files are verified or offsite copies finished.

### 5.6. `pg_stat_replication`

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Replication lag relates to backup retention because standbys/slots can pin WAL. Still, healthy streaming replication does not prove archive destinations or base backups are healthy.

### 5.7. `pg_replication_slots`

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots;
~~~

Columns vary by version. `restart_lsn` reveals the WAL a slot still pins; a long-inactive slot pins WAL and grows `pg_wal`. Never drop a slot solely by age or inactive status before identifying its consumer/owner.

### 5.8. `pg_stat_database` and Relation Metrics

Database stats clarify workload/transaction volumes without replacing backup manager logs. Combine `pg_stat_database`, `pg_stat_wal`, `pg_stat_archiver`, `pg_stat_activity`, and host/storage metrics to distinguish workload spikes from slow backups/archiving.

### 5.9. PostgreSQL Logs

Logs are typically the richest detail source for archive/backup failures:
- `archive_command` exit codes/errors.
- Permission denied.
- No space left on device.
- Connection timeouts/refused.
- Missing segments/files.
- Checksum/manifest errors.
- WAL corruption/read failures.
- Backup start/stop/failures.
- Recovery target not reached or missing WAL files.

Ensure logs carry timestamps, severity, PID/session context, and sufficient retention. Never log archive credentials or secrets.

---

## 6. Monitoring External Backup Jobs and Pipelines

### 6.1. Scheduler

Verify:
- Did the job trigger on schedule?
- Did it overlap a previous run?
- Was it disabled/paused?
- Did it time out or get killed?
- Is the scheduler service healthy?
- Can job run IDs correlate with backup IDs and PostgreSQL logs?

A job absent from database logs may never have started rather than being rejected by the database.

### 6.2. Backup Process

Log:
- Process exit code.
- Start/end timestamps and elapsed duration.
- Bytes read/written/transferred.
- Throughput and retry count.
- Backup ID and manifest path.
- Error category and log location.
- Source/target host.
- Tool/version.

Exit code 0 is just one signal; verify the tool finished every phase and committed catalog metadata.

### 6.3. Storage Destination

Monitor:
- Available capacity/quotas.
- Object count/size and growth.
- Upload errors, throttling, and request timeouts.
- Latency and throughput.
- Permission/credential expirations.
- Lifecycle/retention deletion events.
- Offsite replication/copy status.
- Object lock/immutability status if used.

### 6.4. Encryption and Key Management

Encrypted backups only have value if keys can be fetched in a recovery scenario. Ensure:
- Key identifiers/versions live in backup metadata.
- Keys are managed independently from backup storage.
- Recovery access paths work when primary identity providers/regions fail.
- Access and decryption are rehearsed.
- Plaintext keys never appear in job logs/catalogs.

### 6.5. Network

Track throughput, packet loss, DNS, TLS expiration, firewall changes, and remote storage reachability. Backups can fail at the network layer even while PostgreSQL and backup processes are healthy.

### 6.6. Backup Duration Regression

If backup durations creep upward:
- Did data size grow?
- Did WAL volume/FPI rise?
- Did storage throughput drop?
- Is backup compression/encryption CPU-bound?
- Is network throttling active?
- Did snapshot/copy-on-write behavior change?
- Is the backup job contending with production workloads?

Alert against baselines scaled to size/workload rather than using one static timeout across all databases.

### 6.7. Job Overlaps

Two concurrent full backups spike I/O, storage bandwidth, and backup windows. Schedulers must cap concurrency per cluster/storage capacity and enforce explicit timeouts/cancellation policies.

### 6.8. Never Mask Errors with Infinite Retries

Retries smooth over transient errors, yet infinite retries hide permanent faults and trigger storms. Separate retryable vs. non-retryable errors, apply exponential backoff/jitter, cap attempts, and alert when retry budgets burn.

---

## 7. Metrics, Dashboards, and Alerting

### 7.1. Essential Metric Groups

A backup/recovery dashboard should group metrics so on-call engineers immediately see where failures occur:

| Group | Metrics/Fields | Question |
|---|---|---|
| Scheduler | last start, last success, next run, duration, exit code | Are jobs running on schedule? |
| Backup artifacts | backup ID, size, manifest, checksum, catalog state | Are backups complete and verified? |
| WAL archiving | last archived time/file, success/failure deltas, backlog | Is WAL archiving continuously? |
| WAL generation | `wal_bytes` delta, FPI, WAL rate | How fast is workload generating WAL? |
| Replication | sent/write/flush/replay LSN, slot restart LSN | Are standbys/slots pinning WAL? |
| Storage | capacity, free bytes, object errors, quotas | Is storage nearing exhaustion? |
| Restore tests | last successful restore, duration, target, result | Do backups actually restore? |
| Objectives | measured RPO/RTO, age of latest tested backup | Are business targets met? |

### 7.2. Tracking the Latest Archive Time

~~~sql
SELECT
    now() AS observed_at,
    last_archived_wal,
    last_archived_time,
    EXTRACT(EPOCH FROM (clock_timestamp() - last_archived_time))
        AS seconds_since_last_archive,
    archived_count,
    failed_count,
    stats_reset
FROM pg_stat_archiver;
~~~

This is a freshness signal, not a standalone verdict. If a database sits idle with no new WAL segments, an older `last_archived_time` can be normal. Alert on stale archiving only when WAL generation/segment activity should have archived or policy mandates an `archive_timeout`.

### 7.3. Tracking Failure Counters

Do not inspect only raw point-in-time counters; sample periodically and compute deltas between samples. If `stats_reset` changes, start a new baseline. Good alerts combine:
- Rising failures within a window.
- Recent `last_failed_time`.
- Repeated failures on the same file.
- Archive freshness breaching thresholds during active WAL generation.
- Concurrent `pg_wal` usage growth.

### 7.4. Calculating WAL Generation Rate

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    wal_bytes,
    wal_records,
    wal_fpi,
    stats_reset
FROM pg_stat_wal;
~~~

Take two samples separated by a known interval. If `wal_bytes` climbs 600 MiB in 10 minutes, average WAL generation is roughly 60 MiB/min in that window. Confirm `stats_reset` did not change and remember this is cluster-wide.

### 7.5. Tracking Slots Holding WAL

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
      WHEN restart_lsn IS NULL THEN NULL
      ELSE pg_size_pretty(
          pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
      )
    END AS retained_wal_distance,
    wal_status
FROM pg_replication_slots
ORDER BY restart_lsn NULLS FIRST;
~~~

LSN distance estimates WAL stream ahead of `restart_lsn`, not exact local disk bytes pinned in all situations. Inactive slots can pin WAL indefinitely. Before intervening, identify owner, consumer, and reinitialization impact.

### 7.6. Tracking Running Base Backups

~~~sql
SELECT
    pid,
    phase,
    backup_total,
    backup_streamed,
    tablespaces_total,
    tablespaces_streamed
FROM pg_stat_progress_basebackup;
~~~

Use this view to see whether a backup is advancing or stuck in a phase. Pair with process logs, network throughput, and storage metrics to locate bottlenecks. Progress does not replace checking exit codes and manifests.

### 7.7. Inspecting the WAL Directory

On supported versions and suitably privileged roles, `pg_ls_waldir()` lists WAL files:

~~~sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)::bigint) AS wal_directory_size,
    max(modification) AS newest_file_time
FROM pg_ls_waldir();
~~~

This inspects only the current WAL directory. For real capacity tracking, use filesystem metrics since directory listings do not replace checking mount capacity, inode usage, reserved space, or sibling files. Never delete entries based on this output.

### 7.8. Per-Backup Dashboard

Each backup run should display a timeline row showing:
- Scheduled/start/end timestamps.
- Duration and throughput.
- Backup ID/type.
- Exit code.
- File/object size.
- Manifest/checksum verification.
- WAL range/timeline.
- Offsite replication status.
- Retention expiry.
- Restore test status and latest test date.

### 7.9. Per-Cluster Dashboard

Cluster-level dashboards should show:
- Age of latest verified base backup.
- Age of latest successful archive during WAL generation.
- WAL generation rate.
- Archive failures over 1h/24h.
- Disk usage of `pg_wal` and archive destination.
- Oldest inactive replication slot/`restart_lsn`.
- Latest successful restore drill.
- Measured RPO/RTO vs. objectives.

### 7.10. Designing Context-Rich Alerts

Never set a permanent alert on `failed_count > 0`, because counters reset or stale errors remain non-zero. Good alerts include:
- Time window context.
- Cluster/backup ID.
- Severity.
- Owner/on-call.
- Link to runbook.
- Last success and last failure.
- Impact on RPO/RTO.
- Clear/recovery condition.

### 7.11. Sample Alert Policy

| Alert | Sample Condition | Severity |
|---|---|---|
| Backup missed | No verified backup within SLA window | Critical |
| Backup failed | Job exited non-zero or artifact incomplete | High/Critical per RPO |
| Archive stalled | Active WAL generation with archive freshness past threshold | Critical |
| Archive failures | Failure counter delta rose in window | High |
| WAL disk pressure | `pg_wal` filesystem above warning/critical capacity | High/Critical |
| Slot retention | Slot pinning WAL past budget with inactive consumer | High |
| Offsite copy lag | Local verified backup missing offsite copy within SLA | High |
| Restore test stale | No restore test within scheduled cadence | Medium/High |
| Restore test failed | Restore/validation failed | Critical |
| RTO regression | Restore duration exceeded objective | High |

Thresholds must come from real RPO/RTO, WAL rate, and disk headroom. Never apply the same minute threshold across all clusters.

### 7.12. Alerts Must Not Create False Confidence

- A new archive success does not prove prior segment chains are continuous.
- Existing backup files do not prove files can be decrypted/read.
- Passing `pg_verifybackup` does not prove applications work after restore.
- Zero replica lag does not prove independent backups exist.
- A restore test passing last month does not prove yesterday's backup works.
- Green monitoring does not prove paging routes to on-call engineers still work.

---

## 8. Backup Verification: From Artifacts to Restore

### 8.1. Verification Layers

Verification spans six layers:

1. **Execution:** job finished, valid exit code, no timeout.
2. **Completeness:** all required files/tablespaces/objects/manifests created and uploaded.
3. **Integrity:** checksums, sizes, manifest, and formats valid.
4. **Recoverability:** valid base backup and required WAL chain exist.
5. **Database validation:** PostgreSQL boots, recovers to target, and catalogs/data are readable.
6. **Application validation:** application reads/writes, business data matches, and service criteria pass.

A backup passing only layers 1–3 is not complete proof of restorability.

### 8.2. `pg_verifybackup`

For physical base backups created with manifest support, `pg_verifybackup` checks manifests and file checksums per version capabilities.

Example:

~~~bash
pg_verifybackup /backups/base/backup_2026_11_14
~~~

Use a binary compatible with the backup/server version. Read `pg_verifybackup --help` and version docs to understand WAL checks, tablespaces, and ignore options. One successful verify pass does not replace an actual test restore.

### 8.3. Manifests and Checksums

Manifests define expected artifacts, sizes, and checksums. When copying backups across object storage/offsite:
- Verify before upload.
- Verify after upload or use matching storage checksum semantics.
- Record object version/etag/checksum per storage type.
- Do not assume ETags are always MD5s; multipart uploads and provider semantics vary.
- Confirm the manifest matches the exact backup ID and system identifier.

### 8.4. Checking the WAL Chain

Confirm:
- Where the backup starts/ends.
- Where required WAL segments begin for recovery.
- Whether the WAL archive is continuous up to the recovery target.
- Whether timeline history files are complete.
- Whether segments are readable/decryptable.
- Whether archive retention deleted a still-needed segment.

Do not check only "does the newest WAL file exist"; verify the entire continuous span needed for the base backup/target.

### 8.5. Logical Backup Validation

For custom-format dumps:
- Check file existence and plausible size.
- Run `pg_restore --list` to read the TOC.
- Test restore into an isolated database.
- Verify schemas, extensions, owners/privileges, and key data.
- Run application queries/smoke tests post-restore.

`pg_restore --list` proves only basic TOC readability; it does not replace a full restore.

### 8.6. Isolated Restore Tests

Restore backups onto a dedicated host/VM/network:
- No port or service discovery overlap with production.
- Prevent real apps from sending emails, payments, or calling external APIs.
- Use test credentials.
- Restrict network egress.
- Protect sensitive restored data.
- Log test timestamp and storage location.
- Tear down the test environment per approved procedures.

### 8.7. Checks After PostgreSQL Starts

Verify at minimum:
- Server startup/recovery completed.
- `pg_is_in_recovery()` reflects the expected state.
- Expected databases and schemas exist.
- Required extensions/languages/tablespaces are ready.
- Critical tables/rows are readable.
- Constraints/indexes are valid as required.
- Application roles can connect and query.
- Logs show no recovery errors or missing WAL warnings.

### 8.8. Business Checks

A booting database does not guarantee correct data. Check business invariants:
- Total order counts over known ranges.
- Daily/per-tenant monetary totals.
- Active account counts.
- Orphan foreign key checks.
- Sample transaction IDs/records near the recovery target.
- Outbox/event sequences.
- Relationships across core tables.

Use queries checked against pre-recorded expected ranges/checksums. Never stop at `SELECT 1`.

### 8.9. Checking Logical Consistency

Use application constraints/queries and specialized tools like `amcheck` for certain B-tree structures where appropriate. Not all integrity checks are fast or lightweight; schedule them inside isolated restore environments.

### 8.10. Storing Evidence

Each test should record:
- Backup ID/source.
- Restore target/timestamp.
- PostgreSQL/tool versions.
- WAL timeline and recovery target.
- Logs/exit codes.
- Integrity check results.
- Application validation results.
- Measured RTO/RPO.
- Findings and remediation owners.
- Executor/reviewer.

---

## 9. Retention, Offsite, and Wide-Area Protection

### 9.1. Retention Policy

Retention determines how long backups and WAL must stay. Policies should factor in:
- RPO/RTO.
- Frequency of full/incremental backups if supported.
- WAL archive volume.
- Legal/regulatory obligations.
- Storage costs.
- Delayed incident detection (e.g., corruption spotted days later).
- Ability to restore from older backups and associated WAL.

### 9.2. Retain Enough WAL for All Active Base Backups

If an older base backup remains eligible for restore to a target, preserve the WAL chain required for that target. Deleting WAL purely by file age can leave base backups intact on disk yet unrecoverable across the required timeframe.

Backup managers/catalogs must track backup-to-WAL segment dependencies. Retention must prune by backup set/dependency rather than raw filename age.

### 9.3. Offsite Copies

Backups on the same host/storage account/region as the primary can die in the same outage. Copy to an independent failure domain per requirements:
- Different region.
- Different account/project.
- Different credentials.
- Independent storage policies.
- Immutable/WORM or offline copies where appropriate.

Test accessing and restoring offsite copies—never trust green replication status badges alone.

### 9.4. Immutability

Immutable storage/object locks stop backups from being deleted/modified for a window. Design balances:
- Retention lock duration.
- Legal holds.
- Recovery accounts and break-glass access.
- Ability to process policy-mandated deletions.
- Cost and quotas.
- Separating lock admin privileges from database operations.

### 9.5. Separating Credentials

Backup writers should not be able to wipe archive history. Restore operators need read/decrypt access without rights to shorten retention. Storage administrators and PostgreSQL DBAs should maintain proper separation of duties.

### 9.6. Backup Catalogs Need Backups Too

If the catalog is lost, locating the right backup/WAL chain becomes painful even when objects remain. Export/back up catalogs, encryption metadata, and restore instructions independently; test restoring the catalog in DR exercises.

### 9.7. Retention Deletion Tests

Before running lifecycle deletions:
1. Identify expired backup sets.
2. Confirm dependent WAL is no longer needed.
3. Check legal holds/retention locks.
4. Generate an inventory and dry run.
5. Log objects slated for deletion.
6. Execute per policy.
7. Verify remaining retained backups still restore cleanly via sampling.

### 9.8. Ransomware and Credential Compromise

An attacker able to delete the database will try wiping backups too. Shrink blast radius using:
- Separate credentials and least privilege.
- Immutable/offline copies.
- MFA/break-glass controls.
- Independent audit logs.
- Separate storage accounts/projects.
- Encryption keys isolated from backup storage.
- Clean-room restores from verified sources.

---

## 10. Designing a Recovery Drill Program

### 10.1. Drill Objectives

A recovery drill must answer:
- Can we locate the right backup?
- Can we obtain keys/credentials?
- Can we provision infrastructure?
- Can we restore the base backup?
- Can we replay WAL to target?
- Can we validate database and application?
- Did we meet RPO/RTO?
- Who holds authority to promote/cut over?
- Which dependencies are missing?

### 10.2. Drill Types

| Drill Type | Scope | Suggested Cadence |
|---|---|---|
| Artifact verification | Manifest/checksum/file inventory | Every backup or automated sample |
| Restore smoke test | Restore one backup to an isolated host | Weekly/monthly by criticality |
| Full restore drill | Rebuild cluster and run app validation | Monthly/quarterly |
| PITR drill | Restore to timestamp/LSN before simulated incident | Quarterly |
| Object-level recovery | Recover table/database/object | As needed and by criticality |
| Region/site recovery | Rebuild service from offsite backup | Annually or per SLA |
| Tabletop exercise | Walk through roles/decisions/comms | Quarterly |
| Backup pipeline failure drill | Simulate archive/storage/credential faults in test env | After major changes and periodically |

Cadences should reflect business risk, rate of change, and compliance; these are guidelines, not universal mandates.

### 10.3. Tabletop Exercises

Tabletops are scenario walkthroughs without necessarily restoring real data. The team walks through:
- Who declares an incident?
- Who chooses the recovery target?
- Who owns backups/storage/keys?
- How do we access runbooks if the primary identity provider fails?
- Who approves promotion/cutover?
- How are downtime/data loss communicated?
- What if WAL is missing?
- Who signs off on business data post-restore?

Tabletops uncover coordination, permission, and documentation gaps; they do not prove technical restoration works.

### 10.4. Full Restore Drills

A full drill should:
1. Choose backup ID and recovery target before the session.
2. Pull artifacts from the real disaster storage location.
3. Provision an isolated host/network.
4. Restore the base backup.
5. Configure WAL archive/recovery target.
6. Wait for recovery completion.
7. Run database checks and app smoke tests.
8. Measure RTO/RPO.
9. Record findings.
10. Clean up test environments and artifacts per policy.

### 10.5. PITR Drills

Simulate an incident with a known timestamp/LSN:
- Write a marker transaction before the fault timestamp.
- Write a marker or destructive test action after the recovery point.
- Restore base backup and WAL to a target before the destructive action.
- Verify pre-target marker exists and post-target changes are absent.
- Verify transaction boundaries and timezone/target semantics.

Never run destructive actions on production. Use test datasets or isolated clones.

### 10.6. Testing the Latest Backups

A passing test from six months ago does not prove today's backup restores. Maintain:
- Small automated post-backup or sampled tests.
- Scheduled full restores.
- Scheduled PITR tests.
- Tests after changes to PostgreSQL major versions, backup tools, encryption, storage, or archive pipelines.

### 10.7. Controlled Failure Drills

Drills do not require simulating a production outage. Inject failures in test environments:
- Expired credentials.
- Read-only archive destination.
- Unavailable object storage.
- Missing WAL segment in a test copy.
- Low disk quota.
- Intentionally corrupted test backup manifest.
- Wrong restore target timezone.
- Unreachable KMS/key service.

Inject failures only inside bounded test environments with cleanup plans.

### 10.8. Pass/Fail Criteria

Passing is more than PostgreSQL starting. Define criteria upfront:
- Restore finishes under RTO.
- Recovery point meets RPO.
- WAL chain continuous and recovery target reached.
- Critical schemas/tables present.
- Business invariants hit expected values.
- Application smoke tests pass.
- Access/secret/key workflows work.
- Evidence saved.
- Zero side effects on production/external services.

If any criterion fails, record partial success and the gap; never mark the whole drill as passed.

---

## 7. Metrics, Dashboards, and Alerting

### 7.1. Essential Metric Groups

A backup/recovery dashboard should group metrics so on-call engineers immediately see where failures occur:

| Group | Metrics/Fields | Question |
|---|---|---|
| Scheduler | last start, last success, next run, duration, exit code | Are jobs running on schedule? |
| Backup artifacts | backup ID, size, manifest, checksum, catalog state | Are backups complete and verified? |
| WAL archiving | last archived time/file, success/failure deltas, backlog | Is WAL archiving continuously? |
| WAL generation | `wal_bytes` delta, FPI, WAL rate | How fast is workload generating WAL? |
| Replication | sent/write/flush/replay LSN, slot restart LSN | Are standbys/slots pinning WAL? |
| Storage | capacity, free bytes, object errors, quotas | Is storage nearing exhaustion? |
| Restore tests | last successful restore, duration, target, result | Do backups actually restore? |
| Objectives | measured RPO/RTO, age of latest tested backup | Are business targets met? |

### 7.2. Tracking the Latest Archive Time

~~~sql
SELECT
    now() AS observed_at,
    last_archived_wal,
    last_archived_time,
    EXTRACT(EPOCH FROM (clock_timestamp() - last_archived_time))
        AS seconds_since_last_archive,
    archived_count,
    failed_count,
    stats_reset
FROM pg_stat_archiver;
~~~

This is a freshness signal, not a standalone verdict. If a database sits idle with no new WAL segments, an older `last_archived_time` can be normal. Alert on stale archiving only when WAL generation/segment activity should have archived or policy mandates an `archive_timeout`.

### 7.3. Tracking Failure Counters

Do not inspect only raw point-in-time counters; sample periodically and compute deltas between samples. If `stats_reset` changes, start a new baseline. Good alerts combine:
- Rising failures within a window.
- Recent `last_failed_time`.
- Repeated failures on the same file.
- Archive freshness breaching thresholds during active WAL generation.
- Concurrent `pg_wal` usage growth.

### 7.4. Calculating WAL Generation Rate

~~~sql
SELECT
    clock_timestamp() AS sampled_at,
    wal_bytes,
    wal_records,
    wal_fpi,
    stats_reset
FROM pg_stat_wal;
~~~

Take two samples separated by a known interval. If `wal_bytes` climbs 600 MiB in 10 minutes, average WAL generation is roughly 60 MiB/min in that window. Confirm `stats_reset` did not change and remember this is cluster-wide.

### 7.5. Tracking Slots Holding WAL

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
      WHEN restart_lsn IS NULL THEN NULL
      ELSE pg_size_pretty(
          pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
      )
    END AS retained_wal_distance,
    wal_status
FROM pg_replication_slots
ORDER BY restart_lsn NULLS FIRST;
~~~

LSN distance estimates WAL stream ahead of `restart_lsn`, not exact local disk bytes pinned in all situations. Inactive slots can pin WAL indefinitely. Before intervening, identify owner, consumer, and reinitialization impact.

### 7.6. Tracking Running Base Backups

~~~sql
SELECT
    pid,
    phase,
    backup_total,
    backup_streamed,
    tablespaces_total,
    tablespaces_streamed
FROM pg_stat_progress_basebackup;
~~~

Use this view to see whether a backup is advancing or stuck in a phase. Pair with process logs, network throughput, and storage metrics to locate bottlenecks. Progress does not replace checking exit codes and manifests.

### 7.7. Inspecting the WAL Directory

On supported versions and suitably privileged roles, `pg_ls_waldir()` lists WAL files:

~~~sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)::bigint) AS wal_directory_size,
    max(modification) AS newest_file_time
FROM pg_ls_waldir();
~~~

This inspects only the current WAL directory. For real capacity tracking, use filesystem metrics since directory listings do not replace checking mount capacity, inode usage, reserved space, or sibling files. Never delete entries based on this output.

### 7.8. Per-Backup Dashboard

Each backup run should display a timeline row showing:
- Scheduled/start/end timestamps.
- Duration and throughput.
- Backup ID/type.
- Exit code.
- File/object size.
- Manifest/checksum verification.
- WAL range/timeline.
- Offsite replication status.
- Retention expiry.
- Restore test status and latest test date.

### 7.9. Per-Cluster Dashboard

Cluster-level dashboards should show:
- Age of latest verified base backup.
- Age of latest successful archive during WAL generation.
- WAL generation rate.
- Archive failures over 1h/24h.
- Disk usage of `pg_wal` and archive destination.
- Oldest inactive replication slot/`restart_lsn`.
- Latest successful restore drill.
- Measured RPO/RTO vs. objectives.

### 7.10. Designing Context-Rich Alerts

Never set a permanent alert on `failed_count > 0`, because counters reset or stale errors remain non-zero. Good alerts include:
- Time window context.
- Cluster/backup ID.
- Severity.
- Owner/on-call.
- Link to runbook.
- Last success and last failure.
- Impact on RPO/RTO.
- Clear/recovery condition.

### 7.11. Sample Alert Policy

| Alert | Sample Condition | Severity |
|---|---|---|
| Backup missed | No verified backup within SLA window | Critical |
| Backup failed | Job exited non-zero or artifact incomplete | High/Critical per RPO |
| Archive stalled | Active WAL generation with archive freshness past threshold | Critical |
| Archive failures | Failure counter delta rose in window | High |
| WAL disk pressure | `pg_wal` filesystem above warning/critical capacity | High/Critical |
| Slot retention | Slot pinning WAL past budget with inactive consumer | High |
| Offsite copy lag | Local verified backup missing offsite copy within SLA | High |
| Restore test stale | No restore test within scheduled cadence | Medium/High |
| Restore test failed | Restore/validation failed | Critical |
| RTO regression | Restore duration exceeded objective | High |

Thresholds must come from real RPO/RTO, WAL rate, and disk headroom. Never apply the same minute threshold across all clusters.

### 7.12. Alerts Must Not Create False Confidence

- A new archive success does not prove prior segment chains are continuous.
- Existing backup files do not prove files can be decrypted/read.
- Passing `pg_verifybackup` does not prove applications work after restore.
- Zero replica lag does not prove independent backups exist.
- A restore test passing last month does not prove yesterday's backup works.
- Green monitoring does not prove paging routes to on-call engineers still work.

---

## 8. Backup Verification: From Artifacts to Restore

### 8.1. Verification Layers

Verification spans six layers:

1. **Execution:** job finished, valid exit code, no timeout.
2. **Completeness:** all required files/tablespaces/objects/manifests created and uploaded.
3. **Integrity:** checksums, sizes, manifest, and formats valid.
4. **Recoverability:** valid base backup and required WAL chain exist.
5. **Database validation:** PostgreSQL boots, recovers to target, and catalogs/data are readable.
6. **Application validation:** application reads/writes, business data matches, and service criteria pass.

A backup passing only layers 1–3 is not complete proof of restorability.

### 8.2. `pg_verifybackup`

For physical base backups created with manifest support, `pg_verifybackup` checks manifests and file checksums per version capabilities.

Example:

~~~bash
pg_verifybackup /backups/base/backup_2026_11_14
~~~

Use a binary compatible with the backup/server version. Read `pg_verifybackup --help` and version docs to understand WAL checks, tablespaces, and ignore options. One successful verify pass does not replace an actual test restore.

### 8.3. Manifests and Checksums

Manifests define expected artifacts, sizes, and checksums. When copying backups across object storage/offsite:
- Verify before upload.
- Verify after upload or use matching storage checksum semantics.
- Record object version/etag/checksum per storage type.
- Do not assume ETags are always MD5s; multipart uploads and provider semantics vary.
- Confirm the manifest matches the exact backup ID and system identifier.

### 8.4. Checking the WAL Chain

Confirm:
- Where the backup starts/ends.
- Where required WAL segments begin for recovery.
- Whether the WAL archive is continuous up to the recovery target.
- Whether timeline history files are complete.
- Whether segments are readable/decryptable.
- Whether archive retention deleted a still-needed segment.

Do not check only "does the newest WAL file exist"; verify the entire continuous span needed for the base backup/target.

### 8.5. Logical Backup Validation

For custom-format dumps:
- Check file existence and plausible size.
- Run `pg_restore --list` to read the TOC.
- Test restore into an isolated database.
- Verify schemas, extensions, owners/privileges, and key data.
- Run application queries/smoke tests post-restore.

`pg_restore --list` proves only basic TOC readability; it does not replace a full restore.

### 8.6. Isolated Restore Tests

Restore backups onto a dedicated host/VM/network:
- No port or service discovery overlap with production.
- Prevent real apps from sending emails, payments, or calling external APIs.
- Use test credentials.
- Restrict network egress.
- Protect sensitive restored data.
- Log test timestamp and storage location.
- Tear down the test environment per approved procedures.

### 8.7. Checks After PostgreSQL Starts

Verify at minimum:
- Server startup/recovery completed.
- `pg_is_in_recovery()` reflects the expected state.
- Expected databases and schemas exist.
- Required extensions/languages/tablespaces are ready.
- Critical tables/rows are readable.
- Constraints/indexes are valid as required.
- Application roles can connect and query.
- Logs show no recovery errors or missing WAL warnings.

### 8.8. Business Checks

A booting database does not guarantee correct data. Check business invariants:
- Total order counts over known ranges.
- Daily/per-tenant monetary totals.
- Active account counts.
- Orphan foreign key checks.
- Sample transaction IDs/records near the recovery target.
- Outbox/event sequences.
- Relationships across core tables.

Use queries checked against pre-recorded expected ranges/checksums. Never stop at `SELECT 1`.

### 8.9. Checking Logical Consistency

Use application constraints/queries and specialized tools like `amcheck` for certain B-tree structures where appropriate. Not all integrity checks are fast or lightweight; schedule them inside isolated restore environments.

### 8.10. Storing Evidence

Each test should record:
- Backup ID/source.
- Restore target/timestamp.
- PostgreSQL/tool versions.
- WAL timeline and recovery target.
- Logs/exit codes.
- Integrity check results.
- Application validation results.
- Measured RTO/RPO.
- Findings and remediation owners.
- Executor/reviewer.

---

## 9. Retention, Offsite, and Wide-Area Protection

### 9.1. Retention Policy

Retention determines how long backups and WAL must stay. Policies should factor in:
- RPO/RTO.
- Frequency of full/incremental backups if supported.
- WAL archive volume.
- Legal/regulatory obligations.
- Storage costs.
- Delayed incident detection (e.g., corruption spotted days later).
- Ability to restore from older backups and associated WAL.

### 9.2. Retain Enough WAL for All Active Base Backups

If an older base backup remains eligible for restore to a target, preserve the WAL chain required for that target. Deleting WAL purely by file age can leave base backups intact on disk yet unrecoverable across the required timeframe.

Backup managers/catalogs must track backup-to-WAL segment dependencies. Retention must prune by backup set/dependency rather than raw filename age.

### 9.3. Offsite Copies

Backups on the same host/storage account/region as the primary can die in the same outage. Copy to an independent failure domain per requirements:
- Different region.
- Different account/project.
- Different credentials.
- Independent storage policies.
- Immutable/WORM or offline copies where appropriate.

Test accessing and restoring offsite copies—never trust green replication status badges alone.

### 9.4. Immutability

Immutable storage/object locks stop backups from being deleted/modified for a window. Design balances:
- Retention lock duration.
- Legal holds.
- Recovery accounts and break-glass access.
- Ability to process policy-mandated deletions.
- Cost and quotas.
- Separating lock admin privileges from database operations.

### 9.5. Separating Credentials

Backup writers should not be able to wipe archive history. Restore operators need read/decrypt access without rights to shorten retention. Storage administrators and PostgreSQL DBAs should maintain proper separation of duties.

### 9.6. Backup Catalogs Need Backups Too

If the catalog is lost, locating the right backup/WAL chain becomes painful even when objects remain. Export/back up catalogs, encryption metadata, and restore instructions independently; test restoring the catalog in DR exercises.

### 9.7. Retention Deletion Tests

Before running lifecycle deletions:
1. Identify expired backup sets.
2. Confirm dependent WAL is no longer needed.
3. Check legal holds/retention locks.
4. Generate an inventory and dry run.
5. Log objects slated for deletion.
6. Execute per policy.
7. Verify remaining retained backups still restore cleanly via sampling.

### 9.8. Ransomware and Credential Compromise

An attacker able to delete the database will try wiping backups too. Shrink blast radius using:
- Separate credentials and least privilege.
- Immutable/offline copies.
- MFA/break-glass controls.
- Independent audit logs.
- Separate storage accounts/projects.
- Encryption keys isolated from backup storage.
- Clean-room restores from verified sources.

---

## 10. Designing a Recovery Drill Program

### 10.1. Drill Objectives

A recovery drill must answer:
- Can we locate the right backup?
- Can we obtain keys/credentials?
- Can we provision infrastructure?
- Can we restore the base backup?
- Can we replay WAL to target?
- Can we validate database and application?
- Did we meet RPO/RTO?
- Who holds authority to promote/cut over?
- Which dependencies are missing?

### 10.2. Drill Types

| Drill Type | Scope | Suggested Cadence |
|---|---|---|
| Artifact verification | Manifest/checksum/file inventory | Every backup or automated sample |
| Restore smoke test | Restore one backup to an isolated host | Weekly/monthly by criticality |
| Full restore drill | Rebuild cluster and run app validation | Monthly/quarterly |
| PITR drill | Restore to timestamp/LSN before simulated incident | Quarterly |
| Object-level recovery | Recover table/database/object | As needed and by criticality |
| Region/site recovery | Rebuild service from offsite backup | Annually or per SLA |
| Tabletop exercise | Walk through roles/decisions/comms | Quarterly |
| Backup pipeline failure drill | Simulate archive/storage/credential faults in test env | After major changes and periodically |

Cadences should reflect business risk, rate of change, and compliance; these are guidelines, not universal mandates.

### 10.3. Tabletop Exercises

Tabletops are scenario walkthroughs without necessarily restoring real data. The team walks through:
- Who declares an incident?
- Who chooses the recovery target?
- Who owns backups/storage/keys?
- How do we access runbooks if the primary identity provider fails?
- Who approves promotion/cutover?
- How are downtime/data loss communicated?
- What if WAL is missing?
- Who signs off on business data post-restore?

Tabletops uncover coordination, permission, and documentation gaps; they do not prove technical restoration works.

### 10.4. Full Restore Drills

A full drill should:
1. Choose backup ID and recovery target before the session.
2. Pull artifacts from the real disaster storage location.
3. Provision an isolated host/network.
4. Restore the base backup.
5. Configure WAL archive/recovery target.
6. Wait for recovery completion.
7. Run database checks and app smoke tests.
8. Measure RTO/RPO.
9. Record findings.
10. Clean up test environments and artifacts per policy.

### 10.5. PITR Drills

Simulate an incident with a known timestamp/LSN:
- Write a marker transaction before the fault timestamp.
- Write a marker or destructive test action after the recovery point.
- Restore base backup and WAL to a target before the destructive action.
- Verify pre-target marker exists and post-target changes are absent.
- Verify transaction boundaries and timezone/target semantics.

Never run destructive actions on production. Use test datasets or isolated clones.

### 10.6. Testing the Latest Backups

A passing test from six months ago does not prove today's backup restores. Maintain:
- Small automated post-backup or sampled tests.
- Scheduled full restores.
- Scheduled PITR tests.
- Tests after changes to PostgreSQL major versions, backup tools, encryption, storage, or archive pipelines.

### 10.7. Controlled Failure Drills

Drills do not require simulating a production outage. Inject failures in test environments:
- Expired credentials.
- Read-only archive destination.
- Unavailable object storage.
- Missing WAL segment in a test copy.
- Low disk quota.
- Intentionally corrupted test backup manifest.
- Wrong restore target timezone.
- Unreachable KMS/key service.

Inject failures only inside bounded test environments with cleanup plans.

### 10.8. Pass/Fail Criteria

Passing is more than PostgreSQL starting. Define criteria upfront:
- Restore finishes under RTO.
- Recovery point meets RPO.
- WAL chain continuous and recovery target reached.
- Critical schemas/tables present.
- Business invariants hit expected values.
- Application smoke tests pass.
- Access/secret/key workflows work.
- Evidence saved.
- Zero side effects on production/external services.

If any criterion fails, record partial success and the gap; never mark the whole drill as passed.

---

## 11. Physical Backup and PITR Recovery Procedures

### 11.1. Pre-Restore Preparation

Before starting, identify:
- Backup ID and cluster-matching system identifier.
- Compatible PostgreSQL major version.
- Complete, verified base backup.
- WAL archive location/credentials/keys.
- Timeline history files.
- Tablespaces and mount points.
- Required extensions/binaries.
- Configs, certificates, and secrets.
- Recovery target (time, LSN, XID, or named restore point if created).
- Network isolation and service dependencies.

Never pick a backup solely by newest timestamp; pick a backup with a valid WAL chain to the target.

### 11.2. Provisioning an Isolated Environment

Create a host/VM/storage with adequate capacity and IOPS. Isolate:
- Restore data directory.
- WAL restore/cache location if needed.
- Network/security group.
- Port and DNS.
- Application credentials.
- Egress to external services.

If using production data with PII, apply security controls equal to or stricter than production.

### 11.3. Restoring the Base Backup

Use the tool/procedure that created the backup to restore files and tablespaces. Preserve required ownership/permissions. For physical backups, never copy a few relation files via filesystem commands expecting a consistent cluster.

### 11.4. Configuring WAL Recovery

In modern PostgreSQL, archive recovery uses recovery settings and the appropriate signal file (such as `recovery.signal` in versions past `recovery.conf`). Configure `restore_command` to fetch segments from the archive and set the recovery target matching your objective.

Conceptual config example:

~~~conf
restore_command = 'fetch_wal %f %p'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
~~~

`fetch_wal` is a placeholder for your environment's archive retrieval command, not a built-in command. Verify syntax/timezone/target options against your PostgreSQL version. Specify explicit timezone offsets and confirm the target is reachable along the backup/WAL chain.

### 11.5. Running Recovery and Watching Logs

Start PostgreSQL inside the isolated environment. Monitor:
- WAL segment requests and `restore_command` exit statuses.
- Missing/corrupted WAL errors.
- Timeline switches/history.
- Recovery progress and replay.
- Target reached/pause/promote behavior.
- Filesystem capacity.
- Startup/recovery logs.

If WAL is missing, stop declaring restore success; identify the missing segment and the furthest reachable target.

### 11.6. Confirming the Recovery Target

When recovery hits the target:
- Confirm logs report target reached per version semantics.
- Check whether the server is paused/in recovery or promoted.
- Check `pg_is_in_recovery()`.
- Check transaction markers before/after the target.
- Record the final LSN/timestamp/timeline.

Never rely solely on PostgreSQL accepting connections.

### 11.7. Promotion and Cutover

In drills, live traffic normally does not need to open. If the scenario requires promotion:
- Promote only after confirming the recovery target and validation.
- Update routing inside the test environment.
- Test the application with dedicated credentials.
- Record the new timeline.
- Never allow the old primary and recovered node to accept writes concurrently without explicit fencing.

In production disaster recovery, fencing the old primary and preventing split-brain is mandatory before cutover.

### 11.8. Post-Recovery

Run database/business validations, measure RTO/RPO, store evidence, and clean up. If a drill promoted a test instance, clearly label its timeline/instance to avoid confusing it with production or a live replica.

---

## 12. Runbook When a Backup Job Fails

### 12.1. Receiving the Alert

Record:
- Cluster/environment.
- Backup ID/job run ID.
- Backup type.
- Start/last success/failure timestamps.
- Exit code and error category.
- Remaining RPO/RTO margin.
- Disk/storage headroom.
- WAL archive status.
- Owner and incident severity.

Determine whether the job actually ran or the scheduler never triggered it.

### 12.2. Checking the Scheduler and Process

1. Check schedule and scheduler service health.
2. Confirm job run ID and process start/end.
3. Read stdout/stderr/logs.
4. Check for timeouts, kill signals, or host restarts.
5. Check overlaps/concurrency.
6. Determine whether the failure is transient or permanent.

Never clear job status or logs merely to turn dashboards green.

### 12.3. Checking PostgreSQL

Inspect:
- Server availability and connection errors.
- `pg_stat_progress_basebackup` if a base backup is still running.
- PostgreSQL logs.
- `pg_stat_archiver` and `pg_stat_wal`.
- Replication slots/standbys if WAL retention climbed.
- Locks/resource pressure if the job blocked.

### 12.4. Checking Storage/Network/Credentials

Verify quotas, free space, permissions, object locks, KMS/key access, DNS, TLS, network routes, and remote service health. If credentials expired, rotate via secret management—never put passwords in shell history or incident chats.

### 12.5. Deciding on Retries

Retry when:
- The transient fault is resolved.
- The backup tool supports safe resume/retry.
- The backup catalog does not mark an incomplete backup as complete.
- Storage has sufficient capacity.
- Retrying will not cause overlaps or I/O overload.

If a backup is partial, use tool workflows to mark/clean up partial artifacts. Never stitch partial pieces from different backup runs into one set manually.

### 12.6. Protecting RPO

If a base backup fails while WAL archiving remains healthy, assess whether an older base backup still covers recovery within RPO. If archiving is failing too, risk escalates rapidly; escalate per incident policy, protect disk space, and restore the archive pipeline before WAL is lost.

---

## 13. Runbook When WAL Archiving Fails or Backlog Grows

### 13.1. Scoping the Issue

Gather:
- `pg_stat_archiver` counters/timestamps.
- PostgreSQL logs for `archive_command`.
- Current WAL insert/write/flush LSNs.
- `pg_stat_wal` deltas.
- `pg_wal` filesystem usage.
- Archive destination health.
- Replication slots and standby progress.

### 13.2. Distinguishing Generation Pressure vs. Retention Pressure

**Generation pressure:** workload produces WAL faster than archiving/writes/storage can absorb.

**Retention pressure:** archiving may work yet WAL cannot recycle because slots/standbys/archiver/checkpoints still need it, or archive failures pin segments.

Both can occur simultaneously. Never blindly expand storage quotas if an inactive slot is pinning WAL indefinitely.

### 13.3. `archive_command` Errors

Check:
- Exit codes and stdout/stderr.
- Permissions/ownership.
- Destination path.
- Quota/disk space.
- Network/DNS/TLS.
- KMS/key access.
- Filename/collision handling.
- Retry/idempotency behavior of `archive_command`.

`archive_command` must handle retries safely per PostgreSQL/tool docs—never overwrite a differing segment or return success before the object is durable at destination.

### 13.4. WAL Disk Pressure

When `pg_wal` filesystem approaches full:
1. Alert on-call DBA and storage owner.
2. Measure WAL generation rate and growth rate.
3. Restore the archive destination if broken.
4. Identify which slots/standbys pin WAL and their owners.
5. Check retention policies and disk headroom.
6. Throttle write-heavy jobs if needed and authorized.
7. Never delete WAL segments manually.
8. Never drop slots without identifying consumers.
9. Post-remediation, monitor archive catch-up and WAL recycling.

### 13.5. Forgotten Replication Slots

An inactive slot may hold WAL for a consumer to reconnect. Before dropping:
- Identify slot type and application owner.
- Check whether the consumer can reconnect.
- Assess consequences of dropping (logical consumers may need reinitialization; standbys may need rebuilding).
- Obtain approval per incident procedure.
- Archive evidence and update inventory.

### 13.6. Missing WAL Segment

If recovery reports missing WAL:
- Identify exact filename/LSN/timeline.
- Check local archive caches, offsite copies, and storage version history.
- Check archive logs/backup catalog.
- Identify which backups need that segment.
- Check timeline history/alternate archive locations.
- Determine the furthest reachable recovery target if the segment cannot be recovered.

Never create empty placeholder files or rename other segments to bypass the error; that does not recreate WAL data.

---

## 14. Runbook When Restore Fails

### 14.1. Stop Blind Retries on the Same Data Directory

Restore/recovery can mutate the data directory and recovery state. Upon failure:
- Save logs, backup ID, target, and tool versions.
- Snapshot/copy failure evidence if needed.
- Determine whether retrying is safe or a fresh data directory is required.
- Never alter original WAL/base backups.
- Use a fresh test copy when trying another approach.

### 14.2. Common Failure Categories

| Symptom | Investigation Path |
|---|---|
| Base backup fails to boot | Version, manifest, file permissions, tablespaces, configs |
| WAL segment not found | Archive continuity, timeline, retention, filename mapping |
| WAL checksum/corruption | Storage integrity, transfer, source archive, exact segment |
| Recovery target not reached | Target timezone/LSN, WAL range, target semantics |
| Extension/library missing | Install matching extension versions and shared libraries |
| Permission denied | Ownership, OS accounts, storage/KMS access |
| Disk full | Restore data capacity, WAL replay growth, temp space |
| Server starts yet app fails | Roles, secrets, extensions, schema, business data, external dependencies |
| Restore slower than RTO | Storage throughput, WAL volume, parallelism/tool config, validation bottlenecks |

### 14.3. Missing Extensions

Physical restores bring data files/catalogs, yet the new host still needs compatible extension binaries/shared libraries. Maintain an inventory of extension versions before disasters and store packages/sources. Never assume extensions exist on fresh OS images.

### 14.4. Tablespaces

Tablespaces can live outside the data directory. Restore targets must map tablespace paths accurately with adequate capacity/permissions. A base backup missing tablespace artifacts cannot be rescued by restoring `PGDATA` alone.

### 14.5. Configuration Drift

PostgreSQL configs, `postgresql.auto.conf`, `pg_hba.conf`, certificates, service managers, environment variables, and secrets may sit outside the base backup. Back up required configs separately with versioning and test them during drills.

### 14.6. Wrong Recovery Target

Ambiguous timestamp timezones, target LSNs before backup start, or targets past the last available WAL cause recovery to stop at the wrong point or fail. Specify explicit timezone/LSNs, use marker transactions, and test target semantics before production incidents.

---

## 15. Designing Drill Schedules and Roles

### 15.1. Roles

A drill should designate:

| Role | Responsibility |
|---|---|
| Incident commander | Coordinates, drives progression and escalation |
| DBA/recovery operator | Picks backup, restores, replays WAL, validates database |
| Infrastructure operator | Provisions hosts/networking/storage |
| Security/key custodian | Issues recovery credentials/keys per break-glass policy |
| Application owner | Runs smoke tests and business validation |
| Business approver | Signs off on data and service recovery criteria |
| Observer/scribe | Logs timeline, decisions, evidence, and findings |

One person may wear multiple hats on small teams, but cutover authority and evidence recording must be explicit.

### 15.2. Cadence by Criticality Tier

| Tier | Backup Verification | Restore Test | PITR/Site Drill |
|---|---|---|---|
| Tier 0 / critical | Every backup, automated | Weekly/monthly | Quarterly or per SLA |
| Tier 1 / high | Every backup or tight sampling | Monthly | Quarterly/semiannually |
| Tier 2 / standard | Sampled | Quarterly | Annually |
| Tier 3 / low | Per policy | Periodic per risk | On change/need |

This is a sample schedule; adjust for RPO/RTO, compliance, data sensitivity, and operational capacity.

### 15.3. Drills After Major Changes

Always schedule drills after:
- PostgreSQL major version upgrades.
- Backup tool/agent upgrades.
- `archive_command`/storage provider changes.
- Encryption/KMS key changes.
- Tablespace/layout or storage changes.
- Network/identity policy changes.
- Retention/lifecycle rule changes.
- Region/cloud account migrations.

### 15.4. Pre-Drill Planning

Preparation docs need:
- Objective and scenario.
- Scope, cluster, and backup ID.
- Recovery target.
- Pass/fail criteria.
- RTO/RPO targets.
- Participants/roles.
- Test environment/network isolation.
- Access/keys.
- Expected artifacts.
- Rollback/cleanup plan.
- Business validation owner.

### 15.5. Controlling Blast Radius

- Never point production apps at the restored database.
- Block outbound email/payment/webhook/background jobs.
- Never use production DNS.
- Never let the restore instance auto-register in service discovery.
- Never promote/cut over to production without incident authorization.
- Never use credentials with write permissions to production.
- Purge test data per policy after capturing evidence.

### 15.6. Wrapping Up the Drill

After testing:
1. Stop workloads/restore instances per cleanup plan.
2. Collect logs/metrics/evidence.
3. Confirm zero unintended writes or outbound calls occurred.
4. Revoke temporary secrets/credentials.
5. Update backup catalogs/drill histories.
6. Open action items with owners and due dates.
7. Share results with relevant stakeholders.

---

## 16. Sample Drill Scenarios

### 16.1. Scenario A — Backup Job Fails to Run

**Inject:** Scheduler skips triggering a backup in one window.

**Objective:** Detect missed backup, quantify RPO exposure, and restore schedule.

**Observe:**
- Scheduler/job age alert.
- Latest verified backup.
- Owner/on-call routing.
- Retry/backfill behavior.
- Did the catalog log the missed run?

**Pass criteria:** Alert reaches the right owner within SLA; latest recoverable backup identified; job restored and new backup verified.

### 16.2. Scenario B — Archive Destination Unavailable

**Inject:** Archive storage rejects writes or times out.

**Objective:** Detect archive failures, protect `pg_wal` disk headroom, and recover the pipeline.

**Observe:**
- `pg_stat_archiver`.
- PostgreSQL logs.
- `pg_wal` capacity/growth.
- WAL generation rate.
- Alerting/escalation.
- Archive catch-up once destination recovers.

**Pass criteria:** No manual WAL deletion; generation vs. retention pressure identified; archiving restored; backlog drains and recovery chain remains continuous.

### 16.3. Scenario C — Accidental Data Deletion

**Inject:** In a test dataset, run an erroneous `DELETE`/`UPDATE` after a marker transaction.

**Objective:** PITR to a timestamp before the bad operation.

**Observe:**
- Base backup/WAL chain selection.
- Recovery target timezone.
- Target reached.
- Pre-target marker intact; post-target changes absent.
- App validation and RTO.

**Pass criteria:** Accurate point-in-time recovery, restored test instance isolated from production, RPO/RTO evidence saved.

### 16.4. Scenario D — Region Loss

**Inject:** Assume the primary region is unreachable.

**Objective:** Rebuild cluster in another region from offsite backups/WAL.

**Observe:**
- Break-glass access.
- KMS/key retrieval.
- Offsite data/WAL availability.
- Infrastructure provisioning.
- DNS/routing/fencing.
- Business sign-off.

**Pass criteria:** Restored in an independent failure domain meeting objectives; zero split-brain; catalog/runbooks accessible outside primary region.

### 16.5. Scenario E — Backup With Checksum Failure

**Inject:** Controlled modification of one file in a test backup copy.

**Objective:** Prove integrity verification catches corruption and selects an alternate backup.

**Observe:**
- Manifest/checksum results.
- Alerting.
- Backup catalog state.
- Quarantining bad artifact.
- Restoring from another verified backup.

**Pass criteria:** Corrupted copy is never marked verified; alternate copy chosen; incident logged.

### 16.6. Scenario F — Encryption Key Unavailable

**Inject:** Recovery account fails to fetch key from primary key management service.

**Objective:** Validate break-glass access and isolated key backups.

**Observe:**
- Recovery identity.
- Key version/identifier.
- Approval path.
- Audit trail.
- Decryption duration.

**Pass criteria:** Key accessed per policy without secret leaks; authorization duration stays within RTO.

---

## 17. Post-Drill Finding Analysis and Improvements

### 17.1. Classifying Findings

- **Critical:** Unable to recover within RPO/RTO; missing base backup/WAL/key or missing recovery permissions.
- **High:** Restorable yet exceeds RTO, partial data missing, or validation fails.
- **Medium:** Documentation/alert/role coordination gaps with a workaround.
- **Low:** Minor issues not impacting current objectives.

### 17.2. Root Cause and Contributing Factors

Do not stop at "job failed." Document:
- Trigger.
- Technical root cause.
- Contributing conditions.
- Why alerts did not catch it sooner.
- Why backup/restore verification missed it.
- Impact on RPO/RTO.
- Remediation steps.
- Recurrence prevention measures.

### 17.3. Trackable Action Items

Every finding should have:
- ID.
- Specific description.
- Severity.
- Owner.
- Due date.
- Acceptance criteria.
- Evidence link.
- Status.
- Retest date.

"Improve monitoring" is not clear acceptance criteria. Better: "Alert when WAL generation > 0 and `last_archived_time` exceeds 5 minutes continuously; route alert to on-call DBA; verify by making staging archive destination read-only."

### 17.4. Retesting

After fixing, re-run the exact scenario or a targeted test to prove the issue is resolved. Close findings when verification evidence passes, not simply when code/config deploys.

### 17.5. Feeding Results into Capacity Planning

Restore drills yield real measurements for:
- Restore throughput.
- WAL replay throughput.
- Storage bandwidth.
- CPU/memory usage.
- Provisioning duration.
- Validation duration.
- Archive growth.
- Required disk headroom.

Use these figures to forecast RTO if database size doubles, WAL rate climbs, or storage providers change.

---

## 18. Backup and Recovery Drill Report Template

### 18.1. General Information

~~~text
Drill ID:
Date/time:
Environment:
Cluster/system identifier:
PostgreSQL major version:
Backup ID:
Backup type:
Scenario:
Recovery target:
Participants/roles:
~~~

### 18.2. Timeline Milestones

| Milestone | Start | End | Duration |
|---|---|---|---|
| Declare scenario | | | |
| Provision environment | | | |
| Retrieve/decrypt backup | | | |
| Restore base backup | | | |
| Replay WAL | | | |
| Start PostgreSQL | | | |
| Database validation | | | |
| Application validation | | | |
| Sign-off | | | |

### 18.3. Results

~~~text
Backup artifact verification:
WAL chain continuity:
Timeline/recovery target reached:
Database validation:
Application validation:
Measured RPO:
Measured RTO:
RPO objective:
RTO objective:
Overall result: PASS / PARTIAL / FAIL
Evidence location:
Findings:
Action owners and due dates:
Retest date:
~~~

### 18.4. Separate Failure Reports

A backup failure report should state:
- Job run ID/backup ID.
- Last successful backup.
- First failure timestamp.
- Redacted error class/message.
- WAL/archive impact.
- Current disk headroom.
- RPO exposure.
- Recovery action.
- Retry result.
- Whether restore capability remains proven.
- Incident owner.

### 18.5. Distinguishing PASS, PARTIAL, and FAIL

- **PASS:** all predefined acceptance criteria passed, including RPO/RTO and application validation.
- **PARTIAL:** partial recovery succeeded yet one or more criteria or evidence items are missing.
- **FAIL:** failed to recover to target, service validation failed, or objectives breached without an accepted fallback.

Never turn PARTIAL into PASS merely because the PostgreSQL process started.

---

## 19. Periodic Operations Checklist

### 19.1. Daily

- [ ] Fresh verified backup exists within SLA window.
- [ ] WAL archiving advances during WAL generation.
- [ ] Zero unresolved new archive failures.
- [ ] `pg_wal` filesystem has adequate headroom.
- [ ] Offsite copy status matches policy.
- [ ] Replication slots/standbys are not abnormally pinning WAL.
- [ ] Backup catalog updated with matching artifacts.
- [ ] Alert routing working.

### 19.2. Weekly

- [ ] Review backup duration/size/throughput trends.
- [ ] Review failure/retry trends.
- [ ] Verify sampled manifests/checksums.
- [ ] Review retention/lifecycle events.
- [ ] Review slot/archiver backlogs and disk growth.
- [ ] Run scheduled restore smoke test.
- [ ] Confirm key/credential recovery paths remain usable.

### 19.3. Monthly/Quarterly

- [ ] Full restore drill.
- [ ] Scheduled PITR drill.
- [ ] Offsite restore test.
- [ ] Check measured RTO/RPO.
- [ ] Tabletop exercise covering roles/access/communication.
- [ ] Review findings/action items.
- [ ] Test backup catalog recovery.
- [ ] Review retention and capacity forecasts.

### 19.4. After Changes

- [ ] Test backups after PostgreSQL/backup tool upgrades.
- [ ] Test restores after storage/network/KMS changes.
- [ ] Test WAL archiving after command/provider changes.
- [ ] Test tablespaces/configs/extensions after migrations.
- [ ] Update runbooks and inventories.
- [ ] Re-run relevant scenarios.

---

## 20. PostgreSQL Documentation References

Prefer official documentation matching your server's exact major version:

- [PostgreSQL — Backup and Restore](https://www.postgresql.org/docs/current/backup.html): overview of backup strategies.
- [PostgreSQL — SQL Dump](https://www.postgresql.org/docs/current/backup-dump.html): `pg_dump`/`pg_restore` and logical backups.
- [PostgreSQL — File System Level Backup](https://www.postgresql.org/docs/current/backup-file.html): physical backups.
- [PostgreSQL — Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): WAL archives and PITR.
- [PostgreSQL — pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): creating base backups.
- [PostgreSQL — pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): verifying backup manifests/checksums.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_archiver`, `pg_stat_wal`, and replication statistics.
- [PostgreSQL — pg_stat_progress_basebackup](https://www.postgresql.org/docs/current/progress-reporting.html): progress reporting.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): WAL/archiving settings.
- [PostgreSQL — Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication and standbys.
- [PostgreSQL — Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): recovery targets and `restore_command`.
- [PostgreSQL — amcheck](https://www.postgresql.org/docs/current/amcheck.html): verifying certain index structures.

`/current/` URLs may point to a newer release than the one you operate. Verify command options, view columns, recovery signal files, and configuration semantics for your exact major version.

---

## 21. Practice Exercises

Questions use a PostgreSQL lab or simulated environment. Never run destructive commands on production; all failure injection must stay inside isolated test environments.

### Exercise 1 — Backup Success

A backup job returns exit code 0 and logs `SUCCESS`. Why can you not yet conclude the database is restorable?

### Exercise 2 — Physical vs. Logical

Distinguish physical base backup + WAL archive from `pg_dump`. Which supports PITR via a WAL chain?

### Exercise 3 — Replicas

Why does a healthy standby not replace independent backups?

### Exercise 4 — RPO

Explain RPO using an example of a database with a 15-minute RPO.

### Exercise 5 — RTO

A cluster boots in 30 minutes, yet application smoke tests finish after 75 minutes. If RTO defines service usable, what is the actual RTO?

### Exercise 6 — Backup Schedule

Base backups run nightly and WAL archiving runs continuously. Must RPO equal 24 hours? What conditions decide?

### Exercise 7 — Backup Metadata

List at least eight metadata fields to store for each backup.

### Exercise 8 — `pg_stat_archiver`

Explain `archived_count`, `failed_count`, `last_archived_time`, and `stats_reset`. Why must `stats_reset` be tracked?

### Exercise 9 — Archive Freshness

`last_archived_time` is 2 hours old, yet the database generated zero WAL. Should you immediately alert on an archive failure? Why?

### Exercise 10 — WAL Generation

`pg_stat_wal.wal_bytes` increases by 300 MiB in 5 minutes. Calculate average WAL rate in MiB/min. State one limitation of this measurement.

### Exercise 11 — Replication Slots

An inactive logical replication slot pins an old `restart_lsn` and `pg_wal` grows. Why should you not drop the slot immediately?

### Exercise 12 — Base Backup Progress

`pg_stat_progress_basebackup` reports `backup_total` and `backup_streamed`. What do these fields prove and what do they not prove?

### Exercise 13 — `pg_ls_waldir`

Write a query counting WAL files and total size using `pg_ls_waldir()`.

### Exercise 14 — Backup Verification

What can `pg_verifybackup` check? Why is a restore drill still required?

### Exercise 15 — Logical Dumps

`pg_restore --list` succeeds. Does that prove a full restore will succeed? What should happen next?

### Exercise 16 — WAL Continuity

You have a base backup and the latest WAL segment, yet one middle segment is missing. Can you PITR past the gap? Explain.

### Exercise 17 — Encryption

Backups are encrypted, yet the key is accessible only from the production region. What is the risk and what must be drilled?

### Exercise 18 — Offsite

Why might a backup copy in the same cloud account/region fail to protect against a disaster or attacker?

### Exercise 19 — Retention

Why should you not delete WAL purely by file age?

### Exercise 20 — Backup Catalog

The catalog is lost while backup objects survive. Why can recovery still be hard? What else must be backed up?

### Exercise 21 — Archive Failures

`failed_count` rises and `pg_wal` usage climbs. List five investigation steps in order.

### Exercise 22 — Generation vs. Retention Pressure

Distinguish WAL generation pressure from WAL retention pressure. Can both occur at once?

### Exercise 23 — Missing WAL

Recovery reports a missing segment. List what to verify before concluding recovery is impossible.

### Exercise 24 — Restore Isolation

List at least five measures to prevent a test restore from causing side effects on production.

### Exercise 25 — Recovery Targets

Why does `recovery_target_time` need an explicit timezone? How should the target be verified?

### Exercise 26 — PITR Markers

Design a test with a marker before and a marker after the recovery target timestamp. What is the expected outcome?

### Exercise 27 — Application Validation

Why is `SELECT 1` insufficient to evaluate restore success? List four business checks.

### Exercise 28 — RTO Breakdown

List the timeline milestones to measure during a full restore drill.

### Exercise 29 — Tabletop Exercises

What gaps can tabletop exercises uncover? What do they fail to prove?

### Exercise 30 — Pass Criteria

A drill restores PostgreSQL cleanly yet takes 2x RTO. Should the result be PASS, PARTIAL, or FAIL? Explain using acceptance criteria.

### Exercise 31 — Backup Job Fails to Trigger

The scheduler does not trigger the job. Describe how to distinguish scheduler faults from PostgreSQL faults.

### Exercise 32 — Storage Failure

The archive destination returns permission denied. Why won't infinite retries solve this? What must be fixed?

### Exercise 33 — WAL Disk Nearly Full

The `pg_wal` filesystem has 5% free capacity, archive failures are rising, and an inactive slot exists. Outline a safe response sequence.

### Exercise 34 — Backup Duration Regression

Backup duration jumped from 20 to 90 minutes even though database size grew only 10%. List causes to check.

### Exercise 35 — Base Backup Missing Tablespace

Restore reports a missing tablespace path. Which metadata and infrastructure must be checked?

### Exercise 36 — Missing Extension

A physical backup restores yet PostgreSQL fails to start because an extension library is missing. Why does this happen and how do you prepare?

### Exercise 37 — Snapshot Consistency

A VM snapshot is taken while the database is running. Why can you not assume it is a valid backup by default?

### Exercise 38 — Immutability

Backups are immutable for 30 days, yet RPO/RTO requires restoring a point 60 days back. Which policies need review?

### Exercise 39 — Stale Restore Tests

Daily backups run cleanly, yet the last restore drill happened 9 months ago. What are the risks and what plan is needed?

### Exercise 40 — Failure Classification

A backup succeeds and passes local verification, yet offsite upload fails. How should the job be recorded in the backup catalog?

### Exercise 41 — RPO Calculation

An incident strikes at 12:00. The latest WAL confirmed safely archived is 11:52, yet a continuous segment chain is proven only up to 11:45. What RPO can be claimed?

### Exercise 42 — Post-Change Drills

A backup tool upgrade and KMS key rotation just finished. Which tests should run before considering the pipeline stable?

### Exercise 43 — Restoring from an Older Backup

The newest backup passes checksums yet its WAL chain misses a segment; an older backup has a complete chain. Which should you pick and why?

### Exercise 44 — Action Items

A finding states "monitoring is inadequate." Rewrite it as an action item with measurable acceptance criteria.

### Exercise 45 — Production Runbook

Base backups fail, archiving is also failing, `pg_wal` usage is climbing rapidly, and RPO is threatened. Write prioritized response steps.

---

## 22. Solutions — Exercises 1 to 25

### Exercise 1 — Backup Success

Exit code 0 confirms only that the process finished per the tool's success criteria. You still must verify completeness, manifests/checksums, WAL chains, offsite copies, test restores, and application validation. Backups can miss files or fail decryption even when jobs report success.

### Exercise 2 — Physical vs. Logical

Physical base backups are physical cluster copies; combined with continuous WAL archiving, they support PITR. `pg_dump` produces logical database/object dumps; it does not replace physical base backups and WAL archive chains.

### Exercise 3 — Replicas

Replicas receive and apply accidental `DELETE`s, bad `UPDATE`s, or logical corruption from the primary. Replicas serve HA/failover; independent backups with retention and PITR let you roll back prior to replicated mistakes.

### Exercise 4 — RPO

A 15-minute RPO means the organization accepts losing at most 15 minutes of data prior to an incident per agreed measurement rules. If the newest provable recovery point is 11:40 during a 12:00 incident, actual RPO is 20 minutes and misses the target.

### Exercise 5 — RTO

If the criterion is service usable after application smoke tests, RTO is 75 minutes—not 30 minutes when PostgreSQL started.

### Exercise 6 — Backup Schedule

No. Base backups provide the starting baseline; continuous WAL archiving brings recovery points far closer than 24 hours. Requirements: continuous archiving on the right timeline, accessible/decryptable storage, and a valid base backup.

### Exercise 7 — Backup Metadata

Examples: backup ID, system identifier, PostgreSQL version, backup type, start/end timestamps, start/stop LSNs, timeline, tablespaces, manifest/checksum, WAL range, encryption key ID, storage object version, retention expiry, verification status.

### Exercise 8 — `pg_stat_archiver`

`archived_count` tracks successful archives since stats reset; `failed_count` tracks failures; `last_archived_time` marks the latest success; `stats_reset` marks when counters reset. On reset, delta/count baselines must re-initialize; zero does not prove zero prior errors.

### Exercise 9 — Archive Freshness

Do not alert failure solely from timestamp. When a database is idle with no new segments to archive, an older `last_archived_time` is normal. Correlate with WAL generation, segment switch/`archive_timeout` policy, and destination health.

### Exercise 10 — WAL Generation

300 MiB / 5 minutes = **60 MiB/minute**. This is a cluster-wide counter covering all sessions/background activity and requires checking `stats_reset`.

### Exercise 11 — Replication Slots

Slots may serve logical consumers; dropping one can prevent the consumer from resuming from its last position, forcing full reinitialization/re-snapshot. Verify owner, consumer, `restart_lsn`, and business impact before dropping.

### Exercise 12 — Base Backup Progress

This view reports active phases and streamed bytes/estimated totals. It does not prove the process finished cleanly, manifests/checksums passed, offsite copies completed, or restores succeed.

### Exercise 13 — `pg_ls_waldir`

~~~sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)::bigint) AS wal_size
FROM pg_ls_waldir();
~~~

Requires appropriate privileges and supported versions; use filesystem metrics for true capacity monitoring.

### Exercise 14 — `pg_verifybackup`

It checks manifests and file checksums of physical backups per version capabilities. It does not replace full restores, WAL replay, key retrieval, application validation, or RTO measurement.

### Exercise 15 — Logical Dumps

No. `--list` only reads the TOC. Restore into an isolated database, verify extensions, roles/owners, schemas/data, and run application/business checks.

### Exercise 16 — WAL Continuity

You cannot replay past a missing mandatory segment. Recovery stops before the gap or fails to reach target. Search archive caches/offsite/version history for the segment, or pick an earlier recovery target.

### Exercise 17 — Encryption

If the primary region is lost, both backups and keys become inaccessible; RTO fails even if objects survive. Rehearse break-glass identities, key version retrieval, approvals/audits, and decryption from another region.

### Exercise 18 — Offsite

One incident, account compromise, region outage, or lifecycle misconfiguration can wipe/lock both primary and backups in the same failure domain. Separate accounts/regions/credentials and use immutable/offline copies per policy.

### Exercise 19 — Retention

WAL is a dependency of base backups/PITR. Deleting by age creates gaps in chains needed by retained backups. Delete strictly by backup set/dependencies and policy.

### Exercise 20 — Backup Catalog

Without a catalog, locating backup IDs, versions, timelines, WAL ranges, key IDs, tablespace mappings, and retention becomes difficult. Maintain independent backups of catalogs, encryption metadata, runbooks, and configuration inventories.

### Exercise 21 — Archive Failures

1. Read `pg_stat_archiver` and logs to identify the first failing file/error.
2. Check destination/quotas/permissions/networking/KMS.
3. Measure WAL generation and `pg_wal` disk headroom.
4. Check slots/standbys/`restart_lsn` pinning WAL.
5. Restore the archive pipeline and monitor catch-up and continuity; never delete WAL manually.

### Exercise 22 — Generation vs. Retention Pressure

Generation pressure is WAL produced faster than archiving/processing handles. Retention pressure is WAL unable to recycle because archiver/slots/standbys/checkpoints still require it. Both can happen together.

### Exercise 23 — Missing WAL

Identify filename, LSN, timeline, base backup ID, recovery target, archive catalog, logs, offsite copies, and version history. Exhaust all sources before concluding the furthest reachable target.

### Exercise 24 — Restore Isolation

Examples: isolated network, separate port/DNS, block outbound email/payments/webhooks, use test credentials, restrict egress, avoid production service discovery registration, never use roles with production write privileges.

### Exercise 25 — Recovery Targets

Ambiguous timezones cause targets to misalign and recover to the wrong time. Use explicit timezone offsets, pre/post-target markers, and verify recovery logs/target reached alongside data state.

---

## 23. Solutions — Exercises 26 to 45

### Exercise 26 — PITR Markers

Write marker A before target, then marker B after target. Restore to a timestamp between the markers. Expected outcome: A exists; B and post-target changes are absent. Verify timestamps/timezones and transaction commit boundaries.

### Exercise 27 — Application Validation

`SELECT 1` proves only that the server answers simple queries. Business checks should include:
- Daily order totals/monetary sums.
- Active account counts.
- Foreign key/orphan checks.
- Reading known sample transaction/order IDs.
- Checking outbox/event sequences or key invariants.

### Exercise 28 — RTO Breakdown

Provision host, fetch/decrypt backup, restore base backup, replay WAL, start PostgreSQL, database validation, application validation, routing/cutover, and sign-off.

### Exercise 29 — Tabletop Exercises

Tabletops reveal gaps in permissions, roles, escalation, communications, target selection, key access, dependencies, and runbooks. They do not prove artifacts restore or PostgreSQL replays WAL cleanly.

### Exercise 30 — Pass Criteria

If RTO is an acceptance criterion and restore took 2x RTO, the result is FAIL or PARTIAL per defined policy—never PASS simply because the server booted. Reports must call out unmet criteria clearly.

### Exercise 31 — Backup Job Fails to Trigger

Inspect scheduler logs, next run, job enabled/paused state, trigger history, host/service health, and job run IDs. If the scheduler never spawned a process, the fault is orchestration; if it ran, inspect backup tool logs and PostgreSQL logs to isolate server/connection faults.

### Exercise 32 — Storage Failure

Permission denied is normally a permanent config/IAM fault; infinite retries repeat the failure and trigger log storms. Fix IAM/ACL/ownership/secrets per least privilege, validate with a test upload, and retry only once the destination is writable.

### Exercise 33 — WAL Disk Nearly Full

1. Declare incident and record disk headroom/WAL growth.
2. Check `pg_stat_archiver`/logs/destination.
3. Restore archive connectivity/permissions.
4. Check generation rate and replication slots/standbys.
5. Identify the owner of the inactive slot; never drop without knowing its consumer.
6. Throttle write-heavy jobs if authorized.
7. Never delete WAL manually.
8. Monitor archive catch-up, slot progress, and recycling.
9. Verify WAL chain/backup recoverability post-remediation.

### Exercise 34 — Backup Duration Regression

Check actual data size, throughput, I/O latency, CPU/compression/encryption, network throttling, object storage, backup concurrency, WAL generation/FPI, snapshot behavior, and backup tool/version changes. Measure bytes/sec rather than elapsed wall-clock time alone.

### Exercise 35 — Tablespaces

Check backup manifest/catalog for all listed tablespaces, path mappings, symlinks/objects, mount points, permissions, capacity, and restore tool options. Provision matching paths or remap to new locations per supported workflows.

### Exercise 36 — Missing Extension

Physical backups preserve catalogs/data without necessarily carrying shared library binaries needed to load extensions on new hosts. Maintain package/version/name inventories, pre-install compatible binaries before restoring, and verify extensions in drills.

### Exercise 37 — Snapshot Consistency

Snapshots can catch mid-flight writes, span multiple unsynchronized volumes, or skip PostgreSQL backup/WAL semantics. Verify crash/application consistency, consistency groups, WAL capture, and provider restore instructions.

### Exercise 38 — Immutability

30-day retention will not satisfy a 60-day recovery point without a backup/WAL chain retained that far. Review retention horizons, archive lifecycles, legal policies, capacity, and dependencies; immutable locks never extend expired backups automatically.

### Exercise 39 — Stale Restore Tests

Backup tools/storage/keys/configs may have drifted, corruption may have accumulated, RTO may have grown, and key access may have expired. Run a restore smoke test immediately, schedule full restore/PITR drills, and retest after major changes.

### Exercise 40 — Catalog State

Record as locally verified yet offsite pending/failed (partial)—never mark complete under policies requiring offsite copies. Alert the owner, retry upload after fixing, verify destination, and update catalog state.

### Exercise 41 — RPO Calculation

Although a segment archived at 11:52, continuity is proven only up to 11:45. The proven safe recovery point is 11:45, so conservative RPO at the 12:00 incident is **15 minutes**. Never claim 8 minutes while the WAL chain has an unresolved gap.

### Exercise 42 — Post-Change Drills

Run manifest/checksum verification, restore smoke test, PITR/WAL archive test, offsite retrieval, key retrieval/decryption via recovery identity, application validation, and RTO measurement. Also test rollback/recovery paths if tool upgrades involved catalog migrations.

### Exercise 43 — Older Backup

Choose the older backup with a complete WAL chain if the desired recovery target sits within its window. A newer backup missing a segment cannot reach the target; newer timestamps never beat recoverability.

### Exercise 44 — Action Items

Example: "Within 10 days, add an alert when WAL generation > 0 and `last_archived_time` exceeds 5 minutes continuously; alert must attach cluster ID, last archived WAL, `failed_count` delta, `pg_wal` free space, and page on-call DBA. Test on staging by setting archive destination read-only and save the alert event as evidence."

### Exercise 45 — Production Runbook

1. Declare incident, record current RPO exposure, disk headroom, and latest verified backup.
2. Check archive failure logs, `pg_stat_archiver`, WAL generation, and destination.
3. Identify the latest restorable base backup and WAL chain.
4. Restore destination credentials/networking/quotas.
5. Inspect replication slots/standbys pinning WAL; identify owners before acting.
6. Throttle write-heavy imports/jobs if approved to preserve disk headroom.
7. Never delete WAL or drop unknown slots.
8. Monitor archive catch-up, disk usage, and continuity.
9. Take a fresh backup once the pipeline stabilizes; verify artifacts/offsite.
10. Run restore/PITR validation if the chain was impacted.
11. Update incident status/RPO and escalate per policy.

---

## 24. Quick Decision Table

| Signal | Possible Interpretation | Next Step |
|---|---|---|
| Backup job missing | Scheduler/agent never triggered | Check scheduler, schedule, host, and job history |
| Job exited non-zero | Backup tool/DB/storage failure | Read logs and classify error |
| Job succeeded yet manifest missing | Incomplete artifact | Mark partial; do not catalog as verified |
| `pg_stat_archiver` failures rising | `archive_command`/destination fault | Check logs, permissions, networking, quotas |
| Old last archive, idle WAL | May be normal | Cross-check WAL generation and archive policy |
| Old last archive, rising WAL | Archiving may be stalled | Alert and inspect destination/backlog |
| Rising `pg_wal` usage | Generation or retention pressure | Check `wal_bytes`, slots, archive, standbys |
| Inactive slot pinning old `restart_lsn` | Consumer stalled | Identify owner; recover consumer or drop with approval |
| `pg_verifybackup` fails | Manifest/file/checksum fault | Quarantine artifact; pick alternate backup |
| Verify passes yet restore fails | WAL/config/extension/key/restore path fault | Follow full restore runbook |
| PostgreSQL boots yet app fails | Roles/schema/secrets/data/dependencies | Run application validation and business checks |
| RTO exceeds target | Restore capacity/process insufficient | Analyze time breakdown, tune, and retest |
| Offsite copy pending | Failure domain protection incomplete | Alert, retry, and verify remote copy |
| Restore drill too stale | Recoverability unverified recently | Schedule smoke/full restore test |

---

## 25. Sample Drill Schedule and Record

A simple log can record each test run as follows:

| Field | Example |
|---|---|
| Drill ID | `DR-2026-11-01` |
| Cluster | `orders-prod` |
| Backup ID | `base-2026-11-14-0001` |
| Scenario | PITR before accidental DELETE |
| Target | `2026-11-14 10:30:00+07` |
| Start | `10:00` |
| Database ready | `10:42` |
| App validation complete | `10:55` |
| Measured RTO | `55 minutes` |
| Measured RPO | `7 minutes` |
| Result | PASS if objectives and all checks pass |
| Findings | None / list |
| Owner | DBA on-call |
| Retest | Per findings |

Table values are illustrative. Real drill records must store evidence paths and exact versions.

### 25.1. Backup and Restore Schedules Must Link Together

A backup schedule is meaningful only when restore tests pick an actual scheduled backup ID. Never test restores using a specially prepared side backup if the goal is proving the production pipeline.

### 25.2. Schedules Must Account for Error Detection Time

If corruption can go unnoticed for several days, retention must be long enough to retain a clean backup preceding the corruption. Keeping only a few days of backups risks every restore point already carrying the fault.

### 25.3. Validation Time Is Part of RTO

If restore finishes in 20 minutes yet manual business validation takes 2 hours, the service misses RTO if acceptance criteria require validation. Automate critical checks and store expected baselines securely.

---

## 26. Summary

Backup monitoring must answer three questions: **is the latest backup complete and intact, is WAL continuous up to the required recovery point, and has the organization actually restored successfully recently?**

Principles to remember:

1. **Backup success is not restore success:** verify artifacts, WAL, database, and applications.
2. **Physical backups and logical dumps serve different purposes:** `pg_dump` does not replace base backup/WAL PITR.
3. **Replicas are not independent backups:** logical errors replicate.
4. **RPO/RTO must be measurable:** define clear start/end markers and recovery points.
5. **Read `pg_stat_archiver` in context:** freshness, failure deltas, stats resets, and WAL generation.
6. **WAL generation differs from retention:** disk growth can come from workload or segments pinned by slots/archiver/standbys.
7. **Manifests/checksums are only one layer:** `pg_verifybackup` does not replace full restores.
8. **WAL chains must be continuous on the right timeline:** one missing segment caps recovery targets.
9. **Rehearse offsite/key access:** encrypted backups that cannot be decrypted are useless backups.
10. **Isolate restores:** block production DNS, outbound calls, credentials, and service discovery.
11. **Application validation is mandatory:** server startup and `SELECT 1` do not prove business data correctness.
12. **Tabletops and technical drills complement each other:** one tests coordination; the other proves technical execution.
13. **Measure RTO by milestone:** provision, retrieve, restore, replay, validate, and cutover.
14. **Findings need owners, due dates, and retests:** never close an issue simply because config deployed.
15. **Retention must preserve dependencies:** never prune WAL by file age while base backups still need that chain.
16. **Catalogs, keys, and runbooks need backups too:** recovery relies on metadata and access paths.
17. **Never delete WAL or drop slots reflexively:** identify owners/dependencies first.
18. **Drill after major changes:** tools, versions, storage, KMS, networking, and retention changes can all break recovery.

A trustworthy program follows a continuous loop: **schedule backups → verify artifacts → monitor WAL/archiving/retention → test restore from real storage → validate database and application → measure RPO/RTO → fix findings → drill again**.
