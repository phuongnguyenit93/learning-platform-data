# Latency vs. throughput trade-offs

When building messaging pipelines with Spring Kafka, a producer can send each record immediately as an event occurs or accumulate multiple records into a batch before sending. A consumer can likewise fetch one record at a time or process multiple records from a single `poll()`. Batching typically reduces request count and uses the network and compression more efficiently, increasing throughput. In exchange, the application may wait for sufficient data or batching timers to expire, increasing latency.

No single configuration is optimal for every system. Notification flows needing fast responses typically prioritize low latency; data-sync or analytics flows typically prioritize throughput and resource efficiency. Choosing well requires looking across producer, broker, consumer, and downstream business systems.

## 1. Distinguishing latency and throughput

These two metrics describe different dimensions:

- **Latency** is the time it takes a record to travel from a chosen start point to a chosen end point—for example, from when the producer sends an event until the consumer finishes processing it.
- **Throughput** is the amount of work completed per unit of time, such as records/sec or MB/sec.

A system can achieve high throughput while each record waits longer in a batch or queue. Conversely, a system sending every record immediately can achieve low latency under light load while incurring high request and CPU costs under heavy load.

When measuring latency, do not look only at the average. Track p50, p95, and p99 to spot tail records delayed by batch waiting, brokers, network, retries, or dependencies. Throughput should also be measured at multiple points: successful producer sends, consumer reads, and completed business processing.

| Metric | Question it answers |
|---|---|
| Producer latency | How long does the producer take from `send()` until broker acknowledgement? |
| End-to-end latency | How long does an event take from creation until consumer processing finishes? |
| Records/sec | How many records are sent/read/processed per second? |
| Bytes/sec | How much actual data is transferred or processed per second? |
| p95/p99 latency | How long do the slowest records in the distribution take? |

Agree on measurement points before comparing numbers. For example, completion time of the future returned by `KafkaTemplate.send()` does not include consumer business processing time.

## 2. How does producer batching work?

A Kafka producer does not necessarily send a separate network request per record. The producer groups records into batches per target partition. When a batch grows large enough or its wait timer expires, the producer sends the batch to the broker.

Two key settings are:

- `batch.size`: target capacity of a batch per partition, in bytes.
- `linger.ms`: maximum time the producer waits to accumulate additional records into a batch before sending if the batch is not yet full.

If a batch reaches capacity before `linger.ms` elapses, the producer can send immediately. If traffic is light and the batch is not full, the producer sends when the timer expires. Thus, `linger.ms` can increase latency under low load while making batches fuller when records arrive closely together.

```text
Record A ----+
Record B ----+----> Batch for partition 0 ----+
Record C ----+                                |
                                              +--> Produce request --> Broker
Record D --------> Batch for partition 1 ---+

Batch is sent when full or when linger.ms expires.
```

Batches are organized independently per partition. If a producer sends across many partitions while each partition receives very few records, many batches may stay underfilled despite high overall topic traffic. This is why key distribution and partition count affect batching efficiency.

### `batch.size` is not a record size limit

`batch.size` specifies the buffer size the producer tries to allocate per partition batch. It is not a hard cap on an individual record's size. A record larger than `batch.size` can be sent in its own batch; maximum record/batch sizes remain governed by producer, broker, and topic limits such as `max.request.size`, `message.max.bytes`, or `max.message.bytes` depending on configuration.

Increasing `batch.size` can pack more records together, yet it also raises buffer memory consumption when many partitions are active. Under low traffic, a large `batch.size` does not automatically generate higher throughput; records may still be sent when `linger.ms` expires with partially filled batches.

## 3. Tuning `linger.ms` and `batch.size`

Example producer configuration in Spring Boot:

```yaml
spring:
  kafka:
    producer:
      batch-size: 32768
      properties:
        "[linger.ms]": 5
```

In this example, the producer allocates a 32 KiB target batch per partition and waits up to roughly 5 ms to accumulate more records when a batch is not full. This is a starting point for benchmarking, not an optimal configuration for all workloads.

| Setting | Typical effect when increased |
|---|---|
| `linger.ms` | Batches fill more completely, reducing request count; low-load latency may rise |
| `batch.size` | Batches can hold more bytes; increases buffer memory demand and may not help if per-partition traffic is low |

Do not set `linger.ms` excessively high merely to boost batch utilization. If an SLA demands a tight p99 threshold, batch wait time can consume a large share of the latency budget under low traffic.

## 4. Compression and related producer settings

Compression applies at the batch level, so larger batches usually compress more effectively. Kafka supports common codecs such as `none`, `gzip`, `snappy`, `lz4`, and `zstd` depending on broker/client versions.

```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      properties:
        "[linger.ms]": 5
        "[compression.type]": lz4
        "[enable.idempotence]": true
```

| Codec | General characteristics |
|---|---|
| `none` | No compression; saves CPU but transfers more bytes |
| `gzip` | Typically strong compression ratio at the cost of higher CPU usage |
| `snappy` | Favors compression/decompression speed with moderate ratio |
| `lz4` | Typically offers a strong balance between speed and compression ratio |
| `zstd` | Can achieve high compression ratios; evaluate CPU cost by compression level and environment |

Choose a codec by measuring CPU, network bytes, and latency on real payloads. Repetitive JSON fields usually compress much better than already-compressed or random data. Compression does not reduce record count, nor does it replace sensible payload design.

Other settings also affect latency and reliability:

- `acks=all` waits for acknowledgements from in-sync replicas per Kafka policy; this can add acknowledgement latency while raising write durability.
- `enable.idempotence=true` helps the producer avoid duplicates from retries within Kafka producer guarantees; compatible settings must be maintained.
- `max.in.flight.requests.per.connection` affects how many unacknowledged requests can be in flight per connection. When idempotence is enabled, respect the compatible limits for your Kafka client version.
- `buffer.memory` is the producer memory pool for unsent records. When the buffer fills up, `send()` may block for up to `max.block.ms`.
- `delivery.timeout.ms` bounds the total time the producer spends trying to complete a send before failing; coordinate it with `request.timeout.ms` and retry settings.

Do not weaken producer durability solely to improve a latency metric without assessing the risk of lost or duplicated data.

## 5. Asynchronous sending with KafkaTemplate

`KafkaTemplate.send()` sends records asynchronously and returns a future. If the application waits on the result immediately after every send, the benefits of batching and concurrent requests drop sharply.

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId,
            String payload
    ) {
        return kafkaTemplate.send("orders.events", orderId, payload);
    }
}
```

Callers can continue other work and attach callbacks to handle outcomes:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;

class OrderSendObserver {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSendObserver.class);

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderSendObserver(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    void observe(String orderId, String payload) {
        kafkaTemplate.send("orders.events", orderId, payload)
                .whenComplete((result, error) -> {
                    if (error != null) {
                        log.error("Send order event failed: orderId={}", orderId, error);
                        return;
                    }

                    var metadata = result.getRecordMetadata();
                    log.debug(
                            "Sent order event: topic={}, partition={}, offset={}",
                            metadata.topic(), metadata.partition(), metadata.offset()
                    );
                });
    }
}
```

The examples use the Spring Kafka 3.x future API. In older versions, future types and callbacks may differ. Never call `flush()` after every record in normal sending flows: doing so forces the producer to push buffered records immediately and defeats batching. Flush only at appropriate boundaries, such as before closing the producer or when the application genuinely must drain buffered records.

If business logic requires send confirmation before returning a response, wait on the future at that boundary. Still, weigh request latency and avoid turning every send into an unnecessary synchronous operation.

## 6. Consumer fetch batching and `max.poll.records`

The consumer side also has two distinct stages: the Kafka client fetches data in bytes from brokers, and `poll()` delivers records to the application. Key settings include:

| Property | Role |
|---|---|
| `fetch.min.bytes` | Minimum bytes the consumer wants from the broker before returning a fetch response, if waiting is possible |
| `fetch.max.wait.ms` | Maximum time the broker waits to satisfy `fetch.min.bytes` |
| `fetch.max.bytes` | Total byte cap for a single fetch response, with an exception ensuring the consumer can make progress on the first batch |
| `max.partition.fetch.bytes` | Typical fetch byte cap per partition |
| `max.poll.records` | Maximum records returned to the application in a single `poll()` |

`fetch.min.bytes` and `fetch.max.wait.ms` govern broker data accumulation before sending a fetch response. `max.poll.records` caps how many records the application receives from one poll; it is not a byte cap and is not synonymous with fetch batch size.

Example consumer configuration:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      max-poll-records: 200
      properties:
        "[fetch.min.bytes]": 32768
        "[fetch.max.wait.ms]": 20
```

Under heavy traffic, `fetch.min.bytes` can cut fetch request count by waiting for more data. Under light traffic, the broker may wait up to `fetch.max.wait.ms` before returning data, adding latency. Choose values aligned with SLAs and actual traffic.

## 7. Record listeners vs. batch listeners

Spring Kafka supports two common consumption styles:

- **Record listener:** the container invokes the listener method for each individual record. The Kafka client may still retrieve multiple records per poll, yet the application handles per-record callbacks.
- **Batch listener:** the container passes the list of records from one poll to the listener for group processing.

A batch listener can reduce method-call overhead and leverage bulk operations in a database or target service.

```java
import java.util.stream.Collectors;
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderBatchListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection",
            containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void consume(List<ConsumerRecord<String, String>> records) {
        var orders = records.stream()
                .map(ConsumerRecord::value)
                .collect(Collectors.toList());

        bulkUpdate(orders);
    }

    private void bulkUpdate(List<String> orders) {
        // Write multiple events using an appropriate bulk operation.
    }
}
```

Factory configured in batch mode:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class BatchListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        return factory;
    }
}
```

Actual batch size can be smaller than `max.poll.records` due to available data, partition assignment, and fetch limits. A batch can also contain records from multiple partitions; Kafka guarantees order only within each partition, without imposing a global order across the whole list.

## 8. Poll size, concurrency, and processing duration

Increasing `max.poll.records` can let a consumer process more records per cycle, yet batch processing time also rises. If the listener processes synchronously, the consumer must invoke the next `poll()` before `max.poll.interval.ms` expires; otherwise, Kafka may treat the consumer as stalled and trigger a rebalance.

Initial estimate for sequential batch processing:

\[
T_{batch} \approx N \times T_{record} + T_{overhead}
\]

Where `N` is the actual record count in the batch, `T_record` is the processing time per record, and `T_overhead` is extra time such as bulk operations, deserialization, or commits. Use high percentiles of processing duration to verify safety margins against `max.poll.interval.ms`, not averages alone.

Listener concurrency creates multiple consumers in the same group, though parallelism remains bounded by assigned partitions. If a topic has four partitions, raising concurrency from four to eight will not produce eight consumers reading that topic simultaneously; some consumers will receive no partitions.

Increasing concurrency can improve throughput when partitions and target systems have spare capacity. If the database is already saturated, adding consumers only increases lock contention, connection pressure, competing requests, and latency.

## 9. Other factors altering latency and throughput

Batching is only one part of the end-to-end path:

| Factor | Impact to consider |
|---|---|
| Partition count | Increases load-distribution potential, yet too many partitions add overhead and thin out per-partition batches |
| Key distribution | Skewed keys can create hot partitions; one overloaded partition caps throughput for that key stream |
| Payload size | Large payloads increase network traffic, memory usage, and serialization/deserialization cost |
| Compression | Reduces transferred bytes at the expense of CPU |
| Replication and `acks` | Write acknowledgement level affects durability and producer latency |
| Broker/network | Disk, network, request queues, and ISRs can become bottlenecks |
| Consumer processing | Databases, HTTP calls, locks, and CPU can limit processing rate |
| Retries | Backoff delays and repeated failures raise latency and reduce effective throughput |

When one partition has a hot key, raising `batch.size` or concurrency does not fix key imbalance. Review key strategy, partition count, and entity splitting if business logic permits.

## 10. Choosing configurations by goal

The configurations below are starting points for benchmarking. They are not fixed defaults or universal prescriptions; adjust them for payload size, partition count, hardware, Kafka version, and SLAs.

| Goal | Suggested producer | Suggested consumer | Trade-off |
|---|---|---|---|
| Prioritize low latency | Very low `linger.ms`; moderate batch; compression off or fast | Low `fetch.min.bytes`; low `fetch.max.wait.ms`; moderate poll batch | More requests and potentially lower throughput |
| Balanced | `linger.ms` a few ms; moderate batch; test `lz4` | Short fetch wait; moderate `max.poll.records`; batch listener where fitting | Balances latency and resource efficiency |
| Prioritize throughput | Higher `linger.ms`; larger batch; test `lz4`/`zstd` | Higher `fetch.min.bytes`; large poll batch; bulk processing | Increases wait time, memory, and single-poll processing duration |

Example balanced profile to begin measuring:

```yaml
spring:
  kafka:
    producer:
      batch-size: 65536
      properties:
        "[linger.ms]": 5
        "[compression.type]": lz4
        "[enable.idempotence]": true
    consumer:
      max-poll-records: 200
      properties:
        "[fetch.min.bytes]": 16384
        "[fetch.max.wait.ms]": 10
```

This profile merely illustrates how related properties group together. Before production use, confirm `max.poll.interval.ms` accommodates batch duration, verify `acks`/replication against durability requirements, and measure p95/p99 under representative load.

## 11. Benchmarking and tuning workflow

To know whether a change genuinely improves the system, hold the workload constant and vary one configuration group at a time under control:

1. **Establish a baseline:** record payload size, partition count, producer/consumer concurrency, records/sec, bytes/sec, and p50/p95/p99 latency.
2. **Measure the producer:** track send latency, actual batch size, request rate, compression ratio, buffer availability, retries, and error rate.
3. **Measure the consumer:** track fetch latency, records-consumed-rate, records-lag-max, listener processing time, commit latency, and rebalances.
4. **Tune `linger.ms`:** increase in small steps and compare batch utilization against latency at both low and high load.
5. **Tune `batch.size` and compression:** inspect network bytes, CPU, memory, and request rate; do not watch throughput alone.
6. **Tune fetch settings and `max.poll.records`:** gradually raise poll size while checking batch processing time against `max.poll.interval.ms`.
7. **Tune concurrency:** increase only when enough partitions exist and downstream dependencies have headroom.
8. **Test peak load and failures:** simulate bursts, slow brokers, slow databases, and retries to confirm p99 and consumer lag remain stable.
9. **Select configuration by SLO:** favor configurations meeting required throughput while keeping p95/p99, error rates, and lag within bounds.

Each test run should last long enough to reach steady state. Also measure low-load periods, because that is where `linger.ms` and `fetch.max.wait.ms` most visibly reveal wait costs.

## 12. Common misconceptions

1. **Assuming bigger batches are always faster.** Large batches can increase latency, memory pressure, and single-poll processing duration.
2. **Assuming `linger.ms` is a fixed wait for every record.** Full batches can be sent early; linger is the maximum wait to accumulate more data.
3. **Assuming `batch.size` is a hard cap on one record.** It is a target capacity per partition batch; record/message size limits are separate properties.
4. **Calling `flush()` after every `KafkaTemplate.send()`.** Doing so destroys batching efficiency and forces sender threads to wait needlessly.
5. **Confusing `max.poll.records` with fetch byte limits.** One counts records; fetch settings regulate byte volume and broker wait timing.
6. **Increasing concurrency beyond partition count and expecting matching throughput gains.** Excess consumers may receive no partitions.
7. **Measuring only average throughput.** p95/p99 can degrade even as records/sec rises.
8. **Increasing batch size while ignoring `max.poll.interval.ms`.** Listeners can run too long and trigger rebalances.
9. **Lowering `acks` or disabling idempotence solely to cut latency.** Always weigh the impact on durability and retry safety.
10. **Optimizing only the producer.** Consumers, partition skew, brokers, network, and databases can all be the real bottleneck.

Trading off latency against throughput is an end-to-end decision. Producer batching, compression, fetch batching, and batch listeners can raise processing efficiency, yet every layer can add wait time or increase work per cycle. Measure p95/p99 alongside throughput, lag, and resource utilization under realistic load, and choose settings that satisfy business SLAs rather than maximizing a single metric in isolation.
