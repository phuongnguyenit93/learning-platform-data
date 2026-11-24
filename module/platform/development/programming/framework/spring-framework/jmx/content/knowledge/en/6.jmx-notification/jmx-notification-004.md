# AttributeChangeNotification for Attribute Changes in Spring Framework JMX

## Objectives

In Java Management Extensions (JMX), an MBean exposes operational state through attributes, operations, and notifications. `AttributeChangeNotification` is the standard notification type for an attribute change. Spring Framework JMX helps integrate MBeans into Spring applications, while creating and emitting notifications follows the JMX API.

After this lesson, you will know how to read information about a changed attribute, emit notifications from an MBean, register listeners, and distinguish notifications from reading the current attribute.

## 1. Why Are Attribute Change Notifications Needed?

Suppose an MBean exposes an `Enabled` attribute with value `true`. A client can call `getAttribute(objectName, "Enabled")` periodically to detect changes. However, between two reads, the state could change multiple times without the client knowing.

With notifications, the MBean proactively sends an event when state changes:

```text
Client                          MBean
  |-- addNotificationListener --> |
  |                               |
  |                      Enabled: true -> false
  | <-- AttributeChangeNotification
  |                               |
  |                      Enabled: false -> true
  | <-- AttributeChangeNotification
```

This is an event-driven model: the listener receives information about a change that occurred, including the attribute name and before/after values. Notifications do not automatically provide the current state at all times: a client that registers late or loses connection can miss events. Therefore, in management systems, notifications typically complement reading attributes.

## 2. Structure of AttributeChangeNotification

The `javax.management.AttributeChangeNotification` class extends `javax.management.Notification`. It carries the following information:

| Method | Meaning |
| --- | --- |
| `getType()` | Notification type; the constant `ATTRIBUTE_CHANGE` has value `jmx.attribute.change` |
| `getSource()` | Notification emission source |
| `getSequenceNumber()` | Sequence number supplied by the emitter |
| `getTimeStamp()` | Notification creation time, milliseconds since Unix epoch |
| `getMessage()` | Event description |
| `getAttributeName()` | Attribute name, e.g., `Enabled` |
| `getAttributeType()` | Type name, e.g., `boolean` |
| `getOldValue()` | Value before the change |
| `getNewValue()` | Value after the change |

Creating the notification:

```java
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

The constructor takes source, sequence number, timestamp, message, attribute name, attribute type, old value, and new value. Creating this object **does not emit the event by itself**. The MBean must send it via a broadcaster or the corresponding publisher mechanism.

The old/new values have type `Object`. For primitive types, Java typically boxes them into `Boolean`, `Integer`, `Long`, etc. When handling notifications from other MBeans, clients should inspect metadata or check actual runtime types before casting.

## 3. Building an MBean with a Changing Attribute

### 3.1. Standard MBean interface

```java
package com.example.monitoring;

public interface SwitchMonitorMBean {
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
```

By JMX Standard MBean conventions, the `SwitchMonitorMBean` interface defines the management surface of the `SwitchMonitor` class. The `isEnabled()` and `setEnabled(boolean)` pair creates a readable and writable `Enabled` attribute.

### 3.2. Implementing the broadcaster and sending notifications

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanNotificationInfo;
import javax.management.NotificationBroadcasterSupport;

public class SwitchMonitor extends NotificationBroadcasterSupport
        implements SwitchMonitorMBean {

    private final AtomicLong sequence = new AtomicLong();
    private boolean enabled = true;

    @Override
    public synchronized boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean next) {
        AttributeChangeNotification event;

        synchronized (this) {
            boolean previous = enabled;
            if (previous == next) {
                return;
            }

            enabled = next;
            event = new AttributeChangeNotification(
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Enabled changed",
                "Enabled",
                "boolean",
                previous,
                next
            );
        }

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
                "Notifications about Enabled changes"
            )
        };
    }
}
```

Analysis:

1. `NotificationBroadcasterSupport` provides listener registration, removal, and `sendNotification(...)`.
2. The setter captures the previous value, checks for a difference, updates state, and creates the notification.
3. Calling `setEnabled(true)` when state is already `true` emits no new event in this example.
4. `sequence.incrementAndGet()` supplies increasing sequence numbers for notifications.
5. `getNotificationInfo()` advertises the notification types supported by the MBean.
6. `sendNotification(event)` actually dispatches the event to listeners.

The example intentionally emits the event after exiting the synchronized block so the state lock is not held while calling listeners. When multiple threads update state concurrently, callback order may differ from update order; sequence numbers help identify event creation order, though they do not guarantee every listener processes in that exact order.

### 3.3. Registering the MBean

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.monitoring:type=SwitchMonitor,name=Main"
);

SwitchMonitor monitor = new SwitchMonitor();
server.registerMBean(monitor, name);
```

This registers directly with the platform MBeanServer. In Spring applications, `MBeanExporter` usually manages registration and unregistration. Do not register the same ObjectName twice on one server, as that can cause `InstanceAlreadyExistsException`.

## 4. Registering a NotificationListener

A client must register a `NotificationListener` with the MBeanServer to receive notifications for a specific ObjectName.

```java
import javax.management.Attribute;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanServer;
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification change) {
        System.out.printf(
            "%s: %s -> %s (seq=%d)%n",
            change.getAttributeName(),
            change.getOldValue(),
            change.getNewValue(),
            change.getSequenceNumber()
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
```

Since `Enabled` starts as `true`, the write call generates a `true -> false` notification if the MBean is properly registered and the listener is active. The parameters of `addNotificationListener` are ObjectName, listener, optional filter, and optional handback. `handback` is a context object supplied by the registrant; it is not the old/new value.

In long-lived applications, listeners are typically registered when a component initializes and removed when it shuts down. Do not register a new listener on every request and leave it behind.

### Filtering by attribute

To receive changes only for `Enabled`, use `AttributeChangeNotificationFilter`:

```java
import javax.management.AttributeChangeNotificationFilter;

AttributeChangeNotificationFilter filter =
    new AttributeChangeNotificationFilter();
filter.enableAttribute("Enabled");

server.addNotificationListener(name, listener, filter, null);
```

This filter selects attribute-change notifications whose attribute name matches. If an MBean exposes many attributes or emits multiple notification types, the filter reduces the number of events the listener must handle.

## 5. Discovering Notification Metadata

JMX provides `MBeanInfo` so clients know which notification types an MBean advertises:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanNotificationInfo notificationInfo :
        info.getNotifications()) {
    System.out.println(notificationInfo.getDescription());
    for (String type : notificationInfo.getNotifTypes()) {
        System.out.println("Type: " + type);
    }
}
```

With `SwitchMonitor` above, metadata includes type `jmx.attribute.change`. However, metadata only says the MBean **is capable of** emitting this type; it does not promise how many or when they will be emitted. Notifications appear only when the setter logic actually calls `sendNotification`.

Do not confuse `getNotificationInfo()` with `getNotifications()` on metadata: the MBean implements `getNotificationInfo()`; the client reads the list via `MBeanInfo.getNotifications()`.

## 6. Integrating with Spring Framework JMX

Spring provides utilities to turn application beans into MBeans. A Standard MBean like `SwitchMonitor` can be exported with `MBeanExporter`:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfig {

    @Bean
    public SwitchMonitor switchMonitor() {
        return new SwitchMonitor();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter switchExporter(
            SwitchMonitor monitor,
            MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
            "com.example.monitoring:type=SwitchMonitor,name=Main",
            monitor
        ));
        return exporter;
    }
}
```

Once the context initializes and the exporter registers the object, JMX clients use the exact ObjectName to access attributes and notifications. Keep a single source managing registration for each MBean, avoiding configuring an exporter while also calling `registerMBean` manually under the same name.

### 6.1. Spring NotificationPublisher

Alongside `NotificationBroadcasterSupport`, Spring has `org.springframework.jmx.export.notification.NotificationPublisher` for managed beans to emit notifications. A bean implementing `NotificationPublisherAware` can receive a publisher when exported by an appropriate `MBeanExporter`.

```java
import javax.management.AttributeChangeNotification;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

public class PublisherMonitor implements NotificationPublisherAware {

    private NotificationPublisher publisher;
    private boolean enabled = true;
    private long sequence;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    public void setEnabled(boolean next) {
        boolean previous = enabled;
        if (previous == next) {
            return;
        }
        enabled = next;

        if (publisher != null) {
            publisher.sendNotification(
                new AttributeChangeNotification(
                    this,
                    ++sequence,
                    System.currentTimeMillis(),
                    "Enabled changed",
                    "Enabled",
                    "boolean",
                    previous,
                    next
                )
            );
        }
    }
}
```

This second example illustrates the publisher's role; it does not include the MBean interface, export configuration, or multi-thread synchronization to run standalone. It shows that Spring can supply a notification-emitting mechanism without the bean extending a JMX broadcaster. Ensure the bean is actually managed by an exporter and has received the publisher before expecting notifications to be sent.

### 6.2. ManagedNotification metadata

Spring supports JMX metadata such as `@ManagedResource`, `@ManagedAttribute`, and `@ManagedNotification` along with corresponding assemblers. Metadata helps the MBean advertise notification types that clients can discover.

Key point: declaring metadata **does not automatically emit** `AttributeChangeNotification`. There must be code that emits the event, such as `sendNotification` or `NotificationPublisher.sendNotification`. Annotations must be processed by a suitable exporter/assembler, rather than assuming any annotated bean auto-registers itself.

## 7. How Do Attributes, Operations, and Notifications Differ?

| Component | How the client uses it | Question answered |
| --- | --- | --- |
| Attribute | `getAttribute(name, "Enabled")` | What is the current state? |
| Operation | `invoke(name, "reset", ...)` | What action can be requested? |
| Notification | `addNotificationListener(...)` | What event just happened? |

Writing an attribute via `setAttribute` does not guarantee an AttributeChangeNotification is emitted automatically. The MBean must actively create and emit it. Conversely, receiving a notification does not guarantee the current state is still the event's `newValue`, because the attribute may continue changing afterward.

Example:

```text
t1: Enabled true -> false; emits event A
t2: Enabled false -> true; emits event B
t3: listener processes event A
```

When processing event A at t3, the current state may already be `true`. Any client needing current truth should read the attribute, or use sequence/version numbers to reconcile order.

## 8. Consistency of Old/New Values

Notifications are reliable only when the emitter captures old/new values at the exact moment of update.

Example with validation:

```java
public synchronized void setThreshold(int next) {
    if (next < 0) {
        throw new IllegalArgumentException(
            "Threshold must be non-negative"
        );
    }

    int previous = threshold;
    if (previous == next) {
        return;
    }

    threshold = next;
    // Create previous -> next notification after successful update.
}
```

If the setter rejects the new value, do not emit a notification claiming the value changed. For mutable attribute types, consider immutable snapshots when placing them into old/new values so the objects are not unexpectedly mutated later.

Some guidelines:

- Capture `oldValue` before updating.
- Only create the event once the change condition is confirmed.
- Assign sequence numbers consistently per emitter.
- Do not put secrets, tokens, or sensitive data into message or old/new values.
- Do not treat listener callbacks as part of a transaction with the state update.

## 9. Sequence Numbers, Timestamps, and Concurrency

`getSequenceNumber()` helps distinguish notifications from a single source; for example, `AtomicLong.incrementAndGet()` produces increasing numbers. However, this number is assigned by the emitter, not a global identifier across all JVMs. When an MBean or application restarts, sequence numbers may start over.

`getTimeStamp()` returns the time recorded by the emitter. It does not necessarily equal the time the listener receives the event, especially over a network or with asynchronous processing. Clocks across different JVMs can also drift.

When multiple threads change the same attribute, determine:

1. Are reading the old value and writing the new value synchronized?
2. At what point is the sequence number allocated?
3. Can callbacks be delivered out of update order?
4. Does the client need to retain the latest state or store full event history?
5. How does the system react when a callback is slow?

`NotificationBroadcasterSupport` can use a configurable executor. With synchronous delivery, slow callbacks can delay the emitting thread. With asynchronous callbacks, queues, errors, and ordering must be handled appropriately. Do not let listeners perform prolonged I/O inside a critical setter without understanding the impact on the application.

## 10. Lifecycle and Remote Access

Listeners are registered against a specific MBean by `ObjectName`. If the MBean is unregistered, old registrations should not be treated as permanent. When the Spring context closes, components managing listeners should remove registrations in the corresponding lifecycle hook.

With JMX Remote, clients use `MBeanServerConnection`:

```java
connection.addNotificationListener(
    name,
    listener,
    filter,
    null
);
```

Delivery over a connector can suffer network errors or disconnects. Do not assume notifications during a disconnection are buffered and re-sent later. After reconnecting, clients should re-register on the new connection and read current state to reconcile.

Errors to distinguish include:

- `InstanceNotFoundException`: the MBean is not registered under the ObjectName used.
- `ListenerNotFoundException`: removing a listener registration that does not exist.
- `IOException` in remote clients: transport/connection failure.
- Authorization/security error: client lacks permission to perform the operation.
- Error inside callback: listener processing logic failed; catch and handle separately.

Remote JMX is a sensitive management channel. Restrict network access, use proper authentication and encryption, and do not emit secrets in notifications.

## 11. Guided Practice

Practice using `SwitchMonitor` registered as in section 3.

**Step 1:** Check that the MBean exists:

```java
if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "Missing MBean: " + name
    );
}
```

**Step 2:** Read `MBeanInfo` and verify notification types include `jmx.attribute.change`.

**Step 3:** Register listener and filter:

```java
AttributeChangeNotificationFilter filter =
    new AttributeChangeNotificationFilter();
filter.enableAttribute("Enabled");

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification change) {
        System.out.printf(
            "Attribute=%s old=%s new=%s seq=%d%n",
            change.getAttributeName(),
            change.getOldValue(),
            change.getNewValue(),
            change.getSequenceNumber()
        );
    }
};

server.addNotificationListener(name, listener, filter, null);
```

**Step 4:** Change the value:

```java
server.setAttribute(
    name,
    new Attribute("Enabled", false)
);
server.setAttribute(
    name,
    new Attribute("Enabled", false)
);
server.setAttribute(
    name,
    new Attribute("Enabled", true)
);
```

If the initial state is `true`, this example produces two notifications because the second write does not change the value.

Sample output:

```text
Attribute=Enabled old=true new=false seq=1
Attribute=Enabled old=false new=true seq=2
```

**Step 5:** Remove the listener:

```java
server.removeNotificationListener(name, listener);
```

**Step 6:** Re-read the attribute:

```java
boolean enabled =
    (Boolean) server.getAttribute(name, "Enabled");
System.out.println("Current state: " + enabled);
```

The final read is `true` if no other thread or client updated it during the exercise. This read confirms the current state, while notifications recount the changes the listener received.

## 12. Common Misconceptions

**"Calling setAttribute automatically creates an AttributeChangeNotification."** No. The MBean or publisher must actively emit it.

**"Just adding @ManagedNotification produces events."** No. The annotation describes metadata; the emitter is what sends notifications.

**"A late-registering listener still receives all past events."** There is no guarantee of storing and replaying history.

**"Old/new values are always accurate without worrying about setter code."** They are supplied by the emitter; update logic must produce consistent data.

**"One notification tells you the current state for sure."** State can change further; to know the current state, read the attribute.

**"Sequence number is an absolute order across multiple applications."** No. It has meaning within the emission source and that source's numbering contract.

**"Metadata listing a notification means every attribute write produces an event."** No. Metadata describes the event types the MBean can emit, not a promise on every write.

## 13. Self-Check Questions

1. What is `AttributeChangeNotification` used to describe? **A change to an MBean's management attribute.**
2. What is its standard type? **`jmx.attribute.change`.**
3. What are the two methods to read before/after values? **`getOldValue()` and `getNewValue()`.**
4. How does an MBean actually send the event? **Via broadcaster `sendNotification(...)` or an appropriate publisher.**
5. Which API does a client use to subscribe to events? **`addNotificationListener(...)` on MBeanServer/MBeanServerConnection.**
6. How do you receive events only for `Enabled`? **Use `AttributeChangeNotificationFilter.enableAttribute("Enabled")`.**
7. Can notifications completely replace `getAttribute()`? **No, because notifications do not guarantee current state or complete history.**
8. Why must listeners be removed? **To prevent callbacks and resources from outliving the required lifecycle.**
9. When a remote client reconnects, what should it do? **Re-establish listeners and re-read current state.**

## 14. Key Takeaways

- `AttributeChangeNotification` is the JMX standard for **attribute change** events.
- The event carries **name, type, old/new values, timestamp, and sequence number**.
- **Metadata does not automatically emit notifications**; a broadcaster or publisher is required.
- **NotificationListener** receives events; **AttributeChangeNotificationFilter** filters by attribute.
- **Spring MBeanExporter** connects Spring bean lifecycles with MBeanServer; Spring also provides `NotificationPublisher`.
- **Reading attributes** provides current state; **notifications** indicate a change was detected and delivered to listeners.
- Proactively handle concurrency, ordering, security, reconnection, and listener lifecycles.

When building observability for Spring Framework JMX, treat `AttributeChangeNotification` as a useful event channel for quick reactions; determining exact operational state still relies on attribute contracts and proper reconciliation mechanisms.