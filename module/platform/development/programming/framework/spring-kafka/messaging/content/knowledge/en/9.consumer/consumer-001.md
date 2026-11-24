# KafkaConsumer and the Record Consumption Lifecycle

`KafkaConsumer` is the client used to read records from a Kafka topic. A consumer does not receive data by having the broker push individual records into the application; the application calls `poll()` to fetch available records and continues calling `poll()` to maintain reading progress. This lifecycle includes configuration, topic or partition registration, polling, record processing, offset acknowledgment, rebalance handling, and closing the consumer. Spring Kafka builds on `KafkaConsumer` and manages this loop through a listener container.

Understanding the lifecycle properly helps avoid unintended duplicate reads, losing records due to committing at the wrong time, having a consumer removed from the group due to processing taking too long, and errors caused by using `KafkaConsumer` from multiple threads. This article progresses from the basic Kafka client API to how Spring Kafka manages consumers in `@KafkaListener`.

## 1. Consumers read data using the poll model

Producers write records to a topic's partitions. Each record is assigned a monotonically increasing offset within that partition. A consumer belonging to a consumer group is assigned one or more partitions; when calling `poll()`, the consumer receives the next records from the current read position of the assigned partitions.

Basic reading lifecycle:

```text
Create KafkaConsumer and configure
          |
          v
subscribe(topic) or assign(partitions)
          |
          v
poll(timeout)
          |
          v
Receive ConsumerRecords
          |
          v
Process each ConsumerRecord
          |
          v
Commit offset according to policy
          |
          +----------> next poll()
          |
          v
close() on application shutdown
```

`poll()` returns a `ConsumerRecords<K, V>`, which may contain records from multiple partitions or be empty if no data is available within the wait duration. The consumer must call poll repeatedly even when no records are received in order to remain an active participant in the consumer group and maintain reading progress. Poll is also the point where the client handles group coordination events, including assignment changes during a rebalance.

A consumer should not be created fresh for every record. A consumer typically lives for the entire runtime of a worker or listener container, holding the necessary assignment state, read positions, and connections. Repeatedly creating and closing it increases connection and group-join overhead and can trigger frequent rebalances.

## 2. Configuring KafkaConsumer

A consumer requires at minimum bootstrap servers, a group ID (when using group management), deserializers for key/value, and an appropriate offset policy. Example using `Properties`:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-reader");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);
```

Important properties:

| Property | Meaning |
|---|---|
| `bootstrap.servers` | List of brokers for the client to discover the cluster |
| `group.id` | Consumer group identifier when using group management |
| `key.deserializer` | Converts key bytes into a Java type |
| `value.deserializer` | Converts value bytes into a Java type |
| `enable.auto.commit` | Enables/disables the client's automatic offset commit mechanism |
| `auto.offset.reset` | Policy when there is no valid offset or the offset is out of the log range |
| `max.poll.records` | Maximum number of records returned in a single poll |
| `max.poll.interval.ms` | Time limit between polls when using group management |

Deserializers must be compatible with the producer's serializers. If the producer writes JSON but the consumer uses `StringDeserializer`, the consumer receives a JSON string and the application can convert that string into an object. If using a JSON deserializer directly, type mapping and trusted packages must be configured appropriately for the Spring Kafka version; type headers from untrusted sources should not be trusted.

`group.id` identifies the group sharing partition consumption. Consumers with the same group ID coordinate so that each partition is assigned to at most one consumer in the group at a time. A consumer without a group ID can still read data by manually assigning partitions (`assign`), but it cannot commit offsets to a consumer group; if progress needs to be saved, the application must store offsets elsewhere and seek back on startup.

## 3. Subscribing to topics with subscribe or assigning partitions with assign

### subscribe: letting Kafka manage assignment

`subscribe()` registers the consumer with one or more topics. The Kafka group coordinator and partition assignor coordinate to distribute partitions among consumers in the group:

```java
consumer.subscribe(List.of("orders", "payments"));
```

A consumer can subscribe using a pattern if it wants to follow topics matching a name:

```java
consumer.subscribe(Pattern.compile("orders\\..*"));
```

When the number of consumers changes, partitions are added to a topic, or a group member leaves, Kafka can perform a rebalance. The new assignment is applied to the relevant consumers. This is the common choice for business applications because the group can automatically coordinate partitions.

### assign: the application manages partitions manually

`assign()` directly assigns partitions to the consumer:

```java
TopicPartition partition0 = new TopicPartition("orders", 0);
TopicPartition partition1 = new TopicPartition("orders", 1);
consumer.assign(List.of(partition0, partition1));
```

When using `assign()`, the consumer does not participate in group coordination for Kafka to distribute partitions automatically. The application is responsible for preventing two workers from unintentionally reading the same partition, detecting partition count changes, and handling reassignment. Do not alternate between calling `subscribe()` and `assign()` as concurrent mechanisms; each represents a different partition ownership strategy.

`subscribe()` is suitable when you need a consumer group to balance load and rebalance automatically. `assign()` is suitable for tasks reading specific partitions, operational tools, or systems with their own distribution mechanism. Manually assigning partitions does not automatically guarantee single-processing semantics.

## 4. Polling and processing ConsumerRecords

Basic read loop example with the Kafka client:

```java
KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
consumer.subscribe(List.of("orders"));

try {
    while (running) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1000));

        for (ConsumerRecord<String, String> record : records) {
            process(record.value());
            log.info("topic={}, partition={}, offset={}, key={}",
                    record.topic(), record.partition(),
                    record.offset(), record.key());
        }

        consumer.commitSync();
    }
} finally {
    consumer.close();
}
```

The example omits the declarations of `running`, `process`, and imports. `poll(Duration)` waits up to the specified duration for data; it may return early when records are available. The poll timeout value is not `max.poll.interval.ms`: one controls the wait time in the current call, while the other limits the interval between poll calls.

Each `ConsumerRecord` provides topic, partition, offset, key, value, timestamp, and headers. You should record topic/partition/offset in logs when handling errors so a specific record can be traced. Avoid logging the full payload if the data contains sensitive information or is large.

`ConsumerRecords` may contain records from multiple partitions. When processing sequentially, the consumer handles records in the order returned by the iterator; meaningful ordering is guaranteed within each partition, not globally across partitions. If processing in parallel, the application must ensure ordering and safe offset commits per partition on its own.

## 5. Offsets and commits

An offset is the position of a record within a partition. A consumer has a read position indicating the next offset to be returned; the group also has a committed offset stored durably so the consumer can resume after a restart or rebalance.

A common point of confusion: when a record with offset `42` is processed successfully, the offset to commit is usually `43`, meaning the next position to read. Kafka commits the next offset rather than the offset of the record just processed. For example:

```text
Partition orders-0:
  offset 40  -> processed and committed
  offset 41  -> processed
  offset 42  -> currently processing
  offset 43  -> next position after processing offset 42

Commit offset 43 so the next read starts at 43.
```

### Auto commit

When `enable.auto.commit=true`, the Kafka client automatically commits the read position on the `auto.commit.interval.ms` schedule. This approach is simple, but the application must clearly understand when commits can occur relative to when business processing happens. If an offset is committed before the business result is durably saved, the process may crash and the record will be skipped upon restart.

### Manual commit

With `enable.auto.commit=false`, the application explicitly acknowledges after processing. `commitSync()` waits for the broker to confirm the commit and is commonly used in simple examples. `commitAsync()` does not block the thread waiting for the result, but error callbacks and commit ordering must be handled carefully; an older commit completing late can overwrite newer progress if the application manages it incorrectly.

Example of synchronous commit after all records from a poll have been processed:

```java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(1000));

for (ConsumerRecord<String, String> record : records) {
    processAndPersist(record);
}

consumer.commitSync();
```

Only commit the current position after all related records have been processed successfully. If processing one record fails and the application still commits a position past that record, the failing record may be skipped. If the commit fails after the business logic has completed, the record may be read again; therefore, consumers need idempotency or duplicate-processing protection.

When committing per partition is needed, an explicit offset map can be created. The offset map must also contain the next position:

```java
Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();
offsets.put(new TopicPartition("orders", 0),
        new OffsetAndMetadata(43));
consumer.commitSync(offsets);
```

The example commits offset `43` for partition `orders-0`. In a real application, only build the map from durably processed offsets and ensure you do not commit past an incomplete record in the same partition.

## 6. auto.offset.reset is not an arbitrary replay policy

`auto.offset.reset` is only applied when the group has no valid committed offset for the partition or the committed offset is no longer within the current log range. Common values:

| Value | Behavior |
|---|---|
| `earliest` | Starts from the earliest offset still retained |
| `latest` | Starts from the end of the log at the time reset is needed |
| `none` | Throws an error if there is no valid offset |

Setting `earliest` does not mean the consumer always re-reads the entire history on every startup. If the group already has a valid committed offset, the consumer continues from that offset. To replay, you need to use a new group ID, reset offsets with an appropriate administrative tool, or explicitly seek to the desired read position. Resetting offsets currently in use in production can cause records to be reprocessed or skipped, so impact must be assessed before acting.

## 7. Rebalance and ConsumerRebalanceListener

A rebalance occurs when the group needs to redistribute partitions, such as when a new consumer joins, a consumer leaves the group, partitions change, or the coordinator needs to perform a new assignment. When partitions are revoked, the consumer needs to finish ongoing work and save appropriate offsets before yielding ownership. After the rebalance, the consumer may receive different partitions and resume from the committed offset.

The Kafka client supports `ConsumerRebalanceListener` so applications can react before and after assignment changes:

```java
consumer.subscribe(List.of("orders"), new ConsumerRebalanceListener() {
    @Override
    public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
        // Commit successfully processed offsets before yielding the partitions.
        commitProcessedOffsets(partitions);
    }

    @Override
    public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
        // Initialize required state for the newly assigned partitions.
        log.info("Assigned partitions: {}", partitions);
    }
});
```

`commitProcessedOffsets` is application logic and should only commit offsets that have been durably processed. Do not blindly commit the entire read position if records are still in flight. Some rebalance strategies and client versions provide additional callbacks or differ in revocation timing; check the API in use and design handling according to the group protocol semantics.

Frequent rebalances reduce throughput because consumers must pause processing, exchange assignments, and may re-read uncommitted records. Monitor rebalance logs, listener processing time, consumer lag, consumer count, and poll configuration. `max.poll.interval.ms` needs to be large enough for the maximum processing time of a single poll cycle, but should not be set excessively high to mask a hung listener.

## 8. Shutdown lifecycle and WakeupException

An application should close the consumer in a controlled manner to release connections, leave the group, and finalize internal resources. `KafkaConsumer` is not thread-safe; most methods must be called from the thread owning the consumer. `wakeup()` is the safe mechanism for another thread to request the polling thread to exit the loop.

Example handling a stop signal:

```java
AtomicBoolean running = new AtomicBoolean(true);
KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);

Thread shutdownHook = new Thread(() -> {
    running.set(false);
    consumer.wakeup();
});
Runtime.getRuntime().addShutdownHook(shutdownHook);

try {
    consumer.subscribe(List.of("orders"));
    while (running.get()) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1000));
        for (ConsumerRecord<String, String> record : records) {
            processAndPersist(record);
        }
        consumer.commitSync();
    }
} catch (WakeupException ex) {
    if (running.get()) {
        throw ex;
    }
} finally {
    consumer.close();
}
```

The snippet illustrates the principle: the shutdown thread calls `wakeup()`, and the consumer-owning thread catches `WakeupException` and closes the consumer in `finally`. In a real application, ensure you do not commit offsets of unfinished records during shutdown. `close()` can wait to complete closing; a timeout matching the system's allowed shutdown window can be passed.

When using Spring Kafka, do not create your own shutdown hook for container-managed consumers. Spring manages starting and stopping listener containers according to the application context lifecycle. Configure the application's graceful shutdown timeout to be sufficient for listeners to finish in-flight work and for the container to close consumers.

## 9. KafkaConsumer is not thread-safe

A `KafkaConsumer` instance should only be used by one thread at a time. Do not share the same consumer across multiple threads where each thread calls `poll`, `commitSync`, `seek`, or `subscribe`. If parallel processing is needed, one of the following approaches can be used:

- Create multiple consumer instances, each running on its own thread and joining the same consumer group.
- Have one thread poll and dispatch records to a worker pool, while manually managing processing order and offset commits per partition.
- Use Spring Kafka concurrency so the container creates and manages multiple consumers.

The pattern of polling on one thread and dispatching to a worker pool can increase throughput, but it is very easy to commit past an unfinished record. For example, a partition has offsets 10, 11, and 12; if a worker finishes offset 12 before 10 and 11, offset 13 must not be committed because upon restart the first two records could be skipped. You must track contiguous processed offsets per partition and only commit the next position of that contiguous sequence.

If you need to control the consumer from another thread, use `wakeup()` to wake the polling thread. Do not simply use `synchronized` to turn `KafkaConsumer` into a multithreaded client; that does not change the consumer's ownership and lifecycle constraints.

## 10. Consumer lifecycle in Spring Kafka

With Spring Kafka, `@KafkaListener` declares a message-handling method. Spring creates a listener container, and the container creates and manages `KafkaConsumer`, calls poll, passes records to the listener, handles acks/commits, and reacts to rebalances.

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(topics = "orders", groupId = "order-reader")
    public void onMessage(ConsumerRecord<String, OrderCreated> record) {
        orderService.handle(record.value());
    }
}
```

Basic consumer configuration in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-reader
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.orders.events
```

This example assumes the application has JSON type mapping configured appropriately for the `OrderCreated` class; in a production system, you should declare explicit type mapping or use an appropriate default type instead of opening trusted packages too broadly.

Spring Kafka has main container types such as `KafkaMessageListenerContainer` and `ConcurrentMessageListenerContainer`. The first manages a single consumer; the concurrent container creates multiple child containers/consumers according to the concurrency setting. The number of useful consumers is bounded by the number of partitions assigned to the group. If there are six partitions and concurrency is set to ten, ten consumers cannot all receive partitions of that topic within the same group; some consumers will remain unassigned.

### AckMode and offset acknowledgment

Spring Kafka manages commits according to the listener container's `AckMode`. Common modes:

| AckMode | High-level meaning |
|---|---|
| `RECORD` | Commits after the listener finishes processing each record in a record listener |
| `BATCH` | Commits after all records from a poll have been processed |
| `TIME` | Commits when the configured interval has elapsed and records have been processed |
| `COUNT` | Commits when the configured threshold of processed records is reached |
| `MANUAL` | The listener calls acknowledge; the container commits according to this mode's rules |
| `MANUAL_IMMEDIATE` | Commits immediately when acknowledge is called on the consumer thread; off-thread calls may be handled via the container's deferred mechanism |

Exact names and behavioral details should be verified against your Spring Kafka version. When using `enable.auto.commit=false`, by default the container usually manages offsets instead of the Kafka client's auto-commit. Do not simultaneously enable client auto-commit without understanding the impact, as it may commit before the listener completes.

Example of manual acknowledgment:

```java
@KafkaListener(topics = "orders", groupId = "order-reader")
public void onMessage(OrderCreated event, Acknowledgment acknowledgment) {
    orderService.handleAndPersist(event);
    acknowledgment.acknowledge();
}
```

Only call `acknowledge()` after business processing has completed or work has been durably recorded by design. If the listener throws an exception, Spring Kafka can forward the error to an error handler/retry policy depending on configuration. Design retry, dead-letter, and commit together to avoid losing records or uncontrolled business repetition.

## 11. Common record-reading scenarios

| Scenario | Behavior to understand |
|---|---|
| Consumer starts for the first time | Uses `auto.offset.reset` if the group has no valid offset |
| Normal consumer restart | Resumes from the group's committed offset |
| Consumer experiences rebalance | Partitions may be assigned to another consumer; uncommitted records may be re-read |
| Poll returns no records | `ConsumerRecords` is empty; continue polling as part of the normal lifecycle |
| Processing succeeds but commit fails | Record may be redelivered; idempotent handling is required |
| Commit happens before business persistence | Risk of logically losing the record if the process crashes after commit |
| Consumer processes too slowly | May exceed `max.poll.interval.ms`, leave the group, and trigger a rebalance |
| Multiple threads call the same consumer | Unsafe; a single thread must own the consumer or use multiple consumer instances |

Kafka consumers naturally fit the at-least-once model when the application only commits after successful processing: records may be redelivered if a commit fails or the process stops at an inopportune moment. To prevent duplicate business effects, use an idempotency key, unique constraint, upsert, or transaction in the appropriate storage system. Exactly-once processing across multiple systems requires dedicated transaction design and consistency boundaries; committing offsets alone does not guarantee exactly-once for side effects outside Kafka.

## 12. Monitoring and diagnostics

When a consumer reads slowly or rebalances continuously, monitor both Kafka state and application processing times:

- Consumer lag by group and partition to know the gap between the log end offset and committed/current position.
- Records per poll, poll duration, and processing time per record/batch.
- Rebalance count, revoked/assigned partitions, and how long the group stays stable.
- Failed commits, commit latency, and committed offsets.
- Deserialization errors, business errors, retries, and dead-letter traffic.
- Paused consumers, full worker queues, or slow downstream DB/HTTP calls.

For manual inspection, use `kafka-consumer-groups` to view groups, members, partition assignments, and lag:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-reader
```

Before changing offsets or resetting a group, clearly identify which records will be re-read or skipped. For processing incidents, it is usually best to investigate the root cause in the listener, dependencies, and commit strategy before altering offsets with admin tools.

## Pre-production consumer checklist

- The consumer has a `group.id` and deserializers compatible with the producer's data.
- `subscribe()` vs. `assign()` is chosen to match the partition management strategy.
- The poll loop keeps running and processes records within the `max.poll.interval.ms` limit.
- `auto.offset.reset` is understood correctly: it only applies when an offset is invalid or missing.
- Offsets are committed only after records have been processed or durably stored.
- Idempotency is in place to tolerate redelivered records.
- Each `KafkaConsumer` is owned by only one thread; shutdown uses `wakeup()` and `close()` on the proper thread.
- Rebalance listeners and commit logic do not confirm past unprocessed records.
- The Spring Kafka container manages lifecycle, `AckMode`, retry, and error handler according to a verified configuration.
- Metrics exist for lag, poll duration, processing duration, commits, and rebalances.

The lifecycle of `KafkaConsumer` is a continuous loop between polling, processing, and offset acknowledgment. When you understand how a consumer joins a group, receives partitions, maintains its read position, and shuts down properly, a Spring Kafka application can consume events reliably, recover from errors, and keep record reprocessing under control.
