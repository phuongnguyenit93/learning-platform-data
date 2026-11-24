# Combining Custom MBeans with Framework Endpoints in Spring Boot

## 1. Objectives and Context

Spring Boot offers several application management mechanisms: **custom JMX MBeans** created by the application team, built-in JVM/framework MBeans, and **Spring Boot Actuator endpoints** that can be published over HTTP or JMX. When combining them, the goal is a clear management system without ObjectName collisions, without unintentionally exposing dangerous functions, and without confusing metrics, endpoints, and operational actions.

This lesson focuses on:

- Distinguishing custom MBeans, JVM MBeans, and Actuator endpoints exposed over JMX.
- Understanding Spring Boot configuration that enables JMX and Actuator exposure.
- Creating a custom management MBean using Spring annotations and observing it alongside framework endpoints.
- Designing conflict-free namespaces/ObjectNames, identifying the right MBeanServer, and clarifying exporter ownership.
- Choosing between custom JMX and Actuator endpoints depending on requirements.
- Checking security, lifecycle, and observability of both layers.

**Version scope:** Illustrative examples use common Spring Framework JMX and Spring Boot Actuator concepts. Auto-configuration details, endpoint lists, and properties can change by Spring Boot version; consult dependencies and documentation for your project's exact version.

## 2. Three Management Data Sources in One JVM

A Spring Boot application can have:

~~~text
Spring Boot application / JVM
    |
    +-- Platform MBeanServer
           |
           +-- java.lang
           |     +-- Memory
           |     +-- Threading
           |     +-- Runtime
           |
           +-- com.example.shop
           |     +-- InventoryCache MBean
           |     +-- BackgroundJobs MBean
           |
           +-- org.springframework.boot
                 +-- Actuator endpoint MBeans (if enabled/exposed)
~~~

These branches are conceptual only; domains and display structures can vary across versions, naming strategies, and JMX clients.

### JVM/platform MXBeans

Provided by the JDK, such as Memory, Threading, ClassLoading, Runtime, and GarbageCollector. They usually appear under domains like `java.lang`.

### Custom application MBeans

Defined by the application to measure or control specific resources: caches, workers, queues, sync state, processing statistics. These can use Standard MBeans, MXBeans, Dynamic/Model MBeans, or Spring `@ManagedResource`.

### Spring Boot Actuator endpoints

Actuator provides a unified management endpoint model. When suitable and exposed, endpoints can be accessed over HTTP or JMX, such as health, info, metrics, or other endpoints depending on dependencies, version, and configuration.

**An Actuator endpoint is not by default a custom MBean.** An endpoint is an Actuator abstraction; the JMX exposure layer can present that endpoint as an MBean for JMX clients to consume.

## 3. Distinguishing MBeans and Actuator Endpoints

| Criterion | Custom MBean | Actuator endpoint |
| --- | --- | --- |
| API model | JMX attributes, operations, notifications | Endpoints, operations, and exposure technologies |
| Identifier | `ObjectName` | Endpoint ID, plus ObjectName rules when over JMX |
| Created with | Standard MBean/MXBean or Spring JMX annotations | Built-in Actuator endpoint or custom `@Endpoint` |
| Access | JMX client | HTTP/JMX depending on exposure |
| JMX specificity | High | Endpoint model is more transport-independent |
| Typical use case | Controlling a specific component, typed MBean contract | Health/info/metrics, convention-based app management |
| Security | JMX connector access + business controls | Technology-specific security: HTTP or JMX |
| Naming | Defined by application/exporter | Defined by Actuator JMX exposure/naming |

If you need a **management API solely for Java/JMX clients**, a custom MBean is a natural choice. If you need the same management concept exposable over multiple technologies, a custom Actuator endpoint may fit better.

Neither choice is automatically safer. Writes and operations require appropriate access restrictions, validation, and auditing.

## 4. Dependencies and Enabling JMX in Spring Boot

In a Maven application with Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Boot supports JMX and a commonly used property:

~~~properties
spring.jmx.enabled=true
~~~

This property controls JMX functionality in the corresponding Boot configuration. In a real project, verify:

- Which Spring Boot version is used.
- Whether the Actuator dependency is present.
- Whether JMX auto-configuration is active.
- Which `MBeanExporter` is actually created.
- Whether any custom exporter registers the same MBean or same ObjectName.
- Which Actuator endpoints are allowed to be exposed over JMX.

**Enabling Spring JMX does not mean enabling a remote JMX connector.** MBeans can exist in the platform MBeanServer and be visible to local JConsole while remote connectivity remains unconfigured.

### Actuator Exposure over JMX

Example property:

~~~properties
management.endpoints.jmx.exposure.include=health,info,metrics
~~~

This property illustrates selecting Actuator endpoints exposed over JMX. Some endpoints may not exist if dependencies are missing or disabled; the include list does not create endpoints that do not exist.

You can use include/exclude according to the rules of your project's Spring Boot version. Do not open all endpoints just to "see everything" if real needs require only a few.

### HTTP Exposure Is a Separate Policy

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoints.jmx.exposure.include=health,info,metrics
~~~

The two settings select endpoints for two different technologies. Being able to access an endpoint over JMX does not mean it automatically appears over HTTP, and vice versa.

## 5. Creating a Custom MBean with Spring Annotations

Example monitoring an application cache:

~~~java
package com.example.shop.management;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop:type=Cache,name=products",
    description = "Product cache management"
)
public class ProductCacheManagement {

    private final AtomicLong hitCount = new AtomicLong();
    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Number of cache hits")
    public long getHitCount() {
        return hitCount.get();
    }

    @ManagedAttribute(description = "Whether cache is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(description = "Reset cache hit statistics")
    public void resetStatistics() {
        hitCount.set(0);
    }

    public void onCacheHit() {
        hitCount.incrementAndGet();
    }
}
~~~

This class illustrates the published attributes/operations:

~~~text
com.example.shop:type=Cache,name=products

Attributes:
  HitCount : long [read-only]
  Enabled  : boolean [read/write]

Operations:
  resetStatistics()
~~~

Only methods published in JMX metadata belong to the management contract. `onCacheHit()` carries no management annotation and is therefore not explicitly published as an operation by the annotation assembler.

This example holds state only inside the bean. Production code should delegate to the real cache/service; toggling a flag that the cache ignores causes JMX to report state that does not reflect actual behavior.

## 6. Ensuring the Annotation MBean Is Actually Exported

`@ManagedResource` only supplies metadata; the bean must be discovered and registered as an MBean by an exporter.

In a pure Spring Framework application, you can declare `AnnotationMBeanExporter`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    static AnnotationMBeanExporter annotationMBeanExporter() {
        return new AnnotationMBeanExporter();
    }
}
~~~

However, in Spring Boot with JMX auto-configuration already active, creating a manual exporter can cause duplicate registrations. **Do not copy the configuration above mechanically** when Boot already creates an exporter.

How to verify in an application:

1. Check the effective JMX properties.
2. Identify existing exporter beans.
3. Read startup logs to spot registration errors.
4. Query the MBeanServer to confirm the custom bean's ObjectName.
5. Inspect in JConsole and verify actual attributes and operations.

If the custom bean does not appear, check component scanning, active profiles, conditional registration, exporter, and naming. Actuator still appearing while the custom bean does not is no proof the custom bean was picked up by an exporter.

## 7. Avoiding ObjectName Collisions with Framework Endpoints

Every MBean is uniquely identified in an MBeanServer. Two beans cannot register under the same ObjectName.

For instance, custom MBeans should use their own namespace:

~~~text
com.example.shop:type=Cache,name=products
com.example.shop:type=Queue,name=payments
com.example.shop:type=Scheduler,name=background
~~~

For Actuator, let the framework manage its domain and naming via its own mechanism rather than placing custom MBeans into the same domain/key convention without a reason.

### Common Mistakes

- A custom MBean hardcodes a name matching a framework endpoint.
- Two exporters use the same domain/type/name.
- Two `ApplicationContext`s in one JVM share an MBeanServer and register colliding names.
- A naming strategy relies on runtime proxy classes instead of logical resources.
- Changing the domain upon deployment prevents dashboards or clients from finding the MBean.

### Recommended Rules

Reserve a stable domain for application MBeans, such as `com.example.shop`, with business-meaningful key properties. Avoid naming based on temporary Java classes or shifting hostnames/ports. Within each JVM, each exported logical resource must have a unique ObjectName.

If multiple JVMs each have their own MBeanServer, sharing the same ObjectName is not a conflict; the monitoring system distinguishes instances at the target layer.

## 8. Reading MBeans in JConsole

After running the application:

1. Open `jconsole` and pick the right JVM.
2. Select the **MBeans** tab.
3. Expand the `java.lang` domain to inspect platform MXBeans.
4. Expand the application's domain such as `com.example.shop` to inspect custom MBeans.
5. Find Spring Boot Actuator's domain per the running version's current naming scheme.
6. Read attributes, operations, and descriptions to confirm the right resource.

An illustrative tree:

~~~text
MBeans
├── java.lang
│   ├── Memory
│   ├── Runtime
│   └── Threading
├── com.example.shop
│   ├── Cache
│   │   └── products
│   └── Queue
│       └── payments
└── org.springframework.boot
    ├── health
    ├── info
    └── metrics
~~~

Node structure is illustrative, not a promise of exact display names across all versions. JConsole may group key properties differently, and Actuator JMX naming can vary.

### Verify by ObjectName Rather Than Only Visual Branches

If JConsole displays an MBean under a different branch than expected, cross-check the **full ObjectName**. The domain in an ObjectName is a JMX namespace, not necessarily the class's Java package.

## 9. Querying Custom MBeans and Framework MBeans in Java

`MBeanServer` allows querying domains:

~~~java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class ListJmxMBeans {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        Set<ObjectName> customNames =
            server.queryNames(
                new ObjectName("com.example.shop:*"),
                null
            );

        for (ObjectName name : customNames) {
            System.out.println(name.getCanonicalName());
        }
    }
}
~~~

Run this code in the **JVM hosting the MBeans**. Running it in another Java process makes `getPlatformMBeanServer()` reference that process's own platform server rather than automatically connecting to the external Spring Boot app.

If a separate `MBeanServer` is used instead of the platform server, inject or obtain the exact server the exporter actually uses.

### Checking a Specific Custom MBean

~~~java
ObjectName name = new ObjectName(
    "com.example.shop:type=Cache,name=products"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "Custom cache MBean is not registered"
    );
}

Object hits = server.getAttribute(name, "HitCount");
System.out.println("HitCount = " + hits);
~~~

This query confirms the MBean is registered and the attribute can be read. If permissions or metadata are invalid, the call can still throw a runtime error.

## 10. Custom Actuator Endpoints as an Alternative to Custom MBeans

When you want a management concept accessible over multiple technologies, you can create a **custom Actuator endpoint**:

~~~java
package com.example.shop.management;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "inventorySummary")
public class InventorySummaryEndpoint {

    private final InventoryService inventoryService;

    public InventorySummaryEndpoint(
            InventoryService inventoryService
    ) {
        this.inventoryService = inventoryService;
    }

    @ReadOperation
    public InventorySummary summary() {
        return inventoryService.currentSummary();
    }
}
~~~

`InventoryService` and `InventorySummary` are illustrative types to be defined in the application. How Actuator converts data types and the compatibility of return types across JMX/HTTP exposure must be evaluated against endpoint requirements and framework version.

Endpoint IDs should follow the naming rules of the Spring Boot version in use. Built-in endpoints also have their own IDs such as `health`, `info`, and `metrics`.

### When Should You Not Create an Actuator Endpoint?

If you simply need a Standard MBean with a typed Java interface already used long-term, switching to an Actuator endpoint can break the ObjectName/attribute/operation contract of legacy clients.

If operations require method overloading, JMX notifications, specific MXBean Open Types, or JMX-only clients, a custom MBean is usually a better fit.

## 11. Do Not Export Two Interfaces for the Same Resource Without a Policy

A resource might be managed simultaneously by:

~~~text
ProductCacheService
      |
      +-- Custom MBean: resetStatistics()
      |
      +-- Actuator endpoint: clearCache()
~~~

This is not inherently wrong. However, answer:

- Do both interfaces read the same state?
- Do operations have different names yet overlapping effects?
- Could two clients invoke them concurrently and cause a race condition?
- Are HTTP and JMX access permissions consistent?
- Is there a shared service enforcing validation and concurrency?
- When an action succeeds, do metrics/health reflect it immediately or with a delay?

### Recommended Design: Shared Management Service

~~~text
                ProductCacheService
                   /          \
                  /            \
          JMX adapter       Actuator endpoint
             |                   |
        JMX connector       HTTP / JMX exposure
~~~

Both adapters should call a central service with a clear state machine and policy. Do not duplicate pause/reset/clear logic across two layers and cause inconsistent outcomes.

## 12. Distinguishing Actuator Metrics from Custom JMX Attributes

Suppose an application wants to report cache hit counts. There are at least two ways:

**Custom MBean attribute:**

~~~text
com.example.shop:type=Cache,name=products
    HitCount = 12450
~~~

**Actuator metrics endpoint:** provides metrics from a metrics system like Micrometer using the appropriate meter/tag model.

Both can coexist, yet it becomes confusing if:

- One side counts hits since JVM startup while the other uses a time window.
- One side resets manually while the other is a cumulative counter that does not reset at the same time.
- Metric names/units differ.
- Metric tags and ObjectName keys carry different meanings.
- Clients ignore instance labels and mix counts across replicas.

To stay consistent, align metric definitions: units, time boundaries, data source, and resource scope. Do not expect a custom attribute to automatically appear in Actuator metrics; a dedicated meter or suitable adapter is usually needed.

## 13. Endpoint Exposure and Access Control

Distinguish **availability** from **authorization**.

- Endpoint **enabled**: the bean/endpoint can exist in the application context.
- Endpoint **exposed over JMX**: can be registered as a JMX MBean per configuration.
- Endpoint **exposed over HTTP**: has a web access path per configuration.
- Endpoint **authorized for access**: the client must still pass the corresponding security layers.

Example:

~~~properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.web.exposure.include=health,info
~~~

Do not assume every listed endpoint is ready in every application. Inspect the runtime registry and the actual endpoint list.

### JMX Security Is Not HTTP Security

A remote JMX connector has its own authentication/TLS/authorization. Spring Security for HTTP endpoints does not replace JMX connector policies.

If a management operation is exposed over two transports, review access permissions **on both paths**. An endpoint protected only by HTTP security may still require separate JMX controls when JMX exposure is enabled.

Do not open remote JMX widely just to use Actuator metrics. If you only need monitoring data, a read-only metrics endpoint with a suitable security model can reduce the administrative privileges granted to collectors.

## 14. Naming and Client Compatibility

A custom MBean's ObjectName is part of its management contract:

~~~text
com.example.shop:type=Cache,name=products
~~~

Scripts such as:

~~~java
connection.getAttribute(
    new ObjectName(
        "com.example.shop:type=Cache,name=products"
    ),
    "HitCount"
);
~~~

depend on that name and attribute type. Changing the ObjectName or renaming `HitCount` to `Hits` can break clients.

For Actuator endpoints, the endpoint ID and how the framework maps it to an ObjectName can differ from a custom MBean. When migrating between the two mechanisms, do not assume the JMX contract stays identical.

If legacy clients exist, you can keep a custom MBean adapter for compatibility while rolling out new endpoints. Carefully control ownership and concurrency if both interfaces govern the same resource.

## 15. Lifecycle and Multiple ApplicationContexts

A Spring Boot application can have:

- A main ApplicationContext.
- A separate management context in some configurations.
- Management beans from imported libraries or modules.
- Framework exporters and application-declared exporters.

If multiple exporters share an MBeanServer, avoid duplicate ObjectName registrations.

Some issues:

1. A custom MBean is registered twice because of two exporters.
2. A bean lives in a child context yet the exporter sees a different scope than expected.
3. The context closes yet the old MBean is not unregistered as expected.
4. `REPLACE_EXISTING` policy masks ownership conflicts.
5. JConsole is connected to a different JVM than the application being inspected.

**Registration policies do not replace ownership design.** Each MBean should have a clear owner responsible for register/unregister; if two contexts need the same data, consider a shared service or client/proxy instead of exporting duplicate ObjectNames.

## 16. Integration Testing: Confirming Both MBean Groups

A useful integration test should confirm:

- The custom MBean has the exact expected ObjectName.
- Required attributes/operations are exposed accurately.
- Expected Actuator endpoints appear in JMX when appropriately configured.
- No name collisions exist in the registry.
- Sensitive operations are not unexpectedly exposed.
- Context shutdown cleans up registrations under its management.

Example custom MBean check:

~~~java
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class CustomMBeanContractCheck {
    public static void verify(MBeanServer server) throws Exception {
        ObjectName name = new ObjectName(
            "com.example.shop:type=Cache,name=products"
        );

        if (!server.isRegistered(name)) {
            throw new AssertionError(
                "Expected custom MBean is not registered"
            );
        }

        Object hitCount = server.getAttribute(name, "HitCount");
        if (!(hitCount instanceof Long)) {
            throw new AssertionError("Wrong HitCount type");
        }
    }
}
~~~

This example assumes the test injects the exact MBeanServer used by the exporter. It checks only the custom MBean; the Actuator contract must be tested separately per endpoint ID and the actual naming of the framework version.

### Do Not Hardcode Unverified Actuator Domains

Instead of guessing ObjectNames for health/info, an integration test can query the whole registry, locate MBeans in the actual Actuator domain, and cross-check naming defined by the running version. Then record expected names in test fixtures.

## 17. Common Errors

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| JVM MBeans appear but custom MBean is missing | Exporter disabled or bean not selected | `spring.jmx.enabled`, component scan, metadata |
| Custom MBean exists but Actuator endpoint is missing | Missing Actuator or JMX exposure disallowed | Dependencies, endpoint availability, properties |
| HTTP endpoint exists but JMX endpoint is missing | Two different exposure policies | `management.endpoints.jmx.exposure.*` |
| Two exporters report duplicate name | Same ObjectName in one MBeanServer | Naming, exporter ownership |
| Endpoint appears under unfamiliar domain | Framework naming differs from expectation | MBeanServer query/canonical ObjectName |
| Remote client cannot access | Connector disabled or network/TLS/auth error | JMX transport and security |
| Attribute/operation missing | Metadata or interface mismatch | `MBeanInfo` |
| Metrics from two sources differ | Different scope, unit, reset, or aggregation | Metric definition documentation |
| Context shutdown affects other MBeans | Unclear ownership/registration lifecycle | Exporter and MBeanServer |
| HTTP call succeeds yet JMX is denied | Different access policies | Separate HTTP/JMX authorization |

## 18. When to Choose a Custom MBean vs. Actuator?

| Requirement | Usually Suitable Choice |
| --- | --- |
| Need a Standard MBean/MXBean interface for Java JMX clients | Custom MBean |
| Need JMX notifications per a specific contract | Custom MBean |
| Need attributes with getters/setters and JMX-specific operations | Custom MBean |
| Need Boot's standard health, info, metrics | Actuator |
| Want the same endpoint exposable over HTTP/JMX | Actuator custom endpoint |
| Must preserve legacy ObjectNames for operations scripts | Keep a custom MBean adapter |
| Need metrics solely for a monitoring collector | Micrometer/Actuator metrics usually fit |
| Need dangerous actions with deep security workflows | Evaluate dedicated management API and auditing |

Both can be used if responsibilities do not overlap or a central service controls state. Do not choose based merely on line count.

## 19. Practice Exercise

**Goal:** run a Spring Boot application with a custom MBean for a cache and Actuator `health`/`info` endpoints exposed over JMX.

Steps:

1. Add the Actuator dependency.
2. Enable JMX per your project's configuration.
3. Create `ProductCacheManagement` with `@Component`, `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`.
4. Configure Actuator JMX exposure with only the needed endpoints.
5. Run the application and open JConsole on the right JVM.
6. Find `com.example.shop:type=Cache,name=products`.
7. Read `HitCount` and `Enabled`; try `resetStatistics()` in a test environment.
8. Find the Actuator MBeans that actually appear and record their ObjectNames.
9. Query `MBeanServer` to confirm no unintended ObjectNames exist in the application domain.
10. Distinguish access permissions for HTTP endpoints and remote JMX if remote is enabled.
11. Shut down the application and confirm the exporter cleans up context-lifecycle MBeans.

**Expected result:** custom resources and Actuator endpoints can coexist in the same MBeanServer, use different naming, and serve distinct management needs.

## 20. Self-Check Questions

**1. Does setting `spring.jmx.enabled=true` automatically enable remote JMX?** No. Remote connectors require separate security and transport configuration.

**2. Is `@ManagedResource` synonymous with an Actuator endpoint?** No. It declares metadata for Spring JMX export.

**3. Why might JConsole show JVM Memory yet not show a custom MBean?** Platform MXBeans are built in; a custom bean still needs to be created by Spring and registered by an exporter.

**4. Are Actuator HTTP exposure and JMX exposure identical?** No. They can have separate exposure and security policies.

**5. Does the same ObjectName in two different JVMs collide?** Normally no; uniqueness applies within each MBeanServer.

**6. Why do two management layers calling one resource easily cause bugs?** They can create duplicate side effects or race conditions without a shared service/state machine.

**7. Should you place custom MBeans in the Actuator domain?** Not without a clear reason and checking framework naming/ownership.

**8. When do you need a custom Actuator endpoint?** When you want a management endpoint model independent of JMX that can be exposed over other technologies per configuration.

## 21. Summary

Spring Boot allows using **custom MBeans**, **platform MXBeans**, and **Actuator endpoints** in the same management environment. A sustainable combination is:

- Use custom MBeans for JMX-specific contracts, placing ObjectNames in their own domain.
- Use Actuator for convention-based Boot management endpoints.
- Expose only the endpoints and operations needed.
- Separate JMX connector security from HTTP endpoint security.
- Keep a single shared source of business logic if custom MBeans and Actuator control the same resource.
- Verify the JMX registry and actual metadata instead of guessing framework naming.

**Combining them well does not mean exporting as much as possible, but exposing the right data and actions through each management interface with consistent ownership, naming, and access control.**

### References

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE API — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
