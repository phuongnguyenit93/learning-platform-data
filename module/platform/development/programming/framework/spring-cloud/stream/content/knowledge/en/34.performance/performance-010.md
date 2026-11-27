# Comparing Configurations Using Measurements Instead of Only Adding Threads

In Spring Cloud Stream, increasing `consumer.concurrency` from 1 to 4 or 16 may speed up processing, **or it may fail to increase throughput** while raising p99 latency, database pressure, memory usage, and retry counts. Concurrency is only one parameter in a system consisting of producers, brokers, partitions, consumers, business logic, and downstream dependencies.

This lesson explains how to design measurements, compare configurations, and choose options that actually deliver results. The focus is on event-driven applications using Spring Cloud Stream's `Supplier`/`Function`/`Consumer` model running over Kafka, RabbitMQ, or Pulsar binders, including stateful Kafka Streams topologies. The goal is not finding the highest thread count, but achieving **the required load at acceptable latency, reliability, resource usage, and cost**.

Running example: an `order-projection` service receives `OrderCreated`, validates data, writes a projection to PostgreSQL, and optionally emits `OrderProjected`. As traffic climbs, consumer lag builds up. Measure before deciding whether to add consumers, add partitions, change batch sizes, or optimize the database.

## 1. Performance is a system, not a single variable

Typical path:

~~~text
Producer
  |
  | serialization, batching, compression, acks
  v
Broker (Kafka topic / Rabbit queue / Pulsar topic)
  |
  | partition, dispatch, fetch/prefetch, subscription
  v
Spring Cloud Stream input binding
  |
  | conversion, headers, retry policy
  v
Consumer / Function
  |
  | CPU, allocation, DB calls, HTTP calls, locks
  v
Output binding / ack / offset commit
  |
  v
Downstream service and storage
~~~

Ultimate throughput is capped by the current bottleneck. If PostgreSQL can sustain only around 1,200 writes/second, adding consumers simply increases contention on the connection pool without increasing completed events.

Optimization must distinguish layers:

| Layer | Commonly tested parameters | Potential limits |
|---|---|---|
| Producer | `linger.ms`, `batch.size`, compression, `acks` | Compression CPU, bandwidth, batch wait time |
| Broker | Partitions, replication, quotas, storage | I/O, network, leader or queue hotspots |
| Consumer | Concurrency, replicas, fetch/prefetch | Partition assignment, queue dispatch, RAM |
| Function | Payload conversion, batch logic, allocations | CPU, GC, synchronization |
| Downstream | Batch writes, connection pools, indexes | Transaction locks, pools, rate limits |
| Error path | Retry/backoff/DLQ | Retry storms, poison messages, duplicates |
| Stateful processing | Streams threads, caches, state stores | RocksDB I/O, restore, changelog, key skew |

You cannot declare a configuration good solely from function invocation speed. If outputs are not durably persisted or failing messages are silently skipped, that number does not represent completed business work.

## 2. Define targets and constraints before measuring

Before tuning, write explicit **SLOs** (service level objectives) and functional constraints:

- Target throughput: e.g., 1,500 events/second steady and 3,000 events/second for 10 minutes.
- Latency: p95 under 250 ms, p99 under 800 ms, measured at agreed boundaries.
- Backlog: zero sustained growth at steady traffic; post-burst recovery within the required deadline.
- Correctness: zero lost events; duplicates handled per idempotency policy; ordering by `orderId` if required by business rules.
- Errors: business error, retry, and DLQ rates below defined thresholds.
- Resources: caps on CPU, RAM, database connections, and cost per million events.
- Safety: never weaken delivery guarantees or skip acknowledgements just to inflate numbers.

Without clear targets, the fastest configuration in a test run may be unsuitable for deployment. For example, an option hitting 4,000 events/second with p99 over 5 seconds fails a near-real-time system.

## 3. Distinguishing throughput, latency, lag, and backlog

Four concepts measure distinct quantities:

| Metric | Meaning | Common unit |
|---|---|---|
| Input rate | Messages produced/sent to the broker | events/s |
| Processing rate | Events successfully processed by the app | events/s |
| Output rate | Events successfully written to sink or emitted downstream | events/s |
| Latency | Time from milestone A to milestone B | ms, p50/p95/p99 |
| Kafka consumer lag | Delta between end offset and consumed/committed offset depending on metric | records |
| RabbitMQ ready/unacked | Messages waiting for delivery / delivered awaiting ack | messages |
| Pulsar backlog | Remaining backlogged messages per subscription | messages |
| Error/DLQ rate | Failures and events routed to error flows | events/s, % |

An application with a 20 ms function duration can still have minutes of end-to-end latency if messages sit in the broker. Conversely, zero Kafka lag during idle traffic does not prove the application can survive bursts.

Measure at least three distinct durations:

1. **Queue waiting time:** from when a message is ready in the broker until the consumer begins processing it.
2. **Business processing time:** from when the function starts until business processing finishes.
3. **End-to-end latency:** from when an event is created/emitted until side effects or outputs are confirmed per test criteria.

Pick explicit milestones: producer timestamp, broker receipt time, consumer receipt time, and database transaction commit time. If servers have clock skew, latencies subtracted across machines can be wrong; synchronize clocks or use traces with clock discipline and verify skew.

## 4. Formulas for reading metrics accurately

Over a measurement window \(\Delta t\):

\[
\text{Successful throughput} =
\frac{\text{valid completed events}}{\Delta t}
\]

For a stable system with consistent units, Little's Law states:

\[
L \approx \lambda W
\]

Where \(L\) is the average number of items in the system, \(\lambda\) is the steady completion rate, and \(W\) is the average time an item spends in the system. Do not apply it mechanically when queues are growing unboundedly or load fluctuates continuously.

If the producer emits \(\lambda\) events/second and consumers complete \(\mu\) events/second:

- \(\mu < \lambda\): backlog tends to grow by roughly \(\lambda - \mu\) events/second.
- \(\mu = \lambda\): capacity matches load tightly, leaving little headroom for bursts and retries.
- \(\mu > \lambda\): backlog can drain, provided downstream stays unchanged.

With initial backlog \(B\) and steady rates \(\mu > \lambda\), approximate backlog drain time is:

\[
T_{\text{drain}} \approx \frac{B}{\mu - \lambda}
\]

Purely illustrative example: a backlog of 120,000 events, ongoing ingress of 800 events/s, and consumer completion of 1,000 events/s gives a net drain rate of 200 events/s, taking roughly 600 seconds (10 minutes) if assumptions hold. Do not use this formula when retries, throttling, or key skew cause wide throughput swings.

## 5. p95 and p99 matter more than an average

Suppose two configurations have nearly identical average processing latency:

| Configuration | Avg | p95 | p99 |
|---|---:|---:|---:|
| A | 45 ms | 100 ms | 160 ms |
| B | 44 ms | 115 ms | 850 ms |

B has a slightly lower average yet far worse tail latency. A few events may be waiting on database locks, GC pauses, or retries. For a service requiring p99 under 300 ms, A is clearly preferable.

Percentiles require consistent aggregation windows and measurement boundaries. Never average per-minute p99s to estimate full-test p99. Aggregate histograms or underlying distribution buckets, keeping histogram configuration identical across runs.

Do not measure only function p95 if your SLO covers the journey from publish to durable persistence. A system with fast function execution but queueing at the broker still has very high end-to-end p95.

## 6. Establishing a reproducible baseline

A baseline is the result of the current configuration under controlled conditions:

~~~text
Build:            same commit and JVM
Binder:           same version
Broker:           same cluster/partitions/replication
Consumer group:   explicitly named with equivalent starting offsets
Payload:          same sizes, key distribution, and error rates
Downstream:       same database dataset, indexes, pools, and limits
Environment:      same CPU/memory quotas, pod count, network
Traffic profile:  same ramp-up, steady state, and burst
Measurement:      same metrics and measurement windows
~~~

If Run A happens on an idle cluster and Run B happens while the database runs a backup job, the difference may have nothing to do with concurrency.

With Kafka, prepare consumer groups/offsets consistently for each run. With RabbitMQ, prepare the same message counts and queue state. With Pulsar, keep the same subscription type, backlog, and starting position. Never let one run drain old backlog while another processes live traffic and then compare them directly.

## 7. Designing realistic workloads

Include at least three profiles:

| Profile | Description | What to watch |
|---|---|---|
| Stable | Constant send rate at expected load | Sustained capacity and headroom |
| Burst | Rate spikes 2–3x for several minutes | Lag growth, p99, recovery duration |
| Recovery | Producer drops back to baseline after burst | Backlog drain speed, retries/DLQ |

Workloads should reflect realistic payload distributions, such as 60% small, 30% medium, and 10% large. If 5% of events hit slow database queries or 1% trigger retries, include them in the test with documented ratios and causes.

Verify key distributions. If every message shares `customerId`, adding consumers will not improve per-key parallelism where ordering must hold. A benchmark with uniform random keys can look great while diverging sharply from a production workload with hot keys.

Keep synthetic data seeds, message sizes, key cardinality, and error rates constant within each comparison.

## 8. Measuring across multiple layers to locate bottlenecks

Minimum metric set:

| Layer | Metrics to collect |
|---|---|
| Producer | Send rate, ack latency, error/retry rate, bytes/s, batch size |
| Broker | Ingress/egress, request latency, storage/network, throttling, partition distribution |
| Consumer | Records/s, lag/backlog, poll/fetch behavior, rebalances, redeliveries |
| Function | Successful events/s, failure ratio, duration p50/p95/p99 |
| Database/API | Query latency, pool active/waiting, lock waits, timeouts/rate limits |
| JVM | Process CPU, heap, GC pauses, allocation, thread count |
| Container/node | CPU throttling, memory limits, network, disk I/O |
| Business | Events actually committed/emitted, duplicates, DLQ |

For instance, the Kafka binder exposes the Micrometer metric `spring.cloud.stream.binder.kafka.offset`, reflecting lag by topic and group from the binder's viewpoint. The Kafka client also exposes metrics like `records-consumed-rate` and `records-lag-max`. Read metric definitions carefully: some rely on committed offsets while others reflect fetch/poll progress, so the two charts do not necessarily align.

With RabbitMQ, distinguish `messages_ready` (undelivered) from `messages_unacknowledged` (delivered but unacked). With Pulsar, watch per-subscription backlog, unacked, redeliveries, and dispatch/ack rates. Never assume a Kafka metric maps one-to-one to RabbitMQ or Pulsar metrics.

## 9. Enabling Actuator and Micrometer

With Spring Boot, use Actuator and the Prometheus registry to collect JVM, system, and custom application metrics.

Maven (let Spring Boot manage versions):

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
  <groupId>io.micrometer</groupId>
  <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Example configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Once the registry is on the classpath and endpoints are exposed properly, check `/actuator/metrics` for meter names and `/actuator/prometheus` for observability scraping. Secure management endpoints in production; never expose full metrics to the public Internet.

You can verify with:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/jvm.memory.used
curl http://localhost:8080/actuator/prometheus
~~~

Actuator meter names retain Micrometer naming like `jvm.memory.used`, whereas Prometheus output normalizes them to Prometheus naming conventions. Query with the matching name for each system.

## 10. Adding custom metrics to the Consumer

Measure the business logic itself to see whether CPU/DB is the root cause or merely a side effect of concurrency.

Example `Consumer` receiving order events and calling a service, timing function execution with `Timer` and counting success/failure outcomes:

~~~java
import java.util.function.Consumer;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class OrderMetricsConfiguration {

    record OrderCreated(String orderId, long total) {}

    interface ProjectionWriter {
        void save(OrderCreated order);
    }

    @Bean
    Consumer<Message<OrderCreated>> projectOrder(
            ProjectionWriter writer,
            MeterRegistry registry) {

        return message -> {
            Timer.Sample sample = Timer.start(registry);

            try {
                writer.save(message.getPayload());
                registry.counter(
                    "orders.processed",
                    "outcome", "success"
                ).increment();
            } catch (RuntimeException error) {
                registry.counter(
                    "orders.processed",
                    "outcome", "failure"
                ).increment();
                throw error;
            } finally {
                sample.stop(
                    registry.timer("orders.processing.duration")
                );
            }
        };
    }
}
~~~

Binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: projectOrder
    stream:
      bindings:
        projectOrder-in-0:
          destination: orders.created
          group: order-projection
~~~

`orders.processing.duration` covers only the `writer.save` call and instrumentation overhead inside the lambda. It does **not** automatically include broker queue wait time, network delivery, post-exception retries, or offset commit/ack after the function returns. Combine it with broker metrics and separate end-to-end timing.

Never add `orderId` or `customerId` as labels/tags: unbounded values cause metric cardinality explosions. Use bounded tags such as `outcome`, `function`, `binding`, or `eventType`.

## 11. Reproducible A/B methodology

Do not change five parameters at once and claim concurrency caused the speedup. Structure experiments cleanly:

1. State a concrete hypothesis: "raising concurrency from 1 to 2 reduces lag because CPU has headroom and Kafka has at least 2 partitions."
2. Measure A (baseline), then B (one change), then rerun A to check for environmental drift.
3. Keep load, data, resource limits, broker, and downstream equivalent.
4. Allow warm-up time for JIT, connection pools, caches, and consumer assignments; exclude warm-up from steady-state numbers.
5. Run long enough to observe GC, retries, backlog, and tail latency—not just a 10-second burst.
6. Repeat independent runs; report median, spread, or confidence intervals rather than a single run.
7. Record commit, config, timestamps, dashboard/snapshots, and results in an experiment log.
8. Select configurations against established targets and guardrails.

If you change Kafka partition count, treat it as a separate infrastructure experiment; that change can alter key distribution and ordering. Document it clearly so it is never compared as a simple thread-level tweak.

## 12. Sample result table: more threads is not always better

**The numbers below are entirely synthetic to illustrate how to interpret results, not a real benchmark.**

Simulated conditions: 6-partition Kafka topic, 1 instance with 4 vCPUs, fixed PostgreSQL, steady load 1,500 events/s for 20 minutes after warm-up, zero initial backlog. Payload distribution, keys, and error rates held constant. Because A/B process slower than arrival rate, E2E latency includes growing queue wait and can reach tens or hundreds of seconds.

| Option | Consumer concurrency | Completed (events/s) | p95 E2E | p99 E2E | CPU | End lag |
|---|---:|---:|---:|---:|---:|---:|
| A | 1 | 980 | 395,000 ms | 412,000 ms | 38% | Growing rapidly |
| B | 2 | 1,420 | 62,000 ms | 66,500 ms | 63% | Growing |
| C | 4 | 1,500 | 210 ms | 510 ms | 83% | Stable |
| D | 8 | 1,500 | 370 ms | 1,060 ms | 94% | Stable |

C keeps up with arrival rate and shrinks tail latency relative to B. D completes no additional events because throughput is already capped by the input rate, while CPU and p99 get worse. With 6 partitions, configuring 8 consumer threads in one group can leave some threads without partitions; extra overhead produces no useful work. The simulated p95/p99 values in A/B reflect growing backlog: if a dashboard reports only a few hundred milliseconds of p99 while the queue grows for 20 minutes, it is likely measuring in-function processing duration rather than E2E latency.

If you need p99 under 800 ms while keeping CPU headroom, C is a strong candidate, yet you still must verify stability, retries, cost, and run-to-run variance. Never decide from a single table.

## 13. Kafka consumer: partitions set the practical limit

With the regular Kafka binder, each partition of a topic is assigned to at most one consumer in the same group at a time. Useful consumption parallelism for a topic is therefore usually capped by its partition count.

Suppose there are 6 partitions:

~~~text
concurrency=1
  consumer-1: P0 P1 P2 P3 P4 P5

concurrency=3
  consumer-1: P0 P1
  consumer-2: P2 P3
  consumer-3: P4 P5

concurrency=8 (same group, one topic)
  consumer-1..6: each consumer can receive 1 partition
  consumer-7..8: no partition to process
~~~

This is a simplified illustration: actual assignment also depends on instance count, subscribed topics, and the partition assignor. Always count **total consumers in the same group across all replicas**, not just one pod's concurrency.

If partition count is sufficient yet lag climbs on only 1–2 partitions, the issue may be hot keys or skewed key distribution. Adding total consumers will not cure a hotspot if records sharing that key keep landing on one partition.

## 14. Concurrency experiment example for the Kafka binder

A `Function` transforming events into projections:

~~~java
@Bean
Function<OrderCreated, OrderProjected> projectOrder(
        OrderProjectionService service) {

    return event -> service.project(event);
}
~~~

Baseline:

~~~yaml
spring:
  cloud:
    function:
      definition: projectOrder

    stream:
      bindings:
        projectOrder-in-0:
          destination: orders.created
          group: order-projection
          consumer:
            concurrency: 1
        projectOrder-out-0:
          destination: orders.projected
~~~

Experiment B changes only one parameter:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        projectOrder-in-0:
          consumer:
            concurrency: 2
~~~

Experiment C uses `concurrency: 4`. Keep the same group and destination across runs, while preparing equivalent starting offsets/datasets for each run. If replica count changes, record `replicas × concurrency` to track total consumers.

Measure at least: successful records/s, p95/p99 end-to-end, per-partition `records-lag-max`, consumer rebalances, CPU, GC, database pool waiting, and DLT. If throughput rises while lock/timeout errors jump sharply, the experiment has not succeeded.

## 15. Kafka fetch, batch, and producer tuning must be measured separately

When the bottleneck is I/O or per-record overhead, you can test native Kafka parameters through binder configuration:

| Kafka client parameter | Effect | Potential trade-offs |
|---|---|---|
| `max.poll.records` | Caps records returned per poll | Large batches can extend processing and threaten poll deadlines |
| `fetch.min.bytes` | Minimum bytes broker tries to accumulate per fetch | Improves batch throughput but raises wait time at low traffic |
| `fetch.max.wait.ms` | Max time broker waits for enough data | Cuts tiny fetches; adds latency when messages are sparse |
| `max.partition.fetch.bytes` | Data cap per partition per fetch | Affects memory and fetch pacing |
| `linger.ms` | Producer waits briefly to accumulate a batch | Better batching efficiency, potentially higher publish latency |
| `batch.size` | Producer batch size limit | Larger batches require more memory |
| `compression.type` | Compresses record batches | Less network usage, higher CPU |

These settings must match Kafka binder/client capabilities and your running version. Example producer extended config:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          projectOrder-out-0:
            producer:
              configuration:
                "linger.ms": 5
                "batch.size": 32768
                "compression.type": lz4
~~~

This is a starting point for measurement, not a "fastest" preset. Measure actual batch sizes, send latency, bytes/s, and compression CPU before adopting. With consumer batch mode, payload shape and ack/retry semantics can change, so test function correctness as well.

## 16. RabbitMQ: prefetch and consumer count

RabbitMQ uses queues and a different dispatch model from Kafka. One queue can have multiple consumers receiving messages per broker behavior, while **prefetch** caps how many unacked messages are delivered to a consumer to avoid flooding slow handlers.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: projection
          consumer:
            concurrency: 2

      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              prefetch: 20
~~~

Verify your Rabbit binder version and listener container. `prefetch` is an extended Rabbit consumer property, whereas `concurrency` is a generic consumer binding property. Higher prefetch keeps more messages ready locally, yet raises unacked counts and memory; if a consumer slows down, messages can pile up on specific consumers.

Test controlled pairs such as `(concurrency, prefetch) = (1,10), (2,10), (2,50)` instead of jumping straight to `concurrency=20, prefetch=1000`. Monitor ready queue depth, unacked counts, ack rate, and processing duration.

If the workload depends on ordering, multiple consumers on one queue can finish out of publish order. Verify business semantics before raising concurrency.

## 17. RabbitMQ: which metrics show prefetch is too large?

Signs prefetch is too high:

- `messages_unacknowledged` climbs sharply while ack rate stays flat.
- Consumer heap and message-retaining objects grow.
- Messages pile up on a few slow consumers while others stay idle.
- Pre-processing wait lengthens and p99 rises.
- When a consumer dies, a large volume of messages must be redelivered.

Signs prefetch is too low:

- Consumers wait for the next delivery after every ack; throughput stays low despite idle CPU.
- Network round trips/dispatch dominate business processing time.
- Moderate prefetch increases boost throughput while memory/unacked stay within bounds.

RabbitMQ distinguishes ready messages from unacked messages; total queue depth alone is insufficient. Under manual acknowledgement mode, prefetch is especially helpful for capping unacked deliveries.

If enabling Rabbit binder consumer-side batching, you can test `batch-mode`, `enable-batching`, `batch-size`, and `receive-timeout` per binder docs. However, the API then receives `List<...>` and requires dedicated batch/error handling; never flip batch mode via a single YAML line without checking the function signature.

## 18. Pulsar: subscription type, receiver queue, and partitions

With the Pulsar binder, Spring Cloud Stream's `group` maps to subscription identity; `subscription.type` controls how consumers in the subscription receive messages.

| Type | Scaling consequence |
|---|---|
| Exclusive | One consumer attaches to the subscription; adding replicas adds no active consumers |
| Failover | Has standby consumers; on partitioned topics, active consumers can split partitions |
| Shared | Multiple active consumers; no ordering guarantee |
| Key_Shared | Distributes by key, preserving per-key order per broker semantics |

Pulsar has client-side receiver queues and batching. Larger buffers/receiver queues can cut receive waits while increasing in-flight memory. Effectiveness depends on message size, partition count, subscription type, key handling, and consumer memory limits.

Rather than assuming a native property keeps the same name across all versions, pick Pulsar consumer configurations supported by **Spring Boot/Spring for Apache Pulsar** and your binder version. The Pulsar binder supports overrides at the extended binding level under:

~~~text
spring.cloud.stream.pulsar.bindings.<input-binding>.consumer.*
~~~

Example specifying a `Shared` subscription:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection

      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                type: Shared
                mode: Durable
~~~

Verify ordering and idempotency correctness when changing subscription types; this is a semantic change, not purely speed tuning. With `Key_Shared`, producers must use stable keys and compatible batching (disabling batching or using key-based batching per Pulsar guidance).

## 19. Kafka Streams: thread count and state stores

Kafka Streams should not be benchmarked like a stateless `Consumer`. It runs partition-bound tasks and may materialize state stores, changelogs, and restore state during rebalances.

One way to configure concurrency for the Kafka Streams binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              "num.stream.threads": 2
~~~

With the functional Kafka Streams binder, generic `spring.cloud.stream.bindings.<first-input>.consumer.concurrency` can also map to `num.stream.threads`. When a function has multiple input bindings, documentation specifies setting concurrency on the first input when using the generic property. Never configure both sources for the same purpose with conflicting values.

Before increasing threads, measure:

- Number of stream tasks/partitions that can run in parallel.
- `process-rate` and per-task/processor latency where available.
- CPU, GC, and RocksDB/state-store I/O.
- Changelog traffic, state restoration time, and rebalances.
- Key skew and state store size.
- Impact of caching, commit interval, and suppression on output latency.

A topic with only 2 partitions generally creates no additional useful stream task work when scaling threads from 2 to 8 for the same topology. Adding threads also cannot fix hot keys; it can simply add overhead and memory.

## 20. Do not trade correctness for pretty numbers

Certain changes produce fake "throughput gains":

- Skipping producer acknowledgements and counting messages as succeeded.
- Auto-acking before the database transaction commits.
- Disabling retries or dumping errors straight to DLQ while counting only the happy path.
- Enabling parallel processing that breaks ordering by `orderId`.
- Increasing batch sizes without ensuring transaction/idempotency safety for partial batch failures.
- Disabling changelogs or changing exactly-once guarantees without noting it in comparisons.
- Altering schema/serialization to shrink messages while dropping data.

Performance reports must accompany data correctness verification: input count, successes, errors, retries, DLQs, duplicates, and persisted outputs. An accurate, recoverable 1,500 events/s beats 3,000 events/s that silently drops 1% of events.

## 21. Retries, DLQs, and failure injection

To keep benchmarks realistic, introduce controlled faults:

- Database times out on 1% of requests.
- Broker returns transient errors or briefly disconnects.
- A subset of schema-invalid events routes to the DLQ.
- A consumer restarts mid-processing.
- Downstream slows down for 2 minutes.

Measure retry rate, backoff duration, redeliveries, DLQ counts, and impact on p95/p99 of healthy events. If raising concurrency also spikes exceptions because the database pool exhausts, successful throughput can actually fall.

Keep three counts separate:

\[
N_{\text{input}} = N_{\text{success}} + N_{\text{dead-letter}} + N_{\text{pending}}
\]

This is a simple accounting equation for a controlled window, counting each event once by its end-of-window state. Retry attempts and duplicate deliveries are not new events. In practice, add a filtered/expired state if the system intentionally drops events.

## 22. CPU, memory, GC, and connection pools

Increasing concurrency typically increases simultaneous requests hitting databases/APIs. Cross-check:

| Signal | Hypothesis | Next experiment |
|---|---|---|
| High CPU, rising lag | CPU-bound logic or serialization | Profile CPU, optimize code, check compression |
| Low CPU, high DB pool pending | Waiting on database connections | Tune pool/queries before adding consumers |
| Rising CPU throttling | Container lacks CPU quota | Test appropriate quota before adding threads |
| Rising heap/GC pauses | Prefetch/buffer/batch too large | Reduce in-flight counts, check allocations |
| Broker throttling | Quota or broker saturation | Measure broker request/storage/network |
| Lag rises on one partition | Hot key / skew | Measure per-partition, revisit key strategy |
| DLT rises after scaling | Downstream overloaded | Isolate failure cause and throttle load |

`concurrency` in Spring Cloud Stream does not automatically raise HikariCP's `maximumPoolSize`, nor does it add real CPU to a pod. If 8 consumers share a 4-connection pool and each event runs 3 queries, wait times can rise even with more threads.

Never raise consumer threads, DB pool size, and pod count together in one run if you need to know which change helped.

## 23. Conditional optimization of partitions and keys

Once measurements prove partitions are the limit, consider raising partition counts or changing key strategy. Still:

- Adding Kafka partitions can alter key-to-partition hashes and affect ordering of same-key messages across the change boundary.
- Kafka Streams must account for repartitioning, changelogs, restores, and local state.
- Pulsar partitioned topics can scale throughput, yet require checking subscriptions, routing keys, and ordering.
- RabbitMQ does not share Kafka partition semantics; queue/super-stream/plugin models must be evaluated separately.
- When data has a single very hot key, adding partitions alone may fail to split that key.

A helpful diagnostic is plotting throughput and lag per partition/key bucket, not just topic totals. The goal is identifying **effective parallelism with useful work**, and only then picking consumer counts.

## 24. Illustrative multi-axis benchmark table

**All figures in the following table are hypothetical illustrations, not real measurements.** In this table, p99 is measured **only from when the function starts**, excluding broker queue wait. It assumes an existing backlog to compare peak drain capacity; deployment reports must additionally measure E2E p99 and backlog over time.

| Run | Concurrency | Batch/prefetch | Success/s | Processing p99 | CPU | Retries/s | Notes |
|---|---:|---|---:|---:|---:|---:|---|
| A1 | 1 | default | 950 | 1,200 ms | 36% | 2 | Baseline |
| B1 | 2 | default | 1,350 | 690 ms | 58% | 3 | More parallelism |
| C1 | 4 | default | 1,520 | 520 ms | 79% | 5 | Candidate |
| D1 | 8 | default | 1,500 | 1,050 ms | 94% | 18 | Contention |
| C2 | 4 | tuned batch | 1,620 | 610 ms | 78% | 6 | Higher throughput, worse tail |
| A2 | 1 | default | 940 | 1,240 ms | 37% | 2 | Repeat baseline |

A2 matching A1 closely indicates a reasonably stable environment during this illustration. If A2 diverges widely from A1, investigate environmental shifts before declaring B/C/D better.

If the local target is **in-function processing** p99 under 700 ms and backlog drain capacity above 1,400 events/s, both C1 and C2 pass that filter—with C1 offering better p99 and C2 higher throughput. Before deciding, measure E2E p99, headroom, cost, and run-to-run variance.

## 25. Scoring configurations by constraints rather than a single maximum

Example selection rules:

1. Eliminate configurations violating correctness (lost events, broken ordering, unhandled duplicates).
2. Eliminate configurations violating latency/error/lag-recovery SLOs.
3. Compare **confirmed** throughput across remaining candidates.
4. Compare CPU/memory/broker I/O and resource cost.
5. Prefer options with headroom for bursts and slow downstreams.
6. If differences fall within measurement noise, choose the simpler, easier-to-operate configuration.

You can track a cost metric:

\[
\text{Cost / 1M events} =
\frac{\text{cost during measurement window}}
{\text{valid completed events in window}}
\times 1{,}000{,}000
\]

Calculate cost consistently: pods × CPU/RAM, broker, storage, and downstream. Never count only application CPU as if the broker and database were free.

## 26. Reproducible experiment log template

Every run should save a record like this:

~~~yaml
experimentId: perf-order-projection-2026-11-24-c1
buildCommit: "<git-sha>"
javaVersion: "<version>"
springCloudStreamVersion: "<version>"
binder: kafka
function: projectOrder
inputDestination: orders.created
consumerGroup: order-projection
partitions: 6
replicas: 1
consumerConcurrency: 4

traffic:
  profile: steady-plus-burst
  steadyRatePerSecond: 1500
  burstRatePerSecond: 3000
  payloadDataset: orders-fixture-v2
  keyDistribution: zipf-like
  errorInjectionPercent: 1

environment:
  cpuLimit: "4"
  memoryLimit: "2Gi"
  databasePoolSize: 10

measurement:
  warmupMinutes: 5
  steadyMinutes: 20
  repeatedRuns: 3
  dashboardSnapshot: "<link-to-results>"

metrics:
  successPerSecond: "<measured>"
  p95EndToEndMs: "<measured>"
  p99EndToEndMs: "<measured>"
  lagAtEnd: "<measured>"
  cpuPercent: "<measured>"
  retryPerSecond: "<measured>"
  dlqTotal: "<measured>"

decision:
  result: pending-review
  notes: "Compare against A/B/A and verify guardrails"
~~~

Never fill in fabricated numbers as real measurements. Replace placeholders with system-measured results and preserve metric definitions. Attach dashboard/snapshot links and timestamps so others can verify.

## 27. Complete hands-on workflow

Run a 4-configuration measurement suite for `order-projection`:

1. Prepare a broker and 6-partition topic, a seeded database, and a producer generating a reproducible workload.
2. Enable Actuator/Micrometer; add function timers/counters and per-group broker metrics.
3. Run baseline `concurrency=1` with warm-up and 20 minutes of steady load.
4. Repeat with `concurrency=2`, keeping everything else constant.
5. Repeat with `concurrency=4` and `concurrency=8`.
6. Rerun baseline at the end or interleaved to catch drift.
7. Collect successful events/s, p95/p99 E2E, per-partition lag, CPU/GC, DB pool metrics, and retries/DLT.
8. Use the same burst workload to measure backlog recovery time.
9. Use the results table to pick the sweet spot, explaining root causes rather than sorting purely by throughput.
10. If SLOs are still unmet, design the next experiment for a different variable (DB batching, key distribution, prefetch, or partition count).
11. Verify correctness by reconciling inputs, outputs, duplicates, and DLQ.
12. Document recommendations, chosen configuration, and rollback plan.

For RabbitMQ, switch the experimental variables to `consumer.concurrency` and `prefetch` after collecting the baseline. For Pulsar, check subscription type, receiver queue, and partitions per version. For Kafka Streams, test `num.stream.threads` and monitor state-store/restore/task-level metrics.

## 28. Common mistakes and fixes

| Mistake | Consequence | Right approach |
|---|---|---|
| Raising concurrency by intuition | Higher overhead, worse p99 | A/B/A with identical traffic |
| Checking only application CPU | Misses DB/broker bottlenecks | Collect multi-layer metrics |
| Using producer throughput alone | No proof outputs completed | Count committed business work |
| Ignoring retries/DLQ | Inflated successful throughput | Reconcile input/success/error |
| Measuring averages instead of p99 | Hides tail latency | Measure histograms/percentiles |
| Changing multiple variables at once | Cannot isolate cause | One variable per experiment |
| Skipping warm-up | JIT/caches skew numbers | Exclude warm-up from results |
| Consumers > partitions without checking | Idle threads | Measure assignment/lag per partition |
| Oversized prefetch | Memory/unacked bloat | Step prefetch moderately |
| Testing only small messages/even keys | Fails to match production | Use realistic payload/key distributions |
| Skipping final baseline re-check | Environmental drift mistaken for gain | Use A/B/A or multiple repetitions |
| Changing delivery guarantees during benchmark | Results no longer comparable | Keep semantics fixed; verify correctness |
| Optimizing only steady load | Unknown post-burst recovery | Measure burst + drain time |
| Comparing costs across mismatched scopes | Wrong cost decisions | Normalize cost per 1M successes |

## 29. Self-check questions

1. Why does raising concurrency from 6 to 12 not necessarily raise throughput when a Kafka topic has 6 partitions?
2. Why might falling Kafka lag not be enough to prove the database wrote successfully?
3. What makes a benchmark baseline reproducible?
4. What is the difference between function p99 and end-to-end p99?
5. When RabbitMQ unacked rises while ack/s stays flat, what should you check before increasing prefetch?
6. When Kafka Streams has 2 useful tasks, what usually happens if you raise `num.stream.threads` to 8?
7. Why is switching Pulsar's `Shared` subscription to `Key_Shared` a semantic change requiring testing?
8. How do you distinguish broker, CPU, and database pool limits?
9. With a backlog of 90,000 events, input 700/s, and output 1,000/s, roughly how long does draining take under steady conditions?
10. When two configurations have nearly equal throughput yet differ in p99 and retry rate, what criteria guide the choice?

## 30. Practical conclusion

Start from the **definition of success**, measure a baseline, find the bottleneck, and test one hypothesis at a time. Hold workload and correctness constraints steady while examining successful throughput alongside latency, lag, error rates, and resources. Concurrency, partitions, prefetch, batching, or replica counts only matter when measurements prove they improve SLOs without unacceptable side effects.

In Spring Cloud Stream, the same property name can interact differently with Kafka, RabbitMQ, Pulsar, and Kafka Streams. Base decisions on version-accurate binder docs, real broker observations, and reproducible measurements.

## 31. Official references

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/binding-properties.html) — `consumer.concurrency` and binding properties.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/config-options.html) — Kafka binder, client, and metrics settings.
- [Spring Cloud Stream — Kafka Binder Metrics](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/metrics.html) — `spring.cloud.stream.binder.kafka.offset` and lag meaning.
- [Spring Cloud Stream — Kafka Streams Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html) — `num.stream.threads` and concurrency.
- [Spring Cloud Stream — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html) — prefetch, batching, and consumer options.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/5.0/pulsar/pulsar_binder.html) — subscriptions, partitions, and extended binding properties.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Actuator, Micrometer, and Prometheus.
- [Apache Kafka — Monitoring](https://kafka.apache.org/34/operations/monitoring/) — consumer `records-lag`, `records-consumed-rate`, fetch, and broker metrics.
- [RabbitMQ — Queues and Prefetch](https://www.rabbitmq.com/docs/queues) — unacked deliveries, prefetch, and consumer overload.
- [Spring Kafka — Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html) — record/listener observation.
