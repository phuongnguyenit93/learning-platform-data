# Testing Notification Listeners and Filters in Spring Framework JMX

## Goal

In Java Management Extensions (JMX), an MBean can emit **notifications** to signal that runtime state has changed, a task has finished, or an operational event has occurred. Clients register a \`NotificationListener\` to receive notifications, and may provide a \`NotificationFilter\` to receive only a subset of events. Spring Framework supports JMX exporting alongside listener configurations to integrate notifications into applications.

When writing tests, you cannot merely check that a \`sendNotification()\` method was called. You must verify the full contract: **emitter source, notification type, ordering, sequence number, userData, filter, handback, registration/unregistration timing, and behavior when a listener throws an exception**. When receiving events remotely or across asynchronous threads, you also need to handle timeouts, dropped connections, and delayed deliveries.

This lesson helps you:

- Distinguish \`NotificationBroadcaster\`, \`NotificationEmitter\`, \`NotificationListener\`, and \`NotificationFilter\`.
- Write a test MBean that emits notifications with clear types and sequence numbers.
- Use \`MBeanServer.addNotificationListener\` and \`removeNotificationListener\` in JUnit.
- Test accepted notifications and events excluded by filters.
- Accurately verify \`handback\`, \`source\`, \`message\`, \`userData\`, and sequence numbers.
- Avoid test flakiness using \`CountDownLatch\`, bounded timeouts, and cleanup in \`finally\`.
- Test Spring listeners via \`NotificationListenerBean\`/exporter when integrating with \`ApplicationContext\`.
- Analyze the boundaries of local vs. remote notifications, thread ordering, duplicate callbacks, and context lifecycle.
- Design negative tests for filters, unregistration, and cross-test isolation.

## 1. JMX Notification Architecture

Key components:

\`\`\`text
Business event / runtime state
             |
             v
          MBean
             |
             v
NotificationBroadcaster / NotificationEmitter
             |
             v
         MBeanServer
             |
             +── Listener A + Filter A + Handback A
             |
             +── Listener B + Filter B + Handback B
             |
             +── Listener C (no filter)
\`\`\`

- \`Notification\` is an event carrying type, source, sequence number, timestamp, message, and optional userData.
- \`NotificationListener\` defines \`handleNotification(Notification, Object)\`.
- \`NotificationFilter\` decides which notifications are delivered for a specific registration.
- \`NotificationBroadcaster\` allows adding/removing listeners.
- \`NotificationEmitter\` adds exact listener removal matching listener/filter/handback.
- \`NotificationBroadcasterSupport\` is a utility base class commonly used when writing notification-emitting MBeans.
- \`MBeanServerConnection\` allows registering local or remote listeners depending on the connector.

A notification may be emitted without reaching a listener because:
1. The listener has not been registered yet.
2. The filter returns \`false\`.
3. The listener was already removed.
4. The MBean did not emit a notification along the code path under test.
5. The client connected to a different MBeanServer or ObjectName.
6. The remote connector failed or the subscription was lost.
7. The test ended too early, before the callback executed.

Therefore, tests should verify both **the delivery path and filtering conditions**, not merely how many times an emit method was invoked.

## 2. Defining the Notification Contract Before Testing

Suppose an MBean manages a worker and emits the following types:

| Type | Meaning | Expected Payload |
|---|---|---|
| \`com.example.worker.started\` | Worker started | Worker ID |
| \`com.example.worker.paused\` | Worker pause took effect | Pause reason |
| \`com.example.worker.failed\` | Worker failed | Redacted error code |
| \`com.example.worker.completed\` | A batch finished | Batch ID |

The test contract should specify:

- Type is a stable string.
- Source is the identity published via JMX.
- Sequence number increments according to the emitter's policy.
- Timestamp is validly assigned, without asserting an exact wall-clock instant prone to flakiness.
- Message contains no secrets.
- userData has a stable schema and bounded size.
- Whether ordering is guaranteed across multiple producer threads.
- What mechanism filters event types or severity.
- What handback, if any, the listener expects when the callback runs.

With remote JMX, payloads must be compatible with the connector's serializer/classloading. A custom Java object in userData may require the client to hold that class; consider \`CompositeData\` or simple types when broad interoperability is needed.

## 3. A Test MBean Capable of Emitting Notifications

A standard JMX MBean can implement \`NotificationEmitter\` or extend \`NotificationBroadcasterSupport\`. Example:

\`\`\`java
package com.example.jmx;

public interface WorkerEventsMBean {
    void start();
    void pause();
    void fail(String code);
    long getEventCount();
}
\`\`\`

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import javax.management.MBeanNotificationInfo;

public class WorkerEvents extends NotificationBroadcasterSupport
        implements WorkerEventsMBean {

    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void start() {
        publish("com.example.worker.started", "Worker started", "worker-A");
    }

    @Override
    public void pause() {
        publish("com.example.worker.paused", "Worker paused", "maintenance");
    }

    @Override
    public void fail(String code) {
        publish("com.example.worker.failed", "Worker failed", code);
    }

    @Override
    public long getEventCount() {
        return sequence.get();
    }

    private void publish(String type, String message, String data) {
        long n = sequence.incrementAndGet();
        Notification event = new Notification(
            type, this, n, System.currentTimeMillis(), message);
        event.setUserData(data);
        sendNotification(event);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {
            "com.example.worker.started",
            "com.example.worker.paused",
            "com.example.worker.failed"
        };

        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                Notification.class.getName(),
                "Lifecycle events for worker operations")
        };
    }
}
\`\`\`

In a JMX MBeanServer, the notification's \`source\` may be adjusted or represented as an \`ObjectName\` when dispatched through the server/connector. When testing the local class directly, the source may be \`this\`. Tests should therefore distinguish the emitter-level source contract from the source observed by a listener through the MBeanServer.

For Spring \`@ManagedResource\` and \`@ManagedNotification\`, the exporter/assembler handles notification metadata. When writing a standard MBean as above, no Spring annotations are required just to test filters.

## 4. Registering the MBean in Tests with Safe Cleanup

You can use a dedicated MBeanServer per test to avoid collisions with the application's platform server:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server = MBeanServerFactory.newMBeanServer();
ObjectName name = new ObjectName(
    "com.example.test:type=WorkerEvents,name=Local");

WorkerEvents bean = new WorkerEvents();
server.registerMBean(bean, name);
\`\`\`

\`newMBeanServer()\` creates a server not registered in the factory list like \`createMBeanServer()\`, making it well suited for simple isolated fixtures. When using the platform server, avoid fixed ObjectNames that collide across parallel tests and unregister only MBeans owned by the fixture.

Lifecycle example:

\`\`\`java
boolean owned = false;

try {
    server.registerMBean(bean, name);
    owned = true;

    // Add listeners, emit and assert notifications.
} finally {
    if (owned && server.isRegistered(name)) {
        server.unregisterMBean(name);
    }
}
\`\`\`

In real tests, listeners must also be removed inside \`finally\` before unregistering. This avoids callbacks firing into a finished fixture and interfering with subsequent tests.

## 5. Testing Listener Receipt by Notification Type

JUnit 5 can use \`CountDownLatch\` to await callbacks without arbitrary \`Thread.sleep\` calls:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import javax.management.*;

import org.junit.jupiter.api.Test;

class WorkerNotificationTest {

    @Test
    void receivesStartedNotification() throws Exception {
        MBeanServer server = MBeanServerFactory.newMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.test:type=WorkerEvents,name=Local");
        WorkerEvents bean = new WorkerEvents();
        server.registerMBean(bean, name);

        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<Notification> received =
            new AtomicReference<>();

        NotificationListener listener = (n, handback) -> {
            received.set(n);
            latch.countDown();
        };

        try {
            server.addNotificationListener(name, listener, null, null);

            server.invoke(name, "start", new Object[0], new String[0]);

            assertTrue(latch.await(3, TimeUnit.SECONDS));
            Notification n = received.get();
            assertNotNull(n);
            assertEquals("com.example.worker.started", n.getType());
            assertEquals("worker-A", n.getUserData());
            assertTrue(n.getSequenceNumber() > 0);
        } finally {
            try {
                server.removeNotificationListener(name, listener);
            } finally {
                if (server.isRegistered(name)) {
                    server.unregisterMBean(name);
                }
            }
        }
    }
}
\`\`\`

If the emitter and listener dispatch on the same thread, the latch is already counted down before \`invoke\` returns. If dispatched asynchronously, \`await\` handles bounded latency. A three-second timeout is illustrative; in real CI, set an appropriate threshold without allowing unbounded waits.

Do not assert \`n.getTimeStamp() == System.currentTimeMillis()\` because wall-clock time continuously advances. You can assert the timestamp falls within an acceptable test window with tolerance to avoid flakiness.

## 6. NotificationFilter and Filtering Semantics

A filter accepts a \`Notification\` and returns a boolean:

\`\`\`java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter failuresOnly =
    n -> n != null &&
         "com.example.worker.failed".equals(n.getType());
\`\`\`

When registering the listener:

\`\`\`java
server.addNotificationListener(
    name, listener, failuresOnly, "failure-subscription");
\`\`\`

With this filter, \`started\` or \`paused\` notifications are not delivered to that registration. \`failed\` is delivered to the listener alongside handback \`"failure-subscription"\`.

### 6.1 NotificationFilterSupport

JMX provides \`NotificationFilterSupport\` to enable type prefixes:

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter =
    new NotificationFilterSupport();

filter.enableType("com.example.worker.failed");
\`\`\`

Important: \`NotificationFilterSupport.enableType(String)\` checks type prefixes, not just full-string equality. If you enable \`"com.example.worker"\`, every type starting with that prefix may pass through the filter. For an exact match, write a custom \`NotificationFilter\` using \`equals\` or explicit string validation.

## 7. Testing Positive and Negative Filter Cases

A solid filter test proves both accepted events and excluded events:

\`\`\`java
@Test
void filterOnlyAcceptsFailures() throws Exception {
    MBeanServer server = MBeanServerFactory.newMBeanServer();
    ObjectName name = new ObjectName(
        "com.example.test:type=WorkerEvents,name=Filter");
    WorkerEvents bean = new WorkerEvents();
    server.registerMBean(bean, name);

    java.util.List<Notification> received =
        new java.util.concurrent.CopyOnWriteArrayList<>();
    CountDownLatch failureReceived = new CountDownLatch(1);

    NotificationListener listener = (n, hb) -> {
        received.add(n);
        failureReceived.countDown();
    };

    NotificationFilter filter =
        n -> "com.example.worker.failed".equals(n.getType());

    try {
        server.addNotificationListener(name, listener, filter, null);

        server.invoke(name, "start", new Object[0], new String[0]);
        server.invoke(name, "pause", new Object[0], new String[0]);
        server.invoke(
            name,
            "fail",
            new Object[]{"E_TIMEOUT"},
            new String[]{String.class.getName()});

        assertTrue(failureReceived.await(3, TimeUnit.SECONDS));
        assertEquals(1, received.size());
        assertEquals("com.example.worker.failed",
                     received.get(0).getType());
    } finally {
        try {
            server.removeNotificationListener(name, listener);
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

This test works well for a synchronous emitter and a simple emission sequence. With asynchronous dispatch or concurrent producers, asserting \`received.size() == 1\` right after the target event's latch could miss delayed callbacks from other sources if ordering is not enforced. In async tests, establish a synchronization point or drain the pipeline before making negative assertions.

**Do not use \`Thread.sleep(500)\` as absolute proof that no event arrived.** If a test needs to prove an event is blocked, test the filter directly and use completion/barrier primitives from the emitter or test executor.

## 8. Unit Testing Filters Independently

\`NotificationFilter\` can be unit-tested on its own without an MBeanServer:

\`\`\`java
@Test
void exactMatchFilterRejectsOtherTypes() {
    NotificationFilter filter =
        n -> "com.example.worker.failed".equals(n.getType());

    Notification failure =
        new Notification("com.example.worker.failed", "source", 1L);
    Notification started =
        new Notification("com.example.worker.started", "source", 2L);

    assertTrue(filter.isNotificationEnabled(failure));
    assertFalse(filter.isNotificationEnabled(started));
}
\`\`\`

Unit tests for filters catch bugs in \`startsWith\` logic, null handling, or severity comparisons. However, they do not prove the MBeanServer registered the filter properly; listener integration tests are still required to verify delivery.

### 8.1 Filters Using userData or Severity

If a filter inspects \`userData\`, check types and nulls:

\`\`\`java
NotificationFilter criticalOnly = n -> {
    if (n == null) {
        return false;
    }
    Object data = n.getUserData();
    if (!(data instanceof EventDetails details)) {
        return false;
    }
    return details.severity() >= 4;
};
\`\`\`

\`EventDetails\` is an illustrative application type. For remote JMX, custom DTOs require compatible serialization/classloading strategies; otherwise, prefer simple payloads or \`CompositeData\` for broader interoperability.

## 9. Handback: Verifying the Registration-Associated Parameter

A JMX listener has the signature:

\`\`\`java
void handleNotification(Notification notification, Object handback)
\`\`\`

\`handback\` is the object bound to the **listener registration**, not \`notification.getUserData()\`.

Example:

\`\`\`java
Object handback = "subscription-42";

NotificationListener listener = (n, hb) -> {
    assertEquals("subscription-42", hb);
};

server.addNotificationListener(name, listener, null, handback);
\`\`\`

If the same listener is registered multiple times with different filters/handbacks, it can receive multiple callbacks for the same notification across matching registrations. Therefore, any test counting callbacks must account for how many registrations are actually active.

Do not confuse handback with the payload emitted by the emitter. The emitter supplies \`Notification.userData\`; the party registering the listener supplies \`handback\`.

## 10. Unregistering Listeners: Testing No Events After Cleanup

A lifecycle test must prove the listener is removed cleanly and receives no subsequent notifications.

\`\`\`java
server.addNotificationListener(name, listener, null, null);
server.invoke(name, "start", new Object[0], new String[0]);

server.removeNotificationListener(name, listener);

server.invoke(name, "pause", new Object[0], new String[0]);
\`\`\`

With a synchronous emitter, after \`removeNotificationListener\` and emitting a new event, you can assert no new callback runs. With an async emitter, callbacks already enqueued before removal might still execute late. Tests must therefore distinguish:

- Notifications emitted **before** removal whose callbacks arrive **after**.
- Notifications emitted **after** removal.
- A listener registered multiple times with different filters/handbacks.
- A remote client whose connection dropped and subscription expired.

A deterministic test strategy is using a synchronous executor in the fixture, or a \`CountDownLatch\`/barrier to drain queued events before calling remove. If the goal is blocking post-removal events, emit a distinct-sequence event after confirming removal completed.

### 10.1 Remove Overloads Must Match the Registration

\`NotificationEmitter\` supports removing by exact listener/filter/handback:

\`\`\`java
removeNotificationListener(listener, filter, handback);
\`\`\`

\`MBeanServer.removeNotificationListener\` provides corresponding overloads. When the same listener is registered multiple times, use the matching overload and exact object identity/registration details to avoid removing the wrong one or missing one.

## 11. Testing Notification Metadata on MBeanInfo

An MBean can declare emitted types via \`MBeanNotificationInfo\`. Inspecting metadata:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

MBeanNotificationInfo[] notificationInfos =
    info.getNotifications();

boolean supportsFailed = java.util.Arrays.stream(notificationInfos)
    .flatMap(i -> java.util.Arrays.stream(i.getNotifTypes()))
    .anyMatch(type -> type.equals("com.example.worker.failed"));

assertTrue(supportsFailed);
\`\`\`

This verifies published metadata; it does not prove an event was actually emitted. A complete test combines metadata checks with callback tests. If metadata declares a type that the emitter never sends, only execution tests catch the gap.

Conversely, if the emitter sends a type omitted from metadata, clients may still receive it under some mechanisms, but the monitoring contract becomes unclear. Keep metadata synchronized with actual emitted events.

## 12. Testing Ordering, Sequence Numbers, and Timestamps

Each \`Notification\` has a sequence number defined by the emitter. In the example using \`AtomicLong.incrementAndGet()\`, sequences increase in allocation order:

\`\`\`java
assertTrue(second.getSequenceNumber() >
           first.getSequenceNumber());
\`\`\`

However, with multiple producer threads, the order of \`sendNotification\` calls may differ from sequence allocation order. With an asynchronous executor, callback execution order may also differ from emission order if the executor does not guarantee FIFO or uses multiple workers.

Define the contract clearly:
- Does sequence increase monotonically per emitter, or per type?
- Can gaps appear when a filter drops events?
- Does the client need to reorder or deduplicate?
- Are notifications retried or replayed after reconnect?
- Is the timestamp emission time, notification creation time, or business event time?

With a filter accepting only \`failed\`, sequence numbers might jump from 10 to 13 because other events were filtered out. **Never assert consecutive sequence numbers** on a filtered listener when the emitter interleaves other types.

## 13. Concurrency: Testing Concurrent Notifications

An emitter may publish from multiple threads:

\`\`\`java
ExecutorService pool = Executors.newFixedThreadPool(4);

try {
    for (int i = 0; i < 20; i++) {
        pool.submit(bean::start);
    }
} finally {
    pool.shutdown();
    assertTrue(pool.awaitTermination(5, TimeUnit.SECONDS));
}
\`\`\`

If a test uses an unsynchronized \`ArrayList\` inside a listener invoked from multiple threads, races can occur. Use \`CopyOnWriteArrayList\`, \`ConcurrentLinkedQueue\`, or explicit synchronization. Use a latch counting 20 callbacks, then assert total count, types, and a duplicate-free sequence set.

However, if the listener dispatches asynchronously on a separate executor, waiting only for the emitter thread pool to finish does not guarantee callbacks have completed. Use a latch in the listener or a dispatcher barrier. Never assume every \`NotificationBroadcasterSupport\` always dispatches on the caller thread: constructors can take an executor, and other implementations may behave differently.

## 14. Testing Callback Failures and Isolation

A listener may throw a runtime exception:

\`\`\`java
NotificationListener failing = (n, hb) -> {
    throw new IllegalStateException("simulated listener failure");
};
\`\`\`

When testing, understand the semantics of the broadcaster/dispatcher in use. Do not assume a failing listener causes all other listeners to lose notifications or causes the emitter method to throw; exact behavior depends on the implementation and executor.

A test can:
- Register both a failing listener and a healthy listener.
- Emit a notification.
- Check whether the healthy listener is invoked per the expected contract.
- Check that errors are logged/rate-limited rather than crashing domain processing.
- Ensure both listeners are cleaned up.

This is an important resilience test when notifications drive monitoring, though you must not rely on notifications as a durable message queue with acknowledgments. JMX notifications generally do not provide durable delivery or exactly-once semantics.

## 15. Spring Framework: Exporter and Listener Beans

Spring supports configuring listeners in its JMX ecosystem, such as \`NotificationListenerBean\` combined with \`MBeanExporter\`. A configuration can be structured as:

\`\`\`text
Spring ApplicationContext
  ├── WorkerEvents (MBean)
  ├── MBeanExporter
  │    └── export WorkerEvents → ObjectName
  └── NotificationListenerBean
       ├── listener
       ├── notificationFilter
       ├── handback
       └── mappedObjectNames
\`\`\`

When the exporter manages both registration and listeners, ensure listeners are attached once the MBean can receive notifications and removed when the context closes. In integration tests, verify by building a context with a small fixture and observing callbacks rather than only asserting bean presence.

Conceptual Java configuration example:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class NotificationJmxConfiguration {

    @Bean
    public WorkerEvents workerEvents() {
        return new WorkerEvents();
    }

    @Bean
    public NotificationListenerBean workerListenerBean(
            NotificationListener listener) {
        NotificationListenerBean bean =
            new NotificationListenerBean();
        bean.setNotificationListener(listener);
        bean.setMappedObjectNames(
            "com.example.test:type=WorkerEvents,name=Spring");
        return bean;
    }

    @Bean
    public MBeanExporter exporter(
            WorkerEvents workerEvents,
            NotificationListenerBean workerListenerBean) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(java.util.Map.of(
            "com.example.test:type=WorkerEvents,name=Spring",
            workerEvents));
        exporter.setNotificationListeners(workerListenerBean);
        return exporter;
    }
}
\`\`\`

This snippet requires concrete imports and a \`NotificationListener\` bean, plus the \`MBeanServer\` chosen by the fixture. Setter/constructor APIs must be verified against your Spring version. \`NotificationListenerBean\` supports corresponding mapping/handback/filter properties; tests should prove the listener actually attached to the right ObjectName rather than trusting configuration blindly.

### 15.1 Selecting the Right Server in Tests

If the exporter uses the platform MBeanServer, the test must query the platform server. If the exporter uses a dedicated server, inject that server and avoid calling \`ManagementFactory.getPlatformMBeanServer()\` in assertions. A properly configured listener attached to a different MBeanServer will still miss expected events.

## 16. Testing Spring Annotation Notification Metadata

Spring JMX provides \`@ManagedNotification\` and \`@ManagedNotifications\` to describe notification types in metadata for annotation-driven exported MBeans.

Illustrative example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.ops:type=WorkerEvents,name=Import")
@ManagedNotifications({
    @ManagedNotification(
        name = "com.example.worker.completed",
        description = "Worker completed a batch",
        notificationTypes = {
            "com.example.worker.completed"
        })
})
public class AnnotatedWorkerEvents {
    // Emitter/notification publisher implementation.
}
\`\`\`

Depending on the Spring Framework version, attributes and annotation placement must match the corresponding API. Metadata annotations **do not emit notifications by themselves**: the class must use a valid publisher/emitter mechanism. Tests must separate:
1. Annotation metadata exported as \`MBeanNotificationInfo\`.
2. Actual notifications emitted by the source.
3. Listeners/filters actually receiving or excluding events.

Do not treat annotations as a substitute for emitter behavior.

## 17. Remote JMX Notifications: How They Differ from Local Tests

With a remote connector, callbacks travel to the client over the connector transport and introduce network failures. Key differences:

| Aspect | Local MBeanServer | Remote connector |
|---|---|---|
| Latency | Typically low | Network and transport delay |
| Serialization | Fewer constraints | Payload needs classloading compatibility |
| Disconnection | No network failure | Subscription/connection may drop |
| Ordering | Per emitter/dispatcher | Also depends on transport and buffering |
| Timeout | Mostly thread scheduling | Network, reconnect, and client polling |
| Cleanup | Direct listener removal | Removal may fail if disconnected |
| Security | In-JVM boundary | Authentication, TLS, authorization |

Never run only local tests and claim remote notifications are safe, reliable, and lossless. For remote JMX, run integration tests through a \`JMXConnectorServer\` started in a dedicated fixture, with security credentials/trust where applicable, and clean up the connector/registry.

### 17.1 Lost Connection Does Not Mean Events Are Replayed

JMX notifications are not durable message queues by default. If a client disconnects, it may miss events emitted during the outage. When reliable state is required, clients should combine notifications with **reading current state** or metrics and performing idempotent reconciliation after reconnect.

Notifications are suited for signals and near-real-time updates, not as the sole source of truth for business workflows that cannot tolerate data loss.

## 18. Testing Callback Removal on Context Close

A long-lived leak happens when a listener still holds references to a destroyed Spring bean or finished test fixture:

\`\`\`text
Context A:
  listener A registered
  context.close()
  listener A remains
     |
     v
Old bean retained / callback to destroyed component
\`\`\`

Integration tests should:
1. Start the Spring context and register the MBean/listener.
2. Emit an event and assert the listener receives it.
3. Close the context.
4. Emit an event from a surviving source if the fixture permits.
5. Verify context A's listener is no longer invoked, while MBeans from other contexts are not mistakenly removed.

When the MBean itself is unregistered on context close, to test listener cleanup independently you can use an emitter owned by a longer-lived fixture/shared owner. Do not try invoking an unregistered MBean and interpret \`InstanceNotFoundException\` as proof that "the listener was removed properly".

## 19. Testing Negative Filter Cases with Clear Synchronization

A flaky negative test looks like:

\`\`\`java
emit("started");
Thread.sleep(100);
assertEquals(0, calls.get());
\`\`\`

It can pass while the event is still queued, only for the callback to run after the assertion. Instead, you can:

- Test \`NotificationFilter.isNotificationEnabled\` directly.
- Use a synchronous executor in the fixture so callbacks finish before \`emit\` returns.
- Use a test dispatcher barrier/ack.
- Emit a sentinel event accepted by the filter after the rejected event, then wait for the sentinel; only infer ordering if the dispatcher guarantees FIFO.
- For remote async, use an explicit deadline and state reconciliation rather than claiming absolute absence from a sleep.

For example, a \`NotificationBroadcasterSupport\` fixture without an asynchronous executor dispatches synchronously per its implementation. When a test is single-threaded with no other producers, assertions can run right after the emit call. With a custom executor, the test must control that executor directly.

## 20. Instrumentation and Preventing Listener Leaks

Signals worth monitoring in test/staging:

- Listener registration count per MBean.
- Callback count per type.
- Filtered-out notification ratio.
- Latency from emit to receive.
- Duplicate callback frequency.
- Callback exception count.
- Number of notifications consumers fail to keep up with.
- Number of open remote connections.
- Remaining listeners after shutdown/redeploy.

Not every MBean provides a built-in API to count listeners. You can add instrumentation in an application emitter/registration wrapper or test via callback side effects. Avoid exposing metrics solely for testing if doing so unnecessarily widens the management surface.

## 21. End-to-End Testing Workflow

### Before the Test

1. Pick a unique ObjectName and an isolated test MBeanServer.
2. Define the type/source/payload/sequence contract.
3. Create an emitter with deterministic behavior.
4. Define the filter and handback.
5. Prepare latches or a controlled executor.
6. Clarify who owns the MBean and listener registrations.

### During the Test

1. Register the MBean.
2. Add the listener/filter.
3. Emit both allowed and excluded events.
4. Await callbacks with a timeout.
5. Assert type, payload, handback, and metadata.
6. Verify negative cases with proper synchronization.
7. For concurrency tests, use thread-safe collections and assert received counts.

### After the Test

1. Remove listeners matching their exact registrations.
2. Unregister the MBean if owned by the fixture.
3. Shut down any fixture-created executors or connectors.
4. Verify no events reach callbacks of a closed fixture.
5. Do not delete another test's MBean merely because its ObjectName shares the same domain.

## 22. Common Mistakes

**"Filter enableType performs an exact match."** False. \`NotificationFilterSupport\` matches by prefix. Use a custom filter when an exact type match is required.

**"Listener did not receive anything so the emitter did not emit."** Not necessarily; the filter may have dropped it, the listener may not be registered, the server may differ, or the callback arrived late.

**"Sleeping a few hundred milliseconds proves no callback occurred."** Unreliable under async/remote dispatch.

**"Handback is userData."** False. Handback belongs to the registration; userData belongs to the notification event.

**"Sequence numbers are always consecutive on a filtered listener."** False. Filtered-out events still consume sequence numbers, leaving gaps in what is received.

**"MBeanInfo listing a type means a notification was emitted."** False. Metadata declares capability; callback tests prove runtime behavior.

**"Once a listener is removed, no late callback can ever arrive."** Not guaranteed across all async dispatchers; callbacks already queued beforehand may still execute.

**"Spring annotations automatically send notifications."** False. Metadata and emitter behavior are separate concerns.

**"Remote notifications replay after reconnect."** Not by default; reconcile effective state after reconnecting.

## 23. Practice Exercises

**Exercise 1 — Positive/negative filter.** Create a listener accepting only \`com.example.worker.failed\`; emit started, paused, and failed. Assert exactly one failure event reaches the listener. Add a filter unit test as well.

**Exercise 2 — Handback.** Register the same listener twice with different handbacks and different filters. Explain when the callback can fire twice and how to remove each registration individually.

**Exercise 3 — Sequence.** An emitter sends sequence 1:started, 2:failed, 3:paused, 4:failed. The filter accepts only failed. Should you assert sequence [1,2] at the listener? No; expect [2,4] per emitter sequence.

**Exercise 4 — Async race.** A negative test uses \`Thread.sleep(50)\`. Redesign it using a controlled executor or barrier, and explain why fixed sleeps cause flakiness.

**Exercise 5 — Spring context lifecycle.** A listener is registered via an exporter and the context closes. Design a test proving the listener does not leak without unregistering an MBean owned by another context.

**Exercise 6 — Remote reconnect.** A client disconnects while the worker emits a paused event. Why shouldn't notifications be treated as durable records? Propose how to read effective state after reconnecting.

## Summary

Testing notification listeners and filters in Spring Framework JMX requires verifying both the **event contract** and the **delivery mechanism**: listener registration, notification types, filter acceptance/rejection, handback, metadata, payload, sequence numbers, and lifecycle. Use \`CountDownLatch\`, controlled executors, and dedicated test servers to avoid arbitrary timing dependencies. Clearly separate filter unit tests from MBeanServer integration tests; for remote connectors, also test transport, serialization, reconnect, and security. Finally, always clean up listeners and MBeans according to ownership so tests remain independent without callback leaks or collisions inside the Spring \`ApplicationContext\`.
