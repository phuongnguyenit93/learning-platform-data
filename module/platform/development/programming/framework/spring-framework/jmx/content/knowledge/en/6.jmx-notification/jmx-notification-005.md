# NotificationListener, NotificationFilter, and handback in JMX

## 1. From Passive Observation to Active Event Receiving

In Java Management Extensions (JMX), a management tool often reads state via `MBeanServerConnection.getAttribute(...)`: memory used, thread count, active connections, error counts. That approach is suitable for taking a **state snapshot**, but it has an obvious limitation: to know whether state has changed, the client must actively ask again.

Suppose a task-processing queue has `QueueDepth` and `Capacity`. Operators need to know immediately when the queue exceeds a threshold, a task fails critically, or runtime configuration changes. With polling alone, the tool must pick a sampling interval, accept latency, and risk missing short events occurring between reads.

JMX provides **Notification**: an MBean or event-emitting component (*notification broadcaster*) sends a `Notification` object to registered recipients. To control notification handling, JMX has three core concepts:

- **`NotificationListener`**: the event receiver; its callback is invoked when a matching notification arrives.
- **`NotificationFilter`**: decides which notifications are forwarded to the listener for a registration.
- **`handback`**: a context object supplied by the registrant, returned as the exact same reference to the callback; it is not data emitted by the MBean.

All three work together inside a registration at the MBeanServer. A single listener can be registered multiple times with different filters and handbacks, allowing the same handler logic to be reused across multiple sources or operational contexts.

```text
                 Java Application / MBean
                      |
          management event occurs
                      |
              NotificationEmitter
                      |
                  Notification
                      |
             MBeanServer / JMX
                      |
     +----------------+----------------+
     |                                 |
Registration A                    Registration B
listener L + filter F1            listener L + filter F2
handback "critical"               handback "audit"
     |                                 |
filter permits?                   filter permits?
     |                                 |
handleNotification(n, "critical")  handleNotification(n, "audit")
```

The model above shows that **notification is the event data**, **filter is the event selection condition**, and **handback is the registration context**. These concepts are independent of the application's business methods.

## 2. What Information Does Notification Contain?

`javax.management.Notification` is the base class for JMX notifications. A typical notification has the following properties:

| Property | Role |
|---|---|
| `type` | Event classification string, usually domain-style, e.g., `demo.queue.threshold.exceeded` |
| `source` | Object or name of the notification emission source |
| `sequenceNumber` | Sequence number assigned by the emitter |
| `timeStamp` | Event timestamp, in milliseconds since Unix epoch |
| `message` | Human-readable description, may be empty |
| `userData` | Extended payload set by the application, if any |

Example of creating an event:

```java
Notification notification = new Notification(
    "demo.queue.threshold.exceeded",
    sourceObject,
    nextSequenceNumber,
    System.currentTimeMillis(),
    "Queue depth crossed warning threshold"
);
notification.setUserData("queue=orders, depth=85");
```

`type` is the classification key defined by the event-emission contract. In a system with many notifications, designing stable types helps filters select accurately. `message` helps humans understand quickly, but should not be the criterion for automated processing when a clearly structured `type` exists.

**Sequence number is managed by the emission source**, not a global sequence across all MBeans. It is useful for checking sequence for a single source during an operational period, but does not by itself prove that all messages over the network were received or that there are no duplicates. A sequence can restart when an MBean/JVM is recreated.

**Timestamp does not replace a logical clock or distributed ordering**: across multiple JVMs there can be clock skew, transmission latency, and processing differences. When strict tracing is needed, combine notifications with logs, correlation IDs, and a suitable event-storage system.

## 3. NotificationListener: Where Events Are Received and Handled

The `javax.management.NotificationListener` interface has one method:

```java
void handleNotification(Notification notification, Object handback);
```

The first parameter is the actual notification created by the emitter. The second parameter is the **handback** supplied when registering the listener. A callback can receive multiple notification types; therefore, it often needs to read `notification.getType()` or payload data before processing.

Example:

```java
import javax.management.Notification;
import javax.management.NotificationListener;

public final class LoggingListener implements NotificationListener {
    @Override
    public void handleNotification(Notification notification, Object handback) {
        System.out.printf(
            "[%s] type=%s, source=%s, sequence=%d, message=%s%n",
            handback,
            notification.getType(),
            notification.getSource(),
            notification.getSequenceNumber(),
            notification.getMessage()
        );
    }
}
```

A listener does not discover sources to watch on its own. You must register the listener with a broadcaster, directly or through MBeanServer:

```java
server.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
```

When a notification passes the filter, JMX delivers the notification and corresponding handback to the callback.

### 3.1. Where can a listener be registered?

If code holds a reference to a local `NotificationEmitter` object, it can register directly with `emitter.addNotificationListener(listener, filter, handback)`.

For an MBean registered on an `MBeanServer`, use `MBeanServer.addNotificationListener(ObjectName, NotificationListener, NotificationFilter, Object)`. Remote JMX clients can use the corresponding API on `MBeanServerConnection`.

Registration is valid only when the source object supports emitting notifications. If the MBean lacks the appropriate broadcaster/emitter capability, registration may fail with `RuntimeOperationsException` or an appropriate JMX exception depending on the case. A getter changing value does not mean that MBean automatically emits notifications.

### 3.2. What should a callback do?

A callback is code executed when JMX delivers an event. It should perform short, controlled work:

- Inspect `type`, `source`, and necessary payload.
- Offload the event to another processor if handling takes time.
- Log useful information without logging secrets.
- Guard callback code against exceptions caused by unexpected data.
- Avoid invoking risky operations or long blocking calls merely upon receiving a notification.

Do not assume a single threading model for every broadcaster or connector. With `NotificationBroadcasterSupport`, dispatch behavior can depend on the configured `Executor`. With remote JMX, the connector also affects when callbacks execute. Do not design callbacks assuming they always run on a specific business thread.

## 4. NotificationFilter: Controlling Which Messages Reach the Listener

`javax.management.NotificationFilter` is effectively a functional interface: it has the method `boolean isNotificationEnabled(Notification notification)`.

```java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter onlyCritical = notification ->
    notification != null
        && "demo.queue.critical".equals(notification.getType());
```

When registering:

```java
server.addNotificationListener(
    objectName,
    listener,
    onlyCritical,
    "critical-channel"
);
```

If the filter returns `true`, the notification is allowed through to the listener. If it returns `false`, that registration does not receive the notification. **Filters operate per registration**, and do not prevent a notification from being sent to other listeners. A single notification can be delivered to multiple listeners if their respective filters accept it.

Passing `null` as the filter means no filtering is requested for that registration: the listener can receive every notification the broadcaster emits for that registration.

### 4.1. NotificationFilterSupport

JMX provides `javax.management.NotificationFilterSupport` to filter based on notification type prefixes:

```java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("demo.queue.");
```

The filter above accepts types starting with `demo.queue.`, such as:

```text
demo.queue.warning
demo.queue.critical
demo.queue.recovered
```

and rejects `demo.cache.evicted`.

**Note:** `enableType("demo.queue.")` is **prefix matching**, not a regex and not necessarily a full-string match. If you want to receive strictly one type, use a custom `NotificationFilter` or exact comparison logic.

`NotificationFilterSupport` also provides `disableType(...)`, `disableAllTypes()`, and `getEnabledTypes()` to manage enabled prefixes. Because the rule is prefix-based, a broad type like `demo.` can widen the event scope more than intended.

### 4.2. Custom content-based filtering

When filtering requirements go beyond type, you can inspect `userData` or notification properties:

```java
NotificationFilter highSequenceOnly = notification ->
    notification != null
        && "demo.queue.warning".equals(notification.getType())
        && notification.getSequenceNumber() >= 100;
```

The condition above is only a technical example. In practice, sequence numbers do not represent alert severity, so if you want to filter by severity, provide an explicit severity field in the event contract.

Filters should be simple, fast, and free of side effects. A filter that calls a database or mutates state can slow down the event-emitting flow, depending on the dispatch model. If complex analysis is needed, accept the simple event and pass it to an appropriate processing pipeline.

## 5. Handback: Context for a Single Registration

Handback is often misunderstood as data sent along with a notification. In reality, it is **an object chosen by the listener registrant and passed in at registration time**, which JMX then passes back to the listener when the callback is invoked.

```java
Object handback = "operations-dashboard";

server.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
```

Inside the callback:

```java
@Override
public void handleNotification(Notification notification, Object handback) {
    System.out.println("Subscription context: " + handback);
}
```

Important distinction:

| Data Field | Provided by Whom? | Bound To |
|---|---|---|
| `notification.getUserData()` | Event emitter | The notification itself |
| `notification.getSource()` | Event emitter/JMX may normalize via MBeanServer | The event emission source |
| `handback` | Listener registrant | The specific registration |
| `notification.getType()` | Event emitter | The event type |

One broadcaster emits the same notification to two registrations, yet each registration can receive a different handback. This is very handy when one listener class is reused:

```java
LoggingListener shared = new LoggingListener();

server.addNotificationListener(
    objectName, shared, warningFilter, "dashboard"
);
server.addNotificationListener(
    objectName, shared, criticalFilter, "pager"
);
```

If a notification is accepted by both filters, the callback can be invoked twice with two different handbacks. Do not assume "one notification triggers only one callback" when the same listener has been registered multiple times.

### 5.1. Can handback be any object?

In local registrations, handback can be any regular Java object the listener uses as context, such as a record:

```java
public record ListenerContext(String channel, String component) {}

ListenerContext context =
    new ListenerContext("dashboard", "orders");
```

With remote notifications, exact handback handling depends on how the connector manages registrations; under the standard JMX connector model, handback is kept on the client side to pass to the client's callback, so do not assume handback is a payload sent to the server. Therefore, avoid putting sensitive data or heavy resource references into handback unnecessarily.

Handback can be `null`; listeners must handle that case. If a mutable object is used as handback, multiple callbacks may observe mutated state. Use an immutable context when predictable behavior is desired.

### 5.2. Handback is not a security identity mechanism

Do not use handback values to replace authentication/authorization or implicitly trust that an event is authentic. It is merely a context parameter from the registering code, not proof of event origin or operation permissions.

## 6. Complete Java Example: Broadcaster, Listener, Filter, and Handback

This example demonstrates an MBean monitoring queue depth. When depth exceeds a threshold, the MBean emits a notification; two registrations reuse the same listener with different filters and handbacks.

### 6.1. Define the MBean interface

```java
// QueueMonitorMBean.java
public interface QueueMonitorMBean {
    int getDepth();
    int getWarningThreshold();
    void setWarningThreshold(int threshold);
    void updateDepth(int depth);
}
```

Getters/setters create management attributes; `updateDepth` is an operation. A real application might let only internal code call update and not export this operation; in the example, it is exposed for easy testing via a JMX client.

### 6.2. Implement the notification-emitting MBean

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
    public void setWarningThreshold(int threshold) {
        if (threshold < 1 || threshold > 100) {
            throw new IllegalArgumentException(
                "WarningThreshold must be 1..100"
            );
        }
        warningThreshold = threshold;
    }

    @Override
    public void updateDepth(int newDepth) {
        if (newDepth < 0) {
            throw new IllegalArgumentException("Depth cannot be negative");
        }

        depth = newDepth;

        if (newDepth >= warningThreshold) {
            String type = newDepth >= 90 ? CRITICAL : WARNING;

            Notification notification = new Notification(
                type,
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Queue depth changed to " + newDepth
            );
            notification.setUserData(newDepth);
            sendNotification(notification);
        }
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {WARNING, CRITICAL};
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                Notification.class.getName(),
                "Queue depth threshold notifications"
            )
        };
    }
}
```

Here `NotificationBroadcasterSupport` supplies listener registration/removal and notification emission machinery. It implements `NotificationEmitter`, so when registered as an appropriate MBean, clients can register listeners via MBeanServer.

`getNotificationInfo()` exposes metadata describing the notification types the MBean can emit. Metadata helps tools discover event-emitting capabilities; it does not send notifications on its own. Only when `sendNotification(...)` is called is a notification actually emitted.

The example above emits a notification whenever `updateDepth` receives a value **above the threshold**, even if it was already above the threshold beforehand. This is an illustrative choice. Real systems may need to emit only when **crossing the threshold**, with debouncing, rate limiting, and recovery events.

### 6.3. Registering two observation streams

```java
// Main.java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationFilter;
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class Main {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        QueueMonitor monitor = new QueueMonitor();

        ObjectName name =
            new ObjectName("demo.queue:type=QueueMonitor,name=orders");
        server.registerMBean(monitor, name);

        NotificationListener listener = (notification, handback) -> {
            System.out.printf(
                "channel=%s | type=%s | seq=%d | depth=%s%n",
                handback,
                notification.getType(),
                notification.getSequenceNumber(),
                notification.getUserData()
            );
        };

        NotificationFilterSupport warnings = new NotificationFilterSupport();
        warnings.enableType("demo.queue.warning");
        warnings.enableType("demo.queue.critical");

        NotificationFilter onlyCritical =
            notification -> QueueMonitor.CRITICAL.equals(
                notification.getType()
            );

        server.addNotificationListener(
            name, listener, warnings, "dashboard"
        );
        server.addNotificationListener(
            name, listener, onlyCritical, "pager"
        );

        monitor.updateDepth(40); // Does not emit.
        monitor.updateDepth(75); // Dashboard receives WARNING.
        monitor.updateDepth(95); // Both Dashboard and Pager receive CRITICAL.

        server.removeNotificationListener(
            name, listener, warnings, "dashboard"
        );
        server.removeNotificationListener(
            name, listener, onlyCritical, "pager"
        );

        server.unregisterMBean(name);
    }
}
```

When run, typical output:

```text
channel=dashboard | type=demo.queue.warning | seq=1 | depth=75
channel=dashboard | type=demo.queue.critical | seq=2 | depth=95
channel=pager     | type=demo.queue.critical | seq=2 | depth=95
```

The order of the two callbacks receiving `CRITICAL` may depend on the dispatch mechanism; do not treat log line order as a guarantee across multiple listeners. The point to observe is that **the same notification can be delivered to multiple registrations with different handbacks**.

## 7. Lifecycle Management: Registering and Removing Listeners

Listeners must be lifecycle-managed so they do not leak registrations or keep processing events after the receiving component has stopped.

JMX provides two groups of listener removal operations:

```java
// Remove all registrations matching listener on this MBean:
server.removeNotificationListener(name, listener);

// Remove the exact registration by listener, filter, and handback:
server.removeNotificationListener(name, listener, filter, handback);
```

When the same listener is registered multiple times, the overload with `filter` and `handback` is appropriate when you want to remove each subscription precisely. The API matches the filter and handback objects by registration identity; retain the exact references used at registration time, avoiding creating new look-alike filter/context objects and expecting removal to match.

After removal, callbacks that were already dispatched beforehand may still be running depending on execution and connector behavior. If the lifecycle requires stopping processing completely, the listener must also track closed state and in-flight work.

A simple pattern:

```java
final class ManagedRegistration implements AutoCloseable {
    private final MBeanServer server;
    private final ObjectName name;
    private final NotificationListener listener;
    private final NotificationFilter filter;
    private final Object handback;

    ManagedRegistration(
            MBeanServer server,
            ObjectName name,
            NotificationListener listener,
            NotificationFilter filter,
            Object handback) throws Exception {
        this.server = server;
        this.name = name;
        this.listener = listener;
        this.filter = filter;
        this.handback = handback;
        server.addNotificationListener(name, listener, filter, handback);
    }

    @Override
    public void close() throws Exception {
        server.removeNotificationListener(
            name, listener, filter, handback
        );
    }
}
```

In production code, exception signatures should be more specific as needed, and if multiple resources are initialized, release them in reverse order. `AutoCloseable` lets you place the registration in a `try-with-resources` block to reduce the risk of forgetting cleanup.

## 8. One Listener, Multiple Registrations, and Duplicate Processing Risk

Consider this setup:

```java
NotificationListener listener = new LoggingListener();

server.addNotificationListener(name, listener, null, "all");
server.addNotificationListener(name, listener, criticalOnly, "critical");
```

A `critical`-type notification matches both registrations. The listener can receive **two callbacks for the same notification**:

```text
Notification #42
  -> registration ("all")      -> callback(notification #42, "all")
  -> registration ("critical") -> callback(notification #42, "critical")
```

You cannot rely on the `NotificationListener` instance to infer that each notification is processed only once. If downstream needs deduplication, design an appropriate identity key from source + sequence + emission lifecycle, or an application event ID, and check idempotency.

`handback` itself is often used for routing: the same listener can send notifications to a dashboard, audit logger, or different alerting pipelines. However, if handback is just the string `"critical"`, it is a client-defined routing context, not a server-verified severity.

## 9. Notifications and Other Monitoring Mechanisms

| Mechanism | How Data Is Received | Suitable For |
|---|---|---|
| JMX attribute | Client actively reads | Instantaneous state/measurements |
| JMX notification | Emitter actively pushes events | State changes, runtime alerts |
| Log | Application writes event records | Diagnostics and history via log pipelines |
| Metrics/alert | Collects, stores numbers, and evaluates conditions | Dashboards, trends, and alerts over time |
| Message broker | Durable publish/subscribe depending on configuration | Inter-service event integration, async processing |

JMX notifications are very useful for JVM/MBean management events, but **should not be assumed to be a durable event queue**. Remote connections can drop; listeners can disconnect; callbacks may fall behind. If the application requires replay, controlled retries, dead-letter queues, transactions, or delivery guarantees across multiple services, use a proper messaging mechanism instead of treating JMX Notification as a message broker.

Operators often combine notifications with re-reading attributes to verify current state. For example, a notification saying "queue exceeded 70" indicates the threshold was crossed at emission time; by the time the client processes it, `QueueDepth` may already have dropped.

## 10. Notes on Remote JMX

When the client is in another process, `MBeanServerConnection` is the remote operation interface. Listeners can be registered via:

```java
MBeanServerConnection connection = connector.getMBeanServerConnection();

connection.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
```

Here `connector` is a valid connected `JMXConnector`, and `objectName` points to a notification-capable MBean.

Some considerations:

1. **Remote JMX must be secured** with authentication, TLS where appropriate, network restrictions, and management permissions.
2. Connections or sessions can drop; clients need strategies to detect disconnects, reconnect, and re-register listeners as needed.
3. Do not expect notifications missed during a disconnect to replay automatically. If history is needed, store events or state elsewhere.
4. `userData` payloads crossing a connector must be compatible with the connector's transport/serialization mechanism and client-side types. Do not send large, mutable object graphs or secrets.
5. Notifications must be handled as data from a management channel that can fail, lag, or have restricted permissions; callbacks should not assume every event arrives completely and in order across sources.
6. `handback` provided by the registrant is callback context, not a solution for sending secrets or business parameters from client to server.

A system needing critical alerts can use JMX Notification as an input signal and forward it to an alert pipeline with tracking and deduplication. Do not let the success of a callback be the sole proof that an incident was handled.

## 11. How Does Spring Framework Integrate?

In Spring, MBeans still follow Java's JMX principles: a NotificationEmitter source, MBeanServer, listeners, and registrations. Spring Framework provides helper classes for exporting MBeans and registering listeners, helping manage lifecycles via the container.

An application can:

- Export a bean that implements an MBean interface and notification-emitting capability.
- Use `MBeanExporter` to register the bean into `MBeanServer`.
- Configure listeners via `NotificationListenerBean` or listener mapping configuration appropriate for the Spring Framework version in use.

Conceptual registration example in a Spring application:

```java
import javax.management.Notification;
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    if ("demo.queue.critical".equals(notification.getType())) {
        System.out.println("Critical queue notification: " +
            notification.getMessage());
    }
};
```

This code is only the **listener**; it does not register itself with an MBean. The application must bind the listener to a notification-capable MBean via MBeanServer/Spring exporter or corresponding configuration. When using custom filters and handbacks, ensure the final configuration passes the right parameters at registration time and unregisters when the context stops.

**Do not confuse Spring ApplicationEvent with JMX Notification:** ApplicationEvent is a publish/subscribe mechanism inside the Spring application context; JMX Notification is an event on the JMX management surface observable by JMX clients. To convert between the two, explicit bridging code is required.

In Spring Boot applications, JMX export configuration may depend on `spring.jmx.enabled` and auto-configuration. A bean's presence in ApplicationContext does not guarantee JMX clients can see that bean's notifications.

## 12. Common Pitfalls

### 12.1. Created Notification but listener never runs

Check whether the source actually calls `sendNotification(...)`, whether the MBean is registered under the right ObjectName, whether the listener is registered on the right source, and whether the filter permits that type. Overriding `getNotificationInfo()` to declare metadata alone does not send events.

### 12.2. Using NotificationFilterSupport like a regex

```java
filter.enableType("demo.queue.*");
```

The statement above looks for the **literal prefix** `demo.queue.*`, which has no wildcard meaning. To receive all types starting with `demo.queue.`, use:

```java
filter.enableType("demo.queue.");
```

### 12.3. Confusing userData with handback

`userData` is part of the notification set by the broadcaster. `handback` is context provided by the subscriber at registration time. If two listeners have different handbacks, the same notification still carries the same userData while each callback receives its own handback.

### 12.4. Same listener receives twice

When a listener is registered twice or registered with two filters that both match, one notification can trigger multiple callbacks. Check subscription lists and routing logic before concluding the broadcaster emitted twice.

### 12.5. removeNotificationListener fails to remove

Check ObjectName, listener instance, and filter/handback pair. In particular, when using the overload that removes a specific registration, reuse the saved references. A new lambda with identical logic is still a different listener/filter object.

### 12.6. Callback slows down the entire system

If a listener performs blocking work on a synchronous dispatch mechanism, the emitting thread can be delayed. Move heavy work to a bounded executor or queue, monitor backlog, and define overload policies. When using an asynchronous executor, handle errors, ordering, and shutdown carefully.

### 12.7. Treating notifications as a complete historical log

JMX does not automatically store every notification and replay them after a client reconnects. For historical investigation, send events to a log/event store with suitable retention and querying.

## 13. Scenario-Based Practice

**Scenario A — receive only critical events.** An MBean emits three types:

```text
demo.queue.warning
demo.queue.critical
demo.queue.recovered
```

Task: create a `NotificationFilter` accepting only `demo.queue.critical` and pass handback `"oncall"`. In the listener, log `type`, `sequenceNumber`, `message` and `handback`. Try emitting all three types to observe the output.

**Scenario B — one listener handling multiple groups.** Register the same listener with two filters: one accepting `demo.queue.`, one accepting `demo.cache.`. Handbacks are `"queue-dashboard"` and `"cache-dashboard"`, respectively. Explain why handback should be an immutable context and how to remove each registration individually.

**Scenario C — reducing repeated notifications.** A queue's depth changes `65 -> 72 -> 80 -> 95 -> 85 -> 65` with warning threshold 70 and critical 90. Design rules to emit **on state transitions** `NORMAL/WARNING/CRITICAL`, add a recovery notification, and describe why this emits fewer notifications than emitting on every depth update.

**Scenario D — remote disconnection.** A client registers a listener and then disconnects for 30 seconds. During that time, the server emits three notifications. Explain why you cannot automatically assume the client will receive all three, and propose re-reading the attribute after reconnecting to synchronize current state.

**Scenario E — inspecting metadata.** Use `MBeanServer.getMBeanInfo(objectName).getNotifications()` to print the notification types the MBean declares it supports. Compare the type list with the filter the client registers; try creating a notification type not listed in metadata and discuss why metadata should accurately match the real contract.

## 14. Self-Check Questions

1. What two parameters does `NotificationListener.handleNotification` receive, and where do they come from?
2. Does `NotificationFilter.isNotificationEnabled(...)` decide filtering at the notification level or at the registration level?
3. What does passing `null` for the filter mean?
4. Does `NotificationFilterSupport.enableType` do prefix matching or full-string/regex matching?
5. Can a single notification invoke the same listener twice? When?
6. Why should handback not be treated as `userData`?
7. How do the two overloads of `removeNotificationListener` differ?
8. What happens if an MBean has `getNotificationInfo()` but never calls `sendNotification()`?
9. Do remote JMX Notifications guarantee replay after a disconnect?
10. How do JMX Notification and Spring `ApplicationEvent` differ in usage surface?

## 15. Core Takeaways

**Notification** is event information emitted by a JMX source. **NotificationListener** defines receiving and handling behavior, **NotificationFilter** determines which notification types a registration receives, and **handback** carries context assigned by the registrant and returned when the callback runs.

These three pieces form a clean push-event mechanism for JVM/MBean management. For reliable operation, name notification types stably, filter accurately, manage registration lifecycles, avoid blocking work in callbacks, secure remote connections, and use a dedicated event-storage system if durable delivery is required.
