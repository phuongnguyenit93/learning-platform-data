# sstableloader, File-Based Restore, and Topology/Version Verification in Apache Cassandra

> **Chapter:** Backup and Recovery  
> **Scope:** Restoring Apache Cassandra data from SSTable snapshots/incremental backups using `sstableloader` or loading SSTables locally with `nodetool import`/`refresh`; verifying version compatibility, schema, table ID, partitioner, token ownership, datacenters, and replication factor before opening traffic. Examples reference Cassandra 4.1/5.0 and Java Driver 4.x; data-mutating commands should be executed only in labs or under an approved production runbook.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **SSTable backups/snapshots**, **incremental backups**, **commit logs**, **anti-entropy repair**, **rebuild**, and **restore**; understand when each tool helps recover data.
2. Explain how `sstableloader` **streams token ranges** to a running cluster according to its **current replication strategy**; distinguish it from `nodetool import`/`refresh` loading files directly on individual nodes.
3. Build a **pre-restore checklist** covering Cassandra/SSTable format version, partitioner, schema and table ID, source/target topology, per-DC RF, TTLs/tombstones, backup completeness, and checksums.
4. Prepare the exact directory layout for `sstableloader`, verify `--nodes`, TLS/auth, streaming ports, throttling, and monitor per-replica errors.
5. Build a runbook for **per-node file-based recovery** without blindly dropping SSTables into live data directories or skipping token ownership checks.
6. Explain why **being able to read data after restore** does not prove all replicas are accurate, and why older SSTables can be shadowed by newer tombstones/timestamps.
7. Practice a **non-destructive** restore by streaming a snapshot from one lab table into a matching-schema table in a separate target keyspace.
8. Verify post-restore state using CQL, tracing/metrics, business-source cross-checks, and the Java Driver at appropriate consistency levels.

The core focus of **`DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`** is the **distributed wide-column** architecture: partition key → token → natural replicas; CQL/schema defines data meaning; CL governs required responses. **Recovery must satisfy all three layers**, not just `*-Data.db` files.

## 2. Recovery Method Map: Never Pick the Wrong Tool

| Scenario | Typically Appropriate Tool/Approach | Why? | What It Does Not Solve |
|---|---|---|---|
| Have SSTable backups, want to load into a cluster with **different node count/RF/DC** | **`sstableloader`** | Fetches target ring and streams data slices to natural replicas per target placement | Does not auto-fix logically bad data or timestamps/tombstones |
| Have SSTable backups for **one node**, topology/table compatible, need local file load | **`nodetool import`** (preferred in newer releases) | Loads SSTables on the invoked node with optional validation/token checks | Does not automatically distribute SSTables to remaining replicas |
| Valid SSTables already placed in live table directory; need Cassandra to pick them up | **`nodetool refresh`** (legacy/deprecated in bulk loading docs) | Loads newly placed files without restarting solely for refresh | No token-aware streaming; copying into live directory carries risks |
| One node dies while other replicas hold good data | **Replace/rebuild node** per topology runbook | Streams back ranges the new node must own | Cannot detect if data was lost on **all** replicas |
| A replica merely missed mutations; data/tombstones remain elsewhere | **Anti-entropy repair** | Reconciles and synchronizes replicas | Does not replace backups/PITR when data is lost everywhere |
| Accidental `DELETE` or all replicas hold bad state | **Restore into isolation, reconcile audit, then logical recovery** | Requires an independent source of truth and timestamp/tombstone handling | Running repair or streaming old backups does not auto-undo `DELETE` |
| Want recovery to an exact past second | Backup + designed **CDC/event log/commit-log workflow** | Requires controlled mutation chains and cutoff timestamps | Snapshot + incremental SSTables alone **do not guarantee arbitrary PITR** |

**Quick selection rule:** When topology differs or you want to avoid manually placing files on each node, prefer `sstableloader`. When importing **local files onto a specific node** with known compatible token ranges/schema, evaluate `nodetool import`. Never choose `refresh` over streaming just because the command looks shorter.

### 2.1. Two Planes of Recovery

~~~text
                 BACKUP FILES (SSTables)
                           |
         +-----------------+------------------+
         |                                    |
    sstableloader                        import / refresh
         |                                    |
  Queries target cluster                Targets a SPECIFIC NODE
  ring / replication                    where files are loaded
         |                                    |
  Splits token ranges and               Checks files, schema,
  STREAMS to replicas                   ownership on that node
         |                                    |
         +-----------------+------------------+
                           |
                   CQL data verification
                   + replica coverage
                   + business audit
~~~

These two paths are **not equivalent**: `sstableloader` dispatches data across the cluster by placement; `import`/`refresh` does not turn a local file into a fully distributed replica set. The effect of restoring old files into a populated table also depends on **write timestamps, TTLs, and tombstones**, not just the tool.

## 3. What Actually Resides Inside a Cassandra Backup

### 3.1. An SSTable Is a Set of Files, Not One `Data.db` File

Cassandra stores flushed data as **immutable SSTables**. One SSTable has multiple components sharing the same generation/format, such as:

~~~text
<prefix>-Data.db               Partition/cell data
<prefix>-Index.db              Component index (when format uses it)
<prefix>-Statistics.db         Metadata, timestamps, and statistics
<prefix>-Summary.db            Index summary helper (when present)
<prefix>-Filter.db             Bloom filter (when present)
<prefix>-CompressionInfo.db    Compression metadata (if compressed)
<prefix>-Digest.crc32          Format-specific checksum/digest
<prefix>-TOC.txt               List of SSTable components
~~~

Components **vary across SSTable formats and releases** (e.g., BIG/BTI), so do not assume every SSTable contains the exact names in this example. When copying for restore, preserve the **entire valid component set for the same generation**, rather than copying only `Data.db` and hoping the engine regenerates the rest.

### 3.2. Snapshots and Incremental Backups

| Type | How Created? | Includes | Exclusions / Losses to Watch |
|---|---|---|---|
| **Snapshot** | `nodetool snapshot` creates hard links to flushed SSTables | Node-local SSTables at snapshot time; usually `schema.cql` and `manifest.json` | Not automatically cluster-atomic; excludes unflushed mutations if `--skip-flush` |
| **Incremental backup** | When enabled, flushed/streamed SSTables get hard links in `backups/` | New SSTables after flushes; supports backup chains | Does not automatically hold full schema DDL; restore needs baseline snapshot/matching schema |
| **Commit log** | Mutation log for single-node crash recovery | Appended mutations per durability settings | Not automatically an organized long-term/PITR historical backup |
| **CDC / event audit** | Separately configured pipeline | Can serve as mutation replay source if retention and completeness suffice | Does not automatically cover every table/mutation or global business order |

Snapshots create **hard links**, so a snapshot on the same filesystem can still perish with the disk, be deleted, or suffer ransomware/host loss. **Trustworthy backups** must be copied independently to separate storage with checksum verification, access controls, retention, and periodic restore tests.

### 3.3. Snapshots Are Node-Local, Not "Whole Cluster at T"

~~~text
Cluster RF=3:
     Node A        Node B        Node C
       |             |             |
  Snapshot 10:00  10:01       10:02
       |             |             |
   SSTables A     SSTables B     SSTables C

A mutation at 10:01 may appear in only a subset
of snapshots depending on flush/replication timing.
~~~

For a **business-level restore point**, engineer consistency across tables/nodes and writers: consider brief write quiescing, event-stream checkpoints, or orchestrated backups with clear RPO. Never invoke `nodetool snapshot` several times and claim you have an atomic global snapshot.

### 3.4. RPO/RTO Targets Must Be Stated Upfront

- **RPO (Recovery Point Objective):** maximum recent data acceptable to lose. Restoring a 10:00 snapshot at 12:00 can miss valid mutations between those points unless replayed.
- **RTO (Recovery Time Objective):** maximum acceptable time to restore service, including fetching backups, verifying, streaming/importing, compaction/repair, and traffic cutover.
- **Retention:** how long backups are kept, whether off-node copies exist, and whether readability is tested.
- **Restore scope:** recovering one key, one table, one DC, or the entire cluster; broader scopes make atomicity harder to promise.

**Never promise "RPO=0" just because RF=3.** Replication protects availability/single-node loss as designed; if an accidental `DELETE` replicates to all three, RF=3 faithfully preserves the mistake across all three.

## 4. Manifest: Mandatory Evidence Before Loading SSTables

Every backup set needs an **operationally generated manifest** so original context is never lost. This differs from the `manifest.json` Cassandra may generate inside a snapshot directory.

| Field Group | Example | Why Needed? |
|---|---|---|
| Backup ID/time | `orders-2026-11-21T10Z`, UTC | Pick the exact recovery point and assess TTL |
| Source Cassandra | Version + distribution + SSTable format | Check whether target can read/stream |
| Source schema | DDL, schema digest, table ID, UDTs, indexes | Avoid loading mismatched partition keys or column types |
| Source partitioner | `Murmur3Partitioner` | Token calculation must match |
| Source topology | DC/rack, node IDs, tokens, per-DC RF | Know which node owned the files and what must be combined |
| Dataset | Keyspace/table, data dirs, generations/components | Avoid mixing files from two tables or runs |
| Backup completeness | Node/table/volume list, full snapshot + increments | Avoid restoring from just one of three replicas |
| Integrity | Post-copy file checksums, file count/byte count | Catch dropped or corrupted files during transfer |
| Security | Key ID/encryption, access control, location, owner | Decrypt without exposing sensitive data |
| Logical checks | Expected key set, sample partition counts, audit event IDs | Verify *business accuracy*, not just import success |
| Restore method | `sstableloader` vs. `import`, target cluster/DC/KS | Prevent operators from loading into the wrong target |

### 4.1. Verifying Integrity on an Independent Copy

Example shell commands **only on a staging directory holding copies**, never reading files actively managed by the engine:

~~~bash
# Lab example paths; never run against live data directories.
find /srv/restore-staging -type f -name '*-Data.db' -print
find /srv/restore-staging -type f -name '*-TOC.txt' -print
du -sh /srv/restore-staging

# Compare checksums against independent manifest recorded at backup time.
sha256sum /srv/restore-staging/restore_target/orders/*-Data.db
~~~

Checksums prove only that **bytes copied accurately at backup time**, not that logical data is right. If backups already contained bad or incomplete replica data, checksums still pass. When SSTable corruption occurs, use **version-accurate** verification tools on offline copies and never modify the original backup set.

## 5. Comparing Source and Target Topology

### 5.1. Why Are Tokens/RF/DC Part of the Restore Plan?

Source vs. target example:

~~~text
Source:                              Target:
  dc1 (3 nodes, RF=3)                  dc1 (4 nodes, RF=3)
    A -- B -- C                          P -- Q -- R -- S

  Partition key tenant-a                Same partition key tenant-a
  -> token t                            -> token t
  -> natural replicas A,B,C             -> natural replicas
                                         recomputed on ring P,Q,R,S

SSTables from A do not belong to "A" forever.
Restoring onto a new ring must use the TARGET's placement.
~~~

**`sstableloader`** queries the target cluster for its token/ring map and streams SSTable slices to target natural replicas per keyspace replication. It excels when node counts, token allocations, or RF change. **`nodetool import`** loads locally on **one node**, so the operator must ensure the files hold tokens owned by that target node or follow another placement-preserving plan.

### 5.2. Topology Details to Record Before Restoring

| Question | Command / Source | Consequence If Skipped |
|---|---|---|
| Are target ring nodes UP/NORMAL? | `nodetool status`, `describecluster` | Streaming into a cluster missing replicas |
| What is per-DC keyspace RF? | `DESCRIBE KEYSPACE`/`system_schema.keyspaces` | Wrong replica count or wrong DC |
| Does partitioner match source? | `cassandra.yaml`/JMX/config inventory | Incompatible token calculation and placement |
| Have token ranges/natural endpoints changed? | `nodetool ring`, `getendpoints` for sample keys | Direct file copy lands on non-owning node |
| Are bootstrap/decommission/replace active? | `nodetool status`, `netstats` | Shifting topology mid-restore; streaming contention |
| Are other DCs involved? | `NetworkTopologyStrategy` and target ring | `LOCAL_QUORUM` in one DC does not validate another DC |
| Which local DC do driver/apps use? | Java Driver config | Read verification might check only one DC |

Observation commands:

~~~bash
nodetool version
nodetool status
nodetool ring
nodetool describecluster
nodetool netstats
nodetool getendpoints restore_target orders tenant-a
~~~

`getendpoints` returns expected natural endpoints for a keyspace, table, and partition key from the queried node's perspective; it **does not prove** those endpoints actually hold SSTables or recovered data. For composite partition keys, check your `nodetool` release's key representation syntax instead of guessing an arbitrary string.

### 5.3. Multiple Datacenters and Replication Strategy

~~~sql
-- Illustrative configuration for a two-datacenter cluster.
CREATE KEYSPACE restore_target
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3',
  'dc2': '2'
};
~~~

If source used RF=3 in one DC while target uses RF=3/2 across two DCs, `sstableloader` loads per **target replication**. Stream/space/network volume can be larger than expected. Check cross-DC bandwidth and TLS/storage ports; tune `--throttle-mib`/`--inter-dc-throttle-mib` to actual capacity and loader version.

**Never increase RF and assume new replicas automatically received historical data.** When target keyspace RF changes after restore, follow version-specific repair/rebuild runbooks and verify all new replicas.

### 5.4. Topology Checklist Before Local File Import

A `nodetool import` on node P should run only after verifying:

- P belongs to the target cluster and has the matching local table/schema.
- Imported SSTables hold token ranges owned by P on the **target ring**; use import token checks rather than bypassing them by default.
- Remaining replicas are recovered via matching backup/streaming/repair if required.
- Node P has sufficient disk headroom and no competing heavy imports/compactions.
- You do not confuse a coordinator node with every node that must hold data.

Never pass `--no-tokens` just to silence token ownership errors without an explicit range-migration design. A successful local import holding misplaced tokens still leaves CQL missing data or breaks replica placement.

## 6. Checking Cassandra Version, SSTable Format, Schema, and Table ID

### 6.1. "Both Are Cassandra" Does Not Guarantee SSTable Compatibility

SSTables have their own **formats/versions**, independent of CQL version. Cassandra 4.x and 5.0 also differ in storage engine features, BIG/BTI formats, metadata, and offline tooling. Before restoring, check:

| Component | Source | Target | Decision |
|---|---|---|---|
| Cassandra release | 4.1.x / 5.0.x… | 4.1.x / 5.0.x… | Consult official upgrade/compatibility matrix |
| SSTable format/version | Prefix/`sstablemetadata`/manifest | Reader/loader binary | Can target binary read/stream this format? |
| Partitioner | `Murmur3Partitioner`, etc. | Target config | Same token hashing? |
| CQL schema | Column names/types, primary key, UDTs | Target DDL | Will file bytes decode properly? |
| Table ID | UUID in directory/`schema.cql` | Current UUID | Copying into right table instance for local restore? |
| Serialization/compression | Compression, UDTs, SSTable codecs, encryption | Available libraries/keys | Can components be read and decrypted? |
| Indexes/views | SAI/2i/materialized view schema | Target structures | Need separate rebuild/reconciliation? |
| DDL history | Was the table dropped/recreated/altered? | Current schema | Same name, or actually the same logical structure? |

**Never load SSTables from a newer release directly onto an older binary** just because `CREATE TABLE` succeeded. Newer SSTable formats may be unreadable by older readers. Across major versions, plan **SSTable conversion on a copy** per version docs before restoring, and test in staging.

### 6.2. `sstableupgrade` Is Not a "Run It Blindly" Command

Apache provides **`sstableupgrade`** to rewrite SSTables into the format supported by the running binary; 5.0 docs also discuss snapshot upgrades when using snapshots from older major versions.

Keep in mind:

- This **rewrites files**, consuming CPU/disk/temp space and potentially affecting hard links to original snapshots.
- Offline tools generally require **Cassandra not to be running concurrently on the source data directory**; copy to an isolated environment and verify versions.
- Never use Cassandra 5.0 to "downgrade" SSTables for an older cluster without an official compatibility matrix and restore testing.
- Choose between `sstableupgrade` and `nodetool upgradesstables` based on offline vs. online goals and binary docs—they are not interchangeable.

**Safe path:** keep immutable originals → copy to staging → check reader/format → upgrade **on the copy** if supported → test loading into an equivalent lab cluster → verify CQL and SSTable metadata → only then roll out production runbooks.

### 6.3. Same Table Name, Different Table ID

Cassandra stores table files in directories typically shaped like:

~~~text
/var/lib/cassandra/data/
  shop/
    orders-51b4...<table-uuid>/
      mb-1-big-Data.db
      snapshots/backup-tag/
        mb-1-big-Data.db
        schema.cql
        manifest.json
~~~

This is **schematic**; actual SSTable prefixes and UUIDs vary by version. If you `DROP TABLE shop.orders` and `CREATE TABLE shop.orders` with identical DDL, the **new table ID** will differ. Copying files directly into an old directory will not make Cassandra map them to the new table.

Distinguish:

- **`sstableloader`:** resolves target by keyspace/table (or target-keyspace flag where supported) and streams across the cluster; avoids assuming source table ID must match target table ID.
- **`nodetool import`:** takes explicit target keyspace and table plus an SSTable directory; still requires format/schema/token compatibility.
- **Manual copy + `refresh`:** files must land in the **exact target table-ID directory** on the target node without colliding component filenames; higher risk.

Some snapshot `schema.cql` files include `WITH ID = <uuid>`. When restoring a dropped table, understand the implications of preserving vs. changing IDs—especially if old directories, snapshots/backups, or applications still reference the schema. Never paste production snapshot DDL into another cluster **without inspecting** table IDs, UDTs, indexes, and keyspace replication.

### 6.4. Schema Agreement Does Not Mean Complete Data

Seeing matching DDL in `DESCRIBE TABLE` or driver metadata confirms only **logical structure**. It does not prove:

- Every node received SSTables from the backup.
- Every range in the target DC received streaming.
- TTLs/tombstones do not hide older rows.
- Derived tables/SAI/indexes are consistent.

Require three independent verification layers: **valid schema → valid placement/copy → valid business data**.

## 7. `sstableloader`: Mechanics, Flags, and Dangerous Assumptions

### 7.1. When to Choose `sstableloader`

Appropriate when:

- Restoring snapshot/incremental SSTables into a **running** target cluster.
- Source and target differ in node count, RF, rack/DC layout, or token ranges.
- You want to stream via Cassandra protocol so the target determines natural replicas.
- You need to remap **target keyspace** (in supported loader versions) or stage under target keyspace/table names.

Unlike `nodetool import`, operators do **not** have to copy SSTables into live directories on every replica. Still, the loader needs a **complete, compatible source file set**, reachable endpoints, staging read permissions, and adequate target capacity.

### 7.2. `sstableloader` Pipeline

~~~text
COPY of SSTable files (staging, NOT live active SSTables)
                   |
              sstableloader
                   |
       CQL/native port -> queries initial host
                   |
          Token map + target RF/DC
                   |
       Splits SSTables into token sections
                   |
         +---------+----------+
         |         |          |
      Replica P Replica Q  Replica R
         |         |          |
    SSTables streamed/received on target
         |         |          |
         +---------+----------+
                   |
              CQL reconciliation
             + repair as needed
~~~

**`--nodes` is not a single destination storing all data.** It lets the loader connect and fetch the ring; target endpoints are determined by actual placement. Launching multiple loaders against the same cluster can cause streaming bursts, so throttle concurrency, network, and disk.

### 7.3. Core Syntax and Staging Directory Layout

~~~bash
# Check help only; changes no data:
sstableloader --help

# Sample command using a staging path, NOT a live data directory:
sstableloader \
  --nodes 10.10.1.11,10.10.1.12 \
  --throttle-mib 16 \
  /srv/restore-staging/shop/orders
~~~

Per bulk loading docs, the loader by default infers **keyspace and table from the parent directories** of the SSTable path:

~~~text
CORRECT for target shop.orders:
  /srv/restore-staging/shop/orders/
    nb-1-big-Data.db
    nb-1-big-Index.db
    nb-1-big-Statistics.db
    ...

AVOID passing the raw snapshot path as default target:
  /var/lib/cassandra/data/shop/orders-<uuid>/snapshots/tag-01/

Because parent directory names will be misinterpreted:
  "snapshots"/"tag-01" is not shop.orders.
~~~

**`--nodes`/`-d` is required.** Do not treat `--nodes` as listing every replica needing data as a substitute for ring awareness; it only needs reachable initial hosts, plus network reachability to all endpoints the loader discovers.

### 7.4. Key Options

| Option | Effect | What to Know |
|---|---|---|
| `-d, --nodes` | Initial hosts (comma-separated) | Required; pass appropriate target IPs/hostnames |
| `-p, --port` | Native CQL port (usually 9042) | Used to connect/fetch ring, distinct from streaming storage port |
| `-sp, --storage-port` | Internode streaming port (usually 7000) | Firewalls/TLS must match cluster |
| `-ssp, --ssl-storage-port` | SSL storage port per config | Cross-check version/network policy |
| `-f, --conf-path` | `cassandra.yaml` for SSL/streaming params | Use a **controlled config file**, never blindly point to production configs holding secrets |
| `-u, --username` and credentials | Authentication | Avoid leaking passwords in shell history or process lists |
| `--throttle-mib` | Stream rate cap in MiB/s | Do not pass `0` if wanting a limit—0 means unlimited |
| `--inter-dc-throttle-mib` | Cross-DC throughput cap | Useful for multi-DC loads; version-dependent |
| `-k, --target-keyspace` | Override target keyspace where supported (Cassandra 4.0+) | Does **not** rename target table; check binary help |
| `-v, --verbose` | Verbose progress/logging | Increases log volume; ensure no credentials leak in output |

Never confuse native CQL port `9042` with streaming port `7000/7001`: a host may reach `9042` and still fail streaming if storage ports are blocked. Internode encryption configs vary in newer releases; **do not hard-code 7000/7001**—verify on the target cluster.

### 7.5. File Source Requirement: Independent Staging

`sstableloader` docs describe it as an offline SSTable tool and warn against running directly against data actively mutated by Cassandra. Bulk loading docs simultaneously confirm the loader **streams to a running target cluster**.

Safe operational interpretation:

1. **The target cluster can keep running and serving CQL.**
2. **Source SSTables must be stable copies** from snapshots/incremental backups in a staging directory independent of live data directories—never let Cassandra compaction alter/delete files while the loader reads them.
3. When running other **offline SSTable tools** to inspect/upgrade files, obey requirements to stop Cassandra on that data directory or run on **copies on an isolated host**.
4. Never point `sstableloader` directly at a live, active SSTable directory on a production node.

There is zero contradiction between "running target" and "offline source files": **each side plays a different role**.

### 7.6. What the Loader Does Not Do

- Does not run `CREATE TABLE`; target schema must exist and be compatible.
- Does not know "which business record is truest" when backups carry bad versions.
- Does not ingest CSV/JSON directly; inputs must be valid SSTables.
- Does not turn **one node's** snapshot into full coverage of all token ranges if that node held only part of the dataset.
- Does not synchronize **other denormalized tables** maintained by the app.
- Does not delete source SSTables after streaming; manage staging/retention separately.
- Does not certify that backups suffice to recover to an arbitrary timestamp.

## 8. Safely Preparing File Sets for `sstableloader`

### 8.1. Selecting Recovery Point, Schema, and SSTable Set

Suppose snapshot `bk_20261121_1000` covers `shop.orders` across source nodes. Plan:

1. Gather the snapshot and incremental SSTables **truly belonging to the chosen recovery point**.
2. Confirm table/partitioner/schema in the snapshot; never mix generations from another table.
3. Confirm target loader can read the SSTable format.
4. Audit **source coverage** across token ranges/replicas, including any dead nodes.
5. Copy each SSTable component of the same generation to staging **as real copies**, not hard links sitting on the source data disk.
6. Build manifests/checksums and ensure sufficient disk space on staging and receivers.

### 8.2. Copying into Staging with Target Keyspace/Table Names

Shell example on a **lab/staging** host:

~~~bash
# Example variables; substitute verified real snapshot paths.
SNAP_DIR="/backup-external/backup-id/shop/orders/snapshots/bk_20261121_1000"
STAGING="/srv/restore-staging/shop/orders"

mkdir -p "$STAGING"
chmod 700 "$STAGING"

# Copy files from the VERIFIED snapshot set; do not move.
# Keep schema.cql/manifest.json if present for reference metadata.
cp -a "$SNAP_DIR"/. "$STAGING"/

# Verify SSTable components sharing the same generation.
find "$STAGING" -maxdepth 1 -type f -print
du -sh "$STAGING"
~~~

In staging, `schema.cql`/`manifest.json` may appear alongside SSTables when copying a full snapshot, yet they are **not SSTable components to stream**. The loader scans valid SSTables; keeping metadata in an independent manifest remains helpful. If staging multiple source nodes into one folder, **prevent colliding generation names**: different nodes can share identical SSTable IDs while holding different contents. Use **separate staging folders per node/source set** or supported generation-renaming plans—never arbitrarily rename individual components of an SSTable.

### 8.3. Collecting Multiple Nodes Does Not Mean Duplicate Loads Are Free or Harmless

With RF=3 across 6 nodes in one DC, each node holds **only a fraction** of token ranges. Snapshotting only node A may **omit partitions held solely by other replicas**. Account for full-ring coverage.

Conversely, the same partition may appear on three source nodes. Streaming multiple replica snapshots generates **stream/write amplification**, raises disk/compaction load, and lengthens restores. Timestamp reconciliation normally converges state, yet **that does not mean** loading redundant copies is free or safe when bad timestamps/tombstones exist.

To reduce risk:

- Build a **matrix of token ranges × source nodes × available snapshots**.
- Never assume one node's snapshot or a single `COUNT(*)` is enough.
- Prefer SSTable sets with full coverage and sources with trustworthy mutation history.
- Never mix a time-T snapshot with time-(T+1) incrementals when targeting exact T without a replay policy.

## 9. File-Based Restore with `nodetool import` (Preferred Over `refresh`)

Apache Cassandra 5.0 lists `nodetool import` as the local SSTable loading method replacing `nodetool refresh`, which bulk-loading docs mark deprecated.

### 9.1. What Does `nodetool import` Do?

`import` accepts **keyspace, table, and a directory** containing SSTables and executes option-governed checks: validation, token ownership, cache invalidation, and repaired metadata handling. It runs on **the invoked node**, without querying the ring to stream every token range to all natural replicas like `sstableloader`.

~~~text
Backup copy for node P
        |
        v
Local staging directory
        |
  nodetool import -- KS TABLE /staging/path
        |
  Node P loads SSTables into table store
        |
  Read CQL/metrics across cluster
        |
  Recover remaining replicas via appropriate
  restore/rebuild/repair workflow
~~~

### 9.2. Syntax and Risky Flags

~~~bash
nodetool help import

# Template applicable only when directory holds SSTables for the exact table/node.
nodetool import -- shop orders /srv/restore-staging/node-p/orders
~~~

| Option | Meaning | Practice |
|---|---|---|
| `-e, --extended-verify` | Extra verification of file contents | Helpful for suspect sources; slower |
| `-l, --keep-level` | Preserve SSTable compaction level | Use only when compaction strategy/level metadata match |
| `-r, --keep-repaired` | Preserve repaired markers | Dangerous when bringing "repaired" state from another cluster |
| `-t, --no-tokens` | Skip token ownership checks | **Avoid** unless backed by a special runbook and placement proof |
| `-v, --no-verify` | Skip SSTable verification | **Avoid** on unverified backups |
| `-q, --quick` | Skip multiple verify/cache/placement checks | **Never use** to bypass unexplained import errors |
| `-c, --no-invalidate-caches` | Keep existing caches | Can cause cached reads to miss newly imported data |

**Read help on your actual binary:** releases add flags or alter names; this lesson does not imply every flag exists in every version.

### 9.3. Why Should Repaired Metadata from Another Source Not Be Kept?

SSTables track repaired/unrepaired/pending-repair state tied to **a cluster's repair history**. Blindly passing `--keep-repaired` when moving SSTables from cluster A to B can trick target repair/compaction into believing data was synchronized on **ring B when it never was**.

Normally let the tool **reset/handle repaired state per version-safe policy**, then run repair as required. Never pass `--keep-repaired` merely to skip repair cost.

### 9.4. File Restore Does Not Auto-Fix Schemas, Indexes, or Derived Tables

After `import`, verify:

- The base table has all primary keys and columns.
- Required indexes/SAI/2i serve queries accurately; when in doubt, run **rebuild index** per runbook.
- Materialized views and app-denormalized tables receive **separate backfill/replay** if needed.
- Data from imported files belongs to the node's token ranges and remaining replicas are synced.

Never equate `nodetool import` returning `0` with "clients can read every record at every CL and DC."

## 10. Legacy `nodetool refresh` and Direct Copies into Table Directories

`nodetool refresh <keyspace> <table>` tells Cassandra to **pick up new SSTables placed in a live table directory** without needing a node restart solely for the refresh:

~~~bash
nodetool help refresh

# Illustrative only after files are accurately placed in a lab
# with an approved runbook and verified table ID/token ownership.
nodetool refresh shop orders
~~~

Unlike `import`, `refresh` does not accept an arbitrary source directory; it inspects the target table's local directory. Manual copying into live directories carries heavy risks:

1. **Wrong table ID:** dropped/recreated tables get a new directory UUID.
2. **Generation filename collision:** overwriting an SSTable actively used by the engine.
3. **Wrong token ownership:** files belonged to an old node/ring, not this target node.
4. **Incomplete components:** copying only `Data.db` while omitting metadata/digests/TOC.
5. **Stale read caches and repaired state:** incompatible state.
6. **Half-finished file copy:** `refresh` picks up incomplete component sets.
7. **Low free disk:** temp files, snapshot hard links, and compaction add heavy overhead.

**Selection guidance:** on modern Cassandra releases, prefer **`nodetool import`** from staging with default verification enabled. Use legacy `refresh` only if a runbook explicitly validates binary version, directory UUID, file naming, token ownership, and safe staged copying. **Never** copy directly from a source node into a busy target's live directory and run `refresh` just to "see if it works."

### 10.1. When Copying Files Is Required, Split into Two Phases

~~~text
PHASE A — OFFLINE Preparation
  External backup -> dedicated staging directory
  Checksums / file set / format / schema / tokens
  Confirm complete staged copy

PHASE B — CONTROLLED Load
  Prefer import from staging (no copy into live dir)
     |
     v
  Verify SSTable counts + CQL reads + replica coverage

Legacy refresh:
  Only under a specially designed and accepted procedure:
  copy valid file set into exact live table directory,
  then refresh exact node/table.
~~~

Manual file restore is a **targeted** technique. When moving a whole-cluster snapshot from an old topology to a new topology, `sstableloader` is usually more appropriate with far lower placement risk.

## 11. Timestamps, TTLs, and Tombstones: Why "Restore Ran" Yet Rows Stay Missing?

### 11.1. Cassandra Reconciles Cells by Timestamp, Not Restore Time

Cassandra uses mutation timestamps (typically **microsecond** resolution) to reconcile versions. `sstableloader` or `nodetool import` loads old SSTable contents into the engine; **it does not treat import time as the newest write timestamp**.

~~~text
T0 — Row written cleanly
  status = PAID, write timestamp = 100

T1 — Accidental DELETE
  tombstone, write timestamp = 200

T2 — Restore SSTable from T0 snapshot
  status = PAID, write timestamp = 100

Target table still holds tombstone T1:
  200 > 100 => PAID from snapshot remains shadowed.
  SELECT may still return (0 rows).
~~~

**There is no loader bug here:** it streamed exact bytes and replicated properly, yet Cassandra reconciliation treats the newer `DELETE` as the winning state. This is why **restoring into an isolated keyspace/table** is the safe way to investigate: in isolation, you can inspect snapshot contents before deciding how to touch the live table.

### 11.2. Why Not "Assign Huge Timestamps" to Force Data Back?

A tempting quick hack is replaying the whole snapshot with enormous timestamps. That can:

- Overwrite valid `UPDATE`s that happened after the snapshot.
- Shadow valid `DELETE`s the business intended to keep.
- Create "future" timestamps that normal future mutations cannot beat.
- Break synchronization across denormalized tables, indexes, and audit logs.

If **selective** recovery is needed, rely on an **authoritative source of truth** for valid events, business keys/versions, and target timestamps. Distinguish logical data repair from moving SSTables; the loader **never** makes business decisions.

### 11.3. TTLs Are Not "Refreshed" by Streaming Old Records

Suppose a cell was inserted with `TTL 3600`, snapshotted while still alive, and restored **after its expiration timestamp**. The SSTable carries the original TTL/expiration metadata, so the value may **no longer be visible** after restore.

~~~text
10:00  INSERT token USING TTL 3600
10:10  snapshot, ~50 minutes of TTL remaining
12:00  sstableloader into another cluster

Logical expectation:
  token already passed expiration time; it does NOT "live 1 extra hour."
~~~

To establish a **fresh session**, the application must issue a new mutation per business policy—never treat restore as a TTL reset. For retention-regulated data, resurrecting expired cells can be a serious compliance violation.

### 11.4. Zombie Data When Tombstones Were Purged

The opposite risk:

~~~text
T0: A/B/C all hold customer-123 (ts=100)
T1: DELETE customer-123 (ts=200), C misses DELETE
T2: A/B hold tombstone; C stays offline beyond gc_grace_seconds
T3: A/B compaction purges tombstone once eligible
T4: C / old backup re-introduces customer-123 ts=100 into cluster

No tombstone ts=200 remains to shadow ts=100 data
=> customer-123 can reappear (zombie).
~~~

Repair/loader **cannot recreate a purged tombstone** if no source retains it. Before restoring old SSTables, check:

- Per-table `gc_grace_seconds`, backup age, and repair history.
- Duration any node/replica was offline.
- `DELETE`s/TTLs occurring after the snapshot.
- Any **legal deletion/retention** mandate forbidding data resurrection.
- How to verify **zero reappearance** for deleted keys.

A very old snapshot is not automatically "safe because it is a backup"; it may hold values that current data policy **forbids returning**.

### 11.5. One Table Holds Multiple Versions and Tombstone Scopes

| Type | What to Remember During Restore |
|---|---|
| Cell UPDATE | Per-cell timestamp; a row may reconcile across multiple SSTables |
| Row DELETE | Tombstone shadows older cells in the row |
| Partition DELETE | Tombstone can shadow many clustering rows |
| Range DELETE | Shadows clustering ranges; inspect range bounds |
| TTL | Expiration may occur prior to restore |
| Collection / UDT | Non-frozen collections carry cell-level metadata; check schema compatibility |
| LWT / CAS | Business ordering is not automatically restored by timestamps alone |

`WRITETIME(col)` in CQL shows the write timestamp of a **live** cell; it is **not a tool to inspect tombstones** or full SSTable history. When a `SELECT` returns no rows, distinguish "not loaded," "loaded but shadowed by tombstone," "TTL expired," "wrong primary key/CL," and "read from an unsynced DC."

## 12. Runbook: Restoring via `sstableloader` on a Target Cluster

### 12.1. Phase A — Classify the Incident and Lock Recovery Scope

Pick **one** concrete objective:

1. Restore a lost table into an **isolated recovery keyspace** for reconciliation.
2. Recover a set of accidentally deleted keys after audit verification.
3. Load full data into a **new cluster with different topology**.
4. Recover a node/replica missing data (check whether replace/rebuild/repair fits better).
5. Restore from snapshot + increments to a declared point, with explicit RPO scope.

Never write a runbook saying only "restore Cassandra" without specifying **table/keyspace/cluster/DC, recovery point, and source of truth**.

### 12.2. Phase B — Mandatory Preflight

| Gate | What to Check? | Passing Criterion |
|---|---|---|
| **B1 — Backup** | All SSTable components + checksums/manifests present? | Complete files; independent copy readable |
| **B2 — Version** | Loader/target binary compatible with SSTable format? | Read-tested in lab on matching version |
| **B3 — Schema** | Partition key, clustering columns, types, UDTs, table ID/indexes? | Target schema compatible; DDL verified |
| **B4 — Topology** | Partitioner, tokens, DC/rack, RF, and node health? | Ring stable; sufficient natural replicas |
| **B5 — Capacity** | Free disk, network/streaming, compaction, CPU? | Headroom exists for new data and compaction |
| **B6 — Security** | TLS, auth, secrets, encryption keys, firewalls? | Required ports reachable |
| **B7 — Data safety** | Possible TTL/tombstone/DELETE/newer-write conflicts? | Isolated restore and audit plan ready |
| **B8 — Observability** | Metrics, logs, pre/post checks, on-call? | Can verify step-by-step or abort |

If B2 or B3 fails, **do not stream into production** "just to see if it errors." Always test on a lab cluster matching target schema, version, and replication first.

### 12.3. Phase C — Prepare Target Cluster and Schema

In `cqlsh` on the authorized target cluster:

~~~sql
DESCRIBE KEYSPACE restore_target;
DESCRIBE TABLE restore_target.orders;
~~~

If the target table does not yet exist, **create it with compatible schema** verified from the backup and matching target topology/RF. Never paste raw `schema.cql` from source without checking version constraints, table IDs, deprecated options, or new RF/DCs.

**Safe default path:** restore into a new `restore_target` keyspace with matching schema instead of overwriting production tables immediately. After reconciliation, apps can read from it or selectively replay into the main table per business workflow.

### 12.4. Phase D — Stream in Rate-Limited Batches

~~~bash
# Only on a host holding stable snapshot copies with network reachability to target.
sstableloader \
  --nodes 10.10.1.11,10.10.1.12 \
  --throttle-mib 16 \
  /srv/restore-staging/restore_target/orders
~~~

This is a **sample command**; substitute hosts/paths, verify auth/TLS, and tune rate limits for your environment. Do not run parallel loaders unless capacity has been measured. Monitor:

- Loader logs: established connections, SSTable sections, bytes streamed, failed/partial transfers.
- `nodetool netstats` on receiver nodes.
- Disk I/O, free disk, pending compactions, GC, and read/write p95/p99 latency.
- Node UP/NORMAL status and CL timeouts.
- Loaded ranges/source sets in the manifest—never declare done because one batch succeeded.

Never delete staging once the loader prints 100% until **data and scope have been thoroughly verified**.

### 12.5. Phase E — Verify All Three Layers

**Layer 1: Transport**

- Loader finishes error-free or produces an explicit retry list.
- Zero lingering stream errors; source files/bytes and target receipts match logs.
- No nodes, ports, TLS checks, or auth silently skipped.

**Layer 2: Replica Placement**

- Target keyspace/table, per-DC RF, and ring stability match expectations.
- Primary keys across representative token ranges read cleanly at desired CL.
- Coverage of all source partitions/ranges recorded, not just one node.
- Repair executed if source/target diverged or hints were insufficient; remember repair does not replace auditing.

**Layer 3: Business Correctness**

- Reconcile primary keys and key columns against event/audit logs.
- Verify **rows that must exist and rows that must be absent**, especially `DELETE`/TTL cases.
- Check out-of-order updates, timestamps, business versions, and denormalized tables.
- Confirm purged/erasure-mandated records did not reappear.

### 12.6. Stop Conditions During Streaming

| Condition | Decision |
|---|---|
| Format / schema mismatch | Halt batch; do not force load or wipe metadata |
| A target DC becomes unreachable | Do not claim full replicas; investigate network/ring |
| Free disk drops below safe threshold | Pause loader / reduce concurrency per runbook |
| Client read/write timeouts spike | Check streaming throttle/compaction; shed load safely |
| Deleted row reappears | Block production cutover; inspect tombstones/audit |
| Loader succeeds yet keys remain missing | Check source range coverage, TTL/tombstones, CL, schema |
| Logical data fixes required | Switch to selective recovery workflow; stop blind streaming |

**Rolling back a bulk restore is not simple:** the loader already wrote SSTables into the target table and compaction may have merged them. Using an **isolated recovery keyspace/table** keeps live traffic untouched until checks pass. If loading into a live table is unavoidable, prepare a **business-source undo plan**—never assume an "sstableloader undo" exists.

## 13. Topology Change Example: Restoring from RF=3/3-Node to RF=3/5-Node

Suppose source has RF3 on three nodes and target has RF3 on five nodes in one DC:

~~~text
                  SOURCE                       TARGET
          Cassandra 4.1 / dc1              Cassandra 4.1 / dc1
          nodes A,B,C / RF=3                nodes P,Q,R,S,T / RF=3
                |                                 ^
          node-local snapshots                    |
             A + B + C                            |
                |                                 |
        backup manifest + schema                  |
                |                                 |
           staging copy                           |
                |                                 |
           sstableloader -------------------------+
                |
    target token map -> partitions distributed
         across new natural replicas
~~~

With three source nodes and RF=3, many partitions have three copies (in that DC), yet **node count is not proof snapshots hold every write**—a replica might have been offline or missed mutations. Each source snapshot can reflect a different instant and freshness. Select backup/repair/source-of-truth sets per runbook.

**Mistake to avoid:** copying node A's snapshot to node P, B's to Q, and C's to R assuming replicas are properly distributed. In a 5-node target, token placement shifted; local `nodetool import` like that can strand data on non-owning nodes/ranges. `sstableloader` is built to follow the target ring instead of 1-to-1 node mapping.

### 13.1. Verify Source ≠ Target Using Real Key Data

Select primary keys spanning evenly distributed tokens:

~~~text
Primary key                Expected source state      Target checks
tenant-a/order-001         PAID, version=7            PAID, version=7
tenant-b/order-002         CANCELLED, version=3       CANCELLED, version=3
tenant-c/order-003         DELETED at T1              no row
tenant-d/order-004         TTL expired by T2          no row
~~~

On the target, run `nodetool getendpoints` for those partition keys (syntax per version) to find natural endpoints. Never treat it as reading raw SSTables per node; verify data via CL, controlled tracing, logs, and repair coverage.

### 13.2. Multi-DC: `LOCAL_QUORUM` Does Not Check the Other DC

Suppose target has:

~~~text
dc1: RF=3, local clients read LOCAL_QUORUM
dc2: RF=2, remote clients read LOCAL_QUORUM
~~~

A successful `LOCAL_QUORUM` read in `dc1` **does not confirm** `dc2` received data. Verify **per DC** post-restore, especially when internode TLS/firewalls could block cross-site streaming. Before routing Java traffic to a DC, check keyspace replication, streaming logs, and the driver's `local-datacenter`.

## 14. Lab A — Snapshot Then `sstableloader` into Another Keyspace Without Deleting Source

**Objective:** Create two matching-schema tables on a **single-node lab cluster**, snapshot the source table, modify source data **after** the snapshot, then stream the snapshot into a separate target keyspace. This proves the target reflects the older recovery point and **does not automatically inherit post-snapshot writes**.

**Requirements:** Cassandra 4.1/5.0 single-node lab with one data directory for simplicity; credentials with CQL DDL, `nodetool snapshot`, and `sstableloader` permissions; never run in production. Data paths assume default Linux packaging and **must be verified on your lab host**.

### Step 1 — Create Compatible Source and Target Schemas

~~~sql
CREATE KEYSPACE IF NOT EXISTS restore_source
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE KEYSPACE IF NOT EXISTS restore_target
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS restore_source.orders (
  tenant_id text,
  order_id uuid,
  status text,
  amount int,
  business_version int,
  PRIMARY KEY ((tenant_id), order_id)
);

CREATE TABLE IF NOT EXISTS restore_target.orders (
  tenant_id text,
  order_id uuid,
  status text,
  amount int,
  business_version int,
  PRIMARY KEY ((tenant_id), order_id)
);
~~~

`SimpleStrategy`/RF=1 is solely for illustrating on **a single-node lab**. Never recommend this for multi-DC production. Both tables must share **identical partition keys, clustering keys, types, and row structure**. A **fresh, empty** target table is safest; if reusing a lab, create fresh lab keyspaces/tables or verify empty state before loading to avoid mixing old data.

### Step 2 — Write Source Data Before Snapshot

~~~sql
CONSISTENCY ONE;

INSERT INTO restore_source.orders
  (tenant_id, order_id, status, amount, business_version)
VALUES (
  'tenant-a', 11111111-1111-1111-1111-111111111111,
  'NEW', 500, 1
);

INSERT INTO restore_source.orders
  (tenant_id, order_id, status, amount, business_version)
VALUES (
  'tenant-b', 22222222-2222-2222-2222-222222222222,
  'PAID', 900, 2
);

SELECT order_id, status, amount, business_version
FROM restore_source.orders
WHERE tenant_id = 'tenant-a';

SELECT order_id, status, amount, business_version
FROM restore_source.orders
WHERE tenant_id = 'tenant-b';
~~~

Record expected state `T0` created by the lab: order `1111…` has NEW/version 1, order `2222…` has PAID/version 2.

### Step 3 — Snapshot One Table with Default Flush

~~~bash
# Check version-specific help.
nodetool help snapshot

# Snapshot one table without --skip-flush.
nodetool snapshot --tag lab_restore_01 --table orders restore_source

# Inspect snapshots on node.
nodetool listsnapshots
~~~

`--skip-flush` if passed **skips unflushed memtables**, so avoid it in a lab intending to capture the two `INSERT`s just executed. Snapshots are node-local; a single-node RF1 lab keeps the set simpler than multi-node production.

### Step 4 — Intentionally Create Divergence **After Snapshot**

~~~sql
UPDATE restore_source.orders
SET status = 'PAID', business_version = 2
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

INSERT INTO restore_source.orders
  (tenant_id, order_id, status, amount, business_version)
VALUES (
  'tenant-c', 33333333-3333-3333-3333-333333333333,
  'NEW', 1200, 1
);

SELECT order_id, status, business_version
FROM restore_source.orders
WHERE tenant_id = 'tenant-a';

SELECT order_id, status, business_version
FROM restore_source.orders
WHERE tenant_id = 'tenant-c';
~~~

After this step, source table `restore_source.orders` has PAID/version 2 for order `1111…` plus `tenant-c`. Snapshot `lab_restore_01` **does not mutate** as you write more into source memtables/SSTables: hard links to T0 SSTables preserve the older contents. This assumption must be proven by restoring, not by querying live source.

### Step 5 — Locate Snapshot and Copy into Staging with Exact Parent Path

~~~bash
# Read directory list; never edit live data.
find /var/lib/cassandra/data/restore_source \
  -type d -path '*/snapshots/lab_restore_01' -print
~~~

An actual path looks like:

~~~text
/var/lib/cassandra/data/restore_source/
  orders-<source_table_uuid>/
    snapshots/lab_restore_01/
      <sstable_prefix>-Data.db
      <sstable_prefix>-Statistics.db
      ... other components ...
      schema.cql
      manifest.json
~~~

**Substitute the REAL path** from `find` (do not copy literal `<source_table_uuid>`):

~~~bash
# These paths are lab templates; substitute real <source_table_uuid>.
SNAP_DIR="/var/lib/cassandra/data/restore_source/orders-<source_table_uuid>/snapshots/lab_restore_01"
STAGING="/srv/restore-staging/restore_target/orders"

mkdir -p "$STAGING"
chmod 700 "$STAGING"

# Staging should be empty before a restore test; if not empty,
# stop and inspect—NEVER blindly run rm -rf.
cp -a "$SNAP_DIR"/. "$STAGING"/

find "$STAGING" -maxdepth 1 -type f -print
du -sh "$STAGING"
~~~

If Cassandra uses **multiple data directories**, a table's snapshots can appear in multiple paths. This simple lab is valid only once you confirm all SSTables for the test dataset were collected; never take the first `find` match and claim full production coverage.

**Why is the parent path `restore_target/orders`?** `sstableloader` by default infers target keyspace/table from parent directories. The original snapshot lives under `restore_source/orders-UUID/snapshots/tag`, so feeding that raw snapshot path into the loader cannot automatically target `restore_target.orders`.

### Step 6 — Run `sstableloader` on the Copy

~~~bash
# On a lab host with sstableloader compatible with target.
# 127.0.0.1 works only when loader runs on the same Cassandra lab host.
sstableloader \
  --nodes 127.0.0.1 \
  --throttle-mib 8 \
  /srv/restore-staging/restore_target/orders
~~~

Expected log events include:

~~~text
Established connection to initial hosts
Opening sstables and calculating sections to stream
Streaming relevant parts of SSTables ...
Summary statistics: bytes transferred, duration, transfer rate
~~~

This is **illustrative output**, not a prediction of actual bytes or duration. If "initial hosts" fails, check native port/address; if streaming fails, check storage port/TLS; if schema/format fails, **stop and fix the root cause**—never hex-edit SSTable bytes.

### Step 7 — Compare Current Source vs. Target Snapshot

~~~sql
CONSISTENCY ONE;

SELECT order_id, status, amount, business_version
FROM restore_target.orders
WHERE tenant_id = 'tenant-a';

SELECT order_id, status, amount, business_version
FROM restore_target.orders
WHERE tenant_id = 'tenant-b';

SELECT order_id, status, amount, business_version
FROM restore_target.orders
WHERE tenant_id = 'tenant-c';

SELECT order_id, status, amount, business_version
FROM restore_source.orders
WHERE tenant_id = 'tenant-a';
~~~

| Primary Key | Source Table at Snapshot T0 | Current Source Table T1 | Target Table After Loader (Expected) |
|---|---|---|---|
| `tenant-a/1111…` | NEW, version=1 | PAID, version=2 | **NEW, version=1** |
| `tenant-b/2222…` | PAID, version=2 | PAID, version=2 | **PAID, version=2** |
| `tenant-c/3333…` | Absent | NEW, version=1 | **Absent** |

This demonstrates **snapshot at T0**, not live replication. In production, snapshots are not cluster-wide atomic and post-snapshot writes require explicit replay/restore policies.

### Step 8 — Inspect Metrics and Clean Up Staging per Policy

~~~bash
nodetool status
nodetool netstats
nodetool tablestats restore_target.orders
nodetool compactionstats
~~~

After reconciliation, archive logs/manifests/checksums and outcome statuses. Never delete staging/snapshots the instant the first `SELECT` passes; reserve time to check schemas, token ranges, old tombstones, and representative samples before releasing backups.

**Lab takeaway:** `sstableloader` can load snapshot data into a **matching-schema table in another keyspace** without `DROP`/`TRUNCATE` on the source table. This lets you inspect "data at T0" without overwriting T1 mutations.

### Step 9 — `--target-keyspace` Option, Only When Binary Supports It

Starting with Cassandra 4.0, bulk loading docs describe `-k, --target-keyspace`. With this flag, you can keep the source logical staging path and specify the target:

~~~bash
# Alternative example using separate staging; do not re-run into an already loaded
# table without reason and checking duplicate-load impact.
sstableloader \
  --nodes 127.0.0.1 \
  --target-keyspace restore_target \
  /srv/restore-staging/restore_source/orders
~~~

This is an **alternative** to Step 6, not a requirement to run both. Check `sstableloader --help` on your exact binary to verify option availability and path rules; it changes only the target **keyspace**, not table names or schemas.

## 15. Lab B — Planning File-Based Restore on One Node (Non-Destructive)

Lab A used streaming to hit the right natural replicas. Lab B focuses on **making safe decisions** before invoking `nodetool import`. To avoid double-loading or altering live tables while learning, **run import only on a second lab cluster** with an empty, compatible, operator-verified table.

### 15.1. Pre-Import Verification Sheet

~~~text
FILE-IMPORT PRECHECK
Source:
  snapshot tag / backup ID:
  source node ID, token ranges:
  source table ID + CQL DDL:
  Cassandra/SSTable version:
  checksum verified:
  components count:

Destination:
  Cassandra/SSTable reader version:
  keyspace/table ID and exact schema:
  partitioner:
  target node ID, token ranges, local DC:
  enough disk free and no active repair/streaming:
  other replicas' recovery plan:

Method:
  import, not direct copy+refresh
  token verification: ENABLED
  SSTable validation: ENABLED
  keep repaired metadata: NO, unless proven safe
  rollback/escalation: documented
~~~

### 15.2. Import Syntax for Testing in the Second Lab

~~~bash
# Check help first without importing any files.
nodetool help import

# Run only on the fresh lab cluster after verifying files/tokens/schema.
nodetool import -- restore_target orders \
  /srv/restore-staging/node-p/orders
~~~

**Never pass `--no-tokens` or `--no-verify` just to force the lab to pass.** If `import` reports tokens out of range, that is the exact lesson: files from another ring do not belong directly on node P. Choose `sstableloader` or build an appropriately matched source instead of removing guardrails.

### 15.3. Comparing File Restore and Stream Restore

| Question | `sstableloader` | `nodetool import` |
|---|---|---|
| Need to know which target node owns which tokens? | Loader queries ring to decide | Operator must choose matching node/tokens |
| Automatically streams to all replicas? | Yes, per target replication | No; local import only |
| Input directory needs KS/table names? | Yes, except supported target-keyspace | No path inference needed; passed explicitly in command |
| Can load into a cluster with different topology? | Usually the right tool | Placement risks; needs special procedures |
| Requires target table/schema first? | Yes | Yes |
| Can one `SELECT ONE` verify immediately? | Observable, yet does not prove all replicas | Observable, yet does not prove cluster-wide placement |
| Is loading duplicate SSTables free? | No | No |

## 16. Recovering One Node After Disk Loss: When to Use Backup Files?

Suppose a DC has RF=3 and node P loses its disk:

~~~text
Before failure:
    P (data disk failed), Q, R, S   — RF=3

Ranges held by P may still exist on Q/R/S.

Priority path if other replicas hold valid data:
    replace/rebuild node P per topology and streaming.

Using backup files when truly required:
    restore matching SSTables onto prepared node P
    via import, verifying tokens/schema/format, plus repair.
~~~

**Never assume:** an SSTable from node Q **is automatically** node P's restore file. After node replacements/ring shifts, token ownership changes. Choose between rebuild and import based on speed, replica health, downtime, grace period, and backup quality.

### 16.1. Preconditions for Local Node File Import

- The node is managed/initialized cleanly per replace/rebuild procedures—never attach an old data directory to the cluster and pretend to "revive the node."
- The table directory already has matching schema/table ID, partitioner, and format.
- SSTables come from snapshots with verified checksums and valid token ranges.
- No Cassandra/source process is modifying staging files.
- A repair schedule handles mutations missed since the backup, especially once the **hint retention window** has elapsed.
- Evaluate tombstone GC and zombie risk if the old node stayed down for long.
- Return the node to normal service only after **data coverage + SLOs + CL** pass.

### 16.2. Why Not Always Choose "Copy Files Back from Backup"?

If other replicas remain complete and the ring is healthy, **rebuild/replace** reconstructs the exact token ranges the new node owns in current topology. Backup files may:

- Be hours or days older.
- Miss mutations in memtables/commit logs.
- Contain token ranges the new node no longer owns.
- Carry stale tombstones or incompatible repaired metadata.
- Use an old SSTable format unreadable by a newer binary.

Hence **backup files are a recovery tool**, not automatically the best fix for every single-node failure.

## 17. Java Driver 4.x: Reconciling Recovery Results Against Expected Sources

Java applications connect to Cassandra via **CQL**, not by "reading three `Data.db` files directly" from each replica. An application check verifies **data readable at the chosen CL**, so combine it with loader/repair status and checks across other datacenters.

### 17.1. Reusable CQL Probe

Java 17 example with DataStax Java Driver 4.x, intended for an **RF=1 lab**:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.UUID;

public final class RestoreProbe {
    public record OrderState(
            String status,
            Integer amount,
            Integer businessVersion,
            Long statusWriteTimeMicros) {}

    public static OrderState read(
            CqlSession session, String tenantId, UUID orderId) {

        SimpleStatement stmt = SimpleStatement.builder(
                "SELECT status, amount, business_version, " +
                "WRITETIME(status) AS status_ts " +
                "FROM restore_target.orders " +
                "WHERE tenant_id = ? AND order_id = ?")
            .addPositionalValues(tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .build();

        Row row = session.execute(stmt).one();
        if (row == null) {
            return null; // No live row at this read CL.
        }

        return new OrderState(
            row.getString("status"),
            row.isNull("amount") ? null : row.getInt("amount"),
            row.isNull("business_version")
                ? null : row.getInt("business_version"),
            row.isNull("status_ts")
                ? null : row.getLong("status_ts"));
    }

    public static void main(String[] args) {
        // Contact points/local DC/credentials come from lab environment config.
        try (CqlSession session = CqlSession.builder()
                .withLocalDatacenter("datacenter1")
                .build()) {

            OrderState t0 = read(
                session, "tenant-a",
                UUID.fromString("11111111-1111-1111-1111-111111111111"));

            boolean matchesSnapshotT0 = t0 != null
                && "NEW".equals(t0.status())
                && Integer.valueOf(500).equals(t0.amount())
                && Integer.valueOf(1).equals(t0.businessVersion());

            System.out.println("snapshotT0Matches=" + matchesSnapshotT0);

            OrderState shouldBeAbsent = read(
                session, "tenant-c",
                UUID.fromString("33333333-3333-3333-3333-333333333333"));

            System.out.println("tenantCAfterT0Absent="
                + (shouldBeAbsent == null));
        }
    }
}
~~~

**Connection note:** `datacenter1` in the snippet is the **default DC name in many labs**, whereas a real DC might be `dc1` or another name. The driver needs exact contact points and local datacenter; real apps externalize config and reuse a single `CqlSession` instead of creating sessions per request. The demo omits explicit contact points since environments vary; before running, ensure the driver reaches contact points/defaults per your lab setup.

**Why compare against T0 instead of the current source table?** Because the lab intentionally introduced T1 mutations after the snapshot. Treating `SELECT restore_source.orders` at T1 as "expected" would misclassify an accurate T0 snapshot restore as missing data.

### 17.2. Reading at Different Consistency Levels: Seeing Right Does Not Mean Every Replica Is Right

| Check | What Does It Tell You? | What Does It Not Prove? |
|---|---|---|
| `ONE` | A low-CL read suitable for an RF1 lab | All RF3 replicas match |
| `LOCAL_QUORUM` | Sufficient responses in local DC per RF | Another DC received the data |
| `QUORUM` | Quorum met per keyspace/topology requirement | Every physical replica holds the right copy |
| `ALL` | Requires all relevant full replicas if all are up | Does not verify business correctness or audit sources |
| Controlled tracing | Participating nodes and some read/reconciliation steps | Does not cover all partitions/token ranges |
| Restore/stream/repair logs | Transport and sync coverage | Does not replace logic checks for accidentally deleted data |

In RF=3 production with `NetworkTopologyStrategy`, replace the lab's `ONE` with the proper CL (often `LOCAL_QUORUM` for consistency-sensitive workloads) **per application contract**. Never lower CL just to make a restore report look "all PASS."

**Never confuse coordinator with replica:** connecting Java to node P's IP and running `CONSISTENCY ONE` does not guarantee the returned row was read **from P's local SSTables**. The coordinator may pick another natural replica. To verify what files node P holds, use node inspection/reconciliation tools and offline checks—never call a `SELECT` "reading P exclusively."

### 17.3. Checking Timestamps in Proper Scope

`WRITETIME(status)` returns the timestamp of a **live cell**. When a row is shadowed by a tombstone or expired by TTL, CQL does not expose all historical versions/tombstones. For recovery after an accidental `DELETE`:

1. Check audit sources to confirm **which `DELETE` was erroneous**.
2. Check timestamps/versions of mutations preserved in the snapshot.
3. Check whether newer tombstones exist in the live target via approved timeline/log/SSTable inspection.
4. Build a selective recovery plan by business event rather than relying solely on a single `WRITETIME`.

### 17.4. Verifying Multiple Denormalized Tables

Suppose an application has:

~~~text
orders_by_id            PK((tenant_id), order_id)
orders_by_customer_day  PK((customer_id, day), order_id)
orders_by_status_day    PK((status, day), order_id)
~~~

`sstableloader` loading `orders_by_id` does not automatically populate rows in the other two tables. If an incident wiped all three tables, you must restore/backfill/reconcile **each table** or replay business events through an idempotent pipeline. A passing `GET /orders/{id}` test does not prove customer-listing or status-listing pages recovered.

## 18. Observability During and After Restore

### 18.1. Minimum Signals

| Layer | Metrics / Logs | Purpose |
|---|---|---|
| Loader | Connections, SSTable sections, bytes transferred, failed hosts, summary | Know which batches streamed and what failed |
| Ring / gossip | `nodetool status`, token ownership, node lifecycle | Spot nodes leaving/joining mid-restore |
| Streaming | `nodetool netstats`, throughput, connection errors | Track target ingestion |
| Storage | Disk free, Live/TotalSSTableCount, `tablestats`, pending compactions | Observe file counts and post-load I/O cost |
| Requests | `ClientRequest.Read/Write.Latency`, timeouts/unavailables | Check impact on live traffic |
| JVM / OS | CPU, heap/GC, disk await, network bytes/s | Spot bottlenecks / throttling needs |
| Replica data | Repair logs, range coverage, sampled keys | Assess technical sync |
| Business data | Audit event IDs, versions, expected present/absent rows, TTL | Assess business accuracy |
| Java client | p95/p99, connection pool, retries, CL, local DC | Prove the application actually serves cleanly |

Every Cassandra metric should tag **cluster, DC, node, keyspace, table, UTC timestamp**, and restore method label. A rising `LiveSSTableCount` confirms only new files or compaction changes—**it does not prove all rows arrived**.

### 18.2. Matching Before–After Snapshots

~~~bash
# Before and after on receiving nodes, with separate timestamps.
nodetool status
nodetool netstats
nodetool tablestats restore_target.orders
nodetool compactionstats
nodetool tpstats
~~~

Measure in the application:

- Primary query families, QPS, and p95/p99 latency.
- Timeouts/retries by CL and datacenter.
- Row/column counts returned for tested primary keys.
- Explicit accounting of differences between expected T0 snapshot and current T1 source.
- Status of `DELETE`d or TTL-expired rows.

After large bulk loads, compaction can keep running long after the loader finishes. **Never rush to declare resources stable** while disk/SSTable/compaction backlogs are still climbing and p99 exceeds SLOs.

### 18.3. Three-Layer Acceptance Table

| Gate | Evidence | Outcome |
|---|---|---|
| A — **Files / transport** | Complete source files and checksums; zero loader/import errors; all batches finished | PASS/FAIL |
| B — **Placement / replicas** | Matching ring/partitioner/RF/DC; target token ranges and replicas synced | PASS/FAIL |
| C — **Data / business** | Samples + audits match; `DELETE`/TTL do not resurrect; multi-table sync | PASS/FAIL |
| D — **Service readiness** | p95/p99, timeouts, resource headroom, Java app functional | PASS/FAIL |

Mark **`RESTORE_VALIDATED`** only when all goal-relevant gates pass, **stating scope and sampling method explicitly**. If only 30 keys were checked, never call that a "100% data audit." Explicitly record `COVERAGE=sampled` or `COVERAGE=full` per reality.

### 18.4. Actual RPO/RTO Must Include Validation

~~~text
RTO measured until the application serves accurately:

T_restore =
  backup retrieval time
  + integrity/schema/format checks
  + staging/upgrade if needed
  + streaming/import
  + related repair/compaction and warm-up
  + thorough data validation
  + traffic cutover / feature flags
~~~

Note this is a **task breakdown**, not a strict sequential addition when some tasks run in parallel. Committed RTO must be verified via **periodic restore drills**, never estimated solely from "file copy MB/s."

## 19. Troubleshooting Common Errors

### Case 1 — Loader Reports "initial hosts must be specified"

**Cause:** `sstableloader` is missing `--nodes`/`-d`.  
**Action:** Check `sstableloader --help` and pass hostnames/IPs of appropriate initial target hosts; never change source path to a live data directory to fix this.

### Case 2 — Port 9042 Connects Yet Streaming Fails

**Likelihood:** Native CQL path works, yet storage ports, internode TLS, DNS/broadcast addresses, firewalls, or streaming credentials are misconfigured.  
**Action:** Check `-p` vs. `-sp`/`-ssp`, `--conf-path`, logs, and network paths to **every receiver**, not just initial hosts.

### Case 3 — "No SSTables found" or Wrong Target Table

**Likelihood:** Staging points to an outer folder containing `snapshots/tag` at the wrong depth; parent paths resolve to a wrong keyspace/table name; missing component files.  
**Action:** Verify `<staging>/<keyspace>/<table>/*-Data.db` and all components, and check which target keyspace/table the loader inferred. Never rename files manually.

### Case 4 — "Incompatible SSTable version"

**Likelihood:** SSTables were created by a newer or too-old binary/format unsupported by the target loader; or corrupted components.  
**Action:** Preserve original backups, verify exact Cassandra/SSTable versions, test `sstableupgrade` on an **offline copy** per official compatibility matrix and staging checks; never shove files into live dirs with `refresh` to bypass errors.

### Case 5 — `nodetool import` Reports Tokens Outside Node Ownership

**Likelihood:** Files came from another ring/node whose partition tokens are not owned by the target node.  
**Action:** Stop and check partitioner/ring/replica placement. Use `sstableloader` if redistribution is needed; never reflexively pass `--no-tokens`.

### Case 6 — Loader SUCCEEDS Yet `SELECT` Returns 0 Rows

Main possibilities:

1. Snapshot omitted this partition; backed up only one node lacking full token coverage.
2. Query targets wrong primary key or wrong keyspace/table.
3. TTL already expired.
4. Newer tombstones/timestamps in the target table shadow older data.
5. Schema/UDT/column type mismatch.
6. Read CL/DC hits unsynced replicas or incomplete streaming/repair.

**Action:** Check source manifest/expected keys, timestamps, TTL/tombstones, and read-back per DC. Never loop loader retries blindly before finding root cause.

### Case 7 — `DELETE`d Rows Reappear After Restore

**Likelihood:** Old SSTables loaded after newer tombstones had been purged, or restored into a fresh table without reapplying valid post-snapshot deletions.  
**Action:** **Never put the restored table into live traffic**; check `DELETE` audits and retention, replay valid deletions/changes, and fix data from business events. File-correct restore **does not equal** legally/business-correct state.

### Case 8 — Data Exists in dc1 Yet Missing in dc2

**Likelihood:** Only tested `LOCAL_QUORUM` in `dc1`; loader failed to finish streaming to `dc2`, or target RF/DC config is wrong.  
**Action:** Check `DESCRIBE KEYSPACE`, ring, TLS/streaming logs, and verify using a client configured with `local-datacenter` = `dc2` per runbook.

### Case 9 — File Copy Succeeds Yet `nodetool refresh` Loads Nothing

**Likelihood:** Wrong table-ID directory, filename collision, incomplete components, bad tokens/format, or Cassandra did not detect the files.  
**Action:** Stop direct copying, preserve backups, check logs, and switch to `nodetool import`/`sstableloader` as appropriate. Never delete live SSTables to force reloading.

### Case 10 — Data "Restored" Yet Java App Still Errors

**Likelihood:** Schema agreement incomplete, wrong driver local DC/metadata, missing derived tables/indexes, incompatible paging/CL, or reads shadowed by tombstones.  
**Action:** Check driver pools/CL, schema, `RESTORE_VALIDATED` gates, and business checks across query families rather than judging from one `cqlsh` `SELECT *`.

### Case 11 — Merging SSTables from Multiple Sources Loses Files

**Likelihood:** Two source nodes had **colliding SSTable generation names**, and copying into one staging folder overwrote earlier files.  
**Action:** Use **separate staging directories per node/source set** with checksums and manifests; check file counts and token coverage before running the loader. Never mix components from two different generations.

### Case 12 — Disk Full During Restore or Post-Restore Compaction

**Likelihood:** Newly streamed/imported SSTables plus pinned snapshot hard links plus temporary compaction outputs create high backlog.  
**Action:** Pause further batches, assess disk headroom, throttle/repair/compact per runbook, and expand storage if needed. Never manually delete SSTables or tombstones.

## 20. Security and Operational Safety in Recovery

### 20.1. SSTable Backups Are Real Sensitive Data

SSTable snapshots hold real table values—potentially PII, transactions, accounts, app tokens, or retention-regulated records. Being `*.db` binaries instead of CSV does not make them safe to share.

Minimum practices:

- Enforce **encryption at rest and in transit**, least privilege, and read controls on keys/truststores/keystores.
- Store backups **in a separate failure domain** from data nodes; verify checksums and run restore drills.
- Never pass passwords via `sstableloader -pw <secret>` in centralized scripts/logs when safer credential configs exist; process arguments leak secrets.
- Never leak paths with user info, CQL values, or PII samples into unauthorized monitoring systems.
- Restrict permissions on staging; never treat `chmod 777` from doc examples as a production default.
- Enforce staging retention and cleanup **after acceptance** with audit trails; never clear original snapshots before confirming independent copies exist.
- If SSTables use KMS/volume encryption, confirm **keys remain accessible at restore time**.

### 20.2. Avoiding Data Exposure When Restoring to Test Clusters

When standing up a staging cluster to validate production backups:

1. Use a test environment with **strict network and account controls**.
2. Apply masking/anonymization where possible while keeping data-model compatibility.
3. Isolate contact points and credentials between staging and production so loaders never hit production by mistake.
4. Prevent production Java services from discovering test clusters via seed/contact point lists.
5. Verify target keyspace/table **before** running the loader, as streaming into live tables has no automatic undo.
6. Periodically drill **revoking/withdrawing** backup access after exercises conclude.

### 20.3. Especially Dangerous Actions When "Restoring Quickly"

| Action | Risk | Safer Alternative |
|---|---|---|
| `TRUNCATE` live table so old backup data shows up | Wipes all newer valid data table-wide; breaks RPO | Restore into isolated table, reconcile, then replay selectively |
| `DROP TABLE` and recreate without saving schema/table ID | Loses live data/metadata and causes directory conflicts | Preserve live table, lock DDL/IDs, plan migration |
| Passing `--no-tokens` in `import` to force files onto a node | Wrong replica placement | Switch to loader or fix source/target plan |
| Passing `--no-verify`/`--quick` on corrupted files | Bypasses guards; spreads bad data | Verify files independently and pull a clean backup |
| Copying raw SSTables into live dir while engine/compaction runs | Name collisions, partial components, races, metadata corruption | Stage + `import` or `sstableloader` |
| Passing `--keep-repaired` on files from another cluster | Repair metadata misrepresents the new ring | Keep safe defaults; repair per runbook |
| Rewriting all snapshot timestamps into the future | Shadows all valid newer mutations | Logical recovery per audit/business versions |
| Disabling SSL or opening 7000/9042 to the Internet to stream | Data leaks and huge attack surface | Network allowlists, TLS, and private staging networks |
| Shrinking `gc_grace_seconds` / purging tombstones to "clean fast" | Zombie data when replicas missed `DELETE`s | Repair/retention runbooks and grace monitoring |

No short command replaces defining **the exact recovery target data and proving it is right**.

## 21. Pre-, During-, and Post-Restore Checklists

### 21.1. Before Restore

- [ ] Target defined (table/key/DC/cluster), RPO/RTO, and business sources of truth.
- [ ] Distinguished node failure, replica failure, and logical data corruption.
- [ ] Chosen `sstableloader` vs. `nodetool import` based on **topology and scope**.
- [ ] Have **independent** backups, checksums, manifests, and complete SSTable components/generations.
- [ ] Audited source token-range coverage across nodes/replicas—never relying on one node's snapshot alone.
- [ ] Have snapshot DDL/UDTs/indexes/schema and verified table IDs.
- [ ] Cassandra/SSTable format, partitioner, and compression/encryption compatible with target.
- [ ] Target keyspace, per-DC RF, and natural replica placement verified.
- [ ] Target ring stable—not mid-way through unfinished bootstrap/decommission/replace.
- [ ] Headroom available on disk/network/CPU/GC/compaction for streaming.
- [ ] Client credentials, TLS/ports, staging paths, and access permissions tested.
- [ ] Matrix prepared of keys that **must exist** and **must be absent** post-restore (`DELETE`/TTL).
- [ ] Evaluated snapshot age against tombstone `gc_grace_seconds` and retention.
- [ ] Staging/restore plan avoids **corrupting live tables** before traffic cutover.
- [ ] Assigned owner/on-call, maintenance window, abort thresholds, and rollback/escalation plan.

### 21.2. During Restore

- [ ] Loader/import points to the exact target cluster, keyspace/table, and node.
- [ ] Session logs, batch IDs, source sets, and UTC timestamps captured.
- [ ] Never re-run completed batches without knowing duplicate-load impact.
- [ ] Streaming progress/errors monitored per node/DC, not just total bytes.
- [ ] Free disk/await, network, compaction, read/write p95/p99, and errors monitored.
- [ ] Never alter RF/schema/topology/CL concurrently without a dependency plan.
- [ ] On local imports, never pass `--no-tokens`/`--no-verify` just to bypass errors.
- [ ] On tombstone/TTL/schema mismatches, stop and investigate before loading more.
- [ ] Keep staging/source backups intact until all verification gates pass.

### 21.3. After Restore

- [ ] Source-file integrity, batch counts, token-range coverage, and loader/import exit statuses verified.
- [ ] Keyspace/table/partitioner/RF/DC match target design.
- [ ] Target nodes/replicas received data and required repair handled.
- [ ] Verified via CQL at proper CL across all in-scope DCs, not just `ONE`.
- [ ] Checked primary keys, columns, `WRITETIME` where appropriate, and business versions.
- [ ] Verified **`DELETE`/TTLs did not resurrect** and newer post-snapshot data was not overwritten.
- [ ] Related denormalized tables/indexes/views reconciled/rebuilt if needed.
- [ ] Java driver connects to the right local DC; p95/p99 and timeouts within SLO.
- [ ] Compaction, disk/GC, and network returned to acceptable post-load levels.
- [ ] Verification scope accurately stated as full vs. sampled.
- [ ] Recorded actual RPO, actual RTO, log/metric links, residual risks, and follow-up schedule.
- [ ] Clean up staging only after sufficient evidence exists and retention policy permits.

## 22. Self-Assessment Questions

**Question 1.** When restoring from a 3-node cluster to a 5-node cluster with the same RF=3, why choose `sstableloader` instead of copying files A→P, B→Q, C→R?  
**Guidance:** Target ring token ownership changed; loader streams to new natural replicas, whereas 1-to-1 direct copying can misplace ranges.

**Question 2.** Why is a standalone `Data.db` file usually not a complete SSTable backup?  
**Guidance:** SSTables comprise multiple format-dependent components/metadata/digests sharing the same generation.

**Question 3.** Is a hard-link snapshot on the same source disk resilient to disk failure?  
**Guidance:** No. Independent copies on separate storage with checksum verification are required.

**Question 4.** Why don't consecutive `nodetool snapshot` calls across nodes produce an atomic cluster-wide snapshot?  
**Guidance:** Each node has its own flush/snapshot instant; writes/replication can occur between them.

**Question 5.** Does `sstableloader --nodes 10.0.0.11` stream **all data onto node 10.0.0.11**?  
**Guidance:** No. That is an initial host to query the ring; loader streams slices to endpoints per target replication.

**Question 6.** Why does `sstableloader` need a directory layout like `/staging/shop/orders`?  
**Guidance:** By default, the loader infers keyspace/table from parent directories.

**Question 7.** What happens if port 9042 is open yet the streaming storage port is blocked?  
**Guidance:** Initial connection succeeds, while streaming to target replicas fails.

**Question 8.** Why isn't `nodetool import` on one node equivalent to a cluster-wide restore?  
**Guidance:** It loads files locally; it does not distribute all ranges to all natural replicas.

**Question 9.** Is `nodetool import --no-tokens` the right fix when told tokens don't belong to the node?  
**Guidance:** Not by default; check partitioner/ring/ownership or use `sstableloader`.

**Question 10.** If a target table was `DROP`ped and recreated with the same name, why can copying SSTables into the old UUID directory be ineffective?  
**Guidance:** The new table instance has a different table ID; live paths must match the current table.

**Question 11.** Source SSTables were built on a newer release than the target reader. Can `nodetool refresh` bypass compatibility errors?  
**Guidance:** No; use a supported reader/upgrade path tested on an offline copy.

**Question 12.** Backup holds `status=PAID, ts=100`; target has tombstone `ts=200`. Once loader succeeds, will `SELECT` immediately return `PAID`?  
**Guidance:** No; the newer tombstone shadows the older value.

**Question 13.** Why doesn't a row with a 1-hour TTL snapshotted at 10:10 live for another hour when restored at 12:00?  
**Guidance:** Expiration metadata relies on original write time and does not reset on restore.

**Question 14.** If tombstones purged and an old backup reintroduces `DELETE`d data, what is this risk?  
**Guidance:** Zombie data; requires `DELETE` audits and non-resurrection policies.

**Question 15.** Does `WRITETIME(status)` reveal all historical `DELETE`/TTL tombstones?  
**Guidance:** No; only the timestamp of a live cell in the read result.

**Question 16.** A source node snapshot missed some token ranges, yet `COUNT(*)` on target matches the expected number. Is that enough to declare recovery successful?  
**Guidance:** No; matching counts can still hide different keys/values; verify coverage and audits.

**Question 17.** Why doesn't `LOCAL_QUORUM` succeeding in `dc1` prove `dc2` restored?  
**Guidance:** Local quorum inspects replicas only in the local DC.

**Question 18.** Does `sstableloader` loading `orders_by_id` automatically populate `orders_by_customer_day`?  
**Guidance:** No; both tables have distinct mutations and replicas and require separate restore/backfill/replay.

**Question 19.** Why restore into a new keyspace first when recovering from an accidental `DELETE` on a live table?  
**Guidance:** Avoids mixing old backup timestamps with live tombstones/new writes and lets you verify the source of truth.

**Question 20.** When one node loses its disk while replicas still hold healthy data, must you always run a local file import?  
**Guidance:** No; replace/rebuild from healthy replicas is usually evaluated first per topology.

**Question 21.** Loader returns success and one `SELECT ONE` returns data. Can restore be marked complete?  
**Guidance:** Not yet; verify token/replica/DC coverage, correctness, and SLAs.

**Question 22.** If `sstableloader` streamed into a live table and bad data is later discovered, is there an automatic undo command?  
**Guidance:** No. You need a pre-designed logical recovery/rollback plan—ideally using an isolated table.

## 23. Summary

~~~text
                BACKUP / SNAPSHOT / INCREMENTS
                             |
             Verify manifest + checksums + schema
                             |
          Compare VERSION + SSTable format + ID
                             |
          Compare PARTITIONER + RING + RF/DC
                             |
          Choose method by scope and topology
                   /                   \
             sstableloader          nodetool import
                   |                   |
             STREAM to              LOCAL files
             target replicas        on right node
                   \                   /
                    \                 /
                     TRANSPORT / FILE PASS
                             |
                     REPLICA COVERAGE
                             |
                TTL / tombstone / timestamp
                             |
                  BUSINESS AUDIT / SLO
                             |
                   RESTORE_VALIDATED
                             |
                 Only then cut over live traffic
~~~

**Most important takeaway:** `sstableloader` delivers SSTables to **natural replicas of the target topology**; `nodetool import`/legacy `refresh` handle **local files on individual nodes**. Neither tool knows whether data is **business-correct**, resurrects purged tombstones safely, or turns one node's snapshot into a cluster-wide backup. Trustworthy recovery must be engineered as a **workflow with clear recovery checkpoints, schema/format compatibility, token/RF/DC coverage, TTL/timestamp/tombstone checks, and Java application acceptance**.

## References

- [Apache Cassandra — Backups](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/backups.html) — snapshots, incremental backups, hard links, `schema.cql`, and restore concepts.
- [Apache Cassandra — Bulk Loading](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/bulk_loading.html) — `sstableloader`, `nodetool import`, target keyspace, source directory, and streaming.
- [Apache Cassandra — sstableloader](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstableloader.html) — `--nodes`, `--throttle-mib`, TLS/auth, ports, and stable SSTable source requirements.
- [Apache Cassandra — nodetool import](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/import.html) — importing SSTables from an arbitrary directory, token/verify checks, and repaired metadata.
- [Apache Cassandra — nodetool refresh](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/refresh.html) — legacy loading of newly placed SSTables without restart.
- [Apache Cassandra — nodetool snapshot](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/snapshot.html) — creating snapshots, `--skip-flush`, and node-local scope.
- [Apache Cassandra — sstableupgrade](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstableupgrade.html) — converting SSTable/snapshot formats across Cassandra versions, offline notes, and hard links.
- [Apache Cassandra — nodetool upgradesstables](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/upgradesstables.html) — upgrading managed SSTables on a node per runbook.
- [Apache Cassandra — Storage Engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtable, SSTables, compaction, and write path.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — ring/tokens, replication, consistency, coordinator, and hinted handoff.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy, tombstones, and replica synchronization.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — grace period, tombstone GC, and zombie data.
- [DataStax Java Driver 4.17 — CqlSession API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/CqlSession.html) — CQL queries from Java and session/metadata.
- [DataStax Java Driver 4.17 — Consistency levels](https://docs.datastax.com/en/developer/java/4.17/manual/core/consistency/) — configuring statement CL and verification scope.
