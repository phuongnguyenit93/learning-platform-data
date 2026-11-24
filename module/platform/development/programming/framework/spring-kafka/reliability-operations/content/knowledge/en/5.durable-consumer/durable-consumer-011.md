# ConsumerRebalanceListener

In a Kafka consumer group, partition reading ownership is distributed among active consumers. When group membership or the set of partitions changes, Kafka executes a **rebalance** to determine which consumer owns which partitions. During this period, a consumer may lose some partitions, gain new ones, or lose partition ownership abruptly.

**ConsumerRebalanceListener** is the callback interface allowing an application to react to those ownership changes. In Spring Kafka, this listener is valuable when a consumer needs to release per-partition state, persist checkpoints, initialize resources for newly assigned partitions, or record when partitions were lost. Implemented improperly, an application can commit wrong offsets, hold resources too long, cause duplicate processing, or prolong rebalances.

## 1. What Is a Rebalance and Why Must the Application Know?

A Kafka consumer group lets multiple consumers share reading a topic's partitions. The group coordinator tracks members and orchestrates partition assignment. When the group must alter assignments, consumers participate in a rebalance cycle.

Common triggers include:

- A new consumer joins the group or an existing consumer leaves.
- A consumer stops, crashes, disconnects, or fails to send heartbeats on time.
- A consumer exceeds the allowed interval between polls.
- Topic partition counts change.
- Consumer subscriptions change.
- A consumer restarts during a new version deployment.
- Assignment strategy or group configuration changes.

For example, a group consumes a topic with six partitions and three consumers. Each consumer may receive two partitions. When one consumer stops, Kafka redistributes its partitions among the remaining consumers. When that consumer returns, the group may run another rebalance to balance assignments.

~~~mermaid
flowchart TD
    A["Consumer group stable"] --> B["Membership or partitions change"]
    B --> C["Kafka initiates rebalance"]
    C --> D["Existing consumer receives revoke/lost callback"]
    D --> E["Group finalizes new assignment"]
    E --> F["Consumer receives assigned callback"]
    F --> G["Resume polling and processing records"]
~~~

Applications need visibility into this transition because processing state is often scoped by partition. For example, a consumer might hold counters, caches, state stores, or resource locks per partition. When a partition moves to another consumer, the old consumer must clean up its state and the new consumer must initialize corresponding state.

## 2. Which Callbacks Does ConsumerRebalanceListener Provide?

Kafka provides the **org.apache.kafka.clients.consumer.ConsumerRebalanceListener** interface with three main callbacks:

| Callback | Timing | Typical Application Actions |
|---|---|---|
| **onPartitionsRevoked(partitions)** | Before the listed partitions are revoked during a normal rebalance | Finish work that can complete safely, persist state, and release resources |
| **onPartitionsAssigned(partitions)** | After the consumer receives newly assigned partitions | Initialize per-partition state, load checkpoints, or seek if using a custom offset policy |
| **onPartitionsLost(partitions)** | When the consumer has already lost ownership of the listed partitions | Mark ownership as lost and clean local state; never assume commits are still valid |

The **onPartitionsLost** callback exists on Kafka client versions supporting it. When compiling against older Kafka clients, the interface may not provide that method yet. Check the exact **kafka-clients** version your Spring Kafka application uses.

### 2.1 onPartitionsRevoked

This callback signals that the listed partitions are about to leave the consumer's current assignment. During a normal rebalance, this is the final opportunity for the consumer to handle work tied to those partitions before ownership transfers.

Appropriate actions typically include:

- Flushing buffered state or data tied to partitions about to be revoked.
- Saving checkpoints for completed processing.
- Closing local resources or releasing application-managed locks.
- Recording metrics and logs for the outgoing assignment.
- Completing offset commits per application policy if the application manages commits directly.

Do not assume every partition owned by the consumer appears in the callback list. With cooperative rebalancing, the callback may contain only the subset of partitions actually being revoked; the consumer keeps owning the remaining partitions.

### 2.2 onPartitionsAssigned

This callback runs after the consumer receives a new assignment. The passed collection holds partitions newly assigned to the consumer in that cycle.

The application can:

- Create per-partition state or resources.
- Restore per-partition caches or state stores.
- Load application-managed checkpoints.
- Call **consumer.seek(partition, offset)** if reading from a custom position policy.
- Log the new assignment to observe load distribution.

For offsets, distinguish Kafka-managed committed offsets from custom checkpoints in a database or state store. If the application explicitly seeks from a custom checkpoint, define clearly which checkpoint is the source of truth and ensure checkpoints only reflect safely processed records.

### 2.3 onPartitionsLost

This callback represents cases where the consumer has already lost partition ownership. For instance, the consumer may have been disconnected long enough or the group transferred assignments to another member before the old consumer could finish normal revocation.

Once partitions are lost, the consumer must not assume it still holds permission to commit offsets. Another consumer may already have taken over the partitions. Use this callback to:

- Mark ownership of those partitions as lost.
- Halt or invalidate state writes tied to stale ownership.
- Safely close local resources.
- Emit logs/metrics distinguishing partition loss from normal revocation.
- Rely on idempotency and fencing to block duplicate side effects from the stale consumer.

If the system writes state to a shared store, local cleanup alone is insufficient. Use fencing tokens, leases, or ownership checks so an old consumer cannot keep writing after the partition was handed to a new consumer.

## 3. Distinguishing Revoked, Assigned, and Lost

The three callbacks differ in ownership guarantees and processing timing.

| Situation | Consumer Ownership | How to React |
|---|---|---|
| Partitions about to be revoked in normal rebalance | Consumer is still in handoff and has a cleanup window | Flush required state, finish safe work, and release resources |
| Partitions newly assigned | Consumer has received a new assignment | Initialize state, restore checkpoints, and start processing |
| Partitions lost | Consumer can no longer rely on prior ownership | Do not commit based on stale ownership; fence writes and clean local state |

Do not treat **onPartitionsRevoked** as a generic callback for every partition-loss scenario. When Kafka reports lost partitions, normal revocation may not have happened as expected. Separating both cases prevents committing or writing state from a consumer that already lost ownership.

## 4. How Eager and Cooperative Rebalancing Affect Callbacks

### Eager Rebalancing

With eager assignment strategies, the group typically revokes all existing assignments before distributing new assignments. During that phase, consumers may have to pause processing all partitions, even partitions that end up reassigned back to the same consumer after the rebalance.

Consequently, a small membership change can cause many partitions to be revoked and reassigned. The revoke callback must handle the passed partition collection without assuming only one partition changed.

### Cooperative Rebalancing

Cooperative rebalancing enables incremental partition handoffs. Consumers revoke only the partitions that must move; remaining partitions stay assigned. A common assignment strategy for this approach is **CooperativeStickyAssignor**.

With cooperative rebalancing:

- **onPartitionsRevoked** may receive only a subset of the current assignment.
- The consumer can keep processing partitions that were not revoked.
- **onPartitionsAssigned** reports newly assigned partitions for that cycle.
- Cleanup must be strictly scoped to the partitions provided in the callback.

Never wipe all consumer state when only a subset of partitions is revoked. Key state by **TopicPartition** and modify only entries present in the callback collection.

## 5. Which Thread Executes the Callbacks?

Rebalance callbacks are invoked while the consumer processes polls and group coordination, typically on the same thread executing consumer operations. This carries several operational implications:

- Callbacks should finish quickly to avoid prolonging rebalances.
- Avoid slow database queries, HTTP calls, or external service waits inside callbacks whenever possible.
- Never call **poll()** nested inside a callback.
- Kafka consumers are not thread-safe; never hand the consumer object to another thread for arbitrary API calls.
- Never run lengthy business processing inside callbacks.
- If flushing data is unavoidable, enforce strict timeouts and bound flush volume.

Prolonged callbacks can prevent the consumer from polling on time, triggering further rebalances or exceeding **max.poll.interval.ms**. If cleanup requires heavy work, checkpoint state periodically during record processing so callbacks only finish the small remaining delta.

With Spring Kafka concurrency greater than one, the container runs multiple child consumers. Callbacks execute per consumer and its own assignment. Any state shared across callbacks needs proper synchronization; never assume callbacks from all consumers run sequentially on one thread.

## 6. Registering the Listener Directly with Kafka Consumer

In the raw Kafka client, applications register **ConsumerRebalanceListener** when subscribing to topics:

~~~java
import java.util.Collection;
import java.util.List;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRebalanceListener;
import org.apache.kafka.common.TopicPartition;

public class OrderRebalanceListener
        implements ConsumerRebalanceListener {

    @Override
    public void onPartitionsRevoked(
            Collection<TopicPartition> partitions) {

        // Save completed state and release resources
        // belonging to partitions about to be revoked.
        stateStore.flush(partitions);
        stateStore.release(partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Collection<TopicPartition> partitions) {

        // Initialize state for newly assigned partitions.
        stateStore.initialize(partitions);
    }

    @Override
    public void onPartitionsLost(
            Collection<TopicPartition> partitions) {

        // Ownership is lost: do not commit based on stale assignment.
        stateStore.markOwnershipLost(partitions);
    }
}
~~~

Registering the listener:

~~~java
consumer.subscribe(
        List.of("orders.created"),
        new OrderRebalanceListener()
);
~~~

This example focuses on state lifecycle. **stateStore** is an application-built component; Kafka does not provide flush, release, or initialize methods itself.

In raw Kafka interface callbacks, the listener receives only the partition collection. If consumer operations such as seek are needed, use Spring Kafka's extended callback or a design compatible with your running consumer API. Never store the consumer in a field to invoke it from another thread.

## 7. Integrating ConsumerRebalanceListener in Spring Kafka

Spring Kafka allows attaching a listener to the listener container's **ContainerProperties**. Because the container manages the consumer, this centralizes callback registration alongside listener factory configuration.

There are two options:

- Use Kafka's **ConsumerRebalanceListener** when only the partition list is needed.
- Use Spring Kafka's **ConsumerAwareRebalanceListener** when you also need the **Consumer** inside callbacks, e.g., to call **seek()** or query consumer positions per partition.

**ConsumerAwareRebalanceListener** extends Kafka's listener and provides extra callbacks to coordinate with container-managed offset commit ordering.

### 7.1 Configuring the Listener Factory

The example below uses Spring Kafka 3.x and **ConsumerAwareRebalanceListener**:

~~~java
import java.util.Collection;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        PartitionStateStore partitionStateStore) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties()
            .setConsumerRebalanceListener(
                    new ConsumerAwareRebalanceListener() {

        @Override
        public void onPartitionsRevokedBeforeCommit(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            // Flush state before the container commits pending offsets.
            partitionStateStore.flush(partitions);
        }

        @Override
        public void onPartitionsRevokedAfterCommit(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            // Finish cleanup after the container commit step.
            partitionStateStore.release(partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            partitionStateStore.initialize(partitions);
        }

        @Override
        public void onPartitionsLost(
                Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {

            // Do not assume permission to commit these partitions.
            partitionStateStore.markOwnershipLost(partitions);
        }
    });

    return factory;
}
~~~

Callback names and signatures must match your Spring Kafka and Kafka client versions. If an older client lacks **onPartitionsLost**, omit that override or upgrade dependencies per your application's compatibility plan.

**onPartitionsRevokedBeforeCommit** and **onPartitionsRevokedAfterCommit** are Spring Kafka extensions. They let you place cleanup operations before and after the container processes pending offset commits. This is especially useful when an application must flush state before committing and release resources after committing.

Do not call extra commits inside callbacks simply because you have access to **Consumer**. The listener container already manages offsets per acknowledgment mode and commit settings. If the application manages commits manually, designate a single clear owner and understand the consequences of synchronous commits inside callbacks.

### 7.2 Wiring the Factory to @KafkaListener

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-projection",
        containerFactory = "ordersKafkaListenerContainerFactory"
    )
    public void onOrderCreated(OrderCreated event) {
        orderProjection.apply(event);
    }
}
~~~

The container uses the configured factory, so the listener's consumers register the corresponding rebalance listener. If an application has multiple listener factories, configure callbacks on the right factory; never assume all **@KafkaListener** endpoints share one rebalance listener.

### 7.3 Why Does ConsumerAwareRebalanceListener Provide Consumer?

In **onPartitionsAssigned**, the **Consumer** parameter can be used to act on the consumer executing the callback. One scenario is seeking from a custom checkpoint:

~~~java
@Override
public void onPartitionsAssigned(
        Consumer<?, ?> consumer,
        Collection<TopicPartition> partitions) {

    for (TopicPartition partition : partitions) {
        Long nextOffset = checkpointStore.loadNextOffset(partition);

        if (nextOffset != null && nextOffset >= 0) {
            consumer.seek(partition, nextOffset);
        }
    }
}
~~~

This is strictly an example for systems with an application-managed checkpoint store. Before using it, clarify:

- Whether checkpoints store the next offset to read or the last processed record's offset.
- Whether checkpoints are updated only after business side effects commit.
- Behavior when no checkpoint exists.
- Relationship between custom checkpoints and Kafka committed offsets.
- How to handle seeking to an offset expired by retention or no longer present.

If custom checkpoints and committed offsets diverge, the application may skip unprocessed records or re-read large ranges. In most cases, letting Kafka manage committed offsets via the container is sufficient; use seek only when a clear business requirement demands it.

## 8. Coordinating Rebalance Callbacks with Offset Commits in Spring Kafka

Spring Kafka offers acknowledgment modes controlling how the container records processing progress. Common modes include:

| Ack mode | High-Level Behavior |
|---|---|
| **RECORD** | Commits offset after each record is successfully processed by the listener |
| **BATCH** | Commits offsets after records in a poll batch are successfully processed |
| **MANUAL** | Listener actively acknowledges; container manages commits per mode semantics |
| **MANUAL_IMMEDIATE** | Commits immediately when acknowledged on the consumer thread; behavior also depends on calling thread |

Check exact names and details against your Spring Kafka version. Whichever mode is chosen, define what milestone guarantees a record was safely processed.

A typical flow during normal partition revocation:

1. The container detects a rebalance and prepares to process outgoing assignments.
2. Spring Kafka's pre-commit callback is invoked if using **ConsumerAwareRebalanceListener**.
3. The container handles pending offset commits as configured.
4. The post-commit callback is invoked.
5. The consumer finishes handing off partitions per the rebalance protocol.

Exact ordering between callbacks and commits depends on API, version, and listener type. Rely on the dedicated pre/post-commit callbacks Spring provides rather than guessing ordering by putting logic in a generic callback.

### Offset Commits Do Not Replace Business Checkpoints

A Kafka offset represents the position a consumer group confirmed within a partition. It does not by itself prove a database transaction, HTTP request, or external side effect succeeded.

For instance, a consumer updates a database and then the process crashes before committing the offset. The record may be redelivered after a rebalance. This is standard at-least-once behavior. Consumers need idempotency or an inbox mechanism so redelivery does not duplicate side effects.

Conversely, if the application commits offsets before side effects are durable, records can be skipped after a crash. Thus, revoke callbacks cannot fix inverted processing order in the listener; they only help finalize partition handoff cleanly.

## 9. Managing State Per Partition

An application maintaining per-partition state should store state in a map or registry keyed by **TopicPartition**, rather than one shared state variable for the whole consumer.

Model example:

~~~java
Map<TopicPartition, PartitionState> states;
~~~

When partitions are assigned, the application creates or restores **PartitionState**. When revoked, the application flushes and releases only the partitions in the callback. When lost, the application marks ownership lost and disables writes from the stale owner.

Rules to follow:

- Every flush, release, and initialize operation must accept a specific collection of partitions.
- Cleanup must be idempotent because callbacks or shutdown paths may clean state across multiple lifecycle hooks.
- Never delete state for partitions still retained during a cooperative rebalance.
- If state is shared across instances, use fencing tokens, leases, or ownership checks to prevent an old consumer from overwriting a new consumer's data.
- If state is recoverable from Kafka or a database, store enough metadata to detect stale or invalid checkpoints.

For large state stores, update state periodically during record processing. Revoke callbacks should only flush the remaining final delta rather than persisting an entire large state store all at once.

## 10. Common Callback Implementation Mistakes

### Running Slow Work Inside Callbacks

Calling external APIs or waiting on databases inside callbacks can stall rebalances. The fix is periodic checkpointing, bounding remaining work in callbacks, and enforcing cleanup timeouts.

### Wiping All State When One Partition Is Revoked

With cooperative rebalancing, a consumer may lose only part of its assignment. Clean up only the partitions passed into the callback.

### Committing Offsets After Partitions Are Lost

When the lost callback fires, the consumer no longer holds safe ownership. Do not attempt to commit based on the stale assignment. Rely on the new consumer and idempotency to reprocess unconfirmed work.

### Calling Manual Commits Alongside Container Commits

The Spring Kafka container may already manage commits per ack mode. Adding **commitSync()** inside callbacks without clear offset-ownership boundaries can cause premature commits or unpredictable behavior.

### Keeping the Consumer Reference for Another Thread

Kafka consumers are not thread-safe. Never pass the Consumer object into an executor to call **seek**, **commitSync**, or **pause** arbitrarily. Consumer operations should run on the consumer-owning thread or through Spring Kafka coordination APIs.

### Assuming Assigned Always Contains All Partitions

With cooperative rebalancing, callbacks may include only newly assigned partitions. Initialize or restore strictly for the passed partition set.

### Ignoring Cleanup Errors

If flushing state fails, logs and metrics must identify the affected partitions. Never mark a checkpoint successful when data was not persisted. Design cleanup to be safely retryable without blocking callbacks indefinitely.

### Using Callbacks as a Substitute for Lag Management

A rebalance listener is not a lag-management tool. Rising lag must be investigated via processing speed, concurrency, partition counts, downstream dependencies, and poll settings.

## 11. Consumer Settings Related to Rebalancing

Several properties influence rebalance frequency and behavior:

| Property | Role | Operational Notes |
|---|---|---|
| **group.id** | Consumer group identifier | Consumers with different group IDs belong to different groups |
| **partition.assignment.strategy** | Selects the partition assignor | Cooperative assignors can reduce how many partitions must be revoked |
| **session.timeout.ms** | Time the coordinator waits for heartbeats before marking a consumer inactive | Too low risks evicting consumers on brief glitches |
| **heartbeat.interval.ms** | Heartbeat cadence in protocols using separate heartbeats | Typically lower than session timeout per Kafka constraints |
| **max.poll.interval.ms** | Maximum time between polls while processing | Processing too long can force the consumer out of the group |
| **max.poll.records** | Caps records returned in one poll | Tune alongside per-record processing duration |
| **group.instance.id** | Static member identity when using static membership | Can cut rebalances on controlled restarts; requires unique ID per instance |

Spring Boot configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      properties:
        max.poll.interval.ms: 300000
        session.timeout.ms: 45000
        heartbeat.interval.ms: 15000
        max.poll.records: 200
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

These are illustrative values, not universal defaults for every system. Actual processing times, partition counts, traffic, and Kafka versions must be measured before tuning.

Lowering **max.poll.records** can shorten batch processing time, though it may also reduce throughput. Raising **max.poll.interval.ms** allows longer batch processing, but does not fix a slow downstream dependency. Cooperative assignors reduce partition churn in many cases, though they do not eliminate all rebalances.

## 12. Observing Rebalances in Production

Monitor both consumer metrics and callback telemetry. Useful indicators include:

- Rebalance counts by consumer group and instance.
- Duration from rebalance start until consumers resume steady processing.
- Count of revoked, assigned, and lost partitions.
- Execution duration of each callback.
- Errors flushing checkpoints or cleaning state.
- Offset commit failures.
- Consumer lag and processing rate before/after rebalances.
- Consumer evictions due to **max.poll.interval.ms** violations or missed heartbeats.

Callback logs should include group ID, client ID, consumer instance, topic, partition, callback type, and timestamp. Never log just "rebalance happened"; partition details show whether assignments shifted as expected.

Structured log example:

~~~text
event=consumer_rebalance
group_id=order-projection
client_id=consumer-2
callback=onPartitionsRevoked
partitions=orders.created-2,orders.created-3
duration_ms=18
~~~

Values above are illustrative. Avoid logging payloads or sensitive secrets in rebalance logs.

If callbacks run slowly, investigate database flushes, lock contention, state stores, or network calls inside callbacks. If rebalances recur frequently, check coordinator logs, poll intervals, heartbeats, consumer restarts, subscriptions, and network health.

## 13. Testing ConsumerRebalanceListener

Unit tests can verify cleanup and state transition logic by invoking callbacks with mock **TopicPartition** sets. However, unit tests do not prove the group coordinator and assignor fire callbacks accurately in real scenarios.

Integration tests against a real Kafka broker should cover:

1. A consumer receives initial assignments and initializes state for assigned partitions.
2. A second consumer joins the group and triggers a rebalance.
3. The existing consumer cleans up only the actually revoked partitions.
4. The new consumer initializes state for its assigned partitions.
5. A consumer loses connectivity or ownership and the lost path is handled if supported by the client version.
6. Callbacks neither lose processed offsets nor skip unprocessed records.
7. Cooperative rebalancing preserves state for non-revoked partitions.
8. Listener cleanup does not exceed poll deadlines or trigger repeated group rebalances.

When testing callbacks, verify partition state before and after rebalances, not just that callbacks were invoked. A test might confirm **onPartitionsRevoked** ran while missing a bug that wiped state for retained partitions.

## 14. Implementation Checklist

**Callback Design**

- [ ] Identified all state or resources scoped to partitions.
- [ ] Distinguished normal revocation, new assignment, and partition loss.
- [ ] Callbacks operate strictly on the partitions passed to them.
- [ ] Cleanup is safely idempotent and preserves state of retained partitions.
- [ ] Fencing or ownership checks exist if state is shared across consumers.

**Spring Kafka Integration**

- [ ] Listener is attached to the right container factory.
- [ ] Chosen **ConsumerRebalanceListener** vs. **ConsumerAwareRebalanceListener** as needed.
- [ ] Understood Spring Kafka's pre/post-commit callbacks.
- [ ] Ack mode and offset commit strategy are explicitly defined.
- [ ] No duplicate manual commits conflicting with the container.
- [ ] No Consumer API calls from external threads.

**Performance and Reliability**

- [ ] Callbacks are short and never wait unboundedly on external services.
- [ ] Flushes/checkpoints run periodically during normal processing.
- [ ] **max.poll.interval.ms**, heartbeats, and session timeouts match workload.
- [ ] Cooperative/eager assignor behavior has been accounted for.
- [ ] Consumers are idempotent to tolerate redeliveries after rebalances.

**Observability and Testing**

- [ ] Logs/metrics cover revoke, assigned, lost, callback duration, and commit failures.
- [ ] Tested consumer join, leave, restart, and network loss scenarios.
- [ ] Tested callbacks receiving only partial partition subsets.
- [ ] Verified state and offsets are neither lost nor corrupted after rebalances.

## 15. Operational Principles

ConsumerRebalanceListener is the integration point for partition assignment lifecycles. **onPartitionsRevoked** gives the application a chance to finish cleanup before a normal handoff; **onPartitionsAssigned** allows initializing state upon receiving partitions; **onPartitionsLost** handles situations where ownership has already been lost.

In Spring Kafka, attach the listener to the proper container factory and use **ConsumerAwareRebalanceListener** when consumer access or pre/post-commit coordination is needed. Keep callbacks short, scope state by **TopicPartition**, respect container commit mechanics, and protect shared state with idempotency or fencing. When these rules are clear, consumers can shift assignments while preserving processing progress and resilience when group members fail.
