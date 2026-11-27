# Reading LWT Results via wasApplied and Associated Columns

> **Chapter:** Query Execution from Java  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — learning Apache Cassandra and the distributed wide-column model, partition keys, query-driven table design, read/write consistency, CQL, replication, compaction, repair, error handling, and Java application connectivity.

In Cassandra, a regular `INSERT` can overwrite an existing row. When an application needs **create only if absent** or **update only while the old value still holds**, CQL offers conditional operations such as `IF NOT EXISTS`, `IF EXISTS`, and `IF version = ?`. These are called **Lightweight Transactions (LWT)** or **compare-and-set (CAS)** and rely on the Paxos consensus protocol.

Unlike regular writes, an LWT returns a result row containing a special boolean column `[applied]`. Java Driver 4.x provides `ResultSet.wasApplied()` (or `AsyncResultSet.wasApplied()`) to read the conditional outcome. When CAS is not applied, the response **may include current column values of the row** to help explain the conflict.

Three outcomes must stay separate:

1. **APPLIED:** LWT returns `wasApplied() == true` — the condition passed and the write was applied at the requested consistency level.
2. **NOT_APPLIED:** LWT returns `wasApplied() == false` — a valid response arrived, yet the condition failed. This is a business outcome, **not an exception**.
3. **UNKNOWN/ERROR:** Request timeout, network failure, unavailable, or another error — no definitive outcome exists; **never conclude CAS was not applied**.

**Scope:** this lesson uses Apache Cassandra Java Driver **4.x** (aligned with API **4.19**) and Cassandra 4.x–5.x; Driver 3.x has different classes/APIs. Table outputs are illustrative examples, **not measured benchmark numbers**.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish regular mutations from LWT forms `INSERT IF NOT EXISTS`, `UPDATE IF ...`, and `UPDATE/DELETE IF EXISTS`.
2. Use `ResultSet.wasApplied()` with accurate semantics and understand why it **returns true even for non-LWTs**.
3. Read returned columns when a condition fails using `ColumnDefinitions.contains()`, `Row.isNull()`, and named getters.
4. Use `PreparedStatement`/`BoundStatement` and configure **regular consistency** and **serial consistency** separately.
5. Write sync/async Java code mapping APPLIED, NOT_APPLIED, and UNKNOWN to proper business outcomes.
6. Understand CAS partition scope without conflating LWTs with multi-partition SQL transactions.
7. Build a lab with competing writers to measure conflict rates, timeouts, p95/p99, and verify invariants.

## 2. What problem does LWT solve?

### 2.1. Upsert vs conditional insert

Consider an account state table:

~~~sql
CREATE TABLE lwt_lab.account_state (
    account_id uuid PRIMARY KEY,
    status text,
    version int,
    owner text,
    updated_at timestamp
);
~~~

This command:

~~~sql
INSERT INTO lwt_lab.account_state
    (account_id, status, version, owner)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'NEW', 1, 'worker-A'
);
~~~

is an **upsert**: Cassandra does not check whether the row already exists, and no `[applied]` LWT column is returned. To create only on first insert:

~~~sql
INSERT INTO lwt_lab.account_state
    (account_id, status, version, owner)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'NEW', 1, 'worker-A'
) IF NOT EXISTS;
~~~

If another writer already created the row, the statement returns `[applied] = false` instead of overwriting it.

### 2.2. Versioned UPDATE to prevent lost updates

~~~sql
UPDATE lwt_lab.account_state
SET status = 'ACTIVE',
    version = 2,
    updated_at = '2026-11-21T09:00:00Z'
WHERE account_id = 11111111-1111-4111-8111-111111111111
IF version = 1;
~~~

This means “write only if `version` is still 1”. If another writer already bumped `version` to 2, the `false` response typically includes the **current value of the `version` column**.

~~~mermaid
sequenceDiagram
    participant A as Writer A / Java
    participant B as Writer B / Java
    participant C as Cassandra replicas
    A->>C: UPDATE SET version=2 IF version=1
    B->>C: UPDATE SET version=2 IF version=1
    Note over C: CAS/Paxos arbitrates proposals
    C-->>A: [applied] true (example)
    C-->>B: [applied] false, version=2 (example)
~~~

This diagram **does not claim A always wins**. When two writers both propose with `expectedVersion = 1`, CAS prevents both from applying against state 1 when requests finish cleanly. Contention and timeouts still require dedicated handling.

### 2.3. When to use LWT

| Scenario | Suitable? | Explanation |
|---|---|---|
| Create a resource only once for a unique key | Maybe | `IF NOT EXISTS` guards that key |
| Optimistic locking on status/version | Maybe | `IF version = ?` checks the precondition |
| Delete only if `owner` still matches old value | Maybe | `DELETE ... IF owner = ?` |
| Bulk import millions of idempotent events | Usually unnecessary | LWT adds extra Paxos round trips |
| Enforce unique username when username is not the key | Insufficient | Must design a table keyed by username |
| Transfer balance atomically between two arbitrary partitions | Insufficient | No arbitrary multi-partition ACID transactions |

LWT protects a **partition-scoped invariant**; it does not replace data modeling or hot-partition avoidance.

## 3. The `[applied]` result and returned columns

### 3.1. Response contains a row and a boolean flag

For a conditional operation that receives a response:

~~~text
Successful LWT:
 [applied]
-----------
 True

Failed condition LWT:
 [applied] | ... relevant current columns ...
-----------
 False     | ...
~~~

Do not expect a `true` LWT to echo every column just written. Usually only `[applied]` is returned. If you must read back the written row for reconciliation, run a separate query or use values already known in the service.

### 3.2. Matrix by CQL form

| LWT | When true | When false | Interpretation |
|---|---|---|---|
| `INSERT ... IF NOT EXISTS` | Usually `[applied]` only | Flag plus **existing row values** | A row already exists for this key |
| `UPDATE ... IF version = ?` | Usually flag only | Flag plus current value of **condition column(s)** like `version` | Compare-and-set failed |
| `UPDATE ... IF status = ? AND version = ?` | Usually flag only | Compared columns, e.g. `status`, `version` | Concurrent modification occurred |
| `UPDATE ... IF EXISTS` | Usually flag only | Usually **flag only** | Row does not exist |
| `DELETE ... IF EXISTS` | Usually flag only | Usually **flag only** | No row to delete |
| `DELETE ... IF owner = ?` | Usually flag only | Flag plus current value of `owner` | Owner condition failed |

**Important:** exact returned columns depend on CQL, Cassandra version, and schema. Never hardcode an assumption that every `false` LWT returns the full row. Specifically, `UPDATE ... IF EXISTS` returning `false` typically **does not include `version`**.

### 3.3. Example duplicate `INSERT IF NOT EXISTS`

Suppose the row already has `status='NEW'`, `version=1`:

~~~text
 [applied] | account_id                            | status | version | owner
-----------+---------------------------------------+--------+---------+---------
 False     | 11111111-1111-4111-8111-111111111111  | NEW    | 1       | worker-A
~~~

Column order/grouping can vary; if `updated_at` in the schema was never written, its value is null. Java code must **read by column name**, never `getInt(1)`, because position 1 might be a UUID.

### 3.4. Example failed conditional UPDATE

If `version` is already 2 while the request asks for `IF version=1`:

~~~text
 [applied] | version
-----------+---------
 False     | 2
~~~

The value `2` was observed when CAS evaluated the condition; it **does not promise to stay 2**. Another writer may advance `version` to 3 right after the response is sent.

### 3.5. Should you read `[applied]` with `Row.getBoolean`?

Both are possible:

~~~java
ResultSet rs = session.execute(conditionalStatement);
boolean applied = rs.wasApplied(); // PREFERRED
Row first = rs.one();              // still readable because wasApplied does not consume
if (first != null) {
    boolean flag = first.getBoolean("[applied]");
}
~~~

`ResultSet.wasApplied()` **does not consume the row**; it inspects the flag on the next row. The dedicated method is cleaner and easier to read. Avoid naming any business column literally `"[applied]"` to prevent name collisions in responses on some CQL versions.

## 4. Pitfall: `wasApplied()` returns `true` for non-LWTs

Per the Java Driver 4.19 documentation:

- If the request is an LWT, `wasApplied()` reflects the server's `[applied]` boolean.
- If the request is **not** a conditional write, the method **always returns `true` by API convention**.
- For DDL with `IF NOT EXISTS` such as `CREATE TABLE IF NOT EXISTS`, Cassandra **does not** return an LWT `[applied]` column, so `wasApplied()` also returns `true`. It **does not prove** a new table was created.

~~~java
ResultSet normal = session.execute(
    "UPDATE lwt_lab.account_state SET status='NEW' " +
    "WHERE account_id=11111111-1111-4111-8111-111111111111");

// "true" here does NOT prove a CAS operation succeeded.
boolean misleading = normal.wasApplied(); // true for non-LWT
~~~

**Only use `wasApplied()` for business decisions in code where you know for certain you ran an `INSERT`/`UPDATE`/`DELETE` with an LWT `IF` clause.** Never use it to check whether `CREATE KEYSPACE` or `CREATE TABLE IF NOT EXISTS` created a new schema object.

## 5. Repeatable state-by-state CQL lab

### 5.1. Topology, keyspace, and table

Run in a **lab Cassandra cluster** with real DC `dc1`, three nodes, and RF=3. On a single-node cluster, adjust RF/CL to match topology rather than misinterpreting `Unavailable` errors as LWT bugs.

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

In `cqlsh`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lwt_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lwt_lab.account_state (
    account_id uuid PRIMARY KEY,
    status text,
    version int,
    owner text,
    updated_at timestamp
);
~~~

`IF NOT EXISTS` **does not alter an existing schema** if the keyspace/table already exists. Use `DESCRIBE KEYSPACE lwt_lab` and `DESCRIBE TABLE lwt_lab.account_state` to inspect. To reset the lab cleanly, use a new UUID or new keyspace—never delete production data by mistake.

### 5.2. `INSERT IF NOT EXISTS` twice

~~~sql
INSERT INTO lwt_lab.account_state
    (account_id, status, version, owner, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'NEW', 1, 'worker-A', '2026-11-21T09:00:00Z'
) IF NOT EXISTS;
~~~

When no row exists yet:

~~~text
 [applied]
-----------
 True
~~~

Run the **exact same command** again:

~~~text
 [applied] | account_id | status | version | owner | updated_at
-----------+------------+--------+---------+-------+-----------
 False     | ...        | NEW    | 1       | ...   | ...
~~~

The second run is a **valid CAS conflict**. Never log the full existing row in real schemas containing sensitive data.

### 5.3. Versioned UPDATE: first run and repeat

~~~sql
UPDATE lwt_lab.account_state
SET status='ACTIVE',
    version=2,
    updated_at='2026-11-21T09:05:00Z'
WHERE account_id=11111111-1111-4111-8111-111111111111
IF version=1;
~~~

When `version` is 1, `[applied]=true`. Running again once `version` is 2 returns `[applied]=false`, typically with `version=2`. Notice `updated_at` from `SET` does not necessarily appear in the failed response because it was not part of the `IF` condition.

### 5.4. `IF EXISTS` on present vs missing rows

~~~sql
UPDATE lwt_lab.account_state
SET owner='worker-B'
WHERE account_id=11111111-1111-4111-8111-111111111111
IF EXISTS;

UPDATE lwt_lab.account_state
SET owner='worker-B'
WHERE account_id=33333333-3333-4333-8333-333333333333
IF EXISTS;
~~~

The first is expected to return `true`; the second `false`. For a missing key, **usually only `[applied]` is returned**, without `owner` or `version`.

### 5.5. Conditional DELETE

~~~sql
DELETE FROM lwt_lab.account_state
WHERE account_id=11111111-1111-4111-8111-111111111111
IF version=2;

DELETE FROM lwt_lab.account_state
WHERE account_id=11111111-1111-4111-8111-111111111111
IF EXISTS;
~~~

With no other writers, the first returns `true` and the second returns `false`. **An applied DELETE does not mean bytes are immediately erased from disk**: tombstones, compaction, and repair govern physical reclamation.

### 5.6. Expected results table to record

| Test | Prior state | Expected result | Associated columns |
|---|---|---|---|
| Fresh insert | Row absent | True | Flag only |
| Duplicate insert | Row exists | False | Existing row values |
| Update with matching version | Version 1 | True | Flag only |
| Update with stale version | Version 2, IF 1 | False | Version 2 |
| Update IF EXISTS on missing key | Absent | False | Usually flag only |
| Delete IF matching version | Version 2 | True | Flag only |
| Second delete IF EXISTS | Already deleted | False | Usually flag only |

These are **conditional lab expectations**, not figures measured on a cluster in this text.

## 6. Synchronous Java: check `wasApplied()` then read returned columns

### 6.1. Preparing session, prepared statement, and consistency

Assume a reusable application `CqlSession session` configured with contact points, local DC, TLS, and auth. Driver 4.x examples use:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;
~~~

For LWTs, both consistency levels are set independently:

~~~java
// Illustrative fragment: ps was prepared with matching bind markers.
BoundStatement statement = ps.bind(/* values in order */)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);
~~~

`LOCAL_QUORUM` governs the regular write phase; `LOCAL_SERIAL` governs the serial/Paxos phase. Use only when RF/DC match. Changing CL never creates an LWT if the CQL lacks `IF`.

### 6.2. `INSERT IF NOT EXISTS`: `true` → CREATED, `false` → CONFLICT

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

void createIfAbsent(CqlSession session, UUID accountId) {
    PreparedStatement ps = session.prepare(
        "INSERT INTO lwt_lab.account_state " +
        "(account_id, status, version, owner) " +
        "VALUES (?, ?, ?, ?) IF NOT EXISTS");

    BoundStatement bs = ps.bind(accountId, "NEW", 1, "worker-A")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

    ResultSet rs = session.execute(bs);
    if (rs.wasApplied()) {
        System.out.println("CREATED");
        return;
    }

    // Condition failed because row already exists; read columns if present.
    Row current = rs.one();
    String currentStatus = null;
    Integer currentVersion = null;

    if (current != null) {
        if (current.getColumnDefinitions().contains("status")
                && !current.isNull("status")) {
            currentStatus = current.getString("status");
        }
        if (current.getColumnDefinitions().contains("version")
                && !current.isNull("version")) {
            currentVersion = current.getInt("version");
        }
    }

    // In production: return a conflict DTO; never log sensitive payloads/secrets.
    System.out.println("ALREADY_EXISTS; status=" + currentStatus
            + ", version=" + currentVersion);
}
~~~

Key strength: `wasApplied()` does not consume the row, so `rs.one()` can still read returned columns afterward. `ColumnDefinitions.contains("version")` checks column presence; `isNull` prevents treating null as `0`; `getInt`/`getString` read **by name**.

### 6.3. `UPDATE IF version`: reading the actual value on conflict

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

void updateStatusIfVersion(CqlSession session, UUID accountId,
                           String nextStatus, int expectedVersion) {
    PreparedStatement ps = session.prepare(
        "UPDATE lwt_lab.account_state " +
        "SET status = ?, version = ? " +
        "WHERE account_id = ? IF version = ?");

    int nextVersion = Math.addExact(expectedVersion, 1);
    BoundStatement bs = ps.bind(
            nextStatus, nextVersion, accountId, expectedVersion)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

    ResultSet rs = session.execute(bs);
    if (rs.wasApplied()) {
        System.out.println("CAS_APPLIED; nextVersion=" + nextVersion);
        return;
    }

    Row current = rs.one();
    Integer actualVersion = null;
    if (current != null
            && current.getColumnDefinitions().contains("version")
            && !current.isNull("version")) {
        actualVersion = current.getInt("version");
    }
    System.out.println("CAS_CONFLICT; observedVersion=" + actualVersion);
}
~~~

Bind order is **new status, new version, accountId, expectedVersion**. `actualVersion` is merely the value observed when CAS failed and can change immediately afterward. `null` means no reliable integer was returned in the response; never coerce it to `0`.

### 6.4. `IF EXISTS` false: do not access `version` unconditionally

~~~java
PreparedStatement ps = session.prepare(
    "UPDATE lwt_lab.account_state SET owner = ? " +
    "WHERE account_id = ? IF EXISTS");

ResultSet rs = session.execute(ps.bind("worker-B", accountId));
if (!rs.wasApplied()) {
    // Usually only [applied] is present; version is NOT guaranteed to exist.
    System.out.println("NOT_FOUND");
}
~~~

This condensed snippet uses execution-profile consistency defaults; in production code, ensure regular and serial CLs are configured explicitly per policy.

## 7. Variable response columns: avoiding null and missing-field errors

### 7.1. Distinguish a missing column from NULL

A shared helper may observe:

~~~text
INSERT ... IF NOT EXISTS, false       -> may include status/version/owner
UPDATE ... IF version = ?, false     -> usually includes version
UPDATE ... IF EXISTS, false         -> usually includes [applied] only
~~~

Unconditionally calling `rs.one().getInt("version")` throws on the `IF EXISTS` false path because `version` **is not in the result schema**. Even when the column is present and null, never silently treat null as version `0`.

### 7.2. Java helper returning `Optional`

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.Optional;

Optional<Integer> optionalInt(Row row, String column) {
    if (row == null
            || !row.getColumnDefinitions().contains(column)
            || row.isNull(column)) {
        return Optional.empty();
    }
    return Optional.of(row.getInt(column));
}
~~~

`Optional.empty()` solely means **the response carried no usable integer value**, not that `actualVersion = 0` or that no row exists in Cassandra.

### 7.3. `[applied]` is response metadata, not schema data

`[applied]` is a **synthetic result column from a conditional operation**. It is not a persisted column in `account_state`. Never design `SELECT "[applied]" FROM ...` expecting to query transaction history.

### 7.4. A `false` + returned version cannot replace a subsequent CAS

If another writer bumped version from 2 to 3 right after the response, issuing an **unconditional UPDATE** based on observed version 2 will clobber the newer state. When retrying:

1. Verify business semantics allow retrying.
2. Recompute the proposal from the newer state or return a conflict.
3. Execute **another CAS**, never dropping the condition.
4. Cap retry attempts, apply backoff, and monitor contention.

## 8. Asynchronous Java: `AsyncResultSet.wasApplied()`

### 8.1. Non-blocking request handling

Java Driver 4.x provides `CqlSession.executeAsync(statement)` returning `CompletionStage<AsyncResultSet>`. When the response arrives, `AsyncResultSet.wasApplied()` reads the same LWT flag, and the row can be inspected from the current page:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

CompletionStage<String> createIfAbsentAsync(
        CqlSession session, UUID accountId) {
    PreparedStatement ps = session.prepare(
        "INSERT INTO lwt_lab.account_state " +
        "(account_id, status, version, owner) " +
        "VALUES (?, ?, ?, ?) IF NOT EXISTS");

    BoundStatement bs = ps.bind(accountId, "NEW", 1, "worker-A")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

    return session.executeAsync(bs).thenApply(rs -> {
        if (rs.wasApplied()) {
            return "CREATED";
        }
        Row current = rs.one();
        if (current != null
                && current.getColumnDefinitions().contains("version")
                && !current.isNull("version")) {
            return "CONFLICT_VERSION_" + current.getInt("version");
        }
        return "CONFLICT";
    });
}
~~~

A single LWT normally returns **one response row**, so `fetchNextPage()` for millions of pages is unnecessary. `wasApplied()` **does not consume** the row; `one()` yields the current row. Inside `thenApply`, never run blocking queries, `Thread.sleep`, or heavy CPU work on the driver completion thread.

### 8.2. Exceptional completion is not CAS `false`

~~~text
CompletionStage completes normally:
    rs.wasApplied() == true  -> APPLIED
    rs.wasApplied() == false -> NOT_APPLIED / CAS_CONFLICT

CompletionStage completes exceptionally:
    timeout / unavailable / connection / invalid query / ...
    -> classify as ERROR or UNKNOWN, never treat as false
~~~

**Wrong counter-example:**

~~~java
// DO NOT DO THIS:
// return session.executeAsync(bs)
//     .exceptionally(error -> fakeNotAppliedResult);
~~~

That snippet converts a **request failure** into a **conditional `false`**. If the server committed yet the client lost the reply, this bug can re-create resources, emit duplicate events, or delete the wrong data. Keep exceptions on a separate path, attach a correlation/request ID, and run business reconciliation.

### 8.3. What do Mapper and Spring Data return?

Java Driver Mapper 4.x supports DAO methods returning `boolean`/`Boolean` from `@Update(ifExists = true)`, which the driver maps from `ResultSet.wasApplied()`. When you also need condition columns on `false`, declare `ResultSet`/`AsyncResultSet` as the return type via the Mapper API instead of returning only a boolean.

~~~java
// Conceptual sketch from Apache Java Driver Mapper @Update:
// @Update(ifExists = true)
// boolean updateIfExists(MyEntity row);
//
// @Update(customIfClause = "status = :expectedStatus")
// ResultSet updateIfStatusMatches(MyEntity row, String expectedStatus);
~~~

This is an **annotation sketch**, not a standalone compilable interface: it needs concrete entity/DAO annotations and mapping. With Spring Data Cassandra, repository methods may transform results further. If the app needs both `[applied]` and current values, design an explicit outcome DTO or call the Java Driver directly for critical CAS operations.

## 9. Regular consistency and serial consistency

### 9.1. Two consistency phases

LWT uses Paxos for the **conditional/serial phase**, while regular consistency governs data-write ACKs per Cassandra mechanics. Driver 4.x exposes two distinct setters:

~~~java
BoundStatement bs = ps.bind(/* matching bind markers */)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
~~~

| Attribute | Effect | Do not misunderstand as |
|---|---|---|
| `LOCAL_SERIAL` | Serial phase/quorum **local to the relevant DC** | Equivalent to `SERIAL` across multi-DC |
| `SERIAL` | Serial/Paxos phase spanning broader replicas per topology | Arbitrary multi-partition transactions |
| `LOCAL_QUORUM` | Response requirement for regular write in local DC | Performing CAS when CQL has no `IF` |
| `QUORUM` | Quorum per RF/replica placement | An alternative way to write `SERIAL` |

In multi-DC clusters where invariants must hold **globally** (two regions can update the same key concurrently), carefully analyze `SERIAL` vs `LOCAL_SERIAL`, application DC routing, and failure modes. Never pick `LOCAL_SERIAL` purely for lower RTT if global uniqueness is required.

### 9.2. At what unit does LWT operate?

Cassandra LWT/Paxos operates around a **partition**. It protects a single key/partition designed by the application, and **never creates**:

- Referential integrity between two tables in different partitions.
- Arbitrary unique constraints on a non-partition-key column.
- Cross-partition SQL-style ACID transfers.
- Atomic publishing to Kafka, email, or payment providers.

For example, to enforce unique usernames on registration, create a **registry table keyed by username**:

~~~sql
CREATE TABLE lwt_lab.username_registry (
    username text PRIMARY KEY,
    account_id uuid
);

INSERT INTO lwt_lab.username_registry (username, account_id)
VALUES ('alice', 11111111-1111-4111-8111-111111111111)
IF NOT EXISTS;
~~~

CAS arbitrates competing claims on `username='alice'` within that table. Creating the corresponding `account_state` row in **another partition** is a separate step requiring workflows, idempotency, reconciliation, or an outbox/saga to handle partial failures.

### 9.3. Why does `QUORUM` alone still suffer lost updates?

Two writers reading `version=1` and sending two `UPDATE`s **without `IF`** at `QUORUM` can both receive ACKs, with the final value determined by timestamp conflict resolution. High CL **never** checks prior versions. For CAS, you must use `IF version = ?` with an appropriate serial consistency.

## 10. Handling APPLIED, NOT_APPLIED, and UNKNOWN in services

### 10.1. Business-meaningful mapping

| Outcome | Condition | Potential API response |
|---|---|---|
| **APPLIED** | LWT returns `true` | 201 Created / 200 OK / 204 depending on operation |
| **NOT_APPLIED** | LWT returns `false` | 409 Conflict, 412 Precondition Failed, or 404 for `IF EXISTS` |
| **UNKNOWN / ERROR** | Timeout / error without deterministic LWT flag | 503/504 / controlled retry / reconcile |

These HTTP codes are **suggestions**, not mandatory standards. The key distinction is that **CAS `false` is a valid response**, whereas a timeout is an error needing further verification.

### 10.2. What to do when `wasApplied` is `false`

1. Verify whether the query is `INSERT IF NOT EXISTS`, `UPDATE IF ...`, or `IF EXISTS`.
2. Read only **columns actually present** in the result; never assume a full row.
3. Optionally return `currentVersion`/`currentStatus` if the API contract allows, without leaking another user's `owner` or secrets.
4. When retrying due to a changed version, recompute the proposal and send a fresh CAS with bounded attempts and backoff.
5. If “already in desired state” counts as idempotent success, verify matching business identity/request ID before returning success.

### 10.3. Timeouts can happen after the mutation already applied

~~~text
Java -> Cassandra: UPDATE SET version=8 IF version=7
Paxos/replicas process the request to some stage
Network drops before the reply reaches the client
Java receives a timeout with unknown outcome

Retrying identically:
   May receive false, version=8
   even though the first request already bumped version from 7 to 8.
~~~

Therefore, **never treat a timeout as a rollback or as CAS `false`**. For critical operations:

- Attach an idempotency key, operation ID, or business marker persisted at matching consistency.
- After an unknown outcome, read back state at an appropriate CL and **reconcile**, rather than blindly re-firing side effects.
- Never enable `setIdempotent(true)` mechanically on all CAS statements. A CAS may be idempotent in desired end state while **`wasApplied` differs between the two executions**, affecting API side effects.
- Enforce retry budgets, deadlines, backoff, and telemetry separating overload from business conflicts.

### 10.4. CAS `true` does not make external side effects atomic

Example:

~~~text
CAS true
  -> service calls email or payment gateway
  -> service crashes before recording completion
  -> request replay: CAS may return false
~~~

You cannot look at `wasApplied=false` on replay and conclude the earlier email/payment never happened. Use a **proper outbox, idempotent consumers, operation IDs, sagas, or compensations** as business rules require. Cassandra does not span a single transaction across external systems.

## 11. LWT performance, hot keys, and observability

### 11.1. Paxos has a cost

Compared to unconditional writes, CAS executes extra check/consensus rounds sensitive to quorum availability, network RTT, and single-partition contention. Never add `IF NOT EXISTS` to bulk imports just to feel “safer”.

| Load pattern | Risk | Mitigation |
|---|---|---|
| A few CAS ops/min, low contention | Cost is usually acceptable | Prepare statements and measure real SLOs |
| Many writers contending on one partition | Contention, CAS `false`, and p99 climb | Per-key queuing, limit writers, redesign workflow |
| Writers across multiple DCs | High serial RTT, topology-induced races | Design locality and pick serial CL deliberately |
| CAS returning wide existing rows on `false` | Network, privacy, and memory overhead | Keep registry rows slim with minimal version/status |
| Unbounded retry loops | Amplifies Paxos pressure on busy nodes | Retry budgets, backoff, idempotency/reconcile |

A hot partition stays hot even when LWT is “correct”. Token-aware routing avoids extra coordinator hops, yet it cannot add replicas for a single key.

### 11.2. Cluster and application observability

In the lab cluster:

~~~bash
nodetool status
nodetool tablestats lwt_lab.account_state
nodetool tpstats
nodetool compactionstats
~~~

Combine Cassandra metrics for CAS/Paxos contention, prepare/propose latency, read/write latency, errors, and request latency. **Exact JMX/exporter metric names vary by Cassandra version**; verify actual exported metrics rather than assuming fixed names exist everywhere.

The Java app should record:

- Counts of `APPLIED`, `NOT_APPLIED`, and `UNKNOWN/TIMEOUT` split by query type.
- CAS latency p50/p95/p99 and total request duration, separated from unconditional `SELECT`s.
- Retry counts, contention, coordinator/replica errors, and TLS/network failures.
- Hot-key/rate-limit counters under **anonymized** labels, never logging raw account IDs or sensitive row values.
- CPU/network/disk/compaction/repair and replica Up/Down counts in the DCs used for CL.

Normal CAS `false` from version mismatch **is not automatically an infra error**; however, a sudden jump in conflict rate can point to competing writers, versioning bugs, or a hotspot.

## 12. Test matrix and two-writer lab

### 12.1. Functional tests

| Case | Initial state | Expected outcome | What to verify |
|---|---|---|---|
| First insert | Empty key | True | Do not assume full row returned |
| Duplicate insert | Row exists | False | Read existing columns if present |
| Update matching version | Version 1 | True | Do not expect new version in result |
| Update stale version | Version 2, IF 1 | False | Version 2 in condition column |
| `UPDATE IF EXISTS` on missing key | No row | False | Usually no `version` column |
| `DELETE IF` owner mismatch | Different owner | False | `owner` may be returned |
| Mutation without `IF` | Non-LWT | `wasApplied() == true` per API | No LWT `[applied]` column |
| Repeat DDL `IF NOT EXISTS` | Table exists | `wasApplied() == true` per API | Does not prove newly created |
| Timeout after possible commit | Lost reply | Exception/unknown | Never coerce to `false` |

### 12.2. Testing two competing writers

On a lab cluster with valid RF/CL:

1. Seed a row with `version=1`.
2. Two threads/services send `UPDATE ... IF version=1`, each trying to set a different `status`.
3. Use a barrier or coordinator so both fire nearly simultaneously; record `wasApplied`, exceptions, and latency.
4. When both receive valid responses, confirm at most one CAS applied against state `version=1`.
5. Read back final version/status at matching CL. If either request timed out, mark outcome **unknown** and verify state.
6. Repeat many times on **fresh keys or controlled resets**; never treat one sample as p99.

### 12.3. Controlled benchmark

| Variable | Suggested levels | Purpose |
|---|---|---|
| Writers/key | 1, 2, 8, 32 per lab capacity | Isolate hot-key contention |
| Partition count | One hot key; thousands of independent keys | Compare skew vs scalability |
| CL | Hold regular/serial CL constant per group | Avoid mixing different quorum rules |
| Data model | Small rows; test wide rows separately | `false` LWTs can return extra row data |
| Results | True/False/Unknown, p95/p99, errors | Correctness and performance must both pass |
| Noise | GC, streaming, repair, compaction | Never draw conclusions from one sample |

Never invent numbers; populate from lab runs:

| Writers/key | APPLIED/s | NOT_APPLIED/s | UNKNOWN/s | p95 (ms) | p99 (ms) | CPU/network |
|---|---:|---:|---:|---:|---:|---|
| 1 | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ |
| 2 | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ |
| 8 | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ |
| 32 | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ | _fill_ |

## 13. Common misconceptions

| Misconception | Why it is wrong | Right approach |
|---|---|---|
| “`wasApplied` true always means a new INSERT succeeded” | Non-LWT and DDL `IF NOT EXISTS` also return true per API | Use only on conditional DML results |
| “`wasApplied` false is an exception to retry immediately” | It is a normal CAS conflict | Return conflict or retry conditionally |
| “Timeout = false” | Mutation may have committed while ACK was lost | Treat as UNKNOWN and reconcile |
| “Every `false` LWT returns the full row” | `IF version` returns condition columns; `IF EXISTS` often returns flag only | Check `ColumnDefinitions.contains` |
| “`[applied]` is a table column” | It is a synthetic response column | Never map into persistent schema |
| “`getInt(version)` works anytime” | Column may be absent or null | Check presence and null first |
| “Version returned on CAS `false` is always latest” | Another writer may update right after the reply | Issue a new CAS, never an unconditional update |
| “`QUORUM` automatically prevents lost updates” | Write CL does not check prior versions | Use `IF version = ?` when needed |
| “`LOCAL_SERIAL = SERIAL` across all DCs” | Serial scopes differ | Design around cross-DC invariants |
| “LWT provides ACID transactions across any partitions” | Scope is primarily single-partition | Use registry tables, outbox/saga, reconciliation |
| “`PreparedStatement` makes multi-table workflows atomic” | Prepared only handles bind/parse/routing | Design explicit transaction boundaries |
| “Using LWT for every write is safer/better” | Paxos adds cost and contention | Apply only where invariants demand it |

## 14. Applied questions

**Exercise 1 — Non-LWT:** Calling an `UPDATE` without `IF` returns `wasApplied() == true`. Can you say “CAS succeeded”?

**Answer:** no. `true` is the API's default behavior for non-LWT statements; no condition check occurred.

**Exercise 2 — Version conflict:** `UPDATE ... IF version=3` fails, and the response carries `version=4`. What should you do?

**Answer:** report an optimistic concurrency conflict, optionally exposing `currentVersion=4` if allowed. Do not overwrite unconditionally; any retry must recompute against the new state.

**Exercise 3 — `IF EXISTS`:** `UPDATE ... IF EXISTS` returns `false`; `rs.one().getInt("version")` throws. Why?

**Answer:** no row exists, so the result typically contains only `[applied]` and lacks the `version` column.

**Exercise 4 — Repeated request:** `INSERT ... IF NOT EXISTS` returns `true` the first time and `false` the second time. Is that a network error?

**Answer:** no, it is a failed-condition outcome. If the repeat happened after a timeout, check request ID and business state to confirm whether the first attempt already completed.

**Exercise 5 — Timeout:** Client sends CAS incrementing version 7→8, response drops, and a retry gets `false`/version 8. Did the first request definitely fail?

**Answer:** no. The first request may have committed; reconcile.

**Exercise 6 — Unique username:** `accounts_by_id(id PRIMARY KEY, username)` uses `INSERT ... IF NOT EXISTS`. Can two different `id`s share the same `username`?

**Answer:** yes. The condition checks `id`, not a unique index on `username`. Use a registry table keyed by `username` with a compensating workflow.

**Exercise 7 — Async exception:** Is `exceptionally(error -> "CONFLICT")` appropriate when Cassandra loses quorum?

**Answer:** no. Quorum loss or timeouts are not CAS `false`; classify exceptions as error/unknown.

**Exercise 8 — Serial CL:** A developer sets `setConsistencyLevel(LOCAL_QUORUM)` without `IF version=?`. Does that prevent lost updates?

**Answer:** no. Regular CL does not perform compare-and-set; you need a conditional clause and matching serial CL.

### Completion checklist

- [ ] Understand that `INSERT`/`UPDATE` without `IF` are regular mutations with no LWT `[applied]` result.
- [ ] Call `ResultSet.wasApplied()`/`AsyncResultSet.wasApplied()` accurately on LWTs.
- [ ] Know that non-LWTs and conditional DDL return `wasApplied=true` by API convention.
- [ ] Distinguish APPLIED, NOT_APPLIED, and UNKNOWN/ERROR.
- [ ] Know `INSERT IF NOT EXISTS` returning `false` may include existing row columns.
- [ ] Know `UPDATE IF column` returning `false` may include compared columns, while `IF EXISTS` `false` usually returns flag only.
- [ ] Check `ColumnDefinitions.contains()` and `Row.isNull()` before calling primitive getters.
- [ ] Bind prepared statements in exact order using a long-lived `CqlSession`.
- [ ] Configure regular and serial consistency per RF/DC and invariants.
- [ ] Never treat LWT as arbitrary cross-partition ACID transactions.
- [ ] Implement retry budgets, backoff, and idempotency/reconciliation for unknown outcomes.
- [ ] Measure conflict rates, timeouts, p95/p99, and resources on a realistic cluster.

## 15. References

1. Apache Cassandra — [CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT IF NOT EXISTS`, `UPDATE IF`, `DELETE IF`, and Paxos cost.
2. Apache Cassandra Java Driver 4.19 — [ResultSet API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/ResultSet.html): `wasApplied()`, non-LWT behavior, and non-consuming semantics.
3. Apache Cassandra Java Driver 4.19 — [AsyncResultSet API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/AsyncResultSet.html): async CAS responses.
4. Apache Cassandra Java Driver 4.19 — [ColumnDefinitions API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/ColumnDefinitions.html): `contains()` and column metadata checks.
5. Apache Cassandra Java Driver 4.19 — [Statement API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/Statement.html): `setConsistencyLevel`, `setSerialConsistencyLevel`, and execution attributes.
6. Apache Cassandra Java Driver 4.19 — [Mapper @Update API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/mapper/annotations/Update.html): boolean return via `wasApplied` or raw result to read condition columns.
7. Apache Cassandra source docs — [Paxos/LWT design](https://github.com/apache/cassandra/blob/trunk/src/java/org/apache/cassandra/service/paxos/Paxos.md): consensus and coordinator contention.
8. DataStax CQL Reference — [INSERT IF NOT EXISTS response](https://docs.datastax.com/en/cql-oss/3.x/cql/cql_reference/cqlInsert.html): `false` may return existing row values.
