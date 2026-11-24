# Transaction Rollback in Spring Kafka

**Transaction rollback** in Spring Kafka is the act of invalidating a Kafka transaction when sending or processing records does not complete properly. At the Kafka producer layer, the corresponding operation is `abortTransaction()`. With a transactional listener container, an exception can cause the Kafka transaction to abort, after which **AfterRollbackProcessor** decides how to seek and reprocess unfinished records.

A Kafka transaction can include multiple output records and **the input consumer's offset**, enabling a consume → process → produce flow: either Kafka outputs and offsets commit together, or the transaction aborts and the offset does not advance via that transaction.

This **does not mean databases, REST APIs, emails, or external systems also roll back**. If a listener updated a database and then the Kafka transaction aborts, the database may still have committed. Therefore, rollback must be understood alongside offsets, idempotency, retries, DLT, and transaction boundaries.

## 1. Which Components Do Kafka Transactions Protect?

A Kafka producer can open a transaction, send multiple records to one or more partitions, and then commit or abort. In a consume-and-produce flow, the consumer group's offset can be sent into that very transaction.

~~~text
orders.created (input topic)
        |
        v
Kafka listener container
        |
        +--> Begin Kafka transaction
        |
        +--> Invoke @KafkaListener
        |        |
        |        +--> Validate event
        |        +--> KafkaTemplate.send("orders.validated")
        |
        +--> Send input offsets to transaction
        |
        +-------------+-------------+
        |                           |
        v                           v
   COMMIT TRANSACTION         ABORT TRANSACTION
        |                           |
        +--> Output Kafka           +--> Output Kafka
        |    is committed           |    is not visible to
        |                           |    read_committed
        +--> Input offsets          +--> Transaction input offsets
             are committed               do not commit
~~~

Spring Kafka components:

- `KafkaTemplate` uses a Spring-managed producer to send records.
- `KafkaTransactionManager` manages producer transactions within Spring's transaction infrastructure.
- Listener containers can open a Kafka transaction before invoking the listener.
- `DefaultAfterRollbackProcessor` handles records after a Kafka transaction rolls back.
- `DeadLetterPublishingRecoverer` can route unrecoverable records to a DLT.
- Consumers configured with `isolation.level=read_committed` observe only committed transactional outputs.

Not every `@KafkaListener` is transactional. It exhibits this behavior only when the container factory and transaction manager are properly configured.

## 2. Commit, Rollback, Retry, and Recovery Differ

| Term | Meaning | Impact on input record |
|---|---|---|
| Commit transaction | Confirms Kafka outputs and enlisted offsets | Group offset advances when transaction commits |
| Abort/rollback | Cancels an uncommitted transaction | Offset is not committed by that transaction |
| Retry | Re-executes listener logic after failure | Same record may be redelivered |
| Seek | Adjusts consumer position | Allows re-polling records needing processing |
| `AfterRollbackProcessor` | Coordinates seek, backoff, recovery after abort | Retains or recovers failed records per policy |
| DLT recovery | Saves failed records to a separate topic | May advance offset after successful recovery |
| Database rollback | Undoes database transaction | Not performed automatically by Kafka abort |

**Rollback does not delete the input record from Kafka.** The record stays in the source topic. If the input offset has not committed, the consumer may encounter the record again when continuing or when the partition is reassigned to another instance.

## 3. Producer Transaction Lifecycle

In the Kafka client, the high-level lifecycle is:

~~~text
initTransactions()
      |
      v
beginTransaction()
      |
      +--> send(record A)
      +--> send(record B)
      +--> sendOffsetsToTransaction(...) when using consumer group
      |
      +--> Success --------------------> commitTransaction()
      |
      +--> Exception ------------------> abortTransaction()
~~~

Spring Kafka normally manages these steps for the application. For a producer managed by `KafkaTemplate` and `KafkaTransactionManager`, never manually open or commit a transaction on the same producer outside the transaction scope.

An aborted transaction does not simply mean records are physically erased from the log immediately. Kafka uses transaction markers to represent commit/abort; consumers with `isolation.level=read_committed` do not return records belonging to aborted transactions.

Consumers using `read_uncommitted` can observe records from aborted transactions. Therefore, downstream systems relying on Kafka's exactly-once semantics must configure their isolation level accordingly.

## 4. Spring Boot Configuration for Kafka Transactions

Configuration example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      transaction-id-prefix: order-service-node-1-
      acks: all
      properties:
        "[enable.idempotence]": true
    consumer:
      group-id: order-validator
      enable-auto-commit: false
      isolation-level: read_committed
    listener:
      ack-mode: record
~~~

Meaning:

- `transaction-id-prefix` is the prefix used to generate `transactional.id` values for Spring-managed producers. In Spring Boot, this setting can trigger auto-configuration of the Kafka transaction manager when applicable conditions are met.
- `acks=all` and `enable.idempotence` support reliable producer configuration. Kafka transactional producers have corresponding idempotence requirements.
- `enable-auto-commit=false` lets the container actively manage offsets and enlist them in transactions.
- `isolation-level=read_committed` is especially important for consumers reading transactional outputs from other producers.
- `ack-mode` determines how the container tracks listener progress; offsets inside Kafka transactions have container-managed semantics.

**Transactional IDs must avoid collisions between two active producers.** If multiple replicas share the same transactional identity, Kafka can fence the older producer. When scaling or rolling out, design prefixes/suffixes matching instance counts and producer caches.

If you define custom `ProducerFactory` or `ConcurrentKafkaListenerContainerFactory` beans, verify that the transaction manager is actually attached to the factory in use. YAML alone does not wire an unconfigured custom factory.

## 5. Sending Multiple Records with KafkaTemplate.executeInTransaction

When an application only needs to send multiple records as a single Kafka transaction unit, `executeInTransaction` can be used:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishBoth(
            String orderId,
            OrderEvent event,
            OrderEvent auditEvent) {

        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("orders.events", orderId, event).join();
            operations.send("orders.audit", orderId, auditEvent).join();
            return null;
        });
    }
}
~~~

This example illustrates the `CompletableFuture` style of modern Spring Kafka versions. `KafkaTemplate` must use a transactional `ProducerFactory`. If a send call throws a `RuntimeException` out of the callback, Spring aborts the transaction. If the callback finishes normally, Spring attempts to commit.

Calling `join()` propagates asynchronous send failures inside the callback. If errors are swallowed, execution may proceed to commit despite business failure.

Unsuitable example:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    try {
        operations.send("orders.events", orderId, event).join();
    }
    catch (RuntimeException ex) {
        log.error("Send failed", ex);
        // Swallows error, returns normally.
    }
    return null;
});
~~~

If an abort is needed, throw an exception out of the callback. Never manually call `producer.commitTransaction()` or `abortTransaction()` on resources managed by `KafkaTemplate`.

`executeInTransaction` fits producer-only Kafka transactions. If you need to enlist **input consumer offsets** in the transaction, use a transactional listener container or framework-supported transactional offset management.

## 6. @Transactional and Spring Rollback Rules

You can use Spring's transaction abstraction with `KafkaTransactionManager`:

~~~java
@Service
public class BillingEventService {

    private final KafkaTemplate<String, BillingEvent> kafkaTemplate;

    public BillingEventService(
            KafkaTemplate<String, BillingEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publishBillingEvent(
            String invoiceId,
            BillingEvent event) {

        kafkaTemplate.send("billing.events", invoiceId, event);

        if (!event.isAllowed()) {
            throw new IllegalStateException(
                    "Billing event is not allowed"
            );
        }
    }
}
~~~

The example assumes a `KafkaTransactionManager` bean named `kafkaTransactionManager` and a `KafkaTemplate` configured with a transaction-capable `ProducerFactory`.

By Spring transaction abstraction defaults:

- `RuntimeException` and `Error` usually trigger rollback.
- Checked exceptions do not trigger rollback by default unless `rollbackFor` or another rollback rule is configured.
- The transaction must actually be opened via a Spring proxy or transaction infrastructure; self-invocation can bypass `@Transactional`.
- Catching an exception and returning normally may cause the transaction to commit instead of roll back.

If a business exception is a checked exception, you can declare:

~~~java
@Transactional(
        transactionManager = "kafkaTransactionManager",
        rollbackFor = Exception.class
)
public void publishWithCheckedFailure() throws Exception {
    // Send event and throw checked exception on failure.
}
~~~

Do not apply a broad `rollbackFor` rule without understanding which exceptions truly require rollback; however, explicitly handle checked exceptions when you intend for them to abort the transaction.

## 7. Rollback in Transactional Listener Containers

A transactional listener container is a key configuration for **consume-process-produce** flows. The container starts a Kafka transaction, invokes the listener, enlists input offsets in the transaction, and commits on success.

~~~text
KafkaConsumer.poll()
         |
         v
Container begin transaction
         |
         v
@KafkaListener
         |
         +--> KafkaTemplate.send(output)
         |
         +--> return normally
         |         |
         |         v
         |   send input offsets into transaction
         |         |
         |         v
         |      COMMIT
         |
         +--> throw exception
                   |
                   v
                 ABORT
                   |
                   v
           AfterRollbackProcessor
                   |
                   v
              Retry / recovery
~~~

Listener:

~~~java
@Component
public class OrderValidatorConsumer {

    private final OrderValidator validator;
    private final KafkaTemplate<String, OrderValidated> kafkaTemplate;

    public OrderValidatorConsumer(
            OrderValidator validator,
            KafkaTemplate<String, OrderValidated> kafkaTemplate) {
        this.validator = validator;
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-validator",
            containerFactory = "transactionalListenerFactory"
    )
    public void onOrder(OrderCreated event) {
        OrderValidated validated = validator.validate(event);

        kafkaTemplate.send(
                "orders.validated",
                event.orderId(),
                validated
        );
    }
}
~~~

`transactionalListenerFactory` must be configured with a Kafka-aware transaction manager per your Spring Kafka version's API. The `KafkaTemplate` sending outputs must participate in the container-opened thread-bound Kafka transaction. Merely naming `containerFactory` in the annotation does not make a listener transactional automatically.

The listener should not call `consumer.commitSync()` or enable auto-commit when the goal is committing Kafka offsets atomically with transactional outputs.

## 8. Exceptions Propagating to Trigger Rollback

Example of a listener sending output and then throwing an exception:

~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "transactionalListenerFactory"
)
public void onOrder(OrderCreated event) {
    validator.validate(event);

    kafkaTemplate.send(
            "orders.validated",
            event.orderId(),
            toValidated(event)
    );

    if (event.needsManualReview()) {
        throw new BusinessProcessingException(
                "Manual review required"
        );
    }
}
~~~

When the exception actually reaches the container:

1. The container catches the exception.
2. The transaction manager aborts the Kafka transaction.
3. Kafka outputs in the transaction are aborted.
4. Input offsets sent into that transaction are not committed.
5. `AfterRollbackProcessor` handles seek/redelivery or recovery.
6. The input record remains in the source topic and can be retried.

**Beware of swallowing exceptions:**

~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "transactionalListenerFactory"
)
public void onOrder(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Failed", ex);
        // Returning normally can lead to commit.
    }
}
~~~

Logging an error is not equivalent to rolling back. If the application wants the container to abort, rethrow the exception or use a framework-supported rollback policy.

## 9. AfterRollbackProcessor and Read Position After Rollback

A `KafkaConsumer` has two states to distinguish:

- Consumer position: the offset the consumer will fetch next after poll/seek.
- Committed group offset: the position durably persisted for the group.

A Kafka transaction may hold an offset **pending commit**. When the transaction aborts, that offset does not become a committed offset. However, the consumer may have polled multiple records so its internal position has already advanced further. Thus, the container needs appropriate seek/redelivery handling.

Spring Kafka's `DefaultAfterRollbackProcessor` handles that scenario:

~~~text
poll() receives A, B, C
         |
         +--> process A
         +--> process B fails
         |
         v
Kafka transaction abort
         |
         v
DefaultAfterRollbackProcessor
         |
         +--> Identify incomplete records
         +--> BackOff policy
         +--> Seek to redelivery position
         |
         v
re-poll corresponding records
~~~

Do not think of `abortTransaction()` as a Kafka command that automatically seeks the consumer back to the beginning of the topic. Abort changes transaction state in Kafka; the Spring container/`AfterRollbackProcessor` is responsible for coordinating read positions for retries.

With transactional containers, exceptions must escape so transactions roll back. Spring Kafka does not by default handle transactional container errors by swallowing exceptions the way some non-transactional configurations do. If configuring a custom `CommonErrorHandler`, verify whether it rethrows exceptions.

## 10. Bounded Retries After Rollback

You can create a `DefaultAfterRollbackProcessor` with a recoverer and `BackOff`:

~~~java
DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
                (record, exception) -> {
                    log.error(
                            "Failed record: topic={}, partition={}, offset={}",
                            record.topic(),
                            record.partition(),
                            record.offset(),
                            exception
                    );
                },
                new FixedBackOff(1_000L, 2L)
        );
~~~

This example describes two retries after the initial attempt, spaced one second apart. However, **a recoverer that only logs does not durably preserve failed records**. If data preservation is needed, use `DeadLetterPublishingRecoverer` or a quarantine store that guarantees write acknowledgment.

Retry guidelines:

- Set finite attempt counts and bounded backoffs.
- Distinguish transient errors from permanent data errors.
- Malformed payloads will not fix themselves after a few retries.
- Long backoffs block partitions and can increase consumer lag.
- Any side effects outside Kafka need duplicate protection.
- If the recoverer fails, the error must not be treated as recovered.

Attach the `AfterRollbackProcessor` to the exact container factory used by the listener using your Spring Kafka version's API. A standalone processor bean does not guarantee the listener picks it up unless the factory is wired.

## 11. Batch Listeners and Rollback

A batch listener receives multiple records in one callback. If the callback processes several records successfully and then throws an exception, the transaction containing the batch's outputs may abort. All or part of the batch may need to be re-read according to recovery policy.

~~~text
poll batch:
  A: success
  B: success
  C: exception
  D: not processed
         |
         v
   Kafka transaction abort
         |
         v
   AfterRollbackProcessor
         |
         v
   Redelivery / recovery
~~~

A generic exception from a batch listener does not necessarily tell the framework exactly which record failed. Depending on the version, `AfterRollbackProcessor` may have to redeliver the entire batch. If A and B already updated a database outside Kafka, they may execute again even though the transaction's Kafka output aborted.

When using batch listeners:

- Clearly identify the batch recovery strategy for your Spring Kafka version.
- Use `eventId` and per-record idempotency.
- If needed, use database transactions for batch operations.
- Bound batch sizes against `max.poll.interval.ms` and transaction timeouts.
- Do not treat partial batch success as a committed offset.
- Test mid-batch failures, DLT errors, and crashes before commit.

If business logic requires handling failures per record independently, a record listener can be simpler than a transactional batch listener.

## 12. Recovery to DLT After Rollback

A permanently failing record can repeatedly roll back transactions without self-healing. Once retries are exhausted, `AfterRollbackProcessor` can use a recoverer to send the record to a DLT.

~~~text
Transactional listener
        |
        +--> exception
                |
                v
         Abort Kafka transaction
                |
                v
        AfterRollbackProcessor
                |
                +--> Retry/seek again
                |
                +--> Retries exhausted
                         |
                         v
                 DeadLetterPublishingRecoverer
                         |
                         v
                        DLT
~~~

Example:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltKafkaTemplate);

DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
                recoverer,
                new FixedBackOff(2_000L, 3L)
        );
~~~

Understand the transaction boundary: **the failing transaction has already aborted before recovery runs**. To give DLT publishing and recording the recovered offset consistent semantics, Spring Kafka provides transactional recovery options in supporting versions, such as `setCommitRecovered(true)` with a matching `KafkaTemplate` on `DefaultAfterRollbackProcessor`.

Do not enable a `commitRecovered` option and assume everything is atomic without properly configuring the producer factory, `KafkaTemplate`, transaction manager, and container type.

If DLT publishing fails due to serializer, ACL, missing partition, or broker error, do not treat the source record as successfully recovered. Let the failure surface and rehandle according to policy.

A duplicate window can still exist if the record appeared on the DLT yet the recovered offset had not committed when the process crashed. DLT consumers and replay tools must use event IDs to handle duplicates safely.

## 13. Consumer Position vs Committed Offset

Suppose an input topic has:

~~~text
offset 100: record A
offset 101: record B (failed)
offset 102: record C
~~~

The consumer may have polled A, B, and C. The consumer's position may sit at offset 103, while the group's committed offset remains at the earlier position. If the transaction aborts, offsets pending commit in the transaction do not become committed offsets. `AfterRollbackProcessor` can seek back to reprocess records needing retry.

Distinctions:

| Value | Definition |
|---|---|
| Record offset | Position of a record within a partition |
| Consumer position | Next position the consumer will poll after seek/poll |
| Committed offset | Next position to read persisted for the group |
| Offset in transaction | Offset not finalized until the transaction commits |

Kafka commits the offset of **the next record**. If record at offset 100 finished processing, the corresponding committed value is typically 101.

Do not manually call `consumer.seek` or `consumer.commitSync` inside a listener managed by a transactional container without a very deliberate design. Such calls can desynchronize state from the transaction manager.

## 14. read_committed and Output of Aborted Transactions

A downstream consumer wanting to see only committed Kafka records needs:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

The difference:

~~~text
Kafka transaction T1:
  publish A
  publish B
  abort

Consumer read_committed:
  does not return A, B from T1

Consumer read_uncommitted:
  may see A, B even though T1 aborted
~~~

Kafka maintains transaction metadata and transaction markers. Records from aborted transactions are not necessarily deleted from the log immediately; `read_committed` filters them based on transaction state.

An open transaction can affect the Last Stable Offset and when `read_committed` consumers get to see subsequent records. Therefore, overly long transactions can increase apparent consumer lag and latency, even when consumers poll normally.

`read_committed` does not automatically make all downstream side effects exactly-once, but it is essential when consumers read transactional outputs.

## 15. Database Rollback Differs from Kafka Rollback

This is the most commonly misunderstood boundary.

~~~text
@KafkaListener
      |
      +--> Update database and commit successfully
      |
      +--> Send Kafka output
      |
      +--> Throw exception
                |
                v
        Kafka transaction abort
                |
                +--> Kafka output is aborted
                +--> Input offset not committed
                +--> Database may still have committed
~~~

`KafkaTransactionManager` does not automatically roll back PostgreSQL/MySQL transactions or REST APIs. Even when coordinating two Spring transaction managers, **there is no default XA/2PC transaction** guaranteeing atomic commit/rollback across two resources in every failure mode. One resource can commit before the other fails.

Protective mechanisms:

1. **Idempotent consumer:** each event has a stable `eventId`; do not reapply already completed side effects.
2. **Transactional inbox:** write the processed event and domain updates in the same database transaction.
3. **Transactional outbox:** persist domain changes and an outbox event in the same database transaction; a separate publisher sends to Kafka.
4. **Reconciliation:** periodically compare database state against Kafka outputs.
5. **Compensating action:** run business compensation if an action outside Kafka finished and cannot roll back.

Inbox idempotency example:

~~~java
@Transactional("transactionManager")
public void processOrder(OrderCreated event) {

    boolean firstTime =
            processedEventRepository.insertIfAbsent(event.eventId());

    if (!firstTime) {
        return;
    }

    orderRepository.applyCreation(event);
}
~~~

`insertIfAbsent` represents an operation backed by a unique constraint on `eventId`. Both recording the processed event and updating the order must share the same database transaction. Never store event IDs solely in JVM memory, as that does not survive restarts.

## 16. What Is the Scope of Kafka Exactly-Once?

In a Kafka-to-Kafka flow, if input offsets and output records share the same Kafka transaction, and downstream reads with `read_committed`, the system can achieve exactly-once semantics for the managed Kafka changes.

However:

- Listener methods can still be invoked again after aborts, crashes, or rebalances.
- Databases can be updated twice without idempotency.
- Sent emails or completed HTTP calls cannot be undone by a Kafka abort.
- DLT recovery can encounter duplicates if publish and offset commit are not safely coordinated.
- If downstream uses `read_uncommitted`, it can read outputs from aborted transactions.

Do not claim end-to-end exactly-once without listing every resource with side effects and how each is protected.

## 17. Transactional ID, Fencing, and Fatal Errors

Kafka producers use `transactional.id` so the coordinator can identify the producer, transaction, and epoch. If two active producers share the same `transactional.id`, the older producer can be fenced when the other creates a new epoch.

~~~text
Instance A: transactional.id = order-tx-0
        |
        +--> Begin transaction
        |
Instance B: same transactional.id
        |
        v
Kafka coordinator issues new epoch
        |
        v
Instance A is fenced
        |
        v
Cannot commit as a normal network error
~~~

Fencing protects the system from two producers with the same transactional identity writing concurrently. In production:

- Manage `transactionIdPrefix` and suffixes relative to replicas, concurrency, and producer caches.
- Avoid configuring the exact same static `transactional.id` across all pods.
- Monitor `ProducerFencedException` and producer epoch errors.
- Never retry infinitely on an already fenced producer.
- Close/replace producers through the lifecycle managed by Spring Kafka / `ProducerFactory`.
- Test rolling deployments and scale-out.

Do not treat fencing as a transient glitch where sleeping and retrying on the same old producer will work.

## 18. Transaction Timeout and Poll Timeout

Distinct timeout parameters:

| Configuration | Meaning |
|---|---|
| `transaction.timeout.ms` | Maximum time a transaction may stay open per transaction coordinator |
| `delivery.timeout.ms` | Total time for a producer to complete a send |
| `request.timeout.ms` | Time waiting for a single producer request |
| `max.poll.interval.ms` | Maximum interval between consumer polls |
| `session.timeout.ms` | Time to detect lost heartbeats under group protocol |

If a listener holds a transaction open too long, the transaction can time out and be aborted by the coordinator. If a listener blocks the consumer thread in processing or sleeps too long, it can also exceed `max.poll.interval.ms`, causing a rebalance.

Do not solve this by setting all timeouts to huge values. Instead:

- Reduce processing time inside Kafka transactions.
- Bound batch sizes.
- Enforce timeouts on APIs/databases.
- Classify transient vs permanent errors.
- Use bounded retries and recovery/DLT for poison pills.
- For hour-long retries, use a separate durable retry flow instead of keeping transactions open.
- Check whether non-blocking retries are compatible with transactional listener containers in your Spring Kafka version.

## 19. DefaultErrorHandler and AfterRollbackProcessor

| Component | When useful |
|---|---|
| `KafkaTransactionManager` | Managing Kafka producer transactions |
| `KafkaTemplate.executeInTransaction` | Wrapping multiple output sends in a local transaction |
| `DefaultErrorHandler` | Retries/recovery in standard listener containers |
| `DefaultAfterRollbackProcessor` | Seek, retry, and recovery after transactional container rollbacks |
| `DeadLetterPublishingRecoverer` | Sending unrecoverable records to a DLT |
| `@RetryableTopic` | Non-blocking retries via retry topics; check transaction limitations |

For transactional listeners, exceptions must be visible to the framework for rollback to happen. An error handler that catches and returns normally can cause the transaction to commit instead of abort. For post-rollback recovery, use `AfterRollbackProcessor` in its proper role.

## 20. Testing Rollback Against Real Kafka

Unit tests calling `@KafkaListener` methods directly cannot verify Kafka transaction aborts or offset commits. Use EmbeddedKafka, Testcontainers, or an integrated Kafka cluster to test:

| Scenario | Expectation |
|---|---|
| Listener succeeds | Output commits, input offset advances |
| Listener throws `RuntimeException` | Transaction aborts, output absent from `read_committed` |
| First attempt fails, next succeeds | Redelivery and output committed via Kafka transaction |
| Permanently invalid payload | Bounded retries then DLT |
| DLT publish fails | Record not treated as recovered successfully |
| Crash before transaction commit | Input can be redelivered, uncommitted output invisible |
| Crash after commit | Outputs and offsets remain committed |
| Producer fencing | Error handled per lifecycle, no bad commits |
| Batch fails on middle record | Record/batch redelivery per recovery policy |
| Database commits then Kafka aborts | No duplicate database side effects |
| `read_uncommitted` consumer | Can see aborted outputs, exposing risk |
| Transaction timeout | Abort and recovery function properly |

Typical test flow:

~~~text
1. Publish eventId=evt-1 to orders.created
2. Listener sends output, then intentionally throws exception
3. read_committed consumer does not see aborted output
4. AfterRollbackProcessor schedules record retry
5. Next processing attempt succeeds
6. read_committed consumer sees committed output
7. Input offset is committed properly
8. Database still has no duplicate side effect
~~~

Verify output topic state, committed offsets, DLT, and database. Counting how many times the listener was invoked is insufficient to prove Kafka transaction semantics.

## 21. Metrics and Operations

Signals to monitor:

| Signal | Purpose |
|---|---|
| Transaction abort rate | Quantify failed transactions |
| Transaction commit latency | Measure commit duration |
| Transaction coordinator errors | Detect Kafka transaction infrastructure errors |
| Producer fencing count | Detect duplicate transactional IDs |
| `AfterRollbackProcessor` retry count | Observe redeliveries |
| Consumer lag per partition | Locate blocked partitions |
| DLT publish success/failure | Know whether recovery safely stores records |
| Transaction timeouts | Detect transactions held open too long |
| Rebalance count | Detect consumer group instability |
| Duplicate event detection | Evaluate idempotency outside Kafka |
| End-to-end event latency | Measure latency from input to committed output |

Metric names depend on Kafka client, Spring Kafka, Micrometer, and exporters. Some metrics must be instrumented by the application. Structured logs should include group ID, topic, partition, offset, `eventId`, exception class, retry count, and commit/abort/recovery outcomes, while avoiding sensitive raw payloads.

Situations to watch closely:

**Infinite record looping:** inspect exceptions, `AfterRollbackProcessor`, classifiers, and DLT. Never retry a permanently malformed payload infinitely.

**Output visible in broker yet unreadable by `read_committed`:** inspect transaction state, aborted records, and open transactions / Last Stable Offset.

**Database updated yet Kafka aborted:** design inbox/outbox and idempotency; do not expect Kafka abort to undo databases.

**Abnormal rollbacks when deploying multiple replicas:** inspect transactional IDs and producer fencing.

**Transaction timeouts in large batches:** inspect batch size, processing time, `transaction.timeout.ms`, and `max.poll.interval.ms`.

**`DefaultErrorHandler` present yet no rollback:** verify whether exceptions are swallowed before the transaction manager observes them.

**Duplicates in DLT:** inspect the window where DLT publish succeeded yet recovered offset had not committed; use `eventId` to identify and handle duplicates.

## 22. Checklist Before Bringing Transactional Rollback to Production

- `ProducerFactory` has Kafka transactions enabled properly.
- `transactionIdPrefix` does not cause fencing across active instances.
- `KafkaTemplate` and `KafkaTransactionManager` use the same appropriate transaction resource.
- Listener container genuinely has a Kafka-aware transaction manager when consume-process-produce is required.
- Consumer auto-commit is disabled and offsets are managed by the container.
- Consumers requiring EOS set `isolation.level=read_committed`.
- Exceptions requiring abort propagate out of the listener.
- `@Transactional` has appropriate rollback rules, including checked exceptions when needed.
- `DefaultErrorHandler` is not confused with `DefaultAfterRollbackProcessor`.
- Post-rollback retries have finite attempts and bounded backoff.
- Permanent data errors route to recovery/DLT instead of retrying forever.
- Failed DLT publishes are not treated as successful recovery.
- Transactional recovery uses matching `KafkaTemplate`/`commitRecovered` if enabled.
- Batch listeners have explicit policies for mid-batch failures.
- Transactions do not exceed timeouts or trigger rebalances.
- Database/API side effects use inbox/outbox/idempotency or compensation.
- Tests cover aborts, crashes, commit failures, fencing, DLT failures, and redelivery.
- Monitoring covers rollbacks, commits, consumer lag, and duplicates.
- The system's exactly-once scope is clearly defined.

**Conclusion:** Rolling back a Kafka transaction aborts uncommitted Kafka outputs and prevents committing the input offsets belonging to that transaction. With a transactional listener container, `AfterRollbackProcessor` retries or recovers affected records. Reliability comes not only from `abortTransaction`, but also from transaction manager configuration, exception propagation, consumer isolation levels, DLT setup, and protecting side effects outside Kafka.

