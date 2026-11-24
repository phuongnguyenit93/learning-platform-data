# Transactional producers and isolation

When implementing **exactly-once processing** on Kafka, two pieces must work together: a **transactional producer** writes records and offsets as an atomic unit, while **consumer isolation** governs which records downstream can see. Enabling transactions on the producer alone is not enough for consumers to read the right result: if downstream uses `read_uncommitted`, it can still read outputs from a transaction that ultimately aborts. Conversely, enabling `read_committed` on a consumer alone does not make processing exactly-once if producer writes and input offsets are not committed in the same Kafka transaction.

With Spring Kafka, the typical model is **consume–transform–produce**: a listener reads a record from an input topic, transforms the data, sends it to an output topic via a transactional `KafkaTemplate`, and the container places the consumed offset into the same transaction. When the transaction commits, output and consumption progress are recorded together; when the transaction aborts, transactional output is invisible to `read_committed` consumers and the input offset is not committed in that transaction.

This is a guarantee **within Kafka's scope**. It does not automatically make database updates, HTTP calls, emails, or external payments exactly-once. This lesson covers the complete guarantee boundary, Spring Kafka configuration, isolation behavior, failure scenarios, and operational verification methods.

## 1. Distinguishing delivery, processing, and visibility

Before configuring, distinguish three concepts that sound similar yet differ:

- **Delivery:** whether a record can be received by a consumer once or multiple times.
- **Processing:** whether the same business logic can execute once or multiple times across retries, crashes, or rebalances.
- **Visibility:** whether a transaction's output record can be seen by downstream before commit or after transaction abort.

Kafka transactions combine an idempotent producer, atomic output, and atomic offset commits to support an exactly-once outcome in **read from Kafka → process → write to Kafka** flows when properly configured. Consumers can still re-execute the listener after rollback; what matters is that **only Kafka results from committed transactions become valid results** for `read_committed` downstream consumers.

Example:

~~~text
orders-input (offset 150)
        |
        v
Spring Kafka listener
        |
        +-- Transform event
        |
        +-- KafkaTemplate.send("orders-output", value)
        |
        +-- Container sends offset 151 into transaction
        |
        v
Commit Kafka transaction
        |
        +-- Success:
        |      Output visible to read_committed
        |      Consumer group saves offset 151
        |
        +-- Abort:
               Output not visible to read_committed
               Offset 151 not committed with transaction
               Input offset 150 can be re-read
~~~

If a listener writes Kafka outputs and also calls a REST API, the REST side effect may already have occurred even if the Kafka transaction aborts. Therefore, never extrapolate Kafka exactly-once into system-wide exactly-once.

## 2. What is a transactional producer?

A **transactional producer** is a Kafka producer configured with a **transactional.id** and initialized via the transaction protocol. This producer can execute multiple sends within one transaction, and then commit or abort all of those transactional records as a single unit.

Basic lifecycle of the Kafka Producer API:

~~~java
Properties config = new Properties();
config.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "broker1:9092");
config.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
           StringSerializer.class);
config.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
           StringSerializer.class);
config.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
           "order-worker-instance-1");

try (KafkaProducer<String, String> producer =
         new KafkaProducer<>(config)) {

    producer.initTransactions();

    producer.beginTransaction();
    try {
        producer.send(
            new ProducerRecord<>("orders-output", "order-42", "VALIDATED")
        );
        producer.send(
            new ProducerRecord<>("orders-audit", "order-42", "VALIDATED")
        );

        producer.commitTransaction();
    }
    catch (Exception ex) {
        // Abort only if the producer and transaction still allow it;
        // handle fatal errors/fencing per Kafka client contract.
        producer.abortTransaction();
        throw ex;
    }
}
~~~

This code illustrates the concept; do not use a broad catch block to call `abortTransaction` unconditionally in production, because certain fatal errors or producer fencing require closing the producer rather than continuing to control the old transaction.

Key points:

1. **initTransactions()** initializes the transactional producer with the coordinator.
2. **beginTransaction()** opens a new transaction.
3. **send()** appends transactional records to partitions.
4. **commitTransaction()** completes the commit per protocol.
5. **abortTransaction()** cancels an abortable transaction when an appropriate error occurs.

Without `transactional.id`, a producer can use idempotence yet lacks transactions to group multiple records and offsets into an atomic unit.

## 3. Transactional ID, producer ID, and fencing

Kafka uses **transactional.id** to identify a logical transactional producer across restarts. The coordinator binds this identity to a producer ID and epoch to prevent an old producer from continuing to write with expired ownership.

Example:

~~~text
Instance A: transactional.id = inventory-processor-0
        |
        +-- Processing transaction
        |
        +-- Network loss / prolonged restart

Instance B: transactional.id = inventory-processor-0
        |
        +-- initTransactions() with same identity
        |
        +-- New producer epoch established
        |
        v
Instance A becomes old / zombie producer
        |
        v
Fencing blocks A from continuing to write as a valid producer
~~~

Fencing is a vital part of transaction safety: an old instance must not continue committing outputs after a new instance takes over that identity.

However, **never accidentally reuse the same `transactional.id` across multiple independently active instances**. If two pods share one identity, they can fence each other, causing transaction aborts, increased errors, and reduced throughput.

Spring Kafka typically generates transactional IDs from a **transactionIdPrefix** and suffixes owned by the producer factory. The prefix must be designed so each application instance uses a distinct identity space; suffixes support multiple cached producers inside one instance. How suffixes/pools are allocated and which APIs manage prefixes depend on the Spring Kafka version.

## 4. Idempotent producer vs. transactional producer

Both mechanisms are related yet differ in scope:

| Capability | Idempotent producer | Transactional producer |
|---|---|---|
| Prevents duplicates from producer request retries in a valid session | Yes, via protocol sequence numbers | Yes, built upon idempotent producer foundations |
| Groups multiple records into an atomic transaction | No | Yes |
| Includes consumed offsets in the same atomic unit as outputs | No | Yes, when using appropriate APIs/containers |
| Has `transactional.id` and fencing by transaction identity | Not required | Yes |
| Requires `read_committed` downstream to hide aborted output | Not applicable to non-transactional sends | Yes |
| Guarantees database/HTTP side effects are exactly-once | No | No |

When `transactional.id` is configured, Kafka enforces compatible idempotence requirements. Modern Kafka releases may enable idempotence automatically under transactional configurations, yet never override producer properties in conflicting ways—such as forcing `enable.idempotence=false` on a transactional producer.

Idempotence does not automatically recognize that two application `send()` calls represent the same business event. It protects the producer's retry protocol for a batch/record under matching conditions, not replacing event IDs and deduplication at the business layer.

## 5. Transaction coordinator and transaction log

Kafka has a **transaction coordinator** responsible for managing the transaction state of each `transactional.id`. Transaction state is stored in the internal **__transaction_state** topic; the coordinator uses protocol messages to record state and finalize commits or aborts across participating partitions.

Components:

- Transactional producer initializes identity and epoch.
- Coordinator records the ongoing transaction and involved partitions.
- Producer sends records to topic partitions.
- When consumed offsets exist, they are routed via the transaction protocol to the appropriate consumer group coordinator.
- Commit/abort markers and transaction state govern output visibility.

Do not assume Kafka writes every record to a single partition; a transaction can span multiple partitions/topics within the same Kafka cluster, coordinated by the transaction coordinator.

A transaction is not a shared distributed transaction across Kafka cluster A, Kafka cluster B, and a database. If an application writes concurrently to multiple independent clusters or an external system, a different consistency mechanism is needed.

## 6. What is consumer isolation?

The **isolation.level** property on a Kafka consumer determines how strongly transactional records are filtered.

Two modes:

~~~properties
isolation.level=read_uncommitted
~~~

and:

~~~properties
isolation.level=read_committed
~~~

### 6.1. read_uncommitted

A consumer in `read_uncommitted` mode can read uncommitted transactional records as well as records belonging to transactions that later abort. That is why `read_uncommitted` must not be used for downstream consumers that must apply only successful transaction outcomes.

`read_uncommitted` is the Kafka consumer default in many releases. If a pipeline needs transactional visibility, configure `read_committed` explicitly rather than relying on defaults.

### 6.2. read_committed

A `read_committed` consumer returns only committed transactional records alongside readable non-transactional records per protocol. It **does not return** records from aborted or unfinished transactions.

Common misconception: `read_committed` **does not mean** the topic contains only transactionally produced records. **Non-transactional** records remain visible to a `read_committed` consumer as long as they fall within the readable range.

### 6.3. Comparison table

| Record in Kafka log | `read_uncommitted` | `read_committed` |
|---|---|---|
| Validly written non-transactional record | Readable | Readable |
| Committed transactional record | Readable | Readable |
| Open transactional record | May be read depending on log position | Not returned before commit |
| Aborted transactional record | Readable | Filtered from results |
| Transaction control marker | Not a normal application event | Not returned as a business record |

When building an exactly-once flow properly, downstream consumers need the matching isolation level. An output service using `read_uncommitted` can inadvertently process outputs from canceled transactions.

## 7. LSO, HW, and LEO

To understand `read_committed`, distinguish these broker offsets:

- **Log End Offset (LEO):** the next position at the tail of the leader log, indicating how far the leader has appended data.
- **High Watermark (HW):** the boundary of data replicated sufficiently for Kafka to serve to consumers under matching semantics.
- **Last Stable Offset (LSO):** the stability boundary for `read_committed`; governed by the earliest open transaction in the partition.

With `read_committed`, fetches do not return transactional data past the LSO boundary. An open transaction can leave LSO behind HW in progression, even as other producers keep writing to that partition.

Example:

~~~text
Partition events:

offset 100: stable record
offset 101: record in transaction T (still open)
offset 102: non-transactional record from another producer
offset 103: record in transaction U (committed)

                    LSO
                     |
                     v
... [100] [101] [102] [103] ...
                             |
                             v
                         HW / LEO
~~~

In this scenario, records 102/103 may have to wait for transaction T to finish before the `read_committed` consumer resumes returning records beyond LSO. Kafka preserves stable per-partition reading rather than jumping past an open transaction to surface later records in `read_committed` results.

This illustration omits transaction control markers and replica states; view it as a diagram of visibility boundaries.

## 8. Example: how do commit and abort affect downstream?

A producer sends two records in one transaction:

~~~text
Transaction TX-1:
  send(topic=A, key=k1, value=OUT-1)
  send(topic=B, key=k1, value=OUT-2)
  commitTransaction()
~~~

Once commit finishes, `read_committed` consumers on A and B can see both records when fetching their respective partitions.

If the transaction aborts:

~~~text
Transaction TX-2:
  send(topic=A, key=k2, value=TEMP-1)
  send(topic=B, key=k2, value=TEMP-2)
  abortTransaction()
~~~

`read_committed` consumers do not return `TEMP-1` and `TEMP-2` as application records. `read_uncommitted` consumers can read records appended to the log before/after the abort.

Importantly, transactional visibility is independent of business validation. The broker does not know whether `OUT-1` is valid business-wise; it only knows whether the transaction committed or aborted per protocol.

## 9. Exactly-once through Kafka: why commit offsets with outputs?

Suppose input is at offset 50 and output sends successfully, then the process dies before committing the input offset.

With a non-transactional producer:

~~~text
Read input offset 50
        |
        v
Send output O50 -> broker writes successfully
        |
        v
Application crashes before committing input offset 51
        |
        v
Restart: group reads offset 50 again
        |
        v
Send output O50 again
        |
        v
Downstream may see duplicates
~~~

If Kafka transactions are used yet **output and input offset commit separately**, a failure window still exists: output commits before the input offset commits.

Therefore, a Kafka exactly-once flow needs **sendOffsetsToTransaction** or an equivalent container mechanism to bring consumed offsets into **the same Kafka transaction** as outputs.

When the transaction commits successfully:

- Kafka outputs commit.
- Consumed offsets are recorded under the transaction.
- The consumer group resumes from the new offset upon reassignment.

On abort:

- Transaction outputs remain hidden from `read_committed` downstream.
- Offsets belonging to the transaction are not committed.
- Input can be reprocessed in a new transaction.

This is the basis of EOS in Kafka-to-Kafka stream processing.

## 10. Offset commit via sendOffsetsToTransaction

With the raw Kafka Java API, the producer can send an offset map along with consumer group metadata into the transaction:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
    new TopicPartition("orders-input", 0),
    new OffsetAndMetadata(51L)
);

// Producer is inside a valid transaction.
producer.sendOffsetsToTransaction(
    offsets,
    consumer.groupMetadata()
);
~~~

Here, offset **51** is the **next** position after processed record offset 50. Never commit offset 50 as if it were the next position, as the consumer would re-read offset 50 on restart.

In a Spring Kafka transactional listener container, the framework handles adding offsets to the transaction on behalf of application code. Do not call `consumer.commitSync()` manually to commit input offsets outside the transaction when relying on container EOS.

Specific APIs and requirements for `sendOffsetsToTransaction` vary by Kafka client version; use `consumer.groupMetadata()` in modern APIs to bind offset commits to the appropriate group metadata/generation.

## 11. Spring Boot configuration

Example Spring Boot application using a transactional producer and `read_committed` consumer:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - broker1:9092
      - broker2:9092
    producer:
      transaction-id-prefix: order-service-instance-a-
      acks: all
      properties:
        enable.idempotence: true
        transaction.timeout.ms: 60000
    consumer:
      group-id: orders-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Meaning:

- **transaction-id-prefix:** enables creation of transactional producers via Spring Kafka's `ProducerFactory`.
- **acks=all:** producer requires acknowledgments per Kafka's in-sync replica policy.
- **enable.idempotence=true:** protects producer request retries where applicable; with transactional producers, ensure properties do not conflict.
- **transaction.timeout.ms:** broker coordinator bound on open transactions.
- **enable-auto-commit=false:** lets the listener container manage consumed offsets.
- **read_committed:** appropriate when input contains transactional records and the consumer must not process aborted outputs.

A consumer reading non-transactional input can still use `read_committed`; doing so does not create transactions on the input producer. Enabling `read_committed` on a consumer governs only the visibility of read records.

**Important:** `transaction-id-prefix` must be assigned independently across concurrently running application instances. The `instance-a` string above is illustrative only; production should derive prefixes from instance identity per deployment workflow.

## 12. Configuring KafkaTemplate and KafkaTransactionManager

Spring Kafka uses **DefaultKafkaProducerFactory**, **KafkaTemplate**, and **KafkaTransactionManager** to integrate transactions into applications. In standard Spring Boot configurations, a Kafka transaction manager can be auto-configured when `producer.transaction-id-prefix` is set; in manually wired apps, create the transaction manager from the transactional producer factory.

Java example:

~~~java
@Bean
ProducerFactory<String, OrderResult> producerFactory(
        Map<String, Object> producerConfig) {

    DefaultKafkaProducerFactory<String, OrderResult> factory =
        new DefaultKafkaProducerFactory<>(producerConfig);
    factory.setTransactionIdPrefix("order-service-instance-a-");
    return factory;
}

@Bean
KafkaTransactionManager<String, OrderResult> kafkaTransactionManager(
        ProducerFactory<String, OrderResult> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}

@Bean
KafkaTemplate<String, OrderResult> kafkaTemplate(
        ProducerFactory<String, OrderResult> producerFactory) {

    return new KafkaTemplate<>(producerFactory);
}
~~~

The `producerConfig` map must include bootstrap servers, serializers, and appropriate producer properties. This snippet is an illustrative structure, not a complete copy-paste Spring configuration file.

The transaction manager must use the exact producer factory backing `KafkaTemplate`/the container. If an application creates multiple producer factories or writes to multiple clusters, one `KafkaTransactionManager` does not automatically make separate clusters commit atomically together.

## 13. Container transactions with @KafkaListener

When a listener container is configured with a suitable `KafkaAwareTransactionManager`, the container can manage Kafka transactions around the listener and offset commits.

Example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        KafkaTransactionManager<String, OrderResult> kafkaTransactionManager) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
           .setKafkaAwareTransactionManager(kafkaTransactionManager);
    return factory;
}
~~~

Across Spring Kafka versions, setter names or Boot auto-configuration details may differ. Check your version's API; the goal is to bind the container to the transactional producer factory's Kafka transaction manager.

Listener:

~~~java
@KafkaListener(
    topics = "orders-input",
    groupId = "orders-processor",
    containerFactory = "ordersListenerFactory"
)
public void process(OrderEvent event) {
    OrderResult result = orderService.transform(event);
    kafkaTemplate.send(
        "orders-output",
        event.orderId(),
        result
    );
}
~~~

Overall flow:

1. Container polls records from `orders-input`.
2. Container begins a Kafka transaction for the processing scope.
3. Listener calls `KafkaTemplate.send()` using a producer participating in the transaction.
4. Container adds processed input offsets into the same transaction.
5. Container commits the transaction when the listener completes successfully.
6. If the listener throws an exception or the transaction fails to commit, the container rolls back/aborts and handles redelivery per policy.

Never enable consumer auto-commit when you want the container to control transactional offset commits. Also, never manually call `acknowledge` or `commitSync` in ways that decouple offsets from the framework-managed transaction.

## 14. KafkaTemplate.executeInTransaction and container transactions

`KafkaTemplate` provides **executeInTransaction()** to perform sends inside a Kafka transaction:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders-output", "order-12", result);
    operations.send("orders-audit", "order-12", auditEvent);
    return null;
});
~~~

This is useful when an application needs a transaction for Kafka sends without going through a listener container transaction.

However, there is a key boundary: **executeInTransaction typically opens a local Kafka transaction on the template**, not automatically the transaction currently managed by the listener container. Never wrap Kafka sends inside `executeInTransaction` within a transactional listener and assume input offsets automatically belong to that local transaction.

If the goal is consume–transform–produce EOS, use `KafkaTemplate` with the container-managed transaction manager and let the container perform transactional offset commits. Open nested/local transactions only when you know the library's exact semantics and rollback boundaries.

## 15. A listener re-run does not mean EOS is broken

Suppose an input record at offset 30 is processed:

~~~text
Attempt 1:
   Input 30 -> output O30 in TX-A
   TX-A aborts

Attempt 2:
   Input 30 -> output O30 in TX-B
   TX-B commits
   Input offset 31 is committed with TX-B
~~~

The listener ran twice, and output may have been appended under two separate transactions in the Kafka log. However, a `read_committed` consumer returns only the output from TX-B (the committed transaction). Downstream never sees the aborted TX-A result.

This is the right understanding of exactly-once **effect** in Kafka: you do not need to claim the Java listener executed only once. Kafka transactions and consumer isolation work together so only valid committed results emerge.

If the listener also made an HTTP call to create an invoice during TX-A, the HTTP side effect may already have happened. Aborting TX-A does not delete that invoice. Thus, non-Kafka parts still need duplicate protection.

## 16. Spring Kafka transactional listeners on errors

With a transactional container, exceptions from the listener typically trigger transaction rollback/abort. Spring Kafka includes post-rollback handlers such as **DefaultAfterRollbackProcessor**.

Example:

~~~text
Listener receives Input X
      |
      +-- Sends Output X in Kafka TX
      |
      +-- Throws exception
              |
              v
       Transaction aborts
              |
              v
       Kafka output X hidden from read_committed
              |
              v
       Input offset uncommitted with TX
              |
              v
       AfterRollbackProcessor / redelivery
~~~

Do not assume a **DefaultErrorHandler** configured for non-transactional listeners governs all retries of a transactional listener. Transactional paths and recovery processors must be configured according to your Spring Kafka version.

If after repeated failures the application routes the record to a DLT, evaluate the **recovery transaction**: are DLT publishing and the recovered offset handled under the appropriate protocol? When recovery publishing fails, never commit the input as if the record were safely stored.

## 17. read_committed does not replace consumer acknowledgments

A misconception is that setting `isolation.level=read_committed` automatically guarantees input offsets commit exactly-once. That is false.

`read_committed` affects only which records the consumer **receives from `poll()`**. Consumer offset commits still depend on the container, transaction manager, `AckMode`, and how the application manages processing.

Comparison:

| Setup | Outcome |
|---|---|
| Transactional producer, `read_uncommitted` downstream | Downstream can see aborted transaction outputs |
| Transactional producer, `read_committed` downstream | Downstream hides uncommitted/aborted outputs |
| `read_committed` consumer, regular output producer | No atomic output+offset commit |
| Transactional producer + separate `commitSync` offset | Failure window where output succeeds while input offset is uncommitted |
| Transactional producer + consumed offsets in same transaction + `read_committed` downstream | Foundation for Kafka-to-Kafka exactly-once |

For a service that only reads Kafka and writes to a database, `read_committed` helps avoid reading aborted inputs, yet does not turn database updates and consumed Kafka offsets into an atomic transaction. You then need an idempotent consumer, inbox/outbox, or another consistency design.

## 18. How does transaction timeout affect isolation?

A Kafka producer has **transaction.timeout.ms**. The broker transaction coordinator can abort transactions held open too long. When a transaction aborts, its outputs never appear to `read_committed` consumers.

Example:

~~~text
TX-A begins
   |
   +-- Writes output record to partition P
   |
   +-- Listener calls slow 90s dependency
   |
   +-- transaction timeout 60s
             |
             v
          Broker aborts
             |
             v
read_committed consumer skips TX-A output
~~~

While a transaction has not finished, **LSO can remain held back** and `read_committed` downstream consumers temporarily cannot read records positioned behind the open transaction in the partition. Once the transaction commits/aborts, LSO can advance.

Too low a timeout causes unnecessary aborts. Too high a timeout holds open transactions and LSO stalled for a long time when a producer hangs. Keep transaction scope reasonable and configure HTTP/database dependency timeouts separately.

## 19. Lag on `read_committed` consumers can be misleading

Some dashboards calculate consumer lag as:

~~~text
lag = log_end_offset - committed_offset
~~~

However, a `read_committed` consumer can be bounded by LSO, which sits below LEO while a transaction stays open. Lag measured against LEO then increases even though the consumer cannot read further records behind the unfinished transaction.

Example:

- A producer opens a long-running transaction.
- Another producer continues writing to the same partition.
- LEO rises while LSO stays behind.
- `read_committed` consumer pauses at the stable boundary.
- Dashboard lag rises.

Do not simply increase consumer concurrency to solve this. Check open transactions, producer commit/abort behavior, transaction timeouts, and coordinator health.

Different lag tools may use LEO, HW, or LSO; when analyzing, confirm the exporter's definition to avoid comparing metrics against mismatched baselines.

## 20. Producer fencing, zombie instances, and duplicates

Producer fencing protects transactions from stale instances. However, it **does not protect non-Kafka side effects**.

Suppose instance A calls a Payment API successfully and then loses connectivity. Instance B replaces A using a matching transactional identity to take over. A is fenced and cannot commit the old Kafka transaction. Input is reprocessed on B.

If the Payment API lacks idempotency, B may call the API a second time. Kafka can still commit only one valid output to `read_committed` consumers, yet the payment side effect has been duplicated.

To solve this:

- Use an idempotency key derived from a stable event ID.
- Store processed markers in a database with a unique constraint.
- Place deduplication checks and business updates inside the same database transaction.
- For APIs with ambiguous results, reconcile state before re-issuing side-effecting requests.
- Use a transactional outbox when the database is the business source of truth.

Producer fencing resolves a zombie producer's right to write to Kafka, not distributed transactions across all dependencies.

## 21. Exactly-once and databases: a critical boundary

A consumer reading Kafka, updating a database, and then committing Kafka offsets spans two independent durable systems:

~~~text
Kafka input
     |
     v
Database transaction commit
     |
     v
Kafka offset commit
~~~

If the database commits successfully while the application crashes before the Kafka offset commit, the record is re-read and may update the database twice.

Reversing the order:

~~~text
Kafka offset commit
     |
     v
Database transaction commit
~~~

If the offset commits first and then the database fails, the record may be skipped by the group.

`KafkaTransactionManager` and a database transaction manager can be coordinated by Spring in certain setups, yet never call that a guaranteed atomic two-phase commit unless the system genuinely uses a protocol providing that guarantee. Failures at commit boundaries can still produce inconsistent states.

Common solutions:

- **Inbox / idempotent consumer:** unique event ID, dedup insert and database update in the same transaction.
- **Transactional outbox:** commit business change and event intent in the same database transaction; another publisher sends outbox rows to Kafka.
- **Saga/workflow:** manage state and compensation across multiple services.

Choose an approach based on the primary data store and business consistency boundaries.

## 22. How does a transactional outbox differ from Kafka EOS?

Suppose an Order Service must store an order in a database and emit `OrderCreated`:

~~~text
BEGIN DB TRANSACTION
    INSERT orders(...)
    INSERT outbox_events(event_id, payload, status)
COMMIT DB TRANSACTION

Outbox publisher:
    Read outbox event
    -> Publish to Kafka
    -> Mark sent
~~~

Outbox solves consistency between database business state and event-publishing intent inside one database transaction. The publisher can send duplicates if it crashes between publishing and marking sent, so downstream still needs event IDs and idempotency.

Kafka EOS solves atomicity of Kafka outputs and consumed offsets in Kafka-to-Kafka processing. Both mechanisms complement each other; neither automatically eliminates all duplicate business events across the entire system.

## 23. Ordering and partitions

Kafka guarantees ordering within each partition for records appended in log order. Transactions add visibility rules; they do not create a single global ordering across multiple partitions or multiple topics.

Example transactional send:

~~~text
TX:
   send to orders-output partition 0
   send to orders-audit partition 3
   commit
~~~

A transaction can cause two records to commit or abort together per protocol, yet consumers on two different topics do not necessarily observe them at the exact same physical instant. One consumer can poll topic A before another consumer polls topic B. **Atomic commit does not mean an atomic read snapshot across all consumers.**

If business logic requires ordering per `orderId`, use an appropriate partition key and enforce ordering at the right boundary. Transactions do not automatically fix late-arriving data or key-mapping changes after increasing partition counts.

## 24. Failure scenarios to understand

| Incident | Kafka transaction consequence | What downstream needs |
|---|---|---|
| Listener exception before commit | Transaction aborts/rolls back per policy | `read_committed` hides aborted output; input redelivers |
| Producer crashes between sends | Transaction uncommitted; coordinator may abort | Do not process uncommitted output |
| Transaction commit succeeds, app dies before receiving response | Outcome may be unclear to app | Fencing/idempotency and transaction protocol enable recovery; avoid duplicate non-Kafka side effects |
| Broker/coordinator aborts on timeout | Transactional output excluded from `read_committed` | Input can be re-read |
| Producer fenced by new instance | Old producer loses commit rights | Close old producer, fix identity collision if unintended |
| Consumer uses `read_uncommitted` | May see aborted output | Use `read_committed` when EOS visibility is required |
| Offset committed separately outside transaction | Duplicate window or wrong progress | Commit offsets with output transaction |
| Database write succeeds, Kafka transaction aborts | DB state persists, Kafka output/offset abort | Inbox/outbox/idempotency |
| DLT publish fails | Recovery incomplete | Do not intentionally commit offset as recovered |

Not every request timeout error means the broker aborted the transaction. Inspect the root exception, transaction state, and client contract; handle ambiguous-outcome transactions via the framework rather than blindly retrying commits on a failed producer.

## 25. Retries and recovery in transactional pipelines

A transactional listener can receive the same record multiple times after rollbacks. Distinguish:

1. Internal Kafka client producer request retries.
2. Listener processing retries after transaction abort.
3. Recovering failing records to a DLT once retries are exhausted.
4. Replaying records from a DLT after fixing the root cause.

Transactions protect Kafka outputs of aborted runs, yet each retry layer can execute side effects outside Kafka.

Spring Kafka provides **DefaultAfterRollbackProcessor** for post-rollback handling. If an application uses non-blocking retry topics, verify Spring Kafka version limits with transactional listeners: standard retry-topic patterns in many versions do not support container transactions and batch listeners.

For DLTs on transactional paths, verify whether recovery publishing and recovered offsets are committed via an appropriate recovery transaction. Do not assume every `DeadLetterPublishingRecoverer` automatically writes DLT and source offsets atomically simply because the listener uses Kafka transactions.

## 26. Transaction duration and max.poll.interval.ms

Two key parameters:

- **transaction.timeout.ms:** duration a producer transaction is allowed by the coordinator before timing out and aborting.
- **max.poll.interval.ms:** limit on how long a consumer can go without returning to `poll()` under the group protocol.

A listener running too long can trigger both a transaction timeout and a consumer rebalance. Raising one timeout does not necessarily resolve the other.

Example:

~~~text
Listener processes for 120 seconds
      |
      +-- Kafka transaction timeout 60 seconds
      |      -> coordinator may abort TX
      |
      +-- max.poll.interval.ms 90 seconds
             -> consumer may lose partition ownership
~~~

Recommendations:

- Bound HTTP/database timeouts.
- Reduce record counts / workload per transaction.
- Keep transaction scopes short.
- Measure p95/p99 listener duration and producer commit latency.
- Set `transaction.timeout.ms` within broker `transaction.max.timeout.ms`.
- Monitor rebalances and transaction aborts separately.

If a system must run a job taking several minutes, consider moving the work to an out-of-transaction workflow or emitting a job event and processing asynchronously with idempotency.

## 27. `read_committed` can receive non-transactional records

An often overlooked detail: if only some producers of a topic use transactions, a `read_committed` consumer still sees non-transactional records sent by other producers.

Example:

~~~text
orders-output:
   record A from transactional producer (TX committed)
   record B from regular producer
   record C from transactional producer (TX aborted)

read_committed consumer:
   A -> yes
   B -> yes
   C -> no
~~~

If a business requirement states every record on the topic must be produced via a successful transaction, **that is a requirement on producers and architecture**, not a filter toggleable on consumers. `read_committed` does not enforce producer provenance policies for non-transactional records.

When multiple teams write to one topic, enforce governance on serializers, producer transaction policies, and write ACLs, not only consumer settings.

## 28. Testing transactional producers and isolation

A trustworthy test must observe both **commit results** and consumer **visibility**.

### 28.1. Transaction commit

1. Initialize a transactional producer.
2. `beginTransaction`, send record A.
3. `commitTransaction` succeeds.
4. `read_committed` consumer reads A.
5. Verify record A and offsets within the test scope.

### 28.2. Transaction abort

1. `beginTransaction`, send record B.
2. `abortTransaction`.
3. `read_committed` consumer does **not** receive B as an application event.
4. `read_uncommitted` consumer may observe B depending on position and log data.

### 28.3. Consume–transform–produce rollback

1. Send input record X to the source.
2. Transactional listener sends output Y and throws an exception.
3. Container aborts the transaction.
4. `read_committed` downstream does not see Y from the aborted transaction.
5. Source offset is not committed with the aborted transaction.
6. After fixing the error, the listener reprocesses X and commits output/offset in a new transaction.

### 28.4. Producer fencing

In a test cluster, try initializing a new producer with the same `transactional.id` while the old producer has not closed. Verify the old producer is fenced and the application does not reuse the fenced producer.

### 28.5. Open transactions and LSO

1. Open a transaction and send a record to a partition.
2. Send additional records afterward.
3. Observe the `read_committed` consumer being bounded by LSO.
4. Commit or abort the transaction.
5. Verify the consumer resumes reading stably.

### 28.6. Non-Kafka side effects

1. Listener updates a database or calls a mock HTTP API.
2. Force the Kafka transaction to abort.
3. Redeliver the input record.
4. Verify non-Kafka side effects are protected by event ID/idempotency.

Avoid sharing a production cluster to test aborts, fencing, or transaction timeout changes. Use a test Kafka environment or controlled fault injection.

## 29. Observability and metrics

Track metrics across producers, listener containers, and downstream consumers:

| Signal | Operational question |
|---|---|
| Transaction begin/commit/abort rate | Are transaction aborts spiking abnormally? |
| Transaction duration p95/p99 | Are transactions approaching timeout? |
| Commit transaction latency | Is the coordinator or broker slow? |
| Producer send retries/errors | Are infrastructure errors impacting commits? |
| Producer fencing count | Are there `transactional.id` collisions or zombie producers? |
| Consumer rebalance rate | Are there issues with `max.poll.interval.ms` or membership? |
| `read_committed` lag and oldest record age | Is downstream slow due to processing or LSO? |
| LSO/HW/LEO if exporter supports it | Is an open transaction holding back visibility? |
| Listener business processing latency | Is application logic holding transactions open too long? |
| Rollback/redelivery count | Are source records being reprocessed repeatedly? |
| DLT recovery failures | Are failing records being safely persisted? |
| Business duplicate/idempotency conflicts | Are non-Kafka side effects repeating? |

Metric names depend on Kafka client, Spring Kafka, Micrometer, and exporters. Application-level instrumentation may be needed to measure exact elapsed time from transaction begin to commit/abort.

Never use transaction IDs or event IDs as high-cardinality metric labels; put them in logs/traces with correlation IDs, while aggregating metrics by service, topic, group, and exception class.

## 30. Runbook when EOS behaves unexpectedly

### Step 1: Identify symptoms

- Does downstream see records from aborted transactions?
- Are outputs duplicated?
- Does the consumer group re-read inputs repeatedly?
- Are transaction aborts or producer fencing spiking?
- Is `read_committed` consumer lag rising despite low CPU?

### Step 2: Check producer side

- Does the producer factory have `transactional.id`/`transactionIdPrefix`?
- Do instances use distinct prefixes/identities?
- Does `KafkaTemplate` participate in the right container transaction?
- Does the producer have valid `acks`/idempotence and `transaction.timeout.ms`?
- Are any sends happening outside the transaction when the app assumes they are inside?

### Step 3: Check input offsets

- Is the container managing transactional offset commits?
- Is consumer auto-commit or manual `commitSync` running outside the transaction?
- Is record offset N committed as N+1 on success?
- When a transaction aborts, is the input offset being written separately?

### Step 4: Check consumer isolation

- Has downstream truly set `isolation.level=read_committed`?
- Is there a `read_uncommitted` consumer in another service?
- Does the topic contain non-transactional records from another producer?
- Is lag measured against LEO or LSO?

### Step 5: Check non-Kafka boundaries

- Are duplicates occurring in Kafka outputs or in database/API side effects?
- Are event IDs/idempotency keys stable?
- Are outbox/inbox mechanisms present if database consistency is needed?
- Did a consumer replay from a DLT generate new business events?

### Step 6: Verify recovery

Re-run commit/abort tests, observe `read_committed` visibility, consumed offsets, transaction metrics, and application side effects. Conclude EOS is working properly only once all stated boundaries are verified.

## 31. Common design mistakes

| Practice | Consequence | Right approach |
|---|---|---|
| Enabling transactional producer with `read_uncommitted` downstream | Can read aborted outputs | Configure `read_committed` on downstream needing isolation |
| Enabling `read_committed` while committing input offsets separately | No atomic output+offset | Send offsets inside Kafka transaction/container |
| Calling idempotence "multi-record EOS" | No transaction grouping records | Use transactional producers when needed |
| Sharing the same `transactional.id` across multiple instances | Producers fence one another | Distinct prefixes/identities per instance |
| Calling `executeInTransaction` inside container TX assuming shared offsets | Commit boundary differs from expectation | Let template join the container transaction |
| Calling API/DB expecting Kafka abort to roll back external state | Duplicates or inconsistency | Idempotency, inbox/outbox, sagas |
| Using non-blocking retry topics ignoring container transaction limits | Unexpected retry/offset semantics | Pick version-compatible recovery mechanisms |
| Raising transaction timeout too high | Open TX stalls LSO for long | Keep transaction scope short and monitor duration |
| Reading lag vs. LEO and blaming slow consumer | Misses LSO held back by open TX | Compare transaction state and offset metrics |
| Thinking `read_committed` reads only transactional records | Non-transactional records still appear | Enforce producer policies and topic ACLs |
| Assuming Kafka EOS means listener runs once | Fails to account for redelivery after abort | Separate processing attempts from committed effects |
| Retrying all old producer errors after fencing | Cannot recover old transaction | Reinitialize valid producer, handle fatal errors |

## 32. Production checklist

Before declaring a pipeline has Kafka exactly-once semantics, confirm:

1. Does the producer have `transactional.id`/`transactionIdPrefix` without collisions across concurrent instances?
2. Do producer factory, `KafkaTemplate`, and `KafkaTransactionManager` share the right transactional producer source?
3. Does the listener container actually start and commit Kafka transactions?
4. Are consumed offsets sent into the **same transaction** as Kafka outputs?
5. Is consumer auto-commit disabled when the container manages offsets?
6. Do downstream consumers needing transactional visibility use `read_committed`?
7. Are other producers permitted to write non-transactionally to the same topic?
8. Are transaction timeout, broker max, and `max.poll.interval.ms` aligned with processing times?
9. Is there a rollback/redelivery mechanism suited to transactional listeners?
10. Have commit, abort, fencing, restart, coordinator outage, and LSO been tested?
11. Is monitoring in place for transaction aborts, fencing, `read_committed` lag, and producer errors?
12. When a Kafka transaction aborts after database/HTTP side effects, does the system have idempotency?
13. If using a DLT, are recovery publishing and consumed offsets managed safely?
14. Have incompatible retry-topic patterns been avoided with container transactions?
15. Is there a runbook distinguishing duplicate Kafka outputs from non-Kafka business duplicates?

**Conclusion:** transactional producers and isolation are two complementary halves of an exactly-once Kafka pipeline. A transactional producer ensures Kafka outputs and consumed offsets commit or abort cleanly at the transaction boundary; a `read_committed` consumer observes only committed outputs and filters aborted outputs. Spring Kafka can manage these steps automatically via a transactional `ProducerFactory`, `KafkaTemplate`, and listener container. Still, the exactly-once boundary remains Kafka: to achieve real reliability, keep transaction scopes reasonable, handle rollbacks/fencing, monitor LSO, and design idempotency for all non-Kafka side effects.
