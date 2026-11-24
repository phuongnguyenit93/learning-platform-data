# Container start and stop

In Spring Kafka, the listener container manages the lifecycle of Kafka consumers: creating consumers, calling `poll()`, delivering records to the listener, managing offsets, and closing consumers when stopping. Controlling when a container starts or stops is an important part of operations, especially when an application needs to wait for database migrations, dependency readiness, maintenance, or controlled shutdown.

Spring Kafka typically creates containers for `@KafkaListener` and manages them through `KafkaListenerEndpointRegistry`. Applications can let containers auto-start with the Spring context, defer startup via `autoStartup`, or explicitly call `start()` and `stop()` on containers managed by the registry.

## 1. Listener container lifecycle

A listener container manages one or more Kafka consumers. With `ConcurrentMessageListenerContainer`, the `concurrency` property determines how many child containers/consumers are created to process partitions assigned to the consumer group in parallel.

The basic lifecycle can be described as follows:

```text
Spring ApplicationContext starts
              |
              v
KafkaListenerEndpointRegistry starts
              |
              v
Listener container start()
              |
              v
Consumer connects and joins consumer group
              |
              v
poll() -> listener processes -> commit offset per AckMode
              |
              v
Listener container stop()
              |
              v
Consumer leaves group and closes resources
```

The container executes operations on consumer threads. Calling `start()` requests the container to begin operating; do not assume that immediately when the method returns, the consumer has received all partitions or processed its first record. Connecting to brokers, joining the group, and completing partition assignment occur asynchronously under the Kafka protocol.

`start()` and `stop()` are lifecycle operations. They differ from `pause()` and `resume()`, which pause or resume fetching records while the container remains running. Choosing the right operation avoids triggering unnecessary rebalances when you only want to throttle traffic.

## 2. Default auto startup

Listener containers created for `@KafkaListener` typically start automatically when the Spring context starts. This is convenient for standard consumer applications: once the application is ready, consumers begin receiving records.

Defaults can be configured via Spring Boot:

```yaml
spring:
  kafka:
    listener:
      auto-startup: true
```

To defer all listeners, set `auto-startup: false`. Containers are then registered but do not automatically start when the context starts.

```yaml
spring:
  kafka:
    listener:
      auto-startup: false
```

You can override per listener using the `autoStartup` attribute on `@KafkaListener`:

```java
@KafkaListener(
        id = "order-events-listener",
        topics = "orders",
        groupId = "order-projection",
        autoStartup = "false")
public void handle(OrderEvent event) {
    orderProjectionService.apply(event);
}
```

The `id` attribute creates an identifier to look up the container in the registry. When the application needs individual control over each listener, assign a clear and unique ID in the registry. Because `autoStartup` is a string attribute, configuration placeholders such as `autoStartup = "${orders.listener.auto-startup:false}"` can be used, depending on version and property binding.

The default should match the application's lifecycle. If listeners can run as soon as the Spring context is ready, keeping auto-startup is usually simplest. If listeners may only receive records after migrations, warm-ups, or dependency checks complete, defer startup and trigger it explicitly after preparation steps.

## 3. Controlling containers via KafkaListenerEndpointRegistry

Containers created by `@KafkaListener` are managed by `KafkaListenerEndpointRegistry`. The registry is the appropriate entry point to locate a listener container by ID and invoke lifecycle operations.

Example service controlling a listener:

```java
@Service
public class ListenerLifecycleService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerLifecycleService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("order-events-listener");

        if (container == null) {
            throw new IllegalStateException("order-events-listener not found");
        }

        if (!container.isRunning()) {
            container.start();
        }
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("order-events-listener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
```

`getListenerContainer(id)` returns the matching container or `null` if the ID does not exist. Handle the missing-container case and avoid unnecessary repeated start/stop calls. `isRunning()` reports the container's lifecycle state; it does not assert that the consumer has been assigned partitions or is actively processing records.

To start a listener configured with `autoStartup = "false"`, call the service once dependencies are ready. Example:

```java
@Component
public class ListenerStartup implements ApplicationRunner {

    private final KafkaListenerEndpointRegistry registry;
    private final OrderDependencyReadiness readiness;

    public ListenerStartup(
            KafkaListenerEndpointRegistry registry,
            OrderDependencyReadiness readiness) {
        this.registry = registry;
        this.readiness = readiness;
    }

    @Override
    public void run(ApplicationArguments args) {
        readiness.awaitReady();

        MessageListenerContainer container =
                registry.getListenerContainer("order-events-listener");
        if (container != null && !container.isRunning()) {
            container.start();
        }
    }
}
```

`awaitReady()` is just an example of an application readiness wait mechanism. In real systems, use a readiness check with a timeout, log dependency states, and handle startup failures explicitly; do not wait indefinitely leaving the application in an indeterminate startup state.

## 4. Starting and stopping all listeners

The registry exposes the collection of containers it manages. When an operation needs to run across all listeners, iterate over this collection:

```java
@Service
public class AllListenersLifecycleService {

    private final KafkaListenerEndpointRegistry registry;

    public AllListenersLifecycleService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startAll() {
        registry.getListenerContainers().forEach(container -> {
            if (!container.isRunning()) {
                container.start();
            }
        });
    }

    public void stopAll() {
        registry.getListenerContainers().forEach(container -> {
            if (container.isRunning()) {
                container.stop();
            }
        });
    }
}
```

Use bulk operations only when listeners genuinely share the same lifecycle conditions. Many applications have listeners for different data streams; one listener may need to run immediately while another must wait on a dependency or feature flag. In such cases, controlling by ID is clearer.

Containers created by the registry are not necessarily individual beans in `ApplicationContext`. Therefore, do not assume every container can be injected directly as a Spring bean. For `@KafkaListener`, use the registry. If the application creates containers manually using `ConcurrentMessageListenerContainer`, manage their beans and lifecycles in a way that fits the application structure.

## 5. Controlled container shutdown

When `stop()` is called, the container halts consumption and closes the consumer. During stopping, the container must properly handle in-flight work and offset progress. Specific behavior depends on listener type, ack mode, polled record count, and stop settings.

You can use the callback overload to execute a follow-up step once the container has stopped:

```java
MessageListenerContainer container =
        registry.getListenerContainer("order-events-listener");

if (container != null && container.isRunning()) {
    container.stop(() -> log.info("Order listener has stopped completely"));
}
```

The callback is useful when an administrative workflow needs to wait for the container to finish before closing an auxiliary resource or marking maintenance mode. Do not assume the callback executes synchronously on the same thread calling `stop()`; container lifecycle may need to coordinate with consumer threads.

### Stopping after the current record or after the poll batch

In Spring Kafka versions supporting `ContainerProperties.stopImmediate`, you can adjust the point at which the container stops:

```java
factory.getContainerProperties().setStopImmediate(true);
```

With `stopImmediate = false` (the default in versions supporting this property), the container finishes processing remaining records from the poll before stopping. When set to `true`, the container stops after processing the current record. This setting affects shutdown duration and remaining records in a batch; verify exact semantics for your Spring Kafka version.

Do not confuse `stopImmediate` with skipping offset commits. Offsets are still managed according to the container's ack mode and commit mechanism. If records have not been acknowledged or committed when the container stops, they may be read again when the consumer group resumes. This is normal in an at-least-once model and must be handled safely with idempotency.

## 6. Spring ApplicationContext shutdown

Listener containers integrate with Spring's lifecycle. When the application context stops, Spring asks lifecycle beans to stop by phase. `KafkaListenerEndpointRegistry` manages containers created from `@KafkaListener`, so applications usually do not need custom hooks calling `stop()` on every listener just for standard shutdown.

Spring Boot can receive process/container shutdown signals and close `ApplicationContext`. `SmartLifecycle` beans are then stopped in phase order. If the application has dependencies that must close in a specific order, design phases and callbacks appropriately so listeners stop before the resources they use are closed.

For example, if a listener needs a database to finish the record it is processing, the database connection pool must remain active while the listener stops. Stopping the database first and the listener afterward can cause in-flight records to fail and be redelivered. Organize lifecycles so listeners stop before the database, while setting a shutdown timeout large enough for expected processing times.

Illustrative container configuration:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
orderListenerFactory(ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setShutdownTimeout(20_000L);
    factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}
```

`shutdownTimeout` controls how long the container waits for shutdown to complete in Spring Kafka versions with this property. Its value must align with processing times and the platform's termination grace period. If Kubernetes sends SIGTERM and gives the Pod only a short window before SIGKILL, timeouts inside the application must fit within that budget and leave time for Spring to close other beans.

A typical shutdown sequence:

1. The platform sends a stop signal to the process.
2. Spring Boot closes `ApplicationContext` and asks lifecycle beans to stop.
3. Listener containers stop taking new work and finish allowed in-flight work per stop configuration.
4. Containers commit offsets according to ack mode and confirmable processing state.
5. Consumers leave the group and close resources.
6. Other dependencies close in lifecycle phase order.

If the process is force-killed before completion, uncommitted records may be redelivered. No shutdown setting eliminates replay when a process dies abruptly; listeners should be safe when reprocessing records.

## 7. Lifecycle phase and startup ordering

Spring uses `SmartLifecycle` to control start/stop order of lifecycle-aware components. `phase` determines relative order: lower phases generally start earlier and stop later; higher phases start later and stop earlier. Listener containers have phases managed by registry/container properties depending on configuration and version.

If a listener needs an auxiliary service to start first, phases can be arranged so the dependency is ready before the listener begins. On shutdown, the reverse order lets the listener stop before the dependency. However, phase only orders lifecycle calls; it does not replace readiness checks. A bean may have started while its connection to an external system is not yet truly ready.

When startup depends on business conditions such as schema migration, feature flags, or preloaded caches, the most controllable approach is usually setting `autoStartup=false` on the listener and starting it explicitly once conditions are met. When simple bean ordering suffices, phases may be enough.

Do not change phases arbitrarily in an application with many `SmartLifecycle` beans. Identify real dependencies, document the desired order, and test both startup and shutdown directions.

## 8. Start/stop vs. pause/resume

`stop()` ends the consumer container lifecycle. When the container starts again, consumers rejoin the consumer group and may undergo a rebalance and new partition assignments. `pause()` only pauses fetching records while consumers remain active and retain group membership.

| Operation | Effect | When to use |
|---|---|---|
| `start()` | Starts consumer container and joins consumer group | Starting listener once application is ready |
| `stop()` | Stops consumer container and closes consumer | Shutdown, maintenance, or completely disabling a listener |
| `pause()` | Pauses consumption of assigned partitions; container stays running | Backpressure or temporarily halting incoming records |
| `resume()` | Resumes consumption after pause | Dependencies recovered or backpressure relieved |

Example pausing/resuming a container:

```java
MessageListenerContainer container =
        registry.getListenerContainer("order-events-listener");

if (container != null && container.isRunning()) {
    container.pause();
}

// When conditions allow processing to resume:
if (container != null && container.isRunning()) {
    container.resume();
}
```

Container pause is typically applied on the consumer thread via Spring Kafka's internal mechanism. Thus, calling `pause()` may only set a request; actual paused state takes effect on the next poll cycle. Observe pause/resume events or container status to confirm the change.

If you only need a temporary halt because the database is overloaded, pause/resume is usually preferable to stop/start. Stopping and restarting can cause consumers to leave the group and trigger rebalances, whereas pause keeps the container active. Conversely, when you need to release consumers and halt a listener long-term, stop is the right choice.

## 9. Tracking status with lifecycle events

Spring Kafka emits application events related to consumer and container lifecycle. Useful events include:

- `ConsumerStartingEvent`: consumer is about to be created/started.
- `ConsumerStartedEvent`: consumer has started.
- `ConsumerStoppingEvent`: consumer is stopping.
- `ConsumerStoppedEvent`: consumer has stopped; provides stop reason in supported versions.
- `ContainerStoppedEvent`: container has stopped.
- `ConsumerFailedToStartEvent`: consumer failed to start in versions supporting this event.

You can listen to events to log or update operational state:

```java
@Component
public class KafkaLifecycleEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaLifecycleEvents.class);

    @EventListener
    public void onConsumerStarted(ConsumerStartedEvent event) {
        log.info("Kafka consumer started: {}", event.getContainer());
    }

    @EventListener
    public void onConsumerStopped(ConsumerStoppedEvent event) {
        log.info("Kafka consumer stopped: {}", event.getReason());
    }

    @EventListener
    public void onContainerStopped(ContainerStoppedEvent event) {
        log.info("Kafka listener container stopped: {}", event.getSource());
    }
}
```

Specific event names and properties can vary between Spring Kafka versions; check the API of your version when writing event listeners. Consumer events are typically emitted per consumer thread, so a high-concurrency container can produce multiple start/stop events. Do not count each consumer event as a single start/stop of the whole container.

Event listeners should execute quickly. If lengthy administrative work is needed, offload it to an executor or appropriate coordinator instead of holding the event-publishing thread.

## 10. Running state does not mean ready to receive records

`container.isRunning()` reflects lifecycle state. It does not guarantee that the consumer has finished connecting to brokers, been assigned partitions, or processed records. In systems with strict readiness requirements, also monitor partition assignment and appropriate events.

Example using `ConsumerAwareRebalanceListener` to detect assigned partitions:

```java
factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {
            @Override
            public void onPartitionsAssigned(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {
                log.info("Assigned Kafka partitions: {}", partitions);
            }
        });
```

This is a consumer-level rebalance hook; it can be used to update readiness state if the application genuinely needs to know partition assignments. With multiple consumer threads, aggregate state across all relevant consumers. Being assigned partitions also does not mean downstream business dependencies are always ready.

For health/readiness probes, clearly define what state must be proven: application context running, listener container started, consumer assigned partitions, or downstream systems ready to process. Do not use a single `isRunning()` boolean to represent all these conditions.

## 11. Managing errors on start and restart

Startup can fail if brokers are unreachable, authentication is not ready, topics or metadata are unavailable, or consumer configuration is invalid. Inspect logs and lifecycle events to determine whether containers started cleanly or are repeatedly failing.

When a listener needs restarting after fixing a dependency, you can stop and start it again:

```java
public void restartOrdersListener() {
    MessageListenerContainer container =
            registry.getListenerContainer("order-events-listener");

    if (container == null) {
        throw new IllegalStateException("order-events-listener not found");
    }

    if (container.isRunning()) {
        container.stop();
    }

    container.start();
}
```

The snippet above illustrates the idea, but does not guarantee `stop()` has completed asynchronously before `start()` is invoked in all scenarios. For restarts requiring strict ordering, use `stop(Runnable callback)` and call `start()` from the callback or from a coordinator after confirming the container has stopped.

```java
public void restartOrdersListenerSafely() {
    MessageListenerContainer container =
            registry.getListenerContainer("order-events-listener");

    if (container == null) {
        throw new IllegalStateException("order-events-listener not found");
    }

    if (container.isRunning()) {
        container.stop(() -> {
            log.info("Listener stopped; restarting");
            container.start();
        });
    }
    else {
        container.start();
    }
}
```

In real applications, guard restarts against concurrent requests, record intermediate states, and set a timeout for the workflow. If start fails, report the state clearly rather than letting the system believe the listener is serving normally.

If a consumer stops due to processing or broker errors, restarting can cause uncommitted records to be read again. Listeners must be idempotent regarding side effects outside Kafka. Restarting does not erase committed offsets and does not automatically rewind the consumer to the beginning of the topic; resume position depends on committed offsets and `auto.offset.reset` when no valid offset exists.

## 12. Operating start/stop in production

Controlling listeners in production should have appropriate access controls, audit logs, and observable state. If exposing administrative endpoints to start/stop listeners, protect those endpoints with authentication/authorization and do not allow arbitrary users to alter consumer state.

A maintenance procedure can proceed as follows:

1. Identify the listener ID and affected partitions/topics.
2. Check consumer lag, in-flight records, and dependency health.
3. If only temporary load reduction is needed, pause the container and monitor pause state.
4. If a full stop is needed, call stop and wait for the callback confirming the container has stopped.
5. Perform the change or dependency maintenance.
6. Confirm dependencies are ready, then start the container.
7. Monitor partition assignment, consumer lag, listener errors, and processing rate after starting.

During full application shutdown, prefer letting Spring manage the lifecycle and allocate enough graceful shutdown time for listeners. Avoid calling `System.exit()` or killing the process before stop callbacks finish if the application needs to finish in-flight records.

Operational signals to monitor include:

- Number of running, stopped, or unexpectedly stopped listener containers.
- Time from start request to consumer partition assignment.
- Time from stop request to callback completion.
- Consumer group lag before and after maintenance.
- Rebalance count, broker connection errors, authentication errors, and listener errors.
- Number of records processed but uncommitted during shutdown or restart.

## 13. Common errors

### Container not found in registry

Verify `@KafkaListener` is registered, the ID spelling is exact, and the container was created in the current context. Set an explicit `id` rather than relying on auto-generated IDs when controlling from code.

### Calling start before Spring context is ready

Containers require factories, consumer factories, and dependencies to be configured. Perform lifecycle control after the context is appropriately initialized, such as via `ApplicationRunner`, `ApplicationReadyEvent`, or a dedicated coordinator.

### Calling stop and immediately calling start

If stopping has not completed, starting immediately can create a race condition during restart. Use a callback to restart after the container finishes stopping.

### Using stop when only wanting to pause consumption

Stop causes the consumer to leave the group and can trigger rebalances upon restart. For temporary backpressure, pause/resume is usually more suitable.

### Shutdown timeout too short

The container may lack enough time to finish processing or close consumers before the process is killed. Align Spring timeouts, platform termination grace period, and maximum processing time.

### Assuming start completion means partitions are assigned

Start is a lifecycle transition. Partition assignment happens afterward via the consumer group protocol. Use a rebalance listener or appropriate lifecycle event if readiness depends on assignment.

### Failing to handle redelivered records after restart

If offsets were not committed, records may be read again. Design side effects idempotently and do not treat a restart as proof that prior records had no effects.

## 14. Choosing a mechanism by requirement

| Requirement | Appropriate mechanism | Notes |
|---|---|---|
| Listener runs automatically on app startup | `autoStartup=true` | Common default behavior |
| Wait for migration or dependency before receiving records | `autoStartup=false` then call `start()` | Controllable via registry by listener ID |
| Stop listener during maintenance | `stop()` with callback | Wait for container to stop before next steps |
| Temporarily halt receiving records due to backpressure | `pause()` / `resume()` | Container maintains lifecycle |
| Ordered listener restart | `stop(Runnable)` then `start()` in callback | Avoids race between stop and start |
| Confirm listener has been assigned partitions | Rebalance listener or appropriate event | `isRunning()` is insufficient to prove assignment |
| Application shutdown | Spring lifecycle and graceful shutdown | Align timeouts with deployment platform |

Managing `start()` and `stop()` properly ensures listeners receive records only when dependencies are ready, stop cleanly for maintenance, and release consumers according to lifecycle. Use the registry to control `@KafkaListener`-created containers, distinguish stop from pause, wait for callbacks when strict ordering is required, and always design for safe handling of uncommitted records redelivered after restarts.
