# ConsumerStartedEvent

In Spring Kafka, the listener container manages the lifecycle of one or more Kafka consumers: initializing the client, joining the consumer group, calling `poll()`, invoking the listener method, managing offsets, and closing resources on stop. In addition to processing records, the framework publishes **application events** so the application can observe key lifecycle transitions.

**`ConsumerStartedEvent`** is a Spring Kafka event indicating that a Kafka consumer managed by a listener container has entered the active state after its startup phase. An application can receive this event via Spring `@EventListener` or `ApplicationListener<ConsumerStartedEvent>` to write logs, measure startup duration, track the number of operating consumers, or coordinate health signals.

Key point: **`ConsumerStartedEvent` does not guarantee that the consumer has been assigned partitions, has read its first record, has caught up on lag, or has successfully processed business logic**. It is an **in-JVM** lifecycle signal, not a Kafka record, and it does not replace checking readiness, partition assignment, or business progress.

## 1. Where does ConsumerStartedEvent sit in the workflow?

Example of a listener receiving order creation events:

~~~java
@Component
public class OrderCreatedListener {

    private final OrderService orderService;

    public OrderCreatedListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "orders-created-listener",
            groupId = "orders-service",
            topics = "orders.created")
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

Spring Kafka creates a listener container for the `orders-created-listener` endpoint. The container starts the consumer, the consumer joins the group, and it begins fetching records from the broker.

~~~text
ApplicationContext starts
            |
            v
KafkaListenerEndpointRegistry starts container
            |
            v
Kafka consumer thread created/started
            |
            v
ConsumerStartingEvent (starting phase)
            |
            v
ConsumerStartedEvent (consumer started)
            |
            v
poll / group coordination / partition assignment
            |
            v
Receive record -> invoke @KafkaListener -> ack/commit
~~~

The diagram is intended to separate the **startup lifecycle** from the subsequent Kafka work. The exact ordering between consumer initialization, the first `poll()`, and certain callbacks can depend on implementation/version. Do not use the diagram to assert that the moment `ConsumerStartedEvent` is published, partition assignment is already stable or the consumer has already received data.

The event is published into the **Spring application event infrastructure**. It is only received by beans/event listeners registered within the application that published the event.

## 2. What does the event indicate and what does it not indicate?

`ConsumerStartedEvent` is useful when you want to answer the question: "Has the consumer thread managed by the container started operating?"

| Can be used as a signal | Cannot be concluded from the event alone |
|---|---|
| A consumer has passed the startup step managed by Spring Kafka | Broker has already assigned partitions. |
| Record the start milestone in the lifecycle | First record has already been read. |
| Start measuring time until assignment/first record | Kafka broker and all dependencies are healthy. |
| Increment a consumer start count metric | Consumer is still running at a later observation time. |
| Correlate with stop and restart events | New offsets have been committed or backlog is cleared. |
| Analyze abnormal startup when the event is missing | Absence of the event means the broker is definitely failing. |

A consumer may start successfully yet receive no partition assignment because there are **more consumers than partitions** in the group. It may also start and then encounter authentication, deserialization, or network errors, or be stopped. Therefore, do not set `applicationReady=true` solely based on receiving a `ConsumerStartedEvent`.

Conversely, a consumer failing to deliver the event to an observer because the event listener was not registered, the multicaster did not behave as expected, or the JVM stopped early does not mean the consumer definitely never ran.

## 3. Receiving ConsumerStartedEvent with @EventListener

The event class resides in Spring Kafka's package:

~~~java
import org.springframework.kafka.event.ConsumerStartedEvent;
~~~

A simple observer:

~~~java
package com.example.kafka.monitoring;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStartedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerLifecycleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerLifecycleObserver.class);

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        log.info("Kafka consumer started, source={}, container={}",
                event.getSource(), event.getContainer());
    }
}
~~~

Spring invokes the method when an application event of type `ConsumerStartedEvent` is published. This example only logs the lifecycle; it does not call `KafkaConsumer` APIs and does not interfere with offset positions.

`getSource()` is inherited from Spring's `ApplicationEvent`, whereas `getContainer()` is provided by the Kafka events hierarchy to associate the event with a container. The concrete identifier/object depends on container type and framework version. When logging, use explicitly supported container metadata rather than parsing `toString()` output.

### 3.1. Using ApplicationListener

If you need to implement an interface instead of using an annotation:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ConsumerStartedEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerStartListener
        implements ApplicationListener<ConsumerStartedEvent> {

    @Override
    public void onApplicationEvent(ConsumerStartedEvent event) {
        lifecycleMetrics.markConsumerStarted(event);
    }
}
~~~

Both forms use Spring's application event mechanism. You only need one form per observation task; do not declare two listeners incrementing the same counter unless intended.

### 3.2. Safe observer when monitoring fails

An event handler dedicated solely to monitoring should not break the lifecycle because the telemetry system is unavailable:

~~~java
@EventListener
public void onConsumerStarted(ConsumerStartedEvent event) {
    try {
        lifecycleMetrics.markConsumerStarted(event);
    } catch (RuntimeException exception) {
        log.warn("Could not record consumer start event", exception);
    }
}
~~~

This is an error-isolation mechanism for **monitoring**. Do not apply similar exception swallowing to business-processing `@KafkaListener` methods; exceptions in listeners may need to flow through an error handler, retry, or transaction rollback.

## 4. Finding the associated container and listener ID

A Spring Boot service can run multiple Kafka listeners:

~~~text
orders-created-listener
payments-confirmed-listener
inventory-adjusted-listener
~~~

If all `ConsumerStartedEvent` instances are received by a shared observer, you need to distinguish which listener owns the consumer that just started.

Example checking the container type:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStartedEvent;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerStartMetrics {

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        Object containerObject = event.getContainer();

        if (containerObject instanceof MessageListenerContainer container) {
            String listenerId = container.getListenerId();
            recordStart(listenerId);
        }
    }

    private void recordStart(String listenerId) {
        // Example: record counter by stable listener ID.
    }
}
~~~

With `ConcurrentMessageListenerContainer`, `getContainer()` and `getSource()` may refer to the parent or child depending on the event type. If you need to distinguish individual child consumers from the parent listener, verify how your framework version identifies them with an integration test rather than relying on `source.toString()`.

IDs to distinguish:

| ID | Meaning |
|---|---|
| `@KafkaListener(id = "...")` | Identifies the listener endpoint/container in the Spring registry. |
| `groupId` | Consumer group that distributes partitions and stores committed offsets. |
| `client.id` / client ID prefix | Identifies the Kafka client, often useful for logs and JMX/metrics. |
| Instance/Pod ID | Deployment process hosting the listener. |
| Child consumer container ID | Identifies one consumer thread when using concurrency. |

These IDs may have similar-looking values but do not serve the same role. Use stable IDs with appropriate cardinality for metric labels; use detailed client/instance IDs in structured logs when investigating.

## 5. ConsumerStartedEvent in a concurrent container

`ConcurrentKafkaListenerContainerFactory` can create a listener container with multiple consumer threads:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated> orderFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
~~~

Listener using the factory:

~~~java
@KafkaListener(
        id = "orders-created-listener",
        groupId = "orders-service",
        topics = "orders.created",
        containerFactory = "orderFactory")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Structure:

~~~text
ConcurrentMessageListenerContainer
            |
            +---- child consumer container 0
            +---- child consumer container 1
            +---- child consumer container 2
~~~

With concurrency equal to three, there can be **multiple `ConsumerStartedEvent` instances for the same logical listener endpoint**, corresponding to the started consumer threads. Consumer-level events do not necessarily match the number of listener methods or application replicas.

For example, a topic has only two partitions while listener concurrency is three:

- Three consumers can start.
- At most two consumers receive partitions of the topic in the same consumer group if no other topics are subscribed.
- One consumer may not be assigned any partitions even though it published `ConsumerStartedEvent`.
- Increasing concurrency beyond the partition count does not allow a single partition to be processed concurrently by multiple consumer members in the same group.

**Do not use the count of start events to infer the number of owned partitions.** You need consumer assignment metrics/callbacks to determine partition ownership.

### 5.1. Counting restarts without double-counting

A consumer can start, stop, and start again due to operational actions. If using a counter, each new event can increment the start count. If using a gauge for "number of running consumers", you must combine start and stop events and have a reconciliation mechanism in case events are missed.

Example:

~~~text
t0: child-0 started  -> start counter = 1
t1: child-1 started  -> start counter = 2
t2: child-1 stopped  -> active consumer count needs to decrease
t3: child-1 started  -> start counter = 3
~~~

A "start attempts observed" counter and a "current active consumers" gauge are **two different metrics**. Simply accumulating `ConsumerStartedEvent` and calling the result the active consumer count will be wrong after restarts or shutdowns.

## 6. Distinguishing ConsumerStartingEvent, ConsumerStartedEvent, and ConsumerStoppedEvent

Spring Kafka provides application events describing different steps in the consumer lifecycle.

| Event | General meaning | Usage scenario |
|---|---|---|
| `ConsumerStartingEvent` | Consumer is entering the startup process. | Mark the beginning of startup, measure latency. |
| **`ConsumerStartedEvent`** | Consumer has started at the lifecycle level. | Record that the consumer thread has started running. |
| `ConsumerFailedToStartEvent` | Consumer failed to start within the conditions/timeout monitored by the container. | Investigate startup failure. |
| `ConsumerStoppingEvent` | Consumer is beginning to stop. | Measure stop duration, observe shutdown. |
| `ConsumerStoppedEvent` | Consumer has stopped, possibly with a reason. | Distinguish normal stop from abnormal stop. |
| `ContainerStoppedEvent` | Listener container has stopped. | Observe container/endpoint-level lifecycle. |
| `ListenerContainerIdleEvent` | Listener received no records within the idle threshold. | Track inactivity, not a startup failure. |
| `NonResponsiveConsumerEvent` | Container detects that the consumer is not meeting progress/poll criteria. | Diagnose blocked consumer or slow processing. |

The event list and APIs for retrieving reason/container may differ by Spring Kafka version. Do not assume every event in the table is always published under all configurations.

### 6.1. "Started" does not mean "running forever"

`ConsumerStartedEvent` is a **point-in-time event**. The consumer can stop right afterward due to a broker auth failure, application shutdown, producer fencing, or other errors.

If you need the current state, combine it with `ConsumerStoppedEvent`, container `isRunning()`, and consumer group/lag metrics. A historical start event is not a continuous health check.

### 6.2. "Started" does not mean "assigned"

The consumer joins the group and receives partitions after the thread has started. If you want to measure assignment, use `ConsumerRebalanceListener` or `ConsumerAwareRebalanceListener` / appropriate container assignment APIs.

~~~text
Consumer thread started
          |
          v
Kafka poll() / join group
          |
          v
Partition assignment
          |
          v
Fetch records
          |
          v
Business processing
~~~

These are separate milestones. The startup event indicates the first milestone and cannot substitute for later milestones.

## 7. Tracking partition assignment properly

If the application should only be considered "ready to process" when it owns at least one partition, `ConsumerStartedEvent` is not enough. You can observe assignment via a rebalance callback:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String> myListenerFactory(
        ConsumerFactory<String, String> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setConsumerRebalanceListener(
            new ConsumerAwareRebalanceListener() {
                @Override
                public void onPartitionsAssigned(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {
                    assignmentObserver.recordAssigned(partitions);
                }

                @Override
                public void onPartitionsRevokedBeforeCommit(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {
                    assignmentObserver.recordRevoked(partitions);
                }
            });

    return factory;
}
~~~

The example illustrates receiving assignment/revocation; supported callback interfaces and overrides depend on the Spring Kafka version. If the listener has high concurrency, the observer should associate assignments with the **specific consumer member/container**, rather than writing a global list and assuming it represents the entire group.

Rebalance callbacks can run on the consumer thread. Do not perform long blocking HTTP/DB operations, do not share `KafkaConsumer` across threads, and do not modify assignments outside the callback contract.

An application may own no partitions at a given moment and still be completely healthy if the Kafka group has more consumers than partitions. Therefore, the "has at least one assignment" readiness condition also needs to be tailored to the topology.

## 8. Measuring startup latency with lifecycle events

You can use the `ConsumerStarting` and `ConsumerStarted` milestones to measure the time it takes the framework to bring a consumer thread to the started state.

Example milestones:

~~~text
T0: container.start() called
T1: ConsumerStartingEvent
T2: ConsumerStartedEvent
T3: partitions assigned
T4: first record received
T5: first record processed successfully
~~~

The intervals have different meanings:

- **T2 - T1:** consumer lifecycle startup phase.
- **T3 - T2:** time to assignment, depending on Kafka group coordination.
- **T4 - T3:** time to first record, depending on whether the topic has data.
- **T5 - T4:** first business processing duration.

Measuring only up to T2 and calling it "ready to process records" can be misleading. The consumer might not have an assignment yet, or the topic might have no records.

To compute latency accurately in a concurrent container, correlate events by the **same child consumer**; do not subtract child B's `ConsumerStartedEvent` from child A's `ConsumerStartingEvent`.

### 8.1. Do not use wall clock for every measurement

In Java, when measuring duration within the same process, `System.nanoTime()` is more suitable than `System.currentTimeMillis()` because it is a monotonic clock for elapsed time measurement. When correlating with logs from other processes, UTC timestamps remain useful, but clock skew between machines can distort wall-clock measurements.

The application can keep a temporary map keyed by consumer identity to measure startup duration. The map must remove entries when a consumer stops or fails startup to avoid memory leaks during repeated instance restarts.

## 9. On which thread does the application event handler run?

Spring application events are dispatched through `ApplicationEventMulticaster`. Under the default synchronous configuration, the event handler usually runs on **the thread that published the event**. For Spring Kafka listener lifecycles, this may be the consumer/container thread.

If the application configures `SimpleApplicationEventMulticaster` with an executor, event handlers can run asynchronously. In that case, processing order and thread ownership may differ.

Therefore, an `@EventListener` receiving `ConsumerStartedEvent` should:

- Do minimal work and return quickly.
- Only log, record metrics, or update lightweight in-memory state.
- Avoid HTTP requests without timeouts or long database queries.
- Not call `poll()`, `commitSync()`, `seek()`, or `close()` on `KafkaConsumer` from an arbitrary thread.
- Not call `container.stop()` and wait synchronously in a way that can block the very consumer that is starting.
- Not assume the event listener runs on a separate thread to perform heavy work.

`KafkaConsumer` is not thread-safe for ordinary operations. Features that need to operate on the consumer should use callbacks/manager APIs supported by Spring Kafka and run on the proper thread.

### 9.1. If asynchronous work is needed

An observer can push a lightweight notification to an internal structure for another worker to handle:

~~~java
@EventListener
public void onStarted(ConsumerStartedEvent event) {
    lifecycleQueue.offer(new ConsumerLifecycleMarker(
            "CONSUMER_STARTED",
            System.currentTimeMillis()));
}
~~~

This is a conceptual example with `lifecycleQueue` and `ConsumerLifecycleMarker` defined by the application. It does **not** mean you should spawn a separate thread per event, nor does it guarantee that the notification is durably persisted.

If a lifecycle signal is the prerequisite for performing a mandatory operation, use an appropriate durable storage/coordination mechanism rather than relying on an in-memory queue that can be lost if the JVM crashes.

## 10. ConsumerStartedEvent and autoStartup

A `@KafkaListener` is usually started when the application context starts, depending on container/registry configuration. If you need to delay startup until a dependency is ready, you can use `autoStartup = "false"`.

Example:

~~~java
@KafkaListener(
        id = "orders-created-listener",
        groupId = "orders-service",
        topics = "orders.created",
        autoStartup = "false")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

After the application has started and dependency checks are complete, you can retrieve the container from the registry and call `start()`:

~~~java
@Service
public class OrdersConsumerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersConsumerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean startOrdersConsumer() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-created-listener");

        if (container == null) {
            return false;
        }

        if (!container.isRunning()) {
            container.start();
        }
        return true;
    }
}
~~~

`start()` is a request to begin the lifecycle; do not assume that partition assignment or record processing has already happened before the method returns.

With a `ConsumerStartedEvent` observer, the application can record when the consumer actually passes the startup step after this request. Still, do not use the event to replace callbacks/metrics for the "partitions assigned" step.

### 10.1. Dependency-gated startup

For example, the system must load a schema/cache or verify database migrations before receiving Kafka events. You can use startup orchestration with `autoStartup=false`, calling start once dependencies are ready.

However, avoid letting an "unready dependency" leave the application waiting indefinitely. Set timeouts, retry policies, and alerts. If other instances are processing the same consumer group, while this listener has not started, the broker can distribute partitions to the other members.

## 11. ConsumerStartedEvent and Spring Boot readiness

Do not naively write:

~~~text
If ConsumerStartedEvent received:
    readiness = UP
~~~

This only proves that a start event occurred. A worker can start its consumer yet fail to connect to the broker, receive no assignment, or fail to process records due to a downstream database outage.

For an application with multiple listeners, readiness should explicitly consider which listeners are mandatory:

| Scenario | Appropriate evaluation |
|---|---|
| A critical listener must run | Combine container state with error/assignment monitoring. |
| Consumer group has more members than partitions | Do not treat an idle member as an automatic failure. |
| An optional listener stops | May only warn without bringing down overall readiness. |
| Broker unavailable | Monitor Kafka client/group health and poll progress. |
| Downstream DB failure | Business processing SLO/health checks the DB, independent of startup events. |

**Liveness** also differs from readiness. If a consumer has not received a start event because the broker is slow, do not repeatedly restart the JVM on an unfounded condition; restart loops can cause more group rebalances and slow down recovery.

Spring Boot `ApplicationReadyEvent` indicates that the application completed Boot-level startup, which does not mean each Kafka consumer has been assigned partitions or completed business processing.

## 12. ConsumerStartedEvent and partition count

The number of running consumers and the topic's partition count establish the limit for parallel processing.

Example:

~~~text
Topic orders.created has 4 partitions
Group orders-service has 6 consumers

Consumer A -> p0
Consumer B -> p1
Consumer C -> p2
Consumer D -> p3
Consumer E -> no assignment
Consumer F -> no assignment
~~~

Both E and F may have started their consumer threads even though they have no partitions to process in the current group.

When increasing `concurrency` or scaling replicas, the number of `ConsumerStartedEvent` instances may rise while throughput stays flat if the partition count limit is already reached. Conversely, a hot partition can build lag even when all consumers report started.

Therefore, production metrics should separate:

- Consumer thread starts.
- Active/assigned partitions.
- Records consumed per member/partition.
- Processing latency and error rate.
- Consumer lag per partition.
- Rebalance rate/duration.

## 13. Start event is not a Kafka broker event

A Kafka broker does not know about or publish `ConsumerStartedEvent` to the application. It is a **Spring Kafka event**, pushed by the listener container into the Spring application event mechanism.

Consequences:

- Another microservice does not automatically receive this event over Kafka.
- There is no Kafka topic, partition, or offset for lifecycle events.
- `ConsumerStartedEvent` cannot be replayed after a JVM crash.
- An application event listener may not be invoked if the bean is not registered or the context fails before publishing the event.
- If cross-process auditing is required, you must proactively export metrics/logs or publish a separate domain event with appropriate semantics and durability.

Do not publish a "consumer started" Kafka record inside the `@EventListener` itself and treat it as an absolute durable signal. If the producer is not ready or the broker is unreachable at startup, publishing may fail; this also complicates the lifecycle.

## 14. Start, stop, and restart

Lifecycle cycles can occur as follows:

~~~text
Container START
     |
     +---- ConsumerStartingEvent
     +---- ConsumerStartedEvent
     |
     v
RUNNING -> poll / process / commit
     |
     v
Container STOP
     |
     +---- ConsumerStoppingEvent
     +---- ConsumerStoppedEvent
     +---- ContainerStoppedEvent (depending on container lifecycle)
     |
     v
STOPPED
     |
     +---- restart, new consumer thread
     +---- ConsumerStartedEvent may appear again
~~~

Stop/start events do not necessarily appear in the same strict order in every concurrent container and event multicaster scenario; the diagram only illustrates the main stages.

If the application uses manual start/stop, check both `isRunning()` state and callback signals (if needed). A new consumer thread may be created after a restart, even when the logical listener ID remains unchanged.

A consumer can die abruptly or the JVM can be hard-killed, so you cannot rely on having matched started/stopped event pairs to deduce the active consumer count in production. Gauges should be reconciled with current container state or broker/client metrics.

## 15. When ConsumerStartedEvent does not appear

When a listener does not run and the observer sees no start event, do not jump to a conclusion immediately. Investigate by layers:

1. **Is the listener registered?** Check `@EnableKafka`/Spring Boot autoconfiguration, component scanning, `KafkaListenerEndpointRegistry`.
2. **Is auto-start enabled?** Check `autoStartup` and lifecycle phase.
3. **Was the container asked to start?** If `autoStartup=false`, code or an admin action must call start.
4. **Is the factory/consumer config valid?** Check bootstrap servers, serializer/deserializer, group ID, topic.
5. **Did the consumer fail at startup?** Look for `ConsumerFailedToStartEvent`, Kafka client logs, and exceptions.
6. **Is the observer registered?** `@EventListener` must reside in a bean belonging to the application context receiving the event.
7. **Was the event multicaster customized?** Check async handling, executor shutdown, or failing event listeners.
8. **Are there enough partitions?** Insufficient partitions do not directly explain the absence of a start event, but they can prevent the consumer from processing records.
9. **Did the consumer start and then stop very quickly?** Cross-check `ConsumerStoppedEvent` and container logs.
10. **Was the context/pod stopped before starting?** Check Spring Boot startup failures and orchestrator logs.

When a consumer receives no records even though `ConsumerStartedEvent` appears, investigate partition assignment, group state, lag, and whether the topic has data before assuming listener logic is broken.

## 16. Monitoring and metric design

A useful structured log:

~~~text
event_type=ConsumerStartedEvent
service=orders-worker
listener_id=orders-created-listener
instance_id=orders-worker-3
consumer_start_time=2026-11-15T17:00:00Z
~~~

`consumer_start_time`, `service`, and `instance_id` are fields added by the application/telemetry, **not** all built-in properties of the event. The timestamp above is illustrative only.

Metrics that can be implemented:

| Metric | Meaning | Note |
|---|---|---|
| Consumer start count | Total consumer start occurrences. | Use a counter, not as an active gauge. |
| Consumer startup duration | Latency from starting to started. | Correlate by consumer identity, use a monotonic timer. |
| Listener running gauge | Container state at observation time. | Reconcile in case events are missed. |
| Assigned partition count | Number of partitions owned by the consumer. | Computed from assignment, not from start events. |
| Consumer lag per partition | Backlog to process. | Cannot be inferred from the started event. |
| Rebalance count/duration | Frequency of ownership changes. | Use group/rebalance telemetry. |
| Consumer stop reason count | Classification of stops in supported versions. | Observe alongside `ConsumerStoppedEvent`. |
| First successful processing latency | Time from startup until the first event completes processing. | Requires a separate business processing milestone. |

Metric labels should use service/topic/listener IDs with reasonable cardinality. Do not use event IDs, Kafka offsets, or unbounded client IDs on every metric if the monitoring backend struggles to store high-cardinality series.

## 17. Integration test receiving ConsumerStartedEvent

A unit test calling `onConsumerStarted(...)` directly only tests the observer code; it does not prove that Spring Kafka actually publishes the event. Integration tests should start a Spring context and a real listener container, using Embedded Kafka or Kafka Testcontainers.

For deterministic tests, configure the listener with `autoStartup=false` and call start **after the event probe is initialized**, avoiding missing the event right while the context is starting up.

Example probe:

~~~java
@Component
public class ConsumerStartedProbe {

    private final BlockingQueue<ConsumerStartedEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        events.offer(event);
    }

    public ConsumerStartedEvent await(Duration timeout)
            throws InterruptedException {
        return events.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Key imports include `java.time.Duration`, `java.util.concurrent.BlockingQueue`, `LinkedBlockingQueue`, and `TimeUnit`.

Test listener:

~~~java
@KafkaListener(
        id = "startup-test-listener",
        groupId = "startup-test-group",
        topics = "startup.test",
        autoStartup = "false")
public void onTestMessage(String payload) {
    // No real record is needed to observe consumer lifecycle.
}
~~~

Test:

~~~java
@SpringBootTest
class ConsumerStartedEventIT {

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    ConsumerStartedProbe probe;

    @Test
    void startingContainerPublishesConsumerStartedEvent()
            throws Exception {

        MessageListenerContainer container =
                registry.getListenerContainer("startup-test-listener");

        assertThat(container).isNotNull();
        assertThat(container.isRunning()).isFalse();

        container.start();

        ConsumerStartedEvent event =
                probe.await(Duration.ofSeconds(30));

        assertThat(event).isNotNull();

        container.stop();
    }
}
~~~

The test requires a real broker/topic along with valid Kafka consumer configuration. If the application context contains multiple listeners, the probe should **filter events by container identity** or enable only the relevant listener; otherwise, an event from another listener can cause a false positive.

The test only verifies the start event; no records need to be sent. If you want to verify that the consumer received partitions, you must add a separate assertion based on assignment.

### 17.1. Testing concurrency

Run a listener with `concurrency=3` on a topic with enough partitions; observe events from the child consumers. Set finite timeouts and avoid assuming strict event ordering or fixed counts when consumers restart or tests run in parallel.

Separate three assertions:

1. The container received the start command and is in the running state.
2. Appropriate consumer lifecycle events were published.
3. The consumer group received assignments according to the expected topology.

### 17.2. Testing stop and restart

A scenario:

~~~text
Start container -> receive ConsumerStartedEvent
Stop container -> wait for stop callback/ConsumerStoppedEvent
Restart -> receive ConsumerStartedEvent next time
~~~

Remember to clear the probe queue between phases so stale events are not picked up. Check the container state rather than merely counting total events and concluding the restart succeeded.

### 17.3. Testing startup errors

Cases to test separately:

- Misconfigured consumer factory.
- Invalid authentication/authorization.
- Container shut down while starting.
- Non-existent topic when configuration disables automatic topic creation.
- Listener configured with `autoStartup=false` and no start command issued.

Not all errors produce `ConsumerFailedToStartEvent` in the same way. Combine events with exceptions/logs and container state according to the framework version in use.

## 18. Common mistakes

- **Equating start event with partition assigned:** a consumer can be started without holding any partitions.
- **Treating the start event as absolute readiness:** broker, database, and business processing may not be ready yet.
- **Counting start events as current active consumers:** consumers can stop and restart multiple times.
- **Counting events as replica count:** one replica can have multiple consumer threads.
- **Using the event to commit offsets or manipulate KafkaConsumer from the wrong thread:** an event listener is not an offset-management callback.
- **Blocking HTTP/database calls in @EventListener:** can prolong consumer startup.
- **Assuming events are always processed synchronously and in order:** the event multicaster can be customized.
- **Relying on in-memory events as a durable audit log:** a JVM crash loses unexported traces.
- **Using getSource().toString() as a long-term metric key:** debug string formatting is not an API contract.
- **Not distinguishing listener ID, group ID, and client ID:** leads to dashboards attributing the wrong owner.
- **Testing only the listener method without starting a real container:** does not verify lifecycle events.
- **Testing auto-start while registering the observer too late:** can miss the event.
- **Not clearing the probe queue before restart tests:** assertions accidentally consume stale events.
- **Automatically restarting repeatedly when events are missing:** can cause more group rebalances without fixing the root cause.

## 19. Production design using ConsumerStartedEvent

A minimal observability design:

~~~text
ConsumerStartedEvent
        |
        v
Spring lifecycle observer
        |
        +---- structured log
        +---- consumer startup counter
        +---- startup-duration metric
        +---- update lifecycle milestone in memory
        |
        +---- correlate with:
               ConsumerStoppedEvent
               KafkaListenerEndpointRegistry state
               partition assignment
               consumer lag / processing throughput
               deployment & restart signals
~~~

Treat `ConsumerStartedEvent` as a **starting milestone**, not proof that all startup has completed or that data has been processed. If you need to confirm a service can receive records, combine it with container state, group assignment, and dependency health. If you need to confirm records are processed durably, check business side effects, committed offsets, and transaction semantics.

When used properly, **ConsumerStartedEvent** gives a Spring Kafka system visibility into the startup lifecycle, measures startup latency, and separates consumer startup issues from Kafka group or business issues occurring later. Event handlers should remain concise, avoid interfering directly with the consumer, and always sit within a broader monitoring strategy covering logs, metrics, rebalance callbacks, and real broker data.
