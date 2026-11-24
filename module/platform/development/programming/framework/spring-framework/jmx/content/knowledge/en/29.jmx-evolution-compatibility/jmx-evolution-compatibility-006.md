# Migrating from MBean Interfaces to Annotation Metadata in Spring Framework JMX

## Learning Objectives

This lesson belongs to the **Evolution and Compatibility** group of Spring Framework JMX. In long-running Java systems, many MBeans are written using the Standard MBean convention: a class `CacheManager` implements `CacheManagerMBean`. When a project moves to Spring annotation-based JMX, teams may want to use `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, and `@ManagedOperationParameter` to describe the management API directly on the Java bean.

After completing this lesson, you will be able to:

- Distinguish Standard MBean interfaces, Spring annotation metadata, and ModelMBeans built by Spring.
- Map getters/setters/operations on an interface to management annotations for migration.
- Configure `MBeanExporter`, `MetadataMBeanInfoAssembler`, `AnnotationJmxAttributeSource`, or `@EnableMBeanExport`.
- Preserve `ObjectName`, attribute names, operation signatures, and behaviors depended upon by clients.
- Understand compatibility for JConsole, remote JMX clients, local MBean proxies, and external automation.
- Design a step-by-step migration avoiding registering two MBeans with duplicate `ObjectName`.
- Test compatibility via `MBeanInfo`, runtime state, actual invocations, and lifecycle.

## 1. Two Different MBean Exposure Mechanisms

### 1.1. Standard MBean Interface

Standard JMX specifies that a class such as `CacheManager` can provide a management interface `CacheManagerMBean`. For example:

\`\`\`java
package com.example.cache;

public interface CacheManagerMBean {
    int getEntryCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void clearStatistics();
}
\`\`\`

Implementation:

\`\`\`java
package com.example.cache;

public class CacheManager implements CacheManagerMBean {

    private volatile boolean enabled = true;

    @Override
    public int getEntryCount() {
        return 42;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void clearStatistics() {
        // Clear internal statistics.
    }
}
\`\`\`

JMX recognizes the Standard MBean interface by convention, builds metadata from method signatures, and exposes:

- Attribute `EntryCount`, type `int`, readable.
- Attribute `Enabled`, type `boolean`, readable and writable.
- Operation `clearStatistics()`.

In this approach, **the interface is the explicit management contract**. Changing the interface changes the exposed JMX surface.

### 1.2. Spring Annotation Metadata

Spring Framework JMX provides annotations to describe managed resources and the methods to be exposed:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
\`\`\`

A class does not have to implement `*MBean`, yet can still be adapted and exported by Spring via ModelMBean based on metadata. These annotations are not JDK Standard MBean JMX rules; they are read by the Spring JMX infrastructure when building management metadata.

Example converted to annotations:

\`\`\`java
package com.example.cache;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.cache:type=CacheManager,name=primary",
    description = "Cache management")
public class CacheManager {

    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Number of cached entries")
    public int getEntryCount() {
        return 42;
    }

    @ManagedAttribute(description = "Whether caching is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Enable or disable cache")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(description = "Clear cache statistics")
    public void clearStatistics() {
        // ...
    }
}
\`\`\`

The syntax differs, but the migration goal is preserving the **management contract** already used by clients. Do not just look at Java method names; verify final JMX metadata, how Spring classifies getters/setters, invocation behavior, and whether unintended elements are exposed.

## 2. What Changes When Dropping the *MBean Interface?

| Aspect | Standard MBean interface | Spring annotation metadata |
| --- | --- | --- |
| Contract definition source | Interface `ClassNameMBean` | `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` |
| How management methods are identified | Methods declared on the interface | Methods selected by annotations/assembler |
| Who builds metadata | Server JMX introspection | Spring metadata assembler and ModelMBean adapter |
| Spring JMX annotation dependency | Not required | Required |
| MBean class/descriptor metadata | Standard MBean | Typically ModelMBean or Spring-created adapter |
| Adding detailed descriptions | Limited under default metadata | Detailed annotation metadata supported |
| Java management interface on client | Can share the same `*MBean` interface | May need to keep client interface or use `MBeanServerConnection` |
| Ability to keep equivalent contract | Yes, if unchanged | Yes, but must verify metadata and behavior |
| Risk of accidental API expansion | Adding methods to interface | Incorrect annotations/assembler/autodetection |
| Risk of naming change | Name supplied by exporter/server | `@ManagedResource.objectName` and naming strategy must align |

There is no rule that “annotation mode is always 100% compatible” simply because Java methods share the same names. ModelMBean and Standard MBean metadata may differ in class name, descriptors, or operation/getter representations. A JMX client relying only on standard attributes and operations usually keeps working if the contract is preserved; clients inspecting metadata deeply may need adjustments.

## 3. Inventory the JMX Contract Before Migrating

Before changing code, list the information clients actually rely on.

Example:

\`\`\`text
ObjectName:
  com.example.cache:type=CacheManager,name=primary

Attributes:
  EntryCount  int      readable=true,  writable=false
  Enabled     boolean  readable=true,  writable=true

Operations:
  clearStatistics() -> void

Notifications:
  none

Clients:
  JConsole
  custom JMX tooling
  monitoring jobs
\`\`\`

Distinguish compatibility dimensions:

1. **Registration name:** `ObjectName` domain and key properties.
2. **Attribute names:** casing, JavaBean getter mapping.
3. **Data types:** primitive/wrapper, Open Types if using MXBean.
4. **Methods:** operation names, parameter counts/types, return types, and behavior.
5. **Read/write access:** `isReadable`, `isWritable`.
6. **Non-core metadata:** descriptions, descriptor fields, and class name if used by clients.
7. **Notifications:** types, sequence, source, userData if present.
8. **Lifecycle:** registration/unregistration inside `ApplicationContext`.
9. **Security:** execution permissions and surface of operations with side effects.
10. **Client assumptions:** do tools depend on a specific Java interface or only standard JMX APIs?

The goal is **before/after comparison**, not swapping the interface and hoping dashboards stay unaffected.

## 4. Inspect MBeanInfo Before Switching

`MBeanInfo` is the foundational data for verifying the management contract published in the JMX registry.

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxContractInspector {

    public static void inspect(
            MBeanServer server,
            ObjectName name) throws Exception {

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                    "MBean not registered: " + name);
        }

        MBeanInfo info = server.getMBeanInfo(name);

        System.out.println("MBean class: " + info.getClassName());

        for (var attribute : info.getAttributes()) {
            System.out.printf(
                    "ATTR %s type=%s read=%s write=%s%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable());
        }

        for (var operation : info.getOperations()) {
            System.out.printf(
                    "OP %s returnType=%s%n",
                    operation.getName(),
                    operation.getReturnType());

            for (var parameter : operation.getSignature()) {
                System.out.printf(
                        "  PARAM %s type=%s%n",
                        parameter.getName(),
                        parameter.getType());
            }
        }
    }
}
\`\`\`

Invocation:

\`\`\`java
JmxContractInspector.inspect(
        server,
        new ObjectName(
                "com.example.cache:type=CacheManager,name=primary"));
\`\`\`

Run the inspector against the old version and save a controlled snapshot. After migration, run it again on the corresponding server and compare. In CI, normalize the attributes/operations lists rather than comparing the full `toString()` of descriptors, as some non-contract metadata may differ when moving from Standard MBean to ModelMBean.

**Do not read MBeanInfo from the platform server if the exporter actually uses a custom server.** Obtain the exact `MBeanServer` bound to the exporter or connector.

## 5. Migration Step 1 — Preserve Class Behavior

Before changing the export mechanism, avoid modifying business behavior, method names, and management data at the same time. For example:

\`\`\`java
public int getEntryCount() { ... }

public boolean isEnabled() { ... }

public void setEnabled(boolean enabled) { ... }

public void clearStatistics() { ... }
\`\`\`

To keep clients compatible, these methods must keep their original signatures and semantics. Renaming `clearStatistics()` to `resetMetrics()` will break JMX automation calling `clearStatistics`.

One incremental migration technique is **keeping the `CacheManagerMBean` interface in code even after Spring annotations are added**. This allows old Java clients to continue compiling, though you must control the export path: if the implementation is still a Standard MBean, `MBeanExporter` may detect and export it as a standard interface instead of using annotation metadata as intended. To genuinely validate the annotation-based ModelMBean, confirm how the exporter chooses the registration path in your Spring version.

Do not force removing the interface in the first wave. Establish compatibility tests first, then consider Java API changes.

## 6. Migration Step 2 — Add @ManagedResource and Method Metadata

Example new class no longer implementing the MBean interface:

\`\`\`java
package com.example.cache;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.cache:type=CacheManager,name=primary",
    description = "Primary cache manager")
public class CacheManager {

    private final AtomicInteger entryCount = new AtomicInteger();
    private volatile boolean enabled = true;

    public void addEntry() {
        entryCount.incrementAndGet();
    }

    @ManagedAttribute(
        description = "Current number of cached entries")
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedAttribute(
        description = "Whether cache use is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(
        description = "Enable or disable caching")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(
        description = "Reset cache statistics")
    public void clearStatistics() {
        entryCount.set(0);
    }
}
\`\`\`

Here `addEntry()` is a business method not annotated for export. When using an annotation-based metadata assembler, only validly configured methods are exposed under that mechanism.

**Point to note:** a getter/setter may be represented as an attribute, and ModelMBean metadata may contain operations supporting those accessors. When comparing, distinguish “intended invocable business operations” from getter/setter metadata used by the assembler to back attributes.

If the project has similarly named or overloaded methods, do not infer compatibility from names alone. Inspect the JMX signatures after export.

## 7. Migration Step 3 — Configure @EnableMBeanExport

With Spring Java Config:

\`\`\`java
package com.example.cache;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "platformMBeanServer")
public class CacheJmxConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public CacheManager cacheManager() {
        return new CacheManager();
    }
}
\`\`\`

`@EnableMBeanExport` activates annotation-based JMX exporting. It coordinates the metadata and naming mechanisms required so Spring beans annotated with `@ManagedResource` are exported.

Key points:

- `@ManagedResource` **does not create a Spring bean automatically**. The class must be registered in `ApplicationContext` via `@Bean`, `@Component`, or component scanning.
- `@EnableMBeanExport(server="platformMBeanServer")` selects an `MBeanServer` bean by name; ensure that bean name actually exists in the context.
- `@ManagedResource.objectName` can participate in annotation-based naming strategies.
- Do not enable a second `MBeanExporter` registering the same exported `ObjectName`.

In Spring Boot, JMX auto-configuration may already create an exporter depending on version/profile. During migration, identify the exact active infrastructure to avoid duplicate registrations.

## 8. Migration Step 4 — Configure Explicit Assembler When Needed

Some applications do not use `@EnableMBeanExport` and instead declare a custom exporter, assembler, and naming strategy. In that case, annotation metadata must be wired to the right components:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Bean
public AnnotationJmxAttributeSource jmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
public MetadataMBeanInfoAssembler metadataAssembler(
        AnnotationJmxAttributeSource source) {
    MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}

@Bean
public MetadataNamingStrategy metadataNamingStrategy(
        AnnotationJmxAttributeSource source) {
    MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
    naming.setAttributeSource(source);
    return naming;
}
\`\`\`

Exporter:

\`\`\`java
@Bean
public MBeanExporter cacheExporter(
        CacheManager cacheManager,
        MBeanServer server,
        MetadataMBeanInfoAssembler assembler,
        MetadataNamingStrategy naming) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setAssembler(assembler);
    exporter.setNamingStrategy(naming);
    exporter.setBeans(java.util.Map.of(
            "cacheManager", cacheManager));
    return exporter;
}
\`\`\`

In this example, the exporter receives the key `cacheManager`, and the naming strategy reads `@ManagedResource` metadata to construct the `ObjectName`. If you want to pin the name explicitly, you can pass the full name in the mapping, but verify how the naming strategy actually processes that key.

This configuration is an **alternative** to `@EnableMBeanExport` in the previous example, not something to enable simultaneously for the same managed object.

## 9. Mapping Getters/Setters to @ManagedAttribute

A Standard MBean uses JavaBean conventions:

\`\`\`java
int getEntryCount();
boolean isEnabled();
void setEnabled(boolean value);
\`\`\`

Spring annotation-based JMX can use:

\`\`\`java
@ManagedAttribute
public int getEntryCount() { ... }

@ManagedAttribute
public boolean isEnabled() { ... }

@ManagedAttribute
public void setEnabled(boolean enabled) { ... }
\`\`\`

Verify after migration:

| Element | Before | Desired after |
| --- | --- | --- |
| `EntryCount` | `int`, readable | `int`, readable |
| `Enabled` | `boolean`, readable/writable | `boolean`, readable/writable |
| Getter name | `getEntryCount` | Unchanged |
| Boolean accessor | `isEnabled` | Unchanged |
| Setter parameter | `boolean` | Unchanged |

If you annotate only the getter and omit the annotation on the setter, the attribute may become read-only under the metadata assembler. If old clients call `setAttribute(...)`, that is a breaking change.

A getter can return a primitive or an object type; for remote clients, ensure the data type is supported by JMX/transport. Depending on whether it is exported as Standard MBean or ModelMBean, type descriptors may differ; real tests are the authority.

## 10. Mapping Operations to @ManagedOperation

Standard MBean:

\`\`\`java
public interface CacheManagerMBean {
    void clearStatistics();
    String reloadRules(String profile);
}
\`\`\`

Annotation metadata:

\`\`\`java
@ManagedOperation(description = "Clear cache counters")
public void clearStatistics() {
    // ...
}

@ManagedOperation(description = "Reload rules from a profile")
@ManagedOperationParameter(
    name = "profile",
    description = "Configuration profile to load")
public String reloadRules(String profile) {
    return "RELOADED:" + profile;
}
\`\`\`

`@ManagedOperationParameter` or `@ManagedOperationParameters` describe parameters, but **do not change the Java type/signature** of the operation. To stay compatible with old clients, method name, parameter count, parameter order, types, and semantics must stay consistent.

Example old client:

\`\`\`java
Object result = server.invoke(
        name,
        "reloadRules",
        new Object[]{"blue"},
        new String[]{"java.lang.String"});
\`\`\`

If after migration `reloadRules` accepts only `int` or is renamed to `reloadConfiguration`, the invocation above will fail even though the MBean still registers successfully.

Parameter descriptions are not a validation mechanism. For invalid input, the method must validate it and return a meaningful error or status.

## 11. ObjectName Must Stay Stable

Example old contract:

\`\`\`text
com.example.cache:type=CacheManager,name=primary
\`\`\`

The new configuration must keep the same name if clients depend on it:

\`\`\`java
@ManagedResource(
    objectName = "com.example.cache:type=CacheManager,name=primary")
\`\`\`

Common migration mistakes:

- Changing domain from `com.example.cache` to `com.example`.
- Dropping the `name=primary` key.
- Using a different class name as `type` without a client update plan.
- Having two instances both annotated with the exact same full `ObjectName`.
- Switching `KeyNamingStrategy` to `MetadataNamingStrategy` without verifying the final name.
- Having two exporters manage the old name simultaneously.

An `ObjectName` identifies an MBean **within a single `MBeanServer`**. Two separate JVMs can use the same name without conflict; clients must still connect to the right JVM/server endpoint.

When renaming is necessary, perform a versioned migration: create the new name under another domain/key, notify clients, and maintain a controlled compatibility window. However, do not register two names for the same object if doing so allows operations with side effects to be invoked twice or complicates ownership without impact assessment.

## 12. Avoid Registering Two MBeans Under the Same Name During Transition

A system might accidentally run in parallel:

\`\`\`text
Legacy MBeanExporter -> Standard MBean -> ObjectName X
AnnotationMBeanExporter -> Annotated bean -> ObjectName X
\`\`\`

The usual result is a registration conflict:

\`\`\`text
InstanceAlreadyExistsException: X
\`\`\`

Spring policies like `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, and `REPLACE_EXISTING` change conflict handling, **not prove the migration is right**.

- `FAIL_ON_EXISTING`: helps detect overlapping configurations.
- `IGNORE_EXISTING`: may keep the old MBean, causing the new annotation export to be silently skipped.
- `REPLACE_EXISTING`: may swap the target under the same name and create lifecycle ownership issues.

A safe process usually tests both configurations in **two isolated environments/servers**, then enables a single active export mechanism in production runtime.

If running two versions in parallel for comparison, use separate servers or explicit versioned names instead of abusing replace policy to overwrite an existing name.

## 13. Integrating with Spring AOP Proxies

In a Spring application, a managed bean may be a Spring AOP proxy due to `@Transactional`, security, or other aspects. A JDK dynamic proxy exposes interfaces, which can hide the implementation class during introspection.

When migrating from a Standard MBean interface to annotations on the implementation:

1. Annotations may reside on the target class, not on the runtime JDK proxy class.
2. Management methods might not be exposed on the business interfaces implemented by the proxy.
3. An annotation-aware assembler may support reading target metadata, yet the invocation path still must work properly.
4. Class-based proxies have different traits, though they do not automatically guarantee every method is safe to export.

Do not make absolute claims that annotation mode “always breaks with JDK proxies” or “always handles every proxy”. Inspect the runtime bean type, final metadata, and actual JMX invocations.

When a business service is complex, creating a **dedicated management facade** is a solid option:

\`\`\`java
@ManagedResource(
    objectName = "com.example.cache:type=CacheManager,name=primary")
public class CacheManagementFacade {

    private final CacheService cacheService;

    public CacheManagementFacade(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    @ManagedAttribute
    public int getEntryCount() {
        return cacheService.getEntryCount();
    }

    @ManagedOperation
    public void clearStatistics() {
        cacheService.clearStatistics();
    }
}
\`\`\`

A facade limits the JMX surface, keeps the business service free of annotations, and handles AOP/transaction boundaries more cleanly.

## 14. Clients Using the Old Java Interface

Some remote clients use only standard JMX APIs:

\`\`\`java
connection.getAttribute(objectName, "EntryCount");
connection.invoke(
        objectName, "clearStatistics",
        new Object[0], new String[0]);
\`\`\`

Those clients depend on `ObjectName`, attributes, and operations. If post-migration metadata preserves an equivalent contract, compatibility is generally good.

Some Java clients may use a dynamic proxy such as:

\`\`\`java
CacheManagerMBean proxy = JMX.newMBeanProxy(
        connection,
        objectName,
        CacheManagerMBean.class);
\`\`\`

When the server switches to a Spring-built ModelMBean, the client proxy can still invoke the matching methods if the JMX contract matches and the proxy mechanism works. However, clients may depend on specific metadata, Standard MBean conventions, or interface types; therefore, verify compatibility with real clients.

**Do not rush to delete `CacheManagerMBean.java` from client artifacts/libraries** if external tools still compile against that interface. You can stop using the interface on the server implementation while retaining it as a client API with clear versioning/deprecation.

## 15. MBeanInfo Metadata Can Differ Even When APIs Are Compatible

After migration, metadata may change:

- `MBeanInfo.getClassName()` may reflect a different adapter/ModelMBean.
- Descriptions may be added from annotations.
- Descriptors and impact flags may differ.
- Getters/setters may appear differently in metadata.
- Constructor/notification metadata may differ.

If a monitoring client only reads `EntryCount`, these differences may have no impact. If a client enforces “only accept className X” or relies on an exact operation list, the migration can be breaking.

A good compatibility test has two layers:

1. **Contract assertions:** expected `ObjectName`, attribute names/types/access, and operation signatures/return types.
2. **Behavior assertions:** reading state, writing attributes, invoking operations, and observing expected side effects.

When comparing full metadata, define intentional acceptable differences rather than demanding byte-for-byte equality between two different MBean types.

## 16. Integration Test for the New Annotation Configuration

JUnit Jupiter example:

\`\`\`java
package com.example.cache;

import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class CacheJmxMigrationTest {

    @Test
    void annotatedMBeanKeepsManagementContract() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                "com.example.cache:type=CacheManager,name=primary");

            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);

            assertTrue(Arrays.stream(info.getAttributes())
                .anyMatch(a -> "EntryCount".equals(a.getName())
                    && "int".equals(a.getType())
                    && a.isReadable()));

            assertTrue(Arrays.stream(info.getAttributes())
                .anyMatch(a -> "Enabled".equals(a.getName())
                    && a.isReadable()
                    && a.isWritable()));

            assertTrue(Arrays.stream(info.getOperations())
                .anyMatch(o -> "clearStatistics".equals(o.getName())));

            CacheManager manager = context.getBean(CacheManager.class);
            manager.addEntry();

            assertEquals(
                1, server.getAttribute(name, "EntryCount"));

            server.setAttribute(
                name,
                new javax.management.Attribute("Enabled", false));

            assertFalse(manager.isEnabled());

            server.invoke(
                name,
                "clearStatistics",
                new Object[0],
                new String[0]);

            assertEquals(
                0, server.getAttribute(name, "EntryCount"));
        }
    }
}
\`\`\`

This test verifies registration, metadata, attribute reads/writes, and operation invocation. It illustrates the annotation configuration defined above and does not replace comparing against the old configuration if the goal is proving before/after migration equivalence.

In parallel test suites, the platform `MBeanServer` and fixed `ObjectName` values can collide. Use a dedicated test server or isolated domain/instance names in fixtures.

## 17. Comparing Old/New Contracts via a Structured Snapshot

Instead of saving console output whose order can shift, normalize metadata into a structured format:

\`\`\`text
ObjectName = com.example.cache:type=CacheManager,name=primary

ATTR:
  Enabled|boolean|R|W
  EntryCount|int|R|-

OP:
  clearStatistics|void|()
\`\`\`

In Java, extract `MBeanAttributeInfo[]` and `MBeanOperationInfo[]` from `MBeanInfo`, map them to records, and sort by name/signature. For overloaded operations, name alone is insufficient; compare full signatures.

When migrating to annotation metadata, account for the fact that `ModelMBeanInfo` may represent accessors as operation metadata: if the old Standard MBean lacked those entries, exact operation-set comparisons will differ. You can apply a compatibility policy that requires critical business operations and asserts no sensitive extra operations are exposed.

For systems where clients depend on complete metadata, do not discard these differences arbitrarily; snapshot tests must reflect the real contract used by clients.

## 18. Notes on MXBeans and Open Types

Not every `*MBean` interface is like an MXBean. MXBeans map Java types to Open Types, suitable for remote management clients using standardized data types.

If the legacy system used an MXBean rather than a Standard MBean, migrating to a Spring annotation ModelMBean does not automatically preserve those mapping rules.

Example MXBean:

\`\`\`java
public interface CacheMetricsMXBean {
    Map<String, Integer> getCountsByRegion();
}
\`\`\`

Clients may receive data as Open Types. Switching the implementation to annotation metadata on a POJO while returning a type unsuitable for remote serialization can impact clients.

Therefore, with MXBeans you must:

1. Inventory return/parameter types and actual Open Data formats.
2. Inspect `MBeanInfo` and `OpenMBeanInfo` if applicable.
3. Include a remote JMX connector in compatibility tests.
4. Consider keeping the MXBean contract if the only goal is modernizing Spring configuration.

Do not convert an MXBean to an annotation-based ModelMBean merely to “unify style” if remote data compatibility carries high risk.

## 19. Notification and Listener Compatibility

If the old Standard MBean implemented `NotificationBroadcaster`, clients may have registered `NotificationListener` instances. Switching to Spring annotation metadata does not automatically guarantee old notifications continue firing with the same type, source, sequence, and `userData`.

Determine:

- Which class or component emits notifications?
- Does `MBeanNotificationInfo` publish the old types?
- Do clients call `addNotificationListener` on the same `ObjectName`?
- Do listeners lose registrations when switching exporters?
- Do event names, payloads, or timing change?

Spring provides `NotificationPublisher`, `NotificationPublisherAware`, and notification metadata when using appropriate Spring JMX integration. If migration involves notifications, migrate event emission separately and test both remote and local callbacks, not just attributes.

When replacing a registration under the same `ObjectName`, listeners registered on the old MBean may not automatically follow to the new registration as expected. Design the rollout so clients can reconnect/re-subscribe.

## 20. Common Migration Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Context starts but JConsole does not show MBean | Annotation exporter not enabled or bean missing from context | Check `@EnableMBeanExport`, `@Bean`, correct server |
| `InstanceAlreadyExistsException` | Old Standard MBean exporter and new annotation exporter use same name | Keep single registration owner or isolate test servers |
| `AttributeNotFoundException` | Forgot annotation on getter/setter or attribute renamed | Compare `MBeanInfo` before/after |
| Setter does not work | `Enabled` became read-only | Annotate setter and test `setAttribute` |
| `ReflectionException` on invoke | Method name/signature mismatch | Compare `MBeanOperationInfo` |
| `NotCompliantMBeanException` | Exporter picked wrong MBean path/type | Check Standard MBean vs ModelMBean, assembler |
| Metadata differs from expectations | Spring ModelMBean has different descriptors/class name | Classify breaking vs acceptable differences |
| Java client fails to compile | `*MBean` interface removed from library | Keep client API or version migration |
| Remote client cannot read data type | MXBean/Open Types or serialization changed | Test remote connector with real data |
| Operation side effects changed | Implementation altered during migration | Separate business changes from migration |
| Notifications stop arriving | Listener lost on registration swap or different broadcaster | Verify notification contract, re-subscription |
| Spring AOP proxy hides methods/annotations | JDK proxy exposes only interfaces | Use facade or suitable export strategy |

## 21. Controlled Migration Checklist

**Before migration:**

- List existing exporters and `ObjectName` values.
- Identify clients and use cases.
- Snapshot `MBeanInfo`, including attribute access and operation signatures.
- Determine whether legacy is Standard MBean, MXBean, or ModelMBean.
- Document registration policy, server/connector, and lifecycle.
- Have integration tests for critical reads/writes/invokes/notifications.
- Check proxy/AOP setup and multiple contexts if any.

**During migration:**

- Add annotation metadata with identical method signatures.
- Configure the Spring JMX assembler and naming strategy properly.
- Do not enable two exporters for the same `ObjectName` in test environments.
- Compare metadata across two isolated servers/fixtures.
- Verify behavior against legacy clients.
- Preserve notification and security contracts.

**After migration:**

- Verify `ObjectName` via `queryNames`.
- Verify attribute/operation metadata.
- Test with JConsole and remote JMX clients if remote access is used.
- Monitor registration errors and operation failures.
- Ensure MBeans are unregistered by the proper owner on context shutdown.
- Remove the old interface from client artifacts only after inventorying all consumers.

## 22. Rollout and Rollback Plan

A production migration should not rely on swapping the class directly and restarting with no path back.

**Phase 1 — Baseline:** capture the JMX contract snapshot and confirm which names clients use.

**Phase 2 — Code:** add annotations without yet changing the exporter in the primary runtime. Prepare the new configuration and tests.

**Phase 3 — Verification:** run the Standard MBean and annotation metadata configurations in two isolated test environments; compare contracts and functional behavior.

**Phase 4 — Canary:** deploy one application instance using the annotation exporter, monitoring errors, metrics, and client compatibility. Other instances stay on the old config.

**Phase 5 — Rollout:** progressively transition instances with consistent naming/endpoints. Avoid changing remote authentication/network policies simultaneously unless necessary.

**Phase 6 — Cleanup:** after the compatibility window, remove the legacy exporter and unused server-side interface, while retaining client-facing interface artifacts if consumers still depend on them.

**Rollback:** revert to the old configuration in a compatible deployment, ensuring only one exporter registers each `ObjectName` in the same server. If clients changed, assess backward compatibility before rolling back.

Note for multi-JVM environments: each JVM has its own registry; two versions can use the same `ObjectName` without cluster-wide collision. However, monitoring systems must distinguish instance endpoints to avoid mixing data.

## 23. Hands-on Exercises

**Exercise 1 — Standard MBean baseline.** Create `CacheManagerMBean` and `CacheManager`, exporting under `com.example.cache:type=CacheManager,name=primary`. Read `MBeanInfo`, recording attributes and operations.

**Exercise 2 — Annotation replacement.** Remove the interface implementation in a separate fixture, add `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, and enable `@EnableMBeanExport`. Compare `MBeanInfo` against baseline.

**Exercise 3 — Setter compatibility.** Intentionally omit `@ManagedAttribute` on `setEnabled`, verify the attribute becomes read-only or behavior changes per assembler. Then fix the annotation and re-run the test.

**Exercise 4 — Operation signature.** Add `reloadRules(String profile)` and define `@ManagedOperationParameter`. Invoke via `MBeanServer.invoke` with signature `java.lang.String`; try an incorrect signature and explain the exception.

**Exercise 5 — Legacy client interface.** Keep `CacheManagerMBean` in a client module and use `JMX.newMBeanProxy` to call the new ModelMBean. Verify compatible methods and note metadata differences.

**Exercise 6 — Two exporters.** Deliberately enable both the legacy exporter and annotation exporter with the same name in an isolated test, observe the failure, then keep only one exporter. Explain why `IGNORE_EXISTING` can mask a migration that did not actually occur.

**Exercise 7 — AOP.** Wrap the service in a JDK proxy via a business interface, attempt exporting annotation metadata, inspect `AopUtils` and `MBeanInfo`. Implement a variant using a management facade to separate concerns.

**Exercise 8 — Remote compatibility.** Set up a JMX remote connector in an isolated environment, read attributes and invoke operations from another JVM client. If using MXBean/Open Types or notifications, verify exact data types and callbacks.

## Conclusion

**Migrating from MBean interfaces to annotation metadata** in Spring Framework JMX changes how the management contract is described, and should not unintentionally alter system behavior at the same time. Standard MBean interfaces and Spring annotation-based ModelMBeans generate metadata differently, so staying compatible requires preserving **`ObjectName`, attribute names/types/access, operation signatures/behavior, notifications, and client expectations**. Execute the migration in isolated environments, use `MBeanInfo` and integration tests to compare before and after, keep only one active exporter per registration, and maintain a clear rollback path. A successful migration means the application runs on the new configuration while existing administration tools continue working against the committed contract.
