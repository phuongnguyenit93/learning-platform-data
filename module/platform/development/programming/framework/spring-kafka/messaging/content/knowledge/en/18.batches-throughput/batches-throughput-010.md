# BatchToRecordAdapter

## 1. What problem does BatchToRecordAdapter solve?

A Kafka consumer retrieves data using `poll()`. One poll can return multiple records across one or more partitions. Spring Kafka supports batch listeners to deliver that entire group of records into a single listener method invocation. This works well when business logic processes in bulk, yet sometimes an application still needs to process and recover from errors record by record.

`BatchToRecordAdapter` bridges both approaches: the listener container continues operating in batch mode, while the adapter passes each record in the batch sequentially to a record listener method. As a result, the application benefits from batch polling while business logic receives individual events.

The adapter is especially useful when you:

- Want the listener to receive individual payloads for cleaner business logic.
- Want to pinpoint the exact failing record inside a batch.
- Want to recover or route a single record to a DLT and continue processing remaining records.
- Use a batch listener container with transactions yet need record-level error handling.

`BatchToRecordAdapter` was added in Spring Kafka 2.4.2. APIs and integration details can vary by version, so check the documentation for the Spring Kafka version your application uses.

## 2. How the adapter works

When the factory enables `batchListener`, the consumer polls a group of records. Instead of invoking the listener once with `List<T>`, `BatchToRecordAdapter` iterates over the messages in the batch and invokes a callback for each record. That callback wires to the record-oriented listener method.

```text
Kafka topic partitions
          |
          v
   KafkaConsumer.poll()
          |
          v
    Batch of records
          |
          v
  BatchToRecordAdapter
          |
          +---- record 1 ----> @KafkaListener(payload)
          |
          +---- record 2 ----> @KafkaListener(payload)
          |
          +---- record 3 ----> @KafkaListener(payload)
          |
          +---- record N ----> @KafkaListener(payload)
```

The key point is that the container still receives a single poll batch. The adapter only changes how the batch is dispatched to the application method. It does not spawn extra consumers, create new partitions, or turn each record into an independent poll request.

A batch can contain records from multiple partitions. Offsets are managed independently per `TopicPartition`; the adapter does not establish a global order across partitions.

## 3. Distinguishing the three listener models

| Model | Container mode | Listener parameter | Method invocation unit |
|---|---|---|---|
| Standard record listener | Record | `T` or `ConsumerRecord<K,V>` | One record per invocation |
| Batch listener | Batch | `List<T>`, `List<ConsumerRecord<K,V>>`, or `ConsumerRecords<K,V>` | One batch per invocation |
| Batch container + `BatchToRecordAdapter` | Batch | `T` or `ConsumerRecord<K,V>` | Adapter invokes the record listener for each record in the batch |

Standard record listener example:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(OrderCreated event) {
    orderService.process(event);
}
```

Batch listener example:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchListenerFactory")
public void listenBatch(List<OrderCreated> events) {
    orderService.processBatch(events);
}
```

Example using a batch container with an adapter still receiving single records:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchToRecordListenerFactory")
public void listenOne(OrderCreated event) {
    orderService.process(event);
}
```

In the third example, the factory configures `setBatchListener(true)` and attaches a `BatchToRecordAdapter`. The method still accepts a single `OrderCreated` per invocation. Do not change the parameter to `List<OrderCreated>` if you want the adapter to call a record listener.

## 4. Configuring DefaultBatchToRecordAdapter

Spring Kafka provides `DefaultBatchToRecordAdapter`. You can configure it on `ConcurrentKafkaListenerContainerFactory`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    batchToRecordListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setBatchToRecordAdapter(new DefaultBatchToRecordAdapter<>());
        factory.setConcurrency(3);
        return factory;
    }
}
```

Then declare a listener accepting a single record:

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "batchToRecordListenerFactory")
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
```

This factory creates batch consumers, and the adapter invokes `onOrder()` sequentially for payloads in the batch. `concurrency=3` creates up to three consumer members for the endpoint per application instance; how many consumers actually get partitions still depends on how many partitions are assigned in the group.

If an application only needs a standard record listener, there is no need to configure a batch container merely to get per-record callbacks. Use the adapter when you intentionally want a batch container and need record-level error handling inside a batch.

## 5. Configuring a recoverer for failed records

`DefaultBatchToRecordAdapter` has two commonly used constructors:

- No-arg constructor: uses a default recoverer that only logs the failed record.
- Constructor taking `ConsumerRecordRecoverer`: lets the application specify how to recover a failed record.

Example using a custom recoverer to persist failed records:

```java
ConsumerRecordRecoverer recoverer = (record, exception) -> {
    log.error("Cannot process topic={}, partition={}, offset={}",
            record.topic(), record.partition(), record.offset(), exception);
    failedRecordRepository.save(record, exception);
};

factory.setBatchToRecordAdapter(
        new DefaultBatchToRecordAdapter<>(recoverer));
```

`ConsumerRecordRecoverer` receives the original record and the exception from the failed listener invocation. If the recoverer finishes and returns normally, the adapter continues to the next record in the batch. If the recoverer throws an exception, the batch is aborted; the container can apply error handling or rollback according to configuration.

This is an important distinction when using the default constructor: the default recoverer merely logs and continues. Logging an error does not mean the record was saved to a DLT or processed successfully in business terms. If you must preserve failed records, configure a recoverer with an explicit recovery action.

## 6. Routing failed records to a Dead Letter Topic

A common recovery approach is using `DeadLetterPublishingRecoverer` as the `ConsumerRecordRecoverer`:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
batchToRecordListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        KafkaTemplate<Object, Object> dltTemplate) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setBatchToRecordAdapter(
            new DefaultBatchToRecordAdapter<>(
                    new DeadLetterPublishingRecoverer(dltTemplate)));
    return factory;
}
```

When the listener throws an exception, the adapter invokes the recoverer with the failing record. If the DLT publish succeeds and the recoverer returns normally, the adapter proceeds to the next record. If the DLT publish fails and the recoverer throws an exception, the batch aborts so the container handles it via its active error mechanism.

When deploying a DLT, configure:

- A DLT topic that exists with a partition count matching your routing strategy.
- A producer template able to serialize original keys/values and preserve required headers.
- Clear retention, access permissions, and DLT monitoring procedures.
- A mechanism to replay records after fixing data or consumer bugs.

If records have heterogeneous payload types or contain raw `byte[]` from deserialization errors, the DLT template needs serializers supporting the actual data types. Do not assume a simple `JsonSerializer` can always handle every failed record.

## 7. Record-by-record error handling flow

Suppose a poll returns three records: `OrderCreated A`, `OrderCreated B`, and `OrderCreated C`. The listener processes A successfully, B throws an exception, and C is valid.

With an adapter and recoverer able to recover B:

```text
Poll batch: [A, B, C]
       |
       v
Adapter calls listener(A) ── succeeds
       |
       v
Adapter calls listener(B) ── throws exception
       |
       v
Recoverer handles B (e.g., publish to DLT)
       |
       +── recoverer returns normally
       |          |
       |          v
       |     Adapter continues
       |          |
       |          v
       |     Adapter calls listener(C)
       |
       +── recoverer throws exception
                  |
                  v
             Abort batch
             container error handling / rollback
```

When the recoverer returns normally, the adapter treats the failed record as handled under the recoverer's policy and continues the batch. Thus, the recoverer must actually finish its required work before returning. If it only logs while business rules demand retaining the record, data can be skipped once the batch commits.

If the recoverer throws an exception, the container knows the batch did not finish. With a transactional container, the transaction may roll back and the batch may be reprocessed per `AfterRollbackProcessor`. With a non-transactional container, retry/seek behavior depends on the error handler, `AckMode`, and Spring Kafka version.

## 8. Relationship with batch listener transactions

When using transactions with a regular batch listener, if the listener throws an exception, Spring Kafka by default does not know which record in the batch caused the error. Consequently, the entire batch may be redelivered after rollback.

`BatchToRecordAdapter` partially addresses this: the container still receives batches, yet the listener is called per record. The adapter can invoke a recoverer for the failing record and continue to subsequent records if recovery succeeds. If the recoverer throws an exception, the batch can abort so the transaction rolls back.

This enables clearer policy choices:

| Record processing outcome | Adapter behavior |
|---|---|
| Listener succeeds | Proceeds to the next record |
| Listener fails, recoverer recovers successfully | Marks record as handled per recoverer policy and continues |
| Listener fails, recoverer throws exception | Aborts batch; container handles error or rolls back |

The adapter does not create an independent Kafka transaction per record. Transaction boundaries are still governed by the listener container and transaction manager. If the container runs one transaction per batch, multiple record-listener invocations can execute inside that same transaction.

If you need Kafka outputs and offsets committed atomically, configure Kafka transactions properly. If the listener updates a database or calls external systems, design suitable transaction coordination or idempotency; `BatchToRecordAdapter` does not automatically provide exactly-once guarantees for external side effects.

## 9. AckMode and offset commits

`BatchToRecordAdapter` does not replace the listener container's offset commit mechanism. The adapter controls invoking the record listener and recoverer; the container still manages offsets based on `AckMode`, transactions, and batch completion status.

Key principles:

- Never call `acknowledge()` before the listener or recoverer completes required actions.
- If the recoverer returns normally after persisting to a DLT, the record can be treated as recovered so the batch continues.
- If the recoverer throws an exception, the batch aborts and offsets are not committed as a normally completed batch.
- When using manual acknowledgment, clarify who owns acknowledging: the listener, a custom adapter, or the batch handler.
- Do not manually commit offsets via the consumer API inside callbacks when the container manages commits, unless following a carefully controlled advanced design.

`BatchToRecordAdapter` does not convert a batch container into a record container. Therefore, do not assume every behavior of a record listener container—such as `AckMode.RECORD` or per-record commit boundaries—applies automatically. Check version documentation and actual configuration before relying on specific commit semantics.

## 10. Ordering when the adapter processes record by record

The default adapter iterates through the provided record list and invokes the callback in order. This preserves invocation order within the batch. However, Kafka guarantees ordering only within a partition; a batch can contain multiple partitions with no global ordering among them.

If the listener runs synchronously, records in the same partition are invoked in read order. If the listener offloads work to an executor or returns before side effects complete, business completion order can diverge from invocation order.

Example to avoid when sequential ordering is required:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchToRecordListenerFactory")
public void onOrder(OrderCreated event) {
    executor.submit(() -> orderService.process(event));
}
```

The listener returns immediately after submitting, so the adapter can move on to the next record while earlier processing is still running. If events sharing the same `orderId` depend on order, process synchronously or build key/partition serialization and acknowledge only after required work finishes.

## 11. Does BatchToRecordAdapter increase throughput?

The adapter does not inherently increase throughput. The consumer still polls in batches, yet the application performs one listener invocation per record. The main benefit is retaining batch polling while gaining record-level error handling semantics.

Compared to a batch listener accepting `List<T>`:

- Can lose bulk-operation gains since the service is invoked per record.
- Easier to identify a failing record and route that specific record to a DLT.
- Adds per-record callback/invocation overhead.
- May reduce poll overhead compared to custom micro-poll designs, though not necessarily faster than a standard record listener container.

If your primary goal is bulk inserts or vectorized processing, a true batch listener is usually a better fit. If your goal is record-level recovery inside a batch container or transaction, `BatchToRecordAdapter` is worth considering.

Measure throughput, p95/p99 processing latency, recovery counts, DLT publish rate, batch size, and consumer lag before concluding the adapter improves performance.

## 12. Customizing BatchToRecordAdapter

Applications can use `DefaultBatchToRecordAdapter` with a `ConsumerRecordRecoverer` or implement a custom `BatchToRecordAdapter` when deeper control is needed. The interface receives the list of Spring `Message<?>`, the list of `ConsumerRecord<K,V>`, acknowledgment, consumer, and the callback to process each message.

A custom adapter can:

- Record metrics before/after each record.
- Attach business context before invoking the callback.
- Classify exceptions to pick an appropriate recoverer.
- Apply event-type-specific recovery rules.
- Decide whether to continue or abort the batch according to application policy.

When implementing a custom adapter, follow these rules:

1. Never skip a record or callback unintentionally.
2. Never swallow exceptions unless the record has been safely recovered.
3. Never acknowledge past unfinished records.
4. Preserve record metadata and headers when forwarding or sending to a DLT.
5. Never run callbacks concurrently without an explicit ordering/offset design.
6. Test shutdown, rebalances, and recoverer exceptions.

If you only need to write to a DLT or store failed records, `DefaultBatchToRecordAdapter` with a recoverer is usually simpler and easier to maintain than a custom adapter.

## 13. When should you use BatchToRecordAdapter?

| Need | Choice |
|---|---|
| Independent per-record processing without needing a batch container | Standard record listener |
| Bulk inserts or processing the whole list together | Batch listener accepting `List<T>` |
| Use a batch container while invoking a business listener per record | `BatchToRecordAdapter` |
| Dedicated DLT for a failing record inside a batch | `DefaultBatchToRecordAdapter` with `DeadLetterPublishingRecoverer` |
| Batch-scoped transactions with per-record error classification | Batch container combined with adapter and matching recoverer |
| Per-record retries with an independent schedule without blocking the partition | Evaluate retry topics / non-blocking retries; `BatchToRecordAdapter` itself does not provide that retry schedule |

Do not adopt the adapter merely because its name contains "batch". It does not turn a record listener method into a bulk listener and does not manage complex retry schedules by itself. Choose the adapter when you need the specific combination of batch polling and per-record callbacks.

## 14. Testing BatchToRecordAdapter

Integration tests should verify listener invocation counts, error handling, and offset outcomes:

1. **Successful batch:** send multiple records and verify the listener is invoked once per record in the poll batch.
2. **Mid-batch failure:** make the second record throw an exception, verify the recoverer receives the exact record, and check whether subsequent records are processed per policy.
3. **Recoverer returns normally:** verify the adapter continues to the next record.
4. **Recoverer throws an exception:** verify the batch aborts and the container error handler or transaction rollback behaves as configured.
5. **DLT:** verify failed records are published to the right topic, preserving required keys/values/headers without losing the original record.
6. **Transactions:** verify commit/rollback behavior when either the listener or recoverer fails.
7. **Ordering:** send a sequence of events with the same key and verify invocations follow partition order; test additionally if the listener dispatches async tasks.
8. **Rebalance/restart:** stop the consumer mid-batch, verify uncommitted records can be redelivered and handled idempotently.
9. **Throughput:** compare batch listener, record listener, and batch-to-record under identical payloads, partition counts, and workloads.

Log `eventId`, topic, partition, offset, and recovery outcomes in tests to confirm exactly which records succeeded, which went to the DLT, and which were redelivered.

## 15. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| Listener receives `List<T>` instead of individual payloads | Factory runs in batch mode without `BatchToRecordAdapter`, or listener signature is built for batches | Attach the adapter to the right factory and use a single record/payload parameter |
| Listener is called per record yet the whole batch rolls back | Recoverer throws an exception or the batch transaction aborts | Inspect root exception, recoverer, and transaction boundary |
| Failed record is merely logged and disappears from the main flow | Using the no-arg constructor that only logs and continues | Configure a recoverer that persists durably or publishes to a DLT |
| Subsequent records are not processed after an error | Recoverer throws an exception that aborts the batch | Check DLT publish, repository, and abort/retry policy |
| DLT publish fails | Serializer does not support record type or topic/permissions are wrong | Check template, serializer, topic, and ACLs |
| Assuming the adapter automatically retries failed records | The adapter only calls the recoverer; it does not provide a backoff/retry schedule itself | Configure a proper recoverer or error-handling/transaction setup |
| Business ordering scrambled | Listener returns before background tasks finish | Process synchronously or serialize by partition/key |
| Throughput does not improve as expected | Each record still needs a listener call; bottleneck is downstream | Measure batch size, processing duration, and consider a true bulk batch listener |

## 16. Implementation workflow

1. Determine whether batch polling is needed for throughput/transactions or if a standard record listener suffices.
2. Configure the factory with `setBatchListener(true)`.
3. Attach `DefaultBatchToRecordAdapter` or a custom adapter to the right factory.
4. Declare the listener accepting a single payload or `ConsumerRecord`.
5. Choose a recoverer: log/persist errors, quarantine, or publish to a DLT.
6. Define clearly when the recoverer returns normally versus when it throws an exception.
7. Configure `AckMode`/transactions properly; do not assume per-record commits solely from per-record callbacks.
8. Test mid-batch errors, DLT routing, rollbacks, redelivery, and ordering.
9. Measure throughput, latency, and lag to confirm the adapter fits the workload.

## 17. Summary

- `BatchToRecordAdapter` fits when the container polls in batches while the application wants to invoke a record listener per record.
- Spring Kafka provides `DefaultBatchToRecordAdapter` since version 2.4.2.
- Configure the adapter via `factory.setBatchToRecordAdapter(...)` after enabling `setBatchListener(true)`.
- `DefaultBatchToRecordAdapter` accepts a `ConsumerRecordRecoverer`; if the recoverer returns normally, the adapter continues to the next record; if it throws an exception, the batch aborts.
- The no-arg constructor only logs failed records and continues; configure an explicit recoverer if records must be saved or routed to a DLT.
- The adapter does not create per-record transactions, does not provide a retry schedule itself, and does not guarantee exactly-once processing.
- Offset commits remain managed by the listener container per `AckMode`/transactions; verify version-specific semantics.
- Kafka preserves ordering per partition; asynchronous work inside the listener can still scramble business completion order.
- The adapter does not automatically boost throughput; adopt it for record-level recovery in a batch container and measure real performance.

With `BatchToRecordAdapter`, applications can keep batch polling while handling each record with dedicated business logic. When combined properly with a recoverer, DLT, and transactions, the consumer pipeline can isolate bad records while maintaining control over batch progress and recoverability.

## References

- [Spring Kafka Reference — Transactions with Batch Listeners](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka API — DefaultBatchToRecordAdapter](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/adapter/DefaultBatchToRecordAdapter.html)
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
