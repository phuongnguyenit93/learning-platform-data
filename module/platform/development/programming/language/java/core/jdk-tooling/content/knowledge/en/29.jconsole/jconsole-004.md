# MBeans in JConsole

## 1. What is an MBean?

An **MBean (Managed Bean)** is a Java object exposed through Java Management Extensions (JMX) so that a management tool can monitor or control an application resource or a JVM resource.

An MBean typically represents a manageable component:

- Cache: maximum capacity, entry count, cache clear operation.
- Connection pool: open connection count, connection limit, pool check or close operation.
- Worker service: queued job count, active worker count, pause or resume operation.
- Application configuration: current configuration values, save or reload operation.
- JVM: memory, threads, garbage collector, class loading, and runtime information.

An MBean is not just an ordinary JavaBean. It has a **management interface** that JMX exposes to management tools. This interface describes typed attributes, invocable operations, and notifications that the MBean can emit.

JConsole uses JMX to display the MBeans registered in an MBean Server. The **MBeans** tab lets you inspect information, read/write attributes, invoke operations, and subscribe to notifications.

## 2. What Components Does an MBean Provide?

A management interface typically has three groups:

| Component | Meaning | Example |
|---|---|---|
| Attribute | Named and typed value; can be read-only or read/write | `CacheSize`, `EntryCount`, `Enabled` |
| Operation | Action that a client can invoke | `clear()`, `reload()`, `resetStatistics()` |
| Notification | Event sent by an MBean to subscribed clients | Cache cleared, configuration changed, threshold exceeded |

Cache example:

- `CacheSize`: configured maximum number of entries.
- `EntryCount`: current number of entries, read-only.
- `addEntries(int count)`: adds test data to the cache.
- `clear()`: removes all entries.
- `com.example.cache.cleared`: notification emitted after the cache is cleared.

Attributes differ from operations. An attribute represents the state or configuration of a resource; an operation is a requested action to perform. An attribute setter can change application state, so attribute writes also need to be controlled.

## 3. JMX, MBean Server, and ObjectName

JMX is the management mechanism. An MBean is the managed object. An MBean Server is where MBeans are registered and accessed.

A Java SE JVM has a **platform MBean Server**, accessed via:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
```

Components in the same JVM can register application MBeans with this server. As a result, JConsole and JMX clients can discover both platform MXBeans and application-created MBeans.

Each MBean in an MBean Server has a unique name of type `ObjectName`. General structure:

```text
domain:key=value,key2=value2
```

Example:

```text
com.example:type=CacheControl,name=primary
```

In this example:

- `com.example` is the domain, commonly used to group an application's MBeans.
- `type=CacheControl` identifies the resource type.
- `name=primary` distinguishes the specific instance.

ObjectName properties act as a key/value set in JMX; key order does not change the identity. However, JConsole uses key order to build the MBean display tree. Keep a consistent order, usually placing `type` before `name`, so the tree stays easy to read.

An MBean is registered using `registerMBean`:

```java
ObjectName name =
    new ObjectName("com.example:type=CacheControl,name=primary");

server.registerMBean(new CacheControl(), name);
```

If the name is already in use in the same MBean Server, registration fails with `InstanceAlreadyExistsException`. Choose a unique ObjectName for each instance.

## 4. Common MBean Types

Java JMX supports several MBean types:

| Type | Characteristics | When to Use |
|---|---|---|
| Standard MBean | Management interface defined by naming convention and getters/setters | Simple way to expose a Java component |
| MXBean | Maps data types to Open Types so clients can understand them without custom domain classes | Management data needs strong compatibility with remote clients |
| Dynamic MBean | Provides `MBeanInfo` itself and handles attributes/operations at runtime | Management interface changes dynamically or is configured at runtime |
| Model MBean | Flexible MBean type, commonly used in management frameworks | Management systems with complex metadata and behavior |

### 4.1. Standard MBean

This type is well suited for learning examples. If the implementation class is named `CacheControl`, the management interface must by convention be named `CacheControlMBean` and reside in the same package as the implementation class.

Getters/setters are recognized as attributes:

- `getCacheSize()` and `setCacheSize(int)` create a read/write `CacheSize` attribute.
- `getEntryCount()` creates a read-only `EntryCount` attribute.
- Other methods such as `clear()` and `addEntries(int)` become operations.

The interface must publicly declare the methods to be managed. Only methods declared in the management interface are exposed under the Standard MBean convention.

### 4.2. MXBean

An MXBean has the `MXBean` suffix or is annotated with `@MXBean`. MXBeans map supported Java types to Open Types, allowing remote JMX clients to read data without needing to load the application's custom domain classes.

All JVM platform MBeans are MXBeans. That is why when you open the MBeans tab, you typically see entries such as Memory, Threading, Runtime, and GarbageCollector.

### 4.3. Dynamic MBean

A Dynamic MBean implements `DynamicMBean` and describes its interface at runtime through `MBeanInfo`. This is useful when the list of attributes or operations is only known when the application runs, such as configurations loaded from a file or plugin.

## 5. Built-in JVM Platform MXBeans

The JVM already exposes many MXBeans without requiring you to write custom MBeans. Some common ObjectNames:

| ObjectName | Purpose |
|---|---|
| `java.lang:type=Memory` | Heap and non-heap memory |
| `java.lang:type=Threading` | Thread count, thread info, deadlock detection |
| `java.lang:type=Runtime` | Uptime, VM name, input arguments |
| `java.lang:type=ClassLoading` | Loaded and unloaded class counts |
| `java.lang:type=OperatingSystem` | Operating system and process information |
| `java.lang:type=GarbageCollector,name=...` | GC collection count and time |
| `java.lang:type=MemoryPool,name=...` | Usage for each memory pool |
| `java.lang:type=Compilation` | JIT compilation information when supported by the JVM |

Collector and memory pool names depend on the JVM, GC, and Java version. Do not assume every machine has the exact same list.

A few useful examples in JConsole:

- **Memory**: inspect `HeapMemoryUsage`, `NonHeapMemoryUsage`, `ObjectPendingFinalizationCount`; some attributes can be modified.
- **Threading**: inspect thread counts, retrieve stack information, and invoke deadlock detection operations.
- **GarbageCollector**: inspect `CollectionCount` and `CollectionTime`.
- **ClassLoading**: monitor the number of loaded classes.
- **Runtime**: inspect `Uptime`, `VmName`, `VmVersion`, and VM input arguments.

HotSpot also provides the `HotSpotDiagnostic` MXBean, which allows invoking operations such as `dumpHeap` or changing certain VM options. These operations affect the process and the filesystem; only run them when you understand their impact and have appropriate permissions.

## 6. Starting JConsole and Connecting to a JVM

JConsole is located in the JDK's `bin` directory. Check the tool and version:

```bash
java -version
jconsole -?
```

### 6.1. Local Connection

Start the Java application first, then open JConsole:

```bash
jconsole
```

In the connection dialog:

1. Select the **Local Process** tab or list.
2. Locate the application's JVM by PID, class name, or startup arguments.
3. Select the process to monitor.
4. Click **Connect**.
5. Select **MBeans** to view the registered MBeans.

You can pass the PID directly:

```bash
jconsole <PID>
```

Local connections rely on operating system permissions. JConsole and the target JVM must run under the same user. With modern Java SE, JConsole can attach and start the management agent on demand if the JVM supports the Attach API and system policy permits it.

If the process does not appear or cannot be selected, check the PID, user, permissions, temporary filesystem, and JVM attach capability. Not every process named Java supports attach.

### 6.2. Remote Connection

Remote connections require enabling the JMX agent on the target JVM and configuring ports. Illustrative example:

```bash
java \
  -Dcom.sun.management.jmxremote.port=7091 \
  -Dcom.sun.management.jmxremote.rmi.port=7092 \
  -Djava.rmi.server.hostname=monitor.example.internal \
  -jar application.jar
```

Replace the values in this example with unused ports and a hostname/IP reachable from the machine running JConsole. Fixing both ports makes firewall configuration easier for the RMI registry and connector. `java.rmi.server.hostname` must point to an address that clients can connect to.

On the management machine, open JConsole:

```bash
jconsole monitor.example.internal:7091
```

Enter credentials if the agent requires authentication. Remote JMX uses RMI; network, DNS, firewall, and certificate configurations must allow both the registry connection and the RMI connector.

Remote JMX can allow both reading information and controlling the application. Do not expose the port to the Internet or untrusted networks.

## 7. Reading the MBeans Tab in JConsole

After connecting, JConsole provides main tabs such as Overview, Memory, Threads, Classes, VM, and MBeans. Each tab presents a different view; the MBeans tab provides access to the general management interface of the MBean Server.

In the **MBeans** tab:

- The left tree lists MBeans by domain and ObjectName.
- Selecting an MBean displays its `MBeanInfo` metadata and Descriptor.
- Sub-nodes typically include Attributes, Operations, and Notifications.
- Selecting each item shows its value, data type, description, and corresponding access permissions.

### 7.1. Viewing Attributes

Select an MBean and expand the **Attributes** node.

JConsole lists the attributes and their current values. When you select an attribute, the right pane displays its value, type, and metadata.

Some attributes are read/write, while others are read-only. For example:

| Attribute | Typical Access | Meaning |
|---|---|---|
| `CacheSize` | Read/Write | Maximum number of entries |
| `EntryCount` | Read-only | Current number of entries |
| `HeapMemoryUsage` | Read-only | Heap usage details |
| `Uptime` | Read-only | How long the JVM has been running |

Numeric attributes can be opened as charts in JConsole where supported by the UI. Values may change with each refresh cycle or as the application runs.

Only modify an attribute when you clearly understand what its setter does. For example, reducing `CacheSize` might cause the application to evict entries or change cache behavior.

### 7.2. Invoking Operations

Expand the **Operations** node to see the methods exposed by the MBean. Select an operation to view its description, parameters, and invoke button.

Examples:

- `clear()` clears cache data.
- `addEntries(int count)` adds a specified number of test entries.
- `findDeadlockedThreads()` checks for deadlocks on the Threading MXBean.
- `dumpHeap(...)` asks the JVM to generate a heap dump on the HotSpotDiagnostic MXBean.

When invoking an operation with parameters, enter values matching the displayed types and click the execute button. The return value is displayed in the UI if the operation returns a result.

Operations can mutate application state, consume CPU, write large files, or increase pause times. Read the description and verify the impact before invoking them in production.

### 7.3. Receiving Notifications

If an MBean supports notifications, expand the **Notifications** node and click **Subscribe**.

After subscribing, JConsole displays received notifications and the event count. Select individual notification types to view metadata.

Notifications are useful for events that occur over time, such as:

- Cache cleared.
- Configuration changed.
- Memory usage crossed a threshold.
- A component changed state.

An MBean that emits notifications must support `NotificationBroadcaster` or `NotificationEmitter` and expose notification metadata. If the MBean does not support notifications, the Notifications node may not appear or may have no events to subscribe to.

## 8. Creating a Simple Standard MBean for an Application

The example below creates a cache management MBean. It has two attributes, two operations, and emits notifications when the cache size changes or the cache is cleared.

Create three files in the same directory.

### 8.1. CacheControlMBean.java

```java
public interface CacheControlMBean {
    int getCacheSize();

    void setCacheSize(int size);

    int getEntryCount();

    void addEntries(int count);

    void clear();
}
```

`CacheSize` is a read/write attribute, and `EntryCount` is a read-only attribute. `addEntries` and `clear` are operations.

### 8.2. CacheControl.java

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class CacheControl extends NotificationBroadcasterSupport
        implements CacheControlMBean {

    private final AtomicInteger cacheSize = new AtomicInteger(1000);
    private final AtomicInteger entryCount = new AtomicInteger();
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public int getCacheSize() {
        return cacheSize.get();
    }

    @Override
    public void setCacheSize(int size) {
        if (size < 1) {
            throw new IllegalArgumentException("size must be positive");
        }

        int previous = cacheSize.getAndSet(size);
        entryCount.updateAndGet(current -> Math.min(current, size));

        if (previous != size) {
            sendNotification(new Notification(
                "com.example.cache.size.changed",
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Cache size changed from " + previous + " to " + size
            ));
        }
    }

    @Override
    public int getEntryCount() {
        return entryCount.get();
    }

    @Override
    public void addEntries(int count) {
        if (count < 0) {
            throw new IllegalArgumentException("count must not be negative");
        }

        entryCount.updateAndGet(current ->
            (int) Math.min(cacheSize.get(), (long) current + count)
        );
    }

    @Override
    public void clear() {
        int previous = entryCount.getAndSet(0);

        sendNotification(new Notification(
            "com.example.cache.cleared",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Cache cleared; removed " + previous + " entries"
        ));
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {
            "com.example.cache.size.changed",
            "com.example.cache.cleared"
        };

        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                Notification.class.getName(),
                "Cache configuration and content events"
            )
        };
    }
}
```

`NotificationBroadcasterSupport` provides the notification-sending mechanism. `getNotificationInfo()` describes the event types so JConsole knows which notifications the MBean can emit.

### 8.3. MBeanDemo.java

```java
import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class MBeanDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example:type=CacheControl,name=primary"
        );

        server.registerMBean(new CacheControl(), name);

        System.out.println("Registered MBean: " + name);
        System.out.println("READY");

        new CountDownLatch(1).await();
    }
}
```

The program registers the MBean with the platform MBean Server and then waits so JConsole has time to connect. Stop the program with Ctrl+C in the terminal when you finish practicing.

### 8.4. Compiling and Running

Use JDK 17 or later:

```bash
javac CacheControlMBean.java CacheControl.java MBeanDemo.java
java MBeanDemo
```

Stdout:

```text
Registered MBean: com.example:type=CacheControl,name=primary
READY
```

Keep this terminal open. Open another terminal and run:

```bash
jconsole
```

Select the `MBeanDemo` process, click Connect, and open the MBeans tab.

### 8.5. Practicing on the MBeans Tab

In the MBeans tree, find the `com.example` domain and select `CacheControl` with the `primary` instance.

**Try attributes:**

1. Open Attributes.
2. Read `CacheSize`; the initial value is `1000`.
3. Read `EntryCount`; the initial value is `0`.
4. Change `CacheSize` to `250`.
5. Read `CacheSize` again to confirm the setter was invoked.

**Try operations:**

1. Open Operations.
2. Select `addEntries`.
3. Enter `40` for the `count` parameter and invoke the operation.
4. Read `EntryCount`; the expected result is `40`.
5. Invoke `clear()`.
6. Read `EntryCount` again; the expected result is `0`.

**Try notifications:**

1. Open Notifications.
2. Click Subscribe.
3. Invoke `addEntries` or change `CacheSize`.
4. Invoke `clear()`.
5. Observe the `com.example.cache.size.changed` or `com.example.cache.cleared` notification.

This example illustrates the relationship between a Java object, its management interface, the MBean Server, and JConsole: UI actions are translated into JMX calls to the running MBean.

## 9. Registering and Unregistering MBeans in an Application

Applications typically register MBeans during initialization and unregister them when the component stops.

Unregistration example:

```java
if (server.isRegistered(name)) {
    server.unregisterMBean(name);
}
```

You can implement `MBeanRegistration` to receive callbacks before/after registration or unregistration. This is useful when an MBean needs to prepare resources or clean up listeners.

If registering multiple instances, assign distinct ObjectNames, such as `name=primary` and `name=secondary`. Do not reuse the same ObjectName for two MBeans in a single MBean Server.

## 10. Security When Using MBeans and JConsole

JMX can grant both read access to data and permission to invoke operations and modify attributes. Therefore, JMX access must be treated as application administrative access.

### Local monitoring

- Run JConsole under an account appropriate for the target process.
- Do not share host access beyond what is necessary.
- JConsole consumes resources; consider its impact when using it in production.

### Remote monitoring

- Enable remote JMX with authentication and TLS.
- Allow connections only from approved management networks or hosts.
- Configure firewall rules for the exact RMI registry and connector ports.
- Configure a hostname/IP reachable by clients.
- Use certificates and authentication mechanisms aligned with your organization's policy.
- Grant read-only permissions to users who only need to observe; grant read/write only to those who genuinely need control.
- Protect password/access files with strict file permissions. Plaintext password files are only suitable for development environments; production should use secure authentication such as SSL client certificates combined with passwords or JAAS/LDAP according to operational guidelines.

Do not disable authentication or SSL just to make connections easier in production. Do not expose JMX ports to the Internet. Remote JMX allows invoking MBean operations, so anyone with control access can alter application state.

## 11. Common Issues When Working with MBeans

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Custom MBean not visible in the tree | Not registered, registered to a different MBean Server, or process running an older build | Check `registerMBean`, ObjectName, and startup logs |
| `NotCompliantMBeanException` | Interface naming convention mismatch, invalid interface, or method not following pattern | Verify class `Foo` implements a valid `FooMBean` interface |
| `InstanceAlreadyExistsException` | ObjectName already registered in the same server | Choose a unique instance name or unregister the previous instance |
| Attribute not editable | No setter or attribute exposed as read-only | Check the management interface and setter |
| Operation not appearing | Method not declared in the management interface | Add the method to the management interface and rebuild |
| Notifications not visible | MBean does not support broadcaster/emitter or omits notification metadata | Extend `NotificationBroadcasterSupport` and implement `getNotificationInfo()` |
| Unable to connect to local process | Different user, attach permissions, or JVM does not support attach | Check PID, user, and Attach API policy |
| Remote connection timeout | Wrong host/port, firewall, or RMI connector using a different port | Check both the registry port and the RMI connector port |
| Remote authentication failed | Wrong password/access file, certificate, or truststore | Check authentication and TLS configuration on both client and server |
| JConsole sees MBean but operation fails | Operation throws an exception or parameter value is invalid | Read the returned error and check validation logic in the MBean |

## 12. Principles for Good MBean Design

- **Clear naming:** use domains and ObjectNames that reflect the component, type, and instance.
- **Lightweight attributes:** getters should return quickly without running large queries or slow I/O.
- **Intentional operations:** expose only actions needed for administration; clearly describe their impact.
- **Stable data types:** prefer primitives, `String`, enums, and types that map cleanly over JMX.
- **Thread-safe:** JConsole and other clients can read/write concurrently with the application.
- **Selective notifications:** emit meaningful events and avoid flooding with excessive notifications.
- **No exposed secrets:** never expose passwords, tokens, secrets, personal data, or sensitive configuration.
- **Separate monitoring and control:** observers should get read-only access; state-changing operations require higher privileges.
- **Impact control:** operations such as heap dumps, GC, VM option changes, or config reloads should be evaluated before invocation.

## 13. Summary

An MBean is the management interface of a Java resource exposed via JMX. In JConsole, the MBeans tab displays registered MBeans and lets you work with attributes, operations, and notifications.

Key points to remember:

- An MBean represents an application resource or JVM component.
- Attributes describe state/configuration; operations perform actions; notifications report events.
- MBeans must be registered in an MBean Server with a unique ObjectName.
- Standard MBeans use an interface following the `ClassNameMBean` convention.
- MXBeans provide data types suitable for remote JMX clients.
- Platform MXBeans provide built-in Memory, Threading, Runtime, ClassLoading, and GC information.
- JConsole uses the MBeans tab to view and edit attributes, invoke operations, and subscribe to notifications.
- Remote JMX must be secured with authentication, TLS, authorization, and network restrictions.
- Only invoke impactful operations when you clearly understand their effect on the application.

**Official references:**

- [Oracle Java SE 24 — Using JConsole](https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html)
- [Oracle Java SE 24 — Overview of Java SE Monitoring and Management](https://docs.oracle.com/en/java/javase/24/management/overview-java-se-monitoring-and-management.html)
- [Oracle Java SE 24 — Monitoring and Management Using JMX Technology](https://docs.oracle.com/en/java/javase/24/management/monitoring-and-management-using-jmx-technology.html)
- [Oracle Java SE 24 — StandardMBean API](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/javax/management/StandardMBean.html)
- [Oracle Java SE 24 — JMX Security](https://docs.oracle.com/en/java/javase/24/jmx/security.html)