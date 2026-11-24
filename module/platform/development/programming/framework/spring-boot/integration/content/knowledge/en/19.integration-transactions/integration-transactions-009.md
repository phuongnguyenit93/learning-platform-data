# Distinguishing Local Transactions, Distributed Transactions, and Eventual Consistency

> **Chapter:** Integration Transactions  
> **Module:** SPRING_BOOT_INTEGRATION — integrating systems in Spring Boot across HTTP clients, databases, caches, message brokers, and Spring Integration adapters.  
> **Goal:** Identify real commit boundaries, choose how to coordinate data across systems, and design error handling, deduplication, testing, and observability for integration flows.

An ordering application needs to write an order to PostgreSQL, deduct stock in another service, and then request payment. If all three succeed, the user sees the order confirmed. If writing the order succeeds yet payment fails, the system must answer: which data was committed, which data can be undone, and when will all services see the final state?

Three concepts are frequently confused:

- **Local transaction:** a unit of work committed or rolled back by a single transaction manager on a single transactional resource, typically one database.
- **Distributed transaction:** a business operation spanning multiple resources/services that require coordination. If atomic commit is needed across supporting resources, **XA/JTA with two-phase commit (2PC)** can be used; if coordinating via steps with compensation, a **Saga** is typically used with consistency designed at the business level.
- **Eventual consistency:** a **consistency model** in which replicas/services may temporarily observe different states yet converge toward the desired state once updates are propagated and processed successfully.

The first two concepts mainly describe **transaction boundaries and coordination mechanisms**; the third describes **when data across components must agree**. A Saga is a distributed business workflow pattern that typically embraces eventual consistency, whereas XA/2PC attempts to guarantee atomic commit across participating resources.

## 1. Why Do Transaction Boundaries Matter?

Consider the processing chain:

~~~mermaid
flowchart LR
    A["Order Service<br/>writes PostgreSQL"] --> B["Inventory Service<br/>HTTP call"]
    B --> C["Payment Service<br/>HTTP call"]
    C --> D["Message Broker<br/>publishes event"]
~~~

No default rollback command can simultaneously rewind a PostgreSQL transaction, an HTTP request already processed by another service, an accepted payment, and a broker-received event.

Suppose the code is:

~~~java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    orderRepository.save(new Order(command));
    inventoryClient.reserve(command); // HTTP
    paymentClient.charge(command);     // HTTP
}
~~~

If **charge** succeeds yet Order Service's database commit fails, Order Service's local transaction rolls back; the payment in Payment Service **does not automatically roll back**. If **reserve** succeeds yet the HTTP response is lost, Order Service does not know whether the other side executed or not. This is a system-boundary problem, not a missing annotation.

**Core rule:** before choosing a pattern, explicitly identify **who owns the data**, **who owns the transaction manager**, **where commit points sit**, and **which resources can participate in a shared transaction protocol**.

## 2. Local Transactions: ACID Within One Resource Boundary

A local transaction is the right fit when changes requiring atomicity reside in the same database. For example, inside Order Service:

1. Insert the **orders** row.
2. Insert **order_items** rows.
3. Deduct inventory **if inventory is also owned and updated in the same DB**.
4. Commit everything; on failure, roll back everything.

The ACID properties include:

| Property | Meaning Within One DB Transaction |
| --- | --- |
| **Atomicity** | All operations in the transaction succeed or roll back together |
| **Consistency** | Constraints and implemented rules move the DB from one valid state to another |
| **Isolation** | Concurrent transactions are isolated according to the chosen isolation level |
| **Durability** | Committed data is durably persisted per the DBMS's guarantees |

ACID does not automatically guarantee all business rules in code are correct. Choosing too weak an isolation level or omitting constraints can still cause lost updates, double bookings, and race conditions.

### 2.1. Spring Boot with Spring Data/JDBC

In Spring Boot using a JDBC/JPA transaction manager, **`@Transactional`** typically starts a transaction at the boundary of a public method called through a Spring proxy. Example of a local transaction:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final OrderItemRepository items;

    public OrderService(OrderRepository orders,
                        OrderItemRepository items) {
        this.orders = orders;
        this.items = items;
    }

    @Transactional
    public Long create(CreateOrderCommand command) {
        Order order = orders.save(
                new Order(command.customerId(), "PENDING"));
        command.lines().forEach(line ->
                items.save(new OrderItem(order.getId(),
                        line.sku(), line.quantity())));
        return order.getId();
    }
}
~~~

The entities, repositories, and command represent application models. Both repositories must use **the same transaction manager / managed data source** to share the rollback boundary. Never assume two distinct datasources will commit atomically just because they appear in one `@Transactional` method.

Notes:

- By default, Spring declarative transactions roll back on **`RuntimeException`** or **`Error`**; checked exceptions need explicit policies such as **`rollbackFor`** if rollback is desired.
- **`@Transactional`** does not take effect as expected when calling an annotated method from another method on the **same object** via self-invocation in standard proxy setups.
- In reactive R2DBC apps, use **`ReactiveTransactionManager`** and transaction-managed Publisher flows such as **`TransactionalOperator`**; reactive transactions follow Reactor Context rather than thread-bound JDBC/JPA transactions.
- Never keep a DB transaction open while waiting on slow HTTP calls: connections and locks stay held, increasing contention and complicating recovery.

### 2.2. Local Transactions Do Not Cover External Non-DB Side Effects

Example:

~~~java
@Transactional
public void completeOrder(Long orderId) {
    orders.markCompleted(orderId);     // DB change
    kafkaTemplate.send("orders", orderId.toString(), "COMPLETED");
}
~~~

Even if the database transaction rolls back, a message already received by the broker **does not disappear automatically**. Conversely, the database commit may succeed while sending the message fails. Configuring transactions separately for the Kafka producer or DB does not create a single atomic transaction spanning both. Explicitly define the coordination mechanism, guarantee boundaries, and error handling.

## 3. Distributed Transactions: One Business Request, Multiple Commit Points

A distributed transaction in the broad sense comprises multiple steps affecting independent systems. Two common strategy groups exist:

1. **Atomic distributed transaction:** coordinates commits across XA/2PC-capable resources, aiming for resource-level all-or-nothing.
2. **Business transaction / Saga:** each service commits a step locally; if a later step fails, a **compensating action** moves the business flow to an acceptable state.

Do not equate **distributed transaction** exclusively with XA. Likewise, never call a Saga an atomic rollback: Sagas expose intermediate states and compensating actions usually cannot erase all observable side effects.

### 3.1. XA/JTA and Two-Phase Commit (2PC)

In XA, a **transaction coordinator** communicates with XA-capable resource managers typically in these steps:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant TM as JTA Transaction Manager
    participant DB as XA Database
    participant JMS as XA JMS Broker
    App->>TM: begin transaction
    App->>DB: write rows
    App->>JMS: send message
    TM->>DB: prepare
    DB-->>TM: prepared
    TM->>JMS: prepare
    JMS-->>TM: prepared
    Note over TM: Commit decision if all prepare successfully
    TM->>DB: commit
    TM->>JMS: commit
    Note over TM, JMS: Recovery needed if a participant / coordinator fails
~~~

**Phase 1 — Prepare:** the coordinator asks each resource if it is ready to commit; resources may hold locks and prepared state. **Phase 2 — Commit/Rollback:** the coordinator decides and instructs each resource to execute that decision.

Prerequisites:

- A properly configured **JTA transaction manager** with recovery support.
- Participating drivers/resource managers all **support XA**, not merely local transactions.
- Application understands timeouts, network failures, and **in-doubt** states when a participant prepared without knowing the final outcome.
- Operations, monitoring, coordinator log recovery, and stuck-transaction handling are in place.

An **`@Transactional`** configuration can participate in a JTA transaction if the app truly uses a JTA transaction manager and resources enlist properly. Yet **`@Transactional`** by itself does not turn on XA for two DBs, REST APIs, Kafka, RabbitMQ, or every Spring Integration adapter.

**Critical limitation:** regular REST/HTTP is not an XA participant. Two services committing their own databases do not join a 2PC merely because service A calls service B via `WebClient` or `RestClient`. For Kafka, Spring Kafka offers Kafka-specific transaction mechanisms, which must not be assumed to form a joint XA transaction with the application's DB.

2PC can make sense when an internal system controls a few XA-capable resources and demands strict atomicity. In return, prepare/commit coordination adds latency, coupling, lock contention, and recovery burden; availability can suffer if a participant or coordinator goes down.

### 3.2. Saga: Business Transaction as a Sequence of Local Transactions

Suppose each service owns its own database:

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant I as Inventory Service
    participant P as Payment Service
    O->>O: T1: save PENDING order
    O->>I: Reserve stock (command/event)
    I->>I: T2: commit reservation
    I-->>O: StockReserved
    O->>P: Authorize payment
    P->>P: T3: commit authorization
    alt Payment authorized
        P-->>O: PaymentAuthorized
        O->>O: T4: order CONFIRMED
    else Payment rejected
        P-->>O: PaymentRejected
        O->>I: Compensate: Release stock
        I->>I: T4: commit release
        O->>O: T5: order CANCELLED
    end
~~~

T1, T2, T3... are **separate local transactions**. When a step fails on business rules, the Saga runs **compensating** steps (e.g., releasing reserved stock, refunding collected funds). Compensation cannot erase sent emails, read notifications, or already incurred external fees.

Two common orchestration styles:

| Saga Style | Coordination Mechanism | Best Fit | Primary Risk |
| --- | --- | --- | --- |
| **Choreography** | Services react to one another's business events | Short flows, simple dependencies | Hard to see global state; sprawling event dependencies |
| **Orchestration** | An orchestrator persists Saga state and sends step commands | Multi-step flows, complex timeouts and compensation | Orchestrator needs HA, state persistence, and deduplication |

A Saga needs an explicit state model, such as **PENDING → RESERVING → PAYING → CONFIRMED** or **COMPENSATING → CANCELLED**. Include idempotency, timeout handling, retries, stuck-step detection, event ordering, and manual handling when compensation fails.

## 4. Eventual Consistency: Converging After a Delay

Eventual consistency allows components to remain temporarily out of sync. Once the system stops receiving new updates and pending updates propagate and process cleanly, related replicas/states are **expected to converge**.

For example, Order Service committed **PENDING** at 10:00:00, Inventory Service reserved stock at 10:00:01, Payment Service authorized at 10:00:02, and Order Service transitioned to **CONFIRMED** at 10:00:03. During those three seconds, different services report different statuses even though the system is working as designed.

~~~mermaid
flowchart LR
    A["10:00:00<br/>Order: PENDING"] --> B["10:00:01<br/>Stock: RESERVED"]
    B --> C["10:00:02<br/>Payment: AUTHORIZED"]
    C --> D["10:00:03<br/>Order: CONFIRMED"]
~~~

**No fixed convergence window** is guaranteed solely by the word “eventual.” If events are lost, consumers fail, messages land in dead-letter queues, or compensation fails, the system may **never converge** without retries, reconciliation, and exception handling. Therefore, eventual consistency is a **design commitment requiring operational prerequisites**.

Explicitly specify:

- **Intermediate states:** APIs may return **202 Accepted** or **PENDING**, rather than reporting payment success right after recording the order.
- **Expected convergence window:** e.g., 99% of orders exit `PENDING` within a measured threshold, with alerts on overdue orders.
- **Read visibility:** what states users may read, when they may cancel, and when an outcome is considered final.
- **Conflict rules:** stale events arriving after newer events must be ignored or resolved via version/sequence checks.
- **Recovery policy:** retries, dead-letter queues, reconciliation jobs, dashboards, and administrative actions.

Eventual consistency **does not mean wrong or lost data**; it means accepting a controlled window of divergence. An individual service can still use local ACID transactions while the end-to-end workflow follows eventual consistency.

## 5. Quick Comparison of the Three Concepts

| Criterion | Local Transaction | XA/2PC Distributed Transaction | Saga Coordination & Eventual Consistency |
| --- | --- | --- | --- |
| Commit target | One resource/transaction manager | Multiple XA resources under a coordinator | Each service commits independently |
| Atomicity guarantee | Within local DB/resource scope | Aims for atomicity across XA participants per protocol/recovery | Not globally atomic; compensated at business level |
| Visibility during transitions | Per local DB isolation/commit | Typically aims for unified commit decision across participants | Intermediate states visible, with lag |
| Mid-step failures | Rolls back local transaction | Coordinator-driven recovery and in-doubt resolution | Retries, idempotency, compensation, reconciliation |
| Infrastructure dependencies | DB and transaction manager | JTA, XA-capable resources, recovery logs | Broker/HTTP, Saga state, outbox/inbox, and retries |
| Complexity | Lower within one DB | High; strict protocol compatibility needed | High in business logic and operations |
| Fits independent REST APIs | Does not cover remote effects | HTTP is normally not an XA participant | Usually a better fit |
| Example | Write `order` and `order_items` in same DB | DB + XA JMS on compatible systems | Order–Inventory–Payment via events/commands |

There is no universal best choice. If business invariants fit comfortably inside one DB transaction, keeping them local makes correctness easier to prove. When crossing multiple independent services, explicitly decide whether atomic commit is feasible or eventual progression with exception handling fits better.

## 6. Two Classic Problems When Pairing a Database with a Message Broker

### 6.1. Sending Events After Commit: Risk of Lost Events

~~~text
T1  Order Service: COMMIT order=123
T2  Process crashes
T3  Never got to PUBLISH OrderCreated
=> Database has the order, yet downstream was never notified.
~~~

Reversing the order:

~~~text
T1  PUBLISH OrderCreated succeeds
T2  Database COMMIT fails
=> Consumer processed an event for a non-existent order.
~~~

Simply publishing before or after commit does not solve atomicity between a DB and a broker when they are two independent resources.

### 6.2. Transactional Outbox: Persisting Data Changes and Event Intent Together

**Transactional Outbox** writes business state and an event row inside the **same database transaction**. Another publisher reads the outbox and sends events to the broker. Result: no committed order ever lacks a matching committed **intent to emit an event**.

~~~mermaid
flowchart LR
    A["POST /orders"] --> B["Local DB transaction"]
    B --> C["orders<br/>status=PENDING"]
    B --> D["outbox_event<br/>type=OrderCreated"]
    D --> E["Outbox publisher / CDC"]
    E --> F["Broker"]
    F --> G["Inventory consumer"]
    G --> H["Local DB transaction<br/>inbox + business data"]
~~~

PostgreSQL schema example:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_status_created
    ON outbox_event (status, created_at);
~~~

A Spring Boot service using **`JdbcTemplate`** to demonstrate an atomic local write:

~~~java
import java.util.UUID;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;

    public OrderApplicationService(JdbcTemplate jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Transactional
    public UUID placeOrder(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        // Same datasource, same local transaction:
        jdbc.update("""
                INSERT INTO orders (id, sku, quantity, status)
                VALUES (?, ?, ?, 'PENDING')
                """, orderId, sku, quantity);

        String payload = json.createObjectNode()
                .put("eventId", eventId.toString())
                .put("orderId", orderId.toString())
                .put("sku", sku)
                .put("quantity", quantity)
                .toString();

        jdbc.update("""
                INSERT INTO outbox_event
                       (id, aggregate_id, event_type, payload)
                VALUES (?, ?, 'OrderCreated', ?)
                """, eventId, orderId, payload);

        return orderId;
    }
}
~~~

When **`placeOrder`** commits, both **`orders`** and **`outbox_event`** exist. When an exception rolls back the transaction, neither exists. That is a **local transaction** guarantee, not a distributed commit with the broker. This example uses Java text blocks and PostgreSQL; the project needs Spring JDBC, PostgreSQL driver, Jackson, and matching DataSource/transaction manager setup.

The publisher can use polling or CDC:

~~~text
repeat:
    batch = claimOutboxWithLease(limit = 100)
    for event in batch:
        try:
            broker.publish(
                key = event.aggregateId,
                eventId = event.id,
                payload = event.payload
            )
            awaitBrokerAcknowledgement()
            markPublished(event.id)
        catch transientFailure:
            scheduleRetryWithBackoff(event.id)
~~~

**This is algorithmic pseudocode**, not a built-in Spring Kafka/JMS API. When multiple publishers run concurrently, implement a concurrent **claim/lease** mechanism without holding DB transactions open across network calls, and release leases if workers die. On PostgreSQL, a short transaction with **`FOR UPDATE SKIP LOCKED`** is commonly used to claim; exact implementation depends on ordering and schema requirements.

One particularly important scenario:

~~~text
Publish succeeds -> broker already received event
Publisher dies before markPublished
Publisher restarts -> re-emits the same event
=> Consumer may receive it twice.
~~~

Transactional Outbox ensures **publishing intent is saved alongside DB changes**, yet does not automatically ensure single delivery/processing across all failures. Design idempotent consumers or the Inbox pattern.

## 7. Inbox, Idempotency, and Event Ordering

With **at-least-once** delivery, an event can be redelivered. Each event needs an **`eventId`** stable across all retries and redeliveries. Consumers can store `eventId` in a **`processed_message`** table within the **same local transaction** as the business mutation:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE shipment (
    order_id UUID PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
~~~

~~~java
@Transactional
public void handleOrderCreated(UUID eventId, UUID orderId) {
    int firstTime = jdbc.update("""
            INSERT INTO processed_message (consumer_name, event_id)
            VALUES ('shipment-service', ?)
            ON CONFLICT DO NOTHING
            """, eventId);

    if (firstTime == 0) {
        return; // already processed earlier
    }

    jdbc.update("""
            INSERT INTO shipment (order_id, status)
            VALUES (?, 'NEW')
            ON CONFLICT (order_id) DO NOTHING
            """, orderId);
}
~~~

This handler illustrates PostgreSQL and must sit in a Spring bean managed by the transaction interceptor. If the transaction fails, both the processed marker and the shipment mutation roll back so broker redelivery can reprocess it. Acknowledge the message **after** the consumer transaction commits cleanly. Handle permanent business errors separately: infinitely retrying a malformed event can stall the queue.

**Idempotency keys** for order-creation requests and **`eventId`** for consumers govern two different scopes. If a client sends POST twice after a timeout, a **business request idempotency key** prevents creating two orders; an Inbox only deduplicates **emitted events** and does not automatically deduplicate inbound commands.

Event ordering is also not automatically guaranteed in every broker setup. If the same order emits **`OrderCreated`**, **`OrderConfirmed`**, and **`OrderCancelled`**, add a monotonically increasing **`aggregateVersion`** and apply only valid transitions. With Kafka, using the aggregate ID as partition key helps preserve per-partition order on healthy publish paths, yet you still must handle replays, producer retries, multiple publishers, and consumer-side version checks.

## 8. Failure Scenarios: What Actually Happens?

| Failure Point | Local Transaction | XA/2PC | Saga / Outbox & Eventual Consistency |
| --- | --- | --- | --- |
| Error before DB commit | Rolls back DB changes | Coordinator decides rollback if not yet globally committed | Local step rolls back; may retry |
| Error after DB commit, before sending event | Event can be lost without outbox | If XA resources participate, recovery follows coordinator decision | Committed outbox remains for publisher to resend |
| Event sent yet ACK lost | External side effect may have occurred | Coordinated only if resource supports XA and enlisted | Publisher may republish; consumer must deduplicate |
| HTTP timeout after partner processed it | Does not auto-rollback HTTP | Ordinary REST sits outside XA scope | Query status/idempotency before deciding retry vs. compensation |
| A Saga step fails business rules | Matching local step rolls back | If resources are XA participants, can coordinate rollback; excludes non-XA effects | Runs compensation per state machine |
| Compensating action also fails | No default global mechanism | Not applicable in Saga scenario | Persist `COMPENSATING`/`FAILED`, retry, reconcile, alert |
| Event arrives late or out of order | Outside producer transaction | XA does not resolve post-commit business ordering | Enforce via versions, state transition rules, backlog monitoring |

**You cannot assume “HTTP timeout = partner did not process it.”** The request may have reached Payment Service and written its database before the response dropped mid-network. Therefore, retrying with an **idempotency key** or querying a status endpoint by command ID is far safer than sending a brand-new unguarded charge.

## 9. Choosing an Approach for Spring Boot Integration Scenarios

### 9.1. Single Database Problem

**Requirement:** create an order with line items and update totals, all inside one PostgreSQL DB.

**Choice:** local transaction with **`@Transactional`** (JPA/JDBC) and database constraints. Consider optimistic locking/versioning or appropriate row locks for contended inventory. No Saga is needed when all invariants reside in one DB.

### 9.2. Database and Kafka/RabbitMQ Events

**Requirement:** commit an order and notify email, warehouse, or analytics; slight delivery delay is acceptable.

**Choice:** transactional outbox + publisher or CDC + idempotent consumers. Ensures events are not lost if processes crash after DB commit, while preparing for duplicate deliveries, ordering, and backlogs.

### 9.3. Multiple XA Databases in an Internal Application

**Requirement:** update two XA-capable resources requiring a joint commit decision; the organization accepts recovery overhead.

**Choice:** evaluate JTA/XA/2PC after verifying drivers/resource managers and the transaction manager. Benchmark locks, timeouts, failover, and rehearse in-doubt transaction recovery before production.

### 9.4. Order, Inventory, and Payment as Independent Microservices

**Requirement:** services own separate DBs, communicate via HTTP/brokers, and involve payments and compensation.

**Choice:** Saga with explicit states, outbox/inbox wherever reliable event emission/consumption is required, idempotent commands, conditional retries, timeouts, and compensation. Clients observe **`PENDING`** until completion.

### 9.5. Cache, Read Models, and Search Indexes

**Requirement:** update the database and refresh Redis cache or Elasticsearch.

**Choice:** the database is the source of truth; update caches/indexes via events or invalidation, tolerating stale reads within a bounded window. Caches/indexes are rarely XA participants. Set TTLs, versioning, retries, and rebuild/read-repair mechanisms as needed.

### 9.6. Spring Integration Flows

Spring Integration provides channels, adapters, endpoints, pollers, and transaction support on capable components. A poller reading DB/JMS can run within the source's transaction when configured properly. However, a **flow combining multiple adapters** does not magically become an atomic transaction spanning HTTP, Kafka, caches, and independent services. Identify the exact transaction manager and transactional capabilities of each endpoint/adapter.

## 10. Designing Contracts and Observability for Saga/Eventual Consistency

For Order–Inventory–Payment flows, event contracts should include:

| Field | Purpose |
| --- | --- |
| **`eventId`** | Deduplicates repeated deliveries of the same event |
| **`orderId` / `aggregateId`** | Identifies the business entity and partition key |
| **`sagaId` / `correlationId`** | Links logs, commands, and events of one workflow |
| **`eventType`, `schemaVersion`** | Selects handlers and interprets payload versions |
| **`aggregateVersion` / `sequence`** | Detects stale or out-of-order events |
| **`occurredAt`** | Analyzes latency; do not use alone to enforce ordering |
| **`causationId`** | Traces back to the event/command that triggered the current step |

Sample event:

~~~json
{
  "eventId": "904e9e0e-1400-4cc9-9f68-7a184900d132",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "3b3990c8-f692-466e-9fe3-90f6a1ab2a4b",
  "aggregateVersion": 1,
  "sagaId": "saga-2026-001",
  "correlationId": "req-a14f",
  "occurredAt": "2026-11-21T06:00:00Z",
  "payload": {
    "sku": "SKU-42",
    "quantity": 2
  }
}
~~~

Never place sensitive payment details, access tokens, or unnecessary PII into events. **`Trace ID`** serves distributed tracing via instrumentation; **`correlationId`/`sagaId`** are business identifiers following agreed conventions. All three can cross-reference in queries without having to be identical.

Useful operational indicators:

- **Outbox backlog:** unpublished event count, oldest age, retry counts, and lease-stuck events.
- **Consumer lag / DLQ:** processing delay, deserialization errors, poison messages, and duplicate counts.
- **Saga duration:** elapsed time from `PENDING` to `CONFIRMED`/`CANCELLED`; sagas exceeding SLA.
- **Compensation failures:** failed compensating steps, manual-review backlog, and reconciliation outcomes.
- **Business consistency checks:** `CONFIRMED` orders missing payment authorization, `CANCELLED` orders still holding stock, or published events unacknowledged downstream.

Do not measure only HTTP 200/500: an API request can return 202 successfully while the Saga gets stuck afterward. Dashboards and alerts must track the full business lifecycle.

## 11. Testing Real Failure Boundaries

To test transaction properties properly, include the following tests:

1. **Local rollback:** inside one DB transaction, force an exception after writing order and before writing items; verify zero rows committed.
2. **Outbox atomicity:** if writing outbox fails, order does not commit either; on commit, both order and outbox exist.
3. **Publisher crash:** simulate a crash after successful publish and before updating outbox; after restart, event republishes and consumer applies only one business effect.
4. **Consumer redelivery:** deliver the same `eventId` multiple times, including concurrently; constraints/inbox prevent duplicate business records.
5. **HTTP uncertain outcome:** Payment Service finishes yet client times out; retrying with the same idempotency key does not create a second charge.
6. **Compensation:** payment declines after inventory reserved; system transitions state, sends release command, and frees the exact stock; duplicate release commands remain safe.
7. **Out-of-order events:** an older-version event arrives after a newer version; consumer does not overwrite newer state with older state.
8. **Broker/DB downtime:** observe backlogs, retry backoff, DLQs, and automatic recovery without manual row edits.
9. **XA failure injection** if using 2PC: stop one participant mid-prepare/commit; verify coordinator logs, recovery, and in-doubt transactions.

Spring Boot supports integration tests against real databases and brokers via Testcontainers, combined with fake servers for HTTP timeouts/dropped responses. When using test doubles, remember that mocking HTTP success does not verify broker acks, DB commits, or production network redeliveries. Testing **failure windows between two resources** is what exposes real distributed risks.

## 12. Common Misconceptions That Cause Incidents

**“Just adding `@Transactional` keeps `WebClient` and message brokers safe.”** False: Spring transactions manage only resources actively enlisted in that transaction manager. An external HTTP service may still commit.

**“Distributed transactions always mean 2PC.”** Not every resource supports XA; Sagas coordinate distributed business transactions with different guarantees.

**“A Saga rolls back like a DB transaction.”** Compensation is a new business action. A refund does not erase the original charge record; users may have seen intermediate states.

**“Eventual consistency means any delay is fine.”** Without convergence SLAs, monitoring, retries, and reconciliation, there is no proof the system is working properly.

**“Transactional outbox guarantees exactly-once delivery.”** Publishers can resend if they crash after broker ack; you still need `eventId`, idempotent consumers, and local consumer transactions.

**“A timeout means the request never ran.”** Timeout only means the caller did not get a response in time. Remote state may have committed, requiring lookup or idempotent retries.

**“Resending the same correlation ID prevents duplicates.”** Correlation IDs trace flows; **idempotency keys** identify duplicate side-effecting commands; **`eventId`** deduplicates emitted events.

**“Adding a queue guarantees eventual consistency.”** Brokers do not fix broken business invariants, out-of-order events, DLQ messages, or failed compensations. State machines and reconciliation are required.

## 13. Decision Process for Integration Architecture

~~~mermaid
flowchart TD
    A["Do changes fit in one transactional resource?"] -->|Yes| B["Local ACID transaction<br/>constraints + isolation + proper retries"]
    A -->|No| C["Do all resources needing atomic commit<br/>support XA and coordinate cleanly?"]
    C -->|Yes, and strict atomicity needed| D["Evaluate JTA/XA/2PC<br/>recovery + timeouts + benchmarks"]
    C -->|No or unsuitable| E["Can the business use intermediate states<br/>and compensating steps?"]
    E -->|Yes| F["Saga + local transactions<br/>outbox/inbox + idempotency"]
    E -->|Not yet| G["Redesign boundaries/invariants<br/>or negotiate business requirements"]
    F --> H["Define convergence SLA,<br/>observability, and reconciliation"]
~~~

Before finalizing an approach, answer concretely:

1. **Which invariants must hold immediately?** If “never oversell remaining stock” is a hard invariant, stock reservation must be guarded locally in the inventory service via transactions/constraints or accurate concurrency control.
2. **Which system is the source of truth?** Never let two independent services simultaneously decide ownership of the same data.
3. **Are intermediate states valid?** If yes, expose them clearly in APIs/clients instead of reporting `CONFIRMED` prematurely.
4. **What happens when a step fails post-commit?** Idempotent retry, compensation, transitioning to `NEEDS_REVIEW`, or pausing for reconciliation.
5. **How does recovery work after a process crash?** Job states, outbox rows, Saga state, and pending tasks must be durably persisted.
6. **How do we prove convergence?** Through metrics, SLAs, DLQs, reconciliation jobs, and fault-injection tests.

## 14. Summary Using the Order Placement Example

Suppose a user orders two items:

- **Inside Order Service:** write **`orders`** and **`outbox_event`** in one **local transaction**. Both tables commit or roll back together.
- **Across Order–Inventory–Payment:** services own separate DBs with no shared XA transaction over REST. A **Saga** coordinates stock reservation, payment, and order confirmation; errors after reserving stock may trigger **release stock**.
- **While waiting:** Order may be **`PENDING`**, Inventory **`RESERVED`**, Payment **`PROCESSING`**. This is **intentional eventual consistency**, with expected time limits and handling when convergence stalls.
- **Across the broker:** the outbox publisher may re-emit the same event, consumers store **`eventId`** to deduplicate, and order/charge commands carry matching idempotency keys.
- **On failure:** track Saga state and correlation IDs, never guessing remote state from a timeout alone.

**Key takeaways:** local transactions deliver atomicity **within one commit boundary**; XA/2PC attempts to coordinate commits **across supporting resources**; Sagas coordinate **multiple local transactions via state and compensation**; eventual consistency describes **convergence lag and conditions** across the end-to-end flow. In Spring Boot Integration, sound design begins by mapping every boundary accurately, then layering outbox, idempotency, retries, fault testing, and observability.

## References

- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework Reference — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/)
- [Microservices.io — Pattern: Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Microservices.io — Pattern: Saga](https://microservices.io/patterns/data/saga.html)
