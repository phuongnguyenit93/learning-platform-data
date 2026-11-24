# Distinguishing Autodetected Beans from Beans Declared in the MBeanExporter Map

## 1. Objective

In Spring Framework JMX, `MBeanExporter` is the component that exposes Spring-managed beans to an `MBeanServer`. The exporter can receive beans from two different sources: **an explicit list in the `beans` map** and **beans found by the autodetection mechanism**. Both sources can lead to MBean registration, but they do not carry the same meaning regarding selection, registration naming, and configuration predictability.

The question to solve is: how does a bean discovered by the exporter differ from a bean listed in the map, when should each approach be chosen, and what misconceptions must be avoided when both approaches are used together?

**Short answer:** The `beans` map is an **active, explicit** export list supplied by the configurator; autodetection is the process where the exporter **searches for candidates using discovery rules** in the Spring `ApplicationContext`. Being discovered does not mean every bean will be exported, and being in the map does not mean the bean was discovered via annotations.

## 2. Where the Two Mechanisms Sit in JMX Architecture

```text
Spring ApplicationContext
  |
  +-- Explicit registration
  |      MBeanExporter.setBeans(Map<String, Object>)
  |      key -> ObjectName / source identifier
  |      value -> bean instance or bean name
  |
  +-- Autodetection
         MBeanExporter.setAutodetect(true)
         / autodetectMode
         -> find candidate beans in context
         -> MBean / @ManagedResource recognition rules
  |
  v
MBeanExporter
  |-- ObjectNamingStrategy: determine ObjectName
  |-- MBeanInfoAssembler: describe attributes/operations
  |-- RegistrationPolicy: handle duplicate ObjectName
  v
MBeanServer
  |-- domain:type=...,name=...
  v
JConsole / VisualVM / JMX client
```

Do not confuse **bean discovery** with **MBean registration**: discovery builds the list of candidates, whereas registration places the actual MBean into the `MBeanServer` under a specific `ObjectName`. A bean can exist in the Spring context without belonging to the candidate list; or it can be a candidate yet fail to register due to naming errors, conflicts, permissions, or exporter configuration.

## 3. Approach 1: Explicit Declaration via the `beans` Map

`MBeanExporter` has a `beans` property, typically configured via `setBeans(Map<String, ?>)`. The map describes the objects the application **wants to export**. The key can be an ObjectName used for registration or an input to the naming strategy; the value can be an object or a reference as supported by the exporter configuration.

Java configuration example specifying one bean explicitly:

```java
package com.example.config;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ExplicitJmxConfiguration {
    @Bean
    public CacheManagement cacheManagement(CacheService service) {
        return new CacheManagement(service);
    }

    @Bean
    public MBeanExporter mbeanExporter(
            CacheManagement cacheManagement) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.cache:type=CacheManagement,name=Primary",
            cacheManagement
        ));
        return exporter;
    }
}
```

Here `CacheManagement` is an application management adapter, and `CacheService` is an injected business service; the example assumes these classes are already defined. Only one bean is passed into the map. The exporter does not need to scan the entire context to determine other candidates.

**Advantages of the map:**

- The list of MBeans is deliberately chosen and easy to audit against operational requirements.
- Can export a bean without `@ManagedResource`, provided the assembler and JMX conditions match.
- Allows clear control over the ObjectName or map key.
- Convenient for small management adapters; reduces the risk of an unexpected bean being exported when new components are added to the application.
- Suitable when needing to export only a limited subset in a context containing hundreds of services.

**Points to note:** the map does not itself define how all public methods are exposed. That depends on JMX standard MBeans or the `MBeanInfoAssembler` used by the exporter. Even an explicitly specified bean can still expose too many operations if a reflective assembler is used on a large service.

## 4. Approach 2: Discovering Beans Automatically via Autodetection

Autodetection allows the exporter to scan beans in the ApplicationContext and identify eligible objects for MBean registration according to discovery rules. The rules may be based on whether a bean already conforms to JMX MBean conventions or carries management metadata, depending on the mode and configuration.

Example of a POJO marked by Spring as manageable:

```java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=QueueMonitor,name=Main",
    description = "Job processing queue status"
)
public class QueueMonitor {
    private final QueueService service;

    public QueueMonitor(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getDepth() {
        return service.pendingJobCount();
    }
}
```

Concise configuration for annotation-based export:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

`@EnableMBeanExport` configures the necessary infrastructure to find and export beans matching management annotations. This is the common path when the application owns the source code, uses many `@ManagedResource` beans, and wants to manage metadata directly on classes/methods.

If configuring `MBeanExporter` manually, you can enable autodetection directly:

```java
@Bean
public MBeanExporter detectingExporter() {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setAutodetect(true);
    return exporter;
}
```

**Important:** autodetection mode, naming strategy, and MBeanInfoAssembler must match the kind of beans being discovered. Merely enabling `setAutodetect(true)` does not guarantee every `@ManagedResource` POJO will be exposed with the right metadata in every manual configuration. For annotation-based export, prefer `@EnableMBeanExport` or fully configure `AnnotationJmxAttributeSource`, `MetadataMBeanInfoAssembler`, and `MetadataNamingStrategy`.

## 5. Distinguishing by List Source and Identity

| Criterion | Bean in the `beans` Map | Bean Discovered by Autodetection |
| --- | --- | --- |
| Selection source | Provided by the configurator in `setBeans` | Exporter discovers candidates in ApplicationContext |
| Explicitness | High: each entry can be reviewed | Relies on markers/discovery rules across the bean set |
| Requires `@ManagedResource`? | Not mandatory across all export methods | Needs metadata/MBean type matching the detection mode |
| ObjectName | Can come from map key or naming strategy | Usually from naming strategy, annotation metadata, or MBean rules |
| Adding a new Spring bean | Does not automatically expand the map | Can create additional MBeans if the new bean matches criteria |
| Contract management | Still needs assembler/interface/metadata | Still needs assembler/interface/metadata |
| Main risk | Forgetting to add desired beans, wrong keys, repetitive manual config | Accidentally discovering many MBeans, duplicate ObjectNames, changes when scanning expands |
| Well suited for | Selective, security-sensitive endpoints, centralized config | Many management components with consistent annotations |

The two groups do not produce two fundamentally different kinds of MBeans. After registration, a JMX client only sees the MBean's ObjectName and metadata. The client cannot tell whether the bean was selected via the map or via autodetection, unless the application includes custom metadata showing that.

## 6. Map Key, Spring Bean Name, and JMX ObjectName

Three kinds of names must be distinguished:

1. **Spring bean name**: bean definition identifier in the ApplicationContext, such as `queueMonitor`.
2. **`MBeanExporter.beans` map key**: key used when declaring the exported object; can be an ObjectName string or processed by a naming strategy.
3. **JMX ObjectName**: registered MBean identifier, such as `com.example.jobs:type=QueueMonitor,name=Main`.

They can be related, but they are not the same concept. Example:

```java
Map<String, Object> managementBeans = Map.of(
    "com.example.jobs:type=QueueMonitor,name=Main",
    queueMonitor
);
exporter.setBeans(managementBeans);
```

Here the map key is already an ObjectName representation. If the naming strategy relies on annotation metadata, it may take the ObjectName from `@ManagedResource`. If the generated name differs from expectations, clients will not find the predicted name. When troubleshooting, read the actual MBean list with `MBeanServer.queryNames` and inspect `ObjectName.getCanonicalName()`.

## 7. Example Configuring Autodetect and Explicit on the Same Exporter

Conceptually, `MBeanExporter` can accept both an explicit map and an autodetection option. When both are enabled, anticipate the case where a bean specified in the map also belongs to the autodetected group.

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MixedExportConfiguration {
    @Bean
    public MBeanExporter mbeanExporter(
            CacheManagement cacheManagement) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.cache:type=CacheManagement,name=Primary",
            cacheManagement
        ));
        exporter.setAutodetect(true);
        return exporter;
    }
}
```

The example above **only illustrates two candidate sources** and is not a complete annotation export configuration. Exporting annotated POJOs as intended requires the right assembler/naming strategy. Do not assume the exporter will register two independent MBean copies for the same bean. Depending on detection rules, entry handling, and identity, the bean may be processed only once or collide on ObjectName with other candidates.

To minimize surprises, prefer **one primary selection source** for a group of MBeans. If using both simultaneously, plan ObjectNames and separate responsibilities clearly; inspect the registration list after startup.

## 8. Choosing the Assembler for Each Source

The map and autodetection answer the question **which beans to export**. The assembler answers the question **what to expose from that bean**.

For example, a bean placed in the map while using `SimpleReflectiveMBeanInfoAssembler`:

```java
public class MaintenanceService {
    public int getPendingTasks() { return 10; }
    public void refreshIndex() { /* ... */ }
    public void deleteAllData() { /* ... */ }
}
```

If exported via reflection, even public methods not meant for management can end up in `MBeanInfo`. Just because a bean is explicitly chosen does not mean its management interface is restricted.

In annotation-based export, a dedicated adapter can select only:

```java
@ManagedResource(
    objectName = "com.example.jobs:type=Maintenance,name=Main"
)
public class MaintenanceManagement {
    private final MaintenanceService delegate;

    public MaintenanceManagement(MaintenanceService delegate) {
        this.delegate = delegate;
    }

    @ManagedAttribute
    public int getPendingTasks() {
        return delegate.getPendingTasks();
    }

    @ManagedOperation
    public void requestRefreshIndex() {
        delegate.refreshIndex();
    }
}
```

`deleteAllData` does not appear in the adapter and is not an exposed operation. This reduces the management surface when clients have invoke privileges. However, annotations do not create authorization by themselves; the connector must be protected separately.

## 9. Distinguishing Autodetection from Component Scanning

These are three different steps:

```text
@ComponentScan
     |
     v
Spring finds classes -> registers bean definitions in context
     |
     v
MBeanExporter autodetect
     |
     v
Finds JMX candidates among context beans
     |
     v
MBeanExporter registers MBean under ObjectName
```

`@ComponentScan` is only how components are brought into the Spring context. It does not automatically turn every `@Component` into an MBean. Conversely, a bean created with `@Bean` that has appropriate JMX metadata can also be an autodetection candidate.

A `@ManagedResource` on a class without a bean instance in the context is not automatically found by the Spring exporter. To be autodetected, the object must participate in the management/registration mechanism the exporter actually uses.

In applications with multiple ApplicationContexts or parent-child contexts, the exporter's visibility scope can affect the set of discovered beans. Do not assume an exporter in a child context will manage beans from unrelated contexts.

## 10. Singleton, Prototype, and Discovery Timing

JMX registers one MBean under one ObjectName at a time, while Spring scope governs instance creation.

- **Singleton:** usually fits stable management MBeans well, because one bean instance is shared within the context.
- **Prototype:** each bean lookup can create a new instance; do not assume autodetection creates one ObjectName for every prototype instance spawned after startup.
- **FactoryBean and scoped proxy:** the bean type and actual instance may be resolved through a factory/proxy; check how the exporter recognizes and registers them in the actual configuration.
- **Dynamic beans:** an instance not in the Spring registry at autodetection time will not automatically become an MBean just because it is created later in business code.

If you need to manage a group of short-lived prototypes, designing an aggregating singleton management adapter is usually more stable than registering each instance. If individual dynamic MBeans are needed, build a lifecycle manager that proactively registers/unregisters them and assigns distinct ObjectNames.

## 11. Duplicate ObjectNames and RegistrationPolicy

The MBeanServer requires each ObjectName to identify at most one registered MBean. Collisions can happen when:

- Two entries in the map use the same ObjectName.
- An explicit bean shares an ObjectName with an autodetected bean.
- Two exporters run in the same ApplicationContext or two contexts share the same MBeanServer.
- An MBean was already registered by another subsystem before the exporter runs.
- Multiple instances are configured with a fixed name.

Spring provides `RegistrationPolicy` to control how existing names are handled:

| Policy | General Behavior | Notes |
| --- | --- | --- |
| `FAIL_ON_EXISTING` | Fails on duplicate registration | Usually good for catching unexpected configuration |
| `IGNORE_EXISTING` | Keeps the existing MBean | The new bean is not necessarily exposed |
| `REPLACE_EXISTING` | Replaces the existing MBean | May replace an endpoint owned by another context |

Example:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

Do not use `REPLACE_EXISTING` as a default conflict workaround. Instead, clearly identify who owns the ObjectName, because destroying a context or unregistering could affect an MBean not belonging to the exporter being handled.

## 12. Verifying Actually Registered MBeans

You cannot tell the export source from a single JMX query call. However, you can confirm the set of ObjectNames and management contracts after the application starts.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern =
    new ObjectName("com.example.*:*");

Set<ObjectName> names = server.queryNames(pattern, null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("  attributes=" + info.getAttributes().length);
    System.out.println("  operations=" + info.getOperations().length);
}
```

The code assumes the exporter registers into the platform MBeanServer. If the exporter uses a separate server, connect to that exact server. The pattern `com.example.*:*` only matches domains matching that wildcard; in systems with other domains, adjust the pattern accordingly.

You can also check a specific MBean:

```java
ObjectName exact =
    new ObjectName("com.example.cache:type=CacheManagement,name=Primary");

boolean registered = server.isRegistered(exact);
System.out.println("registered=" + registered);
```

If an MBean does not appear, analyze in order: is the bean in the context, does the map have an entry or does autodetection select it, is the assembler suitable, what name does the naming strategy generate, did registration collide or fail, and is the client connected to the right MBeanServer.

## 13. When to Choose the Map and When to Choose Autodetection?

### Choose the explicit map when:

1. You need a fixed, small, carefully reviewed list of MBeans.
2. You do not want to depend on annotations or markers on source classes.
3. You use a dedicated management adapter for a few critical services.
4. You want to ensure adding new beans to the context does not automatically expose them on JMX.
5. You need control over specific registration names and exported module scope.

### Choose autodetection when:

1. There are many Spring-managed beans clearly designed for management.
2. You consistently use annotation-based export with `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`.
3. You want to expand the MBean set by adding metadata to classes without updating a central map.
4. You have consistent naming conventions and an ObjectName collision management strategy.
5. You control the component scan/context area to avoid unintended expansion of the management surface.

### Combining both mechanisms:

This can fit when one group of beans is JMX-compliant and a group of adapters is declared explicitly. Even so, clearly document each group's responsibility, do not duplicate exporters, and do not treat autodetection as a “scan everything and resolve conflicts automatically” mechanism.

## 14. Common Misconceptions

| Misconception | More Accurate Reality |
| --- | --- |
| `@Component` automatically becomes an MBean | Component scanning and MBean autodetection are two separate steps |
| A bean without `@ManagedResource` cannot be exported | An explicit map can export an eligible bean via an assembler/MBean adapter |
| Explicit map means only getters are exposed | The method list depends on the MBean contract and assembler |
| `setAutodetect(true)` exposes every bean | Only candidates matching autodetect rules are evaluated |
| `@ManagedResource` opens remote JMX automatically | Exporting MBeans and enabling a remote connector are different configurations |
| Adding a new bean does not affect JMX | With autodetection, a new bean can become an MBean if it matches criteria |
| Duplicate ObjectNames can be ignored completely | Ownership, registration policy, and client consistency must be defined |
| JMX clients know whether a bean came from a map or autodetection | Clients usually see only ObjectName/MBeanInfo, not the Spring configuration source |

## 15. Security and Operations

Autodetection reduces configuration work, but it allows the MBean list to change as beans or annotations change. For production, this change must be treated as a management surface change. Important notes:

- Do not annotate/export getters containing credentials, tokens, personal data, or sensitive configuration.
- Do not expose destructive operations just for quick debugging.
- Management getters for monitoring should be lightweight, have minimal side effects, and bound returned data sizes.
- Protect the JMX connector with network policies, authentication, TLS, and proper authorization.
- Keep `ObjectName`, attribute names, types, and operation signatures stable so dashboards/scripts do not break.
- Ensure no other exporter on the same MBeanServer accidentally claims the same ObjectName.
- When multiple instances are needed, design names with sensible identifiers or distinguish by MBeanServer connection; do not default to random PIDs for endpoints dashboards need to access stably.

**The explicitness of a map is not a complete security layer**, and annotation-based autodetection does not automatically make an MBean safe either. Both require a minimal management contract and a JMX connector with appropriate authorization policies.

## 16. Mental Model

```text
Spring bean created in context
             |
      +------+-------+
      |              |
  explicit map    autodetection
      |              |
  dev-specified   MBean / metadata
    entries       discovery rules
      |              |
      +------+-------+
             |
         MBeanExporter
             |
       ObjectName + MBeanInfo
             |
      RegistrationPolicy
             |
         MBeanServer
             |
       JMX management tool
```

**Remember:** the `beans` map answers **“which exact beans do I choose to export”**; autodetection answers **“under this configuration, which eligible beans in the context are found”**. Both must go through MBean registration and metadata creation; both require managing ObjectName, lifecycle, and security. In applications with tightly controlled management contracts, an explicit map or selective annotation-based adapters are usually more predictable than broad, unplanned scanning.
