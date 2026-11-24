# Exactly-once processing and idempotent side effects

In a Spring Kafka system, a message can be reprocessed even if the producer sent it only once. A consumer may finish its work and stop before committing the offset; on restart or after a rebalance, Kafka redelivers that message. A producer may also resend after a timeout because it does not know whether the broker recorded the prior request.

Therefore, distinguish two goals:

- **Exactly-once processing within Kafka** guarantees that Kafka writes and input offsets commit as one atomic unit in a consume-transform-produce flow.
- **Idempotent side effects** guarantee that a business effect outside Kafka occurs only once in terms of final outcome, even if the same event is delivered or processed multiple times.

The two mechanisms complement each other. Kafka transactions solve data boundaries inside Kafka; idempotency solves boundaries such as databases, HTTP APIs, payments, emails, or external systems.

## 1. Why can a message be processed multiple times?

Kafka consumers typically operate under at-least-once semantics when applications commit offsets after processing. This prioritizes avoiding lost messages, yet creates windows where repeated processing can arise.

For instance, a listener reads a message at offset 42, updates the database successfully, and then the process stops before offset 43 commits. When the partition is reassigned, the consumer reads offset 42 again. The database was already updated, yet Kafka does not know that because the offset remained uncommitted.

| Failure timing | What the consumer can observe | Risk |
|---|---|---|
| Before starting processing | Message produced no effect yet | Message is re-read; usually safe |
| During database or HTTP API call | Unclear whether the effect completed | Retries may repeat the side effect |
| After database commit, before offset commit | Database changed, Kafka still views message as unprocessed | Side effect may run a second time |
| After publishing output, before committing offset | Output may already exist, input still re-read | May produce duplicate outputs |
| Producer timeout after broker wrote message | Producer unsure whether prior request succeeded | Retries may create duplicate records if producer is not idempotent |

You cannot conclude that a listener runs only once simply because the application uses Kafka. A reliable design must explicitly define transaction boundaries and how to handle calls with uncertain outcomes.

## 2. What do Kafka's exactly-once semantics protect?

Kafka provides two related mechanisms:

1. **Idempotent producer** uses sequence numbers per producer and partition so the broker recognizes retried sends. It prevents duplicates arising from retries within the same producer session inside Kafka's managed scope.
2. **Kafka transactions** bundle multiple Kafka writes and consumer offsets into a single transaction. For consume-transform-produce flows, outputs and input offsets commit or abort together.

When a transaction commits, consumers configured with **isolation.level=read_committed** only read records belonging to committed transactions. Records from aborted transactions are not returned to consumers in this mode.

This does not mean the listener callback is invoked strictly once. The listener may run again after a transaction aborts or during application recovery. The exactly-once guarantee applies to committed state inside Kafka: a transaction's output does not become committed data twice merely because an earlier attempt retried.

### 2.1 Producer and consumer configuration

Spring Boot configuration example:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      transaction-id-prefix: ${INSTANCE_ID:local}-orders-
      properties:
        enable.idempotence: true
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

**transaction-id-prefix** instructs Spring Kafka to create transaction-capable producers. The prefix must differ across concurrently running instances; if multiple instances use the same transactional ID, the broker can fence the older producer. In deployment environments, set INSTANCE_ID to a stable, unique identifier per instance.

**enable.idempotence** protects producer retries. **acks: all** requires acknowledgment per Kafka's replication settings. **isolation.level: read_committed** matters for consumers that must observe only committed transactional data. When transactions are enabled for a listener, Spring Kafka manages offset commits within the transaction; do not manually commit offsets before processing completes.

Merely setting transaction-id-prefix does not prove the listener container runs inside a transaction. You must configure **KafkaTransactionManager** on the listener container factory (or confirm your Spring Boot version's auto-configuration wires the manager into the right container). **KafkaTemplate** must use the corresponding producer factory so sends inside the listener enlist in the container's transaction.

### 2.2 Consume-transform-produce in a single transaction

Suppose a service reads OrderCreated from the orders topic and emits InvoiceRequested to the billing-events topic:

~~~java
@Component
public class BillingListener {
    private final KafkaTemplate<String, InvoiceRequested> kafkaTemplate;

    public BillingListener(
            KafkaTemplate<String, InvoiceRequested> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(topics = "orders", groupId = "billing")
    public void onOrder(OrderCreated event) {
        InvoiceRequested output = new InvoiceRequested(
                event.eventId(),
                event.orderId()
        );

        kafkaTemplate.send(
                "billing-events",
                event.orderId(),
                output
        );
    }
}
~~~

This listener achieves consume-transform-produce exactly-once semantics only when the listener container is configured with KafkaTransactionManager and KafkaTemplate participates in the same transaction. When the listener returns normally, the container sends the processed offset into the transaction and commits. If processing fails, the transaction aborts; the output is not exposed as committed data and the offset does not advance, so the message can be re-read.

If the listener sends output using a producer outside the container's transaction, or commits offsets via a separate path, the two operations are no longer atomic. A window then opens to produce duplicate outputs or break input-output coupling.

### 2.3 Transactions for multiple independent Kafka sends

When writing multiple Kafka records as an atomic group outside a listener container, use **KafkaTemplate.executeInTransaction**:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("order-events", orderId, orderEvent);
    operations.send("audit-events", orderId, auditEvent);
    return null;
});
~~~

Both sends commit or abort together. This transaction groups the sends inside the callback; it does not automatically enlist a consumer's offsets. For consume-transform-produce listeners, use container-managed transactions and send through the participating template.

## 3. Kafka transactions do not cover external side effects

Kafka transactions do not automatically create a distributed transaction spanning Kafka, relational databases, and HTTP services. The following example still has bugs:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) {
    paymentClient.charge(event.orderId(), event.amount());
    kafkaTemplate.send("payment-events", event.orderId(),
            new PaymentCompleted(event.orderId()));
}
~~~

If the payment call succeeds yet the Kafka transaction aborts, the message will be re-read and the charge command may run again. If Kafka commits yet the HTTP service never executed the side effect, the two systems drift out of sync. Kafka cannot determine the outcome of an HTTP transaction.

Define guarantee boundaries by side-effect target:

| Write target | Suitable mechanism | Guarantee scope |
|---|---|---|
| One or more Kafka topics | Producer idempotence and Kafka transactions | Kafka records and offsets commit atomically |
| Relational database | Inbox/deduplication in the same DB transaction as business changes | An event produces a DB effect once within the unique key scope |
| HTTP API supporting idempotency keys | Send a stable key per business operation | Depends on target API's idempotency contract |
| HTTP API lacking idempotency | Outbox, state machine, controlled retries, and reconciliation | Reduces risk; cannot guarantee exactly-once via Kafka alone |
| Email or webhook delivery | Provider-side idempotency, or persist send state and reconcile | Depends on receiving system's deduplication capability |

## 4. Designing idempotent side effects

An operation is idempotent if repeating the same request leaves the final outcome unchanged:

~~~text
apply(apply(state, event), event) = apply(state, event)
~~~

For instance, setting an order status to PAID can be idempotent when updating by orderId and target state. Incrementing a balance by 100 on every event receipt is not idempotent: receiving the event again adds money a second time.

### 4.1 Use stable event IDs

Producers should assign a unique eventId to each business event and keep that ID unchanged across all retries or replays. Never generate a new UUID each time a listener reprocesses, or the consumer will treat every attempt as a different event.

Idempotency keys must accurately identify the operation. You can use eventId, or a business key like orderId + operation if multiple distinct events represent one operation. If the same key arrives with a different payload, detect and flag it as a data anomaly rather than silently ignoring it.

### 4.2 Inbox tables and database transactions

For database side effects, store processed event markers using a unique key. Recording the marker and updating business data must live in the same database transaction.

PostgreSQL example:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name text NOT NULL,
    event_id uuid NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

The listener can call the following service. INSERT ... ON CONFLICT DO NOTHING returns the number of inserted rows; if 0, the event was previously recorded by this consumer:

~~~java
@Service
public class OrderProjectionService {
    private final JdbcTemplate jdbc;
    private final InvoiceRepository invoices;

    public OrderProjectionService(
            JdbcTemplate jdbc,
            InvoiceRepository invoices) {
        this.jdbc = jdbc;
        this.invoices = invoices;
    }

    @Transactional
    public void handle(OrderCreated event) {
        int inserted = jdbc.update("""
            INSERT INTO consumer_inbox (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "billing",
            event.eventId()
        );

        if (inserted == 0) {
            return; // Event was already processed successfully previously.
        }

        invoices.insertIfAbsent(
                event.orderId(),
                event.eventId()
        );
    }
}
~~~

insertIfAbsent represents writing an invoice backed by an appropriate unique constraint, such as unique on order_id if each order has one invoice. Database unique constraints are the ultimate defense against concurrent processing; checking with SELECT followed by INSERT is unsafe when two consumers run concurrently.

This sequence provides crucial properties:

1. On the first run, the inbox row inserts and business changes write in the same transaction.
2. If the business update fails, the transaction rolls back the inbox row too. When Kafka redelivers the event, the consumer can retry.
3. If the database commits successfully yet the application stops before Kafka commits the offset, the event redelivers. Next time, the inbox insert conflicts and the service skips the already-completed side effect.
4. If two runs execute concurrently, the unique constraint arbitrates; only the transaction inserting the inbox row proceeds with business logic.

@Transactional in this example is a database transaction. Once the listener calls the service and the service commits, the listener returns so the container commits the offset. A window still exists where the database committed yet the offset has not; the inbox makes that window safe on retry.

Never mark an event processed before the side effect succeeds. If you save an inbox row in a separate transaction and then call a database or HTTP endpoint outside that transaction, a failure between steps can skip retries even though the side effect never happened.

### 4.3 Idempotency keys for HTTP APIs

If the target API supports idempotency keys, send the same key on all attempts of the same operation:

~~~http
POST /payments
Idempotency-Key: order-payment:evt-8d7f...
Content-Type: application/json

{
  "orderId": "ORD-1042",
  "amount": 125000
}
~~~

The provider must store the result tied to the key and return the matching response on repeated requests. Simply adding an Idempotency-Key header creates no guarantee if the target API does not enforce this contract. Verify key retention duration, uniqueness scope, behavior on matching key with differing payload, and responses while the first request is in flight.

If an API lacks idempotency support, timeouts create uncertain state: the request may have executed even though the client received no response. Infinite resending cannot solve this safely. Persist operation state, use business reference codes, query status from the target system when possible, and route indeterminate cases into reconciliation.

## 5. Outbox and inbox in database-to-Kafka flows

### 5.1 Transactional outbox when updating a database and emitting events

A common bug is updating a database and calling kafkaTemplate.send() inside one method expecting @Transactional to make both atomic. If the transaction manager manages only the database, the Kafka call does not automatically join the database transaction.

Transactional outbox solves this by writing business changes and an outbox row inside the same database transaction:

~~~text
Database transaction:
  UPDATE orders ...
  INSERT INTO outbox(event_id, topic, message_key, payload, status)
  COMMIT

Outbox relay:
  read unsent outbox rows
  publish event to Kafka
  mark sent after broker acknowledgment
~~~

If the application stops before commit, both business changes and the outbox row roll back. If commit succeeds before the relay publishes, the row remains for the relay to resume after restart. The relay can publish duplicates if it stops after the broker receives the event before marking the row sent; consumers still need inbox or idempotency keys.

Outbox turns event emission into a retryable, reconcilable task. It does not make network publishing itself exactly-once; it ensures events stay coupled to business write transactions while accepting at-least-once relaying.

### 5.2 Inbox when consumers write to a database

Inbox sits on the receiving side: it records applied event IDs in the same transaction as business changes. Combining outbox and inbox forms a reliable pipeline:

~~~text
Service A                         Kafka                         Service B
---------                         -----                         ---------
DB: business row + outbox
          |
          v
      Outbox relay  ---------->  event  ---------------------> Inbox insert
                                                               + DB update
                                                               one DB commit
~~~

This design still allows retries in both relay and consumer, yet every retry carries a stable key to detect already-completed operations.

## 6. Retries, dead-letter topics, and replays

Retries are a normal part of reliable processing. Idempotency keys must remain unchanged across listener retries, rebalance retries, dead-letter topic (DLT) routing, and manual replays.

Practical rules:

- Record an event as complete only in the same transaction as the side effect it protects.
- Let exceptions propagate out of the listener when processing fails so the container applies retries or error handlers. Never catch exceptions and return success when the side effect did not complete.
- Separate transient errors (timeouts, network faults, database unavailability) from non-recoverable data errors (bad schema, missing required fields). Cap retries and route intervention-required errors to a DLT.
- When replaying from a DLT, preserve the original event ID. If business rules require re-running an already-completed operation, create a new command/event with a new business identity and explicit rules.
- Set inbox retention longer than the maximum event replay window. Purging inbox markers too early lets old replays repeat side effects.
- Track event IDs and business keys in logs/traces to correlate end-to-end across producer, Kafka, consumer, and target systems.

For HTTP timeouts, never mark the inbox complete simply because the request was sent. Mark complete only after receiving confirmation or after reconciliation determines the final state. If indeterminate, store UNKNOWN/PENDING_RECONCILIATION for controlled handling.

## 7. Testing failure windows

A test that only sends a message happily does not prove exactly-once or idempotency. Actively simulate possible stopping points:

| Scenario | What to verify |
|---|---|
| Producer resends after timeout | Idempotent producer creates no duplicates from retries within the same producer session |
| Listener sends output then throws before commit | Transaction aborts; read_committed consumer does not see aborted output |
| Listener completes transaction | Output and input offset commit together |
| Database commits, process stops before offset commit | Kafka redelivers event yet inbox prevents repeated DB side effects |
| Two consumers process same event concurrently | Unique constraint grants processing ownership to only one transaction |
| HTTP API succeeds yet client times out | Retry with same idempotency key returns prior result or reconciliation detects state |
| Event replayed from DLT | Old event ID is recognized; already-completed side effects do not re-run |
| Relay publishes then stops before updating outbox | Event may be resent yet consumer processes idempotently |

Beyond final state, monitor duplicate-skipped counts, retry counts, DLT counts, transaction aborts, consumer lag, outbox row age, and operations awaiting reconciliation. These signals distinguish normal retries from prolonged outages or stuck data.

## 8. Choosing mechanisms by data flow

| Flow | Recommended design |
|---|---|
| Kafka → Kafka | Listener container transactions + KafkaTransactionManager + KafkaTemplate sharing producer factory; downstream consumers use read_committed |
| Kafka → database | Inbox with unique key and business updates in one DB transaction; commit offset only after service succeeds |
| Kafka → HTTP/payment | Target-API-supported idempotency key; if unavailable, persist state and combine controlled retries with reconciliation |
| Database → Kafka | Transactional outbox; relay can retry, receiving consumers use inbox/idempotency |
| Kafka → email/webhook | Prefer target APIs with idempotency; persist send status and handle indeterminate outcomes |

When designing a Spring Kafka listener, answer three questions before implementing: which transaction manages offsets, which transaction manages side effects, and which key identifies the same operation across all retries? Whenever two actions span systems that share no transaction, design idempotency or outbox/inbox across that boundary. That is how at-least-once delivery becomes safe business outcomes resilient to retries, crashes, and replays.
