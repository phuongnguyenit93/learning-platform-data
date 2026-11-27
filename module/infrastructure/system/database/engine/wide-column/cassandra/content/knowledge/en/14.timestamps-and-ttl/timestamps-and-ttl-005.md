# Concurrent Writes to the Same Column and Timestamp-Based Resolution Rules

## 1. The Problem: Two Applications Updating the Same Cell Simultaneously

In **Apache Cassandra**, a **distributed wide-column** database management system, multiple clients can concurrently write to the same partition through different coordinators. Cassandra does not keep a single row on one machine: data is replicated across multiple **replicas** according to the replication factor. Due to network latency, retries, and differing processing orders, replicas may temporarily hold different versions of the same cell.

When choosing a single version to return and converging data, Cassandra defaults to the **last-write-wins (LWW)** mechanism based on the **mutation timestamp**. That means:

> For the same regular cell, **the version carrying the larger mutation timestamp wins**, regardless of which request reached the coordinator or replicas later in real time.

This is a data reconciliation rule, **not a cluster-wide write lock**, nor a guarantee that "whoever clicked Save last wins."

For example, an ordering system has two services:

- The payment service writes `payment_status = 'PAID'`.
- The order management service writes `payment_status = 'CANCELLED'` at nearly the same time.
- Both requests are accepted at different coordinators/replicas.

You cannot determine the final state solely from API call order or response arrival times. You must consider the **exact cell**, **write timestamps**, mutation kind (live value vs. deletion), and how Cassandra breaks ties when timestamps are equal.

## 2. What Does "Same Column" Mean in the Wide-Column Model?

A standard LWW conflict occurs at the **exact same data location**: the same keyspace, table, partition key, clustering key (if any), and the same cell/column. In Cassandra, columns with the same name belonging to two different rows are **not** the same cell.

Suppose the table is:

```sql
CREATE TABLE IF NOT EXISTS order_state_by_id (
    order_id uuid PRIMARY KEY,
    payment_status text,
    delivery_status text,
    updated_by text
);
```

| Mutation | Same cell as mutation A? | Why |
|---|---|---|
| A writes `payment_status` of order X | — | The cell under consideration |
| B writes `payment_status` of order X | **Yes** | Same primary key and column |
| C writes `delivery_status` of order X | **No** | Same row, different column |
| D writes `payment_status` of order Y | **No** | Different partition key |

Even when a single `UPDATE` statement sets `payment_status` and `updated_by` at the same time, each cell can be reconciled independently against other mutations. As a result, a single row can combine values from **multiple different writes**. Never assume columns updated in the same statement form an indivisible "row version."

For non-`frozen` collections, UDTs, row markers, and broader-scope deletes, Cassandra also has conflict rules at specific cell/data paths. The examples below focus on **regular scalar columns** to make the core principle clear.

## 3. How Does Cassandra Decide the Winning Record?

A **mutation timestamp** is a 64-bit integer measured in **microseconds (µs) since the Unix epoch**. This is metadata of a write, distinct from a CQL column of type `timestamp` used to store business time at millisecond resolution.

For two live versions of the **same cell**:

1. Compare mutation timestamps.
2. The version with the **larger** timestamp wins.
3. If timestamps are **equal**, Cassandra uses a deterministic tie-breaking rule at the internal data level. **Do not** infer that the version sent/received later wins.
4. When a **tombstone** (deletion marker) and a live value of the same cell have equal timestamps, **the tombstone takes precedence**. A larger tombstone shadows older values.

For **two live values** with equal timestamps, Cassandra has value-comparison rules at the data-representation level (for simple cells, the value with the greater byte order can win). That is conflict-resolution behavior, **not a business rule you should rely on**: byte order does not indicate which event occurred later; complex data structures and expiration metadata have their own handling details.

| Existing cell | New mutation | Basic outcome | Reason |
|---|---|---|---|
| `A @ 100` | `B @ 200` | `B` | `200 > 100` |
| `A @ 200` | `B @ 100` | `A` | New mutation has an older timestamp |
| `A @ 200` | `B @ 200` | Per internal tie-break rule | Not based on arrival time |
| `A @ 200` | Delete `@ 200` | Cell is deleted | Tombstone beats live value at equal timestamp |
| Tombstone `@ 300` | `C @ 250` | Remains deleted | Larger tombstone shadows older write |
| Tombstone `@ 300` | `C @ 350` | `C` is visible | Mutation is newer than tombstone |

```text
                Do both mutations target the same cell?
                       |
            +----------+-----------+
            |                      |
           No                     Yes
            |                      |
     No LWW conflict        Compare write timestamps
                                   |
                          +--------+--------+
                          |                 |
                      Different           Equal
                          |                 |
                 Larger timestamp wins   Tie-break:
                                      tombstone takes
                                      precedence over live
                                      value; live values use
                                      internal rule
```

### "Last" in LWW Does Not Mean the User's "Last"

Suppose client A issues a command at 10:00:00.000, client B issues a command at 10:00:00.010, but A's clock is two seconds ahead of B's. A can assign a larger timestamp, so **A wins despite sending first**. When multiple machines assign timestamps independently, LWW **does not automatically provide a real-time total order** across all requests.

## 4. CQL Hands-On: Writing the Same Cell with Different Timestamps

These examples use the `order_state_by_id` table in a selected **test keyspace**. Pick an unused UUID; timestamps are fixed for easy verification. Do not reuse a UUID from another run if tombstones or higher timestamps already exist on it.

### 4.1. Initial Write

```sql
INSERT INTO order_state_by_id (
    order_id, payment_status, delivery_status, updated_by
)
VALUES (
    55555555-1111-4111-8111-555555555555,
    'PENDING',
    'CREATED',
    'checkout'
)
USING TIMESTAMP 1800000000000000;

SELECT payment_status, writetime(payment_status),
       delivery_status, writetime(delivery_status),
       updated_by, writetime(updated_by)
FROM order_state_by_id
WHERE order_id = 55555555-1111-4111-8111-555555555555;
```

All three newly created cells carry mutation timestamp `1800000000000000`. `writetime()` returns the timestamp of the respective cell and **cannot** be used on primary keys or counters.

### 4.2. Simulating Two Competing Writes with Arrival Order Reversed from Timestamp Order

First write `'PAID'` with a larger timestamp:

```sql
UPDATE order_state_by_id
USING TIMESTAMP 1800000000002000
SET payment_status = 'PAID'
WHERE order_id = 55555555-1111-4111-8111-555555555555;
```

Then write `'CANCELLED'` with a **smaller** timestamp:

```sql
UPDATE order_state_by_id
USING TIMESTAMP 1800000000001000
SET payment_status = 'CANCELLED'
WHERE order_id = 55555555-1111-4111-8111-555555555555;

SELECT payment_status, writetime(payment_status)
FROM order_state_by_id
WHERE order_id = 55555555-1111-4111-8111-555555555555;
```

Expected result: `'PAID'` and `1800000000002000`. The second statement executed later yet did not change the winning version because `...1000 < ...2000`.

To demonstrate a winning write with a larger timestamp:

```sql
UPDATE order_state_by_id
USING TIMESTAMP 1800000000003000
SET payment_status = 'CANCELLED'
WHERE order_id = 55555555-1111-4111-8111-555555555555;

SELECT payment_status, writetime(payment_status),
       delivery_status, writetime(delivery_status)
FROM order_state_by_id
WHERE order_id = 55555555-1111-4111-8111-555555555555;
```

Now `payment_status` is `'CANCELLED'` with timestamp `...3000`. `delivery_status` remains `'CREATED'` with timestamp `...0000`. LWW does not make "the whole row win" just because one column changed.

> **Note:** Running two `UPDATE` statements sequentially here **simulates** two competing requests; they illustrate how arbitration works regardless of version arrival order. The Java section below uses two asynchronous requests to observe genuine concurrency.

## 5. When Two Mutations Have Equal Timestamps

Cassandra does not use "the request that arrived later" to break ties. Therefore, **never deliberately let two writers produce different values with the same timestamp** and expect Cassandra to guess business order.

### 5.1. Two Live Values with the Same Timestamp

Use a separate key:

```sql
INSERT INTO order_state_by_id (order_id, payment_status)
VALUES (55555555-2222-4222-8222-555555555555, 'PAID')
USING TIMESTAMP 1800000000004000;

UPDATE order_state_by_id
USING TIMESTAMP 1800000000004000
SET payment_status = 'CANCELLED'
WHERE order_id = 55555555-2222-4222-8222-555555555555;

SELECT payment_status, writetime(payment_status)
FROM order_state_by_id
WHERE order_id = 55555555-2222-4222-8222-555555555555;
```

`writetime(payment_status)` is still `1800000000004000`, yet **you must not assume `'CANCELLED'` wins because the UPDATE ran second**. Internal tie-breaking rules decide the result. Applications should avoid ties via timestamp policies and/or conditional update mechanisms.

### 5.2. Deletion at the Same Timestamp as a Live Value

Use a separate key to avoid interference from the previous test:

```sql
INSERT INTO order_state_by_id (order_id, payment_status, updated_by)
VALUES (
    55555555-3333-4333-8333-555555555555,
    'PAID',
    'payment-service'
)
USING TIMESTAMP 1800000000005000;

DELETE payment_status FROM order_state_by_id
USING TIMESTAMP 1800000000005000
WHERE order_id = 55555555-3333-4333-8333-555555555555;

SELECT payment_status, updated_by
FROM order_state_by_id
WHERE order_id = 55555555-3333-4333-8333-555555555555;
```

Result: `payment_status` is `null`, while `updated_by` still has `'payment-service'`. **A tombstone beats a live value at the same timestamp**. This also means rewriting a value at timestamp `...5000` is not enough to restore the cell; a valid mutation with a timestamp newer than the tombstone is required.

**Tombstones cannot be viewed directly via `writetime(payment_status)` after the cell has been deleted.** SSTable diagnostic tools, deletion command history, and write logs are more suitable sources when you need to identify a specific tombstone.

## 6. Two Concurrent Requests via Java Driver

In a Java application using **Apache/DataStax Cassandra Java Driver 4.x**, two threads, pods, or services can issue parallel writes to the same partition. The example below gives both requests predetermined timestamps so the LWW outcome **does not depend on completion order**.

Assume the table exists and each run uses a fresh `orderId`:

```java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class ConcurrentOrderUpdates {
    private final CqlSession session;
    private final PreparedStatement updateStatus;

    public ConcurrentOrderUpdates(CqlSession session) {
        this.session = session;
        this.updateStatus = session.prepare(
            "UPDATE order_state_by_id " +
            "SET payment_status = ? WHERE order_id = ?"
        );
    }

    public void writeTwoVersions(UUID orderId) {
        // Both requests write to the exact same cell.
        // Timestamps are in MICROSECONDS since the Unix epoch.
        BoundStatement paid = updateStatus
            .bind("PAID", orderId)
            .setQueryTimestamp(1800000000008000L);

        BoundStatement cancelled = updateStatus
            .bind("CANCELLED", orderId)
            .setQueryTimestamp(1800000000007000L);

        CompletableFuture<?> first = session.executeAsync(paid)
            .toCompletableFuture();
        CompletableFuture<?> second = session.executeAsync(cancelled)
            .toCompletableFuture();

        // Wait for both requests to return results or fail.
        CompletableFuture.allOf(first, second).join();
    }
}
```

When run against a nonexistent key, whether the `cancelled` request finishes before or after the `paid` request, once the data is reconciled **`'PAID'` wins** because timestamp `...8000 > ...7000`. For reads issued while both requests are in flight, consistency level and replica latency can affect the transient version observed; perform verification after both requests complete and at an appropriate consistency level.

**Java Driver note:** `setQueryTimestamp(long)` returns a new statement (Driver 4.x's immutable statement API); you must use the returned value as shown above. If a CQL statement includes `USING TIMESTAMP`, the CQL timestamp takes precedence over the statement-level query timestamp. Also distinguish epoch microseconds from `System.currentTimeMillis()`, which is epoch milliseconds.

## 7. Why Do Timestamps Across Writers Easily Invert Order?

Cassandra can receive mutation timestamps from:

- **CQL `USING TIMESTAMP`:** application specifies microseconds.
- **Statement timestamp in the driver:** e.g., `setQueryTimestamp(...)`.
- **Timestamp generator:** Java Driver has generators assigning client-side timestamps; some types maintain monotonicity within the generator's scope.
- **Coordinator:** the server assigns a timestamp if the request has no client-supplied timestamp.

Different sources can observe different clocks. A generator that is monotonically increasing **within one JVM** does not establish unified ordering across multiple services on separate hosts. A client clock running a few seconds fast can cause its writes to shadow mutations from other clients for several seconds afterward.

```text
  Real time                 10:00:00.000       10:00:00.050
                               |                    |
  Client A (2s fast)        ts 10:00:02.000        |
  Client B (on time)            |             ts 10:00:00.050
                               |                    |
  Send two UPDATEs             A                    B

  Timestamp comparison: A > B → A wins,
  even though B sent its request 50 ms after A.
```

Synchronize clocks on both Cassandra nodes **and** hosts running clients/drivers using a reliable time source (NTP, chrony, or equivalent), monitor clock skew, and standardize how timestamps are produced. A future timestamp can make a cell appear to "refuse new writes" until subsequent mutations surpass the winning value.

### Retries Can Also Flip Business Order

Suppose `E1: PENDING` is sent first but times out; `E2: PAID` is sent later and completes. If the retry of `E1` **receives a new timestamp** larger than `E2`, the state can roll back to `PENDING`. If business logic requires exact replay semantics, use event identifiers and an idempotency policy, and consider **keeping a stable timestamp for the same mutation** where appropriate. Keeping the timestamp stable does not by itself resolve two different mutations intentionally sharing a timestamp; source-level distinction/ordering rules are still needed.

## 8. Replication, Consistency Level, and Reconciliation

Suppose a keyspace has **RF = 3**. Two requests write the same cell at two coordinators:

```text
                        Client A
                    PAID @ ts = 200
                            |
                            v
                      Coordinator X
                       ↙       ↘
                  Replica 1   Replica 2

                        Client B
                 CANCELLED @ ts = 300
                            |
                            v
                      Coordinator Y
                       ↙       ↘
                  Replica 2   Replica 3

    Replicas may temporarily hold different versions.
    When versions are reconciled: ts = 300 wins.
```

The diagram only illustrates asynchronous distribution. In real deployments, Cassandra determines the replicas for a partition based on topology/replication strategy, and the coordinator coordinates according to the request's consistency level.

| Concept | Role in this scenario |
|---|---|
| **Replication factor** | Number of replicas storing the partition |
| **Write/read consistency level** | Condition on how many replicas must participate/acknowledge to satisfy the request, e.g., `ONE`, `QUORUM`, `ALL` |
| **Last-write-wins** | Rule choosing the winning cell when replicas hold conflicting versions |
| **Read reconciliation, repair** | Read-path and operational mechanisms enabling replicas to exchange, detect, and fix divergences |

With RF = 3, `QUORUM` typically requires responses from **2 replicas**. When read/write levels are configured appropriately, quorums overlap, increasing the likelihood of observing the latest version according to **timestamp order** under normal operating conditions. However:

- `QUORUM` **does not guarantee** that a command with a lower timestamp overwrites a version with a higher timestamp.
- `ALL` cannot fix clock skew or a wrong-unit `USING TIMESTAMP`.
- Reading at `ONE` during concurrent writes can observe transiently different states depending on which replica is queried.
- **Repair** converges replicas according to Cassandra's data rules; it does not know which state is business-correct if write timestamps were wrong.

Therefore, separate two questions: **"Did the request satisfy its consistency level?"** and **"Which mutation version wins inside the cell?"** Those two questions are answered by two different mechanisms.

## 9. TTL and Tombstones Under Concurrent Writes

TTL and deletes make arbitration more intricate than plain live writes:

- `USING TTL N` assigns a lifetime of **N seconds** to the written cells. Upon expiration, the data is treated as deleted.
- `DELETE` creates a **tombstone** to shadow older versions on other replicas.
- A tombstone with a larger timestamp (or equal to the timestamp of a live value in the same cell) takes precedence.
- A mutation with a timestamp larger than the tombstone can produce a visible live value again, if business logic permits.

Example of two writes with different TTLs:

```sql
-- Fresh UUID for the TTL example.
INSERT INTO order_state_by_id (order_id, payment_status)
VALUES (55555555-4444-4444-8444-555555555555, 'REVIEW')
USING TIMESTAMP 1800000000010000 AND TTL 3600;

UPDATE order_state_by_id
USING TIMESTAMP 1800000000011000 AND TTL 60
SET payment_status = 'TEMPORARY'
WHERE order_id = 55555555-4444-4444-8444-555555555555;

SELECT payment_status, writetime(payment_status), ttl(payment_status)
FROM order_state_by_id
WHERE order_id = 55555555-4444-4444-8444-555555555555;
```

Immediately after writing, `'TEMPORARY'` is the winning version and `ttl(payment_status)` is roughly 60 seconds. **Do not assume Cassandra will revert to `'REVIEW'` when `TEMPORARY` expires**; the older live version has been superseded by the newer version/expired tombstone. TTL is not a "stack of values" that automatically rolls back to a prior version.

For tables with heavy deletes/TTLs, **compaction**, tombstone retention time, and **repair** are operational concerns. If tombstones are purged unsafely while a replica still retains old data, there is a risk of **zombie data**. Design repair schedules and tombstone policies suited to your environment; never arbitrarily lower `gc_grace_seconds` to dodge conflict issues.

## 10. Not Every Operation Behaves Like a Simple LWW Write

### 10.1. Counters

`counter` columns have a specialized increment/decrement mechanism and do not follow scalar overwriting via `USING TIMESTAMP`. Do not use regular LWW examples to deduce the outcome of concurrent counter updates; you must also account for retries and duplicate increments.

### 10.2. Collections and Broad-Scope Mutations

Non-`frozen` collections can contain multiple independently updated cells/elements; deleting an entire collection behaves differently from updating an element. Deleting an entire row/partition creates a broader-scope tombstone than deleting a single column. Check the exact conflict scope rather than assuming every case is two scalar values in a single cell.

### 10.3. Batches

`BEGIN BATCH ... APPLY BATCH` has Cassandra batch semantics, yet **does not create a "later-arriving wins" order for competing writes to the same cell**. Regardless of the completion order of two batches, version reconciliation is still governed by mutation timestamps. Multi-partition batches also have cost and atomicity characteristics unlike relational transactions and should not replace locking/business coordination.

### 10.4. Lightweight Transactions (LWT)

When you need to check a condition before writing, Cassandra supports **LWT** with `IF` via Paxos. Example:

```sql
-- Set initial state on a separate key for the LWT example.
INSERT INTO order_state_by_id (order_id, payment_status)
VALUES (55555555-5555-4555-8555-555555555555, 'PENDING')
IF NOT EXISTS;

-- Apply only if the current status is PENDING.
UPDATE order_state_by_id
SET payment_status = 'PAID'
WHERE order_id = 55555555-5555-4555-8555-555555555555
IF payment_status = 'PENDING';
```

CQL returns an `[applied]` result column so the client knows whether the update took effect. LWT provides **compare-and-set** within supported scopes, at the cost of extra round trips/overhead. Do not arbitrarily combine `USING TIMESTAMP` with **conditional updates**; Cassandra does not allow user-specified timestamps on LWTs the way regular writes do.

LWT solves a different requirement from LWW: **change only if the current state satisfies a condition**. When multiple services write to the same critical state, design the state transitions and how callers react when `[applied] = false`.

## 11. Designing to Avoid Concurrent Write Conflicts on the Same Cell

In Cassandra data modeling, **query-driven** table design ties directly into write-contention handling. Options include:

| Business requirement | Usually appropriate design | Trade-off |
|---|---|---|
| Accepting "higher-timestamp version wins" | Regular writes with timestamp generator and clock sync | Simple, but requires understanding LWW ordering |
| Each entity has a **single writer** owning state | Route writes by owner/partition or ordered queue | Requires owner assignment and recovery mechanism |
| State transitions must satisfy preconditions | LWT `IF ...`, checked version, handle failed conditions | Higher coordination overhead |
| Must retain every competing event | **Append-only** history table, each event as its own row | Requires query/process to derive current state |
| Must be idempotent on retries | Event IDs, deduplication, and event-stable timestamps when appropriate | Must manage event identity and ordering policy |

Example of state-change history by order and `event_time`:

```sql
CREATE TABLE IF NOT EXISTS payment_events_by_order (
    order_id uuid,
    event_id timeuuid,
    status text,
    source_service text,
    PRIMARY KEY ((order_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);

SELECT event_id, status, source_service
FROM payment_events_by_order
WHERE order_id = 55555555-1111-4111-8111-555555555555
LIMIT 20;
```

Each event gets its own row, reducing direct contention on a single `payment_status` cell. However, **`timeuuid` is also typically clock-based**: whenever business logic demands strict total order across multiple writers, you need a **sequence/version issued by a trusted coordinator** or a dedicated ordering workflow. A history table alone does not solve all clock-skew or event-ordering issues.

To query the newest events, the **clustering key** establishes key-based read order. Cassandra does not permit `ORDER BY writetime(payment_status)` as an arbitrary sort on cell metadata.

## 12. Diagnosing When Two Calls "Succeeded" Yet One Update Was Lost

Identify the **specific cell** and gather evidence before changing consistency levels or editing data:

| Step | What to check | Purpose |
|---|---|---|
| 1 | Keyspace, table, partition key, clustering key, written column | Did both requests truly target the same cell? |
| 2 | `SELECT value, writetime(value) ...` | Which value is winning and what timestamp does it carry? |
| 3 | `USING TIMESTAMP`, `setQueryTimestamp()`, timestamp generator | Where was the timestamp assigned and is the unit µs? |
| 4 | Clock skew across JVMs, client hosts, coordinators | Is a machine assigning future timestamps? |
| 5 | Retry IDs, event IDs, business sequence | Did a retry with a new timestamp let an older event win? |
| 6 | `DELETE`/TTL/tombstones, compaction | Is a record shadowed by a larger tombstone? |
| 7 | RF, read/write CL, replica health, repair | Are replicas temporarily out of sync or conflicting? |
| 8 | LWT and `[applied]` results (if used) | Was an operation rejected because the condition was unmet? |

The following query helps inspect live cells:

```sql
SELECT payment_status, writetime(payment_status),
       delivery_status, writetime(delivery_status)
FROM order_state_by_id
WHERE order_id = 55555555-1111-4111-8111-555555555555;
```

`writetime()` does not display the full history of losing mutations or deleted tombstones. During production investigations, combine application logs, trace/request metadata, and appropriate Cassandra administrative tools. Log `eventId`, `partitionKey`, `mutationTimestampMicros`, `timestampSource`, and request outcome, while avoiding logging unnecessary sensitive values.

### Easy-to-Miss Mistakes

- **Unit mix-up:** `System.currentTimeMillis()` is **milliseconds**, whereas `USING TIMESTAMP` and `setQueryTimestamp()` take **microseconds**.
- **Duplicate timestamps:** two clients read the same timestamp or source resolution is coarser than 1 microsecond; ties do not follow send order.
- **Future timestamps:** a machine with a fast clock can block valid writes in the near future.
- **Wrong observation scope:** seeing one column updated does not prove other columns in the row came from the same version.
- **Consistency misconception:** raising to `QUORUM`/`ALL` does not fix a bad timestamp; read/write CL and reconciliation address replica scope, not business ordering.

## 13. Scenario-Based Self-Check

**Question 1.** Two clients write `payment_status` on an order: A writes `PAID@500`, B writes `CANCELLED@700`. B reaches the coordinator before A. Which value wins after reconciliation?

**Answer:** `CANCELLED`, because `700 > 500`. Coordinator arrival order is not the criterion.

**Question 2.** Two different write commands both have timestamp `900`. Can you guarantee the command sent later wins?

**Answer:** No. Cassandra uses deterministic data-level tie-breaking, not send order; equal-timestamp conflicts must be avoided.

**Question 3.** A cell is live at timestamp `1000`, and a client deletes the cell with tombstone timestamp `1000`. After reconciliation, is the cell still visible?

**Answer:** No. A tombstone at the same timestamp takes precedence over the corresponding live value.

**Question 4.** Two services concurrently update `payment_status` and `delivery_status` of the same order. Must one of the two writes be discarded?

**Answer:** No. They are two separate cells and can coexist with different write timestamps.

**Question 5.** Both reads and writes use `QUORUM`, so is the user who clicks "Save" last guaranteed to win?

**Answer:** No. Quorum governs replica participation and read/write consistency; LWW is still based on mutation timestamps.

**Question 6.** Can retrying a `PENDING` event after `PAID` was already written roll the status back to `PENDING`?

**Answer:** Yes, if the `PENDING` retry receives a larger timestamp. Idempotency and a business ordering policy are required.

**Question 7.** Which tool should be used when transitioning `PENDING → PAID` must occur only if the status is still `PENDING`?

**Answer:** Consider LWT `UPDATE ... IF payment_status = 'PENDING'`, check `[applied]`, and handle contention; do not use unconditional LWW writes as a substitute for compare-and-set.

---

**Key takeaway:** For concurrent writes to the **same cell**, Cassandra chooses by **mutation timestamp**: larger wins; on ties there is an **internal tie-breaking rule** where **a tombstone beats the corresponding live value**. This rule is independent of request arrival order and does not automatically guarantee business order. To avoid lost updates, control timestamps/clock skew/retries, design tables around queries, and use conditional mechanisms like **LWT** when compare-and-set is required.
