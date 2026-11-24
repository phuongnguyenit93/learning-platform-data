# Consumer-Initiated Transactions

In Spring Kafka, a **consumer-initiated transaction** is the pattern where **the Kafka listener container starts a Kafka transaction before invoking the business listener**. The listener reads a record from one topic, processes the data, and sends results to another topic via `KafkaTemplate`. Once the listener succeeds, the container includes the **consumed offsets** in the same transaction as the output records and commits. If the listener fails, the transaction rolls back: Kafka outputs from the transaction never become committed, and the source offset is not committed on that attempt.

This is the foundation of atomic **consume → process → produce** flows within Kafka's scope. Consumer-initiated transactions prevent situations where outputs are persisted while source offsets are uncommitted, or offsets advance without outputs being written. However, it does not mean the listener executes strictly once, and **it does not automatically extend transactions to databases, REST APIs, or systems outside Kafka**.

## 1. The Problem When Consuming and Producing

Suppose an application reads events from `orders.created`, normalizes payloads, and sends new events to `orders.normalized`.

~~~text
orders.created
       |
       v
Spring Kafka @KafkaListener
       |
       +-- validate
       +-- transform
       +-- enrich
       |
       v
orders.normalized
~~~

Without Kafka transactions, these two actions are usually independent:

1. Produce the event to `orders.normalized`.
2. Commit the consumer group offset on `orders.created`.

If the system crashes between the two actions, the following can happen:

| Scenario | Output | Input offset | Consequence |
|---|---|---|---|
| Crash before produce | Not written | Uncommitted | Input can be read again |
| Produce succeeds then crash before offset commit | Written | Uncommitted | Input can be read again and create duplicate output |
| Commit offset too early then produce fails | Not written | Committed | Risk of losing business output |

Consumer-initiated transactions solve this within Kafka by committing **output records and consumed offsets in the same transaction**. When a transaction aborts, its records are invisible to `read_committed` consumers and the source offset does not advance due to the failed transaction.

## 2. Who Actually Initiates the Transaction?

The term consumer-initiated can be misleading, as if `KafkaConsumer` directly called `beginTransaction()`. In reality, **Kafka transactions are provided by `KafkaProducer`**. Spring Kafka's listener container uses a transaction manager and a transactional producer to create the transaction while processing a consumed record.

~~~text
KafkaConsumer.poll()
       |
       v
KafkaMessageListenerContainer
       |
       +-- begin Kafka transaction
       |
       v
Business @KafkaListener
       |
       +-- KafkaTemplate.send(...)
       |
       v
Container sendOffsetsToTransaction(...)
       |
       v
Kafka transaction commit / abort
~~~

Participating components include:

- **ConsumerFactory** creates the `KafkaConsumer` reading the source topic.
- **Listener container** manages the poll loop, listener callbacks, partition assignments, and transaction boundaries.
- **Transactional ProducerFactory** creates `KafkaProducer` instances with `transactional.id`.
- **KafkaTransactionManager** (or `KafkaAwareTransactionManager` depending on Spring Kafka version) manages the transaction.
- **KafkaTemplate** uses the producer belonging to the active transaction to send outputs.
- **AfterRollbackProcessor** decides how to retry or recover when a transaction rolls back.

The container manages the transaction lifecycle; business listeners do not manually call `producer.beginTransaction()`, `producer.sendOffsetsToTransaction()`, and `producer.commitTransaction()`.

## 3. Success Flow: Output and Offset Commit Together

Suppose consumer group `orders-transformer` receives a record on `orders.created`, partition 2, offset 51:

~~~text
Topic:     orders.created
Partition: 2
Offset:    51
Key:       order-1001
~~~

General processing sequence:

1. Consumer polls and receives the record.
2. Listener container begins a Kafka transaction.
3. Listener transforms `OrderCreated` into `NormalizedOrder`.
4. `KafkaTemplate` sends `NormalizedOrder` to `orders.normalized` within this transaction.
5. Listener returns successfully.
6. Container sends the consumer group's consumed offset into the transaction via `sendOffsetsToTransaction`.
7. Container commits the transaction.
8. Kafka accepts the output record and source offset together.

~~~text
BEGIN TRANSACTION T1
    |
    +-- input: orders.created / P2 / offset 51
    |
    +-- output: orders.normalized / key order-1001
    |
    +-- sendOffsetsToTransaction:
    |       group orders-transformer
    |       orders.created / P2 -> 52
    |
COMMIT T1
    |
    +-- output committed
    +-- input offset 52 committed
~~~

**Why commit offset 52 instead of 51?** Kafka stores the committed offset as the next position the consumer group should read. Once the record at offset 51 finishes processing successfully, the next position is typically 52. This is not the record's original offset; the original offset remains 51.

With batch listeners, the container can manage a transaction for the entire batch as configured. Never assume every poll always equals one transaction: boundaries depend on whether the listener is record- or batch-based and on the container version.

## 4. Failure Flow: Transaction Abort and Retry

Suppose the listener sends a Kafka output and then throws an exception:

~~~text
BEGIN TRANSACTION T1
    |
    +-- consume orders.created/P2@51
    +-- produce orders.normalized (not yet committed)
    +-- exception from listener
    |
ABORT TRANSACTION T1
    |
    +-- T1 output is aborted
    +-- consumed offset not committed by T1
    |
    v
AfterRollbackProcessor
    |
    +-- seek/coordinate unfinished records
    +-- backoff and retry
    +-- or recover when retries exhausted
~~~

When the container aborts, downstream consumers with `isolation.level=read_committed` will not see outputs from T1. Since the source offset was not committed by T1, the source record remains eligible for reprocessing.

In a new attempt T2, the listener can reprocess the same record:

~~~text
T1: read offset 51 -> send output X -> error -> ABORT
T2: read offset 51 -> send output X -> succeed -> COMMIT

Downstream read_committed:
  sees only output X of the committed transaction
~~~

**Core point:** transactions protect **committed Kafka outcomes**, not against listener code executing multiple times. If the listener called an external API or wrote to a database before aborting, that side effect may still persist.

## 5. Producer-Initiated vs Consumer-Initiated

| Criterion | Producer-initiated transaction | Consumer-initiated transaction |
|---|---|---|
| Starting point | Service method or producer operation | Kafka listener container |
| Trigger | HTTP request, scheduler, command | Kafka consumer receiving records |
| Output | Multiple Kafka records in transaction | Kafka records produced by listener |
| Consumed offset | Not necessarily involved | Enlisted into transaction by container |
| Goal | Send multiple records atomically | Atomic consume-process-produce in Kafka |
| Error handling | Service-managed transaction rollback | Container rollback, `AfterRollbackProcessor` handles record |

With consumer-initiated transactions, do not slap `@Transactional` onto every `@KafkaListener` just to get Kafka transactions. When the container already has a transaction manager attached, the container itself creates the transaction before calling the listener.

If the application needs database and Kafka transactions simultaneously, two different transaction managers do not automatically merge into one atomic distributed transaction.

## 6. What Do Kafka Transactions Require?

A reliable transactional setup requires aligning several components:

- `ProducerFactory` supports transactions and has a `transactionIdPrefix`.
- `KafkaTransactionManager` uses the same `ProducerFactory` as `KafkaTemplate`.
- Listener container is configured with the transaction manager.
- Consumer disables auto-commit; the container sends offsets via the transaction instead of committing separately.
- Listeners do not swallow exceptions needing rollback.
- Downstream consumers use `read_committed` if aborted transaction outputs must be excluded.
- Kafka cluster supports transactions with appropriate broker/transaction coordinator and replication settings.

~~~text
Transactional ProducerFactory
          |
          +--------> KafkaTransactionManager
          |                    |
          v                    v
     KafkaTemplate      Listener container
          |                    |
          +----- transaction --+
                               |
                          @KafkaListener
~~~

`KafkaTemplate` participates in the transaction through the matching transaction context; simply having a `KafkaTransactionManager` bean in Spring's `ApplicationContext` **does not prove** every listener runs transactionally.

## 7. Spring Boot Configuration

Example Kafka-to-Kafka application processing `OrderCreated`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-transformer-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[acks]": all
    consumer:
      group-id: orders-transformer
      enable-auto-commit: false
      isolation-level: read_committed
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.orders.OrderCreated
        "[spring.json.trusted.packages]": com.example.orders
    listener:
      ack-mode: record
~~~

Key settings:

- **transaction-id-prefix**: enables a transactional producer factory; the framework generates distinct `transactional.id` values for transactional producers.
- **enable-auto-commit: false**: prevents the consumer from recording offsets independently of the container's transaction.
- **isolation-level: read_committed**: prevents the consumer from receiving aborted transactional records from the source topic.
- **acks=all**: requests acknowledgments matching durability requirements; transactions have additional broker and transaction coordinator prerequisites.
- **ack-mode**: coordinates with the container; in transactional listeners, offsets enter the transaction per container semantics.

The `transaction-id-prefix` in this example suits only a single test instance. **Production must ensure concurrently running instances never generate duplicate `transactional.id` values.** You can derive the prefix from a unique instance ID provided by Kubernetes, the deployment platform, or environment config.

In a suitable Spring Boot app, declaring `producer.transaction-id-prefix` can trigger `KafkaTransactionManager` auto-configuration. If your app has multiple `ProducerFactory`, `KafkaTemplate`, or transaction manager beans, wire them explicitly and verify the listener container actually uses the intended manager.

## 8. Explicit Configuration of Transaction Manager and Listener Container

To avoid relying entirely on auto-configuration, you can declare the transaction manager from the transactional `ProducerFactory`:

~~~java
@Bean
KafkaTransactionManager<String, NormalizedOrder>
        kafkaTransactionManager(
                ProducerFactory<String, NormalizedOrder> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Then attach the manager to the listener factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        transactionalListenerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                KafkaTransactionManager<String, NormalizedOrder> kafkaTxManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTxManager);
    return factory;
}
~~~

This example follows the Spring Kafka API featuring **setKafkaAwareTransactionManager**; in older versions, the type or setter may differ. Use the exact API of your project's Spring Kafka version. Avoid defining a second `KafkaTransactionManager` bean unintentionally if Spring Boot already auto-configures an equivalent one.

`ProducerFactory` must already have **transactionIdPrefix**. Creating `KafkaTransactionManager` over a non-transactional producer factory is not enough. `KafkaTemplate` must use the same `ProducerFactory` or compatible transaction infrastructure.

Example:

~~~java
@Bean
KafkaTemplate<String, NormalizedOrder> normalizedOrderKafkaTemplate(
        ProducerFactory<String, NormalizedOrder> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
~~~

In a real deployment, `ProducerFactory` requires matching serializers, security, bootstrap servers, and transaction ID prefix. The listener's container factory must be referenced accurately on `@KafkaListener`.

## 9. Writing a Consume-Process-Produce Listener

Example listener reading `orders.created` and sending to `orders.normalized`:

~~~java
@Service
public class OrderTransformerListener {

    private final OrderMapper mapper;
    private final KafkaTemplate<String, NormalizedOrder> kafkaTemplate;

    public OrderTransformerListener(
            OrderMapper mapper,
            KafkaTemplate<String, NormalizedOrder> kafkaTemplate) {
        this.mapper = mapper;
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-transformer",
            containerFactory = "transactionalListenerFactory")
    public void handle(ConsumerRecord<String, OrderCreated> record) {
        NormalizedOrder normalized = mapper.normalize(record.value());

        kafkaTemplate.send(
                "orders.normalized",
                record.key(),
                normalized
        ).join();
    }
}
~~~

`join()` waits for the Kafka send `CompletableFuture` to finish and ensures send failures surface as exceptions before the listener returns. When an error escapes, the container can roll back the transaction. Never ignore failed futures and return normally as if output had been sent successfully.

In a throughput-optimized system, the app can collect futures and await them all before returning rather than joining each send individually. Still, ensure **all required outputs were accepted properly within the transaction** and errors are handled before the container commits.

Never call `KafkaTemplate.executeInTransaction()` inside the listener to start an **independent** producer transaction if your goal is grouping outputs with container-managed consumed offsets. A separate transaction could commit outputs independently, breaking the intended atomicity.

## 10. How Does sendOffsetsToTransaction Work?

When the listener completes successfully, Spring Kafka passes consumed offsets into the producer's transaction. For a record at offset 51:

~~~text
orders.created / partition 2

offset 50: processed
offset 51: processing
offset 52: next read position

Transactional offset commit:
  group orders-transformer
  orders.created/P2 = 52
~~~

The container uses group membership information and corresponding Kafka APIs to send offsets into the transaction. This is not an independent `consumer.commitSync()`.

If the transaction aborts, offset 52 is not committed from that failed transaction. If the transaction commits successfully, the source offset and output records share the same commit outcome in Kafka.

Do not manually call `consumer.commitSync()` or `consumer.commitAsync()` inside a transactional listener "just to be sure". Committing separately outside the transaction can break atomic output + offset semantics.

## 11. read_committed vs read_uncommitted

Kafka brokers may already hold a transactional producer's output before the transaction commits. Consumers using **read_uncommitted** can read even records belonging to aborted transactions. Consumers using **read_committed** return only committed transactional records.

~~~text
Transaction T1:
  produce A
  produce B
  ABORT

Transaction T2:
  produce C
  COMMIT

Consumer read_committed:
  sees C
  does not see A, B
~~~

If downstream services do not configure `read_committed`, they can observe aborted records and trigger side effects on uncommitted data. That defeats a major purpose of transactional outputs for downstream pipelines.

Downstream consumer example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: normalized-order-consumer
      isolation-level: read_committed
      enable-auto-commit: false
~~~

`read_committed` still reads valid non-transactional records. At the same time, an open transaction earlier in the log can make `read_committed` consumers wait at the **Last Stable Offset (LSO)**, increasing latency even when the broker has received subsequent records.

## 12. What Is the Scope of Exactly-Once Semantics?

Kafka transactions provide the foundation for **Kafka read-process-write exactly-once** when all protected outputs are sent transactionally, consumed offsets share the same transaction, and downstream reads only committed data.

What is protected:

- A transaction's Kafka outputs commit or abort together.
- Consumed offsets commit atomically with outputs within Kafka.
- Downstream `read_committed` consumers do not see aborted transactional outputs.

What is **not** protected by Kafka transactions alone:

- Guaranteeing the Java listener runs strictly once.
- Automatically rolling back database transactions on Kafka abort.
- Automatically undoing HTTP API calls, emails, or payments.
- Atomically committing across two separate Kafka clusters in one transaction.
- Automatically pulling non-transactional producers into the transaction.

When an app crashes before commit, the source record may be read again and the listener run again. What matters is that Kafka outputs from aborted attempts are never committed.

For external side effects, you must apply idempotency, an outbox, or another consistency mechanism if business logic requires it.

## 13. Exceptions and Rollback Boundaries

If a listener throws a `RuntimeException` and it reaches the container, the transaction can roll back. However, if the listener catches the exception and does not rethrow it, the container may treat the listener as completed normally.

Example of what **not to do**:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderCreated event) {
    try {
        paymentService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Payment failed", ex);
        // Not rethrown: container may treat processing as successful.
    }
}
~~~

If `paymentService` fails, the code above could commit the offset despite incomplete business work. A safer approach is logging and rethrowing:

~~~java
catch (RuntimeException ex) {
    log.error("Payment failed", ex);
    throw ex;
}
~~~

Or throwing a suitable business exception recognized by the transaction boundary and recovery policy. Deciding which exceptions are retryable vs non-retryable belongs to your error-handling strategy, but never swallow errors and expect the container to roll back automatically.

## 14. AfterRollbackProcessor Handling Records After Abort

For transactional listeners, **AfterRollbackProcessor** is the key mechanism after a Kafka transaction rolls back. A common implementation is **DefaultAfterRollbackProcessor**.

~~~text
Listener exception
      |
      v
Abort Kafka transaction
      |
      v
AfterRollbackProcessor
      |
      +-- determine offsets to redeliver
      +-- seek or coordinate records
      +-- apply BackOff
      +-- recover if retries exhausted
      |
      v
Consumer polls and reprocesses
~~~

Unlike non-transactional listener containers that commonly configure `DefaultErrorHandler`, transactional listeners primarily rely on after-rollback processing to preserve abort semantics.

If you attach an error handler to a transactional container, verify whether the handler **rethrows exceptions**. An error handler that finishes handling and returns normally can cause the container to commit a transaction that should have aborted.

`BackOff` must be bounded reasonably. Infinite retries in transactional processing can stall a partition indefinitely, spike consumer lag, and starve downstream of outputs.

## 15. DLT Recovery After Rollback

When errors remain unresolvable after multiple retries, records can be routed to a DLT. With transactional listeners, distinguish **the transaction that aborted when the listener failed** from **the recovery transaction used to publish to the DLT and commit the recovered offset**.

~~~text
T1:
  consume input
  business listener fails
  ABORT

After rollback:
  backoff + retry
  ...
  attempts exhausted

Recovery:
  publish failed record to DLT
  commit recovered input offset
  per configured transaction/recovery semantics
~~~

You cannot continue committing T1 after it has aborted. Spring Kafka supports configuring `DefaultAfterRollbackProcessor` with a `ConsumerRecordRecoverer`, such as `DeadLetterPublishingRecoverer`, for recovery; in certain configurations/versions, recovery can run in a **new transaction** and commit the recovered offset alongside the DLT publish.

Factors to clarify explicitly:

1. Retry count and backoff interval.
2. Which errors qualify for retry vs immediate recovery.
3. Whether the DLT topic/partition and serializers match.
4. Whether the recoverer publish succeeded or failed.
5. When the recovered offset is committed.
6. If the recovery transaction aborts, how the source record will be redelivered.

Do not treat invoking the recoverer as proof the DLT write succeeded. Observe publish outcomes and handle recovery failures.

## 16. Transactional.id and Producer Fencing

`KafkaProducer` uses **transactional.id** so the broker can manage transactions and fence older producers using the same identity. Spring Kafka's `ProducerFactory` builds `transactional.id` values from `transactionIdPrefix` and appropriate suffixes.

~~~text
Application instance A:
  transaction-id-prefix: pod-a-orders-tx-
  transactional.id:      pod-a-orders-tx-0

Application instance B:
  transaction-id-prefix: pod-b-orders-tx-
  transactional.id:      pod-b-orders-tx-0
~~~

These are illustrative values. In production, **concurrently running** instances must never accidentally share a `transactional.id`; they will fence one another. A new instance with the same `transactional.id` can fence the old producer, which is Kafka's protection against two producers writing under the same identity.

`ProducerFencedException` must not be handled by retrying on the already fenced producer. The producer and container must go through appropriate lifecycle recovery/restart.

In operations, check:

- Do prefixes distinguish active pods/instances sufficiently?
- Are old and new versions running concurrently with the same prefix?
- Is the transactional producer cache stale or expired on the broker?
- Are multiple application contexts unintentionally sharing a `transactional.id`?

## 17. Producer Cache and Transaction Lifecycle

Spring Kafka can cache transactional producers for reuse. Under high concurrency, the application needs sufficient producer capacity and non-conflicting transactional IDs.

Key points:

- Transactional producers require a producer factory with `transactionIdPrefix`.
- Producer caching, thread counts, and concurrency affect how many producers can be active.
- Brokers expire transactional IDs after inactivity; long-idle producers may face fencing when reused.
- Supporting Spring Kafka versions offer **maxAge** on `DefaultKafkaProducerFactory` to proactively replace cached producers before broker expiration.
- Changing concurrency or replica counts changes the required producer count; never assume one `KafkaTransactionManager` uses only one `KafkaProducer` forever.

Do not raise concurrency blindly just because transaction throughput seems low. Measure consumer lag, producer request latency, transaction commit time, broker CPU, and output partition counts before diagnosing the bottleneck.

## 18. Rebalances During an In-Flight Transaction

A consumer group can rebalance during pod restarts, scale up/down, overly slow polls, or lost connections. If partition ownership changes while a listener is processing, the transaction may fail to commit offsets validly under current consumer group membership.

~~~text
Consumer A assigned P2@51
      |
      +-- begin T1
      +-- slow processing
      |
Group rebalance
      |
P2 moves to Consumer B
      |
Consumer A no longer has valid ownership
      |
T1 may abort / offset commit fails
      |
Consumer B reprocesses P2@51
~~~

Kafka transactions reduce the risk of partial state inside Kafka; however, if Consumer A already called a payment API before losing ownership, that action may already have completed outside Kafka.

Use graceful shutdown, avoid overly long listener execution, monitor rebalances, and enforce idempotency on external side effects. Using the transaction coordinator and consumer group metadata, Kafka validates membership to prevent stale members from committing invalid offsets.

## 19. transaction.timeout.ms and max.poll.interval.ms

Two time-related settings with distinct purposes:

| Parameter | Governs | If threshold exceeded |
|---|---|---|
| **transaction.timeout.ms** | Duration a transaction may stay open per Kafka broker/producer | Transaction may be aborted by broker or fail commit |
| **max.poll.interval.ms** | Maximum time between consumer polls per group protocol | Consumer may lose membership and trigger rebalance |

For instance, a listener processes a large batch, calls a REST API for several minutes, and sends multiple outputs. Even if `max.poll.interval.ms` is large enough, the Kafka transaction can still time out. Conversely, a generous transaction timeout paired with a delayed poll can still trigger a rebalance.

Necessary practices:

- Measure listener processing time, records per batch, and transaction duration.
- Avoid holding transactions open while waiting on slow external services.
- Tune timeouts based on SLOs and measured data, not infinitely large values.
- Consider offloading long work to another workflow instead of holding a Kafka transaction open.
- Never conflate transaction timeouts with HTTP client or database timeouts.

Long transactions can also stall downstream `read_committed` consumers at the Last Stable Offset until the transaction resolves.

## 20. Database Updates Do Not Belong to Kafka Transactions

Suppose a listener both updates a database and publishes Kafka output:

~~~text
orders.created
      |
      v
Kafka listener
      |
      +-- UPDATE orders SET status = ...
      |
      +-- KafkaTemplate.send("orders.normalized")
      |
      v
Kafka transaction COMMIT or ABORT
~~~

If the database `UPDATE` succeeds yet the Kafka transaction aborts, the source Kafka record may be reprocessed. The retry could update the database a second time.

Kafka transactions **do not automatically roll back databases**. Even when using Spring transaction synchronization to order commits, that is usually best-effort coordination, not an atomic distributed XA transaction between Kafka and a database.

Solutions by business need:

- **Idempotent update:** store event ID/version in the database so repeated processing causes no new side effect.
- **Transactional outbox:** write state and event to an outbox table in the same database transaction, then publish separately.
- **Saga/workflow:** coordinate distributed steps and compensating actions.
- **Split boundaries:** keep Kafka-to-Kafka transactional while handling database side effects under their own consistency policy.

If the requirement is "database and Kafka output must always commit together with no intermediate state", enabling `transaction-id-prefix` on the Kafka producer alone is not enough.

## 21. External APIs and Idempotency

A listener may call a payment API before the Kafka transaction commits:

~~~text
Transaction T1:
  call payment API -> succeeds
  send Kafka output -> fails
  abort Kafka transaction

Transaction T2:
  reprocess input
  risk of calling payment API a second time
~~~

When the API supports idempotency keys, use a stable event ID:

~~~java
public void charge(PaymentRequested event) {
    paymentClient.charge(
            event.paymentId(),
            event.amount(),
            event.eventId()); // idempotency key
}
~~~

This snippet illustrates a custom client API; exact syntax depends on the payment provider. If an external API lacks idempotency support, the application needs a separate deduplication/reconciliation state.

A side effect outside the Kafka transaction can occur multiple times even though the final Kafka output has only one committed record. That is why consumer-initiated transactions must never be described as guaranteeing exactly-once across all business operations.

## 22. Batch Listeners and Rollback

A batch listener can process multiple records in a single invocation. When the container manages one transaction per batch, all Kafka outputs sent within that transaction commit or abort together based on the callback's outcome.

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-transformer",
        containerFactory = "transactionalBatchListenerFactory")
public void handleBatch(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        NormalizedOrder normalized =
                mapper.normalize(record.value());

        kafkaTemplate.send(
                "orders.normalized",
                record.key(),
                normalized
        ).join();
    }
}
~~~

This example requires a listener factory with batch mode and a matching Kafka transaction manager. If a record mid-batch fails, the transaction can abort, keeping Kafka outputs sent in that transaction invisible to `read_committed`.

Large batches increase transaction duration and retry cost. Weigh `max.poll.records`, timeouts, side effects, and how `AfterRollbackProcessor` handles batches rather than assuming a failure retries only a single record.

## 23. Can Non-Blocking Retry Topics Be Combined?

Spring Kafka supports `@RetryableTopic` to route failed records to delayed retry topics. However, in standard Spring Kafka setups, **non-blocking retries do not combine directly with container Kafka transactions**.

Consumer-initiated processing transactions roll back and go through `AfterRollbackProcessor`, whereas non-blocking retries forward records to retry topics and commit progress under their own topology. The two mechanisms have different transaction and ordering boundaries.

Do not simply add `@RetryableTopic` to a transactional listener expecting the whole retry topology and consumed offsets to share the same Kafka transaction automatically.

If long delays are needed, design a separate workflow with explicit transaction boundaries. For transactional listeners, usually start with bounded blocking retries and DLT recovery under appropriate transaction semantics.

## 24. Observing Transactions in Production

Key metrics:

- Counts of started, committed, and aborted transactions.
- Transaction duration p50/p95/p99.
- Transaction timeouts and producer fencing errors.
- Listener processing latency, error rates, retries, and recoveries.
- Consumer lag per partition, rebalance rates, and rebalance durations.
- Producer send/commit latencies, broker errors, and request retries.
- Records routed to DLT and DLT publish failures.
- Downstream `read_committed` consumer lag.
- Producer cache size/utilization and active transactional ID count.

An application log might record:

~~~text
eventId=EVT-104
listener=orders-transformer
source=orders.created/P2/51
outputTopic=orders.normalized
transactionOutcome=aborted
exceptionClass=DownstreamTimeoutException
retryScheduled=true
~~~

This is an illustrative structured application log, not a Kafka-generated format. Original topic/partition/offset and event ID belong in logs or traces, not as high-cardinality metric labels.

When lag rises while committed output stalls, distinguish slow listeners, repeated transaction aborts, fenced producers, transaction coordinator errors, and `read_committed` consumers blocked by open transactions.

## 25. Testing Failure Scenarios

Use a real Kafka test broker (such as Testcontainers or EmbeddedKafka) and a downstream consumer with `isolation.level=read_committed`.

### Case 1: happy path

1. Produce an input event to `orders.created`.
2. Listener transforms and sends output.
3. Wait for transaction commit.
4. Verify the `read_committed` consumer receives the output.
5. Verify the consumer group's committed offset advances past the input.

### Case 2: exception after send

1. Listener sends Kafka output inside the transaction.
2. Intentionally throw an exception before the callback completes.
3. Verify the transaction aborts.
4. Verify the `read_committed` consumer does not see the failed attempt's output.
5. Verify the source record is retried or recovered per policy.

### Case 3: crash before commit

1. Consumer reads input and sends output inside the transaction.
2. Stop the process before commit.
3. Restart the consumer group.
4. Verify the source record is reprocessed if no offset committed.
5. Verify only committed outputs appear to `read_committed`.

### Case 4: producer fencing

1. Simulate two instances sharing a `transactional.id` in a test environment.
2. Observe producer fencing and transaction failures.
3. Fix the prefix to distinguish instances.
4. Verify active pods no longer fence one another.

### Case 5: side effects outside Kafka

1. Listener updates a database or calls an API.
2. Intentionally abort the Kafka transaction after the side effect.
3. Confirm the external side effect may have occurred.
4. Reprocess the input and verify idempotency.

Never declare exactly-once from happy-path tests alone. Tests must cover produce, offset commit, abort, crash, and replay boundaries.

## 26. Common Configuration Mistakes

| Symptom | Possible cause | Remediation |
|---|---|---|
| `KafkaTemplate` reports no active transaction | `ProducerFactory` or listener container not transactional | Check `transaction-id-prefix`, transaction manager, and factories |
| Duplicate outputs on retry | Template not in same transaction or external side effects | Check producer factory, `read_committed`, and idempotency |
| `ProducerFencedException` | Duplicate `transactional.id` or stale producer | Check per-instance prefixes, restarts, and producer cache |
| Commit fails after long processing | Transaction timeout or lost group membership | Measure duration, `max.poll.interval.ms`, and rebalances |
| Downstream sees aborted outputs | Consumer uses `read_uncommitted` | Use `read_committed` when commit semantics are needed |
| Source record skipped despite listener failure | Exception swallowed or separate offset commit | Check rethrow, ack mode, and transaction boundary |
| DLT missing records after retries | Recoverer, serializer, or recovery transaction error | Check producer, DLT topic, and `AfterRollbackProcessor` |
| Output invisible despite producer send | Transaction uncommitted or aborted | Check transaction outcome and consumer isolation |
| Database creates duplicate data | Side effect outside Kafka transaction | Add idempotency or outbox |

## 27. Common Misconceptions

**`KafkaConsumer` directly creates transactions.** False. In Spring Kafka, the listener container uses a transactional producer and transaction manager to create transactions while consuming.

**`@Transactional` on `@KafkaListener` is enough.** False. You need a transactional producer factory and a listener container attached to the right transaction manager.

**Any `KafkaTemplate` joins the transaction automatically.** False. `ProducerFactory` and transaction context must match.

**Transactions commit only output records.** False. The key point of consumer-initiated transactions is combining consumed offsets with outputs.

**Processing offset 51 commits offset 51.** False. By convention, group committed offsets represent the next position; typically 52.

**Listeners run only once because exactly-once is enabled.** False. Listeners can rerun after aborts, crashes, or rebalances; Kafka transactions protect committed results.

**Kafka rollback undoes databases/APIs.** False. You need idempotency, transactional outbox, or an appropriate workflow.

**Downstream `read_uncommitted` suffices to verify transactions.** False when aborted outputs must be excluded; use `read_committed`.

**Having a `KafkaTransactionManager` bean means every listener is transactional.** False. Inspect the specific listener container.

**`ProducerFencedException` can be ignored and retried on the same producer.** False. Fenced producers must go through transaction manager lifecycle handling.

**Non-blocking retry topics always work with container transactions.** False. Review Spring Kafka's support limits and design proper transaction boundaries.

## 28. Designing a Consumer-Initiated Transaction Pipeline

When building a Kafka-to-Kafka pipeline, follow these steps:

1. Identify source topics, target topics, and all side effects outside Kafka.
2. Identify atomicity requirements between Kafka outputs and consumed offsets.
3. Configure a transactional `ProducerFactory` with non-colliding `transactionIdPrefix` across active instances.
4. Create `KafkaTransactionManager`/`KafkaAwareTransactionManager` matching your Spring Kafka version.
5. Attach the transaction manager to the listener container factory used by the listener.
6. Ensure `KafkaTemplate` uses the container's `ProducerFactory` and transaction context.
7. Disable consumer auto-commit; never commit offsets separately outside the Kafka transaction.
8. Use `read_committed` downstream when aborted transactional outputs must be skipped.
9. Let exceptions requiring rollback propagate to the container; configure `AfterRollbackProcessor` and bounded retries.
10. Design DLT and recovered offset commits under an appropriate recovery transaction.
11. Protect databases/APIs with idempotency or outbox.
12. Monitor commits/aborts, transaction duration, fencing, rebalances, and consumer lag.
13. Test exceptions after send, crashes before commit, producer fencing, and external side effects.

**Consumer-initiated transactions** are Spring Kafka's core mechanism for consume-process-produce with **outputs and consumed offsets committed atomically in Kafka**. They eliminate the inconsistency risk between outputs and consumer progress on failure, though they do not prevent listener re-execution and do not extend atomicity to systems outside Kafka. Safe design coordinates producer transactions, container transaction managers, `read_committed`, rollback/recovery, unique `transactional.id` values across instances, and idempotency for all business side effects.
