# SimpleReflectiveMBeanInfoAssembler in Spring Framework JMX

## 1. Purpose

When a Spring bean is published as an MBean via JMX, the MBeanServer needs to know which **attributes** and **operations** that bean exposes. This information is represented by \`MBeanInfo\`, which includes the list of attributes, operations, constructors, notifications, and related descriptors.

Spring Framework provides the \`MBeanInfoAssembler\` interface and several implementations to determine the published **management surface**. \`SimpleReflectiveMBeanInfoAssembler\` is a reflection-based assembler that uses a bean's public Java methods to build management metadata by default rules rather than requiring annotation metadata or a pre-specified list of methods.

Its convenience is also an important limitation: if a bean has many public methods, a simple reflective assembler can expose methods intended only for internal implementation. Therefore, it is important to understand its behavior, scope of use, and security boundaries before using it.

## 2. What role does the assembler play?

\`MBeanExporter\` is the Spring component that registers Spring beans with an \`MBeanServer\`. When a bean is not already a standard JMX-compliant MBean, the exporter can adapt the bean into a \`ModelMBean\`. \`MBeanInfoAssembler\` determines the metadata that will appear in the adapted object's MBeanInfo.

High-level processing flow:

\`\`\`text
Spring-managed bean
      |
      v
MBeanExporter
      |
      +--> MBeanInfoAssembler
      |         |
      |         +--> discover getters/setters -> JMX attributes
      |         +--> discover methods         -> JMX operations
      |
      +--> ObjectNamingStrategy -> ObjectName
      |
      v
JMX ModelMBean / MBeanServer
      |
      v
JConsole / VisualVM / JMX client
\`\`\`

An assembler does not open a remote connector on its own, does not register every bean in the context, and does not authorize clients. It determines the **management metadata of beans selected for export**, while registration, naming, and connectors belong to other components.

## 3. What is SimpleReflectiveMBeanInfoAssembler?

The class resides in the package:

\`\`\`java
org.springframework.jmx.export.assembler.SimpleReflectiveMBeanInfoAssembler
\`\`\`

It belongs to Spring JMX's reflection-based assembler family. Under the default rules of this type of assembler:

- Public JavaBean getters/setters can be exposed as JMX attributes.
- Public methods can be exposed as JMX operations via reflection.
- There is no need to declare \`@ManagedAttribute\` or \`@ManagedOperation\` to select individual methods.
- Inherited methods and framework/public utility methods need to be considered when choosing this type of assembler.

Therefore, the name “SimpleReflective” describes **how metadata is generated from class shape**, and does not mean it is a simple security layer or read-only.

Example service:

\`\`\`java
public class CacheService {
    private int entryCount;

    public int getEntryCount() {
        return entryCount;
    }

    public void clearCache() {
        entryCount = 0;
    }

    public void reloadConfiguration() {
        // Reload configuration
    }
}
\`\`\`

If exported using a reflection assembler, a JMX client may see \`EntryCount\` as an attribute and public operations such as \`clearCache\` and \`reloadConfiguration\`, depending on the actual metadata. This differs from manually specifying “only expose getEntryCount”.

**Design perspective:** Being public to Java callers does not mean suitable for exposure to a JMX operator. A public method may serve an internal API and not be designed for invocation from a management tool with access privileges.

## 4. Distinguishing getters/setters from operations

JMX has the concepts of attributes and operations:

- **Attribute** represents readable or writable state, typically mapped from JavaBean getters/setters.
- **Operation** represents an action, typically mapped from a Java method exposed in \`MBeanOperationInfo\`.
- **MBeanInfo** describes the contract that JMX clients see, and does not necessarily reflect every class detail.

Example:

\`\`\`java
public class WorkerPool {
    private volatile boolean enabled = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getActiveWorkers() {
        return 4;
    }

    public void requestRefresh() {
        // Request refresh
    }
}
\`\`\`

A corresponding MBeanInfo might provide:

\`\`\`text
Attributes
  Enabled        boolean  readable=true  writable=true
  ActiveWorkers  int      readable=true  writable=false

Operations
  requestRefresh()
\`\`\`

However, what needs to be verified is the actual output of the assembler on the corresponding class. You should not guess the entire set of exposed operations solely from the table above because rules for excluding getters/setters from operations and handling inherited methods can affect the metadata.

When you only want \`ActiveWorkers\` and \`requestRefresh\`, you need to choose an assembler/configuration that allows controlling those exact methods.

## 5. Configuration example with MBeanExporter

Example of Java-based Spring configuration creating a managed bean and using \`SimpleReflectiveMBeanInfoAssembler\`:

\`\`\`java
package com.example.config;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.SimpleReflectiveMBeanInfoAssembler;

@Configuration
public class JmxConfiguration {

    @Bean
    public WorkerPoolControl workerPoolControl() {
        return new WorkerPoolControl();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            WorkerPoolControl workerPoolControl) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.jobs:type=WorkerPool,name=Main",
            workerPoolControl
        ));
        exporter.setAssembler(
            new SimpleReflectiveMBeanInfoAssembler()
        );

        return exporter;
    }
}
\`\`\`

Exported bean:

\`\`\`java
package com.example.config;

public class WorkerPoolControl {
    private volatile boolean enabled = true;
    private volatile int activeWorkers = 2;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getActiveWorkers() {
        return activeWorkers;
    }

    public void requestRefresh() {
        // An illustrative management operation.
    }
}
\`\`\`

\`setBeans\` explicitly specifies the bean and the key used as the ObjectName. The key in the example is a valid ObjectName string. In this setup, \`MBeanExporter\` adapts the object through the assembler and then registers it with the configured MBeanServer or the server the exporter locates.

Do not enable another exporter that registers the same ObjectName unintentionally; if a context configures \`@EnableMBeanExport\` alongside a manual exporter, check for potential duplicate registration.

### Important configuration note

\`SimpleReflectiveMBeanInfoAssembler\` is only a way to select metadata. If the application contains a bean that is already a JMX-compliant MBean or the exporter configuration uses a different adaptation path, the actual metadata may follow the rules of that MBean. Therefore, inspect \`MBeanInfo\` after registration rather than assuming all objects are reflected through a single path.

## 6. Running example and inspecting MBeanInfo

You can inspect the exported attributes/operations using standard JMX APIs:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectMBean {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=WorkerPool,name=Main"
        );

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                "MBean is not registered: " + name
            );
        }

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf(
                "Attribute %s type=%s read=%s write=%s%n",
                attr.getName(),
                attr.getType(),
                attr.isReadable(),
                attr.isWritable()
            );
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.println(
                "Operation " + operation.getName()
            );
        }
    }
}
\`\`\`

This snippet assumes the MBean has been exported to the platform MBeanServer. If the exporter uses a different MBeanServer, you must obtain that exact connection or server.

Inspecting \`MBeanInfo\` is useful because it shows the final JMX contract rather than just the methods you intended to expose in Java.

## 7. Comparison with other MBeanInfoAssemblers

Spring provides several strategies for selecting the management surface:

| Assembler | Principle | Suitable use cases |
| --- | --- | --- |
| \`SimpleReflectiveMBeanInfoAssembler\` | Simple reflection, broadly exposes public members per assembler rules | Prototypes, controlled internal apps, dedicated management classes with small APIs |
| \`MethodNameBasedMBeanInfoAssembler\` | Selects methods by a configured list of names | When you want to allowlist a few operations/accessors |
| \`MethodExclusionMBeanInfoAssembler\` | Reflection but excludes listed methods | When only needing to exclude a few methods from a controlled surface |
| \`InterfaceBasedMBeanInfoAssembler\` | Selects methods based on specified interfaces | When there is a clear management interface |
| \`MetadataMBeanInfoAssembler\` | Selects by metadata/annotations via \`JmxAttributeSource\` | When selective annotation-based JMX export is desired |

The difference lies in **who decides the list of exposed methods**:

\`\`\`text
SimpleReflective -> looks at public methods of the class
MethodNameBased  -> takes methods in the allowlist
MethodExclusion  -> reflects but excludes specified methods
InterfaceBased   -> takes from the management interface
Metadata         -> takes from annotations/metadata
\`\`\`

If a class contains only a designed management API, simple reflection can reduce configuration. If a class is a business service with many public methods, prefer an allowlist, management interface, or annotations to prevent unintended exposure.

## 8. Comparison with @ManagedAttribute and @ManagedOperation

Annotation-based JMX configuration:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Main"
)
public class WorkerPoolControl {
    @ManagedAttribute
    public int getActiveWorkers() {
        return 2;
    }

    @ManagedOperation
    public void requestRefresh() {
        // Refresh logic
    }

    public void deleteAllRecords() {
        // Internal API, not intended to be exposed via JMX.
    }
}
\`\`\`

With annotation-based export configured via \`@EnableMBeanExport\` or \`MetadataMBeanInfoAssembler\`, \`@ManagedAttribute\` and \`@ManagedOperation\` metadata are used to decide the export scope.

With \`SimpleReflectiveMBeanInfoAssembler\`, those annotations are not the assembler's default filter. The public method \`deleteAllRecords\` can be exposed as a JMX operation even without \`@ManagedOperation\`.

**You cannot simply add annotations and assume other public methods are hidden if the exporter still uses simple reflection.** You must select the right assembler and inspect the published \`MBeanInfo\`.

## 9. Security: reflection is not a permission allowlist

Some dangerous misconceptions:

> “Methods without annotations cannot be called by JMX.”

This is only true when a selective annotation/metadata assembler is used with an appropriate configuration. With a reflection assembler, public methods can be exposed by reflection rules even without annotations.

> “Private methods are safe; all public methods can be exposed.”

Java \`public\` only describes callability in a Java API, not suitability for operation over a network. JMX clients may be granted permission to call \`invoke\`, and a public method like \`resetDatabase()\` or \`shutdown()\` can cause major impact if exported accidentally.

> “Only using JConsole internally so no restrictions are needed.”

Local JMX tools also hold management privileges and can be misused. Remote connectors additionally carry network, credential, and authorization risks. Limiting the MBean surface is an added layer of defense.

APIs that should not be accidentally exposed:

- \`getPassword()\`, \`getAccessToken()\`, or getters returning configuration containing secrets.
- \`deleteAll()\`, \`shutdown()\`, \`execute(String command)\`, and high-impact management functions.
- Getters returning large collections, objects containing user data, or internal object graphs.
- Unbounded, resource-intensive database/network operations.
- Debug methods that mutate state without auditing or validation.

A practical rule: **in production, do not use simple reflection directly on large business services just to avoid writing annotations**. If needed, export a dedicated adapter that only has public methods meant for management.

## 10. Separating a management adapter when wanting to use simple reflection

Suppose a business service has a broad API:

\`\`\`java
public class OrderService {
    public int getPendingCount() { /* ... */ return 0; }
    public void submitOrder(String payload) { /* ... */ }
    public void cancelOrder(String id) { /* ... */ }
    public void purgeFailedOrders() { /* ... */ }
}
\`\`\`

If exporting the service directly with simple reflection, many public operations can appear unexpectedly. Replace it with a small management adapter:

\`\`\`java
public class OrderManagementView {
    private final OrderService service;

    public OrderManagementView(OrderService service) {
        this.service = service;
    }

    public int getPendingCount() {
        return service.getPendingCount();
    }

    public String getStatus() {
        return "RUNNING";
    }
}
\`\`\`

Register only \`OrderManagementView\` through \`MBeanExporter\`. In this case, the adapter's public surface has few methods and carries clear management semantics. However, you still need to inspect \`MBeanInfo\`: inherited public methods or methods added in the future can also change the reflected contract.

If strict control is required, prefer \`InterfaceBasedMBeanInfoAssembler\`, \`MethodNameBasedMBeanInfoAssembler\`, or an annotation-based assembler that lets you pick the exact list.

## 11. Common pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| JConsole shows more operations than intended | Simple reflection picks up public methods | Switch to a metadata/interface/allowlist assembler |
| Unannotated methods still appear | Annotations are not a filter for simple reflection | Choose \`MetadataMBeanInfoAssembler\` |
| Getter appears as a writable attribute | Corresponding public setter is also exposed | Remove setter from contract or use a selective assembler |
| Poor metadata descriptions | Reflection does not provide dedicated descriptions like annotations | Use metadata annotations or an assembler supporting descriptions |
| MBean not visible | Exporter has not registered it, wrong ObjectName/server | Check MBeanExporter config, name, and MBeanServer |
| \`InstanceAlreadyExistsException\` | Duplicate ObjectName in MBeanServer | Use unique ObjectNames, avoid duplicate exporter registrations |
| Remote client fails when reading attribute | Type not deserializable or class missing on client | Use primitives/Open Types/MXBean-compatible data |
| Monitoring getter slows down the system | Heavyweight getter polled continuously | Return snapshots/counters and bound resources |

### What to know when refactoring

If a method was previously not exposed but after a refactor is opened as public, simple reflection can bring it into MBeanInfo. Thus refactoring internal code unintentionally becomes a **management API change**. Every time you add a public method to a class exported via reflection, review its JMX impact.

Conversely, renaming a method or changing its signature can break dashboards/scripts calling the old attribute/operation. Therefore, treat the management contract as an API with version compatibility requirements.

## 12. Performance and concurrency

The assembler typically builds metadata during export, whereas **MBean getters/operations are invoked when clients request them**, potentially many times and concurrently.

- Getters exposed as attributes should be fast and side-effect-free.
- Do not let a getter scan an entire database or allocate huge objects on every poll.
- Avoid state-mutating operations if clients can call them repeatedly without authentication/validation.
- State written by multiple threads must be thread-safe; reflection does not add locking.
- Metric attributes should have clear units, semantics, and conventions when unavailable.
- When multiple consistent metrics are needed, consider a snapshot instead of fragmented reads over a long window.

A class having a \`public String getStatus()\` method is not automatically safe. If \`getStatus()\` opens a network connection or holds a lock for a long time inside, JMX monitoring can still slow down the application.

## 13. Assembler selection scenarios

### Scenario A: Demo applications or internal tools

A small class with only \`getActiveCount\`, \`isEnabled\`, \`requestRefresh\`; the maintainer wants to view it immediately via JConsole. \`SimpleReflectiveMBeanInfoAssembler\` can help reduce metadata configuration.

### Scenario B: Production business services with broad APIs

The service has many public methods, including data modifications. Do not export it directly via simple reflection. Use a selective management adapter and a metadata/interface-based assembler.

### Scenario C: Management API that needs stability across versions

A dedicated management interface with \`InterfaceBasedMBeanInfoAssembler\` or an annotation contract can make changes to attributes/operations easier to detect. Avoid letting reflection automatically expand the contract whenever an internal public method is added.

### Scenario D: Needing names/descriptions in JMX tools

\`MetadataMBeanInfoAssembler\` combined with \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` usually provides more accurate metadata declaration capabilities than simple reflection.

## 14. Mental model

\`\`\`text
                     Spring bean
                         |
             +-----------+-----------+
             |                       |
      SimpleReflective          Metadata/Interface
             |                       |
       Public methods          Selected methods
       Getter / setter         Annotation/interface
             |                       |
             +----------+------------+
                        |
                   MBeanInfo
                        |
                  MBeanExporter
                        |
                  MBeanServer
                        |
                JMX management client
\`\`\`

**Key takeaway:** \`SimpleReflectiveMBeanInfoAssembler\` creates a management interface by reflecting a bean's public methods, making configuration fast but prone to exposing more than intended. It does not rely on \`@ManagedAttribute\`/\`@ManagedOperation\` as an allowlist. For Spring JMX in real applications, prefer a small management API, explicitly selected metadata, MBeanInfo inspection, and connector access restrictions. Reflection is a metadata generation technique, not a security policy.
