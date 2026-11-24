# Wildcard Listener for Exporter-Managed MBeans

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Notifications in Spring  
> **Lesson:** Wildcard listener for exporter-managed MBeans

## 1. Objectives

After this lesson, you will be able to:

- Explain the role of a JMX \`NotificationListener\` when MBeans are exported with Spring.
- Understand the meaning of a **wildcard listener** in \`MBeanExporter\`: a single listener can be registered for **notification-emitting MBeans managed by the exporter**, instead of listing every ObjectName individually.
- Distinguish a Spring exporter wildcard from a JMX **ObjectName query pattern**.
- Configure \`NotificationListenerBean\` and \`MBeanExporter.setNotificationListeners(...)\` intentionally.
- Distinguish between **registering a listener with an MBean** and **filtering notification types**.
- Grasp the limitations regarding external MBeans, dynamically registered listeners, replaced MBeans, and the exporter lifecycle.
- Design listeners that do not slow down processing threads, avoid leaking sensitive data, and have clear verification mechanisms.

## 2. The JMX Notification Model

In JMX, an MBean can emit a \`javax.management.Notification\` when an observable event occurs, such as a task completing, a queue exceeding a threshold, or a state change.

\`\`\`text
Spring bean / MBean
        |
        | sendNotification(...)
        v
JMX notification broadcaster
        |
        | registered listener
        v
NotificationListener.handleNotification(...)
        |
        v
Log / metric / alert / management handling
\`\`\`

Components:

| Component | Role |
|---|---|
| \`Notification\` | Event object containing type, source, sequence, timestamp, message, userData |
| \`NotificationBroadcaster\` | Contract allowing registering/removing listeners and providing notification metadata |
| \`NotificationEmitter\` | Extends broadcaster to support removing a specific registration |
| \`NotificationListener\` | Callback receiving notifications |
| \`NotificationFilter\` | Decides whether an event is forwarded to a listener registration |
| \`NotificationFilterSupport\` | Filter supporting prefix matching on notification types |
| \`NotificationListenerBean\` | Spring configuration wrapping a listener, filter, and target MBeans |
| \`MBeanExporter\` | Registers MBeans and can register listeners for MBeans within its management scope |

Not every Spring bean or MBean emits notifications. Even a successfully configured listener still needs a broadcaster capable of emitting and an event actually occurring.

## 3. What Does Wildcard Listener Mean in Spring?

In Spring's \`NotificationListenerBean\` configuration, target MBeans can be specified by ObjectName. When **no set of mapped ObjectNames is specified**, the Spring exporter can treat this listener as a **wildcard listener** applying to eligible MBeans **managed by that exporter**.

Concept:

\`\`\`text
                     Spring MBeanExporter
                      /       |        \
                     v        v         v
                 MBean A   MBean B    MBean C
                   |         |          |
                   +---------+----------+
                             |
                      wildcard listener
                             |
                             v
                     handleNotification
\`\`\`

Important points:

- This wildcard is a **listener mapping rule of the Spring exporter**, not the \`ObjectName("*:*")\` syntax.
- It does not automatically listen to every MBean in the entire JVM.
- It does not necessarily listen to MBeans registered by other libraries or another application context.
- It does not cause non-notification-emitting MBeans to suddenly emit notifications.
- It is not a durable subscription, storage, or event replay mechanism.

Under standard Spring behavior, a \`NotificationListenerBean\` without \`mappedObjectNames\` is treated as a broadly mapped listener within the scope of MBeans managed by the exporter. When you need a specific set of MBeans, configure an explicit list of ObjectNames.

## 4. Wildcard Mapping vs. ObjectName Pattern

JMX supports pattern-style \`ObjectName\`s:

\`\`\`text
app.management:type=Worker,*
app.management:*
*:type=Queue,*
\`\`\`

These patterns are used with query APIs:

\`\`\`java
Set<ObjectName> names = server.queryNames(
    new ObjectName("app.management:type=Worker,*"),
    null
);
\`\`\`

In contrast, a Spring exporter wildcard listener is a way of **not restricting the listener to a specific list of ObjectNames** in the \`NotificationListenerBean\` configuration.

Two different meanings:

| Mechanism | Purpose | Scope |
|---|---|---|
| ObjectName pattern | Query or select MBean names by pattern | Matching names in the queried server |
| Spring wildcard listener | Register listener on MBeans managed by the exporter | Eligible MBeans within the exporter's scope |
| NotificationFilter | Select which notifications are forwarded to the listener | Events after the listener is attached |
| NotificationFilterSupport | Filter by prefix of \`Notification.getType()\` | Event type, not ObjectName |

Do not use wildcard mapping as a substitute for security controls, ownership, or event type restrictions.

## 5. Example of an MBean Emitting Notifications

### 5.1. Spring Bean with NotificationPublisherAware

Spring supports \`NotificationPublisherAware\` so the exporter supplies a \`NotificationPublisher\` to a bean that needs to emit notices.

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "app.management:type=JobMonitor,name=main"
)
public class JobMonitor
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();

    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher
    ) {
        this.publisher = publisher;
    }

    @ManagedOperation(description = "Complete a sample job")
    public void completeJob(String jobId) {
        Notification event = new Notification(
            "app.job.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Job completed: " + jobId
        );

        event.setUserData(jobId);
        publisher.sendNotification(event);
    }
}
\`\`\`

This example assumes the bean has been created by Spring and the exporter has completed exporting before calling \`completeJob\`. If called too early, the publisher may not have been injected into the bean yet. In production code, validate inputs and avoid placing secrets or personal data in \`message\`/\`userData\`.

### 5.2. Notification Metadata

So management tools know which event types to expect, Spring provides metadata annotations:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "app.management:type=JobMonitor,name=main"
)
@ManagedNotifications({
    @ManagedNotification(
        name = "app.job.completed",
        description = "Job completion event",
        notificationTypes = { "app.job.completed" }
    )
})
public class JobMonitor {
    // Combine implementation details
    // and NotificationPublisherAware from the example above.
}
\`\`\`

This code block illustrates metadata to be added on **the same class that is actually exported**; do not create a second class with the same ObjectName. Metadata annotations do not emit events on their own. The bean must call \`publisher.sendNotification(...)\`.

## 6. Writing a NotificationListener

\`\`\`java
package example.jmx;

import javax.management.Notification;
import javax.management.NotificationListener;

public class JobEventListener implements NotificationListener {

    @Override
    public void handleNotification(
            Notification notification,
            Object handback
    ) {
        System.out.printf(
            "type=%s source=%s seq=%d%n",
            notification.getType(),
            notification.getSource(),
            notification.getSequenceNumber()
        );
        System.out.println(
            "message=" + notification.getMessage()
        );
    }
}
\`\`\`

\`handback\` is the context object supplied by the listener registrar, not \`Notification.userData\`.

\`\`\`text
Notification.userData
  -> payload emitted by the broadcaster

handback
  -> context of the listener registration
\`\`\`

One listener can be registered with multiple MBeans; in that case, read \`notification.getSource()\` and \`notification.getType()\` to distinguish events. However, source should not be cast to a Spring bean implementation class because clients/adapters may represent the source as an ObjectName or another object.

## 7. Configuring a Wildcard with NotificationListenerBean

Core configuration:

\`\`\`java
import org.springframework.jmx.export.notification.NotificationListenerBean;

NotificationListenerBean listenerBean =
    new NotificationListenerBean();

listenerBean.setNotificationListener(
    new JobEventListener()
);

// Do not call setMappedObjectNames(...):
// the listener is configured with wildcard mapping
// within the scope managed by the exporter.
\`\`\`

Then pass the listener to the exporter:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();

exporter.setNotificationListeners(listenerBean);
\`\`\`

These are illustrative configuration snippets. The exporter must still be given an \`MBeanServer\`, appropriate bean mappings or autodetection, and go through the Spring lifecycle before the listener is actually registered.

Spring also supports declaring the listener as a separate bean so dependency injection, logging, and cleanup are managed by the container.

## 8. Complete Java Configuration Example with an Explicit Exporter

Example using an application-controlled \`MBeanExporter\`:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.notification.NotificationListenerBean;

@Configuration
public class JmxNotificationConfig {

    @Bean
    public MBeanServer managementServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public JobEventListener jobEventListener() {
        return new JobEventListener();
    }

    @Bean
    public MBeanExporter managementExporter(
            MBeanServer managementServer,
            JobMonitor jobMonitor,
            JobEventListener jobEventListener
    ) {
        NotificationListenerBean listener =
            new NotificationListenerBean();
        listener.setNotificationListener(jobEventListener);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(managementServer);
        exporter.setBeans(Map.of(
            "app.management:type=JobMonitor,name=main",
            jobMonitor
        ));
        exporter.setNotificationListeners(listener);

        return exporter;
    }
}
\`\`\`

Within the same exporter, you can add other MBeans capable of emitting notifications. When the wildcard listener is applied, the listener can receive notifications from the broadcasters that the exporter registers and manages.

**Configuration warning:** If the application simultaneously enables \`@EnableMBeanExport\` or auto-configuration creates another exporter for the same bean, duplicate registrations may occur. This example uses an explicit exporter to clearly show listener mapping; in a real application, choose a single unified export mechanism.

## 9. Which Events Does the Listener Receive?

Suppose the exporter manages three MBeans:

\`\`\`text
app.management:type=JobMonitor,name=main
app.management:type=QueueMonitor,name=orders
app.management:type=CacheMonitor,name=primary
\`\`\`

Where:

- JobMonitor emits \`app.job.completed\`.
- QueueMonitor emits \`app.queue.threshold\`.
- CacheMonitor has only attributes and emits no notifications.

The wildcard listener can receive events from JobMonitor and QueueMonitor when those MBeans support broadcasting and the listener is attached successfully.

CacheMonitor does not automatically generate notifications merely because a wildcard listener exists.

If another MBean:

\`\`\`text
third.party:type=LibraryMonitor
\`\`\`

is registered directly into the same MBeanServer by another component, the exporter's wildcard mapping does not cover it by default.

Therefore, "wildcard" describes the scope of MBeans **actively managed by the exporter**, not unlimited access to the entire JMX registry.

## 10. Filtering Event Types with NotificationFilter

Not every event belonging to the exporter needs to be delivered to the same consumer. You can add a filter to restrict notification types.

\`\`\`java
import javax.management.NotificationFilter;

NotificationFilter completedOnly =
    event -> "app.job.completed".equals(event.getType());

NotificationListenerBean listener =
    new NotificationListenerBean();

listener.setNotificationListener(
    new JobEventListener()
);
listener.setNotificationFilter(completedOnly);
\`\`\`

This filter decides which callbacks are received, but **does not change the target MBeans**. If the listener is still a wildcard, it is attached to the broadcasters within the exporter's scope and then filters the corresponding event types.

### NotificationFilterSupport

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter =
    new NotificationFilterSupport();

filter.enableType("app.job.");
\`\`\`

\`NotificationFilterSupport\` typically performs prefix matching: configuring \`app.job.\` allows types such as \`app.job.completed\` and \`app.job.failed\`. If you want **one exact type**, use \`equals\` or a custom filter.

## 11. Specifying Concrete MBeans When You Do Not Want a Wildcard

A listener should listen only to selected broadcasters if business requirements call for a narrow scope.

Example using \`NotificationListenerBean.setMappedObjectNames\`:

\`\`\`java
NotificationListenerBean listener =
    new NotificationListenerBean();

listener.setNotificationListener(
    new JobEventListener()
);

listener.setMappedObjectNames(
    "app.management:type=JobMonitor,name=main",
    "app.management:type=JobMonitor,name=batch"
);
\`\`\`

Once ObjectNames are specified, the exporter maps the listener according to the configured target list instead of wildcarding across all MBeans it manages.

You must use the actual ObjectName registered by the exporter. If a bean is renamed, the naming strategy changes, or multiple instances have different key properties, the listener may not be attached where expected.

If the MBean set is large but only one event type is relevant, you can combine **mapped names** and a **notification filter** to reduce scope and avoid unnecessary processing.

## 12. One Listener for Multiple MBeans: Identifying the Source

When a wildcard listener receives multiple event types, the callback code should classify them clearly:

\`\`\`java
@Override
public void handleNotification(
        Notification notification,
        Object handback
) {
    String type = notification.getType();

    switch (type) {
        case "app.job.completed":
            onJobCompleted(notification);
            break;
        case "app.queue.threshold":
            onQueueThreshold(notification);
            break;
        default:
            // Ignore or record according to policy.
    }
}
\`\`\`

The methods \`onJobCompleted\` and \`onQueueThreshold\` are illustrative application helpers.

Combine \`type\`, \`source\`, and a correlation ID if tracing is needed. \`sequenceNumber\` is usually a per-broadcaster counter, not a global order across all MBeans.

Be careful with logging \`userData\`: it may contain domain objects, customer information, or tokens if the producer is poorly designed.

## 13. Listener and Exporter Lifecycle

The Spring exporter is responsible for registering MBeans and listeners configured with that exporter according to the appropriate lifecycle.

\`\`\`text
ApplicationContext startup
          |
          v
MBeanExporter initialization
          |
          +--> Register MBean A
          +--> Register MBean B
          |
          +--> Register listener with eligible MBeans
          |
          v
MBeanServer active
          |
          v
ApplicationContext shutdown
          |
          +--> Cleanup listener registrations
          +--> Unregister MBeans within management scope
\`\`\`

The exact internal ordering depends on the Spring version and exporter implementation. Do not rely on the diagram as a guarantee that all listeners are attached before every startup event.

If a bean emits a notification in its constructor or too early in \`@PostConstruct\`, the listener may not be registered yet and the event will be lost. For mandatory startup events, design an explicit lifecycle or a separate durable event mechanism.

## 14. MBeans Registered Dynamically After Startup

An important question: if the exporter manages a new MBean created after the wildcard listener was configured, does the listener attach automatically?

Behavior depends on the dynamic registration mechanism and the exporter API in use. Spring can manage listener registrations for MBeans it registers itself, but do not assume a wildcard listener will automatically track every MBean added by **external code** or every dynamic registration case.

In a system with dynamic MBeans:

1. Identify how the MBean is created and registered.
2. Determine whether the exporter manages that registration.
3. Verify whether the listener is attached after the MBean appears.
4. Test by emitting a notification with a known type and timestamp.
5. Consider managing subscriptions yourself on registry changes if high coverage is required.

If the listener must track externally registered MBeans, you can use the JMX API directly with \`MBeanServerConnection.addNotificationListener\`, combined with watching the registry via \`MBeanServerDelegate\`.

## 15. Watching Registry Changes with MBeanServerDelegate

JMX has a delegate MBean that emits notifications related to MBean registration/unregistration.

\`\`\`java
import javax.management.MBeanServerDelegate;
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;

NotificationListener registryListener =
    (notification, handback) -> {
        if (notification instanceof MBeanServerNotification event) {
            System.out.println(
                event.getType() + " " + event.getMBeanName()
            );
        }
    };

server.addNotificationListener(
    MBeanServerDelegate.DELEGATE_NAME,
    registryListener,
    null,
    null
);
\`\`\`

Clients can observe \`JMX.mbean.registered\` and \`JMX.mbean.unregistered\` to decide whether to attach a listener to a new MBean.

If adding this mechanism, you must handle races between querying the registry, registering listeners, and MBeans changing. Do not forget \`removeNotificationListener\` on the delegate when stopping.

## 16. Unregister/Re-register and RegistrationPolicy

Suppose the exporter replaces an MBean under the same ObjectName using \`RegistrationPolicy.REPLACE_EXISTING\`:

\`\`\`text
ObjectName X
   -> Old broadcaster
   -> unregister
   -> New broadcaster
   -> register
\`\`\`

A listener attached to the old broadcaster does not automatically transfer to the new broadcaster just because the ObjectName remains the same.

With dynamic replacement, verify whether the exporter re-attaches listeners per its lifecycle. In situations where the client manages subscriptions manually, re-register at the right time.

Do not treat \`REPLACE_EXISTING\` as a mechanism for transferring all notification state or listener registrations.

## 17. Avoiding Heavy Work in handleNotification

\`NotificationListener.handleNotification\` is a callback invoked by the notification delivery system. Depending on the broadcaster/connector and configuration, dispatch may be synchronous or asynchronous.

Avoid:

\`\`\`java
@Override
public void handleNotification(
        Notification notification,
        Object handback
) {
    callRemoteServiceWithNoTimeout();
    performHeavyDatabaseAggregation();
}
\`\`\`

Replace with fast handling:

\`\`\`java
@Override
public void handleNotification(
        Notification notification,
        Object handback
) {
    if (!"app.job.completed".equals(notification.getType())) {
        return;
    }

    eventExecutor.execute(
        () -> processEvent(notification)
    );
}
\`\`\`

\`eventExecutor\` and \`processEvent\` are application-provided components. When submitting to an executor, define queue capacity, rejection policy, shutdown, and exception handling. Avoid unbounded queues or silently swallowing errors.

A wildcard listener can receive a large volume of events; if every event triggers heavy processing, the performance impact can spread across all MBean broadcasters managed by the exporter.

## 18. Testing a Wildcard Listener with Repeatable Scenarios

A good test scenario:

1. Create two broadcaster MBeans in the same exporter.
2. Configure \`NotificationListenerBean\` without mapped ObjectNames.
3. Enable a filter receiving type \`app.job.\` if you want only one event group.
4. Complete Spring context initialization.
5. Invoke the notification-emitting operation on MBean A.
6. Invoke the notification-emitting operation on MBean B.
7. Observe callbacks and record source/type.
8. Try an MBean C outside the exporter, if permitted and in an isolated test environment.
9. Confirm the listener does not automatically receive notifications from C if it was not registered for C.
10. Close the context and verify cleanup according to the designed lifecycle.

Results must be verified by actual callbacks, not merely by the Spring listener bean existing in the ApplicationContext.

## 19. Testing with MBeanServerConnection

An independent test harness can register a listener directly with an MBean:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "app.management:type=JobMonitor,name=main"
);

NotificationListener listener =
    (notification, handback) -> {
        System.out.println(notification.getType());
    };

connection.addNotificationListener(
    name,
    listener,
    null,
    null
);

try {
    connection.invoke(
        name,
        "completeJob",
        new Object[] { "job-001" },
        new String[] { "java.lang.String" }
    );
} finally {
    connection.removeNotificationListener(
        name,
        listener
    );
}
\`\`\`

\`connection\` must point to the exact MBeanServer the exporter used. For remote connections, you may need to wait for the notification using a \`CountDownLatch\` with a timeout before removing the listener, avoiding missing callbacks in transit.

This verifies whether the producer emits events, but **does not replace** testing Spring wildcard mapping. To verify wildcard behavior, you must observe the listener configured in the exporter itself receiving events from different broadcasters.

## 20. When to Choose Wildcard vs. Explicit Mapping?

| Context | Recommended Choice | Reason |
|---|---|---|
| One exporter dedicated to managing a group of MBeans with the same purpose and event convention | Wildcard listener + filter | Concise configuration, easy coverage of the exporter's broadcasters |
| Many unrelated MBeans and high event volume | Mapped ObjectNames | Limits callbacks and processing overhead |
| MBeans from multiple applications/libraries sharing one server | Explicit mapping or direct JMX API | Exporter wildcard does not cover the entire registry |
| Listener needs to audit specific events | Narrow mapping + exact filter | Easy to verify ownership and data policy |
| MBeans registered dynamically via multiple mechanisms | Active registry and subscription tracking | Reduces assumptions about exporter scope |
| Only aggregated health/metrics needed | Notification listener may not be needed | Metrics polling/Actuator may fit better |

Wildcard is a convenient tool **within the exporter's management scope**. It should not replace designing the event contract and restricting sensitive information.

## 21. Risks When a Wildcard Listener Receives Too Many Events

- **Information noise:** multiple broadcasters emit unrelated types.
- **Performance:** callbacks can consume resources on dispatch threads.
- **Duplicate processing:** listener registered multiple times or multiple exporters handling the same MBean.
- **Data security:** logging uncontrolled \`userData\` from MBeans.
- **Hard to audit:** unclear which MBean emitted an event without proper source logging.
- **Lifecycle:** listener can miss events during startup/restart or MBean replacement.
- **Scalability:** number of MBeans/notifications grows with deployment size.

Use filters, structured logging, bounded processing, and integration tests with multiple MBeans. Do not assume the number of received events equals the number of business events under all circumstances; notifications do not have durable delivery by default.

## 22. Distinguishing NotificationListenerBean from NotificationPublisherAware

Two APIs with opposite roles:

\`\`\`text
NotificationPublisherAware
    -> Bean that emits notifications

NotificationListenerBean
    -> Configuration for the receiving side
\`\`\`

\`NotificationPublisherAware\` lets Spring inject a \`NotificationPublisher\` into an exported bean. The bean constructs a \`Notification\` and calls \`sendNotification\`.

\`NotificationListenerBean\` describes a listener, optional filter, and list of target MBeans. The exporter uses this configuration to register the corresponding listener.

A single class acting as both publisher and listener is not forbidden, but responsibilities should be separated to avoid event loops or hard-to-control processing.

## 23. Self-Check Questions

1. Does a Spring exporter wildcard listener mean listening to all MBeans in the JVM?
2. Why can a \`NotificationListenerBean\` without specified mapped ObjectNames become a wildcard listener?
3. Does NotificationFilter select MBeans or notification types?
4. Does \`NotificationFilterSupport.enableType("app.job.")\` perform prefix matching?
5. Must an MBean support broadcaster for a listener to receive notifications?
6. Why shouldn't heavy network I/O be performed directly inside a callback?
7. Does a listener automatically receive events that occurred before it was registered?
8. Is an MBean registered by another library automatically covered by an exporter's wildcard scope?
9. When an MBean is unregistered/re-registered under the same name, is the old listener guaranteed to keep receiving events?
10. To verify that wildcard behavior works, why must you test the Spring listener itself rather than only an independent JMX listener?

## 24. Key Takeaways

\`\`\`text
MBeanExporter
   |
   +-- manages MBean A (broadcaster)
   +-- manages MBean B (broadcaster)
   +-- manages MBean C (does not emit events)
   |
   +-- NotificationListenerBean
          |
          +-- mappedObjectNames unspecified
          |       -> wildcard within exporter scope
          |
          +-- NotificationFilter (if any)
                  -> filters event types
\`\`\`

**Conclusion:** A wildcard listener in Spring JMX is a way to configure a \`NotificationListenerBean\` to listen to broadcasters within the scope managed by \`MBeanExporter\`, instead of listing every ObjectName. It is **not** a JVM-wide subscription, does **not** replace filters, and does **not** guarantee receiving events before registration or after an MBean is replaced. Verify exporter scope, metadata, subscription lifecycle, and callback execution flow properly.