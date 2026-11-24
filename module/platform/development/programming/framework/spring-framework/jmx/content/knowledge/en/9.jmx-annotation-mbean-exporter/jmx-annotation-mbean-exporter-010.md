# Limitations When Using Annotations While a Proxy Obscures the Target Class

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why a Spring bean carrying JMX annotations on the **target class** can still be exported incorrectly or fail to export when wrapped by a **Spring AOP proxy**.
- Distinguish target object, JDK dynamic proxy, CGLIB proxy, management interface, and JMX metadata.
- Understand the roles of \`AnnotationMBeanExporter\`, \`MetadataMBeanInfoAssembler\`, \`AnnotationJmxAttributeSource\`, and \`MBeanServer\`.
- Recognize symptoms: missing \`@ManagedAttribute\`/\`@ManagedOperation\`, \`NotCompliantMBeanException\`, wrong \`ObjectName\`, or the exporter picking up metadata from the proxy instead.
- Choose stable configurations: separating a management bean, using appropriate interfaces, controlling the export path, and verifying the actual MBean via \`MBeanInfo\`.
- Understand the risks of trying to unwrap proxies or switching proxy strategies solely so JMX annotations take effect.

## 2. Context: Where Do Annotations Live, and What Is the Actual Bean?

In Spring Framework, a bean can be declared as:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop:type=OrderMonitor,name=primary")
public class OrderMonitor {

    private int pendingCount;

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedOperation
    public void resetStatistics() {
        pendingCount = 0;
    }
}
\`\`\`

Looking at the source, we see \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\`. However, if the bean is affected by transactions, security, caching, retries, or Spring AOP advice, the instance retrieved from the application context may be a **proxy**, not the original target instance.

\`\`\`text
ApplicationContext
      |
      v
  bean "orderMonitor"
      |
      v
  [Spring AOP proxy] ------------> [OrderMonitor target]
         |                                  |
         |                                  +-- @ManagedResource
         |                                  +-- @ManagedAttribute
         |                                  +-- @ManagedOperation
         |
         +-- object an exporter may receive
\`\`\`

When a management component inspects the **proxy's class** or only the method list present on the proxy, annotation information on the target is not always visible as expected. The behavior depends on the proxy type and the mechanisms used by the Spring exporter/assembler.

**Core point:** Java annotations do not automatically mean metadata appears identically on every proxy class or every interface method. The exporter must resolve the right type/method and use an appropriate annotation lookup policy.

## 3. What Does AnnotationMBeanExporter Do?

\`AnnotationMBeanExporter\` is a component that helps export Spring beans as JMX MBeans based on annotation metadata. In Spring JMX, key annotations include:

- \`@ManagedResource\`: describes a management resource, optionally specifying ObjectName and description.
- \`@ManagedAttribute\`: describes a getter/setter exposed as a JMX attribute.
- \`@ManagedOperation\`: describes an operation invocable via JMX.
- \`@ManagedOperationParameter\`, \`@ManagedOperationParameters\`, \`@ManagedMetric\`, etc. when richer metadata is needed.

An annotation-driven exporter typically coordinates an **attribute source** reading metadata and an **MBeanInfo assembler** converting that metadata into \`MBeanInfo\`.

High-level flow:

\`\`\`text
Spring bean instance
       |
       v
AnnotationMBeanExporter / MBeanExporter
       |
       +-- detects @ManagedResource
       +-- finds @ManagedAttribute, @ManagedOperation
       +-- builds MBeanInfo via assembler
       +-- resolves ObjectName
       |
       v
MBeanServer.registerMBean(...)
       |
       v
JConsole / JMX client
\`\`\`

Each step can be influenced by proxies. For example, when looking up annotations on the bean type, the exporter may need to determine the target class; when invoking an operation, the proxy must actually expose that method; when determining the object name, the naming strategy must handle the target type properly.

### Distinguishing "exportable" from "correctly exposed"

There are at least three distinct scenarios:

1. **No MBean:** \`@ManagedResource\` is not detected, registration does not run, or registration fails.
2. **MBean exists but lacks attributes/operations:** export succeeds, yet JMX metadata does not reflect the annotated methods.
3. **Metadata exists but invoking operation fails:** metadata is generated, yet the method cannot be invoked via the proxy/interface or target logic throws an exception.

These symptoms have different causes and inspection steps. You cannot pinpoint the cause merely from seeing that the bean has annotations.

## 4. JDK Dynamic Proxy: Exposes Interfaces Only

A **JDK dynamic proxy** typically implements one or more Java interfaces. The proxy class does not directly inherit from the concrete target class. If Spring creates an interface-based proxy, implementation methods absent from the interface may not be callable through the proxy like concrete class methods.

Example:

\`\`\`java
public interface OrderService {
    int currentPendingCount();
}
\`\`\`

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop:type=OrderService,name=primary")
public class DefaultOrderService implements OrderService {

    @Override
    @ManagedAttribute
    public int currentPendingCount() {
        return 7;
    }

    // Not declared in OrderService.
    public void resetInternalCounters() {
        // ...
    }
}
\`\`\`

If \`DefaultOrderService\` is proxied by a JDK dynamic proxy implementing \`OrderService\`, callers work through \`OrderService\`, not directly with \`DefaultOrderService\`. This creates clear limitations:

- \`currentPendingCount()\` exists on the interface, so the proxy can forward calls to the target.
- \`resetInternalCounters()\` is not on the interface, so a JDK proxy implementing only \`OrderService\` does not expose this method for direct invocation.
- An annotation on an implementation method does not automatically become an annotation on the interface method under ordinary Java reflection.
- Spring's annotation lookup may support walking back to the target, yet **whether metadata can be found** and **whether the method can be invoked on the proxy** are two separate questions.

In practice, do not try to solve this simply by adding \`@ManagedOperation\` to \`resetInternalCounters()\` and expecting the proxy to immediately expose it. Clarify the export contract and proxy exposure.

## 5. CGLIB Proxy: Subclassing Does Not Eliminate Risk

A CGLIB proxy (class-based proxy) is typically a subclass of the target type. Therefore, it can expose more concrete class methods than a JDK dynamic proxy.

However, limitations remain:

- \`final\` methods cannot be overridden by CGLIB to apply advice.
- \`final\` classes cannot be subclassed by CGLIB.
- \`private\` methods cannot be overridden by a proxy as public methods.
- Searching annotations on the proxy class versus the target class can behave differently.
- Metadata readers, naming strategies, and Spring versions may differ in how they handle proxies.

CGLIB **does not automatically guarantee** every annotation on the target is recognized by the exporter. Nor does it solve all visibility, lifecycle, metadata, and invocation issues.

In particular, do not enable \`proxyTargetClass=true\` across the whole application just to handle JMX. Doing so can change how proxies behave for transactions/security/caching and how beans are injected/cast, causing broader impact than the management goal.

## 6. Java Annotations and Proxies: Why Doesn't Metadata Copy Automatically?

Java has important reflection rules:

- Class-level annotations do not appear on Java interfaces by default.
- \`@Inherited\`, if present, only applies to certain **class-level** inheritance cases, not as a general copy mechanism for method annotations.
- An interface method and an implementation method are two distinct reflection objects.
- A JDK proxy class is dynamically generated; it is not a subclass carrying all target annotations.
- A CGLIB subclass has an inheritance relationship, yet method metadata and how frameworks resolve overridden methods still require care.

Therefore, when JMX annotations reside on the target class, verify whether the exporter uses mechanisms such as **target-class resolution**, **merged annotation lookup**, or appropriate **AOP utilities**. How Spring handles this varies by version and configuration; do not claim every \`AnnotationMBeanExporter\` fails with proxies, nor assume every proxy is transparent.

## 7. Inspecting the Actual Bean: Proxy or Target?

Below is a development-only debugging snippet to identify the bean returned by Spring:

\`\`\`java
import org.springframework.aop.support.AopUtils;

public final class BeanInspection {

    public static void inspect(Object bean) {
        System.out.println("runtime class = " + bean.getClass());
        System.out.println("isAopProxy = " + AopUtils.isAopProxy(bean));
        System.out.println("isJdkProxy = " + AopUtils.isJdkDynamicProxy(bean));
        System.out.println("isCglibProxy = " + AopUtils.isCglibProxy(bean));
        System.out.println("target class = " + AopUtils.getTargetClass(bean));
    }
}
\`\`\`

Usage in context:

\`\`\`java
Object bean = applicationContext.getBean("orderService");
BeanInspection.inspect(bean);
\`\`\`

For example, a JDK proxy has a runtime class such as:

\`\`\`text
jdk.proxy2.$Proxy...
\`\`\`

and the target class may be \`DefaultOrderService\`.

Generated proxy class names are illustrative and depend on JDK/Spring. Do not write inspection logic based on strings like \`$Proxy\` or \`$$SpringCGLIB$$\`; use APIs such as \`AopUtils\`.

**Note:** \`AopUtils.getTargetClass\` attempts to infer the target class via Spring AOP capabilities; with special proxies or custom \`TargetSource\` implementations, results and target resolution capabilities can differ.

## 8. Inspecting JMX Metadata After Export

The most objective verification point is \`MBeanInfo\` from \`MBeanServer\`, because this is the API clients actually see.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxMetadataInspection {
    public static void inspect() throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName objectName = new ObjectName(
                "com.example.shop:type=OrderService,name=primary");

        if (!server.isRegistered(objectName)) {
            System.out.println("MBean not yet registered");
            return;
        }

        MBeanInfo info = server.getMBeanInfo(objectName);

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf("ATTR %s read=%s write=%s%n",
                    attribute.getName(),
                    attribute.isReadable(),
                    attribute.isWritable());
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.println("OP " + operation.getName());
        }
    }
}
\`\`\`

This step **verifies actual export behavior**, rather than just looking for annotations in source code. With Spring, ensure you connect to the exact \`MBeanServer\` used by the exporter; an application may configure a custom server instead of the platform server.

### Analyzing results

- If \`isRegistered\` returns \`false\`: check whether the exporter ran, whether the bean was scanned, and whether the ObjectName is accurate.
- If the MBean exists but attributes are missing: check attribute source/assembler, annotated methods, interfaces, and proxy.
- If metadata lists the operation yet \`invoke\` fails: check method signature, invokability through the proxy, access permissions, and errors from the target.
- If \`ObjectName\` differs from expectations: check \`@ManagedResource\`, naming strategy, exporter configuration, and naming convention.

Do not generalize from a single local success that all proxy modes behave identically. A bean without AOP applied may work directly, yet change its runtime type once \`@Transactional\` or \`@Cacheable\` is added.

## 9. MBeanExporter and Assembler: Boundaries to Understand

In Spring JMX, \`MBeanExporter\` can coordinate components such as:

| Component | Role |
|---|---|
| \`AnnotationMBeanExporter\` | Exports annotated beans via the annotation-based mechanism |
| \`AnnotationJmxAttributeSource\` | Reads metadata from \`@Managed...\` annotations |
| \`MetadataMBeanInfoAssembler\` | Builds attributes/operations metadata from the metadata source |
| \`MetadataNamingStrategy\` | Derives ObjectName from resource metadata |
| \`MBeanServer\` | JMX registry and runtime API |

Note that exact class names and configuration APIs can vary depending on the Spring version. During implementation, consult the API documentation for your running version.

How to read common failures:

\`\`\`text
Annotation present on target
           |
           +-- exporter fails to find annotation?
           |
           +-- assembler inspects proxy method?
           |
           +-- naming strategy misses @ManagedResource?
           |
           +-- proxy does not expose operation?
           |
           +-- duplicate ObjectName registration?
\`\`\`

Do not solve every case with a global proxy setting. Pinpoint **which stage in the pipeline** drops metadata or fails invocation.

## 10. Preferred Solution: Separate Management Bean from AOP-Proxied Service

A simple and stable design uses a dedicated **management adapter** for JMX. The business service can still be AOP-proxied, while the management bean defines a small, intentional management API.

Example:

\`\`\`java
public interface OrderProcessingService {
    int pendingCount();
    void retryFailed();
}
\`\`\`

Service implementation that may use transactions:

\`\`\`java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DefaultOrderProcessingService
        implements OrderProcessingService {

    @Override
    public int pendingCount() {
        return 12; // Replace with actual metric.
    }

    @Override
    @Transactional
    public void retryFailed() {
        // Business operation with transaction.
    }
}
\`\`\`

Management bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=primary")
public class OrderManagement {

    private final OrderProcessingService service;

    public OrderManagement(OrderProcessingService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Pending order count")
    public int getPendingCount() {
        return service.pendingCount();
    }

    @ManagedOperation(description = "Retry failed orders")
    public void retryFailedOrders() {
        service.retryFailed();
    }
}
\`\`\`

Advantages:

1. \`OrderManagement\` is solely responsible for exposing the management contract.
2. \`DefaultOrderProcessingService\` can be AOP-proxied and remain injected via its interface.
3. JMX annotations live on a clean, controllable management type.
4. Operators only see the selected attributes/operations.
5. Calls from the management bean flow through the service's Spring proxy, preserving required transaction/advice behavior.

**Note:** extracting an adapter reduces complexity, but does not guarantee it will never be proxied; if a broad AOP pointcut also applies to the adapter, inspect the runtime class and metadata of the management bean itself.

The \`retryFailedOrders\` operation has real business impact; expose it only if security/operations permit. This is an illustrative example, not a recommendation to expose sensitive actions over JMX without controls.

## 11. Interface-Based Solution: Designing a Clear Management Contract

If you want a plain Java JMX Standard MBean, you can create an interface:

\`\`\`java
public interface OrderMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}
\`\`\`

and class:

\`\`\`java
public class OrderMonitor implements OrderMonitorMBean {
    @Override
    public int getPendingCount() {
        return 0;
    }

    @Override
    public void resetStatistics() {
        // Reset observation-only counters.
    }
}
\`\`\`

\`OrderMonitorMBean\` is the **management interface** per Standard MBean conventions. When using a \`StandardMBean\` wrapper, you can also specify the interface explicitly when the name does not follow the convention.

This design differs from annotation-driven export: the contract is defined by an interface rather than annotation metadata. It can reduce reliance on finding annotations on a concrete target class, though you must still ensure the exporter receives the right object/target and invocation path remains valid if the bean is proxied.

A JDK proxy only exposes the interfaces it implements. Thus, if you want a JMX operation that exists only on the concrete class and not on an interface exposed by the proxy, you can still run into issues. A reliable approach is defining the management API on a suitable adapter/bean and testing it via \`MBeanServer\`.

## 12. Controlled Solution: Explicit Export Configuration

Some projects register beans via \`MBeanExporter\` with fixed ObjectNames instead of relying entirely on automatic annotation scanning.

Illustrative example:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    MBeanExporter orderMonitorExporter(OrderMonitorMBean monitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
                "com.example.shop.orders:type=OrderMonitor,name=primary",
                monitor));
        return exporter;
    }
}
\`\`\`

The snippet illustrates declaring an ObjectName → bean mapping. It assumes the application has an eligible \`OrderMonitorMBean\` bean and the export configuration does not conflict with another exporter.

**Important:** merely configuring \`setBeans\` does not turn every proxy into a compliant MBean. If the proxy is incompatible with JMX metadata/invocation, use a properly designed management adapter or \`StandardMBean\`, then verify registration and \`MBeanInfo\`.

Do not register the same ObjectName from two exporters or from both a Spring exporter and manual code, as \`InstanceAlreadyExistsException\` can occur.

## 13. Do Not Unwrap Proxies Arbitrarily

A common hasty workaround is extracting the target object behind the proxy and exporting it directly. This carries risks:

- Bypasses advice from \`@Transactional\`, \`@Secured\`, \`@Cacheable\`, retries, or other interceptors.
- Turns management invocations into calls without the expected transaction/security context.
- For proxies using a custom \`TargetSource\`, the target instance may not be fixed or safe to retain long-term references to.
- Registration/unregistration lifecycles and dependency initialization can become complicated.

Having to inspect the target for **metadata** does not mean you should **invoke the target directly**. Metadata discovery and invocation are two separate responsibilities.

Nor should you switch the entire application from JDK proxies to CGLIB or vice versa solely to solve annotation lookup. Changing the proxy mode can affect method interception and type injection across the whole application context.

## 14. Interaction with @Transactional, @Cacheable, and @Async

### @Transactional

\`\`\`java
@Service
public class OrderServiceImpl implements OrderService {
    @Transactional
    public void updateOrderStatus() {
        // ...
    }
}
\`\`\`

If a JMX operation calls the target directly and bypasses the Spring proxy, transaction advice may not execute. Having a management adapter call through the injected service proxy is usually much cleaner.

### @Cacheable

A bean proxied for caching can cause the runtime class to differ from the target class. JMX annotations on target methods must be recognized properly by the metadata reader. Avoid placing \`@ManagedOperation\` on business cache methods if they have no management purpose.

### @Async

A JMX operation calling an \`@Async\` method on a service proxy can return before the work completes. This affects the semantics of the management operation: operators must know whether the command means "accepted" or "completed." Expose job status via a separate attribute or metric if the operation triggers asynchronous work.

An important Spring AOP nuance is **self-invocation**: calling a method from another method on the same target instance normally bypasses the proxy; advice may not apply. Having a management adapter call through the service proxy makes maintaining clean boundaries easier.

## 15. MBeanInfo and Invocation: Practical Diagnostic Example

Suppose the \`PaymentService\` bean is annotated:

\`\`\`java
@ManagedResource(objectName =
        "com.example.shop.payments:type=PaymentService,name=primary")
public class PaymentServiceImpl implements PaymentService {

    @ManagedAttribute
    public int getPendingCount() {
        return 8;
    }

    @ManagedOperation
    public void resetMetrics() {
        // ...
    }
}
\`\`\`

yet the \`PaymentService\` interface only declares:

\`\`\`java
public interface PaymentService {
    int getPendingCount();
}
\`\`\`

and Spring creates a JDK dynamic proxy.

Analysis:

1. If \`AnnotationMBeanExporter\` cannot retrieve \`@ManagedResource\` from the target, the bean may be skipped.
2. If the exporter finds the annotation but inspects only public methods on the proxy/interface, \`resetMetrics\` may not be exposed as expected.
3. If metadata still describes \`resetMetrics\` yet the call cannot pass through the proxy, JMX invocation may fail.
4. If \`resetMetrics\` is added to the interface, the proxy can expose the method, though annotation metadata and security policy still need verification.
5. Extracting a \`PaymentManagement\` bean containing only management APIs and calling \`PaymentService\` via its interface typically clarifies the export target.

These are **diagnostic possibilities**, not a claim that a specific Spring version definitely exhibits this bug. Read the actual stack trace/exporter logs and \`MBeanInfo\` to confirm.

## 16. Configuration and Observation Checklist in a Spring Application

When an annotation-driven MBean does not behave as expected, check in a logical order:

1. Does the bean actually exist in the \`ApplicationContext\` and has it initialized?
2. Is the bean an AOP proxy? What does \`AopUtils.isAopProxy(bean)\` return?
3. Is the proxy JDK or CGLIB? What is the target class?
4. On which class/interface is \`@ManagedResource\` placed? Where are method annotations placed?
5. Which exporter is actually configured? Are there duplicate exporters?
6. Which \`MBeanServer\` is used? Is it the exact server you are inspecting with JConsole/client?
7. Which ObjectName was chosen? Does it conflict with an existing MBean?
8. Does \`MBeanInfo\` list the expected attributes and operations?
9. If \`invoke\` fails, do method signatures match and does the proxy expose that method?
10. If JMX calls a service method, do transaction/security/cache advices run through the proxy?

This checklist is for technical investigation, not a demand to change every setting if things are currently working properly.

## 17. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Annotations on target, yet MBean does not appear | Annotation lookup sees proxy type, exporter skips bean, or exporter not enabled | Check export config, target class resolution, and ObjectName |
| MBean exists, yet attributes are missing | Metadata assembler only sees interface/proxy methods or annotations misplaced | Check \`MBeanInfo\`, getters/setters, and annotation source |
| \`NotCompliantMBeanException\` | Bean/proxy incompatible with Standard MBean or export path | Use proper adapter/interface, verify assembler and wrapper |
| Operation cannot be invoked | Method not exposed on proxy, signature mismatch, or target throws error | Extract management adapter or add right interface, read exception |
| Transaction does not run on JMX call | Bypassed AOP proxy to invoke target | Call service through injected proxy |
| Runtime type differs from source class | Spring created JDK/CGLIB proxy | Use \`AopUtils\` instead of manual class name checks |
| Duplicate ObjectName | Two exporters register the same name | Assign one export owner, unify lifecycle |
| Metadata right locally, wrong in staging | Different advice/auto-config enabled per environment | Check proxy mode and actual deployment configuration |
| Enabling CGLIB does not fix it | Metadata/registration issue not caused by JDK proxy | Diagnose export pipeline instead of changing proxy mode |
| Changing naming strategy breaks dashboards | ObjectName changed unexpectedly | Keep naming contract stable, plan client updates |

## 18. Practice

### Exercise A — Reading proxy structure

Given an \`InventoryService\` interface with method \`int availableCount()\` and implementation \`InventoryServiceImpl\` adding \`resetInternalCache()\`. Suppose Spring uses a JDK proxy. Explain:

- Which interface method the proxy can expose.
- Why \`resetInternalCache()\` does not automatically become a method on the proxy.
- Whether an annotation on the implementation method automatically appears when calling Java reflection on the interface method.

**Hint:** Distinguish proxy method surface from annotation lookup.

### Exercise B — Designing a management adapter

Create \`InventoryManagement\` with:

\`\`\`java
@ManagedResource(objectName =
        "com.example.shop.inventory:type=InventoryMonitor,name=primary")
public class InventoryManagement {
    private final InventoryService inventoryService;

    public InventoryManagement(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @ManagedAttribute
    public int getAvailableCount() {
        return inventoryService.availableCount();
    }
}
\`\`\`

Explain why the management bean exposes only the needed attribute and still calls the service through its proxy.

### Exercise C — Inspecting metadata

After exporting \`InventoryManagement\`, use \`MBeanServer.getMBeanInfo(ObjectName)\` and print the attribute list. Confirm that \`AvailableCount\` is actually published. Then try running in a configuration with an AOP proxy on the service and compare observations.

### Exercise D — Choosing a solution

You have a \`@Transactional\` service bean with \`@ManagedOperation\` on a method absent from the service interface, and the exporter fails to find the operation. State two options:

1. Add a proxy-exposed management contract and valid export configuration.
2. Extract a JMX management bean calling the service proxy via its interface.

Explain the risk of unwrapping the proxy and registering the target directly.

### Exercise E — Distinguishing errors

An MBean appears in JConsole, yet the Operations tab is empty. Should you switch to CGLIB immediately?

No. First read \`MBeanInfo\`, verify \`@ManagedOperation\`, inspect the active exporter/assembler, and check the runtime proxy type and method accessibility. Only after gathering evidence should you choose to modify the relevant configuration.

## 19. Self-Check Questions

**1. Is \`@ManagedResource\` on a target class guaranteed to be visible on every proxy class?**

No. It depends on the proxy mechanism, ordinary Java reflection, and the framework's lookup strategy.

**2. Does a JDK dynamic proxy expose every public method of the implementation?**

No. It exposes methods of the interfaces that the proxy implements.

**3. Does a CGLIB proxy eliminate every limitation of annotation-driven JMX?**

No. Constraints around subclassing/final methods, annotation lookup, and export configuration still apply.

**4. Why should administrators inspect \`MBeanInfo\`?**

Because this is the JMX metadata clients actually see, including published attributes, operations, and notifications.

**5. Should you bypass Spring proxies so JMX calls the target directly?**

Not as a default practice. It can bypass transactions, security, or other advice.

**6. Is a management adapter guaranteed never to be proxied?**

No. Broad pointcuts can still apply; verify the configuration.

**7. Are the Spring bean name and ObjectName the same?**

No. Bean names serve the Spring container, whereas ObjectNames identify MBeans in \`MBeanServer\`.

## 20. Key Takeaways

- Annotation-driven JMX depends on **metadata discovery**, **naming**, and **invocation**; proxies can affect each step differently.
- JDK proxies primarily expose interface methods; CGLIB proxies subclass the target but do not eliminate all limitations.
- Annotations on an implementation do not automatically become annotations on interface methods under ordinary Java reflection.
- Do not infer proxy errors solely by looking at class source; inspect \`AopUtils\`, the exporter, and \`MBeanInfo\`.
- Extracting a management adapter is a maintainable design when business services use AOP, transactions, caching, or security.
- Do not arbitrarily unwrap the target to invoke it directly via JMX, because important advice can be bypassed.
- Keep ObjectNames stable and check permissions when exposing operations with side effects.
- To know the application's true behavior, inspect **actual registered MBeans and metadata** rather than merely counting annotations.

## 21. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`AnnotationMBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Spring Framework Javadoc — \`AopUtils\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
