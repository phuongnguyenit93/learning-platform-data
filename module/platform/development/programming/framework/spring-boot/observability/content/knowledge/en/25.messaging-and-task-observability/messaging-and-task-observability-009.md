# Queue depth and lag in messaging and task observability

> **Chapter:** Messaging and task observability  
> **Lesson:** Queue depth and lag  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production.

## 1. Why monitor queue depth and lag?

In asynchronous processing systems, producers send messages or tasks into a queue for consumers to process later. Queues decouple arrival rate from processing rate, but if producers consistently outpace consumers, the backlog grows. Initial HTTP requests may still return `202 Accepted` while actual work is delayed by many minutes.

Two concepts to monitor:

- **Queue depth**: the number of messages/tasks currently waiting to be processed in a queue or subscription as defined by the broker.
- **Consumer lag**: the distance between the latest message position a consumer needs to process and the position the consumer has finished/read up to. In Kafka, lag is typically measured as the number of offsets between the log end offset and the consumer group's committed offset; in other queues, semantics may be unacknowledged or undelivered messages.

Queue depth and consumer lag are related, but they cannot be used interchangeably. Queue depth typically describes a queue's backlog; Kafka consumer lag describes a consumer group's progress relative to the log. Know whether a specific metric comes from the broker, client, or exporter before interpreting it.

~~~mermaid
flowchart LR
  P["Producer"] --> Q["Broker / queue"]
  Q -->|Backlog| D["Queue depth"]
  Q --> C["Consumer group"]
  C -->|Progress position| L["Consumer lag"]
  C --> W["Worker processing"]
  W --> A["Ack / commit offset"]
  A --> Q
~~~

If you only monitor message counts, operations teams can miss a consumer stuck on a specific partition. If you only monitor lag, queue systems without offset semantics may need queue depth, oldest message age, or unacked counts instead.

## 2. What is queue depth?

Queue depth is the number of messages/tasks existing in a state defined by the broker or queue system. Depending on the technology, depth may count:
- Messages ready for delivery (ready/available).
- Messages delivered but not yet acknowledged (unacked/in-flight).
- Total ready + unacked.
- Messages waiting for retry or delay.
- Messages in a specific subscription.

Consequently, a metric named `queue_depth` across two different brokers may not share the same semantics.

For example, a queue has:
~~~text
ready messages       = 800
unacked messages     = 120
delayed messages     = 50
total outstanding    = 970 (if the metric defines total across all three groups)
~~~

When reading a dashboard, check the metric definition. If queue depth only counts ready messages, 120 unacked messages may still be holding resources and impacting throughput.

Continuously rising queue depth usually signals that producers are sending faster than consumers process, consumers are failing, there are too few consumers, or a downstream dependency is slow. However, a queue with high depth alongside high consumer throughput and low message age may simply be a normal burst being drained.

## 3. What is consumer lag?

Consumer lag measures the progress gap between data recorded by the broker and the position processed/committed by the consumer group. The most common example is Kafka consumer lag.

For one partition:

~~~text
log end offset       = 12,500
committed offset     = 12,100
consumer lag         = 400 records
~~~

With multiple partitions, group lag is typically aggregated as a sum or displayed per partition. Verify which approach your exporter/broker metric uses.

Lag can grow when:
- Producers increase publish rate.
- Consumers process slowly.
- Consumer instances decrease or fail to rebalance successfully.
- One partition gets a hot key and experiences skewed load.
- Consumers repeatedly retry a record.
- Offset commits are slow or failing.
- Downstream databases/APIs slow down and lengthen handlers.

Lag is a count of uncommitted/unread records per metric semantics, not directly a wait duration. A lag of 10,000 records might clear in seconds at high throughput, or take hours if consumers have nearly stalled.

## 4. Distinguishing queue depth, consumer lag, and message age

These metrics answer different questions:

| Metric | Question | Common unit |
| --- | --- | --- |
| Queue depth | How many messages are waiting? | messages/tasks |
| Consumer lag | How many positions behind the producer/log is the consumer? | records/offsets |
| Oldest message age | How long has the oldest message been waiting? | seconds |
| Processing duration | How long does one message take to process? | milliseconds/seconds |
| Consumer throughput | How many messages per second does the consumer complete? | messages/second |
| Unacked/in-flight | How many messages are being processed but not yet acked? | messages |

Oldest message age is often especially helpful for understanding user impact. Large queue depth does not always mean messages are delayed for long; conversely, small queue depth can still hide a single message stuck for a very long time.

Examples:
- Depth=20,000, throughput=5,000/s, age=3s: large backlog, draining quickly.
- Depth=30, throughput=0/s, age=900s: small queue, yet the consumer may have stopped.
- Kafka lag=50,000 with low message age: producer just had a large burst and the consumer is catching up.

Do not apply a single depth threshold to every queue. Combine depth/lag with age, throughput, and processing SLAs.

## 5. Kafka: lag by consumer group and partition

Kafka stores records in partitions, and a consumer group maintains committed offset positions. Consumer lag is typically calculated as:

\[
lag_{partition} = log\_end\_offset - committed\_offset
\]

Total group lag can be the sum of lags across partitions:

\[
lag_{group} = \sum_{p \in partitions} lag_p
\]

This is the common model; exporters may use current offset, committed offset, or log end offset with different sampling methods. Some dashboards display per-partition lag to reveal skew.

Example:

| Partition | Log end | Committed | Lag |
| --- | ---: | ---: | ---: |
| 0 | 10.000 | 9.800 | 200 |
| 1 | 12.000 | 11.950 | 50 |
| 2 | 9.000 | 8.000 | 1.000 |
| **Total** | | | **1.250** |

Partition 2 accounts for most of the lag. Looking only at the total of 1,250 hides which partition is experiencing consumer load skew.

### 5.1. Consumer groups and offset commits

Kafka consumers can auto-commit or commit manually. An offset commit does not necessarily mean the business operation finished if the application commits at the wrong time.

With at-least-once processing, applications generally must finish processing successfully before committing to avoid losing messages; in exchange, duplicates can occur if a crash happens after processing but before committing. Idempotency and deduplication must be designed at the business layer.

Rising lag does not by itself prove consumers are not processing. Consumers might be processing while offset commits are slow. Compare:
- Records consumed.
- Records processed successfully.
- Commit rate/commit failures.
- Consumer lag.
- Processing duration.
- Rebalance events.

## 6. Queue metrics in other brokers

Not every messaging system has Kafka-style offset semantics.

| System | Common metrics of interest | Watch out for |
| --- | --- | --- |
| RabbitMQ | Ready, unacked, total messages, consumer count | Ready and unacked are distinct states |
| Kafka | Consumer lag by group/partition, records in/out | Lag is based on offsets/commits |
| Amazon SQS | Approximate number of messages visible, not visible, oldest message age | Some figures are approximate and have update latency |
| ActiveMQ/Artemis | Queue message count, delivering, consumer count | Verify semantics per broker/version |
| In-memory task queue | Pending, running, completed, failed | Must define lifecycle and durability yourself |

RabbitMQ example:
- Ready: messages available to be delivered to consumers.
- Unacked: delivered, not yet acknowledged by consumers.
- Total: typically displayed as a combined status depending on dashboard/broker.

SQS example:
- Visible: messages waiting to be received.
- Not visible: messages currently inside visibility timeout after receipt.
- Delayed: messages not yet ready for delivery.

Do not add these metrics together if the broker already exposes a total metric that includes them; avoid double-counting.

## 7. Growing backlog: producers faster than consumers

A queue is stable when long-term processing rate at least equals the incoming message rate. Let:
- \(\lambda\): arrival rate, messages/second.
- \(\mu\): total processing rate, messages/second.

If \(\lambda > \mu\), the backlog grows approximately by:

\[
\Delta backlog \approx (\lambda - \mu) \times \Delta t
\]

For example, if producers send 1,200 msg/s and the consumer group processes 900 msg/s, the backlog grows by roughly 300 msg/s. After 10 minutes:

\[
300 \times 600 = 180{,}000\ messages
\]

If \(\mu > \lambda\), the backlog can shrink; ideal drain time is approximately the backlog divided by excess throughput:

\[
drain\_time \approx \frac{backlog}{\mu-\lambda}
\]

For example, with a backlog of 60,000, arrival 500/s, and processing 1,000/s, ideal drain time is roughly 120 seconds. This is a steady-state estimate, excluding bursts, retries, partition imbalance, processing variance, and downstream limits.

## 8. Estimating drain time and SLA impact

Queue depth/lag is only a count. To predict when the system will catch up, you need throughput and arrival rate.

~~~text
Backlog                  = 120,000 messages
Producer arrival rate    = 400 messages/second
Consumer processing rate = 1,000 messages/second
Net drain rate           = 600 messages/second
Estimated drain time     = 200 seconds
~~~

If consumer throughput merely equals arrival rate, the backlog will not shrink. If throughput is lower, the backlog keeps growing.

To assess SLAs, measure oldest message age or enqueue-to-completion latency. A queue can drain quickly while still having violated deadlines on older messages; conversely, a fresh backlog can be large while age remains low.

Do not treat a drain-time estimate as a guarantee. Include a safety factor in forecasts and check downstream capacity before increasing consumer concurrency.

## 9. Consumer throughput and processing duration

Consumer throughput measures records completed per unit of time, not just records polled/received.

Distinguish:
- Received/polled: consumer fetched the message.
- Started: handler started.
- Succeeded: processing finished successfully.
- Failed: processing failed.
- Acked/committed: broker notified of progress per protocol.

If consumers poll quickly while handlers run slowly, a high received rate does not mean the backlog is clearing. Measure success completion rate and processing duration separately.

A single message can be retried multiple times. Define clearly whether throughput counts unique business completions or processing attempts; otherwise, a dashboard may make consumers look fast while attempts are merely looping.

## 10. Partition imbalance and hot partitions

Kafka distributes records across partitions. A consumer group processes partitions in parallel, though one partition is typically assigned to only one consumer in the group at a time under the standard model.

If keys are skewed, one partition can receive far more traffic than others. Total consumer capacity may appear to have headroom while the hot partition keeps accumulating lag.

~~~mermaid
flowchart TD
  P["Producer records"] --> A["Partition 0"]
  P --> B["Partition 1"]
  P --> C["Partition 2"]
  A --> X["Consumer A"]
  B --> Y["Consumer B"]
  C --> Z["Consumer C"]
  C --> L["Lag rises on partition 2"]
~~~

Signs:
- One partition has markedly higher lag.
- The consumer assigned that partition has high processing duration.
- One key accounts for a large share of volume.
- Overall group throughput looks healthy while oldest message age rises for one subset.

Adding consumer replicas will not necessarily resolve a hot partition if partition count does not increase or one key always maps to the same partition. Changing partitioning/key strategies requires reviewing ordering, stateful processing, and compatibility.

## 11. Retries, poison messages, and dead-letter queues

A failing message may be retried multiple times. Retries reduce effective throughput and can keep the backlog growing. A poison message that always fails can be processed repeatedly, blocking a partition/queue depending on semantics.

Observe:
- Retry attempts and retry delays.
- Failure categories.
- Processing duration.
- Dead-letter queue depth/age.
- Number of redeliveries.
- Message processing success/failure rate.

A DLQ is not a place where backlog vanishes. If DLQ depth grows, trigger alerts and a remediation workflow. Never delete failed messages just to lower dashboard depth.

Idempotency is vital for at-least-once delivery. Consumers can receive the same message again after a timeout/crash or redelivery; duplicate processing must be safe.

## 12. Spring Boot: instrumenting message processing

Spring Boot/Micrometer provides integrations for several messaging technologies. Observations can wrap producer sends and consumer processing depending on binder/framework/instrumentation. Do not assume every broker client automatically emits sufficient metrics or spans just because Actuator is present.

A manual observation for business processing can look like:

~~~java
public void process(OrderCreated event) {
    Observation.createNotStarted("orders.process", observationRegistry)
            .lowCardinalityKeyValue("event.type", "order-created")
            .observe(() -> orderHandler.handle(event));
}
~~~

In production, place the observation around the proper handler lifecycle, including error/retry semantics. If the listener framework already instruments the consumer operation, avoid creating a second span at the same boundary; a business observation can describe a distinct processing step.

Low-cardinality tags should be event type, destination group, outcome, or a bounded consumer name. Do not put message IDs, customer IDs, order IDs, or payloads into metric labels.

## 13. Propagating trace context through messages

A distributed trace can continue across an asynchronous boundary if the producer injects trace context into message headers and the consumer extracts it before processing.

~~~mermaid
sequenceDiagram
  participant API as order-service
  participant Broker
  participant Worker as fulfillment-worker
  API->>Broker: Publish OrderCreated + trace context
  Broker-->>Worker: Deliver message + headers
  Worker->>Worker: Extract context / start consumer span
  Worker->>Worker: Process order
  Worker-->>Broker: Ack / commit
~~~

With OpenTelemetry, propagation typically uses W3C Trace Context or a compatible format. Framework integrations can inject/extract automatically. If handling headers manually, use the propagator API; do not parse `traceparent` with ad-hoc string logic.

A message processed minutes later can still belong to the original trace, though trace retention/sampling and span lifecycle must be considered. For very long workflows, span links may be more appropriate than continuous parent-child relationships depending on messaging models and tracing conventions.

Trace sampling does not replace queue metrics. A message without a sampled trace must still be counted in queue depth, lag, and throughput metrics.

## 14. Queue depth and lag in metrics

Metrics should clearly reflect their semantics:

~~~text
messaging.queue.messages.ready
messaging.queue.messages.unacked
messaging.consumer.lag
messaging.consumer.records.processed
messaging.consumer.processing.duration
messaging.consumer.errors
messaging.consumer.retries
messaging.dlq.messages
messaging.oldest_message.age
~~~

These names are illustrative metric designs, not default names in every Spring Boot integration. Use existing broker/exporter metrics if already available and document units/semantics clearly.

Appropriate dimensions:
- Normalized destination/queue/topic.
- Consumer group.
- Partition if partition count is bounded and needed.
- Finite outcome/category.
- Application/service name.

Avoid labels:
- Message IDs, arbitrary keys.
- Order/customer/user IDs.
- Raw payloads or exception messages.
- Unbounded dynamic tenant values.

Partition labels multiply series by partition count, though usually bounded; weigh cost when topic/partition counts are very high.

## 15. Alerting on backlog, lag, and age

An alert based solely on queue depth can fire during normal bursts. Good alerts usually combine multiple signals and a sustained duration.

Example conditions to consider:
- Consumer lag rising continuously across multiple windows.
- Oldest message age exceeding SLA.
- Consumer success throughput below arrival rate.
- Pending/ready rising alongside processing errors/retries.
- Consumer group having zero active members.
- Rising DLQ depth or DLQ age.

Conceptual rules:

~~~text
Alert when:
  oldest_message_age_seconds > 300
  for 5 minutes

Or:
  consumer_lag increasing continuously
  AND processed_rate < arrival_rate
  for 10 minutes

Or:
  active_consumers == 0
  AND queue_depth > 0
~~~

This is illustrative logic; choose thresholds based on your SLA and broker. In Kafka, consumer lag can fluctuate with commit intervals; avoid alerts sensitive to brief oscillations. In queues with visibility timeouts, visible/unacked metrics may have update lag.

## 16. Dashboards for operating queues

A useful dashboard can be divided into four groups:

| Group | Panel | Purpose |
| --- | --- | --- |
| Backlog | Queue depth / lag by topic/group/partition | How much unprocessed work is waiting? |
| Freshness | Oldest message age / enqueue-to-completion | How long are messages waiting? |
| Capacity | Arrival rate, success throughput, active consumers | Are consumers keeping up with producers? |
| Reliability | Errors, retries, redeliveries, DLQ | Why isn't the backlog shrinking? |

When lag grows, the dashboard should let you drill down from the overall group to partition/queue, then to consumer instances and the dependencies handlers call. A consumer processing slowly due to database pool wait can increase lag even when the broker is healthy.

Do not show only total queue depth. A topic with 20 partitions can have one partition with massive lag and 19 nearly empty partitions.

## 17. Troubleshooting queue depth and lag

| Symptom | Possible cause | Investigation approach |
| --- | --- | --- |
| Depth/lag rising steadily | Arrival rate exceeds processing rate | Compare publish and completion throughput |
| Lag rising while queue depth is low | Different metric semantics or commit lag | Check offsets, group, and exporter |
| One partition has high lag | Hot key, partition imbalance, stuck consumer | Partition assignment, key distribution |
| High pending, zero throughput | Consumers down or not polling | Health, active members, logs |
| Low ready but high unacked | Consumers holding many in-flight messages | Handler duration, ack timeout |
| Age rising despite low depth | A stuck message or long retries | Oldest message, poison message, DLQ |
| Retries spiking | Failing dependency or poison payload | Error categories, retry policy, downstream |
| DLQ growing | Messages unprocessable after retries | DLQ age, failure reason, replay process |
| Consumer active yet lag stays flat | Polling/receiving without completing/committing | Processed vs. received vs. committed |
| Scaling consumers does not help | Partition limit, DB bottleneck, or hot key | Partition count, DB pool, per-partition lag |
| Queue depth drops abruptly | Purge, expiration, retention, or metric reset | Broker events and retention configuration |
| Metrics missing | Exporter/binder not collecting or label filter | Broker metrics and application registry |

### Investigation workflow

1. Identify whether the metric comes from the broker, consumer client, or custom instrumentation.
2. Check definitions of ready, unacked, lag, and committed offset.
3. Compare arrival rate with successful completion rate.
4. Inspect oldest message age and processing duration.
5. Drill down by topic/queue, group, and partition.
6. Check active consumers, rebalances, and commit failures.
7. Check retries, poison messages, and DLQ.
8. Inspect downstream dependencies such as database/HTTP clients.
9. Adjust concurrency/partitions/retries deliberately and re-measure.

## 18. Real-world scenario: Kafka consumer lag growing

**Scenario:** `order-service` publishes 2,000 events/s. The `fulfillment-worker` group processes 1,500 events/s. Lag increases steadily at ~500 records/s. p95 handler duration is also rising.

### Step 1 — scope the lag

The group dashboard shows high total lag. Drilling down reveals partition 7 accounts for 60% of total lag. The consumer assigned partition 7 is processing more slowly than the others.

### Step 2 — inspect throughput and processing time

Consumer received rate is high, but successful completion is low. Traces for several messages show handlers waiting on slow database operations. Hikari pending connections are rising on the worker.

### Step 3 — separate broker from downstream bottleneck

The broker is receiving and serving records normally. Consumer lag stems from handlers being constrained by the database connection pool; adding more consumers could push even more concurrency onto the DB without raising throughput.

### Step 4 — fix the bottleneck

Shorten transactions, reduce connection hold time, optimize queries, and control concurrency. If partition skew stems from key distribution, review the key strategy while preserving business ordering guarantees.

### Step 5 — forecast the drain

After optimization, completion rate reaches 2,600/s while arrival stays at 2,000/s. A backlog of 180,000 records has a net drain rate of 600/s, giving an ideal drain time of around 300 seconds.

### Step 6 — verify

Monitor group lag, per-partition lag, oldest message age, successful processing rate, handler p95, DB pool pending, and DLQ. Confirm the backlog drops steadily rather than shrinking temporarily due to purge or retention.

**Lesson:** queue lag is an end-to-end symptom. Resolving it requires connecting broker metrics with consumer processing spans and downstream metrics.

## 19. Lab exercises and self-check questions

### Exercise A — define semantics

Pick a broker you use. Document whether the queue depth metric includes ready, unacked, delayed, or total; which offset/ack consumer lag relies on; and where oldest message age is computed.

### Exercise B — simulate backlog

Create a producer emitting 1,200 tasks/s and a consumer processing 900 tasks/s. Predict backlog growth after 10 minutes. Then increase consumer throughput to 1,500/s and estimate drain time.

### Exercise C — Kafka partition lag

Create a multi-partition topic and a consumer group. Introduce key skew so one partition receives most records. Observe total lag and per-partition lag; explain why adding consumers may not resolve a hot partition.

### Exercise D — retries and DLQ

Create a poison message. Configure bounded retries, backoff, and a DLQ. Observe retry count, processing throughput, queue lag, and DLQ age. Verify messages are not silently lost.

### Exercise E — context propagation

Publish a message from a traced HTTP request. Have the consumer extract context and create a processing span. Verify traces/links, log correlation, and behavior when messages are processed late.

### Exercise F — dashboard/alerts

Build a dashboard with queue depth, consumer lag, oldest age, arrival/success throughput, active consumers, and DLQ. Create SLA-based alerts and test short bursts to avoid false positives.

### Self-check questions

1. How does queue depth differ from consumer lag?
2. Why does high queue depth not necessarily mean messages have been waiting long?
3. Which offsets is Kafka consumer lag typically computed from?
4. How do ready and unacked messages differ?
5. Why is oldest message age important for SLAs?
6. How do arrival rate and processing rate determine backlog?
7. How do you estimate drain time when throughput exceeds arrival rate?
8. Why must per-partition lag be monitored?
9. How does a hot key affect consumer parallelism?
10. How does received rate differ from successful completion rate?
11. How do retries and poison messages increase lag?
12. How should rising DLQ depth be handled?
13. How is trace context propagated via message headers?
14. Why does trace sampling not replace queue metrics?
15. When scaling consumers is ineffective, what should be checked across broker, partitions, and downstream dependencies?

**Completion criteria:** accurately explain queue depth/lag/age; understand per-broker semantics; calculate backlog/drain; interpret per-partition lag and consumer throughput; detect retries/DLQ/hot partitions; instrument processing observations; propagate trace context; build SLA-aligned dashboards and alerts.

## 20. Takeaways

- Queue depth counts messages by broker state; consumer lag measures consumer progress against a log/queue according to specific semantics.
- Kafka lag is typically based on log end offset and committed offset, and may need per-partition drill-down.
- Oldest message age and processing latency show time impact that raw depth/lag alone cannot convey.
- Compare arrival rate with successful completion rate to know whether the backlog is growing or shrinking.
- Large queue depth can be a normal burst if throughput is high and age is low; a small queue can still hide a stuck message.
- Ready, unacked, delayed, received, processed, and committed are distinct states; do not sum or compare them if semantics do not match.
- Partition imbalance/hot keys can cause one partition to lag even when total consumer capacity has headroom.
- Retries, poison messages, and DLQs reduce effective throughput; monitor attempts, failures, and DLQ age.
- Spring Boot/Micrometer Observation can measure producer/consumer processing where supported by integration; avoid duplicate spans.
- Use low-cardinality labels; do not put message IDs, arbitrary keys, or payloads into metric tags.
- Propagate trace context via message headers to link requests and workers; trace sampling does not replace broker metrics.
- Alert on lag trends, oldest age, throughput, and active consumers tied to SLAs rather than a single generic depth threshold.

## References

- [Spring Boot Reference — Messaging](https://docs.spring.io/spring-boot/reference/messaging.html)
- [Spring for Apache Kafka — Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Apache Kafka Documentation — Consumer Design](https://kafka.apache.org/documentation/#design_consumerposition)
- [RabbitMQ Documentation — Queues](https://www.rabbitmq.com/docs/queues)
- [Amazon SQS — CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry Semantic Conventions — Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/)
