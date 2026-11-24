# RabbitMQ Transaction Boundaries with Database Updates

In a Spring Boot system, writing to a database and sending or receiving RabbitMQ messages often belong to the same business workflow, yet **they do not automatically participate in one atomic transaction**. This is a core principle when integrating HTTP, databases, caches, and message brokers: you must clearly separate who committed data, who accepted the message, who finished processing, and how to recover when any step fails.

Running example: the **Order** service saves an order in PostgreSQL and emits an **OrderCreated** event to RabbitMQ; the **Inventory** service receives the event, updates reserved stock counts, and acknowledges the message. Business requirements demand zero lost events for committed orders and zero double-deductions of inventory when RabbitMQ redelivers the same event.

## 1. Transactions and Confirmation Signals Have Different Scopes

| Mechanism | Protection Scope | What It **Does Not** Guarantee |
| --- | --- | --- |
| JDBC/JPA transaction with **@Transactional** | SQL operations sharing one transaction manager and DB connection within the same boundary | Does not make RabbitMQ commit or roll back alongside the database |
| AMQP channel transaction (**tx.select**, **tx.commit**, **tx.rollback**) | Eligible AMQP operations on that single channel | Not a distributed transaction with PostgreSQL; does not replace publisher confirms |
| **Publisher confirm** | Broker confirms receipt and handling of a publish under broker guarantees and queue type | Does not confirm consumer processing; a successful confirm can still accompany a returned unroutable message |
| **Publisher return** with **mandatory=true** | Detects messages that cannot be routed to any queue | Does not confirm consumer business processing |
| **Consumer acknowledgment (ack)** | Consumer signals the broker that the delivery is settled and can leave the queue | Does not commit the consumer's database; ACKing before DB commit risks losing work |
| **Persistent message + durable queue** | Improves survival across broker restarts when properly configured; quorum queues are often chosen for replication/durability | Does not close the gap between SQL commit and publish |

In Spring Boot, **@Transactional** uses a transaction manager tied to its configured resource—for example, **JpaTransactionManager** controls JPA transactions on PostgreSQL. **RabbitTemplate** sends messages to an external broker over AMQP; placing both calls inside one **@Transactional** method does not turn them into a global transaction.

Distinguish four milestones clearly:

- **DB commit**: order changes have been accepted in the database.
- **Broker confirm**: broker acknowledged the publish command; also inspect returns to verify routing.
- **Consumer DB commit**: business updates in the receiving service are durable.
- **Consumer ack**: broker receives signal to remove the delivery from the queue.

These are four independent boundaries. Integration design must handle process crashes in any gap between them.

## 2. Why Writing to the DB Then Publishing Directly Causes Dual-Write Bugs

The following code looks clean yet fails consistency:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final RabbitTemplate rabbitTemplate;

    public OrderService(OrderRepository orders, RabbitTemplate rabbitTemplate) {
        this.orders = orders;
        this.rabbitTemplate = rabbitTemplate;
    }

    @Transactional
    public void createOrder(CreateOrderCommand command) {
        Order order = orders.save(Order.from(command));
        rabbitTemplate.convertAndSend(
                "domain.events", "order.created",
                new OrderCreated(order.getId()));
    }
}
~~~

Under standard settings, **convertAndSend** returns after dispatching through the client without guaranteeing the broker persisted and routed the message. Furthermore, JPA transactions typically commit **after the @Transactional method returns**. Failure scenario:

1. RabbitMQ accepts the message.
2. Database commit fails (e.g., constraint violation or lost connection).
3. Inventory Service receives an **OrderCreated** event for an order that does not exist.

Flipping the order to **commit DB first, publish second** introduces another failure:

1. Order commits successfully.
2. Process dies before publish runs, or the broker rejects the publish.
3. The order exists in the DB with no event ever emitted to Inventory.

~~~mermaid
flowchart TD
    A["Create order request"] --> B["Write order to DB"]
    B --> C{"DB committed?"}
    C -->|No| D["Rollback DB"]
    C -->|Yes| E["Publish to RabbitMQ"]
    E --> F{"Broker received and routed?"}
    F -->|Yes| G["Continue workflow"]
    F -->|No / process crashed| H["Order saved yet event may be lost"]
~~~

This is the **dual-write problem**: two independent resources must reflect one business outcome without a transaction coordinator guaranteeing atomic commit or rollback across both.

### Does Putting RabbitMQ in an AMQP Transaction Solve This?

Spring AMQP supports **channelTransacted=true** for AMQP channel transactions. When an outer database transaction is active, Spring AMQP can synchronize the channel transaction via **best-efforts one-phase commit**. That rolls back both sides for many ordinary exceptions, yet **provides no two-phase atomic guarantee**: the DB can commit successfully and the subsequent AMQP commit can fail, leaving no way to undo the committed DB row.

Therefore:

- Use AMQP transactions only when local channel-level batching/atomicity is desired, fully aware of their limits.
- Never treat **channelTransacted=true** as a solution to RabbitMQ–DB dual-write.
- Publisher confirms and AMQP transactions are distinct channel models; never combine them on the same channel.
- For business mutations requiring guaranteed post-commit events, the standard pattern is **Transactional Outbox** paired with **idempotent** consumers.

## 3. Transactional Outbox: Writing Business Data and Event Intent in One DB Transaction

Idea: instead of publishing to RabbitMQ inside the order-creation transaction, insert an **outbox_event** row inside **the exact same database** holding the order. Both records commit or roll back atomically. A separate relay process reads the outbox and publishes to RabbitMQ, retrying on failures.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as PostgreSQL
    participant Relay as Outbox Relay
    participant MQ as RabbitMQ
    participant Consumer as Inventory Consumer
    API->>DB: BEGIN; INSERT order; INSERT outbox
    DB-->>API: COMMIT succeeded
    Relay->>DB: Claim unsent outbox rows
    DB-->>Relay: eventId + payload
    Relay->>MQ: Publish OrderCreated(eventId)
    MQ-->>Relay: Publisher confirm (+ return check)
    Relay->>DB: Mark outbox SENT
    MQ->>Consumer: Deliver event
    Consumer->>DB: Business transaction + inbox
    DB-->>Consumer: COMMIT
    Consumer-->>MQ: ACK
~~~

### 3.1. Illustrative PostgreSQL Schema

~~~sql
CREATE TABLE outbox_event (
    id              uuid PRIMARY KEY,             -- also serves as eventId
    aggregate_type  varchar(80) NOT NULL,
    aggregate_id    uuid NOT NULL,
    event_type      varchar(120) NOT NULL,
    payload         jsonb NOT NULL,
    status          varchar(16) NOT NULL DEFAULT 'PENDING',
    attempts        integer NOT NULL DEFAULT 0,
    available_at    timestamptz NOT NULL DEFAULT now(),
    claimed_until   timestamptz,
    lease_token     uuid,
    created_at      timestamptz NOT NULL DEFAULT now(),
    published_at    timestamptz,
    CONSTRAINT outbox_status_check
        CHECK (status IN ('PENDING', 'CLAIMED', 'SENT'))
);

CREATE INDEX outbox_pending_idx
    ON outbox_event (available_at, created_at)
    WHERE status = 'PENDING';
~~~

The outbox row's **id** is the immutable event identifier. Across retries, the relay must preserve the exact **eventId** and payload rather than minting new IDs. The **payload** should contain the event type, schema version, occurrence timestamp, and required business keys—never rely on consumers deserializing source-service Java entities.

### 3.2. Writing the Outbox Inside the Order Creation Transaction

This concise example uses Spring Data JPA for the order and **JdbcTemplate** for the outbox. Both must share **the same configured DataSource and transaction manager** to participate in one DB transaction.

~~~java
public record OrderCreatedEvent(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        int schemaVersion) {}

@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public OrderApplicationService(
            OrderRepository orders, JdbcTemplate jdbc, ObjectMapper mapper) {
        this.orders = orders;
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Transactional
    public UUID createOrder(CreateOrderCommand command)
            throws JsonProcessingException {
        Order order = orders.save(Order.from(command));
        OrderCreatedEvent event = new OrderCreatedEvent(
                UUID.randomUUID(), order.getId(), Instant.now(), 1);

        jdbc.update("""
                INSERT INTO outbox_event
                    (id, aggregate_type, aggregate_id, event_type, payload)
                VALUES (?, 'Order', ?, 'OrderCreated', CAST(? AS jsonb))
                """,
                event.eventId(),
                event.orderId(),
                mapper.writeValueAsString(event));

        return order.getId();
    }
}
~~~

If inserting the outbox row fails, the entire order transaction rolls back. If inserting the order fails, the outbox rolls back too. The API can return immediately after DB commit **without waiting for RabbitMQ availability**; publishing occurs asynchronously.

Spring transaction note: **@Transactional** requires calls to pass through a Spring proxy, so **self-invocation** within the same bean bypasses transaction advice. Never touch two separate databases or transaction managers assuming shared atomicity.

### 3.3. Batch-Claiming Rows by Relay to Prevent Multi-Instance Duplicate Sends

Across multiple replicas, simply running **SELECT ... WHERE status = 'PENDING'** lets multiple workers send the same row concurrently. One solution is **lease-based claiming** in a short DB transaction. PostgreSQL example (passing **:batchSize** and **:leaseToken** from code):

~~~sql
WITH picked AS (
    SELECT id
    FROM outbox_event
    WHERE (status = 'PENDING' AND available_at <= now())
       OR (status = 'CLAIMED' AND claimed_until < now())
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE outbox_event AS e
SET status = 'CLAIMED',
    lease_token = :leaseToken,
    claimed_until = now() + interval '60 seconds',
    attempts = attempts + 1
FROM picked
WHERE e.id = picked.id
RETURNING e.id, e.event_type, e.payload, e.lease_token;
~~~

The claim transaction must **commit before calling RabbitMQ** so DB row locks are never held across network waits. Once the broker confirms success, the relay marks the row sent only if it still owns the lease:

~~~sql
UPDATE outbox_event
SET status = 'SENT',
    published_at = now(),
    lease_token = NULL,
    claimed_until = NULL
WHERE id = :eventId
  AND status = 'CLAIMED'
  AND lease_token = :leaseToken;
~~~

If publishing fails, return the row to **PENDING** with a future **available_at** (exponential backoff + jitter), record the error, and retry. If a relay crashes while holding a lease, expired **CLAIMED** rows become eligible for another instance to reclaim. Under heavy load, size leases comfortably above publish timeouts to avoid overlapping sends—while still designing for duplicate deliveries and consumer idempotency.

### 3.4. Publisher Confirms and Mandatory Returns

Illustrative config:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

A send helper can await **publisher confirm** per outbox event:

~~~java
// Illustrates publishing one row; caller handles claiming, retries, and marking SENT.
void publishOne(OutboxRow row, RabbitTemplate rabbitTemplate)
        throws Exception {
    CorrelationData correlation = new CorrelationData(row.id().toString());

    rabbitTemplate.convertAndSend(
            "domain.events",
            "order.created",
            row.payloadJson(),
            message -> {
                message.getMessageProperties()
                        .setMessageId(row.id().toString());
                message.getMessageProperties()
                        .setContentType(MessageProperties.CONTENT_TYPE_JSON);
                message.getMessageProperties()
                        .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                return message;
            },
            correlation);

    CorrelationData.Confirm confirm =
            correlation.getFuture().get(10, TimeUnit.SECONDS);

    if (!confirm.isAck()) {
        throw new IllegalStateException(
                "RabbitMQ nack: " + confirm.getReason());
    }
    if (correlation.getReturned() != null) {
        throw new IllegalStateException(
                "Message was returned as unroutable");
    }
}
~~~

In Spring AMQP with **publisher-confirm-type=correlated**, publishers observe results via **CorrelationData**. With returns and mandatory enabled, returned message info is populated before the confirm future completes; the relay must inspect **both** confirm and return. A broker-**acked** publish can still be **returned** if the exchange matches no queues. On timeout or connection loss, the outcome is **uncertain**: the broker may already have persisted the message without the app knowing. Hence, **do not mark SENT** and allow resending with the same `eventId`.

In production applications, you can use callbacks and asynchronous confirm handling instead of blocking a thread per event. Either way, update **SENT** only upon proof meeting system criteria. Broker-side durability also depends on queue type, exchange/queue durability, delivery mode, and RabbitMQ cluster setup.

## 4. Consumer Processing Boundary: Commit DB First, Ack After

Even with a producer outbox, RabbitMQ can still **redeliver the same event**. For example, the consumer updates its DB and crashes before the broker receives **ack**. Seeing an unacknowledged delivery, the broker redelivers it. Without deduplication, inventory could be reserved twice.

A safe ordering for consumer DB state is:

1. Receive the message, extract **eventId**, and validate the payload/contract.
2. Inside **one DB transaction**, insert the processed-event marker (**inbox**) and apply business updates.
3. Wait for **DB commit to succeed**.
4. Only then **ack** the delivery to RabbitMQ.

If step 2 fails, both the inbox marker and business updates roll back; the unacked message is retried or routed to a DLQ per error policy. If step 4 fails, the message may redeliver, and the inbox safely skips duplicate work.

### 4.1. Inbox Table and Idempotent Handler

~~~sql
CREATE TABLE processed_event (
    consumer_name varchar(100) NOT NULL,
    event_id      uuid NOT NULL,
    processed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Example **InventoryService** handling the event inside one DB transaction:

~~~java
@Service
public class InventoryService {
    private final JdbcTemplate jdbc;
    private final InventoryRepository inventory;

    public InventoryService(
            JdbcTemplate jdbc, InventoryRepository inventory) {
        this.jdbc = jdbc;
        this.inventory = inventory;
    }

    @Transactional
    public void reserveForOrder(OrderCreatedEvent event) {
        int inserted = jdbc.update("""
                INSERT INTO processed_event (consumer_name, event_id)
                VALUES ('inventory-reservation', ?)
                ON CONFLICT DO NOTHING
                """, event.eventId());

        if (inserted == 0) {
            return; // This eventId already committed earlier
        }

        inventory.reserve(event.orderId()); // DB update in same transaction
    }
}
~~~

The composite primary key **(consumer_name, event_id)** prevents two concurrent transactions from processing duplicate messages while allowing multiple independent consumer groups to share the inbox infrastructure. If **inventory.reserve** throws an exception, the inbox insert rolls back too so the message can retry. When multiple event types mutate the same entity, you also need business-level locks/guards (e.g., unique **order_id**, state-transition checks, optimistic locking); an `eventId` inbox alone only deduplicates **the same event**.

### 4.2. Ack After the Processing Transaction Returns

~~~java
@Component
public class OrderCreatedListener {
    private final ObjectMapper mapper;
    private final InventoryService inventoryService;

    public OrderCreatedListener(
            ObjectMapper mapper, InventoryService inventoryService) {
        this.mapper = mapper;
        this.inventoryService = inventoryService;
    }

    @RabbitListener(queues = "order.created.queue", ackMode = "MANUAL")
    public void onMessage(Message message, Channel channel)
            throws IOException {
        long deliveryTag = message.getMessageProperties().getDeliveryTag();
        try {
            OrderCreatedEvent event = mapper.readValue(
                    message.getBody(), OrderCreatedEvent.class);

            // Invoked on another bean: InventoryService's transaction
            // has already committed when this call returns normally.
            inventoryService.reserveForOrder(event);
        } catch (Exception processingFailure) {
            // Example for a queue configured with DLX; production must classify
            // transient failures for bounded retry and backoff.
            channel.basicNack(deliveryTag, false, false);
            return;
        }
        channel.basicAck(deliveryTag, false);
    }
}
~~~

This uses **MANUAL ack** to make commit and ack points explicit. Listener container **ackMode=AUTO** can also work when the listener returns only after the DB transaction commits, since the container ACKs on normal return. Still, verify container transaction/advice settings and exception policies to ensure ACKs never fire pre-commit.

Notes:

- Never call **basicAck** inside a **@Transactional** method while its transaction has not yet committed.
- **basicNack(requeue=false)** routes to a DLQ only if the queue has a matching dead-letter exchange/routing; otherwise messages may be dropped. Production code must separate transient errors (DB timeout) from permanent ones (bad schema version), using bounded retries, backoff, and DLQ.
- If **basicAck** fails after DB commit, accept redelivery; the inbox handles it.
- Never invoke non-DB side effects (sending email, calling payment APIs, publishing follow-up events) directly inside the inbox transaction assuming atomicity. Instead, write a **new outbox** record in the consumer service and follow the same pattern.

## 5. Failure Matrix: What Happens and How the System Recovers

| Failure Point | Post-Failure State | Safe Recovery |
| --- | --- | --- |
| Order creation transaction rolls back pre-commit | No order and no outbox row | Return request error; emit no event |
| Order and outbox commit; relay has not sent yet | Outbox in PENDING/CLAIMED; queue lacks event | Relay polls again or reclaims after lease expiry |
| Broker received yet confirm timed out/lost | Publish outcome uncertain; outbox not SENT | Resend **same eventId**; consumer deduplicates |
| Broker confirms ack yet message returned | No matching queue received message | Do not mark SENT; fix exchange/binding/routing and retry |
| Relay receives confirm yet crashes before marking SENT | Message may already be in queue; outbox still retries | Resend; consumer deduplicates |
| Consumer fails before DB commit | Both inbox and business updates roll back | Retry with backoff or route to DLQ |
| Consumer DB commits, process dies before ack | Business updated; RabbitMQ may redeliver | Inbox recognizes eventId, skips duplicate work, and acks |
| Consumer acks pre-commit then DB rolls back | Broker deleted delivery yet work was lost | **Design bug**; fix order to commit before ack |

This matrix yields a **practical guarantee**: outbox + publisher confirms + retries provide **at-least-once** publishing; inbox + commit-before-ack makes **DB effects per `eventId`** effectively once within the DB transaction boundary. This is **not** global end-to-end exactly-once for arbitrary external side effects, and ordering across distinct events is not guaranteed automatically by RabbitMQ or the outbox.

## 6. Comparing Implementation Approaches by Consistency Needs

| Approach | Characteristics | Best Suited For |
| --- | --- | --- |
| Write DB then call **RabbitTemplate** directly | Simple to code; crash gap between both systems | Best-effort notifications where rare loss is acceptable |
| **@TransactionalEventListener(phase=AFTER_COMMIT)** then publish | Publishes only post-commit; still loses events on crash before/during publish without durable recovery queue | Best-effort systems or flows with separate reconciliation |
| **channelTransacted=true** with external DB transaction | Best-efforts 1PC sync; gap remains when one commits and the other fails | Cases with known trade-offs not needing cross-resource atomicity |
| **Transactional Outbox + confirms + retry** | Zero lost publish intent once business transaction commits; allows duplicates | Critical business events requiring recoverability and visibility |
| **Outbox + idempotent consumer/inbox** | Protects both emission and consumer DB processing on redelivery | High-reliability asynchronous workflows |

If low latency matters more than rare loss, simpler approaches may suffice. For orders, payments, inventory reservations, access grants, or audit trails, define required consistency explicitly before choosing a pattern.

## 7. Operational Details Easily Overlooked

### 7.1. Idempotency and Business Keys

**eventId** must remain fixed across retries; independent services can process the same `eventId` by recording under their own **consumer_name**. If two events with distinct IDs request the same one-time business action (e.g., same `paymentId`), add a unique constraint on the business key—not solely on `eventId`.

Skipping a duplicate `eventId` must occur **only against committed processing evidence**. Never rely solely on an un-transactional Redis cache as proof of processing if cache loss would cause duplicate execution. Redis can accelerate checks, yet consistency invariants must rest on the DB or business design.

### 7.2. Event Ordering

Two events for the same order—such as **OrderCreated** and **OrderCancelled**—can arrive out of order due to multiple relays, retries, multiple queues, or concurrent consumers. When ordering matters, include **aggregateId** and **sequence/version** in payloads, publish sequentially per aggregate, or enforce version/state guards at consumers. Ordering by **created_at** in an outbox query alone does not guarantee end-to-end execution order.

### 7.3. Data Contracts and Security

Include **schemaVersion**, UTC timestamps, and stable IDs; propagate trace/correlation IDs to link logs from HTTP requests through the outbox, RabbitMQ, and consumers. Keep tokens, passwords, card data, and unnecessary PII out of payloads and error logs. Consumers must validate required fields and handle unsupported event versions explicitly.

### 7.4. Monitoring and Incident Response

Monitor at minimum:

- **Outbox backlog**: count of PENDING/CLAIMED rows, oldest row age, DB-commit-to-publish latency.
- **Publish health**: confirm nack/timeout rates, returned messages, retry counts, expired leases, and stuck rows.
- **Consumer health**: unacked message count, redelivery rate, processing latency, DB errors, queue depth, and DLQ depth.
- **Business data**: reconcile committed orders against emitted events and downstream state with safe replay tooling.

Alert whenever outbox rows fail to drain within thresholds, DLQs grow, or latency climbs steadily. Never delete failing rows simply to "clear queues"; preserve error context, support controlled retries/replays, and enforce retention/archival policies on **SENT** rows.

## 8. Testing Transaction Boundaries

Unit testing method calls is insufficient. Build an integration test suite using real PostgreSQL and real RabbitMQ in isolation (e.g., Testcontainers) and deliberately exercise:

1. **Atomic rollback:** fail outbox insertion and verify zero orders commit.
2. **Broker unavailable:** commit orders and outbox while RabbitMQ is stopped; start the relay afterward and verify events publish.
3. **Lost confirm:** simulate timeout after broker receipt; verify relay resends the **same eventId** and the consumer mutates the DB only once.
4. **Unroutable publish:** publish to an exchange with an unmatched routing key; verify returns are captured and outbox does not become SENT.
5. **Crash after consumer DB commit:** withhold ack to trigger redelivery; verify only one inbox row and one stock deduction exist.
6. **Concurrent processing:** deliver the same `eventId` across competing consumer instances; unique constraint + transaction must prevent duplicate effects.
7. **Malformed data:** send unsupported version or missing fields; verify retry/DLQ obeys policy without infinite loops.
8. **Ordering tests:** where ordering matters, swap two events for the same aggregate and verify version rules hold.

Example acceptance criterion for order creation: **Once the API returns success, either `OrderCreated` is eventually processed, or the system retains an observable, retryable outbox record; any redelivery of the same `eventId` never reserves inventory a second time.** That criterion is far more concrete than claiming "DB and RabbitMQ share `@Transactional`."

## 9. Pre-Production Checklist

- [ ] Persist **business row + outbox row** inside **one DB transaction** with contract checks and idempotency keys.
- [ ] Equip relays with claim/lease, backoff retries, timeouts, confirm/return handling, and backlog monitoring.
- [ ] Align exchange, bindings, queue durability, delivery mode, and broker replication with required reliability.
- [ ] Commit consumer business data and inbox before acking; handle redeliveries and permanent failures with a DLQ.
- [ ] Protect third-party consumer side effects with dedicated idempotency/outbox strategies.
- [ ] Test crashes in gaps between DB commit, publish confirm, marking SENT, and consumer ack.
- [ ] Maintain reconciliation, replay procedures, alerts, and outbox/inbox retention/cleanup rules.

**Core rule to remember:** **@Transactional** protects only the transaction manager and resources it manages. When RabbitMQ and a database participate in one business action, the safe pattern is **commit event intent alongside business data via an outbox, publish with confirms and retries, process at consumers with an inbox/idempotency, and ack only after DB commit**. This design embraces eventual consistency and possible duplicates while providing explicit recovery paths for real-world failures.
