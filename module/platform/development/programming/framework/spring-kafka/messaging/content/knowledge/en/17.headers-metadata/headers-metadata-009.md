# Header size limits and overhead

## 1. What are Kafka headers used for?

A Kafka record has a key, value, timestamp, and headers. Key/value usually carry the main event data; headers carry small metadata accompanying the record, such as correlation ID, event type, schema version, tenant ID, or trace context.

In Spring Kafka, applications can add headers when sending via `ProducerRecord` or `Message<?>`, and read headers on the consumer via `ConsumerRecord.headers()` or `@Header`. Headers are useful for passing routing, observability, and message-processing information without embedding all metadata into the business payload.

However, headers are not free. Every header increases record size, serialization/deserialization cost, storage, replication, and network transmission. Kafka has no universal dedicated limit like `max.header.bytes` or `max.header.count`; headers are constrained by record batch/request size limits and limits enforced by the application itself.

Therefore, treat headers as a place for small, stable metadata useful to multiple consumers. Large data or primary business data should reside in the value or an appropriate storage system.

## 2. Header structure and size calculation

A Kafka header consists of:

- **Key**: header name as a string.
- **Value**: byte array (`byte[]`); can encode UTF-8 strings, small JSON, or an agreed binary format.

Kafka allows multiple headers with the same key. Header order is preserved in the record; when reading with `lastHeader(name)`, the application receives the last header with that name. Thus, adding duplicate header names can increase size and create ambiguity if producers/consumers do not agree on handling.

In Kafka's wire format, a record stores the header count and each key/value pair along with length fields. Header size is therefore not just the sum of value bytes. There are additional bytes for key names, header count, and length-encoding fields.

Header data can be approximated as follows:

\[
H \approx V(n) + \sum_{i=1}^{n}\bigl(V(|k_i|)+|k_i|+V(|v_i|)+|v_i|\bigr)
\]

Where:

- `n` is the number of headers.
- `k_i` is the UTF-8 encoded header name.
- `v_i` is the value as bytes.
- `V(x)` represents the number of bytes required to encode length `x` in Kafka's format.

This illustrates header overhead; actual record size also includes timestamp/offset deltas, attributes, key, value, record framing, and batch overhead. If the record is compressed, stored/transmitted size may differ from uncompressed size.

### String length is not equal to byte count

When measuring string headers, do not use `String.length()` as the byte size. `String.length()` counts UTF-16 code units in Java, whereas header keys are encoded to bytes and values are converted to bytes by the application. For Vietnamese or non-ASCII characters, the UTF-8 byte count can exceed the character count.

```java
String correlationId = "don-hang-1001";
byte[] value = correlationId.getBytes(StandardCharsets.UTF_8);

int byteLength = value.length;
```

Standardize encoding across all producers/consumers, typically UTF-8 for string headers.

## 3. Which Kafka limits apply to headers?

Kafka controls data size at the record batch and request levels. Headers live inside the record and thus count toward this size. An oversized header can push a record/batch over the limit even when the business value is small.

Important configurations include:

| Configuration | Scope | Role |
|---|---|---|
| `max.request.size` | Producer | Limits the request size a producer sends; also acts as the practical limit on an uncompressed record batch the producer can build |
| `message.max.bytes` | Broker | Limits the record batch size accepted by the broker; check alongside topic configuration and Kafka version |
| `max.message.bytes` | Topic | Can override the broker-level batch limit for a specific topic |
| `fetch.max.bytes` | Consumer | Limits the maximum data the broker returns in a single fetch response |
| `max.partition.fetch.bytes` | Consumer | Limits fetched data for a single partition in one request |
| `replica.fetch.max.bytes` | Follower broker | Limits data a follower fetches from the leader in one request |

Property names and defaults may vary by Kafka version or packaging. Verify actual broker, topic, producer, and consumer configurations rather than relying on a generic default number.

Key points to remember:

- `max.request.size` is not a header-specific limit; it applies at the producer request/record batch level.
- `message.max.bytes` and `max.message.bytes` limit the record batch, which includes key, value, and headers.
- Consumer fetch limits affect how data is returned; Kafka makes an exception for the first batch so consumers can still make progress when a batch exceeds the configured fetch limit.
- Replication must also be able to transport batches. Follower fetch settings should be reviewed when allowing large records.

Do not raise every limit just so a large header can pass through. Increasing record limits impacts memory, network, brokers, and consumers; clearly establish the requirement before making changes.

## 4. No dedicated header limit does not mean unlimited

Kafka core does not provide a standalone standard configuration to cap the header count or total header bytes per record. However, every header still consumes record batch size and is subject to overall producer/broker limits.

Applications should enforce their own policy, for example:

- Maximum of 16 custom headers per record.
- Total bytes of header names and values not exceeding 8 KiB.
- A single header value not exceeding 2 KiB.
- Only header names in an agreed list are permitted.
- Disallow duplicate header names for single-valued fields.

The numbers above are only examples of an **application-chosen budget**, not Kafka defaults. Appropriate limits must be based on workload, internal protocols, and system record limits.

Enforcing limits at the producer boundary rejects abnormal data before sending, rather than waiting for the broker to return `RecordTooLargeException` or letting consumers encounter hard-to-process records.

## 5. Measuring header count and size in Java

You can approximate header bytes before sending. The following code counts headers and sums key/value bytes, excluding Kafka length fields and record overhead:

```java
public record HeaderSize(int count, long payloadBytes) {}

public final class HeaderSizer {

    private HeaderSizer() {}

    public static HeaderSize measure(Headers headers) {
        int count = 0;
        long bytes = 0;

        for (Header header : headers) {
            count++;
            bytes += header.key().getBytes(StandardCharsets.UTF_8).length;

            byte[] value = header.value();
            if (value != null) {
                bytes += value.length;
            }
        }

        return new HeaderSize(count, bytes);
    }
}
```

The result can be used to enforce policy:

```java
private static final int MAX_CUSTOM_HEADERS = 16;
private static final long MAX_HEADER_PAYLOAD_BYTES = 8 * 1024;

void validateHeaders(Headers headers) {
    HeaderSize size = HeaderSizer.measure(headers);

    if (size.count() > MAX_CUSTOM_HEADERS) {
        throw new IllegalArgumentException("Too many Kafka headers");
    }

    if (size.payloadBytes() > MAX_HEADER_PAYLOAD_BYTES) {
        throw new IllegalArgumentException("Kafka headers exceed application budget");
    }
}
```

This is an approximate header payload measurement. It does not replace checking final record/batch size because framing, key/value, record metadata, and compression also apply. If an exact budget is required, measure actual serialized records in integration tests or appropriate producer instrumentation.

## 6. Adding headers with ProducerRecord

`ProducerRecord` allows adding headers before sending:

```java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event,
        String correlationId,
        String traceParent) {

    ProducerRecord<String, OrderCreated> record =
            new ProducerRecord<>("orders", event.orderId(), event);

    record.headers()
            .add("event-type", "OrderCreated".getBytes(StandardCharsets.UTF_8))
            .add("schema-version", "1".getBytes(StandardCharsets.UTF_8))
            .add("correlation-id", correlationId.getBytes(StandardCharsets.UTF_8));

    if (traceParent != null) {
        record.headers().add(
                "traceparent", traceParent.getBytes(StandardCharsets.UTF_8));
    }

    validateHeaders(record.headers());
    return kafkaTemplate.send(record);
}
```

All headers in the example are small metadata. `event-type` and `schema-version` help consumers understand the payload contract; `correlation-id` links processing steps; `traceparent` carries trace info per tracing standards if the system is integrated.

Do not put the entire `OrderCreated` object into headers. The primary payload belongs in the value; headers only supplement information needed for processing or observability.

## 7. Using Spring Message and KafkaHeaderMapper

Spring Kafka supports sending `Message<?>` to combine payload with Spring Messaging headers:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders")
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("correlation-id", correlationId)
        .setHeader("schema-version", "1")
        .build();

kafkaTemplate.send(message);
```

`KafkaTemplate` converts the Spring message into a Kafka record. `KafkaHeaderMapper` maps headers between Spring Messaging and Kafka. Mapper configuration can affect how headers are serialized, especially for types other than strings or byte arrays.

To minimize overhead and avoid cross-language differences, prefer `String` or `byte[]` headers with explicit encoding/conventions. Avoid passing arbitrary Java objects in headers if consumers might be written in Python, Go, or another platform.

Spring Kafka may add type metadata for some headers when the mapper converts complex values. This helps restore types on Spring consumers but also adds extra headers/bytes and depends on mapper configuration. Inspect actual records when using custom header mappers or non-simple header types.

## 8. Reading headers on the consumer

Consumers can read directly from `ConsumerRecord`:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    Header correlationHeader =
            record.headers().lastHeader("correlation-id");

    String correlationId = correlationHeader == null
            ? null
            : new String(correlationHeader.value(), StandardCharsets.UTF_8);

    orderService.process(record.value(), correlationId);
}
```

Or map a header to a parameter using `@Header`:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(
        OrderCreated event,
        @Header(name = "correlation-id", required = false) byte[] correlationBytes) {

    String correlationId = correlationBytes == null
            ? null
            : new String(correlationBytes, StandardCharsets.UTF_8);

    orderService.process(event, correlationId);
}
```

When a header key can appear multiple times, explicitly decide whether to use `lastHeader()` or iterate over all headers with that name. Do not assume headers are always unique if the producer has no enforcement policy.

## 9. Where do large headers increase costs?

### Storage size

Headers live inside the record log. Large headers make record batches larger, increasing required storage capacity and data replicated across replicas. With long retention or high-throughput topics, a few extra KiB per record can accumulate into a substantial amount of data.

### Network and replication

Producers send headers with records to the broker. Brokers replicate record batches according to the replication factor. Consumers fetching records also receive headers, even if the listener does not use them. Therefore, large headers increase network traffic along producer → broker, broker → follower, and broker → consumer paths.

### CPU, allocation, and garbage collection

String or object headers must be converted into bytes. Consumers may allocate additional objects when mapping headers back to Spring Message. Many or large headers increase allocations, byte copying, JSON parsing, and garbage collection pressure.

### Observability and logs

Headers used for tracing or correlation may appear in logs, tracing spans, or DLTs. Oversized headers bloat logs, raise telemetry storage costs, and risk exposing data if they contain sensitive info.

### Cost with multiple consumer groups

Kafka does not create a separate log copy per consumer group; records are stored according to the partition's replication factor. However, each group reading records receives those headers via fetch. Multiple independent groups can therefore multiply total transmitted and processed bytes, even though log storage does not multiply by group count.

## 10. Estimating header cost at scale

Suppose:

- Each record averages 1.5 KiB of headers.
- The topic receives 20,000 records/second.
- Replication factor is 3.

Raw header data sent by producers to the topic per second is approximately:

\[
20{,}000 \times 1.5\text{ KiB} \approx 29.3\text{ MiB/s}
\]

With a replication factor of 3, the header volume stored across cluster replicas is roughly three times the raw header data, before accounting for compression, segments/indexes, and other overhead. If multiple consumer groups read independently, each group adds additional fetch traffic containing headers.

This is only an estimate to illustrate impact at scale; actual footprint depends on compression, batching, retention, replication, and read rates. Headers should not be judged solely by the size of a single record. Multiply by record rate and retention duration.

## 11. Does compression eliminate header overhead?

Kafka can compress record batches using codecs such as gzip, snappy, lz4, or zstd depending on version and configuration. Headers are serialized with the record, so header data can also benefit from compression if values repeat or have compressible structure.

However:

- Compression does not make headers disappear; consumers still must decompress and receive headers.
- Random headers or unique values like UUIDs compress less effectively than repetitive strings.
- Producers still must serialize and hold uncompressed data in memory.
- Producer/broker limits have specific rules on requests and record batches; do not rely on compression to allow unbounded headers.
- Compression increases CPU cost and can trade off latency.

Measure compression ratios and throughput with real data. If headers contain a unique correlation ID per record, do not assume they will compress significantly.

## 12. What should and should not go into headers?

| Data type | Where should it go? | Reason |
|---|---|---|
| Correlation ID / trace context | Header | Small metadata, used to link processing steps |
| Event type / schema version | Header or schema envelope | Helps identify payload contract; requires consistent convention |
| Small tenant ID | Header if used for routing/observability and non-sensitive | Easy to filter/observe, but requires access and trust checks |
| User ID or account ID | Usually in payload; put in header only when explicitly required | Can be sensitive data and leak via logs/telemetry |
| JWT, access token, API key | Do not put in Kafka headers | Easily copied across brokers, DLTs, logs, and consumers |
| Entire HTTP request headers | Do not copy verbatim | Many unnecessary fields, may contain secrets and bloat records |
| Full stack trace | Logs or error tracking system; DLT only when policy dictates | Long content, easily exposes internal data and increases record size |
| Large JSON context or binary attachment | Value or object storage; header holds reference only | Headers are unsuitable for large data |
| Files, images, document content | Object storage; value holds controlled ID/URI | Reduces Kafka load and eases data lifecycle management |

A good header has a short name, clear meaning, simple data type, and stable contract. Do not put temporary debugging info onto every record without a concrete operational need.

## 13. Duplicate header names, high counts, and schema conventions

Kafka allows duplicate header names, but applications must define usage rules:

- Single-valued headers like `correlation-id`, `event-type`, `schema-version` should appear at most once.
- Multi-valued headers should only be used when the contract explicitly specifies order and interpretation.
- Use `lastHeader()` when the convention calls for the latest value; if all values are needed, iterate over `headers().headers(name)`.
- Do not add the same header across multiple layers without defining who owns the final value.
- Standardize header names and encoding so Java, Python, Go, or .NET producers can exchange data consistently.

Manage the list of allowed headers as part of the event contract. When renaming or changing header types, evaluate backward compatibility just like payload schema changes.

## 14. Headers and Kafka metadata are not the same

In operations, distinguish application-attached headers from Kafka metadata provided by the broker/consumer:

| Information | Source | Example |
|---|---|---|
| Custom header | Producer or application | `correlation-id`, `event-type`, `tenant-id` |
| Record key/value | Producer | `orderId`, `OrderCreated` |
| Topic/partition/offset | Kafka record metadata | `orders`, partition `2`, offset `120` |
| Timestamp | Producer or broker per timestamp type | Create time / log append time |
| Consumer group committed offset | Kafka group coordinator | Committed progress per group and partition |

Topic, partition, and offset do not need to be copied into custom headers for consumers to know where a record came from; `ConsumerRecord` and Spring Kafka's `KafkaHeaders` already supply this information. Copying metadata manually can produce duplicate or stale data if records are forwarded to another topic.

## 15. Monitoring and controlling header costs

Monitor headers at both application and Kafka layers:

- Measure header count and total header bytes before publishing.
- Record header size percentiles (p50, p95, p99) by topic/event type.
- Track record size, producer send failures, and `RecordTooLargeException` errors.
- Observe broker request size, network throughput, replication traffic, and disk growth.
- Monitor consumer fetch bytes, processing latency, and garbage collection when changing header schemas.
- Audit DLTs and logs to ensure exceptions/headers do not leak sensitive data.

You can emit application metrics like `kafka.headers.count` and `kafka.headers.bytes` by topic, but avoid using header values or correlation IDs as metric tags since cardinality will explode. Use topic/event type as controlled dimensions; correlation ID belongs in logs/traces rather than metric labels.

When detecting abnormal header growth, trace the producer or event schema version generating those headers. Trimming unnecessary headers is usually more effective than raising cluster-wide limits.

## 16. Process for designing a header budget

1. List the metadata genuinely needed between producer and consumer.
2. Define data type, encoding, and single/multi-value rules for each header.
3. Set application-level limits on header count, total bytes, and individual value sizes.
4. Measure headers using actual UTF-8 bytes or byte arrays; do not use Java character count as size.
5. Check total record/batch size against `max.request.size`, `message.max.bytes`/`max.message.bytes`, and related fetch settings.
6. Test oversized records, duplicate headers, missing headers, and invalid headers.
7. Measure throughput, network, storage, compression, and consumer allocations with realistic data.
8. Monitor after deployment and keep header conventions compatible across producer/consumer versions.

If payload or metadata exceeds the budget, move large data into the value or object storage and pass only a small reference in headers or payload. Ensure references have appropriate access controls, expiration, and protection mechanisms.

## 17. Summary

- Headers are key/string and value/`byte[]` pairs attached to each Kafka record; Kafka allows multiple headers with the same name.
- Headers reside inside record batches and are therefore subject to producer, broker, and topic size limits; Kafka has no universal standalone header limit.
- Header size includes names, values, and length/count encoding overhead; strings must be measured in bytes after encoding.
- Large headers increase storage, replication traffic, consumer fetch, CPU, allocations, and telemetry costs.
- Compression can reduce stored/transmitted bytes but does not eliminate serialization, decompression, and header-processing costs.
- Use headers for correlation ID, trace context, event type, and schema version; avoid tokens, secrets, stack traces, and large payloads.
- Set an application header budget, measure actual sizes, and monitor record sizes rather than relying on a default header limit.
- Distinguish custom headers from Kafka metadata such as topic, partition, offset, and timestamp.

Designing small, well-contracted headers enables Spring Kafka applications to pass essential metadata while keeping record sizes, storage costs, network usage, and processing overhead under control across all consumer groups.
