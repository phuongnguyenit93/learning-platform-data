# NotificationBroadcaster and NotificationEmitter in Spring Framework JMX

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Notification  
> **Lesson:** NotificationBroadcaster and NotificationEmitter

## 1. Objectives

After this lesson, you will be able to:

- Distinguish **JMX notifications** from attributes, operations, Spring application events, and message brokers.
- Understand the \`NotificationBroadcaster\`, \`NotificationEmitter\`, \`NotificationListener\`, and \`NotificationFilter\` contracts, as well as the role of \`NotificationBroadcasterSupport\`.
- Know how to write an MBean that emits notifications, exposes notification metadata, and manages listeners.
- Register, filter, receive, and unregister listeners via \`MBeanServer\`/\`MBeanServerConnection\`.
- Understand the notification flow from a Spring bean exported via JMX to management tools, along with lifecycle, concurrency, and remote connection limitations.

## 2. Mental Model: A JMX Notification Is a Signal Emitted by an MBean

In JMX, an MBean can expose state via **attributes**, allow clients to trigger actions via **operations**, and proactively emit **notifications** when a management event occurs. For example, a pool crosses a load threshold, a job finishes, a cache is refreshed, or a management property changes.

\`\`\`text
                   APPLICATION / JVM
  +------------------------------------------------+
  | Spring bean / MBean                            |
  |   - manages state                              |
  |   - executes operations                        |
  |   - emits Notification when an event occurs    |
  |                       |                        |
  |                NotificationBroadcaster         |
  |                       |                        |
  |                  MBeanServer                   |
  +-----------------------|------------------------+
                          |
             listeners registered via JMX
                          |
             +------------+--------------+
             |                           |
      Local JMX client           Remote JMX connector
             |                           |
             v                           v
      NotificationListener        NotificationListener
             |                           |
      log / alert / UI           admin / monitoring
\`\`\`

Notification is **not synonymous** with persisting data into a durable queue. It is an event notification mechanism for currently registered listeners. If a client has not registered yet, gets disconnected, or cannot keep up, the application should not assume replay history exists. When durable auditing is needed, an appropriate logging system, event store, or message broker must be used alongside it.

In Spring Framework JMX, beans can be published via \`MBeanExporter\` or \`@EnableMBeanExport\`. An exported MBean still follows the JMX contract: listeners interact via \`MBeanServer\`, rather than calling \`ApplicationContext\` directly to listen for notifications.

## 3. Related Interfaces and Classes

| API | Role | Notable Methods |
|---|---|---|
| \`NotificationBroadcaster\` | Contract for an object that can register/remove listeners and advertise notification types. | \`addNotificationListener\`, \`removeNotificationListener\`, \`getNotificationInfo\` |
| \`NotificationEmitter\` | Extends broadcaster, supporting removal of **a specific registration** by listener/filter/handback. | \`removeNotificationListener(listener, filter, handback)\` |
| \`NotificationBroadcasterSupport\` | Helper class for implementing broadcaster/emitter, holding the listener list and providing \`sendNotification\`. | \`sendNotification\`, \`getNotificationInfo\` |
| \`NotificationListener\` | Callback that receives notifications. | \`handleNotification(Notification, Object)\` |
| \`NotificationFilter\` | Decides whether each notification is forwarded to a listener. | \`isNotificationEnabled(Notification)\` |
| \`NotificationFilterSupport\` | Convenient filter based on notification type prefixes. | \`enableType\`, \`disableType\`, \`disableAllTypes\` |
| \`Notification\` | JMX event data: type, source, sequence, timestamp, message, userData. | \`getType\`, \`getSource\`, \`getSequenceNumber\` |
| \`MBeanNotificationInfo\` | Metadata describing the notification types an MBean can emit. | \`getNotifTypes\`, \`getDescription\` |

**Key distinction:** \`NotificationBroadcaster\` only has \`removeNotificationListener(NotificationListener)\` in its basic contract. \`NotificationEmitter\` adds an overload taking both \`NotificationFilter\` and \`handback\`, allowing an exact registration to be removed.

Inheritance relationships:

\`\`\`text
NotificationBroadcaster
        |
        v
NotificationEmitter
        ^
        |
NotificationBroadcasterSupport

NotificationListener  <-- independent callback
NotificationFilter    <-- forwarding condition
\`\`\`

On the MBeanServer side, clients also have \`addNotificationListener\` and \`removeNotificationListener\` overloads that accept the emitting MBean's \`ObjectName\`, unlike calling directly on the broadcaster object.

## 4. What Does NotificationBroadcaster Specify?

The JMX interface:

\`\`\`java
public interface NotificationBroadcaster {

    void addNotificationListener(
        NotificationListener listener,
        NotificationFilter filter,
        Object handback
    );

    void removeNotificationListener(
        NotificationListener listener
    ) throws ListenerNotFoundException;

    MBeanNotificationInfo[] getNotificationInfo();
}
\`\`\`

The three responsibilities are:

1. **Add listener**: retains a subscription consisting of callback, optional \`null\` filter, and optional \`null\` handback.
2. **Remove listener**: removes registrations associated with the listener according to the broadcaster's contract.
3. **Describe notifications**: provides metadata about the types that may be emitted.

The basic interface does not itself provide a public \`sendNotification\` API. An implementing object must organize notification emission itself. With \`NotificationBroadcasterSupport\`, most of this infrastructure is already implemented and we call \`sendNotification(notification)\` when an event occurs.

### Why have \`getNotificationInfo()\`?

A tool like JConsole or a client uses \`MBeanServer.getMBeanInfo(name)\` to read metadata. \`MBeanNotificationInfo\` indicates expected notification types, such as:

\`\`\`text
Type: app.job.completed
Java class: javax.management.Notification
Description: A job has completed
\`\`\`

Metadata helps clients discover observability capabilities. However, metadata itself does not emit events. The implementation must still invoke the corresponding emission mechanism. If an MBean declares notifications but never emits them, listeners will receive nothing.

## 5. What Does NotificationEmitter Add?

\`NotificationEmitter\` extends \`NotificationBroadcaster\` and adds:

\`\`\`java
void removeNotificationListener(
    NotificationListener listener,
    NotificationFilter filter,
    Object handback
) throws ListenerNotFoundException;
\`\`\`

Suppose the same listener is registered twice:

\`\`\`java
broadcaster.addNotificationListener(
    listener, filterA, "A"
);
broadcaster.addNotificationListener(
    listener, filterB, "B"
);
\`\`\`

With \`NotificationBroadcaster.removeNotificationListener(listener)\`, many implementations remove **all** registrations attached to this listener. With \`NotificationEmitter.removeNotificationListener(listener, filterA, "A")\`, we can target registration A specifically while keeping registration B.

Exact behavior follows the JMX contract on registration and matching listener/filter/handback. Therefore, keep the exact filter and handback references used during registration, avoiding creating a new filter with the same configuration that is not the one used for registration.

## 6. NotificationBroadcasterSupport Simplifies Implementation

The class \`javax.management.NotificationBroadcasterSupport\` provides out of the box:

- Managing the list of listeners.
- Applying filters before sending a notification to each listener.
- Passing the registered handback to the callback.
- \`sendNotification(Notification)\` to emit events.
- Constructors allowing you to supply an executor and notification metadata.

You can extend this class and just write the notification-emitting logic:

\`\`\`java
public class JobMonitor extends NotificationBroadcasterSupport
        implements JobMonitorMBean {
    // Business state + call sendNotification(...) when an event occurs.
}
\`\`\`

Note that \`NotificationBroadcasterSupport\` can dispatch callbacks using an executor depending on the constructor. With the default configuration, it typically performs synchronous delivery on the emitting thread; if an asynchronous executor is supplied, callback timing changes. For clients connected remotely via a JMX connector, callback behavior also depends on the transport layer. Do not design business logic assuming listeners always run on the same thread or necessarily receive the event before the operation call returns.

## 7. Complete Example: MBean Emitting Notifications on Job Completion

A standalone example using standard JMX, runnable in a JVM without Spring or a remote connector. Afterward we will bring this MBean into Spring.

### 7.1. Define the Standard MBean interface

\`\`\`java
package example.jmx;

public interface JobMonitorMBean {
    long getCompletedJobs();

    String completeJob(String jobId);
}
\`\`\`

By Standard MBean conventions, a class implementing \`JobMonitorMBean\` can expose the \`CompletedJobs\` attribute and the \`completeJob(String)\` operation.

### 7.2. Write the broadcaster

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class JobMonitor extends NotificationBroadcasterSupport
        implements JobMonitorMBean {

    public static final String JOB_COMPLETED =
        "app.job.completed";

    private final AtomicLong completedJobs =
        new AtomicLong();

    private final AtomicLong notificationSequence =
        new AtomicLong();

    @Override
    public long getCompletedJobs() {
        return completedJobs.get();
    }

    @Override
    public String completeJob(String jobId) {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException(
                "jobId must not be blank"
            );
        }

        completedJobs.incrementAndGet();

        Notification event = new Notification(
            JOB_COMPLETED,
            this,
            notificationSequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Completed job: " + jobId
        );
        event.setUserData(jobId);
        sendNotification(event);

        return "completed:" + jobId;
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { JOB_COMPLETED },
                Notification.class.getName(),
                "Notification emitted when a job completes"
            )
        };
    }
}
\`\`\`

In this example:

- \`completedJobs\` stores the count of successful calls in the illustrative logic.
- \`notificationSequence\` supplies an incrementing sequence number for events emitted by this instance.
- \`type\` is \`app.job.completed\`, convenient for filtering.
- \`source\` is passed as \`this\` in the local implementation; when accessed via MBeanServer/remote client, the source may be represented or transformed by the JMX mechanism, so clients should rely on the registered ObjectName and appropriate metadata rather than casting \`source\` to the implementation class.
- \`userData\` holds the job ID. For remote clients to read \`userData\`, the data must be in a format suitable for transmission over a JMX connector. \`String\` is a simple choice.

The \`completeJob\` method is only an example of emitting an event. In real applications, job processing may finish on a different thread; emit the notification when the event **actually completes**, rather than always emitting immediately upon receiving the request.

### 7.3. Register with MBeanServer and attach a listener

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class JobMonitorDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "learning.jmx:type=JobMonitor,name=main"
        );

        server.registerMBean(new JobMonitor(), name);

        NotificationListener listener =
            (notification, handback) -> {
                System.out.println(
                    "type=" + notification.getType()
                        + ", seq="
                        + notification.getSequenceNumber()
                        + ", message="
                        + notification.getMessage()
                        + ", handback=" + handback
                );
            };

        NotificationFilterSupport filter =
            new NotificationFilterSupport();

        filter.enableType(JobMonitor.JOB_COMPLETED);

        server.addNotificationListener(
            name,
            listener,
            filter,
            "job-monitor-context"
        );

        try {
            Object result = server.invoke(
                name,
                "completeJob",
                new Object[] { "job-42" },
                new String[] { "java.lang.String" }
            );
            System.out.println("Result: " + result);
        } finally {
            server.removeNotificationListener(
                name,
                listener,
                filter,
                "job-monitor-context"
            );
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Example output when using synchronous dispatch:

\`\`\`text
type=app.job.completed, seq=1, message=Completed job: job-42, handback=job-monitor-context
Result: completed:job-42
\`\`\`

Log order is not a general guarantee when changing executors or using remote JMX. In this example, the listener is registered **via MBeanServer** with an ObjectName, without needing to know where the server-side \`JobMonitor\` object resides.

## 8. Detailed Flow from Operation to Listener

\`\`\`text
Client
  |
  | invoke("completeJob", ["job-42"], ["java.lang.String"])
  v
MBeanServer
  |
  v
JobMonitor.completeJob("job-42")
  |
  +--> completedJobs++
  |
  +--> new Notification(
  |       type="app.job.completed",
  |       sequence=1,
  |       source=this,
  |       message="Completed job: job-42"
  |     )
  |
  v
NotificationBroadcasterSupport.sendNotification(event)
  |
  +--> check each registration
  |       |
  |       +--> filter allows?
  |                |
  |          +-----+-----+
  |          |           |
  |         YES          NO
  |          |           |
  |          v           v
  |  handleNotification  skip
  |   (event, handback)
  v
Client observes notification
\`\`\`

One listener can receive multiple notifications, and multiple listeners can listen to the same MBean. Each registration can use a different filter and handback.

A notification is **event-oriented**, whereas \`getCompletedJobs()\` represents **state**. If a listener misses a few events, reading the attribute can still fetch the current snapshot, though it will not automatically restore the entire event history.

## 9. Filtering Notifications with NotificationFilter

\`NotificationFilter\` is a functional interface with:

\`\`\`java
boolean isNotificationEnabled(Notification notification);
\`\`\`

A custom filter:

\`\`\`java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter importantJobs =
    (Notification notification) -> {
        if (!"app.job.completed".equals(
                notification.getType())) {
            return false;
        }

        Object data = notification.getUserData();
        return data instanceof String jobId
            && jobId.startsWith("important-");
    };
\`\`\`

When registering:

\`\`\`java
server.addNotificationListener(
    name,
    listener,
    importantJobs,
    "important-jobs"
);
\`\`\`

A listener is invoked only when the filter accepts the notification. If the filter is \`null\`, every notification emitted by the MBean can be forwarded to the listener according to the contract.

### NotificationFilterSupport prefix-based filtering

\`\`\`java
NotificationFilterSupport filter =
    new NotificationFilterSupport();

filter.enableType("app.job.");
\`\`\`

Point to remember: \`NotificationFilterSupport\` uses **prefix matching**. With prefix \`app.job.\`, it can receive \`app.job.completed\`, \`app.job.failed\`, or \`app.job.started\`, as long as the MBean emits those types. If you want strictly one type, use a filter comparing with \`equals\` or choose a sufficiently specific prefix based on type naming conventions.

This is an easily overlooked difference when filtering a sensitive event: \`enableType("app.job.completed")\` can also match a longer type starting with that string, such as \`app.job.completed.detail\`.

## 10. What Is Handback?

\`handback\` is a context object passed in by the listener registrant; when a notification arrives, JMX passes that exact context back to the callback:

\`\`\`java
Object handback = "pool=main";

server.addNotificationListener(
    name,
    (notification, context) -> {
        System.out.println(context);
    },
    null,
    handback
);
\`\`\`

Handback is useful when the same callback handles events from multiple sources and needs to know which subscription triggered the callback, such as \`node\`, \`region\`, or environment name.

Do not confuse:

- \`notification.getUserData()\`: payload set by the **emitter** of the notification.
- \`handback\`: context supplied by the **listener** at registration time.
- \`notification.getSource()\`: event source according to JMX.
- \`ObjectName\`: MBean identifier in the MBeanServer, typically stored separately in client-side subscription data.

With remote connections, handback transport characteristics depend on the connector mechanism; prefer small, simple, serialization-friendly contexts.

## 11. Removing Listeners: Two Removal Styles with Different Meanings

JMX provides overloads on \`MBeanServer\`/\`MBeanServerConnection\`:

\`\`\`java
removeNotificationListener(
    ObjectName name,
    NotificationListener listener
);

removeNotificationListener(
    ObjectName name,
    NotificationListener listener,
    NotificationFilter filter,
    Object handback
);
\`\`\`

For a listener with multiple registrations on the same MBean:

\`\`\`java
server.addNotificationListener(
    name, listener, filterA, "A"
);
server.addNotificationListener(
    name, listener, filterB, "B"
);
\`\`\`

Calling:

\`\`\`java
server.removeNotificationListener(
    name, listener, filterA, "A"
);
\`\`\`

aims to remove registration A while keeping B. Meanwhile:

\`\`\`java
server.removeNotificationListener(
    name, listener
);
\`\`\`

removes the registrations corresponding to that listener on the MBean.

Some common errors:

- **\`ListenerNotFoundException\`**: no matching registration found to remove.
- **\`InstanceNotFoundException\`**: the MBean for that ObjectName no longer exists.
- **Shutdown race**: the MBean may be unregistered before listener cleanup runs.
- **Duplicate registration**: the callback is invoked multiple times because the same listener was added multiple times. Organize subscriptions to add once or store each registration accurately.

Rule of thumb: every \`addNotificationListener\` should have a corresponding \`removeNotificationListener\` strategy executed when stopping the component or closing the connection.

## 12. MBeanServerDelegate: Notifications About the Registry Itself

JMX has a system MBean \`JMImplementation:type=MBeanServerDelegate\` (constant \`MBeanServerDelegate.DELEGATE_NAME\`). It emits notifications when MBeans are registered with or removed from the MBeanServer.

\`\`\`java
import javax.management.MBeanServerDelegate;
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;

NotificationListener registryListener =
    (notification, handback) -> {
        if (notification instanceof MBeanServerNotification e) {
            System.out.println(
                "Registry event: " + e.getType()
                    + " " + e.getMBeanName()
            );
        }
    };

server.addNotificationListener(
    MBeanServerDelegate.DELEGATE_NAME,
    registryListener,
    null,
    null
);

try {
    // Monitor MBean registration or unregistration.
} finally {
    server.removeNotificationListener(
        MBeanServerDelegate.DELEGATE_NAME,
        registryListener
    );
}
\`\`\`

Common event types include \`JMX.mbean.registered\` and \`JMX.mbean.unregistered\`. This is useful when a client wants to automatically discover new MBeans and register per-instance listeners. Querying existing MBeans and listening for registry changes must handle races, because an MBean may appear or disappear between the two steps.

## 13. Notifications in Spring Framework

Two cases must be distinguished.

### Case A: The bean is a standard JMX broadcaster MBean

If a Spring bean implements a Standard MBean and extends \`NotificationBroadcasterSupport\`, Spring can export it as an MBean capable of emitting notifications.

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

import java.util.Map;

@Configuration
public class JobMonitorJmxConfig {

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            JobMonitor jobMonitor
    ) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "learning.jmx:type=JobMonitor,name=spring",
            jobMonitor
        ));

        return exporter;
    }
}
\`\`\`

Once the exporter registers successfully, JMX clients use the ObjectName:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=JobMonitor,name=spring"
);
\`\`\`

to attach listeners or invoke operations. Ensure the client connects to the exact MBeanServer used by the exporter. Do not misconfigure multiple exporters registering the same ObjectName.

### Case B: Regular bean + Spring JMX metadata

Spring supports \`@ManagedResource\`, \`@ManagedOperation\`, and \`@ManagedAttribute\` to publish a plain Java bean via \`AnnotationMBeanExporter\` or \`@EnableMBeanExport\`. For notifications, Spring provides a mechanism to forward notifications from a bean that emits events appropriately through the JMX MBean.

One option is using \`NotificationPublisherAware\` to receive a Spring-supplied \`NotificationPublisher\`, then emitting notifications with \`sendNotification\` without managing listeners manually.

Example:

\`\`\`java
package example.springjmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=JobMonitor,name=managed"
)
public class ManagedJobService
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();

    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher
    ) {
        this.publisher = publisher;
    }

    @ManagedOperation(description = "Complete a managed job")
    public void complete(String jobId) {
        // Illustrative business logic.
        Notification notification = new Notification(
            "app.job.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Completed: " + jobId
        );

        publisher.sendNotification(notification);
    }
}
\`\`\`

Configuration enabling export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfig {
}
\`\`\`

Spring provides the publisher in the appropriate export context. The publisher must be called **after the bean has been exported and the publisher setter callback has run**; if code calls \`complete\` too early in the lifecycle, the publisher reference may not be ready yet. \`NotificationPublisherAware\` lets the bean focus on creating notifications while the JMX adapter handles forwarding to listeners.

To advertise notification types in JMX metadata for management tools, you can use \`@ManagedNotification\` inside \`@ManagedNotifications\` on the exported class, matching Spring's annotation mechanism.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=JobMonitor,name=annotated"
)
@ManagedNotifications({
    @ManagedNotification(
        name = "app.job.completed",
        description = "A job completed",
        notificationTypes = { "app.job.completed" }
    )
})
public class AnnotatedJobMonitor {
    // Similar business logic and NotificationPublisherAware.
}
\`\`\`

In the respective Spring versions and export mechanisms, use notification annotations conforming to the metadata contract supported by the library. \`@ManagedNotification\` describes the JMX type; it does not emit notifications on its own. Emitting events still requires calling the publisher or broadcaster.

## 14. Spring NotificationListenerBean: Registering Listeners via Configuration

Spring also provides \`org.springframework.jmx.export.NotificationListenerBean\` to configure listeners with the exporter.

\`\`\`java
import javax.management.NotificationListener;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

NotificationListener loggingListener =
    (notification, context) -> {
        System.out.println(notification.getMessage());
    };

NotificationListenerBean binding =
    new NotificationListenerBean(loggingListener);

binding.setMappedObjectNames(
    "learning.jmx:type=JobMonitor,name=spring"
);

MBeanExporter exporter = new MBeanExporter();
exporter.setNotificationListeners(binding);
\`\`\`

This is an illustrative configuration snippet: in a real application, declare fully managed beans/exporters and include the target MBean in the exporter's export list. \`mappedObjectNames\` specifies which MBeans the listener attaches to; it does not replace the notification creation mechanism in the implementation.

Distinguishing the two sides:

\`\`\`text
Server-side:
  Spring bean
    -> JMX MBean + NotificationPublisher / broadcaster
    -> MBeanServer

Server-side Spring exporter listener:
  NotificationListenerBean
    -> exporter registers listener for matching MBeans

Client-side:
  MBeanServerConnection
    -> addNotificationListener(ObjectName,...)
    -> receives callbacks via JMX connector
\`\`\`

These setups can coexist, but avoid accidentally creating duplicate listeners and manage lifecycles clearly.

## 15. NotificationPublisher vs. NotificationBroadcasterSupport

| Perspective | \`NotificationBroadcasterSupport\` | Spring \`NotificationPublisherAware\` |
|---|---|---|
| API Level | Standard JMX (\`javax.management\`) | Spring JMX |
| Target Usage | MBean directly implementing broadcaster | Spring bean exported via Spring mechanism |
| Emitting notifications | \`sendNotification(notification)\` | \`publisher.sendNotification(notification)\` |
| Listener management | Support class manages listeners | Spring/JMX adapter manages publishing side |
| Metadata | Override \`getNotificationInfo()\` | Metadata from Spring JMX assembler/annotations |
| Best suited for | MBeans needing pure JMX compatibility | Spring beans wanting reduced coupling to JMX listener mechanics |
| Caveat | Choose executor/dispatch and clean up listeners | Wait for publisher injection when exporter is ready |

Both approaches expose notifications to the JMX model. Choose based on whether your class is a **direct JMX MBean** or an **exported Spring business bean**.

## 16. Distinguishing JMX Notifications from Spring ApplicationEvent

Spring has \`ApplicationEventPublisher\` and \`@EventListener\` for event communication inside the application context. JMX notifications serve observation/management through MBeanServer.

| Criterion | Spring ApplicationEvent | JMX Notification |
|---|---|---|
| Primary scope | Internal application/Spring context | JMX MBeanServer and management clients |
| Emitting events | \`ApplicationEventPublisher.publishEvent(...)\` | \`sendNotification(...)\` or Spring \`NotificationPublisher\` |
| Listening | \`@EventListener\`, \`ApplicationListener\` | \`NotificationListener\` |
| Source identity | Based on event class/source in Spring | MBean/ObjectName, notification type/source |
| Remote access | Not by default | Possible via JMX connector when configured |
| Durable storage | Not by default | Not by default |

You can **bridge** from Spring ApplicationEvent to JMX Notification to expose a required subset of operational events. However, do not publish sensitive business data by default, do not use JMX notifications as the primary event bus for business workflows, and avoid turning every Spring event into a notification that causes heavy load.

## 17. Notification, AttributeChangeNotification, and Sequence Numbers

JMX has the subclass \`AttributeChangeNotification\` to describe an attribute change:

\`\`\`java
import javax.management.AttributeChangeNotification;

Notification change = new AttributeChangeNotification(
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "ActiveCount changed",
    "ActiveCount",
    "int",
    5,
    8
);

sendNotification(change);
\`\`\`

It contains:

- Attribute name \`ActiveCount\`.
- Attribute type \`int\`.
- Old value \`5\`, new value \`8\`.
- Type \`jmx.attribute.change\`.

**Not every Java field change automatically generates an \`AttributeChangeNotification\`.** The implementation or adapter must emit the notification. A client can receive the event and re-read the attribute to obtain the current state.

Sequence numbers help identify the order of events emitted by one source if the implementation increments the number consistently. They do not inherently provide exactly-once delivery, global ordering across MBeans, or automatic replay of missed notifications.

## 18. Protecting Callbacks and Reducing Thread-Blocking Risks

Listeners often run close to the notification-emitting thread, especially with local broadcasters using a synchronous dispatcher. If a callback is slow, it can prolong notification emission time.

One option is offloading heavy work to a separate executor:

\`\`\`java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.management.NotificationListener;

ExecutorService executor =
    Executors.newSingleThreadExecutor();

NotificationListener listener = (notification, handback) -> {
    executor.submit(() -> {
        // Process outside the event emission path.
        System.out.println(notification.getMessage());
    });
};

// After removing the listener and when the executor is no longer needed:
executor.shutdown();
\`\`\`

This merely illustrates offloading work. In production, define policies for full executor queues, shutdown, callback errors, and task count control. For high-volume notifications, measure throughput, latency, and dropped events according to the defined policy rather than creating unbounded tasks in memory.

If using \`NotificationBroadcasterSupport\` with a custom executor, manage that executor's lifecycle as well to ensure safe shutdown. Do not keep listeners alive longer than the component that needs to receive events.

## 19. Accessing Notifications via Remote JMX

Remote clients can register listeners using \`MBeanServerConnection\`:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName name = new ObjectName(
        "learning.jmx:type=JobMonitor,name=spring"
    );

    NotificationListener listener =
        (notification, handback) ->
            System.out.println(notification.getMessage());

    connection.addNotificationListener(
        name,
        listener,
        null,
        null
    );

    try {
        // Keep the client active while events need to be received.
    } finally {
        connection.removeNotificationListener(
            name,
            listener
        );
    }
}
\`\`\`

The example assumes a remote JMX connector is properly configured and authorized. \`@EnableMBeanExport\` or \`MBeanExporter\` **does not automatically open a remote JMX port**. You must configure the connector/agent and secure the connection with authentication, authorization, TLS, and appropriate network access restrictions.

When the network disconnects, notifications may not arrive. Clients must design for reconnection, re-registering listeners, and synchronizing state via attributes/polling or durable data sources if the business requires it.

## 20. Common Errors

| Symptom | Possible Cause | How to Diagnose |
|---|---|---|
| Notifications not received | \`sendNotification\`/\`publisher.sendNotification\` not called; wrong ObjectName; filter rejects | Check emission path, listener registration, and type |
| Listener receives events from only one instance | Listener attached to a specific ObjectName | Register separately for each target MBean |
| Duplicate events received | Same listener added multiple times | Check registration count and lifecycle |
| Remove throws \`ListenerNotFoundException\` | Wrong listener/filter/handback or already removed | Use the exact registration from add |
| Remove throws \`InstanceNotFoundException\` | MBean already unregistered | Check lifecycle and handle cleanup safely |
| Metadata shown but no events arrive | \`getNotificationInfo\` only describes, does not emit | Check the send call sites |
| Events arrive but payload unreadable remotely | UserData incompatible with remote serialization/classpath | Prefer JMX-friendly types/payloads |
| Slow callbacks degrade app responsiveness | Synchronous dispatch or overloaded queue | Offload processing, set limits, monitor latency |
| New MBeans are not monitored | Listener attached only to MBean list at query time | Watch \`MBeanServerDelegate\` and refresh subscriptions |
| Spring bean has no publisher | Not exported properly or called too early in lifecycle | Check exporter, metadata, and injection timing |

## 21. Practice Scenario

**Context:** an application has two MBeans:

\`\`\`text
learning.jmx:type=JobMonitor,name=orders
learning.jmx:type=JobMonitor,name=payments
\`\`\`

Each MBean emits two types: \`app.job.completed\` and \`app.job.failed\`. The monitoring system only wants to receive \`failed\` notifications from the \`orders\` MBean.

Approach:

1. Create the exact \`ObjectName\` for \`orders\`.
2. Create a \`NotificationListener\` to handle events.
3. Create a \`NotificationFilter\` accepting only the exact type \`app.job.failed\`.
4. Attach the listener to \`orders\` via \`MBeanServerConnection\`.
5. When finished, remove the exact listener/filter/handback.

\`\`\`java
ObjectName orders = new ObjectName(
    "learning.jmx:type=JobMonitor,name=orders"
);

NotificationListener listener =
    (event, context) ->
        System.out.println("FAILED: " + event.getMessage());

NotificationFilter filter =
    event -> "app.job.failed".equals(event.getType());

connection.addNotificationListener(
    orders,
    listener,
    filter,
    "orders"
);

try {
    // Monitor notifications.
} finally {
    connection.removeNotificationListener(
        orders,
        listener,
        filter,
        "orders"
    );
}
\`\`\`

If the \`payments\` MBean also emits \`app.job.failed\`, this listener still does not receive it because the subscription is bound to the \`orders\` ObjectName. If \`orders\` unregisters and re-registers, the client must consider re-registering the listener.

## 22. Concept Check Questions

1. Why does an MBean having \`getNotificationInfo()\` not guarantee that it emits notifications?
2. What capability does \`NotificationEmitter\` add compared to \`NotificationBroadcaster\`?
3. When does \`NotificationBroadcasterSupport\` reduce boilerplate code?
4. Does \`NotificationFilterSupport.enableType("app.job.")\` accept \`app.job.failed\`?
5. How does \`handback\` differ from a notification's \`userData\`?
6. If a local listener takes 5 seconds to process, why can it affect the business invocation thread?
7. Does a listener attached to an old MBean's \`ObjectName\` automatically transfer to an MBean re-registered under the same name?
8. When a remote connector disconnects, do JMX notifications automatically replay after reconnecting?
9. In Spring, what does \`NotificationPublisherAware\` enable?
10. Why should notifications be combined with reading current attributes when reliable observability is needed?

**Hint:** metadata, registration, dispatch, and lifecycle are separate concerns. The notification mechanism can signal events quickly, but it does not replace state storage/recovery contracts.

## 23. Final Takeaways

\`\`\`text
NotificationBroadcaster
  = can manage listeners and describe notifications

NotificationEmitter
  = NotificationBroadcaster
    + remove a specific registration
      (listener, filter, handback)

NotificationBroadcasterSupport
  = convenient implementation
    + sendNotification(notification)

NotificationListener
  = callback that receives notifications

NotificationFilter
  = condition deciding whether an event is forwarded

MBeanServer / MBeanServerConnection
  = where clients attach listeners by ObjectName

Spring NotificationPublisherAware
  = bean supported by Spring to emit JMX notifications
    via a publisher supplied by the exporter
\`\`\`

**Operational rule:** The MBean must **actively emit**, listeners must **register properly**, filters must **permit**, and subscription lifecycles must be **cleaned up**. Treat notifications as point-in-time management signals; durable state and event history require separate mechanisms.