# Spring Framework JMX: AttributeChangeNotification and Attribute Changes

## 1. Objectives

JMX (Java Management Extensions) provides attributes so management tools can observe and adjust an MBean's state. When an attribute changes, an MBean can emit a javax.management.AttributeChangeNotification event to registered listeners. This lesson covers creating notifications, integrating with Spring MBeanExporter and NotificationPublisherAware, inspecting old/new values, registering listeners, handling concurrency, security, and testing.

Key point: merely declaring Spring @ManagedAttribute does not automatically generate AttributeChangeNotification. The bean must proactively emit the event using a corresponding broadcaster or publisher. Notifications do not by default support durable storage or replay after a client reconnects.

## 2. Architecture

```text
Client / JConsole
   |
   | setAttribute(name, new Attribute("MaxWorkers", 16))
   v
MBeanServer
   |
   v
Spring MBeanExporter -> managed bean
                          |
                          | validate + update state
                          v
                   AttributeChangeNotification
                          |
                          v
             NotificationBroadcaster / Publisher
                          |
                 NotificationListener
                          |
                audit / monitoring
```

A value-change path should include: validating the new value, capturing the old value, applying the change successfully, creating the event, and emitting it after state has been updated. If configuring an executor or connection pool fails, do not emit an event claiming the change completed.

## 3. What Is AttributeChangeNotification?

AttributeChangeNotification resides in package javax.management and extends Notification. Constructor:

```java
new AttributeChangeNotification(
    source,
    sequenceNumber,
    timeStamp,
    message,
    attributeName,
    attributeType,
    oldValue,
    newValue
);
```

| Field | Meaning |
|---|---|
| source | Source object or MBean identity |
| sequenceNumber | Event sequence number managed by the emitter |
| timeStamp | Epoch milliseconds |
| message | Short description |
| attributeName | JMX attribute name, e.g., MaxWorkers |
| attributeType | Java type name, e.g., int |
| oldValue | Old value |
| newValue | New value |

The standard notification type is AttributeChangeNotification.ATTRIBUTE_CHANGE, with value "jmx.attribute.change". Specialized getters include getAttributeName(), getAttributeType(), getOldValue(), and getNewValue().

```java
if (notification instanceof AttributeChangeNotification change) {
    System.out.printf("%s: %s -> %s%n",
        change.getAttributeName(),
        change.getOldValue(),
        change.getNewValue()
    );
}
```

An event describes a snapshot at emission time, not a guarantee of the current value at all future points. If the client reads again with getAttribute(), it may see a newer value from another change.

## 4. Standard MBean with NotificationBroadcasterSupport

Define the management interface:

```java
package com.example.jmx;

public interface WorkerPoolControlMBean {
    int getMaxWorkers();
    void setMaxWorkers(int value);
}
```

Implementation:

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanNotificationInfo;
import javax.management.NotificationBroadcasterSupport;

public final class WorkerPoolControl
        extends NotificationBroadcasterSupport
        implements WorkerPoolControlMBean {

    private final AtomicLong sequence = new AtomicLong();
    private int maxWorkers = 8;

    @Override
    public synchronized int getMaxWorkers() {
        return maxWorkers;
    }

    @Override
    public void setMaxWorkers(int value) {
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException("Expected 1..64");
        }

        final int oldValue;
        final long number;
        synchronized (this) {
            oldValue = maxWorkers;
            if (oldValue == value) {
                return;
            }
            maxWorkers = value;
            number = sequence.incrementAndGet();
        }

        AttributeChangeNotification event =
            new AttributeChangeNotification(
                this,
                number,
                System.currentTimeMillis(),
                "MaxWorkers changed",
                "MaxWorkers",
                "int",
                oldValue,
                value
            );
        sendNotification(event);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] {
                    AttributeChangeNotification.ATTRIBUTE_CHANGE
                },
                AttributeChangeNotification.class.getName(),
                "Worker pool configuration changed"
            )
        };
    }
}
```

Details:
- Validation occurs before changing state.
- Synchronization protects the old/new snapshot and update in the example.
- Calling the setter with an unchanged value creates no event.
- The event is sent outside the synchronized block to reduce the risk of callbacks holding the lock for long.
- getNotificationInfo() publishes metadata so clients know which notification types the MBean can emit.

If multiple threads write consecutively, sequence numbers are assigned inside the lock while sendNotification() runs outside the lock. Listeners may receive events out of sequence-assignment order. If strict ordering is mandatory, design a sequential event-emission queue rather than relying on default JMX behavior.

## 5. Exporting a Standard MBean via Spring

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class WorkerJmxConfig {

    @Bean
    WorkerPoolControl workerPoolControl() {
        return new WorkerPoolControl();
    }

    @Bean
    MBeanExporter workerExporter(WorkerPoolControl control) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerPool,name=primary",
            control
        ));
        return exporter;
    }
}
```

MBeanExporter registers the bean under the ObjectName into the chosen MBeanServer. The Standard MBean interface determines the attributes; the broadcaster in the implementation determines notification emission. If there is also an automatic annotation-driven exporter or another exporter, avoid duplicate ObjectName registrations.

## 6. Spring POJO and NotificationPublisherAware

A Spring bean is not required to extend NotificationBroadcasterSupport. Spring provides org.springframework.jmx.export.notification.NotificationPublisherAware so the exporter injects a NotificationPublisher into eligible beans.

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.AttributeChangeNotification;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "com.example.app:type=ConfigControl,name=primary",
    description = "Runtime configuration"
)
public class ConfigControl implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private int maxConnections = 16;
    private volatile NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute(description = "Current connection limit")
    public synchronized int getMaxConnections() {
        return maxConnections;
    }

    @ManagedAttribute(description = "Change connection limit")
    public void setMaxConnections(int value) {
        if (value < 1 || value > 200) {
            throw new IllegalArgumentException("Expected 1..200");
        }

        final int before;
        final long number;
        synchronized (this) {
            before = maxConnections;
            if (before == value) return;
            maxConnections = value;
            number = sequence.incrementAndGet();
        }

        NotificationPublisher p = publisher;
        if (p != null) {
            p.sendNotification(new AttributeChangeNotification(
                this,
                number,
                System.currentTimeMillis(),
                "MaxConnections changed",
                "MaxConnections",
                "int",
                before,
                value
            ));
        }
    }
}
```

The Spring exporter can supply a publisher so the bean sends notifications via ModelMBean. Ensure an appropriate exporter and annotation metadata assembler; the mere presence of NotificationPublisherAware does not guarantee the bean has been exported. If the publisher is not ready yet when the setter runs, the example above still updates state without an event. The system must choose an explicit policy for changes occurring prior to JMX registration.

Example declaring an annotation-driven exporter:

```java
@Configuration
@EnableMBeanExport
public class JmxConfiguration {
    @Bean
    ConfigControl configControl() {
        return new ConfigControl();
    }
}
```

For JMX clients to see the expected notification types, publish notification metadata compatible with your Spring version, such as ManagedNotification/ManagedNotifications, or configure the corresponding MBeanInfoAssembler. Metadata describes notification types but does not automatically call sendNotification().

## 7. Listener Using the JMX API

```java
import javax.management.AttributeChangeNotification;
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName target = new ObjectName(
    "com.example.app:type=ConfigControl,name=primary"
);

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification event) {
        System.out.printf(
            "%s: %s -> %s%n",
            event.getAttributeName(),
            event.getOldValue(),
            event.getNewValue()
        );
    }
};

connection.addNotificationListener(target, listener, null, null);
```

Remove the listener when monitoring is no longer needed:

```java
connection.removeNotificationListener(target, listener);
```

With remote connections, when the target JVM restarts or the connector drops, you must handle reconnection and possibly re-register the listener. JMX notifications do not by default have a durable queue or replay. Application listeners must avoid slow callbacks or heavy I/O on the event-emission path.

## 8. Filtering by Attribute

AttributeChangeNotificationFilter can receive changes only for specific attributes:

```java
import javax.management.AttributeChangeNotificationFilter;

AttributeChangeNotificationFilter filter =
    new AttributeChangeNotificationFilter();

filter.enableAttribute("MaxConnections");

connection.addNotificationListener(
    target,
    listener,
    filter,
    null
);
```

Useful APIs: enableAttribute(name), disableAttribute(name), disableAllAttributes(). The name must be the exact JMX attribute name, such as MaxConnections, not the Java field name maxConnections.

Filters reduce unnecessary callbacks; they are not an authentication or authorization mechanism.

## 9. Changes Outside the JMX Setter

Configuration values can change via a REST endpoint, scheduler, configuration reload, or autoscaling. If the notification contract is "attribute actually changed," consider emitting events for all change paths, not just the JMX setter.

```text
JMX setter --------+
REST admin --------+--> ConfigService.updateLimit(...)
Scheduled reload --+                  |
                                      v
                              update effective state
                                      |
                                      v
                             publish change event
```

Use shared update logic with validation and old/new snapshots to avoid inconsistent events. For real resources, emit only when the change is applied. For instance, writing the maxWorkers field when resizing the executor failed would make a "MaxWorkers changed" event semantically wrong.

JMX notifications are a management signal, not a replacement for a transactional event log or message broker when durability, retries, or strict ordering are needed.

## 10. Thread Safety and Ordering

Issues to handle:
- Two setters running concurrently can produce wrong old/new snapshots if reads and writes are not synchronized.
- Sequence numbers may differ in order from notification delivery.
- Listeners may be synchronous, slowing down setters if callbacks are expensive.
- A listener may call back into the MBean, creating a deadlock risk if sending inside a lock.
- Remote networks can cause delays, interruptions, or lost notifications.
- Listeners can miss events during reconnection windows.

A pragmatic policy is to synchronize state updates, assign sequences after changes, and emit outside locks; for strong ordering, use a bounded sequential executor/queue. Do not promise exactly-once delivery or replay based solely on JMX.

## 11. Reading MBean Metadata

```java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = connection.getMBeanInfo(target);

for (MBeanNotificationInfo item : info.getNotifications()) {
    System.out.println(item.getName());
    for (String type : item.getNotifTypes()) {
        System.out.println(type);
    }
}
```

If jmx.attribute.change does not appear in metadata, inspect the broadcaster's getNotificationInfo() or the corresponding Spring metadata annotations/assembler. Metadata only describes emission capability; actual testing is required to confirm events are sent when attributes change.

## 12. End-to-End Testing

Test procedure:
1. Register the MBean in a test MBeanServer.
2. Register a NotificationListener that records events into a thread-safe list.
3. Write a valid new value via setAttribute.
4. Read the attribute back to confirm the state changed.
5. Wait for the event with a timeout if the broadcaster is asynchronous.
6. Verify AttributeChangeNotification: attributeName, attributeType, oldValue, newValue, and sequenceNumber.
7. Write the same value again; if the contract emits only on actual change, no additional event is produced.
8. Write an invalid value; state and event count must remain unchanged.
9. Unregister the listener in finally.

Operation example:

```java
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerPool,name=primary"
);
int before = (Integer) server.getAttribute(name, "MaxWorkers");
server.setAttribute(name, new Attribute("MaxWorkers", before + 1));
int after = (Integer) server.getAttribute(name, "MaxWorkers");
assertEquals(before + 1, after);
```

This example assumes before+1 is within the valid range. If multiple actors exist, tests must isolate state or manage event concurrency to avoid flaky results.

## 13. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Setter changes value but no notification | sendNotification not called or publisher not injected yet | Check emission path and exporter lifecycle |
| Notification metadata empty | Missing getNotificationInfo or metadata assembler | Check MBeanInfo |
| Event emitted even when old=new | Actual change not checked | Compare old/new before sending |
| Event sent before state update | Sent before validation or applying state | Emit after successful update |
| Wrong oldValue/newValue | Race between threads | Synchronize snapshot and update |
| Listener slows down setter | Synchronous callback or heavy I/O | Avoid I/O under locks; use an appropriate queue |
| Remote client misses events | Connector/JVM restart | Re-register and reconcile current state |
| ListenerNotFoundException | Removing wrong listener/registration | Manage listener identity and cleanup |
| InstanceNotFoundException | Wrong ObjectName or server | Check MBeanServer and registration |

## 14. Security

AttributeChangeNotification can carry oldValue/newValue. Do not emit passwords, tokens, personal data, or confidential information. If a sensitive attribute must change, you can emit an event with non-sensitive data such as a version or changed status without exposing the value.

Remote JMX requires authentication, authorization, transport protection, and network isolation. NotificationListener is not an authorization tool; connection and operation permissions must be designed at the JMX server/connector.

## 15. Hands-On Exercises

**Exercise 1.** Attribute is currently 8, and the setter writes 12. Create an event named MaxWorkers, type int, oldValue=8, newValue=12, and sequence incremented by one.

**Exercise 2.** Write MaxWorkers=12 again when the value is already 12. If the contract emits only when state changes, should an event be emitted? Answer: No.

**Exercise 3.** The setter receives an out-of-range value. May it emit an event saying the update succeeded? Answer: No; a validation failure is not a successful state transition.

**Exercise 4.** Why does @ManagedAttribute not automatically imply notifications? Because the annotation describes the JMX attribute; MBean code or a Spring publisher still must actively emit events.

**Exercise 5.** Why might a listener receive the 2nd event before the 1st event? Because callbacks or sends happen outside the lock and can be reordered by thread scheduling/remote transport.

**Exercise 6.** After a remote JVM restarts, is the old listener guaranteed to remain valid? No; you must handle re-subscription and state reconciliation.

## 16. Summary

AttributeChangeNotification describes a JMX attribute change with attribute name, data type, old/new values, source, timestamp, and sequence. Standard MBeans can emit it using NotificationBroadcasterSupport; Spring POJOs can use NotificationPublisherAware and NotificationPublisher after being properly exported.

For notifications to be reliable at an operational-observation level, emit after state is applied successfully, control old/new snapshots and concurrency, restrict sensitive data, publish metadata, and manage listener lifecycles. When durable or exactly-once events are required, use a business event system instead of relying solely on JMX notifications.