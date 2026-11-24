# Removing Listeners When Context Stops in Spring Framework JMX

## Learning Objectives

In JMX, a \`NotificationListener\` is registered to receive events emitted by MBeans. If a Spring application creates or attaches a listener during startup without removing it when \`ApplicationContext\` stops, leftover registrations can retain references to old beans, cause duplicate event delivery, hinder context restarts, and complicate shutdown.

After this lesson, you will be able to:

- Distinguish the lifecycles of \`NotificationListener\`, \`NotificationBroadcaster\`, \`MBeanServer\`, and \`ApplicationContext\`.
- Register and remove listeners using \`addNotificationListener\`/\`removeNotificationListener\`.
- Use \`@PreDestroy\`, \`DisposableBean\`, \`@Bean(destroyMethod=...)\`, or \`SmartLifecycle\` when listeners are managed by the application.
- Understand the role of Spring \`NotificationListenerBean\` and \`MBeanExporter\` when registering listeners declaratively.
- Design shutdown ordering to remove listeners before needed dependencies or the \`MBeanServer\` are released.
- Verify experimentally that listeners stop receiving notifications after the context closes.

## 1. Why Must Listeners Be Removed?

JMX provides a notification mechanism: an MBean can emit a \`javax.management.Notification\` when state changes, a threshold is crossed, a job finishes, or a management event occurs.

A listener implements the interface:

\`\`\`java
public interface NotificationListener {
    void handleNotification(
            Notification notification,
            Object handback);
}
\`\`\`

When using \`MBeanServer\`, registration typically looks like:

\`\`\`java
server.addNotificationListener(
        objectName, listener, filter, handback);
\`\`\`

This registration lives inside the MBean server/MBean broadcaster scope and can hold a reference to the listener. **Spring does not automatically know how to remove every listener that business code registers manually.** If the context closes while the server remains alive, the registration can retain the listener along with its prior dependencies, preventing expected garbage collection or processing events after application components have stopped.

Example problematic lifecycle:

\`\`\`text
JVM / platform MBeanServer: still running
    |
    +-- MBean emits notification
    |
    +-- Listener belonging to Spring ApplicationContext A
             |
             +-- Service or executor of context A
    |
ApplicationContext A closes
    |
    +-- Listener is not removed
    |
Context B creates a new listener
    |
    +-- Two listeners may remain registered
    +-- Notifications reach both listener A and B
\`\`\`

In some setups, the MBean is unregistered alongside the exporter and unregistration can sever notification paths tied to that registration. However, **do not rely on this indirect side effect** if the listener is registered against an MBean in a shared server, a platform MBean, or a component whose lifetime outlives the context.

## 2. Related JMX APIs

The JDK provides key overloads:

\`\`\`java
MBeanServer.addNotificationListener(
        ObjectName name,
        NotificationListener listener,
        NotificationFilter filter,
        Object handback);

MBeanServer.removeNotificationListener(
        ObjectName name,
        NotificationListener listener);

MBeanServer.removeNotificationListener(
        ObjectName name,
        NotificationListener listener,
        NotificationFilter filter,
        Object handback);
\`\`\`

**\`name\`** specifies the \`ObjectName\` of the registered broadcaster. **\`listener\`** is the object receiving notifications. **\`filter\`** can filter notifications by type or condition. **\`handback\`** is an object returned to the listener when notifications are processed.

The two removal forms have different semantics:

- The two-argument overload \`removeNotificationListener(name, listener)\` removes registrations of that listener on the corresponding broadcaster.
- The four-argument overload \`removeNotificationListener(name, listener, filter, handback)\` removes the registration matching the exact listener/filter/handback combination.

If the same listener is added multiple times with different filters or handbacks, choose the removal form suited to your goal. For a component to manage its subscription accurately, store the filter/handback used or ensure the listener has only one registration on the broadcaster.

Possible errors include \`InstanceNotFoundException\` if the \`ObjectName\` does not exist, and \`ListenerNotFoundException\` if the listener or parameter tuple matches no registration.

## 3. Distinguishing Three Registration Groups

A Spring JMX application can register listeners in several ways:

| Registration Type | Who Performs It | Who Should Clean Up |
| --- | --- | --- |
| \`MBeanServer.addNotificationListener\` called in business/config code | Custom component | That component itself or its lifecycle-managed bean |
| \`NotificationListenerBean\` supplied to \`MBeanExporter\` | Spring JMX exporter | Exporter manages registrations it creates per lifecycle |
| Remote \`MBeanServerConnection.addNotificationListener\` | JMX client in another JVM | Client/connector owner must close, remove, or reconnect per contract |

This lesson focuses on listeners **within the Spring application**. For exporter-managed listeners, leverage the exporter's lifecycle. For manually registered listeners, provide manual removal and test shutdown.

Do not confuse Spring Event's \`ApplicationListener<ContextClosedEvent>\` with JMX's \`javax.management.NotificationListener\`. They are two independent event systems, even though both can be used in the same application.

## 4. Example Notification-Emitting MBean

Create a broadcaster MBean using \`NotificationBroadcasterSupport\`.

**TaskEventsMBean.java**

\`\`\`java
package com.example.jmx;

public interface TaskEventsMBean {
    long getSequence();
    void emitTaskCompleted(String taskId);
}
\`\`\`

**TaskEvents.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class TaskEvents extends NotificationBroadcasterSupport
        implements TaskEventsMBean {

    public static final String TYPE = "com.example.task.completed";
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public long getSequence() {
        return sequence.get();
    }

    @Override
    public void emitTaskCompleted(String taskId) {
        long next = sequence.incrementAndGet();
        Notification notification = new Notification(
                TYPE, this, next,
                System.currentTimeMillis(),
                "Task completed: " + taskId);
        notification.setUserData(taskId);
        sendNotification(notification);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {TYPE};
        return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                        types,
                        Notification.class.getName(),
                        "Task completion notifications")
        };
    }
}
\`\`\`

\`TaskEvents\` is a Standard MBean because it implements \`TaskEventsMBean\`, while extending \`NotificationBroadcasterSupport\` to emit notifications.

The example uses a simple \`taskId\` string. In production, avoid putting secrets or sensitive personal data in \`userData\`, message, or handback because management and logging systems may record them.

## 5. Listener Recording Notifications

**TaskCompletionListener.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import javax.management.Notification;
import javax.management.NotificationListener;

public class TaskCompletionListener implements NotificationListener {
    private final AtomicInteger received = new AtomicInteger();

    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {

        if (TaskEvents.TYPE.equals(notification.getType())) {
            received.incrementAndGet();
            System.out.println("Received: "
                    + notification.getMessage());
        }
    }

    public int getReceivedCount() {
        return received.get();
    }
}
\`\`\`

This class simply counts events for easy testing. In a real application, a listener might push metrics, update caches, or run auxiliary logic. During shutdown, dependencies used by the listener (executors, repositories, queues...) may have already stopped; making timely listener removal even more important.

\`NotificationListener\` has no built-in \`close()\` or \`destroy()\` callback. The interface itself does not know who registered it, on which \`ObjectName\`, or with what filter/handback.

## 6. Approach 1 — Register Manually and Remove with @PreDestroy

A Spring bean lifecycle can manage the subscription itself.

**TaskNotificationSubscription.java**

\`\`\`java
package com.example.jmx;

import javax.annotation.processing.Generated;
import javax.management.MBeanServer;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;
import javax.management.ObjectName;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

public class TaskNotificationSubscription {

    private final MBeanServer server;
    private final ObjectName target;
    private final NotificationListener listener;
    private final NotificationFilter filter;
    private final Object handback;
    private boolean registered;

    public TaskNotificationSubscription(
            MBeanServer server,
            ObjectName target,
            NotificationListener listener) {
        this.server = server;
        this.target = target;
        this.listener = listener;
        this.filter = null;
        this.handback = null;
    }

    @PostConstruct
    public synchronized void start() throws Exception {
        if (!registered) {
            server.addNotificationListener(
                    target, listener, filter, handback);
            registered = true;
        }
    }

    @PreDestroy
    public synchronized void stop() throws Exception {
        if (registered) {
            try {
                server.removeNotificationListener(
                        target, listener, filter, handback);
            } finally {
                registered = false;
            }
        }
    }
}
\`\`\`

In Spring Framework 6+, the example uses \`jakarta.annotation\` corresponding to Jakarta EE annotations. If a project uses an older Spring Framework version, packages and dependencies may differ.

**Note:** the \`javax.annotation.processing.Generated\` import is unnecessary for the subscription; it is an annotation for generated source and unrelated to lifecycle. In real implementation code, only the used JMX and \`jakarta.annotation\` imports are needed. The example shows the lifecycle class to illustrate the \`PostConstruct\`/\`PreDestroy\` relationship.

There is a practical issue to solve: \`@PostConstruct\` runs when the subscription bean initializes, yet the exporter may **not have registered the MBean** into the server at that moment. If the listener subscription depends on an MBean created by \`MBeanExporter\`, design explicit initialization ordering, or use the exporter-managed approach in the next section. Use \`@DependsOn\` appropriately, or register listeners after context refresh completes.

## 7. Approach 2 — Using NotificationListenerBean with MBeanExporter

Spring Framework provides \`org.springframework.jmx.export.NotificationListenerBean\` to describe listeners configured with \`MBeanExporter\`.

Java configuration example:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class ExporterManagedNotificationConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public TaskEvents taskEvents() {
        return new TaskEvents();
    }

    @Bean
    public TaskCompletionListener completionListener() {
        return new TaskCompletionListener();
    }

    @Bean
    public MBeanExporter taskExporter(
            MBeanServer platformMBeanServer,
            TaskEvents taskEvents,
            TaskCompletionListener completionListener) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.task:type=TaskEvents,name=primary",
                taskEvents));

        NotificationListenerBean listenerBean =
                new NotificationListenerBean(completionListener);
        listenerBean.setMappedObjectName(
                "com.example.task:type=TaskEvents,name=primary");
        exporter.setNotificationListeners(listenerBean);
        return exporter;
    }
}
\`\`\`

When \`MBeanExporter\` both exports the MBean and manages the notification listener, it can organize registration and unregistration within the exporter's own lifecycle. This is usually simpler than creating a separate \`@PostConstruct\` subscription for an MBean that the exporter also owns.

\`NotificationListenerBean\` allows configuring filter, handback, and \`mappedObjectNames\` appropriately to scope source MBeans. When an application uses many MBeans, specify which listener receives notifications from which names instead of assuming it will automatically receive from only one MBean.

In a specific Spring version, setter/constructor APIs must be verified against the application's dependency version, especially when using other property mappings or notification filters.

## 8. Approach 3 — Using SmartLifecycle When Start/Stop Ordering Is Needed

For listeners that depend on an executor or must start after the exporter registers, \`SmartLifecycle\` is an option for controlling lifecycle phases.

**ManagedNotificationSubscriber.java**

\`\`\`java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

import org.springframework.context.SmartLifecycle;

public class ManagedNotificationSubscriber implements SmartLifecycle {

    private final MBeanServer server;
    private final ObjectName name;
    private final NotificationListener listener;

    private volatile boolean running;

    public ManagedNotificationSubscriber(
            MBeanServer server,
            ObjectName name,
            NotificationListener listener) {
        this.server = server;
        this.name = name;
        this.listener = listener;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }

        try {
            server.addNotificationListener(
                    name, listener, null, null);
            running = true;
        } catch (Exception e) {
            throw new IllegalStateException(
                    "Cannot register JMX listener", e);
        }
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }

        try {
            server.removeNotificationListener(
                    name, listener);
        } catch (Exception e) {
            throw new IllegalStateException(
                    "Cannot unregister JMX listener", e);
        } finally {
            running = false;
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
\`\`\`

Spring \`SmartLifecycle\` has phased start/stop. On start, lower phases generally start first; on stop, higher phases stop first. However, **the exporter is not necessarily a \`SmartLifecycle\`**. Therefore, phase alone does not guarantee the exporter has finished registering; understand how the exporter initializes during context refresh and use appropriate dependencies.

The example \`stop()\` throws a runtime exception when removal fails. In a real system, you may need to log and continue cleaning up other components; do not let one unremovable listener stall the entire shutdown or skip critical cleanup.

If you actually need to track asynchronous shutdown completion, use the \`stop(Runnable callback)\` overload and invoke the callback once stopping finishes; \`SmartLifecycle\` provides default behavior, yet for async tasks you should implement it explicitly.

## 9. A Simple Configuration with @DependsOn

If a listener subscription is created with \`@PostConstruct\`, it needs to see the broadcaster MBean already registered before calling \`addNotificationListener\`.

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

@Configuration
public class ManualListenerConfig {

    @Bean
    @DependsOn("taskExporter")
    public TaskNotificationSubscription subscription(
            MBeanServer platformMBeanServer,
            TaskCompletionListener completionListener)
            throws Exception {

        return new TaskNotificationSubscription(
                platformMBeanServer,
                new ObjectName(
                    "com.example.task:type=TaskEvents,name=primary"),
                completionListener);
    }
}
\`\`\`

Assume \`taskExporter\`, \`platformMBeanServer\`, and \`completionListener\` are already declared in the context. With \`@DependsOn("taskExporter")\`, Spring initializes the exporter before the subscription bean, and when destroying in dependency order, the subscription gets cleaned up before the exporter/server owner.

Avoid simultaneously using \`NotificationListenerBean\` in the exporter **and** a manual subscription for the same listener/MBean unintentionally. That can create two registrations and cause the listener to receive the same notification multiple times.

## 10. Is ContextClosedEvent Suitable for Removal?

Another approach is listening to \`ContextClosedEvent\`:

\`\`\`java
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;

public class ShutdownListener
        implements ApplicationListener<ContextClosedEvent> {

    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        // Remove JMX registration if this component owns the subscription.
    }
}
\`\`\`

However, \`ContextClosedEvent\` is a **Spring application event**; it is not equivalent to JMX's \`NotificationListener\`. If you both have \`@PreDestroy\` and listen to \`ContextClosedEvent\` to remove the same registration, design idempotency to avoid duplicate removal.

Usually it is best to pick one owner and one primary lifecycle hook. \`@PreDestroy\` or \`SmartLifecycle\` fits a bean encapsulating a subscription. \`ContextClosedEvent\` can be useful when reacting early as the context begins closing, but should not be overused merely to remove one listener.

## 11. Verifying the Listener Is Actually Removed

An effective test does not just call \`context.close()\` and assume cleanup worked. It should ensure an active broadcaster can still emit notifications after the context closes while the old listener no longer receives them.

Example fixture design:

\`\`\`text
Test-owned MBeanServer
    |
    +-- TaskEvents MBean registered by test owner
    |
Spring context A
    |
    +-- TaskCompletionListener
    +-- Subscription registered on TaskEvents MBean
    |
1. emit -> listener count = 1
2. close context A
3. emit -> listener count still = 1
4. create context B / listener B
5. emit -> listener B receives once, A does not
6. close context B and unregister TaskEvents
\`\`\`

The key point is that **the broadcaster must outlive the context being tested**. If the context owns and unregisters the broadcaster upon closing, you cannot emit another notification to prove the listener was removed because the source MBean has also disappeared.

For an isolated test, use a dedicated \`MBeanServer\` created with \`MBeanServerFactory.createMBeanServer\` and clean up with \`releaseMBeanServer\` when done.

## 12. Test Example with a Manually Managed Listener

The following JUnit snippet illustrates the removal-verification logic. The test creates the server and broadcaster outside the context, while the subscriber is started and closed by Spring.

\`\`\`java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class NotificationShutdownTest {

    @Test
    void listenerStopsReceivingAfterContextCloses() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("isolated-test");
        ObjectName name = new ObjectName(
                "com.example.task:type=TaskEvents,name=primary");

        TaskEvents broadcaster = new TaskEvents();
        server.registerMBean(broadcaster, name);

        TaskCompletionListener listener = new TaskCompletionListener();

        try {
            var context = new AnnotationConfigApplicationContext();
            context.registerBean(
                    "testMBeanServer",
                    MBeanServer.class,
                    () -> server);
            context.registerBean(
                    "completionListener",
                    TaskCompletionListener.class,
                    () -> listener);
            context.registerBean(
                    TaskNotificationSubscription.class,
                    () -> new TaskNotificationSubscription(
                            server, name, listener));
            context.refresh();

            try {
                broadcaster.emitTaskCompleted("task-1");
                assertEquals(1, listener.getReceivedCount());
            } finally {
                context.close();
            }

            broadcaster.emitTaskCompleted("task-2");
            assertEquals(1, listener.getReceivedCount(),
                    "Listener must be removed after context close");
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
\`\`\`

This example requires Spring to process \`@PostConstruct\` and \`@PreDestroy\` (with an appropriate \`jakarta.annotation-api\` dependency). To avoid that dependency in tests, you can declare the bean with \`initMethod\` and \`destroyMethod\` or use \`DisposableBean\`.

Note that \`NotificationBroadcasterSupport\` by default may dispatch notifications synchronously when no executor is supplied; if an asynchronous executor is configured, assertions must wait using an explicit synchronization mechanism rather than relying on arbitrary \`Thread.sleep\` calls.

## 13. Testing with MBeanExporter's NotificationListenerBean

When using an exporter-managed listener, the fixture should include:

- A \`TaskEvents\` MBean registered by the exporter.
- \`TaskCompletionListener\` configured via \`NotificationListenerBean\`.
- \`MBeanExporter\` with the corresponding \`notificationListeners\`.
- Closing \`ApplicationContext\` to trigger exporter cleanup.

The test should confirm the listener is attached while the context runs and no registrations remain after the exporter is destroyed. Since the broadcaster may be unregistered at the same time, you can build a fixture where the broadcaster outlives the context, though whether the exporter manages listeners attached to an MBean outside its mapping depends on Spring's supported mapping/listener configuration. Read the exact API and verify with an integration test.

Checking only the listener count while the context is running does not prove removal. You must check after closing or via a context-recreation test to detect duplicate registrations.

## 14. When a Listener Is Registered Multiple Times

JMX allows the same listener object to be added to a broadcaster multiple times, even with different filters/handbacks. Each registration can produce a callback invocation.

Example:

\`\`\`java
server.addNotificationListener(name, listener, filterA, "A");
server.addNotificationListener(name, listener, filterB, "B");
\`\`\`

When calling only:

\`\`\`java
server.removeNotificationListener(name, listener, filterA, "A");
\`\`\`

the registration with filter B and handback B can still remain. If you want to remove all registrations of that listener on that MBean name, use the two-argument overload:

\`\`\`java
server.removeNotificationListener(name, listener);
\`\`\`

However, removing all registrations requires proper ownership. If one listener object is shared across multiple modules, one module should not remove registrations belonging to another module. A safe approach is usually for each subscription owner to have its own listener/filter/handback and remove only what it created.

## 15. Shutdown Order: Listener, Exporter, Server

A design should clearly delineate:

\`\`\`text
ApplicationContext
    |
    +-- MBeanServer (may belong to JVM or be created by Spring factory)
    +-- MBeanExporter (registers MBeans)
    +-- NotificationSubscription (attaches listener)
    |
    v
Shutdown
    1. Prevent creating new subscriptions
    2. Remove context-owned listeners
    3. Stop notification-processing executor in proper order
    4. Unregister MBeans managed by exporter
    5. Release custom MBeanServer if owned by context
\`\`\`

If listener callbacks use an executor, you sometimes need to stop receiving notifications **before** shutting down the executor. If the executor has already stopped while the listener remains registered, callbacks may still try to submit tasks to the executor and receive \`RejectedExecutionException\`.

When \`TaskNotificationSubscription\` injects or uses \`@DependsOn\` on the exporter/server, Spring knows the dependency relationship and can perform destruction in reverse dependency order. For a server borrowed from the JVM, the context should not release that server.

## 16. Handling Cleanup Errors

During shutdown, \`removeNotificationListener\` can fail if:

- The MBean has already been unregistered by the exporter or another component.
- The listener was never successfully registered.
- The registration was already removed by another path.
- The server name or \`ObjectName\` no longer matches.
- The remote connection dropped (for remote JMX clients).

An implementation can catch exceptions and log at an appropriate level:

\`\`\`java
public synchronized void stopSafely() {
    if (!registered) {
        return;
    }

    try {
        server.removeNotificationListener(
                target, listener, filter, handback);
    } catch (javax.management.InstanceNotFoundException
            | javax.management.ListenerNotFoundException ex) {
        // MBean/listener may already have been cleaned up by another owner.
        // Log if needed; verify the actual lifecycle.
    } finally {
        registered = false;
    }
}
\`\`\`

This example illustrates intentional cleanup, not a recommendation to ignore all errors. In particular, if removal fails due to connection or permission issues, the listener may still remain in the registry; do not record a "removed successfully" status without evidence.

For a subscription tracking a \`registered\` flag, setting \`false\` in \`finally\` is a lifecycle choice: it prevents repeated removal attempts, yet can mask a lingering registration if removal genuinely failed. In production, distinguish **remove success**, **registration already gone**, and **unverified removal** with clear logs or states.

## 17. Listeners Using a Remote MBeanServerConnection

When a listener is attached to an MBean in another JVM, code can obtain \`MBeanServerConnection\` from \`JMXConnector\`:

\`\`\`java
MBeanServerConnection connection =
        connector.getMBeanServerConnection();

connection.addNotificationListener(
        objectName, listener, null, null);
\`\`\`

When stopping:

\`\`\`java
connection.removeNotificationListener(
        objectName, listener);
connector.close();
\`\`\`

If a listener remains registered when the connector closes or the server disconnects, its state may depend on the protocol/session. Do not rely on disconnecting to assume all subscriptions were cleaned up per application logic; remove the listener while the connection is still valid and close the connector in \`finally\` when needed.

Remote notification listeners also involve latency, reconnection, and duplicate delivery issues. When re-registering after reconnecting, ensure you do not accidentally create multiple registrations on the same server.

## 18. Differences from Spring ApplicationListener

Both concepts share the word "listener," but they are not equivalent:

| Concept | System | Registration | Cleanup |
| --- | --- | --- | --- |
| \`NotificationListener\` | Java JMX | \`MBeanServer.addNotificationListener\` | \`removeNotificationListener\` or exporter lifecycle |
| \`ApplicationListener<ContextClosedEvent>\` | Spring Events | Spring \`ApplicationEventMulticaster\` | Follows Spring event registration lifecycle |
| \`@EventListener\` | Spring Events | Container discovers listener methods | Container manages registration per context |
| \`NotificationListenerBean\` | Spring JMX export | Attached to \`MBeanExporter\` | Managed by exporter when configured properly |

An \`@EventListener\` does not automatically register a JMX notification listener. Similarly, a JMX \`NotificationListener\` does not automatically receive Spring application events without an explicit bridge.

## 19. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Listener receives notifications twice after context restart | Old subscription was not removed | Remove in lifecycle hook, check owner |
| Context closed yet bean stays in heap | MBean server still holds reference to listener | Use heap analysis and inspect registrations |
| \`ListenerNotFoundException\` on stop | Wrong listener/filter/handback removed or already removed | Store exact registration params, make cleanup idempotent |
| \`InstanceNotFoundException\` on stop | MBean was already unregistered | Design destroy order or handle already-gone case |
| Startup error when adding listener | Exporter has not registered broadcaster yet | Use exporter-managed listener or lifecycle dependency |
| Callback runs after executor has shut down | Listener removed too late | Stop callback source before executor |
| JConsole does not show notifications | Connected to wrong JVM/MBean or broadcaster lacks metadata | Check right server, \`MBeanInfo\`, and notification types |
| Test passes alone but fails in suite | Tests share platform server/registration | Use isolated MBean server and names for fixtures |
| Listener receives no events | Filtered out, wrong \`ObjectName\`, broadcaster does not emit | Check filter, handback, and source MBean |
| Spring bean destroyed yet still receives callbacks | Registration outlived context | Check \`@PreDestroy\`, \`SmartLifecycle\`, and cleanup order |

## 20. Designing Subscriptions with Clear Ownership

A reusable pattern is creating a bean responsible for the entire subscription lifecycle:

\`\`\`text
JmxSubscription
  - MBeanServerConnection server
  - ObjectName target
  - NotificationListener listener
  - NotificationFilter filter
  - Object handback
  - registrationState
  + start()
  + stop()
\`\`\`

This pattern provides several benefits:

1. Avoids scattering \`addNotificationListener\` across multiple service methods.
2. Only one owner knows how the registration was created and how to remove it.
3. Can check state and avoid duplicate registrations.
4. Easy to define dependency relationships with the exporter/server.
5. Easy to test when the context closes.
6. Easy to extend with controlled retry/reconnect logic for remote JMX.

When business services do not need to know about JMX, keep the subscription as an adapter in the monitoring/management layer instead of mixing lifecycle code into business services.

## 21. Hands-On Exercises

**Exercise 1 — Single listener:** create \`TaskEvents\`, \`TaskCompletionListener\`, and a subscription. Emit a notification before closing the context and assert the count increases; close the context and emit again from an external broadcaster, asserting the count does not increase.

**Exercise 2 — Duplicate registrations:** register the same listener twice with two different handbacks. Observe the callback count; try removing only one registration and then removing all. Explain the difference between the two removal overloads.

**Exercise 3 — Lifecycle order:** create an exporter-managed broadcaster and an independent \`@PostConstruct\` subscription. Observe adding too early, then use \`@DependsOn\` or switch to \`NotificationListenerBean\` and verify the result.

**Exercise 4 — SmartLifecycle:** create a subscriber with phase 100 and an executor-managed bean with a lower phase, and inspect the stop sequence. Explain why the subscriber should stop receiving notifications before the executor stops.

**Exercise 5 — Restart test:** start context A and close it; start context B using the same external broadcaster. Emit a notification and verify listener A receives nothing while listener B receives it once.

**Exercise 6 — Remote JMX:** design a client using \`JMXConnector\` and \`MBeanServerConnection\`. Describe a strategy for removing the listener before \`connector.close()\` and handling a lost connection during shutdown.

## Conclusion

**Removing listeners when \`ApplicationContext\` stops** is an important responsibility for Spring applications using JMX notifications. Listeners can be attached via \`MBeanServer.addNotificationListener\` or configured alongside \`MBeanExporter\` using \`NotificationListenerBean\`. If a subscription is created manually by the application, encapsulate it in a bean with a clear lifecycle and call \`removeNotificationListener\` before its dependencies or the server owner are cleaned up. Checking only that the context closes is not enough; a good test proves the listener **stops receiving notifications** from a still-living broadcaster after the context stops.
