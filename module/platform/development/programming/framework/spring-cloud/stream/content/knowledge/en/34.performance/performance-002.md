# Measuring Bottlenecks at the Broker, Consumer, and Dependencies

A Spring Cloud Stream flow can be slow even when the processing function is very fast. A message may wait on producer sending, broker writing or distribution, consumer delivery, function execution, external dependency responses, and finally acknowledgement or commit. If you only measure function execution time, the operations team may optimize the wrong layer and make the system more complex without increasing throughput.

An effective measurement strategy starts with an end-to-end latency budget and breaks it down into observable intervals. Measure application processing time, broker wait time, dependency connection acquisition time, dependency response time, and message acknowledgement time separately. Then correlate application metrics with broker and dependency metrics to identify which layer is limiting throughput.

This lesson establishes a measurement and diagnostic workflow for Spring Cloud Stream with Kafka, RabbitMQ, or Pulsar. You will learn what to measure, which signals to read, how to design load tests, and how to choose fixes based on actual root causes.

## Learning Objectives

After this lesson, you can:

- Break down end-to-end latency into producer, broker, consumer, function, dependency, and acknowledgement segments.
- Distinguish processing time from queue wait time and consumer lag.
- Select p50, p95, p99, throughput, backlog, and oldest-message age metrics.
- Measure function and per-dependency processing time using Micrometer Observation.
- Read broker-specific metrics for Kafka, RabbitMQ, and Pulsar.
- Distinguish an under-concurrent consumer from a consumer blocked by I/O or dependencies.
- Use Little's Law to estimate backlog and wait time.
- Design load tests that reproduce bottlenecks.
- Choose optimizations based on evidence and re-verify with the same workload.

## 1. Viewing the entire path of a message

A message typically traverses the following stages:

1. Producer builds the payload, serializes it, and sends the request.
2. Broker receives the request, authenticates, routes, writes data, and replicates as configured.
3. Message sits in a topic/queue until a consumer can receive it.
4. Consumer fetches or receives the message, deserializes it, and dispatches it to the function.
5. Function executes business logic.
6. Function calls dependencies such as HTTP APIs, databases, caches, or object storage.
7. Consumer acknowledges or commits progress per the binder.
8. Broker updates delivery state and releases corresponding resources.

~~~mermaid
flowchart LR
    A["Producer<br/>serialize + send"] --> B["Broker<br/>accept + persist + route"]
    B --> C["Queue / partition<br/>waiting time"]
    C --> D["Consumer<br/>fetch + deserialize"]
    D --> E["Spring Cloud Stream<br/>function processing"]
    E --> F["Dependency<br/>HTTP / DB / cache"]
    F --> G["Ack / commit"]
    G --> H["Broker progress"]
~~~

End-to-end latency can be approximated as:

~~~text
T_end_to_end =
    T_producer
  + T_broker_accept
  + T_queue_wait
  + T_consumer_dispatch
  + T_deserialize
  + T_function
  + T_dependency_wait
  + T_dependency_service
  + T_ack_or_commit
~~~

Some intervals can overlap due to batching, asynchronous I/O, prefetch, or parallel processing. Therefore, do not add independent metrics together and treat the sum as an exact measurement. This model helps you ask the right questions and identify which layer needs deeper instrumentation.

### Distinguishing three commonly confused durations

- **Processing duration:** the time the function runs after receiving the message.
- **Queue wait / message age:** the time the message waits before the consumer starts processing it.
- **Consumer lag:** the consumer's progress delta behind the broker's latest data; usually measured in records or offsets, not directly in time.

A consumer lag of 10,000 records alone does not tell you whether a message waited 10 seconds or 10 minutes. You also need ingestion rate, processing rate, and the age of the oldest message to interpret it.

## 2. Establishing a latency budget and baseline

Before optimizing, define business goals. For example, 95% of orders must be processed within 2 seconds and 99% within 5 seconds. This is an end-to-end SLO, not a target for the function alone.

An illustrative latency budget:

| Stage | p95 budget |
|---|---:|
| Producer serialize + send | 50 ms |
| Broker accept/persist | 100 ms |
| Queue wait | 300 ms |
| Consumer dispatch + deserialize | 50 ms |
| Function logic | 100 ms |
| Pricing service | 250 ms |
| Database | 150 ms |
| Ack/commit and remainder | 100 ms |
| Total target budget | 1,100 ms |

This is an example of how to allocate a budget, not default numbers for every system. If a step's p95 exceeds its budget, measure p99 and inspect the distribution instead of looking only at the average.

### Minimum baseline

Over the same time window, record:

- Input rate and output/completion rate (messages/second).
- Processing duration p50, p95, p99.
- End-to-end message age p50, p95, p99.
- Consumer lag or queue backlog.
- Oldest message age.
- Retries, redeliveries, nacks, DLQ, and deserialization errors.
- CPU, memory, garbage collection, thread pools, and network.
- Broker request latency, disk/storage latency, replication/flow control.
- Dependency latency, connection-pool wait, and errors/timeouts.

Do not draw conclusions from a single instant snapshot. Compare time series over the same window with deployment markers and load changes.

## 3. Measuring each stage with timestamps and timers

To measure end-to-end age, messages should carry an event timestamp or a clearly defined publish timestamp. Example payload:

~~~java
import java.time.Instant;

public record OrderCreated(
    String eventId,
    String orderId,
    Instant occurredAt
) {}
~~~

At the consumer, record the start of processing. You can compute business event age:

~~~java
import java.time.Duration;

Duration eventAge = Duration.between(
    event.occurredAt(),
    Instant.now()
);
~~~

`eventAge` includes all time from when the business event occurred until the consumer processes it. It is not synonymous with queue wait. If the producer creates the event early and publishes later, the pre-publish wait is also included in this value.

To estimate queue wait, you need the publish timestamp provided by the broker/client or a publish-time header written by the producer right before sending. Kafka record timestamps, Pulsar publish times, and RabbitMQ timestamps/headers each have their own semantics. Verify whether the timestamp in use represents event creation, request send, or broker receipt.

### Clock skew and clocks

Comparing timestamps across multiple machines depends on system clocks. If the producer clock is 300 ms ahead of the consumer, wall-clock queue wait can be negative or skewed. Synchronize NTP/chrony across nodes and monitor clock offset. For durations within a single process, use a monotonic timer such as Micrometer `Timer` or `System.nanoTime()`, rather than subtracting two `Instant` values from a clock that can be adjusted.

### Measuring duration inside the application

Micrometer Observation can create spans and timers for individual business steps:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Service;

@Service
class PricingGateway {

    private final ObservationRegistry registry;
    private final PricingClient client;

    PricingGateway(ObservationRegistry registry, PricingClient client) {
        this.registry = registry;
        this.client = client;
    }

    Price quote(OrderCreated event) {
        return Observation.createNotStarted("orders.dependency.pricing", registry)
            .lowCardinalityKeyValue("dependency", "pricing")
            .lowCardinalityKeyValue("operation", "quote")
            .observe(() -> client.quote(event.orderId()));
    }
}
~~~

Wrap dependency calls in observations so traces separate function processing from the pricing call. If the HTTP client is already auto-instrumented, avoid creating duplicate spans; use the trace waterfall to verify instrumentation covers the intended layers.

Do not attach `eventId`, `orderId`, `customerId`, or URLs with dynamic IDs to metric tags. Those values have high cardinality. Keep them in controlled traces/logs; metrics should only use bounded labels such as function, dependency, operation, outcome, and region.

## 4. Measuring producer and broker sides

Producer send latency measures only part of the path. It may include serialization, buffer wait, retries, and waiting for broker response under the acknowledgement policy. A fast producer send does not prove the broker is handling backlog well: the broker may accept messages quickly while consumers read slowly.

### Producer metrics

- Messages sent per second.
- Send request latency p50/p95/p99.
- Serialization duration.
- Batch size and batch fill ratio.
- Retry count and send error rate.
- Request timeouts, buffer wait, and blocked time.
- Bytes in per second and compression ratio.

If send latency increases along with broker request latency, suspect the broker or network. If send latency increases while the broker is healthy, check serialization, producer buffers, batching, DNS/TLS, and client-side throttling.

### What to measure on the broker?

| Category | Questions |
|---|---|
| Request latency | How long does the broker take to receive and process produce/fetch requests? |
| Queue/request backlog | Are requests waiting in a queue at the broker? |
| Storage | Is disk/BookKeeper limiting write/read throughput? |
| Replication | Are replicas/ISR keeping up? |
| Network | Are network processors, sockets, and bandwidth saturated? |
| Flow control | Is the broker throttling or slowing down producers/consumers? |
| Resource | Are CPU, memory, page cache, disk IOPS, and file descriptors hitting limits? |

Do not look only at broker CPU. A broker can have low CPU while being bottlenecked by disk fsync, replication acknowledgement, network, or request queues.

## 5. Broker metrics by messaging system

### Apache Kafka

Common metric groups:

| Group | Metrics/Signals | Meaning |
|---|---|---|
| Traffic | BytesInPerSec, BytesOutPerSec, MessagesInPerSec | Inbound/outbound traffic |
| Request | RequestQueueTimeMs, LocalTimeMs, RemoteTimeMs, ResponseQueueTimeMs, ResponseSendTimeMs | Time across request processing stages |
| Broker capacity | RequestHandlerAvgIdlePercent, NetworkProcessorAvgIdlePercent | Idle ratio of request/network threads |
| Replication | UnderReplicatedPartitions, OfflinePartitionsCount, IsrShrinksPerSec | Replica and ISR health |
| Storage | Log flush latency, disk utilization, I/O wait | Log write capability |
| Client | Produce/Fetch latency, retry, request rate | Producer/consumer experience |

JMX metric names and MBean groups can vary across Kafka versions. Use the Kafka JMX/metrics docs for your exact version and your cluster's existing broker dashboards. Rising `RequestQueueTimeMs` indicates requests are queuing in the broker; high `RemoteTimeMs` may reflect replica wait or remote handling depending on request type.

If `UnderReplicatedPartitions` or `OfflinePartitionsCount` rises, do not simply push more producer throughput. Check disconnected brokers, slow disks, ISR shrinks, network, and replication first.

### RabbitMQ

Key metrics:

| Group | Metrics/Signals | Meaning |
|---|---|---|
| Ready | messages_ready | Messages waiting for consumers |
| Unacked | messages_unacknowledged | Delivered but not yet acked |
| Consumer | consumer count, consumer capacity | Consumer receive/processing capacity |
| Throughput | publish, deliver, ack rates | Ingress, delivery, and acknowledgement rates |
| Flow control | publisher flow, blocked connection | Broker is slowing down producers |
| Resource alarm | memory alarm, disk alarm | Broker is short on resources |
| Queue | queue length, ingress/egress, leader/replica health | Backlog and queue health |

Rising `messages_ready` alongside low `messages_unacknowledged` usually suggests consumers are not pulling enough or no consumers are active. High `messages_unacknowledged` can occur when consumers receive quickly but process slowly, prefetch is too high, or acks are delayed. Inspect consumer capacity and ack rate alongside queue depth.

For quorum queues, monitor leader, replicas, disk, and inter-node network. Queues with more replicas increase durability but also increase replication overhead.

### Apache Pulsar

Metric groups to watch:

| Group | Metrics/Signals | Meaning |
|---|---|---|
| Topic traffic | msgRateIn, msgRateOut, throughput in/out | Publish and dispatch rates |
| Subscription | backlog, unacked messages, redelivery | Backlog and redeliveries |
| Broker | Dispatch rate, consumer permits, broker load | Distribution capacity |
| Storage | BookKeeper read/write latency, journal latency, ledger errors | Storage latency |
| Resource | Broker CPU/memory, bookie disk, network | Cluster resources |
| Namespace | Backlog quota, dispatch/publish throttling | Namespace-level limits |

Exact metric names may be `pulsar_rate_in`, `pulsar_rate_out`, `pulsar_subscription_back_log`, `pulsar_subscription_unacked_messages`, or corresponding names for your release. Use the metrics endpoint and dashboards for your exact Pulsar release, as names and labels can change.

If `msgRateIn` exceeds `msgRateOut` over a sustained period and backlog grows, the consumer or dispatch path cannot keep up. If broker dispatch is slow along with high BookKeeper write/read latency, inspect storage nodes, journal/disk, and network before increasing consumer count.

## 6. Measuring the consumer: from fetch to ack

The consumer can be the bottleneck even when the broker is healthy. Measure these steps:

1. Time waiting to receive a message.
2. Fetch/poll and dispatch time.
3. Deserialization and message conversion.
4. Thread/worker wait time.
5. Function processing.
6. Dependency calls.
7. Ack/commit.
8. Retries or redeliveries.

Recommended metrics:

- Received rate and completed rate.
- Processing duration p50/p95/p99.
- Queue wait in internal executors.
- Consumer lag by partition/group.
- In-flight, unacked, or pending records.
- Ack/commit latency.
- Deserialization/conversion error rate.
- Retry/redelivery and DLQ rates.
- Effective concurrency and active consumers/threads.

### Consumer lag is not processing latency

With Kafka, per-partition lag is usually calculated as latest offset minus committed offset. Lag can grow because the producer sped up, a consumer stopped, the consumer processes slowly, or partition assignment is unbalanced. A single hot partition can create high lag even when throughput on all remaining partitions looks good.

Read all of the following:
- Per-partition lag, not just the total.
- Whether lag is growing or shrinking over time.
- Record processing rate vs. input rate.
- Oldest event age if timestamps are available.
- Rebalance count and downtime during rebalances.

With RabbitMQ and Pulsar, backlog/queue depth is the number of waiting messages, whereas unacked is messages delivered but not yet acknowledged. Do not call every backlog metric "Kafka consumer lag"; each broker has distinct semantics.

### Concurrency and partition limits

Increasing consumer concurrency only helps if there is enough partition/queue delivery capacity and downstream still has headroom. With Kafka, consumers in the same group exceeding the partition count will leave idle consumers. With RabbitMQ, multiple consumers can receive from the same queue, while prefetch and ack semantics affect distribution. With Pulsar, subscription type and consumer permits affect how the broker dispatches.

If a single partition holds most traffic due to key skew, adding consumers cannot split that partition across independent workers. Revisit key distribution, partition count, and business ordering requirements.

## 7. Measuring dependencies

A function may spend 80% of its time waiting on an HTTP API, database, or cache. In that situation, increasing consumer concurrency only creates more concurrent requests, overloading the dependency and increasing timeouts.

Measure at least:

| Dependency layer | Metrics to capture |
|---|---|
| HTTP/gRPC | Request duration, connect/TLS time, DNS, timeouts, retries, status codes |
| Connection pool | Active, idle, pending/acquire wait, max connections, connection churn |
| Database | Query duration, pool acquisition wait, lock wait, slow queries, transaction time |
| Cache | Command latency, hit/miss, connection wait, timeouts |
| Object storage | Request latency, throughput, throttling, retries |
| Thread/executor | Active threads, queue depth, rejected tasks, task wait time |

Separate time spent waiting for a connection from time spent by the server handling the request. For example, an HTTP call totaling 800 ms may consist of 650 ms waiting on the connection pool and only 150 ms over the network/server. Increasing timeouts will not fix pool saturation.

### Connection pool saturation

Common signs:
- Pending/acquire wait increases.
- Active connections hit max.
- Dependency service time does not rise correspondingly.
- Function threads wait for connections.
- Consumer lag rises subsequently.

Remediation direction:
- Check for connection leaks and connection hold times.
- Check whether pool max fits server limits.
- Shorten transaction/connection hold times.
- Use a bulkhead to bound concurrency.
- Increase the pool only if the dependency has capacity for more requests.

### Retry amplification

If every message retries multiple times while a dependency is failing, total requests sent to the dependency can exceed the input rate. This is retry amplification. Measure retry attempts, backoff time, timeouts, and actual requests hitting the dependency. Use exponential backoff with jitter, cap attempt counts, and apply circuit breakers/bulkheads where appropriate.

Retries do not replace a DLQ or permanent error handling workflow. A validation error should not be retried repeatedly like a transient network error.

## 8. Using traces to build a waterfall

Traces show where a single execution spent its time. A good waterfall should distinguish:

- Consumer receive/dispatch.
- Function invocation.
- Deserialization/conversion if instrumented.
- Dependency HTTP/DB spans.
- Output publishing.
- Ack/commit if instrumentable.

Example trace:

~~~text
orders.consume                         1,240 ms
  ├─ deserialize                          12 ms
  ├─ orders.process                      1,190 ms
  │   ├─ inventory.lookup                  35 ms
  │   ├─ pricing.http                     910 ms
  │   │   ├─ connection.acquire            680 ms
  │   │   └─ remote request                230 ms
  │   └─ orders.persist                   170 ms
  └─ ack/commit                            38 ms
~~~

In this example, the pricing dependency accounts for most of the time, and most of that is connection wait. Optimizing Java function code or increasing consumer concurrency will not fix the root cause.

Not every binder creates separate spans for broker enqueue, queue wait, and ack. When spans are missing, combine event timestamps, broker metrics, and application timers to infer wait intervals. Never name a span and treat it as broker time if instrumentation only measures client API time.

### Correlation ID and event ID

Keep `eventId` stable across retries and forwarding. Trace IDs change depending on propagation and sampling; `eventId` is used to locate the same event across logs/DLQ/replay. Do not use `eventId` as a metric label. Log binding, destination, consumer group, attempt, and outcome in structured logs.

## 9. Queueing theory and Little's Law

Little's Law describes the relationship in a stable system:

~~~text
L = λ × W
~~~

Where:
- `L`: average number of items in the system/queue.
- `λ`: average throughput (messages/second).
- `W`: average time an item spends in the system (seconds).

For example, if a flow receives 150 messages/second and average queue wait is 4 seconds:

~~~text
L = 150 × 4 = 600 messages
~~~

If the backlog grows to 6,000 messages while the input rate remains 150 messages/second, approximate queue wait can reach around 40 seconds under steady conditions and constant service rate. This is only an estimate; bursts, retries, multiple partitions, and parallel processing make the system more complex.

### Estimating consumer capacity

If one consumer stably processes 40 messages/second and there are 5 truly active workers, theoretical capacity is 200 messages/second. However, if a dependency can only sustain 120 requests/second, increasing workers to 10 may increase pending requests and timeouts instead of increasing throughput.

Always measure all of:
- Offered rate: rate producers submit.
- Accepted rate: rate the broker accepts.
- Delivered rate: rate the broker delivers to consumers.
- Completed rate: rate of successful processing.
- Acknowledged/committed rate: rate of progress confirmation.

If the accepted rate exceeds the completed rate over time, the backlog will grow. If the completed rate is high while the ack rate is low, investigate ack/commit and transaction boundaries.

## 10. Diagnosing by symptom

| Observed symptom | Suspected layer | Next check |
|---|---|---|
| Producer send latency rises, broker request queue rises | Broker or network | Request queue, network idle, disk, replication |
| Producer is slow but broker metrics are normal | Producer client | Serialization, buffers, DNS/TLS, retries, batching |
| Broker healthy, queue/backlog rises, consumer CPU high | Consumer compute | Function duration, GC, serialization, concurrency |
| Broker healthy, consumer CPU low, function duration high | Consumer waiting on I/O | Dependency traces, pool wait, network |
| Function duration low but message age high | Queue wait/dispatch | Lag, backlog, partition assignment, consumer capacity |
| RabbitMQ ready high, unacked low | Consumers not receiving enough | Consumer count, capacity, prefetch, connections |
| RabbitMQ unacked high | Consumer processing/ack slow | Processing time, prefetch, ack timeout, blocked workers |
| Pulsar backlog rises, dispatch rate low | Subscription/consumer dispatch | Consumer permits, subscription type, broker load |
| Pulsar backlog rises and BookKeeper latency high | Storage layer | Bookie disk, journal, network, ledger errors |
| Dependency p95 high and pool pending rises | Dependency client/server | Pool sizing, connection hold, service latency |
| Retries and redeliveries rise with dependency errors | Retry amplification | Backoff, timeouts, circuit breaker, DLQ |
| One partition lag much higher than others | Key skew/hot partition | Key distribution, partition count, event size |
| CPU low but latency high | I/O or queue wait | Pool wait, broker, network, locks |
| CPU/GC high and latency rises | Compute/allocation pressure | Serialization, compression, object churn, heap/GC |

Use symptoms as hypotheses to test, not automatic conclusions. A single metric is rarely enough to pinpoint the root cause.

## 11. Bottleneck investigation workflow

Proceed in order to avoid changing multiple variables at once:

1. Confirm which SLO is violated: end-to-end age, p95/p99, throughput, or backlog.
2. Pick a sample trace/message and build a waterfall.
3. Compare input rate, broker accepted/delivered rate, consumer completed rate, and ack rate.
4. Check backlog/lag by topic, partition, queue, or subscription.
5. Cross-check broker metrics: request latency, disk, replication, flow control, and resource alarms.
6. Check consumer concurrency, worker queues, processing duration, deserialization, and ack/commit.
7. Check dependency spans, connection pools, server latency, timeouts, and retries.
8. Form a hypothesis identifying one layer limiting throughput.
9. Change one variable, rerun the exact same workload, and compare results.
10. Verify you did not increase duplicates, message loss, DLQ rate, or downstream latency.

### Choosing windows and percentiles

- p50 represents the typical experience.
- p95 captures most slow requests.
- p99 helps uncover tail latency and rare events.
- Max is easily skewed by a single outlier; do not use it as the sole metric.
- Average can hide tail latency.

Use histograms so the backend can compute percentiles over query windows. Client-side percentiles cannot be accurately aggregated across multiple instances like histogram buckets. Choose buckets around your SLO, for example 50 ms, 100 ms, 250 ms, 500 ms, 1 s, and 2 s.

## 12. Designing load tests to find limits

Load tests need to reproduce real workloads, not just send a small payload for a few seconds.

### Preparation

- Use payloads with production-like sizes and schemas.
- Generate realistic key distributions, including hot keys if present.
- Use equivalent partition, queue, and subscription counts.
- Configure TLS, compression, batching, replication, and retention like the target environment.
- Use real dependencies or mocks with explicit latency/error profiles.
- Ensure brokers and consumers have resources comparable to production.

### Phases

1. **Warm-up:** initialize connections, caches, JIT, and consumer assignments.
2. **Ramp-up:** increase the offered rate in steps.
3. **Steady state:** hold load long enough for backlog and GC trends to show.
4. **Burst:** apply a short spike to observe queue absorption and recovery.
5. **Soak:** sustain load over a long period to detect leaks, disk growth, and retry accumulation.
6. **Failure test:** slow down a dependency, restart a consumer, or induce a broker/network interruption.
7. **Recovery:** restore the service and measure backlog drain time.

Record offered rate and completed rate side by side. A closed-loop load generator may automatically throttle itself when the system slows down, hiding backlog growth that would occur in production. For event-driven systems, use scenarios that keep a fixed offered rate or simulate bursts independently of response time.

### Change only one variable

For example, test consumer concurrency at 2, 4, 8, and 12 while keeping payload, broker, partitions, dependencies, and offered rate unchanged. Compare:
- Completed throughput.
- p95/p99 processing and end-to-end age.
- Lag/backlog and drain time.
- CPU/GC, network, and dependency pool wait.
- Retries, redeliveries, and errors.

If concurrency rises without throughput increasing, while pool pending rises, the dependency may be the limit. If consumers sit idle and partition count is low, broker assignment may be the limit.

## 13. Optimizing by root cause

### When the broker is the bottleneck

- Check disk IOPS/latency, network, and replication first.
- Check request queues and flow control.
- Check partition/queue count, leader placement, and hot partitions.
- Evaluate batching and compression with load tests.
- Check message size, retention, and storage growth.
- Increase brokers/partitions only when there is evidence resources or parallelism are limiting.

### When the consumer is the bottleneck

- Separate deserialization, function, and ack durations.
- Optimize algorithms, allocations, and batch size.
- Adjust concurrency to match partition/queue capacity.
- For Kafka, inspect partition assignment and poll/commit behavior.
- For RabbitMQ, tune prefetch to balance throughput against unacked memory.
- For Pulsar, check subscription type, receiver queue/permits, and dispatch.
- Avoid increasing concurrency if workers are waiting on the same dependency.

### When a dependency is the bottleneck

- Separate pool acquisition time from remote service time.
- Check connection reuse, DNS, TLS handshakes, and keep-alive.
- Set timeouts aligned with the latency budget.
- Use bulkheads to cap concurrent requests.
- Use circuit breakers and retries with backoff/jitter.
- Batch or cache where semantics allow.
- Reduce dependency calls by batching requests or pre-enriching data.
- Confirm dependency capacity before increasing pool size.

### When queue wait is the bottleneck

- Compare offered rate with completed rate.
- Verify the consumer has enough instances and partition/queue assignments.
- Look for hot keys or an overloaded queue/partition.
- Verify consumers are not paused by rebalances, flow control, or dependency timeouts.
- Scale consumers only when capacity exists and backlog can be distributed.

## 14. Example measurement interpretation

Suppose an experiment yields:

| Metric | Before tuning | After tuning |
|---|---:|---:|
| Input rate | 180 msg/s | 180 msg/s |
| Completed rate | 115 msg/s | 176 msg/s |
| Consumer p95 processing | 920 ms | 310 ms |
| Pricing pool wait p95 | 610 ms | 45 ms |
| Pricing service p95 | 180 ms | 175 ms |
| Queue oldest age | 42 s | 3 s |
| Error rate | 0.2% | 0.2% |

Traces showed pricing pool wait accounted for most of the duration. The engineering team shortened connection hold times and capped concurrency at what the dependency could sustain. Afterward, completed rate nearly matched input rate, queue age dropped, and processing time improved. Increasing consumer threads before fixing pool wait could have made things worse.

Another example: consumer p95 is low and CPU is low, yet oldest message age rises; broker metrics are normal and the consumer only receives one hot partition. In that case, analyze key distribution and partition strategy rather than optimizing function code.

## 15. Common performance measurement pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Measuring only function duration | Misses queue wait and broker delay | Measure end-to-end age, lag, and broker metrics |
| Using average instead of p95/p99 | Hides tail latency | Use histograms and percentiles |
| Treating lag as wait time | Misestimates latency | Track record lag and oldest-message age separately |
| Using wall clock to measure duration | Affected by clock adjustments | Use `Timer`/monotonic clock |
| Unsynchronized clocks across producer/consumer | Negative or skewed queue wait | NTP/chrony and verify timestamp semantics |
| Increasing consumer concurrency immediately | Overloads dependencies | Measure dependency pools and throughput first |
| Setting prefetch too high | High unacked memory and skewed distribution | Measure processing time and tune prefetch |
| Unbounded retries | Retry amplification and backlog | Backoff, cap attempts, DLQ |
| Running load tests too short | Misses backlog/GC/soak issues | Warm-up, steady-state, and soak tests |
| Changing multiple settings at once | Cannot tell which change caused the result | Change one variable at a time and save baseline |
| Putting IDs into metric tags | Cardinality explosion | Keep IDs only in traces/logs |
| Not measuring ack/commit | Confuses processing done with delivery completed | Track ack/commit rate and latency |

## 16. Lab: finding the bottleneck in function processOrder

Build a flow that receives `OrderCreated`, calls a Pricing API, writes to a database, and emits `OrderAccepted`.

1. Create an event containing `eventId` and `occurredAt`.
2. Measure producer send duration and publish rate.
3. Measure consumer processing duration with Observation/Micrometer.
4. Create child observations for the Pricing API and the database.
5. Record pool acquisition wait, HTTP/DB service time, and timeouts.
6. Monitor broker backlog/lag and oldest message age.
7. If using Kafka, collect per-partition lag and request/replication metrics.
8. If using RabbitMQ, collect ready, unacked, consumer capacity, and ack rate.
9. If using Pulsar, collect backlog, dispatch rate, unacked, and storage latency.
10. Run a baseline at low load, then step up the offered rate.
11. Slow down the Pricing API to observe pool wait, retries, and queue growth.
12. Increase consumer concurrency by one step and check whether the dependency saturates.
13. Reduce connection hold time or cap concurrency and rerun the same workload.
14. Compare p50/p95/p99, completed rate, backlog, and errors/redeliveries.
15. Write a report identifying the bottleneck layer, evidence, and effective changes.

Acceptance checklist:

| Item | Result to verify |
|---|---|
| End-to-end budget | SLO and per-stage latency budget documented |
| Timestamp | `occurredAt`, publish time, and processing start distinguished |
| Application timing | Function/dependency duration p50/p95/p99 captured |
| Broker metrics | Appropriate request/storage/replication or queue/backlog metrics collected |
| Consumer | Received/completed/ack rates and concurrency captured |
| Lag/backlog | Record lag, queue depth, and oldest age tracked separately |
| Dependency | Pool wait, remote latency, timeouts, and retries captured |
| Trace | Waterfall highlights the slowest span |
| Load test | Covers warm-up, ramp, steady-state, burst, soak, and failure |
| Capacity | Offered rate and completed rate compared |
| Cardinality | No event IDs used as metric labels |
| Recovery | Backlog drain and redeliveries verified after failure |
| Conclusion | Every change has a baseline and re-measured result |

## Conclusion

Measuring bottlenecks in Spring Cloud Stream requires observing the entire message path. Producer send latency, broker request/storage/replication, queue wait, consumer dispatch, function duration, dependency pool wait/service time, and ack/commit are all distinct intervals. Record-based consumer lag cannot replace oldest-message age; low function duration does not prove the flow meets its SLO.

Combine broker metrics with Micrometer Observation, trace waterfalls, and load tests with a controlled offered rate. Diagnose the broker, consumer, or dependency using multiple correlated signals, change one variable at a time, and rerun the same workload. Only increase concurrency or resources once you have confirmed that specific layer is actually limiting throughput; if a dependency or queue wait is the root cause, scaling consumers can make the system slower.

## References

- [Spring Cloud Stream 5.0.4 – Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html)
- [Spring Cloud Stream – Kafka Binder Metrics](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/metrics.html)
- [Apache Kafka – Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [RabbitMQ – Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [RabbitMQ – Consumers and Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch)
- [Apache Pulsar – Monitoring](https://pulsar.apache.org/docs/4.0.x/administration-metrics/)
- [Apache Pulsar – Concepts: Messaging](https://pulsar.apache.org/docs/4.0.x/concepts-messaging/)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry – Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
