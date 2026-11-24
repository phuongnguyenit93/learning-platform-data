# Alerting on stalled consumers

A Kafka consumer can remain alive yet stop making progress on records. For example, a listener may hang on a database call, the consumer may fail to poll the broker, a poison record may fail and retry endlessly, or a consumer group may lose its partition assignments. Checking only whether the process is alive or the container is `RUNNING` can report a healthy state while backlogs grow and events go unprocessed.

Accurately detecting this condition requires monitoring simultaneously **whether the source has new data**, **whether committed offsets are advancing**, **consumer lag and backlog age**, **whether the listener is succeeding**, and **whether the consumer thread continues polling**. A consumer receiving no records is not necessarily broken; the topic may simply have no traffic. Alerts must reflect the expected operational behavior of each stream.

## 1. Distinguishing idle, non-responsive, and stalled

These three states are frequently confused:

| State | Symptoms | Meaning |
|---|---|---|
| Legitimately idle | No new records; lag is 0; listener receives no data. | The topic is quiet. Usually a normal state. |
| Non-responsive consumer | `poll()` does not return within the monitored threshold; Spring Kafka emits `NonResponsiveConsumerEvent`. | The consumer may be blocked inside poll, e.g., network/broker/client issue. |
| Consumer stalled | The topic has new records or existing lag, yet committed offsets/throughput do not advance over time. | The consumer or processing pipeline cannot keep up or has stopped progressing. |

`ListenerContainerIdleEvent` only indicates that the container received no records during `idleEventInterval`. It does not prove the consumer is hung. Conversely, if `poll()` never returns, Spring Kafka cannot emit an idle event because no poll result arrives; in that situation `NonResponsiveConsumerEvent` is the right signal.

A listener taking too long to process can also delay the next poll, which is a processing-time issue between polls. Measure listener duration, committed offsets, and `max.poll.interval.ms` to detect it. Do not treat `NonResponsiveConsumerEvent` as a catch-all watchdog for slow listeners; that event is specifically designed to detect consumers appearing blocked inside `poll()`.

## 2. Signals to monitor

Do not rely on a single metric such as `records-consumed-rate`. Combine these signals:

| Signal | Question to answer | When is it worth alerting? |
|---|---|---|
| Log end offset | Are the topic/partitions continuing to receive records? | End offset rises while consumer offsets stop advancing. |
| Committed offset | Up to which offset has the group confirmed processing? | Offset remains flat while the source keeps receiving new data. |
| Consumer lag | How many records remain unprocessed by the group? | Lag grows continuously or breaches operational thresholds. |
| Oldest record age | How long has the oldest unprocessed record been waiting? | Record age exceeds processing SLA. |
| Records consumed rate | At what rate is the consumer receiving records? | Rate drops to 0 while the source keeps producing data. |
| Listener success/failure and duration | Are listener invocations succeeding or repeatedly failing/slow? | Failures spike, duration climbs, or no successful executions occur. |
| Assigned partitions | Is the consumer group assigned the partitions it should process? | Group has no assignments while the topic has partitions and consumers should be active. |
| Poll/heartbeat/rebalance | Is the consumer polling and maintaining membership? | Poll is blocked, heartbeats are missed, or rebalances repeat. |
| DLT/retry rate | Are records endlessly retrying or routing to DLT? | A single error blocks offset progress or DLT spikes abnormally. |

### Lag is not message age

Consumer group lag in exporters usually represents the offset distance between a partition's end position and the group's committed offset. A lag of 5,000 records may represent a few seconds on a high-throughput topic or many hours on a low-traffic topic. Therefore, also track oldest record age or event-time delay relative to current time.

Distinguish exporter lag calculated from committed offsets from the Kafka consumer client's `records-lag-max`: the client metric uses the consumer's current position, so records already polled but not yet committed may no longer count as lag in that metric. When alerts need committed progress, fetch committed offsets separately from a consumer group/admin exporter or admin tool.

With transactional topics and `isolation.level=read_committed`, consumers read only up to the Last Stable Offset (LSO), not necessarily the high watermark while transactions remain open. Exporters can calculate lag differently; when reading numbers, verify whether your exporter uses log end offset, high watermark, or LSO.

## 3. Enabling idle events and non-responsive monitoring in Spring Kafka

Spring Kafka provides two application event mechanisms:

- `ListenerContainerIdleEvent`: emitted when a container receives no records during `idleEventInterval`; when records resume, since Spring Kafka 2.6.2 `ListenerContainerNoLongerIdleEvent` is also emitted.
- `NonResponsiveConsumerEvent`: emitted when a consumer appears blocked in `poll()` longer than `noPollThreshold × pollTimeout`. A monitor checks periodically at `monitorInterval`.

Example configuring a dedicated listener container factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerMonitoringConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);

        var properties = factory.getContainerProperties();
        properties.setPollTimeout(5_000L);
        properties.setIdleEventInterval(60_000L);
        properties.setMonitorInterval(10);
        properties.setNoPollThreshold(3.0f);

        return factory;
    }
}
```

In this example:

- `pollTimeout=5,000 ms` is the timeout passed to `Consumer.poll()`.
- `noPollThreshold=3.0` sets the non-responsive threshold to three times the poll timeout, roughly 15 seconds.
- `monitorInterval=10` checks consumer state every 10 seconds.
- `idleEventInterval=60,000 ms` emits an idle event every minute when the container receives no records.

`monitorInterval` is in seconds; `pollTimeout` and `idleEventInterval` are in milliseconds. `noPollThreshold` should be greater than `1.0` to avoid false events from race conditions. These values are examples only; choose them based on poll latency, traffic, and service incident detection requirements.

Since Spring Kafka 2.8, `idleBeforeDataMultiplier` defaults to `5.0`: before the container receives its first record, the wait time before emitting an idle event can be multiplied by this factor. After the first record is received, the multiplier no longer applies. If you need custom startup idle alerts, account for this behavior when picking `idleEventInterval`.

Attach the factory to the listener:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "ordersKafkaListenerContainerFactory"
)
public void consume(OrderEvent event) {
    orderService.handle(event);
}
```

If using Spring Boot's auto-configured factory, configure `ContainerProperties` on the existing factory or create a custom factory referenced via `containerFactory`. When creating a new factory, preserve all serializer, converter, error handler, transaction manager, and concurrency settings needed by the application.

## 4. Capturing application events for logs and metrics

`@EventListener` can receive events from every listener container in the application context. With concurrent `@KafkaListener`s, child container IDs usually include suffixes like `orders-listener-0`, `orders-listener-1`; filter by prefix or listener ID accordingly.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;

@Component
public class KafkaConsumerEventMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerEventMonitor.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (!event.getListenerId().startsWith("orders-listener")) {
            return;
        }

        log.info("Kafka listener idle: id={}, idleMs={}, partitions={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions());
    }

    @EventListener
    public void onActiveAgain(ListenerContainerNoLongerIdleEvent event) {
        if (!event.getListenerId().startsWith("orders-listener")) {
            return;
        }

        log.info("Kafka listener received records again: id={}, partitions={}",
                event.getListenerId(), event.getTopicPartitions());
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        if (!event.getListenerId().startsWith("orders-listener")) {
            return;
        }

        log.error("Kafka consumer is not responding: id={}, timeSinceLastPollMs={}, partitions={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll(),
                event.getTopicPartitions());
    }
}
```

The event handler above simply logs state changes. In production, you can increment `kafka.consumer.nonresponsive` and `kafka.consumer.idle` counters while sending structured logs to a centralized platform. Use listener ID or service name as low-cardinality tags; never use event IDs, message keys, or constantly changing partition lists as metric tags.

Events are normally published on the consumer thread. If you replace the application event multicaster with an asynchronous executor, do not invoke methods on `event.getConsumer()` from another thread because the Kafka `Consumer` is not thread-safe. Only access the consumer reference when you fully understand container threading and lifecycle.

## 5. Detecting per-partition idleness

A topic can receive uneven traffic: partition 0 continuously receives records while partition 3 receives none for hours. `ListenerContainerIdleEvent` describes only the container's state; to monitor individual partitions, configure `idlePartitionEventInterval`.

```java
var properties = factory.getContainerProperties();
properties.setIdleEventInterval(60_000L);
properties.setIdlePartitionEventInterval(120_000L);
```

Spring Kafka emits `ListenerContainerPartitionIdleEvent` when a partition receives no records for the configured interval and `ListenerContainerPartitionNoLongerIdleEvent` when that partition resumes receiving records. This signal is helpful when detecting partitions lacking expected traffic or abnormal load skew.

Do not alert solely because one partition is idle. A partition may simply not be chosen by the producer due to key distribution, or the domain may have produced no events for those keys. Alert only when that partition has expected traffic, an existing backlog, or partition-level SLAs.

## 6. Monitoring listener duration and outcomes with Micrometer

Spring Kafka automatically creates a Micrometer timer for listeners since version 2.3 if Micrometer is on the classpath and a `MeterRegistry` is in the application context. The timer is named `spring.kafka.listener` with main tags:

| Tag | Value |
|---|---|
| `name` | Container bean name; concurrent containers add suffixes per child container. |
| `result` | `success` or `failure`. |
| `exception` | `none` or `ListenerExecutionFailedException`. |

This timer tracks invocation counts, processing durations, and error rates. You can add static tags via `ContainerProperties.micrometerTags` or dynamic tags via `micrometerTagsProvider` (since Spring Kafka 2.9.8/3.0.6). Do not put business keys or event IDs into tags because cardinality will grow unboundedly.

Example adding a `service` tag:

```java
import java.util.Map;

var properties = factory.getContainerProperties();
properties.setMicrometerTags(Map.of("service", "orders"));
```

If Micrometer Observation is enabled via `observationEnabled=true`, the observation mechanism manages timers and standard listener timers are disabled to avoid duplicate recording. Choose one instrumentation approach and inspect actual meters in the registry/exporter.

## 7. Collecting Kafka consumer client metrics

Listener timers reflect processing time in Spring; Kafka client metrics reveal fetch, poll, commit, and lag status. Spring Kafka provides `MicrometerConsumerListener` to automatically bind/unbind metrics when `ConsumerFactory` creates or closes consumers.

Example with a manually constructed factory:

```java
import java.util.List;
import java.util.Map;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.ImmutableTag;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.MicrometerConsumerListener;

@Bean
ConsumerFactory<String, OrderEvent> consumerFactory(
        Map<String, Object> consumerProperties,
        MeterRegistry meterRegistry) {

    var factory =
            new DefaultKafkaConsumerFactory<String, OrderEvent>(consumerProperties);
    factory.addListener(new MicrometerConsumerListener<>(
            meterRegistry,
            List.of(new ImmutableTag("service", "orders"))));
    return factory;
}
```

If Spring Boot already creates the `ConsumerFactory`, attach the listener to that existing factory with an appropriate bean/customizer; do not create a second factory just to enable metrics because listener containers may still be using the other factory.

Notable Kafka consumer metrics to monitor include:

| Kafka metric | Meaning |
|---|---|
| `records-consumed-rate` | Rate of records received by the consumer. |
| `records-lag-max` | Maximum lag across tracked partitions; this client metric uses current consumer position, not committed offset. |
| `fetch-rate` | Frequency of fetch requests. |
| `commit-rate` | Frequency of offset commits. |
| `assigned-partitions` | Number of partitions currently assigned to the consumer. |
| `last-poll-seconds-ago` | Seconds elapsed since the most recent `poll()` call. |
| `time-between-poll-max` | Maximum interval observed between two `poll()` calls. |
| `poll-idle-ratio-avg` | Fraction of time the consumer spends inside `poll()` waiting for data rather than processing records; low values can mean processing code consumes most of the time. |

Metric names exported via Micrometer/Prometheus may be normalized differently from native Kafka JMX names. Check real metrics in `/actuator/prometheus` or the application registry before writing alert rules.

## 8. Measuring lag and offset progression

For each `consumer group + topic + partition` tuple, monitor at minimum:

- `logEndOffset`: current end position of the partition per the measurement tool.
- `committedOffset`: offset committed by the group.
- `lag`: distance between log end and committed offset as defined by the exporter.
- `lastCommitTime`: timestamp when the offset last advanced.
- `oldestUnprocessedAge`: age of the oldest unprocessed record, if derivable from event timestamps.

Never compare offsets across two different partitions to form a global ordering. Compute lag and progression per partition, then aggregate by group/topic for dashboards.

Example 5-minute observation table:

| Partition | Start/end log end offset | Start/end committed offset | Assessment |
|---|---:|---:|---|
| 0 | 10,000 → 10,800 | 9,900 → 10,700 | Consumer advancing steadily; lag stays roughly flat. |
| 1 | 8,000 → 8,500 | 7,900 → 7,900 | Producer keeps writing while consumer makes no progress. |
| 2 | 4,000 → 4,000 | 4,000 → 4,000 | No traffic and no backlog; legitimately idle. |

Partition 1 requires investigation. Partition 2 should not trigger an alert unless traffic or business heartbeats are expected.

With `read_committed`, committed offset remains the group's committed position, while log end/LSO differs when open transactions exist. Use a consistent lag definition across dashboards and alerts; avoid comparing two exporters that measure against different offset boundaries.

## 9. Designing multi-signal alerts

A reliable stalled-consumer alert typically combines three conditions:

1. A backlog exists or the source continues writing records.
2. Committed offsets fail to advance over a sufficiently long window.
3. The condition persists beyond the stream's SLA or normal variance.

Example logical condition:

```text
consumer_lag > 0
AND committed_offset unchanged for 5 minutes
AND log_end_offset increases over the same interval
```

This is a logical expression, not standardized metric names. Exact metric names and labels depend on your Kafka exporter, JMX exporter, or custom instrumentation. In PromQL, map the corresponding gauges and compare series per `group`, `topic`, and `partition`.

Illustrative PromQL expression when an exporter exposes the corresponding gauges:

```promql
kafka_group_lag > 0
and on (group, topic, partition)
  (kafka_committed_offset == kafka_committed_offset offset 5m)
and on (topic, partition)
  (kafka_log_end_offset > kafka_log_end_offset offset 5m)
```

`kafka_group_lag`, `kafka_committed_offset`, and `kafka_log_end_offset` in this example are illustrative names; substitute the actual metric names and labels from your exporter. For low-traffic streams, adjust `5m` to fit SLAs and event schedules.

### Recommended alert matrix

| Condition | Suggested severity | Rationale |
|---|---|---|
| Lag grows and committed offset stalls for several minutes while source still receives records. | Warning | Consumer is starting to fall behind. |
| Oldest record age breaches business SLA. | Critical/Page | Events are waiting longer than allowed processing bounds. |
| `NonResponsiveConsumerEvent` occurs repeatedly or persists. | Critical/Page | Consumer poll appears blocked. |
| Listener failures spike and offsets stall. | Warning/Critical | Processing errors or retries are holding back the backlog. |
| Assigned partitions equal 0 while the group should be active and topic has partitions. | Warning | Consumers are not receiving partitions to process. |
| No new records and lag equals 0. | No alert | Likely just a normally idle topic. |
| One partition is idle with no backlog and no expected traffic. | No alert | The partition may simply not have been selected during that window. |

Use `for` clauses to filter out brief spikes and separate warnings from pages. Do not page simply because lag is positive on a single scrape; lag naturally appears briefly whenever producers write faster than consumers in short bursts.

## 10. Kafka consumer settings affecting progress

Two critical properties when listeners process slowly are `max.poll.interval.ms` and `session.timeout.ms`.

| Property | Role | When exceeded |
|---|---|---|
| `max.poll.interval.ms` | Maximum allowed time between two `poll()` calls under group management. | Consumer is considered stalled from polling; the group may rebalance and reassign partitions to another member. |
| `session.timeout.ms` | Maximum time the broker waits for heartbeats to consider a consumer alive under the classic group protocol. | Broker removes the consumer from the group if no heartbeat arrives within the limit. |
| `max.poll.records` | Maximum records returned in a single poll. | Large values can lengthen a processing cycle if each record is expensive. |
| `pollTimeout` | Timeout passed by the container to `Consumer.poll()`. | Affects when poll returns and the `NonResponsiveConsumerEvent` threshold. |

`max.poll.interval.ms` is not the same as `session.timeout.ms`. The Kafka client can continue sending heartbeats while processing records, yet if it fails to call `poll()` within `max.poll.interval.ms`, the consumer can still be evicted from the group. With the newer `consumer` group protocol, some heartbeat/session settings are broker-managed; verify which protocol is in use before tuning client properties.

Example Spring Boot consumer configuration:

```yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
```

This is an example only. Do not blindly raise `max.poll.interval.ms` to hide a hung listener. First measure the maximum processing time for a polled batch, then tune `max.poll.records`, optimize dependencies, or offload long-running work using an appropriate pattern. Raising the interval also delays detecting genuinely dead consumers and can prolong rebalances.

## 11. Common causes of stalled consumers

| Cause | Symptoms | Investigation steps |
|---|---|---|
| Listener hung on database/API call | Listener duration rises, next poll delayed, lag grows. | Check connection pools, query timeouts, HTTP timeouts, and thread dumps. |
| Single record failing repeatedly | Failure timer rises, committed offset stuck on the same partition. | Check error handler, retry/backoff, poison records, and DLT. |
| Consumer cannot poll broker | `NonResponsiveConsumerEvent`, fetch rate drops or flatlines. | Check broker/network, DNS, TLS, client logs, and thread dumps. |
| Consumer group continuously rebalancing | Assigned partitions fluctuate, offsets/throughput choppy. | Check member restarts, `max.poll.interval.ms`, session/heartbeats, and processing duration. |
| Consumer has no assigned partitions | Assigned partitions equal 0, listener receives no records. | Check group ID, topic subscription, ACLs, partition count, and group state. |
| Consumer intentionally paused | Idle events or zero throughput while container is paused. | Check pause/resume state and backpressure triggers. |
| One partition is hot | Lag concentrates in one partition while others progress steadily. | Check key distribution, hot keys, partitioning, and consumer concurrency. |
| Deserialization or schema error | Failures/DLT jump immediately upon encountering an incompatible record. | Check serializers, deserializers, schema versions, and error handler. |
| JVM pause/GC or thread starvation | Large poll gaps, latency spikes across multiple listeners simultaneously. | Check GC pauses, CPU throttling, thread pools, and memory pressure. |

## 12. Runbook when a stalled-consumer alert fires

When an alert fires, investigate in order to avoid offset resets or restarts that destroy diagnostic evidence:

1. **Confirm traffic exists:** check whether the topic/partition log end offset increased during the alert window. If there are no new records and lag is 0, it may simply be idle.
2. **Determine scope:** identify which group, topic, partition, and listener ID are affected. If only one partition is stuck, focus on key distribution or a specific record.
3. **Check assignments:** verify the consumer group has members and partition assignments; confirm the consumer is not unintentionally paused.
4. **Compare offsets:** check whether committed offsets are advancing and how lag/oldest record age behave.
5. **Inspect the listener:** check success/failure timers, exceptions, retries, DLT activity, and database/API call durations.
6. **Inspect poll/rebalances:** look for `NonResponsiveConsumerEvent`, max poll interval logs, heartbeats, and rebalances.
7. **Check resources:** CPU, memory, GC pauses, thread dumps, network, broker health, and connection pools.
8. **Fix root cause:** resolve the failing dependency, poison record, configuration, or capacity bottleneck before replaying/restarting.
9. **Verify recovery:** committed offsets resume advancing, lag decreases, oldest record age drops, and listener successes return.

You can quickly inspect offsets, lag, and members via the Kafka CLI:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group order-projection
```

The output lets you compare `CURRENT-OFFSET`, `LOG-END-OFFSET`, `LAG`, `CONSUMER-ID`, `HOST`, and `CLIENT-ID` per topic/partition. For secured clusters, add `--command-config client.properties` so the CLI uses the proper security protocol and authorized credentials.

Never reset group offsets to `latest` just to silence an alert; doing so can skip unprocessed records. Never restart repeatedly before identifying the root cause, as restarts can trigger rebalance storms and worsen backlogs.

If a poll thread is genuinely stuck, Spring Kafka emits `NonResponsiveConsumerEvent`; documentation notes you can stop the container to wake the consumer and let it shut down. If implementing automated recovery, invoke stop from a different thread, target the parent `ConcurrentMessageListenerContainer`, and enforce a clear restart/backoff policy. Never stop a child container directly or call stop on the event-handling thread itself if doing so blocks the listener.

## 13. Distinguishing consumer health from application health

A health endpoint reporting that the process is alive does not prove the consumer is making progress. An application can return HTTP 200 while listener threads are hung or the group holds zero partition assignments.

Separate these concepts:

- **Liveness:** the JVM/process is alive and able to continue running.
- **Readiness:** the application is ready for traffic per service criteria; in some systems, Kafka dependencies must be ready before accepting HTTP requests.
- **Consumer progress:** committed offsets and listener successes continue advancing with traffic.
- **Consumer availability:** the group holds valid members/assignments and consumers can poll.

Do not turn every idle period into a readiness failure. For event-driven topics, idleness is normal; marking pods NotReady whenever a topic has no records can trigger unnecessary rollout loops or autoscaling churn. Use dedicated alerts for progress and tie readiness only to conditions genuinely required by the service.

## 14. Testing alerts and recovery

An observability test suite should simulate multiple states to confirm alerts do not false-positive:

| Scenario | Expected outcome |
|---|---|
| Topic has no records, lag is 0 | Idle event may fire; no stalled alert is triggered. |
| Producer writes steadily, consumer processes normally | Offsets advance and lag stays stable/drops; no alert. |
| Listener is slow yet finishes within limits | Duration increases; latency warning if threshold exceeded, not classified as non-responsive poll. |
| Listener blocks for a long time | Offsets stall, lag grows; inspect max poll interval and listener timer. |
| Consumer poll hangs/never returns | `NonResponsiveConsumerEvent` fires per monitor threshold. |
| One record fails repeatedly | Failures/retries climb; partition offset held back per error handling policy. |
| Consumer group loses assignment | Assigned partitions drop or hit 0; alert per group state. |
| Consumer intentionally paused | Metrics reflect paused state; no alert if pause is planned. |
| Consumer recovers and receives records again | `ListenerContainerNoLongerIdleEvent` may fire; offsets resume advancing and alert clears. |

Integration tests can use Embedded Kafka or Testcontainers to create real topics/groups. For blocked-listener scenarios, use latches in tests and always enforce timeouts so tests cannot hang indefinitely. For non-responsive polls, simulate conditions preventing `poll()` from returning; do not assume merely sleeping inside a listener triggers this event.

## 15. Common alert design mistakes

| Design mistake | Consequence | Fix |
|---|---|---|
| Alerting whenever `records-consumed-rate = 0` | Quiet topics trigger false alarms. | Combine with source traffic, lag, and event schedules. |
| Alerting immediately whenever lag > 0 | Normal micro-backlogs trigger pages. | Use time windows, lag growth rate, and oldest record age. |
| Monitoring only process health | Listener hangs while the process stays alive. | Monitor offsets, lag, listener timers, and poll events. |
| Monitoring only total group lag | One stuck partition is masked by healthy partitions. | Monitor lag and committed offsets per partition. |
| Treating `ListenerContainerIdleEvent` as proof of a dead consumer | Legitimate idleness is mistaken for failure. | Distinguish idle from `NonResponsiveConsumerEvent` and stalled conditions. |
| Setting `max.poll.interval.ms` excessively high to stop rebalances | Delays detecting dead consumers and hides overly slow listeners. | Measure processing time, shrink batches, optimize dependencies, then pick a realistic timeout. |
| Using unbounded topics/partitions/message keys as metric tags | High cardinality exhausts Prometheus/Micrometer resources. | Use controlled service, listener ID, group, and topic tags; keep partition details in logs or bounded metrics. |
| Automatically resetting offsets on alert | Unprocessed events can be skipped. | Investigate and use a controlled replay workflow. |

## 16. Key takeaways

- Idle does not mean stalled; a topic with no traffic and zero lag is usually normal.
- `ListenerContainerIdleEvent` fires when no records arrive within `idleEventInterval`.
- `NonResponsiveConsumerEvent` fires when a consumer appears blocked in `poll()` longer than `noPollThreshold × pollTimeout`.
- `monitorInterval` controls non-responsive check frequency; `noPollThreshold` should exceed `1.0`.
- `ListenerContainerNoLongerIdleEvent` indicates records have resumed after an idle period.
- Track committed offset, log end offset, lag, oldest record age, listener timers, assignments, and rebalances.
- `max.poll.interval.ms` caps time between polls; `session.timeout.ms` governs heartbeats in the classic group protocol.
- Good alerts confirm source traffic or an actual backlog before paging.
- Never reset offsets or restart repeatedly to mask stalled-consumer symptoms.
- Follow a runbook combining logs, metrics, events, thread dumps, and dependency health to find root causes.

Stalled-consumer alerts must reflect events actually being held back, not merely a listener temporarily receiving no data. Combining offset/lag metrics with incoming traffic, record age, listener duration, and Spring Kafka application events lets teams distinguish idle topics, blocked polls, slow listeners, and lost group assignments. With clear signals, operations can fix the true cause instead of resetting offsets or restarting blindly.

## References

- [Spring for Apache Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
- [Spring for Apache Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring for Apache Kafka — Monitoring with Micrometer](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka — NonResponsiveConsumerEvent API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/event/NonResponsiveConsumerEvent.html)
- [Apache Kafka — Consumer Configurations](https://kafka.apache.org/41/generated/consumer_config.html)
