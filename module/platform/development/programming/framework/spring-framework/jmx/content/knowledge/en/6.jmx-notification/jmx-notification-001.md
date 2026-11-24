# What is a JMX Notification and How Does It Differ from Periodic Metric Polling?

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain **JMX Notification** as an event message emitted by an MBean to listeners when a noteworthy event occurs.
- Distinguish between the **event-driven push** mechanism and **periodic metric polling** via JMX attributes.
- Understand the roles of \`NotificationBroadcaster\`, \`NotificationEmitter\`, \`NotificationListener\`, \`NotificationFilter\`, and \`MBeanServer\`.
- Write a Standard MBean that emits notifications, register a listener, and receive and handle messages.
- Know when to use notifications, metrics, or a combination of both to monitor Spring applications.
- Identify limitations such as missed events, listener lifecycle, processing threads, and security or load-handling requirements.

## 2. Context: Observing State or Reacting to Events?

In Java Management Extensions (JMX), an application often needs to answer two different questions:

1. **What is the current state?** For example: how many requests are currently being processed, what is the current cache size, or how many workers remain in a thread pool.
2. **What just happened?** For example: a queue just crossed a warning threshold, a cache was just cleared, a task just failed, or a service just transitioned to a degraded state.

To answer the first question, an MBean typically exposes **JMX attributes**. Monitoring tools query \`getAttribute\` on a schedule: every 5 seconds, 30 seconds, or 1 minute depending on configuration.

To answer the second question, an MBean can **emit a JMX Notification** when an event occurs. Registered listeners receive the message without having to continuously ask whether the event has happened.

Example of an order-processing queue:

\`\`\`text
Time:               10:00       10:01       10:02       10:03

Queue size:            20          42          95          35
Metric polling:        20          42          95          35
Actual event:                      exceeded threshold 80 at 10:01:45

JMX Notification:                  QueueThresholdExceeded
                                   emitted as soon as detected
\`\`\`

With 1-minute polling, a dashboard may see a queue size of 95 at 10:02; with notifications, a listener can receive the signal as soon as the application detects that the queue has crossed the threshold. However, actual delivery time still depends on how the notification is emitted, threads, connections, and client state; notifications do not guarantee zero latency.

## 3. What is a JMX Notification?

\`javax.management.Notification\` is an object representing a **management event notification**. The message typically contains:

| Property | Meaning |
|---|---|
| \`type\` | String identifying the event type, e.g., \`com.example.shop.queue.threshold.exceeded\` |
| \`source\` | Event emission source; when working through MBeanServer, it may be represented by an ObjectName |
| \`sequenceNumber\` | Sequence number managed by the emission source |
| \`timeStamp\` | Timestamp attached to the notification (milliseconds since epoch) |
| \`message\` | Human-readable descriptive content |
| \`userData\` | Optional additional data; serializability and client compatibility must be considered |

Example:

\`\`\`java
Notification event = new Notification(
        "com.example.shop.queue.threshold.exceeded",
        this,
        18L,
        System.currentTimeMillis(),
        "Order queue exceeded threshold 80"
);
\`\`\`

Notification belongs to the JMX management system. It is not synonymous with Spring \`ApplicationEvent\`, a JMS message, a Kafka record, or a log event. These mechanisms can coexist in the same system, but they differ in API, purpose, lifecycle, and delivery guarantees.

**Easy-to-remember definition:** *A metric describes a value/state; a notification informs that a management event has occurred.*

Not every MBean automatically emits notifications. An MBean must implement a broadcaster/emitter mechanism or be configured by a framework to support emitting events.

## 4. Structure of the Notification Mechanism

Key components:

| Component | Role |
|---|---|
| \`Notification\` | Event payload sent to listeners |
| \`NotificationBroadcaster\` | Contract allowing adding/removing listeners and declaring notification types |
| \`NotificationEmitter\` | Extends broadcaster with removing a listener by a specific filter/handback |
| \`NotificationBroadcasterSupport\` | Common utility class supporting listener management and sending notifications |
| \`NotificationListener\` | Callback \`handleNotification(notification, handback)\` that receives events |
| \`NotificationFilter\` | Decides whether a notification should be forwarded to a listener |
| \`MBeanServer\` | Allows registering MBeans and managing listeners via ObjectName |

Operational flow:

\`\`\`text
                 Application updates state
                             |
                             v
                   MBean emits Notification
                             |
                    NotificationBroadcaster
                             |
                    +--------+--------+
                    |                 |
                    v                 v
             Listener A          Listener B
             filters by         handles all
             threshold          matching events

Independent of the flow above:
Monitoring client -- getAttribute --> MBean --> current value
\`\`\`

The broadcaster manages the list of listeners. A listener can be attached directly to the broadcaster object or registered via \`MBeanServer.addNotificationListener\` with the MBean's ObjectName.

For applications with multiple listeners, filters help avoid processing irrelevant notification types. They do **not** replace JMX access control mechanisms.

## 5. How Does Periodic Metric Polling Work?

In JMX, an MBean can expose attributes such as:

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
    long getProcessedCount();
    boolean isPaused();
}
\`\`\`

Monitoring tools call:

\`\`\`java
Object pending = server.getAttribute(
        objectName, "PendingCount");
\`\`\`

periodically. With a monitoring system, the data can be stored as a time series:

\`\`\`text
t=0s   PendingCount=12
t=30s  PendingCount=28
t=60s  PendingCount=95
t=90s  PendingCount=20
\`\`\`

Polling is convenient for dashboards and alerts based on sustained states, averages, rates of increase/decrease, percentiles, or historical trends. A single poll usually only tells you the value at read time (or the snapshot reflected by the attribute), so it can miss short-lived spikes occurring between two samples.

For example, if a queue spikes to 110 and drops back to 10 between two 30-second polls, collecting only \`PendingCount\` might never show the peak of 110. A notification emitted when crossing the threshold can reflect that event, provided a listener is registered and the transport path is working.

## 6. Comparing Notification and Metric Polling

| Criterion | JMX Notification | JMX Attribute Polling |
|---|---|---|
| Model | Pushes events to listeners | Client pulls values periodically |
| Suitable question | "What just happened?" | "What is the current state?" |
| Data timing | When the application decides to emit an event | When the client reads the attribute |
| Data | Event type, source, timestamp, message, userData | Current values such as size, count, state |
| Frequency | Depends on the number of events occurring | Depends on the interval |
| When no event occurs | Usually sends no messages | Can still read to confirm state |
| Very brief events | Can detect if the application emits at the right moment | Can be missed between polls |
| Historical collection | Requires a listener and consumer-side storage | Easy to integrate into time series with collection intervals |
| Overhead | Scales with the number of events and listeners | Scales with the number of MBeans/attributes and poll frequency |
| Reliability | Does not come with built-in persistence, ack, or replay | Each poll provides a fresh snapshot if connection succeeds |
| Alerting | Suitable for edge/event, state transitions | Suitable for sustained thresholds, trends, rates |
| Late listener startup | May miss events that already occurred | Can read the current state immediately |

**Key point:** Notification and polling are not mutually exclusive. A good design typically uses **metrics to know state and trends**, and **notifications to report important events at the moment they occur**.

Notifications should not be treated as a guaranteed-delivery event queue. The JMX notification API does not provide durable storage, retry, acknowledgement, or replay by default. If a business event must never be lost, an appropriate messaging/persistence mechanism is needed alongside or instead of notifications.

## 7. Complete Example: Standard MBean with Both Metrics and Notifications

Let us create a \`QueueMonitor\` with:

- Attribute \`PendingCount\` for polling.
- Operation \`enqueue(int amount)\` simulating adding work.
- A notification when the queue transitions from below/at the threshold to **above** the threshold.

### 7.1 Management interface

**\`QueueMonitorMBean.java\`**

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
    int getWarningThreshold();
    void enqueue(int amount);
    void clear();
}
\`\`\`

The interface determines the attributes and operations visible to JMX clients. Notifications are supported via \`NotificationBroadcasterSupport\` in the implementation class.

### 7.2 Implementation class emitting notifications

**\`QueueMonitor.java\`**

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    public static final String THRESHOLD_EVENT =
            "com.example.shop.queue.threshold.exceeded";

    private final AtomicLong sequence = new AtomicLong();
    private final int warningThreshold;
    private int pendingCount;

    public QueueMonitor(int warningThreshold) {
        if (warningThreshold < 0) {
            throw new IllegalArgumentException(
                    "warningThreshold must be >= 0");
        }
        this.warningThreshold = warningThreshold;
    }

    @Override
    public synchronized int getPendingCount() {
        return pendingCount;
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void enqueue(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException(
                    "amount must be positive");
        }

        final int before;
        final int after;

        synchronized (this) {
            before = pendingCount;
            pendingCount = Math.addExact(pendingCount, amount);
            after = pendingCount;
        }

        if (before <= warningThreshold && after > warningThreshold) {
            Notification event = new Notification(
                    THRESHOLD_EVENT,
                    this,
                    sequence.incrementAndGet(),
                    System.currentTimeMillis(),
                    "Queue exceeded threshold: " + after
            );
            event.setUserData(after);
            sendNotification(event);
        }
    }

    @Override
    public synchronized void clear() {
        pendingCount = 0;
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {THRESHOLD_EVENT};
        return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                        types,
                        Notification.class.getName(),
                        "Queue warning threshold crossed")
        };
    }
}
\`\`\`

Explanation:

- \`QueueMonitorMBean\` exposes management information for the queue; \`PendingCount\` and \`WarningThreshold\` are attributes.
- \`NotificationBroadcasterSupport\` provides listener registration and \`sendNotification\`.
- \`getNotificationInfo()\` informs tools about the notification types that may be emitted.
- \`AtomicLong\` provides an incrementing sequence number for each event from this emitter.
- When \`pendingCount\` **crosses** the threshold, the MBean emits an event. Subsequent increases while already above the threshold do not re-emit unless it goes back below/at the threshold first.
- \`userData\` contains an Integer representing the pending count at emission time.

This short example uses \`synchronized\` to protect state; production code needs synchronization and event emission ordering designed for the module's concurrency characteristics. In the example, \`sendNotification\` is called after releasing the lock to avoid holding the monitor lock while listeners run. With concurrent operations, a listener might observe a newer metric than the notification payload; the event still represents the crossing that was emitted.

### 7.3 Registering the MBean and listener

**\`NotificationDemo.java\`**

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class NotificationDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=QueueMonitor,name=outbox");

        QueueMonitor monitor = new QueueMonitor(80);
        server.registerMBean(monitor, name);

        NotificationListener listener = (event, handback) -> {
            System.out.println(
                    "[EVENT] " + event.getType()
                    + " #" + event.getSequenceNumber()
                    + " value=" + event.getUserData());
        };

        NotificationFilterSupport filter =
                new NotificationFilterSupport();
        filter.enableType(QueueMonitor.THRESHOLD_EVENT);

        try {
            server.addNotificationListener(name, listener, filter, null);
            try {
                System.out.println("Initial metric: "
                        + server.getAttribute(name, "PendingCount"));

                server.invoke(name, "enqueue",
                        new Object[] {50}, new String[] {"int"});
                server.invoke(name, "enqueue",
                        new Object[] {40}, new String[] {"int"});

                System.out.println("Current metric: "
                        + server.getAttribute(name, "PendingCount"));
            } finally {
                server.removeNotificationListener(name, listener);
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Sample output:

\`\`\`text
Initial metric: 0
[EVENT] com.example.shop.queue.threshold.exceeded #1 value=90
Current metric: 90
\`\`\`

Because the example uses the default \`NotificationBroadcasterSupport\`, the listener is invoked synchronously on the thread emitting the notification. If a custom executor is configured, or with a JMX remote client, display order/timing may vary. Do not rely on stdout timing as an API guarantee.

### 7.4 Running the example

Save the three files in the same directory/package and run:

\`\`\`bash
javac QueueMonitorMBean.java QueueMonitor.java NotificationDemo.java
java NotificationDemo
\`\`\`

First, \`enqueue(50)\` raises the count from 0 to 50, not yet exceeding 80. Second, \`enqueue(40)\` brings the count to 90 and emits a notification. Reading \`PendingCount\` returns 90 even after the listener has finished handling the event.

The program exits after removing the listener and unregistering the MBean. To observe via JConsole, keep the JVM alive while the registration exists.

## 8. Two Ways to Register a Listener

### Approach A: via MBeanServer

\`\`\`java
server.addNotificationListener(objectName, listener, filter, handback);
\`\`\`

This approach is suitable when the client knows the ObjectName and wants to interact with the MBean through the standard JMX interface. \`MBeanServer\` identifies the broadcaster by its registered name.

### Approach B: directly on the emitter

\`\`\`java
QueueMonitor monitor = new QueueMonitor(80);
monitor.addNotificationListener(listener, filter, null);
\`\`\`

This approach suits in-JVM code that already holds a reference to the object, but it does not replace ObjectName registration if you want external JMX tools to look up the MBean.

In both approaches, remove the listener when no longer in use to avoid accumulating callbacks and retaining unnecessary objects. With removal APIs that have multiple overloads, use the exact listener/filter/handback when you need to remove a specific registration.

## 9. Filter, Handback, and Metadata

### Filter

\`NotificationFilter\` takes a notification and returns \`true\` if the event should be forwarded to the listener. \`NotificationFilterSupport\` supports notification type prefixes:

\`\`\`java
NotificationFilterSupport filter =
        new NotificationFilterSupport();

filter.enableType("com.example.shop.queue.");
\`\`\`

The filter above accepts types with the prefix \`com.example.shop.queue.\`, such as \`threshold.exceeded\` or \`consumer.stalled\`.

If you only want a single event type, provide the full type string. Filters can reduce unnecessary callbacks, but they are not an access control mechanism.

### Handback

\`handback\` is an object provided by the listener registrant and passed back to the callback:

\`\`\`java
Object handback = "orders-dashboard";

server.addNotificationListener(name, listener, filter, handback);
\`\`\`

In the callback, the second parameter helps distinguish the registration context. It is not by default a payload created by the broadcaster; the payload resides in \`Notification\`/\`userData\`.

### Metadata

\`MBeanNotificationInfo\` describes the notification types an MBean can emit. It can be read via \`MBeanServer.getMBeanInfo(objectName).getNotifications()\`.

Do not assume that merely declaring metadata will produce events. The MBean must **actually invoke the emission mechanism**, such as \`sendNotification\`, at the appropriate time.

## 10. Metrics and Events Handling the Same Scenario

Suppose you need to alert when the number of pending jobs exceeds 100.

**Polling-only approach:**

1. Dashboard reads \`PendingCount\` every 15 seconds.
2. If greater than 100 for three consecutive cycles, trigger an alert.
3. Sustained states are detected; very short spikes may be missed.

**Notification-only approach:**

1. Application emits an event when the count first exceeds 100.
2. Listener can alert immediately.
3. If the listener just restarted or lost connection at the time of the event, it may miss the signal. There is no default snapshot to know that the count is still at 130.

**Combined approach:**

1. Maintain \`PendingCount\` for dashboards and tools to poll.
2. Emit a notification when crossing the threshold.
3. When a listener newly connects or reconnects, immediately read \`PendingCount\` to obtain the current state.
4. Upon receiving a notification, re-read necessary attributes to verify and update the dashboard.
5. Use metric-based alerts to detect sustained conditions and event alerts to react to state transitions.

This combines event-driven and state-based monitoring: notifications tell you what happened, while metrics tell you **what state the system is currently in**.

## 11. Edge Events and Level/State Conditions

Distinguish between:

- **Edge event:** "The queue just exceeded the threshold" (emitted only at the transition from not exceeding to exceeding).
- **Level/state:** "The queue is currently above the threshold" (may remain true for many minutes).

If an event is emitted only once on crossing, a late-registering listener will not automatically have the existing state "replayed" to it. Metric polling is better suited for determining the current state.

Some designs add a notification when the state recovers:

\`\`\`text
com.example.shop.queue.threshold.exceeded
com.example.shop.queue.threshold.recovered
\`\`\`

Two types help the system represent an incident's lifecycle. However, relying solely on the event pair carries the risk of missing a message; therefore, a metric snapshot or another state-synchronization mechanism is still needed.

For rate metrics or cumulative counters, notifications should correspond to state transitions or management events that genuinely require action. Avoid emitting a notification for every increment if the frequency can be extremely high.

## 12. Threads, System Load, and Listener Processing

\`NotificationBroadcasterSupport\` can use an \`Executor\` to run callbacks instead of executing them directly on the event-emitting thread. This choice noticeably affects latency, execution order, and system load.

Example using an executor:

\`\`\`java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.management.NotificationBroadcasterSupport;

ExecutorService executor = Executors.newSingleThreadExecutor();

NotificationBroadcasterSupport broadcaster =
        new NotificationBroadcasterSupport(executor);

// In the component shutdown lifecycle:
// executor.shutdown();
\`\`\`

The example above illustrates configuring an executor via constructor. In real applications, manage the executor's lifecycle alongside the component and handle callback errors. If events arrive faster than processing speed, the executor queue can grow. With \`newSingleThreadExecutor()\`, the default queue has no fixed bound, so backpressure and memory resources must be considered. Do not use an unbounded queue for workloads that can emit bursts of events without load evaluation.

When designing notifications:

- Keep payloads small and easy to understand.
- Do not make critical business operations depend on listeners succeeding.
- Use clear types; define versions if payload schemas change incompatibly.
- Do not put sensitive information into message or \`userData\`.
- Consider rate limiting, debouncing, or emitting only on state transitions.
- Monitor listener errors and client connectivity.

Notifications can cause an "event storm" if emitted every time a value fluctuates around a threshold. **Hysteresis** can be used: emit exceeded when above 100, and consider recovered only when dropping below 80, helping avoid repeated alert flapping.

## 13. Sequence Numbers, Timestamps, and Reliability

### Sequence number

\`Notification.sequenceNumber\` helps consumers track the order of notifications sent by an emission source. JMX does not enforce how the counter is durably stored or guarantee that consumers will receive every consecutive number. Sequences are useful for observing or detecting potential gaps, but are not absolute proof when an MBean restarts/resets its counter or when multiple sources exist.

Using \`AtomicLong.incrementAndGet()\` is one way to generate consistent sequences within an emitter. Do not use \`System.currentTimeMillis()\` as a sequence number if strict monotonicity is needed.

### Timestamp

\`timeStamp\` is usually assigned when the event is emitted, but it is a value from the clock provided by the application. It is not a guarantee of when the client receives the event. Clock skew, network latency, or executor queues cause the two times to differ.

### Delivery

JMX notifications do not support by default:

- A durable log surviving restarts.
- Exactly-once delivery.
- Application-level retry/acknowledgment.
- Replaying events missed by a listener.

Over a remote JMX connection, notification delivery and reconnection are also affected by the network/connector implementation. If a business event must not be lost (for example, payment settlement), use a message broker or transactional outbox/durable queue according to system requirements, and optionally emit a JMX notification as an auxiliary observability signal.

## 14. Notifications in Spring Framework

Spring Framework has JMX integration to export beans via \`MBeanExporter\` and annotations such as \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\`. It also supports notification-related mechanisms, such as \`NotificationPublisher\` for exported beans to emit JMX notifications through Spring.

Conceptual example with a bean:

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
        objectName = "com.example.shop.orders:type=Queue,name=outbox")
public class OutboxMonitor implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile int pendingCount;

    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }

    public void onThresholdExceeded(int count) {
        pendingCount = count;

        NotificationPublisher currentPublisher = publisher;
        if (currentPublisher != null) {
            Notification event = new Notification(
                    "com.example.shop.queue.threshold.exceeded",
                    this,
                    sequence.incrementAndGet(),
                    System.currentTimeMillis(),
                    "Outbox exceeded threshold: " + count
            );
            event.setUserData(count);
            currentPublisher.sendNotification(event);
        }
    }
}
\`\`\`

**Usage requirements:** \`OutboxMonitor\` must actually be a Spring bean exported via JMX by \`MBeanExporter\` configured to support annotations and notification publishers. Merely having annotations and \`NotificationPublisherAware\` on the class does not automatically make an MBean appear. \`onThresholdExceeded\` is a method called by the application when detecting the state, not automatically a JMX operation.

In Spring Boot applications, JMX export may need appropriate configuration enabled; do not assume every \`@ManagedResource\` is automatically exported if JMX is not enabled. Additionally, \`NotificationPublisher\` in Spring is a JMX integration API, **not synonymous** with Spring's \`ApplicationEventPublisher\`.

### Comparing Spring ApplicationEvent and JMX Notification

| | Spring ApplicationEvent | JMX Notification |
|---|---|---|
| Goal | Event communication inside a Spring application | MBean management notifications |
| Publisher | \`ApplicationEventPublisher\` | \`NotificationPublisher\` or JMX broadcaster |
| Consumer | \`@EventListener\`/\`ApplicationListener\` | JMX \`NotificationListener\` |
| Typical scope | Application context | MBeanServer/JMX connector |
| Strength | Organizing events between components | Integrating Java monitoring and management tools |

Do not emit JMX notifications for every internal business event. Only expose events that have operational significance for administrators.

## 15. When to Choose Which Mechanism?

### Use metric polling when

- You need dashboards for CPU, memory, queue depth, thread count, or cache size.
- You need time-series charts, averages, rates, trends, or capacity analysis.
- You want to know the state immediately after a client connects/reconnects.
- You need to detect a condition that persists across multiple collection intervals.
- You have an observability system that natively pulls data.

### Use notifications when

- You need to know when a state **transitions** to error or degraded.
- There are infrequent but noteworthy management events.
- You want to inform the monitoring system that an MBean just changed configuration or a threshold was crossed.
- You need lifecycle information such as component stopped/restarted or resource removed.
- The MBean emits events at a controllable frequency.

### Combine both when

- An event has immediate significance, yet current status must still be displayed.
- Clients may disconnect and come back.
- Both realtime signals and historical time series are needed.
- You want to use a notification to trigger an immediate attribute read alongside periodic polling.

Do not choose notifications assuming "push is always better than pull". Requirements, reliability, event frequency, and existing monitoring tools determine the right design.

## 16. Common Pitfalls

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Listener does not receive events | Not registered, wrong ObjectName, or filter mismatch | Check \`addNotificationListener\`, notification type, \`getMBeanInfo\` |
| MBean has attributes but emits no notifications | MBean does not implement emitter/broadcaster or never calls \`sendNotification\` | Check emission path at the event condition |
| MBean unregistered while listener is still active | Inconsistent registration/listener lifecycle | Tie cleanup to lifecycle and handle reconnects |
| Events repeat too often | Value fluctuates around threshold or emitter fires on every update | Use state transition/hysteresis/debounce |
| Events occur but dashboard lacks latest state | Notification only reports occurrences, not continuous snapshots | Re-read attributes and keep metric polling |
| Events missed while client is offline | Notifications lack built-in durable replay | Reconnect + read state; use durable messaging if required |
| Application slows down when emitting events | Heavy listener processing or overloaded executor | Optimize callbacks, limit load, consider executor |
| Client sees type but not expected payload | Mismatched metadata/payload or wrong filter | Check \`MBeanNotificationInfo\`, \`userData\`, compatibility |
| Confusing JMX events with Spring events | Different APIs and consumers | Clarify which publisher/listener is needed |
| Exception thrown on invoke | Operation/attribute mapping or implementation logic error | Inspect \`MBeanInfo\` and relevant stack trace |

## 17. Practice Exercises

### Exercise 1 — What can polling miss?

A queue has values:

\`\`\`text
00s: 10
05s: 130
10s: 20
15s: 15
\`\`\`

Monitoring polls every 15 seconds. Explain why the metric series may only show 10 and 15, while a notification emitted at 05s can report the event of the queue exceeding 100.

**Hint:** Metric polling captures snapshots at read time, whereas events reflect emitted state transitions. When a listener is offline, notifications can still be missed.

### Exercise 2 — Designing an MBean for a pool

A connection pool has metrics \`ActiveConnections\`, \`IdleConnections\`, \`MaxConnections\`. When a connection cannot be acquired within 3 seconds, the application can emit \`com.example.shop.pool.acquire.timeout\`.

Identify:

1. Which measurements should be attributes.
2. The notification type and minimal payload sufficient for operations.
3. How a listener registers and filters by the prefix \`com.example.shop.pool.\`.
4. How a dashboard refreshes its snapshot immediately after reconnecting.

### Exercise 3 — Writing a filter

Given the types:

\`\`\`text
com.example.shop.queue.threshold.exceeded
com.example.shop.queue.threshold.recovered
com.example.shop.pool.acquire.timeout
\`\`\`

Write a \`NotificationFilterSupport\` that receives only queue events.

Suggested answer:

\`\`\`java
NotificationFilterSupport filter =
        new NotificationFilterSupport();
filter.enableType("com.example.shop.queue.");
\`\`\`

### Exercise 4 — Adding a recovery event

Extend \`QueueMonitor\`:

- Emit \`threshold.exceeded\` when pending increases from \`<= 100\` to \`> 100\`.
- Emit \`threshold.recovered\` when pending decreases from \`>= 80\` to \`< 80\`, after already being in the warning state.
- Keep \`PendingCount\` as an attribute so clients can still read the current state.

The goal is to avoid notification spam when the queue fluctuates around the threshold.

### Exercise 5 — Handling a late-registering listener

Add a listener after the queue is already at 120. Determine whether the listener will automatically receive the earlier crossing notification, then read \`PendingCount\` to synchronize state. Propose a reconnect strategy that both fetches a snapshot and tracks new events.

## 18. Self-Check Questions

**1. Is a JMX Notification a metric?**

No. A notification is a message about an event; a metric is typically an attribute value or a time series of measurements.

**2. If there are no events, does a notification listener know the queue is still normal?**

Not necessarily. It only knows the events it has received. To determine the current state, you must read attributes or use another synchronization mechanism.

**3. If a collector polls every 1 minute, can a 2-second spike be missed?**

Yes. If the spike falls completely between two samples and the attribute only displays the current value, polling may miss it. A notification can report it if the application emits an appropriate event.

**4. Does \`NotificationBroadcasterSupport\` durably store events by default so offline clients can receive them later?**

No. It manages delivery to listeners and does not provide durable logging/replay by itself.

**5. How does \`NotificationFilterSupport.enableType\` match event types?**

It allows notifications whose type starts with the enabled prefix.

**6. Is Spring JMX's \`NotificationPublisher\` the same as \`ApplicationEventPublisher\`?**

No. One API emits JMX notifications, while the other publishes Spring application events.

**7. Once notifications are in place, can metric polling be removed?**

It should not be removed by default. Notifications help react to events, while metrics provide snapshots and support historical queries.

## 19. Summary

- **A Notification is an event signal** emitted by an MBean to registered listeners; polling is a client **periodically reading state** from JMX attributes.
- Notifications suit state transitions, threshold crossings, errors, or rare but noteworthy management occurrences.
- Polling suits current state, dashboards, trends, rates, and detecting sustained conditions.
- A JMX notification has metadata \`type\`, \`source\`, \`sequenceNumber\`, \`timeStamp\`, \`message\`, and \`userData\`; broadcasters and listeners coordinate to emit/receive events.
- There is no default durable delivery, acknowledgement, or replay. If a listener connects late, read metrics to synchronize state.
- Spring Framework integrates \`NotificationPublisher\`, but bean export must be configured and it must not be confused with \`ApplicationEventPublisher\`.
- Real-world designs typically combine **metrics for observing state** and **notifications for reporting events**, along with reconnect handling, filtering, load control, and listener lifecycle management.

## 20. References

- Java SE 21 — \`javax.management.Notification\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Java SE 21 — \`javax.management.NotificationBroadcasterSupport\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 — \`javax.management.NotificationListener\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE 21 — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Oracle JMX Tutorial — Notifications: https://docs.oracle.com/javase/tutorial/jmx/notifs/
- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
