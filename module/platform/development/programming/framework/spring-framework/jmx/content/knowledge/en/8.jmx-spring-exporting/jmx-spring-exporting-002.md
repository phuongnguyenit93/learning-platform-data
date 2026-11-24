# Spring Framework JMX: Exporting Beans That Are Already MBeans and Regular Beans via Assemblers

## 1. The Problem

The Spring Framework can bring Spring beans into the JMX management system through `MBeanExporter`. However, not every bean has the same shape:

1. **Bean that is already a JMX MBean**: an object that already satisfies a JMX contract, such as a Standard MBean (`WorkerControlMBean`) or `DynamicMBean`.
2. **Regular Java/Spring bean**: a POJO that does not implement an MBean interface. To manage it via JMX, Spring needs to determine which methods/attributes to expose and can use **`MBeanInfoAssembler`** along with a ModelMBean adapter to build the JMX surface.

The same exporter can handle both, but the semantics of exporting differ. For a bean that is already an MBean, the JMX contract is primarily defined by the bean itself. For a regular bean, the assembler decides which attributes/operations are exposed to clients.

\`\`\`text
Spring ApplicationContext
        |
        +-- Standard MBean / DynamicMBean
        |       |
        |       +-- MBeanExporter -> MBeanServer
        |                              |
        +-- POJO Spring bean            |
                |                       |
                +-- MBeanInfoAssembler  |
                        |               |
                        +-- ModelMBean -+
                                        |
                              JConsole / JMX client
\`\`\`

What they share is that the final result is **registered under an `ObjectName` in an `MBeanServer`**. The difference is **where the management surface is derived from**.

## 2. Terminology to Know

| Component | Role |
|---|---|
| `MBeanServer` | Registry and access point for reading/writing attributes, invoking operations, and receiving notifications |
| `ObjectName` | MBean identifier within the server, e.g., `com.example:type=Worker,name=primary` |
| `MBeanExporter` | Spring component that takes beans and registers them under an ObjectName |
| `Standard MBean` | Object following the Java JMX convention, e.g., class `Worker` implementing `WorkerMBean` |
| `DynamicMBean` | MBean that provides its own metadata and read/write/invoke mechanism via a dynamic API |
| `ModelMBean` | MBean with metadata describing exposed attributes/operations; Spring can use it to wrap a POJO |
| `MBeanInfoAssembler` | Spring component that builds `ModelMBeanInfo` from a bean and configuration |
| `MetadataMBeanInfoAssembler` | Assembler using Spring JMX annotation metadata |
| `MethodNameBasedMBeanInfoAssembler` | Assembler that selects methods based on a list of names |
| `InterfaceBasedMBeanInfoAssembler` | Assembler that exposes only members declared in specified interfaces |

**Exporting does not mean the entire public API is opened up to JMX.** For a bean that is already an MBean, the MBean interface/metadata decides. For a POJO, the assembler and exporter configuration decide.

## 3. Approach 1: Exporting a Bean That Is Already a Standard MBean

Java JMX has the Standard MBean convention: class `WorkerControl` implements interface `WorkerControlMBean`, where getters/setters and methods define the management contract.

### 3.1. Defining the Management Interface

\`\`\`java
package com.example.jmx;

public interface WorkerControlMBean {
    int getMaxThreads();
    void setMaxThreads(int maxThreads);
    boolean isRunning();
    long getProcessedCount();
    void resetCounters();
}
\`\`\`

### 3.2. Implementing the Standard MBean

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class WorkerControl implements WorkerControlMBean {
    private volatile int maxThreads = 8;
    private volatile boolean running = true;
    private final AtomicLong processedCount = new AtomicLong();

    @Override
    public int getMaxThreads() {
        return maxThreads;
    }

    @Override
    public void setMaxThreads(int maxThreads) {
        if (maxThreads < 1 || maxThreads > 64) {
            throw new IllegalArgumentException("maxThreads must be 1..64");
        }
        this.maxThreads = maxThreads;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public long getProcessedCount() {
        return processedCount.get();
    }

    @Override
    public void resetCounters() {
        processedCount.set(0L);
    }

    // Not part of the MBean interface, so it does not automatically become a JMX operation.
    public void internalMaintenance() {
        // ...
    }
}
\`\`\`

Following this convention, JMX sees:

- Attribute `MaxThreads`: readable and writable, type `int`.
- Attribute `Running`: read-only, type `boolean`.
- Attribute `ProcessedCount`: read-only, type `long`.
- Operation `resetCounters()`.
- `internalMaintenance()` is not in `WorkerControlMBean`, so it does not become an operation merely because it is a public method.

For sensitive data, do not place management methods in the MBean interface if clients are not permitted to use them.

### 3.3. Exporting via Spring MBeanExporter

\`\`\`java
package com.example.jmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ExistingMBeanConfig {

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public MBeanExporter existingMBeanExporter(
            WorkerControl workerControl) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerControl,name=primary",
            workerControl
        ));
        return exporter;
    }
}
\`\`\`

`setBeans` creates a mapping from JMX names to registered beans. For a bean conforming to Standard MBean rules, the exporter can register it under the provided ObjectName. An assembler is not needed to **invent** a JMX interface for a bean that already has an MBean contract.

This code assumes the application does not also configure another exporter that automatically exports the same bean; in Spring Boot or a context using `@EnableMBeanExport`, clearly define who owns the registration to avoid ObjectName collisions.

### 3.4. Verifying via Standard API

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName target = new ObjectName(
    "com.example.app:type=WorkerControl,name=primary"
);

if (!server.isRegistered(target)) {
    throw new IllegalStateException("MBean is not registered yet");
}

MBeanInfo info = server.getMBeanInfo(target);
for (var attribute : info.getAttributes()) {
    System.out.printf(
        "%s (%s), read=%s, write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
\`\`\`

In a real application, the exporter may use a configured MBeanServer rather than the default platform server. For accurate readback, retrieve the same `MBeanServer` that the exporter is using; the example above illustrates the case where both sides use the platform MBeanServer.

## 4. Approach 2: Exporting a Bean That Is Already a DynamicMBean

A `DynamicMBean` does not rely on the `XxxMBean` interface naming convention. It provides its own:

- `getMBeanInfo()`: dynamic metadata.
- `getAttribute` and `setAttribute`: read/write paths.
- `getAttributes` and `setAttributes`: batch operations.
- `invoke`: operation invocation.

Minimal example for an MBean with an `Enabled` attribute:

\`\`\`java
package com.example.jmx;

import javax.management.*;

public class FeatureFlagDynamicMBean implements DynamicMBean {
    private boolean enabled = true;

    @Override
    public Object getAttribute(String name)
            throws AttributeNotFoundException {
        if ("Enabled".equals(name)) {
            return enabled;
        }
        throw new AttributeNotFoundException(name);
    }

    @Override
    public void setAttribute(Attribute attribute)
            throws AttributeNotFoundException,
                   InvalidAttributeValueException {
        if (attribute == null ||
            !"Enabled".equals(attribute.getName())) {
            throw new AttributeNotFoundException(
                attribute == null ? "null" : attribute.getName()
            );
        }
        if (!(attribute.getValue() instanceof Boolean value)) {
            throw new InvalidAttributeValueException(
                "Enabled must be Boolean"
            );
        }
        enabled = value;
    }

    @Override
    public AttributeList getAttributes(String[] names) {
        AttributeList result = new AttributeList();
        for (String name : names) {
            try {
                result.add(new Attribute(name, getAttribute(name)));
            } catch (Exception ignored) {
                // Minimal example; in practice, proper logging is needed.
            }
        }
        return result;
    }

    @Override
    public AttributeList setAttributes(AttributeList updates) {
        AttributeList result = new AttributeList();
        for (Object raw : updates) {
            Attribute attribute = (Attribute) raw;
            try {
                setAttribute(attribute);
                result.add(new Attribute(
                    attribute.getName(),
                    getAttribute(attribute.getName())
                ));
            } catch (Exception ignored) {
                // Minimal example; in practice, proper logging is needed.
            }
        }
        return result;
    }

    @Override
    public Object invoke(
            String action,
            Object[] params,
            String[] signature)
            throws ReflectionException {
        throw new ReflectionException(
            new NoSuchMethodException(action)
        );
    }

    @Override
    public MBeanInfo getMBeanInfo() {
        MBeanAttributeInfo enabledInfo =
            new MBeanAttributeInfo(
                "Enabled",
                "boolean",
                "Feature flag runtime state",
                true,
                true,
                true
            );
        return new MBeanInfo(
            getClass().getName(),
            "Example DynamicMBean",
            new MBeanAttributeInfo[] { enabledInfo },
            null,
            new MBeanOperationInfo[0],
            new MBeanNotificationInfo[0]
        );
    }
}
\`\`\`

This bean has its own management contract, so `MBeanExporter` can accept the `ObjectName -> FeatureFlagDynamicMBean` mapping without needing to determine the bean's metadata through a POJO assembler.

**Note:** Exceptions from `DynamicMBean` must strictly follow the `javax.management.DynamicMBean` contract; this example only illustrates a single attribute. For large systems, implementing `DynamicMBean` manually can require more effort than using a Standard MBean or a Spring assembler.

## 5. Approach 3: Exporting a Spring POJO via an Assembler

Now consider a regular Java bean that implements neither `SomethingMBean` nor `DynamicMBean`.

\`\`\`java
package com.example.jmx;

public class JobCoordinator {
    private volatile int maxParallelJobs = 4;
    private volatile boolean paused = false;

    public int getMaxParallelJobs() {
        return maxParallelJobs;
    }

    public void setMaxParallelJobs(int value) {
        if (value < 1 || value > 32) {
            throw new IllegalArgumentException("value must be 1..32");
        }
        maxParallelJobs = value;
    }

    public boolean isPaused() {
        return paused;
    }

    public void pause() {
        paused = true;
    }

    public void resume() {
        paused = false;
    }

    public String internalDebugSnapshot() {
        return "not for JMX";
    }
}
\`\`\`

There is no `JobCoordinatorMBean` interface. If the exporter needs to expose this bean, Spring uses a ModelMBean adapter and `MBeanInfoAssembler` to select the management members.

**An assembler is a metadata selector, not a magic switch that turns every method into an MBean operation automatically.** The information generated by an assembler can specify getters, setters, operations, descriptions, and other characteristics depending on the implementation.

### 5.1. Exporting a POJO via MethodNameBasedMBeanInfoAssembler

Suppose you want to expose only:

- `getMaxParallelJobs` and `setMaxParallelJobs` as a read/write attribute.
- `isPaused` as a read-only attribute.
- `pause`, `resume` as operations.
- **Do not expose** `internalDebugSnapshot`.

\`\`\`java
package com.example.jmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Configuration
public class OrdinaryBeanExportConfig {

    @Bean
    public JobCoordinator jobCoordinator() {
        return new JobCoordinator();
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler jobAssembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
            new MethodNameBasedMBeanInfoAssembler();

        assembler.setManagedMethods(
            "getMaxParallelJobs",
            "setMaxParallelJobs",
            "isPaused",
            "pause",
            "resume"
        );
        return assembler;
    }

    @Bean
    public MBeanExporter jobMBeanExporter(
            JobCoordinator jobCoordinator,
            MethodNameBasedMBeanInfoAssembler jobAssembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.app:type=JobCoordinator,name=default",
            jobCoordinator
        ));
        exporter.setAssembler(jobAssembler);
        return exporter;
    }
}
\`\`\`

When the exporter creates a ModelMBean from the POJO, the assembler describes the accessible JMX members. `internalDebugSnapshot` is not in the list, so it is not a public operation selected by this assembler.

Distinguish between **methods included in metadata** and **methods merely present in the Java class**. Regular public methods do not automatically become operations in this example.

### 5.2. Common Assembler Types

| Assembler | How Members Are Selected | Suitable When |
|---|---|---|
| `SimpleReflectiveMBeanInfoAssembler` | Based on reflection over many public methods | Demos or strictly controlled environments, avoiding unintended API expansion |
| `MethodNameBasedMBeanInfoAssembler` | Selected by a list of method names | Few beans, wanting an explicit whitelist |
| `MethodExclusionMBeanInfoAssembler` | Excludes methods in a list | When most of the surface may be exposed, but specific methods must be blocked |
| `InterfaceBasedMBeanInfoAssembler` | Selects methods based on specified interfaces | Wanting management through a separate Java contract |
| `MetadataMBeanInfoAssembler` | Retrieves metadata from annotations or a metadata source | Wanting descriptions via Spring JMX annotations |

For production systems, an explicit whitelist is usually easier to control than opening all public methods. When using reflection or exclusion, consider the future impact when a new public method is added to the class.

## 6. InterfaceBasedMBeanInfoAssembler: Management Contract for POJOs

A regular bean can implement a business/management interface for JMX **without having to follow the Standard MBean interface naming convention**. That interface is simply used as the method list for the assembler.

For example:

\`\`\`java
package com.example.jmx;

public interface JobOperations {
    int getMaxParallelJobs();
    void setMaxParallelJobs(int value);
    boolean isPaused();
    void pause();
    void resume();
}
\`\`\`

\`\`\`java
package com.example.jmx;

public class JobCoordinator implements JobOperations {
    private int maxParallelJobs = 4;
    private boolean paused = false;

    @Override public int getMaxParallelJobs() {
        return maxParallelJobs;
    }

    @Override public void setMaxParallelJobs(int value) {
        maxParallelJobs = value;
    }

    @Override public boolean isPaused() {
        return paused;
    }

    @Override public void pause() {
        paused = true;
    }

    @Override public void resume() {
        paused = false;
    }

    public void clearAllProductionData() {
        // Not part of JobOperations; not exported.
    }
}
\`\`\`

Assembler configuration:

\`\`\`java
import org.springframework.jmx.export.assembler.InterfaceBasedMBeanInfoAssembler;

@Bean
InterfaceBasedMBeanInfoAssembler interfaceAssembler() {
    InterfaceBasedMBeanInfoAssembler assembler =
        new InterfaceBasedMBeanInfoAssembler();
    assembler.setManagedInterfaces(JobOperations.class);
    return assembler;
}
\`\`\`

Then pass it into `exporter.setAssembler(interfaceAssembler)` and register the bean in the mapping as in the previous example.

Important distinction:

- With **Standard MBean**, an interface named `JobCoordinatorMBean` by JMX convention is used directly by Java/JMX to define the contract.
- With **InterfaceBasedMBeanInfoAssembler**, Spring actively reads the interface you specify to build ModelMBean metadata for a regular bean. The interface name does not have to follow the `ClassNameMBean` pattern.

Methods not in the management interface will not be exposed by this assembler simply because they are public Java methods. With proxies/AOP and method resolution, verify that the actual proxy exposes the methods that the ModelMBean will invoke.

## 7. MetadataMBeanInfoAssembler and Spring Annotations

Spring provides a group of JMX annotations in the package:

\`\`\`text
org.springframework.jmx.export.annotation
\`\`\`

For example:

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=JobCoordinator,name=annotation",
    description = "Controls jobs at runtime"
)
public class AnnotatedJobCoordinator {
    private volatile int maxParallelJobs = 4;

    @ManagedAttribute(description = "Maximum concurrent jobs")
    public int getMaxParallelJobs() {
        return maxParallelJobs;
    }

    @ManagedAttribute(description = "Changes maximum concurrent jobs")
    public void setMaxParallelJobs(int value) {
        if (value < 1 || value > 32) {
            throw new IllegalArgumentException("Expected 1..32");
        }
        maxParallelJobs = value;
    }

    @ManagedOperation(description = "Pauses job intake")
    public void pause() {
        // ...
    }

    public void dangerousInternalMethod() {
        // Not exposed when only annotated members are selected.
    }
}
\`\`\`

In addition, `MetadataMBeanInfoAssembler` needs a `JmxAttributeSource` to read annotation metadata. `AnnotationJmxAttributeSource` is the common implementation:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Bean
AnnotationJmxAttributeSource jmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
MetadataMBeanInfoAssembler annotationAssembler(
        AnnotationJmxAttributeSource source) {
    MetadataMBeanInfoAssembler assembler =
        new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}
\`\`\`

In typical configurations, `@EnableMBeanExport` can automatically register the necessary annotation-export components. Avoid configuring multiple exporters scanning the same beans concurrently without clear intent, as this leads to duplicate registrations or inconsistent naming.

### Annotations Are Not Equivalent to an MBean Interface

`@ManagedResource` does not turn a class into a Standard MBean by Java convention. Spring needs an appropriate assembler/exporter to create the management object. When JConsole sees the exported MBean, it communicates via standard JMX without knowing or needing to know that the original bean is a Spring POJO.

## 8. One MBeanExporter for Both Standard MBeans and POJOs

The same exporter can be configured to export both bean types if the application needs to manage them under one namespace. For example:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Configuration
public class CombinedJmxConfig {

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public JobCoordinator jobCoordinator() {
        return new JobCoordinator();
    }

    @Bean
    public MBeanExporter combinedExporter(
            WorkerControl workerControl,
            JobCoordinator jobCoordinator) {

        MethodNameBasedMBeanInfoAssembler assembler =
            new MethodNameBasedMBeanInfoAssembler();
        assembler.setManagedMethods(
            "getMaxParallelJobs",
            "setMaxParallelJobs",
            "isPaused",
            "pause",
            "resume"
        );

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerControl,name=primary",
            workerControl,
            "com.example.app:type=JobCoordinator,name=default",
            jobCoordinator
        ));
        return exporter;
    }
}
\`\`\`

Here `WorkerControl` is a Standard MBean and `JobCoordinator` is a POJO. The exporter can distinguish beans that already fulfill an MBean contract from beans that need an adapter. The assembler is configured to describe the POJO; **do not assume the assembler can arbitrarily rewrite a Standard MBean contract into a new list of methods**.

When using one assembler for multiple different POJO beans, avoid using a single shared method list that only fits one class. Use an assembler that supports configuration by bean key, annotations, or separate configurations if the management contracts differ.

## 9. Verifying via MBeanInfo: The JMX Client's Source of Truth

What a client can do is described by the `MBeanInfo` returned by the MBeanServer. Regardless of whether the underlying code is a Standard MBean or a POJO, clients should discover MBeans in the exact same way.

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

static void inspect(MBeanServer server, ObjectName name)
        throws Exception {

    MBeanInfo info = server.getMBeanInfo(name);

    System.out.println("MBean: " + name);
    System.out.println("Class: " + info.getClassName());

    for (MBeanAttributeInfo attribute : info.getAttributes()) {
        System.out.printf(
            "attribute=%s, type=%s, readable=%s, writable=%s%n",
            attribute.getName(),
            attribute.getType(),
            attribute.isReadable(),
            attribute.isWritable()
        );
    }

    for (MBeanOperationInfo operation : info.getOperations()) {
        System.out.print("operation=" + operation.getName() + "(");
        var params = operation.getSignature();
        for (int i = 0; i < params.length; i++) {
            if (i > 0) System.out.print(", ");
            System.out.print(params[i].getType());
        }
        System.out.println(")");
    }
}
\`\`\`

Example call:

\`\`\`java
ObjectName worker = new ObjectName(
    "com.example.app:type=WorkerControl,name=primary"
);
ObjectName coordinator = new ObjectName(
    "com.example.app:type=JobCoordinator,name=default"
);

inspect(server, worker);
inspect(server, coordinator);
\`\`\`

Then the client can read attributes and invoke operations based on the metadata:

\`\`\`java
int threads = (Integer) server.getAttribute(
    worker, "MaxThreads"
);

server.setAttribute(
    coordinator,
    new javax.management.Attribute("MaxParallelJobs", 6)
);

server.invoke(
    coordinator,
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

Even though the two bean types are exported differently, the client uses the same JMX API. This is the goal of the MBean exporter and ModelMBean adapter mechanism.

## 10. ObjectName Mapping and NamingStrategy

`MBeanExporter` needs to determine an ObjectName for each bean. You can provide explicit names in `setBeans`, or configure a naming strategy to generate names consistently.

Explicit mapping example:

\`\`\`java
exporter.setBeans(Map.of(
    "com.example.app:type=WorkerControl,name=primary", workerControl,
    "com.example.app:type=JobCoordinator,name=default", jobCoordinator
));
\`\`\`

For multi-instance systems, the `name` or `instance` key must ensure that two beans of the same type within one MBeanServer have different ObjectNames. Two different JVMs have separate registries, so they can use the same logical name without directly colliding.

If an `ObjectNamingStrategy` is needed, it can be created based on the bean key in the context:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class ApplicationNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey) throws MalformedObjectNameException {

        String safeKey = beanKey.replaceAll(
            "[^a-zA-Z0-9._-]", "_"
        );

        return new ObjectName(
            "com.example.app:type=ManagedBean,name=" + safeKey
        );
    }
}
\`\`\`

This illustrates the strategy; in production, handle collisions when two different bean keys normalize to the same value. Use a stable naming contract and validate key values instead of replacing characters uncontrollably.

## 11. Common Errors When Exporting Both Bean Types

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| `NotCompliantMBeanException` | MBean does not conform to Standard/Dynamic MBean conventions and is not wrapped properly | Check the `XxxMBean` interface or assembler configuration |
| `InstanceAlreadyExistsException` | Two beans registered with the same ObjectName | Check mappings, auto-export, and duplicate exporters |
| POJO exported but missing attributes | Assembler did not select getters/setters or metadata is incorrect | Inspect `MBeanInfo`, method whitelist, and annotations |
| Internal operation exposed | Assembler is too broad, e.g., reflection exposing public methods | Switch to a whitelist/interface/annotations |
| Client fails with operation name error | Client uses Java method name while MBean metadata differs | Retrieve `MBeanOperationInfo` from the server |
| Attribute write fails | Attribute is read-only or value type mismatches | Check `isWritable()` and `getType()` |
| Proxy/AOP causes discrepancy | Proxy methods do not match metadata or target | Inspect actual bean, proxy interface, and exporter |
| MBean disappears on context shutdown | Exporter unregisters MBeans when bean/context is destroyed | Monitor Spring lifecycle and MBeanServer |
| Calling wrong MBeanServer | Exporter and client use two different servers | Compare injected/configured servers |
| Annotations have no effect | Missing annotation assembler or corresponding `@EnableMBeanExport` | Check `MetadataMBeanInfoAssembler` and attribute source |

Exceptions and how Spring wraps them may vary by Spring version, MBean type, and failure timing. The table is a diagnostic guide; inspect the cause chain and runtime logs.

### The Double-Registration Problem

If a class is annotated with `@ManagedResource`, added to `setBeans`, and also auto-detected by another exporter, multiple attempts to export the same MBean can occur. This must be resolved with a clear configuration specifying **which single entity owns the registration**, not simply by renaming the ObjectName to mask the duplicate symptom.

## 12. Choosing an Assembler by Goal

Some selection rules:

**Standard MBean interface already exists**

Use that Standard MBean contract if suitable. There is no need to convert it to POJO export just because the application uses Spring.

**Regular bean with only a few management methods**

Use `MethodNameBasedMBeanInfoAssembler` to select exactly the required methods.

**Regular bean with a dedicated management interface**

Use `InterfaceBasedMBeanInfoAssembler` to keep the contract independent of the implementation, especially when multiple implementations need the same interface.

**Bean with JMX annotations**

Use Spring's annotation exporter/metadata assembler and annotate members intentionally.

**Bean containing many internal/sensitive methods**

Prefer a whitelist, interface, or annotations. Do not use an assembler that reflects all public methods by default if there is a risk of exposing internal methods.

**High dynamic metadata needs**

Consider `DynamicMBean` when metadata genuinely changes dynamically and full control of the JMX contract is needed; in return, implementation is more complex and requires handling the JMX API directly.

## 13. Security and Lifecycle Controls

Exporting a bean creates a runtime management surface. Information exposed via JMX can be very sensitive, especially if writing attributes or invoking operations is allowed.

- Expose only necessary methods; the assembler is one layer controlling the API surface.
- Validate inputs in setters/operations, even when JConsole displays valid types.
- Do not expose getters returning tokens, passwords, personal information, or internal secrets.
- Restrict JMX remote with authentication, authorization, and transport protection.
- When the context stops, the exporter should unregister MBeans it manages according to the Spring lifecycle.
- With multiple application contexts sharing a server, use clear namespaced names and establish ownership.
- Audit state-changing management operations, without logging sensitive data.

A writable attribute via JMX typically changes running state; it does not automatically persist configuration across restarts. To retain it, the service needs its own persistence mechanism.

## 14. Practice Exercises

### Exercise 1: Identify the Export Path

Given two beans:

\`\`\`java
class A implements AMBean { /* ... */ }
class B { public int getCount() { return 0; } }
\`\`\`

`A` can be exported under the Standard MBean contract if the interface and methods are valid. `B` is not a Standard MBean; to expose `Count` as a JMX attribute via Spring, use an appropriate assembler or annotation export.

### Exercise 2: Why Doesn't the Assembler See a Method?

Bean `JobCoordinator` has `resetCounters()`, but the assembler only manages `getMaxParallelJobs`, `setMaxParallelJobs`, `pause`, `resume`.

The `resetCounters` method will not be selected by that assembler for exposure. To expose it, add the name to the whitelist or annotation/interface according to the management contract.

### Exercise 3: Diagnosing Duplicate ObjectName

Two Spring contexts on the same platform MBeanServer export:

\`\`\`text
com.example.app:type=WorkerControl,name=default
\`\`\`

Two registrations cannot coexist with this ObjectName in one server. Distinguish `context`, `name`, or another meaningful key; also check whether the same bean is being exported twice.

### Exercise 4: Comparing an MBean Interface and an Assembler Interface

Explain the difference between:

\`\`\`java
class Worker implements WorkerMBean
\`\`\`

and

\`\`\`java
class Worker implements WorkerOperations
\`\`\`

where `WorkerOperations` is passed into `InterfaceBasedMBeanInfoAssembler`.

The first follows the Java JMX convention; the second uses a Spring assembler to generate ModelMBean metadata from the selected interface.

### Exercise 5: Client-Side `ClassCastException`

MBean attribute `ProcessedCount` has type `long`; the client writes:

\`\`\`java
Integer count = (Integer) server.getAttribute(name, "ProcessedCount");
\`\`\`

The client casts to the wrong type; the returned value is typically `Long`. Check `MBeanAttributeInfo.getType()` and cast accordingly.

### Exercise 6: Accidentally Exporting a Dangerous Method

A service has a public `deleteAllRecords()`. If an overly broad reflective assembler is used, that operation can become part of the JMX surface. The solution is to switch to a whitelist/interface/annotations restricting management methods and inspect the actual `MBeanInfo`.

## 15. Takeaways

For a **bean that is already an MBean**, Spring `MBeanExporter` primarily **registers** the object according to its existing JMX contract. For a **regular Java/Spring bean**, Spring uses an **assembler and ModelMBean adapter** to define the management surface to expose.

The two export paths differ yet converge on a unified client interface: `MBeanServer`, `ObjectName`, `getAttribute`, `setAttribute`, and `invoke`. Good design starts with a small, stable management contract with clear names, exposing only members that genuinely serve operations, and verifying the result via the `MBeanInfo` of the registered MBean.