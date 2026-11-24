# Batch Listeners and Record Listeners in Spring Kafka

Spring Kafka supports two ways to receive data in a listener: a **record listener** processes one record per method invocation, whereas a **batch listener** receives a set of records returned by a single poll and processes them in one invocation. Both use the same Kafka consumer and listener container, yet differ in input shape, processing organization, error handling, and offset commit timing.

Record listeners are usually easier to control for individual events, retries, and business ordering. Batch listeners can reduce method-call overhead and fit bulk operations, but require clearer design when only a single record in a batch fails. The right choice depends on throughput, ordering requirements, latency, error handling, and business idempotency.

## 1. Where Do Records and Batches Come From?

A Kafka consumer reads data by polling. A single poll can return multiple records from one or more partitions assigned to that consumer.

~~~text
Kafka topic
  partition 0: A1, A2, A3, A4
  partition 1: B1, B2, B3
                  |
                  v
            KafkaConsumer.poll()
                  |
                  v
             Poll result
             A1, A2, B1, A3, B2, A4, B3
                  |
          +-------+-------+
          |               |
          v               v
     Record listener   Batch listener
          |               |
     calls method      calls method once
     multiple times,   with the poll's
     one record each   record set
~~~

With a record listener, the container takes each record in the poll result and invokes the listener for each one. With a batch listener, the container passes the poll's record set to the listener in a single invocation.

A poll does not necessarily return the maximum possible number of records. The result depends on available data, partition assignments, fetch settings, and the max.poll.records limit. A single consumer can also receive data from multiple partitions simultaneously.

## 2. What Is a Record Listener?

A record listener receives one record per method invocation. The application can receive the deserialized payload directly or receive a ConsumerRecord to access Kafka metadata.

Example receiving payload:

~~~java
@Component
public class OrderRecordListener {

    private final OrderService orderService;

    public OrderRecordListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

The container calls the method once per record. If a poll returns 50 records, the listener can be invoked up to 50 times for those records, depending on actual record count and error handling.

If key, partition, offset, timestamp, or headers are needed, accept ConsumerRecord:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-service"
)
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    log.info(
            "Received order: topic={}, partition={}, offset={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key()
    );

    orderService.process(record.value());
}
~~~

A record listener fits when:

- Each event has its own business rules.
- Per-record retries and recovery are required.
- Data errors must be handled independently.
- Idempotency by event ID needs to stay simple.
- Processing duration per individual event must be controlled.
- Intra-partition ordering is critical and sequential processing is appropriate.

A record listener does not mean a consumer reads only one record per poll. The consumer can still poll many records; the container simply invokes the method separately for each record.

## 3. What Is a Batch Listener?

A batch listener receives multiple records in a single method invocation. With Spring Kafka, the factory must be configured for batch mode, after which the method can accept a List of payloads or a List of ConsumerRecord.

Example receiving a payload list:

~~~java
@Component
public class OrderBatchListener {

    private final OrderService orderService;

    public OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void onOrders(List<OrderCreated> events) {
        orderService.processBatch(events);
    }
}
~~~

Example receiving full metadata for each record:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        log.info(
                "topic={}, partition={}, offset={}",
                record.topic(),
                record.partition(),
                record.offset()
        );

        orderService.process(record.value());
    }
}
~~~

One batch listener invocation corresponds to the set of records returned by a single consumer poll. That set can contain records from multiple partitions. Order is guaranteed within each partition by offset order; do not assume a global business order across partitions.

A batch listener is useful when:

- Multiple records can be processed in a single bulk operation.
- Database writes can be combined into a batch.
- Method invocation overhead or per-record transaction startup cost needs to be reduced.
- Business logic accepts batch processing and has an appropriate error strategy.
- Throughput needs to be raised by leveraging batch APIs on the target system.

A batch listener does not automatically make all processing faster. If each record is still processed sequentially and takes the same time, the gain may be small. If the batch is too large, processing one poll can take too long and increase the risk of exceeding max.poll.interval.ms.

## 4. Configuring Record Listeners and Batch Listeners

### Configuring a Record Listener

Record is the default listener type in many Spring Boot configurations. It can be declared explicitly:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      max-poll-records: 500
    listener:
      type: single
      ack-mode: record
      concurrency: 3
~~~

With a record listener, the container calls the method once per record. AckMode RECORD commits after the listener successfully processes each record.

### Configuring a Batch Listener via Spring Boot

To use a batch listener with the auto-configured factory:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      max-poll-records: 500
    listener:
      type: batch
      ack-mode: batch
      concurrency: 3
~~~

In Spring Boot, listener type can be configured as single or batch depending on the version. Check configuration property metadata for your Boot version if property names or types differ.

AckMode BATCH is the natural choice when you want to commit after the entire polled batch has been processed. With a batch listener, the method must complete successfully before the container considers the batch handled under normal flow.

### Creating Dedicated Factories in Java

If an application needs both listener types in the same context, creating two dedicated factories keeps intent clear:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    recordKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.setBatchListener(false);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD
        );

        return factory;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.setBatchListener(true);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.BATCH
        );

        return factory;
    }
}
~~~

Select the corresponding factory on the endpoint:

~~~java
@KafkaListener(
        id = "orderRecordListener",
        topics = "orders",
        groupId = "order-records",
        containerFactory = "recordKafkaListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}

@KafkaListener(
        id = "orderBatchListener",
        topics = "orders",
        groupId = "order-batches",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

This example uses two different group IDs to illustrate two independent consumer groups. In a real system, do not have two listener groups read the same topic if both perform identical side effects without a clear business reason. If they represent two alternative implementations, activate only one group in production or use separate topics/test environments.

## 5. Comparing Record Listeners and Batch Listeners

| Criterion | Record listener | Batch listener |
|---|---|---|
| Method parameter | Single payload or ConsumerRecord | List of payloads, List of ConsumerRecord, or supported batch type |
| Method invocation count | Once per record | Once per poll batch |
| Business processing | Event by event | By set of events |
| Error handling | Easy to identify failing record | Must identify failing record in batch or retry entire batch |
| Retry | Usually easy to retry per record | May retry partial or full batch depending on error handler |
| Offset commit | Can use RECORD or other modes | Typically uses BATCH; semantics depend on ack mode |
| Throughput | Good for per-record processing | Can be higher if target system supports bulk |
| Latency | Record can be processed immediately once poll returns | May need to process entire batch |
| Ordering | Easy to keep sequential intra-partition order | Must preserve order within batch when business requires |
| Memory | Typically holds less data at listener layer | May hold entire batch during processing |

Neither option is always better. Measure throughput, processing latency, commit overhead, consumer lag, and retry cost under realistic workloads.

## 6. Acknowledgments and Offset Commits

Listener type determines callback shape; AckMode determines when offsets are committed. These two concepts are related but not interchangeable.

Common modes:

| AckMode | Behavior |
|---|---|
| RECORD | Commits after each record listener processes successfully |
| BATCH | Commits after all records from one poll have been processed |
| TIME | Commits when ackTime interval is reached |
| COUNT | Commits when ackCount records are reached |
| COUNT_TIME | Commits when either ackCount or ackTime is reached |
| MANUAL | Listener invokes acknowledge; container handles commits per batch semantics |
| MANUAL_IMMEDIATE | Acknowledging on the consumer thread can trigger an immediate commit |

With a record listener, RECORD can reduce the number of records replayed after a crash at the cost of more frequent commits. BATCH can reduce commit overhead, though if the consumer stops before the batch finishes or commits successfully, uncommitted records may be redelivered.

With a batch listener, BATCH is usually the clearest option: the method processes the entire record set and the container commits offsets after the callback succeeds. If the method fails, the error handler decides how to retry and recover.

Do not commit offsets before protected side effects complete. If the listener updates a database and the process stops before committing, records can be redelivered. Therefore, both record listeners and batch listeners require idempotency if reprocessing can produce duplicate effects.

## 7. Error Handling in a Record Listener

With a record listener, an exception is normally tied directly to the record the listener is processing. A CommonErrorHandler such as DefaultErrorHandler can retry the record with backoff and then recover or send it to a DLT when retries are exhausted.

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

If process throws an exception, the container passes the error to the error handler. Example configuration:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    var backOff = new FixedBackOff(1000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

With FixedBackOff(1000L, 2L), the error handler waits one second between retries and allows two retries after the initial attempt. If it still fails, the recoverer can send the record to a DLT. Attach the handler to the actual listener container factory.

Record listeners make identifying failing events and logging metadata simpler. Still, if the record already updated the database before an exception occurred in a later step, a retry can repeat that side effect. Use database transactions and event IDs to protect business logic.

## 8. Error Handling in a Batch Listener

Batch listeners have an important difference: a single method invocation processes multiple records. If the method throws an exception, the container needs to know which record caused the failure to decide which part to retry.

If the listener can identify the failing record's index, throw BatchListenerFailedException:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record =
                records.get(index);

        try {
            orderService.process(record.value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                    "Order batch processing failed",
                    ex,
                    index
            );
        }
    }
}
~~~

The index in the exception indicates the record's position in the current batch list. DefaultErrorHandler can use that information to handle the records before the failing position and seek/retry the remainder according to its policy.

If the listener only throws a generic exception without identifying the failing record, the error handler may have to retry the whole batch. In that case, records already processed successfully before the error may also run again. This is why batch operations must be idempotent or track per-record progress.

Notes on batch error handling:

- Do not catch and swallow exceptions if you want the error handler to retry.
- If the failing record is known, provide the index or corresponding record via BatchListenerFailedException.
- Keep event IDs and metadata for logging, investigation, and replay.
- Ensure bulk operations can roll back or tolerate re-execution.
- Verify DLT/recovery behavior for batch listeners for your Spring Kafka version.
- Do not assume the whole batch committed just because some records succeeded.

## 9. Processing Batches with Bulk Operations

Batch listeners shine when the target system supports bulk operations. For example, instead of writing orders to the database one by one, they can be grouped into a single batch insert/update.

~~~java
@Service
public class OrderBatchService {

    private final OrderRepository orderRepository;

    public OrderBatchService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void processBatch(List<OrderCreated> events) {
        List<OrderEntity> entities = events.stream()
                .map(this::toEntity)
                .toList();

        orderRepository.saveAll(entities);
    }

    private OrderEntity toEntity(OrderCreated event) {
        return new OrderEntity(
                event.orderId(),
                event.customerId(),
                event.amount()
        );
    }
}
~~~

A database transaction can help the entire batch commit or roll back together if the repository and database share a transaction. This does not automatically create a distributed transaction with Kafka offsets. If the database commits successfully while offsets have not yet committed, the batch can be redelivered.

Design options:

- Use a unique constraint on event ID to prevent duplicate inserts.
- Use upserts if repeated updates yield the same result.
- Store inbox/processed events in the same transaction as business data.
- Split batches into smaller chunks if a single batch is too large.
- Cap record count and total batch processing time.

Not every bulk API is atomic. Verify the transaction semantics of the target database or service.

## 10. Batch Size and Poll Settings

A batch listener receives records returned by polling. Consumer settings affect batch size and processing duration.

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 300
      properties:
        "[max.poll.interval.ms]": 300000
        "[fetch.min.bytes]": 1
        "[fetch.max.wait.ms]": 500
    listener:
      type: batch
      ack-mode: batch
      concurrency: 3
~~~

Meaning:

- max.poll.records limits the maximum records returned in a single poll.
- max.poll.interval.ms limits the allowed time between consecutive consumer polls.
- fetch.min.bytes is the minimum data brokers try to return when possible.
- fetch.max.wait.ms limits how long brokers wait to accumulate fetch.min.bytes.
- concurrency creates multiple child consumers to process partitions in parallel.

max.poll.records is not the guaranteed number of records in every batch. If only 20 records are available, a poll may return 20 records even if the limit is 300.

If batch processing takes too long, the consumer can exceed max.poll.interval.ms and be considered no longer healthy. The group can then rebalance and assign partitions to other consumers. Measure p95/p99 batch processing times and tune max.poll.records, concurrency, and target system capacity.

Increasing max.poll.records can boost throughput when bulk operations are efficient, but also increases required memory, per-batch processing duration, and the number of records subject to replay.

## 11. Concurrency and Partition Assignment

Spring Kafka uses ConcurrentMessageListenerContainer to manage multiple child consumers when concurrency exceeds one. Each child has its own Kafka consumer and processes only the partitions assigned to it by the group coordinator.

~~~text
Topic orders: 6 partitions
        |
        v
Consumer group: order-service
        |
        +--> Consumer 1: P0, P1
        |
        +--> Consumer 2: P2, P3
        |
        +--> Consumer 3: P4, P5
~~~

The diagram illustrates only one possible distribution. Actual assignments depend on the partition assignor and active consumer count.

Principles:

- Within the same consumer group, a partition is assigned to at most one consumer at a time.
- Increasing concurrency beyond the partition count does not create additional useful parallelism for that topic.
- Records within the same partition have offset order; sequential processing in the listener preserves business order.
- Different partitions can be processed concurrently.
- A batch listener can receive records from multiple partitions in the same poll; do not assume global order across them.
- During a rebalance, partitions may move to other child consumers and uncommitted records may be redelivered.

If ordering by order ID must be preserved, use order ID as the Kafka key so records for the same order go to the same partition. If a batch listener processes items internally in parallel, ensure order-dependent records cannot complete out of order.

## 12. When to Choose a Record Listener?

Choose a record listener when:

**Each record is an independent business unit.** One failing event should not force other events in the poll to retry alongside it.

**Per-record retries are needed.** DefaultErrorHandler can retry and recover a failing record without writing logic to locate a batch index.

**Latency control is needed.** Each record can be processed immediately as the container extracts it from the poll result, without waiting for the application to handle an entire list.

**Business logic needs clear ordering.** Sequential listeners processing one record at a time within a partition are simpler to design, though concurrency and application-created async calls still require care.

**Individual records vary widely in size or processing time.** Per-record handling avoids having one heavy record stall an entire batch.

In return, a record listener can incur repeated method-call and transaction overhead if each record requires its own operation.

## 13. When to Choose a Batch Listener?

Choose a batch listener when:

**The target system supports bulk operations.** Examples include database batch inserts, bulk indexing, bulk APIs, or aggregations over a record set.

**Per-invocation overhead is high.** Grouping records can reduce transaction openings, API calls, or statement preparations.

**Throughput matters more than single-record latency.** Batches may wait to accumulate data before processing, yet typically utilize resources better on suitable workloads.

**Failing records can be identified.** The listener can throw BatchListenerFailedException to report the failing index so the error handler handles the rest.

**Business logic accepts batch processing.** Records in a batch can be processed together without requiring immediate independent responses.

Avoid a batch listener if a single failing record frequently forces the entire batch to retry, batch processing is hard to roll back, or business ordering rules across records are undefined.

## 14. Batch Listeners, Transactions, and Exactly-Once Semantics

If the listener container uses a Kafka transaction manager, the container can combine writing Kafka outputs and committing input offsets within a single Kafka transaction. With a batch listener, the callback unit is the batch; when an exception aborts the transaction, Kafka outputs belonging to that transaction are not visible as committed data to consumers using read_committed.

However, a Kafka transaction does not automatically include external databases or HTTP services. If a batch already updated a database and then the Kafka transaction aborts, redelivering the batch may update the database again.

For databases:

- Use a database transaction for bulk operations if the whole batch should commit/roll back together.
- Use inbox/event IDs to detect already-processed records.
- Consider transactional outbox when events must be published after database updates.
- Do not invoke external side effects outside a transaction assuming a Kafka rollback will undo them.

Exactly-once in Kafka requires properly configured producer/consumer transactions. It does not automatically guarantee end-to-end exactly-once for batch listeners when external non-Kafka systems are involved.

## 15. Common Mistakes

**Configuring a batch factory while the method still accepts a single payload**

A factory in batch mode expects a batch-compatible listener signature. Use a List of payloads, a List of ConsumerRecord, or a Spring Kafka supported batch type. If single payloads are desired, use a record factory.

**Method accepts List while the factory remains in record mode**

Changing the method signature alone is not enough to configure a batch container. Enable batch listening via Boot properties or factory.setBatchListener(true).

**Oversized batches**

Large batches can increase memory usage, processing duration, and the risk of exceeding max.poll.interval.ms. Lower max.poll.records or break up the work.

**One error triggering retries for the whole batch**

If the failing record is not identified, the handler may have to retry the entire batch. Use BatchListenerFailedException when the failing position is known and design idempotent processing.

**Parallel processing breaking order**

If a batch is split across multiple threads, records from the same partition can finish out of order. Parallelize only when business logic is independent or enforce sequencing/serialization by key.

**Assuming BATCH means exactly-once processing**

BATCH only determines when offsets are committed. If the process stops after side effects complete but before committing, records can be redelivered.

**Increasing concurrency on a topic with few partitions**

Extra consumers may receive no partitions. Increasing concurrency does not replace proper partition design.

**Swallowing exceptions inside the listener**

If the method catches an exception and returns normally, the container may treat the callback as successful. Re-throw errors when the error handler should retry or recover.

## 16. Monitoring Performance and Operations

When comparing the two listener types, measure under identical workloads and conditions.

| Metric | Meaning |
|---|---|
| records-consumed-rate | Number of records processed per second |
| listener execution time | Execution time of the listener method |
| batch size | Average and maximum records per callback |
| consumer lag | Distance between latest offset and committed offset |
| commit rate | Frequency of offset commits |
| commit latency | Time taken for commits to complete |
| rebalance rate | Frequency of partition reassignments across the group |
| retry count | Number of record/batch retry attempts |
| DLT rate | Number of records recovered to a DLT |
| heap/buffer usage | Memory resources consumed while holding batches |

Exact metric names depend on the Kafka client, Spring Kafka, Micrometer, and exporters. Inspect the metrics actually exported by the application rather than assuming all versions share identical names.

A useful comparison should record:

- Overall throughput and per-partition throughput.
- p50, p95, and p99 listener latency.
- Time from record publication to business completion.
- Commit count and commit latency.
- Number of records replayed after restarts.
- Error rate and recovery time.
- CPU, heap, and target database/service load.

Batching can increase throughput, yet also increase latency for the first record in a batch if waiting for more data. Measure both throughput and end-to-end latency before deciding.

## 17. Selection and Configuration Checklist

Before promoting a listener to production, confirm:

- Should each callback receive one record or a poll batch?
- Is the effective factory configured for the right record/batch mode?
- Is the method signature compatible with the listener type?
- Is max.poll.records appropriate for batch size and processing duration?
- Does concurrency match partition count and target system capacity?
- Does AckMode match offset commit requirements?
- Are exceptions propagated to the error handler when retries are needed?
- Does the batch listener identify the failing record index?
- Can the DLT and recovery handle records/batches?
- Are database/API side effects idempotent under redelivery?
- Does batch parallelization break intra-partition ordering?
- Is max.poll.interval.ms sufficient for p99 batch processing time?
- Are consumer lag, batch size, listener latency, commit, and retry metrics monitored?
- Have crashes, rebalances, and mid-batch errors been tested to verify replay?

Record listeners suit per-event processing, independent retries, and clear latency requirements. Batch listeners suit applications that can leverage bulk processing and tolerate batch-level handling. Both still rely on Kafka consumer polls, offset commits, and listener containers; choose based on business boundaries, error strategy, and operational metrics of your system.
