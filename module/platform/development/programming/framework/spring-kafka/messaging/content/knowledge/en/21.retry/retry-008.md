# Retrying with Manual Acknowledgment

Spring Kafka allows a listener to explicitly confirm that a record has been processed successfully using an `Acknowledgment` parameter. This is known as **manual acknowledgment**. Instead of letting the container commit offsets automatically under `RECORD` or `BATCH` mode, the listener explicitly calls `acknowledge()` once work completes.

Manual acknowledgment is useful when the acknowledgment point depends on business processing outcomes, such as committing only after data is persisted or after completing a validation step. When the listener throws an exception before acknowledging, `CommonErrorHandler` can retry the record per the configured policy. However, manual ack does not create exactly-once semantics on its own: if business logic finishes but the application stops before the offset is committed, the record can still be redelivered.

## 1. What Is Manual Acknowledgment?

A Kafka consumer reads records and tracks offsets per partition. When an offset is committed, the consumer group persists the next position to read. With manual acknowledgment, the listener tells Spring Kafka that a record or batch is done by calling `Acknowledgment.acknowledge()`.

Basic flow:

```text
Kafka poll
    |
    v
@KafkaListener receives record
    |
    v
Execute business logic
    |
    +---- Failure ---------------------> Throw exception
    |                                      |
    |                                      v
    |                                CommonErrorHandler
    |                                      |
    |                                Retry / Recovery
    |
    +---- Success --------------------> acknowledge()
                                           |
                                           v
                                     Commit offset
```

The key rule is that the listener acknowledges only after all required processing steps for that attempt have completed. Acknowledging before saving data or calling a downstream service risks skipping records if a failure occurs.

## 2. Two Manual Modes: MANUAL and MANUAL_IMMEDIATE

Spring Kafka provides two `AckMode` options for manual acknowledgment:

| AckMode | Behavior of `acknowledge()` |
| --- | --- |
| `MANUAL` | Ack is queued; offsets are committed after all records from the previous poll have been processed |
| `MANUAL_IMMEDIATE` | If called on the consumer thread, the container commits immediately; if called from another thread, the ack is queued and handled on the container cycle |

`MANUAL` fits when you want the listener to decide which records succeeded while still letting the container batch acknowledgments within a poll. `MANUAL_IMMEDIATE` fits when you want an immediate commit upon calling acknowledge on the consumer thread.

Do not interpret `MANUAL_IMMEDIATE` as a synchronous commit guarantee in all cases. Behavior depends on the calling thread, container commit configuration, and broker results. If acknowledgment is invoked from another thread, the container cannot perform an immediate commit on the consumer thread managing the consumer.

## 3. Enabling Manual Acknowledgment in Spring Boot

Set `enable-auto-commit=false` and choose `ack-mode`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      ack-mode: manual
```

In Spring Kafka, auto commit is typically defaulted to `false` when the framework builds the consumer if the application omits this property. Declaring it explicitly makes clear that the container and listener manage offsets. Do not enable auto commit alongside a manual ack design because the client could commit offsets on an interval independent of listener acknowledgment.

You can use `manual_immediate` if you want immediate commit behavior on the consumer thread:

```yaml
spring:
  kafka:
    listener:
      ack-mode: manual_immediate
```

The Boot property name is `spring.kafka.listener.ack-mode`; its value binds to `ContainerProperties.AckMode`. If creating a listener container factory manually, configure it directly:

```java
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL);
```

## 4. Calling Acknowledgment in @KafkaListener

Spring Kafka can inject an `Acknowledgment` parameter into the listener method:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-service")
    public void onMessage(
            OrderCreatedEvent event,
            Acknowledgment acknowledgment) {

        orderService.process(event);

        // Acknowledge only after business logic completes.
        acknowledgment.acknowledge();
    }
}
```

With `AckMode.MANUAL`, the listener calls `acknowledge()` after `orderService.process` completes. If the service throws an exception, the acknowledge line does not run and the exception propagates to the container for the error handler to process.

If the listener catches the exception, merely logs it, and returns normally, the container has no way to know business processing failed. The listener must rethrow the exception or invoke an intentional recovery workflow; never swallow errors and acknowledge.

## 5. Acknowledgment Timing Determines Loss or Duplicate Risk

Consider the possible failure points:

| Point where application stops | Outcome with manual ack |
| --- | --- |
| Before business processing | Not acked; record can be redelivered |
| During processing before business work completes | Not acked; record can be redelivered |
| Business work completed, before `acknowledge()` | Record can be redelivered; business logic may run again |
| After calling ack, before commit succeeds | Record can be redelivered |
| After offset commit succeeds | Group resumes from the next offset |

Thus, manual ack normally provides at-least-once semantics when acknowledging only after successful processing. This lowers the risk of dropping records, yet can still produce duplicates if a failure occurs between business completion and offset commit.

Acknowledging before processing shifts the risk to at-most-once: once the offset is committed, a business failure prevents re-reading the record. Only do that when task loss is acceptable.

## 6. Retrying When the Listener Has Not Acknowledged

Manual acknowledgment pairs with `DefaultErrorHandler` to retry records when the listener throws an exception. Example configuring two retries spaced one second apart:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
public DefaultErrorHandler orderErrorHandler() {
    return new DefaultErrorHandler(
            new FixedBackOff(1_000L, 2L));
}
```

Attaching the handler to the listener container factory:

```java
factory.setCommonErrorHandler(orderErrorHandler);
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL);
```

When the listener fails before acknowledging, the error handler retries per the backoff. If a retry succeeds and the listener acknowledges, the container advances the offset. If retries are exhausted, the handler can call a recoverer to send the record to a DLT.

With `DefaultErrorHandler`, after successful recovery, `ackAfterHandle` defaults to allowing the container to commit the offset once the handler returns normally. Understand this when using manual ack: successful recovery is also an accepted outcome for the group to advance. If you need finer control over committing recovered records, review `ackAfterHandle`, `commitRecovered`, and the corresponding `AckMode` in your Spring Kafka version's documentation.

## 7. Routing Failed Records to a Dead Letter Topic

When a record remains unprocessable after the configured retries, `DeadLetterPublishingRecoverer` can route the record to a DLT:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
public DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()));

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}
```

This example routes `orders.created` to `orders.created.DLT` while keeping the partition index. The DLT topic must exist or be provisioned appropriately. When preserving source partitions, the DLT must have enough matching partitions.

If DLT publishing fails, the recoverer can throw an exception so the original record is not mistakenly treated as recovered. Monitor DLT publish failures as well, and ensure the DLT producer has serializers compatible with both normal payloads and raw bytes from deserialization errors.

A DLT stores records for investigation or replay; moving a record to a DLT does not mean the business error is fixed. Maintain a clear process for inspecting, fixing data, and replaying.

## 8. MANUAL vs. MANUAL_IMMEDIATE in Record Listeners

Example using `MANUAL`:

```java
@KafkaListener(topics = "payments.authorized", groupId = "payment-ledger")
public void onPayment(
        PaymentAuthorized event,
        Acknowledgment acknowledgment) {

    ledgerService.record(event);
    acknowledgment.acknowledge();
}
```

The ack is recorded and committed by the container per the manual mode cycle after the poll's records are processed. If a poll returns multiple records, do not assume every `acknowledge()` call immediately writes an individual offset commit.

Example using `MANUAL_IMMEDIATE`:

```java
@KafkaListener(topics = "payments.authorized", groupId = "payment-ledger")
public void onPayment(
        PaymentAuthorized event,
        Acknowledgment acknowledgment) {

    ledgerService.record(event);
    acknowledgment.acknowledge(); // Called on the consumer thread.
}
```

With `MANUAL_IMMEDIATE`, calling it on the consumer thread tells the container to commit immediately. Therefore, call it only after all required steps have finished. Never acknowledge at the top of the listener before performing database updates or API calls.

Avoid mixing ack calls from the consumer thread and other threads in the same listener in ways that make commit ordering unpredictable. Pick one consistent processing and acknowledgment model.

## 9. Manual Acknowledgment with Asynchronous Processing

Some applications have the listener hand off work to an executor and acknowledge once the background task completes. If you do that, the listener can return before business work truly finishes; the container must be configured to handle out-of-order acknowledgments.

Spring Kafka has supported `asyncAcks` since version 2.8. When enabled, the container allows records from a poll to be acknowledged in any order. The container tracks missing offsets and pauses the consumer until all acknowledgments for the poll arrive. Only then can commits advance across the gap.

Configuration example:

```java
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL);
factory.getContainerProperties()
        .setAsyncAcks(true);
```

Use this pattern with caution:

- The consumer may be paused while waiting for missing acknowledgments.
- A failing or never-completing background task can block commit progress for that poll.
- If the application stops before all acks arrive, uncommitted records may be redelivered even if earlier background tasks already produced side effects.
- Do not hold onto `Acknowledgment` indefinitely or use it after the container has stopped/rebalanced.
- Handle exceptions inside the executor with clear error reporting/retry logic; never let a future fail silently and leave offsets stalled unmonitored.

`asyncAcks` does not make Kafka consumers thread-safe, nor does it guarantee business completion order. It only helps the container manage out-of-order acknowledgments for records belonging to a poll.

## 10. Manual Acknowledgment with Batch Listeners

With a batch listener, a single invocation receives multiple records. The listener typically acknowledges after the entire batch succeeds:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;

@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-service",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onMessages(
        List<ConsumerRecord<String, OrderCreatedEvent>> records,
        Acknowledgment acknowledgment) {

    for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
        orderService.process(record.value());
    }

    acknowledgment.acknowledge();
}
```

The factory must be configured for batch mode via `setBatchListener(true)` and `AckMode.MANUAL`. If any record throws an exception before acknowledgment, the batch is not confirmed successful and the error handler handles the failure per policy.

With batch listeners, consider what happens if part of the batch already updated the database before a later record failed. When the batch is retried, the completed portion may run again. Use idempotency or database transactions for batch operations.

## 11. Manual Acknowledgment Does Not Replace Idempotency

Suppose the listener updates the database successfully and the application crashes before calling `acknowledge()`. Kafka will redeliver the record. If the listener updates the database again without safeguards, metrics or business state may be duplicated.

A common approach is storing `eventId` in an inbox table within the same transaction as the business update:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

```java
@Transactional
public void processOnce(OrderCreatedEvent event) {
    if (!processedEventRepository.insertIfAbsent(event.eventId())) {
        return; // Event already processed previously.
    }

    orderRepository.createProjection(event);
}
```

`insertIfAbsent` must rely on a unique constraint or an atomic insert operation. Recording the event marker and updating business state must share the same database transaction. Only after the service commits successfully does the listener acknowledge the Kafka offset.

If the application stops between the database commit and the Kafka offset commit, the subsequent redelivery sees that `eventId` already exists and applies no duplicate business effect.

## 12. Relationship with Transactions and Exactly-Once

Manual ack only controls when offsets are confirmed. It does not put database transactions and Kafka offsets into a single distributed transaction.

If a listener simply updates a database and acknowledges, a failure window remains between the two systems. Kafka transactions can combine Kafka output records and input offsets in the same transaction, yet do not automatically span external databases or HTTP side effects.

Therefore:

- Use manual ack to control offset commit timing based on processing outcomes.
- Use idempotency/inbox patterns to guard against duplicates on redelivery.
- Use outbox/inbox or suitable coordination patterns when consistency between a database and Kafka is required.
- Use container transactions / EOS V2 when atomic read-process-write across Kafka topics is needed.

Do not call manual ack exactly-once. The listener can still be invoked again after crashes, rollbacks, or commit failures.

## 13. Commit and Error Handler Considerations

Manual acknowledgment interacts with other listener container settings:

| Setting | What to check |
| --- | --- |
| `enable.auto.commit` | Set to `false` so the container manages offsets |
| `AckMode.MANUAL` | Acks are queued and committed after the poll's records are processed |
| `AckMode.MANUAL_IMMEDIATE` | Commits immediately when acked on the consumer thread |
| `DefaultErrorHandler` | Handles retries when the listener throws an exception before ack |
| `ackAfterHandle` | By default allows commits after the error handler successfully recovers |
| `commitRecovered` | Option to commit recovered record offsets; must adhere to version `AckMode` requirements |
| `asyncAcks` | Allows out-of-order acks, but can pause the consumer while waiting on gaps |
| Kafka transactions | Exceptions leaving the listener roll back the transaction; recovery must be designed for transactions |

With `DefaultErrorHandler`, `setCommitRecovered(true)` is an advanced option to commit the recovered record's offset and requires `MANUAL_IMMEDIATE` per the API contract. Do not enable this option by habit; first verify whether `ackAfterHandle` and your current `AckMode` already meet your needs.

If the listener runs inside a container transaction, exceptions must propagate out so the transaction rolls back. Post-rollback retries are normally managed by `DefaultAfterRollbackProcessor`; do not mechanically apply non-transactional `DefaultErrorHandler` setups to transactional listeners.

## 14. Testing Manual Acknowledgment and Retries

Tests should prove that offsets advance only after acknowledgment and that records are redelivered when the listener fails.

An integration test can verify:

1. Create an input topic and configure the listener with `AckMode.MANUAL`.
2. Send an event with a fixed `eventId`.
3. Fail the service on the first attempt; the listener does not call acknowledge.
4. Confirm the error handler retries and the listener is invoked again.
5. Succeed on the subsequent attempt and call acknowledge.
6. Confirm the group commits the offset and does not receive the record again.
7. Simulate the service committing to the database while the app stops before ack; confirm the record is redelivered yet idempotency prevents duplicate side effects.

Additional cases worth testing:

- Comparing `MANUAL` and `MANUAL_IMMEDIATE`.
- Listener throwing an exception before ack.
- Listener accidentally acking before business completion.
- Exhausting retries and recovering the record to a DLT.
- `asyncAcks` receiving acknowledgments out of poll order.
- Batch listener processing part of a batch before failing.
- Rebalance or shutdown while async tasks have not yet acknowledged.

Use Embedded Kafka or a test broker with `CountDownLatch`, `BlockingQueue`, or Awaitility to await listener invocations and offset commits with timeouts. Never rely on a short `Thread.sleep` to assume a commit has finished.

## 15. Common Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Record re-read even though listener ran | Listener did not ack or commit failed | Check where ack is called and inspect commit logs |
| Record lost after listener failure | Ack called before business work completed | Ack only after business operation succeeds |
| Listener does not retry | Exception caught and not rethrown | Rethrow exception or configure explicit recovery |
| Commit does not happen immediately | Using `MANUAL`, waiting for container to finish the poll | Understand the difference from `MANUAL_IMMEDIATE` |
| Ack from background thread has no effect as expected | `asyncAcks` not enabled or ack arrived after container state changed | Configure async acks intentionally and manage task lifecycles |
| Offsets stuck | A record from the poll was never acknowledged | Monitor ack gaps, timeouts, and background task failures |
| Duplicate database updates | DB commit succeeded before Kafka offset commit | Use event IDs, unique constraints, and the inbox pattern |
| Record enters DLT yet offset loops | Recovery/commit policy mismatch | Check `ackAfterHandle`, `commitRecovered`, and `AckMode` |
| Auto commit advances offsets unexpectedly | `enable.auto.commit=true` | Disable auto commit and let the container manage offsets |

## 16. Conclusion

Manual acknowledgment lets a listener confirm records explicitly once business processing completes. `AckMode.MANUAL` queues acknowledgments and commits after the poll's records finish processing; `MANUAL_IMMEDIATE` commits immediately when acknowledged on the consumer thread. When a listener throws an exception before acknowledging, `CommonErrorHandler` can retry or recover the record.

Acknowledge at the end of a successful processing path, set `enable.auto.commit=false`, understand how `AckMode` interacts with the error handler, and make business logic idempotent to withstand redeliveries. For asynchronous processing, enable `asyncAcks` only once ack gaps, pausing, and task lifecycles are properly managed. Manual ack controls offset commits; end-to-end reliability still depends on retries, recovery, idempotency, and system transaction boundaries.

## References

- [Spring for Apache Kafka — Message Listener Containers: Committing Offsets](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Acknowledgment API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/Acknowledgment.html)
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
