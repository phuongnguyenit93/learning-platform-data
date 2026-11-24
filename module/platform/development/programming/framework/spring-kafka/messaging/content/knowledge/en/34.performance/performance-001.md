# Measuring Throughput and Latency

The performance of a Spring Kafka application cannot be evaluated solely by the number of records a producer sends successfully or the time a listener takes to process a single message. A messaging flow has multiple stages: the producer serializes and sends the record, the broker acknowledges it, the consumer fetches it, the listener processes it, the side effect completes, and the offset is committed. Each stage has its own throughput and latency.

Measuring accurately requires defining the boundaries of the measurement, using appropriate counters and timers, observing percentiles instead of looking only at averages, and tracking consumer lag. When benchmarking, you must control payload size, partitions, replication, key distribution, concurrency, and load generation rate. Otherwise, a high throughput number may simply reflect a test that is easier than production.

This lesson belongs to the **Performance** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how to measure throughput and latency across the producer, consumer, and entire pipeline, read Kafka/Spring Kafka metrics, and design repeatable benchmarks.

## Learning Outcomes

After this lesson, you will be able to:

- Distinguish between throughput, latency, processing time, and consumer lag.
- Define measurement boundaries at producer acknowledgement, listener processing, and end-to-end.
- Calculate throughput in records/second and bytes/second.
- Measure latency using Micrometer Timer and monotonic time.
- Track p50, p95, and p99 instead of relying only on averages.
- Distinguish successful processing attempts from unique business events.
- Read producer, consumer, broker, and listener container metric groups.
- Understand per-partition lag and the relationship between production rate and consumption rate.
- Design open-loop or closed-loop load tests.
- Analyze the impact of partitions, key distribution, batching, compression, and concurrency.
- Build dashboards and benchmarks with warm-up, steady state, timeouts, and repeatable results.

## 1. Throughput and latency are different metrics

**Throughput** indicates how much work a system completes per unit of time. With Kafka, it is typically measured in records/second or bytes/second.

**Latency** indicates how long a single record takes from a chosen start point to a chosen end point. For example, producer send latency may be the time from calling send until the future completes; consumer processing latency is the time the listener spends processing; end-to-end latency is the time from when the event is generated or published until downstream business processing completes.

| Metric | Question answered | Common units |
|---|---|---|
| Producer throughput | How many records can the producer send? | records/s, bytes/s |
| Producer send latency | How long does it take for the broker to acknowledge send? | ms |
| Consumer throughput | How many records does the listener process successfully? | records/s |
| Listener processing latency | How long does the listener take to process one record? | ms |
| End-to-end latency | How long does an event take from source to final outcome? | ms, s |
| Consumer lag | How many records behind the log end is the consumer? | records, offsets |
| Error/retry rate | How many processing attempts fail or retry? | errors/s, retries/s, % |

High throughput does not guarantee low latency. A system can process 100,000 records/second yet have a p99 latency of several seconds due to large batches or queueing. Conversely, low latency under light load does not prove the system can handle production load.

## 2. Define exact measurement boundaries

Before writing metrics or benchmarks, describe the start and end points.

~~~mermaid
flowchart LR
    A[Event created] --> B[Producer send]
    B --> C[Broker acknowledgement]
    C --> D[Consumer fetch]
    D --> E[Listener processing]
    E --> F[Business side effect]
    F --> G[Offset commit]
~~~

Several time intervals can be measured:

1. **Send latency**: from calling KafkaTemplate.send until CompletableFuture completes.
2. **Broker residence/fetch delay**: from the record timestamp at the broker until the consumer receives it, keeping in mind timestamp type and clock synchronization.
3. **Listener processing time**: from when the listener starts until processing finishes.
4. **Business completion latency**: from receiving the record until the database or business side effect completes.
5. **End-to-end latency**: from the generation/publish timestamp at the source until the final outcome is confirmed.
6. **Commit latency**: time to confirm offsets, depending on AckMode and transactions.

Do not add or compare metrics if they use different boundaries. For example, producer acknowledgement latency is not end-to-end latency because the consumer may not have processed the record yet.

## 3. Measuring throughput in records/second and bytes/second

Over a measurement window of duration T seconds:

\[
Throughput_{records} = \frac{N_{successful\ records}}{T}
\]

\[
Throughput_{bytes} = \frac{B_{successful\ bytes}}{T}
\]

For example, in 60 seconds, if the producer receives acknowledgements for 600,000 records:

\[
600.000 / 60 = 10.000\ records/s
\]

If the total payload is 900 MB in the same window, byte throughput is approximately 15 MB/s. Specify clearly whether you are measuring payload bytes, Kafka record bytes, or network bytes because headers, protocol overhead, compression, and replication make these values differ.

When measuring consumer throughput, count records that the listener processes successfully. If you count every time the listener is invoked, retries can inflate the numbers even though the number of completed business events has not increased.

Track separately:

- Records received.
- Processing attempts.
- Successful processing attempts.
- Failed attempts.
- Unique event IDs completed, if business logic has deduplication.
- Records published to DLT.

These counters answer different questions.

## 4. Measuring latency with percentiles

Latency usually has a skewed distribution: most records are fast, while a few records are slow due to GC, network, retries, database, or a hot partition. Averages can hide tail latency.

| Percentile | Meaning |
|---|---|
| p50 | Half of the records have latency at or below this value. |
| p90 | 90% of records have latency at or below this value. |
| p95 | 95% of records have latency at or below this value. |
| p99 | 99% of records have latency at or below this value. |
| p99.9 | Looks deeper into the tail; requires a sufficiently large sample size. |

For example, p50 = 12 ms, p95 = 80 ms, p99 = 700 ms shows that most records are processed quickly, yet a small group is significantly slower.

When reporting benchmarks, state the percentiles, sample count, measurement duration, and load generation method. A p99 calculated from a few hundred records is not as reliable as a p99 calculated from millions of records.

## 5. Use a monotonic clock to measure intervals within one process

When measuring duration within the same JVM, use a monotonic clock such as System.nanoTime instead of subtracting two Instants or currentTimeMillis. Wall-clock time can be adjusted by NTP or system operations.

Example:

~~~java
long startedAt = System.nanoTime();

orderService.handle(event);

long elapsedNanos = System.nanoTime() - startedAt;
long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

If measuring across two different machines or services, use a wall-clock timestamp inside the event and synchronize clocks between hosts. Clock skew can cause end-to-end latency to become negative or inaccurate.

Also distinguish between when an event is created and when the producer sends it. An event may sit in an application queue before publishing; if the goal is to measure the full business experience, choose the appropriate start timestamp.

## 6. Measuring producer send latency with KafkaTemplate

In modern Spring Kafka, KafkaTemplate.send returns a CompletableFuture. You can measure the time from calling send until the future completes. This result reflects the time the producer waits for the send result according to the acknowledgement configuration.

Example using Micrometer:

~~~java
@Component
public class MeasuredOrderProducer {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;
    private final MeterRegistry registry;
    private final Counter acknowledged;
    private final Counter failed;
    private final Timer sendTimer;

    public MeasuredOrderProducer(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate,
            MeterRegistry registry) {
        this.kafkaTemplate = kafkaTemplate;
        this.registry = registry;

        this.acknowledged = Counter.builder("app.kafka.producer.acknowledged")
                .tag("topic", "orders.created")
                .register(registry);

        this.failed = Counter.builder("app.kafka.producer.failed")
                .tag("topic", "orders.created")
                .register(registry);

        this.sendTimer = Timer.builder("app.kafka.producer.send")
                .tag("topic", "orders.created")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void publish(OrderCreatedEvent event) {
        Timer.Sample sample = Timer.start(registry);

        try {
            kafkaTemplate.send(
                    "orders.created",
                    event.orderId(),
                    event
            ).whenComplete((result, error) -> {
                sample.stop(sendTimer);

                if (error == null) {
                    acknowledged.increment();
                } else {
                    failed.increment();
                }
            });
        } catch (RuntimeException exception) {
            sample.stop(sendTimer);
            failed.increment();
            throw exception;
        }
    }
}
~~~

The Timer measures until the future completes; the acknowledged counter increments only when send succeeds, and failed increments when the future or send call fails. In a real application, handle exceptions and log with a correlation ID without logging sensitive payloads.

This is send acknowledgement latency, not the time the record sits in the broker or the time the consumer takes to process it. If the producer uses acks=0, future completion does not carry the same broker confirmation meaning as acks=1 or acks=all.

## 7. Measuring listener processing latency

To measure business processing time in a listener, wrap the service call with a Timer:

~~~java
@Component
public class MeasuredOrderListener {

    private final OrderService orderService;
    private final MeterRegistry registry;
    private final Timer processingTimer;
    private final Counter processed;
    private final Counter processingFailed;

    public MeasuredOrderListener(
            OrderService orderService,
            MeterRegistry registry) {
        this.orderService = orderService;
        this.registry = registry;

        this.processingTimer = Timer.builder("app.kafka.listener.processing")
                .tag("listener", "orders-created")
                .publishPercentileHistogram()
                .register(registry);

        this.processed = Counter.builder("app.kafka.listener.processed")
                .tag("listener", "orders-created")
                .register(registry);

        this.processingFailed = Counter.builder("app.kafka.listener.failed")
                .tag("listener", "orders-created")
                .register(registry);
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment"
    )
    public void consume(OrderCreatedEvent event) {
        Timer.Sample sample = Timer.start(registry);

        try {
            orderService.handle(event);
            processed.increment();
        } catch (RuntimeException exception) {
            processingFailed.increment();
            throw exception;
        } finally {
            sample.stop(processingTimer);
        }
    }
}
~~~

The Timer includes service processing time and is recorded even when the service throws an exception. The exception is rethrown so the container error handler can retry or recover as configured.

The processed counter in the example counts successful processing attempts, not necessarily unique events. If the listener finishes processing but the offset has not been committed and the record is redelivered, processed can increment again. To measure unique business events, count after idempotency/deduplication confirms the event ID has completed.

## 8. Measuring end-to-end latency

To measure from when an event is created until the consumer finishes, the event can carry an occurrence timestamp:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        Instant occurredAt
) {}
~~~

When the listener completes:

~~~java
Duration endToEnd = Duration.between(
        event.occurredAt(),
        Instant.now()
);

endToEndTimer.record(endToEnd);
~~~

This approach requires clock synchronization between producer and consumer. If the two machines have clock skew, the result can be inaccurate. Additionally, occurredAt may be the business occurrence time rather than the publish time; choose the right definition for your SLA.

You can add a separate publish timestamp if you want to isolate the time an event sits inside the application before sending from Kafka and consumer processing time.

Do not use System.nanoTime on the producer and compare it with System.nanoTime on a consumer in a different process/machine. A monotonic clock is only meaningful within the scope of the same clock source.

## 9. Measuring broker acknowledgement, network, and client metrics

The Kafka client provides metrics for producers and consumers. Exact metric names may vary by Kafka client version and exporter naming conventions, but key groups to monitor include:

| Group | Metric/meaning | What it can detect |
|---|---|---|
| Producer send | Record send rate, send total, error rate | Send rate and produce errors. |
| Producer request | Request latency average/max | Slow broker/network responses. |
| Producer batching | Batch size, records per request, compression rate | Batching and compression effectiveness. |
| Producer buffer | Buffer pool wait time, available buffer bytes | Producer blocked due to buffer exhaustion or slow broker. |
| Consumer fetch | Records consumed rate, fetch latency | Fetch rate and broker wait time. |
| Consumer lag | Records lag max or per-partition lag | Consumer falling behind log end. |
| Consumer commit | Commit latency and commit rate | Cost of offset confirmation. |
| Consumer assignment | Number of assigned partitions | Detect consumers without partitions or skewed assignment. |

You can collect Kafka client metrics via JMX or compatible Micrometer/exporter integrations. Do not rely on a single metric name without verifying the actual client version.

## 10. Consumer lag is not latency

Consumer lag usually represents the distance between the log end offset and the committed offset of a consumer group on each partition. High lag indicates that the consumer is not keeping up with written data, but does not directly tell you how many milliseconds each record has waited.

Example:

| Partition | Log end offset | Committed offset | Approximate lag |
|---|---:|---:|---:|
| 0 | 12.000 | 11.900 | 100 |
| 1 | 8.500 | 8.100 | 400 |
| 2 | 9.200 | 9.150 | 50 |

Total approximate lag is 550 records. Partition 1 is falling behind more than the other partitions; this could be due to key skew, slower data processing, or unbalanced assignment/concurrency.

Lag can grow even when the consumer is still processing records, if the producer creates records faster than the consumer. Lag decreases when the processing rate exceeds the production rate over a period of time.

Do not convert lag into time using a fixed multiplier if the record rate varies over time. To measure record age or time lag, use a well-defined timestamp and synchronized clocks.

## 11. Throughput, latency, and lag must be viewed together

A dashboard with only throughput can hide a growing backlog. A dashboard with only latency can miss that the system lacks capacity to handle the load.

| Observation | Possible interpretation |
|---|---|
| Throughput increases, p99 stable, lag stable | The system is keeping up with load in the measurement window. |
| Throughput plateaus, p99 increases, lag increases | Consumer or broker may have hit a limit. |
| High producer throughput, low consumer throughput | Backlog is accumulating. |
| Low consumer throughput, low CPU, high lag | Possibly waiting on I/O, dependencies, or insufficient partition assignment. |
| Low p50 but high p99 | Tail latency from hot partition, GC, retries, or slow downstream. |
| Retry/DLT rising alongside lag | Business errors or dependency issues are impeding progress. |
| Producer buffer wait increasing | Broker/network or producer batching/throughput has an issue. |

Compare metrics over the same time window and the same topic/group. If a dashboard pulls throughput over 1 minute but latency percentiles over 15 minutes, cross-referencing them can lead to wrong conclusions.

## 12. Designing benchmarks with warm-up and steady state

A benchmark can be divided into three phases:

1. **Warm-up**: start the JVM, establish connections, initialize metadata, load classes, and stabilize the consumer group.
2. **Steady state**: generate steady load long enough to capture meaningful throughput and latency.
3. **Cool-down/drain**: stop load generation and observe the consumer draining the backlog if the goal is to measure catch-up time.

Do not use the first few seconds after application startup as the main result. Warm-up can include JIT compilation, broker connection setup, group join, and cache initialization.

Each benchmark run should record:

- Kafka broker and client/Spring Kafka versions.
- Number of brokers, partitions, and replication factor.
- Producer count and consumer instances/concurrency.
- Payload size and key distribution.
- acks, compression, batch size, and linger.
- Consumer fetch settings, AckMode, and processing logic.
- Warm-up duration and steady-state window.
- Counts/bytes of records sent, succeeded, failed, and sent to DLT.
- p50/p95/p99 and start/end lag.
- CPU, memory, GC, network, and disk utilization.

Run multiple iterations under the same conditions and report the median or range across runs. A single benchmark run is easily skewed by caches, GC, or background activity.

## 13. Open-loop and closed-loop load tests

Two load generation approaches can yield very different results.

**Closed-loop**: the load generator sends the next request only after the previous request completes. When the system slows down, the request generation rate automatically drops. This is suitable for measuring behavior with a fixed number of concurrent clients, but can mask overload.

**Open-loop**: the load generator emits records at a target rate independent of response time. This tests whether the system can sustain the expected arrival rate and shows how backlog grows.

| Criterion | Closed-loop | Open-loop |
|---|---|---|
| Load generation rate | Depends on response | Follows schedule/target rate |
| When system slows down | Load automatically drops | Load keeps arriving |
| Detecting queue growth | Can be harder | Clearer |
| Risk of under-measuring tail latency | Prone to coordinated omission | Less prone if schedule is maintained |
| Best suited for | Fixed concurrent clients | Arrival-rate SLAs, capacity planning |

When using open-loop, the load generator must have enough capacity to emit load and record intended timestamps. If the load generator itself bottlenecks, results do not reflect Kafka.

## 14. Avoiding coordinated omission

Coordinated omission occurs when a load generator sends a new request only after the previous request completes. When the system slows down, the load generator sends fewer requests, so periods when the system is overloaded are underrepresented in the latency histogram.

To reduce this effect:

- Use an open-loop generator for arrival-rate benchmarks.
- Record both the intended send time and the actual send time.
- Calculate latency from the intended send time if the goal is to measure experience against the send schedule.
- Report both offered load and achieved throughput.
- Verify the load generator is not CPU- or network-bound.

If offered load is 20,000 records/s but achieved throughput is only 12,000 records/s, the system is accumulating backlog or the generator cannot reach the target configuration. Do not report only achieved throughput while ignoring the requested load.

## 15. Partition count and key distribution affect throughput

Kafka parallelizes primarily through partitions. A consumer group can distribute partitions across multiple consumer members; at any given time, one partition is assigned to only one consumer in the group under the standard group model.

If a topic has 4 partitions but the consumer group has 12 consumers, at most 4 consumers hold partitions from that topic at a time. Increasing concurrency beyond the partition count does not automatically increase throughput.

Key distribution also matters. If all records share the same key, they typically route to the same partition and create a hot partition. Then the single consumer handling the hot partition becomes the bottleneck while other consumers sit idle.

Benchmarks should test:
- Uniformly distributed keys.
- A few high-volume keys.
- A single key.
- No keys or custom partition assignment.

Do not increase partitions solely to add more consumers if per-key ordering is a business requirement. Increasing partitions can change key-to-partition mapping and affect ordering when old and new data coexist.

## 16. Batching, compression, and payload size

Producers can group multiple records into a batch before sending. Settings like batch size and linger time affect the trade-off between throughput and latency.

- Larger batches can improve network efficiency and reduce request overhead.
- Higher linger gives the producer more time to accumulate batches, often improving throughput while increasing send latency.
- Compression reduces transmitted and stored bytes, at the cost of CPU.
- Larger payloads increase network, serialization, broker I/O, and consumer deserialization costs.

Consumers also have fetch settings affecting how much data is pulled per request. Do not tune the producer in isolation while ignoring the consumer or broker.

Benchmarks should test multiple payload sizes representative of production—such as small, medium, and large—while recording whether payloads are compressed and which serializer is used. Unrealistically small synthetic data can make throughput look many times higher than in reality.

## 17. Concurrency and listener processing time

Increasing consumer concurrency can boost processing capacity if there are enough partitions and downstream dependencies can handle the load. However, higher concurrency also increases threads, connections, context switching, and load on databases/downstream services.

Measure:
- Records/s per partition.
- Processing time p50/p95/p99.
- Consumer lag per partition.
- Number of consumers assigned partitions.
- CPU, heap, GC, and thread utilization.
- Database connection pool wait time.
- Retry and error rate.

If a listener is constrained by a database connection pool, increasing concurrency may only increase the number of threads waiting for connections. If a listener makes slow HTTP calls, throughput depends on the connection pool and downstream timeouts.

Do not offload work asynchronously to an executor and commit offsets before the work finishes unless you have an appropriate offset/ordering design. That can make listener metrics look fast while actual business work is not yet complete.

## 18. Micrometer and Spring Kafka observation

Spring Kafka can integrate with Micrometer to observe KafkaTemplate and listener containers in supported versions. Built-in observations/timers capture framework-managed intervals; custom Timers remain useful for measuring business logic specifically.

When enabling instrumentation:
- Check which properties/observation APIs your Spring Kafka and Boot versions support.
- Do not override framework metrics with custom metrics of the same name.
- Use low-cardinality tags such as listener, topic from a fixed list, and outcome.
- Never use eventId, orderId, customerId, or key as metric tags.
- Keep trace IDs in log/trace context rather than metric labels.

Custom metrics should answer specific operational questions. Too many duplicate timers/counters clutter dashboards and increase telemetry costs.

## 19. Prometheus examples for throughput and latency

If Micrometer exports counters/timers following Prometheus naming conventions, you can query rates and histograms. Exact names depend on the registry and metric configuration.

Example query patterns:

~~~promql
rate(app_kafka_producer_acknowledged_total[1m])
~~~

The rate of records acknowledged by the broker for the producer over a 1-minute window.

~~~promql
rate(app_kafka_listener_processed_total[1m])
~~~

The rate of records successfully processed by the listener according to the application counter. Remember that this counter counts successful processing attempts and can increment again when a record is redelivered.

For histograms:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (rate(app_kafka_listener_processing_seconds_bucket[5m]))
)
~~~

Illustrative query for p99 listener processing latency. Verify actual metric/bucket names in Prometheus before adding them to dashboards.

Dashboards should be organized by fixed topic/listener and display:
- Producer acknowledged rate and failed rate.
- Consumer processed rate and processing error rate.
- Listener p50/p95/p99.
- Producer send p50/p95/p99.
- Consumer lag per partition.
- Retry, DLT, and transaction abort rate.
- CPU, heap, GC, network, and broker disk.

## 20. Bottleneck analysis by symptom

| Observed symptom | Possible areas to inspect |
|---|---|
| Producer send latency rises, buffer wait rises | Slow broker/network, full buffer, unsuitable batch or compression settings. |
| Low producer throughput, high CPU | Serialization/compression or producer app is CPU-bound. |
| Low consumer fetch rate, lag rising | Assignment, fetch settings, broker/network, or too few partitions. |
| High listener processing p99 | Database/HTTP, lock contention, GC, or heavy payload processing. |
| One partition has much higher lag | Hot key, key skew, or slower data processing in that partition. |
| Consumer lag grows despite low listener timer | Possibly queue wait before listener, commits, rebalances, or processing metric excludes queue wait. |
| Rising DLT/retries | Failing dependencies or bad data reducing effective throughput. |
| Low CPU but high latency | Waiting on I/O, exhausted pools, locks, or broker/network. |
| High CPU and GC, rising p99 | Heap pressure, allocations, or large batches/payloads. |

Do not conclude a bottleneck from a single metric. Cross-check client, broker, application, downstream, and lag over the same time window.

## 21. Capstone exercise: benchmarking the OrderCreated pipeline

Build a producer → `orders.created` topic → Fulfillment consumer pipeline. The goal is to determine the maximum throughput at which p99 listener latency remains within the SLA.

Requirements:

1. Create counters for producer acknowledged/failed.
2. Measure producer send latency using a Timer around the KafkaTemplate future.
3. Create consumer success/failure counters and a Timer for listener processing.
4. Add an event timestamp to measure end-to-end latency with synchronized clocks.
5. Collect producer/consumer client metrics and per-partition consumer lag.
6. Create the topic with multiple partitions and a documented replication factor.
7. Test small, medium, and large payloads.
8. Test uniformly distributed keys and skewed keys to detect hot partitions.
9. Compare levels of producer concurrency, consumer concurrency, and partition count.
10. Test batch/linger/compression one change at a time, changing only one group of variables per run.
11. Run warm-up followed by a steady state long enough for meaningful percentiles.
12. Test open-loop at multiple offered rates and record achieved throughput.
13. Track start/end lag, retries, DLT, CPU, heap, GC, network, and disk.
14. Report records/s, bytes/s, p50/p95/p99, error rate, and lag.
15. Repeat the benchmark multiple times and record the full configuration for reproducibility.
16. Identify the load level that meets the SLA along with headroom before saturation.

The exercise is complete when you identify the primary bottleneck, explain why throughput or p99 changed, and propose changes backed by measurement data.

## 22. Learning path and completion criteria

| Stage | Core focus | Self-check criteria |
|---|---|---|
| 1. Metric model | Throughput, latency, lag | Can distinguish each metric and its units. |
| 2. Boundaries | Producer, broker, listener, end-to-end | Can state exact start/end points of each measurement. |
| 3. Throughput | Records/s and bytes/s | Can calculate rate from counter delta and time window. |
| 4. Latency | Timer, p50/p95/p99 | Can interpret tail latency and sample count. |
| 5. Instrumentation | Micrometer and Kafka client metrics | Collects metrics with low-cardinality tags. |
| 6. Consumer lag | Per-partition offsets | Detects hot partitions and growing backlog. |
| 7. Load model | Open-loop/closed-loop | Understands offered load, achieved throughput, and coordinated omission. |
| 8. Tuning variables | Partitions, keys, batch, compression, concurrency | Designs controlled single-variable benchmarks. |
| 9. Diagnosis | App, broker, network, downstream | Uses multiple metrics to pinpoint bottlenecks. |
| 10. Capacity | SLA, headroom, and repeatability | Reports reproducible load levels meeting SLA. |

This lesson is complete when you can measure throughput and latency at the right boundaries, track percentiles and consumer lag, and design benchmarks with clear warm-up, steady state, and offered load. You should also be able to explain the impact of partitions, key distribution, batching, compression, concurrency, and downstream dependencies.

Throughput tells you how much the system processes; latency tells you how long a record has to wait; lag tells you how far behind the consumer is. Only by looking at all three metric groups alongside error/retry rates and broker/application resources can you evaluate the real capacity of a Spring Kafka pipeline.

