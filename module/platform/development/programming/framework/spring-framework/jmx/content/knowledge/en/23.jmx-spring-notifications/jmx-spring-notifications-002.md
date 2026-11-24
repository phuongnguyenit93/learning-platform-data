# Registering a Listener for a Specific MBean in Spring Framework JMX

## Lesson Objectives

After this lesson, you will be able to:

- Understand the **Notification broadcaster**, **Notification listener**, and **MBeanServer** model in Java Management Extensions (JMX).
- Distinguish between registering a listener for **a specific ObjectName** and listening to notifications from multiple MBeans.
- Use **Spring MBeanExporter** and **NotificationListenerBean** to attach a listener to the right MBean.
- Register a listener directly via **MBeanServer.addNotificationListener(...)**, using a filter and handback when needed.
- Understand the listener lifecycle, how to unregister, cleanup responsibilities, and the risks of duplicate registrations.
- Verify notifications from the right source, avoiding a wrong ObjectName, wrong MBeanServer, or connecting to a different JVM.
- Design concise callbacks with appropriate error handling and security.

## 1. Why Register a Listener for a Single MBean?

In JMX, an MBean can emit a **Notification** when management state changes. For example:

- A cache is cleared.
- A queue exceeds its backlog threshold.
- A scheduler transitions to the paused state.
- A resource reports an error or recovery event.
- The JVM or a library emits operational events from MBeans that support them.

A Spring application may have many MBeans. If you only care about the primary queue, the listener should not receive every event from every resource.

Example ObjectNames:

\`\`\`text
learning.jmx:type=Queue,name=Primary
learning.jmx:type=Queue,name=Secondary
learning.jmx:type=Cache,name=Products
\`\`\`

If the goal is to listen to notifications from the Primary queue, you need to attach the listener to the exact ObjectName:

\`\`\`text
learning.jmx:type=Queue,name=Primary
\`\`\`

Diagram:

\`\`\`text
MBeanServer
  |
  +-- Queue Primary (NotificationBroadcaster)
  |       |
  |       +----> QueuePrimaryListener
  |
  +-- Queue Secondary
  |       |
  |       +----> other listener (if any)
  |
  +-- Cache Products
\`\`\`

**Core point:** Registering a listener for a single MBean selects the **emitting object** by ObjectName. Only then can you use a filter to select the **notification types** to receive from that object.

## 2. Components in the JMX Notification Model

| Component | Role |
|---|---|
| MBean | Managed resource registered under an ObjectName |
| NotificationBroadcaster | Broadcaster interface capable of registering/removing listeners |
| NotificationBroadcasterSupport | Helper class that facilitates emitting notifications |
| Notification | Object carrying type, source, sequence number, timestamp, message |
| NotificationListener | Callback that receives Notifications |
| NotificationFilter | Rule accepting/rejecting each notification |
| Handback | Private context passed back to the listener when receiving an event |
| MBeanServer | Registration point for MBeans and listeners by ObjectName |
| Spring NotificationListenerBean | Bean configuring a listener along with the set of MBeans to listen to |
| Spring MBeanExporter | Component that exports MBeans and coordinates listeners according to configuration |

There are two layers to distinguish:

1. **MBean registration:** The ObjectName must exist in the MBeanServer.
2. **Listener registration:** The listener is attached to that MBean to receive the notifications it emits.

A Spring bean with a JMX annotation is not a broadcaster by default. The MBean must support notifications and actually emit them; otherwise, the listener will have no events to receive.

## 3. ObjectName Is the Identifying Address of an MBean

Example:

\`\`\`java
ObjectName queueName = new ObjectName(
    "learning.jmx:type=Queue,name=Primary"
);
\`\`\`

An ObjectName consists of a domain and key properties. It is not a network URL; a client in another JVM still needs an appropriate JMX connector to access the target MBeanServer.

An ObjectName is an identifier **within a single MBeanServer**. If the same name appears in two JVMs, they can still be two independent MBeans.

When configuring a listener, you need to know:

- **Which MBeanServer** is the MBean in?
- Is the ObjectName exact?
- Does the MBean support **NotificationBroadcaster/NotificationEmitter**?
- Is the listener registered **before or after** the notification is emitted?

Registering a listener after an event has already been sent usually will not let you receive that event retroactively; JMX Notification is not by default a durable event log with replay.

## 4. Creating a Standard MBean That Emits Notifications

Example using QueueMonitor with two notification types:

\`\`\`text
learning.queue.overloaded
learning.queue.recovered
\`\`\`

### 4.1. MBean Interface

File QueueMonitorMBean.java:

\`\`\`java
package example.jmx;

public interface QueueMonitorMBean {
    int getDepth();
    boolean isOverloaded();
    void updateDepth(int depth);
}
\`\`\`

### 4.2. Implementation That Emits Notifications

File QueueMonitor.java:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    public static final String TYPE_OVERLOADED =
            "learning.queue.overloaded";

    public static final String TYPE_RECOVERED =
            "learning.queue.recovered";

    private static final int THRESHOLD = 100;
    private final AtomicLong sequence = new AtomicLong();

    private int depth;
    private boolean overloaded;

    @Override
    public synchronized int getDepth() {
        return depth;
    }

    @Override
    public synchronized boolean isOverloaded() {
        return overloaded;
    }

    @Override
    public synchronized void updateDepth(int depth) {
        if (depth < 0) {
            throw new IllegalArgumentException("depth must be >= 0");
        }

        this.depth = depth;
        boolean next = depth > THRESHOLD;

        if (next == overloaded) {
            return;
        }

        overloaded = next;

        String type = overloaded
                ? TYPE_OVERLOADED
                : TYPE_RECOVERED;

        Notification notification = new Notification(
                type,
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                overloaded ? "Queue overloaded" : "Queue recovered"
        );

        notification.setUserData(depth);
        sendNotification(notification);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { TYPE_OVERLOADED, TYPE_RECOVERED },
                Notification.class.getName(),
                "Queue overload/recovery notifications"
            )
        };
    }
}
\`\`\`

Explanation:

- QueueMonitor implements QueueMonitorMBean according to the Standard MBean convention.
- NotificationBroadcasterSupport helps manage listeners and emit notifications.
- updateDepth emits a notification only when the overload state changes.
- sequenceNumber increments via AtomicLong.
- type describes the overload or recovery situation.
- userData contains depth for the listener to use when needed.

This example illustrates notifications; in production, queue depth is typically updated from the actual processing component. You should not expose a state-mutating operation solely for monitoring if it opens up unnecessary management behavior.

## 5. Registering a Listener Directly via MBeanServer

Java JMX provides the method:

\`\`\`java
server.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
\`\`\`

Where:

- objectName is the name of the MBean to listen to.
- listener is the callback handling notifications.
- filter selects which notifications are accepted.
- handback is a context object returned to the callback, not an event payload controlled by the broadcaster.

Example listening only to the Primary queue:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;

import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class DirectListenerDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName primaryName = new ObjectName(
            "learning.jmx:type=Queue,name=Primary"
        );

        QueueMonitor primary = new QueueMonitor();
        server.registerMBean(primary, primaryName);

        NotificationListener listener = (notification, handback) -> {
            System.out.println(
                "type=" + notification.getType()
                + ", source=" + notification.getSource()
                + ", seq=" + notification.getSequenceNumber()
                + ", handback=" + handback
            );
        };

        server.addNotificationListener(
            primaryName,
            listener,
            null,
            "primary-queue-listener"
        );

        try {
            primary.updateDepth(120);
            primary.updateDepth(50);
        } finally {
            server.removeNotificationListener(primaryName, listener);
            server.unregisterMBean(primaryName);
        }
    }
}
\`\`\`

Notable points:

- The listener is registered with **primaryName**, not with the Queue Secondary name.
- A \`null\` filter allows receiving every notification emitted by the broadcaster.
- Handback is a static string passed by the registrar; the callback receives it back in the second parameter.
- Use try/finally to remove the listener and MBean when finished.

### Why Must You Unregister the Listener?

If the MBean or MBeanServer lives for a long time, an unremoved listener can continue receiving events, retain references to other objects, and cause callbacks to run after the module is no longer active.

Especially in integration tests or applications with multiple ApplicationContexts, failing to clean up can cause duplicate listeners or retain unwanted references.

## 6. Filtering Notification Types on the Right MBean

Selecting the MBean by ObjectName is not enough if the broadcaster emits multiple notification types.

Example receiving only overload:

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter =
        new NotificationFilterSupport();

filter.enableType(QueueMonitor.TYPE_OVERLOADED);

server.addNotificationListener(
    primaryName,
    listener,
    filter,
    null
);
\`\`\`

**Note:** NotificationFilterSupport uses **prefix matching**. If you enable \`learning.queue\`, it can match both overload and recovered because both share the same prefix.

If you want to match a single type exactly:

\`\`\`java
import javax.management.NotificationFilter;

NotificationFilter exactType =
    notification -> QueueMonitor.TYPE_OVERLOADED.equals(
        notification.getType()
    );
\`\`\`

Two filtering layers:

\`\`\`text
ObjectName
  -> receive notifications only from the selected MBean

NotificationFilter
  -> receive only selected types from that broadcaster
\`\`\`

Do not replace a filter by inspecting the message string; messages are usually intended for human readers and can change without changing the event type contract.

## 7. Configuring a Listener in Spring Framework

Spring JMX supports **NotificationListenerBean**, allowing you to attach a NotificationListener to one or more registered MBeans.

Typically you can configure:

- \`notificationListener\`: Java callback.
- \`mappedObjectNames\`: set of MBean ObjectNames to listen to.
- \`notificationFilter\`: filter if needed.
- \`handback\`: context provided by the registrar.

Example configuring a Spring listener for **a specific MBean**:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;
import javax.management.NotificationListener;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class QueueJmxConfiguration {

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public NotificationListener queueNotificationListener() {
        return (notification, handback) -> {
            System.out.println(
                "Queue event: " + notification.getType()
            );
        };
    }

    @Bean
    public MBeanExporter mbeanExporter(
            QueueMonitor monitor,
            NotificationListener queueNotificationListener) {

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);

        exporter.setBeans(Map.of(
            "learning.jmx:type=Queue,name=Primary",
            monitor
        ));

        NotificationListenerBean listenerBean =
            new NotificationListenerBean();

        listenerBean.setNotificationListener(
            queueNotificationListener
        );

        listenerBean.setMappedObjectNames(
            "learning.jmx:type=Queue,name=Primary"
        );

        exporter.setNotificationListeners(
            new NotificationListenerBean[] { listenerBean }
        );

        return exporter;
    }
}
\`\`\`

Here:

1. Spring creates QueueMonitor.
2. Spring creates QueueNotificationListener.
3. MBeanExporter registers QueueMonitor under the Primary ObjectName.
4. The exporter sets up the listener for that ObjectName.
5. When the broadcaster emits a notification, the callback is invoked.

**Important:** mappedObjectNames specifies the exact MBean to listen to. If you omit mappedObjectNames in a way the exporter interprets as broad application, the listener may be attached to multiple MBeans managed by the exporter. Since the goal of this lesson is to listen to one specific MBean, set mappedObjectNames explicitly.

Spring JMX can configure NotificationListenerBean with ObjectName forms or valid ObjectName strings according to the corresponding setter API. If implementing against a specific Spring version, check the exact setter signature of that version.

## 8. Notes on Bean Name and ObjectName

Suppose the Spring bean is named:

\`\`\`text
queueMonitor
\`\`\`

But MBeanExporter registers it under:

\`\`\`text
learning.jmx:type=Queue,name=Primary
\`\`\`

When configuring mappedObjectNames, you are selecting the **JMX ObjectName**, not just an arbitrary Spring bean name.

If a naming strategy turns the bean name into an ObjectName according to a different rule, you need to obtain the **actual ObjectName** after export to configure the listener accurately.

One way to verify:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=Queue,name=Primary"
);

System.out.println(server.isRegistered(name));
\`\`\`

If false, inspect the exporter, server, and naming strategy before concluding that the listener is broken.

## 9. Configuring Filter and Handback in Spring

You can create a filter:

\`\`\`java
@Bean
public NotificationFilter queueOverloadFilter() {
    return notification ->
        QueueMonitor.TYPE_OVERLOADED.equals(
            notification.getType()
        );
}
\`\`\`

And configure the listener bean:

\`\`\`java
NotificationListenerBean listenerBean =
    new NotificationListenerBean();

listenerBean.setNotificationListener(queueNotificationListener);
listenerBean.setMappedObjectNames(
    "learning.jmx:type=Queue,name=Primary"
);
listenerBean.setNotificationFilter(queueOverloadFilter);
listenerBean.setHandback("queue-primary");
\`\`\`

When the callback receives an event:

\`\`\`java
NotificationListener listener = (notification, handback) -> {
    System.out.println("Type = " + notification.getType());
    System.out.println("Context = " + handback);
};
\`\`\`

### What Is Handback Used For?

Handback is useful when a listener handles multiple registrations and wants to know the context attached at registration time, such as a tenant or a logical label.

However, handback does not replace the event source, ObjectName, or security identity. In a remote environment, you must check object transportability and connector semantics. Do not put secrets in handback or use handback as an authentication mechanism.

## 10. Listening to One MBean When the Application Has Multiple Queues

Suppose the exporter registers:

\`\`\`text
learning.jmx:type=Queue,name=Primary
learning.jmx:type=Queue,name=Secondary
\`\`\`

You want the listener to receive only Primary:

\`\`\`java
listenerBean.setMappedObjectNames(
    "learning.jmx:type=Queue,name=Primary"
);
\`\`\`

When Primary emits a notification, the listener receives it. When Secondary emits one, that listener is not attached to Secondary so it does not receive notifications from it through this registration.

If you want to listen to both, configure an explicit list of ObjectNames, or use separate listener beans when they have different handling responsibilities.

**Do not use an ObjectName pattern as a way to automatically register listeners for all future MBeans** if the API you are using requires concrete names. JMX queryNames can accept an ObjectName pattern for querying, but addNotificationListener requires an existing MBean under its registered name.

A system that discovers MBeans dynamically needs a mechanism to detect and register listeners when new MBeans appear, along with cleanup when an MBean is unregistered.

## 11. Lifecycle: Startup, Shutdown, and Duplicate Registration

A listener needs to be registered when:

1. The MBean has already been registered in the MBeanServer.
2. The listener has been created and is ready to handle events.
3. The filter/handback are configured.

With a Spring-managed MBeanExporter, the notification listener configuration can be coordinated by the exporter with the export lifecycle. When the context closes, the exporter performs cleanup for the registrations it manages.

### Why Not Add the Listener Manually Again?

If you both configure NotificationListenerBean in the exporter and call:

\`\`\`java
server.addNotificationListener(name, sameListener, null, null);
\`\`\`

then multiple registrations can exist for the same callback, leading to duplicate event handling. Choose one clear ownership mechanism.

### With Manual Registration

If you call addNotificationListener yourself, you must call removeNotificationListener in the corresponding lifecycle callback.

Example:

\`\`\`java
public void stop() throws Exception {
    server.removeNotificationListener(objectName, listener);
}
\`\`\`

Handle the case where the MBean has already been unregistered or the listener was not registered separately instead of letting shutdown fail entirely.

## 12. End-to-End Test with Spring

A simple program that creates the context and triggers notifications:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class SpringNotificationDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    QueueJmxConfiguration.class)) {

            QueueMonitor monitor =
                context.getBean(QueueMonitor.class);

            monitor.updateDepth(150);
            monitor.updateDepth(60);
        }
    }
}
\`\`\`

If the listener has no filter, the callback is expected to be invoked twice:

\`\`\`text
Queue event: learning.queue.overloaded
Queue event: learning.queue.recovered
\`\`\`

If using an overload-only filter, the callback is expected to be invoked once.

When implementing in a project, do not rely on exact timestamp/source strings because dynamic values may differ. Focus on event type, sequence, count, and verifying that the listener is attached to the right ObjectName.

## 13. Integration Test: Right MBean, Right Notification

A meaningful test should create two MBeans and one listener only for Primary.

Illustrative JUnit 5 example:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import java.util.concurrent.atomic.AtomicInteger;

import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class SpecificMBeanListenerTest {

    @Test
    void listenerReceivesOnlyPrimaryQueueEvents() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName primaryName = new ObjectName(
            "learning.jmx:type=Queue,name=Primary"
        );
        ObjectName secondaryName = new ObjectName(
            "learning.jmx:type=Queue,name=Secondary"
        );

        QueueMonitor primary = new QueueMonitor();
        QueueMonitor secondary = new QueueMonitor();

        server.registerMBean(primary, primaryName);
        server.registerMBean(secondary, secondaryName);

        AtomicInteger received = new AtomicInteger();

        NotificationListener listener =
            (notification, handback) -> received.incrementAndGet();

        server.addNotificationListener(
            primaryName,
            listener,
            null,
            null
        );

        try {
            primary.updateDepth(200);
            secondary.updateDepth(200);

            assertEquals(1, received.get());
        } finally {
            server.removeNotificationListener(primaryName, listener);
            server.unregisterMBean(primaryName);
            server.unregisterMBean(secondaryName);
        }
    }
}
\`\`\`

For an example broadcaster that dispatches callbacks synchronously by default, the event count assertion can come directly after sendNotification. If the application uses an asynchronous executor, a bounded await mechanism with a timeout is needed instead of assuming the notification has already been processed immediately when the operation returns.

### Testing in a Spring Context

With QueueJmxConfiguration, you can test:

1. Create an AnnotationConfigApplicationContext.
2. Verify \`server.isRegistered(primaryName)\`.
3. Trigger a notification via QueueMonitor.
4. Use a listener that records events into a test collector.
5. Verify only events from Primary are received.
6. Close the context and verify MBean/listener cleanup.

In environments where multiple tests run in parallel, use an isolated MBeanServer or partitioned ObjectNames to avoid conflicts with other tests.

## 14. Which MBeanServer Is the Right One?

One JVM can have multiple MBeanServers. If MBeanExporter uses a custom server:

\`\`\`java
exporter.setServer(customServer);
\`\`\`

then the listener must be registered in **customServer**, not another platform server.

Example:

\`\`\`java
MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer custom =
    MBeanServerFactory.createMBeanServer("custom.jmx");
\`\`\`

Registering the MBean in custom and then calling:

\`\`\`java
platform.addNotificationListener(name, listener, null, null);
\`\`\`

will find no MBean under that ObjectName on the platform server unless there is a separate registration there. An error such as InstanceNotFoundException can indicate that you are operating on the wrong server.

In a Spring application, choose the same server for both the exporter and listener registration, rather than creating a new server only on the listener side.

## 15. Remote JMX Listeners

A client in another JVM uses \`MBeanServerConnection\` from a JMXConnector:

\`\`\`java
MBeanServerConnection connection =
    connector.getMBeanServerConnection();

connection.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
\`\`\`

A remote connection path also depends on the JMX connector, permissions, TLS, network, and lifecycle. You should not open unauthenticated remote JMX just to test notifications.

For remote notifications:

- The client must connect to the right JVM and MBeanServer.
- Do not assume events are durably stored or replayed upon reconnection.
- When the connection is lost, you need a mechanism to detect it and re-register listeners according to operational requirements.
- Listener callbacks should process quickly and avoid prolonged blocking.
- Do not put secrets in Notification message, userData, or handback.
- If delivery guarantees are needed, consider a dedicated message broker/event stream.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Listener does not receive events | Registered with wrong ObjectName | Verify isRegistered and mappedObjectNames |
| InstanceNotFoundException | MBean not registered yet or wrong MBeanServer | Check lifecycle and server identity |
| MBean appears but emits no notifications | MBean does not support broadcaster or does not call sendNotification | Check implementation and getNotificationInfo |
| Listener receives Queue Secondary as well | mappedObjectNames configured too broadly or registered in two places | Check registrations |
| Listener does not receive recovered | Filter accepts only overload | Check filter |
| Listener processes same event twice | Listener added multiple times | Identify owner and clean up |
| Listener disappears after restart | MBean unregistered/recreated, old registration lost | Re-register when lifecycle requires |
| Event type is right but source is unfamiliar | Notification source differs from assumed ObjectName | Inspect getSource, check broadcaster/connector |
| Handback is always null | Listener registered with null handback | Provide context if needed |
| JConsole sees MBean but app does not receive events | JConsole and app registered on different servers/listeners | Confirm MBeanServer and callback |
| Remote listener stops receiving after reconnect | Registration depends on connection/lifecycle | Design re-registration and handle gaps |
| Shutdown reports ListenerNotFoundException | Removing an unregistered listener or removing twice | Track registration state and clean up properly |

## 17. Checklist When Registering a Specific Listener

Before putting a listener into your application:

1. **Is the MBean exported?** Check that the ObjectName exists in the right MBeanServer.
2. **Is the MBean a broadcaster?** Check NotificationBroadcaster/NotificationEmitter and metadata.
3. **Is the name exact?** mappedObjectNames must match the actual ObjectName.
4. **Is the source singular?** Are you avoiding accidentally listening to another MBean of the same type?
5. **Is the filter right?** Specify the types to receive.
6. **Is handback needed?** If needed, provide non-sensitive context.
7. **Is the callback lightweight?** Avoid long blocking tasks or re-entrant calls causing deadlocks.
8. **Is the listener thread-safe?** Notifications can arrive from multiple threads.
9. **Is it registered at the right lifecycle phase?** Do not miss important startup events due to late listener attachment.
10. **Is cleanup clear?** Remove the listener when the module/context stops.
11. **Are there duplicate registrations?** Avoid configuring Spring and manual calls at the same time.
12. **Is remote security ensured?** The connector must be secured.
13. **Are JMX boundaries tested?** Verify events arrive from the right MBean and with the right type.

## 18. Hands-On Exercises

### Exercise 1 — Select One MBean

Given three ObjectNames:

\`\`\`text
learning.jmx:type=Queue,name=Primary
learning.jmx:type=Queue,name=Secondary
learning.jmx:type=Cache,name=Products
\`\`\`

Write addNotificationListener code only for Queue Primary. Explain why filtering by overload type does not replace selecting the right ObjectName.

### Exercise 2 — Filter Overload

Create a NotificationFilter that accepts only \`learning.queue.overloaded\`. Trigger overload and recovery; confirm the callback receives only overload.

### Exercise 3 — Spring NotificationListenerBean

Configure Spring MBeanExporter with a listenerBean whose mappedObjectNames is Queue Primary. Then add Queue Secondary to the exporter without modifying mappedObjectNames. Verify the listener does not receive events from Secondary.

### Exercise 4 — Testing Cleanup

Register a listener manually, trigger an event, remove the listener, and trigger the event again. Confirm the callback count does not increase after removal. Use try/finally to clean up the MBean.

### Exercise 5 — Debugging Wrong Server

Create two MBeanServers A and B, and register QueueMonitor in A. Try addNotificationListener on B with the same ObjectName, observe the error, then fix it by using A. Explain the difference between ObjectName and MBeanServer identity.

## 19. Core Takeaways

- **Selecting an MBean by ObjectName** is the first step to scope the notification source.
- Spring \`NotificationListenerBean\` can use \`mappedObjectNames\` to attach a listener to a specific MBean.
- \`NotificationFilter\` restricts event types; it does not replace selecting the right broadcaster.
- The MBean must be registered and support notifications; having only a Spring bean or ObjectName is not enough.
- The target MBeanServer for the listener must be the MBeanServer holding the MBean.
- Listener registrations have their own lifecycle and require cleanup or management by the exporter.
- Do not assume JMX Notification has durable delivery/replay; for remote connections you must handle reconnection and security.
- Test metadata, source, type, lifecycle, and that events from other MBeans are not received.

## References

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — NotificationListenerBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/NotificationListenerBean.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — NotificationListener: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE 21 API — NotificationBroadcasterSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
