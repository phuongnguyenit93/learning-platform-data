# Backing Up Replica Sets, Sharded Clusters, and Atlas Services in MongoDB

An order-processing application can lose data through an accidental collection drop, a buggy new release, a flawed migration, disk failure, or loss of an entire infrastructure region. A MongoDB replica set provides high availability when a few members fail, yet **replication is not a backup**: a valid accidental deletion replicates right to the secondaries. Sharding scales storage and throughput, yet does not turn independent shard snapshots into a consistent recovery point. MongoDB Atlas offers managed backups, yet specific capabilities and restore modes depend on tier, cloud provider, deployment region, and backup configuration.

**Backup** is creating a data copy usable for recovery. **Restore** is reconstructing data from that copy, verifying integrity, and bringing the service back online. The mere existence of a backup file does not prove restoration will succeed or meet the business's acceptable data-loss and downtime targets.

This lesson belongs to the **Backup and Recovery** chapter of *Database Engine Document MongoDB*, covering three main areas:

- **Replica sets:** `mongodump`, `--oplog`, `mongorestore --oplogReplay`, physical backups, and storage snapshots.
- **Sharded clusters:** data across shards, config server metadata, balancer, DDL, consistent points, and restore orchestration.
- **MongoDB Atlas:** Cloud Backup snapshots, continuous backup/PITR where supported, backup policies, choosing restore targets, and drills.

Hostnames, paths, and accounts in this lesson are **illustrative placeholders**; restore operations and backup policy changes must only be run in authorized labs/targets. Database Tools, MongoDB Server, Atlas, and cloud platforms have version differences: always verify specific release docs before applying in production.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish replication, backup, snapshot, archive, high availability, and disaster recovery.
2. Define **Recovery Point Objective (RPO)** and **Recovery Time Objective (RTO)**.
3. Compare logical dumps, physical snapshots, and incremental/continuous backups.
4. Use `mongodump --oplog` within proper scope for replica sets and recognize its limits.
5. Restore a full dump into an isolated environment via `mongorestore --oplogReplay`.
6. Understand oplog windows, replication lag, and potential data loss when backing up a secondary.
7. Explain why WiredTiger requires consistent storage/journal snapshots.
8. Plan **cluster-aware** backups for sharded clusters, including config servers.
9. Identify risks of chunk/range migrations, metadata/DDL, and skewed-timestamp snapshots.
10. Distinguish Atlas snapshots and PITR according to tier/configuration capabilities.
11. Pick a pre-incident recovery point and assess its impact on subsequent valid writes.
12. Design retention, encryption, least privilege, backup inventories, auditing, and offsite copies.
13. Verify restores via document counts, indexes, business invariants, and application checks.
14. Build DR runbooks, backup monitoring, and realistic RPO/RTO drills.

## 2. Why Is Replication Not a Backup?

A replica set's primary and secondaries replicate data copies via the oplog. That provides failover when a host or process crashes. Yet if a privileged account runs:

~~~javascript
// Dangerous operation example; NEVER run against real data:
db.orders.deleteMany({})
~~~

secondaries apply that deletion too. Once corrupted state replicates to every member, adding another secondary **does not conjure clean data from yesterday**.

| Incident | How Does a Replica Set Help? | How Does a Backup Help? |
|---|---|---|
| One node crashes abruptly | Can elect a new primary if majority holds | Recovers from broader losses |
| Primary loses its disk | Can continue from a secondary | Protects if all replicas hit the same fault |
| Accidental collection delete | Deletion replicates everywhere | Rolls back to a pre-operation copy |
| Migration updates wrong rows | Bad writes still replicate | Restores a clean snapshot/PITR point |
| Ransomware with admin access | Can compromise all nodes | Independent/immutable backups limit blast radius |
| Entire region outage | Single-region HA may be insufficient | Offsite/cross-region DR recovers service |

**High availability** aims at continuity of service. **Backup/DR** aims at recovering valid data when current state cannot be trusted.

## 3. RPO and RTO Drive the Architecture

### 3.1. RPO: Maximum Permissible Data Loss

RPO specifies the maximum acceptable data loss, usually measured in time. If the latest valid backup sits 24 hours before an outage, up to nearly 24 hours of changes can be lost. For a system requiring a 5-minute RPO, daily snapshots alone fall short unless changes are captured continuously with point-in-time restoration.

### 3.2. RTO: Maximum Permissible Downtime

RTO encompasses detection, decision-making, provisioning the target cluster, transferring data, rebuilding indexes, verification, and traffic cutover. A tool can report "restore completed" while the application still cannot connect due to TLS, roles, or networking.

### 3.3. Classification Example

| Data Tier | Illustrative RPO | Illustrative RTO | Approach to Evaluate |
|---|---:|---:|---|
| Reconstructible reports | 24 hours | 8 hours | Periodic snapshots |
| Order management | 5 minutes | 1 hour | Continuous backup/PITR |
| Critical audit records | Near 0 per policy | 4 hours | Dedicated durability and recovery architecture |

These targets are **illustrative business requirements**, not default MongoDB/Atlas SLAs.

### 3.4. Recovery Scope Must Be Defined Upfront

Are you trying to:

- Recover an entire replica set?
- Recover a sharded cluster to one shared logical point?
- Recover only the `orders` collection?
- Recover just 25 accidentally deleted documents?
- Spin up an isolated cluster for investigation before copying data?

A cluster-wide backup may not allow restoring just a few documents directly. Usually you restore to an isolated environment first and then selectively export/merge.

## 4. Three Major Backup Categories

| Category | How It Is Created | Pros | Limitations |
|---|---|---|---|
| **Logical backup** | Reads documents/index metadata via MongoDB API, e.g., `mongodump` | Portable, easy namespace manipulation, BSON/archive files | Can be slow; needs consistency mechanisms during continuous writes |
| **Physical snapshot** | Snapshots database files/journal at storage layer | Efficient on large datasets; faster restore potential | Requires quiesce/snapshot consistency and version-compatible storage |
| **Managed/continuous backup** | Backup service takes snapshots and captures ongoing changes | Automation, retention, PITR where available | Depends on tier, cost, restore limits, and encryption keys |

### 4.1. Full, Incremental, and Continuous

**Full** captures the entire selected scope. **Incremental** stores deltas relative to a baseline; **continuous** captures changes frequently enough to restore to points within a supported window. Never assume a full logical dump automatically grants week-long PITR.

### 4.2. Backups Are Not CSV Exports

Exporting CSV/JSON helps analytics and data interchange, yet typically drops full BSON types, indexes, users/roles, metadata, or transaction-consistent state. Pick methods for recoverability, not merely file-export convenience.

## 5. Oplog and Point-in-Time Consistency in a Replica Set

A replica set records replication operations in the **oplog** (typically `local.oplog.rs`). Secondaries read and apply these entries. When a dump spans several minutes, the database mutates while collections are scanned.

~~~text
10:00: orders has a PENDING order
10:01: dump reads orders
10:02: transaction flips order to PAID
10:03: transaction inserts payment
10:04: dump reads payments
~~~

If a backup reads two collections at two different instants without establishing a consistent cut, the restored copy can show the order as PENDING while its payment already exists.

### 5.1. Effect of `--oplog`

For an **eligible full backup of a replica set**, `mongodump --oplog` appends oplog entries generated during the dump window so `mongorestore --oplogReplay` can apply them on restore per tool rules. The goal is bringing dumped data to a single consistent point within supported scope.

### 5.2. Oplog Window

The oplog does not retain history forever. Older entries roll off once capacity/retention fills. If a dump runs too long or write volume spikes, required oplog entries can vanish. Monitor oplog window length, dump duration, write rates, and related errors.

### 5.3. Oplog Alone Does Not Equal Long-Term PITR

Restoring from an 01:00 snapshot to 10:35 requires continuously archiving changes from the snapshot through the target point outside the live oplog using a reliable mechanism preserving checkpoints, ordering, and transaction semantics. A single `--oplog` run captures history only for **that dump window**.

## 6. Running `mongodump --oplog` for a Full Replica Set

Self-managed example:

~~~bash
# Run on an authorized replica set. Never embed passwords in URIs.
mongodump \
  --uri="mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017,mongo3.db.internal:27017/?replicaSet=rs0&tls=true" \
  --tlsCAFile=/etc/mongodb/tls/ca-chain.pem \
  --username=backupOperator \
  --authenticationDatabase=admin \
  --oplog \
  --gzip \
  --archive=/backups/rs0-full-2026-11-14.archive.gz
~~~

Explanation:

| Option | Meaning |
|---|---|
| `--uri` | Replica set topology + TLS |
| `--tlsCAFile` | Validates MongoDB endpoint certificates |
| `--username`, `--authenticationDatabase` | Identity holding backup privileges |
| `--oplog` | Captures oplog for the full dump |
| `--gzip` | Compresses output |
| `--archive` | Writes a single archive file instead of multiple files |

### 6.1. Mandatory Limitations to Remember

- `--oplog` applies to a **supported full dump** of a replica set—never combine arbitrarily with `--db`, `--collection`, `--query`, or incompatible filters.
- Never run `mongodump --oplog` through `mongos` and claim a consistent **whole-sharded-cluster** backup.
- Cannot be used on a standalone without a replica set oplog like a replica set.
- Does not grant arbitrary PITR beyond the oplog entries actually captured.
- Does not replace checking tool versions, privileges, output integrity, and restore tests.

### 6.2. Backup Accounts

MongoDB provides the built-in `backup` role for common backup tasks, yet exact privilege needs can vary by namespace, backup mode, and server/tool version. Use dedicated least-privilege accounts; never default to an app `readWrite` user or root admin.

### 6.3. TLS and Secret Protection

Enforce TLS and validate CA/SANs. Never expose real passwords in URIs inside logs, cron jobs, or shell history. Inject credentials via secret managers or interactive prompts per tool support. Archives must also be encrypted and access-controlled: `--gzip` **is not encryption**.

### 6.4. Backup Jobs Must Check Exit Codes

Never treat a non-empty archive file as proof of success. Jobs must record exit codes, secret-redacted stdout/stderr, start/end times, bytes written, offsite upload status, and integrity checksums.

## 7. Backing Up From a Secondary: Pros and Cons

A primary serving writes can suffer elevated CPU/disk/network load during large dumps. Backing up from a secondary or dedicated backup secondary offloads the primary, with trade-offs:

- A secondary may have **replication lag**, so the recovered data point trails the primary's latest state.
- An unstable secondary can undergo rollbacks.
- Backup disk/CPU load can slow secondary oplog application.
- Oplog windows and consistency still require verification.
- Tool/driver read preferences must match topology.

### 7.1. Hidden / Priority-0 Secondary

A dedicated hidden secondary isolates backup reads from app queries when properly designed, yet still needs healthy replication, storage, and monitoring. It is **not an immutable backup**: accidental writes still replicate to it.

### 7.2. Backup Source Checklist

Before running against a member, check `rs.status()`, replication lag, disk capacity, write throughput, and resource utilization. Never lock or restart enough voting members to lose replica set majority.

## 8. Backup Metadata and Manifests

Every good backup includes a job-generated manifest, for example:

~~~yaml
backupId: rs0-20261114-013000
topology: replicaSet
replicaSetName: rs0
sourceMongoVersion: "recorded-by-job"
sourceFCV: "recorded-by-job"
databaseToolsVersion: "recorded-by-job"
method: mongodump-oplog
startedAt: "2026-11-14T01:30:00Z"
completedAt: "2026-11-14T01:48:00Z"
archiveUri: secure-storage/rs0-full-2026-11-14.archive.gz
archiveSizeBytes: "measured"
sha256: "computed"
jobStatus: SUCCEEDED
restoreDrillStatus: PENDING
~~~

These are **sample values**, not real checksums. Backups need unique IDs, clear sources, tool/server versions, timestamps, methods, status, and computed checksums. Manifests should also record storage region, encryption key reference, and retention policy.

### 8.1. Archive SHA-256

Hashes detect archive tampering or corruption after hashing. However, a valid hash **does not prove** the backup holds complete documents or will restore cleanly. Restore drills and business validations remain mandatory.

### 8.2. Offsite Upload

If backups stay on the same database host disk, disk failure or infrastructure loss destroys both source and backup. Replicate to an independent storage location with proper access controls and retention.

## 9. Restoring a Full Dump With `mongorestore --oplogReplay`

Restores should start on a **new, isolated, empty target**, not a live production cluster.

~~~bash
# Run on a verified lab/isolated target; never point at production.
mongorestore \
  --uri="mongodb://restore1.lab.internal:27017/?tls=true" \
  --tlsCAFile=/etc/mongodb/tls/lab-ca.pem \
  --username=restoreOperator \
  --authenticationDatabase=admin \
  --gzip \
  --archive=/backups/rs0-full-2026-11-14.archive.gz \
  --oplogReplay
~~~

`--oplogReplay` reads oplog entries embedded in a `--oplog` backup and applies them per Database Tools mechanics. Use this on a **properly prepared target**, never blindly as a generic "restore any live cluster" command.

### 9.1. Do Not Use `--drop` Unintentionally

`mongorestore --drop` deletes target collections before restoring. That is destructive if the target holds active business writes. In DR drills, prepare clean targets to minimize risk; for populated targets, enforce explicit conflict/overwrite approvals.

### 9.2. Restoring Users/Roles

Backing up and restoring system databases/users/roles requires specific privileges and has tool-option limits. An account with `readWrite` on `shop` generally cannot restore cluster users/roles. Verify required privileges, `authSource`, and metadata rules for your deployment.

### 9.3. Index Rebuilds Are Part of Restore

Logical restores may insert millions of documents and rebuild every index. On large datasets, index builds and I/O consume substantial time; RTO must account for index rebuilds, consistency checks, and application cutover.

### 9.4. Do Not Treat `--oplogReplay` as Full-History Replay

If an archive holds oplog entries from the 01:30–01:48 dump window, restoring at 11:00 will not include events up to 10:35. Further PITR requires continuous backups capturing ongoing changes and timestamped replay capabilities.

## 10. How Does Dumping One Collection Differ From a Full Replica Set Backup?

Example exporting `orders`:

~~~bash
mongodump \
  --uri="mongodb://mongo1.db.internal:27017/?tls=true" \
  --tlsCAFile=/etc/mongodb/tls/ca-chain.pem \
  --username=backupOperator \
  --authenticationDatabase=admin \
  --db=shop \
  --collection=orders \
  --archive=/backups/shop-orders.archive
~~~

Useful for exports, investigations, or collection migrations. Yet you cannot claim `orders`, `payments`, and `inventory` share a consistent transaction point if other collections mutate without synchronization.

### 10.1. When Only a Few Documents Were Accidentally Deleted

A lower-risk approach:

1. Restore a full backup/PITR to a clean timestamp on an isolated target.
2. Extract the exact documents to recover, preserving BSON types and IDs.
3. Compare against live documents (which may have valid post-error updates).
4. Merge under controlled business rules and auditing.

Never roll back all of production with an older snapshot when only a narrow subset is affected and selective recovery is viable.

## 11. Physical Snapshots and WiredTiger

Physical backups copy required database files and the journal at a **storage consistency point**. For WiredTiger, they must honor checkpoint, journaling, locking, and atomic snapshot rules of the storage engine and disk subsystem.

### 11.1. Copying Folders While Writing Is Wrong

~~~text
NEVER treat file-by-file copying of live changing files:
cp -r /var/lib/mongodb /backup
as a consistent physical snapshot.
~~~

Files get copied at different instants while WiredTiger metadata and the journal mutate concurrently. Valid snapshots require consistency across **all relevant volumes and files**.

### 11.2. Conceptual Workflow

1. Select an eligible member and inspect replication lag/health.
2. Verify storage backend support for atomic/coordinated snapshots.
3. Use the checkpoint/fsync/freeze procedure recommended by MongoDB + your storage vendor for your version.
4. Snapshot all data and journal volumes at the same point.
5. Release the freeze/lock per runbook.
6. Export/copy the snapshot to independent storage; compute checksums/metadata.
7. Test-restore on the matching version and validate recovery.

### 11.3. `fsyncLock` Does Not Replace Snapshots

Some procedures use commands like:

~~~javascript
// Illustrative admin API only. Do not run arbitrarily on production.
db.fsyncLock()
// Take storage snapshot per approved runbook.
db.fsyncUnlock()
~~~

Locking impacts writes and replication. It does not create a backup by itself, nor guarantee consistency across multiple volumes or multiple shards. Never apply this pattern across a sharded cluster without proper coordination.

### 11.4. Crash-Consistent Differs From Business-Consistent

A snapshot may recover cleanly at the storage engine level while business steps involving Kafka, object storage, or another database sit at different timestamps. Application backups must account for cross-service dependencies.

## 12. RPO of Secondary Snapshots

Example:

~~~text
Primary has writes up to:        10:30
Secondary has applied up to:    10:24
Secondary storage snapshot at:  10:26
~~~

A secondary snapshot taken at 10:26 **does not mean** it holds every primary write up to 10:26. Its effective point depends on how far the secondary applied the oplog. For tight RPOs, measure lag plus backup pipeline latency.

### 12.1. Rollbacks and Majority Commit

Writes not yet acknowledged as durable per write concern can roll back after an election. RPO analysis must account for client-acknowledged writes and write concern policy, not merely primary wall-clock time.

### 12.2. Backup Nodes Affect Availability

When locking or restarting a voting secondary, preserve majority quorum. Avoid actions that leave the replica set unable to elect a primary or cause prolonged replication lag.

## 13. When to Choose Logical vs. Physical for a Replica Set?

| Workload | Logical Dump | Physical Snapshot |
|---|---|---|
| A few GB, need to export specific collections | Convenient | Often unnecessarily complex |
| Multiple TB, short RTO | Likely too slow | Usually worth evaluating |
| Need human-inspectable BSON/metadata | Advantageous | Stored in storage-engine format |
| Need exact source storage state | Not physical format | Fits within version/storage constraints |
| Heavy writes requiring a consistent point | Needs `--oplog`/supported workflow | Needs proper snapshot mechanism |
| Sharded cluster | Insufficient cluster consistency alone | Requires cluster-level coordination |

No single method is universally optimal. Evaluate dataset size, backup duration, oplog window, CPU/disk budgets, restore targets, and tooling.

## 14. Why Are Sharded Clusters Harder to Back Up?

A sharded cluster contains:

- **Multiple shard replica sets** holding user data.
- **Config Server Replica Set (CSRS)** holding catalog/sharding metadata.
- **`mongos` routers** relying on metadata to route queries.
- **Balancer, chunk/range migrations, and DDL** shifting ownership while live.

~~~mermaid
flowchart TD
    App["Application"] --> Router["mongos"]
    Router --> Config["Config Server Replica Set"]
    Router --> ShardA["Shard A Replica Set"]
    Router --> ShardB["Shard B Replica Set"]
    Router --> ShardC["Shard C Replica Set"]
    Config -.-> Metadata["Routing/chunk ranges/catalog metadata"]
    ShardA -.-> Data["User data and indexes"]
    ShardB -.-> Data
    ShardC -.-> Data
~~~

### 14.1. How Dangerous Are Skewed Snapshot Times?

~~~text
10:00 Snapshot Shard A
10:02 Balancer moves range R from A to B
10:04 Snapshot Shard B
10:05 Snapshot Config Server
~~~

These captures may not belong to **any single logical cluster state**. Ranges can be missing or duplicated, or metadata may assign a range to a different shard than where data was captured. Grouping files by similar timestamps does not create consistency.

### 14.2. Config Metadata Is Essential Data

Config servers store sharded namespaces, shard keys/ranges, catalog state, and coordination metadata. You cannot back up user documents on shards alone and reconstruct routing metadata by guessing.

### 14.3. "Synced Clocks" Are Not Enough

Triggering volume snapshots nearly simultaneously via NTP does not establish a **cluster-wide logical consistency point**. Transactions, DDL commits, and migrations require dedicated coordination tooling.

## 15. Do Not Stitch Per-Shard `mongodump` Outputs Manually

A flawed strategy:

~~~text
Dump Shard A at 10:00
Dump Shard B at 10:20
Dump Config at 10:40
Copy everything into one folder named backup-full
~~~

This fails to guarantee consistency, especially under live writes and active balancing.

### 15.1. `mongodump --oplog` Through `mongos` Is Not a Solution

Database Tools `--oplog` has topology limits and **is not a cluster-wide snapshot via `mongos`**. Never dump from a router and advertise RPO/consistency equal to a sharded-aware managed backup.

### 15.2. Each Shard Has Its Own Oplog

Oplogs on Shard A and Shard B do not natively explain how to replay metadata changes, cross-shard transactions, and migration events into one unified cluster state. Sharded backup engines coordinate timestamps and metadata explicitly.

### 15.3. Stopping the Balancer Is Not Enough

`sh.stopBalancer()` may be one step in a supported workflow, yet:

- Write traffic can still continue.
- Active migrations might still be finishing.
- DDL, resharding, or manual migrations can still occur.
- Config metadata and shard datasets still require coordinated snapshots.

Never use "balancer stopped" as the sole criterion for backup consistency.

## 16. Cluster-Aware Solutions for Sharded Backups

Prioritize methods that understand topology and consistent points:

1. **MongoDB Atlas Cloud Backup** when hosted on Atlas with supporting tiers/configuration.
2. **MongoDB Ops Manager/Cloud Manager or specialized MongoDB backup tools** matching version, licensing, and topology.
3. **Cluster-coordinated storage snapshots** following documented/vendor-validated runbooks.
4. **Logical exports via `mongos`** for bounded data extraction/migration tasks, never mistaken for cluster-wide DR backups.

### 16.1. Elements Requiring Coordination

| Component | What Must Be Preserved/Coordinated? |
|---|---|
| Shard replica sets | Data and indexes at the consistent point |
| Config server replica set | Matching catalog/ranges/ownership |
| Balancer/migrations | No half-completed migration states |
| DDL/resharding | No inconsistent schema/routing changes mid-backup |
| Cross-shard transactions | Consistent commit point |
| Backup manifest | IDs, timestamps, versions, and checksums |

### 16.2. Do Not Present Manual Commands as a Universal Fix

Sharded backups are sensitive to version and topology. A short shell script running `fsyncLock` on each `mongod` does not establish full consistency guarantees. Use officially documented solutions, test restores on isolated clusters, and keep a rollback plan.

## 17. Restoring a Sharded Cluster

Conceptual diagram:

~~~mermaid
flowchart TD
    Backup["Cluster-aware backup with consistent point"] --> Target["Prepare isolated target"]
    Target --> Restore["Backup engine restores shards + config metadata"]
    Restore --> Router["Initialize/verify mongos routing"]
    Router --> Verify["Verify ranges, indexes, transactions, and app"]
    Verify --> Gate{"Meets business invariants and RTO?"}
    Gate -->|"No"| Fix["Investigate; do not switch traffic"]
    Gate -->|"Yes"| Cutover["Controlled cutover per change plan"]
~~~

Actual restore ordering is governed by the **supported tooling**; the diagram is not a license to restore config servers before or after shards manually.

### 17.1. Never Hand-Edit Config Collections

If metadata mismatches shard data, never run manual `updateOne` calls on config server collections to "fix" routing. That metadata is MongoDB-managed, and manual edits can worsen corruption. Resolve through supported backup engines and runbooks.

### 17.2. Pick a Clean Target

Restoring snapshots over a cluster holding live production data causes `_id`, metadata, and ownership conflicts. For drills, prefer a fresh/isolated target and validate topology carefully.

### 17.3. Verify Cross-Shard Operations

A cluster can report healthy routers while one shard has broken ranges. Post-restore checks must run queries across multiple shard key values and test sample multi-shard transactions—never check only the first shard.

## 18. Atlas Backup: Managed Yet Still Requires Policy Choices

**MongoDB Atlas** provides backup features depending on cluster tier and cloud deployment:

- **Cloud Backup snapshots** to restore copies at scheduled/on-demand points.
- **Continuous Cloud Backup/PITR**, when enabled/supported, to choose points within the retention window.
- **Backup policies/retention**, adjustable in frequency and retention by plan.
- **Restore workflows** to eligible target clusters via UI, API, or CLI per feature support.

**Never assume** every Free, Flex, or Dedicated cluster, every cloud/region, or every Atlas plan offers identical backups, snapshot downloads, PITR, or cross-region restores. Verify **your specific cluster's** capabilities and account policies.

### 18.1. An Atlas Replica Set Does Not Replace Cloud Backup

Atlas manages high availability via replica sets, which is replication—not historical snapshots. Check the dedicated Backup tab to verify recovery capability after accidental deletions.

### 18.2. Managed Does Not Absolve Operations Teams of Responsibility

Atlas automates much of the plumbing, yet application teams still own choosing RPO/RTO, retention, restore permissions, KMS access, running drills, verifying business logic, and executing safe cutovers.

## 19. Conceptual Atlas Snapshot Workflow

1. Confirm the exact **organization, project, and cluster**.
2. Open Backup/Snapshots in the current Atlas UI.
3. Verify enabled features, schedules, retention, region, and cost.
4. Locate the desired backup ID/snapshot timestamp.
5. Where tier-supported, take an on-demand snapshot before risky migrations.
6. Wait until the snapshot reaches **available/completed** state per service status.
7. Test-restore to another cluster and validate data.

### 19.1. Click Time Is Not the Restore Point

If you request a snapshot at 09:00 and the job completes at 09:12, read the **snapshot timestamp/consistent point** reported by the service; do not infer the restore point from when the button was clicked.

### 19.2. Retention Affects Delayed Bug Recovery

If faulty writes occurred silently for 40 days while snapshots are kept only 14 days, every remaining snapshot already holds corrupted data. Base retention on **incident detection windows**, not just backup frequency.

### 19.3. Snapshot Downloads Are Not Always Available

Downloading snapshots locally, cross-cloud restores, and export options vary by tier, cloud, and version. Some workflows restore directly into another Atlas target. Never promise a downloadable `.archive` file for every cloud backup.

## 20. Atlas Continuous Cloud Backup/PITR

When supported and enabled beforehand, continuous backup captures changes between snapshots so you can pick a restore point inside the **restorable window**.

~~~text
02:00 Base snapshot
02:00–10:35 Backup service captures changes per policy
10:35:20 Accidental delete begins
10:35:19 Desired recovery point, prior to bad operation
10:40 Team detects the incident
~~~

### 20.1. Prerequisites

- Tier/cloud/region and config support PITR.
- Continuous backup **was enabled prior to** the fault.
- Base snapshots and change history remain within retention/restorable window.
- Permissions allow restoring to the chosen point.
- Target has sufficient capacity, version/config compatibility, and privileges.

### 20.2. Enabling PITR After an Incident Creates No History

If continuous backup was disabled when the accidental delete occurred, turning it on afterward cannot recover oplog/backup history the service never captured.

### 20.3. Use UTC Timestamps

Record absolute timestamps such as `2026-11-14T10:35:19Z`. Correlate app logs, audit logs, operation start times, and Atlas's displayed restorable range. Local UI timezones may differ from UTC.

### 20.4. Cluster-Wide PITR Has Trade-Offs

Selecting a state before an accidental delete also excludes **valid** writes committed after the restore point from the restored target. When blast radius is small, restoring into an isolated cluster, extracting missing records, and merging safely avoids discarding good writes.

## 21. Atlas Restore: Choosing Targets and Controlling Change

Typical workflow:

1. Record the incident, source cluster, and clean data timestamp.
2. Check available snapshot/PITR ranges.
3. Choose a **new, isolated target** or existing target per authorization and risk level.
4. Verify project, cluster IDs, MongoDB version, FCV, topology, cloud/region, disk, and KMS.
5. Ensure the operator holds restore privileges and change approval if touching production.
6. Submit the restore request and monitor job state and logs.
7. Verify data, indexes, users/roles, TLS/network connectivity, and app behavior.
8. Execute cutover only if operational readiness criteria pass.

### 21.1. Restoring to a New Target

This is safest for investigation because production stays untouched; you can diff live vs. snapshot data, run smoke tests, and copy selectively. Account for extra cluster cost and restrict access to production data restored into staging.

### 21.2. Overwriting an Existing Cluster

Can replace target data, cause downtime, or corrupt live records. Never pick it casually just because the UI button exists. Require change approval, a backup of current target state, and a rollback/cutover plan.

### 21.3. Multiple Clusters in One Project

To avoid confusing staging with production, record `sourceProjectId`, `sourceClusterId`, `snapshotId`/PITR timestamp, `targetProjectId`, and `targetClusterId` in the change ticket. For destructive actions, enforce four-eyes approval if policy requires.

### 21.4. Targets Do Not Inherit Everything Automatically

Network access/IP allowlists, Private Endpoints, connection strings, users/roles, KMS, target backup policies, and app configs may need reconfiguration depending on restore mode. Restored data alone does not mean traffic readiness.

## 22. Atlas UI, CLI/API, and Permissions

Atlas exposes multiple control surfaces; exact steps and action names vary by version/plan. Automation should:

- Use API/service accounts with least-privilege permissions.
- Never store API keys in source code or logs.
- Specify exact backup/restore IDs and support safe retries/idempotency.
- Monitor job status and prevent retrying a destructive restore onto the wrong target.
- Keep audit trails: requester, source/target, timestamp, and outcome.

### 22.1. Backup Permissions Differ From Restore Permissions

Someone allowed to inspect snapshots does not automatically need rights to overwrite data. Separate backup operators, restore operators, and reviewers/approvers using Atlas project/org roles; these role names are **illustrative business roles**, not necessarily literal Atlas built-in role names.

### 22.2. Billing Policies

Backup storage, PITR retention, on-demand snapshots, cross-region copies, restored cluster compute, and egress all incur charges. Choose policies balancing recovery targets against budget and quotas.

## 23. Atlas KMS and Backup Decryption Readiness

If your organization uses customer-managed encryption keys or KMS integration, backup/restore depends on key accessibility.

- Retain key references/rotation history per policy.
- Never disable or delete older keys while backups within retention still depend on them.
- Verify KMS IAM permissions for restore workflows and target regions.
- Drill scenarios where the primary account loses access yet backups must still recover.
- Separate KMS key-deletion rights from backup-management rights where needed.

A snapshot visible in the UI **is not guaranteed decryptable** if its required key was deleted or permissions were revoked.

## 24. Retention Policies and Independent Copies

A system might configure:

| Backup Type | Example Frequency | Example Retention | Role |
|---|---|---|---|
| Daily snapshot | Daily | 7–30 days | Recovering early-detected errors |
| Weekly snapshot | Weekly | 4–12 weeks | Recovering delayed-detection errors |
| Monthly/archive | Monthly | 6–24 months | Long-term obligations where appropriate |
| Continuous/PITR | Managed by service | Provisioned restorable window | Low RPO |

These are **policy examples**, not fixed Atlas frequencies/retentions. Balance RPO, detection windows, cost, legal holds, and personal data privacy regulations.

### 24.1. 3-2-1 and Immutable Backups

A common strategy maintains multiple copies across distinct environments/locations, including an offsite copy and, for ransomware defense, an **immutable/air-gapped** copy where storage supports it. Replica set members do not count as independent backups: they replicate accidental deletions together.

### 24.2. Separating Backup Deletion Privileges

Never grant backup-deletion privileges to the application database account. Protect backup storage with separate IAM, MFA, object retention/locks where supported, auditing, and reviews on retention changes.

### 24.3. Sensitive Data Inside Copies

Backups contain PII, internal records, logs, and stored credentials/keys. Enforce encryption at rest, TLS in transit, least-privilege access, and retention-driven purging. When restoring to staging, prevent broad exposure of real data.

## 25. Backups Must Align With System-Wide Disaster Recovery

A product might combine:

~~~text
MongoDB: Orders, Payments, and Users
Kafka: Event stream
Object storage: Images and invoice PDFs
Search engine: Search indexes
Identity provider: Users/SSO
KMS: Data encryption keys
~~~

MongoDB snapshots **do not automatically back up** Kafka event logs, object files, search indexes, IAM/KMS, or app configurations. Search indexes can be rebuilt if source data exists, whereas binary files lost from object storage will not reappear from MongoDB pointers.

### 25.1. Cross-System Consistency

If an order committed in MongoDB while its Kafka publish never fired, MongoDB backup/restore alone does not fix delivery semantics. Use outbox/inbox patterns, idempotent consumers, or post-recovery reconciliation workflows.

### 25.2. Dependency Recovery Plan

Runbooks must specify service startup order, when to resume consumers, event reprocessing, invoice reconciliation, traffic opening, and duplicate side-effect prevention.

## 26. Restore Verification Steps

A restore is accepted only when:

1. Backup, source, and timestamp match expectations.
2. Restore job completes with zero unhandled errors.
3. Database, collection, and index counts make sense.
4. Document counts, ID ranges, and sample hashes/invariants match the restore point.
5. Users/roles, TLS, networking, and KMS work.
6. Replica set/sharded cluster topology is healthy.
7. Application smoke tests pass.
8. Actual RPO/RTO are recorded.

### 26.1. Verifying a Replica Set Target

~~~javascript
// Run only on an authorized test target.
rs.status()
db.adminCommand({ ping: 1 })
db.getSiblingDB("shop").orders.countDocuments({})
db.getSiblingDB("shop").orders.getIndexes()
~~~

A healthy `rs.status()` does not prove documents restored properly; an empty cluster is also healthy.

### 26.2. Verifying a Sharded Cluster Target

~~~javascript
// Run via mongos on the restored cluster with proper privileges.
sh.status()
db.adminCommand({ ping: 1 })
~~~

Check shard keys/ranges, config metadata, query routing across multiple shard key values, indexes, and cross-shard transactions. Never query just one shard and declare the whole cluster OK.

### 26.3. Business Invariants

Examples:

~~~text
Every PAID order must have a valid payment.
Total payments must match order totals per rules.
Every invoice reference must point to an existing object.
Inventory movements must match fulfilled orders.
~~~

Correct document counts are not enough: an inconsistent backup can have exact counts while cross-collection links are broken.

## 27. Verifying Source, Target, and Timestamp

Before restoring, record explicitly:

~~~yaml
incidentId: INC-2026-001
sourceCluster: mongo-prod-rs0
sourceTopology: replicaSet
backupId: rs0-20261114-013000
restoreTimestampUtc: "2026-11-14T01:48:00Z"
targetCluster: mongo-restore-isolated
targetEnvironment: recovery-lab
requestedBy: incident-operator
approvedBy: change-approver
restoreStatus: PENDING
~~~

Values are **illustrative**. A destructive restore aimed at the wrong target causes a fresh outage; verify immutable target IDs, environment, and state before executing.

### 27.1. Pick a Clean Backup, Not Just the Latest One

If a faulty migration ran at 09:00 while the newest backup is from 10:00, that backup already holds corrupted data. Inspect audit/application logs to choose a recovery point prior to the fault.

### 27.2. UTC Timestamps and Precision

Record absolute timestamps rather than timezone-less phrases like "9 AM yesterday." For PITR near transaction boundaries, cross-check log events, clock accuracy, and the tool's supported restorable range.

## 28. Monitoring Backup Jobs

| Metric/Signal | Meaning |
|---|---|
| Last successful backup age | Does the newest backup still meet SLA? |
| Backup duration | Is the job exceeding the oplog window or backup window? |
| Backup exit code | Were errors silently ignored? |
| Backup size delta | Missing namespaces or abnormal data shrinkage? |
| Checksum/integrity result | Was the archive altered? |
| Restore drill success | Is the backup actually usable? |
| Actual RPO/RTO | Are business objectives met? |
| Secondary replication lag | Is the snapshot source too stale? |
| Oplog window | Enough history for backup/PITR methods? |
| Atlas snapshot/PITR status | Is the service enabled and healthy? |
| Retention remaining | Are critical backups about to expire? |
| KMS key access | Can restores still decrypt? |

Metric names are **illustrative monitoring suggestions**, not built-in names exported identically by MongoDB. Combine signals from cron/job runners, Atlas, cluster health, storage, and DR drill logs.

### 28.1. Empty Backup Files

A job can write a tiny file due to connecting to the wrong DB, missing privileges, or wrong filters. Check logs, archive manifests, expected sizes/namespaces, and test restores—never rely solely on "file exists."

### 28.2. Alerting When PITR Is Disabled

If a tight RPO relies on continuous backups, monitor that the feature stays enabled and the **restorable window** meets targets. Policy or tier changes can silently degrade recoverability.

## 29. Measuring RPO and RTO in an Incident

~~~text
Incident begins:             10:37
Clean restore point:         10:30
DB restore finishes:         11:25
Application resumes service: 11:42
~~~

In this example:

- Data between 10:30 and the 10:37 incident may be absent from the target: **7 minutes** on the timeline.
- From 10:37 to 11:42: **65 minutes** of service recovery.

Against a 5-minute RPO and 60-minute RTO target, both **missed**. Completing the DB restore at 11:25 does not change end-to-end service RTO ending at 11:42.

### 29.1. RTO Is More Than Copying Bytes

~~~text
Detection + decision + provisioning + restore/index builds
          + verification + credentials/network + cutover + smoke tests
~~~

Contingency plans must measure this entire chain.

## 30. DR Drill Procedure

A drill can follow these steps:

1. Pick a real snapshot/backup inside retention.
2. Provision an isolated target with matching compute/storage/version.
3. Restore fully per runbook without touching production.
4. Check restore status, collections, indexes, and transaction invariants.
5. Run the application against the target with safe test traffic/data.
6. Measure recovery point, RTO, resource usage, and cost.
7. Verify users/roles, TLS/KMS/networking.
8. Log defects, action items, and owners.
9. Decommission the target per policy upon completion.

**Reading a runbook** or running `mongodump --version` does not count as a restore drill.

### 30.1. Scenarios to Rehearse

- Accidental collection deletion.
- Entire replica set outage.
- Restoring prior to a faulty migration.
- Major shard or config server failure.
- Full region loss.
- Expired backup or revoked KMS key.
- Atlas project or network configuration changes.

Each scenario needs its own RPO/RTO targets and approval path.

## 31. Minimum DR Runbook

~~~text
1. Incident trigger and accountable owner
2. Source cluster ID, topology, version, FCV
3. Target RPO/RTO and clean data timestamp
4. Backup inventory + snapshot/oplog ID
5. Backup/restore privileges, secrets/KMS
6. Isolated target, networking/TLS, and resources
7. Verified commands or Atlas restore workflow
8. Job monitoring and failed-state handling
9. Validation: counts, indexes, invariants, application
10. Cutover and handling writes created after the restore point
11. Rollback/fallback if cutover fails
12. Audit and retrospective
~~~

The runbook must hold enough detail for another operator to execute accurately without relying on the script author's memory.

## 32. Backups and Performance Cost

### 32.1. Large Logical Dumps

Dumps scan collections, consuming disk reads, network bandwidth, and compression CPU. On a primary, this affects write latency; on a secondary, it slows replication application. Budget timing, concurrency, and resources carefully.

### 32.2. Compression

`--gzip` shrinks storage and transfer bytes in many cases at the cost of CPU. On already compressed payloads, savings may be modest. Benchmark on real datasets.

### 32.3. Index Rebuilds

Restoring large logical datasets can spend substantial time rebuilding indexes even if BSON loads fast. Reserve sufficient disk headroom and account for unique-index failures on dirty data.

### 32.4. Sharded Backups

Cluster-aware backups coordinate metadata and multiple sources, adding I/O across shards. When snapshotting per node, factor in aggregate throughput, networking, storage capacity, and impact on the balancer and app.

### 32.5. Atlas Restores

Target tier/cluster choice, bandwidth, and resource allocation affect restore duration. A fast backup does not prove a short DR RTO; only **real drills** measure it.

## 33. Common Errors and Scenarios

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `mongodump` permission denied | Backup user lacks privileges | Grant appropriate role/scope |
| TLS handshake failed | Wrong CA/SAN or expired cert | Fix certificate/trust/hostname |
| Abnormally tiny archive | Wrong URI/filter or failed job | Check exit codes and manifests |
| `--oplog` fails with `--collection` | Incompatible option combination | Use full scope or another tool |
| `--oplog` via `mongos` errors | Wrong topology for oplog dump | Use cluster-aware backup |
| Insufficient oplog | Short window, high write rate | Adjust method or oplog capacity |
| Restore duplicate keys | Unclean target or data/index conflict | Restore isolated; review policy |
| Missing indexes after restore | Wrong scope/options/metadata | Inspect restore logs and indexes |
| Snapshot boots yet data is skewed | Inconsistent files/volumes | Use supported snapshot procedure |
| Sharded restore has wrong ranges | Metadata/data from different logical points | Use cluster-consistent backup |
| Atlas PITR missing | Tier/config/retention unsupported | Verify actual cluster capabilities |
| Restore fails to decrypt | KMS key/permissions lost | Restore key access per policy |
| App errors after restore | Users/roles/TLS/network/schema mismatch | Run smoke tests and readiness checklist |
| Backup expired | Inadequate retention | Update retention policy and archives |
| Restore RTO breaches SLA | Data volume, index builds, slow provisioning | Drill and optimize resources/architecture |

## 34. Anti-Patterns to Avoid

1. **Treating replication as backup.** Accidental deletes replicate too.
2. **Having backups never test-restored.** You do not know if recovery works.
3. **Stitching per-shard snapshots from different timestamps.** Breaks cluster consistency.
4. **Running `mongodump --oplog` via `mongos` as a cluster-wide backup.** Wrong scope.
5. **Stopping only the balancer and calling a sharded backup consistent.** Writes, DDL, and migrations still matter.
6. **Testing restores against live production.** Risks wiping or overwriting data.
7. **Enabling PITR after an incident expecting past history.** Uncaptured changes cannot be replayed.
8. **Believing gzip equals encryption.** Does not protect data from file readers.
9. **Storing passwords/backup credentials in public scripts.** Easily leaked.
10. **Failing to retain KMS keys long enough.** Renders encrypted backups unreadable.
11. **Retention shorter than detection windows.** Every remaining backup already contains the bug.
12. **Excluding application readiness from RTO.** Timing the restore command alone is insufficient.
13. **Copying live WiredTiger files without snapshot consistency.** Risks storage corruption.
14. **Skipping backups of external dependencies.** MongoDB lives while the app stays broken.
15. **Not alerting on failed backup jobs.** You may go days without a fresh backup.

## 35. Lab A — Choosing a Backup for a Replica Set

A 3-node replica set holds 30 GiB of data, 15 GiB of indexes, with RPO = 24 hours and RTO = 4 hours. Do the following:

1. Recommend logical dump or physical snapshot, analyzing cost and restore speed.
2. Determine whether `--oplog` is required while writes continue during the dump.
3. If backing up from a secondary, what must you check regarding lag and oplog window?
4. Design the manifest, checksum, and offsite retention.
5. Outline the restore drill steps.

## 36. Lab B — Spotting an Invalid Command

~~~bash
mongodump \
  --uri="mongodb://mongo1.db.internal:27017/?replicaSet=rs0&tls=true" \
  --tlsCAFile=/etc/mongodb/tls/ca-chain.pem \
  --username=backupOperator \
  --authenticationDatabase=admin \
  --db=shop \
  --collection=orders \
  --oplog \
  --archive=/backups/orders.archive
~~~

Why is combining `--oplog` with collection scoping problematic? If exporting only `orders`, can you guarantee `payments`/`inventory` align at the same point in time? What approach gives a consistent full replica set backup?

## 37. Lab C — Controlled Restore

Suppose you have a full dump archive with oplog. Design a practice exercise:

- Provision a new isolated target.
- Verify checksum and tool/server compatibility.
- Run `mongorestore --oplogReplay`.
- Check `rs.status()`, counts, indexes, and orders/payments invariants.
- Measure RPO/RTO.
- Keep production traffic blocked until validation finishes.

Explain why `--drop` must not be used on a populated production target.

## 38. Lab D — Replica Set Secondary Lag

~~~text
Primary writes reached 10:30
Secondary applied oplog only up to 10:24
Secondary snapshot taken at 10:26
~~~

Which writes might the snapshot lack? Can you call this a backup up to 10:26 in primary time? How would you achieve an RPO under 5 minutes?

## 39. Lab E — Sharded Range Migration

~~~text
Snapshot Shard A: 10:00
Balancer moves range R: 10:02
Snapshot Shard B: 10:04
Snapshot CSRS:    10:05
~~~

Explain how data can be missing/duplicated or metadata misaligned after restore. Why is stopping the balancer alone insufficient? Which components must backup tooling understand?

## 40. Lab F — Atlas PITR

Suppose an Atlas cluster **has PITR enabled** with a 48-hour recovery window (exercise assumption). An accidental deletion starts at `2026-11-14T10:15:20Z` and is detected at 10:20. Do the following:

1. Choose a safe restore point prior to the bad operation.
2. Explain how to confirm the timestamp via logs/audits.
3. Explain why restoring to an isolated cluster is preferred.
4. State the impact on valid writes if restoring the entire cluster back to the older point.
5. Give scenarios where PITR is unavailable despite using an Atlas cluster.

## 41. Lab G — Calculating RPO/RTO

Incident at 10:37, clean restore point at 10:30, application back online at 11:42. Calculate actual RPO and RTO in this scenario. Against targets of RPO = 5 minutes and RTO = 60 minutes, were the objectives met?

## 42. Lab H — KMS and Retention

An organization keeps monthly backups for 12 months yet deletes the KMS key encrypting them after 30 days. What happens when trying to restore month six? Design a key rotation/retention policy.

## 43. Lab I — Multi-Service Architecture

An application stores orders in MongoDB, invoice PDFs in object storage, and events in Kafka. After restoring MongoDB 20 minutes back before an outage, which components must be reconciled to prevent missing invoices, duplicate events, or mismatched order states?

## 44. Lab J — Audit and Approval

Draft a DR request ticket covering source project/cluster, backup ID/timestamp, target cluster, approver, permission policies, KMS/TLS configs, validation steps, and cutover criteria. Explain how to prevent accidentally picking staging as source and overwriting production as target.

## 45. Lab K — Correct Document Counts Yet Wrong Business State

After restore, `orders.countDocuments({})` matches, yet a PAID order lacks a payment record. Propose how to investigate inconsistent dump points, cross-collection transactions, restore scope, and application logic. Should the system be declared recovered immediately?

## 46. Suggested Exercise Answers

**A:** A full logical dump can suffice for 30 GiB if measured backup/restore meets RTO; evaluate physical snapshots if I/O or index rebuilds take too long. With continuous writes, use full `--oplog` where supported. Verify lag, oplog, offsite copies, and restore drills.

**B:** `--oplog` is incompatible with arbitrary `--db`/`--collection` filters; exporting only `orders` does not guarantee consistency with `payments`. Use a full replica set backup with oplog or a consistent snapshot method.

**C:** Restore to an isolated target; never run `--drop` on production. Validate data/indexes/invariants; archive checksums do not replace test restores.

**D:** The secondary lacks writes after 10:24 even though snapshotted at 10:26. Measure lag, select a source/method matching RPO, and monitor continuously.

**E:** Range R changed ownership between snapshots, leaving metadata and data misaligned. Cluster-aware backup coordination covering CSRS, shards, DDL, and migrations is required.

**F:** Pick a timestamp before 10:15:20Z inside the restorable window after audit verification. Restore isolated to recover selectively without losing good writes. If PITR wasn't enabled beforehand, isn't supported on the tier, or exceeds retention, that point is unavailable.

**G:** Data-loss gap = 7 minutes; service outage = 65 minutes. Both the 5-minute RPO and 60-minute RTO were missed.

**H:** Once the old key is destroyed, encrypted backups become unreadable. Retain key access throughout backup lifetime or re-encrypt per supported procedures.

**I:** MongoDB snapshots do not restore object files or Kafka offsets. Verify external backups, event replay/idempotency/outbox handling, and invoice references.

**J:** Record immutable identifiers, require approvals, and verify target IDs explicitly rather than relying on display names. Pick a fresh target to avoid destroying production.

**K:** Counts do not guarantee invariants. Inspect backup consistency points, transaction states, and payment data; keep traffic blocked while business state is broken.

## 47. Review Questions

**1. Does a replica set need backups?** — Yes, because bad writes and accidental deletes replicate too.

**2. What is RPO?** — Maximum acceptable data loss, typically measured in time.

**3. What is RTO?** — Maximum acceptable time to restore service availability.

**4. What kind of backup is `mongodump`?** — Logical.

**5. What does `mongodump --oplog` do?** — Captures oplog entries during a full replica set dump to support consistent replay.

**6. Can `--oplog` be used on an arbitrary single collection?** — No; the tool enforces scope and flag compatibility limits.

**7. Can `--oplog` through `mongos` back up an entire sharded cluster?** — No; it is not a cluster-wide consistent method.

**8. Is `mongorestore --oplogReplay` arbitrary PITR?** — No; it only replays oplog entries captured in a qualifying dump.

**9. Is the oplog kept forever?** — No; older entries roll over.

**10. Is a secondary snapshot always up to date?** — No; it may lag behind the primary.

**11. Is copying a live WiredTiger folder a safe snapshot?** — No; storage/journal consistency is required.

**12. Why do sharded backups need config servers?** — They hold the sharding catalog and routing metadata.

**13. Do per-shard snapshots at different times guarantee consistency?** — No.

**14. Is stopping the balancer enough for sharded cluster backups?** — No; writes, DDL, transactions, and metadata still require coordination.

**15. Does Atlas offer Cloud Backup/PITR on every tier?** — No; availability depends on tier, cloud, region, and configuration.

**16. Must PITR be enabled before an incident?** — Yes; change history must already be captured within the restorable window.

**17. Do daily snapshots automatically meet a 5-minute RPO?** — No, without continuous change capture.

**18. Why prefer restoring to a new cluster?** — Reduces overwrite risk and supports diffing/selective merging.

**19. How is `--drop` dangerous?** — It deletes target collections before restoring.

**20. If an archive's SHA-256 matches, is restore guaranteed OK?** — No; data completeness, compatibility, and business invariants still matter.

**21. What happens if a KMS key is deleted?** — Encrypted backups can become undecryptable.

**22. Does RTO include application cutover?** — Yes, not just database byte copying.

**23. Can cluster-wide PITR lose good writes?** — Yes; changes after the chosen restore point are absent from the restored target.

**24. Do backups need TLS, encryption, and access control?** — Yes; they hold production-grade sensitive data.

**25. What should a DR drill do?** — Run a real restore on an isolated target, verify data/app, measure RPO/RTO, and refine the runbook.

## 48. Quick Reference Table

| Requirement | Approach / Key Point |
|---|---|
| Full logical replica set backup | `mongodump` |
| Oplog while dumping active writes | `mongodump --oplog` with supported full scope |
| Restoring a dump with oplog | `mongorestore --oplogReplay` on an isolated target |
| Physical backup | Consistent storage snapshot per WiredTiger/journal rules |
| Secondary backup | Monitor lag and oplog window |
| Sharded backup | Cluster-aware tool coordinating shards and CSRS |
| Never do | Stitch per-shard snapshots from different logical points |
| Atlas snapshot | Cloud Backup where tier/config supports it |
| Atlas PITR | Pre-enabled continuous backup + restorable window |
| Lost subset of documents | Restore isolated + selective merge |
| RPO | Maximum permissible data loss |
| RTO | Maximum permissible service outage duration |
| Backup security | TLS, encryption, least privilege, auditing |
| Backup reliability | Manifests + checksums + test restores |
| DR runbook | Source, point, target, versions, keys, validation, cutover |

## 49. Implementation Checklist

- [ ] Topology and RPO/RTO targets defined?
- [ ] Inventory of namespaces, indexes, users/roles, and external dependencies maintained?
- [ ] Logical/physical/managed backup chosen based on size and consistency needs?
- [ ] If using `--oplog`, are scope and replica set prerequisites met?
- [ ] Oplog window and secondary lag monitored?
- [ ] Physical snapshots capture all database/journal volumes at a consistent point?
- [ ] Active database files never copied arbitrarily?
- [ ] Sharded backups enforce cluster-wide metadata consistency?
- [ ] Multi-shard snapshots never stitched from uncoordinated timestamps?
- [ ] Current Atlas tier/cloud/region verified to support designed backup/PITR?
- [ ] PITR pre-enabled and restorable range monitored?
- [ ] Retention exceeds delayed data-corruption detection windows?
- [ ] Backup user follows least privilege, uses TLS, and avoids hardcoded secrets?
- [ ] Backups encrypted and KMS keys verified accessible?
- [ ] Offsite/immutable copies maintained per risk model?
- [ ] Backup jobs check exit codes, manifests, checksums, and upload success?
- [ ] Restore targets isolated with sufficient storage and version/FCV compatibility?
- [ ] `--drop`/production overwrites prohibited outside approved changes?
- [ ] Collection counts, indexes, and business invariants verified?
- [ ] For sharding, routing/ranges and cross-shard transactions tested?
- [ ] TLS, networking, users/roles, and KMS verified on targets?
- [ ] Application smoke tests and cutover/rollback plans ready?
- [ ] Periodic DR drills measure actual RPO/RTO?
- [ ] Alerts configured for backup failures, stale backups, retention, PITR, and key access?
- [ ] Auditing enforced for restores, snapshots, retention edits, and privacy policies?

## 50. Conclusion

MongoDB backups must start with **topology, data consistency, and RPO/RTO targets**. For **replica sets**, `mongodump --oplog` is a logical backup approach supporting consistent restores within tool limits; physical snapshots must capture WiredTiger data/journal synchronously and account for secondary replication lag. For **sharded clusters**, shard data and config server catalogs require a **cluster-wide consistent point**; never stitch per-shard snapshots from different timestamps into a makeshift recovery.

With **MongoDB Atlas**, managed snapshots and Continuous Cloud Backup/PITR sharply reduce operational toil when **tier, region, and configuration** support them. Even so, application teams still own understanding retention, restore behaviors, KMS keys, target selection, acceptable data loss, and valid writes occurring after the restore point.

Ultimately, **a successful backup does not mean a successful restore**. Protect backups like production data, maintain manifests and checksums, monitor jobs, and run restore drills in isolated environments. Trustworthy recoverability is proven by **consistent data, a working application, and measured RPO/RTO meeting targets**—not merely the presence of a backup file.
