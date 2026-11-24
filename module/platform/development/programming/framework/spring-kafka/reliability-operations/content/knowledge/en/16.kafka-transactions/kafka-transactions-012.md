# Producer Transaction Cache

In Spring Kafka, when a producer uses Kafka transactions, each transaction requires a producer with a valid **`transactional.id`** already initialized with the broker. Repeatedly creating a new `KafkaProducer`, calling `initTransactions()`, executing a transaction, and closing the producer outright is resource-intensive and increases latency. `DefaultKafkaProducerFactory`'s **producer transaction cache** enables reusing already initialized transactional producers once the previous transaction finishes.

This cache lives **inside the Spring Kafka application process**, not in Kafka brokers, and is not a message buffer. It manages transactional producer lifecycles so the application can continuously start transactions without initializing a producer from scratch every time.

In production operations, the producer transaction cache directly affects processing latency, concurrent transaction counts, producer limits, `NoProducerAvailableException` errors, **producer fencing**, transaction ID design when scaling across pods, and handling broker expiration of transactional ID state.

## 1. Why Must Transactional Producers Be Managed Separately?

A non-transactional Kafka producer can send many records without calling `beginTransaction()`. A transactional producer must have a `transactional.id`; when using transactions, the producer roughly follows this flow:

```text
Create KafkaProducer with transactional.id
          |
          v
      initTransactions()
          |
          v
      beginTransaction()
          |
          v
  send(record A), send(record B)
          |
          v
  commitTransaction() or abortTransaction()
          |
          v
Producer can serve the next transaction
```

`initTransactions()` interacts with Kafka's transaction coordinator to initialize or take over producer state for `transactional.id`. This is not a free operation; creating a brand-new producer per transaction incurs extra connection, metadata, thread/buffer resource, and transaction initialization overhead.

Spring Kafka addresses this by having `DefaultKafkaProducerFactory` **retain producers after their transaction finishes**. When code calls `close()` on a factory-provided producer, the factory can return the producer to the cache instead of closing the physical client immediately. The next transaction borrows a suitable producer and reuses it.

The critical precondition is that a producer can only be reused **after the previous transaction has ended**. The same transactional producer cannot run two transactions concurrently.

## 2. How Does the Producer Transaction Cache Work?

Simplified flow when an application has `KafkaTransactionManager`:

```text
                       Spring application
                               |
                               v
                   Start Spring transaction
                               |
                               v
                    DefaultKafkaProducerFactory
                               |
                        borrow producer
                       /             \
                  cache hit         cache miss
                     |                 |
                     |          Create transactional producer
                     |          and initTransactions()
                     \                 /
                      \               /
                       v             v
                    beginTransaction()
                               |
                               v
                       KafkaTemplate.send()
                               |
                               v
                    commit / abort transaction
                               |
                               v
                   Return producer to factory
                               |
                 +-------------+-------------+
                 |                           |
           Still usable                 No longer valid
                 |                           |
                 v                           v
           Cache producer              Close/evict producer
```

Not every transaction gets a cache hit. At startup, the cache holds no producers; producers are created on demand. When multiple transactions run concurrently, each transaction needs its own producer, so the factory may create additional producers. If a producer encounters a fatal error, gets fenced, or exceeds the factory's age policy, it can be closed and replaced.

The cache is normally managed **per `ProducerFactory` inside each JVM**. With three pods, each pod has its own factory and its own cache; there is no automatic shared cache across pods. Two applications sharing a Kafka cluster do not share a Java cache either.

### Caching does not mean unlimited concurrent transactions

One producer can run many transactions **sequentially**, but cannot concurrently run multiple independent transactions. If at peak load 10 transactions execute in parallel, the application needs enough transactional producers or else it will block/fail according to the factory's allocation policy.

This explains why sizing caches based on **concurrency** and simultaneous active transactions matters more than looking solely at messages per second.

## 3. transactional.id and Transaction ID Prefix

Kafka uses `transactional.id` to identify a lineage of transaction sessions. Brokers track producer IDs and epochs bound to this ID; a new producer using the same `transactional.id` can **fence** an old producer to prevent two different producers from writing under one identity.

Spring Kafka lets you configure `transactionIdPrefix` on `DefaultKafkaProducerFactory`. The factory combines the prefix with a **suffix** to generate concrete IDs:

```text
transactionIdPrefix = order-tx-pod-a-

Producer 1 -> transactional.id = order-tx-pod-a-0
Producer 2 -> transactional.id = order-tx-pod-a-1
Producer 3 -> transactional.id = order-tx-pod-a-2
```

These suffixes are illustrative only; how suffixes are generated and reused depends on `TransactionIdSuffixStrategy` and the Spring Kafka version.

### Multi-instance deployment rules

**Transaction ID prefixes must avoid collisions across applications or pods with concurrently active transactional producers.** If two pods share the exact same prefix and receive the same suffix, they can produce identical `transactional.id` values. The later-initializing producer can fence the earlier one, causing in-flight transactions to fail.

Unsuitable configuration when multiple pods run concurrently:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: order-tx-
```

If every pod uses this exact prefix with the same suffix strategy, ID collisions are likely. A safer approach is giving each pod a distinct prefix.

In Kubernetes, you can inject the pod name into an environment variable via the Downward API:

```yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX
    value: "order-tx-$(POD_NAME)-"
```

Kubernetes supports referencing previously declared environment variables using `$(POD_NAME)`. This generates distinct prefixes for concurrently running pods. If an application configures the factory in Java config, build the prefix from instance metadata via an equivalent configuration mechanism.

A **unique prefix per active instance** is essential; choosing between an identity that stays stable across restarts vs changing per new pod also requires considering deployment lifecycles, transaction state, and transactional ID cleanup on brokers.

## 4. Configuring Transactions with Spring Boot

A minimal configuration typically includes producer serializers, a transaction ID prefix, and appropriate delivery reliability parameters:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
    producer:
      transaction-id-prefix: "orders-tx-instance-1-"
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
    consumer:
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
```

In multi-instance environments, never hard-code the same `orders-tx-instance-1-` value for every replica; supply a distinct prefix via environment variables or deployment configuration.

With proper Spring Boot configuration, a transaction ID prefix allows Boot to create related transaction beans, including `KafkaTransactionManager`, per your Boot version's auto-configuration. If an application defines a custom `ProducerFactory` or multiple templates, verify the transaction manager and template use the **exact same transactional factory**.

`isolation.level=read_committed` is a **consumer** setting so listeners do not receive records from uncommitted or aborted transactions. It does not control the producer cache. `enable-auto-commit=false` lets the container control offsets when using consumer-initiated Kafka transactions; producer-initiated transactions alone do not automatically require identical settings on every consumer in the system.

## 5. Configuring DefaultKafkaProducerFactory Directly

When you need control over producer age and suffix count, declare the factory in Java. The example below uses APIs for **Spring Kafka 3.2 and later**:

```java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    public ProducerFactory<String, String> transactionalProducerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "kafka:9092");
        props.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        DefaultKafkaProducerFactory<String, String> factory =
                new DefaultKafkaProducerFactory<>(props);

        factory.setTransactionIdPrefix("orders-tx-instance-a-");
        factory.setMaxAge(Duration.ofMinutes(30));
        factory.setTransactionIdSuffixStrategy(
                new DefaultTransactionIdSuffixStrategy(8));

        return factory;
    }

    @Bean
    public KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> transactionalProducerFactory) {
        return new KafkaTransactionManager<>(transactionalProducerFactory);
    }

    @Bean
    public KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> transactionalProducerFactory) {
        return new KafkaTemplate<>(transactionalProducerFactory);
    }
}
```

Key imports:

```java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.DefaultTransactionIdSuffixStrategy;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;
```

The value `8` in `DefaultTransactionIdSuffixStrategy(8)` caps **how many suffixes can be allocated** for the factory under a bounded suffix strategy; do not mistake it for Kafka partition counts. Choose the limit based on concurrency and nested transaction needs.

**Version note:** `TransactionIdSuffixStrategy` and `DefaultTransactionIdSuffixStrategy` were introduced in Spring Kafka 3.2. On earlier versions, suffix allocation and management differ. Do not copy this snippet into an older version without checking the API. Likewise, do not declare an extra custom factory bean if your project already relies on a Boot auto-configured factory unless intentionally replacing it; avoid creating multiple factories with matching or differing prefixes where templates/managers wire to the wrong one.

## 6. When Are Producers Borrowed from and Returned to the Cache?

For transactions coordinated by `KafkaTransactionManager` or `KafkaTemplate.executeInTransaction(...)`, the lifecycle from the application's view is typically:

1. Transaction begins; Spring Kafka borrows a transactional producer from the factory.
2. The producer is bound to the transaction context so associated sends use the right producer.
3. The application sends records through `KafkaTemplate`.
4. The transaction commits or aborts.
5. The producer is released back to the factory; if still valid, it can be cached for reuse.

Example transaction coordinated by `KafkaTemplate`:

```java
public void publishOrder(String orderId, String payload) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders", orderId, payload);
        operations.send("order-audit", orderId, "created");
        return null;
    });
}
```

In this example, both sends share **the same Kafka transaction**. The factory can reuse that producer for a subsequent transaction once the current one finishes. Never call `KafkaTemplate.executeInTransaction` merely to "warm up the cache"; the purpose of the call is establishing a Kafka transaction boundary.

### Why shouldn't application code close producers arbitrarily?

With Spring Kafka-provisioned transactional producers, the producer lifecycle is tied to transactions and the factory's cache management. If code grabs the raw Kafka producer and calls `close()`, `beginTransaction()`, or `commitTransaction()` outside the chosen management mechanism, it can corrupt transaction lifecycles and reuse.

Prefer supported APIs such as `KafkaTemplate` and `KafkaTransactionManager`. If you must handle producers directly, understand the `ProducerFactory` contract and how Spring releases producers after transactions. **Never share a single in-transaction producer across multiple independent threads.**

## 7. Cache Size and Concurrency

A common operational mistake is sizing the cache smaller than the number of concurrently active transactions.

For example, suppose a pod runs a listener container with `concurrency=4`, each child consumer processing inside a Kafka transaction:

```text
Pod A
  listener-0 -> transaction T0 -> producer P0
  listener-1 -> transaction T1 -> producer P1
  listener-2 -> transaction T2 -> producer P2
  listener-3 -> transaction T3 -> producer P3

Concurrent transactional producers needed: at least 4
```

When using a bounded suffix strategy, set capacity at least high enough for concurrent transactions. When nested transactions or independent producer threads share the factory, actual demand can exceed listener concurrency.

| Scenario in one JVM | Listener concurrency | Other independent transactions | Concurrent producers needed can reach |
|---|---:|---:|---:|
| One listener, one transaction per child consumer | 2 | 0 | 2 |
| One listener, one transaction per child consumer | 4 | 0 | 4 |
| Listener plus one concurrent publish job | 4 | 1 | 5 |
| Listener with nested Kafka transactions | 4 | Depends on nested transaction count | May exceed 4 |
These numbers estimate concurrent capacity; they do not imply each child container pins a producer for its entire lifetime. Producers are borrowed when transactions run and can return to the cache afterward.

In versions supporting `DefaultTransactionIdSuffixStrategy(maxCache)`, a positive `maxCache` caps the suffix pool allocated by the strategy. If all suffixes are in use and no valid producer can be borrowed, Spring Kafka can throw `NoProducerAvailableException`. With the default unbounded suffix strategy, the factory can allocate more transactional IDs as demand grows, trading away the explicit resource cap of bounded configurations.

**Do not multiply replica count by concurrency when setting `maxCache` for a factory inside one pod.** Each pod has its own factory and cache. If four pods run `concurrency=3`, the group may run 12 consumers total, yet each pod normally needs at least three transactional producers for that listener workload, excluding other independent transactions.

## 8. NoProducerAvailableException When the Cache Is Exhausted

`NoProducerAvailableException` can occur when a bounded transaction-ID suffix strategy is used and all available suffixes are occupied. This indicates **no transactional producer can be allocated** inside the application's factory—not that Kafka brokers ran out of partitions or a topic is broken.

Example:

```text
maxCache = 2

Transaction A -> suffix 0 (in use)
Transaction B -> suffix 1 (in use)
Transaction C -> requests third producer
               -> no suffix left
               -> NoProducerAvailableException
```

Remediation paths:

- Count truly concurrent transactions on **the same factory** and compare against `maxCache`.
- Inspect listener concurrency, nested transactions, scheduled producers, and request-thread publishers.
- Reduce concurrent transactions or raise `maxCache` to match measured demand.
- If borrowing a producer must retry, use a bounded backoff policy; avoid tight retry loops that saturate threads and CPU.
- Check transaction start/end logs; an overly long transaction can hold a producer and suffix far longer than expected.

Do not work around this by assigning a random `transactional.id` per send. That avoids suffix limits at the cost of losing caching benefits and polluting brokers with excessive transactional IDs.

## 9. Caches Can Be Affected by transactional.id Expiration

Kafka brokers have `transactional.id.expiration.ms` to expire state for inactive transactional IDs. If a transactional producer sits idle in the cache too long, the broker may expire that producer's transactional ID state. When reused, the producer may hit transaction errors or broker fencing depending on circumstances.

Spring Kafka provides `DefaultKafkaProducerFactory.setMaxAge(Duration)` (available since Spring Kafka 2.5.x) to avoid reusing aged producers. When the factory sees a producer has exceeded the allowed age, it can evict that producer and create a fresh one instead of reusing it forever.

Example:

```java
DefaultKafkaProducerFactory<String, String> factory =
        new DefaultKafkaProducerFactory<>(producerConfigs);

factory.setTransactionIdPrefix("orders-tx-pod-a-");
factory.setMaxAge(Duration.ofMinutes(30));
```

Choose `maxAge` **smaller** than the broker's applicable expiration window, leaving margin for delays, restarts, and operational variance. Not every cluster keeps the default `transactional.id.expiration.ms`; inspect your actual cluster settings before deciding.

`maxAge` is a factory producer-lifecycle policy, **not the timeout of an active Kafka transaction**. Nor does it guarantee a background timer evicts every producer at the exact `maxAge` instant; what matters is that the factory avoids handing back an over-aged producer on reuse.

Distinction:

| Configuration | Purpose |
|---|---|
| `DefaultKafkaProducerFactory.setMaxAge(...)` | Caps cached producer age before reuse. |
| Broker `transactional.id.expiration.ms` | Expiration duration for inactive transactional ID metadata. |
| Producer `transaction.timeout.ms` | Limits how long an active transaction may exist on the broker. |
| Producer `request.timeout.ms` | Timeout for a client/broker request; not the entire transaction timeout. |

If a listener holds transactions open too long, inspect transaction timeouts and processing durations; raising `maxAge` cannot fix timing-out transactions.

## 10. Producer Fencing and Duplicate Transaction IDs

**Producer fencing** protects Kafka from two producers attempting to run transactions under the same `transactional.id`. Brokers use epochs to invalidate the old producer once a new producer initializes with the same ID.

Common scenario during rolling deployments:

```text
Pod old: transactional.id = orders-tx-0
  |
  +-- transaction in progress

Pod new: transactional.id = orders-tx-0
  |
  +-- initTransactions() with the same ID
  |
  v
Pod old may receive ProducerFencedException
```

If multiple pods deploy with a shared prefix and colliding suffixes, fencing can happen even when both pods are healthy. In multi-instance setups, configuring a per-instance unique `transactionIdPrefix` is the foundational safeguard.

Messages/exceptions to distinguish:

- `ProducerFencedException`: the producer was fenced because a newer producer session used that transactional ID.
- `InvalidProducerEpochException` or epoch-related errors: the producer's epoch is invalid for the transaction context.
- Transaction coordinator timeout or unavailable: broker/network/coordinator issue, not necessarily an undersized cache.
- `NoProducerAvailableException`: the application-side factory could not allocate a producer because bounded suffixes were exhausted.

After fencing or unrecoverable transaction errors, do not keep using the same raw producer. Let Spring Kafka and the factory handle discarding invalid producers while investigating duplicate IDs or abnormal transaction lifecycles.

## 11. Transaction Cache and Kafka-to-Kafka Exactly-Once

The producer transaction cache enables **producer reuse**, not automatically exactly-once semantics. Exactly-once for Kafka-read-then-Kafka-write flows requires coordinating consumer offsets with output publishing in the same Kafka transaction.

Flow example:

```text
orders topic -> consumer in group order-service
                     |
                     v
                process record
                     |
                     v
          producer sends normalized-orders
                     |
                     v
    sendOffsetsToTransaction(group metadata)
                     |
                     v
          Kafka transaction commit
                     |
                     v
        consumer advances to next offset
```

In Spring Kafka, this pattern can be coordinated by a listener container transaction manager and a `KafkaTemplate` sharing the same transactional producer factory. Output records and consumer offsets commit under Kafka's transaction protocol. If the transaction aborts, `read_committed` consumers do not see aborted output records, and the transaction's offsets are not finalized on the commit path.

Checkpoints:

- Listener container actually uses `KafkaTransactionManager` or the version-appropriate transaction mechanism.
- Producer factory has `transactionIdPrefix` and transaction IDs do not collide across instances.
- Consumer sets `enable.auto.commit=false` so offsets do not commit outside transaction boundaries.
- Downstream consumers wanting to skip aborted records set `isolation.level=read_committed`.
- Exception handling and rollback do not swallow errors in a way that commits incomplete business processing.

A Kafka transaction **does not automatically make external database transactions atomic** with Kafka. If a listener both updates a database and emits events, evaluate commit ordering, idempotency, or outbox/inbox rather than assuming cached producers guarantee zero duplicates/loss.

## 12. Producer Cache and Nested Transactions

When an application opens a new Kafka transaction while another Kafka transaction is already active, an additional producer may be required. Never assume one transaction manager or one `KafkaTemplate` implies "only one producer needed".

For example, a consumer thread already holds a producer for Kafka transaction A and enters code that deliberately opens an independent Kafka transaction B. Depending on APIs and transaction boundaries, the factory may need a second producer to avoid running two transactions on one producer.

If the cache is configured too small, threads can exhaust suffixes even when listener concurrency is 1. Therefore:

1. Identify which transactions truly nest and whether they share the same factory.
2. Inspect transaction propagation in Spring services and `executeInTransaction(...)` usage.
3. Calculate peak concurrent producers per JVM, including listeners, schedulers, and request threads.
4. Raise `maxCache` deliberately or simplify transaction structure.

Arbitrarily nesting Kafka transactions is discouraged. It complicates commit/rollback behavior and can mislead readers into believing two separate transactions share atomicity.

## 13. Monitoring Caches and Transactions in Production

Do not monitor published message counts alone. An application with a misbehaving producer cache might still emit messages while suffering high latency from constant producer recreation, fencing errors, or allocation failures under concurrency spikes.

Signals to collect:

| Signal | Meaning |
|---|---|
| Kafka transactions started/committed/aborted | Reflects load and transaction failure rates. |
| Transaction latency | Detects slow transaction coordinators, timeouts, or dependencies stretching transactions. |
| Producers created/closed | Unusual spikes may indicate cache churn, fenced producers, or overly short `maxAge`. |
| `NoProducerAvailableException` count | May indicate a too-small bounded suffix strategy or transactions holding producers too long. |
| `ProducerFencedException` and epoch errors | Suspect duplicate transaction IDs, replaced old producers, or abnormal client lifecycles. |
| Producer send errors, retries, request latency | Evaluate broker/network/serialization rather than blaming every failure on caching. |
| Kafka consumer lag and rebalances | Shows indirect impact of slow or failing transactions on processing progress. |

Kafka producers expose metrics via JMX / Kafka client metrics. Spring Kafka / Micrometer may expose listener and `KafkaTemplate` observations depending on configuration, though **there is no guaranteed stable built-in metric named `"transaction-cache-hit-ratio"` across every version**. If cache-specific metrics are needed, inspect your producer factory/listener APIs and add custom instrumentation rather than assuming non-existent metric names.

When logging transaction errors, prefer recording:

```text
event=kafka_transaction_error
application=order-service
instance=order-service-7c9f6d8-p9x5m
transaction_id_prefix=orders-tx-order-service-7c9f6d8-p9x5m-
error_type=NoProducerAvailableException
listener_id=order-listener
consumer_group=order-service
```

This is a custom structured log example, not a default Spring Kafka log format. Avoid logging raw payloads, secrets, authorization headers, or entire producer objects. For `transactional.id`, logging a technical identifier often helps diagnose fencing, subject to your organization's logging policies.

## 14. Commonly Confused Settings

| Setting / concept | Should not be confused with |
|---|---|
| `transaction-id-prefix` | Consumer group ID. |
| `maxCache` in suffix strategy | Topic partition count or cluster replica count. |
| Producer factory `maxAge` | Timeout of an in-flight transaction. |
| `enable.idempotence=true` | Replacement for `transactional.id` and transaction commit/abort. |
| `acks=all` | Proof that all business steps and offsets committed atomically. |
| `read_committed` | Producer cache configuration; it is a consumer isolation level. |
| Producer returned to cache | Records retained in cache; the cache holds clients, not business messages. |

For instance, `transaction.timeout.ms` normally must be less than or equal to the broker's accepted maximum. If a transaction times out on the broker, raising `maxCache` or changing `maxAge` will not make that transaction succeed. Likewise, when producer allocation fails due to bounded suffixes, adding Kafka partitions will not create more suffixes.

## 15. Runbook: NoProducerAvailableException

Suppose after raising `concurrency` from 3 to 8, a listener logs:

```text
org.springframework.kafka.core.NoProducerAvailableException:
No producer available
```

Investigation steps:

**Step 1 — Confirm scope.** Check which instance and producer factory emitted the error and how many listeners/templates share that factory.

**Step 2 — Inspect strategy.** Check the Spring Kafka version, `DefaultTransactionIdSuffixStrategy(maxCache)`, and the configured limit.

**Step 3 — Compare concurrency.** Count concurrent Kafka transactions in the pod; add scheduled publishers, request-thread publishers, and nested transactions if any.

**Step 4 — Check for long-running transactions.** Check whether network/database calls sit inside Kafka transactions, timeouts are overly high, or blocked threads delay returning producers to the cache.

**Step 5 — Adjust deliberately.** Raise the cap to match measured load, reduce concurrency, or apply bounded backoff when borrowing producers. Never turn it into infinite retries.

**Step 6 — Verify after change.** Watch exceptions drop, transaction commit rates recover, and producer counts and consumer lag stabilize.

Crucial note: **do not call `reset()` on the producer factory repeatedly whenever producers run out**. Resetting does not fix concurrency limits; it adds churn, discards cache benefits, and disrupts active transactions.

## 16. Runbook: ProducerFencedException After Rollout

A multi-pod deployment can hit widespread fencing errors right as new versions join the cluster.

```text
Old pod: orders-tx-0
New pod: orders-tx-0
Kafka broker: new producer replaces old producer
Old pod: transaction fails
```

Check in order:

1. Determine whether old and new pods run concurrently, especially during rolling updates using `maxSurge`.
2. Compare the effective runtime `transactionIdPrefix` on each pod, not just repository config files.
3. Check whether multiple producer factories/templates build colliding `transactional.id` values.
4. Check whether fencing occurs continuously or only once during expected ownership handover.
5. Assign unique prefixes per concurrently active instance, then roll out cleanly.
6. Confirm epoch/fencing errors cease and the consumer group advances offsets normally.

Avoid swallowing `ProducerFencedException` and trying to commit the failing transaction. Once fenced, the old producer must not continue to be used as healthy.

## 17. Sizing maxCache and maxAge in Practice

Suppose a service runs three replicas, each with listener concurrency 4 plus up to two independent transactions from a background job.

```text
Replica count: 3
Listener concurrency / replica: 4
Concurrent background transactions / replica: 2

Expected peak / replica = 4 + 2 = 6
Total consumers across deployment = 3 × 4 = 12
```

With a bounded suffix strategy, start sizing at **at least six suffixes per replica**, adding headroom for real load and nested transactions. You do not need 18 suffixes per pod merely because the deployment has three replicas.

When choosing `maxAge`:

- Check the real `transactional.id.expiration.ms` on your brokers.
- Pick a cache age below expiration with an appropriate safety margin.
- Avoid setting it too short, which causes constant producer re-initialization and negates caching.
- Avoid setting it too long, which lets long-idle producers expire on the broker before reuse.
- Monitor producer creation rates, transaction init times, and epoch/fencing errors.

There is no single optimal `maxCache` or `maxAge` for every system. Values must reflect listener concurrency, transaction topology, idle frequency, and Kafka broker policies.

## 18. Checklist for Deploying Transactional Producer Caches

Before deploying a transactional Spring Kafka service to production, verify:

1. **Right factory:** `KafkaTemplate` and transaction manager use the intended transactional `ProducerFactory`.
2. **Unique prefixes:** every concurrently running instance uses a non-overlapping `transactionIdPrefix`.
3. **Appropriate concurrency:** if using a bounded suffix strategy, `maxCache` covers concurrent transactions per JVM, including background jobs and nested transactions.
4. **Reasonable producer age:** `maxAge` prevents reusing producers idle longer than the broker's expiration policy.
5. **Aligned timeouts:** review transaction timeouts, request timeouts, and listener durations, not only cache size.
6. **Clear delivery semantics:** verify offsets and output records commit in Kafka transactions when Kafka-to-Kafka EOS is needed, and downstream uses `read_committed` where appropriate.
7. **Idempotency:** non-Kafka effects have duplicate protection or outbox/transaction safeguards.
8. **Observability:** logs/metrics track commits, aborts, producer creation, fencing, `NoProducerAvailableException`, send errors, and consumer lag.
9. **Safe rollback:** teams know how to respond if a new deploy reuses prefixes, brokers fence producers, or caches exhaust under peak load.
10. **Operational testing:** simulate concurrent transactions, producer failures, pod restarts/rollouts, and serialization/publish errors.

Spring Kafka's producer transaction cache is a **transactional producer reuse** mechanism that cuts initialization overhead and supports consecutive transactions. To use it safely, recognize that caches belong to each `DefaultKafkaProducerFactory`, transaction IDs must be unique across concurrently active instances, suffix bounds must match concurrency, and aged or fenced producers must be replaced. Caching optimizes resources; consistency and reliability still come from how the application structures transactions, offsets, exception handling, and idempotency.
