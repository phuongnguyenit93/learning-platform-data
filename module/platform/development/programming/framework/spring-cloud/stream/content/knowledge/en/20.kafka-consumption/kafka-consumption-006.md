# Manual Acknowledgment with `KafkaHeaders.ACKNOWLEDGMENT`

The Spring Cloud Stream Kafka Binder normally lets the listener container manage offset commits according to Spring for Apache Kafka's acknowledgment configuration. When you need exact control over when a record is considered processed, the consumer can use manual acknowledgment mode (`MANUAL` or `MANUAL_IMMEDIATE`) and retrieve the `Acknowledgment` object from the `KafkaHeaders.ACKNOWLEDGMENT` header.

Manual acknowledgment is useful when business logic must complete a database transaction, persist processing state, or confirm a side effect before Kafka records consumer group progress. However, calling `acknowledge()` only controls offset committing according to Spring Kafka semantics. It does not create an atomic transaction between Kafka and a database, does not turn Kafka into a queue with a requeue command, and does not automatically guarantee exactly-once processing.

## 1. Why Is Manual Acknowledgment Needed?

Kafka stores records in partitioned logs. A consumer group tracks read progress using committed offsets per partition. When a listener processes a record, the listener container needs to know when it may commit the offset so that after a restart the group resumes from the appropriate position.

With the container's automatic acknowledgment configuration, the framework decides commit timing based on `AckMode`, such as after each record (`RECORD`) or after processing all records returned from a single `poll()` (`BATCH`). With manual acknowledgment, the application calls `Acknowledgment.acknowledge()` after reaching a defined completion point.

For example, a consumer handling `OrderCreated` and updating inventory:

1. Kafka delivers the record to the consumer.
2. Spring Cloud Stream converts the record into a message and invokes the consumer function.
3. The application updates inventory inside a database transaction.
4. The transaction commits successfully.
5. The consumer calls `acknowledge()` to signal that the record can count toward processed progress.

If the offset is committed before step 4, the application may lose the chance to re-read the record when the database was not updated. If the database commits and the application stops before step 5, Kafka may redeliver the record; the consumer needs idempotency so the inventory adjustment is not applied a second time.

## 2. Enabling Manual Acknowledgment on the Right Binding

In the Kafka Binder, configure `ackMode` under the consumer-specific section of the binding. Example:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              ack-mode: MANUAL
```

`processOrder-in-0` is the input binding for the `processOrder` bean. `ack-mode` accepts values from Spring Kafka's `AckMode` enum. The two modes used for manual acknowledgment are:

- `MANUAL`: the listener explicitly calls `acknowledge()`. Offsets are queued to be committed with `BATCH`-like semantics, meaning after the records from the preceding poll are processed by the listener.
- `MANUAL_IMMEDIATE`: commits immediately when `acknowledge()` is called on the consumer thread. If called from another thread, the acknowledgment is queued and committed according to container mechanics; do not assume an immediate commit in all cases.

Without manual mode configured, the container typically uses `BATCH` per Spring Kafka defaults. When manual mode is enabled, the Kafka Binder adds the `kafka_acknowledgment` header to the message; the standard constant in code is `KafkaHeaders.ACKNOWLEDGMENT`.

In older Kafka Binder versions, `autoCommitOffset: false` also enabled manual acknowledgment and provided this header. The `autoCommitOffset` property has been deprecated since Kafka Binder 3.1 in favor of `ackMode`. For new applications, prefer configuring `ack-mode`; when maintaining legacy apps, check the exact version's documentation before changing properties.

## 3. Retrieving `Acknowledgment` from Message Headers

To read Kafka-specific headers, the consumer function must accept `Message<T>` instead of only the payload `T`:

```java
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderCreated>> processOrder(InventoryService inventoryService) {
    return message -> {
        Acknowledgment acknowledgment = message.getHeaders().get(
                KafkaHeaders.ACKNOWLEDGMENT,
                Acknowledgment.class);

        if (acknowledgment == null) {
            throw new IllegalStateException(
                    "Kafka acknowledgment header is missing; check the binding ack-mode");
        }

        inventoryService.reserveOnce(message.getPayload());
        acknowledgment.acknowledge();
    };
}
```

Key points to remember:

- `KafkaHeaders.ACKNOWLEDGMENT` is the header constant provided by Spring Kafka.
- The header value has type `org.springframework.kafka.support.Acknowledgment`.
- This header is present only when the binding is configured in a corresponding manual mode.
- Use `Message<T>` to access headers; `Consumer<T>` receives only the payload and has no way to access headers through that parameter.
- `Acknowledgment` is an internal control handle, not business metadata to serialize or forward to another topic.

Do not silently ignore a missing header and return normally. Doing so can fool the application into thinking it controls commits manually while the binding is actually running under a different mode. Treat a missing header as a misconfiguration or processing error that must fail visibly.

## 4. Choosing `MANUAL` vs. `MANUAL_IMMEDIATE`

Both modes require the application to call `acknowledge()`, but commit timing differs:

| Mode | Behavior When `acknowledge()` Is Called | When to Consider |
|---|---|---|
| `MANUAL` | Marks the record as acked; container commits with batch semantics after the poll's records are processed | Want control over which records are acknowledged while accepting commits at poll boundaries |
| `MANUAL_IMMEDIATE` | Commits immediately if called on the consumer thread; otherwise the container queues the acknowledgment | Need immediate commit on the listener thread once work finishes |

`MANUAL` does not mean the offset commits immediately on the line calling `acknowledge()`. It only marks the acknowledgment; the container still applies commit rules. `MANUAL_IMMEDIATE` should also not be assumed instantaneous in every circumstance: the calling thread is a critical factor.

For straightforward synchronous processing, starting with `MANUAL` is usually easier to reason about. Choose `MANUAL_IMMEDIATE` when immediate commit semantics are required and you can guarantee invocation on the consumer thread. Do not choose it just because the mode name contains "immediate".

## 5. Placing Acknowledgment After Business Logic Completes

A separate service can manage the database transaction. When a call through the Spring proxy finishes normally, the transaction interceptor commits before returning control to the consumer:

```java
@Service
public class InventoryService {
    private final InventoryRepository inventory;
    private final ProcessedEventRepository processedEvents;

    public InventoryService(
            InventoryRepository inventory,
            ProcessedEventRepository processedEvents) {
        this.inventory = inventory;
        this.processedEvents = processedEvents;
    }

    @Transactional
    public void reserveOnce(OrderCreated event) {
        if (processedEvents.existsById(event.eventId())) {
            return;
        }

        int updated = inventory.reserveIfAvailable(
                event.productId(), event.quantity());
        if (updated != 1) {
            throw new InsufficientInventoryException(event.productId());
        }

        processedEvents.save(new ProcessedEvent(event.eventId()));
    }
}
```

The consumer invokes the service and only then acknowledges:

```java
@Bean
Consumer<Message<OrderCreated>> processOrder(InventoryService inventoryService) {
    return message -> {
        Acknowledgment acknowledgment = requireAcknowledgment(message);

        inventoryService.reserveOnce(message.getPayload());

        // Runs only after the transaction in the service has committed successfully.
        acknowledgment.acknowledge();
    };
}
```

`requireAcknowledgment` is an application helper that reads the header as in the previous example. `reserveIfAvailable` should perform a conditional database update, and the `ProcessedEvent` table needs a unique constraint on `eventId`. Checking `existsById` and inserting afterward without a unique constraint still has a race condition if two deliveries of the same event run concurrently.

Placing the transaction in a separate service lets Spring apply the proxy cleanly. Do not call a `@Transactional` method via self-invocation inside the same object and assume the transaction interceptor ran. Also do not offload work to another thread inside a transaction and assume the original thread's transaction covers that work.

## 6. What If Processing Fails?

If business processing throws an exception before `acknowledge()` is called, do not acknowledge the record as complete. Let the exception reach the binder/container error handling or classify it in the error-handling layer according to configured policy.

```java
@Bean
Consumer<Message<OrderCreated>> processOrder(InventoryService inventoryService) {
    return message -> {
        Acknowledgment acknowledgment = requireAcknowledgment(message);

        try {
            inventoryService.reserveOnce(message.getPayload());
            acknowledgment.acknowledge();
        }
        catch (TransientInventoryException ex) {
            // Do not ack; let the error handler/retry policy handle the transient failure.
            throw ex;
        }
    };
}
```

This snippet illustrates withholding ack when the transaction fails. Retries, seeks, recovery, or DLQ routing are governed by the error handler and Kafka Binder / Spring Kafka configuration. Manual ack does not create a retry policy or enable DLQ by itself.

Kafka is an offset-based log, not a queue with an operation to push a message back to the tail. When a record has not been committed, the consumer can re-read from the committed offset after a restart, seek, or error-handler recovery. Therefore, do not interpret `acknowledge()` as "delete message" or apply RabbitMQ's `REQUEUE` terminology to Kafka.

### 6.1. Retry and DLQ

Transient errors such as database timeouts can be retried with a bounded attempt count and backoff. Deterministic data errors such as malformed JSON or incompatible schemas usually need quarantine or DLQ rather than infinite retries.

The Kafka Binder supports DLQ via consumer settings such as `enable-dlq` and `dlq-name` (exact property names depend on version). When enabling DLQ, define the target topic, partitioning, publish permissions, and replay workflow. Only treat the record as finished after recovery/quarantine has executed according to the error handler's contract. Never manually ack the original message before knowing the DLQ send succeeded.

## 7. Understanding Offsets and Out-of-Order Risks

Kafka commits offsets per partition. A committed offset represents the next position the consumer group will read on recovery; it is not an independent per-record flag you can toggle in arbitrary order.

Suppose a partition has records 100, 101, and 102:

- If 100, 101, and 102 all succeed and are acked, the container can commit progress past 102 per the ack mode.
- If 100 is unfinished while 101 and 102 are acked, committing past 100 can cause 100 to be skipped on recovery.
- With concurrent processing or out-of-order acks, appropriate out-of-order acknowledgment support is required and you must understand how the container defers commits. Never assume calling `acknowledge()` from multiple worker threads preserves order automatically.

Spring Kafka offers an `asyncAcks` mechanism in supported versions to defer commits when acknowledgments arrive out of order and pause the consumer until gaps are filled. This is container- and version-specific configuration; do not enable or rely on it without verifying that the binder forwards the setting. A simpler and safer pattern for many workloads is sequential per-partition processing or preserving completion order before acking.

## 8. Never Arbitrarily Pass Acknowledgment to Another Thread

`Acknowledgment` is tied to the delivery and consumer container state. Do not serialize it, store it in a database, or retain it as a long-lived object. If you offload processing to an executor:

- The consumer may ack before the task actually completes if the callback returns and automatic behavior remains active.
- `MANUAL_IMMEDIATE` only commits immediately when invoked on the consumer thread; calling from another thread may only queue it.
- Out-of-order acks can interfere with partition commit progress.
- Process shutdown can lose in-memory queued tasks while the record remains unacknowledged.

If background processing is required, use a design with bounded concurrency and an explicit lifecycle, and check `asyncAcks`/container semantics for your specific version. For long-running work or decoupling from the consumer lifecycle, consider persisting the payload into a durable inbox/work table inside a transaction and acking once the record is durably stored. A separate worker then processes the inbox and manages business state.

## 9. Manual Acknowledgment Is Not Exactly-Once

Two critical failure windows remain:

**Database commits first, offset commits second:** the database is updated, then the process crashes before `acknowledge()`. Kafka may redeliver the record. The consumer must recognize that `eventId` was already processed and avoid repeating side effects.

**Offset commits first, database commits second:** if the application acknowledges too early and then the database rolls back or the process crashes, Kafka may not redeliver the record while business state remains incomplete. This is why you must ack after the business completion point.

For critical effects, use a stable `eventId` and an inbox/processed-event table with a unique constraint. When a producer both updates a database and emits events, use a transactional outbox to avoid dual-write issues. Manual ack helps choose offset commit timing; it does not create distributed transactions across Kafka, databases, and external services.

## 10. Testing Manual Acknowledgment

Tests must verify both callback invocation and actual consumer group progress:

| Scenario | What to Verify |
|---|---|
| `ack-mode` is `MANUAL` and header exists | Consumer reads `Acknowledgment` from `KafkaHeaders.ACKNOWLEDGMENT` |
| Do not call `acknowledge()` and stop consumer | Record can be re-read from committed offset after restart |
| Commit database then call ack | Database reflects changes and offset advances per configured semantics |
| Database rolls back before ack | Record is not committed as complete; error handler applies policy |
| Process stops after DB commit before ack | Redelivery creates no duplicate side effects thanks to idempotency |
| `MANUAL` vs. `MANUAL_IMMEDIATE` | Verify difference between poll-batch commits and immediate consumer-thread commits |
| Out-of-order ack | Verify behavior and supported configuration; unfinished records are not skipped |
| DLQ publish fails | Original message is not acknowledged as successfully quarantined |

Unit tests can mock `Acknowledgment` to verify `acknowledge()` is called only after the service succeeds. Integration tests should use real Kafka or an equivalent test environment to verify committed offsets, redelivery, retries, and DLQ. The Test Binder does not fully simulate Kafka offset commits and listener container semantics.

## 11. Observing in Production

To diagnose acknowledgments, logs and metrics should capture:

- Binding, destination, consumer group, topic, partition, and offset.
- Business `eventId` and `correlationId`.
- Timestamps for processing start, transaction commit, and acknowledgment call.
- Retry counts, error-handler failures, redeliveries, and DLQ message counts.
- Consumer lag and offset commit rate.
- Per-record processing time and in-flight record count.

Do not log full payloads if they contain sensitive data. Alert when lag grows, commits fail, retries prolong, DLQ spikes, or the duration from database commit to offset commit exceeds thresholds. These signals help distinguish a slow consumer from a consumer that completed business logic but failed to record progress.

## 12. Pre-Deployment Checklist

- [ ] Correct Kafka binding requiring manual acknowledgment.
- [ ] `ack-mode` set to `MANUAL` or `MANUAL_IMMEDIATE` according to commit goals.
- [ ] Consumer accepts `Message<T>` to access headers.
- [ ] `KafkaHeaders.ACKNOWLEDGMENT` retrieved as `Acknowledgment` and null-checked.
- [ ] Deprecated `autoCommitOffset` not used in new configs where `ack-mode` applies.
- [ ] `acknowledge()` called only after the business completion point is reached.
- [ ] Database transaction commits before ack; idempotency covers the redelivery window.
- [ ] Exceptions before ack flow through configured retry/error handler/DLQ.
- [ ] Understood `MANUAL` batch-semantics commits and `MANUAL_IMMEDIATE` thread constraints.
- [ ] No out-of-order or worker-thread acks without verified container semantics.
- [ ] Integration tests verify offsets, restarts, redelivery, and DLQ on Kafka.
- [ ] Consumer lag, commit errors, retries, processing latency, and DLQ are monitored.

`KafkaHeaders.ACKNOWLEDGMENT` gives the consumer direct control over offset commits when the Kafka Binder is configured in manual mode. `MANUAL` queues acknowledgments to commit at poll boundaries; `MANUAL_IMMEDIATE` commits immediately when called on the consumer thread. Call `acknowledge()` only after business effects are durably stored, keep consumers idempotent, and test redelivery. This approach gives the application clear control over Kafka progress while properly handling failure windows between the database and the broker.

## References

- [Spring Cloud Stream Kafka Binder — Manual Acknowledgement](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html)
- [Spring Cloud Stream Kafka Binder — Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring for Apache Kafka — Committing Offsets and AckMode](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
