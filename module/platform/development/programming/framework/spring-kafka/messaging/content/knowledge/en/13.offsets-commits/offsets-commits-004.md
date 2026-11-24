# Committing by Record vs. by Batch

## 1. Why Do We Need to Choose a Commit Strategy?

A Kafka consumer reads records from partitions by offset. After the application processes the data, the consumer group must save the position from which it can resume reading on the next run. Saving this position is called **committing an offset**.

An application can commit after each record or after finishing a group of records returned from a single `poll()`. These two approaches create different trade-offs among throughput, commit overhead, and the scope of records that may be redelivered if the application fails.

- **Commit by record**: confirms progress immediately after each individual record is processed successfully. If the next record fails, previously committed records may not need to be re-read.
- **Commit by batch**: processes all records from a single poll before confirming progress for the corresponding partitions. This reduces the number of commits, but can cause multiple already-processed records to be redelivered if the application stops before committing.

Committing an offset does not mean Kafka knows that the database or business logic has finished. The application must place commits after the boundary of successful processing and design the consumer to tolerate record redelivery.

## 2. The Committed Offset Is the Next Position to Read

Kafka stores the next offset the consumer group needs to read, not the offset of the last processed record.

For example, a consumer successfully processes a record with offset `40`, then commits `41`:

```text
Processed record: offset 40
Committed offset: 41
Next read:        starts from offset 41
```

If the consumer processes records `40`, `41`, and `42` in a batch and all succeed, the next commit position is typically `43`. Offsets are managed independently per topic-partition; offset `43` of `orders-0` is unrelated to offset `43` of `orders-1`.

Offsets may have gaps due to log compaction, transaction markers, or records not returned under the isolation level. Therefore, do not use the count of observed records in place of actual offsets.

## 3. Committing by Record in the Kafka Consumer API

With the raw Kafka Java Consumer, an application can disable auto-commit, process each record, and commit the next offset for that partition.

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders"));

    while (true) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1_000));

        for (TopicPartition partition : records.partitions()) {
            for (ConsumerRecord<String, String> record : records.records(partition)) {
                processBusiness(record);

                // Commit the partition's next offset after the record succeeds.
                consumer.commitSync(Map.of(
                        partition,
                        new OffsetAndMetadata(record.offset() + 1)));
            }
        }
    }
}
```

For each record, the application executes the business logic first and then commits `record.offset() + 1`. If `processBusiness()` throws an error, the commit call for that record does not run; after the consumer restarts or partitions are reassigned, the record can be re-read.

The example above commits synchronously after each record, making it easy to observe, though it generates many commit round-trips. In high-throughput systems, this cost can be significant. Furthermore, if a poll contains records from multiple partitions, progress must be tracked separately for each partition; never commit an offset from one partition for another partition.

## 4. Committing by Batch in the Kafka Consumer API

If the application commits only after all records in a poll have been processed successfully, it can call `commitSync()` after the loop:

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

        // Commit only after every record in the poll has been processed successfully.
        consumer.commitSync();
    }
}
```

Calling `commitSync()` without a map commits the current positions the consumer has read across its assigned partitions. Therefore, call it only at the end of the batch once all records in the poll have completed. If a record fails mid-loop, execution exits the processing loop before committing; the batch can be redelivered from the previous committed offset.

This creates the possibility of duplicate processing: earlier records in the batch may have already updated the database successfully before a later record fails. The consumer should be idempotent, for example by storing processed `eventId`s with a unique constraint or using a business key so repeated operations produce no additional side effects.

### Committing an explicit offset map

When you want exact control over partitions and commit positions, you can pass a `TopicPartition` → `OffsetAndMetadata` map:

```java
Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

for (TopicPartition partition : records.partitions()) {
    List<ConsumerRecord<String, String>> partitionRecords =
            records.records(partition);

    for (ConsumerRecord<String, String> record : partitionRecords) {
        processBusiness(record);
    }

    if (!partitionRecords.isEmpty()) {
        long nextOffset = partitionRecords
                .get(partitionRecords.size() - 1)
                .offset() + 1;
        offsets.put(partition, new OffsetAndMetadata(nextOffset));
    }
}

if (!offsets.isEmpty()) {
    consumer.commitSync(offsets);
}
```

The code processes records sequentially within each partition and adds only the last successfully processed offset to the map. If a record in a partition fails, the loop throws an exception before that partition is added to the map; partitions processed earlier could be committed if the application catches and handles errors according to its own design. The example above does not catch exceptions in order to keep the main flow simple.

When managing offsets manually, commit only up to the contiguous offset that has been processed successfully in each partition. Never commit past a record that is still in progress or has failed.

## 5. commitSync() and commitAsync()

The Kafka Consumer provides two ways to send commit requests:

| API | Behavior | Trade-off |
|---|---|---|
| `commitSync()` | Sends commit request and waits for broker response | Easy to tell whether commit succeeded or failed; consumer thread must wait |
| `commitAsync()` | Sends commit request without waiting immediately for the result | Reduces blocking time, but requires handling callbacks and commit ordering |

Example of asynchronous commit:

```java
consumer.commitAsync((offsets, exception) -> {
    if (exception != null) {
        log.error("Offset commit failed: {}", offsets, exception);
        return;
    }

    log.debug("Offset committed: {}", offsets);
});
```

`commitAsync()` returns control immediately to the calling thread. If multiple asynchronous commits are pending, callbacks may complete in a different order than the application expects depending on the situation. Never send an older commit after a newer commit in a way that rolls back group progress. When closing the consumer or handling rebalance boundaries, `commitSync()` is commonly used to wait for the final commit to finish.

`commitAsync()` does not increase reliability by itself. If the callback reports an error, the application must decide how to handle it; ignoring errors can cause the group to recover from an older committed offset and re-read records.

## 6. Committing by Record in Spring Kafka

When using `@KafkaListener`, the listener container manages the `KafkaConsumer`, the poll loop, and offset commits. The application chooses a strategy via `ContainerProperties.AckMode` or the Spring Boot property `spring.kafka.listener.ack-mode`.

`AckMode.RECORD` instructs the container to commit after the listener successfully processes each record. If the listener throws an exception, the commit for that record is not performed on the success path; the error handler decides on retry or recovery.

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
    listener:
      ack-mode: record
```

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(topics = "orders")
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
```

In this configuration, each time `onOrder()` completes successfully, the container can commit that record's progress according to `RECORD`. This is appropriate when you want to narrow the scope of records that might be replayed if a subsequent record fails.

Since Spring Kafka 2.3, the framework automatically sets `enable.auto.commit=false` if the application has not explicitly configured this property. This allows the listener container to manage commits via AckMode. Do not enable Kafka client auto-commit at the same time if the goal is to control commits based on listener outcomes.

## 7. Committing by Batch in Spring Kafka

`AckMode.BATCH` is the common default mode for the listener container. The container commits offsets after all records received from a single `poll()` have been processed successfully.

With a record listener, the method is still called once per record, but the container waits until the entire poll batch finishes processing before committing. With a batch listener, the method receives a list of records and typically processes the list as a unit; after the listener finishes successfully, the container commits the batch's offsets.

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
```

Batch listener example:

```java
@Component
public class OrderBatchListener {

    private final OrderService orderService;

    public OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "batchKafkaListenerContainerFactory")
    public void onOrders(List<OrderCreated> events) {
        orderService.processBatch(events);
    }
}
```

The factory used for the endpoint needs batch mode enabled:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
batchKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.BATCH);
    return factory;
}
```

The batch size is not fixed. `max.poll.records` caps the maximum number of records returned in one poll; the actual count can be lower depending on available data, fetch settings, and assigned partitions. A poll batch may also contain records from multiple partitions, each with its own offset.

`AckMode.RECORD` is not supported for batch listeners because the method receives a group of records in a single invocation. If partial batch acknowledgment is required, use the manual acknowledgment mechanism appropriate for your version and ensure you do not commit past unprocessed records.

## 8. Comparing Record vs. Batch Commits in Spring Kafka

| Criterion | `AckMode.RECORD` | `AckMode.BATCH` |
|---|---|---|
| Commit timing | After each successful listener processing of a record | After all records from a poll are processed successfully |
| Listener processing unit | Record listener | Record listener or batch listener |
| Commit frequency | May be higher, depending on record count | Usually lower, per poll batch |
| Throughput | May be lower due to frequent commits | May be higher thanks to reduced commit overhead |
| Replay scope on failure | Usually narrower, close to the failed record | May include earlier uncommitted records in the batch |
| Use case | When per-record commit progress is needed | When balancing throughput and commits |
| Batch listener | Not supported | Natural choice for batch processing |

Example where a poll returns records at offsets `10`, `11`, and `12` from the same partition:

```text
RECORD:
  process 10 ── commit 11
  process 11 ── commit 12
  process 12 ── commit 13

BATCH:
  process 10 ── process 11 ── process 12 ── commit 13
```

If processing offset `12` fails after `10` and `11` completed:

- With `RECORD`, committed progress may already be at `12`, so on retry the consumer continues from the failed record according to the error handler's mechanism.
- With `BATCH`, the end-of-batch commit has not occurred; records `10` and `11` may be redelivered along with record `12`.

In both cases, actual behavior also depends on the error handler, recovery, transactions, and AckMode. Therefore, handlers should be idempotent even when using `RECORD`.

## 9. Manual Acknowledgment When You Need to Decide Commit Timing

If the listener needs to decide when to acknowledge after a specific business condition, you can use `MANUAL` or `MANUAL_IMMEDIATE` and accept `Acknowledgment`.

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
manualListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.MANUAL);
    return factory;
}
```

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "manualListenerFactory")
public void onOrder(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.process(event);
    acknowledgment.acknowledge();
}
```

`MANUAL` queues the acknowledgment into the container's batch commit mechanism. `MANUAL_IMMEDIATE` commits immediately if `acknowledge()` is called on the consumer thread. For record listeners, acknowledge only after the business operation finishes; for batch listeners, acknowledge only after the portion of the batch you are confirming has been safely processed.

Manual acknowledgment does not create exactly-once semantics for a database. If the database commit succeeds but the process stops before the Kafka offset is committed, the record may be redelivered. Idempotency or an appropriate outbox/inbox design is still necessary.

## 10. Failures in Batches and BatchListenerFailedException

With a batch listener, if a record fails, the application can throw `BatchListenerFailedException` to pinpoint the failing record or index. `DefaultErrorHandler` can use this information to handle preceding records and retry/recover from the failing position according to configuration.

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        try {
            orderService.process(record.value());
        } catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Failed to process order event", exception, record);
        }
    }
}
```

If the listener throws an exception without identifying the failing record, the error handler may have to retry the entire batch as a fallback strategy. When doing bulk database processing, decide whether the database transaction rolls back the entire batch; if part of the batch has already committed independently, retries can repeat side effects.

For a record listener using `AckMode.BATCH`, an exception on one record can also prevent the poll batch from committing. `DefaultErrorHandler` and ack settings determine how seeking, retrying, and committing processed portions work. Do not assume that just because a listener finished one record, its offset is committed when AckMode is `BATCH`.

## 11. Impact of Commits on At-Most-Once and At-Least-Once

When commits happen relative to business processing determines the risk of losing records or duplicating processing:

### At-most-once

Commit the offset successfully before business processing. If the process stops after committing but before processing finishes, Kafka resumes from the offset after that record, and the incomplete record may be skipped. If the commit fails, the application should not proceed with processing and still treat it as at-most-once. This reduces duplicate processing at the cost of accepting potential missed processing.

### At-least-once

Process business logic successfully, then commit. If the process stops after processing but before committing, the record may be redelivered. This avoids skipping incomplete records, but requires an idempotent consumer.

### Exactly-once in Kafka

Committing by record or batch does not create exactly-once on its own. For consume-transform-produce flows between Kafka topics, Kafka transactions can coordinate output records and input offsets within the same Kafka transaction. Downstream consumers use `isolation.level=read_committed` to read only committed transaction data.

If the listener updates a database or calls an external API outside Kafka, Kafka transactions do not automatically form a shared ACID transaction with the external system. Outbox/inbox, database transactions, or idempotency are required to ensure business correctness.

| Goal | Typical Sequence | Risk |
|---|---|---|
| At-most-once | Commit then process | Processing may be lost if stopped after commit |
| At-least-once | Process then commit | Processing may repeat if stopped before commit |
| Exactly-once in Kafka | Write output and offsets in a Kafka transaction | Requires proper transaction/isolation config; does not automatically cover databases or external APIs |

## 12. Other AckModes Besides RECORD and BATCH

Spring Kafka also supports threshold-based commit modes:

| AckMode | High-Level Behavior |
|---|---|
| `TIME` | Commits processed offsets when the configured time interval elapses |
| `COUNT` | Commits when the configured number of processed records is reached |
| `COUNT_TIME` | Commits when either the time or record count threshold is reached |
| `MANUAL` | Listener calls `acknowledge()`; container handles commits using manual/batch semantics |
| `MANUAL_IMMEDIATE` | Commits immediately when acknowledge is called on the consumer thread |

`TIME`, `COUNT`, and `COUNT_TIME` still do not allow committing past unprocessed records. They adjust how frequently completed offsets are committed, rather than replacing the determination of successful business boundaries.

Listener containers commonly default to `BATCH`. Spring Kafka also automatically disables Kafka client auto-commit if the application does not explicitly configure `enable.auto.commit`, preventing two commit mechanisms from controlling progress simultaneously.

## 13. Monitoring and Inspecting Committed Offsets

You can use the Kafka CLI to inspect a group's committed offsets and lag:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
```

Common columns:

| Column | Meaning |
|---|---|
| `CURRENT-OFFSET` | Committed offset for the group and partition |
| `LOG-END-OFFSET` | End offset used to compare progress |
| `LAG` | Distance between the end offset and the committed offset |
| `CONSUMER-ID` | Consumer member currently assigned the partition, if any |

If the consumer has polled and processed records without committing yet, `CURRENT-OFFSET` can still lag behind the runtime position. Consequently, the lag shown by the CLI may appear larger than the actual number of records not yet polled by the listener. Read committed offsets alongside position, throughput, and processing status when diagnosing.

Additional metrics to monitor:

- Commit latency and commit failures.
- Consumer lag per partition.
- Retry counts and records routed to DLT.
- Listener processing duration and time between polls.
- Rebalances, partitions revoked/assigned, and broker/network errors.

## 14. Testing Record and Batch Commits

Tests should verify both committed offsets and business side effects, not merely that the listener was invoked.

Recommended scenarios:

1. **Record success:** with `AckMode.RECORD`, send multiple records and verify the committed offset advances after each successful execution.
2. **Batch success:** with `AckMode.BATCH`, send multiple records in a poll and verify the commit occurs after the batch completes.
3. **Mid-poll record failure:** fail one record after earlier records have processed; compare the redelivery scope between RECORD and BATCH.
4. **Manual acknowledgment:** verify offsets are uncommitted before `acknowledge()` and committed per the chosen mode afterward.
5. **Restart before commit:** stop the consumer after business logic completes but before commit, then verify the record can be redelivered and the handler does not duplicate side effects.
6. **Multiple partitions:** verify offsets are committed independently per partition and never past an unprocessed record.
7. **Commit failure:** simulate a broker error or rebalance to verify the application observes commit errors and recovers appropriately.
8. **Batch failure:** throw `BatchListenerFailedException` for a record and verify retry/recovery per the error handler.

You can use `spring-kafka-test` or the Kafka test starter matching your Spring Boot line. For rebalances, network errors, and transactions, supplement tests with a broker/container close to your deployment environment.

## 15. Which Strategy Should You Choose?

| Need | Starting Strategy | Reason |
|---|---|---|
| Each event is an independent unit, want commits close to each record | Record listener + `AckMode.RECORD` | Narrows the scope of records that may be replayed on error |
| Prioritize throughput and bulk processing | Batch listener + `AckMode.BATCH` | Reduces commit frequency and leverages bulk processing |
| Want a record listener while grouping commits by poll | Record listener + `AckMode.BATCH` | Listener still receives individual records; container commits only after the poll batch completes |
| Business logic needs to decide when to acknowledge | `MANUAL` or `MANUAL_IMMEDIATE` | Listener explicitly acknowledges after processing conditions are met |
| Consume-transform-produce needs atomicity within Kafka | Kafka transactions and offsets sent in transaction | Combines output records and input progress in the same Kafka transaction |

There is no one-size-fits-all strategy for every workload. Measure throughput, commit latency, processing time, and redelivery on failure. If downstream is a database, ensure idempotency or use outbox/inbox before increasing parallelism or decreasing commit frequency.

## 16. Summary

- Committing an offset saves the next position to read per consumer group and partition.
- Record commits confirm after each record; batch commits confirm after finishing the records of a single poll.
- The Kafka Consumer API supports `commitSync()` and `commitAsync()`; the application must commit the next offset, not the offset of the last record.
- Spring Kafka uses `AckMode.RECORD` and `AckMode.BATCH` for container-managed commits; `BATCH` is the common default.
- Batch commits reduce commit count but can cause multiple already-processed records to be redelivered if the batch has not committed.
- Manual acknowledgment lets the listener explicitly acknowledge, but does not create an atomic transaction with a database.
- At-least-once typically requires an idempotent consumer; exactly-once requires Kafka transactions within Kafka's scope and dedicated design for external side effects.
- Tests must verify committed offsets, redelivery, and business outcomes in failure/restart scenarios.

By understanding record-level and batch-level commits, teams can pick the right confirmation boundary for Spring Kafka listeners, balance commit overhead against replay scope, and build reliable consumers when applications or brokers fail.
