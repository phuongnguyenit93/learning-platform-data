# Transaction ID Wraparound and Transaction Age in PostgreSQL

A PostgreSQL table can hold rows that have existed for years, while every day the system executes millions of new transactions. **How does PostgreSQL know that a very old row version was committed long ago and must remain visible to future transactions?** This question leads to two foundational MVCC concepts: **Transaction ID (XID)** and **transaction ID wraparound**.

In PostgreSQL, row versions (*tuple versions*) carry transaction metadata, and the traditional XID used for MVCC is **32 bits** wide. A 32-bit counter eventually wraps around to earlier values after roughly **4.29 billion** IDs. If IDs were compared like ever-increasing integers, a transaction committed in the distant past could be mistaken for a transaction **in the future**, breaking visibility of old data.

To prevent that catastrophe, PostgreSQL uses **`VACUUM`**, and specifically **freezing (tuple freezing)**, to mark sufficiently old row versions as confirmed and permanently visible to future snapshots under MVCC rules. The system also tracks `relfrozenxid` and `datfrozenxid` boundaries and runs **anti-wraparound autovacuum** before XID age becomes dangerous.

This lesson dives into:

- 32-bit XIDs, 64-bit `xid8`, wraparound, and modulo "old/new" comparison rules.
- Tuple `xmin`/`xmax`, when XIDs are assigned, and the meaning of `age(xid)`.
- How freezing differs from dead-tuple cleanup; the roles of the visibility map, `relfrozenxid`, and `datfrozenxid`.
- Thresholds: `vacuum_freeze_min_age`, `vacuum_freeze_table_age`, `autovacuum_freeze_max_age`, and `vacuum_failsafe_age`.
- Monitoring XID age across databases, tables, TOAST, open transactions, replication slots, and prepared transactions.
- Runbooks when wraparound warnings appear or the server refuses to assign new XIDs.
- Distinguishing XID wraparound from **Multixact ID (MXID) wraparound**.
- Prevention and practice exercises **without attempting to trigger real wraparound**.

> **Safety scope:** read-only catalog/stats SQL can be used for monitoring when the role has appropriate privileges. Illustrative `CREATE`, `UPDATE`, and `VACUUM` commands must be practiced in a dedicated lab database or authorized environment. Never generate billions of transactions to simulate wraparound, never disable autovacuum, and never try to force production into XID exhaustion.

## 1. Why Does MVCC Need Transaction IDs?

**MVCC (Multi-Version Concurrency Control)** allows multiple transactions to read and modify data concurrently, where an `UPDATE` normally creates a new row version rather than overwriting all bytes of the old row immediately.

Product table example:

~~~text
Tuple version V1:
    sku = 'BOOK-01'
    price = 100
    xmin = XID 500
    xmax = XID 540  (superseded when transaction 540 updated)

Tuple version V2:
    sku = 'BOOK-01'
    price = 120
    xmin = XID 540
    xmax = 0 or no transaction deleting/updating this version yet
~~~

An older snapshot can see V1 while not yet seeing V2. A newer snapshot after transaction 540 commits sees V2, while V1 eventually becomes a dead tuple and can be reclaimed by `VACUUM` once no snapshot needs it.

In a simplified model:

- **`xmin`:** XID of the transaction that created the tuple version, typically via `INSERT` or `UPDATE`.
- **`xmax`:** transaction metadata related to deleting, replacing, or locking the tuple. **Never conclude that every `xmax != 0` means the row was deleted**: `xmax` can represent row locks or Multixacts and still requires checking transaction status and internal flags.
- **Snapshot:** determines which transactions are committed and which tuple versions are currently visible.
- **`pg_xact`:** where PostgreSQL tracks commit/abort status of needed transactions; older documentation often refers to this as CLOG.

~~~mermaid
flowchart LR
    A["INSERT version V1 (xmin=500)"] --> B["Transaction 540 UPDATE"]
    B --> C["V1 has xmax linked to 540"]
    B --> D["V2 has xmin=540"]
    C --> E["Old snapshot may need V1"]
    D --> F["New snapshot sees V2 if 540 committed"]
    E --> G["VACUUM cleans V1 when safe"]
    F --> H["Long-lived V2 needs freezing"]
~~~

Illustrative XIDs 500/540 are purely synthetic numbers; they are **not actual XIDs** PostgreSQL will necessarily assign in your lab.

### 1.1. Transaction ID Does Not Equal Wall-Clock Time

XIDs are allocated from a shared counter across the **PostgreSQL cluster/instance**, not:

- Seconds since PostgreSQL started;
- A per-database ID;
- A table's primary key;
- An exact commit timestamp;
- A number incremented on every `SELECT`.

A transaction staying open for 20 minutes doing only reads may never need a regular XID. Meanwhile, millions of tiny write transactions can advance the XID counter very rapidly.

### 1.2. When Is an XID Assigned?

In PostgreSQL, every transaction gets a **virtual transaction ID (vxid)** for activity management, without necessarily receiving a **non-virtual 32-bit XID** right away. A regular XID is assigned when the transaction first needs to write or mark changes in the database.

~~~text
Session A:
    BEGIN
    SELECT ...
    SELECT ...
    COMMIT

May never allocate a non-virtual XID for a read-only transaction.

Session B:
    BEGIN
    INSERT ...
       ↓
    receives XID when write occurs
    COMMIT
~~~

Therefore, `BEGIN` order does not necessarily match **XID assignment order**. Two transactions opened concurrently receive XIDs in the order they start writing.

## 2. 32-Bit XIDs and the Wraparound Problem

A 32-bit integer has **2³² = 4,294,967,296** bit combinations. PostgreSQL reserves a few special values (such as `InvalidTransactionId=0`, `BootstrapTransactionId=1`, `FrozenTransactionId=2`), while regular XIDs march through the finite space and eventually wrap around.

~~~text
... 4294967293, 4294967294, 4294967295
                           |
                           v
                wraps back to low XIDs
                past the special IDs
~~~

**This is designed behavior, not a random bug.** PostgreSQL must preserve the ability to distinguish "past" and "future" transactions even after low XID numbers repeat.

### 2.1. The ~2³¹ Window Rule

To compare 32-bit XID ordering with modulo arithmetic, PostgreSQL uses a window of roughly **2³¹ = 2,147,483,648** transactions. Picture XIDs arranged on a **clock face**:

~~~text
32-bit XID circle (~4.29 billion positions)

                 Future XIDs
                      |
                      v
   ---- [ahead region] -------- [CURRENT] ----
              ^                     |
              |                     v
         half-circle           past half-circle

From any current point, roughly ~2.147 billion XIDs lie
in the past and ~2.147 billion XIDs lie in the future.
~~~

If an unfrozen tuple carries an XID so old that it falls **too far behind**, modulo comparison treats it as a **future XID**. Tuples that ought to be visible would then be misclassified.

**Never think "danger only starts after a full 4.29 billion transactions."** The real safety boundary is roughly **2.147 billion XIDs of age** from the oldest unfrozen XID, not waiting for a full 32-bit cycle.

### 2.2. A 12-Hour Clock Analogy

An analogy:

~~~text
On a 12-hour clock:
  Current hour = 1
  Number 12 can mean 1 hour ago
  or 11 hours ahead.
~~~

When a number space wraps around, checking "12 < 1" is insufficient to know which came first. You need a **bounded half-circle distance rule**. PostgreSQL applies the exact same principle to XIDs over 32-bit space.

### 2.3. Wraparound Does Not Force Data Loss in PostgreSQL

A healthy PostgreSQL cluster can run **across many full 32-bit XID wraparounds**. Freezing frees sufficiently old row versions from depending on circular XID comparisons.

Danger arises only if the **XID age of unfrozen data exceeds the safe horizon** because `VACUUM` was blocked or failed to complete. PostgreSQL enforces multiple safety layers, including refusing to assign new XIDs when danger gets too close.

## 3. xid, xid8, and Epoch: Why Is Freezing Still Needed With 64 Bits?

Modern PostgreSQL documentation distinguishes:

| Concept | Width / Role |
|---|---|
| `xid` | 32 bits, used in traditional tuple header fields and MVCC mechanics |
| `xid8` | 64 bits, includes **epoch** plus XID, useful for observing/tracking transaction IDs across wraparounds |
| **Epoch** | Increments each time the 32-bit XID counter wraps around |
| **vxid** | Backend-local virtual transaction identifier, distinct from cluster-wide XIDs |

~~~sql
SELECT
    pg_typeof(pg_current_xact_id_if_assigned())
        AS xid_function_type,
    pg_current_xact_id_if_assigned()
        AS my_xid_if_already_assigned;
~~~

`pg_current_xact_id_if_assigned()` returns `xid8` when the current transaction already has an XID, or `NULL` otherwise. It does not allocate a new XID just to inspect it.

By contrast:

~~~sql
SELECT pg_current_xact_id();
~~~

**forces allocation of a new XID** if the transaction does not have one yet. When building monitoring dashboards, **never poll an XID-allocating function just to "watch the XID clock"**; prefer non-allocating functions and metrics.

### 3.1. xid8 Does Not Replace Tuple Freezing

`xid8` lets applications and DBAs represent extended IDs without colliding across wraparounds. However, tuple headers and core MVCC visibility rules still rely on 32-bit XIDs. **Never assume PostgreSQL eliminated wraparound risk just because `xid8` functions exist.**

### 3.2. Limits on Casting, Comparing, and Storing XIDs

Never cast `xmin::text` to compare two strings and decide which tuple is "newer" at arbitrary times. Never cast an XID to `integer`, subtract directly, and call it transaction age. Always use modulo-aware functions—chiefly **`age(xid)`**—and consult version-matched documentation.

For business auditing, `created_at`/`updated_at` and an explicit business version are far better than exposing `xmin` as a timestamp or long-term public version.

## 4. age(xid): Measures **Transactions**, Not Elapsed Time

PostgreSQL provides:

~~~sql
age(xid)  -- returns integer
~~~

This function returns the distance in **number of Transaction IDs** between the given XID and the current counter, accounting for modulo wraparound semantics.

~~~sql
SELECT
    age(datfrozenxid) AS oldest_unfrozen_xid_age
FROM pg_catalog.pg_database
WHERE datname = current_database();
~~~

If the result is `80,000,000`, the tracked XID boundary sits roughly **80 million XID allocations** behind current—it **does not mean the database ran for 80 million seconds**.

### 4.1. Same Number of Days, Vastly Different Ages

Suppose:

| Cluster | Write Transactions/Day (Approx.) | XID Growth After 10 Days |
|---|---|---|
| A — small lab | 2,000 | 20,000 |
| B — medium app | 500,000 | 5,000,000 |
| C — large platform | 20,000,000 | 200,000,000 |

The same 10 calendar days produce a **10,000x** difference in XID consumption between A and C. Wraparound risk depends on **how many XIDs elapsed since the unfrozen horizon**, not uptime alone.

### 4.2. Estimating Time Remaining

For planning only, if average XID consumption is `r` XIDs/day:

\[
\text{Estimated days} \approx
\frac{\text{Target XID threshold} - \text{Current XID age}}
{\text{XID growth per day}}
\]

For example, if an internal maintenance threshold is 200 million XIDs, current age is 160 million, and workload burns ~10 million XIDs/day:

~~~text
(200,000,000 - 160,000,000) / 10,000,000
= 4 days (estimated)
~~~

**This is not a guarantee that the system has exactly four days left.** Transaction rates can spike hourly, vacuum may be blocked on specific tables, and the anti-wraparound threshold is an **automatic maintenance trigger**, **not a data-loss cliff**. Monitor continuously, diagnose causes, and plan ahead.

### 4.3. Why Not Compare Age Against Server Uptime?

A server running for a year with sparse writes can have tiny XID age; a server running for weeks ingesting millions of mutations daily can race toward vacuum thresholds. Thus:

- `uptime` cannot substitute for `age(datfrozenxid)`.
- `pg_stat_database.xact_commit` is a helpful stats counter, yet not identical to total XID allocations.
- A single SQL call or transaction can consume multiple subtransactions; XID burn rate can differ from request rate.
- Never use modified row counts as a direct proxy for XID age.

## 5. Freezing: Protecting Very Old Row Versions

A tuple version committed long ago—whose creating transaction's commit status is no longer needed to decide visibility for future snapshots—can be **frozen**.

Idea:

~~~text
Before freezing:
    Tuple T has xmin = 500; XID/commit status must be evaluated.

After freezing:
    Tuple T carries "frozen" status in internal metadata.
    MVCC knows T is old enough and permanently valid
    for eligible future snapshots.

The XID counter keeps advancing and wrapping without ever
mistaking T for "created by a future transaction."
~~~

### 5.1. Freezing Is Not DELETE

**`VACUUM` performs two distinct tasks that are often confused:**

1. **Pruning / garbage collection:** removes dead row versions no snapshot needs anymore, freeing space for reuse.
2. **Freezing:** marks **still-live yet old row versions** as safe against XID wraparound.

An **insert-only table with zero `UPDATE`s or `DELETE`s** may have almost no dead tuples, yet **still requires freezing**. That is why "a static table has zero dead tuples" is **never** a valid reason to permanently disable autovacuum.

### 5.2. FrozenTransactionId and the Frozen Flag

In very old PostgreSQL releases (pre-9.4), freezing was often described as overwriting `xmin` with `FrozenTransactionId=2`. Modern PostgreSQL primarily uses **tuple header status flags** and can **preserve the displayed `xmin` value**.

Therefore:

~~~sql
SELECT xmin, *
FROM some_table;
~~~

is not a reliable way to check whether a tuple is frozen just by testing whether `xmin` equals 2. Rely on catalog horizons and `VACUUM` observations rather than guessing from `xmin`.

### 5.3. Frozen Does Not Make "Every Tuple Visible to Every Past Snapshot"

Accurately, PostgreSQL only freezes tuples when it is guaranteed safe relative to all active snapshots and transaction horizons. Do not imagine freezing as something that suddenly exposes future transaction writes inside **an already-active old snapshot**.

### 5.4. Freezing Does Not Alter Business Data

Running `VACUUM` to freeze never raises `product.price`, never inserts orders, and never "commits on behalf of" an unfinished transaction. Freezing updates internal storage metadata so already-confirmed versions remain safely recognizable long-term.

## 6. Visibility Map: all-visible and all-frozen

PostgreSQL maintains a **visibility map** tracking per-**heap-page** status. Two key flags:

- **All-visible:** tuples on the page qualify as visible to all active transactions, enabling optimizations such as index-only scans.
- **All-frozen:** tuples on the page have reached safe frozen status; future aggressive `VACUUM`s can **skip** `all-frozen` pages.

~~~text
Heap page P
    |
    +-- not all-visible: MVCC conditions still require checks
    |
    +-- all-visible: safely visible to current snapshots
    |
    +-- all-frozen: XID versions on page are safe against
                    wraparound; future vacuums can skip page
~~~

Never equate **`all-visible` = `all-frozen`**: a page can be visible to all current transactions yet still hold XIDs too young to freeze. Freezing is a separate requirement for long-term survival.

### 6.1. Impact on Aggressive VACUUM

A regular `VACUUM` skips many pages using the visibility map. When advancing an old XID horizon, an **aggressive `VACUUM`** must inspect every page that might contain unfrozen XIDs, while still skipping **`all-frozen`** pages.

This explains why two tables of identical disk size can have vastly different anti-wraparound vacuum costs: `all-frozen` page percentage, churn rate, and index/TOAST state all matter.

### 6.2. The pg_visibility Extension Is an Advanced Inspection Tool

The `pg_visibility` extension inspects the visibility map in DBA/lab environments when installed and permitted. You do not need this extension to understand the lesson or run routine monitoring; **`pg_class`, `pg_database`, and `VACUUM` stats** are safer, more universal starting points.

## 7. relfrozenxid: Per-Relation XID Age

In `pg_class`, **`relfrozenxid`** represents the earliest XID that could still exist **unfrozen** in that relation after eligible `VACUUM` runs.

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    age(c.relfrozenxid) AS xid_age
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
ORDER BY xid_age DESC
LIMIT 20;
~~~

This lists regular tables (`relkind='r'`) and materialized views (`relkind='m'`) with the highest XID age **in the currently connected database**.

**Note:** this is a **safety boundary / lower bound**, not a scan reporting "the exact oldest tuple across all rows." `age(relfrozenxid)` can be high even when user-visible rows were recently updated.

### 7.1. Why Might relfrozenxid Not Advance After a Regular VACUUM?

A `VACUUM` does not necessarily scan every page that might contain unfrozen XIDs. `relfrozenxid` only advances when `VACUUM` completes enough work to prove no unfrozen XID older than the new boundary remains.

~~~text
Regular VACUUM:
    can clean dead tuples and update the visibility map
    without scanning enough pages to advance relfrozenxid.

Aggressive / freeze-capable VACUUM:
    scans pages that may still hold unfrozen XIDs
    and can advance relfrozenxid significantly.
~~~

**Never conclude `VACUUM` is broken just because `age(relfrozenxid)` did not drop right after a regular `VACUUM`.** Read `VERBOSE` logs, check vacuum mode, horizon blockers, and table state.

### 7.2. TOAST Is a Separate Relation

A table with wide columns like `text`/`jsonb` often has a **TOAST table** storing out-of-line values. TOAST tables have their own `relfrozenxid` and can be what holds back an old age boundary.

Query tracking both main tables and their TOAST tables:

~~~sql
SELECT
    c.oid::regclass AS table_name,
    age(c.relfrozenxid) AS heap_xid_age,
    t.oid::regclass AS toast_table,
    age(t.relfrozenxid) AS toast_xid_age,
    GREATEST(
        age(c.relfrozenxid),
        age(t.relfrozenxid)
    ) AS oldest_relevant_age
FROM pg_catalog.pg_class AS c
LEFT JOIN pg_catalog.pg_class AS t
    ON t.oid = c.reltoastrelid
WHERE c.relkind IN ('r', 'm')
ORDER BY oldest_relevant_age DESC
LIMIT 30;
~~~

In PostgreSQL, `GREATEST` ignores NULL arguments when at least one non-NULL argument exists, so tables without TOAST still get `oldest_relevant_age` from their heap.

**Do not forget system catalogs and other databases.** Healthy-looking application tables do not prove the whole cluster is safe, especially if another database has not been vacuumed.

## 8. datfrozenxid: Database-Level Risk Boundary

`pg_database.datfrozenxid` represents the oldest potentially unfrozen XID across relevant relations in a database. It is a critical metric for monitoring wraparound risk **across the entire cluster**.

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;
~~~

This query can run from **one database** and list all other databases in the cluster, subject to privileges.

### 8.1. Why Check Every Database?

XIDs come from a **cluster-wide shared counter**. An `archive_db` that receives zero queries for six months will still see its `age(datfrozenxid)` climb rapidly while **another database** consumes XIDs.

~~~text
Shared cluster XID counter
       |
       +--- database app_prod (burns 10M XIDs/day)
       |
       +--- database reports (rarely modified)
       |
       +--- database archive (zero writes)

New XIDs in app_prod still age datfrozenxid
in reports and archive.
~~~

That is why **seldom-used databases still require anti-wraparound autovacuum** and must never be omitted from runbooks.

### 8.2. Percentage Toward the 2³¹ Boundary

You can build a reference monitoring metric:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    ROUND(
        100.0 * age(datfrozenxid)
        / 2147483648.0,
        2
    ) AS pct_of_half_range,
    2147483648::bigint
        - age(datfrozenxid)::bigint
        AS approximate_xids_to_half_range
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;
~~~

Here `2³¹` is a **mathematical reference ceiling**. Never treat the result as an exact countdown clock to failure day; PostgreSQL triggers protective thresholds earlier and behavior depends on vacuum progress. When this metric moves into red zones, treat it as an operational incident well before hitting the limit.

### 8.3. datfrozenxid Is Not the Last Vacuum Timestamp

`datfrozenxid` is an **XID horizon**, not a timestamp. To see when each table was last vacuumed, check `pg_stat_all_tables.last_vacuum` and `last_autovacuum`; remember **recent vacuum timestamps alone do not prove the freeze horizon advanced**.

### 8.4. Comparing the Two Levels

| Attribute | `relfrozenxid` | `datfrozenxid` |
|---|---|---|
| Stored in | `pg_class` | `pg_database` |
| Scope | Relation in the current database | Database |
| Used for | Finding tables/TOASTs with high XID age | Monitoring risk across databases |
| Unit via `age` | Number of XIDs | Number of XIDs |
| How it advances | Eligible `VACUUM` on the relation | When horizons of all relevant relations advance |
| Hours or minutes? | No | No |

**You cannot validly fix `datfrozenxid` with a manual `UPDATE pg_database SET ...`.** That is engine-managed metadata. You must resolve the tables, transactions, or slots actually preventing `VACUUM` from finishing.

## 9. Regular VACUUM, Aggressive VACUUM, and VACUUM FREEZE

### 9.1. Regular VACUUM

~~~sql
VACUUM some_table;
~~~

Regular `VACUUM` can:

- Reclaim space from dead tuples for reuse;
- Clean dead index tuples;
- Update the visibility map and maintenance stats;
- Freeze eligible tuples on pages it visits;
- Sometimes, though **not always**, advance `relfrozenxid`.

Regular `VACUUM` runs concurrently with normal table reads and writes under mild lock rules. It differs from `VACUUM FULL`, which rewrites the relation and takes strong locks.

### 9.2. Aggressive VACUUM

When `relfrozenxid` grows older than configured thresholds, PostgreSQL must inspect all pages **that might still hold unfrozen XIDs** (skipping `all-frozen` pages). That is **aggressive vacuum**, a deeper scan strategy to advance the XID horizon.

### 9.3. VACUUM (FREEZE)

~~~sql
-- Run only on a lab database table with proper permissions.
VACUUM (FREEZE, VERBOSE) demo_table;
~~~

The `FREEZE` option makes `VACUUM` freeze aggressively, effectively behaving as if freeze age thresholds were 0. It can be handy when preparing static datasets or demos, yet **it is not a magic "fix all MVCC issues" button**.

**Emergency note:** if a cluster is dangerously close to **refusing XID assignments**, modern PostgreSQL docs recommend running **regular `VACUUM`** after clearing blockers—not `VACUUM FULL` and not blindly reaching for `VACUUM FREEZE` as the first emergency step. `FREEZE` can perform extra work beyond the minimum needed to restore XID assignment safety as fast as possible.

### 9.4. VACUUM FULL Has Different Goals and Risks

`VACUUM FULL`:

- Rewrites the entire table to compact the physical file;
- Requires extra free disk space and an `ACCESS EXCLUSIVE` lock;
- Has its own XID allocation and rewrite costs;
- **Is not a preventive or emergency cure for wraparound**.

In short: **wraparound risk requires advancing the freeze horizon with proper `VACUUM`**, not "running FULL to make data cleaner."

## 10. Parameters Governing XID Age

Representative parameters in modern PostgreSQL:

| Parameter | Typical Default in PostgreSQL 18 | Role |
|---|---:|---|
| `vacuum_freeze_min_age` | 50,000,000 | Reference age before vacuum considers freezing encountered XIDs |
| `vacuum_freeze_table_age` | 150,000,000 | Age at which `VACUUM` uses an aggressive scan on a relation |
| `autovacuum_freeze_max_age` | 200,000,000 | `relfrozenxid` age forcing an anti-wraparound vacuum |
| `vacuum_failsafe_age` | 1,600,000,000 | Emergency threshold where `VACUUM` prioritizes wraparound prevention |

**These are reference defaults, not guaranteed settings on your server.** They vary by version or administrator tuning. Check actual values:

~~~sql
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
SHOW autovacuum_freeze_max_age;
SHOW vacuum_failsafe_age;
~~~

### 10.1. vacuum_freeze_min_age

If a tuple is frozen while still very young, a subsequent `UPDATE` creates a new tuple version and wastes the earlier freeze effort. `vacuum_freeze_min_age` balances **avoiding premature freezing** against protecting tuples before XIDs grow old.

Dropping this value very low everywhere does not automatically improve performance. PostgreSQL caps its effective value relative to `autovacuum_freeze_max_age` to maintain a safety margin.

### 10.2. vacuum_freeze_table_age

This is the threshold triggering **`VACUUM`'s aggressive scan strategy**, not when PostgreSQL stops writes. If the application burns transactions while a table has not been scanned deeply enough, `relfrozenxid` continues aging.

Its effective value is capped relative to `autovacuum_freeze_max_age`—typically around **95%** of `autovacuum_freeze_max_age`—leaving maintenance headroom before an anti-wraparound vacuum is forced.

### 10.3. autovacuum_freeze_max_age

When `relfrozenxid` age reaches this threshold, PostgreSQL triggers **anti-wraparound autovacuum**, even if the table has few dead tuples. The **200 million XID** default sits far below the ~2.147 billion limit to give a wide safety margin and avoid keeping commit history in `pg_xact` too long.

Crucial detail:

> Anti-wraparound protection still triggers when needed **even if regular autovacuum is disabled**.

That is **never** a reason to set `autovacuum=off`. Turning off regular maintenance lets dead tuples, index bloat, and freezing debt pile up; when forced anti-wraparound finally triggers, I/O and runtime spikes can be severe.

### 10.4. vacuum_failsafe_age

This is a very late line of defense. When danger is high, `VACUUM` can:

- Bypass normal cost-based vacuum delays;
- Skip non-essential phases such as index vacuuming;
- Prioritize advancing XID/MXID horizons to prevent XID shutdown.

**Failsafe is not a normal operating zone.** Seeing a relation approach `vacuum_failsafe_age` is a critical incident requiring DBA intervention, not something to rely on as routine rescue.

### 10.5. Never Tune Thresholds to Hide an Incident

Raising `autovacuum_freeze_max_age` defers anti-wraparound at the cost of retaining `pg_xact`/`pg_commit_ts` history longer, deferring freeze work, and shrinking operational margin if blockers exist. It does nothing to clear an orphaned prepared transaction or an old replication slot.

Changing settings requires understanding workloads, disk capacity, server version, reload/restart rules, per-table storage parameters, and validation. **Never edit production thresholds just to make an alert turn green.**

## 11. Normal Autovacuum vs. Anti-Wraparound Autovacuum

Autovacuum handles **dead tuple cleanup**, **`ANALYZE`**, **freezing**, and **wraparound prevention**.

### 11.1. Two Trigger Types to Distinguish

**Triggered by tuple churn:**

~~~text
Dead rows / INSERTs reach threshold
        |
        v
Autovacuum processes table to reclaim space & update stats
~~~

**Triggered by XID/MXID age:**

~~~text
age(relfrozenxid) reaches autovacuum_freeze_max_age
        |
        v
Anti-wraparound autovacuum is forced to run
        |
        v
Aggressive scan + freezing advances the horizon
~~~

A table with almost zero `UPDATE`/`DELETE`s may never trigger dead-tuple vacuuming, yet it **must** still be frozen on XID cycles.

### 11.2. Dead Tuple Thresholds Are Not XID Thresholds

Parameters like `autovacuum_vacuum_threshold` and `autovacuum_vacuum_scale_factor` trigger vacuuming based on data modification volume. They are **different** from `autovacuum_freeze_max_age`.

For example, a 100-million-row table stays untouched for a year while another database in the same cluster burns billions of XIDs. That static table still needs aggressive vacuuming to keep old tuples from being mistaken for "future" writes, even with zero dead tuples to clean.

### 11.3. Anti-Wraparound Autovacuum Does Not Yield Easily

Regular autovacuum workers automatically cancel when conflicting lock requests arrive. Anti-wraparound autovacuum carries higher system-protection priority and **does not automatically yield/cancel for ordinary lock requests** the way normal autovacuum does.

In `pg_stat_activity.query`, it appears with a label like:

~~~text
autovacuum: VACUUM ... (to prevent wraparound)
~~~

**Never casually run `pg_cancel_backend` or `pg_terminate_backend` on an anti-wraparound worker** just to "clear locks" without a DBA plan. Repeating that pushes the cluster closer to XID shutdown.

### 11.4. Why Can Anti-Wraparound Vacuum Use Heavy I/O?

It must verify no overly old XIDs remain on pages that are not `all-frozen`. A huge, rarely vacuumed table requires scanning many pages; upon entering failsafe, PostgreSQL prioritizes safety over normal cost delays. Proactive maintenance avoids painful maintenance bursts at bad times.

## 12. Safety Zones, Warnings, and XID Refusal

Thresholds operate across **multiple layers**:

~~~text
Increasing XID age →

    < 200M                    ~1.6B                 ~2.147B
       |                        |                      |
       v                        v                      v
  anti-wraparound         vacuum failsafe        2^31 wraparound
  autovacuum normally     emergency zone            boundary
  forced to run
                         [critical warnings and XID
                          refusal zone near the end]
~~~

This timeline is illustrative: exact defaults vary, and exact points where warnings or XID refusal begin depend on PostgreSQL version.

### 12.1. Warnings Near the Wraparound Boundary

Per PostgreSQL 18 docs, when a database has roughly **40 million transactions** remaining before the wraparound danger point, the server logs warnings like:

~~~text
WARNING: database "exampledb" must be vacuumed within
         ... transactions
HINT: To avoid XID assignment failures, execute a
      database-wide VACUUM in that database.
~~~

This is a **critical operational incident warning**, not a normal autovacuum threshold.

### 12.2. If Still Unresolved

Closer still—when roughly **3 million transactions** remain before the protection limit per PostgreSQL 18 docs—the server refuses commands that **require allocating a new XID**:

~~~text
ERROR: database is not accepting commands that assign
       new transaction IDs to avoid wraparound data loss
       in database "exampledb"
HINT: Execute a database-wide VACUUM in that database.
~~~

PostgreSQL refuses new XIDs to **prevent losing data visibility**, not because "disk is full" or "integer primary keys ran out."

Already-running transactions can finish within limits, and new read-only operations plus appropriate `VACUUM` commands can still execute. **Never assume the server is unrecoverable just because writes are refused.**

### 12.3. Warning Thresholds Depend on Major Version

The **40 million** and **3 million** figures reflect current PostgreSQL documentation referenced here. When operating a specific cluster version, consult the documentation for **your exact major version** and real logs; never hardcode runbooks from another version's numbers alone.

### 12.4. Crossing 200 Million XIDs Does Not Mean Data Is Corrupted

`autovacuum_freeze_max_age=200000000` is a **maintenance trigger threshold**. A table slightly past it may simply have an anti-wraparound vacuum currently running or queued for workers. Investigate it, but **do not interpret it as wraparound having already happened**.

Conversely, waiting until nearly 2 billion to act is far too late in most systems. Set early alerts based on **XID burn rate**, configuration, and how long `VACUUM` takes to complete.

## 13. Safe Monitoring Query Suite: Starting at the Database Level

This section is a **read-only query runbook** for roles with PostgreSQL monitoring privileges. None of these statements alter `pg_database` or `pg_class`. Some details may be restricted if a role lacks permission to view other sessions.

### 13.1. Ranking All Databases by XID Age

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    ROUND(
        age(datfrozenxid)::numeric
        / 2147483648::numeric * 100,
        2
    ) AS pct_of_half_range
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;
~~~

**How to interpret:**

- The top row with the largest `xid_age` is the database to inspect first.
- `pct_of_half_range` is a reference ratio toward 2³¹, **not disk usage percentage**.
- Idle/static databases can still appear at the top because the XID counter is cluster-wide.
- A single reading does not show trend; sample over time.

### 13.2. Comparing Against Current Autovacuum Settings

~~~sql
SELECT
    d.datname,
    age(d.datfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint
        AS configured_autovacuum_freeze_max_age,
    ROUND(
        100.0 * age(d.datfrozenxid)
        / NULLIF(
            current_setting('autovacuum_freeze_max_age')::numeric,
            0
        ),
        1
    ) AS pct_of_configured_age
FROM pg_catalog.pg_database AS d
ORDER BY xid_age DESC;
~~~

If `pct_of_configured_age` exceeds 100%, **do not treat it as 100% chance of data loss**. It simply means database age exceeds the server's configured anti-wraparound trigger threshold. Inspect specific tables, per-table reloptions, active `VACUUM`s, and blockers.

### 13.3. Estimating XID Burn Rate

To estimate XID growth rate, **record metric snapshots in your monitoring system** over time, for example:

~~~text
2026-11-14 09:00:00   xid_age=120,000,000
2026-11-15 09:00:00   xid_age=128,000,000

Growth of ~8 million XIDs in 24 hours.
~~~

**Be careful:** `age(datfrozenxid)` can **drop sharply whenever `VACUUM` advances `datfrozenxid`**; thus the difference between two readings does not always equal raw XID allocation rate. To measure the cluster counter rate directly, use proper XID metrics from your monitoring stack and distinguish 32-bit `xid` from `xid8`.

The example above assumes **`datfrozenxid` did not move** during the interval, not a universal formula for TPS.

## 14. Querying Tables With Highest XID Age in the Current Database

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.oid::regclass AS relation_oid,
    age(c.relfrozenxid) AS xid_age,
    c.reltuples::bigint AS estimated_rows,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_total_relation_size(c.oid)
    ) AS total_relation_size
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY xid_age DESC
LIMIT 30;
~~~

Where:

- `relkind='r'`: regular table.
- `relkind='m'`: materialized view.
- `relkind='t'`: TOAST table.
- `reltuples`: **estimated** row count, not an exact `COUNT(*)`.
- `pg_total_relation_size`: highlights potentially heavy maintenance cost on large tables/TOASTs.

Output covers **only the currently connected database**. `pg_class` is not a cluster-wide catalog containing `relfrozenxid` for every database.

### 14.1. Viewing Only Application Tables, Skipping System Catalogs

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    age(c.relfrozenxid) AS xid_age
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN (
      'pg_catalog',
      'information_schema',
      'pg_toast'
  )
ORDER BY xid_age DESC
LIMIT 20;
~~~

This is purely an **application investigation query**, not the complete risk picture. **System catalogs and TOAST tables also require freezing**; filtering them out of final reports can hide the exact relation holding an old XID.

### 14.2. Combined Report for Main Tables and TOAST

~~~sql
SELECT
    c.oid::regclass AS table_name,
    age(c.relfrozenxid) AS table_xid_age,
    t.oid::regclass AS toast_name,
    age(t.relfrozenxid) AS toast_xid_age,
    GREATEST(
        age(c.relfrozenxid),
        age(t.relfrozenxid)
    ) AS max_table_or_toast_age
FROM pg_catalog.pg_class AS c
LEFT JOIN pg_catalog.pg_class AS t
    ON t.oid = c.reltoastrelid
WHERE c.relkind IN ('r', 'm')
ORDER BY max_table_or_toast_age DESC
LIMIT 30;
~~~

This is a practical way to never miss TOAST tables in age analysis.

### 14.3. Partitioned Tables: Do Not Check Only the Parent Table

A partitioned parent (`relkind='p'`) does not store data tuples directly like a regular heap table. Each partition is a separate relation with its own `relfrozenxid`.

~~~sql
SELECT
    inhparent::regclass AS parent_table,
    inhrelid::regclass AS partition_table
FROM pg_catalog.pg_inherits
ORDER BY inhparent::regclass::text,
         inhrelid::regclass::text;
~~~

If a logical table has 365 daily partitions, do not judge risk solely by the parent name. Inspect **physical partitions**, especially historical partitions that are rarely updated and easy to overlook in maintenance.

### 14.4. Temporary Tables and Autovacuum Differences

**Autovacuum cannot access another session's temporary tables.** Temporary tables must therefore be analyzed/vacuumed by their owning session when appropriate. Still, that does not mean every temp table leaves dangerous XIDs behind after a session closes; their lifecycle and vacuum rules differ from permanent tables.

## 15. Monitoring Last VACUUM and Dead Tuples

`pg_stat_all_tables` provides per-relation maintenance metrics:

~~~sql
SELECT
    relid::regclass AS table_name,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_catalog.pg_stat_all_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

### 15.1. Do Not Look Only at last_autovacuum

`last_autovacuum IS NOT NULL` proves autovacuum ran, yet does not prove `relfrozenxid` advanced safely. It may have been a regular `VACUUM` without an aggressive scan. Conversely, a table with an old `last_autovacuum` yet very fresh `relfrozenxid` may not need freezing yet.

**Combine signals:** XID age + `VACUUM` timestamps + `VACUUM` progress + blockers.

### 15.2. n_dead_tup Is Not XID Age

`n_dead_tup` estimates dead tuples. XID age measures **unfrozen boundary age**—completely different things. A table with `n_dead_tup=0` can still need an anti-wraparound vacuum.

### 15.3. Regular VACUUM Does Not Immediately Return Disk Space to the Filesystem

Regular `VACUUM` primarily makes space inside the table **reusable**. If the table file stays the same size after `VACUUM`, that does not mean freezing failed. `VACUUM FULL` serves physical file compaction with heavier costs and stronger locks.

## 16. Monitoring Active VACUUM Runs

While the server processes large tables, `pg_stat_progress_vacuum` answers:

> "Is VACUUM currently running, on which table, in which phase, and how many heap blocks has it processed?"

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    CASE
        WHEN heap_blks_total > 0
        THEN ROUND(
            100.0 * heap_blks_scanned
            / heap_blks_total,
            1
        )
        ELSE NULL
    END AS pct_heap_scanned,
    index_vacuum_count
FROM pg_catalog.pg_stat_progress_vacuum
ORDER BY datname, table_name;
~~~

Visible columns and phases can change across major versions; this query uses columns widely present across supported PostgreSQL releases.

### 16.1. Percent Heap Scanned Is Not Total Overall Progress

`heap_blks_scanned / heap_blks_total` measures **heap scan progress**; `VACUUM` also handles index vacuuming, heap vacuuming, cleanup, and stats updates. Thus 100% heap scanned **does not mean `VACUUM` is finished**.

### 16.2. Inspecting VACUUM Sessions

~~~sql
SELECT
    pid,
    datname,
    backend_type,
    state,
    query_start,
    wait_event_type,
    wait_event,
    query
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'autovacuum worker'
   OR query ILIKE '%VACUUM%'
ORDER BY query_start;
~~~

Do not label a worker "hung" just because it has run for a long time; it may be scanning a huge table or waiting on resources. Correlate progress, I/O, lock waits, and XID burn rate.

### 16.3. Note on Query Text and Viewing Privileges

Normal roles may not see query details of other sessions. Monitoring systems should use minimal **read-only stats roles** (such as `pg_monitor` where policy permits), never granting superuser to dashboards just to run `SELECT`s.

## 17. Long-Running Transactions: Why Can VACUUM Be Held Back?

A transaction holding an old snapshot can force PostgreSQL to keep old row versions that snapshot can still see. This holds back the **vacuum cleanup horizon**, causing dead tuples/bloat, and in some cases restricts advancing freeze horizons.

Example:

~~~text
Session A:
    BEGIN REPEATABLE READ;
    SELECT ...;  -- takes snapshot
    ... idle for 4 hours ...

Sessions B/C/D:
    UPDATE / DELETE many rows;
    COMMIT;

Autovacuum:
    cannot clean row versions that A's old
    snapshot might still need.
~~~

### 17.1. Finding Sessions With Long-Open Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    state,
    xact_start,
    now() - xact_start AS transaction_duration,
    backend_xid,
    age(backend_xid) AS backend_xid_age,
    backend_xmin,
    age(backend_xmin) AS backend_xmin_age,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

**Two crucial columns:**

- `backend_xid`: top-level XID assigned to the backend, if any.
- `backend_xmin`: XID horizon related to the snapshot/age held by the backend, if any.

Not every session has a `backend_xid`. A read-only transaction can hold a snapshot and `backend_xmin` without ever being assigned a write XID.

### 17.2. Finding the Oldest XID Horizons

~~~sql
SELECT
    pid,
    datname,
    usename,
    state,
    xact_start,
    age(backend_xid) AS xid_age,
    age(backend_xmin) AS xmin_age
FROM pg_catalog.pg_stat_activity
WHERE backend_xid IS NOT NULL
   OR backend_xmin IS NOT NULL
ORDER BY GREATEST(
    age(backend_xid),
    age(backend_xmin)
) DESC NULLS LAST;
~~~

`age(NULL::xid)` returns NULL. In PostgreSQL, `GREATEST` skips NULL arguments when non-NULL values exist, sorting by whichever horizon is older across the two columns.

### 17.3. How Is idle in transaction Dangerous?

~~~sql
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS transaction_duration,
    age(backend_xmin) AS xmin_age
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
~~~

An **`idle in transaction`** session has an open transaction yet is not executing a statement at the moment of inspection. It can:

- Hold an old snapshot;
- Hold row or table locks;
- Prevent `VACUUM` from cleaning enough dead tuples;
- Prolong holding an XID horizon;
- Cause bloat and operational overhead.

**Not every `idle in transaction` session causes immediate wraparound.** Check `backend_xmin`, duration, workload, and transaction type.

### 17.4. How to Handle It

In applications:

- Keep transactions short and always `COMMIT`/`ROLLBACK` cleanly.
- Never open a transaction and wait for user clicks, slow APIs, or lengthy non-DB work.
- Fix connection pools returning connections with open transactions.
- Consider `idle_in_transaction_session_timeout` after evaluating business flows.

In operations:

- Identify PID, application, and owner of the long transaction;
- Contact the owner to commit or roll back safely;
- Only consider `pg_cancel_backend`/`pg_terminate_backend` per an authorized runbook after assessing impact;
- Never blindly terminate a transaction executing a critical payment or migration.

## 18. Prepared Transactions / Two-Phase Commit Can Hold Old XIDs

PostgreSQL supports two-phase commit via:

~~~sql
PREPARE TRANSACTION 'some-gid';
COMMIT PREPARED 'some-gid';
ROLLBACK PREPARED 'some-gid';
~~~

This is illustrative syntax—**never run it as a casual demo**. Once a transaction is **PREPARE**d without being `COMMIT`/`ROLLBACK PREPARED`, it holds its transaction ID and resources indefinitely, even after the original client disconnects.

### 18.1. Inspecting Prepared Transactions

~~~sql
SELECT
    gid,
    "transaction" AS xid,
    age("transaction") AS xid_age,
    prepared,
    now() - prepared AS prepared_duration,
    owner,
    database
FROM pg_catalog.pg_prepared_xacts
ORDER BY xid_age DESC;
~~~

`pg_prepared_xacts` has a column named `transaction`, quoted to avoid colliding with the SQL keyword. `prepared` is when the transaction entered the prepared state.

### 18.2. Never COMMIT PREPARED or ROLLBACK PREPARED Blindly

A prepared transaction typically belongs to a multi-system distributed coordinator. Rolling it back just to free an XID without knowing whether the coordinator decided to commit can create **cross-system data inconsistency**.

When `age("transaction")` is very high:

1. Verify GID, owner, database, and coordinating system.
2. Check actual distributed transaction outcome.
3. Run `COMMIT PREPARED` or `ROLLBACK PREPARED` matching the coordinator's decision.
4. Re-measure XID horizons and observe `VACUUM`.

**Prepared transactions are one of the mandatory blocker checks during serious wraparound alerts.**

## 19. Replication Slots and Held Horizons

Replication slots track state needed for a consumer or replica. An unconsumed slot can pin resources:

- **`restart_lsn`:** governs WAL retention for replication; impacts WAL disk usage.
- **`xmin`:** XID horizon retained for table row data in relevant setups.
- **`catalog_xmin`:** horizon protecting catalog tuples, commonly needed for logical decoding.

**WAL retention** and **XID vacuum horizons** are related, yet **not the same metric**.

### 19.1. Checking Inactive Slots and XID Age

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    xmin,
    age(xmin) AS xmin_age,
    catalog_xmin,
    age(catalog_xmin) AS catalog_xmin_age
FROM pg_catalog.pg_replication_slots
ORDER BY GREATEST(
    age(xmin),
    age(catalog_xmin)
) DESC NULLS LAST;
~~~

A slot without `xmin`/`catalog_xmin` should not be called an XID blocker solely because `restart_lsn` is old; it poses a separate **WAL retention risk**. Read each column accurately.

### 19.2. Why Are Old Slots Dangerous?

When a slot pins a very old `xmin` or `catalog_xmin`, PostgreSQL must preserve row/catalog versions so the consumer can still decode/read them. That blocks `VACUUM` cleanup and can stall advancing certain horizons.

Example:

~~~text
Logical replication consumer stopped
          |
          v
Slot stops advancing xmin/catalog_xmin
          |
          v
VACUUM restricted from removing old tuples
          |
          v
Bloat grows; freeze horizon may struggle to advance
~~~

### 19.3. Never Blindly Drop Replication Slots

~~~sql
-- Reference syntax only; DO NOT run blindly in production:
-- SELECT pg_drop_replication_slot('slot_name');
~~~

Dropping a slot can make a replica/consumer **unable to resume from required WAL**, forcing a rebuild/resync or breaking sync continuity. DBAs must confirm whether the slot is still used, impact on subscribers/replicas, and the recovery plan before acting.

### 19.4. hot_standby_feedback

In physical replication, `hot_standby_feedback` sends snapshot retention needs from a standby back to the primary, making the primary keep row versions longer so standby queries aren't canceled by vacuum. This can pull the **vacuum cleanup horizon** backward, requiring a trade-off between standby query stability and primary bloat.

**Never toggle `hot_standby_feedback` just to silence an alert** without understanding replication topology, streaming lag, and `VACUUM` impact.

## 20. Multixact ID Wraparound: Related Yet Distinct From XID

PostgreSQL also uses **Multixact IDs (MXIDs)** when multiple transactions hold row locks on the same tuple concurrently; multi-locker info is represented via a Multixact ID with member lists stored outside the tuple header.

Like XIDs, Multixact IDs use a **32-bit counter** and have their own aging and freezing mechanisms.

| XID Wraparound | MXID Wraparound |
|---|---|
| Tracks creating/deleting transactions and MVCC visibility | Tracks groups of transactions concurrently locking tuples |
| `pg_class.relfrozenxid` | `pg_class.relminmxid` |
| `pg_database.datfrozenxid` | `pg_database.datminmxid` |
| `age(xid)` | `mxid_age(mxid)` |
| `autovacuum_freeze_max_age` | `autovacuum_multixact_freeze_max_age` |
| `vacuum_failsafe_age` | `vacuum_multixact_failsafe_age` |

### 20.1. Monitoring Multixact Age at Database Level

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    mxid_age(datminmxid) AS mxid_age
FROM pg_catalog.pg_database
ORDER BY mxid_age DESC;
~~~

### 20.2. Monitoring Multixact Age at Relation Level

~~~sql
SELECT
    c.oid::regclass AS table_name,
    age(c.relfrozenxid) AS xid_age,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_catalog.pg_class AS c
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY mxid_age DESC
LIMIT 20;
~~~

### 20.3. Reference Settings

~~~sql
SHOW autovacuum_multixact_freeze_max_age;
SHOW vacuum_multixact_freeze_min_age;
SHOW vacuum_multixact_freeze_table_age;
SHOW vacuum_multixact_failsafe_age;
~~~

In PostgreSQL 18, `autovacuum_multixact_freeze_max_age` typically defaults to **400 million MXIDs**, though always verify your server's actual configuration.

### 20.4. MXID Exhaustion Differs From XID Exhaustion Scope

If MXID wraparound risk gets too high, PostgreSQL refuses **operations needing a new Multixact ID**. That differs from XID exhaustion, which blocks a broader set of commands needing new XIDs.

**Never merge both alerts into a single "transaction age" metric.** Monitor both `age(datfrozenxid)` and `mxid_age(datminmxid)`, as either can hit its limit first.

## 21. Safe Lab: Observing xmin, xmax, and VACUUM

**Goal:** observe tuple versions with `xmin`/`xmax` and `VACUUM` on a small table; do not simulate real XID wraparound. The lab uses a dedicated schema `xid_lab_233`; if that schema already exists, rename it rather than deleting existing data.

### 21.1. Create Table

~~~sql
CREATE SCHEMA xid_lab_233;

CREATE TABLE xid_lab_233.inventory (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL
        CHECK (quantity >= 0),
    note TEXT NOT NULL DEFAULT ''
);

INSERT INTO xid_lab_233.inventory
    (sku, quantity, note)
VALUES
    ('LAB-01', 10, 'Initial version'),
    ('LAB-02', 20, 'Unchanged');
~~~

### 21.2. View System Columns

~~~sql
SELECT
    sku,
    quantity,
    xmin::text AS inserting_xid,
    xmax::text AS xmax_raw
FROM xid_lab_233.inventory
ORDER BY sku;
~~~

`xmin`/`xmax` are **system columns**. Exact numbers depend on the server and lab transaction history; **never copy XID values from another machine expecting identical numbers**.

### 21.3. Create a New Tuple Version With UPDATE

~~~sql
UPDATE xid_lab_233.inventory
SET
    quantity = 12,
    note = 'Updated'
WHERE sku = 'LAB-01'
RETURNING
    sku,
    quantity,
    xmin::text AS inserting_xid,
    xmax::text AS xmax_raw;
~~~

When `UPDATE` creates a new tuple version, the new version's `xmin` reflects the transaction that created it. The old version can remain physically until `VACUUM` safely reclaims it.

### 21.4. Check Table Horizon Age

~~~sql
SELECT
    c.oid::regclass AS table_name,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age,
    c.relminmxid,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'xid_lab_233.inventory'::regclass;
~~~

**Do not expect `age(relfrozenxid)` to equal `age(xmin)` of row `LAB-01`.** The table-level boundary reflects the whole relation and vacuum state, not one individual tuple.

### 21.5. Observe VACUUM (VERBOSE)

Run the following **outside any `BEGIN` transaction**, because PostgreSQL forbids `VACUUM` inside a normal transaction block:

~~~sql
VACUUM (VERBOSE, ANALYZE) xid_lab_233.inventory;
~~~

Read the messages about pages, tuples, and XID horizons for your server version. On a tiny lab table with very young XIDs, `relfrozenxid` age may not drop noticeably.

### 21.6. Try FREEZE in the Dedicated Lab

~~~sql
VACUUM (FREEZE, VERBOSE) xid_lab_233.inventory;
~~~

This example is strictly **for a small lab table** where cost is negligible and the goal is learning. `FREEZE` sets aggressive freezing; PostgreSQL freezes only versions **safe to freeze** under visibility rules.

Then check:

~~~sql
SELECT
    age(c.relfrozenxid) AS xid_age_after
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'xid_lab_233.inventory'::regclass;
~~~

Do not assume `xmin=2` after freezing in modern PostgreSQL. Observing `relfrozenxid` changes and `VACUUM` logs is far more accurate.

### 21.7. VACUUM Must Not Be Put Inside BEGIN to ROLLBACK

This snippet:

~~~sql
BEGIN;
VACUUM xid_lab_233.inventory;
-- Error: VACUUM cannot run inside a transaction block
ROLLBACK;
~~~

is shown to explain the syntax/operational error—**not a sequence to run in production**. Run `VACUUM` in autocommit mode in your SQL client.

### 21.8. Lab Takeaways

The lab demonstrates:

- Tuples carry transaction-related system columns.
- `UPDATE` creates new tuple versions under MVCC.
- `VACUUM` is a standalone maintenance command.
- Freezing concerns long-term XID safety, not changing business values.
- You do not need billions of transactions or dangerous commands to learn this mechanism.

**It does not simulate real wraparound conditions.** Anti-wraparound alerts are examined through hypothetical scenarios and monitoring SQL.

## 22. Diagnosing Rising XID Age When VACUUM Fails to Advance Horizons

Consider a scenario:

~~~text
Prod database:
    age(datfrozenxid) rises steadily.
    One relation has high age(relfrozenxid).
    Autovacuum is enabled.
    Multiple VACUUMs still fail to lower the horizon age.
~~~

Do not immediately raise `autovacuum_freeze_max_age`. Check each group of evidence systematically.

### 22.1. Is a Table or TOAST Holding an Old Horizon?

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    age(c.relfrozenxid) AS xid_age
FROM pg_catalog.pg_class AS c
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY xid_age DESC
LIMIT 30;
~~~

If the top relation sits in a different database, **connect to that database** to inspect its `pg_class` details.

### 22.2. Is VACUUM Running and Making Progress?

~~~sql
SELECT
    pid,
    datname,
    relid::regclass,
    phase,
    heap_blks_total,
    heap_blks_scanned
FROM pg_catalog.pg_stat_progress_vacuum;
~~~

If a worker has been running for a long time, check logs, I/O, wait events, and table size. `VACUUM` may simply still be midway through an aggressive scan and hasn't updated the final horizon yet.

### 22.3. Is an Old Snapshot/XID Being Held?

~~~sql
SELECT
    pid,
    datname,
    application_name,
    state,
    age(backend_xid) AS xid_age,
    age(backend_xmin) AS xmin_age,
    now() - xact_start AS transaction_age
FROM pg_catalog.pg_stat_activity
WHERE backend_xid IS NOT NULL
   OR backend_xmin IS NOT NULL
ORDER BY GREATEST(
    age(backend_xid),
    age(backend_xmin)
) DESC NULLS LAST;
~~~

### 22.4. Are There Orphaned Prepared Transactions?

~~~sql
SELECT
    gid,
    database,
    age("transaction") AS xid_age,
    prepared
FROM pg_catalog.pg_prepared_xacts
ORDER BY xid_age DESC;
~~~

### 22.5. Are Replication Slots Holding xmin/catalog_xmin?

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    age(xmin) AS xmin_age,
    age(catalog_xmin) AS catalog_xmin_age
FROM pg_catalog.pg_replication_slots
ORDER BY GREATEST(
    age(xmin),
    age(catalog_xmin)
) DESC NULLS LAST;
~~~

### 22.6. Are There Lock, Configuration, or Resource Issues?

Possibilities to check:

- Autovacuum is disabled or worker/cost settings are overly throttled.
- DDL jobs or conflicting locks repeatedly interrupt or slow down vacuuming.
- Disk nearly full, starved I/O, or filesystem issues.
- Transactions, replication slots, or prepared transactions pinning old horizons.
- A huge table with very few `all-frozen` pages.
- Old partitions, TOAST tables, or materialized views neglected by maintenance.
- A static database untouched by apps whose XID age rises due to another busy database.

**Separate causes clearly:** a long transaction blocks dead-tuple cleanup; a table that rarely gets aggressive vacuums can keep an old `relfrozenxid` even with zero long transactions. Never force one hypothesis onto every alert.

## 23. Runbook When an Anti-Wraparound Warning Appears

This is an incident response framework **for authorized DBAs who understand the topology**, not a beginner guide to improvise in production. Priorities: avoid XID exhaustion and preserve data integrity.

### Phase A — Confirm Severity

1. Record PostgreSQL version, affected database, and exact log messages.
2. Run `SELECT datname, age(datfrozenxid) ... FROM pg_database`.
3. Check XID burn rate and headroom to configured thresholds.
4. Identify the oldest `relfrozenxid` table/TOAST in the target database.
5. Check whether an anti-wraparound `VACUUM` is already running.

If you see:

~~~text
database ... must be vacuumed within ... transactions
~~~

this is an **active incident alert** requiring immediate runbook action—do not wait for a scheduled maintenance window.

### Phase B — Clear Valid Blockers

PostgreSQL docs recommend inspecting:

- Old prepared transactions in `pg_prepared_xacts`;
- Long-open transactions with old `backend_xid`/`backend_xmin`;
- Unused replication slots pinning `xmin`/`catalog_xmin`;
- Locks or resource contention blocking `VACUUM`.

**Never blindly:**

- Kill a critical business transaction without knowing its impact.
- Roll back a prepared transaction awaiting a coordinator's decision.
- Drop a slot serving an active replica or consumer.
- Cancel an anti-wraparound worker just because it uses I/O.

### Phase C — Run VACUUM to Advance the Freeze Horizon

On the identified database, reference command:

~~~sql
-- Run outside an explicit transaction block;
-- requires privileges to vacuum all tables including system catalogs.
VACUUM;
~~~

In an emergency, **the executing role's privileges are critical**. PostgreSQL docs warn that without permission to vacuum system catalogs and relevant relations, `datfrozenxid` cannot advance sufficiently. An appropriately privileged DBA must execute per runbook.

`VACUUM` with no table list operates only on **the current database** (across tables the role owns/can vacuum); it **does not vacuum every database in the cluster**. If multiple databases are at risk, run it per database or use `vacuumdb` configured appropriately.

### Phase D — If the Database Has Already Refused New XIDs

Per modern PostgreSQL docs, **regular `VACUUM` can still run** even after the server refuses new XIDs. Recommended flow:

1. Resolve eligible old prepared transactions;
2. Safely end transactions/snapshots holding excessively old horizons;
3. Clean up **truly abandoned** replication slots after impact review;
4. Execute **regular `VACUUM`** on the affected database;
5. Re-measure `age(datfrozenxid)`/`relfrozenxid` and verify write operations recover;
6. Restore/improve autovacuum config, monitoring, and operational procedures.

**Never use `VACUUM FULL` in an emergency**: it needs XIDs and strong locks, and may fail or worsen risk. Likewise **do not blindly default to `VACUUM FREEZE` as a "quick fix"**: modern docs note it can do more work than the minimum needed to safely restore XID allocation.

**Do not drop into single-user mode following old blog posts without a concrete reason.** Modern PostgreSQL includes protections in normal mode; bypassing them carelessly increases risk.

### Phase E — Post-Incident Verification and Prevention

- Confirm `datfrozenxid` age dropped or stopped climbing abnormally.
- Check remaining oldest tables/TOASTs.
- Verify `pg_stat_progress_vacuum` and server logs.
- Confirm normal write workloads, latency, and lock waits are healthy.
- Fix root causes: prepared xacts, slots, long transactions, autovacuum tuning, or resource bottlenecks.
- Configure early alerts on XID/MXID age and burn rate.
- Document timeline, actions taken, impact, and runbook updates.

### 23.1. Never Write Directly to System Catalogs to "Reset Age"

**Strictly forbidden as a "fix":**

~~~sql
-- ABSOLUTELY DO NOT RUN:
-- UPDATE pg_catalog.pg_database
-- SET datfrozenxid = ...;
~~~

Catalog boundaries reflect physical tuple invariants and visibility guarantees. Editing them manually desynchronizes metadata from actual heap data and risks data loss or corruption.

### 23.2. Backups Do Not Replace Anti-Wraparound VACUUM

Backups and PITR are vital for disaster recovery, yet **they do not make unfrozen XIDs in a running cluster safe**. Having backups never excuses skipping anti-wraparound maintenance.

## 24. Designing Alerts for XID/MXID Age

A monitoring stack should store time-series metrics like:

~~~text
postgres_database_xid_age{database="orders"} = ...
postgres_database_mxid_age{database="orders"} = ...
postgres_relation_xid_age{database="orders",relation="..."} = ...
postgres_autovacuum_running{database="orders"} = ...
postgres_oldest_backend_xmin_age{database="orders"} = ...
postgres_replication_slot_catalog_xmin_age{slot="..."} = ...
~~~

These are **illustrative metric names**, not guarantees that a specific exporter uses identical names. Map them to the actual metrics exposed by your Prometheus exporter, cloud tool, or custom scripts.

### 24.1. Sample Alert Tiers

| Illustrative Severity | Observed Condition | Action |
|---|---|---|
| Info | XID age grows steadily; vacuum healthy | Continue monitoring |
| Early | A database/table approaches internal maintenance threshold | Check autovacuum, trends, add maintenance capacity if needed |
| High | Age exceeds configured anti-wraparound threshold; vacuum not completing | Investigate blockers, workers, progress, DBA escalation |
| Critical | Approaching failsafe zone or wraparound warning logs | Activate incident response; prioritize XID protection |
| Emergency | Server refuses new XIDs | Controlled recovery runbook; `VACUUM` after clearing blockers |

**Never copy rigid percentages blindly across all clusters.** Tailor thresholds to server version, config, XID burn rate, table/database counts, and time required for aggressive `VACUUM` to finish.

### 24.2. What Should an Alert Include?

A useful alert might report:

~~~text
Cluster: cluster-a
Database: reporting
XID age: 165,000,000
autovacuum_freeze_max_age: 200,000,000
Oldest table: archive.events_2022
Last autovacuum: 10 days ago
Oldest backend_xmin age: 8,000,000
Oldest slot catalog_xmin age: 140,000,000
Observed XID consumption: ~12,000,000/day
Runbook: PostgreSQL XID wraparound response
~~~

These numbers are **hypothetical** to illustrate layout, not real system state. With real data, avoid posting sensitive details in public channels.

### 24.3. Rate-Based Forecasting Must Include Remediation Time

If maintenance threshold is 4 days away, yet vacuuming one huge table takes 10 hours, investigating a replication slot takes 1 day, and DBAs are only on shift during business hours, alerting at "4 days left" can **already be too late**. Alert early enough to diagnose and fix before writes must pause.

### 24.4. Use Transaction Age Rather Than Calendar Schedules

Peak XID growth can spike during flash sales, batch imports, migrations, or traffic surges. Relying on a calendar email saying "run VACUUM every 30 days" without monitoring XIDs lets systems cross thresholds ahead of schedule.

## 25. Why Do Long Transactions, Bloat, and Wraparound Often Appear Together?

All three involve **ability to clean or freeze MVCC metadata**, though they are not a single identical issue.

### 25.1. Bloat

A long transaction holds an old snapshot, stopping `VACUUM` from removing tuple versions that snapshot may still need. As `UPDATE`/`DELETE`s continue, tables and indexes bloat.

### 25.2. XID Age

Meanwhile, the global XID counter keeps advancing as other workers write. `age(datfrozenxid)`/`age(relfrozenxid)` grows if horizons fail to advance.

### 25.3. Freeze Horizon

Advancing `relfrozenxid` requires an eligible `VACUUM` and safe horizons. If a very old snapshot pins tuples, or `VACUUM` cannot finish on time, XID horizons remain old.

### 25.4. Diagnostic Summary

~~~text
Long transaction / old slot
        |
        +-- can pin dead tuples
        |      |
        |      +-- bloat
        |
        +-- can pin snapshot/XID horizon
               |
               +-- restricts cleanup/freeze progress
                      |
                      +-- XID age rises with workload
~~~

Yet a database's XID age can also grow simply because **a huge static table has not had an aggressive vacuum**, even with zero long transactions. Always check both **horizon blockers** and **maintenance schedules / relation sizes**.

## 26. Common Misconceptions

| Misconception | Accurate Explanation |
|---|---|
| "XIDs are 64-bit now, so wraparound is gone." | `xid8` extends identifiers; tuple/MVCC mechanics still manage 32-bit XIDs |
| "Problems only start after 4.29 billion transactions." | Safe comparison window is roughly **2³¹** from unfrozen XIDs |
| "PostgreSQL resets XIDs every 24 hours." | XIDs advance per transaction allocation, not by wall clock |
| "Opening a transaction assigns an XID immediately." | A virtual XID exists; non-virtual XIDs normally allocate when writes occur |
| "Each database has its own XID counter." | All databases in a cluster share one XID counter |
| "Tables without UPDATEs never need VACUUM." | Old tuples in static tables still require freezing |
| "VACUUM is only for shrinking files." | `VACUUM` also cleans dead tuples, updates visibility map, freezes, and prevents wraparound |
| "Regular VACUUM always advances relfrozenxid." | Only when `VACUUM` scans enough required pages |
| "VACUUM FREEZE is always the best choice." | It can add unnecessary work and is unsuitable as a default emergency first step |
| "VACUUM FULL rescues wraparound." | `FULL` needs heavy locks/resources, can need XIDs, and is not a wraparound rescue |
| "xmin = 2 is the only frozen state." | Modern PostgreSQL uses frozen flags and can preserve `xmin` |
| "xmax != 0 means the row is deleted." | `xmax` also represents locks/Multixacts and uncommitted states |
| "age(xid) is seconds since commit." | It counts elapsed XIDs |
| "datfrozenxid is the timestamp of last vacuum." | It is an XID horizon, not a timestamp |
| "Vacuuming one application table makes the cluster safe." | TOAST, catalogs, other relations, and other databases also matter |
| "autovacuum=off means anti-wraparound never runs." | PostgreSQL still forces anti-wraparound when needed |
| "Zero dead tuples means zero XID risk." | Live tuples still require freezing |
| "Just raise thresholds to silence alerts." | Does not clear blockers/horizons and shrinks safety margins |
| "Terminate every PID with high age." | Can abort critical business work; confirm owner and impact first |
| "Replication slots only retain WAL." | Some slots also pin `xmin`/`catalog_xmin` |
| "With backups, wraparound isn't dangerous." | Backups do not replace MVCC maintenance on a live cluster |
| "Wraparound warnings mean stop the server immediately." | Modern PostgreSQL provides online `VACUUM` recovery runbooks |
| "XID and MXID are the same thing." | Two distinct ID spaces with separate horizons and thresholds |
| "Only pay attention when pct_of_half_range hits 100%." | Alert early based on maintenance thresholds and trends |
| "Full VACUUM means running inside BEGIN then rollback." | `VACUUM` cannot run inside a normal transaction block |

## 27. Practice Exercises

Exercises never require pushing XIDs to dangerous levels. Use read-only queries, lab table `xid_lab_233`, or numerical calculations.

### Exercise 1 — Distinguishing XID From Elapsed Time

Explain why a database running for one year at 10,000 write transactions/day can have a lower XID age than another running for 10 days at 10 million write transactions/day.

**Hint:** age is measured in XID allocations elapsed, not uptime.

### Exercise 2 — XID Wraparound Math

Compute:

~~~text
2^32 = ?
2^31 = ?
~~~

**Answer:** `4,294,967,296` and `2,147,483,648`. Why is the critical boundary roughly **half the XID space** rather than waiting for a full cycle?

### Exercise 3 — Checking Current XID Without Allocating One

Compare:

~~~sql
SELECT pg_current_xact_id_if_assigned();
SELECT pg_current_xact_id();
~~~

**Question:** Which function allocates an XID if the transaction lacks one? Why shouldn't a read-only dashboard call the allocating function repeatedly?

### Exercise 4 — Reading xmin and xmax

On `xid_lab_233.inventory`, observe `xmin` and `xmax` before and after an `UPDATE`.

**Question:** What does the new `xmin` indicate? Why must `xmax` never be interpreted solely as "deleted"?

### Exercise 5 — Frozen Flag

After `VACUUM (FREEZE)` on the lab table, must `xmin` change to 2?

**Answer:** No, in modern PostgreSQL; freezing primarily uses metadata flags and does not guarantee `xmin=2`.

### Exercise 6 — Static Tables Still Need Freezing

A table was loaded last year with 100 million rows and almost zero dead tuples. Elsewhere in the cluster, another app writes continuously.

**Question:** Does that static table need anti-wraparound `VACUUM`? Why?

### Exercise 7 — Finding the Highest-Risk Database

Write `SELECT datname, age(datfrozenxid) ... FROM pg_database ORDER BY ... DESC`.

**Question:** Why does a low-traffic database still see its XID age rise?

### Exercise 8 — Finding Oldest Tables

In the lab database, find the 10 relations with highest `age(relfrozenxid)`. Avoid assuming "vacuumed yesterday means safe"; combine `relfrozenxid` with `VACUUM` logs to evaluate.

### Exercise 9 — TOAST

Write a query joining `pg_class` for heap tables with `pg_class` for TOAST tables via `reltoastrelid` and compare their ages.

**Question:** If heap age is small while TOAST age is huge, is vacuuming only the heap in a naive check enough to explain database age?

### Exercise 10 — Half-Range Percentage

Suppose `age(datfrozenxid)=1,000,000,000`. Compute:

\[
\frac{1,000,000,000}{2,147,483,648}\times100\%
\]

The result is roughly **46.6%**. Why does this number **not** permit waiting until 99% to run maintenance?

### Exercise 11 — Configuration Thresholds

Run:

~~~sql
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
SHOW autovacuum_freeze_max_age;
SHOW vacuum_failsafe_age;
~~~

**Question:** Among these settings, which one forces anti-wraparound `VACUUM` to run? Which one is the late emergency layer?

### Exercise 12 — Regular VACUUM vs. FULL

Distinguish `VACUUM`, `VACUUM (FREEZE)`, and `VACUUM FULL` in scan scope, locking, and purpose.

**Guidance:** `FULL` rewrites/compacts files with strong locks; it is not a wraparound rescue option.

### Exercise 13 — Tracking Autovacuum Progress

Run the `pg_stat_progress_vacuum` query from section 16.

**Question:** If `heap_blks_scanned = heap_blks_total`, is `VACUUM` guaranteed to have finished all index/cleanup phases?

### Exercise 14 — Finding Long Transactions

Use `pg_stat_activity` to inspect `xact_start`, `backend_xid`, `backend_xmin`, and `age(...)`.

**Question:** Can a read-only transaction hold a snapshot while `backend_xid IS NULL`? Why must you also check `backend_xmin`?

### Exercise 15 — Orphaned Prepared Transaction

A prepared transaction has `age("transaction")` near 600 million.

**Question:** Should you immediately run `ROLLBACK PREPARED`? Who must confirm the decision and why?

### Exercise 16 — Replication Slots

Suppose a logical slot has `active=FALSE`, `catalog_xmin_age=700M`, and a very old `restart_lsn`.

**Question:** Which independent risks exist? Why can't you just drop the slot without checking the subscriber/recovery?

### Exercise 17 — VACUUM Inside a Transaction

Try `BEGIN; VACUUM xid_lab_233.inventory;` in the lab and then roll back.

**Expected:** error because `VACUUM` cannot run inside a normal transaction block. Afterward, run `VACUUM` separately in autocommit mode.

### Exercise 18 — Checking Trends

Suppose `datfrozenxid` did not move while XID age rose from 100M to 115M over 3 days.

**Question:** What is the approximate rate in XIDs/day? At this rate alone, how long until the 200M threshold?

**Answer:** ~5M/day and ~17 days. This is purely a scenario calculation, not a reliable production forecast when rates or `VACUUM` change.

### Exercise 19 — When Age Drops After VACUUM

Monitoring shows `age(datfrozenxid)` dropped from 190M to 30M after an aggressive vacuum.

**Question:** Did the cluster "undo 160M transactions"?

**Answer:** No; the freeze horizon `datfrozenxid` moved forward, reducing **the distance to the current counter**.

### Exercise 20 — High Alert While Autovacuum Is Running

A database shows `xid_age=240M`, `autovacuum_freeze_max_age=200M`, and `pg_stat_progress_vacuum` shows an aggressive `VACUUM` scanning a large table.

**Question:** Has a wraparound failure occurred yet? What should you monitor next? Should you cancel `VACUUM` to relieve I/O?

### Exercise 21 — Emergency Scenario

The server logs:

~~~text
ERROR: database is not accepting commands that assign
new transaction IDs to avoid wraparound data loss
~~~

**Exercise:** List the sequence for checking prepared transactions, backend horizons, replication slots, regular `VACUUM`, and post-fix verification. Why must `VACUUM FULL` not be used?

### Exercise 22 — XID vs. MXID

Write a query displaying `age(datfrozenxid)` and `mxid_age(datminmxid)` across all databases.

**Question:** If XID age looks normal while MXID age nears its threshold, can the cluster be considered safe?

### Exercise 23 — Estimating Maintenance Duration

A 2 TB unfrozen historical table has an effective `VACUUM` scan throughput of 80 MB/s under current load. Estimate the time **just to read 2 TB** using consistent byte units, then explain why real total `VACUUM` runtime can be either longer or shorter than a full-file read estimate (`all-frozen` pages, I/O contention, indexes, buffers, parallelism).

**Goal:** set alerts not just by XID counts, but also by ability to **finish maintenance in time**.

### Exercise 24 — Interpreting Disabled Autovacuum

A server has `autovacuum=off` and few tables receive `UPDATE`s.

**Question:** Can PostgreSQL still force an anti-wraparound `VACUUM`? Why is turning autovacuum off still discouraged?

### Exercise 25 — Dashboard Code Review

A developer built a dashboard running:

~~~sql
SELECT pg_current_xact_id();
~~~

every second on read-only connections.

**Question:** What side effect can this function cause? Propose a lower-impact monitoring approach distinguishing 32-bit XID from `xid8`.

### Exercise 26 — Direct Cause vs. Symptom

A system exhibits:

~~~text
high age(datfrozenxid)
high n_dead_tup
old last_autovacuum
old replication slot catalog_xmin
old backend_xmin
~~~

**Exercise:** Explain what each signal proves, what it does not prove yet, and the right investigation sequence. Distinguish **symptoms**, **blockers**, and **root causes**.

### Exercise 27 — Writing a Short Ops Runbook

From sections 13–24, draft a one-page runbook covering:

1. Trigger conditions;
2. SQL to check database ages;
3. SQL to find top relations/TOASTs;
4. SQL to inspect `VACUUM` progress;
5. SQL to find old backends/slots/prepared transactions;
6. Who has authority to clear blockers;
7. When to run regular `VACUUM`;
8. How to verify recovery and reconcile business state.

**Important:** never include automated session-kill or slot-drop commands in a runbook without explicit authorization and impact checks.

## 28. Operational Checklist for Preventing Wraparound

1. **Monitor `age(datfrozenxid)` for every database**, not just the primary app database.
2. **Monitor `mxid_age(datminmxid)`** so Multixact exhaustion is never overlooked.
3. Track tables/TOASTs/partitions with the oldest `relfrozenxid`/`relminmxid`.
4. Watch `pg_stat_progress_vacuum`, `pg_stat_all_tables`, and autovacuum logs.
5. Configure early alerts tailored to **actual server config**, XID burn rate, and time required for `VACUUM` to finish.
6. Never disable autovacuum or push thresholds overly high just to reduce I/O.
7. Keep transactions short; eliminate `idle in transaction` leaks.
8. Audit prepared transactions with their two-phase commit coordinators.
9. Manage replication slots with clear owners, retention, and resync plans—never leave forgotten slots indefinitely.
10. Review `hot_standby_feedback` and its cleanup-horizon impact.
11. Ensure system catalogs, static tables, historical partitions, materialized views, and TOAST tables are maintained.
12. Ensure DBA roles running emergency `VACUUM` have privileges covering system catalogs.
13. Provision sufficient disk, I/O, workers, and maintenance windows, watching for DDL/lock contention.
14. Never use `VACUUM FULL` as an XID-exhaustion rescue.
15. Never manually edit `relfrozenxid`/`datfrozenxid`.
16. Never generate billions of transactions or disable safeguards to "test" incidents.
17. Maintain tested runbooks for near-failsafe and XID-refusal emergencies.
18. After every incident, document root cause, preventive fixes, metrics, and alert tests.

## 29. Official PostgreSQL Documentation

Always consult documentation matching **your server's exact major version**; links below point to current docs or corresponding feature sections:

- [Transactions and Identifiers](https://www.postgresql.org/docs/current/transaction-id.html): 32-bit XIDs, `xid8`, epochs, and XID assignment timing.
- [Routine Vacuuming — Preventing Transaction ID Wraparound Failures](https://www.postgresql.org/docs/current/routine-vacuuming.html#VACUUM-FOR-WRAPAROUND): rationale for freezing, XID wraparound, `relfrozenxid`/`datfrozenxid`, safety thresholds, and recovery runbooks.
- [Routine Vacuuming — Multixacts and Wraparound](https://www.postgresql.org/docs/current/routine-vacuuming.html#VACUUM-FOR-MULTIXACT-WRAPAROUND): Multixact IDs, `relminmxid`, and `datminmxid`.
- [Server Configuration — Vacuuming](https://www.postgresql.org/docs/current/runtime-config-vacuum.html): `autovacuum_freeze_max_age`, `vacuum_freeze_min_age`, `vacuum_failsafe_age`, and related settings.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): `FREEZE`, `FULL`, `VERBOSE` options, execution restrictions, and relation handling.
- [System Information Functions](https://www.postgresql.org/docs/current/functions-info.html): `age(xid)`, `mxid_age`, `pg_current_xact_id`, and `pg_current_xact_id_if_assigned`.
- [Progress Reporting — VACUUM](https://www.postgresql.org/docs/current/progress-reporting.html): `pg_stat_progress_vacuum` and `VACUUM` phases.
- [Statistics Collector / pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `backend_xid`, `backend_xmin`, transaction states, and stats views.
- [pg_prepared_xacts](https://www.postgresql.org/docs/current/view-pg-prepared-xacts.html): transactions awaiting two-phase commit completion.
- [pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html): replication slots, `xmin`, `catalog_xmin`, `restart_lsn`.
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html): how snapshots and tuple versions operate.

In particular, late warning thresholds and stats columns can change across releases. Never copy commands or hardcoded numbers from another version while ignoring the docs and logs of your running cluster.

## 30. Summary

**Transaction ID wraparound** stems from PostgreSQL storing traditional MVCC XIDs in a **finite 32-bit space**. The cluster-wide XID counter wraps around after roughly **4.29 billion** IDs, and modulo comparison can only safely order transactions within a window of roughly **2.147 billion**. If an unfrozen row version ages past that safe window, it risks being mistaken for a "future" transaction.

**`VACUUM` freezing** is the core defense: sufficiently old row versions are marked permanently safe so they no longer depend on circular XID comparisons. `pg_class.relfrozenxid` tracks per-relation horizons; `pg_database.datfrozenxid` tracks per-database horizons; `age(xid)` measures distance in **number of transaction IDs**, **never seconds or days**. Because the XID counter is cluster-wide, even idle static databases require maintenance.

PostgreSQL includes multiple automated safety layers: **regular/aggressive `VACUUM`, anti-wraparound autovacuum** at roughly **200 million XIDs by default**, and **failsafe** when age climbs dangerously high. Yet DBAs must still monitor **XID/MXID ages, TOAST/partitions, `VACUUM` progress, long-open transactions, prepared transactions, and replication slots**; old snapshot holders or blocked maintenance can drive a cluster toward severe warnings and eventually **refuse new XIDs to prevent data loss**.

**The single most important operational rule:** never wait for wraparound to handle it. Monitor XID age and burn rate, keep autovacuum enabled, eliminate long transactions, manage slots and prepared transactions, and prioritize **proper `VACUUM` after clearing blockers**. Never edit catalogs manually, never use `VACUUM FULL` to fix wraparound, and never fabricate dangerous wraparound conditions in environments with important data. Proactive prevention keeps PostgreSQL MVCC safe across arbitrarily many Transaction ID wraparound cycles.
