# Updating a Value with TTL and What the New Lifetime Means

## 1. Goal: Understanding What Happens When Overwriting an Expiring Value

In **Apache Cassandra**, a **distributed wide-column** database management system, a cell can be written with a **TTL** (*time to live*) so it automatically expires after a specified number of seconds. A question arises when an application **updates that same cell** before the old TTL finishes: does the cell keep the old deadline, add the new duration on top, or restart counting?

**Core rule:** If a cell-updating mutation **wins by write timestamp**, it creates a **new value version** with new metadata. The TTL and expiration time of the new version are determined **from the new write**, rather than being added to the remaining TTL of the old version.

- `UPDATE ... USING TTL 120 SET value = ...`: the new version is given a lifetime of **120 seconds from the new write**.
- `UPDATE ... SET value = ...` on a table **with no default TTL**: the new version **has no TTL**, even if the previous version was counting down.
- `UPDATE ... SET value = ...` on a table with `default_time_to_live = 600`: the new version generally receives the **default 600-second TTL**.
- `UPDATE ... USING TTL 0 SET value = ...`: the new version **has no TTL**, even if the table defines a default TTL.
- `UPDATE` on a **different column**: does not automatically refresh the TTL of untouched cells.

The crucial condition lies in the word **"wins"**: Cassandra reconciles writes to the same cell via **last-write-wins (LWW)** based on mutation timestamp. An `UPDATE` statement that completes successfully yet carries a timestamp lower than the current version can **leave the observed value and TTL unchanged**.

In this lesson, we use CQL and Java to predict outcomes, distinguish **relative lifetime** from an **absolute business deadline**, and understand impacts on replication, tombstones, compaction, and repair.

## 2. Timeline: New TTL Does Not Add onto Old TTL

Suppose a cell is first written with a **300-second** TTL at `10:00:00`:

```text
10:00:00                                               10:05:00
   |---------------- Old TTL: 300 seconds --------------------|
   |
   +-- status = 'PENDING' (version A)

10:01:30                         10:03:30
   |--------------------------------|
   +-- UPDATE status = 'PAID'        |
       USING TTL 120                |
       version B wins                +-- B expires
```

At `10:01:30`, version A's remaining TTL is roughly **210 seconds**. When writing version B with a **120-second** TTL, the new deadline is around **`10:03:30`**, not `10:07:00` (210 + 120 seconds) and not `10:05:00` (the old deadline).

| Scenario at `10:01:30` | New version's TTL | New expiration time, assuming write wins and accurate clock |
|---|---|---|
| Write `'PAID' USING TTL 120` | 120 seconds | Around `10:03:30` |
| Write `'PAID' USING TTL 600` | 600 seconds | Around `10:11:30` |
| Write `'PAID'`, table has no default TTL | No TTL | Does not expire due to TTL |
| Write `'PAID' USING TTL 0` | No TTL | Does not expire due to TTL |
| Write only the `updated_by` column | `status` cell keeps old deadline | Around `10:05:00` |

**Terminology note:** "Renewing TTL" is often used when increasing lifetime, yet a **shorter** new TTL can cause the value to expire **sooner** than originally expected. Therefore, it is more accurate to say **resetting the lifetime for the new cell version**.

There is no independent countdown task per cell. Cassandra stores expiration metadata, and during reads or SSTable processing determines whether the cell is live or expired. `ttl(column)` returns **remaining seconds**, typically slightly lower than the declared TTL due to latency and whole-second resolution.

## 3. Setting Up a CQL Table to Observe TTL During Updates

Practice in a **test keyspace** selected with `USE <keyspace>;`. The fixed UUIDs below assume **no prior data exists**; if you re-run the examples, change the UUIDs to avoid tombstones or write timestamps from previous runs affecting the results.

```sql
CREATE TABLE IF NOT EXISTS payment_state_by_id (
    payment_id uuid PRIMARY KEY,
    state text,
    updated_by text,
    event_at timestamp
);
```

This schema serves queries for a payment by `payment_id`. It is not meant to demonstrate full real-world payment transaction management; critical monetary state typically requires conditional transitions or a trusted event source.

Create a cell with an active TTL:

```sql
INSERT INTO payment_state_by_id (
    payment_id, state, updated_by, event_at
)
VALUES (
    10101010-1010-4010-8010-101010101010,
    'PENDING',
    'checkout',
    '2026-11-21T00:00:00Z'
)
USING TTL 300;

SELECT state,
       ttl(state) AS state_ttl_s,
       writetime(state) AS state_write_us,
       updated_by, ttl(updated_by) AS updated_by_ttl_s,
       event_at
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

Right after writing with no conflicting mutations:

- `state = 'PENDING'`, `ttl(state)` is near **300 seconds**.
- `updated_by` was also written in the `INSERT`, so it has a TTL near **300 seconds**.
- `event_at` is a **business timestamp** stored in a CQL `timestamp` column, not the TTL start anchor.
- `writetime(state)` is the **microsecond** mutation timestamp used for LWW, not the remaining seconds.

Because all three columns were written in the same mutation, they generally share metadata from that write. Subsequent updates can cause TTLs across cells to diverge.

## 4. Experiment A: Overwriting the Same Cell with a New TTL

Before the initial 300 seconds expire, run:

```sql
UPDATE payment_state_by_id
USING TTL 120
SET state = 'PAID'
WHERE payment_id = 10101010-1010-4010-8010-101010101010;

SELECT state, ttl(state), writetime(state),
       updated_by, ttl(updated_by), writetime(updated_by)
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

If the new mutation wins LWW, the result right after updating is:

| Column | Value | Remaining TTL | Write timestamp |
|---|---|---|---|
| `state` | `PAID` | Near **120 seconds** | Timestamp of `UPDATE` |
| `updated_by` | `checkout` | Continues counting down from **300 seconds of `INSERT`** | Timestamp of `INSERT` |
| `event_at` | Original business timestamp | Continues counting down from **300 seconds of `INSERT`** | Timestamp of `INSERT` |

This is a direct example of **cell-level TTL**: updating `state` does not extend `updated_by` or `event_at`. Furthermore, updating `state` with a 120-second TTL while the old `state` still had 250 seconds left makes the new version **expire earlier** than the old one.

### Does Rewriting the Exact Same Value Have an Effect?

Yes. Cassandra does not require the new string to differ from the old string to treat it as a mutation. Example:

```sql
UPDATE payment_state_by_id
USING TTL 600
SET state = 'PAID'
WHERE payment_id = 10101010-1010-4010-8010-101010101010;

SELECT state, ttl(state), writetime(state)
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

Even though `state` is still `'PAID'`, if the rewrite wins by timestamp, `ttl(state)` is near **600 seconds from the new `UPDATE`**, and `writetime(state)` changes to the new mutation's timestamp. **The same value does not mean the same metadata.**

In real applications, repeated writes with differing TTLs can cause premature expiration or keep data alive longer than intended. Control retries and idempotency rules carefully.

## 5. Experiment B: Updating Without `USING TTL`

For the `payment_state_by_id` table above, we did not set `default_time_to_live`; its default is `0` (**no default TTL**). When rewriting `state` without `USING TTL`:

```sql
UPDATE payment_state_by_id
SET state = 'SETTLED'
WHERE payment_id = 10101010-1010-4010-8010-101010101010;

SELECT state, ttl(state), writetime(state),
       updated_by, ttl(updated_by)
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

If the new mutation wins:

- `state = 'SETTLED'`.
- `ttl(state) = null`: the new version **no longer has a TTL expiration**.
- `updated_by` still keeps the separate TTL set in the initial `INSERT`, if it has not yet expired.

This often surprises developers: **a column previously written with a TTL does not automatically keep that TTL when overwritten without specifying a new TTL**.

In production, a status-editing API that accidentally omits `USING TTL` can turn temporary data into long-lived data. If every update must still expire, design the API to always pass an appropriate TTL or use a table default TTL.

## 6. Experiment C: Deliberately Setting `USING TTL 0`

`USING TTL 0` requests that the new cell version have **no TTL**, even when the table has a default TTL. This is how you establish a non-expiring TTL policy for the **written cells**, not a delete command.

```sql
UPDATE payment_state_by_id
USING TTL 0
SET state = 'ARCHIVED'
WHERE payment_id = 10101010-1010-4010-8010-101010101010;

SELECT state, ttl(state), writetime(state)
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

If it wins LWW, the result is `state = 'ARCHIVED'` and `ttl(state) = null`. It does not mean "expire immediately" or "delete in 0 seconds."

| Write statement | On table with no default TTL | On table with `default_time_to_live = 900` |
|---|---|---|
| `UPDATE ... SET state = 'X'` | New cell has **no TTL** | New cell has **900-second** TTL |
| `UPDATE ... USING TTL 120 SET state = 'X'` | **120-second** TTL | **120-second** TTL |
| `UPDATE ... USING TTL 0 SET state = 'X'` | **No TTL** | **No TTL** |

Never use TTL `-1`, negative values, or ambiguous encodings to represent "forever." `TTL 0` must be an explicit data lifecycle decision; for sensitive data, "no TTL" may trigger separate retention or deletion obligations.

## 7. Experiment D: Updating Another Column Does Not Extend a Cell's TTL

This case is easily confused with "row TTL." Create a separate key:

```sql
INSERT INTO payment_state_by_id (payment_id, state, updated_by)
VALUES (
    20202020-2020-4020-8020-202020202020,
    'PENDING',
    'checkout'
)
USING TTL 180;

-- Change only updated_by without rewriting state.
UPDATE payment_state_by_id
USING TTL 3600
SET updated_by = 'operations'
WHERE payment_id = 20202020-2020-4020-8020-202020202020;

SELECT state, ttl(state), writetime(state),
       updated_by, ttl(updated_by), writetime(updated_by)
FROM payment_state_by_id
WHERE payment_id = 20202020-2020-4020-8020-202020202020;
```

Right after updating:

- `state = 'PENDING'`, `ttl(state)` continues counting down from the `INSERT`'s **180 seconds**.
- `updated_by = 'operations'`, `ttl(updated_by)` is near **3,600 seconds** from the `UPDATE`.
- Two cells in the same row have different write timestamps and expirations.

After `state` expires, the row **can still exist** because `updated_by` has not yet reached its TTL. Java clients must be prepared for `state` being `null` inside a row that still exists.

**Conclusion:** Do not call a single column's TTL "the whole object's TTL" unless the schema design and every write path guarantee uniform lifetimes.

## 8. Table Default TTL During Updates

Cassandra supports `default_time_to_live`, a table property measured in **seconds**. When a default TTL is set, mutations **that do not specify their own TTL** generally use the active default value when writing cells.

```sql
CREATE TABLE IF NOT EXISTS short_cache_by_key (
    cache_key text PRIMARY KEY,
    payload text,
    refreshed_by text
) WITH default_time_to_live = 900;

INSERT INTO short_cache_by_key (cache_key, payload, refreshed_by)
VALUES ('summary:42', 'initial', 'worker-a');

SELECT payload, ttl(payload), refreshed_by, ttl(refreshed_by)
FROM short_cache_by_key
WHERE cache_key = 'summary:42';
```

Both initial data cells have a TTL near **900 seconds**. Now update `payload`:

```sql
-- Without USING TTL: receives the default 900-second TTL for the new payload.
UPDATE short_cache_by_key
SET payload = 'recomputed'
WHERE cache_key = 'summary:42';

SELECT payload, ttl(payload),
       refreshed_by, ttl(refreshed_by)
FROM short_cache_by_key
WHERE cache_key = 'summary:42';
```

If the update wins, `ttl(payload)` is near **900 seconds** from the update, while `ttl(refreshed_by)` continues counting from the `INSERT`.

### Overriding the Default with an Explicit TTL

```sql
UPDATE short_cache_by_key
USING TTL 60
SET payload = 'transient'
WHERE cache_key = 'summary:42';

SELECT payload, ttl(payload)
FROM short_cache_by_key
WHERE cache_key = 'summary:42';
```

The new `payload` cell has a TTL near **60 seconds**, not 900 seconds. If you want no TTL despite the table default:

```sql
UPDATE short_cache_by_key
USING TTL 0
SET payload = 'pinned'
WHERE cache_key = 'summary:42';
```

**Changing `default_time_to_live` via `ALTER TABLE` does not automatically update metadata of existing cells**. It only affects writes issued after the new schema takes effect. To change the lifetime of an existing cell, a suitable new mutation is required rather than merely altering the default.

## 9. When the New Write Loses Last-Write-Wins, Does the TTL Change?

**Not necessarily.** Cassandra arbitrates conflicts by **mutation timestamp**, measured in **microseconds since the Unix epoch**, rather than request arrival order. This applies equally to cells with TTL.

To keep the current wall clock from skewing the example, use **a fresh UUID** with manual timestamps:

```sql
INSERT INTO payment_state_by_id (payment_id, state)
VALUES (
    30303030-3030-4030-8030-303030303030,
    'FIRST'
)
USING TIMESTAMP 1800000000002000 AND TTL 600;

-- This UPDATE is sent later, yet has a smaller timestamp.
UPDATE payment_state_by_id
USING TIMESTAMP 1800000000001000 AND TTL 30
SET state = 'SECOND'
WHERE payment_id = 30303030-3030-4030-8030-303030303030;

SELECT state, writetime(state), ttl(state)
FROM payment_state_by_id
WHERE payment_id = 30303030-3030-4030-8030-303030303030;
```

Expected output immediately after both mutations:

| Expression | Value |
|---|---|
| `state` | `FIRST` |
| `writetime(state)` | `1800000000002000` |
| `ttl(state)` | Near **600 seconds**, not 30 |

Reason: `SECOND@...1000` does not beat `FIRST@...2000`, so **the losing mutation's TTL of 30 does not become the metadata of the visible cell**.

If you retry with timestamp `1800000000003000` and TTL 30, the new version wins and receives a new lifetime of roughly **30 seconds from the later mutation**. Never use abnormal `USING TIMESTAMP` values on production data just to "adjust TTL"; future timestamps can shadow valid subsequent writes.

### Equal Timestamps

When two values for the same cell have equal timestamps, Cassandra uses internal tie-breaking rules; never assume the mutation sent later wins. When a tombstone conflicts with a live value at the same timestamp, the tombstone takes precedence. Therefore, when testing TTL resets, use writes with clear timestamp ordering and fresh test keys.

## 10. When the New TTL Expires, Does the Old Value Reappear?

**Never design around that assumption.** TTL does not provide a "stack" of version history or an automatic rollback mechanism:

```text
10:00    state = PENDING   TTL 1 hour        (version A)
10:05    state = PAID      TTL 2 minutes     (version B wins)
10:07    B expires
         |
         +-- Does NOT revert to state = PENDING by default.
             Expired data is handled via expiration/tombstones.
```

At the storage level, older versions may still linger in memtables/SSTables or on other replicas, yet Cassandra uses timestamp metadata and tombstones to prevent stale versions from reappearing after new data expires or is deleted. Tombstone cleanup must follow safety rules; if a replica holds an old version too long and tombstones are purged prematurely, **zombie data** risk arises.

Never use a short-TTL update as a "temporary override that automatically reverts" an important state. If business logic must return to a previous value, **the application must issue a new transition** with an appropriate timestamp/business sequence, or store events and recompute state from a trusted source.

Another case is when the new cell's TTL is longer than the old TTL. When the new cell later expires, the old version still does not reappear automatically; the new TTL controls the new version's lifecycle rather than maintaining a fallback data stack.

## 11. Retries, Timeouts, and Idempotency: TTL Can Be Refreshed Unintentionally

In distributed applications, a request may be accepted by some replicas while the client encounters a **timeout** before learning the outcome. If the application **issues a new mutation** with the same value, a higher timestamp, and the same TTL, the expiration deadline can be pushed forward:

| Time | Operation | Expected lifetime |
|---|---|---|
| `12:00` | `INSERT token USING TTL 300` | Around `12:05` |
| `12:02` | Retry via a **new** mutation `USING TTL 300` with a winning timestamp | Around `12:07` |
| `12:05` | App assumes token expired per initial write | Token may still be alive from the later write |

**Not every retry extends TTL.** If a retry genuinely resends the exact same mutation with the same timestamp/expiration metadata, it can behave more idempotently. Distinguish driver-level retries from the application constructing a **brand-new write request**; verify how your driver version assigns timestamps and how TTL is computed at different instants.

### When an Absolute Deadline Is Required

For OTPs, tokens, or processing sessions requiring "expire at 12:05 regardless of retries," use **`expires_at` as an absolute business timestamp** from a trusted time source:

1. Determine `expires_at` when creating the event (or obtain it from the token issuer).
2. Before each write/retry, compute remaining time `expires_at - trustedNow`.
3. If already expired, **do not rewrite**; handle as an expired object.
4. If still valid, convert the remaining duration into a valid positive TTL, write it, and still **check `expires_at`** on the business validation path.

Cassandra TTL is useful for automated storage cleanup, **not a substitute** for deadline validation, token replay prevention, or cross-client compare-and-set. In particular, **never convert zero remaining seconds into `USING TTL 0`**: in Cassandra, TTL 0 means **never expire**, the exact opposite of what you intended!

## 12. Java Driver: Updating with a New TTL and Deadline API

In Java, **Apache/DataStax Cassandra Java Driver 4.x** lets you bind TTL in a prepared statement. The number passed to `USING TTL ?` is **seconds**, not milliseconds or microseconds:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class ExpiringPaymentStateRepository {
    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement updateWithTtl;
    private final PreparedStatement updateWithoutTtl;
    private final PreparedStatement inspect;

    public ExpiringPaymentStateRepository(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.updateWithTtl = session.prepare(
            "UPDATE payment_state_by_id USING TTL ? " +
            "SET state = ? WHERE payment_id = ?"
        );
        this.updateWithoutTtl = session.prepare(
            "UPDATE payment_state_by_id " +
            "SET state = ? WHERE payment_id = ?"
        );
        this.inspect = session.prepare(
            "SELECT state, ttl(state) AS ttl_s, " +
            "writetime(state) AS write_us " +
            "FROM payment_state_by_id WHERE payment_id = ?"
        );
    }

    public void replaceForSeconds(UUID id, String state, int ttlSeconds) {
        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        // The new mutation resets TTL if it wins LWW.
        session.execute(updateWithTtl.bind(ttlSeconds, state, id));
    }

    public void replaceWithoutTtl(UUID id, String state) {
        // On a table without default TTL: new cell has no TTL.
        session.execute(updateWithoutTtl.bind(state, id));
    }

    public void replaceUntil(UUID id, String state, Instant expiresAt) {
        long secondsLeft = Duration.between(clock.instant(), expiresAt)
            .getSeconds();
        if (secondsLeft <= 0) {
            throw new IllegalStateException("Object already expired");
        }
        int ttlSeconds = Math.toIntExact(secondsLeft);
        // Also validate against Cassandra/cluster TTL limits.
        replaceForSeconds(id, state, ttlSeconds);
    }

    public void inspect(UUID id) {
        Row row = session.execute(inspect.bind(id)).one();
        if (row == null) {
            System.out.println("No live row");
            return;
        }
        String state = row.getString("state");
        Integer ttl = row.isNull("ttl_s") ? null : row.getInt("ttl_s");
        Long writeUs = row.isNull("write_us") ? null : row.getLong("write_us");
        System.out.printf("state=%s ttl=%s writeUs=%s%n",
            state, ttl, writeUs);
    }
}
```

**Why does `replaceUntil` need extra care in production?** The example uses whole seconds **truncated downward** from the deadline. If less than one second remains, it rejects instead of accidentally passing TTL 0. However:

- Ensure `clock` is trustworthy and hosts have synchronized time.
- Actual TTL is evaluated while Cassandra processes the write, incurring latency; second-granularity TTL is not a millisecond-exact deadline mechanism.
- Not every positive `int` TTL is valid across all Cassandra versions; check cluster maximums and overflow policies.
- If strict expiration enforcement is required, add an `expires_at timestamp` column and validate it on the read/business usage path.
- Critical payment state transitions should use **conditional updates** or event streams, not rely solely on TTL/LWW.

The code deliberately separates **writing with a new TTL** from **writing without specifying a TTL** to show the two different policies. If the table is later altered to `default_time_to_live > 0`, the behavior of `replaceWithoutTtl` changes to match that default TTL.

## 13. Special Cases: Collections, UDTs, Counters, and LWT

### 13.1. Collections and UDTs

A **non-frozen** collection/UDT column can be represented by multiple cells:

- `map<text,text>`: updating `settings['theme']` can set a new TTL **for that key** without extending other keys.
- `set<text>` and `list<text>`: elements written at different times can expire at different TTLs.
- Non-frozen UDT: `SET address.city = 'Hue'` can create a new version of the `city` field with a new TTL without resetting `street`.

Conversely, for `frozen<map<...>>` or `frozen<udt>`, the entire value is **one cell**. Rewriting the frozen value sets timestamp/TTL for **the whole cell**, with no independent per-element TTL.

If business logic needs independent element updates with clear lifetimes, choose an appropriate storage form or model **each element as its own row** per query. Collections should not grow unboundedly inside a partition.

### 13.2. Counters

Counters have specialized update rules and do not support `USING TTL` like regular data columns. Do not apply scalar + TTL update examples to counters.

### 13.3. LWT and Business Preconditions

When multiple services write to one state, **LWT** (*lightweight transactions*) with `IF` let you check update conditions via Paxos, for example:

```sql
-- Example on another UUID, updating only if current state is PENDING.
UPDATE payment_state_by_id
SET state = 'PAID'
WHERE payment_id = 40404040-4040-4040-8040-404040404040
IF state = 'PENDING';
```

The result includes `[applied]` so the client knows whether the condition held. LWT carries higher overhead than regular writes and should not be arbitrarily mixed with manual `USING TIMESTAMP` clauses. TTL still only manages data lifecycle; **it does not enforce conditional state transitions**.

## 14. Replication, Compaction, and Repair When TTL Is Reset

Cassandra can store a partition across multiple replicas according to its **replication factor (RF)**. A cell update with a new TTL is coordinated to replicas; nodes do not necessarily receive requests simultaneously. **Consistency levels** (`ONE`, `QUORUM`, `ALL`) constrain read/write response requirements, without changing LWW rules or the meaning of `USING TTL`.

| Mechanism | Relation to new TTL |
|---|---|
| **Mutation timestamp** | Chooses the winning cell version; observed TTL belongs to the winning version |
| **TTL/expiration metadata** | Indicates when that version ceases to be valid |
| **Replication** | Some replicas may temporarily hold different versions, requiring reconciliation |
| **Consistency level** | Specifies how many replicas participate/acknowledge; does not add old and new TTLs |
| **Repair** | Helps replicas cross-check and converge data versions |
| **Compaction** | Safely cleans up SSTables/tombstones when conditions permit |

When a cell's TTL expires, it is treated similarly to deleted data; Cassandra must guard against **stale copies from replicas** reappearing. Thus, TTL ending **does not mean bytes vanish from disk immediately**. Tombstones, `gc_grace_seconds`, repair schedules, and compaction policies all affect safe physical cleanup.

A workload that continuously "refreshes" TTLs at high frequency can create many versions in SSTables and raise compaction/tombstone pressure, especially with short TTLs and high traffic. Measure **latency, write rate, tombstone counts, disk usage, and repair frequency** instead of just inspecting `ttl()` on a few keys.

Never lower `gc_grace_seconds` or manually touch SSTables just to fix "TTL didn't reset"; first verify whether the mutation won LWW and which TTL policy the client actually sent.

## 15. Diagnostic Checklist: Why Is TTL After `UPDATE` Not What Was Expected?

Query the exact partition key and cells you want to inspect:

```sql
SELECT payment_id,
       state, ttl(state) AS state_ttl_s,
       writetime(state) AS state_write_us,
       updated_by, ttl(updated_by) AS updated_by_ttl_s
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

| Symptom | Primary hypothesis | What to verify |
|---|---|---|
| TTL near 120 right after update, previously near 300 | Normal: new version has TTL 120 | Correct cell and update timing |
| `ttl(state) = null`, yet `state` remains | New cell **has no TTL** | CQL omitted `USING TTL`, `USING TTL 0`, default TTL |
| `ttl(state)` still shows the old TTL | New mutation **did not win** or read saw another version | `writetime(state)`, `USING TIMESTAMP`, clock skew, replica/CL |
| TTL after write is near 900 despite statement omitting TTL | Table has **`default_time_to_live = 900`** | Current schema, actual CQL path |
| New TTL is counting down even though value stayed identical | Rewriting same value creates a new cell version | Timestamp/TTL of repeated writes |
| `state`'s TTL changed while `updated_by`'s did not | Only `state` was written | Which columns were `SET` in the mutation |
| Value vanished before old TTL finished | New version had shorter TTL, or a delete occurred | Mutation history, TTL of winning version |
| Expired value still takes disk space | Data/tombstones awaiting safe compaction | SSTables, compaction, repair |
| Retries make lifetime longer than expected | App issued a new mutation with a new deadline | Event IDs, retry policy, mutation timestamp, `expires_at` |

**Three fastest steps** when investigating:

1. Read **value, `ttl()`, and `writetime()` of the exact cell** in question.
2. Inspect the **final CQL** and **table default TTL**; distinguish which mutation actually wrote the cell.
3. Cross-check **mutation timestamp source, retry logs, and replica health**, avoiding blaming TTL when the cause is LWW/clock skew.

`ttl(column) = null` **does not by itself prove** a cell has expired. If the value is still present, the usual reason is **the current version has no TTL**. If the value is no longer live, it may be due to TTL expiration, `DELETE`, never being written, or reconciliation.

## 16. Self-Check Exercises

**Question 1.** At 10:00, `status = A USING TTL 300` is written. At 10:01, `status = B USING TTL 120` is written and B wins. Assuming no other writes, when does B expire?

**Answer:** Around **10:03**, i.e., 120 seconds from B's write. It does not add A's remaining 240 seconds.

**Question 2.** Same scenario, except write B has TTL 600. Roughly when is the new deadline?

**Answer:** **10:11**, i.e., 600 seconds from 10:01.

**Question 3.** A cell has a 60-second TTL. The application rewrites **the same value** with `USING TTL 300` and the mutation wins. Does the TTL reset?

**Answer:** **Yes.** The value may stay unchanged, yet the new cell version's metadata carries a TTL of roughly 300 seconds.

**Question 4.** A table has `default_time_to_live = 0`. An `UPDATE` rewrites a cell that previously had a TTL, **without `USING TTL`**. What is the outcome if the mutation wins?

**Answer:** The new version **has no TTL**, so `ttl(cell) = null` while the cell remains live.

**Question 5.** A table has `default_time_to_live = 900`. What new lifetime does `UPDATE ... SET value = 'X'` without an explicit TTL create?

**Answer:** A **900-second** TTL for the written cell version, if the mutation wins.

**Question 6.** Both `state` and `updated_by` initially have a 300-second TTL. Only `state` is updated with TTL 120. Does `updated_by` reset its TTL?

**Answer:** **No.** `updated_by` keeps the lifetime belonging to its own version.

**Question 7.** A was written with timestamp 500 and TTL 300. B was written later with timestamp 400 and TTL 30. After both commands, is `ttl(column)` guaranteed to be near 30?

**Answer:** **No.** B loses LWW, so the cell retains A's value/TTL as long as A has not expired.

**Question 8.** Retrying a token after it already expired; the app computes 0 remaining seconds and passes `USING TTL 0`. Is this right?

**Answer:** **Wrong and dangerous**: TTL 0 means **never expire**, not expire immediately. Reject writing already-expired tokens or handle them in the appropriate business flow.

**Question 9.** A new cell with TTL 30 replaces an old cell with TTL 3600. When the new cell expires, does the old version automatically reappear?

**Answer:** **Never assume that.** TTL does not maintain a version stack. Cassandra uses expiration/tombstone metadata to prevent older versions from reappearing; to restore a prior state, the application must actively write a valid new event/version.

---

**Key takeaway:** When updating a value with a TTL, **the LWW-winning mutation creates a new cell version and a new lifetime**. The new TTL counts in seconds **from the new write**, neither adding to remaining TTL nor preserving the old deadline. Omitting TTL can **remove TTL** (on a table with no default TTL) or **apply the default TTL** (on a table with `default_time_to_live`); `USING TTL 0` means **no TTL**, not immediate expiration. Always inspect `ttl()` alongside `writetime()`, control retries, and store `expires_at` when business logic needs an absolute deadline.
