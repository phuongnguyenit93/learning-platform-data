# REINDEX, REINDEX CONCURRENTLY, and Handling Index Bloat in PostgreSQL

Indexes help PostgreSQL locate data faster, yet indexes are also physical structures that require maintenance. INSERT creates index entries; UPDATE may need to update indexes; DELETE leaves behind entries that must be cleaned once tuples are no longer needed. B-tree pages can also undergo page splits, density shifts, and fragmentation depending on the workload.

When an index bloats or shows signs of corruption, PostgreSQL provides the **REINDEX** command to rebuild the index from source data. This is a maintenance operation with substantial impact on locks, I/O, disk space, and query latency.

There are two primary operational modes:

- **Standard REINDEX**: simpler and usually faster, but takes a strong lock on the associated table, blocking both reads and writes.
- **REINDEX CONCURRENTLY**: builds a new index across multiple phases so applications can continue reading and writing for most of the operation, at the trade-off of extra resources, multiple scans, and additional operational constraints.

The first thing to determine is which object is bloated: the heap table, the TOAST relation, or an index. **REINDEX only rebuilds indexes; it does not compact the heap table.** If the table is bloated with dead tuples, investigate VACUUM and transaction horizons; if the heap needs a rewrite, that is a separate problem.

~~~mermaid
flowchart TD
    A["Spot large relation or slow query"] --> B["Identify heap, TOAST, or index"]
    B --> C["Measure index size and density"]
    C --> D{"Evidence of index bloat or corruption?"}
    D -->|"No"| E["Investigate query plan, schema, workload"]
    D -->|"Yes"| F{"Maintenance window available?"}
    F -->|"Yes"| G["Standard REINDEX"]
    F -->|"No"| H["Evaluate REINDEX CONCURRENTLY"]
    G --> I["Monitor locks, disk, latency"]
    H --> I
    I --> J["Verify new index and re-measure"]
~~~

This lesson belongs to the **VACUUM** chapter in the **Database Engine Relational PostgreSQL** module. We will cover B-tree indexes, bloat signals, measurement methods, differences between REINDEX and VACUUM, lock behavior, the concurrent reindex workflow, failure recovery, and safe operational planning.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what REINDEX does and when an index needs rebuilding.
2. Distinguish `REINDEX INDEX`, `TABLE`, `SCHEMA`, `DATABASE`, and `SYSTEM`.
3. Understand the locking and downtime impact of standard REINDEX.
4. Describe `REINDEX CONCURRENTLY` and its build phases.
5. Know the key restriction: concurrent reindex cannot run inside a transaction block.
6. Distinguish index bloat from heap/table bloat and TOAST growth.
7. Measure index sizes using relation-size functions.
8. Estimate B-tree density with `pgstattuple`/`pgstatindex` where the extension is permitted.
9. Understand why dead tuple counts do not equate directly to index bloat.
10. Select indexes to rebuild based on metrics and workload.
11. Understand the impact of fillfactor, page splits, and write patterns.
12. Identify index corruption scenarios and the limits of REINDEX.
13. Handle invalid indexes left behind after a failed concurrent reindex.
14. Plan disk space, I/O, locks, replica lag, and maintenance windows.
15. Verify results after REINDEX and design a rollback-capable maintenance process.

## 2. What Do PostgreSQL Indexes Store?

An index is an auxiliary structure that helps locate rows in a table. For a B-tree, each index entry holds key values and tuple location pointers into the heap. Indexes support:

- Equality and range lookups.
- `ORDER BY` aligned with index ordering.
- `UNIQUE` and `PRIMARY KEY` enforcement.
- Joins and foreign key workloads.
- Index-only scans when the index covers requested columns and the visibility map permits.

Example:

~~~sql
CREATE INDEX idx_orders_customer_created
ON public.orders (customer_id, created_at);
~~~

A query with matching predicates:

~~~sql
SELECT order_id, created_at, total_amount
FROM public.orders
WHERE customer_id = 42
  AND created_at >= timestamptz '2026-01-01 00:00:00+00'
ORDER BY created_at;
~~~

PostgreSQL can choose this index if the planner estimates it costs less than alternative paths.

### An Index Is Not a Plain Copy of the Table

An index contains page headers, internal pages, leaf pages, tuple entries, free space, and metadata. Its size depends on:

- Index access method.
- Row count and key width.
- `INCLUDE` columns.
- Collation and operator class.
- Fillfactor.
- Insert/update/delete patterns.
- Page splits and cleanup.
- PostgreSQL version and access method features.

Therefore, you cannot multiply row count by a constant and claim how large an index "should" be.

## 3. B-Tree Page Splits and Index Density

B-trees keep keys sorted. When inserting a key into a full leaf page, PostgreSQL splits the page into two and updates the tree structure.

Under random insert workloads:

- New keys land across many leaf pages.
- Page splits occur throughout the tree.
- Page density varies.
- The index can require more pages than a sequential build.

With sequential inserts on monotonically increasing keys, splits cluster near the right edge, though no single rule guarantees minimal index size across every workload.

DELETE/UPDATE operations also leave index entries dead or obsolete. VACUUM cleanup and B-tree page deletion recycle pages per the access method's rules; not every emptied page is immediately coalesced to shrink the file.

**Page splits, dead entries, and bloat are related, yet they are not one and the same concept.**

## 4. What Is Index Bloat?

Index bloat generally refers to physical space consumed by an index beyond what is warranted for the current dataset and workload, caused by low page density, dead space, page splits, or churn history.

Illustrative example:

~~~text
Index before churn:
  Leaf page A: [keys keys keys keys keys keys]
  Leaf page B: [keys keys keys keys keys keys]

After heavy UPDATE/DELETE/INSERT:
  Leaf page A: [keys -- -- keys -- --]
  Leaf page B: [-- keys -- -- keys --]

The index may now hold many sparse pages or dead space.
~~~

This is a conceptual diagram; B-trees feature cleanup, page deletion, reuse, and deduplication depending on version and access method.

### Bloat Is Not Synonymous with Dead Tuples

- Dead tuples are heap tuple versions no longer needed by MVCC snapshots.
- Dead index entries are index pointers no longer needed for live row versions.
- Free space is reusable room inside a page.
- Bloat is an assessment of excess space / inefficient page utilization in the context of the workload.

A huge index can be completely normal if the table has many rows or wide keys. Low leaf density may also be intentional if fillfactor was lowered to reduce page splits.

## 5. What Signals Warrant Investigating Index Bloat?

Helpful signals:

- Index size grows noticeably faster than row count or workload.
- Index queries read increasing numbers of buffers over time.
- Cache hit ratios drop because indexes consume excessive shared buffers/OS cache.
- Persistently low B-tree leaf density that does not match fillfactor or workload.
- Heavy churn while old snapshots blocked VACUUM cleanup.
- A single index accounts for most of the table's total storage.
- Rebuilding in a test environment makes the index substantially smaller and improves query I/O.

### Signals That Are Not Enough on Their Own

- A large index: the data itself may simply be large.
- Many index pages: may simply reflect many entries.
- Low `idx_scan`: the workload may be periodic, or the index may enforce a constraint.
- VACUUM just finished: standard VACUUM does not guarantee shrinking index files.
- Disk usage rose: could be heap, TOAST, WAL, temp files, or backups.
- Slow query: could be query plan, locks, CPU, network, or cache.

**Never run REINDEX solely because an index file looks big.**

## 6. Measuring Table and Index Sizes

Core functions:

| Function | Meaning |
| --- | --- |
| `pg_relation_size(relation)` | Size of the default fork (usually main fork) of the relation |
| `pg_table_size(relation)` | Table storage including TOAST and auxiliary forks, excluding indexes |
| `pg_indexes_size(relation)` | Total size of all indexes on the table |
| `pg_total_relation_size(relation)` | Combined table + TOAST + indexes |

Example checking one table's sizes:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('public.orders'::regclass))
        AS main_fork,
    pg_size_pretty(pg_table_size('public.orders'::regclass))
        AS table_storage,
    pg_size_pretty(pg_indexes_size('public.orders'::regclass))
        AS all_indexes,
    pg_size_pretty(pg_total_relation_size('public.orders'::regclass))
        AS total_storage;
~~~

These functions return bytes or human-readable strings. Never add `pg_table_size`, `pg_indexes_size`, and TOAST together—`pg_table_size` already includes table-associated TOAST storage.

### Inspecting Individual Indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(
        pg_relation_size(
            quote_ident(schemaname) || '.' || quote_ident(indexname)
        )
    ) AS index_size
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(
    quote_ident(schemaname) || '.' || quote_ident(indexname)
) DESC;
~~~

To handle schemas/names with special characters robustly, querying via catalogs and OIDs is usually cleaner than string concatenation. Example:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size,
    pg_relation_size(idx.oid) AS index_bytes
FROM pg_index AS i
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY index_bytes DESC;
~~~

This measures size, not bloat ratio.

## 7. Tracking Index Usage

`pg_stat_user_indexes` reports index usage statistics:

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;
~~~

Meaning:

- `idx_scan`: number of index scans initiated per statistics.
- `idx_tup_read`: number of index entries read.
- `idx_tup_fetch`: number of live table rows fetched by simple index scans.

These are cumulative counters since the last stats reset; they are not exact measures of bloat or complete proof of an index's total value.

### Does Low idx_scan Mean Drop It?

No. An index might:

- Enforce a `UNIQUE` or `PRIMARY KEY` constraint.
- Be queried on periodic batch schedules.
- Serve rare but business-critical queries.
- Be used occasionally by the planner.
- Support foreign key checks.

Before dropping an index, check dependencies, constraints, query logs, periodic jobs, and a sufficiently long observation window.

## 8. Using pgstattuple to Inspect Dead and Free Space

The `pgstattuple` extension provides physical metrics for tuples, dead tuples, and free space. It is an optional extension requiring installation privileges and can consume significant I/O scanning relations.

In a lab database:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
~~~

Inspect heap table stats:

~~~sql
SELECT *
FROM pgstattuple('public.orders'::regclass);
~~~

Key columns:

- `table_len`: total relation bytes.
- `tuple_count`: live tuples counted.
- `tuple_len` / `tuple_percent`: bytes/percentage of live tuple data.
- `dead_tuple_count`: dead tuples counted.
- `dead_tuple_len` / `dead_tuple_percent`: bytes/percentage of dead tuples.
- `free_space` / `free_percent`: free space.

### pgstattuple Is Not Free

The full function scans the entire relation and generates heavy I/O. On huge tables, pick timing and scope carefully. Approximate functions cut cost while returning estimates.

`pgstattuple` on a heap describes heap storage; to inspect a B-tree index, use the dedicated function `pgstatindex`.

## 9. Using pgstatindex for B-Trees

`pgstatindex` belongs to the `pgstattuple` extension and targets B-tree indexes.

~~~sql
SELECT *
FROM pgstatindex('public.idx_orders_customer_created'::regclass);
~~~

Useful fields:

- `version`: reported B-tree structure version.
- `tree_level`: depth of the tree.
- `index_size`: index size.
- `root_block_no`: root block number.
- `internal_pages`: count of internal pages.
- `leaf_pages`: count of leaf pages.
- `empty_pages`: count of empty pages.
- `deleted_pages`: count of deleted pages.
- `avg_leaf_density`: average leaf page fill density.
- `leaf_fragmentation`: leaf page fragmentation per function definition.

### Interpreting avg_leaf_density

Low density can indicate ample free space or sparse pages, yet you must account for fillfactor, data types, write patterns, and index purpose.

Examples:

- Fillfactor 70 may be set intentionally for random-insert workloads.
- A freshly built index reflects its configured fillfactor.
- An index growing via page splits naturally exhibits uneven density.
- Leaf fragmentation does not automatically prove queries are slow.

**Never enforce a single fixed density threshold as a universal REINDEX rule for all indexes.**

## 10. pgstattuple_approx and Measurement Cost

You can consider:

~~~sql
SELECT *
FROM pgstattuple_approx('public.orders'::regclass);
~~~

The approximate function leverages the visibility map to reduce scanning and estimate the remainder per extension/version semantics.

Options:

| Method | Advantages | Trade-Offs |
| --- | --- | --- |
| `pg_relation_size` | Very simple, negligible cost | Measures size only |
| `pgstattuple` | Detailed tuple/dead/free space metrics | May scan entire relation |
| `pgstattuple_approx` | Can reduce scan effort | Approximate / estimation error |
| `pgstatindex` | B-tree density/leaf metrics | I/O-heavy, B-tree only |
| Workload benchmark | Measures real impact | Needs representative environment and data |

Do not install extensions just for one number if production policy forbids it. You can measure on a replica or lab, remembering replicas differ in cache state and workload from the primary.

## 11. What Does REINDEX Do?

REINDEX rebuilds an index by reading the source data and constructing a fresh index structure per its current definition.

~~~text
Current index
  |
  | read required source data
  v
Build new index
  |
  | construct pages, entries, and metadata
  v
Swap old index for new index
  |
  v
PostgreSQL uses the new structure
~~~

Potential benefits:

- Eliminates index bloat.
- Recreates B-tree pages packed to the current fillfactor.
- Rebuilds an index after certain corruption issues if heap/source data is intact.
- Moves the index to another tablespace when invoked with the corresponding option.
- Refreshes structure after workload or index-maintenance changes.

REINDEX does not alter the SQL definition (columns, expressions, predicates, uniqueness) of the index. It rebuilds the physical structure from the catalog definition.

### REINDEX Does Not Fix Every Kind of Corruption

If heap data, storage devices, filesystems, or memory are corrupted, rebuilding the index may not resolve the underlying fault. If source data contains duplicates violating `UNIQUE`, rebuilding a unique index will fail. Investigate logs, storage, and integrity first.

## 12. Forms of REINDEX

Syntax examples:

~~~sql
-- Rebuild one index
REINDEX INDEX public.idx_orders_customer_created;

-- Rebuild all indexes on one table
REINDEX TABLE public.orders;

-- Rebuild indexes in one schema
REINDEX SCHEMA public;

-- Rebuild indexes in the current database
REINDEX DATABASE training_db;

-- Rebuild system catalog indexes of the current database
REINDEX SYSTEM training_db;
~~~

Broader forms carry sweeping impact. Syntax, privileges, and option support vary by PostgreSQL version; verify against documentation for your actual server.

### Choose the Narrowest Appropriate Scope

- Issue localized to one index: prefer `REINDEX INDEX`.
- Multiple indexes on one table affected: `REINDEX TABLE`.
- Wide schema/database maintenance: plan explicitly, never run casually.
- System catalog corruption: follow specialized recovery procedures, which may require single-user mode in some situations.

Never use `REINDEX DATABASE` as a "routine weekly cleanup" in place of index monitoring.

## 13. Standard REINDEX and Locking

Standard REINDEX can acquire an `ACCESS EXCLUSIVE` lock on the associated table. This lock blocks both normal reads and writes on the table for the duration of the rebuild.

Example:

~~~sql
REINDEX INDEX public.idx_orders_customer_created;
~~~

While it runs, applications can suffer:

- `SELECT`s forced to wait.
- `INSERT`/`UPDATE`/`DELETE` forced to wait.
- Connection pools filling with lock-waiting sessions.
- API latency spikes or timeouts.
- Other DDL blocked behind locks.

### When to Use Standard REINDEX?

- A maintenance window is available.
- The table is small and rebuild time is brief.
- Workloads can pause or enter maintenance mode.
- You want a simpler, fewer-phase execution.
- Sufficient disk/I/O exists and lock impact is acceptable.

Standard REINDEX can finish faster than concurrent mode because it does not have to preserve parallel access throughout the build. Still, downtime can cost far more than the time saved.

## 14. What Is REINDEX CONCURRENTLY?

`REINDEX CONCURRENTLY` is designed to rebuild an index while other sessions continue reading and writing the table for most of the process.

Example:

~~~sql
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

Unlike standard REINDEX, concurrent mode:

- Builds a replacement index.
- Executes multiple scan/validation phases.
- Waits for transactions that might still use the old index or affect validity.
- Swaps to the new index once ready.
- Drops the old index once safe.

Trade-offs:

- Takes longer overall.
- Consumes more I/O and CPU.
- Requires extra disk space for the new index while the old index still exists.
- Can wait on long-running transactions.
- Has extra restrictions on relation/index types and transaction context.

**CONCURRENTLY does not mean completely lock-free.** It avoids holding a long exclusive lock that blocks DML/SELECT, yet still takes brief locks across phases and can conflict with DDL or other concurrent maintenance.

## 15. Phases of REINDEX CONCURRENTLY

Conceptually, the process flows through:

~~~text
1. Register new index in invalid/not-ready state
       |
2. Wait for eligible existing transactions to finish
       |
3. Build new index by scanning data
       |
4. Wait for transactions that could affect consistency
       |
5. Perform additional validation scan
       |
6. Mark new index valid and swap dependencies
       |
7. Wait for old snapshots to no longer need the old index
       |
8. Drop old index
~~~

Exact phases and scan counts depend on PostgreSQL version. Key points to remember:

- Concurrent builds must ensure no concurrent writes are missed.
- For `UNIQUE` indexes, uniqueness must hold across concurrent writes.
- Waiting on transactions/snapshots can stall completion.
- The old index continues occupying disk space for much of the run.
- A concurrent command can fail or be canceled mid-phase.

## 16. Key Restrictions of REINDEX CONCURRENTLY

### Cannot Run Inside a Transaction Block

Concurrent reindex cannot execute inside an explicit transaction block.

Wrong:

~~~sql
BEGIN;
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
COMMIT;
~~~

Right: run standalone in an autocommit session:

~~~sql
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

This also impacts migration tools/frameworks that automatically wrap every migration in a transaction. Configure the migration explicitly to run outside a transaction where supported by your tool/version.

### Restrictions by Index/Relation Type

Concurrent reindex has restrictions regarding system catalogs, temporary tables, and certain partitioned index/relation setups. Supported target forms and restrictions have evolved across PostgreSQL major versions.

Before scripting bulk runs:

1. Read the `REINDEX` documentation page for your exact major version.
2. Verify whether target indexes belong to system catalogs or temporary relations.
3. Check parent/child partitioned indexes.
4. Check constraint-backing indexes and dependencies.
5. Test on staging with an equivalent schema.

Never assume `REINDEX DATABASE CONCURRENTLY` or concurrent reindexing across partitions behaves identically on all versions.

## 17. REINDEX TABLE CONCURRENTLY

On supported versions, you can run:

~~~sql
REINDEX TABLE CONCURRENTLY public.orders;
~~~

This rebuilds the table's indexes using concurrent semantics. Still verify version support, partitioned table rules, and index types.

If only one index has bloat, targeting that single index narrows impact and simplifies monitoring.

### Do Not Arbitrarily Run Multiple REINDEX CONCURRENTLY Jobs on the Same Table

PostgreSQL limits concurrent reindexing on the same relation and lock conflicts can arise. Running several concurrently can make them wait on each other, spike I/O, and lengthen maintenance.

Schedule sequentially, monitor workers, and confirm each index finishes cleanly.

## 18. Disk Headroom During Concurrent Reindex

During concurrent reindex, the old index must remain on disk while the new index is built. Temporary disk usage can climb substantially.

Example with an 80 GB existing index:

~~~text
Before:
  old index = 80 GB

During build:
  old index = 80 GB
  new index = estimated near rebuilt size
  + WAL/temp/other concurrent writes

After completion:
  old index is dropped
  new index remains
~~~

Do not budget only 80 GB of headroom. Account for:

- The new index possibly differing in size from the old one.
- WAL generated during the build and concurrent DML.
- Disk for temp files and parallel sort/index-build operations.
- Replication/WAL retention.
- Headroom for normal application growth.
- Filesystem or container volume limits.

Running out of disk mid-build fails the reindex and threatens far more than one index.

## 19. WAL and Replication Impact

REINDEX builds a new index structure, generating I/O and WAL per configuration and operation type. On primaries with physical standbys:

- WAL volume can surge.
- Replicas must replay the generated changes.
- Replication lag can climb.
- WAL retention/replication slots can grow primary disk usage.
- Standby query workloads may face I/O contention.

With logical replication, index DDL is not replayed like row changes the way physical replication works; manage schemas and indexes on subscribers separately.

Before reindexing large indexes, check WAL generation rates, replication lag, slot states, and archive/WAL filesystem capacity.

## 20. How Do REINDEX and VACUUM Differ?

| Criterion | VACUUM | REINDEX |
| --- | --- | --- |
| Primary target | Heap table and associated structures | Selected index(es) |
| Dead tuple handling | Yes, per visibility/cleanup rules | Rebuilds index from source data |
| Dead index entry handling | Cleans up via index vacuum passes | Creates fresh index structure |
| Shrinks index file aggressively | Not a general goal | Can shrink if index was bloated |
| Shrinks heap file | Not by default | No |
| Freezes XIDs | Yes | Not its purpose |
| Updates planner statistics | Does not replace ANALYZE | Does not replace ANALYZE |
| Locking | Per VACUUM lock mode | REINDEX mode has distinct lock behavior |

### Example

If `orders` has dead tuples from heavy UPDATE/DELETEs:

1. Find why autovacuum fell behind.
2. Clear any transaction horizon blockers.
3. Run VACUUM to reclaim eligible tuples.
4. Re-measure index size and density.
5. Run REINDEX only if evidence confirms substantial remaining index bloat or another valid need.

REINDEX does not replace VACUUM. If dead tuples remain or churn continues unabated, the rebuilt index will just absorb new churn.

## 21. REINDEX vs. VACUUM FULL

- `REINDEX`: rebuilds indexes.
- `VACUUM FULL`: rewrites/compacts the heap table and associated storage structures per command semantics.
- `CLUSTER`: rewrites the table in the order of one index.

If the heap table is bloated, REINDEX will not compact the heap. If only an index is bloated, `VACUUM FULL` on the whole table is overkill compared to targeted REINDEX.

| Goal | Tool Typically Considered |
| --- | --- |
| Dead tuples needing cleanup | `VACUUM` |
| Stale planner stats | `ANALYZE` |
| Index bloat | `REINDEX` or suitable tool |
| Heap/table bloat needing rewrite | `VACUUM FULL`, `CLUSTER`, or rewrite tool |
| Time-based retention | Partition detach/drop |
| Index corruption | Investigate and `REINDEX` when source data/storage are healthy |

Never pick a command just because it sounds like "cleanup". Pick by object and root cause.

## 22. REINDEX vs. CLUSTER

`CLUSTER` physically reorders the heap table according to a chosen index by rewriting the relation. It changes physical row locations and takes a strong lock.

`REINDEX` only rebuilds index structures; it does not reorder the heap by index order.

If improving range-scan locality along an index is your goal, `CLUSTER` is an option, though:

- Physical order is not automatically preserved by subsequent writes.
- Table rewrites consume heavy disk, I/O, and locks.
- Other indexes must be rebuilt per CLUSTER's workflow.
- Not every workload benefits.

## 23. Index Fillfactor

B-tree indexes support a `fillfactor` storage parameter. The typical default is 90, though verify documentation for your version and index access method.

Example:

~~~sql
ALTER INDEX public.idx_orders_customer_created
SET (fillfactor = 80);
~~~

This configures future builds/rebuilds; it does not immediately rearrange existing entries to make old pages sparser.

Rebuild:

~~~sql
REINDEX INDEX public.idx_orders_customer_created;
~~~

Or concurrently where appropriate:

~~~sql
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

### How to Choose Fillfactor?

- Lower fillfactor leaves extra room on new pages, potentially reducing page splits for random insert/update workloads.
- In exchange, the initial index is larger and its cache footprint increases.
- Read-heavy, rarely changing workloads often suit higher density.
- No single fillfactor is optimal for every index.

**Lower fillfactor does not cure bloat automatically.** It is a trade-off between page density and headroom for future writes.

## 24. Table Fillfactor vs. Index Fillfactor

Heap tables also have a `fillfactor` storage parameter, with different semantics from B-tree indexes.

Example:

~~~sql
ALTER TABLE public.orders
SET (fillfactor = 85);
~~~

Table fillfactor reserves heap page space to encourage HOT updates in certain workloads. Index fillfactor governs index page fullness during builds and inserts.

Never confuse the two settings or change both without measuring.

## 25. Can REINDEX Fix Index Corruption?

In some cases, an index structure is corrupted while the underlying heap/source rows remain intact. Rebuilding the index reconstructs a clean tree from source data.

Proceed cautiously:

1. Record the exact error and affected relation/index.
2. Check PostgreSQL and storage/OS logs.
3. Check whether the heap shows any signs of corruption.
4. Check constraints and dependencies.
5. Choose standard or concurrent REINDEX based on urgency and index type.
6. Verify the rebuilt index.
7. Continue investigating hardware/filesystems if corruption recurs.

### REINDEX Does Not Guarantee Clean Data

If heap pages are corrupt, data is bad, or duplicate keys violate uniqueness, rebuilding the index can fail or rebuild from incomplete/corrupt source rows. Never treat REINDEX as a disk-repair utility.

## 26. Verifying Indexes with amcheck

The `amcheck` extension provides structural index verification functions. For B-trees, `bt_index_check` and `bt_index_parent_check` are available per version privileges and options.

~~~sql
CREATE EXTENSION IF NOT EXISTS amcheck;

SELECT bt_index_check('public.idx_orders_customer_created'::regclass);
~~~

Thorough checks can verify parent/child relationships and require different locks and resources.

`amcheck` checks structural consistency; it does not measure bloat and does not replace backup/restore testing.

Do not run heavy checks endlessly across every production index; pick target indexes and schedules deliberately.

## 27. Handling Invalid Indexes After a Concurrent Failure

Concurrent reindex can fail or be canceled mid-phase. One scenario to recognize is a replacement index left in an invalid/not-ready state.

Inspect catalogs:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    i.indislive,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
   OR NOT i.indisready
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

General meanings:

- `indisvalid`: planner may treat the index as valid for query planning.
- `indisready`: index is ready to receive updates from writes per catalog state.
- `indislive`: index still exists as a live object in its lifecycle.

These states are internal metadata; consult version documentation when handling invalid indexes.

### How to Handle?

- Identify which index is the original, the replacement, or another invalid index.
- Inspect constraints and dependencies.
- Review error logs from the failed REINDEX.
- Either reindex again or drop the invalid replacement index per proper procedure.
- Never drop an index backing a `PRIMARY KEY`, `UNIQUE`, or `EXCLUSION` constraint without understanding dependencies.
- Verify query plans and constraint states after cleanup.

Never blindly run `DROP INDEX` in bulk based only on `indisvalid = false`.

## 28. Monitoring REINDEX Progress

PostgreSQL exposes progress reporting for `CREATE INDEX` and related operations per version. Query `pg_stat_progress_create_index`:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    lockers_total,
    lockers_done,
    current_locker_pid,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index
ORDER BY pid;
~~~

Exact columns and phases depend on PostgreSQL version and operation type. While REINDEX runs, this view helps observe build/scan phases and transactions being waited on.

### Progress Is Not an Exact ETA

`blocks_done / blocks_total` does not necessarily represent overall percentage of remaining wall-clock time. Waiting on transactions, validation, catalog swaps, or cleanup can take significant time while counters barely move.

## 29. Monitoring Locks and Waiting Sessions

Inspect sessions waiting on locks:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_start,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_stat_activity AS a
LEFT JOIN pg_locks AS l
    ON l.pid = a.pid
WHERE a.datname = current_database()
ORDER BY a.query_start;
~~~

During a maintenance window, watch:

- The REINDEX session.
- Waiting DML/SELECT sessions.
- Conflicting DDL operations.
- Long transactions holding snapshots.
- Rising connection pool queues.
- Lock wait durations.

Never cancel a session based solely on query age. Verify PID, query, application owner, and impact before terminating.

## 30. Planning Before REINDEX

Pre-flight checklist:

1. Verify exact database, schema, table, and index.
2. Record index definition, uniqueness, predicate, `INCLUDE` columns, and tablespace.
3. Measure current index size.
4. Confirm evidence of bloat or corruption.
5. Check whether the index backs a constraint.
6. Check PostgreSQL major version and `CONCURRENTLY` restrictions.
7. Calculate disk headroom for old index + new index + WAL/temp.
8. Check replication lag and WAL archive capacity.
9. Schedule a maintenance window if using standard REINDEX.
10. Set `lock_timeout`/`statement_timeout` per runbook if appropriate.
11. Check for long-running transactions.
12. Prepare monitoring for progress, locks, and errors.
13. Prepare actions if the command fails or is canceled.
14. Pick a low-traffic period and notify relevant owners.

### Confirm Index Definition Before Rebuilding

~~~sql
SELECT indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname = 'idx_orders_customer_created';
~~~

Record the definition for post-operation comparison. You do not need to manually drop and recreate an index when REINDEX already meets the goal.

## 31. Standard REINDEX Example in a Maintenance Window

Suppose a specific index has proven bloat and the application can tolerate locking:

~~~sql
-- Run outside a transaction block per maintenance plan.
REINDEX INDEX public.idx_orders_customer_created;
~~~

Operational sequence:

1. Check active sessions and locks.
2. Confirm the application is in its maintenance window.
3. Run the command.
4. Watch progress, disk, and logs.
5. Wait for completion.
6. Verify the index is valid and its definition unchanged.
7. Re-measure size and density.
8. Benchmark representative queries.
9. Close maintenance once application health is stable.

Never run this example on a real production index without confirming lock and downtime approval.

## 32. REINDEX CONCURRENTLY Example

When DML availability must be preserved:

~~~sql
-- Run standalone, outside BEGIN/COMMIT.
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

Workflow:

1. Confirm version support.
2. Confirm the index/relation type permits concurrent reindex.
3. Confirm disk headroom.
4. Check for long transactions that could stall waits.
5. Run in an autocommit session.
6. Monitor `pg_stat_progress_create_index`, `pg_stat_activity`, and logs.
7. Monitor WAL and replication lag.
8. Verify catalog index state after completion.
9. Re-measure size and query performance.

### Why Not Wrap It Inside a Migration Transaction?

Concurrent reindex orchestrates multiple internal transactions and phases. If a migration framework wraps DDL in a single transaction, PostgreSQL rejects the command. Configure the migration to run non-transactionally per your framework's support.

## 33. Lock Timeout and Statement Timeout

You can configure session-level timeouts ahead of the command to avoid waiting forever on locks or running unbounded per policy:

~~~sql
SET lock_timeout = '5s';
SET statement_timeout = '30min';

REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

Values are examples only. `lock_timeout` limits each individual lock acquisition attempt per PostgreSQL semantics; `statement_timeout` bounds statement duration. With multi-phase concurrent reindex, remember a timeout or cancellation can leave state requiring inspection.

`SET LOCAL` requires a transaction block, whereas concurrent reindex cannot run inside a transaction block. Thus this example uses session `SET`, and you should reset or close the session afterward.

## 34. REINDEX vs. Creating a New Index CONCURRENTLY

Two related techniques with distinct goals:

- `REINDEX INDEX CONCURRENTLY`: rebuilds the existing index using its current definition.
- `CREATE INDEX CONCURRENTLY`: builds a brand-new index with a new definition.

If you need to change key columns, predicates, expressions, or `INCLUDE` columns, REINDEX cannot do that; build a new index, verify usage/constraints, and migrate via a dedicated process.

Example creating a new index:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_customer_status
ON public.orders (customer_id, status);
~~~

This is a schema change, not a replacement for REINDEX purely to fix bloat. Avoid leaving duplicate overlapping indexes behind.

## 35. UNIQUE and PRIMARY KEY Indexes

REINDEX preserves `UNIQUE`/`PRIMARY KEY` definitions. During rebuild, PostgreSQL must verify data satisfies uniqueness.

If duplicate data exists due to prior corruption or an anomalous state, the rebuild will fail.

Never drop a constraint just to make REINDEX succeed. Instead:

- Check for duplicate business keys.
- Inspect catalog constraint/index dependencies.
- Determine the cause of corruption.
- Plan proper constraint restoration.
- Verify replica/schema consistency.

### Checking Associated Constraints

~~~sql
SELECT
    conname,
    contype,
    conrelid::regclass AS table_name,
    conindid::regclass AS supporting_index
FROM pg_constraint
WHERE conindid = 'public.idx_orders_customer_created'::regclass;
~~~

If this returns rows, the index backs a constraint. Account for that dependency in your plan.

## 36. REINDEX in Partitioned Systems

A partitioned table can have a parent partitioned index and child indexes on each partition.

~~~sql
SELECT
    parent_index.oid::regclass AS parent_index,
    child_index.oid::regclass AS child_index,
    child_table.oid::regclass AS child_table
FROM pg_inherits AS inh
JOIN pg_class AS parent_index
    ON parent_index.oid = inh.inhparent
JOIN pg_class AS child_index
    ON child_index.oid = inh.inhrelid
JOIN pg_index AS child_i
    ON child_i.indexrelid = child_index.oid
JOIN pg_class AS child_table
    ON child_table.oid = child_i.indrelid
WHERE parent_index.oid = 'public.idx_partitioned_orders'::regclass;
~~~

This query illustrates the catalog relationship; adjust for your actual schema and index names.

### Operations

- Identify parent and child indexes.
- Determine which specific partitions actually have bloat.
- Verify concurrent reindex support for your version.
- Where appropriate, process leaf indexes sequentially.
- Never overlook the validity state of the partitioned parent index.
- Check whether partition attach/detach operations are running.

Partitioned index concurrency restrictions vary by version. Always check docs for your exact server before automating.

## 37. Reindexing Across a Broad Schema or Database

`REINDEX SCHEMA`, `REINDEX DATABASE`, and `REINDEX SYSTEM` have wide scope. A database with thousands of indexes can generate prolonged maintenance load and high peak disk usage.

Never run something like:

~~~sql
REINDEX DATABASE training_db;
~~~

during peak traffic without knowing how many indexes it will rebuild and which relations it will lock.

Before broad reindexing:

- Inventory index counts and sizes.
- Narrow the scope deliberately.
- Evaluate lock impacts.
- Check tablespace/disk capacities.
- Order by priority.
- Monitor replication and workloads.
- Allow pausing/resuming per relation where tools and operations permit.

## 38. Reindexing System Catalogs

System catalogs hold critical PostgreSQL metadata. Reindexing catalog indexes may be necessary in specific corruption scenarios.

Never treat `REINDEX SYSTEM` as routine maintenance. If corruption prevents normal server operation, procedures may require single-user mode or version-specific recovery steps.

- Confirm valid backups exist.
- Identify the specific corrupt catalog and index.
- Consult PostgreSQL documentation on catalog reindexing.
- Never manually drop catalog indexes.
- Follow DBA incident procedures with proper privileges.

## 39. REINDEX and Tablespaces

If you want to place a rebuilt index in a different tablespace, PostgreSQL supports a `TABLESPACE` option per matching syntax/version.

Option syntax example:

~~~sql
REINDEX (TABLESPACE fast_index_space)
INDEX public.idx_orders_customer_created;
~~~

This helps relocate indexes to another storage tier, provided:

- The tablespace exists and is accessible.
- Sufficient space exists on both source and destination.
- Privileges are verified.
- Replication and backup impacts are assessed.
- Post-rebuild verification confirms the index resides in the target tablespace.

Do not confuse an index's tablespace with the heap table's tablespace.

## 40. Is ANALYZE Needed After REINDEX?

REINDEX rebuilds an index; it does not analyze the table and does not alter planner statistics.

In many cases, REINDEX does not require ANALYZE purely because an index was rebuilt. However, if workload, schema, or data distribution also recently changed, statistics may need refreshing separately.

~~~sql
ANALYZE public.orders;
~~~

Run it only when planner statistics warrant refreshing. Do not lump all maintenance commands together without clear purpose for each.

## 41. What to Verify After REINDEX?

### 1. Index State

~~~sql
SELECT
    i.indisvalid,
    i.indisready,
    i.indislive,
    idx.oid::regclass AS index_name
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
WHERE idx.oid = 'public.idx_orders_customer_created'::regclass;
~~~

### 2. Size

~~~sql
SELECT
    pg_size_pretty(pg_relation_size(
        'public.idx_orders_customer_created'::regclass
    )) AS index_size;
~~~

### 3. Index Definition

~~~sql
SELECT indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname = 'idx_orders_customer_created';
~~~

### 4. Query Plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 42
ORDER BY created_at
LIMIT 100;
~~~

### 5. Workload Impact

- Query p50/p95/p99 latency.
- Buffer reads and hits.
- CPU and I/O.
- Lock waits.
- WAL and replication lag.
- Index size.
- Disk headroom.

A smaller index does not automatically guarantee faster queries. The planner might pick a different plan or the bottleneck might live elsewhere.

## 42. Why Can an Index Grow Back After REINDEX?

After rebuilding, workloads keep writing:

- INSERTs add new entries.
- UPDATEs modify indexed columns.
- DELETEs leave entries needing cleanup.
- B-tree page splits continue happening.
- Fillfactor and key distribution govern page density.

If the root cause is write churn or schema/index design, the index will grow again. REINDEX is a point-in-time maintenance fix, not a cure for workload design.

## 43. Should You Run REINDEX on a Fixed Schedule?

There is no universal schedule like "REINDEX the whole database every week" that fits every system.

Blindly scheduling REINDEX can cause:

- Needless I/O spikes.
- Heavy WAL and replication load.
- Disk usage peaks.
- Lock contention if using standard mode.
- Cache churn.
- Rebuilding indexes that were completely healthy.

Instead:

1. Collect size and workload metrics.
2. Measure bloat on suspected indexes.
3. Track trends over time.
4. Identify dead-tuple/page-split root causes.
5. Target only indexes with clear expected benefit.
6. Reindex under control.
7. Compare before and after.

## 44. When Should You NOT Run REINDEX?

Do not start a reindex when:

- You only have one large size number without a baseline.
- Disk is nearly full without room for the replacement index.
- Replica or WAL storage is already in distress.
- Long-running transactions would stall concurrent operations indefinitely.
- Workloads are at peak and cannot absorb extra I/O.
- Index definitions and dependencies have not been recorded.
- Corruption may reside in the heap or storage rather than the index.
- Unique data shows signs of constraint violations.
- PostgreSQL version and restrictions have not been checked.
- Conflicting DDL or partition maintenance is active.

If queries are slow due to missing or poorly designed indexes, REINDEX merely rebuilds the same old index; fix the query and index design instead.

## 45. Common Mistakes

1. **Using REINDEX to fix table bloat**, when REINDEX only rebuilds indexes.
2. **Confusing standard VACUUM with REINDEX**, despite their different purposes.
3. **Running standard REINDEX during peak hours**, blocking SELECT/DML via strong locks.
4. **Assuming CONCURRENTLY takes zero locks**, ignoring lock waits and DDL conflicts.
5. **Running REINDEX CONCURRENTLY inside BEGIN/COMMIT**, causing PostgreSQL to reject it.
6. **Failing to check version**, using unsupported options or target forms.
7. **Reindexing an entire database without an inventory**, causing huge I/O and lock impact.
8. **Ignoring disk headroom**, filling the filesystem mid-operation.
9. **Ignoring WAL and replica lag.**
10. **Running many parallel reindexes**, escalating storage contention.
11. **Treating a large index size as bloat**, ignoring row count and key width.
12. **Treating low `avg_leaf_density` as always bad**, overlooking intentional fillfactor.
13. **Running `pgstattuple`/`pgstatindex` across every production table simultaneously**, triggering heavy scan I/O.
14. **Failing to separate heap bloat, index bloat, and TOAST size.**
15. **Expecting VACUUM to always shrink index files back to the filesystem.**
16. **Dropping an invalid index without checking constraint dependencies.**
17. **Leaving invalid replacement indexes behind after a concurrent failure.**
18. **Assuming REINDEX repairs heap corruption or disk corruption.**
19. **Failing to verify `UNIQUE`/`PRIMARY KEY` after rebuilding.**
20. **Failing to compare query plans and latency before and after.**
21. **Setting a low fillfactor without accounting for larger index size.**
22. **Using `CREATE INDEX CONCURRENTLY` to change a definition and forgetting to drop the old index.**
23. **Running scheduled REINDEX with zero evidence of bloat.**
24. **Failing to check partitioned parent/child index states.**
25. **Failing to inspect logs and progress after a timeout or cancellation.**

## 46. Practice Exercises with Answers

Examples assume a `public.orders` schema exists. Run DDL/maintenance commands only in a lab database or under an approved maintenance plan.

### Exercise 1. What does REINDEX do?

**Answer:** Rebuilds an index structure from source data according to its current index definition.

### Exercise 2. Does REINDEX compact the heap table?

**Answer:** No. It rebuilds indexes; heap bloat requires VACUUM or a dedicated table-rewriting strategy.

### Exercise 3. Write a command to reindex one index

~~~sql
REINDEX INDEX public.idx_orders_customer_created;
~~~

**Answer:** Rebuilds the exact specified index.

### Exercise 4. What does REINDEX TABLE do?

**Answer:** Rebuilds the indexes of the specified table per PostgreSQL version semantics.

### Exercise 5. Why does standard REINDEX cause downtime?

**Answer:** It takes a strong lock on the associated table, blocking reads and writes for the duration of the rebuild.

### Exercise 6. Write REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY public.idx_orders_customer_created;
~~~

**Answer:** Rebuilds the index across phases so DML can continue for most of the operation.

### Exercise 7. Can concurrent reindex run inside BEGIN/COMMIT?

**Answer:** No. It cannot run inside a transaction block.

### Exercise 8. Does CONCURRENTLY mean zero locks?

**Answer:** No. Brief locks are still acquired across phases, and it can wait on transactions or DDL.

### Exercise 9. Why does concurrent reindex need extra disk space?

**Answer:** The old index remains while the replacement index is built; space is needed for both plus related overhead.

### Exercise 10. How do REINDEX and VACUUM differ?

**Answer:** VACUUM handles dead tuples, visibility, and freezing; REINDEX rebuilds index structures.

### Exercise 11. How does VACUUM FULL differ from REINDEX?

**Answer:** `VACUUM FULL` rewrites/compacts the heap relation; `REINDEX` rebuilds only selected indexes.

### Exercise 12. What does `pg_relation_size` measure?

**Answer:** The size of the default fork, typically the main fork, of a relation.

### Exercise 13. What does `pg_indexes_size` measure?

**Answer:** Total size of all indexes belonging to a table.

### Exercise 14. What does `pg_total_relation_size` measure?

**Answer:** Combined table storage, TOAST, and associated indexes.

### Exercise 15. Which index type is `pgstatindex` used for?

**Answer:** B-tree indexes via the `pgstattuple` extension.

### Exercise 16. Is low `avg_leaf_density` always bloat?

**Answer:** No. Account for fillfactor, write patterns, page splits, and design intent.

### Exercise 17. Can `pgstattuple` be expensive?

**Answer:** Yes. Full relation scans generate heavy I/O; schedule carefully and use approximate checks when suitable.

### Exercise 18. Does low `idx_scan` mean an index should be dropped?

**Answer:** No. The index may enforce a constraint or serve rare yet vital workloads.

### Exercise 19. Does REINDEX change an index definition?

**Answer:** No. It rebuilds using the existing definition; changing columns or predicates requires creating a new index.

### Exercise 20. What is the benefit of a lower fillfactor?

**Answer:** Leaves free space on new pages, reducing page splits for write workloads at the cost of a larger index.

### Exercise 21. Does `ALTER INDEX SET fillfactor` rebuild immediately?

**Answer:** No. It applies to future builds and inserts; applying it across the existing structure requires a rebuild.

### Exercise 22. Why do long-running transactions affect cleanup?

**Answer:** Old snapshots retain needed tuple versions; VACUUM and index cleanup cannot remove entries still required.

### Exercise 23. Where do you check for invalid indexes after a concurrent failure?

**Answer:** The `pg_index` catalog using `indisvalid`, `indisready`, and `indislive`.

### Exercise 24. Can you drop every index with `indisvalid=false`?

**Answer:** No. Inspect dependencies and constraints and identify old vs. replacement indexes before cleaning up.

### Exercise 25. What is `pg_stat_progress_create_index` used for?

**Answer:** Tracking phases and progress of `CREATE INDEX` and related operations such as concurrent reindex depending on version.

### Exercise 26. Does REINDEX replace ANALYZE?

**Answer:** No. ANALYZE updates planner statistics.

### Exercise 27. When should you choose standard REINDEX?

**Answer:** When a maintenance window is available and a strong lock is acceptable for a simpler rebuild.

### Exercise 28. When should you consider `REINDEX CONCURRENTLY`?

**Answer:** When DML/reads must remain available for most of the run, sufficient disk/I/O exists, and the index/relation is supported.

### Exercise 29. What does a B-tree page split do?

**Answer:** Splits a leaf page when no room remains for a new entry, affecting page count and density.

### Exercise 30. If the index shrank after REINDEX yet queries remain slow, what should you check?

**Answer:** Query plans, buffers, heap/TOAST, statistics, locks, I/O, CPU, network, and index definition; smaller size alone does not guarantee lower latency.

## 47. REINDEX Deployment Checklist

- [ ] Confirmed whether the target issue is heap, TOAST, or index.
- [ ] Identified exact target index and recorded its definition.
- [ ] Measured size prior to action.
- [ ] Used `pgstatindex`/`pgstattuple` where justified and permitted.
- [ ] Distinguished bloat from normal fillfactor/workload behavior.
- [ ] Checked constraints and dependencies.
- [ ] Verified PostgreSQL major version and concurrent restrictions.
- [ ] Chose standard REINDEX or CONCURRENTLY based on downtime budget.
- [ ] Ensured concurrent reindex does not run inside a transaction block.
- [ ] Sized disk headroom for old index + new index + WAL/temp.
- [ ] Checked long-running transactions and lock waits.
- [ ] Monitored `pg_stat_progress_create_index`.
- [ ] Monitored CPU, I/O, WAL, and replication lag.
- [ ] Avoided running bulk parallel reindexes recklessly.
- [ ] Checked for invalid indexes after any failure or cancellation.
- [ ] Never dropped a constraint-backed index without handling dependencies.
- [ ] Verified `indisvalid`/`indisready`/`indislive`.
- [ ] Measured size and density after rebuilding.
- [ ] Compared query plans and latency before and after.
- [ ] Addressed heap bloat separately with proper VACUUM/rewrite strategies if applicable.
- [ ] Recorded rationale, outcomes, and rebuild timestamp.
- [ ] Avoided scheduled blind REINDEX without bloat evidence.

## 48. Official PostgreSQL Documentation

Consult documentation matching your running major version:

- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html) — syntax, locks, `CONCURRENTLY`, restrictions, and target forms.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dead tuples, VACUUM, and maintenance.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — VACUUM, FULL, and options.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — index building, `CONCURRENTLY`, and fillfactor.
- [Index Access Methods](https://www.postgresql.org/docs/current/indexes-types.html) — index types.
- [B-tree Indexes](https://www.postgresql.org/docs/current/btree.html) — B-tree behavior.
- [Index Storage Parameters](https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-STORAGE-PARAMETERS) — fillfactor and storage options.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_user_indexes`, `pg_stat_activity`.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html) — `pg_stat_progress_create_index`.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html) — tuple/free-space inspection extension.
- [amcheck](https://www.postgresql.org/docs/current/amcheck.html) — index consistency checks.
- [System Catalog pg_index](https://www.postgresql.org/docs/current/catalog-pg-index.html) — `indisvalid`, `indisready`, and index metadata.
- [System Catalog pg_constraint](https://www.postgresql.org/docs/current/catalog-pg-constraint.html) — index/constraint dependencies.
- [Lock Monitoring](https://www.postgresql.org/docs/current/monitoring-locks.html) — lock views and diagnostics.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html) — index placement and storage.
- [Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — parent/child indexes and partition maintenance.

URLs with `/current/` point to current PostgreSQL docs. `REINDEX CONCURRENTLY`, partitioned indexes, progress columns, and specific options vary by major version; verify on your actual server before running in production.

## 49. Summary

**REINDEX rebuilds index structures. `REINDEX CONCURRENTLY` minimizes blocking of reads and writes through a multi-phase build, at the cost of extra resources and brief wait/lock points.**

Key points to remember:

1. **Measure before rebuilding.** Large size alone does not prove bloat; combine sizes, B-tree density, workloads, and query plans.
2. **Distinguish heap bloat from index bloat.** REINDEX does not compact heap tables or TOAST.
3. **VACUUM and REINDEX complement each other.** VACUUM cleans dead tuples, updates visibility, and freezes; REINDEX builds a fresh index structure.
4. **Standard REINDEX takes strong locks**, blocking SELECT and DML; reserve it for suitable maintenance windows.
5. **`REINDEX CONCURRENTLY` keeps workloads running most of the time**, yet uses multiple phases, can wait on transactions, and requires extra disk and WAL.
6. **Never run `REINDEX CONCURRENTLY` inside a transaction block.** Migration tools must run it non-transactionally.
7. **Size disk headroom and replication impact** before rebuilding large indexes.
8. **Fillfactor is a trade-off** between page density and headroom for write workloads; changing it does not rebuild existing pages automatically.
9. **Inspect invalid indexes and dependencies** if a concurrent reindex fails or is canceled.
10. **REINDEX does not replace ANALYZE, fix all corruption, or substitute for proper index design.**
11. **Never reindex on a rigid schedule** without evidence of benefit.
12. **Verify afterward** using catalog states, sizes, query plans, latency, and replica health.

By targeting the exact index needing maintenance, picking the right lock mode, and measuring before and after, you can resolve index bloat while keeping PostgreSQL production risks under control.
