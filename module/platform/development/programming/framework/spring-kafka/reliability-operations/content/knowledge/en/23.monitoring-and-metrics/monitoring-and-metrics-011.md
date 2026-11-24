# Commit latency

In a Spring Kafka consumer, the listener finishing a record and **Kafka confirming the offset commit** are two separate milestones. A consumer can finish a database operation in a few milliseconds yet take hundreds of milliseconds to commit the offset due to network latency, a busy group coordinator, or excessive commit requests. When that happens, throughput, consumer lag, and redelivery risk are all affected.

**Commit latency** in Kafka monitoring typically refers to **the time a consumer offset commit request takes to complete**. It is an important metric in the **Monitoring and metrics** chapter, yet it must be interpreted accurately: it is not record processing time, not record publish time, and does not by itself measure the full duration of a Kafka transaction.

This lesson explains how to understand commit latency, distinguish offset commits from transaction commits, track Kafka client metrics, configure commits in Spring Kafka, design dashboards/alerts, and investigate incidents without weakening delivery guarantees.

## 1. Why measure commit latency?

Consider an `order-worker` service reading from topic `orders.created`:

    Topic orders.created
             |
             v
       KafkaConsumer.poll()
             |
             v
        @KafkaListener
             |
             v
      Business processing: 12 ms
             |
             v
      Offset commit: 180 ms
             |
             v
        Next poll

If the container performs a synchronous commit after every record, high commit latency can sharply cut processing speed. In this simple example, a sequential consumer takes nearly 192 ms/record, or about 5.2 records/second, whereas business code alone could handle over 80 records/second.

Conversely, if the application commits every batch of 100 records, commit cost no longer sits on every record's path. However, a wider interval between commits means more records may have to be reprocessed if the consumer crashes.

Commit latency affects:

- **Throughput:** synchronous commits hold the consumer thread waiting for results.
- **Work completion lag:** business side effects finished while the offset is not yet durably recorded.
- **Consumer lag and freshness:** slow commits can push read/commit speed below producer speed.
- **Redelivery:** processed but uncommitted records can be redelivered after a restart/rebalance.
- **Rebalances and shutdowns:** prolonged commits delay handing off partitions or stopping consumers.
- **Operational SLOs:** the consumer may appear running yet fail to progress fast enough.

Never optimize commit latency by committing offsets before side effects succeed. Cutting latency that way trades away business data safety.

## 2. Which "commit" are we talking about?

In Spring Kafka there are several operations called commit:

| Commit type | System | Meaning |
|---|---|---|
| Consumer offset commit | Kafka group coordinator | Records the consumer group's next read position |
| Producer transaction commit | Kafka transaction coordinator | Completes a Kafka transaction containing output records, optionally with offsets |
| Database transaction commit | PostgreSQL/MySQL/... | Makes database changes durable |
| Listener acknowledgment | Spring Kafka container | Signals the application finished processing the record, potentially triggering a commit per `AckMode` |
| HTTP business acknowledgment | Another service | A business confirmation, not a Kafka offset commit |

**Commit latency** published by the Kafka consumer client usually relates to consumer group offset commit requests. If a listener uses Kafka transactions, also monitor Kafka transaction commit duration because offset commits may go through `sendOffsetsToTransaction` and `commitTransaction`, unlike an ordinary `commitSync` call.

Likewise, a slow JDBC transaction commit metric must not be conflated with Kafka commit latency. Their causes and fixes differ greatly.

## 3. How are consumer offsets committed?

Each record has an address:

    topic + partition + offset

Example:

    orders.created partition 2

      offset 100 -> Order A
      offset 101 -> Order B
      offset 102 -> Order C
      offset 103 -> Order D

The consumer successfully processes the record at offset 100. The value committed for the group is typically **101**, i.e., the next offset the consumer should read upon resuming.

    Last processed offset: 100
    Committed offset:      101

If the consumer processes 100, 101, 102 yet commits only 101, upon restart it can resume from offset 101. Side effects for 101 and 102 may execute again.

Distinguish:

- **Consumer position:** the position the consumer will poll next in the current session.
- **Committed offset:** the position stored by the group coordinator for restarts/reassignments.
- **Processed offset:** the offset the application finished processing per business definition.
- **Acknowledged offset:** the offset confirmed to the listener/container, without guaranteeing the commit request has completed.

`KafkaConsumer.poll()` returning records up to offset 150 does not prove the group committed up to 151.

## 4. Timeline: from record processing to successful commit

A simple pipeline:

    T0  consumer.poll() returns record
    T1  listener begins processing
    T2  business side effect completes
    T3  container decides to commit offset
    T4  Kafka client sends OffsetCommit request
    T5  Group coordinator handles request
    T6  Kafka client receives response
    T7  container continues processing/poll loop

We can break this down:

    Business processing latency = T2 - T1

    Waiting-to-commit latency    = T3 - T2
      (depends on AckMode, batching, scheduling)

    Offset commit request latency ~= T6 - T4

    Time until durable progress  = T6 - T2
      (when commit succeeds)

How T4/T6 are measured inside the Kafka client is an implementation detail, yet separating these concepts matters. A low `commit-latency-avg` does not prove offsets commit immediately after business side effects if the app deliberately waits for multiple records before committing.

To measure end-to-end **processing-to-commit**, collect additional timestamps/metrics at the application or container layer rather than relying solely on Kafka client metrics.

## 5. How does the Kafka group coordinator participate?

Consumer offsets are **consumer group** state stored by Kafka via the coordinator mechanism and the internal `__consumer_offsets` topic.

Simplified flow:

    Spring Kafka listener container
               |
               v
       KafkaConsumer.commitSync()
               |
               v
         Kafka client
               |
               v
       Group coordinator broker
               |
               v
        Offset commit response

The group coordinator validates commit requests against group metadata, partitions, and generation. If the consumer just lost partition ownership or the group is rebalancing, commits can be rejected, retried per supported rules, or throw exceptions.

Latency can come from:

1. Network RTT between client and broker.
2. Overloaded group coordinator.
3. Broker CPU, I/O, or replication pressure.
4. High commit request volume across many consumer groups.
5. Request queues, throttling, or flaky connections.
6. Group rebalances and membership churn.
7. Slow client threads/schedulers or JVM GC pauses.

Client-side commit latency measurements must be paired with broker metrics, because a latency chart alone cannot pinpoint the root cause.

## 6. commitSync and commitAsync

The Kafka Java consumer offers two fundamental commit styles:

**commitSync:** waits until the commit completes or errors/times out per API contract. Suitable when the application needs to know the commit outcome before continuing or relinquishing a partition.

**commitAsync:** sends an asynchronous commit request with a completion callback. The consumer is not blocked in the same way as synchronous commits, though the application must handle failure modes and progress ordering properly.

Comparison:

| Aspect | commitSync | commitAsync |
|---|---|---|
| Call path | Can block waiting for result | Returns fast, callback later |
| Latency impact on consumer thread | Can be large when brokers slow down | Less direct blocking |
| Error handling | Exception from call | Callback/tracking logic |
| Result visibility | Clear once method completes normally | Must inspect callback |
| Rebalance interaction | May need commit before revoke | Careful with late callbacks |
| Redelivery when uncommitted | Still possible | Still possible |

**Async does not mean commits are free.** Requests still travel to the broker. Commit request latency metrics can remain high; the consumer thread simply blocks less at call time.

The Kafka client has specific ordering guarantees for requests/callbacks, yet you should never blindly retry an old async commit without checking whether a newer offset already committed. A late retry of older progress can regress offset state if custom logic is flawed.

## 7. How does Spring Kafka decide sync vs. async?

In supported Spring Kafka versions, `ContainerProperties` has a `setSyncCommits(boolean)` option controlling whether the container uses synchronous or asynchronous commits when managing offset commits.

Java Configuration example:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        ContainerProperties props = factory.getContainerProperties();

        props.setAckMode(ContainerProperties.AckMode.BATCH);
        props.setSyncCommits(true);
        props.setSyncCommitTimeout(Duration.ofSeconds(8));

        return factory;
    }
}
~~~

Key imports:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
~~~

`OrderEvent` is an application DTO. This example shows container configuration and omits full producer/consumer factories, serializers, or topic creation.

**Version note:** The `setSyncCommitTimeout` API and commit retry/error-handling behavior can vary by Spring Kafka version. Check the Javadoc matching your project's dependency.

To use async commits in the container commit path, you can configure `setSyncCommits(false)`. Base this decision on safety requirements, async commit failure handling, and integration test results—never switch to async merely to make p95 latency look nicer on dashboards.

## 8. AckMode determines commit frequency

Spring Kafka listener containers support several `AckMode` values. Depending on mode, offsets commit after each record, after a poll batch, or by count/time conditions.

| AckMode | General behavior | Implication for commit latency |
|---|---|---|
| RECORD | Commits after each record listener succeeds, per container mechanics | More commit requests in small-record workloads |
| BATCH | Commits after all records from one poll are processed | Fewer commits; many records share one commit boundary |
| TIME | Commits when a configured time interval elapses per container mechanics | Can lower commit frequency |
| COUNT | Commits when a configured record count is reached | Depends on record volume |
| COUNT_TIME | When either count or time condition is met | Balances frequency and uncommitted window |
| MANUAL | Listener acknowledges; commits per batch/container mechanics | Ack does not always mean immediate commit |
| MANUAL_IMMEDIATE | Can commit immediately when acknowledged on the consumer thread | Easily causes frequent commits if acking each record |

RECORD example:

    poll() -> [A, B, C]

    process A -> commit offset after A
    process B -> commit offset after B
    process C -> commit offset after C

BATCH example:

    poll() -> [A, B, C]

    process A
    process B
    process C
    commit offset after C

Exact commit timing also depends on record/batch listener mode, transactions, error handlers, seeks/recovery, and Spring Kafka version. The table above clarifies design choices, not a fixed protocol across every configuration.

## 9. RECORD vs. BATCH: throughput vs. replay trade-off

Suppose each consumer processes 1,000 records/second, and one synchronous commit request averages 15 ms.

If configured so every single record truly blocks on a commit:

    Theoretical commit rate needed: 1,000 commits/s
    Commit wait time: 1,000 * 15 ms = 15 seconds
      per 1 second of work

A sequential consumer thread cannot reach 1,000 records/s with that config if every commit must finish before the next record. That is a self-inflicted bottleneck.

If committing every 100 records:

    Commit frequency ~= 1,000 / 100 = 10 commits/s

Commit wait cost per record is amortized substantially. Yet if the consumer crashes before the final commit, records already processed in the batch but uncommitted may run again.

| Design | Benefit | Trade-off |
|---|---|---|
| Commit per record | Smaller replay window | High commit overhead |
| Commit per batch | Usually higher throughput | Larger replay window |
| Async commit | Reduces thread blocking | Must handle errors and callbacks properly |
| Transactional offsets + output | Atomic Kafka read-process-write | Transaction overhead and separate timeouts |

Do not switch to BATCH just because latency is high if each record triggers non-idempotent side effects. First guarantee that reprocessing records will not corrupt business state.

## 10. MANUAL acknowledgment is not a direct commit request

A listener can acknowledge explicitly:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-worker",
    containerFactory = "manualAckFactory"
)
public void onOrder(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(record.value());
    acknowledgment.acknowledge();
}
~~~

This example requires `manualAckFactory` to use an `AckMode` supporting manual acknowledgment, such as `MANUAL` or `MANUAL_IMMEDIATE`.

Distinguish:

- **Processing time:** from when the listener receives the record until `processIdempotently` finishes.
- **Acknowledge call time:** confirming progress with the Spring Kafka container.
- **Kafka offset commit time:** request/response between consumer client and coordinator.

With `AckMode.MANUAL`, `acknowledge` generally marks progress for the container to commit at an appropriate boundary, without guaranteeing an immediate broker commit when the method returns.

With `MANUAL_IMMEDIATE`, if `acknowledge` runs on the consumer thread, it can commit immediately per configuration. Calling from another thread may behave differently; never use async acks without understanding the container contract.

**Never take a timestamp right after `acknowledge()` and call the elapsed time Kafka commit latency.** It may merely measure local method overhead or scheduling delay.

## 11. Commit latency in transactional consumers

With a listener container using Kafka transactions, the read-process-write flow typically looks like:

    Consume input record
             |
             v
      Begin Kafka TX
             |
             v
     Process + KafkaTemplate.send()
             |
             v
    Send input offsets into TX
             |
             v
       commitTransaction()
             |
             +-- Output Kafka committed
             +-- Input group offsets committed

In this model, consumer offset completion is tied to **transaction commit**, not just a standalone `commitSync`.

Therefore:

1. Client consumer `commit-latency-avg` does not necessarily measure full producer transaction commit latency.
2. Monitor corresponding producer transaction duration/commit/abort metrics.
3. Input offsets and Kafka outputs commit atomically when transactions work properly.
4. If the transaction aborts, offsets are not committed by that transaction and inputs can be redelivered.
5. If business side effects write to a database before Kafka commit, they can still repeat on Kafka rollback.

Never mix Kafka transaction commit latency with database commit latency on the same chart without labeling the measurement source clearly.

## 12. Commit-related Kafka client metrics

The Kafka Java consumer publishes metrics via the Kafka client Metrics API and typically via JMX. Common metrics in the consumer coordinator group include:

| Metric | Interpretation |
|---|---|
| `commit-latency-avg` | Average latency recorded for offset commit requests |
| `commit-latency-max` | Maximum latency recorded in the client's measurement window |
| `commit-rate` | Rate of commit requests per unit time per client metric |
| `commit-total` | Total commit requests recorded per client metric |
| `assigned-partitions` | Number of partitions currently assigned to the consumer, in the relevant metric group |
| `rebalance-total` | Number of rebalances recorded, depending on Kafka client version |
| `last-rebalance-seconds-ago` | Time since the last rebalance when supported by the metric |

Exact names, groups, units, and available metrics **depend on Kafka client version**. When building dashboards, inspect the actual list emitted by your client instead of assuming all exist.

Commit latency is typically reported in **milliseconds** for Kafka consumer coordinator metrics. When bridged through JMX exporters, Prometheus, or Micrometer, verify whether units are converted or metric names changed.

`commit-total` counts requests per client metric definition—**not records processed**, nor automatically successful commits without checking version contracts.

## 13. JMX and metric data sources

Kafka clients typically expose coordinator metrics under a JMX MBean like:

~~~text
kafka.consumer:type=consumer-coordinator-metrics,client-id=<consumer-client-id>
~~~

Attributes can include `commit-latency-avg`, `commit-latency-max`, `commit-rate`, and related metrics.

In Spring Kafka with `concurrency > 1`, each child consumer can have its own `client.id`. A dashboard watching only one MBean/client ID will miss the other consumers.

Example:

    Group: billing-workers
    Pod A:
      clientId billing-0
      clientId billing-1
    Pod B:
      clientId billing-2
      clientId billing-3

If `billing-2` sees a sharp commit latency spike while others stay normal, a group-wide average can hide the failing consumer.

When scraping JMX, watch out for:

- JMX exporter rules mapping attribute names to Prometheus metrics.
- Hyphens often converted into underscores.
- `client-id` potentially carrying dynamic suffixes per container and deployment.
- Some metrics appearing only after the consumer starts active work.
- Metrics vanishing when a consumer closes; never interpret "missing series" as 0 latency.

## 14. Micrometer in Spring Kafka

Spring Kafka integrates Micrometer to observe listeners/containers, while the Kafka Java client also has its own metrics for consumers/coordinators.

**These two groups are not identical:**

- **Listener timer/observation:** time Spring Kafka spends invoking listeners or processing records/batches within instrumentation scope.
- **Kafka consumer client metrics:** poll, fetch, commit, and rebalance metrics depending on version.
- **Producer transaction metrics:** measure producer/transaction activity, tracked separately when using EOS.
- **Business metrics:** database/HTTP call durations, DB commits, and business processing outcomes.

When using Micrometer, you can use your library's Kafka client metrics binder/listener or a JMX exporter to bring commit metrics into your monitoring registry.

Do not assume `spring.kafka.listener.observation-enabled=true` automatically creates a timer named "Kafka commit latency" for every offset commit. Listener observation and consumer coordinator commit requests are different scopes.

Verify actual metrics via Actuator's metrics endpoint, JMX, Prometheus scrapes, or your project's configured APM.

## 15. Configuring listener telemetry

Example Spring Boot YAML enabling observation if supported by the version:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-workers
      enable-auto-commit: false
      properties:
        max.poll.records: 100
    listener:
      ack-mode: batch
      observation-enabled: true

management:
  metrics:
    tags:
      application: billing-service
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

This is a directional config for apps with Micrometer/Actuator and the matching registry. Having the `prometheus` endpoint requires the Prometheus registry dependency; YAML alone does not create an exporter.

When using observation, check compatibility with legacy Micrometer listener timers in your Spring Kafka version; some instrumentation modes replace each other or alter metric names.

To get `commit-latency-avg`, you still need **Kafka consumer client metrics** exposed. Never assume listener observation covers the coordinator.

## 16. Measuring commit latency manually with raw KafkaConsumer

For apps managing `KafkaConsumer` directly, you can time `commitSync` calls using `System.nanoTime()` and a Micrometer `Timer`:

~~~java
public final class TimedOffsetCommitter {

    private final Timer commitTimer;

    public TimedOffsetCommitter(MeterRegistry registry) {
        this.commitTimer = Timer.builder(
                "app.kafka.offset.commit.duration")
            .description("Synchronous offset commit call duration")
            .register(registry);
    }

    public void commit(
            Consumer<String, String> consumer,
            Map<TopicPartition, OffsetAndMetadata> offsets) {

        long started = System.nanoTime();

        try {
            consumer.commitSync(offsets);
        }
        finally {
            commitTimer.record(
                System.nanoTime() - started,
                TimeUnit.NANOSECONDS
            );
        }
    }
}
~~~

Related imports:

~~~java
import java.util.Map;
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
~~~

This snippet is for **application-managed consumers**, committing on the thread owning `KafkaConsumer`. Never call `commitSync` inside a `@KafkaListener` just to collect a metric when the Spring Kafka container already manages offsets, as that can corrupt `AckMode`, transactions, or commit ordering.

A `Timer` recorded in `finally` measures method duration even when commit fails; to separate success/error, add a counter or low-cardinality status tag.

This Timer captures **wall-clock method duration**, which can include client-side retries/waits. Hence values need not match client `commit-latency-avg` identically. Neither metric is wrong; they measure different scopes.

## 17. Why not measure using acknowledge() duration?

Conceptually wrong example:

~~~java
long start = System.nanoTime();

ack.acknowledge();

long duration = System.nanoTime() - start;
recordMetric(duration, "commit_latency");
~~~

This snippet may only record how long the container took to register the acknowledgment, without any guarantee the `OffsetCommit` request was sent and completed.

Depending on `AckMode`, acknowledgments can be queued to commit at poll end, after a batch, or at another boundary. If `ack` is called from a worker thread, the actual commit happens even later.

If the goal is Kafka offset commit latency, prefer **Kafka client coordinator** metrics. If measuring from "business success" to "offset durable," design instrumentation hooked into actual commit callbacks/outcomes per container contract rather than timing whichever line is convenient.

## 18. Commit latency can rise from committing too frequently

Suppose a group has 60 consumers, each doing a synchronous commit after every record, and each consumer processes 100 records/second:

    60 consumers * 100 commits/s
      = 6,000 commits/s

That is a heavy load of offset commit requests, even before counting other consumer groups on the same Kafka cluster.

When the coordinator saturates or network/request queues back up, commit latency rises. A vicious cycle begins:

    Many commit requests
          |
          v
    Coordinator latency rises
          |
          v
    Consumer threads block longer
          |
          v
    Processing throughput drops
          |
          v
    Consumer lag rises

Mitigations include batching commits appropriately, cutting unnecessary commit frequency, or distributing workloads—while weighing replay and business durability. Never fix this by raising thread counts infinitely; doing so generates even more commit traffic.

## 19. Calculating cost per record

A simple throughput model for synchronous consumer processing:

    CostPerRecord = BusinessTime + CommitCostPerRecord

When committing after every record:

    CommitCostPerRecord ~= AverageCommitLatency

When committing every N records:

    CommitCostPerRecord ~= AverageCommitLatency / N

Example:

    BusinessTime = 8 ms/record
    CommitLatency = 40 ms/commit

    Commit per record:
      Cost ~= 8 + 40 = 48 ms/record
      Theoretical throughput ~= 20.8 records/s/thread

    Commit every 50 records:
      Cost ~= 8 + 40/50 = 8.8 ms/record
      Theoretical throughput ~= 113.6 records/s/thread

This is an illustrative model assuming sequential processing without overlapping I/O and blocking commits. Real systems must account for fetches, network, batch overhead, partition skew, synchronous producer sends, and scheduling.

These numbers show why lowering commit frequency can boost throughput, yet **they do not prove that config is safe for business state**.

## 20. Trade-off between commit frequency and duplicate window

Suppose a consumer processes 500 records/second and commits every 200 records.

    Time between commits ~= 200/500 = 0.4 seconds

If the JVM crashes before the next commit, some records whose side effects already ran may be redelivered. In count terms, the uncommitted window is typically up to roughly the active batch size, though actual replay scope depends on committed offsets, container error handling, and partition assignments.

If committing every 2,000 records:

    Commit interval ~= 2,000/500 = 4 seconds

Fewer commit requests are sent, yet far more work may need to re-run.

To choose wisely:

1. Are side effects idempotent?
2. Would reprocessing cause duplicate payments/emails?
3. Is recovery from backlog fast enough?
4. What is the SLA for committed progress?
5. How often do consumer restarts/rebalances happen?
6. Does DLT/recovery preserve failing records?

There is no single optimal batch size for all consumer groups.

## 21. Impact of async commits and error callbacks

When calling async commits directly via the Kafka client:

~~~java
consumer.commitAsync(
    offsets,
    (committedOffsets, exception) -> {
        if (exception != null) {
            log.warn(
                "Asynchronous Kafka offset commit failed; offsets={}",
                committedOffsets,
                exception
            );
        }
    }
);
~~~

This snippet is for **raw consumers** or Kafka client API examples; do not call it inside a listener when Spring Kafka manages offsets.

A common hazard is **retrying an old commit out of order**:

    Async commit #1: offset 100
    Async commit #2: offset 150
    Commit #2 succeeds
    Failure callback for #1 fires
    Application blindly retries #1

Retrying offset 100 after offset 150 was already recorded can regress group progress along an improper commit path.

Therefore, if managing async commits yourself, enforce a policy to commit only the newest valid progress and coordinate with revoke/shutdown. Never mix `commitAsync`, `commitSync`, and callback retries haphazardly.

Spring Kafka manages callbacks and commit behavior when `syncCommits=false`; to know what errors/metrics surface, inspect the active container and listener factory policies.

## 22. Commit failure differs from high commit latency

A commit request taking 300 ms and succeeding is **high latency**. A request timing out after several seconds with no confirmation is a **commit failure or uncertain outcome**.

| Condition | Symptoms | Meaning |
|---|---|---|
| Rising latency, high success | Commit p95/p99 rises | Slow or overloaded coordinator/network |
| Timeout | Client gets no response within timeout | Unclear whether broker committed |
| `CommitFailedException` | Group membership/assignment no longer valid | Inspect rebalances/poll intervals |
| Authorization error | Missing permission for operation | ACL/credential config |
| Rebalance in progress | Commit hits generation change | Inspect group stability, poll latency |
| Transaction abort/fencing | Offsets in Kafka TX fail to commit | Inspect producer transaction metrics, lifecycle |

Never take a very large `commit-latency-max` as proof of data loss. Kafka can redeliver from the prior committed offset if a commit did not succeed; that is normal at-least-once behavior, not automatic message loss.

Conversely, the truly dangerous bug is an application **marking business work complete and committing offsets too early**; low latency will not save a broken design.

## 23. Commit latency during rebalances

During a rebalance, partition ownership changes. A consumer can receive `onPartitionsRevoked` before yielding partitions so it can finish work and commit appropriate offsets.

If `commitSync` is too slow:

    Rebalance starts
          |
          v
    Revocation callback
          |
          v
    Flush + commitSync
          |
          v
    Wait on coordinator / network
          |
          v
    New consumer receives assignment late

High commit latency prolongs rebalances and cuts processing availability.

Important:

- In `onPartitionsRevoked`, committing can be appropriate while the consumer still holds valid ownership and state.
- In `onPartitionsLost`, the consumer **has already lost ownership**; do not attempt to commit offsets as the old owner.
- When rebalances and commits collide, commit errors can surface; inspect root causes.
- With `CooperativeStickyAssignor` or corresponding cooperative strategies, the revocation scope can be smaller than eager rebalances.
- Applications doing async work need fencing/cancellation of old tasks when partition ownership transfers.

Do not call `commitSync` manually inside a rebalance listener when the Spring Kafka container already manages commits and no custom logic is required; it easily causes double commits, wrong offsets, or deadlocks.

## 24. max.poll.interval.ms and commit latency

`max.poll.interval.ms` bounds the time between polls required by the consumer group. In some processing paths, **listener processing time plus synchronous commit wait time** pushes polls farther apart.

Example:

    max.poll.interval.ms = 300,000 ms

    One poll returns 500 records
    350 ms processing per record: 175,000 ms
    Total synchronous commit waits: 100,000 ms
    Approximate total: 275,000 ms

Once retries, GC, and scheduler overhead are added, the consumer can approach the limit and trigger a rebalance.

Estimate using:

    TimeBetweenPolls
      ~= processingTimeForReturnedRecords
         + commitWaitingTime
         + handler/retry/otherOverhead

Not every `AckMode` puts all acks/commits directly on this path, yet for sequential sync commits, wait time is a clear part of the overhead.

When raising timeouts, weigh detection speed for hung consumers. Do not simply raise `max.poll.interval.ms` to mask a slow coordinator.

## 25. Group coordinator overload

If many consumer groups commit relentlessly, the broker acting as coordinator becomes a hotspot. Symptoms:

- Commit latency rises across multiple consumers simultaneously.
- High commit request rate.
- High broker CPU/request queue depth.
- Fluctuating rebalance/heartbeat metrics.
- Rising Kafka client request timeouts.
- Commit failures on some groups.

Investigation steps:

1. Identify which broker serves as coordinator for affected groups.
2. Compare latency by client, group, and timestamp.
3. Check broker CPU, network, request handlers, and I/O.
4. Check request throttling and quotas.
5. Check whether commit rate jumped after rolling out `AckMode.RECORD`.
6. Check whether autoscaling spun up many new consumer instances.
7. If needed, lower commit frequency sensibly rather than piling more load onto the coordinator.

Never infer root cause solely from one broker's high CPU. Combine group coordinator stats, network latency, and client-specific metrics.

## 26. Network latency and multi-region setups

A consumer in a region far from the Kafka cluster experiences noticeably higher RTT than a co-located consumer.

Example:

    Consumer region A -> broker region A: RTT 3 ms
    Consumer region B -> broker region A: RTT 70 ms

If `commitSync` depends on a request/response round trip, network distance can dominate commit latency. Committing every record over a 70 ms RTT link severely caps per-thread throughput even when business logic is fast.

Potential improvements:

- Co-locate consumers near the cluster or over low-RTT, stable links.
- Avoid synchronous cross-region commits per small record unless required.
- Measure network packet loss, retransmits, and TLS overhead.
- Consider batching or pipelining compatible with replay/idempotency.
- Never assume raising `request.timeout.ms` lowers latency; it mainly extends how long the client waits before failing.

If multi-region is an architectural requirement, budget that latency into throughput/SLOs from the start.

## 27. JVM, GC, and client-thread scheduling

Commit latency seen by the application can be affected by the JVM:

- Long stop-the-world GC pauses.
- CPU throttling in Kubernetes.
- Thread starvation in containers/hosts.
- Synchronous callbacks or slow logging on consumer threads.
- Allocation pressure during deserialization/serialization.
- Thread pool contention for telemetry or error handling.

A `commitSync` call taking long on wall-clock time can include scheduler delays holding the thread. When analyzing wall-clock durations, compare against Kafka client metrics and JVM/process metrics.

If commit latency spikes alongside GC pauses on one pod while other pods stay fine, the problem likely sits in that client's JVM rather than the coordinator broker.

Monitor CPU usage, CPU throttling, GC pause p99, heap allocation, and pod restart events alongside commit metrics.

## 28. Distinguishing commit latency from fetch and poll latency

A Kafka consumer has multiple stages:

    poll/fetch
        |
        v
    deserialize
        |
        v
    process
        |
        v
    acknowledge
        |
        v
    commit
        |
        v
    next poll

Each metric answers a different question:

| Metric | Question |
|---|---|
| Fetch latency | How long does broker/client data retrieval take? |
| Poll duration | How long does one poll cycle take? |
| Listener processing duration | How long does the business listener take? |
| Commit latency | How long does the offset commit request take? |
| Consumer lag | How many offsets remain unconsumed/uncommitted per measurement method? |
| End-to-end event age | How long does an event take from publish to processing? |

A group with high lag might suffer from slow fetches, slow listeners, slow commits, overloaded downstreams, or partition skew. Never blame commits as the bottleneck without separating the stages.

Low commit latency alongside high listener p99 can still drive lag up. High commit latency with very low commit frequency may affect throughput less than expected.

## 29. Designing a commit latency dashboard

An operational dashboard can comprise four sections.

**A. Commit health**

- `commit-latency-avg` by consumer group/client.
- `commit-latency-max` by client.
- `commit-rate` and `commit-total` rate.
- Commit failures/timeouts from logs or app counters.

**B. Consumer progress**

- Committed offset progression.
- Consumer lag by partition/group.
- Oldest unprocessed record age.
- Records consumed/processed per second.

**C. Group lifecycle**

- Rebalance count/duration.
- Assigned partitions/active members.
- Listener container running state.
- `ConsumerStoppedEvent` and `NonResponsiveConsumerEvent`.

**D. Dependencies and brokers**

- Listener processing p95/p99.
- HTTP/database latency and saturation.
- Broker request queues, CPU, network, group coordinator load.
- JVM GC and CPU throttling.

Charts should allow drilling down from group level to instance/clientId/partition. When aggregating across clients, avoid simple averages that mask a single client with extreme commit latency.

## 30. Avg/max is not the same as p95/p99

Kafka clients typically emit `commit-latency-avg` and `commit-latency-max`, yet **not every version provides commit duration histograms** for computing p95/p99 directly.

- **Average:** shows broad trends while hiding tail spikes.
- **Maximum:** catches peaks while being sensitive to single outliers and window size.
- **p95/p99:** requires histograms or sufficient sample distributions; cannot be derived from avg and max.
- **Request failure rate:** a separate metric; low latency on successful requests does not rule out commit timeouts.

Never label a chart line `commit_p99` if the underlying source only exports `commit-latency-max`. For strict tail latency requirements, add appropriate instrumentation where commits are issued/callbacks received per client/container APIs.

When using a Micrometer `Timer`, enable histogram/SLO buckets before expecting Prometheus to compute quantiles from histograms. A plain Timer does not guarantee percentiles are published.

## 31. Setting alert thresholds

An alerting policy should not merely compare commit latency against a static constant.

Example:

    Warning:
      commit latency average > 100 ms for 5 minutes
      AND commit rate is high enough for metrics to be meaningful

    Critical:
      commit failures rising
      AND consumer lag/oldest age rising

    Incident:
      commit progress stalled completely
      AND producer is still publishing data
      AND consumer group has active consumers

Numbers are illustrative, not fixed Kafka standards. In a single-region cluster, 100 ms may be abnormal; in cross-region setups, baselines may be higher.

Combine:

1. Normal baselines by hour/day.
2. Commit rate to avoid alerting on a single sample.
3. Relative rise over baseline.
4. Error/timeout/rebalance signals.
5. Consumer lag and business freshness SLOs.
6. Blast radius: one consumer vs. multiple groups.

Alerting solely on a brief `commit-latency-max` spike causes alert fatigue.

## 32. When commit latency is low yet lag keeps rising

Scenario:

    CommitLatency: 8 ms (steady)
    ListenerProcessing: 500 ms/record
    InputRate: 400 records/s
    ConsumerCapacity: 100 records/s
    Lag rising

The bottleneck is business throughput, not offset commits. Shaving commit time from 8 ms to 3 ms barely helps when records wait half a second on a database.

Common culprits:

- Slow external APIs/databases.
- Rate limiters enforcing quotas.
- Hot partitions and skewed key distributions.
- Low consumer concurrency relative to partition counts.
- Blocking retries on bad data or failing dependencies.
- Suboptimal batch processing.

Inspect processing duration and dependency metrics before changing `AckMode`.

## 33. When commit latency is high yet lag stays low

Scenario:

    InputRate: 10 records/s
    ConsumerCapacity: 100 records/s
    CommitLatency: 120 ms
    Lag: near 0

With sparse load and ample headroom, high commit latency may not visibly hurt freshness.

Even so, keep watching:

- Commit failures or group instability.
- Shutdown/rebalance duration.
- Kafka transaction timeouts if using transactions.
- Risk of cascading failure if traffic spikes suddenly.
- Other consumer groups suffering from an overloaded coordinator.

Prioritize work based on SLO impact and trends rather than polishing a single number for prettier dashboards.

## 34. When commit latency rises after deployment

A helpful investigation timeline:

    T0: Deployment A uses AckMode.BATCH
    T1: Deployment B switches to AckMode.RECORD
    T2: Commit-rate jumps severalfold
    T3: Commit latency rises, lag rises
    T4: Roll back or adjust commit frequency safely

Questions to check:

1. Did `AckMode`, `syncCommits`, commit timeout, or commit retries change?
2. Did `max.poll.records` or listener concurrency change?
3. Were pods scaled up without changing partition counts?
4. Were transactions enabled on a new listener?
5. Did producer/consumer client versions change?
6. Did network region or broker routing change?
7. Did commit latency rise only on the new group or across the whole cluster?

Annotating deployments on dashboards helps separate config change side effects from independent broker outages.

## 35. Never reduce commit latency by committing early

An anti-pattern:

~~~java
@KafkaListener(topics = "payments")
public void consume(
        PaymentRequested event,
        Acknowledgment ack) {

    ack.acknowledge(); // Too early!

    paymentGateway.charge(
        event.paymentId(),
        event.amount()
    );
}
~~~

If the app acks/commits the offset before calling `paymentGateway` and crashes after ack, the consumer group can skip the event on restart even though payment never ran.

Proper business ordering example:

~~~java
@KafkaListener(topics = "payments")
public void consume(
        PaymentRequested event,
        Acknowledgment ack) {

    paymentGateway.chargeIdempotently(
        event.paymentId(),
        event.amount(),
        event.eventId()
    );

    ack.acknowledge();
}
~~~

Requires a listener container with an appropriate manual `AckMode`. Even when acking after side effects, there remains a window where the side effect succeeded while the offset failed to commit, leading to redelivery. Thus idempotency keys are essential.

**Early offset commits are never a valid performance optimization if they break delivery guarantees.**

## 36. Commit latency in batch listeners

With a batch listener, the application receives a list of records per invocation:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "orders-batch",
    containerFactory = "batchListenerFactory"
)
public void consumeBatch(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        orderService.processIdempotently(record.value());
    }
}
~~~

This example assumes the factory sets `setBatchListener(true)` and configures transaction/ack policies appropriately.

Batch committing reduces commit calls yet brings trade-offs:

- One failing record can impact many records in the batch.
- Processing an entire batch can approach `max.poll.interval.ms`.
- If a batch retries, side effects from earlier records before the failure may re-execute.
- Per-record recovery inside a batch depends on error handlers and exception classes.
- A batch commit's latency resembles a single commit, while protecting more records.

For accurate reporting, track `records-per-commit` (app-measured if needed), not just `commit-rate`.

## 37. Commit latency and DLT/recovery

When a record fails and is routed to a dead-letter topic, the container may need to update offsets once recovery succeeds.

If DLT publish succeeds yet offset commit fails, the source record can be redelivered; the recoverer may send to the DLT again unless idempotency or recovery handling covers it.

If the container commits the source offset even when DLT publishing fails, the failing record can be lost from the recovery path. Therefore:

- Monitor DLT send latency and failures separately.
- Never conflate DLT publish success with consumer offset commit success.
- If using Kafka transactions for recovery, monitor transaction commit outcomes.
- Record original `eventId`/headers to spot duplicates on redrive.
- Never treat high commit latency as an excuse to skip durable DLT publish confirmation.

High commit latency in the recovery path can delay clearing a poison record, letting partition lag keep growing.

## 38. Impact of producer transaction commit latency

A Kafka-to-Kafka transactional app can experience rising output latency due to slow producer transaction commits even while regular consumer offset commit metrics stay very low.

Example:

    Input -> listener -> KafkaTemplate.send(output)
        -> sendOffsetsToTransaction(input offsets)
        -> commitTransaction()
        -> downstream read_committed sees output

While a transaction remains open, `read_committed` downstreams may wait on the last stable offset. Measure separately:

- Producer transaction begin/commit/abort counts.
- Transaction duration.
- Transaction commit/abort errors.
- Producer send latency.
- End-to-end output visibility delay.

Never conclude "offset commit latency is normal, so the EOS flow is healthy" when the real bottleneck is the producer transaction coordinator or transaction timeouts.

## 39. Pairing commit latency with database durability

For consumers writing to a database:

    poll
      |
      v
    Database transaction begin
      |
      v
    INSERT/UPDATE
      |
      v
    Database COMMIT
      |
      v
    Kafka OFFSET COMMIT

This is typically the right order for at-least-once database processing: database side effects complete before Kafka commits progress. Yet if the Kafka commit fails, records can redeliver and database work may repeat.

Metrics to inspect separately:

| Metric | Meaning |
|---|---|
| Database commit latency | Latency for database to confirm transaction |
| Kafka commit latency | Latency for group coordinator to confirm offset |
| Listener end-to-end latency | Both processing and related commit steps |
| Duplicate detection count | Times idempotency rejected reprocessing |
| Consumer lag | Volume of unprogressed records |

If DBAs optimize database commits from 100 ms down to 10 ms while the Kafka coordinator still takes 200 ms per commit, throughput stays capped. Conversely, fast Kafka commits alongside slow DB transactions will not meaningfully boost listener throughput either.

## 40. Testing commit latency with integration tests

Commit latency depends on brokers, networks, group coordinators, and clients, so plain unit tests cannot prove real behavior.

Use Embedded Kafka or Testcontainers with a compatible Kafka broker. Scenario:

1. Create a multi-partition topic and test consumer group.
2. Configure a listener container with `AckMode.RECORD` and `syncCommits=true`.
3. Send a set of records with stable `eventId` values.
4. Capture client coordinator commit metrics and consumer throughput.
5. Re-run with `AckMode.BATCH` in a separate test setup.
6. Compare commit-rate, latency, and total processing duration.
7. Stop the consumer mid-batch and observe redelivery from the committed offset.
8. Enable idempotency and confirm side effects are not duplicated.
9. Trigger a rebalance and inspect commit errors/latency.
10. Simulate slow brokers/coordinators within test infrastructure limits.
11. Correlate with listener processing timers and lag.
12. Confirm no path commits offsets before durable side effects.

Never assert exact commit latency like 20.000 ms or absolute p99 in CI: schedulers, test brokers, and runners jitter. Tests should verify transaction/offset correctness and relative commit-frequency traits; tail-latency benchmarks belong in controlled load tests.

## 41. Testing commit error handling

Beyond the happy path, simulate:

**Commit timeout:** slow down the network/broker so `commitSync` times out or returns an uncertain outcome. Verify the app does not mark source records as "guaranteed committed" solely from side effects.

**Rebalance:** a consumer loses assignment mid-processing; verify the container does not try to commit offsets as the old owner in `onPartitionsLost`.

**Async callback failure:** if calling `KafkaConsumer.commitAsync` directly, verify callbacks log errors and never retry older offsets over newer offsets.

**Shutdown:** stop the container with in-flight records and verify graceful lifecycle and committed progress.

**Transactional read-process-write:** intentionally abort the Kafka transaction after sending outputs and verify `read_committed` downstreams never receive aborted outputs.

**Database side effects:** commit DB successfully while failing Kafka offset commit, then redeliver and confirm Inbox/idempotency blocks double updates.

These tests protect delivery guarantees, not just telemetry numbers.

## 42. Runbook when commit latency rises

An ordered investigation procedure:

1. **Verify the metric:** ms/s units, metric group, client ID, scrape timestamp, and metric source.
2. **Determine scope:** one pod, one consumer group, or the whole cluster?
3. **Compare commit-rate:** did commit request volume jump after a deploy/scale?
4. **Check commit failures:** timeouts, `CommitFailedException`, authorization, transaction errors.
5. **Inspect lag/freshness:** has the issue impacted business processing times yet?
6. **Measure business processing:** are listeners and dependencies slowing down together?
7. **Check consumer group:** rebalances, assignments, `max.poll.interval.ms`.
8. **Check broker coordinator:** CPU, request queues, I/O, replication, throttling.
9. **Check network:** RTT, cross-region paths, packet loss, TLS errors.
10. **Check JVM/pod:** GC, CPU throttling, memory pressure.
11. **Check configuration:** `AckMode`, `syncCommits`, commit timeouts, `max.poll.records`, concurrency.
12. **Pick one controlled change:** optimize frequency or fix root cause.
13. **Verify delivery guarantees:** duplicate window, idempotency, DLT, and transactions.
14. **Monitor post-fix:** commit latency, commit rate, lag, failures, and business SLOs.

Never alter `auto.offset.reset` or manually seek past records just to lower lag. Such actions hide unprocessed data loss.

## 43. Common mistakes

| Mistake | Why it is wrong | Remediation |
|---|---|---|
| Calling listener duration commit latency | Listener timers measure a different scope | Use consumer coordinator metrics |
| Calling `ack()` time Kafka commit latency | Ack does not guarantee commit was sent | Distinguish `AckMode` and commit outcomes |
| Watching only averages | Hides tail spikes | Pair with max/failures and histograms if available |
| Estimating p99 from avg and max | Lacks distribution data | Collect histograms from the right source |
| Setting `syncCommits=false` to "erase" latency | Request latency still exists; errors surface differently | Weigh trade-offs and callbacks |
| Committing every record without sizing coordinator | Floods coordinator with requests | Choose suitable batching |
| Committing huge batches without idempotency | Wide replay window | Use `eventId`/Inbox or shrink batches |
| Treating Kafka client commit metrics as TX commit time | Different mechanisms | Monitor producer transactions separately |
| Merely raising `max.poll.interval.ms` | Does not fix slow coordinators | Analyze commits, processing, and brokers |
| Restarting consumers on every spike | Causes rebalances and redeliveries | Check scope, apply cooldowns |
| Acking/committing before side effects | Risks skipping unfinished business work | Commit only after durable work |
| Averaging multiple client series unweighted | Masks a failing consumer | Drill down by client/group |
| Not verifying units after exporter mapping | Wrong alert thresholds ms/s | Standardize units |
| Treating `commit-total` as messages processed | One commit can cover many records | Track records consumed/processed separately |

## 44. Monitoring implementation checklist

Before using commit latency as an operational signal, verify:

- Are you measuring regular offset commits or transaction commits?
- Do Kafka consumer client metrics export `commit-latency-avg` and `commit-latency-max`?
- Were metric units verified after passing through the exporter?
- Are sensible labels attached for application, consumer group, and client ID?
- Are `AckMode` and `syncCommits` known for each listener container?
- Is commit frequency aligned with `max.poll.records` and concurrency?
- Are commit failures/timeouts tracked separately?
- Are listener processing latency and dependency latency measured?
- Are consumer lag, oldest record age, and committed offset progression monitored?
- Are rebalances and `ConsumerStoppedEvent` monitored?
- Is producer transaction duration measured if using Kafka EOS?
- Does an idempotency policy protect against redeliveries when commits fail?
- Were mid-batch restarts, DLT recovery, and rebalances tested?
- Does a pre-deploy baseline exist for comparison?
- Do runbooks distinguish broker, network, and application bottlenecks?

For useful alerts, combine at least three dimensions: **commit health**, **consumer progress**, and **business processing**.

## 45. Conclusion

**Commit latency tells you how long the Kafka consumer takes to complete offset commit requests with the group coordinator per the metric mechanism in use.** It matters because a consumer with fast business logic yet slow synchronous commits can still suffer capped throughput, rising lag, or prolonged rebalances.

To optimize commit latency properly, distinguish `commitSync` from `commitAsync`, understand `AckMode`, separate commit request metrics from listener processing, and never conflate offset commits with Kafka producer transactions or database commits. Batching and lowering commit frequency boost efficiency while widening redelivery windows; therefore, pair them with idempotency, DLT/recovery, and failure testing.

In production, ask not only "how many milliseconds did the commit take," but also **"do offsets advance safely after business completion, does the consumer meet freshness SLOs, and on failure can the system reprocess records without corrupting side effects?"** That is the true value of monitoring commit latency in Spring Kafka Reliability Operations.
