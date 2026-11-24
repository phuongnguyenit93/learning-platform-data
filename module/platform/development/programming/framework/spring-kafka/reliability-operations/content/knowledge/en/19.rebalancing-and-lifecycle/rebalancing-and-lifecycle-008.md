# Rebalance due to session timeout

## 1. What is a rebalance due to session timeout?

In Kafka, consumers belonging to the same **consumer group** share the partitions of subscribed topics. A Kafka broker acts as the group coordinator and tracks members through a heartbeat mechanism. If the coordinator does not receive a valid heartbeat from a consumer within the allowed time window, that member may be considered inactive and removed from the group. The partitions previously owned by this consumer must be redistributed: this is a **rebalance due to session timeout**.

With Spring Kafka, this can happen even when the `@KafkaListener` method does not throw an exception. The JVM may experience a long pause, network connectivity to the broker may become unstable, CPU may not allocate enough execution time, or the coordinator may not respond in time. After the session expires, Kafka must restore processing capacity by transferring partitions to other consumers.

Example topic `orders` with 4 partitions:

~~~text
Before incident:
  Consumer A -> orders-0, orders-1
  Consumer B -> orders-2, orders-3

Consumer A misses heartbeats long enough:
  Coordinator removes A from group
  Kafka performs rebalance

After incident:
  Consumer B -> orders-0, orders-1, orders-2, orders-3
~~~

A rebalance can lead to rising consumer lag, temporary processing pauses, failed offset commits, or redelivered records. It does not mean records disappeared from Kafka; the issue is that **partition ownership and processing progress** changed.

## 2. Consumer group and group coordinator

### 2.1. Consumer group

`group.id` identifies a group of consumers sharing consumption progress. Each partition is assigned to at most one consumer member in the same group at a time under a valid assignment. Different groups can read the same topic independently.

~~~text
Topic payments: P0 P1 P2 P3 P4 P5

Group payment-service:
  pod-a/consumer-0 -> P0, P1
  pod-b/consumer-0 -> P2, P3
  pod-c/consumer-0 -> P4, P5
~~~

When a consumer leaves the group or is no longer considered alive, the coordinator must redistribute the vacated partitions.

### 2.2. Coordinator tracks membership

The group coordinator is the broker responsible for managing group state. It coordinates join requests, heartbeats, and assignment updates depending on the group protocol. The coordinator cannot directly know whether database business logic inside `@KafkaListener` finished; it only evaluates group protocol signals.

Do not equate liveness with business progress. A consumer can send heartbeats normally while the listener processes very slowly. Conversely, a consumer that processes logic quickly yet loses connectivity to the coordinator can still time out.

### 2.3. Heartbeat

A heartbeat is a periodic signal sent by the consumer to the coordinator to maintain membership. In the **classic** consumer group protocol, common settings include:

- `session.timeout.ms`: time limit the coordinator waits for a heartbeat before considering the member inactive.
- `heartbeat.interval.ms`: cadence at which the consumer attempts to send heartbeats.
- `group.id`: the group the member joins.

Example:

~~~properties
group.id=payment-service
session.timeout.ms=30000
heartbeat.interval.ms=10000
~~~

The timeout window tolerates a few slow or temporarily failed heartbeats. A single failed heartbeat does not automatically mean the coordinator immediately evicts the member.

With the **new consumer group protocol** (when client and cluster support `group.protocol=consumer`), session and heartbeat settings may be governed by the broker via corresponding parameters, such as `group.consumer.session.timeout.ms` and `group.consumer.heartbeat.interval.ms`. Therefore, determine the effective protocol before tuning timeouts.

## 3. Session timeout differs from max.poll.interval.ms

This is the most important distinction when investigating a consumer losing partitions.

| Criterion | Session timeout | Max poll interval |
|---|---|---|
| Question | Is the coordinator still receiving heartbeats/liveness? | Is the application continuing to call `poll()` on time? |
| Classic config | `session.timeout.ms` | `max.poll.interval.ms` |
| Common causes | Network failures, JVM pauses, dead process, unavailable coordinator | Slow listener processing, overly large batches, blocking operations |
| Impact | Member's session expires and it is removed from the group | Consumer may leave group or stop heartbeating depending on membership/protocol |
| Investigation direction | Heartbeat, coordinator, network, GC, CPU | Processing time, poll cycle, batch, downstream |

### 3.1. A slow listener does not always cause session timeout

In modern Kafka clients using the classic group protocol, heartbeating is usually handled by a background thread after the consumer joins the group. Thus a blocked listener does not necessarily stop heartbeats immediately.

However, if the poll loop does not advance for longer than `max.poll.interval.ms`, the consumer violates the poll progress contract. With dynamic membership, the client may proactively leave the group. This case still causes a rebalance but **is not a pure session timeout**.

### 3.2. Static membership behaves differently

If a consumer has `group.instance.id` (static membership), upon exceeding `max.poll.interval.ms`, the client may stop sending heartbeats without immediately yielding the assignment. The coordinator usually waits for the session timeout before reassigning partitions. Hence an incident chain can look like:

~~~text
Listener blocked for a long time
       |
       v
Exceeds max.poll.interval.ms
       |
       v
Static member stops heartbeating
       |
       v
Session timeout
       |
       v
Coordinator reassigns partitions
~~~

Exact handling details depend on the Kafka version and group protocol. The key is not reading the final session timeout log line and ignoring the preceding poll interval cause.

### 3.3. Two timeline examples

Suppose configuration:

~~~text
session.timeout.ms    = 30000   (30 seconds)
heartbeat.interval.ms = 10000   (10 seconds)
max.poll.interval.ms  = 300000  (5 minutes)
~~~

**Scenario A:** Consumer loses connection to coordinator for 35 seconds even though the listener processes quickly. Session timeout can occur.

**Scenario B:** A batch listener takes 7 minutes to return, while network and JVM are normal. First investigate exceeding `max.poll.interval.ms`; do not conclude it is a heartbeat failure merely because the group rebalanced.

## 4. Timeline of a session timeout

Suppose the coordinator received Consumer A's last heartbeat and the session threshold is 30 seconds.

~~~text
T+00s  A sends heartbeat successfully; B stays active
T+03s  A loses connectivity to coordinator
T+10s  A's next heartbeat does not arrive
T+20s  Coordinator still receives no valid heartbeat from A
T+30s  A's session may expire
       Coordinator removes A from group
       Kafka changes assignment
T+35s  B takes over partitions previously belonging to A
T+40s  A recovers network and discovers old membership is invalid
       A must rejoin/reconcile with the group
~~~

Timestamps are illustrative. Reality depends on the last heartbeat, broker load, coordinator availability, protocol, and time for members to finish rebalancing.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant K as Group coordinator
    participant B as Consumer B
    A->>K: Heartbeat succeeds
    B->>K: Heartbeat succeeds
    Note over A,K: A's network is interrupted
    A-xK: Heartbeat fails
    B->>K: Normal heartbeat
    Note over K: A's session expires
    K->>K: Remove A from membership
    K-->>B: Group assignment changes
    B->>B: Receives additional partitions
    Note over A: Connectivity recovers
    A->>K: Continues with old state
    K-->>A: Generation or membership changed
    A->>K: Rejoin/reconcile group
~~~

Kafka only reassigns when the coordinator determines membership changed. A very brief network blip does not immediately move partitions.

## 5. Practical causes

### 5.1. Network interruptions

A consumer may fail to reach the coordinator due to DNS, routing, firewall, NAT, packet loss, or broker connection errors. An existing TCP connection does not guarantee heartbeat requests are answered on time.

Check network RTT, DNS errors, connection resets, broker discovery, and logs marking the coordinator unknown.

### 5.2. Long JVM pauses

A stop-the-world GC pauses Java threads, including the heartbeat thread. If the pause is too long, the coordinator's session may expire before the JVM resumes.

Measure pause duration, heap occupancy, allocation rate, and GC timestamps. One notable pause in logs can matter more than average CPU usage.

### 5.3. CPU throttling or starvation

In Kubernetes, overly low CPU limits or overloaded nodes can starve the JVM of time to run heartbeats on schedule. Multiple consumer threads, GC, and web traffic competing for CPU can amplify the problem.

Monitor container CPU throttling, host load, thread counts, OOM/restarts, and JVM execution pauses.

### 5.4. Unavailable group coordinator

The coordinator broker may restart, transfer leadership, endure heavy load, or temporarily lose connectivity. Consumers will rediscover the coordinator, but if the outage lasts long, group membership can be affected.

Correlate broker logs with client logs. If multiple consumer groups time out at the same time, suspect shared infrastructure before tuning individual listeners.

### 5.5. Process crash or abrupt kill

If a process is killed or a VM loses power, heartbeats stop. The coordinator detects the dead member via session timeout. Conversely, when a consumer shuts down cleanly and sends leave-group, rebalancing can happen before the session timeout threshold.

Thus a rebalance during a rollout is not necessarily a timeout; determine whether there was an orderly leave or an abrupt loss.

### 5.6. Improper Consumer API usage

`KafkaConsumer` is not thread-safe. If an application uses the consumer instance itself from another thread, calling `poll()`, `seek()`, or `commitSync()` from the wrong owner, consumer state can become unpredictable. With `@KafkaListener`, let the container manage the consumer and poll loop.

## 6. How does the Spring Kafka listener container participate?

Spring Kafka is responsible for creating the consumer, polling records, dispatching to listeners, running the error handler, committing offsets, and coordinating lifecycle. The Kafka group coordinator still decides session timeouts.

Typical flow:

1. Listener container creates `KafkaConsumer` from `ConsumerFactory`.
2. Consumer subscribes to topics, joins group, and receives partition assignment.
3. Container polls records and invokes listener.
4. When listener completes, container advances offsets per acknowledgment mode.
5. When rebalance occurs, container receives revoke/assign/lost callbacks depending on group protocol and client state.
6. On clean stop, container closes consumer and releases resources.

A session timeout can happen before the listener container gets to run callbacks. If the JVM is frozen, callbacks cannot run before the broker evicts the member.

### 6.1. Distinguishing revoked and lost

- **Revoked**: partitions are revoked as part of a rebalance process; there may be a chance to save valid state before ownership transfers.
- **Lost**: the consumer has lost partition ownership; do not attempt to commit offsets as if the member were still valid.
- **Assigned**: the consumer receives a new assignment and can prepare state to process.

Callbacks are not a guarantee that "cleanup always runs before the broker moves partitions". During crashes or freezes, old callbacks may arrive late or not at all.

### 6.2. Eager vs cooperative rebalance

Eager rebalancing can require members to revoke all assignments before redistributing. Cooperative rebalancing tries to migrate partitions incrementally and narrow revocation scope.

Cooperative **cannot cure session timeouts**. If a member truly loses liveness, its partitions still need a new owner. Cooperative only adjusts how assignments transfer.

### 6.3. Pausing can still maintain polling

Spring Kafka supports pausing listener containers to temporarily stop receiving new records while still polling under container mechanics to preserve group membership. This is preferable to letting a listener sleep unboundedly.

However, pause does not cure JVM stop-the-world pauses, lost broker connectivity, or network partitions: heartbeats must still physically reach the coordinator.

## 7. Spring Boot configuration with classic protocol

Example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    consumer:
      group-id: payment-service
      enable-auto-commit: false
      max-poll-records: 200
      properties:
        group.protocol: classic
        session.timeout.ms: 30000
        heartbeat.interval.ms: 10000
        max.poll.interval.ms: 300000
    listener:
      concurrency: 3
      ack-mode: record
~~~

Each property has a distinct role:

| Property | Meaning |
|---|---|
| `group-id` | Identifies the consumer group |
| `enable-auto-commit=false` | Lets the container manage offset commits per listener processing |
| `session.timeout.ms` | Missed-heartbeat tolerance window in classic protocol |
| `heartbeat.interval.ms` | Target cadence for sending heartbeats |
| `max.poll.interval.ms` | Limit between poll calls |
| `max-poll-records` | Maximum records returned in one poll |
| `concurrency` | Number of consumers in the listener container per instance |
| `ack-mode=record` | Commits per successfully processed record |

These are **illustrative values**, not fixed recommended settings. Kafka brokers can restrict the `session.timeout.ms` range clients are allowed to request. A session timeout outside bounds will prevent the consumer from joining the group.

### 7.1. Heartbeat interval should be well below session timeout

If heartbeat interval is close to session timeout, a single delayed heartbeat puts the consumer at risk of being considered dead. A typical starting point is around one-third of session timeout:

~~~text
heartbeat.interval.ms = 10000
session.timeout.ms    = 30000
~~~

The actual ratio depends on network jitter, broker response latency, and failover requirements. Do not increase heartbeat rate indiscriminately if brokers are already under heavy group coordination load.

### 7.2. Session timeout too small

- Detects dead members faster.
- Yet prone to false failures on network jitter or GC pauses.
- Can cause frequent rebalances, hurting throughput and increasing lag.

### 7.3. Session timeout too large

- Tolerates longer heartbeat interruptions.
- Yet when a process truly dies, the coordinator detects it slowly.
- The dead member's partitions may wait longer before reassignment, increasing recovery time.

Setting timeouts is a balance between **failure detection speed** and **tolerance for transient failures**.

## 8. With the new consumer group protocol

When clients and brokers support `group.protocol=consumer`, heartbeat and session parameters may be managed by the broker, unlike the classic model.

Client example:

~~~properties
group.protocol=consumer
~~~

Related broker properties may include:

~~~text
group.consumer.heartbeat.interval.ms
group.consumer.session.timeout.ms
~~~

Do not copy classic consumer `heartbeat.interval.ms` or `session.timeout.ms` assuming they still control timeouts when the consumer protocol is in use. Depending on Kafka client version, some classic properties may be rejected or ineffective under the new protocol.

Configuration workflow:

1. Determine the actual `group.protocol`.
2. Confirm Kafka client and broker versions.
3. Determine whether timeouts are controlled on the client or broker.
4. Set supported values.
5. Observe failure detection time through fault injection and metrics.
6. Do not guess solely from property names.

`max.poll.interval.ms` still serves to govern poll progress, though its interaction with static membership/protocol must be checked against the running version.

## 9. Running multiple replicas and concurrency

Suppose a topic has 6 partitions, the service runs 3 pods, each with concurrency 2:

~~~text
Topic payments: 6 partitions

Pod A: A-0, A-1
Pod B: B-0, B-1
Pod C: C-0, C-1

Total consumer members = 3 × 2 = 6
~~~

If Pod B suffers a severe pause, both B-0 and B-1 can lose heartbeats together. The group may transfer the partitions previously held by these two members to the remaining four members.

Increasing concurrency **does not cure session timeouts by itself**. In fact, too many consumers can increase threads, sockets, and resource usage, raising CPU/memory pressure.

Count total consumers in the group across all replicas, not just the concurrency of a single JVM.

### 9.1. Signs of a single-pod issue

If only consumers on one pod experience session timeouts, inspect node networking, pod CPU throttling, JVM GC, and restart events.

If multiple pods across multiple groups time out together, inspect the broker coordinator, network, or shared infrastructure services.

### 9.2. Autoscaling and deployment

New pods joining the group can trigger rebalances even with no timeout. Clean pod shutdowns can also trigger rebalances due to leave-group. Pods losing power abruptly are typically detected later via session timeout.

Correlate deployment history with coordinator logs to tell these scenarios apart.

## 10. Static membership and session timeout

`group.instance.id` provides static membership, giving a consumer a stable identity across restarts in certain architectures.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: payment-service
      properties:
        group.instance.id: payment-worker-slot-a
        session.timeout.ms: 45000
~~~

`group.instance.id` must be unique among active static members in the same group. With listener container concurrency greater than 1, Spring Kafka may generate identifying suffixes per child consumer; understand your version's behavior so you do not configure the same ID for multiple members.

Static membership can reduce unnecessary rebalances during brief restarts, yet it **does not disable session timeouts**.

~~~text
Static member brief restart:
  Can keep assignment more stable.

Static member loses liveness past session timeout:
  Coordinator can still reassign partitions.
~~~

If choosing a very long session timeout for static members, application recovery after a real crash is also slower. Base it on restart SLOs and failover requirements.

## 11. Impact on offset commits and data

Rebalances do not cause Kafka to delete records. However, they change partition ownership and a consumer's ability to commit offsets.

Example:

~~~text
Consumer A processes payments-0 offset 120
    |
    +-- DB write committed
    |
    +-- A loses session before offset commit
    |
    v
Consumer B receives payments-0
    |
    v
B may re-read offset 120 from prior committed offset
~~~

Once A has lost its generation/assignment, an offset commit may fail with `CommitFailedException` or a rebalance-related exception. If A still has background tasks running, side effects from A and B can collide even though Kafka only assigns the partition to one valid member.

### 11.1. Idempotency

With at-least-once processing, redelivery is a normal possibility. Options to protect side effects:

- Stable event IDs.
- Inbox table with unique constraint.
- Idempotent database updates.
- Business operation ID constraints (e.g., payment ID).
- Outbox if events must be published after DB commit.
- Unprocessable errors routed to recovery/DLT per clear policy.

Kafka session timeouts do not guarantee a listener method runs only once. Even when Kafka EOS is configured for Kafka-to-Kafka, side effects outside Kafka still need idempotency mechanisms.

### 11.2. Do not commit offsets after partitions are lost

If a member has lost ownership, do not manually commit progress as if the partition still belonged to it. Specifically, the `onPartitionsLost` callback is not a safe place to force-commit offsets of lost partitions.

If a consumer freezes, it may not run callbacks before the broker moves partitions. Therefore correctness must rely on transactions/idempotency rather than solely on revoke callbacks.

## 12. Observing rebalances in Spring Kafka

You can register a `ConsumerAwareRebalanceListener` to log assignments:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {

            @Override
            public void onPartitionsAssigned(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions
            ) {
                log.info("Assigned: {}", partitions);
            }

            @Override
            public void onPartitionsRevokedBeforeCommit(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions
            ) {
                log.warn("Revoked: {}", partitions);
            }

            @Override
            public void onPartitionsLost(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions
            ) {
                log.error("Lost: {}", partitions);
            }
        }
    );

    return factory;
}
~~~

Imports and callback contracts must match your project's Spring Kafka version.

### 12.1. Do not block inside callbacks

Rebalance callbacks run on the consumer's operational path. A slow database or HTTP operation inside a callback can prolong rebalancing, causing further group instability.

If state checkpointing is needed, use logic with an explicit deadline and distinguish revoke from lost. Do not wait indefinitely to "guarantee" a background task completes.

### 12.2. Do not depend completely on callbacks

A killed or frozen JVM may not run callbacks at the desired time. A new consumer can still receive partitions after session expiration. Side effects outside Kafka must be independently protected via idempotency.

## 13. Diagnosing session timeouts from logs

When seeing rebalances, collect simultaneously:

1. `group.id`, consumer client ID, and pod/JVM.
2. Topic-partition assignment before and after the event.
3. Timestamp of last successful heartbeat and failed heartbeats.
4. Evidence of member removed/session expired from the coordinator.
5. Evidence of `max.poll.interval.ms` violation.
6. Network errors or coordinator discovery failures.
7. GC stop-the-world pauses.
8. CPU throttling, node pressure, pod restarts/OOMs.
9. Kafka broker restarts/coordinator migrations.
10. Offset commit failures and listener redeliveries.

Some log patterns you might see, depending on Kafka version:

~~~text
Heartbeat request failed
Marking coordinator unknown
Attempt to heartbeat failed since group is rebalancing
Max poll interval exceeded
Commit cannot be completed because the group has rebalanced
Partitions revoked / partitions assigned
~~~

These messages do not always appear verbatim. They are investigative leads, not sufficient proof of a session timeout. Inspect full coordinator and client logs around the same timestamp.

### 13.1. Signs of a genuine session timeout

- Consecutive failed heartbeats spanning roughly the session threshold.
- Coordinator reports evicting the member for losing liveness.
- JVM freeze or network outage occurred prior to rebalance.
- Listener/poll interval does not appear to be the primary cause.

### 13.2. Signs of poll interval violation

- Listener/batch processing time exceeded max poll interval.
- Client logs report poll interval exceeded.
- Reducing batch size or optimizing the listener makes the incident vanish.
- Heartbeats may have remained normal up until the poll deadline was breached.

With static membership, these two sequences can follow one another: poll interval violation, then heartbeats stop, then session expiration.

## 14. Kafka CLI to inspect groups

You can inspect consumer groups from an environment with cluster access:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group payment-service
~~~

Output may include committed offset, log end offset, lag, assignment, and member metadata depending on Kafka version and group state. While a group is rebalancing, output can fluctuate; cross-check multiple times alongside logs.

To view partition count:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic payments
~~~

In clusters with SASL/SSL, CLI clients must use the proper authentication config. These are operational examples to understand the tools; not commands to run while authoring docs.

## 15. Monitoring and alerting

| Metric group | Purpose |
|---|---|
| Heartbeat response time and failures | Determine coordinator liveness |
| Heartbeat rate | Detect abnormal heartbeating |
| Rebalance count and duration | Measure group churn |
| Assigned-partitions count | Track partition count per member |
| Poll latency / poll interval | Detect consumers failing to poll on time |
| Listener processing p95/p99 | Correlate business latency with polling |
| GC pause duration | Find stop-the-world pauses |
| Container CPU throttling | Find starvation |
| Broker coordinator request errors | Identify broker-side errors |
| Consumer lag per partition | Measure disruption and recovery |
| Offset commit failures | Signal of lost authority or group generation |
| Duplicate business event count | Evaluate idempotency after rebalance |

Exact metric names depend on Kafka client, Spring Kafka, Micrometer, and monitoring stack. Not all metrics are enabled by default; configure corresponding instrumentation.

Do not alert just because one rebalance occurred during a rolling deployment. More meaningful signals are **continuous rebalances outside maintenance**, lag breaching SLO, prolonged heartbeat errors, or rising commit failures.

## 16. Tuning session timeout safely

### 16.1. When is increasing appropriate?

Raising the timeout can be reasonable if the network has brief jitter or rare GC pauses exceed the current threshold, and fixable root causes have already been addressed.

Illustrative example:

~~~text
Before:
  session timeout    = 10000 ms
  heartbeat interval = 3000 ms

Observed:
  Several brief 12-15s pauses, repeated rebalances.

After measuring and optimizing JVM/infrastructure:
  session timeout    = 30000 ms
  heartbeat interval = 10000 ms
~~~

If the consumer group uses the new protocol, timeouts may need to be changed on the broker side rather than in consumer properties.

### 16.2. Do not use timeouts to mask underlying bugs

Do not just raise session timeout when:

- The listener exceeds `max.poll.interval.ms`.
- JVM OOMs or restarts continuously.
- Broker coordinator is unstable.
- Network drops regularly for minutes.
- Severe CPU throttling occurs.
- App spawns background tasks without deadlines preventing shutdown completion.

An overly long timeout loses the ability to detect dead members quickly. A configuration showing "no more rebalances" is not necessarily good if partitions hang too long when a process truly dies.

### 16.3. Heartbeat interval and broker load

Too frequent heartbeats increase group coordination requests. Too infrequent heartbeats reduce jitter tolerance. Measure coordinator latency and group count, especially with many consumer groups on the same broker cluster.

## 17. Tuning max.poll.interval and max.poll.records

A slow batch can exceed the poll deadline even while heartbeats remain active.

For example, a listener averages 500 ms/record and each poll returns 500 records:

~~~text
500 records × 500 ms = 250 seconds

max.poll.interval.ms = 300000  (5 minutes)

Little headroom remains for retries, GC, and networking.
~~~

You can lower `max.poll.records` to 100, optimize database operations, use appropriate batching, or increase concurrency within partition count and downstream capacity limits.

Workflow:

1. Measure p95/p99 duration per record/batch.
2. Determine practical maximum records per poll.
3. Compute worst-case processing time including retries/backoff and downstream timeouts.
4. Lower `max.poll.records` if batches cause overly long poll gaps.
5. Pick `max.poll.interval.ms` with headroom for variance.
6. Re-measure throughput and lag to avoid shrinking batches excessively.

`max.poll.records` caps records returned per poll; it does not add consumers. If a single record can run longer than the poll interval, change the listener or split the workload.

## 18. Rebalance and asynchronous processing

A dangerous pattern:

~~~java
@KafkaListener(topics = "payments")
public void onPayment(PaymentEvent event) {
    executor.execute(() -> database.apply(event));
}
~~~

The listener returns immediately when the task is submitted. With ack modes tied to listener return, the container may advance offsets before the database side effect completes. If the process crashes, records risk being skipped.

Conversely, if the task runs long after partitions are reassigned due to session timeout, the old consumer and new consumer can both execute side effects.

A safer design:

- Process synchronously in the listener if business deadlines are short.
- Or write a durable work item to a database/queue before the listener returns.
- With asynchronous acknowledgments, understand your Spring Kafka version's semantics and never commit past unfinished records.
- Track tasks by topic-partition, supporting cancellation on revoke/lost.
- Use an inbox or business idempotency key to prevent duplicate effects.

No lifecycle callback replaces database transaction boundaries or unique constraints.

## 19. Testing with fault injection

### 19.1. Coordinator disconnection

1. Create a dedicated test topic and consumer group.
2. Run at least two consumer members.
3. Record assignments and committed offsets.
4. In a test environment, block heartbeats/network for one member long enough.
5. Observe the coordinator evict the member after session timeout.
6. Confirm partitions are reassigned.
7. Restore the member and verify group rejoin/reconciliation.
8. Confirm redelivered events are handled idempotently.

### 19.2. JVM pause

1. Enable metrics and logs for GC/heartbeats.
2. Induce a controlled JVM pause in the test environment.
3. Compare pause duration against session threshold.
4. Observe member removal and rebalance.
5. Reduce resource pressure and re-test.

### 19.3. Isolated max poll interval

1. Have the listener process a slow batch while networking is normal.
2. Let processing exceed `max.poll.interval.ms`.
3. Observe poll violation logs.
4. If dynamic member, observe client leave/rebalance.
5. If static member, track heartbeat stopping followed by session expiration.
6. Adjust poll size/processing duration and re-measure.

### 19.4. Crash after DB commit but before offset commit

1. Send an event with a stable event ID.
2. Have consumer A commit database changes.
3. Cause A to lose membership before offset commit.
4. Have consumer B receive the partition.
5. Confirm the event can be redelivered.
6. Confirm inbox/unique constraint prevents duplicate side effects.
7. Verify committed offsets advance properly after safe processing.

These are controlled infrastructure experiments; never deliberately induce network outages or JVM freezes in production to validate a hypothesis.

## 20. Common diagnostic mistakes

**Assuming every rebalance is due to session timeout:** deployments, joins/leaves, partition changes, and poll interval violations also trigger rebalances.

**Assuming slow listeners always stop heartbeats:** modern classic consumers usually have background heartbeats; check poll intervals separately.

**Increasing session.timeout.ms to fix max.poll.interval:** the two limits serve different purposes.

**Setting heartbeat.interval.ms close to session.timeout.ms:** raises the risk of false failures when a single heartbeat is delayed.

**Setting timeouts too large:** delays detecting truly dead consumers and slows recovery.

**Believing static membership cannot time out:** static members still lose membership when liveness expires.

**Confusing revoked and lost:** committing on lost partitions may no longer be valid.

**Assuming cooperative rebalance eliminates session timeouts:** cooperative only changes how assignments transfer owners.

**Ignoring commit failures:** uncommitted records can be redelivered.

**Using auto commit with long listeners and non-repeatable side effects:** offsets may decouple from business state.

**Submitting background tasks and returning:** the container can treat records as processed before tasks are durable.

**Tuning classic settings when using the new group protocol:** client properties may have no effect.

**Increasing concurrency indefinitely:** consumes more CPU/threads without increasing parallelism beyond partition count.

## 21. Operational troubleshooting table

| Observation | Investigation direction |
|---|---|
| Rebalance right after deploy or scale | Join/leave group, rollout; not necessarily timeout |
| Many heartbeat failures | Network, coordinator, JVM pause |
| Only one pod loses liveness | CPU throttling, GC, host/network specific |
| Multiple groups time out together | Broker or shared infrastructure |
| Listener duration increasing | `max.poll.interval.ms`, batch size, downstream |
| Static membership times out after long task | Poll violation followed by stopped heartbeats |
| CommitFailedException after rebalance | Lost ownership, offsets, and redelivery |
| Lag grows after a member dies | Session detection time, reassignment |
| Fencing transactional producer | Transactional ID/epoch; do not equate with session timeout |
| Timeouts only after idle or restart | Check lifecycle, coordinator, and version/config |
| Continuous rebalances despite normal network | Poll interval, member churn, assignor, resource pressure |

## 22. Conclusion

**Rebalance due to session timeout** occurs when the group coordinator stops receiving sufficient heartbeat/liveness signals from a consumer member within the allowed window. The coordinator evicts that member and the group must redistribute orphaned partitions. Networking, broker coordinator issues, JVM pauses, CPU starvation, and process crashes are common causes.

In Spring Kafka, distinguish this incident from `max.poll.interval.ms`: a slow listener typically impacts the poll loop first, while background heartbeats may keep running. Identify the right group protocol, monitor heartbeats and assignments, configure timeouts on the proper client or broker side, and tie offset commits to business processing outcomes.

When partitions transfer to a new owner, redelivery and offset commit failures can happen. End-to-end reliability comes not from raising timeouts, but from **clear consumer lifecycles, observability, idempotency, and proper transaction boundaries**.
