# start, stop, and container management

In Spring Kafka, `@KafkaListener` does not directly run a poll loop. Spring creates a listener endpoint and a listener container to manage the Kafka consumer, poll records, invoke the listener method, handle acknowledgments, and close the consumer when stopping. When you need to enable/disable a data-receiving stream based on application state or operational conditions, you manage the lifecycle of the listener container.

For annotation-declared listeners, the central component is `KafkaListenerEndpointRegistry`. The registry holds listener containers created from `@KafkaListener` and lets you look up a container by `id` to invoke `start()`, `stop()`, `pause()`, or `resume()`. For containers declared directly as beans, you can inject the bean and manage its lifecycle through Spring.

Distinguish stopping a container from pausing consumption. `stop()` stops the container and closes the consumer per lifecycle rules; the consumer leaves the group and partitions may be assigned to other members. `pause()` temporarily stops receiving records while the consumer continues polling to maintain membership. Choosing the right operation avoids unnecessary rebalances and helps control incoming traffic.

This lesson belongs to the **Listener container** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, and mastering serialization, retries, dead-letter topics, transactions, exactly-once semantics, concurrency, and testing to run reliable messaging streams.

## 1. Listener containers in the Spring Kafka architecture

The listener container is the component that executes the listener. It creates consumers from `ConsumerFactory`, calls `poll()`, dispatches records to the listener method, and coordinates offset commits per configuration.

Two commonly used container types:

| Type | Role |
| --- | --- |
| `KafkaMessageListenerContainer` | Manages a single Kafka consumer and its corresponding listener processing loop. |
| `ConcurrentMessageListenerContainer` | Parent container managing multiple child containers/consumers according to concurrency. |

When using `@KafkaListener`, you typically do not instantiate these two container types yourself. `ConcurrentKafkaListenerContainerFactory` creates containers per configuration, while `KafkaListenerEndpointRegistry` registers and manages containers created from listener endpoints.

Relationship diagram:

~~~mermaid
flowchart TD
    A[ApplicationContext] --> B[@KafkaListener endpoint]
    B --> C[KafkaListenerEndpointRegistry]
    C --> D[Listener container]
    D --> E[ConsumerFactory]
    E --> F[Kafka Consumer]
    F --> G[Kafka Broker]
    D --> H[Listener method]
    H --> I[Business processing]
~~~

The registry manages containers by listener ID. The container manages consumers and the poll loop. The listener method focuses purely on processing received data.

## 2. Assigning an id to @KafkaListener

To find and control a specific listener, declare an explicit `id`:

~~~java
@Component
public class OrderEventListener {

    @KafkaListener(
        id = "orderListener",
        topics = "order-events",
        groupId = "order-service"
    )
    public void onOrderCreated(OrderCreated event) {
        orderService.handle(event);
    }
}
~~~

`id` is the endpoint identifier in Spring Kafka, used to look up the container in the registry. `groupId` is Kafka's consumer group identifier. These two values serve different purposes:

| Attribute | Meaning |
| --- | --- |
| `id` | Listener endpoint/container identifier inside the Spring application. |
| `groupId` | Consumer group name storing offsets and coordinating partitions in Kafka. |
| `clientIdPrefix` | Client ID prefix for consumers created for the listener, useful when monitoring multiple consumers. |

Do not pass groupId to `getListenerContainer()`. The registry looks up by listener ID.

If no explicit ID is declared, Spring Kafka may generate an ID from the endpoint via framework conventions. For listeners that need runtime control, setting a stable ID makes code easier to read, test, and keep independent of auto-generated IDs.

## 3. KafkaListenerEndpointRegistry

`KafkaListenerEndpointRegistry` is the registry managing listener containers created by endpoints such as `@KafkaListener`. Spring registers it in the application context when listener annotation processing is enabled.

You can inject the registry into an operational management service:

~~~java
@Service
@RequiredArgsConstructor
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public void startOrderListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orderListener");

        if (container != null && !container.isRunning()) {
            container.start();
        }
    }

    public void stopOrderListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orderListener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
~~~

`getListenerContainer(id)` returns the corresponding container, or null if the ID is not found. Handle the null case rather than assuming the listener always exists.

The registry also provides APIs to inspect registered containers, such as `getListenerContainers()`. When an application has multiple listeners, you can use the registry to manage them by ID or inspect the set of running containers.

Do not hold a container reference before listener endpoints have been registered if initialization code runs too early. The registry and containers are created during Spring context initialization; control logic must execute after endpoints are registered.

## 4. Automatic startup with autoStartup

By default, listener containers are configured to start automatically with Spring's lifecycle. You can control this with the `autoStartup` attribute on `@KafkaListener`:

~~~java
@KafkaListener(
    id = "orderListener",
    topics = "order-events",
    groupId = "order-service",
    autoStartup = "false"
)
public void onOrderCreated(OrderCreated event) {
    orderService.handle(event);
}
~~~

When `autoStartup = "false"`, the container does not start during normal startup. The application can start the listener once a condition is satisfied: dependencies are ready, business configuration has loaded, readiness checks pass, or an operator enables the stream.

`autoStartup` on the annotation is a String attribute, so property placeholders can be used. For instance, the value can be externalized in application.yml and referenced in the annotation. Verify how this configuration behaves in your Spring Kafka version.

~~~yaml
app:
  kafka:
    order-listener:
      auto-startup: false
~~~

~~~java
@KafkaListener(
    id = "orderListener",
    topics = "order-events",
    groupId = "order-service",
    autoStartup = "${app.kafka.order-listener.auto-startup:true}"
)
public void onOrderCreated(OrderCreated event) {
    orderService.handle(event);
}
~~~

With Spring Boot, you can also configure auto-startup at the listener container properties level for default containers. When individual listeners need separate control, the annotation attribute or a dedicated container factory configuration is clearer. Verify precedence between default configuration and endpoint-level values in your Spring Kafka version.

## 5. Starting a container on demand

When a container does not auto-start, the application can call `start()` after looking it up in the registry:

~~~java
@Service
@RequiredArgsConstructor
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public void start(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                "Listener not found: " + listenerId
            );
        }

        if (!container.isRunning()) {
            container.start();
        }
    }
}
~~~

`start()` asks the container to begin operating per its lifecycle. For a concurrent container, operating on the parent container manages its child containers and corresponding consumers.

After starting, the consumer must connect to brokers, join the consumer group, receive partition assignments, and start polling. Therefore, calling start does not mean the listener receives records at that exact instant. Completing group join and rebalance can take time.

If you need to confirm a listener is ready before opening another business flow, monitor container state and assignments via appropriate events/metrics instead of relying solely on start returning.

## 6. Stopping a container and completion callbacks

`stop()` stops the listener container. The container terminates consumer activity per its lifecycle, stops accepting new records, executes configured shutdown handling, and closes the consumer. The consumer leaves the group; Kafka may rebalance to redistribute partitions to remaining members.

You can call stop synchronously:

~~~java
container.stop();
~~~

Or use a callback to be notified when stopping completes:

~~~java
container.stop(() ->
    log.info("Order listener stopped")
);
~~~

Callbacks are useful when coordinating follow-up steps after the container completes shutdown. Do not assume all consumer shutdown work has finished immediately upon calling stop if you use the asynchronous overload with a callback.

When stopping, understand the impact on the consumer group. If a container stays stopped long enough, partitions are assigned to other consumers in the group. When restarted, the consumer rejoins the group, receives new assignments, and resumes from committed offsets per consumer policy.

## 7. How do pause and resume differ from stop/start?

Pause/resume fits when you want to temporarily halt record delivery while keeping the consumer in the group.

| Operation | Behavior | Group impact |
| --- | --- | --- |
| `start()` | Starts a stopped container. | Consumer joins group and receives assignments. |
| `stop()` | Stops container and closes consumer. | Consumer leaves group; may trigger rebalance. |
| `pause()` | Requests pausing record fetch/dispatch from partitions. | Consumer keeps polling to maintain membership. |
| `resume()` | Resumes receiving records after pause. | Consumer retains existing assignments if group has not changed. |

Example:

~~~java
public void pauseOrderListener() {
    MessageListenerContainer container =
        registry.getListenerContainer("orderListener");

    if (container != null && container.isRunning()) {
        container.pause();
    }
}

public void resumeOrderListener() {
    MessageListenerContainer container =
        registry.getListenerContainer("orderListener");

    if (container != null && container.isRunning()) {
        container.resume();
    }
}
~~~

Pause is typically suitable when a downstream database is overloaded or the application needs short-term intake throttling. The consumer keeps polling without fetching additional records from paused partitions under container mechanics. This maintains membership and avoids rebalances caused by frequent stop/start cycles.

Pause does not mean the listener has already finished every record in the current batch or currently being dispatched. Understand when pause takes effect across poll cycles and container configurations for your version.

### 7.1. Checking pause state

Containers expose APIs to inspect pause state. Depending on Spring Kafka version, methods such as `isPauseRequested()` and `isContainerPaused()` distinguish whether a pause has been requested from whether the consumer has actually paused.

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orderListener");

if (container != null) {
    log.info(
        "running={}, pauseRequested={}, paused={}",
        container.isRunning(),
        container.isPauseRequested(),
        container.isContainerPaused()
    );
}
~~~

`isPauseRequested()` reflects the pause request. `isContainerPaused()` reflects the pause state already applied by the container. Because pause coordinates with the consumer's poll loop, the two states may not transition simultaneously.

## 8. Per-partition pause/resume

Beyond pausing the entire container, some container types support pausing/resuming individual topic-partitions. This is useful when one partition has an issue while other partitions can continue processing.

~~~java
TopicPartition partition = new TopicPartition("order-events", 2);

MessageListenerContainer container =
    registry.getListenerContainer("orderListener");

if (container != null) {
    container.pausePartition(partition);
}
~~~

Resuming a partition:

~~~java
if (container != null) {
    container.resumePartition(partition);
}
~~~

Exact APIs and availability depend on container type and Spring Kafka version. Verify whether the partition is actually assigned to that container. If the partition is not part of the current assignment, pausing it may not take effect as expected.

Pausing a partition does not move that partition to another consumer in the same group. It only pauses processing on the consumer owning that partition. Shifting ownership requires a rebalance or membership/assignment change.

## 9. Managing multiple listeners with the registry

An application may have multiple listeners for different domains:

~~~java
@KafkaListener(
    id = "orderListener",
    topics = "order-events",
    groupId = "order-service"
)
public void onOrder(OrderEvent event) {
    orderService.handle(event);
}

@KafkaListener(
    id = "paymentListener",
    topics = "payment-events",
    groupId = "payment-service"
)
public void onPayment(PaymentEvent event) {
    paymentService.handle(event);
}
~~~

They can be controlled individually:

~~~java
public void stopPaymentOnly() {
    MessageListenerContainer paymentContainer =
        registry.getListenerContainer("paymentListener");

    if (paymentContainer != null && paymentContainer.isRunning()) {
        paymentContainer.stop();
    }
}
~~~

Using distinct IDs avoids impacting unrelated listeners. Never stop all containers just because one stream encounters an issue if the remaining streams continue functioning normally.

When group control is needed, you can iterate containers in the registry and filter by ID convention or application metadata. Build a clear management layer rather than letting HTTP controllers access the registry directly.

## 10. Spring lifecycle and SmartLifecycle

Listener containers participate in Spring's lifecycle. When the application context starts, lifecycle components start in phase order; when the context stops, they stop in the corresponding lifecycle order.

Spring Kafka containers integrate lifecycle hooks to coordinate start/stop and callbacks. You can configure `phase` via container properties or the factory when ordering with other components is required.

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setPhase(100);
    return factory;
}
~~~

The phase value is only an example. Choose phase based on dependency ordering: listeners should start after required components are ready and stop before dependencies they rely on are closed.

Spring uses SmartLifecycle to coordinate start/stop and callbacks. For applications with multiple interdependent components, understand phase and shutdown timeout instead of calling start/stop uncoordinated across multiple places.

Do not abuse phase as a replacement for readiness checks. Phase controls lifecycle ordering; it does not prove a database, remote service, or Kafka broker is ready for business traffic.

## 11. Graceful shutdown when the application stops

When the application context closes, Spring stops listener containers per lifecycle order. Containers must close consumers cleanly to avoid interrupting in-flight processing.

Factors to consider:

- Maximum time a listener takes to process a record or batch.
- Time allotted to the container to stop.
- Offset commit timing.
- Active retries/backoff.
- Whether the consumer participates in Kafka transactions.
- Whether downstream dependencies remain available while the listener stops.

With Spring Boot, you can configure graceful shutdown timeouts at the application level:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

`server.shutdown` primarily controls graceful shutdown of the web server. `spring.lifecycle.timeout-per-shutdown-phase` sets a bound for each Spring lifecycle phase. This is not an independent guarantee that every listener invocation finishes within 30 seconds; compare container timeouts against actual processing times.

When deploying on Kubernetes or another orchestrator, the termination grace period must be long enough for Spring to complete shutdown. If the orchestrator kills the process before the lifecycle finishes, listeners can be terminated abruptly and uncommitted records may be re-read.

### 11.1. Offset commits during shutdown

If a listener finishes processing successfully but offsets have not committed before the process stops, records may be re-read when another consumer takes over the partition. This is standard at-least-once behavior.

If offsets commit before business work finishes, processing can be lost when the process stops. Shutdown must therefore coordinate with ack mode, error handlers, and transactions; do not just raise timeouts while ignoring commit semantics.

Listeners should be idempotent whenever business logic can receive redelivered records. Stopping containers cleanly lowers risk, but cannot eliminate all duplicate possibilities from crashes, network failures, or rebalances.

## 12. Dynamic listener registration

In some applications, the list of listeners is not fully known at compile time. Spring Kafka provides APIs to register endpoints/containers programmatically via the registry and listener container factory.

This is an advanced scenario. Before choosing it, check whether a single listener can subscribe to multiple topics or use `topicPattern`. Dynamic endpoints add complexity to lifecycles, IDs, configuration, and observability.

When registering dynamically, ensure:

- Every endpoint has a unique ID.
- ConsumerFactory and container factory match key/value types.
- Subscriptions/topics are validated properly.
- Auto-startup policy is explicitly chosen.
- Containers start/stop cleanly with the application lifecycle.
- A mechanism exists to stop/remove containers when listener configurations become obsolete.

Never create a new container per incoming request. A listener container is a long-lived resource, not a per-HTTP-request temporary object.

## 13. Controlling listeners via admin APIs

Some systems expose internal APIs to operate listeners, such as pausing a consumer during downstream maintenance. If building such an API, protect access permissions and restrict which listener IDs can be controlled.

Example control service:

~~~java
@Service
@RequiredArgsConstructor
public class ListenerOperations {

    private final KafkaListenerEndpointRegistry registry;

    public void pause(String id) {
        MessageListenerContainer container = requireContainer(id);
        if (container.isRunning()) {
            container.pause();
        }
    }

    public void resume(String id) {
        MessageListenerContainer container = requireContainer(id);
        if (container.isRunning()) {
            container.resume();
        }
    }

    public void start(String id) {
        MessageListenerContainer container = requireContainer(id);
        if (!container.isRunning()) {
            container.start();
        }
    }

    public void stop(String id) {
        MessageListenerContainer container = requireContainer(id);
        if (container.isRunning()) {
            container.stop();
        }
    }

    private MessageListenerContainer requireContainer(String id) {
        MessageListenerContainer container =
            registry.getListenerContainer(id);

        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener id: " + id
            );
        }

        return container;
    }
}
~~~

This service illustrates consolidating lifecycle operations in one place. A controller can call this service after verifying administrative authorization. Never expose unauthenticated start/stop endpoints to the internet or allow callers to pass arbitrary IDs unchecked.

Return the actual container state after the operation and write audit logs: who executed it, which listener, when, why, and the outcome. For pause operations, you may need to wait until the container is actually paused before reporting completion.

## 14. Testing start, stop, pause, and resume

Lifecycle behavior should be tested at the container/integration level rather than only verifying that a service invoked a method.

Scenarios to verify:

1. A listener with autoStartup=false receives no records before start.
2. Calling start causes the listener to join the group and receive records.
3. Calling pause temporarily stops receiving new records per container semantics.
4. Calling resume resumes processing.
5. Calling stop halts the container and closes the consumer.
6. The container can be restarted after stop.
7. Stopping the context triggers lifecycle shutdown.
8. With concurrency, child containers are managed properly.

You can use Embedded Kafka or Testcontainers to run a broker in integration tests. Tests should use latches or bounded wait conditions rather than fixed sleeps.

Example verifying a container is not running when autoStartup=false:

~~~java
@SpringBootTest
@EmbeddedKafka(topics = "order-events", partitions = 1)
class ListenerLifecycleTest {

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @Test
    void listenerCanBeStartedAndStopped() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderListener");

        assertThat(container).isNotNull();
        assertThat(container.isRunning()).isFalse();

        container.start();
        await().atMost(Duration.ofSeconds(10))
            .until(container::isRunning);

        container.stop();
        await().atMost(Duration.ofSeconds(10))
            .until(() -> !container.isRunning());
    }
}
~~~

The example uses Awaitility to wait on state transitions. A real test must configure the listener with autoStartup=false and set up required dependencies/test config. `isRunning` does not imply partition assignment has finished; if a test must confirm the consumer is ready to receive records, wait for assignment or use a probe record.

## 15. Common errors when managing containers

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| getListenerContainer returns null | Wrong ID or endpoint not registered yet | Check id on @KafkaListener and when the registry is queried |
| Called start but no records arrive yet | Consumer is connecting, joining group, rebalancing, or topic has no data | Check group state, assignment, topic, and offset |
| Container starts automatically despite wanting manual startup | autoStartup is still true or endpoint config overrides default | Check annotation and listener container factory |
| Stop triggers rebalance | Consumer left the group and partitions were reassigned | Normal group membership behavior |
| After pause, listener still processes a few records | Pause may take effect on the next poll cycle or in-flight batch | Check pause state and container/version semantics |
| Long pause evicts consumer from group | Consumer stopped polling or broker/network unstable | Check heartbeats, poll loop, and consumer logs |
| Stop does not finish before process is killed | Shutdown timeout or termination grace period too short | Check lifecycle timeouts, listener duration, and orchestrator |
| Restarting receives old records | Offset was not committed before stopping | Check ack mode, commits, and idempotency |
| Controlling the wrong listener | Used groupId instead of listener id, or duplicate IDs | Assign unique listener IDs and look up by ID in registry |
| Raising concurrency does not raise throughput | Too few partitions or downstream saturated | Check assignments, partition count, and dependencies |

## 16. Listener container operations checklist

Before deploying container management to production, verify:

1. Every controllable listener has a stable, unique ID.
2. Appropriate autoStartup setting is chosen for each listener.
3. The registry is injected and used only after endpoints are registered.
4. Management service handles missing container cases.
5. Stop/start is clearly distinguished from pause/resume.
6. Rebalance impact when consumers leave the group is understood.
7. Pause state and when pause takes effect have been verified.
8. Graceful shutdown and termination grace period are configured appropriately.
9. Ack mode, retries, and transactions are compatible with the shutdown procedure.
10. Lifecycle operations emit metrics, logs, and audit trails.
11. Listener control APIs are protected with authorization.
12. Integration tests verify start, stop, pause, resume, and shutdown.

Managing listener containers is how you control consumer lifecycles at the Spring layer. The registry lets you locate the right container by listener ID; start/stop changes consumer membership and lifecycle; pause/resume throttles intake while keeping the consumer active. When properly coordinated with offsets, acknowledgments, rebalances, and graceful shutdown, applications can operate Kafka streams flexibly while keeping processing progress observable and recoverable.

