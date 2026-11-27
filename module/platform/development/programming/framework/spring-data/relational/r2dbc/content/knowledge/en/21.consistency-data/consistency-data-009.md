# Local Transaction Boundaries Across Multiple Resources

Spring Data R2DBC supports reactive transactions for operations against a single `ConnectionFactory`. That transaction can guarantee multiple SQL statements commit or roll back together on the managed database resource. However, a local R2DBC transaction does not automatically span message brokers, HTTP services, Redis, filesystems, or another `ConnectionFactory`.

This is a critical boundary when designing a use case with multiple side effects. For instance, creating an order in a database and then sending an event to Kafka are two operations against two independent resources. If the database commits yet sending the message fails, state across the two systems becomes inconsistent. If sending the message succeeds yet the database transaction rolls back, consumers may receive an event referencing an order that does not exist.

To handle this properly, distinguish local transactions from distributed transactions, identify which resources genuinely participate in the same transaction, and select an integration pattern such as transactional outbox, saga, idempotent retries, or an appropriate distributed coordination mechanism.

## 1. Local Transactions in Spring Data R2DBC

`R2dbcTransactionManager` manages transactions for a single R2DBC `ConnectionFactory`. When a transaction starts, Spring acquires and binds an appropriate connection into the reactive transaction context. Data access operations configured to use the same `ConnectionFactory` and participate in that transaction can share the managed connection.

Configuration example:

```java
@Configuration
public class DatabaseConfiguration {

    @Bean
    ReactiveTransactionManager r2dbcTransactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
```

A service can use `@Transactional` on a reactive method:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderLineRepository lineRepository;

    @Transactional
    public Mono<Order> createOrder(CreateOrderCommand command) {
        Order order = Order.from(command);

        return orderRepository.save(order)
            .flatMap(saved ->
                Flux.fromIterable(command.lines())
                    .map(line -> OrderLine.from(saved.getId(), line))
                    .concatMap(lineRepository::save)
                    .thenReturn(saved)
            );
    }
}
```

If both repositories use the same `ConnectionFactory` and the same reactive transaction manager, the write operations can participate in a single local transaction. If any operation emits an error in the reactive chain, the transaction can roll back.

Reactive transactions are bound to Reactor Context, rather than relying on every operation running on the same thread. Therefore, chain all publishers together and return the publisher for Spring to manage. Never call `subscribe()` or `block()` inside a transactional method to spawn a detached branch of work.

## 2. Resource Scope of R2dbcTransactionManager

`R2dbcTransactionManager` manages a specific `ConnectionFactory`. It is not a transaction coordinator for every resource an application uses.

| Resource | Automatically participates in R2DBC transaction? | Notes |
|---|---|---|
| Repositories and `R2dbcEntityTemplate` using the same `ConnectionFactory` | Yes | Requires the matching transaction manager and reactive context. |
| `DatabaseClient` using the same `ConnectionFactory` | Yes | Spring integrates connection management to join the transaction. |
| A different `ConnectionFactory` | No | Needs its own transaction manager or a different coordination mechanism. |
| JDBC `DataSource` | No | JDBC transaction manager and R2DBC transaction manager manage separate connections. |
| Kafka/RabbitMQ broker | No | Brokers have separate transactions and do not auto-join R2DBC database transactions. |
| Redis or cache | No | Cache commands are side effects outside the R2DBC transaction. |
| Another service's HTTP API | No | Remote services cannot be rolled back by a local database transaction. |
| File system/object storage | No | File writes are not rolled back when a database transaction fails. |

The key point is that a transaction manager only manages the resource it was designed to control. Placing multiple operations inside the same `@Transactional` method does not turn them into a unified ACID transaction if those operations use different resource managers.

## 3. Why Multiple Resources Do Not Auto-Commit Together

Suppose a use case must write an order to the database and send `OrderCreated` to a message broker. Two naive orderings are common, and both leave a failure window:

**Send message first, then commit database:**

1. The application sends `OrderCreated` successfully.
2. Consumers receive the message and try to read the order.
3. The R2DBC transaction fails or rolls back.
4. The message still exists even though the order was never committed.

**Commit database first, then send message:**

1. The R2DBC transaction commits the order.
2. The application sends the message.
3. The broker is unavailable or sending fails.
4. The order exists, yet the event was never published.

An R2DBC transaction cannot roll back a message already accepted by the broker, nor can a broker transaction automatically roll back a record already committed in the database. Merely swapping the order of the two calls does not eliminate the failure window; it simply shifts the failure from one side to the other.

The example below does not create atomicity between the database and Kafka despite having `@Transactional`:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    Order order = Order.from(command);

    return orderRepository.save(order)
        .flatMap(saved ->
            Mono.fromFuture(kafkaTemplate.send(
                "orders",
                saved.getId().toString(),
                new OrderCreated(saved.getId())
            )).thenReturn(saved)
        );
}
```

The Kafka send publisher can be chained into the reactive pipeline, yet `R2dbcTransactionManager` still manages only the database connection. If Kafka succeeds and the database transaction rolls back, the message does not disappear. If the database commits and Kafka fails, the database transaction cannot undo an already-completed commit simply because an external publisher emits an error afterward.

## 4. Distinguishing Local Transactions from Distributed Transactions

A **local transaction** guarantees atomicity within the scope of a single resource manager, such as a transaction on a connection managed by `R2dbcTransactionManager`.

A **distributed transaction** coordinates multiple resource managers so they commit or roll back together under a shared protocol. The two-phase model is commonly called two-phase commit (2PC): a coordinator asks participants to prepare to commit, then decides whether to commit or roll back. This requires every participant to support the protocol and an appropriate coordinator.

The R2DBC SPI does not provide a standard XA/distributed transaction protocol for `R2dbcTransactionManager` to arbitrarily coordinate multiple `ConnectionFactory` instances and brokers. Do not infer that because an API is named `@Transactional`, it automatically provides 2PC.

Within the Spring ecosystem, certain technologies or brokers have their own transactions, and some platforms may provide infrastructure-level distributed coordination. Such coordination requires explicit integration and support from all resource managers; it is not a default feature of Spring Data R2DBC. Before choosing distributed transactions, verify whether drivers, brokers, coordinators, recovery semantics, and deployment models fully support it.

## 5. Multiple ConnectionFactory Instances Mean Multiple Transaction Boundaries

An application may connect to two databases via two `ConnectionFactory` beans, such as an orders database and an analytics database. Each factory typically has a matching transaction manager:

```java
@Bean
@Primary
ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}

@Bean
ReactiveTransactionManager reportingTransactionManager(
        @Qualifier("reportingConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}
```

A transaction managed by `ordersTransactionManager` does not automatically manage connections created by `reportingConnectionFactory`. Even if both factories point to the same database server or database name, they still issue independent connections.

With multiple transaction managers, explicitly specify the manager for each service:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> createOrder(...) {
    // Operations on ordersConnectionFactory.
}
```

If a use case must write to both databases, `@Transactional` with one manager covers only that manager's resource. You can execute two sequential local transactions and design retries/compensation, or use a genuinely compatible distributed transaction coordinator if requirements and infrastructure permit. Do not assume two nested `@Transactional` annotations produce an atomic commit across two databases.

## 6. Transactional Outbox: Writing Data and Events in the Same Database Transaction

Transactional outbox solves the database-commit-and-event-emission problem by saving the event to send as a row in the same database transaction as the business data.

Workflow:

1. Start an R2DBC transaction.
2. Write the order or business mutation.
3. Write an outbox row containing event type, payload, aggregate ID, and pending status.
4. Commit both business data and the outbox row together.
5. A background publisher reads pending outbox rows and sends them to the broker.
6. After broker acknowledgement, the publisher marks the outbox row as sent or updates a corresponding checkpoint.

If the database transaction rolls back, both the order and the outbox row roll back. If the database commits, the event stays in the outbox so the publisher can send it once the broker recovers.

Simple schema example:

```sql
CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX ix_outbox_pending
    ON outbox_event (created_at)
    WHERE published_at IS NULL;
```

The partial index syntax in this example applies to databases like PostgreSQL; other databases may require different indexes or schemas. JSON/JSONB types can also be chosen for `payload` if supported by the driver and schema.

Writing the domain object and outbox row inside the same reactive transaction:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    Order order = Order.from(command);

    return orderRepository.save(order)
        .flatMap(saved -> {
            OutboxEvent event = OutboxEvent.pending(
                UUID.randomUUID(),
                "Order",
                saved.getId().toString(),
                "OrderCreated",
                serialize(new OrderCreated(saved.getId()))
            );

            return outboxRepository.save(event)
                .thenReturn(saved);
        });
}
```

Both repositories must share the same database `ConnectionFactory` and transaction manager. If the outbox resides in a different database, the two writes are no longer atomic within one R2DBC transaction.

## 7. Outbox Publishers and At-Least-Once Delivery

A background publisher queries pending events, sends each event to the broker, and then updates the status. Sending and marking as sent remain two operations on two distinct resources:

- If sending succeeds but the process stops before updating `published_at`, the event will be resent after restart.
- If marked as sent first before sending to the broker, the process may stop between marking and sending, losing the event.

Consequently, the standard implementation sends first, marks afterward, and accepts the possibility of duplicates. This is the **at-least-once** delivery model. Consumers need idempotent handling based on event ID or a unique business key.

Publisher sketch:

```java
Mono<Void> publishOne(OutboxEvent event) {
    return Mono.fromFuture(kafkaTemplate.send(
            "domain-events",
            event.getAggregateId(),
            event.getPayload()))
        .then(outboxRepository.markPublished(
            event.getId(), Instant.now()))
        .then();
}
```

This snippet illustrates the send-then-mark sequence; event selection, leases/locks, retries, timeouts, and error handling must be implemented according to the actual broker and database. If multiple publishers run concurrently, a claim mechanism is needed so they do not all send the same row. You can use leases, a `PROCESSING` status, row locks, or syntax like `FOR UPDATE SKIP LOCKED` if supported by the database.

Do not claim an outbox provides end-to-end exactly-once delivery. Publishers can send duplicates, brokers can redeliver, and consumers can reprocess. Stable event IDs combined with a consumer inbox/deduplication achieve effectively-once processing at the business level, though deduplication state must be explicitly designed and stored.

## 8. Consumer Idempotency

Event consumers should have a way to recognize already-processed events. An inbox table can store event IDs with a unique constraint:

```sql
CREATE TABLE processed_event (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

When a consumer receives an event, it opens a local transaction in the target database, attempts to insert the event ID into `processed_event`, and applies the business mutation in the same transaction. If the event ID already exists, the consumer knows the event was already processed and skips applying duplicate mutations.

Flow illustration:

```java
@Transactional
public Mono<Void> handle(OrderCreated event) {
    return processedEventRepository.insertIfAbsent(event.eventId())
        .flatMap(inserted -> {
            if (!inserted) {
                return Mono.empty();
            }

            return projectionRepository.applyOrderCreated(event);
        });
}
```

`insertIfAbsent` is an illustrative abstraction; implementation can use `INSERT ... ON CONFLICT DO NOTHING` in PostgreSQL or the database's equivalent syntax. If writing the inbox and updating the projection do not share the same transaction, the process can crash between the two steps and cause duplicate processing or lost updates.

If a consumer performs side effects outside the database, such as calling a payment service, the inbox transaction cannot roll back those side effects. In that case, use an idempotency key supported by the target service or place the action inside a stateful saga with compensation.

## 9. Sagas for Business Workflows Spanning Multiple Services

When a use case spans multiple services or independent databases, a saga breaks the workflow into steps, each using its own service's local transaction. If a later step fails, the system executes compensating actions to bring the business state to an acceptable outcome.

Order placement example:

1. Order Service creates the order in `PENDING` state.
2. Inventory Service reserves stock.
3. Payment Service collects payment.
4. Order Service transitions the order to `CONFIRMED`.

If payment fails after stock was reserved, the saga calls Inventory Service to release stock. If order confirmation fails after payment was collected, the workflow may issue a refund. A compensating action is a new business operation, not a rollback of a database transaction already committed by an earlier service.

Two common coordination styles:

- **Choreography:** services emit and react to each other's events without a central coordinator driving every step. This reduces central coupling, though overall flow can become hard to trace across many branches.
- **Orchestration:** a saga orchestrator tracks workflow state and sends commands to each service. This makes ordering, timeouts, retries, and compensation explicit, while introducing a coordinator component.

Sagas fit long-running, multi-resource workflows that accept eventual consistency. They do not provide global isolation like a single ACID transaction; while a saga runs, services may observe intermediate states such as `PENDING`, `RESERVED`, or `PAYMENT_PENDING`.

## 10. Retries, Timeouts, and Compensation

Every saga step must clearly define:

- Pre- and post-execution states.
- Idempotency keys so resent commands never duplicate effects.
- Timeouts and retry counts.
- Which errors are retryable vs. non-recoverable business failures.
- Compensating actions if a subsequent step cannot complete.
- State persistence so the process can resume after restarts.

Never infinitely retry an operation known to be unrecoverable, such as insufficient account balance or out-of-stock items. Conversely, transient network errors can be retried with backoff and jitter. When unsure whether a request reached the target service, idempotency keys prevent double execution.

Compensation does not always completely undo the original action. For example, a sent email cannot be unsent; a captured payment may require a refund rather than deleting payment history. Thus, sagas must model realistic business states and compensating actions.

## 11. Integrating with HTTP APIs and External Services

A database transaction cannot hold locks on a remote HTTP service or roll back requests that service has already processed. Avoid keeping R2DBC transactions open while waiting on HTTP calls.

A generally better structure:

1. Read and validate necessary data before opening a transaction if locking is not required during the external call.
2. Call the external service with an idempotency key and appropriate timeout if that step must happen before writing.
3. Open a short R2DBC transaction to persist the outcome state and related data.
4. If both sides must coordinate across multiple steps, persist workflow/saga state and emit retryable commands/events.

If business ordering requires writing to the database before making the HTTP call, write a `PENDING` status and an outbox command in the same transaction; a worker performs the HTTP call after commit and updates the outcome in another local transaction. That way, even after a process restart, the system still knows what work remains.

## 12. Integrating with Caches and Filesystems

Caches are typically derivable copies of database data. Updating a cache before the database transaction commits can expose new state to other requests before data is officially committed. If the transaction rolls back, the cache becomes stale or wrong.

Several options:

- Invalidate or update the cache after the database commits.
- Emit invalidation events via an outbox for a worker to process.
- Use TTLs and cache-aside patterns so caches self-refresh.
- Do not treat cache writes as part of a database transaction without a genuine coordination protocol.

Similarly, writing files or object storage does not roll back with an R2DBC transaction. When storing files alongside metadata, upload the file to a staging area first, write metadata/status in the database, and promote the file to final status after commit. Include a cleanup job for staged files if the database rolls back or the workflow is abandoned.

## 13. Practices That Easily Create Inconsistent State

| Practice | Risk |
|---|---|
| Writing to DB then sending message, expecting `@Transactional` to cover both | Message sending can fail after the database already committed. |
| Sending message before writing to DB | Consumer may process event before DB data exists; DB rollback does not recall the message. |
| Writing to two `ConnectionFactory` beans under one `R2dbcTransactionManager` | The manager governs only the factory it was configured with. |
| Making HTTP calls inside a long transaction | Pins connections/locks during network waits and still cannot roll back external services. |
| Writing to cache before commit | Cache may hold data that the database transaction later rolls back. |
| Using `onErrorResume` to ignore side-effect failures | Application may report success even though a resource was not updated. |
| Retrying without idempotency keys | Can produce duplicate records, payments, or messages. |
| Marking outbox as sent before broker acknowledgement | Process crashing between steps can lose events. |

## 14. Choosing Integration Patterns by Requirement

| Need | Suitable pattern |
|---|---|
| Multiple SQL statements on the same database must commit together | One local R2DBC transaction with the same `ConnectionFactory`. |
| Reliable database write and event emission | Transactional outbox with a retrying publisher. |
| Consumer may receive events multiple times | Inbox/deduplication and idempotent processing. |
| Multi-service workflow with multiple business steps | Saga choreography or orchestration. |
| Multiple resource managers supporting 2PC requiring global atomic commit | Compatible distributed transaction coordinator, after verifying full support and operational overhead. |
| Updating cache after authoritative data commits | After-commit invalidation or outbox event. |
| Writing files/object storage alongside metadata | Stateful workflow, staging area, and cleanup/compensation. |

Do not pick distributed transactions merely to avoid modeling intermediate states. 2PC can pin resources while coordinators wait on participants, increases operational complexity, and creates infrastructure dependencies. For most web and message-driven systems, outbox plus eventual consistency scales and recovers more cleanly.

## 15. Process for Designing Multi-Resource Use Cases

Before implementing, map out resources and transaction boundaries:

1. List every place with side effects: databases, brokers, caches, HTTP services, file stores, and secondary databases.
2. Identify which `ConnectionFactory` and transaction manager owns each database operation.
3. Mark which operations can share a single local transaction and which lie outside.
4. Document possible failure states between every pair of steps, such as DB committed while message unsent.
5. Choose outbox for events requiring durable post-commit delivery; choose saga for multi-step workflows needing compensation.
6. Design idempotency keys, unique constraints, retries/backoff, timeouts, and dead-letter/rejection handling.
7. Persist enough workflow/checkpoint state to resume after restarts.
8. Move side effects out of long database transactions; keep transactions open only around database work requiring atomicity.
9. Test simulated crash points: before commit, after commit, after sending a message, and before marking it sent.
10. Monitor outbox backlog, pending event age, retry counts, stuck sagas, and compensation failures.

## 16. Testing and Operating Consistency

Testing only the happy path is insufficient to verify a multi-resource workflow is safe. Test failure windows as well:

- Database transaction rolls back after writing domain row and outbox row: neither must exist.
- Database commits successfully, then publisher stops before sending: event stays pending and is delivered after restart.
- Broker receives event, then publisher stops before marking: event may be resent; consumer must prevent duplicate processing.
- Consumer commits business update and loses acknowledgement: broker may redeliver; inbox/deduplication must prevent repeat effects.
- A saga step times out after target service already executed: retry with the same idempotency key must return the corresponding result instead of repeating side effects.
- Compensation fails: workflow must be flagged for intervention or retry, never falsely reported complete.

Key metrics include pending outbox count and age, publish failure rate, duplicate events skipped, saga completion time, workflows stuck in intermediate states too long, retry counts, and failed compensations. Include correlation IDs in logs across services to trace an entire business operation end to end.

Spring Data R2DBC local transactions are the right tool for ensuring atomicity within a single `ConnectionFactory`. Whenever a use case spans multiple databases or resource types, proactively design commit boundaries, intermediate states, and recovery paths. Outbox pairs data with events inside the same database transaction; sagas coordinate local steps and compensating actions; idempotency makes retries safe. No single `@Transactional` annotation turns independent resources into one unified ACID transaction.
