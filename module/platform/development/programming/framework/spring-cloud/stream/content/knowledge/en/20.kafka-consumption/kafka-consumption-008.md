# Batch Consumption with batch-mode and List Payloads

Kafka consumers normally receive data by calling `poll()`. A single poll can return multiple records from the partitions assigned to the consumer. With the default record listener mode, Spring Cloud Stream invokes the function once per record. When `batch-mode` is enabled, the Kafka Binder collects the records from a single poll into a list and invokes the function with `List<T>` or `Message<List<T>>`.

Batch mode reduces handler invocation overhead and fits operations that can process multiple records together, such as bulk database writes or event aggregation. However, a batch is a collection of distinct Kafka records received in a single poll; it is not a single Kafka record containing a JSON array. Batch processing also changes how headers, retries, acknowledgments, and DLQs work. Understand these differences before enabling the mode.

## 1. How Does Batch Mode Work?

In normal mode, the Kafka Binder converts each record into a message and invokes the function individually. With `batch-mode: true`, the binder puts all records received from a single poll into a list and calls the function once.

Suppose a topic contains these records:

```text
Poll 1:
  partition 0: offset 120, OrderCreated(order-101)
  partition 0: offset 121, OrderCreated(order-102)
  partition 1: offset  88, OrderCreated(order-103)
```

In record mode, the function may be invoked three times. In batch mode, the function receives a single payload with three elements:

```text
Consumer<List<OrderCreated>>
    |
    +-- OrderCreated(order-101)
    +-- OrderCreated(order-102)
    +-- OrderCreated(order-103)
```

A batch is formed from the Kafka records returned in that poll. Actual batch size does not necessarily equal `max.poll.records`; that is only an upper bound on how many records a single `poll()` returns. Actual count also depends on available data, partition assignments, and Kafka consumer fetch settings.

Batch mode is supported with Spring Cloud Stream's functional programming model. Do not use `@StreamListener` for batch consumption; that API does not support this mode.

## 2. Enabling batch-mode on an Input Binding

Suppose the application has a function processing order events:

```java
@Bean
Consumer<List<OrderCreated>> processOrderBatch(
        OrderBatchService orderBatchService) {

    return events -> orderBatchService.process(events);
}
```

Input binding configuration:

```yaml
spring:
  cloud:
    function:
      definition: processOrderBatch
    stream:
      bindings:
        processOrderBatch-in-0:
          destination: orders.created
          group: order-batch-service
          consumer:
            batch-mode: true
```

The `batch-mode` property belongs to the common consumer binding properties. It enables listener mode receiving multiple records per invocation. Set this property only on Kafka input bindings that need batching; do not set it at the binder level or on producer bindings.

A named group lets instances of the service share partitions. Each poll of a consumer only includes records from the partitions assigned to that consumer.

## 3. Two Supported Signatures

When batch mode is enabled, the Kafka Binder supports two primary input signatures:

```java
Consumer<List<OrderCreated>>
```

and:

```java
Consumer<Message<List<OrderCreated>>>
```

The first signature receives the list of payloads. It is simple when the logic only needs business data. However, the function does not receive message headers.

The second signature receives a message wrapping the payload list. The function can read batch-level headers, though header values are typically collections corresponding to each element rather than a single value applying to the entire batch.

`List<Message<OrderCreated>>` is not supported in batch mode. Do not assume the binder creates a separate full `Message` for each element.

### Payload Only: List<T>

```java
@Bean
Consumer<List<OrderCreated>> processOrderBatch(
        OrderBatchService service) {

    return events -> {
        if (events.isEmpty()) {
            return;
        }

        service.process(events);
    };
}
```

This is the simplest option when the service only needs the list of events. There are no headers, so if you need event IDs, Kafka offsets, partitions, or correlation metadata, use `Message<List<T>>`.

### Metadata Needed: Message<List<T>>

```java
@Bean
Consumer<Message<List<OrderCreated>>> processOrderBatch(
        OrderBatchService service) {

    return batch -> {
        List<OrderCreated> events = batch.getPayload();

        Object eventIds = batch.getHeaders().get("eventId");
        Object correlationIds =
            batch.getHeaders().get("correlationId");

        service.process(events, eventIds, correlationIds);
    };
}
```

This example illustrates reading headers. When a batch has multiple records, custom headers are represented as collections; element `i` corresponds to the payload at index `i`. Check the collection type and size before pairing metadata with events. Do not read a single header value and apply it to every record if that header is actually a list.

## 4. Reading Batch Headers in Matching Order

Suppose a batch has three events and each record carries its own `eventId`. When using `Message<List<OrderCreated>>`, the header map may contain:

```text
payload:
  [order-101, order-102, order-103]

headers:
  eventId:
    [evt-501, evt-502, evt-503]
  correlationId:
    [checkout-A, checkout-B, checkout-C]
```

Header collections share the same positional order as the payload list. You can zip them by index:

```java
@Bean
Consumer<Message<List<OrderCreated>>> processOrderBatch(
        OrderBatchService service) {

    return batch -> {
        List<OrderCreated> events = batch.getPayload();

        List<?> eventIds = asList(
            batch.getHeaders().get("eventId")
        );

        if (!eventIds.isEmpty() && eventIds.size() != events.size()) {
            throw new IllegalStateException(
                "eventId header count does not match batch size"
            );
        }

        for (int i = 0; i < events.size(); i++) {
            String eventId = eventIds.isEmpty()
                ? null
                : String.valueOf(eventIds.get(i));

            service.process(events.get(i), eventId);
        }
    };
}

private List<?> asList(Object value) {
    if (value == null) {
        return List.of();
    }
    if (value instanceof Collection<?> collection) {
        return new ArrayList<>(collection);
    }
    return List.of(value);
}
```

This is an illustrative example; in a real project, place the helper in an appropriate class and define clearly which headers are required. If a header is converted into another collection type, normalize it based on the binder's actual runtime type. Do not use `List.copyOf()` if the collection may contain `null`, as it rejects null elements.

With Kafka batch listeners, certain metadata is provided as lists. If you need access to per-record converted headers, the Spring Cloud Stream Kafka Binder also provides the `kafka_batchConvertedHeaders` header on certain paths; this header holds a list of metadata maps ordered by payload index. Check your exact binder and Spring Kafka versions before relying on this header.

## 5. Batch Size and Kafka Consumer Properties

Batch size is influenced by Kafka consumer properties. Commonly tuned properties:

| Property | Role |
|---|---|
| `max.poll.records` | Maximum number of records returned from a single `poll()` |
| `fetch.min.bytes` | Minimum amount of data the broker tries to accumulate before returning a fetch response |
| `fetch.max.wait.ms` | Maximum time the broker waits to reach `fetch.min.bytes` |
| `max.partition.fetch.bytes` | Fetch data limit per partition |
| `max.poll.interval.ms` | Maximum time between polls before the consumer is considered stalled |

Per-binding configuration example:

```yaml
spring:
  cloud:
    function:
      definition: processOrderBatch
    stream:
      bindings:
        processOrderBatch-in-0:
          destination: orders.created
          group: order-batch-service
          consumer:
            batch-mode: true
      kafka:
        bindings:
          processOrderBatch-in-0:
            consumer:
              configuration:
                max.poll.records: 200
                fetch.min.bytes: 1024
                fetch.max.wait.ms: 100
```

`max.poll.records` sets a limit of 200 records per poll in this example. This is not a guarantee that every batch always contains 200 elements. If the topic has little data, batches can be smaller; if records do not meet configured fetch thresholds yet, the consumer may receive smaller batches or wait up to the fetch wait time.

Raising `max.poll.records` can reduce listener invocations and boost throughput, but also increases how much data must be held and processed in one shot. If the handler takes too long, the consumer can exceed `max.poll.interval.ms`, be evicted from the group, and trigger a rebalance. Measure real batch processing times before increasing the limit.

## 6. Batch Mode vs. Producer Batching vs. Application-Emitted List Payloads

Distinguish three concepts:

| Concept | Meaning |
|---|---|
| Consumer batch mode | One Kafka poll returns multiple records and the function receives a `List<T>` |
| Producer batching | Kafka producer groups multiple records into network requests/batches for transmission efficiency |
| A List-shaped payload | Producer emits a single Kafka record whose value contains a list of items, such as a JSON array |

Consumer batch mode does not merge multiple Kafka records into a single new record. Records still retain their own keys, partitions, offsets, timestamps, and metadata. The binder only collects them into a list at the function invocation boundary.

If a producer sends a JSON array inside a single record, a record-mode consumer may deserialize that payload into `List<T>` depending on the converter and target type; that is not Kafka batch mode. Conversely, when batch mode is enabled, `List<T>` typically represents a list of values from multiple distinct records.

Producer batching is also independent of consumer batch mode. A Kafka producer can batch records for efficient transmission even when the consumer reads one record at a time.

## 7. Processing the Whole Batch vs. Item-by-Item?

There are two ways to structure processing:

- Call a service accepting the entire `List<T>` to perform a bulk operation, such as a batch insert or bulk API call.
- Iterate over each item to apply individual business rules.

Bulk processing example:

```java
@Service
public class OrderBatchService {

    private final OrderRepository repository;

    public OrderBatchService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(List<OrderCreated> events) {
        List<Order> orders = events.stream()
            .map(Order::from)
            .toList();

        repository.saveAll(orders);
    }
}
```

This works well when operations can share a transaction or bulk API. However, a database batch transaction does not automatically include the Kafka offset commit. If the database commits and the consumer fails before committing offsets, the records can be redelivered. Idempotency or deduplication is still required.

If iterating item by item and the third item fails after the first two committed independently, the entire batch may be reprocessed depending on the error handler and acknowledgment mode. In that case, the first two items would run again. Define clear transaction boundaries and ensure operations can be safely repeated.

## 8. Retries in Batch Mode

The Kafka Binder does not support internal `maxAttempts`-based retries like record mode when batch mode is enabled. In this mode, `maxAttempts` is overridden to `1`. Therefore, do not configure `max-attempts: 5` expecting the binder to automatically re-invoke the function five times for the whole batch.

If retries are needed, configure Spring Kafka's `DefaultErrorHandler` via `ListenerContainerCustomizer` or an error handler suited to your Spring Kafka version. The error handler can apply backoff, retries, or recovery according to record/batch semantics.

Another option is using manual acknowledgment and `Acknowledgment.nack(index, sleep)` in a batch listener to acknowledge items before the failing index and request redelivery of the remaining items per Spring Kafka semantics. Understand `AckMode`, index semantics, and how the container handles the remaining batch. This API does not replace idempotency design.

Do not apply record-listener retry patterns to batch listeners without verifying first. How the framework locates failing records and seeks/replays can differ.

## 9. Acknowledgment and Partial Batch Processing

During batch processing, an exception can fail the entire listener invocation. Without a partial acknowledgment strategy, previously processed records in the batch may also be redelivered when offsets have not been committed.

If manual acknowledgment is needed, you can retrieve `Acknowledgment` from the headers of `Message<List<T>>` with an appropriate manual ack configuration. High-level example:

```java
@Bean
Consumer<Message<List<OrderCreated>>> processOrderBatch(
        OrderBatchService service) {

    return batch -> {
        Acknowledgment acknowledgment =
            batch.getHeaders().get(
                KafkaHeaders.ACKNOWLEDGMENT,
                Acknowledgment.class
            );

        List<OrderCreated> events = batch.getPayload();

        for (int i = 0; i < events.size(); i++) {
            service.process(events.get(i));

            // Perform ack/nack only according to the designed strategy.
        }

        if (acknowledgment != null) {
            acknowledgment.acknowledge();
        }
    };
}
```

This example only shows where to access the acknowledgment; do not copy it without configuring `ackMode` and defining your transaction/commit strategy. Calling `acknowledge()` after the loop is only appropriate if all items succeeded according to the business contract.

For partial batch failures, Spring Kafka provides `nack(index, sleep)` in supported acknowledgment modes. Read the Spring Kafka documentation for your version to verify how offsets before `index` are committed and the remaining items redelivered. Never call `acknowledge()` before processing finishes if doing so could lose redelivery of unprocessed items.

## 10. DLQ When Batch Mode Is Enabled

The Kafka Binder supports DLQ for batch mode starting from version 4.0.2. Note an important behavior: when using DLQ on a batch-mode consumer binding, all records received from the preceding poll may be sent to the DLT, not solely the offending record.

This can cause valid records from the same batch to appear in the DLT alongside the failing record. Therefore, operational procedures should:

- Preserve event IDs and metadata to identify the record that actually caused the failure.
- Avoid blindly replaying the entire batch.
- Verify idempotency before replaying partially processed records.
- Have tooling to filter and replay per record.
- Verify DLT behavior on the exact Kafka Binder version you are using.

If isolating a single failing record and continuing with other records is required, consider a batch error handler, partial acknowledgment, or switching back to record mode. Choose the mechanism based on ordering, throughput, and recovery requirements.

## 11. Null Payloads and Tombstone Records

Kafka can contain tombstone records with null values, especially in compacted topics. When receiving a batch, the corresponding element in the list may be `null` for both `List<T>` and `Message<List<T>>`.

Never assume every element in a batch is non-null. If the consumer reads a compacted topic or a stream with tombstones, handle nulls intentionally:

```java
@Bean
Consumer<List<OrderSnapshot>> processSnapshots(
        SnapshotService service) {

    return snapshots -> {
        for (OrderSnapshot snapshot : snapshots) {
            if (snapshot == null) {
                // Handle tombstone according to the application contract.
                continue;
            }

            service.apply(snapshot);
        }
    };
}
```

Depending on business logic, a tombstone may mean deleting the key from compacted state. Skipping nulls is only valid if the application does not need to act on that deletion.

## 12. Observability and Tracing in Batch Mode

Tracing propagation is not directly supported the same way as record listeners when consuming batches. A batch can hold records from different partitions and producers, each carrying its own trace context or none at all. The framework cannot assign a single trace ID to the entire batch while accurately preserving provenance.

When using `Message<List<T>>`, the Kafka Binder can provide the `kafka_batchConvertedHeaders` header containing per-record header maps. If per-event observations/spans are needed, the application must correlate metadata with each element and manage observation lifecycles manually.

Metrics to record:

- Number of batches received.
- Number of records per batch.
- Batch processing time and per-record processing time where available.
- Failed batches, failed records, and redeliveries.
- Consumer lag per group/partition.
- Records routed to DLT and records replayed.

Do not measure only function invocation count; one invocation can process one record or hundreds of records. Throughput should be measured in records/second while also tracking per-record latency.

## 13. When Should Batch Mode Be Used?

Batch mode fits when:

- Each poll typically yields multiple records.
- The service or database supports bulk operations.
- Per-record function invocation or transaction overhead is significant.
- Processing and recovery at batch boundaries is acceptable.
- The application has suitable idempotency, retry, and DLQ strategies.

Record mode is usually a better fit when:

- Each record needs independent retries or DLQ routing.
- Low per-event latency is required.
- Per-record headers/tracing need standard out-of-the-box handling.
- One bad record must not affect other records.
- Business logic is simple with no clear benefit from bulk processing.

Batching is not automatically faster in every scenario. Large batches can increase latency, memory pressure, and processing duration before offset commits. Benchmark with realistic workloads.

## 14. Testing Batch Consumers

Test at least these scenarios:

1. Batch with a single record.
2. Batch with multiple records from the same partition.
3. Batch with records from multiple partitions.
4. Payload correctly converted into `List<T>`.
5. Header collections matched in exact order with payloads.
6. One malformed-schema record fails the batch per expected policy.
7. One record fails after earlier records already applied side effects.
8. Retry/error handler processes the batch per policy.
9. DLQ receives the expected record or entire batch per binder version semantics.
10. Tombstone/null records handled properly.
11. Consumer restarts before offset commit and redelivery occurs.
12. Large batches do not exceed poll interval limits or memory budgets.

The Test Binder can verify some in-memory function and binding logic, but it does not fully simulate Kafka consumer poll batches, partition assignments, offset commits, batch nacks, or DLTs. Use integration tests with real Kafka, such as via Testcontainers, to verify these behaviors.

## 15. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Function still receives individual records | `consumer.batch-mode` not enabled on the right input binding | Check binding name and configuration |
| Cannot read headers | Function uses `List<T>` | Switch to `Message<List<T>>` |
| Header is not a single scalar value | Batch headers are represented as collections | Zip header elements with payloads by index |
| Using `List<Message<T>>` fails | That signature is not supported in batch mode | Use `List<T>` or `Message<List<T>>` |
| Retries do not run per `maxAttempts` | Binder retry is not supported in batch mode; `maxAttempts` is set to 1 | Configure an appropriate error handler |
| Many records appear in the DLT | Batch DLQ may forward the entire preceding poll's batch | Inspect individual records and replay selectively |
| Consumer triggers rebalances | Batch processing takes too long, exceeding `max.poll.interval.ms` | Reduce batch size, optimize handler, or tune timeout appropriately |
| Null causes handler failure | Batch contains tombstone records | Handle nulls per contract |
| Batch tracing lacks a single trace ID | Batch may contain multiple sources and trace contexts | Handle metadata per record |

## 16. Production Checklist

- Enable `batch-mode: true` on the exact Kafka input binding using the functional programming model.
- Choose `List<T>` if only payloads are needed; choose `Message<List<T>>` if headers are needed.
- Never use `List<Message<T>>` in batch mode.
- Remember a batch is multiple Kafka records from one poll, not a single record holding a JSON array.
- Tune `max.poll.records`, fetch settings, and `max.poll.interval.ms` for processing duration.
- Bound batch sizes and monitor memory/latency.
- Zip batch headers by index; do not treat them as scalars.
- Design idempotency since batches may be redelivered after failures.
- Do not rely on `max-attempts` for batch retries; configure an appropriate error handler.
- Understand that batch DLQ may route all records from the preceding poll to the DLT.
- Handle tombstones/nulls if topics contain compacted records.
- Monitor record throughput, batch size, consumer lag, retries, and DLT.
- Test offsets, redelivery, partial failures, and DLQ against real Kafka.

## 17. References

- [Spring Cloud Stream Kafka Binder — Consuming Batches](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/consume-batches.html), batch signatures, headers, retries, DLQ, and observability.
- [Spring Cloud Stream Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html), Kafka consumer and binder configuration.
- [Apache Kafka Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs), `max.poll.records`, fetch settings, and `max.poll.interval.ms`.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/), batch listeners, error handlers, and manual acknowledgment.

The Kafka Binder's batch mode gathers records received in a single poll into `List<T>` for bulk function processing. Choose `Message<List<T>>` when metadata is required, keeping in mind that headers are also grouped per record and retries/DLQ carry distinct semantics. When batch size, acknowledgment, idempotency, and error handling are designed together, consumers can improve processing efficiency while maintaining reliable recovery when a record in a batch fails.
