# SSTable Formats and Compatibility Across Apache Cassandra Versions

> **Chapter:** SSTables and compaction  
> **Focus:** How to read SSTable file structures, identify BIG/BTI format codes, and understand compatibility during upgrades/restores of an Apache Cassandra cluster. Examples prioritize Cassandra 3.11, 4.0/4.1, and 5.0.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why Cassandra stores a table as **multiple immutable SSTables**, each consisting of **multiple component files**.
2. Read filenames like `oa-12-big-Data.db` or `da-21-bti-Data.db`, distinguishing **SSTable version code**, **file generation**, **format**, and **component**.
3. State the roles of `Data.db`, `Index.db`/`Summary.db`, `Partitions.db`/`Rows.db`, `Filter.db`, `Statistics.db`, and other components.
4. Distinguish BIG and BTI starting from Cassandra 5.0; understand the impact of `sstable.selected_format`, compaction, and `storage_compatibility_mode`.
5. Identify the boundary between **reading older data on a newer version** versus **rolling back from a newer version to an older version**, and why snapshots do not automatically convert formats.
6. Practice observing/evaluating SSTable upgrades with supported commands while avoiding disruption to live user-serving data.

**Scope:** This covers **Apache Cassandra on-disk formats**, not CQL formats, the Java driver, or native protocol wire formats. This lesson does not assume third-party Cassandra distributions share identical compatibility policies.

## 2. Where Do SSTables Fit in the Storage Engine?

Cassandra uses an architecture close to a **Log-Structured Merge Tree (LSM-tree)**. Replicas write mutations to the **commit log** and **memtable**; upon flush, the memtable is written to an SSTable on disk. SSTables are **immutable**: a subsequent UPDATE or DELETE does not directly edit the contents of old files.

~~~text
             CQL write from application
                       |
                  Coordinator
                       |
                  Replica node
                    /      \
               Commit log   Memtable (per table)
                                  |
                              [flush]
                                  |
                            SSTable #101
                                  |
           UPDATE/DELETE -------> New memtable
                                  |
                              [flush]
                                  |
                            SSTable #102
                             \     /
                           [compaction]
                                |
                           SSTable #103
                       (new immutable output)
~~~

An SSTable is **not a single `.db` file**. An SSTable is identified by a common descriptor; component files sharing that descriptor store data, indexes, Bloom filters, statistics, and checksum information. Each table has multiple SSTables, because a partition can have data versions scattered across multiple generations.

### 2.1. How Cassandra Orders Data

- Partitions in an SSTable are ordered by **token order** of the partition key (with Murmur3Partitioner); keys with the same token are handled by the appropriate comparator.
- Rows within a partition are ordered by **clustering key** according to the table's CQL rules.
- Timestamps, TTLs, and tombstones are stored so that **the newest values can be merged** when reading across multiple SSTables and memtables.
- SSTables can be **block-compressed**; reading a single key does not require decompressing the entire `Data.db` file.

Changing the SSTable format does not change the **partition key**, **token ring**, **replication factor**, or how partitions are distributed to replicas. It changes how data is stored and looked up **locally on each node**.

## 3. What Components Make Up an SSTable?

Example **BIG** file set on a Cassandra 5.0 node, with illustrative filenames:

~~~text
<data_dir>/sstable_lab/events-<table_uuid>/
  oa-12-big-Data.db
  oa-12-big-Index.db
  oa-12-big-Summary.db
  oa-12-big-Filter.db
  oa-12-big-Statistics.db
  oa-12-big-CompressionInfo.db
  oa-12-big-Digest.crc32
  oa-12-big-TOC.txt
~~~

These are **illustrative filenames**, not a guarantee that every node/table always has all listed components. For instance, `CompressionInfo.db` only exists when appropriate compression is enabled; component names and counts vary across **BIG**, **BTI**, versions, and indexing features.

| Component | Function | Notes |
|---|---|---|
| `Data.db` | Partition, row, cell, and tombstone data | Main data file, **immutable** |
| `Index.db` | **BIG** primary index: partition key → data position; includes row index info when needed | Distinct from secondary indexes/SAI |
| `Summary.db` | Sparse sample of BIG `Index.db`, helping narrow down the index region to read | Does not contain every row |
| `Filter.db` | Bloom filter for partition keys | Has false positives; no false negatives if structure is valid |
| `CompressionInfo.db` | Offsets and sizes of compressed blocks in `Data.db` | Present only when matching compression settings |
| `Statistics.db` | Metadata such as tokens, min/max timestamps, deletion time, compaction level, repaired state, compression, TTL | Very useful when analyzing upgrades/incidents |
| `Digest.crc32` | CRC digest to verify `Data.db` data | Does not replace backups/replica repair |
| `TOC.txt` | Lists components belonging to the SSTable | Descriptor file, not CQL data |
| `Partitions.db` | Trie-based partition index of **BTI** | Replaces the partition-lookup role of `Index.db` in BIG |
| `Rows.db` | Index for rows/blocks in large partitions of **BTI** | Not every SSTable has the same row index data |
| `SAI*.db` | Storage-Attached Indexing structures if the table has SAI | SAI is a **secondary index**, distinct from the BTI primary index |

### 3.1. Reading by Partition Key in BIG

Simplified read flow:

~~~text
SELECT ... WHERE tenant_id = ?
             |
        compute token/key
             |
    [Bloom Filter: Filter.db]
       |            |
  definitely no   maybe yes
       |            |
      skip       Summary.db -> Index.db
                              |
                         Data.db (partition position)
                              |
                       read rows and reconcile
~~~

The Bloom filter only quickly eliminates SSTables that **definitely do not contain the partition**. If the Bloom filter reports “maybe present”, Cassandra must verify via the index and actual data. `Index.db` is the **primary partition index**, not SAI and not synonymous with CQL `CREATE INDEX`.

### 3.2. Reading by Partition in BTI

BTI (*Big Trie-Indexed*, available from Cassandra 5.0) uses trie-based indexes instead of the traditional BIG-style primary index lookup:

~~~text
SELECT ... WHERE tenant_id = ?
             |
          token/key
             |
        Partitions.db  (trie on partition key)
             |
         Data.db
             |
      Rows.db when needed to look up rows/blocks in a wide partition
             |
          return data
~~~

BTI replaces the **index** portion of an SSTable with structures such as `Partitions.db` and `Rows.db`, reducing lookup costs for certain workloads, especially with large partitions or queries with clustering predicates. `Data.db` still stores row data. This is not an SAI index, even though both BTI and SAI may use trie concepts.

> **Important:** Cassandra architecture documentation often lists components of both BIG and BTI together on one page. That does not mean every SSTable simultaneously has `Index.db`, `Partitions.db`, and `Rows.db`. Check the `big`/`bti` descriptor and the actual file set.

## 4. How to Decode SSTable Filenames

With modern naming:

~~~text
oa-12-big-Data.db
│  │   │   └── component: data content
│  │   └────── format implementation: BIG
│  └────────── generation/id: identifies an SSTable on the node
└───────────── version code: on-disk version of BIG

da-21-bti-Partitions.db
│  │   │   └── component: BTI partition trie
│  │   └────── format implementation: BTI
│  └────────── generation/id: another SSTable
└───────────── version code: on-disk version of BTI
~~~

- **Version code** (`mc`, `nb`, `oa`, `da`...) represents the *file format* version, **not the server release number** like 5.0.9 and **not the CQL protocol version**.
- **Generation/ID** distinguishes one SSTable from another within the same table/node; it is not RF, token, or row count.
- **Format identifier** (`big`, `bti`) selects the format implementation suite, separate from the **version code**. For example, `oa` belongs to BIG while `da` belongs to BTI.
- **Component** indicates what the specific file does. Do not rely on `Data.db` alone as sufficient SSTable data; all associated components must be kept together.

Very old Cassandra versions used different naming schemes; do not parse filenames with hand-rolled regexes and force them across all generations. In real environments, use Cassandra tools matching the exact version to read descriptors.

### 4.1. Reference Version Code Table

| Cassandra line | Format | Notable SSTable codes | Points to remember |
|---|---|---|---|
| 2.1–2.2 | Legacy BIG | `ka`, `la`, `lb` | Historical data; do not assume unconditional readability on every newer version |
| 3.0/3.11 | BIG | `ma`, `mb`, `mc`, `md`, `me` | Each code ties to metadata/on-disk changes per release; e.g. `mc` in 3.0.8/3.9, `md` in 3.0.18/3.11.4 |
| 4.0/4.1 | BIG | `na` (4.0 RC), `nb` (4.0 GA and subsequent releases) | Changes to metadata format, Bloom filter, repair tracking, and host id |
| 5.0 | BIG | `oa` | Includes new metadata/token coverage and deletion-time changes |
| 5.0 | BTI | `da` | Initial BTI version; 5.0 can still support BIG concurrently |

This table describes **on-disk code milestones per Apache documentation**, not a mapping saying “running server 5.0 automatically prefixes every file with `oa`”. A cluster may retain older SSTables after an upgrade, run in compatibility mode, or have `bti` selected. Thus **a single table directory can simultaneously contain multiple version codes and multiple SSTables** during transitions.

Each server version can only read a specific set of formats; beyond the version code, **storage compatibility mode**, compression settings, index format, partitioner, and other deployment conditions must also be considered.

## 5. BIG vs. BTI in Cassandra 5.0: What Is Different?

From Cassandra 5.0, Apache Cassandra supports both:

| Aspect | BIG (legacy format) | BTI (trie-indexed) |
|---|---|---|
| Introduced | Modern BIG widely used since Cassandra 3.x | Cassandra 5.0 |
| Primary index | `Index.db` and `Summary.db` | `Partitions.db` and `Rows.db` |
| Partition lookup | Bloom filter, index summary, and partition index | Trie index and corresponding structures |
| Row access in wide partitions | Collation/row index in BIG | `Rows.db` structure assisting row/block lookup |
| Version code in 5.0 | `oa` (when using new format/version) | `da` |
| Cassandra 4.x compatibility | Based on the BIG **version code** supported by 4.x nodes | 4.x has no built-in BTI reader |
| Newly created in 5.0 | `selected_format: big` | `selected_format: bti` |

**Default:** Cassandra 5.0's compatibility `cassandra.yaml` keeps `big` as the default when the `sstable` section is commented out; `cassandra_latest.yaml` targets newer features and may select `bti`. Do not infer “BTI is enabled” from “using Cassandra 5.0”. Inspect the actual configuration on each node.

Example of selecting the format on a node/lab where configuration changes are permitted:

~~~yaml
# cassandra.yaml, Cassandra 5.0+.
sstable:
  selected_format: bti
~~~

When enabling another format, **old SSTables are not automatically rewritten just by editing YAML**. SSTables created from flushes, compactions, or appropriate rewrite operations can use the target format; old files remain until replaced through their lifecycle. Compatibility and corresponding restart procedures must be checked.

### 5.1. Performance Does Not Depend Only on Format Name

BTI helps improve certain index lookup workloads, yet effectiveness depends on:

1. Partition size, row count, clustering key length.
2. Ratio of single-partition/row reads versus multi-partition scans.
3. Bloom filter false positives, caches, chunk compression.
4. Number of SSTables to read after many flushes and compaction state.
5. Disk I/O, memory, CPU, request concurrency, and multi-replica topology.

The `column_index_size` parameter applies to both BIG/BTI in Cassandra 5.0, with different defaults per format; reducing block index size can speed up intra-partition reads but also increases index size. Do not copy BIG settings to BTI without benchmarking.

### 5.2. BTI and SAI Are Different

**BTI** is a primary SSTable index type for locating partitions and rows/blocks in data already residing on a node. **SAI (Storage-Attached Indexing)** is a secondary index on columns declared via CQL `CREATE INDEX ... USING 'sai'` to support value filtering. A table can use **BTI SSTables** and **SAI** at the same time; SAI files add separate components.

~~~text
SSTable Format: bti
  -> primary lookup: Partitions.db / Rows.db

SAI on status column:
  -> secondary lookup by status value
  -> identify row ID/partition, read base data
~~~

Do not change `selected_format` to “enable SAI”, and do not use `CREATE INDEX` to convert `big` to `bti`.

## 6. What Does “Cross-Version Compatibility” Mean?

Do not lump every kind of compatibility into one sentence like “Cassandra X can read Cassandra Y's data”. There are at least **five separate boundaries**:

| Compatibility type | Right question | Do not equate with |
|---|---|---|
| **On-disk SSTable** | Does the server binary have a reader for this file format/version? | Valid CQL schema |
| **Storage compatibility mode** | Which file/commit log/hints versions is the node currently allowed to write? | `sstable.selected_format` alone |
| **Inter-node streaming** | Can the pair of nodes/versions negotiate and transfer data successfully? | Copying files directly via OS |
| **Snapshot/restore** | Can snapshot files start/import on the target binary with the right schema? | Snapshot creation succeeding |
| **Native protocol/Java driver** | Are the application's CQL sends/receives via the driver compatible? | On-disk SSTable readers |

### 6.1. Upgrade and Downgrade Directions Are Asymmetric

Along an **Apache-supported** upgrade path, the newer binary can usually **read old SSTable files** from source versions within the supported range. This allows rolling upgrades without forcing an immediate full rewrite of all data.

The reverse direction is **not guaranteed**:

- Cassandra 4.1 cannot be assumed to be a valid reader for `oa`/`da` generated by Cassandra 5.0.
- An older node does not understand BTI trie index structures, even if `Data.db` carries contents similar to BIG.
- Once new formats/metadata have been written, swapping back to the old binary on the same data directory may **fail to start** or fail to read data properly.
- A snapshot taken from old SSTables provides material to roll back, but that snapshot must match the **point in time and data state** required by RPO; rollback also involves schema, commit logs, hints, feature flags, and Cassandra versions.

There is no rule that “every newer version reads every file from all earlier versions” regardless of upgrade span. You must read the **official upgrade path**, source/target version limits, NOTES/NEWS, and test thoroughly.

### 6.2. Why Can Compaction Break Rollback Capability?

~~~text
Before upgrade:
  4.1 node -> BIG SSTable version nb
  Pre-upgrade snapshot -> preserves nb file set

During upgrade:
  5.0 node still 4.x-compatible -> can still read nb

After enabling new format/storage features:
  Flush or compaction -> new SSTable version (e.g., oa / da)

Attempting to run 4.1 again on the new data directory:
  4.x reader does not recognize new version -> not a valid rollback
~~~

**Compaction rewrites data**, so when you enable features that produce new formats is just as critical as when you run `nodetool upgradesstables`. Besides compaction, flushes or file streaming from already-upgraded nodes must also be evaluated against version policies.

## 7. Storage Compatibility Mode in Cassandra 5.0

Cassandra 5.0 introduces `storage_compatibility_mode` to roll out new on-disk and messaging features gradually when upgrading from Cassandra 4.x. In 5.0's compatibility configuration, the default mode is `CASSANDRA_4`.

| Mode | Operational meaning | Appropriate timing |
|---|---|---|
| `CASSANDRA_4` | Keeps compatibility with the 4.x line for mode-managed components: file formats, commit log/hints, and related features; does not yet enable breaking new behaviors | Initial rolling binary upgrade phase |
| `UPGRADING` | Intermediate mode: cluster tracks each node's state and activates new behaviors only after cluster-wide version conditions are met | Once all binaries are stable, performing controlled state transition |
| `NONE` | Drops 4.x compatibility constraints to use new 5.0 storage/features | After confirming no legacy rollback is needed |

Process model:

~~~text
All 4.x nodes
      |
      | backup/snapshot, verify supported upgrade version
      v
Rolling binary upgrade to Cassandra 5.0
      |
      | storage_compatibility_mode = CASSANDRA_4
      | test application, nodes, repair, compaction
      v
Rolling restart all nodes with UPGRADING
      |
      | Wait for cluster-wide feature activation condition
      v
Rolling restart all nodes with NONE
      |
      v
Allowed to use new formats/features appropriate for the version
      |
      | consider selecting bti, rewrite SSTables per dedicated runbook
      v
Evaluate stability, disk, latency, and recovery plan
~~~

This is an **illustration of the mode sequence**, not a ready-to-copy runbook for every cluster. Execution order and steps must follow the documentation for the exact minor release and current configuration; specifically, never force format conversion while the cluster still has 4.x nodes or still needs rollback capability.

Example parameter representation:

~~~yaml
# cassandra.yaml, one of Cassandra 5.0's modes
storage_compatibility_mode: CASSANDRA_4

# After completing the rolling upgrade step and verification,
# follow a separate plan to transition the whole cluster via UPGRADING then NONE.
~~~

**Typical detail:** Cassandra 5.0 also changes the maximum deletion time to extend the TTL limit toward year 2106 when the new storage feature is active; in 4.x compatibility mode, the old **2038** limit continues to apply. This illustrates how an on-disk change can affect **data semantics**, not merely read speed.

### 7.1. Relationship with `sstable.selected_format`

These two parameters solve two distinct problems:

1. `storage_compatibility_mode` sets the system's **compatibility boundary** during an upgrade.
2. `sstable.selected_format` chooses the **SSTable implementation for newly created files** (`big` or `bti` in Cassandra 5.0).

Do not select BTI on a node just because you saw the parameter name in `cassandra.yaml`. You must ensure **all involved nodes support the format**, compatibility modes have transitioned per the runbook, and the rollback plan permits that operation.

**Note:** Distributions and `cassandra.yaml`/`cassandra_latest.yaml` files have different defaults; an undeclared setting may apply a compatibility default. Do not infer the actual state from a commented-out configuration line.

## 8. SSTable Format Tools

### 8.1. `nodetool upgradesstables` — Rewriting on a Running Node

In Cassandra 5.0, the command:

~~~bash
# On the target node, specify the exact keyspace/table.
nodetool upgradesstables -- sstable_lab events

# -a: include SSTables already at the current version.
nodetool upgradesstables -a -- sstable_lab events

# Can limit concurrent jobs; check help for your running version.
nodetool upgradesstables -j 1 -- sstable_lab events
~~~

Meaning:

- **Without `-a`:** selects SSTables not yet at the current target version that the node determines must be upgraded.
- **`-a` / `--include-all-sstables`:** also includes SSTables already at *current version*; useful when intentionally rewriting everything under the current configuration, though it **significantly increases I/O cost**.
- **`-j`:** limits concurrent SSTables processed, depending on engine/version; `-j 0` may use all compaction threads and is not a good default for production.
- This command is **node-local**; running it on one node does not mean other replicas have converted their formats.
- It **rewrites files** in the format/version allowed by the current binary and configuration; it does not alter CQL schema, replication factor, or partition keys.

**Important:** `upgradesstables` is not a rescue tool for a node failing to start because it cannot read a file format. It runs via `nodetool` on a running node, requires disk/CPU/I/O headroom, and must be part of a version-appropriate upgrade plan. Do not trigger mass rewrites while the cluster is still in a rolling upgrade and rollback remains an option.

### 8.2. `sstableupgrade` — Offline Tool

Apache Cassandra also provides the standalone `sstableupgrade` tool to rewrite a table's or snapshot's SSTables using the installed binary:

~~~bash
# Only after stopping Cassandra on the lab node and taking a backup.
sstableupgrade sstable_lab events
~~~

**You must stop Cassandra** before running the standalone tool. Apache documentation warns that using offline SSTable tools while the daemon is running can yield unpredictable results. `sstableupgrade` also supports converting **snapshot** SSTables when restoring across major versions, though usage must follow the target binary's docs and backup plan.

Do not confuse:

| Command | When to use? | Scope |
|---|---|---|
| `nodetool upgradesstables` | Node running, want to rewrite selected SSTables | On the invoked node, specified tables |
| `sstableupgrade` | Node **stopped**, offline SSTable/snapshot operation | Local table or snapshot |
| `nodetool compact` | Need on-demand compaction | Merges SSTables per compaction plan; **not** a fully controlled format migration |
| `nodetool repair` | Replica data out of sync | Transfers/fixes data across replicas; **not** aimed at changing all SSTable formats |
| `nodetool flush` | Need to write memtable to SSTable | Only data currently in memtable; does not rewrite old SSTables |

### 8.3. Safe Inspection Tools and Tools Requiring Node Shutdown

~~~bash
# Get server info and cluster health.
nodetool version
nodetool status
nodetool tablestats sstable_lab
nodetool compactionstats

# Check SSTable status via JMX on a running node.
nodetool verify sstable_lab events
~~~

`nodetool verify` can consume heavy I/O when verifying files, so do not treat it as a harmless check under every load. To inspect detailed SSTable metadata with `sstablemetadata` or verify offline with `sstableverify`, you must **stop Cassandra on the node** first:

~~~bash
# Only after stopping Cassandra on the lab node and verifying the real data directory.
sstablemetadata /path/to/oa-12-big-Data.db

# After reviewing tool-specific risks:
sstableverify --help
~~~

`sstablemetadata` reports fields such as partitioner, min/max timestamps, token range, compression ratio, repaired-at, pending-repair, compaction level, TTL, and tombstone stats. `sstableverify` carries warnings about risks of changing repaired state when verification fails; newer versions may require `--force` to run. **Do not** use `--force` as a default production action.

Commands and flags vary across minor versions. Before executing any real command, check `nodetool help <command>` or `<tool> --help` on the **running binary**. In this lesson, offline commands are shown for learning the workflow and **must not be executed** on live service clusters.

## 9. Do Snapshots, Streaming, and Restore Automatically Solve Compatibility?

### 9.1. Snapshots Do Not Convert SSTables

Cassandra snapshots are typically created using hard links to existing SSTables on supported filesystems. As the node continues flushing/compacting, the snapshot retains the **file version from the time of capture**, without automatically upgrading alongside the daemon. Consequences:

- An `nb` snapshot does not automatically become `oa` or `da` after the server moves to Cassandra 5.0.
- Snapshots hold disk space when compaction tries to delete old live files; actual disk usage must account for hard links.
- Restoring a snapshot onto a different binary requires checking **on-disk format**, schema, and supported upgrade paths; in some cases, snapshot SSTables must be upgraded using an offline tool.
- Snapshots do not replace validated backup/restore, because backups must also account for schema, configuration, commit logs, and RPO/RTO targets.

### 9.2. Streaming Can Transfer Data Between Different Node Versions, With Limits

During bootstrap, decommission, rebuild, or repair, Cassandra can stream data between nodes. Streaming **is not equivalent to OS-level copying of SSTable directories**: protocol, reader/writer, version negotiation, SSTable components, and target state all matter.

Some streaming paths can transfer data contents in a way that reconstructs SSTables suitable for the target binary; however, there is no guarantee that **every Cassandra 4.x node** will directly accept **every 5.0 BTI file**. If upgrade-path documentation specifies only mixing a specific set of versions during rolling upgrades, abide by that boundary.

Do not use `scp`, `robocopy`, or copy individual `Data.db` files to move partitions between replicas. Coordinate via Cassandra protocols or SSTable loader tools matching your version and tested restore procedures.

### 9.3. When Is a File “Incompatible”?

| Symptom | Suspected cause | Diagnostic step |
|---|---|---|
| Old node cannot open new SSTable | Version code `oa`/`da` lacks a reader in the old binary | Record filename, binary, storage mode, and downgrade path |
| Both `nb` and `oa` appear under the same 5.0 daemon | Legacy files remain from pre-upgrade; rewrite has not covered all files yet | Check upgrade state and runbook; do not delete files assuming they are “junk” |
| Both `big` and `bti` SSTables exist in one table | `selected_format` was switched; not all files rewritten yet | Assess support level and compaction/upgradesstables progress |
| `Data.db` exists but queries report missing components | Copy/restore missed `TOC.txt` or index/other components, or corruption | Verify file set and logs; do not hand-write components |
| `sstablemetadata` reports unrecognized format | Tool version mismatches file or wrong binary invoked | Check `nodetool version` and tool binary; use supported target tool |
| Latency spikes after format migration | Many files/indexes rewriting, caches warming up, disk busy | Inspect compactionstats, disk I/O, GC, read latency, and caches |
| Snapshot restore unreadable | Snapshot contains file format outside target reader's range | Plan version-appropriate offline conversion/restore and verify data |

## 10. Format Transition Runbook When Upgrading Cassandra 4.1 → 5.0

This is a **decision-making framework** for a distributed cluster using query-driven tables, multiple replicas, consistency levels, and periodic compaction. Exact execution steps must match the upgrade documentation for your exact version, OS, and actual configuration.

### Step 1 — Lock Down Versions and Requirements

Before performing any rewrite operation, answer:

| Question | Required evidence |
|---|---|
| Which version are the nodes running? | `nodetool version` and binary inventory on each node |
| Which format/version are SSTables currently in? | Filename descriptors; sample statistics of representative files |
| Is the cluster currently mixing versions? | Node/rack/DC inventory, rolling upgrade status |
| Is rollback to 4.1 required? | Rollback window policy, verified backups/snapshots |
| Which storage compatibility mode is active? | Per-node `cassandra.yaml` and configuration management workflow |
| Planning to use `big` or `bti`? | Benchmarks and reviewed `sstable.selected_format` |
| Is disk space sufficient for rewrites? | Live SSTables, snapshots, temporary compaction space, free disk |
| Does the workload have SAI, TTLs, heavy tombstones, wide partitions? | Table/index list, compaction strategies, query workloads |

Do not pick `bti` merely because it sounds “newer”; measure a workload with **many partitions, clustering queries, large rows**, or read latency genuinely affected by the primary index.

### Step 2 — Reduce Risk Before Swapping Binaries

1. Confirm all replicas are healthy, critical repairs are complete, and no node is abnormally bootstrapping/decommissioning.
2. Save configurations, schema, and version inventory; take snapshots on nodes per backup policy; **test restore** in an isolated environment.
3. Check current disk utilization and budget for **temporarily holding both old and new SSTables** during compaction/rewrite. Snapshot hard links can keep old files around longer.
4. Define node upgrade order by DC/rack, Java application CLs, error/timeout thresholds, and rollout abort conditions.
5. Explicitly verify the **supported upgrade path**. If the cluster is on 3.11, do not assume you can jump straight to 5.0 bypassing 4.x requirements.

### Step 3 — Upgrade Binaries While Preserving Compatibility

Following the Cassandra 5.0 upgrade path, upgrade nodes one by one from 4.1 and start them with `storage_compatibility_mode: CASSANDRA_4`. During this phase:

- Avoid enabling new features requiring 5.0-only formats.
- Do not run mass `upgradesstables -a` and do not arbitrarily switch to BTI.
- Verify CQL CRUD, partition-key reads, latency, timeouts, replication, Up/Normal node status, repair/compaction, and streaming.
- Log upgraded nodes, observed SSTable versions, and any loader errors. **Multiple SSTable generations** can coexist; that is not automatically an error.

### Step 4 — Decide the Point of No Legacy Rollback

Once **all** nodes are on a compatible 5.0 version, stable, and operators have approved ending the rollback window, transition the whole cluster through `UPGRADING` and then `NONE` via rolling restarts per Cassandra 5.0 docs.

From this point forward, nodes can produce components/formats no longer compatible with Cassandra 4.x. Recovery relies on a **restore runbook with valid backups/formats**, not merely downgrading binary packages.

### Step 5 — If BTI Is Needed, Switch Format and Rewrite in a Controlled Manner

After satisfying the prior steps' conditions, roll out `sstable.selected_format: bti` across the planned scope following configuration change and restart procedures. Pick a test table/group of nodes first, measuring:

- **Before:** SSTable count, p95/p99 read latency, CPU, disk read IOPS, cache hits, write latency, compaction backlog.
- **During:** rewrite throughput, free disk, temporary files, BIG/BTI file counts, latency under load.
- **After:** actual format descriptors, query correctness, latency/throughput, and compaction speed.

To proactively rewrite SSTables already at the current version after switching formats, you may consider:

~~~bash
# Sample on a selected node, after changing config/validating mode.
nodetool upgradesstables -a -j 1 -- sstable_lab events
~~~

This is a **resource-intensive** command. Rewriting one node does not mean all replicas have been rewritten; track progress independently per node. If the goal is only to upgrade **version-outdated** files, `-a` is not always needed.

### Step 6 — Verify Across the Entire Scope

Completion criteria:

1. All involved nodes are running the expected server version, storage mode, and `selected_format`.
2. Each node has finished rewriting its target SSTables, with no failed jobs or unexplained backlog.
3. In relevant table directories, every remaining version/format code can be accounted for; do not assume only one file type remains if snapshots or unrewritten data exist.
4. Reads/writes at the Java application's CL succeed; validate data written **before** and **after** the change across multiple partitions/token ranges.
5. Disk, CPU, p95/p99 latency, compaction, SSTable count, repair, and read error metrics have returned to acceptable levels.
6. New backups/restores have been tested on the **target binary and format**, including a single-replica failure scenario.

A single SELECT returning one correct row does not prove all data has converted formats or is free of corruption.

## 11. Hands-on Lab on a Cassandra 5.0 Lab Cluster

**Requirements:** A **single-node** Cassandra 5.0 lab or test node where config changes, cqlsh, and nodetool are permitted. Do not run `upgradesstables` or restarts on production for this lab. The file-listing steps below illustrate Linux; use the **actual data directory path** of your lab node.

### Exercise 1 — Create Two Generations of BIG SSTables

For simplicity, create an RF=1 keyspace for the single-node lab:

~~~sql
CREATE KEYSPACE IF NOT EXISTS sstable_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS sstable_lab.events (
  tenant_id text,
  event_time timestamp,
  event_id uuid,
  status text,
  payload text,
  PRIMARY KEY ((tenant_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO sstable_lab.events
  (tenant_id, event_time, event_id, status, payload)
VALUES (
  'team_a', '2026-11-20T09:00:00Z',
  11111111-1111-1111-1111-111111111111,
  'NEW', 'created'
);

INSERT INTO sstable_lab.events
  (tenant_id, event_time, event_id, status, payload)
VALUES (
  'team_a', '2026-11-20T10:00:00Z',
  22222222-2222-2222-2222-222222222222,
  'NEW', 'created'
);

SELECT event_time, event_id, status
FROM sstable_lab.events
WHERE tenant_id = 'team_a';
~~~

Trigger a flush on the lab node:

~~~bash
nodetool flush sstable_lab events
~~~

Continue with an UPDATE and another INSERT to create a second generation:

~~~sql
UPDATE sstable_lab.events
SET status = 'DONE'
WHERE tenant_id = 'team_a'
  AND event_time = '2026-11-20T09:00:00Z'
  AND event_id = 11111111-1111-1111-1111-111111111111;

INSERT INTO sstable_lab.events
  (tenant_id, event_time, event_id, status, payload)
VALUES (
  'team_b', '2026-11-20T11:00:00Z',
  33333333-3333-3333-3333-333333333333,
  'NEW', 'created'
);
~~~

~~~bash
nodetool flush sstable_lab events
nodetool tablestats sstable_lab
~~~

**Observation:** The table directory typically has at least two file generations. One generation still holds the old `NEW` value for the `team_a` row, while the later generation holds `DONE`; CQL SELECT must merge versions. Do not conclude there are two **live rows** just because there are two `Data.db` files.

### Exercise 2 — Classify Files by Name

List files only, without modifying/deleting contents:

~~~bash
# Replace the path with the lab node's real data directory.
# List the table directory you are permitted to read.
find /var/lib/cassandra/data/sstable_lab/ -type f -name '*-Data.db'
~~~

Example output (not mandatory output):

~~~text
/var/lib/cassandra/data/sstable_lab/events-<uuid>/oa-7-big-Data.db
/var/lib/cassandra/data/sstable_lab/events-<uuid>/oa-8-big-Data.db
~~~

Record the fields for each file:

| Descriptor | Version code | Generation | Format | Component |
|---|---|---:|---|---|
| `oa-7-big-Data.db` | oa | 7 | big | Data.db |
| `oa-8-big-Data.db` | oa | 8 | big | Data.db |
| `da-9-bti-Partitions.db` | da | 9 | bti | Partitions.db |

**Attention:** If the 5.0 node is in 4.x compatibility mode, files may carry code `nb` instead of `oa`. If configured for BTI, you may encounter `da` instead of `oa`. Record the **actual observed result** and explain it via the configuration.

### Exercise 3 — Inspect Metadata Safely

On a **stopped** node in the lab, read metadata of a `Data.db` file:

~~~bash
# Run after stopping Cassandra on the lab node.
sstablemetadata /var/lib/cassandra/data/sstable_lab/events-<uuid>/oa-7-big-Data.db
~~~

Observe the fields without needing to quote everything:

- `Partitioner` and first/last token: which data range the file covers.
- `Minimum timestamp`, `Maximum timestamp`: mutation times, distinct from filesystem file creation time.
- `Repaired at`, `Pending repair`: repair state important when planning compaction/restore.
- `Compressor` and `Compression ratio`: affects size/block reads.
- `SSTable level`, tombstone stats, TTL: affects compaction and data cleanup.

Because `sstablemetadata` is a standalone tool, **do not run it on a running Cassandra node** per Apache documentation. After restarting the lab, you can observe SSTable count/latency via `nodetool tablestats`.

### Exercise 4 — Try Converting BIG → BTI in a Disposable Environment

Proceed only after:

1. Verifying Cassandra 5.0 and compatibility conditions permit the new format.
2. Taking a snapshot/backup of the lab environment; no 4.x binary rollback needed.
3. Measuring baseline SSTable count, index state, free disk, and CQL queries.

Edit `cassandra.yaml` in the lab:

~~~yaml
sstable:
  selected_format: bti
~~~

Restart following the version-appropriate instructions. Afterward, you may run `nodetool upgradesstables -a` **with limited concurrency** on the lab table to regenerate selected files in the allowed format:

~~~bash
nodetool upgradesstables -a -j 1 -- sstable_lab events
~~~

List the files again and observe the new descriptors. During the rewrite, both BIG and BTI may temporarily appear. CQL results for `team_a` and `team_b` **must remain logically identical**. If metadata/format does not convert as expected, check the binary, mode, configuration, logs, and executed commands; do not manually delete BIG files to force conversion.

~~~sql
SELECT event_time, event_id, status, payload
FROM sstable_lab.events
WHERE tenant_id = 'team_a';

SELECT event_time, event_id, status, payload
FROM sstable_lab.events
WHERE tenant_id = 'team_b';
~~~

**Expected:** `team_a` has two events, where event `1111...` has status `DONE`; `team_b` has one event with status `NEW`. New file locations and names are storage details and must not alter CQL query results.

### Exercise 5 — Analyze a Rollback Scenario

Suppose before upgrade a node ran Cassandra 4.1 with file `nb-20-big-Data.db`. After upgrading to 5.0 and switching to BTI, the node produces `da-21-bti-Data.db`.

Evaluate:

- Can you swap back to the 4.1 binary and start directly on the data directory containing `da`? **Do not treat as compatible.**
- Is having an `nb` snapshot from before the upgrade enough? **Not yet**: you must account for data point-in-time, schema, and proper restore steps.
- Does running `nodetool repair` convert all `da` files back into `nb`? **No**: repair's purpose is synchronizing replicas.
- Does changing `sstable.selected_format: big` on 5.0 automatically convert `da` files back to BIG? **No**: a proper rewrite workflow is required, with no binary-rollback guarantee.

### Exercise 6 — Observe the Effect of Compaction

After two or more flushes, you can run manual compaction **in the lab only**:

~~~bash
nodetool compact sstable_lab events
nodetool compactionstats
~~~

Check the new filenames and query data. If compaction runs and completes, the output uses the format supported by the node's current configuration/capabilities. Old files may remain if snapshots or readers hold references. If the command has nothing to do, do not infer the cluster is broken just because no new file appeared.

## 12. Impact on Java Applications

The Java Driver uses **CQL over the native protocol** and does not need to know about `Data.db`, `Index.db`, or `Partitions.db`. When upgrading the server or changing SSTable formats, the Java application continues using the existing CQL schema; testing is still needed because performance, read errors, timeouts, and cluster version policies may change.

Example of Cassandra Java Driver 4.x reading a partition:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public final class EventReader {
    // session is created and reused across the application lifecycle.
    public static ResultSet findByTenant(CqlSession session, String tenantId) {
        SimpleStatement query = SimpleStatement.builder(
                "SELECT event_time, event_id, status, payload " +
                "FROM sstable_lab.events WHERE tenant_id = ?")
            .addPositionalValue(tenantId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(100)
            .build();
        return session.execute(query);
    }
}
~~~

In an RF=1 lab, LOCAL_QUORUM only needs one replica. In multi-DC production, choose CL, local datacenter, retries, timeouts, and paging policies per SLA; **changing SSTable format does not replace consistency design**. Compare these metrics:

| Testing level | Before upgrade/format change | After upgrade/format change |
|---|---|---|
| Data correctness | Same SELECT by partition key | Identical logical results, including UPDATE/DELETE/TTL |
| Read performance | p50/p95/p99, timeouts, throughput | Measure under same workload and cache warmup |
| Writes and compaction | write p99, flush, compaction backlog | No write stalls or disk full |
| Availability | RF, CL, Up/Normal node count | No lost replicas or schema/streaming errors |
| Restore | Previous backup and recovery sequence | Backups restore cleanly on target binary/format |

If the application uses SAI on Cassandra 5.0, also verify index/SSTable index status after rewriting. **BTI is a primary SSTable index**, whereas SAI is a secondary index: each layer can affect latency differently.

## 13. Misconceptions That Cause Errors During Upgrades

| Wrong assumption | Truth |
|---|---|
| “An SSTable is just one Data.db file.” | An SSTable consists of **multiple components** sharing a descriptor. |
| “Code oa means Cassandra 5.0.9.” | `oa` is the **BIG on-disk code**, not a server patch version. |
| “Cassandra 5.0 automatically converts all old files to oa/da on restart.” | Old files may remain; rewriting requires appropriate flush/compaction/upgrade. |
| “BTI and SAI are the same thing.” | BTI changes the **primary SSTable index**; SAI is a **CQL secondary index**. |
| “Setting selected_format to bti can definitely roll back to 4.1.” | 4.x nodes lack a BTI reader; account for storage mode and restore plans. |
| “-a means increase replica count.” | `upgradesstables -a` means **include all SSTables**, unrelated to RF. |
| “Repair will convert the format of all SSTables.” | Repair synchronizes replica data; format migration is a separate goal. |
| “Copying Data.db to another node is a restore.” | Missing components/schema/ownership and potentially mismatched formats/versions. |
| “A snapshot taken before upgrade will automatically use the new format after upgrade.” | Snapshots preserve files from capture time; check versions when restoring. |
| “If 5.0 SSTables are readable, the Java driver has no compatibility issues either.” | On-disk compatibility and driver native protocol/CQL are **two separate axes**. |
| “Compression, tombstones, and repair metadata do not affect format migration.” | These factors must be preserved/verified during rewrites and data recovery. |

## 14. Self-Check

**Q1.** Given the filename `nb-17-big-Statistics.db`, identify the four descriptor parts and state what the number 17 does **not** represent.  
**Hint:** nb = on-disk version, 17 = generation/ID, big = format, Statistics.db = metadata; 17 is not RF or row count.

**Q2.** Why does a successful UPDATE not immediately reduce the SSTable count?  
**Hint:** Memtables and new SSTables receive mutations; old SSTables are immutable, and only compaction merges eligible generations.

**Q3.** A Cassandra 5.0 table has both `nb-3-big-Data.db` and `oa-4-big-Data.db`. Is the data definitely corrupted?  
**Hint:** No; these may be files from upgrade stages; verify storage mode and supported readers.

**Q4.** Which structures does BTI use to locate partitions and look up rows in wide partitions?  
**Hint:** `Partitions.db` and `Rows.db` replace BIG's `Index.db`/`Summary.db` indexing.

**Q5.** Why is enabling `selected_format: bti` not enough to make all existing files BTI?  
**Hint:** The setting chooses the format of **subsequently created files**, without modifying existing immutable SSTables.

**Q6.** When is `nodetool upgradesstables -a` needed, and why use caution?  
**Hint:** When intentionally rewriting files already at the current version; disk, CPU, I/O costs, and risk of breaking the rollback window.

**Q7.** What is the difference between `nodetool upgradesstables` and `sstableupgrade` regarding Cassandra's running state?  
**Hint:** One runs via nodetool on a running node; the standalone tool requires stopping the daemon.

**Q8.** Can a snapshot containing `da-12-bti-Data.db` be restored directly onto a Cassandra 4.1 node?  
**Hint:** Not by default; old nodes lack a BTI reader and require a valid restore/format runbook.

**Q9.** Why must format conversion evaluate both `storage_compatibility_mode` and `sstable.selected_format`?  
**Hint:** One parameter bounds allowed features/formats for rollback; the other chooses the implementation for new SSTables.

**Q10.** When the Java driver reports read timeouts after format migration, what should you investigate before increasing the timeout?  
**Hint:** Disk I/O, ongoing compaction/rewrites, caches, SSTable count, node health, CL, query plan, and percentile latency.

## 15. Summary Diagram

~~~text
Cassandra storage engine
  Commit log + memtable
         |
       Flush
         v
   Immutable SSTable
         |
         +-- BIG: Data.db + Index.db + Summary.db + ...
         |
         +-- BTI: Data.db + Partitions.db + Rows.db + ...
         |
   Compaction / SSTable rewrite
         |
         v
   New SSTable in allowed format/version

Compatibility:
  Reading old with new binary: only within supported range.
  Reading new with old binary: DO NOT assume.
  Cassandra 5.0: storage compatibility mode defines the boundary,
                 selected_format chooses BIG/BTI for newly created files.
  Snapshot/restore: record and verify actual file versions.
~~~

Rule of thumb to remember: **“SSTables are immutable, descriptors have separate version and format, files are replaced on rewrite, and rollback capability depends on storage mode and verified backups.”** This is the foundation for operating distributed Cassandra with proper read/write consistency, repair/compaction, and stable Java performance.

## References

- [Apache Cassandra 5.0 — Storage Engine: SSTable components, versions, BIG/BTI](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — SSTable structure, `ma`/`nb`/`oa`/`da` codes, and primary indexes.
- [Apache Cassandra 5.0 — cassandra.yaml configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — `storage_compatibility_mode`, `sstable.selected_format`, and compatibility/`cassandra_latest.yaml` differences.
- [Apache Cassandra 5.0 — nodetool upgradesstables](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/upgradesstables.html) — `-a`, `-j`, scope, and rewrite behavior.
- [Apache Cassandra 5.0 — sstableupgrade offline](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/sstableupgrade.html) — rewriting tables/snapshots and requirement to stop the daemon.
- [Apache Cassandra 5.0 — sstablemetadata](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/sstablemetadata.html) — reading token range, timestamps, tombstones, repaired state, compression, and compaction level.
- [Apache Cassandra 5.0 — sstableverify](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/sstableverify.html) — warnings for offline execution and data verification.
- [Apache Cassandra NEWS](https://github.com/apache/cassandra/blob/trunk/NEWS.txt) — pre-upgrade snapshot guidance, upgrade/downgrade format compatibility, and major upgrade stages.
- [Apache Cassandra CASSANDRA-14092 — TTL expiration and storage compatibility](https://github.com/apache/cassandra/blob/trunk/CASSANDRA-14092.txt) — 2038/2106 milestones, `CASSANDRA_4`/`UPGRADING`/`NONE`.
- [Apache Cassandra CEP-25 — Trie-indexed SSTable format](https://cwiki.apache.org/confluence/display/CASSANDRA/CEP-25%3A+Trie-indexed+SSTable+format) — BTI design context and transition plan from BIG.
