# Retrieving MBeanInfo to Inspect the Exposed Interface

## 1. Objectives

In Java Management Extensions (JMX), an MBean can allow external callers or management tools inside the JVM to read attributes, write attributes, invoke operations, and receive notifications. Before performing those actions, a client needs to know **which management interface the MBean actually exposes**.

`MBeanServer.getMBeanInfo(ObjectName)` is the central method for discovering the management interface published by an MBean at query time. The result is an `MBeanInfo` object containing descriptors for attributes, operations, constructors, and notifications, along with the class name and description.

This lesson helps you:

- Retrieve the `MBeanInfo` of an MBean registered in `MBeanServer`.
- Distinguish descriptive metadata from runtime attribute values.
- Read `readable`, `writable`, `isIs` flags, data types, and operation signatures.
- Inspect constructors, notifications, and descriptors when available.
- Handle cases where the MBean name does not exist yet, the MBean changes, or metadata no longer matches current state.
- Identify the limits of `MBeanInfo` regarding access permissions, safety, and compatibility.

## 2. Mental Model: ObjectName → MBeanServer → MBeanInfo

\`\`\`text
JMX client
   |
   | 1. Find MBean's ObjectName
   v
MBeanServerConnection
   |
   | 2. getMBeanInfo(ObjectName)
   v
MBeanInfo
   |-- className
   |-- description
   |-- MBeanAttributeInfo[]
   |-- MBeanOperationInfo[]
   |-- MBeanConstructorInfo[]
   |-- MBeanNotificationInfo[]
   '-- Descriptor
   |
   | 3. Based on metadata, choose the appropriate call
   v
getAttribute / setAttribute / invoke / addNotificationListener ...
\`\`\`

**`ObjectName` is the address identifying an MBean in an `MBeanServer`.** It is not an HTTP path, not a Spring bean name, and not a Java class name. For example:

\`\`\`text
com.example.management:type=OrderQueue,name=Primary
\`\`\`

`MBeanServer` manages registration and access for MBeans inside the JVM. Remote clients typically work with an `MBeanServerConnection` obtained via `JMXConnector`; the same group of methods such as `getMBeanInfo` is still used.

`MBeanInfo` is an *interface structure description*—a form of schema/runtime introspection. It answers "what can be accessed and with what signatures?", rather than reading the current values of all attributes by itself.

## 3. Distinguishing Metadata from Actual Data

Suppose an MBean supports:

- Attribute `PendingCount`: type `int`, readable, not writable.
- Attribute `Paused`: type `boolean`, readable and writable.
- Operation `clearCompleted()`: no parameters, returns `void`.
- A notification warning that the queue exceeded a threshold.

Calling `getMBeanInfo` can reveal the **names and contracts** of these elements. To get the actual number of pending orders, you must separately call `getAttribute(name, "PendingCount")` or the corresponding API.

| Question | Appropriate API | Result |
|---|---|---|
| Which attributes does this MBean publish? | `getMBeanInfo` | `MBeanAttributeInfo[]` |
| Is `PendingCount` readable? | `MBeanAttributeInfo.isReadable()` | Boolean describing the interface |
| What is the current value of `PendingCount`? | `getAttribute` | Runtime value |
| Which operations does the MBean allow? | `MBeanInfo.getOperations()` | `MBeanOperationInfo[]` |
| Invoke a specific operation? | `invoke` | Execution result or exception |
| Is the MBean currently registered? | `isRegistered` | Boolean at the time of call |

A management client typically uses two phases: **discovery** via `MBeanInfo`, followed by **access** via other JMX APIs. Metadata is not a guarantee that the next call will always succeed: state, permissions, and registration can change right after discovery.

## 4. Standard Example: Defining and Registering a Standard MBean

To have concrete data for practice, first create a simple Standard MBean. A Standard MBean defines its management interface by the `<ClassName>MBean` convention.

**OrderQueueMBean.java**

\`\`\`java
package com.example.jmx;

public interface OrderQueueMBean {
    int getPendingCount();

    boolean isPaused();

    void setPaused(boolean paused);

    void clearCompleted();
}
\`\`\`

**OrderQueue.java**

\`\`\`java
package com.example.jmx;

public class OrderQueue implements OrderQueueMBean {
    private volatile int pendingCount = 12;
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return pendingCount;
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
    public void clearCompleted() {
        // An example management operation; a real implementation would process data.
        System.out.println("Clear completed orders requested");
    }
}
\`\`\`

**RegisterMBeanDemo.java**

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RegisterMBeanDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.management:type=OrderQueue,name=Primary"
        );

        server.registerMBean(new OrderQueue(), name);

        System.out.println("Registered: " + name);
        System.out.println("Registered? " + server.isRegistered(name));

        // Here you can query MBeanInfo directly within the same JVM.
    }
}
\`\`\`

In this example, the `OrderQueueMBean` interface determines which methods are exported as attributes or operations. Having additional public methods on the `OrderQueue` class **does not** automatically expose all of them through the Standard MBean.

Common classification conventions:

- `getPendingCount()` becomes attribute `PendingCount`, `readable=true`, `writable=false`.
- `isPaused()` and `setPaused(boolean)` become attribute `Paused`, `readable=true`, `writable=true`.
- `clearCompleted()` becomes operation `clearCompleted`.

Actual values in `MBeanInfo` depend on the MBean type and the specific implementation/introspection; this example illustrates a Standard MBean under normal conventions.

## 5. Retrieving MBeanInfo with MBeanServer

After registration, query the metadata:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("Class: " + info.getClassName());
System.out.println("Description: " + info.getDescription());
System.out.println("Attributes: " + info.getAttributes().length);
System.out.println("Operations: " + info.getOperations().length);
System.out.println("Constructors: " + info.getConstructors().length);
System.out.println("Notifications: " + info.getNotifications().length);
\`\`\`

**Prerequisite:** the MBean must be registered under the exact `ObjectName` in the `MBeanServer` that the client is using.

In a standalone environment, you can obtain the Platform MBeanServer:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
\`\`\`

When writing a generic client that also works with remote JMX, use `MBeanServerConnection`, because `MBeanServer` extends this interface:

\`\`\`java
import javax.management.MBeanServerConnection;

MBeanServerConnection connection = server;
MBeanInfo info = connection.getMBeanInfo(name);
\`\`\`

There is no need to cast back to `MBeanServer` to call `getMBeanInfo`. This is an important benefit when decoupling management code from how the connection is established.

### 5.1. Reading the Attribute List

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s | type=%s | readable=%s | writable=%s | isIs=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable(),
        attribute.isIs()
    );
}
\`\`\`

Meaning of the fields:

- `getName()`: attribute name published via JMX (e.g., `PendingCount`).
- `getType()`: Java type name as a string (e.g., `int`, `boolean`, `java.lang.String`).
- `isReadable()`: contract indicating the attribute can be read.
- `isWritable()`: contract indicating the attribute can be written.
- `isIs()`: whether the `is...` getter convention is used for a boolean attribute as represented in metadata.
- `getDescription()`: text description, which may be sparse or empty depending on the MBean.

**Distinguishing `isReadable()` from access permissions:** this flag describes the MBean interface; it does not mean every client is authorized to read it. In addition, the getter can still throw exceptions or encounter runtime errors.

### 5.2. Using Metadata Before Reading a Value

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public static Object readIfExposed(
        MBeanServerConnection connection,
        ObjectName objectName,
        String attributeName
) throws Exception {
    MBeanInfo info = connection.getMBeanInfo(objectName);

    for (MBeanAttributeInfo attribute : info.getAttributes()) {
        if (attribute.getName().equals(attributeName)) {
            if (!attribute.isReadable()) {
                throw new IllegalStateException(
                        "Attribute is not readable: " + attributeName
                );
            }

            return connection.getAttribute(objectName, attributeName);
        }
    }

    throw new IllegalArgumentException(
            "Attribute is not exposed: " + attributeName
    );
}
\`\`\`

Here, `getMBeanInfo` helps avoid mistakenly calling an unpublished attribute. However, between the check step and the `getAttribute` step, the MBean could be unregistered or change its interface; real calling code must still handle exceptions.

## 6. Reading Operations and Parameter Signatures

`MBeanInfo.getOperations()` returns `MBeanOperationInfo[]`. Each element describes the operation name, return type, declared impact level, and parameter list.

\`\`\`java
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s -> %s (impact=%d)%n",
        operation.getName(),
        operation.getReturnType(),
        operation.getImpact()
    );

    for (MBeanParameterInfo parameter : operation.getSignature()) {
        System.out.printf(
            "  Parameter: %s : %s%n",
            parameter.getName(),
            parameter.getType()
        );
    }
}
\`\`\`

Standard `impact` values of `MBeanOperationInfo` include:

| Constant | Suggested Meaning |
|---|---|
| `INFO` | Operation primarily provides information |
| `ACTION` | Operation can change state |
| `ACTION_INFO` | Involves both action and providing information |
| `UNKNOWN` | Impact level is not clearly specified |

**This is a metadata classification, not a safety enforcement mechanism.** An operation declaring `INFO` still needs careful review before calling. `getMBeanInfo` does not replace authorization or side-effect verification.

### 6.1. Why Do Signatures Matter?

JMX operations can be overloaded with the same name but different parameters. When invoking, the client passes all three parts: operation name, list of parameter values, and signature of parameter types.

\`\`\`java
Object result = connection.invoke(
        name,
        "clearCompleted",
        new Object[0],
        new String[0]
);
\`\`\`

For the zero-parameter example operation, both arrays are empty. For operations taking `long` or `java.lang.String`, the signature must use the types matching the JMX contract. Do not guess signatures based on the method name.

Example of another MBean with `resize(int capacity)`:

\`\`\`java
connection.invoke(
        name,
        "resize",
        new Object[] { 100 },
        new String[] { "int" }
);
\`\`\`

Only invoke this example if `getMBeanInfo` actually publishes `resize` with an `int` parameter on the queried MBean; the `OrderQueueMBean` class above does not expose this operation.

## 7. Constructors, Notifications, and Descriptors

Besides attributes and operations, `MBeanInfo` also returns metadata about constructors and notifications.

### 7.1. Constructors

\`\`\`java
import javax.management.MBeanConstructorInfo;
import javax.management.MBeanParameterInfo;

for (MBeanConstructorInfo constructor : info.getConstructors()) {
    System.out.println("Constructor: " + constructor.getName());

    for (MBeanParameterInfo parameter : constructor.getSignature()) {
        System.out.printf(
            "  %s : %s%n",
            parameter.getName(),
            parameter.getType()
        );
    }
}
\`\`\`

The constructors list may be empty depending on how the MBean is exported and the MBean type. It describes constructor information in JMX metadata; **it does not mean clients can instantiate more instances simply by calling `getMBeanInfo`**. Creating MBeans (if permitted) is a separate operation through the appropriate MBeanServer API.

### 7.2. Notifications

\`\`\`java
import javax.management.MBeanNotificationInfo;

for (MBeanNotificationInfo notification : info.getNotifications()) {
    System.out.println("Description: " + notification.getDescription());

    for (String type : notification.getNotifTypes()) {
        System.out.println("  Notification type: " + type);
    }
}
\`\`\`

`MBeanNotificationInfo` indicates the advertised notification types. It **does not** contain notification history and does not register a listener. To receive notifications, a client must use `addNotificationListener` when the MBean supports it and the connection and permissions allow. Not every MBean emits notifications.

### 7.3. Descriptors

The `MBeanInfo` object and many of its metadata elements can carry a `Descriptor`, a collection of `name → value` fields used to describe extended information. Specific metadata varies across Standard MBeans, MXBeans, Dynamic MBeans, framework exporters, or JMX providers.

\`\`\`java
import javax.management.Descriptor;

Descriptor descriptor = info.getDescriptor();

for (String fieldName : descriptor.getFieldNames()) {
    System.out.println(
            fieldName + " = " + descriptor.getFieldValue(fieldName)
    );
}
\`\`\`

You can also inspect descriptors on metadata components:

\`\`\`java
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    Descriptor attributeDescriptor = attribute.getDescriptor();
    System.out.println(
            attribute.getName() + ": "
                    + java.util.Arrays.toString(
                            attributeDescriptor.getFieldNames()
                    )
    );
}
\`\`\`

Across MBean variants, descriptors can contain information such as MXBean type details or extra properties. Do not force clients to require a descriptor field that is not part of a verified contract.

## 8. Complete Program to Explore an MBean Interface

The Java example below registers `OrderQueue`, then reads and displays its metadata. The `OrderQueueMBean` and `OrderQueue` files use the code from section 4.

**InspectMBeanInfo.java**

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.Descriptor;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanConstructorInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class InspectMBeanInfo {

    private InspectMBeanInfo() {
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.management:type=OrderQueue,name=Primary"
        );

        if (!server.isRegistered(name)) {
            server.registerMBean(new OrderQueue(), name);
        }

        MBeanInfo info = server.getMBeanInfo(name);

        System.out.println("MBean: " + name);
        System.out.println("Implementation class: " + info.getClassName());
        System.out.println("Description: " + info.getDescription());

        System.out.println("\n=== ATTRIBUTES ===");
        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                    "%s : %s [read=%s, write=%s, is=%s]%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable(),
                    attribute.isIs()
            );
        }

        System.out.println("\n=== OPERATIONS ===");
        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.print(
                    operation.getName() + "("
            );

            MBeanParameterInfo[] parameters = operation.getSignature();
            for (int i = 0; i < parameters.length; i++) {
                if (i > 0) {
                    System.out.print(", ");
                }
                System.out.print(
                        parameters[i].getType() + " "
                                + parameters[i].getName()
                );
            }

            System.out.println(") -> " + operation.getReturnType());
        }

        System.out.println("\n=== CONSTRUCTORS ===");
        for (MBeanConstructorInfo constructor : info.getConstructors()) {
            System.out.println(constructor.getName());
        }

        System.out.println("\n=== NOTIFICATIONS ===");
        for (MBeanNotificationInfo notification : info.getNotifications()) {
            System.out.println(notification.getDescription());
        }

        System.out.println("\n=== DESCRIPTOR FIELDS ===");
        Descriptor descriptor = info.getDescriptor();
        for (String fieldName : descriptor.getFieldNames()) {
            System.out.println(
                    fieldName + "=" + descriptor.getFieldValue(fieldName)
            );
        }

        System.out.println("\n=== RUNTIME READ ===");
        System.out.println(
                "PendingCount=" + server.getAttribute(name, "PendingCount")
        );
    }
}
\`\`\`

**What to observe:** the lines in the `ATTRIBUTES` and `OPERATIONS` sections come from metadata. The final `PendingCount=12` line is obtained via `getAttribute`, not extracted from `MBeanInfo`.

You can compile with JDK 21 in the package-structured source directory, then run the `com.example.jmx.InspectMBeanInfo` class. No external libraries are required: the `javax.management` APIs are part of the Java platform. If the application uses a custom module runtime, ensure the `java.management` module is provided.

## 9. Discovering MBeans Without Knowing Names Ahead of Time

In practice, a client may not know the full `ObjectName`. Use `queryNames` to list matching MBeans before calling `getMBeanInfo`.

\`\`\`java
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

ObjectName pattern = new ObjectName(
        "com.example.management:type=OrderQueue,*"
);

Set<ObjectName> names = connection.queryNames(pattern, null);

for (ObjectName candidate : names) {
    System.out.println("Found: " + candidate);
    System.out.println(
            "Attributes: "
                    + connection.getMBeanInfo(candidate)
                            .getAttributes().length
    );
}
\`\`\`

Here `ObjectName` is a **pattern**. The `*` wildcard matches remaining key properties according to `ObjectName` rules. If multiple MBeans exist, handle each name individually; do not treat the `queryNames` result as a single MBean.

`queryNames` serves discovery, but the system can change between returning the set of names and calling `getMBeanInfo`. Handle cases where an MBean is unregistered during iteration.

### 9.1. When Should You Inspect the Class Name?

`MBeanInfo.getClassName()` returns the class name described in metadata. It is useful for identifying object types and assisting diagnostics, but you **should not rely exclusively** on class names when building a JMX client. Standard MBeans, Dynamic MBeans, MXBeans, or proxies/adapters can change how the class name is represented. When coding interactions, rely on attribute/operation metadata and the required interface contract.

## 10. Spring Framework JMX: How Does MBeanInfo Help?

In a Spring application, a bean can be exported as a JMX MBean via `MBeanExporter` and annotations such as `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
        objectName = "com.example.management:type=Cache,name=Main",
        description = "Cache management"
)
public class CacheMonitor {

    private volatile boolean enabled = true;

    @ManagedAttribute
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation
    public void clearCache() {
        // Actual cache-clearing logic is implemented here.
    }
}
\`\`\`

Once the Spring JMX exporter is configured and the bean is exported successfully, a JMX client can call `getMBeanInfo` with the registered `ObjectName` to inspect the interface **actually exposed**, rather than guessing solely from annotations.

This is especially useful when:

- Annotations are present on the class, but the exporter has not run or did not scan that bean.
- The actual attribute name differs from what the client expected.
- A method does not appear as an operation due to assembler/exposure rules.
- The interface changed after an application upgrade.
- A client needs to dynamically build a status view page from metadata.

Note: Spring annotations are not standalone JMX registrations. `@Component` creates a Spring bean, but for it to appear in MBeanServer, the application needs appropriate JMX export configuration; an arbitrary Spring bean does not automatically show up in `queryNames`.

### 10.1. Verifying the Interface That Spring Actually Exports

Suppose you want to confirm that the `CacheMonitor` bean has exposed the `Enabled` attribute and the `clearCache` operation:

\`\`\`java
ObjectName cacheName = new ObjectName(
        "com.example.management:type=Cache,name=Main"
);

MBeanInfo cacheInfo = connection.getMBeanInfo(cacheName);

boolean hasEnabled = false;

for (MBeanAttributeInfo attribute : cacheInfo.getAttributes()) {
    if ("Enabled".equals(attribute.getName())
            && attribute.isReadable()
            && attribute.isWritable()) {
        hasEnabled = true;
    }
}

boolean hasClearCache = false;

for (MBeanOperationInfo operation : cacheInfo.getOperations()) {
    if ("clearCache".equals(operation.getName())
            && operation.getSignature().length == 0) {
        hasClearCache = true;
    }
}

System.out.println("Enabled attribute exposed: " + hasEnabled);
System.out.println("clearCache operation exposed: " + hasClearCache);
\`\`\`

This is a runtime contract verification technique. If the result does not match expectations, check the exporter configuration, annotation mapping strategy, and the `ObjectName` being queried.

## 11. Remote JMX Client: Same API, Different Connection Path

A client running outside the application JVM typically uses `JMXConnectorFactory` to open a JMX connection. Once connected, `getMBeanInfo` still works via `MBeanServerConnection`.

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteInspectDemo {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
                "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );

        try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
            MBeanServerConnection connection =
                    connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                    "com.example.management:type=OrderQueue,name=Primary"
            );

            MBeanInfo info = connection.getMBeanInfo(name);

            System.out.println("Class: " + info.getClassName());
            System.out.println(
                    "Exposed attributes: " + info.getAttributes().length
            );
        }
    }
}
\`\`\`

The `localhost:9010` address is illustrative only; it works when the server has configured remote JMX appropriately, including the registry/RMI endpoint and required connection conditions. Do not expose remote JMX publicly just to run an example. When connecting over a real network, use proper security configuration, authentication, and transport protection.

Remote JMX can fail because the endpoint is not running, firewall/NAT issues, RMI hostname settings, authentication, or authorization; those are connection-path failures, not proof that an MBean's MBeanInfo is missing.

## 12. Exceptions to Handle

`getMBeanInfo` declares important checked exceptions on `MBeanServerConnection`, such as:

| Exception | Common Cause | How to Handle |
|---|---|---|
| `InstanceNotFoundException` | No MBean registered under that `ObjectName` at the time of call | Check the name, registration timing, and possible unregistration |
| `IntrospectionException` | Unable to introspect the MBean to construct metadata | Check MBean/exporter type and root exception |
| `ReflectionException` | Reflection error while retrieving MBean information | Check underlying exception and MBean implementation |
| `IOException` | Communication error over `MBeanServerConnection`, especially remote | Check connection, endpoint, and network |
| `SecurityException` | Security policy denies the operation | Grant appropriate permissions; do not bypass controls |

In addition, read/write/invoke APIs may throw other exceptions. Do not treat `getMBeanInfo` as proof that every operation will succeed when invoked.

Example handling common failure modes:

\`\`\`java
import java.io.IOException;
import javax.management.InstanceNotFoundException;
import javax.management.IntrospectionException;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.ReflectionException;

public static MBeanInfo inspect(
        MBeanServerConnection connection,
        ObjectName name
) throws IOException {
    try {
        return connection.getMBeanInfo(name);
    } catch (InstanceNotFoundException e) {
        throw new IllegalStateException(
                "MBean no longer registered: " + name, e
        );
    } catch (IntrospectionException | ReflectionException e) {
        throw new IllegalStateException(
                "Cannot inspect management interface: " + name, e
        );
    }
}
\`\`\`

The example above lets `IOException` propagate to the connection management layer; `SecurityException` can also propagate for the authorization management layer to handle. In real applications, errors can be mapped to diagnostic states and logged safely according to product requirements.

## 13. Is MBeanInfo "Valid Forever"?

Not necessarily. There are two reasons:

1. **Dynamic MBeans** can return metadata dynamically; the published interface can change depending on configuration or state.
2. **Registration lifecycle:** the same `ObjectName` can be unregistered and re-registered with a different MBean; information stored in an old cache may no longer apply.

Therefore, clients can cache `MBeanInfo` to reduce calls when the contract is stable, but need a refresh mechanism upon reconnecting, on configuration changes, when operations fail due to mismatched names/types, or according to application policy.

### 13.1. What MBeanInfo Does Not Guarantee

- Does not guarantee attribute values at the moment a subsequent operation is called.
- Does not verify every user's permissions just because metadata is readable.
- Does not guarantee an operation is idempotent or free of side effects.
- Does not expose an object's entire internal state beyond what the MBean publishes.
- Does not automatically list Spring beans that have not been registered as MBeans.
- Is not REST API documentation or a source of historical metric data.
- Does not promise that all descriptors or descriptions contain useful information.

## 14. Reading the Result with a "Management Interface" Mindset

When viewing an `MBeanInfo`, analyze it in order:

1. **Identity:** Is the queried `ObjectName` the right MBean of interest?
2. **Type:** What do `className` and `description` say about the object?
3. **Attributes:** Which data can be viewed/written, what are the types, and how should runtime values be handled?
4. **Operations:** Which actions is the client designed to invoke, what parameters are required, and what consequences might occur?
5. **Notifications:** Which event types does the MBean advertise, and is registering a listener needed?
6. **Descriptors:** Is there any extended metadata relevant to the MBean type or tooling?
7. **Security and timing:** Does the connection have permission to proceed, and is the MBean still registered?

Through this, `MBeanInfo` becomes a **runtime-discoverable technical contract**, especially helpful for automated operations tooling or when you do not want to hardcode every MBean property.

## 15. Self-Check

**Q1.** Does `getMBeanInfo` return the current value of `PendingCount`?  
**Answer:** No. It returns information describing the attribute, whereas the value is obtained with `getAttribute`.

**Q2.** Which API shows what parameters an operation has?  
**Answer:** `MBeanInfo.getOperations()` → each `MBeanOperationInfo.getSignature()` → `MBeanParameterInfo` elements.

**Q3.** Does `MBeanAttributeInfo.isWritable()` returning true mean everyone is allowed to write?  
**Answer:** No. That is metadata about writability; actual access permission still depends on security policies and MBean state.

**Q4.** `queryNames` returns an `ObjectName`, but `getMBeanInfo` then throws `InstanceNotFoundException`. Is that a contradiction?  
**Answer:** No. The MBean could have been unregistered between the two calls.

**Q5.** When exporting a Spring bean via JMX, why inspect the actual `MBeanInfo`?  
**Answer:** To know the exact list of attributes/operations that the exporter registered and published, rather than guessing from Spring bean names or annotations.

**Q6.** `getNotifications()` returns notification metadata. How do you receive events?  
**Answer:** Register a `NotificationListener` through the appropriate JMX API when the MBean supports it and access is permitted.

## 16. Summary

- **`MBeanServerConnection.getMBeanInfo(ObjectName)`** is the entry point for discovering the JMX management interface actually published.
- **`MBeanInfo` holds metadata:** class name, description, attributes, operations, constructors, notifications, and descriptor.
- **`MBeanAttributeInfo`** tells you names, types, and readability/writability; **`MBeanOperationInfo`** tells you names, return types, parameter signatures, and declared impact levels.
- **Reading metadata is different from reading values or executing actions.** Use `getAttribute`, `setAttribute`, `invoke`, or notification listeners when interacting.
- Metadata can change, access permissions can be restricted, and MBeans can disappear between two calls. Clients must handle these conditions in operation.

### References

- Java SE API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE API — MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE API — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE API — MBeanOperationInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Oracle JMX Tutorial: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
