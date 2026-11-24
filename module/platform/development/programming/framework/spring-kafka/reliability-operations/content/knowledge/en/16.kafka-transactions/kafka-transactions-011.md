# Redelivery After Rollback

In Spring Kafka, **Kafka transactions** let an application coordinate writing output records and committing input offsets within the same Kafka transaction. If the listener processes successfully, the transaction can commit both output records and processed offsets. If the listener fails and the transaction rolls back (aborts), **the input record's offset is not committed in that transaction**, so the record can be redelivered to the consumer.

**Redelivery after rollback** is more than simply calling the listener again. It involves the Kafka consumer position, committed offsets, broker transaction state, how the listener container repositions the read cursor, retry/recovery policies, and idempotent processing. Understanding these boundaries prevents two dangerous bugs: losing records by marking them processed too early, and causing duplicate side effects when records are redelivered.

In this article, examples focus on Spring Kafka using listener containers and a Kafka transaction manager. Configuration APIs may vary across Spring Kafka versions; always check against your project's actual dependency version.

## 1. What Does Redelivery After Rollback Mean?

Consider the consume-process-produce flow:

    Topic orders.created
           |
           v
    Spring Kafka consumer
           |
           v
    @KafkaListener
           |
           +---- business processing
           |
           +---- KafkaTemplate.send("orders.validated")
           |
           v
    Send processed offset into Kafka transaction
           |
           v
    Commit transaction

If the entire transaction completes, the resulting records are published and the consumer offset commits with the transaction. If the listener throws an exception or the transaction fails before commit, the transaction aborts.

    Input record offset 120
           |
           v
    Kafka transaction T1 begins
           |
           v
    Listener produces output X
           |
           v
    Listener throws exception
           |
           v
    Abort T1
           |
           +---- Output X is invisible to read_committed consumers
           |
           +---- Offset 121 was not committed by T1
           |
           v
    Consumer is repositioned to re-read
           |
           v
    Redelivery of record offset 120

The redelivered record retains the original topic, partition, offset, and payload as stored in the Kafka log. However, **it is not necessarily redelivered instantaneously**: the container may apply backoff, handle rebalances, or wait for broker/dependency issues to resolve.

Redelivery is the possible outcome when an offset remains uncommitted; it is not a promise that every failure always produces exactly one retry invocation. Retry configuration, recovery, shutdown timing, partition ownership, and retention duration all affect subsequent processing.

## 2. Distinguishing Consumer Position from Committed Offset

A Kafka consumer maintains at least two distinct concepts:

- **Consumer position:** the next offset the consumer expects to fetch in its current session; a single poll can advance this position.
- **Committed offset:** the offset persisted for the consumer group, used to determine where to resume when a consumer restarts or a partition is reassigned.

Example:

    Topic orders.created, partition 0

    Offset:          120      121      122      123
    Record:           A        B        C        D

    Initial committed offset: 120
    poll() returns A, B, C, D
    Consumer position may be 124
    Listener processes B and fails

That the consumer position moved past multiple records does not mean A, B, C, or D have been processed or committed. After rollback, the container must handle unfinished records and ensure none are skipped. Depending on the version's mechanism, the container may seek back to a safe offset or retain remaining records for redelivery.

The committed offset is normally **the next offset to read**. If record at offset 120 completes, the corresponding committed value is 121. If record 120 fails and offset 121 has not safely committed, the next read must still be able to return to offset 120.

Looking only at consumer lag or poll position is insufficient to conclude a record finished processing. Distinguish actual business state from transaction offsets.

## 3. Atomicity of Kafka Transactions

A Kafka transaction can include:

1. Records sent by a transactional Kafka producer to one or more topics/partitions.
2. Consumer group offsets sent into the transaction.
3. The commit or abort decision on the broker.

When a transaction commits, Kafka guarantees atomicity for operations **within the scope of the Kafka transaction**. When a transaction aborts, output records from that transaction are not delivered to consumers configured with `isolation.level=read_committed`; offsets sent in that transaction are not committed either.

Example:

    Consume: orders.created-0@120
    Produce: orders.validated-2@X
    Send offset: orders.created-0 => 121

    Commit transaction:
      - Output becomes committed
      - Offset 121 becomes committed for the group

    Abort transaction:
      - Output is aborted
      - Offset 121 is not persisted from this transaction
      - Input remains eligible for redelivery

This supports **exactly-once semantics (EOS) in Kafka-to-Kafka flows** when prerequisites are met. It does **not** automatically make databases, HTTP APIs, emails, or payments outside Kafka part of the same transaction.

If a listener wrote to a database and then the Kafka transaction aborted, the database may still retain the change. When the input record is redelivered, the database side effect may run a second time without idempotency.

## 4. Why Does Spring Kafka Need AfterRollbackProcessor?

When a container uses Kafka transactions and a listener throws an exception, the container rolls back the transaction and then runs post-rollback processing. The **AfterRollbackProcessor** component decides how to reposition unprocessed records and, upon repeated failures, how to recover a problematic record.

The common implementation is **DefaultAfterRollbackProcessor**.

Diagram:

    poll() -> listener -> exception
                           |
                           v
                   Rollback Kafka TX
                           |
                           v
                 AfterRollbackProcessor
                           |
                +----------+-----------+
                |                      |
                v                      v
        Retries remaining        Recovery threshold reached
                |                      |
                v                      v
        Seek/reposition + backoff   Recoverer / DLT
                |                      |
                v                      v
          Next redelivery        Recovered offset policy

Typical responsibilities of `DefaultAfterRollbackProcessor`:

- Adjust consumption positions so the failing record and remaining unprocessed records can be redelivered.
- Apply `BackOff` to avoid tight retry loops.
- Track failure counts per record within the scope supported by the version.
- Upon reaching the retry limit, invoke a recoverer for a record that cannot be consumed normally.
- When properly configured, support committing the recovered record's offset in **a new Kafka transaction**.

**`AfterRollbackProcessor` is not the transaction manager itself.** The transaction manager commits/rolls back Kafka transactions; `AfterRollbackProcessor` manages re-reading/recovery progression after rollback occurs.

## 5. Differences from DefaultErrorHandler

Spring Kafka has two commonly confused mechanisms:

| Mechanism | Typical context | Role |
|---|---|---|
| `CommonErrorHandler` / `DefaultErrorHandler` | Listener containers not using Kafka transactions | Retries, seek/retention, recovery, and listener error handling |
| `AfterRollbackProcessor` / `DefaultAfterRollbackProcessor` | Listener containers using Kafka transactions when transactions roll back | Adjusts redelivery after rollback, applies backoff/recovery |
| `KafkaTransactionManager` | Kafka transactions | Starts, commits, or rolls back transactions per lifecycle |
| `DeadLetterPublishingRecoverer` | Recovery | Publishes failed records to a DLT; usable with error handlers or after-rollback processors |

For transactional listeners, Spring Kafka normally does not configure a default `CommonErrorHandler` in a way that swallows exceptions: exceptions must propagate so the container rolls back the transaction. If you register a custom `CommonErrorHandler`, check whether it is permitted to return normally.

**If a handler catches an exception and returns as if handled successfully, the container may treat the listener as successful and commit the transaction.** No rollback occurs, even though business processing failed. For errors requiring rollback, exceptions must be rethrown or handled via an explicit transactional policy.

Misleading example:

~~~java
@KafkaListener(topics = "orders.created", groupId = "billing")
public void consume(OrderCreated event) {
    try {
        billingService.bill(event);
    }
    catch (Exception exception) {
        log.error("Billing failed", exception);
        // Exception not thrown => container may treat processing as successful.
    }
}
~~~

If `bill()` fails yet the listener exits normally, you cannot expect the Kafka transaction to roll back automatically. Instead:

~~~java
@KafkaListener(topics = "orders.created", groupId = "billing")
public void consume(OrderCreated event) {
    try {
        billingService.bill(event);
    }
    catch (Exception exception) {
        log.error("Billing failed", exception);
        throw exception;
    }
}
~~~

In practice, preserve the original exception type or wrap with the root cause so `AfterRollbackProcessor` can classify the error and logs retain full context.

## 6. Configuring Transactions in Spring Kafka

A common Spring Boot setup enables transactional producers via a transaction-ID prefix and disables consumer auto-commit:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: order-service-tx-
      properties:
        acks: all
        enable.idempotence: true
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
    listener:
      ack-mode: record
~~~

Meaning:

- **transaction-id-prefix**: enables `ProducerFactory` to create transactional producers with distinct `transactional.id` values.
- **enable-auto-commit=false**: prevents offsets from auto-committing separately from business processing.
- **isolation.level=read_committed**: when consumers read transactional outputs, they see only data from committed transactions.
- **acks=all** and idempotence: strengthen producer durability; do not replace transactions.
- **ack-mode**: coordinates with how the listener container marks records processed; the transaction lifecycle decides when offsets actually commit.

In compatible Spring Boot versions, configuring a transaction-id prefix can trigger auto-configuration of `KafkaTransactionManager`. With application-defined factories, attach a Kafka-aware transaction manager properly to the listener container factory.

Conceptual explicit configuration example:

~~~java
@Bean
KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
        ProducerFactory<String, OrderEvent> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Then attach the transaction manager to the listener container factory using the API matching your project's Spring Kafka version. Setter names across versions may be `setTransactionManager` or `setKafkaAwareTransactionManager` on `ContainerProperties`; check your actual version.

Do not copy a configuration snippet from another version and assume listeners are running transactionally. Verify that the producer factory is transaction-capable, the listener container actually receives the transaction manager, and broker logs/metrics show transaction commits/aborts.

## 7. Consume-Process-Produce Example with Rollback

Suppose a listener reads an order event and emits a validated result:

~~~java
@Service
public class OrderValidationListener {

    private final KafkaTemplate<String, OrderValidated> kafkaTemplate;
    private final OrderValidator validator;

    public OrderValidationListener(
            KafkaTemplate<String, OrderValidated> kafkaTemplate,
            OrderValidator validator) {

        this.kafkaTemplate = kafkaTemplate;
        this.validator = validator;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-validation",
        containerFactory = "transactionalListenerFactory"
    )
    public void onOrder(ConsumerRecord<String, OrderCreated> record) {

        OrderCreated event = record.value();

        validator.validate(event); // May throw an exception.

        OrderValidated result = new OrderValidated(
            event.eventId(),
            event.orderId(),
            "VALID"
        );

        kafkaTemplate.send(
            "orders.validated",
            record.key(),
            result
        );
    }
}
~~~

This example assumes `transactionalListenerFactory` is configured to use `KafkaTransactionManager` and `KafkaTemplate` uses a transaction-capable `ProducerFactory`.

Possible outcomes:

- **Validation succeeds, Kafka send succeeds, transaction commits:** outputs commit and the input offset commits within the transaction.
- **Validation throws an exception:** container rolls back the transaction; input offset does not commit; record can be redelivered.
- **Kafka send fails asynchronously:** if the listener does not observe the error and transaction commit later handles it, the transaction can fail at commit time; monitor transaction exceptions rather than merely listener return.
- **Broker does not confirm commit:** actual state may be ambiguous from the client's perspective. On restart, rely on `eventId` and idempotency in case of redelivery.

Keep in mind that `KafkaTemplate.send()` may return a future before the broker finishes writing the record. Never equate a non-throwing `send()` call with the entire transaction having committed.

## 8. Rollback and Redelivery Timeline

Suppose the partition's initial committed offset is 50:

| Time | Action | Committed offset |
|---|---|---|
| T0 | Consumer polls record at offset 50 | 50 |
| T1 | Container starts Kafka transaction T1 | 50 |
| T2 | Listener sends output record | 50 |
| T3 | Listener throws exception | 50 |
| T4 | Container aborts T1 | 50 |
| T5 | `AfterRollbackProcessor` repositions and applies backoff | 50 |
| T6 | Record at offset 50 is redelivered | 50 |
| T7 | Listener succeeds inside T2 | 50 |
| T8 | Container sends offset 51 and commits T2 | 51 |

The listener may be invoked multiple times for the record, yet Kafka outputs aborted in T1 stay invisible to `read_committed` consumers. Once T2 commits successfully, the new output and offset 51 become committed.

If any consumer uses `isolation.level=read_uncommitted`, that consumer can see records from aborted transactions. Therefore, downstream consumers must configure `read_committed` whenever reading rolled-back outputs must be prevented.

## 9. Redelivery Differs from Business Duplicates

Two things can happen at the same time:

- Kafka redelivers the same record because the offset was not committed.
- The business system repeats a side effect because an operation outside the Kafka transaction succeeded before rollback.

Example:

    Listener receives PaymentRequested(evt-1)
       |
       v
    Calls paymentGateway.charge() -> succeeds
       |
       v
    KafkaTemplate.send("payment.completed") -> fails
       |
       v
    Kafka transaction rollback
       |
       v
    Redelivery PaymentRequested(evt-1)
       |
       v
    Call paymentGateway.charge() a second time?

A Kafka transaction cannot roll back `paymentGateway.charge()`. Without sending a stable **idempotency key**, a duplicate charge can occur.

Countermeasures:

1. Identify events with a unique, stable `eventId`.
2. For databases, record the `eventId` marker in the same database transaction as the side effect.
3. For HTTP APIs, pass an API-supported idempotency key.
4. For event-emitting producers, keep keys and `eventId` consistent across retries.
5. Never generate a fresh `eventId` when receiving the same Kafka record again.

The Inbox pattern or idempotent consumers are especially important for business logic with non-Kafka side effects.

## 10. Which Records Are Redelivered After Rollback?

A single poll typically returns multiple records. In a record listener, records preceding a failing record may already have been processed during the same poll cycle, yet offset durability depends on transaction boundaries.

Example:

    orders-0:
       offset 10 -> A
       offset 11 -> B
       offset 12 -> C
       offset 13 -> D

    poll() receives A, B, C, D
    Listener completes A
    Listener processes B -> exception

After rollback, B and unprocessed records C/D must not be skipped. Depending on transaction settings and container version, the processor seeks/repositions partitions to the appropriate offset so records requiring redelivery are read again.

Do not assert that in every scenario only B is redelivered. If A also belonged to the aborted transaction and A's offset had not committed, A may be reprocessed too. If each record committed in its own transaction prior to B, A does not need redelivery because B's rollback does not affect already committed transactions.

To reason accurately, inspect **transaction boundaries**, **ack mode**, **actual committed offsets**, and **processed records** rather than looking solely at poll results.

## 11. DefaultAfterRollbackProcessor and BackOff

`DefaultAfterRollbackProcessor` can use `BackOff` to delay the next redelivery of a failing record. For transient errors, a few retries may suffice for a dependency to recover.

Configuration example:

~~~java
@Bean
DefaultAfterRollbackProcessor<String, OrderCreated>
afterRollbackProcessor() {

    return new DefaultAfterRollbackProcessor<>(
        (record, exception) -> {
            log.error(
                "Record exhausted rollback retries: {}-{}@{}",
                record.topic(),
                record.partition(),
                record.offset(),
                exception
            );
        },
        new FixedBackOff(1_000L, 3L)
    );
}
~~~

The snippet uses a logging recoverer to illustrate the signature, **not safe production recovery**. If a recoverer only logs and then allows skipping the record, data can be lost from the business pipeline. For records that must be preserved, use `DeadLetterPublishingRecoverer` or a durable failed-record store.

If the listener container factory supports the corresponding setter, attach the processor to the factory:

~~~java
factory.setAfterRollbackProcessor(afterRollbackProcessor);
~~~

General workflow:

1. Listener throws an exception.
2. Current Kafka transaction rolls back.
3. Processor applies backoff, repositions offsets, or tracks attempts.
4. Record is redelivered on the next processing pass.
5. Once the retry threshold is reached, the configured recoverer is invoked.

Note that retry counts, how delivery attempts are tracked, and when the recoverer runs depend on `BackOff` settings and Spring Kafka version. Never rely on undocumented defaults without specifying them in configuration or integration tests.

## 12. Poison Pills and Infinite Rollback Loops

A **poison pill** is a record the listener cannot successfully process through simple retries: invalid JSON, business-rule violations, permanently missing references, or logic bugs.

If every retry rolls back and the record is never recovered, the consumer can get stuck:

    offset 80 -> invalid payload -> rollback
    offset 80 -> invalid payload -> rollback
    offset 80 -> invalid payload -> rollback
    ...

Consequences:

- Partition lag climbs.
- Subsequent records cannot be processed.
- CPU, log volume, and dependency calls can spike.
- Downstream dependencies are hammered pointlessly.
- When multiple partitions fail simultaneously, overall consumer group throughput degrades.

A production policy should classify failures:

| Error category | Retry? | Action after retries exhausted |
|---|---|---|
| Transient HTTP 503 | Yes, bounded | DLT or conditional recovery |
| Database deadlock | Yes, with backoff | DLT/alert if persistent |
| Permanent validation failure | Usually no or minimal | DLT for data repair |
| Structural deserialization error | Usually no | DLT preserving raw data if possible |
| Bad permissions/credentials | Avoid retry storms | Alert and pause/fix configuration |
| `NullPointerException` bug | Low limit | DLT, fix code, and re-drive |

With transaction rollbacks, design a durable **recover + commit offset** path. Simply logging errors and moving on can silently drop business work.

## 13. Recovery to DLT After Rollback

A common choice is `DeadLetterPublishingRecoverer`. After a record fails multiple times, the recoverer publishes it to a DLT along with source metadata and exception info.

Example recoverer setup for `AfterRollbackProcessor`:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
            recoverer,
            new FixedBackOff(1_000L, 3L)
        );

factory.setAfterRollbackProcessor(processor);
~~~

Assuming the source is `orders.created` partition 1, the DLT routes to `orders.created.DLT` partition 1 in this example. The DLT topic must exist with matching partitions, or the resolver must choose a valid target partition safely.

The DLT should store:

- Original key/value or recoverable payload.
- Source topic/partition/offset.
- Event ID, correlation ID.
- Exception class and failure details needed for investigation.
- Retry/recovery attempt state.

If the recoverer fails to publish to the DLT, do not mark the source offset as processed. Configure and test mechanisms to detect send failures, timeouts, broker availability, and recovery retries.

## 14. Committing the Recovered Record's Offset in a New Transaction

This is an especially important detail in **redelivery after rollback**.

Once the listener's transaction has aborted, the failing record's offset cannot be treated as committed merely because the recoverer ran. To both persist the record into the DLT and record that the source record was recovered, design a **new Kafka transaction** containing the appropriate operations.

Desired pattern:

    Transaction T1:
       Listener processes record 80
       Exception
       Abort T1

    Recovery transaction T2:
       Publish record 80 -> DLT
       Send source offset 81 to transaction
       Commit T2

When T2 commits successfully, `read_committed` consumers can see the DLT record, and the group can resume from offset 81. If T2 aborts, offset 81 is not committed by T2 and the DLT output is not committed either.

In supporting versions, `DefaultAfterRollbackProcessor` supports **commitRecovered** and `KafkaOperations`/`KafkaTemplate` to enlist the recovered offset into a new transaction. Configure the right `KafkaTemplate` and verify prerequisites regarding transactions, recoverers, listener containers, and version APIs.

Illustrative configuration direction:

~~~java
DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
            new DeadLetterPublishingRecoverer(dltKafkaTemplate),
            new FixedBackOff(1_000L, 3L)
        );

// Supporting versions allow enabling commit of recovered offsets.
processor.setCommitRecovered(true);

// Configure KafkaOperations/Template for the recovery transaction
// per the exact API of your running Spring Kafka version.
~~~

Calling `setCommitRecovered(true)` **alone is not enough** to assume DLT publishing and the recovered offset committed atomically. Verify the processor receives transaction-capable `KafkaOperations` and how the new transaction is managed. Setter or constructor signatures may vary across versions.

If the system fails to commit the recovered offset in an appropriate transaction, a record already sent to the DLT can reappear after restarts/rebalances. Conversely, committing the offset before the DLT write is durable risks losing the record from the recovery path.

## 15. Batch Listeners and Whole-Batch Rollback

With a batch listener, one invocation receives multiple records:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-batch-service",
    containerFactory = "transactionalBatchFactory"
)
public void onBatch(List<ConsumerRecord<String, OrderCreated>> batch) {

    for (ConsumerRecord<String, OrderCreated> record : batch) {
        orderService.process(record.value());
    }
}
~~~

If the fourth record fails after the first three were processed, the batch's Kafka transaction may roll back. When the entire batch shares one uncommitted transaction, Kafka outputs from the first three records abort as well; the required records can be redelivered.

Unlike record listeners, batch listeners do not always give the processor exact knowledge of which specific record failed. **An entire batch may be redelivered/retried**, depending on error handling and APIs.

Never assume `DefaultAfterRollbackProcessor` can skip a single poison record in every batch listener. Supporting versions handle this better when the listener throws `BatchListenerFailedException` with the appropriate record/index; still, batch recovery capabilities depend on Spring Kafka version and transaction semantics. Test your specific batch path.

If every record creates side effects outside Kafka, retrying an entire batch multiplies duplicate risk. Consider record listeners, idempotent writes, or workload partitioning to limit blast radius.

## 16. Redelivery, Seeking, and Partition Ordering

Kafka preserves record order within a partition. When a failing record is held for redelivery, trailing records in the same partition must typically wait so it is not skipped.

Example:

    orders-0:
       30: OrderCreated(A)  -> success
       31: OrderCreated(B)  -> error
       32: OrderCreated(C)  -> waiting
       33: OrderCreated(D)  -> waiting

If B undergoes blocking retries, C and D are delayed. Once B recovers to DLT and offsets are handled per policy, the container can proceed to C/D.

Distinguish the order in which records are **read from Kafka** from the order in which **business side effects execute**. If a listener dispatches work to an executor and returns immediately, the transaction may commit before the task finishes; ordering outside Kafka is no longer guaranteed merely because a topic has one partition.

For flows requiring strict per-key ordering, keep processing synchronous inside the listener or coordinate completion and acknowledgment per partition. Never mark a record succeeded just because a task was submitted.

## 17. Redelivery on Consumer Restart or Rebalance

Redelivery does not happen only after listener-thrown rollback exceptions. It can also happen after:

- A pod is killed mid-transaction.
- The JVM crashes after writing a database side effect yet before Kafka commit.
- A group rebalance moves the partition to another consumer.
- Flaky networking makes the transaction commit outcome ambiguous.
- A transactional producer is fenced or hits transaction timeout.
- A consumer fails before committing offsets.

On restart, the consumer group resumes from the latest committed offset, governed by `auto.offset.reset` if no committed offset exists or the old offset aged out of retention. Never use `auto.offset.reset=latest` as a "fix" for redelivery errors if doing so drops backlogged records.

A new consumer can receive a record whose side effects an old consumer already executed before the Kafka transaction committed. Therefore, idempotency must rely on `eventId` and durable state, not in-memory variables inside one pod's RAM.

## 18. ErrorHandlingDeserializer with Transactional Listeners

Deserialization errors can arise inside `consumer.poll()` before the listener is even called. If a deserializer throws directly, the listener never gets a chance to roll back according to its business logic.

Spring Kafka provides `ErrorHandlingDeserializer` to wrap deserialization error details into headers so the container/error handler can handle bad records according to policy.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
~~~

If a payload fails to parse into `OrderCreated`, the recoverer may need to send raw bytes to the DLT. The `KafkaTemplate` publishing to the DLT must have serializers suited to the actual payload type rather than assuming `OrderCreated`.

A malformed record usually cannot be fixed by rolling back and re-reading repeatedly. Bound retry counts, classify permanent errors, and preserve payloads for investigation or re-drive once schemas are fixed.

## 19. Kafka and Database Transactions Are Not Automatically Atomic

A consume-process-produce pattern may write to a database alongside sending Kafka output:

~~~java
@Transactional
public void updateOrder(OrderCreated event) {
    orderRepository.save(...);
    kafkaTemplate.send("orders.updated", event.orderId(), ...);
}
~~~

`@Transactional` can resolve to different transaction managers depending on application setup. Without explicitly knowing the transaction manager and coordination mechanism, you cannot conclude the database and Kafka will commit or roll back atomically together.

Even when ordering commits between database and Kafka, two independent systems still leave a failure window: the database commits successfully yet the Kafka commit fails. When the Kafka input is redelivered, the database may receive a duplicate operation.

Common solutions:

- **Idempotent consumer:** unique key on `eventId` inside the database transaction.
- **Transactional Inbox:** persist processed record markers inside the same database transaction.
- **Transactional Outbox:** persist output events in the database alongside business changes, then a separate publisher forwards events to Kafka.
- **Idempotent APIs:** pass idempotency keys to dependencies outside Kafka.

Kafka EOS shines when inputs, outputs, and offsets all reside in Kafka; for external side effects, add an appropriate consistency pattern.

## 20. Transaction Timeouts and Producer Fencing

A Kafka transaction must not be kept open too long. If a listener runs too slowly, the transaction can exceed broker or client timeouts.

Conditions to monitor:

- `transaction.timeout.ms` too short relative to processing duration.
- `max.poll.interval.ms` mismatched with batch processing time.
- Transactional producer fenced when another producer uses the same `transactional.id`.
- Broker failing to confirm commit/abort promptly.
- Application scaling or restarts where `transaction-id-prefix` fails to ensure distinct producer identities.

In these cases, the container may fail to commit the transaction, and input records may be redelivered. Never blindly retry all transaction errors with the same fenced producer; certain errors require recreating the producer/container per framework lifecycle.

When scaling an application, understand how Spring Kafka builds `transactional.id` from prefixes and caches producers. Never assign the exact same fixed `transactional.id` across multiple concurrently active application instances.

## 21. Blocking Retries vs Non-Blocking Retries with Transactions

Some systems use `@RetryableTopic` to route failing records to retry topics instead of holding the main partition in a retry loop. However, retry topics, listener transactions, and `AfterRollbackProcessor` have different boundaries.

| Strategy | Behavior on error | Considerations |
|---|---|---|
| `AfterRollbackProcessor` + `BackOff` | Transaction rolls back, record repositioned for redelivery | Blocks partition while waiting; bound retries |
| DLT recovery after rollback | After retries exhausted, sends to DLT and handles recovered offset | Requires durable/transactional recovery |
| `@RetryableTopic` | Forwards record to retry topic for later attempt | Can alter per-key ordering; transaction interaction depends on version |
| Pause consumer to fix dependency | Stops active consumption temporarily | Lag grows; requires controlled rollout and resume |

Do not blindly combine `@RetryableTopic` with transactional listeners assuming every retry-topic forward stays inside the same Kafka transaction. Check your Spring Kafka version's limitations and support, especially recoverer mechanics, container factories, and offset commits. Write integration tests for the exact intended path.

For workflows requiring strict ordering, short blocking retries followed by DLT recovery can be easier to reason about, accepting that poison records can delay other records on that partition.

## 22. Observing Redelivery in Production

To know whether rollback/redelivery is working properly, track Kafka transactions, consumers, and business metrics together.

**Transactions**

- Transaction commit/abort counts.
- Commit failure rates.
- Transaction durations and timeouts.
- Producer fencing or coordinator errors.
- DLT recovery transaction success/failure if applicable.

**Consumers**

- How often the listener receives the same topic-partition-offset.
- Retry/backoff counts and exception causes.
- Consumer lag by group/partition.
- Rebalance counts and rebalance durations.
- Time from poll to successful processing.

**Business**

- Successfully processed `eventId` counts.
- Duplicates caught by the idempotency layer.
- External side effect failures and retries.
- Records routed to DLT and records re-driven.
- Dependency recovery durations.

Logs should contain `eventId`, `groupId`, topic, partition, offset, exception class, attempt/recovery stage, and `correlationId`. Never log full sensitive payloads. Enable appropriate metrics/logs for transactions, and never infer broker state from a single "sent output" log emitted before transaction commit.

## 23. Testing Scenarios for Redelivery After Rollback

An integration test should use a real test-level broker (Embedded Kafka or Testcontainers), because transaction and offset semantics depend on the broker/coordinator rather than Java logic alone.

### 23.1. Listener error before sending output

1. Send a source record with a fixed `eventId`.
2. Configure the transactional listener to throw an exception on the first attempt.
3. Verify the transaction rolls back.
4. Verify the source offset did not commit from the failed attempt.
5. Let the listener succeed on the next attempt.
6. Verify committed output appears once to a `read_committed` consumer.
7. Verify the source offset advances past the record after the successful transaction.

### 23.2. Error after KafkaTemplate.send()

1. Listener sends an output record and then throws an exception before transaction commit.
2. Verify output from the aborted transaction is invisible to a `read_committed` consumer.
3. Verify the source record is redelivered.
4. Let the redelivered attempt succeed.
5. Verify final output and committed offset are consistent.

If a test uses a `read_uncommitted` consumer, it may observe aborted transaction outputs and draw false conclusions about EOS.

### 23.3. Database side effect succeeds then Kafka rolls back

1. Listener writes to the database and commits the change.
2. Then Kafka output fails or the transaction aborts.
3. Source record redelivers.
4. Listener calls the database again with the same `eventId`.
5. Verify unique constraints/inbox prevent a double update.
6. Verify the final Kafka output commits properly.

This test proves Kafka transactions do not protect side effects outside Kafka.

### 23.4. Poison record and DLT

1. Send a record that always throws a validation exception.
2. Configure a finite `BackOff`.
3. Observe redelivery counts.
4. Once retries are exhausted, verify the recoverer sends to the DLT.
5. If `commitRecovered` is configured, verify the source offset commits under the recovery transaction mechanism.
6. Make DLT publishing fail and verify the source record is not lost.
7. Re-drive the fixed record with the original `eventId` and verify idempotency.

### 23.5. Batch listeners and rebalances

1. Send multiple records in one poll.
2. Intentionally fail a record mid-batch.
3. Observe which records redeliver after rollback.
4. Stop a consumer or trigger a rebalance while a transaction is in flight.
5. Verify the new consumer resumes safely from the committed offset.
6. Verify no duplicate business side effects occur outside idempotency bounds.

These tests should capture offsets, transaction outcomes, DLT records, and side-effect invocation counts. Asserting only listener invocation counts is insufficient to prove semantics.

## 24. Incident Runbook for Repeated Rollbacks

When a consumer repeatedly receives the same offset:

1. **Identify key coordinates:** `groupId`, topic, partition, offset, `eventId`.
2. **Confirm the error:** exception from listener, deserializer, producer send, transaction commit, or fencing.
3. **Verify transaction state:** did the transaction actually abort, or did the listener swallow the error and commit?
4. **Check committed offset:** advancing or stuck; do not confuse with consumer position.
5. **Inspect `AfterRollbackProcessor`:** `BackOff`, retry limits, recoverer, and DLT.
6. **Check dependencies:** is a database/API timing out, rate limiting, or unavailable?
7. **Check side effects:** does idempotency need enabling or fixing before continuing retries?
8. **Check DLT:** topic/partition, serializers, publish permissions, and send outcomes.
9. **Check rebalances/transaction timeouts:** are they preventing retry loops from finishing?
10. **Controlled recovery:** fix dependencies/data/code, then re-drive or let consumers resume under monitoring.

Do not resolve incidents by manually bumping committed offsets to skip records without a business decision and a plan to preserve failed records. Improper seeking/committing can lose records needing processing.

## 25. Common Misconceptions

| Misconception | Risk | Correct understanding |
|---|---|---|
| Kafka rollback also rolls back the database | Duplicate database writes on redelivery | Databases lie outside Kafka transaction scope |
| Listener throws exception yet offset auto-commits anyway | Loss of state tracking | Check auto-commit, transactions, and handlers |
| Consumer position advanced means record finished | Skipping unprocessed records | Committed offset determines restart position |
| `KafkaTemplate.send()` without error means output committed | Output may still abort afterward | Transaction commit outcome decides |
| Every rollback redelivers strictly one record | Missing batch/co-transactional record replay | Depends on transaction boundary and processing mode |
| Publishing to DLT once means safe recovery | Possible DLT send failure or uncommitted offset | Requires recovery transaction and send error handling |
| Infinite retries are safe because no record is lost | Poison record blocks partition | Bound retries, use DLT, and alert |
| `read_uncommitted` also prevents seeing aborted outputs | Downstream reads rolled-back data | Use `read_committed` when those semantics are needed |
| Catching and logging an exception still triggers rollback | Container may treat processing as successful | Rethrow exception or mark rollback per design |
| Kafka EOS protects HTTP/email/payments too | Duplicate side effects outside Kafka | Use idempotency keys and complementary consistency patterns |

## 26. Design Principles

- Define the listener container's transaction boundary before reasoning about which records redeliver.
- Disable consumer auto-commit when offsets must participate in Kafka transactions.
- Use a transaction-capable producer/factory; never assume adding an annotation alone enables Kafka transactions.
- Ensure rollback-triggering errors escape the listener or follow the proper transaction contract.
- Understand that rollback leaves transaction offsets uncommitted, making records eligible for redelivery.
- Use `DefaultAfterRollbackProcessor` for redelivery/recovery in transactional containers.
- Bound `BackOff` and attempt counts; never trap poison records indefinitely.
- Use a durable DLT, classify exceptions, and handle recovery publish failures.
- For recovered records, coordinate a new Kafka transaction if DLT + source offset must commit atomically.
- Use `read_committed` on downstream consumers when aborted outputs must stay hidden.
- Keep `eventId` stable and side effects idempotent across databases, APIs, and non-Kafka systems.
- Evaluate batch listeners and rebalances separately because multiple records may redeliver.
- Configure timeouts, handle producer fencing, and use graceful shutdown.
- Monitor committed offsets, transaction aborts, redeliveries, DLT, and duplicates.
- Test rollbacks both before/after Kafka send, before commit, after non-Kafka side effects, and during rebalances.

**Redelivery after rollback** is a core part of transactional consumer reliability: when an attempt fails to complete a Kafka transaction, unconfirmed records still need a controlled path to reprocessing or recovery. Kafka-to-Kafka consistency is protected by transactions and atomic offset commits; business consistency is achieved only by combining backoff, DLT, idempotency, and operational observability.
