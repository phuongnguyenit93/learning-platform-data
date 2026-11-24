# Enabling batchListener on the container factory

By default, Spring Kafka typically configures listeners to receive one record at a time. When a batch listener is enabled, a single `poll()` call from the Kafka consumer can be turned into a single listener invocation with multiple records. This reduces method-call overhead and fits scenarios where the application can process a group of events together, such as writing multiple database rows, calling bulk APIs, or aggregating data.

In Spring Kafka, batch mode is enabled on the listener container factory. The factory creates the container and consumers for `@KafkaListener` endpoints that use it. When a factory is configured for batching, the listener method must have a signature compatible with batched data, such as `List<OrderEvent>` or `List<ConsumerRecord<...>>`.

A batch listener does not automatically make business logic faster. The application still must choose an appropriate poll size, handle errors within a batch, manage offsets, and ensure records are processed in order within each partition. A large batch can increase throughput, yet it also increases memory usage, single-poll processing time, and the scope of records redelivered on failure.

## Learning objectives

After this lesson, you will be able to:

- Explain how a batch listener receives data per poll invocation.
- Enable batch mode using `setBatchListener(true)` on `ConcurrentKafkaListenerContainerFactory`.
- Configure a batch listener using Spring Boot properties.
- Write `@KafkaListener` methods accepting a `List` of payloads, `List<ConsumerRecord>`, or `ConsumerRecords`.
- Choose between a record listener and a batch listener based on business characteristics.
- Tune `max.poll.records`, fetch settings, concurrency, and `max.poll.interval.ms`.
- Understand `AckMode.BATCH`, `MANUAL`, and how offsets are committed after processing a batch.
- Handle whole-batch errors and errors at a specific record.
- Preserve per-partition ordering when a batch contains records from multiple partitions.
- Test batch conversion, partial failure, rebalance, and throughput.

## 1. How does a batch listener work?

The Kafka consumer calls `poll()` to fetch records from its assigned partitions. The result of a single poll is a collection of `ConsumerRecord` instances, which may contain records from multiple partitions. When the listener container runs in batch mode, Spring Kafka passes that collection as input to a single listener invocation.

Processing flow:

~~~text
Kafka topic
  Partition 0: P0-R1, P0-R2, P0-R3
  Partition 1: P1-R1, P1-R2
  Partition 2: P2-R1
          |
          v
KafkaConsumer.poll()
          |
          v
ConsumerRecords (one poll)
          |
          v
Batch listener container
          |
          v
@KafkaListener(List<Record> batch)
          |
          v
Process batch / bulk write / commit offsets
~~~

For example, the `orders` topic has three partitions. One poll may return three records from partition 0, two records from partition 1, and one record from partition 2. The listener receives six records in a single call if they appear in that poll result.

A batch does not necessarily have the exact number of records the application expects. A poll can return fewer records than the configured limit if data is not yet available, fetch conditions have not been met, or other fetch/poll limits apply.

### Batch listener vs. producer batching

These mechanisms are often confused:

| Mechanism | Active side | Purpose |
|---|---|---|
| Producer batching | Producer | Groups records before sending to the broker, reducing request count |
| Consumer batch listener | Consumer / Spring listener container | Delivers multiple records from one poll into one listener invocation |
| Database batch write | Application and database | Combines multiple write operations to reduce round trips |

A producer can batch records even when the consumer processes one record at a time. Conversely, a consumer can receive batches even if the producer has no special batching configuration. These are three separate optimization layers.

## 2. Enabling batchListener via the container factory

The most common approach is to create a dedicated `ConcurrentKafkaListenerContainerFactory` and call `setBatchListener(true)`.

Example:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        // Enable batch listener for endpoints using this factory.
        factory.setBatchListener(true);

        // Create three child consumers within the same listener container.
        factory.setConcurrency(3);

        // Commit batch offsets after the listener processes successfully.
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.BATCH
        );

        return factory;
    }
}
~~~

Key points:

- `setConsumerFactory()` provides bootstrap servers, deserializers, and consumer properties.
- `setBatchListener(true)` instructs the container to invoke the listener in batch mode.
- `setConcurrency(3)` creates up to three child consumers for the endpoint.
- `AckMode.BATCH` commits progress for the records in the poll after the listener processes them successfully.

`AckMode.BATCH` is the typical choice for batch listeners. `AckMode.RECORD` is unsuitable for batch listeners because the listener processes the entire collection in one call and does not return an individual success result per method invocation.

### Attaching the factory to @KafkaListener

The listener must reference the exact factory name:

~~~java
@Component
public class OrderBatchListener {

    @KafkaListener(
        id = "orders-batch-listener",
        topics = "orders",
        groupId = "order-batch-service",
        containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void onOrders(List<OrderEvent> events) {
        orderService.processBatch(events);
    }
}
~~~

If `containerFactory` is omitted, Spring Kafka uses the default factory named `kafkaListenerContainerFactory`. Therefore, merely creating a batch factory does not make every listener use it automatically; each endpoint must reference the proper factory, or the application must configure the default factory in batch mode.

An application can contain both record listeners and batch listeners. Creating two separate factories ensures each endpoint gets the appropriate signature and behavior.

## 3. Enabling batch mode via Spring Boot configuration

If you use Spring Boot's auto-configured factory, you can select the listener type via properties:

~~~yaml
spring:
  kafka:
    listener:
      type: batch
      ack-mode: batch
      concurrency: 3
    consumer:
      max-poll-records: 200
~~~

Meaning:

- `listener.type=batch`: configures Boot's auto-configured listener container factory in batch mode.
- `listener.ack-mode=batch`: commits offsets per batch after successful listener processing.
- `listener.concurrency=3`: creates three child consumers for the listener container.
- `consumer.max-poll-records=200`: limits the maximum number of records returned by the consumer in one poll.

This configuration applies to Spring Boot's auto-configured factory. If the application manually creates a new factory without using Boot's configurer, these properties may not be applied automatically to that factory. For custom factories, configure `setBatchListener(true)`, `setConcurrency()`, and `ContainerProperties` directly.

### Enable batching only for listeners that need it

If an application has both single-record listeners and batch listeners, do not switch the default factory to batch while leaving existing methods with single-record signatures.

Example structure:

~~~text
recordKafkaListenerContainerFactory
    -> @KafkaListener accepting OrderEvent

batchKafkaListenerContainerFactory
    -> @KafkaListener accepting List<OrderEvent>
~~~

Each listener specifies the matching `containerFactory`. This avoids adapter errors caused by a method signature incompatible with the listener container type.

## 4. Supported parameter types for batch listeners

A batch listener can accept converted payloads or raw Kafka records. Choose the parameter type based on your metadata needs.

### Accepting a List of payloads

If you only need business data, accepting `List<OrderEvent>` is the simplest approach:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

The container converts each record's value into `OrderEvent` before invoking the listener. This fits when per-record offset, partition, or native headers are not needed.

### Accepting List<ConsumerRecord>

If you need per-record metadata, accept `ConsumerRecord`:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-audit-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records) {

    for (ConsumerRecord<String, OrderEvent> record : records) {
        log.info(
            "topic={}, partition={}, offset={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key()
        );

        orderService.process(record.value());
    }
}
~~~

Each element retains topic, partition, offset, key, timestamp, headers, and the deserialized value. This option is useful for auditing, partition-level processing, or batches requiring fine-grained offset management.

### Accepting ConsumerRecords

A batch listener can also accept `ConsumerRecords` directly:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-raw-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
        ConsumerRecords<String, OrderEvent> records) {

    for (TopicPartition partition : records.partitions()) {
        List<ConsumerRecord<String, OrderEvent>> partitionRecords =
                records.records(partition);

        orderService.processPartitionBatch(partition, partitionRecords);
    }
}
~~~

`ConsumerRecords` provides access to records grouped by `TopicPartition`. This fits when logic needs to group by partition while keeping native metadata.

### Accepting Spring Messages in a batch

If you want to use Spring Message headers, you can configure `BatchMessagingMessageConverter` and accept a list of `Message` or a payload list depending on converter type and method signature.

~~~java
@Bean
public BatchMessagingMessageConverter batchMessageConverter() {
    return new BatchMessagingMessageConverter();
}
~~~

Attach the converter to the factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
        jsonBatchListenerFactory(
                ConsumerFactory<String, String> consumerFactory,
                BatchMessagingMessageConverter batchMessageConverter) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setBatchMessageConverter(batchMessageConverter);

    return factory;
}
~~~

When per-record metadata is needed, check the batch headers provided by the converter, such as `KafkaHeaders.BATCH_CONVERTED_HEADERS`. Do not assume a single Spring Message header accurately represents all metadata across every record in the batch.

For use cases needing native headers, duplicate header names, or exact per-record offsets, `List<ConsumerRecord<...>>` is usually easier to control.

## 5. Handling headers in a batch listener

In a record listener, headers such as received topic, partition, key, and offset are typically single values. In a batch listener, the corresponding headers can be lists of values matching the order of records.

Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
        @Payload List<OrderEvent> events,
        @Header(KafkaHeaders.RECEIVED_KEY) List<String> keys,
        @Header(KafkaHeaders.RECEIVED_PARTITION) List<Integer> partitions,
        @Header(KafkaHeaders.OFFSET) List<Long> offsets) {

    for (int i = 0; i < events.size(); i++) {
        orderService.process(
                events.get(i),
                keys.get(i),
                partitions.get(i),
                offsets.get(i)
        );
    }
}
~~~

Metadata lists must align index-for-index with the payload list produced by the converter. If you need tighter control, accept `List<ConsumerRecord>` to avoid manually keeping multiple parallel lists in sync.

Headers can be null if a record has no key or the producer did not send custom headers. For optional headers, use nullable types or check values before processing.

## 6. Tuning batch size with max.poll.records

`max.poll.records` caps the maximum number of records the Kafka consumer returns in a single poll. It is an important parameter when enabling batch listeners.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
~~~

If sufficient data is available and fetch limits permit, a single poll can return up to 200 records. The consumer does not guarantee it will always return exactly 200 records.

Factors affecting actual batch size:

- Number of records currently available on assigned partitions.
- `max.poll.records`.
- `fetch.min.bytes` and `fetch.max.wait.ms`.
- `fetch.max.bytes` and `max.partition.fetch.bytes`.
- Average record size.
- Producer rate and broker state.

### Fetch properties vs. max.poll.records

| Property | Role |
|---|---|
| max.poll.records | Limits the number of records returned to the application in one poll |
| fetch.min.bytes | Minimum amount of data the consumer wants the broker to accumulate before returning a fetch, when possible |
| fetch.max.wait.ms | Time the broker waits to reach fetch.min.bytes before sending the response |
| fetch.max.bytes | Limits total fetch response size the consumer wishes to receive |
| max.partition.fetch.bytes | Limits fetched data per partition in a single response |

Fetch properties affect byte volume and when the broker returns data. `max.poll.records` limits how many records a poll returns to the application. Do not use them interchangeably.

Starter configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
      properties:
        "[fetch.min.bytes]": 16384
        "[fetch.max.wait.ms]": 100
        "[max.partition.fetch.bytes]": 1048576
~~~

Values must be tuned according to message size, throughput, latency, and memory. When records are large, even a batch with a small record count can consume significant memory.

## 7. Concurrency and partition count

Concurrency creates multiple child consumers within a listener container. Each consumer is assigned one or more partitions by the Kafka group assignor.

Example of the `orders` topic with six partitions and concurrency set to three:

~~~text
orders:
P0  P1  P2  P3  P4  P5

Consumer 1: P0, P1
Consumer 2: P2, P3
Consumer 3: P4, P5
~~~

Each consumer polls and invokes the listener independently. Thus, within one application instance, up to three batch listener invocations can run concurrently, each processing the batch from its respective consumer.

Rules of thumb:

- The number of child consumers that can actively read a topic cannot exceed that topic's partition count.
- If concurrency exceeds the partition count, some consumers receive no partitions.
- If concurrency is lower than the partition count, one consumer may read from multiple partitions.
- Total group consumer count must be calculated as application replicas multiplied by per-replica concurrency.
- Concurrency does not create additional partitions and does not guarantee linear throughput scaling.

If a batch listener performs database bulk writes, choose concurrency based on connection pool size and database capacity. Creating more consumers than downstream can handle only increases queueing, lock contention, and processing time.

## 8. Batch listeners and ordering

A single batch can contain records from multiple partitions. Kafka only guarantees offset ordering within each partition; there is no global ordering across partitions.

Example:

~~~text
Batch from one poll:

Partition 0: offset 10, 11, 12
Partition 1: offset 20, 21
Partition 2: offset 30

No global ordering:
P0-10 < P0-11 < P0-12
P1-20 < P1-21
P2-30 is independent of the other two partitions
~~~

If a listener receives `List<OrderEvent>`, do not infer ordering between two events from different partitions based on their list positions. If business logic requires per-partition ordering, group records by `TopicPartition` and process each group by offset.

Example:

~~~java
public void processPartitionBatch(
        TopicPartition partition,
        List<ConsumerRecord<String, OrderEvent>> records) {

    records.stream()
            .sorted(Comparator.comparingLong(ConsumerRecord::offset))
            .forEach(record ->
                    orderService.process(record.value()));
}
~~~

Within a single poll, `ConsumerRecords` already preserves records per partition; the sort example makes the offset-ordering requirement explicit. If processing multiple partitions in parallel, each partition needs its own sequential processing stream.

Do not submit individual records from a batch to a multi-threaded executor if side effects for the same partition must remain ordered. A batch listener reduces invocation overhead, yet it does not automatically preserve completion order for asynchronous work spawned by the application.

## 9. AckMode and offset commits for batch listeners

With a batch listener, the listener processes the entire collection of records from one poll. `AckMode` must reflect the batch's acknowledgement boundary.

| AckMode | Meaning for batch listeners |
|---|---|
| BATCH | Commits offsets after the listener successfully processes the entire batch |
| MANUAL | Listener calls acknowledge(); the container manages commits along batch/poll boundaries |
| MANUAL_IMMEDIATE | Attempts to commit immediately when acknowledged on the consumer thread |
| RECORD | Not suitable for batch listeners |

Example configuring BATCH:

~~~java
factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.BATCH
);
~~~

With `BATCH`, if the listener returns normally, the container can commit progress for the records returned in that poll. If the listener throws an exception, the error handler decides retry/recovery and commits according to its configured policy.

Do not enable Kafka auto-commit alongside manual acknowledgement logic without a clear reason. The Spring Kafka listener container normally manages commits and disables auto-commit by default in container-created configurations.

### Manual acknowledgement for batches

You can accept `Acknowledgment`:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "manualBatchFactory"
)
public void onOrders(
        List<OrderEvent> events,
        Acknowledgment acknowledgment) {

    orderService.processBatch(events);

    // Acknowledge the batch after all records have been processed successfully.
    acknowledgment.acknowledge();
}
~~~

Factory using `MANUAL`:

~~~java
factory.setBatchListener(true);
factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.MANUAL
);
~~~

Call `acknowledge()` only after all required work is finished. If part of the batch has already been written to the database before a failure occurs later in the batch, the entire batch may be redelivered. Handlers must be idempotent to avoid duplicate side effects.

## 10. Whole-batch error handling

If a batch listener throws an ordinary exception, the container cannot tell with certainty which records in the batch succeeded. The error handler may retry the entire batch according to its configuration.

Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

If `processBatch()` successfully updates 80 records and fails on the 81st, a retry may re-run the entire batch. Therefore:

- Operations must be idempotent by `eventId`.
- The database can use a unique constraint or an inbox table.
- Do not commit offsets before error/recovery policies complete.
- Track retry counts and redelivered batches.

A batch failure does not necessarily mean zero records were processed. Side effects may have already occurred for part of the batch before the exception was thrown.

## 11. Identifying the failed record with BatchListenerFailedException

If the listener knows the index of the failed record in the batch, it can throw `BatchListenerFailedException` to inform `DefaultErrorHandler` of the failure position. The error handler can treat preceding records as completed, retry/recover the failed record, and proceed according to its configured strategy.

Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, OrderEvent> record = records.get(i);

        try {
            orderService.processIdempotently(record.value());
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                    "Cannot process record at batch index " + i,
                    ex,
                    i
            );
        }
    }
}
~~~

Configuring an error handler with retry backoff:

~~~java
@Bean
public DefaultErrorHandler batchErrorHandler() {
    return new DefaultErrorHandler(
            new FixedBackOff(1000L, 2L)
    );
}
~~~

Attach it to the factory:

~~~java
// Inject the DefaultErrorHandler bean into the factory creation method.
factory.setCommonErrorHandler(batchErrorHandler);
~~~

The example above illustrates bounded retries. Once retries are exhausted, recovery behavior depends on the configured recoverer. In production, clearly define whether a failed record is sent to a DLT, written to an error store, or halts processing for intervention. Do not assume retry exhaustion automatically routes records to a DLT without configuring an appropriate recoverer.

Check the exact constructors and behavior of `BatchListenerFailedException`/`DefaultErrorHandler` against your Spring Kafka version. This mechanism is especially useful when you want partial-batch handling without retrying already-completed records.

## 12. Batch listeners and dead-letter topics

You can combine `DefaultErrorHandler` with `DeadLetterPublishingRecoverer` to route failed records after retries are exhausted. General configuration example:

~~~java
@Bean
public DefaultErrorHandler batchDltErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1000L, 2L)
    );
}
~~~

Attach it to the factory:

~~~java
factory.setCommonErrorHandler(batchDltErrorHandler);
~~~

For a batch listener, if the exception specifies the failed record index via `BatchListenerFailedException`, the error handler can recover that record and continue with the remainder according to policy. If the failed record is not identified, the whole batch may be retried.

With the default resolver, records are typically sent to a topic with the `.DLT` suffix using the source partition number. Thus, the DLT topic needs at least as many partitions; if you want to route to another topic or partition, configure an explicit destination resolver. The DLT also needs serializers compatible with keys, values, and headers. When the recoverer publishes to a DLT, ensure the publish succeeds before the source record's offset is committed under the error handler's policy. Test DLT publish failures and behavior when the DLT broker is unavailable.

Sending a record to a DLT is a business decision: the record has been quarantined for later handling, not successfully processed. Monitoring the DLT and establishing a replay workflow are essential.

## 13. max.poll.interval.ms and batch processing time

The consumer must continue calling `poll()` within `max.poll.interval.ms`. If a listener takes too long to process a batch, the consumer can exceed this interval, be treated as stalled, and leave the group, triggering a rebalance.

Example:

~~~text
max.poll.interval.ms = 300000 (5 minutes)
Batch has 200 records
Average processing time = 2 seconds/record
Estimated sequential total = 400 seconds

Result:
  Batch processing exceeds 5 minutes
  Consumer may leave the group
  Rebalance occurs and records may be redelivered
~~~

This is an illustrative calculation; actual duration depends on latency distribution, batch operations, and parallelism. If a batch takes too long to process, consider:

- Reducing `max.poll.records` to shrink the work per poll.
- Optimizing bulk operations to shorten per-batch processing time.
- Increasing `max.poll.interval.ms` if long processing times are intentional.
- Using concurrency across partitions.
- Splitting a business batch into smaller chunks while committing only when offsets are safe.
- Avoiding arbitrary offloading to an executor without managing acknowledgements and ordering.

Increasing `max.poll.interval.ms` does not make the system faster; it only extends the time a consumer is allowed to process between polls. Monitor rebalances, lag, and actual listener duration.

## 14. Memory and backpressure

Large batches can consume substantial heap because the consumer holds many records, deserialized payloads, and temporary structures during processing. If payloads are large or the listener creates extra object copies, memory consumption rises noticeably.

Consider:

- `max.poll.records`.
- Average message size and size distribution.
- Number of partitions assigned per consumer.
- Concurrency and how many batches can be processed simultaneously.
- Temporary data created during JSON conversion or database batching.
- Downstream connection pools and concurrency limits.

A rough estimate:

~~~text
Memory per batch
  ~= number of records in batch
     x average deserialized object size
     x object/collection overhead factor
~~~

This is only a directional estimate; actual heap usage also depends on JVM object layout, serializers, payloads, headers, and data copies.

If large batches inflate heap usage or cause long GC pauses, reduce `max.poll.records`, limit concurrency, or process in chunks. Do not accumulate all records in a long-lived list inside a service.

## 15. Batch listeners and database bulk operations

A practical benefit of a batch listener is grouping multiple records for bulk database writes.

Example:

~~~java
@Service
public class OrderBatchService {

    private final OrderRepository repository;

    public void processBatch(List<OrderEvent> events) {
        List<OrderEntity> entities = events.stream()
                .map(this::toEntity)
                .toList();

        repository.saveAll(entities);
    }

    private OrderEntity toEntity(OrderEvent event) {
        return new OrderEntity(
                event.orderId(),
                event.status(),
                event.version()
        );
    }
}
~~~

Bulk operations can reduce round trips and increase throughput. However, `saveAll()` does not always produce a single bulk SQL statement; actual behavior depends on the JPA provider, JDBC batching, entity mappings, and transaction setup.

To achieve real database batching efficiency, consider:

- JDBC batch size.
- Transaction boundaries.
- Flushing/clearing the persistence context for large batches.
- Unique constraints on `eventId`.
- Handling duplicates when Kafka redelivers a batch.
- Partial failures and full-transaction rollbacks.

If the entire batch is written inside a single database transaction and that transaction rolls back, none of the records in the transaction are committed. If each record runs in its own transaction, part of the batch may succeed before a later record fails. These two approaches have different retry boundaries.

### Batch transaction example

~~~java
@Transactional
public void processBatch(List<OrderEvent> events) {
    for (OrderEvent event : events) {
        processIdempotently(event);
    }
}
~~~

When an exception escapes the method and rolls back the transaction, updates inside that transaction roll back according to the transaction manager configuration. Kafka offsets are committed only after the listener completes under the chosen `AckMode`; the database and Kafka offsets remain two separate systems unless an appropriate coordination mechanism is used.

## 16. Batch conversion and payload types

If the consumer deserializer already produces objects, the batch listener can accept `List<OrderEvent>`. If the deserializer returns `String`, a converter must transform each payload into the target type.

Common combinations:

| Deserializer | Listener | Conversion mechanism |
|---|---|---|
| JsonDeserializer<OrderEvent> | List<OrderEvent> | Deserializer creates objects; batch converter wraps the list |
| StringDeserializer | List<OrderEvent> | Needs a compatible JSON message converter for each record |
| StringDeserializer | List<String> | Receives raw JSON Strings and parses in the service |
| ByteArrayDeserializer | List<byte[]> | Application handles bytes directly or uses a corresponding converter |
| Any deserializer | List<ConsumerRecord<K,V>> | Keeps record metadata and deserialized values |

When using `StringJsonMessageConverter` or a custom converter, configure the matching batch converter. `BatchMessagingMessageConverter` can delegate single-record conversion to a `RecordMessageConverter`.

Example:

~~~java
@Bean
public BatchMessagingMessageConverter batchJsonConverter() {
    return new BatchMessagingMessageConverter(
            new StringJsonMessageConverter()
    );
}
~~~

Attach it to the factory with `setBatchMessageConverter()`. Check the constructor/API for your Spring Kafka version; if no JSON conversion is needed, the default `BatchMessagingMessageConverter` may suffice.

Do not configure both `JsonDeserializer` and `StringJsonMessageConverter` to convert the same payload path. Choose a single place responsible for JSON parsing to avoid double conversion or type errors.

## 17. Mixing record listeners and batch listeners in one application

A service may need one listener consuming individual records and another consuming batches. Create two separate factories:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        recordListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(false);
    factory.setConcurrency(2);

    return factory;
}

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(3);

    return factory;
}
~~~

Both listeners select their factories:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-notification",
    containerFactory = "recordListenerFactory"
)
public void notifyOne(OrderEvent event) {
    notificationService.send(event);
}

@KafkaListener(
    topics = "orders",
    groupId = "order-analytics",
    containerFactory = "batchListenerFactory"
)
public void aggregate(List<OrderEvent> events) {
    analyticsService.aggregate(events);
}
~~~

The two listeners above use different group IDs so each group reads the entire topic independently. If they shared the same group ID and topic subscription, the two endpoints would split partitions between them; choose group IDs based on processing goals.

If using the Spring Boot global property `listener.type=batch`, the default factory may be configured as a batch factory. Dedicated record factories must explicitly call `setBatchListener(false)` or be created with the appropriate configuration.

## 18. Testing batch listeners

Tests should confirm that the listener genuinely receives multiple records in one invocation and handles commits and retries properly.

Useful test scenarios:

- Create a multi-partition topic, send a group of records, and verify the batch listener receives a `List`.
- Verify a batch can contain records from multiple partitions.
- Verify `List<ConsumerRecord>` retains topic, partition, offset, key, and headers.
- Verify `max.poll.records` caps the maximum records per poll.
- Send fewer records than `max.poll.records` and verify the listener does not wait for a fixed batch size.
- Verify concurrency creates multiple child consumers with proper partition assignment.
- Cause one record in the batch to fail; verify either the whole batch retries or only the failed record retries via `BatchListenerFailedException`.
- Verify DLT publishing succeeds before the offset is recovered/committed per configuration.
- Trigger a database transaction rollback and verify the batch can be redelivered.
- Simulate slow batch processing exceeding `max.poll.interval.ms` and observe the rebalance.
- Verify records in the same partition are still processed in offset order.
- Verify record and batch listeners use separate factories without signature mismatches.
- Measure throughput, latency, heap, and GC while varying `max.poll.records`.

To test that a single listener invocation receives multiple records, send enough data and use a latch/synchronization condition with a timeout. Do not rely on a short sleep and conclude a batch listener only ever receives one record; the broker may return a poll before subsequent records arrive.

## 19. Common mistakes

**Forgetting to call setBatchListener(true).** The listener method accepts a `List`, yet the factory still runs in record mode. Configure the factory properly or use Boot's `listener.type=batch`.

**Using a single-record signature with a batch factory.** The container passes a batch, but the method signature is incompatible. Use a separate record factory or change the method signature.

**Thinking max.poll.records is a fixed batch size.** It is an upper bound, not a guaranteed record count per poll. Actual batches can be smaller.

**Confusing producer batch.size with consumer max.poll.records.** Producer batching and consumer poll batching are two distinct mechanisms.

**Setting concurrency higher than the partition count.** Excess consumers receive no partitions and do not improve throughput.

**Processing a whole batch for too long.** It can exceed `max.poll.interval.ms` and trigger rebalances. Reduce batch size, optimize processing, or adjust the interval.

**Committing offsets when only part of the batch is processed.** Unfinished records may be skipped. Only commit the batch upon completion or use a controlled error-handling/partial-batch strategy.

**Lacking idempotency when a batch is retried.** Records already written to the database before an error may be reprocessed. Use `eventId` and a unique constraint or inbox table.

**Assuming global ordering within a batch.** A batch can span multiple partitions; ordering exists only within each partition.

**Not configuring an error handler for partial failure.** The error handler cannot tell which record failed and may retry the entire batch. Use `BatchListenerFailedException` when the index is known and configure a suitable recoverer.

**Using a converter incompatible with the deserializer.** `StringJsonMessageConverter` expects String/byte data; do not blindly pair it with a `JsonDeserializer` that already produces objects.

## 20. Checklist for enabling batchListener

- [ ] Confirmed the use case can process multiple records together.
- [ ] Factory calls `setBatchListener(true)`.
- [ ] `@KafkaListener` references the right `containerFactory`.
- [ ] Method signature matches: `List` payload, `List<ConsumerRecord>`, or `ConsumerRecords`.
- [ ] `AckMode` fits batching; do not use `RECORD` for batch listeners.
- [ ] `max.poll.records` matches payload size and processing time.
- [ ] `max.poll.interval.ms` accommodates batch processing duration.
- [ ] Concurrency matches partition count and downstream capacity.
- [ ] Multi-partition batches are processed per partition when ordering is required.
- [ ] Listener is idempotent to tolerate batch retries.
- [ ] Error handler covers both whole-batch errors and partial failures.
- [ ] DLT/recoverer is explicitly configured if failed records need isolation.
- [ ] Batch converter is compatible with the deserializer and payload type.
- [ ] Heap, GC, consumer lag, and listener duration are monitored.
- [ ] Integration tests cover multi-partition batches, retries, DLT, rebalances, and shutdown.

## Conclusion

Enable batch listeners on the container factory with `setBatchListener(true)` so Spring Kafka delivers all records from a single poll into a single `@KafkaListener` invocation. You can accept a `List` of payloads for simple business logic or `List<ConsumerRecord>` when per-record metadata is needed. Configure `max.poll.records`, concurrency, `AckMode`, and `max.poll.interval.ms` based on actual processing capacity. Batching reduces overhead and supports bulk operations, yet it widens the failure blast radius, increases memory usage, and requires careful partial-failure handling. Always maintain idempotency, per-partition ordering, and thorough commit/retry testing before deploying batch listeners to production.

