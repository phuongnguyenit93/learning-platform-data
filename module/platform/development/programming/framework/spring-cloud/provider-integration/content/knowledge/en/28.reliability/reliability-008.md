# Transactional Outbox and Compensation Without Cross-Service Transactions

A Spring Boot application frequently needs to update business data in a database and then emit a message so another service can continue processing. If the database write and the message publish are two independent operations, the system can land in a half-completed state: the order was created yet the event was never sent, or the message was sent yet the database transaction rolled back.

Managed services such as Azure Service Bus, Cosmos DB, AWS SQS, DynamoDB, Google Cloud Pub/Sub, and Spanner have their own transactions or guarantees, but there is no single ACID transaction spanning every database, broker, and external API in a typical workflow. The **transactional outbox** closes the gap between persisting data and emitting events. **Sagas and compensation** manage business workflows made up of multiple local transactions when the entire system cannot be rolled back by a single transaction.

This lesson belongs to the **Reliability** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing the integration of Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the dual-write problem and why a database transaction does not include broker publishing.
2. Design outbox records written in the same transaction as business state.
3. Implement a polling/lease publisher or CDC publisher and handle duplicate publishes.
4. Ensure messages carry stable event IDs and consumers stay idempotent via an inbox.
5. Distinguish transactional outbox, transactional messaging, distributed transactions, and sagas.
6. Design saga orchestration/choreography with state machines and compensation.
7. Handle timeouts, unknown outcomes, retries, and compensation failures.
8. Apply these patterns with Cosmos DB/Service Bus, DynamoDB/Streams/SQS, and Spanner/Firestore/Pub/Sub.
9. Integrate the outbox with Spring Boot, Spring Data, and Spring Cloud Stream.
10. Test crash windows, duplicate publishes, partial failures, and workflow recovery.

## 2. The Dual-Write Problem: Two Writes, One Gap

Suppose the Order API must create an order in PostgreSQL and send an OrderCreated event to a broker.

A naive implementation:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.from(command));
    messagePublisher.publish(new OrderCreated(order.getId()));
    return order;
}
~~~

The @Transactional annotation only manages transactions for resources enlisted with the Spring transaction manager, usually the database. Calling a broker does not automatically join that transaction.

There are two failure windows:

### Database Commit Succeeds, Publish Fails

~~~mermaid
sequenceDiagram
    participant A as Order API
    participant DB as Database
    participant B as Broker
    A->>DB: INSERT order
    DB-->>A: COMMIT
    A->>B: Publish OrderCreated
    B--xA: Timeout / unavailable
    Note over DB: Order exists
    Note over B: Event not confirmed
~~~

The order exists, yet the inventory, notification, or fulfillment services never learn about the new order.

### Publish Succeeds, Database Rolls Back

~~~mermaid
sequenceDiagram
    participant A as Order API
    participant DB as Database
    participant B as Broker
    A->>DB: INSERT order
    A->>B: Publish OrderCreated
    B-->>A: Accepted
    A->>DB: COMMIT
    DB--xA: Transaction rollback
    Note over B: Event already emitted
    Note over DB: Order does not exist
~~~

Consumers receive an event referencing a nonexistent order.

This is the **dual-write problem**: two systems must be updated as one business intent, yet there is no shared atomic transaction.

### Why Not Just Publish Inside @Transactional?

Calling the broker inside a database transaction does not make the broker roll back alongside it. If the database rolls back after the broker accepted the message, the broker will not automatically delete it. If you publish before commit and a consumer reads immediately, the consumer may query the database before the order is committed.

Distributed transactions/XA exist in some ecosystems, but they are not a universal choice across managed databases, cloud brokers, and HTTP APIs. They increase coupling and operational cost, and many cloud services cannot participate in a shared XA transaction.

## 3. What Does the Transactional Outbox Solve?

An outbox stores the **intent to emit an event** in the very same database holding business state, inside the same transaction.

~~~mermaid
flowchart LR
    A[Spring Boot command] --> T[Database transaction]
    T --> O[(Business table)]
    T --> X[(Outbox table)]
    X --> P[Outbox publisher / CDC]
    P --> B[Managed broker]
    B --> C[Consumer]
    C --> I[(Inbox + business transaction)]
~~~

Order-creation transaction:

~~~text
BEGIN
  INSERT orders(...)
  INSERT outbox_events(...)
COMMIT
~~~

If the transaction commits, both the order and the outbox event exist together. If it rolls back, both disappear together.

An independent publisher reads the outbox and sends messages to the broker. If the broker is temporarily unavailable, the record remains persisted and the publisher retries later.

**The outbox guarantees that business state and publish intent commit atomically in the same database.** It does not guarantee the broker receives the message only once. The publisher can resend if the broker accepted the message but the publisher lost the acknowledgment before marking the record SENT. Therefore, event IDs must be stable and consumers must still be idempotent.

## 4. Designing the Outbox Table

A reference schema for PostgreSQL:

~~~sql
CREATE TABLE outbox_events (
    id                UUID PRIMARY KEY,
    aggregate_type    VARCHAR(120) NOT NULL,
    aggregate_id      VARCHAR(160) NOT NULL,
    aggregate_version BIGINT,
    event_type        VARCHAR(160) NOT NULL,
    schema_version    INTEGER NOT NULL,
    payload           JSONB NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    next_attempt_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts          INTEGER NOT NULL DEFAULT 0,
    lease_owner       VARCHAR(160),
    lease_token       UUID,
    lease_until       TIMESTAMPTZ,
    published_at      TIMESTAMPTZ,
    last_error_code   VARCHAR(120)
);
~~~

Key fields:

| Field | Role |
| --- | --- |
| id | Stable event ID across publish retries |
| aggregate_type | Type of aggregate emitting the event |
| aggregate_id | Related business entity |
| aggregate_version | Event order within the aggregate if domain uses sequences |
| event_type | Event type name |
| schema_version | Payload version |
| payload | Serialized event data |
| status | Publishing status |
| next_attempt_at | Earliest timestamp for next retry |
| attempts | Number of publisher attempts |
| lease_owner/token/until | Claiming events when multiple publishers run concurrently |
| published_at | Timestamp when broker confirmed publish |
| last_error_code | Latest error code for investigation |

Common statuses:

- PENDING: waiting for a publisher.
- IN_FLIGHT: claimed by a publisher.
- RETRY: prior publish failed transiently.
- SENT: broker confirmed publish per contract.
- DEAD: exceeded retry budget or error requires manual investigation.

Not every application needs all statuses. Simple systems may only need PENDING/SENT plus attempt metadata. Critical workflows benefit from explicit leases, retry schedules, and dead-letter states.

### Indexes and Uniqueness

Example indexes for a polling publisher:

~~~sql
CREATE INDEX idx_outbox_pending
ON outbox_events (next_attempt_at, created_at)
WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX idx_outbox_lease
ON outbox_events (lease_until)
WHERE status = 'IN_FLIGHT';
~~~

If each aggregate version produces at most one event, you can add a unique constraint:

~~~sql
CREATE UNIQUE INDEX uq_outbox_aggregate_version
ON outbox_events (aggregate_type, aggregate_id, aggregate_version)
WHERE aggregate_version IS NOT NULL;
~~~

Use this constraint only when the domain guarantees one version maps to at most one event. If a single version can emit multiple events, use a separate sequence or add an event ordinal.

## 5. Writing Business State and Outbox in the Same Transaction

Spring Boot example using Spring Data JPA. This is an architectural pattern; complete entity mapping, JSON serialization, and repositories according to your database.

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final ObjectMapper objectMapper;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox,
            ObjectMapper objectMapper) {
        this.orders = orders;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Order create(CreateOrderCommand command) {
        Order order = orders.save(Order.create(command));

        OrderCreated event = new OrderCreated(
                UUID.randomUUID(),
                order.getId(),
                order.getVersion(),
                Instant.now(),
                command.customerId());

        outbox.save(OutboxEvent.pending(
                event.eventId(),
                "Order",
                order.getId(),
                order.getVersion(),
                "OrderCreated",
                1,
                serialize(event)));

        return order;
    }

    private String serialize(Object event) {
        try {
            return objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize outbox event", ex);
        }
    }
}
~~~

Points to guarantee:

- Order and OutboxEvent share the same datasource/transaction manager.
- Outbox insert does not run in an independent transaction from the order.
- The event ID is generated once and persisted durably; the publisher does not invent a new ID on retries.
- The payload is the snapshot event to emit, not an arbitrary query reading whatever state happens to exist later.
- The event schema includes version and sufficient metadata for consumers.
- Never call the broker inside this transaction.
- Never hold the database transaction open while waiting on network I/O.

If serialization fails, the transaction must roll back both the order and the outbox. If the order commits, the outbox record must also commit.

## 6. Polling Publisher: Reading the Outbox in Batches

A common implementation uses a periodic worker that reads PENDING/RETRY records, claims them, sends them to the broker, and marks them SENT.

Flow:

1. Open a short transaction.
2. Claim a batch of records not currently held by another worker.
3. Set owner, lease token, and lease expiry.
4. Commit the claim.
5. Send messages to the broker outside the database transaction.
6. Wait for broker confirmation per the API/client contract.
7. If the broker confirms, mark SENT conditioned on the claim token still matching.
8. On transient failure, schedule RETRY with backoff.
9. On permanent failure or exhausted budget, move to DEAD and alert.

### Claiming Across Multiple Concurrent Publishers

PostgreSQL supports the SELECT FOR UPDATE SKIP LOCKED pattern. Example:

~~~sql
WITH candidates AS (
    SELECT id
    FROM outbox_events
    WHERE (
        status IN ('PENDING', 'RETRY')
        AND next_attempt_at <= now()
    ) OR (
        status = 'IN_FLIGHT'
        AND lease_until < now()
    )
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE outbox_events AS e
SET status = 'IN_FLIGHT',
    lease_owner = :worker_id,
    lease_token = :claim_token,
    lease_until = now() + interval '30 seconds',
    attempts = attempts + 1
FROM candidates AS c
WHERE e.id = c.id
RETURNING e.*;
~~~

This query illustrates atomic claiming. Adjust interval syntax and locking to your specific database.

Never hold row locks while performing network requests. Keep claim transactions short to avoid blocking other publishers and business transactions.

### Leases Do Not Eliminate Duplicates

Suppose publisher A claims an event, sends it to the broker successfully, and pauses before marking SENT. The lease expires; publisher B reclaims it and sends the same event. Both can publish the message.

A lease token stops an old worker from overwriting a new claim's status, but it cannot recall an already-sent message. Therefore:

- Use the stable event ID as the message ID.
- Have consumers use an inbox/unique constraint.
- Mark SENT only if the claim token still belongs to the current publisher.
- Renew the lease if batch publishing runs long.
- Set explicit timeouts for broker publishing.
- Never treat leases as exactly-once.

### Conditional Mark SENT

~~~sql
UPDATE outbox_events
SET status = 'SENT',
    published_at = now(),
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL
WHERE id = :event_id
  AND status = 'IN_FLIGHT'
  AND lease_token = :claim_token;
~~~

If 0 rows update, the publisher likely lost its lease or another worker claimed the record. Do not overwrite a newer claim. The published message may be resent; consumer deduplication handles it.

## 7. Publish Confirmation and Unknown Outcomes

When a publisher calls a broker, three outcomes are possible:

- Broker confirms receipt of the message.
- Broker explicitly rejects before accepting.
- Publisher times out/disconnects and does not know whether the broker accepted it.

The third case is an **unknown outcome**. You cannot assume the message was not sent just because the client missed the response.

How to handle it:

1. Keep the same event ID.
2. Retry per policy using the same identity.
3. Accept that the broker may receive duplicates.
4. Use a consumer inbox/broker deduplication within supported scope.
5. Track attempts and correlation IDs.
6. If the event has financial side effects, consumers still need business idempotency.

Never generate a new event ID on each publish retry; doing so makes consumers treat duplicates as new events.

## 8. Preserving Order When Publishing from Outbox

Polling with multiple workers can send events for the same aggregate out of order. For example, version 12 is delayed on worker A while worker B sends version 13 first.

If per-aggregate ordering is required:

- Store aggregate ID and sequence/version in the outbox.
- Set partition/session/message group/ordering key to aggregate ID.
- Claim the next event for an aggregate only after the preceding event is published per policy.
- Avoid running parallel publishers for the same aggregate without an ordering mechanism.
- Consumers must still validate versions and idempotency.
- Handle replays/late events per domain rules.

A claim query can exclude records whose older events are not yet SENT, but it must account for IN_FLIGHT, RETRY, and DEAD. A prior event marked DEAD should not automatically unblock later events if it is a business prerequisite.

Broker ordering within a partition/session does not guarantee database commit order if consumers process concurrently. Outbox ordering and consumer sequence guards must work together.

## 9. Polling Publisher vs. CDC Publisher

There are two common ways to get outbox records to a broker.

| Criterion | Polling Publisher | CDC Publisher |
| --- | --- | --- |
| How it works | Worker queries outbox table on a schedule | Reads transaction log / change stream |
| Latency | Driven by polling interval and batching | Usually lower, connector-dependent |
| Complexity | Easy to start; needs query/claim tuning | Needs connector, offsets, schemas, and ops |
| Database load | Periodic queries on outbox table | Reads transaction log / change stream |
| Retries | Managed by application | Connector/offset and sink retries |
| Duplicates | Possible | Possible on restart / offset replay |
| Ordering | Must design claim and aggregate ordering | Depends on log order, partitions, and sink |
| Best fit | Small/medium apps needing direct control | High throughput or existing CDC platform |

### Polling Publisher

Pros:

- Easy to implement inside Spring Boot.
- Requires no database log-pipeline changes.
- Can filter, rate-limit, and retry under business policies.
- Straightforward to attach metrics and SENT/DEAD states.

Cons:

- Continuous polling queries add load.
- Needs leases/claims to coordinate multiple instances.
- Must manage cleanup and batch sizing.
- Latency depends on polling interval.

### CDC Publisher

CDC reads committed changes from the transaction log or change feed, then forwards outbox events to the broker.

Example architecture: database outbox → Debezium/CDC connector → broker. CDC observes only committed changes, avoiding publishing rolled-back transactions.

However, CDC can still replay records when a connector restarts, offsets were not committed, or snapshots re-run. Consumers must remain idempotent. Manage connector offsets, schema history, log retention, and backpressure.

CDC does not turn a database transaction and broker publish into one shared transaction. It changes how new records are detected; it does not remove all failure windows.

## 10. Consumer Inbox: Protecting the Receiving Side

The outbox closes the producer-side gap. Consumers can still receive the same message multiple times because broker delivery is usually at-least-once or publishers retry after unknown outcomes.

Inbox table:

~~~sql
CREATE TABLE inbox_messages (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      UUID NOT NULL,
    payload_hash  VARCHAR(64) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    result_ref    VARCHAR(160),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Within one transaction:

~~~text
BEGIN
  INSERT inbox(consumer_name, event_id, payload_hash)
  UPDATE business state
  INSERT next outbox event if required
COMMIT

ACK / Complete message
~~~

If the event ID already exists with the same payload hash, the consumer can ACK the duplicate without repeating business effects. If the same ID arrives with a different payload, that is an identity conflict requiring quarantine/alerting.

The inbox and business state must share the same transaction when in the same database. Putting the inbox in Redis while business state lives in PostgreSQL gives no atomicity across the two; crashing between them still leaves a gap.

Inbox retention must cover broker redelivery, DLQ replays, and operational replay windows. For payments/ledgers, unique business references may need to be retained longer than inbox records.

## 11. Outbox, Inbox, and Exactly-Once

Outbox + inbox forms an **effectively-once** chain for business state within the scope of database transactions and defined event identities:

- Producer writes business state and outbox in one transaction.
- Publisher emits events with stable identity; duplicates may happen.
- Consumer writes inbox and business state in one transaction.
- Redeliveries are caught by the inbox.
- External side effects rely on provider idempotency or sagas/reconciliation.

## 12. When Is a Saga Needed?

The outbox protects event emission after a local transaction. Yet a workflow may need to update multiple independent services/databases:

~~~text
Order service: create order
Inventory service: reserve stock
Payment service: authorize/capture payment
Shipping service: create shipment
Notification service: send confirmation
~~~

No single database transaction spans all services. If shipping fails after inventory and payment succeeded, the system needs a way to continue or compensate.

A **Saga** breaks a workflow into multiple local transactions. Each step commits independently and emits the next event/command. If a later step fails, the saga can run compensating actions for prior steps per business rules.

A saga is not a distributed rollback. Each committed step is real state that may already have been observed by other systems.

## 13. Orchestration vs. Choreography

There are two ways to coordinate a saga:

### Orchestration

A saga orchestrator stores workflow state and sends commands to each service.

~~~mermaid
flowchart TD
    O[Order Saga Orchestrator] --> I[Reserve Inventory]
    I --> P[Authorize Payment]
    P --> S[Create Shipment]
    S --> D[Complete Order]
    P -. failure .-> RI[Release Inventory]
    S -. failure .-> VP[Void Payment]
    VP --> RI
~~~

Pros:

- Business flow is visible in one place.
- Easy to track state, timeouts, and compensation.
- Easy to enforce retry budgets and manual intervention.

Cons:

- The orchestrator is another component to operate and scale.
- Can introduce coupling to the workflow definition.
- Must protect state and commands with outbox/inbox.

### Choreography

Services react to one another's events without a central coordinator.

~~~mermaid
flowchart LR
    O[OrderCreated] --> I[Inventory Service]
    I -->|InventoryReserved| P[Payment Service]
    P -->|PaymentAuthorized| S[Shipping Service]
    S -->|ShipmentCreated| C[Order Completed]
    P -->|PaymentRejected| R[Inventory Release]
~~~

Pros:

- Services depend less directly on a coordinator.
- Each service manages its own transactions and events.
- Fits short workflows with few branches.

Cons:

- Overall flow is scattered across many handlers.
- Harder to observe when many events/branches interact.
- Risk of event cycles or ambiguity over who owns timeouts.
- Requires explicit correlation IDs, saga IDs, and workflow state.

### Which Approach to Choose?

| Workflow Characteristic | Suitable Approach |
| --- | --- |
| Simple 2–3 steps, minimal branching | Choreography may suffice |
| Many steps, complex timeouts and compensation | Orchestration is usually easier to control |
| Needs whole-workflow state auditing | Orchestration or explicit saga state store |
| Independent services reacting to domain events | Choreography |
| Operators need to retry/resume individual steps | Explicit orchestrator/state machine |

There is no rigid step-count rule. Choose based on understandability, observability, recoverability, and ease of workflow evolution.

## 14. Designing Saga State and Commands

A saga instance can store:

~~~sql
CREATE TABLE saga_instances (
    saga_id          UUID PRIMARY KEY,
    saga_type        VARCHAR(120) NOT NULL,
    business_key     VARCHAR(160) NOT NULL,
    state            VARCHAR(40) NOT NULL,
    current_step     VARCHAR(120),
    version          BIGINT NOT NULL DEFAULT 0,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deadline_at      TIMESTAMPTZ,
    last_error_code  VARCHAR(120)
);
~~~

Steps table:

~~~sql
CREATE TABLE saga_steps (
    saga_id          UUID NOT NULL,
    step_name        VARCHAR(120) NOT NULL,
    status           VARCHAR(30) NOT NULL,
    command_id       UUID NOT NULL,
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    completed_at     TIMESTAMPTZ,
    compensation_id  UUID,
    last_error_code  VARCHAR(120),
    PRIMARY KEY (saga_id, step_name)
);
~~~

Saga states may include:

- STARTED/RUNNING: workflow in progress.
- COMPENSATING: compensating previously succeeded steps.
- COMPLETED: finished.
- FAILED_FINAL: terminal failure per policy.
- NEEDS_MANUAL_REVIEW: unknown outcome or compensation could not complete automatically.
- CANCELLED: canceled per business rules.

Every command/event needs a stable identity. Use a deterministic key such as saga ID + step name + command type to avoid emitting duplicate commands if the orchestrator restarts.

Update saga state and outbox commands in the same local database transaction. When the orchestrator advances state and emits a command, write state + outbox in one transaction.

## 15. Saga Example: Ordering, Reserving Stock, and Payment

Suppose an order flow has these steps:

1. Order service creates the order in PENDING state.
2. Inventory service reserves stock.
3. Payment service authorizes payment.
4. Shipping service creates a shipment.
5. Order service transitions the order to CONFIRMED.

An orchestration flow:

~~~mermaid
sequenceDiagram
    participant O as Order Saga
    participant I as Inventory
    participant P as Payment
    participant S as Shipping
    O->>I: ReserveInventory
    I-->>O: InventoryReserved
    O->>P: AuthorizePayment
    P-->>O: PaymentAuthorized
    O->>S: CreateShipment
    S-->>O: ShipmentCreated
    O->>O: Mark order CONFIRMED
~~~

If payment is declined:

~~~mermaid
sequenceDiagram
    participant O as Order Saga
    participant I as Inventory
    participant P as Payment
    O->>I: ReserveInventory
    I-->>O: InventoryReserved
    O->>P: AuthorizePayment
    P-->>O: PaymentRejected
    O->>I: ReleaseInventory
    I-->>O: InventoryReleased
    O->>O: Mark order FAILED
~~~

If shipment fails after payment was authorized:

1. Retry CreateShipment if the error is transient and deadline remains.
2. If unable to proceed, request VoidAuthorization.
3. Release inventory.
4. Transition order to FAILED/CANCELLED per business rules.
5. If voiding payment fails, mark NEEDS_MANUAL_REVIEW and reconcile.

### Authorize vs. Capture

If the payment provider supports authorization/capture, you can authorize before shipping and capture only at the right milestone. Once captured, compensation may require a refund rather than a void/rollback. A refund is a new business transaction with its own fees, latency, and lifecycle.

## 16. Compensation Is Not Rollback

Compensation is a business action that brings a workflow to an acceptable state after a downstream step fails. It does not erase committed transaction history.

| Original Action | Possible Compensation | Notes |
| --- | --- | --- |
| Reserve inventory | Release reservation | Reservation may have expired or stock may have been allocated |
| Authorize payment | Void authorization | Depends on provider and authorization state |
| Capture payment | Refund payment | Refund is a new transaction, not a rollback |
| Create shipment | Cancel shipment | May incur fees or fail if handed off to carrier |
| Create subscription | Cancel subscription | A billing cycle may already have run |
| Send email | Cannot unsend email | Can send a correction/clarification |
| Upload document | Delete/mark superseded | Must keep audit trail if referenced |

Compensation itself can fail. Therefore sagas must track compensation state separately, retry within bounds, escalate, and reconcile.

### In What Order Does Compensation Run?

Typically compensation runs in reverse order of succeeded steps:

~~~text
Reserve inventory
  → Authorize payment
  → Create shipment (fails)

Compensate:
  → Void payment authorization
  → Release inventory
~~~

However, this is not an absolute rule. Business domains may require canceling shipment first, or holding inventory until payment void succeeds. Ordering must reflect invariants and risk.

### Forward Recovery vs. Backward Compensation

- **Forward recovery:** fix the dependency and continue the remaining step.
- **Backward compensation:** execute compensating actions for already-completed steps.
- **Manual resolution:** requires operators or business teams to decide when outcomes cannot be resolved automatically.

Never trigger compensation merely because a request timed out. First determine whether the original step succeeded.

## 17. Timeouts and Unknown Outcomes in Sagas

A command may be received and committed by a service while the response event is lost. The orchestrator does not know whether the step succeeded or failed.

For example, the Payment service authorized the charge, yet the PaymentAuthorized event never arrived.

Do not send AuthorizePayment again with a brand-new command ID. Instead:

1. Keep the command ID/idempotency key stable.
2. Query payment status by provider reference/command ID if supported.
3. Wait for event retry or send a query command.
4. Reconcile with the provider.
5. If already authorized, proceed to the next step.
6. If not authorized, retry with the same operation identity per contract.
7. If indeterminable, move the saga to NEEDS_MANUAL_REVIEW.

A timeout is a caller observation, not a conclusion about target system state.

### Saga Deadlines

Each saga should have an overall deadline and per-step timeouts. When a deadline expires:

- Do not automatically compensate if a step has an unknown outcome.
- Query the step's state first.
- Choose forward retry, compensation, or manual review.
- Record the timeout reason and timestamp.
- Bound retries so workflows cannot live forever.

## 18. Idempotency for Every Saga Step

Each command and compensation must be independently idempotent:

- ReserveInventory uses a stable reservation ID tied to the saga/order.
- AuthorizePayment uses a stable payment operation ID.
- CreateShipment uses a stable shipment request ID.
- ReleaseInventory uses the reservation ID and operation ID.
- VoidAuthorization uses the authorization reference.
- RefundPayment uses a dedicated refund operation ID linked to the original payment.

A compensation action can be called multiple times due to retries. It must inspect current state and return an equivalent outcome if already executed.

Never share one idempotency key across all steps. Each side effect needs its own identity while staying linked to the saga ID/correlation ID.

## 19. Outbox Inside Each Service of a Saga

Each service has its own local database and outbox:

~~~text
Order service:
  BEGIN
    update saga/order state
    insert outbox command ReserveInventory
  COMMIT

Inventory service:
  receive command
  BEGIN
    insert inbox command ID
    reserve inventory
    insert outbox event InventoryReserved
  COMMIT
  ACK command

Saga orchestrator:
  receive InventoryReserved
  BEGIN
    update saga step
    insert outbox command AuthorizePayment
  COMMIT
~~~

Every service boundary is protected by a local transaction + outbox/inbox. No single transaction needs to span all services.

If the Inventory service commits the reservation yet fails to publish InventoryReserved, its outbox publisher re-emits it later. If it publishes a duplicate, the orchestrator's inbox catches it.

If the command is redelivered, the Inventory service's inbox blocks duplicate reservation. If the reservation provider is an external API, use a provider idempotency key or separate reconciliation.

## 20. Spring Boot Implementation: Writing Outbox and Publishing Messages

### 20.1. Repository Contract

~~~java
public interface OutboxRepository {
    List<ClaimedOutboxEvent> claimBatch(
            String workerId,
            UUID claimToken,
            int batchSize,
            Duration lease);

    boolean markSent(UUID eventId, UUID claimToken);

    boolean scheduleRetry(
            UUID eventId,
            UUID claimToken,
            Instant nextAttempt,
            String errorCode);

    boolean markDead(
            UUID eventId,
            UUID claimToken,
            String errorCode);
}
~~~

The repository must implement claim/mark atomically in the database. Never implement claiming as SELECT followed by UPDATE without locks or race-condition protection.

### 20.2. Publisher Worker

~~~java
@Component
public class OutboxPublisher {

    private final OutboxRepository outbox;
    private final BrokerPublisher broker;
    private final String workerId;

    public OutboxPublisher(
            OutboxRepository outbox,
            BrokerPublisher broker,
            String workerId) {
        this.outbox = outbox;
        this.broker = broker;
        this.workerId = workerId;
    }

    @Scheduled(fixedDelay = 500)
    public void publishBatch() {
        UUID claimToken = UUID.randomUUID();

        List<ClaimedOutboxEvent> events =
                outbox.claimBatch(
                        workerId,
                        claimToken,
                        50,
                        Duration.ofSeconds(30));

        for (ClaimedOutboxEvent event : events) {
            try {
                broker.publish(
                        event.id(),
                        event.eventType(),
                        event.payload(),
                        event.aggregateId());

                outbox.markSent(event.id(), event.claimToken());
            } catch (RetryablePublishException ex) {
                Instant next = retryTime(event.attempts());
                outbox.scheduleRetry(
                        event.id(),
                        event.claimToken(),
                        next,
                        ex.code());
            } catch (PermanentPublishException ex) {
                outbox.markDead(
                        event.id(),
                        event.claimToken(),
                        ex.code());
            }
        }
    }

    private Instant retryTime(int attempts) {
        long seconds = Math.min(300, 1L << Math.min(attempts, 8));
        return Instant.now().plusSeconds(seconds);
    }
}
~~~

This is illustrative pseudocode. In production:

- BrokerPublisher must wait for confirmation per SDK/binder contract; returning immediately after enqueuing to a local buffer is not a broker acknowledgment.
- Distinguish timeouts/unknown outcomes from explicit rejections.
- Retries need jitter, deadlines, and retry budgets; the shortened example shows backoff only.
- Claim leases must be long enough or renewed while publishing batches.
- Marking SENT must verify the claim token.
- Never swallow database exceptions during status updates.
- Avoid parallel processing of the same aggregate if strict ordering is required.
- Implement graceful shutdown so workers stop claiming new work and finish or let leases expire for held events.

### 20.3. Broker Message Identity

When sending events, use the outbox event ID as the message ID/idempotency identity:

~~~text
message_id = outbox_event.id
partition_key / session_id / ordering_key = aggregate_id
correlation_id = saga_id or request correlation
~~~

Specific headers and fields vary by broker. Never substitute a trace ID for an event ID. Preserve schema version and event type so consumers select the right handler.

## 21. Does Spring Cloud Stream Replace the Outbox?

Spring Cloud Stream provides an abstraction to send/receive messages via binders. It does not automatically turn a JPA transaction into an atomic transaction across every broker.

You can use Spring Cloud Stream as the transport for an outbox publisher:

1. Outbox poller claims events.
2. Calls StreamBridge or a function output binding.
3. Waits for the broker send result/confirmation per the actual binder.
4. Marks SENT after confirmation succeeds.
5. If the outcome is unclear, retries with the same event ID.

Verify:

- Does the binder return an asynchronous send result or acknowledgment?
- When does a send result mean the broker actually persisted the message?
- Are exceptions thrown synchronously or delivered via callback?
- What is the transaction scope of a transactional binder?
- Do binder retries stack on top of outbox retries?
- How are message IDs, partition keys, session IDs, and headers mapped?

Never mark SENT solely because StreamBridge.send returned true if binder semantics do not guarantee broker persistence. Check your binder/version documentation and write integration tests.

## 22. Azure: Cosmos DB, Change Feed, and Service Bus

### Cosmos DB Transactional Batch

Cosmos DB supports transactional batch within a single logical partition for supported operations. You can store a business document and an outbox document in the same partition/batch:

~~~text
Partition key = orderId

Transactional batch:
  Create/replace Order document
  Create OutboxEvent document
Commit batch
~~~

If the batch succeeds, both documents commit together; if it fails, the batch rolls back per service semantics.

Choose a partition key so the business record and outbox record share the same logical partition. If they reside in different partitions, do not assume a transactional batch spans both.

### Change Feed Publisher

The Cosmos DB Change Feed Processor can read new/modified outbox documents and publish events to Service Bus or Event Hubs. Checkpoints/leases are managed per processor and feed range.

A change feed consumer may reprocess documents on restart, lease handoff, or unsaved checkpoints. Publishers must use stable event IDs and downstream consumers must be idempotent.

Do not delete outbox records the instant Change Feed reads them. Configure lifecycle/TTL/cleanup appropriately and ensure the connector/processor has checkpointed past the record per policy.

### Service Bus Transactions Are Not Cross-Cosmos DB Transactions

Service Bus offers transactions for supported broker operations within a Service Bus namespace/transaction scope. That does not create a shared transaction with Cosmos DB or a payment API. A Cosmos outbox/change feed remains the bridge between database commit and broker publish.

## 23. AWS: DynamoDB, Streams, and SQS

### DynamoDB TransactWriteItems

DynamoDB supports transactional writes across multiple items within one service transaction. You can use TransactWriteItems to update a business item and create an outbox item atomically:

~~~text
TransactWriteItems:
  Update Order item
  Put OutboxEvent item with condition attribute_not_exists(eventId)
Commit
~~~

If the transaction succeeds, both business state and the outbox item are written together. Use condition expressions to prevent duplicate writes and guard versions.

### DynamoDB Streams

DynamoDB Streams capture item changes; a Lambda/consumer can read the stream and publish events to SQS, SNS, or EventBridge depending on architecture.

Address:

- Lambda/event source mappings may retry batches.
- Batch failures can cause records to reprocess; configure partial batch responses if used.
- Stream retention is bounded; never treat a stream as a long-term archive.
- Consumers need stable event IDs/idempotency.
- If a record publishes successfully yet source checkpoint/ack is not recorded, it can publish again.

Never treat DynamoDB Streams and the target broker as one atomic transaction. The outbox item/stream event is the emission source, and downstream consumers must deduplicate.

### SQS and EventBridge

An outbox publisher can send events to SQS or EventBridge. For SQS FIFO, set MessageGroupId from aggregate ID and MessageDeduplicationId from event ID within the service's supported window. For Standard queues, consumers must tolerate duplicates. Even when the broker deduplicates, an inbox/unique business constraint still protects side effects.

## 24. Google Cloud: Spanner, Firestore, and Pub/Sub

### Cloud Spanner

Spanner supports transactions across data in the database. You can update a business row and insert an outbox row in the same transaction. A separate publisher reads the outbox and publishes to Pub/Sub.

Spanner change streams can also serve as a CDC source for pipelines. Manage partitioning, offsets, retention, and duplicates on consumer restarts. Pub/Sub publishing remains separate from the database transaction.

### Firestore

Firestore transactions can write multiple documents within the same database subject to service limits and semantics. You can write a business document and an outbox document in the same transaction when designed appropriately.

Triggers/event-driven consumers may be invoked multiple times per platform delivery semantics. Use stable event IDs, transactions/conditional writes, and inboxes to guard against duplicates. Monitor transaction limits, contention, document sizes, and write rates.

### Pub/Sub

Publishers send outbox events to Pub/Sub after database commit. Pub/Sub ordering keys can use aggregate ID when ordering is required and subscriptions are configured appropriately. Consumers still need idempotency/inboxes because Pub/Sub and the database share no single workflow-wide transaction.

Never confuse Pub/Sub's exactly-once delivery feature with exactly-once database updates or external API effects.

## 25. Saga Compensation: Examples and Design Principles

A compensation design must answer:

- Did the original action definitely complete?
- Can the compensation be invoked multiple times?
- Can the compensation fail or time out?
- Are there irreversible side effects?
- Can the workflow recover forward instead of compensating?
- Which states require manual review?
- Who is authorized to decide financial compensation?

### Reservations

Reserving inventory usually produces a reservation ID and expiration. Releasing a reservation must be idempotent: if already released, calling it again must not add stock back twice.

### Payments

Voiding an authorization differs from refunding a capture. A refund must reference the original payment, carry its own refund ID, and track its own status. Never issue a new refund on every saga retry.

### Shipments

Canceling a shipment may be rejected once handed off to a carrier. That requires a return/refund workflow or manual intervention rather than assuming cancellation always reverses create-shipment.

### Emails

An email already sent cannot be rolled back. You can send a correction or follow-up notification, which is a separate business action.

## 26. Saga Retries, Timeouts, and Compensation Failures

Each step should track:

- Command ID/idempotency key.
- Attempt count and retry deadline.
- Timeout.
- Result state.
- Provider reference.
- Compensation command ID.
- Last error category/code.
- Correlation ID/saga ID.

Retry transient failures with backoff/jitter. On timeouts with unknown outcomes, query state before re-sending. When compensation fails, never mark the saga completed; transition to COMPENSATING or NEEDS_MANUAL_REVIEW and alert.

A saga can span hours or days. Never hold a database transaction open across the workflow. Each step is a short local transaction, and saga state is durably persisted.

## 27. Securing Outbox and Saga Data

Outbox payloads may contain customer details, orders, addresses, or payment references. Apply:

- Store only fields required by the event contract.
- Never store secrets, access tokens, passwords, or connection strings in payloads.
- Encrypt databases/storage per policy.
- Restrict read permissions on outbox/DLQs and replay permissions.
- Mask sensitive data in logs/traces.
- Audit the user/identity executing redrives or compensation.
- Configure retention/cleanup per business and legal requirements.
- Never let an operator arbitrarily replay payments/refunds without business authorization.
- Protect saga state from direct edits bypassing the workflow.

Replays and compensation trigger real side effects; operational permissions must be separated and audited.

## 28. Observability: Monitoring Outbox and Sagas

Outbox metrics:

| Metric | Meaning |
| --- | --- |
| outbox_pending_count | Pending events waiting |
| outbox_oldest_pending_age_seconds | Age of the oldest pending event |
| outbox_publish_attempts_total | Publisher attempt count |
| outbox_publish_confirmed_total | Events confirmed by broker |
| outbox_publish_failed_total | Publish failures |
| outbox_duplicate_publish_suspected_total | Duplicates detected at consumers |
| outbox_dead_count | Events exceeding retry budget |
| outbox_lease_expired_total | Expired claims |
| outbox_cdc_lag_seconds | CDC lag if applicable |

Saga metrics:

| Metric | Meaning |
| --- | --- |
| saga_started_total | Sagas started |
| saga_completed_total | Sagas completed |
| saga_compensating_count | Sagas currently compensating |
| saga_failed_total | Terminal saga failures |
| saga_manual_review_count | Sagas requiring human review |
| saga_step_duration_seconds | Per-step durations |
| saga_compensation_failed_total | Failed compensations |
| saga_unknown_outcome_count | Steps with unresolved outcomes |

Monitoring backlog, oldest age, and lag is usually more informative than raw message counts alone. Never use event ID, order ID, or saga ID as high-cardinality metric labels; place them in controlled logs/traces.

## 29. Testing Outbox and Sagas

### Outbox Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Order insert succeeds, outbox insert succeeds | Both commit |
| Outbox serialization/insert fails | Order transaction rolls back |
| Database transaction rolls back | No committed outbox event exists |
| Broker unavailable | Outbox stays pending/retry |
| Broker accepts event, publisher crashes before marking SENT | Duplicate may publish; consumer inbox blocks it |
| Two publishers claim simultaneously | Only one claim owner per record at any valid time |
| Lease expires while old publisher still running | Claim token blocks stale status update; event ID stops duplicates |
| Prior event unpublished | Later event for same aggregate does not leapfrog if strict ordering |
| CDC restart/offset replay | Duplicates handled idempotently |
| Cleanup runs | Does not delete pending/dead/in-flight records needed for investigation |

### Saga Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| All steps succeed | Saga COMPLETED |
| Reserve inventory fails | Payment is not authorized |
| Payment declined | Inventory released |
| Shipment transient failure | Retried within deadline |
| Shipment permanent failure after payment authorization | Authorization voided, then inventory released |
| Void payment times out | Query provider, keep unknown outcome |
| Compensation fails | Saga not marked complete; alerts/manual review |
| Duplicate command | Idempotent service creates no new side effect |
| Orchestrator restarts | Recovers from saga state/outbox |
| Late event response | Correlation/saga ID and step state reject stale response |
| Old command replayed | Idempotency key prevents re-execution |
| Saga deadline expires | Explicit recovery policy, no blind rollback |

### Fault Injection

1. Kill the application after database commit but before the publisher sends the event.
2. Kill the publisher after broker acceptance but before marking SENT.
3. Force broker publish to time out with an unknown outcome.
4. Restart the CDC connector after reading records but before committing offsets.
5. Make the payment service commit while dropping the response event.
6. Force compensation to time out after the provider processed it.
7. Restart the orchestrator while the saga is COMPENSATING.
8. Send the same command multiple times.
9. Deliver an event response after the saga already advanced steps.
10. Verify outbox backlog and saga manual-review alerts.

## 30. Lab Exercise: Order Workflow Using Outbox and Saga

**Context:** The Spring Boot Order service creates an order and emits OrderCreated. Inventory service reserves stock; Payment service authorizes payment; Shipping service creates the shipment. Each service owns its own database and communicates over a managed broker.

### Part A — Order-Side Outbox

1. Create orders and outbox_events tables.
2. Write the order and OrderCreated in the same transaction.
3. Implement a polling publisher or CDC.
4. Use a stable event ID as the message ID.
5. Monitor pending age, publish attempts, and dead count.

### Part B — Inbox and Local Transactions

1. Each consumer maintains its own inbox with a unique consumer/event key.
2. Write inbox and business state in the same transaction.
3. Publish downstream events via the service's outbox.
4. Commit before ACK/Complete.
5. Test duplicate delivery and publisher crashes.

### Part C — Saga Orchestration

1. Create a saga instance for the order.
2. Send ReserveInventory.
3. On InventoryReserved, send AuthorizePayment.
4. On PaymentAuthorized, send CreateShipment.
5. On ShipmentCreated, mark order CONFIRMED.
6. On payment failure, execute ReleaseInventory.
7. On terminal shipment failure, execute VoidAuthorization then ReleaseInventory.
8. If compensation is indeterminate, transition to NEEDS_MANUAL_REVIEW.

### Part D — Recovery Testing

1. Make the broker unavailable after order commit.
2. Restart the publisher and verify the event is sent.
3. Drop publish confirmation and verify consumers create no duplicates.
4. Force payment timeout after authorization.
5. Restart the orchestrator and verify the saga resumes at the right step.
6. Fail void/refund and verify alerts/manual review.
7. Reconcile business state, provider references, and outbox/inbox.

### Deliverables

- Schemas for outbox, inbox, saga instances, and saga steps.
- Transaction boundary diagrams for each service.
- Polling or CDC publisher flow.
- Saga state machine and compensation matrix.
- Test evidence for dual-write failures, duplicate publishes, and partial failures.
- Dashboard for outbox backlog, publish lag, saga states, and compensation failures.
- Runbook for unknown outcomes and manual recovery.

### Self-Check Questions

1. Why does @Transactional not automatically protect both a database write and a broker publish?
2. Where does the outbox persist business state and event intent to guarantee atomicity?
3. Why can a publisher still emit duplicates even when using an outbox?
4. What does a lease token protect, and what does it not protect?
5. How does a polling publisher differ from a CDC publisher?
6. Why do consumers still need an inbox when producers use an outbox?
7. How do outbox and saga solve two different problems?
8. What are the trade-offs between orchestration and choreography?
9. Why is compensation not a rollback?
10. How does voiding an authorization differ from refunding a payment?
11. When a payment times out with an unknown outcome, what should the orchestrator do?
12. Why should saga state and command outbox entries be written in the same local transaction?
13. Within what scope is a Cosmos DB transactional batch bounded?
14. Do DynamoDB Streams make publishing to SQS atomic with DynamoDB?
15. Does Pub/Sub's exactly-once delivery cover Spanner transactions?
16. What conditions push a saga into NEEDS_MANUAL_REVIEW?

## 31. Takeaways

- The dual-write problem arises when a business database and a broker are updated via two independent operations.
- Transactional outbox writes business state and event intent in the same local transaction; a publisher sends after commit.
- Outbox does not guarantee publish-exactly-once. Publishers may resend when acknowledgments are unclear; stable event IDs and inboxes protect consumers.
- Polling and CDC are two ways to detect outbox entries; both require managing offsets/leases, retries, ordering, and duplicates.
- Consumer inboxes must commit alongside business state in one transaction; ACK after commit per broker settlement semantics.
- Sagas break distributed workflows into local transactions and compensation; every step/compensation needs idempotency, timeouts, and durable state.
- Compensation is a new business action that can fail and does not erase committed history.
- Timeouts do not prove side effects did not occur; query/reconcile before retrying or compensating.
- Cosmos DB batches, DynamoDB transactions, Spanner/Firestore transactions, and broker transactions each have distinct scopes; never treat them as cross-service transactions.
- Test crashes after commit, publish unknown outcomes, duplicates, CDC replays, compensation failures, and orchestrator restarts.

## References

- [Transactional outbox pattern — Azure Architecture Center](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos)
- [Azure Cosmos DB transactional batch](https://learn.microsoft.com/azure/cosmos-db/nosql/transactional-batch)
- [Azure Cosmos DB change feed](https://learn.microsoft.com/azure/cosmos-db/change-feed)
- [Azure Service Bus transactions](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-transactions)
- [AWS DynamoDB transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html)
- [DynamoDB Streams](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html)
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [Google Cloud Spanner transactions](https://cloud.google.com/spanner/docs/transactions)
- [Google Cloud Firestore transactions and batched writes](https://firebase.google.com/docs/firestore/manage-data/transactions)
- [Google Cloud Pub/Sub overview](https://cloud.google.com/pubsub/docs/overview)
- [Spring Cloud Stream reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Saga pattern — Azure Architecture Center](https://learn.microsoft.com/azure/architecture/reference-architectures/saga/saga)
- [Microservices.io — Saga pattern](https://microservices.io/patterns/data/saga.html)
- [Microservices.io — Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html)
