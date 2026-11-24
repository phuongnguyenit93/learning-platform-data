# Buffer Memory and Batch Memory

A Kafka producer sends records asynchronously. When an application calls `KafkaTemplate.send()`, the record is serialized, its target partition is determined, and it is placed into the producer's buffer. Records for the same partition are grouped into batches before the sender thread sends requests to the broker. Two critical settings governing memory and batching are **`buffer.memory`** and **`batch.size`**.

`buffer.memory` limits the total memory the producer uses to hold records waiting to be sent. `batch.size` determines the target size of a batch per partition. These two values are directly related: many partitions actively receiving data can require many concurrent batches, exhausting the buffer pool even if individual batches are not full.

## 1. Data flow inside the Kafka producer

When the application sends a record, the Kafka producer does not immediately send each record as an independent request. The producer accumulates records by topic-partition in `RecordAccumulator`, and then the sender thread picks up ready batches to transmit.

```text
Application
    |
    | KafkaTemplate.send(record)
    v
Serialize key/value
    |
    v
Select partition
    |
    v
RecordAccumulator
    |
    +---- Topic A / Partition 0: [batch A0]
    +---- Topic A / Partition 1: [batch A1]
    +---- Topic B / Partition 0: [batch B0]
    |
    v
Sender thread picks up ready batches
    |
    v
Group batches by broker and send ProduceRequest
    |
    v
Kafka broker acknowledges
```

The producer needs memory to hold records before sending, hold batches being built, and manage requests awaiting responses. Batching reduces request count, improves network utilization, and often improves compression efficiency.

## 2. What is buffer.memory?

`buffer.memory` is the total memory the producer can use to buffer records waiting to be sent to the broker. The Kafka producer uses a buffer pool to allocate memory for batches in `RecordAccumulator`.

Configuration example:

```properties
buffer.memory=67108864
```

This value equals 64 MiB. Kafka producers commonly default to 32 MiB (`33554432` bytes); check the default for the Kafka client version your application runs.

When the producer sends records faster than the broker can receive and acknowledge them, batches accumulate in the buffer pool. If there is not enough memory left to allocate a new batch, the thread calling `send()` may have to wait. If waiting exceeds `max.block.ms`, the send operation can fail with a timeout before returning a future.

`buffer.memory` is the budget for the record accumulator, not the total JVM heap limit. The producer also uses memory for objects, metadata, compression, in-flight requests, callbacks, and internal structures. Therefore, never set `buffer.memory` equal to the entire heap allocated to the application.

## 3. What is batch.size?

`batch.size` is the target size of a batch per partition, in bytes. The producer tries to group multiple records for the same partition into a batch until the batch is full or the `linger.ms` send trigger arrives.

Example:

```properties
batch.size=32768
```

A value of 32 KiB allows the producer to group records for the same partition into batches targeting 32 KiB. Kafka producers commonly default to 16 KiB (`16384` bytes), though you should verify against your Kafka client version.

`batch.size` is not the maximum size of an entire request to the broker. One request can contain multiple batches across multiple partitions. A single record larger than `batch.size` may require its own larger batch; it is not merged with other records through normal batching. Record/request sizes remain subject to limits like `max.request.size` and broker-side message/batch limits.

## 4. Distinguishing buffer.memory and batch.size

| Property | `buffer.memory` | `batch.size` |
| --- | --- | --- |
| Scope | Total producer buffer budget | Target size for each partition's batch |
| Unit | Bytes | Bytes |
| Impact | Determines how much pending data the producer can hold | Determines how many records are grouped per batch |
| When too small | Buffer pool exhausts quickly, `send()` must wait | Batches fill quickly, more smaller requests |
| When too large | Increases memory footprint and only absorbs bursts longer | Can improve batching efficiency, but uses memory inefficiently under low traffic |

You can think of `buffer.memory` as the shared budget, while `batch.size` is the target size of each slice allocated to a partition receiving data.

## 5. BufferPool and RecordAccumulator

Inside the Kafka producer, `RecordAccumulator` manages pending batches by `TopicPartition`. When a new record arrives, the producer looks for that partition's current batch to append the record. If there is no space left, the producer must allocate a new batch from `BufferPool`.

`BufferPool` manages reusable buffers. Once the sender thread sends a batch and the batch memory is freed, that memory can return to the pool for reuse by other batches. This reduces new object/buffer allocations in the send path.

An active partition typically needs at least one open batch. If many partitions receive records concurrently, the producer may need many batches simultaneously. When an old batch is full but not yet sent/freed, the partition may need another buffer for the next batch.

Therefore, you cannot judge whether `buffer.memory` is sufficient just by looking at average record count or `batch.size`. You must consider concurrently active partitions, record sizes, send rate, broker wait time, and pending batch count.

## 6. Relationship between partition count and memory

Batches are created per partition. A producer sending to many partitions may have to maintain many separate batches, even if each partition has only a few records.

Illustrative example with `batch.size=32 KiB`:

| Active partitions receiving traffic | Target memory if each partition holds one 32 KiB batch |
| ---: | ---: |
| 10 | Around 320 KiB |
| 100 | Around 3,200 KiB (approx. 3.125 MiB) |
| 500 | Around 16,000 KiB (approx. 15.625 MiB) |
| 1,000 | Around 32,000 KiB (approx. 31.25 MiB) |

This is only an estimate to illustrate per-partition fan-out, not a fixed allocation formula. Batches are allocated on demand; one partition can have multiple queued batches, large records can need larger buffers, and memory is also affected by compression, in-flight requests, and other overhead.

A producer serving hundreds of topic-partitions can exhaust its buffer even if overall throughput is modest, because scattered records keep many small batches alive at once. In that case, increasing `batch.size` can raise the memory reserved per active partition without necessarily improving performance if per-partition traffic is low.

## 7. How does linger.ms affect batching?

`linger.ms` is how long the producer can wait for additional records so a batch fills further before sending. Batches can also be sent early once full or when the producer needs to free resources via internal mechanisms.

Example:

```properties
batch.size=32768
linger.ms=5
```

The producer can wait up to roughly 5 ms to accumulate more records for the same partition. If the batch fills early, it can be sent before linger expires.

| Configuration | Common effect |
| --- | --- |
| `linger.ms=0` | Reduces batching wait time, but can create many small batches under low traffic |
| Small `linger.ms` | Extra chance to accumulate records, often increasing batch fullness with low latency cost |
| Large `linger.ms` | Can raise throughput and compression efficiency, but increases wait time before sending |

The default for `linger.ms` has changed across Kafka client versions; Kafka client 4.x has a different default from older versions. Do not copy a default value from another version's docs without checking your actual dependency.

## 8. Compression and batch memory

Kafka compresses per batch. When a batch holds many similar records, the compression algorithm usually achieves better results than compressing each record individually.

Example:

```properties
batch.size=65536
linger.ms=5
compression.type=zstd
```

`compression.type` can be `none`, `gzip`, `snappy`, `lz4`, or `zstd` depending on client/broker support. Compression reduces network bytes and storage space, at the cost of CPU and extra memory overhead to process the data.

`batch.size` governs how data is accumulated; do not assume a batch always occupies its exact compressed size. Compression happens on the batch, and the compressed size can be significantly smaller than the original data.

When increasing `batch.size` to improve compression ratio, measure CPU, latency, batch fullness, and network throughput. If CPU is already saturated, increasing compression level or choosing a heavier algorithm can reduce throughput.

## 9. What happens when buffer.memory is exhausted?

When the application calls `send()`, the producer may need to wait for metadata or for the buffer pool to allocate memory for a batch. `max.block.ms` limits synchronous blocking for operations like fetching metadata and allocating buffers.

Flow when the buffer pool is exhausted:

```text
Application calls send()
        |
        v
Producer needs buffer for batch
        |
        v
BufferPool does not have enough memory
        |
        v
Thread calling send() waits for buffer release
        |
        +---- Buffer available before max.block.ms ---> Continue sending
        |
        +---- max.block.ms elapsed ---------------> TimeoutException
```

Key point: `KafkaTemplate.send()` normally returns a future for the asynchronous send result, yet the `send()` call itself can still block before returning if it needs to wait for metadata or buffer space. `max.block.ms` is not the time spent waiting for broker acknowledgement.

If the buffer runs out frequently, increasing `buffer.memory` can absorb bursts for longer. However, if the producer continuously generates data faster than the broker can accept, a larger buffer only delays when backpressure appears.

## 10. Distinguishing max.block.ms, request.timeout.ms, and delivery.timeout.ms

These three timeouts govern different stages:

| Property | Controls | On expiration |
| --- | --- | --- |
| `max.block.ms` | How long `send()` can block waiting for metadata or buffer allocation | The `send()` call may throw a timeout before returning a future |
| `request.timeout.ms` | How long to wait for a response to a broker request | The request may be retried if the error is retryable |
| `delivery.timeout.ms` | Maximum total time for the producer to report a send result after the record is accepted into the send pipeline | The future/callback finishes with an error if not yet sent successfully |

`delivery.timeout.ms` encompasses time waiting before send, time waiting for broker response, and retries. This value must be greater than or equal to `request.timeout.ms + linger.ms` per Kafka producer constraints.

Do not raise `max.block.ms` to fix slow broker responses; investigate buffer pressure or metadata availability. Do not raise `delivery.timeout.ms` to cure buffer pool exhaustion if `send()` calls are timing out before a future is created.

## 11. max.request.size and large records

`batch.size` is not the only limit on data size. `max.request.size` caps the request size the producer can send and also constrains the largest record batch. Brokers have corresponding limits like `message.max.bytes`; replica fetches must also be able to pull the batch.

When sending large payloads:

- Check the size after serialization, not just the Java object size.
- Check `max.request.size` on the producer.
- Check `message.max.bytes` or the corresponding topic/broker limit.
- Check `replica.fetch.max.bytes` and related fetch configurations.
- Consider compression, splitting events, or storing large objects in object storage and sending references.

Increasing `buffer.memory` does not allow sending records that exceed request/broker limits. If a record is too large, the producer or broker can still reject it even when the buffer has plenty of memory.

## 12. Configuring buffer.memory and batch.size in Spring Boot

Spring Boot provides dedicated properties for `batch-size` and `buffer-memory` under `spring.kafka.producer`. Other Kafka properties can be placed in `properties`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      batch-size: 32768
      buffer-memory: 67108864
      compression-type: zstd
      properties:
        "[linger.ms]": 5
        "[max.block.ms]": 10000
        "[request.timeout.ms]": 30000
        "[delivery.timeout.ms]": 120000
        "[max.request.size]": 1048576
```

In the example:

- Each batch has a target size of 32 KiB.
- The producer buffer pool has a 64 MiB budget.
- The producer waits up to 5 ms to accumulate more records.
- Compression uses Zstandard if supported by the Kafka client and broker.
- Send calls have a 10-second limit waiting for metadata/buffer.
- Request timeout is 30 seconds and delivery timeout is 120 seconds.
- Maximum request size is configured at 1 MiB.

These values are illustrative starting points, not a universal optimal configuration. `delivery.timeout.ms` must satisfy the relationship with `request.timeout.ms + linger.ms`; also verify retries, broker limits, and system latency requirements.

## 13. Configuring via ProducerFactory in Java

When creating a producer factory manually, you can set the corresponding configs using `ProducerConfig`:

```java
@Bean
public ProducerFactory<String, String> producerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

    props.put(ProducerConfig.BATCH_SIZE_CONFIG, 32 * 1024);
    props.put(ProducerConfig.BUFFER_MEMORY_CONFIG, 64L * 1024 * 1024);
    props.put(ProducerConfig.LINGER_MS_CONFIG, 5);
    props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "zstd");
    props.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, 10_000);
    props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
    props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
    props.put(ProducerConfig.MAX_REQUEST_SIZE_CONFIG, 1024 * 1024);

    return new DefaultKafkaProducerFactory<>(props);
}
```

This example illustrates producer configurations; you still need to add security, idempotence, `acks`, retries, and environment-specific properties. If using Spring Boot auto-configuration, prefer configuring via `application.yml` rather than creating a custom factory solely to change two memory settings.

## 14. Estimating initial buffer.memory

There is no single formula for all workloads, but you can use an estimation approach to pick a trial value:

1. Determine the maximum number of partitions one producer can send to concurrently.
2. Estimate the number of open/queued batches per partition during peak hours.
3. Multiply the concurrent batch count by the target batch size.
4. Add headroom for bursts, large records, and fluctuations in broker speed.
5. Ensure remaining memory is sufficient for the JVM, serializers, compression, and other components.

For example, a producer regularly serving 200 active partitions, assuming an average of one open 32 KiB batch per partition:

\[
200 \times 32\,\text{KiB} = 6.25\,\text{MiB}
\]

This is only the capacity for one target batch per partition. If some partitions have multiple queued batches, traffic bursts, or large records, actual demand is higher. Do not treat this estimate as a final configuration value without measuring the buffer pool under load.

## 15. How to choose batch.size

Choose `batch.size` according to record size and per-partition record rate:

| Workload characteristic | Experimentation direction |
| --- | --- |
| Small records, high traffic on few partitions | Increase batch size moderately to group more records |
| Small records, traffic spread across many partitions | Measure memory footprint; overly large batches may leave many buffer regions underfilled |
| Large records | Set batch size suitable for record size; check `max.request.size` and broker limits |
| Low-latency priority | Smaller batches and low linger, then measure request rate |
| Throughput priority | Try larger batches, suitable linger, and compression |

A large batch size does not automatically increase throughput. If partition traffic is low, the producer may send unfilled batches when linger expires. If the broker/network is the bottleneck, larger batches can reduce request overhead but cannot increase processing capacity indefinitely.

## 16. Signs of buffer pressure and metrics

The Kafka producer exposes metrics to observe the buffer pool and batching. Useful metrics include:

| Metric | Meaning | Signs to watch for |
| --- | --- | --- |
| `buffer-available-bytes` | Available buffer pool memory | Persistently low or frequently near 0 |
| `buffer-total-bytes` | Total buffer pool capacity | Compare against `buffer.memory` |
| `waiting-threads` | Threads waiting for buffer allocation | Sustained values above 0 indicate producer backpressure |
| `bufferpool-wait-time` | Total time waiting for buffer pool | Rises quickly when the producer is congested |
| `bufferpool-wait-ratio` | Ratio of time spent waiting for buffer | Increasing indicates the app spends time waiting on memory |
| `batch-size-avg` | Average batch size | Too low may indicate ineffective batching |
| `records-per-request-avg` | Average records per request | Low values can increase request overhead |
| `compression-rate-avg` | Average compression rate | Evaluates compression effectiveness |
| `record-queue-time-avg` | Time records spend in the producer queue | Rising can reflect linger or a slow broker |
| `request-latency-avg` | Average request latency | Rising can point to a broker/network bottleneck |

Metric names and export mechanisms depend on the Kafka client/Micrometer integration. Check the actual metrics exposed in your running version.

## 17. Tuning by symptom

| Symptom | Possible cause | Investigation/experimentation direction |
| --- | --- | --- |
| `buffer-available-bytes` near 0, `waiting-threads` rising | Producer generates data faster than send rate or broker is slow | Check broker/network, increase buffer within limits, throttle upstream |
| Low `batch-size-avg`, high request rate | Batches are not accumulating enough records | Try increasing `linger.ms`, check per-partition traffic and batch size |
| Small batches despite high total topic traffic | Traffic spread across too many partitions | Measure per-partition throughput; inspect key distribution and partition count |
| High queue time, high broker latency | Broker or network is the bottleneck | Check broker load, request latency, throttling, and replication |
| Heap grows while buffer.memory is stable | Payload objects, serializers, callbacks, or in-flight memory | Profile heap and allocations; don't just raise buffer pool |
| Large records rejected | Exceeds `max.request.size` or broker limit | Check serialized size and limits on both sides |
| High CPU when compression is enabled | CPU-heavy compression algorithm/level | Benchmark `lz4`, `snappy`, `zstd`, `gzip` on your workload |

Do not change `buffer.memory`, `batch.size`, `linger.ms`, and compression simultaneously and conclude one config is better. Change one variable group at a time while keeping workload, partition count, and record size comparable to isolate the cause.

## 18. Load testing and benchmarking

To tune buffer and batch memory, you need a realistic workload:

- Representative payload sizes, including small, medium, and large records.
- Partition count and key distribution matching production.
- Producer rates reflecting peak hours and bursts.
- Broker/network configured similarly to the target environment.
- Compression and acknowledgements matching the planned deployment configuration.
- Consumer/broker load sufficient to create scenarios where the sender cannot transmit instantaneously.

Measure at least:

1. Producer records/sec and bytes/sec.
2. p50/p95/p99 send latency and record queue time.
3. Average batch size and records/request.
4. Buffer available bytes, wait ratio, and waiting threads.
5. CPU, heap, GC, and network throughput.
6. Error/timeout rate when load exceeds broker capacity.

Run a baseline first, change one configuration, repeat multiple times, and compare results. Increasing `buffer.memory` can help absorb bursts, but should not be treated as a throughput improvement if latency and queue time keep climbing.

## 19. Common pitfalls

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| `send()` blocks for a long time | Buffer pool exhausted or metadata unavailable | Observe `waiting-threads`, `buffer-available-bytes`, metadata/network |
| Timeout before receiving future | Waiting for buffer/metadata exceeded `max.block.ms` | Distinguish from broker acknowledgement timeout; find cause of buffer pressure |
| Send future fails after returning | Delivery expired, request error, or retries exhausted | Check `delivery.timeout.ms`, `request.timeout.ms`, retries, and broker logs |
| Raising buffer.memory does not clear bottleneck | Long-term producer throughput exceeds broker capacity | Throttle producer or scale broker/partition capacity appropriately |
| Raising batch.size spikes heap usage | Many partitions holding large batches simultaneously | Measure active partitions and memory pool; consider lowering batch size |
| Low batch fullness | Scattered traffic or linger too low | Try suitable linger and inspect per-partition throughput |
| High request rate | Too many small batches | Tune batch/linger and evaluate key distribution |
| Compression does not improve throughput | Compression CPU became the bottleneck or payload is hard to compress | Benchmark codecs and CPU cost |
| Large records rejected by broker | Exceeds request/message limit | Align producer, broker, and replica fetch limits |

## 20. Production configuration checklist

- [ ] `buffer.memory` fits the heap budget and burst traffic.
- [ ] `batch.size` is chosen based on record size and active partition count.
- [ ] `linger.ms` balances latency with batching.
- [ ] Compression has been benchmarked for CPU, network, and batch size.
- [ ] `max.block.ms` aligns with allowable metadata/buffer wait time.
- [ ] `request.timeout.ms` and `delivery.timeout.ms` are configured consistently.
- [ ] `max.request.size` is compatible with broker/topic limits.
- [ ] Metrics exist for buffer pool, batch fullness, queue time, and request latency.
- [ ] Load tests cover representative partition/key distributions.
- [ ] Upstream backpressure limits exist when the broker cannot keep up.
- [ ] `buffer.memory` is not treated as the total JVM heap limit.

## 21. Conclusion

`buffer.memory` and `batch.size` address two different scopes in a Kafka producer. `buffer.memory` is the overall budget for pending records; `batch.size` is the target batch size per partition. Active partition count, record rate, `linger.ms`, compression, and broker speed together determine actual memory usage.

When the buffer pool runs dry, `send()` calls may wait up to `max.block.ms`; this is distinct from waiting on broker responses or exceeding `delivery.timeout.ms`. Measure `buffer-available-bytes`, `waiting-threads`, batch size, queue time, and request latency before tuning. Increasing the buffer only absorbs bursts for longer; to achieve sustainable throughput gains, balance batching, linger, compression, partitioning, and broker capacity.

## References

- [Apache Kafka — Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka — KafkaProducer API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- [Apache Kafka — Producer Metrics](https://kafka.apache.org/documentation/#producer_monitoring)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
