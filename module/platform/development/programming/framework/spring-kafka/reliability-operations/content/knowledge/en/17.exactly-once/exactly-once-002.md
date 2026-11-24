# EOSMode.V2

**EOSMode.V2** is the **Exactly Once Semantics (EOS)** mode in Spring Kafka that uses Kafka's transaction mechanism to coordinate **writing output records** and **committing input record offsets** within a single Kafka transaction. The key difference of V2 compared to the older mechanism is the broker's ability to rely on **consumer group metadata** when sending offsets into the transaction to support detecting and fencing consumers/producers that no longer own the partition, rather than relying on a strategy of creating separate transactional producers per group/topic/partition as before.

EOSMode.V2 emerged during the transition of Spring Kafka 2.x versions toward a newer transaction mechanism. With Spring Kafka 3.x, **V2 is the supported EOS mode**; new codebases typically do not need to declare the `EOSMode` enum to choose V2. Therefore, understanding **EOSMode.V2** is more important than memorizing a specific setter line: you need to verify the transaction manager, transactional `ProducerFactory`, consumer container, offset-in-transaction, broker compatibility, and downstream configuration.

This article moves from semantics and APIs to implementation, common mistakes, verification via integration tests, and production operations. The scope of **exactly once** is defined carefully: Kafka can guarantee atomicity between output Kafka records and input Kafka offsets under proper configuration; **it does not make every side effect in a database, HTTP call, or email exactly-once**.

## 1. The problem EOS solves

Consider an application reading topic **orders.in**, normalizing the data, and writing to topic **orders.out**:

~~~mermaid
flowchart LR
    I["orders.in"] --> C["Spring Kafka consumer"]
    C --> L["Transform OrderEvent"]
    L --> P["KafkaTemplate producer"]
    P --> O["orders.out"]
    C --> F["Commit input offset"]
~~~

If sending output and committing the input offset are **two independent operations**, there are two failure windows:

1. **Output is written, offset is not committed**: the process dies after sending output; on restart, the same input can be read again and output is duplicated.
2. **Offset is committed, output is not written**: the input is treated as processed, but the output record is lost.

For example, partition 0 of `orders.in` has offset 200:

~~~text
Without coordinated transactions:

consume orders.in-0@200
  -> send orders.out: event X       [SUCCESS]
  -> process is killed
  -> input offset is still 200
  -> restart
  -> re-consume orders.in-0@200
  -> send orders.out: event X       [POSSIBLE DUPLICATE]
~~~

Kafka EOS for the consume-transform-produce model allows **output records and consumer offsets** to be committed in the same Kafka transaction. If the transaction aborts, downstream consumers using `read_committed` will not see that transaction's output and the input offset is not committed through that transaction. When the input is reprocessed, a new transaction can succeed.

**Note:** the listener may be invoked multiple times; EOS here does not promise that the Java method executes only once. It provides semantics for committed Kafka records and committed offsets, not elimination of all duplicate computation.

## 2. What is EOSMode.V2?

Historically, Spring Kafka had different ways to create/identify transactional producers for a listener container.

- The older mechanism is often referred to as **EOSMode.V1**, more tightly coupled to consumer group/topic/partition identity to support fencing.
- **EOSMode.V2** uses the capability of newer Kafka versions to send **consumer group metadata** when adding consumer offsets to a transaction. The broker has information to evaluate the validity of the consumer member/generation in the group coordination protocol and perform appropriate fencing.
- With **Spring Kafka 3.x**, documentation and newer configurations use V2 as the default operating model for transactional listeners; do not copy `EOSMode` setter calls from examples written specifically for 2.x without checking available APIs.

Some documentation uses the term **fetch-offset-request** when describing the evolution of the fencing mechanism. The operational takeaway is: **V2 does not require a fixed per-group/topic/partition `transactional.id` strategy**, yet it **still requires a unique `transactional.id` across concurrently active transactional producers**.

### 2.1 V2 is not "exactly once version two" for every system

The name V2 does not mean every Kafka application is automatically upgraded from at-least-once to exactly-once. A consumer may run on Spring Kafka 3.x while:

- `ProducerFactory` is not transaction-capable.
- `KafkaTemplate` sends outside the transaction.
- The listener container does not open a Kafka transaction.
- The consumer commits offsets separately from the output transaction.
- Downstream reads with `read_uncommitted`.
- A business service calls an external HTTP API with non-idempotent side effects.

In those cases, the V2 label does not fix transaction boundaries on its own. V2 is part of the coordination infrastructure, not an annotation guaranteeing every task occurs only once.

### 2.2 Distinction table

| Question | Does EOSMode.V2 solve it? | Conditions or limitations |
|---|---|---|
| Atomicity across Kafka output records in the same transaction | Yes | Producer transaction and commit/abort are properly handled |
| Committing Kafka consumer offsets with the output transaction | Yes | Listener container coordinates offsets into the transaction |
| Fencing compatible with consumer group metadata | Yes | Broker/client/Spring Kafka support V2 |
| Hiding output from aborted transactions | Yes for `read_committed` consumers | Consumer must set `isolation.level=read_committed` |
| Guaranteeing the listener method is invoked only once | No | Aborts/restarts can cause the listener to run again |
| Atomicity between Kafka and a SQL database | Not automatically | Requires a dedicated transaction/outbox design |
| Preventing two duplicate business events from upstream | No | Requires idempotency/deduplication |
| Eliminating the need for `transactional.id` | No | Producer must still have a proper `transactional.id` |

## 3. How does a Kafka transaction operate?

A Kafka transactional producer has a **transactional.id** and executes the transaction lifecycle:

1. Initialize the transactional producer.
2. Begin the transaction.
3. Send one or more Kafka records.
4. For consume-transform-produce, send input offsets along with consumer group metadata to the transaction.
5. Commit the transaction when all eligible work succeeds; or abort on error.

~~~mermaid
sequenceDiagram
    participant K as Consumer (orders.in)
    participant L as Spring Kafka listener
    participant P as Transactional producer
    participant B as Kafka brokers
    participant R as read_committed consumer
    K->>L: Input record
    L->>P: Send output record
    P->>B: Write transactional output
    L-->>K: Listener succeeds
    K->>P: Send consumed offsets + group metadata
    P->>B: Add offsets to transaction
    P->>B: Commit transaction
    B-->>R: Output eligible to read
~~~

The diagram omits internal steps of the Kafka client, coordinator, and Spring container. The core point: **output and input offset must travel in the same transaction**. If output commits while the input offset commits through a separate mechanism, EOS for the consume-transform-produce chain is not established.

### 3.1 Two operations must reside in the same Kafka transaction

Conceptual example:

~~~text
Transaction TX-42:
  produce orders.out-1@500
  produce orders.audit-0@207
  commit consumed offset orders.in-0 -> 201

COMMIT TX-42
~~~

After commit, the input consumer group has its committed offset advanced to 201 and the outputs in the transaction are considered committed. If TX-42 aborts, the input offset still needs reprocessing and `read_committed` downstream consumers do not receive that transaction's output.

### 3.2 Guaranteeing "committed output" differs from "listener runs once"

If a listener executes:

~~~java
analyticsCounter.increment();
kafkaTemplate.send("orders.out", event.orderId(), serialize(event));
~~~

and the Kafka transaction aborts, the Kafka record is not committed, yet the in-memory counter has already incremented. If the counter represents a persistent external side effect or business metric, re-running the listener can produce duplicate results.

Therefore, distinguish between:

- **Exactly-once Kafka processing effect**: committed Kafka records and Kafka offsets are transactionally coordinated.
- **Exactly-once business side effect**: database, HTTP, email, cache… require separate mechanisms.

## 4. Foundational prerequisites for using V2

Before deploying, verify all of the following together:

- **Spring Kafka version** supports the EOS V2 mechanism.
- **Kafka brokers** support the APIs/protocols V2 uses (typically requiring Kafka broker 2.5 or newer for V2).
- **Kafka clients** are compatible with the broker, transactions, and consumer group metadata.
- **Transaction-capable ProducerFactory** has a proper `transactionIdPrefix`.
- **KafkaTransactionManager** or a Kafka-aware transaction manager matching the version.
- **Listener container** actually enables transactions for the input listener.
- **KafkaTemplate** uses the same transactional producer infrastructure.
- **enable.auto.commit=false** so the container/transaction coordinates offsets.
- **read_committed** on consumers that must see only committed transactional outputs.
- **Topic replication/ISR and broker transaction configuration** suited for production.

V2 does not require a single global toggle to "turn on EOS for all listeners." One project with multiple `ConsumerFactory`/`KafkaTemplate`/container factories can have both transactional and non-transactional flows.

### 4.1 Version compatibility

| Context | How to interpret |
|---|---|
| Spring Kafka 2.x with `EOSMode` enum | May require configuring V2 mode explicitly on the container, depending on the minor version |
| Spring Kafka 3.x | V2 is the supported mechanism; avoid copying V1/V2 selection code from old examples |
| Broker too old | Does not meet V2 protocol requirements; upgrade or review the corresponding version's solution |
| Mixed Spring Kafka, client, and broker | Check the compatibility matrix of the deployed version combination |

**Do not upgrade Spring Kafka in isolation and assume the broker already qualifies.** Some errors only surface when a transaction begins, sends offsets, or commits, not necessarily at application startup.

## 5. Transactional ProducerFactory

Spring Kafka creates producers via **ProducerFactory**; the standard implementation is `DefaultKafkaProducerFactory`. For the factory to create transactional producers, a **transaction ID prefix** must be configured.

Spring Boot YAML example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092

    producer:
      transaction-id-prefix: orders-transformer-instance-01-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      properties:
        acks: all
        enable.idempotence: true
        transaction.timeout.ms: 60000

    consumer:
      group-id: orders-transformer-prod
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        isolation.level: read_committed
~~~

The configuration above illustrates **one application instance**. For multi-pod deployments, every concurrently active instance must be assigned a non-overlapping prefix. For example, `instance-01` is a semantic placeholder, not a shared value to copy across all production pods.

### 5.1 transactionIdPrefix and group.id are two distinct identities

- **group.id**: shared across consumer replicas belonging to the same logical consumer group so Kafka distributes partitions and maintains group offsets.
- **transactionIdPrefix**: must be unique across concurrently active producer factory instances to prevent transactional producers from colliding on `transactional.id`.
- **client.id**: used for logging, metrics, and quotas; does not replace `group.id` or `transactional.id`.

Example:

~~~text
Pod A:
  group.id = orders-transformer-prod
  transactionIdPrefix = orders-transformer-pod-a-

Pod B:
  group.id = orders-transformer-prod
  transactionIdPrefix = orders-transformer-pod-b-
~~~

Both pods share a group to split input partitions; each pod has its own prefix so producer transactions do not fence one another.

### 5.2 V2 relaxes per-partition binding, not producer fencing

With V2, the broker uses consumer group metadata in the send-offsets-to-transaction flow to help control ownership. However, producer fencing based on **transactional.id/epoch** still exists and remains critical.

If two pods attempt to create a transactional producer with the same `transactional.id`:

~~~text
Pod A transactional.id = orders-transformer-0
Pod B transactional.id = orders-transformer-0

Pod B initializes a new producer epoch
=> old producer on Pod A is fenced
~~~

V2 does not "allow sharing a `transactional.id` across multiple pods." It enables a producer management model less dependent on hard-binding IDs per partition, while uniqueness of producer identity must still be preserved.

### 5.3 Checking transaction-capable

You can check early:

~~~java
@Component
public class TransactionalProducerGuard {

    public TransactionalProducerGuard(
            ProducerFactory<String, String> producerFactory) {

        if (!producerFactory.transactionCapable()) {
            throw new IllegalStateException(
                "EOS flow requires transactional ProducerFactory"
            );
        }
    }
}
~~~

If multiple factories exist, inject the right factory using a qualifier. Returning `true` only proves **capability**; it does not prove the listener container opened a transaction or that offsets were committed in that transaction.

## 6. KafkaTemplate, KafkaTransactionManager, and listener container

A transactional Spring Kafka application typically includes:

~~~mermaid
flowchart TD
    P["ProducerFactory (transaction capable)"] --> KT["KafkaTemplate"]
    P --> TM["KafkaTransactionManager"]
    TM --> LC["Kafka listener container"]
    LC --> L["@KafkaListener"]
    L --> KT
    LC --> C["KafkaConsumer input offsets"]
    KT --> O["Kafka output records"]
    C --> TX["Same Kafka transaction"]
    O --> TX
~~~

The components must be wired together properly:

- `KafkaTemplate` sends output using a transactional producer.
- `KafkaTransactionManager` manages the transaction context.
- The listener container starts a transaction when consuming input.
- When the listener succeeds, the container adds the corresponding offsets to the transaction and commits.
- When the listener fails, the container rolls back/aborts, then performs recovery/redelivery via transactional error handling.

### 6.1 Sample producer factory and manager beans

Java example using one `ProducerFactory`:

~~~java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    ProducerFactory<String, String> transactionalProducerFactory() {

        Map<String, Object> props = new HashMap<>();

        props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "kafka-1:9092,kafka-2:9092,kafka-3:9092"
        );
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(
            ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
            true
        );

        var factory =
            new DefaultKafkaProducerFactory<String, String>(props);

        // Must be a dedicated prefix for this instance.
        factory.setTransactionIdPrefix(
            "orders-transformer-instance-01-"
        );

        return factory;
    }

    @Bean
    KafkaTemplate<String, String> transactionalKafkaTemplate(
            ProducerFactory<String, String> transactionalProducerFactory) {

        return new KafkaTemplate<>(transactionalProducerFactory);
    }

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> transactionalProducerFactory) {

        return new KafkaTransactionManager<>(
            transactionalProducerFactory
        );
    }
}
~~~

With Spring Boot auto-configuration, you do not necessarily need to declare all three beans manually. If the project defines custom beans, ensure you do not create two unsynchronized factories/managers sharing the same logical role.

### 6.2 Configuring listener container transactions by Spring Kafka version

With Spring Kafka 2.x, documentation for some minor versions shows this illustrative setup:

~~~java
var factory =
    new ConcurrentKafkaListenerContainerFactory<String, String>();

factory.setConsumerFactory(consumerFactory);
factory.getContainerProperties()
       .setTransactionManager(kafkaTransactionManager);

// For 2.x versions that expose EOSMode selection:
factory.getContainerProperties()
       .setEosMode(ContainerProperties.EOSMode.V2);
~~~

**This is a historical API illustration, not copy-paste code for Spring Kafka 3.x.** In Spring Kafka 3.x, V2 is the supported model; do not call `setEosMode` if the API has been removed. Modern releases use other Kafka-aware transaction manager configuration APIs, such as the corresponding setter on `ContainerProperties`.

For Spring Kafka 3.x, follow three steps:

1. Create `KafkaTransactionManager` from the transactional `ProducerFactory`.
2. Attach the manager to the **right** `ConcurrentKafkaListenerContainerFactory` using the API of the version in use.
3. Verify with an integration test that output records and consumed offsets actually commit/abort in the same transaction.

Do not see `@KafkaListener` inside a `@Transactional` class and conclude you have container transactions. If the listener container does not manage input transactions, input offsets and output transactions can diverge.

### 6.3 Simple transform listener

~~~java
@Component
public class OrdersTransformer {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrdersTransformer(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        id = "orders-transformer",
        topics = "orders.in",
        groupId = "orders-transformer-prod",
        containerFactory = "transactionalListenerFactory"
    )
    public void transform(
            ConsumerRecord<String, String> input) {

        String output = input.value().trim().toUpperCase();

        kafkaTemplate.send(
            "orders.out",
            input.key(),
            output
        );
    }
}
~~~

This method focuses on business logic. **Exactly-once Kafka semantics depend on `containerFactory`** and a properly configured transaction manager, not on the listener calling `send` only once.

## 7. Sending consumed offsets to the transaction

The crux of EOSMode.V2 is that the broker receives **consumer group metadata** when offsets are sent into the transaction.

In the Kafka client, the corresponding API is **sendOffsetsToTransaction(offsets, groupMetadata)**. It combines:

- A map of topic-partitions to the offsets to commit.
- `ConsumerGroupMetadata` describing the current consumer group context.

~~~java
// Conceptual diagram using raw Kafka Java client APIs.
// Spring Kafka's transactional listener container handles
// offset coordination on behalf of application code.

Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
    new TopicPartition("orders.in", 0),
    new OffsetAndMetadata(201L)
);

producer.sendOffsetsToTransaction(
    offsets,
    consumer.groupMetadata()
);
~~~

**You do not need to call this API manually inside a normal `@KafkaListener`** if the container is configured as transactional. Spring Kafka is responsible for passing consumed offsets into the transaction at the proper boundary.

### 7.1 Why does group metadata matter?

In a consumer group, partition assignment can change when:

- A pod restarts.
- A consumer loses heartbeats or exceeds the poll interval.
- The group rebalances due to scaling concurrency.
- A partition is reassigned to another member.

Consumer A may believe it still owns a partition while the group has already assigned it to B. If A keeps committing stale offsets, it risks making processing state outdated or interfering with the new member's progress.

V2 leverages consumer group metadata in transactional offset commits so the broker has additional membership/generation information and performs protocol-level fencing. This is especially important when group assignments change while a transaction is in flight.

### 7.2 Offset commit in a transaction is not "pre-commit"

Example input record at offset 200:

~~~text
Input: orders.in-0@200

After processing:
  output -> orders.out-1@500
  next input offset -> 201

Both output and offset 201
are placed in the same transaction.
~~~

Offset 201 is the **next position to read** after record 200, not "offset 201 has already been processed." When verifying state manually, understand Kafka's committed offset semantics.

### 7.3 When a group rebalances mid-transaction

If a consumer loses partition ownership mid-processing, the container/transaction may fail or must abort under the new group state. Do not force a commit through a separate offset-commit path to avoid an exception.

Proper operational steps:

1. Record the transaction error and group membership state.
2. Let the consumer/container abort or clean up per the framework lifecycle.
3. Allow the group rebalance to complete.
4. Reprocess inputs from the valid committed offset.
5. Rely on Kafka transactions so aborted transaction outputs are not exposed to `read_committed` downstream consumers.
6. Protect non-Kafka side effects with idempotency.

## 8. Comparing V1 and V2 operationally

| Aspect | Legacy V1 mechanism | EOSMode.V2 |
|---|---|---|
| Goal | Consume-transform-produce EOS in Kafka | Same goal |
| How zombie consumer fencing is supported | Ties transactional identity more tightly to group/topic/partition | Leverages consumer group metadata when sending offsets to the transaction |
| Transactional producer identity | Depends on V1's ID strategy | Per-instance prefix and factory-managed suffixes |
| Multi-instance/concurrency fit | Must follow constraints of the older mechanism | More flexible for per-instance producer management |
| Newer framework support | Found mainly in older docs/code | Supported EOS mechanism in Spring Kafka 3.x |
| Does it change EOS boundaries outside Kafka? | No | No |
| Requires broker compatibility? | Yes | Yes, with newer protocol requirements |

You do not need to migrate business data just because an enum changed from V1 to V2. However, upgrading an application requires reviewing broker compatibility, `transactional.id` generation, producer caching, and the test suite. Changes in identity or producer lifecycle can affect fencing and transaction throughput.

## 9. Producer fencing vs. consumer group fencing

Two layers of "fencing" are easy to conflate:

### 9.1 Transactional producer fencing

Kafka manages producer epochs per `transactional.id`. A new producer claiming the same `transactional.id` can cause the old producer to be fenced.

~~~text
A uses transactional.id X
B initializes transactional.id X
A tries to write/commit
=> A is fenced
~~~

This is why `transactionIdPrefix` must be unique across running instances. This error can occur even when the consumer group is stable if two transactional producers share an ID.

### 9.2 Consumer group metadata in V2

When `sendOffsetsToTransaction` passes group metadata, the broker can distinguish whether an offset commit comes from the current consumer group context or a stale context. Thus consumer ownership fencing no longer has to be encoded primarily via per-group/topic/partition `transactional.id` values.

**Both mechanisms complement each other**; they do not replace one another:

- Producer epoch protects transactional producer identity.
- Group metadata validates input offset commits against group ownership.

If an application encounters `ProducerFencedException`, do not immediately conclude the cause is a consumer rebalance. It could also be two pods sharing a `transactional.id`. Inspect the exception, transactional ID, producer lifecycle, and group generation/assignment.

## 10. Consumer isolation.level and LSO

Transactional output does not automatically guarantee downstream consumers see only committed records. Consumers reading output must configure **isolation.level=read_committed** if they must skip aborted records.

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

Two modes:

| isolation.level | Behavior |
|---|---|
| read_uncommitted | May return records belonging to uncommitted or aborted transactions |
| read_committed | Returns only committed transactional records and valid non-transactional records, skipping aborted records |

When a transaction is open on a partition, a `read_committed` consumer can be bounded by the **Last Stable Offset (LSO)**. Records behind an unstable open transaction may not be returned immediately, even if the broker has already received them.

### 10.1 Abort example

~~~text
TX-1 sends orders.out@100
TX-1 sends orders.out@101
TX-1 aborts

read_committed:
  does not deliver those two records as valid output

read_uncommitted:
  may observe records from the aborted transaction
~~~

If a downstream consumer uses `read_uncommitted`, claiming "nobody sees output from aborted transactions" is false. When evaluating end-to-end EOS, inspect downstream configurations.

### 10.2 Is read_committed mandatory on input?

If the input topic has upstream transactional producers and the service should only process committed inputs, the input consumer should use `read_committed`.

If the input topic only has non-transactional producers, `read_committed` can still be used and will read non-transactional records normally.

Key distinction: `read_committed` on **input** determines which records the listener reads; transactions on **output** determine the atomicity of writing outputs and committing input offsets. Both decisions complement each other, though they are not identical.

## 11. AckMode, offsets, and container transactions

With a transactional listener container, offset commits must follow the Kafka transaction lifecycle. The container coordinates offsets according to record/batch listener semantics and the ack mode supported in the framework version in use.

Principles:

- **enable.auto.commit=false**: do not let the Kafka client auto-commit offsets outside the transaction.
- **Do not manually call `consumer.commitSync/commitAsync`** inside a listener "just to be sure" when the container already manages transactions.
- **Do not manually open another unrelated Kafka transaction** and commit input offsets outside the container without understanding the lifecycle.
- **Do not acknowledge early** if business processing has not finished.
- **Do not return from the listener before mandatory work has actually completed**, unless the framework and async architecture are explicitly designed for it.

### 11.1 Record listeners vs. batch listeners

In a record listener, each invocation maps to one record; the container handles offsets according to its policy. In a batch listener, one invocation can contain multiple records; the transaction can span the input batch and corresponding outputs.

For example, a batch has 100 records. If the listener fails on the 70th record and the transaction aborts, the Kafka outputs in that transaction are aborted. Since the input has not been committed, the batch or relevant records can be redelivered according to the transactional rollback/recovery policy.

Do not assume `DefaultErrorHandler` for non-transactional listeners is the sole handler for transactional batches. Spring Kafka commonly pairs **AfterRollbackProcessor** and corresponding recovery mechanisms with transactional containers.

### 11.2 Manual ack does not mean exactly-once

A manual-ack listener can still commit the input offset at the wrong time if it acknowledges before the output commits. Conversely, a transactional container can coordinate offset commits without the listener calling `acknowledge()` manually.

If the goal is Kafka EOS, let the container perform transactional offset commits through supported framework APIs rather than adding manual commits in business logic.

## 12. Retry, rollback, and AfterRollbackProcessor

Transactions do not prevent exceptions from occurring. They abort the Kafka outputs and offsets of a failed processing attempt.

Example:

~~~text
consume input offset 700
  -> send output A
  -> call transformService
  -> throw IllegalStateException

Kafka transaction aborts
  -> output A is not visible to read_committed
  -> input offset is not committed in the transaction
  -> input can be redelivered
~~~

In a transactional listener, **AfterRollbackProcessor** helps determine which records to seek/reprocess after rollback, applying `BackOff` or recovery as configured. Its usage differs from `DefaultErrorHandler` for non-transactional listeners.

### 12.1 Do not swallow exceptions

If a listener encounters an error, catches and logs it, and returns normally, the container may consider the transaction successful and commit outputs/offsets:

~~~java
@KafkaListener(
    topics = "orders.in",
    containerFactory = "transactionalListenerFactory"
)
public void transform(String input) {
    try {
        service.process(input);
    }
    catch (Exception ex) {
        log.error("processing failed", ex);
        // If it returns normally, the container may commit.
    }
}
~~~

If an error must cause a transaction abort, the exception must propagate or the transaction must be marked for rollback via the appropriate API.

### 12.2 Poison records and retry exhaustion

If the same record always fails due to invalid data, the transaction will repeatedly abort and the input may be redelivered continuously. You should not retry indefinitely.

A recovery policy can:

1. Retry finitely for transient errors.
2. After exhaustion, publish the failed record to a DLT.
3. Determine whether DLT publication needs a separate transaction.
4. Advance the input offset only when recovery is deemed complete per policy.
5. Preserve the raw record and metadata for replay.

In Spring Kafka, transactional recovery includes capabilities such as committing recovered offsets in a new transaction via corresponding processor configuration. Verify exact APIs and semantics for your version rather than copying non-transactional listener recoverer configs.

### 12.3 Kafka transactions do not roll back databases

If a listener writes to a database successfully and then fails before the Kafka commit:

~~~text
DB update: COMMIT
Kafka TX: ABORT
input: REDELIVER
DB update: may execute again
~~~

You need idempotency keys, inbox/deduplication, or an outbox. EOSMode.V2 does not fix this non-Kafka failure window.

## 13. Transaction timeout and producer lifecycle

A Kafka transactional producer must finish its transaction within the timeout permitted by the broker. If a listener holds a transaction open too long due to a slow database or API, the coordinator may abort the transaction.

Parameters to monitor:

| Parameter | Meaning |
|---|---|
| transaction.timeout.ms | Timeout the producer requests for the Kafka transaction |
| transaction.max.timeout.ms | Broker-side maximum limit |
| max.poll.interval.ms | Maximum time between consumer polls before risking assignment loss |
| request.timeout.ms | Timeout for an individual network request |
| delivery.timeout.ms | Time limit for producer record delivery |
| acks | Broker acknowledgment level for producer sends |
| min.insync.replicas | Required ISR replica threshold for producer durability per policy |
| transactional.id.expiration.ms | Expiration mechanism for inactive transactional IDs |

Do not confuse `transaction.timeout.ms` with consumer retry backoff. The two intervals serve completely different purposes.

### 13.1 Do not hold a transaction open across a long workflow

Example listener:

1. Starts Kafka transaction.
2. Calls an HTTP API with no timeout.
3. Waits for user approval.
4. Waits for another job to finish.
5. Sends output and commits.

This pattern is unsuitable for Kafka transactions. Break it into steps using Kafka events/workflow state and short transactions. Kafka transactions fit groups of Kafka operations that must commit/abort consistently within a bounded window.

### 13.2 Producer cache and maxAge

`DefaultKafkaProducerFactory` can cache transactional producers for reuse after a transaction finishes. If a producer sits idle too long, the broker may expire its `transactional.id`, causing errors when the factory reuses the stale producer.

Some Spring Kafka versions support configuring **maxAge** so the factory refreshes cached producers before `transactional.id` expires on the broker. For batch-style services or workloads with long idle gaps, this factor must be evaluated.

V2 does not eliminate the need to manage producer caches, TTLs, or the transaction coordinator.

## 14. Rolling deployments, scaling, and concurrency

A consumer group can have multiple pods, each running multiple child consumer containers. With V2:

- Consumers in the same logical group must still share **group.id**.
- Each application instance needs its own transactional ID prefix.
- Transactional producers receive suffixes/caching within the factory scope.
- Do not generate transactional IDs per record or per listener invocation.
- Expect group rebalances during scaling or rolling deploys.
- When ownership changes mid-transaction, the transaction may abort/fence instead of committing.

### 14.1 Example: 3 pods, concurrency 2

~~~text
Topic orders.in: 6 partitions
Consumer group: orders-transformer-prod

Pod A:
  2 child consumers
  tx prefix: orders-transformer-a-

Pod B:
  2 child consumers
  tx prefix: orders-transformer-b-

Pod C:
  2 child consumers
  tx prefix: orders-transformer-c-
~~~

There are six consumer members in total for the group, able to distribute the six partitions. The number of created/cached transactional producers can depend on concurrent transactions and producer factory lifecycle, and does not always equal the exact number of consumer members.

If concurrency increases from 2 to 4 across all three pods, total consumer members rise to 12 while the topic only has six partitions. Some consumers stay idle, while resource and rebalance overhead still exist.

### 14.2 Why shouldn't group.id be used directly as a shared prefix?

A broken configuration:

~~~text
Pod A:
  group.id = orders-transformer-prod
  tx prefix = orders-transformer-prod-

Pod B:
  group.id = orders-transformer-prod
  tx prefix = orders-transformer-prod-
~~~

Both pods can generate colliding transactional IDs when the factory assigns matching suffixes. The result is fencing between producers, commit errors, and instability. Group id is the **load-sharing** identity; transactional prefix is the **producer ownership** identity.

### 14.3 When fencing occurs during a rolling deploy

Do not merely increase retries. Check:

- Do two pods share the same `transactionIdPrefix`?
- Has the old pod actually stopped?
- Is a shared `ConfigMap` supplying a static ID?
- Is the factory creating new transactional producers with an ID that collides with an active one?
- Did a consumer group rebalance happen at the same time?
- Did the broker transaction coordinator report other errors?

Once a producer has been fenced, the old producer cannot validly continue its transaction. Let the framework/lifecycle replace the producer under the proper ownership configuration.

## 15. Reliability when commit fails or has unknown outcome

A producer sending a record successfully does not mean the Kafka transaction has committed. This can happen:

~~~text
send output: broker ACK
commitTransaction: timeout due to network
client does not receive commit response
~~~

The application should not conclude from a send ACK that output is definitely committed. Nor should it conclude every commit timeout definitely aborted without evidence consistent with the Kafka protocol.

A safe approach:

1. Let the Kafka client/transaction manager determine the state and handle exceptions per contract.
2. Do not reuse a fatal/fenced producer.
3. Allow inputs to be reprocessed when offsets are uncommitted per framework semantics.
4. Use stable event IDs so downstream can deduplicate across uncertainty windows.
5. Observe `read_committed` consumers instead of relying only on "send success" logs.

V2 improves offset coordination/fencing within the group, but cannot eliminate every case where a client disconnects or lacks immediate knowledge of a request outcome.

## 16. V2 and non-Kafka side effects

Suppose a listener:

~~~java
@KafkaListener(
    topics = "payments.in",
    containerFactory = "transactionalListenerFactory"
)
public void onPayment(PaymentRequested event) {

    paymentGateway.charge(event);
    kafkaTemplate.send(
        "payments.out",
        event.paymentId(),
        "PAID"
    );
}
~~~

If `paymentGateway.charge()` succeeds and then the Kafka transaction aborts, the input can be reprocessed. On the next run, `charge()` may be called a second time.

Therefore, **Kafka EOS is insufficient to guarantee single payment execution**.

You need:

- A stable idempotency key sent to the payment gateway.
- A mechanism storing processing/processed event state in the database.
- Reconciliation when external responses are ambiguous.
- Transactional outbox/inbox or an appropriate workflow.

### 16.1 Using transactional outbox

If business logic writes to a database and wants to publish a Kafka event:

~~~text
DB transaction:
  UPDATE orders
  INSERT outbox_event
COMMIT DB

Outbox relay:
  read outbox
  publish Kafka
  mark published status
~~~

Outbox stores the intent to emit an event alongside the business change, though the relay may send duplicates if it crashes between publishing and marking status. Consumers still need idempotency.

Do not treat EOSMode.V2 as a replacement for an outbox in systems with database side effects.

### 16.2 Only Kafka records reside inside a Kafka transaction

A Kafka transaction can include outputs across multiple Kafka topics/partitions and input offsets. It does not directly include HTTP requests, database commits, or cloud storage writes. When designing architecture, draw the transaction boundary clearly as follows:

~~~mermaid
flowchart TB
    subgraph K["Kafka transaction"]
        A["Kafka output records"]
        B["Kafka input offsets"]
    end
    C["SQL database"] --- K
    D["External HTTP API"] --- K
    E["Email service"] --- K
    F["Business idempotency + outbox/inbox"] --> C
    F --> D
    F --> E
~~~

The plain connectors in the diagram only represent a related workflow; they do **not** mean the database/HTTP/email are inside the Kafka transaction.

## 17. Observing EOSMode.V2 in production

A proper dashboard must observe **transaction outcomes**, not only producer send counts.

| Category | Metrics/events to track |
|---|---|
| Producer transaction | Begin, commit, abort, timeout, commit latency |
| Producer fencing | `ProducerFencedException`, invalid epoch, duplicate tx prefix |
| Kafka broker | Transaction coordinator health, ISR, transaction timeouts |
| Consumer group | Rebalance count, generation/member changes, assignment |
| Consumer lag | Committed offset, log end offset, LSO for `read_committed` |
| Output | Committed records, downstream processing progress |
| Retry/rollback | `AfterRollbackProcessor` attempts, DLT/recovery failures |
| Business | Event ID, deduplication, mismatch between input and output |
| Factory | `transactionCapable`, prefix uniqueness, cached producer age |

### 17.1 Logs distinguishing send and commit

Good logs should distinguish these events:

~~~text
event=KAFKA_TX_BEGIN
listener=orders-transformer
group=orders-transformer-prod
instance=pod-a

event=KAFKA_SEND_ACK
topic=orders.out
key=order-1001

event=KAFKA_TX_COMMIT_SUCCESS
group=orders-transformer-prod
inputTopic=orders.in
inputPartition=0
inputOffset=200
~~~

If only `KAFKA_SEND_ACK` is present without commit success, you cannot claim the output is eligible for `read_committed` downstream.

### 17.2 Symptoms to distinguish

**Output does not appear:** may be due to aborted or still-open transactions, downstream using `read_committed` and waiting on LSO, the listener not running, or producer send failures.

**Input record is reprocessed:** may be due to a Kafka transaction abort or uncommitted offset, not necessarily broken EOS.

**`ProducerFencedException` spikes:** may be due to duplicate transactional IDs or unstable ownership/lifecycle, not solely a Kafka broker fault.

**Consumer lag rises while HW keeps advancing:** with `read_committed`, this can involve open transactions holding back LSO, in addition to usual causes like a slow listener.

## 18. Integration tests to prove EOS V2

A unit test mocking `KafkaTemplate` cannot prove Kafka transaction semantics. Use a real Kafka broker via Testcontainers or an equivalent integration environment with a version supporting V2.

### 18.1 Happy path test

1. Create topics `orders.in` and `orders.out`.
2. Start the transactional listener container and `KafkaTemplate`.
3. Send an input event with a unique event ID.
4. Have the listener send an output record in the transaction.
5. Wait for the transaction to commit.
6. Use a `read_committed` consumer to read `orders.out`.
7. Verify output appears once per business ID and the input group offset advances.
8. Use logs/metrics to confirm transaction commit.

### 18.2 Abort test on listener exception

1. Send an input event.
2. In the listener, send output and intentionally throw an exception.
3. Confirm transaction abort.
4. Verify a `read_committed` consumer on `orders.out` does not read the aborted output.
5. Verify the input offset was not committed by the failed transaction.
6. Let the listener run again and succeed.
7. Verify only the successful transaction's output is seen by `read_committed` downstream.

Multiple listener invocations may occur; that is expected during retries. Verify committed Kafka effects, not just method invocation counts.

### 18.3 Rebalance and zombie fencing test

1. Run two consumer instances in the same group with different `transactionIdPrefix` values.
2. Make one consumer process slowly or stop polling per the test scenario.
3. Trigger a rebalance so partition ownership moves.
4. Attempt to let the old consumer continue committing a transaction without valid ownership.
5. Verify the protocol/framework prevents invalid offset commits from succeeding.
6. Verify the new consumer processes the input and commits validly.
7. Verify `read_committed` downstream does not see output from aborted transactions.

This test must be designed carefully around framework version, transaction timeout, and `max.poll.interval.ms`; simply killing a pod does not reproduce every fencing scenario.

### 18.4 Duplicate transactional ID test

1. In a test environment, intentionally configure two producers with the same transactional ID.
2. Confirm a fencing/epoch-related error occurs per Kafka semantics.
3. Fix the prefix to be unique per instance.
4. Re-run transaction commits.
5. Confirm both instances operate concurrently without ID contention.

This tests **misconfigured producer identity**, distinct from testing consumer group metadata.

### 18.5 read_uncommitted vs. read_committed test

- Send output in a transaction and then abort.
- Use a `read_uncommitted` consumer to observe behavior per the Kafka protocol.
- Use a `read_committed` consumer to verify aborted output is not delivered as valid data.
- Send a new transaction and commit; verify committed output appears.
- Observe LSO while a transaction is open if needed.

### 18.6 Crash between side effect and commit test

If the listener writes to a database:

1. Let the database write succeed.
2. Cause the Kafka transaction to abort or crash before Kafka commit.
3. Let the input be redelivered.
4. Verify database idempotency prevents duplicate writes.
5. Only conclude the business workflow is sufficiently safe once side effects are protected.

## 19. Common misconceptions

**"EOSMode.V2 only requires adding one enum to get exactly-once."** False. You need a transaction-capable `ProducerFactory`, transaction manager, transactional listener container, and offset-in-transaction actually working.

**"V2 removes the need for `transactional.id`."** False. Producers still require transactional identity; prefixes must not collide among concurrently active producers.

**"`group.id` and `transactionIdPrefix` should be identical across all pods."** False. Group id should match across replicas of a group, while transactional prefix requires uniqueness per producer factory instance.

**"`KafkaTemplate.send()` returning successfully means the transaction committed."** False. Send acknowledgment and commit outcome are two different events.

**"`read_committed` is unnecessary because the producer is already transactional."** False if downstream must ignore aborted records.

**"The consumer method will never run again."** False. Retries, aborts, restarts, and rebalances can cause inputs to be reprocessed.

**"V2 automatically makes database transactions and Kafka transactions atomic."** False. Separate mechanisms are needed for database/HTTP side effects.

**"Transaction abort means all side effects rolled back."** False for effects outside Kafka.

**"`ProducerFencedException` is always a broker bug."** False. Duplicate transactional IDs or ownership changes can be the cause.

**"Increasing transaction timeout fixes everything."** False. It can mask overly long transactions and stall `read_committed` progress.

**"Spring Kafka 3.x must call `setEosMode(V2)`."** Do not assume so. V2 is the supported EOS mechanism in modern releases; the enum API may no longer exist.

**"`read_committed` means every record in Kafka belongs to a transaction."** False. A `read_committed` consumer still reads valid non-transactional records.

## 20. EOS V2 troubleshooting procedure

When inputs are re-read unexpectedly, outputs are missing, or producers are fenced:

1. **Verify versions:** Are Spring Kafka, Kafka clients, and brokers compatible with V2?
2. **Check factory:** Does the right `ProducerFactory` have `transactionCapable()=true`?
3. **Check prefix:** Is `transactionIdPrefix` unique across active instances?
4. **Check manager:** Which factory does `KafkaTransactionManager` use?
5. **Check container:** Does the listener container open Kafka transactions and commit offsets through the transaction?
6. **Check auto commit:** Is consumer `enable.auto.commit` accidentally enabled?
7. **Inspect exceptions:** Distinguish producer fencing, transaction timeout, commit failure, serialization, and broker errors.
8. **Inspect group assignment:** Did a rebalance or member ownership loss occur mid-transaction?
9. **Check output visibility:** What is downstream `isolation.level`? Is there an open transaction/LSO stall?
10. **Reconcile input offsets:** Has the committed offset advanced, and is replay within the expected range?
11. **Check external side effects:** Did database/HTTP actions execute before the transaction aborted?
12. **Recover:** Fix configuration, let the framework clean up transactions, verify with a canary.
13. **Monitor after fix:** Commit/abort rate, output, lag, DLT, and duplicate business effects.

Do not reset input offsets just to "clear errors" before knowing which transactions actually committed. Seeking/resetting can cause massive replays or skip unprocessed records.

## 21. Implementation checklist

**Compatibility and capability**

- [ ] Kafka brokers and clients meet EOS V2 requirements.
- [ ] Know whether the Spring Kafka version uses the `EOSMode` enum or only supports V2.
- [ ] Actual `ProducerFactory` is transaction-capable.
- [ ] `KafkaTemplate` and `KafkaTransactionManager` use the same right factory.
- [ ] Unique transaction ID prefix exists across active application instances.

**Listener and offset**

- [ ] Transactional listener container is configured using the API of the actual Spring Kafka version.
- [ ] Consumer auto offset commit is disabled.
- [ ] Input offsets are sent by the container into the same Kafka transaction as outputs.
- [ ] No independent `commitSync`/`commitAsync` path breaks transaction boundaries.
- [ ] Retry/rollback/recovery uses mechanisms compatible with transactional listeners.

**Producer and downstream**

- [ ] Producer idempotence, acks, timeout, and replication/ISR are properly configured.
- [ ] Transactions are not held open excessively due to external I/O.
- [ ] Producer fencing, cache age, and transaction timeouts are monitored.
- [ ] Downstream uses `read_committed` when committed visibility is required.
- [ ] Alerts exist for open transactions/LSO stalls and consumer lag anomalies.

**Business correctness**

- [ ] EOS boundary is accurately defined: Kafka output + Kafka offset.
- [ ] Database/HTTP/email side effects have idempotency or outbox/inbox.
- [ ] Business event IDs exist for reconciliation and deduplication when needed.
- [ ] Runbooks exist for rollback, DLT, and ambiguous commit failures.

**Verification**

- [ ] Tested successful commits using a `read_committed` consumer.
- [ ] Tested aborts after sending output.
- [ ] Tested rebalances/fencing in an integration environment.
- [ ] Tested duplicate transactional IDs and recovery behavior.
- [ ] Tested crashes between external side effects and Kafka commits.
- [ ] Metrics exist for transaction commit/abort, fencing, and offset progression.

## 22. Conclusion

**EOSMode.V2** is Spring Kafka's modern EOS mechanism that combines Kafka producer transactions with consumer group information when committing offsets in the same transaction. It improves fencing/ownership handling compared to the legacy mechanism and forms the foundation of the consume-transform-produce exactly-once model **within Kafka's scope**.

Proper implementation requires more than selecting a mode option: `ProducerFactory` must be transaction-capable, transactional IDs must not collide among active producers, `KafkaTransactionManager` and the listener container must use the right factory, input offsets must enter the transaction alongside outputs, and downstream must read with `read_committed` if aborted outputs must be excluded. When inputs are retried or transactions abort, business code can still execute again; non-Kafka side effects always need dedicated protection. That boundary is what makes EOSMode.V2 a verifiable reliability mechanism rather than a misleading configuration label.

