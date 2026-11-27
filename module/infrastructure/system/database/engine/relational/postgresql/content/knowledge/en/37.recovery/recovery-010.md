# Measuring Actual RPO, RTO, and Updating PostgreSQL Recovery Procedures

## 1. Why Must Recoverability Be Measured?

A system can report "backup succeeded" every day, have a WAL archive, standbys, and green dashboards, yet still take hours to recover when a real incident strikes. A base backup may lack WAL, object storage may be unreachable, encryption keys may be misplaced, tablespaces may be unprepared, or the runbook may contain commands for a different PostgreSQL major version.

Recoverability must be proven through measurement and drills. The two most critical metrics are:

- **RPO (Recovery Point Objective):** the maximum amount of data an organization tolerates losing during an incident, typically expressed in time.
- **RTO (Recovery Time Objective):** the maximum time an organization tolerates to restore a service to a usable state.

RPO and RTO are business objectives. Actual values can only be determined by observing backups, WAL, replication, infrastructure, procedures, and restore/failover outcomes.

```text
Incident occurs
     |
     +---- RPO ----> Latest recoverable data point
     |
     +---- RTO ------------------------------+
                                             |
                                             v
                                  Service operational again
                                  and verified
```

A solid procedure must answer:

1. When an incident happens, what is the latest data truly recoverable?
2. How much data was lost relative to successfully acknowledged transactions?
3. How long does it take to detect, decide, provision, restore/replay, validate, and open the service?
4. Do results meet the committed RPO/RTO targets?
5. If not, what architecture, configuration, resources, or process changes are required?

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish RPO, RTO, MTD/MTTR, recovery point, and backup freshness.
2. Define start/end milestones when measuring RPO and RTO.
3. Calculate actual RPO from committed/acknowledged data and post-recovery data.
4. Measure RTO across every phase instead of counting only restore command runtime.
5. Distinguish failover to a standby from PITR via base backup and WAL archive.
6. Read replication lag, archive status, WAL LSNs, and recovery logs.
7. Design transaction markers to prove the recovered data point.
8. Organize safe restore drills and failover drills.
9. Evaluate backup integrity, WAL continuity, timelines, keys, and tablespaces.
10. Verify data and applications after recovery.
11. Build RPO/RTO expectations per failure scenario.
12. Update runbooks, ownership, escalation, and evidence after every drill.
13. Feed measurement results into capacity planning and continuous improvement.

---

## 2. RPO and RTO: Two Distinct Objectives

RPO and RTO are often written side by side, yet they measure two different types of loss.

| Metric | Question | Common Units |
|---|---|---|
| RPO | How much data can be lost at most? | Seconds/minutes/hours or transactions |
| RTO | How long can service be down at most? | Seconds/minutes/hours |
| Actual RPO | How much data was actually lost in the recent incident/drill? | Time or transactions |
| Actual RTO | How long did it take from start to usable service? | Time |
| Backup age | How old is the latest base backup? | Time |
| Archive lag | How old is the latest unarchived WAL? | Time/LSN |
| Replication lag | How far behind primary is the standby per chosen metric? | Bytes/time/LSN |

### 2.1. Target Example

A service sets:

- RPO target: at most 5 minutes of data.
- RTO target: at most 60 minutes of outage.

This means that under the defined failure scenario, the organization accepts losing at most 5 minutes' worth of data and must return the service to a usable state within 60 minutes.

This is a commitment to be proven, not an automatic result simply from setting `archive_timeout` to 5 minutes or running nightly backups.

### 2.2. What Does RPO = 0 Mean?

RPO = 0 means zero loss of successfully acknowledged transactions within the committed failure model. This requires matching architecture and durability semantics, such as synchronous replication requiring durable WAL acknowledgment on an eligible standby.

Never promise RPO = 0 for all disasters merely because a standby exists. Simultaneous loss of primary, standby, region, or storage domain may fall outside the initial failure model.

### 2.3. RTO Is Not pg_restore/pg_basebackup Runtime

RTO encompasses the total time needed to recover the service: detection, decision-making, infrastructure provisioning, restoring files, replaying WAL, validation, cutover, and opening traffic. A completed restore command does not mean the service is ready.

## 3. Defining Milestones Before Measuring

Measurements cannot be consistent if every drill picks different start and end points.

### 3.1. RPO Milestones

For a physical failure, you can define:

- `T_failure`: the moment failure stops the system from acknowledging transactions normally.
- `T_last_recoverable`: the timestamp of the last acknowledged transaction present in the recovered database.

Then:

```text
Actual RPO = T_failure - T_last_recoverable
```

In environments with a ledger transaction sequence, also measure the count of transactions acknowledged on the old system yet absent in the recovered system. Measuring by transaction ID/sequence can be more accurate than timestamps when clocks or commit timestamps are unreliable.

### 3.2. RTO Milestones

The organization must formally define:

- `T_start`: when the incident began or when the incident was declared.
- `T_service_restored`: when the service satisfies agreed readiness criteria.

```text
Actual RTO = T_service_restored - T_start
```

Never shift `T_start` between reports to make RTO look shorter. If you want to separate detection and response times, record sub-milestones while keeping one official RTO definition.

### 3.3. When Is a Service Considered Restored?

Verifiable criteria are needed, such as:

- PostgreSQL recovered to the right target/timeline.
- Applications connect using production credentials.
- Core read operations succeed.
- Core write operations succeed if the service requires writes.
- Data invariants/critical tables pass checks.
- Connection pools, background workers, and dependencies operate.
- Traffic is routed to the right primary.
- Error rates and latency fall within acceptable bounds.

If the database starts yet the application cannot connect, service RTO has not ended.

## 4. Distinguishing Targets from Actual Results

A recovery report should present both target and actual metrics.

| Metric | Target | Drill Result | Met? |
|---|---:|---:|---|
| RPO | 5 minutes | 2 minutes 10 seconds | Yes |
| RTO | 60 minutes | 74 minutes | No |
| Restore verification | 100% critical checks | 98% | No |
| WAL continuity | Zero missing segments | Complete | Yes |

Numbers are illustrative. Meeting RPO while missing RTO is still a drill that failed overall requirements.

### 4.1. Never Report Only One Best Number

One successful 20-minute restore does not prove every restore takes 20 minutes. Record multiple runs, environment conditions, backup sizes, and percentiles.

### 4.2. Distinguishing Planned RTO from Observed RTO

- Planned RTO: design target or forecast.
- Observed RTO: measured result from a drill or incident.
- Worst observed: the slowest run in the test set.
- P95: 95th percentile when sample size and statistical method allow.

Never call an estimate an actual.

## 5. RPO Depends on the Failure Scenario

A single architecture's RPO is not necessarily identical across every failure mode.

| Failure Scenario | Common Recovery Path | What RPO Depends On |
|---|---|---|
| Primary process crash | In-place crash recovery | Durably written WAL and storage |
| Primary host loss | Promote standby or restore backup | Sync/async replication, archive |
| Storage/cluster loss | Restore base backup + WAL | Base backup, archive continuity |
| Accidental data deletion | PITR to before destructive transaction | WAL archive and target selection |
| Corruption spreading to backup | Alternate backup/immutable copy | Backup isolation and verification |
| Region loss | Cross-region standby/backup | Cross-region replication/archive lag |
| Replication link loss | Primary continues writes or throttles | Slot/WAL retention and topology |
| Ransomware/credential compromise | Clean-room restore | Immutable backups, keys, clean environment |

### 5.1. Failover RPO

For failover, compare the last acknowledged transaction on the old primary against the last transaction present on the promoted standby.

### 5.2. PITR RPO

For PITR, pick a target prior to the data-corrupting event. The RPO of lost valid data is the span from the last known-good commit to the chosen recovery point—not the time since DBAs noticed the issue if corruption occurred earlier.

### 5.3. Periodic Backup RPO

Daily backups do not automatically mean a 24-hour RPO if WAL is archived continuously and completely. Base backup cadence heavily impacts restore time and WAL replay volume; archive gaps are what break recoverability to recent points.

## 6. RTO Depends on the Entire Recovery Path

RTO typically spans these stages:

```text
Detect incident
      |
      v
Declare / decide recovery path
      |
      v
Fence old primary / prepare target
      |
      v
Provision compute and storage
      |
      v
Restore base backup or promote standby
      |
      v
Replay WAL / reach recovery point
      |
      v
Validate database and application
      |
      v
Cut over traffic
      |
      v
Observe service health
```

Some stages can run in parallel, such as network provisioning and backup metadata verification. When summing total RTO, use the real timeline and critical path; do not mechanically add every duration if tasks overlap.

### 6.1. Restore Throughput

Copy time depends on:
- Backup size.
- Storage/network throughput.
- Compression/encryption.
- File count and metadata overhead.
- Tool parallelism.
- Tablespace mapping.
- Host provisioning time.

### 6.2. WAL Replay Throughput

WAL replay depends on:
- Volume of WAL to replay.
- Random/sequential I/O and storage latency.
- CPU, compression, and checksums.
- Number of modified indexes/relations.
- Recovery conflicts if running on a standby.
- Settings and resource limits of the restore environment.

### 6.3. Validation and Cutover Also Take Time

Checking schemas, critical row counts, application smoke tests, sequence values, permissions, DNS, load balancers, and connection pools can consume a substantial share of RTO.

## 7. Differences Between Failover and PITR

### 7.1. Failover to Standby

Uses a standby already receiving WAL to become the new primary. Usually faster than restoring a full backup because data files are already on disk and most WAL is already replayed.

RPO depends on replication mode, standby state, acknowledged commits, and promotion timing.

### 7.2. PITR from Base Backup

Builds a data directory from a base backup and replays WAL to a target. Useful when:
- The entire cluster is lost.
- Rewinding before a destructive operation is required.
- Standbys already replayed the bad change.
- Building an isolated copy to extract data.

RTO is usually longer because provisioning, transfer/restore, and replay are needed.

### 7.3. Logical Restore

`pg_dump`/`pg_restore` is valuable for object-level recovery/migration, yet restoring large datasets can be slower than physical restore. Measure this backup path separately.

### 7.4. Never Let One Drill Represent Every Path

A fast failover drill does not prove PITR works. A passing PITR drill does not prove failover avoids split-brain. Every failure scenario needs its corresponding test.

## 8. Measuring RPO with Transaction Markers

A practical technique is writing a periodic marker transaction and, after commit succeeds, logging that marker into an independent witness system.

Sample table in the database:

```sql
CREATE SCHEMA IF NOT EXISTS dr_test;

CREATE TABLE dr_test.recovery_marker (
    marker_id uuid PRIMARY KEY,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    sequence_no bigint NOT NULL,
    note text
);
```

A test agent performs:
1. Generate a unique `marker_id`.
2. Write the marker transaction to PostgreSQL.
3. `COMMIT`.
4. Only after the server confirms `COMMIT` succeeded, record `marker_id`, `sequence_no`, and timestamp in an external witness/monitoring system.
5. After failover/restore, query the latest marker present in the database.
6. Compare against the witness ledger.

### 8.1. Why Is an Independent Witness Needed?

Looking only at markers inside the recovered database cannot tell you which newer markers were acknowledged before the incident. The external witness records commits that the test agent saw acknowledged.

### 8.2. The Witness Also Needs Durability

If the external witness shares the same failure domain as the database, one outage can wipe out both. Use an appropriate independent logging/monitoring system and ensure durable writes.

### 8.3. Never Log to the Witness Before COMMIT

Logging a marker to the witness before commit can report a transaction as "acknowledged" even though the database never committed it. Log to the witness strictly after receiving a successful `COMMIT`.

### 8.4. Markers Do Not Replace Application Transaction Ledgers

Markers measure recovery paths and WAL/replication behavior. They do not prove every business table, sequence, or transaction pattern is consistent. Verify application data separately.

## 9. Computing RPO by Timestamp and Transaction Sequence

Sample external witness log:

```text
10:00:00.000 marker 1001 COMMIT acknowledged
10:00:05.000 marker 1002 COMMIT acknowledged
10:00:10.000 marker 1003 COMMIT acknowledged
10:00:15.000 marker 1004 COMMIT acknowledged
10:00:20.000 primary failure
```

After recovery, the latest marker is 1002. Thus:
- Last acknowledged marker: 1004.
- Last recoverable marker: 1002.
- Lost acknowledged markers: 1003 and 1004.
- Approximate time gap: 10 seconds from marker 1002 to failure, per the example's definition.

### 9.1. Measuring by Transaction

```sql
SELECT
    max(sequence_no) AS last_recovered_sequence,
    max(committed_at) AS last_recovered_marker_time
FROM dr_test.recovery_marker;
```

Compare sequence against the external witness to count lost markers. With a 5-second marker cadence, lost marker count does not equal exact lost business transactions; it is a periodic probe, not a full audit.

### 9.2. Timestamps Require Clock Synchronization

Use NTP/chrony or an appropriate time synchronization service across hosts/databases/witnesses. Store UTC timestamps and display explicit timezones. Clock skew distorts time-based RPO.

### 9.3. Use a Monotonic Clock for Durations

To measure elapsed duration within a process, use the OS/test harness monotonic clock rather than subtracting wall-clock timestamps that may jump. Record both wall-clock event times and elapsed durations.

## 10. Measuring RPO in Replication Failover

On the primary, observe standby state via `pg_stat_replication`:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

General meaning:
- `sent_lsn`: WAL sent to standby.
- `write_lsn`: WAL written by standby.
- `flush_lsn`: WAL flushed by standby per protocol.
- `replay_lsn`: WAL replayed by standby.
- `sync_state`: synchronous/asynchronous state per configuration.

### 10.1. LSN Lag in Bytes

Compare current LSN against standby LSN:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS replay_lag_bytes
FROM pg_stat_replication;
```

This is the LSN gap at query time. It does not directly indicate failover data-loss duration and can change right after the snapshot.

### 10.2. Lag Intervals Have Limits

`write_lag`/`flush_lag`/`replay_lag` are recent sampled lag indicators under suitable conditions; they are not guarantees that a standby will lose that exact amount of time if the primary crashes. When idle, values may be NULL or fail to reflect current backlog.

### 10.3. Measuring on the Standby

Inspect:

```sql
SELECT
    pg_last_wal_receive_lsn() AS last_received_lsn,
    pg_last_wal_replay_lsn() AS last_replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

`last_replayed_commit_time` can appear stale even on a caught-up standby if the primary has no new transactions. Never rely on that timestamp alone to alert on lag during idle workloads.

### 10.4. Verify After Promotion

After promoting, compare marker sequences on the new primary against the witness ledger. That gives the actual measurement of acknowledged data loss in the drill.

## 11. Synchronous Replication and RPO Commitments

Synchronous replication can reduce RPO for transactions acknowledged after WAL reaches standbys at the configured sync level.

Concepts to distinguish:

- `synchronous_standby_names`: specifies which standbys participate in synchronous acknowledgment.
- `synchronous_commit`: wait level before confirming commit.
- `remote_write`: waits for standby OS write, not durable disk flush.
- `on`: with synchronous replication, waits for standby durable WAL flush per PostgreSQL semantics.
- `remote_apply`: waits for standby WAL replay, useful for read-after-write on standbys.

### 11.1. RPO = 0 Holds Only Within a Defined Failure Model

If commit acknowledgment waits for durable standby flush and that exact standby is promoted, acknowledged commits can survive certain failure scenarios. This does not cover simultaneous failures, misconfigurations, forced promotion of another standby, or loss of the entire failure domain.

### 11.2. Trade-Offs of Synchronous Replication

- Commit latency increases with network/standby flush latency.
- Standby/network outages can stall transactions or impact availability per configuration.
- Requires careful quorum/standby availability design.
- Actual promotion policy must be verified.

### 11.3. Never Check Only the Setting

Seeing `synchronous_commit = on` does not prove the cluster has an active synchronous standby. Inspect `pg_stat_replication`, `synchronous_standby_names`, `sync_state`, and run failover drills.

## 12. Measuring Archive Freshness and WAL Continuity

When using a WAL archive for PITR, monitor `pg_stat_archiver`:

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

### 12.1. Archive Age

```sql
SELECT
    now() - last_archived_time AS age_since_last_archive,
    archived_count,
    failed_count,
    last_archived_wal,
    last_failed_wal
FROM pg_stat_archiver;
```

This only shows elapsed time since the last successful archive. When there are no writes or no segment switch yet, an older timestamp does not automatically prove WAL loss.

### 12.2. Archive Continuity Matters More Than Last Success

An archive with the latest segment uploaded yet missing a segment in the middle still cannot recover continuously to the target. Verify inventories, archive logs, and real restore execution.

### 12.3. Timeline History

Retain associated `.history` files. When failover creates a new timeline, history files are required for recovery to select the right WAL branch.

### 12.4. Archive Storage Availability

Measure:
- Upload successes/failures.
- Oldest unarchived WAL.
- Object storage latency.
- Capacity/quotas.
- Checksum verification.
- Credential expiration.
- Replication slot retention.

## 13. What Does Base Backup Age Affect?

Base backup cadence typically impacts:
- Time required to copy/restore.
- Volume of WAL to replay after the base backup.
- Storage cost.
- Retention windows.
- Ability to pick an intact base backup.

A base backup every 24 hours does not automatically mean a 24-hour RPO if WAL is archived continuously and completely. However, an older backup increases WAL replay time, impacting RTO.

### 13.1. Measuring Restore Duration Across Backup Ages

Run restore tests using:
- The newest base backup.
- A backup mid-way through the retention window.
- The oldest retained backup.

The goal is understanding worst-case RTO within retention policy, not just the fastest restore path.

### 13.2. The Newest Backup Is Not Always Best

The latest backup may be corrupted, missing WAL, on slow storage, or on an unsuitable timeline. Select a valid backup using metadata/verification.

### 13.3. Incremental Backup Chains

When using incremental backups, restore time also depends on combining/parent chains. Measure the entire chain, not just downloading the newest incremental.

## 14. Building a Service-Tier RPO/RTO Matrix

Not every database carries the same criticality.

Illustrative policy example:

| Tier | Example Workload | RPO Target | RTO Target |
|---|---|---:|---:|
| Tier 0 | Ledger/payment core | 0–1 minute per failure model | 15 minutes |
| Tier 1 | Customer/order OLTP | 5 minutes | 60 minutes |
| Tier 2 | Internal reporting | 1 hour | 4 hours |
| Tier 3 | Historical analytics | 24 hours | 24–48 hours |

Numbers must be agreed upon by business owners, engineering, and operations—never copied blindly.

### 14.1. Ranking by Business Impact

Consider:
- Legal/financial impact of data loss?
- Can the service run temporarily read-only?
- Are manual workarounds available?
- How long until customers are affected?
- Downstream system dependencies?

### 14.2. One Cluster May Host Multiple Tiers

If a database serves multiple workloads, define the recovery unit. A cluster/database restore affects every schema; you cannot assume independent per-table RTOs inside a single physical cluster.

### 14.3. Every Objective Must Have an Owner

Every RPO/RTO requires a business owner and a technical owner. DBAs should never commit to an RTO that infrastructure, applications, and networking cannot sustain.

## 15. Planning Phase-by-Phase RTO Measurement

An event log table for a drill:

| Phase | Milestone Recorded | Example Duration |
|---|---|---:|
| Detect | Alert/incident start | 3 minutes |
| Declare | Incident commander decision | 4 minutes |
| Fence | Block old primary/split-brain | 2 minutes |
| Provision | Host/storage/network | 8 minutes |
| Restore | Copy/prepare base backup | 18 minutes |
| Replay | Replay WAL to target | 12 minutes |
| Validate | DB + application checks | 10 minutes |
| Cutover | DNS/routing/pools | 5 minutes |
| Observe | Smoke/health confirmation | 5 minutes |

Example total is 67 minutes if sequential. If steps overlap in parallel, compute along the real critical path.

### 15.1. Use Structured Timestamps

Record event ID, step name, start time, end time, elapsed duration, actor, and evidence link.

### 15.2. Separate Decision Wait Time

An incident can take 20 minutes just deciding whether to restore. That is part of real RTO and should be improved with clear decision trees/ownership.

### 15.3. Separate Technical Restore from Service Recovery

You can record:
- Database available time.
- Application read-ready time.
- Application write-ready time.
- Full service restored time.

Use the final milestone as primary RTO when business requires complete service restoration.

### 15.4. Measure Both Manual and Automated Time

If a step waits on an on-call engineer logging in, approving, or locating credentials, measure that time. Never omit human latency.

## 16. Designing Safe Restore Drills

Restore drills must run in an isolated environment without impacting production traffic.

A physical/PITR drill:
1. Select backup ID and recovery target.
2. Verify backup manifest/checksums.
3. Provision host/storage.
4. Download and restore base backup.
5. Configure tablespaces/permissions.
6. Configure `restore_command` and recovery target.
7. Create `recovery.signal` if needed.
8. Start PostgreSQL and monitor replay.
9. Pause/promote per test design.
10. Run data/application checks.
11. Record RPO/RTO.
12. Clean up the test environment per policy.

### 16.1. Drills Must Use Real Artifacts

Use the actual backup repository and production WAL archive, not a special demo dataset prepared solely for the test.

### 16.2. Never Overwrite Production

Use isolated networks/ports/hostnames. Disable application jobs, outbound integrations, and scheduled workers that could send emails, trigger payments, or cause external side effects.

### 16.3. Test Failure Paths Too

Simulate scenarios such as:
- Missing archive object.
- Manifest checksum mismatch.
- Missing tablespace mount.
- Unreachable encryption key.
- Recovery target past the last WAL.
- Missing timeline history.
- Insufficient disk space.
- Expired credentials.

The goal is uncovering failure points and detection times.

## 17. Failover Drills vs. Restore Drills

Failover drills test:
- Standby has sufficient WAL.
- Synchronous/async state.
- Promotion procedure.
- Fencing the old primary.
- DNS/load balancer/connection routing.
- Repointing replicas.
- Application retry behavior.
- Split-brain prevention.

### 17.1. Do Not Just Run pg_promote()

A successful promotion command does not prove the service failed over cleanly. Confirm the old primary cannot accept writes, the new primary is on the right timeline, applications reconnect, and replication topology is restored.

### 17.2. Fencing

There must be a mechanism stopping the old primary from accepting writes once a new primary is promoted. This may require cloud/VM/storage/network fencing per architecture. It is essential to prevent split-brain.

### 17.3. Measure Actual Data Loss

Use transaction markers/witness ledgers and compare acknowledged commits. Never rely on replay lag intervals alone as actual RPO.

### 17.4. Measure Time to Write-Ready

An endpoint health check returning 200 is insufficient. Run a controlled test transaction and confirm commit/read-back on the new primary.

## 18. Post-Recovery Data Verification

PostgreSQL starting cleanly does not mean business data fully satisfies the recovery goal.

Verification layers:

### 18.1. Cluster-Level

- Server version/cluster identity.
- Recovery target and timeline.
- Database list.
- Roles/tablespaces/extensions.
- WAL recovery logs.
- Replication/archive state.

### 18.2. Database-Level

- Schemas/tables present.
- Critical row counts or aggregate totals.
- Constraints and indexes valid.
- Sequences/identity values.
- Permissions/ownership.
- Large objects and TOAST-backed values.
- Expected migration/schema version.

### 18.3. Application-Level

- Authentication.
- Read/write paths.
- Critical API operations.
- Background workers.
- Message queues/outbox.
- External storage dependencies.
- Payment/notification integrations in test or controlled mode.

### 18.4. Business Invariants

Examples:
- Balanced debit/credit totals.
- Every order has a valid status.
- No duplicate payments.
- Foreign keys/business references intact.
- Event sequences show no unexpected duplicates or gaps.

### 18.5. Do Not Rely Solely on COUNT(*)

Matching row counts do not prove matching contents. Use checksums/aggregates/semantic invariants on critical tables.

## 19. Checking Sequences and Identity After PITR

When restoring to a point in time, sequence states belong to the recovered data. Before opening writes, verify next sequence values align cleanly without colliding with existing keys.

Inspect sequence state via version-appropriate catalog/sequence functions. Never blindly reset sequences to `MAX(id)+1` across every table without understanding cache, ownership, partitioning, and concurrent writes.

### 19.1. Sequences Can Have Gaps

Sequence values are non-transactional unlike row updates; rollbacks leave gaps. Never demand gapless sequences unless business design truly enforces it.

### 19.2. PITR and External Systems

If the database rewinds prior to a payment yet the payment gateway already processed it, reconcile with external systems. PITR does not roll back out-of-database side effects.

### 19.3. Outbox/Inbox Patterns

If the application uses an outbox, verify event delivery and consumer idempotency after recovery to avoid duplicate deliveries or missed side effects.

## 20. Updating Recovery Procedures After Every Drill

Runbooks are living operational documents. After every drill or incident, update:

- PostgreSQL version and backup/restore tool versions.
- Recovery scenarios and decision trees.
- RPO/RTO targets and actuals.
- Backup IDs/WAL ranges/timelines used.
- Exact commands/options.
- Hostnames/ports/storage mappings.
- Credential/secret retrieval paths (never put secrets in the document).
- Tablespace paths and capacity.
- Network/firewall/DNS/load balancer steps.
- Validation queries and application smoke tests.
- Owners/approvers/escalation contacts.
- Known limitations and failure modes.
- Next drill date.

### 20.1. Version Control

Store runbooks in source control or a document system with revision history, reviews, and proper access controls.

### 20.2. Never Store Passwords in Runbooks

Document where to fetch secrets, which roles are needed, and the authorization workflow. Secrets belong in an appropriate secret manager/vault.

### 20.3. Attach Evidence to Every Step

Each step should specify:
- Expected result.
- Actual result.
- Log/metric/query output reference.
- Failure condition.
- Escalation path.

### 20.4. Set a Review Expiration Date

Runbooks do not remain valid forever. Always review after major upgrades, storage changes, cloud region moves, DNS changes, or backup tooling updates.

## 21. Recovery Decision Tree

```text
Incident declared
      |
      v
Is primary healthy and data logically valid?
      |
      +-- Yes -> repair/restart or crash recovery
      |
      +-- No
           |
           v
Can a trusted standby be promoted safely?
           |
           +-- Yes -> fence old primary -> promote -> validate
           |
           +-- No
                |
                v
Is there a verified base backup + continuous WAL?
                |
                +-- Yes -> restore + replay to selected target
                |
                +-- No
                     |
                     v
              Find alternate backup/replica
              and declare actual RPO limitations
```

### 21.1. Logical Corruption

If the primary is still running yet a transaction corrupted data, do not rush to promote a standby if the standby already replayed the bad transaction. PITR to a target before corruption is usually better.

### 21.2. Physical Loss

If the primary host/storage is lost, a healthy standby often yields a lower RTO than restoring a full backup. Still, fencing and replication state verification are mandatory.

### 21.3. Incomplete WAL

Pick another recoverable backup/replica, identify the last recoverable point, and report actual RPO. Never claim PITR to a point lacking WAL.

## 22. Re-Evaluating RPO/RTO When Architecture Changes

Changes that can invalidate past measurements:
- Database growth.
- Higher WAL generation rates.
- Added indexes/TOAST-heavy columns.
- Storage class/region moves.
- Compression/encryption changes.
- Sync/async replication changes.
- Changes in standby count or quorum.
- Backup cadence/retention changes.
- Restore tool changes.
- Added partitions or tablespaces.
- Application dependency changes.

After every major change, run representative benchmarks/drills and update target feasibility.

### 22.1. Projecting Growth

An RTO of 40 minutes at 1 TB may not hold when the database grows to 3 TB. Measure throughput and replay rates to forecast, then confirm via testing.

### 22.2. WAL Generation Bursts

Bulk loads, index builds, batch updates, or full-page writes can spike WAL generation. Archive bandwidth must handle peaks, not just averages.

### 22.3. Sync Replication Changes

Changing `synchronous_standby_names` or `synchronous_commit` alters commit latency and durability guarantees. Update failure models/RPO and re-drill.

## 23. RPO/RTO and Backup Frequency

Backup frequency directly impacts the restore chain:

- More frequent base backups: less WAL to replay, yet higher storage/network/backup load.
- Less frequent base backups: lower backup load, yet restores may need to replay more WAL.
- Continuous WAL archiving: enables PITR between two base backups.
- Archive gaps: can halt recovery prior to the target.

```text
Backup A
   |
   +-- WAL 1 -- WAL 2 -- WAL 3 -- WAL 4 -- Backup B
                                  |
                                  +-- PITR target
```

### 23.1. Do Not Treat Backup Interval as Actual RPO

If WAL archiving is continuous and durable, the actual recoverable point can be much closer to failure time than the base backup timestamp.

### 23.2. Backup Frequency Can Improve RTO

Newer base backups reduce WAL replay volume, though you must measure because transfer, restore, and manifest verification still carry overhead.

### 23.3. Choose Intervals from Restore Tests

Test varying base backup ages and compare total restore times, storage costs, and backup load. Pick the interval balancing RTO and capacity.

## 24. RPO/RTO and archive_timeout

`archive_timeout` forces new segment archiving more often during low-write workloads, yet it does not guarantee an RPO equal to the configured value.

Actual RPO also depends on:
- Whether segments switch and archive.
- Whether `archive_command` succeeds.
- Whether files persist in an independent failure domain.
- Whether any middle segment is missing.
- Whether the backup chain and timeline are valid.
- Which commits were acknowledged prior to the incident.

A 5-minute `archive_timeout` cannot save an `archive_command` that has been failing for 2 hours.

## 25. RPO/RTO and Replication Lag

Replication lag can be measured via:
- LSN bytes.
- Write/flush/replay positions.
- Time interval metrics.
- Transaction marker sequences.
- External witnesses.

Never rely on one single number to represent everything.

### 25.1. Byte Lag Is Not Time Lag

100 MB of WAL can represent seconds or many minutes depending on workload. WAL generation rates fluctuate.

### 25.2. Replay Lag Is Not Acknowledged Data Loss

A standby may replay slowly yet have already received/flushed the WAL. On promotion, potential data loss depends on promotion semantics and retained WAL, not replay lag alone.

### 25.3. Synchronous State Must Be Verified

If RPO relies on synchronous replication, verify which standby was synchronous at failure time. A standby outside the synchronous quorum may lack some acknowledged commits.

## 26. Measuring Archiving and Replication via LSN

On the primary:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_insert_lsn() AS current_insert_lsn;
```

Inspect replica positions on the primary:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS replay_lag_bytes
FROM pg_stat_replication;
```

On the standby:

```sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

### 26.1. LSNs Must Be Compared on the Same Cluster/Timeline

Never subtract LSNs from two separate clusters and call it replication lag. After promotion, timelines change and history must be accounted for.

### 26.2. Sample Metrics Over Time

A single query shows no trend. Record samples with timestamps, server identity, and timeline for analysis.

### 26.3. Version Compatibility

Some functions/view fields differ across versions. Check `pg_catalog`/`pg_settings` and docs for your exact server version before embedding queries in long-term monitoring.

## 27. Measuring RTO in Clean-Room Recovery

Clean-room recovery restores into an isolated environment free of dependencies on compromised production hosts/credentials/storage.

Measure each component:
1. Creating/initializing the environment.
2. Retrieving credentials and encryption keys.
3. Downloading the base backup.
4. Verifying manifest/checksums.
5. Restoring data/tablespaces.
6. Retrieving WAL archives.
7. Replaying to target.
8. Starting and verifying PostgreSQL.
9. Running application validation.
10. Routing traffic or exposing data to the application.

### 27.1. Testing Loss of Production Access

A strong DR drill proves the backup team can still access repositories and keys even if the production identity provider or primary account fails, per the defined threat model.

### 27.2. Testing Offsite Copies

Do not test only backups residing near the primary. Pick copies in an independent failure domain to measure real RTO during site/region loss.

### 27.3. Testing Realistic Capacity

Restoring 2 TB on an 8-vCPU/SSD machine does not represent restoring 2 TB on a smaller DR host. Match production specs or document any discrepancy.

## 28. Targeted RTO Optimization

If RTO falls short, break down bottlenecks before buying more hardware.

| Bottleneck | Potential Improvements |
|---|---|
| Slow provisioning | IaC, pre-created networks, quota reservations |
| Slow backup download | DR-local storage, parallel transfers, throughput budgets |
| Slow file restore | Faster storage, proper parallelism, file layout |
| Slow WAL replay | Newer base backups, higher restore capacity, replay benchmarks |
| Slow validation | Automated checks and test data contracts |
| Slow DNS/cutover | Lower TTLs, tested runbooks, automation |
| Missing credentials | DR secret access paths and escrow |
| Slow human decisions | Clear decision trees, owners, and escalation |
| Slow replication rebuild | Standby topology and WAL retention planning |

### 28.1. Do Not Optimize One Step While Ignoring the Critical Path

If backup download consumes 80% of RTO, speeding up SQL validation by 20% barely lowers total RTO.

### 28.2. Warm Standbys

A pre-provisioned standby continuously replaying WAL reduces RTO, trading off compute/storage/network cost and requiring strict fencing/failover discipline.

### 28.3. Backup Restore Parallelism

Increasing parallel jobs improves throughput when storage/CPU have headroom. Too many workers cause contention; benchmark on representative data.

## 29. Targeted RPO Optimization

If actual RPO falls short:
- Fix archive failures and missing WAL first.
- Reduce archive upload latency.
- Strengthen durability and failure-domain independence.
- Consider streaming replication.
- Consider synchronous replication for tiers needing very low RPO.
- Tune `archive_timeout` where appropriate.
- Retain sufficient WAL and timeline history.
- Monitor replication slots and archive backlogs.
- Use transaction markers/witnesses to confirm.

### 29.1. Do Not Just Lower archive_timeout

If uploading an object takes 10 minutes or retries for 30 minutes, a 1-minute `archive_timeout` will not improve actual RPO.

### 29.2. Do Not Expand WAL Retention Indefinitely

Retaining WAL longer consumes storage and capacity. Tie retention to the backup catalog/recovery windows and slot consumers.

### 29.3. Sync Replication Does Not Replace Backups

Synchronous standbys also receive erroneous transactions or accidental deletions. PITR/backups remain indispensable for recovering logical corruption and broader disasters.

## 30. Defining Success for Each Drill Type

| Drill | Success Criteria |
|---|---|
| Backup verification | Manifest/checksums and metadata valid |
| Base restore | Server starts and reaches consistency |
| PITR | Stops at exact target/timeline; pre-incident data intact |
| Standby failover | Right node promoted, old primary fenced, app write-ready |
| Regional DR | Restored/failed over in separate failure domain; dependencies ready |
| Application recovery | Critical read/write flows and invariants pass |
| Ransomware recovery | Clean immutable copies/keys used in clean environment |
| Runbook tabletop | Participants make right decisions; owners/escalation clear |

### 30.1. Backup Verification Is Not a Restore Drill

`pg_verifybackup` validates base backups against manifests/checksums. It does not prove WAL archives are complete or that the application works.

### 30.2. Tabletop Is Not a Technical Drill

Tabletops validate decisions and roles; they do not measure restore/replay throughput.

### 30.3. Failover Drills Are Not PITR Drills

Each drill tests a different recovery path. Schedule each type according to risk.

## 31. Sample Drill Schedule

A reference schedule to tailor by tier and risk:

| Frequency | Check | Goal |
|---|---|---|
| Daily | Backup/archiver health, capacity, replication | Catch failures early |
| Weekly | Verify manifests and inventory WAL | Confirm artifacts are verifiable |
| Monthly | Restore a base backup + WAL to target | Measure physical restore and replay |
| Quarterly | Failover/standby promotion drill | Measure failover RPO/RTO and fencing |
| Quarterly/semi-annually | Regional/clean-room recovery | Test offsite copies, keys, and dependencies |
| After major changes | Relevant targeted drill | Revalidate runbooks and assumptions |

### 31.1. Pick Representative Samples

Do not restore only the smallest database. Rotate through large, partitioned, TOAST-heavy clusters and high-WAL-rate workloads.

### 31.2. Off-Hours Drills Do Not Replace Daytime Readiness Checks

Readiness and access paths can be checked during business hours, while fault injection requires guardrails and change approvals.

### 31.3. Never Run Drills Only for Audits

A backup can break right after an audit passes. Maintain steady cadence and automated alerts.

## 32. Measuring with Percentiles and Trends

Across multiple drills, record:
- Actual RPO.
- Actual RTO.
- Restore duration.
- WAL replay duration.
- Validation duration.
- Transfer throughput.
- WAL generation rate.
- Error/retry counts.

Report:
- Median.
- P95 when sample size permits.
- Maximum observed.
- Trends against data size and workload.
- Breakdowns by scenario/region/backup age.

### 32.1. Do Not Aggregate Different Scenarios Together

PITR from a base backup and standby failover have completely different RTO distributions. Report separately per scenario.

### 32.2. Small Sample Sizes Can Mislead

Three drills are not enough to claim a stable P95. Always report sample count and test conditions.

### 32.3. Measure Variance Too

If average RTO is 45 minutes yet one run took 3 hours due to a credential outage, tail risk matters far more than the average.

## 33. Evidence Record for Each Drill

A minimum record:

```text
drill_id:
scenario:
service_tier:
database_cluster:
postgres_major_version:
source_backup_id:
source_backup_timestamp:
timeline:
recovery_target:
incident_start_utc:
last_acknowledged_marker:
last_recovered_marker:
actual_rpo:
actual_rto:
provision_duration:
backup_transfer_duration:
restore_duration:
wal_replay_duration:
validation_duration:
cutover_duration:
backup_verification:
wal_continuity:
application_checks:
data_invariants:
issues:
owner:
reviewer:
runbook_revision:
follow_up_actions:
next_test_date:
```

### 33.1. Document Environmental Conditions

Include instance size, storage class, network path, region, compression, and concurrency. Otherwise, two drills cannot be fairly compared.

### 33.2. Avoid Logging Unnecessary Secrets or Sensitive Data

Evidence should hold controlled identifiers/log references—never passwords, private keys, or full business payloads.

### 33.3. Link Evidence to Runbook Revision

If a drill used an older runbook revision, record it explicitly so teams know whether the current procedure has been verified.

## 34. Runbook Update Process

After every drill/incident:

1. Compare actual RPO/RTO against targets.
2. Identify which phase or assumption caused delays or data loss.
3. Classify root cause: architecture, configuration, capacity, tooling, access, decision-making, or human process.
4. Create corrective actions with owners and deadlines.
5. Update command/config examples for current server versions.
6. Update decision trees, validation queries, and escalation paths.
7. Review with DBAs, application owners, infrastructure/security, and business owners.
8. Merge/publish the new revision per document management procedures.
9. Re-run the failing portion of the drill.
10. Schedule the next review date.

### 34.1. Updates Must Be Concrete

Never write "optimize restore." Write, for example: "Increase DR network throughput from X to Y; goal to cut backup transfer from 42 to 25 minutes; owner: Platform; verify in drill on..."

### 34.2. Runbooks Must Be Versioned

Record PostgreSQL version, `pg_basebackup`/restore tool versions, extensions, and operating environment. Recovery syntax changes across major versions.

### 34.3. Keep Change History

Never overwrite past drill results. Revision history explains why procedures evolved and whether improvements actually worked.

## 35. Ownership and Escalation

Recovery typically spans multiple teams:

| Role | Responsibility |
|---|---|
| Incident commander | Declares incident, coordinates decisions and timeline |
| DBA | Chooses recovery path, manages PostgreSQL/WAL/recovery |
| Infrastructure | Provisions compute, storage, and networking |
| Security | Credentials, keys, clean-room controls |
| Application owner | Smoke tests and business invariants |
| Network/DNS | Routing, fencing, and endpoint changes |
| Business owner | Approves RPO/data loss and cutover decisions |
| Communications | Updates stakeholders on status |

### 35.1. One Person May Hold Multiple Roles

In smaller teams, one engineer may wear several hats. Runbooks must still specify who decides and who executes.

### 35.2. Never Let Approvals Bottleneck RTO

Pre-define authority for promotion, restore targets, data-loss acceptance, and traffic cutover. Do not hunt for approvers mid-incident.

### 35.3. Access Paths Must Be Tested

A DBA may know every command yet lack credentials if the production identity provider is down. Test break-glass access per policy.

## 36. Controlling Risk During Drills

Drills can cause impact if run in the wrong environment or accidentally connected to production.

Before starting:
- Confirm environment and scope.
- Confirm zero production traffic routes.
- Disable jobs/integrations with side effects.
- Use test credentials.
- Set resource quotas.
- Define stop conditions.
- Assign observers and escalation contacts.
- Confirm cleanup plans.

### 36.1. Production Failover Tests

If drilling on production, require change management, small blast radius, rollback/fencing plans, stakeholder approvals, and active monitoring. Never simulate primary loss by killing servers arbitrarily.

### 36.2. Chaos Testing

Fault injection belongs only in environments designed for it. Start with tabletops and sandbox restores, then raise realism within controlled guardrails.

### 36.3. Halt the Drill When Guardrails Are Breached

Examples: application latency exceeds threshold, replication lag exceeds limit, storage approaches capacity, or split-brain risk arises. Log why the drill stopped—that itself is valuable operational evidence.

## 37. Common Mistakes When Measuring RPO/RTO

### Mistake 1 — Calling Backup Interval the RPO

Daily backups do not equal a 24-hour RPO when WAL archives run continuously.

### Mistake 2 — Calling archive_timeout the RPO

It is merely a WAL-switching parameter, not proof of archive success or continuity.

### Mistake 3 — Calling Replication Lag the Actual RPO

Lag metrics do not directly report acknowledged transactions lost upon promotion.

### Mistake 4 — Measuring RTO Only as Restore Command Duration

Omits detection, decision, provisioning, validation, and cutover.

### Mistake 5 — Failing to Define Start/End Milestones

Reports using shifting definitions cannot be compared.

### Mistake 6 — Unsynchronized Clocks

Timestamps across primary, standby, witness, and test agent can drift.

### Mistake 7 — Skipping an External Witness

Leaves no way to know which markers were acknowledged before failure.

### Mistake 8 — Checking Only That the Database Starts

Applications may still fail to connect, fail writes, or see invalid data.

### Mistake 9 — Not Testing the Real WAL Archive

Restoring synthetic test files does not prove production archive continuity.

### Mistake 10 — Testing Only Failover, Not PITR

Standbys also replay destructive transactions; PITR remains essential.

### Mistake 11 — Not Testing Region/Key Loss

Same-site restores do not prove cross-region/clean-room DR.

### Mistake 12 — Omitting Backup ID and Timeline

Makes the recovery path impossible to reproduce.

### Mistake 13 — Not Measuring Worst-Case

A good average can mask a 3-hour restore caused by missing credentials or archive objects.

### Mistake 14 — Not Updating the Runbook

Drills uncover bugs while procedures keep stale commands.

### Mistake 15 — No Owner for Corrective Actions

Issues are logged yet never fixed.

### Mistake 16 — Ignoring External Side Effects

PITR can roll the database back prior to already-executed external payments/emails/events.

### Mistake 17 — Marker Cadence Too Coarse

A marker every 30 minutes lacks resolution to verify a 5-minute RPO.

### Mistake 18 — Marker Transactions Using a Different Durability Path

Test markers must traverse the exact same database/commit/replication path as the target workload.

### Mistake 19 — Measuring Only One Database Size

RTO shifts with size, WAL rate, indexes/TOAST, and storage.

### Mistake 20 — Skipping Recovery Target Timezone/Timeline Checks

Recovery can succeed technically yet land on the wrong data point.

## 38. Example: Evaluating a 5-Minute RPO, 60-Minute RTO System

Suppose targets are:
- RPO <= 5 minutes.
- RTO <= 60 minutes.

A restore drill yields:
- Incident start: `02:00:00 UTC`.
- Last acknowledged marker: `02:00:00 UTC`.
- Last recovered marker: `01:58:30 UTC`.
- Service write-ready: `03:04:00 UTC`.

Then:
- Actual RPO = 1 minute 30 seconds.
- Actual RTO = 64 minutes.

RPO passed; RTO failed.

### 38.1. Time Breakdown

| Phase | Duration |
|---|---:|
| Detect/declare | 8 minutes |
| Provision | 10 minutes |
| Restore base backup | 20 minutes |
| WAL replay | 12 minutes |
| Validation | 9 minutes |
| Cutover | 5 minutes |
| Total | 64 minutes |

### 38.2. Selecting Improvements

If restoring the backup dominates elapsed time, consider:
- Increasing backup frequency if storage/cost allows.
- Using higher-throughput storage in DR.
- Optimizing parallel restore.
- Keeping a warm standby for tiers requiring low RTO.
- Automating provisioning and validation.

Do not reduce `archive_timeout` to fix RTO when RPO already passes and the bottleneck is restore/replay.

### 38.3. Re-Measure After Improvements

Use the exact same scenario, dataset size, environment class, and milestone definitions for fair comparison.

## 39. Example: RTO Met Yet RPO Missed

Suppose:
- RPO target: 5 minutes.
- RTO target: 60 minutes.
- Standby failover completes in 12 minutes.
- Last acknowledged marker on old primary: `10:30`.
- Last marker on promoted standby: `10:18`.

Actual RPO is roughly 12 minutes; RTO is 12 minutes.

RTO passed, yet RPO failed. Investigate:
- Async replication lag.
- Network throughput/interruptions.
- Standby replay/flush position.
- Whether promotion picked the right standby.
- Transaction acknowledgment semantics.
- Whether synchronous replication is needed for this tier.

Never conclude "fast failover means success."

## 40. Example: PITR After Logical Corruption

A transaction accidentally deletes 200,000 rows at `14:00`. Operations detects it at `14:20`.

Steps:
1. Stop the deleting job and restrict related writes.
2. Identify the destructive transaction/time/LSN.
3. Choose a recovery target immediately prior to that transaction.
4. Restore base backup and replay WAL to target.
5. Verify recovered rows.
6. Assess legitimate writes committed after the target.
7. Extract/merge rescued data or cut over per business decision.
8. Measure RTO until the application functions properly.

In this scenario, detection time `14:20` is not the target boundary. Find when corruption actually happened. Legitimate transactions after the target may be lost and require reconciliation.

## 41. Updating Dashboards and Alerts

RPO/RTO dashboards should separate signals:

### Backup Health
- Last successful base backup.
- Backup duration/size.
- Manifest verification.
- Backup age.
- Restore drill results.

### WAL Archive Health
- Last archived WAL/time.
- Failed archive count delta.
- Archive backlog/oldest pending.
- WAL generation rate.
- Archive storage capacity.
- Timeline history inventory.

### Replication Health
- Synchronous state.
- Sent/write/flush/replay LSNs.
- Byte lag/time lag.
- Slot retained WAL.
- Standby availability.

### Recovery Readiness
- Last successful PITR drill.
- Last failover drill.
- Actual RPO/RTO trends.
- Encryption key access tests.
- Tablespace/host readiness.
- Runbook revision and owner.

### 41.1. Actionable Alerts

Every alert must include:
- Severity.
- Resource/cluster.
- Trigger and duration.
- Potential RPO/RTO impact.
- Query/log/evidence.
- Runbook link.
- Owner/escalation.

### 41.2. Avoid Alert Noise

Use persistence/hysteresis for fluctuating metrics, yet never delay critical alerts such as sustained WAL archive failures, near-full disks, or XID wraparound risk.

### 41.3. Dashboards Do Not Replace Drills

A green dashboard only confirms metrics sit inside thresholds. Restore drills verify end-to-end recovery.

## 42. Evaluating Target Attainment by Scenario

A summary report table:

| Scenario | RPO Target | RPO Actual | RTO Target | RTO Actual | Status |
|---|---:|---:|---:|---:|---|
| Primary host loss | 1 minute | 20 seconds | 15 minutes | 12 minutes | Met |
| Region loss | 5 minutes | 4 minutes | 60 minutes | 82 minutes | RTO Missed |
| Logical corruption | 5 minutes | 3 minutes | 120 minutes | 105 minutes | Met |
| Backup repository loss | 15 minutes | 18 minutes | 4 hours | 5 hours | Missed |

Numbers are illustrative. Always record date, sample count, backup age, data size, and test environment.

### 42.1. Never Collapse Status into One Color

Passing RPO while missing RTO are distinct outcomes. State explicitly which metric failed and who owns the corrective action.

### 42.2. Prioritize Fixes

Prioritize by:
- Business impact.
- Gap relative to target.
- Scenario probability.
- Improvement feasibility.
- Cost and risk of change.

## 43. Drill Report Template

```text
DRILL REPORT
============

Drill ID:
Date:
Service / Database:
Scenario:
PostgreSQL version:
Runbook revision:
Backup ID:
Timeline:
Recovery target:

OBJECTIVES
----------
RPO target:
RTO target:
Validation criteria:

OBSERVED DATA
-------------
Incident start UTC:
Last acknowledged transaction marker:
Last recovered transaction marker:
Actual RPO:
Service restored UTC:
Actual RTO:

TIMING
------
Detection:
Decision:
Fencing:
Provision:
Backup transfer:
Restore:
WAL replay:
Validation:
Cutover:
Observation:

RESULTS
-------
Backup manifest:
WAL continuity:
Database checks:
Application checks:
Business invariants:
Replication/archive reconfigured:

GAPS
----
RPO gap:
RTO gap:
Technical blockers:
Process blockers:

ACTIONS
-------
Action:
Owner:
Due date:
Verification drill:
Runbook revision:
Next test:
```

## 44. Runbook Update Template

A runbook update should record:

| Field | Content |
|---|---|
| Revision | Document version |
| Changed at | Update timestamp |
| Reason | Which drill/incident/change prompted the edit |
| Scenario | Failure scenario updated |
| Previous behavior | Prior result/limitation |
| New procedure | New step or command |
| Preconditions | Version, role, storage, network |
| Expected result | Completion criteria |
| Stop condition | When to halt/escalate |
| Verification | Queries, logs, application checks |
| Owner | Accountable person |
| Reviewer | Reviewer |
| Drill evidence | Link to test results |
| Next review | Next inspection date |

Never put secrets, passwords, or private keys into runbooks.

## 45. Practice Exercises with Answers

### Exercise 1. What is RPO?

**Answer:** The maximum amount of data an organization tolerates losing in a defined failure scenario, usually measured in time or transaction counts.

### Exercise 2. What is RTO?

**Answer:** The maximum acceptable duration to restore a service to a usable state.

### Exercise 3. Does a backup every 24 hours mean RPO is always 24 hours?

**Answer:** No. If WAL archiving is continuous and complete, the recovery point can sit much closer to failure time than the base backup.

### Exercise 4. Does archive_timeout = 5 minutes guarantee a 5-minute RPO?

**Answer:** No. It still depends on segment switching, archive success, durability, and WAL continuity.

### Exercise 5. Is RTO equal to pg_basebackup runtime?

**Answer:** No. RTO spans detection, decision, provisioning, restore/replay, validation, and cutover.

### Exercise 6. Formula for actual RPO by timestamp?

**Answer:** `T_failure` minus `T_last_recoverable_commit`, per agreed milestone definitions.

### Exercise 7. Formula for actual RTO?

**Answer:** `T_service_restored` minus `T_start`.

### Exercise 8. When is a service considered restored?

**Answer:** When both database and application satisfy agreed read/write, validation, and routing criteria.

### Exercise 9. Why is an external transaction witness needed?

**Answer:** To know which commits were acknowledged prior to the incident and compare against markers surviving recovery.

### Exercise 10. Should you log to the witness before COMMIT?

**Answer:** No. Log only after the database confirms commit succeeded.

### Exercise 11. Is a marker every 30 minutes suitable for testing a 5-minute RPO?

**Answer:** No. The cadence is too coarse and lacks sufficient resolution.

### Exercise 12. Why must clocks be synchronized?

**Answer:** To compare timestamps accurately across primary, standby, witness, and test agent.

### Exercise 13. What should a monotonic clock be used for?

**Answer:** Measuring elapsed durations unaffected by wall-clock adjustments.

### Exercise 14. What measures failover RPO better than a lag interval?

**Answer:** Comparing acknowledged transaction markers on the old primary against markers present on the promoted standby.

### Exercise 15. Is replay_lag the actual RPO?

**Answer:** No. It is a lag metric and does not directly report acknowledged commits lost upon promotion.

### Exercise 16. Which LSNs does pg_stat_replication provide?

**Answer:** `sent_lsn`, `write_lsn`, `flush_lsn`, and `replay_lsn` along with associated states.

### Exercise 17. Does byte lag convert directly to time lag?

**Answer:** No. It depends on WAL generation rate and workload.

### Exercise 18. Can synchronous replication reduce RPO?

**Answer:** Yes, when commit acknowledgment waits for the standby to reach an appropriate durability level and promotion selects an eligible standby within the failure model.

### Exercise 19. Are remote_write and on identical?

**Answer:** No. `remote_write` waits for the standby OS write; `on` with synchronous replication waits for durable WAL flush per PostgreSQL semantics.

### Exercise 20. Does RPO = 0 apply to all disasters?

**Answer:** No. It is guaranteed only within the defined failure model and durability assumptions.

### Exercise 21. Does a failover drill prove PITR works?

**Answer:** No. PITR requires restoring a base backup and replaying WAL to a target; it must be tested separately.

### Exercise 22. Is PITR appropriate when a standby already replayed an accidental deletion?

**Answer:** Usually yes. Restore to a target prior to the destructive transaction.

### Exercise 23. Why must the old primary be fenced?

**Answer:** To stop the old primary from accepting writes after promotion, preventing split-brain.

### Exercise 24. Does the database starting mean RTO has ended?

**Answer:** No. The application must pass read/write and validation criteria.

### Exercise 25. Which backup should a restore drill use?

**Answer:** Real backups from the repository and production WAL archive per procedure, in an isolated environment.

### Exercise 26. Does pg_verifybackup replace a restore drill?

**Answer:** No. It checks manifests/checksums; it does not prove end-to-end recovery and application functionality.

### Exercise 27. Why must offsite backups be tested?

**Answer:** To prove recoverability if the primary failure domain is lost.

### Exercise 28. How should a target be chosen in logical corruption RPO?

**Answer:** Identify the corrupting transaction/time and recover to the last known-good point prior to it; account for legitimate post-target writes needing reconciliation.

### Exercise 29. Why does PITR not roll back external payments?

**Answer:** WAL only recovers PostgreSQL; external side effects require separate reconciliation.

### Exercise 30. Which phases make up RTO?

**Answer:** Detection, decision, fencing, provisioning, restore, WAL replay, validation, cutover, and service observation per organizational definitions.

### Exercise 31. Why measure P95 RTO?

**Answer:** Averages can hide slow restores; percentiles reveal tail behavior given enough samples.

### Exercise 32. Should RPO and RTO be collapsed into a single status?

**Answer:** No. One metric can pass while the other fails.

### Exercise 33. Does base backup cadence affect RPO or RTO?

**Answer:** Primarily WAL replay volume and RTO; RPO depends mainly on WAL archiving/replication continuity.

### Exercise 34. Does the latest archive succeeding prove WAL continuity?

**Answer:** No. A middle segment can still be missing; check inventories and restores.

### Exercise 35. What is the role of timeline history files?

**Answer:** Describing relationships between timeline branches so recovery follows the right WAL branch.

### Exercise 36. Which owners are needed for a 60-minute RTO?

**Answer:** DBA, infrastructure, application, security, network, and business decision owners depending on the service.

### Exercise 37. Should runbooks contain passwords?

**Answer:** No. Document only secret retrieval paths and required roles.

### Exercise 38. What must be updated after every drill?

**Answer:** Actual RPO/RTO, evidence, bottlenecks, commands, preconditions, validation, ownership, corrective actions, and revision.

### Exercise 39. When should drills be re-run?

**Answer:** Per cadence/risk and after major changes to versions, storage, topology, backup tooling, keys, or application dependencies.

### Exercise 40. How do warm standbys help?

**Answer:** They can lower RTO because data is already restored/replayed; trade-offs include cost and failover/fencing discipline.

### Exercise 41. Can RTO be improved with more frequent base backups?

**Answer:** It can reduce WAL replay volume, though total transfer/restore cost and backup load must be measured.

### Exercise 42. If RPO fails while RTO passes, what takes priority?

**Answer:** Investigating archive/replication durability, WAL continuity, and promotion selection—not just speeding up restore.

### Exercise 43. What if RPO passes while RTO fails?

**Answer:** Analyze the critical path—provisioning, transfer, restore, replay, validation, cutover—and optimize the largest bottleneck.

### Exercise 44. Why test keys in clean-room DR?

**Answer:** Encrypted backups without accessible keys cannot be restored.

### Exercise 45. Is checking database row counts sufficient?

**Answer:** No. Constraints, sequences, application smoke tests, and business invariants are required.

### Exercise 46. Can the final marker represent every business transaction?

**Answer:** Not completely. Markers probe recovery paths; external ledgers and data validation are still needed for critical business flows.

### Exercise 47. Are RPO/RTO permanent fixed numbers?

**Answer:** No. Dataset size, WAL rate, topology, storage, and dependencies evolve, requiring re-measurement.

### Exercise 48. Is a drill halted due to storage exceeding guardrails a wasted failure?

**Answer:** No. It provides valuable evidence on capacity/operational risk; record the stop condition and corrective action.

### Exercise 49. Why record the runbook revision in a drill report?

**Answer:** To track which procedure was tested and confirm whether the current revision is verified.

### Exercise 50. What is required to declare RPO/RTO met?

**Answer:** Clear targets/scenarios, trustworthy measurements, verified restore/failover, actual values within bounds, and archived evidence.

## 46. RPO/RTO Measurement and Procedure Update Checklist

| Stage | Item to Confirm |
|---|---|
| Pre-drill | Scenario, scope, and failure model clearly defined |
| Pre-drill | RPO/RTO targets and start/end definitions agreed |
| Pre-drill | Backup ID, WAL range, timeline, and keys ready |
| Pre-drill | External witness/transaction markers active |
| Pre-drill | Clock synchronization and UTC logging verified |
| Pre-drill | Isolated environment with no production routing |
| During drill | Detection/decision/provision timestamps recorded |
| During drill | Restore/replay/failover progress recorded |
| During drill | Old primary fenced if promoting |
| During drill | Guardrails and stop conditions monitored |
| Post-drill | Last acknowledged vs. recovered markers compared |
| Post-drill | Actual RPO calculated per definition |
| Post-drill | Service-ready timestamp confirmed |
| Post-drill | Actual RTO calculated per definition |
| Post-drill | Data/business/application checks completed |
| Post-drill | RPO and RTO evaluated separately |
| Post-drill | Bottlenecks and assumptions documented |
| Post-drill | Corrective actions assigned owner/deadline |
| Post-drill | Runbook revision updated |
| Post-drill | Next drill date scheduled |

## 47. Official PostgreSQL Documentation

- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html) — base backups, WAL archiving, and PITR.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — creating physical base backups.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html) — verifying backup manifests.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — replication, archiver, activity, and progress views.
- [Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION) — WAL streaming and standbys.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) — durability/acknowledgment semantics.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — WAL settings and archive timeout.
- [Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET) — recovery targets and PITR.
- [pg_stat_replication](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW) — sender/standby LSN positions.
- [pg_stat_archiver](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ARCHIVER-VIEW) — archive success/failure statistics.
- [pg_create_restore_point](https://www.postgresql.org/docs/current/functions-admin.html) — creating named restore points.

Views, fields, recovery options, and replication semantics can change across PostgreSQL major versions. When implementing runbooks, verify `server_version`, `pg_settings`, and documentation for your running version.

## 48. Summary: Measure, Drill, Update, and Re-Measure

```text
Set business objectives
       |
       v
Define scenarios + RPO/RTO
       |
       v
Prepare backups, WAL, standbys, keys
       |
       v
Run restore/failover drills
       |
       v
Measure acknowledged vs. recovered data
       |
       v
Measure elapsed time to service-ready
       |
       v
Validate data and applications
       |
       v
Compare actuals against targets
       |
       v
Fix architecture / capacity / runbooks
       |
       v
Re-drill
```

Principles to remember:

1. **RPO measures tolerable data loss; RTO measures tolerable service outage duration.** Both objectives must be defined separately.
2. **Actual RPO requires comparing acknowledged commits against recovered data.** Lag metrics alone are insufficient.
3. **Actual RTO ends only when the service satisfies usability criteria.** Database startup is just one stage.
4. **Each failure scenario has a distinct recovery path.** Failover, PITR, regional DR, and logical corruption must be tested separately.
5. **Transaction markers need a durable external witness.** Log to the witness after `COMMIT` and use synchronized clocks.
6. **Base backup cadence mainly impacts restore/replay duration.** WAL continuity governs PITR capability between backups.
7. **Synchronous replication protects only within its failure model and acknowledgment semantics.** It does not automatically guarantee RPO = 0 in all disasters.
8. **Restore drills must use real backups/archives.** Manifest verification never replaces end-to-end restores.
9. **Validation covers database, application, and business invariants.** Do not check only whether the process started.
10. **RTO must be measured along the critical path.** Provisioning, transfer, replay, validation, and cutover can all become bottlenecks.
11. **Runbooks require versioning, owners, and evidence.** Every drill must yield concrete corrective actions.
12. **When architecture changes, re-measure targets.** Dataset size, WAL rates, storage, topology, and dependencies all shift outcomes.

**One takeaway to remember:** *RPO/RTO are only meaningful when measured against an explicit failure scenario using verifiable data and timestamps; every drill must produce concrete evidence and a stronger recovery procedure.*
