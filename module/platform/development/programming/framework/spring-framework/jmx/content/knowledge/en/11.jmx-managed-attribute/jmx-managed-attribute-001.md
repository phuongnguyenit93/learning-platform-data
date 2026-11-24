# Spring Framework JMX: @ManagedAttribute and Exposing Properties

## 1. Lesson Objectives

In Spring Framework JMX, the \`@ManagedAttribute\` annotation marks property accessor methods that an application wants to expose to management tools. When a bean is exported as an MBean by Spring, JConsole or a Java JMX client can read or write the corresponding **JMX attributes** without retrieving the bean from the \`ApplicationContext\`.

This lesson clarifies how Spring maps Java getters/setters to attributes, the difference between read-only and read/write properties, how to choose the exact data to expose, how to declare metadata, and the limitations when used in production environments.

\`\`\`text
Spring-managed Java bean
  getMaxConnections()
  setMaxConnections(int)
  getActiveConnections()
  resetStatistics()
           |
           | @ManagedResource + @ManagedAttribute
           v
Spring MBeanExporter + metadata assembler
           |
           v
MBeanServer: com.example.app:type=ConnectionPool,name=primary
           |
           +-- MaxConnections: int  [read/write]
           +-- ActiveConnections: int [read-only]
           |
           +-- resetStatistics(): operation (only if exported separately)
           |
           v
JConsole / MBeanServerConnection
\`\`\`

**Core point:** \`@ManagedAttribute\` is Spring metadata for managed properties. It does not create new fields, does not automatically persist configuration to disk, does not guarantee thread safety, and does not automatically enable a JMX exporter. These aspects must be designed and configured separately.

## 2. JavaBean Properties and JMX Attributes

A standard JavaBean property is represented through accessor methods:

\`\`\`java
public int getMaxConnections();
public void setMaxConnections(int value);
\`\`\`

According to JavaBeans conventions, \`getMaxConnections()\` is the getter for the \`maxConnections\` property, and \`setMaxConnections(int)\` is the setter for that property.

When exported via Spring JMX, clients typically see an attribute named \`MaxConnections\` (name formatting is determined by the metadata/exporter). Clients do not invoke the \`getMaxConnections\` method directly in the usual Java way; they interact through the attribute name:

\`\`\`java
Object current = server.getAttribute(objectName, "MaxConnections");
server.setAttribute(
    objectName,
    new Attribute("MaxConnections", 20)
);
\`\`\`

In MBean metadata, an attribute has important information:

| Information | Meaning |
|---|---|
| \`name\` | Attribute name used in the JMX API |
| \`type\` | Exposed data type, e.g. \`int\`, \`boolean\`, \`java.lang.String\` |
| \`description\` | Description of behavior or management meaning |
| \`isReadable()\` | Whether the client is permitted to read per the attribute contract |
| \`isWritable()\` | Whether the client can perform writes per the attribute contract |
| \`isIs()\` | Whether a boolean attribute has a getter in the \`isXxx()\` form |

The JavaBeans contract provides a way to identify getters and setters; annotations and the assembler decide which members are actually exposed.

## 3. Declaring @ManagedResource and @ManagedAttribute

Consider an example bean managing the maximum number of connections and the number of currently active connections.

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=ConnectionPool,name=primary",
    description = "Example runtime connection pool controls"
)
public class ConnectionPoolControl {

    private volatile int maxConnections = 16;
    private final AtomicInteger activeConnections = new AtomicInteger();

    @ManagedAttribute(
        description = "Maximum configured concurrent connections"
    )
    public int getMaxConnections() {
        return maxConnections;
    }

    @ManagedAttribute(
        description = "Changes the maximum connection limit"
    )
    public void setMaxConnections(int maxConnections) {
        if (maxConnections < 1 || maxConnections > 200) {
            throw new IllegalArgumentException(
                "maxConnections must be from 1 to 200"
            );
        }
        this.maxConnections = maxConnections;
    }

    @ManagedAttribute(
        description = "Currently active connections"
    )
    public int getActiveConnections() {
        return activeConnections.get();
    }

    // For internal logic only, not a JMX attribute.
    public void recordConnectionOpened() {
        activeConnections.incrementAndGet();
    }

    public void recordConnectionClosed() {
        activeConnections.decrementAndGet();
    }
}
\`\`\`

With Spring's annotation-reading metadata assembler, the expected management members are:

\`\`\`text
MBean:
  com.example.app:type=ConnectionPool,name=primary

Attributes:
  MaxConnections
    type: int
    readable: true
    writable: true

  ActiveConnections
    type: int
    readable: true
    writable: false
\`\`\`

Here \`MaxConnections\` has both its getter and setter exposed. \`ActiveConnections\` only has its getter exposed and is therefore read-only.

The \`recordConnectionOpened()\` and \`recordConnectionClosed()\` methods are public Java methods but do not have JMX annotations. When using the annotation metadata assembler properly, they do not automatically become JMX operations.

**Practical application note:** changing \`maxConnections\` in the example field only updates a runtime configuration value. If the bean controls a real connection pool, the setter must integrate logic to resize or update the pool's limit. Avoid letting JMX report an update while the underlying resource does not change.

## 4. Where Should the Annotation Be Placed?

\`@ManagedAttribute\` is used with JavaBean accessor methods, typically getters and setters. Do not place it on a field and expect Spring to fully infer read/write behavior if the application's export mechanism is built to read metadata from methods.

Correct example:

\`\`\`java
@ManagedAttribute
public int getTimeoutSeconds() {
    return timeoutSeconds;
}

@ManagedAttribute
public void setTimeoutSeconds(int value) {
    timeoutSeconds = value;
}
\`\`\`

For a read-only property:

\`\`\`java
@ManagedAttribute
public long getCompletedJobs() {
    return completedJobs.get();
}
\`\`\`

For a boolean property, you can use the \`isXxx\` convention:

\`\`\`java
@ManagedAttribute
public boolean isPaused() {
    return paused;
}
\`\`\`

A plain field such as:

\`\`\`java
private volatile boolean paused;
\`\`\`

is not a property accessible via JMX if you have not exposed the corresponding accessor in the management contract.

## 5. Read-Only, Write-Only, and Read/Write

Attribute accessibility is determined by the exported accessors and the metadata provided by the MBeanServer.

### 5.1. Read-Only

\`\`\`java
@ManagedAttribute(description = "Number of processed jobs")
public long getProcessedJobs() {
    return processedJobs.get();
}
\`\`\`

Clients can read it:

\`\`\`java
long count = (Long) server.getAttribute(
    objectName,
    "ProcessedJobs"
);
\`\`\`

Without an exposed setter, clients cannot write to this attribute. Attempting to write may result in an \`AttributeNotFoundException\` or a corresponding exception from the adapter.

Examples of metrics that should be read-only: total processed requests, number of open connections, startup time, and runtime-computed status.

### 5.2. Read and Write (Read/Write)

\`\`\`java
@ManagedAttribute
public int getRefreshIntervalSeconds() {
    return refreshIntervalSeconds;
}

@ManagedAttribute
public void setRefreshIntervalSeconds(int value) {
    if (value < 5 || value > 3600) {
        throw new IllegalArgumentException("Expected 5..3600");
    }
    refreshIntervalSeconds = value;
}
\`\`\`

This is a runtime configuration that can be observed and adjusted. The client writes and then reads back:

\`\`\`java
server.setAttribute(
    objectName,
    new Attribute("RefreshIntervalSeconds", 60)
);

int observed = (Integer) server.getAttribute(
    objectName,
    "RefreshIntervalSeconds"
);
\`\`\`

Readback confirms the value the bean is exposing. It does not necessarily prove that all underlying workers or schedulers have applied the new value; that depends on the setter implementation.

### 5.3. Write-Only

A property with only an exposed setter can theoretically be write-only in JMX metadata. However, write-only JMX attributes are often difficult to verify post-state and may be handled differently by management tools.

If the operation is a one-off behavioral action, such as \`clearCache()\`, consider \`@ManagedOperation\` instead of writing a setter like \`setClearCache(true)\`. If it is a sensitive configuration that must not be returned to clients, design it separately and clearly define the reason for write-only access.

**Best practice:** only open write access when there is a legitimate operational need and the setter validates inputs.

## 6. Does @ManagedAttribute Imply a Public Setter?

No. The existence of a setter in a class does not automatically make a property writable via JMX if the annotation assembler only exposes the annotated getter.

For example:

\`\`\`java
@ManagedAttribute
public int getLimit() {
    return limit;
}

public void setLimit(int limit) {
    this.limit = limit;
}
\`\`\`

In annotation-metadata-based export, you should not assume an unannotated setter will be exposed. Inspect the actual \`MBeanInfo\` to know whether \`Limit\` is writable.

Similarly:

\`\`\`java
public int getLimit() {
    return limit;
}

@ManagedAttribute
public void setLimit(int limit) {
    this.limit = limit;
}
\`\`\`

If the getter has not been included in metadata, clients should not assume the property is readable. The JMX contract is ultimately confirmed by \`MBeanAttributeInfo\`.

This is useful when a bean contains many setters for application code, but only a subset is allowed to be invoked from management tools.

## 7. Configuring Spring for Annotations to Take Effect

Having annotations in code is not enough. The bean must be exported to the \`MBeanServer\` using the Spring JMX infrastructure.

### 7.1. Concise Approach: @EnableMBeanExport

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    public ConnectionPoolControl connectionPoolControl() {
        return new ConnectionPoolControl();
    }
}
\`\`\`

Annotation-driven configuration creates the appropriate export infrastructure so Spring discovers \`@ManagedResource\` beans and exposes annotated members.

When the application starts, the exporter registers the bean under the declared ObjectName if there are no collisions or configuration errors.

### 7.2. Explicit Configuration: MBeanExporter + MetadataMBeanInfoAssembler

An application can explicitly choose the beans and ObjectNames:

\`\`\`java
package com.example.jmx;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    public AnnotationJmxAttributeSource annotationSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler metadataAssembler(
            AnnotationJmxAttributeSource annotationSource) {

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(annotationSource);
        return assembler;
    }

    @Bean
    public MBeanExporter exporter(
            ConnectionPoolControl control,
            MetadataMBeanInfoAssembler metadataAssembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(metadataAssembler);
        exporter.setBeans(Map.of(
            "com.example.app:type=ConnectionPool,name=primary",
            control
        ));
        return exporter;
    }
}
\`\`\`

With this approach, the assembler extracts metadata from \`@ManagedAttribute\`. The exporter manages the bean → ObjectName mapping.

**Do not configure two exporters simultaneously registering the same bean** without a clear ownership plan. For instance, enabling \`@EnableMBeanExport\` and also creating an explicit exporter with the same ObjectName can lead to double-registration.

### 7.3. How to Verify the Infrastructure

When an MBean does not appear, check sequentially:

1. Was the bean actually created in the \`ApplicationContext\`?
2. Does the class have \`@ManagedResource\`?
3. Do the desired getters/setters have \`@ManagedAttribute\`?
4. Does the context have an appropriate exporter?
5. Is the ObjectName valid and unique in the MBeanServer?
6. Is the client connected to the exact MBeanServer used by the exporter?
7. Are there any exceptions in the startup logs related to registration or metadata?

For Spring Boot, JMX configuration can be controlled by Boot's properties and auto-configuration. Check \`spring.jmx.enabled\` along with existing exporters rather than assuming auto-export behaves identically in every runtime.

## 8. Reading Metadata to Verify Attributes

The standard JMX API allows verifying attributes after export.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName objectName = new ObjectName(
    "com.example.app:type=ConnectionPool,name=primary"
);

if (!server.isRegistered(objectName)) {
    throw new IllegalStateException(
        "MBean not registered: " + objectName
    );
}

MBeanInfo info = server.getMBeanInfo(objectName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "name=%s, type=%s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
\`\`\`

This is the objective source of truth for the registered JMX contract. If an attribute does not appear or is not writable as intended, inspect the assembler, annotations, method signatures, and exporter configuration.

In systems with multiple MBeanServers, replace \`ManagementFactory.getPlatformMBeanServer()\` with the exact server the exporter registered to. Two servers in the same JVM can have different registries.

## 9. Interacting with Attributes via MBeanServer

Assume \`ConnectionPoolControl\` has been exported as in the example.

### 9.1. Reading

\`\`\`java
Object max = server.getAttribute(
    objectName,
    "MaxConnections"
);
System.out.println("Configured max = " + max);
\`\`\`

\`getAttribute\` returns an \`Object\`; the runtime type is typically the boxed type corresponding to the declared type.

\`\`\`java
int configured = (Integer) server.getAttribute(
    objectName, "MaxConnections"
);

int active = (Integer) server.getAttribute(
    objectName, "ActiveConnections"
);
\`\`\`

For a \`long\` attribute, the result is typically a \`Long\`. Casting \`Long\` to \`Integer\` will cause a \`ClassCastException\` on the client, even though JMX read succeeded.

### 9.2. Writing

\`\`\`java
import javax.management.Attribute;

server.setAttribute(
    objectName,
    new Attribute("MaxConnections", 32)
);

int after = (Integer) server.getAttribute(
    objectName, "MaxConnections"
);

System.out.println("After = " + after);
\`\`\`

For an \`int\` property, the value sent via JMX is the corresponding Java \`Integer\`. The string \`"32"\` is not necessarily converted automatically to \`int\`.

### 9.3. Cannot Write to a Read-Only Attribute

\`\`\`java
server.setAttribute(
    objectName,
    new Attribute("ActiveConnections", 99)
);
\`\`\`

Because \`ActiveConnections\` only exposes a getter, the write operation is invalid according to the metadata. This is an attribute access permission error, not a mechanism to directly modify a counter measuring runtime state.

## 10. Descriptions and Metadata for Operators

The annotation supports descriptions so JMX tool users know what an attribute actually means:

\`\`\`java
@ManagedAttribute(
    description = "Idle timeout in seconds"
)
public int getIdleTimeoutSeconds() {
    return idleTimeoutSeconds;
}
\`\`\`

An effective description should answer:

- What does the attribute measure or configure?
- What is the unit: seconds, milliseconds, bytes, count, percentage?
- Can it be modified directly? If so, what are the valid values and side effects?
- Is the value merely a desired configuration or actual runtime state?
- Is the value preserved after a restart?

Example of two attributes with the same \`int\` type but different meanings:

\`\`\`text
MaxConnections:
  Configures the maximum connection limit for the pool

ActiveConnections:
  Number of connections currently in use at the time of reading
\`\`\`

Without clarification, operators might confuse measured metrics with configuration parameters.

## 11. When to Use an Attribute vs. an Operation?

\`@ManagedAttribute\` is suitable for state or configuration values that can be represented as a property. \`@ManagedOperation\` is suitable for deliberate actions.

| Need | Suggested Representation | Reason |
|---|---|---|
| Read number of processed requests | \`@ManagedAttribute\` getter | State value, read-only |
| Adjust worker limit | \`@ManagedAttribute\` getter/setter | A runtime configuration value |
| Read whether worker is paused | Boolean \`@ManagedAttribute\` | Current state |
| Reset counters | \`@ManagedOperation\` | Action with side effects |
| Clear cache | \`@ManagedOperation\` | Action, not state |
| Reload configuration from file | \`@ManagedOperation\` | Executes a task with success/failure |

Example operation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedOperation(description = "Reset connection statistics")
public void resetStatistics() {
    // ...
}
\`\`\`

Do not design a writable \`ClearCache\` attribute and force clients to write \`true\` to trigger cache clearing when it is inherently an operation. A property needs clear read/write semantics, whereas an operation can represent failure states and explicit business parameters.

## 12. Validation and Safety of Writable Attributes

When exposing a setter, the application opens a runtime modification path. The client might be JConsole, an internal script, or an authorized remote JMX connector.

A setter should ensure:

1. **Valid type:** the JMX value has the correct Java type.
2. **Valid value range:** e.g. \`1 <= MaxConnections <= 200\`.
3. **Business invariants:** the new limit does not violate conditions that the service relies on.
4. **Consistent state application:** if modifying a real resource, update related components properly.
5. **Clear error causes:** throw exceptions indicating validation or infrastructure failure.
6. **Observability:** getters/metrics/logs reflect the outcome of the change.

Example:

\`\`\`java
@ManagedAttribute
public synchronized void setMaxConnections(int value) {
    if (value < 1 || value > 200) {
        throw new IllegalArgumentException(
            "Expected maxConnections between 1 and 200"
        );
    }

    // In a real application: validate and configure the pool.
    maxConnections = value;
}
\`\`\`

\`synchronized\` in the example only illustrates protecting the setter operation. For real resources, consider multi-state updates, races with workers, and when the bean publishes the value. \`volatile\` ensures visibility for a single field, not turning a multi-step operation into a transaction.

## 13. Common Errors When Exposing Properties

| Symptom | Possible Cause | How to Check |
|---|---|---|
| MBean not visible | Exporter not running, duplicate name, or bean not created | Check Spring context/exporter and registration logs |
| MBean exists but attribute missing | Getter/setter missing annotation or not selected by assembler | Read \`MBeanInfo\`, check metadata |
| Attribute read-only despite Java setter | Setter not exposed | Check annotation on setter and \`isWritable()\` |
| \`AttributeNotFoundException\` | Wrong name or lacking corresponding read/write permission | Check exact name and \`MBeanAttributeInfo\` |
| \`InvalidAttributeValueException\` | Passed value has wrong type or rejected by adapter | Compare \`getType()\` and the Object type in \`Attribute\` |
| Setter throws error | Validation, state, or backend logic failure | Inspect target/cause exception and application logs |
| \`ClassCastException\` on client | Client casts return value to wrong type | Compare attribute type and boxed type |
| Readback doesn't match written value | Setter normalizes value or concurrent updates occurred | Check setter contract and concurrency |
| Changes lost after restart | Value only stored in memory | Design separate persistence if required |
| Sensitive attribute visible | Inappropriate getter exposed | Narrow management interface and access permissions |

\`AttributeNotFoundException\` does not always mean a mere typo; in cases of read/write contradicting metadata, clients can also encounter this error. Additionally, exceptions may be wrapped by the Spring/JMX MBean adapter.

## 14. Real-World Design Scenarios

### 14.1. Computed Properties Should Not Be Writable

\`\`\`java
@ManagedAttribute
public double getCpuLoad() {
    return cpuProbe.currentLoad();
}
\`\`\`

The read value reflects a measured state. Do not create a fake \`setCpuLoad\` setter just so a dashboard can edit metrics.

### 14.2. Configuration Properties Needing Readback

\`\`\`java
@ManagedAttribute
public int getRetryLimit() {
    return retryLimit;
}

@ManagedAttribute
public void setRetryLimit(int retryLimit) {
    if (retryLimit < 0 || retryLimit > 10) {
        throw new IllegalArgumentException("retryLimit must be 0..10");
    }
    this.retryLimit = retryLimit;
}
\`\`\`

Operations tools can read before/after states. However, if the program reloads the configuration file at another time or restarts, the value may revert to the default.

### 14.3. Attributes Tied to Sensitive Information

Do not annotate getters such as:

\`\`\`java
public String getDatabasePassword() { /* ... */ return "..."; }
public String getAccessToken() { /* ... */ return "..."; }
\`\`\`

Even if read-only, sensitive data can be leaked via JMX clients, monitoring, and logs. If credentials truly need management, use a dedicated secret management mechanism rather than turning secrets into public attributes.

### 14.4. Attributes with Complex Types

JMX clients generally support simple, easy-to-handle types like \`String\`, \`int\`, \`long\`, and \`boolean\` better. For complex data or remote management, consider JMX-compatible types, MXBean open types, or \`CompositeData\`/tabular data structures.

Do not assume an arbitrary domain object will display cleanly or serialize safely over remote JMX. Design appropriate DTOs/metadata if complex state needs to be exposed.

## 15. Practice Exercises

### Exercise 1: Determine Read/Write

Given the class:

\`\`\`java
@ManagedResource(
    objectName = "com.example:type=JobControl,name=main"
)
public class JobControl {

    @ManagedAttribute
    public int getMaxJobs() { return 8; }

    @ManagedAttribute
    public void setMaxJobs(int value) { /* ... */ }

    @ManagedAttribute
    public long getProcessedJobs() { return 100; }
}
\`\`\`

**Question:** What are the read/write permissions of \`MaxJobs\` and \`ProcessedJobs\`?

**Hint:** \`MaxJobs\` has both an annotated getter and setter, so it is read/write. \`ProcessedJobs\` only has a getter, so it is read-only.

### Exercise 2: Choose the Appropriate Annotation

A class has a \`clearCache()\` method. Should \`@ManagedAttribute\` or \`@ManagedOperation\` be used?

**Hint:** \`clearCache()\` is an action, so use \`@ManagedOperation\`.

### Exercise 3: Detect Missing Annotation on Setter

\`\`\`java
@ManagedAttribute
public int getThreshold() { return threshold; }

public void setThreshold(int threshold) {
    this.threshold = threshold;
}
\`\`\`

**Question:** Can you be certain it is writable?

**Hint:** You should not assume so. With the annotation metadata assembler, annotate the setter and inspect \`MBeanInfo\` after export.

### Exercise 4: Diagnose Type Mismatch

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxConnections", "32")
);
\`\`\`

**Question:** If the property is \`int\`, why might this fail?

**Hint:** The string \`"32"\` is a \`String\`, not an \`Integer\`.

### Exercise 5: Reading State After Writing

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxConnections", 32)
);
int value = (Integer) server.getAttribute(
    name, "MaxConnections"
);
\`\`\`

**Question:** Is \`value == 32\` sufficient proof that the actual connection pool has resized?

**Hint:** Not sufficient; you must also observe the actual resource or corresponding metrics.

### Exercise 6: Attribute Missing Despite Correct Annotations

**Question:** What should be checked before modifying the getter?

**Hint:** Whether the bean is exported to the right MBeanServer and ObjectName, whether the exporter/assembler is configured, and whether there are registration errors.

## 16. Summary

\`@ManagedAttribute\` enables Spring Framework to expose **JavaBean properties** as JMX attributes. An exposed getter provides read capability; an exposed setter provides write capability if the metadata/contract permits. Attributes reflect runtime state or configuration, while deliberate actions should be modeled with \`@ManagedOperation\`.

For declarations to take effect, the bean must be exported through the appropriate Spring JMX infrastructure. After exporting, use \`MBeanInfo\` to verify names, types, and read/write permissions. For writable properties, always control validation, thread safety, access permissions, actual side effects, and how values are persisted across restarts.