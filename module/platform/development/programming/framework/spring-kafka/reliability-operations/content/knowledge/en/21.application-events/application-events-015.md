# Listener ID and condition for event filtering

In Spring Kafka, a listener container does more than receive messages from Kafka and invoke `@KafkaListener`. It also emits **Spring Application Events** reflecting operational status: consumer starting or stopping, container idle, partitions paused/resumed, consumer unresponsive to expected polling, and more.

An application can have dozens of Kafka listeners all publishing events into the **ApplicationContext**. If every event handler reacts to every container, monitoring becomes noisy, alerts misfire, or a control task may act on the wrong listener. To solve this, Spring Kafka includes **listener ID** information in container events, and Spring Framework provides the **condition** attribute on **@EventListener** to filter events before invoking the handler.

This lesson in the **Application events** chapter of **Spring Kafka Reliability Operations** focuses on:

- Setting stable listener IDs and understanding how they differ from consumer group IDs.
- Reading listener IDs from Spring Kafka Application Events.
- Using **@EventListener(condition = "...")** with Spring Expression Language (SpEL) to receive only events for the listener of interest.
- Handling cases cleanly when a listener has concurrency greater than one, leading to child containers and suffixed listener IDs.
- Distinguishing annotation-based filtering from checks in Java code.
- Avoiding running event handling on the wrong thread, false alerts, and controlling the wrong container in production.

## 1. What are Spring Kafka Application Events?

A Kafka listener container is the Spring component managing the Kafka consumer lifecycle and listener invocation. During operation, it can publish events through Spring's **ApplicationEventPublisher**. Beans in the same `ApplicationContext` can receive those events via `@EventListener`.

~~~mermaid
flowchart LR
    K["Kafka broker"] --> C1["Container orders-consumer"]
    K --> C2["Container payments-consumer"]
    C1 --> A["Spring ApplicationEventPublisher"]
    C2 --> A
    A --> E1["@EventListener idle handler"]
    A --> E2["@EventListener pause handler"]
    A --> E3["@EventListener lifecycle handler"]
~~~

This approach decouples message-consumption business logic from container-activity observation. For example:

- The listener processes order records normally.
- The container starts going idle due to no records.
- Spring Kafka publishes `ListenerContainerIdleEvent`.
- An `@EventListener` receives the event and updates observational state.

Application events are **internal Spring application events**. They **are not by default Kafka records** sent to a topic and are not a durable cross-service communication mechanism.

### 1.1 Some useful event types

| Event | Typical scenario | Operational usage |
|---|---|---|
| `ListenerContainerIdleEvent` | No records within the configured idle interval | Observe an idle listener |
| `ListenerContainerNoLongerIdleEvent` | Listener receives records again after idle | Confirm consumption stream is active again |
| `ConsumerPausedEvent` | Consumer paused partitions | Record backpressure state |
| `ConsumerResumedEvent` | Consumer resumed partitions | Confirm consumption activity resumed |
| `ConsumerStartedEvent` | Consumer container thread started | Track lifecycle |
| `ConsumerStoppedEvent` | Consumer stopped for a reason | Alert on abnormal shutdown |
| `NonResponsiveConsumerEvent` | Poll unusually delayed relative to monitoring threshold | Investigate blocked consumer |
| `ConsumerPartitionPausedEvent` | A partition was paused | Observe per-partition throttling |
| `ConsumerPartitionResumedEvent` | A partition was resumed | Observe partition state |

Available classes and accessors can vary between Spring Kafka versions. Register only event types actually present in your project's dependency; do not apply newer APIs to older versions.

### 1.2 Not every event is an error

`ListenerContainerIdleEvent` **does not by itself prove Kafka is broken**. The topic may be healthy yet have no new records. `ConsumerPausedEvent` may result from an intentional pause issued by an operator. `ConsumerStoppedEvent` can occur during normal rolling deployments.

Handlers must consider **event type**, **listener ID**, **cause**, and **operational context** before raising alerts or automated actions.

## 2. What is Listener ID used for?

With `@KafkaListener`, the **id** attribute identifies the listener endpoint/container in Spring.

~~~java
@Component
public class OrdersListener {

    @KafkaListener(
        id = "orders-projection",
        topics = "orders.created",
        groupId = "orders-projection-group"
    )
    public void onOrder(OrderCreated event) {
        // Business processing.
    }
}
~~~

Here:

- **orders-projection** is the `@KafkaListener` endpoint ID inside the application.
- **orders.created** is the source Kafka topic.
- **orders-projection-group** is the Kafka consumer group ID.

One practical use of the listener ID is retrieving the container from **KafkaListenerEndpointRegistry**:

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-projection");
~~~

If no ID is explicitly set, Spring may generate an ID based on how the endpoint/container was registered. Auto-generated IDs are hard to keep stable across refactors and are unsuitable as a contract for monitoring or event routing.

### 2.1 Listener ID, group ID, and client ID differ

| Attribute | Purpose | Can replace listener ID when filtering Spring events? |
|---|---|---|
| `@KafkaListener.id` | Identifies endpoint/container in Spring | Yes, serves as the identifier basis |
| `@KafkaListener.groupId` | Kafka consumer group managing partition assignment and offsets | Not by default |
| `@KafkaListener.clientIdPrefix` | Prefix generating Kafka consumer `client.id` | Not by default |
| Topic name | Data subscribed by Kafka consumer | Not by default |
| Event `listenerId` | ID in the Application Event emitted by container | Used for filtering; may carry a child suffix |

Kafka **group ID** is typically shared across multiple pods and consumers splitting load. Listener ID is used to distinguish endpoints within an application context; events from a child consumer can carry an ID extended from the parent.

### 2.2 Caution with idIsGroup

In Spring Kafka, `@KafkaListener.id` can be used as the consumer group ID when no separate `groupId` is provided and **idIsGroup** keeps its default value of true.

Example:

~~~java
@KafkaListener(
    id = "orders-projection",
    topics = "orders.created"
)
public void onOrder(OrderCreated event) {
    // ...
}
~~~

Without an explicit `groupId` configuration, the effective `group.id` may become **orders-projection** rather than the `group.id` configured on `ConsumerFactory` as a developer might expect.

A clearer, less error-prone style:

~~~java
@KafkaListener(
    id = "orders-projection",
    topics = "orders.created",
    groupId = "orders-projection-group"
)
~~~

Or when intentionally using the group ID from the consumer factory, configure `idIsGroup=false` per your version's API.

**Changing a listener ID should not accidentally change the Kafka group ID**. A new group ID creates a new committed-offset namespace, leading to replaying or skipping records depending on `auto.offset.reset` and offset state.

## 3. How does an event carry listenerId?

Spring Kafka container events typically expose a **getListenerId()** accessor indicating which container/listener published the event.

Example idle-observing handler:

~~~java
@Component
public class KafkaIdleLogger {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaIdleLogger.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
            "Kafka listener idle: listenerId={}, idleTime={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }
}
~~~

This method receives every `ListenerContainerIdleEvent` in the `ApplicationContext` where it is registered, regardless of whether the event belongs to orders, payments, or inventory.

If the same application has three listeners:

~~~text
orders-projection
payments-settlement
inventory-sync
~~~

an unfiltered handler will receive idle events from all three. If the handler uses that event to alert against orders' SLA, it will raise false alerts for payments or inventory.

### 3.1 Listener ID can differ from the annotation ID

With `concurrency=1`, an event's `listenerId` may match the endpoint ID. With **ConcurrentMessageListenerContainer**, Spring Kafka typically creates multiple child containers and identifies children with suffixes, for example:

~~~text
Parent @KafkaListener id:
  orders-projection

Child container identifiers:
  orders-projection-0
  orders-projection-1
  orders-projection-2
~~~

This is a common convention; do not hard-code suffix assumptions across all custom containers or every version. Observe **the actual runtime `event.getListenerId()` value**.

If a filter only checks exact equality with the string `orders-projection`, it may miss child events carrying suffixes.

### 3.2 Filtering by container is filtering by source

Listener ID identifies **the container publishing the event**, not necessarily a specific Kafka topic, Kafka partition, or record.

One container can subscribe to multiple topics. One group can have multiple containers. A container with concurrency > 1 can consist of multiple child consumers.

If you need to filter by partition or error type, use corresponding metadata or additional business logic. Filtering by listener ID alone is insufficient to determine which partition is failing.

## 4. Where is @EventListener(condition) evaluated?

Spring Framework provides **condition** on `@EventListener`. The condition is a **Spring Expression Language (SpEL)** expression evaluated before invoking the listener method.

If the condition evaluates to false, Spring **does not call that method** for the matching event.

Simple example:

~~~java
@Component
public class OrdersIdleEvents {

    @EventListener(
        condition = "#root.event.listenerId == 'orders-projection'"
    )
    public void onOrdersIdle(ListenerContainerIdleEvent event) {
        // Handle only events whose listenerId equals orders-projection.
    }
}
~~~

Here:

- Spring selects the method because the parameter type is `ListenerContainerIdleEvent`.
- SpEL reads `listenerId` from the event.
- The method runs only if the condition is true.

This provides **two filtering layers**: the **event type** layer and the **event property** layer. The condition does not stop Spring Kafka from publishing the event; it only decides whether this handler gets invoked.

### 4.1 SpEL can access the event

In Spring `@EventListener` expressions, the event can be accessed via the root object, such as **#root.event**, or event/argument syntaxes supported by your current Spring Framework version.

Example:

~~~java
@EventListener(
    condition = "#root.event.listenerId.startsWith('orders-')"
)
public void onIdle(ListenerContainerIdleEvent event) {
    // ...
}
~~~

Using `#root.event` in the example clarifies that the expression references **the published event**, not a local Java variable in the method.

When using parameter-name expressions such as `#event`, pay attention to compiler flags preserving parameter names and Spring Framework version semantics. When compiled without parameter-name metadata, name-based expressions may not work as expected. Root event or argument index is usually clearer in portable examples.

### 4.2 Conditions should be short and side-effect free

SpEL filters are evaluated during Application Event dispatch. Do not use conditions to:

- Make HTTP requests.
- Call databases.
- Mutate container state.
- Increment/decrement metrics or send Kafka records.
- Run heavy logic that could block the consumer event thread.

Use conditions for fast filtering on immutable metadata, then perform primary handling inside the method.

## 5. Example filtering ListenerContainerIdleEvent by ID

Suppose you only want to track idle state for `orders-projection`.

### 5.1 Equality filtering

~~~java
@Component
public class OrdersIdleMonitor {

    @EventListener(
        condition = "#root.event.listenerId == 'orders-projection'"
    )
    public void handle(ListenerContainerIdleEvent event) {
        log.warn(
            "Orders consumer idle: listenerId={} idleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }
}
~~~

Equality works when `event.listenerId` is strictly `orders-projection` with no suffix. If the listener container has concurrency and child IDs, equality can miss events.

### 5.2 Filtering with startsWith

~~~java
@Component
public class OrdersIdleMonitor {

    @EventListener(
        condition = "#root.event.listenerId.startsWith('orders-projection')"
    )
    public void handle(ListenerContainerIdleEvent event) {
        log.info(
            "Orders idle from child container: {}",
            event.getListenerId()
        );
    }
}
~~~

This predicate matches `orders-projection` as well as `orders-projection-0`, `-1`, `-2`. However, it also matches an ID like **orders-projection-v2**.

Therefore, `startsWith` requires **naming rules preventing prefix collisions** or a tighter predicate.

### 5.3 Predicate for numeric child suffix

If the application uses a specific convention of parent ID + hyphen + digits, you can write:

~~~java
@EventListener(
    condition =
        "#root.event.listenerId == 'orders-projection' " +
        "|| #root.event.listenerId matches '^orders-projection-[0-9]+$'"
)
public void onIdle(ListenerContainerIdleEvent event) {
    // Receive only the parent and child IDs matching the chosen convention.
}
~~~

The expression illustrates using SpEL **matches** for regular expressions. Check runtime IDs and Spring expression parsing against your actual version before treating the pattern as a long-term contract.

Complex regex inside annotations can be hard to maintain; when logic branches heavily or needs dynamic config, moving filtering into Java code is often easier.

## 6. Enable idle events so there are events to filter

You cannot simply declare `@EventListener` and expect `ListenerContainerIdleEvent` to always appear. The container must be configured with an appropriate **idleEventInterval**.

Example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties()
           .setIdleEventInterval(10_000L);

    return factory;
}
~~~

The example illustrates a 10-second interval. Exact timing and emission frequency also depend on polling, container scheduling, and Spring Kafka version.

### 6.1 Idle does not equal failure

Listener idle can occur when:

- Producers have no new events.
- Topic is active yet traffic is low.
- Consumer already read up to log end.
- Consumer is paused.
- Partition assignment changed.
- Consumer has a real issue preventing records from reaching the listener.

A standalone idle event is not enough for a high-severity alert. Cross-check producer rate, consumer lag, assignments, pause status, poll metrics, and business freshness indicators.

### 6.2 Idle duration is metadata, not proof of data loss

When `event.getIdleTime()` reports how long the listener has been idle, that is an observational metric. It does not prove the Kafka broker lacks records, nor does it mean the consumer stopped polling.

For services receiving orders seasonally or on schedule, being idle for a few minutes can be completely normal. For systems receiving continuous transactions, sudden idle can be a signal to investigate.

## 7. Filtering pause/resume events by listener

Spring Kafka can publish **ConsumerPausedEvent** and **ConsumerResumedEvent** when consumers pause/resume along the lifecycle.

~~~java
@Component
public class OrdersPauseMonitor {

    @EventListener(
        condition = "#root.event.listenerId.startsWith('orders-projection')"
    )
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
            "Orders Kafka consumer paused: id={}, partitions={}",
            event.getListenerId(),
            event.getPartitions()
        );
    }

    @EventListener(
        condition = "#root.event.listenerId.startsWith('orders-projection')"
    )
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
            "Orders Kafka consumer resumed: id={}, partitions={}",
            event.getListenerId(),
            event.getPartitions()
        );
    }
}
~~~

With concurrent containers, there may be one event per child/consumer or paused partition set. Never infer **the entire listener paused** simply from receiving one `ConsumerPausedEvent`.

### 7.1 Pause requested differs from consumer paused

When the application calls `container.pause()`, that is a **request**. The container applies pause at an appropriate point on the consumer thread. If `pauseImmediate` is enabled, pause may take effect after the current record; otherwise, the container may finish processing records from the current poll.

Therefore:

- A `container.pause()` call returning does not mean the consumer is immediately paused.
- `ConsumerPausedEvent` is a signal of the actual pause taking effect.
- With `concurrency > 1`, children may pause at different times.
- If parent state is needed, use APIs such as `isConsumerPaused()` per your container/version and observe all children.

### 7.2 Do not use pause events to issue repeated pause commands

A `ConsumerPausedEvent` handler runs because the container already paused; it should normally **record state**, not call `container.pause()` unconditionally again.

Similarly, a `ConsumerResumedEvent` handler should not emit repeated resumes in a cycle.

## 8. Filtering lifecycle events

Application events also help observe consumers starting and stopping. Example:

~~~java
@Component
public class OrdersLifecycleMonitor {

    @EventListener(
        condition = "#root.event.listenerId.startsWith('orders-projection')"
    )
    public void onStarted(ConsumerStartedEvent event) {
        log.info("Orders consumer started: {}", event.getListenerId());
    }

    @EventListener(
        condition = "#root.event.listenerId.startsWith('orders-projection')"
    )
    public void onStopped(ConsumerStoppedEvent event) {
        log.warn(
            "Orders consumer stopped: {}, reason={}",
            event.getListenerId(),
            event.getReason()
        );
    }
}
~~~

The snippet illustrates event types and accessors on the corresponding Spring Kafka line. If your version has different APIs or stop-reason enums, adjust imports/methods accordingly.

### 8.1 Do not alert every stop as an incident

A consumer can stop due to:

- Application shutdown.
- Rolling deployment.
- User/operator stop.
- Authentication or authorization problems.
- Fatal errors.
- Other framework-defined causes.

Always combine **reason**, deployment status, and expected lifecycle. Otherwise, every deploy can trigger a "consumer crashed" alarm even during normal shutdowns.

### 8.2 Distinguishing container lifecycle from consumer lifecycle

One `@KafkaListener` can correspond to a parent `ConcurrentMessageListenerContainer` and multiple child consumer instances. `ConsumerStartedEvent` can be emitted at the child level. Event counts can exceed the number of `@KafkaListener` annotations.

When calculating healthy instance counts, never use "one event = one listener annotation." Group by listener ID, child consumer client ID, and appropriate assignment.

## 9. Condition by event type and listenerId

The method argument in `@EventListener` filters by **event class**. Condition filters by **instance metadata**.

For example, the same `ApplicationContext` has three event occurrences:

~~~text
ListenerContainerIdleEvent(listenerId=orders-projection-0)
ConsumerPausedEvent(listenerId=orders-projection-0)
ConsumerStoppedEvent(listenerId=payments-collector-0)
~~~

The following handler receives only idle events belonging to orders:

~~~java
@EventListener(
    condition = "#root.event.listenerId.startsWith('orders-projection')"
)
public void onOrdersIdle(ListenerContainerIdleEvent event) {
    // ...
}
~~~

It does not receive orders' `ConsumerPausedEvent`, because the method parameter type does not match.

If you want to observe multiple event types, create multiple methods with the same predicate or consolidate logic into a shared service.

### 9.1 Do not confuse @EventListener(condition) with @KafkaListener filtering

Spring Kafka also has **RecordFilterStrategy** and mechanisms to filter records before business listeners process them. Those are different:

| Technique | Which kind of data is filtered? |
|---|---|
| `@EventListener(condition)` | Spring Application Events, e.g., `ConsumerPausedEvent` |
| `RecordFilterStrategy` | Kafka `ConsumerRecord` received from the broker |
| `@KafkaListener(topics, topicPattern)` | Kafka topics subscribed by the listener |
| Kafka consumer assignment | Partitions belonging to the consumer in the group |
| `@KafkaListener(groupId)` | Consumer group offsets and partition distribution |

`@EventListener(condition)` does not make the Kafka broker send fewer records; it only reduces irrelevant **event handler invocations**.

## 10. Conditions with null and defensive filtering

Some application events may originate from custom containers or different framework versions. If a handler is declared on a broad base event type, do not assume every event has a non-null `listenerId`.

A null-safe condition:

~~~java
@EventListener(
    condition =
        "#root.event.listenerId != null " +
        "&& #root.event.listenerId.startsWith('orders-projection')"
)
public void onOrdersIdle(ListenerContainerIdleEvent event) {
    // ...
}
~~~

In SpEL, the `&&` operator performs short-circuit boolean evaluation per expression semantics, preventing `startsWith` from being invoked when `listenerId` is null.

### 10.1 If the condition does not match yet events still exist

Suppose the handler is never called at all:

- Is Spring Kafka publishing the expected event type?
- Was the idle event interval enabled?
- Is the bean containing `@EventListener` component-scanned by Spring?
- Do the publisher context and event listener share the same `ApplicationContext` or appropriate propagation relationship?
- Does `event.listenerId` actually have a suffix?
- Does the condition have a wrong ID, wrong case, or regex error?
- Can the SpEL expression parse and evaluate?
- Was an exception in event dispatch hidden by logging?

Do not "fix" it by stripping all conditions and monitoring everything indiscriminately. Log metadata in a time-bounded debug handler or use selective instrumentation.

### 10.2 Setting stable IDs

A listener ID can become an operational contract, yet it remains internal Spring configuration. When renaming an ID, update:

- `@EventListener` conditions.
- `KafkaListenerEndpointRegistry` lookups.
- Monitoring dashboards and alert labels.
- Pause/resume control automation.
- Event integration tests.

Do not change IDs frequently using build timestamps or deployment UUIDs if monitoring needs to recognize the same logical listener. If you need to distinguish pods, add instance ID or client ID instead.

## 11. Prefix-style conditions: collision risks

Suppose you have listeners:

~~~text
orders-projection
orders-projection-v2
orders-projection-canary
~~~

The condition:

~~~java
@EventListener(
    condition = "#root.event.listenerId.startsWith('orders-projection')"
)
~~~

will match all three, even if the author only wanted the old production listener.

### 11.1 Establishing a naming convention

An illustrative convention:

~~~text
orders-main
orders-main-0
orders-main-1

orders-canary
orders-canary-0
orders-canary-1

payments-main
payments-main-0
~~~

Caution is still required if using prefix `orders-main` while an ID `orders-main-v2` exists. To be unambiguous, use regex matching exact parent and numeric children or a Java helper.

### 11.2 When to drop condition and filter in Java?

If the condition must simultaneously check:

- A list of listener IDs loaded from configuration.
- Complex naming regex rules.
- Specific topic-partitions.
- `ConsumerStoppedEvent` reason.
- Environment or tenant.
- Runtime feature flags.

then Java code inside the method can be easier to read, unit-test, and log.

~~~java
@Component
public class OrdersIdleMonitor {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {

        if (!belongsToOrdersMain(event.getListenerId())) {
            return;
        }

        log.info("Orders main idle: {}", event.getListenerId());
    }

    private boolean belongsToOrdersMain(String id) {

        if (id == null) {
            return false;
        }

        return id.equals("orders-main")
            || id.matches("orders-main-[0-9]+");
    }
}
~~~

With this approach, `@EventListener` is invoked for every idle event yet the method can return early. The trade-off is some unnecessary method invocations in exchange for simpler testing and predicate changes.

## 12. Conditions with SpEL property and method invocation

In SpEL, Java bean properties can be read via property-style access. For example:

~~~text
#root.event.listenerId
~~~

references the `listenerId` property through the event's corresponding accessor. String methods like `startsWith` can be invoked when permitted by the evaluation context.

Example expressions:

| Expression | Meaning |
|---|---|
| `#root.event.listenerId == 'orders-main'` | Exact listener ID |
| `#root.event.listenerId.startsWith('orders-')` | Prefix matching |
| `#root.event.listenerId != null` | Ignore events lacking an ID |
| `#root.event.listenerId matches '^orders-main-[0-9]+$'` | Regex for child IDs following convention |
| `#root.event.listenerId != 'payments-main'` | Exclude one ID |

There is no need to create a new application event solely for filtering. Remember, however, that different event types have different properties: a condition using `getIdleTime()` will not apply to `ConsumerStoppedEvent`.

### 12.1 Prefer property metadata, not payloads

Container events do not represent business Kafka records; they typically carry no `OrderCreated` payload like a listener receives. Relying on `listenerId`, partition sets, idle duration, or reason is the right abstraction level.

If you need to filter business data, place that rule inside consumer record processing or validation, not in an application event condition.

## 13. Concurrency and child event IDs

With `@KafkaListener` `concurrency=3`, Spring Kafka can create three child consumers. Events may arrive in varying order:

~~~text
ConsumerStartedEvent id=orders-main-0
ConsumerStartedEvent id=orders-main-2
ConsumerStartedEvent id=orders-main-1
ConsumerPausedEvent  id=orders-main-1
ConsumerPausedEvent  id=orders-main-0
ConsumerPausedEvent  id=orders-main-2
~~~

Do not assume event arrival order reflects a single atomic state transition of the parent.

### 13.1 Grouping by logical listener

When monitoring needs an overall status, identify:

- Parent listener ID.
- Actual child IDs.
- Count of running child consumers.
- Count of paused children.
- Partition assignments and per-partition state.
- Event timestamps and instance version.

A parent with three children receiving one `ConsumerPausedEvent` does not mean the entire listener is paused.

### 13.2 Do not mix events from multiple pods into one local state

Spring Application Events are local to a single JVM/`ApplicationContext`. Pod A and Pod B each have their own events. For deployment-wide dashboards, export metrics/traces with labels **service, pod/instance, listenerId, clientId**.

An in-memory `Map` updated from events only reflects the process it lives in; it cannot reliably know consumer states on other pods.

### 13.3 Prefix matching requires checking runtime IDs

Sometimes child IDs are assigned by the framework using different rules when creating custom containers, assigning partitions manually, or using container beans outside `@KafkaListener`. Therefore, before attaching production alerts, inspect actual `listenerId` logs and then choose equality, `startsWith`, or regex.

## 14. Threading of ApplicationEvent listeners

By default, Spring `ApplicationEventMulticaster` normally dispatches event listeners synchronously on the event-publishing thread. For Spring Kafka container events, that thread may be **the consumer thread**.

This creates a risk: if `@EventListener` executes a slow HTTP request or a 30-second database query, it can block the consumer thread and slow down polling.

### 14.1 Event handlers should be lightweight

Prefer:

~~~java
@EventListener(
    condition = "#root.event.listenerId.startsWith('orders-main')"
)
public void onPaused(ConsumerPausedEvent event) {

    meterRegistry.counter(
        "kafka_container_paused_total",
        "listenerId", event.getListenerId()
    ).increment();
}
~~~

In production, control metric label cardinality. If listener IDs contain too many UUID/pod-unique suffixes, time series counts can explode. The snippet above illustrates only a simple metric.

Avoid:

~~~java
@EventListener
public void onPaused(ConsumerPausedEvent event) {

    // Anti-pattern: can block the consumer event thread.
    remoteAuditService.callSlowExternalApi(event);
}
~~~

If long processing is needed, hand off copied metadata to a separate bounded executor or monitoring pipeline; never retain a `KafkaConsumer` reference for asynchronous use.

### 14.2 Async ApplicationEventMulticaster

Spring allows configuring `ApplicationEventMulticaster` asynchronously. Then event listeners may run on a different thread from the consumer thread.

Consequences:

- Never call `KafkaConsumer` methods from an async event listener.
- Do not assume events are processed immediately or strictly in order.
- Some events carry consumer references safe only on the original thread.
- If container control is needed, use `MessageListenerContainer` APIs.
- Design bounded queues, error handling, and shutdown for the async executor.

Switching the multicaster to async can affect all other Application Events in the context, not just Spring Kafka events. Assess the scope of change.

### 14.3 Never block or stop the container directly inside consumer event callbacks

Some Spring Kafka event callbacks run on the consumer thread. Performing lifecycle operations that wait on the very thread dispatching the event can cause deadlocks or delays.

If you need to stop the container when idle too long, a safer approach is signaling another executor/controller to coordinate stop per the corresponding Spring Kafka version's API. Never call `consumer.close()`, `consumer.seek()`, or other dangerous operations directly from an event handler without understanding thread ownership.

## 15. Using events for controlled pause/resume

One use case is watching downstream overload and pausing the right listener. Still, Application Events should primarily serve **state observation**, while pause/resume decisions should belong to a component with clear ownership.

Example fetching container by ID:

~~~java
@Service
public class OrdersContainerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersContainerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {

        MessageListenerContainer c =
            registry.getListenerContainer("orders-projection");

        if (c != null && !c.isPauseRequested()) {
            c.pause();
        }
    }

    public void resumeOrders() {

        MessageListenerContainer c =
            registry.getListenerContainer("orders-projection");

        if (c != null && c.isPauseRequested()) {
            c.resume();
        }
    }
}
~~~

The container registry uses the **parent endpoint ID** from `@KafkaListener`. A child event ID might be `orders-projection-0`, yet looking up the registry by child suffix will not necessarily return the expected container.

### 15.1 Never attach pause actions to every idle event

Idle because **the topic has no traffic** can be a healthy state. Calling pause because of idle prevents the container from receiving new records when producers resume activity unless another mechanism resumes it.

Do not design a loop:

~~~text
idle event -> pause
pause -> stays idle
idle event -> pause
...
~~~

Only pause when there is a real reason such as downstream overload, maintenance, or backpressure with a clear resume condition.

### 15.2 Tracking status after requests

When a controller calls `pause()`:

1. The request is recorded.
2. The container applies pause on the consumer loop, possibly after the current record.
3. `ConsumerPausedEvent` is published.
4. Monitoring updates status.
5. On resume, `ConsumerResumedEvent` confirms recovery.

Do not use an event filter to automatically conclude that **all** children paused; aggregate across children or use container state APIs.

## 16. When multiple ApplicationContexts exist

In a standard Spring Boot application, Spring Kafka containers and `@EventListener` beans reside in the same `ApplicationContext`. With parent/child contexts or complex integration tests, events may propagate through the context hierarchy.

Consequences:

- An `@EventListener` may be invoked by events from a child context.
- Multiple listeners may share the same logical ID across different contexts.
- A predicate checking only `listenerId` may fail to distinguish the source context.
- A metric aggregator may double-count if events propagate across multiple levels.

If the application has a hierarchy, design filtering by source/context appropriately rather than relying solely on prefix IDs. In single-context applications, this is usually not an issue.

## 17. Maintainable event handler architecture

As listener counts grow, avoid building one class with dozens of repetitive SpEL conditions and hardcoded IDs lacking convention.

A pragmatic organization:

~~~text
Application events
  -> KafkaContainerEventObserver
       - receive key event types
       - identify listenerId
       - normalize metric/log labels
       - emit operational signals
  -> BackpressureController
       - owns pause policy
       - looks up container by endpoint ID
       - decides pause/resume from downstream state
  -> Alerting
       - uses metrics and SLAs
       - never calls KafkaConsumer directly
~~~

### 17.1 Condition for simple filtering

Example:

~~~java
@EventListener(
    condition = "#root.event.listenerId.startsWith('orders-main')"
)
public void onOrdersIdle(ListenerContainerIdleEvent event) {
    ordersMetrics.recordIdle(event.getListenerId(), event.getIdleTime());
}
~~~

### 17.2 Java predicates for complex logic

Example:

~~~java
@EventListener
public void onConsumerStopped(ConsumerStoppedEvent event) {

    if (!listenerPolicy.isMonitored(event.getListenerId())) {
        return;
    }

    if (!shutdownPolicy.isExpected(event)) {
        alerting.reportUnexpectedStop(
            event.getListenerId(),
            event.getReason()
        );
    }
}
~~~

This allows unit-testing `listenerPolicy` and `shutdownPolicy` independently while keeping logs explaining why an event was ignored.

### 17.3 Never treat event handlers as consumers of a durable stream

Spring Application Events are not a Kafka topic with committed offsets. If the JVM dies while publishing an event or the event listener is not running, events are not automatically replayed after restart.

Critical events needing durable auditing must be turned into metrics/logs or durable audit events through a pipeline with appropriate retries and error handling. Never rely on Application Events as the sole historical store.

## 18. Scenario: condition filters the wrong listener

Suppose the orders idle handler receives payments events too, or receives no orders events at all.

### 18.1 Investigation checklist

1. Verify `@KafkaListener.id` and `idIsGroup`/`groupId`.
2. Verify listener container factory and concurrency.
3. Temporarily register a handler logging only `event.getListenerId()` for the target event type.
4. Check for child suffixes or custom container bean names.
5. Check whether the SpEL condition uses equality, prefix, or regex.
6. If using prefixes, check for collisions between `orders-main` and `orders-main-v2`.
7. If using named parameter `#event`, check Java compile metadata; consider `#root.event`.
8. Confirm the bean containing `@EventListener` is Spring-managed.
9. Confirm the event is actually published by verifying `idleEventInterval` or lifecycle state.
10. Check `ApplicationContext` hierarchy and asynchronous multicaster config.
11. Never alter Kafka `group.id` just to fix an event filter.

### 18.2 A common naming bug

~~~text
@KafkaListener.id = orders
concurrency = 3

event.listenerId:
  orders-0
  orders-1
  orders-2

condition = listenerId == 'orders'
~~~

Result: the condition may never match. Fix with a predicate supporting child IDs or adjust conventions to match actual IDs, rather than assuming the container is not emitting events.

### 18.3 Another bug: overly broad filter

~~~text
@KafkaListener.id:
  orders
  orders-retry
  orders-dlt

condition:
  startsWith('orders')
~~~

Result: the event handler tracks retry/DLT listeners as well. If you only want the main listener, use a distinct name and a narrower predicate.

## 19. Scenario: idle event mistaken for an outage

A listener idle for 60 seconds may simply have no data. Building reliable alerts requires considering:

| Signal | Interpretation |
|---|---|
| `ListenerContainerIdleEvent` | No delivery within configured idle interval |
| Consumer lag = 0 | Consumer caught up with producer; idle may be normal |
| High consumer lag | Unprocessed backlog exists; investigate |
| `ConsumerPausedEvent` | Consumer is intentionally paused |
| `NonResponsiveConsumerEvent` | Poll may be slow/stuck |
| Producer rate | Are records being written to the topic? |
| Partition assignment | Was the consumer assigned partitions? |
| Last processed business event time | Business freshness level |

A proper alert ties to SLAs—for example, "orders has producer traffic and rising lag, yet the listener processed no records for 5 minutes"—rather than merely "idle over 10 seconds."

### 19.1 Base conditions on ID, not on health assumptions

Conditions should only filter **who emitted the event**. Logic evaluating whether an event is normal or abnormal belongs in the monitoring/alerting service, where multiple metrics can be combined.

If a condition grows into a massive SpEL expression embedding stateful health checks, maintenance and testing become much harder.

## 20. Integration with testing and observability

The practical task is verifying that event filters capture only the intended logical listener without missing child containers.

### 20.1 Integration test with concurrency=1

1. Create a Kafka listener with id `orders-main` and a dedicated `groupId`.
2. Configure a short `idleEventInterval` in the test environment.
3. Wait for `ListenerContainerIdleEvent` to be published.
4. Verify the handler dedicated to `orders-main` is invoked.
5. Define another listener `payments-main` and let it go idle.
6. Verify the orders handler does not process payments events.
7. Inspect the actual `listenerId` in the event.

Do not use a unit test calling the handler directly to prove Spring evaluates `@EventListener` conditions properly; such a unit test only tests a Java method.

### 20.2 Integration test with concurrency>1

1. Run `orders-main` with `concurrency=3` and a topic with enough partitions.
2. Wait for child consumer containers to be created.
3. Observe listener IDs on child events.
4. Verify the condition/predicate accepts IDs belonging to `orders-main`.
5. Add listener `orders-main-v2` to test prefix collisions.
6. Verify the predicate does not accidentally accept `v2` if only `main` is required.
7. Verify metric labels distinguish child and parent sensibly.

### 20.3 Testing pause/resume events

1. Retrieve the parent container from `KafkaListenerEndpointRegistry`.
2. Call `container.pause()` from the test thread.
3. Wait for actual pause via `isConsumerPaused` or event.
4. Verify `ConsumerPausedEvent` is received by the matching handler.
5. Call `resume()`.
6. Wait for `ConsumerResumedEvent` and resumed record progress.
7. Verify no other listener's handler was wrongly invoked.

### 20.4 Testing ApplicationEvent conditions

You can build a test context using `ApplicationEventPublisher` and appropriate event instances to test conditions. However, constructors of some Spring Kafka event classes change across versions. Integration tests with real listener containers are more reliable for verifying `listenerId` and child naming.

### 20.5 Thread-safety testing

- Measure event handler latency to ensure it does not block consumer polling.
- If `ApplicationEventMulticaster` is async, verify handlers never access `KafkaConsumer` outside the consumer thread.
- Test shutdown when many events are queued.
- Ensure an overloaded metric/log pipeline does not cause consumers to miss poll intervals.

## 21. Runbook when event filtering misbehaves or events go missing

When operators report "the orders consumer paused yet dashboards show no event":

1. Determine the actual listener ID, not just the Kafka group name.
2. Check child consumer IDs under concurrency.
3. Confirm the pause request was sent to the container with the right ID.
4. Confirm the consumer actually paused, not just `isPauseRequested()`.
5. Check whether `ConsumerPausedEvent` was published in the same `ApplicationContext`.
6. Check `@EventListener` type and SpEL condition.
7. Compare `event.getListenerId()` against the predicate character by character.
8. Check for prefix collisions and null `listenerId`.
9. Check whether the event handler is blocked, failing, or running asynchronously.
10. Check dashboard labels and metrics exporters so metric-export failures are not mistaken for filter bugs.
11. Fix predicates or naming conventions in a controlled way.
12. Re-verify in integration/staging with concurrency matching production.

Never modify Kafka committed offsets or reset a consumer group to solve a pure Application Event filtering problem. Those two layers are independent.

## 22. Common misconceptions

**"@EventListener receives Kafka records."** False. It receives Spring Application Events. Kafka records are processed by `@KafkaListener`.

**"Condition filters data on the broker."** False. It filters Spring event handler invocations, not record fetches.

**"Listener ID is group.id."** Not by default. They are two separate identities, although `idIsGroup` can fall back to ID as group when `groupId` is omitted.

**"One @KafkaListener always emits events with the exact unsuffixed id."** False. Concurrent containers can emit from suffixed child IDs.

**"startsWith is always safe."** False. `orders-main` also matches `orders-main-v2` if the predicate is too broad.

**"@EventListener condition only works on event type."** False. Type is filtered by argument, while condition reads metadata on the event.

**"ListenerContainerIdleEvent proves the broker failed."** False. Low traffic can be completely normal.

**"One ConsumerPausedEvent means the entire concurrent listener paused."** False. The event may belong to one child or partition subset.

**"Event handlers can call KafkaConsumer on any thread."** False. `KafkaConsumer` has thread ownership; async event listeners in particular must avoid this.

**"Slow event handlers do not affect Kafka."** False. With a synchronous multicaster, handlers may run on the consumer thread.

**"Changing @KafkaListener.id affects nothing outside logs."** Not necessarily. Registry lookups and event filters rely on ID; if `idIsGroup` stays true with no explicit `groupId`, the Kafka group can change too.

**"Application Events are a durable audit log."** False. They are not persisted and replayed by the Kafka broker.

## 23. Implementation checklist

**Listener identity**

- [ ] `@KafkaListener.id` is set clearly and stably.
- [ ] `groupId` is set explicitly when needed, avoiding `idIsGroup` side effects.
- [ ] Listener ID, Kafka group ID, and `clientIdPrefix` are distinguished.
- [ ] Naming convention exists for main/retry/DLT/canary listeners.
- [ ] Actual child IDs under `concurrency>1` are known.

**Application events**

- [ ] Correct event type chosen: idle, paused, resumed, started, stopped, or appropriate type.
- [ ] Event-generation settings enabled where needed, e.g., `idleEventInterval`.
- [ ] `@EventListener(condition)` used for simple predicates.
- [ ] Null-safe condition used if needed and prefix collisions avoided.
- [ ] Complex logic written in testable Java predicates/services.

**Threading and operations**

- [ ] Handlers are lightweight and never block the consumer thread.
- [ ] `KafkaConsumer` is never called from async event handlers.
- [ ] Pause/resume performed via `MessageListenerContainer` API.
- [ ] Standalone idle events are not treated as severe errors.
- [ ] Metrics/logs exist per `listenerId`, instance, and partition.
- [ ] Alerts avoid excessive metric cardinality.

**Verification**

- [ ] Tested condition equality and `startsWith`/regex if used.
- [ ] Tested `concurrency>1` and child suffixes.
- [ ] Tested no cross-matching from main/retry/DLT or canary listeners.
- [ ] Tested pause/resume events and actual container state.
- [ ] Tested event listeners running in a real `ApplicationContext`.
- [ ] Tested that handlers do not slow Kafka polling and do not rely on event durability.

## 24. Conclusion

**Listener ID and `@EventListener(condition)`** are a practical pair of tools for selecting the right Spring Kafka Application Events in applications with many listener containers. Listener ID identifies the endpoint/container publishing the event; condition is a SpEL expression evaluated by Spring before invoking the event handler. When a listener has concurrency, events can carry a suffixed child container ID; choose equality, prefix, or regex based on real naming conventions and avoid collisions.

Using this mechanism properly helps monitoring and automation observe individual listeners accurately, without replacing Kafka record filtering, controlling group offsets, or guaranteeing consumer health on its own. Handlers should remain lightweight, thread-safe, distinguish operational states from real incidents, and be verified via integration tests with multiple containers, multiple event types, and production-like concurrency.

