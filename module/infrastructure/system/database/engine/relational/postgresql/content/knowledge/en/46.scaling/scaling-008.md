# amcheck, pageinspect, pg_buffercache, and Internal Inspection Tools in PostgreSQL

PostgreSQL provides numerous tools to inspect internal database state when investigating indexes, heap pages, the buffer cache, dead tuples, the visibility map, WAL, and query activity. These tools are invaluable for deep operational diagnostics, yet they are not interchangeable.

- **amcheck** verifies specific structural consistency invariants of indexes and heaps.
- **pageinspect** reads the physical layout of pages and tuples for detailed forensic investigation.
- **pg_buffercache** observes which pages currently reside in the shared buffer cache at query time.
- Extensions and utilities such as **pgstattuple**, **pg_freespacemap**, **pg_visibility**, **pg_walinspect**, **pg_stat_statements**, **pg_stat_io**, **pg_amcheck**, **pg_checksums**, and **pg_verifybackup** add visibility into storage, tuple visibility, WAL, workload, and backups.

These are often called internal inspection tools because they let administrators look deeper into how PostgreSQL stores and processes data. Some operations are read-only yet still impose significant I/O and CPU load; others require elevated privileges and can expose sensitive data. Always define the goal, scope, permissions, timing, and evidence retention before running them.

~~~mermaid
flowchart TD
    A["Investigation question"] --> B{"What needs verification?"}
    B -->|"Index/heap consistency"| C["amcheck / pg_amcheck"]
    B -->|"Page and tuple layout"| D["pageinspect"]
    B -->|"Pages in shared buffers"| E["pg_buffercache"]
    B -->|"Dead tuples / free space"| F["pgstattuple / pg_freespacemap"]
    B -->|"Visibility map"| G["pg_visibility"]
    B -->|"WAL records"| H["pg_walinspect / pg_waldump"]
    B -->|"Query workload"| I["pg_stat_statements / pg_stat_io"]
    C --> J["Correlate logs, catalogs, backups"]
    D --> J
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
~~~

This lesson belongs to the **Scaling** chapter of the **Database Engine Relational PostgreSQL** module. It focuses on installing, using, interpreting, and safely operating internal inspection tools.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the roles and limits of `amcheck`, `pageinspect`, and `pg_buffercache`.
2. Check extension availability and install extensions in the right database.
3. Identify required privileges and apply least privilege.
4. Use `amcheck` to check B-tree indexes and supported heap consistency checks.
5. Use `pg_amcheck` to automate checks across multiple objects and databases.
6. Use `pageinspect` to read page headers, heap tuples, and B-tree pages.
7. Understand why `pageinspect` is a forensic tool rather than a repair tool.
8. Use `pg_buffercache` to inspect page residency, dirty buffers, and usage counts.
9. Read `pgstattuple`, `pg_freespacemap`, and `pg_visibility`.
10. Use `pg_walinspect` and `pg_waldump` to inspect WAL.
11. Combine `pg_stat_statements`, `pg_stat_io`, and statistics views.
12. Distinguish corruption evidence from unusual query plans or cache behavior.
13. Establish an inspection workflow with bounded scope, evidence capture, and stop conditions.
14. Avoid running heavy checks indiscriminately or granting unnecessary superuser privileges.
15. Know when to halt writes, create backups/clones, and escalate.

## 2. What Are Internal Extensions and Utilities?

PostgreSQL ships several extensions in its source/contrib tree or companion packages, though their availability depends on installation method, distribution, and version.

An extension may provide SQL functions, views, operators, types, shared libraries, background workers, or catalog objects. Installing an extension in one database does not automatically install it across every database in the cluster. Shared libraries are installed at the server level, whereas extension SQL objects are created per database.

### Checking Available Extensions

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
WHERE name IN (
    'amcheck',
    'pageinspect',
    'pg_buffercache',
    'pgstattuple',
    'pg_freespacemap',
    'pg_visibility',
    'pg_walinspect',
    'pg_stat_statements'
)
ORDER BY name;
~~~

Interpretation:

- Row present in `pg_available_extensions`: the server found the extension control files and knows an installable version.
- `installed_version` is non-`NULL`: the extension has already been created in the current database.
- No row returned: the package may be missing, the extension may not be built for the platform/version, or the server cannot locate the extension files.

### Installing Extensions

Examples:

~~~sql
CREATE EXTENSION amcheck;
CREATE EXTENSION pageinspect;
CREATE EXTENSION pg_buffercache;
~~~

You can use `IF NOT EXISTS` if the goal is to create it only when absent:

~~~sql
CREATE EXTENSION IF NOT EXISTS amcheck;
~~~

`IF NOT EXISTS` does not verify that an existing extension matches the expected version or schema. Re-check metadata after installation:

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema,
    pg_get_userbyid(extowner) AS extension_owner
FROM pg_extension
WHERE extname IN ('amcheck', 'pageinspect', 'pg_buffercache')
ORDER BY extname;
~~~

Some extensions require an OS package before `CREATE EXTENSION` works. On Debian/Ubuntu, for example, contrib packages may be distributed per major version; exact package names depend on repository and distribution. On managed databases, providers may restrict the list of supported extensions.

Never install packages or restart the database without an approved platform and change plan.

## 3. Choosing the Tool for the Question

| Question | Appropriate tool | Primary output |
| --- | --- | --- |
| Does a B-tree index show structural inconsistencies? | `amcheck`, `pg_amcheck` | Index check error reports |
| Does a heap page have tool-detectable structural errors? | `amcheck` `verify_heapam` on supported versions | Detected heap errors |
| What headers/tuples are inside a page? | `pageinspect` | Raw page and decoded fields |
| Are a relation's pages currently in shared buffers? | `pg_buffercache` | Buffer residency snapshot |
| How many dead tuples/free space does a table have? | `pgstattuple` | Tuple/dead/free-space statistics |
| What does the free space map record? | `pg_freespacemap` | Free space per heap block |
| Are pages marked all-visible/all-frozen? | `pg_visibility` | Visibility map state |
| What records are in a WAL range? | `pg_walinspect`, `pg_waldump` | WAL record metadata/details |
| Which queries consume buffers/time/temp I/O? | `pg_stat_statements` | Query-level accumulated statistics |
| Which backends generate I/O? | `pg_stat_io` | I/O counters by backend/object/context |
| Do backup files match the manifest? | `pg_verifybackup` | Backup validation result |
| Are cluster checksums intact? | `pg_checksums` | Checksum verification |
| What is the backup/cluster metadata? | `pg_controldata` | Control file information |

Each tool answers only part of the picture. For instance, `amcheck` does not validate all business data, `pg_buffercache` does not directly measure disk latency, and `pageinspect` does not repair damaged pages.

## 4. Access Privileges and Safety

Internal inspection extensions can read raw database pages, WAL metadata, query text, or cross-database information. Default permissions vary by extension and major version.

Principles:

- Use a dedicated DBA/diagnostic role.
- Grant only the privileges needed for each tool.
- Never grant `SUPERUSER` to application roles.
- Never leave `EXECUTE` open to `PUBLIC` on sensitive functions without reason.
- Never store query text or tuple data containing PII in unprotected evidence repositories.
- Test on staging or a clone before running heavy checks.
- Record the database, relation, index, block range, and timestamp.
- Monitor I/O, CPU, lock waits, and application latency during inspection.

### Checking Extension Privileges

Inspect extension functions:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_get_userbyid(p.proowner) AS function_owner,
    p.proacl
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname IN (
    'public',
    'amcheck',
    'pageinspect',
    'pg_buffercache'
)
ORDER BY n.nspname, p.proname;
~~~

An extension's schema may be different from `public`. Use `pg_extension` to identify the actual schema.

Some `pageinspect` functions and raw-storage inspection tools are restricted to superusers or specifically granted roles. Never assume every extension shares the same policy. Read the Privileges section in the documentation for your exact version and inspect current ACLs.

### Separate Inspection Privileges from Repair Privileges

The tools discussed here are primarily for inspection. When corruption is detected, remediation may involve restore, `REINDEX`, object rebuilds, failover, or point-in-time recovery. That is a separate change/incident workflow with approvals and a recovery plan—not an automatic follow-up to an inspection query.

## 5. What Is amcheck?

`amcheck` is an extension providing functions that check specific structural consistency invariants in PostgreSQL. Its primary focus is B-tree indexes, and supported versions also provide heap checking.

`amcheck` is useful when:

- Index corruption is suspected.
- Storage or controllers experienced errors or abnormal resets.
- Server logs record page, checksum, or index errors.
- Queries return inconsistent results and application bugs have been ruled out.
- Periodic checks are mandated by policy.
- Post-incident or post-restore verification is needed.

`amcheck` is not a general-purpose verifier proving all business data is valid. It validates the structural invariants recognized by its functions.

### Installing amcheck

In the database to be checked:

~~~sql
CREATE EXTENSION IF NOT EXISTS amcheck;
~~~

Verify:

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'amcheck';
~~~

## 6. Checking B-Trees with bt_index_check

`bt_index_check` verifies structural consistency of a B-tree index within the function's and version's scope.

Example:

~~~sql
SELECT bt_index_check('public.orders_pkey'::regclass);
~~~

If the function completes without error, the performed checks succeeded. That does not prove every conceivable form of corruption is absent.

### Strengths and Limitations

- Lighter-weight than parent checks in many scenarios.
- Can run during online workloads per the version's locking/visibility semantics.
- Does not replace business-data validation.
- Check thoroughness depends on parameters and index kind.
- Not all access methods are supported like B-tree.

Never interpret a clean run as "the entire database is guaranteed corruption-free."

## 7. Deeper Checks with bt_index_parent_check

Example:

~~~sql
SELECT bt_index_parent_check('public.orders_pkey'::regclass);
~~~

Parent checking verifies additional parent/child page relationships and B-tree invariants. Some versions offer options such as `heapallindexed` or `rootdescend`; check exact signatures and semantics for your version.

Deeper checks may acquire stronger locks or reduce concurrent write throughput on the checked relation. Therefore:

- Assess table size and workload.
- Run outside peak windows where appropriate.
- Monitor lock waits and latency.
- Never run across all large indexes simultaneously without measuring impact.
- Use `pg_amcheck` with bounded job concurrency.

### heapallindexed

On supported versions, `heapallindexed` checks deeper consistency between heap tuples and index entries. This can consume considerable resources because much more data is scanned.

Never enable every deep-check option on every scheduled run without evaluating its cost.

## 8. Checking Heaps with verify_heapam

Supported versions of `amcheck` include `verify_heapam` to detect certain structural errors in heap pages and tuples.

Example on supported versions:

~~~sql
SELECT *
FROM verify_heapam('public.orders'::regclass);
~~~

Output can include block number, tuple offset, attribute number, and error messages depending on version.

Keep in mind:

- Verify the function exists and confirm its signature on the target server.
- Bound the scope; checking huge heaps generates substantial I/O.
- Some reported errors involve TOAST data or visibility state.
- Never attempt manual tuple edits based on output.
- Save raw results and server logs for DBA/storage specialist analysis.

If the function does not exist, check your `amcheck` version and PostgreSQL major version; never fabricate a replacement function from another version's example.

## 9. pg_amcheck: Command-Line Utility

`pg_amcheck` is a command-line utility for running `amcheck` checks across one or more databases/objects. Introduced in PostgreSQL 14, its flags and support vary by version.

Example checking one database:

~~~bash
pg_amcheck --database=appdb --verbose
~~~

Example enabling parent checks:

~~~bash
pg_amcheck --database=appdb --parent-check --verbose
~~~

Example running with bounded jobs:

~~~bash
pg_amcheck --database=appdb --jobs=2 --verbose
~~~

Exact syntax depends on the `pg_amcheck` version. Check `--help` on the installed binary:

~~~bash
pg_amcheck --help
~~~

### Common Options

- Target a specific database, table, or index.
- Scan multiple databases per policy.
- Enable parent checks.
- Enable `heapallindexed` on supported versions.
- Limit parallel jobs.
- Display progress/verbose output.
- Exclude objects or schemas intentionally.

Never invoke cluster-wide options without understanding relation counts and I/O cost. Before running, record the list of target objects and define how failures will be handled.

### Exit Status and Output

- A zero exit code means only that executed checks completed without errors.
- Any non-zero exit code requires reading stderr/stdout to identify the failing object and error class.
- Some objects may be skipped due to permissions or unsupported index types.
- Output does not replace checksum verification, backup validation, or application checks.

## 10. Workflow When amcheck Reports an Error

If `amcheck` reports an error:

1. Pause further scheduled checks on the same scope if needed to avoid extra load.
2. Save the exact output, SQLSTATE/message, timestamp, and version.
3. Identify the exact index, table, and database.
4. Inspect server logs, OS logs, storage telemetry, and checksum status.
5. Check whether the error reproduces on the same block or object.
6. Verify the latest backup and PITR readiness.
7. Assess whether writes must be halted or incident mode activated.
8. Select an approved recovery approach.
9. After recovery, re-run checks and application/data validation.

Never run `REINDEX` or `DROP INDEX` reflexively on every `amcheck` error. Determine the error class and preserve evidence before modifying objects.

### Corruption Is Not Always Limited to the Index

If only an index is corrupted, rebuilding the index may recover it in some situations. However, if heap pages or underlying storage are corrupted, rebuilding the index will not recover lost heap data. Restore/PITR or specialist PostgreSQL/storage evaluation may be required.

## 11. What Is pageinspect?

`pageinspect` provides functions to inspect the raw contents and physical layout of database pages. It serves deep investigations, PostgreSQL internals study, and verifying specific hypotheses.

You can inspect:

- Page headers.
- Heap line pointers and tuple metadata.
- B-tree metapages.
- B-tree page statistics and items.
- BRIN/GiST page structures on supported versions.
- Additional raw page details depending on version.

`pageinspect` is not a general consistency checker. It decodes page fields; the operator must understand the physical structures and interpret fields for the running version.

### Installing pageinspect

~~~sql
CREATE EXTENSION IF NOT EXISTS pageinspect;
~~~

Verify:

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'pageinspect';
~~~

## 12. Reading Raw Pages with get_raw_page

Example reading block 0 of a heap relation:

~~~sql
SELECT get_raw_page('public.orders', 0);
~~~

The function returns the page as `bytea`. It is normally passed to decoder functions rather than inspected as raw binary.

You can specify a fork:

~~~sql
SELECT get_raw_page('public.orders', 'main', 0);
~~~

Common forks:

- `main`: heap/index data pages.
- `fsm`: free space map.
- `vm`: visibility map.
- `init`: initialization fork, mainly for unlogged relations.

Not every relation has every fork. The block number must lie within the existing range for that relation/fork. Under concurrent writes, the result is a point-in-time read snapshot, not a consistent snapshot across multiple commands.

## 13. Reading Page Headers

Example:

~~~sql
SELECT *
FROM page_header(get_raw_page('public.orders', 0));
~~~

The page header exposes physical fields such as:

- LSN: WAL position associated with the page.
- Checksum field per page format.
- Flags: page state and attributes.
- Lower, upper, special: region boundary offsets within the page.
- Page size and layout version.
- Prune XID: pruning-related metadata.

Exact semantics and decoding depend on PostgreSQL version and page type. Never conclude page corruption solely because one field differs from expectations without checking page type, version, and state.

### General Page Layout

~~~text
+--------------------------------------+
| Page Header                          |
+--------------------------------------+
| Line Pointer Array                   |
|  ItemId 1 | ItemId 2 | ...            |
+--------------------------------------+
|                                      |
| Free Space                           |
|                                      |
+--------------------------------------+
| Tuple / Index Tuple Data             |
| grows from the end toward the front  |
+--------------------------------------+
| Special Space (for some page types)  |
+--------------------------------------+
~~~

A heap page typically contains a header, line pointer array, free space, and tuple data. Index pages have their own layout and may use special space for access method metadata.

## 14. Reading Heap Tuples with heap_page_items

Example:

~~~sql
SELECT *
FROM heap_page_items(
    get_raw_page('public.orders', 'main', 0)
);
~~~

Output typically includes:

- `lp`: line pointer number.
- `lp_off`, `lp_flags`, `lp_len`: line pointer offset, state, and length.
- `t_xmin`, `t_xmax`: transaction IDs associated with tuple creation/deletion.
- `t_ctid`: tuple identifier.
- `t_infomask`, `t_infomask2`: internal flags.
- `t_hoff`: offset where tuple header ends / data begins.
- `t_bits`: null bitmap when present.
- `t_data`: raw tuple data.

These are low-level physical fields. Never conclude a row is deleted from `t_xmax` alone; MVCC visibility also depends on transaction status, hint bits, snapshots, and tuple state.

### Line Pointers

A line pointer can represent:

- A tuple stored at an offset.
- A redirect pointer.
- A dead item.
- An unused item.

Not every line pointer holds a live tuple. A heap page can contain dead tuples awaiting vacuum or tuple versions retained by an older transaction horizon.

### Reading Tuple Data

`pageinspect` does not always decode `t_data` into readable SQL columns. Decoding depends on tuple descriptors, attribute layout, alignment, null bitmaps, TOAST, and version. Use normal SQL queries to read business values; use `pageinspect` when investigating physical layout.

## 15. Reading B-Tree Metapages and Page Stats

A B-tree index has a metapage holding index metadata.

Example:

~~~sql
SELECT *
FROM bt_metap('public.orders_created_at_idx');
~~~

Information can include:

- Root block.
- Tree level.
- Fast root / fast level.
- Version / meta flags.
- Version-specific B-tree fields.

Inspect page statistics:

~~~sql
SELECT *
FROM bt_page_stats('public.orders_created_at_idx', 1);
~~~

Block 1 is merely an example; verify valid block numbers and page types. The metapage normally resides at block 0, while subsequent blocks may be internal, leaf, or other pages.

### Reading B-Tree Items

~~~sql
SELECT *
FROM bt_page_items(
    'public.orders_created_at_idx',
    1
);
~~~

Returned columns depend on version, typically including item offset, `ctid`, item length, data bytes, dead/metadata flags, and tuple/index-specific fields.

Never interpret `dead` or `htid` columns in isolation from version and function semantics. Use `pg_amcheck` to check invariants and `pageinspect` to examine specific pages.

## 16. pageinspect and Forensic Workflows

When suspecting an issue on a specific block:

1. Identify the relation and fork.
2. Check relation size and block range.
3. Capture the page header.
4. Capture line pointer and tuple metadata.
5. Read B-tree metapage/page stats if inspecting an index.
6. Correlate with `amcheck` results.
7. Correlate with server logs and checksums.
8. Check whether the block is changing during inspection.
9. Preserve evidence before `REINDEX` or restore.
10. Escalate to DBA/storage specialists if corruption evidence appears.

Raw page data may contain sensitive information. Restrict read access and never paste raw tuple/byte dumps into public tickets.

## 17. What Is pg_buffercache?

`pg_buffercache` inspects the buffers currently residing in PostgreSQL's shared buffer cache at the moment of the query. It answers: which pages are cached in shared buffers, which database/relation/fork they belong to, and their dirty/usage state.

It is not a physical disk I/O profiler. A page absent from shared buffers may still reside in the OS page cache. Conversely, a page present in shared buffers may have been read from storage long ago.

### Installation

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_buffercache;
~~~

Verify:

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'pg_buffercache';
~~~

### Count Buffer Entries

~~~sql
SELECT count(*) AS buffer_entries
FROM pg_buffercache;
~~~

### Buffer Distribution by Database

~~~sql
SELECT
    CASE
        WHEN reldatabase IS NULL THEN 'shared/system'
        ELSE COALESCE(d.datname, 'unknown database')
    END AS database_scope,
    count(*) AS buffers,
    count(*) FILTER (WHERE isdirty) AS dirty_buffers
FROM pg_buffercache AS b
LEFT JOIN pg_database AS d
    ON d.oid = b.reldatabase
GROUP BY 1
ORDER BY buffers DESC;
~~~

The view can contain entries that do not map to ordinary databases or relations. Do not assume every row belongs to a user table.

## 18. Reading pg_buffercache Columns

Key columns:

- `bufferid`: buffer ID in the shared buffer pool.
- `relfilenode`: relation's filenode.
- `reltablespace`: tablespace OID.
- `reldatabase`: database OID; may be `NULL` for shared relations.
- `relforknumber`: main/FSM/VM/init fork.
- `relblocknumber`: block number.
- `isdirty`: whether the buffer is dirty.
- `usagecount`: usage count in the clock-sweep buffer replacement algorithm.
- `pinning_backends`: number of backends currently pinning the buffer per version semantics.

`usagecount` is not a hit counter and does not directly measure query access frequency. `isdirty` does not necessarily mean the page is about to be flushed immediately. Non-zero `pinning_backends` indicates active pinning by backends.

### Buffers by Fork

~~~sql
SELECT
    relforknumber,
    count(*) AS buffers,
    count(*) FILTER (WHERE isdirty) AS dirty_buffers
FROM pg_buffercache
GROUP BY relforknumber
ORDER BY relforknumber;
~~~

Common fork number mapping: `main=0`, `FSM=1`, `VM=2`, `init=3`. Confirm against your PostgreSQL version and page types.

## 19. Mapping Buffers Back to Relations

Mapping filenodes to relations requires accounting for database and tablespace. A filenode can change during table rewrites, `VACUUM FULL`, `CLUSTER`, `REINDEX`, and similar operations. Never join solely on `relfilenode` cluster-wide.

Example for ordinary relations in the current database:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    count(*) AS cached_buffers,
    count(*) FILTER (WHERE b.isdirty) AS dirty_buffers,
    round(avg(b.usagecount), 2) AS average_usage_count
FROM pg_buffercache AS b
JOIN pg_class AS c
    ON c.relfilenode = b.relfilenode
WHERE b.reldatabase = (
    SELECT oid
    FROM pg_database
    WHERE datname = current_database()
)
  AND c.relkind IN ('r', 'i', 'm', 't')
GROUP BY c.oid
ORDER BY cached_buffers DESC
LIMIT 30;
~~~

This is an illustrative diagnostic query, not an exhaustive mapping:

- Certain system relations use mapped filenodes and require `pg_relation_filenode()`.
- Tablespaces should be matched.
- TOAST relations and indexes are separate objects.
- Partitioned parent tables have no storage of their own.
- Filenodes can change concurrently during the query.
- Temporary relations have per-session scope.

For exact inspection, match relation OID, tablespace, and `pg_relation_filenode()`/`pg_relation_filepath()` per version. Join to current-database catalogs only when `reldatabase` matches that database.

## 20. What Questions Does pg_buffercache Answer?

Valid use cases:

- Which relations occupy the most shared buffers?
- How many of a relation's buffers are dirty?
- Are `main` forks or FSM/VM consuming buffers?
- Does a table hold many cached pages after a workload?
- How does buffer residency change after warm-up?
- Are many pages pinned at inspection time?

Do not use `pg_buffercache` to:

- Conclude physical disk read/write counts.
- Conclude long-term query cache hit ratios.
- Prove a table is hot from a single snapshot.
- Evaluate cluster-wide performance without OS cache and workload context.
- Arbitrarily force page eviction or flushing in production.

Take multiple snapshots over time and correlate with `pg_stat_io`, `pg_stat_database`, `EXPLAIN (BUFFERS)`, and OS storage metrics.

## 21. pgstattuple: Measuring Dead Tuples and Free Space

`pgstattuple` reports physical tuple and free-space statistics for tables and indexes.

Install:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
~~~

Inspect a table:

~~~sql
SELECT *
FROM pgstattuple('public.orders');
~~~

Typical output columns:

- `table_len`: relation byte size.
- `tuple_count`: live tuples detected.
- `tuple_len`: total bytes of live tuples.
- `tuple_percent`: percentage of page bytes used by live tuples.
- `dead_tuple_count` and `dead_tuple_len`.
- `dead_tuple_percent`.
- `free_space` and `free_percent`.

### pgstattuple_approx

~~~sql
SELECT *
FROM pgstattuple_approx('public.orders');
~~~

The approximate variant can leverage visibility/free-space metadata to scan less data in some cases, though its output is an estimate with distinct semantics.

### Cost

`pgstattuple` may scan much or all of a relation. On large tables, this generates heavy I/O and CPU load. Run within an observation window, limit scope, and avoid scanning multiple large relations concurrently without assessing load.

A high dead-tuple percentage does not automatically imply `VACUUM FULL` is needed. First check autovacuum, transaction horizon, table churn, index bloat, and whether free space is reusable.

## 22. pgstatindex: Inspecting B-Tree Indexes

`pgstattuple` also includes `pgstatindex` for B-tree indexes:

~~~sql
SELECT *
FROM pgstatindex('public.orders_created_at_idx');
~~~

Columns can include:

- Index size.
- Tree level.
- Index pages.
- Leaf pages.
- Empty/deleted pages.
- Average leaf density.
- Leaf fragmentation.

Interpret values in light of workload, `fillfactor`, insert patterns, and version. Fragmentation or low density is not automatically a bug; a larger index may be normal for the active workload and data distribution.

Never run `REINDEX` solely because of a low density number without measuring query performance, write amplification, and maintenance window impact.

## 23. pg_freespacemap: Inspecting the Free Space Map

The FSM tracks estimated free space in heap pages so PostgreSQL can locate space for new tuples.

Install:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_freespacemap;
~~~

View free space:

~~~sql
SELECT *
FROM pg_freespace('public.orders')
ORDER BY blkno
LIMIT 50;
~~~

Results typically list block numbers and FSM-recorded free bytes. This is allocation metadata, not an exact count of every usable byte.

Use it to:

- Inspect free-space distribution.
- Investigate tables with many empty pages or sparse free space.
- Cross-check against `pgstattuple`.
- Understand space reuse after vacuuming.

Never edit the FSM manually. PostgreSQL maintains the free space map automatically; if metadata inconsistency is suspected, use appropriate verification tools and recovery procedures.

## 24. pg_visibility: Visibility Map

The visibility map tracks `all-visible` and `all-frozen` page states. It supports `VACUUM` and index-only scans.

Install:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_visibility;
~~~

Summary view:

~~~sql
SELECT *
FROM pg_visibility_map_summary('public.orders');
~~~

Per-block inspection:

~~~sql
SELECT *
FROM pg_visibility_map('public.orders')
ORDER BY blkno
LIMIT 100;
~~~

Columns generally show block number, `all_visible`, and `all_frozen`.

### Why Does the Visibility Map Matter?

- `all-visible` lets index-only scans skip heap fetches when conditions allow.
- `all-frozen` reduces future vacuum/freeze work on pages.
- `VACUUM` updates the visibility map as tuple states allow.
- Old transactions or updates can clear a page's `all-visible` bit.

A low `all-visible` ratio can force index-only scans to visit the heap more often, though it is not necessarily an error. Check write churn, vacuum progress, long-running transactions, and query plans.

### Checking Page Visibility

~~~sql
SELECT *
FROM pg_check_visible('public.orders'::regclass);
~~~

~~~sql
SELECT *
FROM pg_check_frozen('public.orders'::regclass);
~~~

These validation functions can detect page flags inconsistent with tuple visibility/freeze state per version semantics. Running across large relations incurs heavy I/O; never edit visibility maps or page flags manually.

## 25. pg_walinspect: Inspecting WAL via SQL

`pg_walinspect` reads WAL record metadata within an LSN range. Introduced in PostgreSQL 15; verify version and function signatures before use.

Install:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_walinspect;
~~~

Example listing WAL records in an LSN range:

~~~sql
SELECT *
FROM pg_get_wal_records_info(
    '0/1000000'::pg_lsn,
    '0/2000000'::pg_lsn
)
LIMIT 50;
~~~

Example WAL statistics:

~~~sql
SELECT *
FROM pg_get_wal_stats(
    '0/1000000'::pg_lsn,
    '0/2000000'::pg_lsn
);
~~~

LSNs above are placeholders. Specify an actual range present in available WAL; recycled or archive-only segments may not be readable from active `pg_wal`.

### WAL Record Fields

Output can include:

- Start/end LSN.
- Transaction ID.
- Resource manager.
- Record type.
- Record length.
- Main data length.
- Full-page image length.
- Description.
- Block reference metadata.

Use it to investigate WAL generation, record types, and activity in an interval. Do not infer business-level transactions from record counts alone.

### WAL Inspection Security

WAL can contain sensitive values or change details. Restrict access, bound LSN ranges, and redact output. Never export raw WAL or record payloads outside authorized systems.

## 26. pg_waldump: External Server Tool

`pg_waldump` is a command-line utility that reads WAL segments and prints record details. It is helpful when analyzing WAL outside SQL sessions or during incident investigations.

Example:

~~~bash
pg_waldump --path=/var/lib/postgresql/16/main/pg_wal
~~~

Options and paths depend on version, OS, package layout, and WAL availability. Check `pg_waldump --help` for your exact major version.

Notes:

- `pg_waldump` reads WAL files; it does not modify the database.
- WAL files must still exist or be supplied from archives.
- Tool version must match the WAL format.
- WAL records can reveal sensitive information.
- Reading large WAL spans generates I/O; restrict LSN/segment ranges.

Never manually copy or delete WAL files inside a live data directory. Use proper archiving and backup tooling.

## 27. pg_stat_statements: Inspecting Query Workload

`pg_stat_statements` aggregates statistics for normalized queries. While not raw page inspection, it is often the first step to identify which workload merits deep investigation.

Setup typically requires:

1. Adding `pg_stat_statements` to `shared_preload_libraries`.
2. Restarting PostgreSQL.
3. Creating the extension in the target database.
4. Verifying counters and reset times.

Example:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Inspect top queries by total execution time:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

View schemas and column names vary across extension versions. Verify with `psql` `\d` or catalogs before automating.

### Interpretation

- `total_exec_time`: cumulative execution time.
- `mean_exec_time`: mean time per call.
- `calls`: invocation count.
- `shared_blks_hit`/`read`: PostgreSQL buffer pool activity.
- `temp_blks_read`/`written`: temporary block spill activity.
- `rows`: rows returned/affected per view semantics.

A query with high total time may simply be called very often; high mean time points to per-call latency. Compare `calls`, `mean`, `total`, and workload volume together.

## 28. pg_stat_io: I/O by Backend and Context

Starting in PostgreSQL 16, `pg_stat_io` provides I/O counters broken down by backend type, object, and context.

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

Version-dependent fields can include `reads`/`read_time`, `writes`/`write_time`, `writebacks`/`writeback_time`, `extends`/`extend_time`, `hits`, `evictions`, `reuses`, `fsyncs`, and `fsync_time`.

Correlate with `pg_stat_statements` for query workload and OS/storage metrics for device behavior. Do not treat every counter as a one-to-one physical device operation.

### Snapshots and Deltas

Counters accumulate since stats reset or server start. Capture snapshots at `t1` and `t2`, record `stats_reset`, and compute deltas. If the server restarted or stats reset between samples, segment measurements before and after.

## 29. Supporting System Inspection Views

Not every investigation requires an extension. Built-in PostgreSQL views are often enough to narrow down the scope first.

### Sessions and Wait Events

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    left(query, 180) AS query_sample
FROM pg_stat_activity
ORDER BY query_start NULLS LAST;
~~~

### Blocking Sessions

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event,
    left(query, 180) AS query_sample
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

### Table Statistics

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY seq_tup_read DESC;
~~~

### Index Statistics

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;
~~~

Counters can reset and reflect only activity since the last reset. A low `idx_scan` over a short window is not sufficient reason to drop an index.

## 30. pg_stat_progress Views

PostgreSQL exposes progress views for several long-running operations. View names and columns depend on version.

Vacuum example:

~~~sql
SELECT *
FROM pg_stat_progress_vacuum;
~~~

`CREATE INDEX` example:

~~~sql
SELECT *
FROM pg_stat_progress_create_index;
~~~

`ANALYZE` example:

~~~sql
SELECT *
FROM pg_stat_progress_analyze;
~~~

Use these to check an operation's current phase, blocks scanned, or remaining work. These views retain no historical records; scrape or snapshot them if post-event analysis is needed.

## 31. pg_checksums: Verifying Page Checksums

Page checksums help detect certain forms of page corruption when PostgreSQL reads pages. Capabilities and procedures depend on version and how the cluster was initialized.

The `pg_checksums` utility can verify cluster checksums offline per version requirements. General example:

~~~bash
pg_checksums --check --pgdata=/path/to/cluster
~~~

The server must be stopped before running check/enable/disable modes per tool/version requirements. Never run against a live data directory if your version's documentation requires cluster shutdown.

Notes:

- The cluster must have been initialized or enabled with checksums to have checksums to verify.
- Zero checksum errors does not prove all logical database data is sound.
- Checksums detect certain page corruption classes; they do not replace backups.
- On checksum mismatches, preserve evidence and follow incident/recovery plans.
- Never rewrite checksums or edit raw pages manually.

Verify status via `pg_controldata` or version-appropriate tooling.

## 32. pg_verifybackup: Verifying Backups

`pg_verifybackup` checks a backup directory against the backup manifest produced by `pg_basebackup` and runs tool-supported validations.

Example:

~~~bash
pg_verifybackup /path/to/basebackup
~~~

The tool version must match the backup format and PostgreSQL version. Passing validation is valuable evidence of manifest/file integrity, yet restore testing remains essential to prove end-to-end recovery.

If using a backup tool other than `pg_basebackup`, use its own verification utility. Never assume `pg_verifybackup` supports every backup format.

## 33. pg_controldata and Cluster Metadata

`pg_controldata` prints cluster control file information:

~~~bash
pg_controldata /path/to/cluster
~~~

It can show:

- Database system identifier.
- Catalog version number.
- Database cluster state.
- Latest checkpoint location.
- REDO/WAL information.
- Checksum version.
- Timeline/checkpoint metadata.

Use it to verify cluster identity, backup/restore state, or startup/recovery diagnostics. Match the binary version and point at the right data directory. Never edit control files with external tools.

## 34. Other Inspection Tools

Additional supporting tools:

| Tool | Purpose | Notes |
| --- | --- | --- |
| `pg_test_fsync` | Compare fsync methods on a filesystem | Benchmark; does not prove production durability |
| `pg_test_timing` | Measure timing overhead/precision | Run on the target host |
| `pgbench` | Benchmark PostgreSQL workloads | Can generate substantial data and load |
| `psql` | Query catalogs and statistics | Ensure compatible client version and privileges |
| `EXPLAIN` | Analyze query plans | `ANALYZE` executes the statement |
| `iostat`/`vmstat`/`sar` | OS I/O, CPU, memory | Correlate with device/container/cloud metrics |
| `strace`/`perf` | Syscall/CPU profiling | Imposes overhead; use under tight control |
| `lsof` | Inspect open file descriptors | Does not replace database catalogs |
| `dmesg`/`journalctl` | Kernel/storage/service errors | May require OS privileges |

Never run benchmarks, tracing, or system probes on production casually. Define impact, duration, sampling rate, and stop conditions first.

## 35. Combining Multiple Tools in One Investigation

For example, when suspecting a table/index issue alongside slow queries:

1. Use `pg_stat_statements` to locate queries with regressions.
2. Run `EXPLAIN (ANALYZE, BUFFERS)` on a representative query.
3. Check index validity in `pg_index`.
4. Run `amcheck` on relevant indexes.
5. Use `pg_buffercache` to inspect a page residency snapshot.
6. Use `pgstattuple`/`pgstatindex` to examine tuple/bloat/index layout.
7. Use `pg_visibility` to inspect `all-visible`/`all-frozen` state.
8. Correlate with `pg_stat_io` and OS I/O metrics.
9. Review server logs, checksums, and storage events.
10. Choose repair or recovery once sufficient evidence is gathered.

You do not need to run every tool in every incident. Start from a concrete question and escalate inspection depth only as evidence warrants.

## 36. Runbook: Periodic B-Tree Checks

### Before Running

- Confirm the database and cluster.
- Verify `amcheck` version and privileges.
- List target indexes.
- Choose concurrency and maintenance window.
- Record disk/I/O/latency baselines.
- Confirm log destination and alert recipients.
- Define the procedure if an error is detected.

### Execution

For a single index:

~~~sql
SELECT bt_index_check('public.orders_pkey'::regclass);
~~~

Or run `pg_amcheck` against an approved list of databases/objects.

### After Running

- Record exit status and output.
- Document checked and skipped objects.
- Record duration and resource impact.
- If errors occurred, open an incident and preserve evidence.
- Close the runbook only when the scope completes and exceptions are logged.

## 37. Runbook: Inspecting a Specific Page

### Before Reading

- Identify the relation OID/name.
- Identify the fork.
- Confirm the block number is in range.
- Record relation size.
- Determine whether concurrent writes are active.
- Check `pageinspect` privileges.
- Define evidence storage and redaction rules.

### Execution

~~~sql
SELECT *
FROM page_header(get_raw_page('public.orders', 'main', 0));

SELECT *
FROM heap_page_items(get_raw_page('public.orders', 'main', 0));
~~~

For B-trees:

~~~sql
SELECT *
FROM bt_metap('public.orders_created_at_idx');

SELECT *
FROM bt_page_stats('public.orders_created_at_idx', 1);
~~~

### After Reading

- Record query, version, relation, and block.
- Never modify raw pages.
- Correlate with `amcheck` if consistency validation is needed.
- If signs of corruption appear, stop write/repair attempts and transition to a recovery plan.

## 38. Runbook: Inspecting the Buffer Cache

### Before Running

- Verify extension and privileges.
- Choose database scope.
- Define goal: residency, dirty buffers, or usage distribution.
- Capture workload metrics simultaneously.
- Avoid overly frequent polling on large systems.

### Execution

~~~sql
SELECT
    count(*) AS buffers,
    count(*) FILTER (WHERE isdirty) AS dirty_buffers,
    round(avg(usagecount), 2) AS average_usage_count
FROM pg_buffercache;
~~~

### Interpretation

- The snapshot reflects state at query execution time.
- Buffer residency shifts with workload.
- It is not equivalent to the OS page cache.
- It is not a physical read/write counter.
- Dirty buffer counts do not directly indicate write latency.

Correlate with `pg_stat_io`, `EXPLAIN (BUFFERS)`, OS metrics, and query workload.

## 39. Runbook: Investigating Bloat and Free Space

### Before Running

- Select the target table/index.
- Check relation size.
- Estimate scan cost.
- Check active workload.
- Identify which decisions or queries depend on the output.

### Execution

~~~sql
SELECT *
FROM pgstattuple_approx('public.orders');

SELECT *
FROM pgstatindex('public.orders_created_at_idx');

SELECT *
FROM pg_freespace('public.orders')
ORDER BY blkno
LIMIT 100;
~~~

### After Running

- Compare live, dead, and free bytes.
- Check autovacuum activity and transaction horizon.
- Determine whether free space is reusable or needs to be returned to the OS.
- Measure query impact.
- Decide on `VACUUM`, `REINDEX`, or table rewrite only with a lock/disk/recovery plan.

Never use a standalone bloat estimate as an automatic trigger for `VACUUM FULL`.

## 40. Runbook: Investigating WAL

### Before Reading WAL

- Define the LSN range.
- Verify WAL segments still exist or are available in archive.
- Confirm `pg_walinspect`/`pg_waldump` version.
- Assess WAL data sensitivity.
- Restrict output and access privileges.

### Execution

~~~sql
SELECT *
FROM pg_get_wal_stats(
    '0/1000000'::pg_lsn,
    '0/2000000'::pg_lsn
);
~~~

### After Reading

- Correlate LSN range and timeline.
- Compare against WAL generation metrics.
- Never infer business-level transactions purely from record counts.
- Store redacted evidence.
- Never manually delete or recycle WAL.

## 41. Understanding Each Tool's Limits

| Tool | Can help detect | Does not prove |
| --- | --- | --- |
| `amcheck` | Certain index/heap structural errors | All business data is valid |
| `pg_amcheck` | Automating `amcheck` scope | Every object/page checked for every invariant |
| `pageinspect` | Specific page contents and metadata | Overall page consistency |
| `pg_buffercache` | Buffer residency snapshot | Physical disk cache/hit rate over time |
| `pgstattuple` | Tuple/dead/free-space statistics | Root cause of bloat or query performance |
| `pg_freespacemap` | FSM-recorded free space | Exact usable bytes to the byte |
| `pg_visibility` | Visibility map state | Complete MVCC correctness |
| `pg_walinspect` | WAL record metadata in a range | Full business transaction semantics |
| `pg_stat_statements` | Query-level aggregate stats | Per-request traces or exact percentiles |
| `pg_stat_io` | I/O counters by backend/object/context | One-to-one physical device operations |
| `pg_checksums` | Checksum mismatches on checksummed pages | Absence of all corruption types |
| `pg_verifybackup` | Backup manifest/file validation | End-to-end restore/application recovery |

## 42. Risks of Production Inspection

1. **I/O amplification:** scanning large tables/indexes drives up storage latency.
2. **CPU overhead:** decoding pages, computing checksums, or aggregating detailed stats.
3. **Lock impact:** some `amcheck` modes or DDL/maintenance checks acquire locks affecting concurrent workloads.
4. **Sensitive data exposure:** `pageinspect` and WAL output can contain user data.
5. **Privilege escalation:** granting superuser for convenience widens blast radius.
6. **Misinterpretation:** misreading tuple flags, usage counts, or visibility map bits.
7. **Snapshot inconsistency:** pages changing mid-read or counters resetting.
8. **False confidence:** tools reporting no errors when corruption lies outside checked invariants.
9. **Premature repair:** running `REINDEX`/`VACUUM`/restore before saving evidence.
10. **Tool mismatch:** binary/extension versions incompatible with the server.

### Stop Conditions

Halt inspection and switch to incident response when:

- A checksum mismatch or `amcheck` corruption error appears.
- Server logs record `PANIC`/`FATAL` related to pages or storage.
- The OS reports I/O errors or filesystem issues.
- Multiple relations become unreadable.
- Queries begin returning inconsistent results.
- Storage latency or error rates spike due to scanning.
- The exact target or version cannot be verified.
- Required privileges exceed approved scope.

## 43. Security and Evidence Preservation

Evidence records should capture:

- Change/incident ID.
- Cluster/database identity.
- PostgreSQL version.
- Extension version.
- Tool version.
- Relation/index and fork/block range.
- Command/query executed.
- Start/end timestamps and timezone.
- Operator/role.
- Exit status.
- Output/log references.
- Resource impact.
- Exceptions and next actions.

Never store passwords, tokens, private keys, connection strings with secrets, unnecessary raw tuple values or WAL payloads, out-of-scope customer PII, or raw page dumps in broadly readable tickets.

If raw pages or WAL artifacts must be kept for forensics, store them in an evidence repository with access controls, encryption, retention limits, and chain-of-custody tracking.

## 44. Controlled Automation of Inspections

A scheduled inspection job may:

1. Collect extension inventory.
2. Select indexes/tables per risk policy.
3. Run `amcheck` with bounded concurrency.
4. Collect query/I/O statistics.
5. Store outputs and timestamps.
6. Alert when a command fails.
7. Open an incident reference and preserve raw evidence.
8. Never auto-run `REINDEX`, restore, or drop objects.

### Separate Detection from Remediation

Detection can be automated because most checks are read-only. Remediation—such as `REINDEX`, `VACUUM FULL`, restore, failover, or data fixes—requires a separate decision gate.

Never schedule cluster-wide `pageinspect` cron jobs without a clear objective. For periodic verification, scoped `pg_amcheck` at a benchmarked cadence is usually much better suited.

## 45. Common Mistakes

1. **Treating `amcheck` as certification that the entire database has zero corruption**, when it checks only supported invariants.
2. **Running `bt_index_parent_check` across all indexes during peak hours**, causing unexpected locking and resource contention.
3. **Ignoring PostgreSQL version differences in function signatures**, causing query errors or misunderstood options.
4. **Confusing `amcheck` and `pageinspect`**, using a page decoder to judge structural consistency.
5. **Editing raw pages manually after reading `pageinspect`**, risking severe database damage.
6. **Reading `t_xmax` as a simple deletion flag**, ignoring MVCC visibility and transaction status.
7. **Running `pageinspect` under an application role**, expanding internal data access unnecessarily.
8. **Joining `pg_buffercache` solely on `relfilenode`**, misattributing relations across databases or tablespaces.
9. **Treating `usagecount` as a query hit count**, misinterpreting buffer replacement metadata.
10. **Treating buffer misses as physical disk reads**, ignoring the OS page cache.
11. **Treating dirty buffers as an exact write backlog**, without correlating I/O and checkpoint statistics.
12. **Running `pgstattuple` concurrently on many large tables**, triggering heavy full-relation scans.
13. **Using dead-tuple percentage alone to justify `VACUUM FULL`**, ignoring lock impact and rewrite costs.
14. **Treating FSM free bytes as exact usable capacity**, overlooking free space map semantics.
15. **Using `pg_visibility` to declare MVCC fully healthy**, overreaching the scope of the visibility map.
16. **Not checking WAL LSN ranges/timelines**, reading wrong or missing records due to recycled segments.
17. **Pasting WAL or `pageinspect` output into public tickets**, leaking sensitive data.
18. **Checking only `pg_amcheck`'s exit code**, overlooking skipped objects and stderr.
19. **Running `pg_checksums` on a running cluster**, violating offline tool/version requirements.
20. **Treating `pg_verifybackup` as a restore test**, skipping actual application recovery validation.
21. **Installing an extension in one database and assuming all databases have it**, overlooking per-database installation.
22. **Granting `SUPERUSER` for convenience**, creating unnecessary blast radius.
23. **Running `REINDEX` automatically upon error without saving evidence**, destroying forensic clues.
24. **Ignoring OS and storage logs**, missing underlying hardware or filesystem causes.
25. **Polling inspection queries too aggressively**, turning diagnostics into the bottleneck itself.
26. **Failing to record version, timestamp, and scope**, making findings non-reproducible.

## 46. Practice Exercises with Answers

### Exercise 1. What is `amcheck` used for?

**Answer:** Verifying specific structural consistency invariants of B-tree indexes and heaps on supported versions.

### Exercise 2. How does `pageinspect` differ from `amcheck`?

**Answer:** `pageinspect` decodes page/tuple structures for inspection; `amcheck` checks structural invariants.

### Exercise 3. What question does `pg_buffercache` answer?

**Answer:** Which pages are currently held in PostgreSQL's shared buffer cache at the moment of the query.

### Exercise 4. Does `CREATE EXTENSION` take effect cluster-wide?

**Answer:** No. SQL extension objects are created in the current database; packages/shared libraries are installed at the server level.

### Exercise 5. Which view lists available extensions?

**Answer:** `pg_available_extensions`.

### Exercise 6. Which catalog lists extensions installed in the database?

**Answer:** `pg_extension`.

### Exercise 7. Which objects does `bt_index_check` target?

**Answer:** B-tree indexes supported by `amcheck`.

### Exercise 8. What is the purpose of `bt_index_parent_check`?

**Answer:** Deeper verification of B-tree parent/child page structures and related invariants.

### Exercise 9. What is `pg_amcheck`?

**Answer:** A command-line utility automating `amcheck` checks across databases/objects, introduced in PostgreSQL 14.

### Exercise 10. Where can invalid indexes be observed?

**Answer:** `pg_index`, specifically `indisvalid` and `indisready`, alongside `amcheck` and logs.

### Exercise 11. What is `verify_heapam` used for?

**Answer:** Detecting specific structural errors in heaps on supported `amcheck` versions.

### Exercise 12. What does `get_raw_page` return?

**Answer:** The raw contents of a relation page as `bytea`.

### Exercise 13. What does `page_header` provide?

**Answer:** Page metadata such as LSN, flags, and page region boundaries per the page format.

### Exercise 14. What does `heap_page_items` display?

**Answer:** Line pointers and tuple header/metadata for a heap page.

### Exercise 15. Does `t_xmax` always mean a row is deleted?

**Answer:** No. You must evaluate MVCC, transaction status, snapshots, and tuple flags.

### Exercise 16. What is `bt_metap` used to inspect?

**Answer:** B-tree index metadata such as root block and tree level.

### Exercise 17. What is `pg_buffercache` `usagecount`?

**Answer:** Buffer replacement strategy metadata, not a query hit counter.

### Exercise 18. Why does `pg_buffercache` not measure physical disk I/O?

**Answer:** Because it inspects only shared buffers; the OS page cache and storage layer lie outside this view.

### Exercise 19. What does `pgstattuple` measure?

**Answer:** Live/dead tuples, tuple bytes, and free space in a relation.

### Exercise 20. What is `pgstatindex` used for?

**Answer:** Inspecting B-tree index structure and statistics.

### Exercise 21. What does `pg_freespacemap` report?

**Answer:** Free space recorded by the FSM per heap block.

### Exercise 22. What two key states does the visibility map track?

**Answer:** `all-visible` and `all-frozen`.

### Exercise 23. Why does the visibility map matter for index-only scans?

**Answer:** `all-visible` pages allow skipping heap fetches when query and index conditions permit.

### Exercise 24. What is `pg_walinspect` used for?

**Answer:** Inspecting WAL record metadata within an LSN range; introduced in PostgreSQL 15.

### Exercise 25. Does `pg_stat_statements` require preloading?

**Answer:** Typically yes—it requires `shared_preload_libraries` and a restart for full operation.

### Exercise 26. Which PostgreSQL version introduced `pg_stat_io`?

**Answer:** PostgreSQL 16.

### Exercise 27. Can `pg_checksums` run on a live cluster?

**Answer:** Check/enable/disable modes require offline conditions per tool/version documentation; never run on a live server when shutdown is required.

### Exercise 28. What does `pg_verifybackup` prove?

**Answer:** Backup manifest/file validation within its supported scope; it does not replace end-to-end restore testing.

### Exercise 29. What should you do first when `amcheck` reports corruption?

**Answer:** Preserve evidence, identify the object/version, inspect logs/storage/checksums, and verify backups/recovery before modifying anything.

### Exercise 30. Why should you not immediately run `REINDEX` upon seeing an error?

**Answer:** You must determine whether the fault lies in the index or in the heap/storage and preserve evidence before altering state.

## 47. PostgreSQL Internals Inspection Checklist

### Before Running

- [ ] Define the investigation question.
- [ ] Confirm cluster, database, and primary/standby role.
- [ ] Verify PostgreSQL and extension versions.
- [ ] Check extension availability and installation state.
- [ ] Verify function signatures and privileges for the version.
- [ ] Choose a specific relation, index, fork, and block range.
- [ ] Assess table/index sizes and I/O impact.
- [ ] Select an appropriate maintenance window and concurrency.
- [ ] Define evidence destination and redaction rules.
- [ ] Establish stop conditions and an escalation owner.

### During Execution

- [ ] Log commands/queries and timestamps.
- [ ] Monitor CPU, memory, I/O, locks, and application latency.
- [ ] Save stdout, stderr, and SQL results.
- [ ] Record any skipped objects or permission errors.
- [ ] Avoid out-of-scope cluster-wide scans.
- [ ] Never edit raw pages or WAL.
- [ ] Stop if system regression exceeds thresholds.

### After Running

- [ ] Interpret results strictly within each tool's scope.
- [ ] Correlate with server logs and OS/storage events.
- [ ] Combine catalog, statistics, and application evidence.
- [ ] If corruption exists, open an incident and preserve evidence.
- [ ] Execute repair/recovery under a separate change plan.
- [ ] Record version, scope, output, and reviewer.
- [ ] Confirm the system remains healthy after inspection.

## 48. Official PostgreSQL Documentation

Consult documentation matching your deployed major version:

- [amcheck](https://www.postgresql.org/docs/current/amcheck.html) — B-tree and heap consistency verification.
- [pg_amcheck](https://www.postgresql.org/docs/current/app-pgamcheck.html) — index/heap checking utility.
- [pageinspect](https://www.postgresql.org/docs/current/pageinspect.html) — inspect pages, heap tuples, and index pages.
- [pg_buffercache](https://www.postgresql.org/docs/current/pgbuffercache.html) — inspect the shared buffer cache.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html) — tuple, dead-tuple, free-space, and index statistics.
- [pg_freespacemap](https://www.postgresql.org/docs/current/pgfreespacemap.html) — free space map inspection.
- [pg_visibility](https://www.postgresql.org/docs/current/pgvisibility.html) — visibility map and page checks.
- [pg_walinspect](https://www.postgresql.org/docs/current/pgwalinspect.html) — WAL record inspection.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — query workload statistics.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_io`, sessions, replication, and progress views.
- [Database Page Layout](https://www.postgresql.org/docs/current/storage-page-layout.html) — page headers, line pointers, and tuple layout.
- [Database Physical Storage](https://www.postgresql.org/docs/current/storage.html) — relation files and forks.
- [pg_checksums](https://www.postgresql.org/docs/current/app-pgchecksums.html) — page checksum verification.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html) — backup manifest verification.
- [pg_controldata](https://www.postgresql.org/docs/current/app-pgcontroldata.html) — cluster control information.
- [pg_waldump](https://www.postgresql.org/docs/current/pgwaldump.html) — reading WAL records from the command line.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) — installing extensions in a database.

The `/current/` URLs point to current PostgreSQL documentation. Extension availability, function signatures, privileges, view columns, and command options can differ across major versions, distributions, and managed providers. Check the documentation for your exact version before running commands in production.

## 49. Summary

**amcheck verifies structure, pageinspect lets you observe pages, and pg_buffercache shows which pages reside in shared buffers.** Companion tools such as `pgstattuple`, `pg_visibility`, `pg_walinspect`, and `pg_stat_statements` extend investigations across storage, MVCC, WAL, and workload.

1. **Choose the tool for the specific question.** Never rely on one extension to certify overall database health.
2. **Install extensions in the right database and verify versions.** Packages/shared libraries and SQL extension objects are two distinct layers.
3. **amcheck/pg_amcheck verify indexes and heaps within version scope.** Clean results do not prove all data is valid.
4. **pageinspect reads physical layout.** It is a forensic tool, not a page repair tool or general consistency checker.
5. **pg_buffercache is a shared buffer cache snapshot.** It does not measure physical disk I/O or reflect the OS page cache.
6. **pgstattuple, pg_freespacemap, and pg_visibility offer distinct perspectives.** Dead tuples, FSM free space, and visibility bits are not interchangeable.
7. **pg_walinspect and pg_waldump inspect WAL.** Restrict LSN ranges and protect sensitive data.
8. **pg_stat_statements and pg_stat_io connect workloads to I/O behavior.** Use snapshots/deltas and correlate with OS metrics.
9. **Some checks incur heavy I/O/CPU or require high privileges.** Choose scope, concurrency, and timing carefully.
10. **When corruption is detected, preserve evidence before remediation.** `REINDEX` cannot fix heap or storage failures.
11. **Backup validation and restore tests remain indispensable.** Diagnostic extensions do not substitute for recovery readiness.
12. **Record version, object, block range, timestamp, and output.** Reproducible evidence enables accurate investigation and review.

Effective internal inspection progresses from question to evidence: pick the right tool, respect output boundaries, cross-check across multiple layers, and execute remediation only after the database state is clearly established.
