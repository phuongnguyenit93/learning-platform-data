# Monitoring Kafka Consumer Lag, RabbitMQ Queue Depth, and DLQ

A Spring Cloud Stream application can start up normally while messages pile up on the broker. An HTTP health endpoint returning UP does not prove consumers are keeping up with data ingestion rates. Operating an event pipeline requires observing both the application and the broker's queue/partition state.

The three key signals in this lesson are Kafka consumer lag, RabbitMQ queue depth, and dead-letter queues (DLQs). Kafka lag shows how many records behind the log end a consumer group is. RabbitMQ queue depth shows how many messages are waiting or delivered without acknowledgment. DLQs show messages diverted from normal processing due to errors, expired TTLs, or dead-letter policies. These numbers must be read alongside publish/consume rates, message age, consumer count, processing errors, and broker resources.

Spring Cloud Stream provides bindings and binders for Kafka, RabbitMQ, and Pulsar; Micrometer/Actuator exports application metrics, while Prometheus and Grafana can collect and visualize broker metrics. This lesson focuses on how to define, collect, interpret, alert on, and act on these signals in production.

## Learning Objectives

After this lesson, you will be able to:

- Explain Kafka consumer lag by consumer group, topic, and partition.
- Distinguish committed offset, log end offset, and unconsumed record count.
- Use Kafka CLI and metrics to locate lagging partitions.
- Distinguish RabbitMQ messages_ready, messages_unacked, and total queue depth.
- Monitor consumer count, consumer capacity, and message rates.
- Monitor DLQs, message age, and dead-letter rates.
- Export Spring Cloud Stream metrics via Micrometer, Actuator, and Prometheus.
- Design dashboards and alerts based on backlog, processing rate, and SLAs.
- Avoid high cardinality and noisy alerts.
- Execute runbooks when Kafka lag or RabbitMQ queue/DLQ depth rises.

## 1. Observability of an event pipeline

~~~text
Producer -> Broker -> Consumer -> Business processing -> Output broker
                |          |
                |          +-- retry / error / DLQ
                +-- lag / queue depth / broker health
~~~

Each layer answers a different question:

| Layer | Question | Signals |
|---|---|---|
| Broker | Where are the messages sitting? | Kafka lag, RabbitMQ queue depth, DLQ depth |
| Consumer | Are consumers active and keeping up? | Consumer count, poll, ack, processing rate |
| Application | Are handlers failing or slow? | Error rate, processing duration, retry count |
| Infrastructure | Are the broker or apps starved of resources? | CPU, memory, disk, network, file descriptors |
| Business | Are events reaching their destination on time? | End-to-end age, success rate, event loss |

Do not rely on a single metric. High queue depth can be normal during peak hours if consumers are draining the backlog quickly. Conversely, small queue depth with messages sitting for hours can signal a stuck partition or routing key.

### 1.1. Metrics, logs, and traces

- **Metrics** are aggregated numbers over time, well suited for trend detection and alerting.
- **Logs** record specific events such as exceptions, rebalances, publish failures, or dead-lettering.
- **Traces** link processing steps of an event across multiple services and brokers.

Use metrics to detect anomalies, then use traces and logs carrying correlation IDs/event IDs to find root causes. Never put event IDs, order IDs, emails, or payloads into metric labels because each unique value can create a new time series.

## 2. What is Kafka consumer lag?

Kafka stores records within individual partitions. A consumer group reads those partitions and commits offsets to record the processed position. Consumer lag is the gap between the end of the log and the consumer group's committed offset.

For one partition:

~~~text
Log end offset (LEO)             = 1,250
Committed offset                 = 1,190
Consumer lag                     = 1,250 - 1,190 = 60 records
~~~

The committed offset usually represents the next position a consumer will read, so the formula above represents uncommitted offsets up to the end of the log under the common calculation. Exporter tools may have their own conventions; check the metric documentation before comparing across systems.

This is an offset distance, which does not always equal the exact number of records the application will receive. Compacted topics may have had offsets removed; transactional consumers using isolation level read_committed may only read up to the Last Stable Offset (LSO), which is lower than the Log End Offset while transactions remain open. When investigating discrepancies, verify whether the exporter compares committed offset against LEO or LSO and understand topic semantics.

### 2.1. Lag must be viewed per group and partition

Kafka lag is not a single number for the entire cluster. You need to know which consumer group is lagging, which topic has a backlog, which partition is largest, and which consumer is assigned that partition.

| Topic | Partition | Committed offset | Log end offset | Lag |
|---|---:|---:|---:|---:|
| orders | 0 | 10,000 | 10,020 | 20 |
| orders | 1 | 8,100 | 8,900 | 800 |
| orders | 2 | 9,500 | 9,510 | 10 |
| orders | 3 | 7,000 | 7,005 | 5 |
| **Total** | | | | **835** |

Total lag is 835 records, but partition 1 accounts for most of the backlog. Looking only at the total can hide key skew, a slow consumer, or errors affecting only one subset of messages.

### 2.2. Lag is a record count, not wait time

A lag of 10,000 records alone does not tell you how long users must wait. If consumers process 20,000 records/second, the backlog can clear quickly. If consumers only process 10 records/second, the same backlog can take many minutes.

\[
\text{Drain time} \approx
\frac{\text{Backlog}}{\text{Consume rate} - \text{Ingress rate}}
\]

This formula only makes sense when the consume rate exceeds the ingress rate. If the ingress rate is greater than or equal to the consume rate, the backlog cannot drop to 0 while load persists.

Therefore, monitor lag, ingress rate, consume rate, and record age together. For time-based SLAs, event age is often more operationally meaningful than offset count.

### 2.3. Common causes

- Producers increased message emission rate.
- Consumers have slow business processing or downstream service timeouts.
- Consumers encounter exceptions and prolonged retries.
- A partition has a hot key or oversized messages.
- Consumers repeatedly rebalance due to restarts or missed heartbeats.
- Too few partitions or consumers for the required parallelism.
- Consumers are blocked by database connection pools, thread pools, or downstream limits.
- Deserialization errors prevent a record from passing through the handler normally.

## 3. Measuring Kafka lag and inspecting consumer groups

### 3.1. Using Kafka command-line tools

The following command displays offsets and lag per partition:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group order-bridge
~~~

The output usually includes these columns:

| Column | Meaning |
|---|---|
| GROUP | Consumer group |
| TOPIC | Topic being consumed |
| PARTITION | Partition |
| CURRENT-OFFSET | Committed offset |
| LOG-END-OFFSET | End-of-log offset |
| LAG | Offset gap |
| CONSUMER-ID | Consumer receiving the partition |
| HOST | Consumer host |
| CLIENT-ID | Client ID |

To inspect group state and members, use `--state` and `--members` if supported by your Kafka CLI version:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group order-bridge \
  --state

kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group order-bridge \
  --members
~~~

The script name may be `kafka-consumer-groups.sh` on Linux or `kafka-consumer-groups.bat` on Windows. Use the script matching the installed Kafka client version.

### 3.2. Reading lag per partition

When one partition has disproportionately high lag:

1. Identify the consumer owning that partition.
2. Check that consumer's processing time and error rate.
3. Check key distribution and message sizes.
4. Check for rebalances or assignment changes.
5. Check whether downstream dependencies are slow.

If lag increases across all partitions simultaneously, producers may be outpacing the entire consumer group or a shared downstream may be failing. If only one partition grows, investigate key skew, poison records, and that specific consumer.

### 3.3. Offset lag vs. event age

Offset lag does not directly reflect message age. One partition may have 500 fresh records produced within one second, while another partition has 50 records stuck from an hour ago.

To measure event age:

- Include a business timestamp or creation timestamp in the event envelope.
- Record the timestamp when the consumer begins processing.
- Create a histogram for latency from occurredAt to processing time.
- If you need the age of unconsumed records, use a controlled exporter/inspector or dedicated metric; do not assume broker offsets automatically provide per-record age.

## 4. Kafka metrics in Spring Cloud Stream

The Kafka binder provides a Micrometer metric for consumer lag:

`spring.cloud.stream.binder.kafka.offset`

This metric reflects unconsumed messages by topic and consumer group; tags carry group, topic, and lag info. The binder creates `KafkaBinderMetrics` when Micrometer is on the classpath and the application does not provide a replacement bean.

Properties controlling offset lag computation include:

| Property | Effect |
|---|---|
| `spring.cloud.stream.kafka.binder.metrics.defaultOffsetLagMetricsEnabled` | When true, lag is calculated on metric access; when false, uses periodically computed values |
| `spring.cloud.stream.kafka.binder.metrics.offsetLagMetricsInterval` | Periodic lag calculation interval; current binder docs describe a 60-second default |

Example in properties format:

~~~properties
spring.cloud.stream.kafka.binder.metrics.defaultOffsetLagMetricsEnabled=true
spring.cloud.stream.kafka.binder.metrics.offsetLagMetricsInterval=60
~~~

Computing lag may require querying Kafka metadata and consumer group offsets. With many topics/partitions or many groups, evaluate collection cost and choose an appropriate interval.

### 4.1. Kafka client metrics

In addition to lag, monitor consumer client metrics:

- `records-consumed-rate` and `records-consumed-total`: rate and total of consumed records.
- `records-lag-max`: maximum per-partition lag in certain client metric groups.
- `fetch-latency-avg` and `fetch-rate`: fetch latency and rate.
- `commit-latency-avg` and `commit-rate`: commit latency and frequency.
- `time-between-poll-avg` and `last-poll-seconds-ago`: polling cadence.
- `assigned-partitions`: number of partitions assigned to the consumer.
- Rebalance and heartbeat metrics: indicators of unstable group membership.

JMX/Micrometer metric names may vary between Kafka client versions and exporters. Do not copy names from an older version without checking the actual registry.

### 4.2. Micrometer and Actuator

Add Spring Boot Actuator and the Prometheus registry matching your project's Spring Boot version. Maven dependency example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Endpoint configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      probes:
        enabled: true
~~~

After the application starts:

- `/actuator/health` provides health status.
- `/actuator/metrics` lists Micrometer metrics.
- `/actuator/metrics/spring.cloud.stream.binder.kafka.offset` lets you inspect the binder metric if exposed under that name in the registry.
- `/actuator/prometheus` exports metrics in Prometheus format when the registry is configured.

Do not expose all Actuator endpoints to the Internet. Restrict endpoints using network policies, authentication, and a separate management port when needed.

### 4.3. Binder observation and tracing

The Kafka binder has the property `spring.cloud.stream.kafka.binder.enableObservation` to enable Micrometer Observation for its bindings. Observation/tracing links producer and consumer activity; it does not replace consumer group lag metrics.

Verify support for your binder version and tracing bridge. Do not assume all headers or trace context propagate automatically across every broker and version.

## 5. What is RabbitMQ queue depth?

RabbitMQ displays messages in a queue across two primary states:

- **Ready**: messages waiting to be delivered to a consumer.
- **Unacknowledged (unacked)**: messages delivered to a consumer that the consumer has not yet acked.

Total queue depth:

\[
\text{messages} =
\text{messages\_ready} +
\text{messages\_unacknowledged}
\]

Example:

| State | Message count |
|---|---:|
| messages_ready | 1,200 |
| messages_unacknowledged | 300 |
| Total messages | 1,500 |

High ready counts usually indicate publish rate exceeds delivery/consumption rate. High unacked counts can indicate consumers have pulled many messages but are processing slowly, prefetch is too high, acks are delayed, or consumers are hung.

### 5.1. Do not look only at total queue depth

| Scenario | Interpretation to check |
|---|---|
| Ready rising, unacked low | Missing consumers, consumers not receiving messages, or low throughput |
| Ready low, unacked rising | Consumers holding messages while processing/acking slowly |
| Both ready and unacked rising | Inbound load exceeds processing capacity or downstream is bottlenecked |
| Ready steadily dropping, unacked stable | Consumers are draining the backlog |
| Low queue depth but high message age | Messages may be stuck in one queue/consumer or traffic is very sparse |
| Consumer count is 0, ready greater than 0 | Queue has no active workers |

RabbitMQ queue depth is a point-in-time snapshot at scrape time. To know whether a backlog is growing, inspect time series and publish/deliver/ack rates.

## 6. RabbitMQ metrics and Prometheus

RabbitMQ ships with a built-in Prometheus plugin:

~~~bash
rabbitmq-plugins enable rabbitmq_prometheus
~~~

The plugin typically exposes metrics on port 15692 at path `/metrics`. Check cluster listener and network configuration before adding it to Prometheus.

Example Prometheus scrape config:

~~~yaml
scrape_configs:
  - job_name: rabbitmq
    static_configs:
      - targets:
          - rabbitmq-1:15692
          - rabbitmq-2:15692
          - rabbitmq-3:15692
~~~

### 6.1. Key queue metrics

RabbitMQ 4.4 provides detailed per-queue metrics:

| Metric | Meaning |
|---|---|
| `rabbitmq_detailed_queue_messages_ready` | Messages ready for delivery |
| `rabbitmq_detailed_queue_messages_unacked` | Messages delivered but not yet acked |
| `rabbitmq_detailed_queue_messages` | Sum of ready and unacked |
| `rabbitmq_detailed_queue_consumers` | Number of consumers on the queue |
| `rabbitmq_detailed_queue_consumer_capacity` | Consumer capacity |
| `rabbitmq_detailed_queue_consumer_utilisation` | Equivalent metric name for consumer capacity |
| `rabbitmq_detailed_queue_messages_delivered_ack_total` | Total messages delivered in manual ack mode |
| `rabbitmq_detailed_queue_messages_acked_total` | Total messages acked by consumers |
| `rabbitmq_detailed_queue_messages_redelivered_total` | Total messages redelivered |

Metric names and families depend on the RabbitMQ version and Prometheus plugin configuration. Detailed per-queue metrics carry higher collection overhead than coarse metrics; enable only the families you need.

### 6.2. Consumer capacity

Consumer capacity represents the fraction of time a queue can immediately deliver a message when consumers are available. Low values can result from:

- No consumers attached.
- Consumers constrained by rate limits or prefetch.
- Consumers taking a long time to process messages.
- Queue frequently empty due to slow producers.

Low consumer capacity does not automatically mean consumers are broken. Inspect it alongside queue depth and publish/delivery rates. An empty queue naturally has low capacity because there are no messages to deliver.

### 6.3. RabbitMQ Management UI and HTTP API

The Management UI and HTTP API are useful for quick investigation. The endpoint:

~~~text
GET /api/queues/{vhost}/{queue}
~~~

can return fields such as `messages`, `messages_ready`, `messages_unacknowledged`, consumer count, and message stats. The Management API fits ad-hoc diagnostics, whereas Prometheus fits long-term time-series storage and alerting.

CLI to inspect queues:

~~~bash
rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers
~~~

Replace `/` with your environment's virtual host. Depending on the version, you can add `messages` or other supported queue fields.

## 7. Monitoring DLQs and dead-letter rate

A dead-letter queue holds messages diverted from normal processing queues due to:

- Consumer reject/nack with requeue=false.
- Message TTL expiration.
- Queue limit or overflow policy exceeded.
- Quorum queue delivery limit exceeded.

DLQs can be created per consumer group or per application topology. Name queues clearly so filtering and ownership are straightforward, e.g., `orders.fulfillment.dlq` or `orders.retry.30s`. Retry queues and quarantine queues serve different purposes; do not dump everything into one DLQ without an operational procedure.

### 7.1. DLQ indicators to monitor

- DLQ ready depth and unacked depth.
- Messages dead-lettered per minute.
- Messages redelivered/replayed.
- Age of the oldest message in the DLQ.
- Retry count or x-death count if present.
- Ratio of DLQ messages to total processed messages.
- Consumer count if the DLQ has an automated inspection consumer.

The RabbitMQ Prometheus plugin can export queue depth and delivery counters. Oldest message age usually requires an application metric or timestamp inspection procedure; do not assume standard queue depth metrics automatically expose per-message age.

### 7.2. DLQ vs. retry queue

A retry queue typically uses TTL/DLX to automatically route messages back to the main queue after a delay. A DLQ or quarantine holds messages for investigation and controlled replay. If a DLQ automatically dead-letters back to the main queue, it is acting as a retry tier.

| Queue | Expectation | Action when growing |
|---|---|---|
| Main queue | May have short-lived backlogs | Check throughput and consumers |
| Retry queue | Holds messages waiting on schedule | Check transient errors and TTL |
| DLQ/quarantine | Normally low or 0 | Investigate errors and plan replay |

### 7.3. Dead-letter rate

A DLQ with 10 messages is abnormal if the system processes only 100 messages/day, but minor if it processes millions/day. View absolute counts alongside ratios:

\[
\text{DLQ rate} =
\frac{\text{dead-lettered messages}}
{\text{messages processed}} \times 100\%
\]

If a dead-letter counter is not available in your queue/broker version, create an application counter when handling errors or placing messages into quarantine. Avoid counting the same message across multiple retry tiers as independent business failures.

## 8. Creating business metrics in Spring Cloud Stream

Broker metrics tell you about queues and offsets; application metrics tell you why consumers are falling behind.

| Application metric | Type | Purpose |
|---|---|---|
| `stream.messages.processed` | Counter | Successfully processed messages |
| `stream.messages.failed` | Counter | Failed messages |
| `stream.messages.retried` | Counter | Retry attempts |
| `stream.messages.dead_lettered` | Counter | Messages routed to DLQ |
| `stream.processing.duration` | Timer/Histogram | Duration to process one message |
| `stream.event.age` | Timer/Histogram | Event age when consumer starts processing |
| `stream.outbox.pending` | Gauge | Events awaiting relay if using an outbox |

Example using Micrometer:

~~~java
@Component
class OrderMetrics {

    private final Counter processed;
    private final Counter failed;
    private final Timer processingDuration;

    OrderMetrics(MeterRegistry registry) {
        this.processed = Counter.builder("stream.messages.processed")
                .description("Successfully processed stream messages")
                .tag("binding", "processOrder-in-0")
                .register(registry);

        this.failed = Counter.builder("stream.messages.failed")
                .description("Failed stream message processing")
                .tag("binding", "processOrder-in-0")
                .register(registry);

        this.processingDuration = Timer.builder("stream.processing.duration")
                .description("Time spent processing a stream message")
                .tag("binding", "processOrder-in-0")
                .publishPercentileHistogram()
                .register(registry);
    }

    void recordSuccess(Duration duration) {
        processed.increment();
        processingDuration.record(duration);
    }

    void recordFailure() {
        failed.increment();
    }
}
~~~

This example focuses on meter creation; integration into handlers should record once per final outcome rather than incrementing the success counter on internal retry successes. Binding names and tags should be stable values.

### 8.1. Metric cardinality

Never attach eventId, orderId, customerId, full exception messages, URLs with dynamic paths, timestamps, or payloads as metric tags. Such values create unbounded numbers of time series, increasing RAM and Prometheus costs.

Use tags with small bounded value sets such as application, environment, binding, destination, controlled consumer group, and outcome. When looking up a specific event, use logs or traces with eventId/correlationId instead of metric labels.

## 9. Dashboards for Kafka and RabbitMQ

### 9.1. Kafka consumer dashboard

Display:

- Total lag by consumer group.
- Lag by topic/partition.
- Maximum lag of any single partition.
- Ingress rate and consume rate.
- Event age or estimated drain time.
- Consumer group members and assigned partitions.
- Rebalances, commit latency, and poll intervals.
- Application processing duration and error rate.

Add group and topic as filters; show the application's critical groups by default. Do not plot only total lag, because a single hot partition can be masked.

### 9.2. RabbitMQ dashboard

Display:

- Ready, unacked, and total messages per queue.
- Consumer count and consumer capacity.
- Publish, deliver, ack, and redelivery rates.
- Queue depth of main, retry, and DLQ queues.
- DLQ oldest message age if a metric is available.
- Node memory, disk, file descriptors, and connections.

RabbitMQ recommends Prometheus and Grafana for long-term collection. The Management UI is helpful for quick investigation but does not replace a time-series storage system.

### 9.3. Pipeline overview

~~~text
Producer rate
    |
    v
Kafka topic -> Consumer group -> Processing success/error
    |                |
    v                v
Consumer lag     Retry / DLQ

Rabbit exchange -> Main queue -> Consumer
                       |            |
                       v            v
                  Queue depth    Ack rate
                       |
                       v
                 Retry / DLQ
~~~

The goal is to answer quickly: at which broker is data stalling, which consumer is falling behind, are errors rising, and which messages need investigation.

## 10. Sample PromQL and alerts

Kafka lag metric names depend on the exporter. Spring Cloud Stream Kafka binder provides `spring.cloud.stream.binder.kafka.offset`; a standalone Kafka exporter may use its own naming convention. Check the Prometheus endpoint before applying the rules below.

### 10.1. Kafka lag

Example if the exporter provides `kafka_consumergroup_lag`:

~~~promql
sum by (consumergroup, topic) (
  kafka_consumergroup_lag
)
~~~

Highest lag per partition:

~~~promql
max by (consumergroup, topic, partition) (
  kafka_consumergroup_lag
)
~~~

Alert when lag remains above a threshold:

~~~yaml
groups:
  - name: kafka-consumer
    rules:
      - alert: KafkaConsumerLagHigh
        expr: sum by (consumergroup, topic) (kafka_consumergroup_lag) > 10000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: Kafka consumer lag is high
          description: Check ingress rate, processing rate and partition assignment.
~~~

The metric name and labels `consumergroup`, `topic`, and `partition` in the example depend on the exporter. Replace them with the actual names in Prometheus. The threshold of 10,000 is only an example; set it according to throughput and SLAs.

### 10.2. RabbitMQ queue depth

Ready backlog per queue:

~~~promql
rabbitmq_detailed_queue_messages_ready
~~~

Sum of ready and unacked:

~~~promql
rabbitmq_detailed_queue_messages
~~~

Unacked per queue:

~~~promql
rabbitmq_detailed_queue_messages_unacked
~~~

Example alert when ready messages pile up:

~~~yaml
groups:
  - name: rabbitmq-queues
    rules:
      - alert: RabbitQueueBacklogHigh
        expr: rabbitmq_detailed_queue_messages_ready > 1000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: RabbitMQ queue backlog is growing
          description: Inspect consumer count, capacity, delivery rate and downstream latency.
~~~

### 10.3. Inactive consumers

When a queue has ready messages but no consumers:

~~~promql
rabbitmq_detailed_queue_consumers == 0
and
rabbitmq_detailed_queue_messages_ready > 0
~~~

### 10.4. Messages in DLQ

If DLQ queue names conventionally end with `.dlq`:

~~~promql
rabbitmq_detailed_queue_messages_ready{queue=~".*\\.dlq"} > 0
~~~

Check whether the exporter's queue label contains the full queue name. Some topologies name DLQs differently; use the actual label values.

### 10.5. Multi-signal alerting

Do not alert solely on a single backlog number. A useful alert may require backlog exceeding a threshold for a sustained duration, consume rate below ingress rate, or event age breaching SLA.

For DLQs, you can alert on new messages arriving within 5 minutes or when oldest age exceeds the handling deadline. For systems where a DLQ has expected routine traffic, base thresholds on business policy rather than treating every message as a critical incident.

## 11. Designing thresholds and SLOs

There is no single lag or queue depth threshold suitable for every system. Determine normal and peak throughput, target processing latency, maximum backlog drainable within recovery windows, how many consumers/partitions can scale, and downstream limits.

For example, a pipeline processing 2,000 messages/second can tolerate a 20,000-message backlog for 10 seconds. Yet if the SLA requires every order to be processed within 2 seconds, event age exceeding 2 seconds must alert even when total lag is low.

### 11.1. Symptom- and cause-based alerts

| Symptom | Cause signals to check |
|---|---|
| Kafka lag growing | Producer rate, consume rate, rebalances, processing duration |
| One partition has high lag | Key skew, consumer assignment, poison record |
| Rabbit ready growing | Consumer count, capacity, prefetch, downstream |
| Rabbit unacked growing | Processing duration, ack mode, stuck consumers |
| DLQ growing | Exception type, schema, retry exhaustion, TTL |
| End-to-end age growing | Broker backlog, network, downstream latency |

### 11.2. Avoiding noisy alerts

- Use `for` to ignore brief fluctuations.
- Split severity by SLA impact.
- Group alerts by application, group, topic, or queue.
- Include dashboard and runbook links in annotations.
- Avoid sending one alert per partition when an aggregated alert suffices.
- Use inhibit rules when a broker outage triggers a flood of queue alerts simultaneously.

## 12. Cardinality and collection costs

Kafka can have many topics, partitions, and consumer groups. RabbitMQ can have thousands of queues. If every metric carries full labels and is scraped too frequently, the monitoring system itself can become a major resource consumer.

Best practices:

- Keep only the labels needed for investigation and alerting.
- Use coarse queue metrics for overviews.
- Enable detailed queue metrics for critical queues or during diagnostics.
- Scrape at intervals aligned with SLAs; there is no need to scrape every metric every second.
- Limit retention and use recording rules.
- Use relabeling/filtering to drop temporary or out-of-scope queues.
- Never use metric labels for dynamic IDs.

The RabbitMQ Prometheus plugin groups metrics into families; detailed queue metrics carry higher cost than coarse metrics. Choose metric families intentionally and watch overhead as queue counts grow.

## 13. Runbook: Kafka consumer lag rising

When receiving a Kafka lag alert:

1. Identify the consumer group, topic, and lagging partitions.
2. Compare ingress rate with consume rate.
3. Check group members, assigned partitions, and rebalances.
4. Inspect processing duration, exceptions, and retry rates.
5. Check consumer polls, commit latency, and downstream dependencies.
6. Check partitions for hot keys or oversized records.
7. If short on capacity, increase consumer instances/concurrency within partition and downstream limits.
8. If a partition is stuck on a poison record, handle errors/DLQ per policy; do not reset offsets arbitrarily.
9. Watch lag decrease and event age return within SLA.
10. Document root cause and any required capacity adjustments.

Adding consumers does not always increase throughput. Within a single consumer group, active parallel consumers are capped by the partition count; excess consumers receive no partitions. If downstream is the bottleneck, adding consumers can worsen the incident.

## 14. Runbook: RabbitMQ queue depth or DLQ rising

When queue depth grows:

1. Identify the queue, vhost, and queue type.
2. Compare messages_ready, messages_unacked, and total messages.
3. Check consumer count and consumer capacity.
4. Compare publish, deliver, ack, and redelivery rates.
5. Check prefetch, processing duration, and downstream dependencies.
6. Check node memory, disk, file descriptors, and connections.
7. If consumer count is 0, check binding lifecycle, deployment, and connectivity.
8. If unacked is high, check for hung consumers, ack timeouts, or slow processing.
9. If DLQ grows, categorize exceptions, schemas, and retry counts.
10. Only replay the DLQ after the root cause is resolved and a deduplication plan is in place.

Never purge a queue or DLQ just to zero out a dashboard. Before purging, determine whether messages can be lost, whether copies must be archived for audit, and whether dropping data is permitted.

## 15. Testing observability

### 15.1. Kafka

- Stop consumers to generate lag.
- Raise producer rate above consume rate.
- Create a hot partition.
- Restart consumers to trigger a rebalance.
- Send schema-invalid records or records causing processing errors.
- Verify per-group/partition lag, event age, and alerts.

### 15.2. RabbitMQ

- Stop consumers while producers keep publishing.
- Increase prefetch to observe unacked counts.
- Slow down consumer processing.
- Reject a message to route it to the DLQ.
- Let a message expire TTL if the topology uses a retry queue.
- Verify ready/unacked/depth, consumer capacity, and DLQ metrics.

### 15.3. Alerts and runbooks

- Verify alerts fire only after the `for` duration.
- Verify labels and annotations reference the right queue/group.
- Verify dashboards open cleanly from alerts.
- Test recovery steps and confirm alerts resolve.
- Verify monitoring does not create unbounded time series under many distinct event IDs.

## 16. Common mistakes

1. **Looking only at total Kafka lag**: a single hot partition can be hidden. Drill down per partition.
2. **Treating lag as wait time**: lag measures offsets, not seconds. Measure event age and throughput.
3. **Ignoring ingress rate**: rising lag can stem from higher producer load. Compare ingress and consume rates.
4. **Adding consumers without checking partitions**: extra consumers get no partitions. Check partition count and assignments.
5. **Looking only at Rabbit total messages**: you cannot tell waiting messages from delivered ones. Separate ready and unacked.
6. **Assuming high unacked always means broken consumers**: large prefetch or slow processing also raises unacked. Check capacity, ack rate, and processing time.
7. **Not monitoring DLQs**: failed messages can linger unnoticed. Set alerts, owners, and retention.
8. **Assuming DLQ depth of 0 is enough**: messages may be stuck in retry queues or failing before reaching the DLQ. Monitor retries and error rates.
9. **Relying solely on the Management UI**: the UI does not replace time-series storage. Use Prometheus/Grafana in production.
10. **Scraping every detailed metric too frequently**: increases overhead and cardinality. Pick appropriate metric families and intervals.
11. **Putting eventId in metric tags**: creates unbounded time series. Use logs/traces to inspect specific events.
12. **Treating health UP as a healthy pipeline**: brokers may be reachable while consumers lag. Combine health, lag, depth, and event age.
13. **Setting alerts on one static threshold only**: ignores throughput and SLAs. Use trends, rates, and backlog age.
14. **Purging the DLQ to clear alerts**: risks losing data needed for investigation. Handle and replay in a controlled manner.

## 17. Monitoring rollout workflow

When deploying Spring Cloud Stream to production:

1. Identify critical consumer groups, topics, queues, retry queues, and DLQs.
2. Enable Kafka binder metrics and configure lag collection appropriately.
3. Enable the RabbitMQ Prometheus plugin and select required metric families.
4. Add Actuator, a Micrometer registry, and application metrics.
5. Configure Prometheus scrape endpoints with appropriate authentication/network policies.
6. Build overview dashboards and drill-down dashboards per group/partition/queue.
7. Define alerts around SLAs, backlog trends, consumer counts, and DLQs.
8. Add event age, processing duration, and error/retry counters.
9. Cap metric cardinality and scrape costs.
10. Write runbooks for Kafka lag, Rabbit queue depth, and DLQ growth.
11. Test by simulating backlogs, consumer outages, and dead-lettering.
12. Periodically review dashboards and alerts against real production load.

## Conclusion

Kafka consumer lag shows how many offsets behind the log end a consumer group sits; inspect it by group, topic, and partition while comparing ingress rate, consume rate, and event age. RabbitMQ queue depth must be split into messages_ready and messages_unacked; total depth alone cannot distinguish slow consumers from missing workers. DLQs are error signals that must be monitored separately alongside retry rates and message age.

The Spring Cloud Stream Kafka binder provides a Micrometer lag metric; RabbitMQ provides queue metrics via its Prometheus plugin; Spring Boot Actuator/Micrometer can export processing duration, errors, retries, and event age. Strong dashboards combine broker metrics, application metrics, and infrastructure signals. Alerts should tie to SLAs and backlog trends, and runbooks should guide checking partitions/consumers, ready/unacked counts, DLQs, and downstream causes. With these signals in place, operations teams can spot backlogs early, pinpoint where messages stall, and recover safely.

## References

- [Spring Cloud Stream — Kafka Binder Metrics](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/metrics.html)
- [Spring Cloud Stream — Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [RabbitMQ — Prometheus and Grafana](https://www.rabbitmq.com/docs/prometheus)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
