# EOS and batch listeners

## 1. What does EOS mean in Spring Kafka?

**Exactly-once semantics (EOS)** is an important Kafka reliability goal when an application both reads records and writes new Kafka records. Within Kafka's scope, transactions can coordinate **output records** with **consumer offsets** to ensure outputs and consumed positions are committed or aborted as a single unit.

When an application uses a **batch listener**, a single listener invocation receives multiple records. If the entire batch processes successfully, the container can commit Kafka outputs and input offsets in the same transaction. If one record in the batch fails and the exception escapes the listener, the transaction can abort; outputs from that transaction are invisible to `read_committed` consumers, and input offsets are not committed by the failed transaction.

Example:

~~~text
Topic: orders.created
          |
          v
Consumer poll -> [R0, R1, R2, R3]
          |
          v
Transactional batch listener
          |
          +-- transform R0 -> Output0
          +-- transform R1 -> Output1
          +-- transform R2 -> Output2
          +-- transform R3 -> Output3
          |
          v
Transaction:
    Kafka outputs + input offsets
          |
    +-----+------+
    |            |
  COMMIT       ABORT
    |            |
    v            v
 Output visible  Output not visible to read_committed
 Offset moves    Offset not committed by aborted transaction
~~~

A point to understand from the outset: **EOS does not mean every line of code in the listener runs only once**. When a transaction fails, the listener may have to reprocess the entire batch. EOS governs committed Kafka results; side effects to databases, HTTP APIs, emails, or payment systems still require idempotency or dedicated coordination mechanisms.

## 2. What is a batch listener?

Spring Kafka supports two common listener types:

- **Record listener:** the method is invoked for each individual record.
- **Batch listener:** the method receives a list of records from one poll or from a container-configured batching mechanism.

Batch listener example:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-transformers",
    containerFactory = "transactionalBatchFactory"
)
public void process(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        OrderValidated output = validator.validate(record.value());
        kafkaTemplate.send(
            "orders.validated",
            record.key(),
            output
        );
    }
}
~~~

In this example, the listener receives a list of records and produces one Kafka output per input. To achieve EOS, the requirement **is not merely having the method accept a `List`**: the listener container must be configured to start Kafka transactions, `KafkaTemplate` must join the active transaction, and the container must add input offsets to the same transaction.

### 2.1. One poll can span multiple partitions

Example:

~~~text
Index 0 -> partition 0, offset 20
Index 1 -> partition 0, offset 21
Index 2 -> partition 2, offset 40
Index 3 -> partition 2, offset 41
~~~

A batch does not necessarily belong to a single partition. Offsets must be managed separately per partition; there is no single arithmetic offset across the batch.

If all records in the example succeed, the transaction can contain the next offsets:

~~~text
partition 0 -> commit offset 22
partition 2 -> commit offset 42
~~~

**The committed offset is the next read position**, not the offset of the last processed record. Kafka transactions use per-partition offsets and consumer group metadata to coordinate commits at the right scope.

### 2.2. Batch size is not fixed

**max.poll.records** sets an upper bound on records returned per poll, without guaranteeing every poll returns that exact count. When a topic has little data, polls may return fewer records. When producers emit heavily, batches can be larger within the configured bound.

When concurrency creates multiple child consumers, each consumer manages its own poll batches and transactions; there is no single global transaction automatically spanning all consumers in the group.

## 3. What does EOS guarantee, and what does it not guarantee?

| Scope | Can Kafka EOS protect it? | Notes |
|---|---|---|
| Writing multiple Kafka records in one transaction | Yes | Committed or aborted per transaction |
| Coordinating Kafka outputs with input offsets in consume-transform-produce | Yes | Container and producer must be configured properly |
| Hiding aborted transaction records from downstream | Yes | Downstream uses `read_committed` |
| Preventing producer retries from duplicating output within idempotence bounds | Yes per Kafka semantics | Idempotent producer is the foundation of transactions |
| Preventing the listener method from being called again | No | Rollbacks or crashes can cause records to be redelivered |
| Atomic commits between Kafka and a database | Not automatically | A Kafka transaction is not a DB XA transaction |
| Atomic commits between Kafka and an HTTP API | No | APIs have separate lifecycles |
| Preventing emails or payments from executing twice | No | Requires idempotency keys or outbox/inbox |
| Guaranteeing multiple downstream services finish simultaneously | No | Each service has its own poll/processing schedule |

A more accurate statement is: **Kafka EOS can deliver an exactly-once outcome for a read from Kafka → compute → write to Kafka chain**, when output commits and input offsets are combined in the same transaction and downstream reads with `read_committed`. It does not eliminate reliability design at boundaries outside Kafka.

## 4. Components participating in a Kafka transaction

| Component | Role |
|---|---|
| `KafkaConsumer` | Reads input records and participates in the consumer group |
| Transactional `KafkaProducer` | Writes output records inside a transaction |
| `KafkaTemplate` | Spring abstraction for sending Kafka outputs |
| `ProducerFactory` | Creates transactional producers with `transactional.id` |
| `KafkaTransactionManager` or Kafka-aware transaction infrastructure | Coordinates transactions for producer/container |
| Kafka listener container | Begins transactions, invokes the batch listener, and adds offsets to the transaction |
| Transaction coordinator | Manages commit/abort state on the broker |
| Downstream `read_committed` consumer | Delivers only committed transactional records |

Calling **`KafkaTemplate.send()`** inside a listener does not automatically create EOS. Without an active Kafka transaction or if the wrong `ProducerFactory` is used, outputs will not be coordinated with input offsets.

For consume-transform-produce, the **listener container** must actively start the transaction before invoking the listener and finalize it after processing finishes.

## 5. Producer transactions and transactional.id

A transactional producer needs a **transactional.id** so Kafka can manage producer identity, epochs, and fencing. Spring Kafka usually takes a **transaction ID prefix** and generates distinct transactional IDs for factory-managed producers.

Example:

~~~text
transaction-id-prefix: orders-transformer-pod-a-tx-

Producer transaction IDs:
    orders-transformer-pod-a-tx-0
    orders-transformer-pod-a-tx-1
    orders-transformer-pod-a-tx-2
~~~

When two running producers share the same `transactional.id`, the newer producer can cause the older producer to be **fenced**. Therefore, multi-pod applications must use distinct prefixes or instance namespaces to prevent collisions across concurrent producers.

**ProducerFencedException** is not an exception to retry infinitely on the same fenced producer. When it occurs, inspect instance identities, transaction prefixes, and producer lifecycles.

### 5.1. Why must transactional.id be stable per instance?

A transaction ID should not be created fresh per event: doing so complicates producer management and observability. Yet you must not use one shared static ID across all running pods either.

A practical convention:

~~~text
<application>-<environment>-<instance>-tx-
~~~

Example:

~~~text
order-transformer-prod-pod-17-tx-
~~~

Deployment configurations must ensure instance IDs genuinely differ across active pods, especially during rolling updates.

## 6. Spring Boot configuration for EOS with batch listeners

A foundational configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    consumer:
      group-id: order-transformers
      enable-auto-commit: false
      isolation-level: read_committed
      max-poll-records: 100

    producer:
      transaction-id-prefix: order-transformer-pod-a-tx-
      acks: all
      properties:
        "[enable.idempotence]": true

    listener:
      type: batch
      ack-mode: batch
      concurrency: 2
~~~

Meaning of settings:

- **enable-auto-commit=false**: offsets are not auto-committed by the Kafka client independently of listener outcomes.
- **isolation-level=read_committed**: input consumer does not read aborted Kafka records from upstream transactional producers.
- **transaction-id-prefix**: establishes the foundation for a transactional `ProducerFactory`.
- **acks=all** and idempotence: support reliable producer writes; transactions require compatible producer settings.
- **listener.type=batch**: listener receives multiple records per invocation.
- **ack-mode=batch**: describes container policy for poll batches; **not a flag that turns on EOS by itself**.
- **concurrency=2**: enables parallel processing across child consumers on separate partitions.

This is a simple configuration example for one development instance. In production, never hardcode the same `transaction-id-prefix` across all replicas if it causes duplicate transactional IDs.

### 6.1. Transaction Manager is not implied by ack-mode

Enabling **ack-mode=batch** and **listener.type=batch** is not enough to give the container Kafka transactions. Ensure the listener container factory is actually configured with a Kafka-aware transaction manager or the matching transaction mechanism of your Spring Kafka version.

Spring Boot can auto-configure `KafkaTransactionManager` when a producer transaction prefix is declared and other conditions hold. However, a **custom listener factory** may not inherit this setup if the application builds its own factory without using Boot's configurer.

Therefore, when building EOS, verify which factory `@KafkaListener` uses, which `ProducerFactory`, which transaction manager, and which transaction `KafkaTemplate` joins.

## 7. Java example configuring a listener factory

In modern Spring Kafka versions providing Kafka-aware transaction manager APIs on container properties, configuration looks like this:

~~~java
@Configuration
public class KafkaBatchConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            transactionalBatchFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory,
                    KafkaTransactionManager<String, OrderValidated>
                        kafkaTransactionManager) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);

        factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);

        return factory;
    }
}
~~~

The example assumes `KafkaTransactionManager` is created from a transactional `ProducerFactory` and the `KafkaTemplate` sending outputs uses a compatible producer factory.

**Version note:** the API for attaching a transaction manager to container properties varies across Spring Kafka lines. Some versions use **setTransactionManager**, while newer versions use **setKafkaAwareTransactionManager**. Use the API of your actual dependency.

Never arbitrarily create a second `KafkaTransactionManager` and `ProducerFactory`: if `KafkaTemplate` uses a different `ProducerFactory` than the one managed by the transaction manager, outputs may not participate in the intended transaction.

### 7.1. Relationship between KafkaTemplate and producer factory

Example declaring a template backed by the same producer factory:

~~~java
@Bean
public KafkaTemplate<String, OrderValidated> kafkaTemplate(
        ProducerFactory<String, OrderValidated> producerFactory) {

    return new KafkaTemplate<>(producerFactory);
}
~~~

For simple Spring Boot applications, the auto-configured `KafkaTemplate` is usually enough. In systems with multiple producer factories across event types, explicitly specify which bean participates in which transaction.

## 8. Writing a transactional batch listener

An example service performing purely Kafka-to-Kafka work:

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
        groupId = "order-transformers",
        containerFactory = "transactionalBatchFactory"
    )
    public void process(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (ConsumerRecord<String, OrderCreated> record : records) {
            OrderValidated output =
                validator.validate(record.value());

            kafkaTemplate.send(
                "orders.validated",
                record.key(),
                output
            ).join();
        }
    }
}
~~~

Assumptions:

1. The batch listener factory genuinely opens a Kafka transaction before invoking the listener.
2. `KafkaTemplate` joins that transaction.
3. Producer sends use serializers compatible with `OrderValidated`.
4. The listener performs no non-Kafka side effects requiring atomicity.
5. Downstream consumers use `read_committed`.
6. Exceptions are not swallowed and treated as successful processing.

**join()** here surfaces send failures within the listener scope. If a send future fails, the exception propagates out and gives the container the chance to abort the transaction. If code merely logs errors asynchronously while returning normally, the transaction boundary can close inconsistently with business expectations.

### 8.1. Is @Transactional needed on the listener?

In a container-managed Kafka transaction model, you do not need to open a second Kafka transaction on the listener with `@Transactional`. The container manages transactions and consumer offsets.

Merely adding `@Transactional` does not replace configuring a transactional container. Conversely, adding `@Transactional` with a different transaction manager can introduce unnecessary complexity around transaction boundaries.

A practical rule: **pick one owner of the Kafka transaction boundary**, usually the listener container for consume-transform-produce.

## 9. Happy path: outputs and offsets commit together

Suppose a poll returns four records across two partitions:

~~~text
Input:
    P0 offset 8
    P0 offset 9
    P1 offset 20
    P1 offset 21
~~~

The listener generates four output records and finishes normally.

The container can send post-processing offsets into the transaction:

~~~text
Output topic orders.validated:
    V0, V1, V2, V3

Input offset commit:
    P0 -> 10
    P1 -> 22
~~~

The container then requests committing the Kafka transaction:

~~~text
Transaction T1
    |
    +-- output V0..V3
    +-- offset P0=10
    +-- offset P1=22
    |
    v
COMMIT
~~~

When the transaction commits successfully:

- `read_committed` downstream can receive V0..V3.
- The input consumer group can continue from offsets 10 and 22.
- If the consumer restarts, it does not need to re-read these records according to the transactionally committed offsets, barring intentional replays or group/offset changes.

This is the core link between EOS and batch listeners: **all Kafka outputs and input progress of the batch commit under a single Kafka transaction decision**.

## 10. Failure path: rolling back the entire batch

Suppose the listener processes:

~~~text
R0 -> emits V0 successfully
R1 -> emits V1 successfully
R2 -> validator throws exception
R3 -> not processed yet
~~~

If the exception propagates to the container, the transaction can abort:

~~~text
Transaction T1
    |
    +-- V0
    +-- V1
    +-- exception at R2
    |
    v
ABORT
    |
    +-- V0, V1 invisible to read_committed consumers
    +-- input offsets not committed in T1
    |
    v
Recovery / redelivery per transactional container
~~~

If the batch is redelivered, the listener can re-run R0 and R1, creating fresh outputs in transaction T2. Once T2 commits, `read_committed` downstream sees outputs from the successful transaction without seeing V0/V1 from the aborted transaction.

This is why EOS does not mean **the listener processes each record strictly once in RAM**.

### 10.1. Why shouldn't exceptions be swallowed?

A dangerous example:

~~~java
for (var record : records) {
    try {
        process(record);
    }
    catch (RuntimeException ex) {
        log.error("Cannot process record", ex);
        // Swallow the error and continue.
    }
}
~~~

If the listener finishes normally, the container may treat the batch as complete and commit offsets, even though one record failed to produce valid output.

If business logic allows skipping records, perform recovery or DLT routing **according to an explicit policy** before letting offsets advance. Logging an error is not proof of successful recovery.

## 11. A batch spanning multiple partitions: rollback consequences

One poll can include records from multiple partitions of the same consumer:

~~~text
Batch:
  index 0 -> P0/10
  index 1 -> P1/40
  index 2 -> P0/11   (error)
  index 3 -> P1/41
~~~

If the batch transaction aborts, the transaction's outputs and uncommitted offsets in that transaction are both affected.

Even record P1/40 that succeeded can be redelivered when the batch is reprocessed, depending on previously committed offsets and recovery behavior. Transactions do not provide an automatic "partial Kafka transaction commit for a few records inside the same transaction."

To isolate failures, use an error/recovery strategy with clear semantics; you cannot selectively commit part of an aborted transaction.

### 11.1. Why doesn't concurrency solve everything?

Increasing concurrency lets child consumers process different partitions in separate transactions. This limits blast radius across consumers, yet one consumer can still receive multiple partitions in the same poll.

Raising concurrency beyond useful partition counts adds no parallelism. Inspect assignments and hot partitions before scaling.

## 12. DefaultErrorHandler and AfterRollbackProcessor

This is an essential difference between regular error handling and transactional error handling.

**Non-transactional listener:** Spring Kafka typically uses **DefaultErrorHandler** to retry, seek, recover, and optionally coordinate commits for completed records.

**Transactional listener:** exceptions usually roll back the Kafka transaction. After rollback, the container uses an **AfterRollbackProcessor** to determine how to seek, redeliver, or recover, depending on version and configuration.

~~~text
Non-transactional batch listener
       |
       v
DefaultErrorHandler
       |
       +-- retry/seek/recover per policy

Transactional batch listener
       |
       v
Exception -> Kafka transaction ABORT
       |
       v
AfterRollbackProcessor
       |
       +-- seek/redeliver/recover per configuration
~~~

Do not apply a non-transactional `DefaultErrorHandler` example verbatim to a transactional listener without checking rollback policy. Using the wrong handler or misidentifying transaction boundaries can cause the app to misread which offsets committed and which records will redeliver.

### 12.1. Batch rollback and record-level recovery

With a batch listener, a generic exception does not tell the container which record failed. Therefore **the entire batch may be reprocessed**.

**BatchListenerFailedException** supplies the failing record's index and is commonly paired with `DefaultErrorHandler` in non-transactional batch handling. However, per-record recovery in transactional batch listeners depends on the Spring Kafka version and `AfterRollbackProcessor`; never assume throwing `BatchListenerFailedException` makes a transactional container commit records prior to the failure just like non-transactional mode.

When business logic requires partial recovery of transactional batches, check Javadoc/reference docs for your exact version and write integration tests with errors at the start, middle, and end of a batch.

### 12.2. Why do batch retries require idempotency?

Even though Kafka outputs from an aborted transaction are invisible to `read_committed`, the listener may already have:

- Written to a database.
- Called a REST API.
- Sent an email.
- Mutated an external cache.
- Emitted metrics, logs, or external audit entries.

These side effects are not rolled back by Kafka. When the batch redelivers, they can repeat. Thus, EOS designs must always state the **transaction boundary** and which actions are non-Kafka side effects.

## 13. Can BatchListenerFailedException replace Kafka transactions?

No. **BatchListenerFailedException** is error metadata, not a transaction manager.

It is useful when you know which record failed and want to report its index in the batch:

~~~java
for (int index = 0; index < records.size(); index++) {
    try {
        process(records.get(index));
    }
    catch (RuntimeException ex) {
        throw new BatchListenerFailedException(
            "Record failed",
            ex,
            index
        );
    }
}
~~~

With a non-transactional batch listener and suitable error handler, the failed index can help commit the successful prefix before the failure and redeliver the failing portion.

With a transactional batch listener, the exception still aborts the active transaction per semantics. Outputs from records before the failed index cannot be treated as committed if they belonged to an aborted transaction. Check how much `AfterRollbackProcessor`/recovery mode supports in your specific version.

## 14. DLT in transactional pipelines

A Dead-letter topic (DLT) stores unprocessable records so they do not block the main flow forever.

When a batch hits a poison record:

1. The container rolls back the transaction containing the failed batch's outputs.
2. Retry/redelivery occurs per `AfterRollbackProcessor`.
3. Once policy permits recovery, the failing record can be sent to the DLT.
4. The main flow should advance offsets only once recovery succeeds per policy.
5. Remaining records continue processing according to container semantics.

### 14.1. DLT and input offsets must coordinate safely

A major risk:

~~~text
Poison record at input offset 90
         |
         v
DLT publish fails
         |
         v
Input offset still commits 91
         |
         v
Failing record is skipped without being saved to DLT
~~~

In transactional pipelines, design how recovery outputs and input offsets coordinate. Depending on version and configuration, `AfterRollbackProcessor` can support executing recovery inside a new Kafka transaction so the DLT record and input offset commit safely.

Do not assume a `KafkaTemplate` sending to DLT outside transactions automatically achieves atomicity with input offsets. Verify exact configuration and test DLT broker/serializer/ACL failures.

### 14.2. Operational requirements for DLT

- DLT topic already exists with appropriate partition mapping.
- Recoverer uses a producer with serializers matching key/value types.
- Principal has `WRITE` permission on the DLT.
- Logs/metrics track recovery successes and failures.
- Sensitive payloads are protected by ACLs, retention, and encryption.
- A triage and replay procedure exists for DLT records.
- Replays must be idempotent or have deduplication.

A DLT is not a business success; it is a recovery state needing monitoring and follow-up handling.

## 15. EOS does not mean each record runs once

Distinguish three layers:

| Layer | Can events repeat? |
|---|---|
| Listener Java method invocation | Yes, after rollbacks, rebalances, or restarts |
| Kafka transactional output seen by `read_committed` downstream | Aborted outputs are withheld; committed outputs follow EOS within Kafka scope |
| DB/HTTP/email side effects from listener | Can repeat without idempotency |

Example:

~~~text
Batch T1:
  R0 -> DB update succeeds
  R1 -> HTTP request succeeds
  R2 -> error, Kafka transaction ABORTS

Retry batch T2:
  R0 -> DB update second time
  R1 -> HTTP request second time
  R2 -> succeeds this time
  Kafka transaction COMMITS
~~~

Kafka protects Kafka outputs, yet does not roll back DB updates or HTTP requests from T1. For the whole system to yield accurate business outcomes, idempotency or a specialized architecture is required.

## 16. Integrating databases via outbox/inbox

If a batch listener both writes to a DB and emits to Kafka, never assume Kafka transactions cover DB changes.

A common design is the **transactional outbox** when the database is the source of truth:

~~~text
Consumer receives OrderCreated
         |
         v
DB transaction:
   +-- update order state
   +-- write outbox event
         |
         v
      DB COMMIT
         |
         v
Outbox publisher
         |
         v
Kafka producer sends output
~~~

Outbox ensures DB updates and event-publishing intent are saved in the same DB transaction. However, the publisher may resend the same event after a crash, so downstream still needs idempotency.

The **inbox pattern** lets a consumer recognize already-processed events using a stable event ID and a unique constraint in the DB:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

On batch retries, if the event ID was already committed in the same DB transaction as the business side effect, the consumer can safely skip the duplicate.

Do not rely merely on checking **`existsById`** before inserting, as two consumers or concurrent threads can race. Database unique constraints are the critical concurrency guard.

## 17. Kafka transactions are not XA transactions

A misleading code snippet:

~~~java
@Transactional
public void processOrder(OrderCreated event) {
    orderRepository.save(...);
    kafkaTemplate.send("orders.validated", ...);
}
~~~

If `@Transactional` uses `JpaTransactionManager`, it manages the DB transaction, not the Kafka transaction. If it uses `KafkaTransactionManager`, the DB is still not part of an atomic transaction with Kafka.

Spring transaction synchronization can coordinate commit order between DB and Kafka in some setups, yet a failure window still exists:

~~~text
DB COMMIT succeeds
        |
        v
Kafka COMMIT fails
        |
        v
Business state changed
while Kafka output is uncommitted
~~~

Therefore, for workflows requiring DB-Kafka consistency, evaluate outbox, inbox, idempotent processing, or sagas/compensation. **Kafka EOS does not replace cross-system consistency design.**

## 18. read_committed and aborted records

To keep downstream from processing outputs of aborted transactions, configure:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

With `read_uncommitted`, consumers can see uncommitted or aborted transactional records, defeating transactions for downstream processing.

### 18.1. Last Stable Offset

A `read_committed` consumer can be bounded by the **Last Stable Offset (LSO)** when unresolved open transactions exist. This means records behind an open transaction may not be delivered yet, even if the broker already stored many newer records.

An overly long open transaction can increase `read_committed` consumer lag. When diagnosing slow consumers, inspect transaction duration, the transaction coordinator, and LSO.

## 19. Batch size, max.poll.interval.ms, and transaction timeouts

Large batches take longer to process. When the container holds a Kafka transaction open across the listener invocation, batch processing time affects both consumer liveness and transaction lifetime.

Key limits:

| Setting | Impact |
|---|---|
| `max.poll.records` | Maximum records returned per poll |
| `max.poll.interval.ms` | Maximum time between valid polls |
| `transaction.timeout.ms` | Producer/broker transaction duration limit |
| `delivery.timeout.ms` | Producer total delivery time limit |
| `request.timeout.ms` | Request/response wait limit |
| `concurrency` | Child consumers processing partitions in parallel |
| `max.partition.fetch.bytes` | Per-partition fetch byte limit |

If batch processing runs too long:

- Transactions time out and abort.
- Consumers exceed the poll interval, leave the group, or trigger rebalances.
- Subsequent records get blocked behind open transactions.
- The Kafka transaction coordinator and producer cache carry extra load.
- Retries further extend batch processing times.

### 19.1. Processing time example

Suppose each record takes 20 ms to transform:

~~~text
100 records x 20 ms = 2,000 ms = 2 seconds
500 records x 20 ms = 10,000 ms = 10 seconds
~~~

If a batch also waits 15 seconds on a downstream call or retries three times, transaction duration can exceed expectations. Measure p95/p99 rather than only averages.

Do not raise `transaction.timeout.ms` or `max.poll.interval.ms` indefinitely to mask a congested downstream. Put timeouts on I/O, cap batch sizes, use suitable backoff, and minimize non-Kafka work inside transactions.

### 19.2. Should you use batch listeners with EOS?

Batch listeners remain a good fit when they reduce processing overhead or bulk-transform records efficiently. However, if batches are long, hold hard-to-make-idempotent side effects, or encounter frequent poison records, record listeners are sometimes easier to operate.

There is no rule that "EOS requires batch listeners" or "batch listeners cannot use EOS." Choose based on throughput, transaction duration, fault isolation, and ordering needs.

## 20. Concurrency and transaction distribution

Suppose topic `orders.created` has 12 partitions, the app runs two pods, each with `concurrency=3`:

~~~text
Pod A:
  consumer A1 -> separate batch / transaction
  consumer A2 -> separate batch / transaction
  consumer A3 -> separate batch / transaction

Pod B:
  consumer B1 -> separate batch / transaction
  consumer B2 -> separate batch / transaction
  consumer B3 -> separate batch / transaction

Total 6 consumers splitting 12 partitions
~~~

Each consumer has its own poll loop and transaction boundary; no single Kafka transaction spans across pods.

If one consumer fails a batch and its transaction aborts, other consumers can continue processing their assigned partitions. However, rebalances or broker outages can still impact multiple consumers in the group.

When scaling:

- Compute total consumers = replicas × concurrency.
- Compare against useful partition counts.
- Ensure producer transactional IDs do not collide.
- Check producer caches and transaction coordinator capacity.
- Measure per-partition consumer lag and transaction commit latency.
- Avoid scaling concurrency past downstream capacity.

## 21. Ordering in EOS batches

Kafka preserves ordering per partition. A batch with records from multiple partitions has no reliable global order across all records in the batch.

If events with the same `orderId` must process in order:

1. Producers use a stable key, typically `orderId`.
2. Partitioners route related events to the same partition.
3. Consumers process records in order per partition.
4. Avoid parallel executors that reorder side effects when business logic requires ordering.
5. During retries/rollbacks, ensure later records do not overtake failing records uncontrollably.

EOS does not automatically fix ordering bugs caused by asynchronous application processing. Kafka transactions assist output/offset commits, yet do not build a system-wide sequential queue across multiple partitions.

## 22. Error handling: retries, poison records, and backoff

A batch can fail due to:

- Transient errors: DB timeouts, HTTP 503s, flaky broker/network.
- Deterministic errors: JSON/schema mismatches, validation failures.
- Producer errors: serialization failures, missing ACLs, transaction timeouts.
- Environment errors: fenced producers, unavailable coordinators.
- Business errors: violated domain invariants.

Handling must classify errors:

| Error category | Strategy |
|---|---|
| Transient dependency failure | Bounded retries with appropriate backoff |
| Invalid payload/schema | Recovery/DLT, do not retry infinitely |
| `ProducerFencedException` | Recreate valid producer, inspect transactional ID collisions |
| Transaction timeout | Reduce transaction duration or adjust policies |
| DLT publish failure | Never treat recovery as succeeded until confirmed |
| Business invariant failure | Domain policy, potentially DLT or manual handling |

With transactional listeners, configure **`AfterRollbackProcessor`** and recovery policies compatible with your version. Never treat non-transactional `DefaultErrorHandler` as the default fix for every error.

### 22.1. Poison records and blocking transactions

A single poison record can cause a batch to roll back continuously, forcing many valid records to reprocess too. Cap retries, use a DLT, and alert on backlogs. Never let one bad record wedge a partition forever if business policy permits isolating it.

## 23. Impact on metrics and observability

Observing send success alone is insufficient. Distinguish **batch invocations**, **Kafka transaction outcomes**, and **business side-effect outcomes**.

| Metric/signal | Meaning |
|---|---|
| Transaction commit rate | Kafka transaction commits over time |
| Transaction abort rate | Transaction rollbacks/aborts |
| Transaction duration p95/p99 | Transaction open duration, detecting long transactions |
| Batch size | Distribution of records per poll/listener invocation |
| Batch processing time | Time spent processing batches |
| Consumer lag by partition | Which partition is slow or stuck on a poison record |
| Rebalance count | Whether the group is destabilized by slow processing |
| Producer fencing errors | Whether transactional ID collisions occur |
| Producer send failures | Serializer, network, ACL, or broker errors |
| `AfterRollbackProcessor` recovery | Whether retries/recoveries succeed |
| DLT ingress/failures | Whether bad records are safely isolated |
| `read_committed` lag / LSO | Whether open transactions are stalling downstream |
| Duplicate external side effects | Whether idempotency is preventing DB/HTTP repeats |

Metric names depend on Kafka client, Spring Kafka, Micrometer, JMX exporters, and existing instrumentation. Metrics like "business side effect completed" must be recorded by the application.

### 23.1. Structured logs

Example:

~~~text
listener=orders-batch
groupId=order-transformers
topic=orders.created
batchSize=74
transactionOutcome=aborted
exceptionClass=InvalidOrderException
transactionDurationMs=950
action=rollback
~~~

Never put event IDs, order IDs, or dynamically generated transactional IDs into high-cardinality metric labels. Those IDs belong in controlled logs/traces.

### 23.2. Distinguishing send acknowledged from transaction committed

When a `KafkaTemplate.send` future completes successfully, the broker acknowledged writing the record per producer delivery settings, yet the transaction can still abort afterward. Dashboards counting only send successes can overreport "successful events."

Instrument transaction commits/aborts at the proper boundary and watch `read_committed` downstream to confirm committed outputs.

## 24. EOS test scenarios with batch listeners

A good integration test should use Embedded Kafka or Testcontainers with a broker supporting Kafka transactions.

### 24.1. Successful batch test

1. Configure transactional `ProducerFactory`, `KafkaTemplate`, and batch listener container.
2. Send four input records to the topic.
3. Listener transforms and sends four outputs.
4. Wait for the transaction to commit.
5. `read_committed` consumer reads outputs.
6. Verify corresponding outputs are committed.
7. Verify input group offsets advance past the batch.

### 24.2. Mid-batch failure test

1. Send a batch with R0, R1, R2, R3.
2. Have R2 throw an exception.
3. Verify the transaction aborts.
4. `read_committed` consumer receives no outputs from the aborted transaction.
5. Verify input offsets were not committed by the failed transaction.
6. Verify retries/redelivery per the actual `AfterRollbackProcessor`.
7. After removing the error, verify the output transaction succeeds and offsets advance.
8. Compare listener invocation counts with committed output counts; they can differ.

### 24.3. Crash and restart test

- Crash the process after `KafkaTemplate` sends outputs but before transaction commit.
- Restart the consumer group under the right transactional ID policy.
- Verify the aborted transaction produces no output readable under `read_committed`.
- Verify input records are reprocessed when offsets were uncommitted.
- Verify a new transaction can complete.

### 24.4. Non-Kafka side-effect test

- Listener writes to a DB before Kafka transaction commit.
- Intentionally trigger a Kafka rollback.
- Verify the DB side effect can persist if the DB transaction committed.
- Prove inbox/idempotency stops replay from creating a second side effect.

### 24.5. DLT and recovery failure test

- Send an unprocessable poison record.
- Cap retries and trigger recovery.
- Verify DLT publish succeeds before allowing offsets to advance per policy.
- Induce a serializer/ACL failure on the DLT publisher.
- Verify the record is not "silently lost" when recovery fails.

## 25. End-to-end example: Batch Order Validation

Suppose an Order Validation service reads **orders.created**, validates schemas and business rules, and sends **orders.validated**. This is a Kafka-to-Kafka pipeline with no DB writes.

A batch contains:

~~~text
R0: order-100 -> valid
R1: order-101 -> valid
R2: order-102 -> valid
R3: order-103 -> valid
~~~

The listener transforms four events and sends four outputs inside the container-managed transaction. Once the method finishes, the container places input offsets into the transaction and commits.

If the batch contains an invalid event:

~~~text
R0: order-100 -> valid
R1: order-101 -> valid
R2: order-102 -> invalid
R3: order-103 -> not reached
~~~

The listener throws an exception and the transaction aborts. Kafka outputs for R0/R1 from the aborted transaction are never received by `read_committed` downstream. Afterward, `AfterRollbackProcessor` governs redelivery/recovery.

If after a retry the code fix or payload becomes valid under new conditions, the next transaction can commit outputs. If the record is permanently invalid, error policies must prevent infinite retries and route to a DLT cleanly.

Key takeaways from the example:

- **Kafka EOS:** Kafka outputs and input offsets commit atomically in a successful transaction.
- **Batch rollback:** the listener may be re-invoked for records preceding the error.
- **Read committed:** downstream does not read outputs from aborted transactions.
- **DLT:** policies must isolate poison records without committing wrongly.
- **External side effects:** if DB/HTTP actions are added to the listener, idempotency or outbox/inbox is required.

## 26. Runbook when an EOS batch listener has an incident

1. Identify listener ID, consumer group, topic, and lagging partitions.
2. Verify the listener container actually has a Kafka transaction manager.
3. Verify `KafkaTemplate` uses the transactional `ProducerFactory` joining that transaction.
4. Check producer transaction ID prefixes and instance uniqueness.
5. Inspect transaction commit/abort counts and transaction durations.
6. Identify the root exception: business, serializer, network, ACL, or fencing.
7. Check `AfterRollbackProcessor`, retry policies, and redelivery behavior.
8. For poison records, check whether DLT and recovery policies preserve data.
9. Verify input offsets advance only after valid commits.
10. Verify downstream uses `read_committed`.
11. Inspect LSO/open transactions if downstream lag looks abnormal.
12. If DB/HTTP side effects exist, check duplicate detection and idempotency.
13. Review `max.poll.records`, `max.poll.interval.ms`, and `transaction.timeout.ms`.
14. Re-test commit/abort behavior after configuration changes.
15. Document root cause, impact, recovery outcome, and preventive measures.

## 27. Common mistakes

**"Using a batch listener gives EOS."** False. You need transactional producers/containers and offset coordination.

**"Enabling `ack-mode=batch` enables transactions."** False. `AckMode` is an acknowledgment policy, not a substitute for `KafkaTransactionManager`.

**"`KafkaTemplate.send` succeeded means the batch committed."** False. Send acknowledgments arrive before transaction commit outcomes.

**"When R2 fails, outputs R0 and R1 are definitely kept."** If they sit inside an aborted transaction, `read_committed` consumers never receive them.

**"EOS means the listener runs once."** Rollbacks can cause the same inputs to be reprocessed.

**"`BatchListenerFailedException` always enables partial commits in transactions."** Batch recovery capabilities depend on version/`AfterRollbackProcessor`; you cannot partially commit an aborted transaction.

**"Non-transactional `DefaultErrorHandler` behaves identically in transactional listeners."** Transaction rollbacks have their own `AfterRollbackProcessor` mechanism.

**"Kafka can roll back DB or HTTP calls."** False. Side effects outside Kafka require outbox/inbox or idempotency.

**"Default consumers hide aborted transactional records."** Never assume; configure `read_committed` explicitly when required.

**"Raising `max.poll.records` always improves throughput."** Oversized batches can cause transaction timeouts and lengthen rollbacks.

**"Multiple pods using the same transactional ID are fine."** That causes producer fencing and prolonged errors.

**"Failing DLT publish while committing the offset is safe."** That can skip records without any recovery evidence.

## 28. Takeaways

**EOS and batch listeners** in Spring Kafka mean combining batch processing with Kafka transactions so **Kafka outputs and input offsets commit or abort together**. Achieving that requires a transactional `ProducerFactory`, a `KafkaTemplate` participating in the listener container's transaction, proper consumer group configuration, and `read_committed` downstream.

When a batch fails, the entire transaction can abort and the batch can be redelivered. Kafka outputs from aborted transactions are not processed by `read_committed` consumers, yet the listener method and non-Kafka side effects can still execute repeatedly. Therefore, EOS does not replace idempotency, outbox/inbox, or recovery policies.

A reliable system controls transaction durations, partition assignments, rollback/retry via `AfterRollbackProcessor`, DLTs, transactional ID fencing, input offset commits, and crash scenarios. Prove guarantees with integration tests covering commits, aborts, replays, and recovery failures before applying them in production.
