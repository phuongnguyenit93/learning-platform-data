# Choosing Cassandra's Role in the System and Identifying the Source of Truth

## 1. Learning Objectives and Context

Apache Cassandra is a distributed NoSQL database following the **wide-column** model, designed for horizontal scaling, maintaining availability when a subset of nodes fail, and serving partition-key-based queries with predictable latency. In a Java application architecture, choosing Cassandra is not merely choosing a storage technology: the team must decide **which data belongs to Cassandra, who has authority to write authoritative data, and how the system recovers state when inconsistencies or failures occur**.

After this lesson, learners will be able to:

1. Distinguish *system of record* (the authoritative system recording business data) from *read model* (a model serving queries), caches, and data replicas.
2. Determine when Cassandra is suitable as a source of truth and when it should serve as a read model generated from PostgreSQL, an event log, or another system.
3. Design the data flow, choose CQL tables based on queries, and select partition keys to avoid overly hot or oversized partitions.
4. Evaluate the impact of replication, consistency level, timeouts, retries, compaction, and repair on business guarantees.
5. Make decisions verifiable through architecture documentation, load testing, and recovery scenarios.

**Lesson scope:** focuses on Cassandra's role in application architecture and identifying the source of truth; the CQL, operational, and Java examples serve to demonstrate the feasibility of those decisions.

## 2. Concepts to Distinguish

| Concept | Question It Must Answer | Example |
|---|---|---|
| **System of record (SoR)** | Which system has authority to confirm the current business record? | PostgreSQL confirms valid orders and payments. |
| **Source of truth** | When two systems conflict, which data is used to arbitrate and reconstruct the rest? | The committed order record in the Orders service; events emitted from this record. |
| **Read model / projection** | Which table is optimized to answer a specific set of queries and can be rebuilt from the source of truth? | Cassandra stores the list of orders by customer for fast display. |
| **Cache** | Which copy can be discarded or reloaded without losing business data? | Redis stores short-lived query results; Cassandra is typically used as a durable *serving store* rather than a conventional cache. |
| **Event log** | Which immutable sequence of events describes changes and can be replayed? | Order change log retained long enough to rebuild projections. |
| **Data owner** | Which service is permitted to create, validate rules for, and modify a domain's data? | Orders Service owns the order lifecycle; Reporting Service only consumes replicas. |

**There is no rule that "the entire system may only have one authoritative database."** The source of truth is defined per *data domain*, or even per group of attributes: orders, payments, device configurations, and sensor records may be owned by different services. However, **each business fact requires a clear arbitration rule**. Two databases that both allow direct edits to the same field without synchronization and conflict resolution mechanisms represent a design lacking clear authority.

Data can be "stored durably" in Cassandra and still only be a projection: the durability of a copy does not automatically turn that copy into the source of truth.

## 3. What Role Should Cassandra Play?

### 3.1. Architectural Options

| Role | When Suitable | Who May Write? | Recovery / Limitations |
|---|---|---|---|
| **Source of truth for events or key-based records** | High write volume, access by device/account and time range, independent records, low multi-entity transaction requirements. | The ingestion service or domain service owning the events. | Snapshots/backups, repair, sufficient retention; requires deduplication rules and data correction procedures. |
| **Serving store / read model** | Requires multiple individually optimized read patterns, stable queries, and authoritative data resides in another system. | Only projection consumers or synchronization pipelines. | Replay events or rebuild from the source of truth; accept published update lag. |
| **Timeline / activity feed store** | Repeated queries like "latest N activities per user/entity", write-heavy, time-ordered. | Activity-producing service or authoritative consumer. | Must know whether the feed is raw data or reproducible; manage time-based partitions. |
| **Secondary store for search/reporting** | Only when queries are fixed by partition key and an appropriate data model. | Pipeline from the source of truth. | Cassandra is not a direct replacement for full-text search engines, OLAP, or arbitrary analytical SQL. |

Cassandra is generally **not the default choice** for workloads requiring many JOINs, arbitrary ad-hoc queries, foreign key constraints, global aggregations, or ACID transactions spanning multiple entities. Those requirements may be better served by a relational DBMS, search engine, or data warehouse. Nor should Cassandra be chosen merely because of "big data": one must specify *dominant queries, partition keys, read/write throughput, consistency levels, and operational practices*.

### 3.2. Role Selection Process

1. **List business invariants.** For example: a refund cannot be confirmed exceeding the paid amount; there cannot be two different final balances. Invariants requiring synchronous updates across multiple rows or partitions signal the need to consider a transactional SoR.
2. **List actual queries.** Specify filter conditions, sort order, result size, frequency, and SLOs. For example: "fetch the 100 most recent events for a device on a given day", not simply "query events".
3. **Identify owners and arbitration rules.** Which service is allowed to write? When Cassandra and another database disagree, which one is trusted? Who is responsible for fixing discrepancies?
4. **Define the update path and acceptable latency.** Direct updates, event-driven updates, or pipeline updates? Do users need immediate read-your-write semantics?
5. **Simulate failures and reconstruction.** If a consumer stops for 30 minutes, a write times out, a node fails, or an entire Cassandra table must be rebuilt, what data does the system use to recover?
6. **Load-test with realistic partition distributions.** Check key distribution, large partitions, paginated queries, compaction, and tombstones; adding more nodes will not rescue a single hot partition.

## 4. Scenario A: PostgreSQL Holds Authoritative Orders, Cassandra Serves Queries

Suppose an e-commerce platform handles payment confirmation, order status transitions, and inventory checks. The data requires consistency across multiple tables and transactional guarantees. The application must also display "the customer's 50 most recent orders" under heavy read traffic.

**Decision:**

- **Orders Service + PostgreSQL** is the SoR for order status; Payment Service and the payment gateway have separate reconciliation rules for payments.
- **Cassandra** holds a projection serving the order history page. Records here may lag by a few seconds within the agreed SLO; it is never used to decide whether a refund is permitted.
- Only Orders Service is authorized to issue business state changes. A consumer updates Cassandra; the order-listing API reads from the projection, whereas confirmation or monetary APIs read from the source of truth.

~~~mermaid
flowchart LR
    A[Web / mobile app] --> B[Orders Service]
    B -->|Transaction: order + outbox| C[(PostgreSQL - SoR)]
    C -->|Outbox relay / CDC| D[Event stream]
    D --> E[Projection consumer]
    E --> F[(Cassandra - read model)]
    A --> G[Order History API]
    G -->|Order list by customer| F
    F -. Failure or data drift .-> H[Rebuild / reconcile from SoR]
    C --> H
~~~

### 4.1. Why Is a Transactional Outbox Needed?

If Java code commits to PostgreSQL and then sends an event sequentially, the process could crash between the two steps: the order has changed, but Cassandra never receives the update. If the event is sent before committing, the projection might display an order that does not yet exist or ultimately gets rolled back.

With a **transactional outbox**, the same PostgreSQL transaction writes both the order change and an outbox row. A relay/CDC mechanism publishes that row to the event stream; the consumer applies it to Cassandra. Delivery typically has **at-least-once** semantics, so duplicate events must be tolerated.

Example payload:

~~~json
{
  "eventId": "fdf7a157-a5f1-4280-a413-9639add340a5",
  "type": "OrderStatusChanged",
  "orderId": "ORD-1024",
  "customerId": "CUS-88",
  "version": 7,
  "status": "SHIPPED",
  "occurredAt": "2026-11-21T03:10:00Z"
}
~~~

Two common pitfalls:

- **Duplicate events:** use a stable event key, track processed markers, or design idempotent upserts; do not blindly increment revenue counters every time the same event is received again.
- **Out-of-order delivery:** if version 7 arrives before version 6, blindly overwriting based on "last event received" will regress the state. Ensure per-orderId consumption ordering and version checking/reconciliation; where a version must be guarded on the Cassandra row itself, a conditional lightweight transaction (LWT) can be used, at a higher consensus cost than standard writes.

A Cassandra write and a PostgreSQL commit should not be treated as a single distributed transaction by default. The design must allow *replay*, *reconciliation*, lag monitoring, and controlled error handling.

### 4.2. Query-Driven Projection

The product query is "list a customer's orders by month, newest first." A table can be designed as:

~~~sql
CREATE TABLE order_read.orders_by_customer_month (
    customer_id text,
    order_month text,       -- Example '2026-11'
    created_at timestamp,
    order_id text,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);

SELECT order_id, created_at, status, total_amount
FROM order_read.orders_by_customer_month
WHERE customer_id = 'CUS-88' AND order_month = '2026-11'
LIMIT 50;
~~~

The composite partition key **customer_id + order_month** bounds data accumulation within a partition over time. **created_at + order_id** establishes deterministic ordering and prevents primary key collisions if two orders share the exact same creation timestamp. When multiple months are needed, the application queries the respective partitions and merges bounded results; Cassandra does not natively support cross-table JOINs like a relational database.

Status updates in the projection may lag. If a customer just placed an order and needs to see it immediately on the confirmation screen, the API can return data from the SoR write result or read the order directly from Orders Service. This exception must be explicitly documented in the API contract.

## 5. Scenario B: Cassandra as the Source of Truth for Time-Series Telemetry

An IoT platform receives millions of temperature, vibration, or location events; a common requirement is "fetch events for device X on day D, most recent first." Events are independent, write-heavy, require no JOINs, and have a clear retention policy. Cassandra **can** serve as the SoR for accepted events within the committed retention window.

~~~mermaid
flowchart LR
    S[Device] --> I[Ingestion API: auth / normalization]
    I --> Q[Durable queue if needed for burst absorption]
    Q --> W[Java writer: idempotency]
    W --> C[(Cassandra - telemetry SoR)]
    C --> R[Telemetry Query API]
    C --> A[Backup / archive per policy]
    M[(Device registry - separate SoR)] --> I
~~~

Here, the **Device Registry** (owning device registration, keys, and configuration) can still live in PostgreSQL. Cassandra is only the SoR for the *telemetry domain*. If Cassandra data has a 90-day TTL, the "source of truth" guarantee also applies only to data within that 90-day window; if the business requires multi-year audit evidence, a durable storage tier clearly designated as the historical source of truth is required.

### 5.1. Designing CQL from Queries, Not from Entity Models

~~~sql
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE telemetry.events_by_device_day (
    device_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload_json text,
    PRIMARY KEY ((device_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

SELECT event_time, event_id, event_type, payload_json
FROM telemetry.events_by_device_day
WHERE device_id = 'sensor-17'
  AND day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-22T00:00:00Z'
LIMIT 100;
~~~

Explanation:

- **Partition key (device_id, day):** determines the logical placement of data across replicas while bounding a read to a single partition. It is not an automatic load-splitting mechanism inside a single partition.
- **Clustering columns (event_time, event_id):** orders events within the partition; event_id disambiguates two events with the same timestamp.
- **A primary key is not a cluster-wide uniqueness constraint on eventId.** Sending the same eventId with a different device_id or day creates a separate row. Writers must validate identifier consistency.
- **Tables are built for queries:** if the product adds "all alerts for a region in the past hour", a separate projection/table or specialized engine must be designed; do not default to cluster-wide scans with ALLOW FILTERING.
- **Avoiding hot/large partitions:** a device emitting tens of thousands of events per second may require hourly bucketing, controlled sharding, or a different ingestion mechanism. Smaller buckets mean multi-day queries must read more partitions; choose based on measurement.

Example of writing an event with a stable identifier:

~~~sql
INSERT INTO telemetry.events_by_device_day
    (device_id, day, event_time, event_id, event_type, payload_json)
VALUES
    ('sensor-17', '2026-11-21', '2026-11-21T03:10:00Z',
     2f75b225-46f8-486c-96eb-a2743ae83365,
     'temperature', '{"celsius":28.4}');
~~~

The application **must preserve the exact same event_id and partition key when retrying the same event**. Generating a new UUID on every retry introduces semantically duplicate events. Storing a separate "latest temperature" record is another projection; two independent table writes do not form an atomic global transaction.

### 5.2. Retention, Deletion, and Durability

TTL allows data to expire automatically but creates **tombstones**, and cleaning up data files depends on compaction. For time series with uniform write/expiration times, **TimeWindowCompactionStrategy (TWCS)** can be evaluated. Tombstone counts, SSTable sizes, slow reads, disk usage, and compaction duration must be measured; do not choose TWCS merely because the table name has a time column.

TTL does not replace a backup/archival policy. If events serve as business or legal evidence, clearly define the long-term retention store, when data is transferred, how completeness is verified, and how recovery works. Deletions via TTL/DELETE also require proper repair operations and adherence to tombstone-related thresholds to avoid resurrected deleted data during prolonged replica outages.

## 6. Consistency Level and Scope of Guarantees

Cassandra replicates data according to the **replication factor (RF)**. In a data center with RF = 3, a **LOCAL_QUORUM** write requires acknowledgments from at least 2 replicas in that data center; a LOCAL_QUORUM read also requires 2. A commonly used relationship is:

\[
R + W > RF
\]

With R = 2, W = 2, and RF = 3, the read and write replica sets overlap under this model. This serves as a basis for choosing consistency levels, **not a guarantee of multi-partition ACID transactions, absolute linearizability across all concurrent writes, or never reading stale state**. Mutation timestamps, write conflicts, failed replicas, expired data, and how the application handles concurrent writes still matter.

| Requirement | Commonly Considered Configuration | What the Application Must Still Handle |
|---|---|---|
| Telemetry tolerating very brief update lag, prioritizing availability | ONE or LOCAL_ONE for certain read/write paths aligned with SLAs | Stale reads, unresponsive replicas, reconciliation, and repair. |
| Critical reads/writes within one data center | LOCAL_QUORUM with an appropriate RF, after measuring latency | Ambiguous timeouts (uncertain whether committed); concurrent writes, idempotent retries. |
| Conditional single-row writes needing contention control | LWT / IF with an appropriate serial consistency level | Higher latency and lower throughput than normal writes; do not generalize into multi-partition transactions. |
| Transactional inventory or payment updates across multiple entities | Transactional SoR or dedicated business orchestration | Cassandra does not natively provide multi-entity SQL/ACID constraints. |

**Timeouts have ambiguous outcomes:** a client not receiving a response **does not prove the write failed**; some replicas may have already persisted it. For event writes, use stable identifiers and safe retries; for payments or monetary counters, enforce business-level idempotency at the data owner. Do not retry indefinitely or raise consistency levels without checking availability under node failures.

**Replication is not backup.** Replication also replicates bad writes or accidental deletes. Snapshots/backups aligned with RPO/RTO, restore drills, monitoring replication lag/repair, compaction backlog, coordinator errors, and tombstone counts are required. **Repair** helps replicas converge; it cannot decide whether an order is "paid" or "canceled" when two authoritative sources conflict.

## 7. Connecting from a Java Application

The Java driver should manage a **shared CqlSession**, configured according to the actual cluster and data center topology; use prepared statements for repeated queries. Example of writing telemetry (Java snippet using driver 4.x API):

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

// Configure contact points, TLS, authentication, and timeouts in the deployment environment.
try (CqlSession session = CqlSession.builder()
        .withLocalDatacenter("dc1")
        .build()) {
    PreparedStatement insert = session.prepare(
        "INSERT INTO telemetry.events_by_device_day " +
        "(device_id, day, event_time, event_id, event_type, payload_json) " +
        "VALUES (?, ?, ?, ?, ?, ?)");

    String deviceId = "sensor-17";
    Instant eventTime = Instant.parse("2026-11-21T03:10:00Z");
    // ID received from upstream and preserved across retries of the same event.
    UUID eventId = UUID.fromString("2f75b225-46f8-486c-96eb-a2743ae83365");
    LocalDate day = eventTime.atZone(ZoneOffset.UTC).toLocalDate();

    BoundStatement write = insert.bind(
            deviceId, day, eventTime, eventId,
            "temperature", "{\"celsius\":28.4}")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

    session.execute(write);
}
~~~

In a production service, create the session once for the application's lifecycle (e.g., as a singleton bean) and close it on shutdown; the snippet above only illustrates a standalone operation. Data center, replication, TLS, and consistency profile configurations must match the deployment environment. When using the asynchronous API, bound in-flight requests and apply backpressure so traffic bursts do not exhaust connections, queues, or memory.

If a write times out, application code needs a retry policy grounded in **operation idempotency**; writing with the same eventId is insufficient if non-idempotent side effects occur in other services. Attach traceId/eventId, measure latency by consistency level, timeout rates, unavailable errors, and consumer backlog to trace discrepancies back to their source.

## 8. Authoritative Data Contract Between Services

Before introducing Cassandra into a system, create a short, verifiable *data ownership contract*:

| Aspect to Specify | Example of a Clear Decision |
|---|---|
| Data domain and owner | Orders Service owns order state; Telemetry Service owns sensor events. |
| Authoritative record | PostgreSQL orders for order state; Cassandra events_by_device_day for telemetry within retention. |
| Who is allowed to write | Only the domain service or projection consumer writes to its assigned tables; BI never modifies source data directly. |
| Business keys and versioning | orderId + version; deviceId + day + eventTime + eventId; eventId preserved on retries. |
| Conflict resolution rules | Order state is rebuilt from PostgreSQL; telemetry events are reconciled against source identifiers and ingest logs. |
| Consistency and freshness requirements | Monetary operations read the SoR; order history may lag up to SLO; telemetry measures P95/P99 latency. |
| Retention and recovery | TTL, archival, backup schedule, RPO/RTO, replay source, and drill owner. |
| Alerting signals | Consumer lag, projection mismatch, hot partitions, tombstones, read/write timeouts, overdue repairs. |

### 8.1. Architecture Acceptance Checklist

- [ ] For each data domain, **SoR, data owner, derived data**, and write permissions are explicitly stated.
- [ ] Every critical endpoint documents its partition-key query, expected partition size, and SLO.
- [ ] Cases requiring multi-entity transactions are identified; they do not rely on two independent Cassandra writes.
- [ ] Mechanisms exist for idempotency, ordering/version protection, and handling ambiguous timeouts.
- [ ] If Cassandra is a projection, a rebuild source, replay mechanism, and drift-checking procedure are defined.
- [ ] If Cassandra is an SoR, TTL/archival/backup/restore policies match the retention period.
- [ ] Load tests have covered skewed keys (hot partitions), node loss, consumer backlog, duplicate records, and out-of-order events.
- [ ] Consistency levels, replication factors, compaction, and repair have been selected and measured in a production-like environment.

### 8.2. Design Exercise

A delivery management system has three requirements: (1) accurate payments and refunds; (2) updating driver coordinates every 3 seconds; (3) displaying a customer's 20 most recent orders. For each data group, determine the SoR, Cassandra's role, partition key, acceptable lag, and recovery strategy if a consumer stops for one hour.

A sound approach: keep payment state in an authoritative transactional service; store driver locations/timeline in Cassandra keyed by driver and time bucket if queries align; build an order history table in Cassandra as a read model from domain events. **The final design must depend on business invariants and measured queries**, especially if there are requirements for route-based pricing, location disputes, multi-year retention, or analytical queries across all drivers.

## 9. Conclusion

Cassandra's proper place is determined by **data ownership, business invariants, and query patterns**, followed by CQL design and cluster sizing. Cassandra is well suited for clearly partition-keyed records, high-volume event streams, and distributed read models; it can also serve as the SoR for a domain with sufficiently simple transactional needs. When authoritative data resides elsewhere, Cassandra must be treated as a rebuildable projection with clearly designed event emission, deduplication, out-of-order handling, lag tracking, and reconciliation. A complete architecture can always answer the question: **"If two copies disagree, which source do we trust and how do we recover?"**
