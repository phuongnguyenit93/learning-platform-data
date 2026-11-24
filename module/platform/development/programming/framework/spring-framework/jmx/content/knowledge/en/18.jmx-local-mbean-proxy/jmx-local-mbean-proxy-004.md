# Local MBeanServerConnection and Proxy Calls in Spring Framework JMX

## 1. The problem: same JVM still needs a clear management interface

Once a Java object has been registered as an MBean in JMX, the caller does not have to hold a direct reference to the original object. Instead, it can work through an `MBeanServerConnection` and an `ObjectName`. This applies even when the caller and the MBean **reside in the same JVM**.

Suppose a Spring application has a `QueueManager` processing a queue. Another component wants to read the pending task count or request pausing the consumer. There are at least three ways:

1. Inject `QueueManager` and call Java methods directly.
2. Locate the MBean in `MBeanServer` and use `getAttribute`/`setAttribute`/`invoke`.
3. Create a **JMX proxy** implementing the management interface and call Java methods on the proxy, letting the proxy translate calls into JMX operation/attribute accesses.

The third approach is typically the focus of **local MBean proxies** in Spring Framework. It gives caller code strong typing and reduces repetition of attribute/operation name strings while still going through the registered management contract.

```text
   Spring caller bean
         |
         | orderMonitor.getProcessedCount()
         v
   JMX management proxy
         |
         | getAttribute(ObjectName, "ProcessedCount")
         v
   MBeanServerConnection (local)
         |
         v
   MBeanServer
         |
         | route by ObjectName
         v
   Registered MBean / ModelMBean
         |
         v
   Application object
```

**Key point:** “local” describes the connection path to an MBeanServer in the same JVM, not that the proxy calls target methods directly. The JMX surface, metadata, type rules, and management exceptions still apply.

## 2. What is MBeanServerConnection?

`javax.management.MBeanServerConnection` is the management access interface for an MBeanServer. It defines common operations:

| Method | Role |
|---|---|
| `getAttribute(ObjectName, String)` | Read an attribute |
| `setAttribute(ObjectName, Attribute)` | Write an attribute |
| `getAttributes(...)` / `setAttributes(...)` | Read/write a set of attributes |
| `invoke(ObjectName, String, Object[], String[])` | Invoke an operation |
| `getMBeanInfo(ObjectName)` | Read attribute, operation, and notification metadata |
| `queryNames(...)` | Find registered ObjectNames |
| `isRegistered(ObjectName)` | Check whether an MBean still exists |
| `addNotificationListener(...)` | Subscribe to notifications |
| `removeNotificationListener(...)` | Remove a listener registration |

`javax.management.MBeanServer` **extends `MBeanServerConnection`**, while also adding local registry capabilities such as registering MBeans directly. Therefore you can assign:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
MBeanServerConnection connection = server;
```

This is a completely valid local `MBeanServerConnection`. No `JMXConnector`, host, port, or RMI is needed if the application only uses the same `MBeanServer` inside the JVM.

With remote connections, `JMXConnector.getMBeanServerConnection()` returns an object with the same interface; calls then may cross the network and introduce serialization, authentication, latency, and timeout concerns.

A useful mental model is:

```text
MBeanServerConnection = client contract
MBeanServer           = server/registry in the JVM
JMXConnector          = bridge when remote access is needed
ObjectName            = logical address of the MBean in the registry
```

## 3. ObjectName identifies the MBean, not the Java bean name

Each MBean in an `MBeanServer` is identified by a `javax.management.ObjectName`:

```text
demo.queue:type=QueueMonitor,name=orders
```

Where:

- `demo.queue` is the domain.
- `type=QueueMonitor` and `name=orders` are key properties.
- The entire ObjectName is the full identifier for clients calling `getAttribute` or `invoke`.

An ObjectName is distinct from a Spring bean name:

```text
Spring bean name : queueMonitor
JMX ObjectName   : demo.queue:type=QueueMonitor,name=orders
Java class       : com.example.QueueMonitor
```

They may be linked via exporter configuration, but are **not automatically identical**.

When the target MBean is not yet registered, a proxy may still be created in some configurations, yet actual calls will fail because the `ObjectName` is missing from the registry. Conversely, a valid ObjectName does not prove the proxy's management interface matches the actual metadata.

## 4. Java SE example: Standard MBean before using Spring

We begin with a simple Standard MBean, without Spring, to see the flow clearly.

### 4.1. Management interface

File `QueueMonitorMBean.java`:

```java
public interface QueueMonitorMBean {
    long getProcessedCount();
    int getWarningThreshold();
    void setWarningThreshold(int threshold);
    void resetStatistics();
}
```

Meaning:

- `ProcessedCount` is a read-only attribute.
- `WarningThreshold` is a read-write attribute.
- `resetStatistics()` is a JMX operation.

### 4.2. Target implementation

File `QueueMonitor.java`:

```java
import java.util.concurrent.atomic.AtomicLong;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicLong processedCount = new AtomicLong();
    private volatile int warningThreshold = 100;

    public void recordProcessed() {
        processedCount.incrementAndGet();
    }

    @Override
    public long getProcessedCount() {
        return processedCount.get();
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int threshold) {
        if (threshold < 1 || threshold > 1000) {
            throw new IllegalArgumentException(
                "threshold must be between 1 and 1000"
            );
        }
        warningThreshold = threshold;
    }

    @Override
    public void resetStatistics() {
        processedCount.set(0L);
    }
}
```

The class implements the interface following the Standard MBean convention; `recordProcessed()` is not in the management interface, so it is not a JMX operation of this Standard MBean.

### 4.3. Registering in the platform MBeanServer

File `Main.java`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public class Main {
    public static void main(String[] args) throws Exception {
        QueueMonitor monitor = new QueueMonitor();
        monitor.recordProcessed();
        monitor.recordProcessed();

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "demo.queue:type=QueueMonitor,name=orders"
        );
        server.registerMBean(monitor, name);

        MBeanServerConnection connection = server;

        System.out.println(
            "Raw count = " +
            connection.getAttribute(name, "ProcessedCount")
        );

        // Subsequent sections can be placed here.
    }
}
```

Even though the target and caller are in the same `main` method, `connection.getAttribute` still goes through the JMX API, ObjectName, and MBean metadata. It is not a regular `monitor.getProcessedCount()`.

## 5. Manual call path: getAttribute, setAttribute, and invoke

When using `MBeanServerConnection` directly, the client must know attribute/operation names and parameter signatures.

```java
long count = (Long) connection.getAttribute(
    name, "ProcessedCount"
);

connection.setAttribute(
    name,
    new javax.management.Attribute(
        "WarningThreshold",
        150
    )
);

Object current = connection.getAttribute(
    name, "WarningThreshold"
);

connection.invoke(
    name,
    "resetStatistics",
    new Object[0],
    new String[0]
);
```

For operations with parameters, `invoke` requires two parallel arrays:

```java
connection.invoke(
    name,
    "setProcessingMode",
    new Object[]{"PAUSED"},
    new String[]{String.class.getName()}
);
```

The `setProcessingMode` example is illustrative only: it must be exported as a corresponding operation for the command to run. For an attribute setter, `setAttribute` is normally used rather than calling `invoke("setWarningThreshold", ...)` and assuming their contracts are equivalent.

**Drawbacks of the manual approach:** the client contains strings like `"ProcessedCount"` and `"WarningThreshold"`, must cast return types, supply signatures manually, and convert data manually when needed.

These drawbacks are a major motivation for using a proxy.

## 6. Java JMX proxy: typed client-side API

The JDK provides:

```java
javax.management.JMX.newMBeanProxy(
    connection,
    name,
    QueueMonitorMBean.class
);
```

Full example:

```java
QueueMonitorMBean proxy =
    javax.management.JMX.newMBeanProxy(
        connection,
        name,
        QueueMonitorMBean.class
    );

long count = proxy.getProcessedCount();
proxy.setWarningThreshold(180);
int threshold = proxy.getWarningThreshold();
proxy.resetStatistics();
```

Caller code looks like normal Java calls, yet the `proxy` object is a stand-in for the MBean. The calls above are translated into JMX attribute accesses and operation invocations.

Comparison:

```text
Raw API:
  connection.getAttribute(name, "ProcessedCount")

Typed proxy:
  proxy.getProcessedCount()
```

**A proxy is not the target object.** A change made through the proxy affects the target MBean in the MBeanServer; the caller does not necessarily hold a direct reference to the implementation.

### 6.1. Standard MBean proxy and MXBean proxy

The JDK distinguishes proxies for Standard MBeans and MXBeans:

```java
QueueMonitorMBean standard =
    JMX.newMBeanProxy(connection, name, QueueMonitorMBean.class);
```

With an MXBean:

```java
MemoryMXBean memory =
    JMX.newMXBeanProxy(
        connection,
        new ObjectName("java.lang:type=Memory"),
        MemoryMXBean.class
    );
```

Corresponding imports include `javax.management.JMX` and `java.lang.management.MemoryMXBean`. MXBeans have a mapping mechanism between Java interface types and OpenData; do not use `newMBeanProxy` in place of `newMXBeanProxy` and expect custom DTOs to be converted by the same rules.

## 7. Spring JMX proxy: MBeanProxyFactoryBean

Spring Framework provides `org.springframework.jmx.access.MBeanProxyFactoryBean`, a `FactoryBean` that can create a proxy to an MBean identified by an ObjectName and a management interface.

Example:

```java
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class ProxyConfiguration {

    @Bean
    public MBeanProxyFactoryBean queueMonitorProxy(
            MBeanServer mbeanServer) {

        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(mbeanServer);
        factory.setObjectName(
            "demo.queue:type=QueueMonitor,name=orders"
        );
        factory.setProxyInterface(QueueMonitorMBean.class);

        return factory;
    }
}
```

A dependent bean can inject the interface:

```java
import org.springframework.stereotype.Service;

@Service
public class QueueDashboard {
    private final QueueMonitorMBean monitor;

    public QueueDashboard(QueueMonitorMBean monitor) {
        this.monitor = monitor;
    }

    public String summary() {
        return "Processed=" + monitor.getProcessedCount()
            + ", threshold=" + monitor.getWarningThreshold();
    }
}
```

With proper proxy factory configuration, Spring supplies an object implementing `QueueMonitorMBean` to inject into the dashboard; calls to it go through JMX.

**Wiring note:** if the context also contains the target `QueueMonitor` implementing `QueueMonitorMBean`, injection by type alone may be ambiguous. Use `@Qualifier` or a distinct bean name to select the proxy instead of the target.

### 7.1. MBeanProxyFactoryBean is not MBeanExporter

The two components address opposite sides:

| Component | Responsibility | Flow |
|---|---|---|
| `MBeanExporter` | Register a Spring bean as an MBean | Spring bean → JMX registry |
| `MBeanProxyFactoryBean` | Create a client proxy for a registered MBean | Spring caller → JMX registry |
| `MBeanServer` | Holds registrations | Registry/server |
| `MBeanServerConnection` | JMX operation contract | Client API |

Creating a proxy does not automatically register the target. Conversely, exporting an MBean does not automatically create an injectable client proxy for every bean.

In many Spring applications, both components may appear together, but bean creation timing and ObjectNames must be managed to prevent the proxy from making calls before the target is registered.

## 8. MBeanClientInterceptor: the mechanism behind the proxy

Spring has `MBeanClientInterceptor` in the `org.springframework.jmx.access` package. It translates calls on the proxy into operations against a JMX `MBeanServerConnection`.

You usually do not need to call the interceptor yourself. `MBeanProxyFactoryBean` provides a convenient `FactoryBean` wrapper to produce a proxy with a management interface. Still, understanding the interceptor helps explain behaviors such as:

- Getter calls are translated to `getAttribute`.
- Setter calls are translated to `setAttribute`.
- Remaining management methods are handled as operations.
- Exceptions related to MBeanServer, ObjectName, or metadata can occur during invocation.
- If a remote connection is needed, the interceptor/proxy needs appropriate connector configuration.

A JMX proxy is an **adapter for a management contract**, not an AOP bean fully representing all implementation methods.

### 8.1. Proxy types must match

The management interface should contain only published JMX methods:

```java
public interface QueueManagement {
    long getProcessedCount();
    void resetStatistics();
}
```

If the target MBean does not actually have the `resetStatistics` operation, the proxy interface may still compile, yet calls will fail when JMX handles them. Therefore, keep the client-side interface synchronized with the target's `MBeanInfo`.

When the server uses a Standard MBean from another interface or a Spring `ModelMBean` generated by an assembler, ensure attribute and operation names match. An interface with the same method names does not guarantee all parameter types, return types, or semantics are compatible.

## 9. How does a local proxy differ from calling the object directly?

Suppose Spring has created a `QueueMonitor` target and registered it as an MBean.

### Direct Java call

```java
QueueMonitor monitor = context.getBean(QueueMonitor.class);
long count = monitor.getProcessedCount();
```

- The caller needs a reference to the target bean.
- The method is invoked with normal Java semantics, possibly going through a Spring proxy/AOP if the bean is wrapped.
- No ObjectName or MBeanServer is required.
- The contract may include implementation methods not exported to JMX.
- Exceptions and data types follow direct Java calls.

### Local JMX call

```java
MBeanServerConnection connection = server;
long count = (Long) connection.getAttribute(
    objectName, "ProcessedCount"
);
```

- The caller needs an ObjectName and `MBeanServerConnection`.
- JMX enforces attribute/operation access rules.
- Only the exported interface portion is accessible via JMX.
- JMX exceptions may be encountered.
- Easy to swap the caller for another JMX client while keeping the same JMX contract.

### Local JMX proxy call

```java
QueueMonitorMBean proxy =
    JMX.newMBeanProxy(
        connection,
        objectName,
        QueueMonitorMBean.class
    );
long count = proxy.getProcessedCount();
```

- The caller gets a strongly typed Java API.
- Underneath, it still relies on JMX.
- It is not the target object, even though both are in the same JVM.
- MBean metadata, signature, and lifecycle constraints still apply.

**Conclusion:** a local JMX proxy is not created primarily to “call Java methods faster”; it is used when you want callers to work through a **JMX management contract** and avoid direct coupling to the implementation.

## 10. Cost and runtime characteristics of local JMX

Because they share a JVM, a local `MBeanServerConnection` avoids network connector overhead. However, calls can still involve:

- Looking up the ObjectName in the registry.
- Validating attributes/operations against metadata.
- Type conversion and reflection or `ModelMBean` dispatch.
- Executing the MBean implementation logic.
- Propagating exceptions per the JMX contract.

Do not treat a local proxy as an optimal replacement for very high-frequency business calls. If processing each event requires calling `incrementCounter()`, it is usually better to call the service directly and expose the counter via JMX for monitoring, rather than routing every event through a JMX proxy.

Local JMX is reasonable when:

- There is a stable management API you want to reuse across local/remote clients.
- An observing module should not depend on the target implementation.
- You need to test/diagnose the real JMX surface.
- You want to use ObjectName to locate a management component by convention.

Direct dependency injection is reasonable when:

- The caller is a core business component needing full performance and type safety.
- The target already has a regular Java service interface.
- JMX semantics or observability by management clients are not needed.

## 11. Initialization order: the proxy may arrive before the MBean

A common scenario:

```text
Spring context refresh
   |
   +--> create MBeanProxyFactoryBean
   |
   +--> create MBeanExporter
   |
   +--> register target MBean
   |
   +--> caller invokes method on proxy
```

If the proxy is used **before the target MBean appears**, the call can fail with `InstanceNotFoundException` or the corresponding Spring JMX access exception. Depending on configuration, proxy initialization may also inspect the connection or MBean metadata before the first call.

Ways to organize this:

1. Create the target and register the MBean before making calls through the proxy.
2. Use explicit dependencies/lifecycles when both beans live in the same Spring context.
3. If the target belongs to another module, design readiness into the contract; do not invoke operations inside the caller's constructor.
4. Read `isRegistered(ObjectName)` for diagnostics, but do not treat it as a guarantee that the MBean will still exist at call time.
5. Handle runtime errors because the target can be unregistered or replaced after the proxy is created.

Distinguish **when the proxy exists** from **when the target can handle calls**. A proxy does not keep an MBean alive on its own.

## 12. getMBeanInfo helps discover the real contract

Before creating or using a proxy, metadata can be read:

```java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s: type=%s, read=%s, write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        "operation=" + operation.getName()
    );
}
```

Types from `javax.management` must be imported. Metadata reveals:

- Whether `ProcessedCount` is actually exported.
- Whether `WarningThreshold` is writable.
- Whether `resetStatistics` is an operation and what its signature is.
- Whether the current target uses a different interface/assembler than the expected proxy interface.

**A proxy cannot invent new capabilities for the target.** If an operation is absent from `MBeanInfo`, declaring a method with the same name on the proxy interface does not make it appear.

## 13. Notifications via MBeanServerConnection

Beyond attributes and operations, JMX also supports notifications. With a local client:

```java
NotificationListener listener = (notification, handback) -> {
    System.out.println(
        "type=" + notification.getType()
        + ", handback=" + handback
    );
};

connection.addNotificationListener(
    objectName,
    listener,
    null,
    "local-observer"
);
```

This code is valid only if the target MBean can emit notifications. A `null` filter means no notification-type filtering for this registration; `"local-observer"` is a caller-chosen handback.

Removing the registration:

```java
connection.removeNotificationListener(
    objectName,
    listener
);
```

If an application needs multiple registrations for the same listener, use the overload taking listener/filter/handback to remove the exact one. Do not let a local listener outlive the lifecycle of its owning component.

A Spring MBean proxy for management methods does not automatically turn notifications into Java callbacks on a business interface; to receive notifications, subscribe via the JMX API or Spring's listener support.

## 14. Proxy exceptions: not identical to every ordinary Java call

When calling directly:

```java
target.setWarningThreshold(-1);
```

the implementation may throw `IllegalArgumentException`. When calling through JMX:

```java
proxy.setWarningThreshold(-1);
```

the exception can pass through JMX reflection/`ModelMBean` and the proxy layer, so the caller may observe an exception that has been wrapped or translated into a JMX access exception. Do not write code that depends on the exception class always being identical to a direct call.

Common cases:

| Cause | Symptom |
|---|---|
| ObjectName does not exist | `InstanceNotFoundException` or related proxy exception |
| Attribute missing/unreadable | `AttributeNotFoundException` or corresponding proxy exception |
| Invalid value | Target validation exception forwarded or wrapped by JMX/Spring |
| Method not exported | Invoke/metadata error |
| MBean replaced or unregistered | Earlier call succeeds, later call fails |
| Remote connector disconnected | Connection/IO error beyond ordinary MBean errors |

Do not use the proxy to mask all failures as “MBean unavailable”. The client must distinguish misconfiguration, invalid input, STOPPING state, and connection failures.

## 15. Spring local proxy with FactoryBean: illustrative wiring

A centralized configuration can create the target, exporter, and proxy in the same context:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class CompleteJmxConfiguration {

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public QueueMonitor queueMonitorTarget() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanExporter queueExporter(
            MBeanServer mBeanServer,
            QueueMonitor queueMonitorTarget) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
            "demo.queue:type=QueueMonitor,name=orders",
            queueMonitorTarget
        ));
        return exporter;
    }

    @Bean
    public MBeanProxyFactoryBean queueMonitorJmxProxy(
            MBeanServer mBeanServer) {
        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();
        factory.setServer(mBeanServer);
        factory.setObjectName(
            "demo.queue:type=QueueMonitor,name=orders"
        );
        factory.setProxyInterface(QueueMonitorMBean.class);
        return factory;
    }
}
```

A consumer can inject the proxy using a qualifier:

```java
@Service
public class MonitoringClient {
    private final QueueMonitorMBean proxy;

    public MonitoringClient(
            @Qualifier("queueMonitorJmxProxy")
            QueueMonitorMBean proxy) {
        this.proxy = proxy;
    }

    public long processed() {
        return proxy.getProcessedCount();
    }
}
```

Because the target also implements `QueueMonitorMBean`, the qualifier avoids ambiguous injection. In a real project, choose a clear lifecycle so the exporter registers the target before the client needs to call it; for instance, test by creating the context and calling the proxy **after context refresh completes**, reading `MBeanInfo` first.

Do not configure multiple exporters registering the same ObjectName unintentionally. The beans in the sample `@Configuration` represent one way to organize a lab; larger applications may use auto-exporters, `@ManagedResource`, and a different naming strategy.

## 16. MBeanServerFactoryBean and local server selection

Spring provides `MBeanServerFactoryBean` to locate or create an `MBeanServer` as configured. With a local proxy, it is crucial that **the exporter and proxy point to the same server**.

```text
Exporter -> Server A -> MBean "demo:type=Queue"
Proxy    -> Server B -> "demo:type=Queue" not found
```

Even though Server A and B are in the same JVM, they are separate registries. An ObjectName registered in A does not automatically appear in B. This is a common reason why a proxy reports an MBean missing while logs show the exporter registered successfully.

For Spring/JVM platform monitoring, choosing `ManagementFactory.getPlatformMBeanServer()` as the shared server is often convenient. However, in tests or applications needing MBean isolation, a separate server can be used. Choose consistently and verify the actual instance, not just the `MBeanServer` type.

## 17. Data types: Standard MBean and MXBean

With Standard MBeans, methods on the proxy typically use the same management interface as the target. If the interface contains custom DTOs, a local proxy can work when both sides have compatible types and JMX handles them appropriately; however, when moving to remote, class availability and serialization can become issues.

MXBeans actively map eligible Java types to Open Types. For example, an MXBean returning a composite DTO may expose `CompositeData` through the raw API, whereas a typed MXBean proxy maps back to the Java type if the reverse mapping is valid.

Comparison:

```java
// MXBean raw API may return CompositeData:
Object raw = connection.getAttribute(name, "Status");

// Typed MXBean proxy:
StatusMXBean p = JMX.newMXBeanProxy(
    connection,
    name,
    StatusMXBean.class
);
StatusDto value = p.getStatus();
```

`StatusMXBean` and `StatusDto` here are illustrative names; the interface and DTO must be defined following valid MXBean mapping rules when run. Do not take `CompositeData` and cast it directly to `StatusDto`.

When using Spring `MBeanProxyFactoryBean` with an MXBean, check the MXBean mode support and type mapping rules of the Spring version in use. If you need a standard MXBean proxy, the JDK's `JMX.newMXBeanProxy` is a direct and explicit option.

## 18. Security: local does not mean controls are unnecessary

Working via JMX in the same JVM usually needs no remote network transport, yet points still require care:

- The MBean interface may contain side-effecting methods such as `resetCounters()`, `clearCache()`, `pauseConsumer()`.
- An internal component holding an `MBeanServer` reference can invoke JMX operations as permitted by the environment.
- If the same `MBeanServer` is later exposed remotely, the management surface also becomes visible to remote clients.
- Exported getters can expose configuration, credentials, or user data.
- A local proxy does not automatically add per-method authentication/authorization.
- Getter errors or latency can still impact the calling thread.

Therefore, treat MBean management like a privileged API: restrict exposed methods, validate values, control access rights, audit-log critical operations, and secure remote connections where present.

Do not use a JMX proxy as a shortcut to bypass security boundaries of business APIs. If an operation modifies critical data, security policies must be enforced at appropriate layers rather than relying on the caller being “in the same JVM”.

## 19. When should you avoid a proxy?

A JMX proxy adds a layer of abstraction and is not always the right choice.

**Do not use it solely for continuous internal logic calls.** For example, a worker calling `recordProcessed()` thousands of times per second through an MBean proxy, instead of calling the Java service directly, can add overhead without providing management value.

**Do not use it to replace messaging between services.** JMX is designed for management/monitoring, not as a durable business event bus.

**Do not use it to hide complex lifecycles.** A proxy does not make the target appear on its own, does not start a database, and does not guarantee the target is READY.

**Do not use it when the type contract is unstable.** If `MBeanInfo` changes frequently during deployment, client proxies can fail on calls; versioning/naming strategies and contract alignment are needed.

Use a proxy when you have a small, stable management interface and want client code to program against that contract rather than depending on implementation classes.

## 20. Hands-on exercises for local proxy testing

### Exercise 1 — Raw API and typed proxy

Register `QueueMonitor` in the platform MBeanServer. Read `ProcessedCount` using `getAttribute` and using `JMX.newMBeanProxy`. Compare both values. Then call `resetStatistics()` via the proxy and read the raw attribute again.

### Exercise 2 — Changing the threshold

Call `setWarningThreshold(200)` via the proxy and read `WarningThreshold` back with `getAttribute`. Then try an invalid value and observe the exception.

### Exercise 3 — Wrong ObjectName

Create a proxy with an `ObjectName` that has no MBean, call a getter, and record the error. Then register the right MBean and retry. The goal is to distinguish creating a proxy from registering the target.

### Exercise 4 — Two local MBeanServers

Create separate MBeanServer A and B in a test JVM. Register the MBean in A but create the proxy pointing to B. Explain why the call fails even though both servers are local. Then point the proxy to A.

### Exercise 5 — Spring wiring

Create `MBeanExporter` and `MBeanProxyFactoryBean` in a Spring context. Inject the proxy into a `MonitoringClient` bean and invoke a getter after context refresh completes. Use a qualifier to distinguish proxy and target.

### Exercise 6 — Updating the interface

Add a new operation to the caller-side management interface without updating the target MBean. Inspect `MBeanInfo` and try calling it. Explain why having the method on the proxy at compile time does not create the capability at runtime.

### Exercise 7 — Notifications

Create an MBean with `NotificationBroadcasterSupport`, register a listener through `MBeanServerConnection`, emit a notification, and remove the listener. Compare notification subscriptions with method calls on the proxy.

## 21. Self-check questions

1. How do `MBeanServer` and `MBeanServerConnection` differ?
2. Why can `MBeanServer` be used as a local `MBeanServerConnection`?
3. What role does `ObjectName` play for a proxy?
4. What does `JMX.newMBeanProxy` do, and does it register the MBean itself?
5. What is the difference between a direct Java call and a local JMX proxy call?
6. Which two opposite directions do `MBeanProxyFactoryBean` and `MBeanExporter` solve?
7. Why can interface-based injection be ambiguous when both the target and proxy implement the interface?
8. What happens if the exporter and proxy use two different local MBeanServers?
9. Why can a proxy fail to call a getter even though the proxy object was created?
10. When should `JMX.newMXBeanProxy` be used instead of `newMBeanProxy`?

## 22. Core takeaways

**`MBeanServerConnection` is the client's JMX interface; an `MBeanServer` in the same JVM can be used directly as a local connection.** The raw API uses `getAttribute`, `setAttribute`, `invoke`, and `ObjectName`; a typed proxy lets callers invoke methods on a management interface while calls still traverse JMX.

In Spring, `MBeanExporter` puts beans into the MBeanServer, while `MBeanProxyFactoryBean` creates proxies to call already-registered MBeans. Keep the exporter and proxy pointing to the same registry, keep the management interface aligned with `MBeanInfo`, ensure proper lifecycle ordering, and use JMX proxies only for commensurate management/observability purposes.
