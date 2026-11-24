# Receiving List<ConsumerRecord> in a listener

## Lesson objectives

In the **Batches and throughput** chapter, this lesson explains how to receive a batch of Kafka records in a single listener invocation using Spring Kafka's `List<ConsumerRecord<K, V>>` type. Each element preserves record metadata such as topic, partition, offset, key, value, timestamp, and headers, allowing the application to process data in batches while still accessing individual record information.

**SPRING_KAFKA_MESSAGING** focuses on building applications that produce and consume Kafka events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead letters, transactions, exactly-once semantics, concurrency, and testing. Batch listeners reduce listener invocation overhead and can increase throughput when batch processing fits, though commits, per-record failures, and processing duration must be carefully controlled.

After this lesson, you will be able to:

- Distinguish a record listener from a batch listener.
- Configure `ConcurrentKafkaListenerContainerFactory` to invoke listeners in batches.
- Declare a method accepting `List<ConsumerRecord<K, V>>`.
- Read key, value, topic, partition, offset, timestamp, and headers of each record.
- Understand the relationship between batch size, `max.poll.records`, partitions, and concurrency.
- Choose an acknowledgment mode and handle offsets properly for batches.
- Handle a single-record failure inside a batch using `BatchListenerFailedException`.
- Test batch listeners and diagnose throughput issues.

## 1. Record listener vs. batch listener

Spring Kafka supports two common ways of invoking a listener.

A **Record listener** receives one record at a time:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

A **Batch listener** receives multiple records in a single invocation:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "batchListenerContainerFactory"
)
public void listen(List<ConsumerRecord<String, OrderCreated>> records) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        billingService.process(record.value());
    }
}
~~~

With a record listener, the container invokes the method for each individual record. With a batch listener, the container gathers the records returned in one poll and passes them into the method as a list.

| Criterion | Record listener | Batch listener |
|---|---|---|
| Listener parameter | A single payload or a single `ConsumerRecord` | `List<Payload>` or `List<ConsumerRecord>` |
| Number of invocations | Typically once per record | Once per polled batch |
| Metadata access | Yes if accepting `ConsumerRecord` | Yes per element if accepting `List<ConsumerRecord>` |
| Batch processing | Application groups manually or processes separately | Can process the entire batch directly |
| Error handling | Scoped to the record currently being invoked | Must identify the failed record/index in the batch |
| Commit | Can be per record or container-configured | Typically per batch or via manual acknowledgment |

A batch listener does not mean Kafka stores multiple records as a single message. Each record remains an independent entry in its partition; Spring Kafka simply collects the poll result into a list to invoke the listener.

## 2. What information does ConsumerRecord contain?

`ConsumerRecord<K, V>` is a Kafka client type representing a record read by the consumer. It holds the payload along with metadata supplied by Kafka.

Commonly used methods:

| Method | Meaning |
|---|---|
| `topic()` | Topic name |
| `partition()` | Partition containing the record |
| `offset()` | Record offset within the partition |
| `key()` | Deserialized key |
| `value()` | Deserialized value |
| `timestamp()` | Record timestamp |
| `timestampType()` | Timestamp type |
| `headers()` | Kafka record headers |
| `serializedKeySize()` | Size of the serialized key |
| `serializedValueSize()` | Size of the serialized value |

Example record:

~~~text
topic     = commerce.order.created
partition = 2
offset    = 105
key       = order-10001
value     = OrderCreated(...)
timestamp = 1794894000000
~~~

Metadata helps the application log, trace, reconcile, and diagnose errors. For example, when processing a record fails, logging topic, partition, and offset pinpoints the exact data location to inspect or replay.

### 2.1. Distinguishing offset from List index

An offset is the position of a record within a partition. The index of an element in a Java `List` is only the record's position within the current batch.

Example:

| List index | Topic partition | Offset |
|---:|---|---:|
| 0 | partition 0 | 101 |
| 1 | partition 1 | 55 |
| 2 | partition 0 | 102 |
| 3 | partition 2 | 8 |

You cannot use `listIndex` as a Kafka offset. One batch can contain records from multiple partitions, and partition offsets have independent ranges.

### 2.2. A batch can contain multiple partitions

If a consumer is assigned multiple partitions, a single poll can return records from multiple partitions. Therefore, `List<ConsumerRecord<K, V>>` does not necessarily contain records from only one partition.

Kafka guarantees record order within each partition. There is no global order across partitions. The application must not assume two adjacent records in the `List` always have a business before/after relationship.

When ordered processing for an aggregate is required, the producer should use a stable key so related records route to the same partition, and the consumer should process sequentially within that partition.

## 3. Enabling batch listener in ConcurrentKafkaListenerContainerFactory

For a listener to receive a list of records, the factory must be configured for batch mode using `setBatchListener(true)`.

Example:

~~~java
@Configuration
public class KafkaBatchListenerConfiguration {

    @Bean(name = "batchListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            batchListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(3);

        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.BATCH);

        return factory;
    }
}
~~~

Key settings:

- `setConsumerFactory(...)` provides the consumer and deserializers.
- `setBatchListener(true)` instructs the container to invoke the listener in batch mode.
- `setConcurrency(3)` creates up to three child consumer containers for endpoints using this factory.
- `AckMode.BATCH` commits offsets per batch after the listener completes successfully per container semantics.

The listener receives batches only when the endpoint uses the factory configured with batch mode enabled.

### 3.1. Declaring a listener accepting List<ConsumerRecord>

~~~java
@Service
public class OrderBatchListener {

    private final BillingService billingService;

    public OrderBatchListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service",
        containerFactory = "batchListenerContainerFactory"
    )
    public void listen(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (ConsumerRecord<String, OrderCreated> record : records) {
            billingService.process(record.value());
        }
    }
}
~~~

Generic type descriptions:

- `String`: key type after deserialization.
- `OrderCreated`: value type after deserialization.

The listener's generics must be compatible with the `ConsumerFactory` and deserializers attached to the factory. Java generics provide compile-time type checking, yet they do not automatically alter how Kafka deserializes bytes.

### 3.2. If batch mode is not enabled

If a listener declares `List<ConsumerRecord<...>>` while the container factory remains in record mode, the parameter type mismatches the invocation mode. Depending on configuration and version, the application may fail during endpoint initialization or when the container invokes the listener.

Verify which factory the endpoint uses and whether that factory has called `setBatchListener(true)`.

## 4. Consumer configuration and batch size limits

The Kafka consumer has the `max.poll.records` property to cap the maximum number of records returned in a single `poll()`.

Example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
~~~

`max-poll-records: 100` means one poll returns at most 100 records to the consumer. This is not a guarantee that every batch always has exactly 100 elements. A batch can be smaller depending on available data, assigned partitions, fetch limits, and poll timing.

Related properties:

| Property | Impact |
|---|---|
| `max.poll.records` | Caps the maximum number of records returned in one poll |
| `fetch.min.bytes` | Amount of data the broker tries to accumulate before returning a fetch response |
| `fetch.max.wait.ms` | Time the broker waits to satisfy fetch min bytes |
| `max.partition.fetch.bytes` | Caps data fetched from each partition |
| `max.poll.interval.ms` | Maximum time allowed between polls |
| `fetch.max.bytes` | Caps total data for a single fetch request per client configuration |

Fetch limits do not equate to the element count in the `List`. Actual batch size depends on how many records can be fetched and `max.poll.records`.

### 4.1. Choosing batch size

Large batches can reduce listener invocations and leverage batch operations in databases or downstream services. However, overly large batches can:

- Increase memory required to hold records.
- Extend processing duration for a single poll.
- Increase retry time when a batch fails.
- Increase how many records must be reprocessed if an error happens late in the batch.
- Cause the listener to exceed `max.poll.interval.ms`.

Small batches reduce work per invocation, yet they can increase listener call overhead and downstream operations.

Measure processing time, consumer lag, actual batch size, error rate, and database load to select an appropriate value.

## 5. Reading metadata of each ConsumerRecord

A major advantage of `List<ConsumerRecord<K, V>>` is that every element retains full metadata.

Example logging record position:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "batchListenerContainerFactory"
)
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        log.info(
            "Received topic={}, partition={}, offset={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key()
        );

        billingService.process(record.value());
    }
}
~~~

This metadata is useful for:

- Recording which record caused an error.
- Tracking lag per partition.
- Reconciling data with the producer.
- Producing traceable logs.
- Classifying records by topic or header.
- Handling multiple topics in a single listener when the subscription is designed for it.

Do not log entire sensitive payloads merely for debugging. Usually topic, partition, offset, key, and correlation ID are sufficient.

### 5.1. Reading Kafka headers

Kafka records can carry headers as name-and-byte-value pairs.

Example reading the `trace-id` header:

~~~java
Header traceHeader = record.headers().lastHeader("trace-id");

String traceId = traceHeader == null
    ? null
    : new String(traceHeader.value(), StandardCharsets.UTF_8);
~~~

When processing a batch:

~~~java
for (ConsumerRecord<String, OrderCreated> record : records) {
    Header header = record.headers().lastHeader("trace-id");

    String traceId = header == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);

    billingService.process(record.value(), traceId);
}
~~~

Record headers are `byte[]`. Convert them to `String` only when the producer specifies the corresponding encoding, such as UTF-8. For binary headers, use a decoder matching the exact format.

### 5.2. Handling null keys and values

Kafka allows records with null keys. On compacted topics, a record with a non-null key and a null value can serve as a tombstone indicating key deletion.

Therefore, never assume `record.key()` or `record.value()` is always non-null:

~~~java
for (ConsumerRecord<String, OrderCreated> record : records) {
    if (record.value() == null) {
        handleTombstone(record.key());
        continue;
    }

    billingService.process(record.value());
}
~~~

Even if a topic does not use tombstones, the convention for handling null values should still be defined in the event contract. Prevent null values from accidentally entering business services and throwing a `NullPointerException`.

## 6. Comparing List<ConsumerRecord> vs. List<Payload>

Spring Kafka supports batch listeners accepting either a payload list or a `ConsumerRecord` list.

**Accepting payloads only:**

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "batchPayloadListenerContainerFactory"
)
public void listen(List<OrderCreated> events) {
    billingService.processBatch(events);
}
~~~

**Accepting full records:**

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "batchRecordListenerContainerFactory"
)
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records) {
    // Can read individual metadata of each record.
}
~~~

| Criterion | `List<OrderCreated>` | `List<ConsumerRecord<String, OrderCreated>>` |
|---|---|---|
| Payload | Yes | Yes via `value()` |
| Key | Not in payload element unless embedded in the object | Yes via `key()` |
| Topic | Not in payload element | Yes via `topic()` |
| Partition | No | Yes via `partition()` |
| Offset | No | Yes via `offset()` |
| Timestamp | No | Yes via `timestamp()` |
| Headers | Not directly | Yes via `headers()` |
| Purpose | Business processing over a list of payloads | Batch processing while still needing Kafka metadata |

If business logic only needs a list of events, `List<Payload>` can be simpler. If you need to observe offset, partition, key, timestamp, or headers, accept `List<ConsumerRecord<K, V>>`.

## 7. A batch can receive records from multiple topics

A listener can subscribe to multiple topics using `topics` or `topicPattern`, provided the payload contract and deserialization are designed accordingly.

Example:

~~~java
@KafkaListener(
    topics = {
        "commerce.order.created",
        "commerce.order.cancelled"
    },
    groupId = "order-audit-service",
    containerFactory = "batchRecordListenerContainerFactory"
)
public void audit(
        List<ConsumerRecord<String, Object>> records) {

    for (ConsumerRecord<String, Object> record : records) {
        switch (record.topic()) {
            case "commerce.order.created" ->
                auditOrderCreated(record);
            case "commerce.order.cancelled" ->
                auditOrderCancelled(record);
            default ->
                log.warn("Unexpected topic: {}", record.topic());
        }
    }
}
~~~

Ensure the deserializer or message conversion can produce appropriate value types for every topic the listener subscribes to. Using `Object` does not automatically resolve schema differences between events.

If topics have different structures, use a shared event envelope, explicit type mapping, or separate listeners per event type.

## 8. Processing a batch record by record

There are two common approaches:

1. Process each record sequentially in a loop.
2. Transform payloads into a collection to invoke a service or database in bulk.

Sequential processing:

~~~java
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        billingService.process(record.value());
    }
}
~~~

Batch processing:

~~~java
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records) {

    List<OrderCreated> events = records.stream()
        .map(ConsumerRecord::value)
        .filter(Objects::nonNull)
        .toList();

    billingService.processBatch(events);
}
~~~

Batch processing can reduce round trips if the service supports bulk operations. For example, the database can insert multiple invoices in one batch rather than issuing an insert per invoice.

However, batch processing only fits when events can be handled together and there is a clear rollback/retry strategy. If one element fails, you need to know whether other elements have already been written successfully.

### 8.1. Avoid arbitrary parallelization inside the listener

Do not submit all records to a thread pool and return immediately from the listener if the container might commit offsets before the actual work finishes.

Dangerous example:

~~~java
public void listen(List<ConsumerRecord<String, OrderCreated>> records) {
    records.forEach(record ->
        executor.submit(() -> billingService.process(record.value()))
    );
}
~~~

The listener can return before the tasks finish. The container may commit the batch's offsets, after which a task fails and Kafka will not redeliver the record.

If asynchronous processing is required, wait for all tasks to finish before acknowledgment/commit, or design dedicated offset and error management. Also enforce per-partition ordering if business rules require it.

## 9. Acknowledgment and offset commit with batch listeners

With batch listeners, the container typically uses `AckMode.BATCH`: after the listener successfully processes the polled batch, the container commits the corresponding offsets for the partitions in the batch according to Spring Kafka's mechanism.

Configuration example:

~~~java
factory.getContainerProperties()
    .setAckMode(ContainerProperties.AckMode.BATCH);
~~~

Common `AckMode` options:

| AckMode | General meaning |
|---|---|
| BATCH | Commits after the listener finishes processing the polled batch |
| MANUAL | Listener calls acknowledge; container handles commits per mode semantics |
| MANUAL_IMMEDIATE | Requests an immediate commit when acknowledge is called on the consumer thread |
| TIME / COUNT / COUNT_TIME | Commits based on time or record count thresholds as supported by the container |

`AckMode.RECORD` does not fit batch listeners because the listener is invoked for the whole batch rather than each individual record. Choose the acknowledgment mode according to the listener type and Spring Kafka version.

### 9.1. Manual acknowledgment

If the listener needs to decide when to acknowledge the batch, accept `Acknowledgment`:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "manualBatchListenerContainerFactory"
)
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records,
        Acknowledgment acknowledgment) {

    billingService.processBatch(
        records.stream()
            .map(ConsumerRecord::value)
            .toList()
    );

    acknowledgment.acknowledge();
}
~~~

The factory must configure `AckMode.MANUAL` or `MANUAL_IMMEDIATE` accordingly.

Acknowledge only after all necessary business work has completed. If database writes happen across multiple steps, consider database transactions or idempotency to handle cases where part of the batch succeeded before offsets were committed.

### 9.2. enable.auto.commit

To let the Spring Kafka listener container manage commits, configure:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
~~~

Do not rely on timer-based auto-commit if you want offset control tied to batch processing results. Committing Kafka offsets and committing a database are two separate operations; they do not automatically form a single atomic transaction.

## 10. Handling errors on a single record in a batch

One challenge with batch listeners is identifying which record caused an error.

If the listener throws a standard exception without indicating the failed record, the error handler may have to process the entire batch under a fallback strategy. Whenever the failing element can be identified, explicitly report its index or record so Spring Kafka can handle it more accurately.

Spring Kafka provides `BatchListenerFailedException` to indicate the failing record in a batch.

Example:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "batchListenerContainerFactory"
)
public void listen(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record = records.get(index);

        try {
            billingService.process(record.value());
        } catch (Exception exception) {
            throw new BatchListenerFailedException(
                "Cannot process order event",
                exception,
                index
            );
        }
    }
}
~~~

With `DefaultErrorHandler`, this exception tells the handler which element in the batch failed. Depending on retry settings, recoverer, and Spring Kafka version, records preceding the failed element can be treated as processed while the failed record and remaining records are retried or recovered according to policy.

If the failed record is not identified, the error handler may retry the entire batch. This makes previously succeeded records eligible for redelivery. Consequently, business processing should be idempotent.

### 10.1. Configuring DefaultErrorHandler

Example handler with backoff:

~~~java
@Bean
public DefaultErrorHandler batchErrorHandler() {
    return new DefaultErrorHandler(
        new FixedBackOff(1_000L, 2L)
    );
}
~~~

Attach the handler to the factory:

~~~java
factory.setCommonErrorHandler(batchErrorHandler);
~~~

In production applications, declare the handler as a bean and inject it into the factory. When using a DLT, configure `DeadLetterPublishingRecoverer` to publish unrecoverable records to a dead-letter topic.

Verify serializers, DLT partitions, retention, and replay procedures. Do not assume every error in a batch is sent individually to the DLT unless the error handler is configured to identify the failing record.

### 10.2. Deserialization errors occur before the listener

If a key or value cannot be deserialized, the listener may never be invoked with that record. Consider `ErrorHandlingDeserializer` to turn deserialization failures into error information that the error handler can process.

Do not handle deserialization errors as ordinary business errors inside the loop when the record was never constructed. Deserializers, error handlers, and DLTs must be configured consistently.

## 11. Concurrency and partition assignment

The factory can create multiple consumers to process batches in parallel:

~~~java
factory.setConcurrency(3);
~~~

Each child container uses its own consumer. Within the same consumer group, a partition is assigned to at most one consumer at any given time.

Example for a topic with 6 partitions:

| Concurrency | Consumers | Distribution potential |
|---:|---:|---|
| 1 | 1 | One consumer receives the assigned partitions |
| 3 | 3 | Up to three consumers processing together |
| 6 | 6 | Potentially one consumer per partition |
| 8 | 8 | At least two consumers have no partitions if there are only 6 partitions |

If an application runs two instances, each with concurrency 3, the total number of consumers in the group is 6.

A batch listener does not allow a single partition to be processed concurrently by multiple consumers in the same group. Batching groups multiple records polled by one consumer; concurrency increases the number of consumers and partitions processed in parallel.

### 11.1. Concurrency is not batch size

These two settings control different factors:

- `concurrency`: number of child consumer containers.
- `max.poll.records`: limit on how many records one consumer receives in one poll.

For example, concurrency 3 and `max.poll.records` 100 can create up to three consumers, each receiving up to 100 records per poll. Total records per poll across the group could reach 300 if every consumer hits the limit, though there is no guarantee batches will always reach this number.

## 12. Batch processing time and max.poll.interval.ms

A batch listener processes the entire list on the consumer container thread. If processing takes too long, the interval between polls may exceed `max.poll.interval.ms`, causing the consumer to leave the group or trigger a rebalance.

For example, if a batch has 100 records and each takes 500 ms sequentially on average, total processing time can reach roughly 50 seconds, before counting database, network, and retry overhead.

If a listener takes too long:

- Reduce `max.poll.records`.
- Optimize database operations for batching.
- Reduce round trips to downstream services.
- Choose concurrency appropriate for partition count and resources.
- Increase `max.poll.interval.ms` when justified by metrics.
- Avoid unbounded waits inside the listener.

Increasing `max.poll.interval.ms` does not make processing faster. It only grants the consumer more time between polls; weigh the impact when a consumer genuinely hangs.

## 13. Transactions and idempotency in batch processing

A batch can contain many events that need to be written to a database. If the database transaction rolls back, all database operations in that transaction can be undone. However, Kafka offsets still have to be managed separately.

Risks:

- The database partially writes data, yet the listener fails before committing offsets.
- The batch is redelivered and already-written records are processed again.
- Offsets are committed while asynchronous work has not finished.
- A Kafka transaction and a database transaction do not automatically form a single distributed transaction.

To process safely:

- Design idempotent operations keyed by event ID or business key.
- Use unique constraints or an inbox table where appropriate.
- Execute batch database updates within an appropriate transaction.
- Acknowledge/commit after required business work completes.
- For Kafka-to-Kafka flows, consider Kafka transactions and sending offsets into the transaction.
- Monitor failed records and maintain a replay procedure.

Do not treat a batch listener as an exactly-once mechanism. Batching only changes how records are received and how the listener is invoked; delivery and transaction semantics still depend on consumer configuration, commits, producers, and business logic.

## 14. Testing a List<ConsumerRecord> listener

Integration tests should confirm the listener receives multiple records properly and metadata remains accurate.

Steps:

1. Start Kafka via EmbeddedKafka or Testcontainers.
2. Create a topic with a defined partition count.
3. Configure the batch listener factory with `setBatchListener(true)`.
4. Send multiple records with keys and values.
5. Wait for the listener to process the batch using a latch or Awaitility.
6. Verify record count, payloads, keys, topic, partitions, and offsets.
7. Test cases where a batch contains records from multiple partitions.
8. Test retries, single-element failures, and acknowledgments.

Example listener test probe:

~~~java
@Component
public class BatchListenerProbe {

    private final BlockingQueue<List<ConsumerRecord<String, OrderCreated>>>
        received = new LinkedBlockingQueue<>();

    @KafkaListener(
        id = "order-batch-test-listener",
        topics = "test.orders",
        groupId = "test-batch-group",
        containerFactory = "batchListenerContainerFactory"
    )
    public void listen(
            List<ConsumerRecord<String, OrderCreated>> records) {
        received.add(List.copyOf(records));
    }

    public List<ConsumerRecord<String, OrderCreated>> awaitBatch(
            Duration timeout) throws InterruptedException {

        return received.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

In the test, send multiple records and retrieve a batch from the probe:

~~~java
List<ConsumerRecord<String, OrderCreated>> batch =
    probe.awaitBatch(Duration.ofSeconds(10));

assertThat(batch).isNotNull();
assertThat(batch).isNotEmpty();
assertThat(batch)
    .allSatisfy(record ->
        assertThat(record.topic()).isEqualTo("test.orders")
    );
~~~

Do not assume a single poll will always return the exact number of records sent. The consumer may receive smaller batches due to timing, fetches, and poll limits. If a test must verify a specific set of records, wait and accumulate them across multiple listener invocations.

When asserting offsets, compare within the same partition. Offsets across two partitions cannot be compared as a single global sequence.

## 15. Common errors when using List<ConsumerRecord>

| Symptom | Possible cause | Resolution |
|---|---|---|
| Listener receives the wrong parameter type | Factory does not enable batch listener | Call `setBatchListener(true)` |
| Batch is always smaller than expected | Poll lacks enough records or fetch/poll limits apply | Check `max.poll.records`, fetch settings, and timing |
| Missing keys or metadata | Listener only accepts a payload list | Switch to `List<ConsumerRecord<K,V>>` |
| ClassCastException | Generic type mismatches deserializer | Verify key/value types and `ConsumerFactory` |
| Batch retried repeatedly | Exception does not pinpoint failed record | Use `BatchListenerFailedException` when index is known |
| Already-processed records reprocessed | Batch retry or incomplete commit | Design idempotency |
| Consumer rebalances | Batch processing exceeds `max.poll.interval.ms` | Shrink batch or optimize/increase timeout carefully |
| Batch spans multiple partitions | Consumer is assigned multiple partitions | Use each record's topic/partition/offset |
| Business ordering lost | Events for the same entity in different partitions or parallel processing | Use a stable key and control concurrency |
| NullPointerException | Keys/values can be null, especially tombstones | Check for null before processing |
| DLT misses expected records | Incompatible recoverer or serializer | Check error handler, DLT, and producer |

## 16. Complete practical walkthrough

Suppose Billing receives `OrderCreated` events and wants to write invoices in batches.

### Step 1: Declare the event

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {
}
~~~

### Step 2: Configure the consumer

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      max-poll-records: 100
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
        max.poll.interval.ms: 300000
~~~

### Step 3: Create the batch listener factory

~~~java
@Bean(name = "batchListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(3);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

### Step 4: Accept List<ConsumerRecord>

~~~java
@Service
public class BillingBatchListener {

    private final BillingService billingService;

    public BillingBatchListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service",
        containerFactory = "batchListenerContainerFactory"
    )
    public void listen(
            List<ConsumerRecord<String, OrderCreated>> records) {

        List<OrderCreated> events = records.stream()
            .map(ConsumerRecord::value)
            .filter(Objects::nonNull)
            .toList();

        billingService.processBatch(events);
    }
}
~~~

### Step 5: Monitor results

Monitor these metrics:

- Actual batch size.
- Processing duration per batch.
- Succeeded/failed record counts.
- Consumer lag per partition.
- Retry counts.
- Records routed to DLT.
- Time between consecutive polls.

~~~mermaid
flowchart TD
    A["Kafka Consumer poll"] --> B["Receive ConsumerRecords"]
    B --> C["Spring builds List<ConsumerRecord>"]
    C --> D["Batch listener"]
    D --> E["Read key/value/metadata"]
    E --> F["Process business batch"]
    F --> G{"Processed successfully?"}
    G -->|Yes| H["Container commits per AckMode"]
    G -->|No| I["Error handler / retry"]
    I --> J{"Retries exhausted?"}
    J -->|No| D
    J -->|Yes| K["Recover or DLT"]
~~~

## 17. Pre-production checklist for batch listeners

- [ ] Has the factory called `setBatchListener(true)`?
- [ ] Does the listener use the right `containerFactory`?
- [ ] Do key/value generics match the `ConsumerFactory` and deserializers?
- [ ] Is `List<ConsumerRecord<K,V>>` chosen when metadata is needed?
- [ ] Are null keys/values and tombstones checked?
- [ ] Is it understood that one batch can contain multiple partitions?
- [ ] Is there no assumption of global offset ordering across partitions?
- [ ] Does `max.poll.records` fit the processing time?
- [ ] Is `max.poll.interval.ms` sufficient for worst-case processing time?
- [ ] Is `AckMode` compatible with batch listeners?
- [ ] Is `enable.auto.commit` intentionally configured?
- [ ] Are single-record failures identified by index/record where possible?
- [ ] Are the error handler, retries, and DLT configured compatibly?
- [ ] Is business processing idempotent when a batch is redelivered?
- [ ] Does the listener avoid returning before asynchronous work completes?
- [ ] Have batch size, metadata, offsets, retries, and rebalances been tested?
- [ ] Are lag and processing duration monitored per partition?

## Conclusion

Accepting `List<ConsumerRecord<K, V>>` lets Spring Kafka invoke a listener once with multiple records returned from a single poll while retaining per-record metadata such as key, topic, partition, offset, timestamp, and headers. To use it, enable batch mode on `ConcurrentKafkaListenerContainerFactory` and specify the proper factory in `@KafkaListener`.

Batch listeners can increase throughput when batch processing fits, yet batch size is not fixed and a batch can contain records from multiple partitions. Choose `max.poll.records`, concurrency, and acknowledgment mode according to real processing duration; pinpoint failing records using `BatchListenerFailedException` when possible; and design idempotency and test commits/retries for reliable batch processing.
