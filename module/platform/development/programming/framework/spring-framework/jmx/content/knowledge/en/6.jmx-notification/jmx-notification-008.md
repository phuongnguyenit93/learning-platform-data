# Ordering, Lost Notifications, and Delivery Guarantee Limits in JMX

## 1. Objectives

Java Management Extensions (JMX) allows MBeans to emit notifications about state changes, alerts, and management events. Spring Framework can integrate this mechanism via JMX exporters, \`NotificationPublisher\`, and listeners.

However, **receiving notifications is not synonymous with receiving a guaranteed-delivery event stream like a message broker**. A notification can be processed slowly, missed when a listener has not registered yet, lost when a remote JMX connection drops, or become unobservable when the JVM process terminates. Sequence numbers help track the emission source, but do not create a replay mechanism.

After this lesson, you will be able to:

- Distinguish creation order, emission order, dispatch order, callback order, and actual observed order.
- Understand the scope and limitations of \`Notification.sequenceNumber\`.
- Identify scenarios where notifications are lost or missed.
- Explain why JMX does not provide *exactly-once*, *at-least-once*, durable storage, or notification replay by default.
- Design fault-tolerant consumers by checking current state, detecting gaps, reconnecting, and resynchronizing.
- Choose the right tool when notifications require high reliability and long-term auditing.

## 2. What Is a Notification?

In JMX, a notification-emitting object typically implements \`NotificationBroadcaster\` or \`NotificationEmitter\`. A \`Notification\` contains information such as:

- \`type\`: event classification string.
- \`source\`: emission source.
- \`sequenceNumber\`: sequence number set by the emitter.
- \`timeStamp\`: timestamp assigned to the notification.
- \`message\`: description.
- \`userData\`: optional supplementary data.

A \`NotificationListener\` receives callbacks:

\`\`\`java
void handleNotification(Notification notification, Object handback);
\`\`\`

Examples of events:

\`\`\`text
com.example.jobs.started
com.example.jobs.progress
com.example.jobs.failed
com.example.jobs.completed
\`\`\`

Notifications are well suited for **informing management tools that a notable change occurred**. Listeners can often re-read MBean attributes to determine current state.

Notifications are not automatically a transaction log. JMX does not implicitly persist events to disk, assign consumer offsets, confirm successful processing, perform durable retries, or provide a historical replay API.

## 3. Four Ordering Concepts to Distinguish

Suppose an MBean emits three notifications in sequence:

\`\`\`text
At the emitter:
N1 (seq=1) -> N2 (seq=2) -> N3 (seq=3)
\`\`\`

Distinguish these stages:

| Concept | Meaning | What Cannot Be Inferred Automatically |
|---|---|---|
| **Creation order** | In what order application threads instantiate notification objects | Does not prove they are sent in that order |
| **Emission order** | In what order the MBean calls \`sendNotification()\` | Does not prove remote listeners see all of them contiguously |
| **Delivery/callback order** | In what order the JMX system and listener receive or handle notifications | Does not guarantee async logic finishes in the same order |
| **Business order** | Which state or transaction actually happened first | Arbitrary timestamps or sequences cannot serve as full business history |

In particular, if multiple threads emit notifications concurrently, clearly define the **serialization point at the source**. Incrementing a counter, constructing a notification, and calling \`sendNotification()\` on different threads do not necessarily form an atomic operation.

### Example of out-of-order execution due to thread contention

\`\`\`text
Thread A: acquires sequence = 10 ----[paused]---- send(N10)
Thread B: acquires sequence = 11 ---- send(N11)
Listener: N11, then N10
\`\`\`

Even when sequence numbers increase monotonically upon allocation, the order of \`sendNotification()\` calls can still differ without synchronization around emission.

If ordering is strictly required, emit through an application-controlled queue or sequential dispatcher. If the consumer processes asynchronously with multiple workers, order preservation is also needed on the consumer side.

## 4. Sequence Number: Useful, Not a Delivery Guarantee

\`Notification\` has a field \`sequenceNumber\` of type \`long\`; in typical Java examples, the emitter actively sets this value. The JMX API does not turn sequence number into a global, durable, self-managed counter for all notifications.

Example emitter:

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class JobMonitor extends NotificationBroadcasterSupport {
    private final AtomicLong nextSequence = new AtomicLong();

    public void jobStarted(String jobId) {
        long sequence = nextSequence.incrementAndGet();

        Notification notification = new Notification(
            "com.example.jobs.started",
            this,
            sequence,
            System.currentTimeMillis(),
            "Job started: " + jobId
        );

        notification.setUserData(jobId);
        sendNotification(notification);
    }
}
\`\`\`

Here \`AtomicLong\` prevents two threads from allocating the same sequence within one instance. It **does not guarantee** that two \`sendNotification()\` calls complete in the same order under concurrency.

### What can sequence numbers help with?

- Logging along with sequence numbers to see the order notifications arrive.
- Detecting **indicators** that one or more sequences were skipped if the emitter contract specifies contiguous numbering per event.
- Recognizing inverted order when the emitter guarantees sequence numbers reflect event order.
- Correlating emitter logs and listener logs during incident diagnostics.

### What do sequence numbers NOT prove by themselves?

- Do not prove exactly-once delivery.
- Do not prove every listener received them.
- Do not prove the notification was processed successfully.
- Do not prove a gap-free number sequence covers all business events.
- Do not prove the sequence continues across JVM or MBean restarts.
- Do not provide an API to retrieve lost notifications.

**Notably:** an emitter may intentionally skip numbers, reset counters, or emit multiple notification types under separate rules. Treat \`seq=10\` followed by \`seq=12\` as an indicator of missed events only when the emitter contract explicitly defines a contiguous, non-resetting sequence within the same epoch.

## 5. Where Notifications Can Be Lost or Missed

### 5.1. Listener not yet registered

If a notification is emitted before \`addNotificationListener()\`, that listener normally will not receive past history. Registering a listener does not cause JMX to automatically replay notifications emitted prior to registration.

\`\`\`text
T1: MBean emits N1
T2: Listener is registered
T3: MBean emits N2
Observed result: listener may see N2 but not N1
\`\`\`

Therefore, do not use notifications alone to initialize a management tool's entire state. **Read initial state** and use notifications as update signals.

### 5.2. Listener removed or MBean unregistered

When a listener is removed, or an MBean is unregistered or replaced, subsequent notifications may no longer reach the old subscription. After re-registering, re-check state.

### 5.3. Remote connection interrupted

Remote JMX is commonly used via \`JMXConnector\` and \`MBeanServerConnection\`. Network partitions, timeouts, reconnects, closed connections, or server JVM restarts can prevent a client from receiving some notifications.

Reconnecting does not automatically prove notifications emitted while offline were re-delivered. Depending on the connector, internal buffers or fetching mechanisms may exist; do not rely on them as durable storage and business replay guarantees.

### 5.4. Buffers or receiving system unable to keep up

Some remote implementations use buffers, queues, or polling to deliver notifications to clients. If the emitter fires too fast, the client is slow, or memory/buffers are bounded, some notifications may be dropped depending on implementation.

You cannot assume every JMX connector shares the same overflow behavior. Consult specific implementation documentation, configuration, and appropriate metrics/logs.

### 5.5. JVM or process terminated

When the JVM exits or crashes, notifications existing only in memory can vanish. \`NotificationBroadcasterSupport\` is not a persistent event store.

### 5.6. Listener throws an exception or fails asynchronous processing

Invoking a callback does not mean processing logic succeeded. A listener can:

- Throw an exception.
- Block on I/O or deadlock.
- Hand events to an internal executor and lose them when the executor shuts down.
- Process duplicates due to the application's own reconnect logic.
- Run slowly, causing new incoming events to back up.

Distinguish **delivered to callback** from **successfully processed and recorded**. Do not lump both outcomes together as "delivered".

## 6. Guarantee Scope of the JMX API

JMX provides interfaces for emitting and listening to notifications, but **does not define an end-to-end contract like a durable message queue for all configurations**.

| Guarantee | Default for JMX Notifications? | Notes |
|---|---|---|
| Can register listener and receive notifications | Yes, when emitter/listener and connection work | Core API functionality |
| Callback order always matches business order | Cannot be assumed | Depends on concurrency, executor, and emitter design |
| Each notification processed exactly once system-wide | No | No built-in business transaction/ack |
| Automatic replay of notifications before listener registration | No | Not an event log |
| Durable persistence across JVM restarts | No | Separate storage required |
| Guaranteed complete delivery to remote client on disconnect/reconnect | Cannot be assumed | Depends on implementation and recovery outside JMX |
| Allows using sequence numbers to detect anomalies | Possible | Requires a clear sequence contract |
| Can re-read current MBean state | Yes, if the MBean exposes matching attributes/operations | Common recovery strategy |

Do not make absolute claims like "JMX always reorders" or "JMX always drops events." In stable environments, many notifications can be delivered in the desired order. The key point is that **the API itself does not provide durable delivery guarantees an application can rely upon under all failure conditions**.

### Local listeners and remote listeners differ

For local listeners in the same JVM, the path is shorter and avoids network errors. Even so, callbacks remain subject to emitter design, executors, concurrency, and listener lifecycles.

For remote listeners, additional factors enter: connections, serialization, client fetch, buffers, reconnects, and implementation differences. Thus, a local test running in order does not prove production behavior over remote JMX.

## 7. \`NotificationBroadcasterSupport\` and Executor Choice

An MBean can use \`NotificationBroadcasterSupport\`:

\`\`\`java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class StatusMonitor extends NotificationBroadcasterSupport {
    public void publish(Notification notification) {
        sendNotification(notification);
    }
}
\`\`\`

Constructors of \`NotificationBroadcasterSupport\` allow supplying an \`Executor\` to dispatch listener callbacks. The default executor may invoke listeners on the emitting thread; when using an asynchronous executor, timing and processing order also depend on the executor's scheduling policy.

Example:

\`\`\`java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.management.NotificationBroadcasterSupport;

ExecutorService callbacks = Executors.newSingleThreadExecutor();

NotificationBroadcasterSupport broadcaster =
    new NotificationBroadcasterSupport(callbacks);
\`\`\`

A single-threaded executor can run callbacks in the order tasks enter that executor's queue. However, preserving end-to-end business order still requires defining emission order, avoiding competing producers, and handling lifecycle/shutdown properly. A single-threaded executor does not add persistence or replay.

If supplying a custom executor, the application is responsible for managing resources and shutting it down appropriately. Do not arbitrarily configure \`newCachedThreadPool()\` or unbounded queues for high-rate notification streams without load control.

## 8. Designing Listeners Tolerant of Notification Loss

An operationally resilient listener should treat notifications as **signals to reconcile against the state source**. Common pattern:

\`\`\`text
Initialization:
  1. Connect to the target MBeanServer/MBean.
  2. Register listener.
  3. Read current state snapshot.
  4. Record source session/epoch if available.

On receiving notification:
  5. Check type/source/sequence per contract.
  6. If gap/out-of-order/reset -> mark resync needed.
  7. Re-read snapshot when needed.
  8. Apply idempotent update to displayed state.

On disconnect:
  9. Mark displayed data stale.
 10. Reconnect and re-register listener.
 11. Read fresh snapshot; do not assume full history was received.
\`\`\`

Registering the listener and reading the snapshot can still race: an event may occur before, during, or after the snapshot. To ensure fully consistent state, the source API needs a reconcilable snapshot/version mechanism. For instance, a \`stateVersion\` incremented on every state change and returned with the snapshot lets consumers ignore stale data or re-read on conflict.

Without versioning, the safe approach is treating notifications as triggers for a **full state refresh**, accepting eventual consistency for observation purposes.

### Minimal listener example

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationListener;

public final class MonitorListener implements NotificationListener {
    private final AtomicLong lastSeen = new AtomicLong(-1);

    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {

        long current = notification.getSequenceNumber();
        long previous = lastSeen.getAndSet(current);

        if (previous >= 0 && current != previous + 1) {
            System.out.printf(
                "Resync needed: prev=%d, current=%d%n",
                previous, current
            );
        }

        System.out.println(notification.getType());
        // For an operations UI: request re-reading current state here
        // or enqueue a refresh into a managed executor.
    }
}
\`\`\`

This example only illustrates detecting **sequence anomalies**. It assumes callbacks execute sequentially from a single source with contiguous, non-resetting sequences and no filtered-out notification types. If callbacks run concurrently or multiple sources exist, \`getAndSet()\` does not preserve observed order and may trigger false alarms. In real systems, process sequentially per source and track \`source + epoch + sequence\`; if only some event types pass the filter, adjust gap detection policy accordingly.

When a gap occurs, **you cannot reconstruct the lost notification's contents from the sequence number alone**. Request a snapshot or use a separate event store if every individual event must be known.

## 9. Designing a Clear Emitter Contract

When writing a notification-emitting MBean, document:

1. **Meaning of each type**: e.g., whether \`job.failed\` indicates a transient error or a permanent state transition.
2. **Sequence scope**: per MBean or application-wide; contiguous or sparse; whether it resets on restart.
3. **Serialization point**: when events are numbered; whether multiple threads can emit concurrently.
4. **Epoch or instance ID**: distinguishes MBean/JVM lifecycles, preventing sequence resets from being mistaken for replays.
5. **Snapshot API**: attributes or operations letting consumers read current state.
6. **Errors and connectivity**: what consumers should do upon disconnect or incomplete delivery.
7. **Delivery semantics**: whether notifications are merely observational signals or carry audit/zero-loss requirements.

A clear contract saves clients from guessing based on "notifications worked in the test environment."

### Example snapshot with version

\`\`\`java
public record JobSnapshot(
    String state,
    long version,
    String instanceId
) {}
\`\`\`

An MBean can expose equivalent operations/attributes for state, version, and instance ID. When \`job.completed\` arrives, the client reads \`JobSnapshot\`; if \`version\` increased, the UI displays the new state. If a late notification arrives carrying an older version, the client does not overwrite the newer snapshot.

For versioning to be genuinely useful, **the emitter must update state and version consistently**. Adding a \`long\` field alone does not resolve races if state and version are not published under the same synchronization logic.

## 10. Spring Framework: Emitting Notifications from an MBean

Spring JMX can expose a Spring bean as an MBean and supports \`NotificationPublisherAware\`:

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Monitor,name=ImportJob"
)
public class ImportJobMonitor implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    public void onJobFailed(String reason) {
        Notification notification = new Notification(
            "com.example.jobs.failed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Import failed"
        );
        notification.setUserData(reason);
        publisher.sendNotification(notification);
    }
}
\`\`\`

This illustrates a notification-emitting class. To run in a real application, configure JMX export properly, configure notification metadata if needed, and ensure \`NotificationPublisher\` has been supplied by Spring before calling \`onJobFailed\`. If business code calls from multiple threads and ordering matters, a serialization point is also needed beyond just \`AtomicLong\`.

Spring provides the bridge for JMX publishing and listener registration; Spring **does not turn notifications into durably persisted, acked, or replayable events**. Those properties must be provided by application design or messaging infrastructure.

### Do not confuse with Spring ApplicationEvent

\`ApplicationEventPublisher\` belongs to the event model inside the Spring application context, whereas JMX \`NotificationPublisher\` targets the JMX management system. They have separate lifecycles and dispatch mechanisms. Neither Spring events nor JMX notifications automatically guarantee durable delivery; if needed, design explicit persistence and delivery mechanisms.

## 11. Remote JMX: Observing Disruptions and Recovery

Example remote client using \`JMXConnector\`:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.NotificationListener;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
            connector.getMBeanServerConnection();

    ObjectName name = new ObjectName(
        "com.example.jobs:type=Monitor,name=ImportJob"
    );

    NotificationListener listener = (n, handback) -> {
        System.out.println(
            n.getSequenceNumber() + " " + n.getType()
        );
    };

    connection.addNotificationListener(
        name, listener, null, null
    );

    // In practice: keep listening session alive, read snapshots, and handle reconnects.
    // Avoid exiting immediately after registering the listener.
}
\`\`\`

This snippet illustrates how to register a listener, not a continuously running client program. In operation you need:
- A properly configured and secured connector server.
- Monitoring of connection errors and connection lifecycle.
- Re-registering listeners on the new connection upon reconnect.
- Synchronizing snapshots and recognizing stale data.
- Avoiding duplicate listeners created on reconnect without cleanup.
- Appropriate timeouts and retry/backoff limits.

Depending on the JMX connector and implementation, connection management notifications such as \`JMXConnectionNotification\` may appear. Watching them helps clients detect disconnects, but connection notifications themselves do not prove all MBean notifications were received.

## 12. When Is a Message Broker or Event Store Needed?

JMX notifications are useful when:
- Management tools need to know "something changed" and re-read state.
- Transient, moderate-volume operational alerts are needed.
- Listeners are online and occasional missed events can be compensated by snapshots.
- The main goal is internal Java/JMX observability.

If the requirements are:
- **Zero missed individual events** across JVM restarts or client downtime.
- Full **auditing**, querying history across days/months.
- **Retries** when consumers fail processing.
- Consumer groups, offsets, backpressure, reprocessing.
- Business transactions requiring data durability and processing acknowledgement.

...then another solution is needed, such as a durably configured event log/message broker (Kafka, RabbitMQ), database outbox, or audit table with dedicated transaction and consumer processing.

Do not assume "using a broker automatically gives exactly-once." Each broker and configuration has specific guarantee bounds; end-to-end exactly-once usually also requires idempotency, transactions, or consumer-side deduplication.

### Hybrid architecture

\`\`\`text
             Business state change
                       |
               Database transaction
                       |
              Outbox / event log
                       |
           Reliable event processing
                       |
            +----------+----------+
            |                     |
      Business consumers     Metrics / audit
            |
   (optional) state update
            |
        JMX MBean
            |
   JMX notification: "state changed"
            |
        Admin console
            |
      Reads current snapshot
\`\`\`

In this design, the business event stream has its own durable storage; JMX notifications act as observability signals that may be missed and recovered by reading state.

## 13. Diagnosing Missing or Out-of-Order Notifications

When a client reports "a notification was lost," separate the hypotheses:

| Symptom | What to Check |
|---|---|
| Saw seq 100 then 102 | Did source emit 101? Is counter contiguous? Did a filter drop the event? |
| Saw seq 102 before 101 | Multiple producers? Async executor dispatch? Concurrent consumer processing? |
| Nothing received after reconnect | Was listener re-registered on the new connection? Are ObjectName and MBean correct? |
| After restart seq resets to 1 | Did source reset its counter? Is there an instance ID/epoch? |
| Callback runs but UI does not update | Downstream logic error? Dropped queue item or blocked thread? |
| Missing only on remote client | Network, connector, buffer, polling, timeouts, connection churn? |
| Missed notifications before client started | Wrong expectation of replay? Is there a snapshot for initialization? |

Logging practices should record:
- Source timestamp and client receive time (without assuming both machines' clocks are strictly synchronized).
- ObjectName/source, type, sequence, instance ID/epoch.
- Listener lifecycle: register/unregister/reconnect.
- Emitted count, callback count, processing errors, snapshot read timestamps.
- Queue/buffer counts and latency if exposed by the implementation.

Do not log secret data inside \`userData\`. For large systems, use metrics to measure emitted, received, failed notifications and resyncs; do not rely solely on notifications themselves to detect when notifications fail to arrive.

## 14. Full Scenario Example

Suppose a data-import management MBean has states:

\`\`\`text
IDLE -> RUNNING -> COMPLETED
                 -> FAILED
\`\`\`

Source emits:

\`\`\`text
N41: RUNNING
N42: COMPLETED
\`\`\`

A client connects after N41 and sees only N42. If the UI initializes by waiting for notifications, it might never see \`RUNNING\`. But if the UI reads \`CurrentStatus\` after registering the listener, it sees the appropriate state at snapshot time.

Another scenario:

\`\`\`text
Client sees: N41, [network outage], N44
\`\`\`

The gap \`41 -> 44\` can warn that N42/N43 are missing **if** sequences are contiguous and share the same epoch. The client must not guess the contents of the two missed notifications. It should re-read \`CurrentStatus\`, \`StateVersion\`, or query an event store if complete history is required.

If the system must process every single state transition, snapshots provide only the latest state and may not reflect intermediate states; in that case, an event store retaining history is required.

## 15. Self-Check Questions

**Question 1.** A listener receives sequence 10 then 12. Can we conclude notification 11 was lost?  
**Answer:** It can only be treated as an indicator if the source contract mandates contiguous numbers, the same epoch, and no filtering. It cannot be concluded if the counter allows valid gaps.

**Question 2.** Does \`AtomicLong.incrementAndGet()\` guarantee callbacks run in ascending number order?  
**Answer:** No. AtomicLong guarantees atomic number allocation, while threads can call \`sendNotification()\` out of order and executors/consumers can alter processing order.

**Question 3.** Will a newly registered listener receive old notifications?  
**Answer:** You cannot expect JMX to automatically replay notifications emitted prior to registration. Use snapshots or an event store depending on requirements.

**Question 4.** On remote JMX reconnect, is re-registering the listener enough to recover history?  
**Answer:** No. You must synchronize state, detect epochs, and if every event is needed, query a separate durable store.

**Question 5.** Why is a notification reaching a callback not yet considered successfully processed?  
**Answer:** The listener may fail in its logic, an async queue may drop the event, or downstream updates may fail. JMX does not provide end-to-end business acknowledgements by default.

**Question 6.** Should a requirement that "every transaction must be audited after restart" use JMX notifications alone?  
**Answer:** No. Persist transactions/events in a database, outbox, or broker/event store with an appropriate delivery contract.

## 16. Remember

1. JMX notifications are a **management signaling mechanism**, not a durably persisted event log by default.
2. \`sequenceNumber\` is assigned by the emitter; it aids diagnostics but creates neither ordering nor delivery guarantees.
3. Multiple threads, asynchronous executors, remote connectors, and downstream consumers can all affect observed ordering.
4. Late listener registration, disconnects, bounded buffers, JVM restarts, and processing errors are all sources of missing data.
5. Design consumers around **snapshot + notification + resynchronization**, with versions/epochs when needed.
6. If every individual event must be kept, design persistence, replay, retries, and idempotency outside basic JMX scope.
7. Evaluate guarantees across **the entire path from producer to business effect**, rather than inferring from a callback being invoked.

### References

- Java SE 21 API — \`javax.management.Notification\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Java SE 21 API — \`NotificationBroadcasterSupport\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 API — \`NotificationListener\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE 21 API — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 API — \`JMXConnector\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html
- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
