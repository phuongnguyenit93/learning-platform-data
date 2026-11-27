# Data Page Structure, Rows, and Physical Location References in PostgreSQL

## 1. From a SELECT Statement to a Row's Location on Disk

When executing:

~~~sql
SELECT account_id, owner_name, balance
FROM accounts
WHERE account_id = 42;
~~~

PostgreSQL does not look up "the 42nd row" by a fixed ordinal position in the table. The engine must determine **which row satisfies the predicate and which version is visible**, then read data from the corresponding storage pages.

Physically, an ordinary PostgreSQL table is organized as follows:

~~~text
Database
  └── Relation of accounts table
        ├── Main fork (table data)
        │     ├── Page 0
        │     │     ├── Page header
        │     │     ├── Item pointers (line pointers)
        │     │     ├── Free space
        │     │     └── Heap tuples
        │     ├── Page 1
        │     └── Page 2 ...
        ├── Free Space Map (FSM)
        └── Visibility Map (VM)

Indexes are separate physical relations with their own pages and structures.
~~~

Key concepts to understand:

- **Page/block:** the basic storage and I/O unit for most PostgreSQL structures; typically **8 KiB** in standard builds.
- **Heap tuple:** a **physical version of a row** inside a heap table.
- **Item pointer / line pointer:** an entry in the array at the top of a page pointing to the byte offset of a tuple within that page.
- **TID (Tuple Identifier):** a physical pointer formatted as **(block number, offset number)**; the offset identifies an entry in the block's line pointer array.
- **CTID:** a system column selectable in SQL showing the TID of **the row version currently being returned**.
- **MVCC:** the multi-version concurrency control mechanism enabling transactions to read consistent snapshots.
- **TOAST:** the mechanism for storing oversized column values, compressing them and/or moving them to an auxiliary relation.

This lesson explains more than what sits inside a block. The core goal is understanding why **CTID is never a business primary key**, why an `UPDATE` creates a new tuple version, why `VACUUM` cleanup is necessary, and how to observe these mechanisms in PostgreSQL using SQL.

> Scope: PostgreSQL using standard **heap tables**; custom table access methods or storage extensions may use different formats. Specific byte sizes depend on build options and version; the 8 KiB default is simply the most common configuration.

## 2. From Logical Objects to Physical Files

### 2.1. A table does not equal a single file

In SQL, you write:

~~~sql
SELECT * FROM public.accounts;
~~~

Yet PostgreSQL tracks a table as a **relation** with its own identifier and metadata in system catalogs. A relation's storage can span multiple forks and segments. Indexes, TOAST tables, and TOAST indexes are also separate relations.

At the filesystem level, filenames do not match table names. PostgreSQL uses physical identifiers such as **relfilenode / relfilenumber** organized by tablespace, database, fork, and segment. Certain table-rewriting operations assign new physical files while the table's SQL name stays unchanged.

You can inspect a relation's *relative path within the data directory* and identifier via:

~~~sql
SELECT
    'public.accounts'::regclass AS relation_name,
    pg_relation_filenode('public.accounts'::regclass) AS relation_filenode,
    pg_relation_filepath('public.accounts'::regclass) AS relative_path;
~~~

This illustrates syntax assuming the table exists. The practice section below creates `storage_lab.accounts` and runs equivalent queries. These functions return **metadata** without needing to open or touch PostgreSQL data files directly.

**Never edit, delete, or directly copy files inside the data directory** while the server is running just because you found their path. Those files are tightly coupled with WAL, shared buffers, checkpoints, MVCC, and crash recovery.

### 2.2. Common forks

A heap relation can use these forks:

| Fork | Role | Key detail |
|---|---|---|
| **main** | Holds heap tuple pages | This is the table data people usually picture when referring to "table pages" |
| **fsm** | Free Space Map | Tracks approximate free space across pages to help choose where to insert |
| **vm** | Visibility Map | Tracks page-level all-visible and all-frozen flags |
| **init** | Initialization fork | Present on **UNLOGGED** relations to reinitialize them during crash recovery |

Not every relation has all four forks at all times. Indexes also have their own page layouts and forks depending on the index access method.

`main` holds row versions. `fsm` **does not contain copies of tuples**, and `vm` **does not store per-row MVCC state**. Both are auxiliary metadata supporting performance and maintenance.

### 2.3. Relation segments

When the main fork grows large enough, PostgreSQL splits the file into **segments**. Standard builds cap each segment at about **1 GiB**, though actual size depends on build settings. In the data directory, segments of one filenode appear as:

~~~text
<relfilenode>
<relfilenode>.1
<relfilenode>.2
...
~~~

These example names illustrate the segment concept, not files to manipulate directly. Logical block numbering runs continuously across the relation without requiring applications to compute segment offsets.

## 3. Page/Block: The Fundamental Storage Unit

### 3.1. Pages are normally 8 KiB

In standard PostgreSQL builds, one page is **8192 bytes**. This size is compiled via `BLCKSZ`, **not an SQL setting you can change per session**.

Inspect the active block size:

~~~sql
SHOW block_size;

SELECT current_setting('block_size')::integer AS block_size_bytes;
~~~

Normally this returns `8192`. If PostgreSQL was built with another block size such as 16 KiB, page-count calculations must use that actual value instead of hard-coding 8192.

Heap pages in the main fork are addressed by block number:

~~~text
Block 0 → byte range [0, block_size)
Block 1 → byte range [block_size, 2 × block_size)
Block 2 → byte range [2 × block_size, 3 × block_size)
...
~~~

This represents a logical offset within **a relation's fork**, not an absolute byte offset on the underlying physical disk.

### 3.2. Heap page layout

Standard layout of a data page:

~~~text
Top of page (byte offset 0)
┌─────────────────────────────────────────────────────────┐
│ PageHeaderData                                          │
│ Typically 24 bytes in standard PostgreSQL layout        │
├─────────────────────────────────────────────────────────┤
│ ItemIdData #1  (line pointer)                           │
│ ItemIdData #2                                           │
│ ItemIdData #3                                           │
│ ...                                                     │
│ Line pointer array growing downward from top of page ↓  │
├─────────────────────────────────────────────────────────┤
│                       FREE SPACE                        │
│              between pd_lower and pd_upper              │
├─────────────────────────────────────────────────────────┤
│ Newer tuple / older tuple ...                           │
│ Tuple data typically grows upward from bottom of page ↑ │
├─────────────────────────────────────────────────────────┤
│ Special space, if used by access method                 │
│ Ordinary heap pages need no special-space contents      │
└─────────────────────────────────────────────────────────┘
End of page (byte offset block_size)
~~~

Growing from opposite ends lets PostgreSQL append **line pointers from the top** and **tuple data from the bottom**. When dead tuples are removed and the page is compacted, payloads can shift **within the page** while line pointers update their byte offsets to continue pointing accurately.

Therefore:

**The TID offset number is the index of the line pointer, not the byte offset of the tuple.**

For example, `ctid = '(5,3)'` points to **item pointer 3 in block 5**, not byte 3 of that block.

### 3.3. What does PageHeaderData contain?

Notable fields in the page header:

| Field | Meaning |
|---|---|
| `pd_lsn` | WAL log sequence number of the last recorded change to this page |
| `pd_checksum` | Page checksum when data checksums are enabled in the cluster |
| `pd_flags` | Page status flags |
| `pd_lower` | Offset to end of line pointer array (start of free space) |
| `pd_upper` | Offset to start of tuple data (end of free space) |
| `pd_special` | Offset to start of special space |
| `pd_pagesize_version` | Page size and layout version metadata |
| `pd_prune_xid` | Hint XID for when page pruning may reclaim space |

In ordinary heap pages, special space holds no index-specific metadata, so `pd_special` normally points to the end of the page. In B-tree indexes, special space stores sibling links and level metadata.

Looking at the three offsets:

~~~text
          pd_lower              pd_upper          pd_special
              |                     |                   |
[header][line pointers]  FREE SPACE  [tuple data ...]   [special]
~~~

Contiguous free space in the page layout is approximately:

~~~text
pd_upper - pd_lower
~~~

Do not confuse this gap with **total reusable space** tracked by the FSM; dead tuples, reusable line pointers, page compaction, and fillfactor all affect usable insert space.

### 3.4. Checksums and WAL are not row contents

`pd_lsn` and `pd_checksum` are metadata supporting page integrity and recovery; they are not user-defined SQL columns.

- **WAL** lets PostgreSQL replay logged changes after a crash according to configured durability guarantees.
- **Page checksums** depend on cluster initialization/configuration; a cluster without checksums lacks checksum-based corruption detection.
- **Hint bits**, visibility flags, and maintenance operations can update page metadata without corresponding to any business `UPDATE`.

Always separate **row payload data** from **page management metadata**.

## 4. Line Pointers: A Mini-Index Inside Every Page

Each entry in the item pointer array is represented by `ItemIdData`; in standard layouts, each entry takes **4 bytes**.

Logically, a line pointer records:

- Byte offset of the tuple (when payload exists).
- Byte length of the tuple.
- Slot status flags.

Common line pointer states in heap pages:

| Symbol | Name | Interpretation |
|---|---|---|
| `LP_UNUSED` | Unused | Slot is empty and available for reuse |
| `LP_NORMAL` | Normal | Normal slot pointing to a tuple payload |
| `LP_REDIRECT` | Redirect | Redirects to another item pointer, typically for HOT pruning |
| `LP_DEAD` | Dead | Slot marked dead during processing |

Exact flag semantics must be interpreted in the **heap page context**, as index pages organize and maintain slots differently.

### 4.1. Why use line pointers instead of storing byte offsets in CTID?

Suppose a tuple sits at byte 7900 and line pointer `#3` points to it. When PostgreSQL compacts the page, that payload may move to byte 7700. If external references pointed directly to **byte 7900**, every index entry would break. With indirection:

~~~text
TID = (block 5, line pointer #3)
                          |
                          v
Line pointer #3: tuple byte offset 7900
                          |
                  Page is compacted
                          |
                          v
Line pointer #3: tuple byte offset 7700
~~~

The TID stays `(5,3)` during intra-page payload compaction as long as the line pointer remains valid. That indirection is a major architectural advantage.

Even so, slots are **not permanent IDs**: once old versions are no longer needed, PostgreSQL can free and reuse line pointers for future writes.

### 4.2. Multiple row versions on the same page

A standard PostgreSQL `UPDATE` creates a **new tuple version** under MVCC rather than overwriting the old tuple in place. If free space and constraints permit, the new version can land on **the very same heap page**.

A page can then hold:

~~~text
Page 5
  LP #2 → old version of account_id=42 (may be dead)
  LP #3 → new version of account_id=42
  LP #4 → another row
~~~

Depending on transaction state and snapshot, a normal `SELECT` sees the appropriate version, while not every physical tuple on the page is **live and visible** to that snapshot.

## 5. Heap Tuple: A Physical Version of a Row

### 5.1. Overall structure

A heap tuple can be pictured as:

~~~text
┌──────────────────────────────────────────────────┐
│ HeapTupleHeaderData                              │
│   transaction IDs, tuple flags, ctid link, ...   │
├──────────────────────────────────────────────────┤
│ Null bitmap and optional metadata                │
├──────────────────────────────────────────────────┤
│ Padding/alignment up to t_hoff                   │
├──────────────────────────────────────────────────┤
│ Column values stored in internal format          │
│   fixed-width / variable-width / TOAST pointer   │
└──────────────────────────────────────────────────┘
~~~

The fixed header requires at least about **23 bytes** before alignment and optional fields. Actual `t_hoff` can be larger, especially with a null bitmap. Hence **"a row with three integer columns = 12 bytes" ignores per-tuple overhead**.

Frequently referenced header fields:

| Internal field | Role |
|---|---|
| `t_xmin` | Transaction ID that created this tuple version, per MVCC |
| `t_xmax` | Transaction ID or lock/delete/update info associated with this version |
| `t_cid` / related metadata | Internal command ID metadata depending on tuple state |
| `t_ctid` | ItemPointer linking to this version or to the next version when updated |
| `t_infomask`, `t_infomask2` | MVCC status bits, lock flags, and tuple attributes |
| `t_hoff` | Byte offset where attribute data begins |
| `t_bits` | Null bitmap when the tuple contains NULL fields |

Not every tuple uses every field in the exact same intuitive way. In particular, a non-zero **`t_xmax` does not automatically mean the row was deleted**: it can encode row locks or an aborted transaction. PostgreSQL inspects flags, transaction commit status, and snapshots to determine visibility.

### 5.2. SQL NULL is not an empty string

When a column is `NULL`, the tuple records the absence via the **null bitmap** without storing normal column payload for that attribute. Subsequent column layout follows alignment and type formatting rules.

- `NULL` is the absence of an SQL value.
- `''` is a zero-length text value.
- `0` is a numeric zero value.

These three have different SQL semantics and can have different physical footprints.

### 5.3. Fixed-width, variable-width, and alignment

A tuple can store:

- `smallint`, `integer`, `bigint`, `boolean`, and other fixed-width types.
- `text`, `varchar`, `bytea`, `jsonb`, and other variable-length types.
- `numeric`, which uses a variable-length internal representation based on precision/value.
- Pointers to TOAST data when oversized attributes live out-of-line.

PostgreSQL aligns certain types on memory/page boundaries, so column ordering can affect padding bytes. However, **do not reorder columns in a production schema solely from hand calculations**, as schema changes carry operational cost and applications may depend on column order.

Inspect SQL-level value sizes via:

~~~sql
SELECT
    account_id,
    pg_column_size(owner_name) AS owner_name_bytes,
    pg_column_size(balance) AS balance_bytes
FROM storage_lab.accounts
ORDER BY account_id;
~~~

`pg_column_size(value)` reports storage size for that individual value; it does not include heap tuple headers, page headers, line pointers, or external relation overhead. Never sum a few columns casually and claim that equals exact disk usage.

## 6. TID and CTID: Logical Address of a Tuple in the Heap

### 6.1. Selection syntax

In PostgreSQL, `ctid` is a **system column** selectable alongside ordinary columns:

~~~sql
SELECT ctid, account_id, owner_name
FROM storage_lab.accounts
ORDER BY account_id;
~~~

Illustrative output format (values are **not guaranteed to match on your machine**):

~~~text
 ctid   | account_id | owner_name
--------+------------+-----------
 (0,1)  |          1 | Nguyen An
 (0,2)  |          2 | Tran Binh
 (0,3)  |          3 | Le Chi
~~~

`(0,2)` means:

- `0`: **block number**, zero-based within the relation's main fork.
- `2`: **offset number / item pointer number** inside that page, one-based.

Never deduce that `account_id = 2` forces `ctid` to be `(0,2)`. That is merely a coincidence from sequential inserts into an empty small table.

### 6.2. CTID does not represent "the Nth row"

A table has no guaranteed SQL row order without `ORDER BY`. CTID reflects the physical slot of a tuple version; `ORDER BY ctid` sorts by physical placement, **not business order, creation time, or primary key**.

~~~sql
SELECT account_id, owner_name, ctid
FROM storage_lab.accounts
ORDER BY ctid;
~~~

This can be useful for **internal inspection**, but should never be used to paginate "page 3 sorted by date" or guarantee stable ordering over time.

### 6.3. How do CTID and TID differ?

- **TID** is the tuple-address type/concept `(block, offset)` used by indexes and the executor to point to heap tuples.
- **`ctid`** is a system column exposing the location of the returned tuple version, of PostgreSQL data type `tid`.
- **`t_ctid`** is an **internal tuple header field** that can point forward to the next tuple version after an `UPDATE`.

These three related terms are **not strictly identical**. In particular, reading `ctid` via `SELECT` is not equivalent to dumping raw `t_ctid` bits from an arbitrary historical tuple.

### 6.4. Why should you never use CTID as a primary key?

CTID can change whenever:

1. A row is `UPDATE`d: PostgreSQL writes a new version, normally at a new tuple location.
2. A **table-rewriting command** such as `VACUUM FULL` or `CLUSTER` reorganizes/rewrites the data.
3. Data-moving or relation-rebuilding operations occur.
4. Dead tuples are reclaimed and slots are **reused** later.

Therefore:

~~~sql
-- Do NOT store CTID as a permanent customer identifier.
SELECT ctid FROM storage_lab.accounts WHERE account_id = 1;
~~~

If a service saves `'(0,1)'` in another table and uses it next week to fetch "customer 1," it may no longer point to the expected row version.

By contrast:

~~~sql
SELECT *
FROM storage_lab.accounts
WHERE account_id = 1;
~~~

The primary key `account_id` is a **stable logical identifier** independent of heap location. A tuple can relocate or be superseded by a new version while its business ID stays constant.

### 6.5. When is CTID useful?

CTID is helpful when:

- Debugging or learning heap structure.
- Observing whether an `UPDATE` produces a new tuple position.
- Analyzing plans using `Tid Scan` or `Tid Range Scan` where supported by PostgreSQL.
- Temporarily identifying a version within **a single controlled transaction or maintenance step**, understanding that concurrent updates or rewrites invalidate the reference.

Special query example:

~~~sql
SELECT ctid, account_id, owner_name
FROM storage_lab.accounts
WHERE ctid = '(0,1)'::tid;
~~~

This is useful only if you **know with certainty** which tuple sits at that address in the current relation state. Never hard-code an assumed CTID in business applications.

## 7. Experiment: Observing CTID Before and After UPDATE

### 7.1. Setting up the lab schema

Run only in a lab database, never production:

~~~sql
CREATE SCHEMA IF NOT EXISTS storage_lab;

CREATE TABLE storage_lab.accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_name TEXT NOT NULL,
    balance NUMERIC(12,2) NOT NULL CHECK (balance >= 0),
    note TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
) WITH (fillfactor = 85);

INSERT INTO storage_lab.accounts (owner_name, balance, note)
VALUES
    ('Nguyen An', 1000000.00, 'Individual customer'),
    ('Tran Binh', 1500000.00, 'Corporate customer'),
    ('Le Chi',    2500000.00, 'Priority customer')
RETURNING account_id, ctid, owner_name, balance;
~~~

`fillfactor = 85` sets a target fill percentage during inserts/rewrites where applicable, leaving free space on pages for same-page `UPDATE`s. It **does not guarantee** every page stays at 85% or that every `UPDATE` becomes HOT.

Do not assume these tables exist in other databases: schema `storage_lab` isolates the exercise.

### 7.2. Recording initial CTIDs

~~~sql
SELECT
    account_id,
    ctid,
    owner_name,
    balance,
    updated_at
FROM storage_lab.accounts
ORDER BY account_id;
~~~

**Record the actual CTIDs** from your own environment. Small datasets often land in the same block, though that is not a mandatory rule.

### 7.3. Updating inside a transaction and observing immediately

~~~sql
BEGIN;

SELECT account_id, ctid, balance
FROM storage_lab.accounts
WHERE account_id = 1;

UPDATE storage_lab.accounts
SET balance = balance + 100000.00,
    updated_at = clock_timestamp()
WHERE account_id = 1
RETURNING account_id, ctid, balance;

SELECT account_id, ctid, balance
FROM storage_lab.accounts
WHERE account_id = 1;

ROLLBACK;
~~~

What to observe:

- `UPDATE ... RETURNING ctid` returns **the new version's location**.
- The new version shares the same `account_id` yet has a **different CTID** from the pre-update version.
- After `ROLLBACK`, the updated version is uncommitted; other transactions never see the tested increase.
- Whether the old and new locations sit in the same block or different blocks depends on page free space and PostgreSQL conditions.

You can re-run:

~~~sql
SELECT account_id, ctid, balance
FROM storage_lab.accounts
WHERE account_id = 1;
~~~

It displays the active pre-rollback data. **CTIDs are not guaranteed to match fixed numbers** across runs or environments.

### 7.4. When committing an UPDATE

Running:

~~~sql
UPDATE storage_lab.accounts
SET note = 'Information verified'
WHERE account_id = 2
RETURNING account_id, ctid, note;
~~~

in ordinary autocommit mode creates a new version and commits it. A subsequent `UPDATE` creates yet another version. That is the core of **multi-version** heap storage.

## 8. CTID, Indexes, and the Journey to Fetch a Row

### 8.1. Why must a B-tree index reference the heap?

Suppose the table has:

~~~sql
CREATE INDEX idx_accounts_owner_name
ON storage_lab.accounts (owner_name);
~~~

A secondary B-tree index orders keys by `owner_name` and stores pointers to heap tuples, typically as **heap TIDs**.

The query:

~~~sql
SELECT account_id, owner_name, balance
FROM storage_lab.accounts
WHERE owner_name = 'Nguyen An';
~~~

can follow this path:

~~~text
Query WHERE owner_name = 'Nguyen An'
                    |
                    v
          B-tree Index Scan
                    |
                    v
       Entry: key + heap TID
                    |
                    v
    Heap page at block X
                    |
                    v
        Line pointer Y
                    |
                    v
   Matching heap tuple / version
                    |
                    v
   Check visibility and read columns
~~~

The index entry directs PostgreSQL straight to the right page and line pointer instead of scanning the entire heap. Still, the optimizer is **not forced** to use the index: on a three-row table, `Seq Scan` is usually cheaper.

### 8.2. Role of visibility when reading an index

An index entry merely identifies candidate tuples. Under MVCC, PostgreSQL still decides which version is **visible to the query's snapshot**. Some index entries point to dead old versions not yet cleaned up, or to the root of a HOT chain that must be traversed to find the valid version.

Distinguish clearly:

- **Index lookup:** finds candidate locations.
- **Heap access:** reads the tuple containing columns or visibility info.
- **MVCC visibility:** decides whether that version belongs in the query result.

Finding an index entry does not guarantee a currently visible row exists.

### 8.3. Index Only Scan and the Visibility Map

If an index contains every column required by a query, PostgreSQL **may** choose `Index Only Scan`. Because standard PostgreSQL indexes do not store per-tuple MVCC visibility info, the Visibility Map tells PostgreSQL which pages are **all-visible**, allowing it to skip heap visibility checks when safe.

Example:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id
FROM storage_lab.accounts
WHERE account_id BETWEEN 1 AND 3;
~~~

If the plan shows `Index Only Scan`, also inspect **Heap Fetches**: the node name alone does not guarantee zero heap reads. On recently modified tables whose visibility map has not been updated by `VACUUM`, heap fetches still occur.

Exact plans and numbers depend on table data, statistics, and execution timing; do not assume every run produces `Index Only Scan`.

## 9. UPDATE, MVCC, and Version Chains

### 9.1. Why not overwrite the old row in place?

If PostgreSQL overwrote old tuple bytes directly while another transaction was still reading, it would need separate undo storage to preserve snapshots and crash recovery. Heap MVCC instead keeps the **old version** for readers that still need it and writes a **new version** for the change.

Example:

~~~text
Time →
       T1 reads balance = 1,000,000
       |
       |        T2 UPDATE balance = 1,100,000
       |                         |
       |                         T2 COMMIT
       |
       T1 can keep reading the version matching T1's snapshot
       depending on isolation level and query timing
~~~

PostgreSQL inspects heap tuple header fields such as `xmin`, `xmax`, flags, and transaction commit status to decide visibility. System columns `xmin` and `xmax` can be queried for learning, but **never use raw transaction IDs as business IDs or commit timestamps**.

### 9.2. New CTID and the t_ctid link

When a version is updated, the old version's internal header sets `t_ctid` to point to the newer version. Updating the new version again forms a **version chain**.

~~~text
Heap tuple V1 (balance = 1,000,000)
      t_ctid -----> Heap tuple V2 (balance = 1,100,000)
                             t_ctid -----> Heap tuple V3 (...)
~~~

This conceptual model illustrates updates. Do not assume chains stay intact forever: `VACUUM` and page pruning reclaim obsolete tuples, adjust line pointers, and reuse space when safe.

### 9.3. Why can SELECT still see old data after a commit?

Every statement or transaction operates against a **snapshot** governed by its isolation level.

- Under `READ COMMITTED` (PostgreSQL's common default), each `SELECT` takes a fresh snapshot at **statement start**. Later statements in the same transaction can see commits made by other transactions.
- Under `REPEATABLE READ`, statements share a transaction-level snapshot per PostgreSQL rules, so commits made by others after the snapshot do not appear in subsequent reads.
- A transaction still sees **its own modifications** appropriately rather than being blind to its own writes.

This explains why **multiple heap tuple versions** coexist on disk while a normal SQL query returns only **one valid version**.

## 10. HOT Update: Optimizing Updates on the Same Page

### 10.1. What is HOT?

**HOT (Heap-Only Tuple)** is an optimization where PostgreSQL places an updated tuple version **on the same heap page** without inserting new index entries in ordinary indexes.

Conceptually, key prerequisites include:

1. No indexed column values change in a way requiring index updates (including index expressions and partial index predicates where applicable).
2. The current heap page has enough free space for the new tuple version.
3. PostgreSQL version and access-method rules permit HOT.

Thus, an `UPDATE` modifying only an **unindexed** column is a HOT candidate, though never guaranteed. If the page is full or an expression index touches that column, a regular non-HOT update occurs.

### 10.2. How HOT reduces index churn

Without HOT:

~~~text
B-tree index
    ├── key → TID V1
    └── key → TID V2  (may need a new entry)

Heap
    ├── V1
    └── V2
~~~

With HOT, conceptually:

~~~text
B-tree index
    └── key → root TID in Heap Page A
                      |
                      v
                 HOT chain
                 V1 → V2 → V3
                 (within the same page)
~~~

When obsolete versions become eligible for pruning, PostgreSQL uses a **redirect line pointer** so the index continues reaching the live version without touching index pages. This reduces index churn and downstream VACUUM work.

**HOT still creates a new heap tuple version, and the new version's CTID can differ.** It does not turn `UPDATE` into an in-place overwrite at the SQL level.

### 10.3. Observing HOT updates

Inspect statistics via:

~~~sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'storage_lab'
  AND relname = 'accounts';
~~~

- `n_tup_upd`: cumulative count of tuple updates.
- `n_tup_hot_upd`: count of updates recorded as HOT.
- `n_dead_tup`: estimated count of dead tuples.

Stats may take a short time to flush to the statistics views and accumulate since the last stats reset; never divide numbers across a handful of test rows to declare optimal HOT ratios.

### 10.4. Fillfactor and space for HOT

PostgreSQL supports the table storage parameter:

~~~sql
ALTER TABLE storage_lab.accounts SET (fillfactor = 80);
~~~

During subsequent inserts or table rewrites, a lower fillfactor leaves breathing room on pages, making HOT updates more likely on update-heavy tables. However:

- Changing fillfactor **does not immediately reorganize existing pages**.
- Lower fillfactor spreads data across **more pages**, increasing sequential scan I/O.
- If updates modify indexed columns or rows are wide, extra page space will not enable HOT.
- Measure read/write workload, HOT ratio, page bloat, and table size.

No single fillfactor fits every table. Append-only tables and heavily updated tables have very different needs.

## 11. VACUUM, Pruning, and Slot Reuse

### 11.1. UPDATE and DELETE leave history to clean up

MVCC writes leave behind older tuple versions no longer needed by new queries yet temporarily retained for older snapshots. Once no active transaction can see an old version, PostgreSQL **reclaims and reuses that space** via maintenance.

Two related concepts:

- **Page pruning:** cleans dead versions within a single page opportunistically when safe during page access or updates.
- **VACUUM:** removes dead tuples, updates auxiliary maps (`FSM`, `VM`), frees space for reuse, and prevents transaction ID wraparound via freezing.

Try in the lab:

~~~sql
VACUUM (VERBOSE) storage_lab.accounts;
~~~

This is a maintenance command—**do not run it in production without authorization**. Routine `VACUUM` is normally handled automatically by autovacuum; DBAs do not manually vacuum after every update.

### 11.2. Regular VACUUM does not repack the whole table

A regular `VACUUM` primarily makes space **reusable inside the relation**; it does not rewrite the entire table into a minimal contiguous file or reorder live rows.

Free pages at the very end of a relation may sometimes be truncated back to the OS. Most reclaimed space, however, stays inside the file for **subsequent PostgreSQL writes**.

**`VACUUM FULL` is different:** it **rewrites the entire table**, shrinking disk footprint at the cost of heavy locks, extra temporary disk space, and mass CTID changes.

### 11.3. Which operations affect CTID?

| Operation | Typical impact |
|---|---|
| `SELECT` | Does not create new tuples merely from reading; may update hint bits / page metadata |
| `INSERT` | Creates a new tuple at an available slot |
| `UPDATE` | Creates a new tuple version; the new version's CTID can differ |
| `DELETE` | Marks the version per MVCC; only eligible for cleanup afterward |
| `VACUUM` (regular) | Prunes/cleans dead tuples and reuses slots; does not actively rewrite all live tuples |
| `VACUUM FULL` | Rewrites the table; can change CTIDs of live tuples |
| `CLUSTER` | Rewrites the table ordered by an index; CTIDs can change |
| `REINDEX` | Rebuilds indexes; does not rewrite the heap table by default |
| `TRUNCATE` | Discards data and assigns fresh storage; all old TIDs become meaningless |

Use this table as an operational rule. Never assume CTID is a stable key just because "we only run regular VACUUM today": updates or rewrites will eventually happen.

### 11.4. Why are long transactions dangerous?

A read transaction holding an old snapshot open prevents PostgreSQL from cleaning dead tuples that snapshot might still observe. When applications leave connections `idle in transaction` for long periods:

- Dead tuples accumulate.
- Heaps and indexes bloat.
- Vacuuming and XID freezing fall behind.
- Queries and writes suffer extra I/O and maintenance overhead.

MVCC boosts concurrency, at a **version-retention cost** that must be bounded by tight transaction boundaries and healthy VACUUM.

## 12. Free Space Map and Visibility Map

### 12.1. FSM helps locate pages with free space

When inserting or updating a tuple, PostgreSQL needs a page with enough room for the tuple and a line pointer. The **Free Space Map** tracks approximate free space across pages of a relation.

If the current page lacks space, the tuple goes to another page. That is one reason an `UPDATE` produces a CTID in a different block.

FSM is not an exact list of free slots, nor does a page full of **dead tuples** immediately register reusable free space before pruning/VACUUM reclaims them.

### 12.2. VM tracks two critical page flags

The Visibility Map maintains page-level bits, notably:

- **All-visible:** every tuple on the page is visible to all current and future transactions, allowing certain operations to skip heap visibility checks.
- **All-frozen:** every tuple on the page is frozen against transaction ID wraparound.

VM differs from FSM: a page can be **completely full** yet all-visible, or have plenty of free space yet not be all-visible.

### 12.3. Why does VM matter for Index Only Scan?

Even when an index contains every column a query needs, PostgreSQL must guarantee returned row versions are visible to the snapshot. When the VM marks a heap page all-visible, PostgreSQL skips checking the heap for visibility.

On newly inserted or updated pages, the VM bit is cleared. `VACUUM` is typically responsible for setting the all-visible bit again once safe.

This explains why **the exact same index** can show different `Heap Fetches` counts across two runs of the exact same SQL.

## 13. TOAST: How Can a Row with Huge TEXT Still Fit?

### 13.1. Page limits and oversized values

With ~8 KiB pages, a natural question arises:

> If a row has a `text` column hundreds of kilobytes long or a huge `jsonb`, how does PostgreSQL store it?

PostgreSQL uses **TOAST (The Oversized-Attribute Storage Technique)** to handle large variable-length attributes. Depending on data type, storage strategy, value size, and tuple length, PostgreSQL can:

1. Store the value **inline inside the heap tuple** if small enough.
2. **Compress** the value if beneficial and permitted by the column strategy.
3. **Move oversized data out-of-line to a TOAST table** in an auxiliary relation, leaving a compact pointer in the main heap tuple.
4. Combine compression and out-of-line storage per storage policy.

Not every `text` column goes to TOAST. Short strings sit inline inside the tuple; only large values trigger compression or out-of-line storage according to internal thresholds and column storage settings.

### 13.2. Visualizing TOAST storage

~~~text
Heap table: documents
  Page 10
    LP #4
      Tuple
        id = 7
        title = "Guide"
        body = [TOAST external pointer]
                      |
                      v
Secondary TOAST relation
   chunk 1, chunk 2, chunk 3, ...
   majority of body data
~~~

A TOAST table has its own heap and index to reassemble chunks. Therefore, a long `text` column's disk footprint may live largely outside the main table's `main fork`.

### 13.3. Checking in SQL

Create a lab table:

~~~sql
CREATE TABLE storage_lab.documents (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);

INSERT INTO storage_lab.documents (title, body)
VALUES (
    'Long text',
    repeat('PostgreSQL guide content. ', 10000)
);

SELECT
    document_id,
    pg_column_size(body) AS stored_value_bytes,
    length(body) AS logical_characters,
    octet_length(body) AS logical_bytes
FROM storage_lab.documents;
~~~

Explanation:

- `length(body)` is the character count of the string.
- `octet_length(body)` is the logical byte length of the string in the database encoding.
- `pg_column_size(body)` reflects the internal stored/compressed representation size, which can be far smaller than logical bytes due to compression.

A `repeat(...)` string is highly repetitive and **compresses unusually well**. Do not use this synthetic string to benchmark real TOAST throughput on incompressible payloads. Use representative data for benchmarks.

Inspect the TOAST relation:

~~~sql
SELECT
    c.oid::regclass AS table_name,
    c.reltoastrelid::regclass AS toast_relation,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
WHERE c.oid = 'storage_lab.documents'::regclass;
~~~

A table can have an associated TOAST relation created from its schema definition **without necessarily** storing any out-of-line values yet. Seeing TOAST metadata does not prove rows are currently TOASTed externally.

### 13.4. TOAST and query cost

A query needing only ID and title:

~~~sql
SELECT document_id, title
FROM storage_lab.documents
WHERE document_id = 1;
~~~

avoids decompressing or fetching the entire `body` when it is not needed in the output.

By contrast:

~~~sql
SELECT document_id, body
FROM storage_lab.documents
WHERE document_id = 1;
~~~

must fetch and detoast the oversized value, adding CPU, I/O, and network transfer cost.

This is why on tables with huge `text`/`jsonb`/`bytea` columns, you should **select only the columns you need** instead of writing `SELECT *` out of habit.

## 14. Inspecting Pages and Tuples with the pageinspect Extension

### 14.1. When is pageinspect needed?

System columns like `ctid` and SQL size views provide high-level visibility. To **look directly inside page headers and line pointers** while studying architecture, PostgreSQL ships the `pageinspect` extension in standard distributions.

> **This section is strictly for authorized labs/DBAs.** `pageinspect` reads low-level raw page contents, can expose sensitive data, and requires elevated privileges. Never install extensions or grant broad permissions in production just to study.

When permitted:

~~~sql
CREATE EXTENSION IF NOT EXISTS pageinspect;
~~~

This installs into the **current database**, subject to privileges and extension availability. If you hit permission or missing-extension errors, stick to the read-only SQL views in earlier sections rather than requesting admin privileges.

### 14.2. Viewing PageHeaderData of block 0

Assuming `storage_lab.accounts` is populated and block 0 exists:

~~~sql
SELECT *
FROM page_header(
    get_raw_page('storage_lab.accounts', 0)
);
~~~

Depending on extension version, columns include:

- `lsn`
- `checksum`
- `flags`
- `lower`
- `upper`
- `special`
- `pagesize`
- `version`
- `prune_xid`

You can match `lower` and `upper` against the page free-space diagram. **No single pair of `lower`/`upper` values is expected to match across runs**, because heap pages evolve with `INSERT`/`UPDATE`/`VACUUM`.

### 14.3. Listing line pointers and tuple headers on page 0

~~~sql
SELECT
    lp,
    lp_off,
    lp_flags,
    lp_len,
    t_xmin,
    t_xmax,
    t_ctid,
    t_hoff
FROM heap_page_items(
    get_raw_page('storage_lab.accounts', 0)
)
ORDER BY lp;
~~~

Meaning:

- `lp`: item pointer number within the page.
- `lp_off`: byte offset the line pointer targets when payload exists.
- `lp_flags`: numeric code for `LP_UNUSED`, `LP_NORMAL`, `LP_REDIRECT`, or `LP_DEAD`.
- `lp_len`: payload length recorded in the line pointer.
- `t_xmin`, `t_xmax`: transaction metadata when a tuple header is present.
- `t_ctid`: item pointer tracking the version chain.
- `t_hoff`: byte offset where tuple attribute data starts.

A line pointer not in `LP_NORMAL` state does not necessarily have a valid tuple header representing a normal SQL row. Do not treat every row from `heap_page_items` as a live user row.

### 14.4. Matching SQL ctid against lp from pageinspect

First:

~~~sql
SELECT ctid, account_id, owner_name
FROM storage_lab.accounts
ORDER BY account_id;
~~~

If a row reports CTID `(0,3)`, it is referenced via **line pointer 3 of block 0**. Look for `lp=3` in `heap_page_items(get_raw_page(..., 0))`.

Note that after updates, rollbacks, or VACUUM, a raw page can contain dead or uncommitted tuples. `get_raw_page` reads raw physical page bytes **without applying SQL MVCC visibility filtering like an ordinary `SELECT`**.

### 14.5. What not to conclude from raw pages

- A non-zero `t_xmax` alone does not prove the tuple was successfully deleted.
- Many line pointers do not imply an equal number of visible SQL rows.
- Having free space on a page does not guarantee any arbitrary-sized row fits.
- A `checksum` of 0 does not indicate corruption if page checksums are disabled.
- Raw pages are great for learning internals, not a stable API for business queries.

Diagnosing genuine page corruption, checksum failures, or WAL incidents requires dedicated recovery runbooks—not a single `pageinspect` query in a lab.

## 15. Measuring Relation Size and Page Counts with SQL

### 15.1. Main fork size

~~~sql
SELECT
    pg_relation_size('storage_lab.accounts'::regclass) AS main_bytes,
    current_setting('block_size')::integer AS block_bytes,
    pg_relation_size('storage_lab.accounts'::regclass)
        / current_setting('block_size')::integer AS main_pages;
~~~

For ordinary heap tables, `pg_relation_size(relation)` defaults to the main fork. Dividing by block size yields the number of blocks allocated in the main fork at the time of the query.

### 15.2. Comparing table, index, and total storage

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('storage_lab.accounts'::regclass)
    ) AS main_heap_size,
    pg_size_pretty(
        pg_indexes_size('storage_lab.accounts'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('storage_lab.accounts'::regclass)
    ) AS total_relation_size;
~~~

`pg_total_relation_size` includes indexes, TOAST, and auxiliary forks in addition to the main heap. Never treat **main heap size** as "total disk used by the table."

### 15.3. FSM and VM

~~~sql
SELECT
    pg_relation_size('storage_lab.accounts'::regclass, 'main')
        AS main_bytes,
    pg_relation_size('storage_lab.accounts'::regclass, 'fsm')
        AS fsm_bytes,
    pg_relation_size('storage_lab.accounts'::regclass, 'vm')
        AS vm_bytes;
~~~

Auxiliary forks may not exist yet or may be tiny depending on table activity. PostgreSQL creates and updates them as needed. Never infer "no dead tuples" or "no MVCC" simply because an auxiliary fork is 0 bytes.

### 15.4. pg_class: relpages and reltuples are statistics

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    c.relpages,
    c.reltuples
FROM pg_class AS c
WHERE c.oid = 'storage_lab.accounts'::regclass;
~~~

- `relpages`: estimated page count for planner statistics.
- `reltuples`: estimated live tuple count for planner statistics.

These values are not updated instantaneously on every `INSERT`/`UPDATE`. Never use `reltuples` as an exact replacement for `COUNT(*)`.

When permitted in the lab:

~~~sql
ANALYZE storage_lab.accounts;
~~~

`ANALYZE` refreshes planner statistics; it does not change page/block layout and does not build indexes. In production, it consumes I/O and can alter query plans, so run it under operational governance.

## 16. Common Misconceptions About Physical Location

### Misconception 1: "CTID is a row number"

False. CTID is `(block number, line pointer number)`. Tables have no guaranteed SQL order without `ORDER BY`, and CTID is not a business ID.

### Misconception 2: "The offset in CTID is a byte offset"

False. The second number is the **line pointer slot index**. The line pointer stores the tuple's byte offset.

### Misconception 3: "Every UPDATE modifies the old row in place"

False in standard MVCC heap storage: `UPDATE` writes a new tuple version while retaining the old version until cleanup is safe. HOT optimizes **avoiding index writes**, not skipping heap tuple versioning.

### Misconception 4: "Every UPDATE must insert new index entries"

Not always. When eligible for **HOT**, PostgreSQL places the new version on the same heap page without adding new entries to ordinary indexes.

### Misconception 5: "VACUUM always shrinks table files on disk"

Regular `VACUUM` primarily makes space **reusable inside the relation**. `VACUUM FULL` rewrites and shrinks the file, at the cost of heavy locks and potential CTID changes.

### Misconception 6: "Because line pointers stay stable, rows are identified forever"

Line pointers keep CTID stable during intra-page compaction and HOT chains, yet slots are eventually freed and reused later. Always use primary keys or unique business keys for durable references.

### Misconception 7: "A long VARCHAR/TEXT value must fit inside 8 KiB"

TOAST compresses or moves oversized attributes out of the main heap tuple, allowing huge variable-length columns to exceed page size cleanly.

### Misconception 8: "Index Only Scan never reads the heap"

PostgreSQL still needs visibility guarantees; whenever the VM has not marked a page all-visible, `Index Only Scan` performs **Heap Fetches**.

### Misconception 9: "One physical tuple equals one row returned by SELECT"

Under MVCC, a page can hold old, new, uncommitted, and dead versions. Snapshots and transaction statuses decide what SQL returns.

### Misconception 10: "You can inspect raw pages in production just like running SELECT"

`pageinspect` is a low-level privileged tool that bypasses SQL MVCC filtering and can expose raw bytes. Use it intentionally only in authorized environments.

### Misconception 11: "One table = one single file"

Relations span forks, segments, separate indexes, and optional TOAST relations. Physical layout involves far more than a single heap file.

### Misconception 12: "With ctid available, we don't need a PRIMARY KEY"

Primary keys provide logical identity, integrity, and relational joins. CTID is only a transient physical tuple-version address with none of those guarantees.

## 17. Summary Diagram: From Index to Tuple and MVCC

~~~mermaid
flowchart TD
    A["SELECT ... WHERE account_id = 42"] --> B{"Planner chooses access path"}
    B -- "Index Scan" --> C["B-tree index lookup"]
    B -- "Seq Scan" --> D["Scan heap pages"]
    C --> E["Heap TID: (block, line pointer)"]
    E --> F["Read page and line pointer"]
    D --> F
    F --> G["Heap tuple / HOT chain if needed"]
    G --> H{"Version visible to snapshot?"}
    H -- "Yes" --> I["Read attributes, TOAST if needed"]
    H -- "No" --> J["Skip / follow appropriate version"]
    J --> G
    I --> K["Return SQL result row"]
~~~

This diagram shows the **conceptual layers**. PostgreSQL's executor includes further optimizations such as bitmap scans, index-only scans, and diverse index access methods; not every query follows one rigid path.

## 18. Practice Exercises

These exercises use `storage_lab.accounts` from section 7 and `storage_lab.documents` from section 13 where needed. Never run modifications or raw-page inspections in production without authorization.

### Exercise 1 — Checking block size

Write SQL to retrieve PostgreSQL's active block size. If a table's main fork is 1,638,400 bytes and block size is 8192 bytes, how many main-fork pages does the table contain?

### Exercise 2 — Explaining CTID

A row returns `ctid='(12,7)'`. Explain both numbers accurately, and explain why you must not infer it means "the 7th row of customer 12."

### Exercise 3 — Observing an update

Pick `account_id=1`, record its initial CTID, run an `UPDATE ... RETURNING ctid` inside a transaction, and roll back. State what you can validly conclude from the new CTID.

### Exercise 4 — Why do line pointers exist?

Suppose a tuple's payload shifts byte offset within the same page during compaction. Why does referencing `(block, line pointer number)` avoid updating every external pointer outside that page?

### Exercise 5 — MVCC and tuple counts

A table has 100 currently visible logical rows. Why can a raw page inspection tool see more than 100 tuple headers? Why does `SELECT COUNT(*)` not necessarily equal the row count from `heap_page_items`?

### Exercise 6 — Choosing HOT vs. non-HOT

A table has indexes on `account_id` and `owner_name`. You update only `note`; under what conditions can the update be HOT? What if you update `owner_name`? What role does page free space play?

### Exercise 7 — VACUUM and CTID

Compare regular `VACUUM`, `VACUUM FULL`, and `CLUSTER` across: whether they rewrite the whole table, whether they can change live tuples' CTIDs, whether they shrink file size, and their operational impact.

### Exercise 8 — TOAST

A table has a 300 KiB `body TEXT` column. How can PostgreSQL store it despite an 8 KiB page size? Explain TOAST's two main techniques and why `SELECT id, title` can be cheaper than `SELECT *`.

### Exercise 9 — Inspecting sizes and forks

Write SQL to fetch main, FSM, VM, index, and total relation sizes. Explain why total size can be many times larger than the main fork.

### Exercise 10 — Index Only Scan

A query selects only columns present in a B-tree index, yet `EXPLAIN ANALYZE` reports `Heap Fetches > 0`. Does that mean the index is broken? What is the Visibility Map's role?

### Exercise 11 — Inspecting pages with pageinspect

In an authorized lab database, use `page_header(get_raw_page(...,0))` and `heap_page_items(...)` to inspect `lower`, `upper`, `lp`, and `lp_off`. Why must you check `lp_flags` before interpreting a tuple header?

### Exercise 12 — Choosing an application key

A developer wants to store `orders.ctid` in `payments` as a foreign key because CTID "looks up fast." Explain at least four risks and recommend a proper design.

## 19. Suggested Solutions

### Exercise 1

~~~sql
SELECT current_setting('block_size')::integer AS bytes_per_page;
~~~

If block size equals 8192 bytes:

~~~text
1,638,400 / 8,192 = 200 pages
~~~

This calculation is illustrative; always check the actual block size and confirm you are measuring the target relation's main fork.

### Exercise 2

`(12,7)` means **block 12, item pointer / line pointer 7 within that block**. The offset is neither a byte offset nor a business ID. This physical address can change on updates or rewrites and implies no business ordering.

### Exercise 3

~~~sql
BEGIN;
SELECT account_id, ctid
FROM storage_lab.accounts
WHERE account_id = 1;

UPDATE storage_lab.accounts
SET note = note || ' - check'
WHERE account_id = 1
RETURNING account_id, ctid;

ROLLBACK;
~~~

`UPDATE` creates a new version with that version's CTID; the new CTID may stay in the same block or move to another depending on page space. `ROLLBACK` discards uncommitted changes per transaction semantics. Never save the new CTID into another table as a durable identifier.

### Exercise 4

Line pointers provide an indirection layer between TID and tuple byte offset. During page compaction, PostgreSQL updates the offset inside the line pointer without changing `(block number, line pointer number)` in valid external references.

### Exercise 5

MVCC `UPDATE`/`DELETE` leaves behind **uncleaned old versions**, alongside uncommitted or obsolete tuples. `COUNT(*)` counts rows **visible to the SQL snapshot**, not every item pointer on a raw page.

### Exercise 6

Updating `note` can be HOT if no index key/expression/predicate requires updating and **the same page has enough free space**. Updating indexed `owner_name` requires index maintenance and therefore cannot be HOT in the same way. A lower fillfactor reserves extra space but never guarantees HOT.

### Exercise 7

- Regular `VACUUM`: cleans dead tuples and makes space reusable; does not rewrite all live tuples like a fresh table.
- `VACUUM FULL`: rewrites the table, can shrink disk footprint, requires strong locks, and can change CTIDs.
- `CLUSTER`: rewrites/reorders the heap by a chosen index, can change CTIDs, and has major operational impact.

Never run the last two in production just to inspect CTID behavior.

### Exercise 8

TOAST **compresses** values and/or stores oversized chunks **in an auxiliary relation**, keeping a reference in the main tuple. `SELECT id, title` avoids reading and detoasting `body` when unused. `SELECT *` incurs extra I/O, CPU, and network transfer.

### Exercise 9

~~~sql
SELECT
    pg_relation_size('storage_lab.accounts'::regclass, 'main') AS main_bytes,
    pg_relation_size('storage_lab.accounts'::regclass, 'fsm') AS fsm_bytes,
    pg_relation_size('storage_lab.accounts'::regclass, 'vm') AS vm_bytes,
    pg_indexes_size('storage_lab.accounts'::regclass) AS index_bytes,
    pg_total_relation_size('storage_lab.accounts'::regclass) AS total_bytes;
~~~

Total size includes indexes, TOAST, auxiliary forks, and related storage, so it can far exceed the main heap.

### Exercise 10

Not necessarily broken. `Index Only Scan` must still guarantee MVCC visibility; when a page is not marked all-visible in the Visibility Map, the executor falls back to checking the heap. `Heap Fetches > 0` is completely normal behavior.

### Exercise 11

~~~sql
SELECT lower, upper, special, pagesize
FROM page_header(get_raw_page('storage_lab.accounts', 0));

SELECT lp, lp_off, lp_flags, lp_len, t_ctid
FROM heap_page_items(get_raw_page('storage_lab.accounts', 0))
ORDER BY lp;
~~~

`LP_UNUSED`, `LP_REDIRECT`, and `LP_DEAD` slots do not behave like `LP_NORMAL`; do not interpret every row as a valid SQL tuple.

### Exercise 12

CTID changes after `UPDATE`, `VACUUM FULL`, and `CLUSTER`; slots get reused; there is no cross-run/cross-relation/cross-partition identity guarantee; and it cannot enforce logical foreign-key integrity. Instead, use `orders.order_id` as the primary key and `payments.order_id` as a proper foreign key referencing it.

## 20. Conclusion

PostgreSQL organizes heap tables into **pages/blocks** containing a page header, a **line pointer** array, free space, and **heap tuples**. Each tuple is a **physical row version** carrying MVCC metadata and column values. Tuple locations are addressed by **TID `(block, offset)`**, and the `ctid` system column exposes the physical location of the row version currently returned.

Line pointers let PostgreSQL move tuple payloads within a page without immediately breaking external slot references. Yet CTID is **never durable like a business key**: updates create new tuple versions, table rewrites relocate tuples, and old slots get reused. MVCC, HOT, VACUUM, FSM, VM, and TOAST work together to deliver **correctness, concurrency, and storage efficiency**.

When inspecting storage, start with safe SQL such as `SELECT ctid`, `pg_relation_size`, `pg_class`, and `EXPLAIN`. Reserve `pageinspect` for authorized environments when examining headers and item pointers directly. Understanding this layout explains why indexes point into the heap, why `UPDATE` creates version history, why `VACUUM` matters, and why **primary keys remain the right durable identifier for application data**.
