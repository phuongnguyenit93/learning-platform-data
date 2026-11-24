# Committing Transactions

In Spring Kafka, **committing a transaction** is the step that successfully concludes a **Kafka transaction**: the Kafka transaction coordinator records the transaction as committed so that records published within the transaction become visible to consumers using **isolation.level=read_committed**. If the transaction also contains consumer offsets via **sendOffsetsToTransaction**, those offsets are committed together with the output records. This is the foundation for building **consume → process → produce** flows with **Kafka-scoped** exactly-once semantics.

Committing a transaction is **not the same** as calling `KafkaTemplate.send()`, flushing the producer, or committing offsets standalone. A `send` call may finish writing data into the Kafka log while the transaction has not yet ended; for consumers reading committed-only records, those records cannot be processed before the transaction commits.

In production, you must understand exactly what is committed, when commit succeeds, how to recognize commit failures, and the limits of exactly-once with databases or external APIs outside Kafka.

## 1. What Problem Does a Kafka Transaction Solve?

Suppose a consumer reads an **orders.created** event, processes it, and writes two subsequent events:

- **inventory.reserved**
- **billing.requested**

With a non-transactional producer, the first send may succeed while the second fails. A downstream consumer could observe reserved inventory with no billing request. With a transactional producer, both records can be written in the same Kafka transaction and are only considered **committed** together.

For applications that both read from Kafka and write to Kafka, there is another issue: if output is written yet the input offset is not committed, after a restart the input may be reprocessed. Kafka transactions allow adding the **input offset** to the transaction holding the output records, committing both as a single unit inside Kafka.

~~~mermaid
flowchart LR
    A["Input topic: orders.created"] --> B["Consumer / listener"]
    B --> C["Process data"]
    C --> D["Kafka transaction"]
    D --> E["Output: inventory.reserved"]
    D --> F["Output: billing.requested"]
    D --> G["Input offset"]
    E --> H{"Commit transaction"}
    F --> H
    G --> H
    H -->|Success| I["Output visible to read_committed and offset advances"]
    H -->|Abort| J["Output aborted, offset not committed in transaction"]
~~~

Kafka may still persist sent records to the log prior to commit. Transaction commit/abort markers and consumer isolation determine which records are allowed to be returned to applications.

## 2. Concepts to Distinguish

| Concept | Meaning |
|---|---|
| **send()** | Sends a record to the producer; the operation may complete asynchronously |
| **flush()** | Waits for records queued in the producer to finish sending at the producer layer |
| **beginTransaction()** | Starts a transaction on a transactional producer |
| **commitTransaction()** | Requests the transaction coordinator to finalize the transaction as committed |
| **abortTransaction()** | Aborts an in-progress transaction if state/API permits |
| **commitSync()/commitAsync()** on consumer | Standard offset commit, not automatically tied to a Kafka producer transaction |
| **sendOffsetsToTransaction()** | Enlists consumer group offsets into a producer transaction |
| **@Transactional** with `KafkaTransactionManager` | Manages transaction boundaries via Spring |
| **read_committed** | Consumer returns only records from committed transactions or non-transactional records |
| **read_uncommitted** | Consumer may see records from uncommitted or aborted transactions |

`commitTransaction` cannot be replaced by `flush`. Flushing only indicates sends finished at the producer layer; it does not write the transaction coordinator's commit decision.

## 3. Lifecycle of a Kafka Transaction

With the raw producer API, the conceptual sequence is:

1. Initialize a producer with **transactional.id** and appropriate serializers.
2. Call **initTransactions()** before executing the first transaction.
3. Call **beginTransaction()**.
4. Send one or more records.
5. Depending on the use case, enlist consumer offsets via **sendOffsetsToTransaction()**.
6. If all work is valid, call **commitTransaction()**.
7. If an error occurs before the commit phase and the transaction is still abortable, call **abortTransaction()**.
8. Close the producer or reuse it for the next transaction according to lifecycle policy.

~~~mermaid
stateDiagram-v2
    [*] --> Ready: initTransactions()
    Ready --> InTransaction: beginTransaction()
    InTransaction --> InTransaction: send()/sendOffsetsToTransaction()
    InTransaction --> Committing: commitTransaction()
    InTransaction --> Aborting: abortTransaction()
    Committing --> Ready: commit succeeds
    Aborting --> Ready: abort succeeds
    Committing --> Failed: fatal error / uncertain outcome
    Aborting --> Failed: abort error
    Failed --> [*]: close producer, recover safely
~~~

This diagram illustrates application logic; Kafka producers maintain more internal states. Do not infer from the diagram that a producer can always be reused after any exception. Errors such as fencing or fatal producer errors may force the application to close the producer and create a new one.

## 4. Configuring a Transactional Kafka Producer

A transactional Kafka producer requires **transactional.id**. This is the identifier used by the transaction coordinator to manage epochs, transaction state, and fencing of stale producers.

Java Kafka client example:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

Properties config = new Properties();
config.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "broker-1:9092,broker-2:9092"
);
config.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
);
config.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
);
config.put(
        ProducerConfig.TRANSACTIONAL_ID_CONFIG,
        "orders-service-instance-a"
);

KafkaProducer<String, String> producer =
        new KafkaProducer<>(config);

producer.initTransactions();
~~~

When `transactional.id` is configured, the Kafka client enforces constraints required for transactional producers, including idempotent producer settings. Still, applications must verify **acks**, retries, delivery timeouts, broker compatibility, and transactional ID permissions for the target environment.

Each active transactional producer needs a transactional ID that avoids accidental collisions. If two producers concurrently use the same `transactional.id`, the producer with the newer epoch can **fence** the older producer. Fencing is useful to stop zombie producers, but causes failures when multiple instances unintentionally claim the same ID.

## 5. Committing a Transaction via the KafkaProducer API

Example sending two output records in the same transaction:

~~~java
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

public void publishBoth(
        KafkaProducer<String, String> producer,
        String orderId,
        String inventoryPayload,
        String billingPayload) throws Exception {

    producer.beginTransaction();

    boolean commitStarted = false;

    try {
        producer.send(new ProducerRecord<>(
                "inventory.reserved",
                orderId,
                inventoryPayload
        )).get();

        producer.send(new ProducerRecord<>(
                "billing.requested",
                orderId,
                billingPayload
        )).get();

        commitStarted = true;
        producer.commitTransaction();

    } catch (Exception ex) {

        if (!commitStarted) {
            try {
                producer.abortTransaction();
            } catch (Exception abortFailure) {
                ex.addSuppressed(abortFailure);
            }
        }

        throw ex;
    }
}
~~~

In this example, **get()** calls wait for send results to detect failures before attempting commit. Waiting here is an illustrative choice to make the transaction boundary clear; in high-throughput systems, asynchronous sends can be used while collecting completion signals prior to commit via an appropriate mechanism.

The `commitStarted` flag distinguishes failures **before commit begins** from failures **during commit**. Once `commitTransaction` has been called and throws an exception, the outcome may depend on the exception type and coordinator state; never blindly call `abort` and assume the transaction definitely did not commit. Follow the Kafka client/version contract, and when state cannot be confirmed, close the producer and rely on idempotency and safe recovery.

For Spring Kafka applications, prefer `KafkaTemplate` and `KafkaTransactionManager` over manually managing transactional producers.

## 6. Transaction Commit vs Offset Commit

**Standard offset commit** records the position a consumer group has processed so a subsequent startup can resume from there. **Kafka transaction commit** decides the fate of records emitted by a transactional producer and can also commit offsets sent into the transaction.

For example, if a consumer reads offset 42 and produces output:

~~~text
Input: orders.created-0, offset 42
Output: inventory.reserved, order 9001
Offset to save next: 43
~~~

Comparison of cases:

| Handling approach | If process dies after publishing output but before offset commit |
|---|---|
| Non-transactional publish, separate offset commit | Input offset 42 may be reprocessed and emit duplicate output |
| Kafka transaction containing output and input offset | If transaction did not commit, output is invisible to `read_committed` and transaction offset did not advance |
| Kafka transaction committed | Output and input offset are committed together in the Kafka transaction |
| Database update outside Kafka transaction | No automatic atomicity between database and Kafka |

If a partition processes records up to offset 42, the offset value stored is **43**: the position of the next record to read. Accidentally committing 42 instead of 43 causes the last record to be reprocessed.

## 7. Enlisting Consumer Offsets in a Kafka Transaction

The Kafka client provides **sendOffsetsToTransaction** to add consumer group offsets to a producer transaction. This is the key mechanism for achieving exactly-once processing when both input and output reside in Kafka.

Conceptual flow:

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

void processPollTransactionally(
        KafkaConsumer<String, String> consumer,
        KafkaProducer<String, String> producer) throws Exception {

    ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofSeconds(1));

    if (records.isEmpty()) {
        return;
    }

    producer.beginTransaction();

    boolean commitStarted = false;

    try {
        Map<TopicPartition, OffsetAndMetadata> nextOffsets =
                new HashMap<>();

        for (TopicPartition partition : records.partitions()) {

            List<ConsumerRecord<String, String>> batch =
                    records.records(partition);

            for (ConsumerRecord<String, String> record : batch) {
                String output = transform(record.value());

                producer.send(new ProducerRecord<>(
                        "processed.events",
                        record.key(),
                        output
                )).get();
            }

            ConsumerRecord<String, String> last =
                    batch.get(batch.size() - 1);

            nextOffsets.put(
                    partition,
                    new OffsetAndMetadata(last.offset() + 1)
            );
        }

        producer.sendOffsetsToTransaction(
                nextOffsets,
                consumer.groupMetadata()
        );

        commitStarted = true;
        producer.commitTransaction();

    } catch (Exception ex) {
        if (!commitStarted) {
            try {
                producer.abortTransaction();
            } catch (Exception abortFailure) {
                ex.addSuppressed(abortFailure);
            }
        }
        throw ex;
    }
}
~~~

This snippet illustrates one poll, one transaction. It omits continuous poll looping, shutdown/rebalance listeners, seeking back to uncommitted offsets after abort, error classification, and producer lifecycle management. If writing a manual consumer loop, handle all of those so records are not skipped after transaction rollbacks. In Spring Kafka, let the container manage it.

Specifically, **sendOffsetsToTransaction** must use the metadata of the consumer group owning the partitions and the exact offsets to commit. Modern APIs accept **ConsumerGroupMetadata** so the transaction coordinator can validate group info against fencing and group membership; never construct arbitrary group IDs or metadata ad hoc.

## 8. Kafka Transactions in Spring Boot

Spring Boot supports auto-configuring Kafka transactional producers when **transaction-id-prefix** is declared:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9092,broker-2:9092
    producer:
      transaction-id-prefix: orders-service-instance-a-
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

When a transactional producer factory is present, Spring Boot can auto-configure a **KafkaTransactionManager** and matching `KafkaTemplate` according to the Boot version used. The goal is letting Spring manage producer lifecycle, transaction begin/commit/abort, and producer cache reuse.

**transaction-id-prefix** is not a single `transactional.id`. Spring Kafka builds transactional IDs by combining the prefix with a suffix/sequence per version mechanism. Each concurrently running instance must have an ID namespace that does not collide with other instances. On Kubernetes, the prefix can incorporate pod identity or a stable instance identifier matching your deployment strategy.

Do not hard-code the same prefix for all replicas if instance suffix allocation can produce colliding IDs. Duplicate `transactional.id` values lead to **ProducerFencedException** or hard-to-diagnose transaction errors.

## 9. KafkaTemplate.executeInTransaction

If an application only needs to send multiple Kafka records as an atomic group and does not consume Kafka input in the same transaction, **KafkaTemplate.executeInTransaction** can be used:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishEvents(
            OrderEvent inventoryEvent,
            OrderEvent billingEvent) {

        kafkaTemplate.executeInTransaction(operations -> {
            operations.send(
                    "inventory.events",
                    inventoryEvent.orderId(),
                    inventoryEvent
            );

            operations.send(
                    "billing.events",
                    billingEvent.orderId(),
                    billingEvent
            );

            return null;
        });
    }
}
~~~

The callback runs inside a transaction managed by `KafkaTemplate`. When the callback finishes normally, the template attempts to commit. When the callback throws an error, the template performs rollback/abort according to transactional producer semantics.

Send operations in modern Spring Kafka typically return **CompletableFuture**. If business logic needs to know a send failed before the callback returns, await/combine futures or throw appropriately from the callback. Never treat calling `send()` without an immediate exception as proof of successful publishing. Transaction commit can also surface producer errors, but explicit exception handling identifies which record caused the failure.

In production, use appropriate timeouts when awaiting producer futures and monitor exceptions from both send and commit. Do not wrap database writes inside `executeInTransaction` and assume the database joins the Kafka transaction automatically.

## 10. @Transactional with KafkaTransactionManager

Spring Kafka provides **KafkaTransactionManager** to manage Kafka producer transactions through Spring's transaction abstraction. With a matching transaction manager bean, services can use **@Transactional**:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class KafkaOnlyPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public KafkaOnlyPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(String orderId) {
        kafkaTemplate.send(
                "inventory.events",
                orderId,
                "reserved"
        );

        kafkaTemplate.send(
                "billing.events",
                orderId,
                "requested"
        );
    }
}
~~~

The name **kafkaTransactionManager** in the annotation must match the actual transaction manager bean. If the same application also has `JpaTransactionManager` or `DataSourceTransactionManager`, specifying the name explicitly avoids picking the wrong default manager.

You can declare the manager explicitly:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTransactionManager;
import org.springframework.kafka.core.ProducerFactory;

@Bean
KafkaTransactionManager<String, String> kafkaTransactionManager(
        ProducerFactory<String, String> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
~~~

In Spring Boot, declare it manually only if auto-configuration does not create the desired manager or you need a custom setup. Avoid registering a second manager in the same role without understanding bean selection.

**Self-invocation:** an internal call between two methods in the same bean may bypass Spring's transaction proxy. For `@Transactional` to take effect, ensure callers invoke through the Spring proxy or use `TransactionTemplate` / another suitable approach.

## 11. Listener Container Transactions and Committing After Processing

In the **consume → process → produce** model, the listener container can manage the Kafka transaction itself:

1. Container polls input records.
2. Container starts a Kafka transaction for the corresponding processing unit.
3. Container invokes `@KafkaListener`.
4. Listener publishes output via a compatible transactional `KafkaTemplate`.
5. If the listener completes normally, the container adds input offsets to the Kafka transaction.
6. Container commits the transaction.
7. If the listener fails, the transaction aborts and the after-rollback mechanism coordinates redelivery/recovery.

Spring Kafka provides APIs to attach a Kafka-aware transaction manager to `ContainerProperties`. In supporting versions:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
transactionalListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);

    return factory;
}
~~~

This example reflects the Spring Kafka generation featuring **setKafkaAwareTransactionManager**. Older versions may use another method, such as **setTransactionManager**; check against your running version. The actual generic types of `ProducerFactory`/`KafkaTemplate` must match the outputs being published, not necessarily the consumer's value type.

Listener example:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-projector",
    containerFactory = "transactionalListenerFactory"
)
public void onOrder(OrderEvent event) {

    var projection = transform(event);

    kafkaTemplate.send(
            "orders.projected",
            event.orderId(),
            projection
    );
}
~~~

The container transaction wraps the listener. If the method throws an exception, it must escape so the container receives the rollback signal. Do not catch and suppress exceptions, causing the container to commit the Kafka transaction as successful when business processing actually failed.

Once a transactional listener container is configured, you typically do not need an extra Kafka `@Transactional` on the listener itself to open another independent Kafka transaction. Understand managers and transaction synchronization before stacking annotations.

## 12. Transaction Scope for Record and Batch Listeners

Transaction boundaries depend on container configuration and listener type.

- **Record listener:** the container invokes the method per record, though transaction scope may cover records from a poll depending on container semantics/version. Never assume one transaction equals strictly one record across all configurations.
- **Batch listener:** one invocation can process multiple records in a batch; an error can roll back the transaction for the active batch slice.
- **subBatchPerPartition:** some configurations allow splitting batches into per-partition sub-batches for partition-scoped processing/transaction boundaries.
- **Concurrency:** each child consumer thread/container has its own transaction context and producer lifecycle; transactional IDs must not collide.

Never design recovery assuming per-record commits if the container commits per poll or batch. Determine actual transaction scope from version, listener type, `AckMode`, and container settings.

## 13. Visibility: read_committed vs read_uncommitted

Kafka consumers have the **isolation.level** setting:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

With **read_committed**, consumers do not return records written in aborted or still-open transactions, while continuing to read non-transactional records normally. With **read_uncommitted**, consumers may see records belonging to aborted/uncommitted transactions before completion, so commit markers cannot be relied upon to filter them out.

Example:

~~~text
T0: Producer starts transaction T1.
T1: Producer sends record A.
T2: Producer sends record B.
T3: Transaction remains open.
T4: Producer commits transaction T1.
~~~

A `read_committed` consumer does not receive A and B before the transaction commits at T4. A `read_uncommitted` consumer may observe already-written records prior to T4 depending on fetch timing and log availability.

### Last Stable Offset (LSO)

For `read_committed`, Kafka tracks the **last stable offset** to avoid returning records past an undecided open transaction. A long-open transaction can prevent `read_committed` consumers from reading subsequent records on the same partition, even from other producers.

Therefore, **long-running open transactions** can cause consumer lag or apparent stalls. Never look solely at producer send success to conclude downstream consumers have seen a record.

## 14. Commit Markers, Abort Markers, and Broker State

The Kafka transaction coordinator manages transaction state, while partition logs record the data records and control markers consumers need to interpret transaction outcomes.

A single transaction can send records to multiple partitions or topics. Kafka coordinates the commit/abort decision via the transaction coordinator protocol so `read_committed` consumers observe consistent state.

Do not confuse **transaction committed** with **record processed by downstream business listeners**. Committing only makes records eligible to valid consumers; downstream can still be slow, fail deserialization, or have a backlog.

Records published to the log consume disk/network before commit. Aborting does not immediately erase bytes from the log; aborted records are skipped by `read_committed` consumers based on metadata and transaction markers.

## 15. Successful Commit, Failed Commit, and Uncertain Outcomes

When calling `commitTransaction`, several outcomes can occur:

| Case | What is known | Handling |
|---|---|---|
| Commit succeeds | Transaction was committed by coordinator per client contract | Safe to start next transaction |
| Error before commit starts | Commit not yet called; transaction can abort if producer still valid | Abort per exception type; keep full logs |
| Producer fenced | Producer lost ownership of transactional ID | Close producer, fix ownership/ID, do not reuse |
| Transaction timeout error | Transaction may have expired/aborted | Inspect error type and coordinator state |
| Network timeout during commit | Outcome may be uncertain on application side | Do not assume aborted; handle cautiously and rely on idempotency |
| Fatal producer state error | Producer may be unable to continue | Close producer and reinitialize per policy |

**Uncertain outcome** is a scenario requiring explicit operational design. If the commit response is lost due to network failure while the broker committed, replaying external side effects can cause duplicates. If the broker did not commit, transaction outputs stay invisible to `read_committed` consumers and input offsets did not advance with the transaction.

Avoid writing "catch any exception from commit, call abort, unconditionally resend all outputs" without checking exception types. Depending on state, the client may disallow aborting, or the commit may already have succeeded while the response was lost.

Applications should rely on framework transactional Kafka APIs, error classification, producer lifecycle management, and idempotent business identifiers to recover safely when immediate outcome is unknowable.

## 16. Producer Fencing and transactional.id

Kafka uses **transactional.id** and producer epochs to protect against zombie producers. When a new producer with the same `transactional.id` initializes, the old producer can be fenced. If the old producer tries to send or commit, it can encounter **ProducerFencedException**.

Example deployment with two replicas:

~~~text
Replica A: transactional.id = orders-worker-0
Replica B: transactional.id = orders-worker-0
~~~

If both replicas truly run simultaneously, they can continuously fence each other. That setup is unsafe unless part of a controlled takeover mechanism.

One approach:

~~~text
Replica A: transaction-id-prefix = orders-worker-a-
Replica B: transaction-id-prefix = orders-worker-b-
~~~

Spring Kafka generates transactional IDs inside each instance's dedicated namespace. With multi-pod systems, prefixes/suffixes should come from deployment identity or managed ID allocation to avoid collisions during rolling updates.

Distinguish **intentional fencing** when a new instance takes over a logical identity from **fencing due to misconfiguration**. If logs show continuous `ProducerFencedException` after scale-out, check duplicate prefixes, producer cache counts, and concurrent ownership first.

## 17. Transaction Timeout and max.poll.interval.ms

Kafka producers have **transaction.timeout.ms**. Brokers also enforce a maximum cap on transaction timeouts. If a transaction stays open too long, the coordinator can abort it or reject configurations exceeding the cap.

Consumers have **max.poll.interval.ms** to bound the interval between polls under group management. If a listener blocks processing too long, the consumer may be evicted from the group and partitions reassigned to another consumer.

These settings are related yet distinct:

| Configuration | Scope | Impact |
|---|---|---|
| `transaction.timeout.ms` | Kafka transactional producer | Limits how long a transaction may stay open |
| `transaction.max.timeout.ms` | Broker | Maximum transaction timeout permitted by the broker |
| `max.poll.interval.ms` | Kafka consumer | Maximum time allowed between poll calls |
| `max.poll.records` | Consumer | Limits records returned per poll, indirectly affecting processing time |
| `delivery.timeout.ms` | Producer | Upper bound for completing a send |
| `request.timeout.ms` | Client request | Time waiting for a single request response |

An overly long transaction can both time out on the producer and trigger a consumer rebalance. If the producer commits offsets against stale group metadata, the transaction can fail or be fenced by group coordination.

Do not use transactions to wrap slow network calls or multi-minute manual waits if an alternative design is possible. Reduce batch sizes, shorten processing, use an outbox, or split workflows when needed.

## 18. Do Not Swallow Exceptions in Listener Transactions

Incorrect example:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "transactionalListenerFactory"
)
public void handle(OrderEvent event) {
    try {
        orderService.apply(event);
    } catch (RuntimeException ex) {
        log.error("Order processing failed", ex);
        // Returns normally: container may commit the transaction.
    }
}
~~~

If the exception is swallowed, the listener method exits normally. The container may assume work succeeded, enlist offsets, and commit the Kafka transaction. This loses Kafka redelivery even though business processing did not complete.

The proper handling is **letting the exception propagate** so the transaction rolls back and after-rollback recovery decides the next step:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "transactionalListenerFactory"
)
public void handle(OrderEvent event) {
    orderService.apply(event);
}
~~~

If an error is an expected domain event and business logic wants to acknowledge the offset without retrying, model it as an explicit processing outcome or publish an appropriate failure/compensation event inside the transaction rather than silently swallowing errors.

## 19. DefaultErrorHandler and AfterRollbackProcessor

For listener containers **without Kafka transactions**, Spring Kafka commonly uses **DefaultErrorHandler** to govern retries and recovery when a listener throws.

For listener containers **using Kafka transactions**, when a listener fails and the transaction rolls back, recovery typically goes through **AfterRollbackProcessor** (such as `DefaultAfterRollbackProcessor`) to seek/redeliver or recover records. Using `DefaultErrorHandler` does not directly replace transaction rollback semantics.

Distinction:

| Component | Context |
|---|---|
| `DefaultErrorHandler` | Handles listener errors in standard containers: retries/backoff/recovery |
| `AfterRollbackProcessor` | Handles post-rollback actions in transactional listener containers |
| `DeadLetterPublishingRecoverer` | Publishes failed records to a DLT per policy |
| `KafkaTransactionManager` | Manages Kafka producer transactions |
| `KafkaTemplate` | Sends records inside the bound transaction |
| `KafkaListener` container | Coordinates polling, listener invocation, offsets, and transactions |

If you want failed records sent to a DLT and recovered offsets committed inside a Kafka transaction, configure a processor and transaction manager compatible with your Spring Kafka version. For example, recovery transaction options and committing recovered offsets depend on constructors and version. Never assume a `DefaultErrorHandler` attached to a transactional factory behaves identically to a non-transactional container.

## 20. Kafka Transactions Do Not Automatically Cover Databases

A dangerous misconception: if a listener has Kafka transactions configured and also has JPA's `@Transactional`, **Kafka records and database rows commit atomically**. In reality, these are **two separate transaction managers** across two separate resource systems.

Spring can synchronize commit order in some configurations, such as database-first then Kafka-second, yet there is no default atomic distributed transaction. Scenario:

1. Database transaction commits successfully.
2. Kafka transaction commit fails.
3. Database has changed while Kafka output remains invisible.

Reversing the commit order means Kafka commits successfully and then the database commit fails. Inconsistent states can still happen either way.

Therefore, you need:

- **Transactional outbox:** persist business changes and an outbox event in the same database transaction; a separate worker publishes outbox rows to Kafka with idempotency.
- **Transactional inbox:** persist processed event IDs and database side effects in the same transaction to withstand redeliveries.
- **Idempotency keys:** protect external APIs and domain commands from duplication.
- **Reconciliation/compensation:** resolve states committed on one side without committing on the other.

Kafka EOS protects the Kafka-to-Kafka pipeline; it does not turn REST calls, emails, databases, or filesystems into part of a Kafka transaction.

## 21. Exactly-Once Semantics: What Is and Isn't Guaranteed

Kafka transactions and idempotent producers achieve Kafka-scoped exactly-once processing semantics under these conditions:

- Output records are sent via a transactional producer.
- Input offsets are committed in the same Kafka transaction as outputs.
- Downstream consumers use **read_committed** if they must see only committed transactional outputs.
- Transactional IDs are managed to prevent zombie producers.
- The application has no side effects outside Kafka escaping the transaction without additional safeguards.

Do not claim "every `@KafkaListener` method executes strictly once". Listeners can still be re-invoked after aborts/restarts/rebalances. The guarantee applies to **observable committed Kafka outputs and input offsets**, not CPU execution counts of code.

Similarly, if a listener calls a payment API before the Kafka transaction commits, the API may already have processed the request. After an abort, the listener is invoked again and may call the API a second time. Use idempotency keys or another workflow design.

## 22. Throughput and Transaction Commit Cost

Kafka transactions carry more overhead than non-transactional publishing:

- The transaction coordinator must track state and participating partitions.
- Commit/abort requires protocol rounds, control records, and network requests.
- Transactional producers have dedicated lifecycles and caches.
- Downstream `read_committed` consumers may wait on open transactions.
- Transaction timeouts must be tuned against batch and processing durations.

Committing after every tiny record can add noticeable overhead. Making transactions too large reduces commit frequency but increases latency and timeout/rebalance risks.

Optimization options:

1. Measure real throughput and end-to-end latency.
2. Choose appropriate batch sizes / transaction durations.
3. Minimize non-Kafka calls inside transactions.
4. Avoid sizing producer transaction caches too small for concurrency.
5. Tune partition counts based on capacity.
6. Monitor transaction commit/abort rates.
7. If Kafka-to-Kafka EOS is unnecessary, evaluate whether an idempotent non-transactional producer with inbox/outbox fits better.

Never disable transactions solely because of perceived overhead without first verifying which business invariants they protect.

## 23. Concurrency and Producer Cache

In Spring Kafka, a transactional `ProducerFactory` can cache producers keyed by transactional ID suffix. Each concurrent transaction needs a valid producer and a unique ID within the factory scope.

As listener concurrency rises, concurrent transactions rise. If the producer cache/suffix pool cannot keep up, the application may hit transactional producer allocation failures or create unexpected resources, depending on version.

Account for:

- Number of child listener containers per instance.
- Number of concurrent non-listener publisher transactions.
- Number of application instances.
- Transactional ID namespace per instance.
- Producer cache capacity and suffix strategy.
- Broker connections and quotas.

Monitor transactional ID errors, fencing, producer initialization, and transaction commit latency after every scale-out. If prefixes collide across instances, a larger cache will not fix ownership conflicts.

## 24. Observing Commit/Abort in Production

Key metrics/fields:

| Metric | Meaning |
|---|---|
| Transaction commit rate | Number of transactions committed successfully |
| Transaction abort rate | Number of aborted transactions |
| Commit latency | Time spent calling commit / awaiting coordinator |
| Transaction duration | Time from begin to commit/abort |
| Transactional producer errors | Fencing, timeouts, invalid state |
| Producer send failure rate | Errors occurring before commit |
| Consumer lag | Backlog of unprocessed input |
| `read_committed` visibility lag | Time until output records become visible downstream |
| Rebalance count | Group membership losses affecting offset transactions |
| `AfterRollbackProcessor` recovery | Retries/recoveries after transaction rollback |
| DLT publish failures | Recovery unable to persist failed records |

Structured logs should include:

~~~text
event=kafka_transaction_commit
service=order-projector
listener_id=ordersProjection
group_id=order-projector
input_topic=orders.created
input_partition=2
last_processed_offset=845
transactional_id_prefix=order-projector-pod-a-
outcome=committed
elapsed_ms=37
~~~

Do not put `transactional.id`, event IDs, or offsets into high-cardinality metric tags if they vary excessively; detailed identifiers belong in logs/traces. Never log secrets or full payloads.

### Alert-worthy signals

- Commit failures rising after a deploy.
- Widespread `ProducerFencedException` during scale-out.
- Abort rates climbing alongside downstream error rates.
- `read_committed` consumer lag rising while open transactions linger.
- Frequent transaction timeouts.
- DLT/recovery not making progress after rollbacks.
- Inconsistencies between DB side effects and Kafka outputs.

## 25. Testing Transaction Commits

To verify semantics, use a real Kafka broker or Testcontainers. A unit test of a method calling `commitTransaction` does not prove the broker wrote commit markers or `read_committed` consumers behave properly.

Scenarios:

| Scenario | Expected outcome |
|---|---|
| Two sends in one transaction then commit | `read_committed` consumer sees both |
| Send succeeds then abort | `read_committed` consumer receives no aborted records |
| `read_uncommitted` consumer | May see uncommitted or aborted records |
| Input → output and offsets share transaction | Outputs and offsets commit together |
| Process dies before commit | Outputs not considered committed; input can be reprocessed |
| Process dies after commit | Outputs visible and input offsets advanced in Kafka |
| New producer uses same `transactional.id` | Old producer is fenced per protocol |
| Transaction timeout | Transaction does not succeed outside policy |
| Listener throws exception | Container rolls back and after-rollback handles |
| Producer send failure | No partial output committed |
| Database commits before Kafka commit fails | Inconsistency detected and inbox/outbox verified |
| Rebalance during processing | Safe offset/group metadata and rollback handling |

### Example verifying read_committed

Create a transactional producer and two consumers on the same test topic with different group IDs:

~~~java
consumerProperties.put(
        ConsumerConfig.ISOLATION_LEVEL_CONFIG,
        "read_committed"
);
~~~

1. Begin transaction.
2. Send records A and B.
3. Wait for send futures to complete.
4. Poll the `read_committed` consumer and verify neither A nor B is received before commit.
5. Commit transaction.
6. Poll again with an adequate timeout and verify both A and B are received.
7. Repeat with another transaction that aborts; verify `read_committed` returns no aborted records.
8. Use a `read_uncommitted` consumer for comparison if needed.

Tests should not rely on fixed `Thread.sleep` delays. Use timeout-bounded polling assertions and isolated consumer groups so committed offsets from prior runs do not interfere.

## 26. Runbook When Transaction Commit Fails

When logs report a transaction commit failure:

1. Identify service, instance, listener container, `transactional.id`/prefix, and transaction manager.
2. Capture the exception class, cause chain, and commit timestamp.
3. Distinguish send errors, add-offsets errors, commit errors, or abort errors.
4. Check broker coordinator health, network, authorization, and topic availability.
5. If `ProducerFencedException`, check whether another producer with the same `transactional.id` is active.
6. Check rolling deploys, scale-out state, and how `transaction-id-prefix` is assigned.
7. Compare `transaction.timeout.ms`, listener processing duration, and `max.poll.interval.ms`.
8. Check consumer group rebalances and offset metadata when `sendOffsetsToTransaction` is used.
9. If commit outcome is uncertain, never blindly replay side effects outside Kafka before verifying/idempotently reconciling.
10. Check whether `read_committed` consumers observed outputs and verify committed input offsets.
11. Inspect `AfterRollbackProcessor`, recovery/DLT, and transactional producer lifecycle.
12. Fix the root cause, roll out carefully, and monitor commit/abort rates and lag.
13. If a database is involved, verify business state consistency and run reconciliation per runbook.
14. Document blast radius, number of replayed records, and preventive measures.

When an instance is fenced, never try to continue committing with the producer that lost ownership. Close the producer, resolve `transactional.id` ownership, and let the framework initialize a new producer per policy.

## 27. Common Implementation Mistakes

**Confusing send with commit.** Send completion does not mean the transaction committed; `read_committed` consumers may not see the records yet.

**Confusing flush with commit.** Flush only waits for producer sends; it does not write transaction commit markers.

**Using `@Transactional` alone and picking the wrong manager.** In apps with multiple transaction managers, explicitly name `KafkaTransactionManager` when a Kafka transaction is needed.

**Swallowing exceptions in listeners.** The container may commit the transaction despite business failure.

**Not including offsets in the transaction.** Committing input offsets separately breaks Kafka-level atomicity between outputs and checkpoints.

**Sharing one `transactional.id` across multiple live producers.** Concurrent instances fence each other.

**Keeping producer transactions open too long.** Risks timeouts, stalls `read_committed` consumers behind the Last Stable Offset, and increases lag.

**Blindly retrying commits on uncertain outcomes.** Can cause unpredictable states or duplicate side effects; rely on Kafka producer protocol and idempotency.

**Assuming Kafka transactions cover databases.** No default distributed atomicity; use inbox/outbox.

**Downstream consumers using `read_uncommitted` while expecting no aborted records.** Configure `read_committed` for that requirement.

**Using `DefaultErrorHandler` as the sole rollback path in transactional listeners.** Understand `AfterRollbackProcessor` and transaction-aware recovery.

**Increasing concurrency without sizing transactional producer resources.** Can exhaust producer caches/suffixes or trigger fencing if namespaces collide.

**Not testing crashes at the commit boundary.** Happy paths alone do not prove recovery and EOS behavior.

## 28. Pre-Production Checklist

**Producer and transaction manager**

- [ ] Transactional producers have non-colliding prefixes/IDs across concurrent instances.
- [ ] Confirmed `KafkaTransactionManager` and `KafkaTemplate` share the right transactional `ProducerFactory`.
- [ ] Producer serializers, ACLs, and broker compatibility are verified.
- [ ] Transaction timeouts fit processing durations.
- [ ] Monitoring covers commit failures, aborts, fencing, and send errors.

**Consumer and listener container**

- [ ] Consumer `enable.auto.commit=false` when the container manages offsets.
- [ ] When Kafka-to-Kafka EOS is required, input offsets are sent in the same transaction as outputs.
- [ ] Downstream consumers requiring committed-only semantics use `isolation.level=read_committed`.
- [ ] Listeners do not swallow exceptions requiring rollback.
- [ ] `AfterRollbackProcessor`/recovery is properly configured.
- [ ] Concurrency, producer cache, rebalances, and `max.poll.interval.ms` are accounted for.

**Business logic**

- [ ] No claim that Kafka transactions cover databases or external APIs.
- [ ] External side effects use idempotency keys if they can be retried.
- [ ] Inbox/outbox or reconciliation is used when cross-system consistency is required.
- [ ] DLT and replay policies exist with stable event IDs.
- [ ] Transaction scope matches throughput and latency requirements.

**Testing and operations**

- [ ] Integration tests cover commit/abort with `read_committed` consumers.
- [ ] Tests cover process crashes before and after commit.
- [ ] Tests cover producer fencing and transaction timeouts.
- [ ] Tests cover listener rollback/recovery and proper offset progression.
- [ ] Runbook exists for uncertain commit outcomes.
- [ ] Dashboards track transaction duration, commit/abort, lag, and DLT.

## 29. Summary of Principles

**Committing a transaction** is the boundary at which Kafka records in a transaction become considered committed and, when using `sendOffsetsToTransaction`, **input consumer offsets** are committed alongside output records. In Spring Kafka, `KafkaTransactionManager`, `KafkaTemplate`, and listener containers manage begin/commit/abort so applications do not have to implement the entire transaction protocol manually.

Sound design rests on core distinctions: send is not commit; flush is not commit; regular offset commit is not sending offsets into a transaction; `read_committed` is not `read_uncommitted`; and Kafka exactly-once is not atomicity with databases or external APIs. Once transactional IDs, producer fencing, timeouts, rollbacks, idempotency, and commit outcome observability are properly managed, systems can run consistent Kafka-to-Kafka processing and recover safely across restarts or rebalances.
