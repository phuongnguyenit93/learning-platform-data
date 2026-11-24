# Backpressure from Downstream

In a Spring Kafka system, a consumer can read records faster than a downstream database, HTTP API, payment system, or internal service can process them. When that happens, increasing concurrency or retrying nonstop does not necessarily improve throughput: the application may exhaust connection pools, increase timeouts, trigger retry storms, and put even more pressure on the very dependency that is already degraded.

**Backpressure from downstream** is the mechanism of regulating the rate of fetching and processing Kafka records based on the actual capacity of dependent systems. The goal is not to keep consumer lag at 0 at all costs; the goal is **not accepting more work than can be processed safely**, while keeping the consumer group stable, preserving offsets, and resuming cleanly when downstream recovers.

In Spring Kafka, key tools include `MessageListenerContainer.pause()/resume()`, per-partition pause, `max.poll.records`, bounded concurrency, controlled retry/backoff, circuit breakers, and acknowledgment mechanisms. Each tool addresses a different layer. Pausing a Kafka consumer does not replace HTTP client timeouts, and a huge thread pool does not replace database load limits.

## 1. How does downstream overload manifest?

A pipeline can be pictured as follows:

```text
Kafka topic
    |
    v
Spring Kafka consumer
    |
    v
@KafkaListener
    |
    +--> Database / connection pool
    |
    +--> Payment/Inventory HTTP API
    |
    +--> Worker queue / thread pool
    |
    v
Business outcome + offset commit
```

If records arrive from Kafka faster than downstream completes them, the unfinished work must sit somewhere: in the Kafka log, in polled record batches, in an internal queue, in pending HTTP requests, or in the database pool. **Where the backlog sits determines the risk**.

| Where work accumulates | Symptom | Primary risk |
|---|---|---|
| Kafka topic | Consumer lag increases | Higher latency; subject to broker retention and storage limits |
| Polled records in consumer | Duration between two `poll()` calls lengthens | Exceeds `max.poll.interval.ms`, triggers rebalance |
| In-application queue | Queue depth and heap grow | OOM, GC pauses, task loss on restart if non-durable |
| In-flight HTTP/database calls | Latency, timeouts, and pool waiting increase | Downstream saturates, cascading failures |
| Retry topic or DLT | Error backlog grows rapidly | Requires additional recovery and replay capacity |

For workloads with fluctuating traffic, the Kafka log is typically a **more durable and controllable** buffer than an unbounded queue inside the JVM. Intentionally letting consumer lag grow for a period can be safer than trying to keep lag low by firing thousands of concurrent requests at an overloaded database.

## 2. Measuring arrival rate, processing rate, and recovery time

Let `λ` be the record arrival rate and `μ` be the sustainable downstream success processing rate, in records/second. When `λ > μ`, backlog grows; only when `μ > λ` can the system reduce backlog.

```text
Backlog growth per second ≈ max(0, λ - μ)

Example:
  Kafka receives 1,200 records/second
  Downstream processes 800 records/second
  Backlog grows by about 400 records/second
  After one minute, ~24,000 additional records are waiting
```

This is a simplified model: batching, partition distribution, retries, and business errors cause real rates to fluctuate. Yet it highlights a critical truth: **pause does not create new downstream capacity**. Pause prevents cascading overload and keeps work in Kafka; after resume, shrinking the backlog requires total processing capacity to exceed the inbound event rate.

Beyond record count, account for **payload size**, CPU cost, number of queries/transactions, connection hold time, and API rate quotas. Two records of identical byte size can consume vastly different downstream capacity. Therefore, backpressure should rely on real health signals rather than a single static lag threshold.

## 3. Choosing signals to detect downstream saturation

Good backpressure signals measure capacity closest to the bottleneck:

| Signal | Meaning | Notes |
|---|---|---|
| HTTP `429 Too Many Requests` | Dependency is enforcing rate limits | Read `Retry-After` when present; do not retry immediately at the same rate |
| HTTP `503`/timeouts increasing | Dependent service may be overloaded or failing | Combine with latency, circuit breaker, and root-cause checks |
| Database pool active/max | Connection pool nearing exhaustion | Sustained high active count may stem from slow queries or lock-holding transactions |
| Queue occupancy | Pending tasks near max capacity | Valid only if the queue is **bounded** and completion is tracked |
| In-flight request count | Tasks occupying resources | Compare against actual concurrency limit downstream can sustain |
| p95/p99 latency | Processing time climbs under load | Often alerts before all requests begin timing out |
| Circuit breaker state | Dependency isolated after high error rate | Requires half-open policy and conditional recovery |
| Consumer lag | Processing rate lower than arrival rate | **An effect**, not always the cause of downstream saturation |

For instance, a 50-connection pool with 49 connections active and 500 queued requests is a much clearer signal than merely seeing Kafka lag climb. Conversely, high Kafka lag might reflect an incomplete deployment or a backfill backlog while the database still has ample headroom. Do not pause further solely because lag is high.

Measure error rates and latency over a sufficiently stable window. A single timeout does not necessarily demand pausing the entire listener; however, rising `429`s, climbing p99 latency, and a nearly full queue occurring together signal an immediate need to shed load.

## 4. Backpressure control layers

There is no single switch suitable for every kind of pressure. Mechanisms should be coordinated by goal:

| Mechanism | What does it control? | When is it appropriate? |
|---|---|---|
| `max.poll.records` | Number of records returned per poll | Limit work held inside a synchronous processing loop |
| Listener concurrency | Number of child consumer containers running in parallel | Balance partition parallelism with downstream capacity |
| Bounded worker pool / semaphore | Concurrent tasks inside the application | Prevent piling work into queues or APIs beyond thresholds |
| Container `pause()`/`resume()` | Temporarily halt fetching new records for the listener | Prolonged downstream overload or waiting for recovery |
| Per-partition pause | Halt only a specific partition | One tenant/key/partition creates abnormal load or needs isolation |
| Blocking retry/backoff | Retry failed records on a schedule | Transient errors where in-partition ordering must be preserved |
| `@RetryableTopic` | Move records to retry topics | Long retries without blocking the main topic; accepts ordering changes |
| Circuit breaker/rate limiter | Reduce outbound calls to downstream | Dependency has quotas or outages requiring retry-storm avoidance |

**Admission control** is the unifying principle: accept more work only when capacity exists to finish it, or a clear durable buffer is in place. If additional work cannot be accepted safely, keeping records in Kafka is usually far better than enqueueing unboundedly and committing offsets prematurely.

## 5. `pause()` and `resume()` on a Spring Kafka listener container

Spring Kafka provides listener-container-level APIs to request pause and resume. For containers managed by `@KafkaListener`, retrieve the container via `KafkaListenerEndpointRegistry` using the listener ID:

```java
@KafkaListener(
        id = "orderProcessor",
        topics = "orders",
        groupId = "order-service",
        containerFactory = "orderListenerContainerFactory")
public void consume(OrderCreated event) {
    orderService.processIdempotently(event);
}
```

An operations component can invoke:

```java
@Component
public class OrderConsumerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderConsumerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderProcessor");
        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resume() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderProcessor");
        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
```

Calling the container API from a coordinating thread is supported; the container safely executes the consumer operation within its lifecycle. **Do not call `KafkaConsumer.pause()` directly from an arbitrary HTTP or scheduler thread**: the Kafka consumer is not thread-safe.

After requesting `pause()`, the container usually completes records already received in the previous poll before applying the pause. Thus pause **does not cancel running work** and may not take effect immediately if a listener blocks for a long time. The container exposes states such as `isPauseRequested()` and `isConsumerPaused()` to distinguish a requested pause from the Kafka consumer actually being paused.

Starting in Spring Kafka 2.9, the `pauseImmediate` option allows the pause to take effect after the current record rather than processing all remaining records from the prior poll; remaining records are held by the container to process on resume. This is a trade-off between pause latency and memory; check version support and test before using.

## 6. Crucial rule: pausing must not stop polling

In Kafka, `pause()` stops the consumer from fetching new records from paused partitions, **yet the application must still maintain the `poll()` loop** to keep consumer group membership and heartbeats alive. Spring Kafka listener containers continue polling while paused so they do not trigger a group timeout merely from temporarily shedding load.

```text
When downstream is overloaded:

Container.pause()
       |
       v
Consumer stops receiving new records
       |
       v
Container keeps polling per Kafka lifecycle
       |
       v
Keeps membership/heartbeat; does not commit unprocessed records
       |
       v
Downstream recovers -> Container.resume()
```

Do not confuse pause with `Thread.sleep(10 * 60_000)` inside `@KafkaListener`. If the listener blocks the consumer thread past `max.poll.interval.ms`, Kafka may consider the member stalled, triggering a rebalance and redelivery. Pause protects membership only while **the container still gets a chance to poll**. A hung HTTP call inside the listener does not magically become non-blocking by calling `pause()`.

For a listener processing large batches, pause may take effect after the current batch finishes. If you need to cap processing duration before the next poll, tune `max.poll.records`, downstream timeouts, retry budgets, and select `pauseImmediate` appropriately.

## 7. Automatic backpressure with hysteresis

If you pause as soon as queue occupancy crosses 80% and resume as soon as it dips to 79%, the container can oscillate between pause and resume nonstop. **Hysteresis** uses a high threshold to stop taking work and a low threshold to reopen intake, avoiding oscillation when load hovers near a boundary.

Example:

```text
Queue usage >= 80%   -> request PAUSE
Queue usage <= 40%   -> eligible to RESUME
40% < queue < 80%    -> keep current state

Circuit breaker OPEN -> keep PAUSED even if queue drops
Circuit breaker CLOSED and queue low -> eligible to RESUME
```

An illustrative policy in Spring, with occupancy metrics supplied by the application:

```java
public record DownstreamSnapshot(
        double queueUsage,
        double poolUsage,
        boolean circuitOpen) {

    public boolean shouldPause() {
        return circuitOpen || queueUsage >= 0.80 || poolUsage >= 0.90;
    }

    public boolean canResume() {
        return !circuitOpen && queueUsage <= 0.40 && poolUsage <= 0.60;
    }
}

public interface DownstreamLoadProbe {
    DownstreamSnapshot snapshot();
}

@Component
public class OrderBackpressureCoordinator {

    private final KafkaListenerEndpointRegistry registry;
    private final DownstreamLoadProbe probe;

    public OrderBackpressureCoordinator(
            KafkaListenerEndpointRegistry registry,
            DownstreamLoadProbe probe) {
        this.registry = registry;
        this.probe = probe;
    }

    @Scheduled(fixedDelayString =
            "${app.orders.backpressure.check-ms:1000}")
    public void adjust() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderProcessor");
        if (container == null || !container.isRunning()) {
            return;
        }

        DownstreamSnapshot load = probe.snapshot();
        if (load.shouldPause() && !container.isPauseRequested()) {
            container.pause();
        }
        else if (load.canResume() && container.isPauseRequested()) {
            container.resume();
        }
    }
}
```

The code above illustrates the **coordination policy**, not a complete implementation of `DownstreamLoadProbe`: the application must gather figures from actual bounded queues, connection pools, bulkheads/circuit breakers, or API quotas. `queueUsage` and `poolUsage` are assumed in the range 0..1. Enable scheduling via `@EnableScheduling` in Spring configuration and avoid slow/blocking probe calls inside the scheduler. Thresholds must be calibrated against real metrics rather than treating 80%/40% as Spring Kafka defaults.

In production, add a minimum pause duration, a sustained healthy window before resuming, state-change event logs, probe exception handling, and alerts if paused too long. If the probe cannot reach the dependency, establish a clear **fail-safe** policy: do not treat a metric-collection error as evidence that downstream recovered.

## 8. Pause the whole container or pause a single partition?

When overload affects the entire dependency (such as a shared database running out of connections), pausing the entire container is usually straightforward. When load is isolated per tenant or one partition has heavy records, Spring Kafka provides **per-partition pause/resume** APIs in supporting versions.

```java
MessageListenerContainer container =
        registry.getListenerContainer("orderProcessor");

TopicPartition busyPartition = new TopicPartition("orders", 2);
container.pausePartition(busyPartition);

// Once the cause is resolved and sufficient capacity exists:
container.resumePartition(busyPartition);
```

This example only makes sense if the container owns the relevant partition; with high listener concurrency, the parent container may have to route the operation to a child container. Exact APIs and semantics depend on the Spring Kafka version. When a rebalance changes ownership, the coordinator must update partition state instead of continuing to assume partition 2 always belongs to the current instance.

Pausing a partition **does not redistribute that partition to another consumer**. A paused consumer keeps its assignment while the group remains stable; that is useful for avoiding extra rebalances, yet it also means throughput on the paused partition stays at 0 until resumed or ownership changes for another reason.

If downstream is a shared service and every partition calls that same dependency, pausing only the highest-load partition may not be enough. If a single tenant spread across multiple partitions causes overload, enforce per-tenant quotas/admission control at the business layer rather than assuming one partition corresponds to one tenant.

## 9. `max.poll.records`: limiting work accepted in a single loop

When a container pauses, records already returned by `poll()` may still be waiting for processing in the current loop. Therefore, if each record makes a slow downstream call, reducing `max.poll.records` is an important complementary step.

```properties
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.max-poll-records=50
spring.kafka.consumer.properties[max.poll.interval.ms]=300000

spring.kafka.listener.ack-mode=record
```

For example, if a poll contains 500 records and each record takes 800 ms to complete, total processing time can be roughly 400 seconds, exceeding the default 300-second `max.poll.interval.ms`. Capping polls at 50 records reduces that same workload to roughly 40 seconds per processing loop before returning to poll, excluding overhead. This is a budgeting estimate, not a latency guarantee, since requests vary in tail latency and error retries.

`max.poll.records` caps the count of records returned per `poll()`, **not the total bytes the Kafka client can fetch/cache internally**. For large payloads, also review `max.partition.fetch.bytes`, `fetch.max.bytes`, memory, and batch sizes. Do not simply lower the record count and conclude heap is under control.

Increasing `max.poll.interval.ms` gives the consumer more time to finish a processing loop, at a cost: a genuinely stuck member can hold partitions longer before the group reassigns them. Set the limit based on the listener's p99/worst-case behavior rather than raising it indefinitely to mask an overloaded dependency.

## 10. Bounded concurrency and bounded queues

An anti-pattern is reading Kafka records and pushing them onto an unbounded `ExecutorService` or queue:

```java
@KafkaListener(topics = "orders")
public void consume(OrderCreated event) {
    executor.execute(() -> orderService.process(event));
    // Method returns: container may assume the record is complete.
}
```

If the listener uses an automatic ack mode, returning from the method before the async task finishes can cause offsets to commit prematurely. A process crash after commit but before worker completion creates a risk of **losing business processing**. With an unbounded queue, pending tasks can also exhaust the heap.

A safe intake model must **bound** both running and queued work. For instance, set a semaphore of 32 in-flight requests, queue capacity of 100, HTTP timeout of 5 seconds, and pause when thresholds are breached. However, a semaphore only throttles downstream calls if the code **does not turn the record into a background task and ack early**.

There are two implementation paths:

1. **Synchronous listener, bounded processing:** keep work on the consumer thread; control `max.poll.records`, timeouts, retries, and pause before overload spreads. Simpler for offsets, though throughput can be constrained by per-record duration.
2. **Async with tracking/ack:** hand tasks to a bounded executor; acknowledge only when tasks complete durably, manage offsets per partition and ordering, apply backpressure as in-flight grows, and handle failed futures. Use async ack capabilities matching your Spring Kafka version and test redelivery/rebalance.

Do not call `BlockingQueue.put()` indefinitely inside the consumer thread when the queue is full: that call causes a poll timeout instead. If admission control rejects a task, have a strategy ensuring the record is not acked and will be retried/retained safely. Never silently swallow `RejectedExecutionException` and let the listener finish normally.

## 11. Acks and offsets: never treat queueing as successful processing

Backpressure is a **rate** concern, whereas acknowledgment is a **progress correctness** concern. A record should only be marked complete once all mandatory side effects have executed or the record has been durably recovered per defined policy.

| Scenario | Correct offset action in principle |
|---|---|
| Downstream succeeds and side effects are durable | Allow commit per ack mode |
| Downstream returns `429` or temporary timeout | Do not ack as successful; retry/backoff or controlled pause |
| Permanently invalid payload | Recover/DLT per policy; advance offset only once recovery succeeds |
| Async task merely enqueued, not yet run | Do not treat as processed |
| DB side effect committed, Kafka offset not yet committed | May redeliver; use idempotent consumer/inbox |

With `AckMode.RECORD`, the container typically commits after each record the listener processes successfully. With manual acknowledgment (`MANUAL`, `MANUAL_IMMEDIATE`), the application must call `acknowledge()` strictly after work completes. In async processing, in-order or out-of-order acks require the container's matching mechanism; do not assume you can commit an arbitrary offset and skip earlier ones.

Some Spring Kafka versions support `asyncAcks`, allowing out-of-order acknowledgments within a single poll while requiring the container to wait for missing acks before advancing. This can keep the consumer paused while in-flight tasks remain unfinished; bounded processing, handling hung tasks, and tracking pending acknowledgments are essential. This mechanism does not replace verifying that data was durably persisted.

## 12. Downstream returns errors: retry, pause, or DLT?

When a dependency returns errors, choose the response according to **error recoverability**:

| Scenario | Suggested response |
|---|---|
| HTTP `429` with `Retry-After` | Slow down, honor wait duration; consider controlled pause and retry |
| Temporary HTTP `503`, database pool nearly full | Bounded backoff, pause on overload signals, circuit breaker |
| A record with data/schema error unfixable by retry | Do not retry fruitlessly; send to DLT/quarantine with source metadata |
| Prolonged downstream outage | Pause consumer or use retry topics if ordering permits; alert on outage duration |
| Valid business rule rejection | Handle as a business outcome; do not send to DLT merely because it did not succeed |

Do not send **every record** to the DLT simply because a database has a long outage. A DLT is for records that cannot be processed per policy, not a place to dump the entire workload from a consumer when downstream temporarily loses capacity. If the dependency recovers after 10 minutes, keeping the backlog in Kafka and resuming carefully can be simpler than pushing millions of records to a DLT and replaying them.

Conversely, a permanently poisoned record can block progress if retried infinitely. Proper non-retryable classification and DLT recovery prevent valid records behind it from being stalled.

## 13. Combining `DefaultErrorHandler` with container-pausing backoff

If transient errors require a long backoff, `DefaultErrorHandler` can use a `BackOffHandler` that supports pausing the container to keep polling during the wait. Spring Kafka provides `ContainerPausingBackOffHandler` in supporting versions to avoid letting the consumer thread sleep long enough to breach `max.poll.interval.ms`.

Illustrative example:

```java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate,
        KafkaListenerEndpointRegistry registry) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    BackOff backOff = new FixedBackOff(30_000L, 3L);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            backOff,
            new ContainerPausingBackOffHandler(registry));

    handler.addNotRetryableExceptions(
            InvalidOrderPayloadException.class);

    return handler;
}
```

Here `InvalidOrderPayloadException` is an application-defined domain class; configure appropriate DLT serializers/ACLs/partitions and attach `handler` to the right listener container factory. Constructor APIs and backoff behavior should be checked against your Spring Kafka version. `FixedBackOff(30_000L, 3L)` represents up to three retry attempts after the initial delivery for retryable errors, assuming no reset policy alters the cycle.

**Distinguish two goals:** a metrics-driven `pause()/resume()` coordinator controls **overall load**, whereas `ContainerPausingBackOffHandler` implements **backoff for a failed record** inside the error handler. When using both, design clear resume authority so a controller does not call `resume()` while the error mechanism still needs the container paused. You can assign a single pause owner or coordinate multi-reason pause state before resuming.

## 14. `@RetryableTopic` and freeing the main topic

Non-blocking retry via `@RetryableTopic` can fit when a record needs a long wait for downstream recovery while the service still wants to process other records on the main topic.

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 5_000, multiplier = 2.0),
        exclude = {InvalidOrderPayloadException.class},
        dltTopicSuffix = "-dlt")
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderCreated event) {
    orderService.processIdempotently(event);
}
```

A failed record is routed through retry topics according to the topology Spring Kafka creates. The main topic can keep advancing instead of blocking a partition across each retry. **This can break per-key processing order**: a later record can complete before an earlier record sitting in a retry topic. If downstream requires sequential state, use state versioning, idempotency, or choose blocking retries instead.

Non-blocking retry also does not solve **system-wide** overload if every record calls the same rate-limited API. If most records get pushed into retry topics, traffic can come back all at once and create another retry storm. You need rate limiters, proper jitter/backoff, circuit breakers, retry-consumer throughput caps, and backlog monitoring across **both main and retry topics**.

## 15. Concurrency, partitions, and global downstream capacity

A setting of `concurrency=8` can spin up to eight consumer threads per instance, yet total downstream load also depends on **instance count, partition count, and concurrency inside each listener**.

For example, with four application replicas, concurrency 5 per replica, and each record opening at most one synchronous HTTP request, when enough partitions exist and all consumers are busy, concurrent requests can reach around 20. If each listener also spawns ten async tasks, total pressure can climb much faster.

```text
4 replicas × 5 consumer threads = up to 20 concurrent listener calls

If each listener spawns 10 async requests:
  can generate up to 200 concurrent requests (without further limits)
```

Downstream capacity is a **shared limit**, not a quota each replica gets to spend in full on its own. If an API only permits 100 requests/second globally, four replicas each enforcing a local 100 requests/second limiter can send up to 400 requests/second. Partition quotas or use a distributed rate limiter when quotas are truly global.

Pausing a container is a local action on the invoked instance/container; it does not broadcast a stop request to the entire consumer group. Other replicas can keep consuming and calling downstream. For global overload, establish consistent signals/policies across replicas. Avoid letting all replicas resume at full blast simultaneously when a circuit breaker turns half-open; use gradual ramp-up or stepped concurrency caps.

## 16. Shutdown, rebalance, and retries while paused

Pause does not guarantee a partition stays on the same instance forever. Rolling deployments, network drops, group membership changes, or rebalances can still revoke and reassign partitions. When that occurs, records already polled but not committed may be redelivered.

Implications to note:

- Pause is a control state **on the running container inside the JVM**, not a durable flag stored in the Kafka log.
- Upon restart, the container initializes fresh; the backpressure policy must evaluate downstream before taking heavy load.
- Upon shutdown, drain already-accepted work, stop accepting new work, and commit offsets accurately per completion state.
- After rebalance, only pause/resume partitions the container actually owns; observe lifecycle/callbacks as needed.
- If a DB side effect succeeded yet the offset failed to commit before shutdown, redelivery can occur; handling must be idempotent.

During deployments, avoid flapping pause/resume because health checks or HPA may misread the consumer. Distinguish **liveness** (whether the process is alive) from **readiness/capacity** (whether the instance should take more work). A consumer intentionally paused due to downstream overload is not necessarily dead; blindly restarting every pod just because lag increased can worsen load.

## 17. Monitoring and alerting for safe control

Backpressure must be observed as an intentional operational state, not an error hidden behind rising consumer lag. A minimal dashboard should track:

| Metric / signal | Diagnostic value |
|---|---|
| Consumer lag per topic/group/partition | Backlog waiting in Kafka |
| Age of oldest unprocessed record | Business latency caused by backlog |
| Pause requested / consumer paused | Whether container is waiting to pause or actually paused |
| Pause duration and pause count | Are prolonged pauses or continuous oscillations occurring? |
| Listener processing p95/p99 | Work duration per record/batch |
| In-flight requests and queue occupancy | How much headroom downstream has left |
| HTTP 429/503, timeout rate | Dependency rejecting or failing to handle more requests |
| DB pool active/idle/pending | Connection and query bottlenecks |
| Time-between-poll max / rebalance | Is the consumer at risk of exceeding `max.poll.interval.ms`? |
| Retry rate, retry-topic lag, DLT rate | Did failure pressure shift into another topology? |

Never use event IDs, offsets, or request IDs as metric labels due to high cardinality. Keep them in controlled logs/traces/audits. State-change logs should include listener ID, consumer group, reason, observed threshold, pause/resume timestamps, backlog, and duration. If multiple factors keep a container paused, log clearly **which reasons remain active** before resuming.

A good alert is not merely "lag is high"; for example: consumer paused over 15 minutes, downstream p99 still elevated, oldest event age breaching SLO, and retry rate climbing. Conversely, a brief pause helping the database recover followed by fast lag drain after resume can be normal backpressure behavior.

## 18. Common failure scenarios

| Symptom | Possible cause | Remediation |
|---|---|---|
| Called `pause()` yet listener keeps processing more records | Container still has records from prior poll; pause not yet effective | Distinguish pause requested/paused, lower `max.poll.records`, consider `pauseImmediate` |
| Consumer rebalanced while "paused" | Listener blocked the thread too long or code used `sleep()` instead of container pause | Ensure container keeps polling, bound processing duration and backoff |
| Downstream gets flooded with `429` right after resume | No hysteresis, too many concurrent requests reopened at once | Reduce initial load, add ramp-up, rate limiter, and lower resume threshold |
| Queue grows while lag stays low | Listener pushes tasks to queue and acks/commits too early | Design bounded queue and ack only after downstream completes |
| CPU/heap spike during overload | Unbounded queue, backlog held inside JVM | Push pressure back to Kafka; bounded admission and smaller poll batches |
| DLT spikes during DB outage | Retry budget too short or all timeouts classified as terminal | Separate transient failures from poison records, use proper pause/backoff |
| Consumer paused yet another group still hits the API | Pause acts locally only, does not control the whole cluster | Coordinate global quotas/health and rate limiters across replicas |
| Individual partition still lags after recovery | Partition pause not resumed or ownership changed | Inspect partition pause state, assignment/rebalance, and coordinate resume |
| Duplicate record processing after restart | DB committed but offset did not commit | Inbox/idempotency and monitor offset recovery |
| Kafka lag does not drop after downstream recovers | Processing capacity ≤ arrival rate, low concurrency, or controller never resumed | Measure arrival/processing rates, check pause state, and scale appropriately |

During incidents, correlate Kafka lag with in-flight/queue depth and downstream errors to locate where the backlog sits. Reflexively raising `max.poll.interval.ms` or adding pods without knowing where new downstream capacity comes from can bring down the dependent system faster.

## 19. Testing backpressure from downstream

A valuable integration test suite should include a Kafka broker, a controllable fake downstream capable of changing latency/quotas, and observations of committed offsets alongside container state. Key scenarios:

1. **Healthy downstream:** listener receives and processes records normally, never pausing spuriously.
2. **Queue crosses high threshold:** controller requests pause; verify container reaches paused state and receives no new batches.
3. **Queue in the band between thresholds:** retain current state, no pause/resume oscillation.
4. **Downstream recovers:** queue drops below low threshold, circuit closes; container resumes and drains backlog.
5. **HTTP 429/Retry-After:** verify rate limit/backoff, no request storms, and failed records are not acked.
6. **One listener blocks for a long time:** measure `max.poll.interval.ms`; verify pause cannot mask a hung synchronous call.
7. **Async task fails:** offset must not commit before side effects complete, and future failures are not swallowed.
8. **Restart while paused:** uncommitted records are redelivered per Kafka offsets; idempotency protects side effects.
9. **Rebalance with heavy in-flight:** partition ownership updates cleanly without uncontrolled continued processing.
10. **DLT and retries:** permanent errors recover properly; transient outages do not dump the entire backlog into DLT against policy.
11. **Multi-replica:** aggregate request rate does not exceed global quota when instances resume together.
12. **Large backlog:** catches up with inbound load after downstream recovery without heap spikes.

In tests, measure both the **Kafka side** (topic, partition, committed offset, lag) and the **downstream side** (request count, completions, timeouts, unique event IDs). Checking `isConsumerPaused()` alone without verifying no records were lost or committed early is insufficient.

## 20. Runbook when downstream is overloaded

A production incident response procedure can follow this order:

1. **Scope the impact:** cluster, topic, consumer group, listener ID, which dependency is failing, how many instances are affected.
2. **Locate the bottleneck:** measure pool usage, queue depth, 429/503s, latency, and error rates; distinguish systemic failures from poison records.
3. **Relieve pressure:** pause the appropriate container/partition or engage circuit/rate limiters; never hold consumer threads with long `sleep()` calls.
4. **Protect offsets:** verify acknowledgments occur only after side effects or recovery succeed; preserve idempotency.
5. **Reduce in-flight:** constrain queues, concurrency, `max.poll.records`, and downstream timeouts if needed.
6. **Fix the dependency:** restore the database/API, adjust pools/indexes/quotas, or roll back a faulty release.
7. **Assess recovery capacity:** ensure post-resume processing rate can exceed event arrival rate if draining backlog is required.
8. **Controlled resume:** wait for healthy signals long enough, ramp load up gradually; do not unleash all replicas at maximum capacity simultaneously.
9. **Post-resume monitoring:** lag, oldest age, p99, request errors, retry-topic/DLT backlogs, and rebalances must trend safely.
10. **Close the incident:** document thresholds, pause reason, duration, recovered data, remaining backlog, and preventive actions.

Never reset consumer group offsets to "reduce lag" without an approved data-handling plan; advancing offsets skips records, while rewinding creates duplicates. Do not increase retention, partitions, or concurrency as a knee-jerk fix without knowing where additional downstream capacity is coming from.

## 21. Production design principles

1. Backpressure is regulating **work intake rate** to match downstream capacity, not trying to zero out all consumer lag.
2. Prefer keeping durable backlog in Kafka rather than building unbounded queues inside the JVM.
3. Choose overload signals from queues, pools, latency, 429/503s, and circuit breakers; do not rely solely on lag.
4. Use `MessageListenerContainer.pause()/resume()` via container APIs, never manipulate `KafkaConsumer` from other threads.
5. Pause is safe for group membership only when the container keeps polling; blocking listeners need their own timeouts.
6. Use hysteresis and sustained healthy windows to avoid continuous pause/resume flapping.
7. Pair pause with `max.poll.records`, bounded concurrency, and memory limits to avoid pulling too many records before pause takes effect.
8. Ack only after downstream processing succeeds or recovery completes durably; async enqueueing is not business completion.
9. Distinguish transient errors from permanent errors when choosing retry, pause, or DLT; avoid retry storms and DLT storms.
10. Calculate total capacity/limits across **all replicas**, never assuming a per-pod rate limit is a system-wide rate limit.
11. Design idempotency for redelivery after rebalance, restart, or failed offset commits.
12. Observe pause duration, poll interval, lag, oldest event age, and downstream health; test recovery as a real failure mode.

**Conclusion:** downstream backpressure is a core pillar of reliable Spring Kafka operations. Consumers must know **when to stop taking more work**, **when it is safe to accept work again**, and **which records have truly completed before committing offsets**. By combining poll-preserving pause/resume, in-flight limits, timeouts, controlled retries, idempotency, and SLO-aligned observability, systems can weather database/API overload waves without turning them into data loss, uncontrolled duplicates, or continuous consumer group rebalances.
