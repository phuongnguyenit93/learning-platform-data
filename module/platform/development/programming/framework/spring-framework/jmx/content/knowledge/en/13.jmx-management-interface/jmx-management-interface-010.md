# Comparing MBeanInfoAssembler with @ManagedAttribute and @ManagedOperation in Spring Framework JMX

## 1. The concept to understand

In Spring Framework JMX, a Spring bean can be registered into `MBeanServer` so management tools can read state or invoke actions. However, **not every Java method should appear on the management interface**.

Two concepts are often mistakenly contrasted as opposites:

- **`MBeanInfoAssembler`**: Spring's component that builds `MBeanInfo` metadata for an MBean from a class, interface, method list, or metadata.
- **`@ManagedAttribute` and `@ManagedOperation`**: annotations declaring that a getter/setter or an operation should become part of the management interface.

Key point: **assemblers and annotations are not mutually exclusive mechanisms**. Annotations are a **metadata source**, and an appropriate assembler—typically `MetadataMBeanInfoAssembler` paired with `AnnotationJmxAttributeSource`—reads that metadata to build `MBeanInfo`.

Other assemblers can publish methods **without annotations**. For example, `SimpleReflectiveMBeanInfoAssembler` relies on reflection, `MethodNameBasedMBeanInfoAssembler` relies on a list of method names, and `InterfaceBasedMBeanInfoAssembler` relies on configured management interfaces.

## 2. Processing chain from Spring bean to JMX client

```text
                        Spring bean
                            |
                  MBeanExporter selects bean
                            |
                  MBeanInfoAssembler
                            |
          +-----------------+------------------+
          |                 |                  |
      Reflection       Method names        Metadata
          |                 |                  |
    Public methods       Allowlist       @ManagedResource
                                          @ManagedAttribute
                                          @ManagedOperation
          |                 |                  |
          +-----------------+------------------+
                            |
                   MBeanInfo metadata
             attributes / operations / info
                            |
                  ModelMBean + ObjectName
                            |
                        MBeanServer
                            |
                  JConsole / VisualVM / API
```

`MBeanExporter` is responsible for exporting beans. `MBeanInfoAssembler` determines the metadata of the adapted MBean. `ObjectNamingStrategy` determines the `ObjectName`. These components have distinct responsibilities, even though they can be configured together.

Spring makes annotation-based export convenient via `@EnableMBeanExport`; this configuration sets up the infrastructure for reading annotation metadata and exporting eligible beans, so applications usually do not need to declare an assembler manually. However, `@ManagedAttribute` sitting alone on a method **does not automatically register** the bean into MBeanServer.

## 3. Distinguishing attributes and operations before comparing

In JMX:

- **Attribute** represents state or configuration. Clients read it with `getAttribute(ObjectName, "ActiveJobs")`, and write it with `setAttribute` only if the attribute is writable.
- **Operation** represents a management action. Clients call it with `invoke(ObjectName, operationName, arguments, signature)`.
- **MBeanInfo** is the metadata describing attributes, operations, notifications, and data type information.

A Java method does not become an attribute merely because it reads an internal field. By JavaBean conventions, `getActiveJobs()` or `isEnabled()` can be an accessor for attribute `ActiveJobs` or `Enabled`. A method like `requestRefresh()` is normally treated as an operation.

Example:

```java
public class WorkerService {
    private volatile boolean enabled = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getActiveJobs() {
        return 3;
    }

    public void requestRefresh() {
        // Call necessary service
    }

    public void deleteAllHistory() {
        // Internal business API, should not be published by default
    }
}
```

The management goal might only be `Enabled` (read-only), `ActiveJobs` (read-only), and `requestRefresh()`. The choice of assembler and annotations decides what clients actually see.

## 4. MBeanInfoAssembler is a metadata-building strategy

The `org.springframework.jmx.export.assembler.MBeanInfoAssembler` interface defines the role of building `ModelMBeanInfo` for exported beans. Spring provides implementations for different publication styles.

| Selection style | Typical component | Principle |
| --- | --- | --- |
| Reflection | `SimpleReflectiveMBeanInfoAssembler` | Reflects public getters/setters and public methods per assembler rules |
| Name list | `MethodNameBasedMBeanInfoAssembler` | Selects methods whose names are in the configured list |
| Name exclusion | `MethodExclusionMBeanInfoAssembler` | Reflects while excluding listed methods |
| Management interface | `InterfaceBasedMBeanInfoAssembler` | Exposes only methods matching the selected interfaces |
| Annotation/metadata | `MetadataMBeanInfoAssembler` | Reads metadata from `JmxAttributeSource`, typically `AnnotationJmxAttributeSource` |

An assembler can choose getters/setters to build attributes and other methods to build operations. Assemblers differ in their policies for which methods are exposed. They are not a runtime authorization mechanism: **the assembler decides the published surface**, while the connector/MBeanServer decides whether a client has permission to use that surface.

### 4.1. SimpleReflectiveMBeanInfoAssembler

Convenient when a class is a small management adapter with a targeted public API. However, a business class with many public methods can easily expose more than intended.

```java
MBeanExporter exporter = new MBeanExporter();
exporter.setAssembler(
    new SimpleReflectiveMBeanInfoAssembler()
);
```

With `WorkerService` above, do not assume `deleteAllHistory()` is hidden merely because it lacks `@ManagedOperation`. A reflection assembler does not use annotations as an allowlist.

### 4.2. MethodNameBasedMBeanInfoAssembler

Selects methods whose names are listed in configuration. This is an external allowlist approach, useful when you do not want to modify bean source code.

```java
MethodNameBasedMBeanInfoAssembler assembler =
    new MethodNameBasedMBeanInfoAssembler();
assembler.setManagedMethods(
    "getActiveJobs",
    "requestRefresh"
);
```

Note that the names used are **Java method names**, not JMX attribute names. When overloads need to be distinguished, check the semantics of the assembler in your Spring version and inspect actual `MBeanInfo`; do not treat method names as a per-signature authorization model.

### 4.3. InterfaceBasedMBeanInfoAssembler

A management interface can separate the management contract from the full public API of the implementation.

```java
public interface WorkerManagement {
    int getActiveJobs();
    void requestRefresh();
}
```

The assembler is configured to select this interface, so adding a business method to the implementation does not automatically expand the JMX contract.

### 4.4. MetadataMBeanInfoAssembler

`MetadataMBeanInfoAssembler` uses `JmxAttributeSource` to read metadata. When paired with `AnnotationJmxAttributeSource`, management annotations become the source for method selection and descriptions.

```text
@ManagedAttribute / @ManagedOperation
                  |
          AnnotationJmxAttributeSource
                  |
          MetadataMBeanInfoAssembler
                  |
                 MBeanInfo
```

If the application already uses `@EnableMBeanExport`, Spring configures most of this chain. You do not need to create another manual assembler just to enable annotation export.

## 5. @ManagedAttribute declares attributes

The `org.springframework.jmx.export.annotation.ManagedAttribute` annotation is typically placed on the getter or setter you want to publish.

```java
@ManagedAttribute(description = "Number of currently running jobs")
public int getActiveJobs() {
    return workerService.getActiveJobCount();
}
```

This declares that the `ActiveJobs` property serves management. The method can compute directly, read an atomic counter, or delegate to a service. It does not need a 1:1 mapping to a Java field.

For booleans:

```java
@ManagedAttribute(description = "Whether accepting jobs is enabled")
public boolean isEnabled() {
    return workerService.isEnabled();
}
```

If writing should be allowed, you can expose the setter:

```java
@ManagedAttribute(description = "Enable/disable accepting jobs")
public void setEnabled(boolean enabled) {
    workerService.setEnabled(enabled);
}
```

When the corresponding getter/setter are exported, the `Enabled` attribute can become writable. This is a control capability change, not just a display change: JMX clients with write access can alter runtime state. Only expose a setter when genuinely needed, while enforcing invariants, validation, authorization, and auditing at the appropriate layer.

**`@ManagedAttribute` differs from a Java field:** a `private int activeJobs` field is not automatically exposed; the selected accessor creates the JMX attribute. A getter can return an aggregated metric with no identically named field.

## 6. @ManagedOperation declares management operations

The `org.springframework.jmx.export.annotation.ManagedOperation` annotation marks a method to be included in the operation list.

```java
@ManagedOperation(description = "Request worker configuration refresh")
public void requestRefresh() {
    workerService.requestRefresh();
}
```

Operations can take parameters:

```java
@ManagedOperation(description = "Set worker limit")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "limit",
        description = "Number of workers, from 1 to 64"
    )
})
public void updateWorkerLimit(int limit) {
    if (limit < 1 || limit > 64) {
        throw new IllegalArgumentException(
            "limit must be in [1, 64]"
        );
    }
    workerService.updateWorkerLimit(limit);
}
```

To compile this example, import `ManagedOperation`, `ManagedOperationParameter`, and `ManagedOperationParameters` from package `org.springframework.jmx.export.annotation`.

Metadata annotations can supply descriptions for JMX tooling, but do not provide security controls by themselves. Clients with permission to invoke operations can still affect data or performance if the implementation lacks constraints.

Do not put `@ManagedOperation` on every public method just “for convenient viewing”: that expands the remote management surface when a JMX connector is enabled.

## 7. Complete example: annotation-based export

The application wants to expose a management adapter for a worker pool without exposing business methods.

**Managed bean:**

```java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Main",
    description = "Worker pool status and management operations"
)
public class WorkerPoolManagement {
    private final WorkerPoolService service;

    public WorkerPoolManagement(WorkerPoolService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Number of active workers")
    public int getActiveWorkers() {
        return service.getActiveWorkerCount();
    }

    @ManagedAttribute(description = "Number of pending tasks")
    public long getPendingTasks() {
        return service.getPendingTaskCount();
    }

    @ManagedOperation(description = "Request worker pool refresh")
    public void requestRefresh() {
        service.requestRefresh();
    }

    // This public method is not intentionally exposed via annotation.
    public String internalDescription() {
        return "implementation detail";
    }
}
```

`WorkerPoolService` is the application's business service providing the three delegated methods in the example; define or inject a real service suitable for your project.

**Configuration:**

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

In Spring's configured annotation-based model, clients expect to see:

```text
ObjectName:
  com.example.jobs:type=WorkerPool,name=Main

Attributes:
  ActiveWorkers   (read-only)
  PendingTasks    (read-only)

Operations:
  requestRefresh()
```

The `internalDescription()` method has no management annotation and is not expected to appear in the annotation-selected contract. Distinguish this from configuring a separate `SimpleReflectiveMBeanInfoAssembler`: in that case, public methods can be exposed even without annotations.

## 8. Manually configuring MBeanExporter with MetadataMBeanInfoAssembler

When you need direct control over an `MBeanExporter`, you can wire the metadata assembler and naming strategy instead of using `@EnableMBeanExport`:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ExplicitJmxExportConfiguration {
    @Bean
    AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler mbeanInfoAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy objectNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter mbeanExporter(
            WorkerPoolManagement management,
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of("workerPool", management));
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        return exporter;
    }
}
```

`@ManagedResource.objectName` on the bean is used by the naming strategy to determine the MBean name. If no name is declared in metadata or another naming strategy is used, the name may be generated by different rules; clients must know the actual ObjectName.

This is an **alternative approach**, not a configuration meant to run alongside `@EnableMBeanExport`. If two exporters attempt to register the same ObjectName, `InstanceAlreadyExistsException` or registration-policy-dependent behavior can occur.

## 9. Direct comparison: assemblers vs. annotations

| Criterion | Reflection/allowlist/interface-based assembler | `@ManagedAttribute` / `@ManagedOperation` annotations |
| --- | --- | --- |
| Nature | Strategy for building `MBeanInfo` | Metadata placed on accessors/operations |
| Configuration location | Java config / XML / exporter bean | Near method source code |
| Method selection | Reflection, method names, or management interface | Annotations read via `AnnotationJmxAttributeSource` + `MetadataMBeanInfoAssembler` |
| Requires modifying class? | Not necessarily | Usually yes if annotating directly |
| Risk of accidental exposure | Higher with simple reflection on large services | Lower when explicitly selecting methods and properly configured |
| Descriptive metadata | Depends on strategy and configuration | Includes descriptions and annotation metadata |
| Separating contract from implementation | Clear with interface-based assembler | Achievable via a management adapter |
| Spring dependency | Integrated in Spring JMX exporter | Spring JMX annotations |
| Flexibility | Configuration changes without editing code | Convenient and visual when code is owned |
| JMX connector permissions | Not controlled directly | Not controlled directly |

You cannot make an absolute claim that “assemblers are old, annotations are new”: **annotation-based export also needs an assembler** to convert annotation info into MBeanInfo. The practical difference lies in whether **metadata is inferred automatically, listed externally, or declared explicitly in code**.

## 10. When to choose each approach?

### 10.1. Choose reflection when the class is already a small management adapter

A dedicated class with only public methods meant for management, e.g., `getHealth()`, `getActiveCount()`, `requestReload()`, can fit `SimpleReflectiveMBeanInfoAssembler`. In return, understand that adding a public method later can unintentionally widen the JMX contract.

### 10.2. Choose method-name allowlist when source cannot be modified

If the bean belongs to an external library or you do not want to add Spring JMX dependencies to the domain, `MethodNameBasedMBeanInfoAssembler` allows selecting methods through configuration. However, if the API has complex overloads, inspect the actual metadata of exposed signatures.

### 10.3. Choose interface-based when a clear contract is needed

`InterfaceBasedMBeanInfoAssembler` fits when management is a long-term contract and Java clients need stability. Changing the implementation rarely alters the MBean contract as long as the interface remains unchanged.

### 10.4. Choose annotation-based when the Spring app owns the code

In a Spring application, annotation-based export is usually easy to read and maintain: put `@ManagedResource` on an adapter or bean, `@ManagedAttribute` on getters/setters, and `@ManagedOperation` on actions. `@EnableMBeanExport` reduces configuration boilerplate.

For production, a small management adapter combined with selective annotations is easier to control than reflection over a large business service.

## 11. A method can change roles depending on the assembler

Suppose:

```java
public class InventoryService {
    public int getStockCount() { return 120; }
    public void refreshStock() { /* ... */ }
    public void purgeAll() { /* ... */ }
}
```

If the exporter uses simple reflection, public methods can be included in metadata. If using `MethodNameBasedMBeanInfoAssembler` with `getStockCount` and `refreshStock`, only those selected names are export targets. If using the metadata assembler, the class needs corresponding annotations, and unannotated methods do not become part of the intended management surface.

Controlled annotation example:

```java
@ManagedResource(
    objectName = "com.example.inventory:type=InventoryManagement"
)
public class InventoryManagement {
    private final InventoryService inventory;

    public InventoryManagement(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ManagedAttribute
    public int getStockCount() {
        return inventory.getStockCount();
    }

    @ManagedOperation
    public void requestRefresh() {
        inventory.refreshStock();
    }
}
```

Do not place `purgeAll()` on the adapter just for debugging. JMX clients can only invoke published operations, yet if a dangerous operation is published, an obscure method name provides no protection.

## 12. How to verify the actually published surface

After the bean is exported, read `MBeanInfo` from the right MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name =
    new ObjectName("com.example.jobs:type=WorkerPool,name=Main");

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, type=%s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s, params=%d%n",
        operation.getName(),
        operation.getSignature().length
    );
}
```

The example assumes the exporter uses the platform MBeanServer; if another server is configured, connect to that exact server. Inspecting `MBeanInfo` helps distinguish design intent from the final contract. Specifically verify which attributes are writable and that no unintended state-mutating operations exist.

You do not need to read a bean's private fields to know the JMX contract: JMX clients see exported metadata, not Java fields directly.

## 13. Common errors and misconceptions

| Symptom | Common cause | Approach |
| --- | --- | --- |
| Has `@ManagedAttribute` but JConsole does not see it | Exporter not enabled, bean not in context, or active assembler does not read annotations | Check `@EnableMBeanExport`/assembler and MBean registration |
| Unannotated public method is still an operation | Exporter uses simple reflection | Use metadata assembler or allowlist |
| Getter is exported as read-only | Corresponding setter not published | Only add setter when writing is genuinely permitted |
| Client calls wrong attribute name | JMX attribute is usually `ActiveWorkers`, not `getActiveWorkers` | Inspect `MBeanInfo` and use the exact name |
| Multi-parameter operation fails to invoke | Wrong signature or parameter types | Check `MBeanOperationInfo.getSignature()` |
| MBean does not exist | Wrong ObjectName, not exported, or wrong MBeanServer | Use `isRegistered`, check naming and lifecycle |
| Duplicate ObjectName | Multiple exporters/beans registering the same name | Use a clear naming policy and avoid duplicate exporters |
| Methods exported too broadly | Using reflection on a business service | Export a small-API adapter or use an allowlist |
| Read-only client's operation call rejected | Connector authorization blocks invoke | Do not confuse with a metadata error; check policy |

**Distinguishing metadata errors from permission errors:** an operation can appear in `MBeanInfo` while the client lacks permission to invoke it. Conversely, even a highly privileged tool cannot invoke a method not published through the MBean contract simply by knowing an internal Java method name.

## 14. Security and stability of the management contract

Regardless of which assembler is used, exposed MBeans may be accessed by local or remote clients per connector configuration. Therefore:

- Publish only attributes/operations needed for monitoring and operations.
- Avoid `getPassword()`, `getToken()`, raw customer data, and stack traces containing sensitive details.
- Getters should be lightweight, resource-bounded, and side-effect-free since clients can poll continuously.
- Operations like `stop()`, `clear()`, and `purge()` must have clear semantics, validation, auditing, and proper execution permissions.
- Do not treat annotations as a security policy; JMX connector authentication, TLS, and authorization are a separate layer.
- Keep `ObjectName`, attribute names, types, units, and operation signatures stable when refactoring classes.
- If choosing reflection, adding a public method can unexpectedly alter the contract.
- If using annotations, removing/renaming annotations or getters can break dashboards relying on old attributes.

**A read-only attribute does not mean public data**: read-only access can still leak configuration and system information. Data exposure decisions must begin with information classification, not merely write permissions.

## 15. Quick decision flow

```text
Need to expose a Spring bean via JMX?
       |
       +-- Can modify code and want to select methods explicitly?
       |       |
       |       +-- Yes -> @ManagedResource
       |                  @ManagedAttribute / @ManagedOperation
       |                  @EnableMBeanExport
       |
       +-- Do not want to modify the class?
       |       |
       |       +-- Have a management interface?
       |       |       |
       |       |       +-- Yes -> InterfaceBasedMBeanInfoAssembler
       |       |
       |       +-- Just a few methods -> MethodNameBasedMBeanInfoAssembler
       |
       +-- Class contains only a small, controlled management API?
               |
               +-- Can use SimpleReflectiveMBeanInfoAssembler,
                   but check the public surface and MBeanInfo
```

## 16. Conclusion

**`MBeanInfoAssembler` is the mechanism that selects and builds metadata, while `@ManagedAttribute` and `@ManagedOperation` are ways to declare metadata on methods.** The two concepts complement each other when using `MetadataMBeanInfoAssembler` with `AnnotationJmxAttributeSource`.

Choose the right strategy based on management contract requirements:

- Reflection is fast, but risks exposing additional public methods as classes evolve.
- Allowlists or interfaces decouple the management contract from implementation.
- Annotations are clear and maintainable in Spring applications, especially when paired with a small management adapter.

In all approaches, inspect actual `MBeanInfo` to know the exact published attributes/operations; secure connectors, restrict side-effecting operations, and keep contracts stable for JMX tools.
