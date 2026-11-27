# Emitting Events After a Successful RPC

## 1. Events Must Reflect a Committed Fact

In **SPRING_GRPC**, clients invoke RPCs according to a Protocol Buffers contract; the Spring service adapter converts the request into a command and invokes the application use case. When the use case mutates state, the system often needs to notify other services via a message broker.

For example, after an order is successfully created, the system may emit `OrderCreated` for inventory, notification, or analytics services to process. This event expresses a fact that has occurred: the order was created. It differs from a `CreateOrder` request, which only expresses a request to perform an action.

A critical requirement is that an event must only be emitted once the business change has committed. If an event is emitted before the transaction commits, consumers may observe a success event even if the database rolls back. If you simply wait for the gRPC method to return and send a message directly, the process may crash in between and lose the event.

## 2. Defining Precisely What "Successful RPC" Means

An RPC can pass through several milestones:

1. The request is authenticated and validated.
2. The use case executes business rules.
3. The database transaction commits state changes.
4. The event is durably recorded for dispatch.
5. The broker confirms receipt of the event.
6. Consumers process the event.
7. The client receives the gRPC response.

These milestones are not synonymous. For a synchronous order-creation RPC, the API can define success when steps 3 and 4 complete: the order data has committed and the event has been written to the outbox in the same transaction. A relay can publish the event afterward.

For an ingress RPC that only accepts an asynchronous command, an `ACCEPTED` response only confirms that the command was recorded under the durability contract. `OrderCreated` must not be emitted at that time because the order may not have been created yet.

Clearly document whether each RPC response means `COMPLETED` or `ACCEPTED`. Events must reflect actual business state and must not be inferred solely from the server calling `observer.onCompleted()`.

## 3. Flow for Emitting Events After a Synchronous RPC

Recommended flow when an RPC performs state changes in a database:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant G as Spring gRPC adapter
    participant U as Application use case
    participant DB as Database
    participant O as Outbox relay
    participant B as Message broker
    participant W as Consumer
    C->>G: CreateOrder(request)
    G->>U: execute(CreateOrderCommand)
    U->>DB: Save order + outbox event
    DB-->>U: Commit
    U-->>G: OrderResult
    G-->>C: gRPC OK / response
    O->>DB: Read pending outbox
    O->>B: Publish OrderCreated
    B-->>O: Broker acknowledgement
    O->>DB: Mark published
    B->>W: Deliver event
    W->>W: Handle idempotently
~~~

The outbox record is committed alongside the order state. Thus, even if the relay runs slowly or temporarily stops, the event remains in the database to be sent later. The RPC does not have to keep a connection open until all consumers finish.

The event may reach the broker before or after the client receives the response, depending on relay scheduling and the network. Contracts must rely on commit state, not on observed ordering between the two communication channels.

## 4. Why Not Publish Directly After Calling the Use Case?

A deceptively simple approach:

~~~java
OrderResult result = createOrderUseCase.execute(command);
kafkaTemplate.send("orders.events", result.orderId(), toEvent(result));
observer.onNext(toReply(result));
observer.onCompleted();
~~~

This approach leaves an error gap between the database and the broker:

| Failure point | Consequence |
|---|---|
| Database commits, process crashes before `send` | State changed, but the event is lost |
| Broker receives event, database transaction rolls back | Consumer receives an event for an uncommitted change |
| Broker receives event, acknowledgement is lost | Producer may resend, creating a duplicate |
| `send` returns a future, but the app does not track its outcome | RPC may report success even though publish failed |

Simply reversing the order to publish before the database commits does not solve it either: the broker can deliver the event while the transaction subsequently rolls back. A database and a broker generally do not participate in the same atomic transaction.

For important events, use a **transactional outbox** to save the business change and the intent to emit the event in the same database transaction. Direct publishing is only suitable when best-effort delivery is acceptable and event loss can be tolerated.

## 5. Domain Events and Integration Events

The two event kinds serve different purposes:

- **Domain event** describes something that happened inside the domain, such as `OrderWasCreated`. It may carry internal types and serve to coordinate use cases.
- **Integration event** is a public contract sent to other systems, such as `orders.created.v1`. It needs a stable schema, versioning, and only data permitted to be shared.

You do not necessarily serialize domain events directly to the broker. The application/infrastructure layer can map a domain event into an integration event to control the data, event name, and compatibility.

Example:

~~~java
public record OrderCreatedDomainEvent(
        String orderId,
        String customerId,
        java.time.Instant createdAt) {}

public record OrderCreatedV1(
        String eventId,
        String orderId,
        String customerId,
        java.time.Instant occurredAt,
        String correlationId) {}
~~~

A domain event may not need `eventId` or `correlationId`; an integration event needs these fields so consumers can deduplicate and trace it.

## 6. Writing Business State and Outbox in the Same Transaction

The use case should own the transaction encompassing the business change and the outbox record. The gRPC adapter simply calls the use case:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CreateOrderService implements CreateOrderUseCase {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final OrderEventMapper eventMapper;
    private final IdGenerator ids;
    private final Clock clock;

    public CreateOrderService(
            OrderRepository orders,
            OutboxRepository outbox,
            OrderEventMapper eventMapper,
            IdGenerator ids,
            Clock clock) {
        this.orders = orders;
        this.outbox = outbox;
        this.eventMapper = eventMapper;
        this.ids = ids;
        this.clock = clock;
    }

    @Override
    @Transactional
    public OrderResult execute(CreateOrderCommand command) {
        Order order = Order.create(
                ids.newOrderId(),
                command.customerId(),
                command.lines(),
                clock.instant());

        orders.save(order);

        OrderCreatedV1 event = eventMapper.toIntegrationEvent(
                order,
                ids.newEventId(),
                command.correlationId());

        outbox.save(OutboxRecord.pending(
                event.eventId(),
                "orders.created",
                1,
                order.id(),
                event));

        return new OrderResult(order.id(), order.status());
    }
}
~~~

This is an illustrative skeleton; the repository and outbox serializer must be implemented for the persistence technology in use. The decisive point is that `orders.save(...)` and `outbox.save(...)` participate in **the same transaction manager and the same database transaction**. If the outbox resides in a different database or uses a different transaction manager, atomicity is no longer guaranteed.

When the transaction rolls back, both the order and the outbox record roll back. When it commits, both exist together. The Spring transaction proxy completes the commit before the proxied call returns to the adapter, provided the use case is invoked properly through the bean proxy.

## 7. Structure of an Outbox Record

An outbox table typically has these fields:

| Field | Purpose |
|---|---|
| `event_id` | Unique ID, used as a deduplication key |
| `event_type` | Integration event name |
| `schema_version` | Payload version |
| `aggregate_id` | Entity/aggregate that produced the event |
| `aggregate_version` | Version sequence of the aggregate if needed |
| `payload` | Serialized event content |
| `created_at` | Timestamp when the event was recorded |
| `published_at` | Timestamp when the broker confirmed |
| `status` / `attempts` | Dispatch status and attempt count |
| `next_attempt_at` | Next retry timestamp if using backoff |

Place a unique constraint on `event_id`. You can add an index for unpublished records by `status` and `created_at`/`next_attempt_at`. Have a retention or cleanup policy for published records so the outbox does not grow without bound.

Do not store credentials or raw gRPC metadata in the payload. Include only business data and permitted context.

## 8. Relay Publishes Events and Marks Only After Acknowledgement

The outbox relay reads pending records, sends events to the broker, and only then marks them published:

~~~java
public void publishOne(OutboxRecord record) {
    try {
        kafkaTemplate.send(
                topicFor(record.eventType()),
                record.aggregateId(),
                record.payload())
            .get(5, TimeUnit.SECONDS);

        outboxRepository.markPublished(
                record.eventId(),
                clock.instant());
    } catch (Exception ex) {
        outboxRepository.scheduleRetry(
                record.eventId(),
                nextAttempt(record.attempts()),
                safeErrorCode(ex));
    }
}
~~~

The example uses `get` in a relay worker to illustrate waiting for broker acknowledgement; do not call this blocking code on the gRPC event loop. You can use an asynchronous callback if the relay is designed around that model.

Mark published only after acknowledgement. If the process crashes after broker acknowledgement but before updating the database, the record remains pending and will be published again. This is an intentional duplicate to avoid losing events; consumers must be idempotent.

When running multiple relay instances, use a claim/lease mechanism or short-lived row locking to avoid processing the same record concurrently. With PostgreSQL you can use `FOR UPDATE SKIP LOCKED`; the exact choice depends on the database. Avoid holding a database transaction open across the broker network wait whenever possible.

## 9. At-Least-Once Delivery and Idempotent Consumers

A transactional outbox ensures events are not lost between database commit and publish intent, but it normally yields **at-least-once** delivery semantics. A consumer may receive the same event multiple times.

Consumers need to:

1. Use `eventId` as the identifying key.
2. Record processed events using a unique constraint or an inbox table.
3. Perform side effects and write the inbox marker in the same transaction if using the same database.
4. Only ack/commit offsets after processing reaches a safe milestone.
5. Have retry/backoff and a dead-letter flow for unrecoverable errors.

If a consumer calls an external system outside the database, the idempotency key must be passed to that system or another coordination mechanism must be used. Persisting the marker only before calling the side effect risks losing work if the process crashes; persisting the marker after the side effect risks duplication if a crash occurs in between. Choose an appropriate transaction boundary or API idempotency strategy.

## 10. What Is the Role of Spring `@TransactionalEventListener`?

Spring provides `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` to run a listener after a transaction commits:

~~~java
@Component
public class OrderLocalEventListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedDomainEvent event) {
        localCache.evict(event.orderId());
    }
}
~~~

This is a good fit for best-effort internal reactions such as evicting a cache or updating an in-process component. The listener does not run if the transaction rolls back.

However, `AFTER_COMMIT` is not durable message delivery. If the process crashes after the database commits but before the listener publishes to the broker, the event can still be lost. If the listener sends to the broker and the broker ack is lost, duplicates can occur. Therefore, for critical integration events, write to an outbox inside the transaction instead of relying solely on a post-commit callback.

Do not use `@TransactionalEventListener` to create the illusion that the database and broker were committed atomically.

## 11. The gRPC Adapter Only Returns a Response from the Use Case Result

The adapter should not decide on its own that an event occurred merely because it received a valid request. It calls the use case; the use case commits state and outbox; the adapter maps the result into a protobuf response:

~~~java
@Override
public void createOrder(
        CreateOrderRequest request,
        StreamObserver<CreateOrderReply> observer) {
    try {
        CreateOrderCommand command = mapper.toCommand(
                request,
                callerContext.current());

        OrderResult result = createOrderUseCase.execute(command);

        observer.onNext(CreateOrderReply.newBuilder()
                .setOrderId(result.orderId())
                .setStatus(result.status())
                .build());
        observer.onCompleted();
    } catch (OrderValidationException ex) {
        observer.onError(Status.INVALID_ARGUMENT
                .withDescription("Invalid order request")
                .asRuntimeException());
    } catch (RuntimeException ex) {
        observer.onError(Status.INTERNAL
                .withDescription("Unable to create order")
                .asRuntimeException());
    }
}
~~~

With this structure, `execute(...)` returns after the transaction proxy has committed successfully. If the commit fails, the adapter receives no success result and sends no success response. The outbox relay can publish the event independently after commit.

Do not publish events in `finally`, `onCompleted()`, or a callback that only reflects transport state. `onCompleted()` means the server has finished the response stream; it is not a transaction commit hook and does not prove the client received the response.

## 12. Deadlines and Cancellation Do Not Reverse a Commit

A client may cancel the RPC or the deadline may expire around the time the transaction commits:

- If the transaction rolls back before committing, the outbox record does not exist either.
- If the transaction already committed, the event has been recorded for dispatch; subsequent client cancellation does not automatically roll back data or delete the outbox.
- If the response is lost after commit, the client may retry and needs an idempotency key to receive the same result.

Do not use gRPC cancellation as a mechanism to cancel a committed event. If business rules require undoing or cancelling a completed action, emit a compensating command such as `CancelOrder` or `RefundPayment`; that is a new business action, not deleting historical events.

## 13. Choosing Event Payload and Ordering

An integration event should contain the data consumers need, without necessarily copying the entire aggregate:

~~~json
{
  "eventId": "evt-31a7",
  "eventType": "orders.created",
  "schemaVersion": 1,
  "aggregateId": "order-42",
  "aggregateVersion": 1,
  "correlationId": "req-7c20",
  "occurredAt": "2026-11-19T10:15:30Z",
  "payload": {
    "orderId": "order-42",
    "customerId": "customer-9",
    "status": "CREATED"
  }
}
~~~

Choose a broker key by aggregate if consumers need to process events for the same entity in order. With Kafka, partitions guarantee ordering within a partition; consumers must still avoid concurrently processing records for the same aggregate in a way that reorders side effects. `aggregateVersion` helps consumers detect missing, duplicate, or out-of-order events.

Version event schemas independently of RPC request versions. Add fields according to compatibility rules and do not change the meaning of published events. An `orders.created` event must always mean the order was created, never changing to "order creation request received".

## 14. When to Wait for the Broker Before Returning a gRPC Response?

With an outbox, the standard pattern is to return the response after the business transaction commits and the outbox record is durably persisted. The broker relay can send afterward. This reduces latency and avoids holding RPCs open while the broker is slow.

If the contract mandates that a response succeeds only once the broker has confirmed the event, the system can wait for publisher acknowledgement after commit. However, recognize that:

- The database has already committed before waiting on the broker.
- If the broker does not confirm, you cannot pretend the database did not change.
- Client retries must use an idempotency key.
- You may need to return a state such as "committed, pending publish" via an operation status rather than returning a generic error that leads callers to believe the transaction did not occur.

Waiting on `send().get()` does not create an atomic transaction between the database and the broker. An outbox remains the durable mechanism for retrying and recovering from failures.

## 15. Testing Events After a Successful RPC

Tests need to verify the relationship between commit, response, and event:

| Scenario | What to verify |
|---|---|
| Order created successfully | Order and outbox record commit together |
| Validation failure | No order and no event |
| Transaction rollback | Outbox record does not exist |
| Broker temporarily down | Outbox stays pending and RPC follows the published success milestone |
| Relay publishes successfully | Broker receives the right event type, ID, key, and payload |
| Relay crashes after broker ack | Event may be resent; consumer does not duplicate side effects |
| `AFTER_COMMIT` listener | Does not run when transaction rolls back |
| Process crashes after commit before relay | Outbox record remains and is published after recovery |
| Client cancels after commit | Business state/outbox is not deleted |
| Client retries with same idempotency key | Does not create duplicate orders or business events |
| Events for same aggregate | Ordering/version preserved per policy |
| Consumer permanent failure | Bounded retries and observable dead-letter |

Use case unit tests should verify that the repository and outbox participate in the same transaction. Integration tests with a real/containerized database and broker verify commit, relay, acknowledgement, and redelivery. Mocking `KafkaTemplate` alone does not prove an event is durably published.

## 16. Observability and Diagnostics

Track each milestone separately:

- RPC success/failure by method and gRPC status.
- Business transaction commits/rollbacks.
- Outbox pending count, oldest record age, and retry counts.
- Time from commit to broker acknowledgement.
- Publish failures, broker timeouts, and duplicate publishes.
- Consumer lag, duplicate hits, dead-letters, and processing latency.
- Time gap between `occurredAt`, `publishedAt`, and consumer processing time.
- `eventId`, `aggregateId`, `aggregateVersion`, and correlation/trace IDs in logs and traces.

Do not use event ID or aggregate ID as high-cardinality metric labels. Use them in logs/traces; metrics should group by bounded values such as event type, topic, status, and consumer.

If a client receives gRPC OK but the event has not reached the consumer, check the outbox record, relay lag, broker acknowledgement, topic/partition, and consumer lag. Under an outbox contract, gRPC OK may only guarantee that the event was durably recorded for dispatch, not that the consumer has processed it.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Emitting event before database commit | Consumer sees events for rolled-back transactions | Write outbox inside the transaction |
| Publishing only after gRPC method returns | Process crash can lose the event | Write outbox before transaction commit |
| Using `onCompleted()` as a commit hook | Mixes transport lifecycle with transaction lifecycle | Emit events from outbox after commit |
| Treating `AFTER_COMMIT` as durable | Crash after commit can lose the event | Use a transactional outbox |
| Marking outbox published before broker ack | Events lost when broker rejects | Mark published after acknowledgement |
| Assuming outbox eliminates duplicates | Consumer may receive the event again | Idempotent consumer keyed by event ID |
| Emitting `OrderCreated` as soon as command is accepted | Broadcasts incorrect business state | Emit event after use case commits |
| RPC retry generates a new event ID | One intent may emit multiple events | Stable idempotency key and event ID |
| Waiting for all consumers to finish before returning RPC | Long RPCs coupled to all downstream services | Return at the published commit/acceptance milestone |

**Key takeaway:** A success event must represent a committed business change. With Spring gRPC, the use case should write business state and an outbox record in the same transaction; the adapter returns the response after the use case commits, while a relay publishes events and marks them only after broker acknowledgement. Delivery is typically at-least-once, so consumers must be idempotent. `AFTER_COMMIT` is useful for best-effort internal reactions, but it does not replace an outbox for critical integration events.
