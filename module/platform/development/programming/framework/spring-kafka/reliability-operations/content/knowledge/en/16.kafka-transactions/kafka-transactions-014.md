# Producer Fencing in Transactions

When running Kafka transactions, Spring Kafka must do more than make writing records and committing offsets atomic; the system must also determine **which producer holds authority to represent a transactional identity**. If an old instance hangs, loses connectivity, or gets replaced yet later wakes up, it might keep sending requests as if it were still the owner. Kafka uses **producer fencing** to stop an outdated producer session from committing transactions under an identity already taken over by a newer session.

This mechanism is vital in systems running multiple replicas, frequent consumer group rebalances, continuous rollouts, or **read → process → write** flows using Kafka transactions. However, `transactional.id`-based fencing does not automatically solve every zombie consumer scenario; you must distinguish producer epochs, consumer group ownership, and side effects outside Kafka.

## 1. What Does Producer Fencing Protect?

A transactional producer has a `transactional.id`. Kafka brokers use this identity to manage transaction lifecycles and issue a **producer ID/epoch** to the active producer session. When another producer initializes with the same `transactional.id`, the transaction coordinator establishes a new generation; requests from the earlier generation become invalid.

~~~text
                transactional.id = inventory-worker-0

Instance A: Producer A ---------------------> Kafka transaction coordinator
                  epoch = 12                  (old-generation owner)
                      |
                  network interrupted
                      |
Instance B: Producer B ---------------------> Kafka transaction coordinator
                  epoch = 13                  (new-generation owner)
                      |
                      +---- write + commit succeeded
                      
Instance A: revives, tries to send/commit with epoch = 12
                      |
                      +---- broker rejects: producer has been fenced
~~~

Without generation boundaries, two sessions sharing a logical identity could cause **split-brain**, each believing it is authorized to process the same work. Fencing blocks the old session at the Kafka layer, even if the old process has not exited yet.

Key point to remember: Kafka fencing applies to Kafka operations from a transactional producer whose identity was superseded. It **does not automatically cancel an HTTP request or roll back a database transaction** executed earlier.

## 2. transactional.id, producerId, and Epoch

Concepts that appear together yet cannot substitute for one another:

| Concept | Role |
|---|---|
| `transactional.id` | Stable logical identity of a transactional producer; brokers use it to track transaction lifecycles across producer sessions. |
| Producer ID (PID) | Identity assigned by Kafka to a producer for managing sequences and transactions. |
| Producer epoch | Generation of the PID/transactional identity; requests carrying an obsolete generation are rejected. |
| Transaction coordinator | Broker coordinating transaction state, producer identity, and commit/abort. |
| Idempotent producer | Prevents duplicates from record send retries within a producer ID/sequence scope. |
| Producer fencing | Blocks an older producer session from operating once its identity is claimed by a newer producer. |

At the protocol level, the producer calls `initTransactions()`, interacting with the transaction coordinator via mechanisms like `InitProducerId`. For an existing transactional ID, Kafka can issue a new generation, invalidating requests from older generations. Applications **do not manually set epochs** via Spring configuration.

Example sequence:

1. Producer A initializes `transactional.id=orders-shard-3`, receiving the current generation.
2. A begins a transaction and sends outputs, then temporarily loses connectivity before committing.
3. Producer B initializes with the **same** `transactional.id` and claims the new generation; the coordinator resolves the old session's unfinished transaction per protocol.
4. B can begin its own transactions once valid initialization completes.
5. A comes back online; the broker sees A's requests carry the old generation and rejects them.
6. A must stop using the fenced producer session; it cannot simply call `commitTransaction()` again to reclaim authority.

Producer fencing does not erase or reverse transactions **already validly committed** before fencing occurred. Its purpose is rejecting operations from sessions that no longer hold authority.

## 3. Why Is Fencing Necessary When a Kafka Transaction Is Interrupted?

A Kafka transaction can span multiple output records and consumer group input offsets. When all Kafka work lives in the same transaction:

~~~text
Consumer poll orders.in
         |
         v
Kafka transaction begins
         |
         +---- business processing
         +---- send orders.out
         +---- send input offset into transaction
         |
         +---- commit transaction
                  |
                  +---- output is committed
                  +---- offset is committed
~~~

If that transaction's producer was fenced by a newer session before commit, the old session **has no authority to complete the transaction**. For downstream consumers using `isolation.level=read_committed`, records from uncommitted or aborted transactions are not treated as committed data for application delivery.

The opposite—letting an old producer session commit even though a new owner is already running—could let two sessions emit outputs for the same logical task. Producer epochs guard that boundary.

Still, **exactly-once in Kafka** applies only within strict boundaries: transactional Kafka outputs and consumer offsets enlisted in the same transaction, paired with proper reading isolation. Fencing alone does not guarantee each listener invocation happens only once; listeners can rerun after rollbacks or rebalances.

## 4. Spring Kafka's Read-Process-Write Flow

In Spring Kafka, the listener container can open a transaction before invoking the listener. `KafkaTemplate` joins the container-managed transaction when configured on a compatible producer factory.

Listener example:

~~~java
@Component
public class OrderProcessorListener {

    private final KafkaTemplate<String, ProcessedOrder> kafkaTemplate;
    private final OrderService orderService;

    public OrderProcessorListener(
            KafkaTemplate<String, ProcessedOrder> kafkaTemplate,
            OrderService orderService) {
        this.kafkaTemplate = kafkaTemplate;
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.in",
            groupId = "orders-processor")
    public void onOrder(ConsumerRecord<String, Order> record) {
        ProcessedOrder result = orderService.transform(record.value());
        kafkaTemplate.send("orders.out", record.key(), result);
    }
}
~~~

With a **transactional listener container** and properly wired `KafkaTemplate`:

- Container starts a transaction before processing.
- Listener sends outputs via `KafkaTemplate` participating in the active transaction.
- Container enlists input offsets into the transaction after valid processing.
- On success, Kafka outputs and offsets commit together.
- Exceptions roll back the transaction; records can be reprocessed via recovery mechanisms.
- If the producer is fenced, the old transaction cannot validly commit; the container must handle the error at the transaction/producer layer.

If the listener runs under a container **without** transactions enabled, the Java code above does not automatically get atomic read-process-write. Using `KafkaTemplate` or enabling producer idempotence alone does not establish Kafka transactions.

## 5. Spring Boot Configuration: transaction-id-prefix

Spring Boot enables Kafka transactions for producers via `transaction-id-prefix`. With suitable auto-configuration, Boot supplies `KafkaTransactionManager` and integrates with the default listener container.

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      transaction-id-prefix: "${APP_INSTANCE_ID:local}-orders-tx-"
      acks: all
    consumer:
      group-id: orders-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

In a single-instance local environment, the prefix `local-orders-tx-` is convenient for testing. **Never leave this same default across all production replicas.** Every concurrent replica needs its own transactional ID namespace unless intentionally representing the same logical producer.

Spring Kafka's `DefaultKafkaProducerFactory` combines the prefix with suffixes to construct transactional IDs for factory-managed producers. How suffixes, caching, and concurrent producer caps work depends on version and factory settings. Therefore, ensure no two active factories/replicas generate the same full transactional ID.

Downstream consumers require `read_committed` if they must not read records from aborted transactions. This is a **reading isolation** setting, not a switch that enables producer fencing.

### 5.1. Creating a transaction manager with a custom factory

When an application does not rely solely on Boot's default configuration, declare the manager explicitly:

~~~java
@Bean
KafkaTransactionManager<String, ProcessedOrder> kafkaTransactionManager(
        ProducerFactory<String, ProcessedOrder> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

The listener container must use this transaction manager, and `KafkaTemplate` must use the matching producer factory to join the same transaction. Some Spring Kafka versions use `setKafkaAwareTransactionManager(...)` to configure the container, whereas earlier versions use a different API; use the exact API of your deployed dependency.

Do not create two producer factories with colliding transactional IDs managing transactions independently while assuming the framework automatically coordinates ownership between them.

## 6. Assigning Transactional IDs Across Multiple Replicas

This is the single most common source of fencing errors in Spring Kafka. Distinguish **concurrent producers** from **replacement producers**.

| Pattern | Identity rule | Meaning |
|---|---|---|
| Active-active, multiple independent instances | Unique prefix per concurrently active instance | Prevents instances from accidentally fencing each other. |
| Single logical worker with replacement session | Stable identity for that logical worker when the new producer should fence the old one | When the same ID reinitializes, the old session loses authority. |
| Cluster with multiple stable shards | Bind identity to shard or worker slot per coordination policy | Shards are isolated; a replacement for a shard can reuse its identity. |
| Pods assigned random IDs on every restart | New identity never matches old instance | Avoids collisions yet **does not automatically fence zombies** via shared transactional ID; protect ownership via other means. |

Example of two active-active replicas:

~~~text
Replica A:
  APP_INSTANCE_ID=orders-a
  transaction-id-prefix=orders-a-orders-tx-

Replica B:
  APP_INSTANCE_ID=orders-b
  transaction-id-prefix=orders-b-orders-tx-
~~~

The prefixes do not overlap. While A and B run concurrently, each uses its own Kafka transactions without fencing the other instance's producers.

For an **active-passive slot** where only one instance may represent that slot, a replacement session can be designed to reuse the slot's stable identity. The new producer can then fence the old one **if they genuinely initialize with the exact same full transactional ID**. Sharing a prefix alone is insufficient if the two processes allocate different suffixes. Understand how the factory manages suffixes and enforce ownership coordination at the application/orchestrator layer.

Specifically, avoid sharing one prefix `orders-tx-` across an active-active cluster: when factories produce overlapping suffixes, producers steal each other's transactional identities. Symptoms include aborted transactions, listener failures during rollouts, and continuous instance restarts.

## 7. Producer Fencing and Zombie Consumers Are Not Identical

A **zombie producer** is a producer session that lost valid ownership of a transactional identity yet keeps trying to write/commit. A **zombie consumer** is an old group member that lost partition ownership after a rebalance yet keeps processing already polled work.

Two distinct mechanisms:

1. **Transactional-ID fencing**: a new producer using the same `transactional.id` invalidates the older epoch.
2. **Consumer-group fencing/ownership**: Kafka consumer groups manage generations, member metadata, and partition assignments. Stale offset operations are rejected per current group state.

In Kafka/Spring Kafka's newer exactly-once model (often called **EOS V2**, associated with KIP-447), consumer group metadata participates when sending consumer group offsets into Kafka transactions. That allows brokers to validate consumer ownership when committing transactional offsets; applications do not need to share the same `transactional.id` across distinct replicas just to fence zombie consumers. Hence, Spring Kafka recommends **unique transactional ID prefixes per active instance** in modern EOS setups.

Do not assume distinct `transactional.id` values automatically stop an old instance from calling a database/API after a rebalance. Kafka guards offsets and transactions with Kafka mechanisms, whereas external targets still need idempotency or fencing tokens if strict single-owner protection is required.

### 7.1. Distinguishing exceptions

| Exception/scenario | Scope | Primary meaning |
|---|---|---|
| `ProducerFencedException` | Transactional producer | Producer no longer holds authority for the transactional identity. |
| `InvalidProducerEpochException` | Kafka producer request | Epoch carried by the request is no longer valid. |
| `FencedInstanceIdException` | Static consumer group membership | Conflict or replacement of a member with `group.instance.id` in the consumer group. |
| Commit errors from invalid group generation/member | Consumer group/offsets | Consumer no longer holds permission to commit offsets as a current member. |

Do not tweak `transaction-id-prefix` to fix consumer group errors. Conversely, do not tweak `group.instance.id` when the real bug is two transactional producers sharing an identity.

## 8. A Fencing Scenario During Rollout

Suppose an active-passive deployment enforces that only one logical worker emits output.

~~~text
T0: Instance A processes order-100, transaction TA is open
T1: A experiences a long pause; system starts replacement instance B
T2: B claims authority with the same transactional identity
T3: Coordinator issues new epoch; session A is fenced
T4: B processes record and commits transaction TB successfully
T5: A resumes and tries to commit TA
T6: Broker rejects TA; A receives producer fenced error
~~~

Kafka outcomes:

- TA cannot be validly committed by A once fenced.
- TB can commit if B meets transaction/group ownership conditions.
- `read_committed` consumers never treat TA's aborted output as committed data.
- Processed records whose input offsets were not committed remain eligible for redelivery.
- If A called an external API before T1, that API **does not roll back** just because the producer was fenced.

In active-active setups, two valid instances **must not** share a transactional identity. Using distinct identities together with Kafka consumer group metadata is a different pattern from replacing a singleton owner with a new session sharing one identity.

## 9. How Should ProducerFencedException Be Handled?

`ProducerFencedException` is generally **fatal to the fenced producer session**. Do not treat it like a timeout to retry indefinitely on the same `KafkaProducer` instance.

Principled handling steps:

1. Let the transaction/container observe the error; never catch it and treat the record as succeeded.
2. Stop attempting `send()` or `commitTransaction()` on the old producer that lost authority.
3. Close/discard the broken producer session via framework management.
4. Identify which instance legitimately owns the transactional identity.
5. Diagnose the cause: duplicate identity, rebalance, rolling restart, or producer factory config.
6. Let the valid system initialize a fresh producer session/transaction per standard lifecycle.
7. Ensure outputs and input offsets commit only via valid transactions.

Do not repeatedly call `abortTransaction()` on a producer in a fatal state expecting it to return to normal operation. Kafka's producer API separates recoverable errors from fatal errors; upon fencing, the old producer must be retired.

### 9.1. Spring Kafka listener container

Some Spring Kafka versions support `ContainerProperties.setStopContainerWhenFenced(true)`. When enabled, the container can stop upon detecting a fenced producer instead of continuing its processing loop. This is worth considering when fencing signals an instance lost ownership and should be replaced/investigated by orchestration.

~~~java
factory.getContainerProperties().setStopContainerWhenFenced(true);
~~~

Assess the impact of stopping the container: does your deployment have restart policies or alerts, who takes over consumer lag, and what non-Kafka tasks is the old instance still running? This option does not fix configuration-level collisions and does not substitute for unique prefixes.

Whether the container stops, emits lifecycle events, or throws specific exceptions can vary by Spring Kafka version; rely on logs and integration test results for your exact version.

## 10. Why Not Retry Immediately on the Old Producer?

When a request is rejected due to an obsolete epoch, resending the same request on the same producer session cannot produce a valid epoch. It is not a transient network glitch that client retries can heal.

Comparison:

| Error type | Handling |
|---|---|
| Transient broker leader change | Kafka client can retry via producer mechanics while within valid bounds. |
| Request timeout with uncertain outcome | Follow idempotence/transaction semantics and timeouts; do not assume total failure. |
| Transaction timeout | Transaction is no longer valid; handle abort/reinitialization per producer state. |
| Producer fenced | Old producer session lost ownership; stop using session and verify owner. |
| Deserialization/business error | Error handler or `AfterRollbackProcessor` handles the record; does not mean the producer was fenced. |

If you try to "retry" by spinning up a fresh producer with **the same transactional ID on every active instance**, the system can enter a mutual fencing ping-pong loop. Fix ownership/configuration rather than raising backoff.

## 11. Transaction Timeout Differs from Fencing

Kafka has timeouts that affect transactions and producers:

- `transaction.timeout.ms`: bounds how long a transaction may remain open; the transaction coordinator can abort overdue transactions.
- `delivery.timeout.ms`, `request.timeout.ms`: producer send/request bounds.
- Broker `transactional.id.expiration.ms`: an unused transactional identity can expire after a long idle period per broker policy.
- Producer cache lifetime/age in Spring Kafka: can affect reusing long-cached producers.

A timed-out transaction is not necessarily caused by another producer fencing it. Conversely, producer fencing can occur immediately when a new session initializes with the same identity, even before the old transaction nears its timeout.

Never raise transaction timeouts to "cure" shared `transactional.id` configurations across replicas. Those are distinct issues requiring separate diagnoses.

### 11.1. Producer cache and maxAge

Spring Kafka can cache transactional producers for reuse. If a producer sits idle in the cache too long, the broker may expire its transactional identity before the client reuses it. Some versions of `DefaultKafkaProducerFactory` support `setMaxAge(Duration)` to replace cached producers before reaching expiration thresholds.

~~~java
defaultKafkaProducerFactory.setMaxAge(Duration.ofDays(3));
~~~

The value above is illustrative only. Set max age according to broker settings and real traffic patterns, safely below the broker's idle expiration threshold. Never assume all brokers share the same expiration duration.

`maxAge` governs cached producer lifecycles; it **does not fix** two instances concurrently sharing a transactional ID or external zombies outside Kafka.

## 12. Exactly-Once, Idempotence, and Fencing

Three frequently confused mechanisms:

- **Producer idempotence**: eliminates duplicates from producer send retries using sequence numbers.
- **Kafka transactions**: group multiple output records and transactional input offsets into an atomic commit/abort unit.
- **Producer fencing**: eliminates the ability of an outdated producer session to commit under the same transactional identity.

For example, an idempotent producer prevents duplicate writes on batch-send timeouts; however, if two independent apps with different producer IDs emit duplicate business events, idempotence cannot recognize them as logical duplicates.

Similarly, Kafka transactions do not mean business logic executes only once. After rollbacks/rebalances, listeners can process the same event again. Side effects outside Kafka must deduplicate by event ID or business key.

With `read_committed`, consumers see only committed transactional records; this is a consumer isolation level, **not** a producer fencing mechanism.

## 13. Side Effects Outside Kafka: Fencing Gaps

Suppose a listener calls a payment gateway and then emits a result event inside a Kafka transaction.

~~~text
A receives PaymentRequested
A calls payment API -> succeeds, funds captured
A loses connection to Kafka
B replaces A and producer A is fenced
A tries to commit Kafka transaction -> rejected
B re-reads PaymentRequested -> may call payment API again
~~~

Fencing blocks A's Kafka commit, yet does not reverse the first payment capture. If B calls the API again without an idempotency key, double charging can happen.

Necessary measures depending on business logic:

- Pass a stable **idempotency key** derived from event/order/payment ID to external APIs.
- Use unique constraints and processing status in databases to block duplicates.
- Use a transactional outbox when database updates and Kafka event publishing must stay reliable.
- Use sagas/compensation when multiple systems participate in an operation that cannot commit atomically together.
- For resources requiring strict single-owner semantics, use leases and **fencing tokens** validated by the target storage/API before accepting writes.

Kafka producer epochs are not automatically verified by databases or HTTP servers. Unless the target system understands that token, it cannot rely on Kafka producer fencing to reject zombie commands.

## 14. Observing Fencing Errors in Production

Signals worth tracking:

| Signal | Likely correlation |
|---|---|
| `ProducerFencedException` spikes during rollouts | Duplicate transactional IDs or a new owner replacing an old session. |
| `InvalidProducerEpochException` | Requests carrying an obsolete epoch. |
| Rising transaction abort/commit failures | Transaction errors, fencing, or infra issues needing classification. |
| Frequent consumer group rebalances | Instance churn, overload, session/poll issues. |
| Certain replicas repeatedly stopping containers | May be getting fenced with stop-on-fenced enabled. |
| Slow producer transaction init | Coordinator, transaction state, or broker health issues. |
| Consumer lag rising during rollouts | Repeated transaction rollbacks or unstable group membership. |

Useful log fields:

- Application/service/environment, pod or instance ID.
- Transactional ID prefix and full transactional ID when obtainable from logs/clients.
- Input topic, partition, offset, and event ID.
- Consumer group ID and member metadata where relevant.
- Timestamps for transaction init, commit/rollback, and exception class.
- Timestamps for deployments/rebalances/instance restarts.

Avoid logging sensitive data or full payloads merely for investigation. For metrics, avoid ultra-high-cardinality labels such as transaction IDs with ever-changing suffixes if your monitoring system cannot handle the series growth.

### 14.1. Diagnostic procedure

1. **Read the exact exception**: producer fenced, invalid epoch, or consumer membership error?
2. **Find the affected transactional ID**: identify effective prefix and suffix.
3. **List running instances**: are two producers sharing the full transactional ID?
4. **Check rollout/restart timing**: did errors align with overlapping replicas or failovers?
5. **Check consumer group ownership**: did a partition just rebalance or is an old member still processing?
6. **Check producer cache/expiration**: did a transactional producer sit idle longer than broker policy?
7. **Inspect commits/aborts and DLT**: which transactions succeeded, which offsets committed, and what appears to `read_committed`?
8. **Fix identity allocation or handover procedures**: stop infinite retries on de-authorized sessions.
9. **Monitor post-recovery**: confirm fencing errors drop, consumer lag recovers, and no unexpected outputs appear.

## 15. Testing Producer Fencing with Two Producers

An integration test with a real broker can spin up two transactional producers sharing an identity. The Java Kafka client example below shows how a newer session fences an older one:

~~~java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "fencing-integration-test");

try (KafkaProducer<String, String> producerA = new KafkaProducer<>(props);
     KafkaProducer<String, String> producerB = new KafkaProducer<>(props)) {

    producerA.initTransactions();
    producerA.beginTransaction();
    producerA.send(new ProducerRecord<>("fencing-test", "key", "from-A")).get();

    // Initialize B with the same transactional.id: B becomes the new generation.
    producerB.initTransactions();
    producerB.beginTransaction();
    producerB.send(new ProducerRecord<>("fencing-test", "key", "from-B")).get();
    producerB.commitTransaction();

    // A lost ownership; A's commit is no longer valid.
    try {
        producerA.commitTransaction();
        throw new AssertionError("Expected producer A to be fenced");
    } catch (ProducerFencedException expected) {
        // Do not reuse producer A for another transaction.
    }
}
~~~

Across client versions and protocol paths, exceptions may be wrapped or surfaced under an epoch-related Kafka exception type. Tests should verify **session A cannot commit**, rather than depending strictly on one unwrapped class name. This example assumes topic `fencing-test` exists, the broker supports transactions, and finite test timeouts are used.

Use a `read_committed` consumer to verify uncommitted output from transaction A is not delivered as valid data, while output from B becomes readable after commit.

### 15.1. Spring Kafka test scenarios

Beyond raw Kafka client tests, integration tests should cover:

1. Two active-active replicas with distinct prefixes; both process and commit transactions normally.
2. Two replicas intentionally sharing prefix/suffix; one session is fenced, and logs/alerts fire.
3. Restarting a logical worker with a stable identity; the old session cannot commit after handover.
4. Listener emits output then throws an exception; downstream `read_committed` does not read rolled-back output.
5. Consumer rebalances mid-processing; verify transactional offset commits and redelivery.
6. Enable `stopContainerWhenFenced` if supported; verify the container stops and infra observes status accurately.
7. Long-idle cached producer; verify `maxAge` and broker policy in a representative test environment.
8. Non-Kafka API succeeds before transaction rollback; verify idempotency keys prevent duplicate side effects.
9. Transactional DLT/recovery on repeated record failures; verify recovered offsets and DLT outputs remain consistent.

Use latches/assertions on transactions, offsets, and exceptions instead of fixed sleeps. Fencing tests must clean up producers/topics and never share identities with parallel tests.

## 16. Common Configuration Mistakes

- **Using the same `transaction-id-prefix` across all active-active replicas**, causing instances' producers to fence one another.
- **Assuming identical prefixes always fence zombies** when actual suffixes may differ.
- **Generating random prefixes on every restart while expecting same-ID fencing**: the new producer does not share the old producer's identity.
- **Retrying `ProducerFencedException` on the fenced producer itself** without resolving ownership.
- **Mistaking transaction timeouts for fencing** and raising timeouts instead of fixing collisions.
- **Assuming producer fencing automatically stops all zombie consumers** while ignoring group generations/transactional offset metadata.
- **Forgetting to enable the listener transaction manager** while expecting input offsets and Kafka outputs to commit atomically.
- **Reading outputs with `read_uncommitted` in tests** and concluding rolled-back transactions still committed.
- **Assuming Kafka fencing rolls back databases/APIs**; external side effects still require duplicate protection.
- **Ignoring producer cache expiration** when long-idle producers hit unexpected errors.
- **Merely raising retries/backoff during rollouts** without inspecting full transactional IDs and identity assignment.
- **Not measuring fencing errors per instance**, making it hard to tell proper zombie eviction from active split-brain.

## 17. Safe Transaction Design Checklist

Before deploying Spring Kafka transactional listeners to production, determine:

- What is a logical producer: an instance, a shard, or a singleton task?
- Which producers run **concurrently** and thus require distinct transactional IDs?
- Upon owner replacement, must the full transactional ID be reused to fence the prior session?
- How many concurrent suffixes/producer sessions can the Spring Kafka factory allocate?
- How do consumer group metadata and the active EOS version protect against stale ownership?
- Do the listener and `KafkaTemplate` genuinely share the same transaction context?
- Are input offsets enlisted into the transaction before committing outputs?
- Does downstream use `isolation.level=read_committed` when required?
- Are fencing exceptions logged, alerted on, and treated as fatal to the old session?
- Are policies set for transaction timeouts, cache max age, and shutdown?
- Do databases/APIs outside Kafka have idempotency keys, outboxes, or dedicated fencing tokens?
- Do integration tests cover handover, rollbacks, redelivery, and producer fencing?

**Producer fencing in transactions** establishes who holds authority to commit to Kafka when a logical producer is replaced. Proper setup starts by separating transactional identity from consumer group ownership, assigning topology-appropriate prefixes/suffixes, and letting Spring Kafka manage transaction boundaries. Combined with `read_committed` reads, post-rollback recovery, observability, and external idempotency, systems can withstand restarts, rebalances, and zombie instances without allowing outdated producer sessions to write or commit illegitimately.
