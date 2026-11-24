# Rebalance due to slow poll

In Spring Kafka, a listener may process records correctly from a business standpoint yet still trigger a **consumer group rebalance** if it takes too long to return to the `KafkaConsumer.poll()` loop. This happens when processing large batches, making slow database or HTTP calls, holding locks for a long time, pausing in a debugger, lacking CPU, or using backoffs that block the consumer thread for extended periods. Kafka interprets the application's failure to call `poll()` on time as a sign that the member is no longer progressing fast enough to keep owning partitions.

Rebalances caused by slow polling are particularly dangerous because the failure may not show up immediately inside the business method. Side effects may already be written to the database, yet the partition is revoked before offsets commit; another consumer then re-reads the record, leading to duplicate processing. Increasing retry counts or increasing concurrency does not solve the root cause by itself. You need an accurate understanding of **`max.poll.interval.ms`**, **`session.timeout.ms`**, listener execution time, and how Spring Kafka organizes consumer threads.

## 1. Consumer groups require both heartbeats and poll progress

A consumer in a Kafka group must prove two distinct things:

1. **It is alive and connected to the group coordinator** via the heartbeat mechanism or corresponding group protocol.
2. **The application keeps calling `poll()` within the allowed deadline**, demonstrating that the consumer is not stuck indefinitely processing records.

The two mechanisms use different time limits:

| Property/mechanism | Meaning | If violated |
|---|---|---|
| `max.poll.interval.ms` | Maximum time between consecutive `poll()` calls in the standard consumer group model | Kafka treats the member as not progressing; may leave group / have partitions revoked and rebalance |
| `session.timeout.ms` | Deadline the coordinator waits for a member's heartbeat per the active group protocol | Member loses session, partitions are reassigned |
| `heartbeat.interval.ms` | Consumer-side heartbeat cadence in the classic group protocol | Tunes liveness check frequency, **does not replace** poll interval |
| `max.poll.records` | Maximum number of records returned per `poll()` call | Does not directly cause rebalance; an overly large batch pushes processing time past poll interval |
| `pollTimeout` of Spring listener container | How long a single Kafka `poll()` call may wait for data | Completely different from `max.poll.interval.ms`; not a business processing time limit |

In modern Kafka clients, heartbeating can run independently of business processing. Therefore **still sending heartbeats while not polling frequently enough** is a real scenario. Kafka does not let a consumer keep partitions forever just because heartbeats are still arriving once `max.poll.interval.ms` is exceeded.

In the **classic consumer group protocol** with dynamic members, when `max.poll.interval.ms` expires, the consumer typically leaves the group proactively and the coordinator reassigns partitions. With **static membership** (`group.instance.id`), when exceeding the poll interval, the consumer may stop sending heartbeats yet not have its partitions reassigned until the session timeout expires. Exact timing details and heartbeat mechanics also depend on protocol/client version; do not treat setting `group.instance.id` as a way to disable poll limits.

## 2. Why is Spring Kafka prone to slow polls with synchronous listeners?

In a standard synchronous record listener setup, the container calls `poll()`, fetches a set of `ConsumerRecord`s, and invokes the `@KafkaListener` method sequentially. Most record-processing logic runs on the container's consumer thread. **While the listener runs synchronously, that thread cannot return to `poll()`**.

```text
Consumer thread for a partition assignment
           |
           v
KafkaConsumer.poll() -> receives multiple records
           |
           +--> listener(record 1) -> database
           +--> listener(record 2) -> HTTP API
           +--> listener(record 3) -> computation
           +--> ...
           |
           v
Next KafkaConsumer.poll()

<---------------- gap between two polls ---------------->
```

A `ConcurrentMessageListenerContainer` can create multiple child containers/consumer threads per concurrency configuration. Each Kafka consumer still has its own `poll()` loop and timeout budget. Increasing concurrency does not turn a blocking listener invocation into non-blocking, nor does it split a batch already delivered to one consumer while it is processing.

This is a failure in the **consumer's processing loop**, not necessarily a slow broker. The broker may be completely healthy, the topic has data, heartbeats are still recorded, yet the consumer thread is held inside a database, REST client, or business lock.

## 3. Timeline: from slow poll to rebalance

Suppose a consumer uses `max.poll.interval.ms=300000` (5 minutes) and `max.poll.records=500`. Each record averages 800 ms to process synchronously. One poll returns 500 records; total time for business processing alone is around 400 seconds, excluding commits, serialization, GC, or retries.

```text
t=0s       poll() returns 500 records
           |
           v
t=0..300s  listener processes sequentially, has not polled again
           |
t≈300s     exceeds max.poll.interval.ms (300 seconds)
           |
           v
           member loses authority to keep owning assignment
           / may leave group; rebalance begins
           |
           v
t≈400s     business method finally finishes
           |
           v
           offset commit may fail because generation/assignment changed
```

The consequence depends on member type, protocol, and when the group finishes rebalancing. Another consumer may be assigned the revoked partition and re-read from the **last committed offset**, while the old consumer is still finishing side effects for preceding records.

Example partition `orders-2`:

| Offset | Possible progression |
|---:|---|
| 100 | Consumer A processed and committed successfully |
| 101 | Consumer A wrote to database successfully but has not committed offset |
| 102 | Consumer A is in a slow downstream call |
| — | Poll interval expires; partition is reassigned to consumer B |
| 101 | Consumer B may re-read from committed offset and process duplicate |

Do not conclude that Kafka "improperly delivered the same record twice against the rules". Under standard delivery semantics, uncommitted offsets can be redelivered when assignments change or processes restart. This is **at-least-once delivery**, requiring idempotent side effects.

## 4. Distinguishing slow-poll rebalance from heartbeat loss

Both incidents can manifest as consumers losing partitions, rising lag, and rebalance logs, yet the fixes differ.

| Observation | Suspect `max.poll.interval.ms` | Suspect session/heartbeat |
|---|---|---|
| Listener runs long in DB/API | Very likely | Not necessarily |
| Log contains `consumer poll timeout has expired` | Strong evidence | Not primary indicator |
| `time-between-poll-max` near/above threshold | Strong evidence | May not increase |
| Consumer thread blocked on lock/GC or retry sleep | Very likely | Possible indirectly |
| Network timeout or coordinator misses heartbeats | Can co-occur | Must investigate |
| Partitions reassigned while process still alive | Possible | Possible |
| `CommitFailedException` appears after rebalance | Possible consequence | Also possible consequence |

A common indicator in Kafka client logs is a message similar to:

```text
consumer poll timeout has expired
```

The exact message varies by client version and may include `max.poll.interval.ms`, reason for leaving the group, or hints to raise the interval/reduce `max.poll.records`. Correlate logs with listener processing duration rather than relying on a single warning line.

If rebalancing coincides with a rolling deployment, consumer restart, or broker outage, do not jump to blaming slow polling. Rebalances can also occur from group membership changes, topic partition count increases, or normal assignment mechanics.

## 5. `max.poll.records` and processing time budget

A useful initial estimate:

```text
T_poll_gap ≈ T_process_records + T_error_handling
             + T_commit + T_runtime_overhead

T_process_records ≈ N_records × T_per_record

Operational requirement:
T_poll_gap must be smaller than max.poll.interval.ms with a sufficient safety margin
```

Example:

| Metric | Assumed value |
|---|---:|
| `max.poll.interval.ms` | 300,000 ms (300 seconds) |
| Processing time p99/record | 700 ms |
| Records in one poll | 500 |
| Estimate 500 × 700 ms | 350 seconds |
| Conclusion | Exceeds 300-second budget before counting overhead |

This is not a statistical guarantee: multiplying per-record p99 by record count is a conservative estimate, and actual per-batch latency distributions must be measured. With batch listeners, there may be bulk API calls or shared transactions, so total time is not necessarily the sum of individual record latencies. Even so, the formula clarifies why a large `max.poll.records` can trigger poll timeouts.

The first fix is usually **bounding records per poll** and reducing synchronous processing time, rather than raising `max.poll.interval.ms` indefinitely. Smaller record counts shorten each poll loop though they can increase overhead, so measure throughput and latency after changing.

## 6. Spring Boot configuration: limiting poll and batch

Example configuration for a standard record-processing listener:

```properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=order-worker
spring.kafka.consumer.enable-auto-commit=false

# Do not fetch too many records per poll if each record takes long to process.
spring.kafka.consumer.max-poll-records=100

# Kafka client property: deadline between poll calls.
spring.kafka.consumer.properties[max.poll.interval.ms]=300000

spring.kafka.listener.ack-mode=record
spring.kafka.listener.concurrency=3
```

The numbers above are illustrative. `max.poll.interval.ms` must cover reasonable p99/worst-case processing, retries, and overhead; `max.poll.records` must balance batch efficiency with returning to `poll()` on time.

`spring.kafka.listener.concurrency=3` allows up to three consumer child containers on the default factory under matching conditions, yet actual utilization depends on assigned partitions. If a group only receives two partitions, raising concurrency to 12 does not create 12 useful processing lanes for those two partitions.

A `@KafkaListener` using the default factory can be written as:

```java
@KafkaListener(topics = "orders", groupId = "order-worker")
public void onOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
```

In the example, `OrderEvent` and `orderService` are hypothetical classes/services; deserializers, schemas, exception handlers, and downstream timeouts require separate configuration. If the application declares multiple `ConsumerFactory` or container factory beans, confirm the listener uses the right factory receiving these properties. A global config can be overridden by a dedicated bean.

## 7. Customizing a dedicated `ConsumerFactory` per workload

When one group of listeners has longer processing times, you can create a dedicated `ConsumerFactory` instead of raising global `max.poll.interval.ms` across the whole system.

```java
@Bean("slowOrderConsumerFactory")
ConsumerFactory<String, OrderEvent> slowOrderConsumerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> props =
            new HashMap<>(kafkaProperties.buildConsumerProperties());

    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 25);
    props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 600_000);

    return new DefaultKafkaConsumerFactory<>(props);
}

@Bean("slowOrderListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
slowOrderListenerContainerFactory(
        @Qualifier("slowOrderConsumerFactory")
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}
```

Listener explicitly attached to the factory:

```java
@KafkaListener(
        topics = "slow-orders",
        groupId = "slow-order-worker",
        containerFactory = "slowOrderListenerContainerFactory")
public void handleSlowOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
```

The configuration snippet uses `KafkaProperties` to inherit client settings such as bootstrap, security, and deserializers; `buildConsumerProperties()` may have different overloads depending on Spring Boot version. Check runtime client config to confirm properties actually reached the consumer.

Raising `max.poll.interval.ms` from 5 to 10 minutes is a **trade-off**: a member can hold partitions longer when the application makes no progress. If a consumer truly hangs, detecting and reassigning work can be slower. Only raise it after controlling slowness causes and defining clear SLOs.

## 8. Common bug: calling downstream without timeouts

One of the most frequent causes is a listener calling a database or HTTP service without timeouts at each layer. An unbounded connection timeout or a query waiting on a lock can hold the consumer thread longer than `max.poll.interval.ms`.

Example of what not to do:

```java
@KafkaListener(topics = "orders")
public void consume(OrderEvent event) {
    // HTTP call may wait a very long time if no timeout is configured.
    externalInventoryClient.reserve(event);
    orderRepository.save(event.toOrder());
}
```

A better design requires timeouts, retry budgets, and isolation for each dependency:

```java
@KafkaListener(topics = "orders")
public void consume(OrderEvent event) {
    // Adapter must have explicit connect/read/request timeouts.
    inventoryAdapter.reserveWithBoundedTimeout(event);
    orderService.saveIdempotently(event);
}
```

In the example, `reserveWithBoundedTimeout` is an application-defined API. Actual timeouts must be set on the corresponding HTTP client/connection pool, database driver/query, or proxy; naming the method does not give the call a timeout on its own.

Calculate an **end-to-end budget**. If a record allows three HTTP retries, each with a 30-second read timeout plus a 10-second backoff between attempts, total time can exceed 100 seconds for a single record. One poll fetching five similar records can exceed 5 minutes very quickly.

## 9. Blocking retries, backoff, and poll interval

`DefaultErrorHandler` can retry records with `FixedBackOff`, exponential backoff, or other logic. If a listener fails and the container waits a long time before retrying the same record, total time before returning to `poll()` increases. Setting a long retry policy without accounting for `max.poll.interval.ms` can trigger rebalances right while the application is trying to recover.

Example:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(30_000L, 4L));

    handler.addNotRetryableExceptions(
            InvalidOrderPayloadException.class);

    return handler;
}
```

The wait intervals alone for four retries can reach 120 seconds, not counting listener work time on each attempt. If one attempt takes 60 seconds and there are multiple attempts, total time easily hits 300 seconds.

In Spring Kafka, how the error handler waits for backoffs and interacts with polling can differ by version/configuration. For long waits, there is a **container-pausing backoff handler** mechanism (`ContainerPausingBackOffHandler`) that lets the container pause the consumer and continue calling `poll()` during the wait, instead of blocking-sleeping the thread across the entire backoff window. This is an option worth considering when you want to maintain group membership during prolonged retries.

With non-blocking retries via `@RetryableTopic`, failed records are published to a retry topic and the source consumer can move on to the next record, reducing source partition stalls from long backoffs. In return, **relative processing order can change**, because subsequent records are processed ahead of the failed record waiting on the retry topic. Do not apply this solution if the business strictly requires processing events with the same key in strict order without suitable versioning/state mechanisms.

## 10. Pausing the consumer is not stopping polling

A common misconception is "pause the consumer to avoid rebalance". A Kafka consumer can be paused to temporarily stop fetching records on partitions, yet to maintain membership the container **must still continue calling `poll()`** on time.

```text
Pause + still poll periodically:
  temporarily receives no new records
  keeps connection, heartbeat/membership
  can resume when downstream recovers

Infinite thread sleep/blocking:
  listener has not returned to poll()
  easily exceeds max.poll.interval.ms
  partitions may be reassigned
```

The Spring Kafka listener container has APIs managing `pause()`/`resume()` and per-partition pause mechanisms; prefer controlling through the container registry or appropriate container APIs instead of calling `consumer.pause()` directly from another thread. `KafkaConsumer` is not thread-safe; manipulating the consumer from an async processing thread can cause races or errors.

Pause is not a tool to "stretch" time for a listener **currently blocking the same consumer thread**. If the thread is still inside an unreturned database call, the container cannot magically resume its `poll()` loop just because pause was flagged. You must bound processing time, move work to an async design with safe boundaries, or use a container-supported backoff handler.

## 11. Async processing is not automatically safe

Offloading work to a thread pool can let the consumer thread return to `poll()` sooner, yet introduces new risks: offsets committed before processing finishes, per-partition ordering altered, memory growing due to task backlog, or partitions revoked while tasks are still running.

Anti-pattern example:

```java
@KafkaListener(topics = "payments")
public void onPayment(PaymentCaptured event) {
    executor.execute(() -> paymentService.capture(event));
    // Method returns immediately. Container may treat the record as finished.
}
```

With a synchronous listener and automatic ack mode, the method returning can cause the container to commit offsets before the async task completes. If the process crashes right after committing, unprocessed tasks can be lost from consumption progress. This is a **risk of losing processing**, not a reliability improvement.

If async is needed, choose a model supported by Spring Kafka and your active version, featuring:

- A way to determine exactly which tasks completed before acknowledging offsets.
- In-flight task control, bounded queues, and backpressure.
- Partition ownership management on rebalance or shutdown.
- Idempotency to survive redelivery/crashes.
- Rules preserving per-partition/per-key order if required by business logic.
- Exception handling from futures to avoid swallowing errors inside thread pools.

Recent Spring Kafka versions have mechanisms supporting asynchronous acknowledgments or async listener return types, but specific semantics must be checked. Do not call `Acknowledgment.acknowledge()` from arbitrary threads without understanding thread-safety, ordering, commit mode, and what the container actually supports.

## 12. `AckMode` and offset commits during rebalance

Spring Kafka supports acknowledgment modes such as `RECORD`, `BATCH`, `MANUAL`, and `MANUAL_IMMEDIATE`. Ack mode determines when the container records and commits progress for processed records, yet **does not change the limit between two `poll()` calls**.

| Ack mode | Characteristics related to slow poll |
|---|---|
| `RECORD` | Commits after each successfully processed record; if listener takes too long it can still exceed poll interval |
| `BATCH` | Commits per batch; a large slow batch widens the uncommitted processing window |
| `MANUAL` | Application indicates when processed; actual commit depends on container semantics |
| `MANUAL_IMMEDIATE` | Can commit when acknowledgment is called per container conditions; does not fix blocking listeners |

When group generation changes due to a rebalance, the old consumer may lose authority to commit offsets for newly revoked partitions. An error like `CommitFailedException` appearing **after the business method ran successfully** is usually a symptom that assignment changed, not necessarily an isolated commit API failure.

Therefore, when seeing `CommitFailedException`, examine rebalance and poll interval logs **prior to it**, rather than merely increasing offset commit retries. If another consumer already owns the partition, retrying commits on the old member is not guaranteed to be valid.

## 13. `ConsumerRebalanceListener` and lifecycle

When a rebalance occurs, partitions can be revoked from the old consumer and assigned to a new consumer. Spring Kafka lets applications participate in this lifecycle via `ConsumerAwareRebalanceListener` or corresponding container callbacks. These callbacks can be used to flush/hand off in-memory state, log assignments, or prevent work items belonging to lost partitions from continuing to write side effects.

```java
@Bean("ordersContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersContainerFactory(ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setConsumerRebalanceListener(
            new ConsumerAwareRebalanceListener() {
                @Override
                public void onPartitionsRevokedBeforeCommit(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {
                    // Record partitions being revoked.
                    // Do not perform slow I/O inside the callback.
                }

                @Override
                public void onPartitionsAssigned(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {
                    // Initialize state for new assignment if needed.
                }
            });

    return factory;
}
```

This is a conceptual example of listener lifecycle; exact methods and callbacks must match your Spring Kafka version. Avoid placing long database transactions, HTTP calls, or heavy batch processing inside rebalance callbacks because slow callbacks themselves further delay group stabilization.

Rebalance listeners **do not replace** idempotency. When partitions are revoked, some side effects may have already occurred before the callback is invoked; design so the new consumer reprocesses safely.

## 14. Effects of eager/cooperative rebalance and static membership

Kafka has multiple partition assignment strategies. With eager rebalancing, a single member change can cause many partitions to be revoked and then reassigned. With cooperative incremental rebalancing, the broker/client can revoke partitions in increments to reduce disruption. However, if a member fails to meet polling requirements, its assignment can still be altered.

**Cooperative rebalance** helps reduce the scope of disruption in some topologies; it **does not fix** listener logic blocking for too long. **Static membership** with `group.instance.id` helps limit unnecessary rebalances during brief instance restarts, yet does not turn a consumer that stops polling indefinitely into a healthy member.

For static members in the classic protocol, when `max.poll.interval.ms` is exceeded, partition reassignment may be delayed until the session timeout expires instead of happening immediately. This can help a short restart avoid losing assignment, yet also lengthens the time partitions go unprocessed if an instance is genuinely stuck. Choosing static membership requires considering stable pod identity, rolling deployments, and session timeout.

When using newer group protocols, heartbeat/session timeout behavior may be governed by broker configuration. Do not mechanically apply tuning values from the classic protocol without verifying the deployed Kafka client, broker, and assignor.

## 15. Monitoring: measuring the true gap between polls

To detect risks early, observe **the latency of each consumer loop**, not just overall consumer lag. Commonly useful signals:

| Metric or log | Operational question to answer |
|---|---|
| `time-between-poll-max` (Kafka consumer metric, if exported) | Is the maximum gap between `poll()` calls approaching the threshold? |
| `last-poll-seconds-ago` or equivalent metric | How long has the consumer gone without calling `poll()`? |
| Listener processing duration p95/p99 | How long does a record or batch actually take to process? |
| Effective `max.poll.interval.ms` | What threshold is currently applied to the consumer? |
| Rebalance count/rate, assigned partitions | Are partitions being revoked frequently? |
| Offset commit failure / `CommitFailedException` | Did commits fail after assignment changes or for another reason? |
| Consumer lag and oldest unprocessed age | How large a backlog is slow polling causing? |
| Database/HTTP timeout, pool waiting, GC pause | Which downstream/runtime factor is holding the consumer thread? |

Exact metric names depend on the Kafka client, Micrometer, and observation configuration; only use available names after checking runtime. Adding tags like application, listener ID, group, and topic can help isolate issues, yet avoid using event ID or offset as metric labels because cardinality is too high.

Emit structured logs for a poll/batch or record containing duration, topic, partition, offset, listener/container ID, exception class, and downstream dependency. If logs only contain group ID, it is hard to tell which child container at concurrency 6 is processing slowly.

A typical dashboard:

```text
Consumer group: order-worker

max poll interval        300 s
max time between polls   280 s   <-- near threshold
listener batch p99       245 s
consumer lag             increasing
rebalance rate           increasing
commit failures          appearing

Investigation path:
  slow listener / downstream timeout -> poll gap -> rebalance
```

These are hypothetical figures illustrating cause and effect. Do not attribute every rebalance to slow polling if poll gaps are not growing and member lifecycle logs point to another cause.

## 16. Runbook for handling slow-poll rebalances

When receiving consumer lag alerts, continuously changing partition assignments, and poll timeout logs, handle in order:

1. **Isolate:** identify the cluster, topic, consumer group, listener ID, and revoked partitions.
2. **Confirm cause:** find poll timeout logs; measure gaps between polls and listener execution times.
3. **Check dependencies:** database lock/query timeouts, HTTP timeouts, connection pools, GC pauses, CPU throttling, and thread starvation.
4. **Distinguish restarts/deploys:** cross-check scaling logs, rolling deployments, and broker/assignment changes to rule out normal rebalances.
5. **Reduce batch/in-flight:** adjust `max.poll.records`, concurrent task count, and downstream load limits if batches are too large.
6. **Bound timeouts:** set explicit limits on HTTP, SQL, and retries; eliminate unbounded blocking calls.
7. **Optimize retries:** choose suitable backoffs; for long backoffs consider container pause or non-blocking retries if ordering permits.
8. **Only then consider raising `max.poll.interval.ms`:** choose a level based on reasonable p99/worst-case and recovery SLO.
9. **Verify idempotency:** verify uncommitted offsets can be redelivered without creating duplicate side effects on rebalance.
10. **Monitor after changes:** poll gap, rebalance rate, commit failures, lag, and successful processing must all improve together.

Do not reset consumer group offsets to "clear lag" without evaluating unprocessed data. Advancing offsets can skip events; rewinding can create duplicates. Likewise, switching to a new consumer group or suddenly increasing concurrency can amplify database load and worsen slow-poll failures.

## 17. Integration testing: proactively reproducing poll timeouts

You can test with a Kafka broker in Testcontainers and two consumer instances in the same group to observe partition ownership transfers. Choose a short enough poll interval for the test environment and use simulated side effects with an idempotency key.

Simple scenario:

1. Create a topic with one partition and a new consumer group.
2. Configure `max.poll.interval.ms` at a test value, e.g., 20 seconds; `max.poll.records` small enough to observe easily.
3. Listener A receives a record and intentionally blocks past 20 seconds using a latch/test hook.
4. Start consumer B in the same group; record assignments and rebalance timing.
5. Let listener A finish after exceeding poll interval; observe offset commit failure if the scenario produces that error.
6. Confirm consumer B can receive the uncommitted record from the durable offset.
7. Confirm the same event ID does not produce two business side effects while A/B both run thanks to inbox/unique constraint.
8. Reduce processing time or `max.poll.records`, re-run, and observe stable polling/rebalancing.

If using static membership, results and reassignment timing may differ due to session timeout; tests must set expectations per protocol/member type. Avoid building tests relying solely on hardcoded `sleep` durations if you can use synchronization/latches and observe actual assignment events.

An illustrative example of a timeout-prone listener (for tests only):

```java
@KafkaListener(topics = "orders", groupId = "poll-timeout-test")
public void simulateSlowProcessing(OrderEvent event) {
    testLatch.awaitForProcessingRelease(); // test helper blocking under control
    orderService.processIdempotently(event);
}
```

`testLatch` is a control object from the test harness, not a standard Spring Kafka API. In production, avoid unbounded blocking calls on the consumer thread.

## 18. Remediation decision table

| Primary cause | Preferred remediation | Watch out for |
|---|---|---|
| Single poll returns too many records | Reduce `max.poll.records`, measure processing time | Smaller batches increase poll/commit overhead |
| Slow SQL queries/locks | Query timeouts, index/lock analysis, reduce contention | Raising poll interval hides database bottlenecks |
| HTTP API occasionally hangs | Connect/read timeouts, circuit breaker, bounded retries | Continuous retries can further overload dependencies |
| Long blocking retry/backoff | Bound attempts or use suitable container-pausing/non-blocking retry | Non-blocking retry can alter event order |
| Listener genuinely needs long time | Raise `max.poll.interval.ms` with justification, reduce records/batch | Stalled members hold partitions longer |
| CPU/GC/thread starvation | Resource and workload tuning, bounded queues | Raising concurrency when CPU-starved can backfire |
| Untracked async work | Use async/ack model with backpressure and idempotency | Early commit loses processing, late commit causes duplicates |
| Rebalances during rolling deploy | Check shutdown, static membership/cooperative assignment | Not every rebalance is a poll timeout |

## 19. Production design principles

When deploying Spring Kafka listeners capable of slow processing, remember:

1. `max.poll.interval.ms` measures the time between `poll()` calls, not heartbeat timeout.
2. Long synchronous listeners, large batches, and blocking retries can prevent the consumer thread from returning to `poll()` on time.
3. Still-running heartbeats do not prove the consumer satisfies the poll limit; static membership only changes when partitions are revoked.
4. Budget maximum time per record/batch, including SQL, HTTP, retries, serialization, and commit overhead.
5. Lower `max.poll.records` and set dependency timeouts before raising `max.poll.interval.ms` too high.
6. Pause helps when the container keeps polling; pause does not fix a callback blocking the consumer thread indefinitely.
7. Offloading work to async requires bounded in-flight, error handling, proper acknowledgment, and ordering protection.
8. When partitions are revoked, old committed offsets can cause record redelivery; side effects must be idempotent.
9. Observe poll gap, listener duration, rebalances, commit failures, lag, and downstream performance together.
10. Test losing assignment mid-processing to prove recovery causes neither data loss nor duplicate side effects.

**Conclusion:** rebalance due to slow polling is Kafka's mechanism to protect the consumer group when the application stops showing processing progress for too long. In Spring Kafka, the cause usually lies in the listener or error handler holding the consumer thread longer than the `max.poll.interval.ms` budget, not necessarily a broken broker or heartbeat. A sustainable fix is reducing blocking time, controlling batches and retries, maintaining proper polling, and accepting redelivery risks through idempotency and offset reconciliation.
