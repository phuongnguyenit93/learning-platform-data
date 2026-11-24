# Measuring consumer lag

Consumer lag shows how far behind a consumer group is when reading the data currently available in Kafka. It is an important signal for detecting backlogs, slow processing, stopped consumers, unassigned partitions, or an overloaded downstream system.

When operating Spring Kafka, you need to monitor lag per topic-partition and per consumer group, then correlate it with consume rate, listener processing time, commits, rebalances, and downstream capacity. A single lag number alone is not enough to conclude whether the system is healthy or experiencing an incident.

## 1. What is consumer lag?

Kafka stores records in each partition and assigns monotonically increasing offsets to record positions. A consumer group commits an offset to record the next position the group needs to read. Consumer lag is typically calculated as the difference between the log end offset and the committed offset:

```text
consumer lag = log end offset - committed offset
```

Example:

```text
Topic: orders
Partition: 0

Committed offset = 1240
Log end offset  = 1300

Lag = 1300 - 1240 = 60
```

The committed offset is the next position to read, not the offset of the last processed record. Therefore, the subtraction above does not add or subtract one.

Lag is usually displayed per partition. Group-wide lag can be the sum of partition lags, while dashboards should also display the maximum partition lag to spot a hot partition or a slow consumer member.

## 2. Distinguishing types of offsets

To interpret lag accurately, you must distinguish the offsets commonly seen in Kafka:

| Concept | Meaning |
|---|---|
| Current position | The next position the consumer will fetch in a partition |
| Committed offset | The position durably saved by the consumer group |
| Log end offset (LEO) | The end of the log according to the leader's log state; the next offset after the last appended record |
| High watermark (HW) | The boundary of records sufficiently replicated under Kafka rules that can be read by consumers in the appropriate mode |
| Last stable offset (LSO) | The stable boundary for consumers using `read_committed`, not advancing past unfinished transactions |

There are two common ways to view lag:

- **Group committed lag:** log end/visible end offset minus committed offset. This is the perspective of consumer group administration tools.
- **Consumer fetch lag:** end offset minus the consumer's current position. This reflects current fetch progress and commonly appears in the `records-lag` metric.

The two values can differ. A consumer may have fetched records and advanced its current position without committing offsets yet; in that case fetch lag drops while committed lag remains high. If the consumer dies before committing, the records may be read again.

For consumers using `isolation.level=read_committed`, records belonging to uncommitted transactions are not returned to the application. When analyzing lag on transactional topics, understand which end offset your tool uses and the LSO boundary visible to the consumer.

## 3. Offset lag is not an exact record count

An offset difference measures positional distance in the log, not always the exact number of business records waiting to be processed.

Offsets can have gaps because:

- Records were deleted by retention.
- The topic uses log compaction and older records with the same key were removed.
- Transaction control records occupy positions in the log.
- Some offsets are not visible to the consumer depending on isolation level.

Therefore, a lag of 100 does not necessarily mean there are exactly 100 unprocessed business messages. It is an offset-based backlog indicator. Combine it with `records-consumed-rate`, `records-produced-rate`, and processing time to evaluate impact.

Lag also does not directly express delay in seconds. To measure time-based delay, you need a time lag metric based on record timestamps or processing timestamps, with clear rules for event time, clock skew, and late events.

## 4. Consumer groups and partitions determine how lag is read

Each consumer group has its own committed offsets per topic-partition. Two groups reading the same topic can have very different lag.

Example:

```text
Topic orders: 3 partitions

Group orders-projection:
  orders-0 lag = 10
  orders-1 lag = 20
  orders-2 lag = 15
  total lag   = 45

Group orders-analytics:
  orders-0 lag = 300
  orders-1 lag = 450
  orders-2 lag = 280
  total lag   = 1030
```

The `projection` group may be keeping up while the `analytics` group falls behind. Therefore, do not measure lag only at the topic level or only for a single consumer group.

When a consumer group is rebalancing, assignments may change. A temporarily unassigned partition or an uninitialized committed offset can make lag reports incomplete. Dashboards should show group state, member count, assigned partition count, and when the metric was updated.

## 5. Checking lag with kafka-consumer-groups.sh

The Kafka CLI is a quick way to inspect committed lag by group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service
```

If the cluster requires SASL/TLS, pass a client configuration file:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9093 \
  --command-config admin-client.properties \
  --describe \
  --group orders-service
```

The output typically includes these columns:

| Column | Meaning |
|---|---|
| `TOPIC` | Topic consumed by the group |
| `PARTITION` | Partition |
| `CURRENT-OFFSET` | Committed offset |
| `LOG-END-OFFSET` | End offset observed by the tool |
| `LAG` | Offset difference |
| `CONSUMER-ID` | Consumer member owning the partition |
| `HOST` | Consumer host |
| `CLIENT-ID` | Client ID |

Example output:

```text
TOPIC  PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
orders 0          1240            1300            60
orders 1          900             950             50
orders 2          700             710             10
```

The total lag in the example is 120. Partition 0 has the highest lag, so you should inspect the consumer owning that partition, processing speed, and key distribution.

Other useful commands:

```bash
# View consumer members and partition assignments
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose

# View consumer group state
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --group orders-service \
  --state
```

Specific options may vary by Kafka version. Use `--help` for the exact CLI version deployed.

## 6. Measuring committed lag with AdminClient

You can use Kafka `AdminClient` to retrieve a consumer group's committed offsets and the corresponding partition end offsets. This approach fits when building an observation job or internal API.

Example:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.ListOffsetsResult;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

class ConsumerLagInspector {

    Map<TopicPartition, Long> calculateLag(
            String bootstrapServers,
            String groupId) throws Exception {

        Properties properties = new Properties();
        properties.put(
                "bootstrap.servers",
                bootstrapServers
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            Map<TopicPartition, OffsetAndMetadata> committed =
                    admin.listConsumerGroupOffsets(groupId)
                            .partitionsToOffsetAndMetadata()
                            .get();

            Map<TopicPartition, OffsetSpec> requests =
                    new HashMap<>();

            committed.keySet().forEach(topicPartition ->
                    requests.put(topicPartition, OffsetSpec.latest())
            );

            Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo>
                    endOffsets = admin.listOffsets(requests).all().get();

            Map<TopicPartition, Long> lagByPartition =
                    new HashMap<>();

            committed.forEach((topicPartition, offsetMetadata) -> {
                long committedOffset = offsetMetadata.offset();
                long endOffset = endOffsets.get(topicPartition).offset();

                lagByPartition.put(
                        topicPartition,
                        endOffset - committedOffset
                );
            });

            return lagByPartition;
        }
    }
}
```

This is a minimal example for partitions that already have committed offsets. In production, also add:

- `AdminClient` SASL/TLS configuration matching the cluster security policy.
- Timeouts for `KafkaFuture` calls and error handling when brokers/partitions are unavailable.
- Detection of negative lag or committed offsets beyond end offsets after truncation/retention; do not silently clamp to 0.
- Detection of partitions that are assigned but have no committed offset yet.
- Attaching group ID, topic, partition, and measurement timestamp to metrics.
- Proper `AdminClient` lifecycle management; do not create a new client on every HTTP request.

The `AdminClient` principal requires permissions to read the group's committed offsets and query topic metadata/offsets according to cluster ACLs.

## 7. Partitions without a committed offset

If a consumer group has never committed an offset for a partition, that partition may not appear in `listConsumerGroupOffsets` results. A missing partition must not be interpreted as lag equal to 0.

You must determine the set of partitions the group actually subscribes to or is assigned, then compare against committed offsets:

- Assigned with no committed offset: initial state or offsets not yet committed.
- No assignment: the group may be empty, rebalancing, or the subscription does not include that topic.
- Committed offset present without a valid end offset: check whether the topic/partition was deleted or metadata is out of sync.

The initial offset also depends on `auto.offset.reset` when the group has no valid offset. `earliest` starts from the earliest retained offset; `latest` starts from the end offset at reset time. This choice directly affects the initial backlog.

## 8. Monitoring Kafka consumer metrics

The Kafka consumer exposes metrics via `KafkaConsumer.metrics()` and JMX. Useful metrics include:

| Metric | Operational meaning |
|---|---|
| `records-lag` | Per-partition lag at the consumer's current position |
| `records-lag-max` | Maximum lag across the partitions the consumer is tracking |
| `records-consumed-rate` | Rate of records consumed |
| `records-consumed-total` | Total number of records consumed |
| `fetch-rate` | Fetch frequency |
| `fetch-latency-avg` | Average fetch latency |
| `commit-rate` | Offset commit frequency |
| `commit-latency-avg` | Average commit latency |
| `poll-idle-ratio-avg` | Ratio of time the consumer is idle between polls |
| `assigned-partitions` | Number of assigned partitions, if exposed by the client/version |

Metric names and tags can vary by Kafka client version and how the exporter maps JMX. Do not assume every metric includes group ID; verify `client.id`, `topic`, `partition`, and actual tags in your observability system.

`records-lag-max` is very useful for spotting a hot partition. However, it does not replace committed group lag because it usually reflects the consumer's current position rather than committed offsets.

## 9. Exposing metrics in Spring Boot with Micrometer

Spring Kafka and the Kafka client can integrate with Micrometer to export metrics to Prometheus or other observability backends. Exact configuration depends on your Spring Boot and Spring Kafka versions.

With Spring Kafka supporting `MicrometerConsumerListener`, you can register the listener on `ConsumerFactory` to attach metrics to created consumers:

```java
import java.util.Map;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.MicrometerConsumerListener;

@Configuration
class KafkaConsumerMetricsConfiguration {

@Bean
DefaultKafkaConsumerFactory<String, OrderEvent> ordersConsumerFactory(
        MeterRegistry meterRegistry) {

    DefaultKafkaConsumerFactory<String, OrderEvent> factory =
            new DefaultKafkaConsumerFactory<>(consumerProperties());

    factory.addListener(
            new MicrometerConsumerListener<>(
                    meterRegistry,
                    Map.of("service", "orders-service")
            )
    );

    return factory;
}
}
```

`consumerProperties()` is an application method returning the consumer configuration map including bootstrap servers, deserializers, group ID, and required properties. The example registers the listener directly on the existing factory; do not create a duplicate factory or a self-referencing bean just to add metrics.

Another option is using Micrometer `KafkaClientMetrics` to bind Kafka client metrics directly. Manage the binder lifecycle alongside created and closed producers/consumers; avoid re-binding on every newly created consumer without deregistering old ones.

The Spring Kafka listener container can also emit timers for record/batch listener processing duration. This timer complements Kafka client metrics: client metrics show fetch/lag/commit, while the listener timer shows business processing time. Do not confuse the listener processing timer with group committed lag.

## 10. Exposing metrics via Spring Boot Actuator

Add the Prometheus registry compatible with your Spring Boot version, then expose the required endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
```

Commonly used endpoints:

- `/actuator/health`: application health status and configured health indicators.
- `/actuator/metrics`: inspect metrics registered in Micrometer.
- `/actuator/prometheus`: scrape Prometheus-formatted metrics if the registry is included.

Do not expose sensitive Actuator endpoints to the public Internet. Protect endpoints with network policies, authentication, and authorization; open only the endpoints needed by the monitoring system.

Metrics from the Kafka client are named according to the binder and version and may use underscores when exported to Prometheus. Query `/actuator/metrics` or `/actuator/prometheus` to confirm exact metric names before writing dashboards and alert rules.

## 11. Monitoring lag with Prometheus and dashboards

A dashboard should show at least four perspectives:

1. Total lag per consumer group.
2. Maximum lag per topic-partition.
3. Lag over time.
4. Produce/consume rates and listener processing latency.

Example custom metric emitted by a committed-lag calculation job:

```text
kafka_consumer_group_lag{
  group="orders-service",
  topic="orders",
  partition="0"
} 60
```

This is a custom metric defined by the application/exporter, not a standard Kafka metric name. If using an exporter with a different schema, normalize labels before building dashboards.

You can calculate total lag:

```promql
sum by (group, topic) (kafka_consumer_group_lag)
```

Find the maximum partition lag:

```promql
max by (group, topic) (kafka_consumer_group_lag)
```

Track the rate of lag growth:

```promql
deriv(kafka_consumer_group_lag[5m])
```

`deriv` gives the approximate rate of increase/decrease over the time window. Do not use it alone as a paging condition; combine it with total lag, consume rate, and duration of the condition.

## 12. Designing alerts by backlog and duration

No single lag threshold fits every topic. Thresholds depend on throughput, SLA, message size, processing time, and consumer scalability.

An alert policy can include:

| Condition | Meaning | Response |
|---|---|---|
| Lag increases continuously for several minutes | Consumer is not keeping up with producer | Check consume rate, processing latency, and downstream |
| Lag exceeds a high threshold long enough | Backlog may impact SLA | Operational warning or paging depending on severity |
| One partition has abnormally high lag | Hot key, skew, or one slow consumer | Check key distribution and partition assignment |
| Lag is high and consume rate is 0 | Consumer stopped, lost assignment, or is stuck | Check container state, exceptions, and broker connectivity |
| Lag grows while commit rate is 0 | Consumer fetches/processes without committing or metrics are out of sync | Check `AckMode`, transactions, and commits |
| Group has no committed offset | New group or offsets not yet created | Check deployment status and `auto.offset.reset` |

You can estimate backlog drain time:

```text
estimated drain time
  = current lag / (consume rate - produce rate)
```

This formula is meaningful only when consume rate exceeds produce rate and both rates remain stable over the measurement window. If consume rate is less than or equal to produce rate, the backlog will not shrink on its own. This estimate is not an exact SLA because record sizes, downstream processing, and partition skew can vary.

## 13. Reading lag patterns to find root causes

Common patterns:

| Pattern | Possible cause | Investigation direction |
|---|---|---|
| All partitions increase lag together | Low consumer capacity or slow downstream | Scale processing capacity, optimize listener/DB, check produce rate |
| Only one partition increases sharply | Hot key or skewed key distribution | Check keys, partitioner, and per-key processing time |
| Lag rises in bursts then falls | Traffic burst or batch processing | Compare peak throughput and drain time |
| High lag, low fetch rate | Consumer cannot fetch or is paused | Check assignment, polling, broker network, and pause state |
| High lag, high fetch rate, low consume rate | Data is fetched but processing is slow | Check listener, DB, HTTP calls, and thread contention |
| Low lag but high listener latency | Low traffic or lag has not accumulated yet | Track latency/SLA separately, not only lag |
| Lag changes abruptly after rebalance | Assignment/offset ownership changed | Check rebalance events, group members, and commits |
| Lag drops abruptly after offset reset | Offsets were altered | Check audit logs and reset commands; low lag does not mean events were processed |

Do not immediately increase concurrency as soon as you see lag. If there are few partitions, raising concurrency may not create useful consumers. If the database is already saturated, adding consumer threads can slow the system down further.

## 14. Rebalances and consumer lag

When members join/leave a group, the consumer group may rebalance and redistribute partitions. During a rebalance, processing pauses on some partitions; lag can increase or assignment metrics can temporarily disappear.

Common causes:

- Instance restart or crash.
- Rolling deployment causing consumers to leave the group.
- Consumer fails to call `poll()` in time and exceeds `max.poll.interval.ms`.
- Network interruption or broker unavailability.
- Subscription or partition count changes.
- Consumer takes too long to process a batch before the next poll.

Monitor rebalance rate, assigned partitions, poll interval, heartbeat, and commit latency alongside lag. If rebalances happen continuously, merely adding more consumers can make the situation worse.

With Spring Kafka, inspect listener container state, concurrency, exception handlers, and listener processing time. Ensure the listener does not block long enough to exceed poll limits; for long-running work, design batching, pause/resume, or worker queues with accurate offset semantics.

## 15. Relating lag to commit configuration in Spring Kafka

Lag relies on committed offsets, so `AckMode` and commit strategy directly affect the numbers.

Common acknowledgement modes:

| AckMode | General behavior |
|---|---|
| `RECORD` | Commit after each record is processed by the listener |
| `BATCH` | Commit after all records in the poll batch are processed |
| `MANUAL` | Listener calls acknowledge; container commits according to mode semantics |
| `MANUAL_IMMEDIATE` | Commit immediately when acknowledge is called on the consumer thread under appropriate configuration |

If the application processes records successfully without committing yet, committed lag can remain high. This is not necessarily an unprocessed backlog; it may simply be the gap between the processing position and the committed position.

Conversely, committing before business side effects complete can make lag drop even when work has failed. Therefore, commits must align with processing, retry, and transaction semantics. Do not optimize dashboards by committing early just to make lag look good.

## 16. Measuring time lag and end-to-end latency

Offset lag answers "how many positions behind the end offset is the consumer?". Time lag answers "how late is the newest event being processed?". The two metrics complement each other.

You can measure end-to-end latency using the event timestamp set by the producer and the timestamp when the listener finishes:

```java
import java.util.concurrent.TimeUnit;

long eventTime = event.createdAt().toEpochMilli();
long processedAt = clock.millis();

long processingDelayMs = processedAt - eventTime;

meterRegistry.timer(
        "orders.event.processing.delay",
        "eventType",
        event.eventType()
).record(processingDelayMs, TimeUnit.MILLISECONDS);
```

Clarify whether `createdAt` is event time or processing time. Clocks between producer and consumer can drift; if accurate measurement is needed, use clock synchronization and consistent timestamp conventions.

Another metric is the elapsed time from the newest record in a partition until the consumer processes that record. This requires reading the record's timestamp and the latest processing state per partition; avoid using a timestamp from one partition to represent the entire topic.

## 17. Testing lag measurement

Integration tests should verify the calculation and edge cases, not just that a consumer receives messages.

Cases to cover:

1. Send 10 records without consuming/committing: group lag increases by offset.
2. Consume and commit all records: committed lag drops to 0.
3. Consume without committing: fetch lag may drop while committed lag remains high.
4. Create two consumer groups: verify each group has independent lag.
5. Create multiple partitions: verify lag is computed per partition.
6. Group with no committed offsets: metric must report an unknown/uninitialized state rather than 0.
7. Rebalance: assignment and lag metrics update after the group stabilizes.
8. Offset reset or retention: detect abnormal changes and avoid reporting negative numbers as valid backlog.
9. For transactional topics, test `read_committed` consumers and readable record boundaries.

When using Testcontainers or Embedded Kafka, create topics with fixed partition counts, use a unique consumer group ID per test, and wait for commits to finish before asserting. Do not use long fixed sleeps; prefer polling assertions with a deadline for stable tests.

## 18. Common pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Lag always 0 even when consumer is stopped | Group has no committed offsets or dashboard skips uncommitted partitions | Monitor group state and uninitialized offsets separately |
| CLI and `records-lag-max` differ | One uses committed offset, the other uses consumer position | Document metric definitions and do not compare them directly |
| Negative lag | Offset state changed due to truncation, reset, or unsynchronized observations | Alert on abnormal offset states and check metadata |
| Lag increases despite fast listener processing | Slow batch commits or commits not occurring | Check `AckMode`, commit interval, and transactions |
| Total lag is low yet SLA is missed | Few records but slow processing or delayed event timestamps | Track time lag and listener latency |
| Lag is high on only one partition | Hot key or skew | Inspect partitioning and key distribution |
| Metrics disappear during rebalance | Consumer temporarily has no assignment | Monitor group state and rebalances |
| Dashboard doubles lag | Multiple exporters publish for the same group/partition | Standardize scrape targets and labels |
| `AdminClient` fails to fetch committed offsets | Missing ACL permissions or broker unavailable | Check group authorization and connectivity |

## 19. Consumer lag observability checklist

1. Identify the consumer groups and topic-partitions to monitor.
2. Measure committed lag per partition and total per group.
3. Distinguish committed offsets from consumer current positions.
4. Display maximum partition lag to detect hot partitions.
5. Track `records-consumed-rate`, `fetch-rate`, `commit-rate`, and listener latency.
6. Monitor rebalances, assigned partitions, and consumer group state.
7. Set alerts based on lag level, growth rate, and duration tied to SLAs.
8. Measure time lag/end-to-end latency separately if the business needs time-based delay tracking.
9. Handle groups without committed offsets, deleted partitions, and abnormal offsets explicitly.
10. Secure Actuator, Prometheus, and `AdminClient` with appropriate ACLs/TLS.
11. Test lag before/after consume, commit, rebalance, and offset reset.
12. Never reset offsets or increase concurrency solely to lower the lag number without finding the root cause.

Consumer lag is a critical metric for knowing how well a consumer group keeps up with the Kafka log. When measured accurately per topic-partition, distinguishing committed offsets from fetch positions and combining processing, commit, rebalance, and time lag metrics, operations teams can identify real backlogs and choose the right remediation.
