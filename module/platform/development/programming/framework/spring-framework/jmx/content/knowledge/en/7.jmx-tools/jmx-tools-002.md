# Java Mission Control and Observing Management Information

## Objectives

After this lesson, you can use **Java Mission Control (JMC)** to connect to a running JVM, explore MBeans via JMX, read management information, perform controlled operations, and distinguish the roles of **JMX Console** and **Java Flight Recorder (JFR)**. You will also know how to verify that Spring Framework has exported MBeans properly, troubleshoot common issues when MBeans do not appear, and choose the right tool for monitoring or incident analysis.

## 1. What Is Java Mission Control?

Java Mission Control is a suite of tools for observing and analyzing Java applications. JMC provides a graphical interface to work with running JVMs and analyze Java Flight Recorder data. In modern JMC releases, the tool is distributed independently of the JDK; exact versions, installation packages, and specific screens depend on the JMC build in use.

Two functional groups to distinguish:

| Tool | Primary Data | Purpose |
| --- | --- | --- |
| **JMX Console / MBean Browser** | State and management operations exposed by the JVM/MBeans | Inspect current metrics, MBean attributes, operations, notifications; live monitoring |
| **Java Flight Recorder (JFR)** | Events recorded over a time interval | Analyze CPU, allocation, GC, threads, I/O, locks, and performance events with time context |

JMC supports both needs, but they should not be conflated: **JMX provides a management and state interface**, whereas **JFR provides event data to analyze JVM behavior over time**. You can use JMX to inspect the current connection count, then use JFR to locate the code causing high allocations or blocked threads during the same period.

In this Spring Framework JMX lesson, the focus is on **JMX Console**, especially the MBean Browser and how to inspect data exported by Spring.

## 2. Connection Architecture

A JMC observation session can be pictured as:

```text
+---------------------------+
| Java Mission Control      |
| - JVM Browser             |
| - JMX Console             |
| - MBean Browser           |
| - Graphs / Notifications  |
+-------------+-------------+
              |
              | JMX connection
              v
+---------------------------+
| Java process / JVM        |
| MBeanServer               |
|  + java.lang:*            |
|  + java.nio:*             |
|  + com.example:*          |
|  + Spring-exported MBeans |
+---------------------------+
```

Inside the JVM, `MBeanServer` manages MBeans registered by `ObjectName`. JMC acts as a **JMX client**, using APIs equivalent to `MBeanServerConnection` to discover `ObjectName`s, read `MBeanInfo`, fetch attributes, invoke operations, and register notification listeners.

Core point: JMC displays only what the JVM and MBeans have exposed. If a Spring bean is not exported as an MBean, opening JMC will not automatically turn that bean into a manageable JMX object.

A JVM typically has a **platform MBeanServer** containing system MBeans such as `java.lang:type=Memory`, `java.lang:type=Threading`, garbage collection management MBeans, and application-registered MBeans. The exact set of MBeans depends on the JVM, modules, and runtime configuration.

## 3. Environment Preparation

To practice, you need:

- A supported JDK to run the Java/Spring application.
- Java Mission Control installed and compatible with the environment and target JVM.
- A running Java application.
- Appropriate JMX connection permissions for the target JVM.

For a **local JVM**, JMC can usually discover processes via the management/attach mechanism provided by the JDK, depending on OS, user permissions, JVM configuration, and attach capability. If a process does not appear, check the account running the JVM, container namespace, attach permissions, and JMC/JDK compatibility.

For a **remote JVM**, the application must expose a management endpoint allowing remote connections. JMX over RMI may require both the registry port and RMI port to be permitted by the firewall; having a single open port may not suffice if the RMI stub advertises an unreachable hostname/port. Proper authentication, TLS, and network access restrictions must be configured. Avoid exposing remote JMX publicly on the Internet.

An isolated-network test configuration example:

```bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -jar app.jar
```

**Use the example with authentication and TLS disabled only when testing on a personal machine or an isolated environment.** Never carry `authenticate=false` and `ssl=false` into production. For remote machines, the hostname and firewall must match the actual connection path; for example, `127.0.0.1` only makes sense when connecting directly on the same machine or via a properly configured tunnel.

In Spring Boot applications, exporting Spring beans as MBeans may require enabling JMX settings and the corresponding exporter configuration. Do not assume every Spring bean appears automatically in JMC.

## 4. Connecting to a Local JVM with JMC

General workflow (menu names may vary by JMC version):

1. Start the Java or Spring Boot application and keep the process running.
2. Open Java Mission Control.
3. Locate **JVM Browser** and the list of local JVMs.
4. Select the right process based on main class, PID, or application name.
5. Open **JMX Console** for the selected JVM.
6. Go to the **MBean Browser** area or equivalent management tab.

Once connected, you will typically see MBean groups (domains) such as `java.lang`, `java.nio`, `com.sun.management` if supported by the JVM, and your application's own domain.

To confirm you selected the right JVM, inspect `java.lang:type=Runtime` (JVM name, start time, uptime if exposed) or `java.lang:type=Memory`. Avoid relying solely on the process name, as multiple instances of the same application may be running on the machine.

**Tip:** for short-lived JVMs, keep the application alive long enough to observe. Do not enable remote JMX mode just because the local browser does not show the process yet: check the local attach environment first.

## 5. How Does MBean Browser Organize Information?

In JMX, each MBean has an `ObjectName`:

```text
java.lang:type=Memory
java.lang:type=Threading
com.example.orders:type=Queue,name=PaymentQueue
```

JMC typically groups MBeans by **domain** and key properties. Tree layouts or filters may vary across versions, but the underlying source of truth is JMX metadata.

When selecting an MBean, the sections typically visible include:

- **Attributes:** state data that can be read or written.
- **Operations:** management methods that can be invoked.
- **Notifications:** event emission capabilities and where to register listeners if supported by the tool.
- **Metadata:** class name, description, signatures, data types, and information from `MBeanInfo`.

For example, with:

```text
com.example.orders:type=Queue,name=PaymentQueue
```

an MBean interface might expose:

```text
Attributes
  PendingCount          int       read-only
  Paused                boolean   read-write
  LastErrorCode         String    read-only

Operations
  clearCompleted()      void
  retryFailed(int max)  int

Notifications
  com.example.orders.queue.backlog
```

These entries appear only if the implementation and actual metadata expose them. JMC does not automatically infer that every public method on a class is a JMX operation.

## 6. Reading Attributes: Observing Current State

Attributes are the easiest information to observe in JMC. With the `java.lang:type=Memory` MBean, you can inspect attributes like `HeapMemoryUsage` or `NonHeapMemoryUsage`.

For example, `HeapMemoryUsage` is represented by a structured data type and usually displays these fields:

```text
init
used
committed
max
```

This value comes from `MemoryUsage` represented via MXBean/Open Data. Depending on JMC, you can expand the fields or view them as a table.

To read application data, inspect the application's domain and select the `PendingCount` or `Paused` attribute.

Distinction:

- **Read-only:** JMX allows reading, not writing through the MBean interface.
- **Read-write:** JMX allows both reading and writing; editing the value can affect the running system.
- **Write-only:** possible in terms of the contract, though rarely suitable for UI observation.

An attribute can be expensive to read. If a getter queries a database or performs heavy computation, continuous polling by JMC can create load. Prefer fast getters, small snapshots, and pre-updated statistics.

Complex structured attributes can be hard to render in UIs, especially with Standard MBeans exposing custom domain types. MXBeans/Open Data improve interoperability across JMX tools.

## 7. Operations: Administrative Actions Must Be Intentional

An operation can change application state, for example:

```text
retryFailed(maxCount=10)
clearCompleted()
pauseConsumer()
resetMetrics()
```

JMC typically lists operation names, parameters, and return types, and allows invocation when the client has permission and the tool supports it.

Before invoking an operation:

1. Verify `ObjectName` matches the right process/resource.
2. Read the operation description and parameters.
3. Confirm the impact and proper authorization.
4. Record the state before invoking, such as `PendingCount`.
5. Invoke operations only in permitted environments and observe the outcome.

In JMX, `MBeanOperationInfo.getImpact()` can report `INFO`, `ACTION`, `ACTION_INFO`, or `UNKNOWN`, but that is **descriptive metadata**, not a security mechanism. An operation like `resetMetrics()` still requires access control regardless of how the UI labels it.

Example of an operation taking an integer parameter:

```java
connection.invoke(
    new ObjectName("com.example.orders:type=Queue,name=PaymentQueue"),
    "retryFailed",
    new Object[] { 10 },
    new String[] { "int" }
);
```

JMC performs an equivalent call over the JMX connection when triggered in the UI. Parameter signatures must match the operation metadata.

## 8. Notifications: Observing Events from MBeans

An MBean can emit notifications if it implements `NotificationBroadcaster` or `NotificationEmitter`. `MBeanNotificationInfo` metadata indicates which notification types can be emitted, for example:

```text
com.example.orders.queue.backlog
com.example.orders.queue.paused
com.example.orders.queue.resumed
```

JMC or another JMX tool may allow registering a listener on the MBean and viewing received notifications. Specific screens and capabilities depend on the JMC version.

A notification typically contains:

- `type`: event type identifier.
- `source`: emitter source.
- `sequenceNumber`: sequence number managed by the emitter.
- `timeStamp`: time the event was created.
- `message`: description.
- `userData`: additional data, if any.

**Knowing "an MBean can emit notifications" does not mean events will immediately appear when you open the tab.** You must subscribe before the event is emitted; JMX notifications by default are not a replayable event history. Disconnecting or removing the listener can cause the client to miss notifications.

To debug, trigger the event in a test environment after the listener is attached, rather than looking for an event emitted in the past.

## 9. Java Example: An MBean Observable in JMC

The following example creates a Standard MBean named `QueueMonitor` and registers it in the platform MBeanServer. Nested public types allow the demo to live in a single file.

Save as `JmcJmxDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import javax.management.*;

public class JmcJmxDemo {
    public interface QueueMonitorMBean {
        int getPendingCount();
        boolean isPaused();
        void setPaused(boolean paused);
        void clear();
    }

    public static class QueueMonitor extends NotificationBroadcasterSupport
            implements QueueMonitorMBean {
        private volatile int pending = 42;
        private volatile boolean paused;
        private long sequence;

        @Override
        public int getPendingCount() {
            return pending;
        }

        @Override
        public boolean isPaused() {
            return paused;
        }

        @Override
        public void setPaused(boolean paused) {
            this.paused = paused;
        }

        @Override
        public void clear() {
            pending = 0;
            sendNotification(new Notification(
                "com.example.queue.cleared",
                this,
                ++sequence,
                System.currentTimeMillis(),
                "Queue was cleared"
            ));
        }

        @Override
        public MBeanNotificationInfo[] getNotificationInfo() {
            return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                    new String[] { "com.example.queue.cleared" },
                    Notification.class.getName(),
                    "Emitted when queue is cleared"
                )
            };
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.demo:type=Queue,name=Payments"
        );
        server.registerMBean(new QueueMonitor(), name);

        System.out.println("JMX object: " + name);
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Open JMC and connect to this JVM.");
        System.out.println("Press Ctrl+C to stop.");

        CountDownLatch forever = new CountDownLatch(1);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try {
                if (server.isRegistered(name)) {
                    server.unregisterMBean(name);
                }
            } catch (Exception ignored) {
                // JVM is shutting down
            }
        }));
        forever.await();
    }
}
```

Run:

```bash
javac JmcJmxDemo.java
java JmcJmxDemo
```

Then in JMC:

1. Select the `JmcJmxDemo` process using the printed PID.
2. Open JMX Console and navigate to MBean Browser.
3. Locate the `com.example.demo` domain and the MBean with `type=Queue,name=Payments`.
4. Read `PendingCount` (initially 42) and `Paused` (initially false).
5. Try editing `Paused` in the demo environment if the UI supports it.
6. Subscribe to the `com.example.queue.cleared` notification, then invoke the `clear` operation.
7. Verify `PendingCount` changes to 0 and the notification is emitted.

Not every JMC version uses the same tab names or interaction flow, but the JMX logic and `ObjectName` remain the same.

## 10. Observing MBeans Exported by Spring Framework

In a Spring application, you can mark a managed bean with annotations:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=OrderMonitor",
    description = "Order processing monitor"
)
public class OrderMonitor {
    private volatile boolean paused;

    @ManagedAttribute(description = "Number of pending orders")
    public int getPendingCount() {
        return 21;
    }

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedAttribute
    public void setPaused(boolean paused) {
        this.paused = paused;
    }

    @ManagedOperation(description = "Reset local statistics")
    public void resetStatistics() {
        // Reset counters
    }
}
```

`@ManagedResource` describes the MBean, `@ManagedAttribute` designates exposed attributes, and `@ManagedOperation` designates operations. The bean appears in JMC only when the **Spring JMX exporter is active and registers it successfully** on the MBeanServer that JMC is connected to.

For example, a Spring Framework application can use `@EnableMBeanExport`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfig {
}
```

Auto-export configuration in Spring Boot can vary by version and properties, so identify which MBean export mechanism is actually enabled in the application. Avoid creating multiple exporters registering duplicate `ObjectName`s.

Once JMC is connected to the right JVM, look for:

```text
com.example.orders:type=OrderMonitor
  Attributes
    PendingCount
    Paused
  Operations
    resetStatistics()
```

If it is missing, check the exporter, annotations, `ObjectName`, and registration error messages in the logs.

## 11. JMX Console: Viewing Graphs and Tracking Trends

JMC includes views that support charting or monitoring values over time. Depending on the version, users can add numeric attributes to graphs, monitor JVM state, and compare fluctuations.

A practical scenario:

- Track `HeapMemoryUsage.used` to observe heap consumption.
- Track `ThreadCount` in `java.lang:type=Threading`.
- Track `com.example.orders:type=OrderMonitor` / `PendingCount`.
- When the queue grows rapidly, also inspect GC activity or JVM CPU usage.

Do not confuse polled metrics in JMX Console with durable historical data. Live graphs typically reflect only the window while the client is connected and collecting. If you need long-term monitoring, alerting, or retention, deploy a dedicated metrics system; JMC is primarily for interactive exploration and diagnosis.

An expensive JMX getter that computes on poll can add load to the application. Watch the cost of attributes before configuring a high sampling frequency.

## 12. How Does Java Flight Recorder Complement JMX?

JFR records JVM and application events for performance root-cause analysis. Depending on the JDK and configuration, recordings can be started directly via JMC or via `jcmd`:

```bash
jcmd <PID> JFR.start name=diagnostic settings=profile duration=60s filename=diagnostic.jfr
```

Replace `<PID>` with the actual PID of the JVM. Permissions and an environment supporting attach/JFR are required. Options and events may vary across JDK versions; check `jcmd <PID> help JFR.start` when needed.

In JMC, open the `.jfr` file to analyze categories such as CPU, memory allocation, GC, threads, locks, or I/O if collected in the recording.

Example investigation sequence:

1. Use MBean Browser to see `PendingCount` rising and `Paused=false`.
2. Use JMX Console to check current thread count and heap usage.
3. Create a JFR recording during the incident window.
4. Analyze thread states or blocking in JFR to identify the bottleneck.
5. Return to JMX to verify application changes after applying the fix.

These are two complementary layers of data: **JMX answers "what is the state and control surface right now?"; JFR answers "what has the JVM been doing over the recent interval?"**. Not every JMX metric automatically appears in a JFR file, and not every JFR event becomes an MBean attribute.

## 13. Common Errors When Using JMC

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| JVM does not appear in local JVM Browser | Different user, container namespace, missing attach permission, or process exited | Check PID, user running JVM, attach support, and JDK/JMC |
| Cannot connect to remote JMX | Wrong host/port, firewall, unreachable RMI hostname/port | Check management endpoint and network path |
| Connection rejected due to authentication/TLS | Mismatched security configuration | Confirm credentials, certificate, and protocol |
| Spring MBeans not visible | Exporter disabled, bean not exported, different domain name, registration failed | Check `MBeanExporter`, annotations, ObjectName, and logs |
| MBean visible but missing attribute/operation | Metadata only partially exposed, unexpected proxy/interface | Inspect `MBeanInfo`, check MBean contract and exporter |
| Attribute throws error when read | Getter throws exception, hard-to-handle data type, MBean unregistered | Check logs, signature, and lifecycle |
| Operation fails | Wrong arguments, insufficient permissions, business error | Verify signature and exception cause |
| Notifications do not appear | Listener not registered or event not emitted yet | Attach listener before triggering event |
| Graphs disappear after disconnect | Live data was not persisted as durable history | Use metrics storage or JFR recordings where appropriate |

If `InstanceNotFoundException` is reported, the MBean may have disappeared or the JVM/endpoint is no longer the right one. For `NotCompliantMBeanException` during registration, check the Standard MBean/MXBean interface, proxies, metadata, or exposed data types.

## 14. Permissions and Safety in JMX Administration

JMX can allow modifying configuration, clearing caches, resetting metrics, pausing processing, or invoking operations with business impact. Therefore:

- Restrict JMX access to authorized operators or operational systems.
- For remote JMX, use authentication, TLS, and network restrictions as appropriate; never expose management ports to the public Internet.
- Avoid exposing secrets, access tokens, passwords, or personal data via attributes, notifications, and operation results.
- Validate operation parameters; do not treat JMX Console as a security boundary.
- In production, execute state-changing operations only under an established operational procedure.
- Avoid oversized attributes and blocking getters; a JMX client may poll frequently.
- Keep the JMC client and JMX server decoupled; when the client disconnects, the application JVM continues running normally unless otherwise affected.

## 15. Practice Exercises

1. Run `JmcJmxDemo` and connect locally with JMC. Record the domain name, `ObjectName`, and readable attributes.
2. Invoke `clear()` after registering a notification listener. Record `PendingCount` and the notification.
3. Export `OrderMonitor` via Spring JMX and compare its UI presentation with the pure Java Standard MBean.
4. Find `java.lang:type=Memory` and `java.lang:type=Threading`. Pick two suitable attributes to monitor under increasing load.
5. Capture a 60-second JFR recording while the application is working and compare the purpose of JFR data with live JMX attributes.
6. Describe possible causes if JMC shows `java.lang` but not the application domain; list where to check in Spring.

## 16. Self-Check Questions

- How does Java Mission Control use JMX Console and Java Flight Recorder for different tasks?
- How does `ObjectName` help you locate the right MBean?
- Why might a Spring bean annotated with `@ManagedResource` still not appear in MBean Browser?
- Why should you not invoke state-changing operations in production just to test the UI?
- How does `MBeanNotificationInfo` metadata differ from having received a notification?
- If remote JMX connects to the registry port but the client still fails, which RMI factor should you check?
- When trying to find the cause of a CPU spike over time, should you use JFR or only inspect attributes in JMX Console?

**Key takeaway:** JMC helps explore and manage a JVM over JMX using JMX Console/MBean Browser while also analyzing performance over time with JFR. With Spring Framework, only MBeans that are successfully exported and registered appear in JMC. Observe attributes to understand state, think carefully before invoking operations, and use JFR when tracking down performance root causes.