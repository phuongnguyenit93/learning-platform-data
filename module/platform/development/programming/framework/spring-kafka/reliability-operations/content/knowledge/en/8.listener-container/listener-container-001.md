# KafkaMessageListenerContainer

In Spring Kafka, **KafkaMessageListenerContainer** is the component that manages the lifecycle and data-reading loop of a Kafka consumer. The container creates the consumer through `ConsumerFactory`, subscribes to topics or assigns partitions according to configuration, invokes the listener when a poll receives records, manages offsets, coordinates rebalances, and stops the consumer in a controlled manner.

This is the foundational class of the listener container model in Spring Kafka. A `KafkaMessageListenerContainer` manages **one Kafka Consumer** and handles polls on one consumer thread. When multiple parallel consumers are needed, Spring Kafka provides **ConcurrentMessageListenerContainer**, which coordinates multiple child `KafkaMessageListenerContainer` instances.

Understanding the role of `KafkaMessageListenerContainer` properly helps design concurrency, offset commits, error handling, and lifecycle clearly. It also helps distinguish containers created directly by the application from containers created automatically from `@KafkaListener`.

## 1. Position of KafkaMessageListenerContainer in the Spring Kafka architecture

The Kafka Java client provides `KafkaConsumer` with operations such as `subscribe`, `poll`, `commitSync`, `commitAsync`, `pause`, and `resume`. If an application uses `KafkaConsumer` directly, the application must manually manage the poll loop, lifecycle, threads, rebalances, and many operational details.

Spring Kafka places a management layer above `KafkaConsumer`. `KafkaMessageListenerContainer` receives configuration from `ContainerProperties`, obtains a consumer from `ConsumerFactory`, and coordinates the message-reading process.

General flow:

~~~mermaid
flowchart TD
    A["Spring application"] --> B["KafkaMessageListenerContainer"]
    B --> C["ConsumerFactory"]
    C --> D["KafkaConsumer"]
    D --> E["subscribe / assign"]
    E --> F["poll loop"]
    F --> G["MessageListener"]
    G --> H["Business processing"]
    H --> I["Offset acknowledgment / commit"]
    B --> J["Lifecycle, pause/resume, events"]
    B --> K["Error handling and rebalance coordination"]
~~~

Core responsibilities of the container:

- Create and close `KafkaConsumer` through `ConsumerFactory`.
- Manage subscriptions by topic, topic pattern, or partition assignment.
- Run the poll loop on the consumer thread.
- Deliver a record or batch of records to the configured listener.
- Coordinate the ack mode and offset commits.
- Handle callbacks related to rebalances.
- Coordinate the error handler and transaction manager when configured.
- Provide lifecycle `start`/`stop`, `pause`/`resume`, and operational signals.

The container is not a broker, does not store data, and does not decide the business logic of a message. It manages how the application retrieves records from Kafka and hands them over to the listener.

## 2. KafkaMessageListenerContainer manages one consumer

The most important point about this class is the one-to-one relationship between a container and a `KafkaConsumer`. That consumer can be assigned one or more partitions, but the container's polls and listener invocations occur on the corresponding consumer thread.

For example, the `orders` topic has six partitions. A `KafkaMessageListenerContainer` in the group can receive all six partitions if there are no other members in the group. The container still uses only one consumer to process the assigned partitions.

~~~mermaid
flowchart TD
    G["Consumer group: orders-reader"] --> C["KafkaMessageListenerContainer"]
    C --> K["One KafkaConsumer"]
    K --> P0["Partition 0"]
    K --> P1["Partition 1"]
    K --> P2["Partition 2"]
    K --> P3["Partition 3"]
    K --> P4["Partition 4"]
    K --> P5["Partition 5"]
~~~

One consumer can process multiple partitions, but within the same consumer, processing order is coordinated by the poll loop and listener. If the listener processes a record slowly, other records polled on the same consumer may have to wait for processing.

The container does not create a separate thread for each partition. To increase parallelism, you must increase the number of consumers in the group using multiple containers or use `ConcurrentMessageListenerContainer` with appropriate concurrency.

### 2.1 Distinguishing from ConcurrentMessageListenerContainer

The two classes are often mentioned together:

| Characteristic | KafkaMessageListenerContainer | ConcurrentMessageListenerContainer |
|---|---|---|
| Number of consumers | One consumer | One or more child consumers |
| Execution model | One consumer thread | Each child container has its own consumer thread |
| Partition distribution | Consumer is assigned partitions by the group coordinator | Multiple consumers in the same group share partitions |
| Purpose | Manage a single consumer | Coordinate concurrency within an endpoint |
| Listener configuration | ContainerProperties | ContainerProperties is used for the child containers |

`ConcurrentMessageListenerContainer` does not replace `KafkaMessageListenerContainer` at the low level. It creates and manages multiple child `KafkaMessageListenerContainer` instances.

If concurrency is 3, the wrapper typically creates three child containers, each owning one `KafkaConsumer`. These consumers join the same group ID and Kafka distributes partitions among them.

~~~mermaid
flowchart TD
    P["ConcurrentMessageListenerContainer<br/>concurrency = 3"] --> C1["KafkaMessageListenerContainer 1"]
    P --> C2["KafkaMessageListenerContainer 2"]
    P --> C3["KafkaMessageListenerContainer 3"]
    C1 --> K1["KafkaConsumer 1"]
    C2 --> K2["KafkaConsumer 2"]
    C3 --> K3["KafkaConsumer 3"]
~~~

If there are four pods and each pod has concurrency 3, a logical consumer group can have up to 12 consumers. The number of consumers that actually receive partitions is still limited by the number of subscribed partitions. If the topic has six partitions, at most six consumers can be assigned partitions at one time; the remaining consumers receive no partitions.

### 2.2 Relationship with @KafkaListener

In Spring applications, most listeners are declared using `@KafkaListener`. Spring Kafka creates endpoints and containers through `KafkaListenerContainerFactory`.

The default factory typically creates a `ConcurrentMessageListenerContainer`, even when concurrency is 1. In that case, the wrapper has one child `KafkaMessageListenerContainer`. Therefore, when reading logs or debugging at runtime, you may see both the endpoint-level container name and the child containers.

Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-reader",
    concurrency = "3"
)
public void handle(String payload) {
    orderService.process(payload);
}
~~~

This annotation declares a listener at the endpoint layer. The application does not call the `KafkaMessageListenerContainer` constructor directly. The factory creates the wrapper and child containers, then manages their lifecycle.

Using `KafkaMessageListenerContainer` directly is appropriate when you need low-level container control, dynamic subscriptions, or integration of a listener outside the annotation model. For typical applications, `@KafkaListener` and container factories reduce the lifecycle code you have to manage manually.

## 3. Ways to specify topics and partitions

`KafkaMessageListenerContainer` takes `ContainerProperties` to know where the consumer should read from and how to process records. There are three common ways to configure the data source.

### 3.1 Subscribe by topic name

Use a topic list when the consumer group needs to participate in Kafka-managed assignment:

~~~java
ContainerProperties properties =
    new ContainerProperties("orders", "order-updates");
~~~

The consumer subscribes to these topics. The group coordinator coordinates members in the group to assign partitions. When a member joins or leaves the group, Kafka may perform a rebalance.

This approach fits consumer groups with multiple instances that need automatic partition distribution and want Kafka to manage membership.

### 3.2 Subscribe by topic pattern

You can use a `Pattern` to subscribe to topics matching a regular expression:

~~~java
Pattern topicPattern = Pattern.compile("orders-.*");
ContainerProperties properties =
    new ContainerProperties(topicPattern);
~~~

This approach is useful when topics are created by convention and the consumer needs to track a dynamic set of topics. The consumer periodically refreshes metadata according to the Kafka client mechanism and can discover new topics matching the pattern.

The pattern must be tightly controlled. An overly broad expression can cause the consumer to accidentally subscribe to topics outside its business scope or receive data from another environment if sharing a cluster.

### 3.3 Assign specific partitions

If the application needs to control partition assignment, you can configure `TopicPartitionInitialOffset`:

~~~java
ContainerProperties properties =
    new ContainerProperties(
        new TopicPartitionInitialOffset("orders", 0),
        new TopicPartitionInitialOffset("orders", 1)
    );
~~~

In direct partition assignment mode, the application is responsible for determining which partitions belong to the container. This differs from group subscription: the consumer does not rely on the group coordinator to distribute assignments automatically in the same way.

This can be used when an application owns specific partitions or when deploying controlled reading flows. You must avoid having multiple consumers assign the same partition without a coordination mechanism, because they can read duplicates and commit offsets competitively.

`TopicPartitionInitialOffset` overloads allow specifying an initial offset or timestamp depending on the Spring Kafka version. When using initial offsets, you need to understand the semantics of absolute offsets, relative offsets, and whether the group's committed offset takes precedence under the specific configuration.

### 3.4 Choosing the right subscription approach

| Need | Configuration approach |
|---|---|
| A logical group reading fixed topics | Topic list |
| Tracking new topics by naming convention | Topic pattern |
| Reading only specific known partitions | TopicPartitionInitialOffset |
| Scaling consumers automatically by group | Subscribe by topic or pattern |
| Application-managed assignment | Assign specific partitions, with a clear runbook |

Do not choose direct partition assignment just to avoid rebalances if the system still needs group coordination. Manual assignment shifts additional responsibility for distribution, failover, and avoiding duplicate partition consumption to the application.

## 4. ContainerProperties: configuring container behavior

`ContainerProperties` is the central configuration object for `KafkaMessageListenerContainer`. It describes the subscription, listener, and many parameters controlling the poll loop, acks, transactions, and lifecycle.

Common configuration groups:

| Group | Example properties | Role |
|---|---|---|
| Subscription | topics, topicPattern, topicPartitions | Define the record source |
| Listener | messageListener | Listener invoked by the container |
| Polling | pollTimeout | Wait time during poll |
| Offset | ackMode, syncCommits | How offsets are acknowledged and committed |
| Rebalance | consumerRebalanceListener | Callbacks when partitions are revoked/assigned |
| Lifecycle | shutdownTimeout, idleEventInterval | Stop the container and detect idle state |
| Transaction | Kafka-aware transaction manager | Coordinate transactions and offsets |
| Monitoring | monitorInterval, noPollThreshold | Detect consumers not polling as expected |

Names and capabilities of some properties may differ across Spring Kafka versions. When configuring a real project, verify against the API of the version in use.

### 4.1 Listener

The listener is the part that processes records polled by the container. Spring Kafka supports record-based and batch-based listeners, which may receive acknowledgment or the consumer depending on the interface.

Common interfaces:

- `MessageListener`: receives each `ConsumerRecord`.
- `AcknowledgingMessageListener`: receives the record along with `Acknowledgment` for manual acknowledgment.
- `ConsumerAwareMessageListener`: additionally receives the Kafka `Consumer` when the listener needs consumer information.
- `BatchMessageListener`: receives a list of records from a single poll.
- `BatchAcknowledgingMessageListener`: processes a batch with acknowledgment.
- `BatchConsumerAwareMessageListener`: receives a batch and the consumer.

Choose a listener interface that matches the processing model. Do not configure a batch-style listener and then process it as a record listener or vice versa.

### 4.2 Poll timeout

Poll timeout defines how long the consumer waits in a single poll when no records are available. It is part of the reading cadence, but it does not replace the Kafka client's `max.poll.interval.ms`.

Two distinct concepts:

- `pollTimeout` is the time a single poll call waits for data.
- `max.poll.interval.ms` is the limit between subsequent polls before the consumer may be considered stalled and removed from the group.

If the listener takes too long to process a batch, the container may fail to call poll within the `max.poll.interval.ms` limit. You should tune `max.poll.records`, processing time, concurrency, and downstream timeouts rather than just increasing poll timeout.

### 4.3 Shutdown timeout

When the application stops, the container needs to stop taking new work and close the consumer in a controlled manner. Shutdown timeout sets a wait limit for the stopping process depending on the lifecycle mechanism and version.

If the listener is in the middle of processing a slow record, shutdown can wait for the listener to finish within the configured limit. When the timeout expires, stopping may lead to uncommitted records being read again later.

Therefore, shutdown timeout must be coordinated with maximum processing time, commit time, and the orchestration termination grace period. You should not set the timeout too short so that every deployment causes many reprocessings; nor should you let the container wait indefinitely.

## 5. Creating KafkaMessageListenerContainer directly

When creating a container in Java, you first need a `ConsumerFactory`. The factory is responsible for creating `KafkaConsumer` instances with bootstrap servers, group ID, deserializers, security, and client properties.

The example below illustrates a consumer reading strings from the `orders` topic:

~~~java
@Bean
ConsumerFactory<String, String> ordersConsumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "kafka-1:9092,kafka-2:9092,kafka-3:9092"
    );
    props.put(
        ConsumerConfig.GROUP_ID_CONFIG,
        "orders-reader"
    );
    props.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
        false
    );

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

Then create `ContainerProperties` and `KafkaMessageListenerContainer`:

~~~java
@Bean
KafkaMessageListenerContainer<String, String> ordersListenerContainer(
        ConsumerFactory<String, String> ordersConsumerFactory) {

    ContainerProperties containerProperties =
        new ContainerProperties("orders");

    containerProperties.setPollTimeout(1500);
    containerProperties.setAckMode(
        ContainerProperties.AckMode.RECORD
    );

    containerProperties.setMessageListener(
        (MessageListener<String, String>) record -> {
            System.out.printf(
                "topic=%s partition=%d offset=%d key=%s value=%s%n",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                record.value()
            );
        }
    );

    return new KafkaMessageListenerContainer<>(
        ordersConsumerFactory,
        containerProperties
    );
}
~~~

In the example:

- `ConsumerFactory` creates consumers with group ID `orders-reader`.
- `ContainerProperties` subscribes to the `orders` topic.
- `MessageListener` receives each `ConsumerRecord`.
- `AckMode.RECORD` requests a commit after the listener processes each record according to the container mechanism.
- `KafkaMessageListenerContainer` manages the consumer thread and lifecycle.

When the container is declared as a Spring bean, its lifecycle is usually managed by `ApplicationContext` via `SmartLifecycle` and auto-startup. There is no need to call `start` manually inside the bean factory method if Spring is managing the default lifecycle. If creating the container outside `ApplicationContext`, the application must call `start` and `stop` at the appropriate times.

### 5.1 Creating and managing a container outside the Spring lifecycle

Example when a component manages the container itself:

~~~java
ContainerProperties properties =
    new ContainerProperties("orders");

properties.setMessageListener(
    (MessageListener<String, String>) record ->
        orderService.process(record.value())
);

KafkaMessageListenerContainer<String, String> container =
    new KafkaMessageListenerContainer<>(
        consumerFactory,
        properties
    );

container.start();

// When the component owning the container needs to stop:
container.stop();
~~~

In real applications, do not call `start`/`stop` arbitrarily from multiple places. A clear owner is needed to ensure the container is started only once and stopped when the application component closes. If using a Spring bean, prefer letting Spring manage the lifecycle.

### 5.2 Configuring the listener after creating the container

You can configure the listener before the container starts via `ContainerProperties`. You should not arbitrarily change the listener or consumer configuration while the container is running.

If you need to change the listener or subscription, stop the container according to its lifecycle, update supported configuration, and restart it. For frequent dynamic changes, consider Spring Kafka's factory and registry instead of modifying the object currently processing polls.

## 6. Container lifecycle

`KafkaMessageListenerContainer` manages the lifecycle from startup until closing the consumer. Operational states to understand include creation, start, poll, pause/resume, rebalance, stop, and close.

### 6.1 Startup

When the container starts:

1. The container validates configuration and listener.
2. The container asks `ConsumerFactory` to create a `KafkaConsumer`.
3. The consumer subscribes to topics, patterns, or receives partition assignments as configured.
4. The Kafka client joins the group if using subscribe.
5. The container runs the poll loop.
6. When a poll yields records, the container invokes the listener.
7. After processing, the container applies ack/commit and continues polling.

The consumer is created and used within the container-managed lifecycle. The application should not extract the internal consumer and call APIs from arbitrary threads because `KafkaConsumer` is not thread-safe.

### 6.2 Poll loop

The poll loop is the center of the container's operation. It continuously fetches records from the broker, processes a record or batch, performs necessary actions, and continues polling.

~~~mermaid
flowchart TD
    A["Container started"] --> B["Create KafkaConsumer"]
    B --> C["Subscribe / assign"]
    C --> D["Poll"]
    D --> E{"Any records?"}
    E -->|Yes| F["Invoke listener"]
    F --> G["Ack / commit according to mode"]
    G --> D
    E -->|No| H["Idle / wait"]
    H --> D
    D --> I["Stop requested"]
    I --> J["Finish current work and close consumer"]
~~~

If the listener runs synchronously on the consumer thread, listener processing time directly affects the timing of the next poll. A listener blocked for too long can cause the consumer to exceed `max.poll.interval.ms` and be removed from the group by the group coordinator.

Therefore, you should measure processing time, set timeouts for downstream calls, limit the number of records per poll, and consider batch size.

### 6.3 Stopping the container

When stop is requested, the container halts the poll loop and closes the consumer according to its lifecycle. Closing the consumer allows the Kafka client to leave the group and release resources.

If the listener is processing a record, the container needs to finish or stop according to the configured shutdown mechanism and timeout. Uncommitted records may be redelivered to another member after a rebalance or when the container restarts.

Stopping the container does not mean records were processed successfully. Only committed offsets determine where the group resumes. Business side effects need to be protected by idempotency in case of reprocessing.

### 6.4 Pause and resume

The container supports pause/resume to temporarily stop receiving records while keeping the consumer lifecycle intact. This is useful when downstream is temporarily overloaded or the application needs to throttle processing.

Pause differs from stop:

- Pause tells the consumer to temporarily stop receiving records from assigned partitions, while the consumer maintains membership and continues polling to preserve group participation.
- Stop closes the consumer and leaves the group; partitions may be assigned to another member.
- Resume allows the container to continue receiving records once conditions recover.

Do not call `KafkaConsumer.pause` directly from another thread. Use the container API appropriate for your Spring Kafka version so the container coordinates the operation on the consumer thread.

Pause does not reduce the backlog in Kafka. It only stops or slows consumption. If a pause lasts long, lag and record age increase; you need to monitor and have appropriate resume thresholds or scaling.

## 7. Offset acknowledgment and commit in the container

`KafkaMessageListenerContainer` coordinates the listener with offset acknowledgment mechanisms. Spring Kafka provides `AckMode` to determine when the container commits processed offsets.

If relying on the Kafka client's auto-commit, offsets may be committed on an independent schedule and not accurately reflect when business processing completed. Spring Kafka typically manages auto-commit on the container side in modern configurations; check the effective consumer properties and do not enable auto-commit arbitrarily.

### 7.1 Main AckModes

| AckMode | Commit timing | Usage |
|---|---|---|
| RECORD | After each record is successfully processed by the listener | Record listeners needing per-record commits |
| BATCH | After finishing processing the records from one poll | Common default for containers |
| TIME | When enough time has elapsed since the previous commit | Batch commits by time |
| COUNT | When enough records have been processed | Batch commits by count |
| COUNT_TIME | When either time or count condition is met | Balance commit frequency |
| MANUAL | Listener calls acknowledge; committed with container batch semantics | When application needs acknowledgment control |
| MANUAL_IMMEDIATE | Commit immediately when acknowledged on the consumer thread; if called from another thread, handled via container queue | When immediate acknowledgment is needed in supported contexts |

`AckMode.RECORD` is only suitable for record listeners, not batch listeners. The default `AckMode` is usually `BATCH` unless the application configures otherwise.

### 7.2 Record listener and batch listener

A record listener processes one record at a time:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-reader"
)
public void handle(String value) {
    orderService.process(value);
}
~~~

A batch listener receives a list of records from one poll:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-batch-reader"
)
public void handleBatch(List<String> values) {
    orderService.processBatch(values);
}
~~~

A batch listener can increase throughput when business logic supports batch processing, but an error in the batch requires an appropriate retry/rollback policy. If a failing record causes the batch to fail, you must determine which records already produced side effects and how to reprocess safely.

### 7.3 Manual acknowledgment

With `AcknowledgingMessageListener` or `@KafkaListener` with an `Acknowledgment` parameter, the application can decide when to acknowledge:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-manual-reader"
)
public void handle(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    orderService.process(record.value());

    acknowledgment.acknowledge();
}
~~~

In the example, `acknowledge` is called after business processing. If the process dies before `acknowledge`, the record may be read again. If `acknowledge` is called before business effects complete, there is a risk of the offset advancing while the business operation is incomplete.

Manual ack increases control but also increases responsibility. Do not call `acknowledge` merely because the listener received the record; you must define the exact business condition considered complete.

### 7.4 Sync and async commits

The container can use sync or async commits depending on configuration. Sync commit waits for the broker response, letting you know the commit result immediately but potentially increasing latency. Async commit does not wait for completion on the main processing path, but commit errors must be observed and handled appropriately.

Choose the commit mode based on throughput, reprocessing requirements, and duplicate tolerance. Regardless of the mode used, business operations should still be idempotent because rebalances, process crashes, or commit failures can cause records to be reprocessed.

### 7.5 Offsets with transactions

When the container is configured with a Kafka transaction manager, offsets of processed records can be sent into the same Kafka transaction as output records. Committing the transaction commits the output records and input offsets as a single unit within Kafka's scope.

When the transaction aborts, output records are not visible to `read_committed` consumers and input offsets are not updated by that transaction. The input can be reprocessed. This mechanism is the foundation for consume-transform-produce exactly-once within Kafka's scope.

Transactions do not automatically include database or HTTP side effects. If the listener writes to a database and the Kafka transaction aborts, the database commit does not automatically roll back. Outbox/inbox, idempotency, or compensation is required for systems outside Kafka.

## 8. Error handling in KafkaMessageListenerContainer

The container invokes the listener and coordinates error handling when the listener throws an exception. Specific handling depends on listener type, `CommonErrorHandler`, transaction setup, and Spring Kafka version.

Common error categories:

- Transient errors: timeouts, network interruptions, or temporarily unavailable downstream services.
- Data errors: deserialization failures, invalid payloads, or incompatible schemas.
- Business errors: processing condition violations or inapplicable data.
- Infrastructure errors: broker unavailable, authentication failure, or authorization failure.

### 8.1 CommonErrorHandler

In modern Spring Kafka versions, `CommonErrorHandler` is the unified abstraction for handling record and batch errors. `DefaultErrorHandler` is commonly used to retry with backoff and recover records after an appropriate number of attempts.

You can configure the error handler through the container factory so containers created from the factory share the same policy. For containers created directly, configure the error handler on the container using the API of the version in use.

The policy must define:

- Which exceptions are retried.
- Number of attempts and backoff.
- Which exceptions are not retried.
- When to recover or publish to a DLT.
- How offsets are committed after recovery.
- Whether recovery runs in a separate transaction.

Do not infinitely retry unrecoverable data errors. Also do not classify all database errors as non-retryable if the dependency can recover.

### 8.2 Poison messages and DLT

A poison message is a record that always causes the listener to fail. If retried on the same partition without limits, that record can block the partition from making progress.

A Dead Letter Topic (DLT) allows moving unrecoverable records to a place for investigation and replay. The DLT needs retention, replication, ACLs, monitoring, and a runbook. Publishing to a DLT can also fail; recovery results must be monitored.

When replaying, preserve the event ID, original topic/partition/offset, and exception metadata to avoid creating duplicate side effects or losing the record's origin.

### 8.3 Deserialization errors

If the deserializer fails before the listener receives the record, the listener cannot handle the exception in the usual way. Spring Kafka provides `ErrorHandlingDeserializer` to pass error information through headers and allow the error handler to handle it.

You need to distinguish deserialization errors from business logic errors. If a payload cannot be parsed, you should not infinitely retry the same byte sequence. Use a DLT or an appropriate data-fix/replay process.

### 8.4 Hung or overly slow listeners

A blocked synchronous listener can prevent the consumer from polling further. Symptoms include increased processing latency, large poll gaps, rebalances, or the consumer being removed from the group due to `max.poll.interval.ms`.

Ways to mitigate risk:

- Set timeouts for HTTP, database, and dependency calls.
- Limit records per poll with an appropriate `max.poll.records`.
- Separate workloads with vastly different processing times.
- Use concurrency within partition and downstream capacity limits.
- Monitor consumer lag and processing time per record/batch.
- Do not use an unbounded thread pool to offload everything from the consumer thread without designing acknowledgment and ordering.

## 9. Rebalances and partition assignment

When the container subscribes by topic, the Kafka group coordinator manages membership and partition assignment. A rebalance occurs when membership changes, subscriptions change, or the group needs to redistribute partitions.

Events that commonly trigger rebalances:

- Container start or stop.
- Pod restart or deployment.
- Lost consumer heartbeat.
- Slow listener processing exceeding `max.poll.interval.ms`.
- Topic partition count change.
- Member fencing or network interruption.
- Pattern subscription discovering a new topic.

During a rebalance, partitions may be revoked from an old consumer and assigned to a new consumer. The container coordinates callbacks so the application can finish in-flight work, commit appropriate offsets, or release per-partition resources.

### 9.1 ConsumerRebalanceListener

`ContainerProperties` can accept a `ConsumerRebalanceListener`. This listener lets the application react when partitions are assigned or revoked.

Illustrative example:

~~~java
containerProperties.setConsumerRebalanceListener(
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {
            log.info("Revoked partitions: {}", partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
            log.info("Assigned partitions: {}", partitions);
        }
    }
);
~~~

The revoked callback is useful for flushing per-partition state or recording in-flight work. The assigned callback is useful for initializing state tied to a partition.

Do not perform long blocking work inside callbacks. Rebalances have deadlines and other members are waiting for the group to finish. If the application needs to commit offsets, it must follow container semantics and avoid committing a position beyond successfully processed records.

### 9.2 Rebalances and duplicate processing

If a record already produced a business side effect but the offset was not committed, the partition may be assigned to another consumer and the record read again. This is common at-least-once behavior.

Consumers should use idempotency keys, unique constraints, or an inbox table to ensure reprocessing does not create duplicate side effects. The container helps manage offsets and assignments, but it cannot automatically know whether the database committed the business change.

## 10. Pause, resume, and load throttling

`KafkaMessageListenerContainer` provides lifecycle control for the application to pause and resume the consumer. Pause/resume is useful when throttling load or maintaining downstream systems.

### 10.1 When to pause?

Some scenarios:

- The database is overloaded and the application needs to reduce reading speed.
- A downstream service is rate-limited.
- Waiting for a resource or dependency to recover.
- The application is draining a stream before maintenance.
- A partition needs to temporarily stop processing by operational decision.

Pause does not delete records and does not commit offsets on behalf of the listener. Records remain in Kafka, and lag may grow. Pause duration thresholds and resume conditions are needed.

### 10.2 Pause vs. stop

| Action | Consumer membership | Receiving records | Partition assignment |
|---|---|---|---|
| pause | Usually continues maintaining group membership | Temporarily stops receiving records from paused partitions | Keeps assignment |
| resume | Continues as before | Resumes receiving records | Keeps assignment if group does not rebalance |
| stop | Consumer closes and leaves group | Receives no records | Partitions may be assigned to another member |

Pause/resume does not replace system-wide backpressure. If producers keep writing faster than consumers, the backlog grows. Monitor lag, record age, and capacity when deciding to pause.

### 10.3 Pausing a partition

Some Spring Kafka APIs allow pausing/resuming specific partitions instead of the entire container. This is useful when only one partition or a group of keys has an issue. Availability and API names depend on the version; use container APIs rather than accessing `KafkaConsumer` from external threads.

When pausing one partition, other partitions managed by the same consumer can continue processing. However, if the listener thread is currently blocked by a record from another partition, pausing one partition does not solve thread starvation.

## 11. Container events and observability

Spring Kafka emits application events to observe consumer lifecycle and health. Specific events depend on the version, but common groups include:

- `ConsumerStartingEvent` and `ConsumerStartedEvent`.
- `ConsumerStoppedEvent`.
- `ListenerContainerIdleEvent`.
- `NonResponsiveConsumerEvent`.
- `ConsumerPausedEvent` and `ConsumerResumedEvent`.
- `ConsumerPartitionPausedEvent` and `ConsumerPartitionResumedEvent`.
- `ContainerStoppedEvent`, `ContainerPausedEvent`, and `ContainerResumedEvent`.

Event listeners can be used to log, update operational state, or raise alerts. Do not use event callbacks to run long blocking work on the event-publishing thread.

### 11.1 Idle event

An idle event can be emitted when the container receives no records for a configured interval. Idle is not necessarily an error. The topic might have no data or producers might be stopped.

Combine idle events with expected traffic, producer rate, and consumer lag. If a topic is expected to have continuous data but the container is idle while lag increases, that is a sign requiring investigation.

### 11.2 Non-responsive consumer

`NonResponsiveConsumerEvent` can help detect a consumer that has not polled for an abnormal duration. Causes may include a hung listener, JVM pause, thread starvation, or downstream calls without timeouts.

Upon receiving the event, check thread dumps, processing latency, downstream metrics, and `max.poll.interval.ms`. Do not automatically restart the container before understanding the root cause; restarting can cause continuous rebalances and worsen the incident.

### 11.3 Metrics

Track metrics by container, client, group, topic, and partition:

| Scope | Metrics/signals |
|---|---|
| Container | Running state, pause state, idle duration, consumer thread activity |
| Consumer client | Poll latency, heartbeat, commit latency, assigned partitions |
| Group | Member count, rebalance count, assignment stability |
| Processing | Record processing time, batch duration, listener error rate |
| Offset | Committed offset, current position, lag per partition |
| Downstream | Database pool, HTTP latency, timeout, queue depth |
| Recovery | Retry count, rollback count, DLT publish count |

Metric names and tagging depend on Spring Kafka, Kafka client, Micrometer, and exporter versions. Verify the actual exported metrics before writing alerts.

## 12. Transaction integration with listener containers

`KafkaMessageListenerContainer` can coordinate with a transaction manager so each listener execution runs in a Kafka transaction. When configured properly, the container starts a transaction before calling the listener, allows `KafkaTemplate` to send output into that transaction, and sends input offsets into the same transaction.

Consume-transform-produce flow:

~~~mermaid
sequenceDiagram
    participant C as KafkaMessageListenerContainer
    participant K as Kafka
    participant A as Application listener
    C->>K: poll input
    K-->>C: input record
    C->>K: begin Kafka transaction
    C->>A: invoke listener
    A->>K: send output record
    C->>K: send input offset to transaction
    C->>K: commit transaction
    K-->>C: commit result
~~~

If the listener throws an exception and the transaction rolls back, the output record is not visible to `read_committed` consumers and the input offset is not committed by that transaction. The input record can be read again.

Distinguish Kafka transactions from database transactions. If the listener updates a database before the Kafka transaction commits, the database side effect does not automatically roll back when the Kafka transaction aborts. Use outbox/inbox or idempotency for side effects outside Kafka.

## 13. Spring Kafka container factory and KafkaListenerEndpointRegistry

In the `@KafkaListener` model, applications typically do not manage each `KafkaMessageListenerContainer` directly. Containers are created from `KafkaListenerContainerFactory` and managed through `KafkaListenerEndpointRegistry`.

Components:

- `ConcurrentKafkaListenerContainerFactory` configures containers for endpoints.
- `@KafkaListener` declares a listener endpoint.
- `KafkaListenerEndpointRegistry` holds listener containers created from annotations.
- `ConcurrentMessageListenerContainer` coordinates child `KafkaMessageListenerContainer` instances.
- `KafkaMessageListenerContainer` manages one `KafkaConsumer`.

You can retrieve a container by ID to control its lifecycle:

~~~java
@Component
class ListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    ListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resumeOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
~~~

The example uses the ID declared in `@KafkaListener`. If the endpoint uses `ConcurrentMessageListenerContainer`, the registry returns the wrapper. Pause/resume on the wrapper is coordinated to the child containers.

Do not store references to the internal `KafkaConsumer` to manipulate it directly. Use the `MessageListenerContainer` interface or Spring Kafka-supported APIs to keep the lifecycle consistent.

### 13.1 Configuring the factory

A factory can configure concurrency, ack mode, error handler, and record/batch behavior:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, String> factory =
        new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

A listener can select the factory:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "orders-reader",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void handle(String value) {
    orderService.process(value);
}
~~~

The factory creates a `ConcurrentMessageListenerContainer` with concurrency 3; the wrapper manages three child `KafkaMessageListenerContainer` instances. Each child has its own consumer and thread.

### 13.2 When to use KafkaMessageListenerContainer directly?

Use directly when:

- A component needs to own a consumer with an explicit lifecycle.
- Subscriptions are created dynamically based on runtime configuration.
- A standalone container is needed without going through an annotation endpoint.
- Building an internal framework or adapter that requires container control.

Use `@KafkaListener` and factory when:

- The listener is part of a standard Spring application.
- Dependency injection, method listeners, and annotation metadata are needed.
- Concurrency and lifecycle should be managed by the endpoint registry.
- Shared configuration for error handlers, converters, interceptors, and transactions is desired.

Do not create containers directly just to avoid understanding factory configuration. Doing so can force the application to manually manage lifecycle, shutdown, metrics, and error handling.

## 14. Common operational errors

| Symptom | Possible cause | How to investigate |
|---|---|---|
| Container fails to start | Invalid ConsumerFactory, deserializer, security, or topic config | Read startup exception and effective consumer properties |
| Container runs but receives no records | Wrong topic/group, offset at end, no partitions assigned, or empty topic | Check assignment, committed offset, log end, and `auto.offset.reset` |
| Frequent rebalances | Poll too slow, heartbeat/network error, or pod restart | Measure listener duration, poll interval, and member lifecycle |
| Lag grows despite live consumer | Slow downstream, blocked listener, hot partition, or long transaction | Compare processing latency, partition lag, and transaction state |
| Duplicate record processing | Offset uncommitted before crash/rebalance or retry | Check ack mode, commit failures, and idempotency |
| Records lost from application view | Offset committed too early, wrong group ID, or `latest` for new group | Reconcile group offset and business side effects |
| Listener not invoked | Deserialization error or error handler holding record | Check deserializer, error handler, and DLT |
| Prolonged application stop | Blocking listener or large shutdown timeout | Check thread dump, downstream timeouts, and shutdown config |
| Paused but lag keeps growing | Producer continues writing while consumer is paused | Monitor produce rate, lag, and pause duration |
| Many idle consumers | Concurrency greater than partition count | Compare consumer count and partition count |

## 15. Investigation procedure when container is not processing records

When a container is running but making no progress, follow this order:

1. Verify the effective listener container ID, group ID, topic subscription, and `ConsumerFactory`.
2. Check whether the container is running or paused.
3. Check whether the consumer is assigned partitions.
4. Compare committed offset, current position, and log end offset per partition.
5. Verify `auto.offset.reset` and group offsets are appropriate.
6. Check poll loop, poll interval, processing duration, and thread state.
7. Check deserializers, listener exceptions, `CommonErrorHandler`, and DLT.
8. Check downstream databases, HTTP calls, thread pools, and connection pools.
9. Check rebalances, broker availability, network, and transaction state if applicable.
10. After fixing, confirm the listener receives records, offsets advance, and business side effects complete once according to the idempotency policy.

Do not increase concurrency or reset offsets before determining whether the container lacks assignment, is paused, is blocked, or is waiting on a dependency. Each cause requires a different recovery action.

## 16. Configuration and operations checklist

**Container and listener**

- [ ] Understand that each `KafkaMessageListenerContainer` manages one consumer.
- [ ] Listener type matches record or batch.
- [ ] `ContainerProperties` specifies the correct topic, pattern, or partition.
- [ ] Poll timeout and `max.poll.interval.ms` are balanced with processing time.
- [ ] Listener does not block indefinitely on downstream calls.
- [ ] Consumer is manipulated only via supported container lifecycle/APIs.

**Offsets and errors**

- [ ] `AckMode` matches the listener and business requirements.
- [ ] Auto-commit is checked and the container manages offsets as intended.
- [ ] Manual acknowledgment is called only after business effects meet completion criteria.
- [ ] `CommonErrorHandler` has finite retries and exception classification.
- [ ] Poison messages have a DLT/recovery policy and replay procedure.
- [ ] Business processing has idempotency when records are redelivered.

**Concurrency and lifecycle**

- [ ] Distinguish `KafkaMessageListenerContainer` from `ConcurrentMessageListenerContainer`.
- [ ] Concurrency does not exceed partition/downstream capacity needs.
- [ ] Start/stop is managed by Spring lifecycle or a single owner.
- [ ] Shutdown timeout aligns with the termination grace period.
- [ ] Pause/resume has conditions and bounded duration.
- [ ] Rebalance callbacks do not perform long blocking work.

**Observability and recovery**

- [ ] Logs include container ID, group ID, topic, partition, and offset.
- [ ] Track lag, assignment, rebalances, and processing latency.
- [ ] Alerts exist for non-polling or abnormally idle containers.
- [ ] Track downstream saturation and deserialization errors.
- [ ] Runbooks exist for container stopped, paused, rebalance loop, and DLT.
- [ ] Tested restart, scale, shutdown, and error handling in an appropriate environment.

`KafkaMessageListenerContainer` is the class that manages a single `KafkaConsumer` in Spring Kafka. It turns poll operations, listener invocations, acknowledgments, rebalances, and lifecycle into a configurable operational unit. When concurrency is needed, `ConcurrentMessageListenerContainer` creates multiple child containers; for standard listeners, `@KafkaListener` and container factories let Spring manage them. Good design aligns subscription, offset policy, error handling, and shutdown behavior with business processing requirements.

