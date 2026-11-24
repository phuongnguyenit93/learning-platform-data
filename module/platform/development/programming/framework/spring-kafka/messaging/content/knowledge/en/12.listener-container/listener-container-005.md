# Record listener and batch listener

## 1. Two ways to receive records in Spring Kafka

Spring Kafka provides two common listener styles for `@KafkaListener`:

- **Record listener**: the listener method is invoked once per record. If a single `poll()` returns multiple records, the container invokes the method sequentially for each record.
- **Batch listener**: the listener method is invoked once with a group of records received by the consumer from a single `poll()`.

Both listener styles share the underlying Kafka consumer and listener container. The main difference lies in the unit of data the application method receives and how the application handles errors, offset commits, metadata, and throughput.

For example, suppose topic `orders` has three partitions. A single `poll()` can return records from all three partitions:

```text
KafkaConsumer.poll()
       |
       +── orders-0: offset 10, 11
       +── orders-1: offset 20
       +── orders-2: offset 35, 36
       |
       +── Record listener: invokes listener 5 times, 1 record each
       |
       +── Batch listener: invokes listener once with a batch of 5 records
```

Here, a batch is the set of records the consumer received from that poll. It does not necessarily contain the same number of records on every invocation, does not necessarily belong to only one partition, and does not automatically form an atomic transaction.

## 2. How does a record listener work?

A record listener receives one record on each method invocation. This is the simple and common approach when each event is an independent business unit.

```java
@Component
public class OrderRecordListener {

    private final OrderService orderService;

    public OrderRecordListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "recordKafkaListenerContainerFactory")
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
```

The container polls records from Kafka, deserializes and converts the payload into `OrderCreated`, and then calls `onOrder()` for each record. If poll returns 100 records, the listener can be invoked 100 times. Polling can still fetch many records in a single request; a record listener does not mean every record requires a separate network request.

### Receiving ConsumerRecord to access metadata

If you need the key, topic, partition, offset, timestamp, or raw headers, the listener can accept `ConsumerRecord`:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "recordKafkaListenerContainerFactory")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    OrderCreated event = record.value();

    log.info("Received eventId={}, topic={}, partition={}, offset={}, key={}",
            event.eventId(), record.topic(), record.partition(),
            record.offset(), record.key());

    orderService.process(event);
}
```

Or receive the payload along with specific headers:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(
        OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    log.info("Received {}, {}-{} at offset {}",
            event.orderId(), topic, partition, offset);
    orderService.process(event);
}
```

`ConsumerRecord` fits when you need extensive metadata or direct access to Kafka headers. Receiving the payload and `@Header` is cleaner when business logic only needs a few transport details.

## 3. How does a batch listener work?

A batch listener receives a list of records in a single invocation. To enable batch mode, configure the listener container factory with `setBatchListener(true)`.

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(3);
        return factory;
    }
}
```

Declare a listener accepting a list of payloads:

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

The container converts the polled records into a list of payloads and invokes `onOrders()` once. The application can process the entire list in one batch operation, such as inserting multiple rows into a database at once or calling a bulk-capable API.

### Receiving ConsumerRecord in a batch

When per-record metadata is needed, you can receive a list of `ConsumerRecord`:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        log.info("topic={}, partition={}, offset={}, key={}",
                record.topic(), record.partition(),
                record.offset(), record.key());
        orderService.process(record.value());
    }
}
```

A batch can contain records from multiple partitions. Offsets are only meaningful within each partition; do not compare offsets across two partitions as a global order. Kafka preserves order within each partition, but does not guarantee overall order across partitions.

Spring Kafka also supports the `ConsumerRecords<K, V>` parameter type for batch listeners when the application wants to work directly with the poll result structure grouped by topic-partition. Choose the parameter type based on the level of metadata the business logic needs.

## 4. Configuring both listener styles

An application can declare two separate factories to avoid confusing listener styles:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    recordKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(false); // Record listener
        factory.setConcurrency(3);
        return factory;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true); // Batch listener
        factory.setConcurrency(3);
        return factory;
    }
}
```

Attach the right factory to each `@KafkaListener`:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "recordKafkaListenerContainerFactory")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}

@KafkaListener(
        topics = "orders-archive",
        groupId = "archive-service",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onArchiveBatch(List<OrderCreated> events) {
    archiveService.storeBatch(events);
}
```

In this condensed example, the two methods could live in separate listener beans. The default factory created by Spring Boot auto-configuration is usually a record listener; if batch mode is needed, create a dedicated batch factory or configure the factory explicitly. Do not pass a method taking `List<T>` to a record listener factory and expect the container to automatically switch to batch mode.

## 5. What determines batch size?

A batch listener receives however many records `poll()` returns on that call. The `max.poll.records` property sets an upper limit on the maximum number of records returned in a single poll; it does not guarantee every invocation receives that exact number.

Example configuration:

```yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
      properties:
        max.poll.interval.ms: 300000
```

`max-poll-records: 200` caps a consumer's single poll at at most 200 records. The actual batch may be smaller depending on available data, producer rate, fetch limits, record sizes, and assigned partitions.

Several other properties also affect how much data is fetched:

| Property | Role |
|---|---|
| `max.poll.records` | Caps the maximum number of records returned by a single `poll()` |
| `fetch.max.bytes` | Caps total fetched data in one request at the consumer config level |
| `max.partition.fetch.bytes` | Caps fetched data per partition in one request, with exceptions so the consumer can make progress |
| `fetch.min.bytes` | Minimum amount of data the broker tries to accumulate before returning a fetch response |
| `fetch.max.wait.ms` | Maximum time the broker waits to satisfy `fetch.min.bytes` before returning a response |

Do not raise `max.poll.records` just to get larger batches. Oversized batches can increase memory usage, processing duration per poll, and the risk of exceeding `max.poll.interval.ms`. Too-small batches can reduce bulk efficiency and increase listener invocation overhead.

## 6. Comparing record listener and batch listener

| Criterion | Record listener | Batch listener |
|---|---|---|
| Invocation unit | One record per call | A list/group of records per call |
| Declaration style | Payload parameter or `ConsumerRecord` | `List<T>`, list of `ConsumerRecord`, or `ConsumerRecords` |
| Factory setting | `setBatchListener(false)` or default | `setBatchListener(true)` |
| Business processing | Each event independently | Can process multiple events in a single bulk operation |
| Metadata | Directly on `ConsumerRecord` or record headers | Per-record metadata available via `ConsumerRecord` or list-typed headers |
| Errors | Easy to identify the failing record since each call handles one record | Must identify the failing record in the batch or accept retrying the entire batch |
| Commits | Can commit after each record with `AckMode.RECORD` | Typically commits per batch; `AckMode.RECORD` does not apply to batch listeners |
| Throughput | Easy to optimize per record, may incur higher invocation overhead | Can increase throughput for bulk work and reduce per-record overhead |
| Latency | Can process each record immediately | May wait for enough data or fetch response before processing a batch |
| Memory | Typically keeps processing footprint smaller | Requires memory for the entire batch and converted objects |

Record listeners are usually easier to understand, easier to retry per record, and suited to business logic with event-specific rules. Batch listeners are helpful when downstream systems support bulk operations or per-call overhead is high, but require careful design for partial failures, commits, and ordering.

## 7. AckMode and offset commit timing

Listener style and AckMode are two separate configurations. A record listener does not mean offsets are always committed per record; a batch listener does not mean a transaction is automatically created.

For record listeners:

- `AckMode.RECORD`: container commits after the listener successfully processes each record.
- `AckMode.BATCH`: container commits after successfully processing all records returned from a single poll. This is a common default mode for listener containers.
- `MANUAL` or `MANUAL_IMMEDIATE`: listener explicitly calls `Acknowledgment.acknowledge()` as configured.

For batch listeners, `AckMode.BATCH` matches the batch processing unit. `AckMode.RECORD` is not supported because the listener method receives and processes a batch as a unit. When using manual acknowledgment, call acknowledge only after processing for the batch or corresponding portion of the batch has completed.

Example batch listener with manual acknowledgment:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "manualBatchListenerFactory")
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records,
        Acknowledgment acknowledgment) {

    orderService.processBatch(records.stream()
            .map(ConsumerRecord::value)
            .toList());

    acknowledgment.acknowledge();
}
```

The corresponding factory can set `ContainerProperties.AckMode.MANUAL`. If batch processing fails and the method throws an exception before `acknowledge()`, offsets are not confirmed by that manual call and the error handler decides retry/recovery.

Since Spring Kafka 3.0.10, batch listeners can use `Acknowledgment.acknowledge(index)` to acknowledge part of a batch under matching configuration conditions, specifically `MANUAL_IMMEDIATE` and invocation on the consumer thread. This is an advanced, version-dependent API; read the documentation for your exact version and test offset ordering before adopting it.

## 8. Error handling with record listeners

With a record listener, an exception is normally tied directly to one specific record. `DefaultErrorHandler` can retry the failing record with backoff, then recover or route it to a dead-letter topic via a recoverer.

Illustrative configuration example:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    var backOff = new FixedBackOff(1_000L, 2L);
    return new DefaultErrorHandler(recoverer, backOff);
}
```

This example configures two retries after the initial processing attempt, spaced one second apart. After retries are exhausted, the recoverer sends the record to the DLT using default routing rules or custom configuration. Configure serializers and DLT topics compatible with the payloads, headers, and data types encountered.

For record listeners, classify exceptions: transient failures can be retried; invalid data errors usually need DLT routing or dedicated business handling. Handlers should still be idempotent because records can be redelivered after restarts or before commit.

## 9. Error handling with batch listeners

A batch listener receives multiple records in a single call, so when the method throws an exception, the container needs to know which record in the batch failed to decide what has already been processed and what needs retrying.

With `DefaultErrorHandler`, a batch listener can throw `BatchListenerFailedException` to pinpoint the failing record or index. Once the failing record is identified, the container can handle preceding records appropriately and retry/recover starting from the failing record and the remaining ones. If the listener throws an exception that does not identify the failing record, the fallback strategy may retry the entire batch.

Example processing each record in a batch and marking the failing record:

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

The example uses `BatchListenerFailedException` to report the failing record to the error handler. Exact commit/retry/recover behavior depends on `DefaultErrorHandler` configuration, AckMode, and the Spring Kafka version. If a listener processes an entire batch with a single bulk statement, pinpointing the failing record may be hard; in that case, design database transactions or data validation steps to isolate partial failures.

Batch listeners do not turn records from multiple partitions into a single transactional unit. If a batch contains records from `orders-0` and `orders-1`, offsets are still managed separately for each partition. An error can cause a subset of records to be redelivered; business operations must tolerate retries.

## 10. Ordering and parallel processing

Kafka guarantees ordering within a single partition. A record listener is called record by record; a batch listener receives a set of records that may originate from multiple partitions. In both cases, there is no global order across partitions.

If the same `orderId` is sent with the same key and routed to the same partition, records for that order maintain append order within that partition. However:

- A batch can contain records from multiple partitions; do not infer business order by comparing offsets across partitions.
- If the application processes batch elements via a parallel stream or executor, completion order can differ from receipt order.
- When processing asynchronously, only commit contiguous completed offsets within each partition; never commit past records still in progress.
- Increasing concurrency creates more consumers in the group, but does not allow two consumers to process the same partition simultaneously under standard assignment.

For business workflows requiring per-entity ordering, keep keys consistent, process sequentially within a partition, or build per-key serialization mechanisms. Do not use batching or parallel processing without a strategy to protect ordering and commits.

## 11. Choosing record listener or batch listener?

Choose a record listener when each event must be processed independently, you want per-record error identification and retries, or records must be processed as soon as polled. This is usually the simplest starting point for business consumers.

Choose a batch listener when the receiving system supports handling multiple records in one call, such as bulk inserts, bulk APIs, batch computations, or reducing conversion/call-stack overhead. Batch listeners are particularly beneficial when processing efficiency scales significantly with batch size.

Before choosing batching, consider:

1. Does downstream have a suitable bulk API or transaction support?
2. If one record fails, can the rest be identified and handled?
3. How much memory does the maximum batch require?
4. Does batch processing time fit within `max.poll.interval.ms`?
5. Is ordering by partition or key required?
6. Do AckMode and error handler reflect the true success boundary?

Do not pick batching just to increase records per listener call. If the bottleneck is a hot partition, a slow database, or a downstream without bulk support, large batches can increase latency and retry duration without improving throughput.

## 12. Testing both listener styles

Integration tests should use multi-partition topics and records with varied keys to verify real behavior.

Useful scenarios:

1. **Record listener:** send three records and verify the method is invoked three times, receiving one payload each time.
2. **Batch listener:** configure a batch factory, send multiple records, and verify the listener receives a list; do not assume every poll delivers the full `max.poll.records`.
3. **Metadata:** verify topic, partition, offset, and key are accurate when receiving `ConsumerRecord` or headers.
4. **Multiple partitions:** send records to multiple partitions and verify a batch can contain records from multiple partitions.
5. **AckMode:** verify committed offsets with `RECORD`, `BATCH`, and manual acknowledgment.
6. **Record errors:** make one record fail and verify `DefaultErrorHandler` retries/recovers as configured.
7. **Batch errors:** throw `BatchListenerFailedException` on a specific record and check preceding/subsequent records under the retry policy.
8. **Batch timeout:** create a slow-processing batch to inspect `max.poll.interval.ms`, rebalances, and consumer lag.
9. **Redelivery:** stop the consumer before commit and verify the handler is idempotent when records are redelivered.

You can use `spring-kafka-test` or the Kafka test starter matching your Spring Boot version. For rebalances, timeouts, transactions, and heavy load, also test against brokers/containers close to the deployment environment.

## 13. Summary

- A record listener invokes the method once per record; a batch listener invokes it once with a group of records from `poll()`.
- Record listeners suit per-event processing and per-record retries; batch listeners help when downstream supports bulk operations.
- Enable batch listeners with `setBatchListener(true)` on the listener container factory and specify the factory on `@KafkaListener`.
- Batch size is influenced by `max.poll.records`, fetch settings, and available data; it is not a fixed size.
- Record listeners and batch listeners can use different AckModes; `AckMode.RECORD` does not apply to batch listeners.
- Batch listeners require a clear error strategy; `BatchListenerFailedException` helps identify the failing record to `DefaultErrorHandler`.
- Batching does not imply an atomic transaction and does not create global ordering across partitions.
- Control `max.poll.interval.ms`, memory, retries, ordering, and idempotency when processing large batches.

When you understand the unit of received data and how the container manages polling, offsets, and errors, a Spring Kafka application can choose the record listener or batch listener that fits its business characteristics and throughput goals.
