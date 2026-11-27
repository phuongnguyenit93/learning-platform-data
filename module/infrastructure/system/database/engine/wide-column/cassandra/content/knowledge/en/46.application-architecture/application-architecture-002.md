# Separating the Business Write Path from Query-Driven Read Tables

## 1. Architectural Problem to Solve

In an order-processing system, operations such as **placing an order**, **confirming payment**, or **canceling an order** must adhere to business rules: no double payment, no transitioning from canceled to delivered, and maintaining change history. Meanwhile, customer-facing screens require entirely different queries:

- Fetch order details by `order_id`.
- Display a customer's 20 most recent orders, with pagination.
- View pending orders for a store.

If all operations are forced into a single table model, every new query pattern may require trading off business correctness against read performance. With **Apache Cassandra**, this issue is even more pronounced: a table is typically designed around **the query it will run**, based on its partition key and clustering columns, rather than expecting ad-hoc queries via joins or cluster-wide filtering.

The solution is to separate:

| Component | Responsibility | Primary Requirement |
| --- | --- | --- |
| **Business write path (command/write path)** | Validate commands, enforce rules, mutate authoritative state | Correctness, deduplication, preserving business invariants |
| **Source of truth** | Store the state recognized by the system | Verifiable, recoverable, and capable of replaying changes |
| **Synchronization path (event/projection pipeline)** | Transform business changes into one or more read projections | Durable, retryable, observable lag |
| **Cassandra read tables (read models/projections)** | Serve a known set of queries with appropriate partition keys | Fast reads, direct key-based lookups, horizontal scaling |

This applies **CQRS (Command Query Responsibility Segregation)** thinking at the data architecture level: the write side decides *what is valid*; the read side organizes *how data should be displayed*. Event sourcing is not mandatory, nor is splitting into two microservices. The core principle is separating responsibilities and consistency contracts.

## 2. Reference Architecture Flow

The example below uses a transactional database as the source of truth and Cassandra as the read-table store. This is a suitable choice when business transactions are needed at the source while Cassandra is needed to serve multiple high-traffic read patterns.

~~~mermaid
flowchart LR
    U["User application"]
    C["Command API"]
    DB[("Source of truth: orders")]
    OB[("Transactional outbox")]
    R["Outbox relay / CDC"]
    Q[("Durable event stream")]
    P["Projection worker"]
    A[("Cassandra: orders_by_id")]
    B[("Cassandra: orders_by_customer_month")]
    RA["Query API"]

    U -->|"Place / pay / cancel order"| C
    C -->|"Single transaction"| DB
    C -->|"Same transaction"| OB
    OB --> R --> Q --> P
    P --> A
    P --> B
    U -->|"View orders"| RA
    RA --> A
    RA --> B
~~~

In this example, a payment command succeeds once the business state and the outbox record are committed at the **source of truth**. The event is delivered to the worker, which then updates each read table. Therefore, **the read API may temporarily see an older version**, even after the write API has returned success. This lag must be part of the product contract.

### Step-by-Step Write Flow

1. The Command API receives `PayOrder(orderId, idempotencyKey)`, authorizes the caller, and validates the order state.
2. Within **a single transaction on the transactional source of truth**, the service updates the order and writes an outbox event, such as `OrderPaid(orderId, version=7, ...)`. If the transaction fails, both changes are rolled back.
3. A relay or CDC mechanism reads the outbox and publishes the event to a durable stream. The event should carry `event_id`, `order_id`, `version`, `occurred_at`, event type, and the data needed to populate read tables.
4. The projection worker consumes the event, updates the relevant Cassandra tables, and acknowledges completion only after required updates succeed.
5. The Query API reads directly from the table serving the query without joining back to the source of truth on every request.

An event stream typically provides **at-least-once delivery**: the same event may arrive again after network failures or worker restarts. Duplicate handling, recovery, and ordering controls must be designed explicitly; one cannot assume each event arrives exactly once.

### Why Not Write Directly to Both Sides in the Command Handler?

Suppose the command handler writes successfully to the source of truth and then writes to Cassandra, but encounters a timeout. The system does not know whether the Cassandra write was applied or not. If Cassandra succeeds first and the source-of-truth transaction rolls back, the read table ends up containing data that was never accepted. Two operations across two systems **do not form an atomic transaction merely because they are called sequentially**.

A **transactional outbox** closes the gap of *writing to the source of truth while losing the event* when the outbox is written in the same transaction as the business data. However, the outbox does not automatically make Cassandra tables atomically consistent: the worker must still be idempotent, retry, and reconcile.

If **Cassandra is also the source of truth**, the architecture can still separate the command model from query projections. However, one must not assume that a Cassandra write across multiple partitions, a logged batch, or an LWT is a distributed transaction equivalent to a relational DBMS transaction. An appropriate change-emission mechanism (CDC, durable event log, or a write flow with a recovery strategy) must be chosen, with atomicity boundaries and partial-update reconciliation clearly defined.

## 3. Designing Cassandra Read Tables Starts from Queries

Suppose the system has two known requirements:

1. `GET /orders/{orderId}`: fetch an order by ID.
2. `GET /customers/{customerId}/orders?month=2026-11`: fetch a customer's newest orders within a month.

Instead of a shared normalized table, create **two projections** containing intentional data duplication:

~~~sql
-- Datacenter name 'dc1' is only an example; use the actual DC name in the real cluster.
CREATE KEYSPACE shop_read
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

-- Direct lookup by order ID.
CREATE TABLE shop_read.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_cents bigint,
    event_version bigint
);

-- List query by customer and month.
CREATE TABLE shop_read.orders_by_customer_month (
    customer_id uuid,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_cents bigint,
    event_version bigint,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

In the `orders_by_customer_month` table:

- The **partition key** is the pair `(customer_id, order_month)`. Orders for a customer within one month are placed in the same logical partition.
- The **clustering key** is `(created_at, order_id)`. Descending creation time returns newest orders first; `order_id` distinguishes orders with identical timestamps.
- `status` and `total_cents` are **denormalized** so the list API does not need extra lookups per `order_id`.
- `event_version` helps identify which business version the projection currently reflects.

The two corresponding queries:

~~~sql
SELECT order_id, customer_id, created_at, status, total_cents
FROM shop_read.orders_by_id
WHERE order_id = 8c614bba-55ab-46bb-86b1-301e34713b9e;

SELECT order_id, created_at, status, total_cents
FROM shop_read.orders_by_customer_month
WHERE customer_id = 6d075fbd-cf57-4f83-a92c-78ab9f61ece3
  AND order_month = '2026-11'
LIMIT 20;
~~~

These queries use the full partition key. No `ALLOW FILTERING`, cluster scan, or join is required. When viewing orders across multiple months is needed, the application queries the relevant buckets and merges results chronologically; `LIMIT 20` on a single bucket does not automatically solve cross-bucket pagination. In production, use paging state, bound the number of buckets accessed, and define clear cross-page merging rules.

**Choosing monthly bucketing must be based on partition size and hotness.** Customers with very high order volumes may need daily bucketing or added sharding; in exchange, queries must read more partitions. No single bucket formula fits every workload. Measure rows per partition, bytes per partition, write rate, and read latency using production-like data.

If the product adds a **pending orders by store** screen, a query model and key tailored to `store_id`/status/bucket must be designed, along with a strategy to delete or move items when status changes. Do not band-aid the existing table by adding `WHERE status = 'PENDING'` when `status` is not part of the query key.

## 4. Turning Business Events into Projections

The worker receives events belonging to the same order:

~~~json
{
  "event_id": "4b598aeb-5c47-41bf-a644-67e2a0cd4f62",
  "type": "OrderPaid",
  "order_id": "8c614bba-55ab-46bb-86b1-301e34713b9e",
  "customer_id": "6d075fbd-cf57-4f83-a92c-78ab9f61ece3",
  "created_at": "2026-11-20T09:15:00Z",
  "order_month": "2026-11",
  "status": "PAID",
  "total_cents": 259900,
  "version": 7
}
~~~

When an order is created (`OrderPlaced`, version 1), the projection worker creates both corresponding records. When paid (`OrderPaid`, version 7), the worker updates `status` and `event_version` on **both** projections. `created_at` and `order_month` should be immutable attributes taken from the original order, not recomputed from the event receipt time.

### Handling Duplicates and Out-of-Order Events

Standard CQL upserts apply **last-write-wins based on write timestamp**. Cassandra does not inherently know that business event version 7 is newer than version 6. If an older event is replayed after a newer event, an unguarded update can revert `status` to an older value.

Several approaches exist, depending on load and correctness constraints:

| Approach | How It Is Applied | Limitations |
| --- | --- | --- |
| **Sequential per order key** | The event stream uses `order_id` as its partition key, processing versions in order per order | Still requires handling duplicates, per-projection failures, and replay flows |
| **Version-conditional LWT** | Transition only from version `n-1` to `n` using `IF event_version = ?` | Costs extra round trips/consensus; different tables still update independently |
| **Rebuildable projection** | Reconstruct read data from snapshots and the event log/source of truth | Requires designing watermarks, event retention, or a complete retrieval source |

Example CQL using a **lightweight transaction (LWT)** to prevent version regression on **an existing record**:

~~~sql
UPDATE shop_read.orders_by_id
SET status = 'PAID',
    event_version = 7
WHERE order_id = 8c614bba-55ab-46bb-86b1-301e34713b9e
IF event_version = 6;
~~~

If the condition is not satisfied, the worker must read the current version and classify the case: duplicate event, a newer version already exists, or an intermediate version is missing. Do not simply ignore every `[applied] = false` result. For creation events, `INSERT ... IF NOT EXISTS` can be used, verifying that the existing record matches the event before treating it as a successfully handled duplicate.

LWT guards the condition within the relevant partition; it is **not** an atomic transaction across `orders_by_id` and `orders_by_customer_month`. If the first table updates successfully while the second fails, the event must be retried or routed to recovery. Separate processing state per projection when they have different availability requirements.

### Java Consumer Illustration

The following snippet illustrates updating **one projection** with Java Driver 4.x after the version 6 record already exists. It shows how to inspect the conditional result, and is not yet a complete consumer including retries, DLQ, and offset management:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

// session is created and lifecycle-managed in the service infrastructure layer.
void projectStatusChange(
        CqlSession session, UUID orderId, String newStatus, long version) {
    PreparedStatement statement = session.prepare(
        "UPDATE shop_read.orders_by_id " +
        "SET status = ?, event_version = ? " +
        "WHERE order_id = ? IF event_version = ?");

    BoundStatement bound = statement.bind(
            newStatus, version, orderId, version - 1)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

    Row result = session.execute(bound).one();
    if (result == null || !result.getBoolean("[applied]")) {
        // Read the current version to distinguish duplicate, out-of-order,
        // or missing record; then retry/reconcile per policy.
        throw new IllegalStateException("Projection version mismatch");
    }
}
~~~

In a real application, prepare the `PreparedStatement` once and reuse it rather than calling `prepare` on every event. Events for the same order should have an ordering strategy in the worker. Apply the same rule to the customer projection without treating the two updates as a single transaction; acknowledge the event only according to the defined completion policy.

## 5. Consistency: Distinguishing Business Transactions from Read-Table Freshness

Suppose the keyspace in the example has **replication factor = 3** in one datacenter and clients read/write with **`LOCAL_QUORUM`**. When replicas operate normally, local quorum requires responses from at least 2 of 3 replicas, ensuring read and write quorums intersect across replicas of **the same data**. This is a balanced choice between availability and consistency for individual Cassandra operations.

However, even when the worker writes successfully with `LOCAL_QUORUM`, the Command API having just written to the source of truth **does not mean** the Query API already sees the updated projection. Between the two APIs lie the relay, queue, worker, and the possibility of a partially updated projection. Distinguish:

1. **Business correctness:** authoritative state, transition validation, idempotency key retention — belongs to the command path/source of truth.
2. **Cassandra consistency level:** affects reading/writing replicas for each individual Cassandra table.
3. **Projection sync lag:** the gap between the version at the source of truth and the latest version each read table has applied.

A request needing immediate fresh data right after payment can return the confirmation result from the Command API, temporarily read from the source of truth for special operations, or return an "updating" state along with the version. Do not use a potentially lagging read table to decide whether a refund is allowed unless an independent, appropriate business check is in place.

A verifiable API design might return:

~~~json
{
  "order_id": "8c614bba-55ab-46bb-86b1-301e34713b9e",
  "accepted_version": 7,
  "read_model_status": "UPDATING"
}
~~~

This is only an **API contract example**: the system must implement how `read_model_status` is determined (e.g., looking up the applied version), rather than inferring that state arbitrarily.

## 6. Operations, Testing, and Recovery

Separating write/read paths increases the number of operational components. These components must have clear monitoring mechanisms:

| Signal | Meaning | Typical Response |
| --- | --- | --- |
| **Event lag** by time and offset | How far the read table lags behind the source of truth | Check queue backlog, worker throughput, Cassandra errors |
| **Version gap** by `order_id` or reconciliation sampling | Projection is missing state transitions | Retry in proper order; backfill from the source of truth |
| **DLQ / retry count** | Event cannot be processed after multiple attempts | Investigate data, schema, dependencies; reintroduce event in order |
| **Cassandra latency and timeouts** | Hot partition, overload, network, or CL settings | Inspect partition distribution, replicas, queries, capacity |
| **Partition size and tombstones** | Overly wide bucket or deletes/updates adding read overhead | Adjust bucketing, TTL/deletion strategy, monitor compaction |

For Cassandra, plan **repairs** and monitor compaction and tombstones according to cluster operational characteristics. TTL is not a fix for a poorly designed deletion mechanism: expired data also creates tombstones during its retention lifecycle and can affect performance. Do not arbitrarily set TTL on order tables if the product requires long-term history.

### When a Projection Fails Mid-Way

Suppose event version 7 updated `orders_by_id` but `orders_by_customer_month` timed out:

1. Leave the event unacknowledged (or record the missing projection state).
2. Retry with appropriate backoff and limits; check version to prevent backward overwrites during retries.
3. If thresholds are exceeded, route to a DLQ containing `event_id`, `order_id`, version, failed projection, and cause.
4. After resolving the incident, replay or backfill and reconcile both tables against the source of truth.

Do not assume a timeout means the write failed: replicas may have accepted the mutation while the client never received the acknowledgment. That is why replay operations must be safe to re-run.

### Rebuilding a Read Table

When adding a new table or changing a partition key, a viable procedure is:

1. Create the new schema and projection worker, establishing the point to start capturing changes (**watermark/offset**).
2. Backfill existing data from the source of truth using a consistent snapshot as supported by the source.
3. Catch up on events from the watermark, avoiding gaps and preventing older events from overwriting newer state.
4. Reconcile row counts and data by time windows, sampling, or per-key version checks.
5. Switch the Query API to the new projection once lag and completeness meet targets; keep the ability to fall back to the old read path during transition.

Simply "copying the whole table and turning on the worker" without a watermark and conflict handling risks losing updates that occurred during backfill.

## 7. Decisions to Lock Down Before Implementation

| Question | Suggested Decision |
| --- | --- |
| Which system determines valid order state? | Designate a single **source of truth** and where invariants are enforced. |
| Which partition key will each read endpoint use? | Write down the actual CQL queries first and design tables around them. |
| What is the maximum acceptable projection lag? | Set measurable targets, such as p95 lag, and UI behavior before updates arrive. |
| What happens on duplicate, out-of-order, or missing-version events? | Define idempotency, ordering, retries, DLQ, and reconciliation. |
| Who is responsible when updating one of multiple tables fails? | Define completion policies and replay mechanisms per projection. |
| Does the partition key risk oversized partitions or hotspots? | Choose buckets from real workload data; measure partition size and multi-bucket queries. |
| How do we evolve schemas with zero downtime? | Projection versioning, backfill, watermarks, reconciliation, and read-traffic cutover. |

### Scenario Analysis Example

**Scenario:** A customer just paid, the write API returned success, yet the "My Orders" page still displays `PENDING` for a few seconds.

**Correct analysis:** First verify the `PAID` status and outbox event at the source of truth. Next check whether the event has been relayed, which version the consumer has processed, and whether `orders_by_customer_month` is lagging. Do not immediately change the Query API's consistency level hoping to fix lag *before the event even reaches Cassandra*.

**Design action:** Display the status confirmed by the Command API on the post-payment screen, monitor projection lag, and allow the Query API to catch up. If the business strictly requires immediate read-after-write, a stronger consistency contract with its corresponding cost is needed, such as reading from the command-side source during the transition window.

## 8. Key Takeaways

Separating the business write path from query-driven read tables lets the application focus **rules and correctness on the command path**, while Cassandra focuses on **distributing and serving query-organized data**. In return, the system accepts duplicated data, asynchronous synchronization, and projection operational responsibility.

Three most important principles:

1. **Design Cassandra tables from the questions they must answer and their partition keys**, not from normalized entity diagrams.
2. **Do not treat multiple separate writes as if they were a distributed transaction**; use an outbox when the source of truth supports transactions and ensure safe replay.
3. **Measure and handle lag, duplicate events, out-of-order delivery, and per-projection failures**; Cassandra consistency levels do not replace these guarantees.
