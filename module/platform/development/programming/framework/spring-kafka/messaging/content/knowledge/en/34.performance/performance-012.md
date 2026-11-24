# Benchmarking Under Realistic Load

A Kafka benchmark is meaningful when the test workload closely resembles what the system will face in production. A test that simply blasts 1 KB records continuously into a broker can reveal producer/broker limits for one specific setup, yet fails to prove a Spring Kafka application can handle orders, payments, or real-payload events within required latency and reliability bounds.

A realistic benchmark must measure the entire path: creating events, serializing, sending via `KafkaTemplate`, broker ingestion and replication, consumer polling, deserializing, listener processing, calling dependencies, and completing side effects. Simultaneously observe throughput, p95/p99 latency, consumer lag, errors, resources, and data correctness. The goal is not finding the highest possible records/second figure under ideal conditions; the goal is identifying the load the system can sustain while meeting agreed SLOs.

## 1. Why benchmark under realistic load?

A benchmark result is only valid within the environment and workload used to measure it. If payload shape, key distribution, replication factor, acknowledgements, consumer concurrency, or dependencies differ from production, results can lead to wrong sizing decisions.

For example, two producers both send 20,000 records/second yet generate vastly different loads:

| Characteristic | Workload A | Workload B |
|---|---|---|
| Payload | Fixed 100-byte string | JSON event averaging 3 KB with nested objects |
| Keys | Uniformly distributed | 20% of keys account for 80% of traffic |
| Compression | None | LZ4 |
| Acknowledgement | `acks=1` | `acks=all`, replication factor 3 |
| Consumer | Polls and discards records | Deserializes, queries database, and updates projection |
| Measured outcome | Broker accepts record | Business event completed |

You cannot conclude both workloads have the same processing capacity simply because records/second match. A benchmark must state clearly which layer it measures and which business steps are included.

## 2. Define targets and SLOs before running

Before changing settings, write down quantitative targets. Illustrative example:

| Metric | Example target |
|---|---:|
| Normal throughput | 8,000 events/s |
| 5-minute peak | 15,000 events/s |
| End-to-end latency p95 | Under 250 ms |
| End-to-end latency p99 | Under 700 ms |
| Consumer lag at steady load | Does not grow continuously |
| Publish error rate | Under 0.01% |
| Lost event rate | 0 in audit verification |
| Recovery after broker restart | Returns to SLO within 2 minutes |

These numbers merely illustrate how to state targets; each system must choose SLOs based on business and infrastructure reality. Specify the measurement window, percentiles, topic/partition scope, and error calculation. Never rely on a single aggregate throughput target while ignoring latency or lag.

Distinguish three target categories:

- **Capacity target:** load the system must serve under normal and peak conditions.
- **Performance SLO:** latency, error rate, and lag to maintain at that load.
- **Resilience target:** how the system must recover when brokers, consumers, databases, or networks fail.

A configuration passes only when it satisfies all critical targets together, not merely peak throughput.

## 3. Model the workload before generating load

A workload model is a reproducible description of real traffic. At minimum, document:

| Attribute | Question to answer |
|---|---|
| Arrival rate | What are the average, peak, and burst events/second? |
| Payload size | What are the p50, p95, p99, and maximum sizes in bytes? |
| Payload shape | Simple JSON, nested objects, binary, Avro/Protobuf, or multiple event types? |
| Key distribution | Are keys uniform or are there hot keys/large tenants? |
| Topic topology | How many topics, partitions, and replication factors? |
| Consumer groups | How many groups read the same topic? |
| Processing cost | Does the listener only validate, or call databases, HTTP, caches, or multiple services? |
| Ordering | Is ordering required per key or per partition? |
| Reliability | Which `acks`, idempotence, transactions, and retry policies are enabled? |
| Retention | How long is data retained and what storage volume does the write rate create? |
| Failure profile | Does the workload include dependency errors, retries, DLT, or rebalances? |

Do not use only the average payload size. Large payloads at p99 can inflate batch sizes, network throughput, serialization time, and memory pressure. Likewise, flat average traffic does not simulate bursts during market open, campaigns, or batch imports.

## 4. Calculate record load and byte load

Throughput by record count and by byte volume answer two different questions. With an average of `R` records/second and average payload size `S` bytes, approximate payload rate is:

\[
\text{Payload bytes/s} = R \times S
\]

For example, 10,000 records/s with 2,048-byte payloads equals roughly 20.48 MB/s of payload before counting protocol overhead, batch framing, compression, and replication traffic.

When sizing a cluster, also factor in:

- Actual batch sizes and compression ratios.
- Replication factor and inter-broker traffic.
- Number of consumer groups reading the same data.
- Fetch traffic from brokers to each consumer group.
- Retention and log growth rate.
- Cross-zone/cross-rack traffic if the cluster spans multiple zones.

Do not simply multiply payload bytes/s by the replication factor and treat that as exact network usage. That is only a rough initial estimate; replication, compression, batching, fetches, and placement all change actual byte traffic.

## 5. Key distribution and hot partitions

Producers often use keys so related events land in the same partition. This preserves per-key ordering, yet uneven key distribution can create hot partitions.

For example, 12 partitions can average 1,000 records/s per partition if evenly distributed. If one large tenant generates 50% of traffic and its key always maps to one partition, that partition receives nearly half of all traffic while others stay underutilized.

Benchmarks should preserve production-like key distribution:

- Number of distinct keys and frequency distribution across keys.
- Share of the hottest key and top 10 keys.
- Null keys or keyless records if the system uses them.
- Partitioning strategy and partition count.
- Shifts in key distribution when partition count increases.

Do not observe only total throughput. Inspect per-partition lag, bytes, and records to spot a saturated partition even when overall cluster resources look idle.

## 6. Define metrics precisely

### Throughput

Measure separately:

1. **Generated rate:** events created per second by the load generator.
2. **Producer accepted rate:** records confirmed successfully by the producer.
3. **Broker ingress rate:** records/bytes accepted into the topic by brokers.
4. **Consumer delivery rate:** records polled and dispatched to listeners by consumers.
5. **Business completion rate:** events completing business side effects.

These rates can diverge. If the producer generates 10,000 events/s while listeners complete only 8,000 events/s, lag will grow even though producer sends succeed.

### Latency

Measure latency at clear boundaries:

| Latency | Start/end points | Meaning |
|---|---|---|
| Producer enqueue | Calling `send()` until method returns | Time for the app to place the record into the producer buffer; not broker ack |
| Producer ack | Calling `send()` until callback/future completes | Serialization, buffer wait, network, broker, and acknowledgement time |
| Broker request | Broker receives request until response | Broker-side request processing cost |
| Consumer fetch | Fetch sent until response arrives | Fetch and data-wait duration |
| Listener duration | Listener starts until method finishes | Processing cost inside the consumer application |
| End-to-end | Event created until side effect completes | Actual business experience |

Average latency is insufficient for evaluation. Always examine p50, p95, p99, and max; p99 can degrade sharply as thread pools, connection pools, or broker queues approach saturation.

### Consumer lag

Record-based consumer lag is typically computed as log end offset minus the consumer's current position or committed offset, depending on the tool. Always specify which offset type is used. Record lag alone does not directly tell how long events have waited; a lag of 5,000 tiny fast-to-process records differs completely from 5,000 records stuck behind a hot partition.

Complement with event age or time lag: time from event creation/append until consumer completion. Monitor lag per partition and per group, not just total topic lag.

## 7. Measuring end-to-end latency accurately

To measure from producer creation to business completion, test events should include a unique `eventId` and creation timestamp. Consumers record timestamps at start and at side-effect completion.

```java
public record BenchmarkEvent(
        String eventId,
        String customerId,
        Instant createdAt,
        String payload) {
}
```

The listener can record:

```java
@KafkaListener(topics = "benchmark.orders", groupId = "benchmark-reader")
public void consume(BenchmarkEvent event) {
    Instant listenerStartedAt = Instant.now();
    orderProjection.apply(event);
    Instant completedAt = Instant.now();

    benchmarkMetrics.recordEndToEnd(
            Duration.between(event.createdAt(), completedAt));
    benchmarkMetrics.recordProcessing(
            Duration.between(listenerStartedAt, completedAt));
}
```

This is an illustrative example; in distributed benchmarks, producer and consumer clocks must be synchronized (NTP/chrony) with clock skew smaller than the desired latency precision. If clock skew is large, subtracting timestamps across two machines can produce negative or distorted results. You can also use distributed tracing or timestamps captured by the same process at appropriate boundaries.

`listener duration` excludes time records sit in the broker or wait for polling. Only `end-to-end latency` covers the full path from event creation to business completion. Never substitute one metric for the other.

## 8. Distinguishing closed-loop and open-loop load

Load generators can produce load in two ways:

- **Closed-loop:** sends the next request only after the previous request finishes. When the system slows down, the generator slows itself down. This easily introduces coordinated omission: the generator emits fewer requests while the system is slow, making measured latency look better than reality.
- **Open-loop:** emits events on a fixed schedule/rate independent of prior response times. When the system cannot keep up, queues/in-flight work grow and latency reflects real pressure.

For production workloads whose arrival rate is independent of processing speed, open-loop models reality more closely. However, cap in-flight work and define a policy when the generator falls behind; if the load generator itself saturates, the benchmark stops measuring the target system cleanly.

If using closed-loop, state concurrency and latency calculation method explicitly. If using open-loop, report target rate, actual generated rate, dropped/delayed events, and generator utilization.

## 9. Separating broker benchmarks from application benchmarks

Run at least two types of benchmarks:

| Type | Tooling | What it answers |
|---|---|---|
| Broker/client baseline | `kafka-producer-perf-test`, `kafka-consumer-perf-test` | What throughput/latency do the cluster and Kafka client achieve at baseline configs? |
| Application end-to-end | Load generator driving the real Spring Kafka app | How much can the full serialization, listener, database, and business logic sustain? |

Kafka performance tools are useful for quick baselines, yet their payloads are typically simple and omit application logic. If the broker perf test is slow, investigate the cluster/client first. If the broker baseline is strong while the application is slow, focus on serializers, listeners, downstream services, thread pools, and connection pools.

## 10. Using the Kafka producer performance tool

Kafka ships `kafka-producer-perf-test` to measure producer throughput with configurable record sizes and send rates. Example for CLI versions using `--producer-props`:

```bash
bin/kafka-producer-perf-test.sh \
  --topic benchmark.orders \
  --num-records 1000000 \
  --record-size 2048 \
  --throughput 10000 \
  --producer-props \
    bootstrap.servers=localhost:9092 \
    acks=all \
    compression.type=lz4
```

This illustrative command sends one million 2 KB records targeting roughly 10,000 records/s. Check `--help` on your exact Kafka distribution. CLI flags evolve across versions; newer releases add `--bootstrap-server`, `--reporting-interval`, and `--command-property`, while some older flags are deprecated. Never copy commands across major versions without checking.

Producer perf tool output typically reports record/byte rates, send latency, and client stats. It does not measure listener processing or database side effects. Use it for producer/broker baselines, never as sole proof of end-to-end SLOs.

## 11. Using the Kafka consumer performance tool

`kafka-consumer-perf-test` measures how fast a consumer reads data from a topic. Illustrative example for CLI versions using `--messages`:

```bash
bin/kafka-consumer-perf-test.sh \
  --bootstrap-server localhost:9092 \
  --topic benchmark.orders \
  --messages 1000000 \
  --group benchmark-reader
```

Some newer versions replace `--messages` with `--num-records`; check `--help` on the binary you run. You can pass consumer properties/config files to mirror application fetch settings and security.

Consumer perf tests focus on reading records and skip Spring listener business logic. A consumer that merely polls and discards records can show dramatically higher throughput than an application that deserializes JSON, validates, writes to a database, and commits offsets.

## 12. Benchmarking the real Spring Kafka application

An end-to-end benchmark should run the actual application artifact or a harness using identical producer/consumer configurations and business paths. The load generator should emit realistic payloads, keys, and headers matching production.

A typical test architecture:

```text
Load generator
   |
   | event + key + eventId + createdAt
   v
Spring Kafka producer / KafkaTemplate
   |
   v
Kafka cluster (topic, partitions, replicas)
   |
   v
Spring @KafkaListener
   |
   +--> deserialize / validate
   |
   +--> service / database / HTTP dependency
   |
   v
Business completion + metrics/traces
```

Keep serializers/deserializers, listener factories, error handlers, acknowledgment modes, database schemas, and dependencies aligned with production. If using a mock database or skipping validation, state that explicitly because results then reflect only the retained subset.

## 13. Load generator using KafkaTemplate

In Spring Kafka 3.x, `KafkaTemplate.send()` returns a `CompletableFuture`. You can use a semaphore to bound in-flight sends and record producer acknowledgement latency:

```java
Semaphore inFlight = new Semaphore(5_000);
LongAdder succeeded = new LongAdder();
LongAdder failed = new LongAdder();

for (long i = 0; i < totalRecords; i++) {
    inFlight.acquire();
    long startedAt = System.nanoTime();
    BenchmarkEvent event = createEvent(i);

    kafkaTemplate.send("benchmark.orders", event.customerId(), event)
            .whenComplete((result, error) -> {
                try {
                    if (error == null) {
                        succeeded.increment();
                        producerAckTimer.record(
                                System.nanoTime() - startedAt,
                                TimeUnit.NANOSECONDS);
                    } else {
                        failed.increment();
                    }
                } finally {
                    inFlight.release();
                }
            });
}

inFlight.acquire(5_000);
inFlight.release(5_000);
```

This is an illustrative skeleton for bounding in-flight sends; production-grade benchmark code must handle interruptions, shutdown, synchronous exceptions from `send()`, timeouts, and callback errors. This loop generates load paced by producer completion (concurrency-bounded closed-loop), not a fixed arrival rate. If open-loop is needed, add a rate limiter or scheduler emitting events on schedule and track events delayed past their scheduled send time.

Never call `future.get()` immediately after every `send()` in a high-load loop if your goal is measuring producer throughput; doing so turns the benchmark into sequential sending with effective concurrency near one. Conversely, never fire unbounded futures without an in-flight cap, as that can exhaust heap and benchmark generator stability rather than Kafka.

With Spring Kafka 2.x, `send` may return `ListenableFuture`; adapt callbacks to your project's version. Keep the exact same version across comparison runs.

## 14. Simulating production-like payloads and keys

The load generator should reproduce data characteristics instead of repeating one constant string:

- Generate JSON matching real size distributions, e.g., p50 800 bytes, p95 4 KB, p99 12 KB.
- Generate keys matching real tenant/customer/order distributions.
- Mix event types at realistic frequencies.
- Include trace/correlation headers if the application uses them.
- Keep ratios of optional fields, arrays, and nested objects close to production.
- Include payloads near `max.request.size` or `max.message.bytes` if the system handles large events.

These sizes are illustrative examples. Derive distributions from anonymized production data or production statistics; never use real personal/sensitive data as benchmark payloads without proper safeguards.

Repeating an identical payload can artificially inflate compression ratios and misrepresent real events. Conversely, purely random payloads can be harder to compress than production data. Simulate both entropy and payload structure.

## 15. Designing load test scenarios

Do not run only a single steady test at one RPS level. Use multiple scenarios to understand system behavior:

| Scenario | How to run | Goal |
|---|---|---|
| Baseline | Low, steady load | Establish baseline latency/throughput |
| Ramp-up | Step up RPS incrementally | Find where saturation begins |
| Steady-state | Hold target load long enough | Verify SLOs and stable lag |
| Burst | Sudden spike to peak | Evaluate buffers, backlog, and recovery |
| Soak | Run steady load for several hours | Detect memory leaks, GC, and resource drift |
| Spike recovery | Stop burst, return to normal load | Measure backlog drain time |
| Failure | Restart broker/consumer or slow dependencies | Verify resilience and recovery |
| Hot-key | Concentrate traffic on a few keys | Detect hot partitions and ordering limits |
| Large payload | Increase ratio of large payloads | Measure serialization, network, memory, and batch behavior |
| Retry/DLT | Inject a controlled error rate | Measure retry amplification and DLT load |

Steady-state runs must be long enough to exclude warm-up effects and observe lag trends. Soak tests must exceed GC cycles, cache warm-ups, and periodic background tasks that can affect the application.

## 16. Warm-up and measurement windows

The JVM needs warm-up time for class loading, JIT compilation, connection pools, metadata caches, and producer buffers. Never use the first few seconds as representative results.

A run can be structured as:

1. **Startup:** create topics/consumer groups, start apps, and await assignments.
2. **Warm-up:** send ramping load until JIT and caches stabilize.
3. **Measurement:** hold target rate and collect metrics over a fixed window.
4. **Drain:** reduce or stop producers and wait for consumers to clear backlog.
5. **Verification:** verify event counts, duplicates, missing events, and errors.

For example, an experiment might warm up for 2–5 minutes, measure steady state for 10–20 minutes, and repeat at least three times. Actual durations depend on workload and environment cost; do not treat these intervals as rigid standards.

Never merge warm-up, measurement, and drain into one average figure. Latency during drain differs from steady state and will skew results.

## 17. Controlling environment variables

To compare two configurations, change only the variable under study. Record:

- Kafka broker, Spring Kafka, Kafka client, and JVM versions.
- Broker count, CPU/RAM/disk/network, and storage class.
- Topic partition count, replication factor, `min.insync.replicas`, retention.
- Producer/consumer properties and serializers/deserializers.
- Application instance count, listener concurrency, and CPU/memory limits.
- Database version, connection pool, indexes, dataset size, and network latency.
- Load generator host, CPU, memory, network, and thread count.
- Run timestamp, workload seed, target rate, and duration.
- Background jobs, compaction, backups, or other workloads on the cluster.

Never run comparative benchmarks on a cluster with uncontrolled background traffic. If a dedicated environment is unavailable, record background load and treat results as relative observations rather than reproducible capacity benchmarks.

## 18. Producer settings to include in the test matrix

Producer configurations affecting latency, batching, network, and durability:

| Configuration | Effect to observe |
|---|---|
| `acks` | Acknowledgement level and replica wait time |
| `enable.idempotence` | Prevents producer retry duplicates; has compatibility constraints with `acks`, retries, and in-flight requests |
| `batch.size` | Larger batches can boost throughput/compression, using more buffer and waiting for data |
| `linger.ms` | Extra wait to fill batches; can raise latency at low traffic |
| `compression.type` | Reduces wire/storage bytes in exchange for compression/decompression CPU |
| `buffer.memory` | Producer buffer capacity; when full, `send()` may block up to `max.block.ms` |
| `max.in.flight.requests.per.connection` | Increases request pipelining; keep compatible with idempotence and ordering |
| `delivery.timeout.ms` | Caps total time for the producer to report success/failure |

Producer idempotence requires compatible settings; in current Kafka documentation, `acks=all`, `retries` > 0, and `max.in.flight.requests.per.connection` <= 5 are key requirements. With conflicting configs, the producer may reject the config or disable idempotence depending on property setup and version. See [Apache Kafka Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs).

Example starting profile for a test matrix (not a universal optimal preset):

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[compression.type]": lz4
        "[batch.size]": 65536
        "[linger.ms]": 5
        "[buffer.memory]": 67108864
```

Run a baseline with current production settings first. Then change one factor at a time—for instance comparing `none`, `lz4`, and `zstd` compression; varying batch sizes; or varying `linger.ms`. Record producer CPU, broker network, and p99 latency. Compression can cut network bytes while raising CPU; the right choice depends on payloads and hardware.

## 19. Consumer and listener settings to test

| Configuration | Potential impact |
|---|---|
| Listener `concurrency` | Consumer thread count; helpful up to partition and downstream limits |
| `max.poll.records` | Maximum records returned per poll; larger batches can boost throughput yet lengthen processing |
| `fetch.min.bytes` | Waits for enough data before returning fetch; raising can improve throughput yet add latency |
| `fetch.max.wait.ms` | Maximum time broker waits to satisfy `fetch.min.bytes` |
| `max.partition.fetch.bytes` | Maximum fetch data size per partition per request |
| `max.poll.interval.ms` | Maximum gap between polls before consumer is considered stalled |
| Ack mode | Affects commit cadence, duplicate window, and overhead |
| Batch listener | Can reduce invocation overhead, but alters error and commit semantics |

Do not raise `max.poll.records` when per-record listener processing is slow without reviewing `max.poll.interval.ms`, memory, and retry behavior. If consumers fail to poll in time, groups can rebalance and add latency.

Concurrency must match partition counts. For a group reading 12 partitions, setting concurrency to 30 does not create 30 active reading threads; extra consumers sit idle. Raising concurrency also does not help if the database connection pool only permits a few connections or downstream is saturated.

## 20. Distinguishing producer throughput from consumer throughput

Consumers can read faster than producers briefly when draining a backlog. Consequently, measuring consumer throughput on a pre-populated topic can yield higher numbers than steady-state pipeline throughput.

Measure both cases:

- **Drain test:** pre-load records and measure how fast consumers drain them. This measures backlog recovery capacity.
- **Steady-state pipeline:** producers and consumers run concurrently at a steady arrival rate. This measures sustainable workload capacity.

If consumer drain hits 50,000 records/s while steady-state pipeline hits only 12,000 records/s, there is no contradiction. Producers, replication, payload generation, or downstream systems may be the pipeline bottleneck.

## 21. Consumer lag and backlog drain time

When producer rate exceeds consumer rate, lag grows. Let:

- \(\lambda\): arrival rate entering the partition or system (records/s).
- \(\mu\): consumer completion rate (records/s).
- \(L\): current backlog (records).

If \(\mu > \lambda\), backlog shrinks at a net rate near \(\mu - \lambda\). Estimated drain time:

\[
T_{drain} \approx \frac{L}{\mu - \lambda}
\]

For example, backlog is 120,000 records while the producer continues sending 4,000 records/s and consumers complete 10,000 records/s. Net drain rate is ~6,000 records/s; estimated drain takes roughly 20 seconds if rates stay steady.

If \(\mu \leq \lambda\), backlog will not shrink on its own while the producer keeps sending. Increase consumer capacity, reduce arrival rate, or investigate bottlenecks. This formula is only an aggregate estimate; hot partitions, retries, rebalances, and uneven payload sizes can lengthen actual drain time.

## 22. Using Little's Law to understand concurrency and queues

Little's Law relates work inside a system, throughput, and residence time:

\[
N = \lambda \times W
\]

Where \(N\) is average in-flight work items, \(\lambda\) is average throughput, and \(W\) is average time in the system.

For example, if listeners complete 2,000 events/s and each event takes 50 ms on average, average items in flight/waiting within that scope are roughly:

\[
N = 2,000 \times 0.05 = 100
\]

This relationship helps estimate required concurrency, yet does not mean spinning up 100 threads guarantees 2,000 events/s. CPU, database pools, partition assignments, and downstream services can cap capacity. Use the formula as a reasoning tool, then verify via benchmarks.

## 23. Monitoring Spring Kafka metrics with Micrometer

Spring Kafka can create timers for listeners and `KafkaTemplate` when Micrometer is on the classpath and the application context has a suitable `MeterRegistry`. Since Spring Kafka 2.3, the listener timer is named `spring.kafka.listener`; since 2.5, the template send timer is named `spring.kafka.template`. You can attach static tags or record-based tag providers, while avoiding high-cardinality tags such as order ID or customer ID. See [Spring Kafka Micrometer Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html).

Since Spring Kafka 3.0, Micrometer Observation can be enabled on `KafkaTemplate` and `ContainerProperties`; when observation is enabled, corresponding Micrometer timers are managed through observation. Batch listeners have version- and config-specific limitations. See [Spring Kafka Micrometer Observation](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html).

Java configuration example:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    factory.getContainerProperties().setObservationEnabled(true);
    return factory;
}

@Bean
KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
```

APIs and auto-configuration may vary across Spring Kafka/Spring Boot versions. If the app already uses Boot auto-configured `KafkaTemplate` or listener factories, customize existing beans rather than creating redundant duplicate beans.

## 24. Broker and consumer metrics to watch

Alongside Spring metrics, monitor Kafka clients and brokers:

| Component | Metrics/observations | Signs to investigate |
|---|---|---|
| Producer | Record/byte rate, request latency, batch size, buffer availability, retries/errors | Rising producer send latency, exhausted buffers, rising retries/errors |
| Consumer | Records consumed rate, byte rate, fetch latency, records lag/max, fetch throttle | Rising lag, falling fetch rate, or increasing throttling |
| Broker | Bytes in/out, Produce/Fetch request latency, request queue time | Rising request queue/local/remote times |
| Replica | Under-replicated partitions, ISR shrink/expand, offline log directories | Durability and replication impacted |
| Network | Throughput, retransmits, connection count, network processor idle | Network saturation or connection churn |
| JVM | Heap, allocation rate, GC pauses, CPU | Rising GC/CPU alongside latency |
| Storage | Disk throughput, latency, utilization, page cache | Broker I/O becoming the bottleneck |

Apache Kafka exposes many broker/client metrics via JMX, including request timing, consumer records lag, under-replicated partitions, and network/request handler idle ratios. Metric names can vary by Kafka version; consult the metric catalog for your deployed version. See [Apache Kafka Monitoring](https://kafka.apache.org/documentation/#monitoring).

## 25. Monitoring downstream and JVM

In a Spring listener, Kafka may fetch quickly while the listener runs slowly due to a database or HTTP service. Therefore, benchmarks must also collect:

- Process/container CPU and CPU throttling.
- Heap, allocation rate, GC pauses, and full GC counts.
- Thread counts, thread pool queue depth, and rejected tasks.
- Database connection pool active/idle/pending counts, query latency, and lock waits.
- HTTP client connection pools, timeouts, retries, and remote latency.
- Cache hit ratios and cache access times.
- Serialization/deserialization duration.
- Listener processing duration and exception rates.

Looking only at Kafka consumer lag can mislead you into raising consumer concurrency when the database connection pool is the real limit. Adding consumers can overload the database further.

## 26. Finding the saturation point

The saturation point is the load level beyond which adding input no longer yields proportional gains in business completion throughput, while latency, lag, or errors begin climbing rapidly.

An illustrative curve:

```text
Throughput
  ^
  |                         ________ capacity plateau
  |                    ____/
  |                ___/
  |            ___/
  |        ___/
  |_______/________________________________> Offered load
              ^
          saturation

Latency/lag typically rises sharply around and after the saturation point.
```

Never pick the point right next to the plateau as the operating target if workloads experience bursts. Maintain headroom for peaks, rebalances, broker maintenance, and downstream variance. Headroom should reflect traffic volatility and SLOs, not a fixed percentage applied blindly to every system.

## 27. Diagnosing bottlenecks by symptom

| Symptom | Possible bottleneck location | Next checks |
|---|---|---|
| Producer ack latency rises, broker CPU/network high | Broker, replication, network, or request queue | Produce request timing, broker disk/network, ISR |
| Producer ack latency rises, broker idle | Producer serialization, buffer, DNS/TLS, or generator | Client CPU, buffer wait, serializer duration |
| Good broker ingress yet consumer lag rises | Consumer/listener or downstream | Listener timer, consumer CPU, poll rate, DB pool |
| One partition has much higher lag | Hot key or partition skew | Per-partition records/bytes, key distribution |
| Listener duration rises alongside DB pool pending | Database saturation | Query latency, locks, pool size, DB CPU |
| p99 rises while p50 stays stable | Tail latency, GC, lock contention, or dependency outliers | Histograms, GC pauses, thread dumps, traces |
| Throughput rises while network bytes drop sharply | Effective compression or altered payload workload | Payload distribution, compression ratio, and CPU |
| Rebalances rise alongside lag spikes | Poll interval, excessive processing time, or member churn | `max.poll.interval.ms`, heartbeats, listener duration |
| Low consumer fetch rate, low lag | Little data or high fetch wait | Arrival rate, `fetch.min.bytes`, `fetch.max.wait.ms` |
| Rising retries/DLT and rising lag | Failing dependency or retry amplification | Exception classes, backoff, DLT publish rate |

Change settings only after forming a metric-backed hypothesis. For instance, raising `fetch.min.bytes` when the consumer is already database-bound will not fix the bottleneck and can worsen latency.

## 28. Controlled batching and compression experiments

Batching and compression are often the first producer variables worth testing, provided they are measured on realistic payloads.

Workflow:

1. Run a baseline with current settings.
2. Keep the workload constant and change one `batch.size` value.
3. Measure throughput, p95/p99 producer ack, producer/broker CPU, and bytes/s.
4. Return to baseline and test a different `linger.ms`.
5. Test `compression.type` (`none`, `lz4`, `zstd`) on the same payload distribution.
6. Compare network savings, CPU cost, and end-to-end latency together.

Producer batching groups records per partition; larger batches can cut request count and improve compression, yet use more buffer memory and records may wait longer for batches to fill. `linger.ms` is a batch-accumulation wait cap, not a fixed delay on every record; full batches can be sent early. Defaults can change across Kafka versions, so record versions in reports. See [Apache Kafka Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs).

## 29. Testing partition counts and consumer concurrency

Build a test matrix across partition counts and concurrency, for example:

| Partitions | Concurrency | Goal |
|---:|---:|---|
| 3 | 1 | Single-consumer baseline |
| 3 | 3 | One consumer per partition |
| 6 | 3 | Two partitions per consumer (depending on assignment) |
| 6 | 6 | Increase parallel consumers |
| 6 | 12 | Observe excess consumers and overhead |

This is only an example matrix. Use production-like key distributions and inspect per-partition throughput/lag. Increasing partition count can raise parallelism, yet also increases metadata, segment files, leader assignments, and alters per-key ordering when the partitioner maps keys to new partitions.

Do not pick a partition count solely from one run's throughput. Account for consumer group scalability, broker count, leader distribution, retention, replication, and future load growth plans.

## 30. Testing retries, DLT, and failure injection

Retries generate extra traffic and processing time. If benchmarks only test the happy path, production capacity can be overestimated.

Design scenarios:

- Small transient failure rate, e.g., 0.1% of records.
- Slow dependency causing periodic spikes in listener duration.
- Group of poison messages routed to DLT.
- Temporary DLT broker publish failure.
- Consumer restarts/rebalances while backlog exists.
- Database timeouts triggering concurrent retries across many records.

Observe retry attempts, retry topic/DLT ingress, listener failure rate, lag, and recovery time. Ensure tests are bounded to prevent unintended retry storms. When benchmarking DLT, verify zero lost records and zero infinite loops.

## 31. Measuring data correctness alongside performance

High throughput is meaningless if records are lost or duplicated outside the contract. Every benchmark event should have a unique ID. After each run, reconcile:

- Events created by the generator.
- Events confirmed by the producer.
- Events received by consumers.
- Events completing business processing.
- Events failed/retried/sent to DLT.
- Duplicate events by `eventId`.
- Missing events or events lacking a terminal state.

Under at-least-once delivery, duplicate deliveries can occur and consumers must be idempotent. Do not conclude data is wrong solely because listener invocation count exceeds generated count; distinguish invocations, unique event IDs, and business completions.

## 32. Benchmarking in a production-like environment

A trustworthy benchmark should match production topology across critical dimensions:

- Matching broker version and broker configuration.
- Broker count, partitions, replication factor, and `min.insync.replicas`.
- Storage class, disk throughput, and network placement.
- Producer/consumer instance counts and CPU/memory limits.
- Security protocols, authentication, and ACLs if security adds meaningful overhead.
- Serialization, Schema Registry, TLS, and compression.
- Databases/dependencies with realistic datasets and connection pools.
- Monitoring/tracing agents similar to production.

If the test environment is smaller, use results for relative comparisons or bottleneck discovery rather than linearly scaling CPU/broker counts to extrapolate production capacity. Kafka throughput depends nonlinearly on partition placement, replication, networking, disk, key skew, and workload mix.

Never run stress tests on a production cluster without a plan, load caps, and operational coordination. A benchmark can drive up lag, consume quotas, or contend for resources with live traffic.

## 33. Reproducible benchmark procedure

1. Document the question to answer and target SLOs.
2. Gather a workload profile from production or controlled synthetic data.
3. Prepare cluster, topics, partitions, replication, and datasets.
4. Verify the load generator is not the bottleneck.
5. Run baseline and warm-up.
6. Run steady state at target rate and record full metrics.
7. Repeat at least three times or enough times to measure variance.
8. Test burst, soak, hot-key, and failure scenarios.
9. Change one intentional variable group at a time; never mutate multiple configs at once.
10. Verify lag drain, event completeness, duplicates, and DLT.
11. Compare results to baseline using the same measurement windows and workloads.
12. Archive configurations, versions, seeds, commands, and dashboard snapshots for reproducibility.

If results swing widely across runs, find the environmental cause before picking the best figure. Report the median across runs and spread; never report only the fastest run.

## 34. Benchmark report template

Every benchmark run should save a structured report:

| Field | Values to record |
|---|---|
| Run ID / timestamp | Unique ID, start/end timestamps |
| Application | Commit SHA, Spring Boot/Spring Kafka/Kafka client versions |
| Cluster | Broker version, broker count, CPU/RAM/disk/network |
| Topic | Partitions, replication factor, retention, min ISR |
| Producer | acks, idempotence, compression, batch size, linger, in-flight |
| Consumer | group count, concurrency, max poll records, ack mode |
| Payload | p50/p95/p99 size, schema, key distribution |
| Workload | target/actual event rate, burst, duration, open/closed loop |
| Results | generated/acked/consumed/completed rates, p50/p95/p99 latency |
| Lag | max/avg per partition, oldest event age, drain duration |
| Errors | send failures, listener failures, retries, DLT, duplicates/missing |
| Resources | CPU, heap, GC, network, disk, DB pool |
| Conclusion | bottleneck, SLO pass/fail, capacity and headroom |

Conclusions must state measurement boundaries explicitly. For example: "At 8,000 events/s, p99 end-to-end reached 420 ms, lag stayed flat, zero missing events; at 10,000 events/s, p99 exceeded 1 second and partition 2 lag grew continuously due to a hot key." This phrasing is far more actionable than "Kafka hit 10k TPS."

## 35. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Producer perf test proves the app hits that throughput | The tool measures only the basic producer/broker path; it runs no business listener |
| High throughput means good latency | A system can raise throughput while p99 and lag already breach SLOs |
| Measuring average latency is enough | p95/p99 reveal tail latency and outliers |
| Low total consumer lag means every partition is healthy | One hot partition can lag heavily while total lag looks low |
| Average payload size is representative enough | p95/p99 sizes and payload entropy impact batching/compression/network |
| Increasing concurrency always raises throughput | Partitions, CPU, and downstream cap parallelism |
| `send()` returning means the broker acked | `KafkaTemplate.send()` returns a future; future completion reflects the send result per ack config |
| Fast consumer polling means fast business processing | Listeners/databases may take much longer to finish |
| One benchmark run is sufficient | JVM warm-up, noise, and environment make results vary; repeat runs |
| Maximizing throughput is the sole goal | Must hit throughput alongside latency, lag, error, and correctness SLOs |
| Small-cluster results scale linearly to production | Partitions, replication, storage, and networking create nonlinear limits |

## Pre-acceptance benchmark checklist

- Throughput, p95/p99 latency, lag, error, and recovery SLOs are defined.
- Workload includes realistic payload size distribution, key skew, event mix, and bursts.
- Broker/client baselines are separated from end-to-end Spring Kafka benchmarks.
- Load generator has sufficient CPU/network and sensible in-flight caps.
- Producer/consumer properties and dependency versions are recorded.
- Warm-up, steady-state, burst, soak, and failure scenarios are included.
- Generated, producer-acked, consumer-delivered, and business-completed rates are measured separately.
- p50/p95/p99 and end-to-end latency are measured with synchronized clocks or tracing.
- Consumer lag and event age are tracked per partition.
- Producer, consumer, broker, JVM, network, disk, and downstream metrics are monitored.
- Event completeness, duplicates, retries, and DLT are verified.
- Each run changes only intentional variables and is repeated.
- Results, configs, run IDs, and measurement boundaries are documented.
- Operating target retains headroom below the saturation point.

Benchmarking under realistic load connects throughput figures to latency, lag, correctness, and resource usage across the entire pipeline. Start with a workload model featuring real payload/key distributions, measure a broker baseline followed by the end-to-end Spring Kafka application, execute multiple scenarios, and change configurations one step at a time. Accept capacity only when the system sustains SLOs across steady state, bursts, and recovery without losing events or producing duplicate side effects outside the contract.

## References

- [Apache Kafka – Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka – Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [Apache Kafka – Producer Performance Tool source](https://github.com/apache/kafka/blob/trunk/tools/src/main/java/org/apache/kafka/tools/ProducerPerformance.java)
- [Spring for Apache Kafka – Micrometer Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring for Apache Kafka – Micrometer Observation](https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html)
