# ContainerStoppedEvent

In Spring Kafka, each listener is normally managed by a **listener container**. The container creates the Kafka consumer, drives the `poll()` loop, invokes the listener method, manages offsets, error handling, assignments, and lifecycle. When the application stops or a listener is requested to stop, the container must stop consuming, terminate consumer threads, and close related resources.

**`ContainerStoppedEvent`** is the Spring application event indicating that a listener container has stopped. Applications can use this signal to log lifecycle transitions, update monitoring state, integrate with shutdown coordination systems, or detect unexpected container stops.

It is important to understand the limit: **this event is not a Kafka record, not a rebalance callback, and does not prove all in-flight business operations succeeded**. It merely reflects a point in the container's lifecycle inside the Spring process.

## 1. Listener container and its role in Spring Kafka

A listener is declared as follows:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "orders-listener",
            groupId = "orders-service",
            topics = "orders.events")
    public void onOrder(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Spring Kafka creates a container for the `orders-listener` endpoint. With `@KafkaListener`, containers are typically managed via `KafkaListenerEndpointRegistry`, while a factory such as `ConcurrentKafkaListenerContainerFactory` supplies concurrency, ack mode, error handler, and other settings.

~~~text
Spring ApplicationContext
       |
       v
KafkaListenerEndpointRegistry
       |
       +---- orders-listener container
               |
               +---- KafkaConsumer / consumer thread
               +---- poll -> process -> offset handling
               +---- start / stop lifecycle
               +---- Kafka application events
~~~

When the container stops, Spring Kafka can publish `ContainerStoppedEvent` so Spring beans subscribed to the event know about this lifecycle state. The event travels through Spring's `ApplicationEventPublisher` / event multicaster, not through the Kafka broker.

## 2. What does ContainerStoppedEvent notify?

The event is used to record that **the container performed its stop process**. It is useful for questions such as:

- Did an operator-requested stop result in the lifecycle signal?
- Is a specific listener stopping during application shutdown?
- At what point can we update a metric counting container stops?
- During a rollout, did any container leave the running state unexpectedly?
- What additional logs/events should be fetched to explain why the container stopped?

However, **do not infer** from a `ContainerStoppedEvent` that:

- All in-progress records succeeded.
- Offsets of all partitions were committed.
- Kafka transactions and database transactions committed.
- The consumer group has no other members.
- Partition ownership moved to a specific instance.
- The stop was caused by an error, auth failure, producer fencing, or admin command.
- The system definitely had time to ship logs/metrics out.
- An abruptly killed JVM will also emit the event.

Lifecycle state and business processing state are two separate concerns. When proving no data was lost or duplicated, you must still inspect committed offsets, error recovery, and idempotency.

## 3. Receiving the event via @EventListener

Use the class in the Spring Kafka package:

~~~java
import org.springframework.kafka.event.ContainerStoppedEvent;
~~~

Example listener:

~~~java
package com.example.kafka.monitoring;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ContainerStoppedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaContainerStopLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaContainerStopLogger.class);

    @EventListener
    public void whenContainerStopped(ContainerStoppedEvent event) {
        log.info("Kafka listener container stopped. source={}",
                event.getSource());
    }
}
~~~

This method receives an **application event inside the same Spring context**. It does not publish an event to Kafka and does not require a topic named `ContainerStoppedEvent`.

`getSource()` belongs to Spring's `ApplicationEvent` API. Depending on the event/version, the API may also provide a reference to the related container. Do not write production logic depending on the string format of `event.getSource().toString()`, because debug strings are not stable identifiers.

### 3.1. Receiving via ApplicationListener

An equivalent option:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ContainerStoppedEvent;
import org.springframework.stereotype.Component;

@Component
public class ContainerStopObserver
        implements ApplicationListener<ContainerStoppedEvent> {

    @Override
    public void onApplicationEvent(ContainerStoppedEvent event) {
        // Update lifecycle observation; do not commit offsets here.
        System.out.println("Stopped container: " + event.getSource());
    }
}
~~~

In production applications, use structured logging and metrics instead of `System.out.println()`. There is no need to declare both `ApplicationListener` and an `@EventListener` recording the same event if only one log is desired.

## 4. Identifying which listener container just stopped

A Spring Boot service can have multiple endpoints:

~~~text
orders-listener
payments-listener
inventory-listener
~~~

If using a global observer, distinguish the containers. You can check the type of event source per supported APIs:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ContainerStoppedEvent;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class KafkaLifecycleObserver {

    @EventListener
    public void onStopped(ContainerStoppedEvent event) {
        Object source = event.getSource();

        if (source instanceof MessageListenerContainer container) {
            String listenerId = container.getListenerId();
            recordStop(listenerId);
        }
    }

    private void recordStop(String listenerId) {
        // Example: increment a counter by listenerId or record status.
    }
}
~~~

When using a concurrent container, the source may relate to the container/child level depending on implementation. If parent–child mapping must be guaranteed, verify the exact API and event source of your running Spring Kafka version before assigning a business ID.

Keep `@KafkaListener(id = "...")` fixed so dashboards and the registry share one name. Distinguish:

| Concept | Meaning |
|---|---|
| Listener ID | Endpoint/container identifier in Spring Kafka. |
| Consumer group ID | Group sharing partitions and storing committed offsets on brokers. |
| Consumer client ID | Client identifier for logging and metric tracking. |
| Instance/Pod ID | Executing process identifier in the deployment environment. |

If no separate `groupId` is declared, some `@KafkaListener` configurations may use the listener ID as the group ID by default. To avoid confusion, production examples should specify both `id` and `groupId`.

## 5. When does ContainerStoppedEvent appear?

Several lifecycle paths can lead to a container stopping:

1. **ApplicationContext closes:** Spring lifecycle asks Kafka listeners to stop during orderly JVM shutdown.
2. **Stopped via API:** the application calls `stop()` on a container from `KafkaListenerEndpointRegistry`.
3. **Operational command:** an admin/management endpoint turns off a consumer for maintenance or workload shifting.
4. **Fatal error conditions:** depending on Spring Kafka version and configuration, certain errors can cause the container to stop.
5. **Concurrent container:** child consumers and the parent container have different stop phases, possibly emitting additional consumer-level events.

Not every Kafka failure stops the container. For example, a briefly unresponsive broker can cause the consumer to retry/reconnect without any stop event.

More importantly, **a consumer group rebalance does not mean the container stopped**. Rebalances normally just alter partition assignments while the container keeps running.

## 6. Container stop timeline and lifecycle events

A conceptual shutdown sequence:

~~~text
Application shutdown or container.stop() call
               |
               v
Spring Kafka requests listener container to stop
               |
               v
Consumer exits poll loop / finishes in-flight work
               |
               v
Consumer closes, container finishes stop lifecycle
               |
               v
Spring Kafka publishes ContainerStoppedEvent
               |
               v
Application event listeners receive event
~~~

The diagram serves as a guide to understanding lifecycle, not a rigid contract for the exact ordering of all callbacks across all versions and concurrent container types. Events may pass through a synchronous or asynchronous multicaster; handler timing can differ from when the publisher created the event.

If the listener is calling an HTTP service during a stop, container termination also depends on dependency timeouts, shutdown policy, and consumer thread state. `ContainerStoppedEvent` itself does not guarantee HTTP returned successfully or database transactions committed.

When observing shutdowns, collect additionally:

- Kafka client logs and container lifecycle logs.
- Committed offsets per topic/partition and consumer group.
- Listener processing latency and open dependency requests.
- Kafka transaction commits/aborts if the listener is transactional.
- DLT/error handler status after failed record processing.
- Spring context shutdown time and orchestrator budgets.

## 7. Comparing with other Spring Kafka events

Spring Kafka has similarly named events representing different steps:

| Event | General meaning | When to use? |
|---|---|---|
| `ConsumerStartingEvent` | Consumer thread enters initialization phase. | Observing startup. |
| `ConsumerStartedEvent` | Consumer has begun operating. | Monitoring consumer readiness. |
| `ConsumerStoppingEvent` | Consumer is about to stop. | Analyzing thread-level stop duration. |
| `ConsumerStoppedEvent` | Consumer has stopped, possibly with a reason. | Classifying consumer stop reasons. |
| **`ContainerStoppedEvent`** | Listener container stopped. | Observing container-level lifecycle. |
| `ConsumerFailedToStartEvent` | Consumer failed to start within wait limit. | Investigating startup failures. |
| `ListenerContainerIdleEvent` | Listener idle for configured period. | Distinguishing no records from stopped consumer. |
| `NonResponsiveConsumerEvent` | Consumer deemed unresponsive per container monitor. | Investigating stuck polls or slow processing. |

The exact event set and properties may differ across version lines. Consumer-level events give deeper visibility into individual consumer threads, while container-level events serve container lifecycle observation.

### 7.1. ConsumerStoppedEvent and reason

`ConsumerStoppedEvent` may carry a reason describing why the consumer stopped, such as normal stop, error, fencing, or auth issues depending on version. `ContainerStoppedEvent` should be viewed as a "container stopped" signal rather than a detailed error code.

When classifying "planned shutdown" vs "unexpected shutdown", combine:

- Application-requested stop status.
- `ConsumerStoppedEvent`/reason if supported by your active API.
- Exceptions and Kafka client logs near the stop timestamp.
- Kubernetes rollout/restart signals.
- Consumer group membership, rebalance, and health metrics.

### 7.2. Rebalance callbacks are not stop events

When a consumer group adds a new replica:

~~~text
Container RUNNING
       |
       v
Partitions revoked
       |
       v
Partitions assigned to members
       |
       v
Container continues polling
~~~

This is a partition ownership change. To handle per-partition state handoffs, use `ConsumerRebalanceListener` or `ConsumerAwareRebalanceListener` per the corresponding Spring Kafka API. Do not use `ContainerStoppedEvent` to commit checkpoints when partitions are revoked, because the container does not necessarily stop then.

## 8. Controlling stops via KafkaListenerEndpointRegistry

The registry lets you look up containers by listener ID and request stops:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class KafkaListenerManager {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerManager(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean stopOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null) {
            return false;
        }

        container.stop();
        return true;
    }
}
~~~

`container.stop()` represents a stop request under the lifecycle contract. Do not assume it means "all offsets committed" or "all business logic finished" the instant it returns.

If you need to coordinate a workflow dependent on stopping, you can use a callback:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null) {
    container.stop(() -> log.info("orders-listener stop completed"));
}
~~~

Stop callbacks and `ContainerStoppedEvent` serve two different needs:

- **Stop callback:** confirms progress of a specific stop request.
- **Application event:** observes container stops, even when the initiator was not the current stop-calling code.

Do not assume execution order between callbacks and event listeners is fixed when the multicaster runs asynchronously or when parent/child lifecycles coordinate.

## 9. ConcurrentMessageListenerContainer and multiple consumer threads

A concurrent listener factory can create multiple consumers:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
~~~

Configured listener:

~~~java
@KafkaListener(
        id = "orders-listener",
        groupId = "orders-service",
        topics = "orders.events",
        containerFactory = "orderFactory")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

With concurrency of three, one concurrent container manages up to three child consumer containers. When stopping, those consumer threads may finish at different times. Therefore:

- Do not count `ConsumerStoppedEvent` as the number of Pods shut down.
- Do not count `ContainerStoppedEvent` as the number of revoked partitions.
- If dashboards measure lifecycle per listener, clearly distinguish parent vs child.
- Per-consumer metrics should use proper client ID/member metadata.
- Do not hardcode an assumption that the event fires strictly once unless verified by integration tests on your running version.

A child consumer stopping due to an error does not necessarily reflect the state of the entire concurrent parent container. Combine events with `registry.getListenerContainer(id).isRunning()` and container status details.

## 10. Which thread can the event listener run on?

Spring application events are published through `ApplicationEventMulticaster`. With the default synchronous multicaster, listeners are usually invoked directly on the event-publishing thread. With an asynchronous executor, handlers may run on a different thread.

Therefore, keep processing inside `@EventListener` **lightweight and free of long blocking**:

~~~java
@EventListener
public void onStopped(ContainerStoppedEvent event) {
    log.info("Listener container stopped, source={}", event.getSource());
    metrics.incrementContainerStopCount();
}
~~~

Avoid doing the following inside event handlers:

- Waiting indefinitely for an HTTP request.
- Running database migrations or holding resource locks for long.
- Committing Kafka consumer offsets or acknowledging records.
- Using `KafkaConsumer` from a thread that does not own that consumer.
- Calling `stop()` and blocking-waiting on the very container currently stopping.
- Invoking cleanup dependent on a bean that may have already closed in an earlier shutdown phase.
- Auto-restarting the container infinitely while auth/fencing errors remain unresolved.

If logging/metrics recording fails, do not let monitoring exceptions disrupt the stop process. Catch and log errors in the observability layer:

~~~java
@EventListener
public void onStopped(ContainerStoppedEvent event) {
    try {
        lifecycleRecorder.recordStopped(event.getSource());
    } catch (RuntimeException exception) {
        log.warn("Could not record Kafka stop event", exception);
    }
}
~~~

Using an asynchronous event listener also does not guarantee the event is processed before the JVM exits. Executors/telemetry exporters may already be shutting down; therefore event handlers should not be the sole place persisting a mandatory audit record.

## 11. Spring Boot graceful shutdown and wait times

Spring Boot manages the lifecycle of many beans, including containers managed by Spring Kafka. When an application shuts down orderly, Spring stops beans by phase and wait budget.

Example:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s

server:
  shutdown: graceful
~~~

`timeout-per-shutdown-phase` is the Spring lifecycle budget; `server.shutdown=graceful` applies to the web server per Spring Boot mechanics. Kafka listeners still have their own lifecycle.

Spring Kafka has container shutdown timeout properties, such as `ContainerProperties.shutdownTimeout` in applicable versions. They must coordinate with:

- How long a record/batch listener needs to process.
- HTTP/database client timeouts.
- Kafka transaction flush/commit/abort.
- Process runtime or Kubernetes grace periods.
- Dependent lifecycle beans that listeners still need.

If shutdown time is too short, the process may be killed before the event fires. If too long, rollouts drag out and faulty instances are not replaced promptly.

### 11.1. Kubernetes SIGTERM and SIGKILL

When a Pod terminates, kubelet normally sends `SIGTERM` and waits for `terminationGracePeriodSeconds`. If the process has not exited, kubelet can send `SIGKILL`:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: order-consumer
      image: example/order-consumer:latest
~~~

`SIGTERM` gives the application a chance for orderly shutdown, so containers can emit `ContainerStoppedEvent`. Conversely, `SIGKILL` or a JVM crash **does not guarantee cleanup callbacks/application events execute**.

Thus, absence of a stop event does not mean the process is still running; correlate signals from the orchestrator, consumer group, and committed offsets. Do not treat stop events as the sole durable audit source.

## 12. Readiness, liveness, and listener health

You can use events to reflect a "listener is no longer active" status, though clear health policies are required.

For example, an application has two listeners:

- `orders-critical` must stay active to process orders.
- `audit-optional` may stop temporarily without affecting the core service.

When `orders-critical` stops unexpectedly, an observer may lower readiness status or raise an alert. When `audit-optional` stops as planned, there is no need to mark the entire service unhealthy.

| State | Question to answer | Role of ContainerStoppedEvent |
|---|---|---|
| Readiness | Is the instance eligible to handle new work? | One input to evaluate critical listeners. |
| Liveness | Is the process alive and able to recover? | Insufficient on its own to decide restarts in all cases. |
| Consumer group assignment | Which partitions does this instance hold? | Requires metrics/consumer APIs, not inferred from event. |
| Business progress | Are events processed within SLO? | Requires lag, throughput, failures, and DB state. |
| Shutdown progress | Has the container stopped per lifecycle? | Event is an appropriate signal. |

For consumer-only services on Kubernetes, HTTP readiness does not directly instruct Kafka brokers to stop assigning partitions. Kafka group ownership and listener container lifecycles must be controlled by separate mechanisms.

## 13. ContainerStoppedEvent is not an "offset checkpoint"

A dangerous design mistake is treating a stop event as a success marker for all records:

~~~text
Wrong:
ContainerStoppedEvent
     |
     +---- auto-commit all offsets
     +---- mark all business events successful
~~~

A container can stop after an exception, a transaction rollback, or before the consumer manages to commit offsets. The event does not tell which records succeeded or which need redelivery.

For record listeners, offset commit responsibility belongs to ack mode, error handler, and container. For transactional listeners, Kafka outputs and input offsets can commit together in a transaction per config; lifecycle events sit outside that commit protocol.

If business effects must be guaranteed, you should:

1. Check committed offsets from the consumer group.
2. Inspect output records with a `read_committed` consumer when using Kafka transactions.
3. Check database/outbox/inbox to detect partial commits.
4. Design idempotency for redelivery.
5. Check DLT/retry when listeners fail.

Do not implement offset commits or record-specific manipulation from an `@EventListener` that merely receives `ContainerStoppedEvent`.

## 14. Distinguishing abnormal scenarios

### 14.1. Consumer group rebalance

A new replica joins, causing partitions to be revoked and reassigned. Containers on existing replicas **can remain running**. Do not use `ContainerStoppedEvent` to decide when to save per-partition state; use proper rebalance callbacks.

### 14.2. Temporarily unavailable broker

`KafkaConsumer` can reconnect, retry requests, or wait for metadata/fetches. Not every request timeout stops the container. To detect situations where progress has stalled, monitor Kafka client errors, lag, and `NonResponsiveConsumerEvent` where applicable.

### 14.3. Authentication/authorization failure

Depending on configuration and version, the container may stop or retry after auth/authz failures. When stopped, the stop event is only an outcome signal. Find the root cause from exceptions, consumer stopped reasons, and Kafka logs; do not auto-restart infinitely into an error loop.

### 14.4. Producer fencing in transactions

When a transactional producer loses authority due to an old epoch, the container may stop under policies like `stopContainerWhenFenced` in supported versions. Investigate the actual transactional ID/owner; restarting a fenced producer on the same contested identity will not cleanly resolve it.

### 14.5. JVM crash or hard kill

A hard-killed process may produce no stop event. The Kafka consumer group and committed offsets must suffice for another instance to resume processing safely; database side effects need duplicate protection.

### 14.6. Pause and resume

`pause()` temporarily halts receiving new records per container mechanics while maintaining appropriate poll loops/group membership. `resume()` continues. Pause/resume is not equivalent to stop/start and should not make dashboards report the container as stopped.

## 15. ApplicationContext closing and lifecycle order

Spring `ContextClosedEvent` and Kafka `ContainerStoppedEvent` have different meanings:

~~~text
ApplicationContext begins closing
        |
        v
ContextClosedEvent
        |
        v
Spring lifecycle stops containers / beans by phase
        |
        v
Kafka listener container stops
        |
        v
ContainerStoppedEvent is published
~~~

The conceptual sequence above does not replace the event contract of your active version. With an asynchronous multicaster, actual handler execution may be delayed. If an observer needs a database connection or telemetry exporter, verify whether they are still alive in that shutdown phase.

Do not let event handlers perform mandatory business logic after most resources have already been destroyed. If you must coordinate stop order across multiple services, use lifecycle/dependencies/phases and bounded waits rather than relying on receiving an in-memory event.

## 16. Integration testing ContainerStoppedEvent

A reliable test uses a Spring context with a real listener container and an event-receiving probe. Kafka Testcontainers or Embedded Kafka can be used to run the consumer.

Probe:

~~~java
@Component
public class StoppedEventProbe {

    private final BlockingQueue<ContainerStoppedEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onStopped(ContainerStoppedEvent event) {
        events.offer(event);
    }

    public ContainerStoppedEvent poll(Duration timeout)
            throws InterruptedException {
        return events.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Required Java imports: `BlockingQueue`, `LinkedBlockingQueue`, `TimeUnit`, `Duration`, and Spring Kafka `ContainerStoppedEvent`.

Test:

~~~java
@Autowired
KafkaListenerEndpointRegistry registry;

@Autowired
StoppedEventProbe probe;

@Test
void stopPublishesEvent() throws Exception {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    assertThat(container).isNotNull();

    if (!container.isRunning()) {
        container.start();
    }

    container.stop();

    ContainerStoppedEvent event =
            probe.poll(Duration.ofSeconds(30));

    assertThat(event).isNotNull();
}
~~~

With multiple listeners, the probe needs to filter by container identity or the test should enable only one container to avoid false positives. With concurrent containers, event counts can reflect parent/child behavior; **do not assert strictly one event unless you have verified the framework contract of your active version**.

### 16.1. Waiting on stop callback instead of Thread.sleep()

~~~java
CountDownLatch stopped = new CountDownLatch(1);

container.stop(stopped::countDown);

assertThat(stopped.await(30, TimeUnit.SECONDS)).isTrue();
assertThat(container.isRunning()).isFalse();
~~~

The callback tests the stop process inside the container, while the probe confirms the application event was published/received. Do not assume callback and event listener order if the event multicaster runs asynchronously.

### 16.2. Test scenarios to include

1. Stop an idle listener: container changes state and event appears.
2. Stop while listener is processing a record: observe wait duration, commit/rollback, and redelivery.
3. Stop concurrent listener: distinguish consumer-level and container-level events.
4. Stop then restart: listener resumes receiving records without leaking consumer threads.
5. ApplicationContext shutdown: container stops within lifecycle limits.
6. Simulate SIGTERM in a child process: gets a chance to emit event and exit gracefully.
7. Hard kill: event may be absent, yet system still recovers via offsets/idempotency.
8. Rebalance without stopping: ensure application does not equate partition revoke with container stop.
9. Fatal error stopping container: combine reason/exception to diagnose.
10. Telemetry observer throws exception: monitoring failure does not disrupt shutdown.

Use finite timeouts and observable conditions. Do not treat a fixed `Thread.sleep()` of a few seconds as proof that stopping completed.

## 17. Structured logging and metrics

A helpful operational log:

~~~text
event_type=ContainerStoppedEvent
application=orders-consumer
listener_id=orders-listener
instance_id=orders-worker-2
shutdown_intent=planned
timestamp=2026-11-15T16:00:00Z
~~~

`shutdown_intent` is **application-managed metadata**, not a default property of `ContainerStoppedEvent`. You can record intent when an admin API calls stop or when the context begins closing, then correlate with events and Kafka client logs.

Metrics to consider:

| Metric | Meaning |
|---|---|
| Container running state | Whether the listener is running or stopped. |
| Stop event count | Number of container stops by stable ID. |
| Consumer stop reason count | Breakdown of causes if supported by Spring Kafka version. |
| Consumer group assignment | Number of partitions currently owned. |
| Consumer lag per partition | Where prolonged stops increase backlog. |
| Listener error rate | Errors right before stopping. |
| Graceful shutdown duration | Time from stop request to completion. |
| Pod restart/termination reason | Distinguishing normal shutdown from hard kill. |

Do not use offsets or correlation IDs as high-cardinality metric labels. Use structured logs/traces to look up individual record details.

If the observability pipeline is also shutting down, the event may be logged yet not exported in time. For mandatory audits, use a dedicated durable mechanism instead of relying on logs emitted from stop events.

## 18. Common mistakes

- **Confusing application events with Kafka records:** `ContainerStoppedEvent` has no Kafka topic/offset of its own.
- **Treating stop events as "backlog cleanly processed":** containers can stop with uncommitted records.
- **Using stop events instead of rebalance listeners:** rebalances do not necessarily stop containers.
- **Conflating ConsumerStoppedEvent and ContainerStoppedEvent:** they describe different lifecycle levels.
- **Assuming one event corresponds to one Pod/partition:** concurrency can generate multiple signals at different levels.
- **Making slow HTTP/database calls inside event handlers:** can delay or break shutdown.
- **Assuming event listeners always run on the consumer thread:** depends on the event multicaster.
- **Relying on the event to commit offsets:** offsets must follow ack/transaction/recovery semantics.
- **Not distinguishing planned vs unexpected stops:** must combine intent, reason, and error logs.
- **Using the event as the sole audit record:** SIGKILL/JVM crashes can prevent the event from appearing.
- **Auto-restarting listeners infinitely on config errors:** does not fix auth/fencing root causes.
- **Using source toString() as a stable identifier:** debug strings are not an API contract.
- **Assuming stop() always means stopped immediately:** check callbacks/state/events.
- **Not aligning timeouts with Kubernetes:** processes can be killed before stopping gracefully.

## 19. Designing lifecycle observability for production

A simple architecture:

~~~text
ContainerStoppedEvent
       |
       v
Spring lifecycle observer
       |
       +---- structured log
       +---- stop counter / running-state gauge
       +---- unexpected-stop alert when appropriate
       |
       +---- correlate Kafka group membership
       +---- correlate ConsumerStoppedEvent reason
       +---- correlate lag/error/transaction metrics
       +---- correlate SIGTERM/restart events
~~~

Never make `ContainerStoppedEvent` the place for business logic such as reprocessing records, acknowledging offsets, or publishing data requiring exactly-once guarantees. It is a **lifecycle observation** event, not a transaction boundary.

When combining this event with `KafkaListenerEndpointRegistry`, consumer-level events, shutdown timeouts, and orchestrator signals, a Spring Kafka system can detect stopped listeners, trace unexpected stop causes, and control rollouts more clearly. Record-processing reliability must still be independently protected by offset management, retry/DLT, Kafka transactions, and idempotency on resources outside Kafka.
