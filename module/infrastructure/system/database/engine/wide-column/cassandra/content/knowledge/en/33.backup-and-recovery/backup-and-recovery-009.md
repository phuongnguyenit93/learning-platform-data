# Storing Copies Off-Node/Off-Cluster and Protecting Access Permissions

## Objectives and Scope

Apache Cassandra replicates partitions across multiple **replicas** per the replication factor (RF), allowing the system to keep serving when some nodes fail. However, **replication is not a backup**: an accidental delete, overwritten data, software bug, or bad administrative operation can propagate to multiple replicas. If all copies sit inside the same failure domain, an infrastructure failure or ransomware attack can wipe out both live data and recovery capability.

Therefore, in the **Backup and Recovery** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this lesson focuses on **moving copies off the node/cluster** and **protecting access permissions to those copies**. The content connects SSTables, partition keys, CQL, replication/consistency levels, compaction, repair, data recovery, and verification from Java applications.

After studying this lesson, you will be able to:

1. Distinguish **replicas**, **local snapshots**, **incremental backups**, **independent-store backups**, and **verified recoverability**.
2. Design a backup pipeline with **manifests, checksums, schema, versions, token/DC metadata**, completion states, and an independent storage repository.
3. Assess risks of node loss, datacenter loss, accidental deletion, data exposure, or attackers deleting backups as well.
4. Apply **encryption in transit/at rest**, least privilege, identity separation, retention, immutability, and auditing.
5. Build a **backup → verify → store off-cluster → restore drill → data reconciliation** workflow rather than merely confirming copy commands returned success.
6. Build a CQL lab and use the Java Driver to verify event IDs/markers after restoring in an isolated environment.

> **Boundaries:** the commands below are samples for **labs or approved procedures** only. Never change retention, delete snapshots, copy sensitive data to personal accounts, or restore over a live serving cluster. `nodetool` flags, SSTable formats, and restore procedures must be cross-checked against your organization's Cassandra version, environment, and security policy.

## 1. Why Are RF=3 and Same-Node Snapshots Insufficient?

Suppose a keyspace has RF=3 in `dc_a`. When one node loses power, the two surviving replicas can continue serving consistency levels like `LOCAL_QUORUM` if conditions hold. Yet many incidents are not simply "one node died":

| Incident | How Does Replication Help? | Why Is an Independent Backup Still Needed? |
| --- | --- | --- |
| One node loses network, disk intact | Other replicas keep serving; repair/rebuild possible | To recover if other copies also fail or data existed only on the lost node |
| Entire datacenter fails | If cluster has replicas in another DC, failover is possible | Locally ACKed writes may not have reached the other DC; standby DC can also fail |
| Accidental `DELETE` or `TRUNCATE` | Delete mutations replicate just like normal data | Returning to pre-deletion state requires an independent recovery point |
| Application overwrites bad values | Replicas typically converge on the new value | Replicas do not preserve immutable business history for "undo" |
| Compaction/format/version bug | Some replicas may still hold good copies | Bugs can hit broadly; requires data and recovery tools outside the live runtime |
| Ransomware compromises operator account | Can seize control of the entire cluster | If the same privilege can delete snapshots/backups, attackers wipe every copy |
| Accidental VM/volume/namespace deletion | Replicas on surviving infra may live | Snapshots on the same volume/cluster can perish with the infrastructure |

### Four Concepts to Keep Distinct

- **Replica:** a live copy participating in reads/writes per topology and consistency level. This is an in-cluster availability/durability mechanism; **it does not provide independent recovery history**.
- **Cassandra snapshot:** a point-in-time image of SSTables on **the local node**, usually via hard links and related file mechanics. A snapshot on the same data volume **is not an off-node backup**.
- **Off-cluster exported backup:** required files/metadata transferred to storage outside the failure domain, with proper permissions, restore preconditions, and integrity verification.
- **Recoverable backup:** a copy that has been **restore-tested** in an appropriate environment and reconciled against expected data. An upload reporting success has not yet reached this bar.

**Note:** snapshots keep references to old SSTables; compaction can produce new SSTables without freeing old bytes still pinned by snapshots. Backup capacity and local disk must be tracked separately.

## 2. Which Components Must Be Protected?

Cassandra writes mutations first to the commit log/memtable, then flushes them to **SSTables**. With snapshot-based backups, the data captured is primarily **SSTable components** at capture time; restoring requires matching schema and topology context as well.

~~~mermaid
flowchart LR
    App["CQL Application"] --> W["Commit log and memtable"]
    W -->|"Flush"| S["SSTables on node"]
    S -->|"nodetool snapshot"| L["Local snapshot"]
    L -->|"Copy + checksum"| O["Off-cluster backup store"]
    SCH["Schema + recovery config"] --> O
    MAN["Manifest + ACK evidence"] --> O
    O -->|"Restore drill"| DR["Isolated test cluster"]
    DR -->|"Marker reconciliation"| V["PASS / GAP report"]
~~~

### Component Inventory

| Component | What to Save? | Why |
| --- | --- | --- |
| **SSTable components** | `Data.db` and accompanying descriptor components for every SSTable in the selected snapshot | A standalone `Data.db` file is not a restorable SSTable package |
| **CQL Schema** | Keyspaces, tables, partition/clustering keys, UDTs, indexes, table options, per-DC RF | SSTables alone do not provide full instructions to recreate the environment |
| **Topology / version** | Cassandra version, SSTable format, DC/rack/snitch, node/host IDs, token ranges if needed | Guides restore method selection and ensures valid replica placement |
| **Backup time and scope** | Snapshot tag, start/end timestamps, nodes, keyspaces/tables | Multi-node snapshots do not automatically share a global transaction point |
| **File manifest / checksums** | Relative paths, byte sizes, SHA-256 digests, and upload status | Detects missing files, byte corruption, or version mix-ups |
| **Event / ACK source** | Operation IDs, primary keys, markers, ACK timestamps, and UNKNOWN states | Reconciles completeness post-restore; may need independent backup protection |
| **Operational config** | Snitch type, driver DC, repair policies, backup automation, restore runbooks | Helps rebuild the cluster without restoring stale node identities |
| **Encryption keys and access rights** | KMS key references, key versions, permission policies, emergency access procedures | Encrypted data cannot be restored without decryption access |

**Never blindly copy all system keyspaces from an old cluster into a new cluster.** Some system tables store node/topology/identity metadata bound to the source cluster; improper restoration can corrupt membership or host identity. Schema, roles, and permissions must be restored via **version-appropriate procedures**, carefully checking sensitive data such as `system_auth` contents where present.

### Snapshots vs. Incremental Backups and Commit Log Archives

| Method | Used For | What Not to Assume |
| --- | --- | --- |
| **Periodic snapshots** | Full recovery points at chosen intervals | Local-disk snapshots alone do not survive node/cluster loss |
| **Incremental backups** | Saving newly flushed SSTables per config, supplementing a suitable full baseline | Must manage file chains/scope and restore dependencies; does not solve PITR alone |
| **Commit log archiving / PITR** | Can support near-target-time recovery when engineered and tested | Requires version-accurate archiving/replay, timestamps, schema, and sequencing; never assumed out of the box |
| **CDC / app event logs** | Helps reconstruct mutations/events via business logic | Does not replace SSTable backups or full schema exports |

A backup plan must explicitly state **supported restore types**: whole cluster, keyspace, table, subset of partitions, or *point-in-time* recovery. Never assume "having snapshots" covers every restore mode.

## 3. Designing Failure Domains for Off-Cluster Storage

### 3.1. Off-Node Is Not Automatically Off-Cluster

Storage locations vary in isolation:

| Storage Location | Survives Single-Node Loss? | Survives Whole Cluster/DC Loss? | Remaining Risks |
| --- | --- | --- | --- |
| Snapshot folder on same data volume | Not guaranteed | No | Shared disk, VM, OS permissions |
| Secondary volume attached to same VM | May survive primary volume failure | Not guaranteed | Shared host/account/region |
| NAS shared with Cassandra | May survive single-node loss | Architecture-dependent | Shared network, credentials, correlated bugs |
| Independent object store in another account/project | Generally stronger | Depends on region/replication | Credential loss, accidental delete, wrong KMS |
| Off-region or off-site store with separate permissions | Supports DR on source region loss | Potentially yes | Must measure restore speed, retention, and reachability |

**"Off-cluster" means real failure-domain separation**, not merely a different prefix in the same bucket or copying to another volume on the same node. Aim for independence across at least four dimensions: **infrastructure**, **identity/permissions**, **encryption keys**, and **deletion/retention controls**.

For example, backing up from a cluster in `dc_a` to object storage in another region while **using the same admin account that can delete both the bucket and the KMS key** still offers weak ransomware protection. Adding immutable retention and separate identities addresses part of that risk.

### 3.2. Diagram of an Accountable Backup Pipeline

~~~mermaid
flowchart TD
    N1["Node A1 snapshot"] --> T["Least-privilege read-only backup agent"]
    N2["Node A2 snapshot"] --> T
    N3["Node A3 snapshot"] --> T
    T --> C["Hash files + build manifest on trusted channel"]
    C --> U["Upload over TLS"]
    U --> O["Off-cluster object store"]
    O --> I["Retention / immutability / audit"]
    O --> Q["Dedicated restore account"]
    Q --> R["Isolated recovery cluster"]
    R --> V["Checksum + CQL reconciliation"]
    V --> G{"Meets target RTO / RPO?"}
    G -->|Yes| P["Backup set accepted"]
    G -->|No| F["Log GAP, update runbook"]
~~~

This diagram is a logical model; it does not require every node to hold direct Internet write access. In restricted environments, an internal backup agent can pull snapshots over a private network and then upload using a least-privilege identity.

## 4. RPO, RTO, and Backup Schedules Must Be Defined Upfront

**Recovery Point Objective (RPO)** is the maximum acceptable data loss, usually measured in time. **Recovery Time Objective (RTO)** is the maximum acceptable downtime before restoring service. Both quantities directly drive backup design.

Hypothetical examples:

- Full snapshot every 24 hours, no incrementals/PITR. If only the latest snapshot is restorable, **data generated after the snapshot cutoff** risks being absent from recovery.
- A 15-minute RPO target is normally **not met** by once-daily snapshots; it requires tested snapshot/incremental/commit-log archive schedules or another event source.
- A byte-complete backup requiring hours to download/stream several TiB may **miss RTO** if the target is resuming service within 30 minutes.

### Never Confuse Replication Lag with Backup RPO

`LOCAL_QUORUM` in DC A only requires local quorum ACKs; it **does not guarantee** writes immediately reach DC B. A backup taken in DC B at time T may miss writes just ACKed in A if B's replicas had not yet received the mutations. Therefore, know **which DC sourced the backup, which data converged, and where the ACK manifest lives**.

Measurements:

~~~text
RPO observed (for an ordered event set):
  = interval from latest continuously recovered data point
    to incident timestamp

RTO observed:
  = T_service_operational - T_impact_started
~~~

These calculations must accompany a list of **ACKed events that are MISSING/MISMATCH**. If scattered gaps exist, a single number of seconds hides partial losses. Read timeouts during reconciliation are **READ_ERROR**, not yet proof of lost data.

| Business Requirement | Design Direction |
| --- | --- |
| Only need to restore an end-of-day copy | Periodic full snapshots exported off-cluster, restore-tested |
| Lose at most a few minutes of data | Combine supported, verified near-real-time mechanisms, e.g., planned event logs/PITR |
| Lose one DC yet resume within minutes | Beyond backups, requires app failover architecture, data placement, and proper routing/CL |
| Ransomware with cluster admin access | Separate-privilege store, immutability, key separation, auditing, and tested recovery copies |
| Policy-driven data erasure mandates | Backup retention/expiry, restore-time deletion reconciliation, and sensitive-data procedures |

## 5. A Trustworthy Backup Set Requires a Manifest

Never name a file `backup-final-new.zip` and store an unattributed pile of files. A **backup set** needs a unique ID and manifest:

~~~yaml
# Sample MANIFEST structure, NOT a Cassandra auto-generated schema.
backup_id: cassandra-lab-20261121T100000Z
status: COMPLETE
cluster_label: lab-cassandra
cassandra_version: "4.x-example"
keyspace: backup_lab
tables:
  - events_by_run
snapshot_tag: drill-20261121-01
source_dc: datacenter1
source_nodes:
  - node-a
  - node-b
  - node-c
started_at_utc: "2026-11-21T10:00:00Z"
completed_at_utc: "2026-11-21T10:03:00Z"
files:
  - path: node-a/backup_lab/events_by_run-UUID/snapshots/drill-20261121-01/xx-Data.db
    bytes: 12345678
    sha256: "64-hex-characters-computed-at-backup-time"
metadata:
  schema_export: schema.cql
  restore_instructions: runbook-version-7
  encryption_key_reference: "kms:backup-key-alias"
~~~

This is an **illustrative template**: paths, sizes, and checksums are placeholders. A real manifest requires an entry **for every file** of all SSTable components, node/table UUIDs, real computed checksums, version, and snapshot scope decisions. It should be **digitally signed or integrity-protected** so an attacker cannot tamper with both data and checksum lists.

### Backup Set Publication States

~~~mermaid
flowchart LR
    A["PLANNED"] --> B["SNAPSHOTTING"]
    B --> C["COPYING"]
    C --> D["VERIFYING"]
    D --> E["COMPLETE"]
    B --> X["FAILED / INCOMPLETE"]
    C --> X
    D --> X
    E --> R["RESTORE_TESTED"]
    R --> Z["RETENTION / EXPIRE per policy"]
~~~

**Publish `COMPLETE` only after** file lists, checksums, uploads, and essential metadata all match the manifest. A single missing file, skipped node, wrong checksum, or missing schema must leave the set **INCOMPLETE** with a specific error. Avoid displaying "backup succeeded" merely because node A's snapshot finished.

The number of nodes to snapshot depends on restore goals and data scope. **Snapshotting one node of an RF=3 cluster does not cover every partition** if that node is not a replica for every token range. For whole-keyspace/cluster recovery, design a plan ensuring **all required token ranges and copies** are collected—typically across multiple nodes using topology metadata rather than picking one node at random.

## 6. CQL Lab: Creating Markers to Verify Backups

Suppose a lab cluster has three nodes in a DC named `datacenter1`, running a uniform Cassandra version. If your real topology differs, adjust RF and DC names accordingly; never set RF=3 on a single-node lab expecting `LOCAL_QUORUM` to behave like three replicas.

### 6.1. Inspect Cluster

~~~bash
nodetool status
nodetool describecluster
~~~

Before snapshotting, record `UN` (*Up/Normal*) node states, actual configured data paths, and any running compaction/repair/streaming activity. Check DC/version in `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` reflects **only the responding node**, not every node. During rolling upgrades, verify version compatibility across all involved nodes.

### 6.2. Create a Table with a Small Partition

~~~sql
CREATE KEYSPACE IF NOT EXISTS backup_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS backup_lab.events_by_run (
    run_id text,
    event_id uuid,
    marker text,
    payload text,
    origin text,
    PRIMARY KEY ((run_id), event_id)
);
~~~

- `run_id` is the **partition key**, isolating each test run.
- `event_id` is the clustering key, serving as a stable reconciliation identifier.
- `marker` is a short value from an independent source containing no sensitive data.
- `payload` is illustrative data only; never store credentials or API tokens in lab tables.
- Avoid TTL or `DELETE` in the basic lab so data-expiration costs do not mix with basic backup mechanics.

**If the keyspace/table already exists**, `IF NOT EXISTS` does not update old replication settings or structures. Verify:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'backup_lab';
~~~

### 6.3. Write Markers at Confirmed CL

In `cqlsh`:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO backup_lab.events_by_run
    (run_id, event_id, marker, payload, origin)
VALUES (
    'backup-drill-01',
    11111111-1111-4111-8111-111111111111,
    'BASELINE-A', 'first-known-record', 'lab-writer'
);

INSERT INTO backup_lab.events_by_run
    (run_id, event_id, marker, payload, origin)
VALUES (
    'backup-drill-01',
    22222222-2222-4222-8222-222222222222,
    'BASELINE-B', 'second-known-record', 'lab-writer'
);
~~~

`CONSISTENCY ALL` is a `cqlsh` command; with RF3, it requires all three replicas to ACK. Add an event to the **ACKed set** only if the statement truly returns success. Timeouts are tagged **UNKNOWN_WRITE**, never assumed unwritten or written. Use a fresh `run_id` per test run to avoid mixing with leftover data from prior runs.

Check baseline:

~~~sql
SELECT event_id, marker
FROM backup_lab.events_by_run
WHERE run_id = 'backup-drill-01';
~~~

Record an **external manifest outside Cassandra** containing `run_id`, `event_id`, `marker`, CL, actual ACK outcome, and timestamp. An external business-source manifest catches missing ACKed events during backup/restore. **Reading two markers before backup** does not guarantee the entire table or cluster finished backing up.

## 7. Creating Snapshots and Moving Files Off-Cluster

### 7.1. Choosing Capture Point and Schema

For the lab, pause new writers or lock the expected marker set before snapshotting to keep reconciliation simple. In production, multi-node snapshots **are not an atomic cluster-wide transaction/snapshot**: each node snapshots at its own time and in-flight writes may have reached only some replicas.

Before copying, export schema/keyspace definitions and node version lists using approved admin tools. In `cqlsh`, you can run:

~~~text
DESCRIBE KEYSPACE backup_lab;
~~~

`DESCRIBE` is a `cqlsh` command, **not CQL you can send as a prepared statement from Java**. Beyond DDL, save security/role frameworks and recovery configs per runbook; avoid storing plaintext secrets alongside SSTables when they can be separated.

### 7.2. Creating Snapshots on Required Nodes

Example from **each selected lab node**, following the procedure recorded in the manifest:

~~~bash
# Check nodetool version and options before using.
nodetool help snapshot

# Common syntax: snapshot a single table with a tag.
nodetool snapshot -t drill-20261121-01 -cf events_by_run backup_lab

# Inspect registered snapshots on the current node.
nodetool listsnapshots
~~~

Normally `nodetool snapshot` flushes memtable data for the table before snapshotting, unless a **skip flush** option is passed where supported by the version. If flush is skipped, unflushed mutations may be absent from the snapshotted SSTables; document that setting and its RPO impact. **Snapshots do not combine every node's state into a business-consistent image.**

On each node, snapshots typically live under the table directory:

~~~text
<data_directory>/<keyspace>/<table>-<table_uuid>/
  snapshots/<tag>/
    <descriptor>-Data.db
    <descriptor>-Index.db
    <descriptor>-Statistics.db
    <descriptor>-TOC.txt
    ... other SSTable components depending on version/format ...
~~~

A table may span multiple `data_directories` or hold multiple descriptors; **never pick a single `Data.db` file** and treat it as backing up the whole table. When backing up multiple nodes, prefix paths by **node ID/host ID + DC + backup ID** to prevent overwriting identically named files from different nodes.

### 7.3. Copying Securely with Scoped Permissions

Ideally, snapshots transfer over **TLS or an equivalent secure channel** into a backup store **outside the node/cluster**. The backup agent gets read access to snapshot directories, without needing permission to modify live SSTables.

Example using Amazon S3-compatible object storage in a lab (illustrative template, not endorsing a specific vendor):

~~~bash
# Illustrative only: SNAP_DIR must be a verified snapshot.
# AWS CLI must use the backup agent's identity/role, with no keys embedded in script.
SNAP_DIR="/var/lib/cassandra/data/backup_lab/events_by_run-<table_uuid>/snapshots/drill-20261121-01"
DEST="s3://<protected-backup-bucket>/cassandra/lab-20261121/node-a/events_by_run/"

# Bucket already configured with retention policy, access control, and KMS.
aws s3 cp "$SNAP_DIR/" "$DEST" \
  --recursive \
  --sse aws:kms \
  --sse-kms-key-id "alias/backup-kms-key"
~~~

This illustrates **upload syntax** only; it does not prove all files are complete or uploads are atomic. Verify destination/IAM configs, CLI version, and KMS policies before running. For large snapshots, use backup tooling with retries, checkpointing, rate limits, checksums, and per-file logging.

**Never store access keys/secrets in literal script variables**, container images, shell commands logged to history, or job output. Prefer workload identities / instance roles with short-lived credentials scoped to specific buckets/prefixes and revocable.

### 7.4. Verifying Checksums and Completeness

For every file in the snapshot:

1. Record **relative path**, bytes, and **SHA-256** computed from a stable source.
2. Upload and verify object metadata/size/checksum, or **read bytes back from the destination and re-hash** via a supported method.
3. Confirm no missing descriptors/components, target nodes/tables/ranges, or metadata/schema.
4. Verify **manifest integrity** (digitally signed or stored in a permission-isolated/immutable location).
5. Only after full reconciliation write `COMPLETE` to the backup catalog.

Example verifying a file across source and destination after pulling it to an isolated check environment:

~~~bash
# Both files represent the same SSTable component; example paths.
sha256sum "/path/source-snapshot/xx-Data.db"
sha256sum "/path/verified-download/xx-Data.db"
~~~

**Never rely on S3 ETag as a trustworthy MD5 checksum in all cases**: multipart uploads and encryption modes give ETags different semantics. Pick an appropriate checksum algorithm/API and **verify end-to-end matching** per storage policy.

> Snapshots may be created/retained via hard links to SSTables on the same volume. **Copying files to object storage** must produce independent copies; creating hard links on the same host and calling it an offsite backup is wrong.

## 8. Protecting Access Permissions: Who Can Read, Write, Delete, and Restore?

Cassandra backups typically contain real customer data, potentially including PII, business tokens, transaction records, or deletion histories. Even an old snapshot can contain raw bytes no longer returned by `SELECT` due to tombstones/TTLs. Therefore, **backup access permissions must be at least as strict as production read permissions**.

### 8.1. Role-Based Permissions, Not a Single Shared Admin Account

| Role | Required Permissions | Permissions to Avoid |
| --- | --- | --- |
| **Snapshot operator** | Run snapshots on approved nodes/tables, read status | Deleting system-wide backups or changing KMS |
| **Backup writer / agent** | Read source snapshots; write objects into assigned prefix; write required metadata | Deleting/overwriting retention, editing bucket policies, cluster admin |
| **Backup auditor** | View catalogs, checksums, logs, status, restore reports | Reading sensitive payloads unless necessary; deleting objects |
| **Restore operator** | Read approved-scope backups, decrypt per procedure, restore into isolated cluster | Arbitrarily overwriting production or altering retention |
| **Security / KMS admin** | Manage key policies, monitor, and grant approved decryption access | Simultaneously reading all datasets and deleting backups unless required |
| **Retention administrator** | Manage retention schedules per policy/separation of duties | Unilaterally deleting immutable copies before expiry |

Organizations should enforce **separation of duties** and **two-person approval** for destructive actions or broad sensitive data access. A single account able to write, alter manifests, delete objects, disable retention, and destroy KMS keys is a **single point of security failure**.

### 8.2. Least Privilege Across Three Layers

1. **Cassandra / node:** the backup agent reads only snapshot folders and required metadata; operational accounts do not implicitly hold every destructive privilege.
2. **Backup store:** write permissions scoped to prefix/backup ID, restricted reads, deletion locked or separated by role. Buckets/projects must block public access.
3. **KMS / credentials:** only jobs needing encryption/decryption receive corresponding permissions; key policies and rotation/lifecycle stay independent, with key-access auditing.

**Encryption does not replace access control.** If a user has decryption rights and can download all SSTables, encrypted backups still leak data. Conversely, tight IAM with unencrypted backup transfers can expose data over untrusted networks.

### 8.3. Encryption in Transit and at Rest

- **In transit:** TLS for connections to object storage; encrypt transport from nodes to backup collectors. Validate certificates/hostnames and never skip TLS verification.
- **At rest:** server-side encryption with KMS or client-side encryption per policy. Verify key ID/region and decryption rights for recovery accounts.
- **Key separation:** manage backup-store keys under permissions separated from Cassandra operational credentials so a single compromise cannot wipe both data and keys.
- **Key lifecycle:** a backup with 90-day retention whose KMS key is scheduled for destruction after 30 days **cannot be recovered**, even if objects remain intact.
- **Metadata and logs:** manifests/traces can reveal host IDs, table structures, and tenant IDs; protect them proportionately and avoid logging payloads.

When using client-side encryption, record whether checksums apply to **plaintext or ciphertext** and how post-decryption validation works. Avoid workflows where checksums match yet no password/key exists to decrypt.

## 9. Immutability, Retention, Versioning, and Accidental-Delete Protection

An actor with delete or overwrite rights on backups can destroy recoverability even after moving data to another region. Therefore:

- **Versioning:** retains object/manifest versions, reducing overwrite risk; yet versioning alone **is insufficient** if an account can delete all versions.
- **Retention / immutability:** use features like Object Lock / WORM when supported, with appropriate periods and modes. Configure upfront and **test** with the backup writer account to prove pre-expiry deletion fails.
- **Separate delete permissions:** daily backup jobs usually need write-only, not delete. Retention pruning should use a separate approved actor/workflow.
- **Cross-account / cross-region copies:** consider multiple fault domains when defending against regional loss or account compromise.
- **Immutable audit logs:** log uploads, downloads, listings, deletions, policy edits, key usage, restores, and verification outcomes; store logs outside areas attackers can easily wipe.
- **Restore-read access:** recovery accounts need timely read access during an incident; a policy letting agents write while nobody can decrypt still breaks DR.

### What Makes a Retention Policy Right?

Keeping copies longer is not always better. Weigh:

| Requirement | Impact |
| --- | --- |
| Recovering from late-discovered accidental deletes | Needs enough history to roll back prior to deletion |
| Cost and storage footprint | Full/incremental/compaction growth can escalate quickly |
| Data retention and erasure regulations | Limits retention duration; requires post-restore deletion/masking workflows |
| Ransomware | Needs immutable retention exceeding attack-detection latency |
| KMS key lifetime | Keep decryption keys valid for the entire backup retention lifetime |
| Backup format compatibility | Plan migrations/restores across major Cassandra upgrades |

**Regarding personal data erasure requests:** immutable backups may retain records already deleted on the cluster within allowed windows. Maintain retention policies and procedures that **avoid re-exposing erased data upon restore**—e.g., reapplying an erasure log post-restore before opening traffic. Never promise that Cassandra `DELETE` instantaneously scrubs bytes from every historical backup.

## 10. Keeping Local Snapshots Safe Without Filling Disks

Cassandra snapshots normally do not immediately copy all data into a second folder; SSTable components are referenced via hard links. This saves space initially, yet after compaction old files **cannot be reclaimed** while snapshot links remain.

Monitor:

~~~bash
# Observe on an authorized lab/cluster node.
nodetool listsnapshots
nodetool tablestats backup_lab.events_by_run
nodetool compactionstats
~~~

Preconditions before clearing snapshots:

1. The catalog marks the backup set **COMPLETE** and off-cluster copies passed checksum verification.
2. Evidence retention policies and earlier backup versions have been checked.
3. No active restore, drill, or incident relies on that local snapshot.
4. An authorized approver confirms the exact **tag/keyspace/node** to clear.

Administrative command template (do not run without confirming the checks above):

~~~bash
# Illustrates common syntax only; verify via nodetool help clearsnapshot.
nodetool clearsnapshot -t drill-20261121-01 backup_lab
~~~

**Never delete with `rm -rf` using vague globs inside the data directory.** Clearing the wrong snapshot can wipe local evidence and recovery points before off-cluster uploads finish. In production, favor tag-specific audited automation.

## 11. Recovery Drills: Proving Copies Actually Work

### 11.1. Restoring in an Isolated Environment

A proper restore drill **never restores over the production cluster**. Use a dedicated cluster/namespace/network, strict access controls, egress limits, and zero connection to live business consumers.

General steps:

1. **Select a `COMPLETE` backup set**, recording restore targets, RPO/RTO, keyspace/table scope, and owner.
2. **Verify access rights and decryption keys** using a dedicated restore account; check TLS, KMS, and auditing.
3. **Read catalog/manifest**, confirming sufficient nodes/files, bytes, checksums, schema, version, and DC/token metadata.
4. **Download files into isolation**, decrypt, and re-verify checksums end-to-end.
5. **Create matching schema** on the target cluster via approved procedures; avoid copying `system.local`/`system.peers` or old node identity metadata into the new cluster.
6. **Load SSTables via the version-accurate restore workflow**, such as streaming with `sstableloader` where appropriate, or supported node-restore/backup tooling; never drop files blindly into a live data directory and restart.
7. **Wait for needed streaming/repair**, checking replica placement and node health. Repair cannot recreate data absent from every replica and source.
8. **Reconcile via CQL/Java** against ACKed event IDs, plus schema, TTL/tombstone, and representative partition checks.
9. **Measure elapsed time** from restore start until synthetic reads/writes in the test cluster pass criteria.
10. **Save PASS/GAP report:** can service resume, or are there missing events, permission errors, missing KMS keys, or incompatible tool versions?

**Distinguish methods:** per-node data-directory restores, SSTable streaming restores, and backup-tool cluster restores are distinct procedures. Choose based on version, topology, scope, and consistency needs. Never copy node names/host IDs/bootstrap state between source and target clusters without a verified procedure.

### 11.2. What to Check Beyond "Query Returned Results"

| Category | Verification Criteria |
| --- | --- |
| Files | Destination file counts/bytes/checksums match manifest |
| Security | Authorized roles can decrypt/restore; unauthorized roles are still denied |
| Schema | Primary keys, clustering, TTL/compaction/replication match; required UDTs/indexes ready |
| Data | ACKed manifest events return exact markers at target CL; never lump `READ_ERROR` into `MISSING` |
| Deleted data | Tombstones/TTLs behave properly and legally deleted data does not reappear |
| Topology | Replicas match DC/RF, nodes healthy, zero failed streams |
| Service readiness | Synthetic latency, error rate, and throughput meet targets |
| Timing | Observed RTO and RPO recorded with exact timestamps |
| Process | Restore does not depend on an unavailable secret or specific individual |

### 11.3. Illustrative RPO/RTO Report

Suppose a lab has 100 events in the manifest, all ACKed before snapshot. After restore:

| Hypothetical Observed Result | Count |
| --- | ---: |
| `FOUND_MATCH` | 97 |
| `MISSING` | 1 |
| `MISMATCH` | 0 |
| `READ_ERROR` | 2 |

The accurate conclusion is **97 events verified matching, 1 event not found at the tested CL/time, and 2 events unverifiable due to read errors**. Never report "3 events lost" or "restore achieved 97% final completeness." To compute time-based RPO, reconcile **ordered ACK timestamps and specific IDs**; aggregate counts alone are insufficient.

## 12. Java Driver: Reconciling Markers After Restore

Java Driver 4.x can verify expected keys inside the **isolated recovery cluster**, not the failing source cluster. The snippet below uses a **prepared statement**, `LOCAL_QUORUM`, and distinct outcome classification. Assume `CqlSession` is configured with contact points, local DC, TLS/auth, and connected to the recovery cluster; on a single-node lab pick a CL matching real topology.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

public final class BackupRestoreProbe {
    public enum Check { FOUND_MATCH, MISSING, MISMATCH, READ_ERROR }
    public record Expected(String runId, UUID eventId, String marker) {}

    private final CqlSession session;
    private final PreparedStatement select;

    public BackupRestoreProbe(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT marker FROM backup_lab.events_by_run " +
            "WHERE run_id = ? AND event_id = ?");
    }

    public Check check(Expected event) {
        BoundStatement query = select.bind(
                event.runId(), event.eventId())
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(true);
        try {
            Row row = session.execute(query).one();
            if (row == null) {
                return Check.MISSING;
            }
            String actual = row.getString("marker");
            return event.marker().equals(actual)
                ? Check.FOUND_MATCH : Check.MISMATCH;
        } catch (RuntimeException e) {
            System.err.printf(
                "READ_ERROR run=%s event=%s cause=%s%n",
                event.runId(), event.eventId(),
                e.getClass().getSimpleName());
            return Check.READ_ERROR;
        }
    }
}
~~~

Points to remember:

- The `Expected` list must be **stored outside Cassandra** or in a trusted transactional source—never derived from the restored table itself to declare completeness.
- `MISSING` means `SELECT` completed with no row; that may be expected for validly `DELETE`d events. Manifests should record expected deletion/expiration states too.
- `READ_ERROR` covers timeouts, unavailable exceptions, and other errors; **never fold it into `MISSING`**. Log CL, timestamp, coordinator, and error class for investigation.
- One `FOUND_MATCH` at quorum proves that key's read result at the active CL—**not that all replicas or the entire table match**.
- Reuse `CqlSession` and `PreparedStatement`. If manifests contain millions of keys, check in buckets with bounded concurrency rather than firing millions of simultaneous queries that overload the restore cluster.
- Never log markers holding PII or secrets. Audit reconciliation data also needs appropriate retention, access control, and encryption.

## 13. Incident Scenarios and Diagnosis

| Symptom | Likely Cause and How to Check | Right Action |
| --- | --- | --- |
| Backup job `SUCCESS` yet node B has no snapshot | Job checked only node A's upload exit code; manifest lacks full node/range coverage | Mark set INCOMPLETE, capture/copy missing parts, re-verify |
| Object store has files yet downloaded checksums differ | Corrupted upload, wrong file, or missing metadata; ETag misinterpreted | Compare source SHA-256 against post-download checksum; do not publish COMPLETE |
| Snapshots reside only in local directories | Missing off-node/off-cluster copy step | Copy to failure-domain-isolated store and verify |
| Backups lost after admin account compromise | Writer also held delete, retention-edit, and key permissions | Separate IAM/KMS, enforce immutable retention, audit, and test deny rules |
| Restore tool cannot read SSTables | Version/format/schema/config mismatch or missing files | Inspect manifest/compatibility; never manually patch SSTable bytes |
| Restore succeeded yet queries miss markers | Snapshot predated ACK or missed scope; unflushed mutations or valid deletes | Reconcile ACK timestamps, snapshot flushes, files/ranges, and event logs |
| Data restored yet inaccessible | Missing KMS key, role, TLS, secrets, or config | Check key lifecycle, break-glass roles, and restore permissions |
| Local disk climbs sharply after snapshots | Hard links pin old SSTables post-compaction | Verify backup COMPLETE, then clear exact tags per policy |
| Source DC has outage and backups in same region are unreachable | Insufficient failure-domain isolation | Maintain copies in a separate region/site; drill restores with source unavailable |
| Restore resurrects data requested for erasure | Backup holds history older than delete mutation | Apply erasure/retention logs and gate post-restore data release |
| Backups read by unauthorized parties | Overly broad IAM/KMS, public bucket, weak auditing | Revoke privileges/credentials, investigate access, close gaps, report incident |

### One Failure Requiring Special Analysis: File-Consistent Yet Business-Inconsistent Backups

A snapshot on node A at T1 and node B at T2 may both be physically valid. Yet between T1 and T2 the app wrote a multi-partition/multi-table operation. SSTables from both nodes **do not form a cluster-wide transactional snapshot**. Depending on restore mechanics, business state may diverge from expectations.

The solution is not "run `nodetool repair` to synthesize transactions," but rather **defining recovery checkpoints/sources of truth, designing consistency, quiescing writers when feasible, or maintaining event logs/outboxes for replay/reconciliation**. Systems needing strict cross-table consistency must be architected appropriately from the start.

## 14. Operational Checklist for a Backup Set

### Before Backup

- [ ] Know target RPO/RTO, keyspace/table/DC scope, and accountable owners.
- [ ] Have schema exports, Cassandra version, SSTable format, RF/token metadata, and restore runbooks.
- [ ] Cluster/nodes are healthy with disk headroom for snapshots/compaction and upload load.
- [ ] External ACK manifest or event log defined outside Cassandra.
- [ ] Backup agent identity holds **least-privilege** read access to snapshots and write access to destination.
- [ ] Destination enforces encryption/TLS, retention, logging, valid KMS keys, and blocks public access.

### During and After Backup

- [ ] Snapshots taken across **all planned nodes/ranges** with clear tags/timestamps.
- [ ] Every SSTable component of the snapshot inventoried and copied; no extra data directories missed.
- [ ] Manifest includes file list, byte sizes, checksums, cluster/node/DC, schema, and status.
- [ ] Upload/checksums verified from the destination, not merely trusting `copy succeeded` logs.
- [ ] `COMPLETE` published only when all criteria pass; failures remain INCOMPLETE.
- [ ] Zero secret credentials or PII leaked into logs, shared manifests, or chat.
- [ ] Local snapshots cleared only **after** off-cluster backups pass verification and retention permits.

### Periodic

- [ ] Rehearse restores using a **dedicated identity** in an isolated cluster.
- [ ] Reconcile markers and deleted/expired records; never conflate read errors with missing data.
- [ ] Measure real RPO/RTO and restore bandwidth; update runbooks if targets are missed.
- [ ] Test deny rules on delete/overwrite and required decryption permissions.
- [ ] Audit KMS key lifecycles, backup formats, immutable retention, and expiry dates.
- [ ] Review offboarded user access, access logs, and anomalous download alerts.

## 15. Exercises and Self-Check Questions

**Exercise 1 — Replicas vs. Backups?** An RF=3 cluster places all three replicas on machines inside one datacenter. An accidental `DELETE` is acknowledged at quorum and propagates to the remaining replica. Does RF=3 restore data to before the DELETE? Describe the copies that needed to be prepared beforehand.

**Exercise 2 — Off-Node and Failure Domains.** Compare: snapshots on the data volume, copying to a NAS in the same rack, and copying to object storage in another account/region with immutable retention. Evaluate resilience against node failure, DC loss, and account compromise.

**Exercise 3 — Designing a Manifest.** With three nodes and one table holding four SSTables/descriptors per node, list the metadata sufficient to verify not a single component is missing. Why are a lone `Data.db` name and S3 ETag insufficient?

**Exercise 4 — Access Control.** One service account currently uploads, lists, deletes objects, edits KMS key policies, and changes retention. Split it into backup writer, auditor, restore operator, and KMS admin roles, along with how to test denied actions.

**Exercise 5 — Measuring RPO.** The last snapshot is at 10:00; the app receives ACKs for three events at 10:03, 10:04, and 10:05, then the cluster is lost at 10:06. Restore shows only events before 10:00. What do you conclude about observed RPO and missed ACKed events? Why is a manifest needed rather than row counts alone?

**Exercise 6 — Verifying Restore.** A restore in an isolated cluster returns 8 `FOUND_MATCH`, 1 `MISSING`, and 1 `READ_ERROR` for 10 ACKed markers. Can you report "2 records lost"? List reconciliation and follow-up verification steps.

**Exercise 7 — Deleted Data.** A snapshot taken prior to a customer data-erasure request still retains bytes of that record. How do you design retention and restore procedures so deleted data is not accidentally resurrected?

**Exercise 8 — When to Clear Snapshots?** Node A's upload succeeded, yet node B's SSTable checksum failed and the manifest is not `COMPLETE`. Should you run `nodetool clearsnapshot` cluster-wide to free disk? Explain the risks and stop conditions.

**Exercise 9 — Encryption Keys.** A backup object has 120 days of retention left, while its KMS key is scheduled for deletion in 30 days. What happens during a restore at day 90? Design monitoring to prevent "files present but useless" backups.

**Exercise 10 — Version Upgrades.** A cluster upgraded Cassandra yet needs to restore an SSTable backup from an older version. Which metadata/compatibility preconditions must be checked? Why can't you simply copy old SSTables into the new cluster's live data directory?

## Summary

**A Cassandra backup becomes truly meaningful only once data leaves the node/cluster failure domain, is protected against unauthorized reads/deletions, has a verified manifest, and can be restored within acceptable time.** Replicas and local snapshots do not replace off-cluster backups. Preserve all SSTable components, schemas, and metadata; compute end-to-end checksums; enforce TLS, encryption/KMS, least privilege, immutable retention, and auditing. Finally, **rehearse restores in an isolated cluster and reconcile against ACKed events**, because a successful upload command alone never guarantees RPO, RTO, or business data completeness.
