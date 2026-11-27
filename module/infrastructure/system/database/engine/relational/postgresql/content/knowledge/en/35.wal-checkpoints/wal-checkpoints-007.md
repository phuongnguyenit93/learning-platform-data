# wal_level, Retention, and the Needs of Different Replication Types in PostgreSQL

PostgreSQL records critical database changes into the **Write-Ahead Log (WAL)** before the corresponding data pages are durably written to data files. WAL enables the database to recover after failures, supports backups/PITR, and feeds standbys or CDC systems.

Three configurations are commonly discussed together:

- **wal_level**: determines how much information PostgreSQL writes to WAL for crash recovery, archiving, physical replication, and logical decoding.
- **WAL retention**: determines how long or how far back old WAL is retained so a consumer can still read it.
- **Replication/archiving configuration**: specifies which consumers need WAL, how PostgreSQL retains WAL, and what resource limits apply.

These three concepts are related but do not replace each other. Selecting wal_level=logical does not automatically guarantee retaining enough WAL for a logical subscriber stopped for several days. Conversely, retaining vast amounts of WAL cannot produce logical change records if the server only runs at wal_level=replica.

A sound design must answer three questions:

1. **What kind of information does the consumer need in WAL?**
2. **How long can a consumer stay offline before the WAL it needs is reclaimed?**
3. **Are disk capacity, WAL generation rate, archiving, and replica lag able to sustain that window?**

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain WAL, WAL records, LSNs, and WAL segments.
2. Distinguish between wal_level=minimal, replica, and logical.
3. Choose wal_level based on crash recovery, PITR, physical replication, and logical replication/CDC needs.
4. Distinguish WAL generation from WAL retention.
5. Understand the roles and limits of wal_keep_size, replication slots, max_slot_wal_keep_size, max_wal_size, and min_wal_size.
6. Configure WAL archiving, archive_command, archive_timeout, and archive retention.
7. Explain why physical standbys, cascading standbys, logical subscribers, and backups/PITR have different requirements.
8. Understand how replication slots retain WAL, restart_lsn, confirmed_flush_lsn, and disk exhaustion risks.
9. Size WAL capacity from WAL generation rates and consumer outage budgets.
10. Monitor primary, standby, archiver, and replication slots using system views.
11. Diagnose archive failures, replication lag, inactive slots, and missing WAL on standbys.
12. Plan wal_level changes, restarts, failovers, backups, and safe WAL cleanup.

## 2. What Is WAL?

WAL is a sequence of records describing the changes required for PostgreSQL to recover the database. Instead of immediately writing every modified data page to its exact spot before confirming a transaction, PostgreSQL writes WAL first and flushes data pages later.

This is the **write-ahead** rule:

```text
Transaction modifies row
          |
          v
Generate WAL records
          |
          v
WAL written/flushed per durability requirements
          |
          v
Transaction can confirm COMMIT
          |
          v
Data pages written to data files later
```

If the server crashes after commit confirmation but before all dirty data pages are written, PostgreSQL uses WAL to redo required changes upon restart.

### 2.1. WAL Is Not a Copy of SQL Statements

WAL is not simply a log file storing verbatim UPDATE or INSERT statements sent by applications. WAL stores storage/recovery-level records along with information needed for replication/decoding modes. Record contents depend on operation type, wal_level, PostgreSQL version, and related settings.

### 2.2. WAL Is Not a Business Audit Log

Do not treat WAL as a human-readable business history answering "who changed an email and why." WAL exists for recovery and replication. If you need an audit trail, design audit tables, an event log, or a CDC pipeline with proper schema and retention.

### 2.3. WAL Is Not an Independent Backup

WAL enables recovery only when paired with a matching base backup or existing database state. A standalone WAL directory cannot replace a full backup.

## 3. WAL Records, LSNs, and Segments

### 3.1. LSN

A **Log Sequence Number (LSN)** is a position in the WAL stream. LSNs are commonly displayed as two hexadecimal parts:

```text
0/16B6C50
0/16B7A20
0/16C0128
```

LSNs increase as WAL is written. LSNs let you compare WAL positions across the primary, standbys, and replication slots.

Commonly used functions:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
```

The pg_current_wal_* functions apply to primaries and supported versions; function names in older PostgreSQL versions may differ.

### 3.2. WAL Segment

WAL is divided into segment files inside the pg_wal directory. A common segment size is 16 MB, though this is a PostgreSQL build/initdb property and should not be hardcoded in capacity calculations.

A segment completes when PostgreSQL switches to the next segment. An old segment may be:

- Retained because crash recovery/checkpoint still needs it.
- Retained because a standby or replication slot still needs it.
- Waiting for successful archiving.
- Recycled for reuse.
- Deleted once no longer needed and policy permits.

### 3.3. WAL Directory

On modern versions, the WAL directory is typically:

```text
$PGDATA/pg_wal/
```

Never delete or edit files in pg_wal using manual filesystem commands. PostgreSQL manages segment lifecycles; manual deletion can break recoverability or prevent the server from starting.

### 3.4. WAL Generation Rate

WAL generation rate is the volume of WAL produced over a time interval. It varies with:

- Volume of INSERT/UPDATE/DELETE operations.
- Row size and number of indexes updated.
- Bulk loads and DDL operations.
- Full-page images after checkpoints.
- Logical decoding requirements.
- Active workloads and enabled PostgreSQL features.

You cannot deduce WAL generation from transactions per second alone; one transaction updating many large rows can emit more WAL than thousands of tiny transactions.

## 4. What Does wal_level Control?

wal_level determines how much information is written to WAL. PostgreSQL has three main levels:

| Value | Purpose | Supported Needs |
| --- | --- | --- |
| minimal | Reduces WAL info to what is needed for crash recovery | Local crash recovery; cannot be used for archiving/PITR or replication |
| replica | Writes enough info for WAL archiving and physical replication | Crash recovery, PITR, physical streaming/cascading replication, hot standby |
| logical | Adds info needed for logical decoding | Everything in replica plus logical replication/CDC |

The common default in modern PostgreSQL is replica.

### 4.1. minimal

minimal logs only the information needed to recover the database after a crash or unclean shutdown. At this level, PostgreSQL can optimize certain bulk operations like creating or loading new relations by omitting full relation data from WAL in ways that break replication and archiving.

In return:

- Cannot use WAL archiving for PITR.
- Does not support hot standby or physical streaming replication.
- Does not support logical decoding.
- Unsuitable for systems needing standbys or CDC.

Never choose minimal for a production primary just to trim WAL if the system has backup/PITR or replication requirements.

### 4.2. replica

replica logs sufficient information to support WAL archiving and physical replication, including hot standby.

This is the appropriate choice for:

- A primary with one or more physical standbys.
- Synchronous or asynchronous streaming replication.
- Cascading replication.
- WAL archives paired with base backups for PITR.
- Backup systems requiring continuous WAL.

replica does not include full row-level change details for logical decoding like logical does.

### 4.3. logical

logical adds WAL information needed for logical decoding. It is a prerequisite for PostgreSQL logical replication and CDC systems using logical decoding output plugins.

logical still supports all physical replication capabilities of replica, though it can add WAL overhead depending on workload and enabled features.

Use it when you need:

- PostgreSQL publications/subscriptions.
- CDC over the logical replication protocol.
- Output plugins such as pgoutput or other plugins.
- Partial table sync or row-change data transformations.

### 4.4. Choosing a Higher Level Does Not Automatically Create Consumers

Setting wal_level=logical does not automatically create publications, subscriptions, replication slots, or CDC consumers. It only instructs PostgreSQL to log the needed information. Everything else must be configured separately.

## 5. wal_level and WAL Retention Are Two Separate Issues

This is a very easy point to confuse:

- wal_level answers **what information WAL contains**.
- Retention answers **how far back old WAL is kept**.

Example:

1. Primary runs wal_level=logical.
2. Logical subscriber stops for 24 hours.
3. A replication slot holds needed WAL while the subscriber is offline.
4. If the disk fills up or a slot cap forces reclaiming needed WAL, the subscriber may be unable to resume from its old position.

wal_level=logical does not by itself guarantee a subscriber keeps its WAL forever.

### 5.1. WAL Generation

The rate at which new WAL is created.

### 5.2. WAL Retention

The amount/duration of WAL not yet eligible for removal because a consumer or recovery requirement still needs it.

### 5.3. WAL Archival

Copying completed WAL segments to an external archive outside pg_wal.

### 5.4. WAL Recycling

Reusing old segment files instead of continually creating and deleting files. A recycled segment still occupies space managed inside pg_wal, and is not proof that its old contents are still available for replication.

### 5.5. One Segment May Be Needed for Multiple Purposes

A WAL segment is removed or recycled only when no internal requirement holds it, such as:

- Checkpoints/recovery.
- wal_keep_size.
- Replication slots.
- Pending/failed archiving.

Therefore, a single retention setting cannot replace monitoring all consumers.

## 6. Key WAL Parameters

| Parameter | Role | Key Reminder |
| --- | --- | --- |
| wal_level | Level of detail logged in WAL | Changing requires server restart |
| wal_keep_size | Minimum WAL kept in pg_wal for standbys | Not a maximum limit |
| max_slot_wal_keep_size | Caps WAL retained by replication slots | Can invalidate slots if exceeded |
| max_wal_size | Soft target for WAL/checkpoints | Not a hard cap on pg_wal |
| min_wal_size | Minimum WAL PostgreSQL tries to recycle/keep | Not a standby retention window |
| archive_mode | Enables WAL archiving | Requires suitable wal_level and restart |
| archive_command | Command to archive each segment | Must return success only when archive is durable |
| archive_timeout | Forces WAL segment switch after interval if WAL activity exists | Can increase archive volume |
| max_wal_senders | Number of sender processes for replication connections | Must cover standbys and replication clients |
| max_replication_slots | Maximum replication slots | Counts both physical and logical slots |
| checkpoint_timeout | Maximum time between checkpoints | Affects checkpoint/WAL behavior, not slot retention |
| synchronous_standby_names | Selects synchronous standbys | Controls commit acknowledgement, not wal_level |

Settings have version-specific contexts and limits. Inspect them on the server:

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
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'max_wal_size',
    'min_wal_size',
    'archive_mode',
    'archive_timeout',
    'max_wal_senders',
    'max_replication_slots',
    'checkpoint_timeout',
    'synchronous_standby_names'
)
ORDER BY name;
```

## 7. wal_keep_size: Keeping a Minimum Amount of WAL for Standbys

wal_keep_size tells PostgreSQL to retain at least a minimum volume of WAL in pg_wal to give standbys a better chance of catching up after lag or disconnections.

Example:

```conf
wal_keep_size = 2GB
```

### 7.1. This Is Not a Time Duration

2GB does not mean keeping WAL for two hours. The time span depends on the WAL generation rate.

If the system generates 10 MB/s, 2 GB covers only a few minutes. If the system generates 100 KB/s, the same size covers a much longer window.

### 7.2. This Is Not a Hard Cap

wal_keep_size is an extra minimum cushion for standbys; it does not cap total pg_wal size at that number. Checkpoints, archive backlogs, replication slots, and workloads can push pg_wal higher.

### 7.3. Without Slots, WAL Can Still Be Lost

If a standby stays disconnected longer than the kept WAL covers and needed segments get recycled, the standby cannot resume streaming from its old LSN via wal_keep_size alone. It must fetch missing segments from the WAL archive or be rebuilt from a base backup.

### 7.4. Older Versions

Older PostgreSQL versions used wal_keep_segments to specify a minimum segment count. Starting in PostgreSQL 13, wal_keep_size replaced segment-count configuration. Consult documentation for your exact major version when managing older clusters.

## 8. Replication Slots: Retaining WAL per Consumer Progress

A replication slot is a mechanism whereby PostgreSQL tracks a consumer's progress and prevents needed WAL from being removed before the consumer confirms receipt or consumption.

Two common types:

- **Physical replication slot:** for physical standbys.
- **Logical replication slot:** for logical decoding, subscribers, and CDC.

### 8.1. Why Are Slots Useful?

If a standby disconnects for several hours, a slot retains WAL starting from the position the standby still needs. When it reconnects, the standby can resume if WAL remains intact and other conditions hold.

You do not have to guess a static wal_keep_size for every outage; the slot tracks each specific consumer's position.

### 8.2. Creating a Physical Slot

Example creating a slot on the primary:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a_slot');
```

Slot names must be unique cluster-wide. The physical standby is configured to use that slot via primary_slot_name.

### 8.3. Creating a Logical Slot

Example:

```sql
SELECT *
FROM pg_create_logical_replication_slot(
    'cdc_customers_slot',
    'pgoutput'
);
```

A logical decoding slot requires an appropriate output plugin. Native PostgreSQL logical replication usually manages slots when creating subscriptions; do not manually create a slot with the same name and then let CREATE SUBSCRIPTION try to create it as well.

### 8.4. A Slot Is Not a Backup

A slot only retains WAL needed by a consumer. It does not hold a full copy of tables, schemas, roles, or databases. Full database recovery still requires base backups and WAL archives aligned with recovery goals.

## 9. Biggest Risk of Replication Slots: WAL Filling the Disk

If a consumer stops running, its slot can keep WAL pinned in pg_wal:

```text
Consumer stops reading WAL
        |
        v
restart_lsn stops advancing
        |
        v
Primary keeps generating new WAL
        |
        v
Old WAL remains pinned by slot
        |
        v
pg_wal grows in size
        |
        v
Filesystem can fill up
```

### 9.1. Inactive Slots Still Retain WAL

active=false does not mean the slot is harmless. An inactive slot can still hold a huge volume of WAL because its consumer has not acknowledged further progress.

### 9.2. Multiple Slots

Each slot can pin its own WAL position. Overall, the oldest WAL needed by any slot can block PostgreSQL from recycling segments. One forgotten slot can pin WAL even when every other standby is caught up.

### 9.3. A Slot Can Outlive Its Consumer

If a CDC pipeline is decommissioned while its logical slot remains behind, the primary may retain WAL indefinitely under the default unlimited setting. You need a lifecycle process for slots.

### 9.4. Never Drop a Slot to Free Disk Without Checking

Dropping a slot allows PostgreSQL to discard WAL a consumer still needs. If the consumer is still active or intended to resume, it may lose resumability and require recreation or re-snapshotting.

## 10. max_slot_wal_keep_size: Bounding WAL Retained by Slots

max_slot_wal_keep_size limits how much WAL replication slots are allowed to retain. A common default is -1, meaning unlimited.

Example:

```conf
max_slot_wal_keep_size = 20GB
```

### 10.1. Why Is a Cap Needed?

The cap protects the primary from an inactive consumer dragging pg_wal growth without bound.

### 10.2. Trade-Off: Slots Can Be Invalidated

If a slot needs older WAL while retained WAL exceeds the cap, PostgreSQL can remove required WAL during a checkpoint. The slot can lose its ability to resume from the old position; the standby or logical consumer must be recovered appropriately, potentially via recreation or reinitialization.

The cap does not "hold up to the max and then make the consumer catch up." It is a trade-off between disk protection and resumability.

### 10.3. The Limit Is Enforced at Checkpoints

Removing WAL to enforce the slot limit ties into checkpoints. Do not treat the configured number as a byte-exact real-time hard wall; monitor pg_replication_slots, disk usage, and logs.

### 10.4. Choose the Limit Based on Outage Budget

If a CDC consumer must survive 6 hours offline, measure peak WAL generation over 6 hours and add headroom. Do not pick 20 GB just because it sounds big.

### 10.5. Version Compatibility

max_slot_wal_keep_size exists in modern PostgreSQL versions (PostgreSQL 13 and later). Verify SHOW max_slot_wal_keep_size and major version docs before using it in automation.

## 11. max_wal_size Is Not a Retention Cap

This is a common misconception.

max_wal_size is a **soft target** related to triggering checkpoints. It does not impose an absolute limit on total WAL size inside pg_wal.

Example:

```conf
max_wal_size = 8GB
min_wal_size = 1GB
```

pg_wal can still grow well past 8 GB when:

- Replication slots pin old WAL.
- Archive commands fail and WAL remains unarchived.
- wal_keep_size requires extra WAL.
- WAL generation spikes sharply.
- Checkpoints have not yet been able to discard needed segments.

### 11.1. max_wal_size Affects Checkpoints

When WAL approaches the level prompting a checkpoint per max_wal_size, checkpoints can be scheduled earlier. It is one way to control checkpoint frequency and I/O behavior.

### 11.2. min_wal_size

min_wal_size governs how much WAL PostgreSQL tries to keep/recycle for reuse. It does not guarantee a standby can resume from any LSN within that span.

### 11.3. Checkpoints Are Not Allowed to Delete Still-Needed WAL

Checkpoints advance the state needed for crash recovery. Yet archive backlogs, replication slots, and wal_keep_size can still retain WAL past the checkpoint boundary.

### 11.4. When Disk Fills Up, Do Not Just Lower max_wal_size

If the cause is an inactive slot or archive failure, lowering max_wal_size will not release WAL pinned by the consumer. Identify the retention owner first.

## 12. WAL Archiving

WAL archiving copies completed WAL segments from pg_wal to an external archive. It is typically used for:

- Point-in-time recovery (PITR).
- Recovering standbys that need older WAL.
- Long-term backups paired with base backups.
- Disaster recovery.

### 12.1. Enabling Archive Mode

Example:

```conf
wal_level = replica
archive_mode = on
archive_command = '...'
```

archive_mode requires a server restart to take effect. Archiving requires an appropriate wal_level; minimal cannot be used for WAL archiving.

### 12.2. archive_command

archive_command is invoked with two placeholders:

- %p: path to the source WAL segment file on the server.
- %f: filename of the WAL segment.

Illustrative configuration invoking an archive helper script:

```conf
archive_command = '/usr/local/bin/archive_wal.sh "%p" "%f"'
```

This script path is an example only. You must implement and test the actual script on the database host.

### 12.3. Conditions for Returning a Success Exit Code

The archive command must return success only after the segment is durably stored at the destination and retrievable. If copying fails, the command must return a non-zero error code so PostgreSQL retries.

Never return exit code 0 merely because a background upload was kicked off before completing.

### 12.4. Archive Command Must Handle Retries Idempotently

PostgreSQL may invoke the archive command again for the same segment after a prior failure or uncertain outcome. The script must handle an already-existing destination file:

- If the destination file has identical contents, treat as success.
- If the destination file has different contents, return an error and investigate.
- Never silently overwrite a different WAL segment simply because filenames match.

### 12.5. Archive Destination Must Be Independent of pg_wal

If the archive directory sits on the same filesystem filling up from pg_wal, archiving may not relieve disk risk. Use separate volumes/storage and monitor capacity.

### 12.6. Protecting Archives

WAL can contain sensitive data at the storage level. Enforce read access controls, encryption in transit/at rest, archive backups, integrity checks, and retention policies.

## 13. archive_timeout and Segment Switching

PostgreSQL typically archives a WAL segment once the segment fills or switches. On very low-write workloads, the current segment might stay partially filled for a long time.

archive_timeout forces PostgreSQL to switch segments after a configured interval whenever eligible WAL activity has occurred.

Example:

```conf
archive_timeout = 300s
```

### 13.1. Why Use archive_timeout?

It reduces how long recent WAL waits before entering the archive, helping RPO on low-write workloads.

### 13.2. Trade-Off: Archive Volume Can Grow

Segments switched early are still archived as full-sized segment files. On sparse workloads, many segments are archived despite carrying minimal useful WAL.

### 13.3. Do Not Equate archive_timeout with RPO

archive_timeout=5min does not guarantee backups can recover every transaction within 5 minutes. You must factor in archive command duration, network/storage availability, WAL flushing, and backup procedures.

### 13.4. Do Not Arbitrarily Set archive_timeout Extremely Low

Very low values generate large numbers of archive files and increase metadata, network, and object-storage costs. Choose based on RPO and real throughput.

## 14. archive_mode: on vs. always

Common values:

- off: WAL archiving disabled.
- on: archives WAL segments generated by the server while running as a normal primary.
- always: also archives WAL received by the server in recovery/standby mode per that mode's rules.

always can help in standby architectures that need to archive received WAL, but archive destinations and ownership must be designed to prevent collisions or overwrites across nodes.

### 14.1. WAL Segment Filenames

A physical standby receives segments bearing the same filenames as those from the primary. If multiple nodes archive into the same namespace, ensure they belong to the same WAL history/cluster with proper distinction and verification.

### 14.2. Do Not Enable always Just to Feel "Safer"

Know clearly which node archives, which segments get stored, how the destination separates namespaces, and where restores will read from.

## 15. Archive Cleanup and Retention

WAL archives are usually kept longer than segments inside pg_wal, yet should not be kept blindly forever.

Archive retention must consider:

- Base backups still eligible for restore.
- Required PITR window.
- Standbys that might need to fetch WAL from the archive.
- Disaster recovery copies.
- Legal/compliance policies and storage costs.

### 15.1. Base Backups and WAL Must Go Together

For PITR, you need a valid base backup plus all continuous WAL from the backup's start/required point through the recovery target.

If WAL archives are purged too early, an older base backup can no longer recover to desired points in time.

### 15.2. pg_archivecleanup

PostgreSQL provides pg_archivecleanup to remove archived WAL older than a specified segment, commonly used in archive_cleanup_command for standby archive recovery.

Use this tool only with exact WAL history/segment boundaries and backup policies. Never run a generic cleanup command across an archive store holding multiple backup chains or clusters without knowing which segments are still needed.

### 15.3. Never Clean Up Based Only on the Current Standby

A caught-up standby does not prove older archive segments are no longer needed for PITR or base backups. Archive retention and streaming retention have separate lifecycles.

### 15.4. Object Storage Lifecycle

When using object storage, lifecycle policies might transition WAL to cheaper tiers or expire them after a period. Ensure recovery tools can still retrieve needed segments and objects have not been transitioned or deleted prematurely.

## 16. What Does Physical Streaming Replication Require?

Physical streaming replication sends WAL from primary to standby so the standby replays physical changes.

Key requirements:

- Primary running wal_level=replica or logical.
- Sufficient max_wal_senders.
- Appropriate replication role and network/TLS setup.
- Standby configured with primary_conninfo.
- Strategy for missing WAL: streaming, slots, and/or archiving.
- Compatible base backup.

### 16.1. Illustrative Primary Config

```conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
wal_keep_size = 2GB
```

These numbers are illustrative only. Size based on actual standbys, backup clients, and replication connections.

### 16.2. Standbys Need a Base Backup

A new standby is typically initialized from a base backup of the primary or a compatible standby. Streaming WAL contains only subsequent changes; it does not send the entire historical dataset to an empty server.

### 16.3. Streaming Replication Does Not Mean Synchronous

Physical streaming can be asynchronous or synchronous. That behavior is controlled by synchronous_standby_names and synchronous_commit, not by wal_level alone.

### 16.4. Standbys Receive WAL by LSN

The primary ships WAL from the needed position; the standby writes, flushes, and replays it. Those three positions can differ at any point in time.

## 17. Physical Replication Without Slots

Streaming replication works even without slots.

### 17.1. Mechanism

The standby reconnects and requests WAL from the required LSN. The primary keeps WAL per general limits such as wal_keep_size; if a segment was already recycled, the standby can fetch WAL from the archive if restore_command is configured.

### 17.2. Advantages

- No inactive slots pinning WAL indefinitely.
- Simpler management for standbys with expected brief outages.

### 17.3. Risks

- If a standby stays offline longer than retained WAL covers and the archive lacks needed segments, the standby cannot resume streaming.
- The standby may need rebuilding from a fresh base backup.

### 17.4. When Is It Appropriate?

When a reliable archive exists and rebuilding a standby after a long outage is acceptable, or when you want to avoid unbounded slot WAL retention.

## 18. Physical Replication Using Slots

Slots inform the primary where a standby still needs WAL from.

### 18.1. Standby Config

Example in the standby's postgresql.conf:

```conf
primary_conninfo = 'host=primary.example.internal port=5432 user=replicator application_name=standby_a'
primary_slot_name = 'standby_a_slot'
```

Manage credentials and TLS properly; never commit plaintext passwords into tracked files.

### 18.2. Creating the Slot

On primary:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a_slot');
```

### 18.3. Benefits

WAL needed by the standby is retained even across standby disconnections, within resource and slot-policy limits.

### 18.4. Costs

If the standby stops for a long period, the slot retains WAL and can grow pg_wal until the filesystem fills up unless capped and alerted.

### 18.5. Combining Slots and Archiving

Slots protect streaming continuity while WAL remains on the primary; archiving provides an independent path to older WAL outside pg_wal. Both may be needed in a robust DR design.

## 19. Cascading Physical Replication

In cascading replication, one standby forwards WAL to downstream standbys.

```text
Primary
  |
  +---- Standby A
           |
           +---- Standby B
           |
           +---- Standby C
```

### 19.1. Benefits

- Reduces direct replication connections to the primary.
- Supports placing replicas across regions or network tiers.
- Distributes WAL sender load.

### 19.2. Retention Still Matters

Standby A must retain WAL needed by B and C or have an archive/recovery path. A lagging cascading standby can delay downstream standbys.

### 19.3. Upstream and Downstream Slots

Each tier may need matching slots. Monitor slots on the node actually retaining WAL, not just on the primary.

### 19.4. archive_mode=always

In some cascading or standby-archiving designs, archive_mode=always may be needed to archive WAL received during recovery. Define each node's role and archive namespace clearly before enabling it.

## 20. Synchronous Replication and wal_level

Synchronous replication requires the primary to wait for one or more standbys to confirm WAL at the chosen level before reporting commit success.

Example:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

This is illustrative configuration only; understand syntax, node names, and your cluster's failover policy.

### 20.1. wal_level Does Not Decide Sync vs. Async

wal_level=replica supplies the WAL info needed for physical replication. Whether commits wait for a standby is a separate decision.

### 20.2. synchronous_commit

Different levels can wait for local WAL flush, remote write, remote flush, or remote apply per version semantics. remote_apply waits for the standby to replay WAL before commit returns.

### 20.3. Trade-Offs

- Synchronous mode can lower RPO for confirmed commits per configuration.
- It can increase commit latency and tie availability to standby responsiveness.
- Poor design can block all write traffic if synchronous standbys disconnect.

### 20.4. Retention Does Not Replace Commit Acknowledgement

Retaining WAL longer does not mean a standby has acknowledged a transaction. Retention ensures WAL remains available to ship/replay; synchronous commit determines when the primary confirms commits.

## 21. WAL Archiving and Point-in-Time Recovery

PITR allows restoring a database from a base backup and replaying WAL to a target timestamp or LSN.

### 21.1. Illustrative Primary Config

```conf
wal_level = replica
archive_mode = on
archive_timeout = 300s
archive_command = '/usr/local/bin/archive_wal.sh "%p" "%f"'
```

### 21.2. High-Level Workflow

1. Create a consistent base backup.
2. Archive WAL continuously covering and following the backup's required point.
3. Ensure the archive command never drops segments.
4. On restore, set restore_command to fetch WAL from the archive.
5. Set recovery target time/LSN/transaction if needed.
6. Test recovery regularly.

### 21.3. restore_command

In recovery config, restore_command fetches required WAL segments from the archive to the path PostgreSQL requests. The command must return proper exit codes depending on whether the file exists and handle retries cleanly.

### 21.4. Archive Completeness

A base backup is useful up to a recovery target only if all required WAL exists. Keeping just the most recent few WAL files does not enable PITR.

### 21.5. Backups and Replication Serve Different Goals

- Replication keeps standbys up to date with the primary.
- Backups restore service when both primary and replicas lose data or when reverting to a time before a mistake.
- WAL archiving is one component of PITR.

Never treat a live standby as an independent backup; an accidental DELETE replicates straight to the standby.

## 22. Logical Replication and CDC Require wal_level=logical

Logical replication transfers row changes in a logical representation instead of copying the entire physical storage layout.

```text
Primary
  wal_level = logical
  publication
  logical replication slot
       |
       v
Logical decoding / pgoutput
       |
       v
Subscriber or CDC consumer
       |
       v
Target database / Kafka / data platform
```

### 22.1. Publications and Subscriptions

Native PostgreSQL logical replication uses a publication on the publisher and a subscription on the subscriber. When creating a subscription with copy_data, PostgreSQL can perform initial table synchronization and then stream ongoing changes.

### 22.2. Related Configuration

The publisher typically needs:

```conf
wal_level = logical
max_replication_slots = 10
max_wal_senders = 10
```

Slot and sender counts must cover native subscriptions, table sync workers, and external CDC consumers.

### 22.3. Replica Identity

For logical replication to identify which row to UPDATE or DELETE on the subscriber, tables need an appropriate replica identity. A primary key is usually best:

```sql
ALTER TABLE app.customers
REPLICA IDENTITY DEFAULT;
```

Without a suitable primary key, consider a qualifying unique index or REPLICA IDENTITY FULL:

```sql
ALTER TABLE app.customers
REPLICA IDENTITY FULL;
```

FULL can increase data sent/read and row-lookup cost on the subscriber. Use it only when needed.

### 22.4. Logical Replication Does Not Automatically Sync Everything

Native logical replication focuses on table data changes. Never assume it replicates all DDL, roles, grants, sequence states, or every database object type. Those require separate deployment/migration processes or extra tooling.

### 22.5. Logical Replication Does Not Fully Replace Physical HA

A logical subscriber maintains its own schemas, objects, and logically mapped data. It is not a byte-for-byte physical standby capable of substituting for the primary via physical failover.

## 23. Logical Replication Slots and LSNs

A logical slot retains WAL until the decoder/consumer confirms consumption.

Key columns in pg_replication_slots:

- restart_lsn: earliest WAL position the slot might still need.
- confirmed_flush_lsn: position the consumer has acknowledged via the logical replication protocol.
- active: whether a consumer is currently attached to the slot.
- catalog_xmin: xmin related to catalog rows still needed by logical decoding.
- wal_status: WAL availability status on versions providing this column.

### 23.1. restart_lsn and confirmed_flush_lsn Differ

confirmed_flush_lsn usually shows how far the consumer has acknowledged. However, restart_lsn can be earlier because PostgreSQL still needs preceding WAL for decoding, reordering, and catalog state.

Therefore, never look only at confirmed_flush_lsn and conclude a slot is not retaining WAL.

### 23.2. Inactive Logical Slots

If a consumer stops running, active=false; the slot can still pin WAL and catalog history. A CDC connector deleted from orchestration while its slot remains on the primary can silently fill the disk.

### 23.3. Logical Decoding and Catalog Retention

Logical slots can pin catalog tuples via catalog_xmin. This can prevent vacuum from reclaiming old catalog rows as usual. Monitor long-lived slots and manage their lifecycle.

### 23.4. Multiple Consumers

Each consumer needs its own slot if independent progress is required. The slowest slot pins WAL the longest.

## 24. Logical Replication and WAL Volume

wal_level=logical writes extra info for logical decoding. Space impact depends on workload, schema, replica identity, full-page images, change types, and active features.

### 24.1. No Fixed Multiplier

Never claim "logical always adds exactly 20% more WAL." Measure pg_stat_wal, archive volume, slot retention, and real workloads on staging.

### 24.2. REPLICA IDENTITY FULL

For UPDATE/DELETE, FULL can require logging much more row data to identify old rows. It can raise WAL, decoding, network, and apply costs compared to primary-key identity.

### 24.3. Tables Without Primary Keys

This is a schema and replication design issue to resolve directly. Do not turn on FULL for every table without measuring.

### 24.4. Logical Replication Slots Can Retain WAL Long-Term

Even with normal WAL generation, consumer lag can grow pg_wal. Budget retention separately for each consumer type.

## 25. Replication Types and Their WAL Requirements

| Need | Minimum wal_level | WAL Retention/Read Mechanism | Key Considerations |
| --- | --- | --- | --- |
| Crash recovery on primary | minimal | Internal WAL up to checkpoint/recovery | Does not support archiving or replication |
| PITR with base backup + archive | replica | Continuous WAL archive | Archive must be complete to recovery target |
| Physical streaming standby | replica | Streaming + wal_keep_size/slot/archive | Standby needs base backup and WAL continuity |
| Cascading physical standby | replica | Upstream streaming/slot/archive | Every tier must hold enough WAL for downstream |
| Synchronous physical replication | replica | Streaming and sync acknowledgement | Sync settings are separate from wal_level |
| Native logical replication | logical | Logical slot and WAL sender | Publications, replica identity, slot lifecycle |
| CDC via logical decoding | logical | Logical slot/output plugin | Consumer acks, restart_lsn, and retention |
| Archiving on standby receiving WAL | Per physical needs, usually replica | archive_mode=always in suitable design | Namespace/history and archive ownership |

### 25.1. One Primary Can Serve Multiple Consumer Types

For example, a system can run physical standbys for HA alongside logical CDC pushing events to analytics. The primary needs wal_level=logical because that is the highest level required among its consumers.

### 25.2. Size Capacity for the Slowest Consumer

Physical standby A may be completely caught up while logical CDC B is stalled. WAL remains pinned by B's slot. Never monitor only HA standbys.

### 25.3. Each Consumer Has a Different SLA

An HA standby may need to resume within minutes; a CDC pipeline may need to replay after hours; a PITR archive may need weeks of retention. Do not force all of them into a single retention figure.

## 26. Combining Archiving, Slots, and wal_keep_size

These three mechanisms protect different things:

| Mechanism | What Does It Protect? | Limits / Risks |
| --- | --- | --- |
| wal_keep_size | Keeps a minimum WAL cushion in pg_wal | Does not guarantee coverage for long outages |
| Replication slot | Retains WAL per consumer progress | Inactive slots can fill disk; caps can invalidate slots |
| WAL archive | Copies segments to storage outside pg_wal | Requires archive completeness, restore path, and retention policy |

### 26.1. Combined Design

A production primary can:

- Use physical slots for critical standbys.
- Use logical slots for CDC consumers.
- Enable WAL archiving for PITR and recovery.
- Set wal_keep_size as a reconnect buffer for standbys.
- Set max_slot_wal_keep_size to bound disk exhaustion risk.
- Alert before any limit is breached.

### 26.2. No Single Parameter Replaces All Others

Raising wal_keep_size does not fix a broken archive command. Enabling archiving does not stop a slot from pinning WAL in pg_wal. Lowering max_wal_size does not keep the disk from filling up.

## 27. Estimating WAL Retention Capacity

A starting formula:

```text
WAL to retain (bytes)
  ≈ Peak WAL generation rate (bytes/second)
    × Consumer outage budget (seconds)
    + Safety headroom
```

### 27.1. Example

Suppose:

- Peak WAL generation: 20 MB/s.
- Consumer outage budget: 6 hours.

Calculation:

```text
20 MB/s × 6 × 60 × 60
= 432,000 MB
≈ 432 GB (decimal)
```

This excludes headroom for spikes, archive backlogs, segment/checkpoint behavior, and other consumers. If you need to survive a 6-hour outage at peak rate, 20 GB is nowhere near enough.

### 27.2. Use Peak or High Percentiles

Average WAL rates may look modest while batch loads, index rebuilds, or month-end runs create huge spikes. Sizing from averages alone runs out of space right when you need it most.

### 27.3. Size Archives Separately

Archive retention is typically sized in days or weeks for PITR and base backup chains. Archive capacity depends on total WAL generated across that window, not just standby outages.

### 27.4. One Segment Shared Across Multiple Slots

WAL is not duplicated per slot inside pg_wal; the oldest WAL position still needed by any consumer dictates which segments are retained. Still, more slots raise the odds that one slow consumer stretches retention.

### 27.5. Headroom

Never run close to 100% filesystem utilization. Leave headroom for bursts, archive retries, checkpoints, temporary files, backups, and operational response time.

## 28. Configuring a Primary for Physical Replication

Illustrative configuration example:

```conf
# WAL information for physical standby and PITR
wal_level = replica

# Replication connections and slots
max_wal_senders = 10
max_replication_slots = 10

# Extra local WAL cushion for standbys without a slot
wal_keep_size = 2GB

# Protect against unlimited retention by an abandoned slot
max_slot_wal_keep_size = 20GB

# Continuous WAL archive for recovery
archive_mode = on
archive_timeout = 300s
archive_command = '/usr/local/bin/archive_wal.sh "%p" "%f"'

# Checkpoint sizing (not a retention cap)
max_wal_size = 8GB
min_wal_size = 1GB
```

These numbers are not universal recommendations. Calculate them from peak WAL rate, standby count, outage budgets, archive throughput, disk space, and backup policy.

### 28.1. Replication Role

Create a role with replication privileges following least privilege:

```sql
CREATE ROLE replicator
WITH LOGIN REPLICATION PASSWORD 'use-a-secret-manager';
```

The password above is illustrative only; production must use a secrets manager and proper authentication policy. Restrict source access in pg_hba.conf and enforce TLS where appropriate.

### 28.2. Verify Config

```sql
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
SHOW wal_keep_size;
SHOW max_slot_wal_keep_size;
SHOW archive_mode;
SHOW archive_timeout;
```

### 28.3. Changes Requiring a Restart

wal_level, archive_mode, max_wal_senders, and max_replication_slots require a PostgreSQL restart to take effect. Several other settings such as retention, checkpoints, and archive commands can reload depending on version context. Check pg_settings.context and pending_restart instead of guessing.

## 29. Configuring Logical Replication

If the same primary serves both physical standbys and logical CDC:

```conf
wal_level = logical
max_wal_senders = 20
max_replication_slots = 20

wal_keep_size = 2GB
max_slot_wal_keep_size = 40GB

archive_mode = on
archive_command = '/usr/local/bin/archive_wal.sh "%p" "%f"'
```

Increase sender and slot limits to cover all physical standbys, logical subscriptions, table sync workers, and CDC clients.

### 29.1. Creating a Publication

```sql
CREATE PUBLICATION customer_changes
FOR TABLE app.customers, app.customer_addresses;
```

### 29.2. Creating a Subscription

```sql
CREATE SUBSCRIPTION customer_changes_sub
CONNECTION 'host=publisher.example.internal dbname=app user=logical_reader'
PUBLICATION customer_changes;
```

This example assumes the subscriber has matching tables, authenticated connectivity, and proper role privileges. Plan initial data copy, ownership, and DDL separately.

### 29.3. Inspecting Created Slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

### 29.4. Be Careful with Multiple Consumers

A single logical slot should never be shared arbitrarily between two independent consumers because they would contend over progress and acknowledgement semantics. Each pipeline needs clear ownership and lifecycle.

## 30. Monitoring Physical Replication on the Primary

The pg_stat_replication view shows WAL senders connected to standbys.

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

### 30.1. The LSNs

- sent_lsn: WAL sent to the standby.
- write_lsn: WAL position the standby reports writing.
- flush_lsn: WAL position the standby reports durably flushing.
- replay_lsn: WAL position the standby has replayed.

Gaps between these LSNs pinpoint whether lag sits in the network, write/flush, or replay.

### 30.2. Lag in Bytes

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS bytes_not_written,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS bytes_not_flushed,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS bytes_not_replayed
FROM pg_stat_replication;
```

Subtractions must handle NULLs when a standby lacks a position yet. This is a point-in-time LSN byte gap, not directly time lag.

### 30.3. Lag Time Columns

write_lag, flush_lag, and replay_lag are timing statistics from recent writes/flushes/replays, not always an accurate measure of how long a consumer has been offline. Combine LSN deltas and timestamps.

## 31. Monitoring Replication on the Standby

On the standby:

```sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_wal_receiver;
```

This view returns no rows when the standby has no active WAL receiver.

### 31.1. Replay Location

```sql
SELECT
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit;
```

These functions apply to standbys; older versions may use xlog function names.

### 31.2. Do Not Rely Solely on Last Timestamp

If the primary sees few writes, the last replay timestamp may appear old even when the standby is completely caught up. Use LSN gaps and WAL activity to interpret accurately.

### 31.3. Hot Standby Feedback

hot_standby_feedback can reduce query-cleanup conflicts on the primary for queries running on the standby, yet can retain dead tuples on the primary and increase bloat. It does not directly retain WAL; it affects row-version retention and vacuum.

## 32. Monitoring Replication Slots

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_type, slot_name;
```

Columns like wal_status and safe_wal_size exist only on newer supported versions. If a query fails on an older major version, inspect the view schema and remove unsupported columns.

### 32.1. Estimating WAL Bytes Retained by Slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS retained_wal_estimate
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(), restart_lsn
) DESC;
```

This estimates the distance from current WAL to restart_lsn, not an exact exclusive byte ownership per slot. Some WAL segments may be shared across multiple consumers, checkpoints, and archiving.

### 32.2. Finding Long-Inactive Slots

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE NOT active
ORDER BY restart_lsn NULLS FIRST;
```

Never drop inactive slots automatically. Verify the owner and consumer first.

### 32.3. Invalidated Slots

On versions with wal_status, status indicates whether the slot still has required WAL or has lost segments. Check safe_wal_size, server logs, and consumer health; do not infer solely from active.

## 33. Monitoring the WAL Archive

pg_stat_archiver provides archive statistics:

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

### 33.1. failed_count Increasing

Possible causes include unreachable archive destination, expired credentials/permissions, full storage, network/object-storage timeouts, archive script returning wrong exit codes, or destination file collisions/checksum mismatches.

### 33.2. archived_count Not Increasing

This does not always indicate an error: if the workload has not filled or switched a WAL segment, the archiver may have nothing to archive yet. Cross-check WAL activity and archive_timeout.

### 33.3. Archive Backlog

Monitor how many WAL files in pg_wal are waiting to be archived, disk usage, and time since the last successful archive. A slow archive command can build up a growing WAL backlog.

## 34. Measuring pg_wal Disk Usage

PostgreSQL provides pg_ls_waldir():

```sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)) AS wal_directory_size
FROM pg_ls_waldir();
```

This function requires appropriate server privileges. It reports the size of files inside the WAL directory at query time.

### 34.1. Do Not Treat File Count as Pure Retained WAL

The directory can contain recycled segments or other WAL-management files. Combine with slots, archive status, checkpoints, and filesystem metrics.

### 34.2. Monitor the Filesystem

pg_ls_waldir() does not replace df or volume metrics. If pg_wal sits behind a symlink or on a separate mount, monitor the exact filesystem hosting it.

### 34.3. Alert on Capacity and Growth Rate

Alert when filesystem usage crosses capacity thresholds, WAL directory grows steadily, inactive slots retain WAL past budget, archive failures persist, or replica lag exceeds outage budgets.

## 35. Monitoring WAL Generation Rate

On versions with pg_stat_wal:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
```

### 35.1. Compute Rate from Two Samples

```text
rate_bytes_per_second
  = (wal_bytes_sample_2 - wal_bytes_sample_1)
    / elapsed_seconds
```

If the server restarted or statistics reset between samples, the delta can be negative or invalid. Always check stats_reset.

### 35.2. Peak Rate

Store time series at fine intervals such as 1 minute or 5 minutes, and calculate high percentiles and daily/weekly peaks. Never size solely from a monthly average.

### 35.3. WAL Generation vs. Archive Throughput

If generation hits 50 MB/s while archiving processes only 20 MB/s, a backlog grows at roughly 30 MB/s during that burst. If sustained, pg_wal can exhaust disk while unarchived segments wait.

## 36. What Should a Monitoring Dashboard Show?

| Category | Metrics |
| --- | --- |
| WAL production | WAL bytes/s, records/s, full-page images |
| Local storage | pg_wal bytes, filesystem free space, growth rate |
| Checkpoints | Checkpoint frequency/duration and write pressure |
| Archiving | archived_count, failed_count, last success age, backlog |
| Physical replication | sent/write/flush/replay LSNs, byte lag, time lag |
| Slots | active, restart_lsn, confirmed_flush_lsn, retained estimate, safe_wal_size |
| Standby | receive/replay positions, receiver state, recovery conflicts |
| DR | archive completeness, last successful base backup, restore test age |
| Logical CDC | consumer lag, slot age, apply rate, last acknowledged LSN |

### 36.1. Alerts Must Reflect Budgets

If operations allow a standby at most 30 minutes offline, alerting at 10 minutes of lag makes sense. If a CDC pipeline allows 12 hours of delay, use a different threshold.

### 36.2. Alert Well Before Disk Full

Do not wait for 95–100% filesystem usage before acting. Alert on WAL growth rate and estimated time until disk exhaustion.

### 36.3. Correlate Metrics

pg_wal growth can come from slots, archive failures, wal_keep_size, or workload bursts. Place these metrics side by side on dashboards to pinpoint the retention owner immediately.

## 37. Scenario: Physical Standby Offline for Extended Time

Suppose a standby uses a physical slot, loses connectivity for 4 hours, and the primary keeps taking writes.

### 37.1. If the Slot Is Uncapped

The primary retains WAL needed by the standby. Resumability is high, yet disk usage grows at the WAL generation rate over all 4 hours and keeps climbing if the standby does not return.

### 37.2. If max_slot_wal_keep_size Caps It

Once retained WAL exceeds the cap, PostgreSQL can discard old segments at checkpoints and invalidate the slot. When the standby returns, it may require reinitialization.

### 37.3. If No Slot Is Used

The standby relies on segments still in wal_keep_size or the WAL archive. If neither has the needed segments, a fresh base backup is required.

### 37.4. Decision

Size retention to your outage budget, configure a cap to protect the primary, and maintain a runbook to rebuild standbys. Never leave unlimited slots without disk alerts.

## 38. Scenario: Logical CDC Consumer Stalled

A CDC consumer can stall due to downstream Kafka/topic unavailability, expired credentials, connector crashes, unhandled schema changes, or failing to commit/acknowledge LSNs.

### 38.1. Impact

The logical slot pins WAL from restart_lsn and can also retain catalog history. The primary keeps generating WAL; disk fills even when database traffic looks normal.

### 38.2. Diagnosis

1. Identify slot owner and connector.
2. Check active state.
3. Compare restart_lsn and confirmed_flush_lsn.
4. Estimate retained WAL.
5. Check consumer logs and last acknowledged position.
6. Verify downstream can resume.

### 38.3. Recovery

Restart the consumer if WAL is still available. If the slot was invalidated or lost WAL, you may need to create a new slot and re-bootstrap/re-snapshot per your CDC tool's capabilities.

### 38.4. Never Drop a Slot Before Deciding on Re-Snapshotting

Dropping a slot releases WAL retention, but the consumer loses its tracked position. Record LSNs, schema state, snapshot requirements, and downstream recovery plans first.

## 39. Scenario: Archive Command Failing

If archive_command returns errors, PostgreSQL retries archiving that segment. Unarchived WAL cannot be recycled normally.

### 39.1. Symptoms

- pg_stat_archiver.failed_count increases.
- Recent last_failed_time.
- pg_wal grows.
- Logs report archive command failures.
- Filesystem free space drops.

### 39.2. Actions

1. Check archive destination, network, and credentials.
2. Check script exit codes and logs.
3. Verify unarchived segments are still intact.
4. Restore storage or network access.
5. Let PostgreSQL retry automatically via its archive loop.
6. Monitor backlog shrinking and disk stabilizing.

### 39.3. Never Delete Unarchived Segments

Deleting files to free space breaks the archive chain and compromises recovery. Fix the archive destination or expand storage instead of deleting PostgreSQL-managed WAL.

## 40. Scenario: pg_wal Nearly Full

```text
pg_wal growth
   |
   +--> inactive replication slot?
   |
   +--> archive failures/backlog?
   |
   +--> standby lag / missing consumer?
   |
   +--> wal_keep_size too large?
   |
   +--> workload WAL burst / checkpoint behavior?
```

### 40.1. Investigation Steps

1. Check filesystem free space and growth rate.
2. Query pg_replication_slots and retained estimates.
3. Query pg_stat_archiver.
4. Query pg_stat_replication.
5. Query pg_stat_wal if available.
6. Identify which segments are still pinned and why.

### 40.2. Remediation Options

- Restore the consumer or standby if it can still resume.
- Fix the archive destination if archiving is failing.
- Drop a slot only after the owner confirms the consumer is no longer needed.
- Adjust retention caps per policy with full awareness of slot invalidation risks.
- Expand disk capacity when needed.
- Throttle workload or bulk operations if WAL generation exceeds capacity.

### 40.3. Never Run rm Inside pg_wal

Never manually delete segments, rename files, or plant dummy files to trick PostgreSQL.

## 41. Changing wal_level on a Running Cluster

wal_level is a server-start setting. Editing postgresql.conf or running ALTER SYSTEM does not change the runtime value immediately; a PostgreSQL restart is required.

### 41.1. Check Value and Pending Restart State

```sql
SELECT
    name,
    setting,
    context,
    pending_restart,
    source,
    sourcefile,
    sourceline
FROM pg_settings
WHERE name = 'wal_level';
```

### 41.2. Upgrading replica to logical

Before restarting:

- Verify logical consumers and slot capacity.
- Estimate new WAL generation and retention.
- Raise sender and slot limits as needed.
- Plan restart/failover window.
- Verify archive and backup chains.
- Check PostgreSQL/CDC tool version compatibility.

After restarting, confirm SHOW wal_level returns logical, create publications/slots, and test the consumer.

### 41.3. Downgrading logical to replica

Never downgrade while logical subscriptions, slots, or CDC consumers still require logical decoding. Confirm consumers are stopped, downstream data is synced, slot lifecycles are closed out, and losing logical decoding on new WAL is acceptable.

### 41.4. Downgrading to minimal

Appropriate only when archiving, PITR, hot standby, physical replication, and logical decoding are all unnecessary. This is rarely appropriate for production databases with disaster recovery requirements.

### 41.5. Downgrading wal_level Is Not Retroactive

Once lowered, new WAL lacks logical decoding info. You cannot re-enable logical later and retroactively decode segments written under replica or minimal.

## 42. Failover and Replication Slots

During primary failover, replication slots require careful management.

### 42.1. Do Slots Exist on the Standby?

Physical standbys can be configured to synchronize slots using features available in supported versions; logical slot failover has specific requirements depending on PostgreSQL version and setup. Never assume all slots automatically appear on the new primary.

### 42.2. Failing Over Logical Consumers

CDC consumers must learn the new publisher, new slot or failover slot, and resume position. Otherwise, changes may be missed or duplicated.

### 42.3. Check Version Support

Features like synchronized logical failover slots evolve across major versions. Read the docs for your exact version rather than copying new-version configs onto an older cluster.

### 42.4. Failover Does Not Solve Archive Continuity

DR design must still preserve base backups and WAL archives. A new primary will not automatically hold the entire WAL history archived by the old primary unless storage architecture shares or replicates the archive.

## 43. archive_mode, archive_command, and Standbys

A standby in recovery can restore WAL from the archive via restore_command, or receive it via streaming. When configured with archive_mode=always, a standby can archive received WAL per that mode's semantics.

### 43.1. Distinguish Restore from Archive

- restore_command: pulls a segment from the archive for recovery/replay.
- archive_command: pushes a completed segment out to the archive.

These are two opposite data directions.

### 43.2. Archive Loops

Never configure archive_command to write segments back into the exact location restore_command reads from in a way that creates loops or conflicts. Keep namespaces and retention clean.

### 43.3. Shared Archives

If the primary and multiple standbys archive to a shared store, ensure they belong to the same WAL history and use idempotent writes. Never let independent clusters write identically named files into the same namespace.

## 44. synchronous_commit and Commit Durability

WAL retention is often confused with durability. They are distinct:

- synchronous_commit defines how long COMMIT waits for WAL durability before returning success.
- synchronous_standby_names defines which standbys are synchronous.
- wal_level defines what information is logged to WAL.
- Retention defines how long old WAL is kept for consumers and recovery.

Example:

```sql
SHOW synchronous_commit;
SHOW synchronous_standby_names;
```

### 44.1. Local Durability

The primary can flush WAL locally and confirm commit while an asynchronous standby has not yet replayed it. This creates a potential data-loss window if the primary dies and failover promotes an async standby that has not received/replayed the WAL.

### 44.2. Synchronous Durability

Waiting for standbys per policy reduces RPO for acknowledged commits, at the cost of latency and dependency on standby availability.

### 44.3. Archives Are Not Synchronous Standbys

Archive commands generally run after a segment switches; commits do not wait for archiving to finish. Never treat WAL archiving as synchronous replication.

## 45. Backups and PITR: Retention by Recovery Window

A backup policy might require:

- Daily base backups retained for 14 days.
- Continuous WAL archive enabling PITR to any time within 14 days.
- A monthly backup kept longer.

This is a sample policy only, not a universal rule.

### 45.1. Determining Which WAL to Keep

For each base backup, determine its start/stop LSN or backup tool metadata, the earliest WAL segment required for backup consistency, continuous WAL up to permitted recovery targets, and timeline history files whenever failover/promotion occurred.

### 45.2. Timelines

After promotion/failover, PostgreSQL switches to a new timeline. Recovery archives must preserve timeline history files and matching WAL segments; never match segment numbers blindly while ignoring timeline history.

### 45.3. Restore Tests

An untested backup is an assumption. Regularly restore into an isolated environment, replay WAL, and verify data and application behavior up to a recovery target.

### 45.4. Archive Retention

Delete archived WAL only when confident no retained base backup, standby, DR workflow, or PITR target requires it. Use a backup catalog or retention manager rather than ad-hoc file deletion commands.

## 46. Version-Specific Settings and Migration

Different PostgreSQL versions differ in:

- Retention parameter names (wal_keep_segments in older versions, wal_keep_size in newer ones).
- Columns in pg_replication_slots.
- Logical failover slot features.
- WAL and checkpoint statistics views.
- Archive library vs. archive_command support.
- Protocol and replication behavior details.

### 46.1. Inspect the Running Server

```sql
SELECT version();

SHOW wal_level;
SHOW wal_keep_size;
SHOW max_slot_wal_keep_size;
SHOW archive_mode;
```

If SHOW reports an unknown parameter, do not blindly add the setting; check your version and its documentation.

### 46.2. Inspect Parameter Context

```sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name LIKE '%wal%'
   OR name LIKE '%replication%'
   OR name LIKE '%archive%'
ORDER BY name;
```

### 46.3. Major Upgrades

During a major upgrade, check replication compatibility, slots, logical decoding plugins, archive tooling, and backup/restore workflows. Never assume existing slots migrate seamlessly to a new major cluster without special handling.

## 47. Securing WAL and Replication

WAL can contain sensitive data at the storage layer. Protect it by:

- Securing network replication links with private networks and TLS.
- Restricting pg_hba.conf strictly to required hosts and users.
- Granting replication roles least privilege.
- Enforcing encryption, access control, and auditing on archive storage.
- Limiting slot management to authorized operational roles.
- Never exposing replication protocol endpoints to public networks casually.
- Protecting backups and WAL archives with the same rigor as live database backups.

### 47.1. Replication Passwords

Never place real passwords in command lines, Git, documentation, or logs. Use .pgpass with restrictive permissions or a secrets manager / orchestration system.

### 47.2. Archive Scripts

Archive scripts execute on the PostgreSQL host under the service OS account. Never pass untrusted client input or arbitrary paths into archive commands.

### 47.3. CDC Data

Logical decoding exports row changes to external systems. Treat CDC consumers as data export channels with proper authorization, masking, and retention.

## 48. Runbook: Standby Cannot Resume Streaming

1. Record primary and standby LSNs and timelines.
2. Check PostgreSQL logs on both nodes for errors.
3. Identify which WAL segment the standby needs.
4. Inspect physical slots and restart_lsn.
5. Check wal_keep_size and current pg_wal contents.
6. Check whether the WAL archive holds the required segments and timeline history.
7. If WAL is available, restore connectivity, slot, or restore path and let the standby catch up.
8. If WAL is gone, plan rebuilding the standby from a fresh base backup.
9. Monitor replica lag and disk usage during catch-up.
10. Adjust outage budgets, retention, and alerts to prevent recurrence.

Never drop slots or delete WAL before confirming the recovery path.

## 49. Runbook: Logical Slot Retaining Too Much WAL

1. Identify slot name, database, owner, and CDC connector.
2. Inspect active state, restart_lsn, confirmed_flush_lsn, and catalog_xmin.
3. Estimate retained WAL bytes.
4. Inspect consumer logs and downstream availability.
5. Restart the consumer if required WAL still exists.
6. If the slot was invalidated, plan a snapshot/resnapshot or re-bootstrap.
7. Drop the slot only after confirming the consumer no longer needs that history.
8. Watch pg_wal shrink once the retention blocker clears.
9. Configure max_slot_wal_keep_size, alerts, and a slot owner inventory.

## 50. Runbook: Archive Backlog or Archive Failure

1. Inspect pg_stat_archiver and PostgreSQL logs.
2. Identify the failing archive command, host, or storage endpoint.
3. Check credentials, permissions, network, quotas, and disk space.
4. Check if destination segments already exist and verify checksums match.
5. Restore the archive destination.
6. Let PostgreSQL retry; never delete unarchived segments.
7. Watch failed_count stop rising, archived_count advance, and backlog shrink.
8. Verify archive completeness with backup/restore validation tools.
9. Adjust capacity and alerting.

## 51. Runbook: pg_wal Growing Rapidly

1. Check filesystem free space and growth rate.
2. Query pg_replication_slots for old restart_lsn or inactive slots.
3. Query pg_stat_replication for standby lag.
4. Query pg_stat_archiver for archive failures.
5. Query pg_stat_wal to measure generation rate.
6. Identify the retention owner and outage duration.
7. Recover the consumer or archive if feasible.
8. Expand storage or throttle load carefully if needed.
9. Drop slots only after a deliberate decision accepting consequences.
10. Never manually delete files inside pg_wal.

## 52. Runbook: Changing wal_level

1. Identify all new replication or CDC consumers to support.
2. Verify PostgreSQL version and feature support.
3. Audit existing slots, subscriptions, and standbys.
4. Estimate new WAL generation and retention needs.
5. Size max_wal_senders and max_replication_slots.
6. Verify disk, archive, and backup capacity.
7. Schedule a restart or failover maintenance window.
8. Update config and restart per HA procedures.
9. Confirm runtime SHOW wal_level.
10. Test physical standbys, logical consumers, and PITR/archiving as required.
11. Monitor WAL, slot lag, archiving, and application errors.

## 53. Common Anti-Patterns

| Anti-Pattern | Consequence | Proper Approach |
| --- | --- | --- |
| Using minimal on a primary needing standbys | Physical replication unsupported | Use replica or logical |
| Using minimal while expecting PITR | No usable WAL archive | Use wal_level=replica or higher |
| Assuming logical creates CDC on its own | No publications, slots, or consumers | Configure pipeline components explicitly |
| Assuming wal_level controls retention | WAL has info yet still gets reclaimed | Design retention separately |
| Raising wal_keep_size alone for long outages | Segments can still be lost | Use slots/archives sized to outage budget |
| Using uncapped slots everywhere | Inactive slots can exhaust disk | Add caps, alerts, and lifecycle tracking |
| Dropping a slot to free disk without checking owner | Consumer loses needed WAL | Verify or prepare re-bootstrap plan |
| Treating max_wal_size as a hard cap | pg_wal can still exceed it | Monitor slots, archiving, and keep settings |
| Treating min_wal_size as standby retention | Does not guarantee LSN resumability | Use slots and archiving |
| Archive command returning 0 before upload finishes | WAL treated as archived before durable | Exit 0 only after durable persistence |
| Non-idempotent archive command | Retries cause overwrites or conflicts | Check existing files and checksums |
| Putting archives on the same full filesystem | Archiving fails to relieve disk pressure | Use separate storage and alerts |
| Keeping archives forever without policy | Unbounded storage costs | Backup-aware retention policy |
| Purging archives based on live standby state | Breaks PITR backup chains | Account for all backups and recovery targets |
| Setting archive_timeout extremely low | Excessive archive files and overhead | Size from RPO requirements |
| Treating archiving as synchronous commit | Does not ensure every commit is archived | Separate archiving from sync replication |
| Ignoring logical restart_lsn | Slot pins WAL unnoticed | Monitor restart_lsn and consumer lag |
| Checking only confirmed_flush_lsn | Misses restart_lsn and catalog_xmin | Monitor full slot state |
| Assuming inactive slots do not retain WAL | Disk still fills up | Audit inactive slots regularly |
| Sizing without peak WAL rate | Insufficient retention during bursts | Size from peak/percentile + headroom |
| Changing wal_level without restarting | Runtime stays at old level | Check pending_restart |
| Lowering wal_level while CDC still runs | Logical decoding stops working | Stop or migrate consumers first |
| Confusing synchronous_standby_names with wal_level | Mixes commit ack with WAL detail | Configure the two layers separately |
| Treating a running standby as a backup | Bad deletes/errors replicate immediately | Use base backups + WAL archives + restore tests |
| Deleting WAL with rm | Breaks recovery and replication | Let PostgreSQL manage segments |

## 54. PostgreSQL Practice Exercises

Run on a lab/staging cluster with appropriate administrative privileges. Exercises changing wal_level, archiving, or replication require restarts or affect cluster state; never run casually on production.

1. **WAL:** explain write-ahead logging and why WAL is flushed before data pages.
2. **Crash recovery:** describe the role of WAL redo after a crash.
3. **WAL vs. SQL log:** explain why WAL is not a log of SQL statements.
4. **LSN:** query pg_current_wal_lsn() and explain its format.
5. **LSN diff:** use pg_wal_lsn_diff to calculate distance between two positions.
6. **Segments:** locate the pg_wal directory and explain segment files.
7. **WAL generation:** list workloads that can cause WAL volume to surge.
8. **wal_level:** compare minimal, replica, and logical.
9. **Minimal:** explain why minimal cannot be used for PITR or standbys.
10. **Replica:** list features supported at replica level.
11. **Logical:** explain conceptually what extra information logical decoding needs.
12. **Selection:** choose wal_level for a system needing only crash recovery.
13. **Selection:** choose wal_level for physical standbys and PITR.
14. **Selection:** choose wal_level for physical HA plus CDC.
15. **Retention:** distinguish WAL generation from retention.
16. **Archiving:** explain archiving as copying segments to external storage.
17. **Recycling:** distinguish recycling WAL segments from archiving WAL segments.
18. **wal_keep_size:** configure 2GB and explain why that does not mean 2 hours.
19. **Legacy:** look up wal_keep_segments in older PostgreSQL versions.
20. **Replication slot:** create a physical slot in the lab.
21. **Physical slot:** configure primary_slot_name on a standby.
22. **Logical slot:** create a logical slot using pgoutput.
23. **Inactive slot:** explain why an inactive slot still retains WAL.
24. **Slot lifecycle:** build an inventory of slots and owners.
25. **restart_lsn:** explain why WAL must be retained from this position.
26. **confirmed_flush_lsn:** explain how it differs from restart_lsn.
27. **catalog_xmin:** describe the impact of a logical slot on catalog vacuuming.
28. **Slot cap:** configure max_slot_wal_keep_size and describe the trade-off.
29. **Slot invalidation:** explain what a standby or CDC consumer must do when a slot loses WAL.
30. **max_wal_size:** demonstrate why it is not a hard cap on pg_wal.
31. **min_wal_size:** explain how recycling differs from retention.
32. **Checkpoint:** distinguish checkpoints from archive/slot retention.
33. **Archive mode:** enable archive_mode and verify restart requirements.
34. **Archive command:** write an archive script accepting source path and segment name.
35. **Idempotency:** design an archive command handling retries and pre-existing files.
36. **Exit code:** explain why you must never return success before object-storage upload is durable.
37. **Archive timeout:** configure 300 seconds and analyze archive volume impact.
38. **Archive mode always:** describe when a standby might need to archive received WAL.
39. **Cleanup:** study pg_archivecleanup and conditions for safe usage.
40. **PITR:** describe base backup + WAL chain.
41. **Restore command:** write a conceptual command fetching WAL segments from the archive.
42. **Recovery target:** explain target time/LSN in PITR.
43. **Timeline:** describe the role of timeline history after promotion.
44. **Physical replication:** list primary and standby prerequisites.
45. **No slot:** describe how a standby fetches WAL and when a rebuild is needed.
46. **Cascading:** diagram primary → standby A → standby B.
47. **Synchronous:** distinguish synchronous_standby_names from wal_level.
48. **Commit:** compare synchronous_commit on vs. remote_apply semantically.
49. **Logical:** create a publication for two lab tables.
50. **Replica identity:** inspect primary keys and REPLICA IDENTITY.
51. **REPLICA IDENTITY FULL:** analyze WAL and apply costs.
52. **Native subscription:** create a subscriber in the lab and inspect its slot.
53. **CDC:** design a logical slot consumer with checkpointing/acknowledgement.
54. **Mixed consumers:** size slots and senders for 3 standbys and 4 CDC connectors.
55. **Sizing:** calculate WAL to retain for 10 MB/s peak and a 2-hour outage.
56. **Sizing:** calculate WAL to retain for 20 MB/s peak and a 6-hour outage.
57. **Headroom:** propose a buffer margin on top of calculated figures.
58. **Generation rate:** sample pg_stat_wal twice and compute bytes/second.
59. **Stats reset:** explain why a delta is invalid if stats_reset changed.
60. **Primary view:** query pg_stat_replication and read sent/write/flush/replay LSNs.
61. **Standby view:** query pg_stat_wal_receiver.
62. **Replay:** read pg_last_wal_receive_lsn and pg_last_wal_replay_lsn.
63. **Slot monitor:** query pg_replication_slots and sort by retained estimate.
64. **Archive monitor:** query pg_stat_archiver and analyze failed_count.
65. **Directory size:** use pg_ls_waldir to sum total bytes in pg_wal.
66. **Disk alert:** design an alert combining filesystem free space and WAL growth rate.
67. **Archive failure:** simulate a broken archive destination in the lab and observe retries.
68. **Inactive slot:** simulate a stopped consumer and observe retained WAL.
69. **Slot recovery:** plan a resnapshot when a logical slot is invalidated.
70. **Standby outage:** describe three recovery paths: slot, archive, and fresh base backup.
71. **wal_level restart:** inspect pg_settings.context and pending_restart.
72. **Upgrade:** list checks when major-upgrading a cluster with logical slots.
73. **Failover:** describe how consumers learn the new publisher and resume LSN.
74. **Archive retention:** design WAL retention tied to base backup/PITR windows.
75. **Security:** design privileges for replication roles and archive storage.
76. **Runbook:** write a procedure for rapid pg_wal growth.
77. **Runbook:** write a procedure for prolonged archive backlogs.
78. **Runbook:** write a procedure when a physical standby cannot resume.
79. **Runbook:** write a procedure when a CDC slot retains WAL beyond budget.
80. **Comprehensive design:** choose wal_level, slot/archive/keep limits, sender/slot capacity, backup/PITR retention, monitoring, and failover strategy for a system with both physical HA and logical CDC.

## 55. Pre-Deployment Checklist

### Replication and Recovery Needs

- [ ] Listed crash recovery, PITR, physical standbys, cascading, and logical CDC consumers.
- [ ] Selected wal_level matching the consumer needing the most detail.
- [ ] Avoided minimal if archiving, PITR, or replication is needed.
- [ ] Validated base backups and complete WAL archives covering recovery targets.
- [ ] Executed real restore tests.

### Retention and Capacity

- [ ] Measured peak WAL generation rate.
- [ ] Defined outage budgets for every standby and CDC consumer.
- [ ] Sized wal_keep_size for desired reconnect buffer.
- [ ] Assigned owners and lifecycles to all replication slots.
- [ ] Set max_slot_wal_keep_size aligned with disk budget and resnapshot policy.
- [ ] Avoided treating max_wal_size as a hard cap.
- [ ] Reserved headroom for WAL bursts, archive backlogs, and replication slots.

### Archiving

- [ ] Verified archive_mode and archive_command.
- [ ] Verified archive command reports success only after durable storage.
- [ ] Handled idempotent retries and checksum/file collisions.
- [ ] Verified capacity, security, and monitoring on the archive destination.
- [ ] Tuned archive_timeout for RPO and file overhead.
- [ ] Ensured cleanup never deletes WAL needed by any base backup or standby.

### Replication

- [ ] Sized max_wal_senders and max_replication_slots with headroom.
- [ ] Provided physical standbys with appropriate slot/archive recovery paths.
- [ ] Configured proper replica identity on replicated logical tables.
- [ ] Ensured CDC consumers track LSNs and acknowledge progress.
- [ ] Clarified synchronous vs. asynchronous policies.
- [ ] Tested failover slot/consumer recovery for your PostgreSQL version.

### Monitoring and Operations

- [ ] Deployed dashboards for WAL bytes/s and pg_wal disk usage.
- [ ] Set alerts for archive failures/backlogs.
- [ ] Set alerts for inactive slots and retained WAL.
- [ ] Set alerts for physical and logical consumer lag.
- [ ] Prepared runbooks for disk pressure, slot invalidation, and standby rebuilds.
- [ ] Prepared version-specific config and upgrade plans.
- [ ] Prohibited deleting or editing WAL files manually via filesystem commands.

## 56. Summary

wal_level, retention, and replication are three parts of one architecture with distinct responsibilities:

```text
wal_level
  -> Does WAL contain enough information for each consumer type?

Retention
  -> How far back is old WAL kept so consumers can still read it?

Replication / Archiving
  -> Who reads WAL, how do they read it, and where is it stored?
```

Key principles to remember:

- **minimal** is only for local crash recovery without archiving or replication; **replica** supports physical replication and PITR; **logical** adds information for logical decoding/CDC.
- **Setting a higher wal_level does not create or protect consumers.** Publications, subscriptions, slots, senders, archiving, and backups still require configuration.
- **wal_keep_size is a minimum extra cushion of WAL, not a hard cap or a duration in hours.**
- **Replication slots protect consumer progress yet can fill the disk** if a consumer stops; max_slot_wal_keep_size trades off disk safety against resumability.
- **max_wal_size is a soft checkpoint target**, not a cap on total pg_wal size.
- **WAL archives need base backups and retention policies** to serve PITR. Archive success must be durably verified with safe retries.
- **Physical replication, logical CDC, and PITR have different retention requirements.** Calculate each consumer's outage budget individually and watch the slowest consumer.
- **Measure WAL generation rates over time**, sizing from peaks/percentiles plus headroom rather than averages or static guesses.
- **Monitor pg_replication_slots, pg_stat_replication, pg_stat_wal_receiver, pg_stat_archiver, and filesystems** to know exactly why WAL is being retained.
- **Never manually delete WAL inside pg_wal.** Recover consumers/archiving, expand capacity, or drop slots only after understanding the consequences and having a recovery plan.

When properly designed, PostgreSQL can recover to arbitrary points in time, keep physical standbys caught up, and stream logical changes to CDC without turning WAL retention into a disk-full outage. Start from **each consumer's requirements**, translate them into **outage and recovery budgets**, and then configure wal_level, slot limits, wal_keep_size, archiving, and operational alerts.
