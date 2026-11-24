# subBatchPerPartition

In Spring Kafka, **subBatchPerPartition** is a listener container option for **batch listeners**. When enabled, the container splits the set of records received from a single poll into smaller groups, each containing only records belonging to the same **TopicPartition**, and invokes the listener separately for each group.

A single poll can return records from multiple partitions owned by the consumer. With standard batch behavior, the listener receives one batch containing records from all partitions present in the poll. When **subBatchPerPartition** is enabled, the listener receives multiple smaller invocations: each invocation represents only one partition. This helps the application process, observe, and in certain transactional configurations, establish transaction boundaries per partition.

This option changes how the container splits batches and invokes the listener. It does not create additional partitions, increase consumer count, alter Kafka assignments, or provide global ordering across partitions.

## 1. Context: One Poll Can Contain Multiple Partitions

Kafka stores records by topic and partition. A consumer group distributes partitions among consumer members. One consumer can be assigned multiple partitions; in a single poll call, it may receive records from some or all of its assigned partitions.

For example, a consumer in group **billing-service** is assigned three partitions:

- **orders.created-0**
- **orders.created-1**
- **orders.created-2**

A single poll can return:

| TopicPartition | Offsets in poll |
|---|---|
| orders.created-0 | 10, 11, 12 |
| orders.created-1 | 25, 26 |
| orders.created-2 | 41, 42, 43, 44 |

With a batch listener using standard batching, the listener receives one collection containing all nine records. The application must group records by topic and partition itself if it wants to process each partition separately.

When **subBatchPerPartition** is enabled, the container performs this grouping before invoking the listener:

~~~mermaid
flowchart TD
    A["Kafka consumer poll"] --> B["Batch from multiple partitions"]
    B --> C["orders.created-0<br/>offset 10, 11, 12"]
    B --> D["orders.created-1<br/>offset 25, 26"]
    B --> E["orders.created-2<br/>offset 41, 42, 43, 44"]
    C --> F["Listener invocation 1"]
    D --> G["Listener invocation 2"]
    E --> H["Listener invocation 3"]
~~~

Each listener invocation corresponds to one partition. The order in which groups are passed to the listener depends on the partition order in the batch; applications should not rely on a fixed order across partitions.

## 2. What Problems Does subBatchPerPartition Solve?

### Per-Partition Processing

Some workloads need to batch records to reduce database call overhead or perform bulk operations, yet still need to know precisely which partition a batch belongs to. For instance, a processor that maintains per-partition state or needs to track processing progress per partition.

If the listener receives a mixed batch, the application has to group records in code:

~~~java
Map<TopicPartition, List<ConsumerRecord<String, OrderEvent>>> grouped =
        records.stream().collect(Collectors.groupingBy(
                record -> new TopicPartition(
                        record.topic(),
                        record.partition()
                )
        ));
~~~

With **subBatchPerPartition**, the container already splits the batch by partition, so the listener can process a homogeneous group directly in each invocation.

### Per-Partition Transaction Boundaries

An important reason to use this option is when an application uses a batch listener with a Kafka transaction manager. The container can process each sub-batch in its own per-partition transaction. When one partition's sub-batch fails, that sub-batch's transaction can roll back as configured, while other sub-batches that completed their own transactions can commit independently.

This helps scope a transaction to records from a single partition. Exact behavior also depends on the Spring Kafka version, transaction manager type, error handler, and container configuration. Verify the semantics of your running version before relying on it for delivery guarantees.

### Simpler Observability and Recovery

Each listener invocation can be tied to a specific topic-partition. Logs, metrics, and error handling can therefore clearly record which partition is being processed. When investigating a slow partition or malformed data, operations teams can isolate the issue much more easily.

## 3. Configuring subBatchPerPartition

This option is configured on **ContainerProperties** of the listener container factory. It is meaningful when the factory is configured for a batch listener.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class BatchListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderBatchListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);

        factory.getContainerProperties()
                .setSubBatchPerPartition(true);

        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.BATCH);

        return factory;
    }
}
~~~

Three settings to distinguish:

- **setBatchListener(true)** selects the batch listener mode.
- **setSubBatchPerPartition(true)** instructs the container to split batches into per-topic-partition groups before invoking the listener.
- **AckMode.BATCH** selects how the container acknowledges offsets after a batch is processed per that mode's semantics. This is an acknowledgment choice independent of sub-batch splitting.

If **subBatchPerPartition** is enabled while the endpoint still uses a record listener, this option does not produce per-partition batch invocations. Ensure the method signature and listener type match batch mode.

### Set Explicit Values

In applications with multiple factories, configure the value on the exact factory used by the endpoint. Do not assume all listeners share the same default. Default values or transaction-related behavior can depend on the Spring Kafka version and how the container is configured. When this behavior matters, explicitly set true or false and verify the effective factory.

## 4. How Does a Batch Listener Receive Data?

A batch listener can receive a list of payloads or a list of **ConsumerRecord**s, depending on how the application needs metadata.

If partition, offset, timestamp, or key is needed for each record, using **ConsumerRecord** is the clearest choice:

~~~java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {

    @KafkaListener(
        id = "orderBatchListener",
        topics = "orders.created",
        groupId = "billing-service",
        containerFactory = "orderBatchListenerFactory"
    )
    public void onOrders(
            List<ConsumerRecord<String, OrderEvent>> records) {

        if (records.isEmpty()) {
            return;
        }

        ConsumerRecord<String, OrderEvent> first = records.get(0);

        String topic = first.topic();
        int partition = first.partition();

        // With subBatchPerPartition=true, records belong to the same topic-partition.
        for (ConsumerRecord<String, OrderEvent> record : records) {
            billingService.process(
                    record.value(),
                    record.offset()
            );
        }

        log.debug(
                "Processed {} records from {}-{}",
                records.size(),
                topic,
                partition
        );
    }
}
~~~

With **subBatchPerPartition=true**, the listener can take topic and partition from the first record to attach context for the whole invocation. Still keep a check or assertion in code if batch homogeneity is a critical business requirement, especially if the factory might be reconfigured later.

If the listener only needs payloads, it can accept **List<OrderEvent>**:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service",
    containerFactory = "orderBatchListenerFactory"
)
public void onOrderPayloads(List<OrderEvent> events) {
    billingService.processBatch(events);
}
~~~

When receiving payloads only, the listener does not have direct per-element topic-partition and offset metadata. If those values are needed for logging, recovery, or auditing, use ConsumerRecord or batch headers appropriate for your message converter and Spring Kafka version.

## 5. Comparing Standard Batch vs. Sub-Batch per Partition

| Aspect | Standard batch | subBatchPerPartition enabled |
|---|---|---|
| Data received by listener | Records from multiple partitions in one poll | A group of records from one topic-partition per invocation |
| Listener invocation count | Typically one invocation per polled batch | Can be multiple invocations, matching partitions present in the poll |
| Record grouping | Application groups manually if needed | Container groups by partition |
| Partition metadata | Present in each ConsumerRecord | Records within one invocation share the same topic-partition |
| Transactions | Can process entire batch in a transaction as configured | Can create separate transactions per partition sub-batch with transactional config |
| Invocation overhead | Fewer invocations | Potentially more invocations |
| Error scope | Can affect a mixed batch | Can scope the invocation to one partition sub-batch |
| Global ordering | None across partitions | Still none across partitions |

Suppose a poll returns 12 records across three partitions, four records per partition:

- Standard batch: listener is called once with 12 records.
- subBatchPerPartition: listener is called three times, each with four records belonging to one partition.

Invocation count does not necessarily equal the number of partitions assigned to the consumer. It depends on which partitions actually have records in that poll result.

## 6. subBatchPerPartition Does Not Increase Concurrency

Distinguish three concepts:

- **Partition**: the unit of storage and ordering in Kafka.
- **Consumer concurrency**: the number of consumers running in parallel within a listener container.
- **Sub-batch**: the group of records the container passes to a single batch listener invocation.

Enabling **subBatchPerPartition** only changes how the container splits poll results. It does not create more consumers, change partition counts, or make sub-batches on the same consumer run in parallel automatically.

For example, one consumer is assigned four partitions and a poll returns records from all four partitions. The container may invoke the listener four times for four sub-batches. Those invocations execute along that consumer's processing thread. To increase parallelism, evaluate concurrency and partition count, not just sub-batching.

If concurrency increases from two to four while the topic has four partitions, the group can distribute up to four partitions across four consumers. Each consumer can still receive records from its assigned partition and produce corresponding sub-batches. Total consumers across the deployment also depend on instance count and per-instance concurrency.

## 7. Relationship with Partition Ordering

Kafka guarantees record ordering within the same partition. When the container splits sub-batches by partition, records within an invocation preserve the partition's read order.

Example:

| Partition | Records in offset order |
|---|---|
| orders.created-0 | 100, 101, 102 |
| orders.created-1 | 200, 201 |
| orders.created-2 | 300, 301, 302 |

The listener receives separate groups:

- Sub-batch partition 0: 100, 101, 102.
- Sub-batch partition 1: 200, 201.
- Sub-batch partition 2: 300, 301, 302.

There is no guarantee that all records of partition 0 must be processed before partition 1 in a multi-consumer system. Cross-partition ordering is not guaranteed by Kafka. If business rules require ordering among events for the same order, the producer must use a stable key so those events land in the same partition.

Do not offload individual records from a sub-batch to an async executor and return immediately from the listener if ordering and proper acknowledgments must be preserved. The container may treat the invocation as completed while actual side effects are still running. If processing asynchronously, the application must manage completion and errors before confirming progress.

## 8. Transactions per Sub-Batch

When using a batch listener with a Kafka transaction manager, **subBatchPerPartition** can be used to create transaction boundaries per partition. Instead of one transaction spanning records from multiple partitions in the poll, the container processes each sub-batch in its own transaction according to your version's semantics and transaction configuration.

This can be useful when:

- Each partition is an independent processing stream.
- The application writes results back to Kafka and wants to commit outputs together with input offsets in the same Kafka transaction.
- A failing partition sub-batch should not force rolling back other partition sub-batches that already committed separately.
- Operations needs to identify which partition a failed transaction belonged to.

Illustrative diagram:

~~~mermaid
flowchart TD
    A["Poll batch: partition 0, 1, 2"] --> B["Sub-batch partition 0"]
    A --> C["Sub-batch partition 1"]
    A --> D["Sub-batch partition 2"]
    B --> E["Transaction 0"]
    C --> F["Transaction 1"]
    D --> G["Transaction 2"]
    E --> H["Commit or rollback"]
    F --> I["Commit or rollback"]
    G --> J["Commit or rollback"]
~~~

Each transaction is illustrated independently per sub-batch. Actual commits or rollbacks depend on listener outcome, transaction manager, error handler, and Kafka state. If the listener does not use a transaction manager, do not infer that enabling sub-batching creates transactions automatically.

### Kafka Transactions Do Not Automatically Cover Databases

If a listener updates a relational database while also writing to Kafka, a Kafka transaction does not automatically make the database transaction part of the same atomic transaction. Use outbox/inbox patterns or an appropriate transaction coordination mechanism.

For Kafka-to-Kafka processing, transactions can coordinate output records and input offsets per Spring Kafka configuration. Downstream consumers should use **isolation.level=read_committed** if they must see only records from committed transactions.

### Considering Transaction Overhead

Per-partition sub-batch transactions can increase the number of transactions compared to one transaction per poll batch. Measure transaction rate, commit latency, broker load, and throughput. A partition with a small batch or even a single record can also start a transaction if configured to do so.

Choose transaction scope based on business boundaries and recovery requirements, not merely on a desire to reduce listener invocation counts.

## 9. Error Handling When Processing Sub-Batches

A batch listener can fail on a record inside the group. When **subBatchPerPartition** is enabled, the failing invocation corresponds to a single partition sub-batch, making it clear which partition is involved. However, how the container retains offsets, retries, or recovers records still depends on the error handler and acknowledgment mode.

Questions to clarify:

- On which record did the listener throw an exception?
- Is the entire sub-batch retried or only the failing record?
- Does the error handler seek the partition back or recover the record?
- Which offset is committed after recovery?
- If using transactions, did the sub-batch's transaction roll back or commit?
- Were other sub-batches in the same poll already processed or committed?

Example error handler using **DefaultErrorHandler**:

~~~java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

factory.setCommonErrorHandler(
        new DefaultErrorHandler(
                new FixedBackOff(1_000L, 2L)
        )
);
~~~

This is only an illustrative retry configuration. For batch listeners, if you need to pinpoint the failing record's position in the batch, use an appropriate mechanism such as **BatchListenerFailedException** per your Spring Kafka version. If a DLT is needed, ensure the publisher has write permissions and sufficient recovery metadata for investigation/replay.

Do not treat sub-batch per partition as an automatic error isolation mechanism for all cases. It splits listener invocation scope; retry, commit, and rollback semantics remain governed by container, error handler, and transaction configuration.

## 10. AckMode and Offset Commits

**subBatchPerPartition** and **AckMode** are two distinct configurations:

- subBatchPerPartition determines how records are split before invoking the batch listener.
- AckMode determines when the container acknowledges and commits offsets.

Factory example:

~~~java
factory.setBatchListener(true);

var properties = factory.getContainerProperties();
properties.setSubBatchPerPartition(true);
properties.setAckMode(ContainerProperties.AckMode.BATCH);
~~~

In a non-transactional setup, BATCH typically acknowledges the batch after the listener completes successfully per container semantics. When a batch is split into sub-batches, understand how your Spring Kafka version handles acknowledgments and offsets across invocations. With a transaction manager, offsets can be coordinated into the transaction via transactional container mechanics.

Do not change AckMode solely to enable sub-batches. Choose acknowledgment behavior according to desired delivery semantics, then enable partition splitting if per-partition invocations or transaction boundaries are needed.

### Why Can Redelivery Still Happen?

If side effects have completed before offsets commit successfully, the consumer can receive those records again after a restart or rebalance. Sub-batches do not eliminate this window. Consumers still require idempotency, especially when batches write to databases or call external APIs.

## 11. Payload List or ConsumerRecord List?

Choosing the listener parameter type affects what information the application can access.

| Listener type | Accessible data | Best suited when |
|---|---|---|
| **List<V>** | Payload of each record | Only business processing on data is needed |
| **List<ConsumerRecord<K,V>>** | Payload, key, topic, partition, offset, timestamp, and headers | Routing, logging, checkpointing, or diagnostics per partition are needed |
| Batch message with headers | Payloads and headers converted by message converter | Application uses Spring Messaging abstraction |

When **subBatchPerPartition** is enabled, using **List<ConsumerRecord<K,V>>** lets code verify that records share the same topic and partition. This is helpful if the batch is written to a database keyed by partition or needs first/last offset logging.

If using a payload list, consider adding appropriate headers or metadata if business logic needs to know the partition. Do not infer the partition from the key because keys may not be unique or the partitioner may change.

## 12. Complete Example with a Batch Listener

The example below demonstrates a batch listener factory splitting sub-batches per partition and a listener logging group metadata:

~~~java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.stereotype.Component;

@Configuration
class OrderBatchKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderBatchListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(3);

        var properties = factory.getContainerProperties();
        properties.setSubBatchPerPartition(true);
        properties.setAckMode(ContainerProperties.AckMode.BATCH);

        return factory;
    }
}

@Component
class OrderBatchConsumer {

    @KafkaListener(
        id = "orderBatchConsumer",
        topics = "orders.created",
        groupId = "billing-service",
        containerFactory = "orderBatchListenerFactory"
    )
    public void consume(
            List<ConsumerRecord<String, OrderEvent>> records) {

        if (records.isEmpty()) {
            return;
        }

        String topic = records.get(0).topic();
        int partition = records.get(0).partition();

        long firstOffset = records.get(0).offset();
        long lastOffset = records.get(records.size() - 1).offset();

        billingService.processPartitionBatch(
                topic,
                partition,
                records
        );

        log.info(
                "Processed {} records from {}-{} offsets {}..{}",
                records.size(),
                topic,
                partition,
                firstOffset,
                lastOffset
        );
    }
}
~~~

In this example:

- The factory enables batch mode.
- Concurrency of three creates up to three child consumers per listener container instance.
- The container splits batches into sub-batches by topic-partition.
- The listener receives a group of records from the same partition.
- The application can log the partition and offset range of the invocation.

This is a basic configuration example and omits transaction manager, error handler, serializers/deserializers, and service dependency injection. Those components must be added for your actual environment.

## 13. When to Enable and When to Disable?

### Consider Enabling When

- The listener is a batch listener and needs to process each partition as a separate unit.
- The application wants per-partition transaction boundaries with a Kafka transaction manager.
- Business logic or logging needs to clearly associate each invocation with a single topic-partition.
- Manual record grouping in application code is currently repetitive and can be delegated to the container.
- Error handling needs invocations scoped per partition, with verified retry/recovery semantics.

### Can Keep Disabled When

- The listener needs to process the entire polled batch as one unit.
- The application does not need to separate records by partition.
- One transaction for the entire batch is an intentional, verified boundary.
- Increasing invocation count adds overhead without delivering benefits.
- The listener already handles multi-partition grouping and processing appropriately.

There is no single right choice for every workload. Define your desired processing and transaction boundaries before enabling it.

## 14. Limitations to Understand

**Does not create automatic parallelism.** Sub-batches are invoked separately, yet usually still execute sequentially on the consumer thread. To increase parallelism, examine concurrency, partition count, and any asynchronous processing in the application.

**Does not create cross-partition ordering.** Each partition has its own order. Sub-batches do not establish global ordering across events in a topic.

**Does not change assignment.** Kafka still decides which partitions are assigned to a consumer. The option only splits batches of the partitions the consumer already received.

**Meaningful only for batch listeners.** Record listeners are already invoked per record; splitting batches by partition does not apply in the same way.

**Does not create transactions without a transaction manager.** A sub-batch is an invocation unit. Transaction boundaries require a transaction manager and matching configuration.

**Does not eliminate duplicates.** Side effects completed prior to commit can still be re-executed after a failure. Idempotency remains an application requirement.

**Does not guarantee equal-sized sub-batches.** Record counts depend on available data, partition distribution, fetches, and poll limits.

## 15. Production Observability and Diagnostics

When **subBatchPerPartition** is enabled, logs should identify which invocation is processing which partition. With a ConsumerRecord list, you can capture topic, partition, and first/last offsets of the group.

Information to observe:

| Information | Purpose |
|---|---|
| Listener ID | Identify the endpoint |
| Consumer group | Identify partition distribution scope |
| Topic and partition | Scope the sub-batch |
| Record count in sub-batch | Track batch sizes per partition |
| First/last offsets | Track processing progress |
| Processing duration | Detect slow partitions |
| Retry/recovery count | Identify recurring failures |
| Commit/transaction result | Determine whether progress was persisted |
| Consumer lag | Detect backlogged partitions |

### Warning Signs

- One partition consistently has much larger sub-batches than others: inspect key distribution, producer traffic, and partition skew.
- One partition processes slowly on a regular basis: inspect hot data, downstream queries, or lock contention by key.
- Many tiny invocations: examine throughput, poll behavior, and listener call overhead.
- Transaction rate spikes sharply: verify whether each sub-batch starts its own transaction under your configuration.
- One partition continuously retries: inspect poison records, error handler, and recovery policy.
- Duplicates rise after rebalances: correlate offset commits with side-effect idempotency.

Do not use total consumer lag to conclude a specific partition is slow. Inspect per-partition lag and correlate it with sub-batch processing duration.

## 16. Testing subBatchPerPartition

Tests should use a real Kafka broker or equivalent test container to verify that the container splits batches properly. Unit tests on a list-handling function do not prove the listener container produces per-partition sub-batches.

A basic test plan:

1. Create a topic with at least three partitions.
2. Send records with keys chosen to distribute across different partitions.
3. Configure a batch listener with **subBatchPerPartition=true**.
4. Ensure the consumer group holds assignments for the partitions under test.
5. Record the topic-partition of each invocation.
6. Confirm every record in an invocation belongs to the same topic-partition.
7. Confirm multiple invocations occur when a poll receives records from multiple partitions.
8. Verify offset ordering within each invocation.
9. Stop the consumer while uncommitted records exist and verify redelivery behavior.
10. If using transactions, verify commit/rollback behavior per sub-batch as configured.

You can assert this invariant directly inside the listener:

~~~java
private void assertSinglePartition(
        List<ConsumerRecord<String, OrderEvent>> records) {

    if (records.isEmpty()) {
        return;
    }

    var first = records.get(0);

    boolean mixedPartition = records.stream().anyMatch(record ->
            !record.topic().equals(first.topic())
                    || record.partition() != first.partition()
    );

    if (mixedPartition) {
        throw new IllegalStateException(
                "Expected a single TopicPartition per sub-batch"
        );
    }
}
~~~

Use this check in tests or controlled assertions if single-partition homogeneity is mandatory. You do not necessarily need to throw exceptions in production solely to validate a configuration assumption; you can emit a metric or warning log depending on requirements.

## 17. Common Implementation Mistakes

**Enabling subBatchPerPartition while forgetting batch mode.** The factory must enable batch listening and the method must accept an appropriate batch parameter type.

**Assuming every poll contains only one partition.** One consumer can be assigned multiple partitions and a poll can return records from multiple partitions.

**Inferring partition from key.** Partitions may be chosen by a partitioner, and record metadata is the authoritative source.

**Assuming each sub-batch runs on a separate thread.** The container splits invocations; it does not turn them into parallel tasks.

**Enabling the option expecting higher throughput.** Consumer count and assignments do not change. Invocation overhead may even increase.

**Overlooking the transaction manager.** The option does not create transactions automatically if the listener container lacks transactional configuration.

**Processing asynchronously and returning immediately.** The container can acknowledge the invocation before side effects finish unless the application coordinates completion properly.

**Neglecting idempotency.** Redelivery can still occur when offsets have not committed or transactions roll back.

**Ignoring partition skew.** A hot partition can produce large, slow sub-batches even while other partitions process quickly.

## 18. Runbook When Sub-Batches Behave Unexpectedly

1. Identify the listener ID, container factory, and consumer group.
2. Verify the endpoint is using a batch listener.
3. Check the **subBatchPerPartition** value on the correct ContainerProperties.
4. Inspect ConsumerRecord metadata of records in each invocation.
5. Check the consumer's topic-partition assignment.
6. Compare invocation count against the number of partitions that actually had records in the poll.
7. Measure batch size and processing time per partition.
8. Check AckMode, error handler, and transaction manager.
9. Correlate commits/rollbacks and offsets on errors.
10. Verify idempotency when records are redelivered.
11. Adjust concurrency or partitioning only when measured data shows more parallelism is needed.
12. After changes, verify throughput, lag, transaction rate, retries, and duplicates.

If the listener receives only one sub-batch even though the consumer is assigned multiple partitions, check whether the other partitions had records in that poll. Being assigned a partition does not mean every poll contains records from it.

## 19. Pre-Production Checklist

**Listener configuration**

- [ ] The right factory is referenced by the **@KafkaListener** endpoint.
- [ ] Batch mode is enabled and the method signature accepts the right batch type.
- [ ] **subBatchPerPartition** is explicitly set on the right ContainerProperties.
- [ ] ConsumerFactory and partition assignment are verified.
- [ ] AckMode aligns with how the listener acknowledges offsets.

**Business logic and transactions**

- [ ] The listener handles exactly one topic-partition per invocation when enabled.
- [ ] Side effects are safe if records are redelivered.
- [ ] A transaction manager is configured if per-sub-batch transaction boundaries are required.
- [ ] The error handler has batch-appropriate retry/recovery.
- [ ] No assumption is made that Kafka transactions cover database transactions.

**Performance and observability**

- [ ] Invocation count, batch size, and processing time per partition have been measured.
- [ ] Partition skew and downstream capacity have been evaluated.
- [ ] subBatchPerPartition is not relied upon to create concurrency.
- [ ] Logs include listener ID, group, topic, partition, and offset.
- [ ] Lag, transaction rate, retries, recovery, and duplicates are monitored.

**Testing**

- [ ] Tested with multiple partitions assigned to the consumer.
- [ ] Verified each invocation contains only one topic-partition.
- [ ] Verified offset ordering within partitions.
- [ ] Verified redelivery when stopped before commit.
- [ ] If transactional, verified commit and rollback behavior per sub-batch.

## 20. Guiding Principles

**subBatchPerPartition** is useful when a batch listener needs to receive records grouped by a single partition, especially when processing or transactions require per-partition boundaries. The container performs the grouping, saving the listener from splitting mixed batches after every poll.

This option affects only how the listener receives batches. It does not alter partition assignment, create parallel consumers, or eliminate redelivery. Configure batch mode, AckMode, error handler, and transaction manager explicitly; use record metadata to track partitions; and keep side effects idempotent. Measure batch size, processing time, lag, and transaction rate per partition before concluding the configuration is production-ready.
