# TTL for Newly Written Data and When the Countdown Starts in Apache Cassandra

## 1. What Problem Does TTL Solve?

In **Apache Cassandra**, a **distributed wide-column** database, some data is only valuable for a short time: verification codes, temporary device states, cache entries, unread notifications, or sessions. Keeping it forever increases table size and operational cost. Cassandra supports **Time To Live (TTL)** so data automatically **expires after a declared duration**.

For example, a verification code valid for only 5 minutes:

```sql
INSERT INTO login_challenge_by_id (
    challenge_id, user_id, code_hash
)
VALUES (
    11111111-7777-4777-8777-111111111111,
    22222222-7777-4777-8777-222222222222,
    'example-hash-not-a-real-code'
)
USING TTL 300;
```

TTL `300` is measured in **seconds**. If Cassandra processes the mutation write around `10:00:00`, the cells with TTL will expire around `10:05:00`. Expired values are no longer returned as live data, even though their bytes on disk may not be reclaimed immediately by compaction.

**The most important point of this lesson:** a new cell's TTL starts counting when **Cassandra performs the write that creates that cell version**. It does **not** start when the table was created, from a timestamp in a business column like `created_at`, or from a mutation timestamp that the application deliberately sets in the past.

TTL is especially useful when designing tables around **queries and data lifecycles**. However, distinguish cell-level validity, replica state, and physical cleanup timing to avoid false expectations.

## 2. When Does the TTL Clock Start Running?

An `INSERT` or `UPDATE` with `USING TTL N` creates a data version with a **lifetime of N seconds from when the write is processed**. Cassandra stores expiration metadata alongside the data. Across the cluster, server-side clocks on the write path participate in determining expiration time; therefore, node clocks must be synchronized. Never treat the time the client sent the request or received the response as the exact TTL boundary.

Consider a successful write with a 120-second TTL:

```text
Client sends INSERT       Cassandra processes write          Expires
      |                            |                           |
      |------ network latency ----->|<------ 120 seconds ----->|
      |                            |                           |
      |                    TTL starts counting            Cell expires
      |                            |
      |                   ttl(column) ≈ 120
      |                            |
      |                    After ~30 seconds
      |                   ttl(column) ≈ 90
```

Suppose Cassandra processes the write at `12:00:00` according to the clock the system uses to compute expiration:

| Observation time | Cell still alive? | Estimated `ttl(column)` |
|---|---|---|
| `12:00:00`, right after write | Yes | Near `120` seconds |
| `12:00:30` | Yes | Near `90` seconds |
| `12:01:59` | Possibly, depending on rounding and read timing | Near `0–1` seconds |
| From around `12:02:00` | No longer a live cell | No live TTL left to observe |

Read TTL values may vary by a few seconds due to request flight time, sampling instant, **whole-second** resolution, and node clocks. When writing tests, assert a **reasonable range** rather than exact equality with `120`.

**There is no background countdown timer running per cell.** Cassandra stores expiration metadata and evaluates liveness when reading/processing data. Reaching expiration does not mean a task immediately erases bytes from every SSTable.

## 3. TTL, Mutation Timestamps, and Time Columns Are Three Different Things

The **Timestamps and TTL** chapter involves three easily confused concepts:

| Component | Unit | Role | Decides when TTL starts counting? |
|---|---|---|---|
| `USING TTL 120` | Seconds | Sets the lifetime for the written cells | **Yes:** grants a relative lifetime starting at write time |
| `USING TIMESTAMP 1700000000000000` | Microseconds since Unix epoch | Metadata to arbitrate versions via **last-write-wins** | **No:** does not turn TTL 120 into "120 seconds starting in 2023" |
| `created_at timestamp` column | Milliseconds since Unix epoch | Stores business time | **No:** purely application data |
| `writetime(col)` | Microseconds | Reads the write timestamp of a live cell | Observation only; not remaining TTL |
| `ttl(col)` | Remaining seconds | Reads remaining unexpired lifetime | Does not directly provide the original absolute start time |

For example, when **importing historical data** with a past write timestamp while setting a 120-second TTL, the newly written cell still counts its lifetime **from this import write**. `USING TIMESTAMP` selects the mutation's position under LWW; TTL controls the lifespan of the written cell version.

This also explains why **a mutation with a higher timestamp written earlier does not necessarily expire later than a mutation with a lower timestamp processed later**. Never infer expiration time from `writetime()`.

## 4. Basic CQL: TTL When `INSERT`ing New Data

Run in a **test keyspace** created and selected with `USE <keyspace>;`. Use an unused UUID so results are not affected by tombstones or timestamps from prior runs.

### Step 1 — Create an Illustrative Table

```sql
CREATE TABLE IF NOT EXISTS login_challenge_by_id (
    challenge_id uuid PRIMARY KEY,
    user_id uuid,
    code_hash text,
    created_at timestamp
);
```

This design serves queries for **a single challenge by ID**. In a real application, only store appropriate hashes/verification tokens and consider additional tables for querying by user or time; avoid treating TTL as the sole security mechanism.

### Step 2 — Write All New Data with a 300-Second TTL

```sql
INSERT INTO login_challenge_by_id (
    challenge_id, user_id, code_hash, created_at
)
VALUES (
    11111111-7777-4777-8777-111111111111,
    22222222-7777-4777-8777-222222222222,
    'example-hash-not-a-real-code',
    '2025-01-01T00:00:00Z'
)
USING TTL 300;

SELECT challenge_id, user_id, code_hash,
       ttl(code_hash) AS code_remaining_s,
       writetime(code_hash) AS code_write_us,
       created_at, ttl(created_at) AS created_at_remaining_s
FROM login_challenge_by_id
WHERE challenge_id = 11111111-7777-4777-8777-111111111111;
```

Immediately after writing:

- `code_hash` and `created_at` are the **written cells**; `ttl(code_hash)` and `ttl(created_at)` are near 300 seconds.
- `created_at` is **January 1, 2025**, intentionally far in the past; it **does not make the TTL expire immediately**. Both cells still live for roughly 300 seconds from the current `INSERT`.
- `writetime(code_hash)` is the mutation timestamp (microseconds) assigned by the driver/coordinator when the statement omits `USING TIMESTAMP`.
- `challenge_id` is the **primary key**, so `ttl(challenge_id)` or `writetime(challenge_id)` cannot be used as on regular data columns.

Once every meaningful cell in the row expires, the record has no live data left for reads. The key may still exist in storage structures as metadata/tombstones until safely cleaned up.

### Step 3 — Observe After Expiration

Re-running the `SELECT` after the TTL expires no longer returns `code_hash` and `created_at` as live values. Depending on any remaining data in the row and client formatting, you may see no row at all or `null` for data expressions. **Do not expect `ttl(code_hash)` to return a negative number meaning "overdue."**

> **Practice:** To observe expiration quickly without waiting 300 seconds, use **a fresh UUID** and replace `USING TTL 300` with `USING TTL 10`. Read immediately, then read again after 10 seconds have passed. Avoid overwriting the same old key with a lower timestamp because LWW can shadow the result.

## 5. Writing New Data with `USING TIMESTAMP` and TTL: Verifying the Start Time

This is the most important experiment for separating **version time** from **expiration time**.

```sql
-- Separate UUID for this experiment, with no prior data.
INSERT INTO login_challenge_by_id (challenge_id, code_hash)
VALUES (
    33333333-7777-4777-8777-333333333333,
    'historical-write-timestamp'
)
USING TTL 180 AND TIMESTAMP 1700000000000000;

SELECT code_hash,
       writetime(code_hash) AS write_us,
       ttl(code_hash) AS remaining_s
FROM login_challenge_by_id
WHERE challenge_id = 33333333-7777-4777-8777-333333333333;
```

Assuming no competing version exists:

| Field | Expected value |
|---|---|
| `code_hash` | `historical-write-timestamp` |
| `write_us` | `1700000000000000`, corresponding to a point in 2023 |
| `remaining_s` | Near **180 seconds**, not negative or `null` just because the write timestamp is old |

**Reason:** TTL is determined when Cassandra processes **the current write**; `1700000000000000` is solely the timestamp used for version arbitration. Even so, an old write timestamp can **lose** if the key already holds data or a tombstone with a larger timestamp; in that case the experiment will not observe the new version. Always use a fresh key.

By the same logic, deliberately setting a mutation timestamp far in the future is **not** a valid way to "extend TTL." It can also make normal subsequent updates lose under last-write-wins. Do not use abnormal test timestamps for production data.

## 6. Which Cells Receive the TTL?

Cassandra attaches TTL to **the data cells written by the mutation**, rather than assigning one single timer to the entire row by default.

| Write pattern | Cells affected by TTL |
|---|---|
| `INSERT` multiple regular columns with `USING TTL 60` | The data cells written in that `INSERT` |
| `UPDATE ... USING TTL 60 SET state = ...` | The updated `state` cell |
| `UPDATE ... SET note = ...` without TTL, table has no default TTL | The newly written `note` cell has no TTL |
| `CREATE TABLE ... WITH default_time_to_live = 900` | Newly written cells get the default TTL unless overridden |
| Primary key | `ttl(pk)` cannot be used; keys identify/route data |

Example of a row with both long-lived and expiring cells:

```sql
CREATE TABLE IF NOT EXISTS device_status_by_id (
    device_id text PRIMARY KEY,
    device_name text,
    latest_state text,
    last_notice text
);

INSERT INTO device_status_by_id (device_id, device_name)
VALUES ('sensor-ttl-01', 'Boiler A');

UPDATE device_status_by_id
USING TTL 45
SET latest_state = 'WARN'
WHERE device_id = 'sensor-ttl-01';

SELECT device_name, ttl(device_name),
       latest_state, ttl(latest_state),
       writetime(latest_state)
FROM device_status_by_id
WHERE device_id = 'sensor-ttl-01';
```

Right after updating, `ttl(device_name)` is `null` and `ttl(latest_state)` is near 45 seconds. After roughly 45 seconds, `latest_state` expires while `device_name = 'Boiler A'` remains intact.

This matters for Java applications: **a row can still be returned even after some columns' TTLs expire**, and each property must be treated as nullable. Never treat one column's TTL as the "expiration date" of the whole business entity if the table holds columns with different lifecycles.

## 7. Does `UPDATE` Restart the TTL Countdown?

**Yes, if the new mutation wins and is written as a new cell version.** When you re-update the same cell that currently has a TTL, the new version's metadata (write timestamp, TTL, and expiration time) is determined by the new write.

Test on a separate key:

```sql
INSERT INTO device_status_by_id (device_id, latest_state)
VALUES ('sensor-renew-01', 'STARTING')
USING TTL 60;

SELECT latest_state, writetime(latest_state), ttl(latest_state)
FROM device_status_by_id
WHERE device_id = 'sensor-renew-01';

-- Run this update before the 60-second TTL expires.
UPDATE device_status_by_id
USING TTL 300
SET latest_state = 'RUNNING'
WHERE device_id = 'sensor-renew-01';

SELECT latest_state, writetime(latest_state), ttl(latest_state)
FROM device_status_by_id
WHERE device_id = 'sensor-renew-01';
```

If the new version wins by timestamp, `latest_state` changes to `RUNNING`, and TTL restarts at **near 300 seconds from the UPDATE**. It is **not** "remaining seconds of the old version plus 300."

### Rewriting Without Specifying a TTL

For a table with `default_time_to_live = 0` (no TTL by default), the statement:

```sql
UPDATE device_status_by_id
SET latest_state = 'RUNNING_STABLE'
WHERE device_id = 'sensor-renew-01';

SELECT latest_state, ttl(latest_state)
FROM device_status_by_id
WHERE device_id = 'sensor-renew-01';
```

can create a new version **with no TTL** if the mutation wins. Then `ttl(latest_state) = null` even though the prior version had a TTL. **TTL is not inherited from the old cell**. Conversely, if the table has a **non-zero default TTL**, a write omitting `USING TTL` can still receive the default TTL.

A write that is older in **mutation timestamp** may fail to replace the newer version even if sent later, and thus also fail to "renew TTL" as the application expects. Inspect `writetime()` alongside `ttl()` after updates to understand which version is live.

## 8. Table Default TTL and Precedence Order

When a table's data shares a uniform lifecycle, instead of writing `USING TTL` on every statement, you can configure **`default_time_to_live`**:

```sql
CREATE TABLE IF NOT EXISTS transient_message_by_id (
    message_id uuid PRIMARY KEY,
    content text,
    source text
) WITH default_time_to_live = 900;
```

A regular write statement:

```sql
INSERT INTO transient_message_by_id (message_id, content, source)
VALUES (
    44444444-7777-4777-8777-444444444444,
    'Temporary notification',
    'system'
);

SELECT content, ttl(content), source, ttl(source)
FROM transient_message_by_id
WHERE message_id = 44444444-7777-4777-8777-444444444444;
```

Both new data cells typically have a TTL near **900 seconds**. If a write specifies its own TTL:

```sql
INSERT INTO transient_message_by_id (message_id, content, source)
VALUES (
    55555555-7777-4777-8777-555555555555,
    'Short notification',
    'system'
)
USING TTL 120;
```

The statement's **120-second TTL** is applied to the written cells instead of the 900-second default. Counting starts from **the second write**, not from when the table was `CREATE`d.

| Scenario | TTL applied to new cell |
|---|---|
| Table has no TTL, write omits `USING TTL` | No TTL |
| Table `default_time_to_live = 900`, write omits `USING TTL` | Uses default: 900 seconds |
| Table `default_time_to_live = 900`, write specifies `USING TTL 120` | Uses statement: 120 seconds |
| Updating a cell on a table with a default TTL | Updated cell receives TTL per the new mutation's policy |

**Do not alter `default_time_to_live` on a production table just to experiment:** changing the default policy affects subsequent writes and can cause unexpected expiration behavior. For data with mixed lifecycles, consider splitting tables by query pattern and lifecycle.

## 9. Does TTL Expiration Mean Immediate Deletion from Disk?

**No.** TTL determines when a cell is **no longer considered live data**. Past the deadline, Cassandra treats the cell as expired data and relies on tombstone/deletion metadata mechanisms to protect consistency across replicas.

```text
      Write new cell            TTL expires          Safe physical cleanup
           |                         |                        |
           v                         v                        v
       Live data              Cell becomes invalid    Compaction may remove
     ttl() decreases          not returned as live      data / tombstones
                                     |
                                     +-- Must consider replicas and repair
                                         before purging tombstones
```

Why can't it be physically erased right away? With replication factor `RF = 3`, one replica might temporarily miss a mutation or be unavailable. When an old node comes back, expired data must not "come back to life" simply because that replica still holds an older record. **Tombstones** shadow stale versions during reconciliation.

**Compaction** is where expired data and tombstones can be reclaimed once safety conditions permit. **Repair** keeps replicas synchronized; tombstone retention settings, repair policies, and node availability all affect **zombie data** risk. Therefore:

- Do not treat TTL as an "erase bytes immediately" command.
- Do not lower `gc_grace_seconds` or skip repairs just to reclaim disk space quickly.
- Monitor tombstone counts, compaction frequency, disk usage, and read latency on TTL-heavy tables.

TTL assists with data lifecycle management, yet **it does not by itself enforce security/immediate physical erasure requirements**. Sensitive-data deletion requirements demand dedicated storage, backup, and governance procedures.

## 10. TTL and Replication: Can Observed Timing Differ?

Cassandra is distributed, so writes can reach replicas at different times. Consistency levels **ONE, QUORUM, ALL** specify how many replicas must satisfy a read/write request, yet **they do not redefine how many seconds a TTL lasts**.

Suppose a mutation with a 60-second TTL is coordinated across three replicas:

- A write at `CL = ONE` can complete before all three replicas converge.
- A read issued right around write time at a weak consistency level can see a different version due to un-updated replicas.
- Near TTL expiration, clock skew between nodes can cause observed expiration timing to deviate.
- Version reconciliation still uses **mutation timestamps**, whereas TTL/expiration metadata determines whether a cell is live or expired.

Never assume `ttl(column) = 45` on one read means **every replica** is strictly synchronized at 45 seconds remaining. It is a value calculated for the data observed by that read under the node clocks and processing times involved.

**Clock skew** causes bugs in both mutation timestamp assignment and expiration evaluation/observation. Synchronize clocks across Cassandra nodes and driver hosts using NTP/chrony or equivalent services. A future `USING TIMESTAMP` is **not** a way to lengthen TTL; it can instead cause subsequent updates to lose under LWW.

## 11. Java Hands-On: Writing TTL Challenges with a Prepared Statement

Java applications connecting to Cassandra typically use **Apache/DataStax Cassandra Java Driver 4.x**. CQL lets you bind TTL as a parameter to create challenges whose lifetimes are determined at runtime:

```java
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class LoginChallengeRepository {
    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement select;

    public LoginChallengeRepository(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO login_challenge_by_id " +
            "(challenge_id, user_id, code_hash, created_at) " +
            "VALUES (?, ?, ?, ?) USING TTL ?"
        );
        this.select = session.prepare(
            "SELECT code_hash, ttl(code_hash) AS remaining_s " +
            "FROM login_challenge_by_id WHERE challenge_id = ?"
        );
    }

    public void create(
        UUID challengeId,
        UUID userId,
        String hashedCode,
        int ttlSeconds
    ) {
        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        // created_at is business data; TTL starts when Cassandra writes.
        session.execute(
            insert.bind(challengeId, userId, hashedCode, Instant.now(), ttlSeconds)
        );
    }

    public Integer remainingSeconds(UUID challengeId) {
        Row row = session.execute(select.bind(challengeId)).one();
        if (row == null || row.isNull("remaining_s")) {
            return null;
        }
        return row.getInt("remaining_s");
    }
}
```

Here `ttlSeconds` is in **seconds**, not epoch milliseconds or microseconds. `created_at` is bound as an `Instant` into a CQL `timestamp` column at millisecond resolution, and does **not** set the TTL start time. When reusing the repository across requests, each `INSERT` creates a new mutation with its own expiration deadline.

### Do Not Use TTL as a Legal Deadline or Absolute Business Lock

For example, a client sets a 300-second TTL and reads `remainingSeconds = 298`. If the application requires "this code may only be used before exactly 10:05:00 UTC," store an explicit **business deadline `expires_at`** from a trusted time source and check it during verification; let TTL handle automatic cleanup. This helps because write processing has latency and hosts can have clock skew.

To prevent challenge reuse, design conditional state transitions/consumption markers or dedicated coordination. TTL **does not create a compare-and-set transaction**, nor does it guarantee single-use under concurrent requests.

## 12. Common Scenarios That Confuse When Counting Starts

| Scenario | When does TTL start? | Important note |
|---|---|---|
| `INSERT ... USING TTL 60` on a new key | When the `INSERT` write is processed | Does not start at `CREATE TABLE` |
| `INSERT` with `created_at` set to an old date | When the `INSERT` write is processed | `created_at` does not govern TTL |
| `INSERT ... USING TIMESTAMP <past> AND TTL 60` | At the current write | Mutation timestamp has a separate LWW role |
| `UPDATE ... USING TTL 120` on the same cell | At the new `UPDATE` **if the version wins** | The new version's TTL is reset |
| Writing another column in the same row | At that column's write | Does not extend TTL of untouched cells |
| `default_time_to_live = 900` | Each new write receives the default TTL | Does not start when the table is created |
| Retrying an old mutation with a higher timestamp | At the new winning mutation | Can accidentally prolong lifetime or overwrite state |
| Data reaches TTL expiration | No live cell remains | Physical byte cleanup depends on compaction and safety rules |

One distinction to keep in mind: **client-level retries are not necessarily treated as "the same mutation" in metadata** if the application assigns a different timestamp or TTL on each attempt. For business rules needing exact expiration deadlines, do not rely on automatic retries preserving the exact original deadline; manage `expires_at` or replay policies at the application layer.

### Counters and Primary Keys

Cassandra does not use TTL on **`counter` columns** the way regular data columns do; counters have their own update mechanism. Primary keys identify partitions/rows and cannot have their TTL read directly with `ttl(primary_key_column)`. Once all live data cells in a row expire, the row can no longer be queried as a record containing data.

## 13. Diagnosing Early or Late Data Expiration

When encountering reports like "record was just created and already vanished" or "TTL was set to 5 minutes yet data is still visible," check in order:

| Step | Check | Why |
|---|---|---|
| 1 | `SELECT value, ttl(value), writetime(value)` by exact partition key | Determine whether cell is live, remaining TTL, and winning timestamp |
| 2 | Does `INSERT/UPDATE` specify `USING TTL`? | Actual declared TTL in seconds |
| 3 | Does the table have `default_time_to_live`? | Can apply TTL even if the write omits `USING TTL` |
| 4 | Which columns does the mutation touch? | TTL is per cell, not row-wide by default |
| 5 | Was there a later update/retry on the cell? | A winning new version can reset TTL |
| 6 | Was `USING TIMESTAMP`/custom driver timestamp used? | An older timestamp can lose to an existing live version or tombstone |
| 7 | Are node and service clocks synchronized? | Clock skew can affect expiration and arbitration |
| 8 | What are RF/CL, replica health, repair/compaction status? | Distinguish replica issues from expired TTL |

Practical diagnostic query:

```sql
SELECT challenge_id,
       code_hash,
       ttl(code_hash) AS remaining_s,
       writetime(code_hash) AS write_us,
       created_at,
       ttl(created_at) AS created_at_remaining_s
FROM login_challenge_by_id
WHERE challenge_id = 11111111-7777-4777-8777-111111111111;
```

**How to read it:** `write_us` shows the timestamp used in LWW (µs), `remaining_s` shows remaining TTL (seconds), and `created_at` is business time (ms). `writetime()` and `ttl()` only reflect the live cell version observed by the query; they do not list tombstones or losing versions.

Do not scan entire tables with `ALLOW FILTERING` just to find records about to expire. When many entities must be monitored, design tables around **needed queries**, track required events/deadlines at the application layer, and use Cassandra operational tools to monitor tombstones, repair, and compaction.

## 14. Self-Check Exercises

**Question 1.** A row is written at 10:00 with `USING TTL 120`. The `created_at` column inside the row holds 08:00. When will the cell expire if clocks and write processing are normal?

**Answer:** Around **10:02**, i.e., 120 seconds after Cassandra processed the write. `created_at` does not determine TTL.

**Question 2.** `USING TIMESTAMP 1700000000000000 AND TTL 60` creates a new cell today. Is the cell already expired since 2023?

**Answer:** No. The old write timestamp is for LWW; the 60-second TTL counts from **the current write**. If the key already has a newer version, the mutation may lose and not become visible.

**Question 3.** An `INSERT` sets a 90-second TTL on `state` and `note`. After 30 seconds, the application updates only `state` with a 120-second TTL. Is `note` extended to 120 seconds?

**Answer:** **No.** `note` keeps the lifetime from the earlier write and will expire on its own schedule; `state` gets the TTL from the new mutation if it wins.

**Question 4.** Why can `ttl(column)` be `null` even while the cell still has a value?

**Answer:** Because the cell currently **has no TTL**, for example when the table has no default TTL and the latest write omitted `USING TTL`.

**Question 5.** A table has `default_time_to_live = 900`, yet an `INSERT` uses `USING TTL 120`. What is the TTL for the cells in that `INSERT`?

**Answer:** **120 seconds**, because the TTL declared in the write statement takes precedence for the data created by that statement.

**Question 6.** After a 120-second TTL expires, does SSTable disk usage necessarily drop immediately?

**Answer:** **No.** The cell becomes invalid for reads first; physical cleanup depends on compaction and safety conditions related to tombstones/replicas/repair.

**Question 7.** Can `ttl(code_hash)` alone strictly prove that an OTP was used only once?

**Answer:** **No.** TTL only manages data lifetime. Preventing reuse requires conditional state checks and updates or a coordinated consumption mechanism.

**Question 8.** If an `UPDATE` uses a timestamp lower than the currently winning version, can it be guaranteed to reset the TTL?

**Answer:** **No.** A lower mutation timestamp can lose under LWW, so the cell's visible TTL remains that of the winning version.

---

**Key takeaway:** Cassandra's TTL is measured in **seconds starting from when the data version is written**, and applies to **the cells touched by the mutation**. It is independent of business timestamp columns and LWW mutation timestamps. `ttl(column)` reports remaining time and `writetime(column)` reports the write timestamp; both functions must be read in proper context. When TTL expires, data loses validity before physical cleanup occurs, so pay attention to replication, tombstones, compaction, and repair.
