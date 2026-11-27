# Coordinating Neo4j with Other Data Stores and Managing Cross-System Consistency

## Learning Objectives

After this lesson, you will be able to:

- Identify the **authoritative data source** (*source of truth*) for each entity when an application uses Neo4j alongside an RDBMS, search engine, cache, or event broker.
- Distinguish **consistency within a single Neo4j transaction** from **cross-system consistency**; choose strong consistency, eventual consistency, or business-appropriate compensating workflows.
- Explain why naive **dual-writes** to two databases are unsafe if implemented merely as two sequential writes.
- Design a **transactional outbox → broker/CDC → Neo4j consumer** pipeline with business keys, idempotency, versioning, ordering control, and delete handling.
- Design **snapshot/backfill, checkpointing, retries, dead-letter queues, reconciliation**, and recovery procedures when a component goes down.
- Combine the Java Driver or Spring Data Neo4j with transactions on the source store without mistaking them for a single distributed transaction.
- Measure synchronization lag, data divergence rates, and impact on critical relationship/path queries.

This belongs to the **Application Design** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. Neo4j represents connected data as a **property graph**: nodes, relationships, properties, and Cypher queries. In real systems, an application may also use PostgreSQL/MySQL for order processing, Kafka for event streaming, Elasticsearch/OpenSearch for search, and Redis for caching. Each store offers distinct value; the major challenge is **keeping representations consistent with the business contract** when each store has its own transactions, data model, and update speed.

> Illustrative examples use PostgreSQL and Neo4j with Java. Table names, properties, Java APIs, connectors, and operational workflows must be adapted to your running product versions. **There is no automatic ACID transaction spanning PostgreSQL, Neo4j, Kafka, and HTTP** simply because the application uses Spring `@Transactional`.

## 1. Why Combine Multiple Data Stores?

An e-commerce system has these requirements:

1. Enforce payment, inventory, and invoicing transactions with strict constraints.
2. Answer "which products has this customer bought, and how are they connected to other customers?"
3. Run full-text search across product names or descriptions.
4. Serve fast API responses and cache frequently accessed screens.

It is unnecessary to force every requirement into a single database:

| Component | Suitable Role | What Must Be Decided |
| --- | --- | --- |
| **RDBMS** | Source transactions: orders, payments, inventory, relational constraints | Which tables are the source of truth? |
| **Neo4j** | Multi-hop queries, customer–order–product relationships, paths, connection discovery | Is the graph a read replica or the primary write source? |
| **Search engine** | Text search, ranking, token analysis | How stale can the index be? |
| **Cache** | Reduce latency for popular reads | What are the invalidation/TTL rules? |
| **Event broker** | Replayable/recoverable change propagation and producer–consumer decoupling | What are ordering, retention, and delivery guarantees? |

This architecture is commonly called **polyglot persistence**. It does not mean every store may mutate the same entity arbitrarily without rules.

### 1.1. Order Flow Example

~~~mermaid
flowchart LR
    API["Order API / Java Service"] -->|Write source transaction| R[("PostgreSQL<br/>Orders + Outbox")]
    R -->|Outbox publisher / CDC| B["Kafka or message broker"]
    B --> N["Graph projector / consumer"]
    N -->|Neo4j transaction| G[("Neo4j<br/>Customer-PLACED-Order")]
    B --> S["Search indexer"]
    S --> X[("Search engine")]
    QR["Relationship API"] -->|Cypher READ| G
~~~

**Architectural assumption of the example:** PostgreSQL decides whether an order exists or is paid. Neo4j is a **read model** serving connected queries; if Neo4j lags behind incoming events, the order **does not vanish from the source of truth**. Graph queries may temporarily lag behind the latest updates.

If Neo4j is the source of truth for a different business relationship (for example, an organizational hierarchy tree), design the **reverse sync direction** and separate write boundaries explicitly. Never assume PostgreSQL is always the primary source for all data.

## 2. Define Ownership and Invariants Before Writing Code

A cross-system data contract must answer:

- Who is authorized to **create, update, and delete** each object type?
- Which IDs are durable across stores: `customerId`, `orderId`, `sku`?
- When properties change, where is the **version** incremented?
- How quickly must the Neo4j replica catch up: within seconds or synchronously in the request?
- When one side fails, may the request return "success," or must the source transaction be blocked?

Example contract for a read-side model:

| Data | Authoritative Source | Neo4j Replica | Rule |
| --- | --- | --- | --- |
| `Customer.customerId` | Customer Service / RDBMS | `:Customer` node | Never generate new IDs when replicating |
| `Order.orderId`, `status`, `totalCents` | Order Service / RDBMS | `:Order` node | Read/apply according to source version |
| `Customer -[:PLACED]-> Order` | Owning customer ID in Order Service | Relationship in Neo4j | Reflect ownership accurately, including changes/deletes |
| `Product.sku` | Product Catalog | `:Product` node | Use stable ID; out-of-order/late events can happen |
| `Order -[:CONTAINS]-> Product` | Order Service / line item data | Relationship in Neo4j | Never treat a temporarily missing node as permanent failure |

**Business invariants** are rules that must always hold at the source: e.g., an order is charged only once, inventory never goes negative, two orders never share `orderId`. **Replica invariants** are states the graph must converge toward: accurate nodes, relationships, `sourceVersion`, and no stale edges after ownership changes.

Distinguish **immediately consistent invariants** from **eventually consistent invariants**:

- Never double-charge: **zero tolerance for lag/stale reads**; enforce in the authoritative system with idempotent payment processing.
- "Similar orders" list in Neo4j updating 2 seconds later: acceptable if the product permits.
- Approving access grants based on a lagging graph: **high risk**; never rely on a lagging read model when security decisions require live state.

## 3. Local ACID Does Not Become Cross-System ACID

Neo4j provides ACID transactions for changes **within that Neo4j database**. PostgreSQL has its own transactions. Two transactions **do not automatically commit/roll back together**:

~~~text
BEGIN PostgreSQL
    UPDATE orders SET status = 'PAID' ...
COMMIT PostgreSQL

BEGIN Neo4j
    MATCH (o:Order {orderId: ...}) SET o.status = 'PAID'
COMMIT Neo4j
~~~

The snippet above is pseudocode. If the first commits and the process crashes before the second, PostgreSQL updated the status while Neo4j did not. Spring `@Transactional` on a service **does not automatically span two transaction managers** or make an HTTP/message-broker call part of the same transaction.

### 3.1. Anti-Pattern: Direct Dual-Write

~~~mermaid
sequenceDiagram
    participant App as Order Service
    participant RDB as PostgreSQL
    participant Graph as Neo4j
    App->>RDB: COMMIT Order = PAID
    RDB-->>App: OK
    Note over App: Crash / timeout
    App--xGraph: :Order not updated
    Note over RDB,Graph: Two representations drift apart
~~~

Reversing the write order does not solve the core problem: if Neo4j commits first and PostgreSQL fails, the graph holds state never accepted by the source of truth.

| Approach | Guarantee | Risk |
| --- | --- | --- |
| Two sequential writes | No cross-store atomicity | Mid-flight crash causes divergence |
| Retry the second write | Improves convergence likelihood | Does not recover lost requests if the process dies without a durable retry record |
| Transactional outbox at source | Business change and **intent to emit event** commit atomically at source | Consumer remains asynchronous; needs retries and deduplication |
| Saga / compensation | Coordinates multiple local transactions with compensating actions | Does not offer single-transaction instant rollback |
| Distributed transactions / 2PC | Can coordinate atomic commit if **every system and config genuinely supports it** | Complex, hurts availability; never assume Neo4j + RDBMS + broker natively support it |

For a graph read model, **outbox + eventual synchronization** is usually far more practical than forcing a distributed transaction across every step.

## 4. Transactional Outbox: Committing Data Changes and Events Together

A transactional outbox stores an event **directly inside the authoritative database**, in the **same transaction** as the business mutation. A separate publisher/CDC process then forwards that event to the broker or consumer.

~~~mermaid
flowchart TD
    A["Order Service receives command"] --> T["PostgreSQL Transaction"]
    T --> O["UPDATE orders and increment version"]
    O --> E["INSERT outbox_events"]
    E --> C{"COMMIT?"}
    C -->|No| R["Rollback both Order and Outbox"]
    C -->|Yes| P["Publisher/CDC reads event"]
    P --> B["Broker / Neo4j Consumer"]
~~~

### 4.1. Illustrative PostgreSQL Schema

~~~sql
CREATE TABLE orders (
    order_id       text PRIMARY KEY,
    customer_id    text NOT NULL,
    status         text NOT NULL,
    total_cents    bigint NOT NULL,
    version        bigint NOT NULL DEFAULT 0
);

CREATE TABLE outbox_events (
    event_id           uuid PRIMARY KEY,
    aggregate_type     text NOT NULL,
    aggregate_id       text NOT NULL,
    aggregate_version  bigint NOT NULL,
    event_type         text NOT NULL,
    payload            jsonb NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    published_at       timestamptz
);

CREATE UNIQUE INDEX outbox_order_version_uk
ON outbox_events (aggregate_type, aggregate_id, aggregate_version);
~~~

This schema is **illustrative**, not mandatory. A uniqueness constraint on aggregate/version fits only when **each version emits one corresponding event**; if business rules emit multiple events per version, design a different key. Establish retention policies, read permissions, and handling for sensitive fields inside `payload`.

Suppose a command updates status within **the same PostgreSQL transaction**:

~~~sql
BEGIN;

UPDATE orders
SET status = 'PAID',
    version = version + 1
WHERE order_id = :orderId
  AND status = 'PENDING'
RETURNING order_id, customer_id, status, total_cents, version;

-- The application uses the exact row returned by UPDATE to build the event snapshot,
-- then inserts the event with the same order_id and version in this transaction.
INSERT INTO outbox_events (
    event_id, aggregate_type, aggregate_id,
    aggregate_version, event_type, payload
)
VALUES (
    :eventId, 'Order', :orderId,
    :newVersion, 'OrderChanged', :payloadJson
);

COMMIT;
~~~

The two SQL statements rely on application logic reading the `RETURNING` row; **if `UPDATE` returns 0 rows**, do not insert an event and decide whether to return an error, handle idempotently, or ignore per business rules. Both must execute on the **same PostgreSQL connection/transaction**. Never insert an event using a `version` read outside the mutating transaction.

In Spring, `@Transactional` on the **RDBMS transaction manager** can wrap the order repository update and outbox insert; after commit, an asynchronous publisher emits the event. Never call Neo4j inside it and assume that transaction annotation covers Neo4j too.

### 4.2. Minimal Payload with Version and Stable ID

~~~json
{
  "eventId": "f3d0b1f1-0181-4b3f-bebb-44a0b9c17355",
  "eventType": "OrderChanged",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "O-901",
  "aggregateVersion": 12,
  "occurredAt": "2026-11-25T08:12:00Z",
  "data": {
    "orderId": "O-901",
    "customerId": "C-101",
    "status": "PAID",
    "totalCents": 150000
  }
}
~~~

Values are **hypothetical**. Events should carry enough information for the projector to build state without calling back to multiple services per event. `aggregateVersion` distinguishes older/newer events; `schemaVersion` lets consumers decode evolving event contracts; `eventId` supports deduplication. Never emit unnecessary sensitive fields if the graph only needs codes and statuses.

### 4.3. Publishers Do Not Get "Exactly Once" for Free

Suppose a publisher:

1. Reads an outbox event.
2. Sends it to Kafka; the broker acknowledges receipt.
3. Crashes before marking `published_at`.

Upon restart, the publisher may emit **the same event twice**. Therefore, a typical outbox guarantees **not losing the intent to emit an event**, yet **delivery can duplicate**. Even when a broker/connector advertises exactly-once semantics within its scope, check the exact **guarantee boundary**; never assume every downstream effect in Neo4j and external systems is also exactly-once.

Marking an outbox row as published **before** broker confirmation is equally dangerous: a crash right after can **lose the event**.

## 5. Where Does CDC Read From? Distinguishing Source and Sink

**Change Data Capture (CDC)** reads committed changes and streams them downstream. There are two different architectural directions:

| Flow | Change Source | When Used |
| --- | --- | --- |
| **PostgreSQL → Neo4j** | PostgreSQL outbox or CDC | RDBMS is source of truth; Neo4j is a graph projection |
| **Neo4j → other systems** | **Neo4j CDC** or application outbox on a Neo4j source | Graph is where authoritative changes originate |

Do not confuse installing a **Neo4j sink connector** (writing into Neo4j) with **enabling Neo4j CDC** (reading changes out of Neo4j). For PostgreSQL → Neo4j, a projector can work via a Kafka consumer + Neo4j Java Driver **without needing Neo4j CDC**.

### Conditions When Neo4j Is the CDC Source

Official Neo4j CDC is conditional on **version, edition/deployment tier, and configuration**. In the Neo4j 5.x series, CDC was introduced in 5.13 for Enterprise, and procedure namespaces changed in 5.17 from `cdc.*` to `db.cdc.*`; verify documentation for newer releases. Neo4j Community does not natively include official CDC. Beyond edition support, you must **enable the appropriate change capture mode** and verify CDC read permissions.

If syncing Neo4j → Kafka/search, design **cursors, transaction log retention, checkpoints, and initial snapshots** just like any reliable CDC source. Never treat Neo4j CDC as an infinite message queue; old cursors can become invalid if logs are pruned or the database undergoes certain lifecycle events.

## 6. Turning Events into Nodes and Relationships in Neo4j

A Neo4j consumer generally **does not need to replay the entire PostgreSQL transaction**. It must **project** the data contract into the right nodes, relationships, and properties.

### 6.1. Prepare Uniqueness Constraints

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;

CREATE CONSTRAINT applied_graph_event_id_unique IF NOT EXISTS
FOR (e:AppliedGraphEvent)
REQUIRE e.eventId IS UNIQUE;
~~~

These constraints:

- Protect logical IDs in the graph; never rely on internal node IDs or `elementId` as cross-system keys.
- Allow Cypher to use uniqueness-backed indexes to look up nodes by `customerId`/`orderId`.
- Prevent two transactions from **committing the same `eventId`** into the processed-event tracking log.

Neo4j `MERGE` does not replace uniqueness constraints when multiple consumers contend concurrently. For parallel relationships or composite keys, design models/constraints and locking mechanisms suited to your Neo4j version.

### 6.2. A Cypher Statement to Update the Graph Projection

For a **full-state** `OrderChanged` event where the order's `customerId` **has not changed**:

~~~cypher
MERGE (c:Customer {customerId: $customerId})
MERGE (o:Order {orderId: $orderId})
SET o.status = $status,
    o.totalCents = $totalCents,
    o.sourceVersion = $version
MERGE (c)-[:PLACED]->(o)
RETURN o.orderId AS orderId;
~~~

`MERGE` finds or creates nodes/edges matching the pattern. Because the event includes the customer ID, the consumer may create a **Customer placeholder** holding only `customerId` if customer details haven't arrived yet. When the customer event arrives later, it fills in authoritative properties. Establish a policy for placeholders and orphaned nodes/relationships rather than silently tolerating missing data forever.

**Never run this statement blindly when an older event arrives after a newer one.** A `SET` without checking `sourceVersion` will **regress state**. The consumer layer must enforce ordering or apply an appropriate version guard (section 7).

### 6.3. When Relationships Change or Entities Are Deleted

If an order can change owning customers, `MERGE (c)-[:PLACED]->(o)` alone leaves the old edge behind. For an authoritative **ownership snapshot** event, delete old `PLACED` edges **pointing to that exact order**, then create the new edge in **the same Neo4j transaction**:

~~~cypher
MATCH (o:Order {orderId: $orderId})
OPTIONAL MATCH (:Customer)-[old:PLACED]->(o)
DELETE old
WITH DISTINCT o
MERGE (newOwner:Customer {customerId: $customerId})
MERGE (newOwner)-[:PLACED]->(o)
RETURN o.orderId;
~~~

This query is specifically an **ownership-replacement** step driven by a version-checked event. It deletes **all `PLACED` edges pointing to the order**; it is valid only when the business contract stipulates a single owner and `PLACED` carries no other semantics. Never use it as-is if an order may validly have multiple owners.

For delete events, define **tombstone** semantics clearly:

- Soft delete: set `o.deleted = true`, preserving the graph for historical queries if required.
- Hard delete: run `DETACH DELETE o` when you truly want to remove the node and **all attached relationships**.
- Delete specific relationship: `MATCH ... DELETE r` when only the link expires.

Never delete a node shared by another domain, nor let a late old event resurrect a just-deleted node. For hard deletes, retain a **tombstone/version** in an appropriate place to block late upsert events; otherwise deleted records can "come back to life."

## 7. Idempotency and Event Ordering: Conditions for Convergence

Brokers and webhooks commonly **duplicate, delay, reorder, or temporarily drop connections**. Consequently, **a consumer must never assume the most recently received event is the newest event**.

### 7.1. Event ID and Aggregate Version Solve Two Different Problems

| Field | Purpose | Limitation |
| --- | --- | --- |
| `eventId` | Identify **the exact same event** redelivered | Two events with different IDs can still have duplicate business effects |
| `orderId` | Identify **the same order** across databases | Does not express order of updates |
| `aggregateVersion` | Compare newer/older state **within one aggregate** | Does not establish global order across different aggregates |
| `schemaVersion` | Identify payload structure for decoding | Not the data's source version |
| `occurredAt` | Observability and sync SLAs | Timestamps do not replace monotonic version numbers under clock skew |

Example:

~~~text
Event E10: Order O-901, version 10, status=PENDING
Event E12: Order O-901, version 12, status=PAID
Event E11: Order O-901, version 11, status=CONFIRMED  (arrives after E12)
~~~

If the projector applies **every event in arrival order**, final state wrongly becomes `CONFIRMED`. With **full-state events** carrying monotonic versions, stale events (`version <= appliedVersion`) can be skipped. With **delta events** such as "increment quantity by 1," **never blindly skip gaps**: detect missing version 11 before applying version 12, or fall back to a snapshot source to rebuild accurately.

### 7.2. Neo4j Java Driver Consumer Pattern

Architectural assumptions:

1. Each event carries **full state of an Order** with `orderId`, `customerId`, `status`, `totalCents`, `aggregateVersion`.
2. The broker partitions by `orderId`; **only one active worker processes a given order at a time**. If multiple workers write the same order outside that guarantee, you must add appropriate locking/CAS; a simple version check before `SET` does not automatically prove safety under every race.
3. Neo4j already has the uniqueness constraints from section 6, and the consumer triggers no external side effects inside the callback.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public record OrderChanged(
        String eventId,
        String orderId,
        String customerId,
        String status,
        long totalCents,
        long version
) {}

public final class OrderGraphProjector {
    private final Driver driver;

    public OrderGraphProjector(Driver driver) {
        this.driver = driver;
    }

    public void apply(OrderChanged event) {
        Map<String, Object> p = Map.of(
                "eventId", event.eventId(),
                "orderId", event.orderId(),
                "customerId", event.customerId(),
                "status", event.status(),
                "totalCents", event.totalCents(),
                "version", event.version());

        try (Session session =
                driver.session(SessionConfig.forDatabase("neo4j"))) {
            session.executeWrite(tx -> {
                boolean alreadyApplied = !tx.run("""
                    MATCH (e:AppliedGraphEvent {eventId: $eventId})
                    RETURN e.eventId AS id
                    """, p).list().isEmpty();
                if (alreadyApplied) {
                    return null;
                }

                long currentVersion = tx.run("""
                    OPTIONAL MATCH (o:Order {orderId: $orderId})
                    RETURN coalesce(o.sourceVersion, -1) AS v
                    """, p).single().get("v").asLong();

                if (event.version() > currentVersion) {
                    tx.run("""
                        MERGE (c:Customer {customerId: $customerId})
                        MERGE (o:Order {orderId: $orderId})
                        SET o.status = $status,
                            o.totalCents = $totalCents,
                            o.sourceVersion = $version
                        MERGE (c)-[:PLACED]->(o)
                        """, p).consume();
                }

                // Write marker and graph updates in the SAME
                // Neo4j transaction to avoid partial writes.
                tx.run("""
                    CREATE (e:AppliedGraphEvent {
                        eventId: $eventId,
                        orderId: $orderId,
                        sourceVersion: $version,
                        appliedAt: datetime()
                    })
                    """, p).consume();
                return null;
            });
        }
    }
}
~~~

**Pattern characteristics:**

- `executeWrite` encompasses reading the marker, checking version, updating the graph, and writing the marker; commit or rollback is **a single Neo4j transaction**.
- If the driver retries the callback on a transient error, operations must tolerate re-execution. **Never publish Kafka messages, send emails, or call payment APIs** inside the callback.
- When a stale event arrives, the graph does not regress; the marker still records that the event was processed under full-state semantics.
- When **the same event** arrives again after commit, finding the marker skips reprocessing.
- **Race to handle explicitly:** if the same `eventId` is processed concurrently by two transactions, the constraint on `AppliedGraphEvent.eventId` prevents at least one transaction from committing a duplicate marker. The failed transaction rolls back and the caller re-checks the marker to distinguish a duplicate from a real failure. Never assume any exception means success.

This pattern does not completely address **deletes, customer reassignment, cross-aggregate events, schema evolution**, or **parallel writes to the same `orderId`**. Those require dedicated event handlers and appropriate keying/ordering designs. To keep the graph from accumulating infinite marker nodes, manage `AppliedGraphEvent` retention **only when** a policy guarantees older events can no longer be replayed or a safe watermark/version replacement exists.

### 7.3. Checkpointing at the Broker and in Neo4j

The sequence should be:

1. Receive event from broker.
2. Write projection **and marker** in a Neo4j transaction.
3. Only after the Neo4j transaction commits successfully, **acknowledge/commit the offset** per consumer semantics.

If the graph commit succeeds and the process crashes **before committing the offset**, the broker redelivers → markers/idempotency protect against duplicate writes. If you acknowledge **before** the graph commits and the consumer crashes, the event can be lost from processing. That is why the order must be **persist durably first, ack second**.

If a consumer reads a cursor-style CDC stream instead of broker offsets, the same rule holds: checkpoint only after the sink writes durably. **Kafka offsets** and **Neo4j CDC change identifiers** are distinct mechanisms and are not directly interchangeable.

## 8. Cross-Entity Event Ordering and Convergence

Partitioning by `orderId` preserves ordering for a single order **when producers use the same partition key and the connector/broker guarantees per-partition order**. It **does not** guarantee:

- Customer events arrive before Order events.
- Product events arrive before `CONTAINS` relationships.
- All aggregates belonging to a business flow update atomically in Neo4j.
- Event order across two partitions matches commit order across all databases.

Mitigation strategies:

| Strategy | When Useful | What to Watch Out For |
| --- | --- | --- |
| **Placeholder nodes** with logical ID | Relationship arrives before full endpoint attributes | Must backfill attributes and monitor long-lived placeholders |
| **Retry with backoff** on missing endpoint | Dependent event may arrive slightly later | Infinite retries stall queues; need a DLQ |
| **Partition by aggregate key** | Maintain event ordering for the same aggregate | Key must stay consistent across publisher/consumer |
| **Version/checkpoint** | Ignore stale updates and detect gaps | Skipping gaps is safe only for suitable full-state events |
| **Periodic reconciliation** | Repair drift after bugs/outages/retention expiry | Requires an authoritative source and efficient comparison |

**Convergence** means once the source stops emitting changes and the backlog drains, the Neo4j replica reflects the source state per contract. Proving convergence requires explicit event modeling, delete handling, versioning, and reconciliation; retries alone are not enough.

## 9. Initial Data Sync: Snapshots and Streaming Changes

A brand-new Neo4j system needs both **historical data** and changes arriving once synchronization starts.

~~~mermaid
flowchart TD
    A["Establish source sync watermark"] --> B["Read snapshot / backfill"]
    B --> C["Upsert nodes/relationships into Neo4j"]
    C --> D["Apply post-watermark events by version"]
    D --> E["Monitor lag and reconcile"]
~~~

### 9.1. Why Can't You Just "Dump First, Subscribe Later"?

~~~text
T1: Start exporting orders table
T2: Order O-901 updates at source and COMMITs
T3: Export finishes
T4: Consumer subscribes to events starting from now
~~~

If the T1 snapshot misses the T2 update and the consumer only reads events after T4, **changes between T1 and T4 are lost**.

A robust procedure:

1. Establish a replayable **CDC/outbox watermark offset**, following connector/source guidelines.
2. Take a snapshot at a consistent point or via controlled snapshot mechanics.
3. Load data by business ID along with source version.
4. Replay post-watermark events, applying **idempotency + version guards** so overlapping snapshot and stream entries never regress state.
5. Reconcile nodes, edges, versions, and business totals before opening graph APIs widely.

There is no **single universal trick** guaranteeing consistent snapshots across all RDBMS/brokers. PostgreSQL may require snapshot transactions, WAL/LSN tracking, and connector CDC algorithms; other sources use their own mechanisms. Pick a concrete strategy, document the cutover point, and test for zero lost events.

### 9.2. Backfill Using `UNWIND` and Batching

Java can read records from the source and send batches to Neo4j:

~~~cypher
UNWIND $orders AS item
MERGE (c:Customer {customerId: item.customerId})
MERGE (o:Order {orderId: item.orderId})
SET o.status = item.status,
    o.totalCents = item.totalCents,
    o.sourceVersion = item.version
MERGE (c)-[:PLACED]->(o);
~~~

This pattern **illustrates snapshot loading** when the target graph is empty or free of concurrent updates. If CDC is running concurrently, the `SET` above can **overwrite a newer version** with a stale snapshot; proper version guards/coordination must exist before running both write streams in parallel. Never let the simplicity of `UNWIND` excuse skipping ordering controls.

Each batch typically commits separately to bound transaction time, RAM, and locks. When a later batch fails, earlier committed batches do not automatically roll back. Therefore batches must be **rerunnable**, checkpointed, and accompanied by failed-record tracking.

## 10. Reading Data While Two Stores Are Out of Sync

**Eventual consistency** means the replica can **lag temporarily**, yet with clear targets and handling—not "accept being wrong forever."

### 10.1. Read-Your-Writes Example

A user creates an order in PostgreSQL, then immediately opens the order relationship page backed by Neo4j:

~~~text
T1: POST /orders -> PostgreSQL COMMITs O-901
T2: API returns 201 Created
T3: GET /graph/customers/C-101/orders -> Neo4j does not have O-901 yet
T4: Consumer processes OrderChanged
T5: GET /graph/... -> O-901 appears
~~~

You cannot use a **Neo4j bookmark** to "force" the read side to wait for a PostgreSQL commit Neo4j has not yet received; bookmarks only provide causal consistency **within Neo4j** across driver/session calls.

API design options:

| Product Requirement | Handling Approach | Trade-off |
| --- | --- | --- |
| Checkout page must show the order immediately | Read from **RDBMS source of truth** | Cannot leverage Neo4j traversal for that screen |
| Link recommendations may lag a few seconds | Read Neo4j and display `lastUpdatedAt` or "syncing" indicator | UI tolerates staleness |
| Must be visible once projection completes | Return operation ID/version; let client poll status/wait with timeout | Increases latency and complexity |
| Full-graph read needing a consistent business snapshot | Build version-watermarked materialized view or consistent batch pipeline | Bounded freshness |

**Never use a lagging graph read model to authorize zero-error transactions** such as inventory deduction or emergency access grants when the authoritative source lives elsewhere.

### 10.2. Freshness Contract

For example, an API can publish:

~~~json
{
  "customerId": "C-101",
  "relatedOrders": ["O-901", "O-902"],
  "projectionVersion": 12,
  "dataAsOf": "2026-11-25T08:12:02Z",
  "isSynchronizing": false
}
~~~

These fields are an **illustrative DTO design**, not properties automatically provided by Neo4j. If exposing `projectionVersion`, define which aggregate and checkpoint it refers to and how it is obtained; never treat order O-901's version `12` as proof that every order/customer/product has synced to that same point.

An example target: "99% of events are observable in the graph within 5 seconds of source commit." That is a **team-defined SLO**; measure `commitTime → applyTime` and account for clock skew. Never mistake it for a built-in guarantee of Neo4j or the broker.

## 11. Multiple Sources Requiring Writes: Sagas and Compensating Actions

Not every workflow is read-model replication. For example, placing an order must simultaneously:

1. Reserve stock in the Inventory Service.
2. Charge payment via the Payment Service.
3. Confirm the order in the Order Service.
4. Create related graph links if the application reads them from Neo4j.

This is a **cross-system workflow with business decisions**, commonly designed as a **Saga**:

~~~mermaid
flowchart TD
    A["Create Order: PENDING"] --> B["Reserve inventory"]
    B --> C{"Reserve OK?"}
    C -->|No| X["Cancel Order"]
    C -->|Yes| D["Charge payment"]
    D --> E{"Payment OK?"}
    E -->|No| F["Release inventory + cancel order"]
    E -->|Yes| G["Confirm order"]
    G --> H["Outbox event -> update Neo4j"]
~~~

Each step mutates its own service's store in a **local transaction**. When a later step fails, the Saga issues a **compensating action**: such as releasing reserved inventory. A compensating action is a new business operation, **not a physical rollback of an already committed transaction**.

### Saga Notes

- Require an **idempotency key** on every command, especially payments and refunds.
- Give each step explicit `PENDING/SUCCEEDED/FAILED/COMPENSATING` states, timeouts, and retry policies.
- Choose **orchestration** (a coordinator tracks state) or **choreography** (services react to events).
- Effects that occurred externally (such as bank settlement) are not always instantly reversible; design compensation and reconciliation workflows.
- Graph projection in this example should generally **not gate payment commit**: if graph sync lags, the order confirmed at the source remains valid.

If Neo4j is the **authoritative source** for an action like traversing an access-control tree, identify which **Neo4j transaction** enforces the invariant and which outcomes must be published via events; do not force it into a "projection-only" pattern.

## 12. Concurrency, Ordering, and ID Design Issues

### 12.1. Never Use `elementId` as a Cross-System ID

`elementId(n)` identifies elements within Neo4j according to version semantics; it is **not a durable business key across backups, restores, exports, or external systems**. Design nodes around `customerId`, `orderId`, `sku`, or domain-managed stable IDs backed by uniqueness constraints.

### 12.2. One Producer Must Assign Versions Under Concurrency Control

Never derive `aggregateVersion` from an application host clock. Versions must increase monotonically **per aggregate**: increment inside the RDBMS row-update transaction, or use source-appropriate sequences/compare-and-set. When multiple instances update the same order, the database must resolve write conflicts so two events never receive the same version.

### 12.3. Multi-Source Writes to the Same Property Cause Ownership Conflicts

If both the Customer Service and the Neo4j graph service can `SET o.status`, a delayed sync event can overwrite Neo4j's change. Three clean options exist:

1. **Single writer:** only one service owns `Order.status`.
2. **Split properties:** RDBMS owns `status`; Neo4j owns `graphScore` or separate analytics properties.
3. **Contracted conflict resolution:** version/vector clocks or domain-appropriate CRDT/merge rules; never blindly rely on wall-clock last-write-wins.

**Preferred default:** single writer per property/aggregate, especially for critical business state. Permitting arbitrary multi-source writes makes consistency dramatically harder to guarantee.

## 13. Failure Scenarios and Recovery Procedures

| Incident | What Can Happen | Recovery Approach |
| --- | --- | --- |
| Order Service crashes **before source commit** | Both order change and outbox roll back | Retry command using idempotency key |
| Source commit succeeds, publisher has not sent yet | Event remains in outbox | Publisher/CDC resumes and dispatches |
| Publisher sends but crashes before checkpoint | Broker receives duplicate event | Consumer deduplicates by `eventId` |
| Neo4j commits, consumer crashes before ack | Broker redelivers event | Marker/version handles duplicate safely |
| Event 12 arrives before Event 11 | Risk of regressing state when 11 arrives later | Full-state version guard; or gap detection for deltas |
| Product event delayed, Order–Product link arrives first | Missing full endpoint data | Placeholder, dependent retry, or controlled DLQ |
| Consumer down longer than broker/CDC retention | Cannot replay entire missed window | Alert, re-snapshot/backfill, and reconcile |
| Delete event arrives late | Wrong or resurrected node/relationship | Tombstone/version + clear delete policy |
| Event schema changes | Consumer fails to parse or misreads fields | Schema versioning, backward compatibility, migrations |
| Neo4j out of capacity / cluster transient outage | Backlog grows, graph API shows stale data | Backpressure, bounded retries, lag alerts, justified scaling |
| Neo4j restored from old backup | Graph loses projections after backup point | Replay from matching checkpoint or re-bootstrap; never blindly reuse stale offsets |

### 13.1. A Dead-Letter Queue Is Not a Trash Can

Events can become unprocessable due to schema mismatches, missing IDs, constraint conflicts, or conflicting data. After reasonable retries:

- Route the event along with **ID, failure cause, timestamp, and schema version** to a managed **dead-letter queue (DLQ)** or error store.
- Retain enough diagnostic detail without **exposing sensitive data**.
- Provide controlled replay tooling, ensuring consumers enforce idempotency/version checks on replay.
- Alert when DLQ size grows or backlog breaches SLOs; **never silently drop events** and claim the system is consistent.

### 13.2. Periodic Reconciliation

Even retry-enabled pipelines suffer logic bugs: mapping errors, lost events before checkpointing, missed edge deletes, or outdated schemas lingering too long. **Reconciliation** compares source and replica:

1. Pick a comparable **watermark/version** or time window.
2. Fetch order IDs/records from the source in batches.
3. Query `Order` nodes in Neo4j for `orderId` and `sourceVersion`; check status and ownership.
4. Classify **missing / stale / divergent / orphaned**.
5. Auto-repair classes with safe rules; investigate or manually resolve sensitive mismatches.

Example Cypher looking up replica state for a batch of IDs:

~~~cypher
UNWIND $orderIds AS orderId
OPTIONAL MATCH (o:Order {orderId: orderId})
OPTIONAL MATCH (c:Customer)-[:PLACED]->(o)
RETURN orderId,
       o.sourceVersion AS graphVersion,
       o.status AS graphStatus,
       collect(DISTINCT c.customerId) AS ownerIds;
~~~

If no `Order` node exists, property fields return `null`; `ownerIds` may be empty. To detect **extra** nodes in the graph absent from the source, compare a watermarked range across both sides rather than querying only IDs currently present at the source.

Reconciliation queries on large graphs need **batching, indexes, concurrency caps, and scheduling**; never run full-production scans during peak traffic.

## 14. Observability, Performance, and Security

A cross-system consistency pipeline must monitor **both transport health and data quality**.

### 14.1. Metrics to Measure

| Group | Suggested Metric | Alert When |
| --- | --- | --- |
| **Sync latency** | p50/p95/p99 of `source commit → Neo4j apply` | Exceeds SLO |
| **Backlog** | Unprocessed event count, oldest event age, consumer lag | Growing steadily or approaching retention limit |
| **Throughput** | Events/s published and applied, throughput by entity type | Apply rate lags behind source mutation rate |
| **Reliability** | Retries, timeouts, transient errors, DLQ count | Spike in errors or lingering DLQ entries |
| **Correctness** | Missing nodes, stale versions, wrong ownership, duplicate markers | Any drift exceeding threshold |
| **Neo4j** | CPU, heap/GC, page cache, DB Hits, lock waits, transaction latency | Projector degrades primary graph queries |
| **Source & broker** | Unpublished outbox rows, WAL/log retention, disk, queue depth | Events risk becoming unreplayable |

**Never report p99 solely over succeeded events while ignoring failed events.** Publish completion rates, failure counts, backlog, and wait times together; if hundreds of overdue events haven't succeeded yet, a "low applied p99" does not mean the system is healthy.

### 14.2. Optimizing the Neo4j Projector

- Use the **Neo4j Java Driver** with a shared `Driver` and per-unit `Session`; group related statements inside **`executeWrite`**.
- Create indexes/uniqueness constraints for business keys used in `MERGE`/`MATCH`.
- Batch events by business key if needed, without **breaking ordering** for the same aggregate; avoid oversized transactions.
- Use `UNWIND` to upsert multiple records when event/version semantics permit and contention is handled.
- Avoid creating relationships with no query purpose; prevent "everything connected to everything" graphs causing massive fan-out.
- On the read path, run `EXPLAIN`/`PROFILE` to inspect seeks/expands, intermediate row counts, DB Hits, and join/sort costs.

With Spring Data Neo4j, an entity graph can span many relationships; do not reload the entire aggregate per event when a targeted Cypher `MERGE`/`SET` updates the exact needed slice. If projecting via entity repositories, inspect mapping lifecycles and risks of unintended relationship overwrites.

### 14.3. Cross-System Security and Authorization

**Data stored across multiple engines = expanded attack surface.** You need:

- Separate service accounts for publisher, consumer, and API; enforce **least privilege** in RDBMS, broker, and Neo4j.
- Proper TLS for Neo4j (`neo4j+s://`/`bolt+s://`) and other links; manage secrets in a secrets manager.
- Never put card numbers, tokens, or unneeded PII into outboxes, events, or graph replicas.
- Retention policies, legal data-deletion compliance, and cross-system **delete/tombstone** propagation.
- Multi-tenant safeguards: include `tenantId` in identifier contracts, constraints, and queries; never let one tenant's events link relationships into another tenant.
- Authorize **graph traversal** queries: a link between two entities can itself be sensitive even when individual node properties are not.

## 15. Hands-On Exercise: PostgreSQL and Neo4j Managing Orders Together

**Scenario:** Order Service writes to PostgreSQL; Neo4j serves `GET /customers/{id}/related-orders`. New orders must appear in the graph within a configured lag budget, without duplicate IDs or state regression.

### Step 1 — Write the Contract

Agree on:

- PostgreSQL owns `orderId`, `customerId`, `status`, and `version`.
- `OrderChanged` events include `eventId`, `aggregateVersion`, and a sufficient snapshot.
- Neo4j writes only these synced properties via the projector; graph-specific analytics properties are owned by a separate job.
- Transactional APIs must read the source; relationship APIs may read the replica.
- Only one worker applies events for a given `orderId` at a time.

### Step 2 — Create Constraints in Neo4j

Execute the three `CREATE CONSTRAINT` statements from section 6. Verify indexes are online:

~~~cypher
SHOW INDEXES
YIELD name, labelsOrTypes, properties, state
RETURN name, labelsOrTypes, properties, state
ORDER BY name;
~~~

### Step 3 — Write Data and Outbox at the Source

Within **the same PostgreSQL transaction**, create/update the order and insert the outbox event. Verify that if the transaction rolls back, **neither the order change nor the new outbox row remains**. This verifies the source's atomicity boundary.

### Step 4 — Simulate Delivery Failures

Use an event `E-100` to test four scenarios:

1. Deliver `E-100` once: `Order` node, `PLACED` relationship, and marker exist.
2. Redeliver `E-100`: graph creates no duplicate `Order` or marker.
3. Deliver version 12 before version 11 of the same Order: state does not regress when event 11 arrives later.
4. Consumer crashes after Neo4j commit but before broker ack: replayed event is handled safely.

### Step 5 — Test Deletes and Ownership Changes

If the domain permits ownership changes:

- Emit a snapshot event with a new `customerId` and higher version.
- Verify **no old `PLACED` relationship remains** if the contract specifies one owner.
- Verify the count of incoming `PLACED` edges per `Order` is accurate, rather than relying on `MERGE` leaving old edges behind.

If orders are canceled or deleted, evaluate **soft delete** vs. **hard delete**, along with preventing stale events from recreating deleted orders.

### Step 6 — Measure Eventual Consistency

Record source commit time, broker arrival time, Neo4j commit time, and when queries observe the node. Compute percentile latencies and count errors/backlog. Pause the consumer briefly and restart it to verify the system **catches up** without exceeding retention.

### Step 7 — Reconcile

Take a batch of `orderId` values from PostgreSQL and compare `status`, `version`, `customerId`, and `PLACED` edges against Neo4j. Intentionally introduce a mismatch in the practice database and verify the reconciliation workflow detects and repairs it **to match the authoritative source**.

### Self-Check Questions

**1. Why not wrap a PostgreSQL write and a Neo4j call in `@Transactional` for cross-store atomicity?**

Because a transaction manager only coordinates resources it actually manages. Two local transactions do not automatically form an ACID distributed transaction; if one commits first, the other can still fail.

**2. Does a transactional outbox guarantee the consumer receives events exactly once?**

No. Events can be redelivered if the publisher crashes after sending and before checkpointing. Consumers must handle duplicates idempotently.

**3. Is `MERGE (o:Order {orderId:$id})` enough to stop late updates from regressing state?**

No. `MERGE` identifies nodes; it does not compare versions. You need source versions, ordering, and concurrency control.

**4. Does a Neo4j bookmark guarantee a node appears immediately after a PostgreSQL commit?**

No. Bookmarks provide causal consistency within Neo4j; they cannot make an unsynchronized event from another system arrive sooner.

**5. If event version 12 arrives before version 11, is it always safe to skip version 11?**

No. Skipping is safe only under a **full-state snapshot event** contract or equivalent mechanism. For delta events, you typically must detect gaps and recover missing events.

**6. If the Neo4j graph read model is wiped after an old restore, is restarting the consumer from the latest offset enough?**

No. The graph may miss historical source data no longer replayable from the broker. Backfill/checkpoint recovery and reconciliation are required.

## 16. Cross-System Architecture Checklist

- [ ] Designate a **system of record** per entity/relationship/property; avoid arbitrary multi-writer setups.
- [ ] Separate **source invariants** from **projection invariants**; set realistic sync-lag SLOs.
- [ ] No unprotected dual-writes across PostgreSQL, Neo4j, broker, and search.
- [ ] Use outbox/CDC aligned to **genuinely enforceable** transaction boundaries; design for duplicate delivery.
- [ ] Standardize `eventId`, `aggregateId`, `aggregateVersion`, `schemaVersion`, and payloads.
- [ ] Use **business IDs and uniqueness constraints** in Neo4j; never use internal IDs/`elementId` as cross-system keys.
- [ ] Consumers persist markers/checkpoints durably; commit offsets only after graph writes commit.
- [ ] Handle **out-of-order events**, per-aggregate concurrency, retries, DLQs, deletes/tombstones, and ownership changes.
- [ ] Initial snapshot/backfill uses a proper cutover watermark; no lost events in the overlap window.
- [ ] APIs route reads by consistency need: live transactional reads from source, graph traversals may use lagging read models.
- [ ] Design Sagas/compensation explicitly when multiple services **genuinely coordinate writes**.
- [ ] Monitor lag, errors, divergence rates, throughput, log retention, and Neo4j resources.
- [ ] Run periodic reconciliation, safe repairs, and recovery drills.
- [ ] Protect sensitive data, service accounts, encryption, multi-tenancy, and cross-system delete compliance.
- [ ] Test crashes **before/after commit**, duplicate events, out-of-order delivery, missing endpoints, and backup restores.

## References

- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Change Data Capture — Introduction](https://neo4j.com/docs/cdc/current/)
- [Neo4j Connector for Apache Kafka](https://neo4j.com/docs/kafka/current/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Microservices.io — Saga](https://microservices.io/patterns/data/saga.html)

**Conclusion:** When coordinating Neo4j with RDBMS, brokers, search, and caches, the core challenge is not merely copying records between systems—it is **designing a verifiable consistency contract**. Define the authoritative source, write outbox records inside the source transaction, apply projections inside Neo4j transactions, enforce idempotency and versioning, and measure lag alongside periodic reconciliation. For cross-system workflows with business consequences, use Sagas/compensation or supported orchestration instead of assuming local transactions will atomically commit together.
