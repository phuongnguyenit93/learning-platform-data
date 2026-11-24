# Producer-Side Batching

A Kafka producer does not need to send every record as a separate request. The producer can group multiple records into a batch and send the batch to the broker, reducing the number of requests, making better use of the network, and usually increasing throughput. Batching also introduces a trade-off: the producer may have to wait briefly to accumulate enough data, increasing send latency. In Spring Kafka, this batching mechanism lives in the Kafka client used by `KafkaTemplate`; therefore, you need to understand the producer client properties to configure it properly.

## 1. How does batching work?

When the application calls `KafkaTemplate.send()` or `KafkaProducer.send()`, the record is serialized and placed into the producer's buffer. The Kafka client organizes batches by target partition. A batch only holds records destined for the same partition; records for another partition are accumulated in a different batch, even though they may be sent within the same network request.

High-level processing flow:

```text
Application calls send(record)
          |
          v
Serialize key/value and choose partition
          |
          v
RecordAccumulator stores record in partition's batch
          |
          +---- batch reaches size -------------------+
          |                                           |
          +---- linger.ms expires --------------------+----> Sender sends request
          |                                           |       to broker
          +---- buffer needs to be freed -------------+          |
                                                              v
                                                     Broker processes batch
                                                              |
                                                              v
                                                   Callback/Future completes
```

`RecordAccumulator` is the logical buffer where the client accumulates records. A background sending thread (Sender) takes ready batches and sends them to the broker. The producer can send multiple batches for multiple partitions in one request, while accumulating records into batches still happens per partition.

A batch is usually sent when it reaches the size limit, when the `linger.ms` wait time expires, when the producer needs to free buffer space, or when the application calls flush/close. Batches are not always full: under low traffic, `linger.ms` expiring can cause a small batch to be sent. The configuration goal is to achieve a sufficiently good batch size without increasing latency excessively.

## 2. Properties that govern batching

| Property | Role | Effect when increased |
|---|---|---|
| `batch.size` | Maximum target size of one batch in bytes per partition | More room to accumulate records; can increase throughput and compression ratio, but uses more buffer |
| `linger.ms` | Time the producer waits for more records before sending an unfilled batch | Opportunity to group more records; increases waiting latency under low load |
| `buffer.memory` | Total memory allocated by the producer for records waiting to be sent | Tolerates more queued data, but increases memory usage |
| `compression.type` | Batch compression algorithm before sending | Reduces transmitted bytes and storage footprint at the cost of CPU |
| `max.request.size` | Maximum size of a request sent to the broker | Caps request size; must coordinate with record and batch sizes |

`batch.size` is measured in bytes and applies to each partition's batch, not the total memory limit of the entire producer. A large record can cause a batch to contain only one or a few records; Kafka does not split a large record into smaller records to fit a batch. Record size is also constrained by other limits such as `max.request.size` on the producer and corresponding message/batch limits on the broker/topic side.

`linger.ms` sets the maximum wait time for additional records to join a batch. Under high load, a batch can fill up before the wait time expires; under low load, the producer typically sends the batch when `linger.ms` expires. Thus, increasing `linger.ms` does not guarantee full batches, though it can improve data grouping when records arrive sporadically.

`buffer.memory` is the memory budget for records that have been accepted but not yet finished sending. When the buffer nears exhaustion, `send()` calls may have to wait up to `max.block.ms` for space to free up or to fetch metadata. If buffer space cannot be freed within this time, the producer may throw `TimeoutException`. Increasing the buffer only delays exhaustion if the record production rate stays consistently higher than the send rate; you must address the underlying bottleneck.

Default values for these properties can vary by Kafka client version. Common values across many versions are a `batch.size` of 16 KiB and `linger.ms` of 0 ms, though some newer versions have adjusted the default of `linger.ms`. Check the effective configuration and documentation for the exact library version you are running before relying on defaults.

## 3. Why are batches grouped per partition?

Kafka stores logs independently for each partition. Every batch is sent to a specific partition and the broker appends that batch to the partition's log. If the producer sends keyed records, the partitioner selects the partition by key (with the default partitioner, exact calculation depends on configuration and version). Records with the same key usually go to the same partition, so they can be grouped into the same batch.

The partition count directly affects batching efficiency. If the application sends the same volume of records but spreads them evenly across many partitions, each partition receives fewer records over a given period. As a result, many small batches may be sent. This does not mean you should reduce partitions arbitrarily: partitions also determine parallelism, ordering, and consumer load. Balance partition count with throughput, consumer count, and business requirements.

For keyless records, the partitioner may use sticky partitioning to temporarily concentrate records into one partition, helping batch more effectively before switching to another partition. The exact distribution depends on the Kafka client and partitioner in use. If the application writes a custom partitioner, consider both load distribution and batching efficiency.

## 4. Compression and batching

Kafka compresses data at the batch level. When a batch contains many similar records, compression algorithms typically exploit repetition better than requests containing very few records. You can configure `compression.type` as `none`, `gzip`, `snappy`, `lz4`, or `zstd`, depending on what the client version, broker, and environment support.

Example selecting `lz4`:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[compression.type]": lz4
```

Compression can reduce network bandwidth and disk usage, at the expense of extra CPU cost. `gzip` generally achieves strong compression ratios at higher CPU cost; `lz4` and `snappy` generally prioritize speed; `zstd` can balance compression ratio and speed depending on configuration level. Benchmark on your application's actual data instead of choosing based solely on algorithm name.

Brokers typically store batches in the compressed format sent by the producer, so compression can reduce both network traffic and log storage. Actual effectiveness still depends on the data, batch fullness, partition count, and whether the broker/consumer has to convert message formats.

## 5. Configuring batching in Spring Boot

Spring Boot maps several common producer properties to Kafka client settings. The following example sets a 32 KiB target batch, waits up to 10 ms to accumulate more records, allocates a 64 MiB buffer, and uses LZ4:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      batch-size: 32768
      buffer-memory: 67108864
      properties:
        "[linger.ms]": 10
        "[compression.type]": lz4
```

In this configuration:

- `batch-size` maps to `batch.size`, in bytes.
- `linger.ms` gives the producer up to 10 ms more to accumulate records.
- `buffer-memory` maps to `buffer.memory`, in bytes.
- `compression.type` specifies the batch compression algorithm.
- `acks: all` requires broker acknowledgement per the topic's ISR policy; this is a durability setting, not a batching property.

The values above are starting points for experimentation. For applications requiring very low latency, a smaller `linger.ms` may fit better. For high-throughput event streams, you can test larger batches and longer linger times if the latency budget allows. Also check `delivery.timeout.ms`, `request.timeout.ms`, `max.block.ms`, and broker-side message limits when tuning these values.

## 6. Configuring via Java and KafkaTemplate

If creating `ProducerFactory` manually, you can pass Kafka client properties directly:

```java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> producerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.BATCH_SIZE_CONFIG, 32 * 1024);
        props.put(ProducerConfig.LINGER_MS_CONFIG, 10);
        props.put(ProducerConfig.BUFFER_MEMORY_CONFIG, 64L * 1024 * 1024);
        props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        return new DefaultKafkaProducerFactory<>(
                props,
                new StringSerializer(),
                new JsonSerializer<>());
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> kafkaTemplate(
            ProducerFactory<String, OrderCreated> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

The example omits imports, and serializer configuration depends on the Spring Kafka version. When using Spring Boot auto-configuration, you do not need to recreate `ProducerFactory` just to change `batch.size` or `linger.ms`; you can set those properties in `application.yml` as shown in the previous section.

`enable.idempotence=true` helps the producer prevent duplicate records from retries within the Kafka producer's guarantee scope. It does not replace business-level idempotency when the application resends the same event with a new send call, nor does it determine how batches are formed.

## 7. Sending asynchronously so the producer can batch

`KafkaTemplate.send()` returns a future for the application to track the send outcome. In Spring Kafka 3.x, the return type is `CompletableFuture<SendResult<K, V>>`:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .whenComplete((result, error) -> {
                    if (error != null) {
                        // Record send error and handle according to application policy.
                        log.error("Cannot publish order event", error);
                        return;
                    }

                    RecordMetadata metadata = result.getRecordMetadata();
                    log.debug("Published to partition {}, offset {}",
                            metadata.partition(), metadata.offset());
                });
    }
}
```

The producer can continue accepting records while the Sender thread sends batches in the background. Avoid calling `get()` immediately after each `send()` in a high-throughput loop unless synchronous confirmation is required; waiting for each record slows down feeding data into the accumulator and reduces batching opportunities. You can keep the futures and handle results asynchronously or wait as a group at an appropriate boundary.

Do not call `flush()` after every record. `flush()` forces buffered records to be sent immediately, making batches small and negating the benefit of `linger.ms`. Only flush at genuine business boundaries where buffered data must be pushed out, such as before ending a processing phase or during managed application shutdown. `KafkaTemplate` does not normally enable auto-flush by default; if `autoFlush` is enabled, understand that every send may trigger a flush and reduce batching.

In older Spring Kafka versions, the future API may be `ListenableFuture` instead of `CompletableFuture`. Use the API matching your project's library version.

## 8. Balancing throughput and latency

Batching is a balancing exercise. Larger batches and longer `linger.ms` can reduce request counts and improve compression efficiency, but increase how long records wait before being sent. Choose based on concrete goals:

| Goal | Tuning direction |
|---|---|
| Low latency | Reduce `linger.ms`, keep a reasonable batch size, and avoid unnecessary flushes |
| High throughput | Test increasing `batch.size`, `linger.ms`, and compression; measure CPU, network, and latency |
| Lower bandwidth | Enable compression and ensure batches are large enough for the algorithm to be effective |
| Bursty/uneven traffic | Try moderate `linger.ms`, inspect queue time and batch size at both off-peak and peak hours |
| Many partitions | Assess record volume per partition; small batches may be due to record scattering |

For example, if the application emits only one record per second to a partition and `linger.ms` is 10 ms, the producer cannot wait for enough records within 10 ms to build a large batch. Increasing `batch.size` from 16 KiB to 64 KiB does not conjure more data; batches may still hold only one record. In this case, increasing `linger.ms` only helps if additional latency is acceptable to wait for subsequent records.

Conversely, if thousands of records per second are distributed across a small number of partitions, batches may fill up very quickly. In that case, increasing `linger.ms` may yield little throughput improvement while still adding latency during quieter traffic periods. Test across multiple load levels rather than benchmarking only at peak load.

## 9. Related timeouts and limits

The following properties are often confused with batching:

| Property | Meaning |
|---|---|
| `max.block.ms` | Maximum time `send()` can wait when metadata or free buffer space is needed |
| `request.timeout.ms` | Time to wait for a response to one request sent to the broker |
| `delivery.timeout.ms` | Maximum total time for a record to be sent successfully, including retries |
| `max.request.size` | Size limit of a producer request |
| `acks` | Acknowledgement level the producer requires from the broker |
| `retries` | Number of times the producer retries on retriable errors; must coordinate with idempotence and delivery timeout |

`linger.ms` is not a delivery timeout. Once a batch is sent, `request.timeout.ms` and `delivery.timeout.ms` govern response waiting and retries. A valid configuration requires `delivery.timeout.ms` to be greater than or equal to the sum of `request.timeout.ms` and `linger.ms` per Kafka client constraints. When adjusting timeouts, verify consistency across these values.

`max.request.size` is not the size of a single individual batch. One request can carry batches from multiple partitions; request limits and broker/topic message/batch limits must accommodate the largest record the application sends. When encountering record-too-large errors, increasing `batch.size` will not necessarily resolve them.

## 10. Measuring batching effectiveness

Do not evaluate batching merely by raising `batch.size` or `linger.ms`. Measure producer metrics under the same workload and network conditions:

| Metric | How to interpret |
|---|---|
| `batch-size-avg` / `batch-size-max` | Average and maximum batch size in bytes |
| `records-per-request-avg` | Average number of records per request |
| `compression-rate-avg` | Average compression ratio of batches |
| `record-queue-time-avg` / `record-queue-time-max` | Time records wait in the producer before sending |
| `buffer-available-bytes` | Remaining available buffer capacity |
| `request-latency-avg` | Request latency to the broker |
| `record-send-rate` / `record-error-rate` | Record send rate and error rate |

Kafka producer metrics are typically exposed via JMX; metric names and monitoring integration depend on the client and observability platform. Track throughput, p95/p99 latency, CPU, network throughput, and send errors together. If batch size increases while compression CPU spikes or latency breaches SLAs, the new configuration may not be suitable.

A practical benchmarking workflow:

1. Record the current configuration and run a test load representative of production.
2. Measure throughput, latency, batch size, records per request, queue time, and CPU.
3. Change one small group of settings at a time, e.g., `linger.ms` first and then `batch.size`.
4. Test at low, medium, and peak load to observe latency when batches are not full.
5. Check whether the buffer frequently depletes and whether `TimeoutException`, retries, or record errors occur.
6. Choose the configuration that meets latency and throughput SLAs with acceptable CPU/memory usage.

## 11. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| `batch-size-avg` stays very small | Low traffic, many partitions, `linger.ms` too short, or frequent producer flushes | Measure record rate per partition; try moderately increasing `linger.ms` and removing unnecessary flushes |
| Latency rises after enabling batching | `linger.ms` too high or queue congestion | Reduce wait time, inspect queue time and broker speed |
| `send()` blocks then times out | Buffer full, slow broker, or metadata unavailable | Check `buffer-available-bytes`, `max.block.ms`, broker, and network; do not just enlarge the buffer |
| High producer CPU usage | CPU-heavy compression or expensive serialization | Compare compression algorithms, measure CPU, and optimize serializers |
| Message/request too large error | Large records or incompatible producer/broker/topic limits | Check `max.request.size` and broker/topic message/batch limits |
| Throughput unchanged after raising batch size | Batches are not filling up; bottleneck is broker, network, serialization, or app | Use metrics to find the real bottleneck before increasing size further |

## Production readiness checklist

- `batch.size` and `linger.ms` are chosen based on throughput and latency budgets.
- Partition count and key distribution are accounted for when evaluating batch size.
- `buffer.memory` is sufficient for expected traffic without causing excessive memory pressure.
- Compression has been benchmarked on real data and CPU usage has been verified.
- `max.request.size`, broker/topic message limits, and record sizes are compatible.
- Timeouts `max.block.ms`, `request.timeout.ms`, and `delivery.timeout.ms` are configured consistently.
- The application handles send results asynchronously and avoids unnecessary per-record flushes.
- Metrics are in place to monitor batch size, queue time, buffer, throughput, latency, and send errors.

Producer-side batching is a mechanism for optimizing Kafka transport and processing capacity. Effective configuration depends on records per partition, record size, allowable latency, compression, and broker capacity. Make controlled changes and verify with metrics under representative load to find the right balance.
