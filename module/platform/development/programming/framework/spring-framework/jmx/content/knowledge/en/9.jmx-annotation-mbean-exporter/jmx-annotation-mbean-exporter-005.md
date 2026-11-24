# Autodetection and How the Exporter Selects Beans to Expose

## Learning Objectives

After this lesson, you will understand how Spring Framework discovers beans marked with JMX metadata when using \`AnnotationMBeanExporter\`; distinguish **autodetection** from **manual export declaration**; understand the effects of \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, \`ObjectName\`, \`ApplicationContext\` scope, and exporter configuration; and know how to verify which beans actually appear in \`MBeanServer\` and why a bean might be skipped.

## 1. Context: A Spring Bean Is Not Automatically a JMX MBean

JMX (Java Management Extensions) enables monitoring and controlling Java objects at runtime via an \`MBeanServer\`. For a Spring bean to appear under a JMX name such as:

\`\`\`text
com.example.orders:type=OrderMetrics,name=primary
\`\`\`

a mechanism must register that bean into the JMX registry. Spring Framework provides \`MBeanExporter\` and \`AnnotationMBeanExporter\`. Both deal with exposing objects to JMX, but how they discover metadata differs.

- \`MBeanExporter\` can take a specific list of beans via \`setBeans(...)\`, paired with defined \`ObjectName\` values.
- \`AnnotationMBeanExporter\` handles annotations like \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\`, and can automatically locate beans carrying matching metadata within the Spring container.

**Autodetection does not mean every Spring bean is automatically published.** With the annotation strategy, a bean must satisfy the detection criteria to become a JMX candidate. Next, the exporter must resolve a name, build valid metadata, and register it successfully into the server.

An instance existing in the \`ApplicationContext\` that is not selected by the exporter continues to function normally in the application—it simply has no entry in the JMX registry.

## 2. What Does AnnotationMBeanExporter Do?

\`org.springframework.jmx.export.annotation.AnnotationMBeanExporter\` is a convenient exporter for using Spring JMX annotations. Conceptually, it combines:

1. The export capability of \`MBeanExporter\`: registering objects into \`MBeanServer\`.
2. An annotation metadata reader such as \`AnnotationJmxAttributeSource\`.
3. A mechanism to build \`ModelMBean\` info from annotations.
4. An \`ObjectName\` resolution mechanism via metadata/naming strategy.
5. An autodetection mechanism to find Spring beans annotated with \`@ManagedResource\`.

In an application, you can register the annotation exporter through appropriate configuration; Spring also provides \`@EnableMBeanExport\` and the XML \`<context:mbean-export/>\` element to enable annotation-based MBean export.

High-level model:

\`\`\`text
ApplicationContext
   |
   +-- orderService (no @ManagedResource)
   +-- orderMetrics (@ManagedResource)
   +-- cacheAdmin   (@ManagedResource)
   +-- internalHelper
   |
   v
AnnotationMBeanExporter
   |
   +-- scans Spring bean candidates via autodetection
   +-- reads @ManagedResource
   +-- reads @ManagedAttribute / @ManagedOperation
   +-- resolves ObjectName
   +-- builds appropriate management metadata
   |
   v
MBeanServer registry
   |
   +-- com.example.orders:type=OrderMetrics,name=primary
   +-- com.example.cache:type=CacheAdmin,name=primary
   |
   v
JConsole / VisualVM / JMX client
\`\`\`

Unselected beans still reside in the Spring container, but do not appear as JMX entries registered by this exporter.

## 3. The Most Important Requirement: @ManagedResource

In the Spring JMX annotation model, \`@ManagedResource\` is typically placed on the **class** to be exported:

\`\`\`java
package com.example.orders;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.orders:type=OrderMetrics,name=primary",
        description = "Runtime counters for order processing")
public class OrderMetrics {
    private final AtomicLong completed = new AtomicLong();

    public void recordCompleted() {
        completed.incrementAndGet();
    }

    @ManagedAttribute(description = "Completed order count")
    public long getCompletedCount() {
        return completed.get();
    }

    @ManagedOperation(description = "Reset counters")
    public void resetStatistics() {
        completed.set(0);
    }
}
\`\`\`

Here, \`@ManagedResource\` identifies the bean as a candidate with class-level management metadata. \`@ManagedAttribute\` and \`@ManagedOperation\` specify which methods are exposed as attributes/operations. The \`recordCompleted()\` method remains \`public\` but is not automatically exported when using the corresponding annotation metadata assembler.

Placing \`@ManagedOperation\` on a method of a class without class-level metadata is not enough to ensure the class is picked up by the exporter's autodetection mechanism. You must understand the candidate selection rules and how the exporter is configured.

## 4. Enabling Autodetection with @EnableMBeanExport

This is the common approach in Spring Framework applications using Java configuration:

\`\`\`java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {

    @Bean
    public OrderMetrics orderMetrics() {
        return new OrderMetrics();
    }

    @Bean
    public OrderService orderService(OrderMetrics metrics) {
        return new OrderService(metrics);
    }
}
\`\`\`

Example service using the same \`OrderMetrics\` bean:

\`\`\`java
package com.example.orders;

public class OrderService {
    private final OrderMetrics metrics;

    public OrderService(OrderMetrics metrics) {
        this.metrics = metrics;
    }

    public void completeOrder() {
        // Business processing would go here.
        metrics.recordCompleted();
    }
}
\`\`\`

\`@EnableMBeanExport\` enables support for exporting beans annotated with Spring JMX annotations. Depending on the Spring version and configuration, the exporter may locate an existing \`MBeanServer\` or use an explicitly provided one. In applications with multiple servers, explicitly choose the right server so management tools do not connect to a different server.

Example with explicit platform server setup and exporter configuration:

\`\`\`java
package com.example.orders;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "platformMBeanServer")
public class MonitoringJmxConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public OrderMetrics orderMetrics() {
        return new OrderMetrics();
    }
}
\`\`\`

The value \`server = "platformMBeanServer"\` references the bean name of the \`MBeanServer\` that annotation support will use. If the application already has an \`MBeanServer\` bean from another configuration, reuse that bean instead of creating a duplicate.

The deciding factor is that \`OrderMetrics\` has \`@ManagedResource\` and is registered in the \`ApplicationContext\`; \`OrderService\` lacks that annotation, so autodetection does not export it as a separate MBean just because it uses \`OrderMetrics\`.

## 5. How Does Autodetection Happen?

You can picture the pipeline when the exporter initializes:

1. Spring creates and configures the beans in the \`ApplicationContext\`.
2. The exporter receives access to the bean factory/context to look up candidates.
3. Autodetection evaluates beans matching the active detection strategy.
4. For annotation-driven export, \`@ManagedResource\` metadata is a primary signal for selecting a bean.
5. The exporter resolves an \`ObjectName\` for each candidate via \`objectName\` on the annotation or the appropriate naming strategy.
6. The assembler reads \`@ManagedAttribute\`, \`@ManagedOperation\`, and related metadata to build the management interface.
7. The exporter registers the MBeans in \`MBeanServer\` during startup lifecycle.
8. JMX clients query the registry by \`ObjectName\`.

The pipeline above is a logical model. Internal callback order, handling of lazy/proxy/\`FactoryBean\` beans, and failure points depend on the Spring version, exporter configuration, and actual bean factory.

If a bean is registered after autodetection completes, do not assume the exporter will automatically re-detect it. Use an appropriate manual registration API, lifecycle configuration, or initialize the exporter at the right time.

## 6. Bean Selection Rules by Autodetect Strategy

\`MBeanExporter\` supports autodetection strategies via constants such as \`AUTODETECT_NONE\`, \`AUTODETECT_MBEAN\`, \`AUTODETECT_ASSEMBLER\`, and \`AUTODETECT_ALL\`. General meaning:

| Strategy | Objects Evaluated | Purpose |
| --- | --- | --- |
| \`AUTODETECT_NONE\` | No automatic bean detection | Exports only explicitly specified beans |
| \`AUTODETECT_MBEAN\` | Beans conforming to standard JMX MBean interfaces | Detects Standard MBeans, MXBeans, or compliant MBeans |
| \`AUTODETECT_ASSEMBLER\` | Beans for which the assembler can provide management metadata | Detects based on metadata, such as annotations |
| \`AUTODETECT_ALL\` | Combines the above mechanisms | Detects both standard MBeans and assembler-recognized beans |

Specific constants and APIs must match the current Spring version; auto-built configurations may pick an appropriate strategy rather than requiring a manual \`setAutodetectMode\` call.

Key differences to remember:

- **MBean convention**: e.g., \`WorkerPool implements WorkerPoolMBean\`; JMX reads the standard interface.
- **Assembler-based**: e.g., \`@ManagedResource\` on \`WorkerPoolAdmin\`; Spring reads annotations to build metadata.
- **Explicit mapping**: e.g., \`setBeans(Map.of("domain:type=...", instance))\`; the bean is selected because the configuration names it explicitly, even if outside autodetection.

Do not conclude that \`@ManagedResource\` always makes a bean appear if the exporter is configured with \`AUTODETECT_NONE\` and has no explicit mapping. Likewise, do not conclude that every bean whose name ends with \`MBean\` is guaranteed to be exported: the class/interface must follow valid MBean rules and lie within the exporter's scan scope.

## 7. Example Comparing Bean Types

Suppose the context has the following beans:

\`\`\`java
@Bean
public OrderMetrics orderMetrics() {
    return new OrderMetrics(); // Class has @ManagedResource
}

@Bean
public PaymentService paymentService() {
    return new PaymentService(); // No JMX metadata
}

@Bean
public ThreadPoolMonitor threadPoolMonitor() {
    return new ThreadPoolMonitor(); // implements ThreadPoolMonitorMBean
}
\`\`\`

If the exporter is configured to autodetect via the annotation assembler, \`OrderMetrics\` is a clear candidate; \`PaymentService\` is not selected; \`ThreadPoolMonitor\` may not be selected if the policy only scans annotation metadata.

If the exporter supports both MBean convention autodetection and the assembler, both \`OrderMetrics\` and \`ThreadPoolMonitor\` may be registered. To know for sure, inspect the configured mode and actual metadata rather than relying on class names or successful dependency injection.

For business services that should not be exposed for management, the easiest approach to control is separating the **business service** from the **management adapter**: create a class marked with \`@ManagedResource\`, expose only the metrics/operations intended for operations, and inject the service into the adapter if needed.

## 8. How the Exporter Resolves ObjectName

After selecting a bean, the exporter must assign a unique \`ObjectName\`. For example:

\`\`\`java
@ManagedResource(
        objectName = "com.example.orders:type=OrderMetrics,name=primary")
public class OrderMetrics {
    // ...
}
\`\`\`

When a supported annotation naming strategy is used, \`objectName\` on \`@ManagedResource\` can supply the exact JMX name. Some naming strategy configurations support deriving a name if the annotation lacks \`objectName\`; check the details of the running Spring configuration.

Distinguish:

| Name | Example | Scope |
| --- | --- | --- |
| Spring bean name | \`orderMetrics\` | Retrieving the object from the bean factory |
| Class name | \`OrderMetrics\` | Java type |
| Annotation metadata | \`@ManagedResource(objectName=...)\` | Naming hint/declaration for a compatible exporter |
| JMX \`ObjectName\` | \`com.example.orders:type=OrderMetrics,name=primary\` | MBean identifier in the registry |

If two beans are assigned the same \`ObjectName\`, a duplicate registration error typically occurs by default unless the exporter has another conflict-handling policy configured. Do not use replace/ignore policies to mask unintended naming mistakes.

Pay particular attention when multiple application contexts share the platform \`MBeanServer\`, or when multiple Spring Boot/application context instances use the same domain and name within the same JVM.

## 9. @ManagedAttribute, @ManagedOperation, and Exposure Scope

\`@ManagedResource\` selects the managed object, while **which methods are exposed** is determined by method-level metadata and the corresponding assembler.

\`\`\`java
package com.example.cache;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.cache:type=CacheAdmin,name=primary")
public class CacheAdmin {
    private volatile boolean enabled = true;
    private int clearedEntries;

    @ManagedAttribute
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedAttribute
    public int getClearedEntries() {
        return clearedEntries;
    }

    @ManagedOperation(description = "Clear cached entries")
    public void clearCache() {
        if (!enabled) {
            throw new IllegalStateException("Cache maintenance disabled");
        }

        // Perform actual cache cleanup here.
        clearedEntries++;
    }

    public void internalRefresh() {
        // Public method but not annotated for JMX export.
    }
}
\`\`\`

In this annotation model, you expect to see the \`Enabled\` attribute (read/write), \`ClearedEntries\` (read-only), and the \`clearCache\` operation. The \`internalRefresh()\` method is not automatically exported by the annotation assembler when it lacks management metadata.

This is a crucial boundary: **autodetection selects the bean**, whereas **the metadata assembler selects the management members inside the bean**. The two decisions are not the same. Check both the registry and \`MBeanInfo\` to confirm the exact exposure scope.

## 10. Registering the Annotation Exporter Manually

Besides \`@EnableMBeanExport\`, you can declare \`AnnotationMBeanExporter\` directly if you want explicit control over parameters. For example:

\`\`\`java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class ManualAnnotationJmxConfig {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public AnnotationMBeanExporter annotationMBeanExporter(
            MBeanServer platformMBeanServer) {
        AnnotationMBeanExporter exporter = new AnnotationMBeanExporter();
        exporter.setServer(platformMBeanServer);
        return exporter;
    }

    @Bean
    public OrderMetrics orderMetrics() {
        return new OrderMetrics();
    }
}
\`\`\`

This is a plain Spring Framework explicit configuration example. If the application already uses \`@EnableMBeanExport\` or an auto-configuration mechanism creating an exporter, do not add a second exporter just to "be sure": that can cause the same bean to be registered twice under one \`ObjectName\`.

With the annotation exporter, class/method metadata is processed using the default support of \`AnnotationMBeanExporter\`. If a custom naming strategy, a different autodetect mode, or registration policy control is needed, configure the exporter according to the Spring API version in use. Do not infer that a setter exists in every version solely from a generic example; verify against the chosen version's API during implementation.

## 11. @EnableMBeanExport and Spring Boot: Configuration Scope

\`@EnableMBeanExport\` is a utility for enabling annotation-based MBean export in Spring Framework. In Spring Boot, the JMX mechanism and auto-export status can be controlled via configuration, such as the \`spring.jmx.enabled\` property depending on the Boot version.

Consequences to keep in mind:

- An \`MBeanExporter\` configured by Boot may already exist before you declare a manual exporter.
- Spring Boot Actuator may provide its own management endpoints/MBeans depending on dependencies and configuration; that does not imply every business bean is exported.
- Multiple exporters or multiple contexts can register duplicate \`ObjectName\` entries.
- An annotated bean may still not appear if the export mechanism is not enabled in the right context.

When the lesson focuses on Spring Framework, first clarify how the exporter is created. In a specific Boot application, inspect the version, \`spring.jmx.enabled\`, the exporter beans in the context, and the actual JMX output.

## 12. Verifying Exported Beans with JConsole and MBeanServer

The quickest approach is using JConsole:

1. Run the application and confirm the \`ApplicationContext\` has initialized.
2. Open \`jconsole\` and select the right JVM/PID.
3. Open the **MBeans** tab and find the domain and \`ObjectName\` from \`@ManagedResource\`.
4. Expand that MBean and inspect \`Attributes\` and \`Operations\`.
5. Cross-check the exported method list against the annotations on the class.
6. Verify that a bean **without management metadata** is not unintentionally exposed.

For automated checks, use the JMX API:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
        "com.example.orders:type=OrderMetrics,name=primary");

boolean exists = server.isRegistered(expected);
System.out.println("Registered: " + exists);

Set<ObjectName> registered = server.queryNames(
        new ObjectName("com.example.orders:*"), null);

for (ObjectName name : registered) {
    System.out.println(name.getCanonicalName());
}

if (exists) {
    MBeanInfo info = server.getMBeanInfo(expected);

    for (var attr : info.getAttributes()) {
        System.out.println("Attribute: " + attr.getName());
    }

    for (var operation : info.getOperations()) {
        System.out.println("Operation: " + operation.getName());
    }
}
\`\`\`

Note: \`ManagementFactory.getPlatformMBeanServer()\` inspects the server **inside the JVM executing the code**. If the code runs in another process, it reads a different registry. External clients must connect to the target JVM via a JMX connector or a tool like JConsole.

\`isRegistered(expected)=true\` confirms the name is in the registry, but to ensure the exporter did not expose unexpected methods, read \`MBeanInfo\` and compare attributes/operations.

## 13. Scenarios Where a Bean Is Not Autodetected

### 13.1. Class lacks @ManagedResource

\`@ManagedOperation\` on an individual method may not be enough for the Spring annotation exporter to pick up the whole bean. For annotation autodetection, annotate the class properly with \`@ManagedResource\`.

### 13.2. Bean is not in the ApplicationContext scanned by the exporter

If an object is created via \`new OrderMetrics()\` outside the Spring bean factory, an exporter scanning Spring beans will not know about it. Similarly, if the object is created in another context outside the exporter's scope, it may not be detected.

### 13.3. Exporter is not enabled or is disabled

A project with all the annotations but without \`@EnableMBeanExport\`, an appropriate exporter, or the equivalent Boot mechanism will not automatically export MBeans merely because annotations exist on classes.

### 13.4. Inappropriate autodetect mode

If configured with \`AUTODETECT_NONE\`, the exporter does not scan automatically. If only \`AUTODETECT_MBEAN\` is selected, a purely annotated bean may not be picked up; an assembler mode or the corresponding annotation exporter configuration is required.

### 13.5. Proxy, FactoryBean, or metadata on another type

Spring AOP proxies, \`FactoryBean\`, scoped proxies, and generated classes can cause the runtime class introspected by the exporter to differ from the class holding the annotations. When troubleshooting, verify the runtime bean type, annotation placement on types/interfaces, and how the exporter/assembler reads metadata in your Spring version.

### 13.6. Invalid or duplicate ObjectName

The exporter may have detected the bean, yet registration failed due to invalid \`ObjectName\` syntax or a pre-existing name. In that case the bean does not appear in the registry as expected, and startup logs usually contain the cause.

### 13.7. Wrong MBeanServer or wrong JVM

An application may have multiple servers or multiple instances; pointing JConsole at the wrong JVM can make you think autodetection failed. Verify PID, server object, and full \`ObjectName\` before changing configuration.

## 14. Autodetection and the Principle of Least Exposure

Because JMX permits invoking operations that can mutate application state, **selecting which beans to export** is an important operational decision.

A controllable approach usually follows these steps:

1. Separate management components from sensitive business services when necessary.
2. Place \`@ManagedResource\` only on management adapters with a clear purpose.
3. Place \`@ManagedAttribute\` or \`@ManagedOperation\` only on methods that truly need to be exposed.
4. Use a consistent naming convention for \`ObjectName\` to identify the module and instance.
5. Inspect metadata and the registry after startup; do not assume annotations alone suffice.
6. Protect remote JMX endpoints with authentication, access control, and network restrictions.
7. For operations with side effects, enforce state/business validation inside the implementation; annotations do not automatically create an authorization layer for operations.

Suppose \`OrderService\` has a \`cancelAllOrders()\` method; you should not expose all of \`OrderService\` over JMX for convenience. Instead, create \`OrderAdmin\` with only the controlled operational methods and clearly separated impact privileges.

## 15. Hands-On Exercises

**Exercise 1 — Discovery via annotations**

Create three beans: \`OrderMetrics\` with \`@ManagedResource\`, \`PaymentService\` with no annotations, and \`CacheAdmin\` with \`@ManagedResource\`. Enable \`@EnableMBeanExport\`. Use \`MBeanServer.queryNames\` to verify that only beans with appropriate management metadata are exported under annotation mode.

**Exercise 2 — Which methods are exposed?**

In \`CacheAdmin\`, add \`getCacheSize()\` with \`@ManagedAttribute\`, \`clearCache()\` with \`@ManagedOperation\`, and \`internalRebuild()\` with no annotation. Inspect \`MBeanInfo\` to confirm which methods were exported to JMX.

**Exercise 3 — Autodetect mode**

With an explicit \`MBeanExporter\` configuration, try \`AUTODETECT_NONE\` and an assembler-based detection strategy in turn, then compare the registered \`ObjectName\` values. Be sure to use the actual API of the Spring version in your project.

**Exercise 4 — Name collision**

Create two beans carrying \`@ManagedResource(objectName="com.example:type=Duplicate")\`. Observe the startup/exporter error and change them to two distinct \`ObjectName\` values. Explain why two MBeans cannot share the same full name in one \`MBeanServer\`.

**Exercise 5 — Bean outside scan scope**

Create an \`OrderMetrics\` instance via \`new\` without registering it as a Spring bean. Verify that the annotation exporter does not automatically discover this instance. Then declare a \`@Bean\` and re-check the registry.

## Conclusion

\`AnnotationMBeanExporter\` helps Spring Framework automatically locate managed beans with matching metadata, especially \`@ManagedResource\`, build attribute/operation info from the related annotations, and register them in \`MBeanServer\`. **Autodetection selects the object**, **the metadata assembler selects the exposed management API**, and **ObjectName defines the identity in the JMX registry**. Understanding these three boundaries prevents missing MBeans, duplicate name registrations, or unintentionally exposing internal application methods.
