# Rebalance count

## 1. What does rebalance count measure?

In a Kafka consumer group system, **rebalance** is the process where the coordinator and consumer members coordinate to establish or change partition assignments. When a new consumer joins, an existing consumer leaves the group, heartbeats are lost, poll deadlines are breached, or subscriptions/assignments change, the group may need to rebalance.

**Rebalance count** is a metric counting how many times a rebalance process was observed by a component over a time window or across its lifetime. It is an important operational metric because rebalances often cause a brief pause or shift in partition ownership, bringing fluctuations in throughput, consumer lag, and redelivery risk.

However, distinguish from the start:

- **Client-level rebalance count**: how many times **a single Kafka consumer client** experienced rebalances per the Kafka client metric definition.
- **Group-level rebalance events**: state transitions of the **entire consumer group**. A single group-level event can increment rebalance counts across many consumer clients simultaneously.
- **Application callback count**: how many times Spring Kafka invokes `onPartitionsAssigned`, `onPartitionsRevokedBeforeCommit`, or `onPartitionsLost`. These callbacks are not a single canonical count for the whole group.

Merging these three concepts into one makes dashboards show misleading numbers. For example, a group with five members rebalancing once can increment client metrics across multiple members—it does not mean the group rebalanced five independent times.

### 1.1. Example

~~~text
Consumer group: checkout-service
Topic: orders (6 partitions)

Before rebalance:
  Consumer A -> P0, P1
  Consumer B -> P2, P3
  Consumer C -> P4, P5

Consumer D joins group.

Group performs one redistribution pass:
  Consumer A -> P0, P1
  Consumer B -> P2
  Consumer C -> P3, P4
  Consumer D -> P5

Clients A/B/C/D may observe separate rebalance milestones.
One "group assignment change" does not equal
the sum of callbacks executed across all clients.
~~~

Rebalance count helps spot **churn**: a group constantly shifting assignments instead of keeping consumers stable. The number alone does not prove a bug; track it over time alongside root causes and impact.

## 2. Why does rebalance count matter?

A system may keep logging "consumer healthy" with pods in `Running` state, yet rebalance continuously and only process records in short bursts between assignment changes.

Observable consequences include:

1. **Interrupted record reception:** consumers are joining/reconciling the group or revoking/assigning partitions.
2. **Rising consumer lag:** producers keep writing while consumers are not processing at normal speed.
3. **Partition ownership shifts:** per-partition state/caches may need cleanup or warm-up.
4. **Offset commit failures:** commits can be rejected when group generation or assignments change.
5. **Redelivery:** records processed without committed offsets may be re-read by a new consumer.
6. **Higher infrastructure load:** extra coordinator requests, metadata/assignment traffic, and downstream cold starts.
7. **Latency spikes:** p95/p99 processing delays can climb even if average throughput looks steady.

Not every rebalance is bad. Scale-outs, rolling deployments, or partition count changes legitimately trigger rebalances. What you must catch are **rebalances that are too frequent, prolonged, failing, or occurring outside expected operations**.

## 3. Causes of consumer group rebalances

| Cause category | Example | Investigation action |
|---|---|---|
| Member join | Scale from 2 to 3 pods | Correlate with deployments/autoscaling |
| Member leave | Graceful shutdown, scale-in | Inspect lifecycle and rollouts |
| Session timeout | Heartbeat fails to reach coordinator long enough | Check network, JVM pauses, brokers |
| Max poll interval | Listener/batch takes too long | Check processing duration and `max.poll.interval.ms` |
| Consumer crash | OOM, process kill, node failure | Check pod restarts, OOM events |
| Subscription change | Consumer subscribes to a different topic set | Check config/deployment |
| Partition metadata change | Partition count increased or assignments altered | Correlate with topic operations |
| Coordinator disturbance | Broker failover, coordinator unavailable | Check broker logs and request latency |
| Protocol/assignor change | Client upgrade, assignment strategy switch | Check compatibility, protocol, assignor |
| Static member identity conflict | Duplicate `group.instance.id` | Check per-member uniqueness |

This table lists common possibilities; an event occurring does not guarantee every rebalance counter increments. How members reconcile assignments also depends on Kafka client version, group protocol, and assignor.

Specifically, a **slow listener** does not immediately cause a heartbeat timeout. In modern classic consumer clients, heartbeats normally run on a background thread; a listener may keep sending heartbeats yet fail to call `poll()` before `max.poll.interval.ms`.

## 4. From rebalance events to metrics

### 4.1. One group rebalance can involve multiple clients

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant B as Consumer B
    participant C as Group coordinator
    participant N as New consumer

    A->>C: Normal heartbeat / membership
    B->>C: Normal heartbeat / membership
    N->>C: Join group
    Note over C: Membership/assignment needs update
    C-->>A: Reconcile / rebalance
    C-->>B: Reconcile / rebalance
    C-->>N: Assignment
    Note over A: Client metrics may rise
    Note over B: Client metrics may rise
    Note over N: New membership state
~~~

If A and B both increment `rebalance-total` by 1, the sum of client counters rises by 2. That does not prove the coordinator ran two independent group-level passes.

### 4.2. Counter lifecycle

Client counters normally accumulate over the process/client lifetime. They reset when the JVM or `KafkaConsumer` is recreated. Example:

~~~text
10:00 Consumer A rebalance-total = 12
10:10 Consumer A rebalance-total = 14
10:20 Process restart
10:21 New Consumer A rebalance-total = 1
~~~

If a dashboard plots the raw counter like a gauge and sees 14 drop to 1, that is not "group rebalances decreased." It is a **lifecycle counter reset**.

In Prometheus, typically analyze using `rate()` or `increase()` rather than raw current counter values. Watch series labels, scraping, and client ID changes across pod restarts.

## 5. Rebalance-related Kafka client metrics

The Kafka consumer client provides group coordination metrics. Across many client versions, they appear under a JMX/Metrics group like:

~~~text
kafka.consumer:
  type=consumer-coordinator-metrics
  client-id=<client-id>
~~~

Common metric names:

| Kafka client metric | Operational meaning |
|---|---|
| `rebalance-total` | Total successful rebalances per consumer client metric |
| `rebalance-rate-per-hour` | Hourly rebalance rate on the client |
| `rebalance-latency-avg` | Average rebalance duration measured by the client |
| `rebalance-latency-max` | Maximum rebalance duration measured by the client |
| `last-rebalance-seconds-ago` | Time since the last rebalance, if provided by client/version |
| `assigned-partitions` | Number of partitions currently assigned to the consumer |
| `failed-rebalance-total` | Total failed rebalances, when supported by version |
| `failed-rebalance-rate-per-hour` | Rate of failed rebalances, when supported by version |

**Names and availability depend on Kafka client version, group protocol, JMX exporter, and metrics library.** Never treat the list above as a guarantee that every app exposes every metric. The first step when implementing is inspecting the actual metrics emitted by your running client.

### 5.1. rebalance-total

This is a cumulative counter per Kafka consumer client definition. When it rises, the client participated in a completed rebalance under its protocol. The counter is most useful when tracking **increases over a time window**.

Never compare raw `rebalance-total` on a freshly started pod against a pod running for 30 days to conclude the new pod is healthier.

### 5.2. rebalance-rate-per-hour

This rate metric spots churning groups. Example:

~~~text
Consumer A:
  rebalance-rate-per-hour ~ 0.0    -> stable during observation period
  rebalance-rate-per-hour ~ 12.0   -> repeated membership activity
~~~

This value is a client-side rate, not guaranteed to mean **12 independent group-wide rebalances**. Combine counters, latency, and member counts.

### 5.3. rebalance latency

A high rebalance count where each finishes very quickly has a different impact from a low count where a single rebalance lasts tens of seconds.

Track two axes together:

~~~text
Frequency: How many rebalances occur?
Duration:  How long does each take?
~~~

With cooperative rebalances or the new group protocol, assignments can shift in multiple steps. Latency metrics reflect client-measured protocol timing and do not replace measuring actual business disruption.

### 5.4. last rebalance

When a time-since-last-rebalance metric exists, it helps distinguish:

- A single rebalance after a deployment.
- A group rebalancing every few dozen seconds.
- A consumer that just restarted.
- A client whose assignments have been stable for a long time.

When metrics vanish because a process is down, never interpret that as "zero rebalances"; monitoring data may simply be missing.

## 6. Does Spring Kafka create a rebalance count metric automatically?

Spring Kafka manages listener containers and can integrate Micrometer/Observation. However, distinguish the metric layers:

1. **Kafka client metrics** such as `rebalance-total`: emitted by `KafkaConsumer`/Kafka client.
2. **Spring Kafka listener/container metrics**: measure listener invocations, processing duration, and container observations depending on version/config.
3. **Custom application metrics**: count callbacks or state transitions from `ConsumerAwareRebalanceListener`.
4. **Broker/group coordinator metrics**: reflect server-side activity, not equivalent to client-specific rebalance counters.

Enabling Spring Kafka listener timers does not mean all `KafkaConsumer`/JMX metrics appear automatically on the Prometheus endpoint. Kafka client metrics may require a Micrometer Kafka binder or JMX exporter config. Depending on Spring Boot version, some Kafka metrics may be auto-bound; verify at the metrics endpoint.

Example where "rebalance" means different things:

~~~text
Kafka consumer JMX:
  rebalance-total = 6
    -> Counted per Kafka client definition.

Application counter:
  partitions-assigned-callback-total = 8
    -> Counts assigned callbacks, not the same metric.

Broker logs:
  Group completed rebalance 3 times
    -> Group/coordinator perspective, different scope.
~~~

**Never name a callback metric `kafka_consumer_rebalance_total` if it only counts `onPartitionsAssigned`**, because readers will mistake it for the official Kafka client counter.

## 7. Example Spring Kafka listener container configuration

Consumer group and listener configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    consumer:
      group-id: checkout-service
      enable-auto-commit: false
      max-poll-records: 200
      properties:
        max.poll.interval.ms: 300000
        session.timeout.ms: 30000
        heartbeat.interval.ms: 10000
    listener:
      concurrency: 3
      ack-mode: record
~~~

This example targets the **classic** group protocol with Kafka client versions supporting those properties. When using `group.protocol=consumer`, several session/heartbeat settings are broker-managed; do not copy classic settings assuming they remain effective.

Implications for rebalance count:

- `concurrency` increases consumer members per instance, potentially raising client metric series and callback counts.
- `max.poll.records` and `max.poll.interval.ms` govern the risk of clients appearing stalled in the poll loop.
- `session.timeout.ms` governs heartbeat loss in the classic group protocol.
- `enable-auto-commit=false` lets the container manage offsets per processing, yet **does not prevent rebalances**.
- `ack-mode=record` shrinks the uncommitted window per record in some cases, yet does not eliminate redelivery on rebalance/crash.

Never tune timeouts solely to make rebalance count look prettier. Balance failure-detection speed, processing duration, and SLOs.

## 8. Tracking rebalance callbacks in Spring Kafka

To explain rebalance counts with concrete application events, Spring Kafka provides `ConsumerAwareRebalanceListener`.

Useful callbacks:

- `onPartitionsRevokedBeforeCommit`: invoked when partitions are about to be revoked in the container's flow.
- `onPartitionsRevokedAfterCommit`: callback after the corresponding commit step, when supported by version/container.
- `onPartitionsAssigned`: consumer receives assignments.
- `onPartitionsLost`: consumer lost partition ownership and should no longer commit as if still owner.

Callbacks record **partition lifecycle**. They do not supply a globally unique "group rebalance ID" guaranteed to be 1-to-1 per pass. Under cooperative rebalances or multi-step assignment shifts, callback counts can differ markedly from `rebalance-total`.

### 8.1. Example registering a rebalance listener

~~~java
@Configuration
public class CheckoutKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            checkoutListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                MeterRegistry meterRegistry
            ) {
        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties().setConsumerRebalanceListener(
            new ConsumerAwareRebalanceListener() {

                @Override
                public void onPartitionsRevokedBeforeCommit(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions
                ) {
                    meterRegistry.counter(
                        "app.kafka.partition.callbacks",
                        "listener", "checkout",
                        "phase", "revoked"
                    ).increment();

                    log.info("Revoked partitions: {}", partitions);
                }

                @Override
                public void onPartitionsAssigned(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions
                ) {
                    meterRegistry.counter(
                        "app.kafka.partition.callbacks",
                        "listener", "checkout",
                        "phase", "assigned"
                    ).increment();

                    log.info("Assigned partitions: {}", partitions);
                }

                @Override
                public void onPartitionsLost(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions
                ) {
                    meterRegistry.counter(
                        "app.kafka.partition.callbacks",
                        "listener", "checkout",
                        "phase", "lost"
                    ).increment();

                    log.warn("Lost partitions: {}", partitions);
                }
            }
        );

        return factory;
    }
}
~~~

Required imports include:

~~~java
import java.util.Collection;

import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;
~~~

`OrderEvent` and `log` are illustrative application types/variables. Callback signatures must match your Spring Kafka version. This snippet illustrates a **callback counter**, not Kafka client `rebalance-total`.

### 8.2. Why callback count is not rebalance count

Consider these cases:

- When a listener starts up and receives partitions, `onPartitionsAssigned` fires even though the consumer held no prior assignment.
- In eager rebalances, many members fire both revoke and assign.
- In cooperative rebalances, some partitions stay while others migrate incrementally.
- When a consumer loses its session/crashes, the old JVM does not necessarily run callbacks before broker reassignment.
- With concurrent containers, multiple child consumers run independent callbacks.
- One callback can receive multiple partitions; counting callbacks differs from counting partition transitions.

Therefore, name the metric accurately for what it counts: **assignment callbacks**, **revocation callbacks**, **lost callbacks**. For Kafka client rebalance counts, use the `KafkaConsumer`/Kafka client counter.

## 9. Counting partitions vs. counting callbacks

A single callback can receive a collection of many partitions:

~~~text
onPartitionsRevokedBeforeCommit:
  [orders-0, orders-1, orders-2]

Callback count increments: 1
Partitions revoked: 3
~~~

These are two different metrics. You can measure:

- `partition_callback_total{phase="revoked"}`: number of callbacks.
- `partition_transition_partitions_total{phase="revoked"}`: total partitions passed to those callbacks.
- `assigned_partitions`: partitions currently held by a consumer.
- `rebalance_total`: Kafka client metric, not replaced by callbacks.

To measure affected partitions, increment the counter by `partitions.size()` inside the callback instead of 1. Even that count does not prove that many group-wide rebalances occurred.

Note also that an assignment callback may include partitions that are not new to the app depending on protocol/initial state; "partitions mentioned in callbacks" is not always identical to partitions that actually changed owner.

## 10. Reading Kafka consumer metrics via JMX

Kafka clients typically expose metrics via JMX when JVM/JMX is properly configured. A common object name:

~~~text
kafka.consumer:type=consumer-coordinator-metrics,client-id=checkout-client-0
~~~

Attributes can include:

~~~text
rebalance-total
rebalance-rate-per-hour
rebalance-latency-avg
rebalance-latency-max
last-rebalance-seconds-ago
assigned-partitions
~~~

These are common example names, not live output from a JVM. With JConsole, JMX exporters, or equivalent tooling, **enumerate actual attributes** and identify the exact client IDs in your runtime.

### 10.1. Client IDs in Spring Kafka

One application JVM with `concurrency=3` can spawn three `KafkaConsumer` instances with distinct client IDs. Depending on config and version, IDs may carry index suffixes.

Example:

~~~text
checkout-consumer-0
checkout-consumer-1
checkout-consumer-2
~~~

If a dashboard queries only one client ID, it can miss most rebalance activity in the listener container.

### 10.2. When an application has multiple listeners

One process may run multiple consumer groups or multiple listener container factories. Each group and each consumer client must be labeled accurately.

Example:

~~~text
service=checkout
  listener=orders
  group=checkout-service
  client=checkout-orders-0

service=checkout
  listener=payments
  group=payment-projection
  client=checkout-payments-0
~~~

Do not sum all counters into one "checkout-service rebalances" number when the app runs multiple independent groups.

## 11. From JMX metrics to Prometheus

With a JMX Exporter, Micrometer Kafka binder, or equivalent bridge, Kafka client rebalance metrics can be exported to Prometheus.

An illustrative series name from JMX exporter:

~~~text
kafka_consumer_coordinator_metrics_rebalance_total
~~~

**This series name depends on exporter configuration; it is not a universal standard name in every Spring Boot deployment.** Micrometer can format meter names and tags under different conventions. Before writing production PromQL, inspect `/actuator/prometheus` or your live scrape endpoint to verify exact series names and labels.

Useful labels:

~~~text
application="checkout"
environment="prod"
group_id="checkout-service"
client_id="checkout-consumer-0"
instance="pod-a"
~~~

Not every JMX metric carries `group_id` automatically. If the exporter only has `client-id`, establish a reliable mapping from client to consumer group or configure common tags appropriately. Never derive a group label by fragile parsing of an unstable client ID.

### 11.1. Counter resets and rate()

Prometheus counters should be analyzed with:

~~~promql
increase(kafka_consumer_coordinator_metrics_rebalance_total[15m])
~~~

This expression returns the **estimated** increase over a 15-minute window for a series. `increase()` handles counter resets per Prometheus semantics given enough samples, yet cannot reconstruct events lost between scrapes or when a client dies rapidly.

Per-second rate:

~~~promql
rate(kafka_consumer_coordinator_metrics_rebalance_total[5m])
~~~

For rebalances per hour on a consumer series:

~~~promql
rate(kafka_consumer_coordinator_metrics_rebalance_total[15m]) * 3600
~~~

This remains a **client rate**, not a normalized group-event rate.

### 11.2. Aggregating across clients

If `group_id` and `application` labels are present and accurate:

~~~promql
sum by (application, group_id) (
  increase(kafka_consumer_coordinator_metrics_rebalance_total[15m])
)
~~~

This estimates **total client rebalance participations in the group**, not necessarily unique group-level rebalance passes.

You can title the dashboard panel:

~~~text
Client rebalance participation, last 15m
~~~

Avoid labeling it:

~~~text
Exact group rebalance events, last 15m
~~~

unless the data source genuinely counts group-level events under a verified definition.

### 11.3. When a group has multiple replicas

Suppose:

~~~text
A rebalance-total: 12 -> 13
B rebalance-total:  7 ->  8
C rebalance-total:  4 ->  5

Total client increase: 3
The group may have experienced one rebalance involving A, B, and C.
~~~

A total of 3 makes sense when measuring **client participation work**, yet is wrong if presented as "three group rebalances."

## 12. How do you count true group rebalance events?

Kafka client metrics have no universal, exact transformation that derives unique group rebalance IDs by summing client counters.

If the operational requirement is "how many times did the group finish changing assignments," consider:

1. **Broker/coordinator logs or metrics** with group-level semantics appropriate for your Kafka version.
2. A centralized observation system ingesting state transitions tagged with group ID and timestamp, plus a verified correlation algorithm.
3. Controlled polling of Kafka Admin API/group-state observation, noting that polling can miss rapid rebalances between intervals.
4. An internal audit/rebalance event stream designed to emit one uniquely keyed group-level event if the app truly requires it.

Do not claim `max()` across client `rebalance-total` gives group rebalance count: clients restart at different times, members join/leave, and counter resets make `max()` semantically unstable.

For most systems, client-level rebalance participation rate + rebalance duration + consumer lag are enough to assess group stability, as long as dashboards clearly explain the semantics.

## 13. Designing a rebalance count dashboard

An operational dashboard should have at least three layers:

### 13.1. Group overview

- Group ID and service/environment.
- Current consumer member count.
- Assigned partitions count.
- Client-level rebalance rate over 5–15 minutes.
- Total consumer lag and max partition lag.
- Pod restarts/rollouts/HPA changes.

### 13.2. Per-consumer client details

- `rebalance-total` and `rebalance-rate-per-hour`.
- `rebalance-latency-avg` and `rebalance-latency-max` if available.
- Time since last rebalance.
- Assignment count, client ID, instance/pod.
- Heartbeat errors and coordinator request latency if available.

### 13.3. Business impact

- Listener throughput (records/sec).
- Processing latency p95/p99.
- Offset commit failures.
- Retry/redelivery counts.
- DLT volume.
- Database/HTTP downstream errors.
- SLOs: time to process, end-to-end latency, or backlog drain time.

Conceptual layout:

~~~text
Consumer group checkout-service
+-------------------------------------------------------+
| Client rebalance participation, 15m: 12 (estimated)   |
| Last rebalance: 40s ago (client-level)                |
| Current members: 4                                    |
+-------------------------------------------------------+
| Lag by partition          | Throughput / sec           |
| P0:  50                   | 120                        |
| P1: 800                   |  70                        |
+-------------------------------------------------------+
| Rebalance latency         | Commit errors              |
| avg/max                   | count/rate                 |
+-------------------------------------------------------+
| Timeline: deployments, HPA, restarts, broker events     |
+-------------------------------------------------------+
~~~

Numbers are illustrative to show presentation layout. Avoid merging client-level rebalance counts and group-level membership counts into one undefined value.

## 14. Alerting on rebalance count

### 14.1. Never alert on raw lifetime counters

Flawed interpretation:

~~~text
Alert when rebalance-total > 100
~~~

A long-running consumer accumulates counter increments even if recently very stable. A newly restarted client starts with a low counter even while rebalancing continuously.

Alert on **increase/rate over a time window** combined with impact.

Illustrative PromQL example, assuming metric name and labels actually exist:

~~~promql
sum by (application, group_id) (
  increase(kafka_consumer_coordinator_metrics_rebalance_total[15m])
) > 10
~~~

The threshold 10 per 15 minutes is an example and must be tuned to member counts, workload, and group baselines. Set suitable `for` durations and severities in Prometheus alert rules to prevent alert storms.

### 14.2. Combine with lag or throughput

A group experiencing several rebalances while still meeting its SLO has a different urgency from a group where rebalances cause throughput collapse and rising backlogs.

Alerting logic:

~~~text
Rebalance participation rises
             |
             +-- Consumer lag rises past SLO?
             |       |
             |       +-- Yes -> high priority
             |
             +-- Commit errors / retries rise?
             |       |
             |       +-- Yes -> check correctness/redelivery
             |
             +-- Coincides with deploy/autoscaling?
                     |
                     +-- Yes -> assess expected churn
~~~

An alert should include group, service, environment, time window, member count, and links to logs/lag dashboards.

### 14.3. Avoid one fixed threshold for all groups

A 2-member group has a different total client participation scale than a 200-member group. With many members, one group-level event creates many client increments.

You may consider a clearly defined internal metric like **client rebalance participation per active member**, provided the denominator reflects average members in the window and is documented as a normalization rather than "true rebalance passes."

### 14.4. Missing metrics do not equal 0 rebalances

If a pod dies, its `rebalance-total` series disappears. A dashboard plotting only live series can show an artificially low increase right when the system is most unstable.

Pair with:

- `up` or scrape health.
- Expected vs. actual consumer member counts.
- Pod restarts.
- Group lag.
- Assignment gaps.
- Metric series freshness.

## 15. Rebalance count vs. rebalance duration

Two systems can show very different profiles:

~~~text
Group A:
  Many short rebalances during deploy
  Lag rises slightly and drains quickly

Group B:
  Fewer rebalances
  Yet each lasts very long
  Lag spikes sharply and recovery is slow
~~~

Looking at count alone makes A look worse than B, even though real impact is the opposite.

A strong metric set includes:

- **Frequency**: rebalance count increase per window.
- **Duration**: average/max latency or percentiles when a suitable source exists.
- **Time spent unstable**: fraction of time the group spends joining/rebalancing, if measurable.
- **Business impact**: throughput, end-to-end latency, and consumer lag.
- **Correctness impact**: commit failures, redeliveries, and duplicate side effects.

If client metrics do not expose duration histograms, never infer p99 from `rebalance-latency-avg` or `rebalance-latency-max`. Computing percentiles requires a separate distribution source.

## 16. Eager vs. cooperative rebalancing affects counts

Kafka supports different assignment strategies, commonly described as:

- **Eager rebalance**: members may revoke many or all partitions before receiving new assignments.
- **Cooperative/incremental rebalance**: only partitions that need to move are revoked in steps, shrinking the disrupted workload.

When migrating from eager to cooperative:

- A single group-level change may follow a different callback sequence.
- Partition revocation counts may drop.
- Group-wide pause duration may shrink.
- Callback or iteration counts may still change depending on protocol.

Therefore, **do not compare raw `onPartitionsRevoked` callback counts before and after migration and call it a `rebalance-total` improvement**. Use consistent metric sources and compare lag/latency too.

### 16.1. Assignor compatibility

If members in the same group disagree on assignment strategies due to version/configuration differences, the group can hit join failures or churn. Check `partition.assignment.strategy` or the assignor mechanism for your group protocol.

Never switch assignors across all members at once without verifying migration paths; some upgrades require staged rollouts to preserve compatibility.

### 16.2. New consumer group protocol

When using `group.protocol=consumer`, membership and assignment shift to the new consumer group protocol with broker-driven coordination. Metrics and callback semantics may differ from the classic protocol depending on Kafka client/broker versions.

During migration, establish a new baseline for rebalance count/rate, inspect actual metrics, and avoid mixing two periods with different semantics to conclude instability merely from a changed number.

## 17. How do session timeouts push counts up?

In the classic protocol, the group coordinator monitors consumer heartbeats. If it receives no valid heartbeat for long enough, the member can be evicted and the group must reassign partitions.

Real causes:

- Broker coordinator unavailable.
- Prolonged JVM stop-the-world GC pauses.
- CPU throttling starving the heartbeat thread.
- Network partitions, DNS, or connection failures.
- Process crashes/OOMs.
- Sudden node or container kills.

Diagram:

~~~mermaid
flowchart TD
    A[Consumer processing] --> B[Heartbeat fails to reach coordinator]
    B --> C{Exceeds session timeout?}
    C -->|No| D[Wait for heartbeat recovery]
    C -->|Yes| E[Coordinator evicts member]
    E --> F[Group reassigns partitions]
    F --> G[Client rebalance metrics/callbacks change]
    G --> H[Consumer lag/commit failures may rise]
~~~

If rebalance counts climb alongside heartbeat errors, check network/coordinator/GC first. Raising session timeouts reduces false failures from brief hiccups while slowing detection of genuinely dead consumers.

Never assume session timeout is the root cause merely because a group has many rebalances. Look for evidence of liveness eviction rather than voluntary leaves during deployments.

## 18. Max poll interval and overly slow listeners

`max.poll.interval.ms` limits the interval between consumer polls. If listener processing runs too long, the consumer breaches the poll deadline and the group must update membership.

Example:

~~~text
max.poll.interval.ms = 300000  (5 minutes)

One poll returns 500 records
Each record takes ~ 800 ms

Approximate total processing:
  500 x 800 ms = 400000 ms (over 6 minutes)

Consumer fails to return to poll in time.
~~~

In modern classic consumer clients, the heartbeat thread can remain active while the listener is blocked. Thus this is not immediately a direct session timeout.

Mitigations to consider:

- Lower `max.poll.records` to bound worst-case work per poll.
- Optimize database I/O or process batches in suitable transactions.
- Enforce timeouts on HTTP/database calls.
- Cap blocking retries on the consumer thread.
- Tune concurrency to partition counts and downstream capacity.
- Raise `max.poll.interval.ms` only with concrete processing duration data and recovery SLOs.

### 18.1. Static membership

With a static member (`group.instance.id`), upon exceeding `max.poll.interval.ms` the consumer may stop sending heartbeats instead of immediately dropping assignment; the coordinator then waits for `session.timeout.ms` to reassign. Final logs may report session expiration even though the root cause was the listener failing to poll on time.

Always cross-check both thresholds and event timelines when rebalance counts spike.

## 19. How does static membership reduce rebalance churn?

Kafka static membership uses `group.instance.id` to keep a stable logical consumer member identity across brief restarts. This can cut unnecessary rebalances during short restarts when paired with an appropriate session timeout.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: checkout-service
      properties:
        group.instance.id: checkout-worker-slot-0
~~~

**Never duplicate the same static instance ID across multiple active consumers.** With Spring Kafka concurrency above 1, understand child consumer IDs and version suffixes so every static member gets a distinct valid identity.

Static membership does not guarantee zero rebalances:

- Scaling out members genuinely requires new assignments.
- A member down longer than session timeout is still evicted.
- Partition/subscription changes still require rebalancing.
- Group protocol/assignor migrations still affect assignments.

If you lower rebalance counts via static membership while setting `session.timeout.ms` too high, the group recovers very slowly when a consumer truly dies. Measure **time to recover partition ownership** alongside rebalance frequency.

## 20. Offset commit failures and data correctness

Rebalance count is not solely a performance metric; in several processing flows, it ties directly to **at-least-once delivery**.

~~~text
Consumer A polls offset 100
      |
      v
Listener updates database successfully
      |
      +-- Group rebalance occurs
      |
      v
A tries to commit offset 101 but lost ownership
      |
      v
Offset commit may fail
      |
      v
Consumer B gets partition, re-reads offset 100
~~~

If the application is not idempotent, the record can produce duplicate side effects. Rebalances do not delete records or make Kafka exactly-once; they change which consumer member owns a partition.

### 20.1. Metrics to cross-check

- Offset commit failures.
- Listener processing errors.
- Redelivery/retry attempts.
- DLT published counts/failure counts.
- Database unique conflicts/inbox duplicate counts.
- Consumer lag.
- Rebalance duration.
- Partition lost callbacks.

### 20.2. Idempotent consumers

For database side effects, use a stable event ID, unique inbox key, or business operation ID inside a database transaction spanning both the inbox write and domain update.

Kafka transactions can coordinate Kafka outputs and source offsets in consume–process–produce, yet do not automatically guarantee database/HTTP side effects run only once.

**Never alert on rebalance count alone while ignoring correctness signals.** A group with few rebalances can still lose data if offsets commit too early; a group rebalancing often yet idempotent can preserve correctness despite worse latency.

## 21. Rebalance count in Kubernetes

In Kubernetes, several environmental factors can push rebalance counts up:

### 21.1. Rolling deployments

When old pods leave the group and new pods join, assignment shifts are expected behavior. Dashboards should include deployment markers to separate planned churn from abnormal churn.

Do not mute all alerts during deployments; you still must verify the group stabilizes after rollout.

### 21.2. HPA flapping

If the Horizontal Pod Autoscaler repeatedly scales replicas up and down around a threshold, the consumer group joins and leaves continuously.

Remedies include HPA stabilization windows, tuned scaling behavior, CPU/lag baselines, and avoiding useless scaling beyond partition parallelism.

### 21.3. CPU throttling/GC

Pods starved of CPU or hitting long JVM GC pauses suffer heartbeat failures or poll deadline breaches. Rising rebalance counts alongside CPU throttling and JVM pauses point straight to resource limits.

### 21.4. Readiness and shutdown

Readiness is not consumer group membership. A pod can be marked not-ready while its Kafka consumer process stays alive and in the group, depending on app lifecycle.

Graceful shutdown must give listener containers time to stop per policy to reduce unexpected partition loss. Even clean stop/starts can shift assignments; "zero rebalance" is never guaranteed.

### 21.5. Duplicate client IDs or missing labels

If multiple pods export metrics with the same client ID and the exporter lacks instance/pod labels, series can merge or overwrite erroneously. Preserve **instance identity** in monitoring, especially across counter resets and scaling events.

## 22. Investigating sudden spikes in rebalance count

An ordered runbook:

1. Identify the exact metric: Kafka client `rebalance-total` vs. custom callback counter.
2. Identify group ID, service, environment, time range, and active member count.
3. Reconcile active series count against actual consumer count.
4. Check counter resets/restarts to rule out dashboard calculation bugs.
5. Check deployments, rollouts, HPA, manual scaling, and topic partition changes.
6. Search logs for join/leave group, member removed, coordinator discovery, and assignment events.
7. Check heartbeat failures, session timeouts, and network errors.
8. Check poll interval violations, listener duration p95/p99, batch size, and blocking retries.
9. Check JVM GC pauses, CPU throttling, OOMs/restarts.
10. Check broker coordinator health and metadata changes.
11. Cross-check rebalance latency, consumer lag, throughput, and commit failures.
12. Check idempotency/retries/DLT if redeliveries are evident.
13. Identify root cause, then change one configuration group at a time in a controlled manner.
14. After the change, re-measure using the exact same metric, grouping, and window.
15. Document the decision, SLA impact, and rollback criteria.

A quick triage tree:

~~~text
Rebalance count rising?
  |
  +-- Coincides with deploy/scale?
  |      -> Planned member churn or HPA flapping?
  |
  +-- Heartbeat/session errors?
  |      -> Network, coordinator, GC, CPU
  |
  +-- Max poll interval exceeded?
  |      -> Listener/batch/IO/retry too slow
  |
  +-- Unclear cause?
         -> Group protocol, assignor, metadata changes,
            client metrics labels/resets, coordinator logs
~~~

Never change session timeout, max poll interval, concurrency, and assignment strategy all at once: if counts drop, you will not know which change actually worked.

## 23. Is a high rebalance count always a bug?

No. For example:

- During a controlled deployment, the group rebalances a few times and stabilizes.
- When a consumer group first scales up, members join and receive assignments.
- When new topics or partitions are added, assignments must update.
- When a consumer genuinely dies, rebalancing is the **necessary recovery mechanism**, not a bug.

High rebalance counts become a problem when they:

- Repeat continuously outside expected changes.
- Keep the group unstable for a significant share of time.
- Cause lag to breach SLOs.
- Cause commit failures, redeliveries, and uncontrolled duplicate side effects.
- Cause partition ownership thrashing, constant cache warm-ups, or sharp throughput drops.

Therefore, dashboards should show **deployment timestamps** alongside rebalance charts. Never enforce a blanket "rebalance total > 0" alert across all production groups.

## 24. Strategies to reduce unnecessary rebalances

### 24.1. Fix liveness root causes

If session timeouts occur:

- Check broker availability and coordinator health.
- Fix networking, DNS, service endpoints, and connection stability.
- Reduce JVM pauses and CPU throttling.
- Tune session timeouts to real jitter and failover SLOs.

Never raise session timeouts infinitely; genuinely dead members will take longer to detect.

### 24.2. Keep poll loops on schedule

If max poll intervals trigger:

- Reduce work per poll or optimize processing.
- Enforce downstream timeouts.
- Avoid unbounded, long blocking retries.
- Bound queues/in-flight tasks and apply proper backpressure.
- Measure p99 listener processing, not just average.

### 24.3. Reduce membership churn

- Eliminate HPA flapping.
- Use consistent rolling update/shutdown lifecycles.
- Use static membership when requirements and ownership models fit.
- Avoid running pointless consumers beyond partition counts.
- Verify client/protocol/assignor compatibility during upgrades.

### 24.4. Cooperative rebalancing

Where systems and clients support it, cooperative assignment cuts partition revocation scope and pause time, especially in large groups.

However, cooperative rebalancing does not cure process crashes, GC freezes, or network partitions. It is an **assignment transition optimization**, not a fix for what causes rebalances.

### 24.5. Measure impact rather than blindly optimizing counts

A change might reduce rebalance counts while doubling crash recovery time. Evaluate all of:

- Failover time.
- Consumer lag and backlog drain time.
- Processing latency.
- Duplicate handling.
- Times the group actually goes unstable.
- Broker/coordinator load.

## 25. Testing rebalance count

Tests should use an isolated Kafka test cluster/group—never inject churn in production just to test metrics.

### 25.1. Stable baseline

1. Run a consumer group with a fixed number of members.
2. Wait for assignments to stabilize.
3. Collect Kafka client `rebalance-total` and `rebalance-rate-per-hour`.
4. Keep replicas, subscriptions, and partition counts unchanged.
5. Verify metrics grow minimally or stay flat absent real rebalance triggers.
6. Observe consumer lag and processing throughput.

### 25.2. Member join

1. Run the group with one member.
2. Record counters before adding a second member.
3. Start the second member.
4. Observe assignment shifts and client rebalance metrics.
5. Record how client counters increment.
6. Confirm you do not derive group rebalance count by summing client deltas.

### 25.3. Graceful leave

1. Run two members.
2. Stop one member via normal container lifecycle.
3. Observe the remaining group reassign partitions.
4. Record callbacks, lag, and rebalance latency.
5. Distinguish voluntary leave from session timeout.

### 25.4. Session timeout

1. In a test environment, simulate a member failing to heartbeat to the coordinator.
2. Wait for membership expiration.
3. Inspect broker/client logs and rebalance metrics.
4. Confirm partitions get reassigned.
5. Verify redelivery per committed offset and idempotency.

### 25.5. Max poll interval

1. Make a test listener run longer than `max.poll.interval.ms`.
2. Keep network/coordinator healthy to isolate the cause.
3. Observe poll interval logs and group membership changes.
4. Inspect counter changes on rebalance.
5. Reduce workload or adjust limits with justification, then re-measure.

### 25.6. Consumer restart and Prometheus counter reset

1. Collect several samples of `rebalance-total`.
2. Restart the consumer.
3. Confirm the new lifecycle's raw counter can be lower than before.
4. Verify PromQL `increase()`/`rate()` and instance/client labels.
5. Ensure dashboards do not misread resets as "negative rebalances" or improved stability.
6. Check for missing scrape samples while the process is down.

### 25.7. Cooperative vs. eager

1. Create test groups matching each assignor/protocol.
2. Have a member join/leave.
3. Record rebalance metrics, callbacks, and affected partitions.
4. Compare duration and backlog, not callback counts alone.
5. When migrating protocols/assignors, re-baseline after confirming semantics.

Do not run Content QA or code tests when the worker assignment is solely authoring STEP 4 Markdown; the scenarios above are testing knowledge for learners.

## 26. Common interpretation mistakes

**Summing `rebalance-total` across all consumers and calling it group event count:** one group pass can increment counters across many clients.

**Counting `onPartitionsAssigned` as official `rebalance-total`:** callback counts and client metrics are not equivalent.

**Treating large raw counters as incidents:** counters accumulate over lifetime; check recent rate and increase.

**Ignoring counter resets after restarts:** dashboards break when client IDs/instances change.

**Watching only one child consumer:** concurrent listener containers run multiple `KafkaConsumer` instances.

**Mixing group IDs:** one application's metrics may span multiple consumer groups.

**Not verifying exporter series names:** Prometheus names vary from examples depending on JMX exporter/Micrometer.

**Ignoring group protocol:** classic and consumer protocols differ in heartbeats/sessions, assignments, and metrics.

**Assuming cooperative means zero rebalances:** membership/assignment reconciliation still occurs on group changes.

**Calling post-deploy rebalance increases bugs:** they may be legitimate lifecycle transitions.

**Raising timeouts just to lower counts:** slows failover and masks resource issues.

**Overlooking `max.poll.interval.ms`:** slow listeners cause group churn even when heartbeats survive briefly.

**Overlooking pod restarts or HPA:** churn can come from the environment rather than Kafka brokers.

**Treating low rebalance count as guaranteeing exactly-once:** offset commits, retries, and idempotency are separate concerns.

**Omitting instance/client labels:** series can merge wrongly or lose counters when scaling.

**Using client metrics to infer unprocessed records:** rebalance count is not backlog; use consumer lag.

**Counting every partition in a revoke event as one group rebalance:** affected partition count is a different metric.

## 27. Standard monitoring rollout process

A rollout can follow these steps:

1. **Pick the right data sources:** Kafka consumer client metrics for rebalance counts; Spring rebalance callbacks for partition lifecycle; coordinator logs for group-level context.
2. **Verify live metrics:** list JMX/Actuator/Prometheus series for your active client version.
3. **Preserve distinguishing labels:** application, environment, group ID, client ID, and pod/instance.
4. **Use counter semantics:** compute `increase()` or `rate()`, handling resets and missing scrapes.
5. **Name dashboards honestly:** "client rebalance participation" when summing client counters.
6. **Add latency and impact:** rebalance latency, lag, throughput, commit failures, restarts.
7. **Overlay operational timelines:** deploys, HPA actions, topic changes, broker changes.
8. **Establish baselines:** normal levels per workload and member count.
9. **Alert on windows:** tie to SLO/impact conditions, not raw lifetime totals.
10. **Write runbooks:** separate member churn, heartbeat/session timeouts, poll intervals, and coordinator issues.
11. **Test with fault injection:** join/leave, restarts, timeouts, and metric resets.
12. **Review after migrations:** client versions, group protocols, assignors, and dashboard labels can change.

## 28. Conclusion

**Rebalance count** is an essential metric for tracking Kafka consumer group stability in Spring Kafka, yet it is only useful when you know **who is counting**: the `KafkaConsumer` client, Spring rebalance callbacks, or the broker/group coordinator.

In many deployments, Kafka client `rebalance-total` and `rebalance-rate-per-hour` are strong starting points. When viewing them in Prometheus, analyze increases/rates over time windows, account for counter resets across restarts, and never call summed client increments unique group rebalances. Cross-check with rebalance latency, consumer lag, offset commit errors, JVM/resource health, and deploy timelines to separate expected churn from incidents.

The operational goal is not forcing rebalance count to 0 at all costs. The goal is ensuring **consumer groups recover cleanly when membership changes, keep throughput/latency within SLOs, and prevent uncontrolled duplicate business side effects**.
