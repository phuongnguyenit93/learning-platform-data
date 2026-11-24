# Dynamic Proxies and Return Type Limitations in Spring JMX

## 1. Learning objectives

After this lesson, you will be able to:

- Explain what a **dynamic proxy for a local MBean** is and why Java code can call an interface while the call actually goes through `MBeanServerConnection`.
- Distinguish JDK dynamic proxies created by JMX, proxies from Spring's `MBeanProxyFactoryBean`/`MBeanClientInterceptor`, and AOP proxies commonly used for business services.
- Describe how a method on a proxy translates into **reading an attribute**, **writing an attribute**, or **invoking an operation** on an MBean.
- Understand **return type** limitations: primitives, `String`, `ObjectName`, arrays, custom DTOs, `CompositeData`, `TabularData`, Java records, generic collections, and MXBean open-type mapping.
- Distinguish local `MBeanServer` behavior from a remote JMX connector, especially **class loading** and **serialization**.
- Handle errors such as `ClassCastException`, `InvalidAttributeValueException`, `ReflectionException`, `MBeanException`, `UndeclaredThrowableException`, or mapping/signature incompatibility errors.
- Design stable management interfaces that are easy to invoke via proxies and easy to turn into monitoring contracts.

## 2. Context: why use a proxy instead of calling MBeanServer manually?

JMX (Java Management Extensions) allows an application to register managed objects (MBeans) with an `MBeanServer`, under an `ObjectName`.

Example:

```text
com.example.shop.orders:type=QueueMonitor,name=outbox
```

A plain JMX client can read an attribute:

```java
Object value = connection.getAttribute(name, "PendingCount");
int pending = (Integer) value;
```

or invoke an operation:

```java
Object result = connection.invoke(
        name,
        "resetStatistics",
        new Object[0],
        new String[0]);
```

This works, but when an application calls many attributes and operations, code must manually handle names, data types, signatures, and checked exceptions.

An **MBean proxy** provides a Java interface so the client writes more natural code:

```java
int pending = monitor.getPendingCount();
monitor.resetStatistics();
```

Behind the call, the proxy translates the method to the corresponding JMX access. The proxy does not remove the JMX boundary; it merely **encapsulates calls to MBeanServerConnection**.

## 3. What exactly is a “local MBean proxy”?

An MBean proxy is called **local** when it communicates with an MBeanServer in the same process/JVM, typically by obtaining the platform MBeanServer:

```java
MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();
```

`MBeanServer` also provides the operations of `MBeanServerConnection`, so the proxy can use this server without a network connector.

Flow:

```text
Application code
       |
       v
QueueMonitorMBean proxy (Java interface)
       |
       v
Dynamic proxy / interceptor
       |
       v
MBeanServerConnection
       |
       v
Local MBeanServer
       |
       v
Registered MBean: com.example.shop.orders:type=QueueMonitor,name=outbox
```

Characteristics:

- No socket/network needed for access within the same JVM.
- Still depends on `ObjectName`, MBean metadata, the interface, and the existence of the registration.
- Calls can fail if the MBean is not yet registered, has been unregistered, or has an incompatible signature.
- Does not automatically add caching for every getter.
- Does not inherently make a slow method fast.

In Spring, you commonly encounter `MBeanProxyFactoryBean` and `MBeanClientInterceptor`. In standard Java, there is `javax.management.JMX.newMBeanProxy(...)` or `newMXBeanProxy(...)`.

## 4. Distinguishing three commonly confused proxy types

| Proxy type | Purpose | Example |
|---|---|---|
| **Spring AOP proxy** | Insert transaction, security, caching, retry, or advice around service methods | Bean with `@Transactional` |
| **JMX MBean proxy** | Represent JMX attributes/operations as a Java interface and send calls to `MBeanServerConnection` | `JMX.newMBeanProxy(...)` |
| **Spring JMX client proxy** | Use Spring factory/interceptor to create a proxy communicating with an MBean | `MBeanProxyFactoryBean` |

A Spring JMX client proxy may look like a service bean when injected by interface, yet its **actual implementation** is JMX commands to an `ObjectName`. It is not equivalent to a Spring AOP proxy directly wrapping a target service.

An important distinction when debugging:

- If the error happens in business advice, investigate the Spring AOP invocation chain.
- If the error is `InstanceNotFoundException` or failing to read a JMX attribute, investigate `ObjectName`/`MBeanServer`/management metadata.
- If the error is `ClassCastException` after the proxy returns a value, investigate return types and JMX type mapping.

## 5. Complete example with a Standard MBean

We create a simple MBean for a queue.

### 5.1. Management interface

**`QueueMonitorMBean.java`**

```java
public interface QueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void pause();
    void resume();
}
```

By the Standard MBean convention, the `QueueMonitorMBean` interface defines management attributes and operations.

- `getPendingCount()` → attribute `PendingCount` of type `int`.
- `isPaused()` → boolean attribute `Paused`.
- `pause()`, `resume()` → JMX operations.

### 5.2. Implementation

**`QueueMonitor.java`**

```java
import java.util.concurrent.atomic.AtomicInteger;

public class QueueMonitor implements QueueMonitorMBean {

    private final AtomicInteger pending = new AtomicInteger(5);
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return pending.get();
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
```

The example uses `AtomicInteger` and `volatile` to simplify reading state in memory; production must design the worker/queue lifecycle accordingly.

### 5.3. Registering and creating a JMX dynamic proxy

**`LocalProxyDemo.java`**

```java
import java.lang.management.ManagementFactory;
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class LocalProxyDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=QueueMonitor,name=outbox");

        server.registerMBean(new QueueMonitor(), name);

        try {
            QueueMonitorMBean proxy = JMX.newMBeanProxy(
                    server,
                    name,
                    QueueMonitorMBean.class);

            System.out.println("Pending: " + proxy.getPendingCount());
            System.out.println("Paused: " + proxy.isPaused());

            proxy.pause();
            System.out.println("Paused after pause(): " + proxy.isPaused());

            proxy.resume();
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

The code requires only standard Java/JMX. When run, `JMX.newMBeanProxy` returns a Java proxy implementing the `QueueMonitorMBean` interface. It does not directly return a reference to the registered `QueueMonitor` object.

### 5.4. What happens when calling the proxy?

```text
proxy.getPendingCount()
    |
    v
connection.getAttribute(objectName, "PendingCount")
    |
    v
QueueMonitor.getPendingCount()

proxy.pause()
    |
    v
connection.invoke(objectName, "pause", [], [])
    |
    v
QueueMonitor.pause()
```

JMX introspection interprets getters/setters according to the management contract and naming conventions. If the proxy interface declares a method that does not exist in the MBean metadata, the call will not succeed merely because Java compiles.

## 6. How does Spring MBeanProxyFactoryBean work?

Spring Framework supports creating JMX client proxies via `MBeanProxyFactoryBean` (using interception to map methods to JMX).

Java configuration example:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class JmxClientConfig {

    @Bean
    MBeanProxyFactoryBean queueMonitorProxy(MBeanServer mbeanServer)
            throws Exception {

        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
        factory.setServer(mbeanServer);
        factory.setObjectName(new ObjectName(
                "com.example.shop.orders:type=QueueMonitor,name=outbox"));
        factory.setProxyInterface(QueueMonitorMBean.class);

        return factory;
    }
}
```

The example assumes the Spring context has an appropriate `MBeanServer` bean and the MBean is registered under the ObjectName above. Because `MBeanProxyFactoryBean` is a `FactoryBean`, consumers typically obtain the **proxy product** by bean name, while obtaining the factory itself (if needed) uses Spring's FactoryBean access syntax.

A client injected through the management interface:

```java
import org.springframework.stereotype.Component;

@Component
public class QueueOperations {

    private final QueueMonitorMBean monitor;

    public QueueOperations(QueueMonitorMBean monitor) {
        this.monitor = monitor;
    }

    public int pending() {
        return monitor.getPendingCount();
    }
}
```

Ensure dependency injection is unambiguous if the application has both the target MBean and the proxy implementing `QueueMonitorMBean`. Bean names/qualifiers or separating the client interface can be used depending on configuration. Do not assume this injection example resolves uniquely if multiple candidates exist.

**Version note:** Check the Javadoc of the Spring version you use for setters, FactoryBean initialization, and metadata autodetection capabilities. With the Spring JMX exporter, the server and client can share the same `MBeanServer`, and you should not create a new server only to have the proxy try to access a name registered on a different server.

## 7. A proxy does not erase the JMX boundary

A dynamic proxy can create the illusion of an ordinary object:

```java
QueueMonitorMBean monitor = ...;
int value = monitor.getPendingCount();
```

Yet the call traverses the `MBeanServer` and has characteristics different from a direct method call:

1. **`ObjectName` is the target identifier**, not a Java object reference to the target.
2. The MBean may not exist at call time.
3. Getters can throw errors from the `MBeanServer`, metadata, or implementation logic.
4. Operations may be restricted by the MBean contract and security policy.
5. Data types passing through the JMX API must match what the proxy expects.
6. Do not assume a local call is always lightweight: a target getter may hit a DB or HTTP endpoint.
7. Clients may see metadata changes if the MBean is unregistered/re-registered under the same name.

Therefore, a proxy interface is a **client-side contract**, not proof that the MBean actually provides all matching methods and types.

## 8. Return types: which types are simplest?

For Standard MBeans in the same JVM, common return types are usually straightforward to use:

| Type | Example method | Notes |
|---|---|---|
| Primitive | `int getPendingCount()` | Clear, cannot be null |
| Boxed primitive | `Integer getPendingCount()` | Can be null per contract, must be handled |
| `boolean` / `Boolean` | `isPaused()` | Boolean or boxed attribute |
| `String` | `String getState()` | Simple, easy to understand |
| `ObjectName` | `ObjectName getRelatedMBean()` | Identifier referencing another MBean |
| Arrays of simple types | `String[] getActiveQueues()` | Size and snapshot semantics must be controlled |
| `CompositeData` | `CompositeData getSnapshot()` | Open type data; client must know fields |
| `TabularData` | `TabularData getWorkers()` | Open-data table with explicit schema |
| Custom DTO | `QueueSnapshot getSnapshot()` | Depends on Standard/MXBean mapping and local/remote class loading |
| Collections/generics | `List<QueueSnapshot> listSnapshots()` | Prone to mapping, interface, and serialization limits |

**There is no rule saying “a local proxy accepts every return type Java accepts.”** Valid return types also depend on the **MBean type**, **`MBeanInfo`**, **mapping mechanism**, and **transport**.

## 9. Standard MBean and MXBean: different type limitations

This is the most important distinction when designing APIs with complex data.

### 9.1. Standard MBean

A Standard MBean derives its management contract from a suitably named interface, for example:

```java
public interface QueueMonitorMBean {
    int getPendingCount();
    QueueSnapshot getSnapshot();
}
```

A custom `QueueSnapshot` can be used in a Standard MBean, however:

- The client must understand the exact runtime class/type when receiving the value.
- If remote, Java serialization/class loading can be a significant barrier.
- The Spring proxy must have a method signature compatible with JMX metadata.
- If the MBean exporter or assembler transforms types via another mechanism, the client may receive a type different from the expected DTO.

With **local** Standard MBeans in the same JVM, clients usually share the classpath and a compatible classloader more easily than remote clients. Yet local **does not eliminate** risks of mismatched interface types, `ClassCastException`, or returning a shared mutable object that clients modify unintentionally.

### 9.2. MXBean

MXBeans define rules mapping many Java types to **Open MBean types**. Clients typically work with standard representations such as `CompositeData` and `TabularData` at the JMX wire/API layer. `JMX.newMXBeanProxy(...)` can apply MXBean mapping so clients see Java types per their MXBean interface.

Example:

```java
public interface QueueStatsMXBean {
    int getPendingCount();
    QueueSnapshot getSnapshot();
}
```

If `QueueSnapshot` conforms to MXBean mapping rules, the API handles the corresponding conversion. If not, registration or access can fail because the data type cannot be converted to an OpenType.

**Do not assume by default:** that a Java record or an arbitrary custom class always maps automatically to `CompositeData` across every JDK version and MXBean setup. Verify mapping against MXBean rules and the specific types.

## 10. Safe example: DTO expressed as simple attributes

If the goal is monitoring with diverse JMX clients, instead of returning an arbitrary DTO:

```java
public interface QueueMonitorMBean {
    int getPendingCount();
    long getProcessedCount();
    String getState();
}
```

Advantages:

- Minimal Java class dependency on the client side.
- Easy to read in JConsole and scripts.
- Easy to map to metrics exporters.
- Avoids complex schemas with serialization or mapping.

Trade-offs:

- A client reading three attributes may observe them at three different points in time, **with no guarantee of an atomic snapshot across all three**.
- If strict consistency is needed, design a compound attribute or snapshot with metadata/version and appropriate mapping.
- Do not split one structure into hundreds of attributes solely to avoid complex types.

## 11. Complex return type example: CompositeData

The JMX Open MBean API provides `CompositeData`, representing a record with fields of declared types.

Example method:

```java
import javax.management.openmbean.CompositeData;

public interface QueueDiagnosticsMBean {
    CompositeData getSnapshot();
}
```

The client can read:

```java
CompositeData snapshot = proxy.getSnapshot();
Object pending = snapshot.get("pendingCount");
Object state = snapshot.get("state");
```

The field names `pendingCount`/`state` must match the `CompositeType` actually exposed by the MBean.

### Building CompositeData

```java
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

public static CompositeData createSnapshot(
        int pending, String state) throws Exception {

    String[] names = {"pendingCount", "state"};
    OpenType<?>[] types = {
            SimpleType.INTEGER,
            SimpleType.STRING
    };

    CompositeType type = new CompositeType(
            "QueueSnapshot",
            "Queue monitoring snapshot",
            names,
            new String[] {"Pending count", "Queue state"},
            types);

    return new CompositeDataSupport(
            type,
            names,
            new Object[] {pending, state});
}
```

`CompositeData` suits clients that want to avoid depending on custom Java DTOs. However, schema management is necessary: renaming fields or changing types can break older clients. `CompositeData.get("missing")` can throw `InvalidKeyException`, so do not treat the schema as self-negotiating.

## 12. TabularData example for status lists

`TabularData` is an open-data structure for tabular data with `CompositeData` rows and valid keys/indexes.

It can be used to publish the status of multiple workers:

```text
workerId   state     processed
w-01       RUNNING   120
w-02       IDLE      105
w-03       PAUSED    90
```

Interface:

```java
import javax.management.openmbean.TabularData;

public interface WorkerStatusMBean {
    TabularData getWorkers();
}
```

Design notes:

- The `TabularType` and `CompositeType` schemas must agree.
- One or more fields must serve as the key to identify rows.
- List size must be bounded; do not return a table of hundreds of thousands of rows on every JMX poll.
- For continuously changing data, define snapshot semantics.
- If the goal is metrics aggregation, multiple scalar gauges/counters or a dedicated metrics endpoint may be more suitable.

## 13. Custom Java DTOs: why does local work while remote can fail?

Suppose:

```java
public final class QueueSnapshot implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private final int pending;
    private final String state;

    public QueueSnapshot(int pending, String state) {
        this.pending = pending;
        this.state = state;
    }

    public int getPending() {
        return pending;
    }

    public String getState() {
        return state;
    }
}
```

A Standard MBean can return this object when both sides are compatible. A local client using the same classloader can cast directly:

```java
QueueSnapshot snapshot = monitor.getSnapshot();
```

However, when moving to remote JMX/RMI, conditions change:

- The DTO must be compatible with the serialization mechanism in use.
- The client needs the `QueueSnapshot` class and any related dependencies.
- `serialVersionUID`, field changes, class versions, or package differences can cause deserialization failures.
- Java serialization carries security risks if objects are untrusted; trusted connections and serialization filtering/allowlisting must be configured where appropriate.
- A class implementing `Serializable` does not automatically guarantee all nested members are serializable.

Therefore, a design built for a local MBean proxy is not automatically a good contract for remote clients. MXBean open types or scalar attributes often reduce dependency on custom classes.

## 14. Why should you not arbitrarily return a JPA Entity?

A JMX getter like the following easily causes problems:

```java
public interface OrderMonitorMBean {
    OrderEntity getLastOrder();
}
```

This is generally an unsuitable design for a management API because:

1. A JPA entity may contain many fields and sensitive data.
2. Lazy associations may trigger SQL when accessed by the client/serializer.
3. The object graph may be large or contain circular references.
4. `LazyInitializationException` can occur once the persistence context is closed.
5. The client must know the `OrderEntity` class.
6. Entity schemas change with business needs, making the management contract unstable.
7. Returning a mutable object inside a local JVM may hand the client a reference with unintended side effects depending on the implementation.

Instead, publish a **minimal management DTO** or attributes such as:

```text
LastProcessedOrderId
LastProcessedEpochMillis
PendingCount
ProcessingState
```

Still ensure published IDs do not carry personal data or secrets. A JMX interface is an **operational API**, not a business entity API.

## 15. Limitations of generic return types

Consider:

```java
List<QueueSnapshot> getSnapshots();
Map<String, QueueSnapshot> getQueues();
Optional<QueueSnapshot> getLatestSnapshot();
```

Things to consider:

- Generics in Java are primarily enforced at compile time; runtime reflection has both raw types and generic metadata, yet mapping support depends on the mechanism.
- Standard MBeans do not automatically define OpenType schemas for arbitrary generic collections.
- MXBeans have mapping rules for valid collections/maps, though not every combination is compatible.
- `Optional<T>` is not a simple JMX data type by default; verify in the specific mapping rather than assuming.
- Remote clients may lack the DTO class or corresponding deserializer.
- Returning large collections over JMX can make management endpoints slow and allocate excessive memory.

If a cross-platform status list is needed, consider `TabularData` or an MXBean interface with officially mapped types. If it is only for dashboards, prefer useful metrics/attributes rather than exporting entire object graphs.

## 16. Method signatures and overloaded operations

The proxy translates operation calls to names and signatures on the MBeanServer:

```java
connection.invoke(
        objectName,
        "resize",
        new Object[] {16},
        new String[] {"int"});
```

An MBean can have overloaded methods:

```java
void resize(int size);
void resize(String preset);
```

They share the same name but have different signatures. If the proxy interface declares a type different from server metadata, the operation may not be found.

For example, the Java interface uses:

```java
void resize(Integer size);
```

yet the MBean metadata only has operation `resize(int)`; in that case, the signatures `java.lang.Integer` and `int` differ. A proxy is not required to convert them automatically the way the compiler handles autoboxing in local method calls.

**Rule:** the client-side interface must match **names, parameter types, and return types** against the actual management contract; do not treat the proxy as a “smart adapter” for arbitrary overloads.

## 17. Null and primitive return types

Java primitives cannot represent `null`.

If the MBean returns `null` while the proxy interface declares:

```java
int getPendingCount();
```

unboxing can throw errors such as `NullPointerException` or a type conversion error depending on the call path.

When a value can be absent, you can:

- Return `Integer` instead of `int` and document `null`.
- Return a separate status `boolean isInitialized()`.
- Use a clear sentinel, such as `-1`, only if it does not conflict with the value domain.
- Expose `LastRefreshEpochMillis` or `Healthy` to indicate freshness.

In MXBean/open-type mapping, understand the nullability rules of the chosen types. Not all clients handle `null` uniformly when converting to metrics.

## 18. Checked exceptions and exception wrapping

`MBeanServer` has exception types for registration, reflection, attribute access, invocation, and implementation errors. A client proxy can translate or wrap exceptions depending on the proxy/interceptor mechanism.

Common types:

| Exception | Situation |
|---|---|
| `InstanceNotFoundException` | No MBean exists at `ObjectName` |
| `AttributeNotFoundException` | Getter maps to a nonexistent attribute |
| `InvalidAttributeValueException` | Value being set is invalid |
| `MBeanException` | Exception from MBean logic wrapped |
| `ReflectionException` | Matching method or signature not found |
| `ClassCastException` | Runtime type incompatible with client-expected type |
| `UndeclaredThrowableException` | JDK proxy encounters a checked exception not declared by the interface and not suitably translated |
| `IOException` | Can occur with a remote `MBeanServerConnection` |

Do not rely on a single exception type to infer the root cause. Read the **cause chain**, metadata via `getMBeanInfo`, and server-side logs. With local JMX, network errors are largely irrelevant, yet contract/mapping errors, object lifecycle issues, and implementation errors still exist.

A proxy interface can add `throws` per contract, though a Spring/JMX proxy does not necessarily propagate the exact exception a direct Java method would. Integration tests are needed to verify how errors are exposed in a specific framework version.

## 19. Reading MBeanInfo to validate return types

Before trusting a proxy interface, query the MBeanServer for what metadata it actually provides.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class MBeanContractInspector {

    public static void inspect() throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=QueueMonitor,name=outbox");

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf(
                    "ATTRIBUTE %s : %s readable=%s writable=%s%n",
                    attr.getName(),
                    attr.getType(),
                    attr.isReadable(),
                    attr.isWritable());
        }

        for (MBeanOperationInfo op : info.getOperations()) {
            System.out.printf(
                    "OPERATION %s -> %s%n",
                    op.getName(),
                    op.getReturnType());
        }
    }
}
```

The output from `MBeanInfo` is what is actually exposed to clients; check attribute names, data types, operations, and parameter signatures.

**Note:** `MBeanInfo` describes types via JMX metadata, yet a custom DTO can still run into runtime serialization/classloader issues when actually called. Metadata inspection must be paired with integration tests calling the proxy and verifying received values.

## 20. When a local proxy also carries classloader risks

Sharing one JVM does not mean every class uses the same classloader. An application may have:

- Application classloader.
- Plugin module classloader.
- Container classloader.
- Framework- or module-specific classloaders.

If two different classloaders load two classes with the same name `com.example.shop.QueueSnapshot`, the JVM treats them as **two distinct types**. An object created by classloader A cannot be cast to the class loaded by classloader B, even though the class name is identical.

Symptom:

```text
ClassCastException: com.example.shop.QueueSnapshot
cannot be cast to com.example.shop.QueueSnapshot
```

Messages like this can be confusing; the root cause is classloader identity. Ways to reduce risk:

- Share contract interfaces and DTOs in an appropriate common module/classloader.
- Return scalars or OpenTypes when interacting across plugins/classloaders.
- Avoid exposing internal implementation classes via the management API.
- Test in the real container/plugin environment, not solely in unit tests on a single classpath.

## 21. Dynamic proxies do not automatically provide caching or backpressure

Because method calls look like regular Java object calls, developers can forget these are calls into a management server. An exporter might poll the proxy continuously:

```java
int pending = proxy.getPendingCount();
```

Yet the real getter might query a database or run heavy computations. A local proxy only eliminates the network hop; it does not eliminate:

- CPU cost of the getter.
- Lock contention.
- Target-side JDBC/HTTP I/O.
- Cost of constructing `CompositeData`/`TabularData`.
- Call frequency across multiple consumers.
- Risk of operations having side effects.

For critical MBean getters, read a cached snapshot or lightweight counter. If heavy queries are needed, refresh on a separate schedule or publish an explicit operation instead of doing it on every proxy read.

## 22. Verifying a Spring local proxy with an integration test

A test can verify both aspects:

1. The MBean registers under the expected `ObjectName`.
2. The client proxy reads the right attributes and invokes operations with the right semantics.

Idea:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import javax.management.JMX;

public class ProxyContractCheck {

    public static void verify() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("test");

        ObjectName name =
                new ObjectName("com.example.test:type=QueueMonitor");

        server.registerMBean(new QueueMonitor(), name);
        try {
            QueueMonitorMBean proxy = JMX.newMBeanProxy(
                    server, name, QueueMonitorMBean.class);

            if (proxy.getPendingCount() != 5) {
                throw new AssertionError("Wrong pending count");
            }

            proxy.pause();

            if (!proxy.isPaused()) {
                throw new AssertionError("Pause failed");
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

The example uses an isolated test server to avoid polluting the platform MBeanServer. To test `MBeanProxyFactoryBean` itself, start a Spring context with the factory, test MBeanServer, and registered bean, then test the proxy product from Spring.

Do not only assert `proxy != null`; a proxy may be created before the MBean server holds the target object (depending on initialization mode). Calling real methods is what tests the end-to-end JMX path.

## 23. Choosing the right return type for the requirement

| Requirement | Commonly suitable return type/design | Why |
|---|---|---|
| Job counts, thread counts | `int`, `long` | Simple, easy to query and convert to metrics |
| Enum states | `String` or enum with clear contract | Limits class dependencies |
| Update timestamps | `long` epoch millis | Easy for diverse clients to consume |
| Linking to another MBean | `ObjectName` | Standard JMX |
| Multi-field snapshot with clear schema | `CompositeData` or valid MXBean mapping | Open types support interoperability |
| Bounded list/table | `TabularData` or valid MXBean type | Has an explicit management schema |
| Custom Java DTO in the same module | Standard MBean with controlled DTO | Only when client/classloader are compatible |
| Multi-level or very large business data | Do not return directly over JMX; design another API | Avoids load, leaks, and messy schemas |
| Streaming/logs/traces | Use appropriate channels | JMX attributes do not suit large streaming data |

There is no single “best” return type for all MBeans. Choose based on **consumers**, **purpose**, **transport**, and **contract stability**.

## 24. Common errors

| Symptom | Possible cause | How to handle |
|---|---|---|
| `ClassCastException` receiving DTO | Return type differs from metadata or different classloader | Inspect interface, runtime type, classloader |
| `AttributeNotFoundException` | Proxy calls a getter with no matching attribute | Read `MBeanInfo`, fix contract |
| `ReflectionException` on invoke | Wrong method name/parameter signature | Compare metadata method signatures |
| `InstanceNotFoundException` | Wrong `ObjectName`, not registered, or unregistered | Check `isRegistered` and lifecycle |
| Works locally, fails remotely | Serialization or client missing class | Use open types/MXBean or appropriate shared DTO |
| `CompositeData.get()` error | Field name/schema changed | Version and validate `CompositeType` |
| Returning huge list slows JConsole | Attribute builds a heavy snapshot | Bound data, split API |
| `null` returned to primitive | Cannot unbox | Use boxed type or secondary status |
| Proxy runs but data is stale | Target getter reads a cached snapshot | Expose freshness/timestamp |
| Errors after modifying `*MBean` interface | Proxy contract does not match registered MBean | Increase `MBeanInfo` tests and migration checks |

## 25. Hands-on exercises

### Exercise A — Translating Java calls to JMX

Given the interface:

```java
public interface CacheMonitorMBean {
    int getEntryCount();
    boolean isEnabled();
    void clear();
}
```

Write the corresponding calls using `MBeanServerConnection`.

Suggested solution:

```java
int count = (Integer) connection.getAttribute(name, "EntryCount");
boolean enabled =
        (Boolean) connection.getAttribute(name, "Enabled");

connection.invoke(name, "clear", new Object[0], new String[0]);
```

### Exercise B — Choosing return types

An MBean needs to expose `QueueState` with `pendingCount`, `paused`, and `lastUpdatedMillis`. Choose among:

1. Three scalar attributes.
2. One `CompositeData`.
3. Custom DTO `QueueState`.

Explain the trade-offs between consistency, ease of use, open-type support, and classloader/remote compatibility.

### Exercise C — Mismatched interface

The client proxy declares:

```java
long getPendingCount();
```

but the real MBean exposes:

```java
int getPendingCount();
```

Predict the risks when the proxy receives an `Integer` while the caller expects `long`. Propose checking `MBeanAttributeInfo.getType()` and fixing the client interface to match the contract, rather than relying on automatic casting.

### Exercise D — Running locally and remotely

Create a Standard MBean returning a custom `QueueSnapshot`. Run locally through the platform MBeanServer, then try connecting via a remote connector from a client lacking the DTO class.

Explain why remote can fail deserialization/class loading and why using `CompositeData` or valid MXBean mapping improves interoperability.

### Exercise E — Spring MBeanProxyFactoryBean

Create a Spring context with a locally registered `QueueMonitorMBean` and an `MBeanProxyFactoryBean` using `setServer`, `setObjectName`, and `setProxyInterface`. Retrieve the proxy from the context and call `getPendingCount()`.

Inspect with `MBeanInfo` when a method is renamed or its return type changes to observe the contract mismatch.

## 26. Self-check questions

**1. Does a local proxy invoke methods directly on the target MBean instance?**

Not in the sense of a regular Java reference. It forwards method calls through a JMX connection/MBeanServer and `ObjectName`.

**2. Why must the client return type match MBean metadata?**

Because JMX returns types according to the server contract; the proxy does not automatically know how to convert arbitrary Objects into the desired Java type.

**3. Does a local proxy avoid all class-loading errors?**

No. Two different classloaders in the same JVM can load two distinct types even when the class name is identical.

**4. Do Standard MBeans and MXBeans share the same DTO handling rules?**

No. MXBeans use open-type mapping, whereas Standard MBeans can expose custom Java types subject to appropriate compatibility requirements.

**5. Is `MBeanProxyFactoryBean` a server-side `MBeanExporter`?**

No. This factory creates a client proxy to call an already-registered MBean; `MBeanExporter` is the server-side mechanism for exporting Spring beans.

**6. Is `List<CustomDto>` always a portable JMX choice?**

No. Generic types, mapping, serialization, and classloaders must be considered.

**7. Can a local MBean getter be slow?**

Yes. Even without a network hop, a getter can still execute SQL, HTTP, or hold locks for a long time.

## 27. Key takeaways

- An **MBean proxy** is a client layer that lets you call JMX like a Java interface; actual calls traverse `MBeanServerConnection`.
- Local proxies need no network, yet remain bound by **`ObjectName`**, **`MBeanInfo`**, method signatures, lifecycle, and type compatibility.
- `JMX.newMBeanProxy` is for Standard MBeans; `JMX.newMXBeanProxy` is for MXBeans with corresponding mapping.
- Spring `MBeanProxyFactoryBean` creates a client proxy; it differs from `MBeanExporter`, which exports MBeans from a Spring context.
- Simple return types (`int`, `long`, `boolean`, `String`) are easy to maintain. For complex structures, consider `CompositeData`, `TabularData`, or verified MXBean mappings.
- Custom DTOs may work locally yet fail remotely due to serialization/class loading; local can also fail due to distinct classloaders.
- The proxy interface must match MBean attributes/operations, including parameter signatures and return types.
- Read `MBeanInfo` and invoke real methods in integration tests to catch mismatches.
- Avoid returning business entities, large object graphs, secrets, or unbounded collections over JMX.

## 28. References

- Java SE 21 — `javax.management.JMX`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/JMX.html
- Java SE 21 — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — `CompositeData`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html
- Java SE 21 — `TabularData`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/TabularData.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanProxyFactoryBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework Javadoc — `MBeanClientInterceptor`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanClientInterceptor.html
