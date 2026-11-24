# notificationListenerMappings of MBeanExporter in Spring JMX

## 1. Learning Objectives

When using Spring Framework JMX, an **MBean** can not only expose attributes and operations but also emit a **JMX Notification** when a management event occurs. For example: a queue becomes overloaded, a worker is paused, a cache is refreshed, or a background task finishes.

`MBeanExporter` supports the **`notificationListenerMappings`** configuration property to attach `javax.management.NotificationListener` instances to the appropriate MBeans during the export process.

After this lesson, you will understand:

- The structure and meaning of `notificationListenerMappings`.
- How to declare a `NotificationListener` and map it to an exported MBean.
- The difference between an **MBean emitting notifications**, a **listener receiving notifications**, an **ObjectName**, and a **listener mapping key**.
- How to configure this using Spring Java `@Configuration` and XML.
- How to manage the listener registration/unregistration lifecycle, handle filters and handbacks, and avoid duplicate listeners.
- How to test notifications using a real `MBeanServer` and troubleshoot issues in a Spring application.

## 2. Overview: Notifications Are Not Attributes or Operations

In JMX, there are three common types of management interaction:

| Component | Usage | Example |
| --- | --- | --- |
| **Attribute** | Client proactively reads/writes state | `PendingJobs`, `Paused` |
| **Operation** | Client proactively invokes an action | `resetStatistics()` |
| **Notification** | MBean emits a notice when an event occurs | `queue.overloaded`, `worker.paused` |

An MBean that emits notifications typically implements `NotificationEmitter` or `NotificationBroadcaster`. Helper classes such as `NotificationBroadcasterSupport` manage the listener list and send events.

A listener implements:

```java
import javax.management.Notification;
import javax.management.NotificationListener;

public class LoggingNotificationListener
        implements NotificationListener {

    @Override
    public void handleNotification(
            Notification notification, Object handback) {

        System.out.println(
            "type=" + notification.getType()
            + ", source=" + notification.getSource()
            + ", message=" + notification.getMessage()
        );
    }
}
```

For a listener to receive notifications, you must **register the listener with the exact MBean** emitting the events. `notificationListenerMappings` is the configuration mechanism for attaching that listener when using `MBeanExporter`.

## 3. What Is notificationListenerMappings?

`MBeanExporter` can accept a map associating an **MBean identifier key** with a **listener**.

Model:

```text
MBeanExporter
  |
  +-- beans:
  |     com.example.jobs:type=Queue,name=Billing
  |        -> billingQueueMonitor
  |
  +-- notificationListenerMappings:
        com.example.jobs:type=Queue,name=Billing
           -> QueueNotificationListener

                       |
                       v
                MBeanServer
                       |
             registered MBean
                       |
                JMX Notification
                       |
                       v
              QueueNotificationListener
```

The mapping key can be an `ObjectName` or an appropriate bean key according to the mechanism `MBeanExporter` is using. When you want readable configuration and want to avoid ambiguity, use the full JMX name of the exported MBean.

Do not interpret this property name as a list of notification types. It is a **mapping of where the listener is registered**. To filter notifications by `type`, combine it with a `NotificationFilter`, or check `notification.getType()` inside `handleNotification`.

Also do not confuse `notificationListenerMappings` with `notificationListeners`. Spring also provides `NotificationListenerBean` to declare listeners and options such as mappedObjectNames, notificationFilter, and handback in detail.

## 4. Creating an MBean Capable of Emitting Notifications

To understand how the mapping works, you first need an MBean that actually emits notifications. For example, a queue management MBean:

```java
package com.example.jobs.jmx;

public interface QueueMonitorMBean {
    int getPendingCount();
    void updatePendingCount(int value);
}
```

Implementation:

```java
package com.example.jobs.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public final class QueueMonitor
        extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    private static final String OVERLOADED =
            "com.example.jobs.queue.overloaded";

    private final AtomicLong sequence = new AtomicLong();
    private volatile int pendingCount;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void updatePendingCount(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("value must be >= 0");
        }

        pendingCount = value;

        if (value >= 100) {
            Notification notification = new Notification(
                OVERLOADED,
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Queue backlog reached " + value
            );

            notification.setUserData(value);
            sendNotification(notification);
        }
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { OVERLOADED },
                Notification.class.getName(),
                "Queue backlog threshold events"
            )
        };
    }
}
```

In this example:

- `QueueMonitorMBean` is a Standard MBean interface.
- `QueueMonitor` extends `NotificationBroadcasterSupport`, providing notification emission and listener management.
- `getNotificationInfo()` publishes metadata about the notifications that can be emitted.
- `updatePendingCount(100)` or higher sends a notification with `type` `com.example.jobs.queue.overloaded`.
- `sequenceNumber` increments monotonically, helping clients observe event emission order per emitter.

The example uses a simple threshold for clarity. In a real system, you should avoid sending unbounded notifications on every update while the backlog remains high: consider emitting only on **state transitions** across the threshold, debouncing, or rate-limiting.

## 5. Creating a NotificationListener for Use in Spring

Event-handling listener:

```java
package com.example.jobs.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import javax.management.Notification;
import javax.management.NotificationListener;

public final class QueueNotificationListener
        implements NotificationListener {

    private final AtomicInteger overloadedEvents =
            new AtomicInteger();

    @Override
    public void handleNotification(
            Notification notification, Object handback) {

        if ("com.example.jobs.queue.overloaded".equals(
                notification.getType())) {
            overloadedEvents.incrementAndGet();

            System.out.println(
                "[JMX] " + notification.getMessage()
            );
        }
    }

    public int getOverloadedEvents() {
        return overloadedEvents.get();
    }
}
```

The listener in the example stores a counter for testing purposes. In production, the listener can forward signals to logging/metrics/an event bus or an incident orchestration system.

**Processing note:** Notification callbacks may run on a thread managed by the emitter/dispatcher. Do not perform slow I/O, long-running processing, or invoke operations that feed back into uncontrolled loops directly inside the callback unless appropriate concurrency is designed.

## 6. Configuring notificationListenerMappings with Java

A centralized configuration example with Spring:

```java
package com.example.jobs.config;

import com.example.jobs.jmx.QueueMonitor;
import com.example.jobs.jmx.QueueNotificationListener;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.NotificationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class QueueJmxConfiguration {

    private static final String QUEUE_NAME =
        "com.example.jobs:type=Queue,name=Billing";

    @Bean
    public QueueMonitor billingQueueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public QueueNotificationListener queueNotificationListener() {
        return new QueueNotificationListener();
    }

    @Bean
    public MBeanServer queueMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter queueMBeanExporter(
            QueueMonitor billingQueueMonitor,
            QueueNotificationListener queueNotificationListener,
            MBeanServer queueMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(queueMBeanServer);

        exporter.setBeans(Map.of(
            QUEUE_NAME,
            billingQueueMonitor
        ));

        Map<String, NotificationListener> mappings = Map.of(
            QUEUE_NAME,
            queueNotificationListener
        );

        exporter.setNotificationListenerMappings(mappings);
        return exporter;
    }
}
```

Meaning of each part:

1. `setBeans` registers the managed object under the chosen `ObjectName`.
2. `setNotificationListenerMappings` instructs the exporter to attach the listener to the specified MBean.
3. `setServer` ensures the exporter registers the MBean and attaches the listener in the intended `MBeanServer`.
4. A client or business code causes `QueueMonitor` to emit a notification.
5. `QueueNotificationListener.handleNotification` receives the callback via the JMX mechanism.

Across Spring versions, the API signature for the mapping may accept a broader map value type; this example uses `Map<String, NotificationListener>` as a compatible type with `setNotificationListenerMappings` for presentation. When applying it, let your IDE determine the exact generic type for your project's Spring Framework version.

Note: `notificationListenerMappings` does not automatically generate notifications and does not turn an ordinary class into a broadcaster. The target must support emitting notifications.

## 7. XML Configuration

For a Spring Framework application declaring beans in XML:

```xml
<bean id="queueMonitor"
      class="com.example.jobs.jmx.QueueMonitor"/>

<bean id="queueNotificationListener"
      class="com.example.jobs.jmx.QueueNotificationListener"/>

<bean id="jmxExporter"
      class="org.springframework.jmx.export.MBeanExporter">

    <property name="beans">
        <map>
            <entry
                key="com.example.jobs:type=Queue,name=Billing"
                value-ref="queueMonitor"/>
        </map>
    </property>

    <property name="notificationListenerMappings">
        <map>
            <entry
                key="com.example.jobs:type=Queue,name=Billing"
                value-ref="queueNotificationListener"/>
        </map>
    </property>
</bean>
```

`value-ref` in the listener map points to the bean implementing `NotificationListener`, not to the MBean emitting the notification.

If you use multiple listeners for one MBean or need filters/handbacks, advanced configuration with `NotificationListenerBean` is usually clearer than trying to cram multiple listeners into a single map key.

## 8. Distinguishing Listener Maps from NotificationListenerBean

Spring supports `org.springframework.jmx.export.NotificationListenerBean`, allowing you to describe a registration with more properties:

- `notificationListener`: the object implementing `NotificationListener`.
- `mappedObjectNames`: the MBeans that receive the listener, by appropriate name/identifier.
- `notificationFilter`: receives only notifications matching the condition.
- `handback`: an object passed along during the callback.

Java example:

```java
import javax.management.NotificationFilterSupport;
import org.springframework.jmx.export.NotificationListenerBean;

NotificationFilterSupport filter =
        new NotificationFilterSupport();

filter.enableType("com.example.jobs.queue.overloaded");

NotificationListenerBean listenerBean =
        new NotificationListenerBean(queueNotificationListener);

listenerBean.setMappedObjectNames(
    "com.example.jobs:type=Queue,name=Billing"
);

listenerBean.setNotificationFilter(filter);
listenerBean.setHandback("billing-queue");

exporter.setNotificationListeners(listenerBean);
```

Here, `NotificationListenerBean` supports a full configuration, whereas `notificationListenerMappings` is a simplified form for mapping listeners by key.

**Which approach should you choose?**

- One listener for one MBean, without needing filter/handback: simple mapping is easy to use.
- Need one listener listening to multiple MBeans or configuring a filter: `NotificationListenerBean` is a better fit.
- Need multiple listeners on the same MBean with separate configurations: use multiple `NotificationListenerBean` instances.

Do not accidentally enable both configurations for the same listener/MBean, as that can cause callbacks to be received multiple times.

## 9. Mapping Keys: ObjectName, Bean Key, and Scope

In some configuration styles, the key used to map a listener can be the full JMX name or the bean key used by the exporter to register the MBean. This depends on how the exporter processes entries and its naming strategy.

An explicit example:

```text
com.example.jobs:type=Queue,name=Billing
```

If you use an internal key:

```text
billingQueueMonitor
```

then you must ensure the exporter maps that key to the correct `ObjectName`, and that the listener mapping follows the rules supported by the Spring version in use.

**Do not assume the Spring bean name and ObjectName are identical.** If the exporter has a naming strategy that turns `billingQueueMonitor` into a different ObjectName, tests need to verify that the listener is actually registered on the expected MBean.

Every MBean on the same server has a unique ObjectName. An incorrect mapping key can cause the listener not to receive notifications or trigger a registration error when the exporter initializes.

## 10. Registration Lifecycle and Cleanup

`MBeanExporter` attaches listeners during export and manages unregistering the listener registrations it established when the exporter/context closes properly.

Flow:

```text
Spring ApplicationContext startup
  |
  +-- Create QueueMonitor
  +-- Create QueueNotificationListener
  +-- Create MBeanExporter
       |
       +-- Register QueueMonitor in MBeanServer
       +-- Register listener with mapped ObjectName
       |
       v
JMX notification flow active

Spring ApplicationContext shutdown
  |
  +-- Unregister listener registrations owned by exporter
  +-- Unregister MBeans owned by exporter
```

Cleanup is especially important if a Spring context is refreshed/redeployed within the same JVM. A lingering old listener can:

- Receive the same event multiple times.
- Hold references to beans/classloaders whose lifecycle has ended.
- Record duplicate or incorrect logs or metrics after redeploy.
- Cause memory leaks.
- Cause errors when the callback accesses a service that has already been closed.

Do not automatically call `unregisterMBean` on an ObjectName not owned by the context just to "clean up." You must understand the ownership of the exporter and MBeanServer.

## 11. Testing Notifications Directly with MBeanServer

Before bringing Spring in, you can verify plain-Java JMX notifications:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class JmxNotificationTest {

    @Test
    void listenerReceivesQueueNotification() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Queue,name=Billing"
        );

        QueueMonitor monitor = new QueueMonitor();
        AtomicInteger received = new AtomicInteger();

        NotificationListener listener = (notification, handback) -> {
            if ("com.example.jobs.queue.overloaded".equals(
                    notification.getType())) {
                received.incrementAndGet();
            }
        };

        try {
            server.registerMBean(monitor, name);
            server.addNotificationListener(
                name, listener, null, null
            );

            // Trigger the event properly via the management operation.
            server.invoke(
                name,
                "updatePendingCount",
                new Object[] { 120 },
                new String[] { "int" }
            );

            assertEquals(1, received.get());
        } finally {
            if (server.isRegistered(name)) {
                try {
                    server.removeNotificationListener(name, listener);
                } catch (javax.management.ListenerNotFoundException ignored) {
                    // Listener was not successfully registered.
                }
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

The example uses a `NotificationBroadcasterSupport` with default synchronous dispatch for illustration. If the broadcaster uses an asynchronous executor, the test needs a bounded wait mechanism (such as a latch) rather than assuming the callback has already executed immediately after invocation.

What the test verifies:

- The MBean is registered.
- The listener is attached to the right ObjectName.
- The operation causes the emitter to emit a notification.
- The callback is received with the expected `type`.
- Registrations are cleaned up in `finally`.

## 12. Testing Through Spring MBeanExporter

An integration test for Spring should initialize an ApplicationContext containing:

- `QueueMonitor`.
- `QueueNotificationListener`.
- A dedicated `MBeanServer` for the test.
- `MBeanExporter` configured with `beans` and `notificationListenerMappings`.

Once the context is refreshed, use the test server to invoke the operation and then verify the listener counter.

Test configuration example:

```java
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class NotificationJmxTestConfig {

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("test.management");
    }

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public QueueNotificationListener queueNotificationListener() {
        return new QueueNotificationListener();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer testMBeanServer,
            QueueMonitor queueMonitor,
            QueueNotificationListener queueNotificationListener) {

        String name =
            "com.example.jobs:type=Queue,name=Billing";

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(name, queueMonitor));
        exporter.setNotificationListenerMappings(
            Map.of(name, queueNotificationListener)
        );
        return exporter;
    }
}
```

Integration test:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SpringNotificationMappingTest {

    @Test
    void receivesNotificationsFromMappedMBean() throws Exception {
        try (var context =
                 new AnnotationConfigApplicationContext(
                     NotificationJmxTestConfig.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            QueueNotificationListener listener =
                context.getBean(QueueNotificationListener.class);

            ObjectName name = new ObjectName(
                "com.example.jobs:type=Queue,name=Billing"
            );

            assertTrue(server.isRegistered(name));

            server.invoke(
                name,
                "updatePendingCount",
                new Object[] { 120 },
                new String[] { "int" }
            );

            assertEquals(1, listener.getOverloadedEvents());
        }
    }
}
```

With a `newMBeanServer` test server, there is no need to release via `MBeanServerFactory.releaseMBeanServer`. Close the `ApplicationContext` so Spring cleans up the exporter and listeners.

If the test has two exporters or the same listener configured in both `notificationListeners` and `notificationListenerMappings`, the callback may be invoked twice. Verify that the configuration attaches the listener only once.

## 13. Filtering Notifications by Type

An MBean can emit multiple notification types:

```text
com.example.jobs.queue.overloaded
com.example.jobs.queue.recovered
com.example.jobs.queue.paused
```

If the listener only cares about overload:

```java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.jobs.queue.overloaded");
```

Then use `NotificationListenerBean.setNotificationFilter(filter)` or `MBeanServer.addNotificationListener(name, listener, filter, handback)` when registering directly.

Do not assume the mapping key contains the notification type name. The mapping key usually identifies the **MBean emitting notifications**; the filter determines **which notifications are received**.

When multiple types matter, you can have multiple dedicated listeners/handlers or one listener branching on `notification.getType()`. Avoid heavy processing inside the callback.

## 14. What Is Handback?

JMX allows passing a `handback` object when registering a listener:

```java
server.addNotificationListener(
    objectName,
    listener,
    filter,
    "billing-queue"
);
```

When the callback runs:

```java
@Override
public void handleNotification(
        Notification notification, Object handback) {

    System.out.println("Source label: " + handback);
}
```

`handback` is context provided by the **listener registrar**. It differs from `notification.getSource()` (the event source) and `notification.getUserData()` (data attached to the event).

If you need to configure handback through Spring, `NotificationListenerBean` is more convenient than simple mapping. Do not arbitrarily put passwords, tokens, or sensitive data into handback.

## 15. Distinguishing Internal Notifications from Remote JMX

`notificationListenerMappings` is used when the **Spring exporter registers a listener on the MBeanServer it manages**.

It does not automatically set up a remote JMX client, open sockets, or transfer a Java listener directly to another JVM by mapping an internal bean.

If a client in another JVM wants to receive notifications:

1. The client connects to the remote `MBeanServerConnection` via `JMXConnector`.
2. The client calls `addNotificationListener` on the remote connection for the MBean's ObjectName.
3. The JMX connector transports notifications back to the client according to the configured protocol and permissions.
4. The client manages reconnection, listener cleanup, and network errors.

Do not confuse a local exporter listener with a remote monitoring subscription. The same ObjectName can exist on multiple JVMs, so you must attach the listener to the right connection/server.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| MBean appears, but listener does not receive events | Bean does not emit notifications; mapping key mismatch; listener not registered | Check broadcaster, `sendNotification`, ObjectName, and config |
| Error when exporter registers listener | MBean does not support notifications or key is wrong | Verify `NotificationBroadcaster`/`NotificationEmitter`, metadata, and server |
| Listener receives events twice | Duplicate registration via mappings, listener beans, or custom code | Choose a single registration/owner mechanism |
| Listener receives too many events | No filter or broadcaster sends on every poll | Use `NotificationFilter`, adjust emission logic |
| `ListenerNotFoundException` on cleanup | Listener already removed or listener/filter/handback tuple mismatch | Manage registrations under the same owner and lifecycle |
| Events stop arriving after redeploy | Old listener/bean retains references, new exporter did not register | Check teardown and startup logs |
| Events arrive but slow down the system | Callback performs slow I/O or heavy logic | Offload processing to an appropriate queue/executor |
| Remote client does not receive events | Connected to wrong server or connector error | Check endpoint, ObjectName, and connection lifecycle |
| Notification type not visible in MBeanInfo | Broadcaster does not publish proper metadata | Check `getNotificationInfo()` |
| Method call succeeds but emits no event | Code path does not call `sendNotification` | Check trigger conditions and implementation |

If `MBeanInfo.getNotifications()` does not contain the expected type, that is a sign to inspect the emitter metadata. However, metadata is only descriptive and does not guarantee that actual logic will emit an event on every invocation.

## 17. Safe Implementation Checklist

- Identify which MBeans actually emit notifications.
- Keep ObjectNames stable with clear domain/type/name.
- Attach listeners only to MBeans you need to listen to.
- Configure a filter when only interested in specific notification types.
- Do not create duplicate registrations between `notificationListenerMappings` and `notificationListeners`.
- Keep callbacks fast and avoid causing notification loops.
- Use appropriate sequence numbers and stable event type descriptions.
- Do not put secrets or personal data in message/userData.
- Verify cleanup when the Spring context closes.
- Test with a real `MBeanServer` in integration tests.
- If listening to remote notifications, test connector/TLS/authentication and reconnection separately.
- Do not treat listeners as a durable delivery mechanism; if you need exactly-once/durable delivery, use an appropriate message broker or event system.

## 18. Hands-On Exercises

1. Create a Standard MBean `QueueMonitor` extending `NotificationBroadcasterSupport`, emitting type `queue.overloaded` when `PendingCount >= 100`.
2. Create a `QueueNotificationListener` that increments a counter when receiving that type.
3. Configure Spring `MBeanExporter.setNotificationListenerMappings` to listen to MBean `com.example.jobs:type=Queue,name=Billing`.
4. Call `updatePendingCount(120)` via `MBeanServer.invoke` and verify the listener receives the event.
5. Replace the simple mapping with `NotificationListenerBean` having `NotificationFilterSupport`, receiving only `queue.overloaded`.
6. Configure two notification types and compare results with and without a filter.
7. Intentionally register the same listener twice and observe the callback count; fix it with a single owner.
8. Write an integration test that closes `ApplicationContext`, ensuring no more callbacks arrive from cleaned-up registrations.
9. Try configuring a listener on an MBean that does not emit notifications to observe how Spring/JMX responds and handles the error.

## 19. Self-Check Questions

- Is `notificationListenerMappings` used to select the MBean emitting events or to select the notification type?
- How does `NotificationListener` differ from `NotificationBroadcaster`?
- Why can't `MBeanExporter` automatically emit notifications for a bean that doesn't support broadcaster?
- When should you use `NotificationListenerBean` instead of a simple map?
- What purposes do `NotificationFilter` and `handback` serve?
- Why might a listener receive the same event twice?
- Does using the same ObjectName on another JVM cause a local listener to receive remote notifications?
- How important is listener cleanup in applications that redeploy multiple times?

**Key takeaway:** `notificationListenerMappings` is a configuration property of `MBeanExporter` used to **attach listeners to MBeans** when Spring registers JMX resources. The MBean must actually support emitting notifications; the mapping does not generate events on its own. For requirements involving filters, handbacks, and multiple listeners, consider `NotificationListenerBean`. Always verify ObjectName, server, lifecycle, and callback behavior through a real `MBeanServer`.