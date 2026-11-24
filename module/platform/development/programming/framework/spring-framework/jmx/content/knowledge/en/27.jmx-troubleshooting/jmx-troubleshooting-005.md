# Attribute or Operation Not Appearing in MBeanInfo: Spring Framework JMX Diagnostics

## 1. Symptoms and Objectives

Spring Framework can export beans as MBeans through `MBeanExporter`, using a Standard MBean, MXBean, `DynamicMBean`, or `ModelMBean` built from metadata. Operators connect with JConsole, VisualVM, or a JMX client and read `MBeanInfo` to see what the MBean exposes.

A familiar error: **The MBean is registered and appears under the right ObjectName, yet the expected attribute or operation is missing from `MBeanInfo`**. For example, the Java class has `getQueueDepth()`, `pause()`, and even `@ManagedAttribute` and `@ManagedOperation`, yet the tool only shows a few other attributes or operations.

The goal of this procedure is to locate the exact layer causing missing metadata:

- Are you inspecting the **right MBeanServer and ObjectName**?
- Is the MBean using a **Standard MBean/MXBean** or a **Spring-built ModelMBean**?
- Is the method included in the **management interface** or selected by the **assembler**?
- Are `@ManagedAttribute`/`@ManagedOperation` actually being processed by the metadata source?
- Is the bean a **JDK/CGLIB AOP proxy** hiding the target class or restricting methods?
- Is a getter/setter mapped as an **attribute** rather than an operation?
- Are there differences in **method signature, data type, overloads, naming, and letter case**?

**Do not fix this by exporting all public methods immediately.** Doing so can expose business APIs, sensitive setters, or operations with side effects.

## 2. Distinguishing "MBean Not Visible" from "MBeanInfo Missing Members"

Identify the symptom first:

| Symptom | Layer to Investigate |
| --- | --- |
| `MBeanServer.isRegistered(name) == false` | Export, autodetection, ObjectName, server, startup |
| MBean exists, but `getMBeanInfo(name)` lacks the attribute | Management interface, assembler, metadata, getter/setter |
| MBean exists, but operation is missing | Assembler, annotations, signature, proxy interface |
| Metadata has the attribute, yet `getAttribute` fails | Runtime invocation, permissions, reflection, getter exception |
| Metadata has the operation, yet `invoke` fails | Signature mismatch, authorization, target method exception |
| JConsole does not see it, yet a local probe does | Tool connected to a different JVM/server, UI/cache, or connector |

A missing entry in `MBeanInfo` is a **metadata surface** issue; it does not automatically mean the Java method does not exist.

If the MBean is not yet registered, follow the startup/registration troubleshooting workflow first, then return to metadata.

## 3. MBeanInfo Is the Source of Truth for the JMX Contract

`javax.management.MBeanInfo` describes the members a JMX client can see:

- `MBeanAttributeInfo[]`: name, type, readability/writability, description.
- `MBeanOperationInfo[]`: operation name, return type, impact, and parameters.
- `MBeanNotificationInfo[]`: declared notification types.
- `MBeanConstructorInfo[]`: constructor metadata when present.
- `Descriptor`: additional information depending on MBean type.

A Java class having 15 public methods does not mean `MBeanInfo` must contain 15 operations. Standard MBeans restrict exposure to the management interface; a Spring metadata assembler may select only a few annotated methods.

`MBeanInfo.getClassName()` should also not be treated as direct proof of the target class in the Spring context, especially when the MBean is a ModelMBean or wrapper.

## 4. Verifying the Right MBeanServer and ObjectName

Probe the exact `MBeanServer` used by the exporter:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

System.out.println("Registered: " + server.isRegistered(expected));

for (ObjectName name : server.queryNames(
        new ObjectName("com.example.jobs:*"), null)) {
    System.out.println(name.getCanonicalName());
}
```

If the exporter is configured with `setServer(customServer)`, inject or retrieve that exact `customServer`. The platform server does not automatically contain MBeans from a custom server.

When using remote JMX, `MBeanServerConnection` on the client only represents the server the connector points to; if the connector differs from the exporter's server, the client may see platform MBeans while missing application MBeans.

`ObjectName` may have its key properties reordered in canonical representation. Inspect `getCanonicalName()`, domain, type, and name instead of doing semantically incorrect raw string comparisons.

## 5. Dumping Attributes and Operations Instead of Guessing from UI

After confirming registration:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(expected);

System.out.println("MBeanInfo class=" + info.getClassName());

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "ATTR name=%s type=%s readable=%s writable=%s is=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable(),
        attr.isIs()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "OP name=%s return=%s impact=%d%n",
        op.getName(),
        op.getReturnType(),
        op.getImpact()
    );

    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.printf("  PARAM %s : %s%n",
            p.getName(), p.getType());
    }
}
```

The output helps resolve three common misunderstandings:

1. Getter `getQueueDepth()` may be exported as **attribute `QueueDepth`**, not operation `getQueueDepth`.
2. Setter `setEnabled(boolean)` may be exported as **writable attribute `Enabled`**, not a separate operation.
3. Overloaded operations share the same name with multiple **parameter signatures**, so clients must compare signatures as well.

Server `MBeanInfo` is far better evidence than guessing from the IDE's list of public methods.

## 6. Standard MBean: Only Methods in the Standard Interface Are Exposed

Consider:

```java
package com.example.jobs.jmx;

public interface WorkerAdminMBean {
    int getQueueDepth();
    void pause();
}
```

```java
package com.example.jobs.jmx;

public final class WorkerAdmin implements WorkerAdminMBean {
    public int getQueueDepth() { return 7; }
    public void pause() { }

    public void resetDatabase() {
        // Public Java method, not part of the management interface.
    }
}
```

When `WorkerAdmin` is registered as a **Standard MBean**, `getQueueDepth` and `pause` belong to the JMX contract; `resetDatabase` does not automatically become a JMX operation.

This is **by design**, not an annotation bug. If a method truly needs to be exported, add it to the management interface after evaluating impact and access permissions, or build a dedicated management adapter.

Note that the Standard MBean convention requires the interface name to follow the class name plus `MBean` suffix pattern, or use an appropriate MBean interface binding mechanism. MXBean has its own conventions and mappings via `MXBean`/JMX annotations.

## 7. MXBean and Data Types

MXBeans apply data type mapping to provide greater classloader independence than arbitrary MBeans.

Example:

```java
public interface CacheStatisticsMXBean {
    long getHitCount();
    long getMissCount();
}
```

`CacheStatisticsMXBean` describes read-only attributes `HitCount` and `MissCount`. If a client looks for an operation `getHitCount`, concluding the operation is missing would be wrong because the method is exposed as an attribute.

When using DTOs/records or generic types, MXBean/OpenType mapping can affect the actual types advertised by `MBeanInfo`. A method using an unsupported type can cause compliance or mapping errors. Do not fix this by loosely changing the client-side signature without checking server metadata.

For complex custom DTOs, consider scalar types, `CompositeData`, `TabularData`, or types with clear JMX mappings.

## 8. Spring POJO Export and MBeanInfoAssembler

Spring can export a non-Standard-MBean POJO as a ModelMBean. The exposed surface is determined by `MBeanInfoAssembler`.

Common strategies:

| Assembler | Criterion Deciding Exposed Methods |
| --- | --- |
| `SimpleReflectiveMBeanInfoAssembler` | Reflection over eligible public methods/properties |
| `MetadataMBeanInfoAssembler` | Metadata from `JmxAttributeSource`, usually annotations |
| `InterfaceBasedMBeanInfoAssembler` | Methods belonging to specified interfaces |
| `MethodNameBasedMBeanInfoAssembler` | Allowlist of method names |
| `MethodExclusionMBeanInfoAssembler` | Excludes configured set of methods |

If the bean uses `MetadataMBeanInfoAssembler`, a public method lacking the proper management annotation **can be intentionally excluded**. If using `InterfaceBasedMBeanInfoAssembler`, an annotation on a method outside the interface will not make the assembler include that method automatically.

Diagnostic step: inspect the actual exporter configuration in the Spring context, not just the annotated class. Having `@ManagedResource` on a bean does not guarantee the exporter is configured to read annotation metadata.

## 9. Configuring Annotation-Based Spring JMX

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
class JmxMetadataConfiguration {

    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MBeanExporter mbeanExporter(
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

Here:

- `AnnotationJmxAttributeSource` reads information such as `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`.
- `MetadataMBeanInfoAssembler` determines attributes/operations from metadata.
- `MetadataNamingStrategy` resolves the MBean name from metadata.
- `MBeanExporter` registers the bean with the server.

If Spring Boot already auto-configures an exporter, inspect the final effective configuration before creating an additional custom exporter to avoid duplicate ObjectNames. The Java example above is no substitute for verifying actual dependencies, context, and Spring version.

## 10. Using the Right Annotation for Each Method Type

A management adapter:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary"
)
public class WorkerJmxAdapter {

    @ManagedAttribute(description = "Current queued jobs")
    public int getQueueDepth() {
        return 12;
    }

    @ManagedAttribute(description = "Paused state")
    public boolean isPaused() {
        return false;
    }

    @ManagedOperation(description = "Pause the worker")
    public void pause() {
        // Administrative command.
    }

    public void privateBusinessAction() {
        // Public Java method, but not annotated for JMX.
    }
}
```

Common mistakes:

- Using `@ManagedOperation` on a getter that JMX clients look for as an attribute.
- Placing `@ManagedAttribute` on a method without a proper getter/setter signature.
- Placing annotations on the implementation while the exporter reads a different contract.
- Omitting `@ManagedOperation` assuming `@ManagedResource` exports every public method.
- Placing annotations on overloaded methods where mapping/invocation behaves unexpectedly.
- Using types or access flags incompatible with expectations.

**Annotations do not automatically enable an exporter or open remote JMX.** They only supply metadata to a configuration path that knows how to read those annotations.

## 11. Getters, Setters, and JavaBeans Conventions

JMX attributes typically originate from property-style methods.

```java
public int getQueueDepth();
public boolean isPaused();
public void setPaused(boolean paused);
```

Common mappings:

| Java method | JMX attribute | Type / access |
| --- | --- | --- |
| `getQueueDepth()` | `QueueDepth` | Readable int |
| `isPaused()` | `Paused` | Readable boolean |
| `setPaused(boolean)` | `Paused` | Writable boolean |
| `getState()` | `State` | Readable return type |

For a setter, a matching getter for the same property or specific assembler rules may be required to define a writable attribute. A method `getQueueDepth(String queue)` is not a zero-arg JavaBeans getter; it is better suited as an operation accepting a parameter if it needs to be exposed.

Watch out for letter case: `queueDepth`, `QueueDepth`, and `getQueueDepth` are distinct representations. JMX clients should read the actual list of attribute names instead of guessing.

## 12. JDK Proxies and CGLIB Proxies Hiding Metadata/Methods

Spring AOP can wrap a bean with a JDK dynamic proxy or a CGLIB subclass proxy.

- **JDK proxy** exposes only methods of the interfaces implemented by the proxy.
- **CGLIB proxy** has a subclass relationship with the target, but cannot intercept `final` methods via overriding.
- Annotations on the target class are not automatically copied onto the JDK proxy class.
- Metadata sources/assemblers can recognize the target class via Spring mechanisms, so not every proxy drops annotations.

Observation:

```java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("workerService");

System.out.println("runtime=" + bean.getClass());
System.out.println("isProxy=" + AopUtils.isAopProxy(bean));
System.out.println("jdk=" + AopUtils.isJdkDynamicProxy(bean));
System.out.println("cglib=" + AopUtils.isCglibProxy(bean));
System.out.println("target=" + AopUtils.getTargetClass(bean));
```

`context` is the Spring `ApplicationContext` supplied at the call site. If the target has `pause()` while the interface implemented by the JDK proxy only has `submitJob()`, the exporter may fail to expose or invoke `pause()` through the proxy object as expected.

A durable fix is usually to place management methods on an interface supported by the proxy, or create a **dedicated JMX adapter** injecting a management port. Do not blindly enable CGLIB across the entire application.

## 13. Two Similar-Looking Errors with Different Root Causes

### 13.1. Missing metadata

`MBeanInfo.getOperations()` does not contain `pause`. Check:

1. Does the MBean interface declare `pause()`?
2. Which assembler is in use?
3. Is `@ManagedOperation` on the right method and read by the metadata source?
4. Is the runtime proxy capable of exposing the method?
5. Are you querying the right ObjectName/server?

### 13.2. Metadata present, but invocation fails

`MBeanInfo` has `pause`, yet:

```java
server.invoke(
    expected,
    "pause",
    new Object[0],
    new String[0]
);
```

throws an error. This can be a different issue: Spring AOP advice, security context, transactions, target method logic, data validation, or JMX signature.

Do not swap the assembler just because the runtime method throws an exception. First inspect the nested cause and cross-check the signature in MBeanInfo.

## 14. Checking Overloaded Methods and Operation Signatures

Example:

```java
public void retry();
public void retry(String jobId);
public void retry(String jobId, int attempts);
```

If the exporter publishes only one overload, `MBeanInfo` may contain a `retry` operation with a specific parameter type list. To invoke accurately:

```java
server.invoke(
    expected,
    "retry",
    new Object[] { "job-7", 3 },
    new String[] { "java.lang.String", "int" }
);
```

Use `int` in the signature rather than `java.lang.Integer` if the server operation actually declares a primitive. A slight mismatch in parameter type can prevent JMX from finding the right operation.

When an operation does not appear in the UI, dump all `MBeanOperationInfo` entries along with `MBeanParameterInfo.getType()`; do not compare operation names alone.

## 15. Inspecting Annotations on Target Class and Methods

If you suspect a proxy is obscuring annotations, compare the runtime class and target class:

```java
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.jmx.export.annotation.ManagedResource;

Object bean = context.getBean("workerService");
Class<?> runtime = bean.getClass();
Class<?> target = AopUtils.getTargetClass(bean);

System.out.println("runtime=" + runtime.getName());
System.out.println("target=" + target.getName());

System.out.println("runtime managed=" +
    AnnotatedElementUtils.hasAnnotation(
        runtime, ManagedResource.class));

System.out.println("target managed=" +
    AnnotatedElementUtils.hasAnnotation(
        target, ManagedResource.class));
```

If runtime lacks the annotation while target has it, this data is only evidence about the **reflection path**; it does not yet prove the exporter failed to read metadata. Continue checking `MBeanInfo` and the exporter configuration.

If multiple interceptors are involved, you can inspect the advisor list via `Advised` when supported by the proxy, without needing to unwrap the entire proxy chain or invoke target methods just to look up annotations.

## 16. An Integration Test Protecting the JMX Surface

A test should use a real Spring context with the exporter and the same AOP advice enabled in production.

Example assertion logic:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import javax.management.MBeanServer;
import javax.management.ObjectName;

void assertJmxContract(MBeanServer server) throws Exception {
    ObjectName name = new ObjectName(
        "com.example.jobs:type=Worker,name=Primary"
    );

    assertTrue(server.isRegistered(name));

    var info = server.getMBeanInfo(name);

    Set<String> attributeNames =
        Arrays.stream(info.getAttributes())
            .map(a -> a.getName())
            .collect(Collectors.toSet());

    Set<String> operationNames =
        Arrays.stream(info.getOperations())
            .map(op -> op.getName())
            .collect(Collectors.toSet());

    assertTrue(attributeNames.contains("QueueDepth"));
    assertTrue(attributeNames.contains("Paused"));
    assertTrue(operationNames.contains("pause"));
    assertFalse(operationNames.contains("privateBusinessAction"));
}
```

In real JUnit tests, verify types, readable/writable flags, and signatures to protect the full contract. Tests must clean up the Spring context/MBeanServer to avoid ObjectName collisions across suite runs or reloads.

Do not test by calling `new WorkerJmxAdapter()` and guessing JMX metadata: you must **register the MBean** to inspect the final `MBeanInfo`.

## 17. A Dedicated Management Adapter Reduces Risk

A sustainable design:

```java
public interface WorkerManagementPort {
    int queueDepth();
    boolean paused();
    void pause();
}
```

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary"
)
public final class WorkerManagementAdapter {

    private final WorkerManagementPort management;

    public WorkerManagementAdapter(WorkerManagementPort management) {
        this.management = management;
    }

    @ManagedAttribute
    public int getQueueDepth() {
        return management.queueDepth();
    }

    @ManagedAttribute
    public boolean isPaused() {
        return management.paused();
    }

    @ManagedOperation
    public void pause() {
        management.pause();
    }
}
```

The adapter places the JMX contract in one spot, avoids forcing the business POJO to export numerous public methods, and avoids tight coupling to the service's proxy structure.

If the adapter is also AOP-proxied, you still need to check its runtime class/target and MBeanInfo; separating an adapter does not automatically guarantee compatibility with every proxy configuration.

## 18. Step-by-Step Diagnostic Workflow

```text
MBean lacks expected attribute/operation
                  |
                  v
       Right server and ObjectName?
             /           \\
           No           Yes
            |             |
     Fix wiring/name       v
                        isRegistered?
                         /    \\
                       No      Yes
                       |        |
                  Export issue  v
                            Dump MBeanInfo
                              |
               +--------------+--------------+
               |                             |
         Standard/MXBean               Spring ModelMBean
               |                             |
       Check interface               Check assembler
               |                    and metadata source
               +--------------+--------------+
                              |
                         Check proxy
                              |
                  Compare signature/type
                              |
                  Test attribute/invoke separately
```

Practical checklist:

1. Identify the exporter's exact `MBeanServer`.
2. Print the registered canonical `ObjectName`.
3. Read `MBeanInfo`, recording attribute/operation types and signatures.
4. Determine whether the MBean is Standard, MXBean, Dynamic, or Spring ModelMBean.
5. If Standard/MXBean, inspect the management interface.
6. If ModelMBean, inspect `MBeanInfoAssembler` and `JmxAttributeSource`.
7. Check whether annotations are on the right methods and types.
8. Check the AOP runtime proxy and target class.
9. Run an integration test with a real Spring context.
10. Only once metadata is correct should you test getAttribute/invoke and nested exceptions.

## 19. Causes and Quick Resolution Table

| Cause | Indicator | Right Direction to Fix |
| --- | --- | --- |
| Wrong ObjectName | `isRegistered=false` or similar name exists | Query canonical names, fix name |
| Wrong MBeanServer | Only JVM MBeans visible | Point exporter/connector to same server |
| Standard MBean interface lacks method | Public method missing in MBeanInfo | Update management interface |
| Metadata assembler not reading annotations | Annotations exist, but entries are missing | Configure metadata assembler/source |
| Reflective assembler exposes differently than expected | Too many/few methods | Choose allowlist or interface-based |
| JDK proxy hides management method | Target has method, proxy interface lacks it | Adapter or appropriate interface |
| Wrong getter signature | `getX` takes parameters or unsuitable return | Use operation or fix getter |
| Overload/type mismatch | Operation name exists, but signature differs | Read MBeanOperationInfo |
| Remote client connected to wrong JVM | UI differs from local probe | Check connector URL/server |
| Metadata correct, but invocation fails | `getAttribute`/`invoke` throws exception | Check AOP/security/runtime code |

## 20. Key Takeaways

**If an attribute or operation does not appear in `MBeanInfo`, start from the metadata of the registered MBean, not from the public methods of the Java class.** First verify the server/ObjectName and dump all attributes/operations. Then branch according to Standard MBean/MXBean interface or Spring ModelMBean assembler; cross-check annotations, method signatures, and AOP proxies. Do not confuse missing metadata with invocation errors, and do not use export-all to mask the problem, as that can expose unintended management APIs.
