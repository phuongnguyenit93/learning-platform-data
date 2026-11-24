# Read-Only, Write-Only, and Read-Write Attributes in MBean Interfaces

## 1. Why Do MBeans Need to Distinguish Read and Write Access?

An MBean (Managed Bean) is an object that provides a management interface for a running Java resource. Through JMX, an operator or a tool like JConsole can view current state and, when permitted, modify part of the runtime configuration.

However, not all information should be modifiable. For example:

- The number of processed requests is **observational information**; reading it makes sense, whereas arbitrarily overwriting the counter usually does not.
- A one-way configuration push might need to **accept a new value** without exposing the currently held value for security reasons or because the data has no suitable getter.
- A warning threshold may need to be **read for inspection** and **written for tuning** during operations.

JMX addresses this distinction through the concept of an **attribute** with two independent capabilities: `isReadable` and `isWritable`. From these two flags, we get three valid attribute combinations in practice: read-only, write-only, and read-write.

```text
                    MBean Management Interface
                              |
                         Attribute
                              |
                  +-----------+-----------+
                  |                       |
              Readable?               Writable?
                  |                       |
           getAttribute(...)        setAttribute(...)
                  |                       |
           Returns state           Modifies state
                  +-----------+-----------+
                              |
                         MBeanServer
                              |
                   Application Object
```

**Key point:** read/write permissions here represent **the attribute's capabilities under the JMX contract**, not per-user authentication and authorization. If an attribute has `isWritable=true`, JMX allows write calls at the interface level; protecting the connection and caller privileges still needs to be configured separately.

## 2. How JMX Recognizes Attributes from a Standard MBean

For a **Standard MBean**, Java uses a management interface following the `ClassNameMBean` convention. For example, class `ServiceMonitor` implements `ServiceMonitorMBean`.

In the interface, JMX uses JavaBean method patterns to identify attributes:

| Declaration in Interface | Interpretation in JMX | Attribute Name |
|---|---|---|
| `T getX()` | Getter, supports reading | `X` |
| `boolean isX()` | Boolean getter, supports reading | `X` |
| `void setX(T value)` | Setter, supports writing | `X` |
| Compatible `getX()` and `setX(T)` | Read-write on the same attribute | `X` |
| Method not following getter/setter patterns | Usually an operation | By method name |

For the `isX()` form, the return type must be primitive `boolean` according to Standard MBean attribute recognition rules. A `getX()` getter takes no parameters and returns a result; a setter takes one parameter of matching type and returns `void`.

Example:

```java
public interface ServiceMonitorMBean {
    long getRequestCount();             // read-only attribute: RequestCount
    void setMaintenanceMessage(String message); // write-only: MaintenanceMessage
    int getWarningThreshold();          // getter: WarningThreshold
    void setWarningThreshold(int value); // setter: WarningThreshold
    boolean isMaintenanceMode();        // read-only: MaintenanceMode
}
```

If a getter/setter pair shares the same name but does not have compatible types, JMX cannot arbitrarily guess that they belong to a valid attribute. Design unambiguous, consistent signatures between the interface and the implementation.

**Important:** a public member on the implementation class that does not appear in the Standard MBean interface will not automatically be exposed as an attribute of that contract.

## 3. Read-Only Attributes

A **read-only** attribute has a getter and no setter exported in the MBean interface.

```java
public interface RequestStatsMBean {
    long getTotalRequests();
    boolean isHealthy();
}
```

When the MBean is registered, the metadata for `TotalRequests` and `Healthy` indicates that they are readable but not writable:

```text
TotalRequests:
  readable = true
  writable = false

Healthy:
  readable = true
  writable = false
```

The client uses:

```java
Object total = connection.getAttribute(objectName, "TotalRequests");
Object healthy = connection.getAttribute(objectName, "Healthy");
```

Here `connection` is an `MBeanServerConnection`, and `objectName` identifies the registered MBean. Because there is no corresponding setter, calling `setAttribute(..., new Attribute("TotalRequests", ...))` will be rejected according to the attribute's writability.

**Use cases:**

- Runtime metrics: thread count, request count, failed task count.
- Health status, connection state, version, or uptime.
- Configuration values that operators only need to inspect and must not arbitrarily edit at runtime.

A read-only getter can still return data that changes over time. `read-only` **does not mean immutable** and **does not guarantee the value will not change between two reads**. It only means a JMX client cannot write directly through that attribute.

If the application has a `resetTotalRequests()` operation, the value of `TotalRequests` can still change due to the operation; the attribute remains read-only because no setter is exposed.

### 3.1. What Characteristics Should a Getter Have?

Getters are called by management tools whenever they need to display or collect data. Therefore, they should:

- Return quickly, avoiding full database scans or slow network calls.
- Not trigger side effects such as clearing caches, writing data, or changing configuration.
- Have a clear return type and unit of measurement, such as milliseconds, bytes, or count.
- Avoid throwing exceptions for common system states; if data is unavailable, represent that through a clear contract.
- Avoid leaking passwords, tokens, or personal data via JMX.

## 4. Write-Only Attributes

A **write-only** attribute only has a setter exposed in the interface:

```java
public interface RuntimeSettingsMBean {
    void setMaintenanceMessage(String message);
}
```

Corresponding metadata:

```text
MaintenanceMessage:
  readable = false
  writable = true
```

The client can write:

```java
connection.setAttribute(
    objectName,
    new javax.management.Attribute(
        "MaintenanceMessage",
        "Scheduled maintenance at 23:00"
    )
);
```

But reading will fail:

```java
connection.getAttribute(objectName, "MaintenanceMessage");
```

The `getAttribute` method throws an appropriate JMX error, typically `AttributeNotFoundException`, when the attribute is not readable. Display behavior in JConsole also depends on the tool: the UI may not show a current value or may not provide a read field for that attribute.

### 4.1. When Should Write-Only Be Used?

Use it when an operator needs to send a value or update request, yet there is no good reason to return that same value back over the management interface. For example, setting an operational notice string or receiving a replacement value to be processed internally.

However, **write-only does not automatically make data secret**. The value can still be exposed via insecure connections, audit logs, the application, or other channels. Do not use a JMX setter to pass secrets without proper security design.

If an action is essentially a command (such as `clearCache()`, `rotateKey()`, `reloadRules()`), an **operation** usually expresses it more clearly than a write-only attribute. A setter should mean "set the value of attribute X," whereas an operation fits "perform action Y."

### 4.2. An Important Distinction

With a setter that has no getter, the client cannot retrieve the before/after value for comparison via the same attribute. If you need to confirm the current state, consider adding a separate read-only attribute such as `getMaintenanceStatus()` or an operation with an appropriate return value. Avoid designing interfaces where operators cannot tell whether an update request was applied.

## 5. Read-Write Attributes

A **read-write** attribute has both a getter and a setter exposed together with the same name and compatible type:

```java
public interface AlertConfigMBean {
    int getWarningThreshold();
    void setWarningThreshold(int threshold);
}
```

Metadata:

```text
WarningThreshold:
  readable = true
  writable = true
```

The client inspects and updates:

```java
int oldValue = (Integer) connection.getAttribute(
    objectName, "WarningThreshold"
);

connection.setAttribute(
    objectName,
    new javax.management.Attribute("WarningThreshold", 75)
);

int newValue = (Integer) connection.getAttribute(
    objectName, "WarningThreshold"
);
```

Reading back helps confirm the actual value returned by the MBean. It does not by itself guarantee that the change is persisted across application restarts, or that no other actor just updated the same attribute.

**Use cases:**

- Warning thresholds, limits, or tuning factors allowed to change at runtime.
- Maintenance/debug modes toggled by operators under controlled conditions.
- Configuration options with clear validation, units, and ranges.

The setter must validate the value itself. For example, `WarningThreshold = -10` may be meaningless in a given domain; JMX does not know business rules if the implementation does not enforce them.

## 6. Complete Java Example: All Three Attribute Types

The example below uses Java SE and the platform MBeanServer, runnable independently of Spring. The goal is to directly observe the three attribute types and their behavior on read/write.

### 6.1. Management Interface

```java
// RuntimeControlMBean.java
public interface RuntimeControlMBean {
    // READ-ONLY: provides getter only.
    long getProcessedRequests();

    // WRITE-ONLY: provides setter only.
    void setMaintenanceMessage(String message);

    // READ-WRITE: getter and setter.
    int getWarningThreshold();
    void setWarningThreshold(int threshold);

    // READ-ONLY boolean following the isX() pattern.
    boolean isMaintenanceMode();

    // Operation independent of attributes.
    void resetRequestCounter();
}
```

### 6.2. Implementation

```java
// RuntimeControl.java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;

public class RuntimeControl implements RuntimeControlMBean {
    private final AtomicLong processedRequests = new AtomicLong();
    private volatile String maintenanceMessage = "";
    private volatile int warningThreshold = 80;
    private volatile boolean maintenanceMode;

    public void recordRequest() {
        processedRequests.incrementAndGet();
    }

    @Override
    public long getProcessedRequests() {
        return processedRequests.get();
    }

    @Override
    public void setMaintenanceMessage(String message) {
        String normalized = Objects.requireNonNull(message, "message").trim();
        if (normalized.length() > 200) {
            throw new IllegalArgumentException(
                "Maintenance message is too long"
            );
        }
        maintenanceMessage = normalized;
        maintenanceMode = !normalized.isEmpty();
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int threshold) {
        if (threshold < 1 || threshold > 100) {
            throw new IllegalArgumentException(
                "WarningThreshold must be between 1 and 100"
            );
        }
        warningThreshold = threshold;
    }

    @Override
    public boolean isMaintenanceMode() {
        return maintenanceMode;
    }

    @Override
    public void resetRequestCounter() {
        processedRequests.set(0);
    }
}
```

Some design points in the implementation:

- `AtomicLong` allows thread-safe incrementing when multiple threads call `recordRequest()` concurrently.
- `volatile` makes updates to individual fields visible across threads; it does not turn multiple updates across different fields into an atomic transaction.
- The `WarningThreshold` setter validates the value before accepting it.
- `maintenanceMessage` has no public JMX getter; internal application code can still use that field's value when implementing appropriate logic.
- `resetRequestCounter()` is exposed as an operation that modifies the counter, even though `ProcessedRequests` is a read-only attribute.

### 6.3. Registration and Verification via MBeanServer

```java
// Main.java
import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.AttributeNotFoundException;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class Main {
    public static void main(String[] args) throws Exception {
        RuntimeControl control = new RuntimeControl();
        control.recordRequest();
        control.recordRequest();

        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "demo.runtime:type=RuntimeControl,name=main"
        );
        server.registerMBean(control, name);

        // Read official metadata from JMX.
        MBeanInfo info = server.getMBeanInfo(name);
        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                "%s: readable=%s, writable=%s, is=%s%n",
                attribute.getName(),
                attribute.isReadable(),
                attribute.isWritable(),
                attribute.isIs()
            );
        }

        // READ-ONLY: readable, writing will be rejected.
        System.out.println(
            "ProcessedRequests = " +
                server.getAttribute(name, "ProcessedRequests")
        );

        // WRITE-ONLY: writable, reading will be rejected.
        server.setAttribute(
            name,
            new Attribute("MaintenanceMessage", "Under maintenance")
        );
        try {
            server.getAttribute(name, "MaintenanceMessage");
        } catch (AttributeNotFoundException expected) {
            System.out.println("MaintenanceMessage is not readable");
        }

        // READ-WRITE: read, write, read again.
        System.out.println(
            "Old threshold = " +
                server.getAttribute(name, "WarningThreshold")
        );
        server.setAttribute(
            name,
            new Attribute("WarningThreshold", 65)
        );
        System.out.println(
            "New threshold = " +
                server.getAttribute(name, "WarningThreshold")
        );

        // Method resetRequestCounter is an operation.
        server.invoke(
            name,
            "resetRequestCounter",
            new Object[0],
            new String[0]
        );
        System.out.println(
            "After reset = " +
                server.getAttribute(name, "ProcessedRequests")
        );

        Thread.sleep(120_000L); // Enough time to observe with JConsole.
    }
}
```

Save the three `public` types in files with matching names and run with the JDK. The example is a Standard MBean because the `RuntimeControl` class implements `RuntimeControlMBean` by convention.

Expected meaningful metadata output:

| Attribute | Readable | Writable | How It Is Produced |
|---|---|---|---|
| `ProcessedRequests` | true | false | Has only `getProcessedRequests()` |
| `MaintenanceMessage` | false | true | Has only `setMaintenanceMessage(String)` |
| `WarningThreshold` | true | true | Has both getter and setter |
| `MaintenanceMode` | true | false | Has only `isMaintenanceMode()` |

The `is` field in `MBeanAttributeInfo` indicates that the attribute uses the `isX()` getter pattern for booleans; it is not a flag indicating whether the attribute "exists."

## 7. Reading and Writing Attributes via the JMX API

Management tools can work via `MBeanServerConnection`. Basic methods:

```java
Object value = connection.getAttribute(name, "WarningThreshold");

connection.setAttribute(
    name,
    new Attribute("WarningThreshold", 90)
);
```

To read/write multiple attributes, JMX provides:

```java
AttributeList readValues = connection.getAttributes(
    name,
    new String[]{"ProcessedRequests", "WarningThreshold"}
);

AttributeList valuesToWrite = new AttributeList();
valuesToWrite.add(new Attribute("WarningThreshold", 70));

AttributeList written = connection.setAttributes(
    name,
    valuesToWrite
);
```

`getAttributes` and `setAttributes` return results for the attributes that were processed successfully; the result may not include all requested attributes. Inspect the returned list instead of assuming the entire batch succeeded.

**Attribute batches are not automatically transactional.** For instance, setting two configuration values with `setAttributes` does not guarantee that both change simultaneously or automatically roll back if one value fails. For multi-field changes requiring joint invariants, design an atomic operation or a composite configuration validated as a whole before applying.

Common errors include:

- `AttributeNotFoundException`: the attribute does not exist or does not support the requested access direction.
- `InvalidAttributeValueException`: the written type/value is incompatible according to JMX or how the implementation handles it.
- `MBeanException` / `RuntimeMBeanException`: the getter/setter on the MBean side threw an exception wrapped accordingly by JMX.
- `InstanceNotFoundException`: the ObjectName does not point to a registered MBean.
- `ReflectionException`: error related to invoking a method via the MBean's introspection/reflection mechanism.

Do not use these exceptions as a way to guess whether an attribute is writable. Before acting, read the metadata to check the exposed capabilities.

## 8. Reading Metadata: The Client's Source of Truth

JMX allows a client to discover in advance what an MBean supports:

```java
MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    String access;
    if (attr.isReadable() && attr.isWritable()) {
        access = "read-write";
    } else if (attr.isReadable()) {
        access = "read-only";
    } else if (attr.isWritable()) {
        access = "write-only";
    } else {
        access = "neither"; // Not a useful attribute to operate on.
    }

    System.out.println(
        attr.getName() + " (" + attr.getType() + "): " + access
    );
}
```

Metadata helps tools build appropriate UIs:

```text
Readable + !Writable  -> display value, disallow editing
!Readable + Writable  -> allow value input, do not display current value
Readable + Writable   -> display value + input control for new value
```

Metadata also contains the type, description, and the `isX()` getter flag. For Dynamic MBeans, metadata is provided directly by the implementation; for Standard MBeans, JMX typically builds metadata from the management interface.

Remember that **metadata can confirm the API shape, not automatically confirm the safety logic of the setter**. Even if `WarningThreshold` has `isWritable=true`, writing `999` may be rejected by validation; an exposed setter may also not apply changes due to runtime state.

## 9. Distinguishing "Writable" and "Allowed to Write"

Two questions need to be answered independently:

1. **Does the MBean expose write capability?** `MBeanAttributeInfo.isWritable()`.
2. **Does this caller have permission to invoke the write?** Depends on the connector, authentication/authorization configuration, network access, and additional safeguards.

For example, an attribute may be designed as read-write while a monitoring account is only allowed to read. The metadata may still describe the attribute as writable because that is the MBean's contract; actual security restricts the monitoring user. Conversely, even an authenticated administrator cannot use `setAttribute` to write an attribute that is read-only by contract.

Do not "protect" a value by omitting the getter while still allowing arbitrary writes over an open connector. Write-only merely removes the read direction on the interface; it does not control who can write.

State-changing operations should have appropriate audit logging, least privilege, and rollback mechanisms when needed. Be especially careful with remote JMX/RMI and network settings, TLS, and authentication; avoid exposing management connections to the Internet.

## 10. Spring Framework: Exporting Attributes with Read/Write Access

Spring supports JMX export via `MBeanExporter` and the annotations in `org.springframework.jmx.export.annotation`. When using annotation-based export with proper configuration, `@ManagedAttribute` marks accessors exposed to the management interface.

Simple example:

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "demo.spring:type=RuntimeSettings")
public class RuntimeSettings {
    private final AtomicLong processedRequests = new AtomicLong();
    private volatile int warningThreshold = 80;
    private volatile String maintenanceMessage = "";

    public void recordRequest() {
        processedRequests.incrementAndGet();
    }

    @ManagedAttribute(description = "Number of processed requests")
    public long getProcessedRequests() {
        return processedRequests.get();
    }

    @ManagedAttribute(description = "Runtime warning threshold")
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @ManagedAttribute(description = "Runtime warning threshold")
    public void setWarningThreshold(int warningThreshold) {
        if (warningThreshold < 1 || warningThreshold > 100) {
            throw new IllegalArgumentException("Range: 1..100");
        }
        this.warningThreshold = warningThreshold;
    }

    @ManagedAttribute(description = "Maintenance notice")
    public void setMaintenanceMessage(String maintenanceMessage) {
        this.maintenanceMessage = maintenanceMessage;
    }

    @ManagedOperation(description = "Reset request counter")
    public void resetRequestCounter() {
        processedRequests.set(0);
    }
}
```

This code declares:

- `ProcessedRequests`: read-only because only the getter is annotated.
- `WarningThreshold`: read-write because both the getter and setter are annotated.
- `MaintenanceMessage`: write-only because only the setter is annotated.
- `resetRequestCounter`: an operation because `@ManagedOperation` is used.

**Condition:** the annotations must be processed by an appropriate JMX exporter configuration. In plain Spring Framework, you can enable the export mechanism via `@EnableMBeanExport` in Java configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {
}
```

The application needs a Spring Context and appropriate dependencies. Depending on the Spring Boot version, JMX auto-configuration and the `spring.jmx.enabled` property can govern exporting. Check the actual MBean metadata to confirm read/write levels instead of inferring from method names or `@Component` status.

### 10.1. Difference Between Spring Annotations and Standard MBeans

A Standard MBean derives its contract from an **interface** like `SomethingMBean`. Spring annotation-based export can select accessors from the **bean** and annotation metadata, depending on the configured assembler/exporter. Do not conflate the two mechanisms:

```text
Standard MBean:
  Management interface -> JMX introspection -> MBeanInfo

Spring annotation export:
  Bean + @ManagedResource/@ManagedAttribute
       -> exporter/assembler -> MBeanInfo
```

In both cases, clients use `MBeanServerConnection` and `MBeanAttributeInfo` to inspect the final interface.

## 11. Read/Write Does Not Mean Immutable, Atomic, or Persistent

There are three common misconceptions when designing attributes:

**Read-only ≠ immutable.** The `ProcessedRequests` counter continues to change via business threads. JMX callers cannot set the counter through the attribute, yet the state is not immutable.

**Read-write ≠ atomic across multiple attributes.** One getter may return a value before another thread updates it. Two set calls can interleave. If multiple attributes must change together consistently, design synchronization logic and an appropriate management operation.

**Writable ≠ persistent.** Changing `WarningThreshold` in RAM can be lost when the application restarts. If a configuration change must be retained, there must be a mechanism to save it to a configuration source and handle consistency between runtime and persistent configuration, while documenting this clearly for operators.

Another point: a setter can accept a value yet normalize it before storing (for example, trimming a string, clamping a threshold) or reject invalid data. Clients should re-read read-write attributes to observe the current value; for write-only attributes, a separate confirmation channel is needed.

## 12. Choosing Attribute vs. Operation

These two mechanisms are often confused:

| Intent | Recommended Choice | Reason |
|---|---|---|
| View number of open connections | Read-only attribute | Status value |
| View/adjust warning threshold | Read-write attribute | A configuration parameter with a current value |
| Set a notice that only needs to be received | Write-only attribute if meaningful | Does not expose a getter |
| Clear cache | Operation | An action affecting the system |
| Reload config file | Operation | Task with its own result/errors |
| Start a job or stop a consumer | Operation | Conditional action with significant side effects |
| Reset counter | Operation | State change via an intentional command |

An operation can take multiple parameters and return a result, whereas an attribute setter typically takes a single value corresponding to one attribute. Prefer a contract that is easy to understand and control: an administrator looking at the metadata should be able to predict the impact of reading or writing.

## 13. Common Pitfalls

### 13.1. Getter/Setter Name Mismatch

```java
int getWarningThreshold();
void setThreshold(int value);
```

JMX sees two different property names (`WarningThreshold` and `Threshold`). It does not automatically pair them into a read-write attribute. Rename the setter to `setWarningThreshold` if you want the same attribute.

### 13.2. Getter/Setter Type Mismatch

```java
int getWarningThreshold();
void setWarningThreshold(String threshold);
```

There is no unified type-safe contract for a read-write attribute. Keep the same Java type for both directions or split into an operation with explicit conversion semantics.

### 13.3. Assuming a Setter in the Implementation Alone Is Enough

```java
public interface RuntimeControlMBean {
    int getWarningThreshold();
}

public class RuntimeControl implements RuntimeControlMBean {
    public int getWarningThreshold() { return 80; }
    public void setWarningThreshold(int value) { /* ... */ }
}
```

In a Standard MBean, the JMX contract is based on the interface, so `WarningThreshold` remains read-only. To expose write access, add the setter to the interface and implement the matching signature.

### 13.4. Reading a Write-Only Attribute to Confirm

```java
connection.setAttribute(name, new Attribute("MaintenanceMessage", "Test"));
connection.getAttribute(name, "MaintenanceMessage"); // not supported
```

A write-only design intentionally disallows reading. If confirmation is needed, use an operation returning status or a separate read-only attribute (without necessarily exposing sensitive values).

### 13.5. Using a Writable Attribute for Dangerous Operations

```java
void setDeleteAllData(boolean enabled);
```

This API is both hard to predict in impact and easy for automation tools to trigger accidentally. A destructive or conditional action needs an operation contract and additional safeguards, rather than being disguised as setting a boolean.

### 13.6. Assuming All JMX UIs Display Write-Only the Same Way

Different JMX tools may choose to render write-only attributes differently. The authoritative source is `MBeanInfo` and the API, not just a single tool screenshot.

## 14. Practice Exercises

**Exercise 1 — Classify an interface.** Given:

```java
public interface CacheControlMBean {
    int getCurrentSize();
    int getMaxSize();
    void setMaxSize(int maxSize);
    void setLoadingProfile(String profile);
    boolean isEnabled();
    void clear();
}
```

Identify: `CurrentSize` read-only; `MaxSize` read-write; `LoadingProfile` write-only; `Enabled` read-only; `clear()` is an operation. Then explain what happens when a client tries to write `CurrentSize`.

**Exercise 2 — Observe metadata.** Register a Standard MBean, call `getMBeanInfo()`, and print `getName()`, `getType()`, `isReadable()`, `isWritable()`, `isIs()` for each attribute. Compare with the methods in the interface and check again after modifying the interface/restarting the application.

**Exercise 3 — Validation.** Write a setter for `MaxConnections` with a valid range of 1..500. Try writing `0`, `200`, `501` via JMX. Describe which value is accepted, which values are rejected, and how the client handles the exception.

**Exercise 4 — Distinguish runtime configuration from persistent configuration.** Create `getWarningThreshold()`/`setWarningThreshold()`, change it to 65, restart the JVM, and observe the value. Then propose a way to persist configuration if operations require retaining the value across restarts.

**Exercise 5 — Move to Spring.** Create a Spring bean with `@ManagedResource`; mark one getter as read-only, one setter as write-only, and one getter/setter pair as read-write. Enable JMX export in an appropriate configuration and inspect the metadata via JConsole.

## 15. Self-Check Questions

1. What do `isReadable()` and `isWritable()` in `MBeanAttributeInfo` describe?
2. Why do `getX()` and `setX()` need matching names/types to form a read-write attribute?
3. What is the difference between a read-only attribute and a truly immutable object?
4. Which API must a client use to write an attribute, and which API to invoke an operation?
5. Why does an attribute's write capability not replace remote JMX authentication/authorization?
6. When is a write-only attribute reasonable, and when should an operation be used?
7. Does `setAttributes()` guarantee a transaction across multiple attributes?
8. Why should you inspect the actual MBean's metadata when using Spring export?

## 16. Conclusion

In JMX, **read-only** is an attribute with read access only, **write-only** has write access only, and **read-write** allows both. Standard MBeans express these capabilities through getter/setter signatures in the management interface; Spring Framework can expose corresponding accessors via its annotation export mechanism.

Always inspect `MBeanAttributeInfo.isReadable()` and `isWritable()` on the registered MBean to know the actual contract. Designing lightweight getters, validated setters, distinguishing attributes from operations, and protecting JMX access will keep your management interface clear, predictable, and safe in operation.
