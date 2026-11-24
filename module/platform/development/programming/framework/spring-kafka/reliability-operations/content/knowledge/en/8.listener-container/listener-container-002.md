# ConcurrentMessageListenerContainer

## 1. Role in Spring Kafka

`ConcurrentMessageListenerContainer` is the Spring Kafka container used to run a listener with multiple Kafka consumers concurrently. It manages the lifecycle of child containers, coordinates listener configuration, and distributes record consumption across multiple consumer threads.

The Kafka client provides `KafkaConsumer`, where each consumer polls on its owning thread and joins a consumer group to receive partition assignments. Spring Kafka provides `KafkaMessageListenerContainer` to manage one consumer. When concurrency is needed, `ConcurrentMessageListenerContainer` creates and manages multiple child `KafkaMessageListenerContainer` instances.

For example, setting concurrency to 3 typically creates three child containers, each with one Kafka consumer and its own poll processing thread. These consumers use the same listener group configuration, so Kafka distributes the group's partitions among them.

Importantly, concurrency creates additional consumers and partition-level parallelism. It does not allow a single partition to be read simultaneously by multiple consumers in the same group, nor does it automatically increase the topic's partition count.

## 2. Parent container and child container structure

The structure can be pictured as follows:

~~~text
ConcurrentMessageListenerContainer
             |
             +-- KafkaMessageListenerContainer #1
             |          |
             |          +-- KafkaConsumer #1
             |          +-- Consumer thread #1
             |
             +-- KafkaMessageListenerContainer #2
             |          |
             |          +-- KafkaConsumer #2
             |          +-- Consumer thread #2
             |
             +-- KafkaMessageListenerContainer #3
                        |
                        +-- KafkaConsumer #3
                        +-- Consumer thread #3

             All consumers join the
             listener's single consumer group
~~~

The parent container coordinates start, stop, pause/resume, and state of the child containers. Each child container manages one Kafka consumer and polls on its own thread.

Thus, when saying a listener has concurrency 3, we mean there are up to three active consumer instances for that listener in the same application. How many consumers actually have partitions to read depends on the partition count and how Kafka assigns partitions.

### 2.1. Differences between the two container types

| Component | Responsibility |
|---|---|
| `KafkaMessageListenerContainer` | Manages one Kafka consumer, poll loop, listener invocation, and offset commits |
| `ConcurrentMessageListenerContainer` | Manages multiple child `KafkaMessageListenerContainer` instances and coordinates their lifecycle |
| `KafkaConsumer` | Kafka client performing subscribe/assign, poll, commit, and receiving records |
| `ConcurrentKafkaListenerContainerFactory` | Creates the appropriate container for endpoints declared with `@KafkaListener` |

Applications usually do not need to create each child container manually. You can configure a `ConcurrentKafkaListenerContainerFactory` and let Spring Kafka create the container for listener endpoints.

### 2.2. Parent container is not a shared KafkaConsumer

Each child consumer has its own client ID, poll loop, buffers, and assignment state. A rebalance or error on one child consumer does not mean all other consumers running in the same JVM share a single `KafkaConsumer` object.

The consumers still belong to the same group if they use the same group ID. The Kafka coordinator manages membership and partition assignment for that group.

## 3. Concurrency and partition assignment

Kafka distributes partitions within a consumer group such that at any given time, each partition is assigned to at most one consumer in the group. Multiple consumers can read the same topic concurrently if the topic has multiple partitions.

Suppose topic `orders.created` has six partitions and the listener has concurrency 3:

~~~text
Topic orders.created:
  P0  P1  P2  P3  P4  P5

Consumer group order-fulfillment:
  Consumer #1 -> P0, P1
  Consumer #2 -> P2, P3
  Consumer #3 -> P4, P5
~~~

Actual assignment depends on the partition assignor and group membership. The diagram illustrates one possible distribution.

If the topic has only two partitions but concurrency is four, at most two consumers can receive partitions in the group at that time:

~~~text
Topic orders.created:
  P0  P1

Consumer group:
  Consumer #1 -> P0
  Consumer #2 -> P1
  Consumer #3 -> no partition
  Consumer #4 -> no partition
~~~

Consumers without partitions may still be group members participating in polls/rebalances, but they contribute no additional record-processing capacity for that topic. Increasing concurrency beyond the partition count does not increase consumption throughput of a group.

### 3.1. Parallelism limit by partition

For a topic with P partitions and a consumer group with C consumers, the number of consumers that can read the topic simultaneously cannot exceed the number of partitions distributed to the group. In the simple case, maximum useful parallelism is approximately:

`min(P, C)`

If a listener subscribes to multiple topics, consider total partitions and assignments across the entire topic set. A consumer may receive partitions from multiple topics; distribution is not necessarily strictly even.

### 3.2. Multiple consumer groups are a different case

If two applications use two different group IDs, each group can receive all records of the topic. This is a fan-out mechanism for multiple independent systems to consume events, not a way to increase concurrency for the same work.

If the goal is to share the load of processing one event stream across instances, instances must join the same consumer group. If each instance has its own group ID, each instance reads a copy of the data stream according to Kafka semantics.

## 4. Configuring concurrency with Spring Boot

Spring Boot can configure default concurrency for listener containers created by the auto-configured factory.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      bootstrap-servers: localhost:9092
      group-id: order-fulfillment
      enable-auto-commit: false
    listener:
      concurrency: 3
      ack-mode: batch
~~~

With this configuration, the default listener container has concurrency 3. Each child consumer uses the consumer factory and corresponding group/consumer settings.

`ack-mode: batch` is the offset commit policy of the listener container. It is independent of concurrency: one property determines commit timing, while the other determines the number of child consumers managed.

If the application uses a custom container factory, verify that the factory is configured from Boot properties or sets concurrency itself. A manually created factory may not inherit all settings from the default factory.

## 5. Configuring with ConcurrentKafkaListenerContainerFactory

When a dedicated factory is needed for a stream, concurrency can be set on `ConcurrentKafkaListenerContainerFactory`:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.BATCH);

        return factory;
    }
}
~~~

Listener using this factory:

~~~java
@Service
public class OrderListener {

    private final FulfillmentService fulfillmentService;

    public OrderListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        id = "orders-fulfillment-listener",
        topics = "orders.created",
        groupId = "order-fulfillment",
        containerFactory = "orderKafkaListenerContainerFactory"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.process(event);
    }
}
~~~

When the container is initialized, the factory creates a concurrent container that manages three child consumers. If the topic has enough partitions, Kafka can distribute work among the three consumers.

### 5.1. Overriding concurrency on @KafkaListener

Spring Kafka allows specifying concurrency directly on the endpoint:

~~~java
@KafkaListener(
    id = "orders-fulfillment-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

The endpoint concurrency value can override the factory value. Configuration placeholders can be used to tune per environment:

~~~java
@KafkaListener(
    id = "orders-fulfillment-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "${orders.consumer.concurrency:3}"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

This way, the value can be placed in the configuration file:

~~~yaml
orders:
  consumer:
    concurrency: 3
~~~

Choose a single clear configuration source to avoid having factory and annotation set different values, which makes it difficult for operators to determine effective concurrency.

## 6. Configuring client ID for each consumer

When there are multiple consumers in the same application, distinct client IDs help identify metrics, logs, and connections for each consumer.

A prefix can be configured on the listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3",
    clientIdPrefix = "orders-fulfillment"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

With a concurrent container, Spring Kafka appends a distinguishing suffix for child consumers when needed, keeping client IDs unique. Illustrative example:

~~~text
orders-fulfillment-0
orders-fulfillment-1
orders-fulfillment-2
~~~

This prefix is useful when filtering metrics or logs by client ID. Avoid reusing the same prefix across unrelated listeners if monitoring tools need to distinguish individual endpoints.

## 7. Topic configuration and partition assignment

There are two common ways for a listener to receive partitions:

- Subscribe by topic and let the Kafka consumer group distribute partitions automatically.
- Explicitly assign partitions to the listener using `topicPartitions`.

### 7.1. Subscribe by topic

This is the usual approach when instances should join a group and have Kafka manage assignments:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

The Kafka group coordinator and partition assignor distribute topic partitions among member consumers. When consumers join or leave the group, assignments may change and trigger a rebalance.

### 7.2. Explicit partition assignment

If a listener needs to receive a specific set of partitions, `@TopicPartition` can be used:

~~~java
@KafkaListener(
    id = "priority-orders-listener",
    topicPartitions = @TopicPartition(
        topic = "orders.priority",
        partitions = {"0", "1", "2", "3"}
    ),
    concurrency = "2"
)
public void consumePriority(OrderCreated event) {
    fulfillmentService.processPriority(event);
}
~~~

With a concurrent container and explicit assignment, Spring Kafka distributes the specified partitions across child containers. When concurrency exceeds the number of specified partitions, concurrency is adjusted so it does not create more child consumers than partitions assignable in that configuration.

Manual assignment is useful when exact partition control is required, but the application must plan assignment updates when topology changes. Group subscription is usually more suitable when Kafka should balance partitions automatically across instances.

## 8. Relationship between concurrency, partitions, and instance count

Concurrency within a single JVM and the number of application replicas in a deployment jointly determine the total number of consumers.

Suppose:

- The topic has 12 partitions.
- Each pod runs one listener with concurrency 3.
- The deployment has 2 pods.
- All consumers use the same group ID.

Total consumers is six. Kafka can distribute 12 partitions across six consumers, averaging about two partitions per consumer.

~~~text
orders.created: 12 partitions

Pod A:
  Concurrent container
    Consumer A1
    Consumer A2
    Consumer A3

Pod B:
  Concurrent container
    Consumer B1
    Consumer B2
    Consumer B3

Consumer group order-fulfillment:
  6 consumers share 12 partitions
~~~

If scaling up to four pods with concurrency still 3, total consumers becomes 12. Then each consumer can receive one partition. If scaled further to six pods, total consumers becomes 18 while the topic still has only 12 partitions; at least six consumers will have no partitions.

Calculate total concurrency across the entire deployment:

`TotalConsumers = replicas × concurrencyPerReplica`

This is the number of consumers created, not the number guaranteed to have partitions. Useful parallelism is further bounded by partition count, broker speed, CPU, network, and downstream systems.

### 8.1. Choosing concurrency based on partitions

A starting point is not setting total consumers far beyond the workload's partition count. However, having one consumer per partition is not always necessary. If each record is CPU-intensive or downstream has connection limits, lower concurrency can be more stable.

Consider:

- Partition count and how partitions are distributed across brokers.
- Throughput and record size.
- Listener p95/p99 processing time.
- Application CPU, heap, and network capacity.
- Connection pools and throughput of downstream DB or APIs.
- Event freshness SLOs and acceptable consumer lag.

## 9. Threading and listener safety

Each child consumer runs its poll loop on its own thread. Therefore, the same listener bean can be invoked concurrently from multiple threads when concurrency is greater than one.

This affects how code is written:

- Do not store shared mutable state in listener fields without proper synchronization.
- Use stateless services or thread-safe designs.
- Ensure repositories and connection pools can handle parallel calls.
- Avoid sharing a non-thread-safe object across all consumers.
- Do not call `KafkaConsumer` directly from a thread other than the consumer's owning thread.

Example of a stateless listener:

~~~java
@Service
public class OrderListener {

    private final FulfillmentService fulfillmentService;

    public OrderListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment",
        concurrency = "3"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.process(event);
    }
}
~~~

If `FulfillmentService` holds an in-memory cache or mutable state, thread safety must be evaluated. A singleton Spring bean is shared among consumer threads by default.

### 9.1. Processing order

Kafka guarantees ordering within a partition. Within the same consumer group, a partition is assigned to only one consumer at a time, so concurrency does not cause multiple consumers in the group to read the same partition in parallel.

Different partitions can be processed concurrently. Therefore:

- Events with the same key usually land in the same partition if the partitioner and keys are stable.
- Events in the same partition preserve log order when processed synchronously along the poll loop.
- There is no global ordering across partitions.
- If the listener offloads processing to a thread pool or returns results asynchronously, the application must manage completion ordering and appropriate commit semantics itself.

If business logic requires ordering by order ID, use a stable key so events for the same order go to the same partition and avoid introducing asynchronous processing that breaks order unintentionally.

## 10. Interaction with AckMode and batch listeners

Concurrency determines the number of child consumers. `AckMode` determines when the container commits offsets. These two settings are independent but work together in operations.

With `AckMode.BATCH`, each child consumer commits offsets after the records from its own poll are processed. There is no shared batch across child consumers.

Example:

~~~text
Consumer #1:
  poll -> records P0, P1
  processing finished -> commit offsets of P0, P1

Consumer #2:
  poll -> records P2, P3
  processing finished -> commit offsets of P2, P3

Consumer #3:
  poll -> records P4, P5
  processing finished -> commit offsets of P4, P5
~~~

If using a batch listener, each child container can pass its poll's record batch to the listener. Batches from different consumers are still processed independently.

When one consumer encounters an error, that container's error handler handles retry/recovery as configured. Other child consumers can continue processing their assigned partitions. However, a rebalance or application-wide failure can affect multiple consumers; do not treat each child as a completely isolated service.

## 11. Rebalances when concurrency changes

A Kafka consumer group performs a rebalance when membership or subscriptions change, or when assignment conditions change. Common situations:

- A new pod starts and creates additional consumers.
- A pod is stopped or loses connectivity.
- A listener container is started or stopped.
- Concurrency changes alter the number of consumers in the group.
- Partitions are added to a topic or subscriptions change.

During a rebalance, partitions may be revoked from an old consumer and assigned to a new consumer. The application needs to complete in-flight processing according to container semantics, commit appropriate offsets, and avoid unsafe side effects when records are redelivered.

### 11.1. Impact on latency and throughput

Rebalances usually create a period where consumers are not processing normally. If the application scales continuously or consumers frequently leave the group, lag may increase even when overall CPU remains available.

Monitor:

- Rebalance rate and rebalance duration.
- Partition assignment per consumer.
- Consumer group state.
- Consumer lag before, during, and after rebalance.
- Record processing time and uncommitted record count.
- Heartbeat, session timeout, or poll interval errors.

Do not keep increasing concurrency solely because lag is rising. Lag may stem from slow downstream systems, hot partitions, broker bottlenecks, or repeated rebalances. Find the root cause before scaling.

### 11.2. Graceful shutdown

When the application stops, the parent container stops the child containers according to the Spring lifecycle. A controlled shutdown lets consumers leave the group, finish in-flight work within configured limits, and commit offsets according to the current policy.

In deployments, allow the application sufficient graceful shutdown time before the process is killed. Actual duration must align with listener processing time, retries, and orchestration termination grace periods.

If the process is killed abruptly, uncommitted records may be redelivered. Idempotent consumers remain necessary even when graceful shutdown is configured.

## 12. Pause, resume, and load management

A concurrent container provides consumption state control through the container API. You can look up the container by ID from `KafkaListenerEndpointRegistry`, then request pause or resume.

Example:

~~~java
@Service
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

When operating on a concurrent container, pause/resume is applied through the container managing the child consumers. Distinguish a pause request from the actual paused state; the Kafka consumer performs pause/resume on the consumer thread according to the container's mechanism.

Pause is useful when downstream is overloaded, maintenance is needed, or record intake rate needs control. However, pause does not delete records in Kafka and does not end the consumer group. Upon resume, consumers continue reading from the position matching the current offset.

If paused for too long, review timeouts and group health for your Kafka client version, especially if consumers stop polling. Use the container API instead of calling `KafkaConsumer` directly from application threads.

## 13. Configuring and operating multiple listeners

An application may have multiple listeners with different throughput targets. Each listener should have a clear ID, group ID, topic, and factory.

Example of two listeners:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void consumeOrder(OrderCreated event) {
    orderService.process(event);
}

@KafkaListener(
    id = "audit-listener",
    topics = "orders.audit",
    groupId = "audit-indexer",
    containerFactory = "auditKafkaListenerContainerFactory"
)
public void consumeAudit(OrderAudit event) {
    auditService.index(event);
}
~~~

The factory for each listener can set separate concurrency, `AckMode`, error handler, and batch mode. Do not use high concurrency for every stream just because one topic needs high throughput.

With multiple listeners, calculate total consumers per pod and total consumers across the deployment. For example, three listeners each with concurrency 4 create 12 consumers on one pod. That impacts connection count, threads, heap, CPU, and broker load.

## 14. Observing ConcurrentMessageListenerContainer

To operate concurrent containers, monitor both container state and Kafka consumer metrics.

| Observation group | Metrics or information |
|---|---|
| Container lifecycle | Running/stopped, start/stop events, pause state |
| Consumer identity | Group ID, client ID, member ID |
| Partition assignment | Partitions owned by each consumer |
| Throughput | Records/bytes consumed per consumer and topic |
| Lag | Lag by group, topic, and partition |
| Processing | Listener duration, batch duration, processing errors |
| Commit | Commit rate, commit latency, commit failures |
| Rebalance | Rebalance count, duration, and cause |
| Resource | Thread count, heap, GC, CPU, and connection pool |
| Downstream | DB pool saturation, API latency, timeouts, and retries |

Spring Kafka and the Kafka client can integrate with Micrometer to emit metrics, depending on version and configuration. Client ID suffixes help distinguish child consumers in dashboards. Verify the actual exported metrics and keep label cardinality under control.

### 14.1. Monitoring partition assignment

Aggregate group lag can hide a hot partition. Inspect lag by partition and client ID to determine:

- Whether one consumer receives disproportionately more partitions than others.
- Whether one partition has much higher traffic than the rest.
- Whether one consumer has abnormally high processing duration or error rate.
- Which consumers have no assignment because concurrency exceeds partition count.

If one partition is hot, increasing concurrency does not necessarily solve it because that partition is still assigned to only one consumer in the group. You may need to review key distribution or increase partitions after evaluating the impact on ordering and existing data.

## 15. Diagnosing common scenarios

| Symptom | Possible cause | Investigation direction |
|---|---|---|
| Increased concurrency without throughput gain | Low partition count, downstream bottleneck, or consumers receiving no partitions | Check assignment, partition count, DB/API latency |
| Many consumers in idle state | Concurrency exceeds assignable partition count | Compare total consumers with partition count |
| High lag on only one partition | Hot key or uneven key distribution | Inspect records/bytes by partition and key strategy |
| Continuous rebalances | Pod restarts, heartbeat/poll timeouts, or membership changes | Inspect lifecycle, logs, timeouts, and deployment events |
| DB connection pool exhausted | Listener concurrency exceeds DB capacity | Measure active connections, wait time, and downstream latency |
| Sharp heap increase | Too many consumers, large fetch buffers, or large batches | Inspect heap, fetch limits, `max.poll.records`, and concurrency |
| Duplicate record processing after scale/restart | Side effects ran before offset committed | Check `AckMode`, error handling, and idempotency |
| Wrong business event ordering | Events for same entity landed in multiple partitions or uncontrolled async processing | Check keys, partitioner, and listener execution model |
| Paused but records still processed briefly | Pause request waiting for consumer thread to apply or records already polled | Check pause state and handling of current poll |

When investigating, first identify the affected consumer group, topic, partition, and client ID. Correlate the timing of concurrency changes with rebalances, lag, and downstream latency. Avoid scaling consumers or increasing timeouts before identifying the cause.

## 16. Choosing concurrency for real workloads

A selection process can start as follows:

1. Record the partition count of the topics the listener subscribes to.
2. Measure records/bytes per second and load distribution by partition.
3. Measure p50/p95/p99 processing duration and downstream latency.
4. Choose initial concurrency aligned with partition count and pod resources.
5. Run representative load tests and observe assignment, lag, throughput, rebalances, and resources.
6. Increase concurrency incrementally if the consumer is the bottleneck and downstream still has capacity.
7. Stop increasing when throughput stops improving, partitions run out, or resources/downstream hit limits.
8. Recalculate total consumers when increasing pod count in deployment.
9. Document configuration, before/after metrics, and scaling limits in the runbook.

If higher throughput is needed when there is already one consumer per partition, you may need to increase partition count or optimize processing. Increasing partitions affects key mapping and event ordering; it is a topic design change that must be evaluated separately.

## 17. Common mistakes

**Assuming concurrency is an arbitrary listener thread count.** Each child consumer has its own `KafkaConsumer` and poll loop. Useful consumers are bounded by partition assignment.

**Increasing concurrency far beyond partition count.** Excess consumers create no additional parallel reading capacity while still consuming resources.

**Confusing multiple consumers in one group with multiple groups.** One group shares partitions to split work; multiple groups receive independent copies of data.

**Using a listener bean with mutable non-thread-safe state.** Multiple consumer threads can invoke the same singleton bean concurrently.

**Assuming a single partition can be processed in parallel by multiple consumers in the same group.** Kafka assigns a partition to only one consumer in a group at a time.

**Increasing concurrency to fix a hot partition.** A hot partition is still owned by one consumer. Review key distribution and partition design.

**Failing to calculate total deployment concurrency.** Consumer count equals concurrency per replica times replica count, before considering partition assignment.

**Calling KafkaConsumer directly from another thread.** `KafkaConsumer` is not thread-safe; use the container API to control pause/resume and lifecycle.

**Ignoring downstream capacity.** Faster consumers can overload the DB or API. Tune concurrency alongside connection pools and backpressure.

**Not observing rebalances.** Frequent scaling can prevent the group from stabilizing and cause lag to grow.

## 18. Comprehensive example: Order fulfillment

Suppose topic `orders.created` has 12 partitions. The Order Fulfillment application runs three pods, each configured with concurrency 2. All consumers use group ID `order-fulfillment`.

Total consumers created:

`3 pods × 2 consumers = 6 consumers`

Kafka distributes 12 partitions across six consumers. If load is relatively even, each consumer can receive about two partitions.

Spring Boot configuration:

~~~yaml
spring:
  kafka:
    consumer:
      bootstrap-servers: kafka:9092
      group-id: order-fulfillment
      enable-auto-commit: false
    listener:
      concurrency: 2
      ack-mode: batch

orders:
  consumer:
    max-poll-records: 100
~~~

Listener:

~~~java
@Service
public class OrderFulfillmentListener {

    private final FulfillmentService fulfillmentService;

    public OrderFulfillmentListener(
            FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        id = "orders-fulfillment",
        topics = "orders.created",
        groupId = "order-fulfillment",
        concurrency = "${spring.kafka.listener.concurrency:2}",
        clientIdPrefix = "orders-fulfillment"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.process(event);
    }
}
~~~

When order volume rises, operations monitors lag by partition, processing duration, and DB pool. If all consumers are busy, lag grows evenly, and DB still has capacity, increasing concurrency or pod count can be considered. If lag grows on only one partition, check key distribution and hot partitions. If the DB pool is already saturated, increasing concurrency can make the situation worse.

If scaled to six pods while concurrency remains 2, total consumers is 12, matching the partition count. This can be a reasonable scaling point if brokers and downstream keep up. If scaled further to eight pods, there will be 16 consumers for 12 partitions; at least four consumers will have no partitions in a simple assignment state.

This example shows that scaling decisions must be based on partitions, throughput, and actual processing capacity, not just application CPU.

## 19. Deployment and operations procedure

1. Identify the listener endpoint, group ID, topic subscription, and partition count.
2. Choose initial concurrency on the factory or on `@KafkaListener`.
3. Ensure each consumer has an identifiable client ID.
4. Verify the listener bean and downstream services can execute safely in parallel.
5. Set `AckMode`, error handler, retry, and batch mode to match business requirements.
6. Calculate total consumers across all pods and compare with partition count.
7. Deploy in a controlled manner and monitor rebalances while the group converges.
8. Measure lag per partition, throughput, processing duration, commits, resources, and downstream.
9. Use pause/resume via the container API when load control or maintenance is needed.
10. Verify graceful shutdown and safe replay when consumers restart.
11. Document concurrency limits, partition counts, and scaling actions in the runbook.

## 20. Key takeaways

`ConcurrentMessageListenerContainer` is the Spring Kafka container that manages multiple child `KafkaMessageListenerContainer` instances. Each child container manages one Kafka consumer and its own poll loop. Consumers typically join the same consumer group to share partitions.

Concurrency enables parallel processing across multiple partitions, but useful parallelism is bounded by partition count and downstream capacity. Listener beans can be invoked concurrently, so shared code and services must be thread-safe. When scaling, observe partition assignments, lag, rebalances, processing latency, resources, and side effects to keep the consumer group stable.

