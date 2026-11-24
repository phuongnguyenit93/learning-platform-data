# Backoff Delay Precision

In Spring Kafka's **non-blocking retry**, a failed record is forwarded to a retry topic and reprocessed only once its eligible timestamp arrives. A **backoff delay** configuration is often read as "wait 2 seconds then retry," yet in real systems it is **not a timer executed to the exact millisecond**. Delay is an expected or minimum wait interval under the retry mechanism; when the listener actually runs also depends on consumer polls, pause/resume, schedulers, partition assignments, system load, and infrastructure latency.

Therefore, when operating non-blocking retry, separate three questions:

1. **When is the record allowed to be retried?** That is the eligible time, computed from the backoff policy and retry metadata.
2. **When does the listener actually receive the record?** That is the actual processing time, which may be later than the eligible time.
3. **How much deviation is acceptable?** The answer depends on SLAs, clock accuracy, poll latency, and consumer capacity.

This lesson explains the mechanisms causing delay variance, how to measure that variance, how to configure and test it in **Spring Kafka Reliability Operations**, and how to distinguish backoff delay from exact-time execution guarantees.

## 1. Non-Blocking Retry Is Not a Kafka Broker Timer

A Kafka topic is a partitioned log. The broker stores records by offset and serves consumers via the fetch protocol; the Kafka broker does not hold a record until a specified business processing timestamp.

Spring Kafka implements non-blocking retry using **retry topics**:

1. The main topic listener processes a record and throws an exception.
2. Retry infrastructure determines the attempt, delay, and target topic per configuration.
3. A corresponding record is published to the retry topic with retry metadata, including an eligible-processing timestamp.
4. The retry topic's consumer may receive the record early.
5. Retry infrastructure defers invoking the listener until due, typically by pausing/resuming the container or partition and continuing appropriate polling.
6. Once the record becomes due, the listener is invoked again; if it still fails, the record may move to another retry topic or the DLT.

~~~mermaid
sequenceDiagram
    participant M as Main topic listener
    participant P as Retry publisher
    participant K as Kafka retry topic
    participant C as Retry consumer
    participant S as Backoff/scheduler
    M->>M: Process record A fails
    M->>P: Request retry
    P->>P: Compute due timestamp
    P->>K: Publish record A + retry metadata
    K-->>C: Consumer polls record A
    C->>S: Due timestamp not reached
    S-->>C: Pause / wait and keep polling appropriately
    S-->>C: Eligible time reached
    C->>C: Invoke listener with record A
~~~

Pausing, polling, and resuming are Spring Kafka consumer-side mechanisms, not a per-message timer executed by the broker. Lifecycle and scheduler details can vary across Spring Kafka versions.

**Key takeaway:** a record is not promised to run at the exact due timestamp; it may only run on a poll cycle or scheduler wakeup after that mark.

## 2. Backoff Delay: Eligible Time vs. Processing Time

Suppose the first failure occurs at 10:00:00.000. The policy asks for a 2,000 ms delay.

We can distinguish these milestones:

| Symbol | Milestone | Example |
|---|---|---|
| F | Listener detects failure | 10:00:00.000 |
| P | Retry record created and timing metadata determined | 10:00:00.080 |
| D | Eligible mark (due timestamp) based on P and delay | 10:00:02.080 |
| A | Retry record ready in Kafka and observed by consumer | 10:00:00.160 |
| R | Retry listener actually invoked | 10:00:02.470 |

In this example, the requested delay is 2,000 ms; the retry listener runs 390 ms after the due timestamp. Measured from the initial failure F, the interval to R is 2,470 ms.

This is not a retry "violating policy" merely because the listener did not run at exactly 10:00:02.080. It reflects that **backoff delay and end-to-end retry latency are two different quantities**.

Remember that the baseline for computing backoff may be when the retry record/metadata is created, not necessarily the exact instant the first exception occurred. Never use the first failure timestamp as the sole reference when measuring wait-mechanism accuracy.

### 2.1 Three Time Quantities to Measure

Notation:

- **t_failure**: timestamp when the listener failed.
- **t_due**: timestamp when the retry record becomes eligible.
- **t_start**: timestamp when the retry listener starts processing.

Definitions:

~~~text
requested_delay = BackOff value applied to the attempt

effective_retry_wait = t_start - t_failure

scheduler_lateness = t_start - t_due

on_time_ratio = fraction of retries whose scheduler_lateness
                falls within an acceptable threshold
~~~

In normal operation, **scheduler_lateness** is typically non-negative because the retry mechanism tries not to process records before their due timestamp. However, if clocks drift between nodes, metadata is wrong, or instrumentation uses inconsistent time sources, measurements can look unusual; do not treat this as a hard real-time guarantee.

Separating **effective_retry_wait** from **scheduler_lateness** reveals whether extra time came from publisher/network delays or late consumer/scheduler execution.

### 2.2 Practical Example

Delay is configured to 5 seconds, yet retries appear to start 7 seconds after failure.

The extra 2 seconds could come from:

- Retry publisher waiting for broker ACKs before the record is readable.
- Retry consumer currently processing other records.
- Retry topic partition paused or awaiting resume.
- A rebalance or restart occurring.
- Consumer thread or scheduler starved of CPU.
- Polling unable to service eligible records quickly enough.

Thus, concluding "a 5-second backoff is inaccurate" requires checking t_due, t_start, and capacity metrics.

## 3. Is Backoff a Minimum Wait Time?

For non-blocking retry, the eligible timestamp prevents invoking the listener early. By design, delay acts as a **minimum wait interval** before a retry attempt may execute, not a guarantee of execution at that exact instant.

That does not mean requesting 5 seconds guarantees the retry happens between 5.000 and 5.001 seconds. Schedulers and consumers typically check/wake at discrete intervals. If the due timestamp falls between two wakeups, the record runs on the next cycle.

### 3.1 Illustration of Poll Latency

Suppose a retry is due at 12:00:05.000. The consumer is waiting or polling and the next check happens at 12:00:05.280.

~~~text
12:00:00.000  Retry published
12:00:05.000  Record becomes eligible
12:00:05.280  Consumer/scheduler resumes processing
                -> Listener begins
~~~

Lateness is roughly 280 ms. This occurs naturally even when delay configuration is completely correct.

### 3.2 No Automatic Upper Bound

If brokers are busy, partitions are unassigned, downstream is slow, or the app stops, retries can run far later than the configured delay. Neither Kafka nor Spring Kafka provides an automatic guarantee like "must execute no later than 10 ms late."

SLAs must distinguish:

- **Minimum wait**: do not process before the due mark assuming accurate clocks and metadata.
- **Delivery freshness**: how late after the due mark the record reaches the listener.
- **Recovery time**: how long business logic takes to finish after initial failure, across all retries.

A system with accurate backoff logic yet insufficient capacity can still breach recovery SLAs.

## 4. Causes of Late Retry Execution

### 4.1 Kafka Consumer Poll Cycle

A consumer does not receive events millisecond-by-millisecond; it polls and processes records in a loop. A retry record can become due while the consumer is:

- Waiting for a poll call to return.
- Processing another record.
- Executing callbacks or container tasks.
- Waiting for a partition resume.
- Participating in a rebalance.

Therefore, poll cadence and listener execution time influence delay after the due timestamp.

Settings like **pollTimeout** and poll properties while paused affect responsiveness, yet there is no fixed rule like "1-second poll timeout means at most 1-second lateness." Thread scheduling, load, and partition assignments also matter.

### 4.2 Pause/Resume and Wakeup Scheduling

Non-blocking retry can temporarily pause consumption on a retry consumer/partition until a record comes due. Once the wait expires, the container must transition back to active processing and continue the poll loop.

Delays can appear at:

- Detecting a record is not yet due.
- Computing the wait interval until due time.
- The scheduler executing the resume task.
- The consumer thread actually picking up and processing the resume.
- Eligible records reaching listener invocation.

If worker threads are saturated, an on-time callback does not mean the listener executes immediately.

### 4.3 CPU, Garbage Collection, and Thread Contention

When an application is CPU-starved, hits long GC pauses, or has many listeners/scheduler tasks competing for threads, retries can be invoked late.

In containerized environments, CPU throttling can delay threads past desired times. Monitor:

- CPU usage and CPU throttling.
- GC pause duration.
- Thread pool saturation.
- Consumer poll latency.
- Scheduler task delay.
- Listener invocation duration.

Changing the delay value does not fix insufficient processing capacity.

### 4.4 Rebalances and Partition Assignment

When a retry consumer restarts or a consumer group rebalances, partitions can temporarily lack an active owner. Any record becoming due during that window waits until assignments stabilize and a consumer can read.

Rebalances can come from:

- Scaling pods or concurrency.
- Rolling deployments.
- A consumer exceeding max.poll.interval.ms.
- Broker/group coordinator changes.
- Consumer crashes or network partitions.

Consequently, p99 lateness typically degrades during deployments even when p50 stays steady.

### 4.5 Backlog in Retry Topics

A retry topic can have thousands of records due simultaneously. One consumer can process only a bounded rate per second. An eligible record queued behind a large backlog will be invoked late.

Example:

~~~text
09:00:00  10,000 retry-topic records become due together
09:00:00  Consumer can process 500 records/second
09:00:01  Many records still waiting
09:00:10  Some records already ~10 seconds past due
~~~

Adding consumption capacity or sensible partitioning reduces backlogs, while respecting downstream limits and per-key fairness.

### 4.6 Earlier Record Waiting on the Same Partition

Kafka keeps log order per partition. If an earlier record is waiting on a later due timestamp, a subsequent record on the same retry partition may have to wait under the container's pause/ordering mechanics, even if the later record has an earlier due timestamp.

This is a form of **head-of-line blocking**. Using separate retry topics per delay tier or appropriate partitioning changes the blast radius, yet does not eliminate per-partition ordering limits completely.

Never assume every record in a retry topic has an independent timer enforced by the Kafka broker.

### 4.7 Clock Skew Between Nodes

Backoff timestamps are often created on one component and checked on a consumer. If two nodes have different system clocks, comparing against an epoch timestamp can fire early or late relative to real elapsed time.

For example, a publisher's clock runs 800 ms ahead of the retry consumer. The due mark in metadata makes the retry consumer perceive an extra ~800 ms wait when compared against its own clock.

Therefore:

- Synchronize time using appropriate infrastructure mechanisms, such as NTP.
- Monitor node clock offset.
- Clearly record whether timestamps come from producer, consumer, or monitoring host.
- Never mix local monotonic clocks and wall-clock timestamps across processes when computing elapsed time.

Negative lateness measurements can signal clock skew or instrumentation bugs. Do not merely clamp values to 0 and ignore the cause.

### 4.8 Publish and Broker Latency

If a record has not yet been written successfully to the retry topic, the retry consumer cannot see it. Publish and broker latency can stretch the time from first failure to retry, especially when:

- Retry publisher is waiting for ACKs.
- Retry topic is below min.insync.replicas.
- Brokers experience high request latency.
- Retry producer hits buffer pressure or timeouts.
- Metadata refreshes, leader elections, or network interruptions happen.

Distinguish publish delay from scheduler lateness. When tracing, record both the failure timestamp and when the retry record was sent/acknowledged.

## 5. How Backoff Types Affect Retry Schedules

Spring Kafka supports fixed, exponential, or randomized backoffs in supported versions/configurations.

### 5.1 Fixed Backoff

Example:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2_000)
)
@KafkaListener(
    topics = "orders",
    groupId = "order-worker"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Assuming standard Spring Kafka semantics: **attempts = 4** includes the initial attempt and up to three retries. Each retry applies the configured backoff delay.

Execution timeline might look like:

| Attempt | Configured delay | Eligible time | Actual processing time |
|---|---:|---|---|
| 1 - main topic | No retry delay | 10:00:00.000 | 10:00:00.000 |
| 2 - retry 1 | 2 seconds | 10:00:02.100 | 10:00:02.440 |
| 3 - retry 2 | 2 seconds | 10:00:04.600 | 10:00:05.010 |
| 4 - retry 3 | 2 seconds | 10:00:07.180 | 10:00:07.500 |

Each attempt's eligible mark depends on when the previous failure occurred and the next retry record was created—not three fixed marks at +2/+4/+6 seconds from the first failure.

### 5.2 Exponential Backoff

Example:

~~~java
@RetryableTopic(
    attempts = "5",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 8_000
    )
)
@KafkaListener(
    topics = "orders",
    groupId = "order-worker"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Expected wait intervals between attempts can be 1, 2, 4, and 8 seconds across the four retry attempts. These are **desired delay values**, not absolute timestamps the listener is guaranteed to hit.

If each retry is delayed an extra few hundred milliseconds or seconds by backlog, total time from initial failure to DLT can significantly exceed the sum of configured delays.

### 5.3 Randomized Backoff and Jitter

Randomized backoff helps prevent consumers from retrying simultaneously when a downstream recovers. With jitter, the delay chosen for each retry can vary. Therefore, measuring accuracy must compare against **the delay selected for that specific attempt**, not only the initial base delay.

Configuring a delay range does not mean retries must occur at one fixed number. Each attempt needs its actual due timestamp to measure deviation.

### 5.4 Topic Reuse and Delay Grouping

Spring Kafka has strategies for creating or reusing retry topics, varying by version and BackOff type. Whether multiple attempts share one retry topic or use separate topics per delay tier affects:

- Number of partitions/topics to operate.
- Number of consumers and operational overhead.
- Extent to which records with different due timestamps share a partition.
- Scope of head-of-line blocking.
- Ability to scale each retry tier independently.

Never assume retry topic names or counts from attempts alone. Inspect the retry-topic topology generated at runtime.

## 6. Configuring Spring Boot and Spring Kafka to Control Latency

A simple configuration example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: order-worker
      enable-auto-commit: false
      properties:
        max.poll.records: 100
    listener:
      ack-mode: record
      concurrency: 3
      poll-timeout: 1s
~~~

Values are illustrative. What matters is deliberate balance between throughput, consumer count, poll intervals, and downstream capacity.

**poll-timeout** is not a direct dial to turn non-blocking retry into a millisecond-exact scheduler. Actual poll intervals also depend on data availability, pause/resume, callback execution, and runtime load.

### 6.1 Parameters to Review Together

| Parameter or component | Operational effect |
|---|---|
| BackOff delay | Expected wait before next attempt |
| Retry-topic topology | Number of retry streams, splitting, and topic reuse |
| Consumer poll timeout | Poll cadence and responsiveness in certain states |
| Pause/resume scheduler | When container resumes processing eligible records |
| Consumer concurrency | Number of consumer threads able to run in parallel |
| Partition count | Maximum parallelism for a group on subscribed partitions |
| max.poll.records | Records per poll and batch processing duration |
| max.poll.interval.ms | Max gap between polls before risking assignment loss |
| Listener duration | How long a consumer thread is held per invocation |
| CPU/GC and broker latency | Execution delays outside backoff logic |

In some Spring Kafka versions, containers expose options for polling while paused and corresponding BackOffHandler/scheduler mechanisms. API names and defaults can vary; inspect your running version's runtime configuration rather than assuming one universal default.

### 6.2 Choosing Concurrency by Partition Count

Suppose a retry topic has 4 partitions and the retry listener group runs 2 pods, each with concurrency 3. Total consumers equal 6, yet at most 4 consumers can be assigned partitions of that topic when considering this topic alone.

Raising per-pod concurrency from 3 to 8 does not give the retry topic more partitions. Extra consumers sit idle. If lateness grows due to a hot partition, adding consumers alone may not help.

Compare load **per partition**, not only total consumer count or total lag.

### 6.3 Reducing Unrelated Workload

If retry consumers share a process with many listeners and heavy CPU tasks, contention can delay schedulers. Measures include:

- Bounding concurrent downstream work.
- Measuring and optimizing listener execution time.
- Ensuring thread/scheduler pools are not saturated.
- Allocating sufficient CPU and memory to the app.
- Separating heavy retry workloads into dedicated deployments if architecture requires.
- Checking GC and thread dumps when latency spikes.

A fast retry system needs capacity to execute attempts, not just small timer settings.

## 7. Measuring Delay Precision in Production

Do not use a "retry count" metric as a proxy for timing accuracy. Measure directly **when records become eligible** and **when listeners are invoked**.

### 7.1 Metadata for Retry Attempts

Spring Kafka retry-topic infrastructure uses metadata to identify attempts and eligible timestamps. You can observe retry headers or add instrumentation around publishers/containers using your project version's APIs.

Timestamps to distinguish:

- **Event created timestamp**: when business logic created the event.
- **Original Kafka record timestamp**: timestamp of the record on the main topic.
- **Retry record append/create timestamp**: timestamp attached to the retry-topic record per Kafka config.
- **Retry backoff due timestamp**: timestamp governing when the record becomes eligible for retry.
- **Retry listener start timestamp**: actual start of reprocessing.

Do not use the Kafka record timestamp as the due timestamp unless the framework guarantees they match. If adding custom timestamps in business headers, name them clearly so they are never confused with Spring Kafka's internal headers.

### 7.2 Formulas for Measuring Lateness

For each attempt:

~~~text
due_at_ms = eligible timestamp of the retry attempt
listener_started_at_ms = timestamp when listener is invoked

lateness_ms = listener_started_at_ms - due_at_ms
effective_wait_ms = listener_started_at_ms - failed_at_ms

early_execution = lateness_ms < 0
late_by_1s = lateness_ms > 1000
~~~

Timestamps being subtracted must share the same epoch and synchronized clocks. To measure elapsed intervals inside a single JVM, use a monotonic clock to avoid wall-clock jumps; however, timestamps passed through Kafka across JVMs are typically wall-clock epochs, so account for clock skew.

### 7.3 Analyzing Distributions Instead of Single Examples

Measure:

- p50 lateness: typical behavior.
- p95 and p99 lateness: high-load behavior and tail latency.
- Max lateness over a time window.
- Rate of retries starting early relative to due timestamp.
- Rate of retries late beyond SLA thresholds, e.g., 1 or 5 seconds.
- Lateness broken down by topic, partition, consumer instance, and retry attempt.

Example:

| Metric | Observed value | Interpretation |
|---|---:|---|
| Configured fixed delay | 2,000 ms | Expected delay |
| p50 lateness | 120 ms | Most attempts start slightly after due |
| p95 lateness | 650 ms | Noticeable tail latency |
| p99 lateness | 3,400 ms | Some attempts are significantly delayed |
| Max lateness | 42 seconds | Investigate rebalances/backlog |
| Retried earlier than due | 0.02% | Check clocks or instrumentation |

This is hypothetical data illustrating how to read a dashboard, not default Spring Kafka performance.

### 7.4 Contextual Logging

A sensible log entry:

~~~text
service=order-worker
topic=orders-retry-2000
partition=2
offset=1184
eventId=evt-1001
attempt=2
dueAtMs=1900000002000
startedAtMs=1900000002290
latenessMs=290
consumerClientId=order-worker-2
~~~

Keep event ID, attempt, and partition to isolate issues. Never log full sensitive payloads.

If application logs lack a reliable due timestamp, do not report a "scheduler lateness" metric built by arbitrarily adding delay to the initial failure timestamp. Call it **observed retry interval** and document how it is computed.

## 8. Delay Precision Under Load and Outages

### 8.1 Under Low Load

Consumers have small backlogs, schedulers and CPUs are idle, and retries usually start closer to the due timestamp. Small variances still appear due to poll loops and thread scheduling.

### 8.2 During a Retry Storm

A downstream fails for several minutes, sending waves of records to retry topics. Once the service recovers, many records come due together. Retry consumers may lack throughput to handle them all on time.

To mitigate:

- Use appropriate exponential backoff/jitter.
- Limit downstream concurrency.
- Add partitions or consumer capacity if proven to be the bottleneck.
- Apply circuit breakers/rate limiting when needed.
- Monitor backlogs and retry-topic age.
- Avoid deploying all pods at once right as a dependency recovers.

Never simply cut delay from 2 seconds to 200 ms because retries look "slow." That can spike downstream load and worsen p99 lateness.

### 8.3 When a Broker or Network Fails

Records cannot be processed if retry consumers cannot reach the partition leader or if publishers fail to publish. If a retry topic has degraded ISR, produce latency or write errors can climb.

In that case, scheduler lateness metrics may rise, yet the root cause is availability/replication rather than BackOff calculation. Correlate broker health, producer retries, and consumer assignments.

### 8.4 During Deployments or Scaling

Rolling deployments cause consumers to join/leave groups and may trigger rebalances. During that window, records already due wait for assignment.

If p99 latency spikes only during deploys, compare:

- Rebalance timestamps.
- Number of assigned partitions.
- Consumer restart duration.
- Lateness per pod/partition.
- Offset advancement after group stabilization.

Never blame every latency spike on poll timeout settings.

## 9. Timing Precision and Ordering Are Two Separate Requirements

A common mistake is assuming that once a retry delay expires, the record will run ahead of records produced after it. Non-blocking retry does not guarantee this between the main topic and retry topics.

Example:

```text
09:00:00  Topic orders, key=order-1, event A fails
09:00:00  A forwarded to retry topic, due in 10 seconds
09:00:01  Topic orders receives event B with same key=order-1
09:00:02  Main listener processes B successfully
09:00:10  Retry listener reprocesses A
```

For a business flow requiring A before B, this outcome can be invalid even though A's backoff delay executed accurately.

Therefore, evaluate simultaneously:

- **Timing requirement**: do not retry too early; lateness is acceptable.
- **Ordering requirement**: may events with the same key overtake each other?
- **Idempotency requirement**: will reprocessing the same event duplicate side effects?

If strict ordering is mandatory, consider per-partition blocking retry, business-key sequencing, or durable waiting state with coordination. Never trade away business ordering solely for throughput.

## 10. When Does Non-Blocking Retry Not Meet Timing Requirements?

Backoff delays in retry topics suit business retries waiting seconds to minutes where some jitter and lateness are acceptable.

They are not suitable when requirements demand:

- Exact execution at an absolute wall-clock time within a few milliseconds.
- Hard deadlines: every record must run before time T even during cluster rebalances or broker outages.
- Strict ordering across the main topic and retry topics.
- Long-term durable scheduling with rich controls like a business job scheduler.
- Direct scheduling, cancellation, rescheduling, or priority adjustment of tasks.

In those cases, consider other designs:

- A scheduler/queue with explicit delayed-job semantics and defined SLAs.
- A database job table with due_at, ownership, leases, indexes, and controlled workers.
- A workflow engine for multi-step jobs, timeouts, or long timers.
- An orchestration service able to track deadlines and handle overdue work.

Even with a dedicated scheduler, stay realistic about clock skew, availability, and duplicate execution. No ordinary distributed system guarantees hard real-time execution across every failure mode.

## 11. Setting SLOs for Backoff Precision

Instead of promising "exact 2-second delay," define a measurable, actionable SLO.

Example:

~~~text
When retry topics and consumer groups are available,
99% of retry attempts start within 2 seconds
after the eligible time (due timestamp),
measured over a 30-minute window.
~~~

The SLO should specify:

- Which records are measured: all retry attempts or a specific topic's retries.
- Reference timestamp: due timestamp from retry infrastructure.
- Exclusions if any: maintenance, cluster outages, large clock drift.
- Percentile and measurement window.
- Pre-breach alert thresholds.
- How unexecuted records are detected, not just executed ones.

That last point is vital: measuring lateness only on records **already invoked by the listener** creates survivorship bias. If a partition stalls and nothing runs, lateness dashboards can look healthy for lack of data. Also measure the age of overdue yet unprocessed records, backlog, consumer lag, and retry-topic end-to-end age.

### 11.1 Alert Suggestions

Signals to combine:

| Signal | Meaning |
|---|---|
| Rising p99 lateness | Retries running slow relative to due time |
| Late-attempt ratio exceeds threshold | SLO at risk of breach |
| Rising retry topic lag | Capacity not keeping up |
| Partition offsets not advancing | Potential head-of-line blocking or stuck consumer |
| Rising rebalances | Disrupted assignments |
| Rising CPU throttling/GC | Schedulers and listeners starved of CPU time |
| DLT publish errors | Post-retry recovery also failing |
| Clock drift beyond threshold | Due timestamp comparisons unreliable |

Avoid alerting on a single metric alone. For example, rising lateness with low lag can point to thread scheduling, whereas high lag with low throughput points to backlog.

## 12. Testing Precision in Integration Environments

Use real Kafka via Testcontainers or a staging environment to test retry-topic infrastructure. Unit tests invoking the listener directly cannot verify pause/resume, consumer polling, and partition assignment.

### 12.1 Testing Fixed Delay

Suppose delay is 2,000 ms and attempts is 3:

1. Create main and matching retry/DLT topics.
2. Have the consumer listener throw a retryable exception on the first attempt.
3. Record the failure timestamp and due timestamp metadata.
4. Measure when the retry listener starts.
5. Confirm the retry is not invoked before the due mark beyond defined measurement/clock tolerance.
6. Measure lateness and verify it is under a **generous, well-grounded** threshold for the test environment.
7. Confirm the record succeeds on retry.

Never write assertions like "retry ran in exactly 2000 ms" with a 1 ms tolerance. Such tests flake easily because JVMs, brokers, schedulers, and CI all have jitter.

### 12.2 Timing Measurement Idea Example

~~~java
public record RetryObservation(
    String eventId,
    int attempt,
    long dueAtEpochMillis,
    long listenerStartedAtEpochMillis
) {
    public long latenessMillis() {
        return listenerStartedAtEpochMillis - dueAtEpochMillis;
    }
}
~~~

This is a measurement model; it does not supply the due timestamp itself. The test harness must extract the due timestamp properly from retry metadata per Spring Kafka version or record due marks via reliable instrumentation.

An integration assertion to consider:

~~~java
RetryObservation observation = awaitRetryObservation("evt-1001");

assertThat(observation.attempt()).isEqualTo(2);
assertThat(observation.latenessMillis())
    .isGreaterThanOrEqualTo(-allowedClockToleranceMillis);
assertThat(observation.latenessMillis())
    .isLessThan(maxAcceptableTestLatenessMillis);
~~~

Tolerances must fit the test environment and SLO. Even when measuring inside one JVM, account for clock skew if the due timestamp originated on another node.

### 12.3 Testing Exponential Backoff

- Configure exponential attempts and delays.
- Fail the listener across multiple attempts.
- Record the due timestamp and actual run time of each attempt.
- Verify expected delay progression matches configuration.
- Measure lateness **per attempt**, not only total retry duration.
- Confirm the record routes to the DLT when exhausted.

### 12.4 Testing Under Load

- Build up a backlog in the retry topic.
- Increase concurrency up to the useful limit per partition count.
- Measure p50, p95, and p99 lateness as load grows.
- Inspect CPU, GC, broker latency, rebalances, and polls.
- Identify the point where SLO breaches begin.
- Retest while downstream is rate-limited.

Results from low-load environments cannot substitute for capacity testing.

### 12.5 Testing Clock Skew and Restarts

In an isolated environment:

- Observe effects when node clocks drift.
- Restart the retry consumer while records are already eligible.
- Trigger a rebalance while retry topics hold backlog.
- Confirm records process once assignments recover.
- Confirm retry metadata and attempt counts do not vanish unexpectedly.
- Verify duplicate side effects are prevented by idempotency keys.

Never alter system clocks on production nodes for testing. Simulate using test clocks/instrumentation or an isolated environment.

## 13. Investigation Procedure When Retries Run Slower Than Delay

When an operator reports "delay is set to 5 seconds yet records run after 30 seconds," investigate in order:

1. **Identify the record:** event ID, topic, partition, offset, attempt, retry topic.
2. **Identify timestamps:** failure time, retry publish, due timestamp, listener start.
3. **Compute the right metrics:** effective retry wait and lateness relative to due.
4. **Inspect retry topology:** which retry topic, whether one topic holds multiple delay tiers.
5. **Inspect the partition:** backlog, offset advancement, head-of-line blocking.
6. **Inspect the consumer group:** member count, assignments, rebalances, and restarts.
7. **Inspect consumer threads:** poll time, pause/resume, listener duration.
8. **Inspect runtime:** CPU throttling, GC, thread pools, and scheduler queues.
9. **Inspect Kafka:** publish latency, broker/ISR health, leader elections, network.
10. **Inspect clocks:** clock skew between creator and evaluator of due timestamps.
11. **Test controlled changes:** reduce workload, tune concurrency, or adjust partition topology.
12. **Re-measure:** confirm p95/p99 lateness and backlog actually improved.

Never change the backoff delay immediately before knowing which milestone was late. For example, if delay is 5 seconds and records have been due for ages due to retry-topic lag, lowering delay to 1 second only makes records come due sooner and can worsen backlog.

### 13.1 Distinguishing Two Easily Confused Cases

**Case A: Backoff policy misapplied.** Attempt 2 should wait 5 seconds yet the generated due timestamp is only 1 second later. Check annotations, profiles, policies, version, and retry-topic routing.

**Case B: Policy correct, execution late.** Due timestamp is properly 5 seconds later; the listener is invoked 25 seconds later due to backlog and rebalances. Fix capacity/lifecycle, not the backoff calculation.

Both produce the symptom "retry delay not matching expectations," yet require completely different fixes.

## 14. Common Misconceptions

**"The Kafka broker schedules retries down to the millisecond."** No. The Kafka broker stores records in logs; Spring Kafka consumers apply deferral logic.

**"Setting delay = 2000 means the listener starts at exactly 2000 ms."** No. The due mark is only when the record becomes eligible; the listener can run later.

**"Late delays mean Spring Kafka calculated wrong."** Not necessarily. Polling, schedulers, backlog, rebalances, CPU, and clock skew all contribute.

**"Raising concurrency always makes retries more precise."** No. Partition count caps parallelism; downstreams can become the bottleneck.

**"Measuring from the first exception is enough."** No. Distinguish retry publish, due timestamp, and listener start.

**"If p50 lateness is small, every record meets SLA."** No. Tail latency and unprocessed records can be severe.

**"Lowering poll timeout always makes retries exact."** No. It may trim some latency, yet cannot replace capacity, assignments, and schedulers.

**"Exponential backoff means every attempt has an exact predictable execution time from the first failure."** No. Each next attempt's due mark depends on prior failure/publish timing, backoff, and infrastructure conditions.

**"Non-blocking retry preserves event order per business key."** Not by default. Main-topic records can overtake records moved to retry topics.

**"Small retry delays always help the system recover faster."** No. Overly short delays while a downstream is still down can trigger retry storms.

## 15. Design and Operations Checklist

**Backoff design**

- [ ] Distinguish minimum backoff from end-to-end retry latency.
- [ ] Attempts and delays are clearly defined per exception type.
- [ ] Bounded retry duration and recovery/DLT exist when exhausted.
- [ ] Jitter or anti-retry-storm strategies exist where needed.
- [ ] Strict ordering assessed before adopting non-blocking retry.

**Configuration**

- [ ] Retry topic topology and consumer assignments are observable.
- [ ] Concurrency matches partition counts and downstream capacity.
- [ ] Poll, pause/resume, and schedulers are understood for your Spring Kafka version.
- [ ] Clock synchronization and CPU/GC are monitored.
- [ ] Retry publisher and DLT have proper durability settings.

**Measurement**

- [ ] Reliable due timestamps exist per attempt.
- [ ] Listener start, effective retry wait, and scheduler lateness are measured.
- [ ] p50/p95/p99 and max lateness are tracked.
- [ ] Overdue unprocessed records are tracked, not just completed records.
- [ ] Metrics split by topic, partition, attempt, and consumer instance.
- [ ] Retry topic lag, rebalances, producer publishes, and clock skew are monitored.

**Testing and runbooks**

- [ ] Integration tests against real Kafka cover fixed/exponential backoff.
- [ ] Temporal assertions use sensible tolerances, not millisecond-exactness.
- [ ] Backlogs, restarts, rebalances, and CPU contention have been tested.
- [ ] Idempotency and reordering between main/retry topics have been tested.
- [ ] Runbooks distinguish policy miscalculation of due time from execution lateness.

**Backoff delay precision** in non-blocking retry must be understood as the precision of the **eligible time**, plus system variance when actually invoking the listener. Spring Kafka does not guarantee a record is processed to the exact millisecond after failure; delay specifies when retry becomes possible, while polling, pause/resume, schedulers, backlogs, rebalances, and clocks determine when retry actually occurs. Reliable design measures due-to-start lateness, sets realistic SLAs, bounds retries, and protects ordering and business side effects with appropriate mechanisms.

