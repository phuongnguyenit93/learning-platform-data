# Mapped ObjectNames, NotificationFilter, and Handback in Spring JMX

## 1. Context: A Listener Does Not Need to Receive Every MBean

Java Management Extensions (JMX) supports a management event-emission mechanism called **Notification**. An MBean can emit a notification when state changes, a threshold is crossed, configuration is modified, or an important task finishes. Spring Framework provides listener-registration helper classes so application code does not need to repeat every `MBeanServer.addNotificationListener(...)` call manually.

When an application has many MBeans, three questions arise:

1. **Listen from where?** Which MBeans should the listener register with? This is the role of **mapped ObjectNames**.
2. **Receive which notification types?** Should the listener receive all of them, or only certain types? This is the role of **`NotificationFilter`**.
3. **When the callback runs, how do we know which subscription this is?** This is the role of **`handback`**.

All three components form a clearly defined JMX subscription:

```text
Spring ApplicationContext
        |
        +--> MBeanExporter ----------------------+
        |                                        |
        |                              MBeanServer
        |                                        |
        +--> NotificationListenerBean             |
               |                                 |
               +-- mapped ObjectNames -----------+--> QueueMonitor
               |                                 +--> CacheMonitor
               +-- NotificationFilter
               +-- handback
               |
               v
         NotificationListener.handleNotification(notification, handback)
```

Key point: **ObjectName selects the source**, **filter selects the events**, and **handback provides callback context**. None of those components makes a bean emit notifications by itself; the emitter must implement the JMX notification contract and invoke the emission mechanism.

## 2. Distinguishing Notifications from Attributes and Operations

An MBean typically provides three interaction types:

| Capability | Interaction Direction | Example |
|---|---|---|
| Attribute | Client reads or writes state | `QueueDepth`, `WarningThreshold` |
| Operation | Client requests an action to execute | `pause()`, `resetCounters()` |
| Notification | Source proactively emits an event to listeners | `demo.queue.threshold.exceeded` |

Reading the `QueueDepth` attribute is a pull operation: the client must ask. A notification is a push from the broadcaster's perspective: when an event occurs, JMX distributes it to valid registrations.

Notifications do not necessarily provide durable storage, replay after disconnect, or exactly-once delivery. If you need event history and strict retries, use logging/an event store or an appropriate messaging system. For JMX, treat notifications as operational signals at the time of emission.

## 3. What Fields Does a Notification Have?

`javax.management.Notification` holds common data:

```java
Notification event = new Notification(
    "demo.queue.threshold.exceeded",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Queue depth exceeded the threshold"
);
event.setUserData(95);
```

Fields to distinguish:

| Field | Meaning |
|---|---|
| `type` | Event type string defined by the broadcaster |
| `source` | Source of the notification |
| `sequenceNumber` | Sequence number assigned by the broadcaster |
| `timeStamp` | Time the event was emitted/created |
| `message` | Human-readable description |
| `userData` | Supplemental payload of the notification |
| `handback` | **Not inside the notification**; comes from the subscription |

`handback` is the second parameter passed by JMX into `NotificationListener.handleNotification`, not a field placed on the event by the broadcaster. One notification can arrive at multiple registrations with the **same userData** but **different handbacks**.

`sequenceNumber` is not a global sequence across all MBeans. Each source may have its own counter, and counters can reset after restarts. Do not use sequence numbers alone as proof of complete delivery across multiple JVMs.

## 4. ObjectName and Mapped ObjectNames

`javax.management.ObjectName` identifies an MBean inside an `MBeanServer`.

Example:

```text
demo.queue:type=QueueMonitor,name=orders
demo.queue:type=QueueMonitor,name=payments
demo.cache:type=CacheMonitor,name=product
```

A Spring `NotificationListenerBean` can be configured with **mapped ObjectNames** to register only with a specific set of sources. The purpose of mapping is to avoid receiving notifications from MBeans outside the listener's scope.

Illustrative example:

```text
listener: alertListener

mappedObjectNames:
  - demo.queue:type=QueueMonitor,name=orders
  - demo.queue:type=QueueMonitor,name=payments

filter:
  receive only demo.queue.critical

handback:
  "oncall-queue"
```

When the exporter registers the listener with the corresponding MBeans, notifications from `demo.cache:type=CacheMonitor,name=product` will not automatically reach this listener merely because it is in the same JVM.

**Mapped ObjectNames select the broadcaster, not rename the notification type.** One MBean can emit multiple types and multiple MBeans can emit the same type. Therefore, when analyzing events, you usually need both source and type.

## 5. NotificationListenerBean in Spring Framework

Spring supports `org.springframework.jmx.export.notification.NotificationListenerBean` to bundle the elements of a registration:

- `NotificationListener` delegate that executes the callback.
- Optional `NotificationFilter` for filtering notifications.
- Optional `handback` containing registration context.
- List of `mappedObjectNames` identifying the relevant source MBeans.

Java configuration example:

```java
import javax.management.NotificationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.notification.NotificationListenerBean;

@Configuration
public class JmxListenerConfiguration {

    @Bean
    public NotificationListenerBean queueListenerBean(
            NotificationListener queueListener) {

        NotificationListenerBean registration =
            new NotificationListenerBean();

        registration.setNotificationListener(queueListener);
        registration.setMappedObjectNames(
            "demo.queue:type=QueueMonitor,name=orders",
            "demo.queue:type=QueueMonitor,name=payments"
        );

        registration.setHandback("queue-dashboard");
        return registration;
    }
}
```

This is a **bean describing a registration**, which is not enough without an exporter/registrar component actually applying it. For Spring to manage the subscription via `MBeanExporter`, you must include the `NotificationListenerBean` in the exporter's listener list or use the corresponding Spring JMX configuration.

Depending on the Spring version, setter signatures accepting ObjectNames represented as `String`, `ObjectName`, or `Object...` may be converted by Spring; use a concrete API compatible with your actual dependency. In Java configuration you can often construct `ObjectName` explicitly to reduce syntax ambiguity.

### 5.1. Lifecycle Principles

Listener registration is tied to the exporter lifecycle. When the exporter initializes and registers successfully, Spring can establish subscriptions; when the exporter closes, the registrations it manages should be removed per the lifecycle.

**Having a `NotificationListenerBean` does not mean a subscription already exists.** If you forget to bind it to the exporter, the callback methods may never be called. When debugging, inspect the exporter, MBeanServer, ObjectName, and registration timing rather than only checking that the `@Bean` was created.

## 6. Creating an Emitter: NotificationBroadcasterSupport

Let's build a Standard MBean that emits events when a queue exceeds a threshold.

### 6.1. Management Interface

```java
// QueueMonitorMBean.java
public interface QueueMonitorMBean {
    int getDepth();
    int getWarningThreshold();
    void setWarningThreshold(int value);
    void updateDepth(int value);
}
```

`Depth` is read-only, `WarningThreshold` is read-write, and `updateDepth` is an operation for testing.

### 6.2. Implementation Emitting Notifications

```java
// QueueMonitor.java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    public static final String WARNING = "demo.queue.warning";
    public static final String CRITICAL = "demo.queue.critical";

    private final AtomicLong sequence = new AtomicLong();
    private volatile int depth;
    private volatile int warningThreshold = 70;

    @Override
    public int getDepth() {
        return depth;
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int value) {
        if (value < 1 || value > 100) {
            throw new IllegalArgumentException(
                "WarningThreshold must be between 1 and 100"
            );
        }
        warningThreshold = value;
    }

    @Override
    public void updateDepth(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("Depth must be >= 0");
        }

        depth = value;
        if (value >= warningThreshold) {
            String type = value >= 90 ? CRITICAL : WARNING;
            Notification event = new Notification(
                type,
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Depth changed to " + value
            );
            event.setUserData(value);
            sendNotification(event);
        }
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { WARNING, CRITICAL },
                Notification.class.getName(),
                "Queue threshold events"
            )
        };
    }
}
```

`NotificationBroadcasterSupport` implements emission, listener registration, and unregistration. `getNotificationInfo()` publishes metadata; **metadata does not emit events by itself**. You must call `sendNotification(event)` in the required logic.

In this example, every depth update above the threshold emits an event. A real system might want to emit only on **threshold crossings** or state transitions, with debounce/rate limiting to avoid spam.

### 6.3. Why Can a Standard MBean Still Emit Notifications?

`QueueMonitor` implements `QueueMonitorMBean` to define attributes and operations while extending `NotificationBroadcasterSupport` to emit notifications. These two mechanisms complement each other.

The object is registered under the exact name:

```text
demo.queue:type=QueueMonitor,name=orders
```

JMX clients can read `Depth`, invoke `updateDepth`, and receive events via listener registrations once the MBean is properly registered.

## 7. NotificationFilter: Filtering by Type

`javax.management.NotificationFilter` declares:

```java
boolean isNotificationEnabled(Notification notification);
```

The filter returns `true` when the notification is allowed to be forwarded to the listener for that registration; returning `false` drops the notification from that registration.

Example receiving only critical:

```java
import javax.management.NotificationFilter;

NotificationFilter criticalOnly = notification ->
    notification != null &&
    QueueMonitor.CRITICAL.equals(notification.getType());
```

Filters can combine conditions: type, source, `userData` content, or sequence when meaningful. However, filters should process quickly without making network calls or long database queries.

If the filter is `null`, the registration requests no filtering and can receive every notification the broadcaster distributes for that subscription.

### 7.1. NotificationFilterSupport

JMX provides `NotificationFilterSupport` supporting filtering **by type prefix**:

```java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("demo.queue.");
```

The filter accepts types starting with `demo.queue.`, for example:

```text
demo.queue.warning
demo.queue.critical
demo.queue.recovered
```

Do not write:

```java
filter.enableType("demo.queue.*");
```

thinking `*` is a wildcard. `NotificationFilterSupport` checks a literal prefix, not a regular expression. If you want **only** `demo.queue.critical`, use a `NotificationFilter` performing an exact string comparison.

### 7.2. Filtering by userData

```java
NotificationFilter largeDepthOnly = event -> {
    if (!QueueMonitor.WARNING.equals(event.getType())) {
        return false;
    }
    return event.getUserData() instanceof Integer depth &&
        depth >= 80;
};
```

The code above requires the `userData` payload to be of type `Integer` per the broadcaster's contract. With remote JMX, the payload must also be compatible with serialization and client-side class access permissions. Do not treat arbitrary `userData` as already validated or guaranteed to have the expected type.

## 8. Handback: Context Supplied by the Subscriber

The `NotificationListener` interface:

```java
void handleNotification(
    Notification notification,
    Object handback
);
```

`handback` is an object **placed into the registration by the subscriber**, which JMX then passes back to the listener when the callback executes. It is not a broadcaster payload.

Example:

```java
NotificationListener listener = (notification, handback) -> {
    System.out.printf(
        "channel=%s type=%s source=%s payload=%s%n",
        handback,
        notification.getType(),
        notification.getSource(),
        notification.getUserData()
    );
};
```

When a registration has handback `"oncall"`, the callback receives that string. Another listener can register with handback `"audit"` and still receive the same notification.

### 8.1. Comparing userData and handback

| Characteristic | `notification.getUserData()` | `handback` |
|---|---|---|
| Supplied by | Broadcaster | Subscriber |
| Tied to | Specific event | Specific registration |
| Can differ between two listeners receiving the same event? | Usually stays the same for the same event | Yes |
| Primary purpose | Event details | Processing/routing context |
| Replaces authentication? | No | No |

Handback can be `null` and can be an immutable context object. Do not use handback to pass passwords, tokens, or heavy resources. For local listeners, keeping a small context record is an easy-to-understand design.

```java
public record SubscriptionContext(
    String channel,
    String component
) {}
```

In a remote connector, managing/storing handback belongs to the client/connector side. Do not assume that handback is data sent to the server.

## 9. Mapped ObjectNames and Multiple Registrations

One Spring `NotificationListenerBean` can be used for multiple ObjectNames. That creates subscriptions corresponding to multiple broadcasters, with the same configured listener/filter/handback.

Example:

```text
QueueMonitor orders
  ObjectName = demo.queue:type=QueueMonitor,name=orders

QueueMonitor payments
  ObjectName = demo.queue:type=QueueMonitor,name=payments

NotificationListenerBean:
  mappedObjectNames = [orders, payments]
  filter = criticalOnly
  handback = "oncall"
```

Expected results:

- WARNING notification from orders: does not reach the listener if using the criticalOnly filter.
- CRITICAL notification from orders: callback receives `handback="oncall"`.
- CRITICAL notification from payments: callback also receives `handback="oncall"`.
- CRITICAL notification from another MBean not in mapped names: this listener does not receive it from that mapping.

Because handback is identical for both sources, the callback needs to also inspect `notification.getSource()` or use an appropriate ObjectName/context to determine whether it originated from orders or payments.

If you need different handbacks per source, you can create **two `NotificationListenerBean` registrations** using the same listener delegate but separate `mappedObjectNames` and handbacks:

```text
Registration A:
  mappedObjectNames = [orders]
  handback = "orders-channel"

Registration B:
  mappedObjectNames = [payments]
  handback = "payments-channel"
```

This is a classic case for configuring multiple registrations instead of cramming a custom lookup table into a single handback.

## 10. Combining with MBeanExporter in Spring

Spring `MBeanExporter` can manage exporting beans and registering notification listeners. Illustrative Java configuration example with explicit types:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.notification.NotificationListenerBean;

@Configuration
public class CompleteJmxConfiguration {

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public QueueMonitor ordersQueueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public QueueMonitor paymentsQueueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public NotificationListener queueNotificationListener() {
        return (event, handback) ->
            System.out.printf(
                "[%s] type=%s source=%s depth=%s%n",
                handback,
                event.getType(),
                event.getSource(),
                event.getUserData()
            );
    }

    @Bean
    public NotificationFilter criticalFilter() {
        return event ->
            QueueMonitor.CRITICAL.equals(event.getType());
    }

    @Bean
    public NotificationListenerBean ordersCriticalRegistration(
            NotificationListener queueNotificationListener,
            NotificationFilter criticalFilter) {

        NotificationListenerBean listener =
            new NotificationListenerBean();

        listener.setNotificationListener(queueNotificationListener);
        listener.setMappedObjectNames(
            "demo.queue:type=QueueMonitor,name=orders"
        );
        listener.setNotificationFilter(criticalFilter);
        listener.setHandback("orders-oncall");
        return listener;
    }

    @Bean
    public NotificationListenerBean paymentsCriticalRegistration(
            NotificationListener queueNotificationListener,
            NotificationFilter criticalFilter) {

        NotificationListenerBean listener =
            new NotificationListenerBean();

        listener.setNotificationListener(queueNotificationListener);
        listener.setMappedObjectNames(
            "demo.queue:type=QueueMonitor,name=payments"
        );
        listener.setNotificationFilter(criticalFilter);
        listener.setHandback("payments-oncall");
        return listener;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            QueueMonitor ordersQueueMonitor,
            QueueMonitor paymentsQueueMonitor,
            NotificationListenerBean ordersCriticalRegistration,
            NotificationListenerBean paymentsCriticalRegistration) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(
            "demo.queue:type=QueueMonitor,name=orders",
            ordersQueueMonitor,
            "demo.queue:type=QueueMonitor,name=payments",
            paymentsQueueMonitor
        ));
        exporter.setNotificationListeners(
            ordersCriticalRegistration,
            paymentsCriticalRegistration
        );
        return exporter;
    }
}
```

The configuration creates one exporter, two Standard MBeans, and two registrations describing listener, filter, and handback. Each registration observes exactly one ObjectName so handback identifies the context source.

**Note when adapting to a real project:** all interfaces/classes must exist on the corresponding Spring Framework classpath; if dependency injection by type is ambiguous due to multiple beans of type `QueueMonitor`, use `@Qualifier` or injection by name, as the example distinguishes parameter names. If there are multiple `NotificationListenerBean` or `NotificationFilter` beans, use explicit qualifiers rather than relying solely on variable names.

Do not enable another automatic exporter for the same two ObjectNames without designing registration policy/ownership; doing so can cause duplicate MBeans.

## 11. Invoking Test MBeans After Spring Context Refresh

Create a lab runner class:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Application {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    CompleteJmxConfiguration.class
                )) {

            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName orders = new ObjectName(
                "demo.queue:type=QueueMonitor,name=orders"
            );
            ObjectName payments = new ObjectName(
                "demo.queue:type=QueueMonitor,name=payments"
            );

            System.out.println(
                "orders registered=" + server.isRegistered(orders)
            );
            System.out.println(
                "payments registered=" + server.isRegistered(payments)
            );

            QueueMonitor orderTarget =
                context.getBean("ordersQueueMonitor", QueueMonitor.class);
            QueueMonitor paymentTarget =
                context.getBean("paymentsQueueMonitor", QueueMonitor.class);

            orderTarget.updateDepth(50);
            orderTarget.updateDepth(75);
            orderTarget.updateDepth(95);
            paymentTarget.updateDepth(92);

            Thread.sleep(1_000L);
        }
    }
}
```

Expected logical output:

```text
orders registered=true
payments registered=true
[orders-oncall] type=demo.queue.critical ... depth=95
[payments-oncall] type=demo.queue.critical ... depth=92
```

The WARNING notification (depth=75) does not reach registrations that accept only CRITICAL. If you add an unfiltered registration for orders, WARNING can reach that registration.

**Do not rely on callback line ordering as a contract:** `NotificationBroadcasterSupport` may dispatch via a configured executor, connector, and arrival timing; if strict ordering is required, design for it separately.

## 12. Distinguishing Spring NotificationListenerBean from Plain JMX NotificationListener

In plain Java JMX, you register:

```java
server.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
```

Spring adds a configuration class:

```java
NotificationListenerBean registration =
    new NotificationListenerBean();

registration.setNotificationListener(listener);
registration.setNotificationFilter(filter);
registration.setHandback(handback);
registration.setMappedObjectNames(objectName);

exporter.setNotificationListeners(registration);
```

In principle, both ultimately create a registration on the MBeanServer. Spring helps bind the registration to bean configuration and the exporter lifecycle.

However, Spring does not alter the meaning of filter/handback in the JMX contract. If the filter returns `false`, the notification is not forwarded to that registration. If handback is `null`, the callback receives null. If the MBean is not a broadcaster, the registration does not create emission capability by itself.

## 13. What Happens When mappedObjectNames Is Not Configured?

`NotificationListenerBean` supports mapping to bind to specific MBeans. When mapped ObjectNames are omitted, behavior can depend on how `MBeanExporter` handles listener configuration and the Spring version, including cases where the listener is attached to MBeans managed by the exporter.

Therefore, for lessons with predictable outcomes, **specify ObjectNames explicitly** for the MBeans you want to observe. Avoid relying on the assumption that a listener will automatically subscribe to every MBean across the entire platform server.

If the goal is to listen to a group of MBeans by domain/pattern, verify whether your version/configuration supports pattern expansion as expected; an ObjectName pattern does not automatically mean the registration will update itself when new MBeans appear later.

An explicit list is usually safer and easier to audit.

## 14. Distinguishing Mapping from Filtering by Source

Suppose two notifications have the same `type`:

```text
demo.queue.critical from orders
demo.queue.critical from payments
```

You can:

- Use mapped ObjectNames containing only orders, with a filter accepting only `critical`.
- Use mapped ObjectNames containing both, with a filter additionally branching by source.
- Use two registrations with different handbacks.

The first strategy is simple when only one source needs listening. The third strategy is convenient when sharing the same handling logic but needing different routing.

**Filtering by source does not completely replace mapped ObjectNames.** If a listener registers with too many broadcasters and then discards most events afterward, the configuration still creates unnecessary registrations. Select the right sources first, then filter events.

Similarly, mapped ObjectNames do not replace `NotificationFilter`: an MBean may emit WARNING/CRITICAL/RECOVERED and a listener may need only CRITICAL.

## 15. One Listener Registered Multiple Times and the Risk of Duplicate Processing

A listener instance can be registered multiple times with the same MBean, for example:

```text
Registration A:
  ObjectName = orders
  Filter = demo.queue.
  Handback = dashboard

Registration B:
  ObjectName = orders
  Filter = demo.queue.critical
  Handback = pager
```

When orders emits CRITICAL, the event can match both. The callback may run **twice** with the same notification but different handbacks:

```text
handleNotification(event #42, "dashboard")
handleNotification(event #42, "pager")
```

This is not necessarily duplicate emission by the broadcaster; it can be two valid subscriptions.

If downstream systems require guaranteeing that the same event is not processed twice, design idempotency or an application event ID. Relying on `sequenceNumber` alone is insufficient in multi-source systems or across restarts.

## 16. Filtering Notifications Safely, Quickly, and Predictably

A filter usually runs during notification dispatch. It should:

- Check well-defined types and payloads.
- Return a `boolean` quickly.
- Not call a database/remote service.
- Not mutate business state.
- Not log sensitive payloads.
- Tolerate null notifications or unexpected userData when needed.

Example filter with type validation:

```java
NotificationFilter criticalWithDepth = event -> {
    if (event == null || !QueueMonitor.CRITICAL.equals(
            event.getType())) {
        return false;
    }

    Object data = event.getUserData();
    return data instanceof Integer depth && depth >= 90;
};
```

The listener callback should also be short and offload heavy work to a controlled queue/executor. Do not assume every callback always runs on a separate thread; the broadcaster or connector determines dispatch behavior.

In production, if the event rate is high, apply rate limiting, aggregation, or deduplication before sending alerts. Otherwise, an MBean generating many notifications can overload the listener and logging pipeline.

## 17. Lifecycle: Startup, Unregister, and Shutdown

An active subscription depends on multiple milestones:

```text
Spring context starts
    |
    +--> QueueMonitor beans created
    +--> MBeanExporter registers ObjectNames
    +--> exporter sets up NotificationListenerBeans
    |
    +--> source emits notification
    |        |
    |        +--> filter
    |                |
    |                +--> listener callback(handback)
    |
Spring context closes
    |
    +--> exporter removes registrations it manages
    +--> MBean registrations cleaned up per lifecycle
```

Situations that need handling:

1. Source MBean is not yet registered when the listener tries to subscribe.
2. Wrong ObjectName, different domain, or different properties.
3. Exporter points to a different MBeanServer than where the source is registered.
4. Two contexts using the same ObjectName and registration policy produce unexpected results.
5. Source unregisters/re-registers, rendering the old subscription meaningless.
6. Context closes while already-dispatched callbacks are still running.
7. Notification is emitted too early, before the listener is attached.
8. Spring listener bean exists but was not configured into the exporter.

Do not assume JMX buffers a backlog to resend notifications emitted before the subscription succeeded. If an important event must be retrievable after startup, expose current state via an attribute or a separate event store.

## 18. Checking Metadata and Registrations from MBeanServer

To verify that a source can emit notifications:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = server.getMBeanInfo(orders);

for (MBeanNotificationInfo notificationInfo :
        info.getNotifications()) {
    System.out.println(
        "Notification class=" + notificationInfo.getName()
    );
    for (String type : notificationInfo.getNotifTypes()) {
        System.out.println("  type=" + type);
    }
}
```

`MBeanInfo.getNotifications()` shows metadata published by the source. However, metadata does not guarantee notifications will be emitted during observation; that depends on actual events and `sendNotification` logic.

Check that the source exists:

```java
System.out.println(server.isRegistered(orders));
```

Then generate a test event in the lab environment using the `updateDepth` operation. If the callback does not run, inspect each stage in order:

```text
MBean registered?
  -> Emitting notifications?
  -> Listener registration created by exporter?
  -> Mapped ObjectName matches?
  -> Filter returns true?
  -> Callback throwing an exception?
```

Do not randomly change multiple configurations at once before knowing at which step the event is blocked.

## 19. Spring XML Configuration (When Legacy Projects Use XML)

In traditional Spring applications using XML, the same parameters can be provided via bean properties:

```xml
<bean id="notificationListener"
      class="com.example.jmx.LoggingNotificationListener"/>

<bean id="criticalFilter"
      class="javax.management.NotificationFilterSupport">
    <property name="enabledTypes">
        <!-- Illustrates structure only; in practice use
             the enableType helper method or a custom filter. -->
    </property>
</bean>
```

For `NotificationListenerBean`, the key properties are `notificationListener`, `notificationFilter`, `handback`, and `mappedObjectNames`. For `MBeanExporter`, the `notificationListeners` property binds the registrations.

If complete XML is needed, base it on the schema, Spring version, and the proper way to configure `NotificationFilterSupport` (since `enableType` is a state-mutating method, not a JavaBeans `enabledTypes` setter). In new projects, Java `@Bean` configuration is usually clearer for creating filters and mappings.

## 20. Spring Boot Integration

Spring Boot provides auto-configuration for JMX export depending on `spring.jmx.enabled` and other conditions. However, **enabling JMX export does not automatically register every notification listener bean as intended**. You must ensure registrations are linked to the exporter actually active in the context.

If an exporter created by Boot/Spring already exists, manually creating a new exporter can export the same bean twice or cause ObjectName collisions. In Boot systems, inventory exporter beans first, establish ownership, and choose a consistent strategy.

Distinguish:

- Spring `ApplicationEvent`: event inside the application context.
- Spring JMX `NotificationListenerBean`: JMX listener registration configuration.
- JMX `Notification`: event object emitted by an MBean.
- Spring Boot Actuator: set of management/monitoring endpoints; does not mean every endpoint emits JMX notifications.

If you want to convert notifications into ApplicationEvents, an explicit adapter is needed; JMX does not automatically push notifications onto the Spring event bus.

## 21. Data Safety and Management Permissions

JMX notifications can be collected by local or remote clients. Do not send secrets, tokens, request bodies, or personal data in `notification.getMessage()` or `notification.getUserData()` simply because they are convenient for debugging.

Handback can contain an object from the client, but should not be used to hold sensitive credentials or replace authorization. If a listener uses handback to route alerts, validate the context type and keep it immutable whenever possible.

Remote JMX requires:

- Proper authentication and authorization.
- TLS or a trusted protected channel.
- Management network restriction.
- Never exposing public RMI/JMX ports.
- Auditing operations with side effects.
- Handling reconnection, event loss, and subscription lifecycle.
- Not assuming notifications are a durable message queue.

For a critical event such as a payment failure, emit a notification containing summary status and a non-sensitive correlation ID; business details should be stored in an appropriate system.

## 22. Common Errors

### 22.1. Listener Bean Exists in Spring but Receives No Events

You created a `NotificationListenerBean` but forgot to attach it to `MBeanExporter`. Fix the binding configuration and verify the exporter has initialized.

### 22.2. Wrong ObjectName Mapping

The source is registered as `demo.queue:type=QueueMonitor,name=orders`, but the mapped name says `demo.queues:type=QueueMonitor,name=orders`. Even differing by domain or a key property prevents the listener from tracking the right source. Use `MBeanServer.queryNames` to verify the actual name.

### 22.3. Misusing Regex in FilterSupport

`enableType("demo.queue.*")` is not a wildcard. Use `enableType("demo.queue.")` to match by prefix or a custom filter for exact matching.

### 22.4. Confusing handback with userData

`userData` comes from the broadcaster in each event; `handback` comes from the subscriber at registration time. If you need the event's `queueDepth`, read the payload; if you need which channel the subscription belongs to, read handback.

### 22.5. Same Listener Callback Fires Twice

This may be due to two overlapping registrations, not necessarily duplicate emission by the broadcaster. List the source/filter/handback of each subscription to identify it.

### 22.6. Listener Registered but MBean Emits Nothing

The MBean must actually be a notification broadcaster and call `sendNotification`. Overriding `getNotificationInfo` metadata is not enough.

### 22.7. Event Emitted Before Listener Registration

JMX does not guarantee replay of past notifications. If the client needs to know whether state is currently CRITICAL, read the attribute after registering or use a state-sync mechanism.

### 22.8. Callback Throws an Exception and Breaks Expected Behavior

Guard the listener, use controlled logging, and offload heavy work to a dedicated processor. Do not assume listener exceptions will be retried.

### 22.9. Exporter Not on the Same MBeanServer as Source

A single JVM can have multiple MBeanServers. If the source registers on A while listener registration happens on B, identical names will still not make the subscription work.

## 23. Hands-On Scenarios

**Exercise 1 — Receive only critical from orders.** Register a listener with `mappedObjectNames` containing only orders, a filter accepting only `demo.queue.critical`, and handback `"orders-oncall"`. Emit WARNING and CRITICAL to compare.

**Exercise 2 — Two sources, one listener.** Map orders and payments to the same listener using a shared critical filter. Inspect `notification.getSource()` to distinguish sources, since handback is the same.

**Exercise 3 — Two different handbacks.** Create two separate `NotificationListenerBean`s for orders/payments with the same delegate; assign `"orders-channel"` and `"payments-channel"`. Demonstrate that the callback receives the per-registration handback.

**Exercise 4 — FilterSupport prefix.** Use `enableType("demo.queue.")` and emit types `demo.queue.warning`, `demo.queue.critical`, `demo.cache.evicted`. Record which types are received and explain prefix matching.

**Exercise 5 — Duplicate registrations.** Create two registrations both mapping orders with overlapping filters. Emit CRITICAL and explain why two callbacks can be valid.

**Exercise 6 — Lifecycle error.** Emit an event before the Spring exporter finishes registration; then emit again. Explain why the first event is not automatically replayed.

**Exercise 7 — Metadata.** Use `MBeanServer.getMBeanInfo` to list the notification types of `QueueMonitor`; compare with the client's filter.

**Exercise 8 — Closing context.** Use `try-with-resources` for `AnnotationConfigApplicationContext`, emitting events before and after cleanup in a lab with proper source management. Observe that listener registrations have a lifecycle and should not continue receiving events once the exporter has closed.

## 24. Self-Check Questions

1. What does `mappedObjectNames` of `NotificationListenerBean` determine?
2. How does `NotificationFilter` differ from source mapping?
3. Does `NotificationFilterSupport.enableType` work by prefix or regex?
4. Is `handback` supplied by the broadcaster or the subscriber?
5. How can `handback` and `userData` differ?
6. Can a listener registered twice with the same source receive the same notification twice?
7. Why might a `NotificationListenerBean` exist in the context without any callbacks running?
8. If an MBean does not call `sendNotification`, is notification metadata enough for the listener to receive events?
9. Why must you check the actual ObjectName instead of guessing from the Spring bean name?
10. Do JMX notifications replay after a disconnect or after a listener registers late?
11. When should you create two separate registrations to have two handbacks?
12. What risks arise if notification payloads contain secrets?

## 25. Key Takeaways

In Spring Framework JMX, **`NotificationListenerBean` bundles a listener, filter, handback, and a set of mapped ObjectNames so the exporter registers an intentional subscription**. ObjectNames determine which emitters to listen to; filters determine which notifications reach the callback; handback carries context defined by the registrar.

For the configuration to work, the MBean must be capable of emitting notifications, the exporter must create the registration on the right MBeanServer, and the ObjectName must match. Keep filters fast, callbacks safe, exclude sensitive payloads, manage lifecycle, and verify with test events as well as `MBeanInfo`. When durable delivery is needed, do not use JMX notifications in place of an event broker.
