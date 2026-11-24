# Verifying Whether Scanned Beans Match the Intended Scope in AnnotationMBeanExporter

## 1. The Problem to Solve

In Spring Framework JMX, **AnnotationMBeanExporter** finds Spring beans that carry JMX management metadata, such as `@ManagedResource`, and exports them as MBeans in an `MBeanServer`. However, an application can have many beans, packages, `ApplicationContext` instances, and exporter configurations. Therefore, the practical question is not just "Is the bean annotated?" but also:

- Is the bean created and managed by Spring in a context visible to the exporter?
- Which beans is the exporter detecting, and under what rules?
- Are any beans outside the intended scope being exported unintentionally?
- Are any beans that need management being missed due to component scanning, conditional initialization, or multiple contexts?
- Are the selected beans actually registered as MBeans with the right `ObjectName`?

**Two processes must be distinguished:** *Spring component scanning* discovers components to create Spring beans; *JMX autodetection/export* selects beans that already exist in the Spring container to publish via JMX. Misconfiguring either process can make the actual MBean list diverge from expectations.

This lesson guides you through verifying MBean detection and export scope by cross-checking bean definitions, annotations, exporter configuration, and the registry in `MBeanServer`.

## 2. Bean Discovery and JMX Export Flow

A typical architecture:

```text
Classpath
    |
    | @ComponentScan / @SpringBootApplication / @Import
    v
Spring ApplicationContext
    |
    +-- Bean A: @ManagedResource
    +-- Bean B: @ManagedResource
    +-- Bean C: no @ManagedResource
    +-- Bean D: not created due to @Profile / @Conditional
    |
    | AnnotationMBeanExporter / metadata assembler
    v
Selected set of beans to export
    |
    | ObjectNamingStrategy + RegistrationPolicy
    v
MBeanServer
    |
    +-- Bean A's ObjectName
    +-- Bean B's ObjectName
    |
    v
JConsole / VisualVM / MBeanServerConnection
```

A bean annotated in source code that **does not exist in the context** will not automatically appear in JMX. Conversely, a bean created in the context is not guaranteed to be exported; the exporter must also recognize its management metadata and register it successfully.

### Two sets to compare

Let:

- **S**: the set of Spring beans managed by the context.
- **E**: the set of beans selected by the exporter to export.
- **R**: the set of `ObjectName` entries actually registered in `MBeanServer`.

The expected outcome is that beans needing management belong to **S**, are selected into **E**, and have corresponding names in **R**. You cannot look only at annotations or see a single name in JConsole and conclude the entire scan process is correct.

## 3. Understanding What AnnotationMBeanExporter Does

Spring Framework provides `AnnotationMBeanExporter` in the `org.springframework.jmx.export.annotation` package. This class integrates bean export based on management annotations:

- `@ManagedResource`: designates a management resource and general metadata.
- `@ManagedAttribute`: describes a getter/setter exposed as an attribute.
- `@ManagedOperation`: describes an operation.
- `@ManagedOperationParameter`: describes an operation parameter.
- `@ManagedNotification`: notification metadata.
- `@ManagedMetric`: metric metadata if used.

Example:

```java
package com.example.orders.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments",
    description = "Payment queue monitoring"
)
public class PaymentQueueManagement {

    private volatile int pendingCount;

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedOperation
    public void resetStatistics() {
        pendingCount = 0;
    }
}
```

If this bean is created by the Spring container, the exporter operates properly, and registration succeeds without error, the corresponding MBean can appear under:

```text
com.example.orders:type=Queue,name=payments
```

However, having `@ManagedResource` on a class **does not replace** enabling Spring JMX export. Annotations are only a source of metadata; the exporter must exist and be active in the application context.

## 4. How Component Scan and JMX Export Scan Differ

### 4.1. Component scan

Configuration:

```java
@Configuration
@ComponentScan(basePackages = "com.example.orders")
public class OrdersConfiguration {
}
```

allows Spring to scan eligible components under package `com.example.orders` and its subpackages. If `PaymentQueueManagement` resides in `com.example.orders.management` and is marked `@Component`, it can be created as a Spring bean provided all initialization conditions are satisfied.

If the configuration only scans:

```java
@ComponentScan(basePackages = "com.example.orders.web")
```

then package `com.example.orders.management` lies outside this scan scope. JMX annotations on the class do not automatically register the class as a bean.

### 4.2. Detection for MBean export

After Spring creates the beans, the exporter can detect beans carrying supported JMX metadata. This is a different process from classpath scanning to instantiate components.

Example:

```text
com.example.orders.web.OrderController
com.example.orders.management.PaymentQueueManagement
com.example.orders.service.OrderService
```

Suppose all three are Spring beans, but only `PaymentQueueManagement` is marked with `@ManagedResource`; an annotation-based exporter should normally include only this bean in the autodetected MBean set.

If the exporter is also configured with **explicit beans**, the exported list may be supplemented or adjusted by that configuration. Therefore, inspect the entire configuration rather than guessing from annotations alone.

### 4.3. ApplicationContext is also a boundary

Multiple Spring contexts can run simultaneously inside one JVM:

```text
Parent context
  ├── SharedService
  └── SharedManagement

Child context A
  └── WebManagementA

Child context B
  └── WebManagementB
```

Which beans an exporter in a context sees depends on the bean factory, context relationships, and specific configuration. Do not assume an exporter in one child context always sees all beans of sibling contexts.

Furthermore, multiple contexts can share the **platform MBeanServer**. In that case, exporters in different contexts still risk registering duplicate `ObjectName` values.

## 5. Checking Whether the Bean Exists in Spring ApplicationContext

The first step is verifying that the bean is actually created in the expected context.

Example:

```java
import org.springframework.context.ApplicationContext;

public final class BeanPresenceCheck {

    public static void inspect(ApplicationContext context) {
        String[] names = context.getBeanNamesForType(
                PaymentQueueManagement.class
        );

        System.out.println("Matching beans: " + names.length);

        for (String name : names) {
            System.out.println("Bean: " + name);
        }
    }
}
```

If the bean is not found:

1. Check the class's package against `@ComponentScan`.
2. Check whether the class has `@Component`, `@Service`, or is declared via `@Bean`.
3. Check `@Profile`, `@Conditional`, and other initialization conditions.
4. Check whether the inspected context is actually the context running the exporter.
5. Check startup logs for bean creation errors.

If there are multiple beans of the same type, verify which bean name genuinely needs management and whether the exporter registers all of them.

**Note:** a method such as `getBeanNamesForType` only reflects objects/types known to Spring in that context. It does not by itself prove that every bean has been registered as an MBean.

## 6. Minimal Exporter Configuration and Expected Scope

An illustrative configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    static AnnotationMBeanExporter annotationMBeanExporter() {
        return new AnnotationMBeanExporter();
    }
}
```

When the annotation exporter is active in the context, beans with matching JMX metadata can be detected and exported. If the application already enables Spring JMX through another mechanism (such as framework configuration or Spring Boot auto-configuration), avoid accidentally creating multiple exporters registering the same bean.

### Why not look only at component scan?

Suppose the context scans `com.example` more broadly than intended. All eligible components can be created, yet the exporter only cares about beans with management metadata. If a third-party library also registers beans with `@ManagedResource` into the same context, they may also appear in JMX depending on autodetection scope and actual configuration.

This raises two separate questions:

- **Is the application scanning too many components?**
- **Is the exporter exporting too many management beans?**

The answers may differ. Tightening component scanning can affect dependency injection and application behavior; to restrict JMX, it is sometimes better to adjust the exporter, naming strategy, or how metadata is declared.

## 7. Checking Actual ObjectNames in MBeanServer

After confirming the bean exists, verify that it has been exported.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxRegistrationCheck {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.orders:type=Queue,name=payments"
        );

        System.out.println(
                "Registered: " + server.isRegistered(name)
        );
    }
}
```

A `true` result means an MBean with that ObjectName exists in the **inspected MBeanServer**. The result does not tell you for certain which Spring exporter registered it or which Java bean is its source if multiple components could use the same name.

If the application configures a separate MBeanServer, `ManagementFactory.getPlatformMBeanServer()` might not be where the exporter registered the MBean. In that case, inspect the exact MBeanServer injected into the exporter.

### Querying by domain

```java
import java.util.Set;
import javax.management.ObjectName;

Set<ObjectName> names = server.queryNames(
        new ObjectName("com.example.orders:*"),
        null
);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
```

Use the output to identify **all MBeans in the application's namespace**, including beans appearing unexpectedly.

### Comparing against the expected list

Example expected set:

```text
com.example.orders:type=Queue,name=payments
com.example.orders:type=Queue,name=shipping
com.example.orders:type=Scheduler,name=background
```

The actual list queried from `MBeanServer` should be compared against that list. If a name is missing, trace the registration path. If an unexpected name exists, identify the source exporter and why its metadata was detected.

## 8. Checking via JConsole or VisualVM

Besides the API, you can use JMX tools for direct observation:

1. Run the Spring application in an appropriate environment.
2. Open `jconsole` from the JDK and connect to the application's JVM.
3. Select the **MBeans** tab.
4. Locate the application domain, e.g., `com.example.orders`.
5. Expand the nodes and inspect the ObjectName, attributes, and operations.
6. Compare with the list of beans intended for export.
7. Note any missing beans or beans outside the expected scope.

**Distinguish display names from ObjectNames:** JConsole can organize key properties into a tree in its own way. Compare full ObjectNames rather than looking only at the leaf node name.

For VisualVM, JMX/MBeans functionality may require a plugin depending on the version. For remote systems, set up a secured JMX connection; do not open public management ports merely for testing convenience.

## 9. Inspecting Metadata to Confirm the Right Bean Was Exported

Even when the `ObjectName` appears, verify that the attributes/operations match the expected contract.

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxContractInspector {

    public static void inspect(
            MBeanServer server,
            ObjectName name
    ) throws Exception {
        MBeanInfo info = server.getMBeanInfo(name);

        System.out.println("MBean: " + name);
        System.out.println("Implementation: " + info.getClassName());

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                "ATTRIBUTE %s type=%s readable=%s writable=%s%n",
                attribute.getName(),
                attribute.getType(),
                attribute.isReadable(),
                attribute.isWritable()
            );
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.printf(
                "OPERATION %s return=%s%n",
                operation.getName(),
                operation.getReturnType()
            );
        }
    }
}
```

For `PaymentQueueManagement`, you expect the `PendingCount` attribute and the `resetStatistics` operation. If an MBean exists under the right ObjectName but the metadata does not match, another exporter or another metadata configuration may have registered the resource.

Do not rely solely on `MBeanInfo.getClassName()` to identify the bean implementation when Spring uses a Model MBean or proxy; the result may reflect the descriptor class or the exported type, depending on the assembler.

## 10. Common Reasons a Bean Is Not Scanned/Exported

### 10.1. Package lies outside component scan

```java
@ComponentScan("com.example.orders.web")
```

does not cover classes in `com.example.orders.management`. The bean is not created, so the exporter never sees it.

Resolution: expand component scan to the proper scope, configure `@Import`, or declare an explicit `@Bean`.

### 10.2. Annotated with @ManagedResource without registering a Spring bean

```java
@ManagedResource
public class QueueAdmin {
}
```

This class has neither `@Component` nor a `@Bean` declaration; JMX annotations do not automatically place it into the ApplicationContext.

Resolution: ensure the class is managed by Spring before checking JMX export.

### 10.3. Bean excluded by @Profile or @Conditional

```java
@Profile("operations")
@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments"
)
public class PaymentQueueManagement {
}
```

If the `operations` profile is not active, the bean does not exist in the context and therefore is not exported to JMX.

Resolution: verify active profiles and condition evaluations appropriate for the environment.

### 10.4. Multiple ApplicationContexts exist

The bean resides in a child context while the exporter resides in another context. The detection scope might not include that bean.

Resolution: identify where the bean is created, where the exporter is created, and the shared MBeanServer. Avoid creating duplicate exporters if a single clear owner can manage the bean set.

### 10.5. Exporter is not enabled

The application has `@ManagedResource`, but lacks `AnnotationMBeanExporter` or the corresponding JMX integration configuration.

Resolution: check the actual exporter beans in the context and the Spring/Spring Boot configuration for the running version.

### 10.6. ObjectName collides with an existing MBean

Two beans both export under:

```text
com.example.orders:type=Queue,name=primary
```

will collide if they share an MBeanServer. Registration may fail or follow `RegistrationPolicy`.

Resolution: assign a unique ObjectName per resource, check the registration policy and ownership; avoid using replace/ignore simply to hide naming mistakes.

### 10.7. Proxy or metadata not recognized as expected

A bean may be proxied by Spring AOP, transactions, or security. Depending on how the proxy is created and how the metadata assembler works, inspecting annotations on the runtime bean may differ from expectations.

Resolution: inspect the target class, proxy class, exporter configuration, and actual metadata from `MBeanServer`. If necessary, extract the management bean into a simple adapter or configure explicit export.

### 10.8. Exporter configured to select beans differently

An application may have a standard `MBeanExporter`, an explicit bean list, an assembler, or a custom naming strategy. Do not look only for `AnnotationMBeanExporter` and assume you know the entire export policy.

Resolution: identify all active exporters in the context and the MBeans each exporter is responsible for registering.

## 11. Avoiding Unintended Out-of-Scope Export

Exporting an unexpected management bean can expose operational details or state-mutating operations. Practical solutions:

### 11.1. Design a clear management package

Example:

```text
com.example.orders
  ├── application
  ├── domain
  ├── infrastructure
  └── management
      ├── PaymentQueueManagement
      └── ShippingQueueManagement
```

A dedicated package helps clarify ownership and track beans carrying JMX annotations. However, **a package is not automatically a filter for every exporter**; you must verify against actual configuration.

### 11.2. Use a management adapter

If a business service has many sensitive methods, create a small management bean:

```java
@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments"
)
public class PaymentQueueMonitor {

    private final PaymentQueueService service;

    public PaymentQueueMonitor(PaymentQueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return service.pendingCount();
    }
}
```

`PaymentQueueService` is an illustrative interface/service. An adapter limits the JMX method surface without exposing the entire business API.

### 11.3. Name by namespace and resource

```text
com.example.orders:type=Queue,application=checkout,name=payments
com.example.orders:type=Queue,application=checkout,name=shipping
```

A consistent ObjectName strategy both prevents collisions and makes querying and checking out-of-scope beans easier.

### 11.4. Separate read permissions and operations

For state-changing operations, configure remote JMX access controls and runtime permissions appropriately. Annotations are not an authorization mechanism. Restrict exporting mutating operations unless necessary.

### 11.5. Maintain an allowlist of permitted MBeans

In large systems, store the expected list of ObjectNames or patterns per environment. During integration tests, query `MBeanServer` and compare. This catches newly exported beans caused by overly broad scan settings early.

## 12. Demonstrating Verification of Permitted MBeans

Suppose the application expects only two MBeans in the `com.example.orders` domain.

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class ExpectedJmxNamesCheck {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        Set<ObjectName> expected = Set.of(
                new ObjectName(
                    "com.example.orders:type=Queue,name=payments"
                ),
                new ObjectName(
                    "com.example.orders:type=Queue,name=shipping"
                )
        );

        Set<ObjectName> actual = server.queryNames(
                new ObjectName("com.example.orders:*"),
                null
        );

        Set<ObjectName> missing =
                new java.util.HashSet<>(expected);
        missing.removeAll(actual);

        Set<ObjectName> unexpected =
                new java.util.HashSet<>(actual);
        unexpected.removeAll(expected);

        System.out.println("Missing: " + missing);
        System.out.println("Unexpected: " + unexpected);
    }
}
```

If either `missing` or `unexpected` is non-empty, inspect the export and naming configuration. This check must run inside the JVM or against an `MBeanServerConnection` corresponding to the **actual server**; running a standalone Java process with its own platform MBeanServer will not automatically see another application's MBeans.

### When multiple sources share a domain

A domain may hold MBeans intentionally registered by multiple subsystems. In that case, the expected list should define a narrower scope (e.g., `application=checkout`) to avoid falsely flagging valid MBeans from other subsystems.

## 13. Inspecting Context and Exporters with Spring Code

You can inspect the exporter beans present in the context:

```java
import java.util.Map;
import org.springframework.context.ApplicationContext;
import org.springframework.jmx.export.MBeanExporter;

public final class ExporterBeanInspector {

    public static void inspect(ApplicationContext context) {
        Map<String, MBeanExporter> exporters =
                context.getBeansOfType(MBeanExporter.class);

        exporters.forEach((name, exporter) ->
                System.out.println(
                    "Exporter bean: " + name
                    + ", type=" + exporter.getClass().getName()
                )
        );
    }
}
```

Since `AnnotationMBeanExporter` extends `MBeanExporter`, this lookup finds the corresponding exporters. If multiple exporters appear, trace which configuration creates each exporter and whether they process the same bean.

Do not conclude with certainty which exporter registered a bean solely from the exporter class; cross-check the configuration and registry.

### Inspecting beans for management annotations

You can use `ApplicationContext` and Spring utilities to search metadata, but proxies, factory beans, and composed annotations mean calling `bean.getClass().isAnnotationPresent(...)` directly can miss metadata. To determine the exact exported set accurately, prefer observing the exporter's output or inspecting actual `MBeanInfo`.

## 14. Practical Scenario: Bean Missing in JConsole

Suppose the source code has:

```text
com.acme.shop.web.ShopController
com.acme.shop.management.InventoryAdmin
com.acme.shop.management.PaymentQueueAdmin
```

Both management classes carry `@ManagedResource`, yet JConsole only shows `InventoryAdmin`.

Investigation steps:

1. Verify whether `PaymentQueueAdmin` has a bean instance in the context.
2. If not, check component scan, `@Profile`, and `@Conditional`.
3. If present, verify whether the exporter/assembler supports that class's metadata.
4. Check the `ObjectName` on the annotation and the naming strategy.
5. Check startup logs for `InstanceAlreadyExistsException` or `NotCompliantMBeanException`.
6. Check the exact `MBeanServer` the exporter registers into.
7. Query `MBeanServer` by domain to rule out the tool displaying the MBean under another branch.
8. Inspect `MBeanInfo` to confirm attributes/operations belong to the right bean.

For example, if both beans use:

```text
com.acme.shop:type=Management,name=default
```

the cause may be an ObjectName collision. Fix it by naming them:

```text
com.acme.shop:type=Management,name=inventory
com.acme.shop:type=Management,name=payments
```

instead of using `REPLACE_EXISTING` as a default workaround.

## 15. Practical Scenario: Unwanted Bean Exported

Suppose JConsole displays an MBean:

```text
com.acme.shop:type=Maintenance,name=internal
```

even though the operations list only expected two queue monitors.

Analysis:

1. Identify the actual bean via configuration or metadata.
2. Find the corresponding `@ManagedResource` or explicit export mapping.
3. Check whether any library/module brings that bean into the ApplicationContext.
4. Determine whether the exporter detects all annotated beans in the context or uses an explicitly configured list.
5. If the bean should not be exposed, exclude it from export via the appropriate configuration or remove management metadata from the class.
6. After the change, query `MBeanServer` to verify the name has disappeared.
7. Check lifecycle to ensure no stale registration remains from an older context.

**Caution:** merely changing packages or disabling component scanning to hide JMX can break business functionality that depends on that bean. Identify the exact configuration layer causing the export.

## 16. Spring Boot: Key Differences to Note

In a Spring Boot application, JMX enablement can depend on Boot configuration and starters/dependencies. In many Boot setups, exporting Spring beans via JMX is controlled by the property:

```properties
spring.jmx.enabled=true
```

However, auto-configuration, domains, naming, and management endpoints can vary across Boot versions, dependencies, and application settings. Do not rely on a single property alone to conclude exactly which beans are exported.

Practical verification steps:

- Determine the active properties and profiles.
- Check which exporter beans are auto-configured.
- Check whether another explicit exporter duplicates functionality.
- Check the actual MBean names via `MBeanServer`.
- If using Spring Boot Actuator, distinguish Actuator JMX endpoints from annotation-exported application MBeans.

In most situations, **reading the actual registry is the final confirming evidence**, while configuration explains why the registry holds that result.

## 17. Avoid Checking the Wrong JVM or MBeanServer

A common mistake is running:

```java
ManagementFactory.getPlatformMBeanServer()
```

in a separate verification program, getting `false`, and concluding the bean was not exported. Each Java process typically has its own platform MBeanServer. Code in a standalone test process inspects its own server.

When using JConsole:

1. Identify the exact process ID.
2. Select the application's JVM.
3. Confirm the application name or main class.
4. Inspect the domains from that MBeanServer.

When using a remote client, obtain an `MBeanServerConnection` from the target JVM's JMX connector:

```java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
        "service:jmx:rmi:///jndi/rmi://127.0.0.1:9999/jmxrmi"
);

try (JMXConnector connector =
             JMXConnectorFactory.connect(url)) {
    MBeanServerConnection connection =
            connector.getMBeanServerConnection();

    // Query MBeans from the target JVM.
}
```

The URL is only an example for a separately configured endpoint; do not assume every JVM exposes JMX RMI on port 9999. Production environments require appropriate authentication/TLS and network access restrictions.

## 18. Common Errors and Troubleshooting Steps

| Symptom | Possible Cause | Inspection Step |
| --- | --- | --- |
| Class has `@ManagedResource` but does not appear | Class is not created as a Spring bean | Component scan, `@Bean`, profile, condition |
| Bean exists but is not exported | Exporter not enabled or metadata mismatch | List of exporters and assemblers |
| Some beans appear in another context | Different ApplicationContext / bean factory | Analyze context relationships |
| Two beans compete for the same name | Duplicate ObjectName | Domain, key properties, registration policy |
| Bean has an MBean but attributes are missing | Methods lack annotations or assembler skips them | `MBeanInfo` and metadata |
| MBean appears with an unexpected name | Naming strategy or ObjectName transformed | Full ObjectName and exporter configuration |
| Extra MBeans appear | Overly broad scan/auto-detection or explicit registration | Trace bean definitions and exporter mapping |
| JConsole does not see the domain | Connected to wrong JVM or server has no registration | PID, JMX URL, MBeanServer |
| Registration fails at startup | Invalid name, duplicate name, or non-compliant MBean | Exception logs and root cause |
| Proxied bean causes metadata mismatch | AOP/proxy affects discovery | Metadata on target class and exporter config |

## 19. Deployment Checklist

When you need to confirm `AnnotationMBeanExporter` scans the intended scope, use this checklist:

1. **Define targets:** list the Spring beans and expected ObjectNames to export.
2. **Confirm Spring context:** right `ApplicationContext`, active profiles, and component scan.
3. **Confirm bean presence:** expected beans actually exist in the context.
4. **Confirm exporter:** an appropriate exporter exists with no unintended duplicate export configuration.
5. **Confirm metadata:** `@ManagedResource`, attributes, and operations are accurate on selected beans.
6. **Confirm naming:** every MBean has a valid, unique ObjectName in the MBeanServer.
7. **Confirm registry:** compare the actual ObjectName set with the expected set.
8. **Confirm contract:** attributes/operations are properly exposed and no unintended methods leak.
9. **Confirm lifecycle:** MBeans are unregistered when the exporter/context stops.
10. **Confirm security:** exported capabilities match JMX access permissions and operational needs.

This verifies the **actual scope**, not merely the declared configuration.

## 20. Self-Check Questions

**1. Why might a bean with `@ManagedResource` not show up in JConsole?**

The class may not be instantiated as a Spring bean, the exporter may not be enabled, the bean may live in another context, the ObjectName may be invalid, registration may have failed, or JConsole may be connected to the wrong JVM.

**2. Is `@ComponentScan` the same as AnnotationMBeanExporter's scan?**

No. Component scan selects classes to create Spring beans; the exporter selects beans and metadata to register MBeans.

**3. Why check both ApplicationContext and MBeanServer?**

Because a bean can exist in Spring without being exported; only the actual registry confirms the MBean is registered.

**4. Can multiple contexts in the same JVM collide on ObjectName?**

Yes. If their exporters share an MBeanServer, ObjectNames must be unique within that server.

**5. Can you rely on `MBeanInfo.getClassName()` to identify the exact original Spring bean?**

Not always, because Model MBeans/proxies and metadata assemblers can affect the displayed class name.

**6. If the exporter detects too many beans, should you immediately narrow broad component scanning?**

Not necessarily. Diagnose component registration and JMX export separately; changing component scanning can break application functionality.

**7. Is `isRegistered(ObjectName)` enough to prove the right bean was exported?**

It only proves an MBean with that name exists in that server. Check metadata and configuration to verify the exact resource and management interface.

## 21. Summary

To verify that `AnnotationMBeanExporter` scans the right scope, cross-check **three distinct yet related layers**:

```text
Spring beans actually present in ApplicationContext
                  |
                  v
Beans selected by exporter via metadata/configuration
                  |
                  v
ObjectNames successfully registered in MBeanServer
```

Combine checks across **component scan**, **ApplicationContext**, **exporter**, **ObjectName**, and **MBeanInfo**. When beans are missing or extra, trace from created beans to registered MBeans, checking context boundaries, naming, and initialization conditions.

Accurate scoping not only avoids missing monitoring data, it also prevents unintentionally exposing management operations. A sound Spring JMX configuration explicitly defines **which beans are exported, under which ObjectNames, with which attributes/operations, and under which exporter's lifecycle management**.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `AnnotationMBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Spring Framework API — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
