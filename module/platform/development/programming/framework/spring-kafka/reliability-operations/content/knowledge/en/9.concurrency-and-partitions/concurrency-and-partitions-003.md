# Child Containers in a Concurrent Container

In Spring Kafka, a listener that needs to process multiple partitions in parallel can run using **ConcurrentMessageListenerContainer**. This container coordinates and creates multiple **child containers** of type **KafkaMessageListenerContainer**. Each child container manages its own Kafka consumer and handles polling, receiving records, invoking the listener, processing acknowledgments, and committing offsets as configured.

Understanding the relationship among the parent container, child containers, consumers, and partitions helps you configure concurrency deliberately. If you increase the child container count without accounting for partition count, application replicas, and downstream capacity, the system may create idle consumers or overload the database. Without understanding child container lifecycles, monitoring errors, pause/resume, and shutdown can also lead to confusing parent-level state with actual consumer-level behavior.

This article focuses on how **ConcurrentMessageListenerContainer** organizes child containers, how partitions are distributed, how to configure it in Spring Boot/Spring Kafka, and how to operate it when a child encounters an issue.

## 1. What Is ConcurrentMessageListenerContainer?

Spring Kafka has two primary listener containers to distinguish:

- **KafkaMessageListenerContainer**: manages a single Kafka consumer and executes the listener on that container's consumer thread.
- **ConcurrentMessageListenerContainer**: an orchestrating container that creates and manages multiple KafkaMessageListenerContainer instances to provide parallel consumption.

Therefore, the concurrent container is commonly viewed as the parent container; the KafkaMessageListenerContainer instances it creates are child containers.

~~~mermaid
flowchart TD
    P["ConcurrentMessageListenerContainer<br/>parent"]
    P --> C0["KafkaMessageListenerContainer<br/>child 0"]
    P --> C1["KafkaMessageListenerContainer<br/>child 1"]
    P --> C2["KafkaMessageListenerContainer<br/>child 2"]
    C0 --> K0["KafkaConsumer 0"]
    C1 --> K1["KafkaConsumer 1"]
    C2 --> K2["KafkaConsumer 2"]
    K0 --> A0["Assigned partitions"]
    K1 --> A1["Assigned partitions"]
    K2 --> A2["Assigned partitions"]
~~~

The parent container does not poll records itself like a standalone consumer. It manages the lifecycle and the collection of child containers. Each child has its own consumer, its own thread, and its own assignment according to the subscription or assignment mechanism in use.

For example, when concurrency is configured to 3, a ConcurrentMessageListenerContainer typically creates three child KafkaMessageListenerContainer instances. Each child has one Kafka consumer. The Kafka group coordinator distributes partitions among those consumers if the listener uses group subscription.

### 1.1 Why Are Child Containers Needed?

A Kafka consumer is not designed for a single consumer instance to process multiple partitions concurrently across multiple threads by calling poll from multiple threads. A consumer has an explicit lifecycle and thread ownership model. To increase parallel processing capacity, applications typically create multiple consumer instances within the same consumer group.

Spring Kafka provides ConcurrentMessageListenerContainer to manage creating those consumer instances. Developers only configure concurrency on the factory or listener; the framework creates and manages the child containers.

Benefits:

- Allows processing multiple partitions in parallel within a single application instance.
- Each child has its own consumer and consumer thread.
- The parent manages starting, stopping, and the lifecycle of the children.
- Container state can be observed at both parent and child levels.
- Listener configuration keeps a single business method without manually creating threads or KafkaConsumer instances.

### 1.2 A Child Container Is Not a Partition

One child container manages one consumer. That consumer may be assigned zero, one, or multiple partitions.

For example, a topic has six partitions and concurrency is three:

- Child 0 may receive partitions 0 and 1.
- Child 1 may receive partitions 2 and 3.
- Child 2 may receive partitions 4 and 5.

This is only an illustrative example. Actual assignment depends on the partition assignor, other members in the group, subscriptions, and rebalance state. Do not assume child 0 always receives partition 0 or that assignment is always strictly balanced.

If concurrency exceeds the number of assignable partitions in the group, some children will not receive partitions and will not process records until the assignment changes.

## 2. Relationship Among Parent, Child, Consumer Thread, and Listener

A typical structure in Spring Kafka:

| Component | Responsibility |
|---|---|
| ConcurrentMessageListenerContainer | Parent; manages the list of child containers and overall lifecycle |
| KafkaMessageListenerContainer | Child; manages a single consumer and its poll loop |
| KafkaConsumer | Performs poll, manages subscription/assignment, heartbeats, and offset protocol |
| Consumer thread | Thread owning the consumer, polling records, and invoking the listener per the container model |
| Listener method | Processes a record or batch received by the child consumer |
| Partition assignment | Set of partitions assigned to a single consumer in the group |

When a child container polls records, the listener is invoked according to the record listener or batch listener configuration. In the standard model, listener invocation runs on that child's consumer thread. Thus, the parent's concurrency produces multiple parallel listener execution threads.

### 2.1 One Child Has One Consumer

In the standard concurrent container structure, each child KafkaMessageListenerContainer manages one Kafka consumer. This consumer is not shared with other children.

This is an important boundary during investigations:

- One child stopping does not mean every child has stopped.
- A failing consumer can leave the group and cause partitions to be reassigned to another child.
- A slow listener on one child can slow down the partitions assigned to that specific consumer.
- The parent may still report a running state while one child is restarting or failing, depending on lifecycle state and error handling.

### 2.2 The Listener Bean Can Be Invoked Concurrently

A Spring component is typically a singleton. When multiple child containers invoke the same listener method, invocations can happen concurrently on multiple threads.

Example:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        topics = "orders",
        groupId = "orders-projection-prod",
        concurrency = "3"
    )
    public void handle(OrderCreated event) {
        projectionService.apply(event);
    }
}
~~~

Three child containers can call handle() concurrently. If the listener holds mutable state in a field, thread safety must be ensured. Do not store a shared temporary variable across invocations without synchronization or an immutable design.

Singleton dependencies such as services, repositories, and HTTP clients must also be safe under concurrent invocation. Being a Spring singleton bean does not automatically make every method thread-safe.

### 2.3 Consumer Threads and Asynchronous Tasks

If a listener hands work off to an executor and returns immediately, the container may treat the listener as completed under the current ack mode while the async task is still running. If the offset is committed before the task finishes, process termination can lose application-level work.

If asynchronous processing is desired, acknowledgments and offset commits must be tied to actual completion results. You must also control ordering, backpressure, in-flight task count, and retryability. Do not simply add CompletableFuture or @Async and assume the Kafka container will wait for the task to finish.

## 3. Configuring Concurrency and Child Container Count

Concurrency is the number of child containers that ConcurrentMessageListenerContainer creates for a listener container. It can be configured on the factory or directly on @KafkaListener.

### 3.1 Configuring on the Listener Annotation

Example:

~~~java
@KafkaListener(
    id = "ordersProjection",
    topics = "orders",
    groupId = "orders-projection-prod",
    concurrency = "3"
)
public void handle(OrderCreated event) {
    projectionService.apply(event);
}
~~~

With this configuration, the concurrent listener container has a concurrency of 3. The parent manages three child KafkaMessageListenerContainer instances. Each child has its own consumer.

The concurrency value in the annotation is a string because the annotation attribute can accept placeholders or SpEL in supported Spring Kafka versions. Environment-specific values can be used, but verify the resolved runtime value after placeholders are evaluated.

### 3.2 Configuring on ConcurrentKafkaListenerContainerFactory

A default concurrency can be set for listeners using a factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
        new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    return factory;
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-projection-prod",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void handle(OrderCreated event) {
    projectionService.apply(event);
}
~~~

If the annotation specifies a concurrency attribute, the annotation value can override the factory's concurrency for that listener. Choose one primary configuration source so operators do not read 3 in the factory while the listener actually runs with a different concurrency.

### 3.3 Configuring via Spring Boot

For the default factory auto-configured by Spring Boot, default concurrency can be set via listener properties in supported Spring Boot versions:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
    consumer:
      group-id: orders-projection-prod
      enable-auto-commit: false
~~~

If the application defines its own ConcurrentKafkaListenerContainerFactory, configure concurrency on the corresponding custom factory. Do not assume default factory properties automatically apply to custom-declared factories.

### 3.4 Choosing Concurrency Based on Partitions

Suppose a topic has eight partitions. One application instance runs with concurrency four. In a group containing only that instance, up to four child consumers are active, each potentially receiving roughly two partitions.

If concurrency is ten, at most eight consumers can receive partitions from this topic; the remaining two children sit idle if no other partitions are subscribed.

Distinguish between two numbers:

- **Child count**: the number of child containers created by the parent.
- **Active consumer count**: the number of consumers that actually hold assignments and are processing partitions.

These two numbers do not necessarily match.

## 4. Calculating Concurrency Across the Entire Deployment

When an application has multiple pods, the number of child containers created per pod must be calculated together with the replica count.

Basic formula:

~~~text
Total child containers = application instances × concurrency per instance
~~~

For example, a deployment has three pods, each configured with concurrency four:

~~~text
3 pods × 4 child containers = 12 consumer instances
~~~

If all share the same group id and subscribe to an eight-partition topic, the group has at most eight consumers assigned partitions from that topic. The remaining four consumers may remain idle for this topic.

| Pod count | Concurrency per pod | Total consumers | Partition count | Consumers able to receive partitions |
|---:|---:|---:|---:|---:|
| 1 | 4 | 4 | 8 | Up to 4 |
| 2 | 4 | 8 | 8 | Up to 8 |
| 3 | 4 | 12 | 8 | Up to 8 |
| 4 | 2 | 8 | 16 | Up to 8 |
| 4 | 4 | 16 | 16 | Up to 16 |

This table assumes all consumers belong to the same group and considers a single topic with the partition count listed in the table. If a listener subscribes to multiple topics, assignment depends on the full set of subscribed partitions.

### 4.1 Do Not Increase Concurrency Without Limit

Increasing concurrency can increase parallelism, but simultaneously increases:

- Number of Kafka consumers and broker connections.
- Number of consumer threads and memory usage.
- Number of poll requests and heartbeats.
- Number of concurrent listener invocations.
- Number of connections or requests to databases/downstream services.
- Pressure on CPU, heap, connection pools, and thread pools.

If downstream can only sustain 20 concurrent requests, increasing from 4 to 30 children can overload downstream systems. Consumer lag can grow even further due to listener timeouts, retries, and connection pool saturation.

Identify bottlenecks before raising concurrency. If the database is the limit, throttle parallelism or optimize queries; adding child containers will not make the database process faster.

### 4.2 Multiple Listeners with Separate Concurrency

An application can have multiple @KafkaListeners with different topics and workloads. Each listener has its own container and can have a different concurrency.

Example:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "orders-service-prod",
    concurrency = "4"
)
public void handleOrder(OrderCreated event) {
    orderService.process(event);
}

@KafkaListener(
    id = "notificationsListener",
    topics = "notifications",
    groupId = "notification-service-prod",
    concurrency = "2"
)
public void handleNotification(NotificationRequested event) {
    notificationService.send(event);
}
~~~

The two listeners total six child containers per application instance. If the application runs three pods, there can be 18 child consumer instances. However, two different group ids create two independent subscriptions and each group has its own assignment.

Do not simply add up all concurrencies in one service and compare against one topic's partition count. Calculate per logical consumer group and across all topics that the listener subscribes to.

## 5. How Partitions Are Distributed Among Child Containers

With group subscription, each child container joins the group as a consumer member. The Kafka group coordinator and partition assignor decide which partition belongs to which consumer.

Example of the orders topic with six partitions and concurrency three:

| Child container | Consumer member | Example assignment |
|---|---|---|
| Child 0 | Consumer 0 | orders-0, orders-1 |
| Child 1 | Consumer 1 | orders-2, orders-3 |
| Child 2 | Consumer 2 | orders-4, orders-5 |

Assignments can vary depending on the assignor, member count, and other topics. A consumer can receive multiple partitions; a single partition is not assigned to two consumers in the same group at the same time.

### 5.1 Assignment Depends on the Partition Assignor

Kafka provides partition assignors with different distribution strategies, such as RangeAssignor, RoundRobinAssignor, and CooperativeStickyAssignor. The distribution strategy can affect how many partitions each child receives and how extensively assignments change when members join or leave the group.

Spring Kafka creates consumers as configured; assignor selection is done through consumer properties. A concurrent container does not automatically guarantee load-balanced assignment by business volume. One partition with high record volume can create a bottleneck even if every child has the same number of partitions.

### 5.2 Rebalancing When a Child Joins or Leaves the Group

When a child container starts, stops, or loses connectivity, group membership changes. Kafka can perform a rebalance to redistribute partitions.

Scenarios:

- Scaling concurrency from 2 to 4: adds consumer members; the group may rebalance.
- Restarting the application: child consumers leave and rejoin the group.
- One child fails: its partitions may be reassigned to remaining members.
- Rolling deployment: old and new pods coexist in the group during rollout.
- Changing subscription or partition count: assignments may change.

Rebalances can pause processing on some partitions. If the listener has not committed offsets yet, records can be redelivered. Therefore, increasing concurrency while the system is already processing slowly can temporarily increase lag before stabilizing.

### 5.3 A Child Without Partitions Still Exists

If child count exceeds partition count, excess children may still be created and remain in a running lifecycle state, yet receive no assignment. This is not a container creation error. It simply means the consumer currently has no partitions to process.

Monitoring child container count alone is insufficient to know actual processing capacity. Observe consumer assignments, assigned partition counts, and record processing rates.

## 6. Explicit Partition Assignment and Child Containers

Besides group subscription, Spring Kafka allows specifying exact partitions via @TopicPartition or TopicPartitionOffset. In this case, partition distribution differs from standard group subscription.

Example:

~~~java
@KafkaListener(
    id = "priorityOrders",
    groupId = "priority-orders-worker",
    topicPartitions = {
        @TopicPartition(
            topic = "orders",
            partitions = {"0", "1", "2", "3"}
        )
    },
    concurrency = "2"
)
public void handle(OrderCreated event) {
    priorityOrderService.process(event);
}
~~~

With explicit partition assignment, Spring Kafka can distribute the declared partitions across child containers in the concurrent container. If concurrency exceeds the number of declared partitions, concurrency may be reduced so redundant children are not created for static assignments according to the framework version's behavior.

Distinguish between:

- **Group subscription**: consumers subscribe to topics; the Kafka group coordinator distributes partitions.
- **Manual assignment**: the application assigns partitions to consumers; consumers manage their own assignments and do not participate in group coordination to divide partitions as in standard subscription.

With manual assignment, if multiple application instances declare the exact same set of partitions, those instances can independently read those same partitions. This can produce duplicate processing. Do not deploy the same manual assignment across multiple replicas without a mechanism for unique partition partitioning and ownership coordination.

### 6.1 When to Use Explicit Assignment

Explicit assignment can be useful when:

- The application must assign specific partitions to workers according to a managed topology.
- A single partition or group of partitions needs isolation.
- A system has an ownership distribution mechanism external to Kafka.
- Specific initial offsets or per-partition seeks must be configured.

However, explicit assignment puts greater responsibility on the application for ownership, rebalancing, scaling, and failover. For most consumer services requiring automatic replica scaling, group subscription is simpler and safer.

### 6.2 Initial Offsets via TopicPartitionOffset

Spring Kafka supports declaring partitions and initial offsets through TopicPartitionOffset. Understand the offset type being used: absolute offset, relative offset, or timestamp-based offset depending on the API and version.

Do not treat annotation initial offsets as a mechanism that continuously resets offsets on every child restart. Initial offsets primarily apply when establishing the assignment; committed offsets and consumer lifecycle still influence where consumption resumes. When intentional replay is needed, use an explicit reset/seek procedure and verify group state.

## 7. Lifecycle of Parent and Child Containers

The parent ConcurrentMessageListenerContainer manages the set of child containers. When the parent starts, it creates or starts children according to concurrency. When the parent stops, it coordinates stopping children and waits for consumers to close according to the container lifecycle.

### 7.1 Start

When the application context starts or a listener endpoint is registered:

1. Spring creates the listener container from the factory.
2. If the endpoint requires a concurrent container, the parent is created.
3. The parent determines concurrency.
4. The parent creates the child KafkaMessageListenerContainer instances.
5. Each child initializes a Kafka consumer and joins the group or applies its assignment.
6. The consumer polls and the listener begins receiving records once partitions are assigned.

Specific steps can vary with lifecycle and lazy startup configuration, but the parent-manages-children model remains the key point to remember.

### 7.2 Stop and Shutdown

When the parent stops, child containers stop according to the container lifecycle. Consumers must finish or cancel work according to shutdown timeout and ack mode. If a listener is processing a long-running record, shutdown duration may extend or the container may have to terminate at timeout.

Recommendations:

- Bound listener processing duration.
- Configure shutdown timeout to align with processing and commit duration.
- Use the deployment platform's graceful shutdown.
- Avoid force termination during normal operations.
- Verify committed offsets and which records may be redelivered after restart.

If the process stops before offsets are committed, records can be reprocessed. This is standard at-least-once behavior and requires idempotent business processing.

### 7.3 Child Restarts and Parent State

A child can encounter errors and be handled by container lifecycle/error handling depending on exception type, container configuration, and Spring Kafka version. The parent manages the children, but do not assume a parent state of running means every child is healthy.

During investigation, inspect the state of each child:

- Which children are running?
- Which children are stopping or restarting?
- Which consumer members hold assignments?
- Which child has listener errors or poll gaps?
- Which partitions are affected?

Looking only at an aggregate parent health indicator can miss a child that is not processing records.

## 8. Observing Child Containers and Consumers

Spring Kafka provides APIs and events to observe containers. Method and event names may vary across versions; use the exact API of your deployed version.

### 8.1 Retrieving Child Containers from the Parent

ConcurrentMessageListenerContainer provides access to its child container list through APIs such as **getContainers()**.

Illustrative example:

~~~java
@Component
public class ListenerContainerInspector {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerContainerInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void printChildren() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersProjection");

        if (container instanceof ConcurrentMessageListenerContainer<?, ?> concurrent) {
            for (MessageListenerContainer child :
                    concurrent.getContainers()) {
                log.info(
                    "childId={}, running={}",
                    child.getListenerId(),
                    child.isRunning()
                );
            }
        }
    }
}
~~~

This is an illustrative example; generic types and API visibility may need adjustment depending on the Spring Kafka version. KafkaListenerEndpointRegistry manages listener containers created by endpoint annotations. Explicitly declared container beans may need to be accessed by bean name or a separate management mechanism.

Do not invoke child lifecycle methods arbitrarily from multiple places. Starting/stopping children should follow a clear coordination flow to avoid unintended assignments and ownership states.

### 8.2 Container Events

Spring Kafka emits container events such as events when a container starts, stops, becomes idle, when a consumer fails, or when partition assignments change depending on the version. Application event listeners can be used to record lifecycle changes.

Conceptual example:

~~~java
@Component
public class KafkaContainerEvents {

    @EventListener
    public void onContainerEvent(ConsumerStoppedEvent event) {
        log.warn(
            "Kafka consumer stopped: listenerId={}",
            event.getContainer()
        );
    }
}
~~~

This event example only illustrates the concept; verify event names, accessors, and packages in the Spring Kafka version in use. Event publishers can be configured to emit events from child containers, not just the parent.

### 8.3 Client IDs and Metrics

Each child has its own consumer client. Spring Kafka can append a suffix to the client id prefix to distinguish consumers created by a concurrent container. This helps broker/client metrics and logs identify individual consumers.

Example client ids look like:

~~~text
orders-projection-0
orders-projection-1
orders-projection-2
~~~

Exact suffix formatting depends on the client id prefix and framework version. Do not rely on the suffix number as a partition id. The suffix identifies a consumer instance, whereas partition assignment is managed separately by Kafka.

Monitor:

- Consumer client id.
- Assigned partitions per child.
- Poll rate and processing duration.
- Commit latency and commit failures.
- Rebalance count.
- Listener error rate.
- Consumer lag by group/topic/partition.
- Running child count compared to desired concurrency.

## 9. Thread Safety and Resource Sharing Across Child Containers

Child containers run concurrently, typically invoking the same listener bean. This is a common source of bugs when moving from concurrency 1 to multiple children.

### 9.1 Avoid Shared Mutable State

Unsafe example:

~~~java
@Component
public class CounterListener {

    private long processedCount;

    @KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        concurrency = "4"
    )
    public void handle(OrderCreated event) {
        processedCount++;
    }
}
~~~

processedCount++ is not an atomic operation. Multiple child threads can update it concurrently and lose increments. If metrics are needed, use a Micrometer counter or an appropriate thread-safe structure.

Do not store the current ConsumerRecord, current correlation id, or mutable request context in a singleton field shared across invocations.

### 9.2 Database Connection Pools

Concurrency increases the number of concurrent listener invocations. If each invocation opens a database transaction or calls a repository, the connection pool must have enough capacity for the actual total load.

For example, three pods with concurrency 5 each can produce up to 15 concurrent listener invocations for this group. If each invocation needs a connection and the shared pool has only 10 connections across the system, some invocations will wait. If waiting exceeds the poll interval or timeouts, consumers may rebalance or retry.

Balance:

- Children per pod.
- Pod count.
- Partition count and per-partition load.
- Database connection pool size.
- Downstream request limits.
- Average and p95/p99 processing time.

### 9.3 Thread Pools and Async Processing

If the listener uses another executor, the total number of execution threads can exceed the child container count. The consumer thread may continue polling while prior tasks have not finished if the code does not coordinate carefully. This affects ordering, acknowledgments, and backpressure.

If an async listener pattern is needed, use mechanisms supported by Spring Kafka in the relevant version and understand the ack semantics. Do not build an unbounded queue from the consumer thread to an executor; the queue can grow without limit when downstream slows down.

### 9.4 Partition-Level Ordering

Kafka guarantees record ordering within a partition. With group subscription, one partition is assigned to one consumer member at a time. Therefore, increasing child containers does not cause the same partition to be processed concurrently in parallel while keeping default ordering.

If records with the same business key must maintain order, ensure they are routed to the same partition using an appropriate key. A consumer can process multiple partitions in parallel, while records within a single partition still must be processed according to ordering requirements.

If the listener submits async tasks that finish out of order, the application can break business ordering even though Kafka delivered records in order. Design sequencing or acknowledge offsets only after preceding side effects complete.

## 10. Error Handling at the Child Container Level

Each child receives a subset of partition assignments and invokes the listener on its own consumer thread. A listener error can affect the partitions assigned to that child according to the error handler and retry policy.

Issues to watch for:

- A poison record causing a child to retry continuously.
- Long-running listener processing preventing the consumer from polling in time.
- A downstream outage impacting multiple children simultaneously.
- One child stopping and triggering partition reassignment.
- DLT publishing failure leaving recovery incomplete.

Error handlers are typically configured on ConcurrentKafkaListenerContainerFactory and applied to child containers created from that factory. Depending on configuration, an exception can retry on the child, roll back a transaction, or route the record to a DLT.

### 10.1 Retries Can Hold Up Partitions on a Child

With blocking retries, a child can spend time retrying a single record. Subsequent records on the same partition cannot bypass the record being retried under partition-ordered processing.

If a child owns multiple partitions, a failing record can affect poll timing and progress on other partitions assigned to the same consumer. Therefore, inspect the child's assignment when investigating a stuck partition.

### 10.2 DLT and Child Containers

When using a Dead Letter Topic, a failing record can be published to the DLT after the configured number of attempts. After successful recovery and offset commit per the error handling policy, the child can continue to subsequent records.

A DLT is not infinite default storage. Configure retention, replication, ACLs, monitoring, and a replay procedure. If DLT publishing fails, do not treat the record as handled.

### 10.3 One Failing Child Does Not Automatically Mean Restarting the Whole Application

If only one child fails, determine whether the error lies in the consumer, broker, listener, or dependency. Restarting the container or restoring the dependency may be necessary, whereas restarting the entire application can trigger rebalances across all children and cause wider disruption.

Prefer scoping the failure via child id, client id, partition assignment, and root exception before choosing an action.

## 11. Scaling Concurrency and Runtime Changes

Some Spring Kafka versions allow adjusting the concurrency of a concurrent listener container at runtime through container APIs. Check your version and lifecycle APIs before using this.

Changing concurrency may cause the parent to stop or recreate part of the child containers and trigger a group rebalance. This is not a free operation.

When increasing concurrency:

1. Check partition count and active consumer count.
2. Check broker and downstream capacity.
3. Increase concurrency in small increments.
4. Monitor rebalances, lag, and processing rate.
5. Verify new children receive assignments.
6. Stop increasing once throughput stops improving or downstream saturation rises.

When decreasing concurrency:

1. Assess how many partitions remain assigned to the remaining members.
2. Stop children following the container lifecycle.
3. Monitor rebalances and offset commits.
4. Confirm remaining consumers have sufficient capacity.
5. Check lag after assignments stabilize.

If concurrency changes via deployment config, rolling deployments can cause group member counts to fluctuate. Account for the window when old and new pods coexist.

## 12. Common Scenarios and Troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| Parent running but no records | Children have no assignment, wrong group id, empty topic, or LSO/read policy | Check individual child state, group membership, assignments, and topic |
| Children running but some children idle | Concurrency exceeds assigned partition count | Compare active consumer count with partition count |
| One partition has high lag | Skewed partition load, poison record, or slow child | Check which child owns the partition, listener latency, and retries |
| Increased concurrency but throughput unchanged | Partition count limit, downstream bottleneck, or CPU saturation | Check assignments, database pool, processing rate, and CPU |
| Restarting one child causes rebalance | Consumer member left the group | Inspect rebalance events, committed offsets, and new assignments |
| Concurrent listener invocations cause race conditions | Listener bean has non-thread-safe mutable state | Inspect shared fields, caches, and dependencies |
| Multiple pods process the same record | Different group ids or overlapping manual assignments | Verify group id and assignment mode |
| Prolonged shutdown | Listener processing takes too long or async tasks have not finished | Check processing duration, shutdown timeout, and executor queues |
| DLT growing rapidly | Poison messages or widespread downstream errors | Categorize exceptions, retry counts, and dependency health |

A single symptom is not enough to conclude root cause. For example, an idle child can be completely normal if child count exceeds partition count. Conversely, a running parent where all children lack assignments may indicate a misconfigured group or subscription.

## 13. Procedure for Investigating a Child Container Not Processing Records

When a concurrent listener is not processing records as expected:

1. Identify the listener id and ConcurrentMessageListenerContainer name.
2. Read the concurrency configured on the factory and annotation; confirm the runtime value.
3. List child containers and each child's running/stopped state.
4. Identify the consumer client id corresponding to each child.
5. Inspect group id, member count, and partition assignments in Kafka.
6. Identify which partitions have no consumer or are building lag.
7. Check poll rate, listener processing duration, error handler, and retries.
8. Correlate database/downstream latency, pool saturation, and thread states.
9. Check rebalance events, consumer restarts, and commit failures.
10. After resolving the cause, verify children hold assignments, offsets advance, and business side effects complete.

If a parent has concurrency 4 with only three partitions, one idle child may be expected. If all four children have no assignments, check group id, topic subscription, ACLs, and group state.

## 14. Testing Parent-Child Structure and Concurrency

Test in an integration environment using a topic with a known partition count.

### 14.1 Verify Child Count

- Configure concurrency to 3.
- Start the listener.
- Confirm the parent is a ConcurrentMessageListenerContainer.
- Confirm the parent manages three child KafkaMessageListenerContainer instances.
- Confirm each child has its own consumer client.

### 14.2 Verify Partition Assignment

- Create a topic with six partitions.
- Run one application instance with concurrency 3.
- Confirm three children join the same group.
- Confirm partitions are distributed across consumers.
- Increase concurrency to 8 and confirm the number of consumers holding assignments does not exceed the topic's partition count in the group.

### 14.3 Verify Multiple Replicas

- Run two pods, each with concurrency 3.
- Confirm total consumer members are approximately six for the group when both pods stabilize.
- Confirm group id matches across pods.
- Confirm partitions are divided across the entire group rather than each pod receiving the full stream.
- Restart one pod and confirm partitions are reassigned.

### 14.4 Verify Thread Safety

- Send multiple records with different keys.
- Record listener thread names and child/client ids.
- Confirm invocations can run concurrently.
- Check shared state, database pools, and downstream concurrency.
- Confirm per-partition/key ordering is preserved as designed.

### 14.5 Verify Errors and Shutdown

- Produce a failing record to verify retries/DLT on a child.
- Stop one child or one pod in the test environment.
- Confirm partitions are reassigned and uncommitted records are safely reprocessed.
- Test graceful shutdown while the listener is processing.
- Confirm both parent and children stop according to the expected lifecycle.

## 15. Design and Operations Checklist

**Container structure**

- [ ] Listener uses ConcurrentMessageListenerContainer when concurrency is needed.
- [ ] Parent manages the expected number of child containers.
- [ ] Each child has its own consumer and consumer thread.
- [ ] Created child count is distinguished from consumers holding partition assignments.
- [ ] It is clear whether the listener uses group subscription or explicit assignment.

**Concurrency and partitions**

- [ ] Total consumers calculated as pod count multiplied by concurrency per pod.
- [ ] Concurrency compared against partition count for each group.
- [ ] Concurrency is not increased when downstream is already overloaded.
- [ ] Assignments are observed by partition and child/client id.
- [ ] Replicas sharing a logical subscription use the same group id.

**Code and resources**

- [ ] Singleton listener is safe under concurrent invocation.
- [ ] Shared state, caches, and metrics use thread-safe mechanisms.
- [ ] Database and HTTP pools have capacity for expected concurrency.
- [ ] Async processing has explicit acknowledgment and backpressure handling.
- [ ] Business ordering per partition/key is preserved.

**Lifecycle and recovery**

- [ ] Parent and children have graceful start/stop.
- [ ] Child state, assignments, and rebalances are monitored.
- [ ] Bounded retries and a DLT are operated.
- [ ] A failing child is isolated before restarting the whole application.
- [ ] Scaling, pod restarts, idle children, and shutdown have been tested in an appropriate environment.

ConcurrentMessageListenerContainer is Spring Kafka's concurrency management layer. The parent creates and coordinates child KafkaMessageListenerContainer instances; each child manages its own consumer to poll and process assigned partitions. When configuring child count, account for application replicas, partition count, assignment mode, and downstream capacity. When investigating incidents, trace from parent down to child, consumer, partition, and listener to pinpoint the exact affected scope.

