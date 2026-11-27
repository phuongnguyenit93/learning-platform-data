# Outbox as a Way to Decouple the Business Transaction from Transport

## 1. The Problem: Business Update Succeeds, Yet the Event Never Reaches the Broker

A sales application has this workflow:

1. Save order `order-501` to the database.
2. Publish the `OrderCreated` event to the message broker.
3. Inventory, email, and accounting systems consume the event.

If the application simply runs two consecutive calls, there are two failure windows:

~~~java
// Intentionally unsafe example; DO NOT use in production.
orderRepository.save(order);
brokerClient.send(orderCreatedEvent);
~~~

- **Database commit succeeds, broker send fails:** the order exists, yet other systems never receive the event.
- **Broker send succeeds, database rolls back:** other systems see an event for an order that never committed.

Reversing the order of the two calls does not solve both cases. Putting the network call inside `@Transactional` also does not automatically enlist the broker in the database transaction. The **Transactional Outbox** solution decouples the **business transaction** from **transport** by saving the event into an outbox table **in the same local transaction** as business data, then publishing the event externally in an asynchronous step.

In the **SPRING_INTEGRATION_PATTERN** module, this technique supports designing Enterprise Integration Patterns with Spring Integration: Router, Filter, Transformer, Splitter, Aggregator, Gateway, error channels, retries, and correlation. An outbox is not a special `MessageChannel`; it is an **architectural pattern at the transaction boundary** that IntegrationFlows can utilize.

### Objectives After This Lesson

- Explain why saving the order and outbox record in the same transaction prevents **business commit without send intent**.
- Design a relay that reads the outbox and sends to transport once the database has committed.
- Accurately identify **at-least-once**, duplicate, crash, retry, and ordering risks.
- Understand the roles of Spring Integration, Spring Transaction, schedulers, error channels, and idempotent consumers.
- Write tests covering rollback, publish success/failure, restarts, and multiple workers.

## 2. Architecture Flow of the Transactional Outbox

~~~mermaid
flowchart LR
    A[API / Gateway] --> B[Order Application Service]
    B --> T["Local DB transaction"]
    T --> O[(orders)]
    T --> X[(integration_outbox)]
    X --> R["Outbox Relay / Dispatcher"]
    R --> I["Spring Integration Flow"]
    I --> K[Broker / Transport]
    K --> C[Consumer]
    C --> N[(Consumer Inbox + Business DB)]
    R -. "Retry / error handling" .-> X
~~~

**Transaction A — Business write:**

~~~text
BEGIN
  INSERT / UPDATE orders ...
  INSERT integration_outbox(eventId, aggregateId, payload, PENDING) ...
COMMIT
~~~

Both records commit together or roll back together, provided they genuinely use **the same database and the same transaction manager/resource**.

**Process B — Outbox relay:** a worker reads committed pending records, sends them to the transport, and records the send outcome. Sending to the broker **is not inside Transaction A**; there is no need to hold the order transaction open waiting on the network.

**Process C — Consumer:** reads events from transport, runs its own business logic, and has a mechanism to detect duplicate events.

### What Does the Outbox Guarantee and Not Guarantee?

| Property | Transactional Outbox |
| --- | --- |
| Business row and outbox row commit/roll back together | **Yes**, when in the same local transaction |
| API must wait for the broker to be up before committing the order | **No** |
| Event persists durably before sending | **Yes**, after outbox commits to a durable DB |
| Broker always receives immediately | **No**; there is relay latency and backlog |
| Emits strictly once under all circumstances | **No**; crashes can cause the relay to resend |
| Consumer automatically prevents duplicate processing | **No**; idempotency/inbox must be designed |
| Event ordering across all aggregates is always preserved | **No**; ordering/partition policies are needed |

Core point: Outbox solves **atomicity between business changes and the “to-publish” record**, rather than using one global transaction spanning the database, broker, and every consumer.

## 3. Comparing Outbox with Common Pitfalls

| Approach | Problem |
| --- | --- |
| `save()` then `broker.send()` outside transaction | DB succeeds, send failure loses the event |
| `broker.send()` then `save()` | Can emit events when DB never commits |
| `@Transactional` wrapping both `save()` and `send()` | A JDBC transaction cannot roll back an already-succeeded broker send |
| `@TransactionalEventListener(AFTER_COMMIT)` calling broker directly | Callback may not run if process dies right after commit; not a durable outbox |
| Outbox row in same transaction, separate relay | After commit, a pending event record exists; relay can retry on transport errors |

**Note:** `@TransactionalEventListener` is still helpful to wake the worker after commit to reduce latency, **yet the outbox record is the durable source of truth**. Never rely solely on an in-RAM callback to guarantee event publishing when the application can crash.

## 4. Data Schema Design

The example below uses **PostgreSQL** to illustrate multi-worker claiming with `FOR UPDATE SKIP LOCKED`. On MySQL, SQL Server, or other databases, claim/lock syntax differs; adjust for your actual DBMS.

~~~sql
CREATE TABLE orders (
    order_id      text PRIMARY KEY,
    status        text NOT NULL,
    total_cents   bigint NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE integration_outbox (
    id               bigserial PRIMARY KEY,
    event_id         uuid NOT NULL UNIQUE,
    aggregate_id     text NOT NULL,
    event_type       text NOT NULL,
    payload_json     jsonb NOT NULL,
    status           text NOT NULL DEFAULT 'PENDING',
    attempts         integer NOT NULL DEFAULT 0,
    next_attempt_at  timestamptz NOT NULL DEFAULT now(),
    claim_token      uuid,
    lease_until      timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    published_at     timestamptz,
    last_error       text,
    CONSTRAINT outbox_status_check
        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'PUBLISHED', 'FAILED'))
);

CREATE INDEX outbox_pending_idx
    ON integration_outbox (status, next_attempt_at, id);

CREATE INDEX outbox_aggregate_idx
    ON integration_outbox (aggregate_id, id);
~~~

**Meaning of key columns:**

| Column | Meaning |
| --- | --- |
| `event_id` | Stable business event ID; consumer uses it for deduplication |
| `aggregate_id` | Business entity key, e.g., `order-501`; often used as routing/partition key |
| `event_type` | Event type, helping Routers select processing branches |
| `payload_json` | Event data decoupled from Java objects living in RAM |
| `status` | Relay status: `PENDING`, `IN_FLIGHT`, `PUBLISHED`, or `FAILED` |
| `attempts` | Number of times the relay has **claimed to attempt publishing** |
| `next_attempt_at` | Do not pick up the message before the next retry timestamp |
| `claim_token`, `lease_until` | Prevents two workers from actively owning one record during the lease window |
| `published_at` | Timestamp when relay confirmed transport acceptance per contract |
| `last_error` | Sanitized error summary; never store credentials or sensitive data |

The unique constraint on `event_id` prevents two outbox records with **the same event ID** in one database, yet does not prevent **one record from being sent multiple times** when the relay retries.

### State Lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Business transaction commits
    PENDING --> IN_FLIGHT: Relay claims
    IN_FLIGHT --> PUBLISHED: Broker ACKs and status updated
    IN_FLIGHT --> PENDING: Transient error + backoff
    IN_FLIGHT --> FAILED: Permanent error / retry budget exhausted
    IN_FLIGHT --> IN_FLIGHT: Lease expired, another worker reclaims
    FAILED --> PENDING: Controlled manual replay
~~~

When a worker is killed while `IN_FLIGHT`, records must have a **lease expiration** mechanism so another worker can reclaim them. Setting `PROCESSING` permanently without leases/reconciliation risks wedging the outbox after a crash.

## 5. Producer: Saving Business Data and Outbox in **the Same** Transaction

A Spring JDBC example making the transaction boundary clear. `@Transactional` must apply to a method called through a Spring proxy, using the same `DataSource`/transaction manager as the JDBC operations.

~~~java
import java.util.Map;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
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
    public UUID createOrder(String orderId, long totalCents) {
        UUID eventId = UUID.randomUUID();

        String payload;
        try {
            payload = json.writeValueAsString(Map.of(
                    "eventId", eventId.toString(),
                    "orderId", orderId,
                    "totalCents", totalCents));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize OrderCreated", ex);
        }

        jdbc.update(
                "INSERT INTO orders(order_id, status, total_cents) " +
                "VALUES (?, 'CREATED', ?)",
                orderId, totalCents);

        jdbc.update(
                "INSERT INTO integration_outbox " +
                "(event_id, aggregate_id, event_type, payload_json) " +
                "VALUES (?, ?, 'OrderCreated', CAST(? AS jsonb))",
                eventId, orderId, payload);

        return eventId;
    }
}
~~~

On a successful call, the DB contains both the order and a `PENDING` outbox row. If the outbox insert throws and rolls back the transaction, the order row also rolls back. If the order write fails, the outbox row is never committed.

**Mandatory conditions:**

- `DataSource` and transaction manager are configured; Spring JDBC joins the same transaction.
- Do not use `REQUIRES_NEW` solely for the outbox insert if both changes must always commit/roll back together.
- Do not invoke `createOrder(...)` via self-invocation inside the same bean assuming `@Transactional` will apply.
- Do not swallow exceptions letting the transaction commit; if catching intentionally, enforce clear rollback policies.
- For business logic needing to avoid creating two orders from a retried API request, add a **request idempotency key** or unique constraint at the order layer. That is a separate concern from outbox relay duplicate publishing.

### Never Publish Messages Directly Inside That Transaction

~~~java
@Transactional
public void unsafeCreateAndPublish(...) {
    // Write to database...
    // brokerClient.send(...); // Does not make it atomic with JDBC.
}
~~~

A successful broker send followed by a database rollback still emits false events. With Outbox, `createOrder` only writes to the DB, while sending to the broker belongs to the relay **after commit**.

## 6. Relay: Claim → Publish → Mark

A relay can run via polling, CDC, or an event-driven worker. With polling, the standard lifecycle is:

1. **Claim** a number of `PENDING` records whose send time has arrived (plus `IN_FLIGHT` records with expired leases).
2. Commit the claim transaction **before making network calls**.
3. Send to the broker/transport with a stable `eventId`.
4. Wait for an **appropriate transport ACK**, not merely an async call returning.
5. Record `PUBLISHED`; on error, reset status and `next_attempt_at`.

~~~mermaid
sequenceDiagram
    participant R as Relay
    participant DB as Outbox DB
    participant B as Broker
    R->>DB: Claim 1 row and commit lease
    DB-->>R: Event + claimToken
    R->>B: Publish(eventId, aggregateId, payload)
    alt Broker confirms
      B-->>R: ACK
      R->>DB: Mark PUBLISHED if claimToken is still valid
    else Broker error / timeout
      B--xR: Error or uncertain state
      R->>DB: Reschedule retry with backoff
    end
~~~

### 6.1. Claim SQL for Multiple Relay Workers

The illustrative PostgreSQL query below runs in **one short transaction**, with `:claimToken` as a fresh UUID per claim and one record at a time:

~~~sql
WITH picked AS (
    SELECT id
    FROM integration_outbox
    WHERE (status = 'PENDING' AND next_attempt_at <= now())
       OR (status = 'IN_FLIGHT' AND lease_until <= now())
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE integration_outbox AS o
SET status = 'IN_FLIGHT',
    claim_token = :claimToken,
    lease_until = now() + interval '60 seconds',
    attempts = attempts + 1
FROM picked
WHERE o.id = picked.id
RETURNING o.id, o.event_id, o.aggregate_id,
          o.event_type, o.payload_json, o.attempts, o.claim_token;
~~~

`FOR UPDATE SKIP LOCKED` reduces contention when two claim transactions run concurrently. `claim_token` acts as a **fencing condition** for subsequent updates; it cannot stop a slow old worker from actually sending a duplicate if the network/scheduler stalled and the lease expired.

**Important:** a 60-second lease is purely illustrative. Pick a lease longer than reasonable timeout/ACK durations or implement lease renewal; if a worker takes longer than the lease to send, another worker can reclaim and send a duplicate. With multi-instance relays, verify concurrency against a real database.

### 6.2. Marking After ACK Using Ownership Token

~~~sql
UPDATE integration_outbox
SET status = 'PUBLISHED',
    published_at = now(),
    claim_token = NULL,
    lease_until = NULL,
    last_error = NULL
WHERE id = :id
  AND status = 'IN_FLIGHT'
  AND claim_token = :claimToken;
~~~

If the update affects **0 rows**, the lease may have expired and another worker reclaimed it. Never conclude the event definitely did not reach the broker; check ownership/metrics and rely on consumer idempotency.

### 6.3. Transient Error: Scheduling Retry

~~~sql
UPDATE integration_outbox
SET status = 'PENDING',
    next_attempt_at = now() + interval '15 seconds',
    claim_token = NULL,
    lease_until = NULL,
    last_error = :safeErrorSummary
WHERE id = :id
  AND status = 'IN_FLIGHT'
  AND claim_token = :claimToken;
~~~

This uses a fixed 15-second backoff for illustration. In production, use exponential backoff with jitter, bounded attempt counts, and business deadlines; once limits are exceeded or data errors are permanent, transition to `FAILED` and alert/quarantine rather than looping endlessly.

**Never hold a database transaction open while waiting for a broker ACK.** A worker can take seconds to send an event. Holding row locks across network calls increases contention, stretches transactions, and can stall the database.

## 7. Relay Worker and Spring Integration Boundaries

Spring can run the relay via `@Scheduled`, a poller, or an operationally triggered worker. The example below shows **orchestration**, with repository and transport encapsulating SQL/network:

~~~java
import java.util.Optional;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

record OutboxEvent(
        long id,
        java.util.UUID eventId,
        String aggregateId,
        String eventType,
        String payloadJson,
        int attempts,
        java.util.UUID claimToken) {
}

interface OutboxRepository {
    // claimNext(): short DB transaction, commits lease before returning.
    Optional<OutboxEvent> claimNext();
    void markPublished(OutboxEvent event);
    void scheduleRetryOrFail(OutboxEvent event, Exception failure);
}

interface OutboxTransport {
    // Returns only after transport confirms per chosen contract.
    // Do not merely enqueue async in RAM and treat publish as succeeded.
    void publishAndAwaitAck(OutboxEvent event) throws Exception;
}

@Component
class OutboxRelay {
    private final OutboxRepository repository;
    private final OutboxTransport transport;

    OutboxRelay(OutboxRepository repository, OutboxTransport transport) {
        this.repository = repository;
        this.transport = transport;
    }

    @Scheduled(fixedDelay = 1_000)
    public void poll() {
        for (int i = 0; i < 20; i++) {
            Optional<OutboxEvent> candidate = repository.claimNext();
            if (candidate.isEmpty()) {
                return;
            }
            publishOne(candidate.get());
        }
    }

    private void publishOne(OutboxEvent event) {
        try {
            transport.publishAndAwaitAck(event);
        } catch (Exception failure) {
            repository.scheduleRetryOrFail(event, failure);
            return;
        }
        // If this update fails after broker ACK, relay may resend
        // when lease expires. Consumer must be idempotent.
        repository.markPublished(event);
    }
}
~~~

This is an **architectural example**, not a standalone runnable app: implement `OutboxRepository` with the SQL from section 6, `OutboxTransport` with your broker, enable scheduling for `@Scheduled`, and configure transactions, logging, and testing. Never execute network calls inside `claimNext()` while a transaction is open.

### Where Does Spring Integration Fit?

The relay can call a `DirectChannel`, and an IntegrationFlow routes the message to an adapter. Mark `PUBLISHED` only if the endpoint's contract genuinely guarantees the desired ACK:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class OutboxTransportIntegrationConfig {

    @Bean("outbox.transport")
    MessageChannel outboxTransportChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow outboxTransportFlow(BrokerClient broker) {
        return IntegrationFlow.from("outbox.transport")
                .handle(OutboxEvent.class, (event, headers) -> {
                    broker.sendAndAwaitAck(
                            event.aggregateId(),
                            event.eventId().toString(),
                            event.eventType(),
                            event.payloadJson());
                    return null;
                })
                .get();
    }
}

// Illustrative contract; real implementation uses Kafka/Rabbit/JMS/etc.
interface BrokerClient {
    void sendAndAwaitAck(String key, String eventId,
                         String type, String jsonPayload);
}
~~~

In this example, `DirectChannel` runs the handler synchronously; `sendAndAwaitAck` **must genuinely wait for transport confirmation** and throw an exception when valid confirmation is absent. If replaced with an `ExecutorChannel`/`QueueChannel` or an adapter that only enqueues into an internal buffer, `send() == true` **does not prove the broker received it**. In that case, do not mark the outbox `PUBLISHED` solely on channel send success.

If transport returns an ambiguous ACK (e.g., timeout after the broker already received it), let the relay retry with **the same event ID**, without creating a new event ID. Spring Integration's error channel can record errors; **outbox status + retry scheduling** itself decides when to replay. Do not let both an error flow and a dispatcher requeue independently without a single clear retry owner.

### EIP Roles in the Relay

| Pattern | Role in Outbox |
| --- | --- |
| **Filter** | Skip events no longer valid if business policy permits; explicitly record status |
| **Transformer** | Convert outbox record into transport message and headers with schema version |
| **Router** | Select topic/queue by `event_type` or tenant |
| **Service Activator** | Send to broker, process ACK, throw on failure |
| **Retry/error channel** | Handle publish errors and direct retry/quarantine |
| **Correlation** | Use `eventId`, `aggregateId`, and trace ID to link logs |
| **Aggregator** | Collect downstream results if business requires; not a mandatory outbox component |

## 8. Crash Windows: Why Is Outbox Typically At-Least-Once?

Suppose the relay is sending `evt-501`:

~~~mermaid
sequenceDiagram
    participant D as Database
    participant R as Relay
    participant B as Broker
    participant C as Consumer
    R->>D: Claim evt-501
    R->>B: Publish evt-501
    B-->>R: ACK
    Note over R: CRASH before marking PUBLISHED
    Note over D: Row stays IN_FLIGHT, lease will expire
    R->>D: New worker claims evt-501
    R->>B: Republish same eventId
    B->>C: May deliver duplicate evt-501
~~~

This is the **gap between broker ACK and persisting outbox status**. There is no atomic transaction spanning these two operations, so the relay may resend after a crash or ambiguous ACK.

| Failure timing | Possible state | Consequence to handle |
| --- | --- | --- |
| Before business transaction commit | Both business row and outbox row roll back | No event emitted for failed transaction |
| After commit, before relay picks up | Outbox `PENDING` | Another worker or next poll picks it up |
| Claimed, not yet published | `IN_FLIGHT` | Wait for lease expiration then reclaim |
| Broker received, relay missed ACK | Unknown whether broker received it | Retry may produce duplicates |
| Broker ACKed, DB mark `PUBLISHED` failed | Outbox stays pending/in-flight | May republish same `eventId` |
| Marked `PUBLISHED` | Outbox recorded transport ACK | Consumer may still not have finished processing |
| Consumer committed, broker ACK lost | Broker redelivers | Consumer inbox/idempotency must block duplicates |

**Operational conclusion:** design assuming an event can be delivered **multiple times**, while business impact remains accurate thanks to idempotent consumers. Never advertise Outbox as providing end-to-end exactly-once automatically.

## 9. Idempotent Consumer and Inbox

The consumer receives a stable `eventId` from the producer. If the consumer processes within the same database as a `consumer_inbox` table, a unique constraint can prevent duplicate processing.

~~~sql
CREATE TABLE consumer_inbox (
    event_id     uuid PRIMARY KEY,
    processed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE order_projections (
    order_id      text PRIMARY KEY,
    status        text NOT NULL
);
~~~

Example consumer using **the same receiving database transaction** to insert into the inbox and update the read model:

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionConsumer {
    private final JdbcTemplate jdbc;

    public OrderProjectionConsumer(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void onOrderCreated(UUID eventId, String orderId) {
        int inserted = jdbc.update(
                "INSERT INTO consumer_inbox(event_id) VALUES (?) " +
                "ON CONFLICT (event_id) DO NOTHING",
                eventId);
        if (inserted == 0) {
            return; // Same eventId already committed earlier.
        }

        jdbc.update(
                "INSERT INTO order_projections(order_id, status) " +
                "VALUES (?, 'CREATED') " +
                "ON CONFLICT (order_id) DO UPDATE SET status = EXCLUDED.status",
                orderId);
    }
}
~~~

When the handler fails before commit, both the inbox insert and projection update roll back. The broker can then redeliver to retry. When the transaction commits and the broker ACK fails, redelivery sees the event ID already in the inbox and makes no further database changes.

**Limitation:** this inbox protects changes **in the same database transaction**. If the consumer also sends emails or calls external REST APIs, a DB rollback does not undo executed side effects. You need downstream idempotency keys, a second outbox, or a reconcilable workflow depending on requirements.

### Avoiding Premature ACK Bugs

For a consumer receiving from a broker, never confirm message completion before the business/inbox transaction actually commits (unless the architecture provides another guarantee). ACKing before commit followed by process death can lose the event even though the broker believes it was handled. ACK/NACK/transaction policies are specific to Kafka, RabbitMQ, JMS, or the adapter in use.

## 10. Ordering and Multiple Events on the Same Aggregate

One order may emit:

~~~text
OrderCreated  -> PaymentConfirmed -> OrderShipped
~~~

Monotonically increasing outbox IDs show **local insert order**, yet do not guarantee total business order:

- Two concurrent transactions may generate IDs in one order and commit in the opposite order.
- Two relay workers may claim/send events at different speeds.
- Brokers can partition messages by key, yet ordering holds only per transport and partition contract.
- Consumers processing/retrying asynchronously may finish out of receive order.

If per-order ordering is required:

1. Use `aggregate_id=orderId` as the routing/partition key when the broker supports it.
2. Persist an **aggregate version** or business sequence inside the event-producing transaction (e.g., `orderVersion=3`).
3. Define how relays/consumers handle gaps, duplicates, and out-of-order arrivals.
4. Evaluate sequential per-aggregate or per-partition dispatch requirements; never rely solely on `ORDER BY id` with multiple workers.

Every event must still carry its own `eventId`. `aggregateId` groups events of the same order, **not replace** per-event idempotency keys.

## 11. Polling Relay vs. Change Data Capture (CDC)?

Two common strategies:

| Criterion | Polling Outbox Relay | CDC from database log |
| --- | --- | --- |
| How new events are detected | Worker queries `PENDING` and claims | CDC connector reads committed changes |
| Latency | Depends on polling interval and backlog | Typically low, depends on connector |
| DB load | Periodic queries/indexes/locks | Uses log replication, with its own operational cost |
| Retry mechanism | Relay manages attempts/next attempt | Connector/broker and offsets manage per design |
| Operations | Simpler code and DB job at small scale | Requires managing connectors, offsets, snapshots, lag |
| Spring Integration interaction | Easy to integrate flows/pollers and error channels | Spring Integration can process on the consumer side |

With CDC (e.g., a tool reading WAL/binlog and routing outbox events), ensure only **committed** transactions emit events and metadata like `eventId`, `aggregateId`, and `eventType` maps accurately. CDC can also replay on connector restarts or offset replays; consumers still need idempotency.

Some architectures use an **insert-only outbox with CDC** instead of a table with multiple relay status columns. Never blindly apply polling claim SQL to CDC when the connector has its own mechanism. Choice depends on throughput, latency, operational skill, and infrastructure.

## 12. Timeouts, Retries, Error Channels, and Dead Letters

Retries should classify errors:

| Scenario | Suggested policy |
| --- | --- |
| Broker temporarily unreachable | Retry with backoff, caps, and alerts |
| Send timed out, ACK uncertain | Retry with **the same eventId**; consumer deduplicates |
| Event data fails serialization | Quarantine/FAILED, fix data or code |
| Topic/queue missing | Likely configuration error; alert and stop aggressive retries |
| Attempts exhausted | `FAILED` + audit, dead-letter, and controlled replay |
| DB mark `PUBLISHED` failed | Do not claim broker missed it; reconcile then retry |

### Error Boundaries in Spring Integration

With a `DirectChannel` and a synchronous broker-sending handler, exceptions propagate back to the relay; the relay sets `PENDING` with a new `next_attempt_at`.

If an IntegrationFlow branches to an `ExecutorChannel` or queue, errors may happen on another thread. Then **the error channel only notifies of the error**, while updating outbox rows must have a **single retry owner**. Never mark `PUBLISHED` merely upon enqueuing in RAM.

A possible error-handling flow:

~~~mermaid
flowchart LR
    R[Outbox Relay] --> I[IntegrationFlow send]
    I -->|ACK| D[Mark PUBLISHED]
    I -->|Error| E[Classify exception]
    E -->|Retryable| P[Mark PENDING + backoff]
    E -->|Permanent| F[Mark FAILED + alert]
    F --> Q[Quarantine / operator replay]
~~~

`RequestHandlerRetryAdvice` can help for brief retries in handlers, yet calculate **total transport attempts** if the relay also retries. Two layers of 3 retries can produce up to 9 attempts on some failure paths. For longer retries, letting the scheduler/DB decide the next attempt is usually easier to control than sleeping threads inside handlers.

### Never Equate DLQ with PUBLISHED Status

A `FAILED` event must not be treated as published merely because the error was logged. Define row retention and replay sources; clean up `PUBLISHED` rows only after retention satisfies audit/reconciliation needs. When replaying **the same business event**, keep the old `eventId`; mint a new ID only when generating a genuinely new business event.

## 13. Monitoring and Reconciliation

An outbox system should observe at least:

| Metric | Meaning |
| --- | --- |
| `outboxPendingCount` | Rows ready or waiting to retry |
| `outboxOldestPendingAge` | Age of oldest backlog item |
| `outboxInFlightCount` | Rows currently held under an owner/lease |
| `outboxExpiredLeaseCount` | Rows needing reclaim because workers may have died |
| `outboxPublishLagMs` | Duration from `createdAt` to broker ACK |
| `outboxRetries` | Relay retry count |
| `outboxFailedCount` | Rows exceeding retry budget / unpublishable |
| `consumerDuplicateSuppressedCount` | Duplicate events blocked by inbox/idempotency |

Example structured log:

~~~text
flow=OrderCreatedOutboxRelay
eventId=7b39bf78-992c-4b04-8782-cfdc6178d852
aggregateId=order-501
eventType=OrderCreated
outboxId=10421
claimToken=9f09cbfa-14e5-450c-bd2a-4192b418f879
attempt=2
createdAt=2026-11-21T09:00:00Z
brokerAckAt=2026-11-21T09:00:04Z
outcome=PUBLISHED
~~~

This is an **application-designed log**. Never log sensitive fields like tokens, card numbers, or full personal details. `claimToken` in the example is a relay coordination UUID; in production, mask/restrict logs per security policy.

### Runbook When Backlog Grows

1. Check if database/transactions remain healthy; inspect overdue `PENDING` and expired-lease `IN_FLIGHT` rows.
2. Check broker availability, quotas, topic permissions, and send error types.
3. Compare producer outbox creation rate with relay ACKed publish rate.
4. Check for retry storms, claim contention, lease duration, and scheduler health.
5. Reconcile `PUBLISHED` event counts with the broker/consumers when required by business rules.
6. For `FAILED` rows, verify consumer side effects before replaying with the same `eventId`.

Never delete active outbox rows just to shrink backlog. Deletion/migration requires retention policies, auditing, and transaction state verification.

## 14. Testing Outbox Across Failure Windows

To prove the mechanism, write **separate** tests for the business transaction and the relay.

### 14.1. Testing the Business Transaction

**Case A — Successful commit:** call `createOrder("order-501", ...)`; query to find **one orders row** and **one outbox row** containing the matching business event.

**Case B — Outbox insert failure:** simulate a unique/serialization/DB error on the outbox insert; the method throws; query to confirm **no new order** exists after rollback.

**Case C — Business insert failure:** use a duplicate `orderId`; verify no outbox event appears for the failed transaction.

An example test using `JdbcTemplate` and JUnit, assuming DB/test context integration is ready:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

class OutboxTransactionIT {
    @Autowired OrderApplicationService orders;
    @Autowired JdbcTemplate jdbc;

    @Test
    void writesBusinessRowAndOutboxAtomically() {
        java.util.UUID eventId = orders.createOrder("order-it-501", 150_000L);

        Integer orderCount = jdbc.queryForObject(
                "SELECT count(*) FROM orders WHERE order_id = ?",
                Integer.class, "order-it-501");
        Integer outboxCount = jdbc.queryForObject(
                "SELECT count(*) FROM integration_outbox WHERE event_id = ?",
                Integer.class, eventId);

        assertEquals(1, orderCount);
        assertEquals(1, outboxCount);
    }
}
~~~

This is an **illustrative test snippet**: it needs `@SpringBootTest` or matching test context configuration, a real PostgreSQL schema, and test data cleanup between tests. If the test itself wraps execution in an outer transaction, seeing uncommitted data does not prove durability; verify from a separate transaction/connection after the application transaction commits.

### 14.2. Testing Relay and Consumer

| Scenario | Expectation |
| --- | --- |
| Normal broker ACK | Row marked `PUBLISHED` after ACK |
| Transient broker failure | Row returns to `PENDING` with `next_attempt_at`, `attempts` incremented |
| Broker ACKs then relay dies before marking | Row reclaimed after lease, may republish with same `eventId` |
| Two relays claim concurrently | Never both own the row within active lease; verify on real DB |
| Lease expires while worker is slow | Duplicate risk recognized; never rely on leases for exactly-once |
| Consumer receives same `eventId` twice | Inbox detects duplicate and DB side effect occurs once |
| Consumer finishes yet broker ACK fails | Redelivery blocked by inbox |
| Two events for the same aggregate | Verify version/partition policy and out-of-order handling |
| Event moved to `FAILED` | Alert/quarantine and controlled replay |
| Relay restarts | `PENDING` or expired-lease `IN_FLIGHT` rows continue processing |

Testcontainers with PostgreSQL is a realistic way to test concurrency and `SKIP LOCKED`. A unit test mocking the repository does not prove row locks/leases work under concurrent transactions.

## 15. When to Choose Outbox and When Another Design Is Needed?

Outbox fits when:

- A database business transaction must emit events to a broker/other service.
- Committing the local transaction must not depend on the broker being online.
- Eventual consistency is acceptable and controlled retry/replay is needed.
- Consumers can be made idempotent and backlog operations tooling exists.

Outbox **does not replace**:

- Distributed/XA transactions if the goal genuinely requires atomic commits across multiple resources and the architectural cost is accepted.
- Sagas/workflows when a process comprises multiple business steps with **compensating actions**.
- Consumer and API idempotency when requests/events can be resent.
- Business schedulers or Delayers when the requirement is waiting until a future time; outbox provides **reliable publishing**, not scheduled delivery timing.

### Combining Outbox with Other EIPs

A possible architecture:

~~~mermaid
flowchart LR
    A[API Gateway] --> B[Business service + Outbox]
    B --> R[Outbox Relay]
    R --> K[Broker]
    K --> T[Transformer]
    T --> F{Filter / Router}
    F -->|Immediate| C[Consumer + Inbox]
    F -->|Wait| D[Delayer + Persistent Store]
    D --> C
    C --> E[Audit / Error handling]
~~~

If a Delayer sits after the broker, make pending messages inside the Delayer durable **as well**, rather than assuming the producer's Outbox protects messages sitting in a downstream JVM. Similarly, when a consumer emits new events after processing, it can use **its own** outbox in its own transaction.

## 16. Hands-On Exercises and Self-Check Questions

1. Create `orders` and `integration_outbox` tables in PostgreSQL. Configure a `@Transactional` service writing both. Simulate an outbox write failure and verify `orders` rollback.
2. Write a relay polling `PENDING` by `next_attempt_at`, claiming with `FOR UPDATE SKIP LOCKED`, sending one record at a time, and marking `PUBLISHED` after ACK.
3. Crash the relay after broker ACK but before the DB update. Explain why the event may be republished.
4. Run two relay instances reading the same database; verify one claim transaction never grabs a row locked by another transaction.
5. Stall one relay past the lease duration while sending. Analyze what happens if another worker reclaims that row.
6. Create `consumer_inbox` with unique `eventId`. Send the same event twice and prove the projection updates only once.
7. Design backoff after broker timeouts; distinguish ambiguous network errors (unknown ACK) from clearly non-retryable schema errors.
8. Emit two events with the same `aggregateId` across two workers. Propose `aggregateVersion` and partition keys to preserve required ordering.
9. Compare polling relay vs. CDC at one million events/day: latency, database load, operations, connector restarts, and replay.
10. Wire Outbox → Broker → Router → Delayer → Consumer. List persistence, retry, error channel, and idempotency points at each boundary.

**Self-check questions:** Why doesn't `@Transactional` wrapping a REST call make it atomic with the database? Why doesn't an `AFTER_COMMIT` callback replace an outbox? When may a row be marked `PUBLISHED`? What happens if a crash occurs between ACK and marking? What risks does `FOR UPDATE SKIP LOCKED` solve and not solve? Why must the consumer inbox be written in the same transaction as business updates? If an event is sent to the broker multiple times, how do you prevent side effects from doubling?

## References

- [Spring Integration Reference — Transactions Support](https://docs.spring.io/spring-integration/reference/transactions.html): transactions in message flows, pollers, and transaction boundaries.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, error channels, synchronous/asynchronous errors.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): `IntegrationFlow`, endpoints, and channels.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional` and transaction scopes.
- [Microservices Patterns — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html): motivation, relay, duplicates, and idempotent consumers.
- [Debezium Documentation — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): CDC option for routing outbox events.
