# Reading and Writing Attributes via MBeanServer in Spring Framework JMX

## 1. Objectives and Role of MBeanServer

One of the most common management operations with JMX is **reading or changing an attribute value** on an MBean. Java Management Extensions (JMX) standardizes how an application's management state is exposed in the form of attributes, operations, and notifications. `MBeanServer` is the component that receives client requests, locates the MBean by `ObjectName`, checks the management contract published by the MBean, and performs the corresponding access.

In a Spring Framework application, a bean can be exported as an MBean via `MBeanExporter` or another JMX registration mechanism. Once registered successfully, management code can use `javax.management.MBeanServer` directly to work with it. This API belongs to Java JMX; Spring handles the configuration and lifecycle of the surrounding objects, while the rules for reading/writing attributes are defined by JMX.

This lesson focuses on the following operations:

- Locating an MBean via `ObjectName`.
- Reading a single attribute with `getAttribute` or multiple attributes with `getAttributes`.
- Writing a single attribute with `setAttribute` or multiple attributes with `setAttributes`.
- Understanding read/write permissions, data types, errors, and limitations of these calls.
- Combining Spring configuration with JMX operations and verifying the result by reading back.

```text
Spring Application
  ├── Managed Spring bean
  │      └── MBeanExporter / MBean registration
  │               │
  │               ▼
  └── MBeanServer ── ObjectName ── MBean
          ▲                        ├── Read-only attribute
          │                        ├── Writable attribute
          │                        └── Operation / Notification
          │
     Java management code
       getAttribute()
       setAttribute()
       getAttributes()
       setAttributes()
```

An important distinction to remember: **an attribute is not an arbitrary accessible Java field**. It is part of the management interface that the MBean has published. An MBean can contain dozens of internal fields while exporting only a few attributes to JMX clients.

## 2. Preparing an MBean for Reading and Writing

### 2.1. The Standard MBean Contract

A fundamental way to create an MBean is using a **Standard MBean** following JMX naming conventions: an interface named `<ClassName>MBean`, and a class implementing that interface. Attributes are derived from JavaBeans-style getter and setter methods.

The following interface defines a read-only `ActiveSessions` attribute and a read/write `Enabled` attribute:

```java
package com.example.monitoring;

public interface TrafficMonitorMBean {
    int getActiveSessions();

    boolean isEnabled();

    void setEnabled(boolean enabled);
}
```

Implementation class:

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

public class TrafficMonitor implements TrafficMonitorMBean {
    private final AtomicInteger activeSessions = new AtomicInteger();
    private volatile boolean enabled = true;

    @Override
    public int getActiveSessions() {
        return activeSessions.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    // Application methods; not part of TrafficMonitorMBean.
    public void sessionStarted() {
        activeSessions.incrementAndGet();
    }

    public void sessionFinished() {
        activeSessions.decrementAndGet();
    }
}
```

JMX sees two attributes:

| Attribute | JMX Type | Read | Write | Basis |
| --- | --- | --- | --- | --- |
| `ActiveSessions` | `int` | Yes | No | `getActiveSessions()` |
| `Enabled` | `boolean` | Yes | Yes | `isEnabled()` and `setEnabled(boolean)` |

There is no `setActiveSessions(int)` in the MBean interface, so JMX does not allow writing `ActiveSessions`. On the other hand, a private field does not automatically become an attribute without a corresponding management contract.

### 2.2. Registering with MBeanServer

An object can be registered using plain JMX:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import com.example.monitoring.TrafficMonitor;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=TrafficMonitor,name=Main");

if (!server.isRegistered(name)) {
    server.registerMBean(new TrafficMonitor(), name);
}
```

This example registers a Standard MBean into the platform MBeanServer. In a Spring application, it is usually better to let Spring configuration own the bean and the MBean export so that initialization/destruction lifecycles are clearly managed; the direct example above illustrates the core JMX API.

A basic Spring configuration:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MonitoringJmxConfig {

    @Bean
    public TrafficMonitor trafficMonitor() {
        return new TrafficMonitor();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter trafficMonitorExporter(
            TrafficMonitor trafficMonitor,
            MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
            "com.example.monitoring:type=TrafficMonitor,name=Main",
            trafficMonitor));
        return exporter;
    }
}
```

Here `MBeanExporter` receives the bean and a specific `ObjectName`, then exports the object to the configured MBeanServer. Avoid manually registering an object with the same name if Spring is already exporting it: duplicate registration can cause `InstanceAlreadyExistsException` or depend on the exporter's registration policy.

### 2.3. ObjectName Is the Access Key

`ObjectName` uses the syntax **domain:key=value,...**:

```text
com.example.monitoring:type=TrafficMonitor,name=Main
```

When accessing an attribute, the client must specify both the ObjectName and the attribute name. `type` and `name` are only identifying properties, not necessarily JMX attributes. Therefore, calling `getAttribute(name, "Enabled")` reads the state exported by the MBean, whereas `getAttribute(name, "name")` will fail if the MBean does not expose an attribute named `name`.

Use consistent names between registration and access. For multiple instances, the identifier needs sufficient information to avoid collisions.

## 3. Reading a Single Attribute with getAttribute

### 3.1. Signature and Return Value

`MBeanServer` provides the method:

```java
Object getAttribute(ObjectName name, String attribute)
    throws MBeanException,
           AttributeNotFoundException,
           InstanceNotFoundException,
           ReflectionException;
```

Example:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=TrafficMonitor,name=Main");

Object raw = server.getAttribute(name, "ActiveSessions");
int activeSessions = (Integer) raw;

System.out.println("Active sessions: " + activeSessions);
```

The first parameter is the MBean identifier; the second parameter is the **case-sensitive** attribute name according to JMX metadata. The return type is `Object` because the API can serve many different MBeans. For an `int` attribute, the actual returned type is typically `Integer`; for `boolean`, typically `Boolean`.

```java
boolean enabled = (Boolean) server.getAttribute(name, "Enabled");
```

Do not cast blindly without knowing the MBean contract. If an administration tool reads MBeans it does not control, discover metadata first and handle possible types such as `String`, numeric types, `ObjectName`, arrays, `CompositeData`, or `TabularData`.

### 3.2. Conditions for a Successful Read

Reading an attribute requires:

1. The MBean is registered under the exact ObjectName on the target server.
2. The MBean exposes an attribute with the exact name.
3. The attribute is declared **readable**.
4. The getter implementation runs and returns a valid value.
5. If accessed remotely, the connection and access permissions allow reading.

An attribute may have a name similar to a JavaBeans property, but not every `getX()` method on a Spring bean automatically becomes a JMX attribute. This depends on the MBean type or the metadata/assembler that Spring uses.

### 3.3. Reading Multiple Attributes at Once

For one MBean and multiple attribute names, use:

```java
import javax.management.Attribute;
import javax.management.AttributeList;

AttributeList attributes = server.getAttributes(
    name,
    new String[] { "ActiveSessions", "Enabled" });

for (Object item : attributes) {
    Attribute attribute = (Attribute) item;
    System.out.printf("%s = %s%n",
        attribute.getName(),
        attribute.getValue());
}
```

`getAttributes` returns an `AttributeList`, where each element is a name/value pair. The resulting list **may contain only the attributes that were successfully read**; do not assume all requested names are present or rely mechanically on positional order. Map by `attribute.getName()` and check for missing names.

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Object> values = new HashMap<>();
for (Object item : attributes) {
    Attribute attribute = (Attribute) item;
    values.put(attribute.getName(), attribute.getValue());
}

if (!values.containsKey("Enabled")) {
    throw new IllegalStateException(
        "JMX attribute Enabled was not returned");
}
```

Reading multiple attributes in a single API call can reduce round-trips for remote clients, but the result is not necessarily an atomic snapshot of the entire MBean: data can still change between individual getter executions.

## 4. Writing a Single Attribute with setAttribute

### 4.1. Signature and Passing Values

`setAttribute` takes an `Attribute` object containing a name and a value:

```java
void setAttribute(ObjectName name, Attribute attribute)
    throws InstanceNotFoundException,
           AttributeNotFoundException,
           InvalidAttributeValueException,
           MBeanException,
           ReflectionException;
```

Example turning off state collection according to the management contract:

```java
import javax.management.Attribute;

server.setAttribute(
    name,
    new Attribute("Enabled", Boolean.FALSE));
```

`Enabled` is the JMX attribute name; `Boolean.FALSE` is the new value with a type compatible with `boolean`. MBeanServer routes the request to the setter logic implemented by the MBean. The setter may validate, normalize, or reject the value depending on business rules.

**A successful write does not mean all related components update immediately.** If the setter only updates configuration and another worker reads it periodically, the observed effect may arrive later; this is an application characteristic, not an automatic JMX rule.

### 4.2. Reading Back to Confirm State

```java
server.setAttribute(
    name,
    new Attribute("Enabled", Boolean.FALSE));

boolean actual = (Boolean) server.getAttribute(name, "Enabled");
if (actual) {
    throw new IllegalStateException(
        "Enabled remained true after write");
}
```

The readback here confirms the value exposed by the JMX getter after writing. If multiple parties modify the same attribute, the value may continue changing immediately afterward. Therefore, reading back is a point-in-time observation and does not replace synchronization or versioning mechanisms when concurrency guarantees are required.

### 4.3. Writing Multiple Attributes with setAttributes

`MBeanServer` provides:

```java
AttributeList setAttributes(
    ObjectName name,
    AttributeList attributes);
```

Example of an MBean that has both `Enabled` and another writable attribute named `Threshold`:

```java
import javax.management.Attribute;
import javax.management.AttributeList;

AttributeList updates = new AttributeList();
updates.add(new Attribute("Enabled", Boolean.TRUE));
updates.add(new Attribute("Threshold", Integer.valueOf(100)));

AttributeList applied = server.setAttributes(name, updates);

for (Object item : applied) {
    Attribute result = (Attribute) item;
    System.out.printf("Applied %s = %s%n",
        result.getName(),
        result.getValue());
}
```

`Threshold` in this snippet is a **hypothetical attribute** of an MBean that supports it; `TrafficMonitorMBean` in section 2 did not declare it. If running directly against the `TrafficMonitor` class, only write `Enabled`.

The result of `setAttributes` is the list of attributes that were successfully processed. Do not assume all requests succeeded. Nor should you treat a batch call as a **transaction**: if the first update succeeds and the second update fails, JMX does not automatically guarantee rollback of the previous state.

For interdependent updates, consider exposing a single management operation that performs validation and consistent updates inside the MBean instead of calling multiple separate setters.

## 5. Checking Which Attributes Are Readable or Writable

### 5.1. Discovering with MBeanInfo

Before interacting with an unknown MBean, use `getMBeanInfo`:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "name=%s type=%s readable=%s writable=%s is=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable(),
        attr.isIs());
}
```

`MBeanAttributeInfo` provides:

| API | Meaning |
| --- | --- |
| `getName()` | Published attribute name |
| `getType()` | Java data type name according to metadata |
| `isReadable()` | Allows reading via JMX |
| `isWritable()` | Allows writing via JMX |
| `isIs()` | Boolean attribute using the `isX()` getter pattern |
| `getDescription()` | Description for operational tools |

The example above is exploratory: in dynamic MBeans (`DynamicMBean`), metadata is provided programmatically; in Spring-exported beans, metadata may also be generated by an assembler. Do not guess permissions solely from getter/setter names in an arbitrary Java class.

### 5.2. Metadata-Safe Utility Example

```java
import javax.management.Attribute;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxAttributeHelper {

    private JmxAttributeHelper() {}

    public static Object read(
            MBeanServerConnection connection,
            ObjectName name,
            String attribute) throws Exception {

        MBeanAttributeInfo attr = find(
            connection.getMBeanInfo(name), attribute);

        if (!attr.isReadable()) {
            throw new IllegalArgumentException(
                "Attribute is not readable: " + attribute);
        }
        return connection.getAttribute(name, attribute);
    }

    public static void write(
            MBeanServerConnection connection,
            ObjectName name,
            String attribute,
            Object value) throws Exception {

        MBeanAttributeInfo attr = find(
            connection.getMBeanInfo(name), attribute);

        if (!attr.isWritable()) {
            throw new IllegalArgumentException(
                "Attribute is not writable: " + attribute);
        }
        connection.setAttribute(name, new Attribute(attribute, value));
    }

    private static MBeanAttributeInfo find(
            MBeanInfo info,
            String attribute) {

        for (MBeanAttributeInfo candidate : info.getAttributes()) {
            if (candidate.getName().equals(attribute)) {
                return candidate;
            }
        }
        throw new IllegalArgumentException(
            "Unknown JMX attribute: " + attribute);
    }
}
```

This utility checks the name and permissions against metadata before performing the operation. It **does not perform automatic type conversion**, does not guarantee the written value is valid, and does not replace specific JMX exception handling. State or metadata can also change between the check and the operation; the server remains the authority that determines the final outcome.

The `MBeanServerConnection` interface is used so the utility can work with local or remote connections. `MBeanServer` extends similar interaction capabilities for the local JVM and additionally supports managing object registrations.

## 6. Errors to Distinguish

Read and write calls have many different failure causes. Do not lump all errors together as "JMX is not working".

| Error | When It Typically Occurs | How to Handle |
| --- | --- | --- |
| `MalformedObjectNameException` | String creating ObjectName has invalid syntax | Fix domain/key/value, use a valid `ObjectName` |
| `InstanceNotFoundException` | MBean not yet registered or wrong server/name used | Check `isRegistered(name)`, exporter, and lifecycle |
| `AttributeNotFoundException` | Wrong name or attribute does not allow requested operation | Check `MBeanInfo`, case sensitivity, and readable/writable |
| `InvalidAttributeValueException` | Written value is incompatible or rejected | Use the right type, check constraints |
| `MBeanException` | Management method implemented by MBean throws a JMX-wrapped exception | Inspect root cause, distinguish business error from connection error |
| `ReflectionException` | Reflection error while performing access | Check interface, getter/setter signatures, and MBean configuration |
| `SecurityException` or corresponding auth/permission error | Principal is not authorized to access | Check policy/roles and security configuration |
| `IOException` when using remote `MBeanServerConnection` | Connection lost, timeout, transport error | Check connector, network, and appropriate retry strategy |

Some errors are unchecked exceptions; specific behavior also depends on the MBean type and connector. `getAttributes`/`setAttributes` may skip individual failed attributes rather than throwing one error for the entire list, so you must inspect the returned result.

Example of specific read error handling:

```java
import javax.management.AttributeNotFoundException;
import javax.management.InstanceNotFoundException;
import javax.management.MBeanException;
import javax.management.ReflectionException;

try {
    Object value = server.getAttribute(name, "ActiveSessions");
    System.out.println(value);
} catch (InstanceNotFoundException ex) {
    System.err.println("MBean is not registered: " + name);
} catch (AttributeNotFoundException ex) {
    System.err.println("Readable attribute not found: ActiveSessions");
} catch (MBeanException | ReflectionException ex) {
    System.err.println("Error executing JMX getter: " + ex.getMessage());
}
```

Do not catch `Exception` and silently return `null`, because operators need to distinguish "the value is genuinely null" from "the read failed".

## 7. Relation to Spring Framework JMX

### 7.1. A Spring Bean Is Not Automatically a JMX Attribute

Spring manages beans in `ApplicationContext`. MBeanServer manages MBeans by `ObjectName`. The two registries have different identifiers and contracts.

For example, Spring `MBeanExporter` exports `TrafficMonitor` under the name:

```text
com.example.monitoring:type=TrafficMonitor,name=Main
```

Then code uses:

```java
server.getAttribute(name, "ActiveSessions");
server.setAttribute(name, new Attribute("Enabled", true));
```

without needing to call `trafficMonitor.getActiveSessions()` or `trafficMonitor.setEnabled(...)` directly. This is access through the JMX management contract, which can serve tools outside Spring.

### 7.2. Annotations and Assemblers Change the Exported Interface

If Spring exports beans using annotation metadata, `@ManagedAttribute` on getters/setters and `MetadataMBeanInfoAssembler` determine which properties are exposed. Example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=TrafficMonitor,name=Main")
public class AnnotatedTrafficMonitor {

    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Whether monitoring is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Enable or disable monitoring")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

An annotation-based bean must be supplied to an exporter configured with an annotation-reading assembler (or an equivalent annotation-driven mechanism) for the metadata to take effect. You cannot just look at annotations and assume every application context registers the MBean. Similarly, having a Java setter does not guarantee JMX writability if the assembler chooses not to export that setter.

### 7.3. Distinguishing Direct MBeanServer and Proxy

Two common access approaches:

```java
Object raw = connection.getAttribute(name, "ActiveSessions");
connection.setAttribute(name, new Attribute("Enabled", true));
```

and through a Spring proxy:

```java
public interface TrafficMonitorClient {
    int getActiveSessions();
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
```

`MBeanProxyFactoryBean` can map calls on this interface to JMX over `MBeanServerConnection`. A proxy makes client code less dependent on String names, yet it still uses the same published attributes and is still subject to JMX/transport errors. When learning how to read and write attributes, the `MBeanServer` API makes the underlying mechanism clear.

## 8. Practical Operational Scenarios

### 8.1. Observing Without Changing State

A dashboard only needs to read `ActiveSessions` periodically. A read-only attribute is appropriate because it requires no write permission and causes no management side effects. Operators still need to consider getter cost: a JMX getter invoked repeatedly can create load if it runs heavy queries or holds locks for a long time.

### 8.2. Changing Configuration Flags

When an application feature needs to be toggled at runtime, a read/write `Enabled` attribute can be exposed. Before changing it, know the semantics: does the flag affect only new requests or also in-flight requests? Is updating allowed in every state? The setter is the place to enforce invariants and can reject inappropriate operations.

Recommended operational flow:

```text
Locate ObjectName
      ↓
getMBeanInfo: confirm Enabled is readable/writable
      ↓
getAttribute("Enabled"): read initial state
      ↓
setAttribute("Enabled", false): request change
      ↓
getAttribute("Enabled"): verify observed value
      ↓
Record timestamp, operator, and outcome in operations system
```

Do not expose passwords, secrets, or sensitive data via attributes for convenience of observation. If enabling remote JMX, protect the connector with appropriate network controls, authentication, and encryption; `setAttribute` capability is a privilege that can impact a running application.

### 8.3. Multiple Attributes and Consistency

Suppose an MBean has `MinimumThreads` and `MaximumThreads`. Writing two separate attributes can produce a temporarily invalid state. The `setAttributes` API does not guarantee transactions either. A better design is:

- Enforce independent invariant checks in each setter; or
- Expose a single operation, e.g., `configureThreadPool(min, max)`, with validation and atomic updates in application logic.

For concurrent operators, you may need versioning, locks, or conditional commands at the application layer. `MBeanServer.setAttribute` does not provide compare-and-swap on its own.

## 9. Suggested Hands-on Exercise

Goal: build a Spring application with a `TrafficMonitor` MBean, read attributes, and change state.

1. Create the `TrafficMonitorMBean` interface and `TrafficMonitor` class as in section 2.
2. Configure `MBeanExporter` to register the bean in the platform `MBeanServer` under `com.example.monitoring:type=TrafficMonitor,name=Main`.
3. After the context initializes, obtain `MBeanServer` and create the corresponding `ObjectName`.
4. Call `getMBeanInfo`, confirming `ActiveSessions` is read-only and `Enabled` is read/write.
5. Call `getAttribute(name, "Enabled")` to check the initial value.
6. Call `setAttribute(name, new Attribute("Enabled", false))`; then read `Enabled` back.
7. Try `setAttribute(name, new Attribute("ActiveSessions", 42))` and observe the error from writing a read-only attribute.
8. Try reading `MissingAttribute` to see the behavior when a name does not exist.
9. If JConsole or a JMX client is available, find the ObjectName and observe state changes via the management UI.

Example runnable function from application code (once the MBean is registered):

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;

import javax.management.Attribute;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class TrafficMonitorDemo {

    private TrafficMonitorDemo() {}

    public static void run() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.monitoring:type=TrafficMonitor,name=Main");

        if (!server.isRegistered(name)) {
            throw new IllegalStateException("MBean not registered: " + name);
        }

        MBeanInfo info = server.getMBeanInfo(name);
        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf("%s: readable=%s writable=%s%n",
                attr.getName(), attr.isReadable(), attr.isWritable());
        }

        boolean before = (Boolean) server.getAttribute(name, "Enabled");
        server.setAttribute(name, new Attribute("Enabled", false));
        boolean after = (Boolean) server.getAttribute(name, "Enabled");

        System.out.printf("Enabled: %s -> %s%n", before, after);
        System.out.println(
            "ActiveSessions: " + server.getAttribute(name, "ActiveSessions"));
    }
}
```

`run()` is called **after** Spring initializes the exporter. Calling it before the MBean is registered causes `MBean not registered`, which accurately reflects a lifecycle issue and does not mean the `getAttribute` API is wrong.

Expected result: `Enabled` appears as readable/writable, `ActiveSessions` as readable but not writable; writing `Enabled` changes the value read back to `false`.

## 10. Self-Check Questions

**1. What parameters does `getAttribute` take?** An `ObjectName` identifying the MBean and a `String` for the attribute name, returning `Object`.

**2. Why does `getAttribute` return `Object`?** Because the JMX interface can serve many attribute types; the client needs to understand metadata to cast or interpret it properly.

**3. If `getActiveSessions()` exists without a setter, can `setAttribute(..., "ActiveSessions")` succeed?** No, when the MBean metadata exposes it as read-only.

**4. Does `getAttributes` always return as many names as requested?** No. You must check which names are actually present in the returned `AttributeList`.

**5. Does `setAttributes` automatically roll back if one attribute fails?** There is no transaction or rollback guarantee for the batch.

**6. If reading fails with `InstanceNotFoundException`, what should be checked?** The ObjectName, the MBeanServer being used, registration timing, and MBean lifecycle.

**7. Where is `MBeanInfo` useful?** It reveals attribute names, types, and readable/writable flags so clients know the actual JMX contract.

**8. Can `MBeanServerConnection` be used instead of `MBeanServer` for reading/writing?** Yes, the corresponding methods are declared on `MBeanServerConnection`, suitable for both local and remote connections.

## 11. Key Takeaways

- **`MBeanServer` + `ObjectName`** identifies the registry and the managed object.
- **`getAttribute`** reads a single attribute's value; **`getAttributes`** reads multiple attributes and requires checking the returned list.
- **`setAttribute`** writes a single attribute via `Attribute(name, value)`; **`setAttributes`** writes a batch but is not transactional.
- **`MBeanInfo`** is the source for discovering which attributes are readable/writable and their published data types.
- **Spring `MBeanExporter`** helps register beans into JMX; read/write permissions still depend on the actual exported MBean interface.
- After writing, **read back and verify the result**, while explicitly handling name, type, permission, and lifecycle errors.

The ability to read and write attributes via MBeanServer is the foundation of JMX management: it allows observing and controlling part of runtime state through a clear management contract, regardless of whether the caller holds a direct reference to the Spring bean.