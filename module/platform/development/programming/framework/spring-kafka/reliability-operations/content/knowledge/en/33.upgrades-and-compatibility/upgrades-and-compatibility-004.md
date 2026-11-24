# EOSMode.V2 and Framework Versions in Spring Kafka Reliability Operations

Upgrading a transactional Spring Kafka service from **2.x** to **3.x or 4.x** can change how the framework protects the consumer group against stale producers (*zombie producers*). Configuration that previously worked with `EOSMode.V1`, `ALPHA`, or `producerPerConsumerPartition=true` may no longer be valid. If the Kafka broker is too old, the new application may fail to initialize transactions. If `transactional.id` is shared across pods, the system may hit `ProducerFencedException`. If outputs are consumed using `read_uncommitted`, tests can even observe records from aborted transactions and wrongly conclude that exactly-once does not work.

Therefore, the topic **"EOSMode.V2 and Framework Versions"** is not merely swapping an enum. It is a cross-cutting compatibility decision spanning **Spring Kafka → Kafka client → Kafka broker → producer identity → consumer group → listener container → integration tests**.

This article belongs to **Spring Kafka Reliability Operations → Upgrades and Compatibility**. It helps you determine the prerequisites for `EOSMode.V2`, understand why `V1` was removed in Spring Kafka 3.0, plan upgrades in a safe order, configure Spring Boot, and verify transactional **Kafka input → processing → Kafka output** flows. Configuration examples primarily use **Spring Boot 3.x, Spring Kafka 3.x, and Java 17**; 2.x and 4.x compatibility notes are documented separately to avoid copying APIs across versions.

## 1. What Does EOS in Spring Kafka Guarantee?

When an application consumes a record from Kafka, processes it, and produces a new record to Kafka, Spring Kafka can manage **consumer offsets and output records within the same Kafka transaction**:

```text
Kafka topic: payments.in
       |
       v
Consumer inside listener container
       |
       v
BEGIN Kafka transaction
       |
       v
@KafkaListener processes input
       |
       v
KafkaTemplate.send("payments.out", ...)
       |
       v
Container sends consumed offsets to transaction
       |
       +------ COMMIT ------> output visible to read_committed
       |                       + group offset committed
       |
       +------ ABORT -------> output hidden from read_committed
                               + group offset not committed
                               + input may be re-read
```

Precisely:

- **Reading and processing** may execute more than once after a rollback. Listeners are not guaranteed to be "invoked only once."
- **Writing Kafka outputs and committing consumed offsets** are coordinated via a Kafka transaction to achieve exactly-once semantics for the read–process–write pipeline within Kafka scope.
- Downstream consumers need `isolation.level=read_committed` so they do not read outputs belonging to aborted Kafka transactions.
- Database writes, REST API calls, payments, or email sends **are not automatically included in a Kafka transaction**. Business-level exactly-once outside Kafka still requires idempotency, outbox/inbox, or dedicated consistency mechanisms.

This foundation applies to both V1 and V2. **The key difference between V1 and V2 is how the broker verifies that a producer/consumer no longer validly owns a partition when committing consumed offsets**, not that V2 turns external side effects into a distributed transaction.

## 2. V1 and V2: Differing in the Fencing Mechanism

Over Spring Kafka's evolution, EOS has had two mechanisms known by different historical names:

| Old Name | New Name | Core Mechanism | Requirement |
| --- | --- | --- | --- |
| `ALPHA` | `EOSMode.V1` | Fencing based on `transactional.id` tied to `group.id/topic/partition` identity | Legacy mechanism, for older brokers |
| `BETA` | `EOSMode.V2` | *Fetch-offset-request fencing*, using consumer group metadata alongside offsets in the transaction | **Kafka broker 2.5 or newer** |

### V1 Mechanism: Per-Partition Transaction ID

V1 guards against zombie consumers by allocating producers/`transactional.id` per `group.id/topic/partition`. When a partition is assigned to a new consumer, the new producer can use the same transactional identity so the broker fences the old producer. Thus V1 typically requires **one producer per consumer partition**, increasing transactional producer counts with partitions/concurrency.

```text
Consumer group G
  topic A / partition 0 ----> Producer txn ID for G/A/0
  topic A / partition 1 ----> Producer txn ID for G/A/1
  topic A / partition 2 ----> Producer txn ID for G/A/2

Rebalance:
  new instance owns G/A/1
        |
        v
  reuses matching transactional identity
        |
        v
  broker fences old producer
```

That model served the need to prevent a producer that lost ownership from continuing to commit transactions/offsets. However, it made per-partition producer management more complex.

### V2 Mechanism: Consumer Group Metadata–Assisted Fencing

Under **KIP-447**, the producer sends **consumer group metadata** together with consumed offsets into the Kafka transaction. The broker can validate ownership/group generation when processing offsets, instead of forcing applications to maintain a producer per `group.id/topic/partition`.

```text
Consumer G / member M / generation N
                 |
                 v
         Receives partition P
                 |
                 v
        Transactional producer
                 |
          send(output)
                 |
          sendOffsetsToTransaction(
              offsets,
              consumer.groupMetadata()
          )
                 |
                 v
        Broker verifies group ownership
                 |
         +-------+--------+
         |                |
       Valid          Stale member/
         |             generation
         v                |
      COMMIT              v
                     reject/fence transaction
```

The code below is a **conceptual illustration of the Kafka client API**, not something to invoke manually inside `@KafkaListener`:

```java
producer.beginTransaction();
producer.send(outputRecord);

// consumer.groupMetadata() provides group membership context.
producer.sendOffsetsToTransaction(
        consumedOffsets,
        consumer.groupMetadata());

producer.commitTransaction();
```

In Spring Kafka, the **listener container** performs the step of sending offsets to the transaction when configured with a suitable transaction manager. Normal application code simply calls `KafkaTemplate.send(...)` inside the listener without manually committing consumer offsets.

**Impact on producer count:** with V2, one transactional producer per partition is no longer needed solely for zombie fencing. Spring Kafka can use a cache of transactional producers to serve active transactions, reducing overhead and scaling flexibly with concurrency. However, V2 **does not mean a single producer for the entire cluster**.

## 3. EOSMode Timeline Across Versions

The following milestones are helpful when reading an older codebase:

| Spring Kafka | Relevant EOS Mode | What to Remember When Upgrading |
| --- | --- | --- |
| **Before 2.5** | Legacy transactional EOS mechanisms | Do not assume `EOSMode.V2` exists; read docs for the exact version in use |
| **2.5** | `ALPHA` / `BETA` | Initial support for V2 per KIP-447, requiring broker support |
| **2.6–2.7** | V2/BETA becomes default; V1/ALPHA still exists | Older clients had a limited fallback period; do not treat fallback as a long-term upgrade contract |
| **2.8–2.9** | `V1` and `V2` coexist; `ALPHA`/`BETA` are old aliases | With `kafka-clients` 3.0+, V2 **does not automatically fall back** to V1 when broker is below 2.5 |
| **3.0 and later** | **Only `EOSMode.V2` is supported** | `V1`/`ALPHA` removed from supported choices; minimum Kafka broker for transactions is **2.5** |
| **3.2 and later** | V2; adds transactional ID suffix management | Introduces `TransactionIdSuffixStrategy`, `DefaultTransactionIdSuffixStrategy`, and producer cache sizing under concurrency |
| **4.x** | V2 remains the EOS mechanism | Also verify Spring Framework/Boot/Kafka client compatibility and test infra/KRaft changes |

**Two critical milestones to remember:**

1. **Spring Kafka 2.6 already defaulted to V2**, so upgrading from 2.8 to 2.9 does not mean V2 is only starting then.
2. **Spring Kafka 3.0 supports only V2**, so production configurations cannot remain indefinitely on `EOSMode.V1` to avoid upgrading Kafka brokers.

In 2.8–2.9, legacy documentation described using `V1` if brokers were still below 2.5 and did not support V2. That was a **transitional path for the 2.x line**, not how Spring Kafka 3.x is configured.

### `ALPHA`/`BETA` Are Not Different Features from `V1`/`V2`

In some older docs:

```text
ALPHA = V1  (transactional.id fencing)
BETA  = V2  (fetch-offset-request fencing)
```

This was a **mode rename**, not four separate operating modes. If a project uses `EOSMode.BETA`, recognize that it refers to V2 and migrate the configuration to the newer version's API/defaults. Do not keep legacy enum aliases in Spring Kafka 3.x/4.x code.

## 4. Compatibility Matrix Must Cover All Four Layers

Upgrading Spring Kafka cannot rely on checking a single version line in Gradle/Maven. At a minimum, verify:

```text
Java / Spring Boot application
          |
          v
Spring Kafka library
          |
          v
Apache kafka-clients library
          |
          v
Kafka broker cluster + inter-broker protocol/features
          |
          v
Transactional ID / consumer group ownership
```

| Layer | What to Verify | What Happens if Wrong? |
| --- | --- | --- |
| **Spring Boot / Spring Framework** | Does BOM/dependency management support the chosen Spring Kafka; does the Java baseline match? | Class/API errors, auto-configuration, runtime incompatibility |
| **Spring Kafka** | Which APIs do `EOSMode`, listener container, producer factory, and transaction manager expose? | Legacy config fails to compile or transactions are not enabled |
| **`kafka-clients`** | Which Kafka client version is selected by the dependency graph; is it overridden? | Protocol/client behavior changes, runtime errors |
| **Kafka brokers** | Every broker serving transactional EOS V2 meets **Kafka 2.5+** and the cluster has an active transaction coordinator | Transaction initialization/offset commit fails; cannot expect fallback |
| **Deployment** | Is the transactional producer prefix unique across concurrent application instances? | `ProducerFencedException` or producer contention |
| **Downstream** | Do output consumers read with `read_committed`? | May observe aborted transaction records and misdiagnose EOS |

### Suggested Mapping of Compatible Lines

Reference table at the **product-line** level (exact versions must follow official BOMs and compatibility matrices):

| Application Line | Typical Paired Spring Kafka | Notes |
| --- | --- | --- |
| Late Spring Boot 2.x | Spring Kafka 2.8/2.9 per Boot/BOM | May still have legacy V1; check broker before jumping to 3.x |
| Spring Boot 3.1.x | Spring Kafka 3.0.x | EOS V2 only, Boot 3 Java 17 baseline |
| Spring Boot 3.2.x | Spring Kafka 3.1.x | EOS V2 only |
| Spring Boot 3.3.x | Spring Kafka 3.2.x | EOS V2 only, changes to transaction suffix management |
| Spring Boot 3.4.x | Spring Kafka 3.3.x | EOS V2 only |
| Spring Boot 4.x | Spring Kafka 4.x per specific Boot release | Check Spring Framework 7/Kafka client 4.x, migration, and broker tests |

This is **directional guidance**, not a guarantee that every minor/patch combination is valid. Spring Kafka publishes compatibility matrices and Spring Boot manages dependency BOMs; **prefer dependencies selected by the Boot line's BOM**, overriding only with good reason and full re-testing.

To avoid "build compiles yet runtime loads a different Kafka client" failures, teams can inspect the dependency tree during testing using commands equivalent to `gradle dependencies` / `dependencyInsight` or Maven `dependency:tree`. **This article presents reference commands** and does not require running a build/Gradle to modify any repository here.

### Broker 2.5+ Is a Minimum Requirement, Not a Production Target

The requirement `broker >= 2.5` means the EOS V2 protocol exists. It does **not** mean you should keep an end-of-life 2.5 broker in production. Newer Spring Kafka lines also introduce newer client/protocol/features; verify compatibility, security, and support policies against the version actually deployed.

If upgrading Kafka brokers to **4.x**, note the move to **KRaft**, removing ZooKeeper-based components starting in Kafka 4.0. That is **a separate infrastructure migration axis** from `EOSMode`: an EOS V2 application may not need code changes for KRaft, yet you must still test the exact client/broker pair, ACLs, transaction coordinator, rebalances, and cluster upgrade path.

## 5. Quick Decision Table for Upgrades

| Current State | Can Move Directly to Spring Kafka 3.x? | Decision |
| --- | --- | --- |
| 2.8/2.9, broker **>=2.5**, already using V2 | **Possible**, if Boot/Java/client are compatible | Drop legacy config, switch to per-instance transaction prefix, test EOS |
| 2.8/2.9, broker **>=2.5**, forcing V1 | **Possible after switching mode** | Test V2 on current branch or staging first, then upgrade framework |
| 2.8/2.9, broker **<2.5**, using V1 | **No**, if transactional EOS is still required | Upgrade Kafka brokers first or stay on a V1-supporting branch temporarily |
| 2.7, using `ALPHA`/`BETA` names | Must review config and upgrade path | Standardize understanding of V1/V2, upgrade broker/client in stages |
| Spring Kafka 3.x running EOS V2 | Moving to 4.x also requires checking Spring Boot/Framework/client | Do not check EOS alone; test build, listener/transaction APIs, and Kafka broker |
| Multi-pod sharing `transaction-id-prefix` | Risky even when brokers already support V2 | Assign distinct prefixes to concurrently running instances |

If a system only **consumes** without producing outputs inside a Kafka transaction, do not claim "Kafka exactly-once" is enabled just by adding `transaction-id-prefix`. Read–process–write EOS requires a **container transaction** with both outputs and offsets participating in the same transaction.

## 6. Migrating Legacy V1 Code to V2

In a Spring Kafka **2.8/2.9** application, you may encounter legacy configuration like this:

```java
// Legacy illustration: for Spring Kafka 2.8/2.9,
// DO NOT copy into Spring Kafka 3.x.
import org.springframework.kafka.listener.ContainerProperties;

// Application-configured Kafka listener container factory.
factory.getContainerProperties()
        .setEosMode(ContainerProperties.EOSMode.V1);

// V1 often used one producer per group/topic/partition.
producerFactory.setProducerPerConsumerPartition(true);

// Batch listeners in V1 might configure:
factory.getContainerProperties()
        .setSubBatchPerPartition(true);
```

The snippet above is a **legacy configuration excerpt**, assuming the project declared `factory` and `producerFactory` with the proper types. These V1 options were tied to fencing by per-partition transactional ID; they should not be carried verbatim into Spring Kafka 3.x.

When moving to **Spring Kafka 3.x**:

- **Remove `setEosMode(V1)` / `ALPHA`**. V1 is no longer supported.
- No need to force `setEosMode(V2)` in standard configurations; **V2 is the only mode** in the 3.x line.
- Review `producerPerConsumerPartition`, a legacy option unnecessary for V2, and avoid relying on V1's per-partition transactional ID scheme.
- Review `subBatchPerPartition` if it was previously enabled solely for V1. V2 does not need it for fencing; keep it only with a clear reason and API/version support.
- **Assign a unique `transactionIdPrefix` per concurrently running application instance**, never sharing one prefix across all replicas.
- Verify `KafkaTemplate` and the transaction manager use **the same transaction-capable `ProducerFactory`**.
- Verify the listener container actually opens a transaction and sends offsets with consumer group metadata.

### V2 Does Not Need a Separate Kafka "Feature Flag"

In Spring Kafka 3.x, many projects show snippets like:

```java
factory.getContainerProperties()
        .setEosMode(ContainerProperties.EOSMode.V2);
```

If the API still exists in your version, calling V2 is semantically valid yet **unnecessary** to enable transactions. **Enabling transactions** happens via a producer factory configured with a transactional ID prefix and a listener container wired with a Kafka transaction manager. An application that only sets the V2 enum without a transaction manager on the container does not automatically gain EOS.

Do not invent a custom property like `spring.kafka.eos-mode: V2` expecting Spring Boot to always recognize it. In Spring Boot 3.x, the standard property is typically `spring.kafka.producer.transaction-id-prefix`; EOS mode is framework logic, not a universal user-declared property.

## 7. Typical Spring Boot 3.x Configuration for V2

Example YAML for a Spring Kafka **3.x** application using Spring Boot auto-configuration:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      transaction-id-prefix: "orders-tx-${HOSTNAME:local}-"

    consumer:
      group-id: orders-processing
      enable-auto-commit: false
      auto-offset-reset: earliest
      isolation-level: read_committed
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

app:
  kafka:
    input-topic: orders.in
    output-topic: orders.out
```

In Spring Boot 3.x, when `spring.kafka.producer.transaction-id-prefix` is set and the application uses standard Kafka auto-configuration, Boot creates a `KafkaTransactionManager` and configures the listener container to use it. **If the project declares its own `ConcurrentKafkaListenerContainerFactory` or transaction manager**, verify the custom factory is wired properly to the manager and producer factory instead of assuming auto-configuration fixes custom beans automatically.

Key properties:

| Property | Role |
| --- | --- |
| `transaction-id-prefix` | Enables Kafka producer transactions; Spring appends suffixes for actual producers |
| `enable-auto-commit=false` | Prevents the consumer from committing offsets outside the transaction |
| `isolation-level=read_committed` | Ensures this consumer does not see aborted upstream Kafka outputs |
| `group-id` | Consumer group identity under which offsets are committed |
| `auto-offset-reset=earliest` | Applies only when the group has no valid committed offset; does not govern replay after rollback |
| Serializer/deserializer | Ensures records are produced/read in the expected format |
| Instance-specific prefix | Avoids transaction ID collisions across replicas |

`HOSTNAME` in the YAML is only an **example identity source**. If your infrastructure supplies non-unique hostnames or reuses them concurrently, use a better instance/pod ID. On Kubernetes, inject `POD_NAME` or `POD_UID` via the Downward API per deployment policy. What matters is that **no two active instances share the same set of transactional IDs**.

### Note on Auto-Commit Configuration Order

In modern Spring Kafka versions, the container normally adjusts consumer auto-commit if not explicitly configured by the application. For transactional flows, still **verify at runtime** that `enable.auto.commit=false` rather than relying on an assumption if custom beans/properties override configuration.

### Configuring Producers Outside a Listener

When a producer is triggered by an API/scheduler rather than a listener, `KafkaTemplate.executeInTransaction(...)` or a transaction manager can be used in the appropriate scope. That is a **producer-initiated transaction**. Inside a transactional listener container, do not wrap every `KafkaTemplate.send` in `executeInTransaction` when the goal is joining **the container's own transaction**; creating a separate transaction can break atomicity with consumed offsets.

## 8. Example Listener Properly Scoped to a Kafka Transaction

Example consuming input and sending output:

```java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final String outputTopic;

    public OrderProjectionListener(
            KafkaTemplate<String, String> kafkaTemplate,
            @Value("${app.kafka.output-topic}") String outputTopic) {
        this.kafkaTemplate = kafkaTemplate;
        this.outputTopic = outputTopic;
    }

    @KafkaListener(topics = "${app.kafka.input-topic}")
    public void handle(ConsumerRecord<String, String> input)
            throws Exception {

        String result = "validated:" + input.value();

        // Send output within the listener container's transaction.
        kafkaTemplate.send(outputTopic, input.key(), result)
                .get(10, TimeUnit.SECONDS);
    }
}
```

The `get(...)` call waits for broker send confirmation, making the failure point clear in the illustration; production throughput may use other async send patterns while preserving transaction semantics. Key mechanics:

- The container begins a transaction **before invoking the listener**, provided the factory is configured for transactions.
- `KafkaTemplate` joins the transaction because it uses the matching producer factory/transaction context.
- Listener returns normally: the container sends offsets to the transaction and commits.
- Listener throws an exception: the transaction rolls back, offsets are not committed in that transaction, and the input can be redelivered.

**Do not commit consumer offsets manually** via `consumer.commitSync()` inside a transactional listener. Doing so creates an independent offset commit path and can break atomic commit boundaries with outputs.

**Do not swallow exceptions** and return normally when business work has not completed. The container may treat the record as succeeded and commit offsets/outputs unexpectedly.

## 9. Producer Identity in V2: Prefixes and Suffixes

V2 does not use producer-per-partition fencing like V1, yet **`transactional.id` remains a critical identity** for Kafka transactional producers.

```text
Application pod A:
  transactionIdPrefix = orders-tx-podA-
  ProducerFactory issues:
    orders-tx-podA-0
    orders-tx-podA-1
    ...

Application pod B:
  transactionIdPrefix = orders-tx-podB-
  ProducerFactory issues:
    orders-tx-podB-0
    orders-tx-podB-1
    ...
```

If A and B share the prefix `orders-tx-`, producers can generate colliding full `transactional.id` values. The broker is allowed to **fence the old producer** when a new producer with the same ID initializes, leading to `ProducerFencedException`/`InvalidProducerEpochException` or unexpected transaction aborts.

| Rule | Why |
| --- | --- |
| Different prefixes across **concurrent instances** | Avoids colliding transactional producer identities |
| Suffixes managed by the producer factory | Reuses/allocates producers aligned with concurrency |
| Do not use `group.id/topic/partition` as ID per the old V1 formula | V2 uses consumer group metadata for ownership fencing |
| Monitor `ProducerFencedException` | May indicate colliding IDs or broker-expired idle producers |
| Size producer cache appropriately | Prevents producer exhaustion under concurrent transactions |
| Do not include sensitive data in transaction IDs | Keeps operational logs safe |

For rolling deployments, account for **old pods still draining** alongside **newly started pods**. A prefix "unique per replica index" can collide if the old process has not exited before the new instance with the same index starts; coordinate lifecycle and fencing properly.

### `maxAge` and `transactional.id.expiration.ms`

Brokers expire transactional IDs that remain unused for long periods. When a cached producer in the application sits **idle for too long**, the broker can expire its ID and the next use raises `ProducerFencedException`, even without a consumer rebalance.

Spring Kafka supports `DefaultKafkaProducerFactory.maxAge` to refresh cached producers **before** the broker-configured expiration window:

```java
// Configuration excerpt in Spring Kafka 3.x.
// producerFactory is an already-created DefaultKafkaProducerFactory bean.
producerFactory.setMaxAge(Duration.ofHours(12));
```

This is an **illustrative value**, not a universal default for every cluster. Choose `maxAge` smaller than the broker's `transactional.id.expiration.ms`, allowing an operational safety margin. Do not confuse `maxAge` (cached producer lifetime) with `transaction.timeout.ms` (time limit of a single Kafka transaction).

For low-traffic flows, test sending a transaction after hours of idle time to catch this issue, rather than testing only during continuous active deployment load.

## 10. Changes in Spring Kafka 3.2: `TransactionIdSuffixStrategy`

Starting in **Spring Kafka 3.2**, the framework provides `TransactionIdSuffixStrategy` to manage `transactional.id` suffixes. With `DefaultTransactionIdSuffixStrategy`:

- When `maxCache > 0`, a fixed pool of suffixes can be allocated and redistributed.
- When `maxCache = 0`, suffixes can be generated incrementally per the version's strategy.
- If the cache limit is exhausted and no idle transactional producer is available, `NoProducerAvailableException` may be thrown.
- Applications can use bounded backoff retries for transient producer shortages, but **should not retry infinitely** if concurrency genuinely exceeds sizing.

Conceptual sizing relationship:

```text
Listener concurrency = 6
Nested transactional producer activity = 2 (possible)

Required transactional producer capacity
  depends on peak concurrent transactions
  and actual factory/container configuration.

If maxCache is smaller than real demand:
  -> NoProducerAvailableException
  -> requires sizing or concurrency adjustment
```

There is no universal "`maxCache=concurrency` always works" formula for every application, because nested transactions, multiple listener containers, and producer-initiated transactions can require additional transactional producers.

**When upgrading from 3.1 to 3.2/3.3**, review producer cache configuration, load-test concurrency, and track `NoProducerAvailableException` errors, in addition to verifying V2 mode (which itself did not change).

## 11. Non-EOSMode Changes That Still Affect Upgrades

A project upgrading from Spring Kafka 2.x to 3.x/4.x can hit multiple changes at once:

| Area | Upgrade Risk | What to Check |
| --- | --- | --- |
| Java/Spring Framework baseline | Classes or APIs no longer compatible | Match Java and Spring Framework to the Boot/Kafka line |
| `kafka-clients` | Protocol, defaults, serialization versions change | Inspect dependency tree/BOM and client-broker matrix |
| Listener/container error handling | Legacy handlers replaced by new common API | Review `CommonErrorHandler`, rollback/retry/DLT |
| Transaction ID prefix | V1 per-partition logic no longer needed | Unique per instance, no improper reuse |
| Producer cache | Suffix/caching/concurrency behavior changes | Load test and watch `NoProducerAvailableException` |
| Transaction timeouts | Broker/client timeouts misaligned | Test long transactions and slow record processing |
| Batch listeners | Transaction scope and batch error handling | Test partial batch failures and replay |
| Kafka 4.x cluster | KRaft and client/broker feature compatibility | Separate broker migration from code upgrade when possible |
| Embedded Kafka tests | Some ZooKeeper-based APIs removed in Spring Kafka 4.x | Migrate to KRaft-based embedded broker/test harness |
| Observability | Metric/log/trace names or tags may change | Base alerts on outcomes and test dashboards |

**Spring Kafka 4.0** brings major client/test infrastructure upgrades; for example, `EmbeddedKafkaZKBroker` is no longer suitable as Kafka 4 moves completely to KRaft. Plan ahead if an EOS integration test suite previously depended on ZooKeeper-based EmbeddedKafka. Do not conflate fixing the test broker with "enabling `EOSMode.V2`."

## 12. Upgrade Order When Running V1 and Old Brokers

Suppose production currently runs:

```text
Spring Boot 2.x
Spring Kafka 2.8
kafka-clients 3.x
Kafka broker 2.4
EOSMode.V1
Producer-per-consumer-partition = true
```

You cannot simply bump `spring-kafka` to 3.x and expect transactions to keep running: **Spring Kafka 3.x no longer supports V1**, and Kafka 2.4 does not satisfy the broker prerequisite for V2.

A safer deployment sequence:

1. **Inventory current config:** dependency versions, broker versions, `EOSMode`, container factories, producer factories, transactional ID prefixes, consumer groups, and DLT/retry policies.
2. **Capture baseline:** commit/abort rates, consumer lag, output counts, transaction durations, producer fencing errors, and end-to-end business metrics.
3. **Upgrade brokers first:** bring the cluster to a supported version with the EOS V2 protocol (minimum 2.5; practically choose a current supported release line); perform rolling/broker upgrades per Kafka guidance.
4. **Keep application version steady during broker upgrade** if compatibility permits; test transactions across the cluster during and after the broker rolling upgrade.
5. **Switch legacy application from V1 to V2** once required brokers support it; remove `producerPerConsumerPartition` reliance as appropriate and verify transaction ID prefixes.
6. **Run EOS V2 integration tests:** happy path, failure after output send, rollback/replay, offset commits, fencing/rebalances, and DLT.
7. **Upgrade Spring Boot/Java/Spring Kafka to compatible versions.** Do not override individual libraries randomly to force an unsupported combination.
8. **Canary/rolling application deployment:** watch producer identities, group rebalances, transaction abort rates, and output/offset accuracy.
9. **Complete legacy config cleanup:** remove `V1`/`ALPHA`, V1-only batch partition flags, and per-partition transactional ID generation code if no longer relevant.
10. **Document rollback runbook:** if the new app fails, know which prior version stays compatible with the upgraded brokers and how transaction IDs/consumer groups are preserved.

Not every organization must split these into identical separate releases, but **never upgrade the broker, client, framework, and retry policy simultaneously** without a strong test/migration plan; when failures happen, isolating the source of change becomes very difficult.

## 13. Rolling Upgrades and Old/New Version Boundaries

When canarying a consumer group, there may be a window like:

```text
Consumer group: orders-processing
   |
   +-- Pod A: Spring Kafka 2.9 / V2
   +-- Pod B: Spring Kafka 3.3 / V2
   +-- Pod C: Spring Kafka 3.3 / V2
```

This **does not automatically guarantee production compatibility** simply because all pods say V2. Test:

- That client versions can coexist in the group under the configured protocol/assignor.
- That rebalances prevent old instances from committing offsets with stale membership.
- That transactional ID prefixes do not collide between live old and new pods.
- That output serializers/schemas remain compatible with downstream consumers throughout the rolling deploy.
- That retry/DLT paths do not emit differently formatted outputs between versions.
- That under increased concurrency, producer caches and group assignments stay stable.

**Do not switch part of the pods to V2 while brokers actually serving commits still lack V2 support.** On a cluster undergoing a rolling broker version upgrade, follow Kafka's feature/protocol upgrade procedure rather than assuming connecting to one new bootstrap broker suffices.

### When an Application Rollback Is Needed

A proper rollback must answer:

1. Is the old version still compatible with the new Kafka broker/client/protocol?
2. What identity will the old `transactional.id` config generate? Could it collide with new pods still draining?
3. How far did input group offsets advance during the new transactions?
4. Does the new output schema break old consumers?
5. Were external side effects outside Kafka executed? Is reconciliation/idempotency needed?

Do not arbitrarily "rewind consumer offsets" to fix a deploy failure: that triggers **business replay** and can recreate outputs/side effects even from previously committed transactions. Resetting offsets requires a dedicated procedure, confirming the consumer group is stopped, and verifying the data is safe to replay.

## 14. Compatibility Testing with a Real Kafka Broker

A unit test mocking `KafkaTemplate` does not verify V2. Assertions like "`send()` was called once" ignore broker fencing, Kafka transaction outcomes, and consumed offset commits.

An EOS integration test needs:

```text
Test producer sends INPUT topic offset N
           |
           v
Spring Kafka transactional listener
           |
       send OUTPUT
           |
       deliberate throw before commit
           |
         ABORT
           |
     input is replayed
           |
       send OUTPUT
           |
         COMMIT
           |
           +--> read_committed OUTPUT has exactly one result
           |
           +--> group committed offset == N + 1
```

Tests should run against a Kafka broker with a protocol matching the framework line under test, e.g., `@EmbeddedKafka` or Testcontainers.

### Illustrative `@EmbeddedKafka` Configuration

For Spring Kafka 3.x in a single-broker test:

```java
import org.springframework.kafka.test.context.EmbeddedKafka;

@EmbeddedKafka(
        partitions = 1,
        topics = {"eos-upgrade.input", "eos-upgrade.output"},
        brokerProperties = {
            "transaction.state.log.replication.factor=1",
            "transaction.state.log.min.isr=1",
            "offsets.topic.replication.factor=1"
        },
        bootstrapServersProperty =
                "spring.kafka.bootstrap-servers")
class EosUpgradeIT {
    // @SpringBootTest and test methods defined below.
}
```

The `=1` replication settings are **only for a single-node test broker** to run transactions. Production must configure replication/ISR per HA and durability policies; never bring `replication.factor=1` into a real cluster.

### Listener Failing Intentionally on First Attempt

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class FailingOnceProjection {

    private final KafkaTemplate<String, String> template;
    private final AtomicBoolean failFirst = new AtomicBoolean(true);
    private final AtomicInteger attemptCount = new AtomicInteger();

    public FailingOnceProjection(
            KafkaTemplate<String, String> template) {
        this.template = template;
    }

    @KafkaListener(
            topics = "eos-upgrade.input",
            groupId = "eos-upgrade-group")
    public void handle(ConsumerRecord<String, String> record)
            throws Exception {

        attemptCount.incrementAndGet();

        template.send(
                "eos-upgrade.output",
                record.key(),
                "processed:" + record.value())
                .get(10, TimeUnit.SECONDS);

        if (failFirst.compareAndSet(true, false)) {
            throw new IllegalStateException(
                    "Fault injected after broker ACK but before commit");
        }
    }

    public int attempts() {
        return attemptCount.get();
    }
}
```

The test app must enable `transaction-id-prefix` and a real listener container transaction manager. `get(...)` ensures fault injection occurs **after broker send confirmation**, not immediately after enqueuing the future. An exception thrown out of the listener must **abort** the transaction, after which after-rollback processing allows retrying the input.

### Necessary Assertions

In a test with a **fresh topic/group and first input at offset 0 on partition 0**, you can assert:

```java
// Pseudocode for an integration test with real consumer/producer fixtures.
// Observer must configure isolation.level=read_committed.

assertTrue(failingOnceProjection.attempts() >= 2);

ConsumerRecord<String, String> result =
        KafkaTestUtils.getSingleRecord(
                readCommittedConsumer,
                "eos-upgrade.output",
                Duration.ofSeconds(30));

assertEquals("processed:paid", result.value());

// Poll again to detect duplicate committed records.
assertEquals(0,
        readCommittedConsumer.poll(Duration.ofSeconds(2)).count());

// Committed offset of the group processing the input:
TopicPartition tp =
        new TopicPartition("eos-upgrade.input", 0);
var committed = groupInspector.committed(
        Set.of(tp), Duration.ofSeconds(10));

assertNotNull(committed.get(tp));
assertEquals(1L, committed.get(tp).offset());
```

This is **pseudocode excerpting the assertions**: `readCommittedConsumer`, `groupInspector`, and the input producer must be created by dedicated test fixtures. The test uses `Duration`, `Set`, `TopicPartition`, `KafkaTestUtils`, and corresponding JUnit assertions.

In real tests, await commit/offset conditions properly and isolate topics/groups/transaction prefixes per scenario. On topics that already contain data, **do not hardcode `offset=1`**: capture the actual input record's offset metadata and assert `committed == input.offset() + 1`. Do not rely on `Thread.sleep` to guess when rollback/commit finishes.

## 15. Additional Tests to Run Before Cutover

| Scenario | Why It Matters | What to Confirm |
| --- | --- | --- |
| Happy path | Baseline transaction flow | Output and consumed offset commit together |
| Failure before output send | No output sent yet | Input replays; offset not wrongly committed |
| **Failure after output ACK, before commit** | Highest duplicate-risk window | Aborted output hidden from `read_committed`; single output committed after retry |
| Process crash mid-transaction | Open Kafka transaction may need timeout/fencing | Correct result after restart, no lost/duplicated committed output |
| Consumer rebalance | Stale group member might attempt commit | V2 fencing rejects offset commits from invalid member |
| Transactional ID collision | Rolling deploy may create overlapping producer identities | No unexpected `ProducerFencedException` |
| Long-idle producer | Broker expires ID in producer cache | `maxAge`/cache works and sends succeed after idle periods |
| High concurrency | Producer suffix/cache exhaustion | No abnormal `NoProducerAvailableException` |
| Batch listener partial failure | One poll holds multiple records | Transaction/offsets roll back per configured batch scope |
| Poison pill and DLT | Retries may stall record permanently | DLT/recovered offsets match policy, errors not swallowed |
| Downstream `read_committed` consumer | Must hide aborted data | Downstream never receives aborted transaction outputs |
| Kafka + DB side effect | Kafka EOS excludes DB | Domain effect is idempotent, no duplicates on replay |
| Mixed old/new versions | Rolling migration | Rebalances, group joins, serializers, and transaction outcomes work |
| Shutdown/restart | Drain and producer cleanup | Old instance cannot keep processing after losing ownership |

**Do not use `attemptCount == 1` as an assertion for exactly-once.** Read/processing may execute multiple times; committed Kafka outputs and offsets are what must be verified.

### Notes on Testing Spring Kafka 4.x

In Spring Kafka 4.x, Kafka test infrastructure moved completely to **KRaft-based Embedded Kafka**, so old ZooKeeper-based test APIs no longer apply. If an EOS test fails right at broker startup after upgrading to 4.x, distinguish **test harness migration** from an application EOS V2 bug. Use `spring-kafka-test` from the same framework line and compatible broker/container versions.

## 16. Error Handling, Retry, and DLT When Changing Frameworks

EOS correctness depends on exception handling, not just the transaction manager.

Example of a listener catching an exception and returning normally:

```java
@KafkaListener(topics = "orders.in")
void consume(String payload) {
    try {
        process(payload);
    } catch (Exception e) {
        log.error("Could not process", e);
        // DANGEROUS: returns as if processing succeeded.
    }
}
```

If `process` fails to produce a valid output yet the method returns normally, the container may treat the transaction as successful and commit the consumed offset. That is **not a V2 bug**; it is a broken failure policy.

In a transactional listener:

- Errors requiring rollback must be **propagated to the container** per configured policy.
- Retry/after-rollback processing governs how records are redelivered.
- `DefaultAfterRollbackProcessor` and recoverers can handle failing records after bounded attempts.
- For Dead Letter Topics, verify **DLT publishing** and **recovered offset commits** follow the right transactional/policy relationship so records never vanish when a DLT send fails.
- `CommonErrorHandler` and non-blocking retry configurations must be reviewed per version; do not assume every retry topic shares the same transaction boundary as the original listener.

If V1 previously split batch transactions per partition using `subBatchPerPartition`, upgrading to V2 and changing batch listener settings can alter the failure/replay scope of a poll. That is why **partial batch failure** must be tested, not only single-record listeners.

## 17. V2 Does Not Turn a DB Transaction Into a Kafka Transaction

A common flow:

```text
Kafka input
   |
   v
@KafkaListener transactional
   |
   +--> UPDATE accounts SET balance = balance - 100
   |          (DB transaction may commit independently)
   |
   +--> KafkaTemplate.send("payments.out", ...)
   |
   X Kafka transaction ABORT
   |
   v
Kafka input is redelivered
   |
   v
DB UPDATE risks running again
```

Kafka EOS V2 guarantees atomicity only for effects **inside the same Kafka transaction**. If the DB commits first and the Kafka transaction aborts, Kafka does not automatically roll back the DB. `@Transactional` with a single transaction manager and complex synchronization also does not magically create a distributed ACID transaction spanning both DB and Kafka.

Options for end-to-end reliability:

| Design | Protection |
| --- | --- |
| **Inbox table / dedup** by `eventId` with unique key | On input replay, DB knows the business operation already ran |
| **Transactional outbox** | Domain update + outbox row commit in the **same DB transaction** |
| **Idempotent API** on target system | Retries with same key do not duplicate side effects |
| **Reconciliation** | Detects lost/duplicated/inconsistent state across systems |
| **Saga/compensation** | Compensates partially completed business steps |

Alongside Kafka output tests, test **DB row counts or business effects** whenever the system performs non-Kafka side effects. A single committed Kafka transaction does not prove "money was deducted only once."

## 18. Producer Fencing: When Is It a Good Signal vs. Misconfiguration?

`ProducerFencedException` does not always share the same root cause:

| Situation | Explanation | Resolution |
| --- | --- | --- |
| New pod and old pod share `transactional.id` | New producer fences the old producer | Assign unique prefixes to concurrent instances and review rollout |
| Cached producer idle too long | Broker expires the transactional identity | Review `maxAge` and `transactional.id.expiration.ms` |
| Rebalance revokes partition from consumer | Stale member cannot validly commit offsets | Observe group membership and handle/retry per lifecycle |
| Client/broker version mismatch | Incompatible transaction protocol/API | Check client-broker compatibility and broker minimum |
| Transaction timeout | Transaction runs past time limit | Break up processing, measure duration, fix blocking calls |
| Producer factory shared improperly | Template/container uses unintended identity/context | Verify producer factory and manager bean wiring |
| Rolling upgrade raises producer concurrency | Cache/suffix exhaustion, transaction contention | Size producer cache and load test |

V2 uses group metadata to fence zombies when sending offsets to a transaction; it **does not eliminate `transactional.id`**. Setting a unique prefix per instance remains mandatory operationally when running multiple instances.

Do not **catch `ProducerFencedException` and try reusing the same producer** as if it were an ordinary record-send error. A fenced producer is in a terminal transaction state that cannot continue safely; the framework and producer/container lifecycle must handle/recreate it per your version's guidance.

## 19. Monitoring Before and After Migration

Metrics to maintain as a comparison baseline:

| Group | Needed Metric or Log | Warning Sign |
| --- | --- | --- |
| Kafka transactions | Commit rate, abort rate, transaction duration, timeouts | Rising aborts/timeouts after upgrade |
| Producers | `ProducerFencedException`, `NoProducerAvailableException`, cache pressure | Prefix collisions or producer starvation |
| Consumers | Rebalance count, partition assignments, group offsets, lag | Continuous rebalances, stalled offsets |
| Output | Committed output count by business/event key | Real duplicates or data loss |
| Error handling | Retry attempts, DLT records, recovered offsets | Poison pills mishandled |
| Client/broker | Versions, coordinator errors, unsupported protocol | Incompatible broker/client |
| Deployment | Instance ID, transaction prefix, app version | Two concurrent pods sharing prefix |
| External effects | Unique business effects in DB/API | Idempotency broken |

Use a **`read_committed` Kafka consumer** when measuring committed business outputs. A `read_uncommitted` consumer can see records from aborted transactions; counting them as valid outputs creates false duplicate alerts on dashboards. Conversely, a `KafkaTemplate.send` success log does not prove the transaction committed.

`consumer lag` can differ across tools when open transactions hold back the last stable offset. When investigating V2, combine **group committed offsets, transaction outcomes, and downstream visibility**, rather than relying on a single lag figure.

### Suggested Structured Log

```json
{
  "eventType": "kafka.transaction.result",
  "service": "orders-projection",
  "frameworkLine": "spring-kafka-3.x",
  "instanceId": "orders-pod-a",
  "consumerGroupId": "orders-processing",
  "inputTopic": "orders.in",
  "inputPartition": 0,
  "inputOffset": 42,
  "transactionOutcome": "COMMITTED",
  "outputTopic": "orders.out",
  "attempt": 2
}
```

This is an **illustrative application schema**, not fields Spring Kafka automatically logs verbatim. Never log full payloads, tokens, sensitive data, or secrets from Kafka records.

## 20. Runbook When Post-Upgrade Deployment Fails

### Scenario A — Transactions Fail to Initialize

**Symptoms:** transaction initialization timeout or broker error indicating unsupported protocol.

Check:
1. Actual Spring Kafka/client versions in runtime dependencies.
2. Broker/controller/transaction coordinator versions and cluster feature level.
3. For brokers below 2.5: Spring Kafka 3.x has no V1 fallback.
4. Whether the producer transaction prefix is configured on the producer factory used by the listener.
5. Kafka transaction state topic, ISR, ACLs, timeouts, and broker health.

**Action:** prioritize restoring compatibility/infrastructure; do not disable transactions and let consumers auto-commit just to "get it running" if the data requires EOS.

### Scenario B — `ProducerFencedException` Spikes After Rolling Deploy

Check:
1. `transactional.id`/prefix of each pod, including draining old pods.
2. Whether instance IDs are genuinely distinct during the overlap window.
3. Whether cached producers sat idle beyond broker expiration.
4. Whether group rebalances/ownership are churning rapidly.
5. Whether a single producer factory is mistakenly shared across multiple listeners/app instances.

**Action:** fix prefixes/lifecycle, pace rollouts, and recover transactions via the listener container; do not swallow fencing errors.

### Scenario C — Duplicate Outputs Appear in Tests

Check:
1. Does the observer consumer have `isolation.level=read_committed`?
2. Did records come from the same input, or did the input topic already have duplicate business events?
3. Does the `KafkaTemplate` sending output share the listener container's transaction?
4. Is `executeInTransaction` starting a separate transaction inside the listener?
5. Are consumed offsets committed in the same transaction or out of band?
6. Is another external writer or producer emitting the same output?

**Action:** re-test with a broker-backed integration test, inspect outputs + offsets, and separate Kafka EOS from business deduplication.

### Scenario D — Consumer Group Lag Grows While No Output Appears

Check:
1. Is a long-running transaction holding back the last stable offset?
2. Is `max.poll.interval.ms` exceeded due to slow processing?
3. Are producer/transaction timeouts causing repeated aborts?
4. Is retry/after-rollback replaying a poison pill?
5. Is the transactional producer cache starved as concurrency grows?
6. Is the DLT/recoverer failing and holding back the input?

**Action:** isolate the failing record/partition and failure point; do not blindly raise timeouts indefinitely or reset offsets.

### Scenario E — Rolling Back the Application After Switching to V2

Verify whether the old version remains **compatible with the broker** and new output schemas, where consumer group offsets have committed, whether reverting transaction prefixes could collide with still-running new pods, and what external side effects were written. If resetting offsets to replay, have an idempotency/reconciliation plan. Never revert to V1 on a framework version that no longer supports it.

## 21. Pre-Release Acceptance Checklist

A deployment team can use these checks when reviewing a migration:

- [ ] Broker cluster serving transactions supports the EOS V2 protocol; for Spring Kafka 3.x minimum broker is **2.5**.
- [ ] Java, Spring Boot, Spring Framework, Spring Kafka, and `kafka-clients` match the compatibility matrix/BOM.
- [ ] No unintended code remains depending on `EOSMode.V1` / `ALPHA` or V1-formula prefixes.
- [ ] Spring Boot `transaction-id-prefix` is injected properly, with a unique prefix per running instance.
- [ ] Listener container actually has a Kafka transaction manager; `KafkaTemplate` uses a compatible producer factory.
- [ ] Consumer auto-commit is off; output consumers requiring EOS use `read_committed`.
- [ ] Exceptions triggering rollback are not swallowed; after-rollback/retry/DLT policies are tested.
- [ ] Integration test covers failure **after output ACK, before commit**, asserting both output and consumed offset.
- [ ] Crash/rebalance/fencing tests match the real topology.
- [ ] Idle-producer and cache/concurrency sizing tests run if the app has multiple listeners.
- [ ] Idempotency/outbox exists for DB/API if business exactly-once is required outside Kafka.
- [ ] Canary tracks transaction abort/fencing metrics, group lag, committed outputs, and DLT.
- [ ] Rollback plan is compatible with broker version, transactional IDs, schemas, and offset history.
- [ ] When upgrading to Spring Kafka 4.x, Embedded Kafka test infra is migrated to KRaft if previously using ZooKeeper.

This checklist represents **operational criteria**, not an automated check built into Spring Kafka. Tests must still be tailored to record/batch listener types, partition counts, retry policies, and system business structure.

## 22. Common Misconceptions

| Misconception | Why It Is Wrong | Correct Understanding |
| --- | --- | --- |
| "To get EOS in 3.x you must set `EOSMode.V2` manually" | V2 is the only mode in Spring Kafka 3.x | Enable Kafka transactions properly on producer/container and verify |
| "`EOSMode.V2` works with every broker" | V2 requires protocol from Kafka broker 2.5+ | Upgrade broker or stay temporarily on a V1-supporting legacy branch |
| "V2 does not need `transactional.id`" | Identity is still required for Kafka producer transactions | Unique prefix per instance, suffixes issued by factory |
| "V2 means the listener runs only once" | Read/process can replay after rollback | Verify committed outputs and offsets |
| "Having a transactional `KafkaTemplate` is enough" | Listener container may not use a transaction manager | Confirm outputs and offsets participate in the same transaction |
| "`read_uncommitted` counting two outputs means EOS is broken" | That consumer can see aborted records | Use `read_committed` for committed outputs |
| "V2 also covers database transactions" | Kafka transactions do not cover DB/API | Use outbox/inbox/idempotency |
| "Sharing one common prefix across all pods is simpler" | Producers can fence one another | Distinct prefix per concurrent instance |
| "Newer clients automatically fall back to V1" | With Kafka client 3.0+ and Spring Kafka 3.x there is no fallback | Upgrade broker and move to V2 |
| "`producerPerConsumerPartition=true` is mandatory" | That was V1's fencing mechanism | V2 does not need one producer per partition for fencing |
| "Manual offset commits are safer" | Can break output–offset atomicity | Let the transactional container send offsets to the transaction |
| "Upgrading broker to Kafka 4 switches EOS to V3" | Kafka 4/KRaft is an infrastructure upgrade axis | Modern Spring Kafka EOS mode remains V2 |
| "Unit tests mocking `send` are enough" | No real broker transactions/offsets/fencing | Test with `@EmbeddedKafka` or Testcontainers |
| "Zero consumer lag proves exactly-once" | Lag does not verify output/offset atomicity | Test commit/abort directly plus business outcomes |
| "App rollback is just changing an image tag" | Schemas, transactional IDs, and offsets may have moved | Need a rollback plan with reconciliation and compatibility |

## 23. Official References

Documentation must be read for the **exact version line in use**, not only the latest `/reference` pages:

- [Spring Kafka — Exactly Once Semantics (reference)](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka — Transactions and transactionIdPrefix](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — Change History, 3.0 removal of EOSMode.V1](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [Spring Kafka 2.9 — Reference, V1/V2 migration](https://docs.spring.io/spring-kafka/docs/2.9.13/reference/html/)
- [Spring Kafka 2.9 — ContainerProperties EOSMode API](https://docs.spring.io/spring-kafka/docs/2.9.13/api/org/springframework/kafka/listener/ContainerProperties.html)
- [Spring Kafka 3.0 — Exactly Once Semantics and broker minimum](https://docs.spring.io/spring-kafka/docs/3.0.17/reference/html/)
- [Spring Kafka — Testing with Embedded Kafka](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka — After-Rollback Processor and exception handling](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Project — Compatibility Matrix](https://spring.io/projects/spring-kafka/)
- [Apache Kafka — KIP-447: Producer scalability for exactly once semantics](https://cwiki.apache.org/confluence/display/KAFKA/KIP-447%3A+Producer+scalability+for+exactly+once+semantics)
- [Apache Kafka — Compatibility Matrix](https://kafka.apache.org/40/getting-started/compatibility/)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)

**Conclusion:** `EOSMode.V2` is Spring Kafka's modern exactly-once mechanism, using **consumer group metadata to protect offset commits inside Kafka transactions**. It became the default in Spring Kafka 2.6 and has been the **only supported mode since 3.0**, requiring Kafka brokers **2.5 or newer**. Safe upgrades require removing legacy V1 settings, isolating `transactional.id` per instance, keeping outputs and consumed offsets in the same transaction, and verifying rollback/replay against a real broker with a `read_committed` consumer. When extending to databases/APIs or upgrading to Kafka/Spring Kafka 4.x, add dedicated idempotency and infrastructure compatibility tests—**never interpret EOS V2 as a promise that "every line of business code executes only once."**
