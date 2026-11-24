# compression.type and CPU Pressure

Kafka can compress records before transmitting over the network and writing to the log. Compression typically reduces bytes transferred among producers, brokers, and consumers while lowering disk log footprint. In return, applications spend CPU compressing and decompressing data. Choosing `compression.type` is therefore a trade-off among bandwidth, storage capacity, throughput, and processing latency.

In Spring Kafka, this setting is typically configured on the producer because the producer builds record batches and compresses them before sending. The right codec depends on payload shape, batch size, CPU limits, and actual system bottlenecks. The codec with the highest compression ratio will not necessarily yield the best throughput if producer CPU is saturated.

## 1. What Does `compression.type` Control?

`compression.type` is a Kafka producer property specifying the codec used to compress record batches. Common values supported by Kafka include:

| Value | Common characteristics | When to test |
|---|---|---|
| `none` | No compression; virtually zero CPU cost for compression/decompression, but transmits and stores more bytes | Payloads already compressed, CPU severely constrained, or workload not limited by network/disk |
| `gzip` | Typically high compression ratio, at the cost of potentially higher CPU and compression latency | Bandwidth or storage is the bottleneck and CPU headroom remains |
| `snappy` | Fast compression and decompression, typically moderate compression ratio | Need to cut wire bytes with relatively low CPU overhead |
| `lz4` | Speed-oriented, typically low latency and moderate CPU cost | High-throughput streams needing a balance between CPU and size |
| `zstd` | Can achieve high compression ratios; CPU cost depends on compression level | Want strong byte reduction and ability to tune compression level to available CPU |

`none` is usually the default if no compression is configured on the producer. Available codecs and compression levels also depend on Kafka client, broker, and codec library versions. Before rolling out a new codec, confirm the entire cluster and all consuming clients support it.

For example, a producer can form a batch of multiple JSON events for the same partition and compress that batch with LZ4. The broker receives the compressed batch and stores data in Kafka's batch format. The consumer decompresses the batch before passing records to the application.

## 2. Kafka Compresses by Batch, Not Per Individual Record

Producers group records into per-partition batches. When a batch is sent, Kafka compresses the batch's data section. This has two implications:

- Multiple records for the same partition in one batch usually compress more effectively than sending small individual records, as the codec has more data to find repeated patterns.
- A producer writing to many active partitions where each partition receives few records can create many small batches. Compression ratios are typically worse then than in a stream with the same total record count that forms larger batches.

Two settings directly influence batch size: `batch.size` and `linger.ms`:

- `batch.size` sets the target batch size the producer tries to accumulate per partition. This is a batch accumulation limit, not the maximum size of a single record.
- `linger.ms` gives the producer extra time waiting for other records to arrive so batches can fill more before sending. Raising this value can improve batching and compression, though it also increases record wait time at low traffic.

`buffer.memory` caps producer memory reserved for pending records. Raising `batch.size` or `linger.ms` can change how much data sits in buffers and how long records wait. Tune these values together under realistic load.

```text
Partition 0 records ----> Batch 0 ----> Compress ----+
Partition 1 records ----> Batch 1 ----> Compress ----+----> Broker
Partition 2 records ----> Batch 2 ----> Compress ----+

Each partition has its own batch. A full batch typically gives better compression than a batch with only a few records.
```

Do not raise `batch.size` indefinitely just to achieve a high compression ratio. Larger batches can increase memory usage, wait times, and request sizes. Balance throughput, latency, and memory.

## 3. Where Does Compression Impact CPU?

A producer → broker → consumer pipeline can consume CPU at multiple points:

1. **Producer:** the Kafka client compresses batches before sending. The more CPU-intensive the codec, the more compute capacity the producer needs to sustain the same record rate.
2. **Broker:** the broker handles requests, stores batches, and serves consumers. When the broker keeps the producer's codec as-is, it avoids re-compression. If broker/topic config mandates a storage codec different from the producer's codec, the broker may have to decompress and recompress, increasing broker CPU and latency.
3. **Consumer:** the client decompresses batches before handing records to listeners. Aggressive compression reduces network fetch bytes and disk reads, yet consumers still need CPU to decompress.

Thus, reducing network bytes does not mean reducing total resource cost. A configuration may raise producer CPU, lower broker network usage, and raise consumer CPU. Monitor every component instead of looking solely at broker CPU.

### When CPU Is the Bottleneck

If the producer is already near 100% CPU or experiencing CPU throttling, picking a heavier codec can lower send throughput. Records wait longer in buffers, requests are formed more slowly, and end-to-end latency climbs. When buffers cannot drain fast enough, the producer can hit buffer wait times or send failures upon timeout.

On the consumer, decompression CPU consumption can slow listener processing, increase consumer lag, and extend poll intervals. On the broker, CPU spent converting codecs can compete with request handling and other broker tasks.

### When Network or Disk Is the Bottleneck

If CPU has headroom while network or disk I/O is saturated, compression can raise overall throughput. Fewer bytes are transmitted and written to logs; brokers can also retain more useful data in page cache. This benefit is especially clear with text payloads or data containing many repeated field names, keys, and values.

Already-compressed payloads such as JPEG images, video, ZIP files, or application-encrypted data rarely compress further. In those cases, CPU cost rises while byte savings are minimal. For high-entropy payloads, benchmark `none` alongside codecs instead of assuming compression always helps.

## 4. Choosing a Codec by Workload

No single codec is best for all systems. The table below is a starting point for benchmarking, not an absolute ranking:

| Primary need | Codecs to benchmark | What to observe |
|---|---|---|
| Low latency and high throughput | `lz4`, `snappy` | Producer/consumer CPU, p95/p99 latency, and bytes/request |
| Strong size reduction with spare CPU | `zstd`, `gzip` | Compression ratio, CPU time per MB, and throughput |
| Producer CPU saturated | `none`, `lz4`, `snappy` | Whether CPU savings outweigh increased network bytes |
| Network or disk throughput bottlenecked | `lz4`, `zstd`, `gzip` | Network/disk bytes saved, broker CPU, and consumer CPU |
| Payloads mostly pre-compressed or encrypted | `none` first, then measure `lz4` | Actual byte reduction vs. extra CPU cost |

A generally sound starting point for high-throughput JSON event streams is testing LZ4. If network or storage remains bottlenecked and CPU has headroom, test Zstandard across different compression levels. For severely CPU-constrained workloads, measure Snappy or disable compression. Choose gzip only after benchmark results show byte savings justify its CPU cost.

### Compression Level

Some codecs support `compression.level`. Lower levels usually favor speed, while higher levels favor compression ratio and can consume more CPU. Meanings and valid ranges depend on codec and client version; do not copy a level from a gzip config onto Zstandard or LZ4 without checking documentation for the running version.

Only configure level after picking a codec and obtaining measurements showing tuning is needed. A high compression level may shave off a few extra bytes while slowing the producer substantially. The goal is optimizing total cost per record, not minimizing batch size at all costs.

## 5. Configuring Compression in Spring Boot

Spring Boot provides `spring.kafka.producer.compression-type`, which maps to the `compression.type` Kafka producer property.

```yaml
spring:
  kafka:
    producer:
      compression-type: lz4
      batch-size: 65536
      properties:
        linger.ms: 5
```

The example above selects LZ4, sets batch size to 64 KiB, and lets the producer wait up to 5 ms to accumulate more records. These are starting values for experimentation; traffic, partition count, and latency requirements may call for different settings.

If the chosen codec supports compression levels and the application needs tuning, pass the Kafka property directly:

```yaml
spring:
  kafka:
    producer:
      compression-type: zstd
      properties:
        compression.level: 3
        linger.ms: 5
```

Level `3` here is only an example configuration for an environment confirmed to support that value in its Zstandard client version. Check valid ranges and measure CPU before using in production. Without a clear reason to adjust level, starting with the codec default is usually easier to operate.

It can also be configured directly when creating `ProducerFactory`:

```java
Map<String, Object> props = new HashMap<>();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class);
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class);
props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
props.put(ProducerConfig.BATCH_SIZE_CONFIG, 64 * 1024);
props.put(ProducerConfig.LINGER_MS_CONFIG, 5);

ProducerFactory<String, OrderEvent> producerFactory =
        new DefaultKafkaProducerFactory<>(props);
KafkaTemplate<String, OrderEvent> kafkaTemplate =
        new KafkaTemplate<>(producerFactory);
```

In a Spring Kafka application, `KafkaTemplate` uses the producer created by `ProducerFactory`. The compression setting binds to that producer and typically applies to every topic it sends to. If topic groups have differing codec needs, separate `ProducerFactory`/`KafkaTemplate` beans with explicit per-group config may be required.

## 6. Distinguishing Producer Config from Broker/Topic Config

The name `compression.type` also appears in broker log configs and topic configs. Its meaning on the broker differs from the producer property:

- **Producer `compression.type`:** codec the client uses to compress batches before sending.
- **Broker/topic `compression.type=producer`:** broker retains whatever codec the producer used.
- **Broker/topic set to a specific codec:** broker may convert batches to the required codec when writing logs. Conversion can require decompression and recompression, increasing broker CPU and latency.
- **Broker/topic `compression.type=uncompressed`:** data is stored uncompressed; the broker must handle decompression if incoming batches are compressed.

Therefore, if a producer sends LZ4 yet the topic requires storing gzip, the system may perform extra compression work on the broker. Before blaming rising CPU on the producer codec, check topic and broker configs along with the actual stored batch codec.

Consumers do not choose the codec of already-written batches. The Kafka client reads the codec from the record batch and decompresses accordingly. Consumers must run a client version compatible with the codec used.

## 7. Measuring Compression Ratio and CPU Cost

Never pick a codec from a single metric. Compare bytes saved against CPU consumed and latency impact. Useful producer metrics include:

| Metric | Meaning during investigation |
|---|---|
| `compression-rate-avg` | Tracks average batch compression; correlate with request size and bytes sent to gauge codec effectiveness. |
| `batch-size-avg` | Shows whether actual batches fill up or frequently stay smaller than configured `batch.size`. |
| `records-per-request-avg` | Shows how many records the producer packs into each request. |
| `request-size-avg` | Tracks sizes of requests sent to brokers. |
| `record-queue-time-avg` | Time records wait in the producer before sending; sharp rises can signal slow producer or brokers. |
| `request-latency-avg` | Request completion time from the producer's perspective. |
| `record-send-rate` | Record send rate, to be read alongside CPU and latency. |
| `bufferpool-wait-time` | Time the producer waits to acquire buffer space; rises can show buffers held too long or producer falling behind. |

Exact metric names and display formats vary by Kafka client version and metrics stack. Check actual metrics exported in your application environment. For compression rate, read your client version's definition to understand the ratio's direction; cross-check request bytes and uncompressed record bytes to avoid inverted interpretation.

Beyond producer metrics, monitor:

- CPU usage and CPU throttling for each producer pod/instance.
- Consumer CPU and listener processing duration.
- Consumer lag, records consumed rate, and fetch size.
- Broker CPU, request handler idle percentage, network bytes in/out, and disk throughput.
- p50, p95, p99 latency from record creation until downstream processing finishes.

Low average CPU does not rule out a single core or container being saturated. For containerized apps, inspect both CPU limits and throttling duration. If a producer spans multiple partitions yet one instance handles heavy traffic, measure per-instance CPU to spot uneven load distribution.

## 8. Controlled Benchmarking

A useful benchmark keeps the workload steady so observed differences stem primarily from the codec. Follow this process:

1. Select representative payloads: repetitive-field JSON, less-repetitive JSON, Avro/Protobuf, or pre-compressed payloads if the system genuinely uses them.
2. Hold partition count, replication factor, producer count, consumer count, batch size, and linger constant while comparing codecs.
3. Run each codec (`none`, `lz4`, `snappy`, `zstd`, and `gzip` if relevant) at the same load rate long enough to pass warm-up.
4. Record throughput in records/s and MB/s, producer/broker/consumer CPU, network bytes, disk bytes, compression metrics, and p95/p99 latency.
5. Repeat at normal and peak loads; observe behavior near CPU limits too.
6. Experiment with adjusting `batch.size`, `linger.ms`, or compression level after establishing a codec baseline. Change only one group of variables at a time.

Example result table:

| Codec | Records/s | Producer CPU | Consumer CPU | Network MB/s | p99 latency | Notes |
|---|---:|---:|---:|---:|---:|---|
| `none` | measured | measured | measured | measured | measured | Baseline |
| `lz4` | measured | measured | measured | measured | measured | Speed-oriented |
| `snappy` | measured | measured | measured | measured | measured | CPU comparison |
| `zstd` | measured | measured | measured | measured | measured | Test different levels |
| `gzip` | measured | measured | measured | measured | measured | Measure CPU cost |

Do not extrapolate benchmark figures from one payload to another. A JSON stream with many repeated field names may compress well, whereas small Protobuf payloads or pre-compressed content can behave quite differently.

## 9. Reading Signs of CPU Pressure in Production

Common symptoms should be cross-checked against metrics:

| Symptom | Possibility to check | Investigation direction |
|---|---|---|
| Producer CPU rises, network bytes drop, throughput stalls | Codec spends more CPU than network savings justify | Compare LZ4/Snappy against Zstd/Gzip or `none`; inspect CPU throttling. |
| High producer CPU and rising `record-queue-time-avg` | Producer slowly building/sending batches or slow broker responses | Correlate producer CPU, request latency, batch size, and broker metrics. |
| Broker CPU rises after codec change | Broker may be converting codecs or handling higher request load | Check topic/broker `compression.type` and producer codec. |
| Consumer CPU rises, lag grows despite lower network fetch bytes | Decompression or business processing is limiting the consumer | Measure consumer CPU, listener latency, and codec compatibility. |
| Low compression ratio, yet CPU rises | Payload resists compression or batches are too small | Inspect payloads, batch size, records per request, and partition count. |
| Lower CPU when compression is off, but network/disk saturates | System may be I/O bound | Benchmark LZ4 or Zstd with batches large enough to cut bytes. |

When producer CPU is throttled, adding threads or concurrency may not improve throughput. Extra threads can worsen CPU contention. First break down CPU usage across serialization, compression, application logic, and other tasks; then tune codec, batching, or resource allocation.

## 10. Practical Configuration Principles

- Start with a codec suited to the workload and measure a baseline; LZ4 is a common test choice for high-throughput streams.
- Raise compression level only when network/disk requires further reduction and CPU headroom exists.
- Use `batch.size` and `linger.ms` to improve batches, while respecting application latency and memory bounds.
- Verify the codec is supported by every Kafka client in the system before rolling out.
- Verify whether brokers/topics preserve the producer codec or convert to another codec.
- Monitor CPU separately on producers, brokers, and consumers; do not judge solely from network bytes.
- Measure under peak load and real CPU limits rather than benchmarking only on a development machine.
- If streams have distinct payloads and requirements, consider separate producer configs instead of forcing one codec across all topics.

## 11. Codec Selection Decision Examples

Suppose a service receives JSON order events and emits tens of thousands of records per second. Producer pods are nearing CPU limits, consumer lag is steady, and broker network is unsaturated. Here, switching from `none` to high-level Zstandard can slow the producer even though requests shrink. Test LZ4 or Snappy first, then compare CPU per record and p99 latency.

In another scenario, the producer has spare CPU while broker network and disk throughput are near saturation. JSON payloads contain many repeated field names and values. Zstandard can substantially cut bytes and raise overall throughput; however, verify consumer decompression CPU and broker CPU if topics force codec conversion.

If payloads are primarily JPEG images or ZIP contents, starting with `none` makes more sense because the data is already compressed. Only keep another codec if benchmarks show byte reductions large enough to outweigh CPU cost.

Choose `compression.type` using measurements across the entire producer → broker → consumer path. A sound configuration lowers total cost and keeps latency within business limits even under load spikes; an isolated high compression ratio is not the ultimate goal.
