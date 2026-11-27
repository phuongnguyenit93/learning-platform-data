# USING TIMESTAMP, USING TTL, and Allowed Combinations in Cassandra

In Apache Cassandra, `USING TIMESTAMP` and `USING TTL` both appear in CQL write statements, yet they **solve two completely different problems**:

- **`TIMESTAMP`** sets the *write timestamp* used to reconcile competing versions of data.
- **`TTL`** (*time to live*) sets the lifespan, in seconds, of the values being written.

The pitfalls go beyond units of measurement. `INSERT`, `UPDATE`, and `DELETE` place **`USING` in different positions**, do not support the same set of options, and impose restrictions when combined with `IF`/`IF NOT EXISTS` conditions (*lightweight transactions*, LWT). A syntactically valid statement may still fail to deliver the intended semantics when a replica goes offline, a write is retried, or older data remains in SSTables.

This lesson belongs to the **CQL Writes and Deletes** chapter of module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Its examples connect distributed write mechanics, partition keys, consistency levels, replication, compaction, and repair with Java Driver code.

After this lesson, you will know how to:

1. Place `USING TTL` and `USING TIMESTAMP` in the right syntactic position for each statement type.
2. Predict which fields expire and which timestamp wins when two mutations compete.
3. Recognize **allowed**, **disallowed**, and LWT-required combinations.
4. Use Java prepared statements without confusing seconds, milliseconds, and microseconds.
5. Design retries, handle tombstones, and verify write/delete outcomes in multi-replica systems.

## 1. CQL table used throughout

Suppose an account preferences service looks up data by `user_id`; the `demo` keyspace already exists in the test environment:

```sql
CREATE TABLE demo.user_preferences_by_id (
    user_id          uuid PRIMARY KEY,
    display_name     text,
    preferred_locale text,
    phone            text,
    otp_code         text,
    account_state    text,
    revision         int
);
```

`user_id` is both the **partition key** and the **full primary key** of the table. Cassandra uses this key to determine the partition and responsible replicas. The remaining columns are regular columns, each with its own version history and expiration behavior.

Create a sample row:

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, display_name, preferred_locale,
    phone, account_state, revision
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'Linh',
    'vi-VN',
    '0900000001',
    'ACTIVE',
    1
);

SELECT user_id, display_name, preferred_locale,
       phone, otp_code, account_state, revision
FROM demo.user_preferences_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

The lab examples assume no other client writes to the same key, node clocks are stable, and the table has no nonzero `default_time_to_live` unless noted otherwise. So that `USING TIMESTAMP` operations do not interfere with auto-generated timestamps, this lesson uses a **separate UUID** when demonstrating custom timestamps.

## 2. Grammar: where does USING go?

You cannot put `USING` in one uniform spot across all three statements. Remember these three templates (showing only the clauses relevant to this lesson):

```sql
-- INSERT: IF NOT EXISTS precedes USING if both appear.
INSERT INTO demo.user_preferences_by_id (user_id, otp_code)
VALUES (33333333-3333-4333-8333-333333333333, '123456')
IF NOT EXISTS
USING TTL 300;

-- UPDATE: USING precedes SET; IF goes at the end.
UPDATE demo.user_preferences_by_id
USING TTL 300
SET otp_code = '654321'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- DELETE: USING TIMESTAMP goes after the table name, before WHERE.
DELETE otp_code FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000000
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

The final `DELETE` uses a **hardcoded timestamp in the past** purely to illustrate syntax; if the existing value was written with a newer timestamp, that tombstone **will not win**, so `otp_code` may still be readable. Never use fixed timestamps like that to delete production data.

### Support matrix

| Statement | `USING TTL` | `USING TIMESTAMP` | Both options together | Can add an `IF` condition? |
| --- | --- | --- | --- | --- |
| Regular `INSERT` | Yes | Yes | Yes, joined by `AND` | `IF NOT EXISTS` works with TTL; not with custom timestamp |
| Regular `UPDATE` | Yes | Yes | Yes, joined by `AND` | `IF EXISTS` or `IF condition` works with TTL; not with custom timestamp |
| `DELETE` | **No** | Yes | **No**, because DELETE has no TTL | `IF EXISTS`/`IF condition` where supported, **not** with custom timestamp |
| Writes on `counter` tables | **No** | **No** | **No** | Does not support LWT conditions like regular columns |

LWTs and counters have additional limits beyond this summary table. **Do not assume that because `USING` exists, every option works with every operation.**

### Two options in one statement: use AND

```sql
UPDATE demo.user_preferences_by_id
USING TTL 600 AND TIMESTAMP 1700000000000001
SET otp_code = '246810'
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

In `UPDATE`, `USING` goes **before `SET`**. You can write `USING TIMESTAMP ... AND TTL ...` instead of `USING TTL ... AND TIMESTAMP ...`; in both forms, `AND` joins write parameters rather than row filter predicates.

To avoid mixing up types of `AND`, distinguish:

- `USING TTL ... AND TIMESTAMP ...`: combines **write parameters**.
- `WHERE key1 = ... AND key2 = ...`: combines **key components / lookup predicates**.
- `IF col1 = ... AND col2 = ...`: combines **LWT conditions** when supported by the statement and CQL version.

## 3. USING TIMESTAMP: version reconciliation time, not a data column

Cassandra stores a *write timestamp* per cell to decide the winning version when multiple writes target the same data location. Behavior is commonly described as **timestamp-based last-write-wins**, rather than strictly following Java call order or coordinator arrival time.

`USING TIMESTAMP` lets the client **override the automatic timestamp** with a specific value:

```sql
-- Dedicated UUID to illustrate manual timestamps.
INSERT INTO demo.user_preferences_by_id (
    user_id, preferred_locale, account_state
)
VALUES (
    22222222-2222-4222-8222-222222222222,
    'vi-VN',
    'ACTIVE'
)
USING TIMESTAMP 1700000000000000;

UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000002
SET preferred_locale = 'en-US'
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

For the same `preferred_locale` cell, timestamp `1700000000000002` is greater than `1700000000000000`, so `'en-US'` wins assuming no other mutations. If you then write:

```sql
UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000001
SET preferred_locale = 'ja-JP'
WHERE user_id = 22222222-2222-4222-8222-222222222222;

SELECT preferred_locale, WRITETIME(preferred_locale)
FROM demo.user_preferences_by_id
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

then `'ja-JP'` **does not beat** `'en-US'` because timestamp `...0001` is smaller than `...0002`, even though the statement ran later. This is the core behavior of write timestamps.

### Units matter critically

| Concept | Unit | Example |
| --- | --- | --- |
| `USING TIMESTAMP` | **Microseconds** since Unix epoch | `1700000000000000` |
| `WRITETIME(column)` | **Microseconds** since Unix epoch | `1700000000000002` |
| Java `Instant.toEpochMilli()` | **Milliseconds** since Unix epoch | `1700000000000` |
| Java `Instant.getEpochSecond()` | **Seconds** since Unix epoch | `1700000000` |
| CQL `timestamp` **type** (date–time value) | Point-in-time representation; stored precision is milliseconds | `'2026-11-21 10:00:00+0700'` |

Confusing `Instant.toEpochMilli()` with the microseconds expected by `USING TIMESTAMP` produces a timestamp **1,000 times smaller**, far in the past; the mutation may fail to beat existing data. Conversely, multiplying or shifting units incorrectly can produce a timestamp far in the future, preventing normal future writes from overriding that value for a long time.

Unless you have a compelling requirement to synchronize version timestamps from an external system, **prefer Cassandra/driver automatic timestamp generation** instead of inventing manual timestamps for every write.

### Two columns in the same row can carry different write timestamps

```sql
UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000003
SET phone = '0911111111'
WHERE user_id = 22222222-2222-4222-8222-222222222222;

SELECT preferred_locale,
       WRITETIME(preferred_locale),
       phone,
       WRITETIME(phone)
FROM demo.user_preferences_by_id
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

Updating `phone` does not refresh the timestamp of `preferred_locale`. Regular upserts write only the mentioned columns. This also explains why an application-maintained `modified_at timestamp` column is **not** the cell reconciliation timestamp: to update `modified_at`, the application must write it explicitly like any regular column.

### Deleting with TIMESTAMP and the risk of "deleted" data remaining visible

```sql
-- Older timestamp than the phone value above: tombstone does not win.
DELETE phone FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000002
WHERE user_id = 22222222-2222-4222-8222-222222222222;

-- Higher timestamp: tombstone can shadow the old phone version.
DELETE phone FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000004
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

Tombstones also carry timestamps to shadow older versions. Therefore, a syntactically successful `DELETE` does not always mean "every version is erased regardless of timestamp"; improper manual timestamps can produce surprising read results.

Equal timestamps follow detailed tie-breaking rules (involving tombstones and value comparison); **never build business logic that relies on equal-timestamp tie-breaking**.

## 4. USING TTL: how long do written values live?

`USING TTL n` sets a lifespan of `n` **seconds** on the values written by that mutation, rather than setting a default lifespan on the entire row or partition.

Example storing an OTP valid for 5 minutes:

```sql
UPDATE demo.user_preferences_by_id
USING TTL 300
SET otp_code = '835194'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

SELECT otp_code, TTL(otp_code), WRITETIME(otp_code)
FROM demo.user_preferences_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Immediately after a successful write, `TTL(otp_code)` typically shows the remaining seconds (near 300 and counting down). After expiration, the value is no longer returned as live data: `otp_code` reads back as `null`.

### TTL applies only to the columns just written

Consider another mutation on the same row:

```sql
UPDATE demo.user_preferences_by_id
USING TTL 120
SET preferred_locale = 'en-US',
    phone = '0900000022'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Here, `preferred_locale` and `phone` are written with a 120-second TTL. `display_name`, `account_state`, `revision`, and `otp_code` **are absent from `SET`**, so this mutation applies no new TTL to them.

If `otp_code` already had a 300-second TTL from the previous statement, the OTP's TTL clock **keeps ticking down**. Editing `phone` does not extend the OTP. Likewise, if only one column in a table has a TTL, do not assume the entire row vanishes when that column expires.

### INSERT with TTL

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, otp_code
)
VALUES (
    44444444-4444-4444-8444-444444444444,
    '482731'
)
USING TTL 180;
```

An `INSERT` with TTL likewise writes only the listed values. If `user_id` already existed with `display_name` or `phone`, those two columns are neither deleted nor given a 180-second TTL because they are not part of this mutation.

**Primary keys do not expire as independent field values.** TTL applies to the written cells/markers in Cassandra's storage model; a row whose only data had a TTL may stop appearing in results once those values and associated liveness metadata expire.

### Overwriting a column that has a TTL

Suppose an `otp_code` cell has 100 seconds remaining. The application overwrites that column:

```sql
UPDATE demo.user_preferences_by_id
USING TTL 600
SET otp_code = '999888'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

If the new mutation wins by timestamp, `'999888'` takes its lifespan from the **new write**, rather than inheriting the 100 seconds left on the previous value. This is why retries after timeouts must consider TTL: re-sending the same OTP with a new timestamp/TTL can extend its lifetime.

### USING TTL 0

`USING TTL 0` is typically used to **rewrite a value with no TTL**, removing the expiration of an older version when the new mutation wins:

```sql
UPDATE demo.user_preferences_by_id
USING TTL 0
SET otp_code = 'LONG-LIVED-CODE'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

On a table without a default TTL, `TTL(otp_code)` on the new value typically returns `null`. In practice, `otp_code` is sensitive data that should expire, so this statement **illustrates syntax only**; never use TTL 0 for production verification codes.

**Watch table settings:** `default_time_to_live` can assign a TTL to written values whenever a statement omits an explicit TTL. Explicit TTLs and clearing expiration must be evaluated against your deployed Cassandra version and table configuration; avoid assuming "no `USING TTL`" always means permanent storage.

### Units, valid values, and storage limits

- TTL is measured in **seconds**, not milliseconds or microseconds.
- TTL must satisfy Cassandra's bounds; `TTL 300` means five minutes, not 300 milliseconds.
- A negative TTL is not a valid way to force immediate expiration.
- Expired data is handled through tombstones and compaction; it does **not** mean old bytes are physically erased at the exact second of expiration.
- Systems and Cassandra versions have maximum representable expiration limits; excessively large TTLs can hit overflow handling policies, so choose sensible TTLs and check configuration for very long retention.

## 5. Combining TIMESTAMP and TTL on the same mutation

For regular `INSERT` or `UPDATE` statements on eligible columns, CQL allows specifying **both parameters**:

```sql
-- INSERT: USING goes after VALUES.
INSERT INTO demo.user_preferences_by_id (
    user_id, otp_code
)
VALUES (
    55555555-5555-4555-8555-555555555555,
    '752901'
)
USING TTL 900 AND TIMESTAMP 1700000000000010;

-- UPDATE: USING goes before SET.
UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000011 AND TTL 1200
SET otp_code = '752902'
WHERE user_id = 55555555-5555-4555-8555-555555555555;
```

The two options control **two independent dimensions**:

| Option | Question answered | Unit | Purpose |
| --- | --- | --- | --- |
| `TIMESTAMP 1700000000000011` | Is this version newer or older during reconciliation? | Microseconds since Unix epoch | Precedence among competing mutations |
| `TTL 1200` | How long does the written value live? | Seconds | Expiration of temporary data |

Do not mechanically calculate expiration time as "`USING TIMESTAMP` plus `TTL`." **An application-chosen write timestamp is not an absolute expiration clock setter.** TTL follows Cassandra's mutation lifetime mechanics during write processing; the two parameters serve separate roles.

### Behavior under concurrent writes

Suppose two mutations hit **the same `otp_code`** and both are accepted:

| Mutation | Write timestamp | TTL | Value |
| --- | ---: | ---: | --- |
| A | 100 | 600 seconds | `'CODE-A'` |
| B | 200 | 30 seconds | `'CODE-B'` |

When B wins by timestamp, the `otp_code` cell holds B's version with its corresponding lifetime. When B expires, **never assume A automatically reappears as a fallback**. Cassandra uses expiration/tombstone metadata to avoid resurrecting older versions replaced or shadowed by B.

A newer version with a shorter TTL is not a "temporary overlay" that lets Cassandra revert to an older version upon expiration. If business logic needs to restore a prior value, the application must explicitly model or write a new value.

### When should you use manual timestamps?

Consider manual timestamps only for clear consistency reasons, such as ingesting data from an external system with reliable version timestamps. Even then, enforce strict controls:

- Standardize on microseconds and a single time source.
- Never use timestamps far in the future.
- Never let an application supply timestamps lower than batches of already-written timestamps.
- Never arbitrarily mix timestamps from sources with differing clock skew.
- Never supply manual timestamps to LWTs; that combination is disallowed, not a way to force transaction ordering.

## 6. IF/LWT conditions: which combinations are allowed?

`IF NOT EXISTS`, `IF EXISTS`, and `IF column = value` turn a mutation into a **conditional operation** (*lightweight transaction*). Cassandra must verify current state via consensus rather than sending a plain upsert.

### 6.1. INSERT IF NOT EXISTS with TTL: allowed

Example creating a temporary code only if the key does not exist:

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, otp_code
)
VALUES (
    66666666-6666-4666-8666-666666666666,
    '301927'
)
IF NOT EXISTS
USING TTL 300;
```

Meaning:

1. Cassandra checks whether **no row exists** at the specified key.
2. If the condition holds, the mutation is applied with the TTL on the written data.
3. If the condition fails, no new mutation from this request is applied.
4. The result contains `[applied]`; the application must check `true`/`false`.

This **combines TTL with LWT**, not a user-specified timestamp with LWT.

**Design note:** if a table has multiple columns or TTL-expired data, "row existence" is a Cassandra liveness concept rather than merely bytes sitting in an old SSTable. Do not rely on the temporary existence of `otp_code` as a substitute for permanent duplicate-account prevention; both problems need proper data modeling.

### 6.2. UPDATE IF EXISTS with TTL: allowed

```sql
UPDATE demo.user_preferences_by_id
USING TTL 180
SET otp_code = '902134'
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;
```

If the row exists when LWT evaluates the condition, the OTP is written with a 180-second TTL. If the row does not exist, `[applied] = false` and the statement does not create a sparse row like an unconditional `UPDATE` would.

### 6.3. UPDATE IF old-value condition with TTL: allowed

```sql
UPDATE demo.user_preferences_by_id
USING TTL 120
SET otp_code = '483721'
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF account_state = 'ACTIVE';
```

The intent is to issue a temporary verification code only for accounts still `ACTIVE`. `IF account_state = 'ACTIVE'` checks existing data, while `TTL 120` applies to the written `otp_code` if the LWT succeeds.

If you want to update multiple columns simultaneously while applying a **TTL to only one of them**, a single mutation with `USING TTL` is not the right expression: TTL applies to the values written in that mutation. When different lifetimes are needed, split mutations by column and design business atomicity/conditions explicitly.

### 6.4. INSERT/UPDATE with IF and custom TIMESTAMP: disallowed

The following statements are **intentionally invalid** to illustrate rejected combinations:

```sql
-- INVALID: LWT IF NOT EXISTS does not accept a custom USING TIMESTAMP.
INSERT INTO demo.user_preferences_by_id (user_id, otp_code)
VALUES (77777777-7777-4777-8777-777777777777, '111222')
IF NOT EXISTS
USING TIMESTAMP 1700000000000100;

-- INVALID: UPDATE IF EXISTS cannot combine with a client-specified timestamp.
UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000101
SET preferred_locale = 'en-US'
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;

-- INVALID: adding TTL does not make TIMESTAMP + IF valid.
UPDATE demo.user_preferences_by_id
USING TTL 300 AND TIMESTAMP 1700000000000102
SET otp_code = '555666'
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF account_state = 'ACTIVE';
```

Rule: **LWT manages timestamps/versions internally for consensus**; supplying a manual write timestamp is incompatible with conditional mutations. When you need both `IF` and TTL, **use only TTL**, without `USING TIMESTAMP`.

### Why doesn't SELECT followed by UPDATE replace IF?

Two concurrent clients:

```text
Client A: SELECT revision -> 1
Client B: SELECT revision -> 1
Client A: UPDATE revision = 2, locale = 'en-US'
Client B: UPDATE revision = 2, locale = 'fr-FR'
```

Without an `IF` condition, the mutations compete by timestamp and one update can be lost. If both send:

```sql
UPDATE demo.user_preferences_by_id
SET preferred_locale = 'en-US', revision = 2
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF revision = 1;
```

only the operation whose condition holds during LWT execution is applied. `USING TTL` could be added if you genuinely want the updated columns to have a TTL; however, most systems do **not** want `revision` to expire automatically, so the compare-and-set example above omits TTL.

### IF combinations have scope limits

LWT does not turn CQL into an arbitrary multi-row query/delete tool. You must still supply valid keys and obey condition constraints by mutation type, table schema, and Cassandra version. Be especially careful with collections/counters and statements affecting multiple rows or partitions: never assume `IF` makes every `USING` combination valid.

## 7. DELETE: TIMESTAMP only, no TTL

`DELETE` writes a **deletion marker (tombstone)** for the selected scope. TTL limits **the lifespan of newly written values**, so **DELETE does not support `USING TTL`**.

### DELETE with TIMESTAMP: valid without IF

```sql
DELETE phone FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000200
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

The tombstone carries the specified write timestamp. If this timestamp is lower than that of the live `phone` value, the tombstone will not shadow that value. For business-valid deletions, avoid arbitrary manual timestamps.

### Conditional DELETE: valid, but without manual TIMESTAMP

```sql
DELETE FROM demo.user_preferences_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;
```

This uses LWT to delete only if the row exists; the application reads `[applied]` to decide how to respond. Do not "optimize" it into:

```sql
-- INVALID: DELETE with IF does not accept a client-chosen timestamp.
DELETE FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000201
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;
```

### Two other invalid DELETE examples

```sql
-- INVALID: DELETE does not support USING TTL.
DELETE phone FROM demo.user_preferences_by_id
USING TTL 300
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- INVALID: DELETE does not support combining TTL and TIMESTAMP this way.
DELETE phone FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000202 AND TTL 300
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

**If you want a value to disappear automatically after 5 minutes, write that value with `USING TTL 300`**, not a DELETE with TTL. If you want immediate logical deletion, use an unconditional DELETE or an LWT DELETE as required by business rules.

### DELETE and TTL produce tombstones via two paths

| Need | CQL | When does it cease to be live data? |
| --- | --- | --- |
| Delete a column immediately | `DELETE col FROM ... WHERE ...` | When the tombstone wins and is observed on reads |
| Delete immediately with specific write timestamp | `DELETE col FROM ... USING TIMESTAMP ... WHERE ...` | When the marker beats older versions |
| Auto-expire a value | `UPDATE ... USING TTL 300 SET col = ...` | After the TTL expires (under proper system time) |
| Delete only if the row exists | `DELETE FROM ... WHERE ... IF EXISTS` | When the LWT condition holds and the marker is applied |

Tombstones play an essential role in distributed systems: replicas that missed a delete need a way to recognize stale data as invalid upon synchronization. `gc_grace_seconds`, repair, and compaction govern when markers and old data can be safely collected; they do **not** alter `USING TTL` or `USING TIMESTAMP` syntax.

## 8. Counters and special operations

Counters have specialized additive/subtractive semantics. Example:

```sql
CREATE TABLE demo.api_call_counts_by_day (
    service_name text,
    call_day date,
    total counter,
    PRIMARY KEY (service_name, call_day)
);

UPDATE demo.api_call_counts_by_day
SET total = total + 1
WHERE service_name = 'auth'
  AND call_day = '2026-11-21';
```

Do not add `USING TTL` or `USING TIMESTAMP` to counter increments, and do not use `IF` like conditional mutations on regular columns. Invalid examples:

```sql
-- INVALID: counters do not support TTL this way.
UPDATE demo.api_call_counts_by_day USING TTL 300
SET total = total + 1
WHERE service_name = 'auth'
  AND call_day = '2026-11-21';

-- INVALID: counters do not support manual timestamps.
UPDATE demo.api_call_counts_by_day USING TIMESTAMP 1700000000000000
SET total = total + 1
WHERE service_name = 'auth'
  AND call_day = '2026-11-21';
```

**Counters are not idempotent**: if the mutation reached replicas before the client timed out, retrying can increment a second time. Never use counters for "strictly-once" invariants in financial transactions or OTP codes.

Collection operations also have dedicated element-level update rules; do not mechanically apply every `USING` option to every `list`, `map`, or `set` edit without verifying the CQL forms supported by your Cassandra version. In particular, editing/deleting `list` elements by index or value can require *read-before-write* and exhibits different contention behavior than upserting a scalar column.

## 9. Timestamps, TTL, and multiple replicas: what happens under failures?

`USING TIMESTAMP` and `USING TTL` execute across a multi-replica system, not a single in-memory store. The coordinator dispatches a mutation to replicas responsible for the partition; consistency levels like `ONE`, `QUORUM`, and others govern how many replicas must acknowledge.

### 9.1. Timestamps determine the winner as replicas converge

Suppose replication factor is 3:

```text
Replica A: locale = 'en-US', write_ts = T2
Replica B: locale = 'en-US', write_ts = T2
Replica C: locale = 'vi-VN', write_ts = T1
T2 > T1
```

Replica C may temporarily lag on the new mutation. When reads, synchronization, or repair reconcile versions, write timestamps determine which version wins. `USING TIMESTAMP` lets you set relative ordering, yet **does not force all three replicas to receive the mutation immediately**.

### 9.2. TTL does not replace replica synchronization

A cell with a TTL expires per Cassandra's expiration mechanics so it is no longer treated as live. Expired data interacts with tombstones and compaction. If replicas fall out of sync, choosing appropriate consistency levels and running repair remain critical operational duties.

**Never lower `gc_grace_seconds` arbitrarily** just to purge TTL-expired values faster from disk. Deletion markers must be retained long enough that a previously disconnected replica cannot resurrect stale data; physical collection timing also depends on compaction and safety checks.

### 9.3. Consistency does not replace conditions

Writing at `QUORUM` with RF=3 typically requires at least two replicas to acknowledge within the quorum scope. Yet:

```sql
UPDATE demo.user_preferences_by_id
USING TTL 180
SET otp_code = '772211'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

is still an **unconditional upsert** even when issued at `QUORUM`. If OTPs may only be issued to `ACTIVE` accounts, use `IF account_state = 'ACTIVE'` and inspect `[applied]`. No standard replica acknowledgment level turns `UPDATE` into a business-state check.

### 9.4. Retries can extend TTLs or overwrite newer values

A classic scenario:

1. Client A sends `USING TTL 300 SET otp_code = 'A'`.
2. The coordinator or network times out, even though some replicas received the mutation.
3. Client B issues a new code `'B'`.
4. Client A automatically retries with a fresh timestamp or TTL.

If A's retried mutation wins by timestamp, it can **shadow code B**, and A's lifetime may reset from the new write. This is why idempotency must be evaluated by **business consequences**, not merely by the syntax of "assigning the same value."

When issuing time-limited OTP codes:

- Generate a stable verification ID/session bound to the issuance request.
- Manage issuing new codes and invalidating old ones at the application layer.
- Avoid blind retries on time-sensitive validity mutations.
- Use LWT when prior session/state checks are required; avoid custom timestamps with LWT.

## 10. Java Driver: binding TTL, timestamps, and handling LWT

These examples use **Apache Cassandra Java Driver 4.x**, assuming an active `CqlSession session`, valid `UUID userId`, and relevant imports. Prepared statements bind **values** instead of concatenating CQL strings from user input.

### 10.1. Binding TTL in seconds

```java
PreparedStatement updateOtp = session.prepare(
    "UPDATE demo.user_preferences_by_id " +
    "USING TTL :ttl_seconds " +
    "SET otp_code = :otp_code " +
    "WHERE user_id = :user_id"
);

BoundStatement writeOtp = updateOtp.boundStatementBuilder()
    .setUuid("user_id", userId)
    .setString("otp_code", "538291")
    .setInt("ttl_seconds", 300)  // 300 seconds = 5 minutes
    .build();

session.execute(writeOtp);
```

The argument `300` is in **seconds**. Never pass `Duration.ofMinutes(5).toMillis()` (`300_000`) to this marker, as that turns 5 minutes into several days. Validate API TTL bounds so temporary codes are not persisted far longer than intended.

### 10.2. Binding TIMESTAMP in microseconds

```java
PreparedStatement updateLocale = session.prepare(
    "UPDATE demo.user_preferences_by_id " +
    "USING TIMESTAMP :write_ts " +
    "SET preferred_locale = :locale " +
    "WHERE user_id = :user_id"
);

// Unit conversion illustration only; production should use the default
// driver/Cassandra timestamp unless there is a clear business reason.
java.time.Instant instant = java.time.Instant.now();
long micros = Math.addExact(
    Math.multiplyExact(instant.getEpochSecond(), 1_000_000L),
    instant.getNano() / 1_000L
);

BoundStatement writeLocale = updateLocale.boundStatementBuilder()
    .setUuid("user_id", userId)
    .setString("locale", "en-US")
    .setLong("write_ts", micros)
    .build();

session.execute(writeLocale);
```

This formula converts `Instant` into microseconds using seconds and nanoseconds; it illustrates **units only**. Generating timestamps across hosts with clock skew can still produce unintended write ordering. In ordinary applications, omit `USING TIMESTAMP` altogether.

### 10.3. Binding both TTL and TIMESTAMP in an unconditional UPDATE

```java
PreparedStatement updateWithBoth = session.prepare(
    "UPDATE demo.user_preferences_by_id " +
    "USING TTL :ttl_seconds AND TIMESTAMP :write_ts " +
    "SET otp_code = :otp_code " +
    "WHERE user_id = :user_id"
);

BoundStatement command = updateWithBoth.boundStatementBuilder()
    .setUuid("user_id", userId)
    .setInt("ttl_seconds", 600)
    .setLong("write_ts", micros)
    .setString("otp_code", "712408")
    .build();

session.execute(command);
```

This shows only **valid binding syntax** for a regular mutation. Do not run it on accounts that already carry future-dated timestamps or inside an LWT workflow; unify your system-wide timestamp policy before using this option.

### 10.4. LWT with TTL, without manual TIMESTAMP

```java
PreparedStatement conditionalOtp = session.prepare(
    "UPDATE demo.user_preferences_by_id " +
    "USING TTL :ttl_seconds " +
    "SET otp_code = :code " +
    "WHERE user_id = :user_id " +
    "IF account_state = :expected_state"
);

ResultSet result = session.execute(
    conditionalOtp.boundStatementBuilder()
        .setUuid("user_id", userId)
        .setInt("ttl_seconds", 120)
        .setString("code", "812306")
        .setString("expected_state", "ACTIVE")
        .build()
);

if (result.wasApplied()) {
    // Condition held; OTP was written with TTL.
} else {
    // Account is not in the expected state.
}
```

`ResultSet.wasApplied()` is how the driver reports whether the LWT condition applied. Never check only whether "`session.execute` threw no exception" to conclude that `IF` succeeded.

### 10.5. Reading TTL and write timestamp from CQL

```java
PreparedStatement inspect = session.prepare(
    "SELECT otp_code, TTL(otp_code) AS seconds_left, " +
    "WRITETIME(otp_code) AS write_ts " +
    "FROM demo.user_preferences_by_id WHERE user_id = ?"
);

Row row = session.execute(inspect.bind(userId)).one();
if (row != null) {
    String code = row.getString("otp_code");
    Integer remaining = row.isNull("seconds_left")
        ? null : row.getInt("seconds_left");
    Long timestampMicros = row.isNull("write_ts")
        ? null : row.getLong("write_ts");
    // Do not log real OTP codes; use only the necessary information.
}
```

`TTL(...)` can return `null` when the cell has no TTL or is no longer live. `WRITETIME(...)` returns the write timestamp of the observed cell; it is not a complete audit log of older versions or tombstones.

### 10.6. Idempotency and retry policies

The driver tracks statement idempotency metadata, yet marking a statement `idempotent` **does not add LWT conditions** or protect against every race:

- Setting a column to a fixed value is easier to retry than counter increments or list appends.
- With TTL, rewriting can extend expiration time.
- With newly generated automatic timestamps, a retry can beat a concurrent write.
- With LWT, `[applied]` and timeouts must be handled per business state.

Do not blindly auto-retry every network error simply because `USING TTL` or a high consistency level is set. For real OTP flows, favor dedicated issuance workflows and idempotency keys.

## 11. Hands-on lab: testing TTL, TIMESTAMP, and IF yourself

Run only in a test environment against `demo.user_preferences_by_id` created in section 1. Use separate UUIDs so results do not depend on earlier examples. The invalid-syntax statements in sections 6–8 are solely for error recognition and **do not** need to be executed.

### Step 1 — Create data without TTL and set TTL on one column

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, display_name, account_state
)
VALUES (
    88888888-8888-4888-8888-888888888888,
    'TTL Lab',
    'ACTIVE'
);

UPDATE demo.user_preferences_by_id
USING TTL 90
SET otp_code = 'TEMP-001'
WHERE user_id = 88888888-8888-4888-8888-888888888888;

SELECT display_name, account_state, otp_code,
       TTL(otp_code), TTL(display_name)
FROM demo.user_preferences_by_id
WHERE user_id = 88888888-8888-4888-8888-888888888888;
```

**Prediction:** `otp_code` has a remaining TTL near 90 seconds, whereas `display_name` has no TTL in this example's default schema. Not every column in the row turns into expiring data just because one column has a TTL.

### Step 2 — Writing another column does not extend the code

```sql
UPDATE demo.user_preferences_by_id
SET preferred_locale = 'en-US'
WHERE user_id = 88888888-8888-4888-8888-888888888888;

SELECT preferred_locale, otp_code, TTL(otp_code)
FROM demo.user_preferences_by_id
WHERE user_id = 88888888-8888-4888-8888-888888888888;
```

**Prediction:** `preferred_locale = 'en-US'`. The OTP's TTL **does not reset to 90 seconds** just because a new mutation updated `preferred_locale`.

### Step 3 — Rewriting OTP with a new TTL

```sql
UPDATE demo.user_preferences_by_id
USING TTL 180
SET otp_code = 'TEMP-002'
WHERE user_id = 88888888-8888-4888-8888-888888888888;

SELECT otp_code, TTL(otp_code)
FROM demo.user_preferences_by_id
WHERE user_id = 88888888-8888-4888-8888-888888888888;
```

**Prediction:** the new OTP has a TTL near 180 seconds right after writing. This is a **new version**, not merely renaming a TTL counter.

### Step 4 — Observing TTL 0

```sql
UPDATE demo.user_preferences_by_id
USING TTL 0
SET otp_code = 'NO-EXPIRY-LAB'
WHERE user_id = 88888888-8888-4888-8888-888888888888;

SELECT otp_code, TTL(otp_code)
FROM demo.user_preferences_by_id
WHERE user_id = 88888888-8888-4888-8888-888888888888;
```

**Prediction:** on a table with no default TTL, the new value no longer has a TTL, so `TTL(otp_code)` typically returns `null`. Use this illustrative code only in the lab: real OTPs should never be stored indefinitely.

### Step 5 — Comparing two custom write timestamps

Create a **brand-new key**, and use manual timestamps only on this key:

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, preferred_locale
)
VALUES (
    99999999-9999-4999-8999-999999999999,
    'vi-VN'
)
USING TIMESTAMP 1700000000000001;

UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000003
SET preferred_locale = 'en-US'
WHERE user_id = 99999999-9999-4999-8999-999999999999;

-- Sent later but lower timestamp: does not win.
UPDATE demo.user_preferences_by_id
USING TIMESTAMP 1700000000000002
SET preferred_locale = 'ja-JP'
WHERE user_id = 99999999-9999-4999-8999-999999999999;

SELECT preferred_locale, WRITETIME(preferred_locale)
FROM demo.user_preferences_by_id
WHERE user_id = 99999999-9999-4999-8999-999999999999;
```

**Prediction:** the value is `'en-US'` with write timestamp `1700000000000003`. Execution order does not override timestamp reconciliation rules.

### Step 6 — DELETE with older and newer timestamps

On the same lab key `9999...`, test two deletion markers:

```sql
-- Tombstone with a lower timestamp than the live value:
DELETE preferred_locale FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000002
WHERE user_id = 99999999-9999-4999-8999-999999999999;

SELECT preferred_locale
FROM demo.user_preferences_by_id
WHERE user_id = 99999999-9999-4999-8999-999999999999;

-- Newer tombstone:
DELETE preferred_locale FROM demo.user_preferences_by_id
USING TIMESTAMP 1700000000000004
WHERE user_id = 99999999-9999-4999-8999-999999999999;

SELECT preferred_locale
FROM demo.user_preferences_by_id
WHERE user_id = 99999999-9999-4999-8999-999999999999;
```

**Prediction:** tombstone `...0002` fails to shadow version `...0003`, whereas tombstone `...0004` shadows it. The final query may return no row (if no live values or row markers remain) or `null` for the deleted column; **the key point to verify is that `preferred_locale` no longer holds the live value `'en-US'`**.

### Step 7 — Combining TTL and TIMESTAMP in a regular INSERT

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, otp_code
)
VALUES (
    cccccccc-cccc-4ccc-8ccc-cccccccccccc,
    'COMBINED'
)
USING TIMESTAMP 1700000000000010 AND TTL 120;

SELECT otp_code, WRITETIME(otp_code), TTL(otp_code)
FROM demo.user_preferences_by_id
WHERE user_id = cccccccc-cccc-4ccc-8ccc-cccccccccccc;
```

**Prediction:** `WRITETIME(otp_code)` equals the specified microsecond timestamp; `TTL(otp_code)` counts down from near 120 seconds. Both numbers serve **two independent purposes**.

### Step 8 — TTL with conditional LWT

```sql
INSERT INTO demo.user_preferences_by_id (
    user_id, display_name, account_state
)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    'Conditional Lab',
    'ACTIVE'
);

UPDATE demo.user_preferences_by_id
USING TTL 60
SET otp_code = 'IF-ACTIVE'
WHERE user_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
IF account_state = 'ACTIVE';
```

**Prediction:** when the condition holds, `[applied] = true` and the OTP gets a 60-second TTL. Next, modify the state and retry:

```sql
UPDATE demo.user_preferences_by_id
SET account_state = 'LOCKED'
WHERE user_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

UPDATE demo.user_preferences_by_id
USING TTL 60
SET otp_code = 'SHOULD-NOT-APPLY'
WHERE user_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
IF account_state = 'ACTIVE';
```

**Prediction:** the final statement returns `[applied] = false`; no new code is written because the state is no longer `ACTIVE`. **TTL + IF** is valid, whereas **custom TIMESTAMP + IF** is not.

### Test summary table

| Test | What to observe |
| --- | --- |
| Write OTP with TTL 90 | Only the written column receives TTL |
| Write `preferred_locale` while OTP has TTL | Does not extend OTP |
| Rewrite OTP with TTL 180 | New version's TTL changes |
| `USING TTL 0` | Clears expiration on the newly written cell in the lab table |
| Write timestamp `...0003` then `...0002` | Higher-timestamp version wins |
| Delete with tombstone `...0002` then `...0004` | Tombstone timestamp determines whether older data is shadowed |
| INSERT with TTL and TIMESTAMP | Both parameters apply, in two different units |
| UPDATE TTL with `IF account_state` | Must check `[applied]` from LWT |

## 12. Common errors and fixes

| Error | Why it is wrong | Fix |
| --- | --- | --- |
| `UPDATE ... SET ... USING TTL 300 WHERE ...` | In UPDATE, `USING` precedes **`SET`** | `UPDATE table USING TTL 300 SET ... WHERE ...` |
| `INSERT ... VALUES (...) USING TTL ... IF NOT EXISTS` | In INSERT, `IF NOT EXISTS` precedes **`USING`** | `INSERT ... VALUES (...) IF NOT EXISTS USING TTL ...` |
| `DELETE ... USING TTL 300 WHERE ...` | DELETE does not support TTL | Write the value with TTL to auto-expire, or use DELETE to delete |
| `UPDATE ... USING TIMESTAMP ... IF EXISTS` | LWT does not accept custom timestamps | Omit `USING TIMESTAMP` and let LWT manage timestamps |
| `INSERT ... IF NOT EXISTS USING TTL ... AND TIMESTAMP ...` | Manual timestamp inside a conditional mutation | Keep only TTL or drop the condition per requirements |
| Passing Java `toEpochMilli()` to `USING TIMESTAMP` | Milliseconds differ from microseconds | Convert units properly or avoid manual timestamps |
| Passing `300000` for a 5-minute TTL | TTL is in seconds | Pass `300` |
| Believing one column's TTL is a row-wide TTL | TTL applies to written values | Specify the right columns or design retention |
| Believing rewriting the same OTP after timeout has no effect | TTL/timestamp can be reset | Design idempotency and timeout handling |
| Using timestamps far in the future | Later mutations have lower timestamps and lose | Do not fabricate arbitrary timestamps; control time sources |
| Mixing counters with TTL/TIMESTAMP/LWT | Counters have dedicated semantics | Use counter tables and add/subtract per rules |
| Thinking `QUORUM` implies `IF` | Consistency is not a business condition | Write `IF` and check `[applied]` |

### Self-check questions

1. **Do `USING TIMESTAMP` and `USING TTL` share the same unit?** No. TIMESTAMP uses microseconds since the Unix epoch; TTL uses seconds.
2. **Can you write `UPDATE ... USING TTL 120 AND TIMESTAMP ...`?** Yes, on supported regular mutations without `IF`.
3. **Can you write `UPDATE ... USING TTL 120 ... IF EXISTS`?** Yes. That is an LWT mutation with a TTL.
4. **Can you add `TIMESTAMP` to the statement in question 3?** No; custom timestamps are incompatible with LWT.
5. **Why doesn't DELETE have `USING TTL`?** DELETE writes a deletion marker; TTL sets the lifespan of written values.
6. **Does writing `phone` with a TTL cause `display_name` to expire?** No, as long as the name is not written in that mutation and has no separate TTL policy.
7. **Why can an UPDATE executed later still lose?** Its write timestamp is lower than the cell's existing version.
8. **When a value with a shorter TTL and higher timestamp expires, does the older version return automatically?** Never assume that; expiration/tombstone mechanics prevent resurrecting stale data.
9. **Does `IF NOT EXISTS` overwrite an existing row?** No; if unmet, `[applied] = false`.
10. **What must you watch out for when retrying an OTP after a timeout?** The prior mutation may already have applied, resetting the timestamp/TTL or racing with a newly issued code.

## 13. Design checklist and key takeaways

Before putting CQL statements with `USING` into a Java application, verify:

1. **Is this INSERT, UPDATE, or DELETE?** Place `USING` in the right position for each statement.
2. **Does the data need a lifespan or custom version ordering?** Use TTL for expiration and TIMESTAMP for reconciliation; never conflate them.
3. **Are the units right?** TTL is in seconds, write timestamps are in microseconds; never pass Java milliseconds directly.
4. **Is `IF` used?** On conditional mutations, use TTL when appropriate and **never** set a custom timestamp.
5. **Which columns are actually written?** TTL attaches only to values in the mutation; omitted/UNSET columns are neither extended nor deleted.
6. **Is data being deleted?** DELETE creates tombstones; never put `USING TTL` on DELETE.
7. **Are counters or special lists involved?** Check syntax limits, read-before-write behavior, and idempotency separately.
8. **Is there risk of clock skew, retries, or concurrent writes?** Design idempotency keys and LWT when protecting state rather than relying on custom timestamps to simulate transactions.
9. **Are consistency levels, repair, and compaction properly operated?** Timestamps and TTLs do not replace replica convergence or safe tombstone handling.
10. **Have you tested with an isolated key in a lab?** Observe `TTL(col)`, `WRITETIME(col)`, and `[applied]` before shipping to production.

**Takeaway:** `USING TIMESTAMP` answers **"which version wins?"** and `USING TTL` answers **"how long does the newly written value live?"** Regular `INSERT` and `UPDATE` statements can combine both via `AND`; `DELETE` accepts only timestamps and never TTL; `IF` mutations can use TTL but **never** manual write timestamps; counters have separate limits. Knowing this matrix helps you write valid CQL and maintain correctness across replicas, network failures, and Java applications.
