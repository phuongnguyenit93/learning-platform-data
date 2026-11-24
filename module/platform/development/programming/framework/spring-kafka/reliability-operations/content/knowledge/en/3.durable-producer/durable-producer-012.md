# Confirming Send Outcome Before Completing a Use Case

In a use case that emits a Kafka event, calling `KafkaTemplate.send()` does not mean the event has been sent successfully. The producer sends data asynchronously: the call typically returns an object representing a future result right away, while the Kafka client continues transmitting the record and awaiting a broker response. If the use case marks itself complete or returns success before the send outcome is confirmed, the application can report success even though the event ultimately fails.

For a use case where emitting the event is a precondition for completion, the application must wait for a successful send outcome or keep the use case in a pending state until that outcome is determined. This ensures the business completion boundary accurately reflects what the system has guaranteed.

## 1. Distinguishing the send Call, Broker Acknowledgement, and Consumer Processing

A send through Spring Kafka passes several distinct milestones:

1. The application calls `KafkaTemplate.send()` and the Kafka client accepts the send request. The record may be buffered for later transmission.
2. The producer sends the request to the broker currently serving as leader of the target partition.
3. The broker responds per the producer's `acks` configuration. Upon receiving a successful response, the send can be considered successful under the chosen acknowledgement policy.
4. A consumer reads the record, executes business logic, and commits its consumer group offset at some later time.

These milestones carry different meanings. `send()` returning does not mean the broker acknowledged. Broker acknowledgement likewise does not mean a consumer has read or finished processing. If the use case only requires Kafka to durably accept the event, it can complete after receiving a successful send result under appropriate configuration. If it requires another system to have processed the event, producer acknowledgement is not enough; an application-layer confirmation mechanism—such as request/reply, workflow state, or a response event—is needed.

## 2. `KafkaTemplate.send()` Returns an Asynchronous Result

In Spring Kafka 3.x, `KafkaTemplate.send()` methods return `CompletableFuture<SendResult<K, V>>`. The future completes when the Kafka producer receives either success or an error for the send. On success, `SendResult` provides the sent record and broker metadata, such as topic, partition, offset, and timestamp.

Example:

```java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders", orderId, event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Could not publish order event: orderId={}", orderId, exception);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.info("Published order event: topic={}, partition={}, offset={}",
            metadata.topic(), metadata.partition(), metadata.offset());
});
```

`whenComplete()` is useful for observing outcomes, logging, or updating metrics. However, if the calling method merely registers a callback and returns immediately, the use case can still finish before the callback runs. A callback by itself does not keep a use case waiting. For the send outcome to decide the use case outcome, either await the future or compose the future into the asynchronous result returned by the use case.

Before Spring Kafka 3.0, the send API used `ListenableFuture` and corresponding callbacks. When working on older projects, use the exact future type of the installed Spring Kafka version; do not copy `CompletableFuture` examples directly onto the older API.

## 3. Waiting for Send Outcome Before Returning Success

If the use case contract requires a synchronous reply, wait on the future via `get()` with an explicit timeout. The example below only returns `OrderAccepted` after the broker has acknowledged the send under producer configuration:

```java
@Service
public class CreateOrderUseCase {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CreateOrderUseCase(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public OrderAccepted execute(CreateOrder command) {
        Order order = createOrder(command);
        OrderCreated event = OrderCreated.from(order);

        try {
            SendResult<String, OrderCreated> result = kafkaTemplate
                    .send("orders", order.getId(), event)
                    .get(5, TimeUnit.SECONDS);

            RecordMetadata metadata = result.getRecordMetadata();
            return new OrderAccepted(
                    order.getId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset());
        }
        catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new EventPublicationInterruptedException(
                    order.getId(), exception);
        }
        catch (ExecutionException | TimeoutException exception) {
            throw new EventPublicationFailedException(
                    order.getId(), exception);
        }
    }
}
```

Types like `Order`, `OrderCreated`, `OrderAccepted`, and the exceptions in the snippet are illustrative domain types. The key point is that the use case only constructs a success result after `get()` returns `SendResult`. If sending fails or no outcome arrives within the wait limit, the use case follows its defined failure path.

`get()` blocks the calling thread while waiting. This approach is straightforward and fits when a business contract requires a synchronous outcome, yet should not be used casually on bounded thread pools such as high-traffic web server request threads. The wait duration should align with `delivery.timeout.ms`, network latency, and the request's time budget. If the use case timeout is shorter than how long the producer is permitted to keep trying, the application can stop waiting while the Kafka client is still finishing the send.

A `TimeoutException` from `future.get(timeout, unit)` only indicates the caller timed out waiting. It does not prove the broker definitely did not write the record. The result may be delayed by slow responses even though the broker persisted the record. Therefore, do not automatically resend the same business operation with a new event ID right when the caller times out; doing so can create duplicate events. Use a stable event ID and consumer idempotency, or a lookup/send-status mechanism able to handle indeterminate outcomes.

## 4. Composing the Future into an Asynchronous Use Case

If the application layer supports asynchrony, the use case can return a `CompletableFuture` and complete it only after sending succeeds. This avoids holding a thread blocked while the broker processes:

```java
public CompletableFuture<OrderAccepted> execute(CreateOrder command) {
    Order order = createOrder(command);
    OrderCreated event = OrderCreated.from(order);

    return kafkaTemplate.send("orders", order.getId(), event)
            .thenApply(result -> {
                RecordMetadata metadata = result.getRecordMetadata();
                return new OrderAccepted(
                        order.getId(),
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset());
            })
            .whenComplete((accepted, failure) -> {
                if (failure != null) {
                    log.error("Order event publication failed: orderId={}",
                            order.getId(), failure);
                }
            });
}
```

`thenApply()` transforms the send result into the use case result. If the send future completes exceptionally, the resulting future also completes exceptionally so the caller can handle the error. `whenComplete()` only observes the result; it does not turn failures into successes. The controller or caller must return/compose this exact future rather than discarding it and returning HTTP success immediately.

For example, an endpoint can return `CompletionStage<ResponseEntity<OrderAccepted>>` and map the result once the future completes. If the API contract allows accepting the request upfront and processing in the background, the endpoint can return `202 Accepted` with an operation ID; in that case, operation status must explicitly reflect `PENDING`, `SUCCEEDED`, or `FAILED`. A `PENDING` state must never be presented as though Kafka had already acknowledged the event.

## 5. Configuring Acknowledgements for Appropriate Guarantees

Waiting on the future is necessary, though the strength of a success guarantee still depends on producer and broker configuration. For critical events, a common setup uses `acks=all` together with producer idempotence:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        max.in.flight.requests.per.connection: 5
```

Timeout values are examples; adjust them to the environment and response times permitted by the use case. When enabling idempotence, the Kafka client requires compatible settings for acknowledgements, retries, and in-flight requests per connection. Avoid values conflicting with idempotent producer requirements. Modern Kafka clients enable idempotence by default in many configurations, though declaring it explicitly makes operational intent easier to verify.

Core meaning of `acks`:

| Value | When does the producer receive confirmation? | Key implication |
|---|---|---|
| `0` | Does not wait for broker acknowledgement. | Producer receives no broker confirmation for the send; hard to detect broker-side send errors. |
| `1` | When the partition leader writes the record to its local log and responds. | Records can be lost if the leader fails before another replica copies them. |
| `all` or `-1` | When replicas currently in the ISR confirm under the replication protocol. | Increases durability; writes may be rejected if ISR fails to meet `min.insync.replicas`. |

`acks=all` does not mean every replica configured for the partition must acknowledge. It applies to replicas currently in the ISR (in-sync replicas). The broker/topic property `min.insync.replicas` sets the minimum replicas required in the ISR for the broker to accept writes with `acks=all`. For instance, replication factor 3 with `min.insync.replicas=2` permits writes when at least two replicas remain in the ISR. If ISR count falls below threshold, the producer can receive `NotEnoughReplicas` or a related error instead of a false success.

Producer idempotence avoids creating duplicate records when the Kafka producer internally retries a send within the same producer session, using sequence numbers and producer IDs. It does not automatically deduplicate business commands re-sent by the application as two separate `send()` calls after a timeout, application restart, or new producer session. For use-case-level retries, use a stable event ID and design idempotent consumers.

## 6. Handling Send Failures and Controlled Retries

A send future can complete exceptionally for many reasons: serialization errors, invalid topic or metadata, authentication/authorization errors, unavailable brokers, timeouts, insufficient ISR replicas, or network errors. Distinguish configuration/logic errors from transient errors when deciding the next action.

The Kafka producer already has built-in retries for retriable errors. `delivery.timeout.ms` caps total time the producer tries to finish a send, including batch wait, response wait, and retries. `request.timeout.ms` caps response wait for one request; `max.block.ms` can affect how long `send()` waits for metadata or buffer space when the producer cannot accept records yet. These differ from the timeout a caller passes to `future.get()`.

When a future fails, you should:

- Log event ID, use case ID, topic, and error type for tracing; avoid logging full sensitive payloads.
- Preserve an accurate error or pending status; never catch an exception and proceed to return a success result.
- Let the Kafka producer handle retries for transient errors as configured, applying application-level retries only after understanding the prior attempt's outcome.
- Use backoff, retry limits, and a stable event ID if retrying at the use case layer.
- Route prolonged or unrecoverable failures into a recovery flow such as outbox retry, dead-letter workflow, or operational alerting.

If the caller times out while the future is still running, do not assume the send failed completely. Have a strategy for indeterminate outcomes: track the future until completion, persist operation status, or allow resending with the same business identifier and deduplication on the receiving side.

## 7. Completion Boundaries When the Use Case Also Writes to a Database

A common challenge arises when a use case both writes to a database and emits a Kafka event. These two operations span two different storage systems and do not automatically become a single atomic transaction just by sitting inside the same Java method or the same `@Transactional` method.

If you commit the database first and then send to Kafka, the database may save the order while the event send fails. If you send to Kafka first and then commit the database, consumers may receive the event even if the database transaction ultimately rolls back. Waiting for Kafka acknowledgement reveals the send outcome, yet does not eliminate the gap between the two systems.

For use cases that must ensure database state and event-emission intent are persisted together, transactional outbox is a common pattern:

```text
Use case
   |
   v
Database transaction
   |-- write business changes
   |-- write event to outbox table
   |
   v
Commit database
   |
   v
Outbox publisher reads unsent events
   |
   v
KafkaTemplate.send() and wait for result
   |
   +---- failure ----> retain state for retry
   |
   v
Broker acknowledgement succeeds
   |
   v
Mark outbox event as sent
```

In this model, the use case can complete once business changes and the outbox row commit in the same database transaction. That guarantees event-emission intent is not lost if the application stops. The publisher keeps sending until receiving Kafka confirmation, then marks the outbox row sent. If the publisher stops after Kafka received the record yet before marking the outbox, it may resend the record. Therefore, consumers still need idempotency based on event ID.

Spring Kafka supports Kafka transactions and can synchronize a transaction manager with another transaction manager via transaction synchronization. That coordination has its own commit ordering and limitations; it does not turn a database and Kafka into an atomic distributed transaction by default. When using Kafka transactions, distinguish when a send future completes from when the Kafka transaction commits successfully. A record in an uncommitted transaction may not be visible to consumers using `isolation.level=read_committed`. With transactions, the use case should only report success once the transaction boundary finishes successfully.

## 8. Recording Send Evidence for Operations and Support

When the broker confirms success, `SendResult` provides metadata useful for linking application logs with Kafka logs:

```java
SendResult<String, OrderCreated> result = future.get();
RecordMetadata metadata = result.getRecordMetadata();

log.info(
        "Kafka publish confirmed: eventId={}, topic={}, partition={}, offset={}",
        event.eventId(),
        metadata.topic(),
        metadata.partition(),
        metadata.offset());
```

Monitor send success/failure counts, retry rates, send latency, timeouts, serialization errors, buffer wait times, and pending outbox event counts. When investigating a use case, event ID and operation ID help reconcile application logs, Kafka records, and consumer processing outcomes.

Do not treat a success callback log as proof that the consumer finished. Topic/partition/offset metadata only confirms where the record was written under the producer's acknowledgement policy. If business logic requires knowing the consumer finished processing, design an application-layer confirmation, such as a response event carrying the same correlation ID or a workflow status updated by the consumer.

## 9. Principles for Applying in Use Cases

- Clearly define the completion condition: whether the broker confirmed receipt of the record, or the consumer finished business processing.
- Never treat calling `KafkaTemplate.send()` or registering a callback as proof of a successful send.
- For synchronous use cases, wait on the future with a timeout and translate send failures into use case failures; preserve interrupt status when catching `InterruptedException`.
- For asynchronous use cases, return or compose the future so the caller receives the final outcome only once sending resolves.
- Choose `acks`, idempotence, replication factor, and `min.insync.replicas` to match durability needs; configure timeouts to fit the time budget.
- Distinguish caller timeouts from indeterminate final send outcomes; use a stable event ID for safe retries.
- When both writing to a database and publishing to Kafka, consider transactional outbox to persist business changes and publish intent in the same database transaction.
- Log successful send metadata and monitor errors, retries, and latency; do not infer from producer acknowledgement that the consumer finished processing.

A use case should only be considered complete at the exact boundary promised by its business contract. If that promise includes Kafka accepting the event, wait for send confirmation per producer configuration. If that promise includes processing by a receiving system, add application-level confirmation. Keeping these two levels distinct ensures the outcome returned to callers accurately reflects the real state of the workflow.
