# Continuous Consumer Group Rebalancing

## 1. Symptoms and Impact

Consumer group rebalancing is the process by which Kafka redistributes partitions among consumers belonging to the same group. A brief rebalance when a new consumer joins, a consumer leaves, or a topic changes is normal behavior.

The problem arises when a group continuously cycles through preparing to rebalance, syncing assignments, and brief steady operation. During a rebalance, some or all consumers may temporarily stop receiving records depending on the assignment protocol. Common consequences include:

- Listeners slow down or pause receiving records for short intervals.
- Consumer lag rises even when message volume changes little.
- Partitions repeatedly switch owners, resetting local caches and in-flight processing state.
- Offsets may be reprocessed if records ran without their offsets being committed.
- Throughput drops, latency climbs, and retries can increase.
- Logs repeatedly show `Revoking previously assigned partitions`, `Adding newly assigned partitions`, `Preparing to rebalance`, or `Rebalance in progress`.

Not every rebalance log indicates a bug. Determine whether the group stabilizes after a deployment or scaling event, or keeps rebalancing under steady-state load.

## 2. How Does Rebalancing Work?

For consumer groups using group management, the Kafka coordinator tracks members and determines partition assignments. Whenever membership or subscriptions change, the group must recompute assignments.

```text
Consumer A             Group Coordinator             Consumer B
    |                          |                          |
    |--- JoinGroup ----------->|                          |
    |                          |<---------- JoinGroup -----|
    |                          |                          |
    |<------ assignment / SyncGroup ----------------------|
    |                          |                          |
    |==== A processes partition 0 | B processes partition 1 ====|
    |                          |                          |
    |--- A leaves group ------>|                          |
    |                          |                          |
    |<------ rebalance / new assignment ------------------|
    |                          |                          |
    |==== B also takes partition 0 ===========================|
```

In eager rebalancing, members typically revoke prior assignments before receiving new ones. Cooperative rebalancing only revokes partitions that actually need to move, reducing disruption. Kafka 4.0 also introduces a new consumer group protocol with broker-driven incremental assignment.

Rebalancing does not delete records. Records stay in the Kafka log; what matters is partition ownership and offset commits to avoid duplicate processing or skipped records caused by improper application commits.

## 3. Common Causes

| Cause group | Signs | First place to investigate |
|---|---|---|
| Listener takes too long | Rebalance appears after a poll with many records or slow DB/HTTP calls | Measure processing time and `max.poll.interval.ms` |
| Missed heartbeats | Consumer removed after GC pause, CPU starvation, network blip, or broker misses heartbeats | Check session timeout, heartbeats, JVM, and network |
| Repeated pod/process restarts | Rebalances coincide with rollouts, liveness probes, or autoscaling | Check restart history and deployment events |
| Duplicate consumer instance IDs | Static members fenced or continuously replacing each other | Check `group.instance.id` on each instance |
| Concurrency/replica churn | Members and assignments shift alongside replica counts or listener containers | Compare consumer count against partitions and deployment config |
| Topic subscription changes | Group rebalances after adding partitions or pattern-matched topics | Check metadata, topic patterns, and partition counts |
| Coordinator/broker/network instability | Multiple consumers or groups hit coordinator/disconnect errors together | Check broker logs, coordinator, and network |
| Retry/backoff blocks polling | Rebalance happens during downstream failures or long retry delays | Inspect error handler and backoff strategy |
| Incompatible rebalance protocol/assignor | Members fail to agree on assignor or protocol | Check Kafka client version, `group.protocol`, and assignors |

Pick the cause based on timestamps, member IDs, client IDs, and correlated logs. Do not immediately raise timeouts when seeing rebalances; that can mask the root cause and delay detecting dead consumers.

## 4. Distinguishing `max.poll.interval.ms`, `session.timeout.ms`, and Heartbeats

These three settings are often confused in consumer groups using the classic protocol.

| Setting | What does it control? | When does a rebalance occur? |
|---|---|---|
| `max.poll.interval.ms` | Maximum time between two `poll()` calls | Consumer fails to call `poll()` in time, usually due to slow record/batch processing |
| `session.timeout.ms` | Time coordinator waits for heartbeats before marking a member dead | Broker receives no heartbeat within session timeout |
| `heartbeat.interval.ms` | Frequency at which the consumer sends heartbeats in the classic protocol | Not record processing time; must be lower than session timeout |

In the classic protocol, heartbeats run independently of listener execution. Thus, a consumer can keep sending heartbeats while the listener runs, yet if it fails to call `poll()` before `max.poll.interval.ms`, Kafka still considers the consumer stalled and triggers a rebalance.

For example, `max.poll.interval.ms = 300000` equals 5 minutes. If a poll returns 100 records and the listener averages 4 seconds per record, total processing time can exceed 5 minutes even though each individual record seems fast.

With the new Kafka consumer protocol (`group.protocol=consumer`), heartbeat interval and session timeout are controlled on the broker side. Client properties `heartbeat.interval.ms` and `session.timeout.ms` are no longer used the classic way; check broker settings `group.consumer.heartbeat.interval.ms` and `group.consumer.session.timeout.ms`.

## 5. Diagnosing Slow Listener Processing

With record listeners, Spring Kafka invokes the listener on the consumer thread. Records returned by a single `poll()` are passed to the listener; the consumer polls again after the container finishes processing that poll. With batch listeners, the listener processes the entire batch before returning to poll.

Estimating poll processing time:

\[
T_{poll} \approx N \times T_{record} + T_{overhead}
\]

Where:

- `N` is the maximum records returned per poll, capped by `max.poll.records`.
- `T_record` is per-record processing time; use p95/p99 rather than average alone.
- `T_overhead` covers commits, retries, extra serialization, logging, and scheduling.

Keep `T_poll` below `max.poll.interval.ms` with a healthy safety margin. If p99 approaches the timeout, one slow database call or JVM pause can evict the consumer from the group.

### Example Configuration Reducing Records Per Poll

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      properties:
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 50
```

The current Kafka client default for `max.poll.records` is 500. Lowering it to 50 trims per-poll processing time, though it also reduces records fetched per iteration and can lower throughput if per-record work is very fast. Measure before and after changing it.

`max.poll.records` caps records returned from a single `poll()`; it does not directly cap how much data the broker fetches into the consumer. The consumer may cache fetched data and hand it out across subsequent polls.

### Optimizing Listener Processing

- Measure processing time per listener and business operation.
- Put timeouts on HTTP/database calls so a single record cannot block the consumer indefinitely.
- Avoid `Thread.sleep()` or unbounded Future waits inside listeners.
- Use batch database operations when suitable to cut round-trips.
- Reduce large payload logging or unnecessary serialization.
- Offload slow tasks to dedicated workflows if business design allows.
- If processing asynchronously, design explicit acknowledgment, retries, and backpressure; never return from the listener before work is safely secured and assume offsets reflect completion.

## 6. Timeout Configuration for Classic Protocol

Example Spring Boot configuration using the Kafka classic group protocol:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      properties:
        "[group.protocol]": classic
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 50
        "[session.timeout.ms]": 45000
        "[heartbeat.interval.ms]": 3000
```

These values are an illustrative starting point, not a universal template. `heartbeat.interval.ms` is typically no more than one-third of `session.timeout.ms`. The broker also bounds session timeouts via `group.min.session.timeout.ms` and `group.max.session.timeout.ms`.

Do not increase `session.timeout.ms` to fix slow listeners hitting `max.poll.interval.ms`. The two timeouts guard different conditions. If a listener takes 8 minutes to process a poll, bumping session timeout to 2 minutes still fails when the 5-minute poll interval expires.

## 7. New Kafka Consumer Protocol and KIP-848

Spring for Apache Kafka 4.0 supports Apache Kafka 4.0's new consumer group protocol. It can be enabled with:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.protocol]": consumer
```

The new protocol uses server-side incremental assignment, reducing disruption when group membership changes. Ensure broker, Kafka client, and Spring Kafka compatibility before enabling it.

When using the new protocol:

- The broker controls heartbeat interval and session timeout via `group.consumer.heartbeat.interval.ms` and `group.consumer.session.timeout.ms`.
- Client-side `heartbeat.interval.ms` and `session.timeout.ms` are not supported in the classic sense.
- Partition assignment runs server-side; custom client assignors in `partition.assignment.strategy` are ignored.
- `onPartitionsAssigned()` may be called multiple times with smaller partition sets due to incremental assignment.
- `ConsumerAwareRebalanceListener` continues to work with the new protocol.

Do not flip a running consumer group to the new protocol with a single config change without checking compatibility and rollout procedures. First confirm broker/client versions, server assignors, and compatibility across all group members.

## 8. Cooperative Rebalancing with Classic Protocol

If still using the classic protocol, consider `CooperativeStickyAssignor` to reduce partitions revoked during group changes:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.protocol]": classic
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Cooperative assignment keeps unaffected partitions assigned and only revokes partitions that must move. It reduces the impact of a rebalance, yet it does not stop rebalances caused by consumers repeatedly leaving the group, exceeding poll limits, or losing heartbeats.

All group members must support and agree on the cooperative protocol. Do not roll out incompatible assignors across running instance versions. Current Kafka clients may default to both `RangeAssignor` and `CooperativeStickyAssignor` to support rolling migrations; when configuring a single assignor explicitly, plan a coordinated rollout.

## 9. Static Membership and `group.instance.id`

By default, consumers join groups as dynamic members. When a process restarts, the group can rebalance to redistribute partitions.

Static membership assigns a unique `group.instance.id` to each consumer instance. If a process stops briefly and restarts within session timeout, Kafka can preserve its membership to minimize rebalances from short restarts.

Example configuration:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.instance.id]": ${KAFKA_INSTANCE_ID}
        "[session.timeout.ms]": 60000
```

This example assumes the classic group protocol. With `group.protocol=consumer`, session timeout is configured on the broker via `group.consumer.session.timeout.ms`, not via the consumer client property `session.timeout.ms`.

`KAFKA_INSTANCE_ID` must be distinct across processes in the same group. With Kubernetes StatefulSets, stable pod ordinals/identities work well. With autoscaling Deployments, assign a stable, unique ID per pod; never reuse the same fixed string across all replicas.

Spring Kafka supports static membership when concurrency is greater than 1; the container appends a suffix per child consumer. Even so, each application instance's base ID must still be unique across pods.

Notes:

- Two consumers sharing the same `group.instance.id` conflict; the older member can get fenced.
- Long session timeouts delay Kafka's detection of a genuinely dead static member.
- If a static member exceeds `max.poll.interval.ms`, the consumer stops sending heartbeats and partitions are reassigned only after session timeout expires, slowing recovery.
- Static membership reduces rebalances from short restarts; it does not cure listeners exceeding `max.poll.interval.ms`.
- Do not enable static membership unless you can manage unique identities and instance lifecycles.

## 10. Checking Concurrency and Partition Count

In Spring Kafka, `ConcurrentMessageListenerContainer` spawns multiple child `KafkaMessageListenerContainer` instances, each owning a consumer. `concurrency` controls how many consumers one listener container creates.

Example:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
```

If a topic has 3 partitions, concurrency 3 can utilize all three consumers. If concurrency is 6 on a 3-partition topic, at most 3 consumers receive partitions; the rest have nothing to process.

Changing concurrency or pod count in the same group alters membership and normally triggers a rebalance. That is expected during scaling. If pod counts oscillate rapidly due to an autoscaler or liveness probes, the group may never settle.

Check:

- Topic partition count.
- Child consumer count from listener container `concurrency`.
- Service replica count.
- Actual member count in the group.
- Partitions assigned to each member.

Do not raise concurrency past partition count expecting higher throughput. Idle consumers do not cause continuous rebalances by themselves, yet they increase member counts and operational complexity during deployments or scaling.

## 11. Checking Restarts, Deployments, and Health Probes

Rebalances often spike during:

- Rolling deployments replacing multiple pods.
- Liveness probes restarting applications because health endpoints misrepresent consumer state.
- Readiness/lifecycle hooks repeatedly stopping/starting listener containers.
- Autoscalers scaling up/down rapidly on short load spikes.
- JVM OOM kills, CPU throttling, or long GC pauses.
- Containers being killed before listener containers shut down gracefully.

Correlate timestamps of `ConsumerStartedEvent`, `ConsumerStoppedEvent`, pod restart counts, deployment rollouts, and rebalance logs. If rebalances happen only once per rollout, that can be normal behavior.

With Kubernetes:

- Set a termination grace period long enough for the app to stop listener containers and close consumers.
- Align preStop/lifecycle hooks with the application shutdown sequence.
- Avoid liveness probes restarting the service merely because Kafka temporarily disconnects or a downstream dependency slows down.
- Separate readiness (ability to take new traffic) from liveness (process alive).
- Tune rollout `maxUnavailable`/`maxSurge` to avoid replacing too many consumers simultaneously.
- Monitor CPU throttling, memory pressure, `OOMKilled`, and GC pauses.

Do not keep an unhealthy pod alive just to avoid a rebalance. Fix the health probe root cause and ensure controlled shutdowns.

## 12. Checking Network and Group Coordinator

If consumers lose connectivity to brokers or the coordinator, heartbeat/join requests can fail and group membership changes.

Check:

- DNS resolution and broker `advertised.listeners`.
- Packet loss, network latency, connection resets, and firewall idle timeouts.
- Whether the coordinator broker is restarting or transferring leadership repeatedly.
- Broker CPU, heap, request queues, and networking.
- Logs for `NotCoordinator`, `CoordinatorNotAvailable`, `DisconnectException`, `TimeoutException`, or authentication/authorization errors.
- Whether multiple groups are affected together or only one group.

If multiple groups on the same cluster destabilize simultaneously, investigate the broker/coordinator/network before tweaking individual consumer settings. If only one group is affected, focus on that group's members, listeners, and configuration.

Do not inflate reconnect timeouts or set infinite retries to hide coordinator failures. Identify which broker is the coordinator, which broker the client connects to, and which requests time out.

## 13. Rebalances Caused by Retries and Backoff Blocking the Consumer Thread

When a listener throws an exception, Spring Kafka's error handler can retry the record per `BackOff`. `DefaultErrorHandler` uses a backoff handler that waits on the processing thread by default. If wait time plus processing exceeds `max.poll.interval.ms`, the consumer can trigger a rebalance.

Since Spring Kafka 2.9, `ContainerPausingBackOffHandler` can pause the listener container during backoff and resume afterward. The container keeps polling in paused mode to preserve group membership. Timing precision depends on `pollTimeout`.

Conceptual configuration example:

```java
@Bean
ListenerContainerPauseService listenerContainerPauseService(
        ListenerContainerRegistry registry,
        TaskScheduler taskScheduler) {

    return new ListenerContainerPauseService(registry, taskScheduler);
}

@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> template,
        ListenerContainerPauseService pauseService) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(30_000L, 2L),
            new ContainerPausingBackOffHandler(pauseService));
}
```

This example builds `ListenerContainerPauseService` from `ListenerContainerRegistry` and `TaskScheduler`, then passes it into `ContainerPausingBackOffHandler`. Ensure the application provides a `TaskScheduler` bean. Check exact constructors and APIs against your project's Spring Kafka version.

For long retry delays or isolating retries from the main flow, consider non-blocking retry topics (`@RetryableTopic`). This brings trade-offs in ordering, operational topics, and processing semantics; design around business needs.

Never call `Thread.sleep()` directly inside a listener to retry. Doing so stalls the poll loop, complicates offset management, and easily triggers rebalances.

## 14. Observing Rebalances with `ConsumerAwareRebalanceListener`

Spring Kafka lets you install a `ConsumerRebalanceListener` through `ContainerProperties`. `ConsumerAwareRebalanceListener` provides callbacks before/after commits when partitions are revoked, when partitions are assigned, and when partitions are lost.

```java
@Bean
ConsumerAwareRebalanceListener orderRebalanceListener() {
    return new ConsumerAwareRebalanceListener() {

        @Override
        public void onPartitionsRevokedBeforeCommit(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            log.info("Partitions revoked before commit: {}", partitions);
        }

        @Override
        public void onPartitionsRevokedAfterCommit(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            log.info("Partitions revoked after commit: {}", partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            log.info("Partitions assigned: {}", partitions);
        }

        @Override
        public void onPartitionsLost(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            log.warn("Partitions lost: {}", partitions);
        }
    };
}
```

Attach the listener to the factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        ConsumerAwareRebalanceListener orderRebalanceListener) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setConsumerRebalanceListener(orderRebalanceListener);
    return factory;
}
```

`onPartitionsRevokedBeforeCommit()` runs right before the container commits pending offsets. `onPartitionsRevokedAfterCommit()` runs after commit. `onPartitionsLost()` (since Spring Kafka 2.4) signals lost partition ownership; do not call `onPartitionsRevoked()` from this callback because the container may handle revocation itself afterward.

Keep callbacks brief and avoid slow HTTP/database calls. Callbacks run on the consumer thread; slow work here can also destabilize the group. Do not commit offsets manually or alter consumer position inside callbacks when the container manages offsets, unless your application uses a manual design with clear semantics.

With the new consumer protocol, `onPartitionsAssigned()` may run multiple times with smaller partition subsets due to incremental assignment. Do not assume the callback executes only once for the entire assignment.

## 15. Monitoring Stalled Polls with Spring Application Events

Spring Kafka emits `NonResponsiveConsumerEvent` when a consumer appears stuck inside `poll()`. This differs from `ListenerContainerIdleEvent`: an idle event merely reports no messages arrived within the configured window; it does not mean the consumer is hung.

You can configure monitoring on the listener container:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setMonitorInterval(30);
    factory.getContainerProperties().setNoPollThreshold(3.0);
    factory.getContainerProperties().setPollTimeout(5_000L);
    return factory;
}
```

`monitorInterval` is in seconds and defaults to 30; `noPollThreshold` defaults to 3.0; `pollTimeout` is in milliseconds. The event fires when the consumer appears not to return from `poll()` within the matching threshold. Keep `noPollThreshold` above 1.0 to avoid false alarms from race conditions.

You can listen for the event:

```java
@Component
public class KafkaConsumerDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerDiagnostics.class);

    @EventListener
    public void onNonResponsiveConsumer(NonResponsiveConsumerEvent event) {
        log.error(
                "Kafka consumer not responsive: listenerId={}, timeSinceLastPoll={} ms, partitions={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll(),
                event.getTopicPartitions());
    }
}
```

The event provides container/listener ID, elapsed time since the last poll, and involved partitions. Use it to trigger investigation. Do not auto-restart containers on a single event; inspect poll threads, broker connectivity, and application health first.

## 16. Inspecting Consumer Group State via CLI

Use `kafka-consumer-groups.sh` to inspect group state, members, and partition assignments. Example on Linux/macOS:

```bash
# Inspect group state and member count
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-service --state

# List consumer members
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-service --members

# View partitions assigned to each member
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-service --members --verbose

# View offsets and lag by topic-partition
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-service
```

On Windows, run `bin\windows\kafka-consumer-groups.bat` with the matching arguments.

Interpreting results:

- `STATE=Stable` with unchanged members/assignments across multiple checks: the group is stable.
- Member count rising/falling repeatedly: processes/pods are joining or leaving continuously.
- Assignments shifting continuously: partition ownership is being redistributed.
- Members present with `#PARTITIONS=0`: consumer currently holds no partitions, possibly because member count exceeds partitions or assignment is in progress.
- Rising lag coupled with high rebalance rates: consumers may be spending time recovering assignments instead of processing records.

Take snapshots multiple times a few seconds apart to observe state transitions. A single snapshot cannot prove a group is rebalancing continuously.

## 17. Monitoring Consumer Metrics

The Kafka Java client exposes consumer metrics via JMX or `KafkaConsumer.metrics()`. Key metrics:

| Metric | Meaning | What to watch for |
|---|---|---|
| `time-between-poll-avg` | Average time between polls | Rises when listener processing is slow |
| `time-between-poll-max` | Maximum gap between polls | Approaching `max.poll.interval.ms` |
| `last-poll-seconds-ago` | Seconds since the most recent poll | Spikes abnormally when consumer is blocked |
| `poll-idle-ratio-avg` | Fraction of time the poll thread is idle | Sharp drop suggests processing consumes most time |
| `rebalance-total` | Total rebalances the consumer joined | Keeps climbing during steady state |
| `rebalance-rate-per-hour` | Hourly rebalance rate | Used to detect churn |
| `rebalance-latency-avg/max` | Rebalance duration | Rises when coordinator or assignment slows down |
| `failed-rebalance-total` | Count of failed rebalances | Rising count shows unstable join/sync |
| `last-rebalance-seconds-ago` | Seconds since last rebalance | Repeatedly resets low during group churn |
| `assigned-partitions` | Partitions currently owned by consumer | Drops to 0 or fluctuates continuously |

Do not look solely at absolute `rebalance-total`, as the counter grows over the process lifetime. Track rates and deltas over time, and correlate with member counts, poll latency, and application restarts.

## 18. Broker and Coordinator Metrics

Brokers also expose group coordinator metrics. With the classic group protocol, track group counts in states `PreparingRebalance`, `CompletingRebalance`, `Stable`, `Empty`, and `Dead`.

With the new consumer protocol, Kafka exposes group coordinator metrics such as:

- `consumer-group-count` across states `Empty`, `Assigning`, `Reconciling`, `Stable`, `Dead`.
- `consumer-group-rebalance-rate`.
- `consumer-group-rebalance-count`.
- `group-count` by protocol `classic`, `consumer`, or `streams`.

If coordinator metrics show multiple groups rebalancing together, inspect broker load and the group coordinator. If only one group shows climbing rebalance counts, investigate that group's members first.

## 19. Step-by-Step Investigation Workflow

1. **Identify the group:** capture `group.id`, topic, listener ID, start time, and rebalance frequency.
2. **Check group state:** run CLI `--state`, `--members`, and `--members --verbose` multiple times.
3. **Correlate member lifecycles:** compare client IDs, hosts, pod restarts, deployments, and consumer start/stop events.
4. **Check poll intervals:** inspect `time-between-poll-max`, `last-poll-seconds-ago`, and p95/p99 listener duration.
5. **Check heartbeats/sessions:** look for disconnects, heartbeat timeouts, network issues, and JVM pauses.
6. **Check processing load:** measure database/HTTP latency, retry delays, batch sizes, and `max.poll.records`.
7. **Check topology:** compare partition count, consumer concurrency, and replica count.
8. **Check identities:** confirm `group.instance.id` has no duplicates if using static membership.
9. **Check protocol:** confirm all members use compatible Kafka clients, assignors, and `group.protocol`.
10. **Check coordinator/brokers:** if multiple groups are impacted, inspect broker logs, coordinator, and network.
11. **Change one factor:** e.g., lower `max.poll.records` or optimize the listener, then monitor the rebalance rate again.
12. **Confirm stability:** group stays `Stable`, assignments stay steady, poll intervals have margin, and lag drops.

Never reset offsets to cure rebalancing. Resetting offsets changes read positions and can lose or reprocess data; it does not fix membership churn.

## 20. Symptom and Resolution Table

| Symptom | Likely cause | Action |
|---|---|---|
| Rebalance after every large batch | Batch processing exceeds `max.poll.interval.ms` | Lower `max.poll.records`, trim batch work, raise timeout after measuring |
| Rebalances coincide with slow DB | Listener blocks on database or HTTP | Set dependency timeouts, bulkheads, optimize queries, and bound retries |
| Rebalances coincide with rollouts | Dynamic members leave/join group | Controlled rolling deployments; consider static membership/cooperative assignor |
| Rebalances after GC pauses | Long JVM pauses delay heartbeats or polls | Analyze GC logs, heap, allocations, and pause times |
| `FencedInstanceIdException` | Multiple consumers share `group.instance.id` | Assign a unique ID per process/consumer |
| Group stuck in `PreparingRebalance` | Members joining/leaving or heartbeat/session timeouts | Inspect coordinator logs, member list, session timeouts, and restarts |
| Group `Stable` yet consumer lag climbs | Slow processing, hot partition, or insufficient throughput | Check per-partition lag and listener durations |
| Multiple groups rebalance together | Unstable broker/coordinator/network | Investigate brokers, network, and group coordinator |
| Rebalances during long retries | Backoff blocks consumer thread | Use `ContainerPausingBackOffHandler` or retry topics |
| Consumer created yet gets no partitions | Consumers exceed partitions or subscription mismatch | Check partition count, group ID, and topic subscription |
| Assignment callback runs multiple times | Cooperative/KIP-848 incremental assignment | Make callbacks idempotent; do not assume a single invocation |

## 21. Configurations You Should Not Change Arbitrarily

- **Do not raise `max.poll.interval.ms` indefinitely:** a hung listener keeps holding the group longer, slowing recovery.
- **Do not raise `session.timeout.ms` without measuring heartbeats:** detecting dead members takes longer.
- **Do not lower `heartbeat.interval.ms` too aggressively:** adds coordinator load without fixing slow listeners.
- **Do not enable static membership with duplicate IDs:** members will fence each other.
- **Do not swap assignors mid-fleet:** mismatched protocols across instances can fail assignment.
- **Do not raise concurrency past partition count expecting higher throughput:** extra consumers stay idle.
- **Do not invoke `Consumer` from another thread:** Kafka consumers are not thread-safe; let the listener container manage the consumer thread.
- **Do not run blocking work inside rebalance callbacks:** callbacks run on the consumer thread and prolong rebalances.
- **Do not disable commits or change `AckMode` just to quiet rebalance logs:** offset semantics must follow processing and transaction requirements.

## 22. Operational Checklist

- [ ] Group stabilizes after deployments and scaling events.
- [ ] `time-between-poll-max` stays well below `max.poll.interval.ms` with safety margin.
- [ ] Listener p99 and batch processing durations are measured.
- [ ] `max.poll.records` fits actual processing times.
- [ ] `session.timeout.ms` and heartbeats fit the classic protocol, or broker-side timeouts fit the consumer protocol.
- [ ] Consumer `group.instance.id` is unique when using static membership.
- [ ] Partition count supports required concurrency.
- [ ] Retries/backoff do not block the consumer thread past the poll interval.
- [ ] Broker coordinator and network show no abnormal disconnects.
- [ ] Rebalance rate, latency, and failed rebalances have dashboards/alerts.
- [ ] Consumer group CLI shows stable members and partition assignments.
- [ ] Rebalance listener callbacks perform no slow work or unintended manual commits.

## 23. Summary

- Rebalancing redistributes partitions; occasional rebalances when members or topics change are normal.
- Continuous rebalancing usually comes from member churn, slow listener processing, heartbeat timeouts, restarts, topic changes, or coordinator/network instability.
- `max.poll.interval.ms` limits time between `poll()` calls; `session.timeout.ms` and `heartbeat.interval.ms` govern heartbeats in the classic protocol.
- Lower `max.poll.records`, optimize listeners, and set dependency timeouts to cut per-poll processing time.
- Spring Kafka 2.9+ provides `ContainerPausingBackOffHandler` to handle long backoffs while keeping polls alive; retry topics handle long delays with ordering trade-offs.
- `CooperativeStickyAssignor` reduces revoked partitions; Kafka 4.0's consumer protocol supports incremental server-side assignment.
- Static membership cuts rebalances during brief restarts but requires unique `group.instance.id` values.
- `ConsumerAwareRebalanceListener`, `NonResponsiveConsumerEvent`, consumer metrics, and `kafka-consumer-groups.sh` help reveal root causes.
- Never reset offsets or raise timeouts blindly; correlate logs, metrics, member lifecycles, and processing durations before changing config.

When poll intervals, heartbeats, consumer membership, and partition assignments are monitored separately, operations teams can pinpoint exactly why a group keeps rebalancing. Fixing the real cause stabilizes assignments, lowers lag, and prevents needless record reprocessing.

## References

- [Apache Kafka — Consumer Configs](https://kafka.apache.org/41/configuration/consumer-configs/)
- [Apache Kafka — Monitoring](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka — Basic Kafka Operations](https://kafka.apache.org/43/operations/basic-kafka-operations/)
- [Spring Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka — Rebalancing Listeners](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/rebalance-listeners.html)
- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
- [Spring Kafka — Handling Exceptions and Backoff](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
