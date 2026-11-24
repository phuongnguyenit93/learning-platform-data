# isolation.level and read_committed

In Kafka, a producer can write multiple records within a transaction and then **commit** or **abort** the entire transaction. Consumers need a way to distinguish records belonging to completed transactions from records whose outcome is still pending. The **isolation.level** property controls how a consumer reads those transactional records.

The two main values are:

- **read_uncommitted**: reads records that Kafka has made visible to consumers within replication bounds, including records belonging to open transactions or transactions that are later aborted.
- **read_committed**: returns only transactional records belonging to committed transactions; skips records from aborted transactions and pauses at the boundary of any unfinished transaction.

In the **Durable Consumer** chapter, isolation level is part of the data-reading contract. If an application reads output from a producer using Kafka transactions, choosing **read_committed** ensures the consumer only processes committed results. However, it does not by itself provide end-to-end exactly-once across the whole application and does not replace offset commits, business idempotency, or database transactions.

## 1. Kafka Transactions from the Consumer's Perspective

Kafka transactions allow a producer to send a group of records to one or more partitions and conclude that group with a commit or an abort. For example, a service might consume an **OrderCreated** event, produce **InventoryReserved** and **PaymentRequested** events, and write both output events within the same Kafka transaction.

If the transaction commits, the output records become valid for consumers using **read_committed**. If the transaction aborts, those records are never returned to **read_committed** consumers.

Overall flow:

~~~mermaid
flowchart TD
    P["Transactional producer"] --> B["beginTransaction"]
    B --> S["send record(s) to Kafka"]
    S --> D{"Business outcome"}
    D -->|Success| C["commitTransaction"]
    D -->|Failure| A["abortTransaction"]
    C --> R["read_committed consumer receives record"]
    A --> X["read_committed consumer skips record"]
    S --> U["read_uncommitted consumer may see record before completion"]
~~~

The key point is that transaction status is managed by Kafka. The consumer does not infer whether a transaction succeeded from a record's payload, key, or headers. The broker records transaction state and appends corresponding control markers into the partition logs.

A single transaction can span records across multiple partitions and topics. Kafka coordinates the transaction coordinator with participating partitions to finalize the transaction. A **read_committed** consumer relies on that state to decide which records are returned.

### 1.1 Types of Records a Consumer May Encounter

At the application level, distinguish three cases:

1. **Non-transactional records**: records sent by a regular producer. These records remain readable by both **read_uncommitted** and **read_committed** once within the readable range.
2. **Records in committed transactions**: both isolation levels can return these records.
3. **Records in open or aborted transactions**: **read_uncommitted** may return these records; **read_committed** waits for the transaction to finish and discards the records if the transaction aborts.

Thus, **read_committed** does not mean a consumer only reads records sent by transactional producers. Non-transactional records are still returned. If a topic mixes transactional and non-transactional data, the consumer can receive both.

### 1.2 Transaction Markers

Kafka stores internal markers to indicate transaction commit or abort on partitions containing transactional records. These markers are control records used by the broker and consumer protocol; applications do not receive them as ordinary business messages.

Consumers do not need to read markers manually or filter by headers. The broker and client apply the isolation level to decide which records are returned.

## 2. The Two Values of isolation.level

The Kafka consumer supports two values for the **isolation.level** configuration:

| Value | Behavior | When Appropriate |
|---|---|---|
| **read_uncommitted** | Reads transactional records as soon as they are fetchable, even if the transaction has not ended or later aborts | Consumers that need to observe every written record and tolerate processing uncommitted transactional data |
| **read_committed** | Returns only records from committed transactions; skips aborted transaction records; waits at open transaction boundaries | Consumers treating transactional output as confirmed business data |

The Kafka consumer default is **read_uncommitted** unless configured otherwise. Enabling transactions on the producer does not automatically force all consumers into committed mode. Each consumer client must have the appropriate isolation level configured.

### 2.1 read_uncommitted

**read_uncommitted** is the Kafka consumer's default read mode. The name can be misleading: it does not mean consumers arbitrarily read unreplicated data. Consumers remain bounded by what the broker exposes according to replication state. The difference lies in transaction state.

With **read_uncommitted**:

- Non-transactional records are read normally.
- Records from an open transaction may be returned before the producer commits.
- Records from a transaction that later aborts may already have been processed by the application.
- The consumer cannot undo already-executed side effects if the producer aborts afterward.

For example, a producer sends **PaymentApproved** inside a transaction that has not yet committed. A **read_uncommitted** consumer can receive the record and send a confirmation email. If the producer aborts the transaction later, Kafka marks the record as aborted, but the sent email cannot be automatically recalled.

This mode suits use cases requiring early visibility and tolerating records that might abort, such as certain monitoring tools or analytics streams accepting provisional data. For consumers performing irreversible business actions, evaluate carefully.

### 2.2 read_committed

**read_committed** filters records by transaction state:

- Returns non-transactional records once within the readable range.
- Returns transactional records after the transaction commits.
- Skips records belonging to aborted transactions.
- Does not return records from open transactions.
- Does not read past the boundary of an unfinished transaction on the affected partition.

This mode fits when consumers must process committed results from transactional producers, especially in consume-transform-produce pipelines or business flows using Kafka transactions.

A **read_committed** consumer does not know whether a transaction is business-valid. It only knows the Kafka transaction committed. If a producer commits a record with erroneous content, the consumer still receives it. Business validation, schema validation, and idempotency must still be enforced by the application.

## 3. Last Stable Offset and Read Boundaries

The most important operational difference when running **read_committed** is the **Last Stable Offset (LSO)**.

A Kafka partition has multiple offset watermarks. Two must be distinguished in this context:

- **High Watermark (HW)**: the replication boundary up to which **read_uncommitted** consumers can typically read.
- **Last Stable Offset (LSO)**: the safe boundary for **read_committed** consumers, constrained by the earliest open transaction on the partition.

LSO marks the position a committed consumer can read up to before having to wait on an unfinished transaction. If an open transaction sits at a low offset, records at higher offsets on the same partition may be held back from **read_committed**, even if those records have already been appended and replicated.

Example of a partition with the following records:

| Offset | Content | Status |
|---:|---|---|
| 100 | OrderCreated | Non-transactional |
| 101 | InventoryReserved | Transaction T1 open |
| 102 | PaymentRequested | Transaction T1 open |
| 103 | CustomerNotified | Non-transactional |
| 104 | AuditRecorded | Non-transactional |

While T1 has not committed or aborted:

- **read_uncommitted** can read up to HW and see records at 101, 102, 103, and 104.
- **read_committed** can read record 100, but stops at the LSO boundary at the unfinished transaction.
- Records 103 and 104 must wait even though they do not belong to T1, because they sit behind an open transaction on the same partition.

Once T1 commits, LSO advances and **read_committed** can read 101, 102, 103, and 104. If T1 aborts, the consumer skips 101 and 102 and continues reading valid records after them.

~~~mermaid
flowchart LR
    A["Offset 100<br/>non-transactional"] --> B["Offset 101-102<br/>open transaction"]
    B --> C["Offset 103-104<br/>subsequent records"]
    subgraph RU["read_uncommitted"]
      R1["Can read past open transaction"]
    end
    subgraph RC["read_committed"]
      R2["Reads up to LSO boundary then waits"]
    end
~~~

The diagram illustrates a single partition. An open transaction on this partition does not automatically block other partitions. Consumers can still receive records from other partitions if their LSO advances.

### 3.1 Why Can LSO Slow Down a Consumer?

A long-running open transaction can pin LSO at an old offset. When that happens:

- New records continue to be appended by producers.
- Brokers can continue replication.
- HW can advance.
- LSO does not advance past the unfinished transaction.
- **read_committed** consumers receive no records beyond that boundary.

From the application's perspective, the consumer may appear alive, throw no exceptions, and poll successfully yet receive no new records from the blocked partition. Lag measured against log end or HW may grow while lag measured against LSO does not reflect the same number.

This is why transaction age, transaction coordinator health, HW/LSO, and consumer lag must be monitored together. Looking only at the consumer process or total lag is insufficient to diagnose the root cause.

### 3.2 Long-Open Transactions and Timeouts

Transactions should be short-lived and bounded. Producers must commit or abort within the time allowed by the broker. The producer's **transaction.timeout.ms** configuration defines the transaction timeout; the broker caps the maximum via corresponding settings such as **transaction.max.timeout.ms**.

If a producer hangs, crashes, or fails to complete a transaction, the transaction coordinator can time out and end the transaction. Once aborted, LSO can advance after state and markers are processed.

Never set a huge timeout just to avoid transaction timeouts. Prolonged transactions pin LSO, force **read_committed** consumers to wait, and increase latency on participating partitions. Investigate why transactions fail to finish: slow downstream, code holding transactions too long, network faults, unavailable coordinator, or stuck producers.

## 4. Offsets, Filtered Records, and Gaps in the Log

A Kafka offset is a position in the partition log. Offsets are not contiguous sequence numbers of records visible to the application.

With **read_committed**, records from aborted transactions are filtered out of returned results, yet their offsets remain in log history. Hence, a consumer might receive a record at offset 100 and the next record at offset 104. Offsets 101–103 may belong to aborted transactions or be omitted due to other isolation/compaction reasons.

Offset gaps are normal behavior. Never assume:

- The next offset always equals the current offset plus one.
- The number of records returned in a poll equals the offset difference.
- Every skipped offset represents a lost record.
- The consumer must manually increment offsets by one to step past aborted records.

The Kafka client manages read positions and consumer group offsets based on log offsets. Applications should use each record's actual offset metadata for logging and investigation.

### 4.1 Offset Commit and Transaction Commit Are Two Separate Concepts

Keep these distinct:

- **Producer transaction commit**: confirms a group of transactional records is complete and eligible to be visible to **read_committed** consumers.
- **Consumer offset commit**: records the position a consumer group has processed so reading resumes there on restart.
- **Database transaction commit**: confirms data changes in a database.

These three commits are not automatically equivalent. A producer transaction commit does not mean consumers have processed the records. A consumer offset commit does not mean database side effects committed. A database commit does not automatically mark Kafka records committed.

In a Kafka exactly-once pipeline, the application can coordinate writing output records and committing input offsets in the same Kafka transaction. Downstream consumers then use **read_committed** to see only output from committed transactions.

## 5. Configuring isolation.level in a Kafka Consumer

**isolation.level** is a consumer configuration. It is not a producer setting and does not alter ACK or replication policies.

Valid values:

~~~properties
isolation.level=read_committed
~~~

Or if keeping the default mode:

~~~properties
isolation.level=read_uncommitted
~~~

It can be configured directly via the Java client:

~~~java
Properties props = new Properties();

props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
          "kafka-1:9092,kafka-2:9092,kafka-3:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG,
          "billing-read-model");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class);
props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG,
          "read_committed");
~~~

Set **read_committed** on every consumer instance that needs to read transactional data by commit state. If an application has multiple consumer factories or multiple listener types, verify the effective configuration of each factory.

### 5.1 Configuration in Spring Boot

Spring Boot can pass the isolation level via consumer properties. Example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: billing-read-model
      auto-offset-reset: earliest
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

In Spring Boot versions supporting the dedicated property, **spring.kafka.consumer.isolation-level** can also be used instead of the property map. Use the style matching your project's Boot version and verify the final value on the ConsumerFactory.

**enable-auto-commit: false** is commonly set so the container or application controls offset commit timing. It is not a prerequisite for **read_committed** to work; the two settings address different concerns.

### 5.2 Java Configuration for DefaultKafkaConsumerFactory

When creating a factory manually:

~~~java
@Bean
ConsumerFactory<String, OrderEvent> consumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
              "kafka-1:9092,kafka-2:9092,kafka-3:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG,
              "order-read-model");
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
              StringDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
              JsonDeserializer.class);
    props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG,
              "read_committed");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
              false);

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

If the application has multiple **ConsumerFactory** beans, configuring one factory does not automatically apply to the others. Check which listener container factory each **@KafkaListener** uses.

## 6. Combining read_committed with a Transactional Producer

**read_committed** is only transactionally meaningful when producers actually use Kafka transactions. A producer needs a **transactional.id** stable per logical instance and the transaction API to begin, commit, or abort transactions.

Java client example:

~~~java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
          "kafka-1:9092,kafka-2:9092,kafka-3:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
          StringSerializer.class);
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
          StringSerializer.class);
props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
          "inventory-service-instance-1");

KafkaProducer<String, String> producer =
    new KafkaProducer<>(props);

producer.initTransactions();

try {
    producer.beginTransaction();

    producer.send(new ProducerRecord<>(
        "inventory-events", "sku-42", "InventoryReserved"
    ));

    producer.send(new ProducerRecord<>(
        "order-events", "order-1001", "OrderReady"
    ));

    producer.commitTransaction();
} catch (Exception ex) {
    producer.abortTransaction();
    throw ex;
}
~~~

In this example, two records are sent to two different topics within the same transaction. A **read_committed** consumer only receives these records when the transaction commits. If the transaction aborts, committed consumers skip them.

In production code, handle transaction exception types properly for your Kafka client version. Some exceptions are retriable; some fatal errors require closing the producer or creating a new one. Never call **abortTransaction()** blindly when the producer is already in a fatal state or fenced. Follow the client's proper lifecycle and error handling.

### 6.1 transactional.id and Producer Fencing

**transactional.id** allows Kafka to identify a producer capable of continuing a transaction identity across restarts. When a new producer initializes with the same transactional ID, the old producer can be fenced to prevent two producers from writing simultaneously under one identity.

This protects transaction correctness, provided IDs are managed properly:

- Each active producer instance needs an appropriate identity.
- Never assign the same transactional ID to two concurrently running independent instances.
- When restarting the same logical instance, fencing invalidates the stale producer.
- Handle **ProducerFencedException** as an error requiring stopping the old producer and recovering under the new lifecycle.

In multi-pod systems, assign a unique transactional ID or prefix per running instance. Never assign the exact same static ID to every pod.

### 6.2 Transaction Commit and Abort

When **commitTransaction()** succeeds, Kafka finalizes the transaction and records become visible to **read_committed**. When **abortTransaction()** succeeds, records in the transaction are marked aborted and skipped by committed consumers.

If the application loses connectivity during commit, the outcome may be ambiguous to the caller. Never assume a transaction definitely aborted just because the client timed out. Rely on the transaction lifecycle, producer identity, and recovery procedures; when retrying business sends, still include an event ID to deduplicate at the application layer if needed.

## 7. Consume-Transform-Produce and Exactly-Once in Kafka

A major use case for **read_committed** is the consume-transform-produce pipeline:

1. The consumer reads an input record.
2. The application performs transformation.
3. The producer writes an output record.
4. The input record's offset is sent into the same transaction as the output.
5. Kafka commits the transaction.
6. Downstream consumers using **read_committed** read the committed output.

If the transaction aborts, neither the output record nor the input offset sent in that transaction is committed. The input can be reprocessed via consumer recovery mechanics.

~~~mermaid
sequenceDiagram
    participant C as Input consumer
    participant A as Application
    participant K as Kafka
    participant D as Downstream consumer
    C->>K: Poll input record
    K-->>C: Input record
    C->>A: Process
    A->>K: Begin transaction
    A->>K: Produce output record
    A->>K: Add input offset to transaction
    A->>K: Commit transaction
    K-->>A: Commit success
    D->>K: Fetch with read_committed
    K-->>D: Committed output record
~~~

This forms the basis of Kafka exactly-once semantics within Kafka's boundary. Achieving it requires coordinating a transactional producer, sending offsets into the transaction, and appropriate consumer isolation.

### 7.1 Why Must Input Offsets Be Included in the Transaction?

If output commits without committing the input offset in the same transaction, restarting the application can re-read the input and generate duplicate output. If the input offset commits before output commits, a failure between the two steps can lose output.

Putting the offset into the same transaction lets Kafka finalize both outcomes as one unit:

- Transaction commits: output is published and input offset is updated.
- Transaction aborts: output is not exposed to **read_committed**, and the input offset is not updated by that transaction.

In the Java client, producers support **sendOffsetsToTransaction(...)**. In Spring Kafka, the listener container can manage transactions and offsets for consume-transform-produce flows when configured transactionally.

### 7.2 read_committed on Downstream Consumers

Consumers reading pipeline output should set **isolation.level=read_committed**. If downstream uses **read_uncommitted**, it can receive output before the transaction completes or receive output from an eventually aborted transaction. Upstream transaction guarantees are then lost at the downstream read boundary.

Every consumer in the chain must be configured consistently with desired semantics. A topic does not automatically force consumers to use **read_committed**.

### 7.3 Limits of Exactly-Once

Kafka transactional exactly-once does not automatically extend to side effects outside Kafka.

For example, a listener may:

- Write to a database.
- Send an email.
- Call an HTTP API.
- Write to a file or object storage.

If the database commits successfully yet the Kafka transaction aborts, the database retains the change. Kafka cannot roll back a database transaction without dedicated coordination. Likewise, a sent email cannot be unsent when a Kafka transaction aborts.

For external side effects, use appropriate patterns such as:

- Transactional outbox when the database is the business source of truth.
- Inbox/deduplication table when the consumer must handle repeated events safely.
- Idempotency keys when calling external APIs.
- Sagas or compensation when business workflows span multiple independent systems.

Never describe a pipeline as end-to-end exactly-once solely because Kafka transactions are enabled.

## 8. Spring Kafka and read_committed

Spring Kafka provides integration for transactional producers and listener containers. When properly configured, the container can start a Kafka transaction for listener processing, participate in sending output via **KafkaTemplate**, and send input offsets into the transaction.

### 8.1 Spring Boot Configuration

Illustrative configuration example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      transaction-id-prefix: ${INSTANCE_ID}-orders-
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
    listener:
      ack-mode: record
~~~

Meaning:

- **transaction-id-prefix** enables creating transactional producers in Spring Kafka.
- The prefix must be unique across active application instances. **INSTANCE_ID** must be provisioned stably and distinctly per pod/instance.
- **isolation.level: read_committed** ensures the consumer receives only committed transactional results.
- **enable-auto-commit: false** lets the container manage offsets according to processing lifecycle.
- **ack-mode** must match how the listener and transactional container are configured. With container-managed transactions, offsets are sent into the transaction by the container's mechanism; never mix manual acks arbitrarily without understanding the semantics.

When supported by your Boot/Spring Kafka version, **spring.kafka.consumer.isolation-level** can also be used instead of the property map. Verify your project's property binding and confirm the final value on ConsumerFactory.

### 8.2 Transactional KafkaTemplate

Example listener consuming an event, building an output event, and sending via **KafkaTemplate**:

~~~java
@Component
class OrderProcessor {

    private final KafkaTemplate<String, OrderReady> kafkaTemplate;

    OrderProcessor(KafkaTemplate<String, OrderReady> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-processor"
    )
    public void handle(OrderCreated event) {
        OrderReady output = new OrderReady(
            event.orderId(),
            event.customerId()
        );

        kafkaTemplate.send(
            "order-ready",
            event.orderId(),
            output
        );
    }
}
~~~

When the listener container is configured for Kafka transactions, sending via a transactional **KafkaTemplate** can join the transaction managed by the container. The container finalizes the transaction and handles input offsets according to the transaction lifecycle.

If the listener throws an exception, the transaction typically rolls back and the input offset is not committed in that transaction; the record can be redelivered. Configure rollback/retry/DLT per business policy. Never catch an exception and merely log it if you want the transaction to roll back: swallowing the exception and returning normally makes the container treat processing as successful.

### 8.3 Transaction Manager and Container Factory

With Java configuration, you can create a transactional producer factory and Kafka transaction manager. Illustrative example:

~~~java
@Bean
ProducerFactory<String, Object> producerFactory(
        KafkaProperties kafkaProperties,
        @Value("${app.instance-id}") String instanceId) {

    Map<String, Object> props =
        kafkaProperties.buildProducerProperties();

    DefaultKafkaProducerFactory<String, Object> factory =
        new DefaultKafkaProducerFactory<>(props);

    factory.setTransactionIdPrefix(
        instanceId + "-orders-"
    );

    return factory;
}

@Bean
KafkaTransactionManager<String, Object> kafkaTransactionManager(
        ProducerFactory<String, Object> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

This is a structural example; adjust generic types, property builders, and listener container factories to match your Spring Boot/Spring Kafka version. Spring Boot may auto-configure some beans when a transaction prefix is declared; do not create duplicate beans if auto-configuration already provides them.

Crucially, the listener container must actually use the intended transactional producer/transaction manager. Merely declaring a **KafkaTransactionManager** bean in the application context does not guarantee listeners run inside transactions if the container factory is not wired properly.

### 8.4 Verifying Effective Configuration

In operations, verify:

- The listener's ConsumerFactory has **isolation.level=read_committed**.
- The ProducerFactory has a transaction ID/prefix.
- Prefixes differ across active instances.
- The listener container uses the expected transaction manager or container transaction mechanism.
- The injected **KafkaTemplate** uses the corresponding transactional producer factory.
- Input offsets are sent into the transaction when EOS is required.
- Downstream consumers also use **read_committed**.

Do not check YAML files alone. Multiple factories, customizers, or profiles may override settings. Inspect the ConsumerFactory/ProducerFactory used by listeners at runtime.

## 9. Error Handling and Recovery in Transactional Listeners

Transactions change how listeners handle errors. An exception can roll back the entire Kafka transaction, including output records sent during the transaction and the input offset.

### 9.1 Listener Fails Before Commit

Example:

1. Listener receives input.
2. Listener sends output via transactional KafkaTemplate.
3. A subsequent step throws an exception.
4. The container rolls back the transaction.
5. Output records from that transaction are invisible to **read_committed** consumers.
6. The input offset is not committed in the transaction.
7. The input can be re-read via recovery mechanics.

This prevents publishing output while advancing input offsets without coordination.

### 9.2 Retries and Rollbacks

Distinguish transient errors from unrecoverable errors:

- Transient errors such as downstream timeouts or broker interruptions can retry with backoff.
- Permanent data errors can be routed to a DLT after an appropriate number of attempts.
- Broad configuration or authentication errors require alerting and fixing root causes, not infinite retries.

For transactional listeners, configure rollbacks and redeliveries using an appropriate error handler/AfterRollbackProcessor. If DLT publishing must occur in a fresh transaction, configure recovery transactions explicitly per your Spring Kafka version. Never assume every DLT publish automatically runs inside or outside the rolled-back transaction by default.

### 9.3 Aborted Transactions

Records from aborted transactions are not returned by **read_committed** consumers. If a consumer uses **read_uncommitted**, it may already have processed those records before abort. Therefore, whenever downstream flows require transactional semantics, isolation levels must be set consistently from the start.

### 9.4 Producer Fencing

If an old producer is fenced because a new producer instance reused its transactional ID, transaction operations on the old producer will fail. This usually signals duplicate ID configuration or an instance lifecycle issue.

Never retry infinitely on a fenced producer. Shut down the stale producer and let the instance holding valid ownership continue per recovery procedures.

## 10. Observing read_committed in Production

**read_committed** consumers can be blocked by open transactions even while brokers continue receiving and replicating records. Monitor signals related to both transactions and read progress.

### 10.1 Consumer Metrics

Monitor:

- Consumer lag by group, topic, and partition.
- Records received per poll.
- Time between polls and processing latency.
- Consumer position and committed offset.
- Partition assignments and rebalances.
- Listener rollback/retry counts.
- Age of the oldest record being processed.
- Duration without progress per partition.

Understand how your monitoring tool computes lag. A dashboard comparing committed offset to log end/HW may report higher lag than the records currently readable at LSO. Never conclude a consumer is slow from a single aggregate number.

### 10.2 Transaction and Partition Metrics

Where available, monitor:

- Active open transaction count and transaction age.
- Transaction commit/abort rates.
- Transaction timeouts and transaction coordinator errors.
- Producer fencing events.
- LSO and HW per partition, or the gap between them.
- ISR/replication health since transaction markers must also be written and replicated.
- Partitions whose LSO has not advanced for a prolonged period.

Exact metric names depend on Kafka version and monitoring exporters. Verify actual exported metrics in your environment before creating alerts.

### 10.3 Signs of a Transaction Pinning LSO

A common incident pattern:

- Producers are still sending records.
- HW keeps rising.
- LSO on one partition stays frozen.
- **read_committed** consumers receive no new records on that partition.
- The consumer process shows no obvious errors.
- Other partitions continue processing normally.

When encountering this pattern, check long-open transactions, hung producers, coordinator state, and timeouts. Simply scaling consumer concurrency will not let new consumers read past the LSO of a blocked partition.

### 10.4 Distinguishing Transaction Lag from Processing Lag

Growing lag can stem from multiple causes:

- Increased producer throughput.
- Slow consumer processing.
- Consumer not polling or constantly rebalancing.
- Downstream bottlenecks.
- LSO pinned by an open transaction.
- Partition without a leader or degraded replication.

Correlate producer rate, HW, LSO, consumer position, processing latency, and downstream metrics. Determine whether records are unreadable yet, read but unprocessed, or processed without offset commit.

## 11. Common Operational Scenarios

| Scenario | read_uncommitted | read_committed | Action |
|---|---|---|---|
| Producer sends non-transactional records | Readable | Readable | No transactional difference |
| Transaction commits successfully | Reads records | Reads records | Verify transaction and downstream progress |
| Transaction aborts | May have read records prior to abort | Skips records | Use read_committed for business consumers needing committed results |
| Transaction still open | May read records inside transaction | Waits at LSO | Inspect producer and transaction duration |
| Long-open transaction at low offset | Can read subsequent records up to fetch limits | Subsequent records on same partition are blocked | Find the transaction pinning LSO |
| Consumer restarts after skipping aborted records | Resumes from committed offset | Resumes from committed offset; offsets may have gaps | Do not treat offset gaps as data loss |
| Producer fenced | May see previously written records | Sees only committed transactions | Restore producer ownership and transaction lifecycle |

## 12. Misconceptions to Avoid

**"read_committed means every record must be sent by a transactional producer."** False. Non-transactional records are still returned. Isolation level only filters records by transaction status when they belong to a transaction.

**"read_uncommitted reads unreplicated data."** False. The main difference is transaction isolation. Consumers remain bounded by Kafka's replication read rules.

**"read_committed automatically enables producer transactions."** False. Producers must be configured transactionally and use the transaction API. Consumer isolation does not change how producers send records.

**"read_committed is identical to database READ COMMITTED."** Not completely. Similar name, different mechanism. Kafka filters records by Kafka transaction state and LSO; it does not provide database snapshot isolation.

**"If a transaction aborts, all executed side effects are rolled back."** False. Kafka can suppress transactional output records and omit committing offsets in that transaction, but external emails, HTTP calls, or database commits are not automatically rolled back.

**"Enabling read_committed is enough for exactly-once."** False. You must coordinate transactional producers, input offsets in transactions, consumer group semantics, and appropriate components. External side effects still require dedicated mechanisms.

**"If the consumer receives no records, the producer has not written them."** False. Records may already be appended and replicated yet held behind an unfinished transaction's LSO.

**"Skipped offsets mean lost records."** False. Committed consumers skip records from aborted transactions; log offsets still advance across those positions.

**"Increasing consumer concurrency will clear a partition stuck at LSO."** False. Multiple consumers reading the partition still cannot read past an unfinished transaction boundary.

## 13. Investigation Procedure When read_committed Receives No Records

When producers report successful sends yet consumers see no records, isolate systematically:

1. Identify the topic, partition, key, event ID, and expected offset.
2. Confirm whether the producer uses transactions or sends non-transactionally.
3. If transactional, confirm whether the transaction committed or aborted; check **commitTransaction()** results and coordinator errors.
4. Check whether the consumer actually has **isolation.level=read_committed**.
5. Check whether the record sits before or after the partition's LSO.
6. Compare LSO and HW to determine if an open transaction is pinning the read boundary.
7. Check transaction age, producer health, transactional ID, and fencing.
8. Check consumer assignment, position, committed offset, and deserialization/listener errors.
9. Once the transaction finishes, verify LSO advances and the consumer resumes receiving records.
10. Reconcile event IDs and business effects to avoid re-sending business operations that already committed but merely had delayed visibility.

Never immediately reset consumer group offsets before knowing whether records aborted, sit behind LSO, or were already processed. Resetting offsets can trigger replays and duplicate side effects.

## 14. Testing read_committed

Test in a staging environment with broker and transaction configurations matching production.

### 14.1 Transaction Commit

- Create a transactional producer.
- Send a record inside a transaction.
- Hold the transaction open and verify a **read_committed** consumer has not received it yet.
- Commit the transaction.
- Verify the **read_committed** consumer receives the record.
- Verify a **read_uncommitted** consumer can observe the record before commit.

### 14.2 Transaction Abort

- Send a record inside a transaction.
- Let **read_uncommitted** poll while the transaction is open.
- Abort the transaction.
- Verify the **read_committed** consumer does not return the aborted record.
- Verify **read_uncommitted** may have received the record before abort.
- Verify offsets of subsequent valid records can exhibit gaps.

### 14.3 Transaction Pinning LSO

- Open a transaction and write a record to a test partition.
- Leave the transaction unfinished.
- Write additional records after it on the same partition.
- Verify **read_committed** stops at LSO.
- Commit or abort the transaction.
- Verify LSO advances and the consumer resumes reading.

### 14.4 Consume-Transform-Produce

- Consumer reads input.
- Transactional producer writes output and sends input offset into the transaction.
- Commit the transaction.
- Verify downstream **read_committed** receives output and the input offset updated.
- Repeat with a transaction abort; verify output is not exposed and input can be reprocessed.

### 14.5 Producer Fencing and Timeouts

- Initialize a transactional producer.
- Initialize another producer with the same transactional ID in a test environment.
- Verify the old producer is fenced by Kafka's mechanism.
- Test transaction timeout and LSO advancement after the transaction ends.
- Record errors and recovery duration.

Each test needs dedicated topics/partitions, traceable event IDs, stop conditions, and pass criteria. Never run fault injection or fencing tests against live production producers serving real traffic.

## 15. Configuration and Operations Checklist

**Consumer**

- [ ] Consumers reading transactional output configure **isolation.level=read_committed**.
- [ ] All relevant consumer factories are configured consistently.
- [ ] Consumer group offsets are managed per processing requirements.
- [ ] Applications tolerate offset gaps and do not assume contiguous offsets.
- [ ] Metrics exist for lag, position, commits, and processing progress.

**Producer Transactions**

- [ ] Transactional producers have properly managed **transactional.id** or prefixes.
- [ ] Transactional IDs/prefixes are unique across active instances.
- [ ] Transactions are short-lived with explicit commit/abort paths.
- [ ] Retriable, fatal, and fencing exceptions are handled properly.
- [ ] Transactions are not held open while waiting long on external non-Kafka work.

**Consume-Transform-Produce**

- [ ] Output records and input offsets share the same Kafka transaction when EOS is required.
- [ ] Downstream consumers use **read_committed**.
- [ ] Listener exceptions trigger rollbacks per desired policy.
- [ ] Retries, DLT, and recovery transactions are explicitly configured.
- [ ] External side effects have proper idempotency/outbox/inbox or compensation.

**Observability and Recovery**

- [ ] Monitor transaction commits/aborts, transaction age, and fencing.
- [ ] Monitor LSO/HW and stalled partitions.
- [ ] Distinguish processing lag from transaction-pinned LSO lag.
- [ ] Maintain a runbook for investigating records missing after producer send.
- [ ] Rehearsed commit, abort, LSO stall, and producer fencing in an appropriate environment.

**isolation.level=read_committed** ensures consumers process only results from committed Kafka transactions. For this mechanism to work effectively, producers must manage transactions properly, consumers must use the right isolation level, and operators must monitor both LSO and open transactions. Combined with committing input offsets in the same transaction, it forms the foundation for Kafka-scoped consume-transform-produce exactly-once; side effects outside Kafka still require dedicated protection by design.

