# Practice: Emitting and Receiving AttributeChangeNotification in Spring Framework JMX

## 1. Lab Objectives

In Java Management Extensions (JMX), an MBean not only supports reading/writing attributes or invoking operations; it can also **emit notifications** when state changes. `AttributeChangeNotification` is the standard notification for an attribute value change event. Spring Framework can export beans as JMX MBeans while also supporting sending and receiving notifications using Spring JMX components.

This lab builds a management bean with an `Enabled` property, emits an `AttributeChangeNotification` when the value changes, and registers a `NotificationListener` to receive and verify the event payload.

After this lesson, you will be able to:

- Explain how notifications differ from polling `getAttribute`.
- Identify the key fields of `AttributeChangeNotification`: `source`, `sequenceNumber`, `timestamp`, `message`, `attributeName`, `attributeType`, `oldValue`, and `newValue`.
- Configure an MBean capable of emitting notifications via `NotificationBroadcasterSupport` or Spring's `NotificationPublisher`.
- Register a listener with `MBeanServer.addNotificationListener`.
- Perform a state change via JMX and observe the notification.
- Write tests that assert notification contents without relying on arbitrary sleep durations.
- Handle listener lifecycle, filters, event ordering, and sensitive data risks.

## 2. How Do Notifications Differ from Attributes?

Attributes and notifications both live on an MBean, but serve two different goals:

| Mechanism | Purpose | Usage |
| --- | --- | --- |
| Attribute | View state at read time | `getAttribute(ObjectName, "Enabled")` |
| Writable attribute | Request a state change | `setAttribute(ObjectName, Attribute)` |
| Notification | Signal that an event occurred | Listener receives callback |
| `AttributeChangeNotification` | Describe an attribute value change event | Listener reads old/new values |

Example:

```text
Initial state: Enabled=true
Client calls setAttribute(Enabled=false)
            |
            v
Bean changes state true -> false
            |
            v
Emits AttributeChangeNotification
            |
            v
NotificationListener receives:
  attributeName=Enabled
  oldValue=true
  newValue=false
```

Notifications are not database transactions, durable messages, or self-healing event logs. A late-subscribing client can miss earlier notifications; a client can also lose events when a connection drops. Therefore, to synchronize state, a listener should typically **read an initial snapshot** and continue listening for changes, combined with a resync mechanism if needed.

## 3. Structure of AttributeChangeNotification

Standard class:

```java
javax.management.AttributeChangeNotification
```

An instance is constructed with:

```java
new AttributeChangeNotification(
    source,
    sequenceNumber,
    timestamp,
    message,
    attributeName,
    attributeType,
    oldValue,
    newValue
);
```

Meaning:

| Parameter | Meaning |
| --- | --- |
| `source` | Event source, typically the MBean or ObjectName |
| `sequenceNumber` | Sequence number managed by the emitter |
| `timestamp` | Emission time in milliseconds since epoch |
| `message` | Description of the event |
| `attributeName` | Attribute name exposed in JMX |
| `attributeType` | Java type name of the attribute |
| `oldValue` | Value before the change |
| `newValue` | Value after the change |

Standard type constant:

```java
AttributeChangeNotification.ATTRIBUTE_CHANGE
```

Listeners can check `notification.getType()` against this constant. `AttributeChangeNotification` extends `Notification`, so it also has common fields such as `getSequenceNumber()`, `getTimeStamp()`, `getMessage()`, and `getSource()`.

### 3.1. Example notification creation

```java
import javax.management.AttributeChangeNotification;

AttributeChangeNotification event =
    new AttributeChangeNotification(
        this,
        1L,
        System.currentTimeMillis(),
        "Enabled changed",
        "Enabled",
        "boolean",
        Boolean.TRUE,
        Boolean.FALSE
    );
```

The string `"Enabled"` should match the **JMX attribute name**, not necessarily the Java field name. With getter `isEnabled()`, the management name is typically `Enabled`. `attributeType` must reflect the type declared in JMX metadata.

## 4. Approach A: Standard MBean Emitting Notifications

To understand foundational JMX first, start with a Standard MBean using `NotificationBroadcasterSupport`. Then move to the Spring exporter.

Define the management interface:

```java
package com.example.jmx;

public interface FeatureSwitchMBean {
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
```

Implementation class:

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.AttributeChangeNotification;
import javax.management.MBeanNotificationInfo;
import javax.management.NotificationBroadcasterSupport;

public class FeatureSwitch
        extends NotificationBroadcasterSupport
        implements FeatureSwitchMBean {

    private final AtomicLong sequence = new AtomicLong();
    private boolean enabled = true;

    @Override
    public synchronized boolean isEnabled() {
        return enabled;
    }

    @Override
    public synchronized void setEnabled(boolean next) {
        boolean previous = enabled;

        if (previous == next) {
            return;
        }

        enabled = next;

        AttributeChangeNotification event =
            new AttributeChangeNotification(
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Feature switch changed",
                "Enabled",
                "boolean",
                previous,
                next
            );

        sendNotification(event);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {
            AttributeChangeNotification.ATTRIBUTE_CHANGE
        };

        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                AttributeChangeNotification.class.getName(),
                "Emitted when Enabled changes"
            )
        };
    }
}
```

This code provides three parts:

1. `FeatureSwitchMBean`: attribute getter/setter contract for the Standard MBean.
2. `NotificationBroadcasterSupport`: dispatches events to registered listeners.
3. `getNotificationInfo()`: describes notification types in metadata for client discovery.

Marking `setEnabled` as `synchronized` keeps the example's read/update pair consistent. However, invoking listeners synchronously while holding a lock can cause issues if a listener is slow or reentrant. In production, evaluate the broadcaster's executor strategy and avoid letting external callbacks extend critical sections.

## 5. Registering and Receiving Notifications with MBeanServer

You can register the Standard MBean directly into an isolated server for the lab:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server =
    MBeanServerFactory.newMBeanServer("com.example.lab");

ObjectName name = new ObjectName(
    "com.example.lab:type=FeatureSwitch,name=Main"
);

FeatureSwitch bean = new FeatureSwitch();
server.registerMBean(bean, name);
```

Register a listener:

```java
import javax.management.AttributeChangeNotification;
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification change) {
        System.out.println("Changed: " + change.getAttributeName());
        System.out.println("Old: " + change.getOldValue());
        System.out.println("New: " + change.getNewValue());
        System.out.println("Sequence: " + change.getSequenceNumber());
    }
};

server.addNotificationListener(name, listener, null, null);
```

Change the attribute via JMX:

```java
import javax.management.Attribute;

server.setAttribute(
    name,
    new Attribute("Enabled", Boolean.FALSE)
);
```

When the setter changes `true` to `false`, the broadcaster emits an event and the listener receives the callback. Calling `setAttribute` again with `false` emits no notification in Section 4's implementation, because no value change occurred.

Clean up the listener and MBean:

```java
try {
    server.removeNotificationListener(name, listener);
} finally {
    if (server.isRegistered(name)) {
        server.unregisterMBean(name);
    }
}
```

Only unregister MBeans owned by the lab. Never perform "unregister every name in the domain" cleanup on a shared platform server.

## 6. Inspecting Notification Metadata

Via `MBeanInfo`, clients can discover which notifications the MBean declares it supports:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanNotificationInfo notificationInfo
        : info.getNotifications()) {

    System.out.println(
        "Notification class: " + notificationInfo.getName()
    );

    for (String type : notificationInfo.getNotifTypes()) {
        System.out.println("Type: " + type);
    }
}
```

Expected output includes the type:

```text
jmx.attribute.change
```

This is the value of `AttributeChangeNotification.ATTRIBUTE_CHANGE`.

To catch contract regressions, tests can assert that this type exists in `MBeanInfo.getNotifications()`. However, metadata listing a type does not prove the event is emitted at the right time; actual tests with a listener are still required.

## 7. Approach B: Spring Framework JMX with NotificationPublisher

Spring Framework JMX provides a built-in `NotificationPublisher` mechanism for beans managed by `MBeanExporter`. A bean can implement `NotificationPublisherAware` and send `Notification` instances via the publisher supplied by the exporter.

This is a useful choice when you want a bean to use Spring annotations instead of extending `NotificationBroadcasterSupport`.

### 7.1. Bean supporting NotificationPublisher

```java
package com.example.springjmx;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.AttributeChangeNotification;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "com.example.springjmx:type=FeatureSwitch,name=Main",
    description = "Managed feature switch"
)
@ManagedNotifications({
    @ManagedNotification(
        name = AttributeChangeNotification.ATTRIBUTE_CHANGE,
        description = "Enabled state changed",
        notificationTypes = {
            AttributeChangeNotification.ATTRIBUTE_CHANGE
        }
    )
})
public class SpringFeatureSwitch
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile boolean enabled = true;
    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute(description = "Current enabled state")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Change enabled state")
    public synchronized void setEnabled(boolean next) {
        boolean previous = enabled;

        if (previous == next) {
            return;
        }

        enabled = next;

        NotificationPublisher target = publisher;
        if (target != null) {
            AttributeChangeNotification event =
                new AttributeChangeNotification(
                    this,
                    sequence.incrementAndGet(),
                    System.currentTimeMillis(),
                    "Enabled changed",
                    "Enabled",
                    "boolean",
                    Boolean.valueOf(previous),
                    Boolean.valueOf(next)
                );

            target.sendNotification(event);
        }
    }
}
```

**Note on notification metadata:** In Spring, `@ManagedNotification` supplies notification metadata, though annotation attributes can vary across versions; verify the exact API for the version you use. A configuration typically only requires appropriate `name` and `notificationTypes`. To keep things minimal and avoid coupling to metadata annotations, you can emit notifications via `NotificationPublisherAware`, then verify directly with a listener and `MBeanInfo`.

Note that `publisher` is only injected when the bean is exported by an `MBeanExporter` supporting `NotificationPublisherAware`. If you instantiate the bean manually and call setters outside Spring JMX, `publisher` will be `null`. A production implementation should define clear behavior before the exporter finishes initialization.

### 7.2. Differences compared to NotificationBroadcasterSupport

| Criterion | Standard MBean broadcaster | Spring NotificationPublisher |
| --- | --- | --- |
| Emission mechanism | `sendNotification()` on `NotificationBroadcasterSupport` | `NotificationPublisher.sendNotification()` |
| Integration | Plain JMX API | Via Spring `MBeanExporter` |
| Metadata | `getNotificationInfo()` | JMX metadata configured through Spring |
| Testability | Register Standard MBean directly | Test exporter, publisher, and listener |
| Lifecycle | Code owns registration/listeners | Spring exporter can manage MBean registration |
| Framework dependency | JDK JMX | Spring Framework JMX |

Both approaches solve the same need: the MBean emits notifications and clients register to receive them. Which one to pick depends on the project; do not accidentally wire both emission paths for a single change if that would produce duplicate notifications.

## 8. Configuring Spring to Export the Bean

An explicit Java configuration using `MetadataMBeanInfoAssembler` and `MBeanExporter`:

```java
package com.example.springjmx;

import java.util.Map;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration
public class SpringJmxLabConfig {

    @Bean
    public SpringFeatureSwitch featureSwitch() {
        return new SpringFeatureSwitch();
    }

    @Bean
    public MBeanServer labMBeanServer() {
        return MBeanServerFactory.newMBeanServer(
            "com.example.springjmx"
        );
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler metadataAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MBeanExporter featureExporter(
            SpringFeatureSwitch featureSwitch,
            MBeanServer labMBeanServer,
            MetadataMBeanInfoAssembler metadataAssembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(labMBeanServer);
        exporter.setAssembler(metadataAssembler);
        exporter.setBeans(Map.of(
            "com.example.springjmx:type=FeatureSwitch,name=Main",
            featureSwitch
        ));
        return exporter;
    }
}
```

Thanks to the isolated server, the lab does not compete for namespaces with the platform server or system MBeans. For clients in another JVM, an isolated server does not automatically have a JMX Remote connector; attach a connector to the right server with security if remote access is truly needed.

If using annotation-driven export such as `@EnableMBeanExport`, do not simultaneously declare a manual exporter for the same ObjectName without an explicit ownership design.

## 9. Registering a Listener in Spring ApplicationContext

Manual test example using a Spring context:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import javax.management.Attribute;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(
            SpringJmxLabConfig.class)) {

    MBeanServer server = context.getBean(MBeanServer.class);

    ObjectName name = new ObjectName(
        "com.example.springjmx:type=FeatureSwitch,name=Main"
    );

    NotificationListener listener = (notification, handback) -> {
        if (notification instanceof AttributeChangeNotification change) {
            System.out.printf(
                "%s: %s -> %s%n",
                change.getAttributeName(),
                change.getOldValue(),
                change.getNewValue()
            );
        }
    };

    server.addNotificationListener(name, listener, null, null);

    try {
        server.setAttribute(
            name,
            new Attribute("Enabled", Boolean.FALSE)
        );
    } finally {
        server.removeNotificationListener(name, listener);
    }
}
```

The MBean must be registered by the exporter before `addNotificationListener` can succeed. Closing `AnnotationConfigApplicationContext` lets the exporter run lifecycle cleanup. Client-registered listeners should still be explicitly removed via `removeNotificationListener` when no longer needed.

## 10. Spring NotificationListenerBean

Beyond registering directly via `MBeanServer.addNotificationListener`, Spring JMX also provides `NotificationListenerBean` to declare a listener and the MBeans it is interested in. In real applications, this allows wiring listeners via Spring configuration.

An illustrative listener:

```java
import javax.management.AttributeChangeNotification;
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification change) {
        System.out.printf(
            "Attribute %s changed to %s%n",
            change.getAttributeName(),
            change.getNewValue()
        );
    }
};
```

If you want Spring to manage listener registration, configure `NotificationListenerBean` with the exporter and appropriate MBean names. Simply having a `NotificationListenerBean` in the context does not automatically attach it to every MBean; you must configure the registration scope and target `MBeanServer` properly.

For a first lab, using `server.addNotificationListener` makes registration, emission, and cleanup directly observable; later you can transition to Spring-managed wiring.

## 11. Using NotificationFilter to Filter Events

A broadcaster may emit multiple notification types. Listeners can use `NotificationFilter` to receive only the events they care about.

Example receiving only attribute changes:

```java
import javax.management.AttributeChangeNotification;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;

NotificationFilter filter = notification ->
    AttributeChangeNotification.ATTRIBUTE_CHANGE
        .equals(notification.getType());

NotificationListener listener = (notification, handback) -> {
    AttributeChangeNotification change =
        (AttributeChangeNotification) notification;

    System.out.printf(
        "%s: %s -> %s%n",
        change.getAttributeName(),
        change.getOldValue(),
        change.getNewValue()
    );
};

server.addNotificationListener(name, listener, filter, null);
```

In this example, the filter ensures the event has the expected standard type. With application-controlled emitters, checking the type is usually enough to infer the expected shape, though production code should still check `instanceof AttributeChangeNotification` when receiving from untrusted broadcasters or mixed event types.

You can also filter further by attribute name:

```java
NotificationFilter onlyEnabled = notification -> {
    if (!(notification instanceof AttributeChangeNotification change)) {
        return false;
    }
    return "Enabled".equals(change.getAttributeName());
};
```

When using a filter, the listener will not receive filtered-out notifications. This is not an emission failure, but intentional client-side filtering.

## 12. Sequence Number and Timestamp

Each notification carries a sequence number and timestamp. Both fields are useful for logging and detecting ordered changes.

Example:

```java
private final AtomicLong sequence = new AtomicLong();

long nextSequence = sequence.incrementAndGet();

AttributeChangeNotification notification =
    new AttributeChangeNotification(
        this,
        nextSequence,
        System.currentTimeMillis(),
        "Enabled changed",
        "Enabled",
        "boolean",
        previous,
        next
    );
```

However:

- Sequence numbers are meaningful only **per emitter**, not as a global ordering across all MBeans.
- When an application restarts or a new instance is created, the sequence may reset.
- Timestamps depend on the emitting JVM's clock; across multiple servers, clock skew can affect comparisons.
- Remote listeners may receive events with delay; receipt time does not equal emission time.
- Do not rely on sequence numbers alone as durable offsets if you need guaranteed zero event loss.

If a system requires replay, durable delivery, or exactly-once semantics, JMX notifications should not replace a dedicated event bus or message broker.

## 13. Old Value and New Value

`AttributeChangeNotification` holds:

```java
change.getOldValue();
change.getNewValue();
```

These are `Object`s, so the client must know the attribute's type. For boolean:

```java
Boolean previous = (Boolean) change.getOldValue();
Boolean next = (Boolean) change.getNewValue();
```

For attributes that are collections or mutable objects, consider snapshots and aliasing. If you emit a notification by passing the same mutable reference after mutating it, old/new may fail to reflect the intended state snapshots.

A safer design is using immutable values or copying an appropriate snapshot before sending. Avoid putting complex object graphs or sensitive data into notifications, especially over remote JMX.

### 13.1. Actual changes vs. requested changes

Suppose a setter receives `next=true`, yet business logic rejects it because the current state is invalid. You must not emit a notification with `old=false, new=true` when the runtime value is still `false`.

Notifications should reflect **applied changes**, not merely incoming requests. If an asynchronous operation only accepts a request, one notification can describe `ACCEPTED` and a completion notification can be emitted later.

## 14. Concurrency Issues When Multiple Clients Update Simultaneously

Suppose two clients send:

```text
Client A: set Enabled=false
Client B: set Enabled=true
```

If the setter is not synchronized, sequence numbers and old/new values may fail to reflect the transition order expected by operators.

In the Standard MBean example, `synchronized` protects read/update and event creation. In production environments, you can separate atomic state updates from event dispatch to avoid invoking listeners while holding a lock:

```text
lock
  read old value
  validate transition
  update new value
  increment sequence
unlock
emit notification
```

This shortens lock hold times, though if threads emit concurrently after unlocking, **notification delivery order** may differ from update order. If strict ordering matters, use a sequential dispatch queue or proper event sequencing.

You cannot infer global notification ordering guarantees solely from per-MBean monotonically increasing sequence numbers.

## 15. Unit Testing with CountDownLatch

A good test should never use `Thread.sleep(1000)` and hope a callback ran. Use `CountDownLatch` to await the notification with a clear timeout.

JUnit 5 example:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import javax.management.Attribute;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.NotificationListener;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FeatureSwitchNotificationTest {

    @Test
    void emitsAttributeChangeNotification() throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("com.example.test");

        ObjectName name = new ObjectName(
            "com.example.test:type=FeatureSwitch,name=Main"
        );

        FeatureSwitch bean = new FeatureSwitch();
        server.registerMBean(bean, name);

        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<AttributeChangeNotification> received =
            new AtomicReference<>();

        NotificationListener listener = (event, handback) -> {
            if (event instanceof AttributeChangeNotification change) {
                received.set(change);
                latch.countDown();
            }
        };

        server.addNotificationListener(name, listener, null, null);

        try {
            server.setAttribute(
                name,
                new Attribute("Enabled", Boolean.FALSE)
            );

            assertTrue(
                latch.await(2, TimeUnit.SECONDS),
                "Expected attribute change notification"
            );

            AttributeChangeNotification event = received.get();

            assertNotNull(event);
            assertEquals(
                AttributeChangeNotification.ATTRIBUTE_CHANGE,
                event.getType()
            );
            assertEquals("Enabled", event.getAttributeName());
            assertEquals("boolean", event.getAttributeType());
            assertEquals(Boolean.TRUE, event.getOldValue());
            assertEquals(Boolean.FALSE, event.getNewValue());
            assertTrue(event.getSequenceNumber() > 0);
        } finally {
            server.removeNotificationListener(name, listener);
            server.unregisterMBean(name);
        }
    }
}
```

This test runs entirely in one JVM, using an isolated MBeanServer to avoid colliding with other tests. If callbacks are synchronous, the latch is already satisfied before `await`; if asynchronous, `await` bounds the wait time.

### 15.1. Verifying no event is emitted when the value is unchanged

You can extend the test:

1. Set `Enabled=false`.
2. Record the current notification count.
3. Call `setAttribute(Enabled=false)` again.
4. Assert the implementation emits no additional event per contract.

Proving "no event occurred" via a time wait is inherently weak. With synchronous local tests and deterministic implementations, you can use a notification counter checked right after the setter; with an async executor, use deterministic synchronization or control the executor in tests.

## 16. Testing Spring NotificationPublisher

To test integration with the Spring exporter:

1. Open `AnnotationConfigApplicationContext` containing `SpringJmxLabConfig`.
2. Retrieve the `MBeanServer` bean from the context.
3. Assert `isRegistered(ObjectName)`.
4. Register the listener before making changes.
5. Call `server.setAttribute(name, Attribute("Enabled", false))`.
6. Wait for the callback using a latch.
7. Assert `AttributeChangeNotification` has exact `attributeName`, `oldValue`, `newValue`, and type.
8. Read `server.getAttribute(name, "Enabled")` to verify the actual runtime state.
9. Remove the listener in `finally`.
10. Close the context so the exporter cleans up its own registration.

This test differs from a pure unit test by verifying that **Spring's `MBeanExporter` supplied `NotificationPublisher` and the `MBeanInfo`/notification path works as expected**. If the publisher is not supplied, inspect the exporter configuration, MBean wrapping/adapting behavior, and lifecycle, not just event construction.

## 17. Exploring Notifications in JConsole

If the MBean is registered in the platform server and JConsole connects to the same JVM:

1. Open the **MBeans** tab.
2. Locate the ObjectName, e.g., `com.example.lab:type=FeatureSwitch,name=Main`.
3. Inspect **Attributes** and the `Enabled` value.
4. Inspect **Notifications** if JConsole displays a notifications section for this MBean.
5. Subscribe to notifications in the tool if that feature is available.
6. Change `Enabled` via an authorized management action.
7. Observe the event with type `jmx.attribute.change`.

UI presentation varies by JDK/JConsole version and MBean type. If the MBean lives on a private MBeanServer, JConsole connected to the platform server will not automatically see the resource. You need a connector pointing to that server or Java test code like in previous sections.

Do not use JConsole to experiment with changing production state without approval. Even a simple `boolean` writable attribute can impact business or operational behavior.

## 18. Listener Lifecycle and Memory Leaks

A listener can hold references to services, beans, or a Spring context. If an MBean broadcaster outlives the application (especially on a shared platform MBeanServer), an old listener can pin an old classloader after redeploy.

Rules:

- Keep a reference to each registered listener.
- Call `removeNotificationListener` when no longer needed.
- Close `JMXConnector` when finished.
- Let `MBeanExporter` clean up Spring-managed MBeans when the context closes.
- Clean up manually registered MBeans according to clear ownership.
- Never arbitrarily unregister framework/container MBeans.
- Avoid storing listeners in static collections that live for the JVM's lifetime.

If `removeNotificationListener` fails because the MBean was already unregistered, review cleanup order and ownership. Do not assume that a listener no longer receiving events means all references have been freed.

## 19. Remote Notifications and Reliability

When a client connects via JMX Remote, notifications travel over the connector. An event emitted while the client is disconnected is not replayed.

A high-availability consumer should:

1. Connect and read the current state.
2. Register the notification listener.
3. Re-read a snapshot if needed to close the gap between initial read and registration.
4. Monitor connect/disconnect and transport errors.
5. Re-register listeners upon reconnect.
6. Resync state instead of assuming every event was received.
7. Use sequence numbers as a diagnostic aid, not as a durable offset.

If business requirements demand guaranteed delivery, auditing, and exact replay, use a dedicated event broker, database log, or another durable mechanism. JMX notifications suit telemetry and administration, not replacing a durable business event bus.

## 20. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Listener receives no events | Forgot `addNotificationListener`, wrong ObjectName/server | Check registration and `isRegistered` |
| `InstanceNotFoundException` on listener registration | MBean not yet registered | Initialize exporter/server before registering |
| `ListenerNotFoundException` during cleanup | Removing wrong listener/registration pair | Retain reference and unregister exact pair |
| Missing events | Subscribed after change or connection dropped | Read snapshot, resubscribe, and resync |
| Event has wrong old/new values | Mutable state, race, or emitted before applying | Snapshot and synchronize transitions |
| Duplicate events | Two publish paths or duplicate listeners | Check broadcaster/publisher and lifecycle |
| `getNotifications()` lacks type | Missing broadcaster/assembler metadata config | Check `getNotificationInfo` or Spring metadata |
| JConsole does not see the MBean | Inspecting wrong MBeanServer or connector | Use the right server/connection |
| Flaky test (passes/fails intermittently) | Sleeping or timing races | Use latch and isolated server |
| Heap grows after redeploy | Listener or MBean pins old classloader | Manage cleanup and reference graphs |

Distinguish metadata errors from actual event emission errors. Having notification metadata on an MBean does not guarantee every state transition emits events properly; conversely, events may be emitted yet invisible to clients if metadata is incomplete.

## 21. Self-Practice Exercises

### Exercise 1 — Standard MBean

1. Create `FeatureSwitchMBean` and `FeatureSwitch`.
2. Create an isolated MBeanServer.
3. Register ObjectName `com.example.lab:type=FeatureSwitch,name=Main`.
4. Add a listener capturing `AttributeChangeNotification`.
5. Call `setAttribute("Enabled", false)`.
6. Print `attributeName`, `attributeType`, old/new, sequence, and timestamp.
7. Verify `getAttribute("Enabled")` returns `false`.
8. Write `false` again and verify the contract emits no extra event.
9. Remove the listener and unregister the MBean.

### Exercise 2 — Spring JMX

1. Create `SpringFeatureSwitch` implementing `NotificationPublisherAware`.
2. Export via `MBeanExporter` and a metadata assembler.
3. Register a listener against the context's `MBeanServer`.
4. Change `Enabled` via JMX.
5. Verify the listener receives type `jmx.attribute.change`.
6. Read `MBeanInfo.getNotifications()`.
7. Close the context and observe cleanup.

### Exercise 3 — Real-world analysis

Suppose a remote client disconnects while `Enabled` changes three times. Explain why reconnecting and waiting for the next notification does not guarantee knowing the latest state. Design a resync step using `getAttribute` and sequence tracking.

## 22. Self-Check Questions

**1. What is `AttributeChangeNotification` used for?** Notifying that an attribute changed, including its name, type, old value, and new value.

**2. How does `getAttribute` differ from notifications?** `getAttribute` reads the current snapshot; notifications report change events.

**3. What is the standard type of an attribute change notification?** `AttributeChangeNotification.ATTRIBUTE_CHANGE`, whose value is `jmx.attribute.change`.

**4. What is the role of `NotificationBroadcasterSupport`?** Provides listener registration and notification emission mechanics for an MBean.

**5. What does Spring's `NotificationPublisherAware` provide?** Allows a bean to receive a publisher supplied by the Spring JMX exporter to send notifications.

**6. Why must you register a listener before changing state?** If registered afterward, earlier events have already fired and are not replayed.

**7. Are sequence numbers unique across all MBeans?** No, they are typically scoped per emitter.

**8. Do notifications guarantee durable delivery?** No. A separate mechanism is required for replay or guaranteed full delivery.

**9. Why must listeners be removed?** To avoid retaining references, memory leaks, and callbacks after the context stops.

**10. When an event says `newValue=false`, should you rely on it forever instead of snapshots?** No; clients should resync when needed, especially after reconnects or missed events.

## 23. Key Takeaways

- **`AttributeChangeNotification`** is JMX's standard notification for attribute changes.
- Notifications carry **`attributeName`, `attributeType`, `oldValue`, `newValue`, `sequenceNumber`, and `timestamp`**.
- Use **`NotificationBroadcasterSupport`** with Standard MBeans or **Spring `NotificationPublisherAware`** when exporting via Spring JMX.
- Register listeners with **`MBeanServer.addNotificationListener`** and remove them with `removeNotificationListener`.
- MBeans should declare notification types via **`MBeanInfo.getNotifications()`**.
- Emit events only when a state transition is actually applied to avoid sending false information.
- **Listener lifecycle** must align with MBean/connector lifecycle to prevent classloader leaks.
- Use **`CountDownLatch`** in tests rather than relying on `Thread.sleep`.
- Remote notifications **do not guarantee durable delivery**; read a snapshot/resync on reconnect.
- Do not include secrets or sensitive data in notifications, especially over remote JMX.

Practicing emitting and receiving `AttributeChangeNotification` shows how MBeans announce state changes in an event-driven way. When combined with accurate metadata, lifecycle-managed listeners, and snapshot synchronization, Spring Framework JMX provides a useful administrative observability channel without confusing it with a durable messaging system.