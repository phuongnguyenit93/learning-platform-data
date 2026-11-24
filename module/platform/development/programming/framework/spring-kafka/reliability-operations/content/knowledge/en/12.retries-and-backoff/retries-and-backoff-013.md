# Monitoring Retry Latency in Spring Kafka

In a Spring Kafka consumer, retry latency is the additional time a record incurs when processing fails and is retried. Tracking this metric helps distinguish whether a service is slow because **business logic takes long**, because of **backoff waits**, because **records are sitting in retry topics**, or because **the Kafka consumer is backlogged**. This distinction is critical when designing SLOs, alerts, dashboards, and incident response procedures.

No single metric named "retry latency" suffices to describe every scenario. For a reliable system, define exact start points, end points, success cases, and cases routed to the DLT. Also recognize the two common retry models in Spring Kafka: retrying inside the listener container with `DefaultErrorHandler`, and retrying via separate topics with `@RetryableTopic`.

This lesson focuses on designing and interpreting latency measurements, collecting metrics and traces, observing retries per attempt, and avoiding common operational misinterpretations.

## 1. First, define latency accurately

A record can pass through many timestamps:

```text
Producer sends event           10:00:00.000
    |
Kafka stores event             10:00:00.040
    |
Consumer starts attempt 1      10:00:00.140
    |  Processing 120 ms -> error
Retry wait starts              10:00:00.260
    |  Wait 1,000 ms
Consumer starts attempt 2      10:00:01.260
    |  Processing 180 ms -> error
Retry wait starts              10:00:01.440
    |  Wait 2,000 ms
Consumer starts attempt 3      10:00:03.440
    |  Processing 160 ms -> success
Business work complete         10:00:03.600
    |
Offset committed               afterward
```

From this single journey, different metrics can be computed:

| Metric | Start → end boundary | Value in example | Interpretation |
|---|---|---:|---|
| Attempt processing latency | Start → end of one listener invocation | 120, 180, 160 ms | Processing time per attempt |
| Retry wait / backoff | One failure → next attempt | 1,000 and 2,000 ms | Time the record waits between attempts |
| Total retry wait | Sum of retry wait intervals | 3,000 ms | Planned waiting portion |
| Time from first attempt to success | First invocation → business completion | 3,460 ms | Total processing and retry wait time |
| Event end-to-end latency | Event sent → business completion | 3,600 ms | Includes time before consumer starts processing |
| Commit latency | Commit start → Kafka commit ACK | Depends on reality | Offset acknowledgment duration |

These boundaries are not interchangeable. A dashboard showing only the listener processing time of 160 ms on the final attempt can look great, even though the event actually waited over three seconds.

### 1.1. Attempt processing latency

This is the execution time of a single business processing run, typically measured from when the listener enters until it returns or throws an exception. It is suited for tracking database performance, HTTP dependencies, in-handler serialization/deserialization, or CPU.

If a record retries three times, three corresponding attempt measurements should be recorded. Separating these measurements reveals whether retries stem from slow processing or from fast failures followed by long waits.

### 1.2. Expected retry delay vs. actual retry delay

`BackOff` specifies the expected wait time between attempts. That is only the **retry schedule**, not necessarily the actual delay.

Distinguish:

- **Configured delay:** expected time per `FixedBackOff`, exponential backoff, or retry topic schedule.
- **Actual delay:** elapsed time from the failure until the listener actually starts the next attempt.
- **Scheduling drift:** the difference between actual delay and configured delay.

Actual delay can be longer due to paused consumers, slow polls, unavailable brokers, backlogged retry topics, rebalances, or saturated system resources.

### 1.3. Retry completion latency

This metric measures from the first processing attempt until business success or until the record moves to recovery. It answers: "Once processing starts, how long does an event take to reach a terminal state?"

Separate terminal outcomes:

- `success`: business processing completed successfully.
- `recovered`: the record was handled by the recoverer—for example, successfully sent to the DLT.
- `failed`: recovery also failed or the record remains pending.

A record routed to the DLT must not be counted as a successful business execution. Sending to the DLT is solely an outcome of the error-handling path.

### 1.4. End-to-end latency

This is the elapsed time from when an event is created/sent until downstream business processing finishes. It includes storage time in Kafka before the consumer reads it, processing time, retries, and other delays.

When the goal is "95% of order events applied within 30 seconds", end-to-end latency is the direct SLO measure. Retry latency only explains one part of why an SLO was breached.

## 2. Blocking retry and retry topics create different latency profiles

Spring Kafka has two common retry models.

### 2.1. Blocking retry in the listener container

With `DefaultErrorHandler`, a failing record is retried during listener container operation. Depending on configuration and version, the container may seek to reread the record or keep the record in memory and redeliver it. Backoff is applied before subsequent attempts.

Example:

```java
@Bean
DefaultErrorHandler orderErrorHandler() {
    FixedBackOff backOff = new FixedBackOff(
            1_000L,  // 1 second between retries
            3L       // up to 3 retries after the initial processing attempt
    );

    return new DefaultErrorHandler(backOff);
}
```

The configuration above allows up to four listener invocations on continuous failure: one initial attempt and three retries. With three one-second waits, maximum expected backoff is three seconds, excluding attempt execution and other overhead.

Blocking retry can slow down the active partition's progress. When a head-of-stream record fails repeatedly, subsequent records may have to wait, raising consumer lag or end-to-end latency for healthy records.

Observe:

- Listener failure counts and attempt counts.
- Processing duration per attempt.
- Wait intervals between attempts.
- Total duration for a record before success/recovery.
- Consumer lag and duration the consumer goes without polling.
- Offset commits after success or recovery.

### 2.2. Non-blocking retry via retry topics

With `@RetryableTopic`, failed records move through retry topics on a delay schedule. Example:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0)
)
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void handle(OrderCreated event) {
    billingService.process(event);
}
```

`attempts` here includes the initial processing attempt. Retries can pass through intermediate topics before reaching the DLT if processing never succeeds. Topic naming, DLT behavior, and generated components depend on Spring Kafka configuration.

With retry topics, latency also includes:

- Time to publish the record to a retry topic.
- Wait time until the timestamp when reprocessing is permitted.
- Time the record sits in the retry topic backlog.
- Time for the retry consumer to get partition assignment and receive the record.
- Overhead of multiple topic hops.
- Time to enter the DLT if attempts are exhausted.

Retry topics allow trailing records in the main topic to keep processing, yet alter ordering characteristics and increase the number of components to monitor.

### 2.3. Comparison table of what to measure

| Aspect | DefaultErrorHandler | @RetryableTopic |
|---|---|---|
| Where retry happens | Listener container reprocesses | Via one or more retry topics |
| Backoff | Executed by `BackOff` and handler/container | Driven by retry topic delivery schedule |
| Extra targets to monitor | Retry attempts, pause/seek, polls, lag | Retry topic lag, publishes, due timestamps, retry consumers |
| Ability to preserve original partition order | Easier to preserve in blocking retry | Can alter observable order at the business layer |
| Failures to watch for | Stalled partitions, long gaps between polls | Retry topic backlogs, delayed retry schedules, multi-hop hops |
| End-to-end metric | Must store first-attempt timestamp | Must persist timestamp across multiple topics/consumers |

## 3. Metrics that belong on a dashboard

A useful dashboard shows latency, retry counts, and backlog side by side. Looking at only one metric group easily leads to misdiagnosis.

| Recommended metric | Type | Purpose |
|---|---|---|
| `app.kafka.listener.attempt` | Timer | Processing duration per attempt |
| `app.kafka.retry.failures` | Counter | Failed processing attempts entering retry/recovery |
| `app.kafka.retry.actual_delay` | Timer or DistributionSummary | Actual elapsed time between two attempts |
| `app.kafka.retry.schedule_drift` | Timer or DistributionSummary | Deviation from backoff schedule |
| `app.kafka.retry.completion` | Timer | Time from first attempt to terminal outcome |
| `app.kafka.event.end_to_end` | Timer | Time from event creation timestamp to business success |
| `app.kafka.retry.recovered` | Counter | Records successfully passing through recoverer |
| `app.kafka.retry.recovery_failed` | Counter | Incomplete recovery attempts |
| `Consumer group lag` | Kafka Gauge/metrics | Incomplete records relative to committed offsets |
| `Retry topic lag` | Kafka Gauge/metrics | Backlog specifically inside retry topics |
| `DLT message rate` | Counter | Rate of unprocessable records |

The `app.kafka.*` names are examples of custom application metrics, **not** a claim that Spring Kafka exports all of them out of the box. Which metrics require manual instrumentation depends on your Spring Kafka version, Micrometer, and retry mechanism.

A dashboard design should split into three layers:

1. **Business:** end-to-end latency, success rate, SLO violations.
2. **Retry:** attempt counts, backoff, completion latency, recovery/DLT.
3. **Infrastructure:** Kafka consumer lag, rebalances, broker/network latency, and service resources.

Combining all three layers reveals why latency rose rather than merely showing that the system is slow.

## 4. Tagging metrics so they remain useful

Keep tag value sets bounded and operationally meaningful.

| Tag | Example | Notes |
|---|---|---|
| `service` | `billing-service` | Service owning the consumer |
| `topic` | `orders.created` | Source topic, or normalized topic group |
| `consumer_group` | `billing-service` | Used to analyze lag/ownership |
| `retry_mode` | `blocking`, `topic` | Distinguishes the two models |
| `outcome` | `success`, `recovered` | Separates business success from recovery |
| `exception` | `TimeoutException` | Group by error class |
| `attempt_bucket` | `1`, `2`, `3_plus` | Prevents unbounded tag growth |
| `retry_stage` | `initial`, `retry`, `dlt` | Simplifies path analysis |

Never use message keys, order IDs, correlation IDs, payloads, exception messages, or Kafka offsets as metric tags. These have very high cardinality, inflating metric storage costs and degrading query performance. Put them into controlled logs/traces and link via trace ID or event ID.

If retry topics include random numbers or dynamic identifiers in their names, normalize the label to a logical topic or retry stage before recording metrics.

## 5. Measuring single-attempt duration in a listener

Measuring with a monotonic clock (`System.nanoTime()`) is appropriate for durations within the same process. `System.currentTimeMillis()` or `Clock.instant()` records wall-clock timestamps, though those can be affected by system clock adjustments.

Example record listener using Micrometer:

```java
@Component
public class BillingListener {

    private final BillingService billingService;
    private final MeterRegistry meterRegistry;

    public BillingListener(
            BillingService billingService,
            MeterRegistry meterRegistry) {
        this.billingService = billingService;
        this.meterRegistry = meterRegistry;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "billing-service"
    )
    public void onMessage(
            ConsumerRecord<String, OrderCreated> record) {

        long startedAtNanos = System.nanoTime();
        String outcome = "success";

        try {
            billingService.process(record.value());
        }
        catch (RuntimeException ex) {
            outcome = "error";
            throw ex;  // Let DefaultErrorHandler manage retry/recovery.
        }
        finally {
            long elapsedNanos = System.nanoTime() - startedAtNanos;

            Timer.builder("app.kafka.listener.attempt")
                    .description("Business processing duration per delivery")
                    .tags(
                        "topic", record.topic(),
                        "outcome", outcome
                    )
                    .publishPercentileHistogram()
                    .register(meterRegistry)
                    .record(elapsedNanos, TimeUnit.NANOSECONDS);
        }
    }
}
```

This snippet records one duration for every actual listener invocation. If the same record is redelivered three times, three measurements are recorded. The `finally` block ensures both successful and failed attempts are captured while still rethrowing the exception so Spring Kafka handles it properly.

Understand this metric's boundary: it **excludes backoff wait time between invocations**, time spent sitting on retry topics, time before the consumer reads the record, and post-listener offset commit time.

In many applications, Spring Kafka includes built-in Micrometer timers or Micrometer Observation for listeners. Leverage that instrumentation when it matches your desired boundaries to avoid redundant metrics.

## 6. Using DefaultErrorHandler to observe failure counts

`DefaultErrorHandler` supports `RetryListener` to receive callbacks when a delivery fails or after recovery. This is a convenient integration point for recording counters and structured logs outside the listener logic itself.

Error handler bean configuration example:

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    public DefaultErrorHandler defaultErrorHandler(
            MeterRegistry meterRegistry) {

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        new FixedBackOff(1_000L, 3L)
                );

        handler.setRetryListeners(
                (record, exception, deliveryAttempt) -> {
                    meterRegistry.counter(
                            "app.kafka.retry.failures",
                            "topic", record.topic(),
                            "exception",
                            exception.getClass().getSimpleName()
                    ).increment();
                }
        );

        return handler;
    }
}
```

Here `deliveryAttempt` represents the delivery count as tracked by Spring Kafka, yet must not be automatically assumed to be the count of "completed retries" or remaining retries. Understand exactly when the callback fires in your version and use explicit metric names like `failures`.

You can extend `RetryListener` to observe `recovered` and `recoveryFailed` via the corresponding callbacks in Spring Kafka's API. Those metrics are distinct from listener success counts.

**Note:** retry callbacks do not provide a ready-made duration covering total wait time. To measure actual delay, correlate timestamps across attempts rather than trying to infer it from counters alone.

## 7. Measuring time between retries

To compute actual delay, you need to know when the prior attempt failed and when the next attempt started.

Concept:

```text
t0: listener attempt 1 fails
t1: error handler starts handling error
t2: scheduled backoff ends
t3: listener attempt 2 actually starts

configured delay = defined backoff schedule
actual delay     = t3 - t0
scheduling drift = actual delay - configured delay
```

Actual delay does not always equal `BackOff` time. It also includes exception-handling overhead, seeking or retaining, polling, queuing, and scheduling.

### 7.1. With blocking retry

You can observe the failure callback timestamp and the next listener invocation timestamp, correlating them by the record identifier of topic, partition, and offset within the current consumer scope.

An in-memory tracker can work when retries happen within the same process, but must manage:

- Multiple consumer threads processing concurrently.
- Rebalances moving records to another consumer.
- Records exhausting retries or moving to the DLT.
- Cleanup after success, recovery, timeout, and shutdown.
- Memory bounds if errors occur continuously across many records.

Never use an unbounded map storing every failed offset in production. If timing must survive restarts or rebalances, persist timestamps durably or carry metadata on the message.

### 7.2. With retry topics

You can record or extract two timestamps:

- **Scheduled due time:** when the record becomes eligible for reprocessing per retry schedule.
- **Actual retry start time:** when the retry listener actually begins.

Then:

```text
retry scheduling lateness = actual retry start - scheduled due time
```

When lateness grows, inspect retry topic lag, partition assignments, consumer pauses, rebalances, throttling, and processing speed.

Do not confuse `scheduled due time` with when Kafka stored the record in the retry topic. A record may be published immediately yet only processed at its due time; that delay is intentional.

Spring Kafka maintains internal metadata headers for retry topics. Their names and preservation behavior can change across versions; when building custom metrics, use the API of the running version or application-managed metadata instead of hardcoding unverified internal header names.

## 8. Measuring end-to-end latency across multiple topics

A timestamp attached to the record by the producer can measure elapsed time from event publication to business completion. This timestamp travels with the message across hops if the pipeline preserves headers.

Example producer writing an application header:

```java
ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>(
                "orders.created",
                event.orderId(),
                event
        );

byte[] publishedAt = ByteBuffer
        .allocate(Long.BYTES)
        .putLong(clock.millis())
        .array();

record.headers().add("x-event-published-at-ms", publishedAt);
kafkaTemplate.send(record);
```

Consumer reads the timestamp and records the metric after business work succeeds:

```java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void onOrderCreated(
        ConsumerRecord<String, OrderCreated> record) {

    billingService.process(record.value());

    Header header =
            record.headers().lastHeader("x-event-published-at-ms");

    if (header == null || header.value().length != Long.BYTES) {
        return;
    }

    long publishedAtMillis =
            ByteBuffer.wrap(header.value()).getLong();

    long elapsedMillis = clock.millis() - publishedAtMillis;

    if (elapsedMillis >= 0) {
        Timer.builder("app.kafka.event.end_to_end")
                .tags(
                    "topic", record.topic(),
                    "outcome", "success"
                )
                .publishPercentileHistogram()
                .register(meterRegistry)
                .record(elapsedMillis, TimeUnit.MILLISECONDS);
    }
}
```

`clock` and `meterRegistry` here are dependencies injected into the bean. The example measures duration **up to when business work completes inside the listener**; it excludes subsequent Kafka offset commits.

This measurement works well for events sharing a timestamp origin, with these caveats:

1. Producer and consumer clocks can skew; NTP or appropriate time synchronization is required.
2. Client-emitted timestamps can differ from when the broker appends the record.
3. With retry topics, ensure headers are preserved when Spring Kafka publishes to retry topics and during manual replays.
4. Missing or malformed headers must follow a separate metric policy; never record negative durations.
5. If an event is replayed days later, end-to-end latency will be huge. Separate replays from normal live traffic.

If you need to measure **retry completion latency** from the first attempt, also store a `first-attempt-at` timestamp when the record is first delivered. Across retry topics and restarts, that timestamp must travel with the record or live in an accessible store. Relying solely on the current Kafka record's timestamp is insufficient, as each publish to a retry topic can assign a new timestamp.

## 9. Observing with Micrometer and Spring Kafka

Spring Kafka integrates with Micrometer to record metrics and observations for producers/consumers in supported versions. Observation can be enabled on the listener container when using the Micrometer Observation ecosystem.

Factory configuration example:

```java
factory.getContainerProperties().setObservationEnabled(true);
```

With Spring Boot, properties like `spring.kafka.listener.observation-enabled` and corresponding observation configurations may be available depending on the Boot/Spring Kafka version. Check the actual configuration metadata of your running dependencies.

Spring Kafka listener observation typically tracks listener invocation duration. It does not automatically prove the entire retry lifecycle from first attempt to success/DLT was measured. When a retry occurs after the listener throws an exception, that individual listener span or timer may have already ended.

What to do:

- Leverage built-in observation to measure listener duration, status, and exceptions.
- Record dedicated metrics for retry delay and retry completion if SLAs require them.
- Use trace context to link producers, the original listener, retry topics, and the DLT.
- Check sampling and context propagation across headers, especially when records are republished.
- Do not assume a single trace automatically spans restarts or retry topics unless propagation is configured.

### 9.1. What questions can traces answer?

For a specific event, a trace can show:

```text
Produce orders.created
  └─ Consume orders.created (attempt 1, failed)
       └─ Publish orders.created-retry
            └─ Consume orders.created-retry (attempt 2, failed)
                 └─ Consume next retry stage
                      └─ Business operation success
```

The diagram is simply an ideal observation model. Whether spans connect into one trace or linked traces depends on tracing instrumentation, header propagation, and your configured observability stack.

Metrics show aggregate trends; traces and structured logs help investigate a specific event or error cluster.

## 10. Distinguishing retry latency from consumer lag

Consumer lag is typically the difference between a partition's log end offset and a consumer group's committed offset. It reflects read/commit progress per partition, not directly an event's retry duration.

Two distinct situations can occur:

### 10.1. Blocking retry causes lag to rise

The first record fails and the container waits/backs off, so subsequent records in the partition are not processed yet. Lag can climb even when producer throughput is unchanged.

In that case, inspect:

- Retry failure rate and wait durations.
- Incoming event rate.
- Attempt processing duration.
- `max.poll.interval.ms` and rebalance frequency.
- Which partitions are accumulating backlogs.

### 10.2. Retry topics keep main-topic lag low yet SLAs still suffer

Failed records are moved to retry topics; the main-topic consumer continues processing subsequent records. Main-topic lag may stay low while failing events remain stuck in the retry chain.

Thus, if a dashboard measures only main-topic lag, retry trouble can be masked. Also inspect retry topic lag, counts of events awaiting retry, scheduled delays, and total event age.

A consumer with zero lag still does not guarantee every event completed business processing: some records may have moved to the DLT or be waiting in another topic.

## 11. Designing dashboards around latency and outcomes

A dashboard can be organized into four areas.

### 11.1. Business experience overview

Display p50/p95/p99 of `event.end_to_end` for successful events, success rate over time windows, and percentage of events breaching SLOs. Include sample counts alongside percentiles to avoid misinterpretation during low traffic.

### 11.2. Retry effectiveness

Display:

- Share of events requiring at least one retry.
- Distribution of attempts per event.
- Post-retry success rate.
- DLT routing rate.
- p95/p99 time from first attempt to success.
- Separate recovery duration for records routed to the DLT.

If retry rate rises while completion latency stays low, transient errors are likely recovering quickly. If retry rate stays flat while p99 latency climbs, backlogs or scheduling drift may be growing.

### 11.3. Retry waiting cost

Display configured backoff, actual delay, and lateness. For retry topics, break down by retry stage; for blocking retry, break down by listener or exception group.

If actual delay rises while configured backoff stays constant, the issue likely lies in scheduling, consumer capacity, or the broker/cluster rather than the `BackOff` configuration itself.

### 11.4. Infrastructure

Display consumer lag, pause durations, rebalances, listener processing duration, Kafka publish failures, and broker/network latency.

These metrics pinpoint why retry latency increased.

## 12. Creating histograms and calculating p95/p99

A Micrometer `Timer` typically records count and total time, and can enable histograms to query sample percentiles. To compute p95/p99 in Prometheus across multiple instances, enable histograms or an appropriate percentile mechanism.

Example:

```java
Timer.builder("app.kafka.retry.completion")
        .description("Duration from first attempt to terminal outcome")
        .tags(
            "topic", topicName,
            "outcome", "success"
        )
        .publishPercentileHistogram()
        .register(meterRegistry)
        .record(elapsed, TimeUnit.MILLISECONDS);
```

PromQL example when the `Timer` exports histograms in seconds:

```promql
histogram_quantile(
  0.95,
  sum by (le, topic, outcome) (
    rate(app_kafka_retry_completion_seconds_bucket[5m])
  )
)
```

The query above estimates p95 over a five-minute window from histogram buckets. It works only when the system actually exports the corresponding buckets and the metric carries `topic` and `outcome` labels.

You can compute event completion rate by outcome:

```promql
sum by (topic, outcome) (
  rate(app_kafka_retry_completion_seconds_count[5m])
)
```

When sample counts are low in a short window, percentiles can fluctuate wildly. Compare against count/rate, pick suitable time windows, and verify bucket boundaries have enough resolution near the SLO.

### 12.1. Why not rely on average as the sole metric?

Suppose 99% of retried records finish in one second while 1% take one minute. The average may still look low, yet customers in the long tail suffer a terrible experience.

p95 and p99 expose tail latency. Still, they require adequate sample counts and proper histograms; you must also know whether you are measuring success or DLT, blocking retry or retry topics.

## 13. Setting SLOs and alerts

SLOs should stem from business requirements, not from configured backoff seconds. For example, a service needs to process most payment events within 30 seconds of event creation.

Useful signals include:

| Signal | Example alert condition | Investigation action |
|---|---|---|
| End-to-end p95 | Exceeds SLO over consecutive windows | Check retries, lag, and dependencies |
| Retry success rate | Drops sharply vs. baseline | Inspect exception mix and dependencies |
| Retry scheduling drift | p95 rises while configured backoff is unchanged | Check topic lag, pauses, rebalances |
| Retry backlog | Waiting record count grows steadily | Check retry consumer capacity |
| DLT ingress | Sudden spike | Analyze unrecoverable errors |
| Recovery failure | Any significant spike | Check DLT publish/serializers/ACLs |
| Consumer lag | Rises alongside retry rate | Check blocking retries or input load |

Example target definition:

```text
SLO: 99% order events complete business processing within 30 seconds
Track: event_end_to_end{outcome="success"}
Early warning: p95 > 20 seconds and retry backlog growing
Breach alert: percentage of events over 30 seconds exceeds error budget
```

The 20/30-second thresholds here are examples only. When implementing, define which events enter the sample, start timestamps, which outcomes satisfy the SLO, and how pending events without a terminal outcome are accounted for.

Measuring latency solely for **already-succeeded** records introduces bias: records stuck in retries long-term never appear in completion histograms. Therefore, add an "oldest pending retry age" or backlog age metric to catch records waiting too long.

## 14. DLT as a separate outcome

Once retries are exhausted, a recoverer may publish the record to a DLT. Record separately:

- Number of records entering the DLT.
- Time from first attempt to completed recovery.
- Number of failed DLT publishes.
- Age of the oldest record currently in the DLT.
- Time from DLT entry until manual handling or successful replay.

Do not record `outcome=success` for a record merely published to the DLT. If the business process has not completed, the business SLO is still unmet.

If a replay process exists, an event can begin a new processing cycle. Decide whether to measure latency per replay cycle separately or from the original event. For audit needs, keep both: `original_event_age` and `replay_processing_latency`.

### 14.1. Recovery can fail too

DLT publishing can fail due to serializers, access permissions, missing topics/partitions, or unavailable brokers. In that case, the recoverer can throw an exception and the record remains unrecovered.

Record completion metrics at the point where recovery is known to have succeeded per policy, not merely when the recoverer call starts. When high durability is required, verify send confirmation, transactions, and offset commit behavior in your specific configuration.

## 15. Which factors affect latency?

### 15.1. Backoff too short

Retrying too quickly while a dependency is failing can trigger a retry storm. The system receives floods of failing requests, burns extra CPU and network, and worsens tail latency even for healthy records.

The fix is choosing bounded backoff, considering exponential backoff and jitter where appropriate, and tracking retry success rates.

### 15.2. Backoff too long

Long backoff eases dependency pressure yet stretches record completion time. With tight SLOs, the retry schedule itself can burn through the error budget.

Estimate total scheduled retry time:

```text
total_expected_time
  ≈ sum(processing_time_per_attempt)
  + sum(configured_backoff)
  + scheduling_overhead
  + queue_wait
```

This is a planning estimate; actual latency must be measured via timestamps.

### 15.3. Insufficient consumer capacity

Retry topics can build backlogs when failing event volume spikes suddenly. Even if each record has a one-second retry schedule, it may wait far longer because retry consumers lack capacity.

Monitor lag, partition count, concurrency, CPU, GC, database connection pools, and attempt processing duration.

### 15.4. Rebalances and restarts

Rebalances can interrupt progress, introducing extra wait time and redeliveries. When measuring latency across multiple processing cycles, preserve the first-attempt timestamp across restarts or use a durable tracking store.

### 15.5. Exceptions with fixed causes

If an error stems from an invalid payload, retrying repeatedly only adds latency before eventually landing in the DLT. Classify exceptions, transition early to appropriate recovery, and monitor non-retryable error rates.

## 16. Logging to support investigations

A useful retry log should contain enough context to correlate attempts without logging sensitive payloads.

Structured log payload example:

```json
{
  "event": "kafka_retry_failure",
  "service": "billing-service",
  "topic": "orders.created",
  "partition": 2,
  "offset": 18420,
  "consumerGroup": "billing-service",
  "deliveryAttempt": 2,
  "exceptionType": "RemoteServiceTimeoutException",
  "retryMode": "blocking",
  "timestamp": "2026-11-15T10:00:01Z",
  "traceId": "example-trace-id"
}
```

This is an illustrative log structure; fields must be emitted explicitly by the application or instrumentation. With retry topics, topic/partition/offset can change on each publish, so a stable event ID or correlation ID is needed to trace across topics.

Do not turn event IDs, trace IDs, or offsets into tags on every metric; keep them in logs or traces and use them only for case-by-case investigation.

## 17. Test scenarios for measuring retry latency

An integration test with a real Kafka broker can verify measurement logic rather than merely confirming the listener was re-invoked.

### 17.1. Blocking retry

1. Use a dedicated test consumer group and topic.
2. Set `FixedBackOff(500L, 2L)`.
3. Make the listener fail on the first two attempts and succeed on the third.
4. Capture start and end timestamps of each attempt.
5. Verify the failure counter increments twice and the attempt timer records three samples.
6. Verify spacing between invocations reflects backoff within reasonable scheduling tolerance.
7. Verify completion latency includes both processing and waiting.
8. Verify committed offset and zero DLT entries when business logic succeeds.

Do not assert exact millisecond precision; CI environments exhibit scheduling jitter. Use tolerances appropriate for the OS, JVM, and test broker.

### 17.2. Retry topics

1. Configure main topic, retry topic, and DLT with short backoff.
2. Send an event with an application-generated original timestamp.
3. Make the initial listener fail and the retry listener succeed.
4. Verify the original timestamp remains accessible after forwarding.
5. Measure when the record became eligible for reprocessing and when the listener actually started.
6. Verify end-to-end latency includes wait time on the retry topic.
7. Simulate a slow retry consumer to observe rising scheduling lateness.
8. Verify DLT and outcome when all attempts fail.

For retry topics, use timestamps or metadata supported by your Spring Kafka version; avoid coupling tests to unstable internal header structures.

### 17.3. Testing restarts and duplicates

Inject a failure after business logic writes to the database yet before the offset commits. When the record is redelivered, attempt metrics may climb and the event is processed again. The handler must be idempotent, and dashboards should include duplicate/replay metrics to explain why attempts exceed unique event counts.

## 18. Common observability mistakes

**Measuring only `@KafkaListener` duration.** That metric captures each listener call while missing backoff and time spent on retry topics. Add completion latency and actual retry delay where needed.

**Treating configured backoff as actual latency.** The retry schedule misses scheduling drift, poll delays, and backlogs. Measure when the next attempt actually starts.

**Watching only main-topic lag.** Non-blocking retry moves records to separate topics. Add retry topic lag and oldest pending event age.

**Counting DLT as success.** DLT is a recovery outcome, not proof that business processing completed. Separate outcome metrics.

**Using retry topic timestamps as the original event timestamp.** Each republish can alter the record timestamp, understating end-to-end latency. Use a preserved source timestamp.

**Using `System.currentTimeMillis` for in-JVM durations without considering clock shifts.** For internal durations, prefer `System.nanoTime()`. Use wall-clock time when comparing across systems and monitor clock skew.

**Putting record keys or exception messages into metric tags.** Cardinality explodes, increasing costs and hurting query performance. Use low-cardinality labels; keep detailed IDs in logs/traces.

**Measuring only completed records.** Records stuck long-term are missing from completion histograms. Add pending age, backlog, and time-since-first-attempt for waiting records.

**Not separating retry attempts from unique records.** One event failing three times can emit three error samples. When computing retry rates, specify whether the denominator is deliveries or unique events.

**Not observing commits and recovery failures.** Business work can finish before commit; DLT publishes can fail. Pair outcome metrics with commit failures, redeliveries, and idempotency.

## 19. Prioritized rollout plan

For a running Spring Kafka service, observability can be added in order:

1. Define business SLOs and start/end timestamp boundaries.
2. Enable listener metrics or observation matching your Spring Kafka version.
3. Count retry failures, exhausted retries, and recovery outcomes via `RetryListener` or equivalent hooks.
4. Preserve event timestamps or event IDs across retry topics/DLTs.
5. Record completion latency and end-to-end latency, separated by outcome.
6. Add actual retry delay and scheduling drift when diagnosing backoff.
7. Combine with consumer lag, retry topic lag, rebalances, and resource metrics.
8. Build dashboards for p50/p95/p99, retry rate, DLT, and pending age.
9. Set SLO-based alerts, observe trends, and test with injected failures.
10. Re-verify instrumentation when upgrading Spring Kafka or changing retry models.

### 19.1. Checklist of questions when a latency alert fires

When p95 or p99 rises, check sequentially: did retry failures increase? Did configured backoff change? Is actual delay drifting from schedule? Does the retry topic have a backlog? Did a new exception type appear? Is the consumer rebalancing or losing partition assignments? Are dependencies timing out? Are stuck incomplete records missing from completion histograms?

These questions separate faults in retry policy, consumer capacity, Kafka, or business services.

## 20. References and version scope

When implementing on a specific version, consult these official documentation sections:

- Spring for Apache Kafka Reference: error handling, `DefaultErrorHandler`, `RetryListener`, `BackOff`, `ContainerPausingBackOffHandler`.
- Spring for Apache Kafka Reference: non-blocking retries, `@RetryableTopic`, retry topic headers, backoff timing, and DLT.
- Spring Kafka Javadoc: `DefaultErrorHandler`, `RetryListener`, `ConcurrentKafkaListenerContainerFactory`, `ContainerProperties`.
- Spring Kafka Reference: Micrometer timers, Micrometer Observation, and listener instrumentation.
- Micrometer Documentation: `Timer`, percentile histograms, tags/cardinality, and Prometheus naming.
- Apache Kafka Documentation: consumer lag, offset commits, client metrics, and record timestamps.

Observability APIs, Spring Boot properties, and retry-topic details can vary across Spring Kafka releases. When upgrading dependencies, verify actually exported metrics, label names, attempt counts, header propagation, and offset persistence. In particular, listener latency and end-to-end retry latency are two distinct measurements and should be plotted on separate graphs.

Monitoring retry latency effectively means knowing **how long each processing attempt takes**, **how long records wait for retries**, **why retry schedules drift**, and **whether events ultimately succeed or enter the DLT**. When these milestones are recorded alongside lag and outcomes, operations teams can see clearly whether retries are protecting the system or stretching processing beyond SLOs.
