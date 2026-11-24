# Reading MBeanInfo after a bean passes through multiple interceptors in Spring JMX and AOP

## 1. Why inspect MBeanInfo at the end of the proxy chain?

In the Spring Framework, a business bean can pass through multiple AOP layers before being exposed outside the `ApplicationContext`: transactions, caching, security, metrics, tracing, and custom advice. A single original bean can have multiple interceptors, or even multiple nested proxy layers.

When a bean is exported as an MBean by Spring JMX `MBeanExporter`, developers often look only at the original class or source-code annotations to guess which attributes/operations will appear. This easily leads to confusion because JMX clients **do not view the source class directly**. Clients see the metadata registered in `MBeanServer`, via `MBeanInfo`.

Real-world examples:

- The target class has `@ManagedAttribute`, yet JConsole does not show the attribute.
- The business interface lacks management methods; a JDK proxy exposes only the interface.
- Spring may read annotations on the target class, yet the method cannot be invoked through the proxy as expected.
- The MBean is registered as a Standard MBean/MXBean instead of a ModelMBean built by Spring's assembler.
- An operation appears in `MBeanInfo`, yet invocation fails at the AOP layer or in business code.
- Two instances are registered with the same interface type, yet metadata differs due to different exporters/configs.

This lesson guides you through inspecting **the actual JMX contract after a bean passes through interceptors**, while avoiding over-inferring from `bean.getClass()`.

## 2. Two metadata layers to distinguish

### 2.1. Class and proxy metadata in Spring

Spring manages Java beans. You can observe:

- `bean.getClass()`: the runtime class of the object retrieved from the container.
- `AopUtils.isAopProxy(bean)`: whether the bean is a Spring AOP proxy.
- `AopUtils.isJdkDynamicProxy(bean)` or `isCglibProxy(bean)`.
- `AopUtils.getTargetClass(bean)`: the target class represented by the proxy, when Spring has sufficient information.
- Annotations on the implementation or interfaces, such as `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`.
- Advisors/interceptors attached to the proxy (if the object supports `Advised`).

This is diagnostic data for **the path from the bean to the exporter**.

### 2.2. MBeanInfo metadata in JMX

`javax.management.MBeanInfo` describes the contract of a registered MBean:

- `getClassName()`: the class name reported by MBean metadata, not necessarily the Spring target class.
- `getAttributes()`: names, data types, read/write capabilities, and descriptions.
- `getOperations()`: operation names, parameter signatures, return types, and impact.
- `getConstructors()`: JMX constructor metadata.
- `getNotifications()`: notifications published by the MBean.
- `getDescriptor()`: additional metadata, if present.

This is **the management surface seen by JMX clients**. Having a public Java method does not automatically put it into `MBeanInfo`.

Both layers must be checked when AOP is involved: target metadata explains the design intent; `MBeanInfo` confirms the registered contract.

## 3. Diagram of a multi-interceptor path

```text
Business implementation
  @ManagedResource / @ManagedAttribute / @ManagedOperation
          |
          v
  Transaction advice
          |
          v
  Method security advice
          |
          v
  Cache / logging / metrics advice
          |
          v
  JDK proxy or CGLIB proxy
          |
          v
  MBeanExporter
     +-- ObjectNamingStrategy
     +-- MBeanInfoAssembler (if exporting a POJO)
          |
          v
  MBeanServer.registerMBean(ObjectName)
          |
          v
  MBeanServer.getMBeanInfo(ObjectName)
          |
          v
  JConsole / VisualVM / JMX client
```

The diagram only illustrates the conceptual flow; a typical Spring AOP proxy may hold **a chain of interceptors** rather than creating a new Java proxy per advice. When nested proxies occur due to configuration or additional libraries, discovering the target class becomes more complex.

Crucially, **advisors/interceptors are not the same as MBean attributes/operations**. Advice changes behavior upon invocation; exporting management methods is determined by the JMX contract or `MBeanInfoAssembler`.

## 4. Example of a target bean subject to multiple advices

A service with both caching and transactions:

```java
package com.example.jobs;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary",
    description = "Worker management"
)
public class WorkerService implements WorkerOperations {

    private volatile boolean paused;

    @Override
    @Transactional
    public void submit(String jobId) {
        // Business processing.
    }

    @ManagedAttribute(description = "Worker paused")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Pause worker")
    public void pause() {
        paused = true;
    }

    @Cacheable("worker-summary")
    public String getSummary() {
        return "worker-state";
    }
}
```

Business interface:

```java
public interface WorkerOperations {
    void submit(String jobId);
}
```

If Spring chooses a JDK dynamic proxy because of AOP, the proxy typically implements `WorkerOperations`, yet does not necessarily have `pause()`, `isPaused()`, or `getSummary()` on the proxy's Java interface. Spring metadata may look up annotations on the target class depending on configuration, yet invoking an implementation-only method through a JDK proxy can run into problems.

If Spring uses a CGLIB class proxy, methods may be visible via the subclass, yet remain subject to constraints on `final` methods, `private` methods, self-invocation, and advice interactions.

Do not use this example to conclude that all Spring JMX exports with JDK proxies fail. You must measure **empirically** via `MBeanInfo` and test invocations.

## 5. Inspecting the runtime bean and target class

Inside a Spring component receiving `ApplicationContext`:

```java
import org.springframework.aop.support.AopUtils;
import org.springframework.context.ApplicationContext;

public final class AopBeanProbe {

    public static void describe(
            ApplicationContext context,
            String beanName) {

        Object bean = context.getBean(beanName);

        System.out.println("beanName=" + beanName);
        System.out.println("runtime=" + bean.getClass().getName());
        System.out.println("isAopProxy=" + AopUtils.isAopProxy(bean));
        System.out.println("isJdkProxy=" + AopUtils.isJdkDynamicProxy(bean));
        System.out.println("isCglibProxy=" + AopUtils.isCglibProxy(bean));
        System.out.println("targetClass=" +
            AopUtils.getTargetClass(bean).getName());
    }
}
```

Example output:

```text
beanName=workerService
runtime=jdk.proxy2.$Proxy...
isAopProxy=true
isJdkProxy=true
isCglibProxy=false
targetClass=com.example.jobs.WorkerService
```

That proves the Spring context returned a proxy; it does **not** prove that `MBeanExporter` registered the bean properly or that JMX clients see all operations.

Each check must answer a specific question: the type of object Spring hands to the exporter differs from the final JMX contract.

## 6. Inspecting the advisor/interceptor chain on a Spring AOP proxy

Multiple interceptors can live in the same Spring AOP proxy. For a proxy implementing `org.springframework.aop.framework.Advised`, you can print the advisor list:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.framework.Advised;

Object bean = context.getBean("workerService");

if (bean instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
```

This list may contain a transaction interceptor, cache interceptor, method-security interceptor, or custom advice. Advisor order can affect behavior, though it does not always equal the exact execution order of every path if advisors have pointcuts, dynamic matching, or other logic.

Do not call `getTargetSource().getTarget()` arbitrarily just to inspect when the target source has a special lifecycle, pooling, or lazy creation; doing so can initialize or borrow an object. Use `AopUtils.getTargetClass` and safe metadata first.

If the proxy does not implement `Advised`, do not infer that there are no interceptors: other proxies or frozen/custom proxies may not expose this API.

## 7. Reading MBeanInfo with MBeanServer

This is the direct check of the JMX contract:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("ObjectName=" + name.getCanonicalName());
System.out.println("MBeanInfo class=" + info.getClassName());
System.out.println("Description=" + info.getDescription());
```

**You must use the exact server where the exporter registered the MBean.** If the exporter uses a custom `MBeanServer`, the platform server may not contain the bean. An `isRegistered=false` result on the wrong server does not allow concluding that AOP lost the annotations.

For remote clients, `MBeanServerConnection.getMBeanInfo(ObjectName)` provides equivalent information over the JMX connector.

## 8. Printing all attributes of MBeanInfo

```java
import javax.management.MBeanAttributeInfo;

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s; type=%s; readable=%s; writable=%s; is=%s%n",
        a.getName(),
        a.getType(),
        a.isReadable(),
        a.isWritable(),
        a.isIs()
    );
}
```

If `@ManagedAttribute` on the target sits on a getter named `isPaused()`, the usual expectation is attribute `Paused` (boolean type). However, naming and exposure can be affected by the assembler and other metadata.

Do not check only whether `Paused` exists; verify:
- Exact attribute name and case sensitivity.
- Type string reported by JMX.
- `isReadable()` and `isWritable()`.
- `isIs()` for boolean getters of the `is...` form.
- Description when needed for operational documentation.

Having a Java method on the proxy is also insufficient to become a JMX attribute if the exporter does not select that method.

## 9. Printing operations and parameter signatures

```java
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "Operation=%s; return=%s; impact=%d%n",
        op.getName(),
        op.getReturnType(),
        op.getImpact()
    );

    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.printf(
            "  parameter=%s type=%s%n",
            p.getName(),
            p.getType()
        );
    }
}
```

A JMX operation is identified by its name and list of parameter types. When overloaded, two operations with the same name can still have two distinct signatures.

Example client invoke:

```java
server.invoke(
    name,
    "pause",
    new Object[0],
    new String[0]
);
```

If `MBeanInfo` publishes `pause(java.lang.String)` yet the client calls with no arguments, the invocation will not match. If `pause()` is in metadata yet the call throws an exception, inspect the nested cause at the AOP/security/transaction layer rather than concluding metadata is wrong.

## 10. Inspecting notifications and descriptors

The JMX surface does not consist solely of attributes and operations. An MBean can publish notifications:

```java
for (var notification : info.getNotifications()) {
    System.out.println(notification.getName());

    for (String type : notification.getNotifTypes()) {
        System.out.println("  " + type);
    }
}
```

With a ModelMBean built by Spring, `Descriptor` may contain useful information about metadata, fields, and how it is exposed:

```java
System.out.println(info.getDescriptor());
```

Do not assume every descriptor has the same fields or always includes the target class. Descriptor contents depend on the MBean kind (Standard, Dynamic, ModelMBean, MXBean) and the framework/assembler.

If `MBeanInfo` contains only a subset of attributes/operations, distinguish **missing metadata** from **methods intentionally not exposed**. A small management interface is usually better than automatically exporting every public method.

## 11. Why can multiple interceptors make MBeanInfo differ from expectations?

Several independent mechanisms exist:

### 11.1. JDK proxies restrict callable methods

If the target has `pause()` yet the JDK proxy implements only an interface with `submit(String)`, the `pause()` method does not appear as a Java method on the proxy. The exporter may retrieve target metadata yet run into trouble binding calls to the runtime proxy.

### 11.2. Spring metadata source selects a different class/annotation

`AnnotationJmxAttributeSource` or the assembler can look up annotations on the target, interfaces, or methods via resolvers. Under different configurations, method selection results also differ. Not every `bean.getClass().isAnnotationPresent(...)` check reflects Spring's actual metadata-reading capability.

### 11.3. The exporter uses a different interface/assembler

When using `InterfaceBasedMBeanInfoAssembler`, `MethodNameBasedMBeanInfoAssembler`, or a Standard MBean contract, the final surface may not rely on annotations on the target. AOP may merely be a coincidence when an export configuration change is what actually causes the difference.

### 11.4. The proxy adds supporting interfaces or methods

A proxy may implement `Advised` and internal framework interfaces. That does not mean they are permitted to leak via JMX. An overly broad reflective assembler can enlarge the published surface unintentionally; use an appropriate allowlist/metadata assembler.

### 11.5. Initialization and context lifecycle differ

The MBean may not yet be registered when the probe runs, or may have been unregistered when the context closed. A startup error may also happen during the export step before any JMX client gets a chance to read `MBeanInfo`.

For these reasons, **reading `MBeanInfo` for the registered name on the actual server** is more valuable than guessing from the proxy type.

## 12. Checking target annotations alongside JMX metadata

A probe lets you compare both perspectives:

```java
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.jmx.export.annotation.ManagedResource;

Object bean = context.getBean("workerService");

Class<?> runtime = bean.getClass();
Class<?> target = AopUtils.getTargetClass(bean);

System.out.println("runtime=" + runtime.getName());
System.out.println("target=" + target.getName());

System.out.println(
    "runtime @ManagedResource=" +
    AnnotatedElementUtils.hasAnnotation(
        runtime, ManagedResource.class
    )
);
System.out.println(
    "target @ManagedResource=" +
    AnnotatedElementUtils.hasAnnotation(
        target, ManagedResource.class
    )
);
```

If the runtime class lacks the annotation while the target has it, that suggests proxy impact on reflection. **Do not automatically conclude the exporter ignored the bean**: Spring JMX can read annotations via target metadata.

Continue by checking `MBeanServer.isRegistered` and `MBeanInfo`; if the MBean fails to register, inspect startup logs to distinguish autodetection skipping the bean from a `registerMBean` error.

## 13. Testing invocation to distinguish metadata from behavior

`MBeanInfo` is the visible contract, yet inspection alone does not prove operations can execute. Test reading attributes and invoking methods:

```java
Object paused = server.getAttribute(name, "Paused");
System.out.println("Paused=" + paused);

server.invoke(
    name, "pause", new Object[0], new String[0]
);

Object after = server.getAttribute(name, "Paused");
System.out.println("Paused after=" + after);
```

Invoking `pause` has side effects; perform this only in tests or authorized environments. In production, prefer read-only probes such as `getMBeanInfo`, `queryNames`, and safe attributes.

If an operation is present in `MBeanInfo` yet throws `SecurityException`, `MBeanException`, `ReflectionException`, or a similar wrapper, examine the deepest cause. Method security may lack an authentication context like an HTTP request because JMX calls may run on a different thread.

Similarly, transaction or caching advice can participate when invoking a method from JMX if the registered object is actually a Spring proxy. Do not treat `@Transactional` on the target as certain proof that calls from `MBeanServer` pass through transaction advice.

## 14. A management adapter keeps the contract stable

When a service has multiple interceptors and the JMX surface needs stability, design a dedicated adapter:

```java
public interface WorkerManagementPort {
    boolean isPaused();
    int getQueueDepth();
    void pause();
}
```

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Management,name=Primary"
)
public final class WorkerJmxAdapter {

    private final WorkerManagementPort management;

    public WorkerJmxAdapter(WorkerManagementPort management) {
        this.management = management;
    }

    @ManagedAttribute
    public boolean isPaused() {
        return management.isPaused();
    }

    @ManagedAttribute
    public int getQueueDepth() {
        return management.getQueueDepth();
    }

    @ManagedOperation
    public void pause() {
        management.pause();
    }
}
```

The service implementing `WorkerManagementPort` can be a Spring AOP proxy. The adapter calls through the interface exposed by the proxy, so business advice can continue operating when configured. JMX metadata stays centralized on the adapter, decoupled from the service's proxy details.

If an AOP pointcut also matches the adapter, the adapter itself can be proxied; integration tests must retrieve the actual bean and verify the export outcome.

## 15. Configuring an appropriate metadata assembler

When using Spring JMX annotations, you need a configuration that recognizes the corresponding metadata. Java configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
class JmxConfig {

    @Bean
    AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MBeanExporter exporter(AnnotationJmxAttributeSource source) {
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

In Spring Boot, if auto-configuration already provides an exporter, avoid creating two exporters with the same responsibility. In plain Spring Framework, `@EnableMBeanExport` can also be used. Pick one strategy, identify the actual server and `ObjectName`, and verify with a probe.

## 16. Integration testing MBeanInfo with active AOP

A test should enable the advices used in production, ensure the bean is proxied, and verify the final `MBeanInfo`:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.aop.support.AopUtils;

void assertManagementContract(
        Object businessBean,
        MBeanServer server
) throws Exception {

    assertTrue(AopUtils.isAopProxy(businessBean));

    ObjectName name = new ObjectName(
        "com.example.jobs:type=Management,name=Primary"
    );

    assertTrue(server.isRegistered(name));

    var info = server.getMBeanInfo(name);

    Set<String> attributes = Arrays.stream(info.getAttributes())
        .map(a -> a.getName())
        .collect(Collectors.toSet());

    assertTrue(attributes.contains("Paused"));
    assertTrue(attributes.contains("QueueDepth"));

    Set<String> operations = Arrays.stream(info.getOperations())
        .map(op -> op.getName())
        .collect(Collectors.toSet());

    assertTrue(operations.contains("pause"));
}
```

The test above requires a context, transaction/caching/security AOP, and a real `MBeanServer`. Merely doing `new WorkerService()` outside Spring is insufficient, because advisors/interceptors do not participate then.

For a strict contract, also verify:
- Attribute types and read/write permissions.
- Operation names and parameter signatures.
- Absence of internal operations outside the allowlist.
- Read-only getters execute without side effects.
- Notification metadata if notifications are used.
- Lifecycle unregistration when closing the context.

## 17. Comparing MBeanInfo before and after AOP changes

When adding a new interceptor, write a regression test:

1. Start the Spring context with the real AOP configuration.
2. Obtain the right `MBeanServer` and `ObjectName`.
3. Read `MBeanInfo` and store the normalized contract structure in test expectations.
4. Add/modify advice or proxy strategy.
5. Start the test context and read `MBeanInfo` again.
6. Compare attribute names/types, read-write flags, and operation signatures.
7. Run invocation tests for allowed methods.
8. Clean up the context so old registrations are not retained.

Do not compare every text field of `MBeanInfo.toString()`, because descriptors, descriptions, or display ordering may vary across versions/frameworks without changing the contract you need to protect. Compare the fields clients actually depend on.

If running two contexts in parallel in the same JVM, choose a distinct `ObjectName` namespace per test. Do not let `InstanceAlreadyExistsException` obscure your AOP test goal.

## 18. Symptom-based diagnostics

| Symptom | Possible Cause | Verification Step |
| --- | --- | --- |
| Bean has annotations yet MBean is missing | Autodetect, naming, or proxy metadata | Spring bean class, exporter config, `isRegistered` |
| MBean exists yet getter is missing | Assembler did not select it or proxy interface lacks method | `getAttributes`, target/interface |
| Operation name exists yet overload is missing | Signature not exported | `getOperations`, parameter list |
| Metadata is right yet invoke fails | Method security, transaction, reflection, or business code | Nested exception and AOP call path |
| Adding advice changes runtime class | JDK/CGLIB proxy strategy changed | `AopUtils` and advisors |
| `getClassName` does not match target | ModelMBean/wrapper/adapter was registered | `MBeanInfo`, exporter wiring |
| `MBeanInfo` wrong in test yet right in prod | Different exporter, profile, AOP, or `MBeanServer` | Compare effective config |
| MBean disappears after restart | Context unregistered or `ObjectName` changed | Lifecycle and `queryNames` |
| Client sees JVM MBeans yet not app MBeans | Connector points to a different server than exporter | Inject and compare `MBeanServer` instances |

When an error occurs, do not rush to enable class-based proxies system-wide. First confirm the exact `ObjectName`, JMX contract, assembler, and differences between the runtime proxy and target class.

## 19. 10-minute inspection workflow

```text
Get bean from Spring context
  |
  +-- Print bean.getClass()
  +-- AopUtils.isAopProxy / getTargetClass
  +-- If Advised: print advisors
  |
  v
Confirm MBeanExporter and MBeanServer
  |
  v
server.isRegistered(ObjectName)?
  |
  +-- NO -> check autodetection, naming, registration logs
  |
  +-- YES -> server.getMBeanInfo(ObjectName)
                |
                +-- Print attributes (name/type/read/write)
                +-- Print operations (name/signature/return)
                +-- Print notifications and descriptor when needed
                |
                v
          Metadata correct?
           /       \\
         NO         YES
         |           |
  assembler/       test getAttribute/invoke
  interface/        and nested exceptions
  proxy metadata
```

Useful diagnostic data to record includes canonical `ObjectName`, runtime proxy class, target class, advisors, exporter config, `MBeanInfo`, and invocation errors. Avoid logging sensitive attribute values or parameters in production.

## 20. Remember

**When a bean has passed through multiple Spring AOP interceptors, the most reliable source for the final JMX surface is `MBeanServer.getMBeanInfo(ObjectName)`.** The runtime class and target annotations help explain why metadata was selected or skipped, while `MBeanInfo` shows which attributes, operations, signatures, and notifications clients actually see. Visible metadata and invocability remain two separate checks. In architectures with complex AOP, a small JMX adapter that keeps the contract stable and integration tests against a real context typically avoid depending on proxy internals.
