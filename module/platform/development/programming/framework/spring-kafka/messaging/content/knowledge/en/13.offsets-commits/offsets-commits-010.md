# Re-Reading Records After Error Handling

A Kafka consumer reads records by per-partition offset. When a listener fails to process a record, the application must decide whether to retry that record, route it to a dead-letter topic (DLT), or actively re-read a log segment to recover data. This mechanism is directly tied to the current read position, committed offsets, and how Spring Kafka handles errors.

Understanding offsets accurately helps avoid two opposing risks: committing too early causes failed records to be skipped, while committing too late can cause already succeeded records to be re-read. In most messaging applications, consumers should be designed to tolerate duplicate processing, then select retry or replay based on exception type and business requirements.

## 1. Why Can Kafka Re-Read a Record?

Kafka does not delete a record once a consumer finishes reading it. A consumer group saves its reading progress via committed offsets for each topic-partition. When a consumer starts or is assigned partitions, it resumes from a read position determined by the committed offset and the `auto.offset.reset` policy.

Suppose partition `orders.events-0` contains the records:

```text
offset:     40       41       42       43       44
record:  OrderA   OrderB   OrderC   OrderD   OrderE
```

The consumer successfully processes records at offsets `40` and `41`, but record `42` triggers an error. If the group has committed `42` as the next position, the consumer can go back and read the record at offset `42` after a retry, restart, or partition reassignment.

The committed offset typically represents the **next position to read**, not the last processed offset:

| Processed Record | Record Offset | Corresponding Commit Offset |
|---|---:|---:|
| `OrderA` | 40 | 41 if processed only up to this record |
| `OrderB` | 41 | 42 if processed up to this record |
| `OrderC` | 42 | 43 if processed up to this record |

Therefore, `ConsumerRecord.offset()` equal to `42` and a committed offset equal to `42` mean different things: the current record has offset 42, whereas commit position 42 tells the consumer to resume from offset 42.

## 2. Two Risks When Committing Offsets

Commit timing must align with when business side effects complete.

### Committing before processing finishes

If the consumer commits offset `43` before processing record offset `42` finishes, and then the application fails or the process stops, the next read may start from `43`. Record `42` has been skipped even though business logic did not complete.

```text
Read record 42
      |
      v
Commit offset 43
      |
      v
Database write fails
      |
      v
Restart -> read from offset 43

Record 42 was not successfully processed yet was skipped.
```

### Finishing processing without committing

If the listener writes to the database successfully but the process stops before committing the offset, Kafka still considers that record unacknowledged. When the consumer re-reads, the same side effect may execute again.

```text
Read record 42
      |
      v
Database write succeeds
      |
      v
Process stops before commit
      |
      v
Restart -> re-read record 42

Side effect may execute twice.
```

That is why consumers are usually designed for at-least-once: prioritizing not skipping records, accepting possible redelivery, and making processing idempotent.

## 3. How Does Spring Kafka Handle Failed Record Listeners?

When a `@KafkaListener` method throws an exception, the listener container forwards the error to the configured `CommonErrorHandler`. For record listeners, `DefaultErrorHandler` is a common choice for retrying and recovering failed records.

Under its default seek mechanism, when handling an error, the error handler moves the consumer position back to the failed record and any subsequent records in the poll result that need to be reprocessed. Records processed prior to the failed record can be committed according to the acknowledgment mode. On the next consumer poll, the failed record is re-read instead of skipped.

Example listener allowing exceptions to propagate to the container:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void consume(ConsumerRecord<String, String> record) {
        // If processing fails, throw an exception so the container/error handler decides on retry.
        process(record.key(), record.value());
    }

    private void process(String orderId, String payload) {
        // Execute business logic; throw an exception if retry or recovery is needed.
    }
}
```

If the listener catches an exception and merely logs it without rethrowing, the container considers the listener invocation completed normally and may commit the offset. Catch errors only when the application has handled or routed the error via an intentional workflow.

## 4. In-Place Retries with DefaultErrorHandler

`DefaultErrorHandler` supports retries with a `BackOff`. The following example waits one second between attempts and performs up to two retries after the initial attempt. If it still fails, `DeadLetterPublishingRecoverer` sends the record to a DLT.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);
        var handler = new DefaultErrorHandler(recoverer, backOff);

        // Invalid data errors are not retried because retrying cannot fix the payload.
        handler.addNotRetryableExceptions(IllegalArgumentException.class);
        return handler;
    }
}
```

To apply the error handler to the listener container factory, configure the factory as follows:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Configuration
class KafkaListenerFactoryConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<Object, Object> kafkaListenerContainerFactory(
            ConsumerFactory<Object, Object> consumerFactory,
            DefaultErrorHandler kafkaErrorHandler) {

        var factory = new ConcurrentKafkaListenerContainerFactory<Object, Object>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);
        return factory;
    }
}
```

In Spring Boot, make sure the factory used by the listener actually receives the `CommonErrorHandler`. If the application declares custom factories, attach the handler to each relevant factory; creating an error handler bean alone while the listener uses a different factory will not produce the expected retry behavior.

`FixedBackOff(interval, maxAttempts)` uses `maxAttempts` as the number of retries after the first attempt. In the example above, a record can be processed initially and retried up to two times before recovery. You can use `ExponentialBackOff` or another backoff to increase wait time between attempts.

### Choosing retryable exceptions

Not every error should be retried:

| Error Type | Commonly Suitable Handling |
|---|---|
| Short database or external service timeout | Bounded retries with backoff |
| Transient network error | Retry while capping total time and attempts |
| Malformed schema payload or invalid business data | Do not retry, or retry only after data correction; usually route to DLT |
| Missing configuration or permissions | Stop/alert and fix configuration; infinite retries do not resolve the root cause |
| Errors from an overloaded downstream dependency | Longer backoff, capped retries, and monitor pressure on the dependency |

If an exception is marked non-retryable, the error handler skips normal retries and goes straight to recovery. Carefully curate the exception list because misclassifying exceptions can send records to the DLT prematurely or cause futile retries.

## 5. Re-Reading After Exhausting Retries: Dead-Letter Topics

When in-place retries reach the allowed limit, the application can send the failed record to a dead-letter topic so the main stream continues. `DeadLetterPublishingRecoverer` typically constructs the target topic by appending `-dlt` to the source topic name and keeping the same partition.

Example:

```text
orders.events, partition 2, offset 42
             |
             | processing failed, retries exhausted
             v
orders.events-dlt, partition 2
```

When using default routing and the source has partition 2, the DLT needs partition 2. In general, a DLT should have at least as many partitions as the source topic unless the application configures a custom destination resolver.

The DLT holds records for investigation or later reprocessing. Spring Kafka typically adds headers describing the source topic, partition, offset, and the exception that occurred. Keep serializer/deserializer settings compatible with the key/value types sent by the recoverer; if a payload was already deserialized into an object, the DLT producer must be able to serialize that object.

When the recoverer successfully publishes to the DLT, the container can acknowledge the source record as handled per the acknowledgment mode and error handler configuration. By default, `DefaultErrorHandler` has `ackAfterHandle` enabled so the container commits after the handler finishes without throwing an exception. If publishing to the DLT fails and throws an exception, the record must not be considered recovered; let error handling continue retrying or report the error per configuration.

If using `AckMode.MANUAL_IMMEDIATE` and wanting the error handler to commit the offset of a recovered record, you can configure `setCommitRecovered(true)`. This property requires a compatible acknowledgment mode; do not enable it arbitrarily when the container uses a different mode.

## 6. How Do In-Place Retries and Retry Topics Differ?

In-place retries (blocking retries) keep processing on the current consumer thread. The error handler waits for the backoff and then seeks to re-read the failed record. During that time, subsequent records on the same thread may be blocked by the failing record.

Spring Kafka also supports non-blocking retries via `@RetryableTopic`. This mechanism forwards failed records to delayed retry topics, allowing the consumer to keep reading subsequent records on the main topic. When retry time arrives, the record is read from the retry topic; if retries are exhausted, it is routed to the DLT.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
class PaymentListener {

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(delay = 1_000, multiplier = 2.0),
            dltTopicSuffix = "-dlt"
    )
    @KafkaListener(topics = "payments.events", groupId = "payment-projection")
    public void consume(String payload) {
        process(payload);
    }

    private void process(String payload) {
        // Process payment; throw an exception if business logic fails.
    }
}
```

In the example, `attempts` denotes the total number of attempts per annotation semantics, including the initial attempt. Spring Kafka creates the needed retry topics according to the backoff configuration and forwards records to the DLT when attempts are exhausted. Specific topic setup, naming, and behavior can vary by Spring Kafka version.

| Criterion | In-Place Retry | Retry Topic |
|---|---|---|
| Retry mechanism | Seek and re-read in the current consumer | Publish to a retry topic and re-read later |
| Consumer blocked by failing record | May be blocked during backoff/retry | Main topic can continue processing subsequent records |
| Business ordering | Preserves partition flow via seek | Can alter order because later records are processed before retrying records |
| Infrastructure | Mainly error handler configuration | Requires retry topics and suitable DLT |
| Suitable scenario | Short-lived errors, strict partition ordering required | Errors needing long waits where reordering is acceptable |

`DefaultErrorHandler` with seek and `@RetryableTopic` are two distinct retry mechanisms; pick the appropriate mechanism for the listener rather than assuming they automatically stack as two sequential retry layers. Non-blocking retries have limitations by version and listener type; in common Spring Kafka versions, this mechanism does not support batch listeners or container transactions. Check your project's exact version documentation before adopting it. Do not pick retry topics solely because they reduce blocking if business rules require strict per-key ordering.

## 7. Re-Reading a Record Using Seek in Spring Kafka

In certain situations, an application needs to actively move a consumer back to a specific offset. Spring Kafka provides `ConsumerSeekAware` so a listener receives a seek callback on the consumer thread, for example when partitions are assigned.

```java
import java.util.Map;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.ConsumerSeekAware;
import org.springframework.kafka.listener.ConsumerSeekAware.ConsumerSeekCallback;
import org.springframework.stereotype.Component;

@Component
class ReplayOrderListener implements ConsumerSeekAware {

    private final Map<TopicPartition, Long> replayOffsets = Map.of(
            new TopicPartition("orders.events", 0), 42L
    );

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        assignments.keySet().forEach(partition -> {
            Long targetOffset = replayOffsets.get(partition);
            if (targetOffset != null) {
                callback.seek(
                        partition.topic(),
                        partition.partition(),
                        targetOffset
                );
            }
        });
    }

    @KafkaListener(topics = "orders.events", groupId = "order-replay")
    public void consume(String payload) {
        processReplay(payload);
    }

    private void processReplay(String payload) {
        // Process event in the replay flow.
    }
}
```

This example illustrates a replay offset defined by the application. In real systems, target offsets should come from configuration or controlled storage; never hard-code offsets in source code.

`seek()` changes the consumer's current read position on the partition. It does not automatically write a new committed offset to Kafka. If the consumer stops before processing and committing new progress, the next partition assignment may start from the old committed offset. Thus, seek is suited for controlling replay within a consumer session; for durable read position changes across restarts, commit new offsets or reset group offsets.

Seek only on partitions currently owned by the consumer, and execute via Spring Kafka callbacks/APIs so the operation runs on the proper consumer thread. Never call `KafkaConsumer.seek()` directly from another business thread.

## 8. Resetting Committed Offsets to Replay a Log Segment

When you need to rerun data for an entire consumer group, you can use `kafka-consumer-groups.sh` to reset committed offsets. Because this modifies the group's saved reading progress, perform it carefully according to plan.

Example checking the group's current offsets:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --describe
```

To preview setting topic partition 0 to offset 42:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders.events:0 \
  --reset-offsets \
  --to-offset 42 \
  --dry-run
```

After verifying the correct group, topic, partition, and offset, execute:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders.events:0 \
  --reset-offsets \
  --to-offset 42 \
  --execute
```

The consumer group must have no active consumers when resetting offsets with administrative tools. Stop instances belonging to the group first, re-verify with `--describe`, run `--dry-run`, and only then run `--execute`. After resetting, start the consumers and confirm lag/offsets begin at the expected position.

`--to-offset 42` sets the next position to read to 42, meaning the consumer can re-read the record at offset 42. If choosing an offset deleted by retention or no longer valid, re-verify the remaining data range before resetting.

Resetting offsets affects the entire specified consumer group/partitions. If multiple applications share the same group ID, all are affected. If you want to replay for investigation without impacting production flows, consider creating a dedicated consumer group to re-read the data.

## 9. Is Replay Safe for Databases and External Services?

Replay causes records to be reprocessed. Kafka manages only logs and offsets; it does not automatically undo side effects written to a database or sent to an HTTP service. Therefore, business operations must be designed to be idempotent.

Common approaches:

- Each event carries a unique `eventId`; the database stores processed event IDs with a unique constraint.
- Use upserts or versioned status updates so repeated processing does not create duplicate rows.
- With an inbox pattern, store the event ID and business updates in the same database transaction.
- If the consumer both updates a database and publishes a new event, consider a transactional outbox to avoid updating the database without sending the output event.
- Rate-limit replays and monitor reprocessed record volume to avoid sudden load spikes on downstream dependencies.

Kafka transactions can coordinate publishing Kafka records and committing offsets within the same Kafka transaction when properly configured. They do not automatically bring external databases or HTTP services into the same transaction. Exactly-once at the Kafka boundary does not mean external side effects automatically occur only once.

## 10. Batch Listeners and Failed Records

With a batch listener, a single poll can pass many records into one listener invocation. When only one record in a batch fails, the application needs to identify the failing record to avoid unnecessarily reprocessing the entire batch.

Spring Kafka supports `BatchListenerFailedException` to indicate the index or record that failed. `DefaultErrorHandler` can commit records preceding the failed record and seek the failed record and subsequent ones for re-reading per batch error-handling semantics.

If a batch listener does not identify the failing record, the error handler may have to retry/replay the entire batch depending on configuration and version. Ensure processing records in a batch is safe to repeat and never commits past records that have not succeeded.

## 11. Transactional Listeners and Error Handling After Rollback

If a listener container runs inside a Kafka transaction, an exception can trigger a transaction rollback. In this model, post-rollback reprocessing is typically managed by `AfterRollbackProcessor`, rather than relying solely on `DefaultErrorHandler` as in non-transactional containers.

After a rollback, the consumer can seek back to the record or batch that needs reprocessing. Once retry attempts are exhausted, the after-rollback processor can recover the record—for instance, publishing to a DLT in an appropriate transaction. Check configuration for the transaction manager, producer transaction ID prefix, acknowledgments, and after-rollback processor for your Spring Kafka version.

Kafka transactions coordinate output records and offset commits within Kafka. If a listener writes to a database outside Kafka, use a dedicated coordination mechanism such as a database transaction with inbox/outbox or distributed transactions if supported by the system.

## 12. Process for Choosing How to Re-Read Records

| Scenario | Appropriate Mechanism |
|---|---|
| Short-lived, self-healing dependency error | `DefaultErrorHandler` and in-place backoff retries |
| Invalid data or non-retryable error | Recoverer and DLT |
| Error needing a long wait while keeping main flow moving | `@RetryableTopic` and retry topics if reordering is acceptable |
| Need to re-read a partition from a specific offset at runtime | `ConsumerSeekAware` or Spring Kafka-managed seek APIs |
| Need a durable replay for the whole group | Stop consumers and reset committed offsets with admin tools |
| Need to re-analyze data without affecting production | Use a separate consumer group |

Before replaying, identify the topic/partition/offset scope, check retention, stop or isolate consumers appropriately, evaluate side effects, and choose where outputs are written. After replaying, monitor consumer lag, repeated errors, DLT, and database load to confirm the stream has stabilized.

## 13. Common Confusions

1. **Assuming record offset equals commit offset.** Record offset `42` and committed offset `42` are not the same; committing `42` indicates the next position to read.
2. **Catching exceptions without rethrowing.** The container may treat the listener as succeeded and commit the offset, preventing retries for the failed record.
3. **Assuming seek changes committed offsets.** Seek only changes the current read position; to change progress durably, commit or reset offsets.
4. **Retrying every exception infinitely.** Data or configuration errors do not vanish on their own; classify retryable and non-retryable exceptions.
5. **Assuming failed DLT publishing still counts as recovered.** Acknowledge the source record only when the recoverer succeeds per configuration; DLT publishing failures must be handled.
6. **Using retry topics without considering ordering.** Later records may be processed before records waiting for retry.
7. **Resetting offsets while the consumer group is still running.** Stop consumers and run dry-run first to avoid unexpected progress changes.
8. **Assuming replay produces no duplicate side effects.** Databases, emails, or APIs may be called again; idempotency or appropriate transactions are required.
9. **Assuming Kafka transactions include databases.** Kafka transactions do not automatically cover resources outside Kafka.

Re-reading records is a key capability for recovering messaging streams after errors. With Spring Kafka, choose in-place retries, retry topics, DLT, seek, or offset resets matching the exact recovery scope needed; at the same time, understand commit timing and ensure business side effects tolerate repeated processing.
