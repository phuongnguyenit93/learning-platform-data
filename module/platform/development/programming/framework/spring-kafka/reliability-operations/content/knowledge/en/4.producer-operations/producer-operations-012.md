# Producer fencing and zombie instances

In a multi-replica Spring Kafka system, a situation can occur where an older instance loses connectivity or hangs without actually terminating. Meanwhile, the system starts a replacement instance to continue processing. When the old instance resumes, both may try to write data using a producer identity that the system considers a single logical producer. Kafka resolves this situation with **producer fencing**.

Producer fencing uses `transactional.id` and producer epoch to ensure only the latest producer session owning a transactional identity is allowed to continue transactional operations on Kafka. It is a vital mechanism in transactional consume-process-produce pipelines, especially during application restarts, failovers, or ownership handoffs between instances.

## 1. What is a zombie instance?

A zombie instance is an old process that can still execute work after the system has decided to replace it or revoke its ownership. The process may have stalled due to a long pause, network partition, container orchestration failure, or isolation from the control plane. Later, it resumes running after a new instance has already taken over the work.

For example, an order-processing service should have only one active producer emitting events for a logical worker:

```text
Time 1: worker-A is active

        worker-A  ---- writes transaction ----> Kafka

Time 2: worker-A pauses/loses network; system starts worker-B

        worker-A  .... unresponsive ....
        worker-B  ---- takes ownership ----> Kafka

Time 3: worker-A comes back alive

        worker-A  ---- tries to keep writing --> Kafka
        worker-B  ---- is current owner --------> Kafka
```

Without fencing, `worker-A` could continue sending data even though `worker-B` has taken over. This creates two processes acting as one logical producer, making it difficult to maintain ordering and transaction atomicity.

A zombie is not necessarily a dead process. The key point is that it has lost ownership according to the system's decision, yet can still perform partial work.

## 2. How Kafka fencing works using transactional.id and epoch

A transactional producer is configured with a `transactional.id`. When the producer initializes transaction support, it registers with Kafka's transaction coordinator via `InitProducerId`. The coordinator issues or restores a producer identity and attaches an **epoch** to that identity.

The epoch is the producer's generation number. When a new producer initializes with the same `transactional.id`, the coordinator increments the epoch and grants authority to the new generation. Transactional requests from the old producer carrying a lower epoch are rejected by the broker because that producer has been fenced.

```text
transactional.id = orders-worker-0

1. worker-A calls InitProducerId
   Kafka issues producerId=P, epoch=4

2. worker-A pauses; worker-B initializes same transactional.id
   Kafka keeps logical producer identity and bumps epoch to 5

3. worker-B sends and commits transaction with epoch=5
   -> accepted

4. worker-A resumes and sends/commits with epoch=4
   -> fenced, rejected by broker
```

As a result, Kafka only accepts operations from the current epoch for that transactional identity. Uncommitted transaction operations cannot be completed by `worker-A` once `worker-B` has assumed ownership. Consumers configured with `isolation.level=read_committed` will not read records belonging to aborted transactions.

Producer fencing does not delete previously committed records. It prevents an old producer from continuing to operate under an identity claimed by a newer generation; open transactions may be aborted or resolved by the coordinator according to transaction state.

## 3. Why is fencing necessary for transactions?

A Kafka transaction can combine writing multiple output records and committing input offsets into a single atomic unit. However, that atomicity requires a single producer holding valid ownership. If two producer sessions could commit for one logical identity simultaneously, the system would lack a clear boundary between the old owner and the new owner.

Fencing establishes generational boundaries:

- A new producer initializing with the same `transactional.id` takes over with a new epoch.
- The old producer cannot continue sending or committing transactions using an outdated epoch.
- Uncommitted transactions from the old producer are not treated as committed data by `read_committed` consumers.
- The new producer can continue work under the same logical identity after ownership transfer.

This is especially useful during application restarts or failovers. If an open transaction was left behind by a prior session, the coordinator can resolve its state when the new producer initializes with the same transactional identity.

Fencing also surfaces misconfigurations: if two active instances accidentally share the same transactional identity, one instance can repeatedly fence the other. This usually signals that identity assignment or replica deployment needs to be fixed.

## 4. Distinguishing transactional.id, producerId, epoch, and idempotence

These concepts are related, yet do not replace one another:

| Component | Role |
|---|---|
| `transactional.id` | Stable identity of a logical transactional producer; used by the coordinator to recognize a producer across sessions. |
| `producerId` | Internal ID assigned by Kafka to a producer to manage sequences and transactions. |
| `epoch` | Generation number of the producer identity; a newer epoch invalidates requests from older epochs. |
| Idempotent producer | Uses producer ID and sequence to prevent duplicates from send-layer retries within a producer session. |
| Producer fencing | Revokes the old producer's authority when a new producer initializes with the same `transactional.id`. |

Idempotence alone does not solve split-brain between two instances. Two instances can be two independent producers with two different producer IDs; each producer's idempotence has no awareness that both represent one logical worker. Only fencing based on `transactional.id` resolves ownership across generations of the same identity.

Conversely, fencing does not replace idempotence. Transactional producers still require appropriate delivery guarantees to handle producer-layer retries. When using transactions, the Kafka client usually requires idempotence-compatible producer settings; let Spring Kafka and the Kafka client apply compatible defaults for your version, or inspect producer properties if you override configuration.

## 5. Assigning transactional.id properly in Spring Kafka

Spring Kafka typically configures `transaction-id-prefix` on the producer. `DefaultKafkaProducerFactory` uses a prefix and suffix to construct transactional IDs for producers it manages. Suffixes let one application run multiple concurrent transactional producers without manually crafting an ID per send.

Spring Boot configuration example:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${APP_INSTANCE_ID:local}-
      acks: all
    consumer:
      properties:
        isolation.level: read_committed
```

In a single-process development environment, `local` may suffice. In multi-replica environments, `APP_INSTANCE_ID` must be supplied per the system's identity strategy. Never leave all replicas falling back to the `local` default.

Example with two active-active replicas:

```text
Replica 0: APP_INSTANCE_ID=orders-worker-0
           transactional.id has prefix orders-worker-0-

Replica 1: APP_INSTANCE_ID=orders-worker-1
           transactional.id has prefix orders-worker-1-
```

Each replica has its own prefix so it does not accidentally fence another replica's producer. Within each replica, the factory manages suffixes for concurrently created transactional producers.

### 5.1 Choosing identity by deployment model

The golden rule is: **producers that can run concurrently must have different transactional IDs; replacement generations of the same logical producer must reuse the identity if mutual fencing is desired.**

| Model | How to assign identity | Reason |
|---|---|---|
| Active-active, multiple replicas processing independently | Each replica gets a distinct, unique prefix while running | Replicas must not fence one another. |
| Active-passive, single owner per logical worker | Replacement instance reuses the logical worker's stable prefix | The new instance will fence the old session if the old session is still alive. |
| StatefulSet or sharded workers with stable ordinals | Include ordinal/shard as part of identity | When replacing a replica in the same slot, identity is reused; different slots stay separate. |
| Pods with random names on every deploy | New Pod name creates a new identity | Avoids collisions, yet does not automatically fence the old Pod; requires orchestration to ensure the old Pod lost authority. |

Do not share one prefix across all active-active replicas. If `orders-worker-0` and `orders-worker-1` initialize the same transactional ID, they can continuously fence each other, causing aborted transactions and processing failures.

Conversely, if an active-passive logical worker always generates a new random prefix on every restart, the new instance does not share a transactional identity with the old instance. Kafka then cannot use the new identity initialization to fence the old session. If a zombie can still reach Kafka, another ownership mechanism or a stable identity for the logical worker is required.

### 5.2 Identity must be unique across active producers

Set `APP_INSTANCE_ID` from an intentional identity source, such as:

- StatefulSet ordinal combined with application name and environment.
- Logical shard ID assigned by a scheduler.
- Stable instance slot managed by the deployment platform.
- Distinct per-replica ID for active-active deployments.

Do not use values like `localhost`, `default`, or an identical environment variable across all replicas in production. Also avoid generating a random prefix on every startup if the goal is letting a new session fence the old session of the same logical worker.

If the same application has multiple independent transactional `ProducerFactory` beans, ensure the transactional ID ranges they generate do not overlap. In typical setups, use a centrally managed factory and let Spring Kafka assign suffixes. When customizing suffix strategies or caches, ensure enough producer slots for actual concurrency and never reuse a suffix still held by another transaction.

## 6. Combining fencing with listener transactions

In a consume-transform-produce pattern, `KafkaTemplate` and the listener container must join the same transaction via the same `ProducerFactory`. Producer fencing protects transactional producer ownership; the listener container remains responsible for coordinating input offsets.

A typical Spring Kafka setup enables transactions via `transaction-id-prefix`, then attaches a `KafkaTransactionManager` built from that producer factory to the listener container. Example transaction manager declaration:

```java
@Bean
KafkaTransactionManager<String, Object> kafkaTransactionManager(
        ProducerFactory<String, Object> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
```

The listener uses a `KafkaTemplate` created from that same producer factory:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "orderListenerContainerFactory")
public void onOrder(ConsumerRecord<String, Order> record) {
    EnrichedOrder result = processor.enrich(record.value());
    kafkaTemplate.send("orders.enriched", record.key(), result);
}
```

When the container begins a transaction, a transactional producer is acquired from the factory. If a new session initializes with the same transactional ID and bumps the epoch, subsequent operations by the old producer will be rejected by the broker. Fencing errors can surface during send or during transaction commit, depending on when the broker detects the stale epoch.

`read_committed` on downstream consumers ensures they only read records from committed transactions. That property does not enable fencing itself; it controls how consumers observe transaction state. Producer identity and the transaction coordinator perform the actual fencing.

## 7. Recognizing fenced producer errors

When an old producer continues operating after its identity has been claimed by a new producer, the Kafka client can return errors such as:

- `ProducerFencedException` — the producer was fenced by another producer with the same `transactional.id`.
- `InvalidProducerEpochException` — the request carries an epoch no longer valid for the producer identity.

Errors can occur while sending records, committing, or aborting a transaction. Thus, application logs may show the listener finishing business logic while the transaction fails to commit.

This is a fatal ownership error for the old producer session. Do not retry infinitely on the same producer as you would for transient network errors. The old producer has lost ownership; close the old session and let the rightful owner process continue. In Spring Kafka, inspect logs from the listener container, transaction manager, and producer factory to pinpoint where the error surfaced.

Operational signs to watch for:

- Recurring `ProducerFencedException` or `InvalidProducerEpochException`.
- Sudden spike in aborted transactions during rollouts or replica scaling.
- Listener containers repeatedly restarting or failing to commit transactions.
- Two Pods both reporting they are processing the same logical worker/shard.
- `APP_INSTANCE_ID` configured identically across replicas or changing unexpectedly after restarts.

Do not simply increase retry counts when hitting fencing. Retries may bloat logs without ever restoring ownership to the old producer. First determine which instance should be the owner and fix identity assignment or ownership transfer.

## 8. Investigation workflow when fencing occurs

When detecting errors, investigate in the following order:

1. **Identify the affected transactional ID.** Extract prefix, suffix, and instance ID from configuration or producer logs. Do not guess solely from deployment name.
2. **List running instances.** Cross-check which Pods/processes, replicas, shards, or logical workers hold the same identity.
3. **Check deployment timing.** Correlate rollout, restart, autoscaling, node pause, or failover timestamps against error timestamps.
4. **Determine the intended owner.** For active-active, each replica needs its own identity. For active-passive, only one instance may own an identity at any time.
5. **Remove the stale session from the processing path.** If the old instance is a zombie, stop or isolate it to prevent continued non-Kafka business execution.
6. **Fix the identity source.** Ensure prefixes are unique across concurrent replicas and stable across restarts of the same logical owner when fencing is required.
7. **Monitor transactions after recovery.** Confirm fencing errors and transaction aborts return to normal, consumer lag drops, and outputs contain only committed transactions when read with `read_committed`.

During investigation, preserve timestamps, instance ID, transactional ID, topic, partition, offset, and exceptions. These details tie producer errors to a specific rollout or ownership handoff.

## 9. Fencing does not protect side effects outside Kafka

Kafka only fences producer operations inside Kafka. If a zombie instance already called an HTTP API, sent an email, or wrote to a database before being fenced, Kafka cannot automatically roll back those side effects. Example:

```text
worker-A: calls payment API successfully
worker-A: pauses before committing Kafka transaction
worker-B: takes same transactional.id and fences worker-A
worker-A: resumes, Kafka rejects committing old transaction

Result: A's Kafka transaction does not commit,
         but the payment API may already have executed.
```

Therefore, if a processor has side effects outside Kafka, add protection at the target system:

- Use stable idempotency keys, such as event ID or order ID, so external APIs do not execute the same request twice.
- Use unique constraints or deduplication tables in the database to prevent applying the same event multiple times.
- Use a transactional outbox when database updates and event emission must be recorded consistently.
- For resources requiring a single owner, use coordinator-issued leases or fencing tokens and have the storage/API validate the token before accepting writes.

An expired lease alone is just an ownership signal. If an old process can still send commands to storage, storage must verify a fencing token or equivalent mechanism to reject commands from the old owner. Stopping application heartbeats alone does not guarantee a zombie can no longer cause side effects.

## 10. Distinguishing producer fencing from consumer fencing

Kafka has multiple mechanisms to stop an old member from operating after ownership changes. Producer fencing and consumer group fencing address different scopes:

| Mechanism | Target | Common symptoms | Purpose |
|---|---|---|---|
| Producer fencing | Transactional producers using `transactional.id` | `ProducerFencedException`, `InvalidProducerEpochException` | Block producers from an old epoch after a new producer claims the same identity. |
| Consumer group generation/offset fencing | Consumer group members and offset commits | Commit failures due to invalid generation/member | Block old consumers from committing offsets after a group rebalance or membership change. |
| Static membership fencing | Consumers using `group.instance.id` | `FencedInstanceIdException` | Block a consumer with a duplicate static member identity in the same group. |

Do not change `transaction-id-prefix` to fix consumer group errors, and do not change `group.instance.id` to fix `ProducerFencedException`. Read the exact exception and pinpoint the failing component.

## 11. Testing fencing behavior

Integration tests against a Kafka broker verify that the application reacts properly when a producer is superseded. A basic scenario can use two transactional producers configured with the same `transactional.id`:

1. Initialize producer A with identity `fencing-test-worker` and start a transaction.
2. Initialize producer B with the same identity. Initializing B increments the current epoch.
3. Attempt to send or commit using producer A; verify the client receives a fencing or invalid epoch error.
4. Send and commit a transaction using producer B.
5. Read the topic with a `read_committed` consumer; verify only records from the committed transaction appear.

When writing integration tests, control initialization and operation timing between the two producers to avoid race conditions. Close producers and clean up topics after tests. Never run two producers with the same transactional ID in parallel tests unless intentionally testing fencing.

Beyond Kafka client-level tests, test deployment identity configuration as well:

- Two active-active replicas receive different prefixes.
- Restarting a replica reuses the corresponding logical slot's identity.
- Rollouts do not cause all replicas to share a prefix.
- When a session is fenced, listeners do not continue treating that transaction as successful.
- Downstream `read_committed` consumers do not observe outputs of aborted transactions.

These tests validate both broker mechanics and how the platform supplies instance identity to Spring Kafka.

## 12. Common configuration mistakes

- **Using the same `transaction-id-prefix` for all replicas:** producers fight over one identity and continually fence each other.
- **Using a random prefix on every restart of a logical worker:** the new instance fails to reuse the old identity and cannot fence the old session via transactional ID.
- **Sharing one prefix across multiple independent `ProducerFactory` beans:** suffixes can collide if factories do not coordinate identity allocation.
- **Infinitely retrying `ProducerFencedException`:** the old producer already lost ownership; retries cannot resolve the cause.
- **Confusing producer fencing with consumer group fencing:** leads to changing the wrong configuration and missing the true owner.
- **Assuming fencing rolls back databases or HTTP calls:** external side effects still require idempotency or fencing at the target system.
- **Assuming `read_committed` fences producers on its own:** isolation level only controls what consumers observe; it does not authorize producers.
- **Rolling out two instances sharing a logical identity without a handoff plan:** the new instance can fence the old instance right at startup, aborting in-flight transactions during handoff.

## 13. Operations checklist for producer fencing

Before deploying transactional producers, determine:

- What is each logical producer: a replica, a shard, a worker slot, or a singleton service?
- Which instances are allowed to run concurrently and which identities must remain unique among them?
- On restart or failover, must the new instance reuse the old logical owner's identity to fence zombies?
- Does the platform guarantee stopping the old instance before the new instance takes over?
- Do `KafkaTemplate` and the listener container use the producer factory matching the transaction manager?
- Do downstream consumers use `read_committed` when uncommitted or aborted transaction records must be excluded?
- Do databases and external APIs have their own idempotency keys or fencing tokens?
- Do logs capture instance ID, transactional ID, topic, partition, offset, and exceptions for investigation?

Producer fencing is the Kafka-side ownership protection layer. Sound design starts by defining the logical producer, assigning transactional IDs to match deployment topology, and having clear ownership handoff procedures. Combined with idempotency in external systems, the application can handle restarts, failovers, and zombie instances without letting an old producer session keep committing Kafka data.
