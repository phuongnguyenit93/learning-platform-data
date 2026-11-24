# sendOffsetsToTransaction

In Kafka and Spring Kafka, **sendOffsetsToTransaction** is the operation that places **consumer offsets** into an **open Kafka producer transaction**, so that input offsets are committed **atomically together with output records** when the transaction commits successfully. This is the single most critical link in the **consume → process → produce** model for **exactly-once semantics (EOS) within Kafka**.

When a consumer reads a record from topic A, processes it, and publishes to topic B, the application must ensure not only that the output is written successfully, but also that **the input read checkpoint is never decoupled from the output**. If the output appears while the input offset has not been saved, a restart can cause the old record to be reprocessed and produce duplicate output. If the input offset commits first while publishing fails, input data can be skipped without producing a result. Placing offsets into the same Kafka transaction as the output closes both failure windows inside the Kafka ecosystem.

**Core point:** calling `sendOffsetsToTransaction` **is not a commit yet**. It only registers offsets in the current transaction. Output records and offsets take effect and commit together only when **commitTransaction()** succeeds; if the transaction aborts, neither the transactional output records nor the corresponding offset updates are committed.

## 1. The problem: non-transactional Kafka-to-Kafka processing

Suppose an application receives an order:

~~~text
orders.created, partition 1, offset 100
value = OrderCreated(orderId=42)
~~~

The listener transforms it into the event:

~~~text
inventory.commands, key=42
value = ReserveInventory(orderId=42)
~~~

Without transactions, an implementation might perform:

1. Consumer reads offset 100.
2. Producer publishes `ReserveInventory` to `inventory.commands`.
3. Consumer commits offset 101 of `orders.created-1`.

However, the process can die between step 2 and step 3. The output exists while the committed offset remains 100. When the consumer restarts, it can re-read offset 100 and emit a new output. Reversing the order and committing the offset before publishing means a publish failure can lead to **lost output**.

~~~mermaid
flowchart TD
    A["Consumer reads offset 100"] --> B["Publish output"]
    B --> C{"Publish finished?"}
    C -->|Yes| D["Commit offset 101 separately"]
    C -->|Dies before offset commit| E["Restart: re-read offset 100"]
    E --> F["Output may be published twice"]
    D --> G["Completed"]
~~~

Kafka transactions allow combining output publication and input offset commit into a single logical unit instead of two unbound operations.

## 2. What does sendOffsetsToTransaction do?

The transactional producer API is typically used in this sequence:

~~~text
initTransactions()
    |
    v
beginTransaction()
    |
    +-- send(output A)
    +-- send(output B)
    +-- sendOffsetsToTransaction({input partition: next offset}, group metadata)
    |
    v
commitTransaction()
~~~

When commit succeeds:

- Transactional output records transition to committed state, so consumers using **read_committed** can read them.
- Input consumer group offsets are updated as part of the transaction.
- When the consumer group resumes, it starts from the committed offsets.

If the transaction aborts:

- Output records belonging to this transaction are not returned to **read_committed** consumers.
- Offsets added via `sendOffsetsToTransaction` **are not committed**.
- Input records remain eligible for reprocessing according to offset/rebalance rules.

~~~mermaid
flowchart TD
    A["Poll input records"] --> B["beginTransaction"]
    B --> C["Produce output records"]
    C --> D["sendOffsetsToTransaction"]
    D --> E{"Transaction outcome"}
    E -->|Commit| F["Output visible to read_committed"]
    E -->|Commit| G["Consumer group offsets advance"]
    E -->|Abort| H["Output marked aborted"]
    E -->|Abort| I["Group offsets do not advance from transaction"]
~~~

Output data may already have been written to the Kafka log prior to commit time. **Committed status**, not merely Kafka having received the bytes, is the basis on which a `read_committed` consumer treats a record as valid output.

## 3. KafkaProducer API

The Kafka client provides the modern overload accepting an offset map and **ConsumerGroupMetadata**:

~~~java
void sendOffsetsToTransaction(
        Map<TopicPartition, OffsetAndMetadata> offsets,
        ConsumerGroupMetadata groupMetadata
) throws ProducerFencedException, KafkaException;
~~~

The signature above illustrates the parameter types and common exceptions; the complete exception list varies across Kafka client versions.

Meaning:

| Parameter | Meaning |
|---|---|
| **Map<TopicPartition, OffsetAndMetadata>** | Next offset to store for each successfully processed input topic-partition |
| **TopicPartition** | Topic and partition pair of the **input** record |
| **OffsetAndMetadata** | Offset to commit, usually last processed offset + 1, with optional metadata |
| **ConsumerGroupMetadata** | Information about the consumer group owning the partitions, used for group coordination and fencing |

Example map:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
        new TopicPartition("orders.created", 1),
        new OffsetAndMetadata(101L)
);
~~~

This map states that the consumer group has processed up through offset 100 of `orders.created-1` and the next read should begin at offset 101.

These are **not** offsets of the output topic. The producer manages output offsets itself when writing. The map represents only the read progress of **input partitions**.

## 4. The offset + 1 rule

This is the most common logic bug when calling `sendOffsetsToTransaction` directly.

For a record at offset 100, after successful processing, **the offset to commit is 101**. A committed offset is the next position the consumer group will read, not the ID of the record just processed.

Example:

| Partition | Successfully processed records | Offset to add to transaction |
|---|---|---:|
| orders.created-0 | 10, 11, 12 | 13 |
| orders.created-1 | 40, 41 | 42 |
| orders.created-2 | 100 | 101 |

Code:

~~~java
TopicPartition tp =
        new TopicPartition(record.topic(), record.partition());

OffsetAndMetadata next =
        new OffsetAndMetadata(record.offset() + 1L);
~~~

If you commit the last processed offset itself rather than `offset + 1`, the last record can be read again. If you commit past records that have not succeeded, the application can drop data.

### Offsets advance independently per partition

A single poll can return records from multiple partitions. Checkpoints must be computed **separately per partition**.

~~~java
Map<TopicPartition, OffsetAndMetadata> nextOffsets =
        new HashMap<>();

for (TopicPartition tp : records.partitions()) {

    List<ConsumerRecord<String, String>> partitionRecords =
            records.records(tp);

    // Assumes all records in this partition have been processed.
    ConsumerRecord<String, String> last =
            partitionRecords.get(partitionRecords.size() - 1);

    nextOffsets.put(
            tp,
            new OffsetAndMetadata(last.offset() + 1L)
    );
}
~~~

Never take the highest offset across the whole poll and apply it to all partitions. Offsets are only meaningful within a single topic-partition.

If the application succeeds on only a **subset** of records in a poll, never commit past a failed record. Commits must reflect **contiguous completed progress** per partition.

## 5. Why is ConsumerGroupMetadata needed?

Kafka needs to know which consumer group an offset update belongs to and whether the producer is committing on behalf of a valid consumer group member.

Consumer group metadata can contain the group ID, generation, member ID, and related group protocol information. It enables Kafka to detect offset commit operations coming from a stale consumer member after a rebalance, improving zombie-processing prevention.

In Kafka client code:

~~~java
ConsumerGroupMetadata groupMetadata =
        consumer.groupMetadata();

producer.sendOffsetsToTransaction(
        nextOffsets,
        groupMetadata
);
~~~

Obtain metadata from the **KafkaConsumer participating in the group that polled the input**. Do not construct group metadata from a bare group ID string when this API is available.

Older Kafka client versions had an overload accepting only a String **groupId**. The modern overload taking `ConsumerGroupMetadata` supplies fuller group information to support fencing. When migrating legacy code, verify the Kafka client API and group management strategy.

### When a rebalance occurs

Suppose consumer A is assigned partition 1, reads offset 100, and begins processing. Then the group rebalances and partition 1 moves to consumer B. If A still attempts to commit offsets using stale metadata, Kafka can reject the operation based on group generation/fencing.

This matters: if A emitted output yet cannot commit the transaction containing the offset, A's transactional output should not be seen by `read_committed` consumers as a valid committed result of an invalid processing attempt.

In a hand-rolled consumer loop, you must handle rebalance listeners, partition revocation/assignment, and transaction rollbacks carefully. The Spring Kafka listener container provides orchestration to reduce how much the application must manage itself.

## 6. Prerequisites

Before calling `sendOffsetsToTransaction`, you need both a properly configured **transactional producer** and a **consumer group**.

### Producer

- Has a **transactional.id**.
- Called **initTransactions()** before the first transaction.
- Called **beginTransaction()** for the current transaction.
- Producer is in a valid, unfenced state.
- Output records are sent using the **same producer transaction**.

### Consumer

- Has polled records and holds valid consumer group metadata.
- **enable.auto.commit=false**.
- Explicit group ID and valid assignment.
- Does not commit input offsets via a separate path that could break atomicity.
- Does not let multiple threads call `KafkaConsumer` concurrently; `KafkaConsumer` is not thread-safe for normal poll/seek/commit operations.

### Downstream consumer

If it must observe only committed transactional outputs, configure:

~~~properties
isolation.level=read_committed
~~~

If downstream uses `read_uncommitted`, it may receive records from aborted transactions; you then cannot rely on EOS visibility to guarantee processing only committed outputs.

### Broker and security

The Kafka cluster must support transactions and have an appropriate transaction coordinator configuration. The producer needs topic `WRITE` permissions and required transactional ID permissions; the consumer needs `READ` and group operation permissions. Misconfigured security/ACLs can prevent the producer from starting or committing transactions.

## 7. Pure Java example: consume → process → produce

This example demonstrates the key Kafka client APIs. It intentionally separates **transaction processing** from **commit** to avoid assuming a transaction aborted if a timeout occurs during commit.

~~~java
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;

public class TransactionalBatchProcessor {

    private final KafkaConsumer<String, String> consumer;
    private final KafkaProducer<String, String> producer;

    public TransactionalBatchProcessor(
            KafkaConsumer<String, String> consumer,
            KafkaProducer<String, String> producer) {
        this.consumer = consumer;
        this.producer = producer;
    }

    public void pollAndProcess() throws Exception {

        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofSeconds(1));

        if (records.isEmpty()) {
            return;
        }

        producer.beginTransaction();

        try {
            Map<TopicPartition, OffsetAndMetadata> offsets =
                    new HashMap<>();

            for (TopicPartition tp : records.partitions()) {

                List<ConsumerRecord<String, String>> partitionBatch =
                        records.records(tp);

                for (ConsumerRecord<String, String> record :
                        partitionBatch) {

                    String result = transform(record.value());

                    producer.send(
                            new ProducerRecord<>(
                                    "processed.orders",
                                    record.key(),
                                    result
                            )
                    ).get();
                }

                long lastOffset =
                        partitionBatch.get(
                                partitionBatch.size() - 1
                        ).offset();

                offsets.put(
                        tp,
                        new OffsetAndMetadata(lastOffset + 1L)
                );
            }

            producer.sendOffsetsToTransaction(
                    offsets,
                    consumer.groupMetadata()
            );

        } catch (Exception processingFailure) {
            try {
                producer.abortTransaction();
            } catch (Exception abortFailure) {
                processingFailure.addSuppressed(abortFailure);
            }

            // Do not allow further polling that skips uncommitted records.
            // Must seek/reinitialize according to the current assignment.
            throw processingFailure;
        }

        // Commit is handled separately.
        // If this call throws, DO NOT blindly assume the transaction aborted.
        producer.commitTransaction();
    }

    private String transform(String value) {
        return value.toUpperCase();
    }
}
~~~

The example above is **not a complete production-ready Kafka consumer application**. It omits:

- Producer initialization with `transactional.id` and `initTransactions()`.
- `subscribe`/`assign`, continuous poll loop, and shutdown.
- Rebalance listener, partition handoff, and seeking after abort.
- Handling fatal/fenced producer errors.
- Retries/backoff, metrics, timeouts, and tracing.
- Handling uncertain outcomes when `commitTransaction` throws an exception.
- Lifecycle management across threads and instances.

If a transaction aborts while the consumer retains its post-poll position, a hand-rolled application must **seek back to uncommitted offsets or recreate the consumer to resume from committed offsets**. Never keep polling new records after an abort and treat old inputs as processed. The Spring Kafka container handles much of this orchestration for the application.

## 8. Producer initialization and consumer configuration example

Transactional producer:

~~~java
Properties producerConfig = new Properties();

producerConfig.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "broker-1:9092,broker-2:9092"
);
producerConfig.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
);
producerConfig.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
);
producerConfig.put(
        ProducerConfig.TRANSACTIONAL_ID_CONFIG,
        "orders-projector-instance-a"
);

KafkaProducer<String, String> producer =
        new KafkaProducer<>(producerConfig);

producer.initTransactions();
~~~

Consumer:

~~~java
Properties consumerConfig = new Properties();

consumerConfig.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "broker-1:9092,broker-2:9092"
);
consumerConfig.put(
        ConsumerConfig.GROUP_ID_CONFIG,
        "orders-projector"
);
consumerConfig.put(
        ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
        false
);
consumerConfig.put(
        ConsumerConfig.ISOLATION_LEVEL_CONFIG,
        "read_committed"
);

consumerConfig.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
);
consumerConfig.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
);
~~~

Setting **read_committed** on the input consumer is necessary if the input topic has transactional records and the application must not read records aborted upstream. For EOS on outputs, it is essential that **downstream consumers** also use `read_committed`.

**transactional.id** must be unique for each concurrently active producer when no intentional takeover is occurring. If replicas share the same `transactional.id`, the newer producer can fence the older one.

## 9. What happens inside Kafka?

A Kafka transaction involves the producer, transaction coordinator, output topic-partitions written by the producer, and the consumer group coordinator responsible for offsets.

When the producer calls **sendOffsetsToTransaction**:

1. The producer identifies the consumer group and the list of offsets to bring into the transaction.
2. The Kafka transaction coordinator and group coordinator coordinate to record the offsets as part of the ongoing transaction.
3. Offsets do not become independent group committed checkpoints before the transaction outcome is decided.
4. When **commitTransaction()** succeeds, the transaction coordinator writes the commit outcome and offsets become committed.
5. On abort, the transaction's offset updates are not committed.

~~~mermaid
sequenceDiagram
    participant C as Kafka consumer
    participant P as Transactional producer
    participant TC as Transaction coordinator
    participant GC as Group coordinator
    participant O as Output partitions

    C->>C: poll input
    P->>TC: begin transaction
    P->>O: send output records
    P->>TC: add consumer group offsets to transaction
    TC->>GC: coordinate transactional offset commit
    P->>TC: commitTransaction()
    TC->>O: commit markers
    TC->>GC: transaction commit decision
    GC-->>C: next committed input offsets available
~~~

The diagram is conceptual; the internal protocol involves additional requests, states, and coordination steps. You do not need to re-implement the protocol when using `KafkaProducer`/`KafkaTemplate` properly.

## 10. Producer identity, epoch, and fencing

A transactional producer has a **transactional.id** and a producer epoch. Kafka uses this mechanism to prevent an old producer from continuing to write data as if it still owned the transaction after a new producer has taken over the same transactional ID.

Example:

~~~text
Pod A: transactional.id = orders-projector-0
Pod B: transactional.id = orders-projector-0
~~~

If both pods are alive simultaneously, the newer producer can fence the older producer. A fenced producer may throw `ProducerFencedException` on send/commit/abort.

Distinguish:

- **Producer fencing:** prevents a zombie producer from using an old `transactional.id`.
- **Consumer group fencing:** group generation/member metadata helps detect offset commits from a consumer that is no longer a valid member.
- **Idempotent producer:** avoids duplicate writes from producer retries within the same producer session/sequence, yet does not replace transactions for atomic output + offset.

In Spring Kafka, `transaction-id-prefix` must be configured so active producers do not unintentionally share IDs, especially across scale-out, rolling deployments, and producer caches.

## 11. Spring Kafka usually calls sendOffsetsToTransaction automatically

In Spring Kafka applications using a **transactional listener container**, you normally **do not need to call `sendOffsetsToTransaction` manually inside a `@KafkaListener` method**.

The container handles:

1. Starting the Kafka transaction for the corresponding processing unit.
2. Invoking the listener.
3. Allowing the listener to publish outputs via a `KafkaTemplate` bound to the transaction.
4. After the listener succeeds, determining processed offsets.
5. Sending those offsets into the Kafka transaction.
6. Committing the transaction.
7. On error, aborting and executing after-rollback processing.

As a result, the listener stays focused on business logic and does not have to calculate offsets or manage `KafkaConsumer` group metadata directly.

~~~mermaid
flowchart TD
    A["KafkaMessageListenerContainer"] --> B["begin transaction"]
    B --> C["@KafkaListener"]
    C --> D["KafkaTemplate.send() output"]
    D --> E{"Listener succeeded?"}
    E -->|Yes| F["Container sends consumed offsets to transaction"]
    F --> G["Commit Kafka transaction"]
    E -->|No| H["Abort transaction"]
    H --> I["AfterRollbackProcessor / redelivery"]
~~~

Note: if the listener manually invokes an incompatible offset-commit/ack API while the container controls the transaction, it can cause conflicts or make checkpoint calculation confusing. Manage offsets manually only when design requires it and transaction ownership is clearly defined.

## 12. Configuring Spring Boot transactional producers

A common Spring Boot configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9092,broker-2:9092
    producer:
      transaction-id-prefix: order-projector-pod-a-
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      group-id: order-projector
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Setting **transaction-id-prefix** enables Spring to generate transactional producer IDs from the prefix and a suffix. In supported versions, Spring Boot can auto-configure **KafkaTransactionManager** from the transactional producer factory. Verify that the factory/container is actually wired with the transaction manager, especially when declaring custom listener factories.

In multi-instance deployments, prefixes must be designed to avoid producer ID collisions. The sample value `pod-a` represents one instance; never copy it unchanged across all replicas.

### Configuring the listener factory

Depending on the Spring Kafka version, you can configure a Kafka-aware transaction manager on container properties:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
transactionalFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        KafkaTransactionManager<String, ProcessedOrder> transactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(transactionManager);

    return factory;
}
~~~

This illustrates the API for Spring Kafka versions supporting **setKafkaAwareTransactionManager**; older codebases may have a different method name. The actual generic types of the transactional producer depend on output record types and do not need to match the consumer input type.

### Listener needs only business logic

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-projector",
    containerFactory = "transactionalFactory"
)
public void onOrder(OrderCreated event) {
    ProcessedOrder output = transform(event);

    kafkaTemplate.send(
            "orders.projected",
            event.orderId(),
            output
    );
}
~~~

When the listener completes, the container is responsible for placing processed offsets into the Kafka transaction before committing. If the listener throws an exception, the container must not treat that run as successful and will follow the appropriate rollback/recovery path.

**Not every `KafkaTransactionManager` bean in context automatically turns every listener into a transactional listener.** Verify the active container factory, Spring Boot auto-configuration, and transaction manager for your version.

## 13. KafkaTemplate and TransactionManager

`KafkaTemplate` can participate in Spring-managed Kafka transactions. Some versions also expose **executeInTransaction** for publishing multiple output records within a local transaction.

~~~java
kafkaTemplate.executeInTransaction(ops -> {
    ops.send("orders.projected", key, value);
    ops.send("orders.audit", key, auditValue);
    return null;
});
~~~

However, this API mainly addresses grouping **output records in the same transaction**. It does not automatically replace the container flow that commits **input consumer offsets** when a suitable transactional listener container is absent.

Distinguish three cases:

| Usage | Kafka output in transaction | Input offsets in same transaction |
|---|---|---|
| `KafkaTemplate.executeInTransaction` for pure publishing | Yes | Not automatically unless consumer offset handling is wired in |
| `@Transactional` with `KafkaTransactionManager` on a publish service | Yes | Not automatically just because the method has `@Transactional` |
| Transactional `KafkaListenerContainer` consume-process-produce | Yes | Container can send consumed offsets into the same transaction per configuration |

Do not add `@Transactional` to a listener and assume Kafka offsets are atomic with outputs if the actual listener container is not managing transactions properly.

## 14. Record listeners, batch listeners, and transaction scope

Understand the exact **processing unit** the container uses as its transaction boundary.

With a record listener, the container may fetch multiple records from one poll and invoke the listener per record. In transactional mode, the transaction boundary and offset-commit mechanism are determined by the framework; do not infer from a single-record method signature that there is always strictly one transaction per record.

With a batch listener, the method receives a collection. The transaction may span the entire batch or a unit split by the container per configuration. If one record in the batch fails, verify whether other output records in that transaction are aborted.

Some configurations offer **subBatchPerPartition**, splitting a poll batch into per-partition groups. When paired with a transaction manager, this can alter transaction boundaries in applicable versions.

Always verify:

- Whether the listener is record or batch.
- Container concurrency.
- Records per poll.
- Transaction scope in the version being used.
- `AckMode` and error-handler/after-rollback semantics.
- Which partitions a transaction can commit offsets for.
- When one record fails, which subset gets redelivered.

If a batch processed three partitions and only one partition failed, never commit offsets for all three if the output transaction aborted.

## 15. sendOffsetsToTransaction and AckMode

Spring Kafka's `AckMode` controls how the container acknowledges progress in regular listener models, whereas when the container uses Kafka transactions, offsets are placed into the transaction via the container's transaction-aware mechanism.

Pitfalls to avoid confusing:

- **AckMode.RECORD** does not mean the application must call `sendOffsetsToTransaction` manually for each record.
- **Acknowledgment.acknowledge()** is not a direct call to `KafkaProducer.sendOffsetsToTransaction`.
- **Consumer.commitSync()** does not replace a transactional offset commit.
- When using transactions, let the container own offset commits; avoid parallel commit paths outside the transaction.
- With manual acks, understand how acknowledgments coordinate with the transaction manager in the version in use.

A system needs **one clear source of ownership** over offset progress. Mixing regular commits with transactional commits without explicit design defeats atomic consume-process-produce.

## 16. read_committed and Last Stable Offset

Outputs of a Kafka transaction are not protected for consumers using **read_uncommitted** in the way expected in an EOS pipeline. To ensure downstream sees only committed outputs, configure:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

When reading with `read_committed`:

- The consumer does not return records from aborted transactions.
- The consumer does not return records from open, uncommitted transactions.
- The consumer still reads non-transactionally published records.
- Kafka uses the **Last Stable Offset (LSO)** to bound the readable position when open transactions exist.

For example, transaction T1 writes record A and stays open for a long time. A `read_committed` consumer can be blocked at the LSO and not read records after A on the same partition yet, even if those later records came from another producer.

When monitoring lag, distinguish normal backlogs from delays caused by long-running/open transactions. Do not conclude a Kafka consumer is broken just because the broker holds records that a `read_committed` consumer cannot see yet.

## 17. Fencing due to rebalance: a realistic scenario

Suppose group `inventory-projector` has consumer C1 processing partition P0:

~~~text
T0: C1 polls P0 offset 100.
T1: C1 begins Kafka transaction.
T2: C1 publishes output.
T3: C1 processes longer than max.poll.interval.ms.
T4: Consumer group rebalances, P0 is assigned to C2.
T5: C1 tries sendOffsetsToTransaction with stale group metadata.
~~~

At T5, group coordination can reject the transactional offset commit because C1 is no longer a valid member/current generation. If the transaction cannot commit, `read_committed` consumers will not treat that transaction's output as committed.

Ways to reduce risk:

- Shorten listener processing time.
- Limit `max.poll.records`.
- Set `max.poll.interval.ms` based on real processing times, not only the happy path.
- Avoid holding a Kafka transaction open while waiting minutes on an HTTP API if you can redesign the flow.
- Use the Spring Kafka container to coordinate rebalances and after-rollback logic.
- Monitor rebalance counts, transaction aborts, and consumer lag.

Do not raise `max.poll.interval.ms` arbitrarily just to avoid rebalances; doing so delays detection of dead consumers.

## 18. transaction.timeout.ms and processing time

A Kafka producer transaction has **transaction.timeout.ms**, and the broker enforces a transaction timeout cap. If a transaction stays open past the threshold, the broker can abort it. An aborted transaction will not commit input offsets added via `sendOffsetsToTransaction`.

At the same time, a Kafka consumer has **max.poll.interval.ms**. A listener can hit both the transaction timeout and the poll interval if it processes too many records or waits on downstream dependencies.

| Setting | Scope |
|---|---|
| `transaction.timeout.ms` | Maximum time a Kafka producer transaction can remain open |
| `transaction.max.timeout.ms` | Broker-enforced maximum timeout limit |
| `max.poll.interval.ms` | Maximum time allowed between poll calls |
| `max.poll.records` | Maximum records returned per poll |
| `delivery.timeout.ms` | Maximum time the producer tries to complete record sends |
| `request.timeout.ms` | Client wait time for a single request |

Do not address transaction timeout issues by raising just one parameter. Measure transaction duration, records per partition, and dependency latency, then pick an appropriate transaction scope.

## 19. When a listener throws an exception or producer send fails

With a transactional listener container, if the listener throws an exception, the Kafka transaction is normally aborted and the transaction's offsets are not committed. After rollback, **AfterRollbackProcessor** can perform seek/redelivery or recovery depending on version and configuration.

If the application uses `KafkaProducer` directly:

- Processing errors before commit usually require an abort if the transaction is still in an abortable state.
- Fencing/fatal producer errors may require closing the producer and not reusing it.
- After an abort, the consumer must re-read uncommitted offsets or seek to the right position.
- Do not treat a successful `send()` call as sufficient to conclude output is committed.
- If an error occurs inside `commitTransaction`, analyze the outcome by exception type before deciding on recovery.

Do not catch a listener exception and return normally if business work did not actually finish:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "transactionalFactory"
)
public void handle(OrderCreated record) {
    try {
        businessService.process(record);
    } catch (RuntimeException ex) {
        log.error("Processing failed", ex);
        // Wrong if you want container rollback: exception was swallowed.
    }
}
~~~

The simple path is letting the exception escape:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "transactionalFactory"
)
public void handle(OrderCreated record) {
    businessService.process(record);
}
~~~

For business errors intentionally ignored, model the processing outcome explicitly; do not arbitrarily "swallow errors" in ways that alter checkpoints.

## 20. Uncertain commit outcomes

One of the hardest failures occurs when the client calls **commitTransaction()**, but the connection drops before receiving the response. The Kafka broker may have committed, or the transaction may not have committed. Never assume the outcome solely from an application-side timeout.

Principles:

1. Distinguish send errors, `sendOffsetsToTransaction` errors, and `commitTransaction` errors.
2. Do not catch every commit exception and unconditionally call abort or resend outputs.
3. Inspect exception types and the contract of the Kafka client version in use.
4. When a producer enters a fatal state, close it and reinitialize per the transaction recovery policy.
5. Use event IDs and idempotency to cope with redeliveries or indeterminate commit outcomes.
6. Reconcile input committed offsets and downstream visibility once the system stabilizes.
7. If non-Kafka side effects exist, run domain reconciliation.

Kafka EOS solves atomic Kafka output + Kafka offsets much better, yet cannot turn the network into a channel where commit responses are always certain from the application's viewpoint.

## 21. Why is idempotency still needed even with EOS?

**Exactly-once semantics in Kafka** does not mean a listener method runs only once. A listener can start, send output, experience a transaction abort, and be invoked again. Internal operations (CPU, logs, databases, HTTP calls) can execute multiple times, while `read_committed` consumers see Kafka outputs only from committed transactions.

If a listener updates a database before the Kafka transaction commits:

~~~text
1. Database update COMMITS.
2. Kafka transaction COMMIT fails.
3. Input offset did not advance with the transaction.
4. Record is redelivered.
5. Database update risks executing a second time.
~~~

To protect the database, use a **transactional inbox**:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within the same database transaction, insert a marker with a unique `event_id` and apply the business change. If the record is redelivered after a Kafka abort, the database can detect the duplicate.

If you need to emit a Kafka event after a database commit, use a **transactional outbox** to store the domain change and outgoing event in the same database transaction, with a separate publisher relaying to Kafka.

Do not use `sendOffsetsToTransaction` as a replacement for inbox/outbox: this API coordinates only **Kafka consumer offsets** with a **Kafka producer transaction**, and does not commit an external database or REST API.

## 22. Comparing processing guarantee strategies

| Strategy | Atomic Kafka output + input offset | Prevents duplicate external side effects | Complexity |
|---|---|---|---|
| Non-transactional producer + separate consumer commit | No | Not automatically | Low |
| Idempotent producer, separate offset commit | No | Not automatically | Medium |
| Kafka transaction + `sendOffsetsToTransaction` | Yes, within Kafka | Not automatically | Medium/High |
| Kafka transaction + inbox database | Yes in Kafka; inbox protects DB separately | Yes if implemented properly | High |
| Database outbox + idempotent publisher | DB change + outbox atomic; Kafka publish separate | Can achieve reliability via idempotency | High |
| Saga/workflow | Depends on orchestration | Requires compensation/idempotency design | High |

An idempotent producer prevents duplicates from producer retries, yet an event reprocessed by the application after a consumer offset issue can still create new output. Kafka transactions combined with offsets address another crucial class of duplicates in Kafka-to-Kafka pipelines.

## 23. Partition ordering and offset correctness

Kafka preserves ordering per partition. With transactional offset commits, ensure offsets advance only across a **contiguously completed** range of records.

Suppose P0 has:

~~~text
Offset 10: success
Offset 11: failure
Offset 12: success (processed asynchronously)
~~~

If you commit offset 13 in a transaction when only 10 and 12 finished, record 11 may be skipped on restart. That is a logic bug, even if the transaction commit succeeds at the protocol level.

The system must choose:

- Sequential processing per partition.
- Waiting for all jobs prior to the checkpoint to complete.
- Contiguous completed-offset tracking for asynchronous processing.
- Never committing past an unprocessed gap.

When using the default `KafkaListener` container, avoid offloading records to an async executor and returning immediately if the container will mark the listener complete before side effects/outputs actually finish. If using async acknowledgments or asynchronous listener APIs per your version, understand how the framework tracks completion, ordering, and transaction boundaries.

## 24. Multi-partition polls and transaction scope

A consumer can poll multiple partitions at once. If all are processed in one transaction, the offsets map must contain each processed partition individually.

Example:

~~~text
Poll:
  orders.created-0 : offsets 2, 3
  orders.created-1 : offsets 20, 21, 22
  orders.created-2 : offset 105

Transaction outputs:
  6 processed records

sendOffsetsToTransaction:
  orders.created-0 -> 4
  orders.created-1 -> 23
  orders.created-2 -> 106
~~~

If the transaction aborts because one record fails, offsets for all three partitions in the transaction do not commit. Upon application restart, data already processed in the failed attempt may be re-read. This matches atomic transaction scope, though it can increase reprocessing cost.

If a workload has many partitions and large batches, consider per-partition transaction scopes or smaller batches where your Spring Kafka version supports it. Never manually commit a partial offsets map from an aborted transaction.

## 25. When should you avoid calling this API directly?

In Spring Kafka applications using **@KafkaListener** and a properly configured transactional container, you normally **do not need to write code calling `sendOffsetsToTransaction`**.

Calling it directly inside a listener carries risks:

- Lacking proper access to consumer group metadata.
- Sending the wrong offset by misidentifying processed records.
- Committing offsets twice or diverging from container management.
- Failing to handle rebalance/seek/abort properly.
- Mixing the container's producer with another producer transaction.
- Sending offsets into a transaction that does not contain the matching output records.
- Failing to handle transaction outcomes when commit fails.

Only use the `KafkaProducer` API directly when building a custom consumer loop, a framework adapter, or under technical requirements demanding direct transaction control. Even then, write integration tests against a real broker.

## 26. Monitoring and observability

Metrics to track:

| Metric | Purpose |
|---|---|
| Transaction begin/commit/abort count | Tracks transaction outcomes |
| Transaction duration | Detects transactions staying open too long |
| Producer commit latency | Detects coordinator/network anomalies |
| Offset-in-transaction failure rate | Detects consumer group or coordinator errors |
| Producer fencing errors | Detects `transactional.id` contention |
| Consumer group rebalance count | Correlates with stale group metadata |
| Consumer lag | Input backlog |
| Read-committed visibility delay | Time outputs wait for transaction commit |
| Transaction timeout count | Detects overly long transactions |
| `AfterRollbackProcessor` retry/recovery | Observes redelivery after aborts |
| Downstream failure rate | Explains causes of transaction aborts |

A transaction event log can include:

~~~text
event=kafka_transaction_committed
service=orders-projector
instance=pod-a
consumer_group=orders-projector
input_topic=orders.created
input_partition=1
next_committed_offset=101
transaction_id_prefix=orders-projector-pod-a-
duration_ms=48
~~~

Do not use continuously changing offsets, event IDs, or `transactional.id` values as metric tags due to high cardinality. They fit better in structured logs or controlled traces.

### Priority alerts

- Transaction abort rate spiking after deployment.
- `ProducerFencedException` appearing in bursts.
- Commit latency rising alongside consumer lag.
- `max.poll.interval.ms` violations or continuous rebalances.
- `read_committed` downstream lag rising due to long-open transactions.
- `AfterRollbackProcessor` continuously retrying the same record without recovery.
- Outputs appearing without input offset commits due to missing transaction wiring.

## 27. Common implementation mistakes

**Committing the just-processed offset itself.** Must use `last processed offset + 1`.

**Computing one shared offset for the whole poll.** Offsets are per topic-partition.

**Committing past an unfinished record.** Can lose business data even when the transaction commit succeeds.

**Using `consumer.commitSync()` alongside transactional commits.** Creates a checkpoint path not atomic with outputs.

**Forgetting `enable.auto.commit=false`.** Auto-commit can advance offsets outside the Kafka transaction.

**Calling `sendOffsetsToTransaction` without `beginTransaction`.** The API requires a transactional producer with an open transaction.

**Not obtaining `ConsumerGroupMetadata` from the real consumer.** Can lack generation/member information and proper fencing.

**Treating a `sendOffsetsToTransaction` call as already committed.** `commitTransaction` is required for the outcome to take effect.

**Downstream reading `read_uncommitted`.** May see aborted outputs.

**Colliding `transactional.id` on scale-out.** New producer fences old producer.

**Listener swallowing exceptions.** Container may commit the transaction and offsets even though business logic failed.

**Continuing to poll from the current position after transaction abort in a custom loop.** Can skip uncommitted records; must seek/reinitialize appropriately.

**Assuming EOS protects databases and HTTP APIs.** Inbox/outbox/idempotency are required.

**Not testing rebalances mid-processing.** Stale group metadata errors can hit immediately under real load.

## 28. Incident scenario: timeout while sending offsets

Suppose the application published output records in a transaction, but **sendOffsetsToTransaction** fails due to a coordinator timeout.

What is NOT guaranteed:

- Outputs cannot be assumed committed.
- Input offsets cannot be assumed advanced.
- You cannot conclude the pipeline succeeded just because output send futures completed.

How to respond:

1. Log the exception and classify as retryable/fatal/fencing.
2. If the transaction is in an abortable state per client contract, abort cleanly.
3. If the producer is fenced or fatal, close the producer and reinitialize per policy.
4. Do not keep polling and skip uncommitted inputs.
5. Let the consumer group re-receive records from committed offsets, or seek back while assignment remains valid.
6. Check transaction coordinator and group coordinator health.
7. Check whether a rebalance occurred during processing.
8. Rely on idempotency for side effects that may already have occurred outside Kafka.

Never automatically call `commitSync()` after `sendOffsetsToTransaction` fails to "save the offset." That breaks the goal of atomic Kafka transactions.

## 29. Incident scenario: producer fenced

If a producer is fenced by another producer sharing the same `transactional.id`:

~~~text
Producer A begins transaction
Producer B starts with same transactional.id
Kafka increments epoch for that identity
Producer A tries sendOffsetsToTransaction/commit
Producer A is fenced
~~~

Actions:

- Close Producer A; do not reuse it.
- Identify the root cause of the duplicate `transactional.id`.
- Check rolling deployments, replica counts, and `transaction-id-prefix`.
- Let the instance with valid ownership continue processing.
- Reconcile consumer group assignments and transactional offsets.
- Verify records from the old transaction are not visible to `read_committed` consumers when the transaction did not commit.

Do not "fix" this by turning off idempotence or removing `transactional.id`. That strips away the transaction and fencing protections the system needs.

## 30. Integration testing with a Kafka broker

Unit tests can verify the offsets map is calculated properly. However, to prove atomic Kafka output + offsets, you need a real Kafka broker or Testcontainers.

Scenarios:

| Test | Expectation |
|---|---|
| 1 input record, 1 output record, commit | `read_committed` sees output; group offset = input offset + 1 |
| Multiple input partitions | Each partition has an independent next offset |
| Send output then abort | `read_committed` sees no output; group offsets do not advance |
| Producer dies before commit | Transaction does not commit; input can be reprocessed |
| Producer dies after commit | Output and input offsets commit together |
| `sendOffsetsToTransaction` with stale group metadata | Commit rejected per fencing/group rules where applicable |
| Consumer rebalance mid-processing | Does not silently commit stale offsets |
| Duplicate `transactional.id` | Producer fencing detected |
| Downstream `read_uncommitted` | May see aborted/uncommitted output, illustrating the limitation |
| Database side effect then abort | Inbox/idempotency prevents duplicates on redelivery |
| Partial batch failure | Does not commit past incomplete records |
| Transaction timeout | Abort/failure observed, no wrong checkpoint created |

### Assertion suggestions

1. Use a dedicated test group ID; do not share committed offsets with other tests.
2. Send an input record with a deterministic event ID.
3. Run the transactional listener against the output topic.
4. Wait for output using a `read_committed` consumer.
5. Verify the input group's committed offset matches the exact next offset.
6. Throw an exception in the listener and confirm no committed output appears.
7. Verify the input can redeliver or follow the recovery policy.
8. Trigger a rollback after output send futures have completed to prove send is not equivalent to commit.
9. Test multiple partitions and separate per-partition offset calculations.
10. Use polling assertions with timeouts rather than fixed `Thread.sleep()` delays.

When running transactional tests, topics and group metadata must be cleaned up or isolated appropriately; avoid reusing the same `transactional.id` concurrently across tests.

## 31. Runbook when an exactly-once pipeline stalls

If the pipeline processes inputs while outputs are invisible or consumer lag grows:

1. Identify listener ID, service, consumer group, and `transactional.id`/prefix.
2. Verify the container is actually transactional, not merely that a `KafkaTransactionManager` bean exists.
3. Inspect producer begin/commit/abort logs and send failures.
4. Verify whether input offsets are being added into the transaction.
5. Check the offsets map per topic-partition, especially `offset + 1`.
6. Verify whether consumer group metadata is valid when `sendOffsetsToTransaction` is called.
7. Check rebalances, `max.poll.interval.ms`, and `transaction.timeout.ms`.
8. Check producer fencing / transactional ID collisions.
9. Verify downstream uses `read_committed` if EOS visibility is required.
10. Inspect Last Stable Offset and open transactions.
11. Check whether the listener swallows exceptions or returns before async processing finishes.
12. If transactions abort, confirm redelivery/`AfterRollbackProcessor` is not stuck.
13. If DB/APIs outside Kafka exist, verify inbox/outbox/reconciliation.
14. After fixing, monitor commit rate, abort rate, consumer lag, and duplicate side effects.

Never use `commitSync()` to push offsets past a failing transaction. If outputs did not commit, advancing offsets independently can lose output data.

## 32. Pre-production checklist

**Producer and transaction**

- [ ] Transactional producer has a unique `transactional.id` across live instances.
- [ ] `initTransactions` is called or Spring Kafka's `ProducerFactory` is used.
- [ ] Output records are published in the same Kafka transaction.
- [ ] `sendOffsetsToTransaction` is called before `commitTransaction` in custom loops.
- [ ] Producer fatal/fencing errors have explicit handling paths.
- [ ] Transaction timeouts and commit latency are measured.

**Consumer offsets**

- [ ] Consumer group has an explicit `group.id` and auto-commit disabled.
- [ ] Offset map is computed per `TopicPartition`.
- [ ] Committed offset is the next offset after the last contiguously processed record.
- [ ] Never commits past incomplete records.
- [ ] `ConsumerGroupMetadata` is obtained from the consumer active in the group.
- [ ] Rebalances/aborts have appropriate seek or replay handling.

**Spring Kafka**

- [ ] Listener container has the right Kafka-aware transaction manager.
- [ ] `KafkaTemplate` uses a transactional `ProducerFactory` aligned with the container.
- [ ] No manual offset commits collide with container ownership.
- [ ] `AfterRollbackProcessor` and recovery policies are defined.
- [ ] Downstream requiring EOS uses `isolation.level=read_committed`.

**Business and operations**

- [ ] Non-Kafka side effects have idempotency/inbox/outbox.
- [ ] Integration tests exist for commit, abort, crash, rebalance, and fencing.
- [ ] Metrics exist for transaction duration, commit/abort, and lag.
- [ ] Send success is not treated as transaction committed.
- [ ] Runbooks exist for uncertain commit outcomes.
- [ ] DLT/replay does not break business consistency.

## 33. Summary of principles

**sendOffsetsToTransaction** attaches **input consumer group offsets** to a Kafka producer transaction containing output records. When the transaction commits, outputs and input checkpoints commit together in Kafka; when it aborts, neither transactional outputs nor offset updates take committed effect. This is the foundation for building exactly-once Kafka-to-Kafka processing.

Three key points to remember: **(1)** commit the next offset, i.e., `last processed offset + 1` per `TopicPartition`; **(2)** pass `ConsumerGroupMetadata` from the consumer actually participating in the group to support fencing; **(3)** `sendOffsetsToTransaction` only stages the offset update, whereas `commitTransaction` determines the transaction outcome. In Spring Kafka, let the transactional listener container manage this operation rather than calling it directly from `@KafkaListener`.

Finally, Kafka exactly-once does not guarantee a listener runs only once and does not automatically make transactions atomic with databases or HTTP APIs. Add idempotency, inbox/outbox, transactional ID management, `read_committed` consumers, crash/rebalance testing, and monitoring so EOS truly protects your system in production.
