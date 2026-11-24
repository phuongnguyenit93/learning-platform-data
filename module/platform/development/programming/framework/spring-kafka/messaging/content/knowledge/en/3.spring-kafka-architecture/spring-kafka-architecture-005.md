# ConcurrentMessageListenerContainer

## Lesson Objectives

In the **Spring Kafka Architecture** chapter, this lesson focuses on `ConcurrentMessageListenerContainer`: the container that coordinates multiple consumers so a listener can process Kafka partitions in parallel within the same consumer group.

**SPRING_KAFKA_MESSAGING** covers building applications that send and receive events with Spring Kafka using KafkaTemplate and @KafkaListener, while understanding topics, partitions, offsets, consumer groups, serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing. Within that scope, `ConcurrentMessageListenerContainer` is a key component on the consumer side: it determines how Spring Kafka creates, manages, and coordinates multiple consumers to increase parallel processing capacity.

After this lesson, learners will be able to:

- Distinguish between `ConcurrentMessageListenerContainer`, `KafkaMessageListenerContainer`, and `ConcurrentKafkaListenerContainerFactory`.
- Describe the relationship between concurrency, consumers, partitions, and consumer groups.
- Configure listener concurrency using Spring Kafka.
- Explain how the container manages lifecycle, offsets, rebalances, and errors when multiple consumers are present.
- Choose an appropriate concurrency level based on partition counts, processing load, and downstream system capacity.
- Identify scenarios where increasing concurrency does not improve throughput.

## 1. Why is ConcurrentMessageListenerContainer needed?

A Kafka consumer typically processes records from the partitions assigned to it. If an application uses only a single consumer for a listener, the partitions owned by that consumer are processed through a single consumption loop. As load grows, a single consumer can become a processing bottleneck.

Spring Kafka provides `ConcurrentMessageListenerContainer` to manage multiple consumers inside a single listener container. Each consumer is run by a child `KafkaMessageListenerContainer`. The consumers join the consumer group and receive partitions through Kafka's assignment mechanism.

For example, topic `orders.created` has 6 partitions. A Billing application runs a listener with concurrency set to 3. Spring Kafka creates 3 child consumer containers. Kafka distributes the 6 partitions across those 3 consumers; each consumer may receive multiple partitions and process records belonging to its assigned partitions.

~~~mermaid
flowchart TB
    A["ConcurrentMessageListenerContainer"] --> B["KafkaMessageListenerContainer 1"]
    A --> C["KafkaMessageListenerContainer 2"]
    A --> D["KafkaMessageListenerContainer 3"]
    B --> E["Kafka Consumer 1"]
    C --> F["Kafka Consumer 2"]
    D --> G["Kafka Consumer 3"]
    E --> H["Assigned partitions"]
    F --> I["Assigned partitions"]
    G --> J["Assigned partitions"]
~~~

The parent container is responsible for coordinating the child containers. The actual consumers still follow Kafka's consumer group protocol. Thus, Spring Kafka does not create partitions itself or alter the broker's partition assignment rules.

## 2. Distinguishing Related Components

The class names look quite similar, but they serve different roles.

| Component | Role |
|---|---|
| `ConcurrentMessageListenerContainer<K, V>` | Container that manages multiple child listener containers for concurrent processing |
| `KafkaMessageListenerContainer<K, V>` | Container that manages a single Kafka consumer and invokes the listener for records the consumer receives |
| `ConcurrentKafkaListenerContainerFactory<K, V>` | Factory that creates `ConcurrentMessageListenerContainer` instances for `@KafkaListener` methods |
| `ConsumerFactory<K, V>` | Creates Kafka consumers with the corresponding configuration and deserializers |
| `ContainerProperties` | Holds container configuration such as topics, partitions, acknowledgement mode, timeouts, and related listeners |
| `@KafkaListener` | Declares an application method to receive records; the listener container executes that method |

High-level relationships:

~~~mermaid
flowchart TD
    A["@KafkaListener"] --> B["KafkaListenerAnnotationBeanPostProcessor"]
    B --> C["ConcurrentKafkaListenerContainerFactory"]
    C --> D["ConcurrentMessageListenerContainer"]
    D --> E["KafkaMessageListenerContainer"]
    E --> F["ConsumerFactory"]
    F --> G["KafkaConsumer"]
    G --> H["Kafka Broker"]
~~~

When the application starts, Spring processes the `@KafkaListener` annotation, locates the specified factory, and creates the corresponding container. If the factory has concurrency greater than 1, the container manages multiple child containers. Each child container creates and manages one Kafka consumer.

A useful way to remember this:

- The factory defines how to build containers.
- The concurrent container coordinates child consumer containers.
- The Kafka message listener container manages a single consumer.
- The listener is the business code invoked when records arrive.

## 3. Concurrency and Partition Model

### 3.1. What does concurrency mean?

Concurrency is the number of child consumer containers managed by a `ConcurrentMessageListenerContainer`. Each child container has its own consumer and runs consumption work on its own thread.

If you configure:

`concurrency = 3`

then the container can create 3 consumers for the same listener and the same consumer group. These three consumers can process different partitions concurrently.

Concurrency is not an arbitrary number of threads calling the same consumer. A Kafka consumer is not safe when called concurrently by multiple threads. Spring Kafka keeps each consumer scoped to its container and container-managed processing thread.

### 3.2. Partitions limit parallelism

Within the same consumer group, a partition at any given time is assigned to at most one consumer. Therefore, the number of consumers actually receiving partitions cannot exceed the number of partitions assigned to the group.

Example with a topic that has 4 partitions:

| Concurrency of one instance | Consumers created | Consumers able to receive partitions | Outcome |
|---:|---:|---:|---|
| 1 | 1 | 1 | One consumer processes all 4 partitions |
| 2 | 2 | Up to 2 | Each consumer can process 2 partitions |
| 4 | 4 | Up to 4 | Possible to have one consumer per partition |
| 6 | 6 | Up to 4 | At least 2 consumers receive no partitions |

Consumers without assigned partitions can still remain in the group waiting for assignment changes, but they contribute no extra record-processing capacity at that time.

This rule applies to the total number of consumers in the group, not just a single process. If there are multiple application instances, the total number of consumers is the sum of concurrency across all running instances. For instance, 2 instances each configured with concurrency 3 create a total of 6 consumers in the group.

### 3.3. Partition distribution example

Suppose a topic has 6 partitions and one instance has concurrency 3. An assignment might look like this:

~~~mermaid
flowchart TB
    T["orders.created: 6 partitions"]
    T --> P0["Partition 0"]
    T --> P1["Partition 1"]
    T --> P2["Partition 2"]
    T --> P3["Partition 3"]
    T --> P4["Partition 4"]
    T --> P5["Partition 5"]
    P0 --> C1["Consumer 1"]
    P3 --> C1
    P1 --> C2["Consumer 2"]
    P4 --> C2
    P2 --> C3["Consumer 3"]
    P5 --> C3
~~~

This is only an illustrative diagram. Actual assignment depends on the partition assignor, number of consumers in the group, number of topics, partition counts, and active consumers. Do not rely on the diagram to assume partitions are always split evenly in every configuration.

### 3.4. Consumer groups and multiple instances

Child containers normally share the group ID configured for the listener. Kafka treats each child consumer as a separate group member. If the application has multiple instances, consumers from all instances join the group and the broker distributes partitions across all members.

Example:

| Instance | Concurrency | Number of consumers |
|---|---:|---:|
| Billing-1 | 2 | 2 |
| Billing-2 | 2 | 2 |
| Billing-3 | 2 | 2 |
| **Total** | | **6** |

With 6 partitions, the group can assign one partition to each consumer. If scaled up to 9 consumers while the topic still has only 6 partitions, at most 6 consumers receive partitions at the same time.

If two applications intend to independently receive the same events, they generally need different group IDs. If they share a group ID, Kafka distributes partitions among consumers in the group rather than delivering every record to each application.

## 4. Configuring ConcurrentMessageListenerContainer

In a Spring application, the common approach is to configure `ConcurrentKafkaListenerContainerFactory`. The factory creates `ConcurrentMessageListenerContainer` when Spring registers listeners.

The following example creates a factory with concurrency set to 3:

~~~java
@Configuration
@EnableKafka
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersListenerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Points to understand:

- `setConsumerFactory(...)` supplies how Kafka consumers are created along with key/value deserializer configuration.
- `setConcurrency(3)` instructs containers created from the factory to manage 3 child consumer containers.
- `setAckMode(RECORD)` selects committing offsets after successfully processing each record according to the container mechanism.
- `@EnableKafka` enables annotation infrastructure in plain Spring configuration. With Spring Boot, listener infrastructure is typically auto-configured; when declaring custom configuration, verify both application settings and which factory is in use.

A listener can specify the factory just declared:

~~~java
@Service
public class OrderCreatedListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "billing-service",
        containerFactory = "ordersListenerFactory"
    )
    public void handle(OrderCreated event) {
        // Billing business processing.
    }
}
~~~

Spring creates the container for the listener method and applies concurrency from the factory. If the application has multiple listener groups with different processing requirements, you can declare multiple factories with distinct configurations—for example, one factory for order processing and another for inventory updates.

### 4.1. Configuring a batch listener

If business logic fits batch processing, the factory can enable batch listener mode:

~~~java
factory.setBatchListener(true);
~~~

The listener method then receives a collection of records instead of a single record:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-batch",
    containerFactory = "batchListenerFactory"
)
public void handleBatch(List<ConsumerRecord<String, OrderCreated>> records) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        // Process each record in the batch.
    }
}
~~~

Batch listeners can reduce listener invocation overhead and suit batch write operations. However, a slow batch increases the time between polls; evaluate `max.poll.interval.ms`, batch size, and the load tolerance of dependent systems.

Do not enable batching solely for throughput if business requirements demand per-record acknowledgement or individual error handling. Retry and commit strategies must be designed alongside batch semantics.

### 4.2. Choosing separate concurrency per listener

Each listener can use its own factory to set concurrency based on its load profile. For example:

- A listener receiving order events might need high concurrency because processing is lightweight and the topic has many partitions.
- A listener generating invoices might need lower concurrency because the database is the bottleneck.
- A listener processing events in order for certain keys might need partition counts and concurrency aligned with ordering requirements.

Concurrency should be a decision based on measurements and partition structure, not a uniform value applied to every listener.

## 5. Container and Consumer Lifecycle

### 5.1. Initialization and startup

When Spring initializes a listener endpoint, the factory creates a `ConcurrentMessageListenerContainer`. The parent container creates child `KafkaMessageListenerContainer` instances according to concurrency. Each child container creates a consumer from `ConsumerFactory`, subscribes to join the group or applies configured assignments, and then starts the poll loop.

Startup flow:

~~~mermaid
sequenceDiagram
    participant S as Spring Context
    participant F as Container Factory
    participant P as Concurrent Container
    participant C as Child Container
    participant K as Kafka Cluster

    S->>F: Create listener endpoint
    F->>P: Create ConcurrentMessageListenerContainer
    P->>C: Create child containers by concurrency
    C->>K: Create consumer and join group
    K-->>C: Assign partitions
    C->>K: Poll records
~~~

### 5.2. Polling and invoking the listener

Each child consumer container runs an independent consumption loop. The consumer polls Kafka, the container passes records to the listener adapter, and the adapter invokes the application method.

~~~mermaid
sequenceDiagram
    participant K as Kafka Broker
    participant C as Consumer Thread
    participant A as Spring Listener Adapter
    participant L as @KafkaListener Method

    C->>K: poll()
    K-->>C: ConsumerRecords
    C->>A: Pass records
    A->>L: Invoke listener
    L-->>A: Processing complete
    A-->>C: Processing result
    C->>K: Commit offset per configuration
~~~

A listener bean is normally a singleton in Spring. When concurrency is greater than 1, the same method can be invoked concurrently by multiple threads. If the listener uses mutable fields, counters, collections, or non-thread-safe objects, synchronize access or change the design to prevent race conditions.

Do not retain a reference to the Kafka consumer to call from another business thread. Kafka consumer is not thread-safe; use the listener container APIs and interaction mechanisms supported by Spring Kafka.

### 5.3. Stopping the container

The parent container manages the lifecycle of child containers. When the Spring context stops or the container receives a stop command, Spring Kafka coordinates stopping consumers, exiting poll loops, and releasing resources. Applications should give containers enough time to finish in-flight processing with appropriate shutdown configuration and timeouts.

If a listener runs too long, shutdown can require waiting. Avoid unbounded business tasks or tasks lacking cancellation/timeout mechanisms, as they can slow down shutdowns and deployments.

### 5.4. Pausing and resuming

Spring Kafka provides pause/resume APIs at the listener container and partition levels. They are useful when you need to temporarily shed load, maintain dependent systems, or apply backpressure control.

Pausing a consumer does not mean removing its assignment or leaving the consumer group. The consumer must still maintain appropriate activity to avoid being considered dead. When resumed, the consumer continues consuming under its current assignment if the group has not rebalanced.

## 6. Partition Distribution and Partition Assignors

Kafka decides how partitions are distributed to consumers in a group via a partition assignor. Spring Kafka manages the consumers and listener containers; assignment rules are executed by the Kafka client and group coordinator.

Some common strategies:

- **RangeAssignor:** distributes partitions in contiguous ranges per consumer on each topic. With multiple topics, distribution across consumers can become uneven.
- **RoundRobinAssignor:** distributes partitions cyclically across consumers, often giving a more balanced distribution when multiple topics have similar partition counts.
- **StickyAssignor:** aims to balance assignments while minimizing how many partitions move when the group changes.
- **CooperativeStickyAssignor:** uses cooperative rebalancing to avoid revoking all partitions during a single rebalance.

The actual strategy depends on the Kafka client version and `partition.assignment.strategy` configuration. Inspect the running consumer configuration before concluding how partitions are distributed.

Example of an imbalance scenario: an application subscribes to two topics, each with 3 partitions, and the group has 6 consumers. A Range-style assignor may assign partitions per topic so that some consumers receive partitions from both topics while other consumers receive none. A Round-Robin-style assignor can spread the six partitions more evenly in that situation.

Not every case requires changing the assignor. Measure assignments, idle consumer counts, consumer lag, and throughput before adjusting.

## 7. Concurrency, Ordering, and Offset Handling

### 7.1. Record ordering

Kafka preserves ordering within a single partition. A consumer in the group assigned that partition reads records in offset order. With concurrency, different partitions can be processed in parallel by different consumers.

If events for the same entity must stay ordered, producers typically use the same key so those events route to the same partition. The consumer group then processes that partition in the order Kafka provides.

Concurrency does not create global ordering across multiple partitions. If a listener dispatches work to another thread pool and returns before work completes, business completion order may also differ from arrival order. When offloading processing asynchronously, the application must manage ordering and acknowledgements itself.

### 7.2. Acknowledgement and offset commits

Each consumer tracks offsets for its assigned partitions. The container manages acknowledgements and commits based on `ContainerProperties.AckMode` and consumer settings.

Common modes:

| Ack mode | How acknowledgement works |
|---|---|
| `RECORD` | Acknowledges after the listener finishes processing each record |
| `BATCH` | Acknowledges records from the poll after the listener finishes the corresponding batch |
| `MANUAL` | Listener calls `Acknowledgment.acknowledge()`; container applies commits according to mode semantics |
| `MANUAL_IMMEDIATE` | Commits immediately when acknowledge is called on the consumer thread; if called from another thread, the commit request is routed back to the consumer thread |

Concurrency does not replace offset policy. Each child consumer container manages the partitions it owns; the application must choose an ack mode compatible with business side effects and error handling strategy.

If offsets are committed before business work finishes, a failure can cause records to be skipped. If processing finishes before offsets are committed, records can be redelivered after a restart or rebalance. Therefore, consumers should be designed to be idempotent.

### 7.3. Rebalances when consumer count changes

When application instances scale up/down, consumers start/stop, or subscriptions change, Kafka can trigger a rebalance to redistribute partitions. During that process:

1. Consumers may be asked to revoke currently owned partitions.
2. The container completes revoke/assign callbacks according to the configured mechanism.
3. The group coordinator computes new assignments.
4. Consumers resume polling with their assigned partitions.

Rebalances can briefly interrupt consumption. If rebalances happen frequently, check listener processing times, poll/heartbeat settings, network health, instance rollouts, and assignment strategy.

Rebalance callbacks can be used for tasks that prepare or clean up per-partition state. Do not use callbacks as a place to execute long-running business logic, as that can slow down the rebalance process.

## 8. Choosing the Right Concurrency

There is no single optimal concurrency value for every system. Consider partitions, instance counts, processing duration, resources, and dependent systems together.

### 8.1. Start from the partition count

For a group, the total number of usefully active consumers is bounded by the total number of assigned partitions. If a topic has 8 partitions and the application runs one instance, concurrency of 8 is a reasonable starting experiment to evaluate maximum partition-level parallelism. If the application runs 2 instances, concurrency of 4 per instance also produces 8 consumers in total.

This is only a starting point. If processing is lightweight, a consumer can handle multiple partitions; if processing is heavy or requires load isolation, a different setting may be needed.

### 8.2. Measure processing time and downstream capacity

Adding consumers can increase concurrent requests to databases, REST APIs, or storage systems. If a downstream system only tolerates 10 concurrent operations, setting total concurrency to 40 can increase timeouts and retries instead of throughput.

Measure:

- Average and high-percentile listener processing times.
- Records processed per second per consumer.
- Consumer lag by partition.
- Connection pools, CPU, memory, and I/O.
- Error rates, timeouts, and retry counts.
- Key distribution and load skew across partitions.

### 8.3. Avoid hot partitions

Even when a topic has many partitions, a very high-frequency key can turn the partition holding that key into a hotspot. Increasing concurrency cannot split a single partition across multiple consumers in the same group.

You may need to revisit the key strategy, partition count, or how business tasks are broken down. Changing keys can affect ordering and how consumers process data, so evaluate the data contract before deploying.

### 8.4. Balance polling and processing duration

Consumers must keep polling within configured limits. If processing between polls takes longer than `max.poll.interval.ms`, Kafka may consider the consumer unresponsive and trigger a rebalance. Large batches, slow listeners, or downstream timeouts can all contribute to this situation.

Increasing concurrency does not automatically fix an overly slow listener. Consider reducing batch size, optimizing business logic, intentionally tuning timeouts, or separating long-running work into a controlled processing pipeline.

## 9. Error Handling in a Concurrent Environment

Each child container has its own consumer, while error handling policies are typically configured on the factory or container. Spring Kafka supports error handlers, retries, backoff, and dead-letter recovery.

When multiple consumers run concurrently, keep in mind:

- An exception from a listener invocation must be handled by the corresponding error handler.
- Blocking retries can slow down the consumer handling that partition; other partitions managed by other consumers can continue moving.
- Retry topics move records onto a separate retry flow, which can change the observed order among events sharing the same key.
- When a consumer leaves the group or fails, partitions may be reassigned to another consumer; uncommitted records may be redelivered.
- DLTs and logs should carry topic, partition, offset, key, and error details to aid investigation.

High concurrency can cause downstream errors to amplify faster because multiple consumers retry or call the dependent service simultaneously. Retry limits, backoff, circuit breakers at the right layer, and downstream capacity must be evaluated together.

## 10. Observability and Operations

To know whether concurrency is effective, observe both the container and the Kafka group.

Important signals:

| Signal | Meaning |
|---|---|
| Consumer count and assignment | Number of active consumers and partitions assigned to each consumer |
| Consumer lag by partition | Lag of each partition, helping detect hot partitions |
| Listener processing time | Time taken to process a record or batch |
| Records consumed rate | Actual consumer throughput |
| Rebalance count and duration | Stability of the consumer group |
| Retry/DLT count | Error handling health and invalid data rates |
| Consumer pause state | Whether a consumer or partition is currently paused |
| CPU, memory, connection pool | Resource limits of the application and dependent systems |

Spring Kafka emits application events related to listener containers, idle consumers, pause/resume, and partition states. Combine them with Kafka client metrics and Spring's observability stack to build alerts.

When investigating a slow listener, do not look solely at total consumer lag. Compare per-partition lag against assignments to determine whether one partition is hot or all consumers are running slowly.

## 11. Testing ConcurrentMessageListenerContainer

Testing should verify both business behavior and how listeners are configured.

Approaches:

1. Use EmbeddedKafka in Spring Kafka Test to run a broker for integration testing.
2. Use Testcontainers when you need a Kafka environment closer to deployment.
3. Send multiple records to different partitions and verify the listener receives all data.
4. Inspect container/factory configuration to verify concurrency is properly applied.
5. Check whether the listener bean is safe when invoked from multiple threads.
6. Test behavior when consumers stop, restart, or undergo group rebalances.
7. Test errors, retries, DLT, and reprocessing of uncommitted records.

When testing parallelism, do not send all records to a single partition and expect them to be processed concurrently. A single partition within a group is assigned to only one consumer at a time. To test multiple consumers working simultaneously, ensure enough partitions exist and data is distributed across those partitions.

## 12. Common Configuration Errors

| Symptom | Possible cause | Investigation steps |
|---|---|---|
| Increased concurrency with unchanged throughput | Few partitions, downstream bottleneck, or skewed key distribution | Check assignment, per-partition lag, and processing time |
| Some consumers receive no records | More consumers than assigned partitions or uneven assignment | Check consumer group and partition assignor |
| Concurrent listener calls corrupt state | Listener bean uses non-thread-safe mutable state | Remove shared mutable state or synchronize access |
| Continuous rebalances | Long processing, poll timeouts, network issues, or crashing/restarting instances | Check max.poll.interval.ms, listener duration, and consumer logs |
| Duplicate record processing | Offset uncommitted before consumer stop or rebalance | Check ack mode and idempotency design |
| Increased concurrency overloads database | Multiple concurrent consumers exceed connection pool or database capacity | Reduce concurrency, throttle load, and measure downstream |
| Business ordering differs from expectations | Related events span multiple partitions or uncontrolled async processing | Review keys, partitioning, and completion tracking |

## 13. Pre-Production Checklist

- [ ] Identify topic, partition count, and consumer group for the listener.
- [ ] Choose concurrency based on total consumers across all instances.
- [ ] Verify actual partition assignments and partition assignor.
- [ ] Ensure listener beans are safe when called concurrently by multiple threads.
- [ ] Choose record listener or batch listener according to business needs.
- [ ] Configure appropriate acknowledgement and offset commit behavior.
- [ ] Design idempotent processing for redelivered records.
- [ ] Set retry limits, backoff, and DLT strategy.
- [ ] Evaluate `max.poll.interval.ms` against actual processing times.
- [ ] Measure consumer lag, throughput, processing time, and downstream load.
- [ ] Test instance scaling, rebalances, restarts, and shutdowns.
- [ ] Set alerts for inactive consumers, rising lag, or abnormal DLT spikes.

## Conclusion

`ConcurrentMessageListenerContainer` is the container that coordinates multiple child `KafkaMessageListenerContainer` instances so a single listener can consume partitions in parallel. Each child container manages one Kafka consumer; consumers join the consumer group and receive partitions according to Kafka assignments. Useful concurrency therefore depends on assigned partition counts, total instances, partition distribution, and application processing capacity.

Configuring concurrency is only one piece of consumer design. For a reliable messaging flow, combine proper partitioning, thread-safe listeners, accurate acknowledgement/offset handling, bounded error handling, idempotency, consumer lag observability, and testing of rebalance scenarios.
