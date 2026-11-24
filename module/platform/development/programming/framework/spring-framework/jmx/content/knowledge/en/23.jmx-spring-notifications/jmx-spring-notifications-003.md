# Registering a Listener for Multiple MBeans in Spring Framework JMX

## 1. Context and Objectives

JMX (Java Management Extensions) not only lets you read **attributes** and invoke **operations** on MBeans, but also supports the **notification** model: an MBean can emit events so clients or other components know when state has just changed.

In Spring Framework JMX, an application often has multiple MBeans emitting notifications:

- A cache management MBean emits a notification when data is refreshed.
- A worker management MBean emits a notification when a worker is paused/resumed.
- A queue management MBean emits a notification when the pending job count exceeds a threshold.
- A connection-observing MBean emits a notification when a downstream service loses connectivity or recovers.

If each event needs to be handled by a unified rule, we need to **register a listener for multiple MBeans**. Spring supports configuring listeners through `MBeanExporter` and related components, alongside the standard JMX notification API.

After this lesson, you will be able to:

1. Understand `NotificationEmitter`, `NotificationListener`, `NotificationFilter`, and `ObjectName`.
2. Distinguish between listeners registered directly on an MBeanServer and listeners managed by a Spring exporter.
3. Configure a single listener to receive events from multiple MBeans in a controlled way.
4. Restrict notifications with filters and handle event data safely.
5. Handle registration, unregistration, and MBean replacement in the application lifecycle.
6. Test multiple emitters without mixing up metadata, listeners, or operations.

## 2. Core Concepts of JMX Notifications

JMX uses the following primary components:

| Component | Role |
| --- | --- |
| `Notification` | Object representing an event: type, source, sequence number, timestamp, message, userData. |
| `NotificationBroadcaster` | Interface indicating that an MBean can emit notifications. |
| `NotificationEmitter` | Extends broadcaster, supporting listener/filter/handback management. |
| `NotificationListener` | Component receiving notifications via `handleNotification`. |
| `NotificationFilter` | Decides which notifications are forwarded to the listener. |
| `ObjectName` | Identifier of an MBean registered in the MBeanServer. |
| `MBeanServer` | Supports `addNotificationListener`/`removeNotificationListener` on registered MBeans. |

Simple flow:

~~~text
MBean A --notification--+
                        |
MBean B --notification--+--> NotificationListener
                        |
MBean C --notification--+
~~~

In JMX, one listener can be registered on multiple MBeans. Each registration is still a separate relationship between the listener and an emitter; there is no concept of "a single subscription automatically covering every MBean" without performing complete registrations.

### Notifications Are Not a Durable Message Queue

Notifications are typically runtime-scoped. If a listener is not registered yet, the application loses connectivity, or an MBean is replaced, the client may miss notifications that were already emitted. JMX does not inherently support durable storage, replay, or exactly-once delivery.

If losing events is unacceptable, use an appropriate event/messaging system at the application layer rather than treating JMX notifications as a reliable business integration mechanism.

## 3. Example of Two MBeans Emitting Notifications

We will build two independent emitters for illustration: `CacheMonitor` and `QueueMonitor`. They use `NotificationBroadcasterSupport`, a standard JMX class that helps manage listeners and emit notifications.

### 3.1. Management Interfaces

~~~java
package com.example.management;

public interface CacheMonitorMBean {
    long getRefreshCount();
    void refresh();
}
~~~

~~~java
package com.example.management;

public interface QueueMonitorMBean {
    int getPendingCount();
    void signalThreshold();
}
~~~

### 3.2. CacheMonitor Emitting Events

~~~java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class CacheMonitor extends NotificationBroadcasterSupport
        implements CacheMonitorMBean {

    private final AtomicLong sequence = new AtomicLong();
    private final AtomicLong refreshCount = new AtomicLong();

    @Override
    public long getRefreshCount() {
        return refreshCount.get();
    }

    @Override
    public void refresh() {
        long count = refreshCount.incrementAndGet();

        Notification notification = new Notification(
            "com.example.cache.refreshed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Cache refreshed, count=" + count
        );

        sendNotification(notification);
    }
}
~~~

### 3.3. QueueMonitor Emitting Events

~~~java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    private final AtomicLong sequence = new AtomicLong();
    private volatile int pendingCount = 10;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void signalThreshold() {
        Notification notification = new Notification(
            "com.example.queue.threshold",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Pending queue size=" + pendingCount
        );

        sendNotification(notification);
    }
}
~~~

Each MBean has its own sequence counter. **The sequence number is not a global identifier** across multiple emitters. When aggregating notifications from multiple MBeans, do not assume their sequences increase continuously system-wide.

Both examples use a synchronous operation to actively emit a notification. In a real system, notifications can be emitted from cache or queue management logic when a condition occurs.

## 4. Registering MBeans in the MBeanServer

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName cacheName = new ObjectName(
    "com.example:type=CacheMonitor,name=products"
);
ObjectName queueName = new ObjectName(
    "com.example:type=QueueMonitor,name=payments"
);

server.registerMBean(new CacheMonitor(), cacheName);
server.registerMBean(new QueueMonitor(), queueName);
~~~

The MBeanServer requires ObjectNames to be unique within one server. For two different emitters, use two distinct and consistent ObjectNames so the listener can track the right resource.

This snippet runs in the same JVM. If you create a separate JVM to execute this code, it will not automatically register MBeans into the JVM of another Spring application.

## 5. How to Register One Listener for Multiple MBeans via the JMX API

First, create the listener:

~~~java
import javax.management.Notification;
import javax.management.NotificationListener;

NotificationListener listener = (Notification notification,
                                 Object handback) -> {
    System.out.println(
        "type=" + notification.getType()
        + ", source=" + notification.getSource()
        + ", sequence=" + notification.getSequenceNumber()
        + ", message=" + notification.getMessage()
        + ", handback=" + handback
    );
};
~~~

Then call `addNotificationListener` separately for each ObjectName:

~~~java
server.addNotificationListener(
    cacheName,
    listener,
    null,
    "cache"
);

server.addNotificationListener(
    queueName,
    listener,
    null,
    "queue"
);
~~~

The same listener is reused, but there are **two independent registrations**. The `handback` parameter is context provided by the caller at registration time; in this example it helps distinguish the source.

When an MBean emits an event, the listener is invoked with the corresponding notification and handback. You can use handback as an object containing the ObjectName, a logical resource ID, or subscription metadata.

### Unregistering Accurately

When you no longer need to receive notifications:

~~~java
server.removeNotificationListener(
    cacheName,
    listener
);

server.removeNotificationListener(
    queueName,
    listener
);
~~~

An application must manage the lifecycle of every registration it creates. Forgetting to remove a listener can cause memory leaks or keep processing events that are no longer relevant.

**Note:** The JMX API has an overload of `removeNotificationListener` taking filter and handback. When multiple registrations have been created for the same listener on one emitter, using the appropriate overload is crucial to avoid removing the wrong subscription or failing to find the matching registration.

## 6. Using NotificationFilter to Receive Only Needed Events

When a listener is shared across multiple MBeans, filters help avoid processing unrelated events.

Example:

~~~java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter filter = new NotificationFilter() {
    private static final long serialVersionUID = 1L;

    @Override
    public boolean isNotificationEnabled(Notification notification) {
        String type = notification.getType();

        return "com.example.cache.refreshed".equals(type)
            || "com.example.queue.threshold".equals(type);
    }
};
~~~

Registration:

~~~java
server.addNotificationListener(
    cacheName,
    listener,
    filter,
    cacheName
);

server.addNotificationListener(
    queueName,
    listener,
    filter,
    queueName
);
~~~

One listener can be registered with **different filters per emitter**. If the cache emits multiple notification types but the subscriber only needs `cache.refreshed`, use a dedicated filter.

### Filtering by Notification Type

Another approach is `NotificationFilterSupport`:

~~~java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport cacheFilter =
    new NotificationFilterSupport();
cacheFilter.enableType("com.example.cache.refreshed");

NotificationFilterSupport queueFilter =
    new NotificationFilterSupport();
queueFilter.enableType("com.example.queue.threshold");
~~~

Then use:

~~~java
server.addNotificationListener(
    cacheName, listener, cacheFilter, cacheName
);

server.addNotificationListener(
    queueName, listener, queueFilter, queueName
);
~~~

**Warning:** `NotificationFilterSupport.enableType` relies on prefix matching of the notification type. If you need an exact match for a single type, write a filter using `equals` as in the previous example.

## 7. Listener Mechanism in Spring MBeanExporter

Spring Framework JMX provides a way to configure listeners on the exporter via `NotificationListenerBean`.

Benefits:

- The listener is managed by Spring as a bean.
- Shared listeners can be declared.
- You can select which exporter-managed MBeans to receive events from.
- Registration/unregistration can be tied to the exporter's lifecycle.
- No need to manually write all `addNotificationListener` code for MBeans within the exporter's scope.

Configuration concept:

~~~text
MBeanExporter
    |
    +-- Beans to export:
    |     CacheMonitor
    |     QueueMonitor
    |
    +-- NotificationListeners:
          SharedEventListener
                |
                +-- CacheMonitor ObjectName
                +-- QueueMonitor ObjectName
~~~

**Important:** The `NotificationListenerBean` mechanism in the exporter applies to the MBeans that the exporter manages according to its configuration. Do not assume that declaring a listener in an exporter automatically registers it with every existing MBean in the platform MBeanServer, including JVM MBeans and MBeans managed by another exporter.

## 8. Creating a Spring Listener That Can Receive Multiple Sources

A simple listener:

~~~java
package com.example.management;

import javax.management.Notification;
import javax.management.NotificationListener;

public class SharedManagementListener
        implements NotificationListener {

    @Override
    public void handleNotification(
            Notification notification,
            Object handback
    ) {
        System.out.printf(
            "type=%s, source=%s, message=%s%n",
            notification.getType(),
            notification.getSource(),
            notification.getMessage()
        );
    }
}
~~~

In production, avoid logging the entire `notification.getUserData()` directly if the data could contain secrets or sensitive information. Listeners should also process quickly and avoid prolonged network/database blocking inside callbacks.

## 9. Configuring NotificationListenerBean for Multiple MBeans

A Java configuration example:

~~~java
package com.example.management;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class MultiMBeanNotificationConfiguration {

    @Bean
    CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    SharedManagementListener sharedManagementListener() {
        return new SharedManagementListener();
    }

    @Bean
    NotificationListenerBean notificationListenerBean(
            SharedManagementListener listener
    ) {
        NotificationListenerBean bean =
            new NotificationListenerBean(listener);

        bean.setMappedObjectNames(
            "com.example:type=CacheMonitor,name=products",
            "com.example:type=QueueMonitor,name=payments"
        );
        return bean;
    }

    @Bean
    MBeanExporter managementExporter(
            CacheMonitor cacheMonitor,
            QueueMonitor queueMonitor,
            NotificationListenerBean listenerBean
    ) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "com.example:type=CacheMonitor,name=products",
            cacheMonitor,
            "com.example:type=QueueMonitor,name=payments",
            queueMonitor
        ));

        exporter.setNotificationListeners(listenerBean);

        return exporter;
    }
}
~~~

In this configuration:

1. Spring creates two MBean source beans.
2. The exporter registers both emitters with separate ObjectNames.
3. `NotificationListenerBean` receives the listener implementation.
4. `setMappedObjectNames` restricts the sources from which notifications are received.
5. `setNotificationListeners` supplies the listener configuration to the exporter.
6. The same listener can receive events from both the cache and the queue.

**Important note on API versions:** Overload names, the type of `mappedObjectNames`, and how `NotificationListenerBean` is declared may differ across Spring versions; when copying, cross-check the Javadoc of the version in use. If `setMappedObjectNames` requires `ObjectName` instead of String in your version, create them with `new ObjectName(...)` or use the matching setter variant.

When an MBean is already managed by another Spring Boot/JMX exporter, do not configure an additional exporter just to receive notifications if doing so creates duplicate name registrations. In that case, consider registering directly on the `MBeanServer` or adjusting ownership.

## 10. XML Configuration Example

In Spring XML applications, you can declare the listener and mapping similarly:

~~~xml
<bean id="sharedManagementListener"
      class="com.example.management.SharedManagementListener"/>

<bean id="notificationListener"
      class="org.springframework.jmx.export.NotificationListenerBean">
    <constructor-arg ref="sharedManagementListener"/>
    <property name="mappedObjectNames">
        <list>
            <value>com.example:type=CacheMonitor,name=products</value>
            <value>com.example:type=QueueMonitor,name=payments</value>
        </list>
    </property>
</bean>

<bean id="mbeanExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example:type=CacheMonitor,name=products"
                   value-ref="cacheMonitor"/>
            <entry key="com.example:type=QueueMonitor,name=payments"
                   value-ref="queueMonitor"/>
        </map>
    </property>
    <property name="notificationListeners">
        <list>
            <ref bean="notificationListener"/>
        </list>
    </property>
</bean>
~~~

The `cacheMonitor` and `queueMonitor` beans must be defined elsewhere in the context. This configuration illustrates the relationship between emitters, listener, and exporter; verify the schema and actual Spring version before use.

## 11. Mapped ObjectNames: Registering the Right Sources

A common mistake is configuring a listener where the ObjectName mapping does not match the exported MBean.

Example:

~~~text
Exported:
  com.example:type=CacheMonitor,name=products

Configured listener:
  com.example:type=CacheMonitor,name=product
~~~

Differing by just one character (`products`/`product`), these are two different ObjectNames. The listener may not get attached to the intended source.

How to verify:

~~~java
ObjectName name = new ObjectName(
    "com.example:type=CacheMonitor,name=products"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "Expected MBean is not registered"
    );
}
~~~

Use `ObjectName.equals` or canonical names when comparing names; key property order does not determine identity.

### When There Are Multiple Instances of the Same Type

~~~text
com.example:type=QueueMonitor,name=payments
com.example:type=QueueMonitor,name=shipping
com.example:type=QueueMonitor,name=notifications
~~~

You can attach the listener to all three using explicit mappings. For dynamically created sources, design a discovery and lifecycle registration mechanism; do not assume a wildcard pattern in listener configuration is always treated by Spring as "subscribe to every current and future MBean."

## 12. Can You Register a Listener with JVM/Framework-Created MBeans?

Yes, if that MBean is a notification broadcaster and the client has permission to register.

For example, several JVM-provided MBeans support specific notifications such as certain Memory/GC MXBeans; however, not every MBean under `java.lang` emits notifications.

In code, use `MBeanServerConnection.addNotificationListener` with a confirmed and authorized ObjectName:

~~~java
connection.addNotificationListener(
    targetName,
    listener,
    filter,
    targetName
);
~~~

Conditions:

- `targetName` is registered in the MBeanServer.
- The target supports notification broadcasting.
- The caller is permitted to register a listener.
- The connection channel and listener type fit the local/remote mechanism.

**Do not confuse** a listener managed by a Spring exporter with a subscription on an arbitrary MBeanServer. If the target does not belong to the exporter in use, registering directly via `MBeanServerConnection` is usually clearer.

## 13. Listener for Multiple MBeans Over a JMX Remote Connector

For remote JMX, a client can use `MBeanServerConnection`:

~~~java
import javax.management.MBeanServerConnection;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

NotificationListener listener = (notification, handback) -> {
    System.out.println(notification.getType());
};

ObjectName cacheName = new ObjectName(
    "com.example:type=CacheMonitor,name=products"
);

ObjectName queueName = new ObjectName(
    "com.example:type=QueueMonitor,name=payments"
);

connection.addNotificationListener(
    cacheName, listener, null, cacheName
);

connection.addNotificationListener(
    queueName, listener, null, queueName
);
~~~

`connection` is an `MBeanServerConnection` obtained from `JMXConnector`. If the remote connection is closed or lost, subscriptions may no longer remain valid; the client must design reconnection and re-subscription.

### Why Store Subscription Mappings?

A client managing multiple MBeans should maintain a list of:

~~~text
[ObjectName, NotificationListener, NotificationFilter, handback]
~~~

This list is used to:

1. Re-register automatically after reconnection.
2. Remove the exact registration on shutdown.
3. Log the event source by ObjectName.
4. Handle MBeans that are replaced or no longer exist.
5. Avoid unintended duplicate registrations.

Do not rely solely on `Notification.getSource()` and assume that value is always the ObjectName. Source is set by the emitter; depending on the server/connector, the client may see a converted source, so use handback and subscription mappings when reliable identification is needed.

## 14. Registering Multiple MBeans in a Loop

When you have a fixed list of ObjectNames, you can use:

~~~java
import java.util.List;
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public final class MultiMBeanSubscriber {
    private final MBeanServerConnection connection;
    private final NotificationListener listener;

    public MultiMBeanSubscriber(
            MBeanServerConnection connection,
            NotificationListener listener
    ) {
        this.connection = connection;
        this.listener = listener;
    }

    public void subscribe(List<ObjectName> names)
            throws Exception {
        for (ObjectName name : names) {
            connection.addNotificationListener(
                name,
                listener,
                null,
                name
            );
        }
    }

    public void unsubscribe(List<ObjectName> names)
            throws Exception {
        for (ObjectName name : names) {
            connection.removeNotificationListener(name, listener);
        }
    }
}
~~~

This pattern is simple, but partial failures need consideration: if registering on the first MBean succeeds and the second fails, the listener may still remain registered on the first MBean.

In a real system, record each successful subscription, and when a step fails, clean up the created registrations or report the partial registration state clearly. Do not treat a loop of multiple registrations as an atomic transaction.

## 15. Partial Registration and Error Cleanup

A safer implementation:

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public final class SafeMultiSubscriber {
    private final MBeanServerConnection connection;
    private final NotificationListener listener;

    public SafeMultiSubscriber(
            MBeanServerConnection connection,
            NotificationListener listener
    ) {
        this.connection = connection;
        this.listener = listener;
    }

    public List<ObjectName> subscribeAll(List<ObjectName> names)
            throws Exception {

        List<ObjectName> registered = new ArrayList<>();

        try {
            for (ObjectName name : names) {
                connection.addNotificationListener(
                    name, listener, null, name
                );
                registered.add(name);
            }
            return registered;
        } catch (Exception error) {
            for (ObjectName name : registered) {
                try {
                    connection.removeNotificationListener(name, listener);
                } catch (Exception cleanupError) {
                    error.addSuppressed(cleanupError);
                }
            }
            throw error;
        }
    }
}
~~~

This pattern attempts to clean up on failure. In remote JMX, cases can still occur where the registration outcome is uncertain if the connection drops after the server processes it; for high reliability, track lifecycle and reconcile subscriptions on reconnect.

## 16. Dynamic MBeans: Registering Listeners for Sources Appearing Later

MBeans can be registered and unregistered following the Spring lifecycle or dynamic resources.

If you want a listener to receive events from MBeans added after the subscriber starts, you must design a registry-watching mechanism instead of querying only once.

JMX has a delegate MBean:

~~~text
JMImplementation:type=MBeanServerDelegate
~~~

This MBean emits `MBeanServerNotification` when an MBean is registered or unregistered.

A pattern:

~~~text
Client
  |
  +-- Subscribe to MBeanServerDelegate
  |
  +-- Query existing MBeans
  |
  +-- Subscribe to matching emitters
  |
  +-- On registration:
  |     +-- Check ObjectName
  |     +-- Subscribe new emitter
  |
  +-- On unregistration:
        +-- Remove subscription tracking
~~~

When using the delegate and querying, guard against race conditions between the two steps. For example, subscribe to the delegate first, then query existing names and use an idempotent set of subscriptions to avoid adding duplicate listeners if an MBean appears concurrently with the query.

### Example Registering a Delegate Listener

~~~java
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName delegate = new ObjectName(
    "JMImplementation:type=MBeanServerDelegate"
);

NotificationListener registryListener = (notification, handback) -> {
    if (notification instanceof MBeanServerNotification event) {
        System.out.println(
            "Registry event: " + notification.getType()
            + " -> " + event.getMBeanName()
        );
    }
};

connection.addNotificationListener(
    delegate,
    registryListener,
    null,
    null
);
~~~

This example uses modern Java pattern matching for `instanceof`; for older Java versions, use a traditional cast.

**Limitation:** Delegate events are not a durable event history. A disconnected client may miss registration events; after reconnecting, re-query the registry and synchronize subscriptions.

## 17. Distinguishing One Shared Listener from Multiple Dedicated Listeners

### One Shared Listener

~~~text
Cache A --+
Cache B --+--> SharedListener
Queue C --+
~~~

Pros:

- Unified logging and notification handling.
- Easy to aggregate event metrics and policies.
- Fewer listener classes.
- Can use filter/handback to distinguish sources.

Cons:

- Logic easily bloats when many different types exist.
- A slow listener can affect emitters.
- Requires careful routing and concurrency control.

### Dedicated Listeners

~~~text
Cache A --> CacheListener
Cache B --> CacheListener
Queue C --> QueueListener
~~~

Pros:

- Separated responsibilities, easy to test per event type.
- Easy to restrict dependencies and handling permissions.
- Less confusion across different notification schemas.

Cons:

- More configuration/registrations.
- May duplicate audit, logging, or error-handling logic.

A hybrid approach is a single shared listener whose sole responsibility is **fast routing** to dedicated handlers by notification type and resource identity.

## 18. Designing Handlers That Do Not Slow Down Emitters

A notification listener may be invoked on the emitter's thread or on an executor depending on the implementation. Do not assume the listener always runs on a separate background thread.

Avoid:

~~~java
@Override
public void handleNotification(
        Notification notification, Object handback
) {
    externalApi.callSlowly(notification);
    database.runLongTransaction(notification);
}
~~~

If the emitter dispatches synchronously, this handler can slow down management operations or the business thread emitting the event.

A more reasonable approach:

1. Validate notification data quickly.
2. Hand off events needing processing to an executor or bounded queue.
3. Run slow logic on a separate worker.
4. Bound the number of queued pending events.
5. Define a policy when the queue is full: drop, coalesce, backpressure, or offload to another event system.
6. Avoid creating unbounded threads or queues per notification.

### Example Listener Offloading Events to an Executor

~~~java
import java.util.concurrent.ExecutorService;
import javax.management.Notification;
import javax.management.NotificationListener;

public class AsyncNotificationListener
        implements NotificationListener {

    private final ExecutorService executor;

    public AsyncNotificationListener(ExecutorService executor) {
        this.executor = executor;
    }

    @Override
    public void handleNotification(
            Notification notification,
            Object handback
    ) {
        executor.execute(() -> process(notification, handback));
    }

    private void process(Notification notification, Object handback) {
        System.out.println(notification.getType());
    }
}
~~~

This pattern only illustrates asynchronous dispatch. Production code needs to handle `RejectedExecutionException`, shutdown lifecycle, queue capacity, and `userData` that may not be thread-safe if mutable objects are shared across threads.

## 19. Notification Data and the Meaning of Source

A notification typically has:

~~~text
type
source
sequenceNumber
timeStamp
message
userData
~~~

When a listener receives from multiple sources, do not use `sequenceNumber` alone to determine global ordering. Emitters can have separate sequence counters, different clocks, or notifications may be processed asynchronously.

Suggested key for logging:

~~~text
target JVM / ObjectName / notification type / sequence number / timestamp
~~~

If the listener uses `handback` to carry the ObjectName, the output is easier to analyze:

~~~java
ObjectName sourceName = (ObjectName) handback;
System.out.println(
    "MBean=" + sourceName.getCanonicalName()
    + ", type=" + notification.getType()
);
~~~

Only cast like this when the registration code itself guarantees handback is an `ObjectName`. If a Spring exporter attaches handback according to another configuration, check the actual callback contract.

## 20. Notification Metadata and @ManagedNotification

In Spring JMX, `@ManagedNotification` describes the notification types an MBean can emit. Example:

~~~java
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example:type=Cache,name=products"
)
@ManagedNotification(
    name = "com.example.cache.refreshed",
    description = "Emitted after a cache refresh"
)
public class CacheManagement {
    // Implementation.
}
~~~

**Metadata differs from runtime events.** Merely declaring `@ManagedNotification` does not make events emit automatically. The bean must actually emit notifications via an appropriate JMX/Spring mechanism.

With Spring, you can use the framework's notification publishing support instead of implementing `NotificationBroadcasterSupport` manually in every case. When using annotations and a publisher, keep the `notification type` in metadata consistent with the actual event type.

If you want to verify which event types an MBean supports:

~~~java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = connection.getMBeanInfo(targetName);

for (MBeanNotificationInfo notificationInfo :
        info.getNotifications()) {
    for (String type : notificationInfo.getNotifTypes()) {
        System.out.println(type);
    }
}
~~~

MBeanInfo shows declared capabilities; it does not prove a listener is registered or that events are guaranteed to be emitted.

## 21. Common Errors When Registering Multiple MBeans

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Listener receives only from the first MBean | Registered only one ObjectName | Register each source separately |
| `InstanceNotFoundException` | ObjectName not registered yet or just removed | Query registry and check lifecycle |
| `RuntimeOperationsException` or other error | Invalid registration arguments | Check listener/filter/handback |
| No notifications seen | MBean does not support emitting events or has not emitted | Metadata, emitter implementation, and tests |
| MappedObjectNames mismatch | Name differs by a key/value | Compare canonical ObjectName |
| Listener receives too many events | Filter too broad | Filter by type or source |
| Same event processed multiple times | Same listener registered multiple times or multiple subscriptions | Track registrations and clean up |
| Listener stops receiving after replacement | Target MBean unregistered/re-registered | Re-subscribe and monitor delegate |
| Remote client stops receiving | Connector disconnected | Reconnect and re-subscribe |
| Duplicate events across multiple replicas | Collector merges sources incorrectly | Attach target JVM/instance identity |
| Memory leak on shutdown | Listener not removed | Manage lifecycle and cleanup |
| App slows down after enabling listener | Blocking handler | Bounded async dispatch |

## 22. Integration Test for Multiple Sources

An integration test should verify both MBeans:

1. Create an isolated MBeanServer.
2. Register `CacheMonitor` and `QueueMonitor`.
3. Register the same listener on both ObjectNames.
4. Invoke `refresh()` and `signalThreshold()`.
5. Wait to receive both notification types using an appropriate test mechanism.
6. Check ObjectName/handback to distinguish sources.
7. Verify filters block out-of-scope notifications.
8. Remove the listener from one MBean and verify the remaining MBean still emits to the listener.
9. Close the server/context and verify cleanup.

### Basic Test Example with CountDownLatch

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import javax.management.NotificationListener;
import javax.management.ObjectName;

CountDownLatch latch = new CountDownLatch(2);

NotificationListener listener = (notification, handback) -> {
    latch.countDown();
};

server.addNotificationListener(cacheName, listener, null, cacheName);
server.addNotificationListener(queueName, listener, null, queueName);

server.invoke(cacheName, "refresh", new Object[0], new String[0]);
server.invoke(queueName, "signalThreshold",
              new Object[0], new String[0]);

if (!latch.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("Expected two notifications");
}
~~~

`server`, `cacheName`, and `queueName` are variables that must be created beforehand in the fixture. The snippet illustrates waiting for two callbacks, but a production test should record notification types to verify **each source emitted the expected type**, not just a total count of two events.

## 23. Inspecting Listeners in JConsole

JConsole supports observing notifications on certain MBeans. When testing:

1. Start the application and connect to the right JVM.
2. Open the **MBeans** tab.
3. Select the `CacheMonitor` source.
4. Find the notifications section (if supported by the tool).
5. Subscribe and invoke the `refresh()` operation.
6. Confirm the event appears.
7. Repeat with `QueueMonitor`.
8. Compare notification type, source, and sequence.
9. Verify inside the Spring application that the shared listener receives events from both sources.

JConsole's own tool subscription is not proof that the Spring exporter registered the application's listener. To confirm the Spring listener, you need test logs or a direct assertion on the listener bean.

## 24. Security and Notification Access Control

Notifications can also carry sensitive data. A `Notification` has a `userData` field that an emitter might use to attach detailed information.

Do not publish:

- Passwords or tokens.
- Personal data.
- Connection strings containing credentials.
- Internal details that expose sensitive architecture.
- Full stack traces or business payloads when unnecessary.

For remote JMX, the connector requires authentication, TLS, and authorization. Listener registration permissions may depend on connector/server policy. A listener reading notifications should not be granted `readwrite` permission simply because the application has other operations.

Additionally, if the listener forwards events to Slack, email, or another system, that is an outbound data path requiring separate control.

## 25. Special Cases

### Multiple ApplicationContexts

One JVM can contain parent/child contexts or multiple independent contexts sharing the platform MBeanServer. A listener in one exporter does not automatically cover MBeans of another exporter/context. Clearly define the owner and scope of each exporter.

### Replaced MBeans

If using `RegistrationPolicy.REPLACE_EXISTING`, the same ObjectName may point to a new MBean. An old subscription is not necessarily transferred. Clients must handle registry changes and re-register.

### MBeans Unregistered When Context Closes

Registrations attached to the old MBean may no longer exist. Listener clients must clear tracking and can re-subscribe when the source reappears.

### Multi-Replica

The same ObjectName on two JVMs is not the same emitter. A remote client receives notifications only from the target JVM to which its connection is attached. To aggregate across a cluster, you need multiple connections/subscriptions and distinct target labels.

### Excessive Notifications

If an MBean emits thousands of notifications/second, JMX may not be a suitable transport for event streaming. Use metric aggregation or a message broker system when throughput, buffering, and replay are needed.

## 26. Implementation Checklist

Before running a system with one listener monitoring multiple MBeans:

1. Are source MBeans registered under the right ObjectNames?
2. Do all sources actually support NotificationBroadcaster/Emitter?
3. Does the Spring exporter manage the exact MBeans being mapped?
4. Is the listener bean created in the right context?
5. Are MappedObjectNames complete and accurate?
6. Are appropriate filters configured for each notification type?
7. Is the handler fast and free of significant blocking?
8. Are queue or executor bounds set for asynchronous processing?
9. Is cleanup handled on shutdown or context change?
10. Is re-subscription handled after reconnect/replacement?
11. Are handback/target identities used to distinguish sources?
12. Are there unit/integration tests for at least two emitters?
13. Is sensitive data controlled in userData/logs?
14. Is it established that notification delivery is not a durable guarantee?
15. Is there a policy for dynamically created MBeans?

## 27. Self-Check Questions

**1. Can a NotificationListener receive from multiple MBeans?**

Yes. You must register the listener separately with each MBean or use an appropriate Spring exporter mapping.

**2. Does registering a listener for an ObjectName pattern automatically track all MBeans created later?**

Do not assume so. If you need to track dynamic MBeans, design a registry listener and separate subscription synchronization.

**3. Why is handback needed?**

It helps pass registration context, such as the source ObjectName or resource ID, so a shared listener can distinguish notifications.

**4. Does using `@ManagedNotification` automatically emit events?**

No. The annotation only declares metadata; the implementation must actually emit notifications.

**5. Is MBeanProxyFactoryBean the primary tool for receiving notifications?**

No. It creates typed proxies for accessing attributes/operations; receiving notifications uses listeners and registration mechanisms of JMX or the Spring exporter.

**6. Why might notifications be lost after reconnecting?**

Subscriptions are usually tied to runtime connections/registrations and have no automatic durable replay mechanism.

**7. Is a notification's sequenceNumber a global sequence number across multiple MBeans?**

No. Each emitter can generate its own sequence. Add ObjectName/target identity when correlating.

**8. Can one listener be used for JVM MBeans and custom MBeans?**

Yes, if the emitters support notifications and the client has permission. For sources outside the current Spring exporter, registering directly via MBeanServerConnection is usually clearer.

## 28. Summary

Registering a listener for multiple MBeans in Spring JMX is a coordination problem of **multiple emitters → one or more handlers**.

- The JMX API lets you reuse the same `NotificationListener` and call `addNotificationListener` for each ObjectName.
- Spring `MBeanExporter` together with `NotificationListenerBean` helps configure listeners for MBeans within the exporter's scope.
- `NotificationFilter` helps select the needed events, and `handback` helps carry source information.
- For dynamic MBeans, observe the registry and manage re-subscription.
- For remote JMX, handle reconnection, access permissions, and potential notification loss.
- Handlers should be fast, have concurrency controls, and avoid exposing sensitive data.

**A shared listener does not eliminate the lifecycle of individual subscriptions.** Good design must specify the exact ObjectName of each emitter, the notification types to receive, and how cleanup is handled when a source or connection changes.

### References

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `NotificationListenerBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/NotificationListenerBean.html
- Java SE API — `NotificationListener`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE API — `MBeanServerNotification`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerNotification.html
