# AckMode RECORD

## 1. What is AckMode?

A Kafka consumer reads records by offset. After the application processes a record, the consumer group must store a committed offset so it knows where to resume on the next read. In Spring Kafka, the listener container manages confirming this progress through `AckMode`.

`AckMode.RECORD` instructs the container to commit the offset after the listener successfully processes each individual record. When the listener method returns normally, the container considers that record finished and acknowledges its offset. If the listener throws an exception, the record is not acknowledged along the success path; the error handler decides whether to retry, recover, or route the failure according to configuration.

`RECORD` suits record listeners, where each method invocation processes a single record. This mode keeps commit progress closely aligned with individual records, reducing how many records must be re-read when a subsequent record fails.

## 2. How RECORD works within a single poll

A single `poll()` on a Kafka consumer can return multiple records. With a record listener, Spring Kafka calls the listener method sequentially for each record in the poll result. Once a single invocation completes successfully, `AckMode.RECORD` acknowledges that record's offset.

Example where the consumer receives three consecutive records from the same partition:

| Record | Offset | Listener result | Illustrative commit progress |
|---|---:|---|---:|
| A | 40 | Success | 41 |
| B | 41 | Success | 42 |
| C | 42 | Throws exception | 43 not committed via success path |

Kafka stores the next offset to read, so finishing record offset 40 results in committing offset 41. If record C fails, records A and B have already been acknowledged; reprocessing can start from offset 42 once the error is handled by the error handler.

~~~mermaid
flowchart TD
    A["Consumer poll"] --> B["Record offset 40"]
    B --> C["Listener processes A"]
    C --> D["Success"]
    D --> E["Commit offset 41"]
    E --> F["Record offset 41"]
    F --> G["Listener processes B"]
    G --> H["Success"]
    H --> I["Commit offset 42"]
    I --> J["Record offset 42"]
    J --> K["Listener processes C"]
    K --> L["Exception"]
    L --> M["Error handler: retry / recover"]
~~~

The table and diagram illustrate records from the same partition. When a poll contains records from multiple partitions, offsets are managed separately per partition; there is no single offset representing the whole topic.

## 3. Configuring AckMode.RECORD with Spring Boot

If all record listeners in an application need per-record commits, you can configure this in `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      type: single
      ack-mode: record
~~~

Meaning of the properties:

- `spring.kafka.listener.type: single` selects the listener mode that processes one record at a time.
- `spring.kafka.listener.ack-mode: record` requests committing offsets after each successful record-listener processing.
- `enable-auto-commit: false` disables scheduled auto-commit in the Kafka client so the listener container manages commit progress.
- `auto-offset-reset: earliest` applies only when the group has no valid committed offset yet; it does not overwrite already committed offsets.

Spring Kafka listener containers normally manage offset commits in place of Kafka consumer auto-commit. Keep `enable-auto-commit` at `false` so acknowledgment behavior is clearly governed by `AckMode`.

## 4. Record listener example with RECORD

A listener receives an order event and invokes synchronous business logic:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderProjectionService orderProjectionService;

    public OrderCreatedListener(
            OrderProjectionService orderProjectionService) {
        this.orderProjectionService = orderProjectionService;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-processor"
    )
    public void handle(OrderCreatedEvent event) {
        orderProjectionService.apply(event);
    }
}
~~~

When `orderProjectionService.apply(event)` finishes and `handle` returns normally, the container can commit that record's offset under `AckMode.RECORD`. If the business call throws an exception, the container passes the error to the error handler.

Because the listener signature accepts only the payload, business code does not need to depend on Kafka metadata. If you need to inspect topic, partition, offset, or key, you can accept `ConsumerRecord`:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    @KafkaListener(
        topics = "orders",
        groupId = "order-audit"
    )
    public void handle(
            ConsumerRecord<String, OrderCreatedEvent> record) {

        auditService.record(
            record.value(),
            record.topic(),
            record.partition(),
            record.offset()
        );
    }
}
~~~

`AckMode.RECORD` is configured on the listener container. There is no need to call `Acknowledgment.acknowledge()` inside the listener when using this mode.

## 5. Configuring RECORD via listener container factory

If the application has multiple listeners and only some need `RECORD`, create a separate container factory. Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            recordKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
                    DefaultErrorHandler kafkaErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);
        factory.setCommonErrorHandler(kafkaErrorHandler);

        return factory;
    }
}
~~~

Specify the factory on the listener that needs this mode:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-processor",
    containerFactory = "recordKafkaListenerContainerFactory"
)
public void handle(OrderCreatedEvent event) {
    orderProjectionService.apply(event);
}
~~~

Listeners using the default factory can still retain `BATCH` or their separately configured mode. The factory name in `containerFactory` must match the declared Spring bean name.

Do not set `AckMode.RECORD` on a batch listener. A batch listener receives an entire list of records in a single call and requires an acknowledgment mode compatible with batch processing, usually `BATCH` or manual acknowledgment.

## 6. How does RECORD differ from BATCH, TIME, and COUNT?

Spring Kafka provides several `AckMode` options to balance commit granularity, commit cost, and error handling behavior.

| AckMode | When offset is acknowledged | Typical usage |
|---|---|---|
| `RECORD` | After each record is successfully processed by the listener | Want per-record commit granularity |
| `BATCH` | After finishing processing the records from a single poll | Common default, suitable for per-poll processing |
| `TIME` | When the configured interval has elapsed and there are records to acknowledge | Want to cap commit frequency by time |
| `COUNT` | When the configured number of records to acknowledge is reached | Want to group commits by count |
| `COUNT_TIME` | When either the record count or time threshold is reached | Combines count and time thresholds |
| `MANUAL` | After the listener calls `acknowledge()`, container commits at the appropriate cycle | Application explicitly chooses when to acknowledge |
| `MANUAL_IMMEDIATE` | Commits immediately when `acknowledge()` is called on the consumer thread | Need explicit acknowledgment right at processing time |

`RECORD` and `BATCH` are the two easiest modes to compare:

- `RECORD` commits after each successful record. If a later record fails, prior records may already have been acknowledged.
- `BATCH` waits until the listener finishes processing the polled records before acknowledging the batch's progress. If the batch fails, more records may have to be re-read depending on the error handler and ack mode.

`TIME`, `COUNT`, and `COUNT_TIME` reduce commit frequency by grouping multiple records before acknowledging. This can lower commit overhead, but increases how many records may be redelivered if the consumer stops unexpectedly before the next commit.

## 7. RECORD and error handling

`AckMode.RECORD` does not itself decide how many times to retry or where to route failed records. It only determines when the container acknowledges offsets after successful listener processing. Retries and recovery are managed by the error handler.

You can configure `DefaultErrorHandler` with a fixed backoff for a failing record:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler() {
        return new DefaultErrorHandler(
            new FixedBackOff(1000L, 2L)
        );
    }
}
~~~

`FixedBackOff(1000L, 2L)` illustrates a one-second wait between retry attempts, with two additional retries after the initial attempt. In the container factory example earlier, Spring injects this `DefaultErrorHandler` bean and registers it with `factory.setCommonErrorHandler(kafkaErrorHandler)`. If using a different factory, register the corresponding error handler on that factory.

For a record at offset 42:

1. The listener receives the record and fails to process it.
2. The error handler waits according to backoff and re-invokes the listener per the retry policy.
3. If a retry succeeds, the container acknowledges that record's progress.
4. Once retries are exhausted, a recoverer can write the failed record to a dead-letter topic or perform the configured recovery action. Whether the offset is committed after recovery depends on error handler and recoverer configuration.

If there is no recoverer or recovery fails, error handling continues according to container policy. Write concrete tests to verify whether offsets are committed after recovery.

With `RECORD`, previously successful records can be committed individually. This limits how far back reads replay when a later record fails. However, if the listener already performed a side effect before throwing an exception, the record can be redelivered and the side effect repeated. Design business operations to be idempotent, such as using `eventId` with a database unique constraint.

## 8. Important limitations to keep in mind

### The listener must finish work before returning

The container determines listener success when the handler method completes normally. If the listener merely launches an asynchronous task and returns immediately, the container may commit the offset before that task finishes:

~~~java
@KafkaListener(topics = "orders", groupId = "order-processor")
public void handle(OrderCreatedEvent event) {
    executor.submit(() -> orderService.apply(event));
    // Method returns immediately; container may acknowledge the offset.
}
~~~

If the background task fails after the method returns, Kafka may already have saved the offset and will not automatically redeliver the record. With `AckMode.RECORD`, complete business work synchronously before returning, or choose an asynchronous model with explicit acknowledgment and error lifecycle management.

### Kafka offset commits and database transactions are separate

`AckMode.RECORD` does not automatically create an atomic transaction between committing a Kafka offset and writing data to a database. If the database write commits successfully but the process crashes before the offset commit, the record may be re-read. If the application commits the offset before data is durable, a subsequent failure can lose the business effect.

For workflows requiring coordination between database state and Kafka, evaluate appropriate transactions or the Inbox/Outbox pattern, while keeping processing idempotent to tolerate redelivery.

### RECORD does not mean exactly-once

Committing after every record only adjusts read progress. It does not guarantee business side effects happen strictly once. Kafka can redeliver a record if processing succeeded before commit completed, or the application may produce a side effect before encountering an error.

Distinguish clearly:

- **At-least-once:** records may be redelivered; the application must handle duplicates.
- **At-most-once:** records can be lost if committed before processing finishes.
- **Exactly-once:** requires an explicit transactional design and clear guarantee boundaries; selecting `AckMode.RECORD` alone does not provide this guarantee.

## 9. Testing AckMode.RECORD

Test both success and failure paths to verify commit timing:

| Scenario | What to verify |
|---|---|
| One record processes successfully | The partition's next offset is committed |
| Multiple records in one poll succeed | Progress is acknowledged after each record |
| A record mid-poll throws an exception | Earlier records are acknowledged; failing record goes through error handler |
| Retry succeeds | Record is acknowledged after listener completes successfully |
| Recovery fails | Offset is not unintentionally acknowledged |
| Consumer stops after side effect but before commit | Record can be redelivered and business logic tolerates duplicates |

You can use Embedded Kafka or Testcontainers to run integration tests. Send records with distinct `eventId` values, intentionally fail one record, and inspect listener invocations and committed offsets via the Kafka Admin API or `kafka-consumer-groups.sh --describe`.

Do not verify only that the listener was invoked. Verify committed offsets and business state as well to catch premature commits or duplicate processing bugs.

## 10. When should you choose AckMode.RECORD?

Choose `RECORD` when each record is an independent business unit, the listener processes synchronously, and you want progress acknowledged immediately after each successful record. This mode is especially helpful when one failing record should not force re-reading all earlier successful records from the same poll.

Consider `BATCH` when you want fewer commits and accept batch-scoped reprocessing. Choose manual acknowledgment when the application needs explicit control over acknowledgment timing, such as acknowledging only after completing a separate workflow.

Implementation checklist:

- [ ] Use a record listener, never a batch listener with `AckMode.RECORD`.
- [ ] Configure `spring.kafka.listener.ack-mode: record` or the corresponding container factory.
- [ ] Keep `enable.auto.commit: false` so the container manages offsets.
- [ ] Return normally only after business work has finished.
- [ ] Configure an error handler and appropriate retry/recovery policy.
- [ ] Design for idempotency to tolerate record redelivery.
- [ ] Monitor committed offsets, consumer lag, and listener errors.
- [ ] Test success, failure, retry, and recovery cases.

`AckMode.RECORD` enables Spring Kafka to acknowledge offsets after each successfully processed record. Understanding the relationship between when the listener returns, the error handler, and offset commits helps limit replay scope while avoiding mistaking per-record commits for end-to-end exactly-once semantics.
