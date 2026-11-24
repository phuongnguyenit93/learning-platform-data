# Testing Notifications and Preventing Duplicate Processing in Spring JMX

## 1. Objectives and Problem Statement

In Spring Framework JMX, an MBean can emit \`javax.management.Notification\` to announce job status, warnings, configuration changes, or management events. Spring supports \`NotificationPublisherAware\` and \`NotificationPublisher\` so managed beans can send notifications when exported.

However, **a sent notification does not mean every listener receives and processes it exactly once**. Listeners can be registered twice, clients can reconnect, producers can re-emit the same event, or downstream consumers can retry. In addition, listeners can miss notifications while unregistered, during disconnections, or on JVM restarts. Therefore, you must test across multiple layers and build **idempotent** handling for business effects that must not repeat.

After this lesson, you will be able to:

- Write a managed bean that emits notifications using Spring.
- Test the publisher using a fake and test listeners through \`MBeanServer\`.
- Verify type, sequence, source, payload, and notification filters.
- Identify causes that lead to an event being processed twice.
- Apply event IDs, database unique constraints, and transactions to prevent duplicate side effects.
- Distinguish \`at-most-once\`, \`at-least-once\`, and \`exactly-once\` within their proper scope.
- Test concurrent delivery, reconnects, restarts, and snapshot recovery.

## 2. Notification Flow and Potential Failure Points

\`\`\`text
Spring bean
    |
    | NotificationPublisher.sendNotification()
    v
MBeanServer / notification broadcaster
    |
    +------ local NotificationListener
    |
    +------ remote JMX connector ------ remote listener
                                           |
                                           v
                                    Handler / queue
                                           |
                                      Dedup gate
                                           |
                                     Business effect
\`\`\`

A system has distinct milestones:

| Milestone | What Can Be Asserted | What Is Not Guaranteed |
|---|---|---|
| Producer creates \`Notification\` | A notification object exists | Not necessarily sent |
| Producer calls \`sendNotification()\` | Requested emission through publisher | Not guaranteed every client receives it |
| Listener callback invoked | A callback observed the notification | Business processing not guaranteed to succeed |
| Handler records event ID | Processing attempt recorded | Side effect not guaranteed to commit in same transaction |
| Business effect commits | Business effect persisted within transaction scope | Does not prove no similar effect occurred in another system |

Do not treat JMX notifications as a durable event log. JMX does not by default provide persistence, full historical replay, consumer offsets, or end-to-end business acknowledgments.

## 3. Data Fields of a Notification

\`\`\`java
import javax.management.Notification;

Notification event = new Notification(
    "com.example.jobs.completed",
    this,
    101L,
    System.currentTimeMillis(),
    "Job completed"
);
event.setUserData("job-123");
\`\`\`

Commonly used fields:

- \`type\`: e.g., \`com.example.jobs.completed\`.
- \`source\`: emitting object or source information.
- \`sequenceNumber\`: sequence number assigned by the producer.
- \`timeStamp\`: timestamp assigned by the producer.
- \`message\`: description.
- \`userData\`: supplemental payload.

**Do not use \`sequenceNumber\` alone as a global event identifier** without an explicit contract. Two different MBeans can both use sequence 101; counters can reset after restarts; and different notification types may share or use separate sequences.

A stable deduplication key should be based on a business-issued \`eventId\`, or \`source + instanceEpoch + sequence\` if the producer guarantees uniqueness of that tuple.

## 4. Managed Bean Emitting Notifications via Spring

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "com.example.jobs:type=Monitor,name=Import",
    description = "Import job monitoring"
)
@ManagedNotification(
    name = "com.example.jobs.completed",
    description = "Import completed event",
    notificationTypes = {"com.example.jobs.completed"}
)
public class ImportMonitor implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile NotificationPublisher publisher;
    private volatile String lastCompletedJob = "";

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute(description = "Last completed job ID")
    public String getLastCompletedJob() {
        return lastCompletedJob;
    }

    @ManagedOperation(description = "Publish completion event")
    public void complete(String jobId) {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("jobId is blank");
        }

        NotificationPublisher current = publisher;
        if (current == null) {
            throw new IllegalStateException("Publisher unavailable");
        }

        lastCompletedJob = jobId;
        Notification notification = new Notification(
            "com.example.jobs.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Completed " + jobId
        );
        notification.setUserData(jobId);
        current.sendNotification(notification);
    }
}
\`\`\`

Explanation:

1. \`@ManagedResource\` defines the ObjectName.
2. \`@ManagedNotification\` describes notification metadata for JMX clients.
3. \`NotificationPublisherAware\` receives the publisher from Spring's JMX export infrastructure.
4. \`complete()\` invokes \`sendNotification()\` at runtime.
5. \`AtomicLong\` issues atomic sequences within an instance, though it does not automatically guarantee callback order across multiple threads.
6. \`getLastCompletedJob()\` is a minimal snapshot that can be re-read after a listener misses a notification.

The \`@ManagedNotification\` annotation **does not emit notifications on its own**. The source itself must invoke the publisher.

### Initializing the Exporter

One Spring Framework configuration approach:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
    @Bean
    public ImportMonitor importMonitor() {
        return new ImportMonitor();
    }
}
\`\`\`

In Spring Boot, check JMX auto-configuration settings, such as \`spring.jmx.enabled\` according to your Boot version. Do not create a second exporter colliding on the same ObjectName when existing infrastructure already performs the export.

## 5. Three Main Testing Levels

| Level | What It Tests | What Cannot Be Inferred |
|---|---|---|
| **Unit test publisher** | Method creates/sends notifications accurately | That a listener receives via MBeanServer |
| **Local JMX integration test** | MBean is registered, listener receives, filter works | That remote transport/reconnect works reliably |
| **Business idempotency test** | Duplicate events do not repeat side effects per contract | That JMX never loses notifications |
| **Remote JMX integration test** | Listener receives over connector, connection recovers | Durable replay after offline periods |
| **Restart/concurrency test** | Deduplication remains effective under target failure modes | Automatic system-wide exactly-once |

You should verify **business effects**, not just count callbacks.

## 6. Unit Testing with CapturingPublisher

Use a fake publisher in JUnit:

\`\`\`java
import java.util.ArrayList;
import java.util.List;
import javax.management.Notification;
import org.springframework.jmx.export.notification.NotificationPublisher;

final class CapturingPublisher implements NotificationPublisher {
    final List<Notification> events = new ArrayList<>();

    @Override
    public void sendNotification(Notification notification) {
        events.add(notification);
    }
}
\`\`\`

Test:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ImportMonitorTest {
    @Test
    void publishesCorrectCompletion() {
        ImportMonitor monitor = new ImportMonitor();
        CapturingPublisher publisher = new CapturingPublisher();
        monitor.setNotificationPublisher(publisher);

        monitor.complete("job-123");

        assertEquals(1, publisher.events.size());
        Notification event = publisher.events.get(0);
        assertEquals("com.example.jobs.completed", event.getType());
        assertEquals(1L, event.getSequenceNumber());
        assertEquals("job-123", event.getUserData());
        assertEquals("job-123", monitor.getLastCompletedJob());
    }

    @Test
    void rejectsBlankJobId() {
        ImportMonitor monitor = new ImportMonitor();
        monitor.setNotificationPublisher(new CapturingPublisher());

        assertThrows(
            IllegalArgumentException.class,
            () -> monitor.complete(" ")
        );
    }
}
\`\`\`

The fake above is not thread-safe; use it only for sequential unit tests. For concurrent emission tests, use \`ConcurrentLinkedQueue\` or proper synchronization.

This tests **producer logic**: it does not prove Spring exported the MBean or that a JMX listener receives notifications.

## 7. Testing Listeners via MBeanServer

In an integration test, use the \`MBeanServer\` selected by the Spring exporter.

\`\`\`java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

MBeanServer server = /* MBeanServer of the Spring test context */ null;

ObjectName name = new ObjectName(
    "com.example.jobs:type=Monitor,name=Import"
);

if (!server.isRegistered(name)) {
    throw new AssertionError("Missing MBean: " + name);
}

CountDownLatch latch = new CountDownLatch(1);
AtomicReference<Notification> received = new AtomicReference<>();

NotificationListener listener = (event, handback) -> {
    received.set(event);
    latch.countDown();
};

server.addNotificationListener(name, listener, null, null);

try {
    server.invoke(
        name,
        "complete",
        new Object[]{"job-123"},
        new String[]{String.class.getName()}
    );

    if (!latch.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Notification was not received");
    }

    Notification actual = received.get();
    if (!"com.example.jobs.completed".equals(actual.getType())) {
        throw new AssertionError("Unexpected type");
    }
    if (!"job-123".equals(actual.getUserData())) {
        throw new AssertionError("Unexpected payload");
    }
} finally {
    server.removeNotificationListener(name, listener);
}
\`\`\`

\`server\` is a placeholder: a complete test must obtain the real MBeanServer from the Spring context or \`ManagementFactory.getPlatformMBeanServer()\` **only when the exporter uses the platform server**.

To reduce flaky tests:

- Register the listener **before** triggering the event.
- Use \`CountDownLatch\` or \`BlockingQueue\`, not a fixed \`Thread.sleep()\`.
- Await with an appropriate timeout.
- Remove the listener in \`finally\`.
- Initialize/close the context with clear ownership.
- Avoid ObjectName collisions across tests running concurrently in the same JVM.
- If callbacks run concurrently, use thread-safe storage instead of \`ArrayList\`.

## 8. Inspecting Notification Metadata

\`\`\`java
var info = server.getMBeanInfo(name);

for (var notificationInfo : info.getNotifications()) {
    System.out.println(notificationInfo.getName());
    System.out.println(
        java.util.Arrays.toString(notificationInfo.getNotifTypes())
    );
}
\`\`\`

Distinguish clearly:

- \`MBeanInfo.getNotifications()\` describes the **published notification types**.
- \`NotificationPublisher.sendNotification()\` is the action of **emitting**.
- \`NotificationListener.handleNotification()\` is where the **callback is received**.
- Business handlers decide whether a notification leads to a **side effect**.

A notification declared in metadata might never be emitted. A listener receiving a callback might fail before business processing.

## 9. Testing Filters: Receiving Only the Right Notification Types

Example using an exact filter:

\`\`\`java
import javax.management.NotificationFilter;

NotificationFilter onlyCompleted = notification ->
    "com.example.jobs.completed".equals(notification.getType());

server.addNotificationListener(
    name,
    listener,
    onlyCompleted,
    null
);
\`\`\`

In addition, there is \`NotificationFilterSupport\`:

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.jobs.");
\`\`\`

\`NotificationFilterSupport\` supports **type prefix** matching, so \`enableType("com.example.jobs.")\` can accept multiple types like \`started\`, \`completed\`, and \`failed\`. Do not assume this is an exact equality check.

Test suites should emit at least three types and verify:

| Type | Exact completed filter |
|---|---|
| \`com.example.jobs.started\` | Excluded |
| \`com.example.jobs.completed\` | Received |
| \`com.example.jobs.failed\` | Excluded |

If a listener receives only completed events, a gap in the source's sequence **does not prove notifications were lost**; other types may have been intentionally excluded by the filter.

## 10. Ordering and Concurrent Publication

Example:

\`\`\`text
Thread A: sequence=100 --pause--> send(N100)
Thread B: sequence=101 ---------> send(N101)
Listener: N101 before N100
\`\`\`

\`AtomicLong.incrementAndGet()\` ensures unique sequence numbers within an instance, but does not serialize the entire create-and-emit operation. If ordering is a mandatory contract, the producer must have an appropriate serialization point, such as a single-thread executor or synchronized emission section.

Similarly, a listener may offload notifications into a thread pool, causing **side-effect completion times** to differ from callback order.

Concurrency tests should verify:
- Whether event IDs are unique.
- Whether the set of events received in the test scope is accurate.
- Whether out-of-order sequences occur if the contract prohibits them.
- Whether duplicate effects occur when multiple handler workers process the same event.
- Whether data corruption occurs due to shared mutable state.

Do not take a passing local test as proof of ordering or delivery guarantees over a remote network during disconnections.

## 11. Why Does an Event Get Processed Twice?

### 11.1. Duplicate Listener Registration

\`\`\`java
server.addNotificationListener(name, listener, null, null);
server.addNotificationListener(name, listener, null, null);
\`\`\`

Multiple registration calls can create multiple registration entries; do not assume MBeanServer automatically deduplicates listeners with the same object reference. During cleanup, use the proper overload and manage \`listener\`, \`filter\`, and \`handback\`.

### 11.2. Reconnect Creates Multiple Active Consumers

A client loses its connection and opens a new one without invalidating the old session. If the same logical consumer has multiple active listeners, a single event can arrive multiple times at the application layer.

Solution:
- Track connection generation.
- Register the listener once per valid connection.
- Unregister or close the old connection.
- Invalidate callbacks from expired sessions.
- Refresh snapshot after reconnecting.

### 11.3. Producer Emits Twice

Business workflows may trigger sending a notification twice due to retries or an event handler firing repeatedly. A stable notification ID helps consumers recognize the same logical event.

### 11.4. Downstream Retries

The listener forwards the event to a database, email, or queue. If the downstream worker retries, the side effect can repeat even though the JMX callback ran only once.

### 11.5. Two Listeners Performing the Same Task

Two consumer instances both subscribe and write to the same business table. Without partitioning ownership or shared deduplication, both may apply the same logical event.

**Lesson:** Deduplication must be designed at the boundary of the **business side effect**, not solely at the JMX callback layer.

## 12. What Is Idempotency?

An idempotent operation can be re-applied with the same request without changing the intended outcome after the first success.

Examples:
- \`setJobStatus("job-123","COMPLETED")\` under state-assignment semantics can be idempotent.
- \`upsert\` of a record with a fixed key can be idempotent.
- \`incrementCompletedCount()\` is not idempotent.
- \`sendEmail()\` is not idempotent by default.
- \`chargeAccount(amount)\` is not idempotent without an idempotency key.

\`\`\`text
E-123 delivered
    |
    +--> handler A --> increment count
    |
    +--> handler B --> increment count

Result: count increments twice
\`\`\`

When the handler has a deduplication key:

\`\`\`text
E-123 delivered
    |
    +--> gate accepts E-123 --> apply effect
    |
    +--> gate sees E-123 --> skip duplicate
\`\`\`

You must define what **a single event** is, especially when the same \`jobId\` can have multiple starts/completions across different runs. Do not use \`jobId\` as the event ID if the same job can validly produce multiple events.

## 13. Payload with eventId

Define the payload:

\`\`\`java
import java.io.Serializable;

public record JobEvent(
    String eventId,
    String jobId,
    String status,
    long occurredAtEpochMillis
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
\`\`\`

Create the notification:

\`\`\`java
JobEvent payload = new JobEvent(
    "evt-123",
    "job-123",
    "COMPLETED",
    System.currentTimeMillis()
);

Notification event = new Notification(
    "com.example.jobs.completed",
    this,
    sequence.incrementAndGet()
);
event.setUserData(payload);
publisher.sendNotification(event);
\`\`\`

A good \`eventId\`:
- Is issued once per logical event.
- Does not change when publication is retried.
- Does not collide with other events within the defined scope.
- Can be stored and traced across systems.
- Does not contain unnecessary secrets or personal data.

If a remote client lacks the \`JobEvent\` Java class, Java serialization may fail. When clients must remain classpath-independent, use a String event ID or an OpenType such as \`CompositeData\`.

## 14. In-Memory Deduplication

Example listener with a thread-safe gate:

\`\`\`java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.management.Notification;
import javax.management.NotificationListener;

public class InMemoryDedupListener implements NotificationListener {

    private final Set<String> seenIds =
        ConcurrentHashMap.newKeySet();

    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {

        if (!(notification.getUserData() instanceof JobEvent event)) {
            return;
        }

        if (!seenIds.add(event.eventId())) {
            return;
        }

        applyEffect(event);
    }

    private void applyEffect(JobEvent event) {
        System.out.println("Event: " + event.eventId());
    }
}
\`\`\`

\`seenIds.add()\` is atomic per key within a single instance. However, **this is not durable exactly-once**:

1. The set grows unboundedly without TTL/eviction.
2. Restarts wipe out seen state.
3. Multiple JVMs do not share the seen set.
4. If the handler fails after \`seenIds.add()\`, retries are skipped even though the effect failed.
5. A duplicate event ID with a conflicting payload may be silently ignored without raising an error.

Using this approach for UI refreshes, non-critical work, or short-lived sessions can be reasonable. For business data, a durable solution is required.

## 15. Preventing Duplicate Processing with a Database Unique Constraint

Create table:

\`\`\`sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(150) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
\`\`\`

Transaction flow:

\`\`\`text
BEGIN
    INSERT processed_events(
        consumer_name, event_id, processed_at
    )
    VALUES ('jobs-consumer', 'evt-123', CURRENT_TIMESTAMP);

    UPDATE job_statistics
    SET completed_count = completed_count + 1
    WHERE statistic_id = 'global';
COMMIT
\`\`\`

If the \`INSERT\` hits a duplicate primary key, consumer logic skips the side effect or returns an "already processed" status per contract.

Crucially, the dedup insert and the business update must execute in the **same transaction** when both live in the same database. If the dedup key commits first and then the business update fails, later retries would be wrongly discarded.

### Spring Service Example

\`\`\`java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JobEventConsumer {
    private final ProcessedEventRepository processed;
    private final JobStatisticsRepository statistics;

    public JobEventConsumer(
            ProcessedEventRepository processed,
            JobStatisticsRepository statistics) {
        this.processed = processed;
        this.statistics = statistics;
    }

    @Transactional
    public void process(JobEvent event) {
        boolean inserted = processed.tryInsertUnique(
            "jobs-consumer", event.eventId()
        );

        if (!inserted) {
            return;
        }

        statistics.incrementCompletedCount();
    }
}
\`\`\`

\`tryInsertUnique\` is repository pseudocode: real implementations must use a unique constraint/atomic insert and handle duplicate conflicts consistently with the transaction manager and database. Do not use a plain "SELECT exists then INSERT," because two threads can both observe non-existence.

### External Side Effects Beyond the Database

For emails, HTTP APIs, payments, or file writes, a database transaction does not automatically guarantee external side effects execute once. You may need downstream idempotency keys, an outbox, processing states, and explicit retry workflows.

## 16. Why Shouldn't You Deduplicate Solely by Sequence?

Suppose:

\`\`\`text
MBean instance A: seq=100
JVM restart
MBean instance B: seq=100
\`\`\`

Two notifications have the same sequence yet are different events.

A better key:

\`\`\`text
sourceObjectName + sourceEpoch + sequenceNumber
\`\`\`

But this is only suitable if:
- The producer guarantees each sequence corresponds to a unique event within an epoch.
- The epoch changes after restarts.
- The client identifies the source accurately.
- Differences across event types are not ignored if the producer defines separate sequences.

In business logic, a stable event ID issued by source logic is usually more reliable.

## 17. Testing Duplicate Prevention by Business Behavior

Minimum test suite:

1. **New event:** E-1 processed once → side effect increments by one.
2. **Duplicate event:** E-1 processed twice → side effect still increments by one.
3. **Different event:** E-2 processed → increments by one more.
4. **Concurrent duplicates:** 20 threads process E-3 → side effect increments only once.
5. **Restart:** after restart, E-3 still does not duplicate the effect if the contract requires durable dedup.
6. **Failure before commit:** transaction rolls back → retry can re-process and succeed.
7. **Conflicting payload:** same event ID with different content → report conflict per policy instead of silently writing wrong data.

JUnit example:

\`\`\`java
@Test
void duplicateEventDoesNotDoubleCount() {
    JobEvent event = new JobEvent(
        "evt-123", "job-123", "COMPLETED", 1000L
    );

    consumer.process(event);
    consumer.process(event);

    assertEquals(
        1,
        statistics.countCompletedEffects("job-123")
    );
}
\`\`\`

This assertion is at the business-effect layer, not merely checking how many times \`handleNotification()\` was called.

## 18. Testing Concurrent Duplicates

A skeleton example:

\`\`\`java
ExecutorService executor =
    Executors.newFixedThreadPool(8);

CountDownLatch start = new CountDownLatch(1);
List<Future<?>> futures = new ArrayList<>();

for (int i = 0; i < 20; i++) {
    futures.add(executor.submit(() -> {
        start.await();
        consumer.process(event);
        return null;
    }));
}

start.countDown();

try {
    for (Future<?> future : futures) {
        future.get();
    }
} finally {
    executor.shutdown();
}

assertEquals(1, repository.countEffects(event.eventId()));
\`\`\`

In real code, add imports, a test database, and proper transaction configuration. Concurrency tests need a database with an actual unique constraint, because a mock repository cannot prove storage-level race conditions.

If multiple threads run \`SELECT exists\`, both can see false and proceed to process. A unique key and atomic insert are the final line of defense.

## 19. Testing Listener Registration Lifecycle

A listener should be registered once on the active connection/session and removed when no longer needed.

\`\`\`java
server.addNotificationListener(
    name, listener, filter, handback
);
\`\`\`

Cleanup:

\`\`\`java
server.removeNotificationListener(
    name, listener, filter, handback
);
\`\`\`

Distinguish registrations that share the same listener but have different filters/handbacks. When using Spring's JMX listener registry or custom registration logic, agree on who owns the listener lifecycle.

Tests should verify:
- No callbacks arrive after the listener is properly removed.
- No duplicate registration is created when a component reinitializes.
- Two connection generations do not produce side effects simultaneously.
- Context shutdown cleans up resources properly.
- Reconnect re-registers the listener without retaining stale references.

## 20. Remote Reconnect and Snapshots

A scenario:

\`\`\`text
Client connected
    |
    v
Receives E-10
    |
    v
Network outage
    |
    +--- Server emits E-11, E-12
    |
    v
Client reconnects
    |
    v
Re-register listener
    |
    v
Read current MBean state
\`\`\`

Never assume E-11/E-12 will be completely replayed after reconnection. Remote connectors may have their own buffers and fetch policies, but JMX notifications are not durable business history.

A dashboard should treat notifications as **change signals**:

\`\`\`text
Notification received
         |
         v
Refresh current attributes
         |
         v
Replace UI snapshot
\`\`\`

If a notification is duplicated, refreshing one extra time does not corrupt state. If a notification is missed, the client can refresh periodically or on reconnect to synchronize.

If you must know every missed state transition individually, snapshots are insufficient; you need a dedicated event log.

## 21. Understanding Guarantee Levels Properly

| Expectation | Guaranteed by Basic JMX Notifications? | Solution When Mandatory |
|---|---|---|
| Registered listener can receive notifications | Yes, via active broadcaster and connector | Test registration/filter |
| Old notifications replayed when listener registers late | No | Durable event log |
| Every event survives JVM restarts | No | Persistent outbox/broker |
| Callback invoked exactly once despite errors | Not by default | Design duplicate-tolerant consumers |
| Business effect applied once | No | Idempotency key + transaction |
| Detect sequence gaps | Possible if source contract is clear | Source+epoch+sequence |
| Recover state after reconnect | Yes if MBean exposes snapshots | Read attributes/version |
| Audit complete history | No | Database/event store |

Do not equate:
- **at-most-once attempt:** may drop events, but never repeats attempts per policy.
- **at-least-once attempt:** retries until criteria are met, may repeat.
- **exactly-once effect:** side effects constrained so impact is not doubled.

Even a system with at-least-once delivery from a broker usually still needs idempotent consumers to approximate exactly-once business effects.

## 22. When to Use a Queue or Event Store?

JMX notifications are well suited for:
- Dashboard refresh signals.
- Immediate operational alerts.
- Observing runtime state.
- Management tools connected at emission time.

Do not use JMX notifications as the sole channel for:
- Payments or balance changes.
- Audit logs that must be complete.
- Workflows that cannot lose events on JVM crashes.
- Job queues requiring durable retries.
- Multi-service integrations needing consumer offsets/replay.

Combined architecture:

\`\`\`text
Business transaction
       |
       v
Database + outbox
       |
       v
Durable event processing
       |
       +----> Idempotent business consumers
       |
       +----> State/metrics
                   |
                   v
               JMX MBean
                   |
                   v
            JMX notification
                   |
                   v
              Dashboard
\`\`\`

In this design, notifications act as an observation layer; critical business events have their own durable storage source.

## 23. Common Mistakes

**1. "JMX guarantees a listener never receives duplicates."**  
There is no such business guarantee; applications can create multiple registrations or retry downstream.

**2. "Sequence number is a unique event ID."**  
False when sources reset, multiple MBeans exist, or sequence policies are unclear.

**3. "ConcurrentHashMap dedup provides exactly-once."**  
False: it does not survive restarts and can mark an event processed before the effect succeeds.

**4. "Receiving the callback means the business transaction committed."**  
False: callback and business transaction are two distinct stages.

**5. "@ManagedNotification emits events automatically."**  
No. It describes metadata, while the publisher/broadcaster must send the notification.

**6. "The filter caused sequence gaps so the connector is broken."**  
Not necessarily. A filter may intentionally drop other notification types.

**7. "Reconnecting automatically re-receives all missed notifications."**  
Do not assume this. You must re-subscribe and refresh snapshots or use an event store.

**8. "Checking callback count alone is enough."**  
No. Business side effects must be verified separately.

**9. "Using internal DTOs in userData is always remote-compatible."**  
No. Clients may lack the class or reject deserialization.

**10. "Running a very long transaction inside a listener callback is harmless."**  
No. It can block notification dispatch; use an appropriate worker/queue mechanism and manage backpressure.

## 24. Hands-On Exercises

### Exercise A — Unit Testing the Producer

1. Create \`ImportMonitor\`.
2. Inject a fake publisher.
3. Call \`complete("job-1")\`.
4. Verify type, sequence, userData, and state.
5. Call again with another job and observe the sequence.

### Exercise B — MBeanServer Integration Test

1. Enable Spring annotation JMX export.
2. Register a notification listener.
3. Call \`complete\` via \`MBeanServer.invoke()\`.
4. Wait for the notification with a latch.
5. Verify payload and metadata.
6. Remove the listener in finally.

### Exercise C — Duplicate Events

1. Create a \`JobEvent\` with a fixed event ID.
2. Call the handler twice.
3. Assert the side effect appears only once.
4. Call with a different event ID and assert the side effect is applied again.

### Exercise D — Concurrency

1. Use 20 threads to process the same event ID.
2. Use a database unique constraint and transaction.
3. Assert the side effect is applied only once.
4. Switch to a non-atomic check-then-insert to observe the race.

### Exercise E — Restart

1. Process and commit event E-1.
2. Create a new consumer instance or restart the application.
3. Send E-1 again.
4. Verify durable dedup still prevents duplicate effects.
5. Compare with an in-memory seen set.

### Exercise F — Reconnect

1. Connect remote JMX in a test environment.
2. Register a listener.
3. Drop the connection while the server emits notifications.
4. Reconnect and re-register.
5. Refresh the MBean snapshot.
6. Verify no duplicate side effects occur when events are re-received through the application path.

## 25. Self-Check Questions

**Question 1.** Does \`@ManagedNotification\` emit notifications on its own?  
**Answer:** No. \`NotificationPublisher.sendNotification()\` or a broadcaster must actually send them.

**Question 2.** Is \`sequenceNumber\` a unique event ID across all JVMs?  
**Answer:** No. It is assigned by the producer and can reset or collide.

**Question 3.** Why can in-memory dedup cause missed processing?  
**Answer:** If it marks an event seen before applying the side effect and the handler fails, retries are skipped.

**Question 4.** Why is a database unique constraint needed when multiple threads process the same ID?  
**Answer:** To ensure atomic uniqueness instead of falling into a check-then-insert race.

**Question 5.** When a JMX client reconnects, what must it do?  
**Answer:** Re-register the listener on the new connection, clean up/invalidate the old session, and refresh state.

**Question 6.** What is the best test against duplicate side effects?  
**Answer:** Assert the final business outcome, even when events are sent multiple times or concurrently, rather than asserting only callback counts.

**Question 7.** Do notifications replace a durable event store when complete auditing is required?  
**Answer:** No. JMX notifications do not by default persist or replay full history.

## 26. Takeaways

- Testing notifications requires separating the producer, local MBeanServer, remote connector, and business effects.
- JMX notifications are a signaling mechanism, **not a durable event log**.
- Duplicates can arise from listener registrations, producer re-emissions, reconnects, or downstream retries.
- \`sequenceNumber\` is useful for diagnostics but is not by default a durable dedup key.
- Use a **stable event ID** per logical event; include source/epoch when using sequences.
- In-memory dedup is appropriate only when restart loss, JVM-scoped concurrency, and failure-handling limits are acceptable.
- Database side effects require a unique constraint and a shared transaction with the dedup record.
- Dashboards should generally use notifications to trigger snapshot reads rather than relying on receiving every single event.
- When zero event loss is required, choose an outbox, event log, or broker with durable storage and idempotent consumers.

### References

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Javadoc — \`NotificationPublisherAware\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisherAware.html
- Spring Framework Javadoc — \`NotificationPublisher\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisher.html
- Java SE 21 API — \`Notification\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Java SE 21 API — \`NotificationListener\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
