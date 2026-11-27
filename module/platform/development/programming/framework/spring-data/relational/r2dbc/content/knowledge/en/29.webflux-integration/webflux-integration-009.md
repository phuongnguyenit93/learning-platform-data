# Coordinating HTTP Calls or External Events with Persistence Operations

In a Spring WebFlux application combined with Spring Data R2DBC, a single use case often needs to both write data to the database and call another HTTP service or emit an event to a message broker. Examples include creating an order and requesting payment processing; saving a profile and notifying a search index; or recording an inventory change and publishing an event for downstream services.

The challenge is that an R2DBC reactive transaction only governs database resources owned by the transaction manager. It cannot roll back an HTTP request already processed by an external system, retract a sent email, or remove a message already accepted by a broker. If the database commits while the external call fails—or the external call succeeds while the database rolls back—the two systems drift out of sync.

Therefore, you must explicitly define operation ordering, transaction boundaries, and recovery strategies. Common choices include: invoking HTTP before or after the transaction under clear rules; persisting workflow state to coordinate multi-step flows; using a transactional outbox to write data and events in the same transaction; using an inbox/idempotency to handle duplicate messages; and implementing sagas with compensating actions when workflows span multiple systems.

## 1. Two Categories of Resources in One Use Case

An integrated business flow typically touches two groups of resources:

- **Local resources:** the database managed by the R2DBC connection factory and reactive transaction manager.
- **External resources:** HTTP services, payment gateways, email providers, message brokers, search indexes, or other external systems.

Example:

~~~mermaid
flowchart LR
    S[WebFlux Service]
    TX[Reactive DB Transaction]
    DB[(R2DBC Database)]
    HTTP[WebClient / HTTP API]
    EXT[External Service]
    S --> TX --> DB
    S --> HTTP --> EXT
~~~

The transaction manager can commit or roll back DB operations. An HTTP service has its own request lifecycle and state; it does not automatically join the R2DBC transaction. Once an external system successfully processes an HTTP request, rolling back the local database does not undo that external system's state.

## 2. Why You Should Not Hold a Database Transaction While Waiting on HTTP

A common anti-pattern:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    paymentClient.authorize(toPaymentRequest(order))
                            .thenReturn(order)
            );
}
~~~

The entire publisher executes inside the reactive transaction. After saving the `Order`, the application holds the connection and transaction open while waiting on a network call. If the payment service takes 5 seconds, the database connection may stay occupied for that entire duration.

This causes several problems:

- Connection pool slots remain occupied longer than needed.
- Row locks or transaction snapshots can stay held while waiting on external services.
- HTTP timeouts stretch transaction lifetimes.
- Payment may succeed while a subsequent DB statement fails, causing a database rollback even though payment was already processed.
- Retrying the transaction may invoke the payment service again and create duplicate side effects.

Keep database transactions short, wrapping only operations that must commit or roll back atomically on the same database. Move HTTP calls outside that boundary, and coordinate outcomes via workflow state or appropriate idempotency mechanisms.

## 3. Why an R2DBC Transaction Cannot Roll Back HTTP

Spring reactive transactions are managed via `ReactiveTransactionManager`, typically `R2dbcTransactionManager`. This manager coordinates an R2DBC `ConnectionFactory`: starting transactions, committing or rolling back on that connection, and binding resources to the Reactor Context.

When a Service calls `WebClient`, `WebClient` sends an HTTP request over the network. The remote HTTP server may:

1. Receive the request.
2. Execute business logic.
3. Commit its own database.
4. Return HTTP 200.

Subsequently, the local database might encounter an error and roll back. There is no universal protocol allowing the R2DBC transaction manager to automatically instruct the remote HTTP server to undo what it just committed.

This marks the boundary between **local transactions** and **distributed workflows**. When coordinating multiple systems, design explicit business protocols such as idempotency, outbox, sagas, or compensation; never rely on `@Transactional` alone.

## 4. Chaining WebClient and Repositories with Publishers

`WebClient` is a reactive HTTP client. Its methods return `Mono<T>` or `Flux<T>`, allowing composition with repository publishers via Reactor:

~~~java
public Mono<ShippingQuote> getQuote(Long orderId) {
    return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(orderId)
            ))
            .flatMap(order ->
                    webClient.get()
                            .uri("/quotes/{postalCode}",
                                    order.shippingPostalCode())
                            .retrieve()
                            .bodyToMono(ShippingQuote.class)
            );
}
~~~

Here:

- The repository returns `Mono<Order>`.
- `flatMap` receives the `Order` and calls `WebClient`.
- `WebClient` returns `Mono<ShippingQuote>`.
- The result flattens into a single `Mono<ShippingQuote>`.

Never call `block()` to wait on HTTP and never call `subscribe()` inside a Service. Return the publisher so callers manage results, errors, and cancellation.

Composing reactive publishers does not place two operations in a distributed transaction. It merely coordinates execution order and signals within one pipeline.

## 5. Choosing Order: HTTP First or Database Write First?

No single ordering fits every business scenario. Analyze what happens when the second step fails.

| Ordering | Primary Risk | Suitable When |
| --- | --- | --- |
| Call HTTP first, then write DB | HTTP succeeds while DB write fails | HTTP is read/validation only, or remote call is idempotent/compensable |
| Write DB first, then call HTTP | DB committed while HTTP fails | Pending state exists alongside post-commit retry/dispatch |
| Write DB and outbox in same transaction, send later | Message may be delivered more than once if worker crashes | Zero event loss after DB commit is required |
| Multi-step workflow with saga | Must manage state and compensation | Multiple services have independent side effects without distributed ACID |

Before picking an ordering, answer:

- If the process crashes between steps, does the system know where work stopped?
- If the client retries the same request, will it cause duplicate side effects?
- If HTTP times out, could the remote service have already processed the request?
- If a message is delivered twice, is the consumer idempotent?
- Can an already-succeeded step be compensated?

## 6. When HTTP Calls Only Read Data

If the external call only reads data and produces no side effects, you can call HTTP first and then run the local write transaction:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    return shippingClient.validateAddress(command.address())
            .flatMap(validation -> {
                if (!validation.valid()) {
                    return Mono.error(
                            new InvalidShippingAddressException()
                    );
                }

                return transactionalOperator.transactional(
                        orderRepository.save(toOrder(command, validation))
                );
            });
}
~~~

The address validation completes before the DB transaction begins. If HTTP fails, no write transaction is opened. If the DB write fails, the HTTP operation was read-only so there are no external side effects to undo.

However, validation results from external services can go stale before commit. If a rule must hold at execution time, the remote service must issue a time-bounded reservation/token; a pure validation call does not guarantee state remains valid later.

## 7. Writing Pending State First, Calling HTTP Outside the Transaction

For operations with side effects like payments, a common pattern is persisting durable workflow state:

1. A short transaction creates the `Order` in `PENDING_PAYMENT` state.
2. Commit the transaction.
3. Call the payment service with a stable idempotency key.
4. When payment succeeds, a new transaction updates the `Order` to `PAID`.
5. On explicit failure, a new transaction updates it to `PAYMENT_FAILED`.

Example:

~~~java
public Mono<OrderResponse> placeOrder(CreateOrderCommand command) {
    return transactionalOperator.transactional(
                    orderRepository.save(toPendingOrder(command))
            )
            .flatMap(order ->
                    paymentClient.authorize(
                                    toPaymentRequest(order),
                                    order.paymentIdempotencyKey()
                            )
                            .flatMap(payment ->
                                    transactionalOperator.transactional(
                                            orderRepository.markPaid(
                                                    order.id(),
                                                    payment.reference()
                                            )
                                    )
                            )
                            .map(this::toResponse)
            );
}
~~~

This is an illustrative skeleton. Production code must handle HTTP errors, ambiguous timeouts, failure state updates, retries, and crash recovery. Persisting `PENDING` beforehand gives the system a durable record for reconciliation and workflow continuation.

Never place the `WebClient` call inside a publisher wrapped by `transactional(...)`. The two transactions in this example are separate local transactions: one creating the pending order, and one recording the result.

## 8. HTTP Timeouts Can Produce Ambiguous Outcomes

Suppose the payment service receives the request, processes and commits the payment, yet the response is lost on the network. `WebClient` times out. The application cannot conclude from a timeout alone that the payment failed.

Two possibilities exist:

- The request never reached the server or the server did not process it.
- The server processed it successfully, yet the response never reached the client.

If the application immediately sends a new payment request with a new key, it can double-charge. Therefore:

- Generate a stable idempotency key for a logical payment operation.
- Reuse the same key when retrying the same logical request.
- The remote service must persist and recognize keys to return the earlier result or in-progress status instead of executing again.
- When the outcome remains unknown, query a status lookup endpoint by key/reference before deciding to retry or compensate.

Never generate a fresh idempotency key on every retry attempt. The key must be created once per workflow and durably stored with the business record.

## 9. Transactional Outbox Solves DB Write Plus Event Emission

A classic problem:

~~~java
return orderRepository.save(order)
        .flatMap(saved ->
                eventPublisher.publishEvent(
                        new OrderCreated(saved.id())
                ).thenReturn(saved)
        );
~~~

If the database commits yet message publishing fails, the event is lost. If publishing succeeds yet the database transaction rolls back, consumers receive an event for an order that does not exist.

The transactional outbox solves this by writing business data and an outbox row inside **the same database transaction**:

~~~mermaid
flowchart TD
    A[Service creates order]
    B[Local R2DBC transaction]
    C[(orders table)]
    D[(outbox_event table)]
    E[Commit]
    F[Outbox relay]
    G[Message broker / HTTP endpoint]
    A --> B
    B --> C
    B --> D
    C --> E
    D --> E
    E --> F --> G
~~~

If the transaction commits, both the `Order` and the outbox event exist. If it rolls back, neither exists. A separate process reads the outbox and dispatches events after commit.

Outbox does not turn message delivery into exactly-once. It guarantees events are durably stored alongside business data; the relay may redeliver on failures, so consumers still need idempotency.

## 10. Designing the Outbox Table

Illustrative schema:

~~~sql
CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(150) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE,
    locked_until TIMESTAMP WITH TIME ZONE,
    published_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_outbox_pending
    ON outbox_event(status, next_attempt_at, created_at);
~~~

Field meanings:

- `id`: stable event ID, serving as the consumer idempotency key.
- `aggregate_type` and `aggregate_id`: business entity emitting the event.
- `aggregate_version`: supports ordering events per aggregate when needed.
- `event_type`: event type name.
- `payload`: serialized event data.
- `status`: `NEW`, `PROCESSING`, `PUBLISHED`, or failure status per design.
- `attempts`: relay delivery attempt count.
- `next_attempt_at`: earliest eligible time for the next attempt.
- `locked_until`: lease allowing another worker to reclaim work if a worker crashes.
- `published_at`: timestamp when delivery succeeded.

Actual schemas should select UUID, JSON/JSONB, index, and timestamp types suited to the database. If payloads hold sensitive data, enforce encryption, access controls, and retention policies.

## 11. Writing Order and Outbox Event in the Same Transaction

Event entity:

~~~java
@Table("outbox_event")
public record OutboxEvent(
        @Id UUID id,
        @Column("aggregate_type") String aggregateType,
        @Column("aggregate_id") String aggregateId,
        @Column("event_type") String eventType,
        String payload,
        @Column("created_at") Instant createdAt,
        String status
) {}
~~~

Service:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    outboxRepository.save(
                            toOrderCreatedEvent(order)
                    ).thenReturn(order)
            );
}
~~~

Both repositories must target the same database and R2DBC connection factory managed by the reactive transaction manager. When both operations run in the same pipeline, the transaction commits or rolls back together.

Do not call the broker or HTTP inside this method. It solely records business data and the intent to emit an event.

If using `DatabaseClient` to insert the outbox row, it must also participate in the same reactive transaction context. Never open a separate standalone connection and write the event outside the transaction.

## 12. Outbox Relay: Short Claim, Send Outside Transaction, Update Result

A relay can run periodically or as a background worker:

1. Open a short transaction and claim a batch of due `NEW` events.
2. Mark `PROCESSING`, increment `attempts`, and set a lease.
3. Commit to release connections/locks.
4. Publish messages to the broker or call HTTP outside any transaction.
5. On success, open a short transaction to mark `PUBLISHED`.
6. On failure, schedule `next_attempt_at` with backoff or move to `DEAD_LETTER` past a threshold.

With PostgreSQL, a common claiming pattern is:

~~~sql
SELECT id, event_type, payload
FROM outbox_event
WHERE status = 'NEW'
  AND (next_attempt_at IS NULL
       OR next_attempt_at <= CURRENT_TIMESTAMP)
ORDER BY created_at, id
LIMIT 50
FOR UPDATE SKIP LOCKED;
~~~

Inside the same claim transaction, update the selected rows to `PROCESSING` and set `locked_until`. Commit before sending. `SKIP LOCKED` is database-specific syntax; on other DBMSs, use an equivalent claim pattern such as conditional `UPDATE` statements with an owner token.

Never hold transactions/row locks while waiting on broker or HTTP responses. If a worker dies after claiming, lease expiration lets another worker reclaim the events.

## 13. Why Can an Outbox Relay Deliver Duplicates?

Suppose the relay sends an event, the broker accepts it, and the process crashes before updating `status = 'PUBLISHED'`. Once the lease expires, another worker sends the event again.

This is at-least-once delivery behavior. Outbox prevents losing events when the database commits, yet it does not eliminate duplicate sends across the boundary between external systems and local status updates.

Therefore:

- Use stable event IDs.
- Consumers record processed event IDs.
- Enforce a unique constraint on event IDs in an inbox/processed-message table.
- Update business state and record the inbox entry in the same consumer transaction.
- If the consumer calls further external systems, propagate idempotency keys or use its own outbox.

Never advertise an outbox as exactly-once delivery without end-to-end protocols and strict semantics across producer, broker, and consumer.

## 14. Inbox Pattern to Prevent Duplicate Event Processing

Consumers can persist IDs of processed events:

~~~sql
CREATE TABLE inbox_message (
    event_id UUID PRIMARY KEY,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Within a single transaction:

1. Insert the event ID into the inbox.
2. If a unique constraint indicates the event already exists, treat it as a duplicate and skip processing.
3. If insertion succeeds, update business state.
4. Commit.

Skeleton logic:

~~~java
@Transactional
public Mono<Void> handle(OrderCreated event) {
    return inboxRepository.insertIfAbsent(event.eventId())
            .flatMap(inserted -> {
                if (!inserted) {
                    return Mono.empty();
                }

                return projectionRepository.updateFrom(event);
            });
}
~~~

`insertIfAbsent` must be implemented using database-native SQL/constraints; never just `SELECT` first and then `INSERT`, because two concurrent consumers can both observe absence.

When consuming messages from a broker, only ACK/commit offsets after the transaction handling the inbox and business update succeeds. ACKing before commit risks losing messages if the database rolls back.

## 15. Idempotency for HTTP Calls

Not only message brokers require idempotency. HTTP clients can also retry due to timeouts, network glitches, or caller retries.

Example payment authorization:

~~~java
public Mono<PaymentResult> authorize(
        PaymentCommand command,
        String idempotencyKey) {

    return webClient.post()
            .uri("/payments/authorize")
            .header("Idempotency-Key", idempotencyKey)
            .bodyValue(command)
            .retrieve()
            .bodyToMono(PaymentResult.class);
}
~~~

The remote service must honor the semantics of this header: the same key with the same logical payload returns the earlier result or an in-progress status without creating another payment. Simply sending a header when the server does not persist/check the key provides no idempotency.

Tie the idempotency key to the operation—for example, order ID + operation type or a UUID generated when creating the workflow. Persist the key durably so process restarts reuse the exact same key.

## 16. Sagas for Multi-System Workflows

When a use case spans multiple systems with independent side effects, model it as a saga. A saga breaks the workflow into local steps; if a later step fails, the system runs compensating actions for previously completed steps.

Order placement example:

~~~mermaid
flowchart TD
    A[Create order PENDING]
    B[Reserve inventory]
    C[Authorize payment]
    D[Confirm order]
    E[Release inventory]
    F[Void / refund payment]
    G[Mark order FAILED]
    A --> B --> C --> D
    B -->|Payment failed| E
    E --> G
    C -->|Confirmation failed| F
    F --> E
    E --> G
~~~

Compensation is not an ACID database rollback. For example, a refund is a new transaction that can itself fail or be delayed; it merely moves business state toward an acceptable outcome.

Sagas can be coordinated via:

- **Orchestration:** a coordinator service/workflow tracks state and invokes each step.
- **Choreography:** services emit/consume events and react with subsequent events.

For systems needing straightforward observability and recovery, orchestration usually makes step states clearer. Choreography reduces coupling to a central coordinator, though long flows can be harder to trace.

## 17. Persisting Saga State in the Database

A workflow table can store:

~~~sql
CREATE TABLE order_workflow (
    id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL,
    state VARCHAR(40) NOT NULL,
    payment_reference VARCHAR(150),
    inventory_reservation_id VARCHAR(150),
    last_error_code VARCHAR(100),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    version BIGINT NOT NULL
);
~~~

Illustrative states:

- `PENDING`
- `INVENTORY_RESERVED`
- `PAYMENT_AUTHORIZED`
- `COMPLETED`
- `COMPENSATING`
- `FAILED`

Each step only performs valid state transitions. Use optimistic locking with `version` or conditional `UPDATE` statements:

~~~sql
UPDATE order_workflow
SET state = 'PAYMENT_AUTHORIZED',
    payment_reference = :reference,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND state = 'INVENTORY_RESERVED';
~~~

If affected rows equal 0, the workflow may have already transitioned under another worker or sit in an invalid state. Never overwrite state blindly.

## 18. Distinguishing Retry, Compensation, and Rollback

Three concepts are often confused:

| Mechanism | Purpose | Scope |
| --- | --- | --- |
| Rollback | Undoes uncommitted changes | Single local database transaction |
| Retry | Re-runs an operation after recoverable failure | One attempt or workflow step |
| Compensation | Issues a new action to offset committed effects elsewhere | Multiple systems / saga |

Examples:

- `INSERT Order` and `INSERT Outbox` in one transaction fail: roll back both.
- Event delivery fails before broker accepts it: retry relay with backoff.
- Payment was captured yet shipping fails: issue refund/void as compensation.

Never use retry as a substitute for compensation. If a payment already succeeded, re-running capture can cause extra side effects; inspect state and execute the proper compensating business action.

## 19. Handling WebClient Errors and Classifying Results

`WebClient` can emit errors due to:

- HTTP 4xx: invalid request, unauthorized, or conflict.
- HTTP 5xx: remote server error.
- Timeout: unknown whether the remote system processed the request.
- DNS/connect/reset: connection failure.
- Decode error: malformed response format.

Example:

~~~java
return webClient.post()
        .uri("/reservations")
        .bodyValue(request)
        .retrieve()
        .onStatus(
                status -> status.is4xxClientError(),
                response -> response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> new RemoteRequestRejected(body))
        )
        .onStatus(
                status -> status.is5xxServerError(),
                response -> Mono.error(new RemoteServiceUnavailable())
        )
        .bodyToMono(ReservationResponse.class)
        .timeout(Duration.ofSeconds(3));
~~~

This is a mapping illustration; in practice, avoid placing sensitive raw response bodies into exceptions or logs. Do not blindly retry all 4xx errors. Some 409 responses may reflect an already-applied idempotent result; some 429/503 responses may be retried respecting `Retry-After` and overall deadlines.

Timeouts or connection resets do not prove the remote side effect did not happen. For resource-creating POSTs, pair idempotency keys with status-lookup endpoints.

## 20. Never Use onErrorResume to Hide Workflow Failures

Dangerous example:

~~~java
return paymentClient.authorize(request)
        .onErrorResume(error -> Mono.empty())
        .flatMap(result -> orderRepository.markPaid(orderId));
~~~

If payment fails, the publisher recovers to empty; `markPaid` does not run, yet the caller sees normal completion and mistakes the workflow for a success.

Either transition to an explicit business failure state or propagate the error:

~~~java
return paymentClient.authorize(request)
        .flatMap(result -> markPaymentAuthorized(orderId, result))
        .onErrorResume(error ->
                markPaymentFailed(orderId, classify(error))
                        .then(Mono.error(error))
        );
~~~

In this example, recording the failure happens in its own transaction, and the original error propagates onward. When the remote result is ambiguous due to a timeout, avoid marking `PAYMENT_FAILED` immediately; use a state like `PAYMENT_UNKNOWN` and a reconciliation step.

## 21. Scoping Transactions Properly

A clear structural pattern:

~~~java
public Mono<Order> createAndRequestPayment(
        CreateOrderCommand command) {

    return transactionalOperator.transactional(
                    orderRepository.save(toPendingOrder(command))
            )
            .flatMap(order ->
                    paymentClient.authorize(
                                    toPaymentRequest(order),
                                    order.idempotencyKey()
                            )
                            .flatMap(payment ->
                                    transactionalOperator.transactional(
                                            orderRepository.markPaymentResult(
                                                    order.id(),
                                                    payment.status(),
                                                    payment.reference()
                                            )
                                    )
                            )
            );
}
~~~

Here:

- The first transaction only persists the pending state.
- The HTTP call runs after commit.
- The second transaction only persists the remote outcome.

Production code must add error branches, timeouts, reconciliation, and idempotency. If payment succeeds while the second transaction fails, the workflow must be able to resume and record the outcome without re-capturing payment.

Do not annotate the entire method with `@Transactional` when the intent is committing separate database operations before and after HTTP. When using annotations, split each local transaction into an appropriate bean/method, or use `TransactionalOperator` to make boundaries explicit.

## 22. Post-Commit Events and Event Listener Limitations

Another option is publishing an application event after transaction commit. In synchronous transactions, Spring offers `@TransactionalEventListener(phase = AFTER_COMMIT)` so listeners run only after commit.

However, keep in mind:

- In-memory events are lost if the process crashes after commit before the listener finishes.
- The listener may run while message delivery fails.
- Listener retries can produce duplicates.
- In reactive transactions, transaction state lives in Reactor Context rather than `ThreadLocal`; publishing and handling events must preserve the reactive transaction context via mechanisms Spring supports.

Where Spring supports reactive transaction events, `TransactionalEventPublisher` can emit events carrying the reactive transaction context. Verify APIs and usage against your Spring Framework version; never assume a plain application event automatically gets imperative-style transaction synchronization.

When the requirement is **never losing an event after database commit**, a transactional outbox is far more durable than in-memory events. Post-commit event listeners fit secondary, non-critical, or regenerable side effects.

## 23. Outbox Polling vs. Change Data Capture

There are two common ways to turn outbox rows into messages:

**Polling relay**

- Worker queries unpublished outbox rows.
- Claims in batches with leases.
- Publishes messages.
- Updates statuses.
- Simple to build with repositories/`DatabaseClient` and schedulers.

**Change Data Capture (CDC)**

- Tool reads the database transaction log.
- Once an outbox row commits, the CDC connector streams the change to the broker.
- Can reduce polling queries and latency.
- Requires operating connectors, offsets, schema registry/serialization, and log retention.

CDC does not eliminate consumer idempotency. Events can still be replayed when a connector rewinds offsets or reprocesses logs.

## 24. Preserving Event Ordering per Aggregate

If an `Order` emits `OrderCreated` then `OrderPaid`, consumers may need to process them in order. The outbox can store aggregate ID and version:

~~~text
order_id = 900
aggregate_version = 1
event_type = OrderCreated

order_id = 900
aggregate_version = 2
event_type = OrderPaid
~~~

Relays should ensure version 2 is not published before version 1 for the same aggregate when ordering is required by contract. Multiple workers using `SKIP LOCKED` can pick up events for the same aggregate in different batches; partition by aggregate, claim in order, or apply appropriate serialization.

Consumers can also store the last applied version and reject or defer out-of-order events per rules. Never assume brokers guarantee global ordering without configuring partitions/keys and appropriate semantics.

## 25. Incoming External Events: Persist First, ACK Later

When receiving webhooks or messages from external systems, the same rule applies in reverse:

1. Verify webhook origin and signature.
2. Persist the event ID and required payload into an inbox or event-receipt table.
3. Commit the database.
4. Return HTTP 2xx/202 or ACK the broker.
5. Execute business logic from the saved record, optionally in a separate worker.

If you return 2xx before durable storage, a process crash loses the event because the sender considers delivery complete. If you run lengthy side effects before ACKing, the sender may time out and retry, making idempotency essential.

Example webhook receiver endpoint:

~~~java
@PostMapping("/webhooks/payment")
public Mono<ResponseEntity<Void>> receivePaymentWebhook(
        @RequestBody Mono<PaymentWebhook> body) {

    return body.flatMap(webhook ->
                    webhookService.storeIfNew(webhook)
            )
            .thenReturn(ResponseEntity.accepted().build());
}
~~~

`storeIfNew` should record the inbox entry and pending processing state in one transaction. Return 202 only after the storage publisher completes. Signatures, timestamps, replay protection, and webhook authentication must be verified before trusting the payload.

## 26. Idempotent Consumer Structure

A consumer can process events following this pattern:

~~~java
@Transactional
public Mono<Void> handle(PaymentWebhook event) {
    return inboxRepository.insertIfAbsent(event.eventId())
            .flatMap(inserted -> {
                if (!inserted) {
                    return Mono.empty();
                }

                return orderRepository.applyPaymentStatus(
                        event.orderId(),
                        event.paymentStatus()
                );
            });
}
~~~

Inbox insertion and the `Order` update must share the same transaction. If updating the `Order` fails, the inbox insert also rolls back so the event can be redelivered and retried. Once the transaction commits, any duplicate delivery finds `insertIfAbsent` returning `false` and skips reapplying business logic.

ACKing after commit prevents event loss caused by premature ACKs. If the process crashes after commit yet before ACK, the broker redelivers and the inbox safely deduplicates it.

## 27. Retries and Backoff for External Calls

HTTP or broker calls can experience transient errors. Retries require:

- Bounded attempt counts.
- Backoff with jitter.
- Retrying only eligible errors such as 429/503 or recoverable connection errors.
- Respecting `Retry-After` when present.
- Preserving the same idempotency key.
- Enforcing an overall deadline.
- Never generically retrying validation or authorization errors.

Example:

~~~java
Retry retry = Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(3))
        .jitter(0.5)
        .filter(this::isRetryableRemoteFailure);

return webClient.post()
        .uri("/reservations")
        .header("Idempotency-Key", reservationKey)
        .bodyValue(request)
        .retrieve()
        .bodyToMono(ReservationResponse.class)
        .retryWhen(retry)
        .timeout(Duration.ofSeconds(10));
~~~

This example retries only the HTTP publisher. If that publisher sits inside a database transaction, retries can stretch transaction duration or repeat in-transaction side effects. Normally execute remote retries outside local DB transactions with a stable key.

## 28. Ensuring Workflow State Is Recoverable

A durable workflow should track:

- Current state and next step.
- Correlation IDs to external systems.
- Idempotency key.
- Attempt count and next retry time.
- Last classified error, not merely raw messages.
- Lease/owner so another worker can take over on crash.
- Reconciliation mechanism for unknown states.
- Compensating actions when needed.

Never rely solely on logs to infer where a workflow left off. Logs can be dropped or expire past retention; state needed for continuation must be durably persisted in the database.

## 29. Observability and Operations for Integrations

Useful metrics:

| Metric | Purpose |
| --- | --- |
| HTTP dependency latency/error rate | Monitor external systems |
| Outbox pending count/oldest age | Detect stalled or slow relays |
| Outbox retry/exhausted count | Spot repeatedly failing events |
| Inbox duplicate count | Measure message redeliveries |
| Workflow age by state | Identify stuck workflows |
| Compensation success/failure | Track saga recovery |
| Idempotency conflict count | Track duplicate requests/events |
| Database pool active/pending | Detect transactions holding connections open |

Logs should safely include correlation IDs, order/workflow IDs, event IDs, and idempotency keys. Never log tokens, payment credentials, or full sensitive payloads.

Configure alerts for aging outbox backlogs, overdue `PENDING` workflows, unreconciled `UNKNOWN` payments, and failed compensations. These states require explicit operational playbooks rather than infinite retries.

## 30. Integration Testing Between Database and External Systems

You cannot validate the entire workflow using mocked repositories alone. Layer your tests:

**Service unit tests**

- Verify invocation order between remote and local publishers.
- Verify error mapping and workflow state transitions.
- Verify idempotency keys remain unchanged across retries.
- Verify compensation branches run when required.

**Database integration tests**

- `Order` and outbox commit together.
- If outbox insert fails, `Order` rolls back too.
- Inbox insert and business updates commit/roll back together.
- Unique constraints prevent duplicate event processing.
- Multi-worker claims/leases never claim the same event concurrently.

**HTTP contract/component tests**

- Remote returns 2xx, 4xx, 5xx.
- Timeouts before and after server processing.
- Invalid response payloads.
- Idempotency keys are transmitted properly.

**End-to-end/recovery tests**

- Process crashes after commit before sending the event.
- Process crashes after sending before marking published.
- Remote succeeds while DB outcome update fails.
- Message is redelivered after consumer commits before ACK.
- Saga compensation fails and resumes.

Testcontainers can provide a real database for R2DBC integration tests. HTTP services can be simulated with WireMock or a mock web server; include timeout and dropped-response scenarios to test ambiguous outcomes.

## 31. Common Mistakes

1. **Holding database transactions while waiting on HTTP.** Connections and locks stay held for too long.
2. **Assuming `@Transactional` rolls back HTTP or message brokers.** Transaction managers govern only enlisted resources.
3. **Writing DB then publishing events directly.** DB can commit while events are lost.
4. **Publishing events before DB commit.** Consumers may receive events for nonexistent data.
5. **Retrying POST with a new idempotency key.** Can create duplicate side effects.
6. **Treating HTTP timeouts as guaranteed remote failure.** Remote may have processed it before the response dropped.
7. **Marking `PAYMENT_FAILED` on ambiguous outcomes.** Risks overlooking a payment that actually succeeded.
8. **Outbox relay holding row locks during network sends.** Extends transaction and connection lifetimes.
9. **Assuming outbox provides exactly-once delivery.** Relays can redeliver after crashes.
10. **Consumer ACKing before commit.** Can lose messages if the database rolls back.
11. **Missing inbox/unique event IDs.** Redelivered messages can apply business logic twice.
12. **Using in-memory event listeners for critical events.** Process can exit after commit before listeners finish.
13. **Using `@TransactionalEventListener` imperatively without accounting for reactive context.** Reactive transactions require preserving context via Spring-supported mechanisms.
14. **Using retries instead of compensation.** Retries do not undo already-committed external side effects.
15. **Not persisting workflow state.** After a restart, the process cannot tell which step to resume from.
16. **Unbounded retries or missing dead-letter/reconciliation.** Workflows can loop forever and hide operational failures.

## Quick Selection Rules

- Wrap only database operations requiring atomicity inside a reactive transaction.
- Never hold connections/row locks while waiting on HTTP or brokers.
- For read-only/validation HTTP calls, you may call before the transaction and write locally, while accounting for staleness over time.
- For synchronous side effects, persist pending state, call remote outside transactions, and save results in a new transaction.
- Use stable idempotency keys for retryable HTTP commands.
- Use a transactional outbox when local data and event-emission intent must commit together.
- Use an inbox/unique event ID so consumers handle redelivered messages safely.
- Use sagas and compensation for multi-system workflows.
- Treat timeouts as potentially ambiguous; reconcile before triggering new side effects.
- Configure bounded retries with backoff, jitter, and deadlines.
- ACK messages only after inbox and business updates commit.
- Monitor outbox age, workflow states, dependency latency, and compensations.
- Test crash windows, duplicate deliveries, and mid-workflow failures.

Coordinating HTTP calls or external events with persistence operations requires clear consistency boundaries. Spring Data R2DBC reactive transactions only protect operations on the database managed by the transaction manager; they cannot undo side effects already committed in external systems. Keep local transactions short, use workflow state and idempotency for HTTP calls, transactional outboxes so post-commit events are not lost, inboxes to prevent duplicate processing, and sagas/compensations for multi-service flows. By explicitly designing for timeouts, retries, crash windows, and reconciliation, applications recover safely when an external system slows down or fails.
