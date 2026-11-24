# Side effects outside transactions

A Kafka consumer usually does more than just read a record and update an offset. It may call a payment gateway, send an email, write to a database, create a file, update object storage, or call another service. These operations lie outside Kafka's transaction. If a side effect succeeds yet the process stops before the offset is committed, Kafka may redeliver the record and the consumer may execute the side effect again.

This is a critical boundary of **correctness and idempotency**: Kafka transactions can coordinate reading/writing Kafka data within one transaction, but they cannot automatically roll back an HTTP request already sent to an external system, an email already delivered, or a file already written. To operate reliably, applications must be designed for crash windows, ambiguous timeouts, retries, and replays.

This lesson belongs to the **Correctness and Idempotency** chapter of Spring Kafka Reliability Operations. It focuses on how to handle **side effects outside transactions** in Spring Kafka: identifying atomic boundaries, designing idempotency keys, using inbox/outbox patterns, decoupling side effects from listeners when appropriate, coordinating retries/DLTs, building sagas/compensation, and testing failure scenarios.

## 1. What does a Kafka transaction protect?

With a Kafka transaction, a producer can send multiple records and commit them as a single unit. In a consume-process-produce model, Spring Kafka can include consumer offsets in the same Kafka transaction as output records. Consumers configured with an appropriate isolation level, typically `read_committed`, only see committed transactional records.

~~~text
Kafka input topic
      |
      v
Consumer poll
      |
      v
Listener processing
      |
      +---- KafkaTemplate.send(output)
      |
      v
Kafka transaction commit
      |
      +---- Output records are committed
      |
      +---- Input offsets are committed
~~~

If the transaction aborts, transactional outputs are not seen as committed by `read_committed` consumers, and input offsets in that transaction do not advance. Input records can be redelivered.

That guarantee applies **inside Kafka**. The transaction does not automatically cover:
- SQL updates on a database not participating in the same distributed transaction.
- HTTP requests to a payment provider or REST service.
- Emails, SMS, or push notifications.
- Files on a filesystem or object storage.
- Tasks creating invoices, calling accounting systems, or external devices.

Example:

~~~text
Kafka listener
    |
    +-- Kafka transaction open
    |
    +-- HTTP POST /payments -> provider charge succeeds
    |
    +-- Kafka transaction aborts
             |
             v
       Input record is redelivered
             |
             v
       HTTP POST /payments again
             |
             v
       Risk of double charge
~~~

Kafka can roll back output records and offsets, but cannot ask a payment provider to undo a charge simply by aborting a Kafka transaction.

## 2. Why can side effects execute multiple times?

Suppose a listener reads a `PaymentRequested` event, calls a payment API, and then commits the offset:

~~~text
1. poll record E
2. call payment API
3. payment API returns SUCCESS
4. process crashes
5. Kafka offset uncommitted
6. consumer restarts and reads E
7. call payment API again
~~~

This is a common failure window. The consumer may have completed the side effect without recording progress in Kafka. With at-least-once delivery, redelivering the record is valid behavior.

A timeout is even harder:

~~~text
Consumer sends HTTP request
       |
       v
Provider executes charge successfully
       |
       v
Response is lost or client times out
       |
       v
Consumer does not know true outcome
       |
       v
Retry request
~~~

A timeout only says the client did not receive a response in time; it **does not prove the server never executed the operation**. If you retry with a new request identity, the side effect can happen twice.

Design must handle all of:
- Crash after side effect succeeds but before offset commits.
- Timeout after the server has received and processed the request.
- Consumer rebalance while the listener is running.
- Retries after transient errors.
- DLT replays hours or days later.
- Operators re-running the same event to recover data.

## 3. Distinguishing delivery guarantees from side-effect guarantees

| Concept | What it guarantees | What it does not automatically guarantee |
|---|---|---|
| At-most-once | Records are not reprocessed per commit-before-processing policy. | Records can be lost if processing fails after commit. |
| At-least-once | Records not yet confirmed successful may be redelivered. | Side effects outside Kafka may repeat. |
| Kafka transactions / exactly-once processing in Kafka | Coordinates Kafka output records and input offsets inside a Kafka transaction per config. | Does not automatically make HTTP, email, databases, or filesystems exactly-once. |
| Idempotent side effect | Multiple requests for the same logical operation yield one business outcome. | Does not automatically ensure ordered delivery or eventual success of every request. |
| Effectively-once business outcome | Retries/replays may occur, yet business outcomes are deduplicated or reconciled. | Not broker magic; requires durable design and state storage. |

In distributed systems, the term "exactly once" must always attach to a **specific boundary**. A Kafka-to-Kafka pipeline can have exactly-once semantics within a Kafka transaction. A workflow calling a payment API and sending emails typically needs idempotency, outbox/inbox, or sagas to achieve an effectively-once business outcome.

## 4. Identifying transaction boundaries in a listener

Example of a listener calling a database and an external API:

~~~java
@KafkaListener(topics = "payments.requested")
public void handle(PaymentRequested event) {
    paymentRepository.markProcessing(event.paymentId());

    paymentGateway.charge(
            event.paymentId(),
            event.amount());

    paymentRepository.markPaid(event.paymentId());
}
~~~

This snippet carries several risks:
- If the first DB update commits and the HTTP call fails, state can be left dangling.
- If the payment provider charges successfully yet the response times out, the consumer does not know the outcome.
- If the process crashes after charging before offset commit, the event can be redelivered.
- If the listener transaction is only a Kafka transaction, the two DB updates are not rolled back by Kafka.
- If a DB transaction is held open across the HTTP call, connections/locks may be held during slow network I/O; DB rollback still does not reverse an already-executed charge.

Identify clearly **which transaction protects each change**. Annotating a method with `@Transactional` does not make every external resource it touches part of one atomic transaction. A transaction manager only manages resources it supports and that are properly enlisted.

## 5. Do not hold a database transaction open while waiting on HTTP

Easy to write, dangerous in practice:

~~~java
@Transactional
public void process(PaymentRequested event) {
    paymentRepository.markProcessing(event.paymentId());

    paymentGateway.charge(event.paymentId(), event.amount());

    paymentRepository.markPaid(event.paymentId());
}
~~~

If the external API takes 20 seconds, the DB connection and transaction may be held for 20 seconds. Consequences:
- Connection pool exhaustion under traffic spikes.
- Prolonged row/table locks.
- Deadlocks or lock contention.
- Transaction timeouts.
- Retries adding load onto both DB and provider.
- DB rollback still fails to undo the side effect already executed at the provider.

For non-rollbackable side effects, split the workflow into steps with durable state: record intent, call the provider with an idempotency key, then record the outcome. This makes crash windows observable and recoverable.

## 6. Idempotency keys for external APIs

If the provider supports idempotency, send a **stable key for the same logical operation** on every retry.

~~~java
public PaymentResult charge(PaymentRequested event) {
    String idempotencyKey = event.paymentId();

    return paymentClient.charge(
            event.paymentId(),
            event.amount(),
            idempotencyKey);
}
~~~

HTTP example:

~~~http
POST /v1/payments
Idempotency-Key: payment-4821
Content-Type: application/json

{
  "paymentId": "payment-4821",
  "amount": 125000
}
~~~

The provider stores the outcome tied to the key and returns the corresponding response on repeated requests per its contract. Check carefully:
- How long is the key retained?
- How does the provider handle the same key with a different payload?
- Are two concurrent requests with the same key serialized/deduplicated?
- Is the replayed response identical to the original response?
- Is the key scoped per merchant/account/endpoint?
- After the key's retention expires, could an old retry create a new charge?

**Do not generate a new UUID on each retry.** The key must derive from the event or logical operation and be durably stored so every redelivery uses the exact same value.

A single shared event ID may not suffice if one event triggers multiple side effects. For instance, an order might charge payment, reserve inventory, and issue an invoice; use per-operation idempotency keys such as `eventId + ":charge"` and `eventId + ":reserve"`. Each side effect has its own state and deduplication rules.

## 7. When the provider does not support idempotency

Not every external API offers an idempotency key. In such cases, you can:
- Use a stable external reference that the provider allows querying.
- Create a request record before calling the provider and mark it `PENDING`.
- After a timeout, query the provider by reference before deciding to resend.
- Periodically reconcile requests with uncertain outcomes.
- Transition indeterminate cases to `UNKNOWN` for controlled handling.
- Establish a manual review workflow for side effects that cannot be auto-confirmed.

Never blindly retry a non-idempotent command after a timeout. If the provider neither allows querying by reference nor supports deduplication, the application cannot prove the first request did not execute. That is an external contract limitation requiring a business process solution.

## 8. Using the inbox pattern to deduplicate events in the database

When a consumer updates a database, a common pattern is writing an **inbox/processed-event marker** in the same DB transaction as the business update.

Example table:

~~~sql
CREATE TABLE processed_event (
    event_id       VARCHAR(100) PRIMARY KEY,
    processed_at   TIMESTAMP NOT NULL
);
~~~

Processing service:

~~~java
@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(OrderCreated event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_event(event_id, processed_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId());

        if (inserted == 0) {
            // Event was already processed in a previous transaction.
            return false;
        }

        jdbc.update("""
            UPDATE order_projection
               SET status = ?, total_amount = ?
             WHERE order_id = ?
            """,
            "CREATED",
            event.totalAmount(),
            event.orderId());

        return true;
    }
}
~~~

This SQL example follows PostgreSQL (`ON CONFLICT`). For other databases, use equivalent insert-if-absent syntax or unique constraints. Ensure marker and business update use **the same database transaction and the same transaction manager**.

Listener:

~~~java
@Component
public class OrderCreatedListener {

    private final OrderProjectionService service;

    public OrderCreatedListener(OrderProjectionService service) {
        this.service = service;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-projection-v1"
    )
    public void consume(OrderCreated event) {
        service.applyOnce(event);
    }
}
~~~

If the DB transaction commits successfully but the Kafka offset commit fails, the record is redelivered. Next time, the unique constraint makes `inserted` equal 0, so the business update does not run again. If the DB transaction rolls back, both the inbox marker and business update roll back; redelivery can run it again.

Key requirements:
- `eventId` remains stable across retries/replays.
- Unique constraint lives in the DB, rather than checking via SELECT then INSERT due to race conditions.
- Inbox marker and business state commit atomically.
- Offset commits after the listener succeeds per the appropriate ack mode.
- Inbox retention is long enough relative to possible replay windows.

An inbox does not automatically deduplicate an HTTP side effect called before the DB transaction commits. For side effects outside the DB, use idempotency keys or an outbox workflow.

## 9. Why SELECT then INSERT is not enough to prevent duplicates

Race-prone pattern:

~~~java
if (!repository.existsByEventId(event.eventId())) {
    repository.save(new ProcessedEvent(event.eventId()));
    updateBusinessState(event);
}
~~~

Two consumers/processes can both check before either inserts:

~~~text
Consumer A: SELECT -> absent
Consumer B: SELECT -> absent
Consumer A: INSERT
Consumer B: INSERT
Consumer A: execute side effect
Consumer B: execute side effect
~~~

A unique constraint will reject one duplicate insert, but the application must handle the duplicate-key/insert result and **only execute the side effect when the insert wins**. The transaction must wrap both the marker and the DB changes. In many systems, an insert-if-absent statement is clearer than checking beforehand.

If an event needs partial processing, do not use a single shared marker marking the entire event complete before every step finishes. Store state per operation or use a state machine with explicit transitions.

## 10. Outbox pattern for DB updates and Kafka publishing

Another scenario: a service updates the DB and then publishes a Kafka event. If the two operations are not in an atomic transaction, the following can happen:
- DB commit succeeds yet Kafka send fails: DB state changes without emitting the event.
- Kafka send succeeds yet DB rolls back: event is emitted for DB changes that do not exist.

**Transactional outbox** solves dual-writes by recording business state and an outbox row in the same DB transaction:

~~~text
Application transaction
       |
       +--> UPDATE orders
       |
       +--> INSERT outbox_event
       |
       v
Database COMMIT
       |
       v
Outbox publisher / CDC
       |
       v
Kafka topic
~~~

Simple schema:

~~~sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(100) PRIMARY KEY,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(200) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);
~~~

Service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional
    public void createOrder(CreateOrder command) {
        Order order = orders.create(command);

        OrderCreated event = new OrderCreated(
                command.eventId(),
                order.getId(),
                order.getTotal());

        outbox.insert(event.eventId(), order.getId(),
                "OrderCreated", serialize(event));
    }
}
~~~

If the DB transaction rolls back, both the order and the outbox row roll back. On commit, a publisher reads the outbox and sends the Kafka record. Depending on architecture, you can implement a polling publisher with locking/claims or CDC such as Debezium.

The outbox publisher can still crash after publishing to Kafka successfully yet before marking the row published. On restart, it may send the event again. Downstream still needs idempotency/inbox; outbox **solves lost events from dual-writes**, rather than turning publishing into end-to-end exactly-once.

## 11. Combining Inbox and Outbox

A common processing chain:

~~~text
Service A:
  DB business update + outbox row
       |
       v
  Outbox publisher -> Kafka
                         |
                         v
Service B:
  Kafka consumer
       |
       v
  DB transaction:
    insert inbox(event_id)
    update business state
       |
       v
  commit DB
       |
       v
  Kafka offset commit
~~~

- Outbox ensures DB changes have a corresponding event to publish.
- Inbox deduplicates events when the consumer receives them again.
- Kafka offset commit after processing ensures crashes may cause redelivery without repeating DB business updates.
- Event ID links steps across services.

This is the **effectively-once business processing** model within the scope of DB state protected by the inbox. If Service B also calls a payment API or sends emails, a dedicated outbox for that command or provider-side idempotency is required.

## 12. Side effects outside DB: record intent first, execute later

For payments, emails, shipping, or external APIs, you can record a **command/outbox intent** in the DB transaction, then have a separate worker execute it.

~~~text
Kafka listener
     |
     v
DB transaction:
  - inbox(event_id)
  - update order state
  - insert payment_command
     |
     v
DB commit
     |
     v
Payment worker reads payment_command
     |
     v
Call provider with stable idempotency key
     |
     v
Persist provider result / command status
~~~

Benefits:
- Listener does not block the Kafka consumer thread waiting on the provider.
- Intent is durably persisted and can resume after restarts.
- Clear status tracking for pending, in-flight, succeeded, failed, or unknown.
- Worker can apply dedicated rate limits, retries, and concurrency.
- Business state and command intent commit in the same DB transaction.

However, the worker still must handle the window where the provider succeeds yet the worker crashes before updating command status. On retry, it must use the same idempotency key or query the provider by external reference. Without either capability, reconciliation/manual review is needed.

## 13. State model for side effects

An out-of-transaction command should have explicit states rather than just a `done` boolean.

~~~text
PENDING
   |
   v
IN_FLIGHT
   |
   +------ provider confirms success ------> SUCCEEDED
   |
   +------ definite retryable failure -----> RETRY_WAIT
   |                                            |
   |                                            v
   |                                        IN_FLIGHT
   |
   +------ permanent business failure ------> FAILED
   |
   +------ timeout / result unknown --------> UNKNOWN
                                                |
                                                v
                                          RECONCILING
                                           /       \
                                          v         v
                                    SUCCEEDED     RETRY_SAFE
~~~

Suggested states:

| State | Meaning | Action |
|---|---|---|
| `PENDING` | Intent recorded, not yet sent. | Worker can claim. |
| `IN_FLIGHT` | A worker is executing it. | Lease/claim prevents concurrent processing by another worker. |
| `RETRY_WAIT` | Confirmed retryable error after backoff. | Retry after allowed timestamp. |
| `SUCCEEDED` | Evidence exists that provider completed. | Do not resend. |
| `FAILED` | Confirmed permanent/business failure. | Await handling or business notification. |
| `UNKNOWN` | Timeout or connection loss left outcome unclear. | Query/reconcile before resending. |

An `IN_FLIGHT` state needs a lease/timeout so another worker can take over after a crash. Lease expiration does not prove the old request was never processed by the provider; the new worker must still use the same idempotency key or check status from the provider.

## 14. Safe retries for side effects outside transactions

Retries must depend on error type:

| Error type | Example | Policy |
|---|---|---|
| Transient and definitely not executed | DNS/connect failure before request is sent. | Can retry with backoff. |
| Transient but outcome unclear | Read timeout after provider received request. | Query by idempotency key/reference or retry with same key. |
| Permanent/business | Card declined, invalid address. | Do not retry infinitely; record business state and handle appropriately. |
| Authentication/configuration | Expired credential, ACL denied. | Pause or retry slowly once config is fixed; alert owner. |
| Rate limited | HTTP 429 or quota response. | Respect `Retry-After` if present, back off, and limit concurrency. |

Use exponential backoff with jitter so workers do not retry in lockstep:

~~~java
Duration delayForAttempt(int attempt) {
    long baseMillis = 500L;
    long capMillis = 60_000L;

    long exponential = Math.min(
            capMillis,
            baseMillis * (1L << Math.min(attempt, 10)));

    long jitter = ThreadLocalRandom.current()
            .nextLong(Math.max(1L, exponential / 2), exponential + 1);

    return Duration.ofMillis(jitter);
}
~~~

This is an illustrative example; production code must handle overflow, attempt caps, clocks, and provider policies. Retries must not exceed business deadlines or the provider's idempotency key retention window if doing so makes stale requests dangerous.

## 15. Retry topics and DLTs do not make side effects automatically idempotent

Spring Kafka can use `DefaultErrorHandler`, recoverers, or `@RetryableTopic` to retry and route failed records to a DLT. This controls Kafka record redelivery; it does not know whether a payment/email/API call already succeeded before the exception was thrown.

Example:

~~~text
Kafka record E
   |
   v
Listener calls external API
   |
   +-- API succeeds, response lost
   |
   v
Listener throws timeout
   |
   v
Retry record
   |
   v
External API called again
~~~

With retry topics:
- Keep event ID and idempotency key stable.
- Never generate a new request identity per attempt.
- Log attempts and side-effect status.
- Process DLT replays with the same business dedupe key.
- Ensure inbox/provider idempotency retention is long enough.
- Distinguish Kafka serialization/consumer errors from external side-effect errors.

A record landing in a DLT does not mean its side effect never occurred. Before replaying, check provider status or the command table.

## 16. Compensation and Sagas

Some workflows span multiple side effects that cannot commit together:

~~~text
Create order
    |
    v
Reserve inventory
    |
    v
Charge payment
    |
    v
Arrange shipment
~~~

If arranging shipment fails after payment succeeded, you cannot roll everything back with a Kafka transaction. You can use a **Saga**: each step has a compensating action defined by business rules.

~~~text
Reserve inventory
       |
       v
Charge payment
       |
       v
Shipment fails
       |
       v
Refund payment
       |
       v
Release inventory
       |
       v
Order = COMPENSATED / CANCELLED
~~~

Compensation is not a technical rollback:
- A refund is a new transaction that can fail or be delayed.
- Releasing inventory may no longer be possible if goods already shipped.
- A sent email cannot be recalled; a correction notice can be sent.
- Each compensation also needs its own idempotency key and state.

Sagas require durable workflow state, per-step timeouts, retry/compensation policies, and manual intervention procedures when compensation fails. Never assume compensation always succeeds or fully reverses prior effects.

## 17. Files and object storage are also side effects

Writing files in a listener shares the same crash-window issue:

~~~text
Write object successfully
       |
       v
Process crashes before Kafka offset commit
       |
       v
Record redelivered
       |
       v
Write object again
~~~

Techniques:
- Use a deterministic object key from event ID/aggregate ID if the same event must update the same object.
- Write to a temporary file then perform an atomic rename when the filesystem supports it.
- Use conditional writes/version preconditions when the object store supports them.
- Store checksums and metadata to verify which content the current object reflects.
- Persist command state in the DB/inbox to track whether the operation completed.
- For large files, persist intent and process via a leased worker instead of tying up the listener thread.

A deterministic key alone does not solve all races: two workers may write concurrently, and overwriting an existing object may be unsafe. Versioning rules, conditional writes, and proper ownership are needed.

## 18. Email, SMS, and notifications

Email usually has no "undo" operation. If a consumer sends an email and crashes before committing the offset, the record can be redelivered and send a second email.

Ways to reduce risk:
- Use a stable notification ID.
- Persist notification intent and delivery status.
- Use provider idempotency if available.
- If the provider lacks it, query delivery status by provider message ID/reference if the API permits.
- Design notification content to tolerate duplicates or add suppression mechanisms.
- Reconcile uncertain outcomes instead of retrying blindly.

A DB inbox marker only protects writing the marker/business state in the DB. If the marker commits before sending the email, a crash between marker and email can lose the email. If you send the email first and then commit the marker, a crash can send duplicates. A notification outbox durably persists intent; a worker and provider idempotency handle dispatch.

## 19. Coordinating DB transactions and Kafka transactions

Spring Kafka supports a Kafka transaction manager and transaction synchronization with certain other transaction managers. That helps coordinate commit ordering, but **does not turn a database and Kafka into a distributed atomic transaction** merely by enabling two transaction managers.

Possible outcomes:
- DB transaction commits successfully, Kafka commit fails: database changed while Kafka offset/output did not commit; record may be redelivered.
- Kafka commits before DB commit finishes (if ordering is misconfigured): consumer may advance offsets while the DB update is not yet durable.
- One resource commits, the other fails: no automatic global rollback for the already-committed resource.

Spring transaction synchronization can coordinate commit order and rollback callbacks depending on configuration/version. Understand your primary transaction manager, secondary manager, listener container transaction, and actual acknowledgment mode. **Never call this XA/2PC or DB+Kafka exactly-once without an actual distributed transaction protocol.**

An often more recoverable option is:
1. DB transaction writes business state + inbox/outbox.
2. Commit DB.
3. Kafka offset commits per configuration after listener success.
4. If offset commit fails, redelivery is deduplicated by the inbox.
5. Outbox publisher emits events and downstream is also idempotent.

This is a clean design because every step has durable state and explicit retry semantics.

## 20. Choosing a strategy by side-effect type

| Side effect | Commonly suitable pattern | Pay special attention to |
|---|---|---|
| DB update in same database | Inbox marker + business update in one DB transaction. | Unique constraint, commit ordering, retention. |
| DB update then Kafka publish | Transactional outbox + downstream inbox. | Outbox publisher can emit duplicates. |
| HTTP payment/booking API | Provider idempotency key + durable command state. | Ambiguous timeouts, key retention, reconciliation. |
| Email/SMS | Notification outbox + provider dedupe/reference. | Cannot undo; delivery status may be unclear. |
| File/object storage | Deterministic key + conditional write/version/checksum. | Concurrent writers and overwrite semantics. |
| Multi-step cross-service business flow | Saga + state machine + compensation. | Compensation can fail; needs manual recovery. |
| Kafka-to-Kafka forwarding | Kafka transactions when atomic consume-process-produce is needed. | Only within Kafka boundaries with proper isolation/transaction config. |

No single pattern fits every task. Choose based on the external system's capabilities, irreversibility, audit requirements, and operational cost.

## 21. Example: consumer writes payment intent, worker calls provider

The listener only records the inbox and payment command in the DB:

~~~java
@Service
public class PaymentCommandService {

    private final JdbcTemplate jdbc;

    public PaymentCommandService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void accept(PaymentRequested event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_event(event_id, processed_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT (event_id) DO NOTHING
            """, event.eventId());

        if (inserted == 0) {
            return;
        }

        jdbc.update("""
            INSERT INTO payment_command(
                command_id, payment_id, amount, status, idempotency_key
            )
            VALUES (?, ?, ?, 'PENDING', ?)
            ON CONFLICT (command_id) DO NOTHING
            """,
            event.eventId() + ":charge",
            event.paymentId(),
            event.amount(),
            event.paymentId());
    }
}
~~~

Worker executing the command:

~~~java
public void execute(PaymentCommand command) {
    PaymentResult result = paymentProvider.charge(
            command.paymentId(),
            command.amount(),
            command.idempotencyKey());

    commandRepository.markSucceeded(
            command.commandId(),
            result.providerReference());
}
~~~

This example assumes the provider supports idempotency keys and commandRepository handles transactions/state transitions properly. Workers must claim commands safely so multiple instances do not execute them simultaneously; even after a successful claim, lease expiry following a crash can cause the command to be retried. The provider idempotency key is the final line of defense when the provider already charged yet the worker failed to record the outcome.

## 22. Concurrency and claiming commands

If multiple workers poll the command table, SELECT pending followed by UPDATE is not enough to prevent races. Use an atomic claim/lease per database capabilities:

~~~sql
UPDATE payment_command
   SET status = 'IN_FLIGHT',
       lease_owner = :worker_id,
       lease_until = :lease_until
 WHERE command_id = :command_id
   AND (
       status IN ('PENDING', 'RETRY_WAIT')
       OR (status = 'IN_FLIGHT' AND lease_until < CURRENT_TIMESTAMP)
   );
~~~

Illustrative SQL; production requires proper transactions/locking, row-count checks, lease durations, and database-specific dialect.

A worker processes only when its update claims exactly one row. Leases prevent two workers from claiming concurrently in normal flows, yet cannot cancel an in-flight HTTP request at an old worker just because its lease expired. If the provider takes longer than the lease, a new worker may start again. Therefore:
- Leases must be renewed for long tasks.
- HTTP timeouts and leases must be coordinated.
- Every attempt uses the same idempotency key.
- `UNKNOWN` states must reconcile before resending if the provider does not deduplicate.

## 23. Observing and auditing side effects outside transactions

A side effect needs logs/metrics sufficient to answer "was it sent?", "is the outcome clear?", and "is retrying safe?".

Suggested structured log:

~~~json
{
  "event": "external_effect_attempt",
  "eventId": "evt-4821",
  "commandId": "evt-4821:charge",
  "effectType": "PAYMENT_CHARGE",
  "provider": "payment-gateway",
  "idempotencyKeyRef": "payment-4821",
  "attempt": 2,
  "status": "UNKNOWN",
  "reason": "read-timeout"
}
~~~

Illustrative schema. Do not log the idempotency key if it is considered sensitive or if the provider treats it like an access token; log a safe reference/hash instead.

Useful metrics:
- Pending command count and age of oldest command.
- Side-effect attempts by provider and outcome.
- Retry rate, timeout rate, and unknown-result count.
- Duration from intent creation to completion.
- Inbox duplicate count.
- Outbox backlog and publish failures.
- Pending/failed compensations.
- DLT ingress and replay counts.

Never put event ID, payment ID, or idempotency key into unbounded-cardinality metric labels. Use logs/traces to investigate individual operations; keep metric labels small in domain size.

## 24. Runbook: timeout when calling an external API

Suppose the consumer calls a payment provider and receives a read timeout.

**Step 1 — Do not infer failure from a timeout.** Record whether the request was sent and whether the timeout happened on connect, write, or response read.

**Step 2 — Identify the logical operation.** Find the event ID, payment ID, command ID, and stable idempotency key. Check which key prior attempts used.

**Step 3 — Query the provider.** If the API supports querying by idempotency key or external reference, look up status before deciding to resend.

**Step 4 — Act on the result.** If the provider confirms success, update the command to `SUCCEEDED`; if confirmed unexecuted, retry with the same key; if indeterminate, keep `UNKNOWN` and route to reconciliation.

**Step 5 — Protect the Kafka offset.** Do not mark the listener successful unless durable intent was recorded. If the listener errors and the record retries, inbox/dedupe must protect business state.

**Step 6 — Check for duplicate side effects.** Reconcile provider references against internal payment records; do not look solely at consumer invocation counts.

**Step 7 — Confirm recovery.** Command reaches a terminal state, retry/unknown backlog drops, and records are handled per policy.

Never generate a new idempotency key "to retry just to be sure"; doing so can create a second payment operation.

## 25. Runbook: side effect succeeded but offset uncommitted

A record called an API successfully, yet the pod restarted before committing the offset.

1. Confirm the record was redelivered via topic/partition/offset and event ID.
2. Check the inbox/command table or provider state from the prior attempt.
3. If the provider already succeeded, update internal state from the known result and do not call charge again.
4. If a retry is needed, use the exact old idempotency key per provider contract.
5. If there is no evidence of provider state, move the command to reconciliation/`UNKNOWN`.
6. Once business state is durable, let the listener complete and commit the offset per ack mode.
7. Monitor duplicate delivery counts and provider operation counts to confirm no duplicate business effects occurred.

Kafka redelivery after a crash is normal. The system must turn it into a safe state/dedupe check.

## 26. Runbook: DLT replay for events with side effects

Before replaying:
1. Identify the event ID and original topic/partition/offset.
2. Locate the command/inbox state of the side effect.
3. Query the provider if the prior attempt had a timeout or unclear result.
4. Determine whether the event already charged, sent email, wrote a file, or updated the DB.
5. Use the same idempotency key if the same operation needs retrying.
6. Confirm the consumer version/config fixes the root cause.
7. Replay in a small/canary batch and observe outcomes.
8. Record replay ID, actor, reason, and outcome.
9. Reconcile replayed events and close commands in terminal states.

Do not delete inbox markers or command history just to force a record to re-run. If a new business action is needed, create a new business-approved command with a new identity.

## 27. Testing crash windows and duplicates

A useful integration test verifies not only happy-path listener processing but also simulates crash windows:

1. Send an event with a stable event ID.
2. Let the consumer write DB inbox + business update, then simulate an offset commit failure; redeliver the record and verify the DB effect happens only once.
3. Have a mock external provider accept the request and record success, yet time out the response; retry with the same idempotency key and verify the provider creates only one operation.
4. Simulate a worker crash after provider success before command status updates; a new worker takes over and reconciles via key/reference.
5. Simulate permanent failure and verify DLT/recovery state is not falsely marked succeeded.
6. Replay the same event ID multiple times and verify dedupe still holds.
7. Test two workers claiming the same command concurrently to confirm only one holds a valid lease.
8. Test compensation failure and manual intervention state if using a Saga.

Use Kafka Testcontainers/embedded brokers, a test database, and a stateful fake HTTP provider in tests. Never call a real payment provider or send production emails to test idempotency.

## 28. Common design mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Thinking Kafka transactions roll back HTTP calls | Side effects still happen even if Kafka transaction aborts. | Use idempotency, outbox/commands, or compensation. |
| Calling API then committing offset without dedupe | Redelivery can produce duplicate side effects. | Stable idempotency key and durable state. |
| Generating a new UUID on every retry | Provider treats each attempt as a new operation. | Use a stable key per logical operation. |
| Retrying blindly after read timeout | Provider may have executed the operation before timeout. | Query/reconcile or retry with same key. |
| Committing DB marker before email, then crashing | Email may be lost even though event is marked processed. | Notification outbox and worker. |
| Sending email before DB marker, then crashing | Email may be sent twice. | Provider dedupe or suppression/reconciliation. |
| SELECT then INSERT for dedupe | Race between two consumers/processes. | Unique constraint and insert-if-absent in transaction. |
| Outbox publisher marks sent after send, crashes mid-way | Event may be published twice. | Downstream inbox/idempotency. |
| Holding DB transaction open while waiting on HTTP | Lock/connection pool pressure and timeouts. | Record intent in short transaction, execute outside transaction. |
| DLT replay without checking provider state | Charges/emails/files may repeat. | Check command/inbox and idempotency before replaying. |
| Treating compensation as absolute rollback | Compensation can fail or not fully reverse effects. | Saga state machine and manual recovery. |

## 29. Pre-production checklist

- [ ] List all side effects outside Kafka: DB, HTTP, email, files, object storage, and other services.
- [ ] Identify crash windows between side effects and Kafka offset/transaction commits.
- [ ] Every logical operation has a stable event ID/command ID.
- [ ] Provider APIs use stable idempotency keys where supported.
- [ ] Ambiguous timeouts are handled via query/reconciliation, not blind retries.
- [ ] DB inbox marker and business update share the same DB transaction.
- [ ] Outbox rows and business state commit together when publishing events from the DB.
- [ ] Downstream has dedupe since the outbox publisher may resend.
- [ ] Worker commands have clear states, leases, retry policies, and terminal outcomes.
- [ ] Retry/DLT replays preserve event identity and never generate new idempotency keys.
- [ ] Irreversible side effects have compensation or manual recovery plans.
- [ ] DB transactions/connections are not held long while waiting on network I/O.
- [ ] Logs include event ID, command ID, provider reference, attempt, and outcome; no secrets logged.
- [ ] Metrics exist for pending/unknown/retry/duplicate/outbox backlog.
- [ ] Tests cover crash after provider success, ambiguous timeout, offset commit failure, and replay.
- [ ] Documentation states the exact boundary of exactly-once; never claims Kafka transactions cover external systems.

## 30. Conclusion

**Side effects outside transactions must be designed as retryable workflows, not as an automatic part of a Kafka transaction.** A Kafka transaction can coordinate Kafka output records and input offsets; it does not roll back payments, emails, independent SQL transactions, or written files. Therefore, consumers need stable idempotency keys, durable inbox/outbox state, explicit command states, and reconciliation processes for indeterminate outcomes.

For DBs, inbox deduplicates events and outbox solves dual-writes. For HTTP providers, use idempotency keys and status queries after timeouts. For multi-step business flows, Sagas and compensation offer controlled recovery paths. When these patterns are combined with retry/DLT handling and crash-window testing, the system can endure redeliveries and replays while preserving business outcomes.
