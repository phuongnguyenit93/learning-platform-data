# Proxy Interfaces Hiding Annotations and Why Spring JMX Autodetection Can Skip a Bean

## 1. The Phenomenon to Explain

In Spring Framework, `MBeanExporter` can automatically find beans eligible for JMX export instead of requiring every entry to be declared in `setBeans`. A common approach is using `@ManagedResource` to mark management classes, then letting annotation-based metadata and the autodetection mechanism find them.

A confusing situation arises when the same bean:

- Works normally without AOP.
- Has `@ManagedResource` on the implementation class.
- When `@Transactional`, method security, or another advice is enabled, the bean is wrapped by Spring in a **JDK dynamic proxy** exposing only interfaces.
- The JMX exporter either does not see the bean or does not expose all attributes/operations.

Core point: **an annotation declared on the target class does not automatically mean the annotation appears on the proxy class or proxy interface**. When a component performing autodetection looks only at the proxy's runtime type/interfaces, it may miss metadata on the implementation. Spring has mechanisms to detect the target class, so exact results still depend on exporter configuration, metadata assembler, proxies, and Spring version.

This lesson explains the layers to distinguish, how to verify in practice, and how to design adapters that avoid depending on how proxies hide annotations.

## 2. What Is Autodetection in Spring JMX?

`MBeanExporter` can be configured to register:

1. **Explicit beans**: a map from key/ObjectName to bean or bean name.
2. **Autodetected beans**: the exporter finds beans matching discovery rules, such as annotation metadata.
3. **Standard MBeans**: objects conforming to Standard MBean, MXBean, or `DynamicMBean`, depending on export path and detection mode.

Example of annotations on an implementation:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;

@Service
@ManagedResource(
    objectName = "com.example:type=BillingMonitor,name=Primary",
    description = "Billing management"
)
public class BillingService implements BillingOperations {

    @ManagedAttribute(description = "Pending invoices")
    public long getPendingInvoiceCount() {
        return 12;
    }

    @Override
    public void processInvoice(String invoiceId) {
        // Business behavior.
    }
}
```

If the exporter uses the right `AnnotationJmxAttributeSource`, `MetadataMBeanInfoAssembler`, and appropriate detection mechanism, the bean can be exposed under the declared ObjectName. However, if the bean is replaced by a JDK proxy and detection logic only inspects interfaces, the implementation's `@ManagedResource` may no longer be visible via that path.

**Do not understand “autodetection” as an algorithm guaranteed to find every annotation at every target layer.** It is a bean discovery policy, affected by how the exporter and proxy perform introspection.

## 3. What Do Java Interfaces and JDK Dynamic Proxies Change?

A business interface:

```java
public interface BillingOperations {
    void processInvoice(String invoiceId);
}
```

Implementation:

```java
@Service
@ManagedResource(
    objectName = "com.example:type=BillingMonitor,name=Primary"
)
public class BillingService implements BillingOperations {

    @Override
    public void processInvoice(String invoiceId) { }

    @ManagedAttribute
    public long getPendingInvoiceCount() {
        return 12;
    }
}
```

When Spring AOP uses a JDK dynamic proxy, the object returned to callers typically has a type like `jdk.proxy2.$Proxy...`, implementing `BillingOperations` and proxy support interfaces, **not a subclass of `BillingService`**.

Two consequences:

- `proxy.getClass()` is not `BillingService.class`; direct reflection on the proxy class does not inherently find the target's `@ManagedResource` annotation.
- The proxy only has methods belonging to the interfaces it implements. `getPendingInvoiceCount()` is not part of `BillingOperations`, so it may not be invocable through the proxy reference even though the implementation has that public method.

Thus there are two independent questions:

1. **Detection:** can the framework find the valid annotation/class to select the bean for export?
2. **Invocation:** once selected, can the MBean representing the proxy actually invoke the method declared as a JMX attribute/operation?

Fixing detection does not necessarily solve invocation.

## 4. Annotations on Target Class, Proxy Class, and Interface

Java annotations have specific inheritance rules. An annotation placed on an implementation **is not automatically copied onto an interface**, and a JDK dynamic proxy does not automatically copy all target annotations onto the proxy runtime class.

Example:

```java
@ManagedResource(
    objectName = "com.example:type=BillingMonitor,name=Primary"
)
public class BillingService implements BillingOperations {
    // ...
}
```

Even if an annotation has `@Inherited`, Java's inheritance mechanism only applies to subclasses under specific rules, and does not make interfaces or JDK proxies inherit annotations from an implementation. Simple reflection like the following may be unsuitable:

```java
boolean marked = bean.getClass()
    .isAnnotationPresent(ManagedResource.class);
```

With Spring AOP, you can query the target class:

```java
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.jmx.export.annotation.ManagedResource;

Object bean = context.getBean("billingService");
Class<?> runtimeClass = bean.getClass();
Class<?> targetClass = AopUtils.getTargetClass(bean);

System.out.println("runtime=" + runtimeClass.getName());
System.out.println("target=" + targetClass.getName());

boolean targetMarked =
    AnnotatedElementUtils.hasAnnotation(
        targetClass, ManagedResource.class
    );
System.out.println("target annotation=" + targetMarked);
```

`AopUtils.getTargetClass` can detect the target class of common Spring AOP proxies. Do not use this check as proof that the exporter definitely uses the same metadata algorithm; it only helps observe why the bean's externally visible class differs from the annotated class.

## 5. Illustrating How an Autodetection Path Can Miss Annotations

```text
Source code:
  @ManagedResource
  class BillingService implements BillingOperations
          |
          v
Spring AOP creates a JDK proxy
          |
          +--> runtime class: $Proxy...
          +--> exposed interface: BillingOperations
          +--> target class: BillingService (holds annotation)
          |
          v
MBeanExporter autodetection / metadata source
          |
          +--> Inspects target metadata correctly?
          |       +--> Yes: candidate may be detected
          |
          +--> Inspects proxy interface/runtime only?
                  +--> No @ManagedResource in that view
                  +--> Candidate may be skipped
```

In real Spring applications, the exporter can work with bean instances, bean names, target classes, and metadata sources. Do not claim every JDK proxy causes autodetection to fail; verify experimentally on the running configuration and version.

Pay special attention to bean creation order and post-processing: when a `BeanPostProcessor` creates a proxy before the exporter inspects the bean, the exporter may receive only the already-proxied object. This explains why enabling an aspect can alter MBean discovery results even when annotation source code did not change.

## 6. Configuring an Annotation-Based JMX Exporter

Spring JMX uses key components:

- `AnnotationJmxAttributeSource`: reads metadata from `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`.
- `MetadataNamingStrategy`: resolves ObjectName from management metadata.
- `MetadataMBeanInfoAssembler`: creates attribute and operation information from metadata.
- `MBeanExporter`: discovers beans and registers MBeans with `MBeanServer`.

Java configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {

    @Bean
    public AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MBeanExporter exporter(
            AnnotationJmxAttributeSource source) {

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);
        return exporter;
    }
}
```

This is an illustrative configuration for plain Spring Framework. In Spring Boot, `spring.jmx.enabled=true` and auto-configuration may provide the exporter; inspect the final configuration rather than arbitrarily adding a second exporter. With Spring Framework, `@EnableMBeanExport` is also a convenient way to declare this capability.

Without an appropriate metadata assembler or naming strategy, the mere presence of annotations in source code does not prove the exporter is using them.

## 7. Separating “Not Detected” from “Failed to Register”

Two similar-looking but distinct symptoms:

### Not detected

The Spring context has bean `billingService`, but the exporter does not select it for export. There is no MBean registration exception because registration never happened.

Signs:
- `context.containsBean("billingService")` is `true`.
- `MBeanServer.isRegistered(expectedName)` is `false`.
- No related `InstanceAlreadyExistsException` or `NotCompliantMBeanException`.
- The bean may be proxied; the annotation is on the target but not read by autodetection.

### Detected but registration failed

The exporter selected the bean, but `registerMBean` did not complete. Logs may contain `UnableToRegisterMBeanException` or deeper root causes:

- `MalformedObjectNameException`: invalid name syntax.
- `InstanceAlreadyExistsException`: duplicate ObjectName.
- `NotCompliantMBeanException`: bean is not JMX-compatible under the export path.
- Reflection, mapping, proxy method, or lifecycle errors.

Read the stack trace instead of applying the same fix to both. Adding annotations to an interface will not resolve a duplicate ObjectName.

## 8. How to Inspect the Proxied Bean and Registration Server

A probe in the application:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("billingService");

System.out.println("Spring bean class: " + bean.getClass());
System.out.println("JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB proxy: " + AopUtils.isCglibProxy(bean));
System.out.println("Target class: " + AopUtils.getTargetClass(bean));

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "com.example:type=BillingMonitor,name=Primary"
);

System.out.println("Registered: " + server.isRegistered(expected));
```

If the exporter is configured to use a custom `MBeanServer`, the probe must obtain that exact instance instead of the platform server. A `false` on the wrong server does not prove the exporter skipped the bean.

If the MBean is registered, query its metadata:

```java
var info = server.getMBeanInfo(expected);
for (var a : info.getAttributes()) {
    System.out.println("Attribute: " + a.getName());
}
for (var op : info.getOperations()) {
    System.out.println("Operation: " + op.getName());
}
```

If `PendingInvoiceCount` is missing, check method annotations, proxy interfaces, and the assembler. If metadata exists but `getAttribute` fails to execute, check the invocation path through the proxy.

## 9. Solution 1: Export a Separate Management Adapter

The clearest approach is placing JMX annotations on a dedicated management class, rather than directly on a proxied business service.

Management port:

```java
public interface BillingManagement {
    long pendingInvoiceCount();
    void requestReconciliation();
}
```

Adapter:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=BillingMonitor,name=Primary",
    description = "Billing management"
)
public class BillingJmxAdapter {
    private final BillingManagement management;

    public BillingJmxAdapter(BillingManagement management) {
        this.management = management;
    }

    @ManagedAttribute
    public long getPendingInvoiceCount() {
        return management.pendingInvoiceCount();
    }

    @ManagedOperation
    public void requestReconciliation() {
        management.requestReconciliation();
    }
}
```

`BillingManagement` can be implemented by a Spring-managed service proxy. The adapter calls that interface and still passes through transaction/security advice where appropriate.

Benefits:

- JMX annotations do not get mixed into business APIs.
- The exporter inspects a class with a small management surface.
- Management commands go through an abstraction that can be tested and guarded.
- Easy to swap JMX for admin HTTP/CLI without modifying domain logic.
- AOP changes to the service have minimal impact on export.

If an overly broad AOP pointcut also proxies `BillingJmxAdapter`, recheck the adapter's runtime class; do not assume every adapter is always unproxied.

## 10. Solution 2: Declare Explicit Export Instead of Relying Only on Autodetect

Another option is not relying entirely on annotation discovery. Declare beans to export in `MBeanExporter.setBeans` with a specific ObjectName key:

```java
import java.util.Map;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.naming.KeyNamingStrategy;

MBeanExporter exporter = new MBeanExporter();

exporter.setNamingStrategy(new KeyNamingStrategy());
exporter.setBeans(Map.of(
    "com.example:type=BillingMonitor,name=Primary",
    billingJmxAdapter
));
```

Here `billingJmxAdapter` is a Spring-managed object. Explicit export avoids errors at the **candidate selection stage**, though you still need to ensure the exported object has a valid JMX interface or an assembler that converts POJOs into appropriate ModelMBeans.

Do not call `new BillingService()` to dodge proxies: doing so can lose dependency injection, transactions, and security.

If the goal is exporting a JDK-proxied service with methods absent from its interface, explicit export will not automatically add those methods to the proxy either. Changing the management surface or using an adapter is the right fix.

## 11. Solution 3: Design the Proxy Interface with All Required Methods

If the project has a valid reason to export the service directly, methods exposed via JMX must **actually be available** on the object the exporter receives. With a JDK proxy, this usually means they must exist on an interface implemented by the proxy.

```java
public interface BillingManagement {
    long getPendingInvoiceCount();
}
```

Service implementation:

```java
public class BillingService
        implements BillingOperations, BillingManagement {

    @Override
    public long getPendingInvoiceCount() {
        return 12;
    }

    @Override
    public void processInvoice(String invoiceId) {
        // ...
    }
}
```

However, adding an interface only solves method invocability. `@ManagedResource` and `@ManagedAttribute` metadata must still be located by the exporter in the right place. Annotations placed on an interface are not always equivalent to annotations on a target implementation because metadata rules and Java annotation inheritance differ.

When unsure, keep annotations on a dedicated adapter class and check `MBeanInfo` after registration.

## 12. Solution 4: Consider Class-Based Proxies, but Do Not Switch Blindly

Spring AOP can use class-based proxies (CGLIB) instead of JDK proxies. This proxy type subclasses the target, so it typically has a different method surface from a JDK proxy. However:

- `final` methods cannot be overridden to intercept.
- `private` methods cannot be proxied via overriding.
- Self-invocation can bypass advice.
- Some annotation discovery issues depend on the metadata source rather than proxy type alone.
- Enabling `proxyTargetClass` can affect the entire AOP configuration.

Therefore, class-based proxies are not a universal fix for autodetection failures. Use them when there is a valid AOP need, then verify JMX registration with integration tests.

## 13. Testing Differences Between Proxy and Target

Create a test using a Spring context with an actual advice enabled to ensure the bean is proxied. A sample assertion for the JMX surface:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.aop.support.AopUtils;

void assertBillingJmx(
        Object billingService,
        MBeanServer server
) throws Exception {

    assertTrue(AopUtils.isAopProxy(billingService));

    ObjectName name = new ObjectName(
        "com.example:type=BillingMonitor,name=Primary"
    );

    assertTrue(server.isRegistered(name));

    var info = server.getMBeanInfo(name);

    boolean found = java.util.Arrays.stream(info.getAttributes())
        .anyMatch(a -> a.getName().equals("PendingInvoiceCount"));

    assertTrue(found);
}
```

The test above assumes the environment is intentionally configured to create an AOP proxy. It needs a test context and the right exporter instance, and is insufficient if calling a plain class outside Spring.

With a dedicated adapter, you can test in two layers:

1. Unit test the adapter with a fake `BillingManagement`: getters/operations delegate properly.
2. Spring JMX integration test: the adapter is registered by the exporter, and MBeanInfo and invocations have the expected attributes/operations.

Especially when using Spring Boot auto-configuration, enable JMX in test configuration in a controlled way, e.g., `spring.jmx.enabled=true`, and avoid ObjectName collisions across tests running in the same JVM.

## 14. Cause and Evidence Matrix

| Symptom | Possible Cause | Evidence to Check |
| --- | --- | --- |
| Bean exists in context but MBean is missing | Autodetection did not select the bean | `getBean`, `isRegistered`, exporter config |
| Annotation on target but absent on runtime class | JDK proxy interface hides target metadata | `AopUtils.getTargetClass`, target metadata |
| MBean exists but missing attribute | Method not on proxy interface or not selected by assembler | `getMBeanInfo`, method annotations |
| MBean has attribute but reading fails | Proxy method uninvocable or getter error | `getAttribute`, nested exception |
| MBean disappears when transactions are enabled | Proxy strategy/bean lifecycle changed | Compare proxy type and exporter before/after |
| No startup exception | Bean skipped during autodetect | Exporter DEBUG logs, actual registrations |
| `NotCompliantMBeanException` occurs | Bean selected but export path non-compliant | Standard MBean/MXBean/assembler |
| `InstanceAlreadyExistsException` occurs | Duplicate ObjectName | Canonical name, other exporter/context |

This matrix helps pinpoint what to observe, not replace reproducing with your actual Spring version.

## 15. Safety Principles for Autodetection

Autodetection reduces configuration, but requires control:

- Do not export every business service simply because they have public methods.
- Use `@ManagedResource` on management components with small surfaces.
- For POJOs, use a metadata assembler to expose only marked methods.
- Ensure ObjectNames are unique, stable, and do not leak sensitive data.
- The JMX connector must have proper security; annotations do not create authorization.
- Management getters should read fast and have no side effects.
- Operations with impact need validation, authorization, and auditing.
- Have integration tests confirming `isRegistered`, `MBeanInfo`, `getAttribute`, and `invoke`.

If many services are proxied by AOP, consider using an explicit JMX adapter instead of relying on autodetect across multiple target/proxy layers.

## 16. Short Investigation Workflow

```text
@ManagedResource on implementation
             |
        Bean in context?
             |
      Yes -> Is bean a proxy?
             |
      Yes -> What is target class?
             |
  Does exporter read target metadata?
             |
       MBean registered?
         /          \
        No          Yes
        |            |
  autodetect /     Does MBeanInfo have
  naming /         the attribute?
  registration       |
                    Can it be invoked?
```

Diagnostic order:

1. Check bean name and instance from the Spring context.
2. Print runtime class, proxy type, and target class.
3. Confirm which class holds the annotations and which metadata source is used.
4. Check whether `MBeanExporter` has autodetection enabled and selects the bean.
5. Check the right `MBeanServer` and `ObjectName`.
6. If the MBean exists, inspect its surface with `getMBeanInfo`.
7. Test invoking getters/operations through the proxy.
8. If needed, switch to explicit export or a dedicated management adapter.

## 17. Takeaways

**A JDK dynamic proxy typically exposes only its interfaces; `@ManagedResource` on the target implementation is not automatically copied onto proxy interfaces or the runtime proxy class.** Therefore, an autodetection path inspecting only the proxy can skip the annotation, even when the original source code is valid. Spring can recover target metadata depending on configuration, so verify in practice. Distinguish detection from invocation, use `AopUtils.getTargetClass` and `MBeanServer.getMBeanInfo` to diagnose, and prefer a dedicated JMX adapter when you want a stable management boundary.
