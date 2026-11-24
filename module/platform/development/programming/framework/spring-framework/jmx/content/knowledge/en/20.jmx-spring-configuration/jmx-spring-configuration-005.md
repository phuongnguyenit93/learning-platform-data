# Integrating MBeanExporter with Existing Bean Configuration in Spring Framework

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain how **`MBeanExporter`** exposes Spring beans already present in the `ApplicationContext` to JMX without recreating business objects.
- Distinguish **bean definition**, **management interface**, **ObjectName**, **MBeanServer**, **exporter**, and **Spring bean lifecycle**.
- Integrate the exporter into Java `@Configuration`, `@Bean`, component scanning, XML, and Spring Boot configurations where appropriate.
- Choose between `setBeans(...)` (explicit registration) and annotation-based autodetection.
- Avoid creating multiple MBeanExporters exporting the same bean or registering two MBeans with the same ObjectName.
- Know how to configure `MBeanServer`, naming strategy, metadata assembler, and registration policy while preserving the Spring beans in use.
- Handle AOP proxies and choose a small management adapter to avoid exposing an entire business service.
- Verify technically using `MBeanServer.isRegistered`, `getAttribute`, `getMBeanInfo`, and integration tests.

## 2. The Problem: The Application Already Has Beans, Now It Needs JMX

A Spring application typically already has a complete bean configuration system:

```text
ApplicationContext
├── orderService
├── orderRepository
├── paymentClient
├── cacheService
├── taskExecutor
└── orderStatistics
```

Suppose the operations team wants to view `PendingOrders` and `ProcessedOrders` via JConsole, while also allowing resetting a monitoring-only counter. You should not create a **second service** solely for JMX registration.

Instead:

```text
                 ApplicationContext
                        |
        +---------------+----------------+
        |                                |
        v                                v
    orderService                   orderStatistics
        |                                |
        +----------------+---------------+
                         |
                         v
                OrderManagement
                         |
                         v
                   MBeanExporter
                         |
                         v
                     MBeanServer
                         |
                         v
             JConsole / JMX client
```

The Spring bean `OrderManagement` is an adapter to expose a small management contract. `MBeanExporter` registers this adapter under an ObjectName. The business service/repository continues using its existing configuration, dependency injection, transactions, and lifecycle.

**Core idea:** JMX integration is an **additional management layer** over existing beans, not a second Spring application or an uncontrolled separate lifecycle.

## 3. Concepts That Must Be Kept Separate

| Concept | Responsibility | Example |
|---|---|---|
| **Spring bean** | Object created, injected, and lifecycle-managed by the IoC container | `orderStatistics` |
| **Bean name** | Identifier in `ApplicationContext` | `orderManagement` |
| **Management interface** | Contract for JMX attributes/operations | `OrderMonitorMBean` |
| **ObjectName** | JMX identifier in `MBeanServer` | `com.example.shop.orders:type=Monitor,name=primary` |
| **MBeanExporter** | Takes beans and registers them into JMX | `setBeans(...)` |
| **MBeanServer** | Runtime registry and access API | `ManagementFactory.getPlatformMBeanServer()` |
| **JMX client** | Reads attributes, invokes operations, receives notifications | JConsole |

A Spring bean name **does not automatically equal** an ObjectName. Bean names can be used to select beans to export, but the JMX identifier must be produced by a naming strategy or declared explicitly.

```text
Spring:
  bean name = orderManagement

JMX:
  ObjectName = com.example.shop.orders:type=Monitor,name=primary
```

The two identifiers serve two different systems. An ObjectName only needs to be unique within one MBeanServer; two independent JVMs can have the same ObjectName.

## 4. Approach: Export an Existing Bean Directly or Create a Management Adapter?

There are two common implementation approaches.

### 4.1. Directly export an existing bean

If a bean has a clear and suitable management interface, it can be exported directly:

```java
public interface QueueMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}

public class QueueMonitor implements QueueMonitorMBean {
    private int pendingCount;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void resetStatistics() {
        pendingCount = 0;
    }
}
```

When this is a Spring bean, the exporter can register it under an ObjectName.

Advantage: fewer wrappers, simple if the bean only has management responsibilities.

Disadvantage: if the bean is a large business service with many AOP aspects or public methods, the JMX contract can become tightly coupled to the business implementation.

### 4.2. Create a management adapter built on existing beans

```java
public interface OrderStatisticsService {
    long pendingOrders();
    long processedOrders();
}
```

```java
import org.springframework.stereotype.Component;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Monitor,name=primary",
    description = "Order processing statistics")
public class OrderManagement {

    private final OrderStatisticsService statistics;

    public OrderManagement(OrderStatisticsService statistics) {
        this.statistics = statistics;
    }

    @ManagedAttribute(description = "Current pending orders")
    public long getPendingOrders() {
        return statistics.pendingOrders();
    }

    @ManagedAttribute(description = "Total processed orders")
    public long getProcessedOrders() {
        return statistics.processedOrders();
    }
}
```

An adapter lets you maintain a **deliberate management surface**, without exposing repositories or other service methods via JMX.

**Warning:** Annotations only declare metadata; you still need an annotation-aware exporter and the bean must reside in the ApplicationContext.

## 5. Combining MBeanExporter with Java @Configuration

Suppose the project already has a `QueueMonitor` bean conforming to Standard MBean rules:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CoreConfiguration {

    @Bean
    QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }
}
```

Add a separate exporter configuration **without recreating `QueueMonitor`**:

```java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxConfiguration {

    @Bean
    MBeanExporter queueExporter(QueueMonitor queueMonitor) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "com.example.shop.orders:type=QueueMonitor,name=primary",
            queueMonitor));

        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING);

        return exporter;
    }
}
```

This flow:

1. Spring creates `queueMonitor` once under the default singleton scope.
2. Dependency injection passes that exact bean into the `queueExporter` factory method.
3. `MBeanExporter` uses this bean for JMX registration.
4. Other components can still inject `QueueMonitor`.
5. MBeanServer and JMX clients interact with the registered MBean.

Do not write `new QueueMonitor()` once in `@Bean` and a second time inside `setBeans`, because you would manage two different objects with two different states.

## 6. Preserving the Spring Bean Lifecycle

The Spring IoC container typically manages:

- Constructor injection and `@PostConstruct`.
- `InitializingBean` or custom init methods.
- AOP post-processors.
- Bean scopes.
- `@PreDestroy`, `DisposableBean`, or destroy methods.

The exporter should not become a reason to bypass those mechanisms.

Example to avoid:

```java
@Bean
MBeanExporter exporter() {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "com.example.shop:type=QueueMonitor,name=main",
        new QueueMonitor()));
    return exporter;
}
```

Here `QueueMonitor` is instantiated with `new` inside the exporter configuration, instead of being injected as an independently managed Spring bean. In many cases this loses desired configuration and lifecycle benefits.

Proper approach:

```java
@Bean
MBeanExporter exporter(QueueMonitor monitor) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "com.example.shop:type=QueueMonitor,name=main",
        monitor));
    return exporter;
}
```

**Note:** If a bean's scope is prototype or request-scoped, exporting a single specific object may not reflect the scope's expectations. With JMX, it is usually better to have a singleton management adapter holding references to appropriate services/proxies, or explicitly designed to represent the whole component.

## 7. MBeanServer: Using the Right Configured Server

An application may have an MBeanServer discovered by Spring or configured separately. `MBeanExporter` can use an injected MBeanServer.

Example:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MBeanServerConfiguration {

    @Bean
    MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
```

Exporter:

```java
@Bean
MBeanExporter exporter(
        MBeanServer mBeanServer,
        QueueMonitor monitor) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(mBeanServer);
    exporter.setBeans(Map.of(
        "com.example.shop.orders:type=QueueMonitor,name=primary",
        monitor));
    return exporter;
}
```

Using the platform MBeanServer is suitable when you want application MBeans to appear alongside JVM platform MBeans like `java.lang:type=Memory`. However, do not create an extra server arbitrarily if JConsole or other exporters are connecting to a different server.

When verifying, use **the same MBeanServer instance** that the exporter uses.

## 8. Interface-Based Config and Proxies: A Common Pitfall

In many applications, business services have `@Transactional`, `@Cacheable`, or security advice, so the actual injected object may be a Spring AOP proxy.

Suppose:

```java
public interface OrderService {
    long pendingOrders();
}
```

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DefaultOrderService implements OrderService {

    @Override
    @Transactional(readOnly = true)
    public long pendingOrders() {
        return 12;
    }
}
```

If Spring uses a JDK dynamic proxy, the object injected via `OrderService` is not necessarily of type `DefaultOrderService`.

**Recommendation:** Have the management adapter accept the business interface:

```java
@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=main")
public class OrderManagement {

    private final OrderService orderService;

    public OrderManagement(OrderService orderService) {
        this.orderService = orderService;
    }

    @ManagedAttribute
    public long getPendingOrders() {
        return orderService.pendingOrders();
    }
}
```

This way the JMX adapter calls through the service's Spring proxy, preserving transaction/security/cache behavior when needed.

However, a JMX getter can be polled continuously. If `orderService.pendingOrders()` runs SQL every time, it can create DB load. Prefer lightweight snapshots/counters or design a controlled refresh.

## 9. Annotated Beans and Assembler: Choosing the Right Export Mechanism

If a management bean is annotated:

```java
@Component
@ManagedResource(
    objectName = "com.example.shop.catalog:type=Cache,name=products")
public class ProductCacheManagement {

    @ManagedAttribute
    public int getEntryCount() {
        return 42;
    }
}
```

then you need an exporter/assembler that understands `@ManagedResource` and `@ManagedAttribute`.

Common components:

- `AnnotationJmxAttributeSource`: reads annotation metadata.
- `MetadataMBeanInfoAssembler`: creates MBeanInfo from metadata.
- `MetadataNamingStrategy`: reads names from managed resource metadata.
- `MBeanExporter`: performs the export.
- `AnnotationMBeanExporter`: a convenience utility suited for annotation-driven export.

**Important:** Do not simply add annotations to a bean, create a default `MBeanExporter`, and assume annotations are definitely processed as desired. Check how the exporter is configured in the Spring version you are using.

### Configuring an explicit metadata pipeline

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class AnnotationJmxConfig {

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
        MetadataNamingStrategy naming =
                new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter annotationExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
        return exporter;
    }
}
```

The configuration above illustrates wiring the pipeline to select managed resources. Check the exact APIs for your Spring version; if the application already has an annotation-driven exporter, **do not create a second exporter** just because you saw this example.

## 10. Explicit Export vs. Autodetection: Avoiding Overlap

Two paths are commonly used:

### Approach A: explicit mapping

```java
exporter.setBeans(Map.of(
    "com.example.shop.orders:type=Queue,name=outbox",
    orderManagement));
```

Suitable when the number of resources is small, a strict allowlist is needed, and naming is controlled by configuration.

### Approach B: autodetection

```java
exporter.setAssembler(metadataAssembler);
exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
```

Suitable when modules have consistent JMX annotations and you want the exporter to discover them automatically.

If both explicit mapping and autodetection are enabled, understand whether the same bean can be selected twice or if duplicate ObjectNames can be generated in that version/configuration. Avoid running two parallel registration paths for the same MBean.

**Ownership rule:** Each `ObjectName` should have **one registration owner** and one primary source of management metadata.

## 11. Do Not Confuse MBeanExporter with MBeanProxyFactoryBean

In Spring JMX there are two directions:

```text
SERVER SIDE:
Spring bean -> MBeanExporter -> MBeanServer

CLIENT SIDE:
Spring bean proxy -> MBeanProxyFactoryBean -> MBeanServerConnection
```

`MBeanExporter` **exposes** beans.

`MBeanProxyFactoryBean` **creates a client proxy** to call an already-registered MBean.

If the same application needs to call a local MBean via a Java interface, a client proxy can be used, but you do not need to create a client proxy just to export a bean. The two tools have different roles.

Some applications already inject Java services directly, so there is no need to go through a JMX proxy for internal business calls. Use a JMX proxy when you want to interact with a **management contract** through MBeanServer and ObjectName, not as a replacement for normal dependency injection.

## 12. Registration Policy: Do Not Mask Configuration Conflicts

When two exporters or two resources register the same ObjectName, `InstanceAlreadyExistsException` can occur. Spring supports `RegistrationPolicy` to control conflicts.

| Policy | When ObjectName Already Exists | Risk / Advantage |
|---|---|---|
| `FAIL_ON_EXISTING` | Reports conflict | Easy to catch misconfiguration |
| `IGNORE_EXISTING` | Keeps existing MBean, skips replacement | New bean may not be exported as expected |
| `REPLACE_EXISTING` | Replaces existing MBean | May cause disruption and lose the old contract |

In initial integration configurations, **`FAIL_ON_EXISTING`** is usually the safest choice for predictability because it catches duplicate exports.

Do not switch to `IGNORE_EXISTING` merely to make the app start up; JConsole might still be reading another exporter's MBean. Do not pick `REPLACE_EXISTING` just to "win" the conflict, as it could replace a library/container MBean that the application does not own.

## 13. Spring Boot: Check Auto-Configuration Before Adding an Exporter

In Spring Boot, JMX/Actuator integration varies depending on configuration and dependencies:

- JVM platform MBeans are always accessible via the platform MBeanServer.
- Custom `@ManagedResource` beans need an appropriate export mechanism.
- Spring Boot Actuator endpoints can be exposed over JMX according to management configuration.
- Libraries may register MBeans themselves, such as a connection pool.

Therefore, before creating a custom `MBeanExporter`, verify:

1. Does the application already have an exporter from auto-configuration?
2. Is `spring.jmx.enabled` or equivalent JMX properties enabled for the Spring Boot version in use?
3. Is there already a bean named `mbeanExporter` or a custom exporter?
4. Does Actuator JMX exposure use the same MBeanServer?
5. Could custom domains/ObjectNames collide with Spring/Actuator or libraries?

Illustrative configuration:

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include: health,info
```

Exact configuration depends on the Spring Boot version and dependencies. Do not treat this YAML example as mandatory for plain Spring Framework applications.

When Boot already provides a valid exporter, leverage that configuration or reconfigure the existing owner rather than adding another exporter with overlapping scope.

## 14. Organizing Configuration by Module

In a multi-module application, you can separate concerns:

```text
com.example.shop
  ├── orders
  │   ├── OrdersConfiguration.java
  │   └── OrderManagement.java
  ├── catalog
  │   ├── CatalogConfiguration.java
  │   └── CacheManagement.java
  └── jmx
      └── JmxConfiguration.java
```

Organization structure:

- Business configurations create services/repositories as before.
- Management adapters inject those services.
- One application-level JMX configuration defines the exporter, naming, policy, and MBeanServer.
- If a module needs to declare its own JMX beans, it provides adapters/metadata, without automatically creating a second exporter if the app already has a shared exporter.

Example:

```java
@Configuration
public class OrderModuleConfiguration {
    @Bean
    OrderStatistics orderStatistics() {
        return new OrderStatistics();
    }
}

@Configuration
public class MonitoringConfiguration {
    @Bean
    OrderManagement orderManagement(OrderStatistics statistics) {
        return new OrderManagement(statistics);
    }
}
```

This example assumes `OrderManagement` has a matching constructor accepting `OrderStatistics`. If `OrderManagement` already has `@Component` and component scanning is active, do not inadvertently declare an extra `@Bean` for the same role.

Practical rule: **one primary creation source per bean** (component scanning or explicit `@Bean`, unless multiple instances are intended); **one exporter owner per ObjectName**.

## 15. What Happens with Singleton, Prototype, and Scoped Proxies?

### Singleton

Spring singleton is the default scope and is usually the best fit for management MBeans. The exporter registers the instance managed in the ApplicationContext.

### Prototype

A prototype bean is created on each bean lookup. If the exporter receives one specific prototype instance, JMX clients interact only with that registered instance, not representing all other prototype objects. This can make observed metrics differ from expectations.

### Request/session scope

A request-scoped bean is not a natural choice for an MBean that lives for the lifetime of the JVM. If using a scoped proxy, JMX calls from threads without a request context may fail.

### Singleton management adapter

Usually safer for overall management: a singleton adapter reads counters/snapshots from services or a metrics registry. Still, clearly define which instance the data belongs to, especially when the system has multiple replicas.

## 16. Limitations of @ManagedAttribute Getters

An MBean being exported successfully does not mean all getters are safe for polling.

Example to examine:

```java
@ManagedAttribute
public long getPendingOrders() {
    return repository.countPendingOrders();
}
```

JConsole or an exporter may invoke the attribute repeatedly, generating repeated SQL queries. If the DB is under pressure, monitoring itself adds more load.

Lower-risk approach:

```java
@ManagedAttribute
public long getPendingOrders() {
    return statistics.getPendingSnapshot();
}
```

Values refreshed in the background should include timestamp/freshness metadata so operators know when data is stale.

For state-changing operations such as `clearCache`, `pauseConsumers`, and `resetStatistics`, consider authorization, auditing, and side effects. `@ManagedOperation` does not implicitly apply business security roles.

## 17. Verifying the Registered ObjectName

After the context starts, you can inspect the MBean via MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.shop.orders:type=QueueMonitor,name=primary");

boolean exists = server.isRegistered(name);
System.out.println("Registered: " + exists);
```

If the exporter uses a different MBeanServer, use that exact instance. Having a client look up the ObjectName on a different server will return `false` even when registration on the target server succeeded.

Reading an attribute:

```java
if (server.isRegistered(name)) {
    Object pending =
            server.getAttribute(name, "PendingCount");
    System.out.println("Pending: " + pending);
}
```

This is an end-to-end check of the JMX getter, not merely confirming that the Spring bean exists.

## 18. Checking the Contract via MBeanInfo

A reliable way to see what clients receive:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf("ATTRIBUTE %s type=%s readable=%s%n",
            attr.getName(), attr.getType(), attr.isReadable());
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("OPERATION " + op.getName());
}
```

Verify:

- Does `PendingCount` have the right name and data type?
- Are read-only/writable semantics correct?
- Are internal operations accidentally exposed?
- Does the ObjectName follow the naming convention?
- Are annotation attributes processed by the assembler?
- Are there any registration conflicts or duplicate owners?

MBeanInfo is **the contract observed by JMX clients**, so it is more valuable than just looking at annotations in source code.

## 19. A Minimal Integration Test

When the application has Spring Test/JUnit 5, you can start a context containing only core beans and the exporter.

Test-oriented example:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import javax.management.MBeanServer;
import javax.management.ObjectName;

class JmxExportIntegrationTest {

    private final MBeanServer mbeanServer;
    // In real tests inject MBeanServer and the Spring context.

    JmxExportIntegrationTest(MBeanServer mbeanServer) {
        this.mbeanServer = mbeanServer;
    }

    @Test
    void exportsExpectedQueueMonitor() throws Exception {
        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=QueueMonitor,name=primary");

        assertTrue(mbeanServer.isRegistered(name));

        Object pending = mbeanServer.getAttribute(name, "PendingCount");
        assertNotNull(pending);
    }
}
```

This is a **conceptual template**. With JUnit 5 and Spring Test, perform constructor injection via the proper test context mechanism (for example `@SpringJUnitConfig` and autowiring setup) or use explicit field injection. The snippet is not a standalone runnable test class without test configuration.

Use a dedicated test MBeanServer so you do not affect other tests in the same JVM. Clean up registrations when closing the context to avoid conflicts across test suites.

### Assertions to include

1. Expected MBeans are present.
2. Unwanted MBeans are not exported.
3. Attributes have the expected types/values.
4. Operation surface is accurate and does not accidentally expose internal methods.
5. The exporter does not register duplicates.
6. Context shutdown removes registrations owned by this owner.
7. AOP proxies are handled properly if services have transactions/caching.

## 20. Lifecycle Issues on Context Shutdown and Restart

`MBeanExporter` can manage unregistering the MBeans it registered when the context stops. When multiple contexts/exporters share an MBeanServer and ObjectName, the lifecycle becomes unpredictable:

```text
Context A register -> MBean X
Context B register -> conflict/ignore/replace
Context A close    -> who owns the current registration?
```

Therefore:

- Do not use registration policies to mask unclear ownership.
- Use one exporter owner per ObjectName.
- Test closing and reopening contexts.
- Do not manually unregister MBeans managed by another component.
- If a container creates system MBeans, respect the container's lifecycle.
- With hot reload/devtools, check for leftover registrations and how context cleanup behaves.

If you need to swap implementations while keeping the ObjectName, design a stable management facade or controlled migration instead of defaulting to `REPLACE_EXISTING`.

## 21. Combining the Exporter with Existing XML Configuration

Spring Framework still supports XML bean definitions in legacy systems. The concept is the same as Java configuration: keep existing bean definitions and add an exporter referencing beans by name.

Example:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="queueMonitor" class="com.example.shop.QueueMonitor"/>

    <bean id="exporter"
          class="org.springframework.jmx.export.MBeanExporter">
        <property name="beans">
            <map>
                <entry key="com.example.shop.orders:type=QueueMonitor,name=primary"
                       value-ref="queueMonitor"/>
            </map>
        </property>
    </bean>
</beans>
```

In XML, `value-ref="queueMonitor"` is a reference to the already-declared Spring bean; it does not create a new object.

If the project already uses the `context:mbean-export` namespace or a similar annotation exporter configuration, understand the current scope before declaring an extra manual `MBeanExporter`, avoiding two registration owners.

## 22. Choosing Between Java Configuration and XML

| Criterion | Java `@Configuration` | XML bean definitions |
|---|---|---|
| Declaration style | Type-safe Java methods and annotations | XML elements, bean references |
| Reusing beans | Constructor/parameter injection | `ref`/`value-ref` |
| Setting ObjectName | Map keys, naming strategy, annotations | Map keys, bean properties, namespace |
| Testing | Spring context with config classes | Spring context with XML resources |
| Risks | Instantiating new beans inside exporter or duplicate `@Component` | Wrong bean id, adding duplicate exporter |
| Interoperability | Can coexist in one context | Can be imported/composed with Java config |

Choose based on the project's existing architecture; you do not have to rewrite all XML to Java just to add JMX. More important is **creating beans once and having a single export owner**.

## 23. Common Mistakes

| Issue | Cause | How to Fix |
|---|---|---|
| MBean reads different state than application | Exporter calls `new` on a different object than the active bean | Inject the Spring-managed instance |
| `InstanceAlreadyExistsException` | Two exporters/beans use the same ObjectName | Use one owner, fix naming or configuration |
| Annotations do not appear | Exporter lacks annotation assembler/source | Configure the metadata pipeline properly |
| `NotCompliantMBeanException` | Bean/proxy does not satisfy the MBean contract | Use Standard MBean, MXBean, or a suitable adapter |
| Getter queries DB on every read | Attribute reads directly from repository | Use lightweight counters/snapshots |
| MBean not visible in JConsole | Wrong MBeanServer or not exported | Check server, ObjectName, startup logs |
| Wrong ObjectName | Bean name confused with ObjectName | Use a naming strategy or explicit mapping |
| Actuator and custom exporter collide | Auto-configuration plus manual exporter | Consolidate to a single registration owner |
| Inappropriate scope | Prototype/request bean exported | Use a singleton adapter |
| Tests interfere with each other | Contexts share the platform MBeanServer | Use dedicated test servers and cleanup |

## 24. A Controlled Integration Workflow

### Step 1: Identify management requirements

List attributes/operations operators truly need. Do not export entire services/repositories.

### Step 2: Choose the managed object

- If an existing bean is a valid Standard/MXBean with a small API: export directly.
- If the business bean is complex or heavily AOP-wrapped: create a singleton management adapter.

### Step 3: Choose the metadata source

- Standard MBean interface.
- MXBean interface.
- Annotation-driven `@Managed...` and assembler.

Do not rely on multiple sources merging consistently on their own.

### Step 4: Choose exporter and naming

One exporter owner and an ObjectName following convention:

```text
com.example.shop.orders:type=OrderMonitor,name=primary
```

### Step 5: Link existing beans

Use constructor injection or `value-ref`; do not instantiate new business objects inside the exporter.

### Step 6: Configure registration policy

Prefer catching conflicts in test/staging environments; use ignore/replace only with clear rationale and lifecycle management.

### Step 7: Verify at runtime

Inspect `MBeanServer`, `MBeanInfo`, attributes, and operation visibility. Also test that unintended elements are not exported.

### Step 8: Check safety

Restrict remote JMX access, control operations with side effects, avoid secrets in ObjectNames/attributes, and keep getters low-cost.

### Step 9: Verify shutdown/restart

Ensure the exporter cleans up registrations owned by its owner without deleting third-party MBeans.

## 25. Practice Exercises

### Exercise 1 — Do not create a second bean

A project has:

```java
@Bean
QueueMonitor queueMonitor() {
    return new QueueMonitor();
}
```

Write an `@Bean MBeanExporter` taking `QueueMonitor` as a parameter and exporting it under ObjectName `com.example.shop:type=QueueMonitor,name=main`. Explain why `new QueueMonitor()` inside the exporter is wrong for shared state.

### Exercise 2 — Adapter vs. direct export

Service `OrderServiceImpl` has `@Transactional`, many public methods, and database access. You need to expose `PendingOrders` and `LastProcessingErrorCode`.

Design a singleton `OrderManagement` with two small getters reading snapshots/counters maintained by the service. Explain why not to export all of `OrderServiceImpl`.

### Exercise 3 — Reading metadata

Register `QueueMonitor`, then use `MBeanServer.getMBeanInfo` to print all attributes/operations. Confirm `PendingCount` is exposed as read-only and internal APIs do not appear.

### Exercise 4 — Annotation-aware configuration

A `@Component` has `@ManagedResource` and `@ManagedAttribute`, yet JConsole does not see the MBean. Check hypotheses in order: whether the bean is in the context; whether the exporter ran; whether the assembler understands annotations; whether the naming strategy chose the right ObjectName; whether the MBeanServer is correct.

### Exercise 5 — Testing duplicate exporters

Intentionally declare two exporters for the same `ObjectName` in a test context. With `FAIL_ON_EXISTING`, observe the conflict. Then fix the architecture to use a single exporter owner, without using `IGNORE_EXISTING` to hide the error.

### Exercise 6 — Migrating XML configuration

Given an XML already declaring bean `queueMonitor`, add an `MBeanExporter` using `value-ref` to the existing bean. Read an attribute via JConsole or a Java client and verify the data comes from the exact same instance.

## 26. Self-Check Questions

**1. Why shouldn't you recreate a service with `new` inside MBeanExporter configuration?**

Because it would create a different object from the bean used by business logic, leading to inconsistent state and lifecycle.

**2. Does a bean with `@ManagedResource` appear automatically in JConsole?**

No. It must be managed by Spring and exported via an annotation-aware mechanism to the appropriate MBeanServer.

**3. Do `MBeanExporter` and `MBeanProxyFactoryBean` do the same job?**

No. The exporter registers MBeans; the proxy factory creates client proxies to invoke already-registered MBeans.

**4. Is a Spring bean name an ObjectName?**

No. An ObjectName is a JMX identifier and must be determined via mapping/naming strategy/metadata.

**5. When should you create a management adapter?**

When a business service has many internal APIs, heavy AOP advice, or needs a minimal, stable JMX contract.

**6. Why shouldn't you use `IGNORE_EXISTING` by default to bypass duplicate errors?**

Because it can skip the new bean, leave an old MBean with the wrong contract, and mask ownership bugs.

**7. Must you use the exact MBeanServer when verifying?**

Yes. Reading a different server can report the MBean does not exist even though the exporter registered it successfully on the target server.

## 27. Takeaways

- Combining an exporter with Spring configuration means **reusing existing beans**, not creating a second implementation just for JMX registration.
- MBeanExporter takes Spring beans and exposes the management contract to MBeanServer under an ObjectName.
- Pick one clear metadata path: Standard MBean, MXBean, or annotation-driven assembler.
- Spring bean name and JMX ObjectName are two distinct identifiers; keep a stable naming convention.
- Each ObjectName should have one registration owner; avoid overlapping explicit export and autodetection.
- A singleton management adapter helps limit the management API and preserve service AOP/lifecycle.
- With Spring Boot, check auto-configuration before adding a manual exporter.
- Verify with `MBeanInfo`, `getAttribute`, and real tests through MBeanServer; do not rely solely on checking annotations in source code.
- Consider security, getter cost, scope, shutdown, and compatibility with monitoring tools.

## 28. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `AnnotationMBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Spring Framework Reference — Exporting MBeans: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
