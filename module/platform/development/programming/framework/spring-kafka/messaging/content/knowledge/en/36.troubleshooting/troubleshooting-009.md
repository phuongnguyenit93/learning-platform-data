# Lag Increasing While Consumer Is Running

An active consumer process does not mean the consumer is processing records fast enough. A listener can be blocked on HTTP/DB, retrying continuously, failing to commit offsets, rebalancing repeatedly, or stuck with a hot partition carrying most of the traffic. In those situations, the application still has threads, logs, and heartbeats, yet consumer lag keeps climbing.

To diagnose properly, look at lag per partition over time, compare record arrival rate against processing and commit rates, and correlate with poll status, listener duration, rebalances, downstream dependencies, and brokers. Raising concurrency or resetting offsets as soon as lag appears usually misses the root cause and can make the incident worse.

This lesson belongs to the **Troubleshooting** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-producing and event-consuming applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, while learning serialization, retries, dead-lettering, transactions, exactly-once, concurrency, and testing to run reliable messaging pipelines.

## 1. What Is Consumer Lag?

Consumer lag is the distance between the position the consumer group has acknowledged and the latest data position on the partition. With the common formula:

\[
\text{lag} = \text{log end offset} - \text{committed offset}
\]

The committed offset is the next position the consumer group will read after restarting or receiving the partition again. The log end offset (LEO) is the end of the partition log as measured by the tool in use.

Example:

| Topic partition | Committed offset | Log end offset | Lag |
| --- | ---: | ---: | ---: |
| orders-0 | 1.200 | 1.250 | 50 |
| orders-1 | 980 | 1.020 | 40 |
| orders-2 | 2.010 | 2.010 | 0 |
| orders-3 | 700 | 850 | 150 |
| **Total** |  |  | **240** |

A lag of 240 means the group is 240 offsets behind the log head across partitions. It does not always equate to 240 unprocessed business events in every case: log compaction, transaction visibility, offset gaps, and how a tool fetches the end offset can all affect interpretation.

Lag also does not directly tell you how long the oldest record has been waiting. A low-traffic partition with lag 20 can hold older events than a high-traffic partition with lag 2,000 that drains rapidly. Track lag, rate of change, and oldest record age together.

## 2. Running Consumer Does Not Mean Making Progress

Distinguish four states:

- **Process alive:** JVM and application have not stopped.
- **Consumer member active:** consumer remains part of the consumer group.
- **Consumer polling:** consumer keeps calling poll and maintaining liveness per Kafka client mechanics.
- **Processing progress:** listener finishes records and committed offsets advance.

A consumer can be alive, sending heartbeats, and part of a `Stable` group while its listener is blocked indefinitely. Another consumer may receive and finish records without acknowledging/committing offsets, causing committed-offset lag to keep climbing.

Therefore, an `UP` health endpoint or a successful startup log is not enough to declare a consumer healthy. You need a progress signal, such as most recent successful processing timestamp, committed offset progression, or record completion rate.

## 3. Distinguishing Rising Lag, High Lag, and Flat Lag

These three patterns point to different investigations:

| Observation | Possible meaning | What to check |
| --- | --- | --- |
| High lag that is decreasing | Consumer is catching up on an older backlog | Estimate catch-up time and monitor trend |
| Low lag that rises steadily | Processing rate is lower than arrival rate | Compare arrival rate and processing rate |
| High lag that stays nearly flat | Consumer is matching producer speed or is stuck at one point | Check per-partition lag and oldest record age |
| Lag is 0 yet events are still delayed | Possibly checking wrong group/topic, early commits, or events not reaching partition | Check group ID, offset commits, and producer timestamps |
| Lag spikes then drops quickly | Producer burst, rebalance, or metric sampling | Correlate timestamps and event rates |

Do not alert solely on a fixed absolute lag threshold. A high-traffic topic may routinely carry thousands of offsets of lag with low latency; a low-traffic topic with lag 30 might have events waiting for minutes.

## 4. Start with Per-Partition Lag

Use the consumer group tool to inspect committed offsets, log end offsets, and lag:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
~~~

Read the `CURRENT-OFFSET`, `LOG-END-OFFSET`, and `LAG` columns. Capture output at multiple timestamps to see which partitions grow and how fast.

Inspect group state and members if your Kafka distribution supports those options:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service \
  --state

kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service \
  --members \
  --verbose
~~~

Option names and output formatting may vary by Kafka version/distribution. Run `--help` on the exact CLI version deployed. Do not run offset-reset commands as a first diagnostic step.

Focus on the partition whose lag grows fastest. If all partitions grow similarly, overall capacity may be insufficient. If only a few partitions grow, inspect key distribution, partition assignment, and the specific record blocking progress.

## 5. Measure Arrival Rate vs. Processing Rate

Lag grows when new records arrive faster than the consumer completes and commits offsets over the same window.

Let:

- \(\lambda\): rate of records written to the topic, in records/second.
- \(\mu\): rate of records completed and acknowledged by the consumer, in records/second.
- \(L\): current backlog, measured in offsets or equivalent records in scope.

Approximately:

\[
\frac{dL}{dt} = \lambda - \mu
\]

If \(\lambda > \mu\), lag rises. If \(\mu > \lambda\), the consumer can drain the backlog. With backlog \(L\) and sustained processing faster than arrival, approximate catch-up time is:

\[
T_{\text{catch-up}} = \frac{L}{\mu-\lambda}
\]

Example: backlog of 60,000 records, producer writes 800 records/sec, consumer acknowledges 1,000 records/sec. The consumer has only 200 records/sec of spare capacity, so it needs roughly 300 seconds to catch up if traffic stays steady.

The formula is only an estimate. Reality also depends on partition distribution, bursts, retries, rebalances, batch size, record size, and downstream dependencies. Calculate per partition when traffic is skewed.

## 6. Verify Group ID and the Right Consumer Group

A simple operational mistake is watching the wrong group. The application might run with a profile- or environment-specific group ID while dashboards still watch an old group.

Check:

- `spring.kafka.consumer.group-id` in runtime configuration.
- `groupId` on `@KafkaListener`, if the annotation overrides the default group.
- Active Spring Boot profiles.
- Environment variable or ConfigMap/secret overrides.
- Actual consumer groups in `kafka-consumer-groups.sh` output.
- Whether an old consumer or side job shares the same group.

Example configuration:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
~~~

If `@KafkaListener(groupId = "order-service-v2")` is declared, inspect that corresponding group. A dashboard showing low lag on group A does not prove group B is keeping up.

Do not rename the group ID just to zero out lag. A new group starts at a different offset per `auto.offset.reset`, causing replays or skipped data depending on configuration and offset state.

## 7. Check Consumer Group State, Assignments, and Rebalances

A `Stable` group state only means membership/assignments are steady at the moment of inspection. It does not prove the listener runs fast or offsets are advancing.

Check:

- Number of active members in the group.
- Number of partitions assigned to each member.
- Whether any partitions are unassigned.
- Whether rebalances happen repeatedly.
- Whether any member has abnormal poll intervals or processing durations.
- Whether consumer instances start/stop repeatedly.

Frequent rebalances cut throughput because consumers revoke/assign partitions, wrap up or discard in-flight work, and rebuild fetch state. If lag rises in waves alongside rebalances, investigate membership causes before adding more consumers.

Common causes include exceeding `max.poll.interval.ms`, session timeouts, repeated deploys/restarts, network interruptions, and membership churn.

## 8. Slow or Blocked Listeners

Listeners execute synchronously on the consumer thread. If a listener waits too long on HTTP, database, Redis, locks, or futures, the consumer cannot keep polling on schedule.

Example:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderEvent event) {
    inventoryClient.reserve(event);
    billingClient.createInvoice(event);
    orderRepository.updateStatus(event.orderId(), "PROCESSED");
}
~~~

Three sequential synchronous calls can make each record expensive. If a dependency has a long timeout or no timeout, lag rises even though the JVM stays alive.

Measure duration separately for:

- Total listener invocation.
- Each dependency HTTP request.
- Database queries and connection pool wait time.
- Lock/semaphore waits.
- Serialization/deserialization.
- Output event publishing time.
- Batch processing duration.

Set timeouts for connect/read/request, queries, and connection acquisition. Avoid `Thread.sleep`, `Future.get`, or manual retry loops inside listeners.

## 9. `max.poll.interval.ms` and Consumers Missing Poll Deadlines

`max.poll.interval.ms` caps the maximum gap between `poll()` calls from a consumer group member. If slow listener work keeps the consumer thread from polling again in time, the member can be considered stalled and its partitions reassigned to another consumer.

Heartbeats still run on a background thread in modern Kafka clients, so checking heartbeats alone cannot detect a blocked listener. Poll progress and listener duration must be monitored separately.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
~~~

Lowering `max.poll.records` shrinks the work per poll and batch duration. Raising `max.poll.interval.ms` makes sense only when a workload has bounded, measured long processing times. Never raise it to mask a dependency that can hang indefinitely.

## 10. Batch Size and Single-Poll Processing Duration

For record listeners, the container may dispatch multiple records from one poll before polling again. For batch listeners, a single invocation processes the whole batch. Therefore, one poll cycle's duration can exceed single-record processing time.

Example:

| Parameter | Value |
| --- | ---: |
| `max.poll.records` | 200 |
| Average processing time per record | 25 ms |
| Approximate sequential duration | 5 seconds |
| Overhead | serialization, dispatch, commit, scheduling |

When records are large or processing has high tail latency, large batches raise memory pressure and stretch poll cycles. Lowering batch size can improve liveness at the cost of more polls and overhead. Measure before and after changes.

Batch listeners need dedicated inspection: one bad record can trigger retries or rollbacks across the batch depending on the error handler and config. One poison record can cause many other records to be reprocessed.

## 11. Partition Skew and Hot Partitions

Kafka allows only one consumer group member to own a partition at a time. When key distribution is uneven, one partition can receive most of the traffic while others sit nearly idle.

Example:

| Partition | Arrival rate | Processing rate | Lag trend |
| --- | ---: | ---: | --- |
| orders-0 | 100/s | 120/s | Falling |
| orders-1 | 900/s | 250/s | Rising fast |
| orders-2 | 80/s | 100/s | Falling |
| orders-3 | 90/s | 110/s | Falling |

Overall consumer capacity may sit idle while partition 1 keeps accumulating lag. Adding more consumers will not help if the hot partition remains owned by one member and per-partition ordering must hold.

Inspect producer keys, partitioner, frequent key counts, and record sizes. One ultra-frequent key creates a hot partition. Changing partition keys or adding partitions requires evaluating ordering, key affinity, and remapping of existing keys.

## 12. Concurrency Cannot Exceed Partition Limits

Spring Kafka can configure concurrency on listener containers:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    return factory;
}
~~~

Within a consumer group, useful active consumers cannot exceed assigned partitions. If a topic has 4 partitions and concurrency is 12, at most 4 consumers get partitions; the remaining child consumers sit idle.

Raising concurrency can boost throughput when enough partitions exist and downstream has spare capacity. It does not parallelize a single partition in order. If listeners are blocked on a database pool, raising concurrency can overload the pool further and accelerate lag growth.

Check partition counts, member counts, assignments, and downstream capacity before scaling.

## 13. Offsets Not Committing Even After Listener Completes

Lag is commonly computed from committed offsets, not just how many records the listener executed. If the listener finishes yet offsets are not acknowledged, lag remains high.

Check `AckMode` and acknowledgment:

| Setting | Behavior to verify |
| --- | --- |
| `RECORD` | Offset is acknowledged after each individual record listener succeeds. |
| `BATCH` | Offset is acknowledged per poll batch once the batch finishes. |
| `MANUAL` | Listener must call acknowledge per application logic. |
| `MANUAL_IMMEDIATE` | Acknowledge can commit right away when invoked on the consumer thread, depending on container configuration. |

With manual acknowledgment, check every code path: success, exception, early return, timeout, and asynchronous completion. If one branch forgets to acknowledge, committed offsets can freeze even though logs show the business method ran.

In Spring Kafka, the container normally manages offset commits; do not enable Kafka client auto-commit casually. Use matching production semantics when diagnosing lag.

## 14. Async Handoffs and Premature Offset Commits

A misleading pattern:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(OrderEvent event) {
    executor.execute(() -> orderService.process(event));
}
~~~

The listener returns immediately after enqueueing. With standard acknowledgment, the container can commit the offset before the worker finishes. Lag may drop even though actual work is unfinished; if the process crashes, in-RAM tasks are lost.

Conversely, with async acknowledgment, if one task fails to complete or offsets are acknowledged out of order, committed offsets can be held back and lag grows.

Offload only with an explicit contract:

- Async listener return types supported by your Spring Kafka version.
- Proper manual/async acknowledgment container configuration.
- Durable handoff into a database/outbox/work topic before acknowledging input.
- Idempotent workers keyed by event ID with restart recovery.

Never treat an in-memory queue as durable storage.

## 15. Retries and Backoff Driving Lag Up

Blocking retries hold the partition/consumer on the failing record before advancing to the next record per policy. When downstream is failing and every record retries multiple times with long backoff, useful throughput collapses.

For example, `FixedBackOff(5000, 3)` adds many seconds of delay per record before recovery, depending on retry counts and version semantics. Consecutive failing records rapidly push lag upward.

Check:

- Retry counts by topic and exception class.
- Backoff intervals and attempt counts.
- Percentage of records recovering successfully.
- DLT publish latency.
- Whether a poison record loops on the same partition.
- Whether nested retries exist across HTTP client, service, and Kafka handler.

Classify exceptions. Transient errors need bounded retries; permanent data errors should recover to a DLT per policy. Never retry a poison record infinitely because it stalls the partition.

## 16. Retry Topics and DLTs Affect How You Read Lag

Non-blocking retry topics move failing records to retry topics so the source partition can keep advancing through newer records. Source-topic lag may drop while records remain pending in retry topics.

Therefore, dashboards watching only the source topic may look healthy while real backlog sits in retry topics. Monitor lag and oldest record age across retry topics and DLTs too, along with pending recovery counts.

With retry topics, ordering can shift: later events may be processed ahead of events waiting for retry. If business rules require per-aggregate ordering, add sequence/version checks or keep sequential processing where needed.

A DLT should not be treated as unowned infinite storage. Monitor DLT arrival rates, record age, replay status, and operational remediation workflows.

## 17. Consumer Pause or Active Backpressure

A listener container can be paused when internal queues fill up or downstream becomes unavailable. The process stays alive and the consumer may keep polling to hold group membership, yet paused partitions deliver no new records to the listener.

Check:

- `isPauseRequested()` and `isConsumerPaused()`.
- Active pause reason.
- Pause start time and duration.
- Queue depth, capacity, and in-flight task counts.
- High/low watermarks.
- Whether a component resumes too early or pauses repeatedly.

During long pauses, rising lag is expected behavior. Fix why queues are not draining or why dependencies have not recovered. Never force-resume just to make lag metrics drop while downstream remains overloaded.

## 18. Repeated Deserialization or Listener Errors

Un-deserializable records can fail before the listener method is invoked. Without proper error handling, bad records can retry or stall partition progress.

Check:

- `ErrorHandlingDeserializer` and delegate deserializers.
- Schema/JSON versions sent by producers.
- Key and value deserialization failures.
- Exception headers and raw bytes in DLT payloads.
- `DefaultErrorHandler` or `AfterRollbackProcessor` attached to the container.
- Logs by topic, partition, and offset.

If listener invocation counts stay flat while lag stays stuck at one offset, inspect deserialization and container error handling. Do not look only inside business listener logs because the listener may never have received an object.

## 19. Broker, Network, and Fetch Throughput

A consumer may be healthy yet fetch records slowly due to broker or network constraints. Investigate:

- Broker request latency and request queues.
- Disk I/O, page cache, and network throughput.
- Under-replicated partitions and ISR churn.
- Broker availability and leader movement.
- Network packet loss, DNS, and TLS handshakes/reconnects.
- Consumer fetch throttling from quotas.
- `fetch.min.bytes`, `fetch.max.wait.ms`, `max.partition.fetch.bytes`, and `fetch.max.bytes`.
- Large record sizes or compression/decompression overhead.

Do not bump fetch sizes blindly. Too-low fetch settings hurt throughput; too-high settings raise memory pressure. Measure bytes consumed rate, fetch latency, fetch rate, and broker metrics before tuning.

If consumers across multiple groups slow down together on the same broker/topic, suspect brokers, network, or producer bursts rather than a single listener bug.

## 20. CPU, Garbage Collection, and Memory Pressure

Listeners can slow down due to CPU-bound serialization, compression, validation, or business logic. JVMs can also pause from garbage collection or high allocation rates.

Check:

- Container CPU utilization and CPU throttling.
- Heap usage, allocation rate, and GC pauses.
- Thread counts and context switching.
- Thread dumps of consumer threads.
- Object sizes of payloads and batches.
- Serialization/deserialization CPU cost.
- Queued and in-flight object counts.

Low CPU with high lag often points to I/O waits, locks, or dependency pools; high CPU with high listener duration points to CPU-bound work. Long GC pauses create periodic poll delays and rebalances.

Use a profiler or Java Flight Recorder when needed. Do not bump heap or thread pools before identifying allocations and bottlenecks.

## 21. Transactional Consumers and `read_committed`

For consumers configured with `isolation.level=read_committed`, Kafka delivers only records from committed transactions and prevents reading past a partition's Last Stable Offset (LSO) while a transaction remains open.

Consequently, on topics with transactional producers, raw log end offset and consumer position can diverge in how lag tools display them. A long-running or stuck producer transaction holds back the LSO, keeping subsequent records invisible to `read_committed` consumers even though the broker already appended them.

Check:

- Producer transaction commit/abort rates.
- Transaction duration and timeouts.
- Producer fencing or transactional ID collisions.
- Long-open transactions on partitions.
- Consumer isolation level.
- LEO, high watermark, and LSO via appropriate broker tools.

Do not assume a listener is slow based solely on LEO under transactional workloads. Determine whether the consumer is capped by LSO or genuinely failing to process visible records.

## 22. Producer Speedups or Traffic Bursts

Lag can climb even at steady consumer capacity if producers suddenly surge. Batch imports, upstream retry storms, or newly scaled producers can push arrival rates past processing rates.

Compare:

- Producer records/sec and bytes/sec.
- Producer instance counts.
- Newly started batch or replay jobs.
- Changes in record size.
- Upstream retries.
- Key and partition distribution.
- Exact timestamp when lag began climbing.

If consumer throughput stayed constant while producer throughput doubled, the issue may be capacity planning or a producer burst. Decide whether to scale consumers/partitions, rate-limit producers, or smooth traffic per SLAs.

Do not blindly scale consumers if a hot partition or downstream bottleneck is already saturated.

## 23. Metrics to Monitor

Monitor consumer, listener, and downstream metrics together:

| Category | Suggested metrics | Question to answer |
| --- | --- | --- |
| Lag | Lag by group/topic/partition, oldest record age | Where is the backlog and how long has it waited? |
| Poll | Time between polls, last poll age, poll rate | Is the consumer still polling? |
| Processing | Listener duration p50/p95/p99, records processed rate | How fast is the listener processing? |
| Fetch | Records/bytes consumed rate, fetch latency/rate | Is the consumer fetching fast enough from brokers? |
| Group | Assigned partitions, rebalance rate, failed rebalances | Are assignments stable? |
| Commit | Commit rate, commit latency, commit failures | Are offsets advancing? |
| Retry | Delivery attempts, backoff time, DLT rate | How much time is spent on failures? |
| Downstream | HTTP latency, DB query/pool wait, error rate | Which dependency slows the listener down? |
| Runtime | CPU, GC pauses, heap, thread states | Is the JVM bottlenecked? |

The Kafka client exposes rich metrics via JMX. Exact metric names and tags can vary across Kafka client versions; inspect the runtime metric catalog instead of hardcoding dashboards from another version.

Useful Kafka consumer metrics during investigation include `records-consumed-rate`, `records-lag-max`, `fetch-rate`, `fetch-latency-avg`, `time-between-poll-avg`, `time-between-poll-max`, `last-poll-seconds-ago`, `assigned-partitions`, `rebalance-rate-per-hour`, and `commit-latency-avg`. Metric names and MBean groups can change across Kafka client versions; verify in runtime JMX before creating alerts.

Spring Kafka integrates with Micrometer to observe listeners and Kafka clients. Use listener ID, group ID, client ID, and topic as bounded dimensions. Avoid putting event IDs or offsets into metric labels due to extreme cardinality.

## 24. Ordered Diagnostic Runbook

When a rising-lag alert fires, follow this sequence:

~~~mermaid
flowchart TD
    A[Lag alert] --> B[Verify group and topic]
    B --> C[Compare lag per partition]
    C --> D[Measure arrival and commit rates]
    D --> E[Check assignment and poll progress]
    E --> F[Inspect listener and downstream]
    F --> G[Check ack, retry, pause and broker]
    G --> H[Apply targeted change]
    H --> I[Verify lag and record age recover]
~~~

1. **Verify the right group/topic:** check runtime group ID and monitored topic.
2. **Inspect per-partition lag:** see whether all partitions or only a few are growing.
3. **Measure rates:** compare records in/sec with records processed/committed per second.
4. **Inspect the group:** state, members, assignments, and rebalance rate.
5. **Inspect poll progress:** last poll, time between polls, and `max.poll.interval.ms`.
6. **Inspect listener duration:** look for HTTP/DB/lock waits, CPU, and oversized batches.
7. **Inspect offsets:** `AckMode`, manual ack, commit failures, and async completion.
8. **Inspect retries/recovery:** retry attempts, backoff, DLT, and deserialization failures.
9. **Inspect pause/backpressure:** pause reason, queue depth, and worker capacity.
10. **Inspect broker/network:** fetch latency, quotas, broker health, and traffic.
11. **Pick a targeted fix:** trim batches, fix dependencies, scale appropriately, or throttle producers.
12. **Monitor catch-up:** confirm lag drops and oldest record age returns within SLA.

Record timestamps, partitions, committed offsets, end offsets, listener durations, and event rates before changing config. That lets you measure each change's impact.

## 25. Choosing Remediation by Root Cause

| Root cause | Preferred remediation | What to avoid |
| --- | --- | --- |
| Listener calls slow HTTP/DB | Timeouts, query optimization, bulkheads, proper pools | Raising concurrency indefinitely |
| Batch/poll cycle too long | Lower `max.poll.records`, optimize batching | Only raising max poll interval |
| Not enough parallel partitions | Re-evaluate partition/key design | Scaling consumers past partition count |
| Hot partition | Fix key distribution or isolate hot keys | Simply adding more consumers |
| Excessive retries/backoff | Classify exceptions, cap retries, DLT | Infinite retries |
| Offsets not committing | Fix `AckMode`/manual ack/commit failures | Resetting offsets to hide metrics |
| Consumer paused | Fix queue/downstream drain and pause cause | Force-resuming |
| Slow broker/network | Investigate brokers, fetches, and quotas | Randomly bumping fetch sizes |
| Producer burst | Rate-limit, batch, capacity planning | Scaling consumers without checking downstream |
| JVM/CPU/GC | Profile, reduce allocations, optimize code | Adding threads when CPU is saturated |

After fixing, watch lag trends and record age across a representative window covering normal and peak traffic. A brief dip in lag does not prove the root cause is solved.

## 26. Do Not Reset Offsets to Zero Out Lag

`--reset-offsets` skips data or replays data depending on the chosen target. It alters where the consumer group reads—it does not increase throughput.

Reset only when there is an explicit business decision to skip or replay data, with exact group/topic/partitions identified and a duplicate-handling plan ready. In production, save current offsets, scope impact, stop consumers cleanly, and obtain operational approval.

If lag climbs because the listener is blocked or offsets fail to commit, resetting offsets merely hides symptoms and risks losing records that needed processing.

## 27. Checklist to Prevent Rising Lag

Before promoting a consumer to production, verify:

1. Dashboards show lag and oldest record age per partition.
2. Metrics track records in/sec and records processed/committed per second.
3. Runtime consumer group ID is clearly observable.
4. Alerts cover abnormal rebalances and poll intervals.
5. Listeners enforce timeouts/deadlines on all I/O dependencies.
6. `max.poll.records` matches record/batch processing durations.
7. `max.poll.interval.ms` has safety margin based on measured workloads.
8. Concurrency matches partition counts and downstream capacity.
9. Partition keys do not create persistent hot partitions.
10. `AckMode` and manual acknowledgments have integration tests.
11. Retries are bounded, exceptions clearly classified, and DLTs monitored.
12. Deserialization failures have a recovery path.
13. Async handoffs use proper acknowledgment or durable queues.
14. Pause/backpressure exposes high/low watermarks and pause reasons.
15. Broker/network/fetch metrics are monitored.
16. Runbooks identify which partition and member cause lag.
17. Offset resets are never used as a default firefighting reflex.

Rising lag while a consumer runs usually means processing and offset acknowledgment cannot keep pace with incoming data, or the consumer is throttled by partitions, retries, commits, brokers, or downstream dependencies. Start with per-partition lag, group assignments, and in/out record rates; then inspect poll progress, listener duration, acknowledgments, and dependencies. Only scale or alter offsets after pinpointing the bottleneck and understanding the impact on ordering, duplicates, and required records.

