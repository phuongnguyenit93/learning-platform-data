# Filtering Notifications on the Emitter Side vs. Receiver Side in Spring Framework JMX

## Objectives

JMX notifications are a mechanism for an MBean to announce events to registered listeners. When a Spring Framework application emits many notifications, the crucial decision is not only **which events to filter** but also **where to place the filtering**: on the emitting side (source/emitter), on the registration and receiving side (listener), or both.

Filter placement directly affects event-creation cost, system complexity, data reusability across multiple listeners, operational safety, and the risk of missing events. A proper listener-side filter saves callbacks but still does not save payload-creation cost at the emitter. Conversely, dropping events at the emitter saves resources but deprives all listeners of observing those events.

This lesson helps you:

- Understand the roles of \`NotificationBroadcaster\`, \`NotificationEmitter\`, \`NotificationListener\`, and \`NotificationFilter\`.
- Distinguish source-level event selection from per-subscriber event selection.
- Explain the sequence of sending notifications, checking filters, and invoking listeners in JMX.
- Register listeners/filters on \`MBeanServer\` or via \`NotificationListenerBean\` configuration in Spring.
- Design filtering by type, source, severity, and bounded data.
- Evaluate trade-offs among performance, observability completeness, security, consistency, and lifecycle.
- Diagnose cases where a listener misses events even though the emitter fired, or a callback receives too much data.

## 1. Notification Flow Diagram

A single MBean event source can send multiple notification types:

\`\`\`text
Spring Application
      |
      v
MBean / NotificationEmitter
      |
      | 1. emits Notification (type, source, seq, timestamp, message, userData)
      v
JMX broadcaster
      |
      +--> listener A's filter ---> listener A (metrics)
      |
      +--> listener B's filter ---> listener B (audit)
      |
      +--> listener C's filter ---> listener C (alert)
\`\`\`

When the emitter does not create a notification, **no listener** can recover that information by changing its receiver-side filter. When the emitter creates a notification and one listener's filter returns \`false\`, that listener skips the event; other listeners can still receive it.

Compare the two questions side by side:

| Decision | Core Question |
|---|---|
| Emitter-side filtering | Should this event kind be constructed and sent from the source at all? |
| Receiver-side filtering | Does this specific subscriber care about an event that was emitted? |

These are two different decision levels, not two syntaxes for writing the same filter.

## 2. Related JMX Components

**\`Notification\`** contains basic fields such as \`type\`, \`source\`, \`sequenceNumber\`, \`timeStamp\`, \`message\`, and \`userData\`. \`type\` is usually a hierarchical string such as \`com.example.jobs.failed\`.

**\`NotificationBroadcaster\`** defines listener registration/removal and describes notification types via \`getNotificationInfo()\`.

**\`NotificationEmitter\`** extends \`NotificationBroadcaster\` with exact removal of a listener/filter/handback triple. An MBean can use \`NotificationBroadcasterSupport\` to implement the emission mechanism.

**\`NotificationListener\`** receives callbacks:

\`\`\`java
void handleNotification(Notification notification, Object handback);
\`\`\`

**\`NotificationFilter\`** decides whether a notification should be delivered to a registered listener:

\`\`\`java
boolean isNotificationEnabled(Notification notification);
\`\`\`

\`handback\` is an object provided by the client at registration time and passed back to the listener; it is not authentication metadata and must not be treated as proof of authorization.

**\`NotificationFilterSupport\`** is a built-in implementation allowing types by prefix; types are enabled via \`enableType(String)\`. Because it uses prefix matching, enabling \`com.example.jobs\` can match \`com.example.jobs.failed\` along with many other subtypes. When you need to filter one exact type, write a custom filter using \`equals\`.

## 3. Receiver-Side Filtering: Filters Bound to Individual Registrations

This is the standard JMX mechanism, used when one emitter has multiple subscribers with different interests.

Examples:

- A metrics listener wants all \`job.completed\` events to increment counters.
- An alert listener wants only \`job.failed\`.
- An audit listener needs state-change events per retention policy.
- An operations UI shows only events belonging to a monitored component.

A \`NotificationFilter\` is passed when registering the listener:

\`\`\`java
import javax.management.*;

NotificationFilter failuresOnly = notification ->
    "com.example.jobs.failed".equals(notification.getType());

NotificationListener listener = (notification, handback) -> {
    System.out.println("Failure event #" + notification.getSequenceNumber());
};

server.addNotificationListener(
    objectName,
    listener,
    failuresOnly,
    null
);
\`\`\`

When the source sends \`com.example.jobs.completed\`, this filter returns \`false\`; the exact same notification can still be delivered to another listener with a matching filter.

Do not bake one consumer group's decision into the emitter if other groups need that kind of data. For instance, turning off completion notifications at the source just because a dashboard does not display them can starve the metrics listener of data.

### 3.1 Filtering by type with NotificationFilterSupport

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.jobs.failed");

server.addNotificationListener(
    objectName,
    listener,
    filter,
    "operations-dashboard"
);
\`\`\`

Here \`handback\` is an application-chosen string; it does not have to appear inside the notification and does not secure the endpoint. If you want to receive only \`com.example.jobs.failed\` and not other types starting with that prefix, use a \`NotificationFilter\` with exact comparison.

### 3.2 Filtering by notification attributes

\`\`\`java
NotificationFilter slowFailures = n -> {
    if (!"com.example.jobs.failed".equals(n.getType())) {
        return false;
    }
    Object data = n.getUserData();
    if (!(data instanceof FailureInfo failure)) {
        return false;
    }
    return failure.durationMillis() >= 5_000;
};
\`\`\`

\`FailureInfo\` in the example is an application-defined data type. When receiving notifications remotely, consider serialization and class availability; an arbitrary DTO is not guaranteed to be compatible across processes. For notifications aimed at general JMX tools, prefer simple payloads or Open MBean data under a stable contract.

Filters should be fast and deterministic, avoiding database access, global locks, or HTTP calls per event. If filtering is heavy, the emission source can slow down or bottleneck the event pipeline.

## 4. Emitter-Side Filtering: Deciding Whether to Create/Send Events

Example emitter creating a notification after each job:

\`\`\`java
Notification n = new Notification(
    "com.example.jobs.completed",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Job completed");
sendNotification(n);
\`\`\`

If the system completes tens of thousands of jobs per second, creating every notification, building payloads, recording metadata, and dispatching to many listeners can impose significant load. A condition can be placed at the source:

\`\`\`java
if (emitCompletionNotifications) {
    Notification n = new Notification(
        "com.example.jobs.completed",
        this,
        sequence.incrementAndGet(),
        System.currentTimeMillis(),
        "Job completed");
    sendNotification(n);
}
\`\`\`

When the condition is false, the completion notification is **never created**. This is sampling or a source-layer emission policy, not a listener-attached JMX \`NotificationFilter\`. Operators must know this clearly because dropping an event at the source loses data for all subscribers.

Filtering at the source makes sense when:

- Events have very high frequency and per-event publication is unnecessary.
- Content must not be emitted on the management channel due to sensitivity.
- The product contract requires only specific milestones or state transitions.
- Another more reliable channel exists for detailed data, such as aggregate metrics or a dedicated audit log.

However, if a notification is already part of an observability or compliance contract, disabling emission must be managed like an interface and operational change. Never assume sampling can replace an audit requiring completeness.

### 4.1 Conditional payload construction

Even when all listeners should receive failure notifications, we can still avoid building expensive diagnostic payloads unless truly needed:

\`\`\`java
if (notifyFailures) {
    String summary = buildBoundedFailureSummary(failure);
    Notification n = new Notification(
        "com.example.jobs.failed",
        this,
        sequence.incrementAndGet(),
        System.currentTimeMillis(),
        summary);
    sendNotification(n);
}
\`\`\`

Do not build \`buildBoundedFailureSummary\` before the \`if\` if the goal is saving cost when not emitting. Payload contents should be bounded and mask secret data. Never put unbounded stack traces, tokens, or raw request bodies into \`userData\`.

## 5. Comparing Cost and Completeness

| Aspect | Emitter-Side Filtering | Receiver-Side Filtering |
|---|---|---|
| Is the notification created? | Can be skipped completely | Source still creates it |
| Is the payload created? | Can be avoided before sending | Usually already created at source |
| Does data reach all subscribers? | No, if the source drops it | Each subscriber chooses individually |
| Saves listener callbacks | Yes | Yes |
| Reduces emission cost at source | Often possible | Partially or not at all |
| Multi-purpose reusability | Limited by source policy | Higher, as listeners have their own filters |
| Risk of global information loss | Higher if critical events are dropped | Scoped only to the filtered subscriber |
| Best suited for | Sampling, suppressing unnecessary data, rate limiting | Routing by type, severity, source, interest |

A practical two-tier design:

\`\`\`text
Business event
   |
   +--> Should it be exposed via JMX? (source policy)
   |          |
   |         No → do not emit JMX notification
   |          |
   |         Yes
   |          v
   |   Build notification with sufficient, size-bounded data
   |          |
   |          v
   |   broadcaster dispatches per each registration's filter
   |          |
   +----------+-----------------+
              |                 |
       Alert listener     Metrics listener
\`\`\`

Note that JMX notifications are not a durable queue by default. Late-connecting or disconnected listeners can miss events. Therefore, if complete history and replay are required, use durable storage or messaging with appropriate guarantees; filters do not solve transport reliability.

## 6. Creating a Notification Emitter in a Spring Application

Example MBean using \`NotificationBroadcasterSupport\`:

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.*;

public interface JobMonitorMBean {
    long getProcessedCount();
}

public class JobMonitor extends NotificationBroadcasterSupport
        implements JobMonitorMBean {

    private final AtomicLong sequence = new AtomicLong();
    private final AtomicLong processed = new AtomicLong();
    private volatile boolean emitCompleted = false;

    @Override
    public long getProcessedCount() {
        return processed.get();
    }

    public void onJobCompleted(String jobId) {
        processed.incrementAndGet();

        if (!emitCompleted) {
            return;
        }

        Notification notification = new Notification(
            "com.example.jobs.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Job completed"
        );
        // Put only filtered and bounded data on the JMX channel.
        sendNotification(notification);
    }

    public void onJobFailed(String jobId, String safeReasonCode) {
        Notification notification = new Notification(
            "com.example.jobs.failed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Job failed: " + safeReasonCode
        );
        sendNotification(notification);
    }

    public void setCompletionNotificationsEnabled(boolean enabled) {
        this.emitCompleted = enabled;
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {
            "com.example.jobs.completed",
            "com.example.jobs.failed"
        };
        return new MBeanNotificationInfo[]{
            new MBeanNotificationInfo(
                types,
                Notification.class.getName(),
                "Lifecycle events emitted by job processing")
        };
    }
}
\`\`\`

The \`setCompletionNotificationsEnabled\` method in the example is an internal Java API, **not yet exposed** as a JMX operation or attribute under the declared \`JobMonitorMBean\`. If you want to change emission policy from JMX, treat that as a monitoring-system control action with proper permissions and auditing. \`getNotificationInfo()\` describes the notification types the broadcaster can emit; it does not guarantee every type is generated at all times.

When registering the class as a Standard MBean, the naming convention interface \`JobMonitorMBean\` defines the exposed attributes/operations. \`NotificationBroadcasterSupport\` provides emission, listener registration, and removal.

### 6.1 Registering the MBean and listener

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.*;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.jobs:type=Monitor,name=Primary");

JobMonitor monitor = new JobMonitor();
server.registerMBean(monitor, name);

NotificationListener errorListener = (notification, handback) -> {
    System.out.println(notification.getType()
        + " at " + notification.getTimeStamp());
};

NotificationFilter errors = n ->
    "com.example.jobs.failed".equals(n.getType());

server.addNotificationListener(name, errorListener, errors, null);
\`\`\`

To avoid listener leaks and restart failures in the same JVM, the component that registered the listener must remove its registration when stopping:

\`\`\`java
server.removeNotificationListener(name, errorListener);
server.unregisterMBean(name);
\`\`\`

This order fits an example where a single owner manages everything. In multi-context systems, do not unregister MBeans owned by other components. If the same listener was registered multiple times with different filters/handbacks, track and remove those exact registrations; \`removeNotificationListener(name, listener)\` may remove matching registrations per the JMX contract.

## 7. Notifications in Spring: Exporter and Listener Bean

Spring Framework provides a mechanism to register notification listeners for application-managed MBeans via \`MBeanExporter\` and \`NotificationListenerBean\`. The idea is to declare listeners and select emitter MBeans in Spring configuration instead of scattering registrations across methods.

Illustrative configuration example with \`NotificationListenerBean\`:

\`\`\`java
import javax.management.NotificationFilter;
import javax.management.NotificationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class NotificationConfiguration {

    @Bean
    NotificationListenerBean failureNotificationListener() {
        NotificationListener listener = (notification, handback) -> {
            System.out.println("JMX failure: " + notification.getType());
        };

        NotificationFilter filter = notification ->
            "com.example.jobs.failed".equals(notification.getType());

        NotificationListenerBean bean = new NotificationListenerBean();
        bean.setNotificationListener(listener);
        bean.setNotificationFilter(filter);
        return bean;
    }
}
\`\`\`

\`NotificationListenerBean\` carries listener and filter metadata; it must be properly wired into \`MBeanExporter\` with matching MBean names to take effect. Merely declaring \`@Bean NotificationListenerBean\` does not mean the exporter automatically discovers and registers every listener bean. Below is a direct exporter configuration example demonstrating that wiring:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.*;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class ExplicitJmxExportConfiguration {

    @Bean
    JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    MBeanExporter jmxExporter(JobMonitor monitor,
                              NotificationListenerBean failureNotificationListener)
            throws MalformedObjectNameException {
        String objectName = "com.example.jobs:type=Monitor,name=Primary";

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(ManagementFactory.getPlatformMBeanServer());
        exporter.setBeans(Map.of(objectName, monitor));

        failureNotificationListener.setMappedObjectName(
            new ObjectName(objectName));
        exporter.setNotificationListeners(
            new NotificationListenerBean[]{failureNotificationListener});
        return exporter;
    }
}
\`\`\`

Ensure no other export mechanism duplicates \`JobMonitor\` registration under the same \`ObjectName\`. Exact configuration may vary when using Spring Boot auto-configuration, annotation exporters, or module bean factories.

If you need to filter by notification data rather than type alone, you can use a custom \`NotificationFilter\`; filter code runs during notification dispatch so it must be compact, fast, and concurrency-safe.

## 8. The Truth About Where Filters Execute

When using standard \`NotificationBroadcasterSupport\`, filters are applied by the broadcaster before invoking that registration's listener callback. This means:

1. The emitter still constructs the \`Notification\` object.
2. The emitter calls \`sendNotification(notification)\`.
3. The broadcaster iterates over listener registrations and checks each filter.
4. For accepted registrations, callbacks are invoked via the broadcaster's execution mechanism.

Because step 1 has already occurred, receiver-side filtering does not avoid the cost of building notifications and payloads. It reduces unnecessary callbacks.

However, over remote JMX connections, listeners/filters may be handled at different layers depending on the connector implementation and API usage. Do not assume a custom Java filter executes in a specific process or prevents all bytes from crossing the wire. If network optimization is mandatory, test the actual connector and design filtering at the source or on a management endpoint with a clear contract.

Additionally, \`NotificationBroadcasterSupport\` can take an executor via constructor. With the default executor, callbacks typically run synchronously on the emitting path; a slow listener can slow down the emitter. When configuring an asynchronous executor, consider queues, callback ordering, saturation, and lifecycle. A filter performing blocking work can still impact the sending path.

## 9. Filtering by Type, Source, Severity, and userData

### 9.1 Type

Use exact comparison when a strict contract is required:

\`\`\`java
NotificationFilter exactFailure = n ->
    "com.example.jobs.failed".equals(n.getType());
\`\`\`

Use \`NotificationFilterSupport\` when intentionally subscribing to an entire prefix group. Document the namespace clearly to avoid accidentally matching newly added future types.

### 9.2 Source

\`Notification.getSource()\` can be an MBean object, a management name, or a type supplied by the emitter. Do not assume every source is an identical \`ObjectName\`, especially across connectors or multiple notification-emitting libraries.

Example:

\`\`\`java
NotificationFilter sourceFilter = n ->
    "com.example.jobs:type=Monitor,name=Primary"
        .equals(String.valueOf(n.getSource()));
\`\`\`

This is only an illustrative string comparison. Production configuration should establish a reliable source representation before comparing; if the source is an \`ObjectName\`, comparing directly against the expected \`ObjectName\` carries stronger semantics.

### 9.3 Severity

Base JMX \`Notification\` **has no standard severity field**. To filter alerts by severity, define it via type or payload:

\`\`\`text
com.example.jobs.failed.warning
com.example.jobs.failed.critical
\`\`\`

Or a structured payload with \`severity\`, \`errorCode\`, \`component\`; in that case, standardize the schema and client compatibility. Avoid parsing severity from free-form \`message\` strings.

### 9.4 UserData

\`userData\` is an extension field and may contain sensitive information; filters inspecting it must check type, nullability, and data length. The emitter should redact before sending because another listener might not apply the current filter. Receiver-side filtering is not a security boundary for data already published to a connector.

## 10. Performance: Accounting for Cost at the Right Stage

Suppose an application has 10,000 jobs completing per second and 3 listeners, only one of which needs completion events.

**Option A: emit every completion**. The source creates 10,000 notifications/sec, the broadcaster checks filters per registration, and invokes only accepting listeners. Source overhead remains high even though two listeners discard them.

**Option B: do not emit completions, expose counters only**. The source updates an atomic counter and emits rare failures/transitions. Per-completion detail is absent on JMX, while aggregate metrics provide lightweight observability.

**Option C: sampled completions with a documented contract**. The source emits under rate limiting or sampling. Listeners know the stream is only a sample; it must not be used to count total jobs. Total counts should come from separate metrics/counters.

Selection criteria:

- Is the goal aggregate observability or recording every individual event?
- What are the frequency and payload size?
- Is any subscriber required to receive 100% of events?
- Does losing one event impact operational decisions or audit requirements?
- Can callbacks withstand backpressure and bursts?
- Are aggregate metrics, a durable stream, or JMX notifications better suited?

Even though JMX can broadcast events to multiple listeners, it must not be turned into a business event bus replacing Kafka, JMS, or durable log/audit systems.

## 11. Reliability, Ordering, and Listener Lifecycle

### 11.1 Do not use JMX notifications as the sole audit log

JMX notifications do not provide durable storage or replay for late-connecting listeners by default. A disconnected listener can miss events. \`sequenceNumber\` helps identify the emitter-assigned sequence and detect gaps within a defined scope; it does not guarantee exactly-once delivery or continuity across restarts.

If full auditing is needed, persist events in a reliable store before or alongside management notifications.

### 11.2 Listeners registered and removed with proper lifecycle

Spring applications undergo context refreshes, redeploys, or repeated test runs; if the same listener is registered repeatedly without removal, callbacks can run multiple times for the same notification. If an MBean is unregistered or re-registered under the same name, subscriptions must be managed per MBeanServer/connector rules; do not assume an old registration remains valid for a new instance.

Ensure the component owning the listener knows when to register, remove, and close executor resources. If the listener performs heavy I/O, offload work to a bounded internal queue; avoid blocking the emission path with network calls.

### 11.3 Ordering and concurrency

\`sequenceNumber\` is normally incremented by the emitter in logical emission order, yet using an asynchronous executor can cause observed callback order to differ from creation order. Listeners should not rely on an assumption that "callbacks are always single-threaded and always sequential" when broadcaster or connector configurations can change.

If multiple listeners run concurrently, filters must be thread-safe. Avoid unsynchronized mutable state inside \`isNotificationEnabled\`.

## 12. Security: Receiver-Side Filtering Does Not Replace Access Control

A common question: "Only team A should see sensitive notifications; is adding a filter for team B to drop them enough?" The answer is **not enough**. Once information has been published by an emitter onto JMX, another client with subscription permissions can choose a different filter or no filter at all. Protection must come from:

1. **The emitter**: do not put secrets/PII or unauthorized raw payloads into notifications.
2. **JMX permissions**: authentication, authorization, network/TLS, and appropriate MBean restrictions.
3. **Separating endpoints or MBeans**: if client groups have different permissions, the management surface structure should reflect that.
4. **Listener filters**: tailoring displayed information and reducing callback work after access has been granted.

If tenant/user-level security is required, establish trustworthy identity and enforcement at the system boundary, rather than relying on a client-supplied filter lambda.

## 13. Diagnosing Unreceived Notifications

Below is an investigation procedure from source to destination:

| Symptom | Possibility | Check |
|---|---|---|
| No listener receives anything | Emitter does not call \`sendNotification\` or emission policy blocks it | Internal source counters, enablement config |
| One listener receives nothing | Filter rejects it, listener registered on wrong emitter | \`type\`, \`ObjectName\`, registration, and filter |
| Listener receives duplicates | Registered multiple times, multiple identical emitters | Add/remove lifecycle, emitter identity |
| Listener receives too much | Broad \`NotificationFilterSupport\` prefix, null filter | Enabled types list, filter logic |
| Events arrive delayed | Blocking callback, congested executor, slow connector | Queue/executor metrics, callback latency |
| Events stop after context restart | Listener not re-registered or MBean instance replaced | MBean and listener lifecycles |
| Remote listener fails to decode data | \`userData\` has unknown/unserializable class | Payload contract, MXBean/OpenType |
| High event volume spikes CPU | Emitted too frequently or heavy filter | Rate, allocations, and filter cost |

### 13.1 Non-disruptive instrumentation

Some useful counters inside the emitter:

\`\`\`text
eligibleEvents
notificationsCreated
notificationsSent
notificationsSuppressedBySourcePolicy
listenerCallbackFailures
\`\`\`

Define exact metric meanings; the broadcaster might not know whether every callback was successfully processed by remote clients. \`notificationsSent\` may only mean the emitter called \`sendNotification\`, without guaranteeing client receipt.

To test filters, emit test events with a distinct type and non-sensitive payload, avoiding injecting fake failures into production alerting pipelines where they might trigger pages/incidents.

## 14. Applied Exercises

### Exercise 1: choosing the filtering layer

An application emits 50,000 \`cache.hit\` notifications per second and 2 \`cache.eviction.failed\` notifications per minute. Dashboards need only the hit ratio; the on-call team needs failures.

Design direction: use counters/hit ratio instead of individual \`cache.hit\` notifications at the source; continue emitting failures with small payloads; on-call listener filters strictly for \`cache.eviction.failed\`. If investigators genuinely need hit samples, add sampling under a separate contract.

### Exercise 2: distinguishing prefix vs. exact

\`\`\`java
NotificationFilterSupport f = new NotificationFilterSupport();
f.enableType("com.example.jobs");
\`\`\`

Can the filter accept \`com.example.jobs.failed\`? Yes, because matching is prefix-based. If you want strictly \`com.example.jobs\`, use a \`NotificationFilter\` with \`equals\`.

### Exercise 3: two listeners

Design a broadcaster emitting \`job.started\`, \`job.completed\`, and \`job.failed\`. Listener A receives only failures, listener B receives started/completed. Write two corresponding \`NotificationFilter\` instances and test the types; each listener must be cleanly registered and cleaned up.

### Exercise 4: security review

An MBean emits notifications containing a token in \`userData\`. One listener intentionally filters by \`type\` to exclude token notifications. Does this solve the problem? No. The token has already been published to the management channel and can be received by another listener; it must be removed/masked at the emitter side and proper access controls applied.

### Exercise 5: slowdown case study

After adding a listener that sends an HTTP request on every failure, the job-processing path begins slowing down. Determine whether callbacks run synchronously or via an executor, measure latency, and consider moving to bounded asynchronous processing. Even when switching to async, handle full queues and shutdown; never create an unbounded executor.

## Summary

**Emitter-side filtering** is a source policy: which events are constructed and published via JMX. It can save CPU/memory and avoid emitting unnecessary content, but also drops events for every subscriber. **Receiver-side filtering** is a per-registration choice: which published notifications a particular listener cares about. It aids routing, cuts callbacks, and separates consumer needs, yet does not eliminate payload-creation cost at the source and does not replace security or durable storage.

A solid Spring JMX design clearly defines the event-type contract, places global suppression policies at the source, uses \`NotificationFilter\` for listener-specific needs, bounds overhead, manages registration/removal lifecycles, and maintains independent observability to know how the system actually emitted, filtered, and processed notifications.
