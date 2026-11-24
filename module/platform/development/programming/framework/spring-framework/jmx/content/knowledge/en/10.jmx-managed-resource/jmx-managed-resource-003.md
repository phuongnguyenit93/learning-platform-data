# Autodetecting @ManagedResource Beans in Spring Framework JMX

## Lesson Objectives

After this lesson, you will be able to:

- Explain why the \`@ManagedResource\` annotation helps Spring Framework identify a bean that can be exported as a JMX MBean.
- Distinguish **bean autodetection** from **metadata assembly** and **MBean registration**.
- Configure \`MBeanExporter\` to automatically detect Spring beans with \`@ManagedResource\` without listing each bean via \`setBeans(...)\`.
- Use \`AnnotationJmxAttributeSource\`, \`MetadataMBeanInfoAssembler\`, and \`MetadataNamingStrategy\` when configuring manually.
- Inspect registered MBeans via \`MBeanServer\`, identify ObjectNames, and see which attributes/operations are actually exposed.
- Diagnose scenarios where \`@ManagedResource\` is present but JConsole does not show the MBean, or where automatic scanning causes duplicate name registrations.

## 1. Context: Needing to Export Many Spring Beans

A Spring application has many components that need management: caches, queues, schedulers, job processors, connection pools, or configuration controllers.

One manual registration approach is declaring each bean in \`MBeanExporter\`:

\`\`\`java
exporter.setBeans(Map.of(
    "learning.jmx:type=Cache,name=Products", productsCache,
    "learning.jmx:type=Queue,name=Primary", jobQueue
));
\`\`\`

This approach is explicit, but requires updating the exporter configuration whenever a new bean is added. Spring Framework JMX provides a way to declare **management metadata directly on the bean** using annotations in \`org.springframework.jmx.export.annotation\`. From there, the exporter can automatically discover qualifying beans according to certain rules.

Example:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Primary job queue"
)
public class QueueMonitor {
    // ...
}
\`\`\`

**Key point:** \`@ManagedResource\` describes a manageable resource. Simply placing the annotation on a class **does not automatically register an MBean** if the application has not enabled the corresponding exporter and autodetection mechanism.

## 2. What Does Autodetect Mean?

Within the scope of this lesson, **autodetect** means the Spring JMX exporter **automatically discovers beans in ApplicationContext marked as JMX-managed resources**, rather than requiring a manual list of names/instances for every bean.

Three logical steps:

\`\`\`text
Spring ApplicationContext
        |
        | contains beans
        v
MBeanExporter autodetect
        |
        | finds beans with corresponding JMX metadata
        v
Metadata assembler + naming strategy
        |
        | determines attributes, operations, ObjectName
        v
MBeanServer.registerMBean(...)
        |
        v
JConsole / JMX client
\`\`\`

Specifically:

- **Autodetection:** finds *which beans* to export.
- **Metadata assembly:** determines *which attributes and methods* to expose to JMX.
- **Naming strategy:** determines *which ObjectName* to use.
- **Registration:** registers the MBean into *which MBeanServer*.

Do not conflate these responsibilities. A bean may be detected yet export can still fail if it lacks an appropriate naming strategy, has an invalid ObjectName, collides on name, or has invalid metadata.

## 3. Annotations to Know

Spring Framework defines several annotations supporting JMX:

| Annotation | Target Level | Purpose |
|---|---|---|
| \`@ManagedResource\` | Class | Marks a managed resource, containing metadata such as ObjectName, description |
| \`@ManagedAttribute\` | Getter/setter | Exposes a management attribute |
| \`@ManagedOperation\` | Method | Exposes a management operation |
| \`@ManagedOperationParameter\` | Parameter | Describes an operation parameter |
| \`@ManagedNotification\` | Class annotation metadata | Declares supported notification types |

Autodetection relies on whether a class has an appropriate \`@ManagedResource\`. Having \`@ManagedAttribute\` or \`@ManagedOperation\` on an arbitrary bean does not automatically mean the exporter will autodetect that bean as a managed resource without an appropriate marker/configuration.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Queue monitor"
)
public class QueueMonitor {
    private volatile boolean paused;

    @ManagedAttribute(description = "Whether queue is paused")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Pause queue")
    public void pause() {
        paused = true;
    }
}
\`\`\`

With appropriate Spring JMX configuration, \`Paused\` becomes an attribute and \`pause()\` becomes an operation. Other unannotated public methods do not by default become JMX operations when using an annotation metadata assembler with annotation-based exposure policy.

## 4. Concise Approach: Enabling Annotation-Driven JMX

Spring Framework supports \`@EnableMBeanExport\` to enable annotation-based JMX export configuration. This is a convenient approach for applications managed with Java configuration.

Example:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Spring will set up the exporter infrastructure needed to detect managed resources by annotation. You do not need to write \`setBeans(...)\` for every resource in this configuration.

The bean must be managed by Spring, for example:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Queue lifecycle"
)
public class QueueMonitor {

    private volatile boolean paused;

    @ManagedAttribute(description = "Paused state")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Pause intake")
    public void pause() {
        paused = true;
    }

    @ManagedOperation(description = "Resume intake")
    public void resume() {
        paused = false;
    }
}
\`\`\`

**Important prerequisite:** the \`QueueMonitor\` class must be registered as a Spring bean, for example via component scanning or a \`@Bean\` declaration. \`@ManagedResource\` does not turn a Java object outside ApplicationContext into a Spring-managed bean.

When the context starts, the exporter scans/identifies managed resources and registers them under their ObjectNames into the MBeanServer in use.

### If Using XML Configuration

In Spring applications configured with XML, the \`<context:mbean-export />\` element provides the corresponding way to enable the annotation-driven JMX exporter.

XML example:

\`\`\`xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/context
         https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="example.jmx"/>

    <context:mbean-export/>
</beans>
\`\`\`

This is an alternative configuration style to Java annotations. Normally there is no need to enable multiple exporters simultaneously for the same managed resources in one context.

## 5. MBeanExporter with Autodetect Mode

When lower-level configuration control is needed, you can create \`MBeanExporter\` manually and set the autodetect mode.

Spring defines modes such as:

- \`AUTODETECT_NONE\`: do not autodetect beans.
- \`AUTODETECT_MBEAN\`: autodetect objects conforming to the Standard MBean convention.
- \`AUTODETECT_ASSEMBLER\`: use the assembler's managed resource recognition capability.
- \`AUTODETECT_ALL\`: combine supported detection mechanisms.

For annotation metadata, \`AUTODETECT_ASSEMBLER\` usually expresses the exact intent: finding beans recognized by the metadata assembler rather than relying solely on \`SomethingMBean\` interfaces.

Minimal configuration to understand component roles:

\`\`\`java
import java.lang.management.ManagementFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ExplicitJmxConfig {

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy namingStrategy =
                new MetadataNamingStrategy();
        namingStrategy.setAttributeSource(source);
        return namingStrategy;
    }

    @Bean
    public MBeanExporter jmxExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(
                ManagementFactory.getPlatformMBeanServer()
        );
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setAutodetectMode(
                MBeanExporter.AUTODETECT_ASSEMBLER
        );
        return exporter;
    }
}
\`\`\`

**Configuration meaning:**

1. \`AnnotationJmxAttributeSource\` reads metadata from JMX annotations.
2. \`MetadataMBeanInfoAssembler\` determines MBean info, attributes, and operations from metadata.
3. \`MetadataNamingStrategy\` retrieves the ObjectName from metadata such as \`@ManagedResource.objectName\`.
4. \`MBeanExporter\` automatically discovers qualifying beans and registers them into the platform MBeanServer.

This is an explicit educational configuration; in typical applications \`@EnableMBeanExport\` avoids writing repetitive infrastructure beans.

### Why Is the Right Assembler Needed?

If you only write:

\`\`\`java
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_ASSEMBLER
);
\`\`\`

without using an assembler capable of recognizing \`@ManagedResource\`, you should not assume the marker annotation will be handled properly. Autodetection mode and metadata strategy are complementary configurations.

### Should You Use AUTODETECT_ALL?

\`AUTODETECT_ALL\` can also detect Standard MBeans alongside beans recognized by the assembler. This is useful in applications that have both management styles, but can expand the exported bean set unexpectedly. When the requirement is simply “autodetect beans with @ManagedResource”, choosing a narrow, intentional mode is usually easier to control.

## 6. Where Does ObjectName Come From?

With the annotation:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary"
)
\`\`\`

MetadataNamingStrategy can use the ObjectName on the annotation to register the bean.

ObjectName has the form:

\`\`\`text
domain:key=value,key2=value2
\`\`\`

Examples:

\`\`\`text
learning.jmx:type=Queue,name=Primary
learning.jmx:type=Cache,name=Products
learning.jmx:type=Scheduler,name=Daily
\`\`\`

ObjectName must be valid and unique within **an MBeanServer**. If two beans annotate the same ObjectName, the exporter may encounter a duplicate registration error.

**Do not confuse ObjectName with class name:** Java class \`QueueMonitor\` can be registered under \`learning.jmx:type=Queue,name=Primary\`. Class name and ObjectName have different responsibilities.

### What If objectName Is Missing?

Name generation or fallback behavior depends on the naming strategy configuration. For a lesson on autodetection, you should provide an explicit ObjectName on \`@ManagedResource\` or define a deliberate naming strategy to reduce ambiguity. Do not guess the generated name without inspecting the actual configuration.

## 7. Complete Hands-On Example

Let us create two Spring beans with \`@ManagedResource\`, along with an ordinary business bean.

### 7.1. QueueMonitor

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Primary queue monitor"
)
public class QueueMonitor {
    private volatile boolean paused;

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation
    public void pause() {
        paused = true;
    }

    @ManagedOperation
    public void resume() {
        paused = false;
    }
}
\`\`\`

### 7.2. CacheMonitor

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=Cache,name=Products",
    description = "Product cache monitor"
)
public class CacheMonitor {
    private final AtomicInteger entryCount = new AtomicInteger(10);

    @ManagedAttribute
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedOperation
    public void clear() {
        entryCount.set(0);
    }
}
\`\`\`

### 7.3. Unannotated Bean

\`\`\`java
package example.jmx;

import org.springframework.stereotype.Component;

@Component
public class OrdinaryService {
    public String getStatus() {
        return "READY";
    }
}
\`\`\`

In a configuration based on metadata annotations and assembler autodetection, \`OrdinaryService\` is not automatically exported just because it is a \`@Component\`. This illustrates the boundary between Spring bean registration and JMX managed resource exposure.

### 7.4. Java Configuration

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan("example.jmx")
@EnableMBeanExport
public class ApplicationConfig {
}
\`\`\`

When initializing the context:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        ApplicationConfig.class)) {

            System.out.println("Context started");
            System.out.println("Press Enter to close");
            System.in.read();
        }
    }
}
\`\`\`

In JConsole, connect to the right Java process, open the MBeans tab, and look under the \`learning.jmx\` domain to find the two ObjectNames. The OrdinaryService bean is not exported under the metadata pattern above.

### 7.5. Verifying via MBeanServer

A check that does not depend on a graphical interface:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName queueName = new ObjectName(
        "learning.jmx:type=Queue,name=Primary"
);
ObjectName cacheName = new ObjectName(
        "learning.jmx:type=Cache,name=Products"
);

System.out.println(server.isRegistered(queueName));
System.out.println(server.isRegistered(cacheName));
\`\`\`

Expected output after the context initializes and the exporter has registered them:

\`\`\`text
true
true
\`\`\`

If the \`@EnableMBeanExport\` configuration uses an MBeanServer other than the platform server or the application has custom configuration, you must check **the exact server being used by the exporter**. Do not assume a new Java process can call \`ManagementFactory.getPlatformMBeanServer()\` and inspect another process's MBeans; an MBeanServer is a per-JVM resource.

## 8. Does Autodetection Scan the Entire Classpath?

No. In the \`MBeanExporter\` model, autodetection primarily works with **beans managed inside the Spring ApplicationContext and visible within the exporter's scope**.

This differs from component scanning:

- \`@ComponentScan\` finds eligible classes to register as Spring beans.
- \`@ManagedResource\` declares the JMX metadata of that bean.
- \`MBeanExporter\` autodetection finds qualifying beans in the context to export.

If a class has \`@ManagedResource\` but has not been registered as a Spring bean, the exporter does not search bytecode classes across every JAR and create instances for you.

### Impact of Parent-Child Contexts

Applications with parent and child contexts can have different bean scopes. If multiple exporters simultaneously detect a bean/ObjectName identifier, conflicts may arise. You must clearly determine which context owns the export and avoid exporting the same ObjectName multiple times into a single MBeanServer.

## 9. Proxies and Bean Types: What to Watch Out For?

Spring can create proxies for \`@Transactional\`, \`@Async\`, AOP, or other features. When a bean is a proxy, the runtime class may differ from the original annotated class.

Spring's exporter/assembler mechanism handles many proxy cases, but you should not assume every proxy type, factory bean, or custom wrapper is recognized identically. If \`@ManagedResource\` is on the target class yet autodetection misses the bean:

1. Check whether the bean actually exists in ApplicationContext.
2. Check whether the exporter uses AnnotationJmxAttributeSource and an appropriate assembler.
3. Check the proxy type, target class, and accessible metadata.
4. Inspect exception logs during export, not just JConsole.
5. If needed, configure explicit managed bean registration instead of autodetection.

In projects with many AOP proxies, this is why you should integration-test several real beans and confirm the exposed metadata.

## 10. Differences Between Standard MBean Convention and @ManagedResource

**Standard MBean convention** relies on an interface named after the implementation class:

\`\`\`text
QueueMonitor -> QueueMonitorMBean
\`\`\`

Whereas the **annotation-driven JMX exporter** lets you select attributes/operations via Spring metadata:

\`\`\`java
@ManagedResource(objectName = "learning.jmx:type=Queue,name=Primary")
public class QueueMonitor {

    @ManagedAttribute
    public int getDepth() { return 0; }

    @ManagedOperation
    public void resetStats() { }
}
\`\`\`

In the annotation exporter model, the class does not have to implement \`QueueMonitorMBean\`. Spring's assembler can build the management interface/metadata to export the object according to the configured strategy.

This is also why \`AUTODETECT_MBEAN\` and \`AUTODETECT_ASSEMBLER\` must be distinguished: one mode relies on intrinsic MBean rules, while the other relies on an assembler capable of recognizing managed resources.

## 11. Autodetect and @ManagedResource Do Not Guarantee Access Control

After a bean is exported:

- A JMX client wanting access from another JVM needs an appropriate connection mechanism.
- Local JConsole/VisualVM still depends on process/attach permissions.
- A remote JMX connector depends on network, authentication, TLS, and policy.
- MBean operations can alter application state and must be protected.
- Annotated attributes or operations must not expose secrets or sensitive data.

Autodetection only decides **which objects are exposed**; it does not mean they should be externally accessible or safe for every caller.

Do not open up remote JMX just to test annotations. When remote administration is needed, use appropriate access policies and environments.

## 12. Export/Unexport Lifecycle

When MBeanExporter is a Spring infrastructure bean:

1. ApplicationContext initializes managed beans and the exporter.
2. The exporter autodetects eligible beans.
3. MBeans are registered into MBeanServer.
4. JMX clients can query registered MBeans if connected.
5. When the context closes and the exporter is destroyed, the exporter cleans up registrations within its managed scope.

The JVM's MBeanServer can outlive the Spring context. Therefore, when testing lifecycle, only check the application's own ObjectNames; do not assume every MBean in the platform server disappears after context.close().

### Duplicate ObjectName

If two contexts both export \`learning.jmx:type=Queue,name=Primary\` into one MBeanServer, the registration policy determines behavior. Do not use replace/ignore carelessly to mask two owners publishing the same name. Design a clear naming scheme and ownership model.

## 13. Common Errors and Diagnosis

| Symptom | Possible Cause | What to Check |
|---|---|---|
| \`@ManagedResource\` is present but MBean is missing | Exporter/autodetect not enabled or Spring bean not registered | Check \`@EnableMBeanExport\`, \`@Component\`/\`@Bean\`, context |
| Bean has annotations but assembler does not recognize it | Wrong assembler or autodetect mode used | Use \`AnnotationJmxAttributeSource\` with metadata assembler |
| MBean registered but ObjectName differs from expected | Different naming strategy or metadata | Check \`@ManagedResource.objectName\`, exporter strategy |
| \`InstanceAlreadyExistsException\` | Two beans/contexts share the same ObjectName | Determine ownership, change naming scheme, or clean up |
| Spring context fails at startup | JMX registration threw an exception | Read root cause in startup logs |
| JConsole does not show the MBean | Wrong JVM, wrong MBeanServer, permissions/connection | Use \`isRegistered\`, verify PID/connector |
| Attributes/operations do not appear | Missing \`@ManagedAttribute\`/\`@ManagedOperation\` or wrong assembler | Use \`getMBeanInfo\` to verify |
| Some beans are not autodetected | Bean outside context, proxy, lazy factory, scan scope | Verify runtime bean and exporter strategy |
| MBean remains after context.close() | Registered by another exporter/manually or context not stopped | Trace ObjectName and managing owner |
| Unexpected MBeans appear | AUTODETECT_ALL too broad or multiple exporters | Narrow autodetect mode/bean selection |

### Recommended Check Sequence

**Step 1:** Confirm the class has \`@ManagedResource\` and the bean is actually registered in Spring.

**Step 2:** Confirm \`MBeanExporter\` is created and running (via \`@EnableMBeanExport\`, XML, or Java config).

**Step 3:** If configuring the exporter manually, check the autodetect mode along with attribute source/assembler/naming strategy.

**Step 4:** Check logs during export for metadata mapping, ObjectName, or registration errors.

**Step 5:** Query \`MBeanServer.isRegistered(objectName)\` or \`queryNames(...)\` on the right server.

**Step 6:** Use \`getMBeanInfo\` to inspect actual attributes/operations. Only then investigate JConsole or remote JMX connection issues.

## 14. Real-World Scenarios

### Scenario A — Adding a New MBean

A developer adds \`@Component\` and \`@ManagedResource\` to \`CacheMonitor\`. The application already has \`@EnableMBeanExport\`. If the ObjectName is valid and unique, the new MBean can be detected and exported at context startup without adding a manual \`setBeans(...)\` entry.

### Scenario B — Annotated Class Outside the Context

A \`QueueInspector\` class has \`@ManagedResource\` but is created with \`new QueueInspector()\` outside Spring. It is not automatically autodetected by the context's exporter. You must create a Spring bean or register it explicitly if there is a specific reason.

### Scenario C — Spring Bean Missing Class Annotation

A bean only has \`@ManagedOperation\` on a method without being marked with \`@ManagedResource\`. Do not assume assembler autodetect will treat it as a managed resource. Use complete metadata or explicit registration.

### Scenario D — Multiple Contexts Colliding on ObjectName

Context A and Context B both find MBeans with the same ObjectName. The second context may fail due to duplicate registration or be handled according to policy. Fix by letting only one context export, or using ObjectNames with distinct namespaces if they are two independent instances.

### Scenario E — A Bean with Many Public Methods

A queue management bean has public methods \`pause\`, \`resume\`, \`removeAllJobs\`, and \`getDepth\`. Only annotate the operations that genuinely need exposure, avoiding turning the entire public business API into a JMX management surface.

## 15. Hands-On Exercises

### Exercise 1 — Enable Autodetection

Create \`@EnableMBeanExport\` and the two beans \`QueueMonitor\` and \`CacheMonitor\` from section 7. Run ApplicationContext and confirm both ObjectNames with \`MBeanServer.isRegistered\`.

Explain why calling \`setBeans\` for each object is unnecessary in this example.

### Exercise 2 — Test Bean Missing Annotation

Remove \`@ManagedResource\` from \`CacheMonitor\` and rerun. With configuration that only autodetects annotated resources, predict whether ObjectName \`learning.jmx:type=Cache,name=Products\` will still be registered. Check with JConsole and \`queryNames\`.

### Exercise 3 — Use Assembler Mode

Replace \`@EnableMBeanExport\` with \`ExplicitJmxConfig\` from section 5. Identify the individual roles of AnnotationJmxAttributeSource, MetadataMBeanInfoAssembler, MetadataNamingStrategy, and MBeanExporter. Explain the error that can happen if one component is omitted.

### Exercise 4 — Observe ObjectName Collision

Create two managed resources with the same \`@ManagedResource.objectName\` in the same MBeanServer. Predict the registration error. Then rename them with sensible domain/key properties and recheck.

### Exercise 5 — Distinguish Spring and JMX

Answer:

1. Does \`@ManagedResource\` create a Spring bean by itself?
2. Does \`@Component\` automatically export as a JMX MBean?
3. Does \`@ManagedOperation\` automatically allow any client to invoke a public method?
4. Is ObjectName an endpoint URL?
5. Does a registered MBean need a JMX connector for another JVM to access it?

**Suggested answers:** No; no; no; no; an appropriate JMX connection path is required to access it from another process.

## 16. Mental Model Summary

To **autodetect beans with \`@ManagedResource\`** in Spring Framework JMX, three conditions must be met:

1. The bean exists within the scope of the Spring ApplicationContext managed by the exporter.
2. JMX annotation metadata can be read and identifies an eligible managed resource.
3. The exporter is enabled and configured with an appropriate autodetect mode, assembler, naming strategy, and MBeanServer.

Do not infer from the presence of an annotation that the MBean has been registered. Verify with \`isRegistered\` and \`getMBeanInfo\`.

When using \`@EnableMBeanExport\`, Spring wires the standard components for you. When advanced customization is needed, configure \`MBeanExporter\` and metadata strategies explicitly to control exactly which beans are exported, what they expose, and under what ObjectName.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — EnableMBeanExport: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework API — AnnotationJmxAttributeSource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Spring Framework API — MetadataMBeanInfoAssembler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
