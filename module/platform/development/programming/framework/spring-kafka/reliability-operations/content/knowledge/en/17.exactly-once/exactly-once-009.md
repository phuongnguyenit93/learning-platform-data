# Per-instance unique transaction IDs

## 1. Why must transaction IDs be unique per instance?

Kafka supports producer transactions to group multiple records sent to Kafka and, in a consume–process–produce flow, coordinate consumer offsets with output records in a single transaction. The identifier of a **logical transactional producer** to the Kafka broker is `transactional.id`.

When deploying a Spring Kafka application across multiple JVMs, containers, or Kubernetes pods, each instance can create its own transactional producers. **Concurrently active, independent producers must never accidentally share the same `transactional.id`.** If they collide on an ID, Kafka treats the later producer as a newer generation of that logical producer; the older producer can be *fenced* (stripped of permission to perform transactions), causing send or commit errors.

For Spring Kafka, the standard configuration is assigning a **unique `transactionIdPrefix` per instance**. `DefaultKafkaProducerFactory` uses this prefix to generate concrete `transactional.id` values, with factory-managed suffixes for producers inside that instance.

~~~text
Billing application, running 3 instances

Instance A (prefix: billing-tx-a-)
  Producer 1 -> transactional.id: billing-tx-a-0
  Producer 2 -> transactional.id: billing-tx-a-1

Instance B (prefix: billing-tx-b-)
  Producer 1 -> transactional.id: billing-tx-b-0
  Producer 2 -> transactional.id: billing-tx-b-1

Instance C (prefix: billing-tx-c-)
  Producer 1 -> transactional.id: billing-tx-c-0

No ID collisions across active producers.
~~~

The suffixes in the diagram are illustrative examples; the algorithm and suffix allocation depend on the Spring Kafka version, producer factory, and `TransactionIdSuffixStrategy` configuration. What matters is that **all IDs generated for concurrent instances do not collide**.

### 1.1. Lesson goals

In operating Exactly once with Spring Kafka, you need to understand:

- How `transactional.id` differs from `client.id`, `group.id`, and business event IDs.
- Why Kafka producer fencing is an intentional safety mechanism yet also a symptom of misconfiguration when two instances fight over one ID.
- How to supply `transaction-id-prefix` per instance via Spring Boot and Kubernetes.
- How to preserve uniqueness across replica scaling, rolling updates, restarts, and scale down/up.
- How to recognize fencing and investigate transaction failures.
- Why a unique ID is a **necessary condition** for transactional producers, not an exactly-once promise for non-Kafka side effects.

## 2. How are transactional producers identified?

### 2.1. transactional.id is a logical identity

A Kafka client sets `transactional.id` to enable the transactional producer protocol. When a producer initializes transactions, the broker transaction coordinator tracks this logical identity and issues the appropriate producer ID/epoch.

An application can sequentially open many Kafka transactions with the same transactional producer, but cannot open arbitrary overlapping transactions on the same producer. The Kafka transaction API follows this lifecycle:

~~~text
initTransactions
      |
      v
beginTransaction
      |
      +---- send(record A)
      +---- send(record B)
      |
      v
commitTransaction
      |
      v
beginTransaction (next transaction)
~~~

Or, when a rollback-eligible error occurs:

~~~text
beginTransaction
      |
      +---- send(record A)
      +---- handle error
      |
      v
abortTransaction
~~~

`transactional.id` is reused across transactions of the same logical producer, not changed per event or per send call.

### 2.2. Producer ID and epoch

The broker uses producer ID and epoch to distinguish producer generations. When a new producer initializes with the same `transactional.id`, the coordinator can bump the epoch and revoke the old producer's authority to use that identity.

~~~mermaid
sequenceDiagram
    participant A as Producer A
    participant K as Kafka coordinator
    participant B as Producer B

    A->>K: initTransactions with ID billing-tx-7
    K-->>A: Issue PID / epoch n
    A->>K: beginTransaction + send
    B->>K: initTransactions same ID billing-tx-7
    K-->>B: Issue new epoch per protocol
    A->>K: commitTransaction using old epoch
    K-->>A: Producer fenced / invalid epoch
    B->>K: Transact using new epoch
~~~

This is **producer fencing**. Kafka uses it to stop two producer generations from both claiming ownership of a transactional ID and creating inconsistent results.

Fencing is not a load-balancing mechanism. Kafka does not share a single `transactional.id` across multiple instances to increase concurrency. Every active transactional producer needs its own valid identity.

## 3. Why do ID collisions often appear during scaling?

Suppose service `orders-worker` runs three pods with the same configuration:

~~~properties
spring.kafka.producer.transaction-id-prefix=orders-tx-
~~~

If each pod creates its own producer factory, the factories can generate identical suffixes—for example, the first producer on all three pods ends up with an ID ending in `0`.

~~~text
Pod A -> orders-tx-0
Pod B -> orders-tx-0
Pod C -> orders-tx-0

All call initTransactions...
=> Older producers can continuously be fenced.
=> Listener transactions roll back, lag rises, app becomes unstable.
~~~

This configuration may **work normally with a single instance**, yet failures appear after:

- Increasing replicas from 1 to 2.
- Rolling deployments running old and new pods simultaneously.
- An old process not having fully stopped when its replacement starts.
- Two environments or two applications sharing a Kafka cluster with overlapping prefixes.
- Multiple independent container factories sharing a prefix without a collision-free suffix strategy.

Therefore, uniqueness must be evaluated at the **scope of the Kafka cluster and all transactional producers that can run concurrently**, not just inside a single JVM.

## 4. Prefixes and suffixes in Spring Kafka

### 4.1. transactionIdPrefix

In Spring Kafka, `DefaultKafkaProducerFactory` can be configured with `setTransactionIdPrefix(...)`. When a prefix is set, the factory creates transactional producers and manages their use for Kafka transactions.

Example:

~~~java
@Bean
public ProducerFactory<String, OrderEvent> orderProducerFactory(
    KafkaProperties kafkaProperties
) {
    Map<String, Object> configs =
        kafkaProperties.buildProducerProperties();

    DefaultKafkaProducerFactory<String, OrderEvent> factory =
        new DefaultKafkaProducerFactory<>(configs);

    factory.setTransactionIdPrefix("orders-tx-instance-a-");

    return factory;
}
~~~

This example targets a producer factory managing transactional producers for instance A. With Spring Boot, you can let auto-configuration build the factory instead of defining one manually, provided the prefix property is passed properly.

### 4.2. Suffixes are not cross-pod unique IDs

Factory-managed suffixes allow multiple producers in the **same factory** to operate without colliding on `transactional.id`. However, JVM A's suffix allocator does not coordinate with JVM B.

Thus, never rely on the factory automatically appending `-0`, `-1` to assume every pod has a unique ID.

~~~text
per-instance unique prefix + factory-managed suffix
                    |
                    v
         unique transactional.id
~~~

In newer Spring Kafka releases, suffix allocation can be configured via `TransactionIdSuffixStrategy` and caching; consult the API for your exact version. If you build a custom suffix strategy, guarantee thread safety, never issue duplicate IDs to active producers, and respect producer cache bounds.

### 4.3. Do not change transaction IDs per event

Another design mistake is embedding the event ID or offset into the transactional ID for every event:

~~~text
Do not create a new producer per event:
  orders-tx-event-10001
  orders-tx-event-10002
  orders-tx-event-10003
  ...
~~~

`transactional.id` identifies a logical producer, not a record. Creating a new producer and new ID per record incurs heavy transaction init, metadata, and lifecycle overhead, while making timeout, cache, and fencing management difficult.

Use event IDs in payloads/headers for business idempotency; use an appropriate transaction ID prefix to manage producer transactions.

## 5. Per-instance Spring Boot configuration

### 5.1. application.yml

Sample configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: "orders-tx-instance-a-"
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      enable-auto-commit: false
      isolation-level: read_committed
~~~

`orders-tx-instance-a-` must be replaced by the actual instance identity at deployment time. Never commit a static value like this into shared config and scale to multiple replicas without overriding it.

`spring.kafka.consumer.isolation-level` affects only consumers configured with that property; it does not automatically change all consumers in the system. Downstream services wanting to avoid seeing aborted records must also use `read_committed`.

### 5.2. Injecting the prefix via environment variable

Spring Boot can bind the property from its corresponding environment variable:

~~~text
SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX=orders-tx-instance-a-
~~~

On another environment or instance:

~~~text
Instance B:
SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX=orders-tx-instance-b-

Instance C:
SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX=orders-tx-instance-c-
~~~

This allows deploying the same artifact while assigning the right identity at launch. Verify the effective value using controlled startup logs or configuration inspection tools, without logging secrets or all Kafka properties.

### 5.3. Which identity should be used?

There are multiple options, each with trade-offs:

| Identity | Advantage | Considerations |
|---|---|---|
| Pod UID | Unique for pod lifetime | Replacement pods get a different UID; does not fence old producer under same ID |
| Pod name | Easy to trace in logs | Must check uniqueness and rolling overlap |
| StatefulSet ordinal | Stable across slot restarts | Must ensure two processes never hold the same slot concurrently |
| Orchestrator-assigned instance ID | Controllable and traceable | Requires collision-free ID allocation service |
| Random UUID at startup | Easy uniqueness | Does not keep the same logical ID across restarts and does not fence zombies by old ID |

**The mandatory rule is zero collisions across concurrently running independent producers.** Whether an ID must remain stable across restarts depends on failover architecture, fencing goals, and how Spring Kafka / Kafka client manages state.

Do not claim "a random UUID suffices for every exactly-once use case": an ID that changes on every startup does not fence an older producer under the same logical identity. For workers handling fixed partitions or using custom ownership, evaluate both logical owner identity and producer fencing.

## 6. Kubernetes example: deriving prefix from Pod UID

In Kubernetes, the Downward API can inject `metadata.uid` into an environment variable and reference it in the prefix.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-consumer
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-consumer
  template:
    metadata:
      labels:
        app: orders-consumer
    spec:
      containers:
        - name: app
          image: example/orders-consumer:1.0.0
          env:
            - name: POD_UID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.uid
            - name: SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX
              value: "orders-tx-$(POD_UID)-"
~~~

Kubernetes supports referencing previously declared environment variables via `$(POD_UID)` in later env values. Pod UID is unique to a pod's lifetime; every pod in the Deployment receives a different prefix.

Example:

~~~text
Pod A UID: 2f8a...
  prefix: orders-tx-2f8a...-

Pod B UID: 7b1c...
  prefix: orders-tx-7b1c...-

Pod C UID: d64e...
  prefix: orders-tx-d64e...-
~~~

Note: this example guarantees **unique IDs across live pods**, yet because a replacement pod gets a new UID, it **does not intentionally reuse the old pod's transactional ID to fence the old producer**. For flows requiring zombie fencing via a stable logical owner, also inspect owner-based identity strategies, consumer group generation, and the EOS mode of your Kafka/Spring Kafka version.

If the application uses a Kubernetes Deployment with rollout overlap, account for both old and new pods coexisting during the update window. Ensure the prefix is not truncated into collisions and no middleware overrides the same env var identically across all pods.

## 7. Unique per instance vs. stable across restarts

These are two related but non-identical requirements.

### 7.1. Unique across active instances

Any two independent transactional producers **running concurrently** must avoid sharing a `transactional.id`. This stops them from fighting over epochs and fencing each other unintentionally.

A prefix containing the Pod UID usually satisfies uniqueness well for standard deployments.

### 7.2. Stable for the same logical owner when fencing is needed

If a logical worker crashes and another worker takes over that exact role, reusing the same logical `transactional.id` lets Kafka fence the old producer if it is still alive. This is a major benefit of stable transactional IDs in ownership/failover designs.

~~~text
Logical worker slot 7

Old process (zombie):
  transactional.id = job-slot-7

New process takes over slot 7:
  transactional.id = job-slot-7
  -> initializes new epoch
  -> old producer is fenced
~~~

However, if two processes intend to operate independently at the same time, they **must not** share that ID. You cannot use one ID simultaneously across two independent owners and treat fencing errors as normal.

### 7.3. Practical selection guide

- Multi-pod service handling dynamic assignments: needs cross-pod uniqueness compatible with consumer group / EOS version.
- Fixed worker slots needing zombie fencing on failover: design stable IDs per logical owner alongside safe leader/ownership coordination.
- Rolling deployments with overlap: clarify whether the new version replaces the same owner or acts as an independent instance.
- Never use `client.id` or `group.instance.id` as a substitute for transactional IDs.

Modern consume–process–produce fencing details also depend on Kafka consumer group metadata and EOS mode, not solely on the prefix string. Check documentation for your exact version when designing custom failover.

## 8. Distinguishing commonly confused identifiers

| Property | Scope | Purpose |
|---|---|---|
| `transactional.id` | Transactional producer | Fencing and transaction state management |
| `transactionIdPrefix` | Spring Kafka `ProducerFactory` | Generates transactional IDs for producers managed by the factory |
| `client.id` | Kafka client | Identifies the client in logs, metrics, and requests |
| `group.id` | Consumer group | Distributes partitions and stores committed offsets |
| `group.instance.id` | Static consumer membership | Stable member identity within a group |
| Producer ID/epoch | Kafka protocol | Identifies producer generation and fencing |
| Business event ID | Business event | Deduplication/idempotency of side effects |

Example:

~~~text
client.id        = orders-consumer-pod-a-0
group.id         = orders-service
group.instance.id= orders-slot-a (if using static membership)
transactional.id = orders-tx-pod-a-0
event.id         = evt-408219
~~~

Values may share part of an identity for traceability, yet **do not serve the same function**. Changing group ID changes the consumer offset namespace; it does not resolve producer fencing. Conversely, changing the transactional ID prefix does not reset consumer offsets.

## 9. Transactional listeners and Kafka-to-Kafka exactly-once

In Spring Kafka, a transactional listener container can wrap consuming and processing a record in a Kafka transaction. Output records sent via `KafkaTemplate` and processed consumer offsets can participate in the same transaction.

~~~mermaid
flowchart TD
    A[Input record on source topic] --> B[Transactional listener container]
    B --> C[Business transform]
    C --> D[KafkaTemplate sends output]
    D --> E[Add source offset to transaction]
    E --> F{Commit Kafka transaction?}
    F -->|Success| G[Output and source offset commit together]
    F -->|Abort| H[Output aborted and source offset uncommitted]
    H --> I[Source record can be redelivered]
~~~

When Kafka transactions and `read_committed` consumers are properly applied, a Kafka-to-Kafka flow can achieve exactly-once semantics within Kafka's scope. However, **transactional ID uniqueness is only one requirement** in that design.

You also need:

- A transactional `ProducerFactory` and `KafkaTemplate` using the right factory.
- A listener container configured with the version-appropriate Kafka transaction manager.
- Source offsets sent into the transaction during consume–process–produce.
- Downstream consumers using `read_committed` if aborted outputs must be hidden.
- Retry/rollback handling exceptions with the right semantics.
- No unprotected non-Kafka side effects lacking idempotency.

### 9.1. KafkaTransactionManager

An illustrative bean:

~~~java
@Bean
public KafkaTransactionManager<String, OrderResult>
        kafkaTransactionManager(
            ProducerFactory<String, OrderResult> producerFactory
        ) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

This manager governs the transactional producer factory. If the application has multiple `KafkaTemplate`/`ProducerFactory` beans, ensure the manager uses the exact factory used by the output-publishing template.

### 9.2. Attaching the transaction manager to the listener container

In Spring Kafka versions supporting the Kafka-aware API:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCommand>
        transactionalListenerContainerFactory(
            ConsumerFactory<String, OrderCommand> consumerFactory,
            KafkaTransactionManager<String, OrderResult> kafkaTxManager
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCommand>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTxManager);

    return factory;
}
~~~

Container APIs and transaction manager types change across Spring Kafka versions. Older versions may use a different setter. Check Javadoc for your exact version and confirm the listener uses this factory.

With Spring Kafka 3.x, EOS V2 is the supported exactly-once mechanism; older versions have docs mentioning EOS V1. Do not copy an older version's topic-partition-coupled ID strategy verbatim onto a modern deployment.

## 10. Why must transaction IDs never be shared among independent producers?

Suppose both Pod A and Pod B use ID `orders-tx-0`:

~~~text
Time T1:
  A initTransactions -> epoch 1
  A begins transaction, sends event A

Time T2:
  B initTransactions -> epoch 2
  B begins transaction with same transactional.id

Time T3:
  A commits -> broker rejects due to stale epoch
  A receives producer fencing / invalid epoch

Time T4:
  B continues under new epoch
~~~

Operational consequences can include:

1. A's transaction aborts or fails to commit.
2. Listener A hits an exception and must roll back/redeliver input.
3. Lag grows because transactions fail to finish.
4. A restarts, creates a new producer with the same ID, and fences B back.
5. Both pods enter a mutual fencing loop.

This bug cannot be fixed by setting `acks=all`, increasing retry counts, or raising `transaction.timeout.ms`. You must fix the source generating transactional IDs or the ownership mechanism.

In some failover architectures, a new instance intentionally reusing the same ID to fence an old instance is valid. The decisive point is that **only one valid owner is allowed to proceed**; never two pods operating concurrently as independent workers.

## 11. Producer fencing is not consumer rebalancing

Producer fencing and consumer rebalancing both relate to reliability, yet belong to two distinct mechanisms:

- **Rebalance** changes partition assignments among consumer members in a group.
- **Fencing** rejects an old producer generation once a transactional identity has been superseded.

A consumer whose partition was revoked may still be running asynchronous code if the application spawned background threads. Kafka group assignments do not stop non-Kafka side effects on those threads. Transactional producer fencing also does not roll back already-committed database transactions.

For parallel processing:

- Track work per `TopicPartition`.
- Stop or cancel tasks for revoked partitions within a deadline.
- Let the old owner's transaction terminate per protocol.
- Never offload external side effects to a background thread and commit the source offset before the task is durable.
- Use event IDs, inboxes, or idempotent operations to guard side effects.

In EOS V2, Kafka uses consumer group metadata when adding offsets to transactions. Transaction ID uniqueness remains essential, while fencing also involves consumer group generation/ownership.

## 12. Failures during Kubernetes rollouts

### 12.1. RollingUpdate

A RollingUpdate often starts new pods before old pods fully terminate. If both share a static prefix, they can concurrently initialize producers with identical transactional IDs.

~~~text
T0: Old pod running, prefix orders-tx-
T1: New pod starts, prefix orders-tx-
T2: Both generate orders-tx-0
T3: Fencing errors during overlap window
~~~

Using a per-instance unique prefix prevents this unintended collision. If a design must inherit a logical identity to fence an old owner, control readiness, shutdown, and ownership explicitly rather than relying on auto-generated suffixes.

### 12.2. CrashLoopBackOff

If a pod repeatedly hits `ProducerFencedException` and restarts, each restart can continue using an ID colliding with another pod. CrashLooping will not self-heal a broken uniqueness setup.

Check:

- Which pods share the same prefix.
- Which factory creates transactional producers.
- Whether the prefix is actually injected into the pod.
- Whether a custom container factory or bean overrides the property.
- Whether another application connects to the same Kafka cluster with a colliding prefix.

### 12.3. HPA autoscaling

When HPA scales replicas up, each replica adds consumer threads and transactional producers. Unique prefixes protect IDs, yet the number of concurrent transactional producers also grows.

Do not just assign distinct prefixes and forget broker resources. Monitor transaction coordinator latency, producer caches, consumer lag, and error rates.

### 12.4. StatefulSet

Stable StatefulSet ordinals yield slot-based identities, such as `orders-tx-slot-0-` and `orders-tx-slot-1-`. This can work when each slot has strictly one valid owner at any instant.

Evaluate split-brain scenarios or lingering old processes on failed nodes. Stable IDs can fence an old producer once a new producer claims the slot, yet do not replace fencing/leader election for databases or non-Kafka services.

## 13. Timeouts, transactional ID expiration, and producer caches

Not every transaction failure stems from two pods sharing an ID. A producer can become unusable even when prefixes are allocated cleanly.

### 13.1. transaction.timeout.ms

`transaction.timeout.ms` limits how long a Kafka transaction may stay open. If an application holds a transaction open too long across HTTP/database calls, the broker can abort the transaction and the subsequent commit fails.

This is the timeout of an **in-flight transaction**, not the permanent lifetime of a transactional ID.

### 13.2. transactional.id.expiration.ms

The broker has `transactional.id.expiration.ms` to govern how long metadata is kept for transactional IDs unused for a long time. A producer kept idle in cache too long can encounter errors upon reuse once metadata/identity expires under its lifecycle.

Spring Kafka provides `maxAge` on `DefaultKafkaProducerFactory` to refresh cached producers before they grow stale. Tune it to match broker expiration and low-traffic workloads.

Do not confuse this expiration with duplicate transactional IDs across two pods; their producer-level symptoms can look similar, yet their root causes and fixes differ.

### 13.3. Kafka broker authorization

Transactional producers generally require permissions on both the transactional ID and target topics. If ACLs deny access, authorization errors occur even with unique IDs.

With Kafka ACLs, check principals, transactional ID resources, topic `WRITE`, and other deployment-mode permissions. Never alter prefixes randomly to "dodge" ACLs when authorization is misconfigured.

## 14. Common errors when transaction IDs are misconfigured

| Symptom | Likely cause | What to check |
|---|---|---|
| `ProducerFencedException` across multiple pods | Duplicate transactional ID or old producer lost ownership | Compare prefixes/suffixes, rollout overlap |
| `InvalidProducerEpochException` | Stale producer epoch or invalid transaction state | Check fencing and transaction lifecycle |
| `OutOfOrderSequenceException` | Invalid producer sequence/order | Check producer state and prior errors |
| `InvalidTxnStateException` | Transaction API called in invalid state | Begin/send/commit/abort sequence |
| `TimeoutException` during commit | Slow broker/network or expired transaction | Transaction duration and coordinator |
| Authorization error | Missing ACL on transactional ID/topic | Principal, resource, and permissions |
| Continuous restarts after scaling | Shared prefix across multiple replicas | Per-instance env configuration |
| Errors only after idle periods | Producer cache / transactional ID expiration | Factory `maxAge` and broker expiration |
| Frequent transaction rollbacks without fencing | Listener exceptions or downstream failures | Listener logs and after-rollback processor |

When producer fencing occurs, **never retry infinitely on the same fenced producer**. This is typically a fatal error for that producer generation. The framework must close/discard the invalid producer, and the application must resolve any identity conflict.

## 15. Logging and observability

The goal is quickly identifying which instance produced which ID, which phase a transaction failed in, and whether consumer offsets were affected.

Fields worth recording:

- Application/service name and deployment environment.
- Instance/pod identity and transaction ID prefix.
- Consumer group ID and client ID (if a listener).
- Configured Kafka cluster name or bootstrap server alias.
- Transaction begin/commit/abort outcomes.
- Kafka exception class, especially fencing/epoch/authorization.
- Listener container ID, topic-partition, and offset on failure.
- Producer cache lifecycle and transaction duration if instrumented.

Do not log secrets, full payloads, or authentication credentials. You can log prefixes and partial transactional IDs to investigate identity collisions, provided security policies allow it.

Metrics worth tracking:

| Metric / signal | Meaning |
|---|---|
| Transaction commit success/error | Transaction completion rate |
| Transaction abort count | Business or infrastructure failures causing aborts |
| Producer fenced count | Producer generation conflicts |
| Transaction duration | Detects long-open transactions |
| Transaction coordinator latency | Detects broker bottlenecks |
| Producer send errors | Publishing failures inside transactions |
| Consumer lag per partition | Impact of rollbacks/redelivery |
| Rebalance count/duration | Assesses group stability |
| Pod restarts | Identifies crash loops from fencing |
| Producer cache activity | Analyzes churn and resource usage |

If fencing rises right after a deployment or autoscaling event, compare running instance identities. If errors appear only after long idle gaps, inspect the producer cache and broker transaction ID expiration.

## 16. Investigation runbook for ProducerFencedException

When fencing logs appear in a service using `KafkaTransactionManager`:

1. Record the failure timestamp, pod/JVM name, environment, and Kafka cluster.
2. Identify the actual `transactional.id` or prefix in use.
3. List all **active instances** of that service in the same cluster.
4. Verify whether prefixes differ across all instances.
5. Check for rollout overlap, HPA scale-up, or lingering old processes.
6. Check whether multiple `ProducerFactory` beans in the same JVM generate colliding IDs.
7. Confirm Spring Boot env overrides are not overwritten by custom Java beans.
8. Cross-check commit/abort logs and Kafka coordinator errors.
9. Never reuse a fenced producer; fix ownership/identity.
10. Re-test in a multi-replica test environment to prove conflicts are gone.

If all prefixes are unique yet fencing still occurs, do not immediately blame a Kafka broker bug. Inspect client lifecycle, broker expiration, preceding transaction errors, and any other producers that might use the same ID.

## 17. Testing unique prefixes before production

### 17.1. Single instance

1. Configure a transactional producer with a test prefix.
2. Begin a transaction, send two records, commit.
3. Verify a `read_committed` consumer sees both records.
4. Run another transaction and confirm the producer continues cleanly.

### 17.2. Two instances with a duplicate prefix (test environment only)

1. Start two instances with the same fixed prefix.
2. Have both initialize transactions around the same time.
3. Observe producer epoch changes and fencing behavior.
4. Log transactional IDs to demonstrate the collision source.
5. Never run this test on production clusters/topics.

### 17.3. Two instances with distinct prefixes

1. Run two instances of the same application with different prefixes.
2. Have each instance send records in its own transaction.
3. Confirm zero fencing errors from ID collisions.
4. Read with `read_committed` to verify committed records are visible.

### 17.4. Rolling deployment

1. Run the old version with several replicas.
2. Deploy the new version via `RollingUpdate`.
3. Record identities/prefixes of both old and new pods during overlap.
4. Verify zero accidental collisions.
5. Monitor transaction commits/errors, consumer lag, and rebalances.

### 17.5. Crash and restart

1. Have a transactional listener process input and kill the process before transaction commit.
2. Restart under the chosen identity strategy.
3. Verify uncommitted input records can be redelivered.
4. Verify output from the aborted transaction is invisible to `read_committed`.
5. Verify non-Kafka side effects are protected by idempotency.
6. If using stable slot-based identity, verify the old owner loses commit rights after the new owner takes over.

Do not rely on a single exception message when testing. Verify output topic state, source consumer offsets, and transaction outcomes.

## 18. Exactly once does not mean one listener invocation

A transactional listener can be invoked again after a transaction abort or process restart. Kafka exactly-once processing within Kafka's scope protects atomic commits of outputs and offsets; it does not promise a listener method runs only once in terms of CPU/business invocations.

Example:

~~~text
Input event E
  -> Listener processes E, transaction T1
  -> T1 aborts
  -> Listener receives E again, transaction T2
  -> T2 commits

Listener ran 2 times.
Committed Kafka output reflects only T2.
~~~

If the listener executes a SQL update or HTTP call across both attempts, that side effect can still repeat. Unique transaction IDs do not solve that on their own. You need:

- A stable business event ID.
- An inbox table or unique constraint in the database.
- Idempotent updates or upserts.
- Transactional outbox when synchronizing database and Kafka.
- Recovery and DLT handling that tolerate duplicate records.

## 19. Decision checklist by deployment pattern

| Pattern | Identity strategy to consider |
|---|---|
| Single JVM producer-only | App-specific fixed prefix, factory manages suffixes |
| Multiple JVMs/pods producer-only | Distinct prefixes across concurrently running instances |
| Kubernetes Deployment | Pod UID or unique instance ID; also evaluate failover semantics |
| Kubernetes StatefulSet | Slot-based identity can be stable, requires proper ownership/fencing |
| Consume–process–produce listener | Unique prefix + transactional listener + source offsets in transaction |
| Multiple `ProducerFactory` beans | Coordinate ID spaces across factories without collisions |
| Multiple namespaces sharing a Kafka cluster | Scope prefixes by app/environment/instance to avoid collisions |
| Rolling update | Account for old and new pods running concurrently |
| Transactional service with DB side effects | Unique ID is insufficient; requires outbox/inbox/idempotency |

A manageable prefix structure:

~~~text
<environment>-<service>-<instance-identity>-
~~~

Examples:

~~~text
prod-orders-worker-pod-72a9-
staging-orders-worker-pod-b814-
prod-payments-worker-slot-03-
~~~

This is not a Kafka-mandated format. What matters is uniqueness, traceability, and alignment with your ownership model. Avoid overly generic prefixes like `tx-`, `producer-`, or `orders-` on a multi-service cluster.

## 20. Common design mistakes

**Using the same `transaction-id-prefix` for all pods:** factories on different pods can generate matching suffixes, causing fencing.

**Assuming factory-added suffixes guarantee cluster-wide uniqueness:** suffixes are managed within one factory, not by a shared allocator across JVMs.

**Using `client.id` instead of `transactional.id`:** client IDs serve observability and are not a transaction fencing mechanism.

**Using `group.id` as a transactional ID:** consumer groups and producer transactions have different semantics; separate identities are needed.

**Using random IDs and assuming automatic zombie fencing:** a new random ID does not supersede the epoch of a producer using an old ID.

**Using stable identities while running two independent owners simultaneously:** one producer will continuously fence the other.

**Generating a transactional ID per message:** increases producer overhead and does not provide business deduplication.

**Fixing only the prefix on fencing while ignoring factory wiring:** custom beans may keep using an old prefix or create another producer.

**Swallowing `ProducerFencedException` and retrying commits:** a producer that lost ownership should not be treated as recoverable by retrying on the same instance.

**Equating a unique prefix with end-to-end exactly-once:** you still need Kafka transaction boundaries, consumer isolation, offset coordination, and external side-effect idempotency.

**Ignoring Kafka cluster scope:** staging and production might share a cluster; identical prefixes can still collide.

**Ignoring transaction expiration:** idle producers in cache can fail for reasons unrelated to ID collisions.

## 21. Production operating principles

- Treat `transactional.id` as a producer transaction's logical identity, not an event ID.
- Use distinct `transaction-id-prefix` values across concurrently active independent instances.
- Let the factory manage suffixes; never rely on suffixes to prevent collisions across JVMs.
- In Kubernetes, supply prefixes via Pod UID/identity or a reliable ID allocator.
- Distinguish cross-pod uniqueness from stable identity needed to fence old owners after failover.
- Check rolling overlap, HPA scaling, and StatefulSet ownership.
- Monitor `ProducerFencedException`, invalid epochs, transaction commits/aborts, and latency.
- Never continue using a fenced producer.
- Align transaction ID strategy with your Kafka EOS version and listener container.
- Configure consumers with `read_committed` when aborted Kafka records must be hidden.
- Do not treat `KafkaTransactionManager` as a distributed transaction with databases.
- Guard business side effects with event IDs, inbox/outbox, and idempotency.

**Conclusion:** In Spring Kafka, per-instance unique transaction IDs prevent independent transactional producers from accidentally fencing one another when scaling across replicas. `transactionIdPrefix` must be scoped properly and paired with producer factory suffixes. For systems needing Kafka-to-Kafka exactly-once, you must also get transaction boundaries, consumer offsets, isolation, and rollback handling right. For failover or external side effects, uniqueness alone never replaces ownership fencing and business idempotency.
