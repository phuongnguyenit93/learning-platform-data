# Assembler-Based Resource Autodetection in Spring Framework JMX

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain `MBeanExporter` **autodetection** and the bean selection mechanism through **`AutodetectCapableMBeanInfoAssembler`**.
- Distinguish interface/JMX-compliance MBean detection mode from metadata-assembler-based resource detection mode.
- Understand how `MetadataMBeanInfoAssembler`, `AnnotationJmxAttributeSource`, and `@ManagedResource` work together to decide whether a Spring bean is exported.
- Proactively configure the exporter and avoid accidentally exposing too many MBeans.
- Verify results using `MBeanServer.queryNames()` and `MBeanServer.getMBeanInfo()`.
- Recognize limitations related to Spring AOP proxies, bean names, `ObjectName`, duplicate exporters, and lifecycle.
- Design an appropriate discovery mechanism for a Spring application that has many beans where only a subset needs to be managed via JMX.

## 2. The Problem: Spring Has Many Beans—Which Beans Should Be Exported?

A Spring application can have hundreds of beans: controllers, services, repositories, schedulers, cache adapters, configurations, and infrastructure beans. Not every bean should appear in JConsole.

Example:

```text
ApplicationContext
├── orderController
├── orderService
├── orderRepository
├── paymentClient
├── inventoryClient
├── queueManagement      (@ManagedResource)
├── cacheManagement      (@ManagedResource)
└── internalScheduler
```

When you want to manage the queue and cache via JMX, you have two main approaches:

1. **Explicit export:** specify the exact beans and `ObjectName`s in `MBeanExporter.setBeans(...)`.
2. **Autodetection:** instruct the exporter to automatically find beans that satisfy certain conditions.

With **assembler-based** autodetection, the decision “is this bean considered a managed resource?” is delegated to an assembler capable of evaluating the inclusion condition. This fits annotation-driven JMX well: only beans with appropriate management metadata are selected.

Key idea:

> An assembler does not merely describe attributes and operations. When implementing `AutodetectCapableMBeanInfoAssembler`, it can also participate in **deciding which beans are autodetected for export**.

Therefore, “assembler-based resource autodetection” does not mean “scan every class with any annotation” or “export every public Java bean”.

## 3. Components to Distinguish

| Component | Function |
|---|---|
| `MBeanExporter` | Integrates Spring beans with `MBeanServer`, selects beans, and performs registration |
| `MBeanInfoAssembler` | Creates JMX metadata for attributes, operations, descriptions, etc. |
| `AutodetectCapableMBeanInfoAssembler` | Extends assembler with the ability to decide whether a bean should be autodetected |
| `MetadataMBeanInfoAssembler` | Assembler that reads management metadata from a `JmxAttributeSource` |
| `AnnotationJmxAttributeSource` | Metadata source from JMX annotations such as `@ManagedResource` |
| `@ManagedResource` | Marks a bean/class as a managed resource and provides resource metadata |
| `@ManagedAttribute` | Marks a getter/setter to expose as a JMX attribute |
| `@ManagedOperation` | Marks an operation permitted to be invoked via JMX |
| `ObjectNamingStrategy` | Determines the `ObjectName` of an exported bean |
| `MBeanServer` | JMX registry and runtime API |

A conceptual processing flow:

```text
Spring ApplicationContext
          |
          v
     MBeanExporter
          |
          +-- autodetectMode = ASSEMBLER
          |
          v
 AutodetectCapableMBeanInfoAssembler
          |
          +-- includeBean(beanClass, beanName)?
          |       |
          |       +-- false --> skip bean
          |       |
          |       +-- true
          |             |
          |             v
          |       build MBeanInfo
          |             |
          |             v
          +------ ObjectNamingStrategy
                        |
                        v
                 MBeanServer
                        |
                        v
                  JMX client
```

The diagram is a logical model for understanding each component's responsibility. Invocation timing, how a proxy's target class is detected, naming policies, and registration depend on the specific Spring version and configuration.

## 4. How Does Assembler Autodetection Differ from MBean Autodetection?

`MBeanExporter` supports autodetection modes that can be configured by constant names.

| Mode | General Meaning |
|---|---|
| `AUTODETECT_NONE` | Do not autodetect beans outside explicit registrations |
| `AUTODETECT_MBEAN` | Find beans that already fit the JMX MBean mechanism, such as Standard/Dynamic MBeans |
| `AUTODETECT_ASSEMBLER` | Let an autodetect-capable assembler decide which beans should be exported |
| `AUTODETECT_ALL` | Combine supported autodetection paths |

In the Spring API, the mode can be set using `setAutodetectModeName("AUTODETECT_ASSEMBLER")` or the corresponding numeric API depending on version.

Point to remember: `AUTODETECT_ASSEMBLER` is **not** synonymous with “take every Spring bean and turn it into an MBean”. It requires an **autodetect-capable assembler** and corresponding include conditions.

### Brief Comparison

Given:

```java
public class HealthMonitor implements HealthMonitorMBean { ... }
```

and:

```java
@ManagedResource(objectName =
        "com.example.shop:type=QueueMonitor,name=primary")
public class QueueManagement { ... }
```

If `AUTODETECT_MBEAN` is chosen, the exporter looks for beans meeting MBean criteria under the JMX mechanism. With `AUTODETECT_ASSEMBLER` and `MetadataMBeanInfoAssembler` + an annotation source, `QueueManagement` is evaluated according to `@ManagedResource`.

You should not predict all outputs of `ALL` mode without inspecting the actual assembler and naming strategy; this mode has a broader scope and can create unintended registrations.

## 5. Contract: AutodetectCapableMBeanInfoAssembler

An ordinary assembler is responsible for creating `MBeanInfo`. An assembler used for autodetection also needs the ability to decide whether a bean is selected.

Conceptual API in Spring:

```java
public interface AutodetectCapableMBeanInfoAssembler
        extends MBeanInfoAssembler {

    boolean includeBean(Class<?> beanClass, String beanName);
}
```

Meaning:

- `beanClass`: the class the exporter passes to the assembler for evaluation.
- `beanName`: the corresponding Spring bean name.
- Value `true`: the bean satisfies the inclusion policy and can be exported.
- Value `false`: the bean is not selected via the assembler's autodetection path.

This is an interface describing a **selection mechanism**, not an arbitrary API for invoking JMX operations.

With `MetadataMBeanInfoAssembler`, selection typically relies on being able to retrieve `ManagedResource` metadata from `JmxAttributeSource`. When combined with `AnnotationJmxAttributeSource`, `@ManagedResource` becomes a key signal for a managed resource.

**Do not confuse:** `@ManagedAttribute` on a getter alone is not necessarily enough for a class to be autodetected as a managed resource; the class-level `@ManagedResource` annotation is what marks a resource in the common metadata-based discovery flow.

## 6. MetadataMBeanInfoAssembler and AnnotationJmxAttributeSource

Suppose:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=QueueMonitor,name=outbox",
    description = "Order outbox queue")
public class QueueManagement {

    private int pendingCount;

    @ManagedAttribute(description = "Current pending jobs")
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedOperation(description = "Reset local statistics")
    public void resetStatistics() {
        pendingCount = 0;
    }
}
```

Role breakdown:

1. **`@ManagedResource`** helps identify this class as a resource to expose to JMX.
2. **`@ManagedAttribute`** describes the getter that becomes the `PendingCount` attribute.
3. **`@ManagedOperation`** describes the `resetStatistics` operation.
4. **`AnnotationJmxAttributeSource`** reads annotation information.
5. **`MetadataMBeanInfoAssembler`** interprets it into metadata and can decide inclusion.
6. **`MBeanExporter`** registers the bean under an ObjectName after discovery/naming.
7. **`MBeanServer`** provides the runtime API for external tools to access.

An annotation is code metadata; it is not an automatic command to register an MBean. An exporter must actually be configured and running in the Spring context.

## 7. Explicit Spring Configuration Example

With plain Spring Framework, you can configure the exporter with the appropriate assembler and naming strategy.

The example below illustrates the idea in Java configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;

@Configuration
public class JmxExportConfig {

    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy strategy =
                new MetadataNamingStrategy();
        strategy.setAttributeSource(source);
        return strategy;
    }

    @Bean
    MBeanExporter mBeanExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
        return exporter;
    }
}
```

In this configuration, the assembler and naming strategy both rely on **a single annotation attribute source**. That reduces the risk of the assembler selecting beans using metadata source A while the naming strategy names them using source B.

### Conditions for the Example to Work

- `QueueManagement` must be registered as a Spring bean, via `@Component` or a `@Bean` declaration.
- `@ManagedResource` must be recognized by the metadata source.
- The MBeanServer used by the exporter must exist and be properly configured; Spring can locate or create a server depending on the environment.
- Do not simultaneously configure another exporter scanning the same resources and registering the same ObjectNames.
- Specific constructor/setter APIs and lifecycle details should be checked against the Spring version in use.

This example illustrates **one configuration path**; many projects have simpler configurations via XML namespace, annotation exporter, or Spring Boot auto-configuration. There is no need to copy all of this if the framework already manages the exporter.

## 8. Declaring an Autodetected Bean

Management bean example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;
import java.util.concurrent.atomic.AtomicInteger;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox",
    description = "Local order queue management")
public class OrderQueueManagement {

    private final AtomicInteger pendingCount = new AtomicInteger();

    public void onQueued() {
        pendingCount.incrementAndGet();
    }

    public void onProcessed() {
        pendingCount.decrementAndGet();
    }

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount.get();
    }
}
```

In the same application, the following beans do not have `@ManagedResource`:

```java
@Component
public class OrderRepositoryAdapter {
    // Internal API.
}

@Component
public class PaymentClient {
    // Internal API.
}
```

When the assembler performs discovery based on resource annotations, these two ordinary beans are not selected merely because they are `@Component`s. This avoids exposing the entire API of services and repositories.

**Security principle:** `@ManagedResource` only marks a resource as exportable; it does not replace authentication, TLS, authorization, or network exposure policies for the JMX connector.

## 9. Bean Evaluation Flow at Application Startup

How to reason about startup configuration:

```text
Bean "orderQueueManagement"
    |
    +-- Is it a bean in ApplicationContext? ---- no -> not scanned
    |
    +-- Does Exporter have autodetection? ------ no -> only use explicit registration
    |
    +-- Is AUTODETECT_ASSEMBLER enabled? ------- no -> another mode applies
    |
    +-- Does Assembler implement autodetect? --- no -> not eligible for this path
    |
    +-- Does includeBean(...) return true? ----- no -> skipped
    |
    +-- Is there a valid ObjectName? ----------- no -> naming/registration error
    |
    +-- Is the ObjectName unoccupied? ---------- no -> conflict
    |
    +-- Does MBeanServer.registerMBean succeed? yes -> client can query
```

This diagram separates **discovery**, **metadata assembly**, **naming**, and **registration**.

If a bean does not appear, do not immediately assume `@ManagedAttribute` is broken. The bean might not have been scanned, might have been excluded by the assembler, might have an invalid ObjectName, or the exporter might have encountered a conflict.

## 10. Distinguishing Autodetection from Explicit Export

Autodetection and `setBeans` serve different purposes.

### Explicit Export

```java
import java.util.Map;
import org.springframework.jmx.export.MBeanExporter;

MBeanExporter exporter = new MBeanExporter();
exporter.setBeans(Map.of(
    "com.example.shop.orders:type=Queue,name=outbox",
    orderQueueManagementBean
));
```

This approach requires code/configuration to **place the bean into the export list**. It works well when the number of MBeans is small or an exact allowlist is needed.

### Assembler-Based Autodetection

```java
exporter.setAssembler(metadataAssembler);
exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
```

The exporter automatically finds beans permitted by the assembler. You do not need to manually list ObjectName → bean for each resource, though you still need to configure a naming strategy and manage annotation consistency.

**Do not assume:** `setBeans` acts as an additional filter over all autodetected beans. On an exporter configured with both, the explicit bean list and the autodetected set can be separate export paths. If you want to export only a small set, do not enable broad autodetect thinking `setBeans` will restrict everything.

### When to Choose Which?

| Context | Usually Reasonable Approach |
|---|---|
| Only 2–3 management beans | Explicit export is easy to control |
| Many modules with consistent JMX annotations | Assembler-based autodetect |
| Security requires a strict allowlist | Explicit export or autodetect with a tested policy |
| Libraries bring pre-built MBeans | Consider MBean autodetect or explicit registration |
| Application has many library-provided `@ManagedResource`s | Review autodetect scope before enabling |
| Dynamic ObjectNames needed per deployment | Purposeful naming strategy/factory |

## 11. How Does a Custom Autodetect Assembler Work?

An application may want to export only management beans belonging to a specific package or convention. If you build your own assembler, you must ensure both **metadata generation** and **inclusion rules**.

Simple idea:

```java
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

public class RestrictedManagementAssembler
        extends MetadataMBeanInfoAssembler {

    @Override
    public boolean includeBean(Class<?> beanClass, String beanName) {
        return beanName.endsWith("Management")
                && super.includeBean(beanClass, beanName);
    }
}
```

Key points:

- The `super.includeBean` condition preserves the managed-resource metadata check.
- Checking the bean name suffix is merely an additional convention-based policy.
- A bean is not exported if it lacks either the matching name or the resource annotation.

**Limitation of the example:** Bean names are usually decided by developers, `@Bean` methods, or component scanners, and are not automatically forced to end in `Management`. A name-based policy can miss valid resources. In a real system, use a tested convention and avoid depending on the runtime class name of an AOP proxy.

A package-based policy must also handle the target class properly if the bean is proxied. Do not assume `beanClass.getPackageName()` always points to the target implementation's package.

## 12. Metadata Assembler Is Not an Access Control Filter

`includeBean` decides whether a bean is selected for **export**. It does not decide which clients can read or invoke operations after export.

Example:

```java
@ManagedResource(
    objectName = "com.example.shop:type=JobController,name=primary")
public class JobManagement {

    @ManagedOperation
    public void restartWorkers() {
        // May cause operational impact.
    }
}
```

If this resource is autodetected, the operation may be exposed to JMX clients with the corresponding permissions. `@ManagedOperation` does not automatically activate a role-based business authorization model.

Therefore:

1. Do not annotate sensitive operations solely for debugging convenience.
2. Restrict JMX remote exposure.
3. Configure authentication/TLS/authorization appropriate to your deployment.
4. Add auditing/rate limiting when operations have significant impact.
5. Treat JMX annotations as part of the public management API.

Autodetection is solely a **selection mechanism**. It does not make an MBean safer or less safe by default; risk depends on what is exported and how access is protected.

## 13. Why Is @ManagedAttribute Alone Not Enough?

A class has:

```java
@Component
public class InternalStatistics {

    @ManagedAttribute
    public int getWorkerCount() {
        return 5;
    }
}
```

But has no `@ManagedResource` on the class.

With typical metadata-based autodetection, the assembler must identify **which classes are allowed to become managed resources**. If the inclusion criterion relies on `ManagedResource`, this class will not be selected, even though the getter has an annotation.

Explicit way:

```java
@Component
@ManagedResource(
    objectName = "com.example.shop:type=WorkerStats,name=primary")
public class WorkerStatisticsManagement {

    @ManagedAttribute
    public int getWorkerCount() {
        return 5;
    }
}
```

This clearly expresses “this object is an MBean” and “this getter is an attribute”. In projects with custom attribute sources/assemblers, inclusion rules may differ; check the actual implementation.

## 14. How Do Annotations and Management Interfaces Differ in Autodetect?

A Standard MBean has a management interface:

```java
public interface CacheMonitorMBean {
    int getEntryCount();
}
```

```java
public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public int getEntryCount() {
        return 10;
    }
}
```

It can be detected under **MBean autodetect** mode.

An annotation-driven resource:

```java
@ManagedResource(objectName =
    "com.example.shop.catalog:type=Cache,name=products")
public class CacheManagement {

    @ManagedAttribute
    public int getEntryCount() {
        return 10;
    }
}
```

can be detected via the **assembler**.

Two different contracts:

- Standard MBean: the `CacheMonitorMBean` interface defines the JMX surface.
- Annotation-driven: the `@Managed...` annotations and the assembler define the JMX surface.

Do not assume that an assembler configuration will automatically find all `*MBean` interfaces, or that MBean discovery mode will interpret all `@Managed...` annotations in the same way.

If you choose `AUTODETECT_ALL`, you must clearly understand both mechanisms and inspect runtime metadata, avoiding designing the management API based on guessing “their union”.

## 15. Interaction with Spring AOP Proxies

Spring can create a JDK dynamic proxy or a CGLIB proxy for beans using `@Transactional`, `@Cacheable`, security, retry, or custom advice.

Suppose:

```java
@ManagedResource(objectName =
    "com.example.shop.orders:type=OrderMonitor,name=main")
public class OrderMonitor {
    @ManagedAttribute
    public int getPendingCount() { return 5; }
}
```

but the runtime bean is a proxy.

Questions to determine:

1. Does the assembler evaluate the **proxy class** or the **target class** when checking inclusion?
2. Can the attribute source find `@ManagedResource` on the target?
3. Does a JDK proxy expose the annotated method?
4. If the MBean registers successfully, can clients actually read the attribute?

Notes:

- A JDK proxy typically exposes only methods of the interfaces it implements.
- A CGLIB proxy subclasses the class but has limitations with `final` and method visibility.
- Spring has utilities such as `AopUtils.isAopProxy` and `AopUtils.getTargetClass` to assist investigation.
- Do not unwrap the target and export it directly if doing so bypasses transaction/security advice.

A clean architectural solution is a **management adapter** minimally affected by AOP, calling business logic through the injected service proxy.

```java
@Component
@ManagedResource(objectName =
    "com.example.shop.orders:type=OrderMonitor,name=main")
public class OrderManagement {

    private final OrderService service;

    public OrderManagement(OrderService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getPendingCount() {
        return service.pendingCount();
    }
}
```

The adapter only has management responsibility; the target business service needs no JMX annotations. However, the adapter itself can still be affected by broad AOP pointcuts, so runtime configuration still needs verification.

## 16. Assigning ObjectName with Metadata Naming Strategy

When annotation-driven discovery uses `@ManagedResource(objectName="...")`, the naming strategy should read from the same metadata source.

Example:

```text
Managed resource:
  bean name = queueManagement
  class = OrderQueueManagement

Annotation:
  @ManagedResource(
      objectName = "com.example.shop.orders:type=Queue,name=outbox"
  )

MBeanServer:
  com.example.shop.orders:type=Queue,name=outbox
```

Do not confuse:

- **Spring bean name**: key in the ApplicationContext.
- **Java class name**: implementation class or proxy.
- **JMX ObjectName**: management identifier in the MBeanServer.

If the naming strategy generates an ObjectName from the bean name while the annotation contains a different ObjectName, investigation becomes difficult. You can deliberately use a different naming strategy; just ensure a clear, owned, and tested convention.

**There is no need** to stuff environment or pod IDs into the domain/ObjectName if monitoring already uses connection/instance metadata to distinguish JVMs. An ObjectName only needs to be unique within the same MBeanServer.

## 17. Inspecting the List of Autodetected MBeans

Do not rely only on an “exporter initialized” message. Query the real MBeanServer:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class DiscoveredMBeansDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName pattern = new ObjectName(
                "com.example.shop.*:*");

        Set<ObjectName> names =
                server.queryNames(pattern, null);

        names.stream()
                .map(ObjectName::getCanonicalName)
                .sorted()
                .forEach(System.out::println);
    }
}
```

The code above assumes the exporter registers into the platform MBeanServer; if there is a custom server, you must use the exporter's actual server.

The pattern `com.example.shop.*:*` matches domains starting with `com.example.shop.`. It **does not** include the exact domain `com.example.shop`; if the system uses both styles, query separately or standardize naming.

Reading an MBean's metadata:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

ObjectName name = new ObjectName(
    "com.example.shop.orders:type=Queue,name=outbox");

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("Attribute: " + attribute.getName());
}
for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
```

Verify all of the following:

- Intended beans appear.
- Unintended internal beans **do not** appear.
- Exposed attributes/operations are accurate.
- ObjectNames follow convention.
- No duplicate exporters, registration errors, or abnormal bean lifecycles exist.

## 18. Integration Tests for Autodetection

With a Spring integration test, you can start a context containing:

- One `@ManagedResource` bean permitted for export.
- One `@Component` without resource annotations.
- An `AUTODETECT_ASSEMBLER` exporter and appropriate assembler.
- A dedicated MBeanServer for the test to avoid affecting process-wide JMX.

Conditions to assert:

```text
Expected:
  com.example.shop.orders:type=Queue,name=outbox
  isRegistered = true

Not expected:
  com.example.shop.internal:type=Repository,name=main
  isRegistered = false
```

If you want to verify programmatically:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxAssertions {

    public static void assertRegistered(
            MBeanServer server, String name) throws Exception {
        if (!server.isRegistered(new ObjectName(name))) {
            throw new AssertionError("Missing MBean: " + name);
        }
    }

    public static void assertNotRegistered(
            MBeanServer server, String name) throws Exception {
        if (server.isRegistered(new ObjectName(name))) {
            throw new AssertionError("Unexpected MBean: " + name);
        }
    }
}
```

In a real project, integrate JUnit 5/Spring Test and obtain the MBeanServer directly from the test context. A test that only checks that the intended bean is exported is not enough; you must also test **not accidentally exposing** internal services.

## 19. Lifecycle, Duplicate Registrations, and Other Exporters

Several common errors when enabling autodetection:

### 19.1. Duplicate ObjectName Registration

```text
Annotation exporter -------+
                           +--> same ObjectName
Manual MBeanExporter ------+
```

If two exporters both register the same ObjectName on the same MBeanServer, `InstanceAlreadyExistsException` can occur. Spring registration policies can handle existing entries in different ways, but they should not be used to mask unclear export ownership design.

**Recommendation:** Each MBean has one registration owner. If other auto-configuration exists, understand whether it already created an exporter before adding a manual exporter.

### 19.2. Bean Not Registered in ApplicationContext

`@ManagedResource` on an object created with `new` outside the Spring context does not make the exporter automatically find that object. The object must be supplied to the exporter or be a Spring bean scanned within the autodetection scope.

### 19.3. Bean Appears Before Being Ready

Autodetection/registration usually occurs during exporter and context initialization lifecycle. If a management getter accesses a component that is not ready yet, it can cause runtime errors. Design attributes that reflect initialization state, and avoid having JMX getters block or initialize heavy resources.

### 19.4. Autodetection on Infrastructure Beans

Do not try to auto-export every bean. Components such as `DataSource`, repositories, serializers, security managers, and client wrappers can have many public methods that are not a public management contract. Use resource annotations or policy-based explicit mapping to narrow the scope.

## 20. Notes on Spring Boot and Auto-Configuration

Spring Boot provides various management utilities, such as Actuator endpoints and the ability to expose management via JMX depending on configuration. Distinguish:

- Spring Framework JMX exporter for custom beans bearing `@ManagedResource`.
- Spring Boot Actuator endpoints that can be exposed via JMX depending on configuration.
- JVM platform MBeans such as `java.lang:type=Memory`, which are standard JVM MBeans.
- Micrometer metrics and Actuator metric endpoints, which are a related instrumentation and exposure mechanism, not synonymous with assembler autodetection.

When an application uses Boot, **do not manually create an additional AnnotationMBeanExporter** just because you see annotations without first knowing what export mechanism Boot already configured. Inspect the effective configuration and actual MBeanServer.

A configuration or dependency change can activate another exporter, causing ObjectName conflicts. Integration tests starting with the right Spring profile help detect differences between local/staging/production.

## 21. Common Misconceptions

| Misconception | Explanation |
|---|---|
| “Assembler autodetect exports every bean.” | Only beans matching the criteria of an autodetect-capable assembler |
| “Having `@ManagedAttribute` means the class is automatically detected.” | With common metadata assemblers, resource-level `@ManagedResource` is the primary marker |
| “Assembler only builds method names, not bean selection.” | `AutodetectCapableMBeanInfoAssembler` can decide inclusion |
| “The bean name is the ObjectName.” | They are two different namespaces; the naming strategy determines JMX identity |
| “Autodetection is security.” | It only selects resources; authorization/TLS must be configured separately |
| “Since the MBean has attributes, export must be right.” | You must verify ObjectName, operations, descriptions, and scope as well |
| “Using `AUTODETECT_ALL` is always more convenient.” | Broader scope can expose unintended resources |
| “You can enable multiple exporters at once without checking.” | ObjectNames can collide and behavior depends on registration policy |
| “`@ManagedResource` works automatically on non-bean classes.” | The exporter only knows objects within its scope |
| “A proxy always preserves annotations just like the original class.” | Metadata lookup and method exposure depend on the proxy/assembler |

## 22. Practice Exercises

### Exercise 1 — Predict Selected Beans

Given three Spring beans:

```java
@Component
@ManagedResource(objectName =
    "com.example.shop:type=Cache,name=products")
class ProductCacheManagement {
    @ManagedAttribute
    public int getEntryCount() { return 10; }
}

@Component
class InternalRepository {
    public int countRows() { return 100; }
}

@Component
class WorkerState {
    @ManagedAttribute
    public int getActiveCount() { return 3; }
}
```

With `AUTODETECT_ASSEMBLER` using `MetadataMBeanInfoAssembler` and `AnnotationJmxAttributeSource`, predict which bean is selected and explain the role of `@ManagedResource`.

**Guided answer:** `ProductCacheManagement` has resource metadata. `InternalRepository` has no JMX annotations. `WorkerState` only has a method-level annotation without a resource annotation, so it does not satisfy the common inclusion condition based on managed resource metadata.

### Exercise 2 — Write a Test Preventing Accidental Export

Start a Spring test context with one management bean and one internal service. Write assertions:

- Management ObjectName is registered.
- Internal ObjectName does not appear.
- MBeanInfo contains only the operations that are actually annotated.

Investigate test failures by checking the mode, assembler, and attribute source before changing component scanning.

### Exercise 3 — Distinguish Two Modes

Create a Standard MBean with a `SampleMonitorMBean` interface and an annotation-based `@ManagedResource` MBean.

Run two separate Spring contexts:

- Context A uses `AUTODETECT_MBEAN`.
- Context B uses `AUTODETECT_ASSEMBLER` with a metadata assembler.

Compare ObjectNames and MBeanInfo. Do not register both contexts into the same server with the same ObjectName without conflict control.

### Exercise 4 — Add a Bean-Name Policy

Build a custom assembler that only accepts beans with the `Management` suffix that also have managed-resource metadata. Test one valid bean and one excluded bean. Discuss drawbacks when bean names change due to refactoring or `@Bean` method naming.

### Exercise 5 — Proxy and Annotation Error

Add `@Transactional` to a service with JMX annotations, causing it to potentially be proxied. Use `AopUtils` to inspect the runtime type and target class. Then check MBeanInfo. If metadata is missing or invocation fails, create a separate management adapter instead of arbitrarily trying to unwrap the target.

## 23. Self-Check Questions

**1. What is `AUTODETECT_ASSEMBLER` used for?**

To let the exporter evaluate Spring beans according to the criteria of an autodetect-capable assembler, rather than only automatically recognizing Standard/Dynamic MBeans.

**2. How does `MetadataMBeanInfoAssembler` work with annotations?**

It uses a `JmxAttributeSource` (such as `AnnotationJmxAttributeSource`) to read managed-resource/method metadata and build MBeanInfo, while also supporting the corresponding inclusion criteria.

**3. Is placing `@ManagedAttribute` on a getter enough for a bean to be autodetected?**

It should not be considered enough. With commonly used annotation metadata discovery, resource metadata such as `@ManagedResource` on the class is required.

**4. Is `setBeans` a mandatory limiting list for autodetection?**

No. Explicit registration and autodetection can be two selection paths; you must inspect the actual exporter configuration.

**5. Why must you also check beans that should not be exported?**

Because accidentally exposing internal services or sensitive operations can create risks and make the operational API difficult to manage.

**6. If the exporter finds the bean but the ObjectName is wrong, is autodetection completely correct?**

Not yet. Discovery is only one step; naming and registration must also match the management contract.

**7. Should you enable `AUTODETECT_ALL` without observing the bean scope?**

No. You need to understand which MBeans and resources might be selected, then verify the runtime results.

## 24. Takeaways

- **Assembler-based autodetection** is the ability of `MBeanExporter` to select Spring beans based on `AutodetectCapableMBeanInfoAssembler.includeBean(...)`.
- For annotation-driven JMX, `MetadataMBeanInfoAssembler` and `AnnotationJmxAttributeSource` are the common pair used to read `@ManagedResource` and `@Managed...` methods.
- `@ManagedResource` expresses resource intent; `@ManagedAttribute`/`@ManagedOperation` express the MBean's API surface.
- `AUTODETECT_ASSEMBLER` differs from `AUTODETECT_MBEAN`; `AUTODETECT_ALL` can combine scopes and requires verification.
- Autodetection is neither a security allowlist nor a guarantee of correct ObjectNames. A consistent export owner and naming strategy are required.
- Spring AOP proxies, auto-export configurations, and bean lifecycles can affect discovery/invocation.
- Inspect the actual `MBeanServer` and `MBeanInfo`, both for intended resources and for beans that must not appear.
- When tight scope control is needed or there are few MBeans, explicit export remains a sound choice.

## 25. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `AutodetectCapableMBeanInfoAssembler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/AutodetectCapableMBeanInfoAssembler.html
- Spring Framework Javadoc — `MetadataMBeanInfoAssembler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — `AnnotationJmxAttributeSource`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
