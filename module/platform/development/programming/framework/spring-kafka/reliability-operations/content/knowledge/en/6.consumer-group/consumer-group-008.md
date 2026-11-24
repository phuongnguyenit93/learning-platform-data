# Rebalancing When a Consumer Dies

In Kafka, a consumer group allows multiple consumers to share the work of reading a topic's partitions. When a consumer stops abruptly, loses connectivity, or fails to meet the group's liveliness requirements, Kafka must detect that the member is no longer available and redistribute its partitions to the remaining consumers. This redistribution process is called a **rebalance**.

Rebalancing enables the group to keep processing data after a member fails. However, it can pause reading, introduce latency, and cause some records to be redelivered. In Spring Kafka, the listener container manages the consumer lifecycle and coordinates with the Kafka group protocol; the application must configure sensible timeouts, handle offsets safely, and ensure side effects can execute again if needed.

## 1. What Happens When a Consumer Dies?

Each consumer in a group maintains membership with Kafka. Under the traditional group protocol, consumers send periodic heartbeats to the group coordinator to prove they are alive. The coordinator tracks the timestamp of the last heartbeat. If a member fails to send a heartbeat within the allowed window, the coordinator marks that member inactive and starts a group rebalance.

For example, topic `orders` has six partitions and group `billing-service` has three consumers:

```text
Before the failure:

  Consumer A  -> P0, P1
  Consumer B  -> P2, P3
  Consumer C  -> P4, P5

Consumer B stops abruptly

After the coordinator detects B has left the group:

  Consumer A  -> P0, P1, P2
  Consumer C  -> P3, P4, P5
```

Actual assignment depends on the partition assignor and remaining member count. The example above merely illustrates redistributing partitions from the lost consumer. If only one consumer remains in the group, it may receive all partitions; if partition load exceeds processing capacity, lag can grow even after the group stabilizes.

When a process or host crashes, the consumer typically cannot send a leave-group request. The coordinator must wait for the timeout mechanism to detect the disconnected member. During a controlled shutdown, the consumer can explicitly leave the group as it closes, allowing remaining members to start rebalancing sooner. Failure detection time therefore depends on the failure mode and group configuration.

## 2. Phases of a Rebalance

A rebalance typically involves the following steps:

1. **Detecting membership change:** the coordinator learns a member left the group, a new member joined, or another change requires partition redistribution.
2. **Revoking old assignments:** consumers learn which partitions are being revoked and perform necessary cleanup.
3. **Negotiating new assignments:** the group coordinator and partition assignor determine which member receives each partition.
4. **Assigning partitions:** consumers receive the new assignment and resume reading from their corresponding committed offsets.
5. **Resuming processing:** the listener container resumes polling, invoking listeners, and committing offsets per configuration.

During a rebalance, some consumers may temporarily pause processing. Disruption duration depends on the group protocol, assignor, partition count, member count, application callbacks, and state recovery time. Prolonged or continuous rebalances can make consumer lag climb rapidly.

Kafka has variants of the group protocol, and rebalance behavior varies by version. The traditional heartbeat and timeout descriptions below mainly cover the classic consumer group protocol. With newer consumer group protocols, certain heartbeat and session parameters are coordinated broker-side; verify your Kafka client/broker version and active configuration before applying specific values.

## 3. Eager Rebalance and Cooperative Rebalance

The partition assignor decides how partitions are divided among members. Two important rebalance styles are eager and cooperative.

### 3.1. Eager rebalance

With an eager protocol, when the group needs to rebalance, members revoke all currently assigned partitions and then wait for the new assignment. Even partitions that do not need to move to another consumer can be revoked and reassigned.

```text
Before:
  A: P0, P1
  B: P2, P3

Eager rebalance:
  A: revoke P0, P1
  B: revoke P2, P3
  group computes new assignment

After:
  A: P0, P2
  B: P1, P3
```

The advantage is a simple coordination model. The drawback is a potentially wider pause because all assignments are revoked, including partitions that end up back on the same consumer.

### 3.2. Cooperative rebalance

Cooperative rebalancing allows partitions to transfer incrementally. Consumers revoke only partitions that truly need to move; unchanged partitions can remain assigned. This reduces how much work must stop and can shorten disruptions when group membership changes.

For example, if only P2 needs to move from A to B, a cooperative assignor can ask A to revoke P2 first, then assign P2 to B in the next rebalance round. Partitions P0, P1, or P3 that do not need to move can continue being processed.

`CooperativeStickyAssignor` is a common Kafka client option supporting the cooperative protocol. When switching, ensure all members in the group use compatible assignor configurations; rolling upgrades across client versions must follow Kafka's compatibility guidelines. Do not switch assignors wholesale without verifying coordination across running instances.

| Characteristic | Eager | Cooperative |
|---|---|---|
| Revoked partitions | Typically revokes entire assignment | Only revokes partitions needing to move |
| Disruption | Can be broader | Typically narrows disruption scope |
| Partition transfer | Revoked and reassigned during the rebalance | May require multiple rounds to complete transfer |
| Compatibility requirements | Per configured assignor/protocol | Members must support cooperative protocol and compatible configs |

Cooperative rebalancing reduces assignment transition cost, yet it does not eliminate every pause or guarantee zero redeliveries. Offsets and side effects must still be managed safely.

## 4. How Kafka Detects an Inactive Consumer

In the classic group protocol, several key configurations govern failure detection timing.

### 4.1. `session.timeout.ms`

`session.timeout.ms` defines how long the coordinator waits for a heartbeat from a consumer before marking that member lost. If a consumer process is killed, a host loses power, or the network drops, the coordinator may have to wait until the session timeout expires before redistributing partitions.

A timeout that is too large delays failure detection. A timeout that is too small can cause healthy consumers to be evicted from the group during brief network blips, CPU saturation, or long JVM pauses. In that case, the group can rebalance continuously even though the application has not actually died.

### 4.2. `heartbeat.interval.ms`

Under the classic protocol, consumers send periodic heartbeats. `heartbeat.interval.ms` controls the interval between heartbeats; it is typically set substantially lower than `session.timeout.ms` so multiple heartbeat attempts occur before the session expires. A common starting guideline is keeping the heartbeat interval at no more than roughly one-third of the session timeout, while respecting broker limits and the configuration rules of your running version.

Successful heartbeats do not prove the listener is healthy in business processing. A consumer can keep heartbeating while its listener is blocked, processing very slowly, or waiting on an unresponsive downstream. You must also monitor `max.poll.interval.ms`, processing times, and lag.

### 4.3. `max.poll.interval.ms`

`max.poll.interval.ms` bounds the maximum time between `poll()` calls by a consumer. If the application receives a batch and takes too long processing it without calling `poll` again, Kafka may consider the consumer unable to make progress and remove it from the group.

For instance, with `max.poll.records=100` and each record taking 1 second on average, a single batch may take nearly 100 seconds—not counting database calls, retries, or GC. If `max.poll.interval.ms` is set lower than actual peak-load processing time, the consumer can be rebalanced even while the process is alive.

When using static membership with `group.instance.id`, behavior after exceeding `max.poll.interval.ms` can differ from dynamic members: the consumer stops heartbeating and partition revocation may wait until `session.timeout.ms`. Therefore, consider both timeouts together and do not assume exceeding max poll interval always triggers immediate redistribution.

### 4.4. Illustrative configurations

```properties
spring.kafka.consumer.properties[session.timeout.ms]=45000
spring.kafka.consumer.properties[heartbeat.interval.ms]=3000
spring.kafka.consumer.properties[max.poll.interval.ms]=300000
spring.kafka.consumer.properties[max.poll.records]=100
```

The values above are only examples for the classic protocol. They are not universally optimal settings. Measure batch processing times under peak load, downstream latency, GC pauses, and network conditions before choosing timeouts. If a listener takes a long time, lower `max.poll.records`, raise the allowed processing window, or design asynchronous processing with proper offset management.

## 5. How Does Spring Kafka Handle Rebalances?

In Spring Kafka, `ConcurrentMessageListenerContainer` or `KafkaMessageListenerContainer` manages the Kafka consumer and poll loop. When a consumer joins or leaves a group, the Kafka client runs the group protocol and the container receives the new partition assignment. The listener method only processes records once partitions are assigned to its consumer.

With `@KafkaListener`, concurrency can be configured so the container creates multiple consumers:

```java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        concurrency = "3")
public void handle(OrderCreated event) {
    billingService.applyIdempotently(event);
}
```

If the topic has six partitions, concurrency three can create three consumers in the group. If one consumer dies, Kafka distributes its partitions to the remaining consumers after detecting the lost member. Raising concurrency to six lets the group use up to six consumers in parallel across the six partitions, provided downstream resources can handle the load.

During a controlled shutdown, the listener container stops consumers via the Spring lifecycle. Allow sufficient shutdown time to finish in-flight records and perform required commits. When a process receives `kill -9` or a host loses power, there is no reliable shutdown callback; the design must accept the possibility of record redelivery.

Do not create multiple consumer groups for the same stream just to increase concurrency. Consumers meant to share load must use the same group ID; different group IDs receive independent copies of the data.

## 6. What Happens to In-Flight Records When Partitions Are Revoked?

This is the most critical point for preventing data loss or duplicate side effects. Suppose consumer B polled record offset `120`, began writing the result to a database, and then the process stopped before committing offset `121`.

```text
Consumer B:
  poll offset 120
       |
       v
  database update succeeds
       |
       X consumer dies before commit

Kafka detects B lost membership
       |
       v
Partition is assigned to consumer A
       |
       v
A reads from old committed offset: 120
       |
       v
Record 120 may be processed again
```

This is expected at-least-once behavior when commits occur only after successful processing. The application needs idempotency so reprocessing does not create duplicate payments, orders, or emails.

If the application commits offset `121` before the database transaction completes and the consumer dies, the new consumer resumes from `121`. The side effect of record `120` may be lost. Therefore, commit timing must follow the committed business completion point.

When using batches, remember that offset commits represent contiguous progress per partition. Do not commit past an incomplete record within the same partition. With asynchronous processing, track completion per partition and commit only the highest contiguous offset where all preceding records have completed.

## 7. Handling Partition Revoke and Lost

Kafka provides `ConsumerRebalanceListener` so applications receive callbacks when partitions are revoked or newly assigned. Key callbacks include:

- `onPartitionsRevoked`: partitions are about to be revoked during a normal rebalance. Can be used to stop new work on those partitions, flush local state, and safely save processed progress.
- `onPartitionsAssigned`: new partitions are assigned. Can be used to initialize state or restore local per-partition data.
- `onPartitionsLost`: on Kafka clients supporting this callback, partitions have already lost ownership before the consumer had a chance to run a normal revoke. Never assume the consumer still holds authority to commit offsets for those partitions.

With a raw Kafka consumer, callbacks can save processed offsets and release resources. In Spring Kafka, the listener container already manages commits according to the acknowledgment mode and error handler. If registering a custom rebalance callback via container properties, coordinate with the container's commit mechanism; avoid manually committing an offset past processing progress or competing with the container.

A revoke callback should execute quickly. Do not call external services or wait on long-running tasks because the callback runs on the consumer control thread and can prolong the rebalance. If large state must be flushed, design periodic checkpoints or keep state small so little work remains at revocation time.

Illustrative example of implementing the Kafka interface at the raw consumer level:

```java
ConsumerRebalanceListener rebalanceListener =
        new ConsumerRebalanceListener() {

    @Override
    public void onPartitionsRevoked(
            Collection<TopicPartition> partitions) {
        // Stop accepting new work for these partitions.
        // Commit offsets only for records that finished processing.
        // Flush local state within the allowed time limit.
    }

    @Override
    public void onPartitionsAssigned(
            Collection<TopicPartition> partitions) {
        // Initialize or restore state for the new assignment.
    }
};
```

This is a raw consumer API example to illustrate callbacks. When using `@KafkaListener`, let the listener container manage the consumer and use the extension points of your Spring Kafka version if rebalance hooks are needed. Never spin up a second Kafka consumer inside a listener just to receive callbacks.

On partition lost, never attempt to commit progress as if a normal revoke occurred. Another consumer may already own the partition. Stop incomplete side effects, release local state, and rely on idempotency when records are redelivered.

## 8. Static Membership and `group.instance.id`

By default, consumers join a group as dynamic members. When a process restarts, it leaves the group and rejoins with a new membership, which can trigger a rebalance. For workloads with stable instances, **static membership** lets you attach a persistent identity to a consumer via `group.instance.id`.

Configuration example:

```properties
spring.kafka.consumer.properties[group.instance.id]=billing-instance-0
```

Static membership can reduce unnecessary rebalances when an instance restarts briefly. The coordinator can retain membership for the duration of `session.timeout.ms` instead of immediately treating the member as gone. When the instance returns with the same identity, it can resume its prior membership per the protocol.

Constraints to keep in mind:

- Every active member in the same group must have a unique `group.instance.id`. Two processes simultaneously using the same ID can trigger duplicate-member errors.
- The ID should stay stable for the same logical instance across restarts, yet differ across replicas.
- In autoscaling environments or where replica identities change continuously, static membership requires careful design.
- If an instance truly dies, partitions may wait for `session.timeout.ms` before reassignment. Static membership can cut rebalances on brief restarts at the cost of slower failover if timeouts are too long.
- With listener concurrency greater than one, ensure each actual Kafka consumer gets a unique identity. How Spring Kafka suffixes instance IDs depends on version and configuration; verify rather than giving multiple consumers the exact same value.

Static membership does not replace heartbeats, poll intervals, idempotency, or monitoring. It only changes how the group recognizes members across leaves and rejoins.

## 9. Tuning to Balance Failure Detection and Group Stability

Do not set every timeout as low as possible just to rebalance faster. Short timeouts detect failures sooner, yet they also increase the risk of falsely evicting healthy consumers during GC pauses, CPU spikes, or unstable networks.

| Parameter | Impact | What to check when tuning |
|---|---|---|
| `session.timeout.ms` | Coordinator heartbeat wait window in the classic protocol | Dead-consumer detection latency, broker limits, heartbeats, and network stability |
| `heartbeat.interval.ms` | Heartbeat frequency in the classic protocol | Relationship to session timeout and network overhead |
| `max.poll.interval.ms` | Maximum time between polls | Batch processing time under peak load, synchronous retries, and GC pauses |
| `max.poll.records` | Maximum records returned per poll | Batch processing time, throughput, memory, and commit cadence |
| `partition.assignment.strategy` | Partition distribution and rebalance mode | Compatibility across members, partitions moved, and client version |
| `group.instance.id` | Enables static membership for stably identified members | Instance lifecycle, uniqueness, and acceptable failover duration |
| Listener `concurrency` | Consumer threads in the application | Partition count, CPU, database connection pool, and downstream capacity |

A controlled tuning approach:

1. Measure p95/p99 record and batch processing durations under realistic load.
2. Choose `max.poll.records` so batches finish comfortably within `max.poll.interval.ms` with headroom.
3. Measure consumer failure detection time in staging and compare it against your RTO.
4. Monitor rebalance rate, moved partitions, and lag during rolling deployments.
5. Enable cooperative assignors or static membership only after verifying compatibility and uniqueness.
6. Re-test process kills, network drops, rapid restarts, and slow downstreams after any major change.

Under the classic protocol, heartbeat interval is typically set much lower than session timeout. Under newer group protocols, some values may be broker-controlled; check the documentation for your deployed version to know which parameters actually take effect.

## 10. Illustrative Spring Boot Configuration

The example below shows a consumer group configuration for a synchronous listener. Tune values according to your processing speed, brokers, and recovery objectives.

```properties
spring.kafka.consumer.group-id=billing-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.properties[session.timeout.ms]=45000
spring.kafka.consumer.properties[heartbeat.interval.ms]=3000
spring.kafka.consumer.properties[max.poll.interval.ms]=300000
spring.kafka.consumer.properties[max.poll.records]=100
spring.kafka.listener.ack-mode=record
spring.kafka.listener.concurrency=3
```

If using a cooperative sticky assignor, configure the corresponding client property, for example:

```properties
spring.kafka.consumer.properties[partition.assignment.strategy]=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Use this setting only when all consumers in the group and your Kafka client version support the cooperative protocol compatibly. During rolling upgrades, follow Kafka's supported assignor migration procedure.

If using static membership, configure `group.instance.id` per logical consumer and ensure no collisions across active members. With multiple replicas running the same configuration, never hard-code the same ID for every instance.

## 11. Graceful Shutdown and Rolling Deployments

Controlled shutdowns let consumers leave the group cleanly and give the listener container a chance to finish in-flight work. When rolling out a new version, avoid stopping too many consumers in the same group simultaneously, as that reduces processing capacity and triggers multiple rebalances.

Operational best practices:

- Use rolling deployments with a controlled limit on concurrently stopping instances.
- Set a termination grace period long enough for the container to stop listeners and finish work within defined bounds.
- Never commit offsets before business side effects finish.
- Stop accepting new work once shutdown begins and let the container manage consumer lifecycles.
- Monitor rebalances, lag, and processing rates throughout the rollout.
- Keep a rollback plan ready if the new version causes exceptions, slow processing, or continuous rebalances.

If the platform sends a stop signal and kills the process after the grace period expires, in-flight work can still be interrupted. Therefore, idempotency remains essential even with graceful shutdown.

## 12. Investigating Continuous Rebalance Incidents

Continuous rebalances (a rebalance storm) usually indicate members cannot maintain stable liveness or configurations mismatch processing durations. Do not simply raise `session.timeout.ms` without identifying the root cause.

| Symptom | Possible cause | Investigation direction |
|---|---|---|
| Consumers repeatedly leave and rejoin the group | Process restarts, crash loops, overly aggressive liveness probes | Check application logs, exit codes, orchestration events, and rollout history |
| Rebalances after long-running batches | Exceeding `max.poll.interval.ms` | Measure batch duration, lower `max.poll.records`, or tune the interval carefully |
| Consumers evicted during flaky networking | Heartbeats fail to reach coordinator within session timeout | Check packet loss, DNS, broker load, CPU, and GC pauses |
| Group is stable yet lag climbs | Consumer throughput trails ingress rate or slow downstream | Compare processing rate, input rate, partition skew, and dependency latency |
| Prolonged rebalances after adding replicas | Many members/partitions, slow revoke callbacks, or complex assignments | Measure callback duration, moved partition counts, and active assignor |
| Static member dies yet partitions are not reassigned | Coordinator waiting out `session.timeout.ms` | Verify heartbeats and session timeout; evaluate static membership trade-off |
| One partition processes much slower than others | Skewed keys or one stalled consumer | Inspect per-partition lag, record sizes, key distribution, and downstream per thread |

When investigating, collect group coordinator logs, consumer logs, container lifecycle events, and metrics over the same time window. Record timestamps for when the process died, when the coordinator detected the lost member, when the rebalance began, when assignment completed, and when the consumer processed its first resumed record. These milestones reveal whether time was spent in detection, coordination, or listener startup.

## 13. Chaos Testing Consumer Failures and Verifying Recovery

A failure-testing suite should simulate multiple failure modes because graceful shutdown and process crashes behave differently.

### Scenario A: controlled stop of one consumer

1. Start the group with multiple consumers and steady load.
2. Record assignments, committed offsets, lag, and processing rates.
3. Stop one instance through its normal lifecycle.
4. Observe the member leaving the group and partitions redistributing.
5. Verify remaining consumers continue processing and lag stays within SLO.

### Scenario B: abrupt process kill

1. Restart the group with the same configuration and test load.
2. Kill one consumer without running graceful shutdown.
3. Record the elapsed time from process death until the coordinator detects the lost member.
4. Observe the rebalance and new assignment.
5. Verify uncommitted records are redelivered without producing duplicate side effects.

### Scenario C: consumer stays alive but processes too slowly

1. Inject a record that makes the listener run longer than expected or simulate a downstream timeout.
2. Observe poll intervals, heartbeats, and rebalances.
3. Check whether the consumer exceeds `max.poll.interval.ms`.
4. Tune batch size, timeouts, or processing design so the group remains stable.

### Recovery criteria

After each drill, verify:

- The group returns to a stable state with the expected member count.
- All required partitions are assigned.
- Committed offsets resume advancing and lag drains at the expected rate.
- Uncommitted records are redelivered safely.
- No records are skipped due to premature commits.
- Side effects are not duplicated thanks to idempotency or deduplication.
- Detection time and recovery time meet the defined RTO target.

Record detection duration, rebalance duration, time until processing resumes, backlog size, and any business discrepancies. If RTO is missed, determine whether the bottleneck was timeout delay, rebalance coordination, startup time, dependencies, or post-failover throughput.

## 14. Operational Principles to Maintain

1. A consumer dying does not mean partitions are reassigned instantaneously; the coordinator must detect the lost member via the group protocol.
2. Choose `session.timeout.ms`, `heartbeat.interval.ms`, and `max.poll.interval.ms` based on real load data and your Kafka version.
3. Use cooperative rebalancing once the entire group supports it and assignor rollout is controlled.
4. Enable static membership only when stable, unique identities exist for every real consumer and failover latency trade-offs are accepted.
5. Let the Spring Kafka listener container manage consumer lifecycles and commits per the selected acknowledgment mode.
6. When partitions are revoked, save only completed progress; when partitions are lost, never assume commit authority remains.
7. Design idempotent listeners because records can be redelivered after crashes or rebalances.
8. Monitor rebalance rates, per-partition lag, processing times, commit errors, and recovery times.
9. Use graceful shutdown and rolling deployments to curb unnecessary rebalances, while still preparing for sudden crashes.
10. Drill process kills, network drops, slow processing, and fast restarts to measure actual RTO.

Rebalancing is the mechanism that keeps a consumer group operational when membership changes. System reliability depends on timely failure detection, stable partition redistribution, committing offsets only after processing finishes, and ensuring redelivered records do not duplicate business effects.
