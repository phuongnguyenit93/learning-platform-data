# Choosing Integration Styles Based on Consistency Requirements and Coupling

## 1. The Selection Problem in Spring Boot Integration

In a **Spring Boot Integration** system, an application often needs to connect HTTP clients, databases, caches, message brokers, and Spring Integration adapters. When designing a flow such as **place order → reserve inventory → process payment → update search → send email**, picking a technology comes second. The more important questions are: **which step needs an immediate result, which states must be right at the same time, and how much are services allowed to depend on one another?**

For example, when a customer clicks "Place Order", the system might:

- Need to reply immediately that **the request has been accepted**.
- Not yet be able to confirm **paid** if the payment gateway has not confirmed.
- Guarantee **a product is not oversold beyond the quantity managed by the inventory service**.
- Allow confirmation emails and search indexes to update **after a controlled delay**.

If you chain synchronous HTTP calls for every step, a slow SMTP server can slow down the entire order request. If you push everything onto a message queue without defining intermediate states, the UI may report "success" while a critical step has not finished. Therefore, the right choice is based on **business constraints and failure characteristics**, not on which technology feels more "modern".

After this lesson, you should be able to distinguish **strong consistency from eventual consistency**, identify forms of **coupling between components**, compare common integration styles, and make decisions backed by latency, reliability, volume, and recovery requirements.

## 2. Understanding Consistency Requirements Precisely

**Data consistency** answers the question: *when must participating parties observe the same valid state, and what temporary divergence is permitted?* Do not slap a "strong consistency" label on the entire system when different flows have different requirements.

| Requirement Level | Practical Meaning | Example |
| --- | --- | --- |
| **Invariant must hold immediately in one transaction** | Related data changes must succeed or fail together within **the data-owning transaction boundary**. | Decrement available quantity and create a reservation record in the same Inventory database. |
| **Outcome must be known before replying** | The caller waits for the result of an external operation. This ensures **response** timeliness, not a cross-service ACID transaction. | Calling Inventory over HTTP to ask whether stock reservation succeeded or was rejected. |
| **Eventual consistency** | Replicas/read models may lag temporarily; once updates are delivered and processed successfully, they converge to a consistent state. | Search index receives `ProductUpdated` events a few seconds late. |
| **Periodic snapshot acceptable** | Data refreshes at scheduled checkpoints or batches. | Reporting warehouse updates nightly. |

### 2.1. Business Invariants vs. "Having an HTTP Response"

Suppose Inventory handles a reservation command inside one transaction:

1. Check available quantity.
2. Record reserved quantity and a `reservationId` row.
3. Commit or roll back together.

That is Inventory's **internal invariant**. If Order calls Inventory over REST and gets `200 OK`, Order knows Inventory reported success per the API contract; **Order's transaction is not automatically in the same transaction as Inventory**. When the network drops after Inventory commits yet before Order receives the reply, state may already have changed even though the caller sees a timeout.

This requires an **idempotency key**, an operation-lookup API by request ID, or a reconciliation flow. Blindly retrying with a new request can reserve stock twice. Even with synchronous HTTP, a timeout cannot be treated as proof that the receiver **did not** execute.

### 2.2. Eventual Consistency Must Have Measurable Bounds

"Update later" is not a clear enough requirement. Specify:

- **System of record:** who owns the authoritative state?
- **Acceptable lag:** e.g., 99% of changes appear in Search within 5 seconds—an illustrative target that must be agreed upon per product.
- **Behavior while waiting:** display "Processing", serve stale data labeled with a timestamp, or read directly from the primary source.
- **Recovery mechanism:** retries, dead-letter queues (DLQs), replays, reconciliation, and alerts when lag breaches thresholds.
- **Rules for late/out-of-order events:** check per-entity versions or update sequences.

For information affecting financial decisions, access permissions, or account balances, you sometimes must verify confirmed state directly at the primary source before proceeding. An asynchronously updated read model is unsuitable as the sole basis for every critical decision.

## 3. Understanding Coupling Between Systems

**Coupling** is not just two Java classes importing each other. In a distributed system, evaluate at least five dimensions:

| Coupling Dimension | Evaluation Question | Example |
| --- | --- | --- |
| **Temporal** | Must both sides be running simultaneously when a request arrives? | Synchronous HTTP usually requires the target service to be available immediately; a queue can hold work for consumers to process later. |
| **Contract & data** | How much does the producer know about the consumer's structures, fields, versions, and purpose? | `OrderConfirmed` is emitted under a business contract; consumers should not need to know Order's internal tables. |
| **Location / protocol** | Does the producer need the target's exact endpoint, protocol, address, or auth method? | HTTP clients need target URL/service config; broker producers need broker addresses and channel/topic names. |
| **Operational & failure** | How directly do failures, throughput, or deployments on one side impact the other? | Slow HTTP stretches request latency; slow consumers grow queue lag. |
| **Transactional** | Does one operation's commit depend on the other side committing? | Requiring transactions across two databases increases coordination, complexity, and contention. |

Messaging typically **reduces temporal coupling**, without eliminating all coupling: producers still depend on the broker, message contracts, retention policies, and duplicate/error handling. An event dumping an entire database table schema can still tightly couple consumers to internal structures.

Moreover, **coupling level** does not equal **connection count**. A small, stable, well-versioned HTTP API can be a better choice than an overly complex event pipeline when the true requirement is simply querying an immediate answer.

## 4. Comparing Major Integration Styles

| Integration Style | Typical Consistency / Freshness | Prominent Coupling | Best Fit When | Trade-Offs to Accept |
| --- | --- | --- | --- | --- |
| **Synchronous request/response: REST, gRPC** | Reads current answer from data owner; HTTP itself provides no distributed transaction. | Coupled to runtime availability, endpoints, SLAs, and API contracts. | User or business step needs immediate feedback; short queries or commands. | Timeouts, cascading failures, concurrency limits, idempotency needed on retries. |
| **Async command via queue** | Producer records request; outcome updates later. | Reduces simultaneous uptime requirement; coupled to broker and command contract. | Work can be queued, takes time, or needs burst absorption. | Must manage `PENDING` states, retries, DLQs, duplicate handling. |
| **Event publish/subscribe** | Consumers update read models or react when events fire; usually eventual. | Producer knows little about consumers; parties still share schema and event semantics. | One business event needs many independent consumers: email, analytics, search. | Harder flow tracing; ordering/replay/schema evolution must be designed. |
| **Event streaming/log** | Persists event log readable by offset; consumers build their own state. | Coupled to topics, partition keys, retention, event contracts. | Many consumers, high volume, replays or stream processing needed. | Managing partitions, lag, offsets, per-partition ordering, and replayed data. |
| **Scheduled batch/file/ETL** | Periodic state snapshots; freshness in minutes/hours/days. | Coupled to formats, exchange schedules, file drops, and reconciliation processes. | Reporting, legacy systems, high volume without real-time requirements. | Stale data between runs, batch reruns, completeness checks. |
| **CDC combined with events/outbox** | Emits DB changes after commit; consumers still converge asynchronously. | Coupled to DB/CDC logs, outbox structure, or event transformation models. | Need to bridge data-update transactions with reliable message emission. | Needs relays, lag monitoring, duplicate resolution, ordering, and error handling. |
| **Shared database/table access** | Sees fresh data quickly, without built-in ownership or stable contracts. | Tightly coupled on schemas, permissions, migrations, and DB load. | Mostly legacy systems with constraints that cannot be replaced immediately. | Schema changes break consumers; blurs ownership, security, and fault isolation. |
| **Distributed transactions XA/2PC** | Coordinates commits across supporting resources for atomicity within participants. | Very tightly coupled on transactions, connections, locks, and availability. | Special cases with platform support and atomicity that cannot be redesigned. | Latency, coordination, complex error/recovery handling; not a microservice default. |

These are **complementary tools**: a single service can use REST for operations requiring confirmation, outbox to emit `OrderConfirmed`, Kafka/RabbitMQ for consumers, and batch jobs for reconciliation. The transport alone does not determine reliability; outcomes also depend on transactions, broker acknowledgments, retries, schemas, deduplication keys, and consumer error handling.

### 4.1. Synchronous When Immediate Decisions Are Needed

For example, Order calls Inventory to reserve stock during request handling. The user may need "In Stock / Out of Stock" immediately to finish the current step. The design requires:

- API returning clear business outcomes: `RESERVED`, `REJECTED`, or an uncertain status on timeout.
- **Connect/read timeouts**, sensible connection and concurrency limits; circuit breakers/bulkheads where one service risks stalling the entire flow.
- Idempotency keys preserved across retries of **the same operation**; Inventory must also enforce deduplication.
- A recovery plan when outcomes are unknown: query `reservationId`/`requestId` or compensate if stock was reserved while Order failed to proceed.

Never confuse **synchronous** with **system-wide strong consistency**. HTTP only waits for a reply; atomicity across two services requires a dedicated strategy or redesigned data-ownership boundaries.

### 4.2. Asynchronous Commands When Results Can Arrive Later

A command such as `GenerateInvoice` sent to a queue expresses: "please perform this work". The producer can return `202 Accepted` with a tracking ID; the consumer processes it when ready. Commands should have clear business destinations and owners, with tracked status. A command is not an event: a command asks to do something; an event announces a fact **that already happened**.

Never return "invoice created" when you have only enqueued the job. Depending on needs, the system can expose polling via `GET /jobs/{id}`, callbacks, webhooks, or push status via WebSockets/SSE. Explicitly specify access permissions for job status and result retention periods.

### 4.3. Events When Scaling Multiple Independent Reactions

After Order **has committed** its confirmed state, it emits `OrderConfirmed`. Email, Search, and Analytics subscribe according to their own needs. Order does not have to call each consumer. When one consumer fails, other consumers can continue per broker mechanics.

Events should describe **meaningful business occurrences**, rather than emitting every raw SQL column change. Formats should include `eventId`, `eventType`, `aggregateId`, schema version, occurrence timestamp, and minimal necessary payload; sensitive personal data should not be broadcast indiscriminately.

## 5. Decision Flowchart Based on Consistency and Coupling

The diagram below helps kickstart design discussions. Every branch must still be validated against real transaction and error-handling requirements.

~~~mermaid
flowchart TD
    A["Need to know outcome before responding?"] -->|Yes| B{"Must data invariants be atomic?"}
    B -->|"Within one owner"| C["Keep operations in one local transaction"]
    B -->|"Across multiple owners"| D["Revisit data boundaries, saga, or special coordination"]
    C --> E["If external needed: request/response with timeout, idempotency"]
    D --> E
    A -->|No| F{"One or multiple places need to process?"}
    F -->|"One owner executes"| G["Queue command and PENDING status"]
    F -->|"Multiple subscribers"| H["Publish event after commit; pub/sub or streaming"]
    H --> I{"Need to prevent event loss between DB and broker?"}
    I -->|Yes| J["Transactional outbox + relay + consumer dedupe"]
    I -->|No| K["Re-evaluate loss/recovery commitments"]
    A -->|"Data only needed periodically"| L["Batch/ETL with reconciliation"]
~~~

Before deciding, ask business stakeholders concrete questions:

1. **Which invariants must never be violated?** Who is the single owner authorized to enforce them?
2. **Is returning `PENDING` acceptable?** If so, for how long, and where do users check the outcome?
3. **When a partner is disconnected, may requests still be accepted?** Where will the system persist commands?
4. **What are the consequences of losing a message or processing a duplicate?** Can it be compensated or reconciled?
5. **How fresh must read data be?** Measure in percentiles, peak conditions, and breach behavior.
6. **How many consumers will exist and how often will contracts change?** Who governs backward compatibility?
7. **What do normal and spike traffic look like?** Do we need backpressure, queues, or batches?

A decision is meaningful when paired with numbers, such as "stock reservation responds within the agreed latency threshold for most requests", "emails are sent within a few minutes", or "Search lag triggers an alert when exceeding SLO". Numbers must be measured against real operational needs and conditions rather than copied mechanically from examples.

## 6. End-to-End Example: Integrating an Ordering System

Suppose there are four bounded contexts: `Order` (owns order state), `Inventory` (owns stock), `Payment` (manages payments with providers), and `Notification/Search` (updates derived data).

~~~mermaid
flowchart LR
    U["User"] --> O["Order API"]
    O -->|"HTTP reserve / immediate reply"| I["Inventory"]
    O -->|"Transaction: Order + outbox"| DB[("Order DB")]
    DB --> R["Outbox relay"]
    R --> MQ[("Broker")]
    MQ -->|"OrderConfirmed"| N["Notification"]
    MQ -->|"OrderConfirmed"| S["Search read model"]
    O <-->|"Payment request/result or PENDING state"| P["Payment"]
~~~

| Step | Required Consistency | Reasonable Integration Style | On Failure |
| --- | --- | --- | --- |
| Reserve stock | Inventory must prevent overselling; UI wants early feedback. | Transaction inside Inventory; Order calls synchronous HTTP with idempotency key. | On timeout, query status or execute proper compensation. |
| Accept order | Order creates a durable `PENDING` record and returns order ID. | Local transaction in Order. | Never return completed state before commit. |
| Payment | Must never mark `PAID` without reliable confirmation; callbacks may lag or repeat. | Call synchronous API if immediate state transition is required; callbacks/events and reconciliation finalize state. | Keep `PAYMENT_PENDING` or verification-needed state; never infer failure from timeout. |
| Send email | Important notifications must not be lost, though delay is allowed. | `OrderConfirmed` via outbox + broker + email consumer. | Backoff retries, DLQ, status lookup, and duplicate handling. |
| Update Search | Index may lag; Order remains source of truth. | Event streaming/pub-sub to consumer updating read model. | Enforce ordering/versioning, measure lag, and rebuild when needed. |
| Daily reports | Real-time per-transaction updates unnecessary. | Scheduled batch/ETL and aggregate reconciliation. | Rerun batch by key/id; verify row counts and totals. |

A reliable flow does not have to force Order + Inventory + Payment + SMTP into **one distributed transaction**. For long-running steps or external organizations, a **saga** with intermediate states and compensating actions usually fits better:

- Stock reserved yet payment fails: issue a cancellation command for the specific `reservationId`.
- Payment has an unknown outcome: verify with the provider by idempotency key before deciding to charge again.
- A refund is a **compensating business transaction**, not an instant rollback of an already-settled charge.
- If cancelling a reservation times out, track cancellation until confirmed or rely on reservation expiration.

## 7. Implementing a Synchronous Integration Point in Spring Boot

Spring Boot 3.2+ supports `RestClient` for synchronous HTTP calls. The example below illustrates calling Inventory; URLs and timeouts are sample values that must match your latency budget and partner capacity.

~~~java
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class InventoryHttpConfig {
    @Bean
    RestClient inventoryRestClient(
            RestClient.Builder builder,
            @Value("${inventory.base-url}") String baseUrl) {
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1_000);
        factory.setReadTimeout(1_500);
        return builder.requestFactory(factory)
                .baseUrl(baseUrl)
                .build();
    }
}

record ReserveStock(
        UUID orderId, UUID orderLineId, String sku, int quantity) {}

record ReservationReply(String reservationId, boolean accepted) {}

class InventoryClient {
    private final RestClient client;

    InventoryClient(RestClient inventoryRestClient) {
        this.client = inventoryRestClient;
    }

    ReservationReply reserve(ReserveStock request) {
        String key = request.orderId() + ":reserve:" + request.orderLineId();
        return client.post()
                .uri("/reservations")
                .header("Idempotency-Key", key)
                .body(request)
                .retrieve()
                .body(ReservationReply.class);
    }
}
~~~

The application must explicitly handle `.body(...)` returning `null`, `4xx/5xx` responses, and I/O exceptions; never assume every error is retryable. Business rejection codes (out of stock) differ from network errors. **Idempotency-Key** only works if Inventory persists and reuses results for the same key/scope, defines retention, and detects payload conflicts. Callers must preserve the same key when retrying the same operation.

To keep one failure point from cascading, configure timeouts, cap connection pools or concurrency, monitor timeout rates, and allocate latency budgets from the outer API down into internal steps. For deep call chains or high concurrency, you can use `WebClient` and reactive programming, though being reactive **does not change** the fundamental dependency on the response outcome.

## 8. Emitting Events After Commit: Transactional Outbox

A common problem is the **dual write**:

~~~text
1. Commit order into database.
2. Publish OrderConfirmed to broker.
~~~

If the process crashes between the two steps, Order is committed with no event. Reversing the order is unsafe too: the broker receives the event before the database commits; the DB transaction may roll back afterward.

**Transactional outbox** closes this gap by writing **business data and an outbox record in the same single-database transaction**:

~~~sql
BEGIN;

INSERT INTO orders (id, customer_id, status)
VALUES (:orderId, :customerId, 'CONFIRMED');

INSERT INTO outbox_events
    (event_id, aggregate_id, event_type, schema_version, payload_json, created_at)
VALUES
    (:eventId, :orderId, 'OrderConfirmed', 1, :payloadJson, CURRENT_TIMESTAMP);

COMMIT;
~~~

This is illustrative SQL with named parameters, assuming the tables and constraints are defined. In Spring Boot, use `@Transactional` to write Order and Outbox through the same transaction manager/datasource. After commit, a relay reads the outbox and publishes to the broker; the relay can poll or use CDC on the outbox table.

~~~mermaid
sequenceDiagram
    participant API as Order Service
    participant DB as Order DB
    participant Relay as Outbox Relay
    participant Broker as Broker
    participant Consumer as Search Consumer
    API->>DB: Transaction: update Order + insert Outbox
    DB-->>API: Commit
    Relay->>DB: Read unpublished events
    DB-->>Relay: OrderConfirmed
    Relay->>Broker: Publish event
    Broker-->>Relay: Ack per broker mechanism
    Relay->>DB: Mark as published
    Broker->>Consumer: Deliver event
    Consumer->>Consumer: Process idempotently
~~~

Key points to remember:

- Outbox ensures **the intended event record commits alongside** the Order change; it **does not** guarantee the publisher emits only once.
- If the relay publishes successfully and crashes before marking sent, the event may be resent. Consumers must handle duplicates.
- With multiple relays or aggregates, use claiming/locking, retry management, and proper ordering by **aggregate key** when required by business rules.
- Outbox does not replace broker durability confirms; configure publish confirms/acks matching your broker and never mark published before receiving the required confirmation.
- Monitor the age of the oldest unpublished outbox row, retry counts, publish failure rates, and cleanup policies once reconciliation is assured.

### 8.1. Event Contracts and Version Compatibility

Example `OrderConfirmed` contract:

~~~json
{
  "eventId": "a3d5a426-ef0a-4e82-a5dd-2c1ef303c7c9",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "aggregateId": "o-123",
  "occurredAt": "2026-11-20T03:30:00Z",
  "payload": {
    "orderId": "o-123",
    "customerId": "c-456"
  }
}
~~~

An event must reflect an actual occurrence and have a unique ID for deduplication. When evolving schemas, prefer adding optional fields, preserving existing field meanings, and testing compatibility with active consumers. For breaking changes, plan version bumps and consumer migrations. Timestamps aid observability yet **are insufficient** for strict ordering across producers; add a monotonically increasing per-aggregate version if consumer logic depends on ordering.

### 8.2. Idempotent Consumers and "Effectively Once" Outcomes

Many brokers deliver with **at-least-once delivery** under retries; duplicate deliveries are normal. One control is an inbox table with a unique key on `(consumer_name, event_id)`, performing **processed-marker insertion and business data updates inside the same local transaction**.

Illustrative PostgreSQL thinking:

~~~sql
BEGIN;

INSERT INTO consumer_inbox (consumer_name, event_id)
VALUES ('search-indexer', :eventId)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Only when INSERT actually added 1 row:
--   update local data or create the corresponding indexing task.
-- If 0 rows: event was received earlier; skip duplicate side effects.

COMMIT;
~~~

In real code, inspect the affected row count and keep updates in the same transaction; define the unique constraint in the database. If the final effect targets a system **outside** that transaction (e.g., sending email), the local inbox alone does not guarantee sending only one email: add target-side idempotency, delivery status tracking, and reconciliation by stable key. Say **"business effects processed once within designed constraint boundaries"** rather than assuming every broker delivers end-to-end exactly-once.

## 9. Where Spring Integration Fits in the Choice Landscape

**Spring Integration** provides Enterprise Integration Patterns such as `MessageChannel`, `Gateway`, `Transformer`, `Router`, `Filter`, `Service Activator`, and external system adapters. They help structure processing into clear-contract steps, wire endpoints, and observe flows.

For instance, an event from a broker might pass through:

~~~mermaid
flowchart LR
    A["Inbound broker adapter"] --> B["MessageChannel"]
    B --> C["Filter schema/version"]
    C --> D["Transformer to internal command"]
    D --> E["Service Activator"]
    E --> F[("Database / SMTP / API")]
    C -->|"invalid"| X["Error channel / DLQ policy"]
~~~

However, patterns like channels or routers **do not automatically merge two databases into one transaction**. Examine closely:

- Where transactions start and end across inbound adapters, data processing, and broker acks.
- Behavior of `retry`, `errorChannel`, DLQs, and handling repeated deliveries of a message.
- Synchronous vs. asynchronous channels: `DirectChannel` invokes handlers on the same call stack, while `ExecutorChannel` hands work to an executor; this changes transaction and thread context.
- Message headers such as correlation IDs, trace IDs, tenants, and versions must be managed explicitly, avoiding forwarding unnecessary sensitive data.

Similarly, using a cache like Redis to speed up reads **does not naturally keep data consistent** with the database. Pick cache-aside, write-through, or invalidation, TTLs, and refresh policies aligned with acceptable staleness. A cache should not be the sole basis for critical invariants without an appropriate synchronization design.

## 10. Failure Scenarios to Design Upfront

| Scenario | Affected Integration Style | Mitigation |
| --- | --- | --- |
| HTTP timeout **after** receiver commits | Request/response | Use idempotency keys, status lookup APIs, reconcile before retrying. |
| One slow dependency exhausts workers/threads | HTTP, JDBC | Timeouts, connection pools, bulkheads, circuit breakers; monitor timeouts and saturation. |
| Broker temporarily unavailable | Queue, pub/sub, streaming | Durable storage/buffering within limits, outbox, backoff retries, backlog monitoring. |
| Message delivered multiple times | Queue, pub/sub, streaming | Deduplicate by event ID in a local transaction; design idempotent handlers. |
| Messages arrive out of order | Multiple consumers, partitions, retries | Proper key/partitioning, per-aggregate versions, ignore stale updates or reconcile. |
| Consumer cannot parse new schema | Event/API contract | Contract tests, compatibility rules, versioning, and ordered rollouts. |
| Search/cache updates lag behind | Read model/cache | Lag metrics, TTL/invalidation, read from source of truth when freshness is mandatory. |
| Batch reruns or fails halfway | Batch/ETL | Checkpoints, idempotent upserts, batch locks, row/total validation, per-item error logs. |
| Saga stalls mid-flow | Orchestration/choreography | Business timeouts, retries, compensating actions, alerts, and manual intervention tools. |

When reviewing an architecture, do not test only the happy path. Failures between committed and uncommitted steps reveal real coupling constraints and consistency limits.

## 11. Testing, Observability, and Acceptance Criteria

A good integration choice must be verifiable using operational telemetry. Metric groups should include:

- **Synchronous:** p95/p99 latency, timeout rates, errors by HTTP/business code, retry rates, connection pool saturation, and queued requests.
- **Messaging:** queue depth, consumer lag, oldest message/outbox age, redelivery counts, retries, DLQ depth, duplicate rates, and time to completion.
- **Data:** reconciliation mismatch counts, read-model lag, schema/serialization error counts, and updates skipped due to stale versions.
- **Business:** rate of Orders stuck in `PENDING` past deadlines, unreleased reservations, unreconciled payments, and emails missed within SLA windows.

Combine trace IDs/correlation IDs across HTTP, outbox, and brokers, while keeping **request IDs**, **operation idempotency keys**, **event IDs**, and **aggregate IDs** distinct: they have different lifecycles and purposes. Metrics and logs should trace an order ID across the entire pipeline without logging payment cards, tokens, or secrets.

High-value test cases:

1. **Lost response after Inventory commit:** retrying with the same idempotency key does not reserve twice.
2. **Order commits, relay dies before publish:** restarting still emits the event.
3. **Publish succeeds, relay dies before marking done:** event may repeat, yet the consumer applies no duplicate side effects.
4. **Consumer receives newer event before older event:** read model is not overwritten by a lower version.
5. **Broker stops for a few minutes:** requests preserve committed state; backlog drains once the broker recovers.
6. **Schema evolution:** older consumers still process messages under the agreed compatibility policy.
7. **Batch rerun:** aggregated totals are not doubled, with reconciliation output verified.

Tests must cover network errors, process crashes, duplicate messages, and transaction rollbacks; mocking a method to return `true` does not prove protocol or database guarantees.

## 12. Summary of How to Choose

First, **identify invariants** and keep changes requiring atomicity under one owner within one transaction boundary whenever possible. Next, determine **when the user must know the outcome**: if immediately, use request/response with timeouts and idempotency; if waiting is acceptable, asynchronous commands with trackable status reduce temporal coupling. When multiple parties must react to a committed business fact, use **events** with stable contracts. When events must never be lost between a database and a broker, apply an **outbox** and idempotent consumers. When data freshness is only needed periodically, simple **batch** jobs can make more sense than continuous streaming.

After choosing the integration style, you still must design **data contracts, transactions, retries, duplicates, errors, observability, and recovery tests**. Those decisions are what determine whether a Spring Boot system maintains required consistency and genuinely reduces operational coupling.
