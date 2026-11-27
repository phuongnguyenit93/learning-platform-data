# `default_time_to_live` and Statement-Specified TTL

## 1. Two Ways to Declare Time to Live in Cassandra

In **Apache Cassandra**, a **distributed wide-column** database management system, data is organized by partition key and clustering key to serve known queries. Beyond query-driven table design, you also need to design the **data lifecycle**: sensor events, temporary notifications, or cache records usually do not need to live forever.

Cassandra supports **time to live (TTL)** in two ways:

1. **Table default TTL**: the `default_time_to_live` option set in `CREATE TABLE` or `ALTER TABLE`. If a mutation does not specify its own TTL, the written cells receive the table's default TTL.
2. **Statement-specified TTL**: `USING TTL <seconds>` in `INSERT` or `UPDATE`. The write statement explicitly determines the lifetime of the cells it updates, **taking precedence over** the table's default TTL.

The core point is that **TTL attaches to the written cell version**, not a shared timer across the entire partition. Changing a table's default TTL does not automatically rewrite all existing data. Writing a different column does not automatically extend the TTL of untouched columns either.

For example, a cache table keeps data for **15 minutes** by default, while some notifications only need to live **2 minutes**:

```sql
CREATE TABLE IF NOT EXISTS notification_cache_by_id (
    notification_id uuid PRIMARY KEY,
    account_id uuid,
    payload text,
    priority text
) WITH default_time_to_live = 900;

-- No TTL specified: newly written data cells receive the default 900-second TTL.
INSERT INTO notification_cache_by_id (
    notification_id, account_id, payload, priority
)
VALUES (
    11111111-8888-4888-8888-111111111111,
    22222222-8888-4888-8888-222222222222,
    'Normal notification',
    'NORMAL'
);

-- Explicit TTL specified: newly written data cells receive a 120-second TTL.
INSERT INTO notification_cache_by_id (
    notification_id, account_id, payload, priority
)
VALUES (
    33333333-8888-4888-8888-333333333333,
    22222222-8888-4888-8888-222222222222,
    'High-priority short-lived notification',
    'HIGH'
)
USING TTL 120;
```

The lifetimes of the two records differ **because of the policies of the two writes**, even though both reside in the same table.

## 2. `default_time_to_live`: Table-Level Default TTL

`default_time_to_live` is a table property whose value is a **number of seconds**. Its default value is **`0`**, meaning **no default lifetime is applied**.

```sql
CREATE TABLE IF NOT EXISTS session_data_by_id (
    session_id uuid PRIMARY KEY,
    owner_id uuid,
    session_payload text
) WITH default_time_to_live = 1800;
```

The table above sets a default TTL of **1,800 seconds = 30 minutes**. When an `INSERT` writes `session_payload` **without `USING TTL`**, the new cell version has a lifetime of roughly 30 minutes from the write.

```sql
INSERT INTO session_data_by_id (
    session_id, owner_id, session_payload
)
VALUES (
    44444444-8888-4888-8888-444444444444,
    55555555-8888-4888-8888-555555555555,
    'example-session'
);

SELECT session_payload,
       ttl(session_payload) AS remaining_seconds,
       writetime(session_payload) AS write_micros
FROM session_data_by_id
WHERE session_id = 44444444-8888-4888-8888-444444444444;
```

Right after writing, `remaining_seconds` is typically close to `1800`. `write_micros` is the mutation timestamp used for **last-write-wins (LWW)**, measured in microseconds, **not** the initial TTL and not the remaining lifetime.

**Why is this a default rather than a "table expiration date"?** Because individual mutations create data at different times. Two cells in the same table written an hour apart can expire an hour apart. The table option determines TTL **when new cells are written**, not a single shared expiration date for the whole table.

## 3. Precedence Order Between Default TTL and Statement TTL

To determine the lifetime of a newly written cell, look at **the TTL used by the mutation itself**:

| Table TTL | TTL on `INSERT`/`UPDATE` | New cell's TTL |
|---|---|---|
| `default_time_to_live = 0` | Not specified | **No TTL** |
| `default_time_to_live = 900` | Not specified | **900 seconds** |
| `default_time_to_live = 900` | `USING TTL 120` | **120 seconds** |
| `default_time_to_live = 900` | `USING TTL 3600` | **3,600 seconds** |
| `default_time_to_live = 900` | `USING TTL 0` | **No TTL** for the cells written by that mutation |
| `default_time_to_live = 0` | `USING TTL 120` | **120 seconds** |
| Table currently `1800`, old cell written when default was `900` | No new mutation on the old cell | Old cell **keeps the lifetime of its written version** |

In CQL, **`USING TTL 0` has a special meaning**: it puts the new cell version into a state of **never expiring via TTL**. This is how you override a default TTL for certain records that must persist longer. It **does not retroactively affect** other cells in the row, nor does it make all existing data in the table permanent.

Only use `USING TTL 0` when you genuinely want the new version to have no TTL. Never use negative numbers as TTL, never use `-1` to mean "unlimited," and never assume every system supports arbitrarily huge TTLs: valid limits, expiration-overflow safeguards, and error-reporting behavior depend on the Cassandra version and cluster configuration.

**The TTL selection rule only takes effect if the mutation wins.** If a client attempts to write a cell at a lower timestamp than an existing live version or tombstone, the statement may be acknowledged yet **fail to change** the value/TTL observed by reads.

## 4. CQL Hands-On: Comparing Default, Custom TTL, and TTL 0

These examples use a **test keyspace** selected with `USE <keyspace>;`. If a table with the same name was created earlier with different settings, inspect the schema or create a fresh test table; `CREATE TABLE IF NOT EXISTS` does **not** alter an existing table.

### Step 1 — Table with a 600-Second Default

```sql
CREATE TABLE IF NOT EXISTS ttl_policy_lab_by_id (
    item_id uuid PRIMARY KEY,
    title text,
    state text,
    note text
) WITH default_time_to_live = 600;
```

### Step 2 — Three Rows Using Three TTL Policies

```sql
-- Row A: default 600 seconds.
INSERT INTO ttl_policy_lab_by_id (item_id, title, state)
VALUES (
    aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa,
    'By default',
    'OPEN'
);

-- Row B: custom 90-second TTL.
INSERT INTO ttl_policy_lab_by_id (item_id, title, state)
VALUES (
    bbbbbbbb-8888-4888-8888-bbbbbbbbbbbb,
    'Custom TTL',
    'OPEN'
)
USING TTL 90;

-- Row C: explicit TTL 0; sets no expiration lifetime for the new cells.
INSERT INTO ttl_policy_lab_by_id (item_id, title, state)
VALUES (
    cccccccc-8888-4888-8888-cccccccccccc,
    'No TTL',
    'OPEN'
)
USING TTL 0;
```

### Step 3 — Read the Actual TTL of Each Cell

```sql
SELECT item_id, title, ttl(title) AS title_ttl,
       state, ttl(state) AS state_ttl
FROM ttl_policy_lab_by_id
WHERE item_id IN (
    aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa,
    bbbbbbbb-8888-4888-8888-bbbbbbbbbbbb,
    cccccccc-8888-4888-8888-cccccccccccc
);
```

This CQL query targets a specific set of **partition keys**. Conceptual result right after writing:

| Row | `ttl(title)` | `ttl(state)` | Explanation |
|---|---:|---:|---|
| A | Near `600` | Near `600` | Default TTL applied |
| B | Near `90` | Near `90` | Statement TTL overrides table TTL |
| C | `null` | `null` | `USING TTL 0` creates cells without TTL |

In practice, every `SELECT` takes time, so positive TTL values **count down**; do not assert exact equality to `600` or `90`. If you prefer not to use an `IN` query, read each partition individually with `WHERE item_id = ...`.

### Step 4 — A New Column Can Have a Different TTL from Existing Columns

```sql
-- Write the note column with a short TTL, leaving title and state untouched.
UPDATE ttl_policy_lab_by_id
USING TTL 30
SET note = 'needs urgent handling'
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;

SELECT title, ttl(title),
       state, ttl(state),
       note, ttl(note)
FROM ttl_policy_lab_by_id
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;
```

`title` and `state` keep the remaining TTL from the `INSERT` (originally 600 seconds); `note` has a remaining lifetime near 30 seconds. **Table-level default TTL does not bundle every cell into a single shared timer.**

## 5. `UPDATE` on an Existing Cell: Is the TTL Renewed?

An `UPDATE` rewriting a cell creates a **new version** of that cell. If the mutation wins by timestamp, the cell receives the lifetime of the **new write**:

```sql
-- Row A previously had state with the default 600-second TTL.
UPDATE ttl_policy_lab_by_id
USING TTL 1200
SET state = 'PROCESSING'
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;

SELECT title, ttl(title),
       state, ttl(state),
       writetime(state) AS state_write_us
FROM ttl_policy_lab_by_id
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;
```

If the new write wins, `state` has a TTL near **1,200 seconds** from the `UPDATE`, while `title` continues counting down from the **600 seconds of the `INSERT`**. TTL does not add `1200` to the old version's remaining seconds.

On a table that still has a 600-second default TTL, an update **without** `USING TTL` receives the **default 600-second TTL for the new version**:

```sql
UPDATE ttl_policy_lab_by_id
SET state = 'QUEUED'
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;

SELECT state, ttl(state)
FROM ttl_policy_lab_by_id
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;
```

If the update wins, `state` gets a TTL near 600 seconds. It **does not retain** the previous version's 1,200-second TTL, because the new cell's TTL is determined by the mutation just executed.

### Converting a Cell to No TTL

```sql
UPDATE ttl_policy_lab_by_id
USING TTL 0
SET state = 'ARCHIVED'
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;

SELECT state, ttl(state), title, ttl(title)
FROM ttl_policy_lab_by_id
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;
```

Expected result if the mutation wins: `state = 'ARCHIVED'`, `ttl(state) = null`; `title` continues with its own remaining TTL. To set TTL 0 on **a new version**, you still have to **rewrite the cell's value**; there is no operation that strips TTL from all existing cells in a table merely by editing the default table option.

**Timing note:** TTL starts counting when Cassandra processes the written mutation, not from a `created_at` column or a past `USING TIMESTAMP` supplied by the application. Server clocks and expiration processing affect the actual instant; never design legal or sub-second strict deadlines based solely on `ttl()`.

## 6. `ALTER TABLE` Changing the Default TTL: When Does It Take Effect?

You can change the default policy **without** creating another table:

```sql
ALTER TABLE ttl_policy_lab_by_id
WITH default_time_to_live = 1800;
```

Once the schema change takes effect, mutations **without `USING TTL`** use the new default of **1,800 seconds**. However, Cassandra **does not walk through all SSTables to rewrite the TTL of already-existing cells**.

Example:

```sql
-- Row D is written after changing default TTL to 1800.
INSERT INTO ttl_policy_lab_by_id (item_id, title, state)
VALUES (
    dddddddd-8888-4888-8888-dddddddddddd,
    'After ALTER',
    'OPEN'
);

SELECT title, ttl(title), state, ttl(state)
FROM ttl_policy_lab_by_id
WHERE item_id = dddddddd-8888-4888-8888-dddddddddddd;
```

`ttl(title)` and `ttl(state)` in row D are roughly `1800`. Cells in rows A/B/C **do not automatically adopt** the 1,800-second TTL simply because the table configuration changed. Only when an old cell is **updated again without specifying a TTL** can that cell receive the **current** default TTL.

| Operation | Existing cells in the table | New cells written after the operation |
|---|---|---|
| Change default from `600` to `1800` | Keep the TTL attached to their prior version | If no `USING TTL`: 1800 seconds |
| Change default from `1800` to `0` | Existing TTLs do not vanish automatically | If no `USING TTL`: no TTL |
| Write `USING TTL 45` after changing default | Untouched columns are unaffected | Written column: 45 seconds |

When rolling out schema changes across nodes, wait for schema agreement and ensure clients have refreshed metadata before testing. In production, changing the default TTL is a **forward-looking storage policy** change: forecast incoming data volume, tombstone retention, and compaction/repair schedules.

## 7. `USING TTL 0`, `null`, and Common Misconceptions

These three expressions have different meanings:

- **`USING TTL 0`:** requests that the written cell versions have **no TTL**.
- **`ttl(col) = null`:** the query function returns no remaining lifetime. If `col` still has a value, the cell currently has **no TTL**; if `col` has no value, it may be unwritten, deleted, or expired.
- **`default_time_to_live = 0`:** the table has no **default** lifetime; individual write statements can still use `USING TTL 120`.

Specifically, `USING TTL 0` **does not delete a value**. It creates a non-expiring data version when written successfully. Deleting a cell is a separate operation:

```sql
DELETE state FROM ttl_policy_lab_by_id
WHERE item_id = cccccccc-8888-4888-8888-cccccccccccc;
```

`DELETE` creates a tombstone (deletion marker) to shadow older versions. If you need conditional checks before deleting or changing state, consider **lightweight transactions (LWT)** and verify the `[applied]` result; TTL does not replace business preconditions.

A cell with a TTL can be overwritten by a mutation whose write timestamp is **lower** than the currently winning version. In that case, the new record may not appear even though `UPDATE` returned success; `ttl()` still displays the metadata of the **currently winning version**, not the TTL of the request just sent. This is a direct interaction within the **Timestamps and TTL** chapter.

## 8. TTL by Cell, Row, and Primary Key

For example, row A has these cells:

```text
Partition: item_id = A
|
+-- title = "By default"            | TTL from initial INSERT
+-- state = "ARCHIVED"              | TTL = none (USING TTL 0)
+-- note = "needs urgent handling"  | 30-second TTL from separate UPDATE
```

Having `note` expire first does not force `title` and `state` to disappear. A row can continue returning **partial data**, because TTL is metadata on live cells. Once **all live data** expires and no matching live row marker remains, the row can disappear from query results.

Primary keys consist of partition keys and clustering keys and serve to address data locations. Do not query `ttl(primary_key_column)` or `writetime(primary_key_column)` as you would regular columns.

For collections with multiple elements or mutations deleting entire rows/partitions, cell and tombstone scopes are more complex than in these scalar examples. In real systems, avoid assuming every Cassandra structure shares a single row-wide timestamp/TTL.

## 9. Java Driver: Setting a Custom TTL or Using the Default TTL

Java applications can use **Apache/DataStax Cassandra Java Driver 4.x** to explicitly choose TTL per request. A prepared statement with `USING TTL ?` takes an integer parameter in **seconds**, not `Duration.toMillis()` or epoch microseconds.

```java
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class NotificationCacheRepository {
    private final CqlSession session;
    private final PreparedStatement insertDefault;
    private final PreparedStatement insertWithTtl;
    private final PreparedStatement updateWithTtl;
    private final PreparedStatement selectRemaining;

    public NotificationCacheRepository(CqlSession session) {
        this.session = session;

        this.insertDefault = session.prepare(
            "INSERT INTO notification_cache_by_id " +
            "(notification_id, account_id, payload, priority) " +
            "VALUES (?, ?, ?, ?)"
        );
        this.insertWithTtl = session.prepare(
            "INSERT INTO notification_cache_by_id " +
            "(notification_id, account_id, payload, priority) " +
            "VALUES (?, ?, ?, ?) USING TTL ?"
        );
        this.updateWithTtl = session.prepare(
            "UPDATE notification_cache_by_id USING TTL ? " +
            "SET payload = ? WHERE notification_id = ?"
        );
        this.selectRemaining = session.prepare(
            "SELECT payload, ttl(payload) AS payload_ttl_s " +
            "FROM notification_cache_by_id WHERE notification_id = ?"
        );
    }

    // Uses the table's default_time_to_live (e.g., 900 seconds).
    public void saveDefault(UUID notificationId, UUID accountId,
                            String payload, String priority) {
        session.execute(insertDefault.bind(
            notificationId, accountId, payload, priority
        ));
    }

    // Custom TTL; 0 means the new version has no TTL.
    public void saveWithTtl(UUID notificationId, UUID accountId,
                            String payload, String priority, int ttlSeconds) {
        if (ttlSeconds < 0) {
            throw new IllegalArgumentException("TTL must be nonnegative");
        }
        session.execute(insertWithTtl.bind(
            notificationId, accountId, payload, priority, ttlSeconds
        ));
    }

    // Updates payload only; other cells keep their own metadata.
    public void replacePayload(UUID notificationId, String payload,
                               int ttlSeconds) {
        if (ttlSeconds < 0) {
            throw new IllegalArgumentException("TTL must be nonnegative");
        }
        session.execute(updateWithTtl.bind(ttlSeconds, payload, notificationId));
    }

    public Integer getRemainingSeconds(UUID notificationId) {
        Row row = session.execute(selectRemaining.bind(notificationId)).one();
        if (row == null || row.isNull("payload_ttl_s")) {
            return null;
        }
        return row.getInt("payload_ttl_s");
    }
}
```

Key points to control:

- Call `saveDefault(...)` when you want **the table's TTL policy**; this path omits `USING TTL`.
- Call `saveWithTtl(..., 120)` when you want **120 seconds** for the `INSERT`ed cells.
- Call `saveWithTtl(..., 0)` when you want the new cells to have **no TTL** where business logic permits.
- `replacePayload(...)` changes only `payload`. `account_id` and `priority` are not rewritten, so their TTLs are not automatically extended.
- `getRemainingSeconds(...) == null` can mean **no TTL or no live cell**. To distinguish them, query the value itself and check business state.

If you configure durations using `Duration`, convert to **seconds with validation**, avoiding rounding a sub-second duration down to `0` and accidentally making the cell non-expiring. Also respect the TTL limits of your running Cassandra version; validate the seconds value before sending.

## 10. TTL, Mutation Timestamps, and Distributed Clocks

TTL is determined at the write time of the new cell version, whereas **mutation timestamp** is **microsecond**-resolution metadata used to choose a version when two writers touch the same cell. Meanwhile, a CQL `timestamp` column represents a business instant at **millisecond** resolution.

Example importing historical data while wanting to cache the result for 2 minutes:

```sql
INSERT INTO ttl_policy_lab_by_id (item_id, title)
VALUES (
    eeeeeeee-8888-4888-8888-eeeeeeeeeeee,
    'Imported event'
)
USING TIMESTAMP 1700000000000000 AND TTL 120;

SELECT title, writetime(title), ttl(title)
FROM ttl_policy_lab_by_id
WHERE item_id = eeeeeeee-8888-4888-8888-eeeeeeeeeeee;
```

If no competing version exists, `writetime(title)` is `1700000000000000` (a past point in time), while `ttl(title)` is **near 120 seconds** right after import. TTL is **not** counted from the past write timestamp. Importing old data and selecting a TTL are two independent decisions.

In a cluster with **RF = 3**, replicas may not receive the same mutation simultaneously, depending on the **consistency level (CL)**. `ONE`, `QUORUM`, and `ALL` govern read/write response requirements; they **do not change** the table default TTL or statement-specified TTL. A record with a future timestamp can still cause a new mutation with a valid TTL but lower timestamp to **lose under LWW**.

Server-side clocks affect expiration timing; synchronize clocks across Cassandra nodes. If the driver/client generates mutation timestamps, monitor application host clocks as well to reduce conflicts. Altering `USING TIMESTAMP` to "extend TTL" is a misuse and can introduce future timestamps that shadow valid subsequent writes.

## 11. TTL Expiration, Tombstones, Compaction, and Repair

When TTL expires, Cassandra considers the cell expired data and treats it similarly to a **tombstone** to prevent a replica holding stale data from resurrecting it. TTL makes the value **no longer live for reads**, but does not guarantee bytes are immediately purged from every SSTable.

```text
Write mutation                        TTL expires                      Physical cleanup
     |                                    |                                 |
     v                                    v                                 v
Live cell version  --TTL counts-->  Cell becomes invalid  --safe compaction--> Removed
                                          |
                                Tombstone/metadata
                              guards against stale data
```

Cassandra uses **compaction** to merge/clean SSTables when conditions permit; **repair** converges replicas. A table with a low default TTL and high write throughput can generate massive amounts of expired data and tombstone pressure, impacting read latency, disk usage, and compaction work.

Therefore, before enabling a default TTL on a large table, evaluate:

1. **Query and partition characteristics:** how many cells per partition, write/read rates, and whether reads frequently scan across expired data?
2. **Compaction strategy:** time-series tables may consider `TimeWindowCompactionStrategy` when aligned with write patterns and lifetimes; do not apply it blindly to every table.
3. **Repair and tombstones:** never lower `gc_grace_seconds` arbitrarily just to reclaim space faster; if a replica still holds old data, unsafe tombstone purging can cause **zombie data**.
4. **Actual retention:** TTL does not guarantee immediate physical erasure from disk, snapshots, backups, or copies outside Cassandra.

Once a cell expires, `ttl(cell)` does not return negative numbers in normal `SELECT` queries; when no live value remains, the result may be `null` or the row may disappear. `writetime(cell)` also does not directly read the timestamp of the resulting tombstone.

## 12. Retries, Concurrent Writes, and Operational Policy Changes

Three common failure scenarios:

**Retries unintentionally extending TTL.** A cache write with a 300-second TTL times out, and the client retries 2 minutes later as a new write. If the retry becomes the winning version, the lifetime may be reset from the later write, keeping the cache entry alive longer than intended. For business requirements with absolute deadlines, store an explicit `expires_at` and define clear retry/idempotency policies.

**Changing default TTL and expecting old cells to update.** An operator runs `ALTER TABLE ... WITH default_time_to_live = 60` to shrink storage. Cells written the previous day still retain their old TTL—or no TTL—until they expire or are rewritten. Plan a separate migration for existing data if lifecycle requirements change.

**Two writers using different TTLs on the same cell.** Service A writes `state = 'READY' USING TTL 120`; Service B writes `state = 'DONE' USING TTL 0`. Cassandra compares **write timestamps** to select the winning version. The TTL returned by `ttl(state)` belongs to **the winning version**, not "pick the larger TTL" or "prefer having a TTL."

A clear way to separate intentions at the application layer:

| Intent | Policy |
|---|---|
| All new notifications expire after 15 minutes by default | `default_time_to_live = 900` |
| One specific notification should only live 2 minutes | `INSERT ... USING TTL 120` |
| One record needs long-term retention in the same table | `INSERT/UPDATE ... USING TTL 0` with controlled policy |
| Existing cell must switch to a new TTL | **Rewrite the cell** with the desired TTL, ensuring the mutation wins LWW |
| Customers need a strict, business-exact expiration deadline | Store `expires_at` and enforce in business logic; use TTL for storage cleanup |

## 13. Diagnosing Unexpected TTL Behavior

A query targeting the exact partition key:

```sql
SELECT item_id, title, writetime(title), ttl(title),
       state, writetime(state), ttl(state),
       note, writetime(note), ttl(note)
FROM ttl_policy_lab_by_id
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;
```

Interpret results alongside schema and mutation history:

| Symptom | What to check |
|---|---|
| No `USING TTL` declared, yet `ttl(title)` is positive | Table has `default_time_to_live > 0` |
| Declared `USING TTL 120`, yet read shows near `900` | Are you reading the right cell/key? Did another mutation win? Was there a rewrite without TTL that picked up default 900? |
| After `ALTER TABLE`, old cells still carry old TTL | `ALTER` does not modify already-written cell metadata |
| `ttl(state) = null`, yet `state` still has a value | Cell currently has **no TTL**, possibly via `USING TTL 0` |
| `ttl(state) = null` and `state = null` | No live cell; check TTL expiration, deletes, key, and replicas |
| `UPDATE` reported success, yet TTL did not change | Check `writetime(state)`, new mutation's timestamp, tombstones, and LWW |
| Newly assigned TTL already dropped by a few seconds | `ttl()` reports **remaining seconds** at read time; expect latency and second-level rounding |
| Expiration state varies across reads | Check CL, replica health, clock skew, repair, and concurrent writes |

Do not run full-table scans or `ALLOW FILTERING` on large datasets just to hunt for low-TTL cells. With Cassandra, **design queries around partition keys** or use appropriate monitoring/business metadata systems. When periodic bulk expiration at scale is needed, consider time-bucketed tables and matching compaction policies.

## 14. Self-Check Questions

**Question 1.** A table has `default_time_to_live = 600`. An `INSERT` without `USING TTL` writes `state`. What is the TTL of the new version?

**Answer:** Roughly **600 seconds** from the write. `ttl(state)` immediately afterward is near 600 and counts down.

**Question 2.** On the same table, an `INSERT ... USING TTL 90` writes `state`. Is 600 or 90 seconds applied?

**Answer:** **90 seconds**, because the TTL specified in the statement takes precedence over the table's default TTL.

**Question 3.** What does `INSERT ... USING TTL 0` mean on a table with a default TTL of 600?

**Answer:** The newly written data cell versions have **no TTL**. Existing cells that were not updated retain their own metadata.

**Question 4.** Does changing `default_time_to_live` from 600 to 1800 extend all existing cells by another 20 minutes?

**Answer:** **No**. The new option applies to **subsequent mutations** that omit an explicit TTL; existing cells keep their previously attached lifetimes.

**Question 5.** `state` has a 120-second TTL, and then `UPDATE ... SET note = ...` runs (without touching `state`). Does `state` reset to 120 seconds?

**Answer:** **No**. Only the updated cells receive that mutation's TTL.

**Question 6.** `state` is updated with `USING TTL 30`, but the mutation's timestamp is lower than the currently winning version. Will `ttl(state)` necessarily change to near 30?

**Answer:** **No**. If the mutation loses LWW, the cell retains the winning version's value and TTL.

**Question 7.** An import today uses `USING TIMESTAMP` from 2023 and `USING TTL 120`. Does the cell expire immediately because of the 2023 timestamp?

**Answer:** **No**. The mutation timestamp governs LWW ordering; TTL counts from the current effective write if the mutation wins.

**Question 8.** A table with a default TTL creates many tombstones. Should you always lower `gc_grace_seconds` to shrink disk usage immediately?

**Answer:** **No**. Evaluate replication, repair schedules, compaction, and **zombie data** risk. TTL does not guarantee immediate physical erasure.

---

**Key takeaway:** `default_time_to_live` defines the **default TTL for newly written cells**; `USING TTL N` on `INSERT`/`UPDATE` **overrides the default policy** for the cells touched by the mutation, where `USING TTL 0` means **no TTL**. TTL attaches to the **winning cell version** and counts in seconds from the write; changing the default TTL does not rewrite existing data. Always inspect `ttl()` together with `writetime()`, and account for replication, compaction, tombstones, and repair when applying TTL policies at scale.
