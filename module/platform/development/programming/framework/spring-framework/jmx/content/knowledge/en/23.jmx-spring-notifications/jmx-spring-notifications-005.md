# notificationListeners and NotificationListenerBean in Spring JMX

## 1. Objectives

JMX Notification is a mechanism for an MBean to **proactively emit management events** when state changes, instead of forcing clients to continuously poll attributes. Spring Framework supports registering JMX listeners through `MBeanExporter`, specifically the `notificationListeners` property and the `NotificationListenerBean` class.

This lesson focuses on using `NotificationListenerBean` to bind a `NotificationListener` to specific MBeans, configure `NotificationFilter` and `handback`, organize the registration/unregistration lifecycle, and test against a real `MBeanServer`.

After studying this, you should be able to distinguish:

- **Notification-emitting MBean**: an object implementing the `NotificationBroadcaster` or `NotificationEmitter` mechanism.
- **NotificationListener**: callback receiving emitted `Notification`s.
- **NotificationListenerBean**: Spring configuration wrapping a listener along with filter, handback, and the list of MBeans to listen to.
- **MBeanExporter.notificationListeners**: list of listener registrations managed by the exporter during MBean registration.
- **Mapped ObjectName**: the listener registration target, not a Java bean name used for invoking business methods.

## 2. Where Do Notifications Flow From and To?

A basic flow:

```text
Spring ApplicationContext
  |
  +-- Managed bean / NotificationPublisherAware
  |         |
  |         v
  |    Exported MBean
  |         |
  |         v
  |    MBeanServer
  |         |
  |    Notification from MBean
  |         |
  |         v
  +-- MBeanExporter.notificationListeners
            |
            v
      NotificationListenerBean
         |       |        |
      listener  filter  handback
         |
         v
    handleNotification(...)
```

In an annotation-driven Spring case, a bean can use `NotificationPublisherAware` to receive a `NotificationPublisher` and then emit events. Another approach is a standard MBean directly using `NotificationBroadcasterSupport` from the JMX API.

Key point: `NotificationListenerBean` **does not turn an arbitrary bean into a notification source**. It only registers listeners with MBeans capable of emitting notifications. If the MBean is not a `NotificationBroadcaster`, listener registration may fail under JMX rules.

## 3. Core JMX Components

### 3.1. Notification

`javax.management.Notification` carries event metadata:

- `type`: event classification string, e.g., `com.example.jobs.worker.paused`.
- `source`: event source.
- `sequenceNumber`: sequence number managed by the emitter.
- `timeStamp`: emission timestamp.
- `message`: short description.
- `userData`: additional payload if any.

Example:

```java
import javax.management.Notification;

Notification notification = new Notification(
    "com.example.jobs.worker.paused",
    this,
    17L,
    System.currentTimeMillis(),
    "Worker paused by administrator"
);
```

Do not put passwords, tokens, customer data, or sensitive object graphs into `message` or `userData`. Notifications can traverse a remote JMX connector if the system allows remote clients to register listeners.

### 3.2. NotificationListener

A listener is the JMX callback:

```java
import javax.management.Notification;
import javax.management.NotificationListener;

public final class WorkerEventListener
        implements NotificationListener {

    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {

        System.out.println(
            "type=" + notification.getType() +
            ", sequence=" + notification.getSequenceNumber() +
            ", handback=" + handback
        );
    }
}
```

Callbacks should execute quickly, avoid holding business locks for long, and avoid throwing exceptions that disrupt the emitter's dispatch path. If time-consuming event processing is needed, offload work to an executor with a bounded queue and an explicit backpressure policy.

### 3.3. NotificationFilter

`NotificationFilter` decides which notifications reach the listener:

```java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter pausedOnly =
    (Notification n) ->
        "com.example.jobs.worker.paused".equals(n.getType());
```

Filters fit when one MBean has multiple notification types but a listener only needs a subset. A filter differs from selecting an ObjectName: **ObjectName selects the emitter**, while the filter selects **the event types from that emitter**.

## 4. NotificationBroadcasterSupport: A Sample Event Source

Create a Standard MBean that emits events:

```java
package com.example.jobs.jmx;

public interface WorkerControlMBean {
    boolean isPaused();
    void pause();
    void resume();
}
```

Implementation:

```java
package com.example.jobs.jmx;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public final class WorkerControl
        extends NotificationBroadcasterSupport
        implements WorkerControlMBean {

    private final AtomicBoolean paused = new AtomicBoolean();
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void pause() {
        if (paused.compareAndSet(false, true)) {
            publish("com.example.jobs.worker.paused",
                    "Worker is paused");
        }
    }

    @Override
    public void resume() {
        if (paused.compareAndSet(true, false)) {
            publish("com.example.jobs.worker.resumed",
                    "Worker is resumed");
        }
    }

    private void publish(String type, String message) {
        Notification event = new Notification(
            type,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            message
        );
        sendNotification(event);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] {
                    "com.example.jobs.worker.paused",
                    "com.example.jobs.worker.resumed"
                },
                Notification.class.getName(),
                "Worker lifecycle state changes"
            )
        };
    }
}
```

`NotificationBroadcasterSupport` handles listener registration and notification sending; `WorkerControlMBean` defines the Standard MBean attributes/operations.

In an environment where multiple threads call `pause`/`resume`, the sequence counter is unique and increments via `AtomicLong`. However, if notifications are emitted from another source, ensure consistent per-emitter sequence conventions.

## 5. Spring MBeanExporter and notificationListeners

`MBeanExporter` provides a property for registering `NotificationListenerBean` instances:

```java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

MBeanExporter exporter = new MBeanExporter();

NotificationListenerBean registration =
    new NotificationListenerBean();

registration.setNotificationListener(
    new WorkerEventListener()
);

exporter.setNotificationListeners(registration);
```

This is a condensed configuration to illustrate the API; the exporter still needs appropriate MBean selection and server setup. If you do not specify which MBeans to listen to, the behavior and matching scope must be checked against the Spring API version in use. In an application with many MBeans, **configure the ObjectName list explicitly** to avoid accidentally receiving events from unrelated sources.

`notificationListeners` is an exporter configuration property: do not confuse it with `NotificationListener` as a callback, and do not treat it as a notification registry independent of JMX.

## 6. Configuring a Listener for a Specific ObjectName

Complete Spring Java config example with a Standard MBean:

```java
package com.example.jobs.config;

import com.example.jobs.jmx.WorkerControl;
import com.example.jobs.jmx.WorkerEventListener;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class WorkerJmxConfig {

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public WorkerEventListener workerEventListener() {
        return new WorkerEventListener();
    }

    @Bean
    public MBeanExporter workerExporter(
            MBeanServer server,
            WorkerControl control,
            WorkerEventListener listener) throws Exception {

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        );

        NotificationListenerBean registration =
            new NotificationListenerBean();

        registration.setNotificationListener(listener);
        registration.setMappedObjectNames(name);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(name.toString(), control));
        exporter.setNotificationListeners(registration);
        return exporter;
    }
}
```

This pattern expresses the intent: the exporter registers the MBean under a specific ObjectName and registers the listener for that exact ObjectName.

Note that Spring has overloads/mappings for `setMappedObjectNames` and may accept `ObjectName` or `String` names depending on the version. When using your project's Spring Framework version, check the actual API; for example, using `ObjectName` as the target name avoids arbitrary string parsing.

If Spring Boot has already created an exporter via auto-configuration, do not add another exporter that also exports `WorkerControl` without checking ownership and collisions. A context with two exporters writing the same `ObjectName` to the platform server may encounter `InstanceAlreadyExistsException`.

## 7. How Does ObjectName Mapping Work?

`NotificationListenerBean` has a list of **mapped object names**; only the matching MBeans get the listener attached by the exporter. Example:

```java
ObjectName primary = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

ObjectName secondary = new ObjectName(
    "com.example.jobs:type=Worker,name=Secondary"
);

registration.setMappedObjectNames(primary, secondary);
```

When the exporter processes MBeans within its export scope, the listener is registered for matching names. One listener can receive notifications from multiple MBeans; the callback should read `notification.getSource()` or identify the source with appropriate metadata to distinguish them.

If you need an event type only from Primary, do not filter solely by `type` because Secondary may emit the same type. Restrict by ObjectName and also filter by type if needed.

With dynamic ObjectNames, validate canonical names and do not use wildcards arbitrarily without confirming the mapping mechanism supports pattern matching as intended. `*` or `?` in JMX can create an ObjectName pattern rather than a single identity.

## 8. NotificationFilter and Handback in NotificationListenerBean

A registration can provide a filter and handback:

```java
import javax.management.NotificationFilter;
import org.springframework.jmx.export.NotificationListenerBean;

NotificationFilter filter = event ->
    "com.example.jobs.worker.paused".equals(event.getType());

NotificationListenerBean registration =
    new NotificationListenerBean();

registration.setNotificationListener(listener);
registration.setNotificationFilter(filter);
registration.setHandback("operations-audit");
registration.setMappedObjectNames(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
);
```

In the callback:

```java
@Override
public void handleNotification(
        Notification notification, Object handback) {

    if ("operations-audit".equals(handback)) {
        // Handle audit branch.
    }
}
```

**Handback** is an object supplied by the listener registrar and returned when a notification arrives. It is not the `userData` placed in the Notification by the emitter.

This is especially useful when the same listener is registered on multiple sources:

```text
Emitter A --listener/filter/handback="cluster-a"--> callback
Emitter B --listener/filter/handback="cluster-b"--> callback
```

Do not pass a large object holding references to the entire `ApplicationContext` as handback unless genuinely necessary, because the registration can retain that reference for its lifetime and complicate cleanup.

## 9. MappedObjectNames and Autodetection

If the exporter uses autodetection to locate MBeans, understand the listener scope:

- The exporter may discover eligible application beans to register.
- The naming strategy decides the final ObjectName.
- NotificationListenerBean is attached according to the mapped object names.
- If the actual name differs from the expected name, the listener may fail to attach even though the MBean exported successfully.

Annotation-driven example:

```java
@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary"
)
public class WorkerManagementAdapter {
    // ...
}
```

If the naming strategy or multi-context setup adds an `instance` key, the final ObjectName may differ; listener mapping using a static name will no longer match.

To diagnose, print `server.queryNames(...)` and compare the canonical ObjectName with the list configured for the listener. Do not assume the Spring bean ID is automatically the ObjectName.

## 10. NotificationPublisherAware in Spring

Spring also supports a notification-emitting path for managed beans: implement `NotificationPublisherAware` to receive a publisher when the bean is exported properly.

Example:

```java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

public final class JobNotificationSource
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    public void reportJobCompleted(String jobId) {
        Notification event = new Notification(
            "com.example.jobs.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Job completed"
        );
        publisher.sendNotification(event);
    }
}
```

This snippet assumes the exporter lifecycle has already injected `NotificationPublisher` before `reportJobCompleted` is called. In a real system, guard against the publisher not being ready yet, especially if the bean is used before JMX registration or while the context is shutting down.

`NotificationPublisherAware` is on the **emitter side**; `NotificationListenerBean` is on the **subscriber side**. The two abstractions complement each other rather than replacing each other.

## 11. MBeanInfo and Notification Metadata

An MBean may emit notifications, yet clients need to know which event types are published. You can inspect metadata:

```java
MBeanInfo info = server.getMBeanInfo(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
);

for (var notification : info.getNotifications()) {
    System.out.println(notification.getName());

    for (String type : notification.getNotifTypes()) {
        System.out.println("  " + type);
    }
}
```

If notification metadata is empty, it may reflect an emitter configuration that does not declare types, even if application code has emission logic elsewhere. Check the MBean type, `getNotificationInfo()`, or the Spring metadata used by the exporter.

Do not use `MBeanInfo.getOperations()` to infer notification types: operations and notifications are two independent parts of the MBean contract.

## 12. Removing Listeners Properly in the Lifecycle

When registering listeners via `MBeanExporter.notificationListeners`, the exporter can manage removing the registrations it owns according to the Spring context lifecycle. This is a major benefit compared to manual registration where cleanup is easily forgotten.

With direct registration:

```java
server.addNotificationListener(
    name, listener, filter, handback
);
```

you must remove it by matching identity:

```java
server.removeNotificationListener(
    name, listener, filter, handback
);
```

`removeNotificationListener` has multiple overloads; the three-part listener/filter/handback overload removes only an exact matching registration. If the same listener was registered multiple times with different filters or handbacks, choose the right overload so you do not remove the wrong registration.

When an app redeploys and an old listener remains retained in the MBeanServer or broadcaster, it can hold a reference to the previous deployment's classloader. Cleanup is therefore an operational requirement, not an optional code-tidying exercise.

## 13. Testing Directly with MBeanServer

A test using an isolated server and a Standard MBean:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class JmxNotificationTest {

    @Test
    void listenerReceivesPauseNotification() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("listener-test");

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        );

        WorkerControl emitter = new WorkerControl();
        BlockingQueue<Notification> events =
            new LinkedBlockingQueue<>();

        NotificationListener listener =
            (event, handback) -> events.add(event);

        try {
            server.registerMBean(emitter, name);
            server.addNotificationListener(
                name, listener, null, "unit-test"
            );

            server.invoke(
                name, "pause", new Object[0], new String[0]
            );

            Notification received =
                events.poll(2, TimeUnit.SECONDS);

            assertNotNull(received);
            assertEquals(
                "com.example.jobs.worker.paused",
                received.getType()
            );
        } finally {
            try {
                server.removeNotificationListener(name, listener);
            } catch (Exception ignored) {
                // May not have been registered or MBean already removed.
            }

            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }

            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

The test above verifies JMX's notification mechanism. It **does not test Spring NotificationListenerBean wiring**, because the listener is added directly to the server. A Spring integration test must create a context containing the exporter, listener bean, and MBean, then trigger the event to prove the actual wiring works.

Use `BlockingQueue` and a timeout instead of a fixed `Thread.sleep` to avoid test flakiness from scheduling. If the callback processes asynchronously, the wait timeout should fit the test environment without masking configuration bugs.

## 14. Integration Testing NotificationListenerBean Configuration

With a Spring context, verify:

1. Context starts and the MBean is registered under the expected ObjectName.
2. `NotificationListenerBean` is picked up by the exporter.
3. Invoking an operation generates a notification.
4. The listener receives the exact type and handback.
5. Triggering an event blocked by the filter does not deliver it to the listener.
6. If multiple MBeans exist, events from ObjectNames outside the mapped list are not received.
7. Closing the context causes the exporter to clean up registrations it owns.
8. Creating a new context or redeploying yields no duplicate callbacks from old listeners.

Example checking a filter with a queue:

```java
BlockingQueue<Notification> events =
    new LinkedBlockingQueue<>();

NotificationFilter pausedOnly =
    e -> "com.example.jobs.worker.paused".equals(e.getType());

NotificationListener listener =
    (e, handback) -> events.add(e);
```

After calling `resume`, the queue should not receive a `resumed` notification; after `pause`, it must receive a `paused` notification. Avoid tests that assert only event count without checking type/sequence/source, because events might arrive from another MBean.

## 15. Common Errors

| Symptom | Likely Cause | How to Investigate |
| --- | --- | --- |
| MBean exists but listener receives nothing | Wrong mapped ObjectName or emitter does not emit | `isRegistered`, `queryNames`, emitter logs |
| Startup error when attaching listener | MBean does not support notifications | Check `NotificationBroadcaster` or adapter |
| Unexpected notifications also received | Filter not configured or filter too broad | Check `NotificationFilter` |
| Listener receives duplicates after redeploy | Old registration was not removed | Check exporter/context lifecycle |
| Handback is `null` | Registration did not set handback | Check `setHandback` |
| Wrong source with multiple MBeans | MappedObjectNames too broad | Narrow down ObjectNames |
| Event received locally but not by remote client | Different remote connector/listener registration | Check connection, reconnect logic |
| MBeanInfo does not list event types | Emitter does not publish notification metadata | `getNotificationInfo`, `getMBeanInfo` |
| Listener slows down the application | Heavy or blocking callback | Move processing to a bounded executor |

A notification listener should not be used in place of a message broker with guaranteed delivery. JMX Notifications do not provide the full durability, replay, and delivery guarantee semantics of a dedicated messaging system.

## 16. Security and Performance Principles

A notification sent via JMX can be observed by remote clients if the connector permits it. Therefore:

- Do not put sensitive data in `Notification.message` or `userData`.
- Define types with clear namespaces: `com.example.jobs.worker.paused`.
- Keep notification payloads small; do not serialize large domain objects.
- Use consistent sequence numbers and timestamps.
- Filter at the appropriate place; listener-side filtering does not replace server-side authorization.
- Do not call a database or remote service synchronously inside a listener if avoidable.
- Bound queues when fanning out or dispatching asynchronously to prevent memory growth.
- Design for idempotency if the listener triggers processing with side effects.
- Protect remote JMX connectors with authentication, TLS, and network isolation.

If notifications have very high frequency, dedicated metrics or event streaming may be more suitable than sending every small change over JMX.

## 17. Comparing Spring-Registered vs. Manually Registered Listeners

| Criterion | `NotificationListenerBean` via Exporter | `MBeanServer.addNotificationListener` |
| --- | --- | --- |
| Configuration location | Spring `ApplicationContext` | Explicit Java code |
| MBean selection | Mapped ObjectNames | ObjectName passed in call |
| Filter | `setNotificationFilter` | Filter argument |
| Handback | `setHandback` | Handback argument |
| Lifecycle | Can be managed by the exporter | Caller must clean up registration |
| Testing | Spring integration context | JMX unit/integration test |
| Purpose | Declarative listener configuration | Dynamic registration by runtime logic |

You do not have to use a Spring listener bean for every case. When listeners must be registered/unregistered dynamically per session, the direct API can be clearer. When a fixed listener is part of application management configuration, `NotificationListenerBean` ties ownership into the context.

## 18. Implementation Workflow

1. Identify which MBeans emit notifications and the expected event types.
2. Publish notification metadata on the emitter; inspect `MBeanInfo` when needed.
3. Register MBeans via the exporter on an identified `MBeanServer`.
4. Create a fast and safe `NotificationListener`.
5. Create a `NotificationListenerBean`, setting listener, filter, handback, and mapped ObjectNames.
6. Attach the registration to `MBeanExporter.notificationListeners`.
7. Start the context and verify the actual ObjectName.
8. Trigger events in a test environment and inspect type/source/sequence/handback.
9. Close the context and verify no duplicate callbacks or leftover registrations remain.
10. Test reconnect/redeploy if there is a JMX remote client or multi-lifecycle context.

## 19. Takeaways

**`NotificationListenerBean` is Spring's configuration model for JMX listeners; `MBeanExporter.notificationListeners` attaches those registrations during MBean export.** A registration consists of a listener callback, filter, handback, and the set of ObjectNames to observe. It does not create notification sources by itself, does not replace security, and does not guarantee durable event delivery. To build a reliable system, use exact ObjectNames, test emitting/receiving notifications on a real `MBeanServer`, and remove listeners properly with the Spring context lifecycle.
