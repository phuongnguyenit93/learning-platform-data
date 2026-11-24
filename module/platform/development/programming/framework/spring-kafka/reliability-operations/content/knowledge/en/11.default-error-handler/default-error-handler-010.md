# BatchListenerFailedException

## 1. Role in Spring Kafka Batch Processing

When a batch listener receives multiple records in a single invocation, the listener may process some records successfully and then encounter an error on a specific record. If it merely throws a regular exception, the container does not know which records in the batch completed and which one caused the failure.

**BatchListenerFailedException** is a specialized Spring Kafka exception used to report the position of the failing record in a batch. When paired with **DefaultErrorHandler**, it helps the error handler separate successfully processed records from the failing record and those following it.

For example, a poll returns five records:

~~~text
Index in batch:      0        1        2        3        4
Record:              A        B        C        D        E
Outcome:         success  success   error   not yet   not yet
                                           processed processed
~~~

If record C causes an error, the listener can throw **BatchListenerFailedException** with index 2. **DefaultErrorHandler** knows records at indices 0 and 1 completed, while record C is the starting point for retry or recovery.

This exception does not retry records, send to a DLT, or commit offsets by itself. It provides positional information to the error handler configured on the container.

## 2. Why Is Pinpointing the Failing Record Important?

Batch listeners are commonly used to process multiple records together to reduce overhead or leverage bulk operations. However, a single batch can contain valid records and failing records mixed together.

Suppose the listener receives these events:

| Index | Event | Processing Outcome |
|---:|---|---|
| 0 | Order A | Success |
| 1 | Order B | Success |
| 2 | Order C | Data error |
| 3 | Order D | Not yet processed |
| 4 | Order E | Not yet processed |

If the listener only throws **RuntimeException**, the error handler does not know the error occurred at Order C. With a batch listener, **DefaultErrorHandler** may have to retry the entire batch because it lacks the information to establish an exact boundary.

When the listener throws **BatchListenerFailedException** and specifies index 2, the error handler can:

1. Treat records prior to index 2 as processed.
2. Commit offsets corresponding to the completed portion per container semantics.
3. Seek or redeliver starting from the failing record onward.
4. Retry the failing record according to the configured BackOff.
5. When retries are exhausted, invoke the recoverer for the failing record if configured.
6. Continue processing the remaining records per the error handler's policy.

Exact handling also depends on Spring Kafka version, container configuration, error handler, and recovery policy. The key point is that the exception tells the handler where in the batch the failing record sits.

## 3. Structure and How to Use the Exception

The **BatchListenerFailedException** class lives in package:

~~~java
org.springframework.kafka.listener.BatchListenerFailedException
~~~

A commonly used constructor when the listener knows the failing record's index:

~~~java
throw new BatchListenerFailedException(
    "Could not process order event",
    cause,
    failedIndex
);
~~~

Where:

- Message describes the error in human-readable form.
- Cause is the original exception thrown by business logic or a dependency.
- **failedIndex** is the zero-based position of the failing record in the batch list.

For example, if the third record in the list causes an error, the index passed is 2.

Do not pass 1-based ordinal numbers, Kafka offsets, partition numbers, or indices from a different list. The error handler needs an index matching the exact list of records currently being processed by the listener.

### 3.1. Index Is the Position in the Batch

Suppose the listener receives:

~~~java
List<ConsumerRecord<String, OrderCreated>> records
~~~

When the record at **records.get(3)** fails, pass index 3:

~~~java
throw new BatchListenerFailedException(
    "Order validation failed",
    exception,
    3
);
~~~

This index is not the Kafka offset. A record can have offset 50 yet sit at index 0 in the batch. A batch can also contain records from multiple partitions, so offsets do not even form a single contiguous sequence.

| Concept | Example | Use as failedIndex? |
|---|---|---|
| Index in List | **records.get(2)** | Yes |
| Kafka offset | **record.offset() == 102** | No |
| Partition | **record.partition() == 3** | No |
| 1-based record position | 3rd record | No, must convert to index 2 |

### 3.2. Preserving Metadata with ConsumerRecord

A batch listener can receive a list of payloads or a list of **ConsumerRecord**. When pinpointing failing records is needed, **ConsumerRecord** provides helpful metadata such as topic, partition, offset, key, timestamp, and headers.

Example:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    // Process batch
}
~~~

Keeping the record list simplifies logging and error investigation. If the listener only receives **List<OrderCreated>**, indices still work, provided the application ensures payloads and metadata stay consistently aligned.

## 4. Combining with DefaultErrorHandler

**DefaultErrorHandler** is Spring Kafka's standard error handler for retrying, seeking, and recovering when listeners fail to process records. With batch listeners, it can use **BatchListenerFailedException** to pinpoint the failing record.

Example configuring a recoverer that sends failed records to a dead-letter topic:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    var backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

In this example, **FixedBackOff(1_000L, 2L)** specifies a 1-second pause between retries and allows two retries after the initial processing attempt. Once retries are exhausted, the recoverer is invoked to handle the failed record.

Attach the error handler to the batch listener container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setCommonErrorHandler(kafkaErrorHandler);

    return factory;
}
~~~

These examples assume the application has already configured an appropriate **ConsumerFactory**, serializers/deserializers, and KafkaTemplate. The DLT publisher needs write permission on the destination topic, and the DLT topic must exist or be allowed to auto-create per cluster policy.

## 5. Example of a Batch Listener Throwing BatchListenerFailedException

A typical usage pattern processes each record in the list and throws the exception at the failing index:

~~~java
@Service
public class OrderBatchListener {

    private final FulfillmentService fulfillmentService;

    public OrderBatchListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment",
        containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void consume(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (int i = 0; i < records.size(); i++) {
            ConsumerRecord<String, OrderCreated> record = records.get(i);

            try {
                fulfillmentService.process(record.value());
            }
            catch (RuntimeException ex) {
                log.error(
                    "Order event processing failed: topic={}, partition={}, offset={}",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    ex
                );

                throw new BatchListenerFailedException(
                    "Could not process order event",
                    ex,
                    i
                );
            }
        }
    }
}
~~~

If the record at index 2 fails, the listener stops the loop and throws the exception with index 2. The error handler has sufficient information to handle the slices before and after the failed record.

Do not continue processing records after an error and then still throw the exception with the earlier index unless business logic guarantees the state of those later records. When the handler redelivers the remainder, side effects may repeat. If parallel processing within a batch is desired, track outcomes per record and clearly establish which records finished before reporting failure.

## 6. Processing Flow with BatchListenerFailedException

Suppose a poll returns five records on the same partition:

~~~text
Poll batch:
  index 0 -> offset 100
  index 1 -> offset 101
  index 2 -> offset 102  <-- error
  index 3 -> offset 103
  index 4 -> offset 104
~~~

The listener processes offsets 100 and 101 successfully, but offset 102 fails. It throws **BatchListenerFailedException** with index 2.

With **DefaultErrorHandler** and standard seeking, the high-level flow is:

~~~text
Batch listener
     |
     | processes offsets 100, 101
     | offset 102 throws error
     v
BatchListenerFailedException(index=2)
     |
     v
DefaultErrorHandler
     |
     +-- marks slice before index 2 as processed
     |
     +-- commits appropriate offsets for completed slice
     |
     +-- seeks/redelivers from offset 102 onward
               |
               v
         Retry failed record
               |
        +------+------+
        |             |
      Success    Retries exhausted
        |             |
        v             v
    Continue       Recover failed
    batch          record (e.g. DLT)
                      |
                      v
                Process subsequent records
~~~

On the same partition, if offsets 100 and 101 completed, the committed offset can advance to 102, meaning the consumer will continue reading from offset 102. When multiple partitions appear in a batch, offsets are managed independently per partition; you cannot derive a single shared commit offset from a list index.

After the failed record is processed or recovered, remaining records continue according to the error handler's retry/recovery behavior. Inspect actual logs and offsets in your running version if your application uses complex batches or multiple partitions.

## 7. What Happens If BatchListenerFailedException Is Not Used?

If a batch listener throws a regular exception such as **IllegalStateException**, the error handler does not know which record caused the failure.

In that case, **DefaultErrorHandler** uses fallback batch retry behavior: the entire batch may be retried. This is a safe fallback when there is no information to distinguish completed records from failed ones, though it can cause successfully processed records to execute again.

Example:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        fulfillmentService.process(record.value());
    }
}
~~~

If **process()** throws an exception, the listener supplies no error index. The error handler must process the batch according to its fallback policy.

Comparison:

| How Error Is Thrown | Info Error Handler Receives | Common Consequence |
|---|---|---|
| **BatchListenerFailedException** with index | Knows the failed record | Can commit preceding slice and retry from failed record |
| Regular exception | Does not know which record failed | May retry the entire batch |
| Listener catches error and does not rethrow | Container may treat listener as complete | Offsets may be committed despite business failure |

If the listener can identify the failing record, supply that information. If an error happens in a bulk operation spanning the entire batch where individual records cannot be isolated, a regular exception may be the more appropriate choice.

## 8. Retry and BackOff

**DefaultErrorHandler** combines with BackOff to decide wait durations and retry counts. Example:

~~~java
var backOff = new FixedBackOff(2_000L, 3L);
var errorHandler = new DefaultErrorHandler(recoverer, backOff);
~~~

With this configuration, the handler pauses 2 seconds between retries and allows three retries under the BackOff policy. Total elapsed time also depends on listener duration, network, broker, DLT publishing, and any application-level retries.

### 8.1. Transient Errors and Non-Retryable Errors

Not every exception should be retried the same way.

| Error Category | Example | Recommended Handling |
|---|---|---|
| Transient errors | DB connection reset, HTTP 503, dependency timeout | Bounded retry with backoff |
| Data errors | Malformed payload, missing required field | Usually do not retry long; recover or DLT |
| Configuration errors | Wrong topic, missing ACL, incompatible serializer | Fix config/permissions; do not retry indefinitely |
| Recoverable business errors | Order state not ready due to eventual consistency | Choose retry policy matching business wait window |

You can configure non-retryable exceptions using **DefaultErrorHandler**'s classification APIs, for example:

~~~java
errorHandler.addNotRetryableExceptions(IllegalArgumentException.class);
~~~

Only apply this classification if that exception truly represents an error unrecoverable via retry. If an exception can wrap transient errors, classify based on causes and application semantics.

### 8.2. Exhausting Retries and the Recoverer

Once retry attempts are exhausted, the recoverer is invoked for the failed record. The recoverer can:

- Log and mark the record as recovered per policy.
- Publish the record to a DLT.
- Persist the record to a dedicated error store.
- Trigger a manual handling workflow.

If the recoverer fails to publish to the DLT, ensure the send failure is not treated as successful recovery. Grant the principal WRITE permission on the DLT, observe publish futures, and handle recovery errors per operational policy.

## 9. Dead-Letter Topics and Failed Records

**DeadLetterPublishingRecoverer** is commonly used to publish records that exhausted retries to a DLT. It can preserve the original payload, key, and headers while adding headers describing the exception and source record depending on configuration.

Example creating a recoverer:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(kafkaTemplate);
}
~~~

By default, the destination can be derived from the record's original topic and partition. If using a custom DLT naming scheme or custom partition mapping, configure a destination resolver aligned with your topology.

When using a DLT, keep in mind:

- The DLT must exist or the broker must permit topic creation per policy.
- DLT partition count must fit the partition-mapping strategy.
- The producer principal needs WRITE permission on the DLT.
- Investigation/replay consumers need READ permission on the DLT and READ on their consumer group.
- Sensitive data in payloads/headers must be protected just like on the source topic.
- Have a replay or manual-handling process so DLT backlogs do not sit indefinitely.

**BatchListenerFailedException** identifies the failing record; the recoverer decides what to do with that record after retries exhaust. The two components play distinct roles.

## 10. Handling Batches Containing Multiple Partitions

A single poll can return records from multiple partitions. The index in **BatchListenerFailedException** is the index in the list received by the listener, not an offset and not a partition identifier.

Example:

~~~text
Index 0 -> partition 0, offset 10
Index 1 -> partition 1, offset 20
Index 2 -> partition 0, offset 11  <-- error
Index 3 -> partition 1, offset 21
~~~

If index 2 fails, the failing record is partition 0, offset 11. Preceding records in the list may belong to partition 1. The error handler must manage offsets per partition rather than blindly committing every offset below the error index.

This is why you should pass the exact index in the list received by the listener, retain **ConsumerRecord** metadata, and let **DefaultErrorHandler** perform commits/seeks per Kafka partition semantics.

Never compute an offset manually by subtracting one from the failed record's offset. Offsets within a partition may have gaps due to compaction, transaction markers, or non-record entries seen by the consumer. Let the framework manage offsets based on actual records in the poll.

## 11. Complete Batch Listener Configuration

A combined example showing consumer factory, batch listener factory, and error handler:

~~~java
@Configuration
public class KafkaBatchConfiguration {

    @Bean
    public DefaultErrorHandler batchErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory,
                    DefaultErrorHandler batchErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setCommonErrorHandler(batchErrorHandler);

        return factory;
    }
}
~~~

Listener:

~~~java
@Service
public class OrderBatchListener {

    private final FulfillmentService fulfillmentService;

    public OrderBatchListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        id = "orders-batch-listener",
        topics = "orders.created",
        groupId = "order-fulfillment",
        containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void consume(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (int index = 0; index < records.size(); index++) {
            var record = records.get(index);

            try {
                fulfillmentService.process(record.value());
            }
            catch (RuntimeException ex) {
                throw new BatchListenerFailedException(
                    "Failed to process order event",
                    ex,
                    index
                );
            }
        }
    }
}
~~~

This code illustrates wiring the listener to the error handler. In a real application, add imports, deserializers, producer serializers for the DLT, security properties, and destination topic settings. Avoid creating multiple error handler beans for similar purposes with different retry policies without clearly binding which factory uses which bean.

## 12. BatchListenerFailedException and Parallel Processing

A batch listener may want to process records concurrently using an executor or reactive pipeline. In that case, be very careful with indices.

If tasks run concurrently, record index 4 might fail before index 1 finishes. **BatchListenerFailedException** reports an error position, but it does not manage in-flight side effects on other threads by itself.

Before throwing the exception, the application must know:

- Which records already finished side effects.
- Which records are still running.
- Which records have not started yet.
- Whether remaining work can be safely stopped or cancelled.
- Whether retrying an already-completed record causes duplicates.

A simpler strategy is processing sequentially within the batch and throwing immediately upon error. If parallel processing is necessary, collect results by index, wait for tasks to finish or cancel per policy, and only then report failure to the container. Side effects must be idempotent because crashes can happen at any time before commit.

Never throw the exception with an index lower or higher than the record that actually failed just to manipulate retries. Doing so can cause completed records to re-run or failing records to be skipped.

## 13. BatchListenerFailedException and Kafka Transactions

When a listener container uses Kafka transactions, error handling follows transaction rollback semantics and **AfterRollbackProcessor** configuration. Do not mechanically apply non-transactional **DefaultErrorHandler** commit/seek descriptions to transactional containers.

In transactional consume-transform-produce, the listener processes a batch and sends outputs within a transaction. If an exception aborts the transaction, outputs inside the transaction are not committed along with input offsets. After rollback, **AfterRollbackProcessor** decides how records are redelivered or recovered.

**BatchListenerFailedException** can supply the failed record position for batch flows supporting those semantics, yet exact behavior depends on Spring Kafka version and rollback processor configuration. When using transactions, check documentation/APIs for your exact version—especially how pre-error batch offsets commit and how post-rollback recovery runs.

Kafka transactions do not cover DB or HTTP service transactions. If a listener writes to a DB and then the Kafka transaction rolls back, the DB does not automatically roll back. Use outbox/inbox or DB transactions with idempotency to bridge this boundary.

## 14. Observability and Diagnostics

When operating with **BatchListenerFailedException**, log thorough metadata for failed records and monitor retries/recovery.

| Metric / Field | Meaning |
|---|---|
| Failed record topic | Topic containing the failing record |
| Failed record partition | Partition of the failing record |
| Failed record offset | Record's position in the partition |
| Failed batch index | Record's position in the list received by the listener |
| Exception class | Error type and retryability |
| Retry attempt | Attempt count for processing the record |
| BackOff delay | Wait interval between retries |
| Recovery result | Whether record was recovered, sent to DLT, or still failing |
| DLT ingress rate | Rate of records routed to DLT |
| Consumer lag | Group backlog |
| Processing duration | Execution time for the batch and individual records |

Structured log example:

~~~text
listener=orders-batch-listener
groupId=order-fulfillment
topic=orders.created
partition=2
offset=1052
batchIndex=3
exception=OrderValidationException
action=retry
~~~

Do not put event IDs or order IDs into high-cardinality metric labels. Record them in logs or traces to trace specific events.

### 14.1. Signals Requiring Investigation

- Same index failing repeatedly: inspect record data and error determinism.
- Retry rate rising while DLT stays flat: inspect BackOff, processing time, and retry success rate.
- DLT ingress spiking suddenly: check schemas, producer versions, and downstream dependencies.
- Consumer lag climbing alongside batch processing duration: check for slow bulk calls or overly long synchronous processing.
- Records before failed index reprocessed: check offset commits, rebalances, transactions, and side-effect idempotency.
- DLT publishing failing: check producer principal, ACLs, topic existence, and serializers.

## 15. Common Usage Mistakes

**Using a 1-based index.** Java List indices start at 0. Passing the wrong index makes the error handler compute the wrong batch boundary.

**Passing Kafka offset instead of index.** Offset is the position in the partition, whereas failed index is the position in the list received by the listener.

**Throwing a regular exception even when the failed record is known.** The error handler may have to retry the whole batch, re-running already-processed records.

**Catching the exception and only logging it.** Normal listener return can make the container treat the batch as successfully processed.

**Throwing BatchListenerFailedException after continuing to process remaining records.** The handler may redeliver records that already caused side effects; establish per-record state before reporting failure.

**Assuming the exception sends records to the DLT by itself.** The recoverer configured on the error handler determines recovery; the exception only supplies failed record info.

**Not configuring a retry policy.** Default BackOff may not fit application latency and dependencies. Choose retry counts and delays intentionally.

**Not separating transient errors from data errors.** Retrying a malformed payload multiple times does not make the payload valid.

**Forgetting DLT permissions.** Error handling may run properly yet recovery publishing fails due to missing WRITE access on the DLT topic.

**Not making side effects idempotent.** Records can be redelivered after crashes, rebalances, or rollbacks. Databases/APIs must guard against duplicate effects.

**Using non-transactional semantics on transactional listeners.** Transactional containers have their own rollback processor and commit behavior; verify exact configuration.

## 16. Adoption Workflow

1. Confirm the listener is genuinely a batch listener and the container uses **DefaultErrorHandler** or a handler supporting the same semantics.
2. Receive batches as an ordered list; prefer **ConsumerRecord** when metadata is needed.
3. Process record-by-record while tracking the current record's index.
4. When a record fails, throw **BatchListenerFailedException** with the cause and exact zero-based index.
5. Choose a BackOff aligned with error types, SLAs, and processing time limits.
6. Configure a recoverer if a DLT or other error storage mechanism is needed.
7. Ensure the DLT publisher has compatible serializers, topics, and ACLs.
8. Make side effects idempotent to withstand redeliveries.
9. Monitor failed indices, topic/partition/offset, retries, recovery, DLT, and consumer lag.
10. If using Kafka transactions, verify rollback semantics and **AfterRollbackProcessor** for your running Spring Kafka version.
11. Test failure cases on the first, middle, and last records of a batch in a test environment to verify actual behavior.
12. Document retry/recovery policies and DLT handling procedures in the runbook.

## 17. Combined Example: Processing an OrderCreated Batch

A consumer receives a batch of four events:

~~~text
Index 0: OrderCreated(order-100) -> success
Index 1: OrderCreated(order-101) -> success
Index 2: OrderCreated(order-102) -> validation error
Index 3: OrderCreated(order-103) -> unprocessed
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int index = 0; index < records.size(); index++) {
        var event = records.get(index).value();

        try {
            fulfillmentService.process(event);
        }
        catch (OrderValidationException ex) {
            throw new BatchListenerFailedException(
                "Invalid order event",
                ex,
                index
            );
        }
    }
}
~~~

With index 2, **DefaultErrorHandler** knows the failing record is OrderCreated(order-102). Preceding records can be recorded as processed, while the failing record is retried per BackOff. If retries exhaust and the recoverer publishes successfully, the failed record is routed to the DLT; subsequent records can then be re-read and processed.

To prevent creating duplicate fulfillments on replay, the service can use a stable **eventId** and an inbox table with a unique constraint. Recording the event ID and creating the fulfillment must share the same DB transaction. If the consumer crashes after DB commit but before Kafka commits the offset, redelivery will recognize the event was already processed.

If OrderCreated(order-102) is an unrecoverable data error, retrying repeatedly only stalls the batch. You can configure this exception type as non-retryable or use short retries before moving to the DLT. If the error is a transient DB timeout, retrying with backoff can succeed without manual intervention.

## 18. Key Takeaways

**BatchListenerFailedException** is the signal telling Spring Kafka which record in a batch listener failed. The index must be the zero-based position in the record list of the current listener invocation; it is not a Kafka offset or partition number.

When paired with **DefaultErrorHandler**, the exception lets the framework process the pre-error slice, retry the failing record, and continue the remainder per retry/recovery policy. If the failing record is not identified and only a regular exception is thrown, the handler may have to retry the entire batch.

The exception does not retry, commit, or publish to a DLT by itself. Configure the error handler, BackOff, and recoverer explicitly, log metadata for failed records, and protect side effects with idempotency. For transactional listeners, additionally verify rollback semantics and **AfterRollbackProcessor** for your actual Spring Kafka version.

