# BatchStatement and Limits by Type, Record Count, and Partition

## Lesson objectives

In Apache Cassandra, a **batch** does not mean “packing more CQL statements together makes the system faster”. A batch is useful when business logic needs to **group related mutations** within the same partition, yet can be very expensive when bundling hundreds or thousands of records across **many partitions**: the coordinator must fan out to many replicas, persist a batchlog for logged batches, and handle timeouts and resource contention.

This lesson belongs to the **Query Execution from Java** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. We examine `BatchStatement` in **Cassandra Java Driver 4.x**, how to pick `LOGGED`, `UNLOGGED`, or `COUNTER`, and limits by **mutation type**, **statement count**, **byte size**, and **partition count**. The concepts connect partition keys/wide-column layout, query-driven table design, consistency levels, multi-DC replication, CQL, compaction, repair, timeout handling, and the Java Driver.

After this lesson, you will be able to:

1. Explain how Cassandra batches differ from ACID transactions and from bulk-ingestion tools.
2. Pick the right **logged**, **unlogged**, or **counter batch** for each workload.
3. Identify **single-partition batches** vs **multi-partition batches** via primary keys, including writes spanning multiple tables.
4. Build a `BatchStatement` from `PreparedStatement`/`BoundStatement`, set consistency levels, and evaluate business idempotence.
5. Enforce application guardrails on **statement count, partition count, estimated bytes, TTL, timestamp, data types, and write permissions** before sending.
6. Separate **ACK**, **UNKNOWN_WRITE**, validation errors, and mismatched readbacks; never auto-retry counters or batches with external side effects.
7. Benchmark batches against **concurrency-bounded individual writes** to pick the better approach using p95/p99, throughput, and errors.

> **Version scope:** Java examples use `com.datastax.oss.driver.api.core...` from Java Driver 4.x and Java 17. Guardrail thresholds, option names, specific CQL syntax, and batch internals can vary across Cassandra 3.x/4.x/5.x and distributions; always check documentation for your exact production release. Data-writing commands are for **lab/staging** only.

## 1. What does a CQL batch actually do?

A `BatchStatement` request bundles **multiple CQL mutations**. The driver sends the batch to a **coordinator**, which resolves tokens/replicas for all involved partitions and executes the write protocol matching the batch type. Replicas still write through commit log and memtable, followed by flush/compaction along Cassandra's standard write path.

~~~mermaid
flowchart LR
    A["Java / BatchStatement"] --> C["Coordinator"]
    C --> P{"How many partitions do mutations touch?"}
    P -->|"Single partition"| R1["Replica set of P"]
    P -->|"Multiple partitions"| R2["Replica set of P1"]
    P -->|"Multiple partitions"| R3["Replica set of P2"]
    C -. "Logged cross-partition batch" .-> B["Batchlog, when needed"]
    B -. "Replay after failure" .-> R2
    B -.-> R3
~~~

### Three batch types

| Type | Typical purpose | Key characteristics |
| --- | --- | --- |
| **`LOGGED`** | Group regular mutations when all-group eventual completion via batchlog is needed across failures, especially across partitions | Incurs **batchlog and coordination cost**; does not provide cluster-wide transaction isolation |
| **`UNLOGGED`** | Group regular mutations when cross-partition batchlog guarantees are unnecessary | Provides **no** cross-partition atomicity; not automatically faster than individual writes |
| **`COUNTER`** | Group increments/decrements on **counter columns** | Has counter-specific semantics; retries are unsafe without control; cannot mix with regular mutations |

**`LOGGED` does not mean “each mutation executes exactly once”**, and `UNLOGGED` does not mean “skip the commit log”. `UNLOGGED` merely skips the **logged-batch batchlog**; every replica still performs standard durable commit-log writes per Cassandra configuration.

A logged batch whose mutations all share the **same partition** typically takes an optimized path without a cross-partition batchlog; exact details depend on version. Never use that optimization as an excuse to cram unbounded rows into a hot partition.

## 2. Atomicity, isolation, and durability: do not confuse with SQL transactions

Many relational databases implement transactions with familiar ACID guarantees. Cassandra batches provide **narrower guarantees aimed at different goals**.

### 2.1. Same partition

When multiple mutations affect the **same partition** within a batch, Cassandra provides **partition-level atomicity/isolation** per its batch semantics: readers should not observe partial updates within that partition on a matching read. This helps when updating related rows or columns in one partition.

However:

- Batches **do not add business preconditions** like “balance >= 0” or “version must equal 7”. Use LWT or explicit concurrency design for compare-and-set.
- Partition-level atomicity does not become a multi-table/multi-partition transaction, nor does it provide cluster-wide serializable isolation.
- With varying TTLs, timestamps, or competing writers, understand **last-write-wins** and tombstones; atomicity does not override timestamp resolution.
- A write succeeding at `LOCAL_QUORUM` only has the ACKs required by that CL, not immediate convergence across every replica and remote DC.

### 2.2. Multiple partitions

A cross-partition logged batch uses a **durable batchlog/replay** mechanism so mutations eventually complete after supported coordinator failures. However, **there is no cross-partition snapshot isolation**:

~~~text
P1: mutation already visible at time T1
P2: mutation not yet visible at time T1

A reader querying P1 and P2 separately at T1
may observe a temporarily inconsistent state.
~~~

Therefore, **never** treat a logged batch like a two-account bank transfer if readers require atomic, conditional visibility across both accounts. Instead, design a ledger/operation ID, state machine, scoped LWT, or explicit transaction coordinator.

### 2.3. A timeout does not answer “was it written?”

A `WriteTimeout` from `session.execute(batch)` **does not prove** the batch rolled back. Some mutations/replicas may have applied, and a batchlog may still replay later. The safe state to record is **UNKNOWN_WRITE** until verified.

| Result | Interpretation | Action |
| --- | --- | --- |
| `execute` returns normally | Coordinator confirmed per requested **CL and batch semantics** | Record ACK with batch ID, CL, and timestamp |
| `WriteTimeout` | Insufficient ACKs within deadline; actual state uncertain | Record `UNKNOWN`, reconcile by PK/operation ID |
| `Unavailable` | Insufficient live replicas for CL at execution time | Check RF/DC/nodes; do not assume zero writes if state is unclear |
| `InvalidQuery` / validation failure | Invalid CQL, types, or batch kind | Fix inputs; never retry blindly |
| Readback misses a marker | Query completed yet marker is absent at read CL | Check TTL, timestamps, replicas/repair, and manifest |

**Core point:** the batchlog supports logged-batch atomicity/durability; it is **not** a business transaction log replacing an event log/outbox, nor a post-failure rollback mechanism.

## 3. Identifying partitions: the critical factor in batch design

In Cassandra, the partition key computes the token and selects the **replica set**. Even when Java sends a single `BatchStatement`, the coordinator still processes every partition touched.

Consider an events table keyed by customer and day:

~~~sql
PRIMARY KEY ((customer_id, event_day), event_ts, event_id)
~~~

- Two rows with the **same `customer_id` and `event_day`** live in **one partition of that table**, even with different `event_ts` or `event_id`.
- Two rows with **different days** or **different customers** live in **two different partitions**.
- If two tables share the same `customer_id` value yet differ in primary-key schema, **never** assume they form one physical partition sharing atomicity.
- Even if distinct partitions happen to have overlapping tokens/replica sets, they remain **distinct partitions**; “same node” does not replace “same partition”.

### Same application key across different tables is still distinct

Example:

~~~text
orders_by_customer_day:
    partition = (customer_id, day)

order_details_by_id:
    partition = (customer_id, order_id)

Same customer_id, yet two different partition keys.
A batch writing both tables does NOT get ACID isolation/rollback
across the two business read paths.
~~~

When denormalizing across multiple query-driven tables, use **idempotency, operation IDs, events/outboxes, and reconciliation** to handle one table becoming visible before another.

### Where do multi-partition batches spend resources?

| Aspect | Single-partition batch | Multi-partition batch |
| --- | --- | --- |
| Replica sets | One replica set for the target partition | Potentially many distinct replica sets |
| Coordinator | Focused mutation delivery | Fan-out to many endpoints, waiting on many ACKs |
| Logged batchlog | Often optimized for single partition | Significant batchlog/replay overhead |
| Latency | Depends on partition/mutation size and CL | Driven by slowest endpoint/replica and fan-out |
| Availability | Depends on that partition's replicas and CL | More partitions widen the failure blast radius |
| Workload risk | Hot partition, oversized batch | Batchlog bottleneck, network, GC, timeouts |

**Never choose batches solely to cut client round trips** at the expense of coordinator fan-out and heavy batchlogs. For multi-partition bulk ingestion, **backpressure-bounded async `INSERT`s** are usually the better baseline to benchmark.

## 4. CQL lab: preparing event and counter tables

### 4.1. Lab prerequisites

Assume a **three-node** lab cluster in DC `datacenter1` using `NetworkTopologyStrategy` with RF=3. Otherwise, adjust RF and CL to match your topology; never try `LOCAL_QUORUM` with RF=3 on a single-node lab.

~~~bash
nodetool status
~~~

In `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` describes the responding node, not the entire cluster. Run examples against fresh lab tables using fresh IDs/ranges each pass so prior data does not skew experiments.

### 4.2. Regular table partitioned by customer and day

~~~sql
CREATE KEYSPACE IF NOT EXISTS java_batch_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS java_batch_lab.events_by_customer_day (
    customer_id uuid,
    event_day date,
    event_ts timestamp,
    event_id uuid,
    status text,
    amount_minor bigint,
    detail text,
    PRIMARY KEY ((customer_id, event_day), event_ts, event_id)
) WITH CLUSTERING ORDER BY (event_ts DESC, event_id DESC);
~~~

In this table:

- `(customer_id, event_day)` is the **composite partition key**.
- `event_ts` and `event_id` are clustering keys for querying recent events per customer/day.
- `status`, `amount_minor`, and `detail` are regular columns.
- Partition keys cannot be modified via `UPDATE`; changing a key means writing a new row/partition and handling the old row per business rules.

`IF NOT EXISTS` does not update an already existing schema/keyspace. Verify replication before applying CL:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'java_batch_lab';
~~~

### 4.3. Completely separate counter table

~~~sql
CREATE TABLE IF NOT EXISTS java_batch_lab.counts_by_customer_day (
    customer_id uuid,
    event_day date,
    metric text,
    total counter,
    PRIMARY KEY ((customer_id, event_day), metric)
);
~~~

Counters follow distinct semantics and cannot be mixed with regular non-primary-key columns in the same table under Cassandra's counter model. **Never use counters for money or sequence numbers requiring exactly-once accuracy**; retrying a timed-out increment can double-count.

## 5. Single-partition LOGGED batch: when to consider it

Suppose business logic records two events for the **same customer/day** in the lab table and wants those mutations processed with batch semantics.

In `cqlsh`, `BEGIN BATCH` defaults to a **logged batch**; add `UNLOGGED` or `COUNTER` only when that type is intended:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
BEGIN BATCH
  INSERT INTO java_batch_lab.events_by_customer_day
      (customer_id, event_day, event_ts, event_id,
       status, amount_minor, detail)
  VALUES (
      11111111-1111-4111-8111-111111111111,
      '2026-11-21', '2026-11-21T09:00:00Z',
      22222222-2222-4222-8222-222222222222,
      'CREATED', 20500, 'created')
  ;
  INSERT INTO java_batch_lab.events_by_customer_day
      (customer_id, event_day, event_ts, event_id,
       status, amount_minor, detail)
  VALUES (
      11111111-1111-4111-8111-111111111111,
      '2026-11-21', '2026-11-21T09:01:00Z',
      33333333-3333-4333-8333-333333333333,
      'PAID', 20500, 'paid')
  ;
APPLY BATCH;
~~~

Both statements share partition key `(customer_id, event_day)`. They differ in **clustering key**, creating two rows inside the same partition.

Verify by partition key:

~~~sql
SELECT event_ts, event_id, status, amount_minor
FROM java_batch_lab.events_by_customer_day
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

**A batch does not guarantee sequential execution order like a Java program.** Both INSERTs here target **two distinct primary keys**; each row needs its own business identifier and timestamp. If two mutations touch the **same cell/key** with equal timestamps or competing writers, textual order inside the batch **must not be relied upon to decide the winning value**.

### When is a single mutation simpler?

If an app merely updates **multiple columns of the same row**, one `INSERT` or `UPDATE` listing all columns in a single mutation suffices. Never wrap multiple `UPDATE`s on the **same row** in a batch when a single CQL statement does the job.

Example:

~~~sql
UPDATE java_batch_lab.events_by_customer_day
SET status = 'PAID',
    amount_minor = 20500,
    detail = 'confirmed'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND event_ts = '2026-11-21T09:00:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

This is a single mutation on one row—no batch needed just to combine three assignments.

## 6. UNLOGGED and multi-partition logged batches: commonly misunderstood risks

### 6.1. UNLOGGED for same-partition mutations

~~~sql
BEGIN UNLOGGED BATCH
  UPDATE java_batch_lab.events_by_customer_day
  SET status = 'VERIFIED'
  WHERE customer_id = 11111111-1111-4111-8111-111111111111
    AND event_day = '2026-11-21'
    AND event_ts = '2026-11-21T09:00:00Z'
    AND event_id = 22222222-2222-4222-8222-222222222222;
  UPDATE java_batch_lab.events_by_customer_day
  SET status = 'VERIFIED'
  WHERE customer_id = 11111111-1111-4111-8111-111111111111
    AND event_day = '2026-11-21'
    AND event_ts = '2026-11-21T09:01:00Z'
    AND event_id = 33333333-3333-4333-8333-333333333333;
APPLY BATCH;
~~~

Same-partition batches can still leverage Cassandra's single-partition update guarantees without a cross-partition batchlog. Even so, `UNLOGGED` is **not** a license for giant batches or relying on cross-partition atomicity.

### 6.2. Anti-pattern: bundling many customers/days for “fast bulk inserts”

~~~text
An ETL job collects 5,000 arbitrary INSERTs:
  P1 = customer A / 2026-11-21
  P2 = customer B / 2026-11-21
  P3 = customer C / 2026-11-20
  ...
  P5000 = another customer / another day

Then sends one BEGIN BATCH ... APPLY BATCH (logged by default).
~~~

Problems:

- The coordinator fans out across many replicas/token ranges and maintains a huge batchlog.
- Any slow replica or token range stalls the whole batch's latency.
- Retrying a giant batch amplifies load and leaves timeout outcomes murky.
- Fewer CQL requests **does not prove higher overall throughput**.
- Batching never changes partition keys or turns 5,000 mutations into one cheap storage write.

Sending the same 5,000 mutations as `UNLOGGED` **does not solve it either**: fan-out and oversized payloads remain, while cross-partition batchlog protection is lost. Prefer **individual writes or small per-partition batches** with rate limiting, bounded in-flight counts, and metrics.

### 6.3. When is a cross-partition logged batch justified?

When there is an explicit need for **eventual completion of a small group of related mutations** while accepting **no isolation between partitions**. For example, certain workflows group denormalized copies sharing an operation ID so the batchlog helps recover from coordinator crashes. Still, to let applications see consistent state and repair drift after failures, you also need **outboxes, operation state, or reconciliation**.

**Never treat logged batches as full replacements for relational transactions**, especially under write contention, multi-key business conditions, or external systems.

## 7. COUNTER BATCH is a separate category

Cassandra counters perform **increments/decrements**, not normal numeric overwrites. They carry distinct retry and consistency semantics, so Cassandra isolates **COUNTER batches** from regular mutations.

~~~sql
BEGIN COUNTER BATCH
  UPDATE java_batch_lab.counts_by_customer_day
  SET total = total + 1
  WHERE customer_id = 11111111-1111-4111-8111-111111111111
    AND event_day = '2026-11-21'
    AND metric = 'created';
  UPDATE java_batch_lab.counts_by_customer_day
  SET total = total + 1
  WHERE customer_id = 11111111-1111-4111-8111-111111111111
    AND event_day = '2026-11-21'
    AND metric = 'paid';
APPLY BATCH;
~~~

Notes:

- Counter mutations **cannot be mixed with regular INSERT/UPDATE statements** in the same batch.
- Counters use `UPDATE ... SET counter_col = counter_col + delta`; never `INSERT` absolute counter values.
- On timeout, increments may already have applied. **Retrying can double-count** if the same increment runs again.
- Never mark counter batches `idempotent=true` just to enable retries or speculative execution.
- When exact business counts or replayability matter, consider **event IDs + a fact/ledger table + aggregation**; counters fit cases where eventual semantics and small drift are acceptable.

Reading results:

~~~sql
SELECT metric, total
FROM java_batch_lab.counts_by_customer_day
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21';
~~~

Re-running the same `COUNTER BATCH` adds again; that is additive counter behavior, not a driver bug. Use fresh lab keys for each experiment expecting fixed counts.

## 8. Java Driver 4.x: building BatchStatement from BoundStatement

### 8.1. Create `CqlSession` once

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class CassandraLabSession {
    public static CqlSession open() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.10.0.11", 9042))
            .addContactPoint(new InetSocketAddress("10.10.0.12", 9042))
            .withLocalDatacenter("datacenter1")
            .build();
    }
}
~~~

These IPs are **lab examples** only. Production requires TLS, authentication/authorization, secrets management, timeouts, local-DC load balancing, backpressure, and metrics. **Reuse `CqlSession`**; opening a session per batch causes handshake overhead, connection churn, and skewed benchmarks.

### 8.2. Prepare query shapes ahead of time

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

PreparedStatement insertEvent = session.prepare(
    "INSERT INTO java_batch_lab.events_by_customer_day (" +
    "customer_id, event_day, event_ts, event_id, " +
    "status, amount_minor, detail) " +
    "VALUES (?, ?, ?, ?, ?, ?, ?)");
~~~

Prepare the `PreparedStatement` **once per query shape** and reuse it across `BoundStatement`s. Never concatenate user input into CQL or re-prepare the same query per row.

### 8.3. Example single-partition LOGGED batch

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class TwoEventsBatch {
    private final CqlSession session;
    private final PreparedStatement insert;

    public TwoEventsBatch(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO java_batch_lab.events_by_customer_day " +
            "(customer_id, event_day, event_ts, event_id, " +
            "status, amount_minor, detail) VALUES (?, ?, ?, ?, ?, ?, ?)");
    }

    public void writeTwo(UUID customerId, LocalDate day) {
        BoundStatement created = insert.bind(
            customerId, day, Instant.parse("2026-11-21T09:00:00Z"),
            UUID.fromString("44444444-4444-4444-8444-444444444444"),
            "CREATED", 20500L, "created");

        BoundStatement paid = insert.bind(
            customerId, day, Instant.parse("2026-11-21T09:01:00Z"),
            UUID.fromString("55555555-5555-4555-8555-555555555555"),
            "PAID", 20500L, "paid");

        BatchStatement batch = BatchStatement.builder(DefaultBatchType.LOGGED)
            .addStatement(created)
            .addStatement(paid)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            // Idempotency for timestamp/TTL/retry not yet proven:
            .setIdempotence(false)
            .build();

        session.execute(batch);
        // No exception means the coordinator acknowledged per CL.
    }
}
~~~

**Details to notice:**

- Both `BoundStatement`s use the **same `customerId` and `day`**, targeting one partition of the **same table**.
- `BatchStatement.builder(DefaultBatchType.LOGGED)` creates a logged batch; `UNLOGGED` or `COUNTER` are separate types—never switch casually without verifying requirements.
- `LOCAL_QUORUM` with RF3 in one DC waits for local quorum; it does not confirm every remote-DC replica.
- `session.execute(batch)` is synchronous and blocks the calling thread until completion or timeout.
- Returning without error **does not return SELECT rows**; for regular batches, `ResultSet` does not contain an updated-row count.
- Both fixed `UUID`s here are for lab use. In production, IDs should derive from **stable operation/event IDs**, never generated fresh on retry.
- `setIdempotence(false)` is a conservative choice. Only flip to `true` per driver policy once writer ownership, timestamps/TTLs, and replay safety are proven.

### 8.4. Switching batch types in Java

~~~java
BatchStatement unlogged = BatchStatement.builder(
        DefaultBatchType.UNLOGGED)
    .addStatement(created)
    .addStatement(paid)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotence(false)
    .build();
~~~

This illustrates code syntax, not advice to convert every logged batch to unlogged. A counter batch must hold **counter statements only**, for example:

~~~java
PreparedStatement increment = session.prepare(
    "UPDATE java_batch_lab.counts_by_customer_day " +
    "SET total = total + 1 " +
    "WHERE customer_id = ? AND event_day = ? AND metric = ?");

BatchStatement counters = BatchStatement.builder(DefaultBatchType.COUNTER)
    .addStatement(increment.bind(customerId, day, "created"))
    .addStatement(increment.bind(customerId, day, "paid"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotence(false)
    .build();

session.execute(counters);
~~~

Never add a regular table's `insert.bind(...)` into `counters`. When a counter batch times out, never auto-retry as if the increments did not happen.

## 9. Enforcing statement, byte, and partition limits in Java

### 9.1. Why enforce limits in the application?

Cassandra warns or rejects oversized batches via thresholds such as `batch_size_warn_threshold_in_kb` and `batch_size_fail_threshold_in_kb` (exact names/defaults vary by version/config), and warns on unlogged batches spanning many partitions. **Never wait for server warnings before bounding inputs on the client.**

Suppose an API receives:

~~~text
POST /customers/{customerId}/events/batch
[
  { "event_id": "...", "day": "2026-11-21", "detail": "..." },
  ...
]
~~~

If clients can submit 50,000 rows, one batch stresses memory, network, disk, coordinator, replicas, and induces timeouts for unrelated workloads. Java/API guardrails should enforce **three independent caps**:

1. **Max mutations/statements**, e.g. **25** in the lab.
2. **Max estimated bytes**, e.g. **64 KiB** in the lab (neither a universal default nor a general recommendation).
3. **Max distinct partitions**, e.g. **strictly one partition** for this logged-batch API.

Additionally: forbid mixing counters and regular mutations, cap field lengths, forbid null primary keys, forbid arbitrary CQL from users, and keep CL/idempotency policies fixed per business rules.

### 9.2. Enforce a single partition before building `BatchStatement`

The code below is an **application guardrail pattern**, assuming authenticated/authorized inputs and reusing `events_by_customer_day`. It caps **25 statements** and **64 KiB estimated**, without claiming to measure exact binary CQL wire size.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.BatchStatementBuilder;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class BoundedBatchWriter {
    private static final int MAX_MUTATIONS = 25;
    private static final int MAX_ESTIMATED_BYTES = 64 * 1024;
    private static final int MAX_DETAIL_BYTES = 8 * 1024;

    public record InputEvent(
        UUID customerId,
        LocalDate eventDay,
        Instant eventTs,
        UUID eventId,
        String status,
        long amountMinor,
        String detail) {}

    private final CqlSession session;
    private final PreparedStatement insert;

    public BoundedBatchWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO java_batch_lab.events_by_customer_day " +
            "(customer_id, event_day, event_ts, event_id, " +
            "status, amount_minor, detail) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)");
    }

    public void writeOnePartition(List<InputEvent> input) {
        if (input == null || input.isEmpty()
                || input.size() > MAX_MUTATIONS) {
            throw new IllegalArgumentException(
                "Batch requires 1.." + MAX_MUTATIONS + " mutations");
        }

        InputEvent first = Objects.requireNonNull(input.get(0));
        UUID partitionCustomer = Objects.requireNonNull(first.customerId());
        LocalDate partitionDay = Objects.requireNonNull(first.eventDay());
        long estimatedBytes = 0;

        BatchStatementBuilder builder =
            BatchStatement.builder(DefaultBatchType.LOGGED);

        for (InputEvent event : input) {
            Objects.requireNonNull(event);
            if (!partitionCustomer.equals(event.customerId())
                    || !partitionDay.equals(event.eventDay())) {
                throw new IllegalArgumentException(
                    "This batch API accepts only a single partition");
            }
            Objects.requireNonNull(event.eventTs());
            Objects.requireNonNull(event.eventId());
            Objects.requireNonNull(event.status());
            Objects.requireNonNull(event.detail());

            int detailBytes = event.detail()
                .getBytes(StandardCharsets.UTF_8).length;
            if (detailBytes > MAX_DETAIL_BYTES) {
                throw new IllegalArgumentException("detail too large");
            }

            int statusBytes = event.status()
                .getBytes(StandardCharsets.UTF_8).length;
            // ESTIMATED budget: overhead/keys/strings.
            // Not exact driver wire serializer bytes.
            estimatedBytes += 128L + detailBytes + statusBytes;
            if (estimatedBytes > MAX_ESTIMATED_BYTES) {
                throw new IllegalArgumentException(
                    "Exceeded batch size budget");
            }

            builder.addStatement(insert.bind(
                event.customerId(), event.eventDay(),
                event.eventTs(), event.eventId(), event.status(),
                event.amountMinor(), event.detail()));
        }

        BatchStatement batch = builder
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(false)
            .build();
        session.execute(batch);
    }
}
~~~

**What this checks:** statement count, same-table/same-partition across both key fields, approximate byte budget, and data types. **What it does not replace:** schema/query ownership checks, exact cell counts, protocol framing overhead, timestamps/TTLs, RF/CL alignment, timeouts, auditing, and retry policies.

Thus **64 KiB is an illustrative app budget**; cluster config may warn at a lower threshold. Benchmark and set **stricter caps** for wide schemas/rows. In production, also check batch state tracking, duplicate event IDs, and tenant authorization for `customerId`.

### 9.3. What if multiple partitions must be supported?

One pattern is **grouping by partition key**, then executing each group as a small unit:

~~~text
input events
    -> validate + deduplicate source event_id
    -> group by (customer_id, event_day)
    -> cap statements and bytes per group
    -> execute with concurrency/rate limits
    -> record outcome per group
    -> reconcile UNKNOWN_WRITE by primary key
~~~

Yet **grouping and firing thousands of concurrent batches** still saturates the cluster. Cap **in-flight requests, QPS per partition, and total buffered memory**. For a single-mutation group, send a standalone `BoundStatement`; never wrap one mutation in a single-item batch purely for API uniformity.

An oversized group can be **split into multiple batches** only if business rules do not require all-group atomicity. If atomicity across more than 25 mutations in one partition is required, **never split silently and claim the guarantee still holds**; redesign the unit of work or negotiate explicit limits.

## 10. Idempotency, timestamps, TTL, and write contention

### 10.1. Idempotence is not merely “using the same INSERT”

A mutation with the **same primary key and values** can be idempotent under certain conditions. Check also:

- **Client generates a fresh UUID on retry** → every retry creates a **different row**, not idempotent.
- **Relative TTL shifts by send time** → expiration moves forward on retry.
- **Different write timestamps** → a late retry can win over a concurrent write and overwrite newer data.
- **Counter `+1`** → retries double-increment, not idempotent.
- **LWT or external side effects** → require dedicated retry contracts; `[applied]` and state can differ across attempts.
- **Multi-table batch** → even if some mutations replay safely, a single non-idempotent mutation makes the **entire batch non-idempotent** for retries.

**Never set `setIdempotence(true)` to force driver retries** without proving every mutation in the batch is safe to replay. Even when idempotent, enforce a **retry budget**, exponential backoff with jitter, timeout policy, and amplification monitoring; retry storms push slow clusters into cascading outages.

### 10.2. Timestamps and mutation ordering

Cassandra reconciles writes via write timestamps; statement order inside a batch **is not a serializable barrier** across competing writers. When expected state matters, use operation/version records, state columns, scoped LWTs, or an application state machine.

Import pipelines sometimes supply explicit `USING TIMESTAMP` values, noting that **CQL `USING TIMESTAMP` uses microseconds**, unlike CQL `timestamp` columns stored in millisecond epoch. Synthetic or overly stale timestamps can lose to newer tombstones. Never backdate timestamps artificially “to force batch ordering”.

### 10.3. TTL inside batches

TTLs can be attached to CQL mutations where syntax/version permits; individual rows/cells can expire at different times. A batch **does not turn mutations with mixed TTLs into an eternal atomic expiration unit**. In tests, record TTL and write time so legitimate expiration is not mistaken for batch data loss.

## 11. Conditional batches and LWT: dedicated limits

Cassandra supports **conditional mutations** via `IF` clauses (LWT/Paxos). Some conditional batch forms are supported, yet come with **strict partition and statement-type restrictions** by version; you cannot arbitrarily turn a multi-partition batch into a cluster-wide CAS transaction.

Single-statement LWT example before considering conditional batches:

~~~sql
INSERT INTO java_batch_lab.events_by_customer_day
    (customer_id, event_day, event_ts, event_id,
     status, amount_minor, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:10:00Z',
    66666666-6666-4666-8666-666666666666,
    'CREATED', 20500, 'created-once')
IF NOT EXISTS;
~~~

LWT responses normally include `[applied]` to show whether the condition passed. Re-running on the same PK and getting `[applied]=false` can be **correct behavior**, not a Cassandra failure.

### Why avoid ad-hoc LWT batches?

- Conditions apply only within Cassandra's supported Paxos/conditional-batch scope; multi-partition conditional batches are generally invalid or lack expected guarantees.
- LWT incurs extra Paxos round trips and higher latency than regular writes.
- Counters cannot mix with LWT/regular mutations in the same batch.
- Retrying LWTs after timeouts requires handling **unknown outcomes** and preserving operation IDs; never infer from a timeout that the condition never applied.

When business rules require transitioning **`CREATED → PAID` only on matching version**, use an LWT on the proper partition/row rather than expecting an unconditional logged batch to stop lost updates.

## 12. Bulk ingestion: comparing batches vs async individual writes

### 12.1. Two options to benchmark

**Option A — Small per-partition batches**

~~~text
source events
 -> group by partition
 -> batch <= app limits
 -> coordinator / replica sets
 -> measure p95/p99, batch size, errors
~~~

**Option B — Individual async writes**

~~~text
source events
 -> PreparedStatement + BoundStatement
 -> executeAsync per mutation
 -> bounded in-flight + rate limiter
 -> measure p95/p99, throughput, errors
~~~

Driver snippet:

~~~java
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;

BoundStatement one = insert.bind(
    customerId, day, eventTs, eventId,
    "CREATED", 20500L, "new-event");

CompletionStage<AsyncResultSet> completion =
    session.executeAsync(one);

// Single illustrative call; real bulk systems must bound
// in-flight requests and handle errors per event.
~~~

Never treat this snippet as an **unbounded load generator**; bulk ingestion needs queues/semaphores/rate limiters and checkpoints. If the cluster already has a compaction backlog or pending tasks, cranking up concurrency drives latency and timeouts higher.

### 12.2. Why can many async writes beat one large batch?

The driver routes each individual mutation via partition key / token awareness when metadata is available, spreading coordinator load and applying per-request backpressure. A huge logged batch bundling many partitions into one coordinator loses that spread, swells the batchlog, and stretches tail latency.

**However**, individual async writes also lack group atomicity and can flood the cluster if unbounded. Choose from **business semantics first**, then benchmark.

### 12.3. A CQL batch does not replace bulk `SELECT`s

`BEGIN BATCH ... APPLY BATCH` is strictly for **INSERT/UPDATE/DELETE** mutations, **never for bundling `SELECT` queries**. If an API suffers N+1 reads, fix the query-driven table design, target the right partition/projection, and cut fan-out—never try stuffing `SELECT` into `BatchStatement`.

## 13. Benchmarking and observing batch cost

### 13.1. Variables to hold constant

When comparing `LOGGED`, `UNLOGGED`, and independent writes, hold these constant:

| Variable | Why hold constant |
| --- | --- |
| Cassandra version, RF/DC, healthy nodes | Affects replica placement and CL |
| Write/read CL | Affects required ACKs/responses and latency |
| Total mutations | Prevents a batch from looking “fast” by doing less work |
| Partition popularity | Hot partitions behave very differently from distributed keys |
| Payload bytes and TTL | Changes network, storage, and compaction work |
| Concurrency and target QPS | Shifts overload, pending tasks, and retries |
| Retry / speculative settings | Can amplify total requests |
| Warm-up, background compaction/repair | Can skew measurements |

**Compare only configurations delivering equal business guarantees.** Never declare `UNLOGGED` the “winner” over `LOGGED` if business logic requires `LOGGED` completion semantics. Likewise, never compare 1 multi-partition batch against 100 individual writes while ignoring differences in idempotency or partial visibility.

### 13.2. Metrics to collect

~~~text
batch_id, batch_type, first_partition_key_hash,
statement_count, distinct_partition_count, estimated_bytes,
CL, coordinator, elapsed_ms, outcome, retry_count
~~~

In production telemetry, avoid logging **raw partition keys, PII, or payloads**; use hashes or internal IDs. Collect at minimum:

- **End-to-end batch `p50/p95/p99`**, split by batch type and statement count.
- **Mutations/sec** alongside **CQL requests/sec**, since one batch is one request carrying multiple mutations.
- **Error rates** by `WriteTimeout`/`Unavailable`/`WriteFailure`/`InvalidQuery` and `UNKNOWN`.
- **Batch warnings/guardrail rejections**, actual/estimated batch byte sizes, and partition counts.
- CPU/GC, heap, network, disk I/O, commitlog/memtable, pending tasks, and compaction.
- Batchlog/replay activity, hints, and read-repair/anti-entropy repair if applicable.
- Coordinator/replica distribution per node and DC, not just cluster-wide averages.

Basic operational tools:

~~~bash
nodetool status
nodetool tpstats
nodetool compactionstats
nodetool tablestats java_batch_lab.events_by_customer_day
nodetool netstats
~~~

Depending on version, add JMX/metrics for batchlog and dropped messages, without **assuming identical metric names or outputs** across all Cassandra releases. `nodetool status` reports health/tokens/load, **not how many partitions a batch touched**; capture that from the application or selective tracing.

### 13.3. Purely hypothetical numbers for reading reports

| Trial | Mutations | Partitions | p95 | Errors/10k | Sound takeaway |
| --- | ---: | ---: | ---: | ---: | --- |
| A: LOGGED 2 events same partition | 2 | 1 | 9 ms | 0 | Reasonable if group semantics are needed |
| B: LOGGED 200 events across partitions | 200 | 200 | 180 ms | 40 | Signs of fan-out and oversized batch; inspect metrics |
| C: 200 async INSERTs, bounded | 200 | 200 | 14 ms/INSERT | 3 | Must measure **full-group completion time** and correctness before comparing A/B |

These numbers are **illustrative exercises for reading reports**, not real benchmark measurements. The p95 of **one INSERT** cannot be compared directly to the p95 of **completing a group of 200 INSERTs**; align units and business guarantees first.

## 14. Diagnostic runbook and production guardrails

### 14.1. On “Batch too large” errors or warnings

1. Record **batch type, statement count, partition count, and estimated bytes** of the offending request.
2. Check effective batch size thresholds/guardrails for your exact Cassandra version.
3. Correlate coordinator CPU, memory, pending tasks, batchlog, and network metrics.
4. Shrink batches or switch to individual writes **if business semantics permit**.
5. Never raise `batch_size_fail_threshold_in_kb` blindly to let MiB-sized batches pass without evaluating RAM/GC and I/O impact.

### 14.2. On logged batch timeout

- Record `UNKNOWN_WRITE`, batch ID, operation IDs, CL, coordinator, timestamp, and PK list.
- Never assume a partial missing readback means the whole batch rolled back.
- Evaluate idempotency of **each mutation**, timestamps/TTLs, concurrent writers, and batchlog replay.
- Reconcile against a manifest classifying `FOUND_MATCH`, `MISSING_AT_CL`, `MISMATCH`, and `READ_ERROR`. Never use a full-table `COUNT(*)` to decide.
- If recovery is needed, follow workflow/outbox/repair plans; **repair never recreates an event that was never written to any replica**.

### 14.3. On counter batch timeout

- **Never auto-retry** `+1` increments.
- If counts are business-critical, reconcile from an **event ledger/source IDs** and repair counters safely rather than assuming a readback reflects every prior increment attempt.

### 14.4. When batches drive up p99

| Symptom | Hypothesis | Controlled mitigation |
| --- | --- | --- |
| p99 scales with partition count | Coordinator fan-out / batchlog | Restrict to 1 partition or test bounded async writes |
| CPU/GC climbs with bytes | Oversized payloads / serialization | Trim projection/row size, enforce byte caps |
| Timeouts on specific nodes | Hot replica, compaction, network | Inspect token/partition skew, pending tasks, disk |
| Retries surge after timeouts | Retry storm or speculative duplication | Cut retries/concurrency, audit idempotency |
| Multi-DC latency spikes | Client picks remote-DC coordinator or WAN lag | Verify local DC/CL and network links |
| Data mismatch after re-runs | Fresh UUIDs, shifted TTL/timestamp, concurrent writers | Stable operation IDs, manifests, and ownership |

### 14.5. Pre-deployment checklist

- [ ] Clear batch rationale: partition atomicity/group completion, not blind throughput hopes.
- [ ] Correct `LOGGED`/`UNLOGGED`/`COUNTER` choice; never mix counters and regular mutations.
- [ ] Verified **actual partition count**; never mistake same customer across different tables/days for the same partition.
- [ ] API caps on statement count, payload bytes, distinct partitions, and field sizes.
- [ ] Sufficient RF/CL in local DC; never downgrade CL to mask batch issues.
- [ ] `PreparedStatement` reused, `CqlSession` long-lived, avoiding N+1 and filtering queries.
- [ ] Timeout/retry budgets defined with **per-mutation** idempotence evaluated, not just batch-level.
- [ ] Independent operation IDs/manifests separating `UNKNOWN_WRITE` and `READ_ERROR`.
- [ ] Benchmarked against bounded-concurrency individual writes under matching workload and semantics.
- [ ] Monitoring p95/p99, batch-size warnings, errors, pending tasks, and coordinator/replica load.
- [ ] Canary, rollback/forward-fix, and data-repair plans that never rely on deleting SSTables.

## 15. Questions and hands-on exercises

**Exercise 1 — Identifying partitions.** A table has `PRIMARY KEY ((customer_id, event_day), event_ts, event_id)`. Do two events for the same customer on different `event_day`s belong to one or two partitions? What if they share customer and day but differ in `event_id`?

**Exercise 2 — LOGGED or UNLOGGED?** Two mutations in the same partition must become visible together as a unit; 200 mutations across many partitions are bundled solely to reduce client requests. Propose separate approaches for both cases and state the trade-offs.

**Exercise 3 — Atomicity vs isolation.** Why must a logged batch writing P1 and P2 not be used as a two-account money transfer if a reader can see P1 before P2? Propose a ledger/operation-state design instead.

**Exercise 4 — Counters.** A `COUNTER BATCH` increments two metrics, the client times out, and the app retries. How can final values drift? Why does setting `idempotence=true` not provide exactly-once semantics?

**Exercise 5 — Byte limits.** There are 20 mutations, each with a 10 KiB UTF-8 `detail`, totaling roughly 200 KiB before protocol overhead. With a 64 KiB application budget, how should the request be handled? Why does `LIMIT` not fix write batches?

**Exercise 6 — Java code.** Write `BatchStatement.builder(DefaultBatchType.LOGGED)` from two `BoundStatement`s sharing `customerId` and `eventDay` at `LOCAL_QUORUM`. Explain why `PreparedStatement` is preferred over string concatenation.

**Exercise 7 — Retries and TTL.** A mutation with the same PK is retried after 10 minutes with a 1-hour TTL computed at send time. Why can the expiration shift? Design a timestamp/TTL/ownership contract for safe replay.

**Exercise 8 — Multi-table.** An app writes a list table keyed by `(customer_id, day)` and a detail table keyed by `(customer_id, order_id)` inside one logged batch. Why should you not call this an isolated transaction across both tables? What must you check on timeout?

**Exercise 9 — Bulk ingestion.** For 10,000 events across 8,000 partitions, compare one giant logged batch, 400 small batches, and 10,000 bounded-in-flight async writes. Which metrics must you gather to compare throughput and failure semantics accurately?

**Exercise 10 — LWT.** An `INSERT ... IF NOT EXISTS` returns `[applied]=true`, and a subsequent run on the same PK returns `false`. Is that a bug? Why can multi-partition conditional batches not be assumed to work as CAS transactions?

**Exercise 11 — Diagnosis.** Cassandra logs oversized batch warnings while pending tasks climb. Outline steps to take before adjusting guardrails, and explain why raising thresholds can make things worse.

**Exercise 12 — Reconciliation.** A three-mutation batch times out. Readback reports two `FOUND_MATCH` and one `READ_ERROR`. Can you report one mutation as lost? What must the manifest store to verify accurately?

## Remember

**`BatchStatement` bundles multiple CQL mutations into one request, yet it is neither a fast bulk-ingestion tool by default nor a multi-partition ACID transaction.** Pick the right **`LOGGED`**, **`UNLOGGED`**, or **`COUNTER`** type; distinguish scoped partition atomicity from cluster-wide isolation; identify partitions by **full partition key and table**. In Java, use `PreparedStatement`/`BoundStatement`, enforce caps on **statement count, payload bytes, distinct partitions, and in-flight requests**, uphold RF/CL requirements, and treat timeouts as **`UNKNOWN_WRITE`** until reconciled. For multi-partition workloads needing no group semantics, benchmark **backpressure-bounded async writes** instead of giant batches. Success is proven by **data correctness, error rates, p95/p99 latency, and resource health**, not by fewer CQL requests.
