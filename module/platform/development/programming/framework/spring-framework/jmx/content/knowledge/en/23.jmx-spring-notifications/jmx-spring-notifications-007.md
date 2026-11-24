# Emitting Notifications from Exported MBeans in Spring Framework JMX

## 1. Objectives

JMX (Java Management Extensions) not only allows management tools to read attributes or invoke operations on MBeans, but also supports **notifications**: event messages emitted by an MBean to registered listeners. In Spring Framework JMX, a Spring-managed bean exported via `MBeanExporter` can conveniently emit notifications through the `NotificationPublisherAware` interface.

For example, a worker pool can emit an event when a backlog threshold is reached, when transitioning to a degraded state, or when a refresh completes. Instead of forcing operators to poll state continuously, the application sends a notification when the event occurs.

**Core point:** the bean must be properly exported through Spring's JMX infrastructure, receive a `NotificationPublisher` during export, construct a `javax.management.Notification` with an explicit type/source/sequence/timestamp, and call `sendNotification`. Declaring notification metadata helps clients discover event types, but metadata **does not automatically create or emit events**.

## 2. What Is a Notification in JMX?

A JMX notification is an event emitted by a notification broadcaster to listeners registered with an MBeanServer or MBeanServerConnection.

```text
Spring-managed resource
      |
      | state change / management event
      v
JMX NotificationPublisher
      |
      v
Exported MBean (ObjectName)
      |
      v
MBeanServer
      |
      +--> NotificationListener A
      +--> NotificationListener B
      +--> JConsole / JMX client
```

A `Notification` contains basic information:

- `type`: event type identifier, e.g., `com.example.jobs.queue.threshold`.
- `source`: event source object, usually declared consistently with the source MBean.
- `sequenceNumber`: broadcaster event order, typically monotonically increasing.
- `timeStamp`: event creation time, in epoch milliseconds.
- `message`: short, human-readable description.
- `userData`: supplemental data, used only with a clear schema and never containing secrets.

Notifications are not Java exceptions, not HTTP callbacks, and do not guarantee durable storage. They primarily serve **event-driven** observation over an active JMX connection.

## 3. Distinguishing Attribute, Operation, and Notification

| Component | Role | Example |
| --- | --- | --- |
| JMX attribute | Current readable/writable state | `QueueDepth`, `Enabled`, `LastRefreshEpochMillis` |
| JMX operation | Action a client can request | `requestRefresh()` |
| JMX notification | Event proactively announced by the MBean | `queue.threshold`, `refresh.completed` |

Example of a system with 1,000 pending jobs:

- The client reads `QueueDepth` to know the **current state**.
- An operator calls `requestScaleUp()` to request an **action**.
- The MBean emits the `com.example.jobs.queue.threshold` notification when backlog crosses the threshold, notifying clients of the **threshold-crossing event**.

The three components complement each other. Notifications do not replace attributes because a listener can disconnect or register after an event has already occurred. A reliable monitoring system should both read the current snapshot and process notifications as useful signals.

## 4. What Components Does Spring Provide?

Spring JMX includes key APIs:

| Component | Responsibility |
| --- | --- |
| `MBeanExporter` | Exports Spring beans as MBeans, manages registration/lifecycle |
| `NotificationPublisherAware` | Callback for Spring to inject `NotificationPublisher` into an exported bean |
| `NotificationPublisher` | Spring API for sending JMX `Notification`s |
| `@ManagedResource` | Marks a managed resource and ObjectName metadata |
| `@ManagedNotification` | Describes a notification type and metadata for JMX clients |
| `@ManagedNotifications` | Declares multiple notification types on a resource |
| `@ManagedAttribute` | Exposes readable or writable state |
| `@ManagedOperation` | Exposes a management action |
| `NotificationListener` | Standard JMX interface receiving notifications from an MBean |
| `MBeanServerConnection.addNotificationListener` | Registers a listener via the JMX API |

Typically `NotificationPublisherAware` lives in `org.springframework.jmx.export.notification`; the `ManagedNotification`/`ManagedNotifications` annotations live in `org.springframework.jmx.export.annotation`.

## 5. Flow for Emitting Notifications from an Exported Bean

Basic workflow:

1. Spring instantiates the management bean and exports it via `MBeanExporter`.
2. The exporter creates/adapts the appropriate MBean and registers it under an `ObjectName`.
3. If the bean supports `NotificationPublisherAware`, Spring passes the publisher to the bean.
4. When the application detects an actual event, the bean creates a `Notification`.
5. The bean calls `publisher.sendNotification(notification)`.
6. The MBeanServer forwards the notification to registered listeners matching that ObjectName.

Do not confuse the step of **declaring notification types** with **emitting notifications**. `@ManagedNotification` helps describe the contract, but events are sent only when code calls the publisher.

## 6. Complete Example: WorkerPoolManagement Emitting Notifications

Suppose the application wants to emit an event when pending jobs reach a threshold. Create a management adapter:

```java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Main",
    description = "Monitor worker pool and emit operational events"
)
@ManagedNotifications({
    @ManagedNotification(
        name = "com.example.jobs.queue.threshold",
        description = "Pending job count exceeded warning threshold"
    ),
    @ManagedNotification(
        name = "com.example.jobs.refresh.completed",
        description = "Worker pool refresh completed"
    )
})
public class WorkerPoolManagement implements NotificationPublisherAware {
    private final WorkerPoolService service;
    private final AtomicLong sequence = new AtomicLong();
    private volatile NotificationPublisher publisher;

    public WorkerPoolManagement(WorkerPoolService service) {
        this.service = service;
    }

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute(description = "Number of pending jobs")
    public long getPendingJobs() {
        return service.pendingCount();
    }

    @ManagedOperation(description = "Request worker pool refresh")
    public void requestRefresh() {
        service.requestRefresh();
    }

    public void onQueueThresholdExceeded(long pending) {
        publish(
            "com.example.jobs.queue.threshold",
            "Queue backlog exceeded warning threshold",
            pending
        );
    }

    public void onRefreshCompleted() {
        publish(
            "com.example.jobs.refresh.completed",
            "Worker pool refresh completed",
            null
        );
    }

    private void publish(String type, String message, Object userData) {
        NotificationPublisher current = publisher;
        if (current == null) {
            // Export not yet complete: no JMX publisher.
            return;
        }

        Notification event = new Notification(
            type,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            message
        );
        if (userData != null) {
            event.setUserData(userData);
        }
        current.sendNotification(event);
    }
}
```

`WorkerPoolService` is an application service providing `pendingCount()` and `requestRefresh()`; the two callbacks `onQueueThresholdExceeded`/`onRefreshCompleted` must be invoked by business code or an event component at the right time. They are not automatically invoked by Spring JMX when metrics change.

**Source note:** the example uses `this` as the notification source when creating the event. In a real system, especially when using a ModelMBean/proxy, inspect the notification the client actually receives and align the source with the MBean contract. Clients typically use the ObjectName from listener registration to identify the sender rather than relying on serializing the entire implementation object.

## 7. Enabling Export for Annotated MBeans

With Spring Framework:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {
}
```

For a management bean to be exported by annotation, it must be placed in the `ApplicationContext` (e.g., via `@ComponentScan` or `@Bean`) and use appropriate export infrastructure. `@ManagedResource.objectName` identifies the MBean. The MBeanServer must see the registered MBean so JMX clients can connect.

If configuring `MBeanExporter` manually, ensure the assembler reads annotations and uses an appropriate naming strategy. Avoid using two exporters registering the same ObjectName, and avoid assuming a bean receives the publisher before it is exported.

## 8. Why Use NotificationPublisherAware?

A pure JMX implementation can extend `NotificationBroadcasterSupport`, manage listeners, and emit events itself. In a Spring-managed POJO exported via `MBeanExporter`, `NotificationPublisherAware` separates sending notifications from writing boilerplate broadcaster and MBean registration code.

```text
Application service -> management bean
                            |
               NotificationPublisherAware
                            |
                  NotificationPublisher
                            |
                     Spring JMX adapter
                            |
                        MBeanServer
```

Benefits:

- Services do not need to interact directly with MBeanServer or ObjectName to emit events.
- Spring supplies a publisher bound to the exported MBean.
- Event-emitting code can live in a management adapter with a distinct operational contract.
- Notification metadata can be declared via annotations.
- Registration/unregistration lifecycle is integrated with the exporter.

However, the publisher is not a message broker or event store. If you need delivery guarantees, replay, durable consumer offsets, or cross-service event streams, use proper messaging infrastructure rather than treating JMX notifications as a business queue.

## 9. Notification Types and Metadata

JMX clients can inspect `MBeanInfo.getNotifications()` to see the event types an MBean advertises.

Example:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = server.getMBeanInfo(objectName);
for (MBeanNotificationInfo notification : info.getNotifications()) {
    System.out.println(notification.getDescription());
    for (String type : notification.getNotifTypes()) {
        System.out.println("  type=" + type);
    }
}
```

Metadata should use types with a stable namespace:

```text
com.example.jobs.queue.threshold
com.example.jobs.refresh.completed
com.example.jobs.pool.degraded
```

Do not use generic types like `error`, `event`, or `state` in an application with multiple MBeans. A clear type helps listeners filter and interpret events.

**Declaring metadata does not replace emitting.** A notification type can appear in `MBeanInfo` without any event ever being sent. Conversely, events may be sent, yet if metadata does not reflect the exact type, management tools cannot easily discover the contract and operators get confused.

## 10. Registering a NotificationListener on the JMX Client Side

The standard JMX API allows listeners to register by ObjectName.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=WorkerPool,name=Main"
);

NotificationListener listener = (Notification event, Object handback) -> {
    System.out.printf(
        "type=%s sequence=%d message=%s%n",
        event.getType(),
        event.getSequenceNumber(),
        event.getMessage()
    );
};

server.addNotificationListener(name, listener, null, null);

try {
    // During this time the application may emit notifications.
    // For example, callback onQueueThresholdExceeded is invoked elsewhere.
} finally {
    server.removeNotificationListener(name, listener);
}
```

This is a local example assuming the MBean is already registered in the platform MBeanServer. If the Spring exporter uses a different server, the client must use that exact server. For remote JMX, clients use an `MBeanServerConnection` obtained via JMXConnector and need a secured connector configuration.

The listener must stay alive long enough to receive events; do not register and immediately remove it before the event is actually emitted. In long-running code, the lifecycle owner must hold the listener and unregister it on shutdown to avoid reference leaks.

## 11. Filtering Notifications by Type

JMX provides `NotificationFilterSupport` to block types that do not need processing:

```java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.jobs.queue.threshold");

server.addNotificationListener(name, listener, filter, null);
```

A filter helps a listener focus on a group of events, but it is not an authorization mechanism. If a client is granted permission to read notifications, the JMX connector's permission rules must still be enforced separately.

The `source`, `userData`, and `message` fields need a long-term compatible schema. Do not put secrets or raw business object graphs in notifications because clients may be remote and payloads may be logged.

## 12. Emitting Notifications When Actual Events Occur

The trigger point does not have to be a JMX operation. There are three common patterns:

1. **From a business event:** the worker pool detects a backlog threshold and calls the management publisher.
2. **From a management operation:** after `requestRefresh()` finishes, the system sends `refresh.completed`.
3. **From a health/state transition:** when a subsystem moves from UP to DEGRADED, the publisher sends a clearly typed notification.

You should not emit a new notification every time a JMX client calls a getter:

```java
@ManagedAttribute
public int getQueueDepth() {
    publishWarning(); // Anti-pattern: polling generates spurious events.
    return queue.depth();
}
```

Getters are polled frequently by monitoring; if a side effect emits notifications, the system can spam events and skew results. Instead, emit events when state actually crosses a threshold, optionally with debounce/hysteresis.

Example emitting only on transition from below threshold to above threshold:

```java
private final AtomicBoolean aboveThreshold = new AtomicBoolean();

public void onQueueDepthChanged(long depth) {
    boolean nowAbove = depth >= 500;
    boolean wasAbove = aboveThreshold.getAndSet(nowAbove);
    if (nowAbove && !wasAbove) {
        onQueueThresholdExceeded(depth);
    }
}
```

The example needs to import `java.util.concurrent.atomic.AtomicBoolean`. This approach does not handle every distributed state/hysteresis case, but illustrates avoiding useless repeated notices. Production systems may need cooldowns, sustained-state confirmation, or threshold calculation per business rules.

## 13. Sequence Numbers and Concurrency

Usually each broadcaster maintains an incrementing sequence number:

```java
private final AtomicLong sequence = new AtomicLong();

long sequenceNumber = sequence.incrementAndGet();
```

`AtomicLong` prevents two threads emitting events from getting the same sequence number. However, sequence numbers do not guarantee every listener will receive all events. When a remote connector disconnects, notifications can be lost; a sequence gap is a useful signal, not a replacement for a durable event log.

A Spring application may emit notifications from multiple threads, so consider:

- Thread-safety of the state triggering events.
- Avoiding calling listeners or the notification publisher while holding critical locks.
- Avoiding large payloads or blocking work on the event emission path.
- Rate-limiting or coalescing events if emitted very frequently.
- Not inferring global ordering across multiple broadcasters or multiple JVMs.

Sequence numbers should be treated as the relative order of events created by **a single emitter**, not a system-wide global sequence.

## 14. Event Payload: What Should userData Contain?

`Notification.setUserData(Object)` can attach supplemental data. However, remote JMX may need to serialize data over a Java connector, so avoid attaching complex domain objects or sensitive information.

Simple example:

```java
Notification notification = new Notification(
    "com.example.jobs.queue.threshold",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Queue warning threshold exceeded"
);
notification.setUserData(Long.valueOf(750));
publisher.sendNotification(notification);
```

For multi-field payloads, you can use JMX Open Types such as `CompositeData` or simple structures with a clearly documented schema. Avoid depending on application-specific classes on remote clients without a versioned contract.

Never send JWTs, passwords, session tokens, PII, or stack traces containing sensitive data in message/userData. Notifications can be logged, displayed in tools, or delivered to multiple listeners with varying privilege levels.

## 15. Publisher Lifecycle

`NotificationPublisherAware.setNotificationPublisher` is called when Spring sets up the appropriate export pipeline. Before that point, the reference to the publisher may be null.

Therefore, event-emitting code should understand clearly:

- When a bean is created but not yet exported, are notifications dropped or buffered?
- If the MBean has been unregistered, what does continuing to emit events mean?
- If the bean is re-exported, is the publisher replaced properly?
- Who owns cleanup when the context closes?

The example used `volatile NotificationPublisher` and a null check to avoid dereferencing before export. This is a simple **drop notifications while no publisher is present** policy. If the application requires zero event loss, an independent event store or broker is needed rather than relying on the JMX publisher.

Do not store the publisher in static global state and emit after the ApplicationContext has closed. That makes object lifecycles hard to control and can retain references to old MBeanServers/beans.

## 16. Notification Listeners in Spring

In addition to the direct JMX API, `MBeanExporter` supports configuring notification listeners to attach listeners to exported MBeans. This configuration can be convenient when the listener is also a Spring-managed bean.

Concept:

```text
Spring MBeanExporter
   |
   +-- exported MBean
   |
   +-- configured NotificationListener
           |
           +-- handle selected notification types
```

In a real project, use a listener mapping configuration compatible with your Spring Framework version and ObjectNames. If a listener must receive notifications from MBeans registered elsewhere or over a remote connector, using `MBeanServerConnection.addNotificationListener` with the appropriate server can be clearer.

Do not confuse Spring's `ApplicationEventPublisher` with JMX's `NotificationPublisher`. Spring application events run in the ApplicationContext's internal event mechanism; JMX notifications pass through MBean broadcasters to JMX listeners. You can bridge internal events to JMX notifications via a management adapter, but the two systems are not automatically linked merely because both names contain "publisher."

## 17. Notifications Are Signals, Not the Sole Source of Truth

A listener can:

- Connect after an event has already been emitted.
- Disconnect mid-stream due to redeploy, network issues, or connector restarts.
- Miss events due to slow client processing or failures.
- Receive duplicate events in scenarios where a forwarding system has its own retries.

Therefore, notifications should signal when to re-check state—for example, receiving `queue.threshold` and then reading `QueueDepth`—rather than serving as the sole source of truth.

```text
Notification received
        |
        v
Client reads current attribute
        |
        v
Decide whether action is still needed
```

This pattern also avoids false reactions if the state has already self-recovered before the listener processes it.

## 18. Security of Notifications

JMX notifications are not a confidential channel by default. In an application with remote JMX enabled:

- Protect the connector with network policy, authentication, TLS, and authorization.
- Restrict the MBeans and notification types clients may access per server security policies.
- Do not send secrets in type, message, source, or userData.
- Do not place dangerous operations near notification listeners without authorization checks.
- Be careful when reporting errors because exception messages/stack traces can contain sensitive information.

`@ManagedNotification` metadata only describes the contract; it does not authenticate clients, encrypt payloads, or enforce ACLs.

## 19. Handling Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `setNotificationPublisher` is not called | Bean not exported yet or export path does not support publisher | Check MBeanExporter, bean instance, and JMX config |
| Metadata present but no notifications received | `sendNotification` not called or listener not registered | Check event path and listener lifecycle |
| Listener registered but no events seen | Wrong ObjectName/MBeanServer, filter excluded event | Verify matching server, name, and notification type |
| Local listener works, remote does not receive | Connector/authorization/network error | Check JMX service URL, permissions, and TLS |
| Notification repeated many times | Code emits from getter/polling or lacks debounce | Emit on state transition and rate-limit |
| `userData` fails deserialization on client | Payload uses internal or non-serializable class | Use simple types/Open Types |
| Sequence numbers are non-contiguous | Missed events or source changed | Use events as signals and read current state |
| MBean closed yet still tries to emit | Publisher reference outlives MBean lifecycle | Manage shutdown/callbacks and avoid static state |
| JConsole does not list notification types | Metadata annotation or assembler misconfigured | Check `MBeanInfo.getNotifications()` |

## 20. Designing a Good Notification Contract

A notification contract should specify:

1. **Type** with a stable namespace: `com.example.jobs.queue.threshold`.
2. **Source** MBean: a concrete ObjectName, unambiguous across application instances.
3. **Emission condition**: threshold crossing, task completion, or state transition.
4. **Repetition semantics**: can it emit multiple times, is there a cooldown?
5. **Sequence**: increments per broadcaster and whether it resets on a new lifecycle.
6. **Timestamp**: epoch millis when the event was emitted.
7. **Payload**: small, safe schema containing no secrets.
8. **Reliability**: best-effort; clients must read attributes to confirm state.
9. **Security**: which clients are permitted to subscribe and receive contents.
10. **Compatibility**: do not change types/fields unexpectedly if dashboards/automation consume them.

## 21. Summary

```text
Exported Spring bean
      |
      +-- @ManagedResource
      +-- @ManagedNotifications (metadata)
      +-- NotificationPublisherAware
                 |
          publisher injected
                 |
          application event
                 |
          Notification object
                 |
          sendNotification
                 |
              MBeanServer
                 |
        JMX NotificationListeners
```

**Key takeaway:** to emit notifications from an exported MBean in Spring Framework, a bean typically implements `NotificationPublisherAware`, receives the `NotificationPublisher` provided by the exporter, and calls `sendNotification` when an actual event occurs. `@ManagedNotification`/`@ManagedNotifications` describe event types but do not send events automatically. Manage sequence numbers, payloads, listener lifecycles, ObjectNames, and security; use notifications as complementary signals alongside current attributes, not as a durable queue.
