# Managing Lifecycle in an Application

## Lesson Objectives

In the **Dynamic containers** chapter, this lesson covers managing the lifecycle of Kafka listener containers in a Spring Kafka application. An application may need to enable or disable a listener based on configuration, create a consumer when a tenant is activated, stop a stream when a service is turned off, or temporarily pause a consumer when downstream is overloaded.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive Kafka events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-lettering, transactions, exactly-once semantics, concurrency, and testing. Proper lifecycle management lets you control consumers according to application state while keeping commit, retry, and shutdown behavior predictable.

After this lesson, learners will be able to:

- Distinguish a listener container's lifecycle from a Spring bean's lifecycle.
- Control containers created by `@KafkaListener` using `KafkaListenerEndpointRegistry`.
- Use `autoStartup` to control automatic listener startup.
- Start, stop, pause, and resume listener containers for their intended purposes.
- Create dynamic containers from `ConcurrentKafkaListenerContainerFactory`.
- Manage dynamic containers with a component that has an explicit lifecycle.
- Choose subscriptions by topic, pattern, or partition assignment.
- Handle group IDs, concurrency, and resources when running multiple containers.
- Perform graceful shutdown and avoid leaving orphaned consumers behind.
- Observe container state and test lifecycle operations.

## 1. Listener Containers Have Their Own Lifecycle

In Spring Kafka, `@KafkaListener` does not directly spawn a consumer running inside the Java method. Spring detects the annotation, creates an endpoint, and registers a listener container to manage the consumer, poll loop, and listener invocations.

A listener container has lifecycle states and operations such as:

- Start: starts consumers and begins receiving records.
- Stop: stops consumers in a controlled manner.
- Pause: temporarily stops receiving new records while the container still exists.
- Resume: resumes receiving records after being paused.
- Status inspection: checks whether the container is running or paused.

Two concepts should be distinguished:

| Object | Role |
|---|---|
| Spring listener bean | Holds the event-handling method |
| Message listener container | Manages the Kafka consumer and invokes the listener method |
| Kafka consumer | Polls records from the broker and joins the consumer group |
| Endpoint registry | Stores and manages containers registered via listener endpoints |

A listener bean is usually a singleton. Stopping a container does not remove the listener bean from the Spring `ApplicationContext`. Conversely, the bean continues to exist even while its container is stopped.

## 2. Managing Containers Created from @KafkaListener

Spring Kafka provides `KafkaListenerEndpointRegistry` to manage listener containers created from `@KafkaListener` and endpoints registered with the registry.

Example declaring a listener with an ID:

~~~java
@Service
public class OrderEventListener {

    private final BillingService billingService;

    public OrderEventListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
        id = "ordersListener",
        topics = "commerce.order.created",
        groupId = "billing-service"
    )
    public void listen(OrderCreated event) {
        billingService.process(event);
    }
}
~~~

The `id` attribute identifies the listener container in the registry. You can retrieve the container by ID and control its lifecycle:

~~~java
@Service
public class OrderListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderListenerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container == null) {
            throw new IllegalStateException(
                "ordersListener has not been registered"
            );
        }

        if (!container.isRunning()) {
            container.start();
        }
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
~~~

`getListenerContainer(id)` returns the container registered with the registry. If the ID is wrong or the endpoint has not been registered yet, the result can be `null`. Always check before invoking lifecycle methods.

### 2.1. Enabling/Disabling Auto-Startup with autoStartup

By default, listener containers usually start automatically with Spring's lifecycle. If you want the application to decide when to start, set `autoStartup` to `false`:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    groupId = "billing-service",
    autoStartup = "false"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

The container is still registered in the registry, though it does not run automatically when the application context starts. The application can call `start()` after validating configuration or business state.

You can set `autoStartup` per environment using placeholders or SpEL supported by the annotation. For example, defaulting to `false` in development and `true` in production. This attribute only controls automatic container startup; it does not determine whether the listener bean is created.

### 2.2. When to Call start

Do not retrieve a container from the registry inside another bean's constructor assuming the endpoint is already registered. Listener endpoints are discovered and registered during application context initialization.

If you need to control startup after the application is ready, you can use `ApplicationReadyEvent`:

~~~java
@Component
public class OrdersListenerStartup {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersListenerStartup(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void startListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null && !container.isRunning()) {
            container.start();
        }
    }
}
~~~

Use this approach only when the listener must start after a specific startup condition. When no special condition exists, letting Spring manage auto-startup is usually simpler.

## 3. How Do Start, Stop, Pause, and Resume Differ?

These operations serve different purposes:

| Operation | Meaning | When to Use |
|---|---|---|
| `start()` | Starts the container | Enabling a stopped listener |
| `stop()` | Stops the container | Disabling a listener or shutting down |
| `pause()` | Requests the consumer to temporarily stop receiving new records | Downstream overloaded, temporary throttling needed |
| `resume()` | Resumes receiving records after pause | Downstream has recovered |
| `isRunning()` | Checks whether the container is running | Health/status endpoints or operations |
| `isContainerPaused()` | Checks the container's pause state | Flow-control monitoring |

Pause is not the same as stop. When paused, the container still exists and consumers remain within its lifecycle; fetching new records is temporarily halted via the container mechanism. When resumed, consumers continue operating without recreating the container.

Example:

~~~java
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
~~~

Pause is typically suited for load shedding or brief maintenance. Stop is suited when you want to terminate the consumer container. Do not repeatedly stop/start as a substitute for `pause`/`resume` when the goal is merely temporary throttling.

## 4. What Happens When a Container Stops?

When stop is called, the listener container stops polling and terminates consumers according to Spring Kafka's lifecycle. Handling of in-flight records and offset commits depends on the acknowledgment mode, transactions, processing state, and library version.

Key points to understand:

- Processed and committed records will not be redelivered according to the committed offsets.
- Uncommitted records may be redelivered when the consumer restarts or partitions are assigned to another consumer.
- Side effects written to a database before an offset commit may execute again if the record is redelivered.
- If a listener is processing during shutdown, give the container enough time to finish per the shutdown policy.
- Do not assume stopping means all asynchronous work initiated by the listener has completed.

Therefore, listeners must be idempotent when business logic has side effects. For asynchronous work, wait for tasks to finish or design an explicit acknowledgment/offset mechanism.

## 5. Managing All Listeners via KafkaListenerEndpointRegistry

The registry can retrieve the list of IDs and registered containers:

~~~java
@Service
public class KafkaListenerOperations {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerOperations(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public Map<String, Boolean> listenerStatuses() {
        Map<String, Boolean> statuses = new LinkedHashMap<>();

        for (MessageListenerContainer container :
                registry.getListenerContainers()) {
            statuses.put(
                container.getListenerId(),
                container.isRunning()
            );
        }

        return statuses;
    }

    public void stopAllRegisteredListeners() {
        registry.stop();
    }

    public void startAllRegisteredListeners() {
        registry.start();
    }
}
~~~

`getListenerContainers()` returns the containers managed by the registry. Containers created directly from a factory and not registered with the registry will not automatically appear in this list.

Use registry-wide start/stop operations when you need to control the whole set of listeners. If you only want to turn off one stream, look up that container by ID rather than stopping all of them.

## 6. Creating Dynamic Listener Containers with a Factory

In some cases, the list of topics or tenants is only known while the application is running. In that case, you can create containers from `ConcurrentKafkaListenerContainerFactory`.

The factory provides shared settings such as:

- `ConsumerFactory` and deserializers.
- Concurrency.
- Common error handler.
- Record interceptor.
- Default container properties.
- Other options configured on the factory.

Example creating a container for a topic:

~~~java
ConcurrentMessageListenerContainer<String, OrderCreated> container =
    listenerContainerFactory.createContainer(
        "commerce.order.created"
    );

container.getContainerProperties()
    .setGroupId("billing-service");

container.setupMessageListener(
    (MessageListener<String, OrderCreated>) record ->
        billingService.process(record.value())
);

container.start();
~~~

Important sequence:

1. Create the container from the factory with the topics or partitions to consume.
2. Set the group ID if overriding the default configuration.
3. Attach the message listener via `setupMessageListener`.
4. Configure container-specific properties.
5. Start the container.
6. Store the reference so you can pause, resume, or stop it later.

A container created directly from a factory must have its lifecycle managed by the application. Do not assume it is registered in `KafkaListenerEndpointRegistry` or automatically managed by Spring as a separate bean.

## 7. Managing Dynamic Containers with a Component

Do not create a container inside a controller and discard its reference. Have a dedicated component responsible for creating, storing, starting, and stopping containers.

The following example illustrates a manager handling one container per tenant. In a real system, topic names and group IDs must be validated against platform conventions.

~~~java
@Component
public class TenantConsumerManager implements SmartLifecycle {

    private final ConcurrentKafkaListenerContainerFactory<String, TenantEvent>
        containerFactory;

    private final TenantEventHandler eventHandler;

    private final Map<String,
        ConcurrentMessageListenerContainer<String, TenantEvent>> containers =
            new HashMap<>();

    private volatile boolean running;

    public TenantConsumerManager(
            ConcurrentKafkaListenerContainerFactory<String, TenantEvent>
                containerFactory,
            TenantEventHandler eventHandler) {
        this.containerFactory = containerFactory;
        this.eventHandler = eventHandler;
    }

    public synchronized void startTenant(String tenantId) {
        if (!running) {
            throw new IllegalStateException(
                "TenantConsumerManager is not running"
            );
        }

        var existing = containers.get(tenantId);
        if (existing != null) {
            if (!existing.isRunning()) {
                existing.start();
            }
            return;
        }

        String topic = topicFor(tenantId);

        var container = containerFactory.createContainer(topic);
        container.setBeanName("tenant-" + tenantId);
        container.getContainerProperties()
            .setGroupId(groupIdFor(tenantId));

        container.setupMessageListener(
            (MessageListener<String, TenantEvent>) record ->
                eventHandler.handle(tenantId, record.value())
        );

        try {
            container.start();
            containers.put(tenantId, container);
        } catch (RuntimeException exception) {
            container.stop();
            throw exception;
        }
    }

    public synchronized void stopTenant(String tenantId) {
        var container = containers.get(tenantId);

        if (container != null) {
            container.stop();
            containers.remove(tenantId, container);
        }
    }

    @Override
    public void start() {
        running = true;
    }

    @Override
    public synchronized void stop() {
        RuntimeException failure = null;

        for (var entry : new ArrayList<>(containers.entrySet())) {
            try {
                entry.getValue().stop();
                containers.remove(entry.getKey(), entry.getValue());
            } catch (RuntimeException exception) {
                if (failure == null) {
                    failure = new IllegalStateException(
                        "One or more tenant containers could not be stopped",
                        exception
                    );
                } else {
                    failure.addSuppressed(exception);
                }
            }
        }

        running = false;

        if (failure != null) {
            throw failure;
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }

    private String topicFor(String tenantId) {
        return "tenant." + tenantId + ".events";
    }

    private String groupIdFor(String tenantId) {
        return "tenant-event-processor-" + tenantId;
    }
}
~~~

This manager demonstrates core principles:

- Using a map to retain references to each container.
- Synchronizing creation/removal operations to prevent creating two containers for the same tenant in the same process.
- Attaching the listener before starting.
- Starting the new container and storing it for management.
- Stopping the container before removing management state.
- Stopping all child containers when Spring calls lifecycle `stop`.

This is a lifecycle management skeleton. Add tenant ID validation, container count limits, logging, metrics, and error-handling policies tailored to your real application.
In this example, `isRunning()` reflects that the manager is participating in Spring's lifecycle; it does not claim that every child container is healthy. Check the state of each individual container and record any containers that fail to stop. The `stop()` method attempts to stop remaining containers even if one throws an exception, while keeping references to containers that failed to stop so they can be observed and handled.

### 7.1. Why Use SmartLifecycle?

`SmartLifecycle` allows a component to participate in the start/stop lifecycle of the Spring `ApplicationContext`. The manager can stop child containers when the application shuts down.

`getPhase()` determines relative start/stop ordering among lifecycle components. Components with lower phases typically start earlier and stop later; components with higher phases start later and stop earlier. Choose the phase based on actual application dependencies.

If the manager only creates containers on runtime demand and does not need startup lifecycle participation, you can use `DisposableBean` or `@PreDestroy` for cleanup. Whichever you choose, ensure every manually created container is stopped when the application shuts down.

## 8. Choosing Subscription: Topic, Pattern, or Partition Assignment

The factory can create containers with several subscription styles.

### 8.1. Subscribing to One or More Topics

~~~java
var container = containerFactory.createContainer(
    "commerce.order.created",
    "commerce.order.cancelled"
);
~~~

The consumer subscribes to the declared topics and participates in group assignment.

Suitable when the topic set is known in advance or varies per configuration.

### 8.2. Subscribing by Topic Pattern

If topics are dynamically created following a naming convention, you can subscribe via regex:

~~~java
var container = containerFactory.createContainer(
    Pattern.compile("^tenant\\..*\\.events$")
);
~~~

The consumer discovers topics matching the pattern via the Kafka client's metadata refresh mechanism. This can reduce the need to create one container per topic when topics share the same schema and processing logic.

Control regexes and topic access permissions. An overly broad pattern can cause the consumer to accidentally subscribe to topics outside business scope.

### 8.3. Assigning Specific Partitions

If the application needs to target exact partitions, you can create a container using `TopicPartitionOffset`:

~~~java
var container = containerFactory.createContainer(
    new TopicPartitionOffset("commerce.order.created", 0)
);
~~~

This is explicit assignment. The application takes responsibility for distributing partitions across containers and handling topology changes. It differs from topic subscription where the Kafka group coordinator distributes partitions automatically.

Do not assign multiple consumers to the same partition without an explicit ownership design. Two independent consumers could read the same partition and cause duplicate processing.

## 9. Group ID and Concurrency for Dynamic Containers

Each container can use its own group ID or join the same logical consumer group depending on the goal.

| Goal | Group ID |
|---|---|
| Multiple instances process one topic stream and split partitions | Same group ID |
| Two independent services both need to receive all events | Different group IDs |
| Each tenant is an independent processing stream | Per-tenant group ID |
| Multiple containers in one JVM scaling one subscription | Unified group/subscription design with verified assignment |

Do not generate a random group ID on each restart if you want to continue from prior committed offsets. A stable group ID lets the consumer resume saved progress.

Concurrency is configured on the factory or container. Useful consumer count is bounded by the number of assigned partitions. For example, on a 4-partition topic, concurrency 8 does not yield 8 consumers concurrently processing data from that topic; some consumers will receive no partitions.

When creating multiple dynamic containers, actual total consumers equal the sum of concurrencies across all containers. Cap container counts and consumer counts so you do not exceed broker, network, thread, and database resources.

## 10. Idempotent Dynamic Start/Stop

Lifecycle management APIs may be called repeatedly due to HTTP request retries, schedulers, or configuration events. Therefore, operations should be idempotent:

- Starting an already-running container: do not create a second container.
- Starting an existing but stopped container: restart that container.
- Stopping a stopped or nonexistent container: return an appropriate result without unexpected errors.
- Failing to create a container: do not leave a stale entry in the internal registry.
- Failing to stop: log the error and maintain observability for follow-up handling.

The manager example earlier used `synchronized` to protect the map within one JVM. If multiple replicas receive commands to create consumers, in-JVM synchronization is insufficient to guarantee only one replica creates a container. An external coordination mechanism is needed when ownership must be cluster-wide unique.

Do not use a local map as the source of truth for tenant state if multiple instances can manage it. Store desired state in a database/config service and let each instance reconcile according to design.

## 11. Pause/Resume for Load Throttling

If downstream is temporarily overloaded, pausing the container stops receiving more records while keeping the container alive.

Example:

~~~java
public void pauseTenant(String tenantId) {
    var container = containers.get(tenantId);

    if (container != null && container.isRunning()) {
        container.pause();
    }
}

public void resumeTenant(String tenantId) {
    var container = containers.get(tenantId);

    if (container != null && container.isRunning()) {
        container.resume();
    }
}
~~~

In a real manager, these two methods must use the same synchronization or concurrent map scheme as start/stop operations.

Pause can be useful when:

- A database is undergoing maintenance.
- Downstream is hitting rate limits.
- A single tenant needs to be temporarily paused.
- Configuration is changing and you want to halt incoming records.

Pause does not delete records from Kafka, nor does it dissolve the consumer group. Records continue accumulating in the topic and consumer lag may grow. Set alert thresholds and have a resume plan.

## 12. Graceful Shutdown and Stop Duration

Spring applications normally stop listener containers while closing the application context. For manually created containers, the manager must ensure all child containers are stopped.

A shutdown sequence should:

1. Stop accepting requests to create new containers.
2. Stop or pause containers per policy.
3. Allow in-flight processing to finish within the allotted window.
4. Let containers apply configured acknowledgment/commit semantics.
5. Close associated consumers and producers.
6. Log which containers stopped successfully or failed.

Container properties can configure a shutdown timeout:

~~~java
container.getContainerProperties()
    .setShutdownTimeout(15_000L);
~~~

The exact timeout must suit record processing time, transactions, and the application's shutdown budget. Do not increase the timeout indefinitely to mask a hung listener.

If shutdown is forced before commits complete, records may be redelivered. That is why idempotency and duplicate handling remain essential even with graceful shutdown.

## 13. Lifecycle Events and State Observation

Spring Kafka emits application events related to consumer/container lifecycles. You can use event listeners to log or update operational status.

Example tracking stopped consumers and containers:

~~~java
@Component
public class KafkaContainerEvents {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaContainerEvents.class);

    @EventListener
    public void onConsumerStopped(ConsumerStoppedEvent event) {
        log.info("Kafka consumer stopped: {}", event);
    }

    @EventListener
    public void onContainerStopped(ContainerStoppedEvent event) {
        log.info("Kafka container stopped: {}", event);
    }
}
~~~

Depending on container type and version, you can also observe idle events, partition assigned/revoked events, pause/resume events, or unresponsive-consumer events. Events may be emitted for child containers/consumers; avoid assuming each event corresponds to a single listener endpoint.

Information worth tracking:

- Listener ID or bean/container name.
- Topics and assigned partitions.
- Group ID.
- Container running/paused status.
- Number of consumer threads.
- Consumer lag.
- Start/stop counts.
- Startup/shutdown errors.
- Record processing time and retry rate.

Do not check only `isRunning()`. A running container may still lack partition assignments, be paused, or make no progress due to broker/downstream issues.

## 14. Distinguishing Stop, Pause, and Subscription Changes

These three actions have different effects:

| Need | Approach |
|---|---|
| Temporarily halt receiving records and resume later | Pause/resume |
| Stop consumer completely | Stop |
| Change topic set | Stop old container, create container with new subscription, or use an appropriate pattern |
| Change group ID | Recreate consumer/container with new group ID |
| Transfer partition ownership | Use group rebalance or a controlled assignment strategy |
| Pause a single partition | Pause/resume partition if container API and design support it |

Do not change the group ID or active subscription by mutating a configuration field and expecting the consumer to switch automatically. Such changes typically require recreating the container or using an explicitly supported API.

## 15. Securing Lifecycle Control APIs

If you provide HTTP endpoints to start/stop listeners, those endpoints directly affect event processing. Protect them as administrative operations.

Example controller delegating solely to the manager:

~~~java
@RestController
@RequestMapping("/admin/kafka/consumers")
public class ConsumerAdminController {

    private final TenantConsumerManager manager;

    public ConsumerAdminController(TenantConsumerManager manager) {
        this.manager = manager;
    }

    @PostMapping("/{tenantId}/start")
    public ResponseEntity<Void> start(@PathVariable String tenantId) {
        manager.startTenant(tenantId);
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/{tenantId}/stop")
    public ResponseEntity<Void> stop(@PathVariable String tenantId) {
        manager.stopTenant(tenantId);
        return ResponseEntity.noContent().build();
    }
}
~~~

In production:

- Enforce admin authentication and authorization.
- Validate tenant IDs and topic names against an allowlist.
- Audit who started/stopped and when.
- Rate-limit operations to prevent continuous consumer churn.
- Return actual state rather than only indicating the request was accepted.
- Do not let users pass arbitrary regexes or topic names to subscribe to.
- Cap the maximum number of dynamic containers.

## 16. Testing Listener Lifecycle

Test both annotation-managed containers and dynamically created containers.

### 16.1. Testing @KafkaListener with the Registry

Declare the listener with `autoStartup = "false"`, then:

1. Retrieve the container by listener ID.
2. Verify the container is not yet running.
3. Call start.
4. Send a record and verify the listener receives it.
5. Call stop.
6. Verify the container stops.
7. Restart and verify resumption from committed offsets.

Use EmbeddedKafka or Testcontainers to test against a real broker. Do not only mock the registry, as actual consumer lifecycle must be verified.

### 16.2. Testing Dynamic Containers

With the manager:

1. Call start for a tenant.
2. Verify the container is created and running.
3. Call start again and verify no second container is created.
4. Send a record to the tenant topic and verify the handler receives the event.
5. Pause the container and observe receipt of new records.
6. Resume and verify processing continues.
7. Stop the tenant and verify the container stops.
8. Stop the tenant again and verify the operation is safe.
9. Stop the application context and verify all child containers close.

Synchronize tests with latches or Awaitility. Avoid fixed `Thread.sleep()` to guess when consumers have subscribed or received partitions.

## 17. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `getListenerContainer` returns null | Wrong ID or endpoint not yet registered | Check `id` and call timing |
| Listener does not auto-start | `autoStartup=false` | Call start after endpoint registration |
| Dynamic container receives no records | Listener not attached or wrong topic subscribed | Call `setupMessageListener` before start and check subscription |
| Cannot stop consumer | Container not stored/tracked | Track containers in a manager |
| Repeated start spawns multiple consumers | Missing check for existing container | Make start operations idempotent |
| Consumer has no partitions | Concurrency exceeds partitions or group assignment | Check partitions and group membership |
| Records reprocessed after restart | Offsets uncommitted before shutdown | Design idempotency and appropriate acks |
| Paused yet lag grows | Consumer stopped fetching new records | Monitor lag and plan resume |
| Dynamic containers survive shutdown | Manager did not stop child containers | Participate in `SmartLifecycle` or cleanup |
| Two replicas spawn duplicate consumers | Synchronization only within one JVM | Use external desired state/coordination |
| Pattern subscribes to too many topics | Overly broad regex | Restrict patterns and ACLs |
| Changing group ID yields unexpected offsets | New group ID has its own committed offsets | Check reset/offset policies |

## 18. Pre-Production Checklist for Dynamic Containers

- [ ] Annotated listeners have stable IDs?
- [ ] `autoStartup` used when startup timing must be controlled?
- [ ] Registry accessed only after endpoints are registered?
- [ ] Registry-managed containers distinguished from containers created directly from a factory?
- [ ] Dynamic containers stored for lifecycle management?
- [ ] Listeners attached before containers start?
- [ ] Group IDs stable and aligned with partition-sharing model?
- [ ] Container counts and concurrency bounded?
- [ ] Topics/patterns validated against an allowlist?
- [ ] Pause/resume used for temporary halts, stop for full shutdown?
- [ ] Child containers stopped on application shutdown?
- [ ] Shutdown timeout matches processing duration?
- [ ] Possibility of record redelivery after shutdown evaluated?
- [ ] Metrics exist for running, paused, assigned partitions, and lag?
- [ ] Repeated start/stop, pause/resume, rebalances, and shutdown tested?

## Conclusion

Spring Kafka provides `KafkaListenerEndpointRegistry` to control containers created from `@KafkaListener`. Use listener IDs to retrieve containers, combining `autoStartup`, `start()`, and `stop()` when enabling or disabling listeners based on application state. For topics or tenants only known at runtime, create containers from `ConcurrentKafkaListenerContainerFactory`, attach listeners, and manage references and lifecycle yourself.

A container created directly from a factory must be tracked by a manager and stopped on application shutdown. Distinguish pause from stop, size group IDs and concurrency to match partition topology, cap dynamic container counts, secure administrative APIs, and design idempotency because uncommitted records may be redelivered. Testing lifecycle against a real Kafka broker verifies that consumers start, pause, resume, and stop exactly as the application expects.
