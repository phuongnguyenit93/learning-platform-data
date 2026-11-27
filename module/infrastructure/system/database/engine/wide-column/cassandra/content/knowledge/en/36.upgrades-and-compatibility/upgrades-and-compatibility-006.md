# Backing Up Configurations/Data and Rehearsing Recovery Before Changes

## 1. The Problem: Upgrade Finished, Cluster Is Up, Yet Applications Cannot Read Data

An **Apache Cassandra** cluster has run for years, serving event queries by device and time range. The operations team plans to upgrade Cassandra/JDK and adjust several `cassandra.yaml` parameters. In staging, nodes boot cleanly. Yet in production, after upgrading two nodes, Java applications begin timing out, several tables become inaccessible, and rolling back to the old binary fails to start as expected.

At that moment, urgent questions arise:

- Where are the old config versions, **schema**, per-datacenter RF, snitch, tokens, and node list stored?
- Were **SSTable snapshots** captured on every node before the change, or only on a coordinator?
- Were backups moved off-host with **manifests/checksums**, or are they merely hard-link directories on the same disk?
- If the source kept receiving writes during backup, where is **the recovery point (RPO)** guaranteed?
- Are backups compatible with **the Cassandra version, SSTable format, and restore tool** the team plans to use?
- Has anyone **rehearsed a restore in an isolated environment** and measured recovery time (RTO)?

In Cassandra, `nodetool snapshot` is helpful, yet **a snapshot is not automatically a complete, cluster-wide consistent, or restore-tested backup**. A change-ready system must hold **evidence** that configurations, schemas, data, and access controls can be reconstructed to acceptable levels.

This lesson belongs to the **Upgrades and Compatibility** chapter of the Cassandra module. Its material connects how Cassandra distributes partitions by token, stores data in SSTables, uses replication/consistency, reconciles via repair, and how Java applications verify read/write paths after recovery.

**Lesson objectives:**

1. Classify **configuration, schema, data, commit log, and metadata backups** by recovery goal.
2. Distinguish **snapshots, incremental backups, commit log archiving, logical exports, and replication**.
3. Identify artifacts requiring protection prior to upgrading, especially `system_auth`, topology, encryption keys, and TLS/JMX configs.
4. Author a runbook to capture backups **on every required node**, export off-cluster, verify checksums/retention, and protect permissions.
5. Rehearse an **isolated** restore, understanding SSTable format, internode compatibility, and schema risks.
6. Define **RPO, RTO, go/no-go, and rollback versus restore**, then verify via CQL/Java and before/after metrics.

> **Scope:** examples use Apache Cassandra with full replicas, `NetworkTopologyStrategy` keyspaces, and DC `dc1`. Command/option names, enabling incremental backups, SSTable formats, commit log archival, and upgrade paths **depend on version/distribution**. This lesson provides workflows and lab examples, **not permission to run directly on production**.

## 2. Three Concepts to Lock Down Before Choosing Backup Tools

### 2.1. Backup, Snapshot, and Replication Are Not the Same

| Mechanism | Protects against what? | Does not guarantee what? |
| --- | --- | --- |
| **Replication factor** | A partition has multiple natural replicas, tolerating node/DC faults per RF and CL. | Does not stop accidental `DELETE`s from replicating, logical corruption, dropped schemas, or ransomware. |
| **Local snapshot** | Preserves an SSTable set for **one node/table/keyspace** at capture time. | Does not survive if that disk/node is lost; does not automatically capture an atomic cluster-wide snapshot. |
| **Off-cluster backup** | Stores copies of data and metadata in an independent fault domain. | Does not prove restorability until manifests, versions, and decryption access are verified. |
| **Incremental backup** | Retains newly flushed SSTables after a checkpoint per version mechanics. | Does not replace a base full backup, is not a continuous mutation stream, and does not standalone-log all deletes. |
| **Commit log archive / PITR** | Can shrink data-loss windows by recovering close to an incident if fully engineered. | Simply copying live commit log files is not safe replayable PITR. |
| **Logical export** | Data extracted into rows/records for import or remodeling. | Does not automatically preserve writetimes, TTLs, tombstones, or cluster-wide consistent snapshots. |

An RF = 3 cluster survives losing a node, yet if a user holds `TRUNCATE` privileges on a table, all three replicas lose the business data. **Replication serves availability/durability; backups serve recovery from changes or mistakes replication cannot undo.**

### 2.2. RPO and RTO Are Requirements, Not Default Features

- **RPO (Recovery Point Objective):** maximum acceptable **time window of data loss** upon recovery. For instance, a 15-minute RPO means yesterday's snapshot cannot satisfy the requirement.
- **RTO (Recovery Time Objective):** allowed elapsed time until the service **returns to serving condition**, including restoring nodes, schemas, data, permissions, routing, and application verification.
- **Consistency of the restored state:** does the app require an atomic point-in-time snapshot, or can distributed snapshots be reconciled?
- **Incident scope:** losing one disk/node, one datacenter, the entire cluster, an accidental schema drop, or an incompatible upgrade?

Suppose a system processes 4 million writes per day. Daily 24-hour snapshots may suffice for rebuildable data, yet fail for order data with a 5-minute RPO. If an upstream event stream can replay all mutations with stable IDs, the RPO strategy may combine **snapshots + verified replay** rather than relying solely on RF.

### 2.3. Recovery Objectives Must Be Measurable

~~~text
Service             : telemetry-api
Target incident     : loss of one DC or failed upgrade rollback
Expected RPO        : <= 15 minutes (example)
Expected RTO        : <= 120 minutes (example)
Data correctness    : complete keys/values within target time window
Schema/RBAC         : tables, roles, and app permissions restored
Post-restore SLO    : read p99 and write error rate within approved limits
Evidence            : restore rehearsal + checksums + CQL/Java canary
~~~

This is a **requirement template**, not Cassandra defaults. Without explicit RPO/RTO targets, a team cannot prove a backup procedure is "safe enough."

## 3. Comprehensive Pre-Upgrade Backup Inventory

A copy of the `data/` directory **cannot replace all artifacts** needed for a cluster to function properly.

| Group | Artifacts to include in plan | Why it matters |
| --- | --- | --- |
| **Schema** | `CREATE KEYSPACE`, `CREATE TABLE`, UDTs, indexes, materialized views, functions/aggregates if used; migration history. | Table definitions must match SSTables and applications. |
| **Data** | SSTable snapshots per **node**, keyspace/table, and timestamp; manifests/checksums; incremental sets if any. | Restores physical data per node or imports via supported tools. |
| **Auth data** | `system_auth` and role/permission provisioning policies, backed up securely. | Losing auth metadata can lock out admins and clients. |
| **Replication/topology** | `cluster_name`, DC/rack/snitch, per-keyspace RF, seeds/contact points, token ownership, host IDs, node inventory. | Places data on proper replicas and restores routing. |
| **Cassandra config** | `cassandra.yaml`, `cassandra-env.sh` or equivalent, JVM options, compaction/commitlog/timeouts, logging, rackdc/snitch config. | Reproduces node behavior and enables pre/post-upgrade diffs. |
| **Runtime & packages** | Cassandra/JDK versions, build/distribution, plugins, Java Driver, OS/image/Helm/operator versions. | Verifies compatibility paths and rollback environments. |
| **Security material** | TLS certificate chains, truststores/keystores, key IDs, secret references, JMX auth, encryption-at-rest metadata. | Data may become unreadable or clients fail to connect without keys/certs. |
| **Backup infrastructure** | Snapshot schedule, object storage target, IAM, retention, encryption, verification logs. | Having bytes stored does not equal permission or capability to restore. |
| **Application contract** | CQL query templates, prepared statements, CL, schema dependencies, Java Driver settings, and smoke tests. | A cluster can show `UN` while apps still fail post-upgrade. |
| **Operations history** | Repair/streaming state, alerts, backup manifests, change ticket, approvals, UTC timestamps. | Separates upgrade regressions from pre-existing faults. |

### 3.1. Back Up Configuration as **Versioned Inputs**

Do not grab `cassandra.yaml` alone and assume that suffices. Depending on deployment, config lives in **ConfigMaps/Helm values/operator CRDs**, mounted files, JVM flags, or environment variables. With configuration management, record the exact **commit/image digest** running on every node before upgrading.

**Never place private keys, passwords, or access tokens into Markdown files, public Git, or tickets.** Manifests should hold only **references to secret versions**; real secrets live in encrypted, access-controlled vaults with independent recovery. Secret backups must obey rotation, retention, and emergency access policies.

### 3.2. Avoid Misinterpreting System Data

- `system_schema` reflects schema metadata and can be inspected; store an independent versioned **DDL/schema export** too.
- `system_auth` is sensitive distributed data requiring proper RF/backup/restore and post-restore login checks.
- Other `system*` keyspaces contain local state/metadata; **never blindly copy all system files from an old cluster onto a new cluster**, as they embed host IDs, token/topology state, and versions.
- `system_traces` and transient data may not be required for business RPO; decide by policy rather than backing up everything "just in case."

## 4. SSTable Snapshots: Fast to Capture, Tricky If Restore Was Overlooked

### 4.1. Core Mechanics

Cassandra writes mutations to the commit log and memtables, then flushes them into **immutable SSTables**. Snapshots typically create **hard links or filesystem references** to SSTables on the node, preserving files as of snapshot time.

~~~mermaid
flowchart TD
    A["Mutations enter memtable and commit log"] --> B["Flush per snapshot/version mechanics"]
    B --> C["Active SSTables on node N1"]
    C --> D["Snapshot tag: references SSTables"]
    C --> E["Compaction creates new SSTables"]
    D --> F["Old files stay retained while referenced by snapshot"]
    D --> G["Copy to independent backup storage"]
    G --> H["Manifest + checksums + version + key IDs"]
    H --> I["Restore rehearsal on isolated cluster"]
~~~

Notes:

1. Snapshots are **local per node**. Running the command on one coordinator does not capture all replicas/DCs.
2. Hard links share blocks with active SSTables, so snapshots **do not double disk usage immediately**; as compaction replaces old SSTables, snapshots pin old blocks and prevent disk space from shrinking.
3. Flush/memtable ordering and skip-flush options **depend on version**. A snapshot that does not flush memtable contents may miss un-flushed mutations without logs/supplements.
4. While nodes are snapshotted sequentially, applications continue writing. **There is no atomic cluster-wide snapshot transaction** just because all nodes share a tag name.
5. Creating a snapshot does not prove a backup is complete; you must **copy data off-node** and test reading it back.

### 4.2. Practicing `nodetool` in the Lab

~~~bash
# Check exact syntax on the running version:
nodetool help snapshot
nodetool help listsnapshots

# Pre-operation checks:
nodetool status
nodetool info
nodetool compactionstats
nodetool listsnapshots

# Run only on a LAB node for the lesson keyspace:
nodetool snapshot -t preupgrade-lab-20261121 telemetry_recovery

# After the tool reports completion:
nodetool listsnapshots
~~~

`nodetool snapshot -t` is a common syntax example; **keyspace/table scopes and options can vary** across Cassandra releases, so check `nodetool help snapshot` on the live node. In production, automation must run across **every required node**, recording node ID, DC, rack, version, tag, timestamp, and outcome.

### 4.3. "Successful Snapshot" Requires Four Layers of Evidence

| Layer | Evidence | Insufficient if you only have... |
| --- | --- | --- |
| **Local snapshot** | Correct node/table tag, valid local manifest. | Exit code 0 from one command. |
| **Off-node export** | Files/metadata stored on independent storage, checksums match, permissions valid. | `listsnapshots` on the source node. |
| **Restorable** | Successfully imported/restored onto an isolated cluster with matching schema/version. | `upload completed` or object count. |
| **Business-valid** | CQL/Java canary, data comparison, auth, and p99 pass. | Node reaching state `UN`. |

## 5. Incremental Backups and Commit Log Archival: Do Not Mix Their Purposes

### 5.1. What Is an Incremental Backup?

On supported versions, `incremental_backups` enables retaining **newly flushed SSTables** in a backup staging area for export; it is not a real-time per-mutation stream.

~~~yaml
# Conceptual configuration example; verify/apply only per actual Cassandra version.
incremental_backups: true
~~~

To restore using incremental backups, you need:

- A trustworthy **base/full snapshot** with intact schema and timestamps.
- The set of incremental SSTables covering the recovery window and a **gap-free** manifest.
- Identification, checksums, load ordering, deduplication, and SSTable compatibility.
- **Retention** enforcement: never delete the base snapshot while incremental sets still depend on it.

**Do not treat incremental SSTable backups as equivalent to a Kafka log, CDC, or application-level PITR transactions.** Updates/deletes and TTLs operate via mutation/SSTable semantics, requiring all relevant components to be restored together.

### 5.2. Commit Logs and PITR Capability

Commit logs exist for **recovering un-flushed memtables after a node crash**, not automatically as an arbitrary backup mutation history. Some versions/deployments support **commit log archiving** with custom configs/scripts. Designing *point-in-time recovery* (PITR) requires:

1. Verifying the feature, `commitlog_archiving.properties` or equivalent, Cassandra version, and official operator guidance.
2. Establishing the **archive start point**, matching base snapshot, and retention.
3. Ensuring archiving drops zero segments, preserves ordering/timestamps, and verifies checksums.
4. Testing **version-exact replay**, avoiding replaying mutations incompatible with schemas/tombstones or targeting a live serving cluster by mistake.
5. Performing an actual restore test to a chosen UTC target and **measuring data drift** against the source of truth.

**Never hot-copy open commit log files and call it PITR**, nor delete/read/edit segments inside a running node's commitlog directory. Archive/replay scripts need auditing, separate credentials, and dedicated IAM.

### 5.3. Logical Exports Do Not Replace Native Snapshots

Exporting via CQL/DSBulk/ETL tools helps move data across versions or altered schemas. However, a `SELECT` reading **live rows** does not export full tombstone histories, per-cell writetimes, original TTLs, or cross-partition concurrent state.

Example:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry_recovery.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';
~~~

This is a **logical data check**, not a physical backup capable of restoring all Cassandra semantics intact. When using logical imports, define explicit contracts for **expiry, timestamps, idempotency, deletes, and consistency**.

## 6. Multi-Datacenter: A Snapshot from One Node Cannot Recover the Cluster

Suppose a business keyspace:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_recovery
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};
~~~

Another production example has `dc1: 3`, `dc2: 3`. Data for a partition is replicated across replicas in each DC; yet **having the same RF does not mean every node holds the entire keyspace**.

~~~text
dc1: N1, N2, N3        dc2: N4, N5, N6

Partition A → A's natural replicas in each DC
Partition B → B's natural replicas in each DC

Snapshot of N1 contains only N1's SSTables.
Snapshot of N4 contains only N4's SSTables.
To protect the whole keyspace, backups must cover a sufficient node scope.
~~~

**Never assume snapshots across three nodes share one atomic point of consistency.** Each node receives mutations and flushes at different times. A successful `LOCAL_QUORUM` write only requires local DC quorum; remote replicas may not yet hold that mutation when their snapshots run.

### 6.1. Backup Scope by Risk Scenario

| Incident to survive | Required backup/restore scope |
| --- | --- |
| Loss of one node | Replication/replace can help, yet backups remain necessary against corruption/deletion alongside rebuild/repair runbooks. |
| Loss of an entire DC | Backups must reside outside **that DC's failure domain**, never solely on nodes inside the lost DC. |
| Accidental table drop | Pre-drop backup, schema export, and controlled recovery plan. |
| Loss of `system_auth` access | Auth system backup and tested break-glass administrative procedures. |
| SSTable format upgrade mistake | Backups **readable by supported tools/versions** and proper import/restore procedures. |
| Atomic app-level snapshot need | Dedicated write barrier/quiesce or upstream source-of-truth replay mechanism. |

In multi-DC environments, verify **per-DC RF, placement, repairs, and outage gaps** before snapshotting. If a replica is missing mutations, a backup from that node can be incomplete even when files and manifests validate cleanly.

## 7. Pre-Upgrade Compatibility: Check by Matrix Instead of Comparing Version Numbers

A backup has value only when a **supported recovery path** exists. When changing Cassandra, JDK, drivers, or topology, verify at least these layers:

| Compatibility layer | Mandatory question | If skipped |
| --- | --- | --- |
| **Upgrade path** | Is source version → target version directly supported? Is an intermediate release required? | Node fails to start or enters unsupported mixed-version state. |
| **SSTable format** | Can the target version read backed-up formats? Is `upgradesstables` or a conversion tool recommended? | Cannot use old binary to read new files once formats upgrade. |
| **Internode protocol** | Can new and old versions coexist during the rolling window? For how long? | Messaging/streaming/gossip incompatibilities. |
| **CQL/native protocol** | Are Java Driver, protocol negotiation, TLS, auth providers, and prepared statements compatible? | Applications fail even while nodes report `UN`. |
| **JDK/JVM** | Are JDK version, GC flags, JVM options, and container memory supported? | Process fails to start or suffers GC/latency regressions. |
| **Schema/features** | Do UDTs, indexes, materialized views, functions, counters, LWTs, CDC, or TTLs have version constraints? | Query failures, data divergence, or semantic shifts. |
| **Storage/capacity** | Is there enough disk for compaction, streaming, snapshots, hints, and temp tables? | Disk fills up during compaction or recovery. |
| **Security/operations** | Did JMX, TLS, authorization, backup scripts, or `nodetool` options change? | Cannot connect or extract data during an emergency restore. |

**Never assume a 3.x → 4.x or 4.x → 5.x path is allowed across arbitrary minor releases.** Only by checking **release notes, upgrade guides, and version matrices for the exact release** can you lock down order and mixed-version support.

### 7.1. `upgradesstables` Is Not a Harmless Command

Some Cassandra versions provide `nodetool upgradesstables` to rewrite SSTables into the running version's format. It can cause **heavy SSTable read/write I/O, disk pressure, and compaction spikes**, and render physical files unreadable by older binaries.

Therefore:

- Never run any SSTable format conversion before locking in **rollback feasibility and pre-upgrade backups**.
- Never assume swapping back to the old binary is a working rollback after data files/schemas have upgraded.
- If restoring from old snapshots is ever required, know **which tool and version accept that SSTable format**, and test in the lab.
- Monitor operations that can rewrite files **even if the command launches cleanly**; post-checks confirm completion.

### 7.2. Data Compatibility Does Not Equal Application Compatibility

Suppose the cluster reaches `UN`, yet the Java Driver specifies the wrong local DC or its truststore no longer matches certificates. The application still fails. Conversely, an application connecting over CQL does not prove snapshots/repairs work.

Go/no-go criteria must cover **two independent layers**: *cluster data/operations health* and *application contract/latency health*.

## 8. Before Backup: Preflight and Real Capacity Sizing

### 8.1. Node/Cluster Checklist

~~~bash
# Run on authorized nodes in lab or per production runbook.
nodetool status
nodetool info
nodetool compactionstats
nodetool tpstats
nodetool netstats
nodetool listsnapshots

# Linux example: substitute actual configured paths/mount points.
df -h
~~~

Record:

1. **UTC timestamp**, cluster name, datacenter, rack, node/host ID, source version/JDK.
2. Per-DC RF for all keyspaces, `UN`/`DN`/`UJ` states, and any active bootstrap/rebuild/replace/decommission.
3. Pending repairs, compactions, flushes, streaming, and client errors; do not back up mid-incident without assessing impact.
4. Write rate, p95/p99, timeouts, error rate, and free disk/headroom on **every volume**, not just cluster averages.
5. Old snapshots, retention, space pinned by hard links, and off-cluster destination capacity.
6. Operator permissions, backup destination IAM/TLS, encryption keys, and date of the latest restore test.

### 8.2. CQL Metadata Checks

~~~sql
-- Run with an account holding appropriate metadata read permissions.
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'telemetry_recovery';

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'system_auth';
~~~

In `cqlsh`, you can also run:

~~~sql
DESCRIBE KEYSPACE telemetry_recovery;
DESCRIBE TABLE telemetry_recovery.events_by_device_day;
~~~

`DESCRIBE` is a **`cqlsh` command**, not a CQL statement sent verbatim through the Java Driver. Schema exports must preserve **complete DDL, keyspace/table names, UDTs/indexes, resource creation order, and versions**. Never rely solely on screenshots of `DESC` without controlled DDL files.

### 8.3. Estimating Disk Headroom

Suppose a node has a **1,000 GB** data volume with **820 GB** used. The team anticipates retaining **120 GB** of old SSTables pinned by snapshots, generating **70 GB** of temporary compaction output, and receiving **40 GB** of new writes before old files can be freed:

~~~text
Initial free space                 : 180 GB
Old files pinned by snapshot (est.): 120 GB
Temporary compaction output (est.) :  70 GB
New writes during window (est.)    :  40 GB
Total potential growth             : 230 GB
Modeled headroom shortfall         :  50 GB
~~~

This is a **simplified upper-bound example**: hard links do not duplicate files at snapshot time, and file release timing/compaction scopes vary. Yet it highlights a vital point: **taking a safe backup on a nearly full node can starve subsequent compactions of disk space**, even though creating the initial snapshot was instant.

## 9. CQL Lab: Baseline Data Before Changes

### 9.1. Table by Device and Day

After creating keyspace `telemetry_recovery` in Section 6, create the lab table:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_recovery.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`(device_id, event_day)` is the composite partition key; `(event_time, event_id)` is the clustering key. The same device across two days can map to **different tokens/natural replicas**. This matters during backup/restore because you cannot grab a snapshot from one random node and assume it holds every partition of the table.

### 9.2. Write Sentinel Rows

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_recovery.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T08:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'heartbeat', 'ok');

INSERT INTO telemetry_recovery.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T08:05:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'temperature', '21.2');

INSERT INTO telemetry_recovery.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-8', '2026-11-21', '2026-11-21T08:07:00Z',
   123e4567-e89b-42d3-a456-426614174003, 'alarm', 'over_limit');
~~~

`LOCAL_QUORUM` with RF = 3 in `dc1` requires **two replica ACKs** per write. It does not prove **every replica** wrote the row at the exact moment a snapshot is taken; therefore, sequential per-node snapshots still require a data consistency plan.

### 9.3. Record Data and Read-Path Baseline

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry_recovery.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T09:00:00Z';
~~~

The sentinel dataset contains **two rows** for `device-7`, ordered by `event_time DESC`, with fixed event IDs and payloads. During restore rehearsals, compare **keys and values** to catch wrong keyspaces, buckets, clustering orders, or missing rows. In production, a few sentinel rows **do not replace** full-scale reconciliation.

## 10. Pre-Rolling-Upgrade Backup Procedure

### Phase A — Lock Information and Boundaries

1. Record **change ID**, source/target versions, and **supported upgrade path**.
2. Lock **RPO/RTO**, time window, and write handling during snapshotting: pause writes, write barrier, durable event stream, or another fitting approach.
3. Lock **table/keyspace/node/DC scope**, including `system_auth` and required metadata.
4. Capture baseline RF, tokens, schemas, auth/JMX/TLS, and replica health.
5. Ensure sufficient disk headroom, backup bandwidth that does not choke reads/writes, and proper backup storage permissions.

### Phase B — Create Snapshots on Every Required Node

~~~bash
# Lab node EXAMPLE; production automation must execute across full node scope.
nodetool snapshot -t preupgrade-lab-20261121 telemetry_recovery
nodetool listsnapshots
~~~

Never treat a standalone snapshot tag as a unique cluster-wide identifier. In the backup manifest, record:

~~~text
change_id       = CHG-2026-11-21-CASS-UPGRADE
snapshot_tag    = preupgrade-lab-20261121
node            = cassandra-dc1-n1
datacenter      = dc1
rack            = rack-a
host_id         = <recorded-node-host-id>
cassandra_src   = <exact-version-and-build>
jdk_src         = <exact-jdk-build>
keyspace        = telemetry_recovery
schema_hash     = <hash-of-versioned-schema-export>
snapshot_start  = <UTC>
snapshot_end    = <UTC>
backup_format   = native-sstable-snapshot
manifest_state  = LOCAL_SNAPSHOT_VERIFIED
~~~

`<...>` are placeholders to fill with actual observed outputs, **never** copied literally into manifests. Record **one entry per node/table/artifact**; if node N3 failed its snapshot, the whole backup set may fail its goal even if N1/N2 succeeded.

### Phase C — Export and Verify Off-Cluster

1. Verify **the exact snapshot files and metadata** per node against the versioned manifest; never blindly copy a mutating `data` directory.
2. Transfer data to **fault-isolated object storage/backup appliance**, encrypted in transit and at rest.
3. Verify **file checksums** and file/byte counts at both source and destination, never relying solely on a `copy` exit code.
4. Store **schema/config/version manifests** alongside secret/key references; enforce read/delete permissions and retention/immutability.
5. Mark `BACKUP_EXPORTED` once data lands safely, and reserve `RESTORE_VERIFIED` strictly for after a successful restore rehearsal.

On a Linux lab host, checking the hash of **a sample file**:

~~~bash
# Example path must be replaced with the actual verified snapshot/backup file.
sha256sum /backup-staging/example-sstable-file.db
~~~

In production, use a backup system that generates **automated manifest hashes**, compares end-to-end, and audits retention and restorability. Never store plaintext encryption keys in manifests, and never keep backups solely on Cassandra's own volumes.

### Phase D — Complete Pre-Change Gates

Do not upgrade the first node until you have:

- Backup sets covering required **nodes/DCs, keyspaces, and metadata**.
- Verified checksums/manifests and off-cluster copies with confirmed decrypt/read access.
- A **restore rehearsal** passing on supported source/target versions.
- Proven worst-case data loss within **RPO**; if writes continued, verified log/replay or an appropriate freeze window.
- A rolling plan, one or more **Java canary queries**, stop thresholds, and rollback/restore docs.

## 11. How Do You Know If a Backup Is Truly Consistent?

### 11.1. Node Snapshots Are Not Application Transaction Snapshots

Suppose two related business writes occur:

~~~text
10:00:00.100  Write order header to partition A
10:00:00.150  Write order items to partition B
10:00:00.120  Snapshot N1
10:00:00.170  Snapshot N2
~~~

If a backup combines SSTables from both nodes into one recovery set, you can end up with **a header missing its items** or vice versa, depending on partition placement, replicas, and write timing. Cassandra does not provide **atomic cross-partition/cross-DC snapshots** for this pattern.

To achieve a business-consistent state, explicitly engineer one of these:

- **Quiesce writes:** pause/drain mutations during a controlled window, confirm in-flight writes settle, then snapshot.
- **Application barrier/watermark:** record a business checkpoint in the source of truth and retain mutation logs to replay to that state.
- **Upstream transaction/outbox:** use an ordered/offset-based transactional source and rebuild Cassandra projections after restore.
- **Eventual consistency with reconciliation:** if business rules allow, define data completeness criteria and post-restore reconciliation.

None of these happen automatically just by using `QUORUM` or `ALL`: CL governs **per-request replica responses**, not multi-table distributed transaction snapshots.

### 11.2. Tombstones and TTLs Affect Backup/Restore Outcomes

A `DELETE`d row can still leave tombstones in SSTables, and expired TTLs do not erase files immediately. Native SSTable restores carry **timestamps/tombstones/TTL metadata**, yet correctness still depends on having complete SSTables, matching versions, recovery points, and proper loading/merging.

Meanwhile, **logical exports of live rows** miss tombstones and original expiration metadata. Re-importing via fresh `INSERT`s can **reset TTLs from import time** and resurrect previously deleted data if mutation ordering is mishandled.

Therefore, restore tests must check:

1. Live rows match exact values as of the target point.
2. Deleted/expired rows **do not** reappear illegally.
3. Remaining TTLs and retention match business rules.
4. Replicas are repaired/converged per scope and version.
5. Any post-snapshot mutations were replayed/reconciled strictly to the **watermark**.

**Never lower `gc_grace_seconds` arbitrarily to speed up reclamation before a backup**: replicas missing tombstones can resurrect stale data during subsequent synchronization.

## 12. Restore Rehearsal: An Isolated Environment Matters More Than a Restore Command

**Restore rehearsal** means performing an actual restore from stored backups in a controlled environment and proving the service reads/writes properly and meets the target recovery point. It is completely different from running `nodetool listsnapshots` or downloading one file from object storage.

### 12.1. Three Restore Styles for Three Goals

| Restore style | Scenario | Conditions/trade-offs |
| --- | --- | --- |
| **Physical node recovery per supported workflow** | One node loses a disk and needs host replacement/structured file recovery. | Requires understanding host ID, token ownership, file paths, topology, and versions; replace/streaming is often preferred over file copying. |
| **Restore to an isolated lab cluster via SSTable import/streaming** | Validating backups or recovering data into an independent cluster. | Create compatible schema/target topology and use version-supported tools like `sstableloader` or equivalent workflows. |
| **Logical record/export restore** | Moving to a different schema requiring data transformation. | Does not automatically preserve tombstones/TTL/writetimes; requires source-of-truth inputs and semantic verification. |

There is no universal `restore everything` command across all Cassandra releases. Before rehearsing, write a **restore plan tailored to the data source, snapshot layout, source/target versions, schema, encryption, and topology**.

### 12.2. Mandatory Isolation Layers

~~~mermaid
flowchart LR
    A["Backup storage: read-only snapshot + manifest"] --> B["Approved restore staging"]
    B --> C["TEST Cassandra cluster on isolated network"]
    D["Production gossip/internode/CQL"] -.->|"Must not connect"| C
    E["Secret manager: test credentials"] --> C
    C --> F["CQL/Java canary + data reconciliation"]
    F --> G["RPO, RTO, and restore evidence"]
~~~

When building the test cluster:

- Use **separate cluster identity, network, seeds/contact points, and service DNS**; block internode/gossip traffic to production. Never let a test node accidentally join the production ring.
- Verify **`cluster_name`, listen/broadcast addresses, DC/rack/snitch**, and TLS configs match the test topology.
- Never copy production secrets or private keys into under-protected labs. Fetch only authorized backups, encrypted and redacted as needed.
- If the test cluster has fewer nodes than production RF, prepare a **valid test RF/CL plan** without altering the original backup or production; never assume `LOCAL_QUORUM` for `dc1:3` works on a single node.
- Record **version and SSTable conversion/import method** in the lab. Never switch target versions arbitrarily just so a tool "agrees to read files."
- Separate rehearsal output storage and logs from the source backup; keep source backups **read-only/immutable** so drills can repeat safely.

**Warning:** copying files or restoring straight into a live Cassandra node's SSTable directory corrupts file state and SSTable trackers. Use **official version-supported import/streaming/restore mechanisms**, and for offline recovery follow node-stop/metadata/topology runbooks. Never just run `cp` or `rsync` into an active directory.

## 13. Step-by-Step Restore Rehearsal Runbook

### Step 1 — Pick One Backup Set and Fix Targets

Never pick "the latest" vaguely. Every rehearsal must lock in:

~~~text
rehearsal_id      = DRILL-2026-11-21-01
backup_set_id     = PREUPG-2026-11-21-telemetry
source_cluster    = cassandra-prod
source_version    = <exact-source-build>
target_cluster    = cassandra-restore-lab
target_version    = <supported-restore-version>
target_rpo_point  = <UTC watermark / snapshot set + mutation-log position>
required_tables   = telemetry_recovery.events_by_device_day, system_auth policy
success_criteria  = checksum + data match + role checks + application canary
restore_deadline  = <UTC deadline representing RTO>
~~~

The backup source must carry **per-node manifests, DDL, config/version, and hashes**. If backups ran while production still took writes, the plan must specify **which mutation watermark is recovered**, not just snapshot directory timestamps.

### Step 2 — Verify Download, Decryption, and Metadata Readability

1. Use **short-lived backup/restore credentials**; do not log in as an application superuser.
2. Access off-cluster storage and check object counts, byte sizes, checksums, and **manifest integrity**.
3. Verify required key IDs/envelope keys/trust chains for decryption exist and are accessible.
4. Check full schema DDL, `keyspace/table-UUID` mappings, versions, RF/DC, SSTable components, and snapshot tags.
5. Verify **base snapshots and incremental/archived log chains** if multi-step restore is targeted.
6. Never accept just a single `Data.db` file: an SSTable consists of **multiple components** such as index/statistics/compression metadata that depend on version.

**Outcome:** record `BACKUP_BYTES_VERIFIED` or `BACKUP_INCOMPLETE`—**never** jump straight to `RESTORE_SUCCESS`.

### Step 3 — Provision Target Environment with Exact Compatibility

- Provision an isolated test cluster with Cassandra/JDK **per the approved support matrix**.
- Apply **the exact keyspace/table schema** from versioned DDL; verify keys and clustering columns before loading.
- Confirm the test cluster has sufficient disk for **import/streaming/compaction**, including temp files and backup staging.
- Decide `system_auth` handling: either restore it cleanly in an isolated admin environment or reprovision equivalent test identities. **Never mix production auth metadata accidentally with test policies.**
- Choose **CL/driver versions** matching test replica counts and smoke-test goals.

### Step 4 — Load Data Using the Method Matching the Backup Type

For native SSTable backups, options may include **SSTable streaming/import** or version-specific offline recovery. `sstableloader` is commonly used to **stream SSTables into a target cluster**, yet path syntax, DDL prerequisites, source/target formats, authentication, and snapshot directory handling must be verified on the exact Cassandra release.

Never:

- Copy files from one arbitrary version into another version's node and keep restarting until it boots.
- Run `nodetool refresh` or direct file copies without knowing node/table state and version-specific import rules.
- Copy system data tied to **host identity/ring metadata** into a test cluster with different identities.
- Load a snapshot from **only one node** and claim full keyspace recovery.
- Run restore tests and admin tools using production credentials in uncontrolled environments.

**Outcome:** record tables/windows/token ranges loaded, skipped/failed files, byte counts, and session/streaming logs.

### Step 5 — Reconcile and Wait for Required Background Work

After ingest:

~~~bash
# On TEST node.
nodetool status
nodetool info
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool tablestats telemetry_recovery.events_by_device_day
~~~

When replicas diverge or many SSTables were imported, the workflow may need **repair/compaction per version guidance**. Never force major compaction just to "clean up restored data"; it can consume huge temporary disk space, alter TTL/tombstones, and extend RTO.

**`UN` only proves the node is up/normal in membership**; it does not prove every partition or role was restored accurately.

### Step 6 — Reconcile Data and Test Applications

1. Query known **sentinel** partitions by partition key and clustering range.
2. Compare `event_time`, `event_id`, `event_type`, and `payload` by **key/value**, not just row count.
3. Cross-check representative partitions, hot/cold partitions, boundary timestamps, TTLs, deletes, and late-arriving events.
4. If an **external source of truth** exists, compare against its state at the defined watermark—not against two unsynchronized snapshots.
5. Test Java Driver/CQL with **least-privilege read/write roles**, TLS, local DC, and proper CL; also verify `Unauthorized` rejection when permissions are missing.
6. Measure p50/p95/p99, error rates, timeouts, disk I/O, GC, and request throughput under controlled lab load.

### Step 7 — Record RPO/RTO and Pass/Fail Verdict

~~~text
Tool outcome              : import command success / failed / unknown
Data verification         : key/value match / mismatch / not measured
Recovery point validated  : last event/offset verified at <UTC>
Recovery elapsed          : measured wall time to service canary readiness
Auth/TLS verification     : passed / failed / not applicable
SLO/functional canary     : passed / failed / incomplete
Final verdict             : RESTORE_VERIFIED / FAILED / INCONCLUSIVE
~~~

**Do not equate the restore command finishing with RTO.** RTO is achieved only when **applications serve accurately** under approved criteria. If mismatches appear or deletes/TTLs went untested, mark `INCONCLUSIVE`, never `VERIFIED`.

## 14. Java Driver 4.x: Post-Restore Smoke Test

The test cluster already holds `telemetry_recovery.events_by_device_day` and the sentinel rows from Section 9. This Java example checks **the exact two events** for `device-7` on one day. It runs read-only, requires no DDL/JMX privileges, and does not modify backup data.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class RestoreSmokeTest {
    public static void main(String[] args) {
        // Use only the host/DC of the isolated TEST cluster.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement statement = session.prepare(
                "SELECT event_time, event_id, event_type, payload " +
                "FROM telemetry_recovery.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ?");

            BoundStatement read = statement.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            Map<UUID, String> expected = new HashMap<>();
            expected.put(
                UUID.fromString("123e4567-e89b-42d3-a456-426614174001"),
                "heartbeat|ok");
            expected.put(
                UUID.fromString("123e4567-e89b-42d3-a456-426614174002"),
                "temperature|21.2");
            Map<UUID, String> actual = new HashMap<>();
            long started = System.nanoTime();

            for (Row row : session.execute(read)) {
                Instant time = row.getInstant("event_time");
                if (time.isBefore(Instant.parse("2026-11-21T08:00:00Z"))
                        || !time.isBefore(
                            Instant.parse("2026-11-21T09:00:00Z"))) {
                    throw new IllegalStateException(
                        "Unexpected event outside sentinel window");
                }
                UUID eventId = row.getUuid("event_id");
                String value = row.getString("event_type")
                    + "|" + row.getString("payload");
                if (actual.put(eventId, value) != null) {
                    throw new IllegalStateException("Duplicate event ID");
                }
            }

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);

            if (!actual.equals(expected)) {
                throw new IllegalStateException(
                    "RESTORE_MISMATCH: sentinel key/value mismatch");
            }
            System.out.println("RESTORE_SENTINEL_OK"
                + " query=events_by_device_day"
                + " cl=LOCAL_QUORUM"
                + " rows=" + actual.size()
                + " elapsed_ms=" + elapsedMs);
        }
    }
}
~~~

### 14.1. Conditions for Interpreting This Test Correctly

- `CqlSession.builder()` must target the **rehearsal cluster**, never production. The loopback IP here is a lab setup.
- `LOCAL_QUORUM` with `dc1:3` requires two replicas; if the test cluster has only one node, **design valid test RF/CL** rather than silently lowering CL when verifying correctness.
- Two sentinel rows catch obvious mistakes yet **do not prove the entire backup is complete**. Reconcile data by partition/window or canonicalized checksums at scale.
- The program measures client elapsed time including decoding/iteration, not standalone replica disk latency.
- In production, configure **TLS, authentication, secret managers, and driver timeouts**; omitting them in this lab snippet does not mean security is optional.
- If the backup predates the sentinel rows, align the test to **the actual backup set and watermark** rather than misattributing post-backup data as a restore failure.

### 14.2. Also Test Negative/Rejected Cases

If auth/RBAC is in restore scope, run with a **read-only role** and verify:

1. `SELECT` on authorized tables succeeds.
2. Unauthorized `INSERT/DELETE/ALTER TABLE` operations **are genuinely rejected** when safely tested on a lab table.
3. Break-glass admin accounts work per procedure; revoked default accounts/secrets can no longer log in.
4. Java connections validate proper truststores/certificates; never use TLS `trust-all`.

**Restoring `system_auth` incorrectly** can leave data intact while locking out every app and admin; that directly impacts RTO and cannot be skipped.

## 15. Data Verification: Counts Are Insufficient, and File Checksums Are Insufficient

### 15.1. Two Distinct Verification Levels

- **Backup file-level checksum:** confirms bytes copied from source to target **were not accidentally corrupted**. It does not prove the backup captured the right table, timestamp, or all replicas/tokens.
- **Record-level logical reconciliation:** confirms required keys/values **are actually queryable** on the restored cluster, including TTL/delete logic and mutation replay to the watermark.

~~~text
File checksum PASS
  != backup coverage PASS
  != data consistency PASS
  != application availability PASS
  != RPO/RTO PASS
~~~

### 15.2. Why Full-Table `COUNT(*)` Is a Trap

Cassandra does not maintain a free, exact live-row counter for every table. Running `SELECT COUNT(*)` across large datasets scans vast numbers of partitions/SSTables, causing I/O, GC, tombstone pressure, and frequent timeouts.

During restore rehearsals, prefer:

1. Selecting **bounded scopes**: device/day, token ranges, or tables/tenants per inventory.
2. Comparing **primary key sets**, `event_time`, canonicalized payloads, and critical business fields.
3. Computing **ordered fingerprints** over normalized data in external tooling where appropriate, documenting the algorithm/serialization.
4. Ensuring source and restore are compared at **the same watermark**. If writes continue, differences may reflect timing skew rather than data loss.
5. Checking **rows that must not exist**: deleted/TTL-expired events must not reappear in violation of contracts.

### 15.3. Distinguish Repair from Logical Data Recovery

`nodetool repair` reconciles replicas of **the same keyspace/table** across a repair range; it **does not** recreate dropped schemas, fix backups missing tables, or turn logical exports into atomic snapshots. After a restore, repair may be part of the sync plan, **never a substitute** for full application data verification.

## 16. Before Rolling Upgrade: Go/No-Go and Rollback Concepts

### 16.1. Distinct Reversal Scenarios

| Action | When feasible? | Risks |
| --- | --- | --- |
| **Config rollback** | When old config exists, new config created no incompatible state, and the version permits it. | May still require restarts and impact availability. |
| **Binary rollback** | Only when **the specific downgrade path is supported** and data/schema/format have not crossed compatibility bounds. | Old binary may fail to read upgraded SSTables or schemas. |
| **Restore from backup** | When tested pre-change backups and a suitable restore target exist. | Incurs RPO/RTO and may need rehydration/streaming/replay; not instantaneous. |
| **Replace/rebuild replica** | When the cluster retains replicas with full data and topology supports it. | Cannot help when accidental deletes replicated to all replicas. |

**Never write "if the upgrade fails, reinstall the old version" as a complete rollback strategy.** Once SSTable formats, schemas, or internode compatibility change, downgrades may be unsupported. Evaluate exact source/target version limits and run a restore rehearsal.

### 16.2. GO Criteria Before the First Node

~~~text
[ ] Source -> target upgrade path is release-supported.
[ ] JDK/driver/native protocol/TLS/JMX compatibility tested.
[ ] Source config, schema DDL, RF/DC, topology, roles, and secret refs saved.
[ ] system_auth protected, backed up, and break-glass rehearsed.
[ ] Snapshots/backups cover required nodes/partitions/keyspaces per approved plan.
[ ] Base/incremental/archived-log chain complete if required by RPO.
[ ] Off-cluster backup checksums, manifests, retention, encryption verified.
[ ] Isolated cluster restore rehearsal passes data + auth + Java canary.
[ ] Measured RPO and RTO meet targets.
[ ] Capacity/disk headroom available for snapshots, compaction, streaming.
[ ] Replica/DC health, repair, and hint/compaction backlogs acceptable.
[ ] Canary node/order preserves quorum without risky multi-replica restarts.
[ ] Stop conditions, owners/approvers, and rollback/restore plans documented.
~~~

If any criterion **lacks evidence**, never mark `GO` simply because the maintenance window arrived. High-risk changes require accountable approvers to sign off on exceptions.

### 16.3. STOP Criteria During Rolling Upgrade

- A new node fails to join the ring compatibly, or gossip/internode connections fail.
- Active RF/CL lacks sufficient replicas; read/write timeouts or unavailable errors exceed baseline.
- Free disk drops below maintenance headroom, or compaction/streaming backlogs grow unchecked.
- Java applications fail to connect, or prepared statements/TLS/auth start failing.
- Snapshot/export/restore/backup access breaks due to config or permission changes.
- Unexplained data/canary discrepancies appear.

**Halting rollout expansion** does not necessarily mean immediately restarting/rolling back the upgraded node. Reversals must follow **supported paths** and actual SSTable/schema state.

## 17. Common Rehearsal Failures and Safe Responses

| Situation | Possible causes | Safe action |
| --- | --- | --- |
| `listsnapshots` shows tag, yet object storage is empty | Only captured locally; export never ran or uploader failed. | Keep `BACKUP_INCOMPLETE`, fix export, and verify checksums. |
| Snapshots exist for N1/N2, missing on N3 | Automation missed nodes or node failed. | Assess token/replica coverage; never claim cluster-wide coverage. |
| File checksums PASS, yet sentinel rows missing | Wrong node/window/schema backed up, or replica snapshot predated mutation. | Reconcile manifests, watermarks, full/incremental/replay, and natural replicas. |
| Restore test accidentally sees production | Misconfigured DNS/seeds/cluster identity/network isolation. | **Stop immediately**, isolate network; assess impact before retrying. |
| Test node boots yet cannot read SSTables | Incompatible version/format/schema/path/metadata. | Use supported import/upgrade path; do not force hot file copies. |
| `system_auth` restore locks out admins | Auth metadata, RF/role cache, or credential mismatch. | Run break-glass runbook, keep isolated, verify role provisioning. |
| Restored TTLs look "renewed" | Logical import created fresh mutations with full TTLs. | Compute remaining TTL/expiry, test semantics, never treat logical exports as native. |
| `DELETE`d rows reappear | Incomplete replay/tombstones, timestamp conflict, or diverged replicas. | Halt cutover, investigate mutation order/repairs and data watermarks. |
| Recovery takes hours longer than RTO | Slow import/streaming I/O, excessive SSTables, network, or startup. | Measure bottlenecks and tune controlled backup/parallelism. |
| Old binary fails to start after upgrade | File/schema format changed or downgrade unsupported. | Restore from pre-change backup on compatible version; stop blind downgrade attempts. |
| Backup vault fails to decrypt | Missing key ID/KMS/IAM, expired cert, or rotated/deleted key. | Audit backup encryption/recovery key lifecycles and update procedures. |
| Restore test checked only one row yet signed off GO | Correctness bar far too weak. | Expand scope to deleted/TTL/hot partitions, app SLOs, and auth. |

### 17.1. When a Command Fails or Loses Connectivity

If automation loses SSH/JMX during snapshot/import, the command may be **unstarted, still running, or partially completed**. Record status `UNKNOWN` and verify via logs, session IDs, snapshot inventories, file manifests, and streaming status before retrying. Never blindly re-trigger heavy jobs on a loaded cluster.

## 18. Designing Durable Off-Cluster Backups

### 18.1. Practical 3-2-1 Principles

A common guideline is maintaining **multiple copies**, across **different failure domains/storage media**, with **at least one copy off-cluster/off-site**. This is a resilience guideline rather than an exact mandated count for every organization; align it with RPO/RTO, cost, and compliance.

Practical controls:

1. **Isolation:** backup destinations must not depend on Cassandra disks, nodes, DCs, or Cassandra admin credentials.
2. **Encryption:** data and metadata encrypted in transit and at rest with independent KMS/secret recovery.
3. **Immutability/retention:** prevent accidental edits/deletions with enforced retention and policy audits.
4. **Least privilege:** backup writers should not automatically hold delete rights over all backups; restore readers stay separate from apps.
5. **Integrity:** file checksums, signed/versioned manifests where supported, and periodic integrity verification.
6. **Observability:** alerts on overdue backups, incomplete exports, missing nodes, RPO gaps, and expiring secrets/certs.
7. **Restore rehearsals:** run periodically and **before major changes**, sampling random or high-risk backups.

### 18.2. What Should a Backup Manifest Contain?

~~~text
backup_set_id
change_id + reason
source_cluster + environment
exact source Cassandra/JDK build
keyspace/table/schema export hash
per-node: host_id, DC, rack, token/ring metadata
per-node: snapshot tag + UTC start/end + state
SSTable component list + byte sizes + checksums
incremental set IDs / archived segment ranges (if any)
source of mutation watermark/RPO definition
encryption key references (no raw keys)
off-cluster destination + retention/immutability
verified_by + verified_at_utc + verification method
restore rehearsal ID + target version + verdict
~~~

Maintaining an **independent manifest** also tells you which backup belongs where if nodes end up on different SSTable formats post-upgrade. Never guess versions solely from backup dates or filenames.

## 19. Case Study: Two-DC Cassandra Upgrade, Valid Snapshots Yet Missed RPO

Suppose a cluster has `dc1:3` and `dc2:3`. Apps write in `dc1` with `LOCAL_QUORUM`. Company targets: 10-minute RPO, 90-minute RTO. The team captures pre-upgrade snapshots as follows:

| UTC time | Hypothetical event | What must be evaluated |
| --- | --- | --- |
| 09:00 | Sequential snapshots on N1–N3 in `dc1`. | Are writers active? Did any mutations miss other replicas? |
| 09:05 | Sequential snapshots on N4–N6 in `dc2`. | Have writes from `dc1` arrived at `dc2` yet? |
| 09:10 | All nodes share the same tag name. | Matching tags **do not** create an atomic cluster-wide snapshot. |
| 09:15 | File exports report completion. | Are checksums/manifests and all SSTable components complete? |
| 09:20 | Upgrade starts; apps keep writing. | Which mutations after snapshot will be replayed if rollback is needed? |
| 10:00 | Upgrade incident renders apps unavailable. | Did prior restore tests prove 90-minute RTO and 10-minute RPO? |

**Flaw in this scenario:** the team checked only snapshot tag counts and one sentinel `SELECT` before 09:00, then claimed a 10-minute RPO. If recovery at 10:00 must restore from 09:00 backups without a **continuous, recoverable mutation log** up to 09:50, the 10-minute RPO **was never guaranteed**.

**How to fix:** combine snapshots with a tested catch-up/archive/replay plan, or run the change inside a controlled write-freeze window if SLAs allow. In restore rehearsals, verify **mutations near the target watermark**, cross-DC consistency, and application behavior—not merely file existence.

### 19.1. Incident Findings Must State Evidence Boundaries

~~~text
Observation:
  Snapshots exist on all 6 nodes, exported and checksums PASS.

Not yet proven:
  Ability to restore all writes prior to 09:50.
  Post-restore schema/permissions accurate across both DCs.
  Recovery completes within 90 minutes under real load.

Decision:
  BACKUP_EXPORTED, RESTORE_RPO_UNVERIFIED
  => NO-GO for changes requiring a 10-minute RPO.
~~~

There is nothing wrong with **not yet guaranteeing** an RPO; what is wrong is marking it passed without evidence.

## 20. Common Misconceptions

| Statement | True/False | Explanation |
| --- | --- | --- |
| "RF = 3 replaces backups." | **False** | Replication does not protect against accidental deletes or logical corruption spreading to replicas. |
| "One `nodetool snapshot` on a coordinator snapshots the whole cluster." | **False** | Snapshots are per-node operations; coverage must be orchestrated. |
| "Snapshots always double disk usage immediately." | **False** | Hard links share blocks; old files remain pinned across subsequent compactions. |
| "Two DCs sharing a snapshot tag means identical point-in-time data." | **False** | No atomic cross-node/cross-DC application snapshot exists by default. |
| "Backups on the same Cassandra disk still protect against disk failure." | **False** | Sharing the failure domain risks losing both together. |
| "Incremental backups are a commit log mutation stream." | **False** | They capture newly flushed SSTables and require a base snapshot. |
| "Copying live commit logs gives you PITR." | **False** | Archival/replay requires dedicated configuration, watermarks, and testing. |
| "`DESCRIBE TABLE` shows data is fully backed up." | **False** | DDL shows only schema. |
| "Valid file checksums prove RPO is met." | **False** | Checksums do not tell whether timestamps and scope cover required data. |
| "Full-table `SELECT COUNT(*)` is a cheap verification check." | **False** | It can trigger massive scans in Cassandra. |
| "You can downgrade binaries anytime a rolling upgrade fails." | **False** | SSTable/schema/compatibility changes may forbid downgrades. |
| "`LOCAL_QUORUM` turns multiple SELECTs into an atomic snapshot." | **False** | CL governs per-request replica replies, not multi-table transaction snapshots. |
| "Enabling TLS makes backups self-restoring." | **False** | Recovery still depends on metadata, decryption keys, schemas, SSTables, RF, and restore tests. |
| "Having backups without rehearsing leaves RTO unproven." | **True** | RTO is measured only once data and applications are actually serving. |
| "Before a major upgrade, save configs/schemas, data, and rehearse an isolated restore." | **True** | Reduces the risk of locking out the cluster or hitting an impossible rollback. |

## 21. Exercises with Answers

**Exercise 1.** On an RF = 3 cluster, snapshots are taken only from node N1. Can this be considered a complete backup of every partition in the keyspace?

**Answer:** **No.** N1 may hold only a subset of token ranges. You need a backup strategy covering the full node/replica/token set plus data verification.

**Exercise 2.** Snapshots finish at 09:00, an incident hits at 10:00, and required RPO is 10 minutes. Is having only the 09:00 snapshot enough?

**Answer:** **No.** Roughly 60 minutes of mutations could be lost without replay/archival sources or another checkpointing strategy. A 10-minute RPO requires proving recovery up to at least roughly 09:50 in this example.

**Exercise 3.** Why does using the same snapshot tag on N1 and N2 not prove both nodes captured identical data at one instant?

**Answer:** Snapshots execute at distinct local timestamps on each node; replication, flushes, CLs, and concurrent writes cause data to differ. The tag is merely an administrative label.

**Exercise 4.** An operator insists `system_auth` needs no backup because `CREATE TABLE` DDL was exported for all business tables. What is the risk?

**Answer:** Roles/permissions can be lost, locking out logins. Protect auth data with bootstrap/break-glass workflows, while never blindly copying old cluster metadata into a new topology.

**Exercise 5.** Full snapshots use hard links. After a major compaction, `df` usage does not drop. Why?

**Answer:** Snapshots still hold references to old SSTables, preventing disk blocks from being freed even after active SSTables are replaced. Enforce retention and off-cluster exports rather than deleting production snapshots arbitrarily.

**Exercise 6.** A backup file downloaded from object storage passes SHA-256 verification, yet CQL restore lacks sentinel rows. Why did the hash still PASS?

**Answer:** Checksums verify only the bytes of **the selected file**. The backup may belong to the wrong node, miss files/ranges, use the wrong schema, or predate when events were written. Both manifests and logical data checks are needed.

**Exercise 7.** After converting SSTable formats with an upgrade tool, a node running the old binary refuses to boot. Can you revert simply by swapping the package back?

**Answer:** **Never assume so.** Downgrades may not support new formats/schemas; follow version-specific recovery paths and pre-upgrade backups.

**Exercise 8.** Data had a 30-day TTL, was logically exported, and re-imported today with a 30-day TTL. What can go wrong?

**Answer:** Lifetimes get extended from import time, violating original retention. Compute remaining TTL/expiry and preserve delete/tombstone contracts.

**Exercise 9.** A restore rehearsal creates a new cluster but reuses production's seed list and broadcast addresses. What is the risk?

**Answer:** Test nodes can contact or try joining production, disrupting topology/identity and risking data safety. Always **isolate network/cluster identity** and verify before startup.

**Exercise 10.** Import returns exit 0 and `nodetool status` displays `UN`. Is that enough to record `RESTORE_VERIFIED`?

**Answer:** **No.** Check file/token coverage, key/value data, TTLs/deletes, auth/TLS, Java apps, and RPO/RTO.

**Exercise 11.** Why avoid running full-table `SELECT COUNT(*)` across multi-TB tables during peak production load?

**Answer:** Cassandra must scan massive amounts of data/SSTables to count, stressing I/O, CPU, tombstone scans, and risking timeouts. Reconcile in bounded scopes/windows with rate limits.

**Exercise 12.** A team measures 45 minutes to restore and boot nodes, then another 60 minutes until the API serves steadily. Is real RTO 45 or 105 minutes?

**Answer:** By definition, RTO runs **until the service is ready per business criteria**, so elapsed time in this example is roughly **105 minutes** if phases ran sequentially. Never measure RTO solely by process startup.

## 22. Final Checklist: Is Documentation Ready for Change?

~~~text
SCOPE
[ ] Clear RPO/RTO, incident scope, and consistency requirements.
[ ] Release-supported upgrade/downgrade paths documented.
[ ] Source/target Cassandra, JDK, driver, and SSTable/feature compatibility recorded.

CONFIGURATION & SECURITY
[ ] Schema DDL, topology/DC/rack/snitch/RF, seeds, and config versions archived.
[ ] system_auth, roles/permissions, and break-glass safely planned.
[ ] TLS/JMX/secret refs, encryption key lifecycles, and backup IAM verified.

BACKUP
[ ] Snapshots cover exact nodes/keyspaces/tables, tags, timestamps, and token coverage.
[ ] Snapshots exported to an independent fault domain, not just local hard links.
[ ] Component files/checksums/manifests match with zero missing/unknown artifacts.
[ ] If required by RPO: base + incremental + archive/replay chain evidenced.
[ ] Retention/immutability, access controls, and backup job checks pass.

RESTORE REHEARSAL
[ ] Rehearsal cluster truly isolated from production.
[ ] Restore tools and versions match SSTable/schema formats.
[ ] Data, TTLs/deletes, and watermark consistency reconciled.
[ ] CQL/Java canary, RBAC/TLS, RF/CL, replica health, and SLOs pass.
[ ] RPO and RTO measured from an actual restore with action logs.

GO / NO-GO
[ ] Disk headroom, compaction, network/streaming, and repair capacity verified.
[ ] Config rollback, data recovery, and immutable backups ready.
[ ] Owners/approvers, maintenance window, node order, and stop criteria set.
[ ] Any criterion lacking evidence explicitly marked NO-GO/EXCEPTION.
~~~

~~~mermaid
flowchart TD
    A["Prepare Cassandra upgrade"] --> B["Lock RPO/RTO and version matrix"]
    B --> C["Inventory config, schema, system_auth, DC/RF, and secret refs"]
    C --> D["Per-node snapshots + off-cluster backup export"]
    D --> E["Checksums, manifests, incremental/PITR if needed"]
    E --> F["Restore rehearsal on isolated cluster"]
    F --> G["CQL/Java canary, correctness, auth, and RPO/RTO"]
    G --> H{"All criteria evidenced?"}
    H -->|No| I["NO-GO: fix coverage, restore path, capacity"]
    I --> D
    H -->|Yes| J["GO: rolling change per canary, enforce stop criteria"]
    J --> K["Post-check each node/DC, monitor SLOs and recoverability"]
~~~

**Summary:** before changing Cassandra versions or configurations, protect not only **SSTables**, but also **schemas, `system_auth`, topology/DC/RF, runtime configurations, and associated keys/cryptographic material**. Per-node snapshots are great for preserving SSTables, yet they must be **exported to an independent fault domain, checksum/manifest-verified, sized for full replica/token coverage, and tied to a meaningful RPO**. More importantly, an **isolated restore rehearsal** must prove data and applications genuinely work on the supported version—including **TTLs/deletes, permissions, consistency, and p99**. Only then do you have grounds for a **GO** decision; **binary rollback** and **data restore** are distinct paths and must never be conflated once an upgrade alters SSTable formats.
