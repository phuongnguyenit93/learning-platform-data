# Pause Per Partition

In Spring Kafka, a consumer can be assigned multiple partitions across one or more topics. Not all partitions always need to be read at the same rate: one partition may be bottlenecked by a dependency, overloaded, or need to be temporarily halted to handle anomalous data, while the remaining partitions continue operating normally. **Pausing per partition** allows temporarily stopping the fetching of additional records from a specific `TopicPartition` without halting the entire listener container.

Spring Kafka provides APIs such as `pausePartition(TopicPartition)`, `resumePartition(TopicPartition)`, `isPartitionPauseRequested(TopicPartition)`, and `isPartitionPaused(TopicPartition)` on `MessageListenerContainer` in supporting versions (per-partition pause/resume was introduced in Spring Kafka 2.7). This is an **operational backpressure** tool; it is not a retry mechanism, does not commit offsets on its own, does not move records to a DLT, and does not guarantee that records already fetched before the pause will stop processing immediately.

## 1. What scenarios does partition pause solve?

Suppose the `orders` topic has four partitions. A consumer group has two instances, each with one consumer:

```text
Topic orders
  partition 0 ---> Consumer A
  partition 1 ---> Consumer A
  partition 2 ---> Consumer B
  partition 3 ---> Consumer B
```

If records in `orders-2` need to call an unstable payment system, operations may want to relieve pressure on that system while still processing `orders-3`. When pausing partition 2:

```text
Consumer B
   |
   +--> orders-2: PAUSED (stops fetching additional new records)
   |
   +--> orders-3: ACTIVE (continues polling and delivering records)

Consumer A
   |
   +--> orders-0: ACTIVE
   +--> orders-1: ACTIVE
```

Key point: **`orders-2` remains assigned to Consumer B**. Pause does not ask the Kafka coordinator to reassign that partition to Consumer A. If the goal is to shift load to another member, you must evaluate scaling, group membership, and rebalancing rather than simply calling pause.

### When is it useful?

- A partition contains records tied to a specific tenant or business key that must be temporarily halted due to its own dependency.
- A processing flow requires manual inspection before accepting more records from a suspect partition.
- The application enforces rate limits against an external service and wants to throttle consumption on certain partitions during overload.
- The system needs to keep healthy partitions making progress instead of pausing the entire listener.
- A workflow can pause per partition to preserve local ordering while waiting on a business condition.

Do not default to per-partition pause as the cure for every kind of overload. If the entire database is saturated, pausing one selected partition may simply shift pressure to the other partitions; in that case, container-wide backpressure, concurrency limits, rate limiters, or improving the dependency may be more appropriate.

## 2. Partition assignment, pause, and Kafka poll are three distinct concepts

The Kafka consumer group determines **which member owns a partition**. Kafka consumer `pause(Collection<TopicPartition>)` determines **which partitions temporarily do not return new records via `poll()`**. The Spring Kafka listener container provides APIs to request pause in alignment with the consumer thread lifecycle.

| State | Meaning | Does the partition still belong to the consumer group member? |
|---|---|---|
| Assigned + active | Consumer owns the partition and continues fetching records. | Yes. |
| Assigned + paused | Consumer owns the partition but temporarily stops fetching more records from it. | Yes. |
| Revoked | Coordinator revoked the partition from the member during a rebalance. | No. |
| Container stopped | Listener container is no longer operating as a normal consumer. | After leaving the group, partitions are redistributed. |

A paused partition does not necessarily cause the group to rebalance. The consumer must still `poll()` regularly to maintain membership and appropriate heartbeats, especially when all partitions are paused.

**Do not call `KafkaConsumer.pause(...)` directly from an HTTP request thread or an external monitoring thread.** KafkaConsumer is not a thread-safe object for arbitrary cross-thread use. Call the Spring Kafka container's pause API; the container coordinates the operation with the consumer in the right context.

## 3. The pausePartition and resumePartition APIs

In Spring Kafka versions supporting per-partition pause, `MessageListenerContainer` provides the main operations:

```java
container.pausePartition(new TopicPartition("orders", 2));
container.resumePartition(new TopicPartition("orders", 2));
```

`TopicPartition` is a pair of **topic name + partition index**. For example, `TopicPartition("orders", 2)` is completely distinct from `TopicPartition("payments", 2)`.

Commonly used observation APIs:

```java
TopicPartition tp = new TopicPartition("orders", 2);

boolean requested = container.isPartitionPauseRequested(tp);
boolean applied   = container.isPartitionPaused(tp);
```

Distinguish clearly:

- `pausePartition(tp)`: **issues a request** to pause the partition.
- `isPartitionPauseRequested(tp)`: checks whether the container has received the pause request.
- `isPartitionPaused(tp)`: checks whether the pause state has been applied by the container according to its observed state.
- `resumePartition(tp)`: issues a request to clear the pause, allowing the partition to be polled again when validly assigned.

The pause request and the actual paused state **do not necessarily change on the same line of code**. Spring Kafka can apply the pause at a safe poll-loop boundary. If a batch/record from the previous poll is still being processed, records may still be delivered to the listener before the pause takes effect.

Therefore, do not write:

```java
container.pausePartition(tp);
// DO NOT assume here that all processing on tp has strictly stopped.
performDangerousMaintenanceOnPartitionData();
```

If you need an absolute guarantee that no handler is running before maintenance, add a quiescence protocol: observe the applied pause state, count in-flight work, wait for running transactions to finish, and use a business lock/lease where appropriate.

## 4. Example with @KafkaListener and KafkaListenerEndpointRegistry

To control a listener from another service, assign a fixed `id` to the listener:

```java
@Component
public class OrderKafkaListener {

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        concurrency = "3"
    )
    public void onMessage(ConsumerRecord<String, String> record) {
        orderProcessor.process(record.key(), record.value());
    }
}
```

`KafkaListenerEndpointRegistry` lets you look up the container by listener ID and request partition pause/resume:

```java
@Service
public class OrderPartitionControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderPartitionControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause(int partition) {
        TopicPartition tp = new TopicPartition("orders", partition);
        container().pausePartition(tp);
    }

    public void resume(int partition) {
        TopicPartition tp = new TopicPartition("orders", partition);
        container().resumePartition(tp);
    }

    public PartitionPauseState state(int partition) {
        TopicPartition tp = new TopicPartition("orders", partition);
        MessageListenerContainer c = container();

        return new PartitionPauseState(
                c.isPartitionPauseRequested(tp),
                c.isPartitionPaused(tp));
    }

    private MessageListenerContainer container() {
        MessageListenerContainer c =
                registry.getListenerContainer("orders-listener");
        if (c == null) {
            throw new IllegalStateException(
                    "orders-listener is not registered");
        }
        return c;
    }

    public record PartitionPauseState(
            boolean pauseRequested,
            boolean paused) {
    }
}
```

Key imports:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
```

The example above assumes a Spring Kafka version supporting per-partition container methods and a Java version modern enough for `record`. You can replace `record` with a regular DTO/class on older Java versions.

Do not expose `pause`/`resume` through an unauthenticated HTTP endpoint. If creating an operations endpoint, restrict permissions, validate topic/partition inputs, log the operator, timestamp, and pause reason, and have an auto-recovery mechanism in case an operator forgets to resume.

## 5. When listener concurrency is greater than one

`concurrency = "3"` can create three child consumer containers for a single listener. Each child consumer is assigned a separate set of partitions in the group by Kafka:

```text
ConcurrentMessageListenerContainer: orders-listener
    |
    +--> child container 0 -> orders-0, orders-3
    +--> child container 1 -> orders-1, orders-4
    +--> child container 2 -> orders-2, orders-5
```

The assignment above is illustrative only; the Kafka assignor and actual member count determine distribution.

When calling the per-partition API on a concurrent container, Spring Kafka must apply the request to the child container that holds the assigned partition. Code should not rely on an assumption like "partition 2 always belongs to child container 2," because rebalances or replica scaling can change assignments.

Inspect actual assignment state and select the right **listener container**. If the application has multiple `@KafkaListener`s subscribing to the same topic or multiple groups, pausing in listener A's container does not mean group B also stops processing that partition.

Especially across multiple replicas:

- Each pod has its own JVM's `KafkaListenerEndpointRegistry`.
- Calling the registry in pod A **does not automatically propagate** the pause request to pod B.
- If the partition is assigned to pod B, the actual pause request must be routed to the proper owner, or every pod must receive the same desired state and apply it whenever it owns the partition.

For centralized deployment-wide pause needs, build a control plane with desired state and a reconciliation mechanism across instances rather than assuming a single call on one pod suffices.

## 6. Pause does not release partitions and does not intentionally cause rebalances

In Kafka, a paused partition remains in the consumer's assignment. Consequences:

1. Other consumers in the same group **do not automatically take over the paused partition**.
2. No auto-scaling mechanism automatically moves that partition to an idle member merely because lag increases.
3. The consumer can continue heartbeating and polling to maintain membership.
4. The partition preserves record ordering by offset upon resume, though ordering **across partitions** is not guaranteed.
5. Committed offsets do not change solely because of pausing.

If the goal is to halt `orders-2` because its target system is slow, pause is appropriate. If the goal is to redistribute hot load from Consumer B to Consumer A, pause is the wrong tool: evaluate partitioning strategy, consumer count, partition count, and load-balancing capability.

### What if all partitions are paused?

The container can still continue polling to maintain group state, but will not receive additional records from paused partitions. Using the container API rather than blocking the thread with `Thread.sleep(...)` is crucial so you do not trigger a `max.poll.interval.ms` timeout.

Do not interpret "still polling" as making the application completely immune to rebalances. If the listener processes a record for a very long time, the process hangs, the network drops, or membership changes, the group can still rebalance per Kafka rules.

## 7. When does pause begin taking effect?

A pause request does not automatically discard records the consumer already fetched earlier. A single poll cycle can return multiple records:

```text
T0: poll() fetches 5 records from orders-2
T1: listener starts processing record 1
T2: operations thread calls pausePartition(orders-2)
T3: listener still processes records from the prior poll
T4: container applies pause on poll boundary
T5: subsequent poll does not fetch more new records on orders-2
```

This is a logical diagram, not an exact guarantee of the T3/T4 ordering for every version or listener mode. What to remember is that **pause is not an immediate cancellation command for all running processing**.

If the application uses a batch listener, a batch containing records from the target partition may have already been passed to the listener before the request was received. If a record listener still has buffered records waiting to be dispatched from a poll, pausing while the listener is running does not necessarily prevent all already-fetched records from being processed.

Therefore:

- Use `isPartitionPauseRequested` to know **intent** has been recorded in the container.
- Use `isPartitionPaused` or pause events to know the container state has been **applied**.
- Track in-flight tasks/transactions separately if you need to wait for current processing to finish.
- Do not use pause as a substitute for business locking or high-precision distributed leases.

## 8. Pause and offsets/acknowledgment

Pause does not commit offsets, does not seek, and does not change the ack mode. Example:

```text
orders-2:
  committed offset = 100
  log end offset   = 140

pausePartition(orders-2)

orders-2:
  committed offset still = 100 (assuming no other commit)
  producer keeps writing: log end may rise to 150
```

If records finished processing before pause and the container commits their offsets afterward, the committed offset can still advance. That change comes from prior processing/ack, **not from the pause command itself**.

Principles:

| Operation | Automatically commits offset? | Affects fetching? |
|---|---|---|
| `pausePartition(tp)` | No. | Yes, temporarily halts fetching new records for the partition once applied. |
| `resumePartition(tp)` | No. | Yes, allows fetching records again. |
| `Acknowledgment.acknowledge()` | Per ack mode/configuration. | Not a pause command. |
| `consumer.seek(tp, offset)` | Does not commit automatically. | Changes reading position; distinct from pause. |
| `container.stop()` | Has its own lifecycle and pending-handling per config. | Stops container, not equivalent to pausing one partition. |

With a transactional listener, a transaction started before pause must still commit/abort according to transaction policy. Pause does not turn open transactions into completed ones.

## 9. Per-partition backpressure: control design

Backpressure is how you prevent the intake rate of new work from exceeding processing capacity. With per-partition pause, the control flow can rely on dependency latency, in-flight request counts, timeout rates, or queue depth rather than relying solely on Kafka lag.

Example policy for partitions that map relatively stably to a downstream resource:

```text
Dependency latency / error rate rises
            |
            v
  Protection threshold breached?
       /           \
      No           Yes
      |             |
      v             v
   Continue    pausePartition(tp)
     poll           |
                    v
           Monitor dependency recovery
                    |
                    v
          Stability condition met?
               /          \
              No          Yes
              |            |
              v            v
            Keep     resumePartition(tp)
           paused
```

### High/low thresholds and hysteresis

If the application pauses as soon as dependency latency exceeds 500 ms and resumes as soon as latency drops below 500 ms, state can flip continuously. Use **hysteresis**:

- Pause if average latency exceeds 800 ms continuously over an observation window, or if error rate exceeds the chosen limit.
- Only resume when latency drops below 300 ms and error rate remains stable across several cycles.
- Enforce a minimum pause duration and a post-resume cooldown.
- Enforce a maximum pause limit or alert to avoid leaving a partition forgotten too long.

These thresholds are examples only; measure based on SLAs, throughput, and dependency characteristics. Backpressure does not make work disappear: records stay in Kafka within retention limits, and **lag typically increases while the partition is paused**.

### Why not use high lag as the sole pause condition?

High lag usually indicates the consumer is falling behind the producer. If you pause the consumer merely because lag is high, the backlog will grow even faster. Lag should be used **to evaluate impact and prioritize recovery**, while pause decisions should be tied to a specific protective reason such as insufficient dependency capacity or an unsafe business state.

## 10. Managing desired state with multiple pods

In a Kubernetes environment, a pause decision may need to remain in effect across rolling updates, restarts, or rebalances. Local pause state inside one Java container **is not cluster-wide durable configuration**.

An operational design:

```text
Control plane / database
  desiredPausedPartitions = {orders-2, orders-5}
                 |
                 v
        Control reconciler
                 |
         +-------+-------+
         |               |
         v               v
       Pod A           Pod B
   local registry   local registry
         |               |
         v               v
   Owns orders-2?   Owns orders-5?
         |               |
         v               v
   Apply pause      Apply pause
```

Each instance needs to know which partitions it owns and reconcile desired state against actual assignments. When a partition changes owner due to a rebalance, the new instance must apply the policy before treating that partition as safe to process, if the business requires continuous pausing.

In specific versions/configurations, local pause requests may be managed by the container across assignment changes; however, **do not rely on local state as a durable source of truth across restarts**. Have a reconciliation mechanism and verify actual state.

Depending on security requirements, a desired-state API should:

1. Authenticate and authorize the user or service requesting the pause.
2. Validate that the topic/partition belongs to an allowlist.
3. Record reason, incident ID, operator, and pause expiration time.
4. Synchronize requested state to the relevant instances.
5. Observe that the request was applied, rather than returning HTTP 200 as soon as the flag is set.

## 11. Rebalance, revoke, and resume

A consumer group can rebalance when scaling pods, hitting `max.poll.interval.ms` errors, a member leaving the group, or increasing topic partition counts. During a rebalance, a partition can be revoked and then assigned to another consumer.

```text
Before rebalance:
  Pod A owns orders-2 (paused)

After rebalance:
  Pod A: orders-2 revoked
  Pod B: orders-2 assigned
```

Do not expect Pod A's pause state to automatically transfer to Pod B. If the business rule is "orders-2 must stay paused until an operator resumes it," store that intent outside individual JVMs and reapply it when a new assignment appears.

If using `ConsumerAwareRebalanceListener` or assignment/revoke application events, avoid blocking the consumer thread. A reconciler can update state or schedule policy application; do not make long database/HTTP calls directly inside the rebalance callback.

Before resuming, confirm:

- The partition belongs to the target listener container.
- The root cause of the pause has been resolved, not just that the alert silenced.
- No maintenance action or conflicting in-flight record processing is active.
- Cluster-wide desired state has been switched to "resume."
- Throughput, error rate, and lag are monitored as records begin being read again.

## 12. Events for observing pause/resume

Spring Kafka publishes pause/resume application events. Depending on the supported version, partition-level events may include `ConsumerPartitionPausedEvent` and `ConsumerPartitionResumedEvent`.

Example listener logging event metadata:

```java
@Component
public class KafkaPartitionPauseEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPartitionPauseEvents.class);

    @EventListener
    public void onPaused(ConsumerPartitionPausedEvent event) {
        log.info("Kafka partition pause applied: {}", event);
    }

    @EventListener
    public void onResumed(ConsumerPartitionResumedEvent event) {
        log.info("Kafka partition resume applied: {}", event);
    }
}
```

Illustrative imports:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionPausedEvent;
import org.springframework.kafka.event.ConsumerPartitionResumedEvent;
import org.springframework.stereotype.Component;
```

In a real project, pick the exact fields from the event per your version's API and include `pod`, `listenerId`, `groupId`, `topicPartition`, and `reason` in structured logs. Events are emitted on the container's processing flow; handlers should be fast and not wait on long network calls.

**A "pause applied" event differs from a "pause requested" log.** On dashboards, separate these two states so you do not report a partition as stopped while the container is still finishing records from the previous poll.

## 13. Monitoring lag and retained backlog

While paused, producers can continue writing records. If no new commits happen, partition lag grows:

```text
orders-2 committed offset  = 100
orders-2 log end offset    = 110
lag                        = 10

pause orders-2
producer writes 40 more records

orders-2 committed offset  = 100
orders-2 log end offset    = 150
lag                        = 50
```

After resuming, the consumer needs enough throughput to drain the backlog. If the producer writes an average of 200 records/s and the consumer processes 250 records/s, the theoretical maximum lag drain rate is only around 50 records/s (before accounting for overhead, batching, retries, and partition skew).

Minimum signals to monitor:

| Signal | Purpose |
|---|---|
| `pause_requested` per topic-partition | Know whether an operator/controller requested a halt. |
| `pause_applied` per topic-partition | Know whether the consumer is actually paused. |
| Pause duration | Avoid leaving a partition paused indefinitely. |
| Consumer lag and log-end offset per partition | Measure backlog size and recovery speed. |
| Listener throughput per partition | Confirm active partitions are still making progress. |
| Dependency latency/error rate | Know whether the pause cause still persists. |
| Rebalance/assignment events | Detect partition ownership changes while paused. |
| Oldest record age / retention headroom | Avoid pausing so long that old data is deleted before processing. |

These metric names are **instrumentation suggestions**, not defaults built into the Kafka client or Spring Kafka. Consumer lag can usually be viewed via Kafka tooling; Spring container pause state must come from APIs, events, or application-exposed metrics.

## 14. Inspecting via Kafka CLI and application logs

An important operational step is confirming **the group still owns the partition** and understanding whether lag grew due to pause or another failure.

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service
```

This command typically displays topic, partition, committed offset, log end offset, lag, and member/host/client ID. However, **Kafka CLI cannot conclude that a Spring Kafka container has paused a partition** solely from assignments or lag. The consumer group protocol does not expose a "paused by Spring container" flag directly derivable from normal output.

With Kubernetes, you can combine:

```bash
kubectl get pods -l app=order-service -o wide
kubectl logs -l app=order-service --since=15m --prefix=true
```

Look for `pause requested`, `partition pause applied`, `resume`, assignment/revoke logs, listener exceptions, transaction aborts, and dependency health. If the CLI shows a partition still assigned with a stationary offset while other partitions advance, that is consistent with pause; **confirm via container state** rather than guessing from lag alone.

## 15. How does pause differ from stop, seek, retry, or scale?

| Mechanism | Primary effect | When to use |
|---|---|---|
| `pausePartition(tp)` | Temporarily stops fetching new records from one partition; keeps assignment. | Selective backpressure or intentional pause of a single partition. |
| `container.pause()` | Requests pausing consumption for the entire container. | Need to reduce pressure across all partitions managed by the container. |
| `container.stop()` | Stops container lifecycle; may leave group and trigger rebalance. | Maintenance or truly stopping the listener. |
| `consumer.seek(tp, offset)` | Changes read position by offset. | Controlled replay/skip; not pause. |
| `DefaultErrorHandler` + `BackOff` | Retries or recovers failed records. | Handling transient/permanent listener failures. |
| `@RetryableTopic` | Routes failed records to retry topics for reprocessing. | Non-blocking retry when compatible with ordering and transaction model. |
| Increase concurrency/replicas | Increases consumer members and distributes assignments if partitions allow. | Increasing parallel processing capacity, not a substitute for pause. |

Pause does not solve permanent poison-record errors. If a record always fails due to bad data, you need exception classification, bounded retries, and DLT/recovery. Pause only defers reading additional records; upon resume, the error will reappear if the root cause was not fixed.

## 16. Pause and ErrorHandler/transactional listeners

The error handler might be retrying a record with backoff. If an operator simultaneously requests pausing the partition, understand the boundaries:

- Pause does not cancel a currently running retry listener.
- Records already fetched before pause may continue being processed or retried per container/error handler.
- Pause does not automatically send failed records to a DLT.
- Pause does not alter `AckMode` policy or committed offsets.
- With Kafka transactions, an open transaction must still commit/abort per transaction policy; pause does not alter atomicity.

If the goal is to block sending requests to a failing dependency, also place a **circuit breaker or rate limiter at the callsite**, rather than relying solely on pause because some records may already be in flight.

If using non-blocking retry topics, a failed record may already have moved to a separate retry topic. Pausing a partition on the **main topic** does not automatically pause partitions of the **retry topic** or DLT consumers. Each listener/container and group must be managed within its exact scope.

## 17. Retention, lag, and the risk of pausing too long

Backpressure is not free. Records waiting in Kafka are subject to topic retention policies. If a partition stays paused long enough that log retention deletes old offsets before they are processed, the consumer may encounter invalid-offset situations or miss data depending on `auto.offset.reset` and recovery settings.

Example:

```text
Topic retention: 24 hours
Partition pause: 20 hours
Oldest unprocessed record age: 22 hours

Risk: unprocessed records may be purged from the log early
```

Do not treat a simple retention number as a guaranteed deadline if the topic is also subject to log compaction, size-based retention, or other broker policies. Track **oldest unprocessed record age**, log start offset, and retention headroom, and alert before data is at risk.

For systems requiring zero event loss, you may need short maximum pause limits, increased retention, offloading to durable queues, or an active replay workflow rather than leaving partitions paused indefinitely.

## 18. Runbook: pausing a partition to protect a dependency

Suppose `orders-2` is causing repeated timeouts to the payment service while other partitions remain healthy.

**Step 1 — Confirm scope.** Verify whether errors affect only `orders-2` or are system-wide. Cross-check keys, topic, partition, consumer member, dependency metrics, and error start time.

**Step 2 — Identify the owner.** Inspect current consumer group assignments. Across multiple pods, find the instance owning the partition or ensure the control plane distributes desired state to the right pods.

**Step 3 — Request pause.** Call `pausePartition(new TopicPartition("orders", 2))` through the Spring Kafka container API; do not call `KafkaConsumer.pause` from an external thread.

**Step 4 — Verify application.** Check `isPartitionPauseRequested`, `isPartitionPaused`, application events, and in-flight work. Do not declare an absolute stop immediately after invoking the method.

**Step 5 — Monitor during pause.** Track `orders-2` lag, record age, retention headroom, dependency health, and throughput on remaining partitions. Set alerts if pause exceeds target duration.

**Step 6 — Restore processing conditions.** Fix the dependency, adjust rate limits/circuit breakers, or remediate bad data. If a poison record exists, choose appropriate retry/DLT handling before resuming.

**Step 7 — Resume.** Update desired state, call `resumePartition(tp)`, verify the resume event, and confirm offsets begin advancing. Monitor error rates to prevent a continuous pause/resume loop.

**Step 8 — Close the incident.** Document pause cause, interruption duration, accumulated lag, catch-up duration, failed records, and preventive measures.

Never reset offsets to "make lag disappear" without an approved business decision and data-preservation mechanism.

## 19. Runbook: partition is paused yet records are still being processed

Common causes:

| Symptom | Possible cause | Resolution |
|---|---|---|
| Listener logs still appear right after `pausePartition` | Records were already returned by the prior poll, or pause is not yet applied. | Check requested/applied state, wait for in-flight work to complete. |
| Partition resumes running after rebalance | Partition moved to another pod without the desired pause state. | Reconcile pause on the new owner, inspect assignment events. |
| Only one pod stopped, another pod still processes the same topic | Paused a different container/group/instance. | Verify listener ID, consumer group, and partition owner. |
| Kafka CLI still shows the partition assigned | Normal state when paused. | Do not use assignment as proof of resume; inspect container pause state. |
| A retry topic still processes records | Pause only applies to the topic-partition on the specified container. | Manage retry listener/topic separately if needed. |
| Consumer group rebalances during pause | Pod restart, long-running listener, timeout, or membership change. | Check `max.poll.interval.ms`, polls, heartbeats, and Kubernetes events. |
| Offset still advances slightly after pause | Commit/ack of records processed before pause. | Correlate pause-applied timestamp with commit history. |

If pause has been applied yet the listener continuously receives new records from the exact same partition, check which API and listener container were called, the Spring Kafka version, assignment status, and whether other code is calling `resumePartition`.

## 20. Integration testing for per-partition pause

To prove the policy works, run integration tests against real Kafka, such as via Testcontainers or an embedded broker supporting your Kafka version.

A test scenario:

1. Create an `orders` topic with at least two partitions.
2. Start a listener container with a fixed `id` and a test-specific group ID.
3. Wait for full assignment and verify the listener receives baseline records from both partitions.
4. Call `pausePartition(orders-0)` and wait until the pause state is applied.
5. Publish additional records to `orders-0` and `orders-1`.
6. Verify `orders-1` continues processing; `orders-0` stops receiving new records after accounting for in-flight records.
7. Call `resumePartition(orders-0)` and wait for applied state to change.
8. Verify backlogged records on `orders-0` are processed, offsets advance, and no data is lost.
9. As needed, trigger a rebalance/restart to verify desired state is properly restored.

Avoid asserting immediately after the pause call without waiting on asynchronous conditions; that produces flaky tests. Also avoid using a long fixed `Thread.sleep(...)` instead of awaiting actual pause state when tests can use condition-await utilities.

If business-level once-only processing must be tested, integrate separate idempotency/assertions. Pause/resume itself does not guarantee exactly-once processing.

## 21. Operational principles

- Use Spring Kafka container's `pausePartition(tp)` / `resumePartition(tp)` instead of calling `KafkaConsumer.pause` from a non-consumer thread.
- Understand pause as **stopping further fetches**, not immediately stopping or canceling all in-progress records.
- Separate `pause requested` and `pause applied` when displaying status.
- Pause **does not revoke assignments**, does not trigger rebalances on its own, and does not move partitions to other members.
- Pause **does not commit offsets**, does not seek, and does not replace error handlers or DLT.
- With concurrency and multiple replicas, verify the right owner; persist desired state if pause must survive restarts/rebalances.
- Monitor lag, record age, retention headroom, pause duration, and dependency health; never leave a partition paused indefinitely.
- Choose backpressure thresholds with hysteresis and cooldown; avoid oscillating pause/resume around a single threshold.
- When resuming, confirm the dependency has recovered and processing capacity is sufficient to catch up on the backlog.
- Protect operational APIs with authentication, authorization, audit logs, and topic-partition validation.
- Test pause under in-flight records, multiple partitions, rebalances, and restarts.

**Per-partition pause** is a narrow-scope consumption control tool in Spring Kafka. It helps protect dependencies or halt an anomalous data stream without forcing other partitions to stop. To operate reliably, distinguish pause requests from applied state, preserve offsets and per-partition ordering, handle assignments across scaling/rebalances, and plan resumes based on lag, retention, and downstream system health.
