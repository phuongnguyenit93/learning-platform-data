# Producer Batching

Producer batching is the mechanism of grouping multiple Kafka records into a batch before sending them over the network to the broker. In a Spring Kafka application, `KafkaTemplate` provides the message-sending API, while batching is handled by the underlying Kafka Producer. Therefore, batching effectiveness depends on send traffic, how records are distributed across partitions, producer configuration, and broker processing capacity.

Batching reduces the number of network requests, lowers per-record processing overhead, and generally improves throughput. When batches hold more data, compression also tends to achieve better ratios. In return, the producer may have to hold records in buffers longer while waiting for a batch to fill, increasing latency. The operational goal is to find the balance among throughput, latency, memory, and CPU resources on both producer and broker.

## How Does Producer Batching Work?

When the application calls `KafkaTemplate.send()`, Spring Kafka forwards the record to the Kafka Producer. The producer serializes the key and value, determines the target partition, and appends the record to the buffer dedicated to that partition. This buffer is managed by `RecordAccumulator`.

The Kafka Producer has a sender thread that drains ready batches and transmits them to the broker. A batch is typically sent when it reaches the `batch.size` limit or when the `linger.ms` wait time expires. Buffer pressure and other send conditions also affect the actual send timing.

```text
Application
   |
   | KafkaTemplate.send(record)
   v
Kafka Producer
   |
   | Serialize key/value and select partition
   v
RecordAccumulator
   |
   | Accumulate records into per-partition batches
   v
Sender thread
   |
   | Batch full or linger.ms elapsed
   v
Produce request --------------------> Kafka broker
   |
   | Send result
   v
Callback / CompletableFuture
```

Batching happens per topic-partition. Records belonging to two different partitions are never combined into the same batch, even if they are sent from the same application or for the same topic. A single network request can carry multiple batches for multiple partitions, but each batch still belongs to a specific partition.

For example, if the producer continuously sends records to partition 0, that partition's batch can quickly reach the target size. If records are spread across 30 partitions with low traffic per partition, each batch may contain fewer records and have to wait for `linger.ms` before being sent. Therefore, total records per second across the application is not enough to predict batch size; you must look at per-partition traffic.

## Settings That Directly Affect Batching

### `batch.size`

`batch.size` sets the target maximum size in bytes for a single partition's batch. Once a batch reaches this threshold, the producer can send it without waiting for `linger.ms` to expire.

- Smaller values create smaller batches, often increasing request count and communication overhead when traffic is high enough.
- Larger values allow accumulating more data, which can improve throughput and compression.
- Larger batches can require more memory, especially when many partitions have pending data simultaneously.

`batch.size` is neither a hard limit on the size of a single record nor a limit on the total size of a request. Large records are still subject to message and request size limits such as `max.request.size` on the producer along with broker/topic message size limits. Ensure these limits are compatible when the system sends large records.

### `linger.ms`

`linger.ms` is the duration the producer can wait for additional records to fill a batch before sending. If a batch reaches `batch.size` sooner, the producer can send it immediately.

Increasing `linger.ms` is typically beneficial when per-partition traffic is not yet high enough to fill batches quickly. The producer gets more time to accumulate records, which can reduce request count and improve compression efficiency. In return, records may wait longer before being sent, especially under low traffic.

Lowering `linger.ms` is appropriate when the application prioritizes low latency. However, setting it too low while traffic is scattered can cause the producer to frequently send small batches. Default values can vary by Kafka client version; check the actual version in use rather than relying on a default number from another version's documentation.

### `buffer.memory`

`buffer.memory` determines the amount of memory the producer allocates for buffering records waiting to be sent. This memory is shared across the producer's partitions, rather than being a fixed private allocation per batch.

When the rate at which the application enqueues records exceeds the rate at which the producer sends data out, the buffer can fill up. When that happens, `send()` calls may block waiting for memory allocation or metadata, up to `max.block.ms`, and then fail if they still cannot proceed. Increasing `buffer.memory` can absorb short bursts, but it cannot fix a situation where the producer continuously sends faster than broker or network capacity.

### `compression.type`

Compression is applied at the batch level. A batch with many records generally offers better compression opportunities than many tiny batches, especially when records have repetitive structure or content.

Common codecs include `none`, `gzip`, `snappy`, `lz4`, and `zstd`, depending on Kafka client version and deployment environment. Each codec has different CPU consumption and compression ratios. For instance, LZ4 is often considered when high compression/decompression speed is needed; gzip or zstd may fit when reducing bandwidth or storage is prioritized and the corresponding CPU cost is acceptable. Benchmark with data close to production data.

### Other Related Settings

| Property | Role | Operational Impact |
|---|---|---|
| `max.request.size` | Limits the size of a request sent by the producer | Must match record/batch sizes and broker/topic limits |
| `max.block.ms` | Limits how long send operations can wait for metadata or buffer space | Useful for detecting producer blocking due to lack of memory or metadata |
| `acks` | Acknowledgment level the producer requires from brokers | Affects data durability and latency; should not be lowered merely to increase batching |
| `enable.idempotence` | Helps prevent duplicate writes on retries via the idempotent producer mechanism | Maintains reliability when the producer retries; compatible settings must be preserved |
| `max.in.flight.requests.per.connection` | Maximum unacknowledged requests per connection | Affects request pipelining; must be compatible with idempotence and ordering requirements |
| `delivery.timeout.ms` | Limits total wait time for successful delivery, including retries | Must be factored in when setting application-level latency targets and timeouts |

Batching is a performance optimization. You should not trade away acknowledgment, ordering, or duplicate-prevention requirements just to enlarge batches. If the producer requires idempotence, keep `enable.idempotence=true` and related settings compatible with the Kafka client version in use.

## Configuring Batching in Spring Boot and Spring Kafka

Spring Boot maps common producer properties under `spring.kafka.producer`. Kafka client properties without a dedicated field can be placed under `spring.kafka.producer.properties`.

Example `application.yml`:

```yaml
spring:
  kafka:
    producer:
      acks: all
      batch-size: 32768
      buffer-memory: 67108864
      compression-type: lz4
      properties:
        "[linger.ms]": 5
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
```

In this example:

- `batch-size: 32768` sets the target batch size to 32 KiB.
- `linger.ms: 5` gives the producer up to the configured wait time to accumulate records when a batch is not yet full.
- `buffer-memory: 67108864` reserves about 64 MiB for the producer buffer.
- `compression-type: lz4` enables LZ4 batch compression.
- `acks: all` and `enable.idempotence: true` represent a reliability-focused setup; ensure broker settings and related properties satisfy the corresponding requirements.

This is an illustrative starting set of values for experimentation, not an optimal configuration for every workload. Measure in an environment with record sizes, key distributions, partition counts, and send rates close to production.

Equivalent configuration in `application.properties`:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.batch-size=32768
spring.kafka.producer.buffer-memory=67108864
spring.kafka.producer.compression-type=lz4
spring.kafka.producer.properties[linger.ms]=5
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
```

When an application creates `ProducerFactory` or `KafkaProducer` manually instead of relying on Spring Boot auto-configuration, ensure the batching properties are passed to the actual producer used by `KafkaTemplate`. Modifying a configuration file has no effect if the real producer bean overrides or ignores those properties.

## Sending Asynchronously So Batching Can Work

`KafkaTemplate.send()` performs an asynchronous send and returns a future result. The application can continue sending subsequent records while the producer accumulates batches or awaits broker acknowledgment. This is the proper usage pattern so the Kafka Producer has enough data to form batches.

The example below uses Spring Kafka 3.x's `CompletableFuture` API:

```java
CompletableFuture<SendResult<String, OrderCreated>> future =
    kafkaTemplate.send("orders", event.orderId(), event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.warn(
            "Kafka send failed: topic={}, errorType={}",
            "orders",
            exception.getClass().getSimpleName()
        );
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.debug(
        "Kafka send acknowledged: topic={}, partition={}, offset={}",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
```

In this example, the callback logs only technical metadata and the exception type, not payloads or credentials. On older Spring Kafka versions, the returned future type may differ; use the API appropriate for your project's version.

Some coding patterns can inadvertently negate batching benefits:

```java
// Avoid waiting for each record immediately after sending.
kafkaTemplate.send("orders", event).get();

// Avoid flushing after each record.
kafkaTemplate.send("orders", event);
kafkaTemplate.flush();
```

Waiting for the result immediately after every send forces the sequential sending thread to wait on the broker before continuing, reducing the opportunity to group multiple records. Calling `flush()` after every record forces the producer to push buffered data early, usually resulting in small batches. Only call `flush()` at business or lifecycle boundaries where the application genuinely needs to ensure buffered records are pushed out; do not make it a default operation after every message.

Sending asynchronously does not mean ignoring failures. The application still must handle callbacks, retry according to an appropriate policy, and monitor send errors. If too many concurrent send tasks are spawned without bounds, the application can put pressure on memory, thread pools, or brokers. Manage concurrency and backpressure at the application layer.

## Partition Count and Record Distribution Affect Batches

Because batches are accumulated per partition, the partitioner and keys directly affect batching efficiency.

- **Traffic concentrated in few partitions:** each partition receives more records, so batches can fill quickly and reach larger sizes.
- **Traffic spread across many partitions:** each partition receives fewer records in the same interval, so batches may stay small and frequently wait for `linger.ms`.
- **Skewed keys:** a hot key can funnel most records into one partition, turning that partition into a bottleneck while other partitions stay idle.
- **Increasing partition count:** can increase parallelism on brokers and consumers, yet also splits producer records into more separate batch streams. Adding partitions does not automatically make batching more efficient.

Do not change keys or partitions solely to make batches larger if doing so breaks per-entity ordering requirements, consumer scalability, or load balance. Evaluate throughput, partitioning correctness, and the processing capacity of the entire pipeline together.

## Measuring Batching Effectiveness

You should not evaluate batching solely by the number of successfully sent records. Monitor batch quality, producer wait time, end-to-end latency, and resource pressure as well.

Useful producer metrics exposed via JMX or the Kafka client metrics system include:

| Metric | Meaning During Analysis |
|---|---|
| `batch-size-avg` | Average batch size; shows how large actual batches get |
| `batch-size-max` | Largest observed batch size |
| `records-per-request-avg` | Average records per request; helps evaluate record aggregation |
| `compression-rate-avg` | Observed compression ratio of batches |
| `record-queue-time-avg` | Time records spend inside the producer before sending |
| `buffer-available-bytes` | Available producer buffer capacity |
| `bufferpool-wait-time-total` | Total time the producer spent waiting for buffer pool space |
| `request-latency-avg` | Average latency of requests to brokers |

Exact metric names and exposure may vary by Kafka client version and monitoring stack. Verify the actual metric list exported by the running client. Beyond producer metrics, track throughput, business p95/p99 latency, producer/broker CPU, network throughput, error rate, and replica/ISR status.

Common diagnostic signs:

- Low `batch-size-avg` and low `records-per-request-avg`: inspect per-partition traffic, key distribution, `linger.ms`, and whether the application flushes or blocks after every send.
- Batches consistently near `batch.size` while latency remains within target: try raising batch size to see whether throughput or compression improves.
- Rising `record-queue-time-avg`: records are waiting longer inside the producer; review `linger.ms`, broker health, network, and buffer pressure.
- Steadily dropping `buffer-available-bytes` or rising buffer wait time: the producer may be generating records faster than it can send. Raising buffer size only absorbs bursts; find the root cause of congestion if the condition persists.
- Compression improves but producer CPU rises sharply: compare other codecs or adjust batch size based on benchmarks.

## Practical Tuning Workflow

Tune one property group at a time on a representative workload and retain before/after numbers for comparison.

1. **Establish a baseline:** record throughput, p95/p99 latency, record size, partition count, key distribution, batch metrics, buffer wait, CPU, and network.
2. **Inspect the send path:** confirm the application does not call `flush()` or wait on results per record; verify the actual producer receives the intended Spring Boot configuration.
3. **Tune `linger.ms`:** try small incremental increases if batches are still small and the system has latency headroom. Stop when throughput stops increasing meaningfully or latency exceeds targets.
4. **Tune `batch.size`:** increase when batches regularly hit the threshold and evidence shows larger batches help. Monitor memory when many partitions are active.
5. **Test compression:** compare `none`, `lz4`, `snappy`, `zstd`, or environment-supported codecs with real data; measure CPU, bandwidth, and latency.
6. **Check buffers and brokers:** if the producer waits on buffers, determine whether brokers, partitions, network, or downstream limits are creating a bottleneck.
7. **Verify reliability:** re-check `acks`, idempotence, retries, timeouts, ordering, and behavior when brokers fail; do not rely solely on throughput in a happy-path benchmark.

Benchmarks should run long enough to pass warm-up, include both steady load and bursts, and use the same latency measurement from application send to acknowledgment. Changing only one property group at a time makes it clear which change produced the result. After choosing settings, re-test under production-like load and during slow or disconnected broker scenarios.

## Common Configuration and Operational Mistakes

**Setting a huge `batch.size` expecting throughput to always rise.** Large batches only help when each partition receives enough records to fill them and the producer has enough memory. Under low traffic, batches may still be sent when `linger.ms` expires; raising the target size does not generate more records.

**Increasing `linger.ms` without measuring latency.** The producer may pack more records, yet wait time grows and pushes p99 latency beyond the SLA. Set explicit latency limits and test under both low and high load.

**Increasing `buffer.memory` to cure broker congestion.** A larger buffer can delay when the application experiences backpressure, but it does not make brokers process faster. If the input rate continuously exceeds the output rate, the buffer eventually fills up anyway.

**Adding partitions solely to create more throughput.** More partitions can increase parallelism, yet they also fragment batches and raise management overhead. Account for consumer concurrency, per-key ordering, broker limits, and storage capacity.

**Calling `flush()` or waiting on `.get()` after every record.** This forces early producer sends and diminishes batching. Only synchronize at business points that genuinely require an immediate result.

**Ignoring send errors because the API is asynchronous.** `send()` returning before broker acknowledgment does not mean the record was persisted successfully. Handle futures/callbacks, timeouts, and retries according to application policy.

**Lowering acknowledgment guarantees to make benchmarks look better.** Settings like `acks=0` can alter latency and throughput, but they change delivery guarantees. Benchmarks must keep the same reliability requirements needed in production.

## Operational Principles

Producer batching works well when records are sent continuously, distributed reasonably across partitions, and the producer has enough time to accumulate data before sending. Start with moderate settings, send asynchronously, avoid per-record flushes, and then use metrics to tune `batch.size`, `linger.ms`, `buffer.memory`, and compression.

When deploying to production, always evaluate batching alongside end-to-end latency, backpressure, partition distribution, producer reliability, and broker capacity. A good configuration is one that meets throughput goals within defined latency and resource limits while preserving all delivery guarantees required by the system.
