# Notification type, source, sequence number, and timestamp in JMX

## Objectives

This lesson helps you understand the four main fields of a Java Management Extensions (JMX) Notification, read them via the Java API, emit notifications from a Standard MBean, receive notifications in a listener, and apply those fields properly when diagnosing management events in a Spring Framework application.

You will distinguish:

- **type:** what kind of event occurred.
- **source:** where the event originated.
- **sequence number:** the logical order assigned by the emitter to the notification.
- **timestamp:** the time attached to the notification, measured in milliseconds since the Unix epoch.

These fields serve different roles; understanding them accurately avoids mistakes when filtering events, correlating across multiple JVMs, and reasoning about ordering or timing.

## 1. What is a JMX Notification?

JMX allows an MBean to expose attributes, operations, and notifications. Attributes let you read state, operations let you perform management actions, and notifications inform you that an event has occurred.

For example, a queue management MBean may emit notifications when:

- The queue exceeds a warning threshold.
- The queue returns to normal state.
- Job intake is paused.
- Management configuration is reloaded.

Notifications differ from polling an attribute. A listener receives a message when the broadcaster emits an event; the listener does not need to repeatedly call getters to check for changes.

Java defines the javax.management.Notification class, along with the NotificationBroadcaster, NotificationEmitter, and NotificationListener interfaces. NotificationBroadcasterSupport helps implement a broadcaster with less code.

Conceptual diagram:

    MBean / NotificationBroadcaster
              |
              | sendNotification(Notification)
              v
       Notification listener
              |
              +-- getType()
              +-- getSource()
              +-- getSequenceNumber()
              +-- getTimeStamp()

A notification can also carry message and userData, but this lesson focuses on the four primary metadata fields.

## 2. The Four Core Fields

| Field | Java API | Meaning | Example |
|---|---|---|---|
| type | getType() | Event type identifier | learning.queue.overloaded |
| source | getSource() | Source of the event | MBean ObjectName or emitting object |
| sequence number | getSequenceNumber() | Sequence number assigned by the broadcaster | 27 |
| timestamp | getTimeStamp() | Timestamp of the notification | Epoch milliseconds value |

Together, the four fields answer: **What happened, at which source, with what sequence number, and attached to what point in time?**

They are not equivalent to business IDs, service URLs, trace IDs, or message broker delivery guarantees.

## 3. Notification type: what event?

Type is a String, read via:

\`\`\`java
String type = notification.getType();
\`\`\`

An application can define:

\`\`\`java
public static final String QUEUE_OVERLOADED =
        "learning.queue.overloaded";

public static final String QUEUE_RECOVERED =
        "learning.queue.recovered";

public static final String CONFIG_RELOADED =
        "learning.config.reloaded";
\`\`\`

Those values belong to the application's contract. JMX does not force every custom notification to share the same namespace; however, structured naming helps multiple clients interpret them consistently.

### Type is not a Java class name

Multiple notifications can all be instances of javax.management.Notification while having different types:

\`\`\`java
Notification overload = new Notification(
        "learning.queue.overloaded",
        source,
        1L
);

Notification recovered = new Notification(
        "learning.queue.recovered",
        source,
        2L
);
\`\`\`

Both have the same Java class yet describe two different events. When handling them, use getType() rather than checking only getClass().

### How should types be named?

Recommended convention for custom notifications:

    <namespace>.<component>.<event>

Examples:

    learning.queue.overloaded
    learning.queue.recovered
    learning.cache.invalidated

Names should have stable meaning, be specific enough, and be documented. Avoid changing types unexpectedly because monitoring tools may filter by the old values.

For JDK or library MBeans, prefer official constants and types. For instance, AttributeChangeNotification defines a specific notification type for attribute changes. Do not replace types that are already part of a third-party contract.

### Are types declared in advance?

A broadcaster usually advertises the notification types it can emit using MBeanNotificationInfo:

\`\`\`java
MBeanNotificationInfo info = new MBeanNotificationInfo(
        new String[] {
            "learning.queue.overloaded",
            "learning.queue.recovered"
        },
        Notification.class.getName(),
        "Queue state notifications"
);
\`\`\`

This information serves discovery for JMX tooling. Declaring MBeanNotificationInfo does not automatically emit events; code must still construct and send the Notification.

## 4. Source: where did the event come from?

Source is read via:

\`\`\`java
Object source = notification.getSource();
\`\`\`

The return type is Object, so you cannot assume every notification has a String or ObjectName source.

A Notification can be constructed as follows:

\`\`\`java
Notification notification = new Notification(
        "learning.queue.overloaded",
        this,
        5L
);
\`\`\`

In that case, the code passes the current object as the source. JMX mechanisms may represent the source by the MBean name when the notification passes through the management system. Clients must check the contract and actual runtime value to determine how to interpret it.

### Source and ObjectName

ObjectName is the identifier of an MBean inside an MBeanServer:

    learning.jmx:type=QueueMonitor,name=Primary

You can use ObjectName as the source when appropriate:

\`\`\`java
ObjectName sourceName = new ObjectName(
        "learning.jmx:type=QueueMonitor,name=Primary"
);

Notification notification = new Notification(
        "learning.queue.overloaded",
        sourceName,
        5L
);
\`\`\`

But do not treat ObjectName as a URL for connecting to a JVM. A client wanting to receive notifications from another JVM still needs to connect to the corresponding MBeanServer via a JMX connector.

### Type and source answer two different questions

Example:

    type   = learning.queue.overloaded
    source = learning.jmx:type=QueueMonitor,name=Primary

    type   = learning.queue.overloaded
    source = learning.jmx:type=QueueMonitor,name=Secondary

Two notifications have the same type but originate from two different queues.

A listener can log:

\`\`\`java
System.out.println("Type: " + notification.getType());
System.out.println("Source: " + notification.getSource());
\`\`\`

When handling multiple sources, record both type and source so independent events are not conflated.

### Is source unique across all JVMs?

Not necessarily. An ObjectName is scoped within a single MBeanServer. Two independent JVMs can have the exact same ObjectName:

    learning.jmx:type=QueueMonitor,name=Primary

If aggregating notifications from multiple JVMs, also retain the identity of the source host/instance/connection. source alone is insufficient as a global ID.

## 5. Sequence number: order assigned by the emitter

Read the sequence number:

\`\`\`java
long sequence = notification.getSequenceNumber();
\`\`\`

The sequence number is usually incremented whenever the broadcaster emits a notification:

    overload  -> 1
    recovered -> 2
    overload  -> 3

However, Notification does not define a global counter by itself. The broadcaster or library owning the notification decides the scope and numbering scheme.

### Generating sequence numbers with AtomicLong

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;

private final AtomicLong sequence = new AtomicLong();

long next = sequence.incrementAndGet();
\`\`\`

AtomicLong supports obtaining strictly increasing numbers safely when multiple threads allocate numbers concurrently.

Example creating a notification:

\`\`\`java
Notification notification = new Notification(
        "learning.queue.overloaded",
        this,
        sequence.incrementAndGet(),
        System.currentTimeMillis(),
        "Queue exceeded threshold"
);
\`\`\`

### Sequence number is not a system-wide event ID

Two different MBeans can both emit sequences 1, 2, 3. When a JVM restarts, a new broadcaster can also reset its counter back to 0.

Example:

    JVM A / Queue Primary: 1, 2, 3
    JVM B / Queue Primary: 1, 2, 3

You cannot conclude that notification #2 from JVM A and #2 from JVM B are the same event.

A more reasonable correlation key might include:

    (JVM instance, MBean identity, sequence number)

If the application needs a globally unique correlation ID or event ID, design it separately and place it in supplementary data.

### Does sequence number prove delivery order?

Not necessarily. When multiple threads allocate sequence numbers and then send notifications, a thread with a higher sequence number may send or be processed before a thread with a lower sequence number.

AtomicLong guarantees atomicity of the increment operation; it does not automatically guarantee notification delivery order to all listeners in all environments.

If delivery order must be strict, serialize the emission flow and define a clear ordering contract.

### Can you rely on sequence to detect lost notifications?

Use it only as a hint. Suppose a listener receives 10 and then 13. This could happen because:

- The listener filters only certain types, while the counter increments for all types.
- The listener was registered after some notifications had already been emitted.
- Notifications arrived out of sequence allocation order.
- The broadcaster or client underwent a lifecycle change.
- Some notifications were not delivered to the listener.

By default, JMX notifications are not a durable message queue with replay or exactly-once delivery. Sequence numbers do not turn JMX into an event store.

## 6. Timestamp: the time attached to the notification

Read the timestamp:

\`\`\`java
long timeStamp = notification.getTimeStamp();
\`\`\`

A Notification timestamp usually uses epoch milliseconds: the number of milliseconds since 1970-01-01T00:00:00Z.

Example:

\`\`\`java
Notification notification = new Notification(
        "learning.queue.overloaded",
        this,
        42L,
        System.currentTimeMillis(),
        "Queue overloaded"
);
\`\`\`

Use the Java Time API to display it:

\`\`\`java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

Instant instant = Instant.ofEpochMilli(
        notification.getTimeStamp()
);

String displayed = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm:ss.SSS z")
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .format(instant);

System.out.println(displayed);
\`\`\`

Epoch milliseconds do not carry a timezone; the timezone is applied only when formatting for display.

### Is timestamp when the event happened or when it was received?

This depends on when the broadcaster attaches the timestamp. A notification may be created after the business condition actually occurred. A listener may receive the notification later due to scheduling or transport.

Three points in time must be distinguished:

1. **When the condition occurred** in business logic.
2. **When the notification was created/timestamped.**
3. **When the listener received the message.**

They can differ.

### Does timestamp guarantee absolute ordering?

No. Multiple notifications can share the exact same millisecond timestamp. A machine's clock can be adjusted; clock skew can exist between machines.

Example:

    Event A: sequence=100, timestamp=1762855200123
    Event B: sequence=101, timestamp=1762855200123

Two events with the same timestamp but different sequence numbers are normal.

Do not use timestamp as a unique ID. Do not assume timestamps from two different JVMs can prove exact ordering when clocks are unsynchronized and the event model is not clearly defined.

### Measuring listener latency

You can observe:

\`\`\`java
long receiveTime = System.currentTimeMillis();
long eventTime = notification.getTimeStamp();
long apparentDelay = receiveTime - eventTime;
\`\`\`

This is only **apparent delay**. When broadcaster and listener run on two hosts, clock skew can make the result inaccurate or even negative.

If you need to measure duration within the same process, use a monotonic time source like System.nanoTime() to compute elapsed time, rather than inferring from wall-clock timestamps.

## 7. Complete Example: MBean Emitting Notifications

Create a Standard MBean managing queue state. When depth exceeds 100, the broadcaster emits overload; when it returns to an acceptable level, it emits recovery.

### 7.1. Interface

File QueueMonitorMBean.java:

\`\`\`java
package example.jmx;

public interface QueueMonitorMBean {
    int getDepth();
    boolean isOverloaded();
    void updateDepth(int newDepth);
}
\`\`\`

### 7.2. Implementation and broadcaster

File QueueMonitor.java:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor
        extends NotificationBroadcasterSupport
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
    public synchronized void updateDepth(int newDepth) {
        if (newDepth < 0) {
            throw new IllegalArgumentException(
                    "newDepth must be non-negative"
            );
        }

        depth = newDepth;
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
                new String[] {
                    TYPE_OVERLOADED,
                    TYPE_RECOVERED
                },
                Notification.class.getName(),
                "Queue state changes"
            )
        };
    }
}
\`\`\`

In this example:

- **type** distinguishes overload and recovery.
- **source** is passed as the current broadcaster object.
- **sequence number** increments each time a notification is actually emitted.
- **timestamp** is taken at notification creation time.
- **userData** is the current depth; this is supplementary data, not one of the four primary fields.

The updateDepth method synchronizes the state transition to keep the example easy to follow. In real systems, consider the impact of invoking listeners inside a synchronized block, keep callbacks short, and design management operation permissions clearly. Actual queue depth usually comes from internal processors rather than letting JMX users adjust it directly.

### 7.3. Registering MBean and listener

File NotificationDemo.java:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class NotificationDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "learning.jmx:type=QueueMonitor,name=Primary"
        );

        QueueMonitor monitor = new QueueMonitor();
        server.registerMBean(monitor, name);

        NotificationListener listener =
                (notification, handback) -> {
                    System.out.println(
                        "type=" + notification.getType()
                        + ", source=" + notification.getSource()
                        + ", sequence="
                        + notification.getSequenceNumber()
                        + ", timestamp="
                        + notification.getTimeStamp()
                    );
                };

        server.addNotificationListener(
                name,
                listener,
                null,
                null
        );

        monitor.updateDepth(110);
        monitor.updateDepth(120);
        monitor.updateDepth(50);

        server.removeNotificationListener(name, listener);
        server.unregisterMBean(name);
    }
}
\`\`\`

The expected output is two notifications, because updating from 110 to 120 does not change the overload state.

Sample output:

    type=learning.queue.overloaded, source=..., sequence=1, timestamp=...
    type=learning.queue.recovered, source=..., sequence=2, timestamp=...

source and timestamp depend on the runtime environment as well as how JMX delivers notifications. Do not write tests asserting fixed dynamic values.

## 8. Filtering by type

A listener that only wants to know when the queue is overloaded can use NotificationFilterSupport:

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter =
        new NotificationFilterSupport();

filter.enableType(QueueMonitor.TYPE_OVERLOADED);

server.addNotificationListener(
        name,
        listener,
        filter,
        null
);
\`\`\`

Note that NotificationFilterSupport matches by **prefix** of the notification type. If a general prefix like learning.queue is enabled, the listener can receive multiple types starting with that prefix.

To match exactly one type:

\`\`\`java
import javax.management.NotificationFilter;

NotificationFilter filter =
        n -> QueueMonitor.TYPE_OVERLOADED.equals(n.getType());
\`\`\`

A listener that filters out some events may see gaps in sequence numbers. This does not by itself prove that messages were lost.

## 9. Applying in Spring Framework

Spring Framework supports publishing MBeans via MBeanExporter and annotation-based management metadata mechanisms. Even when an MBean is instantiated by Spring, the type, source, sequence number, and timestamp fields still carry their Java JMX meaning.

Example configuration exporting a Standard MBean:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    MBeanExporter queueMonitorExporter(QueueMonitor monitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(
                ManagementFactory.getPlatformMBeanServer()
        );
        exporter.setBeans(Map.of(
                "learning.jmx:type=QueueMonitor,name=Primary",
                monitor
        ));
        return exporter;
    }
}
\`\`\`

Spring manages the bean and the exporter's lifecycle. The MBean must still expose notifications according to the JMX contract. JConsole or a JMX client wanting to observe an MBean in another JVM must connect to the right JVM with sufficient permissions and register a listener via MBeanServerConnection.

Distinguish JMX Notification from Spring ApplicationEvent: Spring ApplicationEvent primarily serves internal communication within the application context. JMX Notification is a management contract for JMX listeners. The two mechanisms can be integrated, but they are not automatically equivalent.

## 10. Cases with Multiple MBeans or Multiple JVMs

Suppose there are two JVMs:

    JVM-A: type=learning.queue.overloaded
           source=learning.jmx:type=QueueMonitor,name=Primary
           sequence=8

    JVM-B: type=learning.queue.overloaded
           source=learning.jmx:type=QueueMonitor,name=Primary
           sequence=8

These can be two separate events. Even though ObjectName and sequence are identical, the MBeanServer/JVM identities differ.

When sending notifications to a centralized logging system, add metadata such as:

- service and instance ID;
- hostname/pod ID if needed;
- ObjectName or source identifier;
- notification type;
- sequence number scoped to the broadcaster;
- timestamp and collector receive time;
- correlation ID if needed to associate the event with a request or business action.

Do not place sensitive data such as tokens, passwords, or personal information into source, message, or userData. Management clients can log and forward these fields.

## 11. Ordering, Reliability, and Limitations

### Notification is not a message broker

JMX notifications are typically used to observe runtime state and management events. They do not provide by default:

- durable storage;
- replay of previously emitted events;
- exactly-once delivery;
- acknowledgement from all listeners;
- global ordering across JVMs.

If those properties are required, use a messaging/event log system with an appropriate contract. JMX can still be used to monitor that system.

### Sequence and timestamp do not replace each other

sequence number is logical order **assigned by the emitter**. timestamp is the time attached to the event according to the clock. Notifications can have different sequence numbers yet share the same timestamp; or callbacks can arrive at listeners out of sequence allocation order.

### Keep listeners simple

Listeners should perform brief work and avoid slow network operations or unbounded blocking inside callbacks. If heavier processing is needed, hand off data to an executor or internal queue with clear bounds.

### Do not automatically treat gaps as data loss

When a listener receives sequence 5 then 9, examine filters, listener registration timing, the broadcaster's counter, and concurrency. Only conclude notifications were lost if the source contract and delivery mechanism prove it.

## 12. Common Pitfalls Table

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Listener does not distinguish event types | Only reads message, ignores type | Use getType() |
| Two sources get merged into one | Ignores source or instance ID | Record both source and JVM identity |
| Duplicate sequences across two JVMs | Independent counters | Do not use sequence as a global ID |
| Sequence jumps after filtering | Filter skips other types | Check counter contract |
| Notifications arrive out of sequence order | Concurrent sends/transport | Inspect numbering and emission order |
| Duplicate timestamps | Time resolution | Do not use timestamp as an ID |
| Negative delay when computing latency | Clock skew | Check host clocks |
| Listener receives no events | Wrong ObjectName, not registered, skipped by filter | Check broadcaster/listener |
| JConsole shows no notifications | MBean did not advertise broadcaster metadata | Check NotificationBroadcaster and getNotificationInfo() |
| Notifications lost after restart | No durable store | Use a broker/event store if replay is needed |

## 13. Exercises

### Exercise 1: Reading metadata

Given a notification:

    type = learning.cache.invalidated
    source = learning.jmx:type=Cache,name=Products
    sequenceNumber = 17
    timeStamp = 1762855200000
    message = Cache invalidated

Answer:

1. Which field indicates the event type?
2. Which field indicates the source?
3. Does sequence 17 prove this is the 17th event across all JVMs?
4. Is timestamp when the listener received it or the time attached to the notification?
5. Should you parse message to distinguish events if type already has a contract?

Suggested answer: type identifies the kind; source identifies the origin; sequence is scoped to the broadcaster; timestamp is the time attached to the notification; use stable type values for automation.

### Exercise 2: Filtering notifications

From the QueueMonitor example, register two listeners: one receiving all types and one receiving only learning.queue.overloaded. Perform three state transitions: overload, recovered, overload. Compare the sequence numbers observed by the two listeners and explain why the filtered listener sees a non-contiguous sequence.

### Exercise 3: Multi-source analysis

Given the logs:

    source=Queue-A, type=overloaded, seq=8, ts=1000
    source=Queue-B, type=overloaded, seq=8, ts=1002
    source=Queue-A, type=recovered, seq=9, ts=1020

Timestamps here are illustrative values. Can the two seq=8 records be considered duplicates? Why? If Queue-A and Queue-B belong to two different JVMs, what additional information is needed to distinguish sources reliably?

Answer: no; sequence numbers are not unique across broadcasters. Retain JVM/instance identity and the appropriate ObjectName.

## 14. Notification Design Checklist

Before introducing a custom Notification into an application:

1. Define stable types and document the event kinds.
2. Clearly define source and how instances are identified remotely.
3. Define sequence number scope, when it resets, and how it increments safely.
4. Attach timestamps at a meaningful point, and document what that point represents.
5. Expose getNotificationInfo() for supported types.
6. Keep message understandable and userData compact and non-sensitive.
7. Design type-based filters appropriately.
8. Do not assume listeners receive events in global order or with replay.
9. Keep callbacks short and handle listener errors safely.
10. Treat JMX notifications as a management channel; if a durable event stream is needed, use a dedicated system.

## 15. Remember

**type answers "what event", source answers "which source", sequence number represents the logical order assigned by the emitter, and timestamp represents the time attached to the notification.**

No single field on its own guarantees global identity or reliable delivery. When building a Spring Framework system with notification-emitting MBeans, combine the four fields with the broadcaster contract, ObjectName, instance identity, listener filters, and clear operational guidelines.

## References

- Java SE 21 Notification API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Java SE 21 NotificationBroadcasterSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 NotificationFilterSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationFilterSupport.html
- Java SE 21 MBeanNotificationInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanNotificationInfo.html
- Spring Framework JMX reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
