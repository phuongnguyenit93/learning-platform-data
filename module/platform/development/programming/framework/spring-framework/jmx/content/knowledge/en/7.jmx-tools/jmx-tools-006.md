# Testing Notifications in JMX Tools

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** JMX Tools  
> **Lesson:** Testing Notifications in JMX Tools

## 1. Objectives

After this lesson, you can:

- Determine whether an MBean advertises the capability to emit **JMX notifications**.
- Connect to the right JVM using JConsole or an appropriate JMX tool and locate the exact **ObjectName** of the MBean.
- Subscribe to notifications in the tool, trigger a test event, and inspect \`type\`, \`source\`, \`sequenceNumber\`, \`timeStamp\`, \`message\`, and \`userData\` when displayed by the tool.
- Distinguish **missing notification metadata**, **no registered listener**, **filter blocking**, **event not emitted**, **wrong JVM/MBeanServer**, and **unstable remote connection**.
- Use \`MBeanServerConnection\` as an independent verification tool when precise control over filters, subscriptions, and event payloads is needed.
- Understand how Spring exports beans and emits notifications, while managing listener lifecycles properly.

## 2. What Is a Notification in Monitoring Workflows?

JMX (Java Management Extensions) lets applications expose management data via MBeans. Three common mechanisms:

| Mechanism | Purpose | How Clients Use It |
|---|---|---|
| **Attribute** | Read or change current state. | Attributes tab or \`getAttribute\`/\`setAttribute\`. |
| **Operation** | Request the MBean to perform an action. | Operations tab or \`invoke\`. |
| **Notification** | MBean proactively sends notice of an event. | Notifications tab or \`addNotificationListener\`. |

Example: a queue management MBean has attribute \`QueueDepth\`, operation \`resetQueue()\`, and notification \`app.queue.threshold.exceeded\` when queue length exceeds a threshold.

Notifications are **point-in-time**. If you open the UI only after an event has already occurred, you typically will not see past events. Normally, the tool must **register a listener first**, and only afterward is the event generated and emitted.

\`\`\`text
Spring/JVM Application
      |
      v
MBean emits Notification
      |
      v
MBeanServer (right JVM and ObjectName)
      |
      +---- Local JMX attach ----> JConsole
      |
      +---- JMX Connector -------> Remote JMX Client
                                       |
                                       v
                              Registered Listener
                                       |
                                       v
                          Displays type / message / time
\`\`\`

Subscribing to notifications on an MBean does not turn JMX into a durable message queue. JMX notifications by default do not provide replay, durable subscriptions, exactly-once delivery, or guaranteed retention of full history while a client is disconnected.

## 3. Preparing a Repeatable Test Scenario

A reliable notification test should include:

1. **Right MBean:** a clear \`ObjectName\`, e.g., \`learning.jmx:type=TaskMonitor,name=main\`.
2. **Known notification type:** e.g., \`app.task.completed\`.
3. **Controlled trigger:** an operation \`completeTask(String taskId)\` or an application action you can intentionally trigger.
4. **Listener registered before the trigger:** to avoid missing events because the tool started listening too late.
5. **Correlation data:** event type, timestamp, sequence number, message, and a correlation identifier such as task ID.
6. **Cleanup:** remove the listener when finished, close connections, and unregister the test MBean if you registered it yourself.

If the application has real events without an easy-to-repeat trigger, set up a test environment with suitable data. Avoid triggering destructive operations such as clearing production caches, closing connections, or resetting state just to verify the UI.

## 4. Creating a Demo MBean That Emits Notifications

The following pure JMX example can be observed with JConsole without configuring a remote connector.

### 4.1. Standard MBean Interface

\`\`\`java
package example.jmx;

public interface TaskMonitorMBean {
    long getCompletedCount();

    String completeTask(String taskId);
}
\`\`\`

The interface name follows Standard MBean rules: class \`TaskMonitor\` implements \`TaskMonitorMBean\`. \`getCompletedCount()\` becomes a management attribute, while \`completeTask(String)\` is exposed as an operation.

### 4.2. Implementation That Emits Notifications

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class TaskMonitor extends NotificationBroadcasterSupport
        implements TaskMonitorMBean {

    public static final String TASK_COMPLETED =
        "app.task.completed";

    private final AtomicLong completedCount =
        new AtomicLong();

    private final AtomicLong sequence =
        new AtomicLong();

    @Override
    public long getCompletedCount() {
        return completedCount.get();
    }

    @Override
    public String completeTask(String taskId) {
        if (taskId == null || taskId.isBlank()) {
            throw new IllegalArgumentException(
                "taskId must not be blank"
            );
        }

        long total = completedCount.incrementAndGet();

        Notification event = new Notification(
            TASK_COMPLETED,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Task completed: " + taskId
        );
        event.setUserData(taskId);

        sendNotification(event);

        return "completed=" + total;
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { TASK_COMPLETED },
                Notification.class.getName(),
                "A task was completed"
            )
        };
    }
}
\`\`\`

Here:

- \`sendNotification(event)\` actually emits the notification. Declaring \`getNotificationInfo()\` alone does not generate events.
- \`type\` is \`app.task.completed\`, used to classify the event.
- \`source\` is set to \`this\` in the implementation; when passing through an MBeanServer or remote connector, the source representation may differ. Do not cast \`source\` to a concrete implementation class on the client.
- \`sequenceNumber\` increments per \`TaskMonitor\` instance. It is not a global order across all MBeans.
- \`timeStamp\` is the emission time provided by the implementation, not necessarily identical to the time the tool receives it.
- \`userData\` holds \`taskId\` to correlate events during testing.
- \`CompletedCount\` lets you read aggregate state after an event, but an attribute does not replace notification history.

### 4.3. Registering the MBean and Keeping the JVM Alive

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class TaskMonitorApplication {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "learning.jmx:type=TaskMonitor,name=main"
        );

        server.registerMBean(new TaskMonitor(), name);

        System.out.println("MBean registered: " + name);
        System.out.println(
            "PID: " + ProcessHandle.current().pid()
        );
        System.out.println(
            "Open JConsole and invoke completeTask(...)"
        );

        // Keep the JVM alive so JConsole has time to connect.
        System.in.read();

        server.unregisterMBean(name);
    }
}
\`\`\`

Start \`TaskMonitorApplication\` in a JVM that JConsole can attach to. The program waits for stdin input before exiting; do not press Enter until you finish the verification steps.

This example uses the **platform MBeanServer** and registers an explicit name. When re-running multiple times in the same JVM, if the name already exists, \`registerMBean\` may throw \`InstanceAlreadyExistsException\`; do not silently unregister MBeans not owned by the test.

## 5. Connecting JConsole to the Right JVM

JConsole is a JMX GUI tool bundled with many JDK distributions. A common way to launch it is running \`jconsole\` from the JDK's \`bin\` directory.

Sequence:

1. Start the test application and note the PID it prints.
2. Open a terminal with the matching JDK and run \`jconsole\`.
3. Choose **Local Process** with the matching PID. If the application runs from an IDE, still pick the application's JVM process rather than the IDE or Gradle daemon.
4. Accept the connection prompt if JConsole asks for confirmation.
5. Open the **MBeans** tab and find the \`learning.jmx\` domain.
6. Select the MBean with key properties \`type=TaskMonitor,name=main\`.

A JVM can contain many system MBeans in \`java.lang\`, \`com.sun.management\`, or other domains. Do not confuse default JVM MBeans with application MBeans.

**Note:** depending on OS, JDK, user permissions, and attach settings, JConsole may not be able to connect to a local process. With containers, WSL, Docker, or multi-user environments, JConsole on the host may not see the JVM process as a local process. In such cases, configure an appropriate JMX connector; merely enabling Spring JMX export does not automatically open remote connectivity.

## 6. Finding the Notifications Tab in JConsole

After selecting an MBean, JConsole typically displays sections such as Attributes, Operations, Notifications, and Info depending on metadata and MBean type.

In the **Notifications** section:

- Check the list of notification types advertised by the MBean.
- Click **Subscribe** or the equivalent action so JConsole registers a listener.
- Only after subscribing should you trigger the notification.
- Watch the received notification count and select an event to view its details and timestamp.
- Use **Unsubscribe** when you no longer need to listen.

Button labels and layout may vary across JDK/JConsole versions. Recognize that the action's purpose is **registering/unregistering a listener with the MBean**, rather than relying strictly on a fixed button position in the UI.

If Notifications is missing, inspect the Info tab or MBean metadata. An MBean that does not advertise notifications or implement event emission may not provide a listening surface in the tool.

Rule of thumb: **a successful Subscribe does not mean an event has arrived yet**. Subscribing only registers a listener; a subsequent \`sendNotification\` is needed for data to appear.

## 7. Testing Events Directly via Operations

For \`TaskMonitor\`, JConsole can display the operation:

\`\`\`text
completeTask(java.lang.String)
\`\`\`

After subscribing:

1. Switch to **Operations**.
2. Select \`completeTask\` and enter a test ID such as \`job-001\`.
3. Invoke the operation.
4. Return to **Notifications** to view the new event.
5. Match the message against \`job-001\`, type \`app.task.completed\`, sequence number, and timestamp.
6. Under **Attributes**, re-read \`CompletedCount\` to verify the value incremented.

Expected after one successful call:

\`\`\`text
Type:          app.task.completed
Message:       Task completed: job-001
UserData:      job-001
Sequence:      1
Timestamp:     execution time
CompletedCount: 1
\`\`\`

Numbers and timestamps depend on the instance's history. If invoked multiple times, sequence and \`CompletedCount\` will be higher. If unregistered and recreated as a new instance, counters may start over from the beginning. JConsole may display \`userData\` or source in its own format, so verify based on the type/message/sequence the tool actually provides.

For operations taking parameters, the tool must convert UI input into the appropriate Java type. If the UI does not support entering an operation's parameter type, you can use a Java client via \`MBeanServerConnection.invoke\` to trigger the event instead of struggling in the GUI.

## 8. How to Read Notification Fields

| Field | Meaning | Example | What to Avoid |
|---|---|---|---|
| \`type\` | Event classification code. | \`app.task.completed\` | Do not assume all MBeans use the same type naming convention. |
| \`source\` | Emitter source in JMX representation. | MBean/ObjectName or other source | Do not cast to a Spring bean when remote. |
| \`sequenceNumber\` | Sequence number assigned by the emitter. | \`8\` | Do not assume global ordering. |
| \`timeStamp\` | Timestamp stored by the event. | Epoch milliseconds | Do not equate with the time the UI received it. |
| \`message\` | Human-readable description. | \`Task completed: job-001\` | Do not use message as the sole machine-readable identifier. |
| \`userData\` | Extra payload supplied by the emitter. | \`job-001\` | Remote clients may fail to deserialize arbitrary objects. |

For systematic analysis, combine **ObjectName + notification type + sequenceNumber + timestamp + correlation ID**. If an application has multiple instances, sequence number \`1\` from two instances represents two different events.

Event types are often dot-separated hierarchical strings. Example:

\`\`\`text
app.task.started
app.task.completed
app.task.failed
\`\`\`

That is an application convention; JMX does not force every event to use these three names.

## 9. Checking Metadata: Does the MBean Advertise Notifications?

JConsole renders views based on metadata from JMX. You can inspect it directly via the API:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanNotificationInfo n : info.getNotifications()) {
    System.out.println(n.getDescription());

    for (String type : n.getNotifTypes()) {
        System.out.println("  type=" + type);
    }
}
\`\`\`

If \`info.getNotifications()\` is empty, tools have difficulty knowing expected notification types. Conversely, having metadata does not prove events are actually emitted.

Distinguish four steps:

\`\`\`text
1. MBean is registered
2. MBean advertises notification metadata
3. Client registers listener
4. MBean actively emits notification
\`\`\`

Each step can succeed or fail independently. If the GUI does not show an event, do not immediately conclude "JMX is broken"; find which link in the chain did not happen.

## 10. Independent Verification with NotificationListener

When JConsole does not show enough detail, a programmatic JMX client lets you observe received notifications clearly.

Example using \`MBeanServerConnection\` and the right \`ObjectName\`:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "learning.jmx:type=TaskMonitor,name=main"
);

NotificationListener listener =
    (Notification event, Object context) -> {
        System.out.printf(
            "type=%s source=%s seq=%d time=%d%n",
            event.getType(),
            event.getSource(),
            event.getSequenceNumber(),
            event.getTimeStamp()
        );
        System.out.println(
            "message=" + event.getMessage()
        );
        System.out.println(
            "userData=" + event.getUserData()
        );
        System.out.println(
            "handback=" + context
        );
    };

connection.addNotificationListener(
    name,
    listener,
    null,
    "diagnostic-session"
);

try {
    connection.invoke(
        name,
        "completeTask",
        new Object[] { "job-002" },
        new String[] { "java.lang.String" }
    );

    // Allow enough time for the callback if the connection is remote.
} finally {
    connection.removeNotificationListener(
        name,
        listener
    );
}
\`\`\`

\`connection\` must be an \`MBeanServerConnection\` pointing to the server that registered the MBean. The snippet above is **code within a context holding a connection**, not a standalone runnable Java class. When verifying remotely, you can use \`JMXConnectorFactory.connect\` to obtain the connection and close the connector when done.

If a remote client receives events asynchronously, removing the listener immediately after \`invoke\` can miss callbacks still in transit. For a deterministic check, use a \`CountDownLatch\` to wait for the event with a bounded timeout.

## 11. Timed Testing with CountDownLatch

The following example helps distinguish an event genuinely arriving from guessing based on console logs.

\`\`\`java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import javax.management.MBeanServerConnection;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public static Notification awaitTaskCompleted(
        MBeanServerConnection connection,
        ObjectName name,
        String taskId
) throws Exception {

    CountDownLatch latch = new CountDownLatch(1);
    AtomicReference<Notification> captured =
        new AtomicReference<>();

    NotificationListener listener = (event, context) -> {
        if (!"app.task.completed".equals(event.getType())) {
            return;
        }

        if (!taskId.equals(event.getUserData())) {
            return;
        }

        captured.set(event);
        latch.countDown();
    };

    connection.addNotificationListener(
        name,
        listener,
        null,
        taskId
    );

    try {
        connection.invoke(
            name,
            "completeTask",
            new Object[] { taskId },
            new String[] { "java.lang.String" }
        );

        boolean arrived = latch.await(
            5,
            TimeUnit.SECONDS
        );

        if (!arrived) {
            throw new IllegalStateException(
                "No matching notification within timeout"
            );
        }

        return captured.get();
    } finally {
        connection.removeNotificationListener(
            name,
            listener
        );
    }
}
\`\`\`

**How to interpret the result:** success means the listener received a notification whose type and \`userData\` matched the task ID. A timeout only tells you **no matching event was observed within the wait window**; it could be because no event was emitted, the filter did not match, the listener was registered incorrectly, the network was slow, or the connector dropped. Do not conclude a single specific cause solely from a timeout.

With tests against a local MBeanServer, results are usually fast and stable. With remote JMX, factor in realistic latency and stability when choosing a timeout.

## 12. Filters in Tools and Verification via API

Some tools let you filter displayed events or select notification types. A tool's UI filter can differ from a JMX filter registered on the server side. When you need exact control over event types, use \`NotificationFilter\`:

\`\`\`java
import javax.management.NotificationFilter;

NotificationFilter onlyCompleted =
    event -> "app.task.completed".equals(
        event.getType()
    );

connection.addNotificationListener(
    name,
    listener,
    onlyCompleted,
    null
);
\`\`\`

You can also use \`NotificationFilterSupport\`:

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter =
    new NotificationFilterSupport();

filter.enableType("app.task.");
\`\`\`

However, \`NotificationFilterSupport\` performs **prefix matching**: \`app.task.\` can match both \`app.task.completed\` and \`app.task.failed\`. If you need an exact type string, an \`equals\`-based filter is more suitable.

To remove the exact registration using that filter, call:

\`\`\`java
connection.removeNotificationListener(
    name,
    listener,
    onlyCompleted,
    null
);
\`\`\`

Keep references to the same listener, filter, and handback objects used when adding. The overload taking only \`name, listener\` may remove all registrations of that listener on the MBean.

## 13. Testing Notifications When Spring Exports Beans

Spring Framework can register beans as MBeans using \`MBeanExporter\` or \`@EnableMBeanExport\`. For ordinary beans, Spring supports \`NotificationPublisherAware\` to receive a publisher and emit JMX notifications.

### 13.1. Spring Bean Emitting Notifications

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
    objectName = "learning.jmx:type=TaskMonitor,name=spring"
)
public class ManagedTaskService
        implements NotificationPublisherAware {

    private final AtomicLong sequence =
        new AtomicLong();

    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher
    ) {
        this.publisher = publisher;
    }

    @ManagedOperation(description = "Complete a task")
    public void completeTask(String taskId) {
        Notification event = new Notification(
            "app.task.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Task completed: " + taskId
        );
        event.setUserData(taskId);

        publisher.sendNotification(event);
    }
}
\`\`\`

Export configuration:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Ensure the application context creates the bean and export completes before calling \`completeTask\`. Calling it too early before the publisher is injected may fail because the publisher has not been initialized yet.

### 13.2. Advertising Notification Types to Tools

In Spring, notification metadata can be configured with \`@ManagedNotification\` inside \`@ManagedNotifications\` on the exported class:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=TaskMonitor,name=spring"
)
@ManagedNotifications({
    @ManagedNotification(
        name = "app.task.completed",
        description = "A task has completed",
        notificationTypes = { "app.task.completed" }
    )
})
public class AnnotatedTaskMonitor {
    // Combine with an appropriate notification emission mechanism.
}
\`\`\`

Metadata helps management tools recognize event types. Annotations by themselves do not emit events; \`publisher.sendNotification\` or an actual broadcaster mechanism is still required.

If you use this code, place the metadata on the actual Spring bean class being exported and implement the corresponding emission logic. Do not register an extra demo class with the same ObjectName.

### 13.3. Connecting to the Right Server

\`@EnableMBeanExport\` only enables exporting beans to JMX. It does not automatically open a remote connector. If the Spring exporter registers on the platform MBeanServer, a local JConsole attached to the same JVM can usually observe the MBean. If the application uses a separate MBeanServer, JConsole attached to the platform server may not see the MBean even though the exporter registered it successfully.

When multiple JVM applications run on the same host, cross-check PID, domain, and ObjectName rather than looking only at similar process names.

## 14. Testing Notifications with JConsole: An Auditable Checklist

A test session can record the following details:

| Check Item | Evidence to Collect |
|---|---|
| Target JVM | PID, main class name, or startup command. |
| Target MBean | Canonical ObjectName and domain. |
| Notification metadata | List of types and descriptions in MBeanInfo. |
| Subscription | Timestamp/Subscribe action performed. |
| Trigger | Operation or application action and inputs used. |
| Event result | Type, message, sequence, timestamp, userData if present. |
| Post-trigger state | Related attribute, e.g., CompletedCount. |
| Cleanup | Unsubscribed and connector closed. |

Example log record:

\`\`\`text
JVM:             PID 18422
MBean:           learning.jmx:type=TaskMonitor,name=main
Notification:    app.task.completed
Subscribed at:   10:15:00
Trigger:         completeTask("job-001")
Observed at:     10:15:04
Event sequence:  1
Event message:   Task completed: job-001
Attribute:       CompletedCount = 1
Cleanup:         unsubscribed
\`\`\`

This is illustrative data, not output from a live system. In real environments, record the values actually shown by the tool rather than guessing from code.

If evidence is needed for regression testing, combining JConsole screenshots with client logs and \`CountDownLatch\` assertions helps distinguish manual verification from automated checks. Do not include sensitive data or credentials in shared screenshots or logs.

## 15. Diagnosing When Notifications Do Not Appear

### Scenario A: The MBean Does Not Appear

**Symptom:** domain or ObjectName cannot be found.

Common causes:

- Connected to the wrong JVM/PID.
- Spring export not enabled or bean not exported.
- ObjectName differs from expected name.
- MBeanServer in use differs from the platform server JConsole attached to.
- MBean was already unregistered.
- Registration error such as \`InstanceAlreadyExistsException\` or malformed ObjectName.

API verification:

\`\`\`java
boolean registered =
    connection.isRegistered(name);

System.out.println("registered=" + registered);
\`\`\`

When the MBean does not exist, there is no point checking filters or notification payloads yet; resolve registry/connection first.

### Scenario B: MBean Exists Without Notification Metadata

**Symptom:** Attributes/Operations may appear, but Notifications is missing or lists no event types.

Inspect \`MBeanInfo.getNotifications()\`. For Standard MBeans, the implementation must support a broadcaster and expose \`MBeanNotificationInfo[]\`. For Spring-exported beans, configure appropriate notification metadata.

Do not equate "no metadata" with "definitely no emission path": emitting and describing are separate responsibilities, though GUI tools generally rely on metadata to surface the capability.

### Scenario C: Subscribed, Yet No Events Arrive

Check in order:

1. Did you subscribe **before** generating the event?
2. Did you invoke the right operation or trigger the right business flow?
3. Does the implementation actually call \`sendNotification\` or \`publisher.sendNotification\`?
4. Is the listener attached to the right ObjectName?
5. Is the notification type being dropped by a filter?
6. Was the MBean unregistered/re-registered after subscribing?
7. Did the connection drop, or is the client paused or failing to process callbacks?

If needed, use a simple Java listener with no filter to rule out UI/filter issues.

### Scenario D: Unexpected Event Count

Possible reasons:

- The trigger was invoked multiple times.
- Duplicate listeners were registered.
- One action emits multiple notification types.
- A prefix filter accepts more types than expected.
- Asynchronous dispatch causes events to arrive delayed.
- The client missed events due to unsubscribing or disconnecting.
- Multiple instances emit notifications with independent sequence numbers.

Do not use the GUI event count as the sole proof of how many times business logic ran. Check the corresponding attributes/counters or business logs as well.

### Scenario E: Events Arrive, but Payload Is Hard to Read

With remote JMX, \`userData\` is a Java object and may require serialization/compatible classes on the client. When emitting notifications for general-purpose tools, prefer primitive wrappers, \`String\`, or standard JMX types. Avoid sending complex domain objects or sensitive data.

## 16. Notifications in JConsole vs. VisualVM and Other Clients

**JConsole** is typically handy for quick checks of local JVMs and MBeans exposing metadata. The tool lets you browse MBeans, view attributes/operations, and subscribe to notifications when supported.

**VisualVM** focuses on JVM observation; MBean browsing and notification viewing depend on installed plugins/features and application version. If your current VisualVM setup lacks a notification UI, that does not prove the MBean does not emit events. You can use JConsole or a programmatic JMX client to verify.

**Programmatic JMX clients** are well-suited for automated testing, exact filtering, correlation ID matching, timeouts, and controlled remote connections. The \`MBeanServerConnection\` API is the shared communication layer; tool UIs differ, yet all rely on the corresponding JMX operations.

An effective test can use JConsole for visual inspection and a Java test to assert that events are delivered to the listener with the expected data.

## 17. Local vs. Remote JMX: Connection Differences

Local attach:

\`\`\`text
JConsole -> JVM process -> platform MBeanServer
\`\`\`

Remote:

\`\`\`text
JConsole / client
      |
      v
JMXConnector
      |
      v
MBeanServerConnection
      |
      v
MBeanServer
\`\`\`

For remote connections, you need:

- A configured connector with a reachable endpoint.
- Hostname/port/JNDI/RMI aligned with network infrastructure.
- Proper authentication and authorization.
- TLS or appropriate transport security.
- Firewall and network policies allowing the connection.

Remote JMX over RMI may require attention to both the registry port and the advertised endpoint port, especially across NAT/containers. A connection succeeding for reading attributes does not guarantee every notification will be delivered reliably throughout the session.

**Do not expose remote JMX publicly to the Internet** just to test notifications. MBean operations can modify system state, and notifications may carry internal information.

## 18. Listener Lifecycle and Events from Dynamically Changing MBeans

If a tool or client subscribes and the MBean is later unregistered, the subscription to the old MBean does not automatically transfer to a new implementation. Even if a new MBean re-registers under **the same ObjectName**, the listener may need to be re-registered.

You can monitor registry changes through the system MBean \`MBeanServerDelegate\`:

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

connection.addNotificationListener(
    MBeanServerDelegate.DELEGATE_NAME,
    registryListener,
    null,
    null
);
\`\`\`

When \`JMX.mbean.registered\` or \`JMX.mbean.unregistered\` occurs, the client can update its list of watched MBeans. For applications with dynamic MBean registration, this provides a way to build re-subscription logic, though you must still handle races between query/subscribe and connection state.

Remember to remove the Delegate listener when closing the client.

## 19. Self-Check Questions

1. An MBean appears in JConsole without a Notifications tab: which metadata do you inspect first?
2. Why must you click Subscribe before invoking \`completeTask\`?
3. Does \`getNotificationInfo()\` automatically emit notifications?
4. Does \`getSequenceNumber()\` prove no events were lost across all MBeans?
5. How does \`getTimeStamp()\` differ from the time JConsole receives the event?
6. When \`NotificationFilterSupport.enableType("app.task.")\` is enabled, can \`app.task.failed\` be received?
7. If a remote client disconnects and reconnects, must the listener be re-registered?
8. When a Spring bean implements \`NotificationPublisherAware\`, what is the publisher used for?
9. If a notification was received yet \`CompletedCount\` did not change, what logic would you inspect?
10. Why should notifications not replace durable logs or audit trails?

A complete explanation connects four links: **registered MBean, advertised metadata, subscribed listener, and code actually emitting the event**.

## 20. Key Takeaways

\`\`\`text
[1] Connect to the right JVM / MBeanServer
       |
[2] Find the right ObjectName
       |
[3] Check notification metadata
       |
[4] Subscribe listener
       |
[5] Trigger a known event
       |
[6] Observe type, source, sequence, time, message, userData
       |
[7] Read related attributes/logs to cross-check
       |
[8] Unsubscribe and close connection
\`\`\`

**The crux of testing notifications in JMX tools:** a tool can only display notifications it has the opportunity to receive. Always verify both the emission path **and** the listening path, trigger the event after subscribing, verify the right server/ObjectName, and use a Java listener with a timeout when you need stronger proof than a graphical UI.