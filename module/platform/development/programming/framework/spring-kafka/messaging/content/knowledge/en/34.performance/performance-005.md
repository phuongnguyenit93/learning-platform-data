# fetch.min.bytes and fetch.max.wait.ms

`fetch.min.bytes` and `fetch.max.wait.ms` are two Kafka consumer configurations that control how the broker returns data in a fetch request. `fetch.min.bytes` sets the desired byte threshold for a fetch response; `fetch.max.wait.ms` sets the maximum time the broker waits to accumulate enough data before returning the response. Combining these two parameters balances throughput, network efficiency, and latency when the consumer reads events from Kafka.

In the `SPRING_KAFKA_MESSAGING` module, the consumer receives events with `@KafkaListener`, while Spring Kafka manages `KafkaConsumer` underneath the listener container. Both properties belong to consumer configuration; they affect how much data the broker sends in a single fetch and the broker-side wait time, not how many times the listener is invoked or how many records are committed.

## 1. How does a consumer fetch data?

The consumer does not send a separate request per record. The Kafka consumer sends fetch requests to the broker holding the leader of its assigned partitions. The broker returns record batches from the partitions in the request. When enough data is not yet available, the broker can hold the request for a limited time to accumulate more bytes.

~~~mermaid
sequenceDiagram
    participant C as Kafka consumer
    participant B as Partition leader broker
    C->>B: Fetch(minBytes, maxWaitMs)
    Note over B: Wait for appended data
    alt Enough fetch.min.bytes
        B-->>C: Fetch response with accumulated data
    else fetch.max.wait.ms elapsed
        B-->>C: Fetch response with currently available data
    end
    C->>C: Buffer records and return via poll()
~~~

The broker returns a response when either condition is met: accumulated data reaches the `fetch.min.bytes` threshold, or wait time reaches `fetch.max.wait.ms`. Under low traffic, the response may be smaller than the min threshold when the wait time expires. Under high traffic, the min threshold may be reached very quickly, so the broker returns before max wait expires.

## 2. What is `fetch.min.bytes`?

`fetch.min.bytes` is the minimum number of bytes of data the consumer wants the broker to return in a fetch response. The default is typically `1`, meaning the broker can respond as soon as data is available. Setting a larger value lets the broker group more data into the response, reducing small responses and potentially improving network efficiency at high throughput.

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.min.bytes: 65536
~~~

The value `65536` equals 64 KiB. The broker will try to wait until the response has at least around 64 KiB of data or until the `fetch.max.wait.ms` limit. This is a threshold for the fetch response, not a requirement that every record or every partition have 64 KiB.

If the consumer is assigned multiple partitions on the same broker, data from those partitions can contribute together toward the byte threshold of the corresponding fetch request. Therefore, a single partition does not need to produce `fetch.min.bytes` on its own.

## 3. What is `fetch.max.wait.ms`?

`fetch.max.wait.ms` is the maximum time the broker waits to satisfy the `fetch.min.bytes` condition. The default is typically `500` milliseconds.

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.max.wait.ms: 100
~~~

The broker waits up to 100 ms for the fetch request if it has not accumulated `fetch.min.bytes`. When time expires, the broker returns whatever data is currently available, even if the byte count is below the min threshold.

This is a broker-side wait time for a fetch request. It is not a delay before each listener invocation, not `max.poll.interval.ms`, and not a timeout for a single business call.

## 4. How the two parameters work together

The two configurations should be read together:

| `fetch.min.bytes` | `fetch.max.wait.ms` | Typical behavior |
|---:|---:|---|
| 1 | 500 | Broker can return early as soon as data exists; max wait mainly limits waiting when no data exists |
| 65536 | 100 | Accumulates up to ~64 KiB or waits at most 100 ms |
| 262144 | 250 | Tries to accumulate ~256 KiB; can improve batching at the cost of waiting longer |
| 1 | 50 | Prioritizes early responses, reducing wait time under sparse traffic |

For example, setting `fetch.min.bytes` high and `fetch.max.wait.ms` low gives the broker only a brief window to accumulate data, so it often returns responses smaller than the threshold under low traffic. Conversely, a small min and large max wait does not force the broker to wait the full duration once data already meets the min threshold.

There is no single optimal pair of values for all topics. Choose based on traffic, record size, partitions per consumer, target latency, and downstream capacity.

## 5. Configuration in Spring Boot

Spring Boot passes Kafka consumer properties through the `spring.kafka.consumer.properties` map. Common configuration example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.acme.orders.OrderCreatedEvent
        spring.json.trusted.packages: com.acme.orders
        fetch.min.bytes: 65536
        fetch.max.wait.ms: 100
        request.timeout.ms: 30000
~~~

The keys `fetch.min.bytes`, `fetch.max.wait.ms`, and `request.timeout.ms` are native Kafka consumer configuration names. They are placed under `properties` because Spring Boot does not create a dedicated type-safe field for every Kafka client property.

Keep `request.timeout.ms` larger than `fetch.max.wait.ms` with enough margin for network/broker processing. If the request timeout is shorter than the time the broker can hold a fetch request, the consumer may time out before the broker completes the response.

## 6. Direct configuration via `ConsumerFactory`

If creating `ConsumerFactory` manually, you can put the Kafka consumer properties in the configuration map:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;

@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    public ConsumerFactory<String, String> ordersConsumerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-service");
        properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        properties.put(ConsumerConfig.FETCH_MIN_BYTES_CONFIG, 65_536);
        properties.put(ConsumerConfig.FETCH_MAX_WAIT_MS_CONFIG, 100);
        properties.put(ConsumerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);

        return new DefaultKafkaConsumerFactory<>(properties);
    }
}
~~~

Do not declare the same consumer property in multiple places with different values without knowing the override precedence. When Spring Boot auto-configures a factory, a custom `ConsumerFactory` may replace or omit part of Boot's configuration; verify the actual factory used by the listener container.

## 7. Distinguishing from other fetch limits

`fetch.min.bytes` and `fetch.max.wait.ms` are not maximum response size limits. Other related configurations:

| Configuration | Role | Primary effect |
|---|---|---|
| `fetch.min.bytes` | Desired minimum byte threshold | Broker may wait to accumulate a batch |
| `fetch.max.wait.ms` | Maximum broker wait time | Caps the wait time for batch accumulation |
| `fetch.max.bytes` | Target total byte limit for a fetch response | Controls how much data one fetch can return |
| `max.partition.fetch.bytes` | Target byte limit per partition in a fetch | Controls data volume per partition |
| `max.poll.records` | Maximum records returned by a single `poll()` | Controls how many records the app gets per poll |
| `max.poll.interval.ms` | Maximum time between `poll()` calls | Controls consumer group liveness |

Kafka can still return the first record batch even if it exceeds `fetch.max.bytes` or `max.partition.fetch.bytes` so the consumer does not get stuck when the first batch in a partition exceeds the limit. Therefore, those two max settings are target fetch limits, not a hard guarantee that a response never exceeds that size.

`max.poll.records` limits the number of records returned from `poll()`, not the bytes sent by the broker in a fetch response. The consumer can fetch and buffer data before the application retrieves records via poll.

## 8. Distinguishing from poll timeout and listener container

The Spring Kafka listener container calls `KafkaConsumer.poll()` in a loop. The container's `pollTimeout` controls the timeout passed to the poll call; `fetch.max.wait.ms` controls how long the broker can hold a fetch request to accumulate enough bytes.

| Component | Where does it live? | What does it control? |
|---|---|---|
| `fetch.max.wait.ms` | Kafka broker handling fetch request | Waiting for data on the broker |
| `pollTimeout` | Spring Kafka listener container | How long a single `poll()` waits for results |
| `max.poll.interval.ms` | Kafka consumer group | Time limit between poll calls |
| `max.poll.records` | Kafka consumer | Maximum records returned from poll |

These durations interact in overall latency, but do not replace each other. Increasing `pollTimeout` does not make the broker accumulate more bytes; increasing `fetch.max.wait.ms` does not make the listener process faster.

## 9. Choosing settings for low-latency workloads

For events that must be processed promptly, keep `fetch.min.bytes` low so the broker returns responses as soon as data is available. You can lower `fetch.max.wait.ms` to cap how long the broker waits when no data is present yet.

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.min.bytes: 1
        fetch.max.wait.ms: 50
~~~

This example is a good benchmark starting point for low-volume, low-latency workloads. It can increase small fetch responses and request rates under high traffic. Do not lower max wait too aggressively if the broker/consumer are far apart or the cluster is under heavy load without measuring the impact.

## 10. Choosing settings for high-throughput workloads

For workloads with steady traffic and small records, you can raise `fetch.min.bytes` to gather more data in one response and choose a moderate `fetch.max.wait.ms`:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.min.bytes: 131072
        fetch.max.wait.ms: 100
        fetch.max.bytes: 52428800
        max.partition.fetch.bytes: 1048576
        max.poll.records: 500
~~~

In this example, the consumer aims to gather around 128 KiB before the broker responds, while the broker waits at most 100 ms. The fetch max and poll records limits are kept explicit so you can analyze fetched bytes separately from the number of records processed per poll.

Under low traffic, the broker still responds when max wait expires, even if 128 KiB has not been reached. If downstream cannot keep up, larger fetch batches can increase buffered data and memory pressure; coordinate with `max.poll.records`, concurrency, and backpressure.

## 11. Impact on latency and throughput

Increasing `fetch.min.bytes` typically has these effects:

- Reduces small responses when data arrives steadily.
- Increases average bytes per fetch response.
- Can improve network efficiency and throughput.
- Can increase wait time when traffic is sparse or spread across many partitions/brokers.

Increasing `fetch.max.wait.ms` typically has these effects:

- Gives the broker more time to group records into one response.
- Can increase batch size and reduce the frequency of small responses.
- Can increase latency for newly arrived records when `fetch.min.bytes` is not yet met.
- Can make the consumer feel slower when the topic has low traffic.

Lowering both parameters can deliver records to the listener sooner, but may also increase request/response overhead. Actual results depend on record size, compression, partition count, consumer count, producer rate, and network.

## 12. How to benchmark and tune

Tune following a controlled process:

1. Record a baseline with the current configuration: throughput, p50/p95/p99 processing latency, consumer lag, and fetch response size.
2. Use a representative workload: producer rate, key distribution, partition count, and payload size close to production.
3. Change one parameter at a time, e.g., raise `fetch.min.bytes` from 1 to 64 KiB.
4. Re-measure latency and throughput under both high traffic and low traffic.
5. Test changing `fetch.max.wait.ms` separately to isolate the effect of broker wait.
6. Check memory/buffers, CPU, network, broker request rate, and consumer lag.
7. Pick settings that satisfy latency and throughput SLOs, then test when downstream is slow.

Do not pick values based solely on peak throughput. If p99 latency exceeds the SLO or consumer lag grows continuously, the configuration may be unsuitable even if bytes/response increased.

## 13. Metrics and signs of misconfiguration

Monitor metrics from the consumer, Spring Kafka, and the broker:

| Metric | Signs to watch for |
|---|---|
| Consumer fetch rate | Too many tiny fetch requests or an abnormal drop in fetch rate |
| Fetch size / bytes consumed rate | Responses smaller than expected or fetched data failing to keep up with producer |
| Fetch latency | Fetch duration rising as max wait increases |
| Records consumed rate | Actual consumer throughput |
| Per-partition consumer lag | Backlog growing despite large fetch responses |
| Listener processing time | Slow downstream preventing the consumer from keeping up |
| Rebalance count | May rise when processing/polling is delayed |
| Heap, GC, and network throughput | Detects buffers or fetch batches causing resource pressure |

Exact metric names depend on the Kafka client version, Spring Kafka Micrometer integration, and monitoring system. Verify which metrics are actually exported instead of assuming every dashboard name exists.

## 14. Common mistakes

- **Setting `fetch.min.bytes` too high for low-traffic topics:** the broker often waits nearly the entire max wait only to return a small response.
- **Setting `fetch.max.wait.ms` too high:** increases wait time when byte threshold is not met, raising latency.
- **Thinking max wait is a fixed delay:** the broker responds early once min bytes are met.
- **Mistaking min bytes for a per-partition threshold:** it is a threshold for the fetch response, not per record/partition.
- **Confusing `max.poll.records` with fetch size:** one limits records returned via poll, the other governs fetch bytes.
- **Confusing `pollTimeout` with broker wait:** they operate at two different layers.
- **Setting `request.timeout.ms` lower than fetch wait:** the client may time out before the fetch response is returned.
- **Increasing fetch batches without monitoring memory:** larger buffered data can increase heap pressure.
- **Benchmarking only high traffic:** settings that batch well at high load can hurt latency at low load.
- **Assuming fetch max is a hard cap:** Kafka makes an exception for the first record batch so the consumer can make progress.

## 15. Configuration checklist

- [ ] `fetch.min.bytes` is chosen based on traffic and latency SLOs.
- [ ] `fetch.max.wait.ms` caps batch accumulation wait time appropriately.
- [ ] Distinguished both properties from `fetch.max.bytes` and `max.partition.fetch.bytes`.
- [ ] `max.poll.records` is tuned independently according to listener processing time.
- [ ] `pollTimeout` and `max.poll.interval.ms` are properly understood at the container/consumer layer.
- [ ] `request.timeout.ms` is larger than fetch wait with network margin.
- [ ] Benchmarked under both high traffic and low traffic.
- [ ] Monitored fetch size, fetch latency, consumer lag, and listener processing time.
- [ ] Checked heap/network when increasing batch size.
- [ ] Tested with production-like partition count, concurrency, and payloads.

`fetch.min.bytes` controls how much data the consumer wants grouped into a fetch response, while `fetch.max.wait.ms` caps how long the broker waits to accumulate that data. Raising them can improve batching and throughput at the cost of latency, especially under low traffic. Good settings should be chosen via real benchmarks and evaluated alongside fetch limits, poll limits, memory, and downstream capacity.
