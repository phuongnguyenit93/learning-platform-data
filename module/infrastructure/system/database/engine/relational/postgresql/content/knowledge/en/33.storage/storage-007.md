# Table and Index Bloat in PostgreSQL

A PostgreSQL table with 2 million active rows can occupy a file on disk many times larger than expected. An index that started small now consumes tens of gigabytes. Queries still return accurate results, yet cache hit rates drop, backups take longer, I/O climbs, and scans must read far more pages. These symptoms often point to **bloat** in tables or indexes.

In PostgreSQL, bloat is not simply "a file containing wasted empty bytes." It arises from how **MVCC** retains multiple row versions, how VACUUM cleans up unneeded versions, and how heap/index pages hold free space for reuse. To handle it properly, first distinguish:

- Dead tuples that still exist because an old transaction/snapshot prevents cleanup;
- Dead tuples eligible for cleanup awaiting VACUUM;
- Reusable free space inside the relation;
- Unproductive heap/index pages needing a rewrite/rebuild to shrink the file;
- Legitimate growth from real live data, TOAST, indexes, or intentional fillfactor.

**Regular VACUUM enables space reuse inside a relation; it does not by default shrink files back to the OS.** `VACUUM FULL`, `CLUSTER`, `pg_repack`, or `REINDEX` can rewrite/rebuild relations/indexes to reclaim disk space, yet each carries distinct costs, temporary disk requirements, and locking impact.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what table and index bloat are and why bloat cannot be inferred solely from file size.
2. Describe how MVCC creates row versions on UPDATE/DELETE.
3. Distinguish live tuples, dead tuples, free space, page fragmentation, and bloat.
4. Explain the roles of regular VACUUM, VACUUM FULL, ANALYZE, CLUSTER, REINDEX, and pg_repack.
5. Understand why regular VACUUM does not necessarily shrink relation files.
6. Identify old transactions/snapshots pinning dead tuples.
7. Separate table bloat, index bloat, and TOAST storage.
8. Explain HOT updates, fillfactor, and their effect on index churn.
9. Read statistics from `pg_stat_user_tables`, `pg_stat_user_indexes`, `pg_class`, and `pg_stat_progress_vacuum`.
10. Use `pgstattuple`, `pgstattuple_approx`, and `pgstatindex` when extensions are available.
11. Understand the limitations of bloat estimation formulas and statistical metrics.
12. Tune autovacuum according to table scale and data churn rate.
13. Monitor vacuum freeze and transaction ID wraparound risk.
14. Choose remediation matching bloat severity, lock budget, disk headroom, and SLAs.
15. Build a before/after measurement workflow for vacuuming or rebuilding.

## 2. What Is Bloat?

**Bloat** describes relation space (table, index, or TOAST relation) exceeding what is needed to hold useful data given its current state and storage design. Excess space may stem from:

- Unreclaimed old row versions (dead tuples);
- In-page free space left behind after tuple deletions;
- Sparse heap/index pages caused by updates, deletes, fragmentation, or page splits;
- Fillfactor intentionally reserving free space;
- Large TOAST data or necessary indexes overlooked by the observer;
- Sparse pages remaining in the relation file that hurt scan efficiency.

### 2.1. Visual Example

Suppose a table stores 100,000 orders. Over several years, many orders are deleted or modified. File size can remain near its peak pre-deletion size:

~~~text
Before changes:
+--------------------------------------------------+
| live row | live row | live row | live row | ...  |
+--------------------------------------------------+

After many UPDATEs/DELETEs:
+--------------------------------------------------+
| live row | dead row | free space | live row | ...|
+--------------------------------------------------+

After regular VACUUM:
+--------------------------------------------------+
| live row | reusable space | live row | free ... |
+--------------------------------------------------+

After rewrite/rebuild:
+---------------------------------------+
| live row | live row | live row | ...  |
+---------------------------------------+
~~~

This diagram illustrates the concept only. An actual heap page contains a page header, line pointers, tuple data, alignment, and optional free space; index pages have their own layouts.

### 2.2. Bloat Does Not Mean All Free Space Is Bad

Free space on pages can be genuinely useful:

- UPDATEs can place new row versions on the same page;
- HOT updates can avoid creating new index entries;
- Subsequent INSERTs can reuse available space;
- Reserve space on index pages helps reduce page splits.

Therefore, **not every free byte needs reclaiming**. Forcing every page to 100% fullness can force subsequent UPDATEs/INSERTs into extra I/O and generate new bloat faster.

### 2.3. Relation Size Alone Does Not Tell Efficiency

A 10 GB table may be completely healthy if packed with live data. A 2 GB table may be heavily bloated if only a fraction holds live rows. Examine:

- Live/dead tuple counts;
- Free space ratio and page distribution;
- Heap, index, and TOAST sizes;
- Query workload and scan patterns;
- Growth trends over time rather than a single snapshot.

### 2.4. Distinguish Bloat from Legitimate Growth

If a table adds a large JSONB document column, a new GIN index, or real new rows, growth is expected. **Do not label every disk increase as bloat.**

## 3. How MVCC Creates Row Versions

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)**. UPDATE normally does not overwrite the old row's bytes in place like editing a text file; it creates a new version so concurrent transactions continue seeing consistent snapshots.

### 3.1. INSERT

An INSERT creates a new tuple stamped with transaction metadata indicating which transaction created it. Once committed, the tuple becomes visible to qualifying snapshots.

### 3.2. UPDATE

Example:

~~~sql
UPDATE orders
SET status = 'paid'
WHERE order_id = 1001;
~~~

Under MVCC, PostgreSQL generally:

1. Marks the old version invalid for newer snapshots;
2. Writes a new tuple version containing `status='paid'`;
3. Retains the old version until no active snapshot can possibly need it;
4. Lets VACUUM reclaim the old version later.

An UPDATE creates dead tuples even when logical row count never changes.

### 3.3. DELETE

~~~sql
DELETE FROM orders
WHERE order_id = 1001;
~~~

DELETE marks the tuple deleted for future visibility. The tuple does not disappear from the file immediately; VACUUM cleans it up once no transaction/snapshot still needs to see that version.

### 3.4. A Dead Tuple Is Not an Active Row

A **dead tuple** is a row version no longer visible to any current snapshot and eligible for reclamation once the transaction horizon allows. Until then, old versions must stay intact for older snapshots reading past state.

### 3.5. Why Does PostgreSQL Not Delete Immediately?

A transaction started before the UPDATE may still need to read the old value. Deleting the old version prematurely would corrupt snapshot consistency.

~~~text
Transaction A: BEGIN -------------------- SELECT ...
                    |
Transaction B:       UPDATE row; COMMIT
                    |
VACUUM:              cannot remove old tuple while A still needs old snapshot
                    |
Transaction A: COMMIT
                    |
Later VACUUM:        can clean up old tuple
~~~

### 3.6. HOT Updates

Under suitable conditions, PostgreSQL performs a **Heap-Only Tuple (HOT) update**: the new version stays on the same heap page and avoids creating new index entries in unaffected indexes. HOT cuts index churn and cleanup cost.

HOT typically requires:

- UPDATE does not modify columns used by indexes (including expression/predicate dependencies);
- Enough room exists on the same heap page for the new tuple;
- Other index/implementation-specific HOT conditions are satisfied.

### 3.7. Not Every UPDATE Adds New Index Entries

When HOT succeeds, existing index entries lead to the HOT chain so PostgreSQL locates the right heap version. When HOT cannot be used, indexes receive new entries for the new version, driving index churn.

## 4. Three Space Categories to Distinguish

### 4.1. Heap/Table Bloat

Heap bloat concerns table pages holding:

- Live tuples;
- Dead tuples;
- Line pointers;
- Free space;
- Page metadata.

Dead tuples and sparse pages force heap scans to read more pages than needed.

### 4.2. Index Bloat

Index bloat is index storage growing beyond useful need due to churn, page splits, deleted entries/pages, and sparse distribution. B-tree indexes have internal/leaf pages; other access methods (GIN, GiST, BRIN, hash) have distinct structures and behaviors.

**Never apply a single B-tree formula to claim every index type bloats identically.**

### 4.3. TOAST Bloat

PostgreSQL stores oversized values (text, bytea, JSONB, etc.) out-of-line in a TOAST relation. Updating or deleting oversized values creates dead tuples and free space inside the TOAST table and its index.

Measuring only the main heap table misses most of the footprint of tables holding large JSON/documents. Use `pg_total_relation_size()` and inspect associated TOAST relations.

### 4.4. Page Fragmentation

Page fragmentation describes data scattered sparsely or non-contiguously in ways that inflate page reads/sequential scans or lower index density. A relation with free space may still reuse it efficiently for its workload; thus fragmentation and bloat are related yet not strictly identical.

### 4.5. Free Space Map (FSM)

The FSM tracks approximate free space within a relation so PostgreSQL finds suitable pages for writes. The FSM aids space reuse; it does not store business rows and does not return free bytes to the OS.

### 4.6. Visibility Map (VM)

The Visibility Map tracks heap pages where all tuples are visible to all current transactions, as well as all-frozen status. It enables:

- VACUUM to skip scanning clean pages unnecessarily;
- Index-only scans to skip heap fetches when visibility permits.

Dead tuples, updates, or transaction horizons clear all-visible status. VACUUM updates the VM during cleanup.

### 4.7. Comparison Table

| Concept | Reusable? | Shrinks File Automatically? |
| --- | --- | --- |
| Cleaned dead tuple | Space reused inside the relation | Usually no |
| Free space on heap page | Usable for new tuples | No |
| Empty/trailing pages | Can be truncated during some vacuum runs | Can shrink file if trailing and eligible |
| Index deleted/free pages | Reusable by the index depending on structure | Usually no |
| Bloat requiring rewrite | After rewrite, relation/index is rebuilt compactly | Yes, depending on method |

## 5. Common Causes of Bloat

### 5.1. High-Frequency UPDATE/DELETE

Status tables, event queues, session tables, or counter tables receiving continuous UPDATEs generate massive dead tuple churn. If vacuum falls behind, dead tuples and relation size climb.

### 5.2. Updating Indexed Columns

If an UPDATE modifies an indexed column, HOT cannot apply for that index; PostgreSQL must maintain index entries for the new version. Workloads repeatedly updating indexed columns drive heavy index churn.

### 5.3. B-Tree Page Splits

When a B-tree leaf page lacks room for a new insert, PostgreSQL splits the page. Splits are normal B-tree behavior, yet random insert/update patterns, wide keys, or high density can inflate index page counts and fragmentation.

### 5.4. Autovacuum Falling Behind

Possible causes:

- Scale factor too high for very large tables;
- Poorly tuned thresholds;
- Too few or busy autovacuum workers;
- Cost delay/limit throttling vacuum speed;
- Long-running transactions or replication horizons pinning dead tuples;
- Write rate outpacing vacuum capacity;
- Autovacuum disabled at the table or database level;
- I/O, CPU, or lock contention.

### 5.5. Long-Running Transactions and Idle in Transaction

A session holding an open transaction—even `idle in transaction`—retains an old snapshot and blocks VACUUM from reclaiming certain tuples. Even a tiny SELECT left inside an open transaction pins the xmin horizon.

### 5.6. Replication Slots and Standby Feedback

Replication slots retain WAL and can pin xmin/catalog_xmin so subscribers/consumers can keep reading required state. `hot_standby_feedback` from standbys can also pin horizons, causing the primary to accumulate dead tuples/bloat.

### 5.7. Mismatched Fillfactor and Workload

Too high a fillfactor leaves no room for HOT updates. Too low a fillfactor creates excess free space and bloats the relation from the start. Choose based on UPDATE/INSERT ratios and row size.

### 5.8. Bulk DELETE Without Rewrite

Deleting 90% of rows does not shrink the table file by 90% upon commit. Regular VACUUM makes page space reusable; shrinking the file significantly requires an appropriate relation rewrite.

### 5.9. Bulk Imports, Batch Churn, and Retried Jobs

Import/ETL jobs performing repeated UPDATEs/DELETEs, mass upserts, or delete-and-reload cycles cause massive table/index churn. Idempotency and better batch design cut redundant writes.

### 5.10. Unnecessary Indexes

Every index adds disk space, WAL, INSERT/UPDATE/DELETE cost, and vacuum work. Redundant or unused indexes expand storage with no matching benefit.

### 5.11. What Is Not Bloat

- Genuine live row growth;
- JSONB/text/bytea columns holding large payloads;
- New indexes required by query workloads;
- Intentionally lowered fillfactor;
- An audit/event table growing per retention policy;
- An index with naturally lower page density due to its workload and access method.

Evaluate bloat alongside workload and business data, never from a single ratio alone.

## 6. What Does Regular VACUUM Do?

`VACUUM` is the routine maintenance mechanism that reclaims unneeded dead tuples and keeps relations healthy under MVCC. It is not a command to "compress every table into the smallest possible file."

### 6.1. Cleaning Dead Tuples

When the transaction horizon allows, VACUUM:

1. Identifies tuple versions no longer needed;
2. Cleans corresponding index references during index cleanup;
3. Marks heap space reusable;
4. Updates free space and visibility metadata;
5. Performs freezing work needed to prevent transaction ID wraparound per vacuum policy.

### 6.2. Regular VACUUM Does Not Rewrite the Whole Table

~~~sql
VACUUM copy411.contacts;
~~~

Regular VACUUM cleans and marks space for internal reuse within the relation. It does not copy all live rows into a new relation, making it far less disruptive than VACUUM FULL.

### 6.3. VACUUM Can Truncate Trailing Empty Pages

In some situations, regular VACUUM can truncate empty pages at the **end of the relation**, partially shrinking the file. However:

- Only qualifying trailing pages are truncated;
- Free space in the middle of the file remains allocated for reuse;
- Truncating the tail may require a strong lock briefly;
- VACUUM's `TRUNCATE` option controls this behavior depending on version.

Therefore, never promise that running regular VACUUM returns all bloat to the filesystem.

### 6.4. VACUUM ANALYZE

~~~sql
VACUUM (ANALYZE) public.orders;
~~~

VACUUM cleans tuples; ANALYZE gathers planner statistics (value distributions, selectivity, histograms/most-common values, etc.). The two complement each other:

- VACUUM handles storage cleanup/MVCC;
- ANALYZE helps the planner choose execution plans.

ANALYZE **does not** clean dead tuples or shrink files.

### 6.5. VACUUM VERBOSE

~~~sql
VACUUM (VERBOSE, ANALYZE) public.orders;
~~~

`VERBOSE` prints details on pages/tuples and vacuum work. Output format depends on version and table state. It is a useful diagnostic signal, not a complete bloat measurement.

### 6.6. VACUUM Cannot Run Inside a Transaction Block

~~~sql
-- Do not place VACUUM inside:
BEGIN;
VACUUM public.orders;
COMMIT;
~~~

Regular VACUUM cannot run inside an explicit transaction block. Some migration tools wrap statements in transactions automatically; configure the tool appropriately when running vacuum.

### 6.7. VACUUM and Locks

Regular VACUUM uses locks that let most normal reads and writes continue, yet still interacts with workloads and can be blocked by certain DDL or conflicting locks. VACUUM is not "zero-lock." Monitor progress, lock waits, I/O, and workload on large tables.

### 6.8. VACUUM Does Not Immediately Fix All Index Bloat

VACUUM cleans indexes according to index type and conditions. For B-trees, index pages become reusable while the index file does not necessarily shrink. When rebuilding an index to reclaim sparse pages, look to REINDEX.

### 6.9. INDEX_CLEANUP

VACUUM provides an `INDEX_CLEANUP` option (depending on version) controlling index entry cleanup. AUTO decides based on dead tuple levels; OFF can speed up emergency runs while leaving index cleanup debt. **Never routinely disable index cleanup just to make vacuum faster** without assessing the consequences.

## 7. VACUUM FULL: Rewriting the Relation to Shrink the File

`VACUUM FULL` rebuilds the table contents, eliminating most free space/bloat and shrinking the relation where possible.

~~~sql
VACUUM (FULL, ANALYZE) public.orders;
~~~

### 7.1. Conceptual Behavior

Instead of merely marking page space reusable, VACUUM FULL **rewrites the relation** into a more compact physical copy and swaps it in according to PostgreSQL's procedure.

### 7.2. Advantages

- Can reclaim substantial heap table disk space;
- Rebuilds a compact relation layout;
- Can improve scan locality if the table was severely fragmented;
- Reduces pages read when bloat was genuinely severe.

### 7.3. Critical Disadvantages

- Requires an **ACCESS EXCLUSIVE lock** on the table for the duration;
- Queries and other operations on the table must wait;
- Needs enough temporary disk space for the rewritten copy and related structures;
- Consumes heavy I/O/CPU, generates WAL, and impacts replication/backups;
- Unsuitable to run casually on large production tables serving critical workloads.

### 7.4. VACUUM FULL Is Not Used by Autovacuum

Autovacuum runs regular vacuum; it **never runs VACUUM FULL automatically** to shrink tables. This is intentional because FULL requires a heavy lock and full relation rewrite.

### 7.5. Do Not Run FULL Just Because n_dead_tup Is High

`n_dead_tup` is an estimate; dead tuples can be cleaned and reused by regular VACUUM. Before choosing FULL, verify:

1. Do dead tuples actually remain high after regular vacuum?
2. Is relation size markedly larger than live data requirements?
3. Will freed space simply be reused by the ongoing workload?
4. Is a long transaction pinning the horizon?
5. Are temporary disk space and a lock window available?

### 7.6. When to Consider It

- A large volume of data was deleted and disk must be returned to the filesystem;
- Severe bloat has been confirmed via measurement;
- A maintenance window or downtime tolerance exists;
- Sufficient disk headroom for rewriting and a backup/recovery plan are verified.

## 8. CLUSTER: Rewriting and Ordering by Index

`CLUSTER` rewrites a table in the physical order of a specified index:

~~~sql
CLUSTER public.orders USING orders_created_at_idx;
~~~

### 8.1. What Does CLUSTER Do?

- Rewrites the table in index order;
- Rebuilds the table's indexes as part of the process;
- Can improve locality when queries routinely read adjacent rows by the clustered key;
- Reclaims heap free space/bloat by creating a fresh layout.

### 8.2. CLUSTER Does Not Maintain Order Permanently

After CLUSTER, new INSERTs/UPDATEs gradually erode physical ordering. PostgreSQL does not keep the table sorted by index order on subsequent writes.

### 8.3. Locks and Disk

CLUSTER takes a strong lock (ACCESS EXCLUSIVE) and requires temporary disk space for the rewrite. Plan it as major maintenance, not a lightweight index tuning command.

### 8.4. CLUSTER vs. VACUUM FULL

| Criterion | VACUUM FULL | CLUSTER |
| --- | --- | --- |
| Rewrites heap | Yes | Yes |
| Orders by index | Not the goal | Yes |
| Reclaims heap bloat | Yes | Yes |
| Rebuilds indexes | Yes via rewrite process | Yes |
| Strong lock | Yes | Yes |
| Preserves order long-term | Not guaranteed | Not guaranteed after subsequent DML |

Choose CLUSTER when **physical ordering along an index** delivers measurable workload value, not merely to shrink file size.

## 9. pg_repack: More Online Rewrites, Yet Not Free

`pg_repack` is an extension/tool outside core PostgreSQL designed to rebuild tables/indexes while minimizing read/write lock duration compared to VACUUM FULL or CLUSTER under suitable conditions.

### 9.1. High-Level Workflow

pg_repack generally:

1. Creates a new table structure with the desired layout;
2. Copies data over;
3. Tracks/applies concurrent changes occurring during the copy;
4. Swaps the structures at the final step under a shorter lock when conditions permit.

Exact mechanics depend on extension version and execution options.

### 9.2. Does Not Mean Zero-Lock

pg_repack still acquires locks at certain stages, requires specific privileges and prerequisites, can be blocked by long-running transactions/DDL, and requires temporary disk for both old and new copies. Never claim it is "100% online and never blocks."

### 9.3. Prerequisites to Verify

- pg_repack version matches the server;
- Extension is installed and approved by DBAs;
- Table has a primary key or suitable unique index required by the tool/version;
- Proper ownership and object-creation privileges;
- Adequate disk headroom and WAL/replication budget;
- Monitored lock window and workload;
- Backup, rollback, and recovery plans.

### 9.4. When to Consider It

When significant bloat is confirmed and table/index rewrites are required, yet a long ACCESS EXCLUSIVE lock from VACUUM FULL is unacceptable. Validate against the extension's official documentation and test in staging first.

### 9.5. pg_repack Does Not Replace Autovacuum

Rewriting treats the symptom. If workload, autovacuum settings, long snapshots, and index design stay unchanged, bloat will return.

## 10. REINDEX: Addressing Index Bloat

`REINDEX` rebuilds an index from its table/partition data. It is usually the direct way to reclaim confirmed bloat inside an index.

### 10.1. Reindexing a Single Index

~~~sql
REINDEX INDEX public.orders_customer_id_idx;
~~~

Non-concurrent REINDEX blocks concurrent writes/reads according to REINDEX lock semantics; verify version and lock behavior.

### 10.2. REINDEX TABLE

~~~sql
REINDEX TABLE public.orders;
~~~

Rebuilds all indexes on the table; it **is not** a heap rewrite like VACUUM FULL. If bloat lives mainly in the heap, REINDEX alone will not fix heap bloat.

### 10.3. REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY public.orders_customer_id_idx;
~~~

In supported versions, `CONCURRENTLY` reduces blocking of INSERT/UPDATE/DELETE for most of the rebuild by building a new index, syncing changes, and swapping when ready. However:

- It still takes locks in brief phases;
- Can wait on older transactions/snapshots;
- Requires temporary disk for both old and new indexes simultaneously;
- Consumes CPU/I/O and generates WAL;
- Can fail and leave behind an invalid index requiring cleanup;
- Cannot run inside a transaction block.

### 10.4. REINDEX Is Not VACUUM

| Command | Primary Purpose |
| --- | --- |
| VACUUM | Reclaims dead tuples and makes space reusable |
| VACUUM FULL | Rewrites heap to shrink the relation |
| REINDEX | Rebuilds indexes |
| REINDEX CONCURRENTLY | Rebuilds indexes with minimal DML blocking via concurrent phases |
| CLUSTER | Rewrites heap in index order |

### 10.5. When to Reindex

- A B-tree index shows abnormal page density/size after heavy churn;
- An index is invalid/corrupt under documented recovery procedures;
- Index disk space must be reclaimed where vacuum cleanup does not shrink the file;
- Evidence shows the index is a major source of storage or latency issues.

Never reindex every index on an arbitrary schedule: rebuilding consumes I/O/WAL, temporary disk, and can impact production.

## 11. HOT Updates and Fillfactor

**HOT (Heap-Only Tuple)** lowers the cost of updating a row by avoiding new index entries under qualifying conditions. It is a major mechanism for limiting index bloat on update-heavy tables.

### 11.1. HOT Conditions

An UPDATE can be HOT when:

- Columns referenced by the table's indexes do not change (including columns in index expressions/predicates);
- The new tuple version fits on the same heap page as the old version;
- Other index-type and implementation-specific HOT conditions are met.

If an UPDATE alters an indexed column, PostgreSQL normally inserts new index entries for the new tuple version.

### 11.2. Why Does Fillfactor Relate to HOT?

If heap pages are packed near 100%, an UPDATE needing a new tuple version finds no room on the old page. HOT fails even when no indexed column changed. Lowering table fillfactor below 100 reserves room for same-page updates.

### 11.3. Table Fillfactor

~~~sql
CREATE TABLE public.orders (
    order_id bigint PRIMARY KEY,
    status text NOT NULL,
    updated_at timestamptz NOT NULL
)
WITH (fillfactor = 80);
~~~

Fillfactor 80 is an example: PostgreSQL targets roughly 80% page fullness when writing new tuples per fillfactor rules, leaving space for updates. This does not guarantee every page always sits at exactly 20% free.

### 11.4. Changing Fillfactor on an Existing Table

~~~sql
ALTER TABLE public.orders
SET (fillfactor = 80);
~~~

This changes the storage parameter for **pages/tuples created or written afterward**; it does not automatically rewrite the existing table into the new layout. To apply it to existing pages, a planned rewrite operation with lock/disk evaluation is required.

### 11.5. Lower Fillfactor Is Not Always Better

- Append-only tables with rare UPDATEs do not need much reserved space;
- Lower fillfactor enlarges the initial relation and lowers scan density;
- Wide rows can consume even more pages;
- If UPDATEs routinely modify indexed columns, lowering fillfactor will not enable HOT;
- Setting it too low adds unnecessary storage and I/O overhead.

### 11.6. Index Fillfactor

B-tree indexes also have a fillfactor, typically defaulting to 90. It can be configured:

~~~sql
CREATE INDEX orders_customer_idx
ON public.orders(customer_id)
WITH (fillfactor = 80);

ALTER INDEX public.orders_customer_idx
SET (fillfactor = 80);
~~~

Index fillfactor controls leaf-page fullness during index builds and splits. Lower values can reduce splits on random-insert workloads at the expense of more pages and disk space.

### 11.7. ALTER INDEX Does Not Automatically Rebuild the Index

Changing fillfactor does not reorganize existing pages to the new density. To apply the fillfactor across the entire index, evaluate REINDEX (concurrently if supported by your version).

### 11.8. Monitoring the HOT Ratio

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    round(
        100.0 * n_tup_hot_upd / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent
FROM pg_stat_user_tables
WHERE n_tup_upd > 0
ORDER BY n_tup_upd DESC;
~~~

A high HOT ratio suggests UPDATE workloads leverage HOT effectively; a low ratio warrants inspecting updated columns, index definitions, row width, and free space. **There is no single universal HOT ratio target for all tables.**

### 11.9. HOT Does Not Eliminate Heap Bloat

HOT cuts index churn yet still writes new tuple versions in the heap. VACUUM is still needed to prune/clean unneeded versions. HOT reduces cost; it does not replace VACUUM.

## 12. Autovacuum: Automatic Maintenance

PostgreSQL runs an **autovacuum launcher** and worker processes that automatically execute VACUUM/ANALYZE when tables cross configured thresholds. For most systems, keeping autovacuum enabled and tuned to the workload is fundamental for controlling bloat.

### 12.1. Two Tasks Performed by Autovacuum

- **Auto-vacuum:** cleans dead tuples, updates visibility/freeze metadata;
- **Auto-analyze:** gathers planner statistics once enough rows change.

A table may trigger VACUUM and ANALYZE at different times.

### 12.2. Vacuum Thresholds Based on Threshold and Scale Factor

For UPDATE/DELETE, the trigger threshold is conceptually described as:

~~~text
vacuum threshold
  = autovacuum_vacuum_threshold
  + autovacuum_vacuum_scale_factor * estimated_table_tuples
~~~

Common PostgreSQL defaults are threshold 50 and scale factor 0.2, though **always check your actual version/configuration**. A 100-million-row table with scale factor 0.2 needs roughly 20 million tuple changes (plus threshold) before triggering under this formula.

### 12.3. Why Can the Default Scale Factor Be Too High?

On very large tables, 20% corresponds to tens of millions of rows. Autovacuum may wait until massive dead tuples accumulate, leading to table/index bloat and heavy vacuum spikes.

### 12.4. Analyze Threshold

~~~text
analyze threshold
  = autovacuum_analyze_threshold
  + autovacuum_analyze_scale_factor * estimated_table_tuples
~~~

Stale statistics can cause poor query plans even after vacuum cleans dead tuples. `ANALYZE` is a separate job to monitor.

### 12.5. Insert-Triggered Vacuum Thresholds

Modern PostgreSQL also provides `autovacuum_vacuum_insert_threshold` and `autovacuum_vacuum_insert_scale_factor` to vacuum append-heavy tables, updating the visibility map and freezing tuples. Insert-triggered vacuuming operates differently from UPDATE/DELETE thresholds.

### 12.6. Checking Current Configuration

~~~sql
SHOW autovacuum;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_vacuum_insert_threshold;
SHOW autovacuum_vacuum_insert_scale_factor;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
SHOW autovacuum_max_workers;
SHOW autovacuum_naptime;
SHOW autovacuum_vacuum_cost_limit;
SHOW autovacuum_vacuum_cost_delay;
~~~

Certain GUCs or defaults differ across major versions and managed services. Use `SHOW`/`pg_settings` instead of memorizing fixed numbers.

### 12.7. Per-Table Tuning

~~~sql
ALTER TABLE public.orders
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.01
);
~~~

This is an example for a large, frequently updated table, not a universal optimum. For small tables, different absolute thresholds and scale factors apply.

### 12.8. Inspecting Per-Table Settings

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND c.reloptions IS NOT NULL
ORDER BY n.nspname, c.relname;
~~~

`reloptions` stores relation storage parameters, including fillfactor and any per-table autovacuum overrides.

### 12.9. Autovacuum Workers

`autovacuum_max_workers` caps how many autovacuum workers run concurrently. Raising worker count lets more tables vacuum in parallel, yet increases CPU/I/O contention. If disk throughput is saturated, adding workers will not speed up total vacuum throughput.

### 12.10. Cost-Based Delay

Autovacuum uses cost-based vacuum delay/limit settings to balance maintenance against foreground workloads. If vacuum runs too slowly, inspect:

- Global and per-table cost limit/delay;
- I/O saturation;
- Worker count and queue of eligible tables;
- Long transactions or replication horizons;
- Table size and churn rate.

Do not blindly raise cost limits sky-high without measuring application latency impact.

### 12.11. Autovacuum Does Not Replace VACUUM FULL

Autovacuum keeps relations clean and space reusable. It does not rewrite tables to shrink files to minimum size. Returning disk space to the filesystem requires a controlled rewrite method.

### 12.12. Never Disable Autovacuum to "Treat" Bloat

~~~sql
-- Do not use as a permanent setting:
ALTER TABLE public.orders
SET (autovacuum_enabled = false);
~~~

Disabling autovacuum causes dead tuples to accumulate, increasing bloat and transaction ID wraparound risk. Use only in specialized temporary scenarios with active operator monitoring and an explicit manual VACUUM plan.

## 13. Vacuum Freeze and Transaction ID Wraparound

VACUUM does more than clean bloat. It also **freezes tuples** so old transaction IDs are never misinterpreted after the counter wraps around.

### 13.1. Why Does Freezing Matter?

PostgreSQL uses finite transaction IDs. When transaction age grows large, the database must ensure old tuples are marked frozen or handled under anti-wraparound rules before IDs can be reused.

### 13.2. Anti-Wraparound Autovacuum

Even if a table has very few dead tuples, PostgreSQL may still trigger vacuuming to freeze tuples. Anti-wraparound vacuum protects database correctness, not merely storage efficiency.

### 13.3. Checking age(relfrozenxid)

~~~sql
SELECT
    n.nspname,
    c.relname,
    age(c.relfrozenxid) AS xid_age,
    c.relfrozenxid
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY xid_age DESC
LIMIT 30;
~~~

This indicator identifies tables with high XID age. Combine it with database-level age, freeze settings, and autovacuum info; never conclude wraparound is imminent from a single row alone.

### 13.4. Checking Freeze Limits

~~~sql
SHOW autovacuum_freeze_max_age;
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
~~~

These parameters govern when VACUUM freezes tuples. Changing them arbitrarily can spike freeze work or push wraparound risk closer.

### 13.5. VACUUM FREEZE Does Not Mean Compacting

~~~sql
VACUUM (FREEZE, VERBOSE) public.orders;
~~~

FREEZE processes transaction metadata; it is not a relation rewrite command to remove bloat. If the goal is shrinking files, evaluate FULL/CLUSTER/pg_repack separately.

### 13.6. Never Delay Anti-Wraparound Vacuum

When approaching safety limits, PostgreSQL prioritizes emergency vacuuming and may refuse writes to protect data integrity. This is a critical incident; follow version-specific docs and DBA runbooks rather than raising freeze thresholds to silence warnings.

## 14. Measuring Table, Index, and TOAST Sizes

Before fixing bloat, identify where disk space actually sits. PostgreSQL provides size functions:

| Function | Meaning |
| --- | --- |
| `pg_relation_size(relation)` | Size of the default fork (main fork) of the relation |
| `pg_table_size(relation)` | Table size including heap, TOAST, and auxiliary components, excluding indexes |
| `pg_indexes_size(relation)` | Total size of the table's indexes |
| `pg_total_relation_size(relation)` | Total of table + indexes + TOAST |
| `pg_size_pretty(bytes)` | Human-readable formatting of bytes |

### 14.1. Largest Tables by Total Size

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_table_size(relid)) AS table_including_toast,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
~~~

This query shows physical footprint; **it does not by itself prove bloat**. Tables with many indexes or large TOAST data can have high total size due to real data.

### 14.2. Size of Individual Indexes

~~~sql
SELECT
    ns.nspname AS schemaname,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size,
    pg_get_indexdef(idx.oid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_relation_size(idx.oid) DESC
LIMIT 50;
~~~

This locates the heaviest disk-consuming indexes. Large size does not automatically mean an index is redundant or bloated; cross-check query workload, row counts, and distinct values.

### 14.3. Checking Heap / Index / TOAST Breakdown

~~~sql
SELECT
    c.oid::regclass AS relation,
    pg_size_pretty(pg_relation_size(c.oid)) AS main_heap,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes,
    pg_size_pretty(pg_table_size(c.oid)
                   - pg_relation_size(c.oid)) AS toast_and_aux,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.relpersistence = 'p'
  AND c.relnamespace NOT IN (
      'pg_catalog'::regnamespace,
      'information_schema'::regnamespace
  )
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 30;
~~~

`pg_table_size` includes TOAST and auxiliary forks, so subtracting `pg_relation_size` gives only a rough TOAST/aux difference, not an exact TOAST measurement. To measure TOAST directly, query the relation referenced by `pg_class.reltoastrelid`.

### 14.4. Measuring TOAST Separately

~~~sql
SELECT
    c.oid::regclass AS table_name,
    NULLIF(c.reltoastrelid, 0)::regclass AS toast_relation,
    CASE
        WHEN c.reltoastrelid <> 0
        THEN pg_size_pretty(pg_total_relation_size(c.reltoastrelid))
    END AS toast_total_size
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.reltoastrelid <> 0
ORDER BY pg_total_relation_size(c.reltoastrelid) DESC;
~~~

A TOAST table grows large when rows hold oversized values. Determine whether that space holds active retained data or dead versions of modified values.

## 15. Dead Tuple and Vacuum Statistics

The `pg_stat_user_tables` view provides estimates/counters to track table activity.

### 15.1. Which Tables Have Many Dead Tuples?

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_percent,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

`n_live_tup` and `n_dead_tup` are **estimates**, not exact live counts at every instant. A high dead percentage is a signal to investigate, not sufficient proof to run VACUUM FULL.

### 15.2. Tracking Churn Rates

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY (n_tup_upd + n_tup_del) DESC
LIMIT 30;
~~~

Counters can reset and reflect activity since the last reset; take periodic snapshots if you need hourly or daily churn rates.

### 15.3. Index Usage Statistics

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
~~~

Low `idx_scan` can suggest a rarely used index, yet inspect stats reset age, seasonal workloads, constraints, and query plans. **Never DROP an index solely because idx_scan=0 over a short window**: the index may enforce UNIQUE/FK constraints or serve scheduled batch jobs.

### 15.4. Monitoring Running Vacuums

~~~sql
SELECT
    p.pid,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_vacuum AS p
LEFT JOIN pg_stat_activity AS a USING (pid)
ORDER BY p.pid;
~~~

Progress columns reflect the current vacuum phase/work; some fields may not apply in every phase. Zero rows means no vacuum is currently running at query time.

### 15.5. Vacuum Progress Is Not Percentage of Bloat Removed

`heap_blks_scanned / heap_blks_total` shows scan progress in the current pass, not the share of bloat eliminated. Never use it to predict exact completion time or exact disk space reclaimed.

### 15.6. Checking Stale ANALYZE

~~~sql
SELECT
    schemaname,
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC
LIMIT 30;
~~~

Stale statistics can degrade query plans, causing extra page reads or poor index choices. That is a planner statistics issue, distinct from physical bloat even when both occur together.

## 16. Long Transactions and Replication Horizons

VACUUM can only remove tuple versions no longer needed by any active snapshot/transaction. Therefore, locate **what is pinning the xmin horizon** whenever dead tuples stay high after vacuum.

### 16.1. Finding Long-Running Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Pay close attention to `idle in transaction` sessions. They can hold transaction snapshots open even while running no active query.

### 16.2. Long Snapshots Do Not Require Slow Queries

~~~sql
BEGIN;
SELECT COUNT(*) FROM public.orders;
-- application keeps the connection open for hours
~~~

can hold a snapshot open for hours. VACUUM cannot clean tuple versions still visible to that snapshot. Inspect transaction lifecycles and connection pool behavior.

### 16.3. Replication Slots

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE WHEN catalog_xmin IS NOT NULL
         THEN age(catalog_xmin) END AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Long-inactive slots retain WAL and pin transaction horizons. **Never DROP a replication slot casually to solve bloat**: the downstream consumer may lose replication continuity and require full resync/reinitialization.

### 16.4. Standby Feedback

~~~sql
SHOW hot_standby_feedback;
~~~

When standbys send feedback to the primary, the xmin horizon can be held back to avoid query conflicts on standbys. This reduces standby conflicts at the cost of dead tuple/bloat accumulation on the primary.

### 16.5. Prepared Transactions

~~~sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Orphaned prepared transactions hold locks and transaction horizons. Never run `ROLLBACK PREPARED` without verifying the two-phase commit coordinator and business transaction state with the system owner.

### 16.6. Resolve Root Blockers Before Re-Running VACUUM

While an old snapshot pins tuples, repeating VACUUM cannot reclaim those pinned versions. Identify the blocking session/slot/prepared transaction, assess impact, and resolve it through proper application/replication procedures. Once the horizon advances, vacuum can clean up.

## 14. Measuring Table, Index, and TOAST Sizes

Before fixing bloat, identify where disk space actually sits. PostgreSQL provides size functions:

| Function | Meaning |
| --- | --- |
| `pg_relation_size(relation)` | Size of the default fork (main fork) of the relation |
| `pg_table_size(relation)` | Table size including heap, TOAST, and auxiliary components, excluding indexes |
| `pg_indexes_size(relation)` | Total size of the table's indexes |
| `pg_total_relation_size(relation)` | Total of table + indexes + TOAST |
| `pg_size_pretty(bytes)` | Human-readable formatting of bytes |

### 14.1. Largest Tables by Total Size

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_table_size(relid)) AS table_including_toast,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 30;
~~~

This query shows physical footprint; **it does not by itself prove bloat**. Tables with many indexes or large TOAST data can have high total size due to real data.

### 14.2. Size of Individual Indexes

~~~sql
SELECT
    ns.nspname AS schemaname,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    pg_size_pretty(pg_relation_size(idx.oid)) AS index_size,
    pg_get_indexdef(idx.oid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_relation_size(idx.oid) DESC
LIMIT 50;
~~~

This locates the heaviest disk-consuming indexes. Large size does not automatically mean an index is redundant or bloated; cross-check query workload, row counts, and distinct values.

### 14.3. Checking Heap / Index / TOAST Breakdown

~~~sql
SELECT
    c.oid::regclass AS relation,
    pg_size_pretty(pg_relation_size(c.oid)) AS main_heap,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes,
    pg_size_pretty(pg_total_relation_size(c.oid)
                   - pg_table_size(c.oid)) AS toast_and_aux,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.relpersistence = 'p'
  AND c.relnamespace NOT IN (
      'pg_catalog'::regnamespace,
      'information_schema'::regnamespace
  )
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 30;
~~~

`pg_table_size` includes TOAST and auxiliary forks, so the subtraction above is not an exact TOAST measurement. To measure TOAST directly, query the relation referenced by `pg_class.reltoastrelid`.

### 14.4. Measuring TOAST Separately

~~~sql
SELECT
    c.oid::regclass AS table_name,
    NULLIF(c.reltoastrelid, 0)::regclass AS toast_relation,
    CASE
        WHEN c.reltoastrelid <> 0
        THEN pg_size_pretty(pg_total_relation_size(c.reltoastrelid))
    END AS toast_total_size
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.reltoastrelid <> 0
ORDER BY pg_total_relation_size(c.reltoastrelid) DESC;
~~~

A TOAST table grows large when rows hold oversized values. Determine whether that space holds active retained data or dead versions of modified values.

## 15. Dead Tuple and Vacuum Statistics

The `pg_stat_user_tables` view provides estimates/counters to track table activity.

### 15.1. Which Tables Have Many Dead Tuples?

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_percent,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

`n_live_tup` and `n_dead_tup` are **estimates**, not exact live counts at every instant. A high dead percentage is a signal to investigate, not sufficient proof to run VACUUM FULL.

### 15.2. Tracking Churn Rates

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY (n_tup_upd + n_tup_del) DESC
LIMIT 30;
~~~

Counters can reset and reflect activity since the last reset; take periodic snapshots if you need hourly or daily churn rates.

### 15.3. Index Usage Statistics

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
~~~

Low `idx_scan` can suggest a rarely used index, yet inspect stats reset age, seasonal workloads, constraints, and query plans. **Never DROP an index solely because idx_scan=0 over a short window**: the index may enforce UNIQUE/FK constraints or serve scheduled batch jobs.

### 15.4. Monitoring Running Vacuums

~~~sql
SELECT
    p.pid,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    p.index_vacuum_count,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_progress_vacuum AS p
LEFT JOIN pg_stat_activity AS a USING (pid)
ORDER BY p.pid;
~~~

Progress columns reflect the current vacuum phase/work; some fields may not apply in every phase. Zero rows means no vacuum is currently running at query time.

### 15.5. Vacuum Progress Is Not Percentage of Bloat Removed

`heap_blks_scanned / heap_blks_total` shows scan progress in the current pass, not the share of bloat eliminated. Never use it to predict exact completion time or exact disk space reclaimed.

### 15.6. Checking Stale ANALYZE

~~~sql
SELECT
    schemaname,
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC
LIMIT 30;
~~~

Stale statistics can degrade query plans, causing extra page reads or poor index choices. That is a planner statistics issue, distinct from physical bloat even when both occur together.

## 16. Long Transactions and Replication Horizons

VACUUM can only remove tuple versions no longer needed by any active snapshot/transaction. Therefore, locate **what is pinning the xmin horizon** whenever dead tuples stay high after vacuum.

### 16.1. Finding Long-Running Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Pay close attention to `idle in transaction` sessions. They can hold transaction snapshots open even while running no active query.

### 16.2. Long Snapshots Do Not Require Slow Queries

~~~sql
BEGIN;
SELECT COUNT(*) FROM public.orders;
-- application keeps the connection open for hours
~~~

can hold a snapshot open for hours. VACUUM cannot clean tuple versions still visible to that snapshot. Inspect transaction lifecycles and connection pool behavior.

### 16.3. Replication Slots

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE WHEN catalog_xmin IS NOT NULL
         THEN age(catalog_xmin) END AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Long-inactive slots retain WAL and pin transaction horizons. **Never DROP a replication slot casually to solve bloat**: the downstream consumer may lose replication continuity and require full resync/reinitialization.

### 16.4. Standby Feedback

~~~sql
SHOW hot_standby_feedback;
~~~

When standbys send feedback to the primary, the xmin horizon can be held back to avoid query conflicts on standbys. This reduces standby conflicts at the cost of dead tuple/bloat accumulation on the primary.

### 16.5. Prepared Transactions

~~~sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Orphaned prepared transactions hold locks and transaction horizons. Never run `ROLLBACK PREPARED` without verifying the two-phase commit coordinator and business transaction state with the system owner.

### 16.6. Resolve Root Blockers Before Re-Running VACUUM

While an old snapshot pins tuples, repeating VACUUM cannot reclaim those pinned versions. Identify the blocking session/slot/prepared transaction, assess impact, and resolve it through proper application/replication procedures. Once the horizon advances, vacuum can clean up.

## 17. Measuring Live/Dead/Free Space with pgstattuple

Statistics in `pg_stat_user_tables` are estimates. For deeper measurement, PostgreSQL provides the **`pgstattuple`** extension (typically part of contrib).

### 17.1. Installing the Extension in a Lab Database

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
~~~

Extension installation depends on server packages/images and role privileges. Managed services may require DBA involvement or extension allowlisting. Never assume the extension is pre-installed on every PostgreSQL instance.

### 17.2. Measuring a Table

~~~sql
SELECT *
FROM pgstattuple('public.orders'::regclass);
~~~

Typical output columns:

| Field | Meaning |
| --- | --- |
| `table_len` | Scanned relation size |
| `tuple_count` | Count of live tuples |
| `tuple_len` | Total bytes of live tuple data |
| `tuple_percent` | Percentage of live tuple bytes |
| `dead_tuple_count` | Count of dead tuples |
| `dead_tuple_len` | Total bytes of dead tuples |
| `dead_tuple_percent` | Percentage of dead tuple bytes |
| `free_space` | Total free space inside the relation |
| `free_percent` | Percentage of free space |

### 17.3. Example of Reading Output

Suppose an illustrative output:

| Metric | Hypothetical Value |
| --- | ---: |
| table_len | 1,000 MB |
| tuple_len | 550 MB |
| dead_tuple_len | 150 MB |
| free_space | 220 MB |
| overhead/other | 80 MB |

You cannot say "bloat is exactly 450 MB" without considering page layout, alignment, line pointers, index/TOAST, fillfactor, and reusability. Yet the numbers indicate the relation has substantial bytes not holding live tuple data and warrants investigation.

### 17.4. pgstattuple_approx

~~~sql
SELECT *
FROM pgstattuple_approx('public.orders'::regclass);
~~~

This approximate function leverages the visibility map to skip all-visible pages, reducing cost relative to a full scan. It returns fields such as:

- `table_len`, `scanned_percent`;
- `approx_tuple_count`, `approx_tuple_len`, `approx_tuple_percent`;
- `dead_tuple_count`, `dead_tuple_len`, `dead_tuple_percent`;
- `approx_free_space`, `approx_free_percent`.

Results are **approximations**; do not mechanically compare them directly against exact numbers when snapshots/workloads have shifted.

### 17.5. Measuring a B-Tree Index

~~~sql
SELECT *
FROM pgstatindex('public.orders_customer_id_idx'::regclass);
~~~

Typical metrics include:

| Field | Meaning |
| --- | --- |
| `tree_level` | B-tree height |
| `index_size` | Index size |
| `internal_pages` | Count of internal pages |
| `leaf_pages` | Count of leaf pages |
| `empty_pages` | Count of empty pages |
| `deleted_pages` | Count of deleted pages |
| `avg_leaf_density` | Average leaf-page density |
| `leaf_fragmentation` | Leaf-page fragmentation metric per extension definition |

`pgstatindex` applies to **B-tree** indexes. Never use this output to diagnose bloat on GIN/GiST/BRIN/hash indexes.

### 17.6. Low Density Does Not Automatically Prove Bloat

Low leaf density can result from:

- Index fillfactor intentionally configured low;
- Index recently built with a fillfactor;
- Random insert workloads and page splits;
- Heavy deletes/updates;
- Key characteristics and tuple size.

Compare against fillfactor design, workload, and history. A 70% density index can be completely normal for random insert/update workloads.

### 17.7. Cost of pgstattuple

`pgstattuple` scans the full relation; `pgstatindex` also reads the index structure. On hundreds-of-GB tables/indexes, this causes significant I/O. Prefer `pgstattuple_approx` where suitable, pick quiet windows, and monitor impact.

### 17.8. Do Not Run Continuously for Real-Time Polling

Deep-inspection extensions are meant for **targeted investigations/periodic audits**, not running every minute on every table. Use lighter stats views for trend monitoring, then target suspect relations for deep checks.

## 18. Bloat Estimation: Limitations to Understand

Many SQL formulas online use `pg_class.reltuples`, `relpages`, data types, page size, and fillfactor to estimate expected pages. These formulas are useful for screening, yet carry assumptions.

### 18.1. reltuples and relpages Are Estimates

~~~sql
SELECT
    c.oid::regclass AS relation,
    c.reltuples,
    c.relpages,
    pg_relation_size(c.oid) AS relation_bytes,
    current_setting('block_size')::integer AS block_size
FROM pg_class AS c
WHERE c.relkind = 'r'
  AND c.relnamespace NOT IN (
      'pg_catalog'::regnamespace,
      'information_schema'::regnamespace
  )
ORDER BY pg_relation_size(c.oid) DESC;
~~~

`reltuples`/`relpages` update via operations such as VACUUM/ANALYZE and do not always reflect instantaneous current state.

### 18.2. Expected-Size Formulas Must Assume Row Width

A simple estimate may need:

- Average tuple width;
- Heap page overhead;
- Line pointer overhead;
- Fillfactor;
- Alignment/padding;
- Null bitmap;
- TOAST storage behavior;
- Tuple visibility/dead versions.

If row-width assumptions are wrong, expected page counts are wrong too. There is no single universal bloat query exact across every schema/workload.

### 18.3. Bloat Estimates Are Not Immediately Reclaimable Disk Bytes

A report claiming 40 GB of "waste" does not guarantee VACUUM FULL will return exactly 40 GB. Part may be useful free space, part due to fillfactor, part inside indexes/TOAST, and part un-reclaimable due to snapshots.

### 18.4. Verify Estimates with pgstattuple

A sound workflow:

1. Use size/stats views to shortlist candidates;
2. Run pgstattuple/pgstatindex on selected relations;
3. Check long transactions/slots;
4. Run regular VACUUM if reclaimable dead tuples exist;
5. Re-measure;
6. Consider a rewrite only if physical bloat remains substantial and disk must be returned.

### 18.5. Measure Before/After Under Identical Conditions

Before/after comparisons should match:

- Same relation and same size function;
- Same workload window or recorded DML volume between measurements;
- Same extension/version and measurement method;
- Timestamps/snapshots;
- Dead tuple counts, free space, and index density;
- Query latency/I/O if performance is the goal.

Never compare `pg_table_size` before against `pg_total_relation_size` after and conclude bloat grew.

## 19. Checking Per-Table Autovacuum Status

### 19.1. Summarizing Activity and Vacuum Age

~~~sql
SELECT
    s.schemaname,
    s.relname,
    pg_size_pretty(pg_total_relation_size(s.relid)) AS total_size,
    s.n_live_tup,
    s.n_dead_tup,
    s.n_tup_upd,
    s.n_tup_del,
    s.last_autovacuum,
    s.autovacuum_count,
    s.last_autoanalyze,
    s.n_mod_since_analyze
FROM pg_stat_user_tables AS s
ORDER BY pg_total_relation_size(s.relid) DESC
LIMIT 50;
~~~

Look for large tables with high n_dead_tup, heavy UPDATE/DELETE counts, and very old last_autovacuum timestamps. Do not rely solely on `last_autovacuum`: a table might simply not have crossed thresholds yet, or may have been vacuumed manually.

### 19.2. Checking Tables with Autovacuum Disabled

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.reloptions
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.reloptions @> ARRAY['autovacuum_enabled=false'];
~~~

This finds one specific storage option form; global and per-table autovacuum settings must be checked further. Temporary tables are not handled by autovacuum like permanent tables.

### 19.3. Checking Database-Level Vacuum Settings

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name LIKE 'autovacuum%'
   OR name LIKE 'vacuum_%'
ORDER BY name;
~~~

`source` reveals whether settings come from defaults, config files, database, role, or session. Managed databases may impose platform limits or overrides.

### 19.4. Idle Workers Can Be a Symptom

If autovacuum is not running, check:

- Have any tables crossed thresholds?
- Is autovacuum enabled at server/database/table level?
- Are worker slots available?
- Are workers throttled by cost delay or slow I/O?
- Are lock conflicts or long-running transactions blocking?
- Are logs showing permission or disk-space errors?

### 19.5. Autovacuum Running Continuously on the Same Table

A table may repeatedly hit thresholds due to a very high write rate. This does not mean autovacuum is "malfunctioning"; the workload may generate churn faster than current cleanup capacity. Review thresholds, scale factors, cost budget, worker capacity, index count, and schema design.

## 20. Root-Cause Bloat Remediation Workflow

There is no single "fix bloat" command for all cases. Identify **whether bloat sits in the heap, indexes, or TOAST**, whether vacuum can clean it, and whether the goal is space reuse or returning disk to the filesystem.

### 20.1. Decision Tree

~~~text
Relation size grows / query scans slow down
            |
            v
Measure heap, indexes, TOAST, and live/dead/free
            |
            v
Many dead tuples remaining?
     | Yes                        | No / Few
     v                            v
Check xmin horizon,          Sparse index density/layout
autovacuum, and vacuum        or large heap free space?
     |                            |
     v                            v
Fix blocker; run regular     Index bloat? ---- Yes ---> REINDEX (CONCURRENTLY if suited)
VACUUM + ANALYZE             Heap bloat?  ---- Yes ---> Consider rewrite
     |                            |
     v                            v
Re-measure, monitor reuse    Need disk reclaimed immediately?
                                  |
                      +-----------+-----------+
                      |                       |
                      v                       v
             Lock window exists        Must minimize blocking
                      |                       |
                      v                       v
              VACUUM FULL/CLUSTER       pg_repack (if suitable)
~~~

This diagram is a decision framework, not an automated algorithm. Every step requires checking PostgreSQL version, locks, disk headroom, replication, and SLAs.

### 20.2. Case A: Many Dead Tuples, Yet File Shrink Not Needed

~~~sql
VACUUM (ANALYZE, VERBOSE) public.orders;
~~~

Then:

1. Check `n_dead_tup` and vacuum timestamps;
2. Re-measure with pgstattuple if needed;
3. Observe whether new INSERTs/UPDATEs reuse the free space;
4. Monitor size and query latency over time.

Do not run FULL merely because the file did not shrink; free space may now be ready for reuse.

### 20.3. Case B: Dead Tuples Do Not Decrease

Check:

- Long-running transactions and idle-in-transaction sessions;
- Replication slots, `xmin`, `catalog_xmin`;
- `hot_standby_feedback`;
- Prepared transactions;
- Worker/autovacuum settings;
- Lock waits, I/O saturation, and vacuum logs.

Resolve the horizon blocker first; run vacuum again once tuples become eligible for reclamation.

### 20.4. Case C: Confirmed Index Bloat

Target the specific index and consider:

~~~sql
REINDEX INDEX CONCURRENTLY public.orders_customer_id_idx;
~~~

Or during an approved maintenance window:

~~~sql
REINDEX INDEX public.orders_customer_id_idx;
~~~

Measure index size before/after, check index validity, query plans, lock waits, and WAL. Never reindex an entire database based solely on an estimated bloat report.

### 20.5. Case D: Heap Bloat Requiring Disk Reclamation

If a maintenance window is available:

~~~sql
VACUUM (FULL, ANALYZE) public.orders;
~~~

If physical ordering by an index is needed and locking is acceptable:

~~~sql
CLUSTER public.orders USING orders_created_at_idx;
~~~

If DML blocking must be minimized and prerequisites are satisfied, evaluate pg_repack. All three require disk headroom and staging validation.

### 20.6. Case E: Bloat Returns Rapidly

Do not keep scheduling frequent rewrites without fixing:

- Updating indexed columns unnecessarily;
- Low HOT ratio due to lack of page free space;
- Unsuitable fillfactor;
- Autovacuum thresholds set too high;
- Old transactions/snapshots;
- Churn-heavy ETL/batch jobs;
- Redundant indexes or overly wide keys.

### 20.7. Do Not Arbitrarily Substitute DROP/CREATE Index for REINDEX

Dropping an index can slow queries, drop constraint enforcement, or allow duplicate data during DML. If rebuilding an index, account for dependencies/constraints and use REINDEX or planned CREATE INDEX CONCURRENTLY.

## 21. Lab: Generating Churn, Measuring, and Observing VACUUM

This lab illustrates the difference among **dead tuples**, **reusable free space**, and **file size**. Run only in a lab database with permissions to create schemas/tables and sufficient disk; never run in production.

### 21.1. Create Schema and Test Table

~~~sql
CREATE SCHEMA copy426;

CREATE TABLE copy426.bloat_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status text NOT NULL,
    note text NOT NULL,
    payload text NOT NULL
)
WITH (fillfactor = 80);
~~~

Table fillfactor 80 reserves room for some updates; it does not guarantee every UPDATE is HOT.

### 21.2. Generate Sample Data

~~~sql
INSERT INTO copy426.bloat_demo(status, note, payload)
SELECT
    CASE WHEN g % 2 = 0 THEN 'open' ELSE 'closed' END,
    'note-' || g,
    repeat('x', 200)
FROM generate_series(1, 50000) AS g;

CREATE INDEX bloat_demo_status_idx
ON copy426.bloat_demo(status);

CREATE INDEX bloat_demo_note_idx
ON copy426.bloat_demo(note);
~~~

### 21.3. Record Initial Sizes

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('copy426.bloat_demo'::regclass))
        AS heap_size,
    pg_size_pretty(pg_indexes_size('copy426.bloat_demo'::regclass))
        AS indexes_size,
    pg_size_pretty(pg_total_relation_size('copy426.bloat_demo'::regclass))
        AS total_size;
~~~

### 21.4. UPDATE a Non-Indexed Column

~~~sql
UPDATE copy426.bloat_demo
SET payload = repeat('y', 200)
WHERE id % 2 = 0;
~~~

If the new tuple fits on the page and HOT conditions are met, part of the updates can be HOT because `payload` is not indexed. Check `n_tup_hot_upd` to observe; exact results depend on row layout and page free space.

### 21.5. UPDATE an Indexed Column

~~~sql
UPDATE copy426.bloat_demo
SET status = CASE
    WHEN status = 'open' THEN 'closed'
    ELSE 'open'
END
WHERE id % 3 = 0;
~~~

`status` is indexed, so updates changing its value are generally non-HOT with respect to that index, generating new index entries.

### 21.6. DELETE a Subset of Rows

~~~sql
DELETE FROM copy426.bloat_demo
WHERE id % 10 = 0;
~~~

Commit statements before measuring so deleted tuples qualify against current snapshots. VACUUM may still wait if other open transactions hold older snapshots.

### 21.7. Measure Dead/Free Space Before VACUUM

~~~sql
SELECT *
FROM pgstattuple('copy426.bloat_demo'::regclass);

SELECT
    pg_relation_size('copy426.bloat_demo'::regclass) AS heap_bytes,
    pg_indexes_size('copy426.bloat_demo'::regclass) AS index_bytes;
~~~

If the extension is unavailable/unpermitted, use `pg_stat_user_tables` estimates and skip the deep scan.

### 21.8. Run Regular VACUUM

~~~sql
VACUUM (VERBOSE, ANALYZE) copy426.bloat_demo;
~~~

Run this **outside an explicit transaction block**. Then re-measure with the same queries from 21.7.

### 21.9. What to Observe

- Dead tuple bytes/count should decrease;
- Free space should increase as tuples are reclaimed;
- Heap/index file sizes may not shrink noticeably;
- That space is now reusable by future INSERTs/UPDATEs;
- Index cleanup updates page states without guaranteeing index file shrinkage.

### 21.10. Inspect B-Tree Indexes

~~~sql
SELECT *
FROM pgstatindex('copy426.bloat_demo_status_idx'::regclass);

SELECT *
FROM pgstatindex('copy426.bloat_demo_note_idx'::regclass);
~~~

Compare leaf density/page counts before and after churn/vacuum if you recorded a baseline. Do not generalize a "correct" threshold for all workloads from a small lab.

### 21.11. Test REINDEX on a Lab Index

~~~sql
REINDEX INDEX CONCURRENTLY copy426.bloat_demo_status_idx;
~~~

If your version supports it and you are outside an explicit transaction block, concurrent reindex allows DML to continue for most of the operation. In a quiet lab, compare before/after sizes to see the rebuilt index. On older servers, use version-supported syntax or regular REINDEX in a test environment.

### 21.12. Test VACUUM FULL in the Lab Only

~~~sql
VACUUM (FULL, ANALYZE) copy426.bloat_demo;
~~~

This rewrites the table and takes an ACCESS EXCLUSIVE lock. Afterward, re-measure heap/table size to see file shrinkage compared to regular vacuum.

### 21.13. Do Not Scale the Lab Indefinitely

50,000 rows is enough to observe the concepts in a small environment. Do not inflate it to billions of rows just to plot bloat; disk/CPU/WAL and replication can be impacted.

### 21.14. Clean Up the Lab When Verified Safe

~~~sql
DROP SCHEMA copy426 CASCADE;
~~~

This deletes all objects in the lab schema. Run only if the schema is strictly **the lesson's test schema** with no data you need to preserve.

## 22. Bloat by Index Type

Not every index is a B-tree. Cleanup and measurement tools must match the access method.

### 22.1. B-Tree

B-trees handle equality/range/ordering queries. INSERT/UPDATE/DELETE cause page splits, dead entries, and sparse leaf pages. VACUUM cleans up; REINDEX rebuilds the structure.

### 22.2. GIN

GIN serves arrays, full-text search, and JSONB operators. It uses a pending list to batch inserts before merging into the main tree (depending on `fastupdate` and settings). An oversized pending list or lagging cleanup can spike query latency.

Factors to monitor:

- GIN pending list and `gin_pending_list_limit`;
- Autovacuum/VACUUM cleanup;
- Frequency of UPDATE/DELETE on indexed values;
- Index size and query latency.

Never use `pgstatindex` (a B-tree tool) to measure GIN.

### 22.3. GiST and SP-GiST

Spatial and specialized search indexes use their own tree structures. Page utilization and split behavior cannot be judged using B-tree leaf density thresholds. Use metrics/tools matching the access method and workload.

### 22.4. BRIN

BRIN stores block-range summaries, typically far smaller than B-trees on large tables whose data correlates with physical order. Bloat/size in BRIN has different semantics; check range count, summarization, and data correlation.

### 22.5. Hash Index

Hash indexes have their own bucket/split/overflow behavior. Do not apply B-tree bloat formulas to hash indexes.

### 22.6. Unused and Redundant Indexes

An index with zero query usage is a candidate for review, yet before dropping it:

- Check primary key/unique/exclusion constraints;
- Check foreign keys and query plans;
- Check daily/monthly/quarterly workloads;
- Check whether the index supports maintenance, reporting, or incident queries;
- Compare duplicate/left-prefix indexes against query predicates;
- Check time elapsed since last statistics reset.

Redundant indexes add storage and write amplification, yet dropping the wrong index can break correctness or performance.

### 22.7. Partial and Expression Indexes

Partial/expression indexes can reduce size by indexing only necessary rows/expressions. However, predicates/expressions also affect HOT eligibility and DML cost. Evaluate per workload rather than indexing every column.

## 23. Schema Design to Reduce Bloat

### 23.1. Index Only What the Workload Needs

Every index consumes storage and must be maintained when indexed data changes. Eliminating unnecessary indexes reduces:

- Index bloat;
- WAL volume;
- CPU/I/O for INSERT/UPDATE/DELETE;
- Vacuum/index cleanup duration;
- Backup/restore times.

### 23.2. Avoid Indexing Constantly Updated Columns Unnecessarily

If an `updated_at` column changes on every row update and is indexed, every UPDATE increases index churn. Ask which queries genuinely need that index and whether an alternative design works.

### 23.3. HOT-Friendly Schemas

To increase HOT opportunities:

- Avoid indexing frequently modified columns unless queries require them;
- Leave sensible free space on heap pages;
- Keep row width stable where feasible;
- Monitor HOT ratio;
- Audit expression/partial index dependencies.

### 23.4. Row Width and TOAST

Rows with multiple large text/JSONB columns trigger TOAST. Updating a large column can create new row versions and new TOAST chunks. If workloads frequently tweak a small part of a huge JSON document, consider splitting data into smaller tables/records aligned with access patterns and retention.

### 23.5. Separating Hot and Cold Data

A single table holding both active transactions and multi-year history mixes churn on the same relation. Depending on business requirements, time-based partitioning or archive tables help:

- Clear retention boundaries;
- Removing old data via partition detach/drop instead of row-by-row DELETE;
- Focusing vacuum on hot partitions;
- Limiting index maintenance to active data.

Partitioning does not eliminate bloat by itself; each partition still needs vacuum and index maintenance.

### 23.6. Retention and Bulk DELETEs

If policy calls for purging an entire month of data, dropping/detaching a partition is far cleaner than deleting millions of rows. Still verify foreign keys, dependencies, backups/replication, audit rules, legal holds, and DDL privileges.

### 23.7. TRUNCATE When Deleting an Entire Table

`TRUNCATE` reclaims table storage far faster than DELETE because it avoids row-by-row processing. However, it requires a strong lock, obeys specific FK/trigger rules, and does not fire row-level DELETE triggers. Use only when genuinely removing **all rows** and downstream systems accept those semantics.

### 23.8. Avoid No-Op UPDATEs

~~~sql
UPDATE public.orders
SET status = status
WHERE batch_id = 42;
~~~

still creates row versions and index churn despite unchanged values. When business logic allows, filter out unchanged rows:

~~~sql
UPDATE public.orders
SET status = 'paid'
WHERE batch_id = 42
  AND status IS DISTINCT FROM 'paid';
~~~

Cutting redundant UPDATEs is often the most direct way to reduce dead tuples and vacuum pressure.

### 23.9. Upsert Only When Values Differ

`INSERT ... ON CONFLICT DO UPDATE` can update existing rows even when new values match existing ones depending on the statement. Add `WHERE old.col IS DISTINCT FROM EXCLUDED.col` when appropriate to skip no-op updates.

### 23.10. Retention on Audit/Event Tables

Audit/event tables are usually append-heavy, yet can still see UPDATEs/DELETEs for status corrections or retention. Time-partitioning and dropping old partitions reduces churn, while checking compliance and historical query needs.

## 24. Tuning Autovacuum by Table Profile

There is no single parameter set for every table. Tune based on row count, update/delete rate, page count, vacuum duration, dead tuple trends, and I/O budget.

### 24.1. Large, High-Churn Tables

Example per-table tuning to trigger vacuum earlier:

~~~sql
ALTER TABLE public.orders
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.01,
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.005
);
~~~

A lower scale factor shrinks the proportional trigger; the absolute threshold prevents hyper-frequent vacuuming on tiny tables. These numbers are starting points to measure.

### 24.2. Small, Low-Churn Tables

Small tables rely mainly on relatively low absolute thresholds so they do not wait for huge percentages. Yet for tiny, rarely written tables, defaults are usually fine; do not tune just because a table "didn't vacuum today."

### 24.3. Append-Only Tables

Insert-only tables still need vacuuming to:

- Freeze tuples;
- Update the visibility map;
- Support index-only scans;
- Maintain vacuum XID age.

Review insert-triggered vacuum settings for your PostgreSQL version.

### 24.4. Hot-Update Tables Without Indexed Updated Columns

Monitor HOT ratio, fillfactor, and vacuum cadence. If HOT ratio is low due to full pages, test lowering fillfactor; if updated columns are indexed, evaluate index necessity first.

### 24.5. Tables with Many Indexes

Vacuum must clean up index references. Having many indexes raises maintenance cost; drop redundant indexes and evaluate `INDEX_CLEANUP` knowingly when appropriate.

### 24.6. Partitioned Tables

Autovacuum processes storage-bearing partitions as individual relations. A partitioned parent holds no heap tuples like a leaf partition; gathering ANALYZE statistics across parent/partition hierarchies may need manual runs depending on version/workload. Inspect large leaf partitions individually, not just the parent.

### 24.7. Global Worker/Cost Tuning

When many tables need vacuum simultaneously, review:

- `autovacuum_max_workers`;
- `autovacuum_naptime`;
- `autovacuum_vacuum_cost_limit`;
- `autovacuum_vacuum_cost_delay`;
- Disk throughput, CPU, and IOPS;
- Worker duration and pending table queue.

Raising workers/cost limits clears backlogs faster yet competes with foreground application I/O. Measure application latency and replication lag.

### 24.8. Logging Autovacuum

~~~sql
SHOW log_autovacuum_min_duration;
~~~

In authorized environments, log slow autovacuum runs to see which tables take long, how many tuples/pages were processed, and whether blockers caused skips. Protect logs, enforce retention, and avoid excessive logging under heavy load.

### 24.9. Monitoring After Tuning

After changing storage parameters:

1. Record before/after configuration;
2. Monitor autovacuum frequency and duration;
3. Monitor `n_dead_tup` and relation sizes;
4. Monitor HOT ratio;
5. Monitor query latency, I/O, and WAL;
6. Re-evaluate after a full workload cycle.

Do not declare tuning successful simply because dead tuples dipped for a few minutes without observing long-term bloat and latency.

## 25. Bloat, Backups, Replication, and Disk Capacity

### 25.1. Bloat Enlarges Backups

Physical backups copy relation files, so bloat inflates backup size, transfer time, and restore duration. Logical backups serialize rows and index definitions without preserving empty free pages like physical backups; impact varies by tool.

### 25.2. Rewrites Generate Extra I/O and WAL

VACUUM FULL, CLUSTER, REINDEX, and pg_repack read/write huge volumes of data, emit WAL, and can spike replication lag. On systems with standbys, monitor:

- WAL generation rate;
- Replication lag;
- Slot retention;
- Disk headroom on both primary and standbys;
- Backup/archiving backlog.

### 25.3. Plan Temporary Disk Space Ahead

During a rewrite, old and new relation copies coexist temporarily. During concurrent index rebuilds, old and new indexes coexist on disk. Never start when free filesystem space is less than the target relation's size.

### 25.4. Do Not Confuse OS Disk Free with Relation Free Space

`df`/disk monitoring shows filesystem capacity. `pgstattuple` shows tuple/free space inside a relation. Regular VACUUM raises reusable space without changing `df`; rewrites shrink relation size, yet filesystem free space only rises once file blocks are unlinked/returned.

### 25.5. Storage Snapshots and Copy-on-Write

Certain storage/volume snapshots retain old blocks after a rewrite until snapshots expire. Shrinking a relation does not always immediately reduce storage backend usage or billing. Check storage-layer semantics.

### 25.6. Replication Slots Can Grow Both WAL and Dead Tuples

Abandoned slots retain WAL, while a slot's `xmin`/`catalog_xmin` holds back the vacuum horizon. Evaluate both impacts rather than blindly deleting slots to free space.

## 26. Production Bloat Diagnostic Runbook

When a table/index grows or queries slow down, follow an ordered measurement and root-cause workflow before rewriting.

### Phase A — Identify Relation and Scope

Record:

1. Specific schema/table/index;
2. Total size and daily/weekly growth rate;
3. Whether heap, indexes, or TOAST dominate;
4. Estimated live/dead rows;
5. INSERT/UPDATE/DELETE workload;
6. Which queries slowed, scan types, and latency shifts;
7. PostgreSQL version, storage type, replication topology, and SLAs.

### Phase B — Targeted Deep Measurement

For suspect relations:

- Run `pgstattuple` or `pgstattuple_approx` on the heap;
- Run `pgstatindex` on B-tree indexes;
- Check relation size alongside indexes and TOAST;
- Record timestamps, queries, results, and concurrent workload.

Do not run full scans across all large tables simultaneously without an I/O budget.

### Phase C — Check VACUUM and Autovacuum

Inspect:

- `n_dead_tup`, `last_autovacuum`, `autovacuum_count`;
- Table storage parameters and autovacuum settings;
- `pg_stat_progress_vacuum`;
- Autovacuum logs;
- Long-running transactions, idle-in-transaction sessions, prepared transactions;
- Replication slot xmin/catalog_xmin and standby feedback.

### Phase D — Classify Root Cause

| Observation | Action Path |
| --- | --- |
| Many dead tuples, no recent vacuum | Check autovacuum thresholds/workers |
| Vacuum runs yet dead tuples stay | Find xmin horizon/long snapshots |
| Dead tuples drop, free space rises, size steady | Likely normal space-reuse state |
| High heap free space and disk must be returned | Evaluate VACUUM FULL/CLUSTER/pg_repack |
| Low B-tree density and abnormal index size | Check workload/fillfactor; consider REINDEX |
| GIN pending list/cleanup backlog | Check GIN settings, vacuum, and workload |
| Large TOAST footprint | Review large-value churn and retention |
| Bloat returns quickly | Fix schema, HOT eligibility, index churn, autovacuum |

### Phase E — Select Remediation and Assess Risk

Before executing:

- Lock type and DML blocking duration;
- Temporary disk needed for new relation/index;
- WAL generation, replication lag, and backup impact;
- Query latency during maintenance;
- Active transactions holding locks/snapshots;
- Rollback/recovery procedure;
- Operator staffing and monitoring coverage during execution.

### Phase F — Execute and Re-Measure

1. Capture baseline metrics;
2. Run the chosen regular VACUUM/REINDEX/rewrite;
3. Monitor progress, locks, I/O, WAL, and replication;
4. Re-measure relation/index sizes with identical functions;
5. Re-measure live/dead/free space and density;
6. Verify query plans and latency;
7. Document changes and watch whether bloat recurs.

### Phase G — Do Not Stop at Disk Numbers

A rewrite can shrink file size while query latency stays poor if the true bottleneck is a missing index, bad plan, network, CPU, or lock contention. Conversely, regular VACUUM can restore healthy reuse even when file size does not change. Measure both storage and behavior.

## 27. Easily Misdiagnosed Scenarios

### 27.1. Large File with Few Dead Tuples

Could be genuine live data, large indexes/TOAST, low fillfactor, or redundant indexes. Never run VACUUM FULL reflexively.

### 27.2. High Dead Tuples Yet VACUUM Does Not Shrink the File

Regular VACUUM focuses on reusing free space. If dead tuple count drops while file size holds steady, that is not necessarily a failure.

### 27.3. VACUUM Running Continuously

Could stem from high write rate, aggressive/mismatched scale factor, partitioned tables, low worker capacity, or heavy freeze/index cleanup work. Inspect trends and durations before adding workers.

### 27.4. Slow Queries After Bulk UPDATEs

May result from stale statistics, dead tuples, cache churn, or index churn. Run appropriate ANALYZE, inspect plans, vacuum, and check index state. Do not assume VACUUM FULL is the only answer.

### 27.5. Index Size Grows While Heap Size Stays Flat

Check updates to indexed columns, page splits, fillfactor, duplicate indexes, and index types. Reindex helps confirmed bloat, yet fix the write pattern to stop recurrence.

### 27.6. pg_stat_user_tables Shows Low n_dead_tup While Bloat Is High

Stats are estimates covering only dead tuples; the relation may still have low page density, large free space, or index bloat. Use pgstattuple/pgstatindex for deep checks.

### 27.7. pgstattuple Reports High free_percent

Free space may be actively reusable. If upcoming workloads insert/update the same relation, that room can be helpful. Rewrite only when there is a measured goal to return disk or improve locality.

### 27.8. REINDEX Finishes Yet Database Size Barely Drops

The rebuilt index may be smaller, yet the heap, other indexes, TOAST, WAL, temporary files, or storage snapshots still occupy disk. Measure the exact target relation and filesystem.

### 27.9. VACUUM FULL Fails to Run

Could be blocked by locks, run inside a transaction block, lack disk space, lack privileges, wrong relation type, or DDL conflicts. Read the exact error and resolve properly; never retry blindly in a loop creating a lock queue.

### 27.10. Autovacuum Freeze Is Not a Bloat Event

A table can be vacuumed for freezing even with few dead tuples. Never disable vacuum simply because dead tuple percentages look low.

## 28. Remediation Selection Checklist

| Condition | Preferred Approach | What to Avoid |
| --- | --- | --- |
| Dead tuples after UPDATE/DELETE | Regular VACUUM, autovacuum tuning | Immediate VACUUM FULL |
| Dead tuples pinned by old snapshot | Resolve transaction/slot horizon | Repeatedly running vacuum |
| Reusable free space | Monitor workload | Forcing every page compact |
| Heavy heap bloat needing shrinkage | VACUUM FULL/CLUSTER/pg_repack | Running unprepared at peak hours |
| Confirmed B-tree index bloat | REINDEX (CONCURRENTLY if suitable) | Blindly reindexing all indexes on schedule |
| Index churn from UPDATEs | HOT, fillfactor, index review | Rebuilding without fixing root cause |
| GIN pending list | GIN maintenance/settings | Using B-tree pgstatindex metrics |
| TOAST bloat | Vacuum/rewrite TOAST relation appropriately, review large-value churn | Measuring only main heap fork |
| Expired old partitions | Detach/drop partition if business permits | Deleting millions of rows unnecessarily |
| Wraparound risk | Anti-wraparound vacuum / DBA runbook | Raising freeze thresholds to hide warnings |

## 29. Useful Monitoring Queries

### 29.1. Top Relations by Size

~~~sql
SELECT
    c.oid::regclass AS relation,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    c.reltuples::bigint AS estimated_rows,
    c.relpages AS estimated_pages,
    c.reloptions
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm')
  AND c.relpersistence = 'p'
  AND c.relnamespace NOT IN (
      'pg_catalog'::regnamespace,
      'information_schema'::regnamespace
  )
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 50;
~~~

### 29.2. Top Dead Tuple Estimates

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
~~~

### 29.3. Top Long Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 30;
~~~

### 29.4. Active Vacuums

~~~sql
SELECT
    pid,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;
~~~

### 29.5. XID Age by Database

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    datfrozenxid
FROM pg_database
ORDER BY xid_age DESC;
~~~

These are metadata-reading monitoring queries; detailed visibility may depend on role privileges. Use dashboards/monitoring to retain historical trends rather than running queries manually only after disk fills up.

## 30. Practice Exercises — MVCC and Bloat Concepts

Exercises use the PostgreSQL lab database, schema `copy426`, and queries from this lesson. Some questions require reasoning rather than executing DDL. **Never run rewrite commands, DROP, or TRUNCATE in production solely for practice.**

### Exercise 1 — Defining Bloat

A table file is larger than its live data requires. Give at least four causes of relation growth and explain why large file size alone does not prove bloat.

### Exercise 2 — UPDATE Under MVCC

A row is UPDATED from `status='open'` to `status='paid'`.

**Question:** why does PostgreSQL create a new tuple version? Is the old version cleaned up immediately?

### Exercise 3 — DELETE Does Not Erase Bytes Immediately

DELETE 100,000 rows and commit. **Question:** why might the table file not shrink yet? What must VACUUM do next?

### Exercise 4 — Dead Tuples

Distinguish live tuples, dead tuples, tuple versions still needed by old snapshots, and free space after vacuum.

### Exercise 5 — Regular VACUUM

~~~sql
VACUUM public.orders;
~~~

**Question:** does this command rewrite the entire heap? What is its primary goal?

**Answer:** it does not rewrite the entire table; it cleans dead tuples and makes space reusable.

### Exercise 6 — VACUUM Does Not Shrink Files

After VACUUM, `n_dead_tup` drops sharply yet `pg_relation_size()` stays nearly unchanged.

**Question:** is this a failure? Explain reusable free space.

### Exercise 7 — Trailing Pages

Under what circumstances can regular VACUUM truncate empty pages at the end of a relation? Why is free space in the middle of a file normally not returned to the filesystem?

### Exercise 8 — VACUUM ANALYZE

Distinguish the effects of VACUUM and ANALYZE. Why do fresh statistics not clean dead tuples?

### Exercise 9 — VACUUM Inside a Transaction

~~~sql
BEGIN;
VACUUM public.orders;
COMMIT;
~~~

**Question:** why is this execution invalid? How should a migration tool that wraps statements in transactions be configured?

### Exercise 10 — Long-Running Snapshots

Transaction A opens a snapshot; Transaction B UPDATES/DELETES a row and commits; VACUUM runs while A remains open.

**Exercise:** explain why the old tuple cannot yet be reclaimed and what changes after A finishes.

### Exercise 11 — HOT Updates

A table has an index on `customer_id`, while UPDATE modifies only `note`.

**Question:** when can HOT occur? Why does it reduce index churn?

### Exercise 12 — Unsuccessful HOT

An UPDATE modifies a column covered by a B-tree index.

**Question:** why does HOT generally not apply for that index? How are new index entries generated?

### Exercise 13 — Fillfactor 100

A heap page is nearly full and an UPDATE needs to write a new tuple version.

**Exercise:** explain why insufficient free space causes HOT to fail even when no indexed column changed.

### Exercise 14 — Table Fillfactor 80

~~~sql
CREATE TABLE t (
    id bigint,
    status text
) WITH (fillfactor = 80);
~~~

**Question:** is 20% free an absolute guarantee for every page? Why is the table larger initially?

### Exercise 15 — ALTER TABLE SET fillfactor

~~~sql
ALTER TABLE t SET (fillfactor = 70);
~~~

**Question:** does this command rewrite all existing pages automatically? How can the new layout be applied to existing data?

### Exercise 16 — Index Fillfactor

Compare table fillfactor with B-tree index fillfactor. Which workloads does each help, and what are the storage trade-offs?

### Exercise 17 — HOT Ratio

~~~sql
SELECT n_tup_upd, n_tup_hot_upd
FROM pg_stat_user_tables
WHERE relname = 'orders';
~~~

**Question:** what causes a low HOT ratio? Is there one universal target across all tables?

### Exercise 18 — Heap Bloat vs. Index Bloat

A 2 GB heap table has 15 GB of indexes.

**Exercise:** determine what to measure before choosing between VACUUM FULL and REINDEX.

### Exercise 19 — TOAST

A table holds large JSONB documents, and `pg_total_relation_size` far exceeds `pg_relation_size`.

**Question:** why inspect the TOAST relation? What storage is omitted when looking only at heap size?

### Exercise 20 — Free Space Map

What role does the FSM play in locating pages with free room? Is it a file holding row data or a mechanism returning disk to the filesystem?

### Exercise 21 — Visibility Map

Explain how all-visible and all-frozen flags assist VACUUM and index-only scans.

### Exercise 22 — Page Fragmentation

A table has 30% free space, yet the upcoming workload will INSERT similar rows.

**Question:** why avoid rewriting by default to remove all free space?

### Exercise 23 — Index Page Splits

Describe why B-tree leaf pages split on insert. How do random keys and fillfactor influence splits?

### Exercise 24 — Redundant Indexes

A table has 12 indexes, 5 of which show no recorded usage.

**Exercise:** list checks required before dropping any index.

### Exercise 25 — No-Op UPDATE

~~~sql
UPDATE orders SET status = status;
~~~

**Question:** can this generate row churn? Write a predicate avoiding updates when values have not changed.

**Answer:** use `status IS DISTINCT FROM target_value` in the WHERE clause when appropriate.

### Exercise 26 — Excessively Low Fillfactor

An append-only table has fillfactor 50.

**Exercise:** analyze storage/scan overhead and why lower fillfactor is not automatically better.

### Exercise 27 — ETL Churn

An ETL job deletes all of yesterday's rows and re-inserts the same data.

**Question:** what costs does this create? How could partitioning, conditional upserts, or staging help?

### Exercise 28 — Oversized Data

Updating a 2 MB JSONB document across millions of rows.

**Exercise:** explain why TOAST churn and WAL can grow huge; propose splitting data or updating according to access patterns.

### Exercise 29 — Bloat or Real Growth?

A table grows from 5 GB to 12 GB after adding 20 million new rows.

**Question:** what evidence is needed before calling the 7 GB increase bloat?

### Exercise 30 — VACUUM and Transaction IDs

A table sees few DELETEs yet has a high XID age.

**Question:** why is VACUUM freeze still necessary? Is it safe to disable autovacuum just because dead tuples are low?

### Exercise 31 — pgstattuple

Run `pgstattuple('public.orders'::regclass)`.

**Exercise:** explain `tuple_percent`, `dead_tuple_percent`, and `free_percent`. Why not simply add the last two percentages and call that "exact bloat"?

### Exercise 32 — pgstattuple_approx

**Question:** why can `pgstattuple_approx` run faster than a full scan? What metadata does it leverage, and what is the nature of its output?

### Exercise 33 — pgstatindex

A B-tree index shows low `avg_leaf_density`.

**Exercise:** list at least four reasons density can be low and explain why knowing index fillfactor matters.

### Exercise 34 — Size Functions

Distinguish `pg_relation_size`, `pg_table_size`, `pg_indexes_size`, and `pg_total_relation_size`. Write a query for one table printing all four metrics.

### Exercise 35 — Largest Indexes

Use `pg_stat_user_indexes` and `pg_relation_size(indexrelid)` to list the 10 largest indexes.

**Question:** can you immediately DROP the first index in the list? Which checks are missing?

### Exercise 36 — TOAST Size

Write a query using `pg_class.reltoastrelid` to find the largest TOAST relations. Explain why checking only the main heap fork is insufficient.

### Exercise 37 — Autovacuum Threshold

Suppose a table has 50 million estimated tuples, vacuum threshold 1,000, and scale factor 0.01.

**Question:** what is the approximate UPDATE/DELETE trigger threshold per the formula? Why is this still only an estimation model?

**Answer:** roughly 501,000 tuple changes, depending on rules/estimates and version.

### Exercise 38 — Default Scale Factor

A 100-million-row table uses scale factor 0.2.

**Exercise:** explain why waiting for roughly 20 million changes can be too late on a heavy workload.

### Exercise 39 — Insert-Triggered Vacuum

An append-only event table sees virtually no UPDATE/DELETE.

**Question:** why is insert/freeze vacuum still needed? Name the relevant insert-triggered settings by version.

### Exercise 40 — Autovacuum Workers

A server has 10 large tables needing vacuum simultaneously, yet only 3 workers.

**Exercise:** list metrics to inspect before increasing workers and explain why an I/O bottleneck can prevent extra workers from helping.

### Exercise 41 — Long Transactions

A session stays `idle in transaction` for 4 hours.

**Question:** how can it pin a snapshot and block vacuum from reclaiming dead tuples? Outline how to investigate.

### Exercise 42 — Replication Slots

A logical replication slot has been inactive for days with an old xmin/catalog_xmin.

**Exercise:** analyze its impact on WAL and the vacuum horizon; explain why the slot must not be dropped before verifying the subscriber.

### Exercise 43 — hot_standby_feedback

**Question:** what does feedback from a standby help avoid? What dead-tuple trade-off can the primary experience?

### Exercise 44 — pg_stat_progress_vacuum

**Exercise:** write a query retrieving relation, phase, and heap_blks_total/scanned/vacuumed. Explain why the ratio of scanned blocks is not the percentage of bloat removed.

### Exercise 45 — REINDEX CONCURRENTLY

**Question:** what is the main advantage over regular REINDEX? Which stages still involve locks, temporary disk, and transaction waits?

### Exercise 46 — VACUUM FULL

A 200 GB table needs shrinking, yet only 40 GB of free disk space remains.

**Exercise:** analyze why running VACUUM FULL can fail or disrupt service; what disk/lock/backup preparations are needed?

### Exercise 47 — CLUSTER

A time-series table is routinely queried over contiguous date ranges.

**Question:** when can CLUSTER on a timestamp index improve locality? Why does physical order drift as new writes arrive?

### Exercise 48 — pg_repack

**Exercise:** list prerequisites, lock phases, disk headroom needs, and the difference between "less blocking" and "zero-lock."

### Exercise 49 — Partition Retention

A log table partitioned by month needs data older than 24 months purged.

**Exercise:** compare deleting millions of rows against detaching/dropping partitions. List FK, audit, replication, backup, and legal retention checks.

### Exercise 50 — Capstone: Bloated Orders Table

A system has a 300 GB `orders` table with 6 indexes, status updated multiple times per day, autovacuum running continuously, and high fluctuating dead tuple estimates. A long-running reporting transaction and a logical replication slot are also present.

**Deliverables:**

1. Diagram the heap, indexes, TOAST, and relevant transaction horizons.
2. Write queries measuring total size, heap/index sizes, dead tuple estimates, vacuum activity, and HOT ratio.
3. Choose a deep measurement approach with pgstattuple/pgstatindex and explain its cost.
4. Investigate the reporting transaction and replication slot before running more VACUUM.
5. Calculate current autovacuum thresholds and propose justified per-table settings.
6. Audit indexes on frequently updated columns; identify HOT opportunities.
7. Propose table/index fillfactor settings and explain trade-offs.
8. State when regular VACUUM suffices and when REINDEX is required.
9. Evaluate VACUUM FULL, CLUSTER, or pg_repack against lock/disk/WAL/SLAs.
10. Design a before/after measurement plan covering replication lag, query latency, and disk recovery.
11. Propose preventive fixes: update predicates, retention, partitioning, and index cleanup.
12. Write an incident/rollback runbook if a rewrite stalls or disk pressure spikes.

**Passing criteria:** never pick a command solely because it "shrinks the file." You must demonstrate **where bloat resides, why it formed, whether vacuum can clean it, and the cost/locking of the chosen remediation**.

## 31. Routine Maintenance Checklist

### 31.1. Size Monitoring

- [ ] Track total size of large tables over time.
- [ ] Separate heap, indexes, and TOAST.
- [ ] Track size growth relative to live row counts and business data.
- [ ] Track the largest indexes and their business justification.
- [ ] Never treat relation size alone as proof of bloat.

### 31.2. MVCC and VACUUM Monitoring

- [ ] Monitor n_live_tup/n_dead_tup while understanding they are estimates.
- [ ] Track last_autovacuum, autovacuum_count, and vacuum durations.
- [ ] Monitor pg_stat_progress_vacuum during large vacuum runs.
- [ ] Check for long-running transactions and idle-in-transaction sessions.
- [ ] Check replication slots, xmin/catalog_xmin, and standby feedback.
- [ ] Check for orphaned prepared transactions.
- [ ] Never disable autovacuum as a permanent configuration.
- [ ] Monitor XID age and anti-wraparound vacuum activity.

### 31.3. HOT and Index Monitoring

- [ ] Monitor HOT update ratio.
- [ ] Audit indexes on frequently updated columns.
- [ ] Evaluate table/index fillfactor against workload.
- [ ] Review index usage over sufficiently long cycles.
- [ ] Never DROP indexes solely for low idx_scan over a short window.
- [ ] Use access-method-appropriate metrics; pgstatindex is B-tree only.
- [ ] Monitor GIN pending list/maintenance when using GIN.

### 31.4. Remediation Selection

- [ ] Run regular VACUUM before considering rewrites if reclaimable dead tuples exist.
- [ ] Run VACUUM FULL only when shrinkage is required and lock/disk windows exist.
- [ ] Run CLUSTER only when physical ordering delivers measurable query gains.
- [ ] REINDEX only indexes confirmed to have issues.
- [ ] Use REINDEX CONCURRENTLY when version and workload permit.
- [ ] Evaluate pg_repack against prerequisites, locks, disk, and WAL.
- [ ] Never schedule full-relation rewrites without measurement evidence.

### 31.5. Operational Safety

- [ ] Capture baseline sizes, dead/free space, and query latency.
- [ ] Verify sufficient temporary disk and filesystem headroom.
- [ ] Verify WAL, archiving, and replication capacity.
- [ ] Inspect active locks and running transactions.
- [ ] Prepare maintenance/rollback plans and active operator oversight.
- [ ] Re-measure using identical tools/methodology after remediation.
- [ ] Watch for bloat recurrence and address root causes.

## 32. Frequently Asked Questions

### 32.1. Does VACUUM Delete Dead Tuples?

Yes, when tuple versions are no longer needed by any active transaction snapshots. VACUUM makes space reusable; it does not necessarily rewrite the relation or shrink the file.

### 32.2. Why Didn't the File Shrink After VACUUM?

Free space may sit in the middle of the relation and be retained for reuse. Only qualifying trailing empty pages can be truncated in certain cases. To rewrite the entire heap, look to VACUUM FULL/CLUSTER/pg_repack.

### 32.3. Is VACUUM FULL Safe?

It is a valid operation, yet takes an ACCESS EXCLUSIVE lock, temporary disk space, and heavy I/O. Plan it carefully for production tables; never run it casually during peak hours.

### 32.4. Should VACUUM FULL Run Nightly?

Normally no. Autovacuum and regular VACUUM handle routine maintenance; heavy rewrites require confirmed bloat and an explicit disk-reclamation goal.

### 32.5. Does a High Dead Tuple Percentage Mean VACUUM FULL Is Needed?

No. Regular VACUUM can clean dead tuples and make space reusable. Choose a rewrite only if physical bloat remains severe and the relation must shrink.

### 32.6. Does REINDEX Shrink the Table Heap?

No. REINDEX rebuilds indexes. Heap bloat requires vacuuming or rewriting the table as appropriate.

### 32.7. Is REINDEX CONCURRENTLY Lock-Free?

No. It avoids blocking DML for most of the build, yet still acquires brief locks, waits on transactions, uses temporary disk, and generates WAL.

### 32.8. Does Low Fillfactor Increase Bloat?

It makes relations/indexes slightly larger initially because space is intentionally reserved. Yet for update-heavy or random-insert workloads, that headroom cuts HOT failures and page splits. Weigh the trade-off per workload.

### 32.9. Do HOT Updates Prevent Dead Tuples?

No. HOT still creates a new tuple version in the heap, while avoiding new index entries. VACUUM is still required for cleanup.

### 32.10. Why Do Long Transactions Cause Bloat?

They pin an old snapshot, blocking VACUUM from cleaning older tuple versions. Locate long transactions and fix their lifecycle before running more vacuums.

### 32.11. Do Replication Slots Affect Bloat?

Yes. Slots holding xmin/catalog_xmin pin the vacuum horizon; slots also retain WAL. Never delete slots before verifying consumer state and recovery plans.

### 32.12. Is pgstattuple Exact?

`pgstattuple` scans the relation to measure live/dead/free space at execution time, yet results must still be interpreted alongside page layout, concurrency, and reclamation goals. `pgstattuple_approx` runs faster in many cases, returning estimates.

### 32.13. Can pgstatindex Measure GIN?

No. `pgstatindex` is for B-tree indexes. Use metrics/tools suited to GIN, GiST, BRIN, or hash.

### 32.14. Does n_dead_tup = 0 Prove There Is No Bloat?

No. It is an estimate of dead tuples and does not fully reflect sparse page density, index bloat, or TOAST. A relation can still be sparse or hold abundant free space.

### 32.15. Why Doesn't Autovacuum Run Immediately After DELETE?

It triggers based on thresholds/scale factors, worker availability, cost limits, and transaction horizons. Committing a DELETE does not immediately launch autovacuum.

### 32.16. Should autovacuum_max_workers Be Set Very High?

Not by default. More workers can amplify I/O contention. Measure vacuum backlog, worker duration, storage throughput, and application latency first.

### 32.17. Is TRUNCATE a Bloat Cure?

Only when business logic truly intends to delete every row and accepts lock, FK, and trigger semantics. Never use TRUNCATE when live rows must stay.

### 32.18. Does Bloat Always Slow Down Queries?

Not always. Impact depends on query access patterns, caching, scan types, and where bloat sits. Measure query latency/plans and I/O rather than guessing from disk size.

### 32.19. Does pg_repack Replace Autovacuum?

No. pg_repack is a rewrite/rebuild tool; autovacuum remains essential for ongoing MVCC cleanup and freezing.

### 32.20. How Do You Know If Bloat Returned?

Track trends in sizes, live/dead/free space, index density, HOT ratio, vacuum cadence, and write workloads over consistent windows. A single snapshot is insufficient.

## 33. Official PostgreSQL Documentation

The links below point to current PostgreSQL documentation. When operating systems, select the **exact major version** of your server because autovacuum settings, REINDEX CONCURRENTLY, progress views, and options evolve across releases:

- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): MVCC cleanup, VACUUM, ANALYZE, autovacuum, and wraparound.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): FULL, FREEZE, VERBOSE, INDEX_CLEANUP, and TRUNCATE options.
- [Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html): thresholds, scale factors, workers, and cost settings.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html): index rebuilds, CONCURRENTLY, and lock/transaction restrictions.
- [CLUSTER](https://www.postgresql.org/docs/current/sql-cluster.html): rewriting tables by index and storage parameters.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html): pgstattuple, pgstattuple_approx, and pgstatindex.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_user_tables, pg_stat_user_indexes, pg_stat_activity, and replication stats.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): pg_stat_progress_vacuum and progress views.
- [Storage Page Layout](https://www.postgresql.org/docs/current/storage-page-layout.html): heap pages, tuple headers, line pointers, and free space.
- [Heap-Only Tuples (HOT)](https://www.postgresql.org/docs/current/storage-hot.html): HOT updates and eligibility conditions.
- [CREATE TABLE Storage Parameters](https://www.postgresql.org/docs/current/sql-createtable.html#SQL-CREATETABLE-STORAGE-PARAMETERS): table fillfactor and storage options.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index fillfactor and index options.
- [System Catalog pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html): relpages, reltuples, reloptions, and TOAST relation.
- [System Catalog pg_stat_all_tables](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ALL-TABLES-VIEW): table activity counters.
- [System Catalog pg_stat_progress_vacuum](https://www.postgresql.org/docs/current/progress-reporting.html#VACUUM-PROGRESS-REPORTING): vacuum progress.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html): replication slots and hot_standby_feedback.
- [Routine Reindexing](https://www.postgresql.org/docs/current/routine-reindex.html): when and how to reindex.
- [pg_repack project](https://github.com/reorg/pg_repack): external extension/tool to rewrite relations with shorter blocking under suitable conditions.

## 34. Summary

**Table and index bloat** arises from the interplay among MVCC row versions, dead tuples, free space, page layout, index churn, TOAST, and vacuuming. PostgreSQL keeps old versions while snapshots still need them; VACUUM cleans eligible versions and makes space reusable.

| Tool | Primary Goal | Rewrites? | Key Caveats |
| --- | --- | --- | --- |
| VACUUM | Clean dead tuples, freeze, reuse space | No full heap rewrite | Files usually do not shrink significantly |
| VACUUM ANALYZE | Cleanup + update planner statistics | No full heap rewrite | ANALYZE does not replace VACUUM |
| VACUUM FULL | Reclaim heap bloat via rewrite | Yes | ACCESS EXCLUSIVE lock, temporary disk |
| CLUSTER | Rewrite heap in index order | Yes | Strong lock; physical order drifts with DML |
| REINDEX | Rebuild indexes | Yes, for index | Does not fix heap bloat |
| REINDEX CONCURRENTLY | Rebuild indexes with less DML blocking | Yes, for index | Still has lock phases, temp disk/WAL, and waits |
| pg_repack | Rewrite table/index with shorter block window | Yes | External tool, prerequisites, and disk headroom |

To control bloat sustainably:

1. Track table/index/TOAST sizes alongside live/dead/free estimates;
2. Keep autovacuum active and tuned to table scale and churn rate;
3. Hunt down long transactions, replication slots, and pinned snapshot horizons;
4. Design indexes and fillfactor to curb churn and promote HOT where appropriate;
5. Avoid no-op UPDATEs and row-by-row retention DELETEs;
6. Measure deeply with pgstattuple/pgstatindex selectively;
7. Match VACUUM, REINDEX, or rewrites to the exact type of bloat;
8. Measure before and after across disk, query latency, WAL, and replication.

**Not every byte of free space is waste, and not every large relation is bloated.** A healthy system cleans dead tuples promptly, reuses free space effectively, keeps indexes aligned with workloads, and rewrites only when reclamation/performance gains outweigh lock, I/O, and temporary disk costs.
