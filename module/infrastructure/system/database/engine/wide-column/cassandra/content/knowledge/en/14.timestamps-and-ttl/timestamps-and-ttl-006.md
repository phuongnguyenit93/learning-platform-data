# WRITETIME, TTL, and Observing Value Metadata in Apache Cassandra

## 1. Why Observe a Value's Metadata?

In **Apache Cassandra**, a **distributed wide-column** database, an application typically reads a value with `SELECT`, yet that value only reflects the **currently visible version**. Two records with identical contents can still carry different metadata, specifically:

- **Write timestamp** (mutation timestamp): the timestamp Cassandra uses to reconcile versions of the same cell under the **last-write-wins** mechanism.
- **Time to live (TTL)**: the remaining lifetime of a cell configured to expire automatically.

CQL provides two essential observation functions:

```sql
SELECT writetime(state), ttl(state)
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

These two functions help answer very practical questions: "Why didn't the new write win?", "How many seconds does this cell have left before expiring?", "Does this column have a TTL?", and "Were two columns in the same row written at different times?".

**Limitations:** `writetime()` and `ttl()` report metadata for the **value currently active in the read result**. They **do not provide edit history**, do not list losing versions, do not reveal shadowed tombstones, and do not replace replica/SSTable inspection tools during deep investigations.

## 2. Distinguishing Write Timestamp, CQL `timestamp`, and TTL

Although all relate to time, these three concepts serve three distinct roles:

| Concept | Unit | Value source | Purpose |
|---|---|---|---|
| Mutation timestamp | **Microseconds** (µs) since Unix epoch | `USING TIMESTAMP`, client/driver, or coordinator | Arbitrates cell versions under LWW |
| CQL `timestamp` column | **Milliseconds** (ms) since Unix epoch | Business value `INSERT`ed/`UPDATE`d | Stores the timestamp of an event or business action |
| Declared TTL (`USING TTL`) | **Seconds** | Write CQL or table `default_time_to_live` | Sets how long the cell is kept alive |
| `ttl(column)` | **Remaining seconds** | Computed by Cassandra from cell expiration metadata | Observes remaining lifetime at read time |

For example, a sensor emits an event at `2026-11-21T01:20:30.123Z` into an `event_at timestamp` column. Cassandra may write this cell with mutation timestamp `1795224030123456`, while the application attaches a TTL of `3600` seconds. The business timestamp, version order, and lifetime are all separate pieces of information.

For the same `event_at` value:

```text
event_at                       -> event time (timestamp type, ms)
writetime(event_at)            -> cell metadata write time (epoch µs)
ttl(event_at)                  -> remaining seconds alive if TTL is set
```

Never conclude that `writetime(event_at)` equals the value of `event_at` itself. Cassandra **does not automatically use a business time column as the write timestamp**, unless the application explicitly uses that value to supply the mutation timestamp.

## 3. The `WRITETIME(column)` Function

`writetime(column)` returns the **write timestamp of the currently live cell**, as a 64-bit integer in **microseconds since the Unix epoch**.

```sql
SELECT state,
       writetime(state) AS state_write_us
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

If it returns:

```text
 state  | state_write_us
--------+------------------
 online | 1795224030123456
```

then `state_write_us` is the metadata used to compare versions of `state`. That number **does not by itself prove** the request ran at that exact wall-clock instant: the timestamp could have been set manually by the client, the clock source could be skewed, or a driver could have generated monotonically increasing timestamps.

### Key Points to Remember

1. **Applies per cell:** two columns in the same row can have different `writetime()` values because they were updated in different mutations.
2. **Not a sort key:** Cassandra does not allow arbitrary `ORDER BY writetime(state)`; to read data in chronological order, design an appropriate **clustering key**.
3. **Not a history log:** when a newer version wins, `writetime()` does not return the timestamps of previously losing versions.
4. **Cannot be used on primary keys:** partition keys and clustering keys identify data location and cannot be queried with `writetime()` like regular data columns.
5. **Does not apply to counters:** counters use a separate write mechanism. For collections or complex types, whether write timestamps can be retrieved and what they mean per element depends on storage structure; verify against the column type and Cassandra version before relying on it.
6. **Can return `null`:** when a cell has no live value to observe—for instance, the column was never written or has expired—CQL does not return a write timestamp for a live value.

Because the unit is microseconds, never take a raw `writetime()` number and pass it into an API expecting **epoch milliseconds** without converting units.

## 4. The `TTL(column)` Function

`ttl(column)` returns the **number of seconds remaining** before a cell with a TTL expires. This is a decreasing countdown, not an absolute timestamp and not the initial TTL value.

```sql
SELECT state,
       ttl(state) AS state_remaining_s
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

Interpreting the output:

| Result of `ttl(state)` | Interpretation |
|---|---|
| Positive integer, e.g. `113` | Cell has a TTL and has roughly 113 seconds remaining at the time Cassandra reads it |
| `null`, while `state` still has a value | Cell currently has no expiration TTL (no TTL set or TTL was cleared) |
| `null`, while `state = null` | No live cell to observe: may never have been written, was deleted, or TTL expired |

Note: **`ttl(state) = null` is not enough to conclude that the cell was deleted**. You must read `state` as well and check the TTL configuration. In addition, TTL is stored and calculated at second granularity, so the observed value can be slightly lower than the declared seconds due to request latency and execution time.

### TTL Does Not Automatically Restore Old Versions

When a mutation writes a new value with a TTL, that value expires according to Cassandra's expiration mechanism. Never infer that once the new value expires, the prior value will automatically reappear. Cassandra handles expiration with metadata/tombstones to prevent replicas holding older copies from resurrecting expired data.

## 5. CQL Hands-On: Observing a Write Without TTL

The examples in this lesson run in a **test keyspace** you created and selected with `USE <keyspace>;`. If you already used these test keys in an earlier run, switch to fresh keys so leftover tombstones or timestamps do not affect the output.

Create a table supporting lookups by `device_id`:

```sql
CREATE TABLE IF NOT EXISTS device_latest_by_id (
    device_id text PRIMARY KEY,
    state text,
    description text,
    event_at timestamp
);
```

Write state and event time:

```sql
INSERT INTO device_latest_by_id (
    device_id, state, description, event_at
)
VALUES (
    'sensor-01',
    'online',
    'device reporting normally',
    '2026-11-21T01:20:30.123Z'
);

SELECT device_id,
       state,
       writetime(state) AS state_write_us,
       ttl(state) AS state_remaining_s,
       description,
       writetime(description) AS description_write_us,
       ttl(description) AS description_remaining_s,
       event_at,
       writetime(event_at) AS event_at_write_us
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

Expected result regarding **relationships between fields**:

- `state` and `description` both have values; `writetime(...)` for each cell returns a microsecond integer.
- This `INSERT` specifies no TTL; if the table also has no `default_time_to_live`, then `ttl(state)` and `ttl(description)` are **`null`**.
- `event_at` displays the business timestamp at millisecond resolution; `writetime(event_at)` is the cell's write metadata and may differ from `event_at`.
- Columns written in the same normal mutation typically share the same write timestamp; a subsequent update can cause timestamps across columns to diverge.

Because the write omits `USING TIMESTAMP`, the actual `writetime()` value depends on the timestamp source supplied by the driver or coordinator. **Do not hardcode the numeric output** as part of this test.

## 6. Observing TTL Counting Down Over Time

Update only the `state` column, setting a 120-second TTL:

```sql
UPDATE device_latest_by_id
USING TTL 120
SET state = 'alert'
WHERE device_id = 'sensor-01';

SELECT state,
       writetime(state) AS state_write_us,
       ttl(state) AS state_remaining_s,
       description,
       ttl(description) AS description_remaining_s
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

Right after updating, the output typically looks like:

```text
state = alert
state_write_us = <epoch microseconds of the UPDATE>
state_remaining_s = <a positive integer near 120>
description = device reporting normally
description_remaining_s = null
```

If you run the same `SELECT` again after about 30 seconds, `state_remaining_s` will be roughly 90 seconds. Once the TTL expires, `state` is no longer a live queryable value; `description` can still exist because the TTL was attached to the **updated cell**, not automatically applied to every column in the row.

### Note for Manual Testing

Do not take the returned TTL number and assert exact equality to 120, 90, or 0 in automated tests. There is execution latency and whole-second rounding; check a reasonable range instead, such as `0 < ttl(state) <= 120` right after writing while the cell is still alive.

This example also shows that a single row can simultaneously hold:

| Column | Value | Current TTL | Write timestamp |
|---|---|---|---|
| `state` | `alert` | Yes, counting down from 120 seconds | Timestamp of the `UPDATE` statement |
| `description` | `device reporting normally` | No | Timestamp of the `INSERT` statement |
| `event_at` | Business timestamp | No | Timestamp of the `INSERT` statement |

That is why when diagnosing a row you must read `writetime()` and `ttl()` **for each column you want to inspect**.

## 7. How Does Re-updating a Cell Affect Metadata?

### 7.1. Rewriting the Same Cell with a New TTL

On a separate test key, create a value with a short TTL and rewrite it before expiration:

```sql
INSERT INTO device_latest_by_id (device_id, state)
VALUES ('sensor-renew', 'temporary')
USING TTL 60;

SELECT state, writetime(state), ttl(state)
FROM device_latest_by_id
WHERE device_id = 'sensor-renew';

UPDATE device_latest_by_id
USING TTL 300
SET state = 'renewed'
WHERE device_id = 'sensor-renew';

SELECT state, writetime(state), ttl(state)
FROM device_latest_by_id
WHERE device_id = 'sensor-renew';
```

If the new mutation wins LWW, `state = 'renewed'` gets a **new write timestamp** and `ttl(state)` is near **300 seconds**. The new TTL is not added onto the remaining 60 seconds; it is the lifetime of the **newly written cell version**.

### 7.2. Rewriting the Same Cell Without Specifying a TTL

For a table **without `default_time_to_live`**, updating the same column without `USING TTL` creates a new version **with no TTL**:

```sql
UPDATE device_latest_by_id
SET state = 'persistent'
WHERE device_id = 'sensor-renew';

SELECT state, writetime(state), ttl(state)
FROM device_latest_by_id
WHERE device_id = 'sensor-renew';
```

If this write has a larger write timestamp than the old one, the result is `state = 'persistent'` and `ttl(state) = null`. Do not think an initial TTL "sticks permanently" to the column. It is metadata belonging to the currently live cell version.

**Exception to remember:** if the table is configured with `default_time_to_live > 0`, a statement that omits `USING TTL` can still receive the **table's default TTL**. Always examine both the CQL and table schema when interpreting `ttl()`.

### 7.3. Updating Another Column

```sql
UPDATE device_latest_by_id
SET description = 'checked by operator'
WHERE device_id = 'sensor-renew';

SELECT state, writetime(state), ttl(state),
       description, writetime(description), ttl(description)
FROM device_latest_by_id
WHERE device_id = 'sensor-renew';
```

Writing `description` does not automatically alter the timestamp or TTL of the `state` cell. Cassandra manages metadata per cell, so **two columns in the same row do not necessarily share the same lifecycle**.

## 8. Table-Level Default TTL

In addition to `USING TTL` on write statements, Cassandra supports the table option **`default_time_to_live`**, measured in seconds. It fits data with a uniform lifecycle, such as session state or cache records.

```sql
CREATE TABLE IF NOT EXISTS session_cache_by_id (
    session_id uuid PRIMARY KEY,
    account_id uuid,
    payload text
) WITH default_time_to_live = 900;

INSERT INTO session_cache_by_id (session_id, account_id, payload)
VALUES (
    77777777-7777-4777-8777-777777777777,
    88888888-8888-4888-8888-888888888888,
    'short-lived session'
);

SELECT payload, writetime(payload), ttl(payload)
FROM session_cache_by_id
WHERE session_id = 77777777-7777-4777-8777-777777777777;
```

`ttl(payload)` is near 900 seconds immediately after writing even though the `INSERT` has **no** `USING TTL`, because the table defines a default TTL. A statement like `INSERT ... USING TTL 300` can set a custom TTL for the affected cells, overriding the default lifetime per CQL semantics.

A default TTL is a **data modeling and lifecycle** decision; it is separate from replication factor or consistency level. For tables using TTL heavily, plan for tombstones, compaction, repair, and queries hitting expired data.

## 9. Deleting Cells, Tombstones, and Observation Limits

Deleting a value is different from replacing it with an empty string or the string `'null'`:

```sql
INSERT INTO device_latest_by_id (device_id, state, description)
VALUES ('sensor-delete', 'offline', 'maintenance');

DELETE state FROM device_latest_by_id
WHERE device_id = 'sensor-delete';

SELECT state, writetime(state), ttl(state), description
FROM device_latest_by_id
WHERE device_id = 'sensor-delete';
```

In the row above, `state` no longer has a live value; `description` remains `'maintenance'`. The outputs of `writetime(state)` and `ttl(state)` do not reveal the timestamp of the tombstone that was just created.

A **tombstone** stores the information required to prevent stale data on other replicas from reappearing. If a client rewrites a value with a timestamp **lower** than the tombstone, Cassandra still prioritizes the tombstone. When you need to examine tombstone timestamps or older versions, use internal/SSTable inspection tools and operation logs appropriate for your Cassandra version.

With TTL, once a cell expires, it is handled like deleted data. Therefore:

- `ttl(state)` **does not** continue returning negative numbers in regular `SELECT` queries.
- Never treat `null` as sole proof to distinguish **never written**, **deleted**, **expired**, and **no longer live due to reconciliation**.
- Never use `writetime()` and `ttl()` as substitutes for business event history or audit logs.

Tombstones are purged according to compaction policies and replication/repair safety. Purging under unsafe conditions can cause **zombie data** (old data reappearing). Operate repair and configure tombstone retention appropriately rather than trying to use TTL to "wipe data instantaneously."

## 10. `WRITETIME` and `TTL` in a Distributed System

A partition can have multiple replicas, e.g. `RF = 3`. When a client writes at consistency level `ONE`, other replicas may not receive the same version immediately. On read, Cassandra reconciles data versions from the participating replicas; write timestamps play a central role in deciding the visible version.

| Aspect | Role |
|---|---|
| **Write timestamp** | Chooses the winning cell version during conflicts |
| **TTL/expiration metadata** | Specifies when a value ceases to be live and is treated as expired data |
| **Replication factor** | Specifies how many replicas hold a partition |
| **Read/write consistency level** | Specifies how many replicas must participate/acknowledge to satisfy a request |
| **Repair/compaction** | Converges replicas and cleans up data/tombstones under safety rules |

`writetime()` in a `SELECT` reflects **the value observed by that read request**, not that every replica across the cluster is instantaneously in sync. Read consistency level, replica status, write timeouts, and repair all influence the data observed at query time.

If a new `UPDATE` reports success yet reads still return the old version, besides out-of-sync replicas, inspect **write timestamps**. A client with a fast clock or an explicit future `USING TIMESTAMP` can cause valid later mutations to lose under LWW. Raising consistency to `QUORUM` or `ALL` will not make a smaller timestamp win.

TTL also interacts with clocks and expiration times: clock skew can cause expiration to be observed differently from expectations. However, **mutation timestamp** and **expiration time** are two separate pieces of metadata; never assume changing `USING TIMESTAMP` automatically stretches or shrinks TTL by the exact offset between timestamps.

## 11. Reading Metadata from the Java Driver

In a Java application, use **Apache/DataStax Cassandra Java Driver 4.x** to read both the value and metadata of a regular cell. Prepared statements let you execute repeated lookups by partition key:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class DeviceMetadataReader {
    private final CqlSession session;
    private final PreparedStatement statement;

    public DeviceMetadataReader(CqlSession session) {
        this.session = session;
        this.statement = session.prepare(
            "SELECT state, " +
            "writetime(state) AS state_write_us, " +
            "ttl(state) AS state_ttl_s " +
            "FROM device_latest_by_id WHERE device_id = ?"
        );
    }

    public void inspect(String deviceId) {
        Row row = session.execute(statement.bind(deviceId)).one();
        if (row == null) {
            System.out.println("Device row not found or no live columns");
            return;
        }

        String state = row.getString("state"); // Can be null.
        Long writtenAtMicros = row.isNull("state_write_us")
            ? null : row.getLong("state_write_us");
        Integer remainingSeconds = row.isNull("state_ttl_s")
            ? null : row.getInt("state_ttl_s");

        System.out.printf("state=%s, writeUs=%s, ttlSeconds=%s%n",
            state, writtenAtMicros, remainingSeconds);
    }
}
```

**Never blindly call `getLong()` or `getInt()` on nullable metadata**. In Java, primitive `long`/`int` cannot represent `null`, whereas `Long`/`Integer` preserve the "no metadata returned" state.

### Converting `writetime()` to `Instant`

If you need to display a write timestamp in logs or monitoring, you can convert epoch microseconds to a Java `Instant` without losing the microsecond fraction:

```java
import java.time.Instant;

public static Instant fromEpochMicros(long micros) {
    long seconds = Math.floorDiv(micros, 1_000_000L);
    long remainingMicros = Math.floorMod(micros, 1_000_000L);
    return Instant.ofEpochSecond(seconds, remainingMicros * 1_000L);
}
```

`Math.floorDiv` and `Math.floorMod` handle pre-Unix-epoch timestamps properly too. Never call `Instant.ofEpochMilli(micros)`: that mistakes **microseconds** for **milliseconds**, producing a wildly wrong point in time.

If you want to estimate the expected expiration instant, you can combine the **read** timestamp and the remaining `ttl(column)`. This is **only an approximation** because TTL is tracked in whole seconds, requests incur latency, and expiration metadata can be evaluated against node clocks; do not treat that sum as a microsecond-accurate deadline.

## 12. Separating Write Time from Event Time in Table Design

A common requirement is: "Read the latest 100 measurements of a device ordered by occurrence time." **Do not** design this by reading all rows and doing `ORDER BY writetime(value)`. Cassandra orders within a partition by the **clustering key**, and `writetime()` is cell metadata, not a substitute query key.

Query-driven design example:

```sql
CREATE TABLE IF NOT EXISTS readings_by_device_day (
    device_id text,
    reading_day date,
    event_time timeuuid,
    temperature double,
    PRIMARY KEY ((device_id, reading_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

SELECT event_time, temperature,
       writetime(temperature), ttl(temperature)
FROM readings_by_device_day
WHERE device_id = 'sensor-01'
  AND reading_day = '2026-11-21'
LIMIT 100;
```

Here `event_time` is the **clustering key** ordering the records; `writetime(temperature)` merely observes metadata of the temperature cell. If event times need a different precision or strict cross-source ordering, design separate keys and time sources (such as epoch microseconds + event ID, or a sequence from a trusted source).

**Daily time bucketing** bounds the number of rows per partition for data streams with matching traffic; for devices emitting very high sample rates per day, smaller buckets may be necessary. This belongs to query-driven table design, distinct from metadata inspection.

## 13. Quick Diagnostics with `WRITETIME` and `TTL`

When read data differs from expectations, follow this checklist:

| Symptom | Query/check | Potential causes to examine |
|---|---|---|
| Cell suddenly disappears | `SELECT value, ttl(value), writetime(value)` | TTL expired, `DELETE`, `null` write, wrong key, or out-of-sync replica |
| `ttl(value)` is `null`, yet value exists | Cross-check `USING TTL` and `default_time_to_live` | Cell has no TTL on the winning version |
| `ttl(value)` is lower than the TTL just set | Measure elapsed time between write and read | TTL is **remaining seconds**, not initial TTL |
| Update succeeded yet old value still wins | Inspect `writetime(value)` and timestamps in client logs | New mutation had a smaller timestamp or was shadowed by a tombstone |
| Two columns in one row have different `writetime`s | Check single-column `UPDATE` statements | Two cells were written by different mutations |
| `writetime(value)` is far in the future | Compare epoch µs with UTC, timestamp generator, `USING TIMESTAMP` | Clock skew or client supplying an invalid timestamp |
| `writetime` returns `null` despite prior writes | Check value, delete/TTL, request history | No live cell remains for the function to read metadata |
| Results differ across reads | Check CL, RF, replica health, repair, concurrent writes | Replicas or versions out of sync; TTL may be counting down |

A compact diagnostic query:

```sql
SELECT device_id,
       state,
       writetime(state) AS state_write_us,
       ttl(state) AS state_ttl_s,
       description,
       writetime(description) AS description_write_us,
       ttl(description) AS description_ttl_s
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

**Three rules when reading the output:**

1. **Compare metadata per cell:** `writetime(state)` does not represent the entire row.
2. **Keep units straight:** write timestamps are µs; CQL `timestamp` is ms; TTL is seconds.
3. **Verify the timestamp source:** `writetime()` does not say who generated the timestamp; check application logs, driver/coordinator configuration, and write history.

In production, avoid full-table scans just to hunt for low-TTL cells. The wide-column model requires querying by appropriate partition keys; for cluster-wide monitoring, use sampling on known keys, application metrics, and operational tooling instead of `ALLOW FILTERING` on large tables.

## 14. Self-Check Exercises

**Question 1.** `writetime(state)` returns `1800000000000123`. Is this value in microseconds or milliseconds?

**Answer:** **Microseconds** since the Unix epoch. If a Java application needs an `Instant` from it, use the proper epoch-microseconds conversion.

**Question 2.** The `state` cell still holds `'online'`, yet `ttl(state) = null`. Can you conclude the cell has expired?

**Answer:** No. The value is still present; `ttl(state) = null` usually means the current version **has no TTL set**.

**Question 3.** `UPDATE ... USING TTL 120 SET state = 'alert'` only modifies `state`. Does `description` automatically expire after 120 seconds?

**Answer:** No. TTL attaches to the written cell; `description` retains its own metadata unless updated in the same mutation.

**Question 4.** A cell is written with a 60-second TTL, and 10 seconds later is rewritten with a 300-second TTL. Is the remaining lifetime of the new version 350 seconds?

**Answer:** No. When the new version wins, it carries a fresh TTL of roughly **300 seconds from the new write**, without adding the previous version's remaining time.

**Question 5.** A cell has been `DELETE`d. Does `writetime(cell)` let you read the tombstone's write timestamp directly?

**Answer:** No. `writetime()` observes metadata of live values; you need mutation history or appropriate SSTable/internal inspection tools to examine tombstones.

**Question 6.** Why does a table created with `default_time_to_live = 900` still return a positive `ttl(payload)` even when the `INSERT` has no `USING TTL`?

**Answer:** Because the table has a default TTL; Cassandra applies that default lifetime to written data unless the statement overrides that policy.

**Question 7.** To query a device's 100 newest records, should you use `writetime(temperature)` as the sort key?

**Answer:** No. Design the **partition key** and **clustering key** around the query (such as `reading_day` and `event_time`); `writetime()` is only for observing metadata.

**Question 8.** Two replicas diverge: one has `state = A` at timestamp `200` and the other has `state = B` at timestamp `300`. What will `writetime(state)` be after reconciliation if there is no newer tombstone?

**Answer:** `300`, because version `B` wins under LWW. The function does not return a list containing both `200` and `300`.

---

**Key takeaway:** `WRITETIME(column)` reports the **mutation timestamp in microseconds** of a live cell; `TTL(column)` reports the **remaining seconds** if the cell has a TTL. Read both functions **per column**, interpret them in the context of `USING TTL`/`default_time_to_live`, LWW, replication, and tombstones. They are invaluable for diagnostics, yet they neither provide version history nor replace query-driven table design in Cassandra.
