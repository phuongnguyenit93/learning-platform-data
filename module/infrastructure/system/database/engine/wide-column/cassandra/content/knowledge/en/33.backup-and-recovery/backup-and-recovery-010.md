# Restoring a Table or Keyspace into an Isolated Environment in Apache Cassandra

## 1. Purpose of a Recovery Drill

Apache Cassandra is a distributed **wide-column** database management system. Partitions are located by **partition key**, replicas are placed using tokens and replication strategy, and Java applications read/write via CQL at appropriate consistency levels. When an accidental delete, application bug, multi-node failure, or storage outage occurs, having surviving replicas in the cluster does not mean you can safely roll back to older data.

In the **Backup and Recovery** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module, this lesson focuses on the question:

> How do you restore a table or an entire keyspace from backups into a **separate Cassandra cluster** to verify data and procedures **without accidentally modifying production**?

The goal of an isolated environment is not necessarily replicating infrastructure at 100% production scale. The more important goal is having a **recovery target with independent identity, data, access permissions, and networking**, enabling you to:

1. **Prove backups are readable:** SSTable files are complete, compatible, and pass integrity checks.
2. **Prove schemas can be rebuilt:** keyspaces, tables, primary keys, types, replication, indexes, and needed dependencies.
3. **Prove restored data is accurate** for the point in time and scope supported by the backup.
4. **Measure recovery duration** to compare against RTO and spot slow bottlenecks.
5. **Investigate accidental deletes/corruption** without mixing old backup data into production.
6. **Allow controlled QA/Java application queries** to reconcile keys, query shapes, TTLs, consistency, and business rules.

**Safety rule number one:** never test recovery by copying SSTables or running import commands directly against the production cluster before verifying data and change plans.

## 2. Backups, Replicas, Repair, and Restore Are Different Concepts

| Mechanism | Purpose | Can Recover Data Prior to a Replicated DELETE? | Fit for Lesson Goal |
|---|---|---|---|
| **Replication** | Maintain current copies across multiple replicas | Usually **no**: `DELETE` is replicated too | Protects availability; does not replace backups |
| **Repair** | Compare and synchronize differences across replicas | Not a time-travel mechanism | Maintains consistency while cluster runs |
| **Hinted handoff** | Replay missed mutations when a replica is temporarily absent | No: hints can carry the newer `DELETE` | Reduces temporary replica drift |
| **Snapshot** | Capture SSTable versions at a requested point in time | **Potentially**, if snapshot holds the data and TTL/schema conditions allow | Primary source for restore exercises |
| **Incremental backup** | Save newly flushed SSTables since a managed baseline | Can supplement snapshots, but does not provide full PITR alone | Recovers newer data per policy |
| **Commit-log archive** | Archive log segments for replay via supported workflows | Can participate in point-in-time recovery when fully configured/verified | Advanced topic, version-dependent |
| **Restore to isolated cluster** | Rebuild schema and data on an independent target | Uses backups to inspect pre-incident state | Core focus |

**Without independent backups, replication is not "version history."** Once all replicas receive a valid delete command, repair typically reinforces that deletion rather than restoring old data.

## 3. Restore Scope: Single Table vs. Whole Keyspace

### 3.1. Restoring a Single Table

Suppose only `commerce.orders_by_id` suffered a buggy `UPDATE` while other tables remain valid. A sensible scope may be:

- Fetch the exact snapshot/SSTables for `orders_by_id`.
- Recreate a **compatible keyspace and table** in the isolated cluster.
- Import the required SSTables and check rows/timestamps/tombstones/TTLs.
- Extract the needed record set or prepare a subsequent approved recovery plan.

You do not need to import every table in the keyspace if an investigation only inspects a mis-updated partition. Still, understand whether that table's data depends on other tables, UDTs, indexing, or business logic.

### 3.2. Restoring an Entire Keyspace

Restoring an entire keyspace has a broader scope:

- Keyspace replication settings must be **intentionally adapted** to the isolated environment's topology.
- All tables, user-defined types (UDTs), indexes, materialized views, and functions/aggregates (if used) must be inventoried.
- Data for **all tables** needing recovery must be collected, with per-table coverage verified.
- Snapshots across different nodes do not by default produce **a keyspace-wide consistent transaction**.

For businesses with denormalized tables such as `orders_by_id` and `orders_by_customer`, restoring only one table can leave an incomplete or contradictory view relative to the other. That is an application design and consistency problem, not just file copying.

### 3.3. Cases Requiring Extra Caution

- **Counter tables:** never replay counter `INSERT`/`UPDATE`s like regular rows; increments have distinct semantics and retries double-count.
- **Materialized views / secondary indexes:** build/rebuild mechanics depend on version and features; base-table SSTables do not automatically rebuild every secondary structure.
- **LWT/Paxos:** table snapshots do not equate to a full consensus-state snapshot for in-flight transactions.
- **TTLs:** data can **expire in real time** after snapshot capture; restoring does not pause the clock.
- **Tombstones and `gc_grace_seconds`:** restoring while missing related snapshots/SSTables can resurrect wrong data or break delete semantics.
- **CDC, triggers, integrations:** decide whether to disable them in the isolated environment to avoid external side effects.

## 4. Architecture of a Safe Isolated Environment

### 4.1. Isolation Across Multiple Layers

A test cluster deserves to be called **isolated** only when at least these factors are addressed:

| Layer | Basic Requirement | Rationale |
|---|---|---|
| **Cluster identity** | Separate `cluster_name`, fresh host IDs, gossip never touches production | Prevents test nodes from joining the live ring |
| **Network** | Dedicated VPC/subnet, firewall, security groups, seeds pointing only to restore nodes | Prevents gossip/streaming/CQL traffic with production |
| **Data directories** | Dedicated disks/filesystems; never mount production volumes | Prevents overwriting original SSTables, commit logs, or snapshots |
| **Credentials / TLS** | Separate identity/secrets for recovery environment | Avoids leaking keys or granting unneeded production privileges |
| **Contact points** | CQL clients use only restore target IPs/DNS | Prevents Java from accidentally running CQL against production |
| **External side effects** | Disable or sandbox jobs, CDC consumers, webhooks, email, payment hooks | Prevents stale data from triggering real-world actions |
| **Access control** | Least privilege, auditing, log retention | Backup data may contain PII and secrets |
| **Resources** | Dedicated CPU/RAM/disk/network quotas; monitor free disk | Restoring/streaming is heavy I/O |

**Merely renaming a keyspace does not create isolation.** Running `sstableloader` pointed at a production contact point still loads data into the live cluster even if the source folder sits on a lab machine.

### 4.2. Recovery Flow Diagram

~~~mermaid
flowchart TD
    A["Immutable backup: SSTable snapshot + metadata"] --> B["Verify manifest/checksums"]
    B --> C["Read-only staging; never mutate source backup"]
    C --> D["Dedicated recovery cluster: cluster_name/seeds/network"]
    E["Matching CQL schema + RF in restore DC"] --> D
    D --> F["sstableloader or SSTable load per runbook"]
    F --> G["Verify data, TTLs/tombstones, schema"]
    G --> H["Read-only Java app on restore cluster"]
    H --> I["RPO/RTO report and evidence"]
    I --> J["Retain for investigation or tear down lab per policy"]
    K["Production"] -. "NO DATA-LOAD CONNECTIONS" .-> D
~~~

Note: the dashed arrow represents a **connection boundary**, not a required data flow. Backups are **copied in a controlled manner** from storage or media into the isolated environment's staging area.

### 4.3. Pre-Backup-Touch Checklist

~~~text
[ ] Scope: single table or entire keyspace?
[ ] Target data point, RPO, and RTO?
[ ] Confirmed exact snapshot tag, timestamp, and source nodes/DCs?
[ ] Complete set of SSTable components, manifests, and matching schema?
[ ] Any additional data backups, incremental backups, or commit-log archives?
[ ] Checked compatibility between SSTable version and target Cassandra?
[ ] Target uses a new cluster_name, separate IPs/seeds, and firewall blocking production?
[ ] Credentials, certificates, and KMS keys handled securely?
[ ] Target storage sufficient for data, streaming, compaction, and headroom?
[ ] All automation capable of side effects isolated?
[ ] Plan in place to record checksums, progress, errors, and timestamps?
~~~

Do not start by running `nodetool refresh` or `sstableloader` and only afterward ask where the source files came from.

## 5. What Does a Cassandra Snapshot Contain?

### 5.1. SSTable-Based Snapshots

Cassandra uses immutable **SSTable** files. Snapshots typically rely on hard links to SSTable components at capture time; directory structure looks illustratively like:

~~~text
/var/lib/cassandra/data/
  commerce/
    orders_by_id-<table-id>/
      snapshots/
        pre_incident_20261121/
          <sstable-component-files>
          <manifest-or-metadata-if-present>
~~~

Actual paths depend on `data_file_directories`, version, and table ID. One table can hold SSTables across **multiple data directories**; backing up just one directory does not guarantee the full table.

Snapshots preserve SSTables at capture time; `nodetool snapshot` in default configurations coordinates flushing memtable data first, unless a skip-flush flag such as `--skip-flush` is used where supported. **Check actual snapshot behavior and logs**, especially when evaluating very recent mutations.

### 5.2. Snapshot Commands (Illustrative)

On the nodes specified in the backup plan using version-accurate syntax:

~~~bash
# Snapshot one table; check 'nodetool help snapshot' for your running release.
nodetool snapshot -t recovery_drill_20261121 -cf orders_by_id commerce

# Snapshot the whole keyspace on this node.
nodetool snapshot -t recovery_drill_20261121 commerce

# List snapshots known to this node.
nodetool listsnapshots
~~~

**Warning:** these commands snapshot only **the connected node**, not all replicas or all nodes in the cluster. Use a verified orchestration mechanism to cover the required tokens/DCs and confirm all needed nodes succeeded.

Flags like `-cf`, keyspace/table arguments, and command names can vary by version; always run `nodetool help snapshot` before real execution.

### 5.3. "Keyspace-Wide" Snapshots Are Not Cluster-Wide Transactions

Suppose an order is written to two tables in sequence:

~~~text
10:00:00  orders_by_id       has order O123
10:00:01  snapshot node A
10:00:02  orders_by_customer gets updated
10:00:03  snapshot node B
~~~

Files from node A and node B can reflect slightly different instants. Cassandra does not provide **global snapshot isolation** across all tables and all replicas merely because an operator reuses the same snapshot tag.

If the business requires cross-table consistency:

- Use a business write-quiesce window if feasible.
- Record a verified **restore point** in an upstream/event log.
- Design post-restore checks and reconciliation.
- Never claim "identical snapshot tags" mean all tables share an identical timestamp.

## 6. Preparing Complete and Trustworthy Backups

### 6.1. Inventory of Artifacts to Preserve

| Artifact | Why Needed |
|---|---|
| **SSTable components** (Data, Index, Summary, Statistics, etc. per release) | Forms data that can be read or streamed back |
| **Snapshot manifest** (if present) | Inventories files belonging to the snapshot |
| **CQL Schema** | Rebuilds keyspaces, tables, column types, primary keys, UDTs, indexes |
| **Version metadata** | Evaluates SSTable format and tooling compatibility |
| **Topology / per-DC RF** | Understands token coverage and plans target replica placement |
| **Timestamps, timezone, and snapshot tag** | Establishes freshness and distinguishes pre/post-incident copies |
| **Checksums and file sizes** | Detects incomplete copies or corrupted files |
| **Encryption / key material** (if encrypted) | Enables reading backups; secures decryption privileges |
| **Incremental files / log archives** (if needed) | Recovers post-snapshot data within real capabilities |
| **Backup job success/failure logs** | Prevents using snapshot sets that succeeded on only a subset of nodes |

Never assume a snapshot on **one replica** represents the entire table across the cluster. A single node holds only token ranges belonging to its replica placement. Full recovery requires coverage across **all partitions/token ranges**, collected across multiple nodes/DCs per plan.

### 6.2. Verifying File Inventory Without Touching Source Backups

Example operations performed on **staging copies**, not live serving SSTable directories:

~~~bash
# Illustrative for a Linux staging host; paths must be verified by operator.
find /restore-staging/commerce/orders_by_id -type f -print

# Generate file hashes of staging data to compare against source manifest.
# Output must be checked against checksums saved at backup time.
find /restore-staging/commerce/orders_by_id -type f   -exec sha256sum {} \;
~~~

Never recompute checksums **after a file was corrupted** and treat them as original; authoritative checksums must come from trusted backup manifests/stores. When copying, check errors, byte counts, and per-file hashes. Keep source backups immutable and operate on a **working copy**.

### 6.3. Estimating Required Storage Space

Suppose:

- Total SSTables in restore scope: **480 GiB**.
- Target data distribution and replication: depends on target RF/placement.
- Headroom for compaction, streaming, and background work: assume planning **40% extra** above expected lab storage bytes.

~~~text
If expected data files in lab ≈ 480 GiB:

Assumed headroom = 480 × 40% = 192 GiB
Preliminary total budget = 480 + 192 = 672 GiB

This is a budgeting example, NOT a guaranteed formula.
~~~

If `sstableloader` streams data from multiple source replicas, files may hold overlapping logical partitions and generate more I/O than the final footprint. If the lab changes RF, recalculate **per-node disk capacity**, not just total logical bytes. Beyond data, reserve space for commit logs, system data, logs, temporary snapshots, compaction, and retry/error files.

## 7. Building an Isolated Cassandra Cluster

### 7.1. Never Copy Production's Raw Data Directory

A very dangerous shortcut is copying production's entire data/commitlog/system folders onto a lab host and changing IPs. Doing so carries over **host IDs, token metadata, gossip state, and internal system data** unfit for a brand-new cluster.

Stand up an **empty** restore cluster, initialize fresh identities, create schemas, and load **only the SSTables of target user tables** via supported tools.

Items to verify:

- Cassandra version compatible with source SSTables; never assume a newer/different version can read all old formats directly.
- `cluster_name`, `seeds`, `listen_address`, `rpc_address`, datacenter/rack/snitch belong strictly to the lab.
- Sufficient nodes for target RF and disk/network capacity for recovery.
- Appropriate TLS/authentication and KMS/key management, while **sharing zero secrets beyond minimum necessity**.
- Restore nodes have no gossip/streaming paths to production; enforce firewalls via network policies, not just cluster names.
- Applications run read-only/sandboxed with no unintended scheduled jobs or CDC consumers.

### 7.2. Single Node or Multi-Node?

A **single-node lab** may suffice to inspect schemas and sample rows if quorum/availability testing is unnecessary. Yet with one node, a keyspace with RF=3 in that DC cannot satisfy `LOCAL_QUORUM` or mirror production placement.

To test **distributed read/write paths**, use a lab cluster with enough nodes and matching RF. In a minimal lab, you may set RF=1 **lab-only** to inspect backup contents while explicitly documenting that this **does not validate** RF=3, repair, or outage behavior.

**Never copy production replication settings verbatim when DC names or node counts differ.** The restore target is logical data; replication placement must match the isolated topology.

## 8. Recreating Schema Before Importing SSTables

### 8.1. Saving Schema as CQL

Use the DDL stored with the backup or a trusted schema export:

~~~cql
-- Example cqlsh on SOURCE cluster when authorized, solely to export schema.
DESCRIBE KEYSPACE commerce;
~~~

`DESCRIBE` is a **cqlsh** command, not a statement sent directly through a driver to query data. During recovery, prefer **the DDL preserved alongside the backup** rather than pulling current schema after a bad change already occurred.

### 8.2. Recreating Keyspace and Table in the Lab

Suppose the lab has a three-node datacenter `restore_dc` and will test `LOCAL_QUORUM`:

~~~cql
CREATE KEYSPACE commerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'restore_dc': 3
}
AND durable_writes = true;

CREATE TABLE commerce.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    placed_at timestamp,
    status text,
    total_amount decimal
);
~~~

The names **`commerce` and `orders_by_id`** match the logical source schema to streamline importing, while **the cluster remains independent** via networking, identity, and host IDs. The DC name `restore_dc` must match the lab's snitch configuration.

With only **one node** and no quorum testing, RF=1 in the lab DC is more sensible. If the source table uses **UDTs**, create types before tables; for indexes and views, verify rebuild ordering per tool/version.

### 8.3. Schema Compatibility Is More Than Table Names

For SSTable import to succeed, verify:

- **Primary key and clustering columns:** data types, ordering, clustering order, and partition key must match.
- **Column types, UDTs, static columns:** never arbitrarily change types before loading.
- **Table options** such as compression, compaction, TTL, and gc grace: can alter post-restore read/runtime behavior.
- **Schema ID:** the new cluster generates a new table ID; import tooling must map cleanly without copying source table system metadata.
- **SSTable format/version:** must be supported by the target cluster's tooling.
- **Data encryption:** backups may require dedicated decryption keys.

If schema migrations ran between snapshot time and recovery time, never blindly create today's schema and load old SSTables. Determine the **schema at the restore point**, check compatibility, and plan transformations if needed.

## 9. Choosing How to Load Backup Data into the Lab

Two common approaches behave very differently.

### 9.1. `sstableloader`: Streaming Data into the Target Cluster

`sstableloader` is commonly used to **stream existing SSTable data into a running Cassandra cluster**, honoring target token placement and RF. For an isolated environment, this is usually preferred because data distributes across lab nodes automatically without forcing operators to manually map files to token ranges.

Logical steps:

1. Build the lab cluster and create compatible target schema.
2. Copy snapshot SSTable components into staging **outside live running data directories**.
3. Arrange files in the **source layout accepted by that version's `sstableloader`**.
4. Point `sstableloader` at **the exact lab contact point**, with appropriate auth/TLS.
5. Monitor stream progress, errors, and disk usage on lab nodes.
6. Verify loaded data and CQL read results.

**Illustrative** example (substitute IPs and check `sstableloader --help` for your release):

~~~bash
# First verify the tool and syntax for the exact Cassandra release.
sstableloader --help

# RUN ONLY WHEN 10.50.0.11 is a contact point of the ISOLATED cluster.
# /restore-staging/commerce/orders_by_id must follow the layout
# expected by your version's sstableloader.
sstableloader -d 10.50.0.11 /restore-staging/commerce/orders_by_id
~~~

**Critical:** example paths are not a promise that every release accepts this layout. Some releases require table-ID directory names and/or explicit target keyspace/table flags. Confirm via `sstableloader --help` and test on a small dataset first.

This tool **writes data into the target cluster**—it is not read-only. Verify IP/DNS, certificates, cluster identity, and permissions before running. **Never point `-d` at a production seed/contact point during a restore drill.**

### 9.2. `nodetool refresh`: Loading Copied SSTables on a Target Node

Another approach for **local** imports on a running Cassandra node is copying compatible SSTables into the exact **target table's data directory** and telling the node to reload SSTables:

~~~bash
# Syntax illustration only; never run before copying and verifying files safely.
nodetool refresh commerce orders_by_id
~~~

This is **not a drop-in substitute for `sstableloader` across every cluster**:

- Files must sit in the exact table ID/path with right permissions and compatible SSTable format.
- Importing directly on one node does not automatically ensure **cluster-wide replication/token coverage** under a new topology.
- Data can collide with existing SSTables if the target is not truly empty.
- Older versions/tombstones may be shadowed by newer mutations or yield confusing results.
- Loading wrong files can corrupt table state and require operational intervention.

Use `refresh` only for **operator-verified local recovery scenarios**, never as the default step for every restore.

### 9.3. When to Choose Which?

| Criterion | `sstableloader` | `nodetool refresh` |
|---|---|---|
| Target is a new multi-node cluster | **Usually better fit** via target-aware streaming | Requires solving file-to-node/range mapping manually |
| Token ownership / RF differs | Streams data per lab replica placement | Does not push files to all needed replicas |
| Source is SSTable snapshots | Supported with matching layout/format/version | Usable if files are placed accurately and compatible |
| I/O impact | Streams over network, writes on target nodes | File copy + local refresh, still incurs I/O |
| Risk of hitting production by mistake | **High if wrong `-d` is passed** | **High if logged into a production node** |
| Must test in isolation | Yes, start with small tables and verify | Yes, only per specific runbook |

**Never confuse `nodetool rebuild`, `repair`, and `refresh`.** Rebuild/repair leverage existing live replicas to sync; they do not automatically ingest external snapshots to restore old logical data.

## 10. Workflow to Restoring One Table with Snapshots and sstableloader

This section outlines an **operational runbook** using `commerce.orders_by_id` as an example. IPs, paths, and DDL are illustrative; always run in an authorized lab and verify release compatibility.

### Step 1 — Lock Scope and Select Restore Point

Record:

- Incident ID and reason for restore.
- Which tables/partitions require inspection.
- Pre-incident snapshot timestamp, UTC timezone, and expected data at that instant.
- RPO (acceptable data loss) and RTO (recovery time) definitions.
- Proof of complete snapshots and read access to storage.
- Lab node/disk counts and expected RF/CL.

For example, an accidental `DELETE` occurs at 10:00 UTC. If the latest valid snapshot is 09:00 UTC, restoring from snapshot shows data around 09:00—**it does not automatically retain writes between 09:00 and 10:00**. Recovering closer to 10:00 requires appropriate incremental/log/upstream replay mechanisms.

### Step 2 — Verify Isolated Cluster and Block Production Paths

Confirm:

~~~text
Environment: recovery-lab
Cluster name: cassandra-restore-lab
Datacenter: restore_dc
Contact point: 10.50.0.11 (example)
Production network: DENIED from recovery workload
Schema target: commerce.orders_by_id
Expected RF in restore_dc: 3
~~~

Avoid putting plaintext credentials into shell history whenever possible; provision secrets via managed mechanisms.

### Step 3 — Verify Snapshots and Stage SSTables

Inspect manifests, hashes, byte counts, and file lists at each source. Copy to isolated staging while **preserving source backups untouched**. With multi-node snapshots, verify which partition ranges are represented and ensure no data was missed due to a failed node snapshot.

When multiple copies of the same data exist, streaming from every copy can raise cost or cause redundant physical work. Build the input list based on coverage/correctness, not "dump every file into one directory and hope."

### Step 4 — Create Compatible Schema on Target

Use DDL from the snapshot point or verified compatible schema. Verify table metadata via `DESCRIBE KEYSPACE commerce` in the **lab**, confirm RF fits lab node count, and ensure no production app writes to the target.

### Step 5 — Load Data

Run `sstableloader` from staging targeting the lab, watching progress output and exit codes. For multi-table keyspaces, proceed systematically per table while watching disk/network/compaction. Never launch excessive parallel imports just to shrink RTO on paper.

### Step 6 — Post-Import Checks

- `nodetool status`: lab nodes in the right DC and healthy state.
- `nodetool netstats`: active streams finish without stalling; monitor peer progress.
- `nodetool compactionstats`: post-import backlog and disk pressure.
- `DESCRIBE TABLE` and targeted partition-key `SELECT`s.
- Reconcile sample records, timestamps, and row counts via controlled methods.
- Check whether TTLs/tombstones cause data to look different from snapshot day.

### Step 7 — Report and Decide on Data Usage

Document which backup set was used, schema version, checksums, duration, error counts, reconciled data, limitations, and recommended next steps. **Never automatically "reverse-sync" data from the lab into production** after seeing a few queries pass.

## 11. Workflow to Restore an Entire Keyspace

When an entire keyspace is needed, do not merely repeat loader commands—consider **schema dependencies and cross-table completeness**.

### 11.1. Recommended Recovery Order

1. Inventory tables, UDTs, functions/aggregates (if any), indexes/materialized views, options, and dependencies.
2. Select a consistent backup/restore point across all tables; document node-to-node snapshot timing skew.
3. Build the target cluster and configure matching RF/DC.
4. Create **UDTs before tables using them**; create base-table schemas per matching version.
5. Plan restoring base-table data and secondary structures (indexes/views) per separate runbooks.
6. Reconcile critical partition/record counts per table plus cross-table business consistency.
7. Run application validation on the lab and confirm zero side effects.
8. Conclude with an RPO/RTO report and known gaps.

### 11.2. Never Assume System Schemas Are Portable

Cassandra's system keyspaces contain topology, node identities, and internal state. Not all schema/user/role/system tables should be copied raw from production into a new cluster.

Administrative components such as authentication, authorization, and schema history must be designed separately for the lab. Specialized restore tools may coordinate parts of this; still verify **metadata consequences** prior to execution.

### 11.3. Reconciling Denormalized Tables

Suppose an application maintains:

~~~text
commerce.orders_by_id
  order_id -> customer_id, status, total_amount

commerce.orders_by_customer
  (customer_id, order_id) -> status, total_amount
~~~

If both tables' snapshots do not share the same logical instant, order O123 may exist in the first table while absent or holding a different status in the second. Cassandra does not guarantee cross-table transactions across multi-node snapshots.

**Keyspace recovery criteria must include business invariants**, not merely whether every table answers `SELECT` queries.

## 12. Point-in-Time Recovery: Snapshots Alone Are Not Enough

### 12.1. Snapshots and Incremental Backups Differ

A snapshot reflects SSTable state at a defined instant. Incremental backups save newly flushed SSTables per enabled policy; combining them recovers more data, yet **still does not automatically provide exact cluster state at any arbitrary millisecond**.

Questions that must be answered:

- Which incremental files occurred before vs. after the restore point?
- Which unflushed mutations sat in which commit logs?
- How are `DELETE`/TTL mutations and timestamps preserved?
- Can replay stop at a tool-supported cutoff?
- Can coordination across nodes and keyspaces be guaranteed?

Without a rehearsed PITR workflow, state clearly **"restoring from snapshot around time window X,"** never promising **"restoring to exact 09:59:59."**

### 12.2. Commit-Log Archiving Only Works When Prepared Ahead of Time

Some Cassandra releases support commit-log archiving/replay per release mechanics. Reaching a specific recovery point requires archived segments, metadata, restore config, and tested replay/cutoff ordering in the lab.

**Never manually copy production commit logs into a new lab cluster's data directory** and start it expecting Cassandra to replay transactions accurately. Commit logs bind to local formats/metadata and recovery state; follow release-specific procedures, especially across differing topologies and schemas.

### 12.3. TTLs Keep Ticking in Real Time

For example, a row written at 08:00 with `TTL 3600` (one hour), snapshotted at 08:30, then restored at 12:00. The row may **already have expired at 09:00**, even though the snapshot was taken before expiry.

Therefore:

- Snapshots preserve data/timestamp/TTL semantics; **they do not freeze the TTL clock**.
- Reads in the lab cluster after TTL expiry may omit that row.
- Pre/post-TTL data checks must weigh timestamps and business expectations.
- Never "fix" this by shifting the restore machine's clock or hacking SSTable timestamps.

### 12.4. Tombstones and Deleted Data

`DELETE`/TTL writes tombstones so replicas know old data is no longer live. Mixing snapshot data with newer data in the same table allows timestamps/tombstones to shadow each other. In a recovery environment, an **empty target** removes one layer of complexity, yet tombstones inside snapshots still retain their semantics.

Never cherry-pick one `Data.db` SSTable holding a desired row while discarding tombstones in other SSTables. Doing so can resurrect data already deleted at the restore point or create inconsistent states.

## 13. Testing with CQL in the Restore Environment

### 13.1. Querying by Partition Key

Example for `commerce.orders_by_id`:

~~~cql
-- Run in cqlsh connected to the ISOLATED CLUSTER.
CONSISTENCY LOCAL_QUORUM;

SELECT order_id, customer_id, placed_at, status, total_amount
FROM commerce.orders_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

`LOCAL_QUORUM` is valid only if the lab DC's RF and healthy replica count support it. On a single-node RF=1 lab, test options differ. Always record the CL used during reconciliation so results retain context.

### 13.2. Data Verification Approaches

| Check Category | Example | Why Useful |
|---|---|---|
| **Key existence** | `SELECT` across 10–100 known partition keys | Detects missing data in business scope |
| **Column values** | status, amount, timestamp, UDTs/collections | Detects schema/type mismatches |
| **Deletes / TTLs** | Records expected to be expired or deleted | Detects restores violating deletion semantics |
| **Data coverage** | Keys spanning multiple token ranges and source DCs | Detects backups missing nodes/ranges |
| **Cross-table consistency** | Orders matching across denormalized tables per invariant | Detects skewed snapshot timestamps |
| **Application** | Read-only API/DAO on lab | Proves real queries execute and return right data |
| **Metadata** | Version/schema, RF, table options, indexes | Explains differences between lab and source |

Never run `SELECT COUNT(*)` on massive tables as a primary check: full-table counts trigger expensive scans and timeouts. For volume checks, rely on manifests, external counters, stratified sampling, or controlled token-range reconciliation jobs.

### 13.3. Never Compare Row Counts Alone

Two restores can match in total row count while differing in amounts/statuses/timestamps, missing some partitions while carrying extra ones. Reconcile **record identity, payload contents, and invariants** using a representative test suite.

When comparing checksums:

- File hashes verify **backup files and staging copies** were not altered.
- Logical row checksums verify **data contents** post-import, requiring canonical ordering and encoding.
- Never expect SSTable file hashes in the lab to match source hashes after `sstableloader`: importing and compaction rewrite bytes into new SSTables.

## 14. Java Driver 4.x: Verifying Restores Without Touching Production

A Java verification app needs its own **dedicated `CqlSession`**, contact points, and local DC. Example:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.util.UUID;

// Example: IP belongs strictly to the restore cluster, NOT production.
try (CqlSession lab = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("10.50.0.11", 9042))
        .withLocalDatacenter("restore_dc")
        .build()) {

    PreparedStatement find = lab.prepare(
        "SELECT status, total_amount " +
        "FROM commerce.orders_by_id WHERE order_id = ?"
    );

    UUID orderId =
        UUID.fromString("11111111-1111-1111-1111-111111111111");

    BoundStatement query = find.bind(orderId)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

    Row result = lab.execute(query).one();
    if (result == null) {
        throw new IllegalStateException(
            "Expected restored order was not found");
    }

    String status = result.getString("status");
    BigDecimal amount = result.getBigDecimal("total_amount");

    System.out.println("Restored order: " + status + ", " + amount);
}
~~~

This snippet tests **reading** one partition by known key. Real setups require dedicated lab auth/TLS, timeouts, and driver metrics. When inspecting sensitive data, **never print PII to stdout or logs** just to display business values; use comparisons/counts/aggregates and sanitized logging.

Protective practices:

1. Configure dedicated lab client settings; **never fall back to default production environment variables, secrets, or contact points**.
2. Grant the test account **SELECT-only privileges** whenever possible.
3. Add CI/CD guardrails rejecting runs whose endpoints fall outside an approved lab allowlist.
4. Never emit telemetry, CDC, or webhooks to production or live payment/email systems.
5. Use prepared statements with partition-key `WHERE` clauses to avoid test-induced full scans.
6. Measure read p95/p99 latency and timeouts to see whether the recovered cluster sustains expected workloads rather than merely reading a few rows.

## 15. Monitoring During Import and Post-Restore

### 15.1. Status Commands

~~~bash
# Inspect nodes, DC/rack, status, and data distribution.
nodetool status

# Active send/receive streams during sstableloader and other operations.
nodetool netstats

# Compaction backlog and disk pressure after loading data.
nodetool compactionstats

# Internal thread-pool queues and dropped messages.
nodetool tpstats

# Release-specific keyspace/table and SSTable statistics.
nodetool tablestats commerce.orders_by_id
~~~

Field names and formatting vary by version. Seeing zero active streams in `netstats` is a good sign, yet **insufficient** to prove complete recovery; combine with loader exit codes, logs, file inventories, and CQL checks.

### 15.2. Minimum Restore Dashboard

| Group | What to Observe |
|---|---|
| **Progress** | Bytes/files copied, streams completed/failed, tables imported |
| **Disk** | Free space, write latency, IOPS, throughput, compaction overhead |
| **Network** | Throughput, retransmissions, errors, timeouts |
| **Cassandra** | Nodes UP/normal, pending compaction, read/write latency, dropped messages |
| **Data quality** | Key checks, logical checksums, TTL/tombstones, invariants |
| **RTO** | Elapsed time from authorized start until reads/validation pass |
| **RPO** | Actual recovered data checkpoint vs. business-accepted threshold |
| **Security** | Access logs, read privileges, transport encryption, and lab retention |

Record UTC timestamps for copy/restore milestones: start, schema verification, loader start/finish, validation finish, and cleanup. Timestamping gives a far more realistic RTO than guessing from backup byte size alone.

## 16. Troubleshooting Runbook During Recovery

### 16.1. Loader Reports Schema Mismatch

**Symptom:** `sstableloader` cannot load files even though the table name matches.

Check:

- Is the schema from the **snapshot instant** or a newer altered schema?
- Do primary key/clustering types match?
- Are UDTs, static columns, or dropped/recreated columns involved?
- Are the Cassandra version and SSTable format supported?
- Does the staging directory follow the layout the loader expects?

Never hack target columns or manually copy SSTables into production. Work in the lab, keep original backups intact, and retry with a verified compatible schema.

### 16.2. Loader Makes Partial Progress Then Stops

Inspect **networking from staging to lab nodes**, TLS/auth, free disk, streaming sessions, I/O errors, and compaction. If source files came from only one production node, missing token coverage is a separate problem from stream timeouts.

Do not blindly restart the loader infinitely when partial data may already be loaded. Understand idempotency/duplicate behavior for your tool, data timestamps, and target state. For critical datasets, standing up a **fresh empty lab target** for a clean controlled retry can be safer.

### 16.3. SELECT Does Not Return Expected Rows

Possible causes:

1. Backups omitted the partition or source token range coverage was incomplete.
2. Snapshot predated the row write.
3. TTL expired by recovery day.
4. Row is shadowed by a tombstone with a newer timestamp.
5. Wrong schema or import path.
6. Query used wrong key/CL or replicas are unhealthy.
7. Missing incremental/backup files.

Never conclude "loader succeeded so restore is right" without checking data against these failure modes.

### 16.4. Lab Runs Nearly Out of Disk After Loading

Streaming, flushes, and compaction can hold both old and new SSTables simultaneously; moreover, snapshots, logs, and staging may share the same volume. Check `df`, `du`, and configured storage paths; throttle/pause imports safely if needed.

**Never delete Cassandra-managed SSTables to free space** and never delete original backups before ensuring independent copies remain usable.

### 16.5. Restore Succeeds Technical Checks Yet Business State Is Inconsistent

For instance, `orders_by_id` shows `SHIPPED` while `orders_by_customer` shows `CONFIRMED`. This signals cross-table snapshots were skewed in time, or the source app was already out of sync prior to backup.

Inspect restore points, business event logs, and dual-table update logic, then build a **reconciliation plan**. Never blindly apply a "whichever table looks newer wins" rule without understanding timestamps, event order, and side effects.

## 17. Especially Dangerous Operational Mistakes

| Misconception or Action | Risk | Replacement Principle |
|---|---|---|
| Pointing `sstableloader -d` at a production IP | Loads stale backup data into the live cluster | Restrict network allowlists to lab and verify cluster identity |
| Copying system keyspaces / host IDs from production | Collides identities and token metadata | Stand up empty cluster with fresh identity |
| Using one node's snapshot to restore a whole keyspace | Missing token ranges and many partitions | Verify coverage across all required sources |
| Creating today's schema and loading very old SSTables | Mismatches or altered semantics | Rebuild schema at the restore point and evaluate transitions |
| Treating snapshots as arbitrary millisecond PITR | Misses RPO | Use rehearsed incremental/commit-log/upstream logs |
| Ignoring TTLs and tombstones | Miscounts rows or resurrects deleted data | Validate timestamp/TTL/delete semantics |
| Running `COUNT(*)` on huge tables as a "quick check" | Full scans, cluster load, and timeouts | Use sampling, checksums, and controlled reconciliation jobs |
| Deleting old SSTables manually when disk fills | Data loss or corrupted table state | Capacity planning, runbooks, and monitoring |
| Comparing post-loader SSTable file hashes with original snapshots | Comparing the wrong layer because loader rewrites bytes | Hash source-to-staging files; use logical checksums post-import |
| Giving the restore app production credentials/endpoints | Data leaks or accidental live writes | Separate secrets, configs, and access controls |
| Declaring recovery successful after a single SELECT | Misses partitions, tables, and invariants | Validate across full scope and business criteria |
| Using `repair` to undo a `DELETE` | Repair syncs current state; does not replay history | Restore from independent backups and reconcile |
| Letting the lab run CDC/outbound jobs | Side effects on downstream systems | Sandbox or disable integrations |

## 18. Measuring RPO, RTO, and "Restore Successful" Criteria

### 18.1. RPO Must Be a Verified Commitment

Suppose data was deleted at **10:00 UTC** and the latest valid snapshot is **08:30 UTC**. Without matching incrementals/commit-log/upstream replay, recoverable data can only be expected around snapshot time (subject further to distributed snapshot skew).

~~~text
Incident time:             10:00 UTC
Snapshot restore point:    08:30 UTC
Nominal gap:               90 minutes

Never claim RPO <= 5 minutes merely because
sstableloader is fast or the lab cluster is UP.
~~~

**RPO** is the acceptable business data loss in a failure scenario—not just snapshot file age. Factor in unflushed mutations, skewed backups, TTLs, and availability of incremental backups.

### 18.2. RTO Must Include Verification

Time breakdown example:

| Step | Hypothetical Duration |
|---|---:|
| Provision infra and verify isolation | 25 minutes |
| Fetch/copy backups and verify checksums | 50 minutes |
| Create schema and verify compatibility | 20 minutes |
| Stream SSTables into lab | 95 minutes |
| Reconcile data and validate applications | 35 minutes |
| **Total drill duration** | **225 minutes (3 hours 45 minutes)** |

These figures are illustrative, not a Cassandra SLA. Define when the RTO clock starts per organizational convention and when the environment counts as **ready for use**. A loader printing "100%" does not mean the business has recovered.

### 18.3. Five Tiers of Recovery Proof

- **Level 1 – File validated:** backups exist with matching checksums.
- **Level 2 – Schema loaded:** keyspace/table/UDTs match and the lab cluster is ready.
- **Level 3 – Data loaded:** loader/refresh finished without critical errors.
- **Level 4 – Logical validation passed:** sample data, key coverage, TTL/delete semantics, and invariants pass.
- **Level 5 – Application rehearsal passed:** apps connect to lab, critical queries/DAOs run, RPO/RTO and integration safety are confirmed.

**A trustworthy backup is one that is regularly restored and verified**, not merely a job reporting "SUCCESS."

## 19. Exercises and Scenarios with Answers

### Question 1 — Why Not Restore Directly into Production?

An operator wants to import an old snapshot into a live table currently receiving new mutations. What can go wrong?

**Answer:** New and old data collide via timestamps/tombstones; imported data can shadow or be shadowed by other mutations, yielding unpredictable states. The operation risks disrupting the live system. Always restore into a lab first and establish a clear data reconciliation plan.

### Question 2 — Is a Single Node's Snapshot Enough?

A keyspace has RF=3 across six nodes. You save only node A's snapshot and want to restore the whole keyspace. Is coverage guaranteed?

**Answer:** No. Node A holds only the token ranges assigned to it. Ensure sources cover all partitions and all relevant tables.

### Question 3 — Single-Node Lab with RF=3

You create a `NetworkTopologyStrategy` keyspace with `restore_dc:3` on a one-node lab, then read at `LOCAL_QUORUM`. What is the risk?

**Answer:** The lab lacks enough replicas/nodes for that RF. Quorum requirements may fail. Either scale lab nodes or set an RF matching test goals while documenting limitations compared to production.

### Question 4 — Snapshots and TTL

A row is written at 08:00 with a 3600-second TTL, snapshotted at 08:30, and restored at 12:00. Is the row guaranteed to remain visible?

**Answer:** No. TTLs expire relative to original write time; snapshots do not freeze TTL clocks. The row may already have expired before restore.

### Question 5 — Checksums Match Yet SELECT Finds No Data

Name three causes to investigate.

**Answer:** Wrong/missing token coverage, incompatible schema, expired TTL, tombstones shadowing the row, snapshot predating the write, incomplete import, or wrong query key/CL. File checksums confirm copy integrity only, not logical data completeness.

### Question 6 — sstableloader vs. refresh

When loading a snapshot into a lab cluster whose token placement differs from source, which tool generally fits better?

**Answer:** `sstableloader`, because it streams data according to the target cluster's replica placement. `nodetool refresh` is a local import and does not distribute data across multiple nodes automatically.

### Question 7 — Keyspace Tables Skewed Across Checkpoints

`orders_by_id` and `orders_by_customer` show different statuses even though both came from snapshots sharing the same tag. Is the backup definitely corrupted?

**Answer:** No. Snapshots across different nodes/tables do not guarantee a globally consistent transaction. Inspect timing, write flows, and business invariants.

### Question 8 — Point-in-Time Recovery

Snapshot at 08:00, incident at 10:00. To recover to exact 09:59, can you just rename the snapshot tag to 09:59?

**Answer:** No. Tag names do not alter file contents. You need a version-verified, consistency-checked chain of backups/incrementals/commit-log archiving or upstream event replay.

### Question 9 — Only 1 Order Matches

One `SELECT` returns O123 accurately; can you declare the whole keyspace recovered?

**Answer:** No. Verify multiple partitions/token ranges, multiple tables, sampling and logical checksums, TTLs/tombstones, and business invariants.

### Question 10 — Restore Took 95 Minutes, Validation Added 35 Minutes

In Section 18's RTO example, counting provisioning, copying, schema, and validation, is rehearsal RTO 95 minutes or 225 minutes?

**Answer:** 225 minutes (3 hours 45 minutes) under the illustrative drill definition. Streaming time alone is not total recovery time.

### Question 11 — How to Guarantee Zero Side Effects?

A new restore cluster uses production accounts and seeds, and services auto-start scheduled email jobs. Is it safe just because it runs on different machines?

**Answer:** No. Isolate networks, seeds, cluster identity, credentials, contact points, and integrations. Disable or sandbox jobs/webhooks/CDC so no real external actions occur.

### Question 12 — Different File Hashes After Import

SSTable checksums in the lab differ from original snapshots, while sample data matches. Is that proof of backup corruption?

**Answer:** No. Loaders/compaction rewrite SSTables at the byte level. Use file checksums between **source and staging**, and verify imported data via logical checks/invariants.

## 20. Completion Checklist and Operations Report

~~~text
RESTORE REHEARSAL SUMMARY
-------------------------
Incident / rehearsal ID:
Source backup/snapshot tag:
Source cluster version:
Target isolated cluster_name / DC:
Scope (tables/keyspace):
Schema version / migration notes:
RF / consistency used for validation:
Backup file count and checksum verification:
SSTableloader/refresh method and tool version:
Loaded tables / token coverage:
Streaming, compaction and disk health:
Sample keys checked / logical checksums:
TTL and delete/tombstone validation:
Cross-table application invariants:
Data gaps and known limitations:
Start/end UTC:
RPO achieved / not achieved / unknown:
RTO measured:
Production isolation verification:
Side effects disabled:
Rollback/cleanup plan for lab:
Reviewers / approval:
~~~

When completing the report, clearly distinguish **PASS**, **FAIL**, and **UNKNOWN**. If source snapshot completeness could not be verified, never mark `PASS` just because sample row counts matched. If data is lacking to prove RPO, mark **UNKNOWN** and recommend additional backup/restore drills.

## 21. Summary

For Apache Cassandra, **restoring a table or keyspace into an isolated environment** is a multi-step workflow—never just copying files or running a single `nodetool` command:

1. **Define scope and restore point** before touching backups; know whether you need one table or a full keyspace.
2. **Isolate the lab cluster from production** across networks, seeds, host IDs, disks, credentials, and external integrations.
3. **Verify backup coverage** across all token ranges, tables, metadata, checksums, and version compatibility.
4. **Build schema matching the snapshot** and RF fitting lab topology; a single-node lab does not validate production quorums.
5. **Favor placement-aware import mechanisms**, such as `sstableloader` where appropriate, instead of manually dropping SSTables onto nodes.
6. **Understand point-in-time limits:** snapshots are not global transaction cuts; TTLs keep ticking; PITR demands tested extra mechanisms.
7. **Reconcile both data and business logic:** key coverage, values, deletes/tombstones, denormalized tables, and real Java queries.
8. **Measure RPO/RTO end-to-end**, including provisioning, copying, importing, and validation.
9. **Never auto-push data back into production.** Any next step after a rehearsal requires its own change plan, owner, and rollback plan.

A recovery drill succeeds when operations can answer with evidence: **"I know which backups were used, which data was recovered, what limits remain, how long it took, and that test actions never touched the production cluster."**
