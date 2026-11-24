# Spring Framework JMX Notification: Registering and Removing Listeners

## 1. Objectives and Big Picture

JMX does not only allow reading/writing attributes or invoking operations on MBeans. An MBean can also **emit Notifications** when a management event occurs, such as a worker state change, a queue crossing a threshold, a processing batch finishing, or a resource reconfiguration. Interested components can **register a listener** to receive events, and then **unregister** it when monitoring is no longer needed.

Three main roles:

- **Emitter (notification broadcaster / emitter)**: the MBean emitting \`javax.management.Notification\`.
- **Listener**: an object implementing \`javax.management.NotificationListener\`, handling notifications via \`handleNotification(Notification, Object)\`.
- **MBeanServer**: the intermediary where listeners are registered and removed by \`ObjectName\`. For listeners managed through the server, another \`ObjectName\` can be used to designate the receiving MBean.

Basic flow:

\`\`\`text
                               register
JMX client / Spring bean  ------------------------+
    NotificationListener                          |
             |                                     v
             |                            MBeanServer
             |                                   |
             | addNotificationListener(          | broadcaster's ObjectName
             |     name, listener, filter, handback)
             |                                   |
             +<----------- Notification ----------+
             |
             +--> handleNotification(notification, handback)
             |
             +-- removeNotificationListener(...) --> Cancel subscription
\`\`\`

**Registering** creates a notification-receiving relationship. **Unregistering** ends that relationship. Do not confuse a Java listener object still existing in memory with the listener still being registered to receive notifications: an object can still be alive while no longer receiving events, or a listener not directly referenced by business code may still be retained by MBeanServer/broadcaster via an active subscription.

## 2. Foundational Java JMX APIs

Core types in \`javax.management\`:

| API | Role |
|---|---|
| \`Notification\` | Event data, containing type, source, sequence number, timestamp, message, and optional user data |
| \`NotificationListener\` | Callback receiving notifications via \`handleNotification\` |
| \`NotificationFilter\` | Decides which notifications are forwarded to the listener |
| \`NotificationFilterSupport\` | Utility filter based on notification type |
| \`NotificationBroadcaster\` | Contract for emitting events and managing listeners |
| \`NotificationEmitter\` | Extends broadcaster and supports removal by the listener/filter/handback triple |
| \`NotificationBroadcasterSupport\` | Utility class for emitting notifications and managing registrations |
| \`MBeanServerConnection\` | API for registering/removing listeners from a client or through MBeanServer |

Listener interface:

\`\`\`java
import javax.management.Notification;
import javax.management.NotificationListener;

NotificationListener listener = new NotificationListener() {
    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {
        System.out.println(
            "type=" + notification.getType()
                + ", seq=" + notification.getSequenceNumber()
                + ", message=" + notification.getMessage()
                + ", handback=" + handback
        );
    }
};
\`\`\`

The \`handback\` parameter is an object passed in by the **registrant**. It helps the listener distinguish subscription contexts. \`handback\` is not the main event payload; the payload lives in the \`Notification\` object and may include \`userData\`.

## 3. Creating a Simple Broadcaster MBean

An MBean emitting notifications should advertise its notification capability. For example, a worker controller can emit a notification when transitioning from RUNNING to PAUSED.

Define the management interface:

\`\`\`java
package com.example.jmx;

public interface WorkerControlMBean {
    boolean isActive();
    void pause();
    void resume();
}
\`\`\`

Implement the broadcaster with \`NotificationBroadcasterSupport\`:

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class WorkerControl
        extends NotificationBroadcasterSupport
        implements WorkerControlMBean {

    public static final String PAUSED = "com.example.worker.paused";
    public static final String RESUMED = "com.example.worker.resumed";

    private final AtomicLong sequence = new AtomicLong();
    private volatile boolean active = true;

    @Override
    public boolean isActive() {
        return active;
    }

    @Override
    public synchronized void pause() {
        if (!active) {
            return;
        }
        active = false;
        sendNotification(new Notification(
            PAUSED,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Worker paused"
        ));
    }

    @Override
    public synchronized void resume() {
        if (active) {
            return;
        }
        active = true;
        sendNotification(new Notification(
            RESUMED,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Worker resumed"
        ));
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { PAUSED, RESUMED },
                Notification.class.getName(),
                "Worker lifecycle notifications"
            )
        };
    }
}
\`\`\`

In this example, \`getNotificationInfo()\` declares the notification types the MBean can emit; clients use metadata for discovery. \`sendNotification\` actually emits events to registered listeners.

**Concurrency note:** the example sends notifications while holding the \`synchronized\` lock. In real business operations, you can capture state changes inside the lock and emit the notification after leaving the synchronized block to reduce the risk of callbacks or executors causing complex interactions. The design must keep state change ordering consistent with event emission.

Register the MBean on the platform MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerControl,name=main"
);

server.registerMBean(new WorkerControl(), name);
\`\`\`

This snippet assumes the ObjectName is not already registered. In Spring applications, \`MBeanExporter\` usually registers the MBean instead of calling \`registerMBean\` manually for the same bean.

## 4. Registering a NotificationListener with MBeanServer

The most common approach uses the overload:

\`\`\`java
void addNotificationListener(
    ObjectName name,
    NotificationListener listener,
    NotificationFilter filter,
    Object handback
)
\`\`\`

Full example:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.NotificationFilterSupport;
import javax.management.ObjectName;

ObjectName target = new ObjectName(
    "com.example.app:type=WorkerControl,name=main"
);

NotificationListener listener = (Notification n, Object context) -> {
    System.out.printf(
        "event=%s, sequence=%d, context=%s%n",
        n.getType(),
        n.getSequenceNumber(),
        context
    );
};

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.worker.paused");
filter.enableType("com.example.worker.resumed");

String handback = "monitoring-subscription-1";

server.addNotificationListener(
    target,
    listener,
    filter,
    handback
);
\`\`\`

Meaning of each argument:

1. \`target\`: **ObjectName of the notification-emitting MBean**, not the listener's name.
2. \`listener\`: actual callback object receiving events.
3. \`filter\`: can be \`null\` to receive all notification types the broadcaster forwards; when using a filter, an event reaches the callback only if \`isNotificationEnabled\` returns \`true\`.
4. \`handback\`: optional \`null\` or any suitable context object in the JVM; MBeanServer passes this value to the listener when invoking the callback.

\`NotificationFilterSupport.enableType\` checks types starting with the enabled string, so it can also match subtypes sharing the same prefix. When you need to match **one exact type**, implement a custom filter with \`notification.getType().equals(...)\` or strictly enforce type namespace conventions. Do not treat prefix filters as an authorization mechanism.

To test:

\`\`\`java
server.invoke(
    target,
    "pause",
    new Object[0],
    new String[0]
);

server.invoke(
    target,
    "resume",
    new Object[0],
    new String[0]
);
\`\`\`

After the invocations, the listener receives matching notifications according to the broadcaster's dispatch mechanism. With an asynchronously implemented broadcaster, callbacks may run later; do not rely on callback ordering as a synchronous transaction with the operation unless a specific contract guarantees it.

## 5. Removing Listeners Properly

JMX supports two ways to remove a listener object via \`MBeanServerConnection\`:

\`\`\`java
removeNotificationListener(ObjectName name, NotificationListener listener)

removeNotificationListener(
    ObjectName name,
    NotificationListener listener,
    NotificationFilter filter,
    Object handback
)
\`\`\`

### 5.1. Removing all registrations of a listener on an MBean

\`\`\`java
server.removeNotificationListener(target, listener);
\`\`\`

The two-parameter overload removes registrations of \`listener\` on the \`target\` broadcaster (per the API contract). The same listener may be registered on other MBeans, so removing on \`target\` does not remove subscriptions on other MBeans.

### 5.2. Removing a specific subscription precisely

If the same \`listener\` is registered multiple times with different filters/handbacks, the four-parameter overload allows removing one specific registration combination:

\`\`\`java
server.removeNotificationListener(
    target,
    listener,
    filter,
    handback
);
\`\`\`

You must pass back the exact filter/handback objects used during registration. In local JMX, matching typically relies on identity of listener, filter, and handback per the listener management contract; **do not construct a new filter object with identical contents and assume it matches the old subscription**.

Common mistake:

\`\`\`java
NotificationFilterSupport first = new NotificationFilterSupport();
first.enableType("com.example.worker.paused");

server.addNotificationListener(target, listener, first, "ctx");

// A different filter object:
NotificationFilterSupport second = new NotificationFilterSupport();
second.enableType("com.example.worker.paused");

// Do not assume second identifies the exact registration made with first.
server.removeNotificationListener(target, listener, second, "ctx");
\`\`\`

Keep the original \`listener\`, \`filter\`, and \`handback\` inside a subscription management object for accurate removal.

### 5.3. Removing a listener when the target object is unregistered

If \`target\` has already been unregistered from the MBeanServer, calling remove may raise \`InstanceNotFoundException\`. If the broadcaster cannot find a matching registration, JMX typically throws \`ListenerNotFoundException\`. A shutdown handler may choose to log when a subscription has already disappeared, but should not swallow all exceptions because doing so could hide configuration errors or wrong names.

## 6. Managing Lifecycle with AutoCloseable

To avoid forgetting to remove listeners, wrap the subscription in an object with \`close()\`. When setup succeeds, \`close()\` performs removal once.

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

public final class JmxSubscription implements AutoCloseable {
    private final MBeanServerConnection connection;
    private final ObjectName broadcaster;
    private final NotificationListener listener;
    private final NotificationFilter filter;
    private final Object handback;
    private final AtomicBoolean closed = new AtomicBoolean();

    public JmxSubscription(
            MBeanServerConnection connection,
            ObjectName broadcaster,
            NotificationListener listener,
            NotificationFilter filter,
            Object handback) throws Exception {

        this.connection = connection;
        this.broadcaster = broadcaster;
        this.listener = listener;
        this.filter = filter;
        this.handback = handback;

        connection.addNotificationListener(
            broadcaster,
            listener,
            filter,
            handback
        );
    }

    @Override
    public void close() throws Exception {
        if (!closed.compareAndSet(false, true)) {
            return;
        }
        connection.removeNotificationListener(
            broadcaster,
            listener,
            filter,
            handback
        );
    }
}
\`\`\`

Usage:

\`\`\`java
try (JmxSubscription subscription = new JmxSubscription(
        server,
        target,
        listener,
        filter,
        handback)) {

    server.invoke(target, "pause", new Object[0], new String[0]);
    server.invoke(target, "resume", new Object[0], new String[0]);

} // close() unregisters the listener
\`\`\`

This example emphasizes **ownership and cleanup**. In real applications, consider exceptions during removal, retries, or confirming closed state before marking cancelled. In the version above, \`closed\` flips to \`true\` before \`removeNotificationListener\` completes; if removal fails, the object does not automatically retry. Choose this policy only when shutdown is best-effort, or add appropriate error handling.

For long-lived listeners spanning the entire Spring context lifecycle, store the subscription as a bean field and cancel it in the destroy callback instead of limiting it to a short \`try-with-resources\`.

## 7. Spring Framework: Registering Listeners via MBeanExporter

Spring JMX provides \`MBeanExporter\` to export beans and supports registering notification listeners via exporter configuration. Depending on wiring, Spring can manage registration/removal lifecycles when the context closes.

Related interfaces and classes:

- \`org.springframework.jmx.export.MBeanExporter\`
- \`org.springframework.jmx.export.notification.NotificationListenerBean\`
- \`org.springframework.jmx.export.notification.NotificationPublisher\`
- \`org.springframework.jmx.export.notification.NotificationPublisherAware\`

### 7.1. Plain listener in Spring

\`\`\`java
package com.example.jmx;

import javax.management.Notification;
import javax.management.NotificationListener;

public class AuditNotificationListener implements NotificationListener {
    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {

        System.out.printf(
            "[JMX AUDIT] type=%s, source=%s, msg=%s%n",
            notification.getType(),
            notification.getSource(),
            notification.getMessage()
        );
    }
}
\`\`\`

You can declare a \`NotificationListenerBean\` to describe the listener, target MBeans, and filter/context. Configuration example:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.notification.NotificationListenerBean;

@Configuration
public class JmxListenerConfiguration {
    @Bean
    public AuditNotificationListener auditNotificationListener() {
        return new AuditNotificationListener();
    }

    @Bean
    public NotificationListenerBean auditListenerBean(
            AuditNotificationListener auditNotificationListener) {

        NotificationListenerBean definition = new NotificationListenerBean();
        definition.setNotificationListener(auditNotificationListener);
        definition.setMappedObjectName(
            "com.example.app:type=WorkerControl,name=main"
        );
        return definition;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            WorkerControl workerControl,
            NotificationListenerBean auditListenerBean) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(java.util.Map.of(
            "com.example.app:type=WorkerControl,name=main",
            workerControl
        ));
        exporter.setNotificationListeners(auditListenerBean);
        return exporter;
    }
}
\`\`\`

This example shows how to attach a listener to an exporter. Be careful not to configure another exporter that automatically exports the same bean, especially when using Spring Boot auto-configuration or \`@EnableMBeanExport\`. The exported bean's type must actually support NotificationBroadcaster/Emitter.

In Spring, \`NotificationListenerBean\` can map a listener to one or more \`ObjectName\`s; when no mapping is specified, registration scope depends on exporter configuration. Explicitly declare target MBeans to avoid receiving unwanted notifications.

### 7.2. NotificationPublisherAware for Spring-exported beans

For Spring-managed MBeans, \`NotificationPublisherAware\` can be used to receive a \`NotificationPublisher\` supplied by the exporter:

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "com.example.app:type=WorkerControl,name=main"
)
public class SpringWorkerControl implements NotificationPublisherAware {
    private final AtomicLong sequence = new AtomicLong();
    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedOperation
    public void pause() {
        // Update business state here...
        publisher.sendNotification(new Notification(
            "com.example.worker.paused",
            this,
            sequence.incrementAndGet(),
            "Worker paused"
        ));
    }
}
\`\`\`

This example targets Spring JMX annotation export. \`NotificationPublisherAware\` is on the **emitting** side, distinct from \`NotificationListener\` on the **receiving** side. For clients to discover notification types accurately, the MBean must carry notification metadata compatible with the export/assembler mechanism in use.

When a bean is not managed by an exporter or the publisher has not been injected yet, calling \`publisher.sendNotification\` can fail; Spring lifecycle and exporter configuration must be properly set up.

## 8. Spring Lifecycle: Creating Subscriptions and Removing When Context Closes

If a Spring application actively registers listeners via the JMX API, lifecycle can be managed using \`@PostConstruct\` and \`@PreDestroy\`, or \`SmartLifecycle\` / \`DisposableBean\` depending on requirements.

Example Spring bean registering at startup and removing on context close:

\`\`\`java
package com.example.jmx;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import org.springframework.stereotype.Component;

@Component
public class WorkerNotificationSubscriber {

    private final MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

    private final ObjectName target;
    private final NotificationListener listener;
    private final NotificationFilterSupport filter;

    public WorkerNotificationSubscriber() throws Exception {
        target = new ObjectName(
            "com.example.app:type=WorkerControl,name=main"
        );

        listener = (Notification event, Object handback) ->
            System.out.println("Received: " + event.getType());

        filter = new NotificationFilterSupport();
        filter.enableType("com.example.worker.");
    }

    @PostConstruct
    public void start() throws Exception {
        server.addNotificationListener(
            target,
            listener,
            filter,
            null
        );
    }

    @PreDestroy
    public void stop() throws Exception {
        server.removeNotificationListener(
            target,
            listener,
            filter,
            null
        );
    }
}
\`\`\`

This snippet is illustrative for applications using Jakarta annotations. In Spring Framework 6, \`jakarta.annotation\` is the standard namespace. The Jakarta annotation API dependency must be on the classpath if not provided by the runtime.

**Note on initialization ordering:** the subscriber's \`@PostConstruct\` might run before the target MBean is exported. If so, \`InstanceNotFoundException\` will occur. In real applications, establish explicit dependencies so the exporter completes registration first, use an appropriate lifecycle phase, or register after a context-ready event; do not use an infinite retry loop without checking shutdown.

If \`@PreDestroy\` runs after the exporter has already unregistered the MBean, removal can fail. You can let the same component manage both exporter and subscription, or choose \`SmartLifecycle\` with controlled start/stop ordering.

### When should Spring handle registration?

If the subscriber lives in the same Spring context as \`MBeanExporter\` and lifecycles can be managed together, \`NotificationListenerBean\` usually reduces manual code. If the subscriber is an external client or connects to remote JMX, managing directly via \`MBeanServerConnection\`/\`JMXConnector\` is usually clearer.

## 9. Registering Listeners from a JMX Remote Client

When a Java client connects to another JVM, it typically uses \`JMXConnectorFactory\`:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL serviceUrl = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

try (JMXConnector connector =
        JMXConnectorFactory.connect(serviceUrl)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName target = new ObjectName(
        "com.example.app:type=WorkerControl,name=main"
    );

    NotificationListener listener = (event, context) ->
        System.out.println("Remote event: " + event.getType());

    connection.addNotificationListener(
        target,
        listener,
        null,
        null
    );

    try {
        // Client is active and able to receive notifications.
        // Do not close the connector before ending the subscription.
    } finally {
        connection.removeNotificationListener(target, listener);
    }
}
\`\`\`

This illustrates the connection pattern; the endpoint only works when remote JMX has been configured accordingly. In real environments, configure authentication, authorization, TLS/transport security, and network restrictions per infrastructure standards. Never expose a public remote JMX port without securing access.

**Characteristics of remote delivery:**

- Notifications are transferred over the JMX connector's transport; losing connection can cause the client to miss notifications.
- Do not assume notifications are durably stored, automatically retried indefinitely, or delivered exactly once.
- \`Notification\` and \`userData\` must be compatible with serialization/transport when crossing a remote connector.
- Listeners receive only notifications emitted after the subscription is actually established; there is no built-in historical replay mechanism.
- Manage reconnect and resubscribe when connections drop if the application needs long-running observation.

If a subscription is lost after a disconnect, the client should ensure the new connection is ready and then re-register. Avoid creating duplicate subscriptions on the same connection, which leads to duplicate callbacks.

## 10. Case Where the Listener Is a Registered MBean

Besides accepting a \`NotificationListener\` object, \`MBeanServerConnection\` has an overload that registers a listener by \`ObjectName\`:

\`\`\`java
addNotificationListener(
    ObjectName broadcasterName,
    ObjectName listenerName,
    NotificationFilter filter,
    Object handback
)
\`\`\`

In this form, the listener must be an MBean identified in MBeanServer by \`listenerName\` and satisfy the appropriate notification-receiving contract. The goal is for the intermediary server to manage the relationship between two MBeans.

Syntax example:

\`\`\`java
ObjectName broadcaster = new ObjectName(
    "com.example.app:type=WorkerControl,name=main"
);

ObjectName listenerMBean = new ObjectName(
    "com.example.app:type=AuditListener,name=worker-events"
);

server.addNotificationListener(
    broadcaster,
    listenerMBean,
    null,
    "operations"
);
\`\`\`

A valid listener MBean must be registered before making this call. Merely naming a plain Java object is not enough. Removing the subscription:

\`\`\`java
server.removeNotificationListener(
    broadcaster,
    listenerMBean
);
\`\`\`

or the overload with filter and handback. On \`InstanceNotFoundException\`, distinguish between an unregistered broadcaster and a missing listener ObjectName; check both with \`isRegistered\`.

## 11. Filters and Handback When a Listener Is Reused

One listener can receive events from multiple sources or multiple event types. For instance, the same callback registered twice with different filters:

\`\`\`java
NotificationListener listener = (n, context) ->
    System.out.println(context + ": " + n.getType());

NotificationFilterSupport pauseFilter =
    new NotificationFilterSupport();
pauseFilter.enableType("com.example.worker.paused");

NotificationFilterSupport resumeFilter =
    new NotificationFilterSupport();
resumeFilter.enableType("com.example.worker.resumed");

Object pauseContext = new Object();
Object resumeContext = new Object();

server.addNotificationListener(
    target, listener, pauseFilter, pauseContext
);
server.addNotificationListener(
    target, listener, resumeFilter, resumeContext
);
\`\`\`

To stop receiving pause events while continuing to receive resume events:

\`\`\`java
server.removeNotificationListener(
    target, listener, pauseFilter, pauseContext
);
\`\`\`

To stop all subscriptions of this listener on target:

\`\`\`java
server.removeNotificationListener(target, listener);
\`\`\`

If a client creates duplicate registrations, a single notification can trigger multiple callbacks. Duplication is sometimes caused by setup logic re-running without removing earlier registrations, rather than the broadcaster emitting multiple times.

**Handback should be lightweight, non-sensitive context.** With remote JMX, consider objects sent over connectors and serializability requirements. Do not put secrets or resource-heavy objects into handback just to tag a subscription.

## 12. Common Errors When Registering and Removing

| Scenario | Typical Symptom | How to Diagnose |
|---|---|---|
| Wrong broadcaster ObjectName | \`InstanceNotFoundException\` | Check \`isRegistered\` and \`queryNames\` |
| MBean does not support notifications | \`RuntimeOperationsException\` or adapter-specific error | Check if MBean is broadcaster/emitter and has \`MBeanNotificationInfo\` |
| Listener already removed | \`ListenerNotFoundException\` on subsequent remove | Manage subscription state and single cleanup owner |
| Different filter/handback passed on remove | \`ListenerNotFoundException\` | Retain the exact objects used during registration |
| Unintentionally registered twice | Event hits callback twice | Track add/remove counts and subscription identity |
| Filter does not match | Listener receives no notifications | Check \`getType()\` and filter matching rules |
| Operation emits no event | Listener receives no notifications | Verify broadcaster calls \`sendNotification\` |
| MBean unregistered | Remove fails or events stop | Manage lifecycle and shutdown ordering |
| Remote connection dropped | Missed notifications, callbacks stop | Check connector, reconnect, and resubscribe |
| Callback throws runtime exception | Dispatch log/error or caller thread impact depending on executor | Catch errors inside listener and isolate processing |

Do not assume a single exception type across all MBeanServer implementations, Spring adapters, and JMX connectors. Read \`cause\`, stack trace, broadcaster name, and MBean metadata to pinpoint the actual failure.

## 13. Concurrency and Callback Reliability

\`NotificationListener.handleNotification\` is a callback; how and when it runs depends on the broadcaster/connector and executor.

- **Do not perform long blocking work in callbacks.** If the listener needs database writes, network calls, or heavy computation, push minimal data to a bounded executor/queue and process outside the callback.
- **Do not assume callbacks always run on the thread invoking the operation.** \`NotificationBroadcasterSupport\` may use an executor to dispatch; remote connectors also have their own event transport threads.
- **Do not assume consecutive events equal a single transaction.** An MBean can send notifications while state continues changing or listeners read newer state.
- **Define removal semantics clearly.** \`removeNotificationListener\` cancels the registration, but callbacks already scheduled beforehand may still be executing; full shutdown requires stopping worker queues and awaiting in-flight tasks if the application contract demands it.
- **Make callbacks resilient.** Handle errors locally, record metrics for succeeded/failed events, and never let one malformed event crash the entire listener.

Example lightweight handler:

\`\`\`java
NotificationListener listener = (notification, handback) -> {
    try {
        String type = notification.getType();
        long sequence = notification.getSequenceNumber();

        // Handle quickly or enqueue into a bounded queue.
        System.out.println(type + " #" + sequence);
    } catch (RuntimeException ex) {
        // Log with context without exposing sensitive data.
        System.err.println("JMX notification handler failed: " + ex);
    }
};
\`\`\`

In systems needing to detect missed events, observe sequence numbers together with source and restart epoch. **Sequence numbers do not guarantee global uniqueness or exactly-once delivery**; different sources can have independent sequences, and restarts can reset counters. If durable event history is required, use a message broker/event log instead of relying solely on JMX Notifications.

## 14. Reproducible Practice Procedure

Suppose the \`WorkerControl\` MBean is already registered and you have \`MBeanServer server\` and \`ObjectName target\`.

### Step 1: Verify broadcaster exists

\`\`\`java
if (!server.isRegistered(target)) {
    throw new IllegalStateException("MBean not registered: " + target);
}

for (var info : server.getMBeanInfo(target).getNotifications()) {
    System.out.println(
        "notification class=" + info.getName()
    );
    for (String type : info.getNotifTypes()) {
        System.out.println("  type=" + type);
    }
}
\`\`\`

### Step 2: Create listener and filter

\`\`\`java
NotificationListener listener = (n, ctx) ->
    System.out.println("RECEIVED " + n.getType());

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.worker.paused");
\`\`\`

### Step 3: Register

\`\`\`java
server.addNotificationListener(target, listener, filter, null);
\`\`\`

### Step 4: Invoke operation to emit event

\`\`\`java
server.invoke(target, "pause", new Object[0], new String[0]);
\`\`\`

Observe the listener receiving the pause event.

### Step 5: Unregister

\`\`\`java
server.removeNotificationListener(target, listener, filter, null);
\`\`\`

### Step 6: Invoke again and verify subscription is gone

\`\`\`java
server.invoke(target, "resume", new Object[0], new String[0]);
server.invoke(target, "pause", new Object[0], new String[0]);
\`\`\`

After removal, the listener is no longer scheduled to receive new events from that subscription. If callbacks were already dispatched earlier or a remote client has latency, late callbacks may still appear. Account for this behavior when verifying shutdown in asynchronous systems.

## 15. Self-Check Questions

**1. Why keep a reference to NotificationListener?**

To remove the exact listener instance that was registered and avoid losing cleanup capability. If a new lambda is created each time, you cannot assume the new lambda matches the old registration.

**2. If a listener was added twice with two different filters, what does calling the two-argument remove do?**

It removes that listener's registrations on the corresponding broadcaster. To remove only one specific subscription, use the four-argument overload with the exact filter and handback.

**3. Does a filter replace authorization?**

No. Filters only select which events are forwarded to a listener. Authorization must be enforced by the JMX connector/server and system security policies.

**4. Why might a client receive no notifications even when the MBean is registered?**

The MBean may not be emitting events, the filter may not match, the ObjectName may be wrong, listener registration may not have succeeded, the connection may have dropped, or the event occurred before the subscription was established.

**5. Can JMX Notifications be used as a durable message queue?**

There is no default guarantee of durable storage, replay, or exactly-once delivery. They suit runtime management signals; strict delivery requirements call for an appropriate messaging platform.

**6. When the Spring context stops, what needs checking?**

Identify which lifecycles own the exporter and subscriber, the unregistration order, and handling cases where the broadcaster has already disappeared; avoid leaving subscriptions active after the service no longer needs monitoring.

## 16. Remember

Registering a JMX Notification listener via \`MBeanServer.addNotificationListener\` establishes a **broadcaster → listener** relationship, with optional filter and handback. Remove it with \`removeNotificationListener\`, preferring to keep original references to remove the exact subscription. With Spring Framework, you can use \`NotificationListenerBean\` alongside \`MBeanExporter\` so Spring manages registrations, or use the JMX API directly within Spring lifecycle hooks when fine-grained control is needed.

The most important point when building multi-component systems is treating a listener as a resource with an **owner, lifecycle, and cleanup**. Define when to register, when to stop, and how to handle reconnects, slow callbacks, and removal errors. That way notifications genuinely aid runtime observability without creating duplicate subscriptions or leaking retained resources.