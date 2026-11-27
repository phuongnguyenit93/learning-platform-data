# Load Testing, Lag Monitoring, and Fault Recovery Verification

A Spring Cloud Stream application can start up cleanly and still fail to sustain production load. Producers can emit events faster than consumers process them; a single partition can become overloaded; retries can mask prolonged errors; or a consumer may restart yet fail to drain its backlog within acceptable operational windows. Therefore, you must measure the full event path, track queue lag, and actively inject faults to verify recovery.

This exercise builds a verification workflow for a Supplier/Function/Consumer pipeline running on Kafka, RabbitMQ, or Pulsar. We will define target load, generate reconcilable test data, observe throughput and lag, stop or throttle consumers, restart services, and verify that all data is processed accurately and backlog returns to normal.

## 1. Expected Outcomes

After completing this exercise, you will be able to:

- Distinguish throughput, processing latency, backlog, consumer lag, and oldest message age.
- Design baseline, steady-state, burst, and soak load tests.
- Measure incoming events, successful completions, errors, retries, and processing durations using Micrometer.
- Read per-partition lag in Kafka, queue depth and unacknowledged messages in RabbitMQ, and subscription backlog in Pulsar.
- Calculate backlog drain time while producers continue publishing.
- Verify consumer restarts, broker reconnects, redeliveries, retries, and dead-letter queues.
- Distinguish data loss from duplicate processing while validating consumer idempotency.
- Draw conclusions backed by metrics and predefined acceptance criteria.

## 2. Pipeline Model and Measurement Points

Consider an order processing flow:

```text
Supplier / Producer
        |
        v
   Broker topic / queue
        |
        v
Consumer group / subscription
        |
        v
Business processing Function
        |
        v
Database or target service
```

Each point yields a distinct set of metrics:

| Measurement point | Question to answer | Metrics to collect |
|---|---|---|
| Producer | How many events is the app emitting? | Sent count, send rate, send errors |
| Broker | How many events are waiting? | Queue depth, log end offset, subscription backlog |
| Consumer | Is the consumer keeping up with the producer? | Lag, active consumer count, consume rate |
| Function | How long does each event take to process? | Processing latency, error counts, retries |
| Target system | Are outcomes recorded accurately? | Unique record count, transaction errors, write latency |
| End-to-end pipeline | How long from emission to completion? | End-to-end latency, oldest message age |

Never look solely at CPU usage or sent message counts. Low CPU can coincide with growing backlogs if consumers are blocked waiting on external services; a producer reporting a successful send does not prove business logic completed.

## 3. Distinguishing Throughput, Latency, and Lag

**Throughput** is the number of events processed per unit of time, typically measured in events/second. Separate at least three rates:

- Ingress rate: rate at which producers push events to the broker.
- Consume rate: rate at which consumers pull events from the broker.
- Completion rate: rate at which business processing finishes successfully.

These three rates can differ. Consumers may read quickly yet process slowly, increasing in-memory or unacknowledged messages.

**Processing latency** is the time a function takes to handle one event, from start to end of business execution. **End-to-end latency** is the time from event creation to business completion, including broker wait time, consumer wait time, processing, and retries.

**Backlog** is the amount of queued work waiting to be processed. **Consumer lag** typically represents the gap between the latest log position and the consumer group's committed position. Continuously rising lag means consumers are falling behind producers. Lag is a count of records or messages as reported by the broker; it does not directly tell you how many seconds events are waiting.

Also track **oldest message age**—the age of the oldest unfinished event. Two consumer groups with the same 10,000-record lag under different ingress rates can have vastly different wait times.

| Metric | Meaning | Used to detect |
|---|---|---|
| Ingress rate | Events entering the broker per second | Rising incoming load |
| Completion rate | Events completed per second | True processing capacity |
| Lag / backlog | Number of waiting events | Consumers falling behind |
| Oldest message age | How long the oldest event has waited | Latency SLA violations |
| Processing p50/p95/p99 | Processing time percentiles | Tail slowdowns on a subset of requests |
| Retry rate | Number of retry attempts | Transient errors or unstable dependencies |
| DLQ rate | Events routed to dead-letter | Events unprocessable under current policy |
| Rebalance / redelivery | Consumer group reassignment or broker redelivery | Consumer disconnects, restarts, or failed ACKs |

A healthy average can hide a subset of very slow events. When evaluating latency, examine p95 and p99 alongside p50, sample counts, and observation windows.

## 4. Calculating Processing Capacity and Backlog Drain Time

Let:

- `λ`: rate of incoming events (events/second).
- `μ`: completion rate of the consumer group (same unit).
- `B`: number of waiting events.
- `t`: observation duration.

If `μ > λ`, the consumer has spare capacity to drain the backlog. If `μ = λ`, the backlog barely shrinks. If `μ < λ`, the backlog continues growing.

When load is relatively steady and processing capacity is constant, approximate drain time is:


`T_drain = B / (μ - λ)`, for `μ > λ`.


For example, if consumers complete 1,200 events/s while producers continue sending 900 events/s and backlog stands at 108,000 events:


`T_drain = 108,000 / (1,200 - 900) = 360 seconds`.


If producers stopped completely, approximate time would be `108,000 / 1,200 = 90` seconds. Never divide backlog by consumer rate alone and conclude that is your recovery time while producers are still active.

When `μ < λ`, backlog grows at approximately `λ - μ`. For example, if producers emit 1,000 events/s while consumers finish only 750 events/s, backlog grows by roughly 250 events/s. After 10 minutes, backlog can grow by about 150,000 events absent caps or traffic shifts.

These formulas are operational estimates. Real-world behavior is also shaped by key skew, partition counts, batching, retries, database latency, garbage collection, and broker speed. Base capacity planning on measurements taken over sufficiently long windows.

## 5. Preparing the Test Environment

Before running load tests, record configurations and test conditions:

- Java, Spring Boot, Spring Cloud Stream, and binder versions in use.
- Broker topology, partition or queue counts, replication, and retention policies.
- Consumer group or subscription, instance count, concurrency, and active consumer count.
- Retry, backoff, ack/commit, DLQ, and dependency timeout settings.
- CPU, RAM, container limits, connection pools, and database settings.
- Test dataset, payload sizes, and key distribution.
- Start time, warm-up window, steady-state window, and recovery window.

Use isolated test topics, queues, or namespaces to avoid polluting shared environments. Tag each run with an identifier like `runId=load-2026-11-24-a` and assign unique IDs to every event. Synchronize clocks across load generators, consumers, and observability backends if measuring end-to-end latency via timestamps.

Never put sensitive data into test payloads. Use realistic payload sizes and structures; artificially tiny payloads produce overly optimistic throughput numbers.

## 6. Configuring a Consumer with Group and DLQ

The example below uses the Kafka binder and a function named `processOrder`. The derived input binding name is `processOrder-in-0`.

```yaml
spring:
  application:
    name: order-stream
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 3
            concurrency: 3
    kafka:
      binder:
        brokers: localhost:9092
      bindings:
        processOrder-in-0:
          consumer:
            enable-dlq: true
```

In this configuration:

- `group` creates a stable consumer group identity so the broker tracks consumption progress.
- `max-attempts` sets retry attempts per Spring Cloud Stream consumer settings.
- `concurrency` instructs the Kafka binder to run multiple consumer threads for the binding.
- `enable-dlq` enables Kafka binder dead-letter handling for events that exhaust the retry policy.

Parallel consumers within one group are bounded by assignable partitions. If a topic has 3 partitions, raising `concurrency` to 8 will not create 8 independent partition readers; extra consumers sit unassigned. Increasing partitions affects per-key ordering, data distribution, and operational plans, so evaluate carefully before changing it.

Exact property names and behavior vary by Spring Cloud Stream and binder versions. Cross-check with the documentation matching your project's BOM. For RabbitMQ and Pulsar, queue/subscription, retry, and dead-letter settings follow each binder and broker's specific mechanisms.

## 7. Instrumenting Functions with Micrometer Metrics

Spring Boot Actuator and Micrometer provide visibility into processing times, failure counts, and end-to-end latency. The example below uses stably named timers and counters. Never attach `eventId`, email, order ID, or per-message values as metric tags, because time-series cardinality will grow without bound.

Metrics class:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.TimeUnit;

@Component
public class OrderMetrics {
    private final Timer processingTimer;
    private final Timer endToEndTimer;
    private final Counter processingFailures;

    public OrderMetrics(MeterRegistry registry) {
        this.processingTimer = Timer.builder("app.orders.processing")
                .description("Time spent processing one order event")
                .register(registry);

        this.endToEndTimer = Timer.builder("app.orders.end.to.end")
                .description("Time from event creation to successful processing")
                .register(registry);

        this.processingFailures = Counter.builder("app.orders.processing.failures")
                .description("Number of failed processing attempts")
                .register(registry);
    }

    public void recordProcessing(long elapsedNanos) {
        processingTimer.record(elapsedNanos, TimeUnit.NANOSECONDS);
    }

    public void recordEndToEnd(Instant createdAt) {
        Duration delay = Duration.between(createdAt, Instant.now());
        if (!delay.isNegative()) {
            endToEndTimer.record(delay);
        }
    }

    public void recordFailure() {
        processingFailures.increment();
    }
}
```

Consuming function:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

import java.time.Instant;
import java.util.function.Consumer;

@Configuration
public class OrderFunctions {
    @Bean
    Consumer<Message<OrderCreated>> processOrder(
            OrderService orderService,
            OrderMetrics metrics) {

        return message -> {
            long started = System.nanoTime();
            OrderCreated event = message.getPayload();

            try {
                orderService.handle(event);
                metrics.recordEndToEnd(event.createdAt());
            } catch (RuntimeException exception) {
                metrics.recordFailure();
                throw exception;
            } finally {
                metrics.recordProcessing(System.nanoTime() - started);
            }
        };
    }
}

record OrderCreated(String eventId, Instant createdAt, int quantity) {}
```

This assumes `OrderService.handle` implements existing application business logic. The function rethrows exceptions so Spring Cloud Stream's error-handling and retry mechanisms operate. Swallowing exceptions and returning normally lets the binder treat the message as succeeded and advance progress despite business failure.

The processing timer records on both success and failure paths. The end-to-end timer records only on successful completion. The failure counter tracks failed attempts; an event retried three times increments the counter multiple times. To count unique failed events, reconcile by `eventId` in storage or emit an appropriate business metric without putting `eventId` in tags.

`createdAt` must be stamped at the producer with synchronized host clocks. Clock skew can cause negative or distorted end-to-end latencies. `System.nanoTime()` is suitable for measuring durations within the same process; never exchange it as a wall-clock timestamp across machines.

## 8. Enabling Actuator and Exporting Metrics

Add Actuator and the Prometheus registry matching your Spring Boot version. Example configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
  metrics:
    distribution:
      percentiles-histogram:
        app.orders.processing: true
        app.orders.end.to.end: true
```

Commonly used endpoints:

- `/actuator/health`: health indicator status.
- `/actuator/metrics`: discover meters and inspect individual metrics.
- `/actuator/prometheus`: Prometheus scrape format once the registry dependency is added.

Example metric checks:

```bash
curl http://localhost:8080/actuator/metrics/app.orders.processing
curl http://localhost:8080/actuator/prometheus
```

In production, expose only necessary endpoints and enforce authentication, authorization, and network policies. Metrics endpoints reveal operational internals; never leave Actuator endpoints exposed unprotected on the Internet.

Micrometer timers provide count, total time, and max by default; histograms or percentiles require registry-aligned configuration. Client-side percentiles and server-side histograms behave differently. When comparing p95/p99 across multiple instances, prefer histograms with compatible buckets so observability backends can aggregate accurately.

## 9. Monitoring Lag on Kafka

Kafka stores logs per partition. Each consumer group tracks its own consumption progress. Lag is typically calculated as log end offset minus the group's committed offset per partition. This is an offset distance, not seconds of wait time.

Use Kafka's bundled CLI tool:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-processor
```

On Windows, use `kafka-consumer-groups.bat` inside the `bin\windows` directory of the Kafka distribution.

Output includes columns like `CURRENT-OFFSET`, `LOG-END-OFFSET`, and `LAG`. Interpret per partition:

- Lag climbing on one partition while others stay near 0 points to key skew, a slow consumer, or assignment imbalance.
- Lag climbing evenly across all partitions indicates aggregate consumer capacity is below ingress rate.
- Lag dropping after scaling consumer capacity confirms the extra capacity helps.
- Sudden lag shifts coinciding with rebalances point to consumer restarts, membership churn, or assignment changes.

Inspect consumer group state and members when diagnosing rebalances. A single point-in-time `describe` snapshot is insufficient to declare stability; sample periodically and examine trends.

Offsets represent log positions, not necessarily exact business message counts when transactions, filtered records, or custom offset commits are involved. Reconcile data using event IDs and business outcomes alongside lag.

## 10. Monitoring Backlog on RabbitMQ

RabbitMQ does not express lag using Kafka consumer offsets. For queues, monitor at least:

- `messages_ready`: messages waiting to be delivered to consumers.
- `messages_unacknowledged`: messages delivered to consumers but not yet acknowledged.
- `consumers`: active registered consumers.
- Publish, deliver, ack, and redeliver rates.
- Oldest message age if exposed by monitoring plugins or instrumentation.

Quick CLI inspection:

```bash
rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
```

If `messages_ready` rises, consumers cannot pull fast enough. If `messages_unacknowledged` climbs continuously, consumers are processing slowly, holding messages too long, or failing to ACK. If redeliveries rise, investigate consumer crashes, closed channels, timeouts, and reject/requeue policies.

With dead-letter exchanges or dead-letter queues, monitor DLQ ingress and dead-letter reasons. Low depth on the main queue does not indicate health if messages are rapidly draining into a DLQ.

## 11. Monitoring Backlog on Apache Pulsar

With Pulsar, monitor state per topic and subscription. Useful metrics include:

- Subscription message backlog.
- Message rate in and out.
- Unacknowledged message count and redelivery counts.
- Connected consumers, subscription state, and load distribution.
- DLQ or dead-letter topics if dead-letter policies are enabled.

Inspect topic stats with:

```bash
pulsar-admin topics stats persistent://tenant/namespace/orders
```

In the output, inspect the subscription matching your application consumer along with backlog, rate, unacked, and redelivery fields provided by your broker version. Exact field names and JSON structure can vary across Pulsar releases.

Do not interpret Pulsar backlog using Kafka offset formulas. Use subscription metrics and message age to judge whether consumers are keeping up. Also verify backlog quotas, retention, and subscription policies so expired or quota-trimmed messages are not mistaken for successful consumption.

## 12. Designing Repeatable Load Tests

A useful load test must be reproducible and reflect actual application behavior. Craft realistic payloads, keep message sizes steady per scenario, and match production key distributions. If every message uses the same Kafka key, load piles onto a single partition and fails to test distributed throughput.

Execute these phases:

1. **Baseline:** run at low load to confirm pipeline, dashboards, and data reconciliation work.
2. **Warm-up:** ramp gradually so JVM JIT, connection pools, and caches stabilize.
3. **Ramp-up:** step up ingress rate, holding each step long enough to observe lag trends.
4. **Steady-state:** hold target load for a predetermined duration.
5. **Burst:** inject sudden spikes to observe peak absorption and backlog growth.
6. **Soak:** sustain load longer to uncover memory leaks, connection leaks, prolonged GC, or gradual degradation.
7. **Recovery:** reduce or stop load and measure backlog drain time and return to baseline.

Record start/end timestamps, actual ingress rate, completion rate, p95/p99, lag, oldest message age, error rates, and resource utilization for every phase. Never record only intended target load; record what the producer actually emitted.

### 12.1. Generating Load via `StreamBridge`

You can use a dedicated producer app or a load-test profile. The following example emits JSON events through output binding `orders-out-0`:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
```

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.cloud.stream.function.StreamBridge;

import java.time.Instant;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

@Configuration
@Profile("load")
public class LoadPublisher {
    @Bean
    ApplicationRunner publishLoad(StreamBridge streamBridge) {
        return args -> {
            int totalEvents = 100_000;
            long targetPerSecond = 1_000;
            long intervalNanos =
                    TimeUnit.SECONDS.toNanos(1) / targetPerSecond;
            long nextSend = System.nanoTime();

            for (int i = 0; i < totalEvents; i++) {
                OrderCreated event = new OrderCreated(
                        "load-" + i,
                        Instant.now(),
                        1);

                boolean accepted = streamBridge.send("orders-out-0", event);
                if (!accepted) {
                    throw new IllegalStateException(
                            "StreamBridge did not accept event " + event.eventId());
                }

                nextSend += intervalNanos;
                long waitNanos = nextSend - System.nanoTime();
                if (waitNanos > 0) {
                    LockSupport.parkNanos(waitNanos);
                }
            }
        };
    }
}
```

Run the publisher under the `load` profile in a test environment. Adjust event counts, target rates, and payloads per scenario. For higher concurrent load, run multiple producer instances or use a concurrency-capable load generator.

`StreamBridge.send` returning `true` indicates acceptance by the application channel; it does not substitute for proof that consumers completed business work or persisted data durably. To conclude a test, reconcile unique emitted event IDs against final downstream business outcomes.

Never enable the `load` profile in production. When generating concurrent load, assign globally unique event IDs across all producers to avoid miscounting or overwriting records.

### 12.2. Measuring Broker Capacity Independently

For Kafka, `kafka-producer-perf-test.sh` measures raw broker write throughput using fixed-size payloads. Example:

```bash
kafka-producer-perf-test.sh \
  --topic broker-load-test \
  --num-records 1000000 \
  --record-size 512 \
  --throughput 5000 \
  --producer-props bootstrap.servers=localhost:9092 acks=all
```

This measures raw broker/producer performance with synthetic records. It bypasses Spring Cloud Stream JSON conversion, functions, databases, and retries. Use it to isolate broker ceilings from business-processing ceilings, never as sole evidence of end-to-end throughput.

## 13. Defining Acceptance Criteria Before Running

No single lag or p99 threshold fits every system. Thresholds must derive from SLAs, emission rates, retention windows, and required recovery targets.

Sample criteria set:

| Category | Criterion to define |
|---|---|
| Target load | Ingress rate sustained across the selected load profile |
| Throughput | Completion rate meets or exceeds business demand |
| Backlog | No continuous growth during steady-state load |
| Latency | p95/p99 and oldest message age remain within SLA |
| Errors | Business error and retry rates stay within limits |
| DLQ | Zero valid events unexpectedly routed to DLQ |
| Recovery | Consumers restart, resume processing, and drain backlog within RTO |
| Completeness | Every valid event ID reaches a final outcome |
| Uniqueness | Redeliveries produce zero duplicate side effects |
| Resources | CPU, heap, GC, connections, and broker storage remain within bounds |

Document measurement windows and warm-up exclusions. A system might sustain target throughput for 30 seconds yet collapse over 30 minutes. Criteria must reflect required operational duration.

## 14. Checking Lag Under Steady-State Load

During steady-state runs:

1. Record ingress rate from producers or broker metrics.
2. Record completion rate from business metrics.
3. Sample lag/backlog per partition, queue, or subscription periodically.
4. Record processing p50/p95/p99 and end-to-end p95/p99.
5. Monitor retries, DLQ, redeliveries, and rebalances.
6. Record CPU, heap, GC, threads, connection pools, DB latency, and broker resources.
7. Compare trends across consecutive windows.

If ingress exceeds completion over sustained intervals, backlog grows. If rates match yet oldest message age climbs, inspect message distribution, prolonged retries, hot partitions, or stuck events.

When one partition shows noticeably higher lag, inspect key distribution and per-business-type processing times. Never raise concurrency before understanding partition and dependency limits; adding threads can increase lock contention or DB load without boosting completion rate.

## 15. Verifying Consumer Stop and Restart

This is the foundational test proving consumers resume from broker-saved progress:

1. Emit a known batch of events with unique IDs and record the total.
2. Wait for consumers to stabilize and record baseline lag.
3. Stop all consumer instances while producers keep emitting at the target rate.
4. Observe backlog growing and confirm producers keep publishing smoothly.
5. Restart consumers with the same group or subscription.
6. Monitor consumer assignments, completion rate, lag, and oldest message age.
7. Wait for backlog to return to normal thresholds per acceptance criteria.
8. Reconcile all event IDs and final business outcomes.

With Kafka, keep the exact same group ID so consumers resume from the group's committed offsets. Creating a new group can cause reading from a different position per offset-reset policy, invalidating test results.

With RabbitMQ, verify unacknowledged messages are redelivered after channels or connections close. With Pulsar, inspect subscription backlogs and redeliveries on the active subscription. Never directly compare raw metrics across the three brokers as if they shared identical semantics.

## 16. Verifying Failures Between Processing and Message Acknowledgment

A critical failure mode occurs when a consumer executes side effects but fails to acknowledge progress to the broker. Example:

1. Consumer receives event `order-123`.
2. Database commits the order update.
3. Process terminates before offset commit or ACK.
4. Broker redelivers the event after consumer restart.

Under at-least-once delivery, this causes repeat delivery and requires idempotency control. Design an explicit test killing the process right after DB commit but before ACK/commit, then verify redelivery creates zero duplicate side effects.

Never assume all binder configurations commit or ACK at the same point. Check ack modes, auto-commit, transactions, and error handling for your binder. If acknowledgment occurs before durable business persistence, failures lose data; if after durable persistence, failures cause redeliveries. Align the policy with system requirements.

## 17. Verifying Retries and Dead-Letter Handling

Create a deterministic test payload that triggers failure—such as an invalid business field or a code causing a dependency error. Execute:

1. Send one valid event and one intentionally failing event.
2. Verify the valid event completes successfully.
3. Verify the failing event retries the configured number of times with expected backoff.
4. Inspect logs and metrics to distinguish retry attempts from unique events.
5. Verify the event moves to the DLQ or dead-letter topic/queue after exhausting retries per binder config.
6. Confirm payload, headers, exception metadata, and `eventId` are intact for investigation.
7. Fix the root cause and replay from the DLQ via a controlled process.
8. Reconcile side effects to confirm replay does not duplicate orders or transactions.

A DLQ isolates unprocessable events; it does not fix data automatically. Never replay an entire DLQ to the main topic without identifying root cause, ordering, replay rate, and idempotency guarantees. A poison payload can trigger retry loops or spike new backlogs.

## 18. Verifying Broker Reconnects and Rebalances

Simulate temporary broker unavailability or disrupt network connectivity between consumers and the broker in a test environment. Track:

- Timestamps when connection errors appear in logs and metrics.
- Reconnect attempt counts and connection recovery time.
- Consumer group or subscription status.
- Rebalances, partition assignments, and active consumer counts.
- Lag/backlog during the outage.
- Processing rate immediately after connectivity returns.
- Unique completed event IDs and duplicate side effects.

Do not check solely whether the process stays running. A container can remain `Running` while its consumer stops receiving messages. Health checks should reflect vital application dependencies, while dashboards expose consumption progress and lag.

If restarts recur repeatedly, inspect timeouts, heartbeats, session timeouts, max poll intervals, and batch processing durations for Kafka; inspect connection/channel recovery and consumer acknowledgment timeouts for RabbitMQ; inspect consumer reconnects, subscriptions, and redelivery policies for Pulsar. Tune parameters according to your actual broker and binder versions.

## 19. Verifying Slow Consumers and Partition Skew

Create a scenario slowing part of the pipeline—such as adding latency to a downstream call or concentrating keys onto a single partition. Observe:

- Does lag rise across all partitions or only one?
- Which consumer exhibits elevated processing p95/p99?
- Are database connection pools or thread pools saturated?
- Does increasing concurrency raise completion rate or merely worsen contention?
- Once the slowdown clears, does the backlog drain completely?

If only one partition runs hot, adding more instances will not help because a single partition is assigned to at most one consumer in the same group at a time. Review keys, partitioning strategy, and partition counts. Changing keys can affect per-entity event ordering, so preserve required business invariants.

If all partitions lag while the database is saturated, adding consumer threads can make things worse. Find the true bottleneck—dependencies, batching, connection pools, CPU, network, or broker.

## 20. Idempotency and Data Reconciliation

In distributed pipelines, consumers can receive the same event multiple times after timeouts, crashes, or retries. Counting total function invocations does not tell you how many unique business operations succeeded.

Every event needs a stable identifier such as `eventId`. On the target system, use a unique constraint or inbox table to record processed event IDs within the same transaction as business mutations.

Conceptual example:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Inside the processing transaction, attempt to insert `event_id`. If the key already exists, the event was applied earlier; skip duplicate side effects per business rules. Recording the marker and updating data must share an appropriate transaction so you never end up with a committed marker without business changes, or committed business changes without an idempotency marker.

During reconciliation, compare these sets:

- `sentIds`: event IDs emitted by producers per test logs.
- `completedIds`: event IDs with finalized business outcomes.
- `duplicateAttempts`: how many times the same event ID was redelivered or reprocessed.
- `failedIds`: event IDs lacking final outcomes and sitting in retry/DLQ.

Check `sentIds - completedIds` to uncover missing events; check repeated event IDs in side effects to detect duplicates. Matching total counts alone does not guarantee matching ID sets.

## 21. Measuring Recovery Time and Setting RTO/RPO

**RTO** is the target time for a service to return to acceptable operation after an incident. For event pipelines, define the completion milestone clearly: consumer reconnected, completion rate restored, or backlog fully drained. If recovery requires clearing the backlog, RTO must account for drain time.

**RPO** is the maximum acceptable data loss. For test events, count producer-confirmed event IDs lacking final outcomes once recovery finishes. Separate events sitting in DLQs, expired past retention, or awaiting replay so states are never conflated.

Record a timeline for each run:

| Milestone | Timestamp to record |
|---|---|
| T0 | Load generation starts |
| T1 | Fault injection starts |
| T2 | Consumer or broker detects failure |
| T3 | Connection/consumer recovers |
| T4 | Completion rate returns to target |
| T5 | Backlog and oldest message age return to normal |
| T6 | Data reconciliation completes |

From the timeline, compute detection time, consumer recovery time, and backlog drain time. These are distinct components; a system may reconnect in seconds yet take many minutes to clear its backlog.

## 22. Example Recovery Calculation

Suppose a test yields these numbers:

- Producer maintains 900 events/s.
- Consumer group completes 1,200 events/s under healthy operation.
- Consumers are stopped for 120 seconds.
- Retention limits do not drop messages during the test window.

Approximate backlog buildup:


`B = 900 × 120 = 108,000 events`.


Once consumers restart, spare capacity is:


`μ - λ = 1,200 - 900 = 300 events/second`.


Estimated drain time:


`T_drain = 108,000 / 300 = 360 seconds`.


If the recovery target is 5 minutes, 1,200 events/s capacity is insufficient here. You must either throttle ingress during recovery, increase true processing capacity, or adjust RTO per product requirements. Raising completion rate to 1,500 events/s yields 600 events/s spare capacity and roughly 180 seconds drain time.

Conclusions must be verified by post-change measurements: can 1,500 events/s actually be sustained, does the database hold up, does p99 stay within SLA, and are business outcomes 100% complete?

## 23. Dashboards and Alerts

An operational dashboard should organize charts into:

1. **Traffic:** ingress rate, consume rate, completion rate.
2. **Backlog:** Kafka lag by group/partition; RabbitMQ ready and unacked; Pulsar subscription backlog.
3. **Latency:** processing p50/p95/p99, end-to-end p95/p99, oldest message age.
4. **Reliability:** error rate, retry rate, redeliveries, DLQ rate, rebalances, and reconnects.
5. **Resources:** CPU, heap, GC pauses, thread pools, connection pools, DB latency, and broker storage.

Alerts should combine trends and impact. For example, alert when lag climbs continuously across multiple windows and oldest message age breaches SLA; alert separately on DLQ growth; alert when completion rate lags behind ingress rate persistently. Static lag thresholds rarely fit topics with varying traffic profiles.

Use bounded-cardinality tags such as function name, binder, environment, or outcome. Avoid tagging by event ID, user ID, order ID, or exception message. Use logs with correlation IDs or traces to debug specific events rather than creating a metric time series per event.

## 24. Quick Diagnostic Table

| Symptom | Possible cause | How to verify |
|---|---|---|
| Lag rises uniformly | Consumer capacity below ingress | Compare ingress vs. completion rates, CPU, DB latency |
| Only one partition has high lag | Key skew or slow consumer on that partition | Inspect per-partition lag, key distribution, processing time |
| Low lag but high end-to-end latency | Events take long after delivery | Check processing timers and dependency latencies |
| RabbitMQ `ready` climbs, `unacked` low | Missing consumers or consumers not pulling | Check consumer counts, bindings, and prefetch |
| `unacked` climbs continuously | Slow processing or ACKs stuck | Check processing duration, timeouts, channels, and exceptions |
| Pulsar backlog climbs | Subscription falling behind or inactive consumers | Inspect subscription stats, consumers, and redeliveries |
| Retries climb while throughput drops | Failing dependency or poison messages | Classify exceptions, backoff, and retry ratios |
| DLQ grows | Malformed payloads or misaligned error policies | Read error metadata, schemas, and event IDs |
| Repeated rebalances | Consumer restarts, heartbeat or poll timeouts | Check group logs, processing duration, and timeouts |
| Duplicate data after restart | Redelivery after business commit | Check commit/ACK boundaries and idempotency |
| Missing data after restart | Early ACK/commit, retention expiry, or target write failure | Reconcile event IDs, offsets, transactions, and broker retention |
| Low CPU yet lag grows | Consumers blocked on I/O or dependencies | Check thread dumps, DB/network latency, and connection pools |

## 25. Complete End-to-End Exercise Workflow

Execute sequentially and record results at each step:

1. Create test topics/queues and configure a stable consumer group or subscription.
2. Enable metrics for processing latency, end-to-end latency, and processing failures.
3. Enable metrics/Prometheus endpoints in the test environment.
4. Set up a producer generating unique event IDs and recording all emitted IDs.
5. Run baseline, verify end-to-end flow, and confirm clean reconciliation.
6. Run ramp-up then steady-state; record ingress, completion, lag, and p95/p99.
7. Inject a burst; observe backlog spike and recovery drain time.
8. Stop consumers while producers continue publishing; measure backlog growth rate.
9. Restart consumers; measure reconnect time, completion rate, and drain time.
10. Inject failure after DB write but before ACK/commit; verify redelivery and idempotency.
11. Inject poison messages; verify retries, DLQ routing, and controlled replay.
12. Reconcile event IDs, side effects, and final outcomes against target RTO/RPO.

Re-run each scenario at least once after major configuration changes. Document which single change drove the difference; never alter partitions, concurrency, batch sizes, and connection pools simultaneously if you want to isolate root causes.

## 26. Extension Exercises

**Exercise 1 — Finding Throughput Limits**

Step up load incrementally to find the highest ingress rate where completion keeps up, backlog stays flat, and p99 meets SLA. Repeat with small payloads and realistic production-sized payloads. Explain the limiting bottleneck in each case.

**Exercise 2 — Calculating Drain Time**

At a given moment, backlog is 240,000 events, producers emit 600 events/s, and consumers complete 1,000 events/s. Compute approximate drain time. Next, suppose producers speed up to 1,000 events/s; explain what happens to the backlog.

**Exercise 3 — Detecting Hot Partitions**

Generate traffic with evenly distributed keys, then shift to a single key dominating most messages. Compare per-partition lag, completion rate, and p99. Propose a key distribution strategy that preserves required business ordering.

**Exercise 4 — Testing Duplicates**

Inject a failure right after database commit but before consumer message acknowledgment. Record message delivery counts, function invocation counts, and created side effects. Add idempotency and re-run to prove side effects apply only once.

**Exercise 5 — Testing DLQ**

Emit an invalid event, verify retry counts, DLQ metadata, and replay after fixing the data. Prove that valid events continue processing normally per system policy.

## 27. Exercise Completion Criteria

Measurement is complete only when evidence exists for all of the following:

- Target load and test conditions are documented.
- Ingress rate, completion rate, lag/backlog, and latency were observed under steady-state load.
- At least one backlog buildup and post-recovery drain time were measured.
- At least one consumer restart or broker reconnect was verified.
- Retries and DLQs operated per configured policy.
- Event IDs were reconciled to detect both missing data and duplicate processing.
- Pass/fail verdicts against RTO/RPO and SLAs are explicitly backed by data.

If targets are missed, document the uncovered bottleneck—such as partition skew, database throughput, retry storms, or consumer concurrency. A strong report identifies which metric proves the bottleneck and which follow-up test will validate the fix.

## 28. References

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Spring Cloud Stream Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/)
- [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Concepts](https://micrometer.io/docs/concepts)
- [Apache Kafka Operations — Consumer Groups](https://kafka.apache.org/documentation/#basic_ops_consumer_group)
- [RabbitMQ Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [Apache Pulsar — Topic Stats](https://pulsar.apache.org/docs/next/administration-stats/)

Cross-check documentation matching the exact Spring Boot, Spring Cloud Stream, binder, and broker versions used in your module. Metric names exposed by broker exporters, retry configurations, and dead-letter behaviors can differ across versions.
