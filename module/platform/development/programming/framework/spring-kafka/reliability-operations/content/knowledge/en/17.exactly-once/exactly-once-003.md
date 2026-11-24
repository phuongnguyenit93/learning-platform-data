# read-process-write exactly once

In Spring Kafka systems, a common flow is **reading records from an input topic, executing business processing, and writing result records to an output topic**. If the application crashes, the broker disconnects, or the consumer group rebalances right between steps, the same input record can be read again. When that happens, the critical question is not just how many times the consumer processes it, but **whether the final result gets duplicated or lost**.

Kafka provides **exactly-once semantics (EOS)** for read-process-write flows where all involved operations reside within Kafka. Spring Kafka supports coordinating producer transactions with consumer group offsets so that publishing outputs and recording consumption progress occur in **the same Kafka transaction**.

The scope must be clearly understood: EOS does not mean the listener method is called only once. The listener may run again after an error. What a Kafka transaction guarantees is that **committed outputs and committed offsets either succeed together or have no effect together** within the Kafka transaction scope, when the system is properly configured. Side effects on databases, emails, HTTP APIs, and other services do not automatically belong to that same transaction.

## 1. The problem: what failure windows exist in read, process, then write?

Suppose an `order-validator` service consumes `orders.created` and produces `orders.validated`.

    orders.created
          |
          v
    Consumer polls record A
          |
          v
    Validate A
          |
          v
    Producer sends result X
          |
          v
    Consumer commits source offset

If you only use a normal producer and commit offsets separately, there are at least two failure modes.

**Output written, offset not yet committed:**

    Poll A -> Process A -> Write X succeeds
                              |
                              v
                        Crash before commit
                              |
                              v
                        Consumer re-reads A
                              |
                              v
                        Write X a second time

The output can be duplicated because the Kafka consumer group does not yet know A was processed.

**Offset committed first, output not yet written:**

    Poll A -> Commit offset A
                    |
                    v
             Crash before write X
                    |
                    v
            Restart reads record after A

This time output X can be lost because the consumer no longer re-reads A according to the committed offset.

If outputs and offsets are committed **atomically in a Kafka transaction**, both failure windows are handled under a unified contract: either both outputs and offsets are committed, or the transaction aborts and the input record still has a redelivery path.

## 2. What does "Exactly once" apply to?

The phrase "exactly once" is easily misunderstood because a system has multiple layers.

| Target | What Kafka EOS guarantees | What Kafka EOS does not guarantee on its own |
|---|---|---|
| Output Kafka records | Outputs from committed transactions are visible to `read_committed` consumers | Does not stop other applications from intentionally publishing a new business event with the same content |
| Consumer group offsets | Offsets are written in the same transaction containing the output | Does not prevent the listener from being invoked again before the transaction commits |
| In-memory processing | Can re-run while aborted Kafka outputs are not treated as committed | Does not guarantee a Java method runs only once |
| Database | Outside Kafka transaction atomicity | Does not roll back/commit automatically with Kafka |
| HTTP/payment/email | Outside Kafka transaction atomicity | Does not prevent duplicate requests, charges, or emails |
| Downstream consumers | Can see only committed transactions if using `read_committed` | `read_uncommitted` may see records from aborted transactions |

EOS for read-process-write flows should be interpreted at the system boundary: **Kafka output data and Kafka read progress have an atomic relationship**. When processing is purely a transformation from an input event to an output event, this is a very strong foundation to avoid losing or duplicating outputs due to post-crash retries.

A record may be attempted twice by the listener, yet if the first attempt belonged to an aborted transaction, downstream `read_committed` consumers do not accept that attempt's output as a valid result.

## 3. Three operations in a single Kafka transaction

A successful read-process-write transaction comprises three logical operations:

1. Consumer reads input records via `poll`.
2. Transactional producer sends output records to Kafka.
3. Consumer group offsets are sent **into the transaction itself** before committing.

Diagram:

    Transaction T1 begins
          |
          v
    Input: orders.created-0@120
          |
          v
    Process -> OrderValidated
          |
          v
    Produce: orders.validated
          |
          v
    Send source offset=121 to transaction
          |
          v
    commitTransaction()
          |
          +---- Output X committed
          |
          +---- Source offset 121 committed

If the transaction aborts:

    abortTransaction()
          |
          +---- Output X in T1 marked aborted
          |
          +---- Source offset 121 not committed by T1
          |
          +---- Input offset 120 can be reprocessed

**Offset 121** is the next position after the record at offset 120. Committing an offset does not record "record 120", it records the position where consumption should resume.

Producer transactions in Kafka coordinate multiple partitions/topics and offsets in the same transaction. Output does not need to live on the same partition as input; however, ordering, partition allocation, and throughput still need dedicated design.

## 4. Why is an idempotent producer not enough?

Kafka producers support idempotence to reduce duplicate risks when a producer retries the same batch due to uncertain network responses.

For instance, a producer sends a batch to the broker, but the response is lost. If the producer retries, an idempotent producer uses producer identity/sequence numbers to avoid writing the batch twice within its supported scope.

However, **an idempotent producer does not connect outputs with consumer offsets**.

    Read A
    Send X via idempotent producer
    Crash before offset commit
    Restart -> Read A again
    Send X in the new processing attempt

Two processing runs can create two distinct business send calls. Producer idempotence has no way of knowing they originated from the same input A. A transaction holding both output and offset is needed to close the gap between write and commit.

Kafka transactions build on producer idempotence, transaction coordination, and fencing; they provide a broader consistency guarantee than standalone idempotent sends.

## 5. Prerequisites for exactly-once read-process-write

Key requirements:

- Kafka brokers support transactions and have transaction state log configurations suited to the environment.
- Output producer is initialized as a **transactional producer** with a valid `transactional.id`.
- Consumer auto-commit of offsets is disabled so offsets are sent into the Kafka transaction.
- Listener container is configured with a Kafka transaction manager or equivalent transactional mechanism.
- Output is sent using a `KafkaTemplate` participating in the container-managed transaction.
- Downstream consumers need **isolation.level=read_committed** if they must not see outputs from aborted transactions.
- All used topics/partitions can accept records and satisfy access permissions.
- Transaction IDs are allocated distinctly enough across concurrently active instances.
- Transaction duration, processing time, retry/backoff, and poll intervals are mutually compatible.

In a single-broker development environment, replication settings for the transaction state log may need adjustment to initialize transactions. Production needs replication/min ISR settings suited for fault tolerance; do not copy single-broker settings to a real cluster.

If part of a data write flow uses a producer outside the transaction, that part cannot be assumed atomic merely because the listener container is marked transactional.

## 6. Spring Boot configuration to enable Kafka transactions

Foundational configuration example with modern Spring Boot/Spring Kafka:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    consumer:
      group-id: order-validator
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        isolation.level: read_committed
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
        spring.json.use.type.headers: false

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      transaction-id-prefix: order-validator-tx-
      properties:
        acks: all
        enable.idempotence: true

    listener:
      ack-mode: record
~~~

Meaning of the core properties:

| Property | Role |
|---|---|
| `producer.transaction-id-prefix` | Activates Spring-managed transactional producers |
| `consumer.enable-auto-commit=false` | Prevents automatic offset commits outside the transaction |
| `consumer.properties.isolation.level=read_committed` | Skips outputs from aborted and uncommitted transactions |
| `producer.properties.acks=all` | Requires replica acknowledgments per ISR configuration |
| `producer.properties.enable.idempotence=true` | Idempotent producer supporting safe retries |
| `listener.ack-mode` | Controls how the listener container records progress before sending offsets into the transaction |

With suitable Spring Boot auto-configuration, setting `transaction-id-prefix` can let Boot create a `KafkaTransactionManager` and attach it to the default listener container factory. **Do not assume every custom factory is configured like the default factory.** If the application builds its own `ConcurrentKafkaListenerContainerFactory`, verify that the transaction manager is actually attached to that container.

In production, do not give every pod the same `transaction-id-prefix` if deriving `transactional.id` from the prefix risks collisions across instances. The prefix should carry instance identity or be managed so `transactional.id` values are unique across active producers.

## 7. Example @KafkaListener reading and writing in a transaction

Suppose the system has two Java record events:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        long amount) {
}

public record OrderValidated(
        String eventId,
        String orderId,
        String validationStatus) {
}
~~~

Processing service:

~~~java
@Service
public class OrderValidationListener {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public OrderValidationListener(
            KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        id = "orderValidationListener",
        topics = "orders.created",
        groupId = "order-validator"
    )
    public void onOrder(
            ConsumerRecord<String, OrderCreated> record) {

        OrderCreated event = record.value();

        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId missing");
        }

        OrderValidated output = new OrderValidated(
            event.eventId(),
            event.orderId(),
            "VALID"
        );

        kafkaTemplate.send(
            "orders.validated",
            event.orderId(),
            output
        );
    }
}
~~~

This snippet assumes `KafkaTemplate` and the `@KafkaListener` container both participate in the Kafka transaction, configured with a transaction-capable `ProducerFactory` and `KafkaTransactionManager`. Without that configuration, the code looks like consume-process-produce but **has no atomic offset+output guarantee**.

When the listener succeeds, the container coordinates sending processed offsets into the transaction and then commits. When the listener throws an exception, the container aborts the transaction; uncommitted output has no effect for `read_committed` downstream consumers and input can be redelivered.

In Spring Kafka, transaction boundaries often align with a single container poll batch, even for record listeners, depending on version and configuration. Do not infer that every listener method invocation automatically creates an independent transaction.

## 8. Is @Transactional needed on the listener?

**Do not add `@Transactional` merely to "enable EOS"** without knowing which transaction manager will be selected.

In the container-managed Kafka transaction model:

1. Listener container opens the Kafka transaction.
2. Container invokes the listener.
3. `KafkaTemplate` participates in the open transaction.
4. Container sends offsets into the transaction and commits/aborts.

The listener method may not need `@Transactional`. If you use `@Transactional` without specifying a manager in an application that has both `DataSourceTransactionManager`/`JpaTransactionManager` and `KafkaTransactionManager`, the annotation may pick an unexpected transaction manager.

A misleading example:

~~~java
@Transactional
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    orderRepository.save(...);
    kafkaTemplate.send("orders.validated", ...);
}
~~~

If the annotation picks the JPA transaction manager, it does not automatically turn the database and Kafka into a single atomic distributed transaction. The Kafka container may be opening an independent transaction, or have no Kafka transaction at all depending on configuration.

Determine **who starts the transaction**, **which transaction manager is used**, and **how offsets are sent into the transaction**. Do not rely solely on the presence of an annotation.

## 9. Role of KafkaTransactionManager

`KafkaTransactionManager` is the transaction manager provided by Spring Kafka for Kafka producer transactions. It works with a `ProducerFactory` that supports transactional producers.

Explicit bean example:

~~~java
@Bean
KafkaTransactionManager<String, Object> kafkaTransactionManager(
        ProducerFactory<String, Object> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
~~~

When customizing a listener factory, attach the manager to `ContainerProperties` using the API of your specific Spring Kafka version.

Illustrative example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
transactionalListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        KafkaTransactionManager<String, Object> transactionManager) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);

    // Spring Kafka 3.x exposes transaction manager configuration APIs
    // on ContainerProperties; use the exact method name for your version.
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(transactionManager);

    return factory;
}
~~~

Setter names can vary across Spring Kafka lines (older releases used `setTransactionManager`). The example above illustrates wiring the manager, not a substitute for checking your exact dependency version.

If the application has multiple `KafkaTemplate` beans or multiple `ProducerFactory` beans, verify that the template used to send outputs inside the listener is backed by the right producer factory to join the transaction. A `KafkaTemplate` built from an unrelated producer factory can send outside the transaction if misconfigured.

## 10. How are offsets sent into a transaction?

The Kafka Java client exposes `sendOffsetsToTransaction()` on `Producer`. In modern Kafka versions, the API accepts an offset map and `ConsumerGroupMetadata`.

Descriptive example at the Kafka client level:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets =
        Map.of(
            new TopicPartition(record.topic(), record.partition()),
            new OffsetAndMetadata(record.offset() + 1)
        );

producer.sendOffsetsToTransaction(
    offsets,
    consumer.groupMetadata()
);
~~~

This snippet is not a complete listener. If using `KafkaConsumer` and `KafkaProducer` manually, the application must also manage `beginTransaction()`, `send()`, `commitTransaction()`, `abortTransaction()`, `poll()`, error handling, and seek/redelivery. `KafkaConsumer` is not thread-safe; never call `consumer.groupMetadata()` or commit operations from arbitrary threads.

In Spring Kafka's container-managed transaction model, **the container automatically passes processed offsets into the transaction**. Application code should not call `sendOffsetsToTransaction()` again for the same flow without a clear reason and design.

The purpose of consumer group metadata is to let the broker associate offset commits with group membership. In EOS v2, this metadata supports fencing and correct handling when assignments/rebalances change.

## 11. How important is read_committed?

A Kafka transaction can write data to the log and then abort. Records from an aborted transaction remain physically in the log until retention expires, but are not considered committed output.

Consumers have two isolation levels:

| Isolation level | What does the consumer see? |
|---|---|
| `read_uncommitted` | Can see records from committed, uncommitted, or aborted transactions |
| `read_committed` | Receives only committed records and valid non-transactional records; discards records from aborted transactions |

Example:

    Transaction T1:
      write X1
      write X2
      abort

    Transaction T2:
      write Y1
      commit

    read_uncommitted:
      may observe X1, X2, Y1

    read_committed:
      observes only Y1 (and other non-transactional records)

Downstream systems wanting to leverage EOS must use `read_committed` when reading transactional outputs. If an analytics system still uses `read_uncommitted`, it may observe data that business logic rolled back and compute wrong totals or sync invalid state.

An operational consequence: a `read_committed` consumer only reads up to the **last stable offset (LSO)**, bounded by the earliest open transaction. A long-running or stuck transaction can increase downstream lag/latency even while producers send many other records. Monitor transaction duration and transaction timeouts.

## 12. Rollback and redelivery after failures

In a transactional listener, when a method throws an exception, the container must abort the transaction and reposition the consumer so unsuccessfully processed records can be redelivered.

Typical sequence:

    poll input A
       |
       v
    Begin T1
       |
       v
    Listener processes A
       |
       v
    KafkaTemplate.send X
       |
       v
    Exception before commit
       |
       v
    Abort T1
       |
       v
    AfterRollbackProcessor
       |
       v
    Seek/reposition record for reprocessing
       |
       v
    Begin T2 -> Redeliver A

In Spring Kafka, `DefaultAfterRollbackProcessor` is commonly used to coordinate redelivery/backoff/recovery after a transaction rollback. It differs from `DefaultErrorHandler` in non-transactional containers.

When a rollback happens, Kafka outputs belonging to T1 are not treated as committed by `read_committed` downstream consumers, and input offsets sent into T1 are not committed either. Redelivery may run the listener again, but the new transaction produces committed output only when the subsequent attempt succeeds.

## 13. Do not swallow exceptions in the listener

A very common way to break EOS is catching exceptions and only logging them:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    try {
        orderService.validate(event);
        kafkaTemplate.send("orders.validated", event);
    }
    catch (Exception exception) {
        log.error("Validation failed", exception);
        // Not thrown -> container may consider the listener done.
    }
}
~~~

In this example, the container does not know business logic failed. It may go ahead and send the offset into the Kafka transaction and commit. The input will not be redelivered as expected, even though the output may not exist.

If an error must trigger a rollback, let the exception propagate:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    try {
        orderService.validate(event);
        kafkaTemplate.send("orders.validated", event);
    }
    catch (Exception exception) {
        log.error("Validation failed", exception);
        throw exception;
    }
}
~~~

If you want to handle a failed record and move on, deliberately design a recoverer/DLT and a policy for committing the recovered offset. Do not replace recovery by swallowing exceptions to "avoid retries."

## 14. Transaction boundary: single record or poll batch?

With a record listener, the method may be called multiple times in a single poll loop. That does not mean every record always has its own separate transaction. In Spring Kafka, transactional containers often manage transactions at the scope of records received in a poll, depending on listener type and configuration.

Example:

    poll() -> A, B, C

    Transaction T1 begins
      listener(A) -> send XA
      listener(B) -> send XB
      listener(C) -> exception
    T1 aborts

If A, B, and C belong to the same transaction T1, outputs XA/XB also abort. Uncommitted inputs processed in that transaction can be redelivered safely by offset.

If configuration uses a different transaction boundary, the replay scope also differs. Thus, when analyzing duplicates and throughput, check the actual transaction boundary instead of assuming one call equals one transaction.

Batch listeners must also consider how to pinpoint failing records in a batch, since a generic exception can force the entire batch to reprocess. If batch processing has side effects outside Kafka, idempotency is mandatory to avoid repeating actions.

## 15. Retry, backoff, and poison pills in EOS flows

A record that fails repeatedly can block a partition and cause repeated transaction aborts. Causes can include:

- Transiently unavailable HTTP dependency.
- Database deadlock or timeout.
- Malformed event schema or missing required fields.
- `NullPointerException` bug or logic unable to handle a new state.
- Insufficient permissions to produce to the output topic.
- Fenced or timed-out transactional producer.

Do not retry indefinitely with a short fixed wait. You can use `DefaultAfterRollbackProcessor` with `FixedBackOff` or `ExponentialBackOff` and a recoverer.

Illustrative example:

~~~java
DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
            (record, exception) -> {
                log.error(
                    "Could not process record {}-{}@{}",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    exception
                );
            },
            new FixedBackOff(1_000L, 3L)
        );
~~~

The snippet above **only logs**, so it is not a complete production recovery policy. After retries are exhausted, allowing records to be skipped without durable storage can cause business data loss. Use a DLT or a reliable recovery mechanism.

Choose backoff intervals based on dependency recovery times, SLA limits, and `max.poll.interval.ms`. Permanent data errors generally cannot self-heal via retries.

## 16. DLT and "exactly once" during recovery

A record may be processed multiple times and always fail. Once retries are exhausted, systems typically route it to a DLT so the partition is not blocked indefinitely.

Goal:

    T1:
      Read bad record A
      Listener fails
      Abort T1

    Recovery transaction T2:
      Publish A -> orders.created.DLT
      Send input offset past A to transaction
      Commit T2

If the DLT record and the source offset commit together in a new transaction, they have atomicity similar to read-process-write. If the recovery transaction aborts, the source offset is not recorded, so the record can still be reprocessed.

In Spring Kafka, `DefaultAfterRollbackProcessor` supports options such as `commitRecovered` and `KafkaOperations` in certain versions. Configuration must wire the right transactional `KafkaTemplate`, processor, and listener transaction manager.

Illustrative example:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltKafkaTemplate);

DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
            recoverer,
            new FixedBackOff(1_000L, 3L)
        );

// Enable committing recovered offsets per supported API.
processor.setCommitRecovered(true);

// Also provide appropriate KafkaOperations and configure
// the processor/container for recovery transactions
// according to the exact Spring Kafka version in use.
~~~

Do not infer that calling `setCommitRecovered(true)` alone suffices to make DLT sends and source offset commits atomic. Verify transaction participation and the DLT send failure path.

If the broker rejects the DLT record or the producer serializer fails on the corrupted payload, the recoverer must surface the error instead of letting the container commit the source offset as successfully recovered.

## 17. Database side effects are outside Kafka transactions

Suppose a listener both writes to PostgreSQL and publishes a Kafka output:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    orderRepository.save(toEntity(event));
    kafkaTemplate.send("orders.validated", validate(event));
}
~~~

If the database commits successfully but the Kafka transaction aborts, the input will be redelivered. Reprocessing may insert the same order again or increment a counter twice.

Kafka EOS does not create a distributed transaction across Kafka and a database. Even when using `@Transactional` and ordering commits, failure windows remain between the two resource managers.

Solutions:

**Idempotent update:** write records using a unique constraint on `eventId`, or a conditional upsert.

**Transactional Inbox:** within a single database transaction, both mark `eventId` as processed and update business data. When Kafka redelivers, the consumer sees the existing `eventId` and does not repeat the side effect.

**Transactional Outbox:** store the output event alongside business changes in the database, and have a separate publisher relay outbox events to Kafka. Design duplicate handling/idempotency for both the publisher and downstream consumers.

**Saga/compensation:** if a workflow spans multiple non-Kafka services, coordinate state and compensating steps rather than expecting a system-wide rollback.

If the business side effect is a payment or an email, you must use an idempotency key or durable delivery state tracking. Non-duplicate Kafka outputs do not prove a customer was not charged or emailed twice.

## 18. Transactional ID, producer fencing, and multi-instance scaling

Each transactional producer is identified by Kafka via `transactional.id`. The broker uses producer ID/epoch and the transaction coordinator to prevent an old producer from continuing to commit after a new producer with the same `transactional.id` takes over.

**Producer fencing** plays a critical role when an old instance hangs, experiences a network partition, or restarts. The old producer may receive errors such as `ProducerFencedException` and must stop using that producer per framework mechanisms.

In multi-pod environments:

    Pod A: transaction-id-prefix = order-validator-A-
    Pod B: transaction-id-prefix = order-validator-B-
    Pod C: transaction-id-prefix = order-validator-C-

Each pod needs a transactional ID namespace that avoids colliding with other active pods. Spring Kafka generates `transactional.id` from the prefix and caches producers, yet prefix identity must still be managed when scaling.

Do not assign the same fixed `transactional.id` to all pods. If two active producers share an ID, they can fence each other and cause transactions to continuously abort.

During rolling deployments, you can tie identity to pod/instance and plan the lifecycle so an old producer is not still alive while a new instance uses the same `transactional.id`. Also stop containers gracefully enough for transactions to complete or abort cleanly.

## 19. EOS v2 in Spring Kafka

In modern Spring Kafka releases, **EOSMode.V2** is the mechanism used for Kafka exactly-once aligned with newer Kafka client/broker capabilities.

An important feature is that the producer sends offsets into the transaction together with consumer group metadata, supporting fencing and correctness when consumer group assignments change. This mechanism improves producer/consumer group coordination compared to historical modes.

Do not copy legacy EOS mode configurations from a blog using a different Spring Kafka version. Many enums, properties, and transaction APIs have evolved as Spring Kafka progressed. Verify the version in use and the contract of `KafkaTransactionManager`, listener container, and `ProducerFactory`.

Even with EOS v2, requirements for `read_committed` downstream, a transaction-aware `KafkaTemplate`, offsets sent inside the transaction, and idempotency for external systems remain unchanged.

## 20. Transaction timeout and max.poll.interval.ms

Timeouts affecting the availability of EOS flows:

| Parameter | Meaning | Risk if misconfigured |
|---|---|---|
| `transaction.timeout.ms` | Maximum lifetime allowed for a Kafka transaction | Long transactions abort due to timeout |
| `max.poll.interval.ms` | Maximum time between polls | Consumer may lose assignment if processing takes too long |
| `request.timeout.ms` | Wait time for a request response | Timeout errors / truncated communication |
| `delivery.timeout.ms` | Producer delivery time bound | Producer send errors cause transaction aborts |
| producer `max.in.flight.requests.per.connection` | Unacknowledged in-flight requests | Must be compatible with idempotence and throughput needs |
| shutdown timeout | Wait time for listener/container shutdown | Pod killed mid-transaction if too short |

If a single poll returns many records and the listener processes slowly, the transaction can stretch out. While the transaction stays open, `read_committed` downstream consumers wait on LSO and effective throughput drops.

Do not simply raise timeouts to hide slow processing. Measure per-record duration, records per poll, dependency latency, commit latency, and work distribution across partitions.

## 21. Record ordering, concurrency, and partitions

Kafka guarantees ordering per partition, not across an entire topic. In a consumer group, each partition is assigned to at most one consumer at a time, and Spring Kafka concurrency creates multiple parallel consumers to increase throughput.

Example:

    orders.created: 8 partitions
    deployment: 2 pods
    concurrency per pod: 4
    => up to 8 consumers can receive partitions

Each child consumer can have a transactional producer managed according to Spring Kafka's lifecycle and cache. Ensure the `transaction-id` prefix does not conflict across instances.

Notes:

- Raising concurrency above the partition count creates no useful parallelism.
- Send outputs with stable keys if downstream needs ordering per aggregate.
- One transaction can write to multiple output partitions, but Kafka does not impose global ordering across them.
- If a listener hands work off to an executor and returns immediately, the container may commit offsets before the task finishes; EOS for outputs depending on that task can break.
- Never use `KafkaConsumer` concurrently from multiple threads; the container manages the thread owning the consumer.

With async processing, completion must be integrated into the transaction and offset boundary. Simply calling `executor.submit()` does not make the background task part of the Kafka transaction.

## 22. Kafka Streams vs. Spring Kafka listeners

Kafka Streams supports EOS for read-process-write topologies via transactions and offset/state management. With Kafka Streams, configuring `processing.guarantee` properly lets the runtime coordinate processing state, changelogs, and Kafka outputs within its supported scope.

A Spring Kafka listener is a lower-level model: the application controls the listener and can configure `KafkaTransactionManager`, `KafkaTemplate`, `AfterRollbackProcessor`, and custom business logic.

| Criterion | Spring Kafka listener | Kafka Streams |
|---|---|---|
| Model | Listener receives records/batches and runs application code | Stream processing topology |
| EOS configuration | Container transaction + producer/offset | Streams processing guarantee |
| State | Managed by the app or backed by a DB | Streams state stores/changelogs |
| Retry/recovery | Error handler, after-rollback, DLT | Streams error/processing mechanisms |
| Side effects outside Kafka | Requires separate idempotency/transaction model | Also lacks distributed transactions with DB/API |

Choose Spring Kafka if the application mainly executes business logic integrated with services/repositories. Choose Kafka Streams if the core need is transforming, joining, aggregating, or stateful stream processing by topology. Do not treat Streams as an automatic solution for exactly-once side effects across external systems.

## 23. Observing correctness in production

A dashboard showing only consumer lag and producer throughput is insufficient to prove EOS. Observe both transactions and business outcomes.

**Producer transaction**

- Number of transactions begun, committed, and aborted.
- Transaction duration and timeout rate.
- Producer fencing, coordinator, or commit errors.
- Producer send errors and delivery timeouts.

**Consumer**

- Committed offsets per group/partition.
- Consumer lag and rebalance counts.
- Redelivery counts for a topic-partition-offset.
- Time from poll to commit/abort.
- After-rollback and DLT recovery errors.

**Output**

- Committed outputs received by `read_committed` downstream.
- Duplicate output `eventId` instances detected.
- End-to-end latency from input event to visible output.
- Records stuck in open transactions or DLT.

**Business**

- Number of `eventId`s processed successfully.
- Number of duplicates skipped by the idempotency layer.
- Number of non-Kafka side effects re-executed.
- Discrepancy between valid inputs and expected business outputs.

Logs should include `eventId`, `groupId`, `topic`, `partition`, `offset`, transaction/recovery stage, and exception class. Avoid logging sensitive payloads or full stack traces on every retry.

## 24. Testing read-process-write exactly once

Unit-testing the listener is insufficient to verify EOS, because atomicity between producer output and consumer offset depends on the broker transaction coordinator. Write integration tests using a client-compatible broker (Embedded Kafka or Testcontainers).

### 24.1. Happy path

1. Create input and output topics.
2. Enable `transaction-id-prefix`, disable auto-commit, configure a transactional listener.
3. Send input event A with a fixed `eventId`.
4. Wait for output X to be observed by a `read_committed` consumer.
5. Verify the consumer group committed the offset past A.
6. Restart the consumer and verify no extra X is published from the same input A.

### 24.2. Crash after send but before commit

1. Listener sends output X in Kafka transaction T1.
2. Intentionally throw an exception before container commit.
3. Verify transaction T1 aborts.
4. Use `read_committed` downstream to confirm T1's X is not visible.
5. Let the retry process A successfully in T2.
6. Verify only the committed output from T2 is visible.
7. Verify the input offset advances only after T2 commits.

### 24.3. Failure during transaction commit

1. Simulate broker/coordinator unavailability during commit.
2. Observe transaction exceptions/aborts within the test environment's capabilities.
3. Do not assume commit definitely failed from a client timeout alone.
4. Restart and verify the flow can recover without creating duplicate business results within EOS scope.
5. If external side effects exist, verify idempotency.

### 24.4. read_uncommitted vs. read_committed

1. Intentionally create a transaction with output and abort it.
2. Use two downstream consumers on the same topic with different isolation levels.
3. `read_uncommitted` can read records from the aborted transaction.
4. `read_committed` does not return aborted output records as valid data.
5. Inspect transaction logs/metrics to cross-check.

### 24.5. Database side effects and rollback

1. Write a database row for `eventId` A.
2. After database commit, cause the Kafka transaction to abort.
3. Allow input A to be redelivered.
4. Verify a unique constraint or Inbox prevents duplicate writes.
5. Verify the Kafka output ultimately commits exactly once per scenario.

### 24.6. Poison records and DLT

1. Send an event that permanently violates validation.
2. Verify finite backoff/retries after rollback.
3. Verify DLT publication and source offset commit if a recovery transaction is configured.
4. Make the DLT producer fail and verify the input remains eligible for redelivery.
5. Re-drive with the original `eventId` and verify no duplicate side effects occur.

### 24.7. Rebalance mid-transaction

1. Run multiple consumers in the same group.
2. Keep one listener processing, then stop a consumer or alter membership.
3. Verify the transaction cannot commit under the wrong owner when fencing applies.
4. New consumer reads safely from the committed offset.
5. Verify no Kafka output is lost and no non-Kafka side effect violates the idempotency policy.

Tests must reconcile **committed records**, **actual offsets**, **transaction outcomes**, and **business side effects**, rather than only counting listener method invocations.

## 25. Common configuration mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Enabling only `enable.idempotence` | Offsets are not atomic with outputs | Use Kafka transactions and send offsets with the transaction |
| Forgetting `transaction-id-prefix` | Producer may not be transactional | Configure a transactional `ProducerFactory` |
| Enabling consumer auto-commit | Offsets can advance ahead of outputs | Disable auto-commit so the container manages them |
| Downstream using `read_uncommitted` | Reads outputs of aborted transactions | Use `read_committed` |
| `@Transactional` picks JPA manager | Confuses database transaction with Kafka transaction | Check transaction manager and container wiring |
| `KafkaTemplate` does not join container transaction | Outputs sent outside transaction | Use the right template/factory |
| Listener catches exception and returns normally | Container may commit offset despite failed processing | Rethrow or recover per policy |
| Duplicate transactional IDs across pods | Continuous producer fencing | Use unique prefixes/identities |
| Transaction timeout too short | Timeouts cause aborts and heavy redelivery | Measure processing and set an appropriate timeout |
| Async task runs after listener returns | Offset commits before side effect finishes | Coordinate completion with the transaction |
| Only logging and skipping poison records | Business data can be lost | Use DLT/durable recovery |
| Treating DB/API as part of Kafka EOS | Duplicate side effects on rollback | Use Inbox, Outbox, idempotency keys |
| Testing only the happy path | Misses crash/rebalance windows | Test abort, fencing, redelivery, and DLT |

## 26. Procedure for rolling out EOS to production

A controlled approach:

1. List input topics, output topics, consumer groups, `eventId`, and non-Kafka side effects.
2. Define the exact boundary requiring atomicity: Kafka output + input offsets.
3. Configure a transaction-capable producer and a unique `transaction-id` prefix per instance.
4. Disable consumer auto-commit; configure the listener container transaction manager.
5. Use the same `KafkaTemplate`/`ProducerFactory` participating in the transaction when sending outputs.
6. Set `read_committed` on downstream consumers that must skip aborted outputs.
7. Configure exception propagation, after-rollback, `BackOff`, and DLT recovery.
8. Design idempotency/Inbox/Outbox for database changes or external APIs.
9. Set timeouts and graceful shutdown aligned with processing durations.
10. Test against a test broker: happy path, abort, redelivery, restart, DLT, rebalance.
11. Roll out incrementally and measure transaction abort rate, lag, visible output, and duplicates.
12. Maintain runbooks for fencing, commit errors, poison records, and recovery failures.

Do not convert an entire consumer group to transactional mode just to chase an "exactly once" label if the application actually only writes to a database. In that case, an Inbox model with idempotent updates can be a more important guarantee than a Kafka producer transaction. Choose mechanisms matching your business boundaries.

## 27. Conclusion and key takeaways

- **Exactly-once read-process-write** on Kafka means Kafka outputs and consumer offsets are coordinated in a single transaction.
- Producer idempotence is useful, yet does not replace transactions with offsets.
- Listeners may execute multiple times after crashes/aborts; this does not contradict EOS of committed outputs.
- Downstream requires `read_committed` to avoid seeing outputs of aborted transactions.
- Do not swallow exceptions if container rollback is needed.
- `DefaultAfterRollbackProcessor` and recovery policies govern the redelivery path on errors.
- DLT publishing and recovered offset commits must follow a durable policy; avoid silent skipping.
- `transactional.id`/prefixes must be managed to prevent fencing across instances.
- Transactions do not automatically protect databases, emails, HTTP calls, or payments.
- For external side effects, use Inbox, Outbox, unique constraints, or idempotency keys.
- Do not assume `@Transactional` automatically turns two resource managers into one distributed transaction.
- Testing must observe brokers, offsets, isolation levels, and failure windows, not just listener invocation counts.

When properly designed, Spring Kafka enables applications to read input events, process them, and publish results with an atomic relationship between **committed outputs** and **committed input offsets**. This is the foundation of Kafka-to-Kafka EOS: the system can retry or redeliver after failures without publishing aborted outputs multiple times. For business operations extending beyond Kafka, idempotency and appropriate consistency patterns must still be added to achieve end-to-end reliability.
