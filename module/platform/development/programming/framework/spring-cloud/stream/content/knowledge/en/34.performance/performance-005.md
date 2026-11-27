# Evaluating Compression, Payload Size, and Serialization Cost

The performance of a Spring Cloud Stream pipeline depends not only on broker speed or consumer count. Every message must also be converted from a Java object to bytes, potentially compressed, transmitted over the network, stored, read back, decompressed, and deserialized. These steps consume CPU, memory, bandwidth, and processing time.

Compression can reduce bytes transferred and storage footprint, but increases CPU usage. A compact serialization format can shrink payloads, but requires schemas, generated code, or schema lookup steps. A large payload can increase latency, heap allocation, GC pressure, and the risk of hitting broker message size limits. No single codec or format fits every workload; measure on representative data at both client and broker levels.

## 1. Path of a message

A message in an event-driven application typically passes through these steps:

~~~mermaid
flowchart LR
    A["Business object"] --> B["Serialize"]
    B --> C["Byte payload"]
    C --> D["Compress"]
    D --> E["Publish via binder"]
    E --> F["Broker / network / storage"]
    F --> G["Consume"]
    G --> H["Decompress"]
    H --> I["Deserialize"]
    I --> J["Function / Consumer"]
~~~

The exact order may vary by binder and serializer. For example, Kafka compresses record batches at the producer; RabbitMQ typically treats bodies as opaque bytes and the application must explicitly compress if desired; Pulsar producers have their own compression options. Regardless of how it is implemented, identify exactly which component compresses and which decompresses to avoid double compression or mis-deserializing data.

Main costs:

| Component | Potential costs |
|---|---|
| Serialization | CPU encoding, byte array allocation, reflection or generated-code work |
| Compression | Compression CPU, temporary buffers, latency scaling with payload size |
| Network | Bandwidth, packets, TLS overhead, and transmission time |
| Broker storage | Log/queue disk space, disk I/O, replication |
| Decompression | CPU and memory to restore the payload |
| Deserialization | CPU decoding, object graph creation, validation, and GC |

For small messages, serialization and scheduling may take more time than data transfer. For large messages or repetitive strings, compression can significantly cut network and storage usage. Measure to determine whether the workload is limited by CPU, network, broker, or application code.

## 2. Where does payload size matter?

Payload size is the byte count of message data at a specific boundary. Distinguish at least:

- Object size in heap: not equivalent to wire size.
- Serialized size: bytes before compression.
- Compressed size: bytes transmitted or stored per codec.
- Protocol record/frame/batch size: may include key, headers, metadata, and framing.

For instance, an `OrderEvent` having 15 Java fields does not mean the message takes 15 fixed units of bytes. Strings are encoded into bytes per charset, JSON field names repeat, timestamps/numbers have text representations, and schema IDs or headers add bytes. Binary formats typically encode data types directly and omit repeated field names.

Large payloads impact:

1. Bandwidth between the application and the broker.
2. Broker disk and replication traffic.
3. Serialize, compress, decompress, and deserialize duration.
4. Batch sizes and how many records fit in one request.
5. Heap allocations, buffers, and garbage collection.
6. Risk of exceeding producer, broker, consumer, or subscription limits.
7. Retry cost: large messages resent multiple times multiply resource consumption.

Do not track only messages per second. A pipeline processing 5,000 msg/s with 1 KB payloads carries a very different byte load than one processing 5,000 msg/s with 200 KB payloads.

### 2.1. Measuring size at multiple boundaries

For each event type, record:

| Quantity | How to measure | Purpose |
|---|---|---|
| Serialized bytes | Byte array length after serializer | Evaluate format and schema |
| Compressed bytes | Byte array length after application codec | Compute compression ratio |
| Broker record/message size | Broker metrics or tools | Assess actual size received by the broker |
| End-to-end payload size | Per application contract | Compare across services |

Compression ratio can be calculated as:

\[
R = \frac{\text{compressed bytes}}{\text{serialized bytes}}
\]

For example, if a 100 KB payload shrinks to 25 KB after compression, `R = 0.25`, representing roughly a 75% byte reduction at the measured boundary. Always state the denominator and measurement point; never compare one broker's compressed body against another broker's total request size.

## 3. Serialization formats: JSON vs. binary

Serialization turns objects into a form transmittable through the broker. Format choice affects size, CPU, readability, schema evolution, and coupling between producers and consumers.

| Format | Strengths | Trade-offs |
|---|---|---|
| JSON | Human-readable, easy to debug, broad support, flexible schema | Repeated field names, text numbers/timestamps, parsing/allocations can cost CPU |
| Avro | Compact binary, explicit schema, supports schema evolution via compatibility rules | Requires schemas and typically a schema registry or distributed schemas |
| Protocol Buffers | Compact binary, fast generated code, efficient field tags | Requires managing `.proto` files and compatibility rules on schema changes |
| CBOR | Binary representation for JSON-like data models | Ecosystem and schema governance depend on platform |

Do not conclude binary is always faster than JSON in every case. Small payloads can be dominated by serializer invocation, object creation, or message conversion overhead. JSON with proper Jackson configuration can be fast enough and easy to operate. Binary typically pays off at high throughput, with repetitive payloads, or when significant byte reduction is required.

### 3.1. JSON serialization example

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderEvent(
    String eventId,
    String orderId,
    String customerId,
    BigDecimal amount,
    Instant occurredAt,
    String status
) {}
~~~

With Jackson:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();

byte[] bytes = mapper.writeValueAsBytes(event);
OrderEvent decoded = mapper.readValue(bytes, OrderEvent.class);
~~~

In real applications, `ObjectMapper` configuration should be centrally managed and shared, include necessary Java time modules, and be verified by compatibility tests. Do not create a new `ObjectMapper` per message because initializing mappers and modules incurs unnecessary overhead.

### 3.2. Schemas and schema evolution

When producers and consumers are deployed independently, the schema is the contract between them. Define:

- Which fields are required and which may be absent?
- Are default values provided?
- Are field type changes compatible?
- Can old consumers read messages produced by new producers?
- Where is the schema ID/version carried?
- What are the schema registry's caching and availability policies?

Avro, Protobuf, and JSON Schema have different compatibility rules. Verify `BACKWARD`, `FORWARD`, or `FULL` policies in your schema management tool; do not rely solely on code compiling cleanly.

Schema registries are typically cached on the client. Do not assume every message makes a network call to the registry, but cold starts, cache misses, registry outages, or new schema registrations can add latency and failure modes. Measure encode/decode duration separately from registry interaction duration if applicable.

## 4. CPU and memory cost of serialization

A serializer can allocate many temporary objects: `String`, byte arrays, buffers, wrappers, maps, and metadata. A deserializer can build an object graph larger than the original byte payload. This affects the garbage collector, especially at high message rates.

Common causes:

- Serializing the same object multiple times for logging, publishing, and auditing.
- Converting an object to a JSON `String` and then encoding the `String` to UTF-8 bytes.
- Instantiating a new `ObjectMapper` or serializer per message.
- Using reflection or uncached schema lookups.
- Deserializing an entire large payload when only a few fields are needed.
- Creating multiple byte-array copies during compression, decompression, or converter transitions.
- Holding payloads in internal queues too long, increasing heap retention.

Measure allocation rate and GC alongside CPU. An optimization might lower CPU yet increase buffer retention or peak memory; throughput rises in short benchmarks while p99 latency degrades in long runs.

### 4.1. Avoiding redundant serialization

Avoid doing this:

~~~java
String jsonForLog = mapper.writeValueAsString(event);
byte[] payload = mapper.writeValueAsBytes(event);
publisher.send(payload);
~~~

The snippet above encodes the same object twice. If logging is needed, log selective identifier fields or byte counts; avoid logging full payloads unnecessarily.

~~~java
byte[] payload = mapper.writeValueAsBytes(event);
logger.debug("Publishing eventId={}, payloadBytes={}",
    event.eventId(), payload.length);
publisher.send(payload);
~~~

If application-layer compression is needed, compress the already-serialized byte array rather than re-serializing the object. Ensure the byte array is not mutated after being handed to an asynchronous publisher.

## 5. How does compression work?

Compression finds repeating structures or patterns that can be represented in fewer bytes. JSON often contains repeated field names, status strings, and recurring property names, so it tends to compress well. Payloads that are already compressed, encrypted, or contain random data rarely compress much further.

Common codecs:

| Codec | General characteristics | When to consider |
|---|---|---|
| gzip/DEFLATE | Often strong ratio, ubiquitous, CPU can be higher than speed-oriented codecs | Limited bandwidth or large text payloads |
| Snappy | Speed-first, moderate compression ratio | High throughput needing low CPU cost |
| LZ4 | Fast decompression, often suited for high-speed pipelines | When latency and CPU matter |
| Zstandard (Zstd) | Tunable compression levels balancing ratio and speed | When tuning for load and CPU capacity |
| ZLIB | Widely supported codec with adjustable levels | Compatibility and general-purpose compression |

These are relative characteristics; real performance depends on library version, level, batch size, data, and CPU. Benchmark rather than picking a codec from a generic ranking table.

### 5.1. Compression ratio and throughput

Suppose a batch contains 1 MB of JSON data:

| Hypothetical result | Compressed size | Ratio | Bytes saved |
|---|---:|---:|---:|
| Codec A | 300 KB | 0.30 | 70% |
| Codec B | 420 KB | 0.42 | 58% |
| Uncompressed | 1,000 KB | 1.00 | 0% |

If Codec A consumes substantially more CPU, it can reduce messages processed per second when the producer is already CPU-bound. Codec B has a worse ratio yet may achieve higher throughput and lower latency.

Evaluate simultaneously:

- Compression ratio.
- CPU time for encode/compress and decompress.
- Throughput in messages/s and bytes/s.
- Producer latency and consumer processing latency.
- Network throughput.
- Broker disk usage and replication traffic.
- Allocation rate, heap, and GC pauses.

## 6. Kafka: record-batch compression

A Kafka producer compresses record batches before sending them to the broker. Because compression operates across a batch, multiple records on the same partition offer better pattern matching than compressing small records independently.

Common producer codecs include:

- `none`
- `gzip`
- `snappy`
- `lz4`
- `zstd`

The producer property `compression.type` selects the codec. Kafka consumers decompress batches on read; the application does not need to call `GZIPInputStream` manually when using standard Kafka serializers/deserializers.

Example per-output-binding configuration in the Spring Cloud Stream Kafka binder:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                compression.type: zstd
                linger.ms: 10
                batch.size: 65536
~~~

In this example:

- `compression.type` picks the codec for the producer binding.
- `linger.ms` gives the producer extra time to accumulate records into a batch before sending.
- `batch.size` sets the target batch size per partition.

This illustrates the Kafka binder property model; verify prefixes and property names against your project's Spring Cloud Stream Kafka binder version. With multiple output bindings, configure each binding individually so unnecessary codecs are not applied to every stream.

### 6.1. Batch size and linger

Larger batches can improve compression ratios and reduce requests, but can increase the time records wait for a batch to fill. Increasing linger helps form batches at medium or low load, at the cost of extra pre-send latency.

Do not immediately maximize `batch.size`. Watch:

- `batch-size-avg` and `records-per-request-avg`.
- Request rate and producer request latency.
- Buffer pool wait time.
- Per-partition throughput.
- p95/p99 publish latency.

If each partition receives records very sparsely, raising `batch.size` may not produce larger batches. If partition count increases, each partition receives fewer records in the same interval and batching efficiency can drop.

### 6.2. Compression on the broker and consumer

A Kafka broker can store batches with the producer's codec or enforce a broker compression policy depending on configuration. Consumer clients handle decompression per the record batch format. Do not gzip JSON payloads at the application layer and also enable Kafka batch compression without measuring; double compression usually adds CPU while the second pass saves few bytes.

Request, record batch, and fetch sizes have separate limits. Properties such as producer `max.request.size`, broker `message.max.bytes` or topic `max.message.bytes`, and consumer `max.partition.fetch.bytes` and `fetch.max.bytes` must be reviewed together. Compression is not a reliable way to bypass message size limits; an oversized compressed batch or record can still be rejected or fail to fetch as expected.

## 7. RabbitMQ: separating body compression from AMQP transport

AMQP does not automatically compress bodies just because TLS is enabled or the Rabbit binder is used. RabbitMQ generally treats bodies as byte sequences and does not automatically decompress application content. If compression is needed, producers and consumers must agree on codec and metadata.

An application contract might specify:

- Body holds compressed bytes.
- Content type describes the uncompressed data, e.g., `application/json`.
- Content encoding or an equivalent header records `gzip`/`zstd`.
- Consumer reads encoding, decompresses, then deserializes.

Example plain-Java GZIP compression helper:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPOutputStream;

public final class PayloadCompression {

    private PayloadCompression() {
    }

    public static byte[] gzip(byte[] input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(output)) {
            gzip.write(input);
        }
        return output.toByteArray();
    }
}
~~~

The consumer needs matching decompression:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPInputStream;

public static byte[] gunzip(byte[] input) throws IOException {
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    try (GZIPInputStream gzip =
            new GZIPInputStream(new ByteArrayInputStream(input))) {
        gzip.transferTo(output);
    }
    return output.toByteArray();
}
~~~

This is a codec utility, not a complete Rabbit binder configuration. When integrating, use a byte-array serializer/converter or appropriate message converter, set `content-encoding` per your AMQP message properties/header contract, and ensure the consumer decompresses before the JSON/Avro/Protobuf deserializer runs. Do not let a default converter try to parse gzip bytes as JSON text.

Application-level compression shrinks the payload body, yet RabbitMQ still processes messages, headers, queue indexes, routing, and storage. Check broker and client message size limits for your running version. Frame max is a protocol frame limit and should not be treated as the total message size limit.

## 8. Pulsar: producer compression

Apache Pulsar supports producer-side compression. Clients can compress messages or batches before sending to the broker; matching consumers decompress on receipt. Common Java client options include `LZ4`, `ZLIB`, `ZSTD`, `SNAPPY`, and `NONE`, depending on client version.

Example using the Pulsar Java client:

~~~java
import org.apache.pulsar.client.api.CompressionType;
import org.apache.pulsar.client.api.Producer;

// client is an initialized PulsarClient configured with the service URL.
Producer<byte[]> producer = client.newProducer()
    .topic("persistent://public/default/orders")
    .compressionType(CompressionType.ZSTD)
    .create();
~~~

In a Spring Cloud Stream application, configuration may be supplied via Pulsar binder or client properties depending on the binder version. Consult the corresponding binder docs instead of assuming Kafka property names like `compression.type` work on Pulsar.

Compression can save network and storage while consuming CPU on producers and consumers. Measure actual payloads, batching, backlog, and latency. For messages already compressed at the application layer, do not add producer compression unless benchmarks prove a benefit.

## 9. When to compress in the broker client vs. in the application?

| Approach | Compression/decompression point | Advantages | Trade-offs |
|---|---|---|---|
| Kafka producer compression | Kafka producer compresses record batch; consumer decompresses | Native integration, batch compression, app works with normal objects | Specific to Kafka clients; requires producer config tuning |
| Pulsar producer compression | Pulsar producer/client | Native integration with client and batching | Requires proper binder/client config; depends on codec support |
| Rabbit/application compression | Application or converter before publish | Useful when body control or cross-system contracts are needed | Must manage content encoding, compatibility, and decompression |
| Pre-broker shared compression | Producer app compresses bytes | Same payload can traverse multiple brokers | Consumers must know the codec; brokers cannot inspect content |

Prefer native broker-client compression when it meets requirements and handles consumer decompression automatically. Use application-level compression when you need a broker-independent compressed payload contract or must compress before an intermediary layer. Avoid compressing the same content twice.

## 10. Large payloads and broker limits

Each broker and client enforces different size limits. Those limits can apply to messages, record batches, requests, frames, fetches, or buffers; they do not necessarily measure the exact same boundary.

| System | Limits to check | What to watch |
|---|---|---|
| Kafka | Producer request, broker/topic record batch, consumer fetch | Producer, broker, and consumer limits must be compatible |
| RabbitMQ | Broker maximum message size, protocol frame, client memory/buffer | Frame size is not total message size |
| Pulsar | Broker maximum message size, producer/batch, and consumer receive | Check broker, namespace, and client version settings |

If messages are too large, common options are:

1. Remove unnecessary fields or eliminate redundant data.
2. Switch to a binary schema where appropriate.
3. Compress the payload if the data is compressible.
4. Chunk messages under a contract with sequence IDs, chunk counts, and idempotency.
5. Store large blobs in object storage and send an event containing URI, checksum, content type, and metadata.

For payloads of several MB or hundreds of MB, the claim-check pattern is usually much better than pushing entire blobs through the broker. Brokers should transport events and references; object storage handles large content. Ensure proper access permissions, retention periods, checksums, retries, and object cleanup.

Chunking adds complexity: consumers must reassemble all chunks and handle missing, duplicate, or out-of-order chunks, timeouts, and state cleanup. Choose it only when truly required and with an explicit recovery design.

## 11. Compression and TLS solve different problems

Compression shrinks compressible payload bytes. TLS encrypts data in transit and authenticates peers. TLS is not compression, and compression is not encryption.

When using TLS:

- TLS record framing and handshakes carry their own overhead.
- Application payload compression can run before TLS encryption.
- Do not expect TLS to compress content; TLS compression has been removed from modern configurations due to security risks.
- Compressing secret data alongside attacker-controlled data in the same context can create a side-channel; evaluate your threat model if payloads contain secrets.

The typical order is serialize, compress if needed, then TLS encrypts bytes in transit. On the receiving end, TLS decrypts the transport first, then the application/broker client decompresses and deserializes per contract.

## 12. Example measuring serialization and compression

Simple measurements in a unit test can compare sizes, but never use `System.nanoTime` in a short loop as a final benchmark conclusion. JVM warm-up, JIT, GC, and CPU scheduling skew short measurements.

Example collecting sizes:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPOutputStream;

import com.fasterxml.jackson.databind.ObjectMapper;

public final class PayloadSizer {

    public static void main(String[] args) throws IOException {
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        OrderEvent event = new OrderEvent(
            "evt-1001",
            "order-1001",
            "customer-42",
            new java.math.BigDecimal("125.50"),
            java.time.Instant.parse("2026-03-10T10:15:00Z"),
            "ACCEPTED"
        );

        byte[] json = mapper.writeValueAsBytes(event);
        byte[] gzip = gzip(json);

        double ratio = (double) gzip.length / json.length;
        double savedPercent = (1.0 - ratio) * 100.0;

        System.out.printf("serialized=%d bytes%n", json.length);
        System.out.printf("gzip=%d bytes%n", gzip.length);
        System.out.printf("ratio=%.3f%n", ratio);
        System.out.printf("saved=%.1f%%%n", savedPercent);
    }

    static byte[] gzip(byte[] input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(output)) {
            gzip.write(input);
        }
        return output.toByteArray();
    }
}
~~~

Measuring a single event only illustrates the math. Run on a dataset with production-like size and content distributions, including small, medium, and large payloads, highly repetitive data, and incompressible data.

## 13. Benchmarking properly

A useful benchmark answers a concrete question: which codec cuts network usage enough without pushing CPU or p99 latency over budget?

### 13.1. Microbenchmarks

Use JMH to measure in isolation:

- Serializing objects to JSON/Avro/Protobuf.
- Deserializing byte arrays back to objects.
- Compressing and decompressing byte arrays.
- Allocation bytes/op and GC.

JMH handles warm-up, forking, and measurement far better than manual loops. Keep payloads identical across runs and exclude broker/network I/O from microbenchmarks.

### 13.2. End-to-end benchmarks

Run the application against a real broker or production-equivalent environment. Compare:

| Test axis | Suggested values |
|---|---|
| Payload | 1 KB, 10 KB, 100 KB, 1 MB, or real distribution |
| Format | JSON, Avro, Protobuf if supported |
| Codec | `none`, `gzip`, `snappy`, `lz4`, `zstd` per binder |
| Producer batching | Default batch and a few controlled linger/batch settings |
| Concurrency | Single producer, multiple producers, target consumer count |
| Broker | Identical replication, partitions, storage, and network setup |
| Duration | Long enough to observe warm-up, steady state, and GC |

Hold partition count, replication factor, consumer concurrency, message rate, and hardware constant when comparing codecs. Changing multiple variables at once makes it impossible to know where gains came from.

### 13.3. Metrics to record

- Throughput in messages/s and MB/s.
- Producer send latency p50/p95/p99.
- Consumer end-to-end latency p50/p95/p99.
- CPU usage and CPU time per process.
- Allocation rate, heap occupancy, and GC pauses.
- Network bytes in/out.
- Broker disk throughput and log/queue storage usage.
- Compression ratio by payload type and batch.
- Retries, timeouts, record/message-too-large errors, and error rate.

Never rely on averages alone. A codec with good average throughput but poor p99 latency may be unsuitable for latency-sensitive systems.

## 14. Compression level and batch size

Some codecs expose tunable levels. Higher levels generally consume more CPU searching for better compression; incremental gains often diminish rapidly. Do not default to the highest compression level.

With Kafka, batch effectiveness depends on records per partition and batching window. With Pulsar, batching and compression also interact; check client version and producer configuration. With RabbitMQ, application-level compression typically compresses per payload or per application-defined unit, so per-message overhead can be noticeable for small payloads.

Practical rules:

1. Start with default settings and record a baseline.
2. Test a speed-focused codec and a ratio-focused codec.
3. Raise compression level only if the extra bytes saved provide clear value.
4. Tune batching only after observing actual batch sizes.
5. Check latency and memory at low load, not just high load.
6. Evaluate consumer CPU as well, because decompression also has a cost.

## 15. Spring Cloud Stream content type and native encoding

Spring Cloud Stream provides content-type-based message conversion. Binders can convert payload objects to bytes via converters or middleware-native serializers. Properties like `useNativeEncoding` and `useNativeDecoding` control native encoding/decoding in certain binders.

When using Avro/Protobuf or compressed byte payloads:

- Clarify which component is responsible for serialization and deserialization.
- Set a content type matching the message contract.
- If using native encoding, configure serializers/deserializers at the binder/client level.
- If using application converters, ensure converters execute compression and serialization in the right order.
- Never let one side treat gzip bytes as JSON text.
- Test compatibility across different deployed producer and consumer versions.

Exact property names and native encoding behavior depend on the binder. Kafka, Rabbit, and Pulsar do not share identical serializer configurations. Consult the specific binder's documentation instead of copying a property prefix from Kafka to Rabbit/Pulsar.

## 16. Compression, schemas, and versioning

Compression does not replace schema governance. A compressed payload still requires knowing:

- Is the decompressed format JSON, Avro, or Protobuf?
- Does the schema version or schema ID live in headers, an envelope, or the payload?
- Is the codec `gzip`, `zstd`, or another format?
- Do older consumers support that codec?
- If a codec is unrecognized, is the message retried, quarantined, or sent to a DLQ?

If using application-level compression, `content-encoding` must be part of the contract. Do not guess codecs from magic bytes or try multiple codecs sequentially in production; that creates ambiguous behavior and wastes CPU.

During rolling deployments, deploy consumers supporting a new codec before producers begin emitting it. When changing codecs, use explicit headers/versions or separate topics/destinations during migration. Keep the ability to read old data throughout retention and retry windows.

## 17. Common errors and diagnostics

| Symptom | Possible cause | Remediation |
|---|---|---|
| Producer CPU spikes after enabling compression | Codec/level too heavy or batches too small | Measure CPU and ratio; try a faster codec or better batching |
| Consumer CPU rises | Heavy decompression or deserialization | Measure each step; shrink payloads, change codec/format, or scale capacity |
| Ratio near 1.0 | Payload already compressed, encrypted, or incompressible | Disable compression for that binding if no gain |
| Publish latency rises at low load | `linger`/batching holds records waiting to group | Lower `linger` or configure per workload |
| Messages rejected by broker as too large | Incompatible producer/broker/topic limits | Compare each limit; reduce payloads or use object storage |
| Consumer fails to parse payload | Mismatched codec/header or serializer contract | Check content type, content encoding, and decode order |
| Compressed payload is larger than original | Message too small or codec framing overhead | Skip compression below a beneficial threshold |
| Heap/GC spikes sharply | Many temporary byte arrays/objects or long payload retention | Reduce copies, stream where suitable, cap buffers and backlog |
| Schema registry causes latency spikes | Cache misses, registry cold starts, or timeouts | Inspect caching, schema lifecycle, and registry availability |
| One consumer version cannot read new messages | New codec or schema not yet supported | Deploy compatible consumers before producers |

## 18. Decision workflow

1. Collect real payload distributions per event type, not just one sample.
2. Measure serialized bytes and bytes on the broker/network.
3. Measure CPU, allocations, and latency of the current serializer/deserializer.
4. Test another format if serialization represents a significant share.
5. Test native binder compression codecs if supported.
6. For Rabbit or shared contracts, evaluate application-level compression and metadata.
7. Tune batching only after collecting actual batch metrics.
8. Verify producer, broker, consumer, and broker storage limits.
9. Run end-to-end benchmarks under production-like load.
10. Pick the configuration meeting latency, throughput, CPU, and storage SLOs.
11. Roll out backward-compatibly and monitor errors, retries, and DLQ after deployment.

## 19. Pre-optimization checklist

- [ ] Identified payload sizes before and after serialization.
- [ ] Measured compressed bytes and compression ratio per event type.
- [ ] Identified whether serialize, compress, decompress, or deserialize consumes the most CPU.
- [ ] Checked allocation rate, heap, and GC.
- [ ] Compared codecs on representative data.
- [ ] Verified batch size and linger for Kafka/Pulsar if used.
- [ ] Clarified whether compression lives in the broker client or application layer.
- [ ] Avoided double-compressing the same payload without measurable benefit.
- [ ] Producer and consumer agree on content type, content encoding, and schema version.
- [ ] Verified message/request/fetch limits across producer, broker, and consumer.
- [ ] Planned object storage or chunking for very large payloads.
- [ ] Ran end-to-end benchmarks reviewing p95/p99, CPU, network, disk, and GC.
- [ ] Tested older consumers when producers change format or codec.
- [ ] Set up dashboards tracking payload sizes, errors, and latency post-deploy.

## Official References

- [Apache Kafka Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs): `compression.type`, `batch.size`, `linger.ms`, and `max.request.size`.
- [Apache Kafka Broker Configurations](https://kafka.apache.org/documentation/#brokerconfigs): `message.max.bytes` and related broker settings.
- [Apache Kafka Consumer Configurations](https://kafka.apache.org/documentation/#consumerconfigs): `fetch.max.bytes` and `max.partition.fetch.bytes`.
- [Spring Cloud Stream Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html): producer/consumer bindings and Kafka-specific properties.
- [RabbitMQ Publishers](https://www.rabbitmq.com/docs/publishers): publishing, message bodies, and publisher confirms.
- [RabbitMQ Limits](https://www.rabbitmq.com/docs/limits): broker message and resource limits.
- [Apache Pulsar Messaging](https://pulsar.apache.org/docs/next/concepts-messaging/): producers, consumers, batching, and message handling.
- [Apache Pulsar Client Configuration](https://pulsar.apache.org/api/client/): producer compression and client options.
- [Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/): Java benchmarking methodology with warm-up and forking.
