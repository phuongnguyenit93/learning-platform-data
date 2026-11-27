# Batch statements and logged batches in Apache Cassandra

## 1. Problem: if one message must write multiple rows, should you use BATCH?

Suppose a Spring Integration flow receives an `OrderPaid` event from JMS. After verifying the signature, transforming JSON, and validating fields, the application needs to persist the order's history in Apache Cassandra. Each `OrderPaid` may produce two or three mutations: appending an event, updating related info, and recording processing status.

Developers familiar with relational databases often propose:

~~~sql
BEGIN BATCH
    INSERT INTO ...;
    UPDATE ...;
APPLY BATCH;
~~~

However, **a Cassandra `BATCH` is not equivalent to an SQL transaction**, nor is it a **default speedup mechanism** for thousands of independent writes. In particular, a **multi-partition logged batch** provides an *eventual atomicity* completion/recovery mechanism across mutations, without the isolation, rollback, or consistent snapshot reads of an RDBMS ACID transaction.

Distinguish five concepts up front:

1. **CQL `BATCH`:** a single request containing multiple `INSERT`, `UPDATE`, and/or `DELETE` statements.
2. **LOGGED batch:** uses the Cassandra batchlog when protecting execution of multiple mutations across coordinator failures, especially across multiple partitions.
3. **UNLOGGED batch:** omits the batchlog; a failing multi-partition batch can be partially applied.
4. **COUNTER batch:** a specialized batch for updating counter columns, lacking the idempotency of regular writes.
5. **Client-side batching:** buffering, chunking, or throttling **independent requests** before sending; does not necessarily use CQL `BEGIN BATCH`.

In the **SPRING_INTEGRATION_ADAPTERS** module, inbound/outbound adapters, gateways, pollers, and `MessageChannel` connect files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while managing message contracts, errors, and connection lifecycles. **Batch statements and logged batches**, part of the **Adapter Cassandra** chapter, helps you choose the right bulk-write approach when message flows pass through the Cassandra outbound adapter/gateway.

### Learning objectives

After this lesson, you will be able to:

- Read and write `BEGIN BATCH`, `BEGIN UNLOGGED BATCH`, and `BEGIN COUNTER BATCH`.
- Distinguish **single-partition isolation**, **logged multi-partition eventual completion**, and transaction-semantics limits.
- Explain Cassandra's **batchlog**, coordinator, replicas, timeouts, and transient partial visibility.
- Build a `BatchStatement` with Java Driver 4.x using `SimpleStatement`, `PreparedStatement`/`BoundStatement`, and `DefaultBatchType`.
- Create batches with Spring Data `ReactiveCassandraOperations.batchOps(...)` and handle `Mono<WriteResult>`.
- Use Spring Integration `CassandraMessageHandler` with `List<entity>`, `ingestQuery` taking `List<List<?>>`, or `statementFunction`.
- Bound batches by **partition key**, payload bytes, mutation count, deadlines, and retry budgets.
- Design idempotency, recovery, acknowledgments, and failover tests suited to JMS/Kafka.

## 2. Separating three scopes: request, partition, and business

~~~mermaid
flowchart LR
    A["JMS / HTTP / Kafka event"] --> B["Transformer + Validator"]
    B --> C["Spring Message<List<OrderEvent>>"]
    C --> D["Cassandra outbound handler"]
    D --> E["ReactiveCassandraOperations / CqlSession"]
    E --> F["Cassandra coordinator"]
    F --> P1[("Partition order-101")]
    F --> P2[("Partition order-102")]
    F --> P3[("Partition order-103")]
~~~

| Boundary | What does it mean? | What it does not guarantee by itself |
|---|---|---|
| **A Spring Message** | Payload + headers sent over a `MessageChannel` | Does not equal a CQL `BATCH` or a Cassandra transaction |
| **A CQL `BATCH`** | Bundles multiple mutations into one request | Does not isolate reads across all partitions |
| **A Cassandra partition** | Group of rows identified by partition key; stored on one replica set | Not equivalent to a Kafka topic partition |
| **A business event** | Business identifier, e.g. `eventId` | Not automatically deduplicated across retries |
| **A source acknowledgment** | JMS commit/ack or Kafka offset commit | Not atomic with Cassandra batch completion |

Even when a Spring Message carries `List<OrderEvent>`, how Spring Integration/Spring Data processes that list determines whether it becomes a batch operation or multiple calls; **never guess from the Java collection type without checking the API and version**.

### 2.1. What confirmation levels exist in a successful flow?

~~~mermaid
sequenceDiagram
    participant Src as JMS broker
    participant SI as Spring Integration
    participant DB as Cassandra coordinator
    participant Rep as Cassandra replicas
    Src->>SI: Message<events>
    SI->>DB: CQL BATCH / batchOps
    DB->>Rep: Replicate mutations
    Rep-->>DB: ACK per consistency level
    DB-->>SI: Response / timeout
    SI-->>Src: Commit or rollback per policy
    Note over Src,Rep: Cassandra batch and broker commit share no ACID transaction
~~~

When Cassandra reports success, that reflects consistency/acknowledgment for the Cassandra operation; if the **JMS commit subsequently fails**, the message can still be redelivered. Conversely, an async handler can let the JMS callback finish **before the Cassandra operation completes**.

## 3. CQL BATCH: syntax and core rules

Cassandra CQL lets you group mutation statements using:

~~~sql
BEGIN BATCH
    INSERT INTO ...;
    UPDATE ...;
    DELETE ...;
APPLY BATCH;
~~~

`BEGIN BATCH` with no keyword after `BEGIN` is **LOGGED** by default. In standard CQL syntax, **do not write `BEGIN LOGGED BATCH`**; write:

~~~sql
BEGIN BATCH
    INSERT INTO ...;
    UPDATE ...;
APPLY BATCH;
~~~

The other two types:

~~~sql
BEGIN UNLOGGED BATCH
    INSERT INTO ...;
    UPDATE ...;
APPLY BATCH;
~~~

~~~sql
BEGIN COUNTER BATCH
    UPDATE some_counter_table SET quantity = quantity + 1 WHERE key = 'a';
    UPDATE some_counter_table SET quantity = quantity + 2 WHERE key = 'b';
APPLY BATCH;
~~~

**Notes:**

- `BATCH` normally holds only `INSERT`, `UPDATE`, and `DELETE` mutations; never put `SELECT` or DDL like `CREATE TABLE` inside.
- Never nest another `BEGIN BATCH` inside an existing batch.
- Counter mutations require a `COUNTER` batch and cannot be mixed with regular mutations.
- When using `IF` conditions (LWT), stricter same-partition/statement rules apply; do not treat it as an arbitrary multi-partition transactional batch.
- Within a batch, mutations targeting the **same partition** can execute with partition-level isolation. Across **multiple partitions**, concurrent reads may observe partial progress.

### 3.1. A table used across the examples

On a **test** cluster with keyspace `shop_integration`, create:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_events (
    order_id text,
    event_id text,
    occurred_at timestamp,
    event_type text,
    payload_json text,
    PRIMARY KEY ((order_id), event_id)
);
~~~

In this table, `order_id` is the **partition key** and `event_id` is the **clustering column**. Two events sharing `order_id='ORD-101'` belong to the same Cassandra partition. Events for `ORD-101` and `ORD-102` belong to **two different partitions**.

In production examples, a single order might generate too many events; evaluate bucketing/time-windows and design around query patterns. Do not treat the lab schema as universal advice for all workloads.

### 3.2. Single-partition BATCH

~~~sql
BEGIN BATCH
    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-101', 'OrderCreated', '{"step":1}');

    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-102', 'OrderPaid', '{"step":2}');
APPLY BATCH;
~~~

Both rows share **partition key `ORD-101`**. Cassandra can optimize a single-partition LOGGED batch to skip the batchlog. Keep it **small, single-partition, and driven by a domain requirement**; do not batch thousands of events solely to reduce Java method calls.

### 3.3. Multi-partition BATCH

~~~sql
BEGIN BATCH
    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-103', 'OrderPaid', '{"source":"jms"}');

    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-102', 'evt-201', 'OrderCreated', '{"source":"http"}');
APPLY BATCH;
~~~

These two mutations span **two partitions**. With a LOGGED batch, Cassandra uses the **batchlog** to drive all mutations to completion via recovery if the coordinator fails. **There is no guarantee** that a client reading `ORD-101` and then `ORD-102` mid-execution sees both changes simultaneously.

### 3.4. Statement order in a batch is not side-effect order

Within a batch, Cassandra can assign the **same write timestamp** to mutations lacking explicit per-statement timestamps. When the same column/primary key is written multiple times with identical timestamps, conflict resolution can yield a result different from textual CQL order.

~~~sql
-- DO NOT rely on these two statements to represent a state sequence.
BEGIN BATCH
    UPDATE shop_integration.order_events
    SET event_type = 'PAID'
    WHERE order_id = 'ORD-101' AND event_id = 'evt-101';

    UPDATE shop_integration.order_events
    SET event_type = 'CANCELLED'
    WHERE order_id = 'ORD-101' AND event_id = 'evt-101';
APPLY BATCH;
~~~

If business logic requires `OrderPaid(v2)` before `OrderCancelled(v3)`, use an **aggregate version**, an append-only event log with distinct keys, and/or conditional mutations; **never assume the later statement in a batch always wins**.

## 4. What does a LOGGED batch actually guarantee?

In standard CQL, **LOGGED BATCH** means Cassandra uses the batchlog so mutations in the batch are **driven to completion through recovery** under supported conditions. With **multiple partitions**, updates may **become visible at different times**.

| Property | Single partition | Multi-partition |
|---|---|---|
| `BATCH` contains multiple mutations | Yes | Yes |
| Isolated visibility within that partition | Yes, within Cassandra semantics | **Not** guaranteed across partitions |
| `LOGGED` batch uses batchlog | Can be optimized to skip batchlog | Normally uses batchlog |
| When coordinator dies after batchlog | Cassandra has replay/completion | Cassandra has replay/completion |
| Reading all rows sees one instant snapshot | Only within partition/query/CL scope | **No** |
| Rollback to old state like SQL transaction | **Not** SQL rollback semantics | **Not** |
| Atomic JMS/Kafka ack with the batch | **No** | **No** |

### 4.1. Eventual atomicity vs SQL ACID

Cassandra documentation describes logged batches as ensuring mutations are either applied or replayed via the batchlog **under valid execution conditions**. That does not mean:

- All partitions transition state at one observable instant.
- Other applications cannot observe intermediate state.
- Multi-table/multi-partition transaction isolation exists as in PostgreSQL.
- On caller timeout, zero mutations occurred and it is safe to mint new event IDs.
- Replica-persisted changes automatically roll back if the upstream JMS message rolls back.

Thus, if your logic reads two Cassandra partitions expecting "if A exists then B must already be visible immediately", **a logged batch does not create an instant cross-partition read invariant**.

### 4.2. Checking mid-batch execution

~~~mermaid
sequenceDiagram
    participant App as Writer
    participant Coord as Coordinator
    participant R1 as Partition A replicas
    participant R2 as Partition B replicas
    participant Reader as Concurrent reader

    App->>Coord: BEGIN LOGGED BATCH (A, B)
    Coord->>Coord: Write batchlog (multi-partition)
    Coord->>R1: Mutation A
    R1-->>Coord: ACK A
    Reader->>R1: Read A
    R1-->>Reader: A already changed
    Reader->>R2: Read B
    R2-->>Reader: B not changed yet
    Coord->>R2: Mutation B / retry if needed
    R2-->>Coord: ACK B
    Coord-->>App: Completion per consistency level
~~~

A reader can see `A=new` while `B=old`. That is why a logged batch **is not a cross-partition snapshot transaction**; even though batchlog replay later brings everything to completion, an intermediate window existed.

## 5. Batchlog: how does Cassandra protect multi-partition batches?

The batchlog is an **internal Cassandra mechanism**, not a Kafka topic, JMS queue, Spring `errorChannel`, or application outbox table. A multi-partition logged-batch coordinator writes batch details to the batchlog infrastructure before dispatching mutations to replicas. If the coordinator drops or crashes after the batchlog is durably recorded, Cassandra can replay missing mutations.

~~~mermaid
flowchart TD
    A["Client: logged BATCH A + B"] --> C["Cassandra coordinator"]
    C --> L["Write batchlog to batchlog endpoints per cluster mechanism"]
    L --> D["Send mutation A and mutation B"]
    D --> RA["Replica set partition A"]
    D --> RB["Replica set partition B"]
    RA -. "ACK / write received" .-> X["Completion criteria met"]
    RB -. "ACK / write received" .-> X
    X --> R["Delete/complete batchlog when criteria met"]
    R --> Y["Client response if request is still waiting"]
    L -. "Coordinator fails" .-> RE["Batchlog replay"]
    RE --> RA
    RE --> RB
~~~

### 5.1. Four phases to distinguish

1. **Intake:** The coordinator receives the batch and identifies mutations and partition keys.
2. **Protection:** For a logged batch requiring a batchlog, the coordinator persists serialized mutation descriptors to batchlog endpoints before proceeding.
3. **Execution:** The coordinator dispatches mutations to replica sets; partition A may apply before partition B.
4. **Completion/recovery:** Once durability/application conditions are met, the batchlog entry is removed, or replayed if incomplete work is detected.

Exact mechanics vary across Cassandra versions, replication strategies, hinting, and failure handling. **Never infer** from a `WriteTimeoutException` that the batchlog was definitely persisted; failures can strike at different stages. Design retries and reconciliation for uncertain states.

### 5.2. Why is the batchlog not a message queue?

- It exists to **finish in-flight batch mutations**, not to retain business events long-term.
- There is no application consumer API to poll the batchlog like a JMS destination.
- It does not replace source events, DLQs, outboxes, or inboxes.
- It does not manage Kafka offset checkpoints or JMS commits.
- It does not preserve a complete business audit history.
- It has resource limits, I/O overhead, and recovery lag.

If the business requires durable long-term ingestion, **upstream brokers and application replay mechanisms** remain essential.

### 5.3. Points where the outcome is uncertain

| Failure point | Possible Cassandra state | What caller should do |
|---|---|---|
| Request never reached coordinator | Probably no mutations applied | Idempotent retry if conditions permit |
| During batchlog write | Unknown which/how many mutations applied | Never assume rollback; use read-back/retention policies |
| After batchlog, before all mutations sent | Batchlog may still replay | Wait for convergence and reconcile; keep same business IDs |
| One partition ACKed, another lagged | Partial visibility possible | Avoid cross-partition instant read invariants |
| Client times out after batch applied | Batch may have completed | Never mint new event IDs; avoid duplicate side effects |
| Source broker commit fails after DB write | Event may be redelivered | Idempotent write; separate duplicates from conflicts |

## 6. Single-partition BATCH: where Cassandra has a clear advantage

With two mutations sharing partition key `ORD-101` in the **same table/partition**, Cassandra provides partition-scoped isolation for the batch. A single-partition logged batch can be **internally optimized into an unlogged batch**, avoiding expensive cross-partition batchlog writes.

### 6.1. Example adding two events for one order

~~~sql
BEGIN BATCH
    INSERT INTO shop_integration.order_events
        (order_id, event_id, occurred_at, event_type, payload_json)
    VALUES (
        'ORD-101', 'evt-104',
        '2026-11-23T08:00:00Z', 'OrderValidated', '{"state":"VALID"}'
    );

    INSERT INTO shop_integration.order_events
        (order_id, event_id, occurred_at, event_type, payload_json)
    VALUES (
        'ORD-101', 'evt-105',
        '2026-11-23T08:01:00Z', 'OrderPaid', '{"state":"PAID"}'
    );
APPLY BATCH;
~~~

**Why this works well:** both events live in the same Cassandra partition; the batch is small and serves one business aggregate. Still, **never treat a batch as a sequential queue**: if downstream updates current order state by version, enforce state-machine/version guards.

### 6.2. Benefits and limits of single-partition batches

| Aspect | Benefit | Limitation |
|---|---|---|
| Single client request | Cuts round trips for a few related mutations | Not always faster than multiple concurrent writes |
| In-partition isolation | Concurrent reads do not see interleaved row states within that partition per Cassandra semantics | Does not extend to cross-partition isolation |
| Lower batchlog overhead | Can optimize away the batchlog | Still executes/writes multiple mutations |
| Shared aggregate/order | Easy to align batches with domain units | Oversized/hot partitions remain problematic |
| Batch retry | Fixed keys make replay clean | Does not deduplicate newly minted event IDs or payload conflicts |

**Never use `BATCH` to dump millions of items for one order at once.** Size batches around partition limits and workloads, or revise the data model.

## 7. UNLOGGED BATCH: when to use it and why it is often misused

`BEGIN UNLOGGED BATCH` skips the batchlog. With **multiple partitions**, if the coordinator crashes midway, some partitions may apply while others never receive updates; Cassandra **does not use a batchlog to drive completion**.

~~~sql
BEGIN UNLOGGED BATCH
    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-u01', 'PaymentRequested', '{}');

    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-102', 'evt-u02', 'PaymentRequested', '{}');
APPLY BATCH;
~~~

**This is a technical example to illustrate semantics, not a production recommendation.** Two distinct partitions expose unlogged batches to partial application, with no cross-partition isolation or completion guarantee.

### 7.1. The usual right choice

**Single-partition `BATCH`** is the natural case for unlogged/optimized batching. For independent writes across many partitions when throughput is the goal, prefer **bounded concurrent asynchronous individual writes** instead of stuffing everything into an unlogged batch.

### 7.2. Never use UNLOGGED just to "optimize away" the batchlog

Skipping batchlog overhead does not make multi-partition mutations cheap. The coordinator still parses and routes the entire batch, creating a **hot coordinator**, network/heap pressure, and uneven load across the cluster.

| Workload | Option to consider |
|---|---|
| Two related mutations in one partition | Small single-partition batch |
| Three mutations across partitions needing eventual completion together | Small `LOGGED` batch, accepting partial visibility |
| 10,000 independent events across partitions | Bounded concurrent async writes, chunked in the app |
| Large data migration | Partition/range-aware backfill with throttling and retries |
| Continuous time series | Partition keys/bucketing, bounded parallelism; never batch a full day |

### 7.3. Never treat a batch as a JOIN or interactive transaction

`BATCH` executes mutations only. It cannot run `SELECT` inside the batch body to compute values and conditionally update. For conditional writes, use Cassandra LWT within its supported scope; for complex invariants spanning partitions/tables, design dedicated protocols/reconciliation or pick a transactional store suited to that need.

## 8. COUNTER BATCH: a different world for idempotency

Cassandra supports **counter columns** for incrementing or decrementing cumulative totals:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_event_counters (
    order_id text PRIMARY KEY,
    total_events counter
);
~~~

Counter batch example:

~~~sql
BEGIN COUNTER BATCH
    UPDATE shop_integration.order_event_counters
    SET total_events = total_events + 1
    WHERE order_id = 'ORD-101';

    UPDATE shop_integration.order_event_counters
    SET total_events = total_events + 2
    WHERE order_id = 'ORD-102';
APPLY BATCH;
~~~

### 8.1. Counter updates are not idempotent

Suppose a consumer executes `+1`, the coordinator applies it, and the response is lost. The consumer retries `+1`: the counter **can increment a second time**. Driver retries and speculative execution must never be enabled blindly on counters.

**Never** call `setIdempotent(true)` on a counter batch just to get automatic driver retries. Never mix counter mutations with regular `INSERT`/`UPDATE` statements in the same batch.

### 8.2. When the business needs exact reproducible totals

When exact processed-event counts are required, a more resilient design is:

1. Persist each event with a **stable ID** in an event-log table.
2. Compute projections/counts via a consumer with deduplication/checkpointing.
3. Retain the ability to recompute aggregates from the event log if projections drift.

Cassandra counters suit workloads that accept counter semantics, yet they are **not automatic exactly-once counters** alongside JMS/Kafka redeliveries.

## 9. Bounding batch size and performance: do not tune by row count alone

A common question is: "How many rows should go in each batch?" There is no universal number across schemas, payload sizes, key distributions, or clusters. Cassandra cares about **serialized size, partition count, node health, latency, and mutation type**, not merely Java list length.

### 9.1. Two safety thresholds in cassandra.yaml

In many Cassandra 4.x/5.x versions, default warn/fail settings for **multi-partition batches** look like:

| Property | Reference default value | Meaning |
|---|---|---|
| `batch_size_warn_threshold_in_kb` (Cassandra 4.x) or `batch_size_warn_threshold` (newer config) | ~**5 KiB** | Warns on large multi-partition batches |
| `batch_size_fail_threshold_in_kb` or `batch_size_fail_threshold` | ~**50 KiB** | Rejects oversized batches exceeding threshold |
| `unlogged_batch_across_partitions_warn_threshold` | ~**10 partitions** | Warns on `UNLOGGED` batches spanning too many partitions |

These values are **reference defaults that vary by Cassandra version and configuration**; check your actual `cassandra.yaml`. Never crank thresholds from 50 KiB up to megabytes just to silence warnings: oversized batches strain coordinator memory/CPU and destabilize nodes.

### 9.2. Row count hides serialized byte size

Suppose each event's JSON is ~2 KiB:

~~~text
10 events × 2 KiB  ≈ 20 KiB payload (before overhead).
30 events × 2 KiB  ≈ 60 KiB payload (before overhead).

For a multi-partition batch, 30 rows can already exceed
the reference default failure threshold of ~50 KiB.
~~~

Conversely, 100 tiny rows within **one partition** behave very differently from 100 rows across 100 partitions. **Never** hardcode `MAX_BATCH_ROWS=500` across all workloads without measuring byte sizes and distinct partition-key counts.

### 9.3. Why are multi-partition logged batches expensive?

~~~mermaid
flowchart TD
    A["Client sends 1 multi-partition LOGGED BATCH"] --> B["Coordinator manages all mutations"]
    B --> L["Batchlog I/O"]
    B --> S["Serialize / route each mutation"]
    S --> P1["Partition set A / replicas"]
    S --> P2["Partition set B / replicas"]
    S --> P3["Partition set C / replicas"]
    L --> M["Cleanup / replay bookkeeping"]
    P1 --> C["Response aggregation"]
    P2 --> C
    P3 --> C
~~~

Packing a thousand independent writes into one batch does **not** let Cassandra distribute coordinator work across partitions the way independent token-aware requests with a concurrency cap do. Instead, it **concentrates the bottleneck** onto the single coordinator receiving the batch.

### 9.4. Client-side micro-batching vs CQL batches

A producer may collect 100 messages and group them into 10 chunks of 10 events:

~~~text
Inbound Kafka/JMS messages
  -> buffer/chunk 10 events in application
  -> group by Cassandra partition key
  -> each group chooses:
       (a) small single-partition BATCH, or
       (b) bounded asynchronous individual writes
  -> track per-event completion
~~~

**Buffering/chunking in the application does not require sending `BEGIN BATCH`.** That is a scheduling/backpressure choice. In Spring Integration, `Aggregator`/`ReleaseStrategy` can group messages by size/time window, while requiring careful attention to the **message group store** and durability before acknowledgment.

### 9.5. When to prefer individual requests?

If 1,000 events hit **1,000 distinct Cassandra partition keys**, issuing individual `CqlSession.executeAsync` or reactive operations with a concurrency cap leverages token-aware routing and spreads load. Building giant `LOGGED` batches merely to reduce `send()` calls adds batchlog and hot-coordinator overhead.

When **two to five mutations** touch related tables/partitions and **genuinely require batchlog-driven completion**, a small `LOGGED` batch fits well. Still, if **instant cross-partition consistent reads** are required, a logged batch will not provide them; revisit your data model or invariants.

## 10. Java Driver 4.x: BatchStatement and DefaultBatchType

Driver 4.x provides:

~~~java
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
~~~

| Java Driver type | Role |
|---|---|
| `BatchStatement` | Wraps one or more `BatchableStatement<?>` instances |
| `DefaultBatchType.LOGGED` | Uses `LOGGED` semantics |
| `DefaultBatchType.UNLOGGED` | Skips batchlog |
| `DefaultBatchType.COUNTER` | Batches counter mutations |
| `SimpleStatement` | CQL + positional values or statement options |
| `PreparedStatement` | Prepared CQL without single-execution values yet |
| `BoundStatement` | Prepared CQL + bound values, batchable |

### 10.1. Building a LOGGED batch with two bound statements

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class OrderEventBatchDao {

    private final CqlSession session;
    private final PreparedStatement insertEvent;

    public OrderEventBatchDao(CqlSession session) {
        this.session = session;
        this.insertEvent = session.prepare(
                "INSERT INTO shop_integration.order_events "
                + "(order_id, event_id, event_type, payload_json) "
                + "VALUES (?, ?, ?, ?)");
    }

    public void writeTwoEventsSameOrder(
            String orderId, String eventId1, String eventId2) {

        BoundStatement first = insertEvent.bind(
                orderId, eventId1, "OrderCreated", "json-1");
        BoundStatement second = insertEvent.bind(
                orderId, eventId2, "OrderPaid", "json-2");

        BatchStatement batch = BatchStatement
                .builder(DefaultBatchType.LOGGED)
                .addStatement(first)
                .addStatement(second)
                .build();

        session.execute(batch);
    }
}
~~~

This example writes **two rows in the same Cassandra partition** (identical `orderId`). The driver builds a `LOGGED` batch, and Cassandra can optimize a single-partition batch without writing to the batchlog. `CqlSession`/`PreparedStatement` are reused; never open a new session per incoming message.

### 10.2. Mixing SimpleStatement and BoundStatement

~~~java
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement first = SimpleStatement.newInstance(
        "INSERT INTO shop_integration.order_events "
        + "(order_id, event_id, event_type, payload_json) "
        + "VALUES (?, ?, ?, ?)",
        "ORD-101", "evt-106", "OrderPacked", "json-3");

BatchStatement batch = BatchStatement.newInstance(
        DefaultBatchType.LOGGED,
        first,
        insertEvent.bind(
                "ORD-101", "evt-107", "OrderShipped", "json-4"));

session.execute(batch);
~~~

This is a fragment inside a DAO with `insertEvent` and `session`. `SimpleStatement.newInstance(query, values...)` uses **positional values**; Java Driver 4.x **does not support `SimpleStatement` instances with named parameters inside `BatchStatement`** per Driver 4.19 docs. When named binding is needed in a batch, **prepare the query and bind a `BoundStatement`**.

### 10.3. Immutable BatchStatement and builder

After creation:

~~~java
// WRONG: setter result ignored; original batch unchanged.
batch.setExecutionProfileName("bulk-write");

// RIGHT: reassign the result to use the batch with the new profile.
batch = batch.setExecutionProfileName("bulk-write");
~~~

Driver 4.x's built-in `BatchStatement` is **immutable**. `setConsistencyLevel`, `setTimeout`, `setIdempotent`, and other setters return a **new `BatchStatement`**; `BatchStatementBuilder` lets you configure everything once and call `build()`.

### 10.4. Batch-level CL, timeout, and idempotency

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;

BatchStatement batch = BatchStatement
        .builder(DefaultBatchType.LOGGED)
        .addStatement(first)
        .addStatement(second)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(3))
        .setIdempotent(true)
        .build();

session.execute(batch);
~~~

Here `first`/`second` are `BatchableStatement<?>` instances already prepared in the method. These settings are **examples**, not universal defaults for every cluster:

- `LOCAL_QUORUM` requires matching replication topology; with RF=3 in one DC, two replica responses are typically needed.
- `timeout(3s)` is the **driver request deadline**, not a limit on how long batchlog replay may take after a client timeout.
- `setIdempotent(true)` is valid only if **every mutation in the batch is safe to retry**.
- Never mark a `COUNTER` batch or mutations with duplicate external side effects as idempotent.

### 10.5. Protocol limits vs operational limits

Java Driver 4.x permits up to **65,536 statements** in a `BatchStatement` at the protocol level. **That is not a recommended batch size**; Cassandra enforces **much lower byte thresholds** on multi-partition batches, and production systems typically require tight workload-specific limits.

Never construct a 50,000-statement batch simply because the Java builder allows it. Before creating a batch:

1. Cap **serialized bytes** and mutation count.
2. Cap the number of distinct partition keys.
3. Choose logged vs unlogged per invariant.
4. Check consistency, timeouts, and business idempotency.
5. Measure p95/p99, coordinator load, and backpressure on a real cluster.

### 10.6. Async driver requests are not atomic Kafka/JMS commits

~~~java
// Fragment in DAO:
session.executeAsync(batch).whenComplete((result, error) -> {
    if (error != null) {
        recordFailure(error);
    } else {
        recordCompletion(result);
    }
});
~~~

`recordFailure(...)`/`recordCompletion(...)` are application-defined callbacks. `executeAsync(...)` returns `CompletionStage<AsyncResultSet>`; the callback can run **after the caller has returned**. If an inbound JMS listener already committed before the callback fires, a Cassandra failure cannot roll back the JMS message automatically.

## 11. Spring Data Cassandra: `ReactiveCassandraBatchOperations`

Spring Data Cassandra provides:

~~~java
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.ReactiveCassandraBatchOperations;
~~~

The two primary entry points:

~~~java
ReactiveCassandraBatchOperations batch = operations.batchOps();

ReactiveCassandraBatchOperations unlogged =
        operations.batchOps(DefaultBatchType.UNLOGGED);
~~~

In Spring Data Cassandra 4.5/5.1, **`batchOps()` defaults to creating a `LOGGED` batch**. To change the type, call `batchOps(BatchType)`; **do not** assume every entity list needs the default `LOGGED` batch, especially when entities span many independent partitions.

### 11.1. Entity mapping for multiple rows in one partition

Assuming `shop_integration.order_events` from section 3 exists:

~~~java
import java.io.Serializable;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public record OrderEventKey(
        @PrimaryKeyColumn(
                name = "order_id", ordinal = 0,
                type = PrimaryKeyType.PARTITIONED)
        String orderId,
        @PrimaryKeyColumn(
                name = "event_id", ordinal = 1,
                type = PrimaryKeyType.CLUSTERED)
        String eventId
) implements Serializable {}
~~~

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_events")
public record OrderEventEntity(
        @PrimaryKey OrderEventKey key,
        @Column("event_type") String eventType,
        @Column("payload_json") String payloadJson
) {}
~~~

`@PrimaryKeyClass` defines the composite primary key; `PARTITIONED` on `order_id` and `CLUSTERED` on `event_id` match the CQL schema. Java records automatically provide value equality/`hashCode`; non-matching column names require `@Column`.

On Spring Data Cassandra versions supporting record mapping, records work as shown. If an older project version has limitations with immutable record entity/constructor mapping, use standard Java classes with no-arg constructors/getters/setters and `equals/hashCode` on the key class, and verify mapping with integration tests.

### 11.2. Writing a small entity batch

~~~java
import java.util.List;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderEventBatchService {

    private final ReactiveCassandraOperations operations;

    public OrderEventBatchService(ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Mono<Void> writeSameOrder(List<OrderEventEntity> events) {
        validateSameOrderAndLimit(events);

        return operations.batchOps()
                .insert(events)
                .execute()
                .then();
    }

    private static void validateSameOrderAndLimit(
            List<OrderEventEntity> events) {
        if (events == null || events.isEmpty() || events.size() > 10) {
            throw new IllegalArgumentException("Batch requires 1..10 events");
        }
        if (events.get(0) == null || events.get(0).key() == null
                || events.get(0).key().orderId() == null
                || events.get(0).key().orderId().isBlank()) {
            throw new IllegalArgumentException("First partition key is invalid");
        }
        String orderId = events.get(0).key().orderId();
        if (events.stream().anyMatch(
                e -> e == null || e.key() == null
                        || !orderId.equals(e.key().orderId())
                        || e.key().eventId() == null
                        || e.key().eventId().isBlank())) {
            throw new IllegalArgumentException(
                    "All events must share the same Cassandra partition key");
        }
    }
}
~~~

Here `10` is an **illustrative limit**, not a Cassandra hard limit. Production must account for payload bytes, mutation count, p99 latency, and cluster config. The service **intentionally restricts to one `orderId`** because this demonstrates a single-partition batch.

### 11.3. Batch operations have a single-use lifecycle

Spring Data documentation states that `ReactiveCassandraBatchOperations` **may only be executed once**. Once `execute()` is called and subscribed, the batch instance cannot accept additional mutations or be re-executed:

~~~java
// Right: create a new instance for each batch invocation.
return operations.batchOps(DefaultBatchType.LOGGED)
        .insert(events)
        .execute();
~~~

When retrying, **never reuse an already-executed batch operations instance**. Instead, create a fresh instance inside `Mono.defer(...)` so every subscription/retry constructs its own batch:

~~~java
import reactor.core.publisher.Mono;

Mono<Void> saveWithRecreatableBatch(List<OrderEventEntity> events) {
    validateSameOrderAndLimit(events);

    return Mono.defer(() ->
            operations.batchOps(DefaultBatchType.LOGGED)
                    .insert(events)
                    .execute()
                    .then());
}
~~~

Do not blindly attach `retryWhen(...)` to every Cassandra write: retry only when mutations are idempotent and within budget. `Mono.defer` solves **recreating batch state**; it does **not** make business effects idempotent by itself.

### 11.4. Customizing batch QueryOptions

With Spring Data Cassandra **4.4+**, `withQueryOptions(QueryOptions)` is available:

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.cql.QueryOptions;
import reactor.core.publisher.Mono;

QueryOptions options = QueryOptions.builder()
        .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .timeout(Duration.ofSeconds(3))
        .build();

Mono<Void> result = operations.batchOps(DefaultBatchType.LOGGED)
        .insert(events)
        .withQueryOptions(options)
        .execute()
        .then();
~~~

`operations` and `events` exist in the enclosing service. `LOCAL_QUORUM` fits only verified replication topologies; a 3-second timeout is a lab value. If using a Spring Data version lacking `withQueryOptions`, check that version's Javadoc and configure driver statements or execution profiles rather than copying an unavailable API.

### 11.5. Batches mixing insert/update/delete

~~~java
return operations.batchOps(DefaultBatchType.LOGGED)
        .insert(newEvent)
        .update(existingEntity)
        .delete(oldEntity)
        .execute();
~~~

This fragment assumes `newEvent`, `existingEntity`, and `oldEntity` are properly mapped. All mutations must stay within **the data scope whose partition keys and business semantics you analyzed**. If those entities belong to different partitions, you are creating a **multi-partition batch**; never assume all three changes become visible atomically to cross-partition readers.

### 11.6. Notes on batch timestamps

Spring Data `ReactiveCassandraBatchOperations` supports `withTimestamp(long)` to assign a shared timestamp across the batch. CQL batches also support `USING TIMESTAMP` per Cassandra rules. **Never use a shared timestamp to represent business ordering between two competing updates to the same column**; under last-write-wins, mutations with identical timestamps trigger conflict resolution that may not match Java list order.

When current-state ordering matters, use a business `aggregateVersion`/LWT or an immutable event log; never batch two updates to the same row assuming the later statement wins.

## 12. Spring Integration Cassandra: `List` payloads and `ingestQuery`

Spring Integration Cassandra (since 6.0) uses `CassandraMessageHandler` with `ReactiveCassandraOperations`. The handler supports:

- `Type.INSERT`, `UPDATE`, `DELETE`: `@Table` entity payloads; when the payload is a **`List<entity>`**, the handler performs the corresponding batch operation.
- `setIngestQuery(...)`: `INSERT` mode with a **`List<List<?>>` matrix** payload.
- `Type.STATEMENT` / `statementFunction(...)`: caller supplies a driver `Statement<?>`, which may be a `BatchStatement`.
- One-way outbound **channel adapter** (no reply by default); outbound **gateway** for flows needing replies/results.

### 12.1. Java DSL for List<entity>

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class CassandraBatchIntegrationConfig {

    @Bean
    public IntegrationFlow batchOrderEventsFlow(
            ReactiveCassandraOperations operations) {
        return IntegrationFlow.from("validatedOrderEventBatches")
                .handle(Cassandra.outboundChannelAdapter(
                        operations, CassandraMessageHandler.Type.INSERT),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

The input channel expects a Spring Message with a `List<OrderEventEntity>` payload, **not a list of JSON strings**. Validate and map before reaching the endpoint; in this single-partition batch example, the application must verify all elements share the **same `orderId`**.

For entity lists, the Spring Integration Reference states the handler executes a **batch operation**. Spring Data `batchOps()` defaults to `LOGGED`; if you need **`UNLOGGED`** or explicit control over `BatchStatement`, use a service activator, driver API, or explicit `statementFunction(...)` rather than assuming a nonexistent DSL property switches batch types.

### 12.2. Sending a Spring Message containing a list

~~~java
import java.util.List;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

List<OrderEventEntity> batch = List.of(
        new OrderEventEntity(
                new OrderEventKey("ORD-101", "evt-108"),
                "OrderConfirmed", "json-5"),
        new OrderEventEntity(
                new OrderEventKey("ORD-101", "evt-109"),
                "OrderPaid", "json-6")
);

boolean accepted = validatedOrderEventBatches.send(
        MessageBuilder.withPayload(batch).build());
if (!accepted) {
    throw new IllegalStateException("Spring Message was not accepted");
}
~~~

`validatedOrderEventBatches` is an injected `MessageChannel` bean. `send(true)` reflects only channel/endpoint semantics; under the handler's **default async** mode, the write may still be executing after `send()` returns. With `async(false)` and `DirectChannel`, exceptions can propagate to the caller, yet Cassandra and JMS still share no transaction.

### 12.3. `ingestQuery(...)`: matrix payload vs entity list

Spring Integration provides the syntax:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow ingestOrderEventsFlow(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("cassandraIngestInput")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .ingestQuery(
                        "INSERT INTO order_events "
                        + "(order_id, event_id, event_type, payload_json) "
                        + "VALUES (?, ?, ?, ?)"),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Example payload:

~~~java
import java.util.List;
import org.springframework.messaging.support.MessageBuilder;

List<List<Object>> matrix = List.of(
        List.<Object>of("ORD-101", "evt-i01", "OrderPacked", "json-a"),
        List.<Object>of("ORD-101", "evt-i02", "OrderShipped", "json-b")
);

cassandraIngestInput.send(
        MessageBuilder.withPayload(matrix).build());
~~~

Each inner list matches the **four `?` markers** in order and CQL codecs. `List.of(...)` rejects Java nulls; if null/`UNSET` is needed, clarify the contract and use a compatible API.

**Do not confuse them:** `ingestQuery` is a Cassandra outbound handler mode accepting a **matrix**; it is not a Spring `Aggregator`, nor does it guarantee your desired logged/unlogged batch type if the DSL does not expose that choice. Check Javadoc and test your active version whenever batch type is a strict business requirement.

### 12.4. Using statementFunction to supply a prebuilt BatchStatement

~~~java
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow explicitBatchStatementFlow(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("explicitBatchRequests")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        BatchPayload request =
                                (BatchPayload) message.getPayload();

                        if (request == null || request.items() == null
                                || request.items().isEmpty()
                                || request.items().size() > 5) {
                            throw new IllegalArgumentException(
                                    "Batch size must be in 1..5");
                        }

                        BatchItem firstItem = request.items().get(0);
                        if (firstItem == null || firstItem.orderId() == null
                                || firstItem.orderId().isBlank()) {
                            throw new IllegalArgumentException(
                                    "First partition key is invalid");
                        }
                        String orderId = firstItem.orderId();
                        if (request.items().stream().anyMatch(
                                        item -> item == null
                                                || item.eventId() == null
                                                || item.eventId().isBlank()
                                                || !orderId.equals(item.orderId()))) {
                            throw new IllegalArgumentException(
                                    "Lab batch only accepts matching orderId and valid eventId");
                        }

                        var builder = BatchStatement.builder(
                                DefaultBatchType.LOGGED);
                        for (BatchItem item : request.items()) {
                            builder.addStatement(SimpleStatement.newInstance(
                                    "INSERT INTO order_events "
                                    + "(order_id, event_id, event_type, payload_json) "
                                    + "VALUES (?, ?, ?, ?)",
                                    item.orderId(),
                                    item.eventId(),
                                    item.eventType(),
                                    item.payloadJson()));
                        }
                        return builder.build();
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

DTOs:

~~~java
import java.util.List;

public record BatchItem(
        String orderId, String eventId,
        String eventType, String payloadJson) {}

public record BatchPayload(List<BatchItem> items) {}
~~~

`CassandraMessageHandler` in `STATEMENT` mode can execute a driver `BatchStatement` returned by `statementFunction`. The code above uses **positional `SimpleStatement` values** to prevent CQL injection; never read raw CQL queries from client headers.

**Critical checks missing if copied verbatim into production:** this example validates item count, `eventId`, and identical `orderId`, yet does not check total serialized bytes, `eventType`/JSON contracts, authorization, uniqueness, or overall quotas. It enforces a **single-partition batch**; removing the `orderId` check and sending multiple orders turns it into a **multi-partition logged batch** with partial visibility and batchlog overhead.

### 12.5. Adapter or gateway?

| Endpoint | Use when | Note |
|---|---|---|
| `Cassandra.outboundChannelAdapter(...)` | One-way write, no Spring reply needed | Monitor completion/error paths |
| `Cassandra.outboundGateway(...)` | Reply/result/query output needed | Reactive result/`WriteResult` per operation/version |
| Custom `@ServiceActivator` calling `batchOps(...)` | Need explicit control over batch type and response/error policy | No automatic source ACK linkage |
| Custom `@ServiceActivator` using driver `BatchStatement` | Need direct control over CQL options, timestamps, and types | Own lifecycle, metrics, and retries explicitly |

When you need to inspect conditional batch/LWT `[applied]` status, do not rely on a non-replying outbound adapter treating `send(true)` as applied. Use a gateway/driver API that reads the result and understand Cassandra's conditional-batch restrictions.

## 13. Choosing the write approach by workload, not batch preference

### 13.1. Decision flowchart

~~~mermaid
flowchart TD
    A["Multiple mutations to write?"] --> B{"Same Cassandra partition?"}
    B -->|"Yes"| C{"Mutations belong to one business aggregate?"}
    C -->|"Yes"| D["Consider a small single-partition batch"]
    C -->|"No"| E["Separate writes or small batches as needed"]
    B -->|"No"| F{"Truly need eventual completion together?"}
    F -->|"Yes, few mutations"| G["Small multi-partition LOGGED batch"]
    F -->|"No, throughput is the goal"| H["Independent async writes + bounded concurrency"]
    D --> I["Measure p99, failures, and idempotency"]
    E --> I
    G --> I
    H --> I
~~~

### 13.2. Selection table

| Workload | Mechanism to consider | Why | Avoid |
|---|---|---|---|
| One event → one single row | One independent `INSERT` | Simple, efficient routing | Wrapping a single statement in a pointless batch |
| One event → three rows in same partition | Small single-partition `BATCH` | Partition isolation, less overhead | Sending huge cross-partition batches |
| Two rows in two tables/partitions needing eventual co-completion | Small multi-partition `LOGGED BATCH` | Batchlog supports recovery | Treating reads from two tables as an atomic snapshot |
| 10,000 independent events | Async writes with concurrency cap | Token-aware routing, spreads coordinator load | A 10,000-row `LOGGED BATCH` |
| Backfilling many partitions | Partition-aware chunks + throttling | Per-chunk recovery and monitoring | Unbounded ingest batches |
| Updating cumulative counters | `COUNTER` mutation/batch when appropriate | Counters have unique semantics | Blind retries |
| Updating current state with version guard | Appropriate single-partition LWT | Enforces compare-and-set | Using a logged batch instead of version checks |

### 13.3. Grouping messages by order: business grouping vs Cassandra partitions

Spring Integration's `Aggregator` groups multiple Spring Messages into a list message. If you correlate by `orderId`, elements **may** share one Cassandra partition when the schema partition key is `order_id`.

However, if the Cassandra partition key is `(tenantId, orderId, bucketMonth)`, grouping by `orderId` alone is **not enough**. Messages spanning month boundaries or different tenants belong to **multiple partitions** even though the Java group shares one `orderId`.

**Rule:** compute the Cassandra partition key from the **CQL schema** and validated payload; align Spring correlation/group keys with the **entire composite partition key**, not just one representative header.

### 13.4. A simple predicate for single-partition batches

~~~java
static void requireSamePartition(List<OrderEventEntity> events) {
    if (events == null || events.isEmpty()) {
        throw new IllegalArgumentException("Empty batch");
    }
    String orderId = events.get(0).key().orderId();
    if (events.stream().anyMatch(e ->
            e == null || e.key() == null
                    || !orderId.equals(e.key().orderId()))) {
        throw new IllegalArgumentException(
                "Rows do not share the same Cassandra partition");
    }
}
~~~

This code targets the **lab schema whose sole partition key is `orderId`**. For composite partition keys, compare *all partition columns*. Always validate non-null `orderId` beforehand rather than calling `equals` on null.

### 13.5. Sizing batches by bytes, not only row count

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;

static void validateBatchSize(List<BatchItem> items) {
    if (items == null || items.isEmpty() || items.size() > 10) {
        throw new IllegalArgumentException("Maximum 10 items in lab");
    }

    long estimatedBytes = items.stream()
            .mapToLong(item -> {
                if (item == null || item.payloadJson() == null) {
                    throw new IllegalArgumentException("Missing payload");
                }
                return item.payloadJson()
                        .getBytes(StandardCharsets.UTF_8).length;
            })
            .sum();

    if (estimatedBytes > 16 * 1024) {
        throw new IllegalArgumentException(
                "Batch JSON payload exceeds lab limit");
    }
}
~~~

**The 16 KiB limit is illustrative only.** This snippet sums raw JSON bytes **without** accounting for Cassandra serialization, field names, protocol framing, partition keys, or mutation metadata. Production must enforce a safe ceiling well below actual failure thresholds with comfortable headroom, while also bounding **distinct partition keys**.

## 14. Consistency levels, timestamps, and TTL in batches

### 14.1. Consistency remains Cassandra's ACK condition

With RF=3 in a single DC, `LOCAL_QUORUM` waits for two replica responses per consistency rules. When a batch spans **multiple partitions**, **multiple replica sets** are involved. A logged batchlog drives mutations past coordinator failures; it does **not** mean every replica of every partition applied the mutation simultaneously when the client observes success.

| CL | Core meaning | Limit with multi-partition `BATCH` |
|---|---|---|
| `ONE` | One replica responds per policy | Creates no cross-partition snapshot |
| `LOCAL_QUORUM` | Local DC quorum | Creates no cross-partition isolation |
| `ALL` | Waits for all involved replicas | Availability drops when any replica fails; still not an SQL transaction |
| `SERIAL`/`LOCAL_SERIAL` | Serial consistency for LWT | Not a general CL for regular batches |

### 14.2. A batch can share a single write timestamp

~~~sql
BEGIN BATCH USING TIMESTAMP 1763884800000000
    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-t01', 'OrderPacked', 'json-a');

    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-t02', 'OrderShipped', 'json-b');
APPLY BATCH;
~~~

CQL `USING TIMESTAMP` expects **microseconds since Unix epoch**, not raw Java `Instant.toEpochMilli()`. The value above is an **illustrative timestamp**, not a mandatory current clock. Once a batch-level timestamp is specified, do not mix per-statement timestamps arbitrarily per your Cassandra version's CQL restrictions.

**Never confuse** Cassandra's **write timestamp** with business `occurredAt`/`aggregateVersion`. The server timestamp governs conflict resolution; if two mutations on the same column/row share the same timestamp, tie-break rules—not CQL batch order—determine the winner.

### 14.3. Event TTL differs from batch timeout

| Attribute | Purpose |
|---|---|
| CQL `USING TTL n` / Spring Data `WriteOptions.ttl(...)` | How long data is retained before expiration |
| Driver `Statement.setTimeout(Duration)` | How long the client waits for Cassandra's response |
| Cassandra `write_request_timeout` | How long coordinator waits for replica ACKs |
| `JMS timeToLive` | How long a JMS message stays valid on the broker |
| Spring gateway `replyTimeout` | How long a Spring caller waits for a reply |

Setting a TTL on a Cassandra row **does not acknowledge the source JMS message**, establish a retry policy, or halt batchlog recovery. When retrying writes with TTL, note that **re-sending can shift expiration times** and mutation timestamps; evaluate true data idempotency.

### 14.4. Conditional batches / LWT are not regular logged batches

A conditional `IF NOT EXISTS` or `IF version = ?` requires **LWT/Paxos** with serial consistency and valid conditions within Cassandra's supported scope. Conditional batches carry restrictions (notably requiring mutations to target the same partition) that regular batches do not.

**Guidance:** if the domain requires transitioning state from `PAID(version=2)` to `SHIPPED(version=3)` only when version is unchanged, use an appropriate **conditional update**. Never batch two consecutive `UPDATE state` statements assuming `LOGGED` resolves concurrent-writer races.

## 15. Timeouts, retries, and idempotency of a batch

### 15.1. A timeout does not tell how many mutations persisted

~~~mermaid
sequenceDiagram
    participant JMS as JMS Broker
    participant App as Integration Handler
    participant Coord as Cassandra Coordinator
    participant R1 as Partition A replicas
    participant R2 as Partition B replicas
    JMS->>App: Deliver eventBatchId=batch-001
    App->>Coord: BEGIN BATCH A,B
    Coord->>R1: Apply A
    R1-->>Coord: ACK
    Coord->>R2: Apply B
    Note over Coord,App: Network response lost / client timeout
    Coord--xApp: No timely response
    App-->>JMS: Exception -> rollback per listener policy
    JMS->>App: Redeliver batch-001
    Note over App: Retry with same business IDs and partitions
~~~

Both A and B **may** have persisted; or A may be temporarily visible while batchlog/retries finish B; or the request never arrived. The caller needs **idempotent retry/reconciliation**, never minting fresh IDs just because a timeout occurred.

### 15.2. An idempotent BATCH must be idempotent on every mutation

| Mutation | Retry whole batch? | Notes |
|---|---|---|
| `INSERT` immutable event with fixed full primary key | Usually safe | Provided TTL/timestamp/payload stay consistent |
| `DELETE` with same primary key | Usually safe, watch timestamps/GC | Tombstones and concurrent writes can interact |
| `UPDATE` state with version guard | Conditionally | Inspect applied result and ordering |
| Increment Cassandra counter | **Unsafe** for blind retry | Can increment twice |
| `INSERT` with newly generated consumer `eventId` | **Unsafe** | Retries create duplicate business rows |
| Send email/HTTP after batch | **Not** protected by batch | External system needs its own idempotency |

**Calling `setIdempotent(true)` on `BatchStatement` does not automatically make each mutation idempotent.** The driver uses that flag solely to govern retries/speculative executions; it keeps no deduplication inbox.

### 15.3. Multi-layer retry budgets

Suppose:

~~~text
Driver retry:                 max 1 retry/request
Service-layer retry:          max 2 retries/delivery
JMS broker redelivery:        max 5 deliveries
Batch mutations/request:      3
~~~

One event group can multiply into far more attempts than expected. With two driver executions per service attempt and three service attempts per delivery, five deliveries produce **up to 30 batch executions**, meaning **up to 90 mutation attempts** before even counting speculative executions. Never let uncoordinated retry storms amplify across all nodes and partitions.

### 15.4. Bounding retries by exception type

| Error | Suggested strategy |
|---|---|
| `DriverTimeoutException` | Outcome uncertain; bounded idempotent retry/reconcile |
| `WriteTimeoutException` | Some mutations may have applied; retry carefully |
| `UnavailableException` | Shed load, check cluster/CL; backoff |
| `OverloadedException` | Reduce concurrency/batch size; avoid hot retries |
| `InvalidQueryException` | Fail fast, fix schema/CQL; never retry |
| Codec/type mismatch | Fix contract/mapping; never retry identical input |
| Authorization failure | Fix ACLs/secrets; never retry indefinitely |
| LWT `applied=false` | Business condition unmet; not a transport failure |

### 15.5. A batch is not a rollback journal

Never write logic like:

~~~text
try {
    loggedBatch();
} catch (TimeoutException ex) {
    // WRONG: assumes the database wrote nothing and mints new IDs.
    createNewIdsAndRetry();
}
~~~

Instead:

~~~text
onTimeout(batchId):
    keep original event IDs and full Cassandra primary keys
    classify retryable vs permanent errors
    retry only if idempotent and within budget
    read/reconcile when the outcome is unknown
    quarantine conflicting duplicates or unrepairable events
~~~

This is **pseudocode**, not a built-in Spring API. Cassandra and the message broker do not share a rollback boundary.

## 16. JMS/Kafka acknowledgment: which system owns "batch succeeded"?

### 16.1. A JMS listener receiving a batch message

~~~mermaid
flowchart LR
    JMS["JMS message batch-001"] --> L["Message-driven inbound adapter"]
    L --> D["DirectChannel"]
    D --> V["Validator/Transformer"]
    V --> C["Cassandra handler async=false"]
    C --> DB[("Cassandra logged batch")]
    DB -. "Completion / error" .-> C
    C -. "Propagate" .-> L
    L --> ACK["JMS commit / rollback per policy"]
~~~

In a synchronous flow with a transacted listener, Cassandra exceptions can propagate back to the JMS listener and trigger broker **redelivery**. Yet if Cassandra already applied the mutations and the JMS commit fails or the JVM crashes, the batch will be **redelivered**; idempotency remains mandatory.

### 16.2. When using ExecutorChannel or the default async handler

~~~text
JMS receive
   -> in-memory ExecutorChannel
   -> listener callback returns
   -> JMS commit (per config)
   -> Cassandra batch starts / finishes later
   -> Cassandra timeout / failure
   -> Cannot roll back already-committed JMS message
~~~

`CassandraMessageHandler` in Spring Integration **defaults to `async=true`**. Setting `async(false)` waits for completion on synchronous paths when appropriate, without creating an atomic transaction between Cassandra and JMS. An in-memory `QueueChannel`/`ExecutorChannel` is not a durable queue replacing the broker.

### 16.3. Kafka: offset commits are independent of CQL batches

Kafka offsets track consumer progress per policy; they share **no atomic transaction** with Cassandra `BATCH`. If the consumer commits offsets before Cassandra completes, downstream failures lose automatic replay. If Cassandra finishes and the JVM crashes before offset commit, records will replay.

Resilient designs rely on one or more of:

1. Ack/commit the source only after Cassandra completion where supported.
2. Durable handoff/inbox enabling replay after async failures.
3. Idempotent event IDs and deterministic primary keys.
4. Reconciliation for uncertain outcomes and potential partial visibility.
5. DLQ/quarantine for data errors unfixable by retries.

### 16.4. One message with 10 events can be poisoned by a single bad event

In many flows, one JMS message delivers a **batch of 10 business events**. If one element carries an invalid CQL type:

- The handler may reject the entire batch or fail before writing.
- The broker may redeliver the **entire JMS message**.
- Repeated retries will never fix the malformed element.
- Sending the whole batch to a DLQ forces 9 valid events to wait behind 1 bad event.

Decide your policy upfront:

- **Fail the whole batch:** when all events truly form one indivisible business unit.
- **Split and quarantine per event:** when events are independent and high availability/throughput matters.
- **Durable preprocessing:** parse/validate each event before batching to avoid poison batches.

Never split a logged batch into independent writes if the domain explicitly requires shared batchlog completion semantics; clarify the invariant first.

## 17. Lifecycle, validation, and observing batches in production

### 17.1. Lifecycle from source message to batch completion

~~~mermaid
flowchart TD
    R["Receive Spring Message"] --> V["Validate schema, tenant, IDs, payload sizes"]
    V --> K["Compute Cassandra partition key"]
    K --> G{"Single partition?"}
    G -->|"Yes"| S["Small batch or independent writes"]
    G -->|"No"| N{"Need batchlog completion?"}
    N -->|"Yes"| L["Small LOGGED batch"]
    N -->|"No"| I["Independent async writes, bounded"]
    S --> E["Execute"]
    L --> E
    I --> E
    E --> O{"Completion observed?"}
    O -->|"Success"| C["Ack/checkpoint per policy"]
    O -->|"Error/unknown"| X["Idempotent retry / reconcile / DLQ"]
~~~

**Core message:** validate and classify **before** touching Cassandra, rather than letting a giant multi-partition batch fail at the coordinator. A batch may still be in flight when `send()` returns true if downstream runs asynchronously.

### 17.2. Useful metadata contract

| Field/header | Trusted source | Purpose |
|---|---|---|
| `eventId` | Business producer | Idempotent key for each event |
| `batchId` | Application aggregator/producer | Correlation/logging; does not replace event IDs |
| `tenantId` | Authenticated context | Scope and authorization |
| `partitionKey` | Transformer from schema/payload | Decides single- vs multi-partition batch |
| `schemaVersion` | Validated event contract | Selects compatible DTO/transformer |
| `receivedAt` | Message transport/time source | Observability; never replaces event `occurredAt` |
| `retryAttempt` | Retry infrastructure | Tracks retry budget |
| `traceId` | Tracing infrastructure | Links source→Cassandra failures |

**`batchId` identifies the processing group, not a unique primary key for every event.** Even if a retry generates a new `batchId` while keeping original event IDs and primary keys intact, writes remain idempotent; however, batch-level reconciliation requires clear source/target mapping.

### 17.3. Never accept raw CQL from external messages

Inside `statementFunction(...)`, strictly avoid:

~~~java
// DO NOT DO THIS: query comes directly from HTTP/JMS payload.
SimpleStatement unsafe = SimpleStatement.newInstance(
        (String) message.getPayload());
~~~

Replace with a **static** query and bound values:

~~~java
SimpleStatement safe = SimpleStatement.newInstance(
        "INSERT INTO order_events "
        + "(order_id, event_id, event_type, payload_json) VALUES (?, ?, ?, ?)",
        item.orderId(), item.eventId(), item.eventType(), item.payloadJson());
~~~

Here `item` is a validated `BatchItem` DTO. Prepared/bound values prevent clients from changing table, column, or operation names; if multiple tables are needed, select only from a code-defined **allowlist**, never concatenating untrusted client headers.

### 17.4. Never share a singleton batch builder

`CqlSession` is a long-lived, thread-safe resource. `PreparedStatement` can be reused. However:

- `BatchStatementBuilder` is a mutable builder for **one batch invocation**, never shared across threads.
- Built-in `BatchStatement` is immutable; create a fresh instance per group.
- `ReactiveCassandraBatchOperations` is a **single-execute** builder/operation object, never retained as a singleton bean across events.
- `MessageChannel` transports messages without preserving durable state across process crashes.

### 17.5. Shutdown and in-flight batches

When a service receives `SIGTERM` or closes the Spring context:

1. Stop accepting new messages at inbound endpoints/broker listeners via platform mechanisms.
2. Drain **in-flight Cassandra batches** within the shutdown budget where supported.
3. Do not commit JMS/Kafka sources before completion when required by contract.
4. Preserve durable replay paths if shutdown exceeds its deadline.
5. Recover using the same reproducible event IDs and batch memberships.

Never claim that calling `stop()` on an endpoint automatically waits for every reactive Cassandra operation to finish persisting; test actual shutdown behavior on your configuration.

## 18. Observability: finding bottlenecks at the right layer

| Metric/log | Where measured | What to watch |
|---|---|---|
| Batch requests/s | Application/driver | Batch frequency |
| Mutations/batch p50/p95/p99 | Application | Sudden spikes in rows per batch |
| Serialized bytes/batch | Application/driver | Approaching warn/fail thresholds |
| Distinct partition keys/batch | Application | Multi-partition batches spanning many keys |
| `LOGGED` vs `UNLOGGED` vs `COUNTER` | Application config | Does batch type match business invariant? |
| Cassandra `BatchlogReplays` | Cassandra cluster | Coordinator failure/replay activity |
| `BatchSize` / `unlogged-across-partitions` warnings | Cassandra logs/metrics | Batch anti-patterns |
| Coordinator write latency p95/p99 | Cassandra/driver | Hot coordinators, network/I/O |
| Pending tasks/compactions/tombstones | Cassandra nodes | Background overload or delete pressure |
| Driver retries/timeouts | Driver | Retry storms and latency |
| Reactive in-flight operations | Application | Missing concurrency cap or stalled drain |
| JMS queue depth / Kafka lag | Source broker | Slow Cassandra creating backlog |
| Duplicate/conflicting event IDs | Domain metrics | Replay churn or bad producer contracts |
| DLQ/quarantine rate | Integration error flow | Poison messages or batch failures |

**Do not treat `BatchlogReplays=0` as an error:** in a healthy cluster, replay counts stay low. What warrants investigation is rising replays coinciding with write timeouts/latency spikes, or stalled batchlog cleanup.

### 18.1. What to do when Cassandra logs batch warnings?

If logs report a **large batch** or **unlogged batch across many partitions**:

1. Trace `batchId`, upstream source, distinct partition-key count, and byte size.
2. Determine whether `logged` was chosen merely for throughput or truly for completion semantics.
3. Break into **bounded independent async writes** if mutations are independent.
4. When logged batches are truly needed, check whether related data can be **co-located in one Cassandra partition**.
5. Enforce batch row/byte caps before building statements.
6. Measure cluster p95/p99, replica balance, coordinator load, and retries.
7. **Never merely raise `batch_size_warn_threshold`** to silence the warning.

### 18.2. Source and domain alerting

Logs should include event IDs, `batchId`, logical operation, outcome, CL, elapsed time, and exception type. Never log JSON payloads containing PII/tokens/credentials or raw CQL with secret values. For metrics, `batchId`/`eventId` have high cardinality and belong in logs/traces rather than metric labels.

## 19. Troubleshooting table

| Symptom | Possible cause | Fix |
|---|---|---|
| CQL reports `syntax error near LOGGED` | Wrote `BEGIN LOGGED BATCH` | Use `BEGIN BATCH` (logged is default) |
| `SELECT` inside `BATCH` rejected | `BATCH` accepts mutations only | Separate `SELECT` queries |
| Counter batch fails on regular `INSERT` | Mixed counter and regular mutations | Use `BEGIN COUNTER BATCH` solely for counters |
| Multi-partition `BATCH` is very slow | Batchlog/coordinator overloaded by many mutations | Shrink batches or use bounded independent async writes |
| Cassandra logs `Batch too large` | Total serialized bytes exceeded threshold | Split batches; cap bytes and mutations |
| Warning: unlogged across partitions | `UNLOGGED` batch spans many partition keys | Group by partition or stop batching |
| Reading table A shows row while table B does not | Cross-partition partial visibility | Do not assume snapshot isolation; reconcile |
| `WriteTimeoutException` yet some rows exist | Timeout after partial/completed writes | Idempotent retry and reconciliation |
| Batch retry creates new rows | Consumer minted new `eventId`/partition key | Preserve business IDs and deterministic keys |
| Counters increment higher than expected | Retried counter batch | Avoid blind retries; build deduplicated aggregates |
| Batch with two `UPDATE`s ignores CQL order | Same timestamp or concurrent writes | Use aggregate version, LWT, or distinct row keys |
| `List<entity>` fails mapping | Entity lacks `@Table`/proper primary key | Fix annotations or transformer |
| `List<String JSON>` fails in `Type.INSERT` | Handler expects entities, does not auto-parse JSON | Add JSON-to-entity transformer |
| `ingestQuery` binding error | `List<List<?>>` missing values or mismatched order/codecs | Check `?` count, row width, and types |
| `SimpleStatement` named parameters fail in `BatchStatement` | Unsupported in Driver 4.x batches | Use prepared+bound or positional simple statements |
| `BatchStatement.setTimeout(...)` has no effect | Ignored return value of immutable setter | Reassign batch or use builder |
| `ReactiveCassandraBatchOperations` throws executed twice | Reused same instance after subscription | Create fresh `batchOps` per invocation/retry |
| Reactive `execute()` writes nothing | Publisher was never subscribed | Return `Mono` to framework or attach consumer |
| JMS commits then Cassandra batch fails | Async handler/channel acked too early | Use durable handoff or await completion |
| Cassandra finishes yet JMS redelivers | Broker commit is not atomic with DB | Idempotency and consistent event IDs |
| One poison event blocks 9 valid events | Bundled independent events into one batch | Validate/split/quarantine before writing |
| Batchlog replays rising | Coordinator/node instability or overload | Inspect failures, latency, and batch sizes |
| Cross-DC read-after-write lags | `LOCAL_QUORUM` is local to one DC | Re-evaluate consistency/replication SLAs |
| CQL batches trigger OOM/GC | Coordinator handling oversized batches | Cut batch bytes/concurrency and review data model |

### 19.1. Ask before retrying

**You may retry a three-mutation request only when all three have safe semantics.** If one mutation increments a counter, the entire batch is **non-idempotent**. If one mints a fresh ID every attempt, replays spawn extra business rows. When all three are immutable `INSERT`s on fixed keys, retries are generally safe—still verify timestamps, TTLs, conflicting duplicates, and source acknowledgments.

## 20. Hands-on lab: from CQL BATCH to Spring Integration

**Environment:** Java 17+, compatible Spring Integration 6+/7+ and Spring Data Cassandra reactive, a Cassandra test cluster, and `cqlsh`. Testcontainers suffices for API exercises, while coordinator-failure/batchlog-recovery and quorum exercises require a **real multi-node cluster or managed test environment**. Never inject network faults, kill nodes, or raise batch thresholds in production.

### Exercise A — Single-partition CQL logged batch

1. Create `shop_integration.order_events` from section 3.
2. Insert two rows with `order_id='ORD-101'` via `BEGIN BATCH ... APPLY BATCH`.
3. Query back:

~~~sql
SELECT order_id, event_id, event_type
FROM shop_integration.order_events
WHERE order_id = 'ORD-101';
~~~

4. Inspect the full primary key and confirm both rows belong to **one partition**.
5. Re-run the **exact same CQL** to observe upsert semantics: no new row with a different `event_id` appears.
6. Send a row with the same `event_id` but different `payload_json`, identifying the risk of a **conflicting duplicate**.
7. Record p95 latency and cluster metrics for the small batch.

**PASS:** understands `BEGIN BATCH` defaults to `LOGGED`, knows single-partition batches can bypass the batchlog, and never treats conflicting payloads on retry as idempotent.

### Exercise B — Multi-partition logged batch and partial visibility

1. Prepare two partition keys: `ORD-101` and `ORD-102`.
2. Send a `BEGIN BATCH` containing one `INSERT` per order.
3. Confirm that when the **CQL batch completes successfully**, both rows persist per the request's consistency/timeout.
4. In a failure-injection environment, simulate a slow or crashing node/coordinator mid-dispatch; inspect batchlog replay/timeout logs.
5. Have a concurrent reader query both partitions during writes/recovery; note the **possibility of partial visibility** (not every run will catch the window).
6. Wait for recovery/reconciliation and re-query by key. Never treat a `WriteTimeoutException` as proof that neither row was written.
7. Sketch a timestamped event/ACK timeline showing where a lost response can happen.

**PASS:** explains eventual completion vs snapshot isolation and never claims "atomic SQL transaction proved" from test results.

### Exercise C — UNLOGGED and COUNTER BATCH

1. Using **test data**, run `BEGIN UNLOGGED BATCH` across `ORD-101`/`ORD-102`.
2. Simulate coordinator failure (if a multi-node chaos setup is available); explain why partial application can occur without batchlog recovery.
3. Run `BEGIN COUNTER BATCH` on the test counter table from section 8.
4. Increment a counter, then resend the same business event; observe the double-increment risk.
5. Explain why counter updates cannot be mixed into a regular `BATCH`.
6. Propose how to recompute aggregates from a deduplicated/replayable event log when counters must be exact.

**PASS:** distinguishes `LOGGED`, `UNLOGGED`, and `COUNTER` in both semantics and retry behavior.

### Exercise D — Driver BatchStatement and prepared binding

1. Create a Spring-managed singleton `CqlSession` and prepare `insertEvent` once.
2. Call `writeTwoEventsSameOrder(...)` in `OrderEventBatchDao`.
3. Use `BatchStatement.builder(DefaultBatchType.LOGGED)` with two `BoundStatement`s.
4. Switch to `DefaultBatchType.UNLOGGED` on the same partition **solely to explore the API**, not as a full benchmark.
5. Configure `setConsistencyLevel` and `setTimeout`, and verify immutable setter behavior.
6. Intentionally pass a `SimpleStatement` with named CQL markers into a batch (negative test), then fix using **prepared+bound**.
7. Fire 10 concurrent requests, verifying **each request gets its own `BatchStatement`** while `PreparedStatement` is reused.

**PASS:** no user data concatenated into CQL strings, no shared global mutable builder, and never treats 65,536 as a target batch size.

### Exercise E — ReactiveCassandraBatchOperations

1. Create `OrderEventEntity`/`OrderEventKey` and `ReactiveCassandraOperations`.
2. Run `batchOps().insert(events).execute()` for two rows of the same order.
3. Consume `Mono<WriteResult>` via Reactor `StepVerifier` or a framework subscriber; query the DB back.
4. Execute/subscribe one batch-operations instance, then attempt to reuse it to observe `IllegalStateException` on versions enforcing single-use.
5. Fix by **creating a fresh instance** per call/`Mono.defer(...)`.
6. Try `batchOps(DefaultBatchType.UNLOGGED)` in tests and understand why choosing batch type intentionally matters.
7. On supporting Spring Data versions, apply `withQueryOptions(...)` for CL/timeout and measure elapsed time.

**PASS:** knows batch operations default to `LOGGED`, execute once per instance, and require subscription for `Mono` I/O.

### Exercise F — Spring Integration List<entity> and ingestQuery

1. Build `batchOrderEventsFlow` with `Cassandra.outboundChannelAdapter(operations, Type.INSERT)`.
2. Send `Message<List<OrderEventEntity>>` with two events for one order.
3. Query Cassandra to confirm both rows share the partition key with exact event IDs.
4. Send two events from **two different orders** to verify the app must classify multi-partition batches before sending.
5. Build `ingestOrderEventsFlow` and send a **`List<List<Object>>`** payload matching the CQL marker count.
6. Send an inner list missing a value or with a wrong Java type; confirm the error hits your validation/error path.
7. Switch to `statementFunction(...)` with an explicit `BatchStatement`; compare batch-type control.

**PASS:** distinguishes entity lists from value matrices, keeps raw JSON `String` out of entity mode, and remembers the one-way adapter emits no reply.

### Exercise G — Controlled throughput comparison

On the test cluster, create three workloads with identical total event counts and payload bytes:

| Workload | Variant |
|---|---|
| W1 | One independent Cassandra `INSERT` per event with a concurrency cap |
| W2 | Events for the same order grouped into small single-partition batches |
| W3 | Events across different orders grouped into multi-partition `LOGGED` batches |

Procedure:

1. Warm up the driver prepared-statement cache and cluster.
2. Run each workload under controlled concurrency and payload size.
3. Measure throughput, p50/p95/p99 latency, max in-flight requests, coordinator CPU, and errors.
4. Inspect Cassandra batch-size warnings, batchlog replay metrics, and node load distribution.
5. Compare results **without assuming W3 wins merely because the client sends fewer requests**.
6. Vary rows/batch in small steps, noting when latency spikes or cluster warnings fire.

**PASS:** batching decisions rest on benchmark and partition-distribution data, not SQL-transaction assumptions.

### Exercise H — JMS source acknowledgment and crash recovery

1. Configure a JMS message-driven inbound adapter with test transaction/redelivery settings.
2. Send a message carrying `BatchPayload` with `batchId=batch-001` and two stable `eventId`s.
3. With a sync Cassandra handler and `DirectChannel`, verify propagated errors trigger JMS rollback/redelivery.
4. Let Cassandra finish, simulate a JVM crash before JMS commit, and observe broker redelivery of `batch-001`.
5. Confirm **identical full Cassandra primary keys** prevent duplicate rows with newly minted event IDs.
6. Switch to `ExecutorChannel` or an async handler; prove the source callback **can return before DB completion**.
7. Add a durable handoff/recovery path or adjust ack policies to fit the SLA.
8. Inject one invalid event into a batch and evaluate fail-whole-batch vs split/quarantine per event.

**PASS:** never claims "transacted JMS + logged batch = exactly-once"; explains both failure windows and idempotent replay.

### Exercise I — LWT and business invariants

1. Create `order_current_state` with `orderId` as partition key and `version` as a regular column.
2. Run conditional `UPDATE ... IF version = ?` within Cassandra's supported scope.
3. Inspect `[applied]` and distinguish `false` from exceptions/timeouts.
4. Place two same-partition mutations inside a conditional batch **using syntax supported by your Cassandra version**.
5. Attempt a conditional batch **across partitions** in a negative test and observe Cassandra's restrictions.
6. Compare LWT cost/latency against regular `BATCH`.
7. Explain why LWT does not form a transaction with JMS/Kafka.

**PASS:** never confuses a logged batch with serializable compare-and-set; knows when a business version guard is needed.

### Final verification matrix

| Check | PASS outcome |
|---|---|
| CQL | `BEGIN BATCH`, `BEGIN UNLOGGED BATCH`, and `BEGIN COUNTER BATCH` use valid syntax |
| Single-partition | Identical partition keys; understands isolation scope |
| Multi-partition | Understands batchlog/eventual completion and partial visibility |
| `UNLOGGED` | Not confused with recovery-guaranteed logged batches |
| `COUNTER` | Non-idempotent mutations are not blindly retried |
| Timestamps | Statement order in batch is not assumed to dictate final column winner |
| Driver | `BatchStatement`/`DefaultBatchType` + positional/prepared binding used properly |
| Immutable builder | `BatchStatement` never modified while discarding setter results |
| Spring Data | `batchOps` executed once, `Mono` subscribed, batch type chosen deliberately |
| Spring Integration | `List<entity>` distinguished from `List<List<?>>`; `statementFunction` returns `BatchStatement` |
| Validation | Caps bytes, row count, and distinct partitions |
| Errors | Distinguishes timeouts, unavailable, and permanent errors |
| Retries | Preserves `eventId`s/partition keys without duplicating side effects |
| Broker ACK | Does not commit before completion when business contract forbids |
| Recovery | Durable replay, quarantine, and reconciliation in place |
| Benchmarks | Measures p95/p99, retries, batchlog, and per-coordinator load |

**What unit mocks cannot prove:** batchlog replay, coordinator failover, partial visibility, Cassandra consistency/timeouts, performance under load, and JMS/Kafka commit boundaries. Use a real multi-node Cassandra test cluster, network fault injection, and a real test broker when verifying these behaviors.

## 21. Self-assessment questions

1. Does CQL `BEGIN BATCH` default to `LOGGED` or `UNLOGGED`?
2. Why isn't `BEGIN LOGGED BATCH` valid standard syntax?
3. How does `BEGIN UNLOGGED BATCH` differ from `LOGGED` in recovery behavior?
4. Which column/mutation types use `BEGIN COUNTER BATCH`?
5. Why can't counter updates and regular writes be mixed in the same batch?
6. Can a Cassandra batch contain `SELECT` and `CREATE TABLE`?
7. Why can Cassandra optimize away the batchlog for single-partition batches?
8. Does a multi-partition `LOGGED` batch prevent readers from seeing partial state?
9. What is the batchlog? Is it a JMS queue or a durable application event log?
10. When a coordinator loses connectivity after writing the batchlog, why can mutations still replay?
11. Does a `WriteTimeoutException` prove no rows were persisted?
12. Why isn't a logged batch equivalent to a distributed SQL transaction with snapshot isolation?
13. Do two updates to the same row in one batch apply in CQL statement order?
14. How does Cassandra's write timestamp differ from business event timestamps and aggregate versions?
15. Does CQL `USING TIMESTAMP` take microseconds or milliseconds?
16. Why is a multi-partition `UNLOGGED` batch a common throughput anti-pattern?
17. For 1,000 independent events, should you consider bounded independent async writes or a 1,000-row `LOGGED` batch?
18. Which metrics measure large batches by serialized bytes and partition-key count?
19. What do `batch_size_warn_threshold` and `batch_size_fail_threshold` protect against?
20. Why shouldn't you simply raise warn/fail thresholds to make Cassandra warnings disappear?
21. Which Java Driver API uses `DefaultBatchType.LOGGED`, `UNLOGGED`, and `COUNTER`?
22. Does Java Driver 4.x support `SimpleStatement` with named parameters directly inside `BatchStatement`?
23. Why is `PreparedStatement.bind(...)` helpful when sending many batches?
24. Does `BatchStatement` in Driver 4.x have in-place mutable setters?
25. Is the driver's 65,536-statement limit a recommended production batch size?
26. Which batch type does `ReactiveCassandraOperations.batchOps()` use by default?
27. How many times may each `ReactiveCassandraBatchOperations` instance be executed?
28. Why is `Mono.defer(...)` helpful when retrying a reactive batch?
29. When should you use `withQueryOptions(...)` instead of changing global driver config?
30. In Spring Integration, how is a `List<entity>` payload handled differently from `List<List<?>>`?
31. What payload contract does `ingestQuery` enforce?
32. When should `statementFunction(...)` return a driver `BatchStatement`?
33. Why isn't `MessageChannel.send(true)` enough to conclude an async Cassandra batch finished writing?
34. Does a Cassandra logged batch commit a JMS session or Kafka offset atomically?
35. When the DB wrote yet the JVM crashed before JMS commit, which identifiers must redelivery preserve?
36. Why do counter increments inside a batch make retries dangerous?
37. If a batch has one poison event and nine valid events, should you fail the whole batch or split it? What determines that choice?
38. Why must Spring's `Aggregator` match the **entire composite partition key** when grouping messages?
39. What does a conditional LWT batch solve that a regular logged batch cannot?
40. Name at least five metrics or logs useful for investigating large batches and batchlog replays.

## 22. Official references

- [Apache Cassandra — CQL Data Manipulation: BATCH](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `BEGIN BATCH`/`UNLOGGED`/`COUNTER` syntax, shared timestamps, single-partition isolation, and batchlog semantics.
- [Apache Cassandra — CQL v3 Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/cql_singlefile.html): `BATCH` statement, restrictions, and examples.
- [Apache Cassandra — Cassandra Configuration Reference](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): batch size warning/failure thresholds and operational settings.
- [Apache Cassandra — Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/): partitioning, coordinators, replicas, and consistency.
- [Apache Cassandra Java Driver 4.19 — Batch](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/batch/): `BatchStatement.newInstance`, `builder`, `DefaultBatchType`, immutability, and statement limits.
- [Apache Cassandra Java Driver 4.19 — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): positional/named binding, immutable `BoundStatement`, and prepared cache.
- [Apache Cassandra Java Driver 4.19 — Idempotence](https://apache.github.io/cassandra-java-driver/4.19.0/core/idempotence/): guidelines on marking retries and speculative executions idempotent.
- [Spring Data Cassandra API — ReactiveCassandraOperations](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/ReactiveCassandraOperations.html): `batchOps()` and `batchOps(BatchType)`.
- [Spring Data Cassandra API — ReactiveCassandraBatchOperations](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/ReactiveCassandraBatchOperations.html): `insert`, `update`, `delete`, `withQueryOptions`, `execute()`, and single-use instances.
- [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@Table`, and CQL mapping.
- [Spring Data Cassandra — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): publisher subscriptions and reactive execution.
- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, batches from `List<entity>`, `ingestQuery` with `List<List<?>>`, `statementFunction`, and async default.
- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation/release strategies, message grouping, and group stores.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`/`errorChannel`, separating messaging errors from broker transactions.

**Key takeaway:** Cassandra's **`LOGGED BATCH`** protects **mutation completion** via batchlog recovery, yet **does not provide SQL-style transaction isolation across multiple partitions**. **Small single-partition batches** are the natural sweet spot; **multi-partition `UNLOGGED` batches** risk partial application, and **`COUNTER` batches are non-idempotent** under blind retries. For independent writes, prefer **bounded concurrent individual writes** over large multi-partition batches. In Spring Integration Cassandra, distinguish **`List<entity>`**, **`ingestQuery` taking `List<List<?>>`**, and **`statementFunction` returning `BatchStatement`**; all require validation, monitoring, idempotent replay, and explicit acknowledgment boundaries with JMS/Kafka.







