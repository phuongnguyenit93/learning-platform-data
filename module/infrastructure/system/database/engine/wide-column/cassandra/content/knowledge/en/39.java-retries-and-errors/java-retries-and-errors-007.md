# The Idempotent Flag and Responsibility for Determining Operation Semantics

> **Chapter:** Java Retries and Errors  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database. When Java executes CQL, you must consider partition keys, replication, consistency levels, last-write-wins write rules, compaction, repair, timeouts, and the coordinator/replica path.  
> **Focus:** The **idempotent** flag in Apache Cassandra Java Driver 4.x and the developer's responsibility when using retries or speculative execution.

## 1. Opening Scenario: After a Timeout, Does a Retry Create Two Effects?

Suppose a Java service writes an `OrderCreated` event to Cassandra. The driver receives **WriteTimeout**, without knowing how many replicas applied the mutation. Three possibilities exist: a subset of replicas wrote it, the server completed the write but the response was lost, or the request did not finish. **Never infer “not written” from a timeout.**

If Java generates a new UUID and retries, one logical event becomes two rows. If it retries a **counter increment**, the counter can increment twice. With **`INSERT IF NOT EXISTS`**, the first attempt may have returned `true` while its response dropped; the retry returns **`[applied]=false`** even though the first attempt created the row.

We must distinguish:

1. **CQL idempotency:** does re-applying the exact same operation preserve data state under required invariants?
2. **Java Driver idempotent flag:** statement metadata used by policies like retry and speculative execution; the flag **does not alter the nature** of the CQL operation.
3. **Business workflow idempotency:** repeating the same HTTP request to create an order, charge payment, emit an event, or send an email must not duplicate effects in violation of the contract.

**Responsibility for determining idempotency belongs to the data, API, and domain designers—not to driver auto-inference.**

### Objectives

- Understand idempotency conditions in Cassandra and the role of **`setIdempotent(true/false)`**.
- Classify `SELECT`, `INSERT`, `UPDATE`, `DELETE`, counters, collections, LWTs, TTLs, timestamps, and batches.
- Choose the flag based on semantics, never out of a wish for “fewer timeouts”.
- Design stable request IDs, retry budgets, backoff, and reconciliation after ambiguous outcomes.
- Use Java Driver 4.x with **`BoundStatement`**, **`PreparedStatement`**, consistency levels, and async execution.
- Test final data states, duplicate side effects, retries/faults, and cluster RF/DC conditions.
- Correlate hot partitions, compaction, repair, and observability under rising load.

> **Version note:** Examples use Java Driver **4.x** under the **`com.datastax.oss.driver.api`** namespace. Verify exact option names, policies, and APIs against your Cassandra, driver, and JDK versions. Run labs only on lab/staging clusters.

## 2. Defining Idempotency Across Three Layers

A state transformation \(f\) is idempotent if:

\[
f(f(s)) = f(s)
\]

Simply put: applying the same transformation twice leaves no different final state than applying it once.

~~~text
status := "PAID"
status := "PAID"
=> Looking solely at status, the final state stays "PAID".

total := total + 1
total := total + 1
=> Counter increases by 2; not idempotent.

events := events + ["paid"]
events := events + ["paid"]
=> List may receive two elements; not idempotent.
~~~

In Cassandra, you must also consider **timestamps, TTLs, tombstones, replicas, concurrent writes, and the read path**. Two writes with the same visible value can carry different timestamps and alter how Cassandra resolves conflicts against other writes.

| Layer | Question | Example |
|---|---|---|
| **Storage state** | Does repeating the mutation preserve data invariants? | Setting a fixed `status` on the same primary key |
| **Request result** | Does a retry return the exact same response? | LWT `IF NOT EXISTS`: `true` then `false` |
| **Business workflow** | Does the overall request produce one contractual effect? | Creating an order and emitting an event / sending an email |

### 2.1. The idempotency key must belong to the logical request

A customer clicks “Place Order” and the gateway retries after a timeout. If each attempt generates a **new `orderId`**, all `INSERT`s can succeed on separate partitions. No statement-level idempotent flag can rescue that bug.

Design the system to issue an **idempotency key** before the first attempt and preserve it across all retries. Define key scope clearly (tenant, operation type, expiration window, payload fingerprint). A reused key with a different payload must be rejected as a conflict rather than silently treated as the same request.

### 2.2. Identical CQL text, different timing

Suppose Java issues the same CQL `INSERT` but regenerates the timestamp on every attempt. Consider three mutations:

~~~text
T1: Request A sets status=PAID at timestamp 100.
T2: Request B sets status=REFUNDED at timestamp 110.
T3: Retry of A sets status=PAID at timestamp 120.

The final state reverts to PAID even though A was merely "retrying".
~~~

That is the **last-write-wins** hazard. An assignment that looks idempotent in isolation may still be unsafe to retry alongside concurrent writers. You may need **revision/CAS via LWT**, deterministic timestamps, idempotency keys, and convergence rules—never rely on ad-hoc client timestamps to simulate transactions.

## 3. What `setIdempotent` Actually Means in Java Driver 4.x

~~~java
BoundStatement safe = prepared.bind(...)
    .setIdempotent(true);

BoundStatement unsafe = prepared.bind(...)
    .setIdempotent(false);
~~~

This is **metadata on the statement**. The driver reads it in applicable execution policies, primarily:

- **Retry policy:** may retry eligible errors on a statement marked idempotent. Which errors, how many attempts, and outcomes still depend on the policy/version.
- **Speculative execution:** when configured, the driver can launch a duplicate execution if an earlier attempt stalls, reducing tail latency; non-idempotent operations must not be speculatively duplicated.
- **Review / observability:** documents developer intent, though it is not proof of business safety.

The flag **does not**:

- Turn counter increments or list appends into assignments.
- Add `IF NOT EXISTS` or transactions to CQL.
- Guarantee every error will be retried or succeed on retry.
- Automatically stabilize timestamps, TTLs, `requestId`, or business fingerprints.
- Guarantee that a timeout means the server never executed the query.
- Alter consistency level, replication factor, or LWT serial CL.
- Control emails, payments, message brokers, or external side effects.
- Cure hot partitions, compaction backlogs, or disk saturation.

### 3.1. Four cases to remember

| Actual semantics | Driver flag | Consequence |
|---|---|---|
| Safe to re-run | **`true`** | Driver may consider retries/speculation per policy |
| Unsafe to re-run | **`false`** | Protects against unsafe replays checked by policies |
| Unsafe, marked `true` | **Wrong `true`** | Can duplicate side effects or overwrite newer state |
| Safe, marked `false` | **Conservative `false`** | Fewer retry/speculation opportunities, but never corrupts data |

Never default `true` across all statements just to get “fewer errors”. When safety is unproven, choose **`false` conservatively** and review.

### 3.2. `BoundStatement` immutability and the discarded-return bug

In Java Driver 4.x, statement setters generally return a new statement instance.

~~~java
BoundStatement original = prepared.bind(...);
original.setIdempotent(true);  // Return value discarded; original unchanged.
session.execute(original);     // Does not execute with true set.
~~~

Correct:

~~~java
BoundStatement request = prepared.bind(...)
    .setIdempotent(true)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(request);
~~~

The same immutability rule applies to **`setSerialConsistencyLevel`**, **`setPageSize`**, **`setExecutionProfileName`**, and related attributes.

### 3.3. Defaults and execution profiles

An example HOCON configuration for Java Driver 4.x:

~~~hocon
datastax-java-driver {
  basic {
    request {
      consistency = LOCAL_QUORUM
      timeout = 2 seconds
      default-idempotence = false
    }
  }
}
~~~

Values are **illustrative**; consult the configuration reference and effective config of your driver release. Keep `default-idempotence` conservative and set `true` deliberately on reviewed statements. Named execution profiles bundle timeout, CL, and retry policy; **a profile cannot turn an unsafe mutation into a safe one**.

## 4. CQL Idempotency Matrix

| Operation kind | Can it be idempotent? | Conditions and traps |
|---|---|---|
| **`SELECT`** with no side effects | **Usually yes** | Retries may read newer values, but never mutate Cassandra |
| **`INSERT`** with fixed key and values | **Conditionally** | Timestamps/TTLs, concurrent writers, CDC, and side effects |
| **`UPDATE SET field = literal`** | **Conditionally** | Concurrent writes/timestamps and domain state machines |
| **`DELETE`** by fixed key | **Conditionally** | Tombstone timestamps, resurrection, and concurrent writes |
| **`COUNTER: total = total + 1`** | **No** | Each execution can increment again |
| **`LIST` append/prepend** | **Usually no** | Elements can be appended multiple times |
| **`SET` add/remove** | **Conditionally** | Set elements deduplicate, yet timestamps/tombstones/concurrency still matter |
| **`MAP` key/value assignment** | **Conditionally** | Fixed key assignment differs from state-dependent mutations |
| **`BATCH`** | **Must review entire batch** | A batch may hold non-idempotent mutations; no cross-partition transactions |
| **`IF NOT EXISTS` / `IF column = ?`** | **Needs dedicated review** | `[applied]` changes across attempts and timeouts are ambiguous |
| **DDL `CREATE`/`ALTER`/`DROP`** | **Not by default** | `IF NOT EXISTS` is neither schema diffing nor rollback |

### 4.1. Fixed assignments vs. increments and appends

~~~sql
-- Potentially safe when paired with fixed keys, versions, and timestamps.
UPDATE shop.orders_by_id
SET status = 'PAID'
WHERE tenant_id = ? AND order_id = ?;

-- Unsafe for blind retries:
UPDATE shop.counters_by_tenant
SET total = total + 1
WHERE tenant_id = ?;

-- Unsafe when list appends can produce duplicate elements:
UPDATE shop.tasks_by_id
SET events = events + ?
WHERE tenant_id = ? AND task_id = ?;
~~~

The tables in this snippet illustrate **operation syntax** only; they do not exist unless you create the corresponding CQL schema.

### 4.2. TTL is a subtle case

~~~sql
INSERT INTO shop.expiring_event_by_id (
    tenant_id, event_id, event_type
) VALUES (?, ?, ?)
USING TTL 120;
~~~

A relative TTL means a delayed retry shifts cell expiration and liveness metadata. If the business contract requires **expiration 120 seconds from the initial request**, do not assume this CQL is idempotent merely because column values are fixed. Design a fixed **`expires_at`**, deterministic timestamps, and retention rules, and test on your exact Cassandra version.

### 4.3. Batches do not rescue unsafe mutations

~~~text
BATCH with 2 INSERTs having stable keys/values/timestamps:
  Can evaluate idempotency of the whole batch.

BATCH containing a counter increment or list append:
  Cannot mark the whole batch safe just because part of it is an INSERT.

BATCH + sending an email in Java:
  The batch's idempotent flag does not control the email.
~~~

A Cassandra `LOGGED BATCH` uses a batchlog mechanism, not a multi-partition/multi-service ACID transaction with rollback. Never use giant multi-partition batches as a bulk loader.

## 5. Why Doesn't a Timeout Mean “Not Written”?

A Java request normally travels through a coordinator to the partition's replicas. With **RF = 3 in `dc1`** and **`LOCAL_QUORUM`**, a write needs acknowledgments from **two replicas** under Cassandra's rules. If one replica acknowledges while two stall, the client sees `WriteTimeout` even though the first replica **already applied the mutation**.

~~~mermaid
sequenceDiagram
    participant J as Java Driver
    participant C as Coordinator
    participant A as Replica A
    participant B as Replica B
    participant D as Replica C
    J->>C: INSERT, LOCAL_QUORUM
    C->>A: Mutation
    C->>B: Mutation
    C->>D: Mutation
    A-->>C: ACK
    B--xC: Slow / lost response
    D--xC: Slow / lost response
    C-->>J: WriteTimeout / insufficient ACKs
    Note over J,D: A may already have persisted the write.
    J->>J: Do not conclude "not written"
~~~

### 5.1. Error matrix and allowed conclusions

| Signal | Valid conclusion | Invalid inference |
|---|---|---|
| **WriteTimeout** | Insufficient ACKs before server timeout | No replica persisted the write |
| **WriteFailure** | One or more write failures reported; request did not meet criteria | No partial data was applied |
| **Driver-side request timeout** | Client waited past driver deadline/timeout | Coordinator stopped processing |
| **Unavailable** | Too few live replicas for the requested CL | The row definitely does not exist |
| **Overloaded** | Server reports intake/processing pressure | Immediate retry helps the system |
| **ReadTimeout / ReadFailure** | Read path failed to meet response conditions | Prior writes did not occur |
| **LWT `[applied]=false`** | Condition failed on that attempt | Earlier attempt of the same request did not apply |

Infrastructure failures can leave state **`UNKNOWN`**. That is a **meaningful business state**, not something to coerce to `false` to simplify code.

### 5.2. RF, CL, and replicas are not a deduplication engine

Raising **RF** or using **`LOCAL_QUORUM`/`QUORUM`/`ALL`** affects availability, latency, and acknowledgment guarantees—it **never** makes `counter + 1` idempotent or turns `SELECT`-then-`INSERT` into compare-and-set.

**Repair** converges replica state at the Cassandra storage level; it has no idea which `orderId`s are business duplicates. **Compaction** merges SSTables and purges tombstones in the background; it will not collapse two rows with **two distinct `request_id`s**. Key design and deduplication must happen at the application layer.

### 5.3. Retries do not equal exactly-once

Retries can raise the odds that a logical operation **completes**, without guaranteeing the server executed it exactly once. End-to-end exactly-once involves request identity, one or more sinks, emitted events, concurrent writes, and durable checkpoints. With Cassandra, multi-system workflows typically rely on **at-least-once + idempotent consumers/deduplication + reconciliation**.

## 6. CQL Lab: Distinguishing Three Mutation Patterns

Create a test keyspace on an appropriate cluster. This example uses RF = 3 in **`dc1`**; on a single-node lab, adjust RF/CL accordingly and note the testing limitation.

~~~sql
CREATE KEYSPACE IF NOT EXISTS idempotency_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

-- Each logical request has its own key for exact reconciliation.
CREATE TABLE IF NOT EXISTS idempotency_lab.event_by_request (
    tenant_id uuid,
    request_id uuid,
    event_type text,
    payload text,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, request_id))
);

-- List collection to demonstrate duplicate-append risk.
CREATE TABLE IF NOT EXISTS idempotency_lab.task_list_by_id (
    tenant_id uuid,
    task_id uuid,
    events list<text>,
    PRIMARY KEY ((tenant_id, task_id))
);

-- Separate counter table per CQL rules.
CREATE TABLE IF NOT EXISTS idempotency_lab.counter_by_tenant (
    tenant_id uuid PRIMARY KEY,
    total counter
);
~~~

**Wide-column analysis:**

- **`event_by_request`** uses composite partition key **`(tenant_id, request_id)`**, pinning each logical request for direct reads and reconciliation without creating one unbounded tenant partition.
- **`task_list_by_id`** exists strictly to prove list-append unsafety. In production, if events grow over time, prefer **multiple rows per task/bucket** rather than unbounded collections.
- **`counter_by_tenant`** illustrates unsafe accumulation on retry; a busy tenant can also create a **hot partition**.
- Partition keys select the replica set; CL defines required responses. The idempotent flag **does not change** token routing.

### 6.1. Fixture for a stable assignment

~~~sql
INSERT INTO idempotency_lab.event_by_request (
    tenant_id, request_id, event_type, payload, created_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'ORDER_CREATED', '{"order":"lab-01"}',
    '2026-11-21T08:00:00Z'
);

SELECT event_type, payload, created_at
FROM idempotency_lab.event_by_request
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND request_id = 22222222-2222-4222-8222-222222222222;
~~~

The CQL above shows a logical request with a fixed key; no explicit write timestamp is set. The Java snippet next shows how to fix the timestamp from **a single source** when business rules require it.

### 6.2. Two non-idempotent patterns

~~~sql
-- Resending on ambiguous outcome can increment the counter twice.
UPDATE idempotency_lab.counter_by_tenant
SET total = total + 1
WHERE tenant_id = 11111111-1111-4111-8111-111111111111;

-- Resending can append 'STARTED' multiple times.
UPDATE idempotency_lab.task_list_by_id
SET events = events + ['STARTED']
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND task_id = 33333333-3333-4333-8333-333333333333;
~~~

These CQL statements are lab fixtures only. Never run them against production counters or lists just to observe idempotency; use an isolated test cluster.

## 7. Java Driver 4.x: Setting the Right Flag per Statement

### 7.1. Prepared `INSERT` with fixed key and timestamp

The code below executes **one logical request** with stable `tenantId`, `requestId`, `payload`, `createdAt`, and write timestamp. In production, the service creates these **once before the first attempt** and preserves them across approved retries.

~~~java
import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class IdempotentWriteDemo {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        UUID requestId = UUID.fromString(
            "22222222-2222-4222-8222-222222222222");
        Instant createdAt =
            Instant.parse("2026-11-21T08:00:00Z");

        // Demo: microsecond timestamp chosen ONCE.
        long writeTimestampMicros =
            createdAt.toEpochMilli() * 1_000L;

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO idempotency_lab.event_by_request " +
                "(tenant_id, request_id, event_type, " +
                "payload, created_at) VALUES (?, ?, ?, ?, ?) " +
                "USING TIMESTAMP ?");

            BoundStatement request = insert.bind(
                    tenantId, requestId, "ORDER_CREATED",
                    "{\"order\":\"lab-01\"}",
                    createdAt, writeTimestampMicros)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            session.execute(request);

            // If retrying: resend THIS EXACT mutation with
            // unchanged requestId, values, and timestamp.
        }
    }
}
~~~

**Conditions allowing `true` for this example:**

1. Bound values are **immutable** across attempts.
2. Primary key is stable—no new UUID minted after a timeout.
3. Write timestamp is deterministic and matches the data versioning policy.
4. No relative TTL, counter, list append, or response-dependent LWT.
5. No unguarded external side effects outside the DB.
6. Concurrent writers, tombstones, and timestamps are verified via tests and domain contracts.

**Never infer “fixing a timestamp gives me transactions”.** If distinct requests share timestamps or race, last-write-wins and tombstone rules still apply; for conditional state transitions, use **CAS/LWT or proper versioning**.

### 7.2. Anti-pattern: regenerating timestamp on each attempt

~~~java
// Never mint a fresh clock timestamp on every retry.
BoundStatement attempt = insert.bind(
    tenantId, requestId, eventType, payload,
    createdAt, System.currentTimeMillis() * 1_000L);
~~~

Even when the primary key and payload stay constant, the timestamp changed. A delayed retry arriving after another writer's update can win under timestamp precedence and corrupt business state.

### 7.3. Counters: must be set to `false`

~~~java
PreparedStatement increment = session.prepare(
    "UPDATE idempotency_lab.counter_by_tenant " +
    "SET total = total + 1 WHERE tenant_id = ?");

BoundStatement counterWrite = increment.bind(tenantId)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotent(false);

session.execute(counterWrite);
~~~

This runs inside a method with initialized `session` and `tenantId`. **`setIdempotent(false)`** stops driver policies from auto-replaying the mutation, yet **does not resolve a timeout where the increment already applied partially**. The API needs tracking and reconciliation rather than service-level retries.

### 7.4. List appends: never mark `true` for easy retries

~~~java
import java.util.List;

PreparedStatement append = session.prepare(
    "UPDATE idempotency_lab.task_list_by_id " +
    "SET events = events + ? " +
    "WHERE tenant_id = ? AND task_id = ?");

BoundStatement appendEvent = append.bind(
        List.of("STARTED"), tenantId, taskId)
    .setIdempotent(false);

session.execute(appendEvent);
~~~

A list element can be appended multiple times if retried. If the application needs an ordered event log, model **one row per event with its own `eventId`** rather than growing an unbounded list. `List.of` requires Java 9+; on older JDKs use the equivalent list factory.

### 7.5. `SimpleStatement` also carries the flag

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement query = SimpleStatement.builder(
        "SELECT event_type FROM idempotency_lab.event_by_request " +
        "WHERE tenant_id = ? AND request_id = ?")
    .addPositionalValues(tenantId, requestId)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotent(true)
    .build();
~~~

For repeated queries, **`PreparedStatement`** is generally preferable to avoid re-parsing overhead and preserve CQL type bindings. This `SimpleStatement` example merely shows where metadata lives; verify exact API signatures for your pinned driver version.

### 7.6. Batches: the flag must reflect the entire action

When using **`BatchStatement`** or CQL `BATCH`, evaluate idempotency for **every mutation in the batch**, never marking `true` just because one component statement is an `INSERT`. Any batch containing counters, list ops, or unstable timestamps/TTLs needs dedicated handling. Multi-partition batches do not provide business workflow rollback.

## 8. LWT: Same Row, Different `[applied]` Outcome

~~~sql
CREATE TABLE IF NOT EXISTS idempotency_lab.claim_by_key (
    tenant_id uuid,
    request_id uuid,
    owner_token text,
    status text,
    PRIMARY KEY ((tenant_id, request_id))
);

INSERT INTO idempotency_lab.claim_by_key (
    tenant_id, request_id, owner_token, status
) VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

For an unused key:

~~~text
Attempt 1: Cassandra applies IF NOT EXISTS, [applied] = true.
Response is lost; client hits timeout.
Attempt 2: Client retries same key, [applied] = false.
Reading back the row reveals the initial request's own owner_token.
~~~

**`[applied]=false` does not mean “the initial request failed to create the row”.** Read the row by key and compare `owner_token`/request fingerprint to distinguish a replay of the same request from a competitor winning first.

### 8.1. Regular CL vs. serial CL

~~~java
BoundStatement lwt = preparedConditional.bind(
        tenantId, requestId, ownerToken, "CLAIMED")
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_SERIAL)
    .setIdempotent(false);
~~~

Here **`false` is the conservative choice** when downstream side effects depend on observing **`[applied]`** and retry safety is unproven. **`LOCAL_QUORUM`** is the regular CL for the commit phase, while **`LOCAL_SERIAL`** governs LWT Paxos consensus scope—two distinct settings.

If writers span multiple DCs and require a global uniqueness invariant, evaluate **`SERIAL`** vs. **`LOCAL_SERIAL`** per your Cassandra version rather than defaulting to `LOCAL_SERIAL` purely for speed. The idempotent flag **does not alter** serial CL.

### 8.2. Checking `[applied]` when a response arrives

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

Row result = session.execute(lwt).one();
if (result == null) {
    throw new IllegalStateException("LWT returned no result");
}

if (result.getBoolean("[applied]")) {
    // Created during this response-bearing attempt.
} else {
    // Condition false: read the row to distinguish duplicate vs. conflict.
}
~~~

When **`session.execute(lwt)`** throws a timeout or network exception, **never** fall through to the `false` branch. Track the state as **`UNKNOWN`**, which may require data reconciliation after cluster recovery.

## 9. Three-State Result Classification for Services

An API can expose a three-state domain outcome:

~~~text
APPLIED_TRUE
  Server returned [applied]=true.

APPLIED_FALSE
  Server returned [applied]=false.

UNKNOWN
  Timeout/transport/failure prevented a conclusive answer.
~~~

Suggested mapping:

| Signal | Service action |
|---|---|
| `true` with matching data | Report created / applied |
| `false`, row matches idempotency key and fingerprint | Report already processed for the same request per contract |
| `false`, row belongs to a different request | Report business conflict |
| Timeout / `WriteFailure` / driver timeout | Never return “false”; hold `UNKNOWN` and reconcile when possible |
| `Overloaded` / `Unavailable` | Shed load or fail fast; retry only if budget and safety allow |
| Authentication / invalid CQL / codec | Fix code/config; never retry blindly |

**A `false` outcome after a retry can represent an earlier attempt's success.** Persist IDs, owners, and fingerprints before the first attempt rather than regenerating them per retry.

## 10. Async Java: Keep Errors as Errors, Never Coerce to `false`

For services returning **`CompletionStage`**, server/driver faults complete the stage exceptionally. Coercing all errors to `false` can trick the HTTP layer into reporting “order already exists” when the state was never verified.

### 10.1. Especially dangerous anti-pattern

~~~java
// WRONG: timeouts, overload, and network errors turn into condition-not-met.
return session.executeAsync(lwt)
    .thenApply(result ->
        result.currentPage().iterator()
            .next().getBoolean("[applied]"))
    .exceptionally(error -> false);
~~~

This destroys the distinction between **`APPLIED_FALSE`** and **`UNKNOWN`**. Preserve exceptions and causes for reconciliation or explicit error responses.

### 10.2. `CompletionStage` example preserving outcomes

~~~java
import java.util.Iterator;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class ConditionalWriteService {
    private final CqlSession session;

    public ConditionalWriteService(CqlSession session) {
        this.session = session;
    }

    public CompletionStage<Boolean> executeConditional(
            BoundStatement lwt) {
        return session.executeAsync(lwt)
            .thenApply(page -> {
                Iterator<Row> it =
                    page.currentPage().iterator();
                if (!it.hasNext()) {
                    throw new IllegalStateException(
                        "Missing [applied] result");
                }
                return it.next().getBoolean("[applied]");
            })
            .whenComplete((applied, error) -> {
                if (error != null) {
                    Throwable cause = unwrap(error);
                    System.err.println(
                        "LWT error class: " +
                        cause.getClass().getSimpleName());
                }
            });
    }

    private static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException &&
                error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }
}
~~~

**Meaning:**

- The stage resolves to **`true`/`false`** only when the server returns a conditional result.
- On timeouts or driver errors, the stage stays failed; **`whenComplete`** only observes rather than turning it into `false`.
- Never log raw `BoundStatement`s, credentials, payloads, or sensitive idempotency tokens.
- Wire this service to a **shared `CqlSession`** rather than opening sessions per HTTP request.
- This snippet intentionally triggers no retries; retry decisions belong where the **business contract** is known.

### 10.3. Exception classes do not decide retries alone

If a service catches:

~~~java
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.WriteFailureException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;

try {
    session.execute(write);
} catch (WriteTimeoutException ex) {
    // Ambiguous outcome: preserve request identity and reconcile.
} catch (WriteFailureException ex) {
    // Inspect failure and partial-application risk.
} catch (OverloadedException ex) {
    // Shed load; never retry immediately when server is overloaded.
}
~~~

where `write` is a previously built `BoundStatement`. This is only a classification skeleton, not a complete handler. You must also handle **`UnavailableException`, read failures, client timeouts, and network/TLS/auth/codec errors**. Operational classification does not mean every class is automatically retryable.

## 11. Retry Budget: Re-Execute Only When All Conditions Hold

A sound retry policy must satisfy all of these simultaneously:

1. **The operation is proven idempotent** across both storage and business semantics.
2. **The error is plausibly transient**, not a CQL, schema, or auth bug.
3. **End-to-end deadline remains** after subtracting backoff and the next attempt's execution time.
4. **Retry budget remains** and the server is not overloaded / circuit breaker is not open.
5. **No uncoordinated multi-layer retries** exist across driver, service, gateway, and HTTP client.
6. **Consistency level and serial consistency are preserved**, never silently downgraded to mask errors.

~~~mermaid
flowchart TD
    A["Attempt failed"] --> B{"Safe to re-execute mutation?"}
    B -->|No / Unclear| R["No auto-retry; keep UNKNOWN / reconcile"]
    B -->|Yes| C{"Transient error and server has headroom?"}
    C -->|No| F["Fail fast / shed load"]
    C -->|Yes| D{"Deadline + retry budget remain?"}
    D -->|No| G["Return error; no new attempt"]
    D -->|Yes| E["Backoff + jitter + retry with same identity"]
    E --> H["Record attempt and outcome; mint no new ID"]
~~~

### 11.1. Non-blocking full jitter

**Illustrative** policy parameters (not universal Cassandra thresholds):

~~~text
max_attempts = 3 (including initial attempt)
base_backoff = 100 ms
max_backoff = 1000 ms

If eligible to retry:
  ceiling = min(max_backoff, base_backoff * 2^(attempt - 1))
  delay = random(0, ceiling)

Schedule the next attempt only when:
  remaining deadline covers delay + minimum processing time,
  and load state does not require shedding load.
~~~

In async Java, use **`ScheduledExecutorService`**, `CompletableFuture.delayedExecutor` (if supported by your JDK), or your framework's scheduler. **Never call `Thread.sleep`** inside a driver callback or reactive event loop.

### 11.2. Why must the retry budget include the driver layer?

Suppose the gateway retries an HTTP call up to 2 times, the service retries CQL up to 3 times, and the driver also runs a retry policy. Physical requests can far exceed logical requests depending on policy and timing.

Measure:

~~~text
logical_requests
driver_physical_attempts
service_retry_attempts
gateway_retry_attempts
speculative_executions
in_flight_requests
admission_rejected_requests
~~~

Do not rely on a fixed multiplier formula without knowing each layer's exact policy, but **enforce an end-to-end cap** and clarify which layer owns retries. With **speculative execution**, account for two executions running concurrently for one logical request.

### 11.3. A flawed deadline example

HTTP deadline is **2 seconds**. A request waits **400 ms** in a queue, the first Cassandra attempt takes **1,300 ms**, and the service plans a **200 ms** backoff followed by a **1-second** driver timeout.

~~~text
2,000 ms - 400 ms - 1,300 ms - 200 ms = 100 ms
~~~

Only 100 ms remain for a second attempt, result mapping, and the HTTP response. Launching a 1-second attempt violates this deadline. Failing cleanly and letting the system recover beats firing orphaned server work.

## 12. Backpressure and `Overloaded`: `false` Does Not Cure Saturation

When Cassandra reports **`Overloaded`**, immediate retries make things worse:

1. In-flight requests climb.
2. Coordinator/replica queues, disks, and GC take added load.
3. Tail latency rises, timing out unrelated requests.
4. Multiple clients retry together, creating a **retry storm**.
5. Expired API calls leave orphaned work running on the server.

The idempotent flag may allow considering retries, yet **it does not mean retrying is always beneficial**. Under overload, apply **admission control, bounded concurrency, rate limiting, backoff, finite queues, and load shedding**.

### 12.1. Java semaphore for logical operations

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class BoundedCqlGateway {
    private final CqlSession session;
    private final Semaphore inFlight;

    public BoundedCqlGateway(
            CqlSession session, int maxConcurrent) {
        if (maxConcurrent <= 0) {
            throw new IllegalArgumentException(
                "maxConcurrent must be positive");
        }
        this.session = session;
        this.inFlight = new Semaphore(maxConcurrent);
    }

    public CompletionStage<AsyncResultSet> execute(
            BoundStatement statement) {
        if (!inFlight.tryAcquire()) {
            CompletableFuture<AsyncResultSet> denied =
                new CompletableFuture<>();
            denied.completeExceptionally(
                new RejectedExecutionException(
                    "Cassandra client admission limit"));
            return denied;
        }
        try {
            return session.executeAsync(statement)
                .whenComplete((result, error) ->
                    inFlight.release());
        } catch (RuntimeException ex) {
            inFlight.release();
            throw ex;
        }
    }
}
~~~

**Limitations of this example:**

- The permit guards **one `executeAsync`** for the first page/result; if paging through **all pages**, hold the permit across **`fetchNextPage()`** until the full pipeline finishes.
- This cap applies **per Java instance**, not across the whole service. \(N\) instances multiply total concurrency.
- **`RejectedExecutionException`** is client-side admission control, distinct from Cassandra's **`OverloadedException`**; track them separately in logs/metrics.
- If the service performs manual retries, scope permits/quotas to the **logical operation** rather than granting uncontrolled fresh permits per retry.
- For LWTs, round-trips and CAS contention take longer than normal writes; allocate a separate capacity budget.
- Production systems also require deadlines, cancellation, queue limits, and graceful shutdown/draining.

### 12.2. Request rate and concurrency are two separate axes

By Little's Law in a stable system:

\[
L \approx \lambda W
\]

where **\(L\)** is average in-flight requests, **\(\lambda\)** is throughput (req/s), and **\(W\)** is average request duration.

| Average RPS | Average latency | Estimated in-flight |
|---|---:|---:|
| 1,000/s | 0.1 s | 100 |
| 1,000/s | 0.5 s | 500 |
| 1,000/s | 2.0 s | 2,000 |

If Cassandra slows down 20x while arrival rate stays flat, in-flight requests surge dramatically. **Raising timeouts without bounding concurrency** triggers memory pressure, terrible p99, and `Overloaded`. Note that Little's Law is a steady-state estimate, not an exact forecast when queues saturate or requests drop.

## 13. Layer Responsibilities in a Java/Cassandra Architecture

| Layer | Must be responsible for | Must not assume |
|---|---|---|
| **Business / domain owner** | Defining logical operations, duplicate policies, replay vs. conflict rules | That the driver knows whether a payment was captured |
| **Java application developer** | Stable keys/values, accurate idempotent flags, exception mapping, retry/deadlines | That `setIdempotent(true)` guarantees safety |
| **Repository / data model owner** | Partition keys, clustering, query-driven schemas, TTL/timestamp semantics | That changing CL fixes unkeyed queries |
| **Platform / SRE** | RF/DC, node health, capacity, compaction/repair, metrics, backups | That replicas deduplicate business records |
| **Driver / policy** | Executing CQL per config, permitted retries/speculation | Any business knowledge outside the request |
| **Gateway / HTTP client** | Honoring deadlines and idempotency headers, avoiding nested retries | That every `POST` is safe to retry |
| **Downstream sink** | Deduplication/outbox/reconciliation for external side effects | That a successful Cassandra `INSERT` guarantees an email was sent |

### 13.1. Code reviews must ask semantic questions

Before approving **`setIdempotent(true)`**, reviewers should ask:

1. What is the **operation identity**? Is `requestId` stable across retries?
2. Can the **primary key** change between attempts?
3. Can bound values, **write timestamp, or TTL** change?
4. Are there counters, list appends, relative mutations, or response-dependent LWTs?
5. Can concurrent writers interleave and alter timestamp/version semantics?
6. Do external side effects run before or after the CQL call?
7. Which **retry/speculative execution policies** apply and how many total attempts are allowed?
8. After a timeout, how is state verified if the outcome is `UNKNOWN`?
9. Do consistency level, RF, and DC match business guarantees?
10. Do integration tests verify safe replay and failure paths?

If key answers are missing, **do not enable `true` just to boost request success rates**.

## 14. Using an Idempotency/Claim Table When Uniqueness Is Required

For the rule **“only one request may claim a business key”**, one option is an LWT:

~~~sql
CREATE TABLE IF NOT EXISTS idempotency_lab.claim_by_business_key (
    tenant_id uuid,
    business_key text,
    request_id uuid,
    payload_fingerprint text,
    state text,
    PRIMARY KEY ((tenant_id, business_key))
);

INSERT INTO idempotency_lab.claim_by_business_key (
    tenant_id, business_key, request_id,
    payload_fingerprint, state
) VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

**Design:**

- **`(tenant_id, business_key)`** is the partition key for the uniqueness invariant.
- **`request_id`** identifies the logical request holding the claim.
- **`payload_fingerprint`** detects key reuse with a mismatched payload without logging sensitive plaintext.
- **`state`** tracks workflow progress and requires conditional updates if concurrent workers can advance it.

After **`[applied]=false`**, the service reads the row at an appropriate CL and compares **`request_id` + `payload_fingerprint`**:

~~~text
Same request_id and fingerprint:
    Can be treated as a duplicate of the same request;
    check state to see whether the business step already completed.

Different request_id or fingerprint:
    Business conflict; do not retry endlessly hoping to win.

Read failed due to timeout/unavailable:
    UNKNOWN; insufficient proof to report created or not created.
~~~

**LWTs do not provide cross-table or cross-system transactions.** If the claim succeeded while writing details or publishing an event failed, use a **state machine + outbox/reconciliation**—never expect CAS to roll back an email or message broker.

### 14.1. Idempotency key TTL and deduplication window

If claims expire after a TTL, determine:

- Can clients or gateways retry after that expiration window?
- Do older events still exist downstream?
- Is reusing the business key after TTL expiration allowed by domain rules?
- Will expired rows/tombstones add read, compaction, or repair overhead?

If an idempotency record expires before the last retry arrives, the same logical operation will be treated as a brand-new request. Therefore, **retention and idempotency windows must cover the retry horizon and business data retention period**.

### 14.2. Fingerprints do not replace authorization

A fingerprint compares payloads, not user identity. APIs must authenticate and authorize by tenant so one client cannot probe another tenant's claim state using `business_key`. Log only approved request IDs, never raw payment tokens, secrets, or sensitive PII.

## 15. JUnit 5 Integration Testing: Idempotent vs. Accumulative Mutations

A test that merely checks code called **`setIdempotent(true)`** does not prove idempotency. Execute operations repeatedly against an **isolated fixture**, verify final data state, and test faults and concurrent writers.

### 15.1. Testing repeated `INSERT` with fixed key, data, and timestamp

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import org.junit.jupiter.api.Test;

public class IdempotenceIntegrationIT {
    @Test
    void repeatedSameInsertHasOneLogicalRow() {
        UUID tenantId = UUID.randomUUID();
        UUID requestId = UUID.randomUUID();
        Instant occurredAt =
            Instant.parse("2026-11-21T09:00:00Z");
        long stableTimestampMicros =
            occurredAt.toEpochMilli() * 1_000L;

        // Adjust contact point/DC and auth/TLS for your lab cluster.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO idempotency_lab.event_by_request " +
                "(tenant_id, request_id, event_type, payload, " +
                "created_at) VALUES (?, ?, ?, ?, ?) " +
                "USING TIMESTAMP ?");

            BoundStatement sameMutation = insert.bind(
                    tenantId, requestId,
                    "ORDER_CREATED", "{\"order\":\"lab-01\"}",
                    occurredAt, stableTimestampMicros)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            // Explicitly execute twice in the test rather than
            // waiting for the driver to retry automatically.
            session.execute(sameMutation);
            session.execute(sameMutation);

            PreparedStatement select = session.prepare(
                "SELECT event_type, payload, created_at " +
                "FROM idempotency_lab.event_by_request " +
                "WHERE tenant_id = ? AND request_id = ?");

            Row row = session.execute(select
                .bind(tenantId, requestId)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM))
                .one();

            assertNotNull(row);
            assertEquals(
                "ORDER_CREATED",
                row.getString("event_type"));
            assertEquals(
                "{\"order\":\"lab-01\"}",
                row.getString("payload"));
            assertEquals(
                occurredAt,
                row.getInstant("created_at"));
        }
    }
}
~~~

**Verified scope:** executing **the same `BoundStatement`** twice for **the same partition key** and **the same write timestamp** yields the expected final state in the lab.

**Not yet proven:** safety with interleaved concurrent writers, relative TTLs, CDC, tombstones, failed attempts, or external side effects. If those belong to your workflow, add matching tests before approving `true`.

### 15.2. Counters double-increment if resent

Add this test method to the class or a dedicated test class with matching imports:

~~~java
@Test
void repeatedCounterIncrementHasTwoEffects() {
    UUID tenantId = UUID.randomUUID();

    try (CqlSession session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .build()) {

        PreparedStatement increment = session.prepare(
            "UPDATE idempotency_lab.counter_by_tenant " +
            "SET total = total + 1 " +
            "WHERE tenant_id = ?");

        BoundStatement oneIncrement = increment
            .bind(tenantId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(false);

        // Intentionally execute twice to show:
        // false does not alter CQL semantics.
        session.execute(oneIncrement);
        session.execute(oneIncrement);

        PreparedStatement select = session.prepare(
            "SELECT total FROM idempotency_lab.counter_by_tenant " +
            "WHERE tenant_id = ?");

        Row row = session.execute(select
            .bind(tenantId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM))
            .one();

        assertNotNull(row);
        assertEquals(2L, row.getLong("total"));
    }
}
~~~

**Key point:** **`setIdempotent(false)`** prevents automatic driver-managed retries/speculation, **yet does not stop Java code from calling `session.execute` twice**. Because the test explicitly sends two mutations, the counter increments to 2. That is why manual service retries require separate review.

On an overloaded lab cluster or with failed requests, results can be nondeterministic; run this test on a **healthy cluster with no fault injection**. In real JUnit suites, initialize schemas in shared setup fixtures rather than dropping tables per test.

### 15.3. Non-idempotent list append test

~~~java
@Test
void repeatedListAppendCreatesDuplicates() {
    UUID tenantId = UUID.randomUUID();
    UUID taskId = UUID.randomUUID();

    try (CqlSession session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .build()) {

        PreparedStatement append = session.prepare(
            "UPDATE idempotency_lab.task_list_by_id " +
            "SET events = events + ? " +
            "WHERE tenant_id = ? AND task_id = ?");

        BoundStatement statement = append.bind(
                java.util.List.of("STARTED"), tenantId, taskId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(false);

        session.execute(statement);
        session.execute(statement);

        PreparedStatement select = session.prepare(
            "SELECT events " +
            "FROM idempotency_lab.task_list_by_id " +
            "WHERE tenant_id = ? AND task_id = ?");

        Row row = session.execute(select.bind(
                tenantId, taskId)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM))
            .one();

        assertNotNull(row);
        java.util.List<String> actual =
            row.getList("events", String.class);
        assertNotNull(actual);
        assertEquals(2, actual.size());
        assertEquals("STARTED", actual.get(0));
        assertEquals("STARTED", actual.get(1));
    }
}
~~~

A sequential demo test on a list does not imply Cassandra preserves strict ordering under **concurrent list writes** from multiple clients. Here two appends run **sequentially** in a lab solely to prove list appends differ from fixed value assignments.

### 15.4. Tests requiring a multi-replica environment

If CI runs only a single RF = 1 Cassandra container, tests prove basic CQL and driver wiring. They **do not prove**:

- `LOCAL_QUORUM` with RF = 3 surviving a replica failure.
- Driver retries/speculation under multi-node network faults.
- CAS LWT behavior across multi-DC writers.
- Latency shifts when compaction/repair competes for I/O.
- Data convergence after partial replica writes.

Maintain a multi-node, multi-DC staging suite with controlled fault injection; never extrapolate production safety solely from unit tests or single-node local runs.

## 16. Testing Lost Responses After a Write Applied

A classic source of **duplicate business effects** is: **the server persisted the write, but the client lost the response**. You can simulate this safely with a service-layer test double without breaking production networks.

### 16.1. Test scenario

~~~text
1. Service generates requestId K and payload P once.
2. Repository sends mutation K/P; Cassandra persists it.
3. Test adapter hides the response and throws "response lost".
4. API layer sees UNKNOWN and invokes reconciliation.
5. Query row by K at proper CL; observes payload P.
6. Service concludes the request already exists with the same fingerprint,
   mints no new ID, and emits no duplicate event.
~~~

**Note:** This simulates a **lost response after success**, not an actual server **`WriteTimeoutException`**. Testing real network faults requires a staging cluster with fault injection.

### 16.2. Lost-response test pseudocode

~~~java
// Service-level pseudocode; not built-in driver APIs.
UUID requestId = UUID.randomUUID();
String fingerprint = "hash-of-canonical-payload";

// Test adapter: write succeeds, then simulate lost response.
fakeRepository.whenWrite(requestId, () -> {
    realRepository.writeStableRequest(requestId, fingerprint);
    throw new SimulatedLostResponseException();
});

Outcome first = service.create(requestId, fingerprint);
assertEquals(Outcome.UNKNOWN, first);

Outcome afterReconciliation =
    service.reconcile(requestId, fingerprint);
assertEquals(Outcome.ALREADY_PROCESSED, afterReconciliation);

assertEquals(1, businessSink.countByRequestId(requestId));
~~~

Names like **`fakeRepository`, `service`, `Outcome`, `SimulatedLostResponseException`, and `businessSink`** are **illustrative test doubles and domain types**, not Java Driver 4.x classes. Define them to match your project architecture.

**What is verified is the business outcome**: after an ambiguous initial call, reconciliation resolves the request without duplicating side effects. Never coerce timeouts into “success” without data verification.

### 16.3. LWT `false` after retry is a distinct test case

~~~sql
INSERT INTO idempotency_lab.claim_by_business_key (
    tenant_id, business_key, request_id,
    payload_fingerprint, state
) VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

Scenario:

1. Initial attempt returns **`[applied]=true`** on the server, but the client loses the response.
2. Retry with the same business key receives **`[applied]=false`**.
3. Java reads the row and compares `request_id` and `fingerprint`.
4. If same logical request, return **`ALREADY_PROCESSED`** per contract.
5. If different, return **`CONFLICT`**.
6. If the read also times out or replicas are unavailable, retain **`UNKNOWN`**.

Never write tests asserting `false == conflict` on every retry. Tests must distinguish **same request** from **different request**.

## 17. Bounded Load and Fault-Injection Testing

### 17.1. Test matrix

| Scenario | What to verify | Risk to avoid |
|---|---|---|
| **Repeated stable `INSERT`** | Final row matches expected state | Checking row count while ignoring timestamps/TTLs |
| **Repeated counter/list** | Two sends produce two effects | Setting `true` just to reduce error counts |
| **`WriteTimeout`** | Never assumed not written | Minting a new ID on retry |
| **Lost response** | Reconciliation locates the original request | Treating `false` as a conflict |
| **`Overloaded`** | Backpressure/shedding works; retries stay bounded | Retry storms and queue bloat |
| **Slow replica** | Deadlines, CL, retry budgets, and write state | Silent CL downgrades |
| **Concurrent writers** | Stale retries never overwrite newer versions | Assuming identical-value writes are always safe |
| **Near-expiry TTL** | Expiration matches contract after retries | Extending TTL or deleting prematurely |
| **Multi-DC LWT** | Serial CL matches invariant scope | Using `LOCAL_SERIAL` out of habit |
| **Downstream event** | No duplicate emission on DB retry | Confusing CQL flags with exactly-once |

Run all tests using **test request/tenant IDs** under bounded concurrency and QPS limits. Never induce `WriteTimeout` or sever production networks to prove behavior.

### 17.2. Critical test for interleaved writers

Illustrative ordering:

~~~text
A sets status=PAID, timestamp 100.
B sets status=REFUNDED, timestamp 110.
A retries with timestamp:
  (a) fixed 100
  (b) newly generated 120
~~~

**Expected behavior under timestamp rules:** case (b) overwrites B's valid update; case (a) does not in this simple scenario because its timestamp is lower. Even then, if B shared A's timestamp, or different tombstones/TTLs or domain rules applied, other anomalies can arise.

Never claim “the data stays identical after retries, so it's safe” without including **concurrent writers** in your test criteria.

### 17.3. Scope test conclusions accurately

A passing test proves semantics only for the tested **cluster version, topology, data fixture, CL, and fault model**. Test reports should record:

~~~yaml
suite: "idempotent-flag-integration"
run_id: "lab-2026-11-21-example"
cassandra_version: "<exact-version>"
java_driver_version: "<exact-version>"
jdk_version: "<exact-version>"
topology:
  datacenter: "dc1"
  nodes: 3
  replication_factor: 3
request:
  kind: "stable-insert"
  consistency: "LOCAL_QUORUM"
  idempotent_flag: true
  stable_primary_key: true
  stable_write_timestamp: true
verification:
  repeated_writes: 2
  row_state_matches_expected: true
  result: "PASS"
scope:
  concurrent_writer_tested: false
  network_fault_tested: false
~~~

This is an **application-defined report format**, not Cassandra configuration. Never log secrets, raw bind values, sensitive idempotency tokens, or user payloads.

## 18. Diagnosing Data Corruption Caused by Retries

### 18.1. Questions to answer

1. Was a **logical request ID** generated before the first attempt?
2. How many physical attempts occurred across driver, app, gateway, and caller?
3. Did all attempts share identical primary key, payload, timestamp, and TTL?
4. Did speculative execution fire extra attempts?
5. When did another writer modify the row?
6. Did the query use `IF`/LWT or a normal write? Was **`[applied]`** coerced to `false` on error?
7. What were the actual CL and serial CL? What was RF/DC/node health?
8. Did hot partitions, GC pauses, disk I/O, compaction, or repair trigger timeouts?
9. Were external side effects invoked twice?
10. Do backups, CDC, or logs support reconciliation and incident recovery?

### 18.2. Useful `nodetool` commands and signals

On authorized Cassandra nodes (syntax varies by version):

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool tablestats idempotency_lab.event_by_request
nodetool tablehistograms idempotency_lab event_by_request
~~~

Correlate with node logs, GC/heap/native RSS, free disk/latency, pending/dropped messages, read/write/CAS latency, coordinator/replica logs, and application traces.

**Compaction** can raise disk pressure and **repair** competes for I/O/network while surfacing late-converging data. However, **never run repair to “delete duplicate orders”**: two orders with different `requestId`s are two valid rows by primary key, and Cassandra has no idea they came from one user action.

### 18.3. Controlled structured log sample

~~~json
{
  "event": "cassandra_write_outcome_unknown",
  "operation": "event_by_request.insert",
  "request_id_hash": "hash-example-72",
  "statement_idempotent": true,
  "consistency": "LOCAL_QUORUM",
  "exception_class": "WriteTimeoutException",
  "application_attempt": 1,
  "driver_attempts_observed": 1,
  "logical_deadline_remaining_ms": 185,
  "reconciliation_required": true
}
~~~

This is an **illustrative JSON format**, not default driver logging. Record only approved hashes/correlation IDs—never customer UUIDs, passwords, tokens, payment details, raw payloads, or raw `BoundStatement` values.

### 18.4. Remediation runbook

~~~mermaid
flowchart TD
    A["Detect anomalous duplicates / retries"] --> B["Isolate logical request and attempts"]
    B --> C{"Write has unclear side effects?"}
    C -->|Yes| D["Hold UNKNOWN, preserve evidence"]
    C -->|No| E["Compare key/value/timestamp/TTL/flag"]
    D --> E
    E --> F["Read row at right CL; compare fingerprint"]
    F --> G{"Sufficient evidence to conclude?"}
    G -->|No| H["Pause replay; reconcile / incident"]
    G -->|Yes| I["Classify SAME_REQUEST/CONFLICT/COMPLETED"]
    I --> J["Fix retry policy, test faults, monitored rollout"]
~~~

When an incident involves lost funds or wrong orders, prioritize **preserving evidence and business remediation** rather than just flipping a flag and closing the ticket. Changing `setIdempotent` prevents future bad retries but does not fix already-corrupted data or duplicate side effects.

## 19. Common Anti-Patterns

| Anti-pattern | Consequence | Replacement |
|---|---|---|
| **`setIdempotent(true)`** on every mutation | Counters/lists/side effects can replay | Review each operation by semantics |
| Assuming every `INSERT` is idempotent | Timestamps/TTLs/retry IDs can shift | Stable keys, values, timestamps, concurrency tests |
| Generating a new UUID after timeout | One logical event creates multiple rows | Generate ID once per request and reuse |
| Treating **`WriteTimeout` = not written** | Retries cause duplicates/overwrites | Hold `UNKNOWN`; reconcile by primary key |
| Treating **LWT `false` = competitor won** | Misses the client's own successful first attempt | Compare request ID/fingerprint and state |
| Catching exceptions and returning **`false`** | Conflates business conflict with infra failure | Three-state domain outcome with `UNKNOWN` |
| Marking counters/list appends safe | Double-increments/appends on retry/speculation | `setIdempotent(false)`, dedup event modeling |
| `default-idempotence=true` service-wide | Silent unsafe retries on new queries | Conservative default, explicit per-statement flags |
| Calling setter and discarding returned statement | Flag/CL never takes effect | Assign/chain immutable statement methods |
| Switching CL to `ONE` on retry | Violates consistency contract | Keep contractual CL; fix nodes/load |
| Downgrading `SERIAL` to `LOCAL_SERIAL` for timeouts | Weakens multi-DC uniqueness invariant | Review invariants and topology |
| Retrying immediately on `Overloaded` | Retry storms and queue bloat | Load shedding/backoff, bounded in-flight |
| Retrying in driver + app + gateway without shared budget | Attempt count explodes | One end-to-end policy, track physical attempts |
| Using large batches as multi-table transactions | No workflow rollback; coordinator overload | Small semantic batches, outbox/reconciliation |
| Giant sets/maps/lists in one partition | Large mutations, tombstones, compaction pressure | Rows/buckets shaped by access patterns |
| Calling **`Thread.sleep`** in async callbacks | Blocks I/O threads; hurts tail latency | Non-blocking scheduler and deadlines |
| Closing `CqlSession` per HTTP request | Connection churn and high latency | Reuse session across service lifecycle |
| Testing single-node and assuming RF=3/multi-DC safety | Misses quorum and replica failures | Dedicated representative cluster suite |
| Running repair to “fix duplicate orders” | Replicas legitimately keep two distinct rows | Domain deduplication and reconciliation |

## 20. Scenario Exercises and Solutions

### Exercise 1 — Does setting `true` make addition safe?

A developer writes:

~~~java
BoundStatement request = incrementCounter.bind(tenantId)
    .setIdempotent(true);
~~~

**Question:** Is `UPDATE total = total + 1` safe when the driver retries?

**Suggested answer:** No. The flag only signals intent to the driver; it does not alter the mutation. On an ambiguous outcome, a retry can increment twice. Use `false`, avoid blind manual retries, and design event-level deduplication.

### Exercise 2 — `INSERT` with the same primary key

An app `INSERT`s with the same primary key, payload, and `created_at`, yet generates a fresh write timestamp on each retry.

**Question:** Is this enough to guarantee idempotency alongside concurrent writers?

**Answer:** Not yet. A late retry with a newer timestamp can overwrite a valid subsequent mutation. You need stable timestamp/version rules, concurrency tests, and reconciliation where appropriate; a single fixed-key assignment does not prove full workflow safety.

### Exercise 3 — TTL and expiration

A record is written with **`USING TTL 120`**. After 90 seconds, the client retries the same CQL because it missed the first ACK.

**Question:** Can this shift expiration away from the intended time?

**Answer:** Yes, there is a risk; relative TTLs and retry semantics must be verified. If expiration must be measured from the initial request, store an absolute timestamp/expiry strategy instead of assuming retries are safe.

### Exercise 4 — `WriteTimeout` at `LOCAL_QUORUM`

RF = 3; one replica returns ACK, two stall. The coordinator returns `WriteTimeout`.

**Question:** Can you conclude no replica wrote the data?

**Answer:** No. Some replicas may have applied the mutation. Retry only if idempotent, keeping request identity intact, and reconcile instead of creating a new row.

### Exercise 5 — One `POST` creates two orders

An HTTP client retries after a timeout. On every execution, the service calls `UUID.randomUUID()` to generate a new `orderId` before `INSERT`.

**Question:** Why didn't `setIdempotent(true)` on the `INSERT` prevent two orders?

**Answer:** The two attempts used **two different primary keys**. The idempotency key must belong to the logical request, persist across HTTP/gateway/service retries, and be checked alongside a payload fingerprint.

### Exercise 6 — LWT `false` after retry

Attempt 1 of **`INSERT IF NOT EXISTS`** applied on the server, but the response dropped. Attempt 2 gets **`[applied]=false`** and sees the same request ID in the row.

**Question:** Should the service return a conflict error?

**Answer:** Not by default. If the stored row matches the initial request's fingerprint, it is a replay of the same request. Reconcile state/workflow, return an idempotent success per contract, and suppress duplicate side effects.

### Exercise 7 — Async error handling

A service writes:

~~~java
return session.executeAsync(statement)
    .thenApply(page -> parseApplied(page))
    .exceptionally(error -> false);
~~~

**Question:** Where is the bug?

**Answer:** It turns timeouts, network drops, and overload into conditional `false`. Preserve the exception/`UNKNOWN` state and invoke reconciliation; return `true`/`false` only from a valid LWT response.

### Exercise 8 — Counter test returns 2

A test uses a fresh `tenantId`, executes the same counter `UPDATE` twice, and reads `total=2`.

**Question:** Why doesn't this contradict setting `false` on the driver statement?

**Answer:** The code explicitly sent the statement twice. `setIdempotent(false)` does not stop the application from calling `execute` repeatedly; it only informs automatic driver/policy retry mechanisms.

### Exercise 9 — Three-layer stacked retries

Gateway, service, and driver each configure retries. The app sees `application_retry_count=0` and concludes the DB received only one attempt.

**Question:** Is that conclusion valid?

**Answer:** No. Measure logical vs. physical attempts, driver retries/speculation, service retries, gateway retries, and caller retries. An app counter of 0 does not prove zero physical retries occurred.

### Exercise 10 — Dropping CL on timeout

An endpoint promises `LOCAL_QUORUM` writes. After `WriteTimeout`, a retry policy falls back to `LOCAL_ONE` to raise success rates.

**Question:** What is the risk?

**Answer:** It breaks the contractual acknowledgment guarantee without fixing replica, disk, or compaction causes. Never downgrade consistency silently; diagnose availability or use an explicitly approved degradation mode.

### Exercise 11 — Speculative execution with list append

The driver enables speculative execution, and a list-append statement is marked `true`.

**Question:** What can go wrong?

**Answer:** A single logical request can trigger concurrent executions that both append, duplicating list elements. Mark it `false` and avoid non-idempotent mutations if speculative or retried execution is desired.

### Exercise 12 — Query-driven tables and retries

A tenant has a multi-GiB event partition. The team increases page size/timeouts, sets `true`, and retries 5 times on `ReadTimeout`.

**Question:** Why doesn't this fix the root cause?

**Answer:** Queries still pound the same large partition's replicas; tombstones, SSTables, and compaction I/O stay heavy. Re-bucket/shard around access patterns, shed load, and optimize the read path. The idempotent flag cannot optimize a bad data model.

### Exercise 13 — LWT protects uniqueness, yet emails duplicate

`INSERT IF NOT EXISTS` succeeds and sends an email. The caller loses the HTTP response and retries; the app receives `false` yet sends the email again anyway.

**Question:** Did the LWT fail?

**Answer:** Not necessarily. The LWT protected the claim row in Cassandra, not the email service. Use an idempotency key at the email sink/outbox or track workflow state and reconcile rather than firing emails solely off `false`.

### Exercise 14 — `false` on a `SELECT`

A read-only `SELECT` with fixed bind values and no side effects is set to `setIdempotent(false)`.

**Question:** Does this corrupt data, and what is the trade-off?

**Answer:** It is conservative and will not cause bad writes, yet it restricts policy retries/speculation and can raise user-visible errors or tail latency during transient glitches. Review and set `true` once proven safe.

### Exercise 15 — A different payload reuses a key

Two HTTP requests from the same tenant share the **same idempotency key** but carry different payment payloads.

**Question:** Can the second request return `ALREADY_PROCESSED`?

**Answer:** No. Compare fingerprints/canonical payloads and authorization; key reuse with different content is a conflict or contract violation. CQL flags cannot resolve client key misuse.

### Exercise 16 — Single-node test vs. multi-DC production

A team runs `INSERT`/`SELECT` tests on a single RF=1 Cassandra container and declares `LOCAL_SERIAL` preserves global uniqueness across multi-DC writers.

**Question:** What is missing?

**Answer:** Testing concurrent writers from multiple DCs, realistic RF/DC, `SERIAL` vs. `LOCAL_SERIAL`, network partitions, and exact driver versions. Single-node runs verify basic syntax, never multi-DC invariants.

## 21. Code Review and Operations Checklist

- [ ] Define the **logical operation** and idempotency key at the API/domain layer.
- [ ] Keep request ID, partition key, and payload fingerprint constant across all allowed attempts.
- [ ] Distinguish **storage idempotence, response idempotence, and workflow idempotence**.
- [ ] Never set `true` on counters, list appends, or relative mutations unproven to be safe.
- [ ] For `INSERT`/`UPDATE`/`DELETE`, review timestamps, TTLs, tombstones, concurrent writers, and domain states.
- [ ] Never assume LWTs are blindly retryable; handle **`[applied]` `true`/`false`/`UNKNOWN`**.
- [ ] Read and reconcile rows by key after timeouts when required—never mint random replacement IDs.
- [ ] Never coerce exceptions into boolean `false` in async or repository layers.
- [ ] Capture/chain return values from immutable statement setters.
- [ ] Verify `default-idempotence` and execution profiles on your pinned driver version.
- [ ] Set `true` explicitly on **reviewed statements**; keep `false` conservatively when uncertain.
- [ ] Review retry policies and speculative execution, bounding physical attempts.
- [ ] Enforce **end-to-end deadlines**, backoff/jitter, retry budgets, and circuit/admission controls.
- [ ] Never retry `Overloaded` immediately or silently downgrade CL outside business contracts.
- [ ] Enforce bounded in-flight counts, finite queues, and per-tenant/endpoint rate limits where needed.
- [ ] Verify RF/DC, CL, local datacenter, and serial CL for multi-DC LWTs.
- [ ] Ensure partition keys fit queries and collections, mutations, batches, and partitions stay bounded.
- [ ] Monitor coordinators/replicas, disk/GC, tombstones, compaction, and repair before increasing retries.
- [ ] Maintain integration tests for replaying identical mutations, negative counter/list tests, and lost-response tests.
- [ ] Run multi-node lab fault injection covering `UNKNOWN` outcomes and reconciliation.
- [ ] Test concurrent writes, near-expiry TTLs, and external duplicate side effects.
- [ ] Share `CqlSession`/`PreparedStatement` across the service lifecycle rather than creating them per HTTP request.
- [ ] Keep secrets, raw bind values, payment payloads, and user identifiers out of logs.
- [ ] Document driver/Cassandra versions, topology, RF/CL, attempt counts, and untested scope in test reports.

## 22. Summary

**Idempotency is not a property the Java Driver can deduce from a CQL keyword.** It is a contract covering **re-execution of the same logical operation**, shaped by primary keys, bound values, timestamps/TTLs, concurrent writers, conditional outcomes, and external side effects.

Calling **`setIdempotent(true)`** tells the driver that your team **has verified the operation is safe to replay** under configured policies—it does not make an unsafe operation safe. Counter increments, list appends, and side-effecting workflows require different patterns; LWTs can return **`[applied]=false` after an earlier attempt succeeded with a lost response**. On `WriteTimeout`/`WriteFailure`, the outcome may be **`UNKNOWN`** and must never be assumed unwritten.

In Apache Cassandra, correctness requires combining **stable idempotency keys, partition-key-aligned tables, CL matched to RF/DC, bounded retries/deadlines, backpressure, and reconciliation**. During failures, compaction, repair, and replica health affect completion rates, but they never replace domain-level deduplication. Enable `true` only after **proving the semantics**, testing repeated execution, and building reconciliation for ambiguous outcomes.
