# enable.auto.commit and commit strategies

## 1. What is offset committing used for?

A consumer reads records from a partition by offset. After finishing processing a record or a group of records, the consumer needs to record the position where reading can resume on the next run. That operation is called **committing an offset**.

The committed offset is the next position the consumer will read, not the offset of the last processed record. For example, if a consumer successfully processes the record at offset `41`, the offset to commit is normally `42`.

Kafka stores committed offsets per consumer group and partition. Therefore:

- Consumers in the same group share the group's reading progress for each partition.
- Two different groups have independent committed offsets, even when reading the same topic.
- When a consumer restarts or a partition is assigned to another consumer, the consumer can resume from the committed offset.

Offset committing is part of reliability design. Committing too early can cause unfinished records to be skipped; committing too late can cause already-processed records to be redelivered. The right strategy depends on tolerance for duplicate processing, throughput, and the cost of each commit.

## 2. enable.auto.commit of the Kafka Consumer

In the Apache Kafka Java Consumer, the `enable.auto.commit` property controls whether the Kafka client automatically commits offsets periodically. The default value in a plain Kafka consumer is `true`; the interval is controlled by `auto.commit.interval.ms` (typically 5 seconds by default).

When `enable.auto.commit=true`, the client commits reading progress automatically in the background. The application does not need to call `commitSync()` or `commitAsync()` for each poll. However, the Kafka client does not know whether the application's business processing has finished. Commits are decided based on what the consumer has polled, not on confirmation from the business service.

This can cause lost processing if the application is still processing a batch whose offsets have already been committed. For example:

1. `poll()` returns records from offset `100` to `109`.
2. The application has only finished processing up to offset `103`.
3. Auto-commit saves progress up to the next offset of the polled batch.
4. The application stops abruptly before processing offsets `104` through `109`.
5. On restart, the consumer may resume past the committed offsets, leaving some unprocessed records undelivered.

Thus, auto-commit is convenient for simple applications that can tolerate risking partial processing loss, but unsuitable when commits must be tied to business completion.

### Plain Kafka Consumer configuration example

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, true);
props.put(ConsumerConfig.AUTO_COMMIT_INTERVAL_MS_CONFIG, 5_000);

KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
consumer.subscribe(List.of("orders"));
```

In this example, the consumer auto-commits periodically. The application has no signal to tell Kafka that a specific record has completed business processing. If you need exact control over commit timing, disable auto-commit and commit after processing succeeds.

## 3. Disabling auto-commit and manual committing

With `enable.auto.commit=false`, the Kafka client does not automatically save offsets periodically. The application is responsible for calling commit once processing reaches the desired boundary.

Two common APIs:

- `commitSync()`: sends the commit request and waits for the result. This is straightforward and appropriate when you need to know the commit succeeded before proceeding.
- `commitAsync()`: sends the commit request without blocking the current thread. This reduces wait time, though callbacks and ordering of commit requests must be handled carefully.

Example of synchronous commit after processing an entire batch:

```java
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders"));

    while (true) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1_000));

        for (ConsumerRecord<String, String> record : records) {
            processBusiness(record);
        }

        // Only commit when every record in the batch has been processed successfully.
        consumer.commitSync();
    }
}
```

If `processBusiness` throws an error mid-batch, the `commitSync()` call at the end of the loop does not run. When the consumer restarts, the batch may be redelivered from the previous committed offset. Earlier records in the batch may have already been processed before the error occurred, so the handler must be idempotent to avoid duplicate side effects.

Note: `commitSync()` does not inherently know which records in the batch succeeded. It commits the current position that the consumer has read. If the application wants to commit after each record while polling multiple records, it must track the next processed offset per `TopicPartition` and pass a `TopicPartition` → `OffsetAndMetadata` map to the commit API. Never commit the current poll position if trailing records remain unprocessed.

## 4. How does Spring Kafka manage commits?

When using `@KafkaListener`, applications normally do not call `KafkaConsumer.commitSync()` or `commitAsync()` directly. Spring Kafka's listener container manages the consumer, the `poll()` loop, listener invocation, and offset commits.

Since Spring Kafka 2.3, the framework automatically sets `enable.auto.commit=false` if the application has not configured this property. This allows the listener container to control commit timing according to `AckMode`. If `enable.auto.commit=true` is explicitly enabled, the Kafka client auto-commits periodically and the application loses the container's AckMode commit control.

With Spring Kafka, keep `enable.auto.commit=false` and choose `spring.kafka.listener.ack-mode` according to processing requirements. The default value for the listener container is `BATCH`.

### Recommended configuration

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    listener:
      ack-mode: record
```

In Spring Boot, `enable-auto-commit` is the kebab-case property mapping to the Kafka client property `enable.auto.commit`. `ack-mode` configures how the listener container commits offsets. The two properties serve different roles: one disables the Kafka client's auto-commit mechanism; the other selects the commit strategy managed by the container.

## 5. AckMode modes in Spring Kafka

`ContainerProperties.AckMode` determines when the listener container commits offsets. Commonly used modes:

| AckMode | Commit timing | Suitable use case |
|---|---|---|
| `RECORD` | After the listener successfully processes each record | Need per-record commit granularity, reducing how many records may be replayed on failure |
| `BATCH` | After all records in a poll batch are successfully processed | Want a balance between throughput and safety; this is a common default |
| `TIME` | Commits pending offsets once the configured duration has elapsed since the last commit | Want to throttle commit frequency by time |
| `COUNT` | Commits pending offsets once the configured number of records has been processed since the last commit | Want to commit by record count threshold |
| `COUNT_TIME` | Commits pending offsets when either the time or record count threshold is reached | Combine time and count thresholds |
| `MANUAL` | Listener calls `acknowledge()`; offsets are processed in batch mode after the poll's records complete | Application wants explicit acknowledgment while still batching commits |
| `MANUAL_IMMEDIATE` | Listener calls `acknowledge()` and the container commits immediately if the call runs on the consumer thread | Need immediate commit after a specific processing condition |

With `TIME`, `COUNT`, and `COUNT_TIME`, the container tracks successfully processed offsets and commits pending ones when the respective threshold is reached. These thresholds do not permit committing past unprocessed records. With `MANUAL_IMMEDIATE`, call `acknowledge()` on the consumer thread for predictable immediate commit behavior. Mixing acknowledgments across consumer threads and other threads can alter commit timing.

### RECORD and BATCH

With `RECORD`, the container commits after each successful listener completion for a record. If processing offset `20` succeeds and offset `21` fails, progress can be saved up to `21`; the failed record is handled according to error handling and its offset.

With `BATCH`, the container waits until all records in the poll are processed successfully before committing. If a record in the batch fails and is not recovered, the batch commit may be delayed; earlier records in the same batch may be redelivered. This generally improves commit efficiency at the cost of a potentially larger replay scope.

### MANUAL and MANUAL_IMMEDIATE

When choosing a manual mode, the listener method accepts an additional `Acknowledgment` parameter. The application calls `acknowledge()` once business conditions are met.

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual
```

```java
@Component
public class OrderListener {
    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(topics = "orders", groupId = "order-service")
    public void onOrder(String payload, Acknowledgment acknowledgment) {
        orderService.process(payload); // Throw an error if business logic did not complete.
        acknowledgment.acknowledge();  // Only acknowledge after processing succeeds.
    }
}
```

With `MANUAL`, calling `acknowledge()` marks the offset for the container to commit in batch mode. With `MANUAL_IMMEDIATE`, the container commits immediately if called on the consumer thread. Do not call acknowledge before business operations have completed and required data has been durably persisted.

Manual acknowledgment does not automatically make the system exactly-once. If the database commits successfully but the application stops before the Kafka offset is committed, the record may be redelivered. The processing service still needs idempotency or a suitable data coordination mechanism.

## 6. Choosing a strategy by delivery semantics

Offset commits decide up to which point Kafka considers records processed by the consumer. Three common perspectives:

### At-most-once

Offsets are committed before business side effects finish. If the application stops after committing but before processing completes, the record may not be redelivered. This prioritizes avoiding duplicate processing and accepts the risk of lost processing.

### At-least-once

The application processes the record successfully first, then commits the offset. If the application stops after processing but before committing, the record will be redelivered. This avoids skipping unfinished records but requires idempotent handlers to tolerate duplicate processing.

### Exactly-once

Manual offset commits or choosing `RECORD` do not automatically produce exactly-once semantics. For Kafka consume-transform-produce flows, Kafka transactions can write output records and offsets in the same transaction; downstream consumers use `isolation.level=read_committed` to read only committed data. For side effects outside Kafka such as database writes or API calls, an outbox/inbox pattern, appropriate transactions, or idempotency is still required for coordination.

| Goal | Typical processing order | Risk to handle |
|---|---|---|
| At-most-once | Commit first, then process | Potential record loss if processing fails after commit |
| At-least-once | Process successfully, then commit | Potential duplicate processing if stopping before commit |
| Exactly-once within Kafka | Write output and offset in a Kafka transaction | Must configure transactions and isolation properly; does not automatically cover external side effects |

In most business systems, at-least-once combined with idempotent processing is easier to operate and recover. Choose exactly-once only when business requirements and data boundaries truly demand it, while clearly understanding the scope of its guarantees.

## 7. Synchronous and asynchronous commits in the listener container

When the container performs commits, Spring Kafka defaults to synchronous commits (`syncCommits=true`). Synchronous commits wait for the broker's response, letting the container know whether the commit succeeded or failed. You can switch to asynchronous commits via container properties to reduce wait time, but you must handle callbacks and the risk of commits completing out of order.

Example of Java factory configuration:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.RECORD);
    factory.getContainerProperties().setSyncCommits(true);
    return factory;
}
```

With `syncCommits=true`, the container uses `commitSync()`. When set to `false`, the container uses `commitAsync()` and can register a callback to observe results. Measure commit latency and throughput before changing this; async commits are not always faster overall if brokers or networks are overloaded.

## 8. Rebalances, restarts, and pending offset commits

When a consumer leaves the group, loses connectivity, or partitions are reassigned, Kafka performs a rebalance. Partitions may move from one consumer to another. The new consumer resumes from the group's latest committed offset.

If the application processed some records without committing before partitions were revoked, those records may be re-read by the new consumer. The listener container coordinates with the consumer lifecycle and rebalances to manage commits; applications must not assume a partition always belongs to the same instance.

Several scenarios to verify:

- **Application stops after processing, before committing:** records may be redelivered; idempotency is required.
- **Application commits before processing:** records may be skipped when processing fails.
- **Rebalance during long processing:** control processing duration, `max.poll.interval.ms`, and concurrency to avoid the consumer being treated as no longer polling in time.
- **Consumer restart during retries:** inspect the error handler, ack mode, and offsets to understand whether records will be retried in place or redelivered.

Do not process asynchronously and acknowledge immediately upon submitting tasks to an executor. If background threads have not finished while offsets are already committed, the application can lose processing if the process stops. If asynchronous processing is needed, coordinate completion, per-partition ordering, and offset commits according to actual completed progress.

## 9. Distinguishing commonly confused offset properties

| Property/API | Meaning | Does it control commit timing? |
|---|---|---|
| `enable.auto.commit` | Enables/disables Kafka client background auto-commit | Yes, when enabled the Kafka client commits periodically |
| `auto.commit.interval.ms` | Auto-commit interval when `enable.auto.commit=true` | Affects auto-commit only |
| `spring.kafka.listener.ack-mode` | Selects the commit strategy managed by Spring Kafka listener container | Yes |
| `auto.offset.reset` | Selects starting position when group has no valid committed offset | No; not a commit mechanism |
| `Acknowledgment.acknowledge()` | Tells the container the application has processed up to that offset | Yes, in manual modes |
| `commitSync()` / `commitAsync()` | Direct Kafka Consumer offset commit APIs | Yes, when the application manages the consumer directly |

In particular, `auto.offset.reset=earliest` does not mean the consumer always re-reads from the beginning. When a group already has a valid committed offset, Kafka resumes from that offset. To re-read data, intentionally change the offset or use a different group ID, while ensuring the data is still within retention.

## 10. Testing commit strategies

Tests should verify processing outcomes and offset positions across success, error, and restart scenarios. With Spring Kafka, you can use `spring-kafka-test` or the Kafka test starter matching your Spring Boot line; some scenarios require a real broker or Kafka container to simulate rebalances and restarts realistically.

Useful scenarios:

1. Send a record, verify the listener processes it successfully, and verify the offset is committed under `RECORD`.
2. Send multiple records in one poll, verify `BATCH` commits only after the batch finishes.
3. Configure `MANUAL`, verify the offset is not committed before `acknowledge()` and is committed after that call.
4. Make the listener throw an exception, verify the error handler retries or recovers per configuration, and offsets do not advance past unprocessed records.
5. Stop the application after side effects complete but before committing, restart it, and verify records can be redelivered without duplicate side effects.
6. Test a new group with `auto-offset-reset=earliest` versus a group with existing committed offsets to observe the two distinct behaviors.

Do not check only logs saying "listener received message". Verify business outcomes, the group's committed offsets, and post-restart behavior to prove the commit strategy actually works.

## 11. Practical choices for Spring Kafka applications

| Need | Recommended config/strategy | Reason |
|---|---|---|
| Consumer processes records independently and needs tight per-record commits | `enable-auto-commit=false`, `AckMode.RECORD` | Container commits after each successful listener invocation |
| Want to balance throughput and commits | `enable-auto-commit=false`, `AckMode.BATCH` | Batches commits per poll, a common default |
| Business logic needs explicit control over when to acknowledge | `enable-auto-commit=false`, `AckMode.MANUAL` | Listener acknowledges only after business conditions are satisfied |
| Need immediate commit when listener acknowledges | `enable-auto-commit=false`, `AckMode.MANUAL_IMMEDIATE` | Commits immediately when acknowledge is called on the consumer thread |
| Consume-transform-produce flow requires atomicity within Kafka | Kafka transactions and transactional listener container | Output records and offsets can be committed in the same transaction |

For business messaging applications, a sensible starting configuration is usually `enable-auto-commit=false` with `AckMode.BATCH` or `RECORD`. Choose `RECORD` when you want per-record commit boundaries; choose `BATCH` when you want batched commits and accept possible partial batch redelivery on failure. Only use manual acknowledgment when a specific business requirement demands controlling exact acknowledgment timing.

## 12. Summary

- `enable.auto.commit=true` allows the Kafka client to auto-commit periodically without waiting for the application to confirm business completion.
- Disable auto-commit to commit after successful processing; Kafka Consumer provides `commitSync()` and `commitAsync()`.
- Since version 2.3, Spring Kafka disables auto-commit automatically if not explicitly configured, letting the listener container manage commits.
- `AckMode.RECORD`, `BATCH`, `TIME`, `COUNT`, `COUNT_TIME`, `MANUAL`, and `MANUAL_IMMEDIATE` govern when the container commits.
- At-least-once generally requires idempotent processing; exactly-once requires Kafka transactions within Kafka's boundary and dedicated design for external side effects.
- Rebalances, restarts, and asynchronous processing can all cause record redelivery; test committed offsets and business outcomes.

By choosing the right commit strategy, a Spring Kafka application can control the trade-off between throughput, latency, risk of lost records, and duplicate processing. This provides the foundation for consistently configuring retries, dead-letter handling, and transactions across the entire messaging pipeline.
