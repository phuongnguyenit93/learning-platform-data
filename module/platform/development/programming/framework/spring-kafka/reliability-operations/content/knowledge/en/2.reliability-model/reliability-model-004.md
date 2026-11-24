# Read, Process, and Write in One Flow

In a Spring Kafka application, a common processing flow reads a record from an input topic, executes business logic, and writes the result to an output topic. For example, a service receives `OrderCreated` from `orders.in`, validates and enriches the order data, and then emits `OrderEnriched` to `orders.enriched` for downstream services to continue processing.

This flow has three clear steps:

1. **Read** — the consumer receives the record and decodes its key, value, and metadata.
2. **Process** — the application validates data and runs business logic to produce a result.
3. **Write** — the producer sends the result to the destination topic.

The reliability pivot is the ordering between writing the result and confirming the input offset. If the application confirms the offset too early, the record can be lost when writing the output fails. If writing the output succeeds but the offset is not yet confirmed, the record can be read again and produce duplicate results. Spring Kafka provides transactions to combine writing output records and confirming input offsets into the same Kafka transaction.

## 1. Viewing the Full Lifecycle of a Record

```text
orders.in
   |
   v
Kafka consumer / @KafkaListener
   |
   v
Deserialize -> Validate -> Process
                         |
                         v
                  KafkaTemplate.send()
                         |
                         v
                   orders.enriched

Listener succeeds    -> commit transaction (output + input offset)
Listener fails       -> rollback; input record may be read again
```

With a listener running in a container-managed transaction, the container starts the transaction before invoking the listener. `KafkaTemplate` uses a producer participating in that transaction. When the listener ends normally, the container adds the processed offset to the transaction and commits. When the listener throws an exception, the transaction rolls back; neither the output record nor the input offset is committed.

This yields **exactly-once processing within the Kafka consume-transform-produce scope**: a committed execution makes output and offset take effect together. It does not mean every line of business code runs only once, nor does it cover systems outside Kafka such as databases, HTTP APIs, or payment systems.

## 2. Read: Receiving Records and Understanding Metadata

`@KafkaListener` is the standard entry point for a Spring Kafka processing flow. A listener can receive just the payload or the entire `ConsumerRecord`. For reliable processing, `ConsumerRecord` is useful because it provides:

- `key()` — routing key for the record, often reused when emitting results.
- `value()` — payload converted by the deserializer.
- `topic()`, `partition()`, and `offset()` — position of the input record, very useful for logging and incident investigation.
- `headers()` — metadata such as correlation ID, trace context, or event type.

For example, a listener receiving an order:

```java
@Component
public class OrderEnrichmentListener {

    private final OrderProcessor processor;
    private final KafkaTemplate<String, Object> kafkaTemplate;
    private final String outputTopic;

    public OrderEnrichmentListener(
            OrderProcessor processor,
            KafkaTemplate<String, Object> kafkaTemplate,
            @Value("${app.topics.orders-out}") String outputTopic) {
        this.processor = processor;
        this.kafkaTemplate = kafkaTemplate;
        this.outputTopic = outputTopic;
    }

    @KafkaListener(
            topics = "${app.topics.orders-in}",
            groupId = "${spring.kafka.consumer.group-id}")
    public void onOrder(ConsumerRecord<String, Order> record) {
        EnrichedOrder result = processor.enrich(record.value());
        kafkaTemplate.send(outputTopic, record.key(), result);
    }
}
```

`Order`, `EnrichedOrder`, and `OrderProcessor` are the application's data types and business components. The example assumes the producer is configured with a serializer suitable for `EnrichedOrder` and the listener container is configured with transactions as shown in the next section.

### Deserialize and Validate

The deserializer is responsible for converting bytes in Kafka into Java types. Keep producer serializers and consumer deserializers consistent, and manage schemas when event structures evolve. A record that fails deserialization can fail before the listener method is ever invoked; therefore, configure deserialization error handling, such as `ErrorHandlingDeserializer`, if the application needs to route malformed records to a dead-letter topic (DLT).

Validate input data before running business logic. Distinguish permanent data errors, such as a missing order ID, from transient errors, such as a customer lookup service temporarily unavailable. These two error categories require different handling policies: invalid records usually need to be isolated or sent to a DLT, while transient errors can be retried.

## 3. Process: Retriable Business Logic

Place business logic in a dedicated service rather than writing all logic inside the listener. The listener orchestrates the flow; `OrderProcessor` produces the business result. This structure makes logic independently testable and clarifies when an exception should return to the container.

```java
@Service
public class OrderProcessor {

    public EnrichedOrder enrich(Order order) {
        if (order == null || order.getOrderId() == null) {
            throw new InvalidOrderException("orderId is required");
        }

        // Execute business rules and create the new result.
        return new EnrichedOrder(
                order.getOrderId(),
                order.getCustomerId(),
                calculatePriority(order));
    }

    private String calculatePriority(Order order) {
        return order.getTotal().signum() > 0 ? "NORMAL" : "REVIEW";
    }
}
```

In practice, the processor may call internal services, look up data, or apply business rules. Pay attention to side effects. A Kafka transaction cannot automatically roll back a database write or a completed HTTP request. If the processor updates a database and the Kafka transaction later rolls back, the database data may still remain changed.

For side effects outside Kafka, choose an explicit strategy:

- Design **idempotent** operations using a stable event ID or business key so repeated calls do not create extra effects.
- Use **transactional outbox** when you need to write to a database and emit events consistently: write business changes and an outbox row in the same database transaction, then let a separate publisher move outbox rows to Kafka.
- Use a saga or compensation workflow when business logic spans multiple systems and cannot share a single distributed transaction.

Do not catch an exception and continue as if processing succeeded. If the listener swallows the exception, the container may treat the run as successful and commit the offset. When you want retries or rollback, let the appropriate exception propagate out of the listener.

## 4. Write: Emitting Results with KafkaTemplate

`KafkaTemplate` is Spring Kafka's primary abstraction for sending records. A common call form is:

```java
kafkaTemplate.send(topic, key, value);
```

Keys matter. Kafka uses the key to select a partition via the partitioner; records with the same key typically go to the same partition and preserve order within that partition. If the flow requires ordering by `orderId`, use `orderId` consistently as the key on both input and output when the data model allows.

In Spring Kafka 3.x, `send()` returns `CompletableFuture<SendResult<K, V>>`. Sending normally happens asynchronously. When the listener runs inside a container-managed Kafka transaction, the producer transaction is flushed and committed at the end of processing; a send failure that prevents committing will fail the processing run. If the application needs to read send metadata, you can attach a callback or wait on the future with a timeout, but avoid blocking the listener thread without a specific reason.

Send results can provide metadata such as output topic, partition, and offset. This information is helpful for logs and tracing, but does not replace confirming that the transaction committed.

## 5. Combining Output and Input Offset with a Kafka Transaction

This is the right approach when a listener reads from Kafka, transforms a record, writes the result back to Kafka, and needs both operations committed together.

### 5.1 Configure the Transactional Producer

With Spring Boot, enable transactions using a transaction ID prefix:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${INSTANCE_ID:local}-
      acks: all
    consumer:
      group-id: order-enricher
      properties:
        isolation.level: read_committed

app:
  topics:
    orders-in: orders.in
    orders-out: orders.enriched
```

`transaction-id-prefix` enables the producer factory to create transactional producers. The prefix must be unique across running application instances to prevent instances from sharing transaction IDs and fencing each other. When running multiple replicas, assign a distinct `INSTANCE_ID` to each replica; do not share the `local` value across concurrent instances.

`acks: all` requires broker acknowledgement according to replicas in the ISR. To make actual durability match requirements, also configure the replication factor and `min.insync.replicas` on the broker/topic. Transactions guarantee atomicity of Kafka operations; they do not replace cluster durability settings.

### 5.2 Attach KafkaTransactionManager to the Listener Container

The listener container must use a `KafkaTransactionManager` created from **the same `ProducerFactory` that `KafkaTemplate` uses**. You can configure the factory using the following pattern (generic types should match the application's producer factory and serializers):

```java
@Bean
KafkaTransactionManager<String, Object> kafkaTransactionManager(
        ProducerFactory<String, Object> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, Order>
orderListenerContainerFactory(
        ConsumerFactory<String, Order> consumerFactory,
        KafkaTransactionManager<String, Object> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, Order>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);
    return factory;
}
```

If using a custom factory name, point the listener to it with `@KafkaListener`'s `containerFactory` attribute. If the application uses Spring Boot auto-configuration, verify the generated transaction manager and producer factory beans, then attach the transaction manager to the right listener container. Avoid creating one `ProducerFactory` for `KafkaTemplate` and another for the transaction manager, because those two producers will not automatically share the same transaction.

### 5.3 What Happens When the Listener Runs?

With the configuration above, the success sequence is:

1. Container starts a Kafka transaction.
2. Consumer receives the input record and invokes the listener.
3. Listener runs business logic and calls `KafkaTemplate.send()`.
4. Producer writes the output record within the open transaction.
5. Listener returns normally.
6. Container sends the processed record's offset into the transaction.
7. Transaction commits; the output record and input offset take effect together.

If processing or sending output raises an error that causes the listener to fail, the transaction rolls back. The offset is not committed, so the input record will be consumed again per the container's retry policy. Output records from a rolled-back transaction will not be visible to `read_committed` consumers.

Consumers reading transactional data should use `isolation.level=read_committed`. If a downstream consumer uses `read_uncommitted`, it can see records from uncommitted or aborted transactions. Each consumer group can have its own isolation setting; verify both consumers of the input topic and consumers reading transactional outputs.

## 6. Without Transactions: Understanding At-least-once

A non-transactional flow can still be reliable if output is sent successfully before the listener finishes and the offset is committed. However, a window exists between the two operations:

```text
Output sent successfully ---- app stops ---- commit input offset
         |                                    |
         +---- output already exists          +---- offset uncommitted
```

When the application restarts, the input record can be read again and duplicate output can be produced. This is **at-least-once** behavior: prioritizing not losing records, while permitting repeated processing.

With a non-transactional record listener, you can wait for broker acknowledgement before the listener returns:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "nonTransactionalRecordListenerFactory")
public void onOrder(ConsumerRecord<String, Order> record) throws Exception {
    EnrichedOrder result = processor.enrich(record.value());

    kafkaTemplate.send(outputTopic, record.key(), result)
            .get(10, TimeUnit.SECONDS);
}
```

This example only illustrates a non-transactional flow: if sending fails or times out, the exception propagates so the container does not treat the record as successfully processed. Choose an appropriate timeout and handle `InterruptedException` properly in production code. When sending succeeds but the offset commit fails, output can still be re-emitted. Make downstream consumers idempotent or deduplicate using a stable event ID.

Do not call `send().get()` mechanically in every listener. Waiting on the future holds the consumer thread longer and lowers throughput. In a container-managed transactional flow, transaction commit already flushes the producer; wait on the future separately only when you need the send result or want to handle send errors right at that point.

## 7. How Do Offsets and AckMode Affect Behavior?

AckMode specifies when the container confirms offsets after a listener succeeds. For record listeners, common choices are:

| AckMode | Confirmation timing | Operational impact |
|---|---|---|
| `RECORD` | After each record is successfully processed by the listener | Easy to reason about per record; fits when clear commit boundaries are desired. |
| `BATCH` | After all records in a single poll are successfully processed | Fewer commits; if a batch fails, more records may have to be reprocessed. |
| `MANUAL` | When the listener calls `acknowledge()`; container commits with batch semantics | Application decides when to ack and must manage it carefully. |
| `MANUAL_IMMEDIATE` | Commits immediately when `acknowledge()` is called on the consumer thread | Tighter control, but easy to create hard-to-follow logic if acked at the wrong time. |

With container transactions, the offset is sent into the Kafka transaction when the container finishes processing per listener/container semantics. Let the container manage offsets in typical consume-transform-produce models; only use manual acknowledgement when there is a specific requirement and you understand how it interacts with transactions.

Do not enable Kafka consumer auto commit for flows that need to coordinate offsets with outputs. Let the Spring Kafka container manage commits. If a batch listener is used, clearly define retries and partial batch handling; semantics differ from per-record listeners.

## 8. Retries, Rollback, and Dead Letter Topic

Not all errors should be handled the same way. A common strategy is:

| Error type | Example | Typically appropriate handling |
|---|---|---|
| Transient | Broker or dependent service briefly unavailable | Bounded retries with backoff. |
| Invalid data | Missing required field, incompatible schema | Route to DLT or quarantine flow for investigation. |
| Unrecoverable business error | Order is in a state that forbids transitioning | Record the reason and handle per business policy; avoid infinite retries. |
| Prolonged infrastructure outage | Database or dependent service is down | Pause/throttle consumption per policy, monitor lag, and restore the dependency. |

In a transactional flow, exceptions roll back the transaction. Spring Kafka provides `DefaultAfterRollbackProcessor` to coordinate seeks and retries after rollback; you can configure attempt limits and dead-letter publishing. When moving a record to a DLT, publishing to the DLT must also be guaranteed: if DLT publishing fails, never silently confirm the original offset as if processing succeeded. Error-handling configuration must match the container's transaction mode.

A useful DLT should preserve source details such as topic, partition, offset, key, timestamp, and exception. Include correlation ID or event ID so records can be traced from input to output or DLT. DLT replay procedures must verify schema compatibility and idempotency before replaying, because replay can rerun business logic.

Retries with backoff help avoid piling load onto a failing dependency. However, prolonged retries can hold partitions and increase consumer lag. Set attempt limits, wait durations, and post-retry exhaustion policies based on the criticality of the flow. Non-blocking retries using retry topics are a different model from blocking retry/rollback; evaluate transaction semantics and record ordering separately before combining them.

## 9. Preserving Ordering and Avoiding Duplicate Processing

Kafka guarantees ordering only within a single partition. If two events for the same order must be processed in order, use the same key so they route to the same partition. Increasing partition counts or changing the partitioner can affect how keys are distributed, so review this when changing topic topology.

Producer idempotence removes certain duplicates caused by producer-layer retries within a producer session. It does not automatically stop the application from re-emitting the same business effect after a consumer rereads an input record. To prevent duplicates at the business level:

- Each event should have a stable `eventId` across retries.
- Downstream services can store processed event IDs with a unique constraint or a deduplication store.
- Update operations should be conditional or versioned to avoid applying an older event multiple times.
- During retries or DLT replays, preserve the original event ID; do not generate a new ID for the same logical event.

Exactly-once in Kafka synchronizes outputs and offsets of a Kafka transaction. Idempotency is still required for databases, APIs, notifications, payments, and any side effects outside that transaction.

## 10. Operational Metrics and Signals to Monitor

A read-process-write flow can be logically sound yet still become unstable under load or dependency incidents. Monitor at least the following signals:

- **Consumer lag** per group and partition to know whether processing keeps up with write rates.
- **Listener processing duration** and output send duration to spot slow processors or brokers.
- **Records read/written**, retry counts, rollback counts, and records routed to DLT.
- **Serialization/deserialization errors** and send errors per topic/partition.
- **Transaction commits/aborts** and producer fencing errors to detect duplicate transaction ID prefixes.

Logs should include topic, partition, offset, key or event ID, and correlation ID. Do not write full sensitive payloads to logs. Use trace context in Kafka headers if the system has distributed tracing.

Listener container concurrency should match the number of partitions the consumer group can process in parallel. Adding threads beyond the partition count does not increase group throughput. If processing a record takes too long, check `max.poll.interval.ms`, `max.poll.records`, and actual processing time to keep the consumer from being marked dead. For long-running work, consider reducing records per poll, optimizing logic, or offloading heavy work to another flow with explicit confirmation design.

Transactions should not stay open excessively long. Transaction duration must be compatible with transaction timeouts, poll intervals, and dependency latency. Keeping a transaction open too long increases timeout risk and forces `read_committed` consumers to wait for the transaction to finish before reading subsequent related data.

## 11. Testing the Happy Path and Failure Points

Tests should cover the entire path from input to output and offset, rather than just asserting that the processor returns the right object. You can use Embedded Kafka or Kafka Testcontainers to verify behavior against a real broker in integration tests.

Useful scenarios include:

1. Send a valid record to the input topic; verify the output has the expected key and payload.
2. Make the processor throw an exception; verify output is not committed and input is retried as configured.
3. Make the broker reject or fail to acknowledge output; verify the listener does not succeed and the offset is not committed early.
4. Stop the application after output is sent but before the offset is committed in a non-transactional flow; verify the system tolerates possible duplicate output and downstream handles it idempotently.
5. With transactions, verify a `read_committed` consumer does not see output from an aborted transaction.
6. Send an undeserializable record or invalid data; verify the record is handled per DLT/quarantine policy.
7. Replay an already-processed event; verify idempotency prevents duplicate side effects.

Integration tests should wait on explicit conditions such as output appearing or offsets reaching expected positions, rather than fixed sleeps. Clean up topics, consumer groups, and containers after each test so stale state does not skew results.

## 12. Common Design Mistakes

- **Committing offsets before sending output:** if sending fails, input is already confirmed and results can be lost.
- **Sending output and swallowing exceptions:** the container may commit the offset even though business logic or sending failed.
- **Using different producer factories:** `KafkaTemplate` does not join the transaction managed by the listener container.
- **Assuming Kafka transactions cover databases or HTTP:** external side effects can still persist after rollback.
- **Reading transactional output with `read_uncommitted`:** consumers can observe records from aborted transactions.
- **Sharing a transaction ID prefix across multiple instances:** causes producer fencing and transaction errors.
- **Infinite retries without backoff:** amplifies load on failing dependencies and keeps consumer lag high.
- **Relying on producer idempotence to prevent all duplicates:** producer idempotence does not replace event IDs and business-level deduplication.

## 13. Choosing a Model for a Flow

| Need | Model to consider |
|---|---|
| Read Kafka, process, write Kafka with atomic output and offset effect | Container-managed Kafka transaction with `KafkaTransactionManager` and shared `ProducerFactory`. |
| Accept at-least-once, can handle duplicates downstream | Send output successfully before listener returns, then let container commit offset; use idempotency. |
| Consistent database update and Kafka event emission | Transactional outbox; do not rely on a single Kafka transaction to commit both systems. |
| Transient errors requiring retries | Blocking retries with backoff or a retry-topic design evaluated separately for ordering and transactions. |
| Unprocessable records | Dead Letter Topic with source metadata, monitoring, and a replay procedure. |

During design, answer three questions clearly: **when is the offset confirmed, what happens if sending output fails, and which side effects sit outside the Kafka transaction?** The answers determine whether the flow provides at-least-once or Kafka-scoped exactly-once, how retries behave, and where idempotency is required.
