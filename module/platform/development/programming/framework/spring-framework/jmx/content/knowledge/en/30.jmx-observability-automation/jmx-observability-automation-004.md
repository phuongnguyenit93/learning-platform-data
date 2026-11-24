# Pushing Notifications as Operational Events in Spring Framework JMX

## 1. Objectives

JMX notifications are runtime signals emitted by MBeans. In Spring Framework JMX, management components commonly use notifications to report the state of workers, queues, caches, or downstream connections. To use them in operations, these notifications must be turned into structured **operational events** that are easy to store, search, alert on, and use to trigger runbooks.

Target processing chain:

~~~text
Business event
   -> Spring MBean
   -> JMX notification
   -> NotificationListener
   -> normalizer / enricher
   -> bounded queue / durable pipeline
   -> operational event sink
   -> alerting / dashboard / automation
~~~

Example notification:

~~~text
type=com.example.orders.queue.threshold
source=com.example.orders:type=Queue,name=payments
message=Queue backlog above threshold
~~~

Corresponding operational event:

~~~json
{
  "eventType": "queue.backlog.high",
  "service": "checkout",
  "environment": "production",
  "instance": "checkout-2",
  "resource": "payments",
  "severity": "warning",
  "occurredAt": "2026-11-11T09:00:00Z",
  "summary": "Queue backlog exceeded threshold",
  "attributes": {
    "pendingCount": "1400",
    "threshold": "1000"
  }
}
~~~

These JSON values are illustrative only, not real data. In a real system, target identity, timestamp, severity, and payload must come from trusted sources.

## 2. Distinguishing Notification, Operational Event, and Alert

| Concept | Meaning | Example |
| --- | --- | --- |
| JMX notification | Runtime message sent through MBeanServer | com.example.queue.threshold |
| Operational event | Event record with a stable schema and operational context | queue.backlog.high |
| Alert | Evaluation of a condition needing attention or action | Backlog above threshold for 5 minutes |
| Incident | Operational issue requiring coordinated response | Checkout degraded |
| Automation action | Policy-approved action | Collect diagnostics |

Not every notification warrants an alert. If every metric fluctuation creates an incident, the system will generate alert fatigue and make real incidents harder to identify.

## 3. Designing Responsibilities by Layer

**Emitter MBean:** detects state transitions and emits notifications with clear types.

**Listener:** receives callbacks quickly, validates the event type, and pushes into the pipeline.

**Normalizer:** maps type, ObjectName, and userData into a schema independent of Java JMX.

**Enricher:** adds service, environment, target JVM, deployment version, and correlation ID.

**Event sink:** forwards to an event log, broker, alerting system, or operations API.

**Automation engine:** decides actions after checking security preconditions, idempotency, and cooldowns.

Do not let the emitter send HTTP requests directly to multiple external systems or place full retry logic inside `handleNotification`. That introduces coupling where network slowness can impact the event-emission path.

## 4. Spring NotificationPublisher on the Source Side

A bean that wants to emit notifications via Spring JMX can implement NotificationPublisherAware.

~~~java
package com.example.orders.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments",
    description = "Payment queue management"
)
@ManagedNotification(
    name = "com.example.orders.queue.threshold",
    description = "Queue backlog exceeded threshold"
)
public class PaymentQueueManagement
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher value) {
        this.publisher = value;
    }

    public void onThresholdCrossed(int pendingCount) {
        NotificationPublisher current = publisher;
        if (current == null) {
            throw new IllegalStateException("JMX publisher unavailable");
        }

        Notification event = new Notification(
            "com.example.orders.queue.threshold",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Queue backlog above threshold"
        );
        event.setUserData(pendingCount);
        current.sendNotification(event);
    }
}
~~~

The ManagedNotification annotation only publishes metadata about the event type; it does not emit events automatically. The bean must be managed by an appropriate exporter, and the application must call sendNotification.

The example assumes the business layer only calls onThresholdCrossed on a threshold-crossing transition. If called every time queue depth increases, a notification storm can occur. Hysteresis or policy-based throttling is needed.

## 5. Standardizing the Event Schema

A stable schema decouples downstream consumers from javax.management.Notification.

~~~java
import java.time.Instant;
import java.util.Map;

public record OperationalEvent(
    String eventType,
    String service,
    String environment,
    String instance,
    String objectName,
    String resource,
    String severity,
    Instant occurredAt,
    String summary,
    Map<String, String> attributes
) {}
~~~

The record snippet requires a Java version supporting records; Java 8/11 projects can use an immutable POJO instead.

Schema rules:

1. Keep eventType names stable with clear semantics.
2. Choose UTC timestamps; distinguish occurredAt from receivedAt if needed.
3. Obtain service/environment/instance from trusted deployment metadata.
4. Store the canonical ObjectName for source traceability.
5. Constrain the size and data types of attributes.
6. Never forward secrets, tokens, or sensitive personal payloads.
7. Apply schema versioning when incompatible changes occur.
8. Do not assume JMX sequenceNumber is a global event ID.

Example event names:

~~~text
worker.failed
worker.recovered
queue.backlog.high
queue.backlog.recovered
cache.refresh.completed
configuration.applied
~~~

## 6. Normalizer Mapping Notifications

~~~java
import java.time.Instant;
import java.util.Map;
import javax.management.Notification;
import javax.management.ObjectName;

public final class QueueEventNormalizer {
    private final String service;
    private final String environment;
    private final String instance;

    public QueueEventNormalizer(
            String service,
            String environment,
            String instance) {
        this.service = service;
        this.environment = environment;
        this.instance = instance;
    }

    public OperationalEvent normalize(
            Notification n, ObjectName source) {

        if (!"com.example.orders.queue.threshold".equals(n.getType())) {
            throw new IllegalArgumentException("Unsupported event type");
        }

        Object payload = n.getUserData();
        String count = payload instanceof Integer
            ? payload.toString() : "unknown";

        return new OperationalEvent(
            "queue.backlog.high",
            service,
            environment,
            instance,
            source.getCanonicalName(),
            source.getKeyProperty("name"),
            "warning",
            Instant.ofEpochMilli(n.getTimeStamp()),
            "Queue backlog above threshold",
            Map.of("pendingCount", count)
        );
    }
}
~~~

The normalizer must check an allowlist of type/source and the userData data type. With remote JMX, userData may fail to deserialize if the client lacks the class or has an incompatible type.

Do not assume notification.getSource() is always an ObjectName. Source can be an object or other information depending on the emitter/transport. You can pass the trusted ObjectName via handback when registering the listener.

## 7. Registering a NotificationListener

~~~java
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName queueName = new ObjectName(
    "com.example.orders:type=Queue,name=payments"
);

NotificationListener listener = (notification, handback) -> {
    ObjectName source = (ObjectName) handback;
    // Normalize and enqueue quickly.
};

connection.addNotificationListener(
    queueName, listener, null, queueName
);
~~~

Here connection is an MBeanServerConnection connected to the target server. Because this code itself passes queueName as the handback, casting to ObjectName is valid for this registration.

When the listener resides in the same Spring context and the MBean is managed by the same exporter, you can use NotificationListenerBean:

~~~java
import org.springframework.jmx.export.NotificationListenerBean;

NotificationListenerBean listenerBean =
    new NotificationListenerBean(listener);

listenerBean.setMappedObjectNames(
    "com.example.orders:type=Queue,name=payments"
);

exporter.setNotificationListeners(listenerBean);
~~~

If the MBean is in another JVM or managed by a different exporter, registering via MBeanServerConnection is usually clearer. Do not create an extra exporter that causes duplicate ObjectName collisions just to attach a listener.

## 8. Bounding the Callback

Callbacks should not perform slow I/O:

~~~java
public void handleNotification(Notification n, Object context) {
    externalIncidentApi.createIncident(n); // Not recommended.
}
~~~

Split it into:

~~~text
JMX callback
   -> validate + normalize
   -> bounded queue
   -> worker
   -> sink
~~~

A listener with a bounded queue:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public final class EventBridgeListener implements NotificationListener {
    private final BlockingQueue<OperationalEvent> queue =
        new ArrayBlockingQueue<>(1000);

    private final QueueEventNormalizer normalizer;

    public EventBridgeListener(QueueEventNormalizer normalizer) {
        this.normalizer = normalizer;
    }

    @Override
    public void handleNotification(
            Notification notification, Object handback) {

        if (!(handback instanceof ObjectName)) {
            return;
        }
        ObjectName source = (ObjectName) handback;

        try {
            OperationalEvent event =
                normalizer.normalize(notification, source);

            boolean accepted = queue.offer(event);
            if (!accepted) {
                // Increment drop counter; apply overload policy.
            }
        } catch (IllegalArgumentException invalid) {
            // Increment invalid/filtered counter.
        }
    }

    public OperationalEvent take() throws InterruptedException {
        return queue.take();
    }
}
~~~

A queue capacity of 1000 is just an example. You must define the full-queue behavior: drop, coalesce, dead-letter, or route through another durable path. Never use an unbounded queue because a slow consumer can cause the JVM to run out of memory.

## 9. Event Sink and Worker

Define a sink interface:

~~~java
public interface OperationalEventSink {
    void publish(OperationalEvent event) throws Exception;
}
~~~

Simple worker:

~~~java
public final class EventBridgeWorker implements Runnable {
    private final EventBridgeListener listener;
    private final OperationalEventSink sink;

    public EventBridgeWorker(
            EventBridgeListener listener,
            OperationalEventSink sink) {
        this.listener = listener;
        this.sink = sink;
    }

    @Override
    public void run() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                OperationalEvent event = listener.take();
                sink.publish(event);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                break;
            } catch (Exception ex) {
                // Record failure, retry or dead-letter by policy.
            }
        }
    }
}
~~~

This is an illustrative skeleton, not a durable pipeline. If publishing fails, an event already removed from the queue may be lost. Achieving at-least-once delivery requires durable storage, retries with acknowledgments, and poison-message handling.

## 10. Delivery Guarantees: Understanding JMX Limitations

JMX notifications are runtime-oriented:

- Clients not yet registered can miss notifications.
- If a remote connection drops, events during the disconnect have no built-in replay mechanism.
- If an MBean is unregistered/replaced, old subscriptions may cease to exist.
- Callbacks or queues can become overloaded.
- Retries from an event sink can produce duplicate records.

Distinguish:

| Requirement | Design |
| --- | --- |
| Best effort | JMX listener + bounded queue + logging |
| Duplicate reduction needed | Event ID/idempotency key + deduplication |
| At-least-once to sink | Durable queue/store + retry and ack |
| Lossless audit needed | Persist business event durably before emitting JMX |
| Replay after outage needed | Broker/event store with retention |
| Only current state needed | Metric/attribute and periodic polling |

End-to-end exactly-once delivery cannot be achieved with a NotificationListener alone. If durability is critical, have the business service write to a transactional outbox and treat JMX strictly as a supplementary observation signal.

## 11. Idempotency and Deduplication

A notification has a sequenceNumber, but sequences belong to the emitter, are not cluster-wide unique, and can reset on JVM restart.

A dedupe key can be built from:

~~~text
targetInstance
+ canonicalObjectName
+ emitterGeneration
+ notificationSequenceNumber
+ notificationType
~~~

Condition: generation is managed stably and the source does not reuse sequence numbers within the same generation. If the producer provides a unique, durable event ID, prefer verifying and using that ID.

Causes of duplicates:

- The same listener registered multiple times.
- Two bridges subscribing to the same target.
- Event publisher retrying after a timeout.
- MBean re-emitting the same state.
- Improper reconnect/re-subscribe handling.

Deduplication should use storage with a TTL or bounded capacity. An unbounded HashSet will cause memory growth.

## 12. Attaching Target Identity

An ObjectName is only unique within a single MBeanServer. Different JVMs can share the exact same ObjectName:

~~~text
checkout-a: com.example.orders:type=Queue,name=payments
checkout-b: com.example.orders:type=Queue,name=payments
~~~

Therefore, operational events must carry additional target identity:

~~~text
service=checkout
environment=production
cluster=payments-east
instance=checkout-a
objectName=com.example.orders:type=Queue,name=payments
~~~

Do not infer environment or instance by parsing free-form notification messages. Use deployment metadata or trusted collector configuration.

## 13. Event Severity and Correlation

Example policy:

| Notification type | Event type | Initial severity |
| --- | --- | --- |
| queue.threshold | queue.backlog.high | warning |
| queue.recovered | queue.backlog.recovered | info |
| worker.failed | worker.failed | critical or warning per service |
| worker.restarted | worker.restarted | info |
| cache.refreshed | cache.refresh.completed | info |
| configuration.applied | config.applied | audit/info |

An event severity does not necessarily trigger an immediate alert. The alerting engine can apply threshold durations, business impact, and recovery history.

Use a correlation key:

~~~text
environment + service + resource + issueType
~~~

to group high and recovery alerts. Without correlation, every notification may create a separate incident that never auto-closes when the service recovers.

## 14. Automation and Preventing Feedback Loops

An operational event can open a runbook or trigger auto-remediation. However, do not react blindly:

~~~text
queue backlog high -> clearQueue()
~~~

That action could wipe unprocessed data. An appropriate workflow can collect diagnostics, open an alert, or propose scaling capacity after verification.

When automation is used, ensure:

1. Explicit preconditions and scope.
2. Authorization and approval when required.
3. Idempotency keys and operation IDs.
4. Cooldowns, rate limits, and bounded retries.
5. Auditing of trigger, action, and outcome.
6. Timeouts, circuit breakers, and rollback capability.
7. Safeguards preventing automation-emitted events from re-triggering itself.

Example feedback loop:

~~~text
worker unhealthy
  -> automation.restartWorker
  -> worker restarting notification
  -> automation.restartWorker again
~~~

Distinguish event types, state transitions, and cooldowns to prevent loops.

## 15. Security When Converting Notifications into Events

Notifications can contain sensitive operational information. You should:

- Never forward raw userData unchecked.
- Allowlist fields and notification types.
- Limit message, attribute, and batch sizes.
- Never store passwords, tokens, customer payloads, or private keys.
- Preserve trusted source identity.
- Protect remote JMX with authentication, TLS, and network ACLs.
- Protect the sink/broker with credentials scoped only to required publish permissions.
- Do not grant dangerous operation-invocation rights to a bridge that only needs to subscribe.

JMX management permissions and event broker permissions are two separate privilege boundaries.

## 16. Lifecycle, Reconnect, and Re-Subscribe

When an MBean is unregistered or replaced, a listener can lose its subscription. Remote JMX connectors can also drop connections. The bridge must manage:

~~~text
CONNECTING -> SUBSCRIBED -> DISCONNECTED
      ^                         |
      +------ RECONNECT --------+
~~~

Workflow:

1. Connect to the right MBeanServer.
2. Confirm the ObjectName is registered.
3. Register the listener and record registration state.
4. Monitor connection notifications.
5. Reconnect with exponential backoff and jitter.
6. Re-query the registry after reconnecting.
7. Re-subscribe idempotently.
8. Clean up listeners and connectors on shutdown.

MBeanServerDelegate can emit notifications when MBeans are registered/unregistered. However, those notifications are not durable; after a reconnect, registry state must still be synchronized.

## 17. Observability for the Bridge Itself

Measure each stage:

~~~text
jmx_notification_received_total
jmx_notification_filtered_total
jmx_notification_invalid_total
jmx_notification_enqueued_total
jmx_notification_dropped_total
operational_event_publish_success_total
operational_event_publish_failure_total
operational_event_queue_depth
operational_event_oldest_age_seconds
jmx_connector_reconnect_total
jmx_subscription_recovered_total
~~~

These are suggested application-implemented metrics, not default Spring metrics.

If received increases while published does not, investigate the queue, worker, and sink. If the source emits while received does not increase, check listener registration, ObjectName, filters, and the connector.

## 18. Common Failure Modes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| No events seen | MBean does not emit or listener not registered | Check producer and ObjectName |
| MBeanInfo lists notification, but no events | Metadata does not emit automatically | Check sendNotification |
| Listener receives, but broker has nothing | Queue full/publish failure | Metrics, retry/dead-letter |
| Events lost after deploy | MBean replaced or context restarted | Re-subscribe |
| Duplicate events | Duplicate registration or publish retries | Dedupe and source generation |
| Too many alerts | Emitting events on every metric change | State transition/throttle |
| Incident never closes | Missing recovery event or wrong correlation | Align event types/correlation key |
| Wrong instance | Using ObjectName alone | Add target identity |
| Callback slows down application | Blocking I/O | Bounded async queue |
| Memory grows continuously | Unbounded queue/map | Capacity limits and TTL |
| Automation loops | Event/action loop | Cooldown and state machine |
| Data leak | Forwarding raw payload | Validate, redact, and enforce size limits |

## 19. Testing

An integration test should include:

1. Create an isolated MBeanServer via MBeanServerFactory.newMBeanServer().
2. Register a TestEmitter that supports notifications.
3. Create a mock/stub listener/normalizer/sink.
4. Register the listener with the appropriate ObjectName and filter.
5. Invoke the MBean operation that emits the notification.
6. Wait for the event using a latch or bounded mechanism.
7. Assert eventType, resource, instance, and payload.
8. Test unknown types, invalid userData, and queue-full behavior.
9. Test MBean replacement and re-subscription.
10. Test connection failures and sink publish failures.
11. Clean up listener/MBean/worker.

Stub test sink:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public final class RecordingEventSink implements OperationalEventSink {
    private final List<OperationalEvent> events =
        new CopyOnWriteArrayList<>();

    @Override
    public void publish(OperationalEvent event) {
        events.add(event);
    }

    public List<OperationalEvent> events() {
        return events;
    }
}
~~~

A test that only verifies `handleNotification` was called is insufficient. Verify that the event is normalized and published according to the expected schema.

## 20. When to Use a Different Event Source?

| Need | Choice |
| --- | --- |
| Best-effort management signals | JMX notification bridge |
| Aggregated metrics needed | Micrometer/Actuator metrics |
| Lossless auditing needed | Durable event log/outbox |
| Replay after outage needed | Message broker with retention |
| Tracking long-running operations | Operation ID + MBean status |
| Approval workflows needed | Incident/runbook platform |
| Multi-language compatibility needed | JMX-independent schema |
| Current state snapshot needed | JMX attribute getter/polling |

Using JMX notifications for their intended purpose reduces load and avoids turning a runtime management channel into a message broker without durable storage.

## 21. Production Checklist

1. Are notification types and schemas clearly defined?
2. Does the producer emit on state transitions instead of every metric change?
3. Are source ObjectNames and target JVMs validated?
4. Is the operational event schema versioned?
5. Are payloads allowlisted and size-bounded?
6. Does the callback avoid blocking network I/O?
7. Does the buffer have a capacity limit and overload policy?
8. Do publish failures have retry/dead-letter handling matching requirements?
9. Is an appropriate event ID/dedupe mechanism in place?
10. Are alert correlation and recovery events configured properly?
11. Does auto-remediation have guardrails/cooldown/auditing?
12. Are both remote JMX and the sink secured?
13. Does the bridge support reconnect/re-subscribe?
14. Are metrics recorded for each stage?
15. Are integration, overload, and failure tests in place?
16. Is the distinction between best-effort and durable delivery documented?

## 22. Self-Check Questions

**1. Is a JMX notification a complete operational event?** No. Type, source, severity, service, instance, and payload must be normalized.

**2. Should an incident be created for every notification?** No. Alert policies and correlation are required.

**3. Why should a callback not call external APIs directly?** Because network I/O can block and slow down the emitter.

**4. Is sequence number a global event ID?** No. It can repeat across emitters and after restarts.

**5. Do JMX notifications replay after a disconnect?** Not by default. If needed, use a durable event source.

**6. When is a transactional outbox needed?** When critical events must not be lost and require retry/replay capability.

**7. Why is target instance needed?** ObjectName is only unique within a single MBeanServer, not across an entire cluster.

**8. What does safe automation require?** Preconditions, authorization, idempotency, cooldowns, bounded retries, and auditing.

## 23. Summary

Converting JMX notifications into operational events bridges JVM management with observability and automation.

A sound design needs a clear normalizer schema, trusted source identity, lightweight callbacks, bounded queues, drop/retry handling, alert correlation, security, deduplication, and reconnects. For events that require guaranteed durability, a business event store or outbox must be the primary source of truth; JMX notifications should only be a supplementary signal.

**Pushing notifications as operational events does not mean dumping raw JMX data onto a broker. What matters is a meaningful, controlled event contract aligned with your delivery requirements.**

### References

- Spring Framework Reference — JMX notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring API — NotificationPublisher: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisher.html
- Spring API — NotificationListenerBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/NotificationListenerBean.html
- Java SE API — Notification: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
