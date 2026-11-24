# Creating Listener Containers Programmatically

Spring Kafka typically creates listener containers from methods annotated with `@KafkaListener`. However, some systems only know which topics to consume at runtime: when a new tenant is activated, a subscription configuration is updated, or a data stream is opened only for a limited window. In these cases, the application can create and manage listener containers directly in code.

The common approach is to use `ConcurrentKafkaListenerContainerFactory` to create a `ConcurrentMessageListenerContainer`, configure the topic, group ID, listener, and container properties, and then call `start()`. When the container is no longer needed, the application calls `stop()` and releases it. Creating dynamic containers also means the application takes responsibility for lifecycle management, identification, resource limits, and handling errors during startup or shutdown.

This lesson belongs to the **Dynamic containers** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how to create listener containers programmatically, distinguish topic-based subscription from explicit partition assignment, and safely manage dynamic containers in Spring Kafka.

## Learning Outcomes

After this lesson, you will be able to:

- Explain the role of the listener container and container factory.
- Create a `ConcurrentMessageListenerContainer` using `createContainer()`.
- Configure `ContainerProperties`, group ID, AckMode, and the message listener.
- Create a container with topic-based subscription or explicit partition assignment.
- Enable concurrency appropriate for the partition count and processing capacity.
- Start, stop, and manage container lifecycle while the application is running.
- Distinguish directly created containers from containers managed by `KafkaListenerEndpointRegistry`.
- Understand offsets, group membership, and rebalances when adding or removing containers.
- Avoid duplicate container creation, thread leaks, and connection leaks.
- Test dynamic start/stop, assignment, and shutdown handling.

## 1. Where Are Listener Containers Created From?

With `@KafkaListener`, Spring processes the annotation into a listener endpoint and creates a container to poll records and invoke the listener. The container factory provides the `ConsumerFactory` along with shared configuration such as concurrency, error handler, converter, and container properties.

~~~mermaid
flowchart TD
    A["@KafkaListener endpoint"] --> B["KafkaListenerContainerFactory"]
    B --> C["Listener container"]
    C --> D["KafkaConsumer"]
    D --> E["Poll records"]
    E --> F["Invoke listener"]
~~~

When creating a container programmatically, the application proactively calls the factory instead of waiting for Spring to process annotations. The factory still lets you reuse consumer configuration and already-declared container settings.

You can use this approach when:

- The topics to subscribe to depend on runtime configuration.
- A new tenant or customer is activated.
- A consumer needs to be opened/closed based on a workflow's state.
- The application manages multiple subscription streams with independent lifecycles.
- You want to assign a specific set of partitions to a container.

You should not create dynamic containers just to replace a simple static listener. Each additional container can create consumers, threads, broker connections, and group coordination overhead.

## 2. Creating a Container from ConcurrentKafkaListenerContainerFactory

`ConcurrentKafkaListenerContainerFactory` can create a container from a list of topics. For example:

~~~java
ConcurrentMessageListenerContainer<String, OrderCreatedEvent> container =
        factory.createContainer("orders.created");
~~~

The container is created, though it does not necessarily begin polling immediately. The application needs to configure the listener and required properties before calling `start()`.

The factory is typically configured as a Spring bean to share the `ConsumerFactory` and processing policies:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
dynamicOrderFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
        CommonErrorHandler commonErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(commonErrorHandler);
    factory.setConcurrency(2);

    return factory;
}
~~~

The factory serves as the central place for shared configuration. Each container created from the factory can receive additional per-container configuration before starting.

Factory APIs and options may vary across Spring Kafka versions. Make sure to use the exact dependency version in your project.

## 3. Configuring ContainerProperties

A container has properties that control subscription, group, acknowledgment, and the listener callback. Common settings to review include:

| Property | Role |
|---|---|
| `groupId` | The container's consumer group when subscribing to topics. |
| `ackMode` | How the container acknowledges offsets. |
| `messageListener` | Callback that receives a record or batch of records. |
| `pollTimeout` | Wait duration during poll. |
| `clientId` | Client identifier for observability and distinguishing consumers. |
| `shutdownTimeout` | Wait duration when the container stops. |

Example configuration before starting:

~~~java
ConcurrentMessageListenerContainer<String, OrderCreatedEvent> container =
        factory.createContainer("orders.created");

ContainerProperties properties = container.getContainerProperties();

properties.setGroupId("orders-dynamic-fulfillment");
properties.setAckMode(ContainerProperties.AckMode.RECORD);
properties.setPollTimeout(2_000L);
~~~

If the `ConsumerFactory` already has a group ID, configuring the group ID on `ContainerProperties` can be used to override it for a specific container. Always verify the effective group ID to avoid multiple containers accidentally joining the same group unintentionally.

## 4. Attaching a MessageListener Programmatically

When creating a container directly, the application can attach an implementation of `MessageListener<K, V>`. The listener receives a `ConsumerRecord` and processes the payload along with its metadata.

~~~java
properties.setMessageListener(
        (MessageListener<String, OrderCreatedEvent>) record -> {
            orderService.handle(record.value());

            log.info(
                    "Handled topic={}, partition={}, offset={}",
                    record.topic(),
                    record.partition(),
                    record.offset()
            );
        }
);
~~~

After configuring the listener, start the container:

~~~java
container.start();
~~~

Unlike a `@KafkaListener` method, a `MessageListener` callback works directly with `ConsumerRecord`. The application must write its own logic to access the key, value, headers, and metadata as needed.

If manual acknowledgment is required, you can use a listener type that supports acknowledgment such as `AcknowledgingMessageListener` and configure the corresponding `AckMode`. Do not make arbitrary manual commits while the container is managing offsets; choose one consistent acknowledgment model.

## 5. Complete Example: Creating a Container for a Runtime Topic

Suppose the application needs to enable a consumer for a topic when a tenant is activated. The manager stores containers by topic to avoid duplicates and allow stopping the right container.

~~~java
@Component
public class DynamicOrderContainerManager {

    private final ConcurrentKafkaListenerContainerFactory<
            String, OrderCreatedEvent> factory;

    private final OrderService orderService;

    private final Map<String,
            ConcurrentMessageListenerContainer<String, OrderCreatedEvent>>
            containers = new ConcurrentHashMap<>();

    public DynamicOrderContainerManager(
            ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreatedEvent> factory,
            OrderService orderService) {
        this.factory = factory;
        this.orderService = orderService;
    }

    public synchronized void start(String topic, String groupId) {
        if (containers.containsKey(topic)) {
            return;
        }

        var container = factory.createContainer(topic);
        ContainerProperties properties = container.getContainerProperties();

        properties.setGroupId(groupId);
        properties.setAckMode(ContainerProperties.AckMode.RECORD);
        properties.setMessageListener(
                (MessageListener<String, OrderCreatedEvent>) record ->
                        orderService.handle(record.value())
        );

        containers.put(topic, container);
        container.start();
    }

    public synchronized void stop(String topic) {
        var container = containers.remove(topic);

        if (container != null) {
            container.stop();
        }
    }

    @PreDestroy
    public synchronized void stopAll() {
        containers.values().forEach(
                MessageListenerContainer::stop
        );
        containers.clear();
    }
}
~~~

This example uses one container per topic with the group ID passed in on start. If the same topic can be consumed by multiple group IDs within the same JVM, the management key should be the `topic + groupId` pair rather than just the topic.

In a real application, startup errors and container state must be handled. If `start()` fails or the container does not enter the running state, the manager needs to record the state so it can retry initialization or report an error. You should not rely solely on the container being added to the map to conclude that the consumer is active.

## 6. Topic Subscription vs. Explicit Partition Assignment

Spring Kafka supports two container creation styles with different semantics.

**Topic subscription**:

~~~java
var container = factory.createContainer(
        "orders.created",
        "orders.updated"
);
~~~

The consumer uses the group coordinator to join a consumer group and receive partition assignments according to its subscription and assignor.

**Explicit partition assignment**:

~~~java
var container = factory.createContainer(
        new TopicPartitionOffset("orders.created", 0),
        new TopicPartitionOffset("orders.created", 1)
);
~~~

In this approach, the container is directly assigned the specified partitions. The consumer does not use group subscription/rebalance to distribute those partitions as in normal subscribe mode.

Explicit assignment suits specialized tasks such as reading a single partition for migration or operational tooling. The application must manage partition ownership itself, prevent two containers from unintentionally processing the same partition, and decide how to initialize offsets.

If a group ID is used to commit offsets in manual assignment mode, offsets can still be stored per group, but the group coordinator does not automatically divide partitions among directly assigned consumers.

## 7. Choosing Concurrency for Dynamic Containers

With topic subscription, you can set concurrency so the container creates multiple consumer workers:

~~~java
var container = factory.createContainer("orders.created");
container.setConcurrency(3);
container.getContainerProperties().setGroupId("orders-fulfillment");
container.getContainerProperties().setMessageListener(
        (MessageListener<String, OrderCreatedEvent>) record ->
                orderService.handle(record.value())
);
container.start();
~~~

Concurrency is the number of consumer workers managed by the container, not an arbitrary number of listener methods or concurrently processed records.

When a topic has fewer partitions than the configured concurrency, some consumers may not receive any partition assignment. For example, if a topic has two partitions but container concurrency is five, the container can create five consumers, yet at most two consumers hold partitions from that topic at a time if all share the same subscription.

If a container uses explicit partition assignment, the number of consumers may be bounded by the number of assigned partitions. Always compare concurrency, partition count, and actual assignments before scaling.

## 8. Group ID, Offsets, and Rebalance When Creating a New Container

When a container subscribes to topics with a group ID, it joins the consumer group. If a new container is started with the same group ID and a compatible subscription, Kafka may rebalance to distribute partitions across members.

The outcome depends on:

- The partition counts of the topics.
- Each member's subscription.
- The partition assignor.
- The group protocol and member states.
- Whether consumers are joining, leaving the group, or restarting.

A new container does not create a new group if the group ID is the same. Conversely, a different group ID has independent offsets and can re-read the entire topic according to `auto.offset.reset` when the group has no committed offsets yet.

Before creating a container, determine whether it is an additional consumer scaling an existing group or an independent consumer that needs to receive the entire stream. This decision directly impacts which data is read and the load placed on the broker.

## 9. Starting, Pausing, Resuming, and Stopping a Container

The container supports lifecycle operations:

~~~java
container.start();

container.pause();
container.resume();

container.stop();
~~~

- `start()`: starts the consumer workers and polling.
- `pause()`: pauses receiving records according to the container mechanism.
- `resume()`: resumes consumption.
- `stop()`: stops the container and closes the consumers according to the lifecycle.

Pause is not the same as stop. Pause keeps the container and group membership via the consumer/container mechanism, whereas stop closes the consumer and can trigger a group rebalance.

If you need to wait until the container finishes stopping before releasing dependent resources, use the lifecycle stop callback when supported by your API version. Do not remove management state before you have a plan for handling a failed or incomplete stop.

## 10. Managing Containers with KafkaListenerEndpointRegistry

Containers created from `@KafkaListener` are typically managed by Spring through `KafkaListenerEndpointRegistry`. You can look up a container by listener ID and control its lifecycle:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && !container.isRunning()) {
    container.start();
}
~~~

The registry manages listener endpoints registered with it, including annotation-based endpoints and endpoints dynamically registered via the registry API.

A container created directly with `factory.createContainer(...)` does not automatically appear in the registry just because it uses the same factory. The application must retain references to and manage the lifecycle of those containers itself, or register a dynamic endpoint through the registry if it wants the registry to manage it.

Do not mix both models without a clear owner. A container needs a single place responsible for starting, stopping, and shutting it down.

## 11. Registering Listener Endpoints Dynamically via the Registry

When you want to create an annotation-style endpoint and register it at runtime, Spring Kafka provides an API to register listener endpoints with `KafkaListenerEndpointRegistry`.

General workflow:

1. Create a `KafkaListenerEndpoint` with a unique ID.
2. Configure the group ID, topics or partitions, and the listener method/bean.
3. Choose the appropriate container factory.
4. Call `registerListenerContainer(endpoint, factory, startImmediately)`.
5. Retrieve the container by endpoint ID from the registry to start/stop or observe it.

This approach fits when the application needs to manage endpoints via the registry. However, creating a `MethodKafkaListenerEndpoint` requires configuring the method, bean, and message handler factory compatible with your Spring Kafka version. If you only need a simple `ConsumerRecord` callback, creating the container directly from the factory is usually easier to understand.

The endpoint ID must be unique in the registry. Before registering, check whether the endpoint already exists to avoid duplicate registration errors.

## 12. Dynamic Topic Does Not Mean Automatic Kafka Topic Creation

Calling `factory.createContainer("tenant-42.orders")` only creates a consumer container to subscribe to the topic. It is not an API that creates topics on the broker.

The topic must already exist, or the broker must be configured to allow auto-creation. In production, topics should be provisioned via `AdminClient`, IaC, or a dedicated topic governance process, with controlled partition counts, replication factors, retention, and ACLs.

A flow to activate a stream can include:

1. Validating the tenant and permission to create the subscription.
2. Verifying that the topic has been provisioned.
3. Checking the consumer group and offset policy.
4. Creating the container with the approved configuration.
5. Starting and verifying that the container is active.
6. Monitoring lag, assignment, and consumer errors.

Do not allow external requests to pass an arbitrary topic and immediately create a container. Doing so can cause the application to subscribe to unauthorized topics or spawn an unbounded number of consumers.

## 13. Error Handling and Shared Configuration

A container created from a factory can use shared settings configured on the factory, such as `ConsumerFactory`, concurrency, common error handler, record filter strategy, and container properties applied by the factory.

However, explicitly verify per-container settings:

- Group ID.
- AckMode.
- Message listener.
- Subscription or partition assignment.
- Client ID prefix.
- Error handling and retries.
- Deserializers and type mapping on the `ConsumerFactory`.

If the listener callback throws an exception, the container must have an appropriate error handler. Do not catch and swallow all exceptions inside the callback, as doing so can advance offsets even though business logic failed.

If using a transactional listener container, you must configure the appropriate transaction manager and `KafkaTemplate`. Do not assume a programmatically created container automatically has transactions just because another factory in the application uses transactions.

## 14. Managing Concurrency and Container Count

Each container can create one or more consumer workers depending on concurrency. If the application creates one container per tenant and each container has concurrency three, 100 tenants can spawn up to 300 consumer workers.

Before scaling, calculate:

~~~text
N_consumers = sum(C_i), for i = 1..N_containers
~~~

Where `C_i` is the concurrency of the `i`-th container. The actual number of workers holding assignments also depends on partition counts and group subscriptions.

Limits should be enforced for:

- Maximum number of containers per application instance.
- Maximum concurrency per container.
- Total consumer workers across the deployment.
- Number of allowed subscribed topics/tenants.
- Heap, thread, connection, and broker request resources.
- Number of start/stop operations within a time window.

If many tenants share the same processing logic, consider a single container subscribing to multiple topics or an appropriate routing model instead of creating a separate container per tenant. The decision should consider isolation, group semantics, and offset management capability.

## 15. Avoiding Duplicates and Race Conditions

A dynamic container manager often receives start/stop commands from APIs, schedulers, or administrative events. Two concurrent requests could both create a container for the same topic if not synchronized.

Measures to take:

- Use a registry/map keyed uniquely by container identity.
- Synchronize creation and removal operations or use an explicit state machine.
- Distinguish `STARTING`, `RUNNING`, `STOPPING`, and `STOPPED`.
- Only mark `RUNNING` after the container confirms it has started.
- On startup failure, release the container and allow controlled retries.
- Do not allow stopping a container in `STARTING` state without explicit rules.
- Persist container configuration so it can be restored after a restart if needed.

Do not use only the topic as the key if the same topic can have multiple group IDs or different assignments. An identity can consist of the topic subscription, group ID, and assignment type.

## 16. Shutdown and Releasing Resources

Dynamic containers are not managed like regular beans if the application creates them via a factory and holds them in a map. The manager must stop all containers when the application context shuts down.

For example:

~~~java
@PreDestroy
public void shutdown() {
    containers.values().forEach(MessageListenerContainer::stop);
    containers.clear();
}
~~~

In systems with many containers, you can stop them in order or wait for callbacks to confirm each container has closed its consumers. If in-flight records must be drained, design a shutdown timeout and process in-flight records before the process exits.

Do not delete topics or group offsets when stopping a container. Stopping a container only stops the consumer; Kafka data and committed offsets remain according to retention and group configuration.

If a container is registered in `KafkaListenerEndpointRegistry`, let the registry/Spring lifecycle manage it according to the rightful owner instead of stopping the same container from multiple places.

## 17. Observing Dynamic Containers

A dynamic container needs a stable identifier for operations. You should store and expose:

- Container ID.
- Topic subscription or partition assignment.
- Group ID.
- Concurrency.
- Lifecycle state.
- Client ID of the consumer workers.
- Current partition assignment.
- Consumer lag and processing rate.
- Start/stop counts and initialization errors.

Manager-created containers can be observed via the internal map. For containers registered in the registry, use `KafkaListenerEndpointRegistry` to query them.

On the Kafka side, use `AdminClient` or consumer group management tools to inspect members and partition assignments. Do not treat `container.isRunning()` as proof that every consumer has joined the group or been assigned partitions.

Logs should include the container ID, group ID, topic, partition, and lifecycle transitions. Avoid using a high-cardinality tenant ID as a metric label if the number of tenants is unbounded.

## 18. Testing Dynamic Listener Containers

Tests should verify lifecycle and consumer group semantics, not just that a container object was instantiated.

| Scenario | What to Verify |
|---|---|
| Create container by topic | Container has the expected subscription and group ID. |
| Start | Consumer is created and joins the group. |
| Receive record | `MessageListener` is invoked with the expected key/value. |
| Stop | Consumer closes and member leaves the group. |
| Duplicate start | Manager does not unintentionally create a second container. |
| Two group IDs | Independent offsets and assignments. |
| Same group ID | Members share partitions via group assignment. |
| Concurrency greater than partitions | Extra consumers receive no partition assignment. |
| Explicit assignment | Container reads only the specified partitions. |
| Start failure | Manager does not retain a false `RUNNING` state. |
| Shutdown | All dynamic containers are stopped. |
| Rebalance | Assignment changes are observed and handled safely. |

Use EmbeddedKafka or Testcontainers to test against a real broker and listener container. Use Awaitility or latches with timeouts to wait for container startup, assignment, or record arrival; do not rely on fixed `Thread.sleep`.

When testing stop, verify that the consumer group member leaves and no more records are processed by the stopped container. If other members exist in the group, the group can still continue operating.

## 19. Common Pitfalls

| Pitfall | Consequence | Resolution |
|---|---|---|
| Creating container but forgetting `start()` | Consumer does not poll records | Call start after configuring the listener. |
| Not setting the right group ID | Consumer joins unintended group or fails configuration | Specify the group ID for each container. |
| Creating duplicate containers | Extra consumers, duplicate processing, or rebalance | Use container identity and a deduplicating manager. |
| Not stopping containers | Thread, connection, and consumer leaks | Manage lifecycle and shutdown. |
| Thinking `createContainer` creates topics | Consumer subscribes to non-existent topic or fails | Provision topics separately via `AdminClient`/IaC. |
| Confusing subscribe with explicit assignment | Misunderstanding rebalances and partition ownership | Choose the API matching the desired semantics. |
| Creating too many containers | Increased resource usage and group coordination | Enforce quotas, limit concurrency, and monitor. |
| Direct container expecting registry management | Container not found in registry | Manage directly or register dynamic endpoint via registry. |
| Unsynchronized concurrent start/stop | Duplicate containers or invalid state | Use a state machine/locks and handle lifecycle. |
| Not configuring an error handler | Listener errors are not recovered per policy | Use an appropriate factory and error handler. |

## 20. Capstone Exercise: Managing Consumers per Tenant

Build a `DynamicOrderContainerManager` for per-tenant topics.

Requirements:

1. Create a `ConcurrentKafkaListenerContainerFactory` with a `ConsumerFactory` and `CommonErrorHandler`.
2. Create a container via `factory.createContainer(topic)` when a tenant is activated.
3. Set the group ID according to the chosen subscription policy.
4. Attach a `MessageListener` to process `OrderCreatedEvent`.
5. Configure `AckMode` and concurrency.
6. Prevent duplicate container creation based on container identity.
7. Start the container and record its lifecycle state.
8. Stop the container when the tenant is deactivated.
9. Stop all containers when the application shuts down.
10. Experiment with creating containers by topic and by `TopicPartitionOffset`.
11. Use two group IDs to observe independent offsets.
12. Use the same group ID to observe rebalancing and partition sharing.
13. Test concurrency greater than the partition count.
14. Use `AdminClient` to verify members and assignments.
15. Write integration tests for start, receive, stop, restart, and shutdown.
16. Set quotas on container count and concurrency to avoid creating too many consumers.

The exercise is complete when the manager can create, track, and stop containers based on runtime configuration; prevents duplicates; leaks no consumers; and you can accurately explain group membership, offsets, and partition assignments after each change.

## 21. Learning Path and Completion Criteria

| Stage | Core Focus | Self-Check Criteria |
|---|---|---|
| 1. Container model | Factory and listener container | Can explain how the factory creates containers. |
| 2. Programmatic creation | `createContainer()` | Can create a container for a topic in code. |
| 3. Listener callback | `MessageListener` and `ConsumerRecord` | Can attach a callback and process records. |
| 4. Container properties | Group ID, AckMode, poll timeout | Can configure properly before starting. |
| 5. Subscription | Topics and `TopicPartitionOffset` | Can distinguish group subscription from manual assignment. |
| 6. Concurrency | Consumer workers and partitions | Can choose concurrency based on partitions and load. |
| 7. Lifecycle | Start, pause, resume, stop | Can manage containers at runtime. |
| 8. Registry | `KafkaListenerEndpointRegistry` | Can distinguish direct containers from registry-managed endpoints. |
| 9. Operations | Quotas, state, metrics, shutdown | Can prevent duplicate containers and resource leaks. |
| 10. Testing | Dynamic lifecycle and group assignment | Can verify start/stop, offsets, and rebalances. |

The lesson is complete when you can create listener containers using `ConcurrentKafkaListenerContainerFactory`, configure the listener and group ID, start/stop them at runtime, and distinguish topic-based subscription from explicit partition assignment.

Dynamic containers help an application react to subscription needs that change at runtime. In return, the application must explicitly manage identity, lifecycle, group semantics, offsets, and resource quotas. Always create containers from a configured factory, start only after the listener is ready, and ensure a stop/shutdown process so consumers are never left unmanaged.

