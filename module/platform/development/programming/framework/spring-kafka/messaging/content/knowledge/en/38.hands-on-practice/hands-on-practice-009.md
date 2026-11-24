# Measuring Lag and Processing Time

Consumer lag and processing time are two key signals indicating whether a Spring Kafka application is keeping up with the event production rate. Lag shows how many records a consumer group is behind the end of the log; processing time shows how long the application takes to process a record or batch. When combined with event age, throughput, and processing errors, operations teams can distinguish insufficient consumer capacity from a slow downstream dependency or a sudden producer traffic spike.

This hands-on lab sets up measurements for three metrics: per-partition lag, listener processing time, and latency from event creation to processing completion. You will use Kafka offsets/metadata, Spring Kafka, Micrometer, and Actuator to collect metrics, then design actionable dashboards and alerts.

## 1. Distinguishing Lag, Processing Time, and Event Age

Three metrics are often loosely referred to as "latency," yet they answer different questions:

| Metric | Question | Common unit |
|---|---|---|
| Consumer lag | How many records is the consumer group still behind the end of the log? | Records, per partition or group total |
| Processing time | How long does the listener take to process a record/batch after receiving it? | Milliseconds or seconds |
| Event age / end-to-end latency | How long has the event existed by the time the consumer finishes processing it? | Milliseconds or seconds |

A consumer can have zero lag while still having high processing time if the producer emits very few records. Conversely, lag can be high while processing time is low if the producer suddenly ramps up throughput. Therefore, never rely on a single metric alone to conclude whether the system is healthy or bottlenecked.

```mermaid
flowchart LR
    A[Producer creates event] -->|occurredAt| B[Kafka topic / partition]
    B -->|offset and fetch| C[Consumer poll]
    C --> D[Listener starts processing]
    D --> E[Listener finishes]
    B -. committed offset vs. log end offset .-> F[Consumer lag]
    D -. start to finish .-> G[Processing time]
    A -. occurredAt to finish .-> H[Event age]
```

Event age includes queuing time inside Kafka, consumer fetch/dispatch time, and processing time. Processing time only measures the work performed by the listener or worker. Consumer lag is a record count, not a direct measure of seconds delayed.

## 2. Understanding How Consumer Lag Is Calculated

Kafka stores records in each partition with monotonically increasing offsets. A consumer group commits an offset representing the next position to read. If a partition's log end offset is `L` and the committed offset is `C`, basic lag is calculated as:

\[
Lag = \max(0, L - C)
\]

For example, a partition has a log end offset of 1,250 and the group has committed offset 1,200. The consumer still has roughly 50 records to catch up to the end of the log.

| Partition | Log end offset | Committed offset | Lag |
|---|---:|---:|---:|
| 0 | 1,250 | 1,200 | 50 |
| 1 | 980 | 980 | 0 |
| 2 | 2,400 | 2,250 | 150 |
| **Total** | — | — | **200** |

The committed offset is the next position to read, so do not add or subtract one due to zero-based record indexing. If a partition has no committed offset yet, interpret lag according to the group's reset/initialization policy; never silently treat a missing value as zero lag.

Lag should be monitored per partition in addition to the group total. Total lag can mask a hot partition: for instance, 5 partitions may sit near 0 while one partition's lag climbs steadily due to key skew or a slow consumer.

## 3. Observing Lag with Kafka Client and Operational Tools

The Kafka consumer client exposes metrics such as `records-lag` and `records-lag-max` per partition/client. These metrics are useful for spotting consumers falling behind. Exact metric names and how they export to Micrometer/JMX depend on the Kafka client version, Spring Boot version, and metrics configuration.

To inspect lag at the consumer group level, you can use `kafka-consumer-groups.sh`:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

The output displays partition, current offset, log end offset, and lag. Use this command for manual checks during investigations; in production, collect metrics automatically via a Kafka exporter, `AdminClient`, or your monitoring stack.

With `AdminClient`, you can calculate lag from the group's committed offsets and the latest offsets of each partition:

```java
public Map<TopicPartition, Long> calculateLag(
        AdminClient adminClient,
        String groupId) throws Exception {

    Map<TopicPartition, OffsetAndMetadata> committed = adminClient
            .listConsumerGroupOffsets(groupId)
            .partitionsToOffsetAndMetadata()
            .get(10, TimeUnit.SECONDS);

    Map<TopicPartition, OffsetSpec> requests = committed.keySet().stream()
            .collect(Collectors.toMap(
                    Function.identity(),
                    ignored -> OffsetSpec.latest()));

    Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> latest =
            adminClient.listOffsets(requests)
                    .all()
                    .get(10, TimeUnit.SECONDS);

    Map<TopicPartition, Long> lagByPartition = new HashMap<>();
    committed.forEach((partition, offset) -> {
        long endOffset = latest.get(partition).offset();
        lagByPartition.put(
                partition,
                Math.max(0L, endOffset - offset.offset()));
    });
    return lagByPartition;
}
```

This snippet illustrates partitions that already have committed offsets. In production tooling, fetch the partition list from topic metadata so partitions without committed offsets are also detected, handle rebalancing groups, and retry on `AdminClient` timeouts. Do not run `AdminClient` queries too frequently on every record processed; poll on a monitoring schedule with bounded timeouts.

On transactional topics, a `read_committed` consumer may not yet be able to read records behind an open transaction even though the log end offset has increased. When investigating lag, examine transaction duration and the last stable offset; lag relative to the log end offset can include records held back by an active transaction.

## 4. Measuring Listener Processing Time

Processing time should be measured around the actual work performed by the listener. You can use a Micrometer `Timer` to record count, total time, and latency distribution.

Example listener measuring per-record processing time:

```java
@Component
public class OrderListener {

    private final OrderService orderService;
    private final MeterRegistry meterRegistry;

    public OrderListener(
            OrderService orderService,
            MeterRegistry meterRegistry) {
        this.orderService = orderService;
        this.meterRegistry = meterRegistry;
    }

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void consume(ConsumerRecord<String, OrderEvent> record) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String result = "success";

        try {
            orderService.apply(record.value());
        }
        catch (RuntimeException ex) {
            result = "failure";
            throw ex;
        }
        finally {
            sample.stop(Timer.builder("orders.listener.processing")
                    .description("Time spent processing an order event")
                    .tag("listener", "orders")
                    .tag("result", result)
                    .register(meterRegistry));
        }
    }
}
```

The exception is still rethrown so the Spring Kafka error handler can perform retry/recovery. The timer records failed attempts as well; the `result` tag separates successes from failures. Never put `orderId`, `eventId`, keys, or exception messages into metric tags because they cause very high cardinality. Use logs or traces for per-event tracing.

If the listener is a batch listener, time the entire batch and also record the number of records in the batch using an appropriate counter/distribution. Do not compare a single-record timer directly against a batch timer without accounting for batch size.

## 5. Distinguishing Listener Time from Worker Time

If a listener simply enqueues records and returns, a timer around the listener measures enqueue time, not actual business processing time in the worker. In that pattern, measure separately:

- Queue wait time: from when the record is enqueued until a worker picks it up.
- Worker processing time: from when the worker starts until work finishes.
- In-flight count: number of events workers are currently processing.
- Queue depth: number of events waiting in the internal buffer.

Example measuring worker time:

```java
public void processQueued(OrderEvent event) {
    Timer.Sample sample = Timer.start(meterRegistry);
    String result = "success";
    try {
        orderService.apply(event);
    }
    catch (RuntimeException ex) {
        result = "failure";
        throw ex;
    }
    finally {
        sample.stop(Timer.builder("orders.worker.processing")
                .tag("result", result)
                .register(meterRegistry));
    }
}
```

Without measuring workers separately, dashboards may report low listener latency while the internal queue grows and real work finishes very slowly. With asynchronous handoffs, also verify that offsets are only acknowledged after the work has been durably persisted or completed per system guarantees.

## 6. Measuring Event Age and End-to-End Latency

Consumer lag is a record count, whereas event age shows how long the oldest record or individual events have been waiting. To measure end-to-end latency, events should include a business timestamp such as `occurredAt`:

```java
public record OrderEvent(
        String eventId,
        String orderId,
        Instant occurredAt,
        String eventType) {
}
```

The consumer computes event age when processing finishes:

```java
long ageMillis = Duration.between(
        record.value().occurredAt(),
        Instant.now()).toMillis();

Timer.builder("orders.event.age")
        .tag("event_type", record.value().eventType())
        .register(meterRegistry)
        .record(Math.max(0L, ageMillis), TimeUnit.MILLISECONDS);
```

In production, only use an `event_type` tag if the value set is bounded and controlled. If event types come from arbitrary input, normalize them into a small set. Never put event IDs or order IDs into tags.

You can use `ConsumerRecord.timestamp()` instead of a payload timestamp, but understand the timestamp type:

- `CREATE_TIME`: timestamp attached by the producer; producer clock skew can make event age negative or abnormally large.
- `LOG_APPEND_TIME`: timestamp attached by the broker on append; measures time since the broker wrote the record, excluding any time the event sat in the producer beforehand.

Synchronize clocks across nodes with NTP and pick a consistent timestamp definition. Event age is a time-based measurement; it does not replace offsets or sequence numbers for determining business ordering.

## 7. Configuring Micrometer and Spring Boot Actuator

Spring Kafka supports listener container timers when Micrometer is present. Modern Spring Kafka versions typically provide the `spring.kafka.listener` timer with tags identifying the listener, outcome, and exception; `KafkaTemplate` can also expose send observations/metrics. Exact metric names and tags depend on the Spring Kafka version and observation configuration.

Add Actuator and an appropriate registry, such as Prometheus:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Configure endpoints and histograms:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        "spring.kafka.listener": true
        "orders.listener.processing": true
        "orders.worker.processing": true
        "orders.event.age": true
```

Do not expose metrics/prometheus endpoints to the public Internet. Restrict access via network policies, authentication, or internal monitoring infrastructure. If using a Spring Kafka version with separate observation settings, enable them per that version's documentation and verify actual metrics at `/actuator/metrics` or `/actuator/prometheus`.

## 8. What Should a Dashboard Display?

A useful dashboard should show both backlog and processing capacity:

| Panel | Metric/visualization | Operational question |
|---|---|---|
| Total lag by group | Sum of lag across partitions | Is the overall backlog growing or shrinking? |
| Max lag by partition | Max lag and top partitions | Is there a hot partition or an individually stuck consumer? |
| Lag trend | Lag over time | Is the consumer catching up after a traffic spike? |
| Records consumed rate | Records/second by group | How many records is the consumer processing? |
| Listener processing p50/p95/p99 | Timer histogram | What are normal processing times and tail latency? |
| Worker/queue metrics | Queue depth, wait time, worker time | Is backlog sitting in Kafka or moved into RAM? |
| Event age p95/p99 | Time from `occurredAt` to completion | How long has the oldest event been waiting? |
| Error/retry/DLT rate | Counters by error type | Is lag growing due to repeated errors or high load? |

Always display partitions alongside group and topic. Total lag can rise during normal producer traffic bursts; if the processing rate stays higher than the incoming rate, the backlog will drain. Conversely, steadily rising lag with a processing rate below the incoming rate indicates insufficient consumer capacity or a downstream bottleneck.

## 9. Designing Actionable Alerts

Do not alert merely because lag exceeds a static number on a single scrape. Combine thresholds, duration, and processing latency:

- **Continuously growing lag:** total lag or partition lag increases over a sustained window while consumer throughput is lower than producer throughput.
- **Hot partition:** one partition has significantly higher lag than the remaining partitions.
- **Slow processing:** listener p95/p99 time breaches SLA over multiple intervals.
- **Event age exceeding SLA:** oldest event or p99 age exceeds the business-acceptable window.
- **Rising retries/DLT:** failure rates rising alongside lag indicate failing records may be stalling consumer progress.
- **Inactive consumer:** assigned partitions have lag while records consumed rate is 0 even though the producer is still publishing.

For example, if the SLA requires events to be processed within 30 seconds, alert when p95 event age exceeds 30 seconds continuously for several minutes. Record-count lag thresholds must be scaled to throughput: 10,000 records might be just a few seconds on a very high-volume stream, yet hours on a low-volume stream.

## 10. Hands-On Lab: Measuring Lag and Processing Time

Run on the `orders.events` topic with consumer group `order-projection`:

1. Send a steady stream of events, such as 100 records/second, containing `eventId`, `orderId`, and `occurredAt`.
2. Record partitions and offsets from `SendResult.getRecordMetadata()`.
3. Create the consumer listener and instrument processing time with a Micrometer Timer.
4. Measure event age from `occurredAt` until listener processing completes.
5. Collect committed offsets and log end offsets to compute per-partition lag.
6. Plot total lag, max lag, listener p95/p99, and event age p95/p99.
7. Increase producer load to 300 records/second and observe the lag trend.
8. Inject simulated latency into `OrderService.apply()` to see processing time and lag change.
9. Restore normal processing speed and measure how long the consumer takes to drain the backlog.
10. Create a hot partition by reusing a single key repeatedly, then compare lag across partitions.

### Example Controlled Delay in a Test Environment

```java
public void apply(OrderEvent event) {
    try {
        Thread.sleep(100);
    }
    catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Processing interrupted", ex);
    }

    repository.save(event);
}
```

Use simulated delays only in test environments or dedicated profiles; never leave `Thread.sleep()` in production processing. Compare throughput before/after and identify when the consumer can no longer keep pace with the producer.

### Results to Record

| Scenario | Producer rate | Consumer rate | Lag trend | Processing p95 | Event age p95 |
|---|---:|---:|---|---:|---:|
| Baseline load | 100 records/s | Measure actual | Measure actual | Measure actual | Measure actual |
| Increased load | 300 records/s | Measure actual | Measure actual | Measure actual | Measure actual |
| Slow worker | 100 records/s | Measure actual | Measure actual | Measure actual | Measure actual |
| Hot partition | 100 records/s | Measure per partition | Measure per partition | Measure actual | Measure actual |

Do not fill in expected numbers as if they were measured. Document the environment, partition count, concurrency, run duration, payload size, and producer/consumer settings so others can reproduce the experiment.

## 11. Reading Results and Finding Bottlenecks

| Observation | Possible cause | Investigation path |
|---|---|---|
| Lag rising, processing p95 rising | Slow listener or downstream | Check DB latency, connection pool, CPU, GC, and service call times. |
| Lag rising, processing time stays low | Producer rate exceeds total capacity or too few consumers/partitions | Compare incoming/consumed rates, partition assignments, and concurrency. |
| Moderate total lag, one partition very high | Key skew or partition-specific failure | Inspect key distribution, failing records, and per-partition consumer assignment. |
| Zero lag, high event age | Timestamp/event age mismeasured or sparse batched arrivals | Check `occurredAt`, clock skew, batch arrival, and timestamp type. |
| Low listener time, high event age | Internal queue or pre-listener wait time is large | Measure queue depth, queue wait, and worker processing separately. |
| Lag spikes sharply after deploy | Rebalance, restart, or rollout | Check rebalance duration, pod restarts, and graceful shutdown. |
| Lag rises alongside retries/DLT | A batch of failing records slows progress | Inspect exceptions, retry backoff, recoverer, and DLT throughput. |

When lag grows, do not blindly increase concurrency. If partition count is insufficient, adding consumers yields no extra parallelism. If the database is already saturated, raising concurrency slows the downstream down further. Pick actions based on evidence from per-partition lag, processing timers, and downstream resource metrics.

## 12. Acceptance Checklist

- Lag is calculated per partition from log end offset and committed offset.
- Groups without committed offsets are handled explicitly; missing data is never treated as zero lag.
- Dashboards display total lag, max lag, and lag trends.
- Processing timers instrument listeners; workers are measured separately if processing is asynchronous.
- Event age uses well-defined timestamps with synchronized clocks.
- Metric tags have bounded cardinality; never use event IDs or business keys as tags.
- p50/p95/p99 or histograms are collected to observe tail latency.
- Alerts combine lag, processing rate, event age, and retry/DLT errors.
- Experiments cover load increases, slow workers, and hot partitions.
- Test reports document exact configurations and measured numbers.

Measuring lag and processing time properly separates Kafka backlog from slow application processing. Per-partition lag shows how far behind the log end a consumer sits; Micrometer Timers measure listener/worker duration; event age shows how late business outcomes arrive. Placing these three signals alongside throughput, retries, and downstream resources lets operations pinpoint bottlenecks and scale the right component instead of adding consumers blindly.
