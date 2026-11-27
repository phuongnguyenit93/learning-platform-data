# Measuring queue wait time and processing duration

An order is published as a message for the Inventory Worker to process asynchronously. The dashboard shows average processing time is only 80 ms, yet users still wait several seconds to see results. The cause may be that the message sits in the queue long before a consumer receives it. If you only measure processing time inside the handler, the system misses latency caused by backlog, insufficient consumer capacity, or retry schedules.

The **Measuring queue wait time and processing duration** lesson belongs to the **Messaging and task observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understanding context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production.

> **Principle:** Measure pre-processing wait time (queue wait), execution time (processing duration), and end-to-end age (publish to completion) separately. The three measurements answer three different questions. Do not assume a queue is healthy just because the handler runs fast; nor sum retry attempts as if they were independent messages when measuring the experience of a single logical job.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish queue wait time, processing duration, and end-to-end message age.
2. Identify appropriate timestamps at publish, enqueue, receive/start, retry, and completion.
3. Understand the impact of broker semantics, consumer concurrency, prefetch, and acknowledgement.
4. Measure wait time and processing duration using Micrometer Timer/Observation.
5. Design metrics for backlog, consumer lag, retries, failures, and throughput.
6. Handle clock skew, missing timestamps, and replayed messages.
7. Distinguish attempt duration from logical task duration.
8. Connect message context with distributed traces via propagation.
9. Choose appropriate histogram buckets and SLOs for queue wait/processing.
10. Test and investigate queue backlogs or slow workers.

## 2. Three types of duration to measure

A message typically passes through these milestones:
- **Published:** producer starts or finishes sending the message.
- **Enqueued/accepted:** broker confirms the message was accepted into the system.
- **Received/started:** consumer receives the message and begins processing.
- **Completed:** handler finishes with success or failure.
- **Acknowledged:** consumer confirms to the broker that the message was processed per delivery semantics.

~~~mermaid
flowchart LR
    A["Publish"] --> B["Broker accepts"]
    B --> C["Queue wait"]
    C --> D["Consumer starts"]
    D --> E["Processing"]
    E --> F["Complete"]
    F --> G["Ack"]
~~~

From these milestones, define:

| Quantity | Conceptual formula | Meaning |
|---|---|---|
| Publish-to-accept | `accepted_at - publish_started_at` | Time to send / be accepted by broker |
| Queue wait | `processing_started_at - enqueued_at` | Time the message waited before a worker started |
| Processing duration | `processing_finished_at - processing_started_at` | Time a worker spent processing one attempt |
| Ack latency | `acknowledged_at - processing_finished_at` | Time from handler completion to broker ack |
| End-to-end age | `completed_at - published_at` | Age of the logical message from publish to result |
| Consumer lag | Unprocessed offset/position or timestamp difference per broker | How far behind the data stream the consumer is |

Not every broker exposes all enqueue, receive, and ack milestones. Determine whether timestamps come from the broker/client or must be carried in message metadata. Never mix different definitions under the same metric name.

## 3. Queue wait time

Queue wait time is the interval from when the broker accepts the message until the consumer begins processing it. It reflects backlog and consumption capacity.

Example:
- Producer publishes at 10:00:00.000.
- Broker accepts at 10:00:00.010.
- Consumer starts at 10:00:02.010.
- Handler finishes at 10:00:02.090.

Queue wait is ~2 seconds; processing duration is ~80 ms. The handler is fast, yet the system is still slow because messages must wait.

Queue wait can rise due to:
- Message arrival rate exceeding processing capacity.
- Insufficient consumer instances/threads.
- Consumers paused, rebalancing, or crashing.
- Prefetch/visibility timeout/partition assignment keeping messages from workers.
- A group of poison messages or constant retries consuming capacity.
- Slow downstream dependencies preventing consumers from picking up new messages.

Queue wait should be viewed alongside queue depth, oldest message age, consumer count, throughput, and retry rate.

## 4. Processing duration

Processing duration measures the time from when an attempt starts running the handler until the handler finishes or hits a terminal error/cancellation. It answers how long a worker takes to handle a message once received.

Example:

~~~text
message.type = inventory.reservation
consumer = inventory-worker
processing.duration = 80 ms
outcome = success
~~~

Processing duration can rise due to:
- CPU-heavy handler code or serialization.
- Slow database queries/transactions.
- Slow HTTP dependencies.
- Lock contention or thread starvation.
- Large payloads.
- Garbage collection or resource saturation.

Measure processing duration around the exact processing portion you want to observe. If a timer includes executor queue wait, it is no longer pure handler duration; name and define the metric accordingly.

## 5. End-to-end message age

End-to-end age measures from the publish time of the logical message until the business operation completes. It includes publish, queue wait, processing, retries/backoff, and intermediate steps if defined across multiple services.

~~~mermaid
flowchart TD
    A["Published"] --> B["Broker / queue wait"]
    B --> C["Attempt 1"]
    C --> D{"Success?"}
    D -->|No| E["Retry delay / redelivery"]
    E --> F["Attempt 2"]
    F --> G["Completed"]
    D -->|Yes| G
~~~

A message can have an 80 ms processing duration yet a 5-minute end-to-end age because it waited in a queue or retried multiple times. Measuring end-to-end age is valuable for user-facing workflows, asynchronous processing SLAs, and job deadlines.

Define clearly what completion means: handler return, database commit, publishing the next event, or completion of the business workflow. If a message initiates a multi-step workflow, a single consumer span does not represent the entire business process duration.

## 6. Defining accurate timestamps

Each timestamp should be tied to a specific event:

| Timestamp | Recorded by | Notes |
|---|---|---|
| `publishedAt` | Producer | Time the logical event was created or sent |
| `acceptedAt`/`enqueuedAt` | Broker or producer receiving broker confirmation | Broker is usually more reliable for queue residence |
| `receivedAt` | Consumer/client | May differ from when the handler starts |
| `processingStartedAt` | Consumer instrumentation | Start milestone for the handler timer |
| `processingFinishedAt` | Consumer instrumentation | Success/failure/cancel |
| `acknowledgedAt` | Client/broker protocol | Ack may occur after handler completion |

Do not reuse one field named `timestamp` for multiple meanings. If the broker provides an enqueue timestamp, prefer it for calculating queue residence. If only a producer timestamp exists, subtracting across producer and consumer clocks can be skewed by clock skew.

### 6.1 Clock skew

Suppose the producer clock is 700 ms ahead of the consumer. Computing `consumerStart - publishedAt` will be 700 ms shorter than reality—or even negative. Queue wait based on a broker enqueue timestamp can reduce error if managed by the broker, though consumers and brokers still need synchronized clocks.

Recommendations:
- Synchronize host clocks with NTP/chrony or your platform's time sync service.
- Prefer monotonic clocks for durations measured within the same process.
- Use wall-clock timestamps only when measuring across process boundaries.
- Record and monitor negative/implausible durations rather than silently clamping negatives to 0.
- Name metrics according to the timestamp source so incompatible metrics are never compared.

### 6.2 Replayed or migrated messages

When replaying messages from a dead-letter queue or backfilling, `publishedAt` can be very old. End-to-end age will reflect age since the original event rather than the replay's wait time. Additionally measure the enqueue/receive timestamp of the current delivery and distinguish replays with a bounded outcome/source dimension if needed.

Never record unique message IDs as metric tags. Use message IDs in controlled traces/logs to investigate individual records.

## 7. Acknowledgment, retries, and redelivery

Message processing may follow at-most-once, at-least-once, or broker-specific semantics. With at-least-once, a handler can receive the same message again if ack fails, the consumer crashes, or visibility timeout expires.

Distinguish:
- **Attempt:** a single handler execution.
- **Delivery:** a single broker delivery of a message to a consumer; delivery can happen before the handler starts.
- **Logical message/job:** the original business work item, which may span multiple deliveries/attempts.
- **Retry delay:** the wait interval before the next attempt.
- **End-to-end age:** total age of the logical job until terminal completion.

If one attempt fails in 100 ms, waits 30 seconds for retry delay, and the next attempt succeeds in 100 ms: total processing time across both attempts is 200 ms, whereas end-to-end age is at least 30 seconds plus queue waits. The two metrics cannot substitute for one another.

### 7.1 Ack latency

If the handler returns but the ack is slow or fails, the broker may redeliver the message. Measuring ack latency helps separate slow handlers from ack/network issues. Depending on the client API, acks may be sent automatically after the callback or explicitly by application code. Do not measure ack duration if the framework does not expose an accurate milestone; use available broker/client metrics.

### 7.2 Retries and poison messages

Continuous retries can cause the same logical message to occupy workers repeatedly. Useful metrics:
- Attempts per logical message (aggregated distribution, not tagged by ID).
- Retry count/rate by message type and outcome.
- Dead-letter count.
- Oldest message age.
- Processing duration per attempt.
- End-to-end age to success/dead-letter.

Bound retries, use backoff/jitter, classify transient vs. permanent errors, and enforce a dead-letter policy. Never retry validation/schema errors forever.

## 8. Micrometer metrics for messaging and tasks

A typical metric suite includes:

| Metric | Type | Definition |
|---|---|---|
| `messaging.consumer.queue.wait` | Timer/Histogram | Enqueued to processing start |
| `messaging.consumer.processing` | Timer/Histogram | Processing start to terminal handler outcome |
| `messaging.message.age` | Timer/Histogram | Published to business completion |
| `messaging.consumer.completed` | Counter | Completed attempts/logical jobs per definition |
| `messaging.consumer.errors` | Counter | Failed attempts |
| `messaging.consumer.retries` | Counter | Observed retries/redeliveries |
| `messaging.consumer.dead_lettered` | Counter | Messages moved to DLQ |
| `messaging.consumer.in_flight` | Gauge | Messages currently being processed |
| `messaging.queue.depth` | Gauge | Current backlog if exposed by broker |
| `messaging.queue.oldest_age` | Gauge | Age of oldest message if exposed by broker |

Exact metric names depend on the Micrometer binder, Spring Integration, Spring Kafka, Spring AMQP, or custom instrumentation. Before creating custom metrics, check existing integrations to avoid duplicate measurements.

### 8.1 Timers for queue wait and processing

Example custom instrumentation for tasks:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.time.Instant;

class TaskMetrics {

    private final MeterRegistry registry;

    TaskMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void recordQueueWait(Duration wait, String taskType) {
        Timer.builder("messaging.consumer.queue.wait")
                .tag("task.type", taskType)
                .publishPercentileHistogram()
                .register(registry)
                .record(wait);
    }

    void recordProcessing(Duration duration, String taskType) {
        Timer.builder("messaging.consumer.processing")
                .tag("task.type", taskType)
                .publishPercentileHistogram()
                .register(registry)
                .record(duration);
    }
}
~~~

This example records precomputed durations. In a real listener, capture timestamps at the right milestones and ensure each attempt is recorded exactly once across success/error/cancel paths.

### 8.2 Measuring processing with Timer.Sample

`Timer.Sample` measures duration using Micrometer's monotonic clock:

~~~java
Timer.Sample sample = Timer.start(registry);
try {
    process(message);
    sample.stop(successTimer);
} catch (RuntimeException ex) {
    sample.stop(errorTimer);
    throw ex;
}
~~~

`Timer.Sample` works well for durations within the same process. It does not measure cross-process queue wait; queue wait requires enqueue/receive timestamps or broker-provided residence metrics.

## 9. Observation for consumer processing

Micrometer Observation can wrap consumer operations to generate metrics and tracing spans via handlers.

~~~java
Observation.createNotStarted("messaging.process", observationRegistry)
        .lowCardinalityKeyValue("messaging.system", "kafka")
        .lowCardinalityKeyValue("messaging.operation", "process")
        .lowCardinalityKeyValue("messaging.destination.name", "orders")
        .observe(() -> handle(message));
~~~

This example illustrates a custom Observation. Built-in instrumentation from Spring Kafka/AMQP or other frameworks may already create an Observation; do not wrap the same operation in a duplicate observation unless it serves a distinct purpose.

Observation context should contain:
- Messaging system (`kafka`, `rabbitmq`, `jms`...).
- Normalized destination/queue/topic.
- Operation (`receive`/`process`/`settle` depending on semantics).
- Outcome (`success`/`error`/`rejected`).
- Bounded error type if needed.

Do not add message keys, payloads, customer IDs, or message IDs to low-cardinality tags.

### 9.1 Consumer Observation and span lifecycle

A consumer span may start when the message is received or when the handler begins, depending on instrumentation. If the goal is measuring queue wait, you need the broker enqueue milestone; consumer span duration normally covers only instrumentation start-to-stop and does not automatically represent total time spent in the queue.

Distributed tracing messaging conventions distinguish producer/consumer spans and links; a message consumed in a batch or from multiple producer contexts may require span links instead of a single parent. Follow the semantics of the integration in use.

## 10. Kafka, RabbitMQ, and other brokers

Not every broker defines queue wait the same way.

| System | Available signals | Notes |
|---|---|---|
| Kafka | Record timestamp, consumer lag/offset, poll/processing time | Lag is typically offset distance; not directly equivalent to time |
| RabbitMQ | Ready/unacked messages, queue stats, delivery/ack | Queue enqueue timestamp needs a reliable source |
| JMS | Provider/client delivery metadata, listener duration | Timestamp availability depends on provider |
| SQS-like queues | Sent/ApproximateFirstReceive/visibility/redrive metrics | Broker age metrics are often approximate |
| Spring `TaskExecutor` | Task submission/start/finish | Queue wait is executor queue time, not broker wait |

### 10.1 Kafka consumer lag is not queue wait time

Kafka lag is typically computed from the consumer group's committed/current offset relative to the log end offset. It measures unconsumed records, not how long a record has waited. Lag can grow when throughput is low, but knowing record age requires timestamps and understanding timestamp semantics.

Example:
- Lag of 10,000 records on a topic doing 20,000/s may be only half a second of data.
- Lag of 100 records on a topic doing 1/s may represent nearly 100 seconds.

Therefore monitor offset lag, records/sec, and record age/queue wait together when needed.

### 10.2 Prefetch and concurrency

RabbitMQ prefetch or Kafka poll batches can cause messages to be delivered by the broker before the handler actually starts. If queue wait is measured from enqueue to handler start, that interval includes both broker backlog and client-side buffering. This is often a helpful view of real latency, provided the metric definition is documented clearly.

## 11. Cardinality and histogram buckets

Metric tags must be bounded:
- `messaging.system`.
- Allowlisted `destination.name`.
- Normalized `consumer.group`.
- `operation`.
- `task.type` with a small set of values.
- `outcome`/`error.type`.

Avoid message IDs, high-count partitions/offsets, message keys, user IDs, payload fields, and exception messages. Partition can be a bounded dimension if partition count is small and operationally justified; never assume all broker metadata is safe as tags.

Histogram buckets should reflect latency targets:
- Queue wait: may need buckets from a few milliseconds up to tens of seconds or minutes.
- Processing: typically concentrated from milliseconds to a few seconds depending on workload.
- End-to-end age: may need longer buckets and a separate distribution.

Do not use identical buckets across all three metrics if their scales differ. Client-side percentiles are hard to aggregate across instances; histogram buckets are better suited for backend aggregation and SLOs.

## 12. SLOs and alerting

Example SLOs:
- 99% of messages begin processing within 2 seconds of broker enqueue.
- 99% of tasks finish handler execution within 500 ms.
- 95% of logical jobs complete within 30 seconds of publish.
- Never allow oldest message age to exceed 5 minutes in critical queues.

These are examples; choose targets based on business contracts and traffic patterns.

Alerts should combine signals:
- Queue wait p95/p99 exceeding budget.
- Oldest message age rising continuously.
- Queue depth/consumer lag rising while throughput fails to keep pace.
- Processing duration rising.
- Error/retry/dead-letter rates rising.
- In-flight counts approaching concurrency limits.
- End-to-end age breaching SLA.

Do not alert merely because queue depth is high if the queue is draining rapidly and age is low. Queue depth is an instantaneous gauge; age and throughput reveal whether the backlog impacts users.

## 13. Testing queue wait and processing measurements

Create tests with deterministic time milestones:
1. Publish a message.
2. Hold the message in the queue or delay listener start.
3. Start the handler.
4. Let the handler run for a controlled delay.
5. Complete/throw/cancel and ack.
6. Assert queue wait and processing duration are recorded accurately per definition.

### 13.1 Testing separation of the two durations

Simulated example:
- Enqueued at t=0.
- Handler starts at t=2s.
- Handler finishes at t=2.1s.

Expected:
- Queue wait ~2s.
- Processing duration ~100ms.
- End-to-end age ~2.1s if publish and enqueue are close together.

Avoid tight sleep thresholds in main tests when latches/barriers and suitable tolerances can be used. Duration tests should tolerate scheduler jitter.

### 13.2 Testing retries and redelivery

Also test:
- First attempt fails.
- Retry delay of 1s.
- Next attempt succeeds.
- Verify attempt processing timers record two observations.
- Logical end-to-end age includes the retry delay.
- Retry counter increments accurately per chosen semantics.
- No message ID is attached as a metric tag.

### 13.3 Testing clock skew and missing timestamps

Use simulated timestamps to test:
- Producer timestamp earlier/later than consumer.
- Missing timestamp.
- Broker enqueue timestamp absent.
- Replayed message with an old `publishedAt`.
- Negative or implausibly large durations.

Do not silently coerce every negative duration to 0; record invalid timestamps or drop samples under an explicit policy with its own metric.

## 14. Troubleshooting

| Symptom | Possible cause | Remediation |
|---|---|---|
| Low processing duration yet slow user workflow | Large queue wait/backlog | Measure queue wait, oldest age, and consumer lag |
| Low queue wait yet slow processing | Slow handler/dependency/CPU/DB | Inspect consumer span and dependency spans |
| High Kafka lag yet low record age | Very high topic throughput | Inspect offset lag alongside records/sec and timestamp age |
| High queue depth yet low age | Fast consumer drain or fresh traffic burst | Monitor age/throughput; avoid single-metric depth alerts |
| Negative duration | Clock skew or mismatched timestamp semantics | Sync clocks, use broker timestamps, and validate |
| Replay shows huge age | Using original publish timestamp | Also measure enqueue age for the replay attempt |
| High retry count yet low error rate | Final retry succeeded | Track attempts and logical outcomes separately |
| Rising ack timeouts/redeliveries | Ack failing or consumer crashing | Check ack mode, visibility timeout, and handler lifecycle |
| Consumer span excludes queue wait | Span starts when handler receives message | Use separate broker age/queue wait metrics |
| Metric series exploding | Dynamic message ID/key/partition used as tags | Remove dynamic IDs; use only bounded dimensions |
| Timer recorded twice | Both success and `finally`/`catch` stop timer | Ensure each terminal path records exactly once |
| Abnormal batch listener duration | One span/timer represents multiple messages | Define batch vs. per-message metrics clearly |

## 15. Playbook: backlog grows while workers remain fast

**Scenario:** Processing p95 remains 80 ms, yet message completion SLAs are breached.

1. Check queue depth/consumer lag and oldest message age.
2. Measure queue wait from broker enqueue to handler start.
3. Compare arrival rate with completion throughput.
4. Inspect consumer count, concurrency, partition assignment, and prefetch.
5. Check whether retry/dead-letter traffic is consuming capacity.
6. Check for worker pauses/rebalances, thread pools, and downstream connection pools.
7. If queue wait is high while processing is stable, scale consumers or tune partitions/concurrency within dependency capacity limits.
8. If retries/backoff consume time, classify transient vs. permanent failures and bound retries.
9. Monitor end-to-end age after changes to confirm SLA recovery.

Do not scale consumer concurrency blindly: more workers can overload downstream databases/APIs, driving up processing duration and creating a new backlog.

## 16. Self-check exercises

**Exercise 1 — Separating durations.** A message is enqueued at 10:00:00, the handler starts at 10:00:03 and finishes at 10:00:03.2. What are queue wait, processing duration, and end-to-end age (assuming publish coincides with enqueue)?

**Exercise 2 — Kafka lag.** Why can't a consumer lag of 5,000 records automatically be translated into a 5-second queue wait without knowing throughput/timestamps?

**Exercise 3 — Retries.** A logical message has two attempts, each taking 100 ms, with a 20-second retry delay. How do total processing duration and end-to-end age differ?

**Exercise 4 — Clock skew.** The producer clock is 1 second ahead of the consumer. What happens when computing `consumerStart - publishedAt`? Which timestamp should be used and how should clocks be synchronized?

**Exercise 5 — Acks.** The handler finishes quickly, yet messages redeliver continuously. Which milestones/metrics besides processing duration need inspection?

**Exercise 6 — Histograms.** Why do queue wait and processing duration need different histogram buckets?

**Exercise 7 — Cardinality.** Why shouldn't message ID and offset be default metric tags? Where should they be used to investigate a specific message?

**Exercise 8 — SLOs.** Workers process in 50 ms, yet queue wait p99 is 45 seconds. Which SLO is breached and which metrics should be checked to determine capacity?

### Answer hints

1. Queue wait is 3 seconds; processing is 200 ms; end-to-end is ~3.2 seconds.
2. Lag is a count of offset records; time depends on arrival/consume rates and record timestamps.
3. Processing attempts sum to 200 ms; end-to-end is at least ~20.2 seconds plus queue waits and overhead.
4. Duration can be negative or 1 second shorter than reality. Use broker enqueue timestamps when available, synchronize clocks, and validate timestamps.
5. Ack latency, ack failures, visibility timeout, consumer crashes/rebalances, and delivery counts.
6. Queue wait can span milliseconds to minutes; processing is typically milliseconds to seconds. Separate buckets keep percentiles/SLOs meaningful.
7. Every message/offset creates a new series. Use controlled traces/logs to locate a specific message.
8. Queue-start latency/end-to-end SLO is breached; inspect backlog, arrival/consume throughput, concurrency, partitions/prefetch, and oldest age.

## 17. Official references

- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle, handlers, conventions, and context.
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timers, histograms, percentiles, and duration recording.
- [Spring for Apache Kafka — Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): producer/consumer observations and tracing.
- [Spring AMQP — Micrometer Observation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable-micrometer.html): listener observation and metrics.
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring): consumer lag, throughput, and broker metrics.
- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring): queue depth, ready/unacked messages, and consumer metrics.
- [OpenTelemetry Semantic Conventions — Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/): producer/consumer spans, message attributes, and propagation.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context across process boundaries.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registry, timers, and custom metrics.

**Remember:** Queue wait measures time before a worker begins; processing duration measures how long one attempt runs; end-to-end age measures the age of the logical job from publish to result. Monitor all three alongside backlog, throughput, retries, acks, and consumer capacity. Use broker timestamps when available, synchronize clocks, keep metric tags bounded, and use traces/logs to investigate individual messages. Fast workers do not mean a responsive asynchronous system if queues are building up.
