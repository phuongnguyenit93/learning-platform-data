# Batch Size and linger.ms

A Kafka producer does not necessarily send each record immediately when the application calls `KafkaTemplate.send()`. The producer can group multiple records into a batch and send them in the same request. Batching reduces the number of requests, uses the network more efficiently, and often improves throughput. Two configurations that directly affect batching are `batch.size` and `linger.ms`.

`batch.size` defines the target batch capacity per partition. `linger.ms` gives the producer a short additional window to wait for subsequent records to arrive, giving batches a chance to fill up more before being sent. Increasing these two values can increase throughput and compression efficiency, but can also increase latency and memory usage. They should be tuned based on record size, actual traffic, and the application's latency requirements.

## 1. How does producer batching work?

When the application calls `KafkaTemplate.send(topic, key, value)`, Spring Kafka delegates the call to the Kafka producer. The producer serializes the key/value, determines the target partition, and places the record into the buffer dedicated to that partition. Multiple records targeting the same partition can be grouped into one batch before sending to the broker.

```text
KafkaTemplate.send(record A, key -> partition 0) --+
KafkaTemplate.send(record B, key -> partition 0) --+--> Batch partition 0 --+
KafkaTemplate.send(record C, key -> partition 1) ------> Batch partition 1 --+--> Produce requests
KafkaTemplate.send(record D, key -> partition 0) --+                         |
                                                                           Kafka broker
```

Batches are formed separately for each partition. A record sent to partition 0 does not fill the batch for partition 1. Therefore, the same overall traffic spread across many partitions can produce many smaller batches compared to traffic concentrated on fewer partitions.

The producer sends a batch when the batch reaches its size threshold, when the `linger.ms` wait expires, or when another condition forces the producer to send pending data, such as `flush()` or buffer space needing to be freed. `linger.ms` is a maximum additional wait time to accumulate records, not a guarantee that every batch waits that exact number of milliseconds.

## 2. batch.size: batch capacity per partition

`batch.size` is a producer configuration in bytes that defines the target batch capacity per partition. When a batch is nearly full, new records may be placed into the next batch and the current batch is sent.

Example:

```properties
batch.size=65536
```

This value equals 64 KiB per partition batch. It does not mean the producer can only use 64 KiB total across all partitions, nor is it the maximum size limit for a single record.

If the batch is too small:

- Batches are easily sent with few records.
- Request count can rise and network/protocol overhead becomes higher.
- Per-batch compression efficiency can be low.

If the batch is too large:

- Memory needed for active partitions can increase.
- Under low traffic, batches may still be sent when `linger.ms` expires before filling up.
- Wait time or memory usage may increase without improving throughput if the producer does not have enough records.

`batch.size` does not replace `buffer.memory`. `buffer.memory` is the producer's total memory budget for pending records across the whole producer; `batch.size` is the per-partition batch capacity. When many partitions are active concurrently, the producer may need many batches coexisting in the buffer.

## 3. linger.ms: waiting longer to accumulate records

`linger.ms` determines how long the producer can wait additionally to accumulate records into a batch before sending an unfilled batch. Example:

```properties
linger.ms=5
```

The producer can wait up to roughly 5 ms for more records in the batch. If the batch fills up before then, the producer sends early without waiting the full 5 ms. If no new records arrive, the batch is sent when the wait time expires.

| `linger.ms` value | Common effect |
| --- | --- |
| 0 ms | Prioritizes sending early; batches can be small under low traffic |
| A few ms | More opportunity to group records, often a starting point for experiments |
| Higher | Can increase batch size and compression ratio, but increases record wait time under low traffic |

Do not interpret `linger.ms` as a fixed latency added to every record. Under high traffic, batches can fill very quickly and be sent before linger expires. Under low traffic, records may wait nearly the full linger duration before being sent. End-to-end latency also depends on serialization, buffer queue, network, broker acknowledgement, and the consumer.

The default value depends on the `kafka-clients` version. Kafka 4.0 changed the default `linger.ms` to 5 ms; older client versions typically default to 0 ms. Check the client version managed by Spring Boot/Spring Kafka instead of relying on defaults from another example.

## 4. How batch.size and linger.ms work together

The two configurations address two different conditions:

- `batch.size` sets the batch capacity per partition.
- `linger.ms` gives the batch extra time to receive new records.

For example, suppose the batch capacity is 64 KiB and the producer receives records averaging 1 KiB:

| Scenario | Likely outcome |
| --- | --- |
| High traffic, many records to the same partition | The batch may reach 64 KiB before linger expires and be sent early |
| Low traffic, only a few records | The batch is not full yet, but is sent when linger expires |
| Many partitions receiving sparse records | Each partition has its own batch; many batches may be small despite high total traffic |
| A single record larger than batch.size | The record can still be sent individually if request and broker limits allow; batch.size is not the max record limit |

Increasing `batch.size` without enough traffic to fill batches may yield no benefit. Increasing `linger.ms` helps the producer wait longer, but is only effective if new records keep arriving for the same partition within that window.

## 5. Configuration in Spring Boot

Spring Boot provides properties for batch size and buffer memory. Other Kafka producer properties can be passed via the `spring.kafka.producer.properties` map:

```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      buffer-memory: 67108864
      compression-type: lz4
      properties:
        linger.ms: 5
        max.block.ms: 60000
```

In the example:

- `batch-size: 65536` sets the batch size to 64 KiB.
- `linger.ms: 5` allows waiting up to roughly 5 ms to accumulate records.
- `buffer-memory: 67108864` sets the producer buffer to 64 MiB.
- `compression-type: lz4` enables LZ4 batch compression.
- `max.block.ms` limits how long calls such as `send()` can block while waiting for metadata or buffer allocation.

These are illustrative starting values, not an optimal configuration for every system. Boot property names and map binding behavior can vary by version; check the metadata of the Spring Boot version in use if a setting is not applied.

## 6. Direct configuration via ProducerFactory

If the application creates its own `ProducerFactory`, you can set Kafka producer configs using `ProducerConfig` constants:

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Bean
ProducerFactory<String, String> producerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.BATCH_SIZE_CONFIG, 64 * 1024);
    props.put(ProducerConfig.LINGER_MS_CONFIG, 5);
    props.put(ProducerConfig.BUFFER_MEMORY_CONFIG, 64L * 1024 * 1024);
    props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
    return new DefaultKafkaProducerFactory<>(props);
}

@Bean
KafkaTemplate<String, String> kafkaTemplate(
        ProducerFactory<String, String> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

If using Spring Boot auto-configuration, you usually only need to set the YAML properties rather than creating a producer factory manually. Do not declare two producer factories with different configurations and accidentally inject the wrong factory into `KafkaTemplate`.

## 7. Compression and batch size

Kafka compresses data per batch. Batches containing many similar records typically achieve better compression than many small requests. Common choices:

| Codec | General characteristics | When to consider |
| --- | --- | --- |
| `none` | No compression, avoids compression/decompression CPU cost | Small payloads or CPU is the bottleneck |
| `gzip` | Typically good compression ratio but higher CPU usage | When saving network/disk is more important than CPU |
| `snappy` | Fast compression/decompression, moderate compression ratio | Need balance between CPU and network |
| `lz4` | Typically high speed, low latency | High-throughput, latency-sensitive workloads |
| `zstd` | Can achieve good compression ratio with tunable levels | Need balance between compression ratio and CPU for the workload |

The actual choice depends on the data. JSON with many repeated field names usually compresses better than already-compressed payloads or random data. Measure compression ratio, producer/broker/consumer CPU, and network throughput on representative data.

Do not increase batch size solely to optimize compression ratio if latency already exceeds the SLA. Also do not enable a CPU-heavy codec without measuring its impact on the producer and broker.

## 8. flush() and synchronous sends can defeat batching

Producer batching works well when multiple `send()` calls can accumulate in the buffer. Calling `flush()` after every record forces the producer to push pending data immediately, reducing the opportunity to group multiple records into the same batch.

```java
// Avoid doing this in the normal send path:
for (OrderCreated event : events) {
    kafkaTemplate.send("orders", event.orderId(), event);
    kafkaTemplate.flush();
}
```

Usually, you should send consecutively and let the producer decide when to send based on batch size, linger, and buffer state:

```java
for (OrderCreated event : events) {
    kafkaTemplate.send("orders", event.orderId(), event);
}
```

`flush()` is appropriate when you need to ensure buffered records are pushed before a lifecycle boundary, such as before closing the producer or in a flow that must wait for publishing to finish. Do not use flush as a default operation after every send.

Similarly, calling `.get()` immediately after every `send()` in a sequential loop makes the calling thread wait for each record, reducing batch accumulation unless other threads are sending concurrently. In high-throughput paths, you can send asynchronously and then collect callbacks/futures to wait at a work-batch boundary when needed.

## 9. Related configurations to monitor

`batch.size` and `linger.ms` do not operate independently. Several other configurations affect buffering, requests, and reliability:

| Configuration | Role | Notes |
| --- | --- | --- |
| `buffer.memory` | Total producer memory for pending records | If buffer is exhausted, `send()` may wait up to `max.block.ms` and then time out |
| `max.block.ms` | Max time `send()` waits for metadata/buffer | Timeouts can occur before the record enters the buffer |
| `max.request.size` | Producer request size limit | Must be compatible with broker/topic message size limits |
| `compression.type` | Batch compression codec | Measure CPU and compression ratio alongside latency |
| `acks` | Broker acknowledgement level | Choose based on durability and replication requirements |
| `enable.idempotence` | Prevents duplicates from producer retries per Kafka semantics | Keep compatible settings; do not disable just for throughput without evaluation |
| `max.in.flight.requests.per.connection` | Unacknowledged requests per connection | Consider alongside idempotence and ordering requirements |

`batch.size` is the per-partition batch capacity; `max.request.size` and broker/topic message limits govern accepted request/record sizes. A record larger than batch size is not necessarily rejected; check the corresponding request and broker limits.

## 10. Measuring batching effectiveness with producer metrics

You cannot conclude batching is effective simply because you increased `batch.size` or `linger.ms`. Monitor producer metrics, depending on the client version and integrated metrics system:

| Common metric | Meaning | Used to evaluate |
| --- | --- | --- |
| `batch-size-avg` | Average batch size | Whether actual batches became larger after tuning |
| `batch-size-max` | Maximum batch size | Whether batches frequently hit the limit |
| `records-per-request-avg` | Average records per request | Whether each request carries more records |
| `compression-rate-avg` | Average compression rate | Whether codec and batch size improved compression efficiency |
| `record-queue-time-avg` | Time records spend in the producer queue | Whether linger/buffer increased wait time |
| `request-latency-avg` | Request latency to the broker | Whether network/broker became a bottleneck |
| `bufferpool-wait-time-total` | Total time producer waited for the buffer pool | Whether buffer is insufficient under high load |
| `record-send-rate` | Record send rate | How throughput changed |

Exact metric names or how they are exposed can vary across Kafka client versions. Inspect the actual JMX/Micrometer metrics of the client and cross-check with the documentation for your running version.

## 11. Workflow for tuning batch.size and linger.ms

Start with a repeatable baseline:

1. Record current throughput (records/s and bytes/s), p95/p99 publish latency, CPU, network, and producer metrics.
2. Measure average record size and size distribution, the number of partitions receiving traffic, and the number of producer instances.
3. Try increasing `batch.size` in moderate steps while keeping `linger.ms` unchanged; observe `batch-size-avg` and `records-per-request-avg`.
4. Try increasing `linger.ms` in small steps to see if batches fill more and throughput/compression improve.
5. Check p95/p99 latency, record queue time, buffer wait, and memory; stop increasing when latency or resource usage crosses thresholds.
6. Test compression codecs with representative data and compare CPU, network, and compression ratio.
7. Repeat under peak load and low load; a configuration that works well at peak may add excessive latency when traffic is sparse.

Change only one group of parameters at a time so you know which factor caused the difference. Measure both the producer and broker; if the broker/network is already saturated, increasing batch size may not improve throughput.

## 12. Example configuration choices by goal

The values below are only starting points for experimentation, not fixed formulas:

| Goal | Initial configuration direction | What to monitor |
| --- | --- | --- |
| Low latency, sparse traffic | Very small `linger.ms`; moderate batch size | p95/p99 publish latency and records/request |
| High throughput, continuous records | Increase `batch.size`, try `linger.ms` of a few ms | Average batch size, bytes/s, CPU, and queue time |
| Network is the bottleneck | Try larger batches and a suitable codec | Compression ratio, network bytes/s, and CPU |
| Many partitions with sparse traffic | Review partition count and linger; each partition has its own batch | Small batch count, request rate, and queue time |
| Buffer frequently exhausted | Review `buffer.memory`, broker ingestion rate, and producer count | Buffer wait, send timeouts, and producer memory |

Do not increase the number of partitions solely to increase batch size. Partitions affect parallelism, ordering, and how the producer splits batches; changing the partition count should be evaluated as a separate architectural decision.

## 13. Testing and common pitfalls

When testing batching, generate enough traffic to the same partition to observe real batches. Sending one record and waiting for the result cannot prove the producer groups multiple records. You can send multiple records with the same key or specify a partition in tests, then observe producer metrics.

| Symptom | Possible cause | Suggested action |
| --- | --- | --- |
| Average batch size stays small | Sparse traffic, many partitions, linger too low | Measure traffic per partition; try slightly increasing linger |
| Throughput does not rise after increasing batch | Broker/network/CPU is another bottleneck | Measure request latency, broker load, and network |
| Publish latency rises noticeably | High linger or buffer queue buildup | Reduce linger, inspect record queue time and SLA |
| Producer often times out on send | Insufficient buffer or broker cannot keep up | Check buffer wait, `buffer.memory`, `max.block.ms`, and broker health |
| Low compression ratio | Incompressible payload or small batches | Measure codec on real data and improve batch accumulation if appropriate |
| Almost no batching | Flushing after every send or awaiting futures sequentially | Remove unnecessary flushes and evaluate asynchronous sending |

## 14. Implementation checklist

- [ ] Understand that `batch.size` applies per partition batch.
- [ ] Understand that `linger.ms` is a maximum additional wait time to accumulate records, not a fixed delay on every record.
- [ ] Explicitly configure batch size and linger according to the actual `kafka-clients` version.
- [ ] Evaluate `buffer.memory`, `max.block.ms`, and `max.request.size` alongside batch size.
- [ ] Measure record size and traffic per partition.
- [ ] Do not call `flush()` after every record in the normal send path.
- [ ] Do not await each future sequentially if the goal is high-throughput batching.
- [ ] Evaluate compression codecs alongside CPU, network, and compression ratio.
- [ ] Monitor batch-size, records-per-request, queue time, buffer wait, and publish latency.
- [ ] Load test at both low and high traffic, and verify p95/p99 latency.

`batch.size` determines the batch capacity per partition, while `linger.ms` determines how much longer the producer can wait to accumulate records before sending. Combining these two settings with appropriate buffering, compression, and `KafkaTemplate` usage improves batching efficiency; actual throughput and latency measurements are the basis for selecting the final values.
