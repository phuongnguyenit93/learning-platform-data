# Retries with Timestamps/TTL and the Risk of Changing Business Outcomes

## 1. Why Might "Retrying the Same Command" Not Have the Same Meaning?

In **Apache Cassandra**, a **distributed wide-column** database, a Java application can send a mutation to a coordinator, which forwards it to replicas according to the **replication factor (RF)** and **consistency level (CL)**. If the client hits a timeout, loses connection, or receives an error from the coordinator, the application typically wants to **retry** to complete the operation.

However, there is a crucial distinction:

> **Retrying does not mean the prior mutation definitely failed.** The first write may already have been accepted by some replicas, or even satisfied the write quorum while the response was lost. Replaying it can create another cell version with a **new timestamp**, a **new TTL**, or a **new business side effect**.

For Cassandra, two kinds of metadata must be watched:

- **Mutation timestamp** (microseconds since the Unix epoch): used to arbitrate versions of the same cell under **last-write-wins (LWW)**.
- **TTL** (seconds): determines how long a cell version stays alive, counted from when that version is written rather than a "fixed deadline" preserved automatically across every retry.

Example of an order-state service:

1. `E1`: update `state = 'PENDING'` is sent at 10:00 and times out.
2. `E2`: update `state = 'PAID'` is sent at 10:01 and completes.
3. The application **rebuilds and sends E1** at 10:02 with a new timestamp larger than E2.

If both touch the same cell and the E1 retry carries the largest timestamp, Cassandra can display **`PENDING`** again, even though that is the **older** business event. The issue is not a flaw in LWW: the system is following the timestamp-comparison rule with the values supplied, unaware of business order.

This lesson aims to separate **protocol/driver-level retries** from **business-operation replays**, build CQL/Java examples, and design systems so retries do not accidentally invert event order or extend TTL-bound data.

## 2. A Write Timeout Means "Unknown Outcome", Not "Unwritten"

A Cassandra write request passes through multiple steps. The diagram below illustrates `RF = 3`; the actual number of acknowledgments required depends on CL:

```text
  Java client             Coordinator             Replica A/B/C
      |                         |                        |
      +---- UPDATE ------------>|                        |
      |                         +------ mutation ------->|
      |                         |<----- some ACKs -------+
      |                         |
      |      (network drop or client timeout)
      X<------ response? -------|
      |
      +---- RETRY? ------------>|    Attempt 1 may have already
                                |    succeeded partially or met CL.
```

Several states must be kept distinct:

| Situation | What the client knows | Risk on replay |
|---|---|---|
| Request not yet sent over network and confirmed unexecuted | No server effect yet | Safe to send initially |
| Client timeout after sending request | **Uncertain** how many replicas applied it | Data may already exist |
| Server reports write timeout | Required ack count was not met in time | Some replicas may still have written |
| Request met CL and ACK reached client | Write confirmed per CL | Does not guarantee version wins against a larger timestamp |
| LWT timeout / unknown | Uncertain whether condition was applied | Unchecked retry could transition state again |

**Never infer "write timeout = rollback."** Cassandra does not provide conventional transaction rollback for writes that already reached replicas. When business preconditions matter, you need a **post-timeout reconciliation strategy** using business keys, event IDs/versions, and suitable consistency levels.

## 3. Three Kinds of Retries Can Produce Three Different Outcomes

Not all "retries" share the same semantics:

| Retry mechanism | What can change? | What must be controlled? |
|---|---|---|
| **Driver retries the same execution** per policy | Coordinator/network path; actual timestamp/expiration handling depends on driver/server behavior and version | Idempotency flag, retry policy, logs, timeouts |
| **Application calls the same prepared statement again** | A new statement or timestamp generator may assign a new mutation timestamp; relative TTL may be recomputed | Preserve the same event context; do not mint a fresh ordering |
| **Replaying events from a queue/DLQ** minutes/hours later | Large delay, original TTL expired or event already stale; newer events already processed | Event ID, business version, absolute deadline, conditional state transitions |

Common failure example:

```text
E1: ORDER_CREATED  -> timestamp 100  -> status = PENDING
E2: PAYMENT_DONE   -> timestamp 200  -> status = PAID
retry E1           -> timestamp 300  -> status = PENDING

State after reconciliation: PENDING (timestamp 300),
even though true business order was E1 before E2.
```

**A larger timestamp does not necessarily mean a newer event.** When independent services use their own clocks or their own driver timestamp generators, clock skew pushes LWW order further away from business order. Do not try to fix this by raising CL to `QUORUM` or `ALL`: CL governs replica requirements, not state ordering.

## 4. CQL Hands-On: Retrying an Old Event Rolls Back State

Run only in a **test keyspace** selected with `USE <keyspace>;`. UUIDs must be unused; all fixed timestamps in examples are in **microseconds** for illustration, not for production use.

### 4.1. Create a Table for Current-State Queries

```sql
CREATE TABLE IF NOT EXISTS retry_order_state_by_id (
    order_id uuid PRIMARY KEY,
    state text,
    last_event_id text,
    last_source text
);
```

This table optimizes the query "give me the current state of `order_id`." It is a **latest-state table**; if strict protection against state regression is needed, you must add coordination/conditional logic rather than relying solely on this schema.

### 4.2. E1 and E2 Processed in Correct Order

```sql
INSERT INTO retry_order_state_by_id (
    order_id, state, last_event_id, last_source
)
VALUES (
    11111111-1313-4131-8131-111111111111,
    'PENDING', 'E1', 'checkout'
)
USING TIMESTAMP 1700000000001000;

UPDATE retry_order_state_by_id
USING TIMESTAMP 1700000000002000
SET state = 'PAID',
    last_event_id = 'E2',
    last_source = 'payment'
WHERE order_id = 11111111-1313-4131-8131-111111111111;

SELECT state, writetime(state),
       last_event_id, writetime(last_event_id)
FROM retry_order_state_by_id
WHERE order_id = 11111111-1313-4131-8131-111111111111;
```

Result: `state = 'PAID'` and `writetime(state) = 1700000000002000`, because E2 has a higher timestamp than E1.

### 4.3. Replaying E1 with a New Timestamp

```sql
-- Application bug: E1 retry is given a timestamp HIGHER than E2.
UPDATE retry_order_state_by_id
USING TIMESTAMP 1700000000003000
SET state = 'PENDING',
    last_event_id = 'E1-retry',
    last_source = 'checkout'
WHERE order_id = 11111111-1313-4131-8131-111111111111;

SELECT state, writetime(state), last_event_id
FROM retry_order_state_by_id
WHERE order_id = 11111111-1313-4131-8131-111111111111;
```

Notable result: `state = 'PENDING'` and `writetime(state) = 1700000000003000`. The mutation followed **LWW rules accurately**, yet the value is **wrong relative to the business flow** where payment had already completed.

### 4.4. When the Retry Preserves the Original Timestamp

On a separate key, simulate replaying E1 with **E1's timestamp preserved**:

```sql
INSERT INTO retry_order_state_by_id (order_id, state, last_event_id)
VALUES (
    22222222-1313-4131-8131-222222222222,
    'PENDING', 'E1'
)
USING TIMESTAMP 1700000000001000;

UPDATE retry_order_state_by_id
USING TIMESTAMP 1700000000002000
SET state = 'PAID', last_event_id = 'E2'
WHERE order_id = 22222222-1313-4131-8131-222222222222;

-- Replay E1 while reusing E1's original write timestamp, lower than E2.
UPDATE retry_order_state_by_id
USING TIMESTAMP 1700000000001000
SET state = 'PENDING', last_event_id = 'E1'
WHERE order_id = 22222222-1313-4131-8131-222222222222;

SELECT state, writetime(state), last_event_id
FROM retry_order_state_by_id
WHERE order_id = 22222222-1313-4131-8131-222222222222;
```

Result: `PAID@1700000000002000` continues to win. This is **one way to reduce the risk of old replays inverting order**, yet **it is not sufficient as a general rule**: you must ensure timestamps genuinely represent business order, and handle clock skew, timestamp collisions, tombstones, and other writers.

## 5. Retrying TTL: The Same Number of Seconds Can Create a Different Expiration Deadline

With TTL, you must distinguish **relative duration** from **absolute deadline**.

If the business requirement is "token lives for 5 minutes from initial issuance":

```text
12:00  issue token -> write TTL 300       Business deadline: 12:05
12:02  app constructs a new write of
       the same token with TTL 300;
       new timestamp wins
                                          New TTL deadline: ~12:07
12:05  token should no longer be usable
       yet the new cell may still be live
```

The issue is not the arithmetic of `300 seconds`: it is the behavior of **setting a fresh relative TTL from the new write**. When a replayed request is rebuilt, Cassandra can establish a new expiration. If the business deadline must remain unchanged, store and enforce that deadline in the application layer.

### 5.1. CQL Hands-On on a TTL Cell

```sql
CREATE TABLE IF NOT EXISTS retry_token_by_id (
    token_id uuid PRIMARY KEY,
    expires_at timestamp,
    token_hash text
);

-- expires_at: business milestone, stored separately without TTL in this test table.
INSERT INTO retry_token_by_id (token_id, expires_at)
VALUES (
    33333333-1313-4131-8131-333333333333,
    '2030-01-01T12:05:00Z'
);

-- Token lives 300 seconds from this write.
UPDATE retry_token_by_id
USING TTL 300
SET token_hash = 'example-hash-not-a-token'
WHERE token_id = 33333333-1313-4131-8131-333333333333;

SELECT token_hash, ttl(token_hash) AS remaining_s,
       writetime(token_hash) AS write_us, expires_at
FROM retry_token_by_id
WHERE token_id = 33333333-1313-4131-8131-333333333333;
```

The `expires_at` field in the example is purely an **independent illustrative milestone**; in a real application, compute it from a **trusted issuance time** rather than hardcoding 2030. Writing `token_hash` again with `USING TTL 300` can make `ttl(token_hash)` near 300 seconds even though `expires_at` did not change. Use `expires_at` to evaluate whether the token is past its business deadline.

Simulate the application intentionally re-issuing the mutation afterward:

```sql
-- Run on the still-live test key after waiting for a short interval.
UPDATE retry_token_by_id
USING TTL 300
SET token_hash = 'example-hash-not-a-token'
WHERE token_id = 33333333-1313-4131-8131-333333333333;

SELECT token_hash, ttl(token_hash), writetime(token_hash), expires_at
FROM retry_token_by_id
WHERE token_id = 33333333-1313-4131-8131-333333333333;
```

If the new write wins by mutation timestamp, remaining TTL typically **resets close to 300 seconds**, even when the `token_hash` string is unchanged. This is the **risk of refreshing TTL via a new mutation**; not every internal driver retry necessarily behaves this way.

### 5.2. What About Retrying with the Same Mutation Timestamp?

Even if an application reuses **the same timestamp** on a command with TTL, never assume **the expiration deadline is guaranteed to stay unchanged**. Expiration metadata depends on write processing and the retry path; equal-timestamp conflicts also invoke cell tie-breaking rules. A statement with the same value, timestamp, and TTL **does not automatically carry an immutable absolute `expires_at`**.

Therefore, when reasoning about idempotency with TTL, separate:

- **Value idempotency:** resending the same `token_hash` yields the same string.
- **Version idempotency:** not minting a new timestamp that lets an older event win.
- **Lifetime idempotency:** not accidentally pushing back the deadline for the same entity.
- **Business idempotency:** not issuing a new token, not charging/posting twice, and not regressing state.

A retry path is only safe when it preserves **the exact invariants the business requires**, not merely when `SELECT` shows the same value.

## 6. `USING TIMESTAMP`, Driver Generator, and Coordinator During a Retry

Mutation timestamps can be supplied through multiple paths:

1. CQL `USING TIMESTAMP <epoch_micros>` explicitly set by the application.
2. Statement timestamp via Java Driver 4.x, e.g., `BoundStatement.setQueryTimestamp(long)`.
3. Driver timestamp generator, if the client is configured to assign timestamps.
4. Cassandra coordinator when the request carries no client-supplied timestamp.

| Retry style | Characteristics to watch |
|---|---|
| Replaying CQL with a fixed `USING TIMESTAMP 1700000000001000` | Requested timestamp stays fixed; **TTL and business semantics still need separate evaluation** |
| Creating a new statement and calling `setQueryTimestamp(nowMicros)` | An old event can receive a new timestamp larger than a later event |
| Using the driver's timestamp generator | Monotonicity within one generator does not guarantee order across hosts or services |
| Letting the coordinator assign timestamps | Coordinators have distinct clocks; retrying through another node can alter LWW order |

Never assume "retries always generate a new timestamp," nor assume "driver retries always keep the same timestamp": distinguish **retrying the same execution** from **the application building a new command**, as well as generator config, driver version, and actual request path. When debugging, collect enough evidence to know which mutation carried which timestamp.

**Clock skew** makes matters worse: a client with a fast clock creates future timestamps, preventing valid subsequent updates from winning. Synchronize application host clocks and Cassandra nodes via NTP/chrony or equivalent services.

## 7. Driver "Idempotence" Does Not Automatically Make Business Logic Safe

At the database layer, an operation is often called **idempotent** if repeating it with the same intent produces no different final result for the data of interest. For instance, `SET state = 'PAID'` looks safer than `counter = counter + 1`, yet in practice you still must consider **timestamps, TTL, and event order**.

Java Driver 4.x supports marking **statement idempotence** so retry and speculative execution policies can decide when re-sending is permitted. That flag is a **developer declaration**, not a transaction guarantee that automatically deduplicates or preserves deadlines.

| Statement | How might it be evaluated? | Risk to control |
|---|---|---|
| `UPDATE ... SET state = 'PAID'` with stable version/order | May be value-idempotent | Old replay / new timestamp can overwrite newer state |
| `INSERT ... USING TTL 300` | Must inspect carefully | Rewriting later can alter remaining lifetime |
| `UPDATE counter SET count = count + 1` | **Not** idempotent if resent | Can double-increment |
| `INSERT ... VALUES (..., now())` | Depends on intent/execution | Retry may generate a different key or event |
| State transition with `IF state = ...` | Conditional, yet timeout yields unknown outcome | Must read/reconcile state and event ID |

**Practical rule:** mark a statement idempotent only when you know the exact behavior of the request **when executed multiple times**, including expiration and interactions with other writers. Never turn on retries for every write just because the CQL looks like `UPDATE SET`.

### Retry Policies and Speculative Execution

Retries can trigger on timeouts, connection failures, or unavailable responses depending on policy. **Speculative execution** can send duplicate requests to another coordinator when a request is slow, so idempotency applies there too. That is very different from "a retry only happens when Java calls `execute()` a second time."

Increasing retry counts to mask an unstable cluster is discouraged: excessive retries can overload struggling nodes further (*retry storm*). Bound retry counts, use backoff with jitter, measure latency/error rates, and separate transient errors from schema/policy errors that retries cannot fix.

## 8. Java Driver 4.x: Attaching an Event's Timestamp to a Statement

The snippet below shows how **not to mint a new timestamp for the same event** when the application explicitly re-executes it. It assumes the source supplying `eventTimestampMicros` is valid as a business-order version; that guarantee **must be enforced outside Cassandra**.

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class OrderStateWriter {
    private final CqlSession session;
    private final PreparedStatement update;

    public OrderStateWriter(CqlSession session) {
        this.session = session;
        this.update = session.prepare(
            "UPDATE retry_order_state_by_id " +
            "SET state = ?, last_event_id = ?, last_source = ? " +
            "WHERE order_id = ?"
        );
    }

    public void writeEvent(UUID orderId, String state, String eventId,
                           String source, long eventTimestampMicros) {
        BoundStatement mutation = update.bind(state, eventId, source, orderId)
            .setQueryTimestamp(eventTimestampMicros);

        // Do not mark idempotent mechanically. Only enable automatic
        // retries once end-to-end system semantics are proven safe.
        session.execute(mutation);
    }
}
```

In Java Driver 4.x, `setQueryTimestamp(...)` returns a new statement per its immutable API. `eventTimestampMicros` must be in **microseconds**, not `System.currentTimeMillis()` (milliseconds).

**Conditional benefit:** replaying the same `eventId` with its original timestamp will not simply receive a newer timestamp just because a delivery queue was delayed. **However**:

- If two distinct events share the same timestamp, Cassandra uses internal tie-breaking and **does not know** which business version is right.
- If timestamps come from unsynchronized service clocks, order can still be wrong.
- If a cell was deleted by a tombstone with a higher timestamp, an old replay will not resurrect the data.
- If the event has a TTL, stabilizing the timestamp **does not mean** stabilizing the expiration deadline.
- Do not arbitrarily use `setQueryTimestamp()` on **LWTs/counters**; those operations have separate constraints.

For payment states, setting timestamps from event time is only a viable design if event time is genuinely trustworthy. When **conditional state transitions** are required, prefer controlled versions and LWT rather than relying on clocks alone.

## 9. Java: Keeping Business Deadlines Fixed Across TTL Retries

A sturdier design for tokens stores an absolute `expiresAt` generated by a **trusted source** at issuance. Each mutation send computes the **remaining TTL**, rather than resending the original full TTL by default.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class TokenWriter {
    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement putExpiringHash;

    public TokenWriter(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.putExpiringHash = session.prepare(
            "UPDATE retry_token_by_id USING TTL ? " +
            "SET token_hash = ? WHERE token_id = ?"
        );
    }

    public void writeUntil(UUID tokenId, String hash, Instant expiresAt) {
        // Use the initial issuance deadline; do not recompute expiresAt from NOW.
        long secondsLeft = Duration.between(clock.instant(), expiresAt)
            .getSeconds(); // Truncates down to whole seconds.

        if (secondsLeft <= 0) {
            throw new IllegalStateException("Token already expired");
        }
        if (secondsLeft > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("TTL out of int range");
        }

        // Also check Cassandra version-specific TTL/expiration limits.
        session.execute(putExpiringHash.bind(
            Math.toIntExact(secondsLeft), hash, tokenId
        ));
    }
}
```

This example **reduces the risk of unintentionally extending TTL** when the application rebuilds the command after a delay. It **does not guarantee an exact-to-the-millisecond deadline**: TTL is tracked in whole seconds, network latency exists, and server/client clocks can drift. Therefore, **when consuming a token, always validate `expires_at` against business time**, and single-use tokens need an atomic consumption mechanism.

**Especially dangerous bug:** if 0 seconds remain, never send `USING TTL 0`. In Cassandra, **TTL 0 means no TTL**, not "expire immediately." The write path must reject or handle already-expired tokens per policy.

When retrying after a timeout, keep the same `tokenId`/`expiresAt` fixed and do not issue a new token if the operation is merely re-persisting the original one. Minting a fresh token is **a separate business event** and must be managed independently.

## 10. Idempotency Keys and Event Logs: Preventing Replays from Becoming New Actions

A stronger approach than merely "resending the same CQL" is assigning an **event ID or idempotency key** to each business event.

```text
Message broker / API
      |
      +-- eventId=E1, orderId=O1, version=1, state=PENDING
      |
      +-- eventId=E2, orderId=O1, version=2, state=PAID
      |
      +-- replay eventId=E1
               |
               +-- recognizes E1 was processed / version is stale
               +-- does NOT roll state back from PAID to PENDING
```

Example order event history table:

```sql
CREATE TABLE IF NOT EXISTS order_events_by_order (
    order_id uuid,
    event_id uuid,
    event_version bigint,
    state text,
    source text,
    PRIMARY KEY ((order_id), event_id)
);

-- Event ID stays constant across retries; IF NOT EXISTS helps detect
-- duplicates for this exact event row.
INSERT INTO order_events_by_order (
    order_id, event_id, event_version, state, source
)
VALUES (
    44444444-1313-4131-8131-444444444444,
    55555555-1313-4131-8131-555555555555,
    1, 'PENDING', 'checkout'
)
IF NOT EXISTS;
```

Read `[applied]` to know whether `INSERT IF NOT EXISTS` wrote the row. Note, however, that **deduplicating an event in one table and updating latest-state in another table do not automatically form an atomic transaction across two partitions**. If cross-table consistency is needed, design outbox/inbox patterns, processing states, replay/reconciliation jobs, or service-level orchestration.

**An Event ID does not replace a business version.** An event with a fresh ID that carries an old state can still roll back latest-state unless ordering is checked. Versions need a trusted issuer (a single writer, coordinator, or conditional update mechanism).

## 11. LWT: Using Compare-and-Set When State Order Matters

Cassandra's **Lightweight Transactions (LWT)** support conditional updates via `IF`, backed by Paxos. Instead of "whoever has the larger timestamp wins," you check the current business version before transitioning state.

Create a versioned test table:

```sql
CREATE TABLE IF NOT EXISTS versioned_order_state_by_id (
    order_id uuid PRIMARY KEY,
    version bigint,
    state text,
    last_event_id text
);

INSERT INTO versioned_order_state_by_id (
    order_id, version, state, last_event_id
)
VALUES (
    66666666-1313-4131-8131-666666666666,
    1, 'PENDING', 'E1'
)
IF NOT EXISTS;

-- Transition to PAID only if current version is 1.
UPDATE versioned_order_state_by_id
SET version = 2, state = 'PAID', last_event_id = 'E2'
WHERE order_id = 66666666-1313-4131-8131-666666666666
IF version = 1;
```

If `[applied] = true`, the transition took effect. Now a retry of E1 checking `IF version = 0` or `IF version = 1` will **not arbitrarily roll state backward** once `version` has advanced to 2.

### Retrying LWT After a Timeout

LWTs can also time out, leaving the client **uncertain whether the transition committed**. Never assume a timeout means `[applied] = false`. A conservative procedure:

1. Re-read the row at a consistency level appropriate for LWT flows and your Cassandra version.
2. Compare `version`, `last_event_id`, and state against **the exact event being retried**.
3. If the event was already applied, treat it as business-complete.
4. If the version has moved further ahead, treat the event as stale and do not overwrite backward.
5. If still at the expected version, retry the CAS within a bounded retry policy.

In LWTs, do not attach client-chosen `USING TIMESTAMP` as in regular writes. CAS protects conditions within supported scope at the cost of higher overhead and latency; avoid using it on every write when business logic only needs LWW.

## 12. Retries with TTL on Collections, Counters, Deletes, and Batches

Not all CQL mutations carry the same risks:

| Target / operation | What to watch on retry |
|---|---|
| **Scalar SET** on same cell | A new timestamp can change the winning version; TTL can set a new deadline |
| **Non-frozen Map/UDT** updating one key/field | Only the written element may receive a new timestamp/TTL; others keep their metadata |
| **Frozen collection/UDT** | Rewrite replaces the whole cell; TTL applies to the entire frozen value |
| **Counter** `+ 1` | Retries can double-count; do not treat as idempotent |
| **`DELETE`** | Tombstone has its own timestamp; retrying with a new timestamp can reorder delete vs. write |
| **Multi-mutation Batch** | Does not automatically handle dedupe or business order; batch timeouts still require reconciliation |
| **LWT with `IF`** | Timeout outcome is uncertain; check `[applied]` and state/version during reconciliation |

A common pitfall with `DELETE`: an application deletes a cell, hits a timeout, and later re-issues `DELETE` with a brand-new, much higher timestamp. The new tombstone can shadow a **valid write executed between the two deletes**. This is particularly dangerous when scheduled delete retries run without awareness of newer business activity.

For *counters*, do not apply `USING TTL` or `USING TIMESTAMP` the way scalar writes do. Counters have distinct semantics and limits; preventing double-increments requires event IDs/deduplication or an alternative counting design.

## 13. Replication, Consistency Levels, and Request "Success"

Suppose `RF = 3` and the application uses `CL = QUORUM` for writes. Quorum is typically two out of three replicas, yet:

- A quorum ACK **does not guarantee** a mutation with a lower timestamp beats an existing version with a higher timestamp.
- **Retries** may route through another coordinator, yet changing CL does not freeze timestamps or TTLs.
- Reading at `ONE` in the middle of mutations can observe transiently different versions due to out-of-sync replicas.
- **Repair** converges replicas per Cassandra's rules, yet cannot deduce that `PAID` should have beaten `PENDING` in business terms.
- Expired TTL creates expiration/tombstone metadata to prevent old values from reappearing; **compaction** and `gc_grace_seconds` govern safe reclamation, not preserving business deadlines on the application's behalf.

When investigating timeouts, separate **how many replicas ACKed**, **which cell version is winning**, and **whether the business event completed**. Those are three distinct questions—do not lump them into "did Cassandra write it or not?".

## 14. Diagnosing Retry Incidents Causing Lost Updates or Extended TTLs

### 14.1. Queries to Inspect Cells

```sql
SELECT order_id, state, writetime(state) AS state_write_us,
       last_event_id, writetime(last_event_id) AS event_write_us
FROM retry_order_state_by_id
WHERE order_id = 11111111-1313-4131-8131-111111111111;

SELECT token_id, token_hash, ttl(token_hash) AS ttl_s,
       writetime(token_hash) AS token_write_us, expires_at
FROM retry_token_by_id
WHERE token_id = 33333333-1313-4131-8131-333333333333;
```

`writetime()` reports **metadata of the currently observed live cell**, without listing past retries, losing versions, or tombstones. `ttl()` reports **remaining seconds** (or `null` if the cell has no TTL or is no longer live), not an absolute business deadline.

### 14.2. Checklist for Tracing a Retry

| Question | Evidence to gather |
|---|---|
| Was the retry issued by the driver or re-created by a service/queue? | Request ID, retry attempt count, stack trace, retry policy |
| Are you sure the prior attempt did not apply? | Coordinator timeout, ACKs, application logs, current stored data |
| Same `event_id` or newly minted event? | Idempotency key, broker offset/sequence |
| Did the mutation timestamp change? | `USING TIMESTAMP`, `setQueryTimestamp`, generator, `writetime` on live cell |
| Where were TTL and deadline computed? | `USING TTL`, `default_time_to_live`, issuer `expires_at` |
| Did another writer process a newer event in the meantime? | Business version, state transition logs |
| Did the client confuse seconds / milliseconds / microseconds? | Variable units, `Duration`/`Instant` conversions |
| Are tombstones or expired cells involved? | DELETEs, TTLs, SSTable tools, mutation history |
| Are replicas, CL, or clock skew involved? | RF/CL, node health, NTP offsets, repair status |
| Is there a retry storm? | Throughput, latency, timeout rate, retry limits and backoff |

**Never collect plaintext tokens or secrets** just for troubleshooting. Structured logs should contain pseudonymous IDs, relevant business keys, event IDs, microsecond timestamps, TTL seconds, UTC deadlines, retry counts, and outcome categories.

## 15. Implementing Safe Retries in a Java Application

A practical design can follow these principles:

1. **Classify operations:** state overwrites, create-once, counters, TTL caches, single-use tokens, LWTs. Do not apply one blanket retry policy to everything.
2. **Assign event IDs and versions at the business source:** preserve them across every replay. Never use "retry time" as the version of an old event.
3. **Establish an absolute deadline when business TTL applies:** store `expires_at` at issuance; before rewriting, compute remaining time and reject if expired.
4. **Pick a concurrency control strategy:** single-writer per key, LWT/CAS, or versioned event log + projector. Rely on plain LWW only when that matches intended semantics.
5. **Configure driver idempotence accurately:** review retry policies, speculative execution, timeouts, and retryable errors.
6. **Bound retries:** max attempts, jittered backoff, overall timeout, and dead-letter queues (DLQ). Never replay infinitely into an overloaded cluster.
7. **Reconcile after unknown outcomes:** read current state/version/event ID before deciding to issue a new mutation.
8. **Test with failure injection:** simulate dropped ACKs, coordinator timeouts, slow replicas, out-of-order events, clock skew, near-zero TTLs, and post-deadline retries.
9. **Make decisions observable:** log why an event was written, skipped as stale, treated as already applied, or routed to manual handling.

### Business-Based Decision Table

| Requirement | Recommendation |
|---|---|
| Cache that may refresh on every access | Actively renew TTL; accept "sliding expiration" semantics |
| Token that must expire strictly at issuance deadline | Immutable `expires_at` + remaining TTL + validation on use |
| Order must never regress from `PAID` to `PENDING` | Version/CAS or ordered projector; do not rely solely on request arrival timestamps |
| Events that may arrive duplicated from a queue | Event IDs, deduplication, and proper checkpoints/offsets |
| Counters / increment-decrement operations | No blind retries; source deduplication or alternative design |
| Idempotent-safe pure writes with no ordering requirement | Verify idempotency and retry policy before enabling |

## 16. Scenario Exercises and Answers

**Question 1.** E1 has timestamp `100`, E2 has timestamp `200`. A retry of E1 receives timestamp `300`. After reconciling the same cell, which event's value wins?

**Answer:** **The E1 retry** if no larger tombstone/version exists, because `300 > 200`. This can cause a business state regression.

**Question 2.** A client receives a write timeout. Can you conclude the write did not reach any replica?

**Answer:** **No.** Some or enough replicas may already have applied the mutation while the client failed to receive a clear acknowledgment.

**Question 3.** A token is issued at 12:00 with TTL 300; the app rebuilds and writes the mutation again with TTL 300 at 12:02 and the new mutation wins. Should the token be accepted until 12:07?

**Answer:** The cell may remain live until ~12:07, yet the **true business deadline** from initial issuance is still 12:05. You must check immutable `expires_at`.

**Question 4.** If a replay reuses the same mutation timestamp while re-issuing `USING TTL 300`, is the absolute expiration time guaranteed to stay unchanged?

**Answer:** **Never assume that.** TTL is relative lifetime metadata; execution paths and conflict/tie-breaking rules must be verified, and business deadlines must be preserved independently.

**Question 5.** Can `USING TTL 0` be used to expire a token immediately when remaining time equals 0?

**Answer:** **No.** `TTL 0` means **no TTL**. Reject or handle the already-expired token.

**Question 6.** Does marking a statement `isIdempotent = true` in the Java Driver automatically ensure a payment API will not process twice?

**Answer:** **No.** That driver flag only informs retry/speculative-execution decisions; business idempotency requires event IDs, side-effect control, and state/version checks.

**Question 7.** If E1 retries with timestamp `100` while E2 already won at timestamp `200`, will E1 roll the state backward?

**Answer:** For the same regular cell without other complex interactions, **no**: E2 has the higher timestamp. However, ensure timestamps accurately represent valid ordering; equal timestamps and tombstones follow distinct rules.

**Question 8.** Does `CL = ALL` prevent an old retry carrying a larger new timestamp from overwriting business state?

**Answer:** **No.** `ALL` enforces replica acknowledgments, not state-transition preconditions.

**Question 9.** An LWT `IF version = 1` times out. Can the client assume the condition did not apply and always resend immediately?

**Answer:** **No.** The outcome may be unknown; reconcile version/event ID first, then issue a bounded CAS retry if still needed.

**Question 10.** Why can executing `UPDATE state = 'PAID'` twice fail to be business-idempotent even with the same value?

**Answer:** The second attempt may carry a new write timestamp or reset TTL, altering LWW ordering or expiration deadlines; additionally, service side effects could run twice without deduplication.

---

**Key takeaway:** In Cassandra, **retries can change business outcomes** when an older event receives a **new mutation timestamp** or a value is rewritten with a **fresh relative TTL**. A timeout does not prove the prior write failed; the driver's idempotence flag does not replace business idempotency. Preserve **event IDs/versions**, distinguish same-execution retries from newly built mutations, store an **absolute `expires_at`** for deadline-sensitive data, and use **LWT/coordination** when state transitions must follow strict order. RF, CL, repair, and compaction handle data distribution and cleanup rather than validating business flow correctness.
