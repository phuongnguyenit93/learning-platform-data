# sstableloader and Input Data Compatibility Requirements

> **Chapter:** Operational Tools  
> **Scope:** Apache Cassandra — a distributed *wide-column* database with LSM/SSTable storage, partition keys, replication, and consistency levels. This lesson guides how to use **`sstableloader` to load data from existing SSTables into a cluster**, emphasizing source-target compatibility requirements, verification workflows, failure modes, and cross-checking via CQL/Java Driver 4.x.
>
> **Objectives:** Understand what `sstableloader` does and does not do; verify **SSTable format, Cassandra version, partitioner, schema, TTL/tombstone data, token placement, and network/authentication**; and design a controlled bulk-load workflow without breaking data correctness on a live cluster.

## 1. Scenario: You Have an SSTable Directory—How Do You Load It Into a New Cluster?

An operations team has a snapshot of table `orders_by_customer_day` from an older Cassandra cluster. They need to load that data into a new cluster running in a different datacenter. The snapshot directory contains files like:

```text
.../lab/orders_by_customer_day-<table-id>/snapshots/export-01/
  na-1-big-Data.db
  na-1-big-Index.db
  na-1-big-Statistics.db
  na-1-big-TOC.txt
  ...
```

Prefixes, SSTable IDs, and component lists in this example are **illustrative only**; they vary by version and format. A real SSTable is a **set of companion components**, not a standalone `Data.db` file.

The team's initial plan is to copy the files into a target node's data directory and restart. That approach is very risky:

- Token placement may differ between source and destination clusters.
- A single node does not own every partition in the snapshot.
- The destination table may have different column definitions, clustering keys, or codecs.
- Running Cassandra manages SSTables, indexes, and read/compaction states internally.
- Simply copying files does not distribute replicas according to the replication factor (RF).

**`sstableloader` solves the data transfer part:** it reads SSTables from a properly organized source directory and **streams data to the appropriate target replicas based on the destination cluster's token ranges**. However, it **does not rewrite schemas, convert arbitrary legacy SSTables, or prove imported data has no conflicts**.

> Rule: **Source data must be readable and semantically compatible with the destination schema before running `sstableloader`.**

## 2. What Tool Is `sstableloader`?

`sstableloader` is commonly called an SSTable **bulk load** tool. It ships with the Cassandra distribution matching your release. Its purpose is to take pre-built SSTable data and distribute it via streaming into a running cluster.

Conceptual flow:

```text
Prepared, immutable SSTable source
        |
        | Reads SSTable format and metadata
        v
Host running sstableloader
        |
        | 1. Connects/discovers target cluster and schema
        | 2. Resolves target token ranges/replicas
        | 3. Streams SSTable data to appropriate nodes
        v
Target Cassandra cluster
        |
        +--> Replica R1: receives owned token range slice
        +--> Replica R2: receives copy per RF
        +--> Replica R3: receives copy per RF
        |
        v
SSTables integrated and serving reads
(after streaming/validation/health verification)
```

This is a logical diagram, not a literal wire protocol diagram. Connection mechanics, endpoint selection, whole-SSTable vs. section streaming, progress reporting, and configuration flags vary by Cassandra release.

### What It **Can** Do

- Ingest data from offline SSTables into a live cluster without issuing row-by-row `INSERT` statements from an application.
- Distribute data according to **destination token ownership and replication strategy**, rather than assuming one directory belongs to one node.
- Support restoring or reusing SSTable-exported data within a controlled migration or recovery workflow.
- Transfer large datasets using Cassandra's internal streaming mechanism, subject to version/format support.

### What It **Does Not** Do Automatically

- Does not create keyspaces/tables, change partition keys, rename columns, or convert CQL data types.
- Does not translate SSTables across **arbitrary** pairs of Cassandra versions/formats.
- Does not recover data missing across all source replicas.
- Does not resolve business logic around duplicate events, idempotency, or concurrent write conflicts.
- Does not provide a table-wide atomic transaction: if a job fails after streaming part of the data, you must manage partial-load state.
- Does not replace scheduled repair, backup strategies, or post-topology replica checks.
- Does not turn a single node's snapshot into a full cluster copy if that node did not own all token ranges.

## 3. Comparing `sstableloader` with Alternatives

| Tool / Mechanism | Data Source | When Commonly Used | What Cannot Be Equated |
| --- | --- | --- | --- |
| **`sstableloader`** | Pre-built SSTables in a valid source layout | Bulk loading into a live cluster, routing by destination tokens | Does not create schemas or convert all formats |
| **`nodetool refresh`** | SSTables placed in the proper import location **on a specific node** | Adopting local SSTables under supported conditions | Does not distribute data across all replicas like bulk streaming |
| **`nodetool repair`** | Live cluster replicas holding ranges | Reconciling diverged replicas or missed mutations | Not a tool for importing an external backup folder |
| **`nodetool rebuild`** | Live source replicas, typically in another DC | Populating a node in a new topology | Does not ingest an arbitrary offline SSTable folder from a workstation |
| **SSTable backup/restore** | Snapshots, incremental backups, commit logs where available | Restoring per backup runbook and RPO/RTO | Requires selecting point-in-time, version, and consistency |
| **CQL import / bulk ETL** | CSV/JSON or logical business records | Changing schemas, altering partition keys, cleaning data | Distinct CQL parse/write cost; requires idempotency design |

If you must change the `PRIMARY KEY` or convert a `text` column to `timestamp` in business logic, the right path is usually **logical read → transform → write to new table**, not forcing `sstableloader` to read old SSTables as if they matched the new table.

## 4. Why Check Compatibility Before Loading?

SSTables store Cassandra's on-disk representation along with metadata for decoding cells, timestamps, tombstones, and index components. The target cluster uses its **CQL schema** and partitioner to interpret and route that data.

A set of SSTables can sit on disk with the exact same name as the destination table yet remain **semantically incompatible** with it.

Example:

```text
Source:
PRIMARY KEY ((customer_id, event_day), event_time, event_id)
payload text

Target:
PRIMARY KEY ((customer_id), event_day, event_time, event_id)
payload text

Same column names, different partition key!
-> Must NOT bulk load directly as the same table.
```

This is not merely a performance issue. Partition tokens are computed from **partition key values and structure**. Changing the partition key causes data to be misinterpreted or misrouted; logical migration is required.

### Minimum Compatibility Matrix

| Component | What to Verify / Match | What to Do If Different |
| --- | --- | --- |
| **Cassandra version** | Whether source SSTable format is readable/streamable by loader and destination | Use supported upgrade/conversion paths or logical import; never guess from filenames |
| **SSTable format & components** | All required components present, uncorrupted, valid format | Verify on a copy; retake a clean snapshot if missing/corrupt |
| **Partitioner** | Token algorithm on source/target, e.g., `Murmur3Partitioner` | Do not assume loader converts partitioners; use logical migration if incompatible |
| **Keyspace/table** | Expected source names and existing destination schema | Create/align schema via CQL per runbook before loading |
| **Partition key** | Identical columns, order, and data types | Logical migration to a new table if different |
| **Clustering columns/order** | Identical clustering columns, order, and comparator types | Do not load directly if row representation differs |
| **Column types** | CQL types, collections, tuples, UDTs, serialization metadata | Transform logically if formats do not decode compatibly |
| **Static/regular columns** | Column roles, schema evolution / dropped columns | Inspect table definition/metadata; do not just compare names |
| **Timestamp/TTL/tombstone** | Reconciliation rules, expiration, and deletion semantics | Define overwrite/retention policy; validate post-load data |
| **Replication/topology** | RF/DC, token ownership, and target node states | Fix topology/replication and capacity before streaming |
| **Auth/TLS/network** | CQL metadata access and internode streaming connections | Verify credentials and connectivity from loader host to every target |

Source and target do not need identical physical hardware or settings. However, any difference affecting **how data is decoded or how row/cell identity is determined** must be resolved prior to import.

## 5. Cassandra Version and SSTable Format Requirements

### Comparing Version Strings Is Not Enough

Operations teams often ask: "Source is Cassandra 3.x, target is 4.x; can we run `sstableloader`?" The answer cannot rely on major numbers alone:

- Releases can use **different SSTable formats**.
- Tools from one release can read some older formats, though not necessarily every format.
- Certain transitions require an **SSTable upgrade** step before moving data.
- Streaming/network/auth protocols between loader and target nodes also carry compatibility constraints.

**Never run an arbitrary `sstableloader` found on `PATH`.** Select a tool package whose version and format compatibility are verified for your source-target pair, ideally tested first on a matching-version lab cluster.

### What Metadata Should Be Recorded?

Before migrating, record in your checklist:

```text
Source Cassandra release:
Source partitioner:
Source SSTable format/generation:
Source keyspace/table and table schema:
Destination Cassandra release:
Destination partitioner:
Destination table schema:
Loader version:
Validation result on representative snapshot:
```

Prefixes like `na-...-Data.db` or `nb-...-Data.db` **are not a complete compatibility contract**. Use release-appropriate SSTable metadata tools; names, flags, and outputs can vary by version.

### When Format Conversion Is Needed

Tools like `sstableupgrade` exist for supported SSTable format upgrades. Never run them against the sole snapshot of critical data without keeping an untouched original/backup and runbook:

- Do not assume an "upgrade" tool can downgrade formats for an older target release.
- Never run mutating tools directly on live data files of a production node.
- Do not assume format upgrade alone suffices: **schema, partitioner, and timestamp semantics** must still match.
- Budget disk cost, conversion time, and rollback steps.

When source and target diverge too far, **CQL/ETL export-import** is often cleaner and safer despite higher processing cost.

## 6. Schema Requirements: What Must Stay Identical?

### Example Source Schema for Practice

Suppose keyspace `lab` exists and both environments share an equivalent schema:

```cql
CREATE TABLE IF NOT EXISTS lab.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    note text,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

From partition key `(customer_id, order_day)`, Cassandra computes the token for each customer's daily partition. Rows inside the partition are ordered by `created_at` and `order_id`.

The target needs a **compatible schema**, especially on:

- `customer_id` and `order_day` with identical types and order as the partition key.
- `created_at` and `order_id` with identical order, types, and clustering semantics.
- `status`, `amount`, and `note` decoded with matching types.
- Any previously dropped/renamed columns evaluated alongside schema history metadata.
- Compatible nested type definitions if the table uses UDTs or complex collections.

A table with the same name defined as:

```cql
PRIMARY KEY ((customer_id), order_day, created_at, order_id)
```

no longer shares the same partition model. Even if CQL columns look visually similar, it **is not a safe target for the original SSTables**.

### More or Fewer Columns in the Schema?

When a table undergoes `ALTER TABLE`, Cassandra handles schema evolution. Never assume adding or dropping columns automatically lets every old SSTable load cleanly:

- A new column missing from source SSTables may read as unset/null; verify behavior for your specific types and config.
- A **dropped** column carries drop-time metadata affecting how old imported data is read.
- Incompatible type changes can cause SSTable decoding errors or silent misreads.
- UDTs and collections have distinct serialization and update rules.

**Safe practice:** create the target table with a verified schema, load a **small but representative snapshot sample**, and verify every column type—plus deleted/TTL rows—via CQL before bulk loading.

### Table IDs and Physical Layout

Cassandra data directories typically embed an internal ID alongside the table name, such as `orders_by_customer_day-<table-id>`. Some tools read **keyspace/table names from the directory layout**, while metadata resides inside SSTable components.

Do not rename directories or table IDs by guesswork just to make the tool "accept" files. Check the exact directory layout expected by **your running `sstableloader` version**; never treat an old cluster's table ID as proof it matches the target table.

## 7. Partitioner and Token Ownership: Foundational Prerequisites

Cassandra distributes partitions by tokens computed from partition keys via the partitioner. Most clusters use `Murmur3Partitioner`, though you must never assume every cluster matches without checking.

Distinguish two layers:

1. **Schema partition key:** the columns and types defining how key bytes are serialized.
2. **Partitioner/token placement:** the token function and the ring nodes owning ranges in the target cluster.

`sstableloader` reads SSTables and routes data to target replicas based on destination token ownership. It is not an arbitrary transformer from a table with partition key A to one with partition key B.

### What If RF or Node Count Differs?

RF and topology **do not have to match the source**. A completely valid use of bulk load is moving logical data into a new cluster with different node counts or RF—provided **schema and partitioner align**—letting data distribute according to target ownership.

Example:

```text
Source cluster: dc-old, RF=3, 4 nodes
Target cluster: dc-new, RF=3, 8 nodes

Same partitioner + compatible schema
          |
          v
sstableloader resolves replicas for token ranges in target cluster
          |
          v
Data streams to target replicas, rather than copying node-1 files to node-1
```

If target RF is not yet applied or topology is still bootstrapping/rebuilding, loading while ownership is unsettled complicates verification. Stabilize topology first and verify coverage afterward.

## 8. Preparing Source SSTables: Never Grab Live Files Haphazardly

SSTables are immutable once flushed, yet **a node's live SSTable set changes when compaction deletes or replaces files**. Copying files mid-compaction risks missing components or capturing an inconsistent directory snapshot.

### Where Should Source Files Come From?

Standard sources are **managed SSTable snapshots**, or exports/staging sets built via Cassandra-supported workflows. Example on a **lab** source node:

```bash
nodetool flush lab orders_by_customer_day
nodetool snapshot -t export-01 lab
nodetool listsnapshots
```

`flush` writes the table's memtables to SSTables so the snapshot captures recent mutations; `snapshot` creates local SSTable references. Check version-specific table flags and snapshot contents via `nodetool help snapshot`. The example above snapshots the **`lab` keyspace**; in practice, scope to specific tables if supported.

**A snapshot on one node is not a cluster-wide transactional snapshot.** If a node replicates only part of the ring, its snapshot contains only the data that node holds; exporting an entire keyspace requires a **token/replica coverage plan** or full-scope backup process.

### Why Stage and Keep an Untouched Original?

Safe workflow:

1. Take the snapshot once mutations prior to the cutoff are flushed.
2. Locate the exact table snapshot directory.
3. Copy/stage **all SSTable components** using a method that preserves bytes and required metadata.
4. Keep the original untouched; never run mutating SSTable tools on the sole snapshot copy.
5. Verify checksums, file counts, and sizes to catch copy truncation.
6. Use only the staged copy for `sstableloader` tests or format conversion if needed.

If point-in-time recovery after the snapshot timestamp is required, **commit log replay and backup timelines** are separate mechanisms. `sstableloader` does not automatically replay mutations written after the snapshot.

### Never Mix Files from Multiple Formats or Tables Arbitrarily

Never dump SSTable components from multiple tables into one folder expecting the loader to sort them out by content. Preserve **filenames, per-SSTable component sets, and the keyspace/table layout supported by your loader**.

*Illustrative* staging layout on a staging host:

```text
/srv/cassandra-import/
└── lab/
    └── orders_by_customer_day-<table-id>/
        ├── <descriptor-A>-Data.db
        ├── <descriptor-A>-Index.db
        ├── <descriptor-A>-Statistics.db
        ├── <descriptor-A>-TOC.txt
        ├── <descriptor-B>-Data.db
        ├── <descriptor-B>-Index.db
        ├── ...
        └── ...
```

This layout is not guaranteed across every release. `sstableloader` inspects keyspace/table names from **the input path**; some versions accept snapshot paths directly if structured properly. Check `--help` and test on staging. **Never rename SSTable components manually** just to mimic an example.

## 9. Does Source Data Actually Cover All Token Ranges?

Single-node snapshots are easily misunderstood in RF>1 clusters:

- One source node stores only the partitions it replicates, not the whole keyspace.
- A snapshot taken while a replica was offline or stale may lack mutations received by peers.
- When multiple source nodes have overlapping token ranges, SSTables may hold different versions of the same cell; Cassandra applies timestamp/tombstone reconciliation, not "latest file by name".
- If a source purged tombstones before an older replica reconciled, deleted data can resurrect on load.

Build a **coverage map**:

| Question | Required Evidence |
| --- | --- |
| Which source nodes/replicas are included? | Per-node snapshot inventory |
| Which ranges does each source own? | Token ownership and topology at snapshot time |
| Are all needed partitions covered? | Full-range coverage or verified logical source |
| Were source replicas synchronized? | Repair history, offline node status, capture time |
| Did mutations occur after snapshot? | Cutover plan, logs/replay/dual-writes/reconciliation |
| Does imported data overlap existing target rows? | Merge/overwrite policy by timestamp and restore goals |

**Streaming one file cleanly only proves that file was transferred**—it does not prove the source set represents all business data.

## 10. TTL, Tombstones, Timestamps, and Data Conflicts

This is the easiest area to get wrong when bulk loading into an existing cluster.

### TTL Does Not "Restart Its Clock" on Import

Mutations written with `USING TTL` embed expiration metadata. Loading an old SSTable **must not be treated as a fresh INSERT whose TTL starts counting from import day**.

Example:

```text
Day D:   write event with 7-day TTL
Day D+5: take snapshot
Day D+6: load SSTable into new cluster
Day D+7: event hits logical TTL expiration

Never assume 7 full days remain starting from D+6.
```

If a snapshot is too old, many TTL cells may already be expired before loading. In that case, a successful load does not guarantee those cells appear in target queries.

### Original Timestamps Govern Version Reconciliation

Cassandra uses cell/mutation timestamps and reconciliation rules to pick winning values. Suppose:

```text
Imported SSTable: status='PENDING' @ timestamp 100
Target cluster:   status='PAID'    @ timestamp 200

After import:
- Do not expect 'PENDING' to overwrite 'PAID' merely because import ran later.
- The newer timestamp 200 mutation can still win on read.
```

Timestamps here are illustrative integers showing older vs. newer ordering, not literal valid CQL timestamps. Cassandra also applies tie-break and tombstone rules on equal timestamps; never design an import relying on "whichever file ran last".

### Tombstones Can Block Older Data

If a snapshot contains tombstones, they may stream alongside data depending on SSTable state and compaction timing. Tombstones must remain intact past safety bounds before GC. Conversely, if a snapshot lacks critical tombstones, loading older versions risks resurrecting deleted rows.

**Never set `gc_grace_seconds=0` or manually strip tombstones to speed up import.** On data with previously offline replicas, doing so increases zombie data risk.

### Time and Clock Skew

Cassandra write timestamps can come from clients or servers depending on mutation policy. Two clusters with skewed clock histories risk unintuitive write ordering.

Before merging source SSTables into a live target table:

- Compare source and target data timestamps and client-generated timestamp policies.
- Verify clock synchronization across apps and nodes.
- Decide explicitly between **merge**, **full backup replacement**, or **migration into an empty table**.
- Plan how concurrent writes during streaming are handled.

**Bulk load is not a business upsert enforcing event ordering.**

## 11. Data Types and Features Requiring Special Checks

### Collections and UDTs

SSTables can contain `list`/`set`/`map` collections, UDTs, or tuples. Decoding depends on schema and format.

- `frozen` and non-frozen collections differ in representation and update semantics.
- Target UDTs must match compatibly, including field names and types.
- Updated or deleted collection elements carry element/collection tombstones that must be preserved.
- Never load old collections into a modified schema merely because JSON dumps look similar.

### Counters

Counters use specialized distributed update mechanics and state; counter SSTable snapshots cannot be treated like ordinary scalar columns and merged arbitrarily into a live table.

For counter tables, require a **migration workflow explicitly supported and tested on your Cassandra version**. If accuracy cannot be guaranteed, consider exporting logical values and redesigning or following release-documented recovery steps. Never test `sstableloader` on production counters merely because the tool accepts the format.

### LWT, Paxos, and Conditional Operations

SSTable bulk loading bypasses row-level `INSERT ... IF NOT EXISTS` or `UPDATE ... IF ...` consensus logic. If an application relies on LWT/`LOCAL_SERIAL` or Paxos state to enforce invariants, plan write pauses/limits and compatible state checks. **Never treat bulk loading as serialized CAS operations.**

### Indexes, SAI, Materialized Views, and CDC

When tables use secondary indexes, Storage-Attached Indexes (SAI), materialized views, or CDC:

- Check Cassandra version/features on both source and target.
- Verify whether indexes/views/CDC are built or re-synced properly after SSTables stream.
- Run index rebuild/validation or backfills if required by your release runbook.
- Never run a primary-key `SELECT` alone and claim all index/view query paths work.
- Never expect bulk SSTable import to emit **all CDC events** the way normal CQL writes through the commit log do.

Exact behavior varies by feature and release; always test index/view queries and real CDC pipelines.

## 12. Network, Authentication, and Access Requirements

`sstableloader` needs more than one target IP. It typically requires:

1. **Initial contact** to discover the cluster, schema, and token ownership.
2. **Streaming connections** to every endpoint owning target ranges.
3. **Accounts and permissions** if authentication is enabled.
4. **TLS/encryption** matching cluster CQL/internode policies.
5. Proper DNS/routing/firewalls/ports **from the loader host to every node that can be a stream target**.

Key failure example:

```text
Loader host reaches contact point C1 over native transport.
Yet R2 and R3 have private IPs unroutable from the loader host.
-> Schema discovery may succeed.
-> Streaming to target replicas fails.
```

Never equate "CQL port 9042 works" with "every stream target is reachable". Ports and protocols vary by version and config; audit actual network rules instead of punching wide firewall holes.

### Keep Passwords Out of Command History

Some versions accept username/password arguments or config files. To avoid credential leaks:

- Check `sstableloader --help` for your running release.
- Prefer supported credential mechanisms that keep secrets out of command lines and process lists where possible.
- Lock down config/certificate file permissions and never commit secrets to source control.
- Never paste credentials into runbooks/logs and avoid overly broad superuser accounts.

Examples in this lesson **omit inline passwords**.

## 13. Choosing an Import Strategy: Empty Cluster, Live Cluster, or New Table?

| Target State | Primary Risk | Recommended Strategy |
| --- | --- | --- |
| **New, empty cluster/table** | SSTable/schema compatibility, missing token ranges, expired TTLs | Create compatible schema, verify source/coverage, bulk load, validate |
| **Cluster with live serving table** | Old/new timestamp conflicts, tombstones, concurrent writes | Plan merge logic, freeze/coordinate writes, or load into a new staging table |
| **Target needs full data replacement** | Bulk load does not delete target rows absent from source | Use proper restore/swap/replace runbook; do not treat import as truncate+restore |
| **Target changes partition key/types** | No safe SSTable mapping | Logical ETL/CQL migration with validation |
| **Target adds a datacenter** | RF/ownership changes, incomplete history | Compare `nodetool rebuild` vs. offline bulk load per topology runbook |
| **Recovering after node disk loss** | Wrong node identity/tokens and source replicas | Prefer supported replace/rebuild/restore over arbitrary file import |

**Loading into a fresh empty table** is generally easier to verify than overlaying a live table receiving updates, though you still must plan read routing, application cutover, and permissions.

## 14. Step-by-Step Lab Procedure

Suppose you want to load SSTables for `lab.orders_by_customer_day` into a **test target cluster** with a compatible schema.

### Step A — Inspect the Target Cluster

```bash
nodetool status
nodetool describecluster
```

In `cqlsh` connected to the target cluster:

```cql
DESCRIBE KEYSPACE lab;
DESCRIBE TABLE lab.orders_by_customer_day;
```

Confirm the keyspace/table exist, key columns/types match the source, and RF/DC are configured properly. If keyspace `lab` does not exist yet in the lab, create it per designed replication strategy; **never blindly copy source RF** if target topology differs.

Example for **one** DC named `dc1` with at least three suitable nodes:

```cql
CREATE KEYSPACE IF NOT EXISTS lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
```

This is a schema-setup example; do not use `dc1` or RF=3 if your lab cluster does not match. Never default to `SimpleStrategy` for multi-DC deployments.

### Step B — Confirm Table Definition

```cql
CREATE TABLE IF NOT EXISTS lab.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    note text,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

**`IF NOT EXISTS` does not verify schema match!** If the table already exists with a different definition, this statement will not reshape it. Always run `DESCRIBE TABLE` and compare with the source.

### Step C — Prepare Source Data

On a source lab cluster with the matching table, create sample mutations:

```cql
INSERT INTO lab.orders_by_customer_day
    (customer_id, order_day, created_at, order_id, status, amount, note)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21',
    '2026-11-21T03:00:00Z',
    11111111-1111-4111-8111-111111111111,
    'PAID',
    250.00,
    'source-row'
);

INSERT INTO lab.orders_by_customer_day
    (customer_id, order_day, created_at, order_id, status, amount, note)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21',
    '2026-11-21T03:01:00Z',
    22222222-2222-4222-8222-222222222222,
    'PENDING',
    125.00,
    'ttl-row'
) USING TTL 86400;
```

Then flush and snapshot on the source lab node using supported tools:

```bash
nodetool flush lab orders_by_customer_day
nodetool snapshot -t export-01 lab
nodetool listsnapshots
```

Reminder: on a multi-node source cluster, **a snapshot on one node does not cover all ranges**. Exporting a full table genuinely requires a complete source coverage plan and concurrency protection.

### Step D — Verify Files on the Staging Host

On the host holding the SSTable copy, verify:

```text
[ ] Keyspace/table directories follow the layout required by loader.
[ ] All components of each SSTable are present.
[ ] No files mixed in from other tables.
[ ] Separate untouched original backup and checksum/inventory exist.
[ ] Loader version can read the SSTable format.
[ ] Source and target partitioner and schemas are compatible.
[ ] Target has headroom, RF/DC, and stable token ownership.
[ ] Network/auth/TLS tested to all streaming endpoints.
```

Use the matching-release SSTable metadata tool if available; never edit files just to make metadata "look nicer". Check help:

```bash
sstableloader --help
```

If your binary uses `-h` instead of `--help`, check your actual release's help first.

### Step E — Run the Load from the Staging Host

Illustrative command **without credentials**:

```bash
sstableloader -d 192.0.2.10,192.0.2.11 \
  /srv/cassandra-import/lab/orders_by_customer_day-<table-id>
```

Where:

- `192.0.2.10` and `192.0.2.11` are documentation addresses—replace them with real target cluster contact points.
- `-d` specifies initial hosts for cluster discovery, **not an exhaustive list of all replicas that will receive writes**.
- The final directory holds SSTable components with a name/layout **accepted by your loader version**.
- `<table-id>` is a placeholder, not literal characters to type verbatim.
- With authentication/TLS enabled, pass credentials/TLS flags supported by your tool version.

This example does not replace compatibility testing. **Never load a production snapshot into another production cluster on the basis of a one-liner.**

### Step F — Monitor the Import

On target nodes:

```bash
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool tablestats lab.orders_by_customer_day
```

Correlate telemetry:

- Active/succeeded/errored streaming sessions and bytes sent/received.
- Source/destination disk read/write latency and headroom.
- CPU, GC, network saturation, and application write/read p95/p99.
- SSTable count, compaction backlog, and node states.
- Scoped load results; save loader stdout/stderr and timestamps.

A tool exiting with partial errors or incomplete source token coverage **must not be declared a successful migration**.

## 15. Verifying Data with CQL

For the test partition:

```cql
SELECT created_at, order_id, status, amount, note,
       TTL(note), WRITETIME(note)
FROM lab.orders_by_customer_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_day = '2026-11-21';
```

Verification checks:

1. Both events appear with expected keys/values while still live.
2. `decimal`, `uuid`, `date`, and `timestamp` columns decode accurately.
3. `WRITETIME(note)` reflects the live value's original write timestamp, not magically reset to bulk-load time.
4. `TTL(note)` on the TTL row reflects **remaining lifetime**, not reset at import time.
5. If TTL has already expired by check time, the row/cell may no longer appear live—**do not blindly conclude the loader skipped the file**.

### How Best to Reconcile Source and Target Data?

| Check | Value | Limitations |
| --- | --- | --- |
| Compare **sample partitions** across token ranges | Catches wrong columns/types/TTL/values | Does not prove every range is complete |
| Check source and target **coverage** | Catches unexported/unloaded ranges | Requires complete topology and source inventory |
| Compare row counts across chosen partition sets | Catches missing/duplicate logic in samples | Avoid full-table `COUNT(*)` |
| Compare values, timestamps, remaining TTL | Catches merge/expiry/schema bugs | Timestamps may differ if ETL rewrote mutations |
| Check index/SAI/view read paths (if any) | Verifies secondary query paths post-load | Depends on index rebuild/version behavior |
| Check p95/p99 and timeouts under real read load | Ensures data can be served | Does not prove data completeness alone |

**Full-table `SELECT COUNT(*)`** is not an ideal verification: it can be extremely expensive, proves nothing about individual partitions/ranges, and risks impacting production.

### Verify Deleted Data Too

If business logic relies on deletes, include samples of deleted/TTL-expired rows. Post-import resurrection of old values can stem from:

- Snapshots missing needed tombstones.
- Unsynchronized or stale source replicas.
- Import merging with older timestamps/values at target.
- Unsafe repair/GC grace history.

Never respond with blanket `DELETE` runs before understanding the cause and impact scope.

## 16. Java Driver 4.x: Post-Import Verification via Business Queries

Java applications must prove bulk-loaded data serves **partition-key queries** cleanly at target consistency levels.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.metadata.Node;

public final class ImportedOrdersCheck {
    private final CqlSession session;
    private final PreparedStatement byDay;

    public ImportedOrdersCheck(CqlSession session) {
        this.session = session;
        this.byDay = session.prepare(
            "SELECT created_at, order_id, status, amount, note " +
            "FROM lab.orders_by_customer_day " +
            "WHERE customer_id = ? AND order_day = ? LIMIT ?"
        );
    }

    public List<UUID> fetchOrderIds(UUID customerId, LocalDate day) {
        BoundStatement statement = byDay.bind(customerId, day, 100)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setPageSize(100);

        ResultSet result = session.execute(statement);
        Node coordinator = result.getExecutionInfo().getCoordinator();

        List<UUID> ids = new ArrayList<>();
        for (Row row : result) {
            Instant createdAt = row.getInstant("created_at");
            UUID orderId = row.getUuid("order_id");
            String status = row.getString("status");
            BigDecimal amount = row.getBigDecimal("amount");
            String note = row.getString("note");

            if (orderId == null || createdAt == null) {
                throw new IllegalStateException("Imported row missing expected key");
            }
            ids.add(orderId);
            System.out.printf(
                "%s %s %s %s %s%n",
                createdAt, orderId, status, amount, note
            );
        }

        System.out.println("Rows=" + ids.size()
            + " coordinator_dc="
            + (coordinator == null
                ? "unknown" : coordinator.getDatacenter()));
        return ids;
    }
}
```

Assumes `CqlSession` is configured with the right local datacenter, contact points, auth/TLS, and keyspace, and RF in the coordinator DC supports `LOCAL_QUORUM`. This snippet verifies one partition—**it does not prove the entire load is complete**. Never print real personal/order data into production logs; use test data, masking, and proper sampling.

One successful request only proves enough replicas satisfied that CL. To confirm all replicas post-bulk-load, track streaming/repair and verify scope per runbook rather than running a single `LOCAL_ONE` SELECT.

## 17. Resource Impact and Throttling Import Speed

Because `sstableloader` relies on streaming, it can contend with live workloads:

- **Source host disk reads:** reading SSTables, metadata, checksums/formats.
- **Network:** multiple streams pushing to target replicas.
- **Replica disk writes:** receiving SSTable data plus integration/compaction work.
- **CPU:** compression/decompression, validation, serialization, metadata handling.
- **Memory:** buffers and JVM activity on loader and target nodes.

A heavy load can also leave elevated SSTable counts and compaction backlogs lingering after the command exits.

### Do Not Optimize Only for MiB/s

A sound objective:

```text
High useful import throughput
           AND
Business p95/p99 and error rate within SLO
           AND
No disk exhaustion / compaction stall
           AND
Data verified accurate and complete
```

Some `sstableloader` releases expose a streaming throttle flag; verify the exact flag name and **units** via `--help`. Never copy a value like `200` from another release's command and assume it means 200 MiB/s.

A typical safe schedule:

1. Test a small representative SSTable batch.
2. Measure p95/p99, throughput, disk/network, and compaction backlog.
3. Raise limits or worker count cautiously, avoiding hammering the same replicas from too many loaders at once.
4. Throttle back or reschedule if live APIs breach SLO.
5. After loading finishes, keep monitoring compaction and disk; never close the ticket merely because progress hit 100%.

## 18. Partial Imports, Retries, and Idempotency

### When the Loader Fails Mid-Run

Some SSTables may already have streamed and integrated before failure. Recovery requires:

- Saving logs, file lists, versions, target nodes, and error scope.
- Determining which nodes/ranges received data via streaming evidence.
- Fixing network/auth/disk/format causes before retrying.
- Testing retry behavior for your tool/version in a **test environment**, especially if the target table already holds data.
- Re-verifying logical data/timestamps/TTL and replica coverage after retry.

**Never assume a failed load rolls back atomically.** Nor should you assume retrying the same SSTable creates a fresh business row: Cassandra keys rows by primary key and reconciles cells by timestamp, yet side effects/indexes/CDC and partial-load state still require checks.

### Why Is Retrying Not Simply "Run It Again"?

If imported data carries older timestamps while the target table receives newer writes:

- Multiple versions of a key may coexist; timestamps decide which reads win.
- Tombstones may mask older versions.
- TTLs may have expired before the retry.
- CDC/indexes/views or business pipelines may lack true "exactly-once" semantics.

When you need to **exactly replace a snapshot** rather than merge, use a dedicated runbook with staging tables/swaps/routing and agreed write cutoffs. The loader has no magic "make target table 100% identical to snapshot" switch.

## 19. Common Errors and How to Diagnose Them

### Error A — Tool Reports Unsupported SSTable Format

**Possibilities:** source/loader/target versions are incompatible, or an SSTable component is corrupt.

**Check:** source Cassandra release, SSTable format, tool version, and file components. Test on a lab, use supported format conversion/ETL paths, and never rename prefix `na` to `nb`.

### Error B — Keyspace or Table Not Found

**Possibilities:** target schema not created yet, wrong input directory name/layout, or loader version parses table names differently than expected.

**Check:** `DESCRIBE KEYSPACE/TABLE` on target, staging path, and loader layout rules. Never alter table IDs or rename directories to another table without verifying schema compatibility.

### Error C — Invalid Schema / Column / Type Mismatch

**Possibilities:** mismatched partition/clustering keys, differing column types, or incompatible schema evolution.

**Check:** full `CREATE TABLE` on both sides, dropped columns, UDTs/collections. If keys or types genuinely changed, switch to logical ETL rather than forcing old SSTables into a new table.

### Error D — Contact Point Connects, Yet Streaming Fails

**Possibilities:** loader host cannot reach all streaming endpoints, or firewall/TLS/internode protocols differ from expectations.

**Check:** all target node addresses published in topology, version-specific ports/protocols, network routes, and node logs. Never test `cqlsh` to one host and assume full network readiness.

### Error E — Insufficient Permissions or TLS Mismatch

**Possibilities:** auth requires different credentials, untrusted certificates, or incompatible encryption policies.

**Check:** credential/certificate mechanisms supported by loader, role permissions, and specific error logs. Never disable TLS in production just to import faster.

### Error F — Out of Disk on Receiving Replicas

**Possibilities:** underestimated SSTable bytes/RF, temporary compaction files, or snapshots pinning space.

**Check:** per-node SSTable size, RF, headroom, active/total disk space, and snapshots. Expand capacity or adjust schedule; never manually delete SSTables or commit logs.

### Error G — Loader Succeeds, Yet Queries Return No Data

**Possibilities:** query uses wrong partition key, TTL expired, different target schema/table, partial load, or older imported timestamps masked by newer target data.

**Check:** query sample keys, check `TTL`/`WRITETIME`, stream logs/coverage, and table metadata. Never conclude an imported file was ignored from a single `SELECT`.

### Error H — Primary Key Reads Work, Yet Index/View Queries Miss Data

**Possibilities:** secondary index/SAI/materialized view has not updated/rebuilt per version procedure.

**Check:** index/view queries, metrics, and release-specific build/rebuild docs; do not check only the base table.

### Error I — Deleted Data Reappears

**Possibilities:** stale source, missing tombstones, unsafe snapshot/repair history, conflicting timestamps, or older data elsewhere.

**Check:** `DELETE` history, `gc_grace_seconds`, source replica health, snapshot files, and timestamps. This is a correctness bug—pause cutover and investigate before expanding import.

### Error J — Import Degrades Live Read/Write APIs

**Possibilities:** network, disk, compaction, or streaming concurrency contending with live traffic.

**Check:** `netstats`, `compactionstats`, `tpstats`, disk await, CPU/GC, and per-node p99. Reduce concurrency/throttle or shift windows while tracking migration deadlines.

## 20. Post-Import Verification and Handover Workflow

A practical runbook should enforce three gates.

### Gate 1 — **Compatibility Proven**

- [ ] Recorded source version, loader version, target version, and SSTable format.
- [ ] Partitioner, partition key, clustering key, and column/UDT types are compatible.
- [ ] Target keyspace/table exist, with valid RF/DC and token ownership.
- [ ] Source snapshot is immutable, with complete components and required ranges.
- [ ] Verified TTL, tombstones, timestamps, and special features.
- [ ] Auth/TLS/network plan verified with zero secret exposure.

### Gate 2 — **Controlled Streaming Completed**

- [ ] Tested small SSTable batch and measured p95/p99 impact.
- [ ] Source and target nodes maintained resource headroom.
- [ ] Logs capture per-batch outcomes, errors, and retries clearly.
- [ ] Zero unresolved failed sessions remain.
- [ ] Compaction was not arbitrarily altered/disabled and data files were not deleted to "free space".
- [ ] Rollback or return-to-source plan exists if data validation fails.

### Gate 3 — **Data and Application Verified**

- [ ] Sample partitions across multiple token ranges match expected keys/values.
- [ ] Data types, collections/UDTs, TTL, and timestamps read back accurately.
- [ ] Deleted/expired rows do not unexpectedly resurrect.
- [ ] Indexes/SAI/views and CDC pipelines (if any) verified per release.
- [ ] Reviewed repair/replica coverage and streaming consistency.
- [ ] Java Driver uses right local DC/CL; API p95/p99, timeouts, and errors meet SLO.
- [ ] Agreed on cutover, rollback, and source write cutoff if migrating.

**One `Data.db` finishing transfer is not the completion criterion.** Success means data is semantically accurate, landed on the right replicas, serves business queries properly, and respects SLOs.

## 21. Misconceptions to Avoid

**"`sstableloader` is just `COPY` for CQL data."** False. It handles SSTables and streaming, requiring storage and schema compatibility.

**"Same table name means it will load."** False. Partition/clustering keys, column types, partitioner, and schema history all matter.

**"Copying just `Data.db` is enough."** False. SSTables consist of companion components; missing/corrupt metadata prevents reading.

**"A snapshot from one replica is a cluster-wide snapshot."** False. It holds only the partitions and versions that specific node stored.

**"Loading onto the first node suffices for RF=3."** False. `sstableloader` uses token placement/streaming to reach target replicas; manual copy to one node does not distribute data.

**"Different target RF makes bulk load impossible."** Not necessarily. RF/topology can differ as long as schema/partitioner/format match and loader routes properly.

**"TTL resets at import time."** False. Expiration metadata inside original SSTables governs; cells can expire before or right after load.

**"A later SSTable import overwrites all target data."** False. Cassandra reconciles via timestamps and rules, not wall-clock time when loader ran.

**"Loading a snapshot replaces the whole existing table."** False. Importing does not automatically delete target rows absent from the snapshot.

**"No need to check tombstones since SELECT hides deleted rows."** False. Tombstones govern correctness and zombie data risk.

**"All nodes `UN` guarantees the loader streamed to every replica."** False. Gossip health does not guarantee source coverage or successful stream sessions.

**"Reading a few rows with `LOCAL_ONE` proves restore is complete."** False. You must verify token ranges, multiple replicas, and business queries.

**"Skip index/CDC checks because primary-key CQL works."** False. Secondary features may require dedicated post-streaming steps.

**"Increasing streaming throttle always makes migration safer."** False. Importing contends for CPU/disk/network and can spike app p99.

## 22. Exercises and Interview Scenarios

1. Explain the difference between `sstableloader` and `nodetool refresh` when loading SSTables from a staging host into a multi-node cluster.
2. Why can you not bulk load directly between two tables both named `orders_by_customer_day` if their partition keys differ?
3. An SSTable from an older Cassandra release uses a format unsupported by the loader. Name two safe approaches and explain why renaming files is not a solution.
4. In an RF=3, 6-node cluster, does a snapshot on node N1 cover the entire keyspace? How do you check?
5. Why can source and target have different RFs yet still perform a valid bulk load when compatible?
6. A record with a 7-day TTL was written 6 days ago. Does importing it today grant 7 more days of life? Why or why not?
7. Target table has `status='PAID'` at a newer timestamp than source `status='PENDING'`. Which value will likely be read after merge, and why?
8. When the source contains tombstones while an old target replica was offline long, what risk must import watch out for?
9. Why might bulk loading fail to emit CDC events like a normal CQL write? What should you do if business logic requires replaying events?
10. What special precautions apply if a table uses `counter`, LWT, or materialized views?
11. A loader connects to the contact point yet times out while streaming. Which network/auth layers should you inspect?
12. Target already holds data, yet the business wants it "identical to Day D's snapshot". Why does bulk load alone not fulfill this requirement?
13. Why is full-table `SELECT COUNT(*)` not an optimal bulk-import verification?
14. A source snapshot has many expired TTL cells. Why can the loader succeed while fewer rows are readable than expected in the files?
15. How do you use `nodetool netstats`, `compactionstats`, `tpstats`, and the Java Driver to detect when an import degrades SLOs?
16. Propose a recovery strategy when a loader job fails mid-way without assuming atomic rollback.
17. Design a compatibility checklist covering source version, loader version, partitioner, schema, SSTable format, TTL/tombstones, and UDTs.
18. Why should you not load SSTables directly into a table whose partition key was redesigned? Propose an alternative ETL flow.
19. In a multi-DC cluster, why verify per-DC RF, streaming network, and CQL results per Java Driver local DC before cutover?
20. Newly loaded data answers primary-key queries correctly yet index queries miss rows. Which feature and workflow will you inspect?

## 23. End-of-Lesson Decision Flowchart

```text
          HAVE SSTABLES TO LOAD INTO TARGET CLUSTER
                           |
                           v
           Does source cover needed data/token ranges?
                 |                    |
                No                   Yes
                 |                    |
      Supplement source/repair        v
      or restore backup         Version/format readable?
                                     |         |
                                    No        Yes
                                     |         |
                             Supported         v
                             Upgrade/ETL    Schema + partitioner compatible?
                                                   |         |
                                                  No        Yes
                                                   |         |
                                          Logical CQL       v
                                          migration     Policy for TTL/tombstone/
                                                        conflicts in place?
                                                        |       |
                                                       No      Yes
                                                        |       |
                                               Design merge    v
                                               or staging   Check network/
                                                            auth/RF/capacity
                                                                   |
                                                                   v
                                                       Dry-run on staged copy
                                                                   |
                                                                   v
                                                       Controlled bulk load
                                                                   |
                                                                   v
                                                Verify ranges, data, APIs,
                                                indexes/CDC, and rollback
```

**Remember:** `sstableloader` **streams existing SSTables into a Cassandra cluster according to destination token ownership**. It is valuable for bulk imports, yet **does not automatically turn source SSTables into schema-compatible CQL data**. Only load after verifying **format/version, schema/partitioner, source completeness, RF/topology, TTL/tombstones/timestamps, auth/network, and post-load serving health**. A successful migration means **semantically accurate, complete data on safe replicas without breaking business SLOs**—not merely a "stream completed" message.
