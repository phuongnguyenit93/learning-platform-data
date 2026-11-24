# Creating Read-Write Attributes with Getters and Setters in Spring JMX `@ManagedAttribute`

## 1. What Is an Attribute in JMX?

In Java Management Extensions (**JMX**), an **attribute** is a state value that management tools can read, write, or both read and write through an MBean. When integrating Spring Framework JMX, `@ManagedAttribute` declares a Spring bean's getter or setter method as part of the management interface.

For example, a bean with state:

```java
private volatile boolean enabled = true;
```

We can expose that state to JConsole under the attribute name **Enabled**, making it readable and editable if we simultaneously export both the appropriate getter and setter:

```java
@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}

@ManagedAttribute
public void setEnabled(boolean enabled) {
    this.enabled = enabled;
}
```

In JMX, the **getter** provides read capability; the **setter** provides write capability. If the two methods form a valid pair with the same property name and data type, management tools usually see **a single read/write attribute**, not two separate attributes.

It is important to distinguish:

- **Java property**: the bean's pair of `getXxx()`/`setXxx(...)` or `isXxx()`/`setXxx(...)` methods.
- **JMX attribute**: the name, type, read/write permissions, and metadata exposed by the MBean.
- **Spring `@ManagedAttribute`**: the annotation that helps Spring build JMX metadata from bean methods.
- **MBeanServer**: where management tools perform `getAttribute` and `setAttribute` on a registered `ObjectName`.

## 2. Mechanism for Mapping Getters/Setters to Attributes

Given a bean:

```java
public class WorkerSettings {
    private int maxWorkers = 8;

    public int getMaxWorkers() {
        return maxWorkers;
    }

    public void setMaxWorkers(int maxWorkers) {
        this.maxWorkers = maxWorkers;
    }
}
```

By JavaBeans conventions, the property named `maxWorkers` has a getter and a setter. In the JMX interface, the attribute name is typically exposed with a capitalized first letter: **MaxWorkers**.

If using an annotation-based exporter:

```java
@ManagedAttribute
public int getMaxWorkers() { /* ... */ }

@ManagedAttribute
public void setMaxWorkers(int maxWorkers) { /* ... */ }
```

then Spring can build metadata like this:

```text
ObjectName: com.example.jobs:type=WorkerSettings,name=background

Attribute: MaxWorkers
Type:      int
Readable:  true
Writable:  true
Is-is:     false
```

### Common Naming Conventions

| Java method | JMX attribute | Meaning |
| --- | --- | --- |
| `getMaxWorkers()` | `MaxWorkers` | Getter enabling read access |
| `setMaxWorkers(int)` | `MaxWorkers` | Setter enabling write access |
| `isEnabled()` | `Enabled` | Boolean getter using `is` style |
| `setEnabled(boolean)` | `Enabled` | Boolean setter |
| `getActiveCount()` | `ActiveCount` | Getter without setter, typically read-only |
| `setMaintenanceMode(boolean)` | `MaintenanceMode` | Setter without getter, potentially write-only |

How Spring maps methods to JMX metadata also depends on the exporter and assembler in use. Merely having a method in the class does not guarantee it is exported; with the annotation mechanism, you must mark the right methods and enable an appropriate exporter.

## 3. Complete Example: A Read-Write Attribute

Create a Spring bean with `@ManagedResource` and two `@ManagedAttribute` annotations:

```java
package com.example.jobs.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerSettings,name=background",
    description = "Settings for background workers"
)
public class WorkerSettingsManagement {

    private volatile int maxWorkers = 8;

    @ManagedAttribute(
        description = "Maximum allowed worker count"
    )
    public int getMaxWorkers() {
        return maxWorkers;
    }

    @ManagedAttribute(
        description = "Update maximum allowed worker count"
    )
    public void setMaxWorkers(int maxWorkers) {
        if (maxWorkers < 1 || maxWorkers > 128) {
            throw new IllegalArgumentException(
                "maxWorkers must be between 1 and 128"
            );
        }
        this.maxWorkers = maxWorkers;
    }
}
```

This bean has a JMX attribute named `MaxWorkers`:

- When a client reads it, the MBean calls the getter and returns the current value.
- When a client writes it, the MBean passes the new value to the setter.
- The setter validates the value range from 1 to 128.
- The `volatile` field ensures threads see the latest `int` value according to Java Memory Model semantics.

**Architecture note:** the example only changes a configuration variable. In a real system, changing `maxWorkers` must be accompanied by logic applying it to the actual executor or scheduler; changing a variable without applying it to the underlying resource can cause the JMX UI to show the new configuration while application behavior remains unchanged.

### Configuring the Exporter

Annotations only produce metadata when a corresponding exporter is present:

```java
package com.example.jobs.management;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class JmxManagementConfiguration {

    @Bean
    static AnnotationMBeanExporter annotationMBeanExporter() {
        return new AnnotationMBeanExporter();
    }
}
```

In a Spring Boot application, the JMX mechanism may be configured or auto-configured separately depending on version and properties. If an exporter already exists, avoid creating a duplicate exporter registering the same ObjectName.

In the example, `@Component` ensures the bean is discovered by Spring if the package is within component scan scope. `@ManagedResource` provides management metadata. `AnnotationMBeanExporter` handles exporting the bean to the MBeanServer.

## 4. Reading and Writing Attributes via MBeanServer

You can interact using the Java API:

```java
import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class WorkerSettingsClient {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.jobs:type=WorkerSettings,name=background"
        );

        Object before = server.getAttribute(
                name,
                "MaxWorkers"
        );
        System.out.println("Before: " + before);

        server.setAttribute(
                name,
                new Attribute("MaxWorkers", 16)
        );

        Object after = server.getAttribute(
                name,
                "MaxWorkers"
        );
        System.out.println("After: " + after);
    }
}
```

This client snippet assumes the bean was registered by the exporter in **the same MBeanServer/JVM**. If run as a separate standalone Java program, that program's `getPlatformMBeanServer()` will not automatically access MBeans in the application JVM. For remote access, an `MBeanServerConnection` via an appropriate JMX connector is required.

Expected output when the initial value is 8:

```text
Before: 8
After: 16
```

`getAttribute` takes the **JMX attribute name**, not the Java method name. Therefore use `MaxWorkers`, not `getMaxWorkers`. `setAttribute` takes a `javax.management.Attribute` object containing the name and the value to write.

## 5. Distinguishing Read-Only, Write-Only, and Read/Write

Read and write permissions are part of the MBean metadata.

### 5.1. Read-Only Attribute

```java
@ManagedAttribute
public long getProcessedCount() {
    return processedCount;
}
```

No corresponding setter is exposed. The MBean typically shows:

```text
ProcessedCount: readable=true, writable=false
```

This is the right choice for counters, uptime, thread counts, or state that should only be observed.

### 5.2. Write-Only Attribute

```java
@ManagedAttribute
public void setMaintenanceMode(boolean mode) {
    this.maintenanceMode = mode;
}
```

If the metadata mechanism supports setter-only properties and no getter is exposed, the attribute can be write-only:

```text
MaintenanceMode: readable=false, writable=true
```

However, write-only attributes are often hard to operate because clients do not know the current state. When you need to change state without providing a readable value, consider a clearly named **operation**, such as `enableMaintenance()`, instead of a hard-to-verify setter.

### 5.3. Read-Write Attribute

```java
@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}

@ManagedAttribute
public void setEnabled(boolean enabled) {
    this.enabled = enabled;
}
```

Expected metadata:

```text
Enabled: readable=true, writable=true
```

Use this style when operators need to both view and adjust state, such as toggling a feature that is designed to be changeable at runtime.

### Selection Table

| Need | Getter | Setter | Suggestion |
| --- | --- | --- | --- |
| Observe a metric only | Yes | No | Read-only attribute |
| Adjust runtime configuration | Yes | Yes | Read/write attribute |
| Send command without reading value | Optional | Optional | Usually use an operation |
| Major state-changing action | N/A | N/A | `@ManagedOperation` |
| Sensitive configuration | Depends on requirement | Depends on requirement | Restrict permissions, consider not exporting |

## 6. Boolean Getters: getXxx and isXxx

According to JavaBeans and JMX conventions, booleans typically use `isXxx()` getters:

```java
private boolean enabled;

@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}

@ManagedAttribute
public void setEnabled(boolean enabled) {
    this.enabled = enabled;
}
```

JMX can mark `MBeanAttributeInfo.isIs() == true` for `isXxx`-style boolean getters.

You can use `getEnabled()` for boolean properties in many contexts, but be consistent across the getter, setter, and introspection rules. For wrapper `Boolean`, use `getEnabled()` rather than assuming `isEnabled()` is recognized the same way as primitive `boolean` by every mechanism.

### Common Mistakes

```java
public boolean isEnabled() { ... }
public void setIsEnabled(boolean value) { ... }
```

These two methods can be interpreted as different properties (`Enabled` and `IsEnabled`), making the author think they created a read-write attribute while metadata fails to pair them as expected.

Use the proper form:

```java
public boolean isEnabled() { ... }
public void setEnabled(boolean value) { ... }
```

## 7. Setter Parameter Type Must Match the Getter

A valid read-write attribute requires consistent data types:

```java
@ManagedAttribute
public int getPoolSize() {
    return poolSize;
}

@ManagedAttribute
public void setPoolSize(int poolSize) {
    this.poolSize = poolSize;
}
```

Do not pair an `int` getter with a `String` setter:

```java
public int getPoolSize() { ... }
public void setPoolSize(String value) { ... }
```

Two methods with incompatible types can prevent JavaBeans introspection or JMX metadata from identifying a read/write property as intended.

When a client writes via `MBeanServerConnection.setAttribute`, the value type must match the declared type. For example, if `MaxWorkers` is `int`, a Java client should pass `Integer`. Writing the string `"16"` should not be assumed to convert automatically to an integer in every JMX client.

## 8. MBeanInfo Shows Whether an Attribute Is Truly Read-Write

Instead of inferring from source code, clients can read the actual registered metadata:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class AttributeInspector {

    public static void inspect(
            MBeanServerConnection connection,
            ObjectName name
    ) throws Exception {
        MBeanInfo info = connection.getMBeanInfo(name);

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                "%s: type=%s, readable=%s, writable=%s, isIs=%s%n",
                attribute.getName(),
                attribute.getType(),
                attribute.isReadable(),
                attribute.isWritable(),
                attribute.isIs()
            );
        }
    }
}
```

An attribute with:

```text
MaxWorkers: type=int, readable=true, writable=true, isIs=false
```

means metadata permits clients to read and write. However, **metadata does not guarantee every write will succeed**: the setter can reject the value, business logic can fail, or the user may lack permissions.

Conversely, when an attribute is read-only, tools generally do not provide an edit field or write operations are rejected.

### Why Inspect Runtime Metadata?

Source code might have both getter and setter, yet:

- The setter was not annotated with `@ManagedAttribute`.
- The exporter does not use annotation metadata as expected.
- The bean was exported through an interface containing only the getter.
- The actual class is a proxy or a different bean.
- The metadata assembler restricts the set of methods.
- The ObjectName points to an MBean registered by another exporter.

`MBeanInfo` is the authoritative check for the actual JMX interface seen by clients.

## 9. Spring Demo with Multiple Attribute Types

```java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=JobProcessor,name=default",
    description = "Runtime job processor management"
)
public class JobProcessorManagement {

    private final AtomicLong processed = new AtomicLong();
    private volatile boolean enabled = true;
    private volatile int maxParallelism = 4;

    @ManagedAttribute(
        description = "Total number of completed jobs"
    )
    public long getProcessedCount() {
        return processed.get();
    }

    @ManagedAttribute(
        description = "Whether job processing is enabled"
    )
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedAttribute(
        description = "Maximum parallel workers"
    )
    public int getMaxParallelism() {
        return maxParallelism;
    }

    @ManagedAttribute
    public void setMaxParallelism(int value) {
        if (value < 1 || value > 32) {
            throw new IllegalArgumentException(
                "maxParallelism must be in range 1..32"
            );
        }
        maxParallelism = value;
    }

    // Ordinary business/internal method.
    public void recordCompletion() {
        processed.incrementAndGet();
    }
}
```

Expected in JConsole:

| JMX attribute | Type | Read | Write |
| --- | --- | --- | --- |
| `ProcessedCount` | `long` | Yes | No |
| `Enabled` | `boolean` | Yes | Yes |
| `MaxParallelism` | `int` | Yes | Yes |

`recordCompletion()` is a regular Java method not declared as a management operation. With an annotation exporter, it should not be automatically exposed simply because the method is public.

**Real-world application:** if `setMaxParallelism()` needs to update a real executor, the setter must call the appropriate update API. The demo only keeps flags and counters to clarify attribute mapping.

## 10. Practicing in JConsole

Assuming the application is running and the exporter has registered:

```text
com.example:type=JobProcessor,name=default
```

Steps:

1. Open `jconsole` from the JDK and connect to the right JVM.
2. Select the **MBeans** tab.
3. Expand the `com.example` domain and select the MBean with the ObjectName above.
4. Go to the **Attributes** section.
5. View `ProcessedCount`: read-only.
6. View `Enabled`: can be toggled between `true` and `false` if client/permissions allow.
7. View `MaxParallelism`: test a valid value in a practice environment.
8. Re-read the attribute to verify the state has been updated.
9. When entering a value outside the valid range, observe how the setter error is returned to the client.

Before changing an attribute on a production system, make sure it is designed for runtime management. A setter can change service behavior immediately.

### How JConsole Displays Data Types

Depending on the client, attributes may be presented in a table and support inline editing if metadata allows. Not every complex type has a corresponding editor. For `int`, `boolean`, and `String` types, interaction is usually simpler.

## 11. Testing Writes via the JMX API

Reading and writing by `ObjectName`:

```java
import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxAttributeWriter {

    public static void updateMaxParallelism(
            MBeanServerConnection connection
    ) throws Exception {
        ObjectName name = new ObjectName(
            "com.example:type=JobProcessor,name=default"
        );

        Object before = connection.getAttribute(
                name,
                "MaxParallelism"
        );

        connection.setAttribute(
                name,
                new Attribute("MaxParallelism", 6)
        );

        Object after = connection.getAttribute(
                name,
                "MaxParallelism"
        );

        System.out.println(
                "MaxParallelism: " + before + " -> " + after
        );
    }
}
```

This is a standard API common to both local and remote connections. `MBeanServer` extends `MBeanServerConnection`. For remote access, the application obtains the connection from a `JMXConnector` after connecting.

When the setter throws an error, `setAttribute` can throw a corresponding exception. Do not assume every write succeeds just because the attribute metadata says `writable=true`.

## 12. Validation: The Setter Remains a Protective Boundary

A getter/setter exposed via JMX can receive input from a management client in another process. Therefore, the setter must validate data and business conditions just like any other public API.

Example:

```java
@ManagedAttribute
public void setMaxPoolSize(int size) {
    if (size < 1 || size > 64) {
        throw new IllegalArgumentException(
            "Pool size must be in range 1..64"
        );
    }

    // Apply to a real managed executor here.
    executor.setMaximumPoolSize(size);
}
```

Keep in mind that `ThreadPoolExecutor` has a relationship between core pool size and maximum pool size; changing limits out of order can throw `IllegalArgumentException`. The snippet above only illustrates setter validation, not complete logic for resizing every executor.

Steps for designing a good setter:

- Define the valid value range.
- Check correlations with other configuration settings.
- Apply changes to the real resource in a safe order.
- On failure, avoid leaving metadata or recorded state out of sync with runtime.
- Log/audit significant operations as required.
- Avoid performing very long-running tasks under a synchronous JMX call when avoidable.

The getter should reflect **the currently applied state** or clearly state that it is the **requested** value; avoid a `MaxWorkers` attribute where clients think a change was applied while the executor still runs with the old limit.

## 13. Thread Safety and Consistency

JMX does not automatically protect bean state from concurrent access.

For example:

```java
private volatile boolean enabled;
```

is suitable for a simple boolean flag because reads/writes see the latest value under the Java Memory Model. However, for configurations with multiple related fields:

```java
private int minWorkers;
private int maxWorkers;
```

updating each field separately can allow a thread to observe an invalid intermediate state.

Solutions depend on business requirements:

- Use an immutable configuration object with a `volatile`/atomic reference to swap atomically.
- Use `synchronized`/locks appropriately when modifying multiple fields.
- Bundle related changes into a single management operation accepting all parameters.
- Avoid exposing independent setters for each value if they must not be changed independently.

For counters, use `AtomicLong`, `LongAdder`, or snapshots as needed. Clearly separate read-write properties from operations with complex business behavior.

## 14. Should Getters and Setters Share the Same Description?

`@ManagedAttribute` can carry descriptive metadata on methods. When an attribute has both a getter and a setter, the Spring assembler must aggregate metadata into a single `MBeanAttributeInfo` or `ModelMBeanAttributeInfo`.

Write descriptions in terms of the **attribute**'s meaning, not the individual Java method action:

```java
@ManagedAttribute(
    description = "Maximum number of concurrent workers"
)
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute
public void setMaxWorkers(int value) {
    this.maxWorkers = value;
}
```

In practice, the exporter/assembler determines how descriptors are merged. If getter and setter metadata conflict, inspect the actual `MBeanInfo` instead of relying on assumed precedence rules.

Additional operational details such as units, valid ranges, and change impact can be placed in the description or accompanying operational documentation.

## 15. Spring Beans and JMX Attributes Are Two Separate Contracts

A class:

```java
public class QueueService {
    public long getPendingCount() { ... }
    public void setProcessingEnabled(boolean enabled) { ... }
    public void submitJob(Job job) { ... }
}
```

may be used by many different parts of the application. Exporting the entire class directly can blur the boundary between the business API and the JMX API.

A cleaner design is an adapter:

```java
@ManagedResource(
    objectName = "com.example:type=QueueControl,name=orders"
)
public class QueueControl {
    private final QueueService service;

    public QueueControl(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return service.getPendingCount();
    }

    @ManagedAttribute
    public boolean isProcessingEnabled() {
        return service.isProcessingEnabled();
    }

    @ManagedAttribute
    public void setProcessingEnabled(boolean enabled) {
        service.setProcessingEnabled(enabled);
    }
}
```

`QueueService` and `Job` in the example are illustrative business types. The adapter restricts exactly which properties are exported. Add a managed setter only when you genuinely want JMX clients to be able to change state.

## 16. Common Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Attribute not visible | Bean not exported, missing annotation, or wrong ObjectName | Exporter, `@ManagedResource`, MBeanServer |
| Attribute read-only despite having a setter | Setter not exposed in metadata | Annotation, assembler, `MBeanInfo.isWritable()` |
| Getter/setter become two different properties | Naming does not follow the same convention | `getXxx/isXxx` and `setXxx` |
| Type error when writing | Value does not match metadata type | `MBeanAttributeInfo.getType()` |
| `AttributeNotFoundException` | Wrong JMX attribute name | Use the exact name in `MBeanInfo` |
| `InvalidAttributeValueException` | Invalid or incompatible value | Validation and data type |
| `MBeanException` | Error from getter/setter code or resource | Exception cause and business logic |
| Write succeeds but behavior does not change | Setter only changed config variable without updating resource | Check runtime application logic |
| Read returns stale value | Metadata caching, polling, synchronization | Currency time limit and thread safety |
| No editor in tool | Client does not support data type or write permission | Metadata/client capabilities |
| Another bean has the same ObjectName | Duplicate exporter registration | Naming and registration policy |

### Distinguishing Setter Errors from Metadata

Metadata `writable=true` only indicates the attribute has a write path. The setter can still reject a new value when invalid. If a write fails, inspect the client exception and application logs to determine whether the failure came from type conversion, validation, or internal logic.

## 17. Special Cases

### 17.1. Setter Without Getter

An MBean can expose a write-only attribute if the exporter/assembler mechanism supports it. However, being unable to read back state makes operations hard to verify. Consider an operation if the action resembles "sending a command" rather than "setting a property value."

### 17.2. Expensive Getters

A JMX getter may be invoked periodically by monitoring tools. Avoid getters that execute large database queries, network calls, or long-held locks. If measurement is costly, intentionally use a snapshot/cache and document data latency.

### 17.3. Multiple Overloaded Setters

For example:

```java
void setLimit(int value);
void setLimit(String value);
```

Introspection can become ambiguous. For JMX, keep one clear type per attribute and use separate operations when multiple input representations are needed.

### 17.4. Changing Types

If clients currently read `MaxWorkers` as `int`, changing it to `long` can break dashboards or Java clients. Attribute names, types, and read/write permissions are part of the management contract that should remain stable.

### 17.5. Remote Management

A client in another JVM using remote JMX interacts through `MBeanServerConnection`; do not assume arbitrary custom objects can cross JVM boundaries easily. For complex data, consider MXBeans and Open Types. Secure remote JMX connections with authentication, TLS, and proper network controls.

## 18. When to Use @ManagedOperation Instead of a Setter?

Getters/setters are appropriate when the state is a meaningful property that can be set to a valid value:

```text
Enabled = true/false
MaxWorkers = 8/16
LoggingLevel = INFO/DEBUG
```

For actions such as:

```text
clearCache()
reloadConfiguration()
rebuildIndex()
rotateCredentials()
```

expose them as operations, for example:

```java
@ManagedOperation(
    description = "Reload application configuration"
)
public void reloadConfiguration() {
    // Deliberate management operation.
}
```

Do not create a fake setter like `setReload(true)` just to trigger a side effect, unless it is genuinely state with a clear contract. Operations convey the meaning of "executing an action" much better.

## 19. Self-Check Questions

**1. What are the conditions for a getter and setter to create a read-write attribute?**

They must share the same conventional property name, have compatible data types, and both be exposed in JMX metadata.

**2. Which setter pairs with the `isEnabled()` getter?**

`setEnabled(boolean enabled)`, not `setIsEnabled(...)`.

**3. Why might `MBeanInfo` report read-only when both getter and setter exist in the class?**

The setter might not be annotated with `@ManagedAttribute` or may have been excluded from the export contract by an interface/assembler.

**4. Does `writable=true` guarantee writing any value will succeed?**

No. The setter can enforce range checks, runtime conditions may disallow it, or the client may lack permissions.

**5. Is `@ManagedOperation` needed for a setter?**

No. A setter is annotated with `@ManagedAttribute` to create the attribute's write path; `@ManagedOperation` is used for standalone management actions.

**6. Why should getters be fast?**

Monitoring tools may poll them periodically; slow getters increase load and can degrade application performance.

**7. Does updating a variable in a setter guarantee the resource is using the new value?**

No. Application logic must actually apply the configuration to the runtime resource.

## 20. Summary

In Spring JMX, **`@ManagedAttribute` on a getter enables read access**, and **`@ManagedAttribute` on the matching setter enables write access**. When both methods describe a valid Java property, the Spring exporter can expose **a single read/write JMX attribute**.

The final point of verification is always the actual metadata:

```text
MBeanInfo
  Attribute: MaxWorkers
  Type: int
  Readable: true
  Writable: true
```

However, write permission in metadata differs from access control and business validation accepting a value. A managed setter must validate inputs, handle concurrency, update real resources, and ensure safe execution. When behavior resembles a command rather than adjusting a property, choose `@ManagedOperation`.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework API — `ManagedAttribute`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework API — `AnnotationMBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Java SE API — `MBeanAttributeInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
