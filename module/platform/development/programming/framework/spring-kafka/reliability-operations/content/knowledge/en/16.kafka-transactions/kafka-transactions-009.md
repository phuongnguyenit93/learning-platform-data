# Listener Container Transactions

In Spring Kafka, a **listener container transaction** is the mechanism by which a listener container manages a Kafka transaction around record consumption. In the **consume–process–produce** model, an application reads from one Kafka topic, processes the data, and writes to another topic; the container can place **output records** and **processed consumer offsets** into the same Kafka transaction. When the transaction commits, both outputs and processing progress take effect. If the transaction aborts, uncommitted outputs stay invisible to `read_committed` consumers and input offsets are not confirmed by that transaction.

This forms the foundation for **Kafka-to-Kafka pipeline exactly-once semantics**, though it does not mean a Java listener runs strictly once and **does not** automatically provide exactly-once for databases, HTTP APIs, payments, or emails. When transactions roll back or processes crash, listeners can be re-invoked; side effects outside Kafka must have idempotency mechanisms.

## 1. Lifecycle of a Container-Initiated Kafka Transaction

~~~text
Kafka consumer poll()
        |
        v
Container opens Kafka transaction
        |
        v
@KafkaListener receives record
        |
        +--- KafkaTemplate sends output records in transaction
        |
        +--- Processing succeeded?
                  |
             +----+----+
             |         |
            Yes        No
             |         |
             v         v
Container adds       Abort Kafka
offset to Kafka      transaction
transaction             |
             |          v
             v       After-rollback
Commit Kafka tx      retry/recovery
             |
             v
Output + offset
committed together
~~~

The container starts a transaction before calling the listener, then coordinates enlisting the corresponding offset in the transaction and committing when the listener completes normally. If the listener throws an exception, the transaction rolls back and the record can be reprocessed via the rollback processor mechanism.

Do not manually call `consumer.commitSync()` to "commit offsets faster" inside a transactional listener. Offsets must be coordinated **inside** the container-managed Kafka transaction.

## 2. What Is the Scope of Exactly-Once?

Suppose a consumer receives `OrderApproved` from `orders.approved` and sends `ShipmentRequested` to `shipments.requested`.

Without a transaction spanning outputs and offsets, two issues can occur:

1. Output is sent yet the process stops before committing the offset: after restart, the input is redelivered and emits another output.
2. Input offset is committed yet sending the output fails: the input event is skipped without producing output.

Kafka transactions combine outputs and input offsets:

| Outcome | Kafka output | Input offset |
|---|---|---|
| Transaction commits | Visible to `read_committed` consumers | Offset committed within the transaction |
| Transaction aborts | Transaction output invisible to `read_committed` | Not committed by that transaction |
| Transaction still open | Output not yet ready for `read_committed` | No commit outcome yet |

A record may be **executed multiple times by the listener** after rollbacks. Committed Kafka outcomes still conform to transaction semantics. Do not infer from the phrase "exactly-once" that every side effect executes strictly once.

## 3. Components of a Listener Transaction

| Component | Role |
|---|---|
| `ConcurrentMessageListenerContainer` | Polls records, invokes listener, manages transactions and offsets |
| `ConsumerFactory` | Creates input Kafka consumers |
| `ProducerFactory` | Creates transactional Kafka producers |
| `KafkaTransactionManager` | Coordinates transactions through the producer factory |
| `KafkaTemplate` | Publishes Kafka records and joins the active transaction when using the matching producer factory |
| `DefaultAfterRollbackProcessor` | Coordinates record handling after rollback |
| `DeadLetterPublishingRecoverer` | Can write failed records to a Dead Letter Topic (DLT) |
| `read_committed` consumer | Sees only committed transactional records, skipping aborted ones |

Listener containers created from `@KafkaListener` are normally managed through `KafkaListenerEndpointRegistry`. For transactions to work, ensure the container truly has a Kafka transaction manager attached and `KafkaTemplate` uses a matching transactional producer factory.

In a listener whose Kafka transaction is already started by the container, you typically **do not need** to add `@Transactional` merely to open a transaction for Kafka outputs. `@Transactional` may still be used to open a **database transaction**, but that is a separate resource.

## 4. Spring Boot Configuration

Example configuration for transactional producer and record listener:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example:9092,kafka-2.example:9092
    producer:
      transaction-id-prefix: order-transform-instance-01-
      acks: all
    consumer:
      group-id: order-transformer
      enable-auto-commit: false
      isolation-level: read_committed
    listener:
      ack-mode: record
~~~

Explanation:

- `transaction-id-prefix` enables the producer factory to create transactional producers. Prefixes must be **unique across concurrently running instances** that risk generating colliding transactional IDs. Across multiple pods, inject distinct prefixes via your configuration system.
- `acks: all` aligns with durability requirements for transactional publishing.
- `enable-auto-commit: false` prevents the Kafka client from auto-committing offsets outside the container. Spring Kafka containers also manage auto-commit actively; declaring it explicitly clarifies intent.
- `isolation-level: read_committed` prevents consumers from reading aborted transactions. This is particularly critical for **consumers of output topics**.
- `ack-mode: record` illustrates record-level progress tracking; actual offsets are enlisted by the container into the transaction per listener configuration.

With Spring Boot auto-configuration, declaring a transactional producer factory may cause a Kafka transaction manager to be created and applied automatically. If you define a custom `ConcurrentKafkaListenerContainerFactory`, verify the wiring; **never assume every listener is transactional just because YAML specifies a prefix**.

Example prefixes for three pods:

~~~text
pod-a -> order-transform-a-
pod-b -> order-transform-b-
pod-c -> order-transform-c-
~~~

Do not share a single prefix across all running replicas. A new producer using the same `transactional.id` can fence the older producer.

## 5. Configuring the Container Factory in Java

When defining custom factories, you can attach `KafkaTransactionManager` to the container:

~~~java
@Configuration
public class TransactionalListenerConfiguration {

    @Bean
    KafkaTransactionManager<String, ShipmentRequested> shipmentTransactionManager(
            ProducerFactory<String, ShipmentRequested> producerFactory) {

        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderApproved>
    orderTransactionalListenerFactory(
            ConsumerFactory<String, OrderApproved> consumerFactory,
            KafkaTransactionManager<String, ShipmentRequested> transactionManager) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderApproved>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
               .setKafkaAwareTransactionManager(transactionManager);
        factory.getContainerProperties()
               .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

This example uses the `setKafkaAwareTransactionManager` API available in supporting Spring Kafka versions; older versions use a different method to set the transaction manager. If Boot already creates a transaction manager, inject/reuse that bean rather than creating a second manager without controlling producer factories.

The input type is `OrderApproved`, while output can be `ShipmentRequested`: they do not have to be the same Java type. What matters is that the manager's producer factory is the **exact same producer factory** used by `KafkaTemplate` to publish outputs meant to be enclosed in the transaction.

Corresponding listener:

~~~java
@Component
public class OrderListener {

    private final KafkaTemplate<String, ShipmentRequested> kafkaTemplate;

    public OrderListener(
            KafkaTemplate<String, ShipmentRequested> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        id = "order-transactional-listener",
        topics = "orders.approved",
        groupId = "order-transformer",
        containerFactory = "orderTransactionalListenerFactory")
    public void onOrder(OrderApproved event) {

        ShipmentRequested shipment = new ShipmentRequested(
            event.orderId(),
            event.customerId(),
            event.approvedAt()
        );

        kafkaTemplate.send(
            "shipments.requested",
            event.orderId(),
            shipment
        );
    }
}
~~~

The listener does not manually start/commit/abort transactions in code: the container orchestrates those steps. If the application has multiple `KafkaTemplate` or producer factory beans, avoid accidentally injecting a non-transactional producer.

## 6. Happy Path When Processing Succeeds

Suppose the consumer reads `orders.approved-1@204`:

| Step | Action | State |
|---|---|---|
| 1 | Container polls offset 204 | Record unconfirmed |
| 2 | Container opens Kafka transaction | Transaction active |
| 3 | Listener builds and sends `ShipmentRequested` | Output uncommitted |
| 4 | Listener returns without throwing | Listener-level processing succeeded |
| 5 | Container adds corresponding input offset to transaction | Output and offset share transaction |
| 6 | Transaction commits | Published atomically together |
| 7 | Downstream `read_committed` consumer reads output | Input progress confirmed |

Treat this as a **conceptual** sequence; Spring Kafka manages producer/consumer API details and transaction scope based on listener type and ack mode. Never rewrite these steps with manual `KafkaProducer.commitTransaction()` calls inside `@KafkaListener`.

## 7. Path When the Listener Fails

Example of a listener sending output and then throwing an exception:

~~~java
@KafkaListener(
    topics = "orders.approved",
    containerFactory = "orderTransactionalListenerFactory")
public void onOrder(OrderApproved event) {

    kafkaTemplate.send(
        "shipments.requested",
        event.orderId(),
        toShipment(event)
    );

    if (!availabilityService.isReady()) {
        throw new TemporaryDependencyException("Dependency unavailable");
    }
}
~~~

When the exception propagates up to the container, the Kafka transaction rolls back. Uncommitted outputs in the transaction stay invisible to `read_committed` consumers. Input offsets are not committed in the aborted transaction either.

~~~text
beginTransaction
  -> send output in transaction
  -> listener throws exception
  -> abortTransaction
  -> after-rollback processing
  -> seek/retry or recover per policy
~~~

Never **swallow exceptions** when processing actually failed:

~~~java
// Wrong if the record failed yet the listener returns normally.
try {
    remoteService.call(event);
}
catch (Exception ex) {
    log.error("Remote call failed", ex);
    // Not rethrown: container may commit the transaction.
}
~~~

If an application intentionally treats an error as a valid business completion, model that decision explicitly rather than accidentally turning a failure into a commit.

## 8. Offsets, Ack Mode, and Transactions

The Kafka container combines the offsets it marks as processed with the active transaction. When the transaction succeeds, offsets and output records commit together. The underlying mechanism is `sendOffsetsToTransaction`, though listeners **do not call this API themselves** when the container manages it.

Points to remember:

- Kafka consumer `enable.auto.commit` must not commit independently of container transactions.
- Ack mode affects when the container considers records processed; with transactional listeners, offsets commit **per transaction**.
- Between record listeners and batch listeners, error/rollback scope can differ. A batch failing partway can roll back the batch's transaction, and previously invoked records may be redelivered.
- DLT/recovery can advance offsets for records abandoned from retries, provided recovery transactions are configured accurately.

Committing offsets via `consumer.commitSync()` inside a listener or using a separate producer outside the transaction undermines Kafka-to-Kafka atomicity.

## 9. Why Is read_committed Needed Downstream?

Kafka brokers may store records sent by a transactional producer before the transaction commits or even if it later aborts. Consumers configured with `read_uncommitted` can observe data from aborted transactions.

Consumers wanting to observe only committed transaction effects should configure:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

`read_committed` also reads valid non-transactional records normally. When open transactions exist, consumers can be held back by the **Last Stable Offset (LSO)**. Therefore, observed latency on output topics can rise when transactions run long or stall.

Distinguish:

- **Committed consumer group offset:** consumption progress.
- **Committed transaction:** Kafka writes and offsets within the transaction are finalized.
- **LSO:** safe read boundary for `read_committed` consumers.

Do not call a pipeline "exactly-once" while leaving output consumers on `read_uncommitted` when the application relies on hiding aborted records.

## 10. Transactional ID and Producer Fencing

Every Kafka transactional producer has a `transactional.id`. Brokers use transactional IDs and producer epochs to stop old producers from continuing to publish as if they still held transaction ownership. If another instance creates a producer with the same ID, the previous producer can be **fenced**.

~~~text
Wrong when running in parallel:
  instance-A: tx prefix = orders-tx-
  instance-B: tx prefix = orders-tx-

Can generate duplicate transactional.id values.

Proper direction:
  instance-A: tx prefix = orders-tx-A-
  instance-B: tx prefix = orders-tx-B-
~~~

Spring Kafka derives transactional IDs from the prefix and version-specific suffixes/producer management strategies. Prefixes should be controlled per instance/pod; never set a single fixed value across all replicas.

If `ProducerFencedException` or similar errors appear:

1. Check whether two processes share a transactional ID.
2. Check rolling deployments for overlap between old and new versions.
3. Check producer caches, concurrency, and transaction managers.
4. Check broker transaction coordinator and timeouts.
5. Never catch fencing errors and continue sending as if the producer were still valid.

## 11. Transaction Timeouts and Long-Running Listeners

A Kafka transaction must not stay open indefinitely. Related configurations:

| Configuration | Meaning |
|---|---|
| `transaction.timeout.ms` | Maximum Kafka transaction duration per producer/broker |
| Broker `transaction.max.timeout.ms` | Maximum transaction timeout accepted by broker |
| `max.poll.interval.ms` | Maximum interval between consumer polls |
| `max.poll.records` | Maximum records fetched in a single poll |
| Producer `maxAge` in Spring Kafka | Helps replace idle cached producers before transactional ID expiration in supporting versions |

If a listener calls an HTTP API that can hang for minutes, the transaction stays open too long, increasing timeout risk and keeping outputs invisible to downstream `read_committed` consumers. If the consumer exceeds `max.poll.interval.ms`, group rebalances can trigger additional failures/rollbacks.

Ways to reduce risk:

- Set explicit timeouts for HTTP/database dependencies.
- Shorten processing duration inside transactions.
- Bound batch sizes to realistic processing throughput.
- Use workflows/outbox for long tasks instead of holding Kafka transactions open for minutes.
- Choose retry budgets and backoffs based on dependency recovery times.

## 12. Error Handling: DefaultAfterRollbackProcessor

For transactional listener containers, exceptions normally trigger rollback, after which Spring Kafka uses `DefaultAfterRollbackProcessor` to decide seek/retry/recovery. This differs from the standard `DefaultErrorHandler` in non-transactional listeners.

Example after-rollback processor configuration:

~~~java
@Bean
DefaultAfterRollbackProcessor<String, OrderApproved>
orderAfterRollbackProcessor(DeadLetterPublishingRecoverer recoverer) {

    return new DefaultAfterRollbackProcessor<>(
        (record, exception) -> recoverer.accept(record, exception),
        new FixedBackOff(1_000L, 3L)
    );
}
~~~

Apply to the corresponding factory:

~~~java
factory.setAfterRollbackProcessor(orderAfterRollbackProcessor);
~~~

In the example above, `FixedBackOff` waits one second between retries, up to three retries per Spring Framework semantics. For permanent exceptions, configure appropriate non-retryable classification to avoid pointlessly retrying the same payload.

**Recovery and new transactions:** If you need to publish recovered records to a DLT **and** commit the source offset in a new recovery transaction, configure options such as `commitRecovered` and the corresponding `KafkaTemplate/KafkaOperations` on `DefaultAfterRollbackProcessor` per your Spring Kafka version. Do not assume calling `DeadLetterPublishingRecoverer` alone makes DLT publishing and offset advancement atomic.

If DLT publishing fails, do not consider the record recovered. The container must continue handling the failure per policy to avoid dropping the record.

## 13. Do Not Assume @RetryableTopic Combines with Transactions

`@RetryableTopic` implements non-blocking retries via intermediate topics and delays. In many Spring Kafka versions, non-blocking retries **are not supported directly in combination with container transactions** in standard configurations.

This is because forwarding records across retry topics, advancing input offsets, delaying processing, and rolling back transactions require consistent boundaries. Merely adding `@RetryableTopic` to a transactional listener may fail to achieve the expected semantics.

When retries are needed:

- Short errors: consider retries/backoff via the after-rollback processor.
- Permanent errors: recover to DLT in a controlled way.
- Long-term retries: design a dedicated workflow/retry topology with explicit transaction boundaries, ordering, and idempotency.
- Do not stack multiple retry layers without calculating total attempt counts and failure windows.

## 14. Database Transactions Differ from Kafka Transactions

A listener can both write to a database and send Kafka output:

~~~java
@KafkaListener(
    topics = "payments.received",
    containerFactory = "transactionalPaymentListenerFactory")
public void onPayment(PaymentReceived event) {

    paymentService.saveState(event); // separate DB transaction
    kafkaTemplate.send(
        "payments.applied",
        event.paymentId(),
        new PaymentApplied(event.paymentId())
    );
}
~~~

If `paymentService.saveState` uses database `@Transactional`, that is a **database transaction**. The Kafka container transaction is **another transaction**; Spring does not create an atomic XA transaction between the two systems by default.

Risk scenario:

~~~text
Kafka container transaction starts
  -> DB transaction starts
  -> DB write succeeds
  -> DB commit succeeds
  -> Kafka transaction commit fails
  -> Input record is redelivered
  -> DB may be written twice if not idempotent
~~~

A Kafka transaction cannot roll back an already completed DB commit. Nor can it roll back emails or HTTP requests already accepted by external services.

Common patterns:

1. **Inbox/idempotent consumer:** record processed event IDs and business state in the same database transaction.
2. **Transactional outbox:** persist business state and events to publish in the same database transaction; a publisher sends events later with deduplication.
3. **Saga/state machine:** multi-step cross-service flows using durable state and compensation.
4. **Idempotency keys:** HTTP/payment services supporting repeated identical requests without duplicating effects.

Do not mechanically add `@Transactional` and assume databases and Kafka commit atomically.

## 15. Idempotency in Listeners with Side Effects Outside Kafka

Example of an inbox table in a database:

~~~java
@Service
public class OrderProjectionService {

    @Transactional // database transaction
    public void apply(OrderApproved event) {

        boolean firstTime =
            processedEventRepository.insertIfAbsent(event.eventId());

        if (!firstTime) {
            return;
        }

        orderRepository.markApproved(event.orderId());
    }
}
~~~

`insertIfAbsent` is a conceptual operation; it requires a unique constraint and database transaction to prevent race conditions. Both recording the processed marker and updating business state must commit together.

If the Kafka transaction rolls back after the DB commits, the listener may be called again. The inbox prevents duplicate DB updates. However, if the Kafka output did not commit on the first attempt and the replay **skips sending output** simply because the inbox says "already processed", the application may lose a required output. That case requires an outbox or logic that consistently reconstructs outputs from committed state.

**DB idempotency alone does not prove atomicity between DB and Kafka output.** Choose a pattern that preserves the entire business invariant.

## 16. Async Tasks and Transaction Context

Container transactions are tied to the processing lifecycle on the listener/consumer thread. If a listener submits work to another thread and returns before that work finishes, Kafka producer sends inside that task may not join the open transaction.

Unsafe example:

~~~java
@KafkaListener(
    topics = "orders.approved",
    containerFactory = "orderTransactionalListenerFactory")
public void onOrder(OrderApproved event) {

    CompletableFuture.runAsync(() -> {
        kafkaTemplate.send(
            "shipments.requested",
            event.orderId(),
            toShipment(event)
        );
    });

    // Listener finishes before the async task completes.
}
~~~

The container may commit the transaction before the task even runs. If the task fails, exceptions do not automatically return to the consumer thread to roll back the input offset.

If asynchronous processing is necessary, explicitly design result awaiting, transaction context propagation, and error handling. For long tasks or work decoupled from the poll loop, prefer durable workflows instead of keeping Kafka transactions open indefinitely.

Do not nest `KafkaTemplate.executeInTransaction` inside a container transaction without understanding that it can create a transaction independent of the container's transaction.

## 17. Concurrency and Transaction Scope

A `ConcurrentMessageListenerContainer` with `concurrency = 3` spawns three child consumers operating in parallel, each with its own consumer thread and transaction lifecycle.

~~~text
Listener container (concurrency=3)
  |
  +-- consumer A -> Kafka tx A
  +-- consumer B -> Kafka tx B
  +-- consumer C -> Kafka tx C
~~~

This does not create one global Kafka transaction across the entire consumer group.

- Failure in one consumer does not by default roll back another consumer's transaction.
- Raising concurrency increases demand for transactional producers and transaction IDs.
- Having more consumers than useful partitions does not increase throughput proportionally.
- Consider output keys to preserve per-aggregate ordering.
- Kafka transactions do not provide a total order across all partitions.

Producer factories and transaction managers must have enough capacity for concurrent transactions. Watch CPU, memory, Kafka producer caches, and broker coordinator health when scaling.

## 18. Critical Failure Windows

| Incident | Kafka output | Input offset | Required handling |
|---|---|---|---|
| Exception before sending output | None | Not committed in failed transaction | Retry/recovery |
| Exception after sending, before commit | Transaction aborts | Not committed | Downstream `read_committed` does not see aborted output |
| Process crashes mid-transaction | Broker may abort on timeout/fencing | Uncommitted in tx | Input may be redelivered |
| Kafka commit completed yet app loses connection | Depends on broker outcome | Depends on transaction outcome | Do not conclude from local exception alone |
| DB committed yet Kafka commit fails | DB retains side effect | Kafka tx uncommitted | Needs idempotency/outbox |
| DLT publisher fails | DLT not durably written | Must not mark recovery done | Retry recovery, alert |
| Downstream consumer `read_uncommitted` | May see aborted output | Unrelated to input offset | Violates isolation expectations |
| Two pods share transactional ID | Producer may be fenced | Transaction fails | Fix prefix/rollout |

For producer fencing errors, never silently retry sends on the same producer as if it were a transient network blip; inspect transaction state and transactional ID ownership.

## 19. Operating on Kubernetes and Kafka Clusters

When deploying multiple replicas:

1. Assign a unique transaction ID prefix per concurrently active instance.
2. Check rolling deployments to avoid overlapping instances sharing a transactional ID.
3. Provision topics/ACLs and ensure the broker transaction coordinator is healthy.
4. Size consumer groups, partition counts, and concurrency appropriately.
5. Align graceful shutdown with listener and transaction timeouts.
6. Verify downstream consumers use `read_committed` when needed.
7. Monitor producer fencing, transaction timeouts, retries, and DLT.
8. When running a single broker locally/in tests, tune transaction state log replication/min ISR accordingly; production must use durable replication levels.

`SIGTERM` does not guarantee every transaction commits. If a process is killed, brokers can abort open transactions and inputs may be redelivered. Listeners must remain replay-safe.

## 20. Observability for Transactional Listeners

| Metric/signal | Why needed |
|---|---|
| Kafka transaction commit/abort/error | Assess transaction stability |
| Transaction duration | Detect transactions held open too long |
| `ProducerFencedException` | Detect duplicate IDs or invalid producers |
| Broker transaction coordinator errors | Transaction infrastructure failures |
| Consumer lag and rebalances | Track input progress |
| Kafka output publishing failures | Detect transactional output failures |
| After-rollback retry count | Detect repeating listener errors |
| DLT recovery count/failures | Unprocessable records |
| Consumer `read_committed` lag | Observe LSO impact |
| Duplicate event IDs in inbox | Track replays and idempotency |

Logs should include topic, partition, offset, consumer group, event ID, and exception class; avoid logging secrets or sensitive payloads. Do not use event IDs as metric labels due to very high cardinality.

Alert when transaction failures spike after deploys, fencing appears across pods, transaction durations exceed budgets, or lag climbs while listeners roll back repeatedly.

## 21. Runbook When a Transactional Listener Misbehaves

**Duplicate outputs:** check downstream `read_committed` isolation, confirm `KafkaTemplate` joins the matching transactional producer factory, and check whether upstream published duplicate business events. If duplicates happen in databases or HTTP side effects, fix idempotency outside Kafka.

**Producer fenced:** check transaction ID prefixes across all pods, rollout overlap, producer caches, and the broker coordinator. Never treat fencing as a normal record error and commit the offset.

**Increasing timeouts:** measure listener duration, database/HTTP latency, transaction timeout, and `max.poll.interval.ms`. Apply dependency timeouts and shorten work inside transactions rather than raising timeouts indefinitely.

**Records retrying endlessly:** inspect exceptions thrown by the listener, after-rollback processor, backoff, and retryable/non-retryable classification. Verify DLT recovery publishes succeed when retry budgets run out.

**Listener returns normally yet produces no result:** look for code catching exceptions without rethrowing, unawaited async tasks, or a `KafkaTemplate` not participating in the active transaction.

## 22. Scenarios to Verify Behavior

A test environment with a transaction-capable Kafka broker should exercise three paths.

**Success:** publish an input event, listener sends output, Kafka transaction commits, downstream `read_committed` sees the output, and the input offset advances properly.

**Intentional rollback:** after sending output in the listener, throw an exception. Downstream `read_committed` must not see the aborted output; input is retried/recovered per configuration.

**Crash/failover:** stop the process before commit, start a replacement instance, and verify Kafka outputs/offsets reach a consistent outcome. If database side effects exist, verify inbox/idempotency prevents duplicate updates.

These scenarios distinguish genuinely working transactions from configurations where the producer merely has `transaction-id-prefix` set while the listener container lacks a transaction manager.

## 23. Choosing a Pattern by Consistency Requirement

| Requirement | Design direction |
|---|---|
| Read Kafka and write Kafka, commit output + input offset together | Container-initiated Kafka transaction |
| Read Kafka and update only a database | DB transaction + inbox/idempotency |
| Update database then reliably emit Kafka events | Transactional outbox |
| Coordinate multiple external APIs | Workflow/saga with durable state and idempotency |
| Short retries inside a transactional listener | After-rollback processor and backoff |
| Unprocessable payloads | Recovery/DLT per policy |
| Long-delayed retries across multiple topics | Separate retry architecture; review container transaction limitations |
| Consumers must never see aborted records | `isolation.level=read_committed` |

**Listener container transactions enable Spring Kafka to combine output records and input offset progress into a single Kafka transaction.** To use them properly, ensure the container uses the right `KafkaTransactionManager` and transactional producer factory, assign unique transaction ID prefixes per instance, let the container manage commits/rollbacks, and use `read_committed` on consumers needing isolation. For side effects outside Kafka, you still must design idempotency, inbox, outbox, or workflows because Kafka transactions cannot roll back databases or external systems.
