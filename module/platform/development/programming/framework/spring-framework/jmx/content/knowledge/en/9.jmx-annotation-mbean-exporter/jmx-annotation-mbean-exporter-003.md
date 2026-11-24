# server and defaultDomain Properties of AnnotationMBeanExporter in Spring Framework JMX

## Objectives

When exporting Spring beans as JMX MBeans, two configurations that are easily confused are **server** and **defaultDomain**. Both appear in the exporter setup area, yet they solve two different problems:

- **server** decides **which MBeanServer** the MBeans are registered into.
- **defaultDomain** provides a **default domain for the exporter's ObjectName naming strategy** in cases where no domain is explicitly specified.

These are two independent axes: choosing the right MBeanServer does not automatically make the ObjectName right; changing the domain does not move an MBean to a different MBeanServer. In Spring applications with multiple contexts, servers, or exporters, distinguishing these two settings helps prevent MBean-not-found errors, name collisions, and lifecycle management difficulties.

This lesson focuses on annotation-based JMX export configuration in Spring Framework, typically via \`AnnotationMBeanExporter\` or the equivalent \`@EnableMBeanExport\` mechanism. The illustrative examples should be adapted to your Spring Framework version and how Spring Boot auto-configuration is enabled in the project.

After this lesson, you will be able to:

1. Explain how the exporter selects the target MBeanServer.
2. Understand the differences between \`server\`, the MBeanServer's default domain, and the exporter's \`defaultDomain\`.
3. Determine when \`defaultDomain\` takes effect and when an ObjectName is already explicitly declared.
4. Write intentional Spring Java and annotation configuration for one or multiple MBeanServers.
5. Diagnose cases where JConsole sees the wrong MBeans, ObjectNames collide, or the exporter registers to an unintended server.
6. Design clear namespaces and ownership across multiple Spring ApplicationContexts.

## 1. Three Objects, Three Responsibilities

Minimal model:

\`\`\`text
Spring bean
    |
    | @ManagedResource + @ManagedAttribute + @ManagedOperation
    v
AnnotationMBeanExporter
    |
    | server = specific MBeanServer
    | naming strategy + defaultDomain
    v
MBeanServer
    |
    | registry: ObjectName -> MBean
    v
JMX client (JConsole, script, monitoring)
\`\`\`

An MBean is always identified within **a specific MBeanServer** by **a specific ObjectName**. For example:

\`\`\`text
MBeanServer: platform server of JVM A
ObjectName:  com.example.inventory:type=CacheMetrics,name=ProductCache
\`\`\`

That same ObjectName can exist in another MBeanServer without colliding at the JMX registry level. Conversely, two beans registering the same ObjectName into **the same** server will collide, unless the author proactively configures an appropriate registration policy.

| Concept | Example | Meaning |
|---|---|---|
| MBeanServer | Platform server, container-created server, dedicated server | Registry holding MBean registrations |
| ObjectName domain | \`com.example.inventory\` | Logical namespace within the registry |
| ObjectName key properties | \`type=CacheMetrics,name=ProductCache\` | Distinguishes instances within the same domain |
| \`server\` on exporter | Injected \`MBeanServer\` bean | The MBeanServer used by the exporter |
| \`defaultDomain\` on exporter | \`com.example.inventory\` | Fallback domain used by the naming strategy when needed |

Remember that **a full ObjectName consists of the domain and the key property list**. Changing \`defaultDomain\` does not automatically change \`type\`, \`name\`, or \`instance\`.

## 2. The server Property: Where Are MBeans Registered?

\`AnnotationMBeanExporter\` is a Spring JMX mechanism that finds beans with management metadata and exports them to an \`MBeanServer\`. It inherits registration management capabilities from Spring's exporter infrastructure.

Conceptually, the \`server\` configuration is a reference to an object implementing \`javax.management.MBeanServer\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxServerConfig {

    @Bean
    public MBeanServer applicationMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

When the exporter is configured to use this bean, every MBean managed by the exporter is registered in the **current JVM's platform MBeanServer**. The platform server also contains JVM management MXBeans such as memory, threads, and class loading. Thus, application MBeans and platform MBeans are visible in the same registry.

Setting \`server\` to a dedicated server changes the registration target for that exporter:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DedicatedJmxServerConfig {

    @Bean(destroyMethod = "")
    public MBeanServer dedicatedMBeanServer() {
        return MBeanServerFactory.createMBeanServer("com.example.private");
    }
}
\`\`\`

This example only illustrates creating a dedicated server. When using a dedicated server in a real system, the owning component must manage registrations, connectors, shutdown, and \`MBeanServerFactory.releaseMBeanServer(server)\` if the server was created by the factory and is being tracked by it. \`destroyMethod = ""\` does not perform that cleanup; it merely prevents Spring from inferring an automatic destroy method for the bean reference. Do not create a separate server just to change the namespace: a single platform server can contain many domains.

### 2.1 server is not a network address

The \`server\` value here is an **MBeanServer object**, not a JMX URL, hostname, or port. Remote access is the responsibility of JMX connectors and security configuration.

\`\`\`text
Exporter ───── register ─────> MBeanServer
                                  ^
                                  |
                       JMXConnectorServer
                                  ^
                                  |
                              Remote client
\`\`\`

A server can exist and hold MBeans even when no remote connector is running. Conversely, a remote client connecting to a connector attached to **a different server** will not see the newly exported MBeans even though registration succeeded.

### 2.2 Let Spring auto-detect the server or specify it explicitly?

Spring's exporter mechanism can locate an MBeanServer using a default strategy if no specific server is provided. However, the runtime/container choice, classpath, configuration, and number of existing servers can make behavior unpredictable if you do not understand the setup. For applications with clear operational requirements, explicitly providing the chosen \`MBeanServer\` reduces ambiguity.

If the application genuinely uses only one platform server, a simple and consistent configuration is usually appropriate. If the application runs in a container or shares a JVM with multiple products, identify the server that the connector and monitoring system will access before exporting.

## 3. defaultDomain: Naming Within the Same Server

A JMX \`ObjectName\` has the form:

\`\`\`text
<domain>:<key1>=<value1>,<key2>=<value2>,...
\`\`\`

Example:

\`\`\`text
com.example.orders:type=Queue,name=Pending
\`\`\`

In this example:

- The domain is \`com.example.orders\`.
- The key properties are \`type=Queue,name=Pending\`.
- The entire string is the \`ObjectName\`.

The exporter's \`defaultDomain\` is typically used by a naming strategy, such as \`MetadataNamingStrategy\`, to choose the domain when metadata does not provide an explicit ObjectName/domain. This is **not equivalent** to changing the server, the server's own internal default domain, or an explicitly defined full ObjectName.

Visualization:

\`\`\`text
Exporter A
  server = platformMBeanServer
  defaultDomain = "com.example.orders"
      |
      +-- Bean QueueStats --> com.example.orders:name=queueStats,type=...
      +-- Bean WorkerStats --> com.example.orders:name=workerStats,type=...

Exporter B
  server = platformMBeanServer
  defaultDomain = "com.example.billing"
      |
      +-- Bean InvoiceStats --> com.example.billing:name=invoiceStats,type=...
\`\`\`

Two exporters use **the same server** but have different domains. When named appropriately, they do not collide.

Conversely:

\`\`\`text
Exporter A -> server X -> com.example.orders:type=Queue,name=Main
Exporter B -> server Y -> com.example.orders:type=Queue,name=Main
\`\`\`

Here the two registrations do not collide because they are on different servers, even though the ObjectName is identical. Clients must still connect to the right server to see the target object.

### 3.1 defaultDomain does not override an explicit ObjectName

Consider the bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.explicit:type=Cache,name=ProductCache",
    description = "Metrics for product cache"
)
public class ProductCacheMetrics {
}
\`\`\`

If the exporter uses \`defaultDomain = "com.example.fallback"\`, the bean still requests \`com.example.explicit:type=Cache,name=ProductCache\` according to its explicit metadata. Changing \`defaultDomain\` is not a way to rename beans that already specify a full ObjectName.

Design principle: MBeans that need a stable ObjectName for external monitoring can declare their full name explicitly; \`defaultDomain\` is useful when you want to unify naming for beans whose names are generated by the naming strategy.

## 4. Three Domains That Can Easily Be Confused

Distinguish between:

1. **Domain in a specific ObjectName**: \`com.example.app\` in \`com.example.app:type=Pool,name=Primary\`.
2. **Default domain of the MBeanServer**: the value determined by the server implementation or used in corresponding JMX ObjectName/domain cases.
3. **defaultDomain of the Spring exporter/naming strategy**: an application-level configuration for how names are generated.

A dedicated server can be created with a default domain:

\`\`\`java
MBeanServer server =
    MBeanServerFactory.createMBeanServer("com.example.serverDefault");
\`\`\`

Afterward, the Spring exporter can still configure its naming strategy with \`defaultDomain="com.example.application"\`. These two values do not necessarily match.

\`server.getDefaultDomain()\` returns the default domain reported by the server; it **does not prove** that every MBean in the server belongs to that domain. One registry can hold dozens of different domains.

Example:

\`\`\`java
System.out.println(server.getDefaultDomain());
System.out.println(server.getDomains().length);
\`\`\`

\`getDomains()\` reports the domains that currently have registered MBeans, whereas \`getDefaultDomain()\` reports the server's default domain. When looking for a "missing" Spring MBean, query by **the exact ObjectName** or \`queryNames\` with the appropriate domain/keys.

## 5. Configuring AnnotationMBeanExporter

Depending on how the application is configured, you can use \`AnnotationMBeanExporter\` directly or let \`@EnableMBeanExport\` create the exporter. The two examples below illustrate configuration intent; choose one primary export approach per scope to avoid duplicate registrations.

### 5.1 Declaring AnnotationMBeanExporter directly

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class DirectExporterConfiguration {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public AnnotationMBeanExporter annotationMBeanExporter(
            MBeanServer jmxServer) {
        AnnotationMBeanExporter exporter = new AnnotationMBeanExporter();
        exporter.setServer(jmxServer);
        exporter.setDefaultDomain("com.example.application");
        return exporter;
    }
}
\`\`\`

In a real project, avoid both declaring an exporter directly and letting another automatic exporter register the same MBeans. Exact class names, instantiation, and lifecycle hooks depend on the Spring Framework version; check the API in use when upgrading.

Annotated bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    description = "Worker state and control operations"
)
public class ImportWorkerAdmin {

    private volatile boolean paused;

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Request pausing new work")
    public void pause() {
        paused = true;
    }
}
\`\`\`

The metadata does not specify an explicit \`objectName\`. The exporter's naming strategy will generate a name according to the configured rules; \`defaultDomain\` adjusts the fallback domain. The exact key property structure of the generated name depends on the active naming strategy, so when clients or alert rules need a fixed ObjectName, inspect the actual name in the registry and manage the naming contract explicitly.

### 5.2 Using @EnableMBeanExport

Spring provides an annotation to enable exporting MBeans that carry metadata:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(
    defaultDomain = "com.example.application",
    server = "jmxServer"
)
public class AnnotationDrivenJmxConfiguration {
}
\`\`\`

This references the bean named \`jmxServer\` if declared in the context. Server bean example:

\`\`\`java
@Bean
public MBeanServer jmxServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

The \`server\` value in \`@EnableMBeanExport\` is the **MBeanServer bean name in the Spring context** per the annotation contract, whereas \`setServer\` on the exporter takes an **MBeanServer object**. This distinction is important: do not put \`host:port\` into the annotation's \`server\` attribute.

When using Spring Boot, JMX export can be controlled by Boot configuration. Standardize on one declaration mechanism so you do not create duplicate exporters. Do not infer that \`@EnableMBeanExport\` automatically enables a remote JMX connector.

## 6. Combined Example: Two Domains, Same Platform MBeanServer

Suppose an application has two groups of MBeans:

- \`InventoryMetrics\`: reports the number of items waiting to sync.
- \`BillingMetrics\`: reports invoice statistics.

Both can be registered in the platform server:

\`\`\`text
platform MBeanServer
  ├── com.example.inventory:type=Metrics,name=SyncQueue
  └── com.example.billing:type=Metrics,name=InvoiceQueue
\`\`\`

To guarantee exact names, specify explicit ObjectNames in the annotation:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.inventory:type=Metrics,name=SyncQueue")
class InventoryMetrics {
    @ManagedAttribute
    public long getPendingCount() {
        return 0L;
    }
}

@Component
@ManagedResource(
    objectName = "com.example.billing:type=Metrics,name=InvoiceQueue")
class BillingMetrics {
    @ManagedAttribute
    public long getPendingCount() {
        return 0L;
    }
}
\`\`\`

In this case, \`defaultDomain\` does not need to participate in naming the two MBeans because they already declare full ObjectNames. The exporter configuration still needs to point to the server that monitoring will access.

If you omit explicit \`objectName\` values and want each group to have its own default domain, you must configure the exporters and the bean scopes they are responsible for so that they do not scan/export the same beans twice. Merely creating two exporters with different \`defaultDomain\` values that both scan the entire context does not automatically partition MBeans into groups.

## 7. Multiple MBeanServers in One JVM

Multi-server model:

\`\`\`text
                   Spring ApplicationContext
                             |
                   +---------+---------+
                   |                   |
             Exporter A           Exporter B
             server = X           server = Y
             domain = app         domain = internal
                   |                   |
              Server X             Server Y
                   |                   |
              Connector X          Connector Y
\`\`\`

Decisions that must be clear:

- Which server holds JVM/runtime MBeans and which holds application MBeans?
- Are two connectors needed, or only local access?
- Which connector does the monitoring client use?
- Who owns the lifecycle of a dedicated server?
- Do the two exporters scan the same beans?
- Are different security policies applied to each connector?

Each MBeanServer has its own registry. Two servers do not automatically synchronize MBeans. If you registered an MBean into server X, changing \`defaultDomain\` on exporter Y does not make the MBean "appear" in server Y. To move it, you must change the registration target following lifecycle procedures.

### 7.1 Using a dedicated server does not equate to automatic security

Separating servers can be useful for management structure and export scoping, but it does not automatically guarantee authorization. Connector permissions, local access capabilities, JVM boundaries, authentication, TLS, and per-operation policies must still be controlled. A remote connector pointing to the wrong server can expose internal MBeans or prevent monitoring from seeing the expected data.

## 8. Registration Policy and Name Collisions

Within the same MBeanServer, an \`ObjectName\` must be unique. If an exporter attempts to register a name that already exists, \`InstanceAlreadyExistsException\` or behavior according to the configured registration policy may occur.

Example:

\`\`\`text
Exporter A → platform server
   com.example.app:type=Worker,name=Main

Exporter B → platform server
   com.example.app:type=Worker,name=Main
\`\`\`

Even if exporter B has \`defaultDomain="com.example.other"\`, if bean B's annotation still explicitly declares the ObjectName \`com.example.app:type=Worker,name=Main\`, a collision still occurs. Changing \`defaultDomain\` does not fix this issue.

Situations to consider:

| Situation | Resolution |
|---|---|
| Two contexts export the same name to the same server | Define ownership and namespace by context/instance |
| One bean is scanned by two exporters | Narrow export scope or consolidate into one exporter |
| A bean has a wrong explicit ObjectName | Fix the metadata and clients depending on the name |
| An old context has not unregistered its MBean | Fix lifecycle cleanup; do not delete unowned MBeans |
| Two different servers have the same ObjectName | No registry collision, but the right connector must be selected |

A policy that replaces existing MBeans can impact other components; use it only when ownership and replacement timing are clearly designed.

## 9. Diagnostics: MBean Not Visible in JConsole

Suppose the application logs that the exporter registered successfully, but JConsole does not show \`com.example.application:type=Worker,...\`.

Check in order:

1. **Confirm the right JVM**: which application process is JConsole connecting to?
2. **Confirm the right MBeanServer**: is the exporter using the platform server or a dedicated server? Does the connector point to that exact server?
3. **Check the actual ObjectName**: does the bean have \`@ManagedResource(objectName=...)\`? Is \`defaultDomain\` used by the naming strategy?
4. **Check if the exporter is active**: does the context enable JMX annotation export? Are the right beans scanned?
5. **Check registration errors**: are there collisions, malformed ObjectNames, or initialization exceptions?
6. **Check lifecycle**: has the context/exporter been shut down or has the MBean already been unregistered?

An API check:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer platform = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> applicationNames = platform.queryNames(
    new ObjectName("com.example.application:*"),
    null
);
applicationNames.forEach(System.out::println);
\`\`\`

If \`applicationNames\` is empty, that only proves there is no matching ObjectName in the **queried platform server** at the moment of reading. The exporter may have registered it in a different server or a different domain. Try querying the exact server used by the exporter and printing the actual ObjectNames, instead of rushing to conclude the bean was not exported.

### 9.1 What does MBeanInfo help determine?

Once the MBean is found, \`server.getMBeanInfo(name)\` reveals attributes, operations, and notification metadata. It helps verify the exported interface content, but does not directly explain why \`defaultDomain\` chose a particular name. To understand naming, inspect the annotation/strategy and exporter configuration.

## 10. Verifying Configuration with a Small Test

An integration test should initialize a Spring context with the right exporter and bean, then inspect the registry:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JmxExporterConfigurationTest {

    @Test
    void mbeanAppearsInSelectedServer() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.inventory:type=Metrics,name=SyncQueue");

        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     DirectExporterConfiguration.class,
                     InventoryMetrics.class)) {

            assertTrue(server.isRegistered(name));
            assertNotNull(server.getMBeanInfo(name));
        }

        assertFalse(server.isRegistered(name));
    }
}
\`\`\`

For this example to run in a specific project, ensure the exporter points to the platform server, the bean has the right annotations and ObjectName, and no parallel test or other registration uses the same name. If the test uses a different exporter configuration with a different scanning/registration lifecycle, adjust the fixture accordingly. Do not have a test delete arbitrary MBeans by name to "clean the environment" because those might belong to another test.

For \`defaultDomain\`, you can create a bean without specifying a full ObjectName and inspect the actual domain chosen by the naming strategy. Assert against the configured naming strategy's contract rather than assuming a single key property pattern is identical across all versions.

## 11. Lifecycle and Ownership

A Spring-managed exporter typically cleans up the MBeans it registered when the exporter is destroyed. However, a **shared MBeanServer** can outlive the context:

\`\`\`text
JVM creates platform MBeanServer
     |
Spring Context A creates exporter
     |  registers com.example.a:...
     |
Spring Context B creates exporter
     |  registers com.example.b:...
     |
Context A closes
     |  unregisters MBeans managed by A
     |
Platform server stays alive
     |  MBeans managed by B remain present
\`\`\`

If a bean is registered manually outside the exporter, the registering code itself must manage cleanup. Do not release the platform server just because one context closes. If using a factory-created server, identify the owning component and manage releasing it after cleaning up connectors/registrations properly.

Changing \`server\` in configuration at runtime should not be viewed as an automatic MBean migration operation. If you need to switch registries, design a controlled shutdown of the old exporter and re-registration via the new exporter. Changing \`defaultDomain\` can also alter the generated ObjectName on the next registration, causing old alerts/scripts to miss the MBean; treat this as a management contract change.

## 12. Common Configuration Mistakes

### 12.1 Putting a URL into server of @EnableMBeanExport

Semantically incorrect:

\`\`\`java
@EnableMBeanExport(server = "service.example.com:9999")
\`\`\`

The annotation's \`server\` value is the **Spring bean name** referencing an \`MBeanServer\`, not a connector address. Define an \`MBeanServer\` bean and use its exact bean name.

### 12.2 Changing defaultDomain and expecting the MBean to appear on another server

The domain only resolves the ObjectName namespace. If the client connects to server Y while the exporter registers into X, changing \`defaultDomain\` will not make the MBean visible on Y.

### 12.3 Letting two exporters scan the same set of beans

If two exporters detect and register the same bean with the same ObjectName into the same server, a collision can occur. Giving each exporter a different bean name in the Spring context does not guarantee distinct JMX namespaces.

### 12.4 Assuming annotation objectName gets rewritten

A full ObjectName from \`@ManagedResource\` is the bean's specific naming choice. \`defaultDomain\` is not a tool for overriding all annotations.

### 12.5 Confusing the server's default domain with the exporter's defaultDomain

\`server.getDefaultDomain()\` is MBeanServer metadata. \`exporter.setDefaultDomain(...)\` affects how the exporter/naming strategy generates names per configuration. Both can hold different values.

### 12.6 Forgetting to check Spring Boot JMX auto-configuration

In Spring Boot, JMX export configuration is influenced by Boot settings and auto-configuration. When adding \`@EnableMBeanExport\` or a manual exporter, check whether another mechanism has already enabled the same functionality. "Duplicate MBean" errors often stem from duplicate export and lifecycle issues rather than \`server\`/\`defaultDomain\` themselves.

## 13. Operational Design Guidelines

For each MBean group, document:

- **Registry**: which server receives registrations? Who owns the server? Is it shared?
- **Namespace**: which domain and key properties? Explicit ObjectName or generated by naming strategy?
- **Exporter**: which exporter is responsible for registration and unregistration? Is there duplicate scanning?
- **Client**: which server do JConsole/monitoring connect to? Are MBean names used in dashboards stable?
- **Security**: does the connector have appropriate authentication, encryption, and authorization?
- **Lifecycle**: after a context restart, can the MBean be re-registered with the same name without collision?
- **Change management**: will changing \`defaultDomain\` break scripts/alerts depending on ObjectNames?

Sample configuration documentation:

\`\`\`text
JMX server: JVM platform MBeanServer
Exporter: AnnotationMBeanExporter of the main application context
Default domain: com.example.inventory
Special ObjectNames:
  com.example.inventory:type=Cache,name=Catalog
  com.example.inventory:type=Queue,name=ImportJobs
Remote connector: configured separately in management infrastructure
Ownership: Spring context manages exporter registrations
\`\`\`

When deploying across multiple environments, avoid putting secrets, user IDs, or sensitive payloads into ObjectNames. The domain should signify a module or application, not a place for continuously changing runtime information.

## 14. Reinforcement Exercises

**Exercise 1.** An exporter uses the platform server and \`defaultDomain="com.example.alpha"\`. Bean A has \`@ManagedResource(objectName="com.example.explicit:type=Cache,name=A")\`. Which domain does bean A belong to when registered? **Answer:** \`com.example.explicit\`, because the ObjectName is already explicit.

**Exercise 2.** Exporter X uses server X and exporter Y uses server Y, yet both register \`com.example:type=Worker,name=Main\`. Is there a JMX registry collision? **Answer:** no, because ObjectName uniqueness is only required within each server. Clients must choose the right server.

**Exercise 3.** Two exporters both use the platform server and register the same ObjectName. Will changing \`defaultDomain\` of one exporter to \`com.example.other\` reliably fix the error? **Answer:** no; if the name is written explicitly, \`defaultDomain\` has no effect. You must fix ownership/namespace or export scope.

**Exercise 4.** JConsole connects to the right JVM but does not see the MBean. List three things to check first: **the exporter's target server**, **which server the connector is connected to**, and **which registry the actual ObjectName appears in**.

**Exercise 5.** Write a Spring configuration using an \`MBeanServer\` bean named \`applicationServer\`, then reference it via \`@EnableMBeanExport(server = "applicationServer", defaultDomain = "com.example.ops")\`. Explain why \`"applicationServer"\` is a bean name rather than a host.

## Summary

In Spring Framework JMX, an exporter's \`server\` and \`defaultDomain\` have two independent responsibilities. **server selects the JMX registry where MBeans are registered**; **defaultDomain adjusts the default domain when the naming strategy needs to generate an ObjectName**. Neither setting automatically substitutes for the other. With AnnotationMBeanExporter, good design starts by identifying the target MBeanServer, choosing stable ObjectNames, assigning registration ownership to an exporter, and checking the actual registry after startup/shutdown. This keeps management observable, avoids name collisions, and maintains the contract with JMX clients across application upgrades.
