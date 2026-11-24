# Compression Type

A Kafka producer can compress records before sending them to the broker. Compression reduces bytes transferred over the network, disk storage usage, and replication traffic between brokers. In return, the producer and consumer spend CPU to compress and decompress; the broker may also spend CPU if the topic policy requires decompressing and recompressing batches.

The `compression.type` property selects the codec the producer uses to compress record batches. Kafka supports common options `none`, `gzip`, `snappy`, `lz4`, and `zstd`. With Spring Kafka, this setting is passed through the `ProducerFactory` used by `KafkaTemplate`; in Spring Boot, you can configure `spring.kafka.producer.compression-type`.

## 1. Compression operates at the batch level

A Kafka producer does not compress each record as an individual file. The producer groups records into per-partition batches, then compresses each batch before sending the Produce request. Therefore, compression effectiveness depends on the codec, payload size, data repetition, and how many records can be grouped into the same batch.

```text
Producer
  Record A ---+
  Record B ---+----> Batch for partition 0 ----+
  Record C ---+                                |
                                               v
                                      Compression codec
                                               |
                                               v
                                      Compressed batch
                                               |
                                               v
                                          Kafka broker
                                               |
                                  storage / replication
                                               |
                                               v
                                      Consumer fetch
                                               |
                                               v
                                      Decompress batch
                                               |
                                               v
                                      Listener receives record
```

Key points to remember:

- Compression is applied to record batches, typically separately per partition.
- Batches with many records and payloads with repeating patterns usually compress better than small batches or random data.
- The Kafka consumer decompresses batches automatically; the listener receives deserialized keys/values as usual.
- The application does not need to invoke codecs manually to decompress records read by the Kafka client.
- Compression does not change record ordering within a partition and does not replace serializers/deserializers.

If a producer sends a few records to very many partitions, each partition may only have small batches. High total topic traffic does not guarantee every batch is large enough to achieve a good compression ratio.

## 2. Values of compression.type

The producer property `compression.type` accepts the following codec values:

| Value | General characteristics | When to try |
|---|---|---|
| `none` | No compression; lowest CPU, but transfers and stores more bytes | Small payloads, CPU-saturated producer, or baseline comparison |
| `gzip` | Often good compression ratio, in exchange for higher compression/decompression CPU | Network/disk is the bottleneck and spare CPU is available |
| `snappy` | Prioritizes speed, moderate compression ratio | Need byte reduction at relatively low CPU cost |
| `lz4` | High compression/decompression speed, often fits high-throughput streams | Want balance between CPU and network |
| `zstd` | Often good compression ratio, with tunable compression level on supporting clients | Large payloads or need significant network/disk reduction with CPU budget |

There is no single best codec for every workload. For example, JSON with many field names and repeated strings may compress well, whereas already-compressed, encrypted, or random payloads may shrink very little. Benchmark with production-like data.

`producer` is not a producer codec value. It is an option in the topic configuration `compression.type`, meaning the broker preserves the codec used by the producer. The producer property uses `none`, `gzip`, `snappy`, `lz4`, or `zstd`.

## 3. Which components perform compression and decompression?

In the typical flow:

1. Producer serializes objects into bytes.
2. Producer groups records into per-partition batches.
3. Producer compresses batches according to `compression.type`.
4. Broker receives and stores batches; the broker may keep the original codec or convert codecs according to the topic policy.
5. Replication and consumer fetches transfer data in the stored batch format.
6. Kafka consumer decompresses batches before passing records to the application.

Because the consumer decompresses automatically, listener code does not need to know whether the producer chose gzip or lz4. However, the consumer still pays decompression CPU cost. If you increase throughput using stronger compression, monitor consumer CPU to ensure decompression does not become a new bottleneck.

Compression reduces data size in transit and at rest, but does not make the business payload smaller after the listener receives the record. If the listener parses large JSON or performs CPU-heavy object mapping, optimize that step separately.

## 4. Configuring compression.type in Spring Boot

Spring Boot provides the `spring.kafka.producer.compression-type` property. Example choosing lz4:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      compression-type: lz4
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

The `compression-type` property maps to the Kafka producer property `compression.type`. If you prefer configuring it directly via the properties map, you can write:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[compression.type]": zstd
```

Choose one place to configure it to avoid two conflicting values. If both `compression-type` and `properties["compression.type"]` are declared, verify the final property received by the producer factory.

`KafkaTemplate` does not have an independent compression setting per `send()` call. Compression is a setting of the Kafka producer created by `ProducerFactory`. If an application needs two different compression policies, it can create two separate producer factories/templates with explicitly managed configurations.

## 5. Configuring via ProducerFactory in Java

When not using Spring Boot auto-configuration or when you need direct control over producer properties, set `ProducerConfig.COMPRESSION_TYPE_CONFIG` in the factory configuration:

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
class KafkaProducerConfiguration {

    @Bean
    ProducerFactory<String, String> producerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "zstd");

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

Every record sent with this template will use the codec configured on the producer factory. In production, bootstrap servers, serializers, and compression type should come from environment configuration rather than being hard-coded.

## 6. Combining compression with batch.size and linger.ms

Kafka compresses batches, so compression effectiveness is heavily influenced by record accumulation:

- `batch.size` sets the target capacity for per-partition batches.
- `linger.ms` gives the producer extra time to accumulate records when a batch is not yet full.
- `compression.type` selects the codec applied to batches.

Example configuration:

```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      compression-type: lz4
      properties:
        "[linger.ms]": 5
```

With sufficiently high traffic, batches can fill up before linger expires. With low traffic, the producer may wait up to the linger duration to send an unfilled batch. Larger batches can improve compression ratios, but also increase required memory and can add latency while waiting to accumulate records.

Do not increase `batch.size` or `linger.ms` in isolation just to get a lower compression ratio. Monitor together:

- Average batch size and batch fullness rate.
- Time records spend in the producer buffer.
- p95/p99 producer latency.
- Producer and consumer CPU.
- Broker and network bytes in/out.

If payloads are already compressed or batches are too small, increasing linger may simply add latency without saving many bytes.

## 7. Topic compression.type and broker policy

The producer decides the initial codec, but the topic can dictate how the broker stores batches using the topic configuration `compression.type`.

Common topic options:

| Topic compression.type | Behavior |
|---|---|
| `producer` | Keeps the codec used by the producer; this is the common default |
| `uncompressed` | Broker decompresses and stores uncompressed batches |
| `gzip`, `snappy`, `lz4`, `zstd` | Broker stores batches using the specified codec; may have to decompress and recompress if the incoming codec differs |

Example keeping the producer-chosen codec:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --alter \
  --add-config compression.type=producer
```

Example forcing the topic to store batches with zstd:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --alter \
  --add-config compression.type=zstd
```

When the broker must convert codecs, the broker spends CPU to decompress and recompress. Therefore, choosing a topic policy different from the producer codec can reduce overall benefit if the broker becomes a bottleneck.

Do not confuse the producer property `compression.type` with the topic property of the same name. The producer property chooses the initial send codec; the topic property decides whether the broker keeps that codec or converts to another codec.

## 8. Checking the current topic policy

You can inspect topic configurations using the Kafka CLI:

```bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --describe
```

If a topic has no explicit override for `compression.type`, it may inherit the `producer` default according to Kafka configuration. Check both topic and producer configuration when compression ratios or CPU differ from expectations.

In environments managed by IaC or a Kafka operator, change topic configs through your organization's standard configuration source to avoid drift between the cluster and repository.

## 9. Choosing a codec by payload characteristics

Payload size and content usually affect the compression ratio:

| Payload | Common compression behavior | Experimentation suggestion |
|---|---|---|
| JSON with many fields and repeated strings | Many repeating patterns, usually compresses well | lz4, zstd, gzip |
| Very small JSON, sparse records | Batch overhead may be a large fraction | none, lz4, or moderate batch increase |
| Avro/Protobuf binary | Often already more compact than JSON, though still has repeating data | lz4, zstd, none |
| Images/video or already-compressed payloads | Unlikely to shrink further | none, or fast codec after measuring |
| Encrypted/random data | Usually hard to compress | none |

Do not treat this table as a rigid rule. Avro/Protobuf does not mean the payload is already compressed; binary data can still shrink with a suitable codec. Test on real data samples.

## 10. Compression ratio and how to read the numbers

You can define the post-compression size ratio as:

```text
compression ratio = compressed bytes / uncompressed bytes
```

For example, an initial batch of 100 KiB becomes 35 KiB after compression:

```text
compression ratio = 35 / 100 = 0.35
size reduction    = 1 - 0.35 = 65%
```

A lower ratio means fewer bytes after compression compared to the original. However, a lower ratio does not automatically mean a faster system: the codec may use more CPU, batches may wait longer, and the broker might recompress.

When reading the Kafka producer metric `compression-rate-avg`, check the metric definition for your client version. This metric typically represents the ratio of compressed batch size to uncompressed size; lower values indicate more effective compression. Do not confuse this metric with percentage of bytes saved.

## 11. Measuring performance before choosing a codec

A useful benchmark keeps the workload equivalent across runs:

1. Prepare a representative production payload set, including small/medium/large sizes and repetitive/random data.
2. Keep partition count, key distribution, producer concurrency, and record emission rate constant.
3. Run a baseline with `none`.
4. Test `lz4`, `snappy`, `zstd`, and `gzip` one by one.
5. Measure producer throughput, broker network bytes, consumer throughput, and end-to-end latency.
6. Record CPU for producer, broker, and consumer.
7. Repeat under low load and high load to observe batch fill and linger effects.
8. Select the codec meeting latency/throughput SLAs at a reasonable CPU and network cost.

Metrics to track:

| Metric | Used to evaluate |
|---|---|
| `compression-rate-avg` | Post-compression batch size ratio |
| `batch-size-avg` | Whether average batches are large enough to compress effectively |
| `record-send-rate` | Records sent per second by the producer |
| `request-latency-avg` / `request-latency-max` | Broker request response time |
| `record-queue-time-avg` | Time records wait in the producer accumulator |
| `record-retry-rate` and `record-error-rate` | Send retries and errors |
| CPU and network bytes | Actual resource cost of the codec |

Metric names and export mechanisms depend on the Kafka client, JMX, Micrometer, and monitoring system. Compare numbers on the same client version and collection setup.

## 12. Impact on broker, replication, and storage

When a topic uses `compression.type=producer`, the broker typically retains the compression codec sent by the producer. This can reduce:

- Bytes received over the network at the broker.
- Bytes stored in log segments.
- Bytes transferred via replication between brokers.
- Bytes consumers must fetch from the broker.

If a topic forces the broker to convert codecs, the broker must decompress and recompress batches, increasing CPU and potentially increasing append latency. When multiple producers use different codecs while a topic enforces a single shared codec, benchmark broker CPU load.

Compression does not change replication factor, partition count, or retention mechanics. It changes physical data size, which can slow disk usage growth, but does not replace capacity planning.

## 13. Record and request size limits

Compression can make batches smaller in transit and storage, but should not be used to circumvent size limits:

- Producers have request limits such as `max.request.size`.
- Brokers/topics have batch/message limits such as `message.max.bytes` or `max.message.bytes` depending on configuration and version.
- Consumers have fetch limits such as `fetch.max.bytes` and `max.partition.fetch.bytes`.

Check record/batch sizes for both uncompressed and compressed data and ensure consumers can fetch valid batches. A single oversized record can still cause errors regardless of how well the codec compresses.

Do not raise all limits indiscriminately. Large payloads put pressure on memory, network, and GC on both producers and consumers.

## 14. Codec compatibility between clients and cluster

Producers and consumers require Kafka clients that support the chosen codec. For clusters with mixed broker versions, verify compatibility against Kafka client/broker versions and your organization's rolling upgrade process, especially when adopting newer codecs like zstd.

Items to verify:

- The Kafka client runtime has the required codec implementation on the classpath.
- All consumers reading the topic support the codec the producer emits.
- The broker can retain or convert the codec per topic policy.
- CLI tools, connectors, MirrorMaker, or non-Java applications can read that codec.
- Broker/client upgrades do not break reading older batches stored in the log.

Do not check only that the producer sends successfully. Verify that consumers, connectors, and operational tools can read compressed data in the topic.

## 15. Compression and serializers are separate layers

The serializer determines how Java objects are converted to bytes; the compression codec determines how batch bytes are compressed.

| Layer | Examples | Responsibility |
|---|---|---|
| Serializer | StringSerializer, JsonSerializer, KafkaAvroSerializer | Converts keys/values to bytes |
| Compression | gzip, snappy, lz4, zstd | Compresses record batches |
| Deserializer | StringDeserializer, JsonDeserializer, KafkaAvroDeserializer | Converts bytes back into objects |

For example, an application can use `JsonSerializer` for values and `lz4` for batches. The consumer uses `JsonDeserializer`; the Kafka client decompresses the batch first and then the deserializer converts the JSON payload back into an object.

Do not configure `KafkaAvroSerializer` just because you want data compression. Avro is a serialization format; gzip/lz4/zstd are compression codecs. Both mechanisms can be used together.

## 16. Notes on KafkaTemplate and multiple producer factories

`KafkaTemplate` obtains its producer from a `ProducerFactory`. Therefore, compression type is decided at the factory, not per `send()` call:

```java
KafkaTemplate<String, String> fastTemplate = templateUsingLz4;
KafkaTemplate<String, String> compactTemplate = templateUsingZstd;

fastTemplate.send("orders.events", "order-1", payload);
compactTemplate.send("archive.events", "order-1", payload);
```

The example above assumes the application has two templates created from two producer factories with separate compression configurations. If multiple templates share one factory, they also share the producer configuration and codec.

Only create multiple factories when there is a clear operational need; each factory increases the number of producers, buffers, and connections to manage. If all topics share the same requirements, one producer factory with one codec is usually simpler.

## 17. Troubleshooting compression

| Symptom | What to check |
|---|---|
| Compression ratio near 1.0 | Low-repetition payloads, small batches, already-compressed data, or producer property not applied |
| Producer CPU spikes | CPU-heavy codec, high compression level, or throughput exceeding capacity |
| Broker CPU spikes after changing topic config | Broker may be decompressing and recompressing batches |
| Consumer CPU spikes | Decompression plus deserialization/parsing becoming a bottleneck |
| Network drops but latency rises | CPU-heavy codec, linger/batch wait, or broker recompression |
| Producer reports unsupported codec | Kafka client version or runtime dependency missing codec implementation |
| Consumer/connector cannot read topic | Client or connector does not support the codec stored in the log |
| Record size still exceeds limit | Uncompressed payload or batch exceeds limit; compression does not guarantee every record stays under the threshold |

When investigating, verify producer `compression.type`, topic `compression.type`, Kafka client version, actual batch size, and compression metrics. Avoid looking at only one ratio metric and concluding performance improved.

## 18. Common misconceptions

1. **Assuming Kafka compresses each record individually.** Producers compress per-partition record batches.
2. **Assuming the consumer must decompress manually.** The Kafka client decompresses before the listener receives records.
3. **Assuming zstd is always better than gzip or lz4.** Results depend on payloads, CPU, batches, and workload.
4. **Mistaking `producer` for a producer codec.** It is a topic policy to preserve the codec chosen by the producer.
5. **Configuring only the producer and ignoring topic policy.** The topic can force the broker to convert codecs or store uncompressed.
6. **Increasing batch/linger solely to improve compression ratio.** This can increase latency and memory usage.
7. **Assuming compression replaces serializers.** Serializers convert objects to bytes; compression compresses batch bytes.
8. **Assuming compression lets you bypass message limits.** Request/batch limits still apply.
9. **Measuring only network while ignoring CPU.** A codec reduces bytes but can saturate producer, broker, or consumer CPU.
10. **Not checking connectors and non-Java consumers.** Every client reading the topic must support the stored codec.

`compression.type` is a performance choice at the producer batch level. Start with representative data, measure compression ratio alongside CPU, network, throughput, and p95/p99 latency; then pick the codec that fits your SLA. With Spring Kafka, configure `spring.kafka.producer.compression-type` or the corresponding producer property, and check the topic policy so the broker does not silently recompress in a way that raises cost.
