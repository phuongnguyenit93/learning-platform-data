# Event listeners for all containers in Spring Kafka

Spring Kafka does not merely route records from topics to `@KafkaListener` methods. **Listener containers also publish Spring application events** reflecting consumer lifecycle, idle state, pause/resume, poll-loop anomalies, and other operational situations.

When an application has multiple `@KafkaListener` endpoints, multiple topics, multiple consumer groups, or a `ConcurrentMessageListenerContainer` with multiple child consumers, writing a separate observer per listener often causes duplicate code and missed coverage. An **application-level event listener** can receive events from **every listener container publishing into that Spring `ApplicationContext`**, centralizing logging, metrics, alerts, and operational controls.

In the **Spring Kafka Reliability Operations** module, this lesson on **Event listeners for all containers** focuses on building an observer using `@EventListener` or `ApplicationListener` to monitor all containers, distinguishing event sources, avoiding double-counting, protecting consumer threads, and using events for their intended purpose.

**Key distinction right away:** `@KafkaListener` receives **Kafka records** from the broker; `@EventListener` receives **Spring application events** published inside the application. An `ApplicationEvent` is not a Kafka record, has no Kafka offset of its own, and is not durably stored in Kafka.

## 1. Two listener mechanisms that are not the same

An application can run two kinds of listeners side by side:

~~~text
Kafka broker
    |
    +--> orders.events
    |        |
    |        v
    |   @KafkaListener onOrder(...)
    |
    +--> payments.events
    |        |
    |        v
    |   @KafkaListener onPayment(...)
    |
    +--> notifications.events
             |
             v
        @KafkaListener onNotification(...)


Spring Kafka listener containers
    |
    +--> ConsumerStartedEvent
    +--> ListenerContainerIdleEvent
    +--> ConsumerPausedEvent
    +--> NonResponsiveConsumerEvent
    +--> ConsumerStoppedEvent
             |
             v
     Spring ApplicationEventPublisher
             |
             v
      @EventListener observer
             |
             +--> logs / metrics / alerts
~~~

Differences:

| Criterion | @KafkaListener | Spring @EventListener |
|---|---|---|
| Data source | Kafka topics/partitions | Spring `ApplicationContext` event publisher |
| Data type | Kafka `ConsumerRecord` or payload | Java event object |
| Used for | Processing business logic when records arrive | Observing container lifecycle and status |
| Offset/ack | Has Kafka offsets and commit policy | No dedicated Kafka offset or ack |
| Consumer group | Listener container joins a group | Observer does not join a Kafka group |
| Scope | Per topics/listener endpoint | Per event type, within `ApplicationContext` |
| Durability | Kafka stores records per retention | Application events are runtime signals by default |
| Retry | Via listener error handling/recovery | No automatic Kafka retry semantics |

An event listener is not an alternate channel for processing `OrderCreated` or `PaymentAuthorized`. It should only perform operational work related to **the container emitting the event**.

## 2. Why can a single event listener observe all containers?

Spring Kafka listener containers publish events using Spring's `ApplicationEventPublisher` mechanism. Spring delivers events to beans registered for the matching event type within the application context.

Example of an application with three Kafka listener endpoints:

~~~java
@Component
public class BusinessListeners {

    @KafkaListener(
            id = "orderListener",
            topics = "orders.events",
            groupId = "orders-service"
    )
    public void onOrder(OrderEvent event) {
        orderService.handle(event);
    }

    @KafkaListener(
            id = "paymentListener",
            topics = "payments.events",
            groupId = "payments-service"
    )
    public void onPayment(PaymentEvent event) {
        paymentService.handle(event);
    }

    @KafkaListener(
            id = "notificationListener",
            topics = "notifications.events",
            groupId = "notifications-service"
    )
    public void onNotification(NotificationEvent event) {
        notificationService.handle(event);
    }
}
~~~

Another Spring bean registers:

~~~java
@Component
public class AllKafkaContainerEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(AllKafkaContainerEventObserver.class);

    @EventListener
    public void onKafkaEvent(KafkaEvent event) {
        log.debug(
                "Kafka event: type={}, source={}",
                event.getClass().getSimpleName(),
                event.getSource()
        );
    }
}
~~~

**KafkaEvent** is the base class for Spring Kafka application events. When Spring publishes an event in that hierarchy, a method accepting `KafkaEvent` can receive its corresponding subtypes.

This observer does not need to know the three listener IDs in advance. Nor does it need to register with each `@KafkaListener` method. When a qualifying listener container publishes an event into the same `ApplicationContext`, Spring's event mechanism routes it to the observer.

However, the scope of **all containers** here means containers publishing events into **the `ApplicationContext` where the bean is listening**, not all containers across every JVM, every Kubernetes pod, or every microservice in the system.

## 3. Two ways to register a global observer

### 3.1. Using @EventListener

This is usually the easiest approach to read:

~~~java
@Component
public class KafkaLifecycleObserver {

    @EventListener
    public void onAnyKafkaEvent(KafkaEvent event) {
        recordInternalEvent(
                event.getClass().getSimpleName(),
                event.getSource()
        );
    }

    private void recordInternalEvent(String type, Object source) {
        // Write lightweight logs or update metrics.
    }
}
~~~

If you only want a few event types, declare multiple methods with specific types:

~~~java
@Component
public class KafkaOperationsEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaOperationsEvents.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.warn(
                "Kafka listener idle: listenerId={}, idleTimeMs={}",
                event.getListenerId(),
                event.getIdleTime()
        );
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.error(
                "Kafka consumer may be blocked: source={}",
                event.getSource()
        );
    }

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka consumer paused: source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka consumer resumed: source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }
}
~~~

The methods above are invoked for matching events published by any corresponding container in the application context. The code illustrates familiar Spring Kafka APIs; available event classes and accessors depend on dependency version.

### 3.2. Using ApplicationListener

If you want a class implementing a formal interface contract:

~~~java
@Component
public class AllKafkaEventsListener
        implements ApplicationListener<KafkaEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(AllKafkaEventsListener.class);

    @Override
    public void onApplicationEvent(KafkaEvent event) {
        log.debug(
                "Kafka application event: type={}, source={}",
                event.getClass().getSimpleName(),
                event.getSource()
        );
    }
}
~~~

Both approaches rely on Spring event publication, not consuming records directly from Kafka. Choose one approach for a shared observer. Do not register two handlers emitting the same metric without realizing both **receive the same event**; that can double-count numbers.

### When to choose which approach?

| Approach | Advantage | Caveat |
|---|---|---|
| `@EventListener(KafkaEvent)` | Single general event collection point | Must classify subtypes to avoid overly noisy logs |
| `@EventListener(ConcreteEvent)` | Specialized handler, clear event type | More methods |
| `ApplicationListener<KafkaEvent>` | Explicit Java interface contract | Needs a dispatch method |
| `ApplicationListener<ConcreteEvent>` | Fits one specific responsibility | Does not cover all event types |
| Custom `ApplicationEventMulticaster` | Customizes app-wide event dispatch | Can alter thread and failure semantics |

In real operational systems, it is usually best to use **typed listeners** for events requiring dedicated actions, and a general observer strictly for bounded logging/metrics.

## 4. Common container event groups

Not every Spring Kafka version has the exact same set of event classes. Some events were added in newer releases. The table below describes common groups in modern Spring Kafka:

| Event class / group | When published | How to use |
|---|---|---|
| `ConsumerStartingEvent` | Consumer thread/container is about to start | Track startup duration |
| `ConsumerStartedEvent` | Consumer has started its lifecycle | Count active consumers |
| `ConsumerStoppingEvent` | Consumer is stopping | Record shutdown |
| `ConsumerStoppedEvent` | Consumer has stopped | Observe stop reason if supported by event |
| `ContainerStoppedEvent` | Container stopped | Distinguish normal vs. abnormal shutdown |
| `ListenerContainerIdleEvent` | Container received no records within configured interval | Track low-traffic streams or suspect upstream |
| `ListenerContainerNoLongerIdleEvent` | Records reappear after idle | End idle state |
| `ListenerContainerPartitionIdleEvent` | A monitored partition became idle | Per-partition observation |
| `ListenerContainerPartitionNoLongerIdleEvent` | Partition receives records again | Clear per-partition idle state |
| `ConsumerPausedEvent` | Consumer/container paused | Track backpressure |
| `ConsumerResumedEvent` | Consumer/container resumed | Measure pause duration |
| `ConsumerPartitionPausedEvent` | A partition paused | Investigate partition-level throttling |
| `ConsumerPartitionResumedEvent` | A partition resumed | Mark partition active again |
| `NonResponsiveConsumerEvent` | Consumer poll not progressing per monitor threshold | Alert on risk of blocked thread |
| `ConsumerFailedToStartEvent` | Consumer failed to start within configured timeout | Alert on startup failure |
| `ListenerContainerAuthEvent` | Authentication/authorization issue surfaced by container | Alert on security/configuration |

Exact event names and types can vary by Spring Kafka version. Check your actual library before adding imports or relying on an event introduced in newer releases.

In particular, **not every exception in a listener automatically produces a corresponding application event**. Per-record processing errors still require `CommonErrorHandler`, `DefaultErrorHandler`, recovery/DLT, and dedicated logging/metrics.

## 5. Example configuring idle events for all listeners sharing a factory

Spring Kafka only publishes certain events after enabling or setting the corresponding threshold. For instance, `ListenerContainerIdleEvent` requires `idleEventInterval`.

You can set it on a `ConcurrentKafkaListenerContainerFactory` shared by multiple listeners:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, Object>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, Object> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, Object>();

        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties().setIdleEventInterval(60_000L);

        return factory;
    }
}
~~~

This example requires the observed endpoints to actually use this listener factory. A shared factory applies the idle interval to every container created from it.

When multiple factories exist, settings on **one factory** do not automatically apply to listeners using another factory. An `@EventListener` observer can still receive events from all factories, yet each container only publishes events it was configured to emit.

A listener explicitly specifying the factory:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "kafkaListenerContainerFactory"
)
public void onOrder(OrderEvent event) {
    orderService.handle(event);
}
~~~

Do not confuse **global event reception scope** with **scope of applying idle threshold config**. Those are two separate decisions.

## 6. Idle events do not mean the consumer failed

`ListenerContainerIdleEvent` is typically published when the consumer receives no records within a preset duration. That can be completely normal:

- Low-publish topic.
- Business logic only generates events at specific hours.
- Producer temporarily has no data.
- Assigned partition has no traffic.
- Consumer is paused or waiting for data in a valid state.

Example:

~~~text
orders.events:
  09:00 event A
  09:01 event B
  09:02 ...
  09:03 no events
  09:04 no events
           |
           v
ListenerContainerIdleEvent
~~~

If a topic naturally gets only a few events per day, going idle after 60 seconds is not an incident. Conversely, on a continuous-traffic payment stream, having no records for several minutes may warrant investigating upstream producers or broker connectivity.

Set thresholds and alerting policies **according to each stream's characteristics**, even when a single observer receives events from all containers.

### Dedicated idle observer example

~~~java
@Component
public class KafkaIdleEventHandler {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleEventHandler.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener idle: listener={}, idleMs={}, partitions={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions()
        );
    }

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerNoLongerIdleEvent event) {

        log.info(
                "Kafka listener no longer idle: listener={}",
                event.getListenerId()
        );
    }
}
~~~

Do not use idle events to automatically reset offsets or skip records. They are status signals, not directives that data is corrupt.

## 7. NonResponsiveConsumerEvent differs from ListenerContainerIdleEvent

This is an especially important pair of events in reliability.

**Idle:** Consumer can still poll normally yet receives no new records.

**Non-responsive:** A monitor detects the consumer has not executed a poll cycle within a suspicious duration relative to poll timeout and configured thresholds.

~~~text
Case A: IDLE

poll() --> no records
poll() --> no records
poll() --> no records
           |
           v
ListenerContainerIdleEvent
           |
           +--> Consumer is still polling


Case B: NON-RESPONSIVE

poll() --> listener processing
                 |
                 +--> hung SQL query
                 +--> long Thread.sleep
                 +--> Deadlock
                 |
          fails to return to poll on time
                 |
                 v
        NonResponsiveConsumerEvent
~~~

`NonResponsiveConsumerEvent` is **a sign needing investigation**, not conclusive proof that the consumer lost group membership. It can appear due to a long-running listener, a blocked consumer thread, system pauses, or other scheduling factors.

### Configuring the monitor

Spring Kafka provides monitor interval and no-poll threshold options. Illustrative factory configuration:

~~~java
factory.getContainerProperties().setMonitorInterval(30);
factory.getContainerProperties().setNoPollThreshold(3.0f);
~~~

The threshold is evaluated relative to the container's poll timeout. Verify exact API names and parameter types against your running version.

An observer:

~~~java
@Component
public class KafkaPollHealthObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPollHealthObserver.class);

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.error(
                "Kafka consumer may be non-responsive; source={}",
                event.getSource()
        );
    }
}
~~~

Upon receiving the event, capture thread dumps, measure listener latency, check JDBC connection/query timeouts, inspect CPU/GC pauses, and assess consumer lag. Do not automatically kill/restart every container solely on a single event without safeguards against restart loops.

## 8. Lifecycle events monitor container startup and stop

With many listeners, looking solely at the Spring Boot application being `RUNNING` is insufficient. A Kafka listener container may fail on start, stop, or remain unassigned.

Lifecycle-related events help identify:

~~~text
Application start
       |
       v
ConsumerStartingEvent
       |
       v
ConsumerStartedEvent
       |
       v
RUNNING
       |
       +--> Stop requested
       |       |
       |       v
       | ConsumerStoppingEvent
       |       |
       |       v
       | ConsumerStoppedEvent
       |
       v
ContainerStoppedEvent
~~~

Some events may be emitted per child consumer when a container has high concurrency. Do not conclude "the entire listener stopped" just because one `ConsumerStoppedEvent` arrived from one child.

Logging example:

~~~java
@Component
public class KafkaConsumerLifecycleLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerLifecycleLogger.class);

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        log.info("Kafka consumer started: source={}", event.getSource());
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        log.warn(
                "Kafka consumer stopped: source={}, reason={}",
                event.getSource(),
                event.getReason()
        );
    }

    @EventListener
    public void onContainerStopped(ContainerStoppedEvent event) {
        log.info("Kafka container stopped: source={}", event.getSource());
    }
}
~~~

`ConsumerStoppedEvent` in supported versions can supply a `reason` to distinguish stop causes. Do not hard-code every enum value into dashboards without checking your version. A consumer stopped during an intentional shutdown should not trigger the same alert severity as an abnormally stopped consumer.

## 9. Pause/resume events for backpressure

Pause/resume events are useful when the system intentionally throttles load:

~~~text
Database saturation
       |
       v
Container.pause()
       |
       v
ConsumerPausedEvent
       |
       v
Kafka keeps polling in paused state
       |
       v
Database recovered
       |
       v
Container.resume()
       |
       v
ConsumerResumedEvent
~~~

A global observer can:

- Record the pause reason from the application's control system.
- Measure how long the consumer stayed paused.
- Report the number of paused partitions.
- Detect containers paused longer than SLOs.
- Correlate consumer lag with pause duration.
- Distinguish backpressure pauses from retry/backoff pauses.

Example:

~~~java
@Component
public class KafkaPauseResumeObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPauseResumeObserver.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka paused; source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka resumed; source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }
}
~~~

**One `ConsumerPausedEvent` does not mean all child containers in the application are paused.** Identify the source, partition assignments, and relevant container.

Never call `Consumer.pause()` or `Consumer.resume()` directly from an observer running on another thread. When controlling containers, use Spring Kafka `MessageListenerContainer.pause()/resume()` via reference or `KafkaListenerEndpointRegistry`, and clearly track different pause reasons to avoid accidental resumes.

## 10. All containers in one application is not all consumers in the cluster

A Spring Boot service can run multiple replicas:

~~~text
Kubernetes Deployment: orders-service

Pod A                         Pod B
  Spring ApplicationContext     Spring ApplicationContext
  @KafkaListener order          @KafkaListener order
  @KafkaListener payment        @KafkaListener payment
  Event observer A              Event observer B

         |                              |
         +--------------+---------------+
                        |
                    Kafka cluster
~~~

Observer A only receives application events published inside the context A listens to. It does not directly receive internal listener container events from Pod B.

Therefore:

- **Within one pod/context:** `@EventListener` can observe multiple containers.
- **Across multiple pods:** aggregate logs/metrics/traces into observability systems such as Prometheus, OpenTelemetry, or a log aggregator.
- **Across multiple services:** use centralized monitoring or a business event bus if cross-service signals are truly required.
- **Across multiple `ApplicationContext`s in one JVM:** understand Spring's event propagation rules; do not assume all contexts hear one another.

Spring application events generally propagate from child contexts upward to parent contexts, but do not automatically broadcast laterally across sibling contexts. If using parent/child contexts, place observers in the right context and verify actual event propagation.

## 11. Concurrent containers can emit multiple events for the same listener ID

With:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        concurrency = "3"
)
public void onOrder(OrderEvent event) {
    orderService.handle(event);
}
~~~

Spring Kafka can create a `ConcurrentMessageListenerContainer` containing three child containers corresponding to separate Kafka consumers.

~~~text
ordersListener (parent)
     |
     +--> child consumer 0 --> partitions P0, P1
     |
     +--> child consumer 1 --> partitions P2, P3
     |
     +--> child consumer 2 --> partitions P4, P5
~~~

A lifecycle or pause event may represent the state of **one child consumer**, not the entire parent. When counting running consumers, identify by source/child ID or stable client ID rather than group ID alone.

If you only store:

~~~text
ordersListener = RUNNING
~~~

then when one of the three consumers stops abnormally, granularity is lost. Prefer a model like:

~~~text
ordersListener / consumer 0 = RUNNING
ordersListener / consumer 1 = STOPPED
ordersListener / consumer 2 = RUNNING
~~~

How child identity is obtained depends on Spring Kafka version, listener ID, and the event's container source. When building metrics, use bounded-value labels such as application, listener, and client/child index; never use partition offsets or `eventId` as tags.

## 12. Identifying the event source to know which container emitted the event

A global observer should identify at minimum:

1. Event type.
2. Listener container source.
3. Listener ID when supported by the event.
4. Relevant topic/partitions when supported by the event.
5. Consumer client/group identity if needed for investigation.
6. Application instance/pod ID in the deployment environment.

Example idle event providing listener ID:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {

    String listenerId = event.getListenerId();

    log.info(
            "Idle: listener={}, durationMs={}, partitions={}",
            listenerId,
            event.getIdleTime(),
            event.getTopicPartitions()
    );
}
~~~

For events lacking `getListenerId`, record `event.getSource()` and map sources via container lifecycle metadata. Avoid assuming every event type shares the exact same set of accessors when the actual API does not support them.

Do not parse listener IDs assuming every ID has a fixed suffix. With concurrent containers, Spring Kafka may append suffixes to child containers; record actual identifiers per your version and container config.

### Filtering events by specific listener

A global observer can receive all idle events yet alert only for critical business topics:

~~~java
@EventListener
public void onCriticalListenerIdle(
        ListenerContainerIdleEvent event) {

    String listenerId = event.getListenerId();

    if (!listenerId.startsWith("paymentsListener")) {
        return;
    }

    log.warn(
            "Critical listener idle: id={}, idleMs={}",
            listenerId,
            event.getIdleTime()
    );
}
~~~

The example uses a prefix because listener IDs may carry child consumer suffixes. In production, use an explicit policy mapping by listener IDs or application-managed metadata rather than relying on fragile name parsing without control.

Filtering by event type and source is how you reuse one observer while keeping different operational thresholds for orders, payments, and notifications.

## 13. Monitoring multiple container factories

A real application often has multiple factories:

~~~text
orderListenerFactory
    +--> ordersListener

paymentListenerFactory
    +--> paymentsListener

batchListenerFactory
    +--> settlementBatchListener
~~~

If each factory has a different idle interval, the global observer receives events from all containers, yet event frequencies differ.

Example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
orderListenerFactory(
        ConsumerFactory<String, OrderEvent> cf) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(cf);
    factory.getContainerProperties().setIdleEventInterval(60_000L);

    return factory;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
paymentListenerFactory(
        ConsumerFactory<String, PaymentEvent> cf) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, PaymentEvent>();

    factory.setConsumerFactory(cf);
    factory.getContainerProperties().setIdleEventInterval(15_000L);

    return factory;
}
~~~

The same `@EventListener(ListenerContainerIdleEvent)` receives events from both factory groups if they publish into the same context. Alert policies can treat 15 seconds of payments idle as notable while treating 60 seconds of orders idle as informational.

Remember that factory configuration sets **the conditions for emitting events**, whereas the observer decides **how to react when events appear**.

## 14. Thread model of Spring ApplicationEvents

Standard Spring event publication uses `ApplicationEventMulticaster`. Under the common default setup, event listeners are invoked **synchronously** on the event-publishing thread unless configured otherwise or an event type has special semantics.

With Spring Kafka, many events are published from the Kafka consumer/container thread. Consequently, code inside `@EventListener` may execute **on the very thread that must continue polling and processing records**.

~~~text
Kafka consumer thread
        |
        +--> poll()
        |
        +--> Spring Kafka publishes ConsumerPausedEvent
        |         |
        |         v
        |   @EventListener runs synchronously
        |         |
        |         +--> lightweight logging
        |         +--> counter increment
        |
        +--> return to consumer loop
~~~

If the observer makes an HTTP call to an alerting system and waits 30 seconds, the consumer thread can block, delaying polls and raising the risk of exceeding `max.poll.interval.ms`.

**Rule:** Event handlers must be fast, bounded, and free of long I/O. Tasks like sending Slack/email alerts, calling incident APIs, or querying databases should be handed off to an asynchronous mechanism with controlled queues and timeouts.

Never pass the entire `KafkaEvent` object or `Consumer` instance to a worker thread and manipulate the consumer there. `KafkaConsumer` must not be used arbitrarily from another thread, and events can hold references to objects safe only within the current lifecycle.

## 15. Caution when configuring an asynchronous ApplicationEventMulticaster

An application can configure `SimpleApplicationEventMulticaster` with a `TaskExecutor` to dispatch events asynchronously. Doing so changes the observer's thread context and can affect other application events too, not just Spring Kafka.

~~~text
Kafka consumer thread
        |
        +--> publish(event)
                 |
                 v
          Async event executor
                 |
                 +--> observer thread
~~~

Benefits:

- Observer I/O does not necessarily block the consumer thread.
- Easy to decouple logging/alerting latency from the poll loop.

Risks:

- Must never invoke `KafkaConsumer` methods from another observer thread.
- Event processing order can vary across tasks.
- An event may be processed after the container already stopped or rebalanced.
- A full queue can drop telemetry or cause unwanted backpressure.
- Changing the global multicaster can affect transaction-related Spring events.
- Some Spring events are unsuitable or disallowed from running asynchronously per framework contracts.

Therefore, if you only need to send alerts asynchronously, it is usually safer for a **typed `@EventListener` to capture a small snapshot** and push it to a dedicated bounded queue. Do not alter the global application event multicaster without understanding its impact on other Spring components.

## 16. Example offloading alerts to a safe asynchronous mechanism

Suppose a `NonResponsiveConsumerEvent` must alert an external system. Do not invoke the alerting API directly inside the event handler:

~~~java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    incidentClient.createIncident(event); // Avoid doing this directly.
}
~~~

A better approach is creating a **plain data snapshot**:

~~~java
public record KafkaContainerAlert(
        String type,
        String source,
        Instant observedAt
) {}
~~~

Handler:

~~~java
@Component
public class KafkaContainerAlertPublisher {

    private final KafkaAlertQueue queue;

    public KafkaContainerAlertPublisher(KafkaAlertQueue queue) {
        this.queue = queue;
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {

        KafkaContainerAlert alert = new KafkaContainerAlert(
                "NON_RESPONSIVE_CONSUMER",
                String.valueOf(event.getSource()),
                Instant.now()
        );

        queue.offer(alert);
    }
}
~~~

`KafkaAlertQueue` represents an application-implemented bounded queue or publisher with timeouts, queue-full policies, and metrics for dropped alerts. It does not carry `Consumer` objects across threads.

On another worker, the system can read `KafkaContainerAlert` and call the incident API with appropriate retry/backoff. Because telemetry events are unlike business records, decide whether losing an alert during a process crash is acceptable. If not, use a durable alert outbox or dedicated event storage.

## 17. Not every application event requires a corrective action

A global observer can easily become an over-reaching controller—for example, seeing idle and immediately seeking or restarting, seeing non-responsive and stopping the container, or seeing pause and immediately resuming.

Such reactions can create failure loops:

~~~text
Container idle
     |
     +--> Observer restarts container
               |
               v
          Consumer rebalance
               |
               v
          Container idle again
               |
               v
          Restart again
~~~

Classify reactions properly:

| Event | Preferred reaction | Do not automate blindly |
|---|---|---|
| `ConsumerStartedEvent` | Record status, update readiness appropriately | Count as business success |
| `ListenerContainerIdleEvent` | Observe traffic, alert per expected rate | Reset offsets or restart immediately |
| `ListenerContainerNoLongerIdleEvent` | Clear idle alert | Infer records were processed successfully |
| `NonResponsiveConsumerEvent` | Capture thread dumps, latency, alert | Kill container on every single event |
| `ConsumerPausedEvent` | Record pause state/duration/reason | Resume if another controller holds pause |
| `ConsumerStoppedEvent` | Separate normal vs. abnormal stops | Restart infinitely without cooldown |
| `ListenerContainerAuthEvent` | Alert on security/configuration details | Log credentials/tokens |
| `ContainerStoppedEvent` | Observe shutdown completion | Conclude entire deployment stopped |

An event reflects **status at observation time**, not the full truth about record processing. To govern retry/DLT, you still need the data path and corresponding error-handling mechanisms.

## 18. Observing container-wide idle vs. per-partition idle

A container may be assigned multiple partitions. If only one partition has no records while other partitions receive steady data, the container overall is not idle.

~~~text
Consumer A:
  P0: 100 records / second
  P1: 0 records / minute
  P2: 50 records / second
~~~

If you need to know when P1 stops receiving data, **partition idle events** (when supported by your version and configured) are more useful than listener-level idle.

Selection criteria:

- **ListenerContainerIdleEvent:** track a container/consumer having no data overall.
- **ListenerContainerPartitionIdleEvent:** track a specific partition having no data.
- **Consumer lag:** measure Kafka backlog per partition.
- **Producer metrics:** identify whether upstream stopped publishing.
- **Topic retention/offsets:** confirm whether data exists.

An empty partition can be normal if key distribution is skewed or a tenant has low traffic. Conversely, high lag alongside an idle listener can point to a paused partition, misassigned partitions, consumer errors, or other issues. Never infer from a single event alone.

## 19. Using KafkaListenerEndpointRegistry to correlate events with containers

`KafkaListenerEndpointRegistry` helps locate listener containers registered via `@KafkaListener`, look them up by ID, and perform controlled lifecycle actions.

~~~java
@Component
public class KafkaContainerRegistryView {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaContainerRegistryView(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void listKnownContainers() {
        for (MessageListenerContainer container
                : registry.getListenerContainers()) {

            log.info(
                    "Kafka container: id={}, running={}",
                    container.getListenerId(),
                    container.isRunning()
            );
        }
    }
}
~~~

Fetching a specific container:

~~~java
MessageListenerContainer orders =
        registry.getListenerContainer("ordersListener");

if (orders != null && orders.isRunning()) {
    orders.pause();
}
~~~

The registry is a container management tool; **it is not required for Spring `@EventListener` to receive events from containers**.

Note: the registry usually focuses on containers created from `@KafkaListener` endpoints. Containers created manually as Spring beans may be managed differently. To observe events from every real container, ensure they use the right `ApplicationEventPublisher`/context.

Do not treat the registry as an event history table. It reflects currently managed containers, not a full log of past events.

## 20. Event observers across multiple contexts and test environments

A simple application typically has a single `ApplicationContext`. However, complex systems may use parent/child contexts, embedded modules, or multiple Spring Boot applications in one JVM.

~~~text
Parent ApplicationContext
       |
       +--> Child Context A
       |       |
       |       +--> Kafka Container A
       |
       +--> Child Context B
               |
               +--> Kafka Container B
~~~

Spring application event propagation depends on context relationships. Events from a child can propagate up to the parent; events do not automatically travel from one child to a sibling child. An observer placed in Child A does not automatically receive events from Child B.

In integration tests, contexts can be created and closed repeatedly, starting/stopping listener containers and emitting lifecycle events. If an observer writes metrics into a singleton outside the context without proper resets, stale numbers can leak across tests.

When multiple contexts exist, verify:

1. Which context does the container publish events into?
2. Which context does the observer bean live in?
3. Is parent/child event propagation behaving as expected?
4. Is there a risk of the same observer existing in both parent and child and double-counting?
5. Should application instance/context IDs be added to logs?

Do not assume "all" means system-wide if the reality is only a single Spring `ApplicationContext`.

## 21. Use ApplicationEvents as monitoring signals, not an event store

Spring `ApplicationEvents` are not durably persisted like Kafka records. If the JVM crashes right after emitting an event, the observer may not finish handling it or export telemetry externally.

Therefore:

- `ApplicationEvents` fit runtime monitoring, state notifications, and hooks.
- Kafka broker metrics fit tracking partition lag, consumer membership, and throughput.
- Micrometer/OpenTelemetry fit metrics/tracing.
- Log aggregators or incident platforms fit historical alerting.
- If an operational event must be guaranteed saved, use a dedicated durable outbox/topic/storage.

Do not treat an observer logging `ConsumerStartedEvent` as proof that business data cannot be lost. Consumer lifecycle and record-level reliability are two separate concerns.

## 22. Which events are NOT for handling record exceptions?

An error inside `@KafkaListener`:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) {

    if (event.amount().signum() < 0) {
        throw new InvalidOrderException("Negative amount");
    }

    orderService.process(event);
}
~~~

`InvalidOrderException` requires mechanisms like `DefaultErrorHandler`, retry/recoverer, and DLT. You cannot expect a `ConsumerStoppedEvent` or `ListenerContainerIdleEvent` for every failing record.

Proper flow:

~~~text
Record listener
     |
     +--> Exception
     |
     v
DefaultErrorHandler / AfterRollbackProcessor
     |
     +--> Retry
     |
     +--> DLT / recovery
     |
     v
Offset policy

ApplicationEvents
     |
     +--> Container idle
     +--> Pause/resume
     +--> Lifecycle
     +--> Poll health
     |
     v
Logs / metrics / alerts
~~~

Separating the two paths prevents a global observer from accidentally skipping records or seeking the consumer at the wrong time.

With transactional containers, record processing errors should roll back the transaction per config, after which `AfterRollbackProcessor` decides redelivery/recovery. Application event listeners do not replace the transaction/error lifecycle.

## 23. Handling errors inside event observers

If an `@EventListener` handler throws an exception under synchronous event dispatch, the exception can propagate to the event-publishing thread or `ApplicationEventMulticaster` error handling, depending on configuration.

A handler intended solely for logging/metrics should not cause the consumer thread to fail because the telemetry server is unavailable.

Design example:

~~~java
@Component
public class SafeKafkaEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(SafeKafkaEventObserver.class);

    private final KafkaContainerMetrics metrics;

    public SafeKafkaEventObserver(KafkaContainerMetrics metrics) {
        this.metrics = metrics;
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        try {
            metrics.recordConsumerStopped(
                    String.valueOf(event.getSource()),
                    event.getReason().name()
            );
        }
        catch (RuntimeException ex) {
            log.warn(
                    "Could not publish consumer stopped metric",
                    ex
            );
        }
    }
}
~~~

`KafkaContainerMetrics` represents an internal abstraction; do not let it make long synchronous HTTP calls on the consumer thread. Pushing telemetry to a bounded queue or local in-memory metrics registry is usually better.

Observer errors must be judged by severity: do not swallow errors impacting a business transaction if an event is a mandatory business hook; conversely, most operational telemetry should never stop the Kafka consumer from polling.

## 24. Monitoring and alerting without exploding metrics cardinality

An observer receiving events from all listeners can export metrics:

| Metric | Useful tags |
|---|---|
| `kafka_container_started_total` | application, listener, reason/source category |
| `kafka_container_stopped_total` | application, listener, stop reason |
| `kafka_container_idle_total` | application, listener |
| `kafka_container_nonresponsive_total` | application, listener |
| `kafka_container_pause_total` | application, listener, reason |
| `kafka_container_paused_seconds` | application, listener |
| `kafka_container_resume_total` | application, listener |
| `kafka_partition_idle_total` | application, topic, partition or partition band |
| `kafka_container_alert_dropped_total` | application, alert type |

The metric names above are custom examples, not a guarantee that Spring Kafka emits those exact names out of the box.

Avoid tags with unbounded values:

- Record keys.
- Event IDs.
- Kafka offsets.
- Raw exception messages containing request IDs.
- Unbounded dynamic client IDs.
- Topic names driven by arbitrary user input.

Tag selection must fit the scale of topics, partitions, and replica counts. With thousands of partitions, exporting a time series per partition can be very expensive; consider aggregating by topic/group or using dedicated dashboards.

### Suggested alert severities

- **Info:** consumer start/stop during planned rolling deployments.
- **Warning:** critical listener idle longer than SLO; pause lasting beyond threshold.
- **Critical:** prolonged non-responsive consumer alongside rising lag; authentication failures; unexpected container stop.
- **Recovery:** no-longer-idle, consumer resumed, successful restart after incident.

Do not page directly for every idle event if the topic normally has low traffic.

## 25. Classifying by state and event to build runbooks

A simple runbook:

~~~text
Event: NonResponsiveConsumerEvent
    |
    +--> Check thread dump / long-running listener
    |
    +--> Check max.poll.interval.ms and poll timeout
    |
    +--> Check DB query/connection timeout
    |
    +--> Check consumer lag and rebalance
    |
    +--> Decide action based on actual state


Event: ConsumerPausedEvent
    |
    +--> Check pause reason
    |
    +--> Identify container/partition
    |
    +--> Inspect DB/backpressure/retry state
    |
    +--> Monitor paused duration and lag
    |
    +--> Resume once all pause reasons clear


Event: ConsumerStoppedEvent
    |
    +--> Inspect reason and shutdown context
    |
    +--> Separate rolling deploy from unexpected stop
    |
    +--> Check group assignment and lag
    |
    +--> Alert/restart per bounded policy
~~~

This turns events into diagnostic signals rather than turning handlers into uncontrolled restart loops.

## 26. Example of a clearly categorized shared observer

A lightweight approach using one bean and typed handlers:

~~~java
@Component
public class GlobalKafkaContainerObserver {

    private static final Logger log =
            LoggerFactory.getLogger(GlobalKafkaContainerObserver.class);

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        log.info(
                "Kafka consumer started; source={}",
                event.getSource()
        );
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        log.warn(
                "Kafka consumer stopped; reason={}, source={}",
                event.getReason(),
                event.getSource()
        );
    }

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.debug(
                "Kafka listener idle; id={}, idleMs={}",
                event.getListenerId(),
                event.getIdleTime()
        );
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.error(
                "Kafka consumer non-responsive; source={}",
                event.getSource()
        );
    }

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka paused; source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka resumed; source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }
}
~~~

The example targets modern Spring Kafka and Java appropriate for the application. Add imports for Spring `@Component`, `@EventListener`, classes in `org.springframework.kafka.event`, and `Logger`/`LoggerFactory`. In production, shift from raw logging to metrics with bounded labels and alert only on threshold breaches.

Note: this bean does not need to be registered individually per `@KafkaListener`. Spring dispatches events to it based on event type and application context.

## 27. Avoiding double-counting when mixing general and specialized handlers

Suppose a class contains:

~~~java
@EventListener
public void all(KafkaEvent event) {
    metrics.increment("kafka_events_total");
}

@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    metrics.increment("kafka_events_total");
}
~~~

For a `ListenerContainerIdleEvent`, **both methods can be invoked**, causing `kafka_events_total` to increment twice without an explicit counting policy.

Design alternatives:

- Have the general handler increment only a single total metric by event type.
- Have specialized handlers record only specialized metrics such as `idle_duration`.
- Never increment the same counter from multiple handlers.
- Use a single dispatcher if every event must be counted exactly once.
- If event sources have a parent/child hierarchy, separate individual child events from application-aggregated parent events.

Double-counting in observability is also a reliability bug: dashboards may report a container stopped twice and trigger incorrect restart/alert policies.

## 28. Testing an observer receiving events from all containers

An integration test should create multiple listener endpoints in the same Spring `ApplicationContext`, enable idle events or publish an appropriate event, and verify the observer receives the expected event type and source.

Example scenarios:

| Scenario | What to verify |
|---|---|
| Two `@KafkaListener` endpoints in same context | Global observer receives events from both |
| One listener with `concurrency=3` | Observer sees child consumers when lifecycle events emit |
| Listener A idle, listener B has traffic | Entire application is not concluded idle |
| Consumer A pauses | Observer identifies right source/partitions |
| Consumer B resumes | Does not clear A's pause state |
| `NonResponsiveConsumerEvent` | Alert is created without blocking consumer thread |
| Log/metric handler throws exception | Data path is unaffected beyond policy |
| Normal application shutdown | `ConsumerStoppedEvent` creates no false critical alert |
| Multiple factories, only one enables idle interval | Only containers with interval enabled emit idle events |
| Child/parent `ApplicationContext` | Event propagation is not misunderstood |
| Async event delivery | `KafkaConsumer` is not used from another thread |
| General observer and typed handlers | Same metric is not double-counted |

With Spring Kafka, use EmbeddedKafka or Testcontainers Kafka to produce realistic start/idle/pause scenarios. Unit tests calling `onIdle(...)` directly do not verify Spring event listener registration and container event publication.

Check listener registry state, event sources, and metrics too, and avoid failing tests due to asynchronous event dispatch latency that the test did not wait for appropriately.

## 29. Common configuration mistakes

### @EventListener does not receive idle events

Check whether `setIdleEventInterval` was placed on **the right listener container factory**. An event that is never published cannot be received by the observer, even if the method signature is right.

### Observer only receives events from one listener

Check which `ApplicationContext` the observer belongs to, which context's factories the listeners use, and whether listener ID filters are dropping events. Do not confuse `@KafkaListener` topic filtering with Spring event subscription.

### A single event is logged multiple times

There may be multiple observer beans, both generic and typed event handlers, or parent/child contexts both registered. Check registered bean count and event sources.

### Event handler slows down the consumer

The handler is running synchronous I/O or holding locks too long on the consumer thread. Move heavy work to bounded async processing and pass only metadata snapshots.

### Idle alerts fire constantly even though Kafka is healthy

Topics with low traffic, overly short idle intervals, or empty partitions are normal. Tune alerts to expected traffic and SLOs.

### ConsumerPausedEvent appears yet the whole application is not paused

The event may belong to one child container or partition. Identify the source/partitions before drawing conclusions.

### Application is running yet ConsumerStoppedEvent appears

One child consumer can stop while the parent or other children remain running. Check the reason, concurrency, and status of individual consumers.

### NonResponsiveConsumerEvent appears after a slow query

The listener may be blocked and not returning to poll. Check JDBC timeouts, `max.poll.interval.ms`, processing latency, and thread dumps. Do not just raise timeouts to hide the root cause.

### Observer tries to call Consumer API from an async thread

`KafkaConsumer` must not be used arbitrarily from another thread. Use `MessageListenerContainer` APIs or route requests to the appropriate control flow.

### Events do not appear in cluster-wide dashboards

Spring `ApplicationEvents` are local to the application context and do not broadcast to other pods. Export metrics/logs from each pod and aggregate into the observability platform.

## 30. Checklist for designing a global event listener

- Distinguish `@KafkaListener` receiving records from `@EventListener` receiving Spring application events.
- Observer is a Spring bean in the appropriate context.
- Use `@EventListener(KafkaEvent)` or `ApplicationListener<KafkaEvent>` when broad observation is needed.
- Use typed listeners for idle, non-responsive, lifecycle, and pause/resume when specific policies are required.
- Configure `idleEventInterval` and monitor settings on the right listener factory.
- Understand that one factory can create multiple listener containers.
- Understand that a concurrent container has multiple child consumers.
- Identify event source and listener ID; never collapse all child states into one boolean.
- Distinguish container idle from non-responsive consumer.
- Never treat an application event as a Kafka record with offsets/acks.
- Never replace `DefaultErrorHandler`/DLT with an observer.
- Keep event handlers lightweight and never block the consumer poll thread.
- Never pass `Consumer` references to async workers.
- Enforce bounded queues and timeouts if sending alerts asynchronously.
- Never trigger restart/pause/resume loops from a single event.
- Distinguish normal shutdown from unexpected stops.
- Avoid double-counting between generic and typed handlers.
- Use metrics with bounded-cardinality labels.
- Treat `ApplicationEvents` as local signals, not a cluster-wide event stream.
- Maintain centralized observability across pods/instances.
- Test multi-listener, concurrency, idle, pause, shutdown, and error scenarios.

**Conclusion:** A Spring `@EventListener` or `ApplicationListener` accepting `KafkaEvent` types can serve as **a shared observer for all listener containers in the same Spring `ApplicationContext`** without modifying each `@KafkaListener`. Practical value comes from properly classifying idle, non-responsive, lifecycle, and pause/resume events; associating events with container/partition sources; avoiding blocking consumer threads; and turning those signals into controlled logging, metrics, and alerts. A global event listener is the container's observability layer—**it does not replace Kafka record processing, offset commits, retries, or DLTs**.

