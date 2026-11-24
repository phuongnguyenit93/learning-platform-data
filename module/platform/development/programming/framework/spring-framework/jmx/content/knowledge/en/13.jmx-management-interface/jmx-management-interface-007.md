# Choosing a single metadata source to avoid unpredictability in Spring JMX

## 1. Learning objectives

After this lesson, you will be able to:

- Explain what **management metadata** in JMX consists of and why a single source defining the contract must be clearly established for each MBean.
- Distinguish Standard MBean interfaces, MXBean interfaces, `@ManagedResource`/`@ManagedAttribute`/`@ManagedOperation` annotations, metadata assemblers, and `MBeanExporter` configuration.
- Recognize cases where the same bean is interpreted differently by multiple export mechanisms, naming strategies, or assemblers.
- Design a **single source of truth** for attributes, operations, descriptions, and the ObjectName of each MBean.
- Choose verification via `MBeanServer.getMBeanInfo()` rather than relying only on code annotations or interfaces.
- Establish coordination rules across business services, management adapters, Spring AOP proxies, collectors, and operational tools.

## 2. The problem: one MBean with metadata declared in multiple places

In Java Management Extensions (JMX), the **MBean management interface** defines what operators can observe or control. With a Standard MBean, the interface follows the `ClassNameMBean` naming convention; with an MXBean, the interface is recognized as an MXBean; with Spring, metadata can be declared via annotations and mapped through an assembler.

When multiple mechanisms appear together in a project, for example:

```text
OrderMonitorMBean.java       --> declares getPendingCount(), reset()
OrderMonitor.java            --> @ManagedAttribute, @ManagedOperation
Spring configuration         --> MBeanExporter + naming strategy
Another auto-configuration   --> auto-scans/exports @ManagedResource
```

developers may assume all declarations will be “merged” into the same MBean. In reality, **JMX metadata is generated according to the export mechanism in use**; there is no universal rule that independent metadata sources are always merged with the same precedence.

The result can be:

- Attributes/operations appear differently than expected.
- An attribute has a description in an annotation, yet JConsole displays a different description.
- The MBean has a name different from the naming convention.
- The same ObjectName is registered by two exporters, causing a conflict.
- An AOP proxy causes annotation lookup to resolve a class/interface other than expected.
- A refactoring changes metadata even though the Java business API did not change.

**Core principle:** Each MBean should have **one clearly designated management contract**, and one primary export path responsible for turning that contract into `MBeanInfo` in `MBeanServer`.

## 3. What does JMX management metadata include?

An `MBeanInfo` typically describes:

| Component | Meaning | Example |
|---|---|---|
| **Attributes** | Readable/writable properties, data types, descriptions | `PendingCount` (int, read-only) |
| **Operations** | Management actions and parameters | `resetStatistics()` |
| **Constructors** | Constructor metadata when applicable | Constructor descriptions |
| **Notifications** | Notification types the MBean can emit | `queue.threshold.exceeded` |
| **Description** | Description of the MBean or member | `Order queue monitor` |
| **Descriptors** | Extended metadata per the JMX model | Units, display conventions depending on assembler |

**ObjectName** is the identifier used to register and query the MBean; it is not merely a field inside `MBeanInfo`. In Spring configuration, ObjectName can come from `@ManagedResource.objectName`, an explicitly assigned name, or a naming strategy.

Therefore, when speaking of “one metadata source”, two aspects must be clarified:

1. **Management contract:** where are attributes/operations/notifications/descriptions declared?
2. **Registration contract:** where are ObjectName and the export lifecycle decided?

A shared naming convention may exist, but exporters should never compete to choose an ObjectName for the same instance.

## 4. Common metadata sources in Java/Spring JMX

### 4.1. Standard MBean interface

Example:

```java
public interface OrderMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}

public class OrderMonitor implements OrderMonitorMBean {
    @Override
    public int getPendingCount() {
        return 17;
    }

    @Override
    public void resetStatistics() {
        // Reset counters only.
    }
}
```

With the Standard MBean convention, **the `OrderMonitorMBean` interface** is the contract interpreted by JMX introspection into attributes and operations.

Other public methods on `OrderMonitor` that are not in the interface do not automatically become JMX operations.

Advantages:

- Explicit contract, easy to read and test.
- The Java compiler helps guarantee the implementation satisfies the interface.
- No need to add separate annotations on every method if only basic metadata is needed.

Trade-offs:

- Richer descriptions or metadata may require additional mechanisms.
- Must follow naming conventions or use an appropriate `StandardMBean` wrapper.
- Using a plain JMX interface alone does not determine object name, connection permissions, or lifecycle.

### 4.2. MXBean interface

An MXBean also derives its contract from an interface, but has rules for mapping Java data to **open types** used for JMX interoperability. Example:

```java
public interface QueueMetricsMXBean {
    int getPendingCount();
    String getQueueName();
}
```

When choosing an MXBean, the management contract should reside in the defined MXBean interface. Do not simultaneously add another layer of annotation metadata that readers might mistake for the authoritative interpreted source.

MXBeans fit when you want to publish structured data exchangeable across processes/clients without distributing all custom server classes. Not every Java type has a direct mapping; you need to understand MXBean open-type rules.

### 4.3. Annotation-driven Spring JMX

Spring provides:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=primary",
    description = "Order monitoring endpoint")
public class OrderManagement {

    @ManagedAttribute(description = "Pending orders in this JVM")
    public int getPendingCount() {
        return 17;
    }

    @ManagedOperation(description = "Reset monitoring counters")
    public void resetStatistics() {
        // ...
    }
}
```

Here, the annotation group is the **management metadata source**. To take effect, the bean must be processed by an appropriate exporter/assembler. Simply putting annotations on a Java class does not guarantee the MBean appears on MBeanServer.

Benefits:

- Easy to add descriptions and method details.
- Can use a dedicated JMX management adapter without needing a `*MBean` interface.
- Fits Spring applications using component scanning/export.

Trade-offs:

- Metadata discovery depends on the exporter/assembler and how proxies are handled.
- Keep annotations centralized in the management layer rather than scattered across layers.
- Changing export configuration can alter the resulting metadata.

### 4.4. Dynamic MBean or ModelMBean

`DynamicMBean` allows a component to supply `getMBeanInfo()` and handle attributes/operations itself. `ModelMBean` has descriptors and detailed metadata configuration.

These are deeply customizable management models suitable for certain framework/plugin scenarios. However, once dynamic metadata is chosen, **do not simultaneously treat Standard MBean naming conventions and Spring annotations as two competing contracts** without a clear unified design.

## 5. Why does “combining everything” produce unpredictable behavior?

Suppose:

```java
public interface PaymentMonitorMBean {
    int getPendingCount();
}
```

Meanwhile, the implementation also has annotations:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.payments:type=Monitor,name=main")
public class PaymentMonitor implements PaymentMonitorMBean {

    @Override
    @ManagedAttribute(description = "Payments waiting")
    public int getPendingCount() {
        return 12;
    }

    @ManagedOperation(description = "Reconcile payment states")
    public void reconcilePayments() {
        // ...
    }
}
```

A developer might expect both `PendingCount` from the interface and `reconcilePayments()` from the annotation to be published.

However:

- If the bean is introspected by JMX as a **Standard MBean**, the primary contract is `PaymentMonitorMBean`; `reconcilePayments()` is not in that interface.
- If Spring uses an **annotation-based metadata assembler**, attributes/operations are selected by that mechanism's annotations; `reconcilePayments()` may appear.
- If **two exporters** both try to register the ObjectName, one registration can fail with `InstanceAlreadyExistsException`.
- If the bean is wrapped in a JDK dynamic proxy, `reconcilePayments()`—not being on the interface—may not be exposed by the proxy, creating additional metadata/invocation issues.

These are consequences depending on the **actual export path**, with no universal “interface always wins over annotation” precedence rule across all Spring configurations.

The goal is not to forbid interfaces and annotations from coexisting in source code, but to **avoid letting two sources be interpreted as public contracts simultaneously without clearly defining the metadata selection mechanism**.

## 6. Single source of truth rule for an MBean

A project-level policy can be defined:

> Each ObjectName has exactly one management owner and one recognized mechanism defining attributes/operations. Everything else is an implementation detail or supplementary documentation, not a second contract.

Specific rules:

1. **Choose a contract style:** Standard MBean, MXBean, annotation-driven, or DynamicMBean.
2. **Choose an export owner:** a designated MBeanExporter or JMX registration mechanism.
3. **Choose a naming strategy:** explicit ObjectName or a standard factory/naming strategy.
4. **Do not export the same bean twice** under the same ObjectName using different mechanisms.
5. **Do not scatter management annotations** across multiple services/interfaces expecting Spring to merge them as desired.
6. **Verify actual metadata** via MBeanInfo after the application starts.
7. **Treat metadata changes like API contract changes:** evaluate impact on JConsole, exporters, dashboards, and automation.

This policy does not require every MBean across the whole company to use the same style. One system may use Standard MBeans for libraries and Spring annotations for internal adapters, provided each MBean has one clear contract source.

## 7. Approach A — Using an interface as the primary source

If you want the management interface to be the sole contract, design it as:

```text
OrderMonitorMBean.java   <-- management contract
         |
         v
OrderMonitor.java        <-- implementation
         |
         v
MBeanServer              <-- registered by ObjectName
```

Runnable example without Spring:

**`OrderMonitorMBean.java`**

```java
public interface OrderMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}
```

**`OrderMonitor.java`**

```java
public class OrderMonitor implements OrderMonitorMBean {
    private int pendingCount = 5;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void resetStatistics() {
        pendingCount = 0;
    }

    public void importOrders() {
        // Internal API, not in the management interface.
    }
}
```

**`StandardMBeanDemo.java`**

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class StandardMBeanDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=OrderMonitor,name=main");

        server.registerMBean(new OrderMonitor(), name);
        try {
            System.out.println(
                    server.getAttribute(name, "PendingCount"));
            server.invoke(name, "resetStatistics",
                    new Object[0], new String[0]);
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

In this approach:

- The interface is the single source of truth for the API surface.
- The implementing class does not add `@ManagedAttribute` to “extend” the contract.
- The ObjectName is decided at registration or by a dedicated factory.
- JMX clients use attribute `PendingCount` and operation `resetStatistics`, without seeing `importOrders`.

If rich descriptions are needed, you can intentionally choose another metadata mechanism, provided you **clearly state where the API is decided** and verify the result.

## 8. Approach B — Using an annotation-driven management adapter

In a Spring application, a dedicated management adapter is an easy-to-maintain model:

```text
OrderProcessingService (business interface)
              ^
              |
DefaultOrderProcessingService (business logic + AOP)
              ^
              | called through proxy
              |
OrderManagement (JMX annotations)
              |
              v
Annotation-aware exporter -> MBeanServer
```

Example:

```java
public interface OrderProcessingService {
    int pendingCount();
}
```

```java
import org.springframework.stereotype.Service;

@Service
public class DefaultOrderProcessingService
        implements OrderProcessingService {

    @Override
    public int pendingCount() {
        return 5;
    }
}
```

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=main",
    description = "Read-only order monitoring")
public class OrderManagement {

    private final OrderProcessingService service;

    public OrderManagement(OrderProcessingService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Pending orders in local instance")
    public int getPendingCount() {
        return service.pendingCount();
    }
}
```

In this approach:

- All `@Managed...` annotations for this MBean reside on `OrderManagement`.
- The business service does not need to carry JMX annotations.
- The Spring exporter must be enabled with an appropriate annotation-aware assembler.
- Do not create `OrderManagementMBean` just to define another contract if annotations have been chosen as the source of truth.
- If the service is Spring AOP-proxied, the management adapter calls through the service interface to keep advice and boundaries clear.

**Note:** The adapter itself can still be AOP-proxied by a broad pointcut. In that case, verify target-class resolution, method accessibility, and actual metadata. A single source of truth resolves contract ambiguity, not every proxy issue by itself.

## 9. Approach C — MXBean for strongly typed management data

If the system wants clients outside the JVM to read complex data via open types, you can choose MXBean:

```java
public interface QueueStatusMXBean {
    int getPendingCount();
    String getState();
}
```

With MXBean:

- The MXBean interface is the contract.
- Data types must follow MXBean mapping rules.
- Use a stable `ObjectName` and register via the appropriate mechanism.
- Do not build a competing layer of annotation contracts unless there is a clear reason and explicit configuration.

The difference between Standard MBean and MXBean is not “one has metadata and the other does not”; both have metadata. MXBean has rules for mapping data types to Open MBean types to increase interoperability.

## 10. One export owner: avoiding registering an MBean twice

Even with a single metadata contract, errors can still occur if two exporters register the bean.

Architecture to avoid:

```text
Spring @ManagedResource scanning ------+
                                       |
Manual MBeanExporter ------------------+--> same ObjectName
                                       |
Manual server.registerMBean -----------+
```

Two register calls with the same ObjectName in one MBeanServer cannot both succeed if the name is already taken. JMX may throw `InstanceAlreadyExistsException`, or Spring may apply a registration handling policy depending on configuration.

Do not treat an “ignoreExisting” policy (if configured on the exporter) as a standard substitute for defining ownership, because then the **actually registered** metadata depends on initialization order. A more stable approach:

- Document which component is responsible for exporting each ObjectName.
- Use only one registration path for the same MBean.
- Check whether auto-configuration or annotation scanning overlaps with manual mappings.
- Tie unregistration to the appropriate lifecycle.
- If the implementation needs to change, update the existing owner rather than adding a second exporter.

Uniqueness applies within the **same MBeanServer**; multiple JVMs can have the same ObjectName without colliding.

## 11. Naming metadata: ObjectName also needs one owner

An MBean can be named from:

- `@ManagedResource(objectName="...")`.
- `MBeanExporter.setBeans` mapping.
- `ObjectNamingStrategy` or a custom factory.
- `ObjectName` passed to `MBeanServer.registerMBean`.
- Framework-specific conventions.

Do not let multiple places independently decide different names for the same MBean.

Example:

```java
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox")
public class QueueManagement { /* ... */ }
```

yet the exporter mapping uses:

```text
com.example.shop.orders:type=OrderQueue,name=primary
```

If both are treated as naming contracts, operators will not know which one to look for. Depending on the export mechanism, one name may be chosen or another exporter may register an extra MBean.

**Recommended policy:** Choose one of the two:

1. **ObjectName directly on `@ManagedResource`:** suitable for fixed names and dedicated adapters.
2. **ObjectName in a naming factory/export configuration:** suitable when environment variables, tenants, or instances are needed; avoids hardcoding deployment details in the class.

Do not use both as equal requirements. If both metadata and mapping must exist at the same time, state clearly which mapping is authoritative and write tests verifying the actual registered ObjectName.

## 12. How can metadata from interfaces and annotations differ?

Consider:

```java
public interface WorkerMonitorMBean {
    int getActiveThreads();
    void stop();
}
```

Implementation:

```java
@ManagedResource(
    objectName = "com.example.shop:type=WorkerMonitor,name=main")
public class WorkerMonitor implements WorkerMonitorMBean {

    @Override
    @ManagedAttribute(description = "Currently active threads")
    public int getActiveThreads() {
        return 4;
    }

    @Override
    public void stop() {
        // ...
    }

    @ManagedOperation(description = "Reset counters")
    public void resetCounters() {
        // ...
    }
}
```

Expected results differ by contract:

| Method | Standard MBean interface | Annotation-driven assembler |
|---|---|---|
| `getActiveThreads()` | Attribute `ActiveThreads` | Attribute if annotation is recognized |
| `stop()` | Operation `stop` | Not annotated in the example |
| `resetCounters()` | Not in interface | Operation if annotation is recognized |

Therefore, a client tool may see `stop` but not `resetCounters`, or vice versa, depending on the export path. This illustrates contract divergence; the specific runtime result must be confirmed on the registered MBean.

**Do not write tests by simply counting annotations in source** if the system chose an interface as the contract. And do not use the interface method list as the baseline if the annotation assembler is designated as the metadata source.

## 13. AOP proxies make multiple metadata sources even riskier

Spring AOP can create a JDK dynamic proxy or a class-based proxy. An `OrderMonitor` class with JMX annotations whose runtime bean is a proxy can cause:

- Class-level annotations to be looked up on the target or proxy depending on the mechanism.
- A JDK proxy interface to expose only interface methods.
- An annotated method not on the proxy interface not to be callable as expected.
- CGLIB restrictions on `final` classes/methods.
- Naming strategy inspecting a runtime type different from the declared type.

When both a `*MBean` interface and `@Managed...` annotations exist, investigators also have to figure out which metadata discovery takes precedence. A single contract dramatically reduces the hypotheses to check.

Proxy inspection example:

```java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("orderManagement");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

This is illustrative debug code in a context with `applicationContext` available. Do not manually unwrap the target and export it directly if doing so bypasses security/transaction/caching advice.

## 14. Verifying the source of truth with MBeanInfo

Whether choosing an interface or annotations, **MBeanServer is the final data source for JMX clients**. After exporting, read the real metadata:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class MBeanContractInspection {
    public static void printContract() throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=OrderMonitor,name=main");

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                    "Expected MBean is not registered");
        }

        MBeanInfo info = server.getMBeanInfo(name);

        System.out.println("MBean: " + name);
        System.out.println("Description: " + info.getDescription());

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf("ATTRIBUTE %s type=%s read=%s write=%s%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable());
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.printf("OPERATION %s%n",
                    operation.getName());
        }
    }
}
```

This snippet assumes the MBean has been exported to the **platform MBeanServer**; if Spring is configured with a custom server, use that exact instance.

Inspecting `MBeanInfo` helps verify:

- Whether attribute `PendingCount` exists and is read-only per contract.
- Which operations are actually published.
- Whether description/parameter metadata was generated by the assembler.
- Whether there is any discrepancy between source code and the client-visible contract.

To verify stability across builds, you can write an integration test checking the set of required attributes/operations and the set of operations that must not be published (especially sensitive methods).

## 15. Testing the JMX contract without relying on implementation internals

For a Standard MBean, a test can:

1. Create an isolated `MBeanServer` for testing via `MBeanServerFactory.createMBeanServer()`.
2. Register the MBean with a test ObjectName.
3. Read `MBeanInfo`.
4. Compare the attribute/operation lists against the contract.
5. Unregister in `finally`.

Example:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

public class ContractTestExample {
    public static void verify() throws Exception {
        MBeanServer server = MBeanServerFactory.createMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.test:type=OrderMonitor");

        server.registerMBean(new OrderMonitor(), name);
        try {
            var info = server.getMBeanInfo(name);

            Set<String> attributes = Arrays.stream(info.getAttributes())
                    .map(x -> x.getName())
                    .collect(Collectors.toSet());

            Set<String> operations = Arrays.stream(info.getOperations())
                    .map(x -> x.getName())
                    .collect(Collectors.toSet());

            if (!attributes.contains("PendingCount")) {
                throw new AssertionError("Missing PendingCount");
            }
            if (!operations.contains("resetStatistics")) {
                throw new AssertionError("Missing resetStatistics");
            }
            if (operations.contains("importOrders")) {
                throw new AssertionError("Internal API leaked to JMX");
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

This is a “plain Java assertion” example to show the logic; in a real project, use JUnit/AssertJ or the corresponding test framework. Do not treat this plain JMX test as a replacement for a Spring integration test if the actual contract is built by an annotation assembler.

For annotation-driven export, the test should start a Spring context with the right exporter/assembler/beans, then read `MBeanInfo` from the MBeanServer used by the exporter.

## 16. Which option should you choose for your project?

| Scenario | Usually suitable metadata source | Notes |
|---|---|---|
| Java without Spring | Standard MBean interface | Easy to understand with minimal dependencies |
| Need interoperable open types | MXBean interface | Verify complex type mappings |
| Spring app, want annotation descriptions | Management adapter + `@Managed...` | Configure annotation-aware exporter |
| Library with existing Standard MBean | Keep library interface | Do not wrap with unnecessary annotations |
| Domain/ObjectName needs deployment config | Naming factory or exporter mapping | Single naming owner |
| Business bean with many AOP advices | Dedicated adapter exposing small management API | Do not bypass the service proxy |
| Need runtime-dynamic metadata | DynamicMBean / ModelMBean | Keep metadata and invocation consistent |

There is no rule requiring the entire system to use a single style. **The right granularity is per MBean/management contract**: pick one primary authoritative style and keep it consistent within the module.

## 17. Migration workflow when mixed metadata already exists

If legacy code has overlapping `*MBean` interfaces, annotations, exporter mappings, and auto-configurations, migrate in a controlled manner:

### Step 1: Capture actual runtime state

Read registered ObjectNames and `MBeanInfo` from the live runtime environment. Record which attributes and operations consumers actually use. Do not guess from source code.

### Step 2: Choose the target contract

Decide between a Standard/MXBean interface or annotations for each MBean. Define which operations are permitted to be published and canonical attribute names.

### Step 3: Pick the registration owner and naming owner

Assign one exporter or manual registration per ObjectName. List configurations that might cause duplicate exports.

### Step 4: Clean up code to match the contract

If choosing an interface, remove JMX annotations that only create noise or are unused. If choosing annotations, consolidate them into a management adapter; do not keep a `*MBean` interface ambiguously as a second public API.

### Step 5: Verify via integration tests

Run the application with AOP enabled like production; read `MBeanInfo` and validate critical fields. Also check the absence of internal operations.

### Step 6: Transition dashboards/clients

If ObjectNames or attribute names change, update JMX exporters, dashboards, alert rules, JConsole scripts, and operational runbooks. If backward compatibility must be preserved, plan it explicitly instead of relying on accidental registration order.

## 18. Signs a system has multiple competing metadata sources

Symptoms worth investigating:

- A service has `SomethingMBean`, `@ManagedResource`, `@ManagedOperation`, and two `MBeanExporter` beans.
- An MBean appears twice under slightly different ObjectNames.
- One environment shows an operation while another does not, despite identical Java code.
- Metadata descriptions change after adding an AOP annotation.
- JConsole shows only Standard MBean interface methods, not annotated methods.
- After enabling Spring Boot JMX or Actuator integration, registration conflicts appear.
- Multiple naming strategies run for the same bean.
- Exporter configuration uses an existing-MBean handling policy to mask conflicts instead of resolving ownership.

Each symptom requires observing **runtime state and export configuration**. Do not draw conclusions from bean names or annotation counts alone.

## 19. Common pitfalls

| Issue | Cause | Prevention |
|---|---|---|
| `InstanceAlreadyExistsException` | Two registrations with the same ObjectName | One export owner/registration path |
| Missing `@ManagedOperation` in JConsole | Exporter uses interface contract instead of annotations or proxy does not expose method | Check MBeanInfo and the right source |
| Internal operation appears unexpectedly | Export surface too broad | Minimal contract, test absence |
| MBean has unexpected description | Assembler reads a different metadata source | Single metadata source and test descriptions |
| ObjectName changes across deployments | Unstable naming strategy | Explicit naming factory/contract |
| AOP proxy causes differences | Metadata reader or method exposure affected by proxy | Adapter and integration test with real proxy mode |
| “ignoreExisting” makes behavior unpredictable | Whichever mechanism registers first decides metadata | Do not use a policy to mask duplicate exporters |
| Unintentionally mixing MXBean and Standard MBean | Two contracts differ in type mapping and naming | Choose one style per interoperability requirements |
| Interface refactoring breaks dashboard | Attributes/operations are a public management contract | Versioning/migration and JMX tests |
| Annotation exists on class but exporter is not active | No matching export path | Check context/assembler and MBeanServer |

## 20. Practice exercises

### Exercise 1 — Recognizing two contract sources

Given:

```java
public interface CacheMonitorMBean {
    int getEntryCount();
}

@ManagedResource(objectName =
    "com.example.shop.catalog:type=CacheMonitor,name=main")
public class CacheMonitor implements CacheMonitorMBean {
    @ManagedAttribute
    public int getEntryCount() { return 10; }

    @ManagedOperation
    public void flush() { /* ... */ }
}
```

Predict the metadata when exported by Standard MBean convention versus via an annotation assembler, then use MBeanInfo to compare in two separate tests. Do not register both under the same ObjectName simultaneously.

### Exercise 2 — Choosing an ObjectName owner

A bean has `@ManagedResource(objectName="...name=old")` while config also maps it to `"...name=new"`. Choose one mechanism as authoritative and fix the other so two competing naming methods no longer remain.

### Exercise 3 — Checking after refactoring

You rename `QueueMonitorMBean.getPendingCount()` to `getQueuedCount()`. Which clients or dashboards could be affected? Write an integration test ensuring the `PendingCount` attribute name still exists if backward compatibility is still required.

### Exercise 4 — Separating a management adapter

A service has `@Transactional`, `@Cacheable`, and `@ManagedOperation`. Create a dedicated `ServiceManagement` bean for JMX, exposing only `getHealthStatus()` and `resetMonitoringCounters()`, and call the service through a Spring-injected dependency.

### Exercise 5 — Testing operation absence

An implementation class has a public method `deleteCustomerData()`. Design a management contract that does not publish that method and verify `MBeanInfo.getOperations()` does not contain this dangerous method name. There is no need to implement real data deletion logic.

## 21. Self-check questions

**1. If a class has both a `*MBean` interface and `@ManagedOperation`, will both definitely be merged into MBeanInfo?**

No. The result depends on the export path/assembler and whether the method is exposed.

**2. Why should one ObjectName have one registration owner?**

To avoid duplicate registrations and metadata depending on exporter initialization order.

**3. What is the final source of truth for JMX clients at runtime?**

The registered MBean and its `MBeanInfo`; source code is the intended contract, while runtime metadata is what clients see.

**4. Does choosing annotation-driven export require removing all business Java interfaces?**

No. Business interfaces remain useful; just avoid treating them as a second management contract unless designed that way.

**5. Can Standard MBeans and MXBeans be used in the same application?**

Yes. The “single source” rule applies per MBean; different MBeans can use different mechanisms.

**6. Is “ignoreExisting” a standard way to avoid metadata conflicts?**

It should not be treated as an architectural solution. It can mask duplicate registrations and cause order-dependent behavior.

**7. Why test MBeanInfo after enabling AOP?**

Proxies can alter the runtime class and method exposure; actual metadata can differ from predictions based on source code.

## 22. Key takeaways

- Management metadata is an **operational contract**: attributes, operations, descriptions, notifications, and related information.
- Each MBean should have **one primary contract source**: Standard MBean interface, MXBean interface, Spring annotations, or DynamicMBean metadata.
- Each MBean also needs **one export owner** and one naming policy to avoid registration conflicts or differing ObjectNames.
- Interfaces and annotations can coexist in source, but are not merged by default; the export mechanism determines what clients see.
- AOP proxies make guessing from the implementation harder; use an adapter and verify runtime metadata.
- JMX clients inspect `MBeanInfo`, not source code. Contract tests should rely on actual metadata.
- Keep the management surface small, stable, and security-controlled; avoid publishing sensitive business operations.
- When changing a contract or ObjectName, treat it as a migration affecting dashboards, exporters, and operational tools.

## 23. References

- Java SE 21 — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — `StandardMBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Controlling MBean Registration Behavior: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — AOP Proxying: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
