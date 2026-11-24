# Record listener and batch listener

Spring Kafka supports two primary ways for a listener to receive data from Kafka: a record listener processes one record per method invocation, whereas a batch listener processes a group of records returned from a single poll. Both run on the listener container and share the same consumer foundation, but they differ in how data is delivered to business code, how offsets are acknowledged, and how errors are handled.

A record listener fits when each event needs independent processing, straightforward retries, and per-record error control. A batch listener fits when multiple events can be processed together—for example, bulk database writes, bulk APIs, or computing over a dataset. Batching can reduce per-record overhead and increase throughput, at the cost of added complexity around memory, latency, acknowledgement, and failed-record handling.

This lesson belongs to the **Batches and throughput** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, while covering serialization, retries, dead letters, transactions, concurrency, and testing to operate reliable messaging pipelines.

## 1. How do record listeners and batch listeners differ?

A record listener receives one record per listener method invocation. The consumer may still fetch multiple records in a single poll, but the listener container passes them to the method one by one.

A batch listener receives a collection of records in a single invocation. This collection typically corresponds to the records returned by the Kafka consumer from a single `poll()`. Batch size varies with traffic, partition assignment, fetch limits, and `max.poll.records`.

| Criterion | Record listener | Batch listener |
| --- | --- | --- |
| Input data | A single record | A list/collection of records |
| Listener invocations | Once per record | Once per batch |
| Error handling | Easy to identify the failed record | Must identify the failed record in the batch or retry the whole batch |
| Acknowledgement | Can acknowledge per record or per batch depending on AckMode | Typically acknowledges after processing the batch |
| Throughput | Suitable for per-event processing | Can be higher when processing in bulk |
| Latency | Can process each record immediately | May wait for sufficient data or the polled batch |
| Memory | Typically lower per invocation | Can be higher due to holding multiple records at once |
| Use case | Sending emails, updating a single aggregate, event-driven business calls | Bulk inserts, batch updates, bulk APIs, set-based data processing |

Both modes read data by partition and offset. A batch listener does not create topic-wide ordering; records from multiple partitions can appear in the same batch, while ordering is guaranteed only within each individual partition.

~~~mermaid
flowchart TD
    A[Kafka consumer poll] --> B[Records from assigned partitions]
    B --> C{Listener mode}
    C -->|Record| D[Container invokes listener for each record]
    C -->|Batch| E[Container passes entire batch in one call]
    D --> F[Processing and acknowledgement]
    E --> F
    F --> G[Commit offsets according to AckMode]
~~~

## 2. Record listener with @KafkaListener

A record listener is the default mode of the listener container. The method can receive the deserialized payload:

~~~java
@Component
public class OrderEventListener {

    @KafkaListener(
        id = "orderRecordListener",
        topics = "order-events",
        groupId = "order-service",
        containerFactory = "recordListenerFactory"
    )
    public void onOrderEvent(OrderEvent event) {
        orderService.handle(event);
    }
}
~~~

Spring Kafka retrieves the record from the consumer, converts the value to OrderEvent using the configured deserializer/converter, and then invokes the listener method.

If you need metadata such as topic, partition, offset, key, or timestamp, receive `ConsumerRecord` directly:

~~~java
@KafkaListener(
    id = "orderRecordListener",
    topics = "order-events",
    groupId = "order-service",
    containerFactory = "recordListenerFactory"
)
public void onOrderEvent(
        ConsumerRecord<String, OrderEvent> record) {

    log.info(
        "topic={} partition={} offset={} key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );

    orderService.handle(record.value());
}
~~~

Receiving ConsumerRecord is useful when you need auditing, tracing, or metadata-dependent processing. If you only need the payload, receiving OrderEvent keeps the listener signature cleaner.

### 2.1. Configuring a record listener container factory

You can declare a dedicated factory for record listeners:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            recordListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(false);
        return factory;
    }
}
~~~

`setBatchListener(false)` makes it explicit that this factory uses a record listener. This is also the default behavior in standard configurations, though declaring it explicitly helps distinguish it from a batch factory.

A single default factory can be shared across multiple record listeners if they share the same ConsumerFactory, converter, and container policy. When a group of listeners needs a different AckMode or concurrency, you can create a separate factory.

## 3. Batch listener with @KafkaListener

To make a listener receive an entire batch, configure the container factory with `setBatchListener(true)`:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

A listener using this factory can receive a list of ConsumerRecord:

~~~java
@Component
public class OrderBatchListener {

    @KafkaListener(
        id = "orderBatchListener",
        topics = "order-events",
        groupId = "order-batch-service",
        containerFactory = "batchListenerFactory"
    )
    public void onOrders(
            List<ConsumerRecord<String, OrderEvent>> records) {

        orderService.handleBatch(records);
    }
}
~~~

A single listener invocation receives the set of records returned by the consumer poll. The batch can contain records from multiple partitions assigned to that consumer. It does not necessarily contain `max.poll.records` items; if the topic has little traffic or the fetch returns fewer records, the batch can be smaller.

Use `List<ConsumerRecord<K,V>>` when you need access to per-record metadata. If you only need payloads, you can use `List<OrderEvent>` when the message converter is configured for batch conversion.

## 4. Should a batch listener receive payloads or ConsumerRecord?

Two signatures are commonly used:

**Receiving ConsumerRecord:**

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-service",
    containerFactory = "batchListenerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records) {

    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.validate(record.value());
    }

    orderService.persistBatch(records);
}
~~~

The advantage is that every element includes the full topic, partition, offset, key, timestamp, and headers. This option is easier to control when handling errors per record or when observability is needed.

**Receiving converted payloads:**

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-service",
    containerFactory = "batchListenerFactory"
)
public void onOrders(List<OrderEvent> events) {
    orderService.persistEvents(events);
}
~~~

This style requires appropriate batch message conversion. Spring Kafka provides `BatchMessagingMessageConverter` to convert a batch of ConsumerRecords into a Spring Message whose payload is a list. The converter can work with a record converter to deserialize/convert each element.

If you need metadata alongside payloads, you can receive `List<Message<?>>` or configure an appropriate converter/header mapping. Choose the signature your application actually needs; avoid converting every record into a Message object if you only process payloads.

## 5. Configuring BatchMessagingMessageConverter

When a batch listener receives a payload list and needs metadata/header conversion, you can configure a batch converter:

~~~java
@Bean
public BatchMessageConverter batchMessageConverter() {
    return new BatchMessagingMessageConverter();
}
~~~

Attach the converter to the factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            BatchMessageConverter batchMessageConverter) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setBatchMessageConverter(batchMessageConverter);
    return factory;
}
~~~

`BatchMessagingMessageConverter` can use an inner record converter to convert each record. If the application already uses a JSON converter or custom converter, configure it according to the API of your Spring Kafka version.

If the listener receives `List<ConsumerRecord<K,V>>`, you may not need to convert each record into a Spring Message. Using ConsumerRecord preserves native Kafka metadata and avoids an extra conversion layer.

## 6. How is a batch created from poll?

The Kafka consumer calls `poll()` to fetch records from assigned partitions. A single poll can return multiple records from one or more partitions. A batch listener receives this set of records in a single invocation.

Several factors affect batch size:

| Setting / factor | Impact |
| --- | --- |
| `max.poll.records` | Limits the maximum number of records returned in a single poll. |
| `fetch.max.bytes` | Limits the total data fetched in a single request per client configuration. |
| `max.partition.fetch.bytes` | Limits the data fetched per partition in a single request. |
| Number of assigned partitions | More partitions can contribute records to the same poll. |
| Producer traffic | With little new data, batches are typically smaller. |
| Poll timing and network | Affects when and how much data is received. |

`max.poll.records` limits the number of records returned to the application in one poll; it is not a byte size for the batch and does not replace fetch size settings. The Kafka client may prefetch data into an internal buffer and then return records to the application up to the poll limit.

Configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
      properties:
        max.poll.interval.ms: 300000
        fetch.max.bytes: 52428800
        max.partition.fetch.bytes: 1048576
~~~

These numbers are illustrative values only. Measure payload size, throughput, partition count, and processing time to choose suitable limits. Increasing batch size does not automatically increase throughput if the bottleneck is in the database, network, or business logic.

## 7. A batch can contain records from multiple partitions

A single consumer can be assigned multiple partitions. Therefore, one poll batch can contain records from multiple partitions of the same topic or even multiple topics if the subscription allows.

Illustrative example:

~~~text
Consumer A is assigned:
  order-events-0
  order-events-1
  payment-events-0

One poll:
  order-events-0: offsets 10, 11
  order-events-1: offsets 20, 21, 22
  payment-events-0: offsets 5, 6
  --------------------------------
  Total: 7 records in batch
~~~

Record ordering within each partition is still preserved by offset. There is no global business ordering between records from partition 0 and partition 1. If a batch listener processes all records in a loop, do not assume records from one partition will always appear before records from another.

If sequential processing per key is required, use a key so events for the same entity land in the same partition, and avoid asynchronous dispatching that breaks ordering.

## 8. Acknowledgement and offset commit with record listeners

The container manages offset commits based on `AckMode`. For record listeners, common modes include:

| AckMode | General behavior |
| --- | --- |
| `RECORD` | Commits after the listener finishes processing each individual record. |
| `BATCH` | Commits after all records from the current poll have been processed. |
| `TIME` | Commits on a time interval when processed records exist. |
| `COUNT` | Commits once a configured number of processed records is reached. |
| `COUNT_TIME` | Combines record-count and time thresholds. |
| `MANUAL` | Listener calls acknowledge; commits follow the container's batch commit flow. |
| `MANUAL_IMMEDIATE` | Commits immediately when acknowledge is called on the consumer thread; behavior differs if called from another thread. |

These modes apply when Kafka consumer auto-commit is disabled so the Spring container manages acknowledgements. Spring Kafka generally recommends container-managed commits rather than enabling auto-commit in listener applications.

For record listeners, `AckMode.RECORD` fits when you want commit progress closely tracking each record. `BATCH` can reduce commit frequency, but if the consumer stops mid-batch, already-processed records after the committed offset may be re-read.

Do not treat an offset commit as proof that every action outside Kafka has durably completed. If a listener updates a database and then commits offsets, design appropriate transaction/outbox/idempotency mechanisms to handle crashes between the two operations.

## 9. Acknowledgement and offset commit with batch listeners

A batch listener receives a collection of records as a single listener invocation unit. `AckMode.RECORD` is not suitable for batch listeners because the container does not invoke the listener per record; use BATCH or manual modes according to the semantics of your Spring Kafka version.

With `AckMode.BATCH`, the container commits after the listener successfully processes the batch. This is a common choice when the entire batch is treated as one processing unit.

Example using manual acknowledgment:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-service",
    containerFactory = "batchListenerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records,
        Acknowledgment acknowledgment) {

    orderService.persistBatch(records);
    acknowledgment.acknowledge();
}
~~~

Only acknowledge after business processing has completed according to contract. If you acknowledge before the database commits, the application risks losing the chance to reprocess records on failure.

### 9.1. Partial batch acknowledgment

Since Spring Kafka 3.0.10, a batch listener can acknowledge part of a batch using `Acknowledgment.acknowledge(index)` under supported conditions. This mechanism requires `AckMode.MANUAL_IMMEDIATE` and must be called by the listener on the consumer thread. The index identifies the last successfully processed record in the batch.

Illustrative example:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-service",
    containerFactory = "manualBatchFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records,
        Acknowledgment acknowledgment) {

    for (int index = 0; index < records.size(); index++) {
        process(records.get(index));
        acknowledgment.acknowledge(index);
    }
}
~~~

The example above only illustrates the API; the factory configuration must set AckMode.MANUAL_IMMEDIATE and follow the version's requirements. Partial acknowledgement enforces monotonically increasing indexes and must not be called arbitrarily from another thread. Read the Javadoc for your version before adopting it, as this API has strict requirements.

If partial acknowledgment is not needed, processing the entire batch and calling acknowledge once is simpler and less error-prone.

## 10. Error handling in record listeners

With a record listener, an error during an invocation typically belongs to a specific record. A Spring Kafka error handler can retry the record, apply backoff, or route the record to a dead-letter topic.

Example configuring DefaultErrorHandler with DeadLetterPublishingRecoverer:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1000L, 2L)
    );
}
~~~

This configuration illustrates retrying with a one-second wait and a finite number of retries before the recoverer handles the record as configured. You must configure the DLT destination, producer template, and appropriate exception classification.

With a record listener, the error handler can seek/redeliver the failed record or move it to a DLT. Subsequent records in the same partition are typically not processed past the failed record while blocking retry holds partition progress.

Transient errors such as database timeouts can be retried. Invalid-data errors usually do not resolve on their own; classify them and route them to a DLT after a reasonable number of attempts.

## 11. Error handling in batch listeners

Batch listeners have an important difference: if the method throws an ordinary exception, the container does not necessarily know which element in the batch failed. Depending on the error handler and version, the entire batch may be retried or reprocessed.

If the listener can identify the failed record, it can throw `BatchListenerFailedException` with the failed index or ConsumerRecord. `DefaultErrorHandler` can use that information to treat records prior to the failed position as succeeded and retry/recover the failed record and remaining records according to policy.

Example:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-service",
    containerFactory = "batchListenerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderEvent> record = records.get(index);

        try {
            orderService.handle(record.value());
        }
        catch (Exception exception) {
            throw new BatchListenerFailedException(
                "Failed to process order event",
                exception,
                index
            );
        }
    }
}
~~~

The constructor signature and how the error handler processes it should be checked against your Spring Kafka version. The exception's purpose is to indicate the failed record's position in the batch so the container can apply progress and retries more accurately.

If a batch listener only throws a generic exception without identifying the failed record, the whole batch may have to be reprocessed. Therefore, business operations inside a batch should be idempotent or have a mechanism to detect already-processed events to avoid duplicate side effects.

### 11.1. Batch retry and DLT

When retries are exhausted, the recoverer can send failed records to a DLT. With batch listeners, you must understand which records are recovered and which are redelivered afterward. When the failed index is accurately identified, the error handler can commit the part before the failure and handle the remainder according to policy. If the position cannot be identified, the batch may be treated as a single failed unit.

Do not assume every batch is always routed intact into a single DLT record. Recovery behavior depends on the exception, batch error handling strategy, and recoverer configuration. If you need a separate DLT record per event, design and test record splitting explicitly.

## 12. Ordering when processing batches

A batch listener does not break offset ordering within each partition, but the application must be careful when processing a batch spanning multiple partitions.

A single poll batch can contain:

- Multiple consecutive records from partition 0.
- Multiple consecutive records from partition 1.
- Records from multiple topics if the subscription includes multiple topics.

Kafka does not guarantee ordering across partitions. If a listener processes a batch using a parallel stream or executor, completion order can also differ from the order in which the listener received the records.

Example to avoid when ordering is required:

~~~java
records.parallelStream()
    .forEach(record -> orderService.handle(record.value()));
~~~

This approach can run records from the same partition concurrently and complete out of offset order. If sequential processing per partition/key is needed, process sequentially or split the batch by partition and process each partition sequentially.

Batch processing should leverage bulk operations without violating business ordering constraints.

## 13. Concurrency and partition count

Listener container concurrency creates multiple consumers within the same group. With a batch listener, each consumer polls its own batches from its assigned partitions.

If a topic has six partitions and factory concurrency is three, the group can have three consumers, each receiving a subset of partitions. Each consumer processes batches from the partitions assigned to it.

Useful concurrency does not exceed the number of partitions assigned to the group. If there are two partitions but concurrency is eight, at most two consumers will have partitions to read from at any given time.

Increasing concurrency and increasing batch size are two different scaling dimensions:

- Concurrency increases the number of consumers that can process partitions in parallel.
- Batch size increases the number of records processed in a single invocation per consumer.

Both can increase throughput, but both also increase resource usage and pressure on dependencies. Measure database connection pools, heap, CPU, network, and listener latency before increasing them.

## 14. Optimizing throughput with batch listeners

A batch listener can improve throughput when fixed per-invocation overhead is high. For example, instead of inserting each record individually, the application groups multiple events and uses JDBC batching or a bulk API.

Some techniques:

- Use bulk inserts/updates instead of individual statements.
- Tune batch size according to payload size and database limits.
- Reduce unnecessary object conversions.
- Use appropriate serializers/deserializers and avoid oversized payloads.
- Monitor batch processing time and record count per batch.
- Limit concurrency to avoid overloading downstream systems.
- Choose a commit cadence aligned with replay tolerance.

Batch processing example:

~~~java
public void persistBatch(List<ConsumerRecord<String, OrderEvent>> records) {
    List<OrderEvent> events = records.stream()
        .map(ConsumerRecord::value)
        .toList();

    orderRepository.saveAll(events);
}
~~~

The example uses `Stream.toList()`, which requires Java 16 or later. If your project uses Java 8/11, you can use `Collectors.toList()`. Additionally, `saveAll` does not guarantee that every repository implementation performs an actual SQL bulk insert; inspect the generated SQL and actual transaction behavior.

The optimal batch size depends on the data. Batches that are too small fail to leverage bulk operations; batches that are too large increase memory usage, processing time, and the risk of exceeding the poll interval.

## 15. max.poll.interval.ms and batch processing time

The consumer must continue calling poll within the `max.poll.interval.ms` limit. If processing one batch takes too long before the next poll, the consumer may be considered stalled and leave the group, triggering a rebalance.

Example:

- max.poll.records = 500.
- One record takes 100 ms on average.
- Sequential processing of 500 records takes about 50 seconds, excluding database/network overhead.
- If max.poll.interval.ms is 30 seconds, the consumer risks exceeding the limit.

This is only an estimate; actual time depends on latency distribution, batching, retries, and runtime behavior. Measure p95/p99 processing time rather than just the average.

Remediation approaches:

- Reduce max.poll.records if batches are too large.
- Optimize bulk operations and the listener.
- Adjust max.poll.interval.ms appropriately if tasks legitimately take longer, while evaluating membership impact.
- Split work into steps that can finish within the poll limit.
- Avoid long retries/backoffs directly on the listener thread without accounting for the poll interval.

Increasing max.poll.interval.ms does not make processing faster; it only extends how long the consumer is allowed between polls before being treated as non-progressing.

## 16. When to choose a record listener vs. a batch listener?

| Requirement | Recommended choice | Reason |
| --- | --- | --- |
| Independent per-event processing | Record listener | Easy to reason about, retry, and observe per record. |
| Business calls requiring low latency | Record listener | No need to accumulate multiple records before processing. |
| Bulk insert/update | Batch listener | Leverages database batch APIs. |
| Windowed/batch data processing | Batch listener | A single invocation can process a collection of records. |
| Poison records needing clear isolation | Record listener or batch with failed-index handling | Easy to identify and recover failed records. |
| Many small events, high throughput | Can use batch listener | Reduces per-call overhead if downstream supports bulk operations. |
| Detailed Kafka metadata needed | Both | Record listener receives ConsumerRecord; batch receives List<ConsumerRecord>. |

Do not choose batching solely to increase throughput. If downstream does not support bulk operations or batching increases latency and memory too much, a record listener may be a better fit.

An application can use multiple container factories: a record factory for business flows needing per-event handling and a batch factory for analytics/import flows. Separating factories keeps ack policies, concurrency, and converters clear.

## 17. Testing record listeners and batch listeners

Integration tests with Embedded Kafka or Testcontainers help verify that the container factory, listener signature, conversion, offsets, and error handling work as expected.

### 17.1. Testing record listeners

- Send multiple records to the topic.
- Verify the listener is invoked per record.
- Verify payloads and metadata.
- Verify per-record exceptions/retries.
- Verify offset commits according to AckMode.

### 17.2. Testing batch listeners

- Configure the factory with `setBatchListener(true)`.
- Send multiple records before polling.
- Verify the listener receives a list with multiple elements when poll conditions allow.
- Verify records from multiple partitions and ordering within each partition.
- Verify batches smaller than max.poll.records.
- Verify failed index, retries, and DLT.
- Verify acknowledgments and commits when a batch succeeds or fails.

Do not assert that a fixed number of records will always arrive in a single batch. A poll may return fewer than the limit due to data arrival timing, partition assignment, fetches, and byte limits.

Tests should use a latch or Awaitility with a finite timeout. To verify a specific batch, control the producer to send before polling and configure the test consumer accordingly; avoid fixed sleeps because results depend on the scheduler and broker.

### 17.3. Performance testing

Benchmark record and batch listeners on the same dataset, partition count, consumer count, and dependencies. Measure:

- Records per second.
- Average and percentile batch sizes.
- Listener processing latency p50/p95/p99.
- Consumer lag.
- CPU, heap, GC, and network.
- Database throughput and connection usage.
- Retry/error/DLT rate.

Compare end-to-end throughput and latency. A batch listener with higher throughput but excessive p99 latency may fail to meet SLAs.

## 18. Common issues

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Listener receives single records despite wanting batches | Factory does not enable batch listener or listener uses the wrong factory | Check setBatchListener(true) and containerFactory |
| Batch listener fails to convert payload list | Method signature or converter mismatch | Check BatchMessageConverter and generic types |
| Batch is always smaller than max.poll.records | Poll does not guarantee returning the full limit | Check producer rate, partitions, fetch settings, and poll timing |
| Batch takes too long and triggers rebalance | Exceeded max.poll.interval.ms | Measure processing time, reduce batch size, or adjust interval |
| Retry reprocesses many records | Batch exception does not identify failed index | Use BatchListenerFailedException when the failed record is known |
| Offsets committed before processing finishes | Acknowledge/commit called too early | Only acknowledge after durable operations complete |
| Records in the same partition complete out of order | Using parallel stream/executor | Process sequentially or partition work by partition/key |
| Increasing batch size does not increase throughput | Bottleneck is downstream or in the network | Profile each layer, try bulk APIs, and inspect dependencies |
| DLT contains unexpected data | Batch recovery semantics untested | Check failed index, recoverer, and handler |
| Consumer rebalances frequently | Long batch processing, restarts, or poll interval | Check max.poll.interval.ms and container lifecycle |

## 19. Checklist for choosing and operating a listener mode

Before putting a listener into production, verify:

1. Record or batch mode matches latency and throughput requirements.
2. The listener uses the right container factory.
3. Batch listeners have `setBatchListener(true)` enabled.
4. Method signatures match payload, ConsumerRecord, or Message converter.
5. `max.poll.records` and fetch sizes are chosen based on payload/partitions.
6. AckMode fits record or batch semantics.
7. Acknowledge occurs only after durable business operations complete.
8. Batch error handling identifies the failed record when partial recovery is needed.
9. Retry/DLT does not lose records or break business ordering.
10. Processing time does not exceed `max.poll.interval.ms`.
11. Concurrency does not exceed actual needs or downstream capacity.
12. Integration tests and benchmarks measure throughput, latency, lag, retries, and DLT.

Record listeners and batch listeners use the same Kafka consumer yet create two distinct processing models. Record listeners stay simple when per-event processing and error isolation are needed; batch listeners leverage bulk operations to improve throughput when downstream supports them. Choosing well requires balancing latency, memory, commit semantics, retries, ordering, and poll time limits so the consumer group stays stable.

