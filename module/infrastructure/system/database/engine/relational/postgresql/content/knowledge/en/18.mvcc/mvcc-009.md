# Visibility Map, Freezing, and What They Mean for Queries in PostgreSQL

PostgreSQL uses **MVCC (Multi-Version Concurrency Control)** to allow multiple transactions to read and write concurrently without forcing every `SELECT` to wait on every `UPDATE`. When a row is modified, PostgreSQL normally creates a **new row version** in the heap and retains the old version for transactions that may still need to see it.

This model is great for concurrency, yet raises three important operational questions:

1. How does PostgreSQL know that a heap page can be treated as **visible to all transactions** without checking every individual tuple?
2. How does PostgreSQL keep rows alive for years while remaining safe when **transaction IDs (XIDs)** wrap around?
3. Why can a query with an index covering every required column still need to read the **heap**, and why does `VACUUM` speed up certain `Index Only Scan` queries?

The two mechanisms connecting these three questions are the **visibility map (VM)** and **freezing**.

- The **visibility map** stores per-**heap-page** state: whether all tuples on the page are visible to all transactions, and whether tuples on the page have been frozen with respect to XIDs/MultiXacts.
- **Freezing** is part of MVCC maintenance to prevent **transaction ID wraparound** and allow stable pages to be marked `all-frozen`.
- **Index-only scans** can rely on a heap page's `all-visible` flag to return data straight from the index without visiting the heap to verify visibility for each index entry.

This lesson belongs to the **MVCC** chapter of the **Database Engine Relational PostgreSQL** module. We will build accurate intuition, look at system-inspection SQL queries, run experiments on a dedicated table, and understand when optimizing `VACUUM` genuinely helps query performance.

---

## 1. Recap of MVCC: One Logical Row Can Have Multiple Physical Versions

Consider a table:

~~~sql
CREATE TABLE demo_account (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(12, 2) NOT NULL
);

INSERT INTO demo_account(account_id, balance)
VALUES (101, 1000.00);
~~~

After a transaction runs:

~~~sql
UPDATE demo_account
SET balance = 1200.00
WHERE account_id = 101;
~~~

PostgreSQL does not simply overwrite the old tuple's bytes in place. Normally, `UPDATE` creates a new tuple version; the old version remains for a while to serve MVCC and is reclaimed once no transaction needs it anymore.

Conceptual model:

~~~text
Logical row: account_id = 101

Old version: balance=1000
    xmin = creating transaction
    xmax = updating/deleting transaction (when applicable)

New version: balance=1200
    xmin = transaction creating the new version
    xmax = not yet deleted/updated (when applicable)
~~~

`xmin` and `xmax` are system fields related to transaction visibility; they are not business data and should never replace application-managed versions.

Under different snapshots, PostgreSQL decides which version is visible. Hence there is only **one logical row**, yet the heap may hold uncleaned physical versions.

### 1.1. COMMITting a Transaction Does Not Mean VACUUM Has Run

After an `UPDATE` commits:

- The new version becomes visible to eligible snapshots.
- The old version may not yet be cleanable if another transaction still needs it.
- Even when cleanable, the old version may still await `VACUUM` or appropriate pruning.
- The page's visibility map `all-visible` flag has likely been cleared by the modification.

That is why **committing**, **cleaning dead tuples**, **marking `all-visible`**, and **freezing XIDs** are distinct events.

## 2. Heap Pages Are the Unit of the Visibility Map

PostgreSQL stores table data in **heap pages**. The common page size is **8 KiB** in default builds, though you should verify actual configuration:

~~~sql
SHOW block_size;
~~~

A single page can hold many tuples and versions of different rows.

Illustration:

~~~text
Heap relation: product

Page 0    [tuple A] [tuple B] [tuple C]
Page 1    [tuple D] [tuple E] [tuple F]
Page 2    [tuple G] [tuple H] [tuple I]
...
~~~

The visibility map does not store an entry per SQL row. It stores **one pair of flags per heap page**.

This leads to an important consequence:

> Modifying just a single tuple on a page makes that entire page lose `all-visible` eligibility, even though almost all remaining tuples on it are committed and readable as usual.

Index entries pointing to tuples on this page may once again need heap visibility checks.

## 3. What Is the Visibility Map?

The **visibility map** is an auxiliary fork of a heap relation recording per-page visibility and freezing status. In modern PostgreSQL versions, it holds **two bits per heap page**:

1. **`all-visible`**: all relevant tuples on the page are known to be visible to every transaction under MVCC rules; index-only scans can exploit this.
2. **`all-frozen`**: relevant transaction metadata on the page has reached frozen status, so the page needs no further freezing work for existing versions.

Diagram:

~~~text
                       Heap
             +----------+----------+
             |                     |
          Page 0                 Page 1
             |                     |
             v                     v
        Visibility map (VM)

        Page 0: all_visible = 1
                all_frozen  = 1

        Page 1: all_visible = 0
                all_frozen  = 0
~~~

An **`all-frozen`** page is also considered **`all-visible`**. Conversely, an **`all-visible`** page is not necessarily **`all-frozen`**.

### 3.1. Table Distinguishing the Two Flags

| State | Primary Meaning | Important Consequence |
|---|---|---|
| `all_visible=0` | No guarantee the page is visible to all transactions | Index-only scans may have to visit the heap |
| `all_visible=1, all_frozen=0` | Page qualifies as `all-visible`, but still holds XID/MultiXact metadata needing freezing later | Index-only scans can skip heap fetches; future `VACUUM` may still need to freeze |
| `all_visible=1, all_frozen=1` | Page is both `all-visible` and frozen under applicable rules | Helps both index-only scans and anti-wraparound `VACUUM` efficiency |
| `all_visible=0, all_frozen=1` | Not a valid VM state to expect | `all-frozen` implies `all-visible` |

**Do not equate the two flags.** `all-visible` answers current page-wide visibility; `all-frozen` additionally answers transaction ID lifecycle.

## 4. Where Does the VM Live and How Does It Differ From Heap/Indexes?

PostgreSQL stores a relation across file forks, commonly including:

- **Main fork:** primary data of the heap or index.
- **FSM (Free Space Map):** approximate information about reusable free space on pages.
- **VM (Visibility Map):** `all-visible`/`all-frozen` status for heap pages.

Physical filenames may carry suffixes like `_fsm` or `_vm`, though regular applications should never touch those files directly. PostgreSQL manages them and maintains WAL/consistency internally.

### 4.1. The VM Is Not an Index

The visibility map:

- Does not map business keys to row locations.
- Does not locate SKUs, emails, or time ranges like a B-tree.
- Does not replace primary keys, unique constraints, or real indexes.
- Simply tells the engine **whether a heap page is safe for skipping certain visibility checks**.

How indexes and the VM work together:

~~~text
B-tree Index
  |
  +--> index entry contains key/INCLUDE columns
  |
  +--> TID points to heap page
           |
           +--> Check VM: is page all-visible?
                    |
                    +-- YES -> can return from index
                    |          without accessing heap
                    |          to verify visibility
                    |
                    +-- NO  -> must read heap and
                               check tuple visibility
~~~

The "can return from index" condition holds only when the index method supports index-only scans and the index contains all columns the query needs. The VM never turns an index missing columns into a covering index.

## 5. "Visible to All Transactions" Is Not "Row Committed"

A committed tuple may be visible to one snapshot, yet **not necessarily** visible to every active snapshot.

Example:

~~~text
T1: transaction A starts and holds an old snapshot.
T2: transaction B INSERTs a new row.
T3: transaction B COMMITs.
T4: transaction A may still not see the new row,
    depending on isolation/snapshot.
~~~

Thus "B committed" is not enough to declare the whole page containing the new row `all-visible`.

The VM flag carries a stronger guarantee: PostgreSQL has verified the page meets safety conditions to skip heap visibility checks for corresponding index entries.

### 5.1. Page-Level Visibility, Not Query-Specific

`all-visible` does not mean "all rows on the page satisfy `WHERE price > 100`." Nor does it mean "the current session can see all tuples under access privileges."

This flag is **global page-level MVCC metadata**, independent of business filters and authorization policies of any particular `SELECT`.

### 5.2. Row-Level Security Is Not Handled by the Visibility Map

If a table uses RLS, PostgreSQL must still apply policies and SQL predicates. The VM provides no authorization mechanism and cannot let users view rows they are forbidden from seeing.

The VM only optimizes the physical/MVCC visibility check when safe.

## 6. When Is the all-visible Flag Set?

In normal operations, **`VACUUM`** is the primary mechanism that checks and marks eligible pages as `all-visible`.

Overview:

1. A page holds tuples that satisfy visibility eligibility.
2. `VACUUM` evaluates tuple states and required horizons.
3. Once the page qualifies, PostgreSQL marks `all-visible` in the VM.
4. Subsequent index-only scan queries can leverage that flag.

This is not a promise that `VACUUM` marks **every page** `all-visible`. Pages with tuples still affected by open transactions, unreclaimable old versions, or concurrent changes may not yet qualify.

### 6.1. Why Doesn't COMMIT Automatically Re-Set all-visible?

A transaction committing does not mean:

- No older snapshots remain open.
- All dead tuples on the page are eligible for removal.
- A page-wide safety scan was performed.
- The VM was updated to a new state.

PostgreSQL does not force every `COMMIT` to re-scan every touched page to update the VM. Maintaining safe VM bits is tied to `VACUUM` and appropriate storage mechanisms.

## 7. What Clears the all-visible Flag?

Write operations touching a heap page—such as relevant `INSERT`/`UPDATE`/`DELETE`s—make the page no longer all-visible and cause PostgreSQL to **clear** that bit.

Example:

~~~text
Before change:
Page 42: all_visible=1, all_frozen=1

Transaction updates one row on Page 42:
Page 42: all_visible=0, all_frozen=0

After commit:
Page 42 does not automatically revert to all-visible.

Later VACUUM:
If conditions are met, all_visible can be set again;
all_frozen depends on freezing status.
~~~

Flags are cleared **per page**, so updating a few hundred tuples scattered across many pages can clear many VM bits.

### 7.1. UPDATE and New Tuple Versions

`UPDATE` normally creates a new version in the heap and marks the old version obsolete for newer snapshots. Even when an `UPDATE` is HOT (Heap-Only Tuple) under eligible conditions, the modified page still requires MVCC/visibility tracking.

HOT reduces index-update work, yet **does not mean a HOT-updated page stays `all-visible`**.

### 7.2. Do Not Use the VM to Judge Raw Write Speed

A page losing `all-visible` does not mean the write went wrong—that is normal when data changes. Frequently updated tables naturally have a lower percentage of `all-visible` pages than nearly read-only tables.

The goal is not forcing every page to stay `all-visible` at all times, but understanding the **balance between write activity, `VACUUM`, and read workloads**.

## 8. Index-Only Scan: Why Can the Name Be Misleading?

An index-only scan reads data from an index when the index contains every column the query needs.

Example:

~~~sql
CREATE INDEX idx_orders_cover
ON orders (customer_id, created_at DESC, id DESC)
INCLUDE (total_amount);
~~~

A query can use this index:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Column-wise, the index has everything:

- `customer_id` for filtering.
- `created_at` and `id` for ordering.
- `total_amount` in `INCLUDE` to return values.

However, PostgreSQL indexes normally **do not store full MVCC visibility state of heap tuples**. An index entry can point to a tuple not yet visible to the current snapshot or a version that has become obsolete.

Therefore, during an `Index Only Scan`, PostgreSQL checks the VM:

- Heap page is `all-visible` → can skip the heap lookup for that index entry.
- Heap page is not `all-visible` → must visit the heap to verify whether the tuple is visible.

### 8.1. "Index Only Scan" Can Still Show Heap Fetches

A plan showing:

~~~text
Index Only Scan using idx_orders_cover on orders
  Index Cond: (customer_id = 42)
  Heap Fetches: 350
~~~

is not contradictory. It is still an `Index Only Scan` node, yet it had to visit the heap when the VM did not allow skipping visibility checks.

Conversely:

~~~text
Index Only Scan using idx_orders_cover on orders
  Index Cond: (customer_id = 42)
  Heap Fetches: 0
~~~

shows that on that run, the node returned results without needing heap fetches for this metric. Not every query on the same table will necessarily have 0 heap fetches.

### 8.2. What Do High Heap Fetches Tell Us?

It indicates the query is not benefiting fully from `all-visible` pages or requires heap visibility checks.

However, **never directly infer**:

- Heap fetches = number of non-all-visible pages.
- Heap fetches = number of dead rows.
- High Heap Fetches = need to run `VACUUM FULL`.
- Low Heap Fetches = table has zero bloat.

One page may be visited multiple times for different index entries; actual `Heap Fetches` also depends on index scans, predicates, and data distribution.

## 9. Impact on Queries: Before and After VACUUM

Consider a mostly read-only table:

~~~text
Bulk-loaded historical table
         |
         v
Many pages are stable
         |
         v
VACUUM marks pages all-visible
         |
         v
Index-only scans can return data
with very few heap fetches
~~~

Conversely:

~~~text
Frequently UPDATEd transactional table
         |
         v
Many pages were recently modified
         |
         v
all-visible cleared on those pages
         |
         v
Index-only scans must check the heap
         |
         v
Heap Fetches can increase
~~~

This is a **mechanism that changes performance** without changing SQL or indexes. For the exact same query, differing ratios of `all-visible` heap pages can yield different execution times.

Still, the PostgreSQL planner also considers statistics, caches, index types, selectivity, table size, and other costs. Having `all-visible` VM bits does not guarantee the planner will pick `Index Only Scan`.

## 10. Experiment: Creating a Table and Covering Index

The SQL below is strictly for a **dedicated lab database**. It creates synthetic data to observe the VM and `Index Only Scan`, not a procedure for production.

~~~sql
CREATE SCHEMA mvcc_lab;

CREATE TABLE mvcc_lab.events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    note TEXT
);

CREATE INDEX idx_events_cover
ON mvcc_lab.events (
    account_id,
    occurred_at DESC,
    id DESC
)
INCLUDE (amount);

INSERT INTO mvcc_lab.events (
    account_id,
    occurred_at,
    amount,
    note
)
SELECT
    (g % 20 + 1)::INTEGER,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second',
    (10000 + g % 5000)::NUMERIC(12, 2),
    NULL::TEXT
FROM generate_series(1, 20000) AS g;
~~~

The table has 20,000 rows, with `account_id` spread across 20 values. `occurred_at` increases steadily with ID, keeping test outcomes easy to follow. The index covers every column needed for a sample pagination query:

~~~sql
SELECT id, occurred_at, amount
FROM mvcc_lab.events
WHERE account_id = 7
ORDER BY occurred_at DESC, id DESC
LIMIT 100;
~~~

`note` is intentionally **excluded from the index** so we can update a non-indexed column in the next experiment.

### 10.1. Running EXPLAIN Before VACUUM

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, occurred_at, amount
FROM mvcc_lab.events
WHERE account_id = 7
ORDER BY occurred_at DESC, id DESC
LIMIT 100;
~~~

Things to observe in the output:

- Does the planner pick `Index Only Scan` or another scan?
- Are there `Heap Fetches`?
- What are `actual rows` and `Buffers`?

Do not expect a fixed `Heap Fetches` number beforehand. Immediately after `INSERT`, VM bits may not yet mark pages `all-visible`; the planner and actual database state determine the plan.

### 10.2. Running VACUUM in the Lab

~~~sql
VACUUM (ANALYZE) mvcc_lab.events;
~~~

`VACUUM` performs MVCC cleanup and marks eligible heap pages `all-visible`. `ANALYZE` updates planner statistics.

**`VACUUM` cannot run inside an explicit transaction block** under normal syntax. Run the command in a session not inside `BEGIN ... COMMIT`.

Re-run:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, occurred_at, amount
FROM mvcc_lab.events
WHERE account_id = 7
ORDER BY occurred_at DESC, id DESC
LIMIT 100;
~~~

If `Index Only Scan` is chosen and relevant pages are `all-visible`, `Heap Fetches` can drop sharply—even to 0.

### 10.3. Why Shouldn't You Draw General Conclusions From One Measurement?

Two `EXPLAIN` runs also differ due to:

- Planner statistics updated by `ANALYZE`.
- Data/caches warmed up by the previous run.
- OS and buffer caches holding pages.
- Exact numbers depending on PostgreSQL version and environment.
- Small tables making sequential scans cheaper.

This experiment illustrates the relationship between **VM, visibility checks, and index-only scans**, not a universal speedup guarantee across all systems.

## 11. Experiment: UPDATE Clears all-visible Benefits

After `VACUUM`, try updating some rows:

~~~sql
UPDATE mvcc_lab.events
SET note = 'reviewed'
WHERE account_id = 7
  AND id <= 2000;
~~~

Because `note` is not in `idx_events_cover`, PostgreSQL **may** use HOT updates if other conditions and page free space allow. Still, the touched heap pages changed, so the VM can lose `all-visible` flags.

Re-run:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, occurred_at, amount
FROM mvcc_lab.events
WHERE account_id = 7
ORDER BY occurred_at DESC, id DESC
LIMIT 1000;
~~~

Depending on which pages hold those rows, `Heap Fetches` can rise. If the query only reads untouched pages or the planner chooses a different path, the effect may be less visible.

Then run:

~~~sql
VACUUM (ANALYZE) mvcc_lab.events;
~~~

and run `EXPLAIN` again to observe the shift.

### 11.1. Why Does Updating an Unindexed Column Still Affect It?

Even when index entries do not need changing for `note`, MVCC still manages heap tuple versions. A recently written page cannot safely be treated as having every tuple visible to every snapshot.

That is the direct link between **MVCC storage** and **index-only queries**.

### 11.2. What About Updating an INCLUDE Column?

If you modify `amount`, that column is `INCLUDE`d in the index. Under normal HOT rules, updating an index-referenced column prevents HOT optimization; index and heap costs therefore differ from updating only `note`.

Never run one HOT experiment and assume all `UPDATE`s behave identically.

## 12. Inspecting the VM With the pg_visibility Extension

PostgreSQL provides the **`pg_visibility`** extension with functions to inspect the visibility map and page states.

In a lab database, if the extension is available and your role has privileges:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_visibility;
~~~

In managed environments, you may lack permission to create extensions or inspect page-level info. Request DBA assistance if needed; never elevate production privileges just to run examples.

### 12.1. Total all-visible and all-frozen Pages

~~~sql
SELECT *
FROM pg_visibility_map_summary(
    'mvcc_lab.events'::regclass
);
~~~

The output has two key numbers:

- `all_visible`: count of heap pages marked `all-visible` in the VM.
- `all_frozen`: count of heap pages marked `all-frozen` in the VM.

Never mistake these numbers for **row counts**. They are **page counts**.

### 12.2. Inspecting Individual Pages

~~~sql
SELECT
    blkno,
    all_visible,
    all_frozen
FROM pg_visibility_map(
    'mvcc_lab.events'::regclass
)
ORDER BY blkno
LIMIT 30;
~~~

You can filter for pages that are not `all-visible`:

~~~sql
SELECT blkno, all_visible, all_frozen
FROM pg_visibility_map(
    'mvcc_lab.events'::regclass
)
WHERE NOT all_visible
ORDER BY blkno
LIMIT 30;
~~~

When the database has concurrent writes, VM state can change after the query runs. Never treat observed results as a permanent snapshot of page state.

### 12.3. pg_visibility Is Not a Routine VM Repair Tool

The extension offers diagnostic functions, yet this lesson focuses on **observation**. Never attempt to alter VM flags manually via low-level hacks or relation-file edits.

PostgreSQL must maintain the VM safely alongside WAL, tuple visibility, and `VACUUM`; uncoordinated flag modifications can make queries return wrong results.

## 13. Calculating the Table's all-visible Page Percentage

You can combine main fork size and extension page counts:

~~~sql
WITH
page_count AS (
    SELECT
        (
            pg_relation_size(
                'mvcc_lab.events'::regclass,
                'main'
            ) / current_setting('block_size')::INTEGER
        )::BIGINT AS heap_pages
),
vm AS (
    SELECT *
    FROM pg_visibility_map_summary(
        'mvcc_lab.events'::regclass
    )
)
SELECT
    p.heap_pages,
    vm.all_visible,
    vm.all_frozen,
    ROUND(
        100.0 * vm.all_visible
        / NULLIF(p.heap_pages, 0),
        2
    ) AS all_visible_percent,
    ROUND(
        100.0 * vm.all_frozen
        / NULLIF(p.heap_pages, 0),
        2
    ) AS all_frozen_percent
FROM page_count AS p
CROSS JOIN vm;
~~~

This gives a quick look at page coverage. On an empty table, `NULLIF` prevents division by zero and percentages return NULL.

### 13.1. These Percentages Are Not Row Percentages

A page with 5 tuples and a page with 100 tuples both count as **one page**. Having 80% `all-visible` pages does not necessarily mean 80% of SQL rows sit on `all-visible` pages.

### 13.2. Point-in-Time Observation

`pg_relation_size` and `pg_visibility_map_summary` can read state at slightly different instants under concurrent writes. Thus this is an **approximate point-in-time operational metric**, not an atomic physical snapshot verification of the whole relation.

## 14. pg_class.relallvisible: Information for the Planner

PostgreSQL also stores relation statistics metadata in `pg_class`:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.relpages,
    c.reltuples,
    c.relallvisible,
    ROUND(
        100.0 * c.relallvisible
        / NULLIF(c.relpages, 0),
        2
    ) AS relallvisible_pct
FROM pg_class AS c
WHERE c.oid = 'mvcc_lab.events'::regclass;
~~~

Meaning:

- `relpages`: estimated page count of the relation.
- `reltuples`: estimated tuple count.
- `relallvisible`: number of `all-visible` pages recorded in the catalog for the planner.

These values are updated by maintenance operations like `VACUUM`/`ANALYZE` and **do not necessarily reflect the exact current instant**.

### 14.1. How Does It Differ From pg_visibility?

| Source | Purpose | Directness |
|---|---|---|
| `pg_class.relallvisible` | Statistics for the planner to estimate index-only scan cost | Can lag behind the real VM |
| `pg_visibility_map_summary` | Inspects actual VM bits per page when called | More direct for current VM state |
| `EXPLAIN (ANALYZE) Heap Fetches` | Actual heap fetches of the node in one query run | Measures specific query behavior |
| `pg_stat_user_tables` | Activity stats / dead tuple estimates and `VACUUM` runs | Operational metrics, not a VM map |

Never rely solely on `relallvisible` to assert "all these pages are guaranteed `all-visible` right now."

## 15. VACUUM and ANALYZE Do Different Work

Both commands frequently appear together:

~~~sql
VACUUM (ANALYZE) mvcc_lab.events;
~~~

However:

- **`VACUUM`**: cleans dead tuples when safe, reuses space, maintains the VM, and handles freezing.
- **`ANALYZE`**: gathers statistics so the planner can estimate selectivity, cardinality, and choose plans.

`ANALYZE` alone does not mark pages `all-visible` or frozen. If you want to see what changed due to `VACUUM` vs. `ANALYZE`, separate the two effects.

### 15.1. VACUUM Usually Does Not Shrink the Table File Immediately

Regular `VACUUM` primarily enables **internal space reuse**, not returning the entire file size to the operating system. It can truncate eligible trailing empty pages in some cases, yet never treat shrinking files as the default goal of every `VACUUM`.

`VACUUM FULL` **rewrites** the table to reclaim disk space and requires strong locks, which is completely different. Never run `VACUUM FULL` just to increase `all-visible` pages for index-only scans.

## 16. Freezing: The XID Wraparound Problem

PostgreSQL uses cyclic transaction IDs; traditional XIDs live in a 32-bit space. As a system runs for a long time, XID values grow and eventually wrap around.

If old XID references stayed untouched forever without protection, PostgreSQL could no longer distinguish "old" from "new" once numbers wrapped around.

**Freezing** processes old transaction metadata in tuples so PostgreSQL knows the row version is old enough and safe to treat as created by a committed past transaction under MVCC semantics, without continuing to depend on finite-lived XID details.

### 16.1. Never Interpret Freezing as Locking Rows

The word "frozen" is easily mistaken for "rows cannot be `UPDATE`d/`DELETE`d." That is **false**.

A frozen tuple:

- Can still be `SELECT`ed normally.
- Can still be `UPDATE`d or `DELETE`d if permissions and constraints allow.
- On `UPDATE`, PostgreSQL creates a new tuple version per MVCC rules.
- The page holding that tuple loses its `all-visible`/`all-frozen` flags on modification.

Freezing protects **transaction visibility metadata**, not read-only immutability of business data.

## 17. Does Freezing Really Overwrite xmin = FrozenTransactionId?

In introductory explanations, learners often see the model "replace an old XID with `FrozenTransactionId`." That is a **conceptual** way of saying the tuple is treated as frozen.

In modern PostgreSQL versions, the physical mechanism uses **tuple header / infomask bits** to represent frozen status rather than always overwriting `xmin` with a magic constant.

Therefore:

- Do not assume `SELECT xmin` shows you the entire freezing mechanism.
- Do not build applications relying on `xmin` as a durable version ID.
- Do not cite an XID shown on an old tuple as proof freezing hasn't run without understanding internal representation.

System columns exist for MVCC/debugging, not long-term business contracts.

## 18. How Does all-visible Differ From all-frozen?

A page is marked **`all-visible`** when PostgreSQL determines all existing tuples are visible to all transactions per VM rules.

A page is marked **`all-frozen`** when all XID/MultiXact metadata needing freezing on the page has been processed, so future vacuum sweeps don't have to revisit that page for current freezing purposes.

Think of it as:

~~~text
Page with committed tuples old enough for all snapshots to see
    |
    +--> Can be all-visible
    |
    +--> Yet XID/MultiXact may not be frozen yet
             |
             v
        VACUUM freezing
             |
             v
        Can become all-frozen
~~~

**Implication relationship:**

\[
\text{all-frozen} \Rightarrow \text{all-visible}
\]

whereas:

\[
\text{all-visible} \not\Rightarrow \text{all-frozen}
\]

This is one of the most important rules to remember about the visibility map.

## 19. Why Does all-frozen Help VACUUM?

When PostgreSQL must guard against XID wraparound or freeze old transactions, it needs to know which pages still contain transaction metadata requiring inspection.

If the VM marks a page `all-frozen`, `VACUUM` can **skip that page during freezing passes**, under the algorithm's safety rules.

Pages that are `all-visible` yet not `all-frozen` still have to be scanned during an **aggressive vacuum** to freeze transaction metadata.

The savings on large, mostly read-only tables can be substantial:

~~~text
500 GB historical table
  |
  +--> Many all-frozen pages
  |       |
  |       +--> Aggressive vacuum can skip
  |            pages needing no re-freezing
  |
  +--> Pages not yet all-frozen
          |
          +--> Must be inspected/frozen if eligible
~~~

Do not assume `all-frozen` means PostgreSQL will **never** read that page again for anything else. Queries and other maintenance still read it, and new DML clears the flags.

## 20. Regular VACUUM vs. Aggressive VACUUM

In PostgreSQL, `VACUUM` runs under different modes/conditions.

### 20.1. Regular VACUUM

A regular `VACUUM` focuses on cleaning unneeded tuples, updating the VM, and freezing tuples meeting thresholds. It can **skip many `all-visible` pages** that don't need immediate attention to save I/O.

### 20.2. Aggressive VACUUM

Once a relation's XID age grows large enough, PostgreSQL switches to **aggressive** vacuuming: scanning pages that are not `all-frozen` to process old XIDs/MultiXacts and prevent wraparound.

Aggressive vacuum still **skips `all-frozen` pages**. It does not mean reading every byte of every page when the VM proves certain pages need no freezing work.

### 20.3. VACUUM (FREEZE) in the Lab

PostgreSQL supports:

~~~sql
VACUUM (FREEZE, ANALYZE, VERBOSE) mvcc_lab.events;
~~~

Depending on version, `FREEZE` acts like a vacuum with aggressive minimum-age freeze settings, causing PostgreSQL to freeze eligible tuples eagerly.

**Never run `VACUUM (FREEZE)` casually on large production tables.** It can generate heavy I/O, WAL, and long maintenance windows. Autovacuum already handles routine freezing based on XID age and table activity.

This command must run **outside an explicit transaction block**.

## 21. Freezing Thresholds

Important settings can be inspected with:

~~~sql
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
SHOW autovacuum_freeze_max_age;
~~~

General role:

| Parameter | Role |
|---|---|
| `vacuum_freeze_min_age` | Minimum XID age before regular `VACUUM` considers freezing eligible XIDs |
| `vacuum_freeze_table_age` | Threshold determining when `VACUUM` becomes aggressive to handle old XIDs |
| `autovacuum_freeze_max_age` | Critical threshold triggering anti-wraparound autovacuum when a relation gets too old |

Exact parameters and limits vary by version. Several also have per-table `reloptions` overrides. Never copy settings from another system without weighing XID age, transaction throughput, I/O, table sizes, and maintenance windows.

### 21.1. Never Tune One Parameter in Isolation

Lowering thresholds drastically forces earlier freezing and extra maintenance work.

Raising thresholds excessively defers work and risks forcing urgent **anti-wraparound vacuums** that cannot be delayed.

The goal is steady, safe scanning and freezing matched to workload—not "maxing thresholds so `VACUUM` runs as rarely as possible."

## 22. relfrozenxid and Table Transaction Age

PostgreSQL stores an XID boundary per relation in `pg_class.relfrozenxid`.

You can inspect it:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.oid = 'mvcc_lab.events'::regclass;
~~~

`age(c.relfrozenxid)` measures transaction age relative to the current transaction ID under PostgreSQL semantics.

A high age indicates the relation needs attention in your anti-wraparound strategy. It does **not directly** tell you dead tuple counts, index-only heap fetches, or the `all-visible` ratio.

### 22.1. XID Age Is Not Age in Days

A table created last month can have a high XID age if the server processed huge transaction volumes. A table created years ago can have a low XID age if properly vacuumed and frozen.

Never mechanically convert `age(relfrozenxid)` into "days since last VACUUM."

### 22.2. Checking Age at the Database Level

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS database_xid_age
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
~~~

`datfrozenxid` is the database-level boundary across its relations. DBAs monitor it alongside relation-level metrics to prevent wraparound.

System catalogs or non-standard relations can also constrain vacuum/freeze progress; never watch only one big user table.

## 23. MultiXact and Freezing

Beyond single transaction IDs, PostgreSQL uses **MultiXact IDs** when multiple transactions lock the same tuple concurrently.

The engine must manage the MultiXact lifecycle to avoid wraparound similarly.

Related inspection:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.relminmxid,
    mxid_age(c.relminmxid) AS multixact_age
FROM pg_class AS c
WHERE c.oid = 'mvcc_lab.events'::regclass;
~~~

Depending on PostgreSQL version, MultiXact autovacuum parameters have dedicated thresholds. In production monitoring, watching only `age(relfrozenxid)` while ignoring `mxid_age(relminmxid)` can miss MultiXact wraparound risk.

### 23.1. All-Frozen Covers Both Metadata Families

When a page is marked `all-frozen` per PostgreSQL rules, it implies the page no longer needs revisiting solely for pending XID or MultiXact freezing under current conditions.

Never try to manually edit `xmin`, `xmax`, or tuple headers via SQL hacks to "reduce age." PostgreSQL `VACUUM` handles this safely.

## 24. Why Is XID Wraparound Serious?

If a system fails to process old XIDs and lets XIDs approach the wraparound boundary, PostgreSQL prioritizes anti-wraparound maintenance. In severe cases, the database refuses new write transactions to prevent data corruption.

That is a protective safety stop—not PostgreSQL "deleting old data."

### 24.1. Never Disable Autovacuum to Save I/O and Forget Wraparound

Disabling autovacuum globally or per table causes:

- Dead tuple accumulation.
- Fewer `all-visible` pages for index-only scans.
- Stale planner statistics if `ANALYZE` stops.
- XID/MultiXact age climbing toward danger thresholds.
- Unexpected forced anti-wraparound vacuums.

Even when regular autovacuum is disabled, PostgreSQL keeps special safeguards for anti-wraparound, yet **never rely on that for normal operations**.

When I/O is tight, tune autovacuum thoughtfully and monitor XID age instead of turning maintenance off.

## 25. Long Transactions Affect VACUUM

Suppose:

~~~text
10:00 - Session A starts a transaction holding an old snapshot.
10:01 - Session B updates many rows.
10:02 - Session B commits.
10:03 - VACUUM runs.
10:30 - Session A still holds its transaction open.
~~~

While an old snapshot still needs old tuple versions, `VACUUM` cannot freely remove those versions. Affected pages may fail to reach `all-visible`/`all-frozen` status as they would without the holding transaction.

### 25.1. Consequences

- Dead tuples persist longer.
- Bloat grows.
- The VM does not achieve expected `all-visible` coverage.
- Index-only scans perform extra heap fetches.
- Advancing freezing horizons can be restricted.
- `VACUUM` has to redo work once the blocker clears.

Not every long transaction triggers every consequence on every table; impact depends on snapshots, modified tables, and transaction type. Still, it is a primary diagnostic lead.

## 26. Finding Long Transactions and Connection States

Monitoring query:

~~~sql
SELECT
    pid,
    usename,
    datname,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_excerpt
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 30;
~~~

`xact_start` is when the transaction began, not necessarily when a snapshot was captured. To trace exact horizons, also inspect transaction metadata and related views.

### 26.1. Privileges to View Other Sessions' Queries

Depending on roles, unprivileged users cannot see full session details of other users, and `query` fields may be hidden. Never grant overly broad privileges or log raw query text containing sensitive literals into dashboards.

### 26.2. Long Idle Transactions Matter Too

`state = 'idle in transaction'` is a key warning sign, especially when the transaction holds snapshots/locks or already modified data.

Applications should:

- End transactions promptly.
- Never keep transactions open across user requests.
- Configure appropriate timeouts like `idle_in_transaction_session_timeout` after evaluation.
- Avoid holding pool connections idle while waiting for users to view pages.

Never automatically kill every long transaction without evaluating its impact on legitimate work.

## 27. Replication Slots and hot_standby_feedback

Replication settings can also constrain cleanup of old tuples.

Examples:

- A replication slot retaining state for a slow consumer.
- A logical replication slot holding `xmin` or `catalog_xmin` under certain configurations.
- `hot_standby_feedback` telling the primary that a standby still needs old tuple versions.

As a result, `VACUUM` on the primary cannot immediately clean tuples that look dead from the application's view, indirectly affecting bloat and `all-visible` ratios on active pages.

### 27.1. Inspecting Slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin
FROM pg_replication_slots;
~~~

Distinguish:

- A slot retaining unconsumed WAL causes WAL disk usage to grow.
- A slot holding `xmin`/`catalog_xmin` restricts tuple cleanup.
- Not every slot holds both kinds of horizons.
- Slot actions must account for subscribers, CDC, backups, and data-loss risks.

Never drop a production replication slot just because it looks old without understanding its consumer.

## 28. Tracking VACUUM via pg_stat_user_tables

PostgreSQL provides table activity statistics:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    n_tup_ins,
    n_tup_upd,
    n_tup_del
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_lab'
  AND relname = 'events';
~~~

How to read it:

- `n_live_tup` and `n_dead_tup` are **statistical estimates**, not exact `COUNT`s.
- `last_autovacuum` can be NULL if no run has been recorded since stats tracking/reset.
- High `n_tup_upd` indicates write churn and frequent clearing of VM bits over time.
- `vacuum_count` and `autovacuum_count` show maintenance runs, though they do not prove individual pages are frozen.

### 28.1. Monitoring Active VACUUM Progress

While PostgreSQL is running `VACUUM`, check:

~~~sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum
ORDER BY pid;
~~~

Rows only appear while a `VACUUM` is actively running per version capabilities. `heap_blks_scanned` does not mean every block was read from disk due to page skipping and caching.

## 29. How Is Autovacuum Triggered?

Autovacuum evaluates multiple signals, including updated/deleted tuple counts, `INSERT` counts on supported versions, table-size scale factors, and XID/MultiXact ages.

Observable parameters:

~~~sql
SHOW autovacuum;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_vacuum_insert_threshold;
SHOW autovacuum_vacuum_insert_scale_factor;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
~~~

Not every server or major version has identical parameter lists or behavior; always inspect your target server.

### 29.1. Why Do Very Large Tables Need Attention to Scale Factors?

A percentage-based trigger on total row count can allow huge volumes of changes before autovacuum fires. On large, frequently updated tables, delayed `VACUUM` causes:

- Many dead tuples.
- Many pages losing `all-visible`.
- Index-only scans doing heavy heap fetches.
- Bloat and high I/O spikes.

Consider **per-table** autovacuum tuning after measuring the workload—such as lower thresholds tuned to available resources. Never alter a server-wide setting from a textbook example without observing effects on other tables.

### 29.2. INSERT-Only Tables Still Need VACUUM

An append-only table with almost zero `UPDATE`/`DELETE`s still needs maintenance to:

- Mark eligible pages `all-visible` for index-only scans.
- Freeze XIDs once data ages sufficiently.
- Manage long-term transaction age.

Never conclude "zero dead tuples means autovacuum has nothing to do."

## 30. Why Do Read-Mostly Tables Benefit From all-frozen?

A bulk-loaded historical table with rare changes has these traits:

- Tuples remain stable for long periods.
- `VACUUM` marks most pages `all-visible`.
- Freezing gradually promotes them to `all-frozen`.
- Index-only scans minimize heap accesses when matching indexes exist.
- Aggressive vacuums skip already-frozen pages.

Conversely, a table with constant row-by-row `UPDATE`s:

- Pages continually lose `all-visible`.
- Tuple versions and dead entries accumulate for cleanup.
- VM bits churn constantly.
- Index-only scans rarely hit 0 heap fetches on hot pages.
- Freezing repeats as new versions age.

That does not mean a "hot" table should never use index-only scans; check what fraction of queried pages are hot and measure on real workloads.

## 31. Does the Visibility Map Guarantee Avoiding Heap Reads on Every Index-Only Scan?

No.

Even when an index includes all needed columns, these conditions still apply:

1. Does the index access method support returning values for index-only scans?
2. Does the index contain all required key/`INCLUDE` columns?
3. Which heap pages do the scanned index entries point to?
4. Are those specific pages `all-visible` at check time?
5. Does the planner estimate `Index Only Scan` as cheaper than `Index Scan` or `Seq Scan`?
6. Are there filters/expressions requiring data not held in the index?

Example:

~~~sql
SELECT id, occurred_at, amount, note
FROM mvcc_lab.events
WHERE account_id = 7
ORDER BY occurred_at DESC, id DESC
LIMIT 100;
~~~

`idx_events_cover` **does not contain `note`**, so an index-only scan on that index alone cannot satisfy the `SELECT`. An `all-visible` VM never supplies missing columns.

### 31.1. INCLUDE Is Not a Cure-All

You could stuff every column into `INCLUDE` to make an index covering, yet wider indexes:

- Increase storage size.
- Increase `INSERT`/`UPDATE` cost.
- Can break HOT eligibility when included columns are updated.
- Risk exceeding index-tuple size limits depending on data.
- Still perform heap fetches whenever VM pages aren't `all-visible`.

Design covering indexes only for queries with clear measured gains.

## 32. Common Misconceptions About Freezing

### Misconception 1 — Freezing Compresses Data

No. Freezing processes transaction visibility metadata, not row compression.

### Misconception 2 — Frozen Means No UPDATEs Allowed

False. Frozen tuples remain normal table rows that can be updated/deleted per privileges and constraints; the new version gets fresh MVCC metadata.

### Misconception 3 — All-Visible Equals All-Frozen

False. `all-frozen` implies `all-visible`, not the reverse.

### Misconception 4 — An All-Visible Page Never Needs VACUUM Again

False. The page may still need freezing, and new writes clear the flags.

### Misconception 5 — VACUUM FREEZE Is Required to Optimize Index-Only Scans

Not necessarily. Index-only scans require **`all-visible`**, not directly **`all-frozen`**. Regular `VACUUM` is enough to mark `all-visible`.

### Misconception 6 — Freezing Drops relfrozenxid Age to 0 Immediately

Do not expect every `VACUUM` to reset age to 0. How far horizons advance depends on open snapshots, remaining XIDs/MultiXacts, and cutoff rules.

### Misconception 7 — Freezing Replaces Backups

No. Freezing does not create point-in-time recovery checkpoints or protect against accidental `DELETE`s, hardware failures, or dropped tables.

## 33. Visibility Map and the PostgreSQL Planner

The planner consults `pg_class.relallvisible` when estimating the benefit of an index-only scan. If stats show a high fraction of `all-visible` pages, expected heap-fetch cost is lower.

Yet the planner also weighs:

- Whether the index matches predicates.
- Sort requirements.
- `LIMIT` clauses.
- `WHERE` selectivity.
- Relation size.
- Cost settings like `random_page_cost` and `seq_page_cost`.
- Cache ratios and physical/logical correlation.
- Gaps between estimated and actual rows.

### 33.1. Queries May Still Choose Index Scan

A highly selective query needing a column outside the index uses `Index Scan` instead of `Index Only Scan`. A query returning most of the table may pick `Seq Scan` despite a covering index.

Never force the planner into a specific node just to see `Heap Fetches: 0`. The true objective is overall latency, throughput, and total resource cost.

### 33.2. Why Does Stale relallvisible Matter?

If `pg_class.relallvisible` lags far behind the actual VM, the planner may misestimate heap-fetch avoidance. Routine `VACUUM`/`ANALYZE` and up-to-date stats lead to better plan choices.

Never use extensions or catalog hacks to manually edit `relallvisible`.

## 34. VACUUM Cannot "Clean All Dead Tuples" When a Blocker Exists

Suppose a long transaction holds a snapshot needing old versions. `VACUUM` cannot delete old versions just because `n_dead_tup` is rising. Versions potentially visible to valid snapshots must stay.

Once the blocker disappears, the next `VACUUM` can reclaim more space.

Blocker sources to check:

- Long transactions or `idle in transaction` sessions holding snapshots.
- Unresolved prepared transactions.
- Replication slots or standby feedback pinning cleanup horizons in certain setups.
- Long-lived transaction IDs or row locks.

Never try to delete tuples via anything outside `VACUUM`. MVCC requires cleanup to respect safe visibility horizons.

## 35. Can the VM Change Even Without UPDATEs?

Yes.

Operations affecting the VM include:

- **`INSERT`:** the page receiving a new tuple loses `all-visible`.
- **`DELETE`:** alters tuple states on the page.
- **`UPDATE`:** creates a new version and alters the page.
- **`VACUUM`:** sets `all-visible`/`all-frozen` when eligible.
- PostgreSQL maintenance and crash-recovery actions managing fork/page states.

Thus `all_visible_percent` can drop on a high-rate `INSERT`-only table between `VACUUM` runs—`DELETE`s are not required for the VM to change.

## 36. Is the Visibility Map WAL-Logged?

PostgreSQL manages the VM so changes stay consistent and crash-safe with WAL and recovery. Marking a page `all-visible` is synchronized properly with heap state.

Why does this matter?

If the VM ever claimed `all-visible` while an ineligible tuple sat on the page and an index-only scan skipped checking the heap, `SELECT` would return wrong MVCC results. Hence the VM is **not an approximate counter**; setting its bits obeys strict safety rules.

Operators should only use PostgreSQL-supported SQL/`VACUUM` commands—never edit `_vm` files directly.

## 37. Observability: Matching the Right Metric to Each Question

| Question to Answer | Useful Observation |
|---|---|
| Is a query using `Index Only Scan`? | `EXPLAIN (ANALYZE, BUFFERS)` |
| Is the query hitting the heap often? | `Heap Fetches` on the `Index Only Scan` node |
| How many heap pages are `all-visible`/`all-frozen`? | `pg_visibility_map_summary` |
| Which flags does a specific page have? | `pg_visibility_map` |
| How does the planner estimate `all-visible`? | `pg_class.relallvisible`, `relpages` |
| Does the table have many estimated dead tuples? | `pg_stat_user_tables.n_dead_tup` |
| Has `VACUUM`/autovacuum run recently? | `last_vacuum`, `last_autovacuum` |
| What is `VACUUM` doing right now? | `pg_stat_progress_vacuum` |
| Is table/database XID age high? | `age(relfrozenxid)`, `age(datfrozenxid)` |
| Does MultiXact age need watching? | `mxid_age(relminmxid)` |
| Is a long transaction holding back cleanup? | `pg_stat_activity` and horizon monitoring |
| Is a replication slot holding `xmin`? | `pg_replication_slots` |

One metric alone cannot prove a root cause. For example:

- High `Heap Fetches` does not prove autovacuum failed.
- Low `n_dead_tup` does not guarantee all pages are `all-visible`.
- High `relallvisible` does not prove queries chose `Index Only Scan`.
- High XID age does not mean the table has many dead tuples.
- Low `all_frozen` does not automatically mean imminent wraparound risk.

## 38. Case Study: Mostly Read-Only Report With Rising Heap Fetches

Suppose a system has a 200-million-row `event_history` table, mostly `INSERT`-only:

~~~sql
CREATE INDEX idx_event_history_cover
ON event_history (
    tenant_id,
    created_at DESC,
    event_id DESC
)
INCLUDE (event_type);
~~~

Reporting query:

~~~sql
SELECT event_id, created_at, event_type
FROM event_history
WHERE tenant_id = 42
ORDER BY created_at DESC, event_id DESC
LIMIT 100;
~~~

Initially `Index Only Scan` had very few heap fetches. After sustained high-speed ingestion, queries reading **the newest data** experience more heap fetches because newly `INSERT`ed pages have not yet been marked `all-visible` by `VACUUM`.

### 38.1. Do Not React With a Full-Table VACUUM FREEZE Right Away

A better investigation path:

1. Confirm the query still uses the covering index.
2. Track `Heap Fetches` and `Buffers` over time.
3. Inspect overall VM ratios and, if needed, the relevant heap page ranges.
4. Check whether autovacuum ran and whether long transactions blocked it.
5. Check insert-triggered autovacuum thresholds for your server version.
6. Compare latency on recent data ranges vs. older historical ranges.
7. Tune maintenance parameters only with clear evidence.

A table with 95% `all-visible` pages can still show heavy heap fetches if queries target the 5% of recent pages that are not yet `all-visible`.

## 39. Case Study: Old Table Needing Anti-Wraparound Vacuum

Suppose an old log table rarely changes yet has high `age(relfrozenxid)`. The DBA must ensure `VACUUM` freezes it before reaching safety limits.

Steps:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    age(c.relfrozenxid) AS xid_age,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_class AS c
WHERE c.oid = 'mvcc_lab.events'::regclass;
~~~

Then check configuration:

~~~sql
SHOW autovacuum_freeze_max_age;
SHOW vacuum_freeze_table_age;
SHOW vacuum_freeze_min_age;
~~~

and stats:

~~~sql
SELECT
    last_autovacuum,
    autovacuum_count,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_lab'
  AND relname = 'events';
~~~

If intervention is truly required, run `VACUUM` per operational plan while monitoring progress, blockers, I/O, locks, and replication impact.

A table **with negligible dead tuples** can still require freezing due to XID age. That is why an anti-wraparound vacuum does not mean PostgreSQL is "cleaning too much dead data."

## 40. Lab Verification Walkthrough

To tie all mechanisms together, run in order:

1. Create `mvcc_lab.events` and the covering index.
2. `INSERT` synthetic data.
3. Inspect `pg_visibility_map_summary` if the extension is available.
4. Run `EXPLAIN (ANALYZE, BUFFERS)` with a query reading only indexed columns.
5. Run `VACUUM (ANALYZE)` outside a transaction.
6. Re-inspect `all_visible` and `Heap Fetches`.
7. `UPDATE` a group of rows, then re-measure.
8. Run `VACUUM` again and observe changes.
9. Test `VACUUM (FREEZE, VERBOSE, ANALYZE)` **in the lab only** to observe `all_frozen`.
10. Query `age(relfrozenxid)` and `mxid_age(relminmxid)` to connect with freezing.

This is a **learning walkthrough**, not a QA checklist or production runbook. Step-by-step numbers vary with VM state, caches, concurrent transactions, and server version.

### 40.1. Why Shouldn't You Turn Off Autovacuum for the Lab?

Autovacuum can run between steps and update the VM—that is part of PostgreSQL's real behavior.

Rather than disabling autovacuum server-wide, appreciate that background maintenance is active. If strict repeatability is needed, isolate a dedicated lab database with controlled timelines and note the experiment's limits.

## 41. Common Mistakes

### Mistake 1 — All-Visible Means Zero Active Transactions

No. It means that page qualifies as `all-visible`, not that the entire database is idle.

### Mistake 2 — All-Visible and All-Frozen Are the Same

No. `all-frozen` is a stronger state carrying freezing guarantees.

### Mistake 3 — COMMIT Automatically Turns the VM All-Visible

No. `VACUUM` normally checks and marks qualifying pages.

### Mistake 4 — Index Only Scan Never Reads the Heap

No. Whenever target pages are not `all-visible`, `Heap Fetches` occur.

### Mistake 5 — Heap Fetches Equals Dead Tuple Count

No. It counts heap accesses for scan visibility verification, not dead rows.

### Mistake 6 — High Heap Fetches Means Run VACUUM FULL

No. `VACUUM FULL` rewrites the table with strong locks; it is not the default fix for VM flags.

### Mistake 7 — ANALYZE Automatically Sets All-Visible

`ANALYZE` collects planner stats; `VACUUM` maintains the VM and freezing.

### Mistake 8 — Frozen Tuples Cannot Be Modified

False. Freezing never locks business data against updates.

### Mistake 9 — Freezing Is Only Needed When DELETEs Are Heavy

False. Insert-only tables held long-term still need anti-wraparound protection.

### Mistake 10 — relallvisible Is the Live VM Value Updated Instantly

False. It is catalog metadata for the planner and can lag behind the actual VM.

### Mistake 11 — n_dead_tup Is an Exact COUNT

No. It is a statistical estimate.

### Mistake 12 — 90% All-Visible Means Queries Only Heap-Fetch 10% of Rows

No. The VM is page-level; queries often focus on the 10% of hot pages.

### Mistake 13 — All-Frozen Means VACUUM Will Never Touch the Page Again

No. New writes clear it, and other operations still access it.

### Mistake 14 — Disable Autovacuum to Avoid Performance Impact

This causes bloat, missing VM maintenance, and XID wraparound risk.

### Mistake 15 — XID Age Equals Calendar Days

No. Age is measured in transactions, not wall-clock days.

### Mistake 16 — Watch Only relfrozenxid and Ignore MultiXact

This misses wraparound pressure involving `relminmxid`.

### Mistake 17 — VACUUM Always Cleans Every Dead Tuple

Transaction or replication horizons can keep old versions pinned.

### Mistake 18 — Adding Every Column to INCLUDE Is Always Faster

Wide indexes hurt write/storage cost, and VM state still governs heap fetches.

### Mistake 19 — Full-Table VACUUM FREEZE Is the Best Default Tuning

It can consume heavy I/O and WAL; base choices on XID age and maintenance plans.

### Mistake 20 — Editing _vm Files to "Improve" Index-Only Scans

Extremely dangerous. The VM is internal metadata that PostgreSQL must update safely.

## 42. Practice Exercises

### Exercise 1 — Two VM Bits

A page has `all_visible=true` and `all_frozen=false`. Can this be valid? Explain.

**Hint:** Yes; the page may be visible to all snapshots yet still hold unfrozen XIDs/MultiXacts.

### Exercise 2 — Implication

Does `all_frozen=true` imply `all_visible=true`?

**Hint:** Yes.

### Exercise 3 — COMMIT and VM

An `INSERT` just committed; is its page guaranteed to be `all-visible`?

**Hint:** No.

### Exercise 4 — Updating One Row

Only one row on an `all-visible` page is `UPDATE`d. Why might index-only scans for *other* rows on the same page also visit the heap?

**Hint:** The VM tracks flags per page, not per row.

### Exercise 5 — Index Only Scan

A query uses `Index Only Scan` yet `EXPLAIN` reports `Heap Fetches: 500`. Is that a contradiction?

**Hint:** No; the heap must be checked whenever pages are not `all-visible`.

### Exercise 6 — Missing Column

An index covers `(account_id, occurred_at, id) INCLUDE(amount)`. The query also selects `note`. Does the VM help that index supply `note`?

**Hint:** No.

### Exercise 7 — ANALYZE vs. VACUUM

Distinguish the primary functions of `ANALYZE` and `VACUUM`.

**Hint:** Planner statistics vs. tuple cleanup / VM / freezing.

### Exercise 8 — Inspecting the VM

Write SQL counting `all-visible` and `all-frozen` pages of `mvcc_lab.events` using the extension.

**Hint:** `pg_visibility_map_summary('mvcc_lab.events'::regclass)`.

### Exercise 9 — Finding Non-All-Visible Pages

Write a query fetching the first 20 `blkno` values with `all_visible=false`.

**Hint:** `pg_visibility_map` with `WHERE NOT all_visible`.

### Exercise 10 — Catalog Stats

From `pg_class`, read `relpages`, `reltuples`, and `relallvisible`.

**Hint:** Filter by `oid = 'mvcc_lab.events'::regclass`.

### Exercise 11 — Calculating Ratio

A table has 1,000 heap pages, 700 of which are `all-visible`. What is the `all-visible` page percentage? Does it equal the percentage of committed rows?

**Hint:** 70%; not a row percentage.

### Exercise 12 — Frozen Does Not Mean Read-Only

Can a frozen tuple be `UPDATE`d?

**Hint:** Yes, if permissions and constraints allow.

### Exercise 13 — XID Age

Write a query checking `age(relfrozenxid)` for a table.

**Hint:** `pg_class` and `age(c.relfrozenxid)`.

### Exercise 14 — Database Horizon

Write a query sorting databases by `age(datfrozenxid)` descending.

**Hint:** `pg_database`.

### Exercise 15 — MultiXact

Which function inspects MultiXact age from `relminmxid`?

**Hint:** `mxid_age(relminmxid)`.

### Exercise 16 — Aggressive Vacuum

Can aggressive vacuum skip `all-frozen` pages?

**Hint:** Yes, under safety rules.

### Exercise 17 — VACUUM FREEZE

Is `VACUUM (FREEZE)` the default solution for every large table?

**Hint:** No; weigh I/O, WAL, and XID age.

### Exercise 18 — Long Transactions

A transaction holds an old snapshot for hours. How can it affect `VACUUM`?

**Hint:** Retains old versions, blocks cleanup, and delays VM/freezing progress.

### Exercise 19 — Replication Slots

A logical slot holds `catalog_xmin`. Why investigate before dropping the slot?

**Hint:** A consumer may depend on it; affects cleanup and replication continuity.

### Exercise 20 — INSERT-Only

An append-only table has no updates or deletes. Does it still need `VACUUM`/freezing?

**Hint:** Yes, for `all-visible` marking and XID wraparound protection.

### Exercise 21 — Heap Fetches After UPDATE

Why can a covering-index query experience more heap fetches after a batch of `UPDATE`s even without changing SQL or indexes?

**Hint:** Pages lost their `all-visible` flags.

### Exercise 22 — HOT

Does updating an unindexed `note` guarantee HOT every time? Does HOT mean the page stays `all-visible`?

**Hint:** No to both; page free space and visibility rules still apply.

### Exercise 23 — VACUUM FULL

Why shouldn't you run `VACUUM FULL` just to boost `all-visible` page counts?

**Hint:** Table rewrite and strong locks; not a routine optimization.

### Exercise 24 — Planner

Why might a `SELECT` skip `Index Only Scan` despite high `relallvisible`?

**Hint:** Missing columns, selectivity, costs, sorting, and overall plan cost.

### Exercise 25 — Historical Table

A mostly read-only table has a high `all-frozen` ratio. How does that help future aggressive vacuums?

**Hint:** Skips many pages that need no freezing.

### Exercise 26 — Hot Table

A continuously `UPDATE`d table has a low `all_visible_percent`. Is that automatically a configuration bug?

**Hint:** No; write churn is a natural cause.

### Exercise 27 — Scope of the VM

Does the VM enforce RLS permissions or MVCC visibility status?

**Hint:** MVCC visibility; RLS is enforced separately.

### Exercise 28 — Choosing the Right Metric

To know how often a query actually visited the heap during an `Index Only Scan`, check `pg_class.relallvisible` or `EXPLAIN` `Heap Fetches`?

**Hint:** `EXPLAIN ANALYZE` `Heap Fetches`.

### Exercise 29 — pg_stat_user_tables

Is `n_dead_tup` an exact dead-tuple count updated instantaneously?

**Hint:** Normally it is an estimate.

### Exercise 30 — Blockers and Actions

`VACUUM` cannot clean many dead tuples due to a long transaction. What should you inspect before tuning autovacuum settings?

**Hint:** `pg_stat_activity`, snapshots/locks, replication horizons, server version, and privileges.

## 43. Summary

- **MVCC** retains tuple versions so concurrent transactions with different snapshots read consistent data.
- The **visibility map** stores two bits per **heap page**: `all-visible` and `all-frozen`; it is neither a table nor a key-lookup index.
- **`all-frozen` implies `all-visible`**, whereas an `all-visible` page may not yet be fully frozen.
- **`VACUUM`** cleans dead tuples, maintains the VM, and freezes metadata when eligible; **`ANALYZE`** mainly updates planner statistics.
- **`INSERT`/`UPDATE`/`DELETE`** clear VM bits on modified pages; `COMMIT` alone does not automatically re-mark pages `all-visible`.
- **`Index Only Scan`** still visits the heap whenever target pages are not `all-visible`. The **`Heap Fetches`** metric in `EXPLAIN (ANALYZE, BUFFERS)` reflects that actual work.
- **Covering all queried columns in an index** and **`all-visible` VM pages** complement each other; the VM never supplies columns missing from the index.
- **Freezing** guards against XID/MultiXact wraparound and cuts scanning work for future aggressive vacuums; it **never makes rows read-only**.
- **`pg_visibility`** inspects per-page VM bits; **`pg_class.relallvisible`** is planner catalog metadata that may lag.
- **`age(relfrozenxid)`**, **`age(datfrozenxid)`**, **`mxid_age(relminmxid)`**, and autovacuum stats indicate long-term freezing health.
- Long transactions, replication horizons, and write churn affect cleanup and VM coverage.
- Never react blindly to high `Heap Fetches` with `VACUUM FULL`, `VACUUM FREEZE`, or disabling autovacuum; verify against actual workloads and operational constraints.

Key relationship to remember:

~~~text
MVCC creates multiple tuple versions
           |
           v
VACUUM checks/cleans/freezes when safe
           |
           v
Visibility map records page-level status
           |
           +--> all-visible
           |       |
           |       v
           |   Index Only Scan can
           |   skip heap visibility fetches
           |
           +--> all-frozen
                   |
                   v
               Aggressive VACUUM can
               skip already-frozen pages
~~~

Understanding **MVCC – visibility map – freezing** together explains why the exact same PostgreSQL query can speed up or slow down over time, and empowers you to manage autovacuum and indexes using evidence rather than guesswork.
