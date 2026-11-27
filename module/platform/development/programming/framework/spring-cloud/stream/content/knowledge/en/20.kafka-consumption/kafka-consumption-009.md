# Correlating Per-Element Headers in a Batch

A Kafka consumer can receive multiple records in a single `poll()`. With batch mode in the Spring Cloud Stream Kafka binder, those records are passed to the processing function as a list of payloads. When the application needs to know which topic, partition, offset, or key each element came from, receiving `List<T>` alone is not enough: you must accept `Message<List<T>>` to access per-record metadata.

The key point is that batch headers are not a single shared set of metadata applying to the entire list. With `Message<List<T>>`, per-record metadata headers are represented as collections ordered identically to the payload list. The element at index `i` in the payload list must be correlated with the metadata at index `i` in each header collection. Misaligned indexing can cause logs, traces, routing, or business decisions to attach one record's metadata to another record.

## 1. Batch Mode in the Kafka Binder

By default, the Spring Cloud Stream Kafka binder invokes the consumer function once per record. When `batch-mode` is enabled, all records fetched in a single poll are assembled into a batch and delivered to the listener as a `List<?>`.

Configuration example:

```yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-batch-processor
          content-type: application/json
          consumer:
            batch-mode: true
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                max.poll.records: 100
```

`batch-mode: true` enables batch consumption for the input binding. `max.poll.records` caps the maximum number of records the Kafka consumer returns in a single poll. Actual batches may be smaller than this limit when less data is available. Fetch properties such as `fetch.min.bytes` and `fetch.max.wait.ms` also influence how the broker accumulates data before returning.

A batch is the set of records the consumer receives from that poll. If the consumer subscribes to multiple topics or multiple partitions, one batch can contain records from different topics and partitions. Never assume all elements in a batch share the same topic, partition, or key.

## 2. Two Supported Function Signatures

With Spring Cloud Stream Kafka binder batch mode, the two main supported signatures are:

```java
Consumer<List<OrderCreated>>
Consumer<Message<List<OrderCreated>>>
```

The difference lies in header access:

| Signature | Payload | Message Header Access |
| --- | --- | --- |
| `Consumer<List<OrderCreated>>` | List of `OrderCreated` items | Cannot access batch message headers |
| `Consumer<Message<List<OrderCreated>>>` | List of `OrderCreated` via `getPayload()` | Can read headers; per-record metadata are collections aligned with the payload |

If per-record metadata correlation is needed, use `Message<List<T>>`. `List<Message<T>>` is not supported for Spring Cloud Stream Kafka binder batch consumption. Do not confuse this model with certain ways of declaring batch listeners directly via `@KafkaListener` in Spring Kafka.

## 3. Header Structure of Message<List<T>>

Suppose a batch contains three payloads:

```text
payload[0] = OrderCreated("ORD-101")
payload[1] = OrderCreated("ORD-102")
payload[2] = OrderCreated("ORD-103")
```

Per-record headers are represented by collections in the same order:

```text
kafka_receivedTopic     = ["orders.created", "orders.created", "orders.priority"]
kafka_receivedPartition = [2, 0, 1]
kafka_offset            = [501, 812, 77]
kafka_receivedMessageKey= ["ORD-101", "ORD-102", "ORD-103"]
```

Therefore, the metadata for `payload[1]` resides at index `1` in each corresponding header collection:

| Index | Payload | Topic | Partition | Offset | Key |
| ---: | --- | --- | ---: | ---: | --- |
| 0 | `ORD-101` | `orders.created` | 2 | 501 | `ORD-101` |
| 1 | `ORD-102` | `orders.created` | 0 | 812 | `ORD-102` |
| 2 | `ORD-103` | `orders.priority` | 1 | 77 | `ORD-103` |

This is an illustrative example. Actual values depend on topic subscriptions, partition assignments, keys, header mappers, and binder configuration. An offset is meaningful only within a single topic-partition; do not compare two offsets from different partitions as if they form a global order.

## 4. Reading Kafka Headers per Element

Spring Kafka provides constants in `KafkaHeaders` to access record metadata. With a batch message, the corresponding headers can hold collections:

- `KafkaHeaders.RECEIVED_TOPIC`: topic of each record.
- `KafkaHeaders.RECEIVED_PARTITION`: partition of each record.
- `KafkaHeaders.OFFSET`: offset of each record.
- `KafkaHeaders.RECEIVED_KEY`: key of each record, if present.
- `KafkaHeaders.RECEIVED_TIMESTAMP`: timestamp of each record.

Example consumer function accepting `Message<List<OrderCreated>>`:

```java
import java.util.List;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

public record OrderCreated(String orderId, long totalCents) {}

@Configuration
public class OrderBatchConsumers {

    @Bean
    public Consumer<Message<List<OrderCreated>>> processOrders() {
        return batchMessage -> {
            List<OrderCreated> orders = batchMessage.getPayload();

            List<String> topics = headerList(
                    batchMessage, KafkaHeaders.RECEIVED_TOPIC);
            List<Integer> partitions = headerList(
                    batchMessage, KafkaHeaders.RECEIVED_PARTITION);
            List<Long> offsets = headerList(
                    batchMessage, KafkaHeaders.OFFSET);
            List<?> keys = headerList(
                    batchMessage, KafkaHeaders.RECEIVED_KEY);

            if (topics.size() != orders.size()
                    || partitions.size() != orders.size()
                    || offsets.size() != orders.size()) {
                throw new IllegalStateException(
                        "Batch payload and Kafka metadata are not aligned");
            }

            for (int i = 0; i < orders.size(); i++) {
                OrderCreated order = orders.get(i);
                String topic = topics.get(i);
                Integer partition = partitions.get(i);
                Long offset = offsets.get(i);
                Object key = i < keys.size() ? keys.get(i) : null;

                processOne(order, topic, partition, offset, key);
            }
        };
    }

    private static <T> List<T> headerList(
            Message<?> message, String headerName) {
        Object value = message.getHeaders().get(headerName);
        if (value instanceof List<?> values) {
            @SuppressWarnings("unchecked")
            List<T> result = (List<T>) values;
            return result;
        }
        return List.of();
    }

    private static void processOne(
            OrderCreated order,
            String topic,
            Integer partition,
            Long offset,
            Object key) {
        System.out.printf(
                "Order %s from %s-%d@%d, key=%s%n",
                order.orderId(), topic, partition, offset, key);
    }
}
```

This example uses a helper to validate the header type and keep loop logic focused on index correlation. In production code, handle missing optional headers, null values, or unexpected data types explicitly. Never cast blindly assuming every binder/client returns the exact same Java type.

## 5. Index Alignment Rules Between Payload and Headers

When processing a batch, the index is the link between payload and metadata. A safe loop must extract the payload and all headers at the exact same index:

```java
for (int i = 0; i < orders.size(); i++) {
    OrderCreated order = orders.get(i);
    String topic = topics.get(i);
    Integer partition = partitions.get(i);
    Long offset = offsets.get(i);

    audit(order, topic, partition, offset);
}
```

Avoid these practices:

- Using the header at index `0` for every payload in the batch.
- Sorting the payload list independently without sorting the corresponding header collections.
- Filtering or removing a payload while leaving header lists untouched and continuing to use the old indices.
- Pairing payloads with headers via `Map` iteration order or assuming all records share the same partition.
- Treating a single offset as shared metadata for the entire batch.

If you need to filter or sort a batch, create an intermediate structure holding both the payload and metadata for each record before transforming:

```java
public record OrderEnvelope(
        OrderCreated payload,
        String topic,
        int partition,
        long offset,
        Object key
) {}
```

Then convert each index into an `OrderEnvelope`. Any filtering, sorting, or grouping keeps metadata bound to its payload, preventing parallel lists from drifting out of alignment.

## 6. Per-Record Custom Application Headers

Beyond Kafka metadata like topic, partition, offset, and key, producers can send application headers such as `correlationId`, `eventType`, or `tenantId`. When a batch converter maps these headers, Spring Kafka can provide the special `KafkaHeaders.BATCH_CONVERTED_HEADERS` header.

This header is a list of maps; the map at index `i` holds the converted headers of the record corresponding to payload `i`.

Example:

```java
import java.util.List;
import java.util.Map;

import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

List<?> convertedHeaders = (List<?>) batchMessage.getHeaders()
        .get(KafkaHeaders.BATCH_CONVERTED_HEADERS);

for (int i = 0; i < orders.size(); i++) {
    Map<?, ?> recordHeaders = (Map<?, ?>) convertedHeaders.get(i);
    Object correlationId = recordHeaders.get("correlationId");
    Object eventType = recordHeaders.get("eventType");

    System.out.printf("%s: correlation=%s, type=%s%n",
            orders.get(i).orderId(), correlationId, eventType);
}
```

Before accessing it, verify the header exists, is a list, and has the same size as the payload list. `BATCH_CONVERTED_HEADERS` depends on the header mapper; without an appropriate mapper, native header data may be supplied in another form. Check your project's mapper configuration and Spring Kafka version.

`BATCH_CONVERTED_HEADERS` can also contain per-record tracing headers. A batch can contain records from multiple producers with different trace contexts, so the batch cannot share a single `traceId`. If creating individual observations or spans, the application must read each element's map and set the context for that specific record.

## 7. Native Headers vs. Converted Headers

Kafka records store headers as byte arrays. Spring Kafka uses a header mapper to convert them into Spring Messaging headers with appropriate Java types. In a batch, two forms of data may appear:

| Form | Contents | Usage |
| --- | --- | --- |
| Converted headers | Mapped Java header values; per-record metadata represented as collections or per-element maps | Suitable when the application reads business headers such as strings or numbers |
| Native Kafka headers | Raw headers from the Kafka client, preserving names and byte values per the Kafka API | Used when custom decoding is needed or to access headers the mapper does not convert |

When using native headers, align element order with payloads and decode byte values using the encoding agreed upon with the producer. Do not assume a byte-array header can be cast directly to `String` without specifying a charset.

A header mapper may filter header names, skip certain internal headers, or fail to convert values depending on configuration. Therefore, if a business header is mandatory, test producer and consumer through a real binder rather than only inspecting synthetic `Message` objects in unit tests.

## 8. Batch Headers Are Not Shared Metadata for the Entire Batch

Some headers describe the entire delivery or container, while many describe individual records. Distinguish these two categories before writing logic:

| Information Type | Examples | Interpretation |
| --- | --- | --- |
| Per-record | Topic, partition, offset, key, timestamp, and converted headers | Value at index `i` belongs to the payload at index `i` |
| Per-batch/container | Consumer information or acknowledgment tied to the poll | Applies to the delivery/batch; do not attach to individual payloads as per-record metadata |

A batch can span multiple partitions. If an application logs a single `partition` for the whole batch, that log can be misleading or outright wrong. When auditing individual records, log topic-partition-offset together with the event ID of that specific payload.

Offsets also do not establish a total order across partitions. For instance, offset 900 on partition 0 does not necessarily occur after offset 120 on partition 3 in business time. If per-aggregate ordering is needed, the producer must use an appropriate key so related events land in the same partition, and the consumer must process sequentially within that scope.

## 9. Checking Metadata Size and Integrity

Before processing, validate the sizes of payloads and required header collections:

```java
private static void validateBatch(
        List<?> payloads,
        List<?> topics,
        List<?> partitions,
        List<?> offsets) {

    int size = payloads.size();
    if (topics.size() != size
            || partitions.size() != size
            || offsets.size() != size) {
        throw new IllegalArgumentException(
                "Payload and per-record metadata sizes differ");
    }
}
```

Not every header is mandatory. A Kafka key may be null; an application header may be absent; a mapper may omit optional headers from the message. Validate sizes only for metadata your logic genuinely requires. For optional headers, handle nulls or missing entries explicitly.

If required metadata is missing, never silently attach another record's metadata to a payload. Abort batch processing or route through error handling per policy, recording the position and event ID for investigation.

## 10. Handling Per-Element Conversion Failures

During batch conversion, one record can fail deserialization/conversion even when other records in the same batch are valid. A Spring Kafka batch converter can represent a failed payload as `null` at the corresponding index and expose failure details in the `KafkaHeaders.CONVERSION_FAILURES` header when a supporting converter mechanism is used.

Therefore, never assume every element in `List<T>` is non-null. If the application must distinguish a conversion error from a valid null business payload, inspect conversion failure metadata by index and handle it explicitly.

Example checking an element before invoking business logic:

```java
for (int i = 0; i < orders.size(); i++) {
    OrderCreated order = orders.get(i);
    if (order == null) {
        // Match KafkaHeaders.CONVERSION_FAILURES at the same index,
        // log the error and apply the batch/error-handling policy.
        continue;
    }

    processOne(order);
}
```

Do not skip null elements without recording why. If a message failed conversion due to a bad schema, a DLQ or investigation workflow is needed so data is not silently dropped.

## 11. Retries, DLQ, and Acknowledgment in Batch Mode

Batch mode changes the error-handling scope compared to record mode:

- Built-in Spring Cloud Stream binder retries are not supported in the standard way in batch mode; `maxAttempts` is overridden to `1`.
- You can configure `DefaultErrorHandler` via `ListenerContainerCustomizer` to establish appropriate retry behavior at the listener container layer.
- Since Spring Cloud Stream 4.0.2, the Kafka binder supports DLQ for batch consumption. When DLQ is enabled, all records received from the preceding poll may be sent to the DLQ topic, not just the failing element.
- With manual acknowledgment, `Acknowledgment.nack(index, sleep)` can acknowledge items before `index` and request redelivery of the remaining records per container semantics.

Consequently, batch size affects the blast radius of redelivery and DLQ. Overly large batches can cause many valid records to be redelivered or routed to the DLQ alongside one bad record. Design idempotent consumers and test exact failure behavior on your target binder version.

## 12. Per-Record Observability and Tracing

A batch listener does not naturally have a single shared trace context for all elements. A batch can group records from multiple partitions, topics, or producers; each record may carry its own `traceparent` or no tracing header at all.

The Spring Cloud Stream Kafka binder does not automatically propagate per-batch observation/tracing context the way record listeners do. When receiving `Message<List<T>>`, the application can inspect `KafkaHeaders.BATCH_CONVERTED_HEADERS`, extract tracing headers from each payload's corresponding map, and create observations/spans per record if needed.

When logging a batch, record:

- Number of records in the batch.
- Event ID or business key of each record.
- Per-record topic, partition, and offset when traceability is needed.
- Per-record correlation/trace ID, rather than collapsing to one value for the whole batch.
- Processing outcome and errors by index/event ID.

Do not log sensitive payloads or entire headers by default. Select minimal metadata for traceability while protecting credentials.

## 13. Complete Example: Processing a Batch and Auditing Metadata

The example below bundles payloads and metadata into one structure before processing:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

public record OrderRecordContext(
        OrderCreated order,
        String topic,
        Integer partition,
        Long offset,
        Object key,
        Object correlationId
) {}

public class OrderBatchHandler {

    public Consumer<Message<List<OrderCreated>>> processBatch() {
        return message -> {
            List<OrderCreated> payloads = message.getPayload();
            List<String> topics = requiredHeaderList(
                    message, KafkaHeaders.RECEIVED_TOPIC);
            List<Integer> partitions = requiredHeaderList(
                    message, KafkaHeaders.RECEIVED_PARTITION);
            List<Long> offsets = requiredHeaderList(
                    message, KafkaHeaders.OFFSET);
            List<?> keys = optionalHeaderList(
                    message, KafkaHeaders.RECEIVED_KEY);

            validateBatch(payloads, topics, partitions, offsets);

            List<?> converted = optionalHeaderList(
                    message, KafkaHeaders.BATCH_CONVERTED_HEADERS);

            List<OrderRecordContext> records = new ArrayList<>();
            for (int i = 0; i < payloads.size(); i++) {
                OrderCreated order = payloads.get(i);
                if (order == null) {
                    throw new IllegalStateException(
                            "Null payload at batch index " + i);
                }

                Object correlationId = null;
                if (i < converted.size()
                        && converted.get(i) instanceof Map<?, ?> headers) {
                    correlationId = headers.get("correlationId");
                }

                records.add(new OrderRecordContext(
                        order,
                        topics.get(i),
                        partitions.get(i),
                        offsets.get(i),
                        i < keys.size() ? keys.get(i) : null,
                        correlationId));
            }

            records.forEach(this::processOne);
        };
    }

    private static <T> List<T> requiredHeaderList(
            Message<?> message, String name) {
        List<T> values = optionalHeaderList(message, name);
        if (values.isEmpty()) {
            throw new IllegalStateException("Missing batch header: " + name);
        }
        return values;
    }

    private static <T> List<T> optionalHeaderList(
            Message<?> message, String name) {
        Object value = message.getHeaders().get(name);
        if (value instanceof List<?> list) {
            @SuppressWarnings("unchecked")
            List<T> typed = (List<T>) list;
            return typed;
        }
        return List.of();
    }

    private static void validateBatch(
            List<?> payloads,
            List<?> topics,
            List<?> partitions,
            List<?> offsets) {
        int size = payloads.size();
        if (topics.size() != size
                || partitions.size() != size
                || offsets.size() != size) {
            throw new IllegalStateException(
                    "Payload and metadata collections are misaligned");
        }
    }

    private void processOne(OrderRecordContext context) {
        System.out.printf("Processing %s at %s-%d@%d, correlation=%s%n",
                context.order().orderId(),
                context.topic(),
                context.partition(),
                context.offset(),
                context.correlationId());
    }
}
```

This example illustrates code organization; add constructors, bean registration, domain models, and error policies suited to your project. In a real application, extract the header-reading helper and mapping step into a separate component for easier unit testing.

## 14. Testing Payload and Header Correlation

Unit tests should verify that metadata at a given index binds to the matching payload. You can construct `Message<List<OrderCreated>>` with `MessageBuilder` using list-valued headers:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class BatchHeaderMappingTest {

    @Test
    void alignsHeadersWithPayloadIndex() {
        List<OrderCreated> orders = List.of(
                new OrderCreated("ORD-1", 1000),
                new OrderCreated("ORD-2", 2000));

        Message<List<OrderCreated>> message = MessageBuilder
                .withPayload(orders)
                .setHeader(KafkaHeaders.RECEIVED_TOPIC,
                        List.of("orders.created", "orders.priority"))
                .setHeader(KafkaHeaders.RECEIVED_PARTITION,
                        List.of(1, 0))
                .setHeader(KafkaHeaders.OFFSET,
                        List.of(10L, 25L))
                .build();

        List<?> topics = (List<?>) message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC);
        List<?> offsets = (List<?>) message.getHeaders()
                .get(KafkaHeaders.OFFSET);

        assertEquals("orders.created", topics.get(0));
        assertEquals(10L, offsets.get(0));
        assertEquals("orders.priority", topics.get(1));
        assertEquals(25L, offsets.get(1));
    }
}
```

This test verifies the indexing contract in application code, but does not prove the real Kafka binder populates batch headers properly. Add integration tests with Kafka to confirm metadata maps correctly across polling, batch conversion, and header mapping.

## 15. Essential Integration Test Scenarios

For a batch consumer, test at minimum:

1. A batch containing a single record.
2. A batch containing multiple records from the same partition.
3. A batch containing records from multiple partitions.
4. A batch receiving data from multiple topics if the binding subscribes to multiple topics.
5. Records with a null key or missing application headers.
6. Custom headers mapped into `BATCH_CONVERTED_HEADERS` at the exact right index.
7. One unconvertible payload with its conversion failure identified at the exact index.
8. A batch with a failing element and retry/DLQ/acknowledgment behavior matching configuration.
9. Consumer restart or rebalance while processing a batch.
10. Batch size varying with `max.poll.records` and available data.

The Test Binder is helpful for testing functions and bindings, but cannot replace Kafka integration tests when verifying offsets, partitions, header mapping, batch conversion, and DLQ.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Cannot read headers in the function | Function accepts `List<T>` instead of `Message<List<T>>` | Change the signature to `Message<List<T>>` when metadata is needed. |
| Every payload gets the same partition/offset | Code reads index 0 of a header and reuses it for the whole batch | Read header collections and index them alongside the payload. |
| `ClassCastException` when reading headers | Wrong cast or header mapper returned a different type | Check runtime type and mapper configuration before casting. |
| Header collection is shorter than payload list | Optional header missing, inconsistent mapping, or wrong assumptions | Validate required headers and halt on inconsistent data. |
| `List<Message<T>>` fails to bind | Signature is not a batch type supported by the Kafka binder | Use `List<T>` or `Message<List<T>>`. |
| Tracing has only one context for the whole batch | Treating the batch as a single business message | Read `BATCH_CONVERTED_HEADERS` and handle tracing per record. |
| Multiple records sent to DLQ when one fails | Batch DLQ applies to the entire poll batch per binder configuration | Evaluate batch size, retries, manual nack, and idempotency. |
| Null records silently skipped | Conversion failure or `KafkaNull` left unhandled | Inspect null values and conversion failure metadata by index. |

## 17. Safe Batch Processing Workflow

When building a batch consumer that must correlate headers, follow this sequence:

1. Enable `consumer.batch-mode` on the right input binding.
2. Choose `Message<List<T>>` when metadata is required.
3. Identify which headers are per-record metadata and which are batch-level metadata.
4. Retrieve header collections via `KafkaHeaders` constants rather than hard-coded strings where possible.
5. Validate type, presence, and size of required headers.
6. Pair payloads and metadata using the same index.
7. Convert into a record context/envelope if filtering, sorting, or parallel processing is needed.
8. Handle null payloads and conversion failures explicitly.
9. Design retries, DLQ, and acknowledgments with batch scope in mind.
10. Test with multi-partition batches and observe by event ID / topic-partition-offset.

## References

- [Spring Cloud Stream Kafka Binder — Consuming Batches](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/consume-batches.html)
- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring for Apache Kafka — Batch Listener Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)

Cross-reference the documentation for the exact Spring Cloud Stream Kafka binder and Spring Kafka versions you are using, especially regarding batch header mapping, conversion failures, tracing, and acknowledgment.

## Conclusion

In Spring Cloud Stream's Kafka batch mode, `List<T>` provides only payloads; to read metadata you must use `Message<List<T>>`. Per-record headers are represented as collections aligned with the payload list, so they must be accessed by the same index. `KafkaHeaders.BATCH_CONVERTED_HEADERS` provides per-element converted header maps when supported by the mapper. Validating header types and sizes, bundling payloads with metadata into a unified structure, and testing multi-partition batches prevent misattributing topics, partitions, offsets, keys, or correlation IDs across events.
