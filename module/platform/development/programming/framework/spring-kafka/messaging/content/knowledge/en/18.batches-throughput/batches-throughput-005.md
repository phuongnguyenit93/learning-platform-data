# Batch size and poll timing

When consuming events with Spring Kafka, an application can receive one record at a time or receive multiple records in a single listener invocation. Receiving in batches reduces method-invocation, data-conversion, and offset-commit overhead, thereby increasing throughput on high-traffic topics. However, large batches also increase how much data must be held in memory and the processing duration between two `poll()` calls. With unsuitable settings, the consumer can experience higher latency, overly long processing, or group eviction for violating poll timing limits.

This lesson explains how Kafka forms consumer batches, the role of size and wait parameters, how to configure batch listeners in Spring Kafka, and how to select values based on actual processing duration.

## 1. How is a batch formed?

A consumer does not necessarily receive each record the instant it is written to a topic. The Kafka client sends fetch requests to brokers, retrieves data from assigned partitions, buffers fetched data internally, and returns records to the application through `poll()`.

With a batch listener, Spring Kafka turns the records returned by a single `poll()` call into a single listener invocation. The data flow can be visualized as follows:

```mermaid
flowchart LR
    A[Topic and partitions] --> B[Kafka broker returns fetched data]
    B --> C[Kafka consumer buffers data]
    C --> D[consumer.poll() returns records]
    D --> E[Spring Kafka batch listener]
    E --> F[Process and commit offsets per configuration]
```

The actual batch size is the number of records in the result of one `poll()` call. This value can be smaller than the configured limit because the broker does not yet have enough data, the consumer is assigned only a subset of partitions, byte-level fetch limits apply, or records arrive incrementally. Therefore, setting a limit of 500 records does not mean the listener always receives exactly 500 records every time.

The Kafka consumer may also have fetched more data into its internal buffer while returning at most the permitted number of records in the current `poll()`. The remainder can be returned in subsequent polls. This distinguishes the cap on records handed to the application per poll from the byte volume a broker sends in a single fetch response.

## 2. Parameters affecting batches and polls

The following parameters solve different problems. Understand each role before tuning them together.

| Parameter | Scope | Meaning and impact |
|---|---|---|
| `max.poll.records` | Kafka consumer | Limits the maximum number of records returned by one `poll()` call. This directly bounds element count in a batch listener. Raising it can increase throughput, yet also increases memory and single-batch processing time. |
| `fetch.min.bytes` | Kafka consumer / broker fetch | Minimum bytes of data the consumer prefers to receive in a fetch response. The broker may wait for more data to reach this threshold. Higher values improve batching under heavy load, at the cost of extra latency under low traffic. |
| `fetch.max.wait.ms` | Broker fetch | Maximum time the broker waits to satisfy `fetch.min.bytes` before returning a fetch response. This is part of broker-side data accumulation. |
| `max.partition.fetch.bytes` | Kafka consumer | Limits data fetched per partition in a single request. This parameter affects data volume and memory, rather than directly setting the batch record count. |
| `fetch.max.bytes` | Kafka consumer | Limits total data in a single fetch response. This is a byte limit, unlike `max.poll.records` which is a record-count limit. Kafka makes an exception so consumers can still progress if a partition's first batch exceeds the configured limit. |
| `pollTimeout` | Spring Kafka container | How long the container waits in `consumer.poll(Duration)`. If data is already available, poll can return early. This is not the time budget allowed for the listener to process a batch. |
| `max.poll.interval.ms` | Kafka consumer | Maximum interval allowed between two `poll()` calls. Listener batch processing time falls within this gap between polls. If processing takes too long and exceeds the limit, the consumer may be considered dead and trigger a group rebalance. |

Two pairs of parameters are frequently confused:

- `pollTimeout` governs how long a single poll waits for data; `max.poll.interval.ms` bounds the gap between two polls, including the time the application spends processing received data.
- `max.poll.records` caps the number of records returned; `fetch.min.bytes` and fetch settings control byte volume and how the broker waits for data. Raising `max.poll.records` does not force the broker to produce enough records for a full batch.

## 3. Enabling batch listeners in Spring Kafka

For a listener to receive multiple records per invocation, the container factory must be configured in batch mode. The example below creates a dedicated factory for the order stream and sets the poll timeout to one second:

```java
@Configuration
public class KafkaBatchConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, Order> orderBatchFactory(
            ConsumerFactory<String, Order> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, Order> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.getContainerProperties().setPollTimeout(1_000L);
        return factory;
    }
}
```

The listener can accept a list of `ConsumerRecord` to access key, value, partition, offset, and timestamp:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-worker",
        containerFactory = "orderBatchFactory")
public void consume(List<ConsumerRecord<String, Order>> records) {
    for (ConsumerRecord<String, Order> record : records) {
        process(record.value());
    }
}
```

If the application only needs payloads, the listener can use a payload list type compatible with the configured message converter and deserializer. Regardless of parameter style, a batch listener must be paired with a container factory that sets `setBatchListener(true)`; using a record listener factory causes a list-accepting signature to mismatch the processing mode.

Kafka consumer limits can be configured via Spring Boot. The following example illustrates a starting configuration for a relatively high-traffic workload; values should be measured and tuned based on message size, processing capacity, and system latency requirements:

```yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
      properties:
        "[max.poll.interval.ms]": 300000
        "[fetch.min.bytes]": 65536
        "[fetch.max.wait.ms]": 100
```

Square-bracket syntax lets Spring Boot preserve dotted Kafka property names when binding the `properties` map. `pollTimeout` in the Java example is a Spring Kafka container property; the remaining properties are forwarded to the Kafka consumer.

## 4. Choosing batch size based on processing time

Large batches help only when the consumer can process them within a safe window. If the listener processes each record sequentially, processing time can be estimated as:

\[
T_{batch} \approx T_{overhead} + B \times T_{record}
\]

Where:

- `B` is the actual number of records in the batch.
- `T_record` is the time to process a single record; examine high percentiles such as p95 or p99 rather than only the average.
- `T_overhead` covers fixed costs such as message conversion, database access, logging, and offset commits.

For example, if each record takes around 15 ms and the listener processes 200 records sequentially, record processing alone can take around 3 seconds. Actual time also depends on I/O, resource contention, GC, and end-of-batch operations. If this total approaches `max.poll.interval.ms`, the consumer risks missing the next poll and triggering a rebalance. Keep substantial headroom for load spikes instead of setting the limit tightly against measured averages.

A single consumer's throughput can be estimated broadly as the number of records processed divided by one cycle's duration, which includes poll wait time, batch processing, and overhead. When multiple consumers run concurrently, total capacity can scale with active consumers, though still bounded by partition count, downstream resources, and load distribution. `max.poll.records` applies per consumer; do not treat it as an aggregate limit across the entire listener container.

Practical rules of thumb:

1. **Start with a moderate batch.** Measure processing duration and memory before raising `max.poll.records`. Change one parameter at a time to identify what improves throughput versus what adds latency.
2. **Increase batches when fixed costs dominate.** If each listener invocation or commit carries noticeable overhead, grouping more records reduces per-record cost.
3. **Shrink batches when processing stretches out or memory climbs.** Large messages, large payload lists, or slow sequential processing are all reasons to lower `max.poll.records`.
4. **Tune fetch settings to traffic.** High `fetch.min.bytes` fits topics with steady traffic prioritizing throughput. For low-volume topics or low-latency needs, lower byte thresholds and shorter wait times usually fit better.
5. **Increase `max.poll.interval.ms` only once processing duration is understood.** If a batch legitimately needs more time to finish, extend the poll interval accordingly. Raising it indiscriminately only masks slow listeners and delays detection of hung consumers.
6. **Match concurrency to partitions.** Each consumer in the container receives its own assigned partitions. Raising consumer thread count above the partition count cannot increase consumption capacity while still consuming extra resources.

## 5. Monitoring to verify configuration effectiveness

Do not judge a configuration solely by the record count in one batch. Observe throughput, latency, and consumer stability together:

| Metric to monitor | How to interpret |
|---|---|
| Records per listener invocation | Shows whether actual batches stay near `max.poll.records` or are frequently smaller. |
| Records consumed rate and consumer lag | Shows whether consumption keeps pace with event production. |
| Batch processing duration, especially p95/p99 | Shows whether the listener has enough time to call the next poll before `max.poll.interval.ms`. |
| Heap memory and GC activity | Large batches can retain many payloads and intermediate objects simultaneously. |
| Rebalance count and processing errors | Abnormal rebalance spikes can indicate overly slow batch processing or unstable consumers. |
| Offset commit and downstream operation time | Pinpoints whether bottlenecks lie in commits, the database, or dependent services. |

If batches are consistently small despite high `max.poll.records`, inspect partition traffic and fetch limits before increasing the record cap further. If batches are consistently full while lag still climbs, examine processing duration, downstream capacity, and how many consumers can run concurrently. If latency rises without throughput gains, revisit `fetch.min.bytes`, `fetch.max.wait.ms`, and `pollTimeout`.

## 6. Key points to remember when processing batches

- Kafka preserves record ordering within each partition; a batch can contain records from multiple partitions, so there is no global ordering across partitions.
- Receiving a list in the listener does not mean every record's offset is committed the moment processing begins. Commit timing depends on `AckMode`, transactions, and Spring Kafka's error handler configuration.
- If batch processing can be re-executed after errors, retries, or rebalances, business logic should be idempotent or include suitable deduplication safeguards.
- `pollTimeout` does not replace `max.poll.interval.ms`. A short poll wait does not help if the listener spends too long processing the batch before the next poll.
- No single batch size is optimal for every system. The right value balances throughput, latency, memory, processing time, and downstream service capacity.

When tuning, start from batch processing duration and consumer lag, then adjust record limits, fetch settings, and poll intervals incrementally. The goal is for consumers to receive enough data to lower overhead while consistently finishing each processing cycle with ample margin before the next `poll()`.
