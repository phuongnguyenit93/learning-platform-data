# Practice: Reproducing an AOP Proxy Issue and Fixing It with Target-Class Proxying in Spring Framework JMX

## 1. Lab Objectives

In Spring Framework, a managed bean can be wrapped by Spring AOP to apply `@Transactional`, `@Cacheable`, tracing, or custom advice. Once AOP is enabled, the object returned by the Spring container is no longer the raw original implementation. If Spring uses a **JDK dynamic proxy**, the proxy primarily exposes the configured interfaces. This can affect a JMX exporter or metadata assembler that needs to access methods existing only on the implementation class.

This lab helps you:

1. Create a management bean with a business interface and a management operation not declared on that interface.
2. Enable Spring AOP to observe a JDK dynamic proxy.
3. Reproduce a **controlled failure** when a JMX inspection/export configuration depends on the implementation API rather than the proxy API.
4. Switch to a **target-class proxy** (class-based proxy, typically CGLIB in Spring AOP).
5. Re-verify the Spring bean type, `MBeanInfo`, `ObjectName`, and invocations via `MBeanServer`.
6. Distinguish proxy-related issues from exporter, assembler, naming, or server errors.
7. Evaluate the limitations of class-based proxies and when a management facade is a better solution.

> **Scope:** This is a single-JVM Spring Framework lab using local JMX, with no remote connector required. Do not expose JMX/RMI to the network in this lab.

## 2. Expected Outcomes

We want to observe two scenarios:

| Scenario | Proxy Type | What to Observe |
|---|---|---|
| A — JDK dynamic proxy | Proxy implements business interface | Methods present only on the implementation do not appear directly on the interface proxy |
| B — Target-class proxy | Proxy is a subclass of the implementation | Public non-final methods on the implementation are accessible through the class-based proxy |
| C — JMX contract | Exporter uses appropriate metadata | `MBeanInfo` contains the requested attributes/operations |
| D — Regression test | Tests run under both configurations | Detects unintended changes to the JMX API |

**Note on reproducibility:** Not every Spring JMX version/configuration loses MBeans when JDK proxies are enabled. Some exporters and assemblers know how to resolve the target class or underlying metadata. Thus, this lab deliberately constructs a case requiring concrete-type visibility; the failure should not be generalized into a rule that "JDK proxies always break JMX".

## 3. Background: Two Spring AOP Proxy Mechanisms

### 3.1. JDK dynamic proxy

When a bean has an interface and Spring AOP is configured to use interface-based proxies:

```text
OrderWorkerImpl implements OrderWorker
              |
              v
       JDK dynamic proxy
              |
              +-- implements OrderWorker
              |
              +-- does not extend OrderWorkerImpl
```

Example:

```java
public interface OrderWorker {
    void execute();
}
```

```java
public class OrderWorkerImpl implements OrderWorker {

    @Override
    public void execute() {
        // Business work.
    }

    public int getProcessedJobs() {
        return 10;
    }

    public void resetProcessedJobs() {
        // Management operation.
    }
}
```

A JDK proxy implementing `OrderWorker` is not an instance of `OrderWorkerImpl`. Even though the target still has `getProcessedJobs()`, a client viewing the proxy only through the `OrderWorker` interface cannot invoke that method. If a custom export/inspection component reflects only on the proxy class without resolving the target, JMX metadata may omit the method.

### 3.2. Target-class proxy

When `proxyTargetClass=true`, Spring AOP uses a class-based proxy when applicable:

```text
OrderWorkerImpl
      ^
      |
Class-based proxy extends OrderWorkerImpl
      |
      +-- execute()
      +-- getProcessedJobs()
      +-- resetProcessedJobs()
```

The proxy is a subclass of the implementation, so most public methods of the target class remain present in the proxy's type hierarchy. This mechanism does not eliminate constraints:

- A `final class` cannot be subclassed to create this kind of proxy.
- A `final method` cannot be overridden/advised.
- A `private method` cannot be advised via subclass overriding.
- `self-invocation` typically bypasses Spring proxy-based advice.
- Class-based proxies can affect behavior in places expecting interface proxies.
- Method visibility, module system rules, and constructor constraints still need checking per Spring/JDK version.

**Do not treat target-class proxying as a default security or transaction fix:** it only changes how proxies are generated, not whether a JMX exporter exposes all methods properly.

## 4. Environment Setup

Requirements:

- JDK 17 or later.
- Spring Framework 6.x or a compatible version.
- Spring Context, Spring AOP, and AOP dependencies such as AspectJ Weaver when using `@Aspect`.
- JUnit 5 for integration tests.
- An IDE or terminal running Maven/Gradle.
- Spring Boot is not required; if using Boot, control auto-configured exporters and AOP settings so results are not mixed.

Package layout:

```text
src/main/java/example/jmx/lab/
    OrderWorker.java
    OrderWorkerImpl.java
    TraceAspect.java
    LabConfiguration.java
    JmxInspector.java

src/test/java/example/jmx/lab/
    AopJmxProxyTest.java
```

Example Maven dependencies in `pom.xml` (choose a compatible Spring version consistently across all modules):

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-aop</artifactId>
  </dependency>
  <dependency>
    <groupId>org.aspectj</groupId>
    <artifactId>aspectjweaver</artifactId>
  </dependency>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

These dependencies are illustrative; your project must declare versions via a BOM or dependency management and configure Surefire/JUnit accordingly. Do not copy as-is and expect Maven to infer versions without dependency management.

## 5. Step 1 — Create the Business Interface

File `OrderWorker.java`:

```java
package example.jmx.lab;

public interface OrderWorker {
    void execute(String orderId);
}
```

The interface has only one business operation. This is intentional to create a difference between **the API exposed by the JDK proxy** and the management methods residing on the implementation.

Do not add `getProcessedJobs()` or `resetProcessedJobs()` to the interface yet, because doing so would hide the root cause demonstrated by this lab.

## 6. Step 2 — Create the Implementation with Management Methods

File `OrderWorkerImpl.java`:

```java
package example.jmx.lab;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "training.aop:type=OrderWorker,name=Primary",
    description = "Order worker management view")
public class OrderWorkerImpl implements OrderWorker {

    private final AtomicInteger processed = new AtomicInteger();

    @Override
    public void execute(String orderId) {
        processed.incrementAndGet();
    }

    @ManagedAttribute(
        description = "Number of processed orders")
    public int getProcessedJobs() {
        return processed.get();
    }

    @ManagedOperation(
        description = "Reset the demonstration counter")
    public void resetProcessedJobs() {
        processed.set(0);
    }
}
```

In this example:

- `execute(String)` is on the business interface.
- `getProcessedJobs()` and `resetProcessedJobs()` exist only on the implementation.
- `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation` provide Spring JMX metadata.
- `AtomicInteger` makes the counter safer in multi-threaded tests.
- The reset operation only alters a demo counter; it causes no real data loss.

If the exporter uses an appropriate annotation assembler, the expected JMX contract is:

```text
ObjectName:
  training.aop:type=OrderWorker,name=Primary

Attribute:
  ProcessedJobs (readable)

Operation:
  resetProcessedJobs()
```

**The goal is not to prove annotations are lost**, but to verify whether the exporter recognizes them on the target when the proxy type changes.

## 7. Step 3 — Create an Aspect So Spring Actually Generates a Proxy

File `TraceAspect.java`:

```java
package example.jmx.lab;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TraceAspect {

    @Around("execution(* example.jmx.lab.OrderWorker.execute(..))")
    public Object aroundExecute(ProceedingJoinPoint point)
            throws Throwable {

        long started = System.nanoTime();
        try {
            return point.proceed();
        } finally {
            long elapsed = System.nanoTime() - started;
            System.out.println(
                "execute latency ns=" + elapsed);
        }
    }
}
```

This aspect requires no transaction manager or database. Its sole purpose is making Spring generate an AOP proxy, letting the lab reproduce both JDK and target-class proxies without adding complex transaction configuration.

Use `@EnableAspectJAutoProxy` across two configuration classes to switch proxy modes.

## 8. Step 4 — Configure Spring for a JDK Dynamic Proxy

File `JdkProxyConfig.java`:

```java
package example.jmx.lab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class JdkProxyConfig {

    @Bean
    public OrderWorker orderWorker() {
        return new OrderWorkerImpl();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

When the context creates the `orderWorker` bean, the aspect applies to `execute(..)` and Spring can return a JDK dynamic proxy implementing `OrderWorker`.

Runtime check:

```java
Object bean = context.getBean("orderWorker");

System.out.println("Bean type: " + bean.getClass());
System.out.println("Is AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("Is JDK proxy: " +
    AopUtils.isJdkDynamicProxy(bean));
System.out.println("Target type: " +
    AopUtils.getTargetClass(bean));
```

Imports:

```java
import org.springframework.aop.support.AopUtils;
```

Useful assertions:

```java
assertTrue(AopUtils.isJdkDynamicProxy(bean));
assertFalse(bean instanceof OrderWorkerImpl);
assertTrue(bean instanceof OrderWorker);
```

These assertions verify the **proxy mode**, not that the JMX exporter will fail.

## 9. Step 5 — Reproduce the Concrete-Type Visibility Error

A controlled way to reproduce the issue is simulating an export/inspection component that requires the concrete implementation type:

```java
Object bean = context.getBean("orderWorker");

OrderWorkerImpl concrete = (OrderWorkerImpl) bean;
```

With a JDK proxy, the cast fails:

```text
java.lang.ClassCastException:
  ...JdkDynamicAopProxy... cannot be cast to OrderWorkerImpl
```

Do not rely on exact proxy class names or exception messages in tests. What needs to be proven is that `OrderWorkerImpl.class.isInstance(bean)` is `false`.

This is a deterministic failure for a **client/inspector coupled to the implementation class**. In real Spring JMX, an assembler may resolve the target class and still export successfully. To verify JMX behavior, inspect `MBeanInfo` separately rather than concluding from a `ClassCastException` alone.

### 9.1. Why might an exporter lose operations?

A custom metadata assembler might do the following:

```java
for (Method method : bean.getClass().getMethods()) {
    // Search for @ManagedOperation directly on runtime proxy methods.
}
```

If the proxy is a JDK proxy implementing only the business interface, `resetProcessedJobs` is absent from `bean.getClass().getMethods()`. Consequently, the inspector cannot find the operation and skips exporting it.

**This is a design flaw in the introspection path**, not an inevitable rule of every Spring JMX exporter.

A better approach is using `AopUtils.getTargetClass(bean)` and Spring's proper metadata support, or separating a management facade.

## 10. Step 6 — Configure a Target-Class Proxy

File `TargetClassProxyConfig.java`:

```java
package example.jmx.lab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class TargetClassProxyConfig {

    @Bean
    public OrderWorkerImpl orderWorker() {
        return new OrderWorkerImpl();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

With `proxyTargetClass=true`, Spring creates a subclass proxy when the class can be proxied.

Verification:

```java
Object bean = context.getBean("orderWorker");

assertTrue(AopUtils.isCglibProxy(bean));
assertTrue(bean instanceof OrderWorkerImpl);
assertTrue(bean instanceof OrderWorker);
```

Because the proxy is a subclass, an inspector expecting `OrderWorkerImpl` can access these public methods. However, this approach carries trade-offs around types, `final` methods, native/AOT constraints, and effects on other advisors.

### 10.1. When using @Transactional

In a transaction-proxy-based application, you may configure:

```java
@EnableTransactionManagement(proxyTargetClass = true)
```

This parameter adjusts the proxy strategy within the corresponding transaction configuration scope. If an application has multiple auto-proxy creators, enabling class-based proxies can affect other proxies because Spring unifies AOP proxy configuration. Run regression tests rather than flipping the entire application just for one MBean.

For this lab, `@EnableAspectJAutoProxy` is sufficient to reproduce proxying without needing a database.

## 11. Step 7 — Use an Isolated MBeanServer

No remote JMX is needed. Create a server in tests:

```java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("aop.test");
```

Example `@Bean`:

```java
@Bean
public MBeanServer testMBeanServer() {
    return MBeanServerFactory.newMBeanServer("aop.test");
}
```

Crucially, the exporter must use **that exact server**. If the exporter registers in the platform server while tests read the isolated server, you will get `InstanceNotFoundException` and mistakenly blame AOP.

Fixed ObjectName:

```java
ObjectName name = new ObjectName(
    "training.aop:type=OrderWorker,name=Primary");
```

Never derive the ObjectName from the proxy class name, because it can change with proxy mode, JVM restarts, or Spring configuration.

## 12. Step 8 — Export the MBean from the Target-Class Proxy

Below is how to configure `MBeanExporter` with Spring JMX annotation metadata; in real projects you can use `@EnableMBeanExport` if autodetection is desired.

```java
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration(proxyBeanMethods = false)
public class JmxExporterConfig {

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("aop.test");
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer testMBeanServer,
            OrderWorker orderWorker,
            MetadataMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "training.aop:type=OrderWorker,name=Primary",
            orderWorker));
        return exporter;
    }
}
```

This configuration requires the appropriate imports and Spring JMX dependencies. The example mainly illustrates **wiring between target/proxy, metadata assembler, and MBeanServer**.

**Warning about version-specific constructors/configuration:** Some Spring JMX APIs have additional initialization contracts or naming strategies. Always check your project's Spring version and run integration tests inspecting the actual `MBeanInfo`. For a simple prototype, use `@EnableMBeanExport` in a context without competing exporters.

### 12.1. Avoid two exporters registering duplicates

If `@EnableMBeanExport` is active alongside a custom `MBeanExporter` using the same ObjectName, tests can fail with `InstanceAlreadyExistsException`. The lab should have only **one owner** registering a given ObjectName on the test MBeanServer.

## 13. Step 9 — Inspect MBeanInfo After Export

Read metadata of the registered resource:

```java
ObjectName name = new ObjectName(
    "training.aop:type=OrderWorker,name=Primary");

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("ATTR: " + attribute.getName());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("OP: " + operation.getName());
}
```

Checks:

```java
boolean attributeVisible =
    Arrays.stream(info.getAttributes())
        .anyMatch(a -> a.getName().equals("ProcessedJobs")
            && a.isReadable());

boolean operationVisible =
    Arrays.stream(info.getOperations())
        .anyMatch(o -> o.getName().equals("resetProcessedJobs"));

assertTrue(attributeVisible);
assertTrue(operationVisible);
```

If the JDK proxy configuration still exports the attribute/operation accurately, note that: Spring's exporter is handling metadata/target class resolution well. In that case, the concrete-type cast failure remains true, yet **it does not prove a JMX failure**. The lab should explain what was actually observed rather than forcing a nonexistent failure.

## 14. Step 10 — Access Attribute and Invoke Operation via JMX

Once `MBeanInfo` confirms the contract:

```java
Object value =
    server.getAttribute(name, "ProcessedJobs");

System.out.println("Processed jobs = " + value);
```

Invoke operation:

```java
server.invoke(
    name,
    "resetProcessedJobs",
    new Object[0],
    new String[0]);
```

Then:

```java
assertEquals(0,
    server.getAttribute(name, "ProcessedJobs"));
```

If the operation is missing, JMX reports `ReflectionException`; if the MBean is not registered, `InstanceNotFoundException`; if metadata matches but the business method throws an exception, you may see `MBeanException` or `RuntimeMBeanException`.

These exceptions help pinpoint whether the fault lies in **registration**, **exposure**, **signature**, or **business execution**. Do not assume every error after enabling AOP is caused by the proxy strategy.

## 15. JUnit Tests for JDK Proxy and Target-Class Proxy

Example type-visibility test, independent of JMX:

```java
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class ProxyModeTest {

    @Test
    void jdkProxyDoesNotExposeConcreteType() {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JdkProxyConfig.class)) {

            Object bean = context.getBean("orderWorker");

            assertTrue(AopUtils.isJdkDynamicProxy(bean));
            assertTrue(bean instanceof OrderWorker);
            assertFalse(bean instanceof OrderWorkerImpl);
        }
    }

    @Test
    void targetClassProxyRetainsConcreteType() {
        try (var context =
                new AnnotationConfigApplicationContext(
                    TargetClassProxyConfig.class)) {

            Object bean = context.getBean("orderWorker");

            assertTrue(AopUtils.isCglibProxy(bean));
            assertTrue(bean instanceof OrderWorker);
            assertTrue(bean instanceof OrderWorkerImpl);
        }
    }
}
```

To test JMX, open a context with `TargetClassProxyConfig` and `JmxExporterConfig`, sharing the same MBeanServer.

### 15.1. Regression test for the JMX contract

```java
@Test
void targetClassProxyExportsManagementContract()
        throws Exception {

    try (var context =
            new AnnotationConfigApplicationContext(
                TargetClassProxyConfig.class,
                JmxExporterConfig.class)) {

        MBeanServer server =
            context.getBean(MBeanServer.class);

        ObjectName name = new ObjectName(
            "training.aop:type=OrderWorker,name=Primary");

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(Arrays.stream(info.getAttributes())
            .anyMatch(a -> a.getName()
                .equals("ProcessedJobs")));

        assertTrue(Arrays.stream(info.getOperations())
            .anyMatch(op -> op.getName()
                .equals("resetProcessedJobs")));

        server.invoke(
            name, "resetProcessedJobs",
            new Object[0], new String[0]);

        assertEquals(
            0, server.getAttribute(name, "ProcessedJobs"));
    }
}
```

Imports for `MBeanServer`, `ObjectName`, `MBeanInfo`, and `Arrays` must be added to the test file.

If your project's Spring JMX setup handles JDK proxies properly, add a similar test for the JDK case to guard compatibility rather than expecting the JDK test to always fail.

## 16. Experiment: Custom Inspector Looking at the Wrong Type

To see the root cause more deeply, write a diagnostic inspector simulating the flawed path:

```java
public static boolean hasOperationOnRuntimeClass(Object bean) {
    return Arrays.stream(bean.getClass().getMethods())
        .anyMatch(m -> m.getName()
            .equals("resetProcessedJobs"));
}
```

Possible output:

```text
JDK proxy: false
Class-based proxy: true
```

Now write the better path:

```java
public static boolean hasOperationOnTargetClass(Object bean) {
    Class<?> type = AopUtils.getTargetClass(bean);

    return Arrays.stream(type.getMethods())
        .anyMatch(m -> m.getName()
            .equals("resetProcessedJobs"));
}
```

In both cases, the target class contains the method.

**Lesson:** switching to a class-based proxy is one fix when a component forces concrete implementation type usage; when the component can be modified, proper target-class introspection or a dedicated management facade is usually more sustainable.

## 17. When Target-Class Proxying Does Not Solve the Issue

Some causes lie outside the proxy strategy:

| Symptom | Possible Cause | Verification |
|---|---|---|
| MBean completely missing | Exporter not active | `isRegistered`, bean lifecycle |
| MBean under different ObjectName | Different naming strategy | `queryNames` |
| Missing getter/operation | Metadata assembler not reading annotations | `MBeanInfo`, config |
| JDK proxy missing method | Interface proxy does not expose method | `getInterfaces`, target class |
| Class-based proxy fails | Final class/method or module constraints | Proxy creation error |
| Operation invocation fails | Wrong signature or method threw exception | `MBeanInfo`, exception cause |
| JConsole does not see MBean | Exporter uses another MBeanServer | Compare server identity |
| MBean exists but transaction does not run | Bypassed AOP proxy/self-invocation | Check advisor invocation |
| Flaky test | Multiple contexts registering same ObjectName | Isolated server and lifecycle |

Do not use target-class proxying to mask a broken exporter configuration. Inspect registration and `MBeanInfo` first before changing AOP settings.

## 18. Management Facade: A Sustainable Alternative

In production, you do not always want the JMX API coupled to a business bean's implementation.

A dedicated facade:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.aop:type=WorkerManagement,name=Primary")
public class OrderWorkerManagementFacade {

    private final OrderWorker worker;
    private final OrderWorkerStatistics stats;

    public OrderWorkerManagementFacade(
            OrderWorker worker,
            OrderWorkerStatistics stats) {
        this.worker = worker;
        this.stats = stats;
    }

    @ManagedAttribute
    public int getProcessedJobs() {
        return stats.getProcessedJobs();
    }

    @ManagedOperation
    public void resetStatistics() {
        stats.reset();
    }
}
```

`OrderWorkerStatistics` is a project-defined component. `OrderWorker` can remain a JDK proxy for business methods; the facade serves as the managed resource with a stable JMX contract.

Advantages:

- Does not force business interfaces to carry management methods.
- Does not rely on runtime proxy class names for ObjectNames.
- Allows per-operation authorization, validation, and auditing.
- Makes testing the JMX API independent of transaction/caching implementations.
- Changing AOP proxy mode has less impact on the management facade.

**Note:** if the facade itself is wrapped by an AOP proxy, test its metadata and export just like any managed bean. Do not assume separating a facade eliminates all proxy concerns.

## 19. Checking Transaction Semantics After Changing Proxy Mode

When an application uses `@Transactional`, changing proxy mode can affect many beans. Regression tests should check:

1. Methods are invoked through the Spring-managed bean, not directly on the raw target.
2. Transaction advice actually triggers on expected methods.
3. Both interface and concrete-type injection still work.
4. `final`/`private` methods are not assumed to be advised.
5. Business exception rollback behavior remains intact.
6. Self-invocation is still understood to bypass the proxy.
7. Custom advisors, caching, and security are not lost.
8. JMX operations do not accidentally bypass authorization.
9. MBean ObjectNames and attributes/operations remain stable.
10. No duplicate MBean registrations across contexts.

**Caution:** target-class proxying improves concrete method visibility, but does not guarantee every management operation call passes through transaction/security advice. That still depends on the exported target, proxy, and actual call path.

## 20. Testing Threads, Lifecycle, and ObjectNames

JMX operations can be called on a different thread from business execution. An operation resetting counters must be thread-safe. The example uses `AtomicInteger` to avoid unnecessary races.

With an isolated MBeanServer:

```java
try (var context =
        new AnnotationConfigApplicationContext(
            TargetClassProxyConfig.class,
            JmxExporterConfig.class)) {
    // Verify registration and invoke operations.
}
// Spring context closes and exporter cleans up its registrations.
```

Do not reuse the same platform ObjectName across multiple parallel tests. If each test uses `newMBeanServer()`, ensure both exporter and client use that isolated server reference.

A lifecycle check:

```java
assertTrue(server.isRegistered(name));
context.close();
assertFalse(server.isRegistered(name));
```

If a test unregisters an MBean mid-run, cleanup behavior depends on the exporter; never run destructive tests on a shared server.

## 21. Diagnostic Workflow When AOP Causes JMX Issues

```text
1. Enabled AOP and MBean disappeared / lost methods?
          |
          v
2. Identify proxy mode using AopUtils
          |
          v
3. Check ObjectName on the right MBeanServer
          |
          v
4. Read actual MBeanInfo attributes/operations
          |
          +-- ObjectName missing?
          |      -> exporter/naming/server/context
          |
          +-- Method missing?
          |      -> proxy interfaces, assembler, target metadata
          |
          +-- Method present but invoke fails?
                 -> signature, AOP/target exception
          |
          v
5. Try a management interface or facade
          |
          v
6. If concrete type is still required:
   test target-class proxy in a lab
          |
          v
7. Regression test JMX + AOP semantics
```

This sequence avoids changing the proxy mode system-wide when the true cause is merely an ObjectName or an exporter setting.

## 22. Practice Exercises

### Exercise A — Observe both proxy modes

Run `JdkProxyConfig` and `TargetClassProxyConfig`. Print class name, target class, and `AopUtils.isJdkDynamicProxy`/`isCglibProxy`. Explain the relationship between the business interface and implementation.

### Exercise B — Reproduce ClassCastException

Fetch the `orderWorker` bean from the JDK proxy context and attempt casting to `OrderWorkerImpl`. Use `assertThrows(ClassCastException.class, ...)` in a test. Then test with the class-based proxy.

### Exercise C — Runtime vs. target inspection

Write two helpers: `hasOperationOnRuntimeClass` and `hasOperationOnTargetClass`. Compare under JDK proxy and target-class proxy.

### Exercise D — JMX metadata

Export the bean using Spring annotation metadata, inspect `MBeanInfo`, and assert `ProcessedJobs` and `resetProcessedJobs`. Compare both proxy modes; do not pre-judge failure before running.

### Exercise E — Transactions

Add a transaction manager and `@Transactional` in a lab project with an in-memory database. Compare advisor activation between JDK and class-based proxies. Verify rollback behavior and avoid self-invocation in test design.

### Exercise F — Management facade

Create `OrderWorkerManagementFacade` obtaining `OrderWorkerStatistics` from a separate bean. Keep the business bean as a JDK proxy and export the facade. Verify the JMX contract does not depend on the business bean's concrete type.

### Exercise G — Failure matrix

Intentionally use a wrong ObjectName, a wrong operation signature, and an exporter on a different server. Classify the exceptions; explain why changing proxy mode does not solve these errors.

## 23. Self-Check Questions

1. How do JDK dynamic proxies and target-class proxies differ in their relationship to the implementation class?
2. Why might a method present only on the implementation not be visible on a JDK proxy?
3. What does `AopUtils.getTargetClass` help debug?
4. Does a JDK proxy cause every Spring JMX exporter to fail?
5. When is `proxyTargetClass=true` reasonable?
6. Why are `final` methods/classes an issue with class-based proxies?
7. If `MBeanInfo` is already correct, do you need to change the proxy mode?
8. Why must transaction/security advice be re-tested after changing proxy mode?
9. How does a management facade keep the JMX contract stable?
10. How do you distinguish registration errors from invocation errors?
11. Why are isolated MBeanServers needed in tests?
12. What happens if two exporters register the same ObjectName?

## 24. References

- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — AopUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — MetadataMBeanInfoAssembler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework API — AnnotationJmxAttributeSource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html

**Key takeaway:** target-class proxying can fix errors when a component depends on a concrete implementation type that a JDK proxy does not expose. However, a proper JMX exporter/assembler can often handle JDK proxies directly. Always verify **proxy mode, MBean registration, MBeanInfo, and invocation** before altering AOP configuration, and re-test transaction/security semantics afterward.
