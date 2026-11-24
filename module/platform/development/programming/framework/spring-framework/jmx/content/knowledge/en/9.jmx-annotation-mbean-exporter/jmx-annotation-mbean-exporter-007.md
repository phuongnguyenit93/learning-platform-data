# AnnotationMBeanExporter: Distinguishing Explicit and Automatic Exporter Configuration

## 1. Objectives

In Spring Framework, a Java bean only becomes a JMX management component when an **export** mechanism registers it into an \`MBeanServer\`. Annotations such as \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` describe *what* is managed, whereas the exporter determines *which beans, with which ObjectNames, in which MBeanServer* are registered.

There are two common ways to organize configuration:

1. **Explicit:** the application proactively creates/configures \`MBeanExporter\`, specifying beans, ObjectNames, assembler, naming strategy, server, and registration behavior.
2. **Automatic (annotation-driven):** enables discovery of annotated beans, typically via \`@EnableMBeanExport\` in Java/Spring configuration, letting Spring create the required \`AnnotationMBeanExporter\` infrastructure.

Both still use the Spring JMX exporter and standard Java JMX. The main difference lies in **who owns the bean list, how names are chosen, and the level of registration control**.

\`\`\`text
                       Spring ApplicationContext
                                 |
           +---------------------+---------------------+
           |                                           |
     Explicit exporter                         Annotation-driven
     MBeanExporter                              @EnableMBeanExport
     setBeans({...})                           AnnotationMBeanExporter
           |                                           |
           +---------------------+---------------------+
                                 |
                     MBeanServer + ObjectName
                                 |
                 JConsole / VisualVM / JMX client
\`\`\`

Do not equate "has annotations" with "is already exported": a bean marked \`@ManagedResource\` does not appear in JMX by itself without an active, properly configured exporter mechanism.

## 2. Foundational Components

| Component | Responsibility |
|---|---|
| \`MBeanServer\` | Registers, finds, and interacts with running MBeans |
| \`ObjectName\` | Unique JMX name within an MBeanServer |
| \`MBeanExporter\` | Exports beans from Spring to JMX |
| \`AnnotationMBeanExporter\` | Exporter configuration tailored to annotation-driven JMX |
| \`@EnableMBeanExport\` | Enables annotation-driven export in Spring Java configuration |
| \`@ManagedResource\` | Marks a bean as a management resource and can set ObjectName/description |
| \`@ManagedAttribute\` | Exposes property getters/setters |
| \`@ManagedOperation\` | Exposes management operations |
| \`MetadataMBeanInfoAssembler\` | Reads management metadata described by annotations via a metadata source |
| \`AnnotationJmxAttributeSource\` | Supplies annotation metadata to the assembler |

Distinguish Spring JMX annotations from standard Java \`javax.management\`:

- Java JMX clients still invoke \`getAttribute\`, \`setAttribute\`, and \`invoke\` using \`MBeanServerConnection\`.
- Spring annotations primarily affect when a bean is exported, how \`ModelMBean\` metadata is built, and the registration name.
- \`@ManagedResource\` does not turn a class into a Standard MBean following the \`XxxMBean\` convention; exporting a POJO requires an appropriate adapter/assembler.

## 3. A Sample Bean Used for Both Approaches

Suppose an application has a task-processing service with management members:

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerControl,name=primary",
    description = "Worker runtime management"
)
public class WorkerControl {
    private volatile int maxThreads = 8;
    private final AtomicLong completed = new AtomicLong();

    @ManagedAttribute(description = "Configured worker limit")
    public int getMaxThreads() {
        return maxThreads;
    }

    @ManagedAttribute(description = "Change configured worker limit")
    public void setMaxThreads(int value) {
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException("maxThreads must be 1..64");
        }
        maxThreads = value;
    }

    @ManagedAttribute(description = "Completed jobs")
    public long getCompleted() {
        return completed.get();
    }

    @ManagedOperation(description = "Reset completed counter")
    public void resetCounter() {
        completed.set(0);
    }

    public void internalDiagnostics() {
        // Not annotated: not exposed by annotation metadata.
    }
}
\`\`\`

The example uses \`volatile\` and \`AtomicLong\` to focus on the JMX interface. In a real system, updating \`maxThreads\` must be wired to the corresponding executor/pool: changing a Java field alone does not reconfigure runtime resources.

Expected JMX contract:

\`\`\`text
ObjectName = com.example.app:type=WorkerControl,name=primary

Attributes:
  MaxThreads   int   readable + writable
  Completed    long  read-only

Operations:
  resetCounter()
\`\`\`

\`internalDiagnostics\` is not included in the management interface merely because it is public. Which members are selected depends on the assembler and actual metadata.

## 4. Explicit Configuration with MBeanExporter

When you want to specify each bean and JMX name explicitly, you can create \`MBeanExporter\` as a Spring bean.

Example using an annotation-reading assembler to ensure the POJO is exported according to \`@ManagedAttribute\` and \`@ManagedOperation\`:

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
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource attributeSource) {

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(attributeSource);
        return assembler;
    }

    @Bean
    public MBeanExporter workerExporter(
            WorkerControl workerControl,
            MetadataMBeanInfoAssembler jmxAssembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(jmxAssembler);
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerControl,name=primary",
            workerControl
        ));
        return exporter;
    }
}
\`\`\`

In this model, \`setBeans\` specifies the **exact beans** to export and their corresponding ObjectNames. The assembler determines **which members are exposed**. The name in \`setBeans\` is the application's explicit choice; keep it consistent with annotation metadata to avoid confusion when expanding configuration.

### 4.1. Benefits

- Provides a clear inventory of beans and ObjectNames.
- Easy to configure components with dynamic names or multiple instances of the same class.
- Easy to specify a particular \`MBeanServer\` when multiple servers exist.
- Can configure assembler, naming strategy, listeners, and registration policy at a single point of ownership.
- Suitable when you need to tightly constrain the management surface or integrate an existing JMX model.

### 4.2. Costs

- Configuration must be updated whenever managed beans are added or removed.
- Mapping can become repetitive in applications with many MBeans.
- If another annotation auto-detection mechanism is enabled simultaneously, duplicate registration risks arise.
- Configuration authors must understand the relationship between Spring beans, JMX metadata, and ObjectNames.

**Key takeaway:** an explicit exporter does not mean ignoring annotations. You can still use \`MetadataMBeanInfoAssembler\` to apply annotations, while bean selection and registration remain explicitly managed by the application.

## 5. Automatic Configuration with @EnableMBeanExport

In Spring Java configuration, a more concise approach is declaring:

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class AutomaticJmxConfiguration {

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }
}
\`\`\`

\`@EnableMBeanExport\` activates the annotation-based export mechanism. Spring registers the \`AnnotationMBeanExporter\` infrastructure, detects beans carrying matching metadata, and exports them to \`MBeanServer\`.

With \`WorkerControl\` annotated with \`@ManagedResource\`, the automatic exporter can find the bean and register the ObjectName described in the annotation:

\`\`\`text
com.example.app:type=WorkerControl,name=primary
\`\`\`

JMX members from \`@ManagedAttribute\` and \`@ManagedOperation\` are published according to Spring metadata. Beans that are unannotated or do not match detection criteria will not automatically be exported just by existing in the context.

### 5.1. When to use

- A moderate number of management resources.
- Each managed bean has clear annotation metadata.
- ObjectNames are stable and straightforward.
- The development team wants to declare the JMX contract close to code.
- No deep per-bean registration customization is needed.

### 5.2. Limitations to understand

- Annotations live on the class, so changing a JMX name may require changing code or related configuration.
- Multiple beans instantiated from the same class may share the same static \`objectName\`, causing collisions within the same \`MBeanServer\`.
- The automatic mechanism does not resolve ownership on its own if the application also creates a manual exporter.
- "Automatic" behavior only begins after the Spring context initializes and the export infrastructure is properly configured.

## 6. AnnotationMBeanExporter: What Is Automatic?

The name \`AnnotationMBeanExporter\` can mislead learners into thinking it is an independent server. In reality, this exporter is **Spring export configuration** using standard JMX infrastructure.

It reduces configuration effort by:

1. Detecting annotated beans according to the export mechanism.
2. Using an annotation metadata source to build MBean info.
3. Retrieving or deriving the ObjectName from configuration and metadata.
4. Registering the MBean with \`MBeanServer\`.
5. Managing unregistration according to the exporter/context lifecycle.

It does not guarantee:

- Every annotated bean has a non-colliding name under all instantiation patterns.
- Every public method should be exported.
- JMX access permissions are automatically secured.
- Writable attribute values are persisted to durable configuration.
- Other exporters in the same JVM will not conflict.

Thus, "automatic" mainly refers to **discovery and wiring**, not a replacement for management contract design.

## 7. Direct Comparison

| Criterion | Explicit MBeanExporter | Annotation-Driven Exporter |
|---|---|---|
| Who selects beans to export? | Mapping/configuration specified by the application | Annotation discovery mechanism |
| Who chooses ObjectName? | \`setBeans\`, naming strategy, or specific config | Annotation/naming strategy and exporter config |
| Needs \`@ManagedResource\`? | Not required if bean is a standard MBean; if using a metadata assembler, matching metadata is needed | Typically uses \`@ManagedResource\` |
| Needs \`@ManagedAttribute\`? | Yes if using an annotation assembler; another assembler may be used | Used to expose attributes |
| Per-bean configuration | More | Less |
| Multi-instance name customization | Easy to control directly via mapping | Requires a plan to avoid static name collisions |
| Control over exported beans | Explicit via mapping | Based on annotations and auto-detection |
| Duplicate registration risk | Yes if mappings collide or another exporter also registers | Yes if auto-detection and another exporter also register |
| Best suited for | Systems needing fine-grained control over each MBean | Applications managed consistently via annotations |

Both approaches can coexist in one system **if export scopes do not overlap** and ownership is strictly defined. However, a small application is usually easier to maintain when choosing one mechanism as the primary control point.

## 8. Which MBeanServer Is Used?

JMX MBeans are registered into a specific \`MBeanServer\`. A JVM can have the platform server as well as other servers created by the application.

In Spring, you can configure the server with an \`MBeanServer\` bean or an appropriate factory:

\`\`\`java
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Bean
MBeanServerFactoryBean mbeanServerFactory() {
    MBeanServerFactoryBean factory =
        new MBeanServerFactoryBean();
    factory.setLocateExistingServerIfPossible(true);
    return factory;
}
\`\`\`

This is one infrastructure configuration approach; verify the actual server chosen by the exporter. If a client queries the platform server while the exporter registers into a different server, \`InstanceNotFoundException\` will occur even though export succeeded.

With an explicit exporter, set the server via \`exporter.setServer(server)\`. With annotation-driven export, use the corresponding \`@EnableMBeanExport\` attributes and conventions for your Spring version.

**Do not create a new MBeanServer arbitrarily** just to avoid collisions. If multiple exporters intend to manage one process, clarify scope and MBean names first; separate servers can make monitoring harder to discover.

## 9. JMX Naming and ObjectName Collision Risk

Suppose you create two \`WorkerControl\` beans of the same class in one Spring context:

\`\`\`java
@Bean("primaryWorker")
WorkerControl primaryWorker() {
    return new WorkerControl();
}

@Bean("backupWorker")
WorkerControl backupWorker() {
    return new WorkerControl();
}
\`\`\`

If the class annotation contains:

\`\`\`java
@ManagedResource(
    objectName = "com.example.app:type=WorkerControl,name=primary"
)
\`\`\`

then both may attempt to use the same name. An \`MBeanServer\` does not allow two MBeans with the same ObjectName to coexist simultaneously. On registration, \`InstanceAlreadyExistsException\` or a Spring-wrapped exception may occur.

### 9.1. Explicit solution

Map each bean with its own distinct name:

\`\`\`java
exporter.setBeans(Map.of(
    "com.example.app:type=WorkerControl,name=primary",
    primaryWorker,
    "com.example.app:type=WorkerControl,name=backup",
    backupWorker
));
\`\`\`

When using annotation metadata with a static ObjectName, verify how mapping names and metadata names are prioritized in your configured exporter; it is best to keep a single consistent naming source.

### 9.2. Naming strategy solution

Use \`ObjectNamingStrategy\` to generate an ObjectName from the bean key or runtime ID:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class WorkerNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey) throws MalformedObjectNameException {

        String token = beanKey.replaceAll(
            "[^a-zA-Z0-9._-]", "_"
        );

        return new ObjectName(
            "com.example.app:type=WorkerControl,name=" + token
        );
    }
}
\`\`\`

This is a mechanism example and does not guarantee absolute uniqueness because two different bean keys could normalize to the same token. In production, validate the naming convention or assign a stable ID guaranteeing no collisions.

### 9.3. Multiple replicas across different JVMs

Two JVMs can register the same \`ObjectName\` because they use separate \`MBeanServer\` instances. Monitoring should distinguish target JVMs/endpoints rather than trying to synthesize globally unique names with random UUIDs. Only add \`instance\` to the ObjectName if the system needs to distinguish multiple MBeans with the same role inside the same server or has specific operational requirements.

## 10. Do Not Enable Two Exporters on the Same Bean

A common configuration mistake:

\`\`\`java
@Configuration
@EnableMBeanExport
class JmxConfig {

    @Bean
    WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    MBeanExporter extraExporter(WorkerControl workerControl) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerControl,name=primary",
            workerControl
        ));
        return exporter;
    }
}
\`\`\`

If the auto exporter detects \`WorkerControl\` and the explicit exporter also registers the same ObjectName, double-registration can occur. If an exporter has a collision-handling policy, one registration may be skipped or replaced, leaving MBean ownership unclear.

How to fix:

- Choose a single registration owner for each MBean.
- When combining them, ensure the two exporters are configured for disjoint sets of beans.
- Check which mechanism auto-detects the bean.
- Do not use \`IGNORE_EXISTING\` or \`REPLACE_EXISTING\` as a way to hide duplicate export without understanding ownership.
- Check which exporter unregisters the ObjectName on shutdown, preventing one context from removing an MBean still needed by another context.

Fix the **root cause of duplicate configuration** before changing conflict policies.

## 11. Spring Boot and Differences from Plain Spring Framework

In a plain Spring Framework application, \`@EnableMBeanExport\` is an option for enabling annotation JMX export.

In Spring Boot, JMX auto-configuration can be governed by application properties such as \`spring.jmx.enabled\`, exporter annotations, and Actuator. Therefore, do not assume Boot always enables export or always disables it across all configurations/versions.

Check:

1. JMX properties in the actual environment.
2. Existing \`MBeanExporter\`/\`AnnotationMBeanExporter\` beans already in the context.
3. Whether \`@EnableMBeanExport\` is also used manually.
4. Whether Actuator endpoints or other MBeans share the same ObjectName/domain.
5. Which \`MBeanServer\` the exporter actually registers into.

An application should only combine Boot JMX auto-configuration with a manual exporter when it clearly understands the scope and how to prevent duplication. Exact Boot properties can vary by version; consult the reference documentation matching your running dependencies.

## 12. Verifying Results via MBeanServer

Whether using explicit or annotation-driven configuration, the final result must be confirmed in \`MBeanServer\`.

Query example:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerControl,name=primary"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not exported: " + name);
}

MBeanInfo info = server.getMBeanInfo(name);
System.out.println("Class: " + info.getClassName());

for (var attr : info.getAttributes()) {
    System.out.printf(
        "%s: %s (R=%s W=%s)%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Verify that \`isRegistered(name)\` returns true, the expected attributes/operations appear, and the data types match the intended contract.

### 12.1. Read/write/invoke to confirm

\`\`\`java
Object current = server.getAttribute(name, "MaxThreads");
System.out.println("Before: " + current);

server.setAttribute(
    name,
    new javax.management.Attribute("MaxThreads", 12)
);

Object updated = server.getAttribute(name, "MaxThreads");
System.out.println("After: " + updated);

server.invoke(
    name,
    "resetCounter",
    new Object[0],
    new String[0]
);
\`\`\`

These calls only succeed if the MBean is registered and the JMX contract includes those members. Writing an attribute can modify live application state; run only with values suitable for a practice environment.

### 12.2. When the MBean does not appear

A verification flow:

\`\`\`text
MBean not visible
  |
  +-- Spring context initialized successfully?
  |
  +-- Active exporter present?
  |      |
  |      +-- Explicit: setBeans has right bean/ObjectName?
  |      +-- Automatic: @EnableMBeanExport enabled?
  |                     bean has @ManagedResource?
  |
  +-- Exporter registers into the right MBeanServer?
  |
  +-- ObjectName valid and non-duplicate?
  |
  +-- Bean created/discovered in context?
  |
  +-- Any export exception in startup log?
\`\`\`

Do not conclude export succeeded solely because annotations exist in source code.

## 13. Common Errors and How to Identify Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Bean has \`@ManagedResource\` but no MBean | Annotation export not enabled or bean not in context | Enable the right exporter and verify bean lifecycle |
| MBean lacks expected operation | Missing \`@ManagedOperation\` or different metadata assembler | Check annotations and \`MBeanInfo\` |
| \`InstanceAlreadyExistsException\` | ObjectName registered twice | Identify all exporters and owning beans |
| Client reports \`InstanceNotFoundException\` | Wrong name or wrong MBeanServer | Query actual ObjectName and server |
| Same bean exported twice | Explicit exporter and auto exporter both detect it | Separate scopes or remove one export path |
| Export shows fewer attributes than expected | Assembler selects fewer members than anticipated | Check \`MetadataMBeanInfoAssembler\` and annotations |
| Bean has multiple instances with static annotation name | ObjectName collision | Name by bean key/stable instance ID |
| MBean disappears when context stops | Exporter unregisters per lifecycle | Check shutdown ownership |
| MBean visible but JMX permissions wrong | Connector/server not secured as required | Design authentication, authorization, and network isolation |

Do not assume every export error is caused by annotations. An MBean can fail to register due to server, name, MBean type, lifecycle, or conflicts between configuration classes.

## 14. Guidelines for Choosing an Approach

### Choose explicit configuration when:

- The application has varied MBean types, including standard JMX-compliant MBeans and POJOs needing a specific assembler.
- ObjectNames must be controlled per deployment configuration or multiple instances.
- You want to map only select beans in the context as MBeans.
- You need to attach notification listeners, choose a dedicated server, or control registration policy proactively.
- The system needs to inventory and alter export rules in one centralized configuration point.

### Choose annotation-driven when:

- The application uniformly uses \`@ManagedResource\` on management components.
- Each bean has a clear JMX name with low collision risk.
- You want management methods close to code with \`@ManagedAttribute\` and \`@ManagedOperation\`.
- You want to reduce mapping boilerplate when adding MBeans following the same convention.
- No per-bean custom registration logic is required.

Neither option is universally better. Decide based on naming contract stability, MBean count, existing auto-configuration, and registration control requirements.

## 15. Distinguishing Practice Exercises

### Exercise 1: Annotated without enabling exporter

\`\`\`java
@ManagedResource(objectName = "com.example.app:type=Cache,name=products")
class ProductCacheControl { /* ... */ }
\`\`\`

If the context lacks an appropriate export mechanism, does this MBean appear automatically?

**Explanation:** No. Annotations are metadata; an exporter must run to register the MBean.

### Exercise 2: One class, two beans

Two beans of the same class share \`@ManagedResource(objectName = "...name=primary")\`. Which approach gives better control?

**Explanation:** You can use explicit mapping or a naming strategy to ensure distinct ObjectNames in the same server. Autodetection does not resolve static name collisions.

### Exercise 3: Adding a public method

There is an unannotated public method \`eraseAllData()\`. When using the annotation metadata assembler exposing only annotated methods, does this method appear as an operation?

**Explanation:** No. It must be included in the management interface via assembler/annotation configuration to be exported.

### Exercise 4: Boot has an exporter and the developer enables @EnableMBeanExport

If Boot already configures an exporter and the application adds \`@EnableMBeanExport\`, what needs checking?

**Explanation:** Check the number of exporters, bean selection mechanism, ObjectName collisions, and shutdown ownership; do not assume both configurations can overlap harmlessly.

### Exercise 5: Client does not see bean despite successful exporter logs

Which \`MBeanServer\` must be checked?

**Explanation:** The client must connect to the exact server/endpoint where the exporter registered. Two MBeanServers in the same JVM have independent registries.

### Exercise 6: When to use an explicit exporter even when the bean has annotations?

**Explanation:** When you need to explicitly specify beans, naming strategy, server, assembler, callbacks, or export scope. Annotations can continue to describe management members.

## 16. Key Takeaways

**Explicit** means the application directly decides the bean list, ObjectNames, and exporter configuration. **Automatic** means Spring's annotation infrastructure detects beans and registers JMX MBeans based on developer-declared metadata.

Both converge on the same client-side JMX API. A successful configuration requires three conditions: **the right bean is selected**, **ObjectNames do not collide in MBeanServer**, and **JMX metadata accurately describes the managed members**. When switching from one approach to the other, treat it as a runtime configuration change that can affect scripts and monitoring, and verify actual results with \`MBeanInfo\`.