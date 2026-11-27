# Immutable SSTables and Metadata/Index/Data Components in Apache Cassandra

**SSTable (Sorted String Table)** is the **immutable** on-disk storage structure of **Apache Cassandra**. Once an SSTable is completely created from *memtable* data or from compaction/streaming, Cassandra does not directly modify the data bytes of that SSTable to perform subsequent `INSERT`, `UPDATE`, or `DELETE` operations. Instead, new versions and **tombstones** are written to the memtable and then into new SSTables; **compaction** merges SSTables when appropriate.

An SSTable is **not just a single `Data.db` file**. It is **a set of components sharing the same descriptor/identifier**: sorted data, indexes for locating partitions/rows, Bloom filters, statistics, compression info, checksums, and a component list. Starting from **Apache Cassandra 5.0**, the **BTI (Big Trie-Indexed)** SSTable format can use `Partitions.db` and `Rows.db` in place of the `Index.db`/`Summary.db` pair of the **BIG** format. Therefore, it is necessary to distinguish *concepts* from *file names across versions/formats*.

This lesson belongs to the **SSTables and compaction** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module: understanding distributed architecture and the wide-column model, partition keys, query-driven table design, read/write consistency, CQL, replication, compaction, repair, error handling, and Java applications. The goal here is to master **SSTable immutability and the role of each metadata/index/data component**, thereby explaining the write/read paths, why a partition appears across multiple SSTables, and how to diagnose without corrupting data.

## 1. Three Concepts Not to Confuse

| Concept | Role | Is it an SSTable? |
|---|---|---|
| **Commit log** | Sequential write log that helps recover mutations not yet flushed when a node crashes | **No**; manages its own lifecycle |
| **Memtable** | Organized in-memory data structure receiving new mutations for a table | **No**; source of data to create SSTables via flush |
| **SSTable** | Set of immutable on-disk files containing sorted data and related indexes/metadata | **Yes**; unit of reading, compaction, snapshot, streaming |
| **SAI index** (*Storage-Attached Index*) | Secondary index structure, tied to the memtable/SSTable lifecycle when a table has SAI | **Not synonymous with primary index**; may add per-SSTable files |
| **Snapshot** | Consistent point-in-time copy at the SSTable file level, typically via hard links on supported filesystems | Does not create a “new data type”; references immutable SSTables |

**An SSTable belongs to a single table on a single node**, not “one shared file for the entire cluster”. Multiple replicas hold data that must be replicated, but **the SSTable files do not necessarily match byte-for-byte or in count**: flush, compaction, repair, and streaming happen independently per node.

Also, do not assume **each partition resides in only one SSTable**. A partition can have data in multiple SSTables and memtables, because its writes occur across different flush cycles.

### 1.1. What Does Immutability Guarantee?

- **No in-place overwrites** of row contents already inside an SSTable when a new mutation arrives.
- **Reads and writes can happen concurrently** without having to update old data structures in place.
- **Compaction writes new outputs** and then switches the active SSTables state; input files are only removed when it is safe to do so, including waiting for active readers.
- **Snapshots/hard links** are straightforward because referenced SSTable contents are no longer modified in place.
- **Metadata and indexes** are generated for the corresponding SSTable dataset; if data changes due to compaction, those structures for the new SSTable are also regenerated.

Immutability **does not** mean business data cannot be updated. `UPDATE` and `DELETE` remain valid; only **how versions are stored** differs from databases that update blocks in place.

## 2. Write Path: From CQL Mutation to SSTable

A simplified diagram for a mutation that has reached a **replica node**:

~~~text
Java/CQL client
      |
      v
Coordinator receives request -> selects replicas by partition token
      |
      v
Replica node
  +------------------------------+
  | commit log (durability)      |
  | memtable (live data)         |
  +------------------------------+
      |
      | flush: switch current memtable to read-only state,
      | continue writing to a new memtable
      v
  +------------------------------+
  | New, IMMUTABLE SSTable       |
  | Data + index + metadata      |
  +------------------------------+
      |
      | subsequent mutations go into the new memtable,
      | without modifying old SSTables
      v
  Compaction can merge multiple SSTables into a new SSTable
~~~

In Cassandra, the typical write path writes mutations to the **commit log** and **memtable**; the commit log provides **replay** capability after a crash for unflushed data. Durability policy, commit log configuration, consistency level, and replica health affect the conditions under which a request is acknowledged. Therefore, **a client receiving an ACK does not mean the mutation has already been flushed into an SSTable**.

**Flush** occurs when a memtable reaches system thresholds/conditions or when triggered via administrative tools. Cassandra switches the old memtable to read-only mode to flush while accepting new writes into another memtable; it writes sorted data out to an SSTable along with its accompanying components. Once a commit log span has been durably written to SSTables, the corresponding commit log segments can become eligible for reuse/deletion according to the node's mechanism.

Why it is called **Sorted**: within each SSTable, partitions are organized in **token order** (with `Murmur3Partitioner`, the token from hashing the partition key); rows within a partition are organized in **clustering key order**. This enables sequential lookups and merging, but **does not** mean partitions across the cluster are sorted by numeric key values or calendar dates.

### 2.1. One Row Having Multiple Versions Without Violating PRIMARY KEY

Suppose a table has `PRIMARY KEY (account_id)` and column `display_name text`.

~~~text
At t1: display_name = "Mai"       -> memtable -> SSTable A
At t2: display_name = "Mai Anh"   -> memtable -> SSTable B
At t3: DELETE display_name        -> memtable -> SSTable C

Logical read at t3: value is no longer live
Disk before compaction: A, B, C can still coexist
~~~

Cassandra does **not** have three distinct logical rows just because three SSTables carry the same `account_id`. They are **versions of cells or deletion markers** reconciled according to write metadata. `PRIMARY KEY` still identifies **one logical row** in the table.

Note that the write timestamp in mutation metadata is usually in **microseconds**, **distinct from** a CQL `timestamp` column storing business time in **milliseconds**. When reconciling versions, Cassandra compares the metadata write timestamp and conflict resolution rules, not an application-defined `updated_at` column unless the application implements its own logic.

## 3. An SSTable Is a Set of Files: Names, Directories, and Formats

On a node, Cassandra stores SSTables in the data directory corresponding to the **keyspace/table**. The path depends on `data_file_directories`, operating system, deployment, and version.

A simplified representation:

~~~text
<data_directory>/
  demo_ks/
    events_by_device_day-<table-id>/
      nb-1-big-Data.db
      nb-1-big-Index.db
      nb-1-big-Summary.db
      nb-1-big-Filter.db
      nb-1-big-Statistics.db
      nb-1-big-CompressionInfo.db
      nb-1-big-Digest.crc32
      nb-1-big-TOC.txt

      nb-2-big-Data.db
      nb-2-big-Index.db
      ...components of another SSTable...
~~~

This is an **example of a compressed BIG format**, not a mandatory file naming requirement. Each set shares a **common descriptor** such as `nb-1-big`; the suffix `Data.db`, `Index.db` identifies the component. In the example name:

- `nb`: **SSTable version** code in a BIG format series.
- `1`: generation identifier according to the version's rules.
- `big`: the BIG **SSTable format**.
- `Data.db`, `Index.db`, `TOC.txt`: component names.

On Cassandra 5.0, BIG format may use version code `oa`; depending on configuration, **BTI** may appear. Do not infer the Cassandra version from **a single** file or hard-code the `nb-*-big-*` pattern for every cluster. A table undergoing an upgrade/format migration may also contain SSTables of different formats/versions that the current node can still read.

### 3.1. A Component Does Not Mean One Partition

`Data.db` can contain **many partitions**. `Index.db`/`Partitions.db` is the index **within the same SSTable**, not one file per partition. Nor does `Summary.db` contain pre-aggregated SELECT results; it is an **index summary** to speed up lookups.

An SSTable typically has a **main data path** and **auxiliary files** for lookup, integrity, and statistics. When a component is missing or corrupted, handling depends on the component and version; **do not manually delete or edit a component file** thinking Cassandra will safely regenerate it on its own.

## 4. Data.db: Where the Actual Data Resides

`Data.db` is the main data component, holding data encoded according to the SSTable format. It can be visualized as:

~~~text
Data.db
  partition(token/key A)
    partition metadata
    static row (if any)
    clustering row #1
       columns/cells, write timestamps, TTL/tombstone metadata
    clustering row #2
       ...
  partition(token/key B)
    ...
  partition(token/key C)
    ...
~~~

This is a **logical diagram**, not a byte-for-byte binary dump. In practice, how row liveness, cells, static columns, range tombstones, and row index blocks are represented depends on the format/version.

Key points to understand:

1. **Partition key determines the partition group**, and the token/partitioner locates the group on the token ring.
2. **Clustering columns determine row ordering** within the same partition; declaring `WITH CLUSTERING ORDER BY` affects how data is organized/queried per schema.
3. **Cells carry write/delete metadata**: write timestamp, TTL/expiration depending on cell type, tombstone, etc., so the same column can have versions across multiple SSTables.
4. **Row/partition/range tombstones** can shadow multiple cells, not just a single scalar value.
5. **A partition can be very wide (wide partition)**: many clustering rows, many index blocks; in that case you must pay attention to row indexes and partition size, not just the total SSTable count.

**Do not directly edit `Data.db`** to “fix a record” or “delete a tombstone”. It is binary data with associated indexes/checksums/metadata; changing bytes manually can cause corruption or replica divergence. All business data modifications must go through CQL/supported APIs or controlled operational recovery procedures.

### 4.1. Data.db Is Usually Block-Compressed

When compression is enabled, Cassandra compresses `Data.db` into **compression chunks**. A request reading part of a partition may need to locate the relevant chunk, read the compressed data, and decompress that chunk; it does not mean decompressing **the entire SSTable**.

Compression efficiency depends on data type, block size, codec, number of tombstones, and access pattern. Compression reduces disk usage and I/O in some cases at the cost of CPU and chunk-read overhead. Changing a table's compression configuration does not immediately rewrite all old SSTables; the flush/compaction/rewrite lifecycle must be taken into account.

## 5. Primary Index of the BIG Format: Index.db

In the traditional **BIG format**, `Index.db` stores the **partition key → data offset** index in `Data.db`. Very wide partitions also have **position/index information across clustering row regions** (commonly called the promoted index or row index in BIG).

Conceptual example:

~~~text
Index.db (BIG):
  key A -> Data.db offset 0x001000
  key B -> Data.db offset 0x03B800
  key C -> Data.db offset 0x070400
  ... entries in index order ...

Data.db:
  [partition A ...][partition B ...][partition C ...]
~~~

The hex addresses are **illustrative**, not real offsets. The index helps Cassandra seek directly to the right byte range instead of sequentially scanning the entire `Data.db` for a partition key.

For a wide partition, when querying by clustering range:

~~~cql
-- Once the full partition key is known:
SELECT *
FROM demo_ks.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z';
~~~

Cassandra can use the index at the partition level and **row blocks** to narrow down the region to read. However, the index **does not turn an overly wide partition into multiple independent partitions**, nor does it replace the partition key with a global secondary index.

### 5.1. Primary Index Differs from Secondary Index

The name `Index.db` here refers to the **SSTable-internal primary on-disk index**, serving **to locate data whose partition key is already known**.

It **does not** mean Cassandra builds a general-purpose B-tree/query index on every column of the table. To query `WHERE event_type = 'LOGIN'` across all tenants, you still need a **query-driven table** or a specifically designed and tested index. SAI will create **separate components** when enabled.

## 6. Index Summary of BIG: Summary.db

With the BIG format, `Summary.db` is a **sample of entries in `Index.db`** that helps quickly locate the vicinity of the target key. Documentation describes a typical sampling rate of **every 128 entries** by default, though sampling can vary based on memory budget, configuration, and version.

Visualization:

~~~text
Index.db:
  A  B  C  D  E  F  G  H  I  J  K  ...

Summary.db:
  A  ..........  G  ..........   (illustrative sampling example)
~~~

When searching for key `E`, Cassandra can use the summary to **jump to the index region near E**, then read the necessary part of `Index.db` to determine the `Data.db` offset. Because the summary is a **sample**, it is not a complete index and cannot by itself confirm whether a key exists.

| Structure | What question does it answer? | Is it enough to read column values? |
|---|---|---|
| `Summary.db` | Which region of the partition index should lookup start at? | **No** |
| `Index.db` | At which offset in `Data.db` is this partition key located? | **No** |
| `Data.db` | What do the specific values/cells/rows contain? | **Yes**, when decoded with appropriate metadata |

**Version note:** BTI in Cassandra 5.0 uses a different trie structure and therefore **does not use a BIG-style index summary**. Consequently, if you do not see `Summary.db` in a BTI file set, that is **not** a sign of a missing SSTable component.

## 7. Bloom Filter: Filter.db

`Filter.db` stores a **Bloom filter** structure of the **partition keys** present in an SSTable. A Bloom filter helps answer:

- **Definitely not present**: the partition key is not in this SSTable.
- **Possibly present**: the partition key may be in this SSTable; index/data must be checked to confirm.

A Bloom filter is a **probabilistic filter** that can produce **false positives**: it says *possibly present*, yet the key is not actually in the SSTable. For a Bloom filter operating properly as designed, it will not miss an existing key with a **false negative**.

~~~text
Find partition key = P in SSTable S

                Bloom filter S
                     |
           +---------+---------+
           |                   |
         "no"              "maybe"
           |                   |
     skip SSTable S      use index -> Data.db
                               |
                         verify actual key
~~~

This prevents a partition read query from blindly accessing data in **all** SSTables, especially when the SSTable count is large while a partition only appears in a few files.

### 7.1. Bloom Filter Does Not Filter Clustering Rows

This internal Bloom filter **does not** answer “is there a row with `occurred_at = T`?” by checking individual clustering keys. It filters at the **partition key level**. When partition P actually exists in S, Cassandra still needs to read the appropriate index/data to know the clustering rows and cells.

Nor is the Bloom filter an index for `WHERE status_code = 500` or `WHERE tag CONTAINS ...` across all partitions.

### 7.2. Memory and False-Positive Chance

The Bloom filter is typically stored as `Filter.db` on disk and loaded/kept in **off-heap memory** when used on the read path. The table setting `bloom_filter_fp_chance` determines the acceptable false-positive rate.

Example:

~~~cql
-- Illustrative configuration only; measure in practice before changing.
ALTER TABLE demo_ks.events_by_device_day
WITH bloom_filter_fp_chance = 0.01;
~~~

Lowering `bloom_filter_fp_chance` can reduce wasted I/O from false positives, but **increases memory consumption**; there is no universally optimal value for every workload. An SSTable's Bloom filter is built during flush/compaction; changing the table parameter **does not immediately update filters of old immutable SSTables**. They must be rewritten through the appropriate SSTable lifecycle to adopt the new setting.

Do not tune parameters in production without a baseline of **BloomFilterFalseRatio**, **BloomFilterOffHeapMemoryUsed**, latency, and disk I/O. For append-mostly tables with few reads, the optimal configuration may differ from read-heavy key-lookup tables.

## 8. The New BTI Format: Partitions.db and Rows.db

**Cassandra 5.0** introduced the **BTI (Big Trie-Indexed)** format from CEP-25. When a node is configured to use BTI for creating SSTables, the primary index mechanism differs from BIG:

| BIG (traditional) | BTI (Cassandra 5.0+) | Meaning |
|---|---|---|
| `Index.db` | `Partitions.db` | Locates partitions using a trie/prefix instead of a BIG-style partition index |
| Promoted row index inside BIG mechanism | `Rows.db` | Dedicated row-blocks index for partitions that are sufficiently wide |
| `Summary.db` | **No equivalent needed** | The trie supports direct key lookup; does not use a BIG-style index summary |
| `Data.db` | `Data.db` | The main data component still exists |
| `Filter.db`, `Statistics.db`, ... | Corresponding components | Filtering, metadata, and integrity functions are still needed per format |

### 8.1. What Does Partitions.db Do?

In BTI, `Partitions.db` holds an index based on a **trie (prefix tree)** that maps distinguishing key prefixes to offsets in `Data.db` or to appropriate row index information. Tries leverage **shared byte prefixes** to reduce lookup cost and index size in many cases.

Do not interpret `Partitions.db` as “one file per partition”. It is still a **component of the whole SSTable**.

### 8.2. What Does Rows.db Do?

`Rows.db` serves to navigate to **row blocks** inside wide partitions that need deeper indexing. For small partitions that do not need multi-block row indexing, the lookup path can point directly into `Data.db`. The `Rows.db` file helps the system avoid loading a huge promoted index into memory when a partition has very many clustering rows.

The goal is **fast lookup of both partitions and clustering slices** without relying on BIG's key cache/index summary mechanism.

### 8.3. Does BTI Require Configuration?

BTI is **not** guaranteed to be the default in every Cassandra 5.x build/distribution. Apache documentation shows an example configuration in `cassandra.yaml`:

~~~yaml
sstable:
  selected_format: bti
~~~

**This is only an example for understanding the format. Do not edit `cassandra.yaml` or restart production nodes based on this lesson.** You must verify format selection on your exact build, upgrade/downgrade compatibility, streaming, resources, and rollout plan.

**Selecting BTI** affects **newly written SSTables** (flush/compaction/rewrite); it does not immediately convert all old BIG SSTables into BTI. A node can read both BIG and BTI SSTables if the version supports it. Therefore, operational tools must inspect the **format in the descriptor** rather than assuming `Index.db` is always present.

## 9. Metadata and Integrity Components

The following files are not primary business data, but they are essential for reading, recovering, and administering SSTables.

| Component | Contents / Purpose | What **not** to infer |
|---|---|---|
| **`Statistics.db`** | Statistical metadata: min/max write timestamp, TTL, tombstone/deletion, clustering range, repair state, compaction level, certain histograms... | Not actual row contents or an SQL query statistics table |
| **`CompressionInfo.db`** | Offsets/metadata of compression chunks to locate and decompress the appropriate `Data.db` regions | Not a complete copy of compressed data |
| **`Digest.crc32`** | Digest/CRC-32 for checking `Data.db` integrity per format | CRC is not cryptographic security proof or anti-tamper signature |
| **`CRC.db`** | Per-chunk checksums for certain **uncompressed**/compatible format cases | Not every SSTable has both `CRC.db` and `CompressionInfo.db` |
| **`TOC.txt`** | List of components belonging to **the same SSTable** | Not a list of all SSTables in the entire table/cluster |
| **`SAI*.db`** | Components attached to SAI secondary indexes when enabled | Does not replace `Index.db` or `Partitions.db` for primary-key lookups |

File names depend on version and format type; do not treat this table as a contract requiring “all 8 exact files”. For instance, an uncompressed table may not have `CompressionInfo.db`; a table without SAI enabled will have no SAI components. **The specific SSTable's `TOC.txt` is the direct source of truth** for identifying the actual component set.

### 9.1. Statistics.db and Tombstone Metadata

`Statistics.db` contains values used by tools such as `sstablemetadata` to display:

- **Min/max timestamp** of cells in the SSTable, related to write metadata.
- **Min/max local deletion time** as encoded for deletions/TTLs.
- **TTL min/max**, histograms, and estimates of tombstone reclaimability.
- **Repaired-at**, pending repair/session metadata in supported versions.
- **Compaction level** when the compaction strategy uses levels.
- **First/last token/key**, partition size estimates, and related compression information.

Do not confuse the **microsecond write timestamp in statistics** with a CQL `timestamp` column typically representing an `Instant` in milliseconds. Statistics are aggregated per SSTable and are insufficient to assert “which rows have `event_type = LOGIN`”.

The **estimated droppable tombstones** value is only an **estimate** based on time/metadata; it does not guarantee an actual compaction will drop that exact number. Eligibility for purging is also constrained by **overlap** with other SSTables, repair state, and configuration.

### 9.2. How Is CompressionInfo.db Used?

With chunk-compressed `Data.db`:

~~~text
Need to read a logical offset in Data.db
       |
       v
CompressionInfo.db:
  chunk index -> on-disk position and compression metadata
       |
       v
Read the relevant compressed chunk
       |
       v
Decompress -> decode partition/row/cell
~~~

Because compression is block-based, reading a few logical bytes may require reading/decompressing an entire chunk; hence chunk size affects **read amplification** and **compression ratio**. Do not manually edit `CompressionInfo.db`: byte offsets will no longer match the data.

### 9.3. Digest, CRC, and Integrity

Digests/CRCs help detect data errors caused by storage corruption or transmission/write faults at the appropriate layers. However:

- CRC-32 is **not** cryptography to defend against someone with write permissions intentionally altering files.
- Checksum verification **does not** guarantee all business data is valid — a misparsed timestamp still has a valid checksum.
- You cannot “fix corruption” by replacing `Digest.crc32` to match a damaged file.
- When corruption is suspected, follow backup/snapshot procedures, replica verification, and Cassandra recovery tools, rather than editing a single component.

### 9.4. What Role Does TOC.txt Play?

`TOC.txt` describes the components of an SSTable under a descriptor. For compressed BIG, the TOC might list:

~~~text
Data.db
Index.db
Summary.db
Filter.db
Statistics.db
CompressionInfo.db
Digest.crc32
TOC.txt
~~~

For BTI, it may list `Partitions.db`, `Rows.db` instead of `Index.db`/`Summary.db`. Even though the file is plain text, **do not edit TOC directly** to “hide” a component: doing so can render the SSTable unreadable or cause file management errors.

## 10. Read Path: How Does Cassandra Use These Components?

For a query specifying the full partition key, a replica needs to read live state from the **memtable and relevant SSTables**:

~~~text
SELECT WHERE partition_key = P
              |
              v
        Memtable / cache
              |
              v
       SSTables that may contain P
              |
     +--------+-------------------------+
     |                                  |
  Filter.db                         min/max key,
  (Bloom filter)                     token/metadata
     |                                  |
     +------- select candidate SSTables +
                        |
                        v
             BIG: Summary.db + Index.db
               or BTI: Partitions.db
                        |
                        v
          Data.db offset and row blocks
            (Rows.db/row index if needed)
                        |
                        v
          read/decompress/decode cells
                        |
                        v
           merge with memtable and data
             from other SSTables with P
                        |
                        v
             conflicts, TTL, tombstones
                        |
                        v
                  Row/Column Result
~~~

This is a **conceptual** diagram, not a fixed function-call order across all versions. Cassandra may use key cache, row cache, index summary, min/max metadata, partition read optimizations, and various shortcuts. The actual read path also depends on query type (row/range/collection/SAI) and consistency level.

A key takeaway: **the Bloom filter only excludes SSTables that lack the partition key**. If the same partition P appears in A, B, and C, the replica may have to read data from **multiple SSTables** and merge versions.

### 10.1. Example of Three SSTables with the Same Partition

~~~text
SSTable A (older):
  P -> status = "PENDING", amount = 100

SSTable B (newer):
  P -> status = "PAID"

SSTable C (even newer):
  P -> tombstone(amount)

Current memtable:
  P -> note = "checked"

Logical result when reading P:
  status = "PAID"
  amount = null   (shadowed by tombstone)
  note = "checked"
~~~

**Write timestamp** metadata and reconciliation rules (including ties with identical timestamps) determine which cells are live; the diagram only illustrates typical chronological ordering. Cassandra does not always pick “the entire newest row” and discard all columns from older versions — **columns can be written in separate mutations**.

### 10.2. Read Amplification and SSTable Count

One way to picture **read amplification** is the number of blocks, indexes, filters, and versions that must be examined to return **one logical result**. Having the same partition across multiple SSTables can increase read work; Bloom filters and indexes help **skip** irrelevant data, but do not eliminate the need to reconcile versions that are genuinely involved.

When many SSTables overlap by key range, read queries for a known partition may need to inspect multiple files. That is one reason **compaction** is necessary.

Do not conclude “if there are 20 SSTables, every SELECT reads all 20 `Data.db` files”: most may be eliminated by Bloom filters/ranges/indexes. Nor should you conclude “low SSTable count guarantees low latency”: a very wide partition or dense tombstones can still cause slow reads.

## 11. Compaction: Writing New SSTables, Not Modifying Old Ones

Compaction reads a selected group of SSTables, **merges** data versions by key/timestamp, and writes one or more **new** SSTables. Once the outputs are written/committed under the file management mechanism, input SSTables are removed from the active set and can be reclaimed once no readers/snapshots hold references.

~~~text
Before:
  SSTable A: P(status=PENDING), Q(...)
  SSTable B: P(status=PAID),   R(...)
  SSTable C: P(tombstone),    S(...)

                 compaction
                     |
                     v
After:
  SSTable D: live cells/rows,
             tombstones that must still be kept,
             new metadata/index/filter

  A, B, C are no longer in the live set once swap succeeds,
  but files are only deleted when safe.
~~~

**Note:** compaction does not necessarily select every SSTable containing a partition in a single pass. If another SSTable outside the compaction set holds older values, Cassandra must **preserve the appropriate deletion markers** so that old data is not resurrected.

### 11.1. When Is a Tombstone Purged?

A tombstone is not dropped simply because `gc_grace_seconds` has elapsed:

1. The tombstone must be **old enough** per the table's grace/gc policy.
2. Compaction must ensure **there is no older data in other SSTables that the tombstone still needs to shadow**; overlap/coverage checks apply.
3. **Repaired/unrepaired** state and related settings can restrict purging.
4. An eligible compaction must **actually run**; the grace period only defines eligibility for purging, not an exact-time scheduled deletion job.

**Do not arbitrarily set `gc_grace_seconds=0`** to clear tombstones quickly. If a replica missed a delete and was not repaired in time, old data can be re-synchronized as **zombie data**. You must coordinate retention, repair schedules, node outages, compaction, and data characteristics.

### 11.2. Compaction Strategies Determine Which SSTables Merge

Some strategies:

| Strategy | Core idea | Workload patterns to evaluate |
|---|---|---|
| **STCS** — SizeTieredCompactionStrategy | Groups similarly sized SSTables to merge | Write-heavy, aiming to limit write amplification in certain workloads |
| **LCS** — LeveledCompactionStrategy | Organizes SSTables into levels to bound overlap across levels | Read-heavy, lookups needing more predictable latency |
| **TWCS** — TimeWindowCompactionStrategy | Groups SSTables by time windows | Time-series data with matching TTL/write batch characteristics |
| **UCS** — UnifiedCompactionStrategy (Cassandra 5.0+) | Adjusts compaction selection by overlap/size, allowing trade-off tuning | Must benchmark exact version, read/write load, and resources |

The strategy decides **when and which SSTables** are rewritten, rather than turning **immutable SSTables into in-place mutable files**. Output SSTables' `Data.db`, index, filter, and statistics components are still generated in the corresponding format.

Do not choose TWCS solely because a column has type `timestamp`; mixed TTLs, late writes, backfills, and long-lived/old data can break the “windows expire cleanly” expectation. You must measure data distribution and the retention model.

### 11.3. Compaction Does Not Replace Repair

**Compaction** merges data **on a single node**. **Repair** compares/reconciles data **across replicas** to fix inconsistencies. **Replication factor** and consistency level govern replication and acknowledgment per schema/configuration, but do not automatically replace repair when a node misses mutations.

An SSTable's repaired/unrepaired metadata can affect compaction selection. Hence, do not assume “all SSTables with overlapping token ranges will immediately merge together” if repaired groupings or compaction strategies differ.

## 12. CQL Practice: Creating Multiple SSTable Versions in a Controlled Way

The following lab is **only for test clusters where you have administrative permission**. `nodetool flush`, compaction, and schema changes affect node resources; do not run them blindly in production.

### 12.1. Wide-Column Schema by Device/Day

~~~cql
-- Example assumes an existing demo_ks keyspace you are permitted to use.
CREATE TABLE demo_ks.events_by_device_day (
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Query pattern served: “Read the 50 latest events for a device on a UTC day”, when `(device_id,event_day)` is fully known. This design reduces the risk of a single partition holding **years of events** for a device, though if one device emits too much data per day, you still need to measure size, shard, or use smaller buckets.

### 12.2. Initial Write, Flush, Then Update

~~~cql
INSERT INTO demo_ks.events_by_device_day (
    device_id, event_day, occurred_at, event_id, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'LOGIN', 'v1'
);
~~~

If you have permissions on the test node:

~~~text
nodetool flush demo_ks events_by_device_day
~~~

The flush command **does not** assert that all other replicas in the cluster flushed simultaneously. It instructs the connected node to flush the corresponding table/keyspace.

Write an update with the **same primary key**:

~~~cql
UPDATE demo_ks.events_by_device_day
SET payload = 'v2'
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:00:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Flush the lab node again, then delete the `payload` column:

~~~cql
DELETE payload
FROM demo_ks.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:00:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

If flushed again, a node may have **multiple SSTables for the same partition**, carrying `payload='v1'`, `payload='v2'`, and a tombstone. Actual timing of flushes/compactions/background tasks can cause **observed SSTable counts to differ from expectations**; do not rely on seeing exactly “3 Data.db files” on every run.

### 12.3. SELECT and WRITETIME: Observing Logical State

~~~cql
SELECT occurred_at, event_id, event_type, payload
FROM demo_ks.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

`payload` can return `null` because it was deleted, even though older `Data.db` files still contain bytes of `'v1'`/`'v2'`. `SELECT` reflects **reconciled logical data**, rather than listing all SSTable versions.

You can inspect the write timestamp of a **regular column that currently has a value**:

~~~cql
SELECT event_type, WRITETIME(event_type) AS event_type_write_us
FROM demo_ks.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21';
~~~

`WRITETIME(event_type)` is in **microseconds**. Do not call `WRITETIME(occurred_at)` because `occurred_at` is a clustering column, not a regular data column from which to retrieve a write time.

### 12.4. Java Driver: Keys and Timestamps Must Remain Stable on Retry

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

// CqlSession session = ...; // Connect to keyspace/cluster outside this example.
UUID deviceId =
    UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID eventId =
    UUID.fromString("22222222-2222-4222-8222-222222222222");

Instant occurredAt = Instant.parse("2026-11-21T08:00:00Z");
LocalDate dayUtc = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();

PreparedStatement insert = session.prepare(
    "INSERT INTO demo_ks.events_by_device_day "
  + "(device_id,event_day,occurred_at,event_id,event_type,payload) "
  + "VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement bound = insert.boundStatementBuilder()
    .setUuid(0, deviceId)
    .setLocalDate(1, dayUtc)
    .setInstant(2, occurredAt)
    .setUuid(3, eventId)
    .setString(4, "LOGIN")
    .setString(5, "v1")
    .build();

session.execute(bound);
~~~

**Retry after timeout**: reuse the exact same `deviceId`, `dayUtc`, `occurredAt`, and `eventId`. If you generate a new ID/timestamp, you create a **new row** instead of another mutation for the same row. This both corrupts business data and forces multiple versions/SSTables to store unnecessary content.

SSTable immutability is a **storage detail**; the Java Driver does not directly write `Data.db`, `Index.db`, or `Statistics.db`. The application only knows CQL and consistency/mutations. Do not design business logic assuming “the data is definitely in SSTable number 3”.

## 13. Safe Diagnostics: nodetool, Metadata, and Metrics

### 13.1. Inspecting Nodes/Tables with nodetool

Useful commands when administrative access is available:

~~~text
nodetool tablestats demo_ks.events_by_device_day
nodetool compactionstats
nodetool status
~~~

Metrics to look for:

| Metric | Indicative meaning | Do not jump to conclusions |
|---|---|---|
| **SSTable count** | Number of live SSTables for the table/node | Not the number of INSERTs or partitions |
| **SSTables per read** | Number of SSTable data files actually read per partition read | Not every file that Bloom/index already skipped |
| **Bloom filter false positives/ratio** | Rate at which the filter reports possible match when data is absent | Not the number of lost rows |
| **Bloom off-heap memory** | Memory allocated for Bloom filters | Not total Java heap |
| **Index summary off-heap memory** | BIG summary cost when present | Does not apply the same way to BTI |
| **Compression metadata memory** | Memory for locating/decompressing chunks | Not raw Data.db in RAM |
| **Pending compactions** | Pending compaction work | Not automatically an error; check the trend |
| **Space used live/total** | SSTable disk usage under different accounting methods | Snapshots, hard links, and filesystems can affect observed usage |
| **Estimated partition size** | Indicator of wide partitions/hotspots | Only an estimate/histogram; investigate against the workload |

**Look at trends** over time and correlate with p95/p99 read latency, write latency, disk I/O, free disk, and flush queue. A single point-in-time snapshot of metrics is usually insufficient to decide on changing compaction strategy.

### 13.2. sstablemetadata, sstabledump, sstablepartitions

Tools such as `sstablemetadata`, `sstabledump`, and (on supported versions) `sstablepartitions` help **inspect SSTables at the file level**. Illustrative examples:

~~~text
sstablemetadata /path/to/oa-1-big-Data.db
sstabledump /path/to/oa-1-big-Data.db
sstablepartitions /path/to/oa-1-big-Data.db
~~~

**Important safety notes:**

- Paths are **placeholders** only. Never probe and run commands haphazardly in production.
- Tools, flags, and whether a node must be running or stopped **depend on the specific command/version**. Read the official documentation for your exact deployment.
- Whenever possible, use a **snapshot or consistent copy of SSTables** for investigation to avoid altering files actively managed by Cassandra.
- `sstabledump` can display **real data and sensitive information**; manage permissions, log outputs, and redaction.
- **Do not run `scrub`, `upgradesstables`, `compact`, or major compaction** just to “take a look”; those tools can rewrite files and consume significant disk/CPU.
- If you encounter a checksum mismatch/corruption, **do not delete a single component** to attempt self-healing; follow your incident runbook and validated restore/repair plan.

### 13.3. Interpreting the Right Version/Format

When inspecting an SSTable directory, verify first:

1. **Which node and keyspace/table is this?**
2. **Which SSTable descriptor is it?** For example, BIG or BTI, and which version.
3. **Which components are actually listed in that set's TOC?**
4. **Is the SSTable compressed? Does it have SAI indexes?**
5. **Which compaction strategy does the table use? What is the repaired/unrepaired metadata?**

Only after that should you compare sizes or hypothesize “missing Index.db”. For **BTI**, not seeing `Index.db`/`Summary.db` is **normal**; look for `Partitions.db` and the corresponding components instead.

## 14. Common Misconceptions That Cause Incidents

| Misconception | Reality | Correct action |
|---|---|---|
| “An SSTable is a single Data.db file.” | An SSTable is a **set of components** for data/index/metadata/integrity. | Identify by descriptor + TOC. |
| “UPDATE modifies records in old Data.db.” | Old SSTables are **immutable**; new mutations go to memtable then new SSTables. | Understand read reconciliation and compaction. |
| “DELETE must erase bytes immediately.” | Deletes create tombstones; old bytes may remain on disk. | Design safe TTL/repair/compaction. |
| “Each partition appears in only one SSTable.” | A partition can span multiple SSTables and memtables. | Monitor SSTables per read. |
| “Index.db is a secondary index for all columns.” | It is **BIG's internal primary on-disk index**. | Use proper partition keys/SAI/query tables. |
| “Summary.db holds business data summaries.” | It is a **sampling of Index.db** in BIG. | Use index summary to understand the read path. |
| “If Bloom says yes, it definitely exists.” | Bloom filters have **false positives**. | Check index/data to confirm. |
| “Bloom says no, but it might still exist.” | A properly functioning filter **has no false negatives** for inserted keys. | Investigate software/data integrity if evidence suggests otherwise. |
| “Index.db is mandatory on all Cassandra 5.0 nodes.” | **BTI** uses `Partitions.db`/`Rows.db`; BIG still has Index/Summary. | Check format rather than guessing from version. |
| “Having CompressionInfo.db means the whole SSTable must be decompressed on read.” | Data is chunk-compressed; only needed chunks are read. | Evaluate chunk size/CPU/I/O. |
| “Statistics.db is a table you can SELECT in CQL.” | It is **internal metadata**, not a CQL table. | Use `sstablemetadata`/metrics. |
| “CRC proves business data is valid.” | Checksums only verify format-level integrity. | Validate at the API and round-trip tests. |
| “After gc_grace_seconds, tombstones vanish right on the hour.” | Requires compaction and safety/overlap/repair checks. | Monitor repair and purge eligibility. |
| “Compaction fixes all replicas.” | Compaction is **node-local**; repair is **across replicas**. | Distinguish the roles of both mechanisms. |
| “Many SSTables always means every read opens that many Data.db files.” | Bloom, min/max, and indexes can skip most of them. | Measure SSTablesPerRead, latency, false positives. |
| “Lower gc_grace_seconds to 0 to clean up fast.” | Can cause zombie data if a replica missed a delete. | Change only per runbook and repair guarantees. |
| “Only 1000 rows means the partition must be small.” | Large payloads or many versions/tombstones still cause load. | Measure bytes/partition, wide partitions, tombstones. |
| “Client ACK means Data.db was definitely written.” | ACK does not mean SSTable flush happened. | Understand commitlog, consistency, and recovery. |

## 15. Comprehension Check Exercises

### Exercise 1 — Which Component Holds What?

Given the descriptions: “row bytes”, “partition index”, “bloom filter”, “TTL/tombstone statistics”, “compressed chunk locator”, “component list”.

**Answer:** respectively **`Data.db`**, **`Index.db` in BIG or `Partitions.db` in BTI**, **`Filter.db`**, **`Statistics.db`**, **`CompressionInfo.db`**, **`TOC.txt`**.

### Exercise 2 — Why Doesn't UPDATE Modify an SSTable?

A client reads `balance = 100`; then executes `UPDATE balance = 120`. Does Cassandra open the `Data.db` holding value 100 and overwrite it directly?

**Answer:** no. The mutation is written via **commit log/memtable**, then becomes a new SSTable; on read, Cassandra reconciles versions. Compaction may later replace the set of SSTables with a new SSTable containing the appropriate version.

### Exercise 3 — Bloom Filter False Positive

A Bloom filter returns “maybe present” for partition P, yet `Index.db` does not find that key. Is the data corrupted?

**Answer:** not necessarily; that can be a **normal false positive**. It costs an extra lookup but does not lose data. Conversely, if the filter returns “no” for a key actually present in that same SSTable, integrity/corruption must be investigated because it violates Bloom filter design guarantees.

### Exercise 4 — BIG vs BTI

You see files `da-10-bti-Data.db`, `da-10-bti-Partitions.db`, `da-10-bti-Rows.db`, without `Index.db` or `Summary.db`.

**Question:** is this SSTable missing its index?

**Answer:** no. This is **BTI**, using trie-indexed partition/row components. Inspect the descriptor/TOC and version rather than applying a BIG checklist to BTI.

### Exercise 5 — Tombstone Older Than 10 Days Not Yet Purged

A table has tombstones past `gc_grace_seconds` that still remain in SSTables.

**Question:** is that a Cassandra bug?

**Answer:** not necessarily. Either an eligible compaction has not run yet, another SSTable holds older data that the tombstone must still shadow, or repair/overlap conditions are not met. Do not manually delete tombstones. Investigate compaction, metadata, overlap, and repair schedules.

### Exercise 6 — One Partition Across Multiple SSTables

After three writes/flushes on the same partition P, a node has three SSTables holding different parts of P. SELECT returns all the latest fields.

**Question:** how does Cassandra do this? Does it turn P into three distinct CQL partitions?

**Answer:** no. It looks up the relevant SSTables/memtables and **merges/reconciles** them by write metadata; P remains **one logical partition**. Compaction can later merge the versions into a new SSTable.

### Exercise 7 — Java Retry and Duplicate Rows

A Java worker writes an event with `event_id=UUID.randomUUID()`. After a timeout, the worker generates a new UUID and retries the write. Could this create two rows?

**Answer:** yes. They have **different primary keys**; Cassandra does not know they represent the same business event. Generate the event ID **once** and keep timestamp/bucket/ID stable across retries.

### Exercise 8 — Choosing Diagnostic Tools

Goals: “Know how many live SSTables a table has and its Bloom false-positive ratio”; “View min/max timestamp and repaired-at metadata of a specific SSTable”; “Inspect wide partitions with many tombstones”.

**Answer:** respectively use **`nodetool tablestats`/metrics**, **`sstablemetadata`**, and **`sstablepartitions`** (if supported by your Cassandra version), in a controlled environment/path. Do not delete files or run major compaction just to gather metrics.

## 16. SSTable Design and Operations Checklist

- [ ] Distinguished **commit log**, **memtable**, and **SSTable** in the write path?
- [ ] Understood **write ACK does not mean flush**, and crash recovery involves the commit log?
- [ ] Understood SSTables are **immutable**; UPDATE/DELETE create mutations/versions rather than modifying old Data.db?
- [ ] Known that an SSTable is a **set of multiple files** sharing a descriptor, not just `Data.db`?
- [ ] Known that `Data.db` stores rows/cells/tombstones ordered by partition token and clustering order?
- [ ] Distinguished `Index.db` (BIG) from `Partitions.db`/`Rows.db` (BTI)?
- [ ] Understood `Summary.db` is a BIG index sampling, with no mandatory equivalent in BTI?
- [ ] Understood `Filter.db` is a **partition-key** Bloom filter, having false positives but no false negatives?
- [ ] Known `CompressionInfo.db` locates compressed chunks, not business data?
- [ ] Known `Statistics.db` stores timestamp/tombstone/TTL/repair/compaction metadata?
- [ ] Known `Digest.crc32`, `CRC.db`, and `TOC.txt` serve integrity/component discovery per format?
- [ ] If SAI is enabled, distinguished SAI components from the **primary-key index**?
- [ ] Measured SSTablesPerRead, BloomFilterFalseRatio, index summary/off-heap memory, and pending compactions?
- [ ] Known tombstone purging also depends on **gc_grace_seconds, overlap, compaction, and repair**, not just time?
- [ ] Avoided using `gc_grace_seconds=0`, `scrub`, or major compaction as ad-hoc quick fixes?
- [ ] Chosen partition/bucket keys per query to avoid wide partitions and heavy overlap?
- [ ] If using the Java Driver, kept IDs, timestamps, and buckets stable across mutations/retries?
- [ ] Established snapshot/backup, repair, and corruption investigation procedures **without directly editing SSTable files**?
- [ ] Verified Cassandra version, SSTable format, and tool requirements before operating?
- [ ] When changing compaction/compression/Bloom settings, benchmarked and evaluated SSTable rewrite lifecycles?

## References

- [Apache Cassandra — Storage Engine (SSTable components, BIG/BTI)](https://cassandra.apache.org/doc/latest/cassandra/architecture/storage-engine.html).
- [Apache Cassandra — Compaction Overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html).
- [Apache Cassandra — Tombstones, gc_grace_seconds, and purge conditions](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/compaction/tombstones.html).
- [Apache Cassandra — Bloom Filters](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/bloom_filters.html).
- [Apache Cassandra — Trie-Indexed SSTables / BTI (Cassandra 5.0)](https://cassandra.apache.org/_/blog/Apache-Cassandra-5.0-Features-Trie-Memtables-and-Trie-Indexed-SSTables.html).
- [Apache Cassandra — nodetool tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html).
- [Apache Cassandra — sstablemetadata](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstablemetadata.html).
- [Apache Cassandra — sstablepartitions](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstablepartitions.html).
- [Apache Cassandra — Metrics](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/metrics.html).

**Key Takeaway:** **Immutable SSTables** form the foundation of Cassandra's storage engine: new writes do not overwrite old `Data.db` files, instead creating new SSTables and letting **read reconciliation and compaction** handle multiple versions. **`Data.db` holds data**, **indexes locate partitions/rows** (BIG uses `Index.db`/`Summary.db`; BTI uses `Partitions.db`/`Rows.db`), **`Filter.db` filters out definitely irrelevant SSTables**, and **`Statistics.db`, `CompressionInfo.db`, digest/CRC, and `TOC.txt`** serve metadata, performance, and integrity. Understanding each component helps design queries properly, run compaction/repair safely, and avoid “quick fixes” by directly modifying immutable files.
