# ConsumerStartingEvent

In Spring Kafka, a listener does not start receiving records immediately when the application creates a bean or calls `start()` on the listener container. The container still needs to initialize the consumer task, submit the task to an executor, start the consumer thread, and enter the `poll()` loop. To let the application observe these milestones, Spring Kafka publishes **application events**. `ConsumerStartingEvent` is an early signal indicating that **the consumer thread has started initializing, before the consumer begins polling**.

This event is useful when operating multiple listeners, multiple partitions, and multiple replicas: it helps determine whether the consumer thread has been run by the executor, correlates startup with a specific listener container, and aids in diagnosing cases where a consumer fails to start. However, it **is not proof that the listener has received partitions, polled successfully, processed records, or is ready to serve business logic**.

This lesson focuses on understanding when the event is published, how to listen for it with Spring `@EventListener`, distinguishing it from adjacent application events, combining it with timeouts and the task executor, and building startup observability suited to Spring Kafka Reliability Operations.

## 1. Where does ConsumerStartingEvent sit in the consumer lifecycle?

With `@KafkaListener`, Spring creates a listener container to manage the Kafka consumer and the record-processing lifecycle. Each consumer needs a task/thread to serve `poll()` along with dispatching records to the listener.

A simplified sequence:

~~~text
Spring application context initializes
             |
             v
Kafka listener container is created
             |
             v
Container receives start() command
             |
             v
Consumer task is executed by executor
             |
             v
ConsumerStartingEvent
    (consumer thread starts, before polling)
             |
             v
ConsumerStartedEvent
    (consumer is about to start polling)
             |
             v
Kafka consumer poll(), join group, assignment...
             |
             v
Receive records / invoke @KafkaListener
             |
             v
On shutdown: stopping/stopped events
~~~

The steps above are a model for understanding the lifecycle, not a promise that every Spring Kafka version always has the exact same number of internal calls or the same detailed sequence of operations. In particular, **having `ConsumerStartingEvent` does not guarantee that the consumer will poll successfully right afterward**: authentication, authorization, network, broker availability, or initialization errors can occur in subsequent steps.

According to the Spring Kafka documentation, the event is published **when a consumer thread is newly started, before it begins polling**. Therefore, this is an appropriate milestone for observing **thread startup**, not a milestone for business readiness.

## 2. ConsumerStartingEvent is a Spring application event

Event class:

~~~java
org.springframework.kafka.event.ConsumerStartingEvent
~~~

This class extends `KafkaEvent` and participates in Spring's `ApplicationEvent` mechanism. The Spring Kafka listener container publishes the event to the application context; beans can listen for it via `@EventListener` or `ApplicationListener<ConsumerStartingEvent>`.

Components to distinguish:

| Component | Role |
|---|---|
| `@KafkaListener` | Defines the record-processing method |
| `MessageListenerContainer` | Manages the consumer thread, polling, and listener execution |
| `KafkaListenerEndpointRegistry` | Holds references to containers created by `@KafkaListener` |
| `ConsumerStartingEvent` | Signals that the consumer thread has started initializing |
| `ConsumerStartedEvent` | Signals that the consumer is about to start polling |
| `ConsumerFailedToStartEvent` | Reports a timeout when `ConsumerStartingEvent` has not been observed per the startup policy |
| `ConsumerStoppedEvent` | Reports that the consumer has stopped; includes reason information in supported versions |
| `ContainerStoppedEvent` | Reports that the container has stopped |

`ConsumerStartingEvent` was introduced in Spring Kafka starting in the 2.3 version line. The specific API should be checked against the application's `spring-kafka` dependency; do not rely on documentation from a newer version if the codebase uses an older version.

## 3. What information can be retrieved from the event

`ConsumerStartingEvent` provides two important container references through the API inherited from `KafkaEvent`:

- **`source`:** the listener container that directly published the event.
- **`container`:** the listener container associated with the event; when `source` is a child container of a concurrent container, this value may be the **parent container**.

Example:

~~~java
MessageListenerContainer source =
        event.getSource(MessageListenerContainer.class);

MessageListenerContainer container =
        event.getContainer(MessageListenerContainer.class);
~~~

The generic methods `getSource(Class<T>)` and `getContainer(Class<T>)` let you obtain a properly typed reference without manually casting `Object`. Passing `MessageListenerContainer.class` is appropriate when you want to work with the container at the interface level.

Meaningful data:

| Data | How to use | What not to infer |
|---|---|---|
| `event.getSource(...)` | Identifies which child/container published the event | Not necessarily the parent managing the entire group |
| `event.getContainer(...)` | Identifies the corresponding container, possibly the parent | Not a Kafka `Consumer` instance |
| `event.getTimestamp()` | Time when Spring created the event | Not the time when Kafka partitions were assigned |
| `source.getListenerId()` | Identifies the listener/container in logging, per the supported API | Not a business event ID |
| `source.isRunning()` | Observes lifecycle state at the moment of invocation | Does not prove the consumer has polled/read records |

This event **is not a `ConsumerRecord`**. Because it is published before polling, there is no business event payload, Kafka key/value, original offset, or specific partition being processed. If you need to know about assignments, observe consumer rebalance/assignment using the appropriate API instead of expecting `ConsumerStartingEvent` to contain that information.

## 4. Listening with @EventListener

A simple way to record consumer startup:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStartingEvent;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerStartupObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerStartupObserver.class);

    @EventListener
    public void onConsumerStarting(ConsumerStartingEvent event) {
        MessageListenerContainer source =
                event.getSource(MessageListenerContainer.class);

        MessageListenerContainer parent =
                event.getContainer(MessageListenerContainer.class);

        log.info(
            "Kafka consumer starting: source={} parent={} time={}",
            source.getListenerId(),
            parent.getListenerId(),
            event.getTimestamp()
        );
    }
}
~~~

Whenever the application publishes `ConsumerStartingEvent` and the listener bean is registered, the `onConsumerStarting` method is invoked. `source` and `parent` may be the same container if this is not a child of a concurrent container.

What the code above does **not** do:

- Does not modify Kafka offsets.
- Does not interfere with consumer polling.
- Does not start another container.
- Does not send or receive records.
- Does not automatically make health/readiness pass.
- Does not automatically retry startup errors.

Its role is **state observation**. Prefer keeping the handler short and non-blocking so it does not slow down the consumer startup path.

## 5. Example of a monitored listener

Set a stable listener ID for observability:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "orders-consumer",
        topics = "orders",
        groupId = "order-projection")
    public void onOrder(OrderEvent event) {
        orderService.apply(event);
    }
}
~~~

When `orders-consumer` starts, the Spring Kafka listener container creates the consumer task. The startup observer can log the corresponding event. In an application with multiple listener IDs, the observer will receive events from **every container in the application context**, not just `orders-consumer`.

If you need to narrow the scope, filter by the parent/source ID and instance name as shown in the following sections.

## 6. Distinguishing from ConsumerStartedEvent

The two event names look similar, but the milestones they represent are different:

| Event | When does it occur? | Proper interpretation |
|---|---|---|
| `ConsumerStartingEvent` | Consumer thread starts initializing, before polling | Consumer task has begun running |
| `ConsumerStartedEvent` | Consumer is about to start polling | Consumer has approached the poll loop |
| Consumer receives assignment | After the corresponding poll/join group/rebalance process | Partitions have been assigned to the group |
| Listener processes first record | When poll returns records and dispatches | Business data processing has started |

Both `ConsumerStartingEvent` and `ConsumerStartedEvent` are **lifecycle events**, not confirmation that Kafka currently has records, that business dependencies are healthy, or that consumer lag is zero.

If the application starts when the topic is empty, the consumer can still publish startup events and poll normally without ever receiving a record. Therefore, do not require "must receive the first record" to consider thread startup valid; system readiness must be defined according to its own requirements.

## 7. How is ConsumerFailedToStartEvent related?

Spring Kafka provides `ConsumerFailedToStartEvent` to detect situations where **the container requested consumer startup but has not received `ConsumerStartingEvent` within `consumerStartTimeout`**.

Conceptual timeline:

~~~text
Container start() called
        |
        +-- Executor receives consumer task
        |      |
        |      +-- Thread is run in time
        |             |
        |             v
        |       ConsumerStartingEvent
        |
        +-- ConsumerStartingEvent not seen
               within consumerStartTimeout
               |
               v
          ConsumerFailedToStartEvent
          + startup warning/error log
~~~

A common cause is that the **task executor does not have enough threads** compared to the number of listener containers and concurrency. For example, an executor has 2 threads but needs to run 5 long-lived consumer tasks: some tasks may wait indefinitely in the queue, leading to a timeout.

Understand the direction of inference:

- **With `ConsumerStartingEvent`:** the task has been run up to the initialization milestone; does not prove the consumer can poll successfully.
- **With `ConsumerFailedToStartEvent`:** timeout while the starting event has not been seen; investigate the executor/lifecycle. Do not immediately conclude the Kafka broker is down.
- **With neither event in the logs:** the event listener may not be registered, the container may not have been started, log filtering may be hiding it, or the application is not receiving events in the right context.

Do not use `ConsumerFailedToStartEvent` to automatically spawn unlimited executor threads; concurrency and resources must be calculated explicitly.

## 8. Configuring consumerStartTimeout

`consumerStartTimeout` belongs to `ContainerProperties`. Depending on the version, the default duration is typically documented as **30 seconds**; the application can set a value based on actual startup capacity.

Example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
           .setConsumerStartTimeout(Duration.ofSeconds(45));

    return factory;
}
~~~

Additional imports:

~~~java
import java.time.Duration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
~~~

Meaning:

- The container waits for the consumer thread to emit the startup signal within the configured duration.
- If the starting event is not observed, the framework can publish `ConsumerFailedToStartEvent`.
- Increasing the timeout helps reduce false alerts if executor startup is briefly slow, **but it does not fix thread starvation** or a task executor that permanently lacks threads.
- `consumerStartTimeout` is not a Kafka broker request timeout, `max.poll.interval.ms`, `session.timeout.ms`, or the deadline for waiting on partition assignment.

If the application starts up quickly but cannot consume due to broker/ACL/authorization issues, merely increasing the consumer start timeout may not solve that problem.

## 9. Example of diagnosing thread starvation

Suppose an application has:

~~~text
Listener orders: concurrency = 3
Listener payments: concurrency = 2

Total long-lived consumer tasks: up to 5
Shared executor: only 2 active threads
~~~

A Kafka consumer task is typically long-lived and polls continuously; it does not return its thread after a few milliseconds. If all five tasks are forced to share a fixed executor with only two worker threads, three tasks may sit in the queue without ever running.

In that case:

1. Some child consumers may publish `ConsumerStartingEvent` normally.
2. Other tasks have no thread to run on, so they have not published the event.
3. The container waits up to `consumerStartTimeout` and may publish `ConsumerFailedToStartEvent`.
4. Some partitions do not have an active consumer as intended by the configuration.
5. Lag grows on the streams that are not being adequately served.

How to handle it:

- Check the number of child consumers that need to run concurrently.
- Inspect the actual `AsyncTaskExecutor`/listener task executor type configured on the factory/container.
- Ensure the executor has enough threads for long-lived tasks, or use a dedicated, suitably sized executor.
- Check queue backlog, rejected tasks, thread states, and CPU/thread quotas.
- Check whether a task is blocked initializing a Kafka producer, deserializer, credentials, or another dependency.
- Do not merely increase `consumerStartTimeout` to mask the root cause.

This is a startup failure cause located **inside the process**, not in the Kafka broker.

## 10. ConsumerStartingEvent with ConcurrentMessageListenerContainer

When using `@KafkaListener(concurrency = "3")` or factory concurrency, Spring Kafka creates a **concurrent container** managing multiple child Kafka consumers.

~~~text
ConcurrentMessageListenerContainer: orders-consumer
          |
          +-- child-0 -> ConsumerStartingEvent
          |
          +-- child-1 -> ConsumerStartingEvent
          |
          +-- child-2 -> ConsumerStartingEvent
~~~

In this situation, `event.getSource(MessageListenerContainer.class)` may be the child container that published the event; `event.getContainer(MessageListenerContainer.class)` usually points to the parent container managing the entire group of child consumers.

Each child thread can start at a different time. Therefore:

- Do not count one event for the entire parent and conclude that all child consumers are already running.
- Do not confuse listener concurrency with the topic's partition count.
- If concurrency exceeds the number of partitions, some child consumers may not be assigned any partitions even though they still start up.
- Increasing concurrency can increase the number of startup events observed.
- After a restart or stop-start, events can appear again; they do not represent a unique business event.

Listener example:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders",
    groupId = "order-projection",
    concurrency = "3")
public void onOrder(OrderEvent event) {
    orderService.apply(event);
}
~~~

When running multiple replicas, each replica has its own registry and child containers. Do not aggregate starting event counts by listener ID alone while ignoring instance ID if you want to analyze the actual task count across the cluster.

## 11. Filtering events by the desired listener container

If the application has dozens of listeners, filter early to avoid excessive logging or updating metrics incorrectly.

~~~java
@Component
public class OrdersConsumerStartingObserver {

    private static final Logger log =
            LoggerFactory.getLogger(OrdersConsumerStartingObserver.class);

    @EventListener
    public void onStarting(ConsumerStartingEvent event) {
        MessageListenerContainer parent =
                event.getContainer(MessageListenerContainer.class);

        if (!"orders-consumer".equals(parent.getListenerId())) {
            return;
        }

        MessageListenerContainer source =
                event.getSource(MessageListenerContainer.class);

        log.info(
            "Orders consumer thread starting: source={} parent={}",
            source.getListenerId(),
            parent.getListenerId()
        );
    }
}
~~~

Depending on parent/child naming and the container creation mechanism of the version, verify what listener ID is returned. Because `source` may be a child, comparing `source`'s ID with `orders-consumer` may not match even when the event belongs to that original listener.

Do not use the child ID suffix as a fixed business identifier. The suffix or the mapping between tasks and partitions can change across concurrency changes, rebalances, or restarts.

## 12. Using ApplicationListener instead of @EventListener

Besides the annotation, you can use the `ApplicationListener` interface to receive the specific event type:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ConsumerStartingEvent;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class ConsumerStartAuditListener
        implements ApplicationListener<ConsumerStartingEvent> {

    @Override
    public void onApplicationEvent(ConsumerStartingEvent event) {
        MessageListenerContainer source =
                event.getSource(MessageListenerContainer.class);

        auditLogger.recordConsumerThreadStarting(
                source.getListenerId(),
                event.getTimestamp()
        );
    }
}
~~~

`auditLogger` is an example service provided by the application. If auditing writes over the network or to a database, consider pushing minimal information to a bounded internal queue and processing it off the consumer thread. Do not let slow logging/auditing stall startup.

Choose `@EventListener` when you want a concise listener method inside a Spring bean. Choose `ApplicationListener<ConsumerStartingEvent>` when the class is designed specifically to receive this event. Both use the Spring application event mechanism, not a Kafka topic containing startup events.

## 13. On which thread is the event published?

By default, Spring's `ApplicationEventMulticaster` usually invokes event listeners **synchronously on the thread that published the event**. For Kafka listener container events, this is usually a consumer-related thread.

This has a very practical consequence: if `@EventListener` performs a long blocking operation, the consumer thread can be delayed right during startup.

Example of what not to do:

~~~java
@EventListener
public void onStarting(ConsumerStartingEvent event) {
    externalAuditApi.callAndWaitForMinutes(...);
    Thread.sleep(60_000L);
}
~~~

An event handler like this can prolong the time from when the consumer task begins until polling starts, even though `ConsumerStartingEvent` has already been published.

What to do instead:

~~~java
@EventListener
public void onStarting(ConsumerStartingEvent event) {
    MessageListenerContainer source =
            event.getSource(MessageListenerContainer.class);

    log.info("Consumer thread starting: {}", source.getListenerId());
    startupMetricRecorder.increment(source.getListenerId());
}
~~~

If you need to send a notification or store remote audits, prefer an asynchronous mechanism **that does not slow down the consumer thread**, and bound queue size and resources. Do not use lifecycle events as a hook to inject heavy operational tasks into the consumer's hot path.

## 14. Thread safety when a custom event multicaster runs asynchronously

You can configure the Spring application event multicaster to use an asynchronous executor. When doing so, the event handler may be called on a **different** thread from the consumer thread.

Rules:

- Kafka `Consumer` is not thread-safe.
- Do not call methods on Kafka `Consumer` from an async event handler just because the event object holds a reference to a consumer in some event types.
- `ConsumerStartingEvent` mainly carries container references; do not assume it provides a `KafkaConsumer` to manipulate.
- If you need to pause/resume, use the `MessageListenerContainer` API instead of touching `KafkaConsumer` directly from an arbitrary thread.
- If you need to work with assignment/seek, use callbacks designed by Spring Kafka for the consumer thread, such as `ConsumerSeekAware` or an appropriate rebalance listener.

In particular, handlers written for `ListenerContainerIdleEvent` or `NonResponsiveConsumerEvent` may carry a consumer reference; if the multicaster is switched to async while the code still calls `consumer.pause()`/`seek()` arbitrarily, thread-safety bugs will occur.

A safe rule for `ConsumerStartingEvent` is to **only read container metadata and record observability**, not directly manipulate consumer state inside the callback.

## 15. ConsumerStartingEvent is not a readiness signal

An application can publish `ConsumerStartingEvent` when:

- The Kafka cluster is temporarily disconnected.
- DNS/broker bootstrap is not ready yet.
- The consumer has not joined the group yet.
- Partition assignment has not happened yet.
- The topic is empty and there are no records to process.
- Downstream dependencies are not ready yet.
- The listener is still initializing other tasks before polling.

Therefore, a health/readiness probe that only checks "starting event seen" may return **READY** too early.

Distinguish the levels of readiness:

| Observed condition | What is proven? | Not yet proven |
|---|---|---|
| Application context refresh | Spring beans have been created | Kafka consumer thread is running |
| `ConsumerStartingEvent` | Consumer thread started startup | Poll, assignment, business readiness |
| `ConsumerStartedEvent` | Consumer is about to poll | Partition assignment has occurred |
| Assignment callback | Consumer was assigned partitions in the group | First record has been processed |
| Successful poll/record processing | Data path is working | All partitions or other dependencies are healthy |
| Consumer lag/SLO within threshold | Processing progress meets an operational criterion | Does not replace all health checks |

A good readiness policy should be based on **specific service requirements**. For example, an API service that does not depend on a Kafka consumer to serve HTTP traffic may become ready before the Kafka stream catches up. A critical background worker may need to ensure the consumer is running, assignment is valid, and downstream dependencies are healthy before being considered ready to perform its work.

No single lifecycle event is sufficient to verify all of these conditions.

## 16. Distinguishing ConsumerStartingEvent from ApplicationReadyEvent

Spring Boot's `ApplicationReadyEvent` signals the stage where Spring Boot application startup has completed according to the framework. `ConsumerStartingEvent` is published by the Spring Kafka container at the milestone when the consumer thread starts.

The two events have different scopes:

~~~text
Spring Boot application startup
    |
    +-- Create beans / register @KafkaListener
    |
    +-- Start SmartLifecycle containers by phase
    |
    +-- ConsumerStartingEvent (may occur during startup)
    |
    +-- ApplicationReadyEvent (Spring Boot lifecycle)
~~~

Do not rely on an absolute ordering between every lifecycle event of every container and `ApplicationReadyEvent` across all configurations. `autoStartup=false`, custom lifecycle phases, dynamic listener creation, or stop/restart can cause consumer events to occur **after** Spring Boot is already ready.

With dynamically created containers, a background service can publish `ConsumerStartingEvent` at any time during the application's lifecycle, not just at process startup.

## 17. Why can an event appear multiple times?

Several situations generate additional `ConsumerStartingEvent` occurrences:

1. The application restarts and the container starts again.
2. An operator calls `stop()` and then `start()` on the listener container.
3. A child consumer is recreated according to the corresponding lifecycle/error recovery.
4. Another listener or a new dynamic listener is registered and started.
5. Multiple child consumers in a concurrent container start together.
6. Multiple application instances run the same listener ID.

Do not infer that each listener ID has only a single starting event over the lifetime of the system.

Several occurrences **do not mean** a new starting event is generated:

- A new Kafka record is polled.
- A `DefaultErrorHandler` retry on the same running consumer.
- A normal rebalance while the consumer thread still exists.
- Pausing/resuming the container without stopping/starting the consumer thread.

If a service counts starting events as "the consumer finished processing 1 batch", the metric will be completely wrong. This is a metric about **consumer task lifecycle**, not record throughput.

## 18. Combining ConsumerStartedEvent and ConsumerStoppedEvent

To observe a lifecycle rather than only the start milestone, listen to multiple event types:

~~~java
@Component
public class KafkaConsumerLifecycleLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerLifecycleLogger.class);

    @EventListener
    public void onStarting(ConsumerStartingEvent event) {
        log.info(
            "Kafka consumer STARTING: {}",
            event.getSource(MessageListenerContainer.class).getListenerId()
        );
    }

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        log.info(
            "Kafka consumer STARTED: {}",
            event.getSource(MessageListenerContainer.class).getListenerId()
        );
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        log.info(
            "Kafka consumer STOPPED: source={} reason={}",
            event.getSource(MessageListenerContainer.class).getListenerId(),
            event.getReason()
        );
    }
}
~~~

Event imports:

~~~java
import org.springframework.kafka.event.ConsumerStartingEvent;
import org.springframework.kafka.event.ConsumerStartedEvent;
import org.springframework.kafka.event.ConsumerStoppedEvent;
~~~

`ConsumerStoppedEvent` has a `reason` describing several stop causes such as normal, error, fencing, authentication, or no-offset depending on the version. There is no need to guess the reason by parsing exception logs.

If you want to compute startup latency, pair events belonging to the same **lifecycle instance** appropriately. Using only the listener ID across the entire cluster can mix data from different pods or multiple child consumers.

## 19. Example of tracking startup latency

An application can measure the time from receiving `ConsumerStartingEvent` to `ConsumerStartedEvent`. This is the duration between **two lifecycle milestones**, not the time from application start until business processing is ready.

Idea:

~~~text
ConsumerStartingEvent at t0
ConsumerStartedEvent  at t1

startup_transition_duration = t1 - t0
~~~

For reliable results:

- Use container source identity and instance identity to pair the two events.
- Do not use system timestamps from different pods in the same measurement if clocks are not synchronized.
- Store pairing state in thread-safe structures if concurrent events occur.
- Evict expired entries when a consumer never reaches the started milestone.
- Do not use overly granular dynamic consumer IDs as unbounded metric tags.

For aggregated metrics, use labels such as application, listener ID, or container type; avoid high-cardinality values like event ID, Kafka offset, or random thread ID. When investigating a specific consumer, use logs or tracing.

Note: if the consumer is blocked **after `ConsumerStartedEvent` but before a successful poll**, the measurement above does not reflect the full time to reach readiness. To measure readiness, additional observation conditions are required.

## 20. Metrics and alerts to build

| Signal | Meaning |
|---|---|
| Count of `ConsumerStartingEvent` by listener/instance | Consumer threads actually starting |
| Count of `ConsumerStartedEvent` | Threads reaching the pre-polling milestone |
| Count of `ConsumerFailedToStartEvent` | Consumer task startup exceeded timeout |
| Count of `ConsumerStoppedEvent` by reason | Why the consumer lifecycle ended |
| Duration from starting → started | Detects slow startup in the initialization phase |
| Listener container running state | Whether the container is started |
| Executor active threads and queue size | Detects consumer tasks lacking workers |
| Consumer group members/assignment | Whether consumers joined the group and received partitions |
| Consumer lag | Actual progress compared to the producer |
| Poll/processing error rate | Whether consumers are processing records successfully |
| Authentication/authorization failures | Credential/ACL errors, not to be confused with executor starvation |

A useful alert: `ConsumerFailedToStartEvent` increases after raising `concurrency` or adding listeners. In that case, prioritize checking the executor, thread capacity, and container configuration.

Another alert: many starting events appearing in succession on the same instance alongside abnormal stopped events. This can be a sign of lifecycle churn or a container restart loop; investigate the reason and deployment timing.

## 21. ConsumerStartingEvent and executor sizing

An initial sizing model:

~~~text
orders listener concurrency = 4
payments listener concurrency = 3
shipments listener concurrency = 2

Total long-lived consumer tasks: 9
~~~

If all of them share a fixed executor with 4 worker threads, at most four tasks have threads running concurrently; the remaining tasks risk never starting if the running tasks always hold their threads. Some containers may produce `ConsumerFailedToStartEvent` when `consumerStartTimeout` is exceeded.

There is no single thread-sizing formula for every system: Spring Kafka version, executor type, container concurrency, and workload can vary. However, you must ensure the executor serves **all long-lived consumer tasks adequately**.

Sizing steps:

1. List the number of `@KafkaListener` definitions and the concurrency of each container.
2. Identify which factories/containers share the listener task executor.
3. Check the executor's core/max pool size, queue capacity, and rejection policy.
4. Measure the number of live consumer threads after startup.
5. Observe starting/failed-to-start events under increased load.
6. Separate listener executors from other executors such as Kafka producer callbacks, database tasks, or application async jobs.
7. Do not share a small pool with long-blocking tasks if doing so can starve consumer tasks.

Increasing `consumerStartTimeout` can reduce alarms during slightly slow startups; it cannot create more threads when the pool is completely occupied.

## 22. Handling ConsumerFailedToStartEvent

An observer can log/alert:

~~~java
@Component
public class ConsumerStartupFailureObserver {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerStartupFailureObserver.class);

    @EventListener
    public void onFailed(ConsumerFailedToStartEvent event) {
        MessageListenerContainer container =
                event.getContainer(MessageListenerContainer.class);

        log.error(
            "Kafka consumer failed to start before timeout: container={}",
            container.getListenerId()
        );

        startupAlertPublisher.publish(container.getListenerId());
    }
}
~~~

`startupAlertPublisher` is an example component defined by the application. In production, send alerts asynchronously or through a safe mechanism that does not slow down the thread publishing the event.

When receiving this event, categorize the cause:

- **Executor starvation:** tasks lack threads.
- **Task rejected:** executor shutdown or queue/rejection policy.
- **Container did not actually start:** `autoStartup`, lifecycle phase, configuration error.
- **Startup block:** part of initialization occupies the thread or a dependency is blocked.
- **Monitoring/config mismatch:** the event listener is not registered in the right context, or the timeout configuration is too short for the real environment.

`ConsumerFailedToStartEvent` is **the symptom of not observing the starting event in time**. It does not by itself pinpoint the root exception or confirm that the broker is down.

## 23. Impact on Kubernetes readiness/liveness

A Kubernetes pod can run a Spring Boot HTTP server while the Kafka consumer has not started due to a lack of executor threads. If the readiness probe only checks HTTP 200 on a generic endpoint, the system may mark the pod ready even though background Kafka processing is not working.

Conversely, if the liveness probe requires the consumer to always be processing records, an empty topic or a maintenance pause can trigger unnecessary restarts.

A design approach:

- **Liveness:** the process and framework are still operational; do not use the absence of records as a reason to kill the pod.
- **Readiness:** depends on the service's role; may need to verify the consumer container is running, assignment exists, downstream capacity is available, or no startup failure occurred.
- **Startup probe:** allows adequate startup time for deployment and Kafka group joining.
- **Business health:** track lag, processing success, DLT, retries, and SLAs in observability.

`ConsumerStartingEvent` can supplement readiness information, but **should not be the sole condition**. If the system requires partition assignment, check assignment via the appropriate callback/API. If the consumer is intentionally paused for backpressure, the health policy must interpret pause properly rather than treating it as a crash.

## 24. What should and should not be done with the event?

### Do

- Write structured logs for consumer thread startup.
- Increment a consumer starting counter by listener/instance.
- Track the transition duration from starting to started.
- Correlate events with deployments/rollouts and concurrency changes.
- Detect executor starvation via `ConsumerFailedToStartEvent`.
- Track lifecycle churn when consumers are stopped/started frequently.
- Combine with container state, assignment, and consumer lag in dashboards.

### Do not

- Mark all listeners and business flows as READY solely from the starting event.
- Commit offsets, reset offsets, or seek the Kafka consumer inside a startup callback.
- Make long synchronous HTTP/database calls or sleep inside the event handler.
- Restart the container directly inside the callback without lifecycle ownership.
- Count this event as the number of Kafka records consumed.
- Assume one event corresponds to one partition.
- Assume `source` is always the parent container.
- Read the event and automatically scale out consumer concurrency without bounds.
- Use lifecycle events to replace error handlers, retries, DLTs, or poll error monitoring.

## 25. Scenario: consumer starts but receives no records

Suppose the logs record:

~~~text
11:00:01 ConsumerStartingEvent source=orders-consumer-0
11:00:01 ConsumerStartedEvent  source=orders-consumer-0
11:03:01 No business records processed
~~~

Possibilities:

1. The topic is empty and there are no new records.
2. The consumer group has committed offsets at the end of the log.
3. The consumer does not have a partition assignment yet or partitions were assigned to another member.
4. The consumer is paused.
5. The deserializer/poll encountered an error after startup.
6. Kafka ACL/authentication or broker connectivity has an issue.
7. The listener container is still running, but the listener is processing slowly or retrying a failing record.

How to investigate: check assignment, lag, `isConsumerPaused()`, consumer group membership, poll error logs, and error handler exceptions. Do not conclude the consumer is healthy just because `ConsumerStartingEvent` was seen.

## 26. Scenario: ConsumerFailedToStartEvent after increasing concurrency

Suppose before deployment:

~~~text
Listener orders concurrency=2
Executor active threads=2 / max=4
Starting events=2
Failed-to-start events=0
~~~

After deployment:

~~~text
Listener orders concurrency=8
Executor active threads=4 / max=4
Starting events=4
Failed-to-start events increasing
~~~

This is a sign easily associated with the executor lacking threads. Reducing concurrency to a suitable level or using an executor with sufficient capacity can resolve it; simply increasing the timeout will not allow the remaining four consumer tasks to run if the four-thread pool is held long-term.

If `concurrency` exceeds the number of partitions, efficiency should also be considered: adding consumer threads does not necessarily increase throughput. However, lacking partitions **does not by itself explain** why a task has no thread to publish the starting event; those are two different limits.

## 27. Scenario: repeated start/stop during rollout

Log example:

~~~text
12:00:00 STARTING orders-consumer-0
12:00:00 STARTED  orders-consumer-0
12:00:20 STOPPED  orders-consumer-0 reason=ABNORMAL
12:00:21 STARTING orders-consumer-0
12:00:21 STARTED  orders-consumer-0
12:00:42 STOPPED  orders-consumer-0 reason=ABNORMAL
~~~

Some repeated starts are normal during a rolling deployment or intentional operator restarts. However, **repeated abnormal stops** need investigation: producer fencing, auth failures, consumer exceptions, shutdown hooks, or container lifecycle logic.

Do not measure starting event counts without looking at stopped reasons and deployment versions. An increasing starting counter can be caused by system scale-out or a crash loop; the operational meaning is very different.

## 28. Guide to testing the event in an application

When developing a listener startup observer, you can design integration tests to observe the event:

1. Start the Spring application context with an explicitly configured `@KafkaListener` and container factory.
2. Register `@EventListener(ConsumerStartingEvent.class)` before the container starts.
3. Start the container and wait for the event using a latch or test event collector.
4. Verify that the event has the expected source/container references.
5. If using a concurrent container, observe multiple child consumer starting events.
6. Stop and restart the listener container, and observe the new startup event.
7. Verify that `ConsumerStartingEvent` is not treated as synonymous with partition assignment.
8. Intentionally create an executor thread-starvation environment to observe the startup timeout.
9. Verify that the event handler does not hang consumer startup.
10. After the test, shut down the container/executor so threads do not leak.

Example of an event-collecting component for testing purposes:

~~~java
@Component
public class ConsumerStartingEventCollector {

    private final BlockingQueue<String> startedSources =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onStarting(ConsumerStartingEvent event) {
        String sourceId = event
                .getSource(MessageListenerContainer.class)
                .getListenerId();

        startedSources.offer(sourceId);
    }

    public String awaitStarting(long timeout, TimeUnit unit)
            throws InterruptedException {
        return startedSources.poll(timeout, unit);
    }
}
~~~

In production, there is no need to keep an unbounded queue of events if nothing is reading them. The collector above is an example for short-lived tests; real systems should use metrics/logging or bounded data structures.

The scenarios above only explain how to build tests; authoring this lesson did not run content QA or a test application.

## 29. Runbook: ConsumerStartingEvent not seen

When a `@KafkaListener` is expected to run but does not publish the event:

1. **Check whether the listener is registered:** correct `@KafkaListener`, bean scanning, and configuration.
2. **Check whether the container exists:** use `KafkaListenerEndpointRegistry` with the listener ID.
3. **Check lifecycle:** `isRunning()`, `autoStartup`, lifecycle phase, and whether anything called `stop()`.
4. **Check concurrency:** how many child consumers actually need to run?
5. **Check the task executor:** pool size, active threads, queue length, and rejections.
6. **Check startup timeout:** `consumerStartTimeout` and whether `ConsumerFailedToStartEvent` is present.
7. **Check logging/event registration:** is the `@EventListener` bean in the right application context?
8. **Check startup blockers:** initialization of the consumer factory, deserializer, metrics hooks, and thread startup.
9. **If ConsumerStartedEvent is already seen but still no records:** switch to investigating assignment, polling, auth, and lag; stop treating it as a thread startup error.
10. **Remediate and monitor:** confirm starting/started events and that the consumer group operates as required.

Do not reset Kafka offsets or change `auto.offset.reset` just because the starting event is missing: these two mechanisms solve different problems.

## 30. Runbook: event is present but consumer is still not ready

An event arriving does not mean the Kafka data path is working. Check in order:

1. Is the consumer thread still alive and the container still running?
2. Has the consumer started polling, and are there error logs during poll?
3. Has the consumer group joined and been assigned partitions?
4. Are the topic, group ID, ACLs, and broker bootstrap configuration correct?
5. Is the consumer paused due to backpressure or maintenance?
6. Did the deserializer hit a poison record causing poll to fail at a fixed offset?
7. Is the listener retrying a record and holding the partition?
8. Are database/HTTP downstream services responding?
9. Is lag decreasing or is offset progress meeting requirements?
10. Is DLT increasing abnormally?

If the root cause is a schema/deserialization error, the solution lies in `ErrorHandlingDeserializer`, exception classification, and recovery. If the root cause is executor starvation before startup, the solution lies in thread capacity. Do not use a single event to replace the entire diagnosis.

## 31. ConsumerStartingEvent design checklist

- [ ] Understand that the event is published when the consumer thread starts, before polling.
- [ ] Distinguish `ConsumerStartingEvent` from `ConsumerStartedEvent` and `ConsumerFailedToStartEvent`.
- [ ] Use `@EventListener` or `ApplicationListener<ConsumerStartingEvent>`.
- [ ] Understand that `getSource(Class)` is the container publishing the event and `getContainer(Class)` may be the parent.
- [ ] Handle concurrency: multiple child consumers can publish multiple events.
- [ ] Filter by the appropriate listener/container ID; do not assume `source` is always the parent.
- [ ] Do not treat the starting event as partition assignment, record processing, or readiness.
- [ ] Do not run long blocking I/O inside a synchronous callback.
- [ ] Do not manipulate `KafkaConsumer` from an async event handler.
- [ ] Observe `consumerStartTimeout` and `ConsumerFailedToStartEvent`.
- [ ] Size the executor adequately for long-lived consumer tasks.
- [ ] Monitor running state, assignment, lag, stopped reason, and retry/DLT alongside startup events.
- [ ] Distinguish startup after restart/scaling from an abnormal startup loop.
- [ ] Maintain runbooks for when the event is missing and when the event is present but the consumer is not yet operating.

## 32. References

- [Spring Kafka Reference — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
- [Spring Kafka API — ConsumerStartingEvent](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/event/ConsumerStartingEvent.html)
- [Spring Kafka API — KafkaEvent](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/event/KafkaEvent.html)

**Conclusion:** `ConsumerStartingEvent` is a very early lifecycle signal for a Spring Kafka consumer: **the thread starts initializing before polling**. It supports startup tracing, monitoring consumer thread counts, and combining with `ConsumerFailedToStartEvent` to diagnose thread exhaustion in the executor. To confirm that a consumer is truly ready, additional signals are needed for container running state, polling, assignment, dependency health, lag, and business processing. A reliable application must clearly distinguish between **thread started**, **polling started**, and **capable of processing data safely**.
