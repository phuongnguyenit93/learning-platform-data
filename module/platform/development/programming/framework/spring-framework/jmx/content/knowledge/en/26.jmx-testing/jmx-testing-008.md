# Testing Local Proxies via MBeanServerConnection in Spring Framework JMX

## 1. Goal and Scenario

Spring Framework provides a JMX proxy mechanism so Java code can interact with MBeans through a familiar interface. Instead of calling `getAttribute`, `setAttribute`, and `invoke` everywhere, a client bean can call `monitor.getActiveJobs()` or `monitor.resetCounters()`. Behind the scenes, `MBeanProxyFactoryBean` uses `MBeanClientInterceptor` and `MBeanServerConnection` to translate calls into JMX operations.

However, a test that merely calls the Java target directly and asserts a value is **not enough**. It does not prove that the MBean is registered, that the proxy points to the right server and ObjectName, that attribute/operation names match, or that the Spring client interceptor actually routes calls through JMX.

This lesson walks through building well-scoped integration tests:

- Create an isolated MBeanServer or use an explicitly injected server.
- Register a Standard MBean or Spring-managed bean via `MBeanExporter`.
- Configure a local proxy using `MBeanProxyFactoryBean`.
- Use `MBeanServerConnection` to check registration and metadata.
- Compare calls through the Java proxy against `getAttribute`, `setAttribute`, and `invoke` over JMX.
- Test read-only attributes, operation signatures, missing ObjectNames, and execution errors.
- Ensure test cleanup to prevent collisions during repeated or parallel runs.

## 2. The Path Under Test

```text
Spring test / client
       |
       v
WorkerControl proxy (Java interface)
       |
       v
MBeanProxyFactoryBean
       |
       v
MBeanClientInterceptor
       |
       v
MBeanServerConnection
       |
       v
MBeanServer
       |
       v
Registered WorkerControl MBean
       |
       v
WorkerControl target
```

To confirm the local proxy truly works, tests should observe results at the **JMX boundary**, not only on the target.

### 2.1. Three Testing Levels

| Test Type | Example | What It Proves |
|---|---|---|
| Target unit test | `target.getActiveJobs()` | Java business logic |
| MBean integration test | `server.getAttribute(name, "ActiveJobs")` | MBean registered, valid metadata/dispatch |
| Proxy integration test | `proxy.getActiveJobs()` compared with server | Spring client proxy calls the right MBean via JMX |

Unit tests remain necessary, but they cannot replace the third test.

## 3. What Is MBeanServerConnection?

`javax.management.MBeanServerConnection` is the common interface a client uses to interact with an MBeanServer. `MBeanServer` implements this interface, so the same API works with a local server:

```java
MBeanServer server = MBeanServerFactory.newMBeanServer();
MBeanServerConnection connection = server;
```

Key methods:

```java
boolean isRegistered(ObjectName name);
Object getAttribute(ObjectName name, String attribute);
AttributeList getAttributes(ObjectName name, String[] names);
void setAttribute(ObjectName name, Attribute attribute);
Object invoke(ObjectName name, String operation, Object[] args,
              String[] signature);
MBeanInfo getMBeanInfo(ObjectName name);
Set<ObjectName> queryNames(ObjectName pattern, QueryExp query);
```

With a local server, no `JMXConnector`, network port, TLS, or RMI is needed. Yet lookup, metadata, signature, and exception rules remain JMX rules.

**Distinction:** a local `MBeanServerConnection` does not test remote authentication, TLS, firewalls, or connector lifecycles. Testing those concerns requires dedicated remote JMX integration tests.

## 4. Why Use a Dedicated MBeanServer in Tests?

The platform server obtained from `ManagementFactory.getPlatformMBeanServer()` is a shared JVM resource. If multiple test contexts export `training.spring:type=Worker,name=Primary`, `InstanceAlreadyExistsException` can easily occur.

A dedicated fixture:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer isolated =
    MBeanServerFactory.newMBeanServer("test.jmx");
```

Advantages:

1. No name collisions with production-like MBeans or other tests on the platform server.
2. Clean registry state verifiable per test.
3. Tests can close the context and verify unregistration.
4. Independent fixtures can be created for parallel test execution.
5. No need to enable remote JMX.

`newMBeanServer` creates a server not registered with `MBeanServerFactory` like some other server creation paths. Even so, still close the Spring context and clean up test-created resources.

Do not assume JConsole will auto-discover this private server; local JConsole attach typically inspects the platform management interface.

## 5. Java Contract for Proxy and MBean

We choose a Standard MBean to separate the proxy concern from annotation metadata and keep the contract explicit.

File `WorkerControlMBean.java`:

```java
package example.jmx;

public interface WorkerControlMBean {
    int getActiveJobs();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void resetCounters();
}
```

File `WorkerControl.java`:

```java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class WorkerControl implements WorkerControlMBean {
    private final AtomicInteger activeJobs = new AtomicInteger();
    private volatile boolean enabled = true;

    @Override
    public int getActiveJobs() {
        return activeJobs.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void resetCounters() {
        activeJobs.set(0);
    }

    public void startedOneJob() {
        if (enabled) {
            activeJobs.incrementAndGet();
        }
    }
}
```

Expected JMX mappings:

| Interface method | JMX representation |
|---|---|
| `getActiveJobs()` | Attribute `ActiveJobs`, readable, not writable |
| `isEnabled()` | Attribute `Enabled`, readable |
| `setEnabled(boolean)` | Attribute `Enabled`, writable |
| `resetCounters()` | Operation `resetCounters`, no parameters |

This is a Standard MBean contract; the JMX server derives metadata from `WorkerControlMBean`. In systems using Spring `@ManagedResource` and `@ManagedAttribute`, equivalent results must be verified through the assembler.

## 6. Configuring Spring Exporter and Local Proxy

File `JmxTestConfiguration.java`:

```java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration(proxyBeanMethods = false)
public class JmxTestConfiguration {

    public static final String NAME =
        "training.spring:type=Worker,name=Primary";

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("test.jmx");
    }

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public MBeanExporter workerExporter(
            MBeanServer testMBeanServer,
            WorkerControl workerControl) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(NAME, workerControl));
        return exporter;
    }

    @Bean
    public MBeanProxyFactoryBean workerProxy(
            MBeanServer testMBeanServer) throws Exception {

        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();
        factory.setServer(testMBeanServer);
        factory.setObjectName(new ObjectName(NAME));
        factory.setProxyInterface(WorkerControlMBean.class);
        return factory;
    }
}
```

Two critical wiring points:

- The exporter is injected with the **exact fixture server**.
- The proxy is also injected with the **exact fixture server**, and the same ObjectName.

If the exporter uses the platform server while the proxy uses the test server, the client will hit `InstanceNotFoundException` even though the target object is completely healthy.

### 6.1. Injection Ambiguity Trap

`workerControl` implements `WorkerControlMBean`; the product of `MBeanProxyFactoryBean` implements the same interface. Injecting `WorkerControlMBean` by type without a qualifier can cause Spring to find multiple candidates.

In tests, look it up by **bean name**:

```java
WorkerControlMBean proxy =
    context.getBean("workerProxy", WorkerControlMBean.class);
```

This avoids accidentally receiving the target and assuming the proxy is working.

## 7. First Test: Registration and Metadata

File `LocalMBeanProxyIntegrationTest.java`:

```java
package example.jmx;

import java.util.Arrays;
import javax.management.*;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class LocalMBeanProxyIntegrationTest {

    @Test
    void mbeanHasExpectedMetadata() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JmxTestConfiguration.class)) {

            MBeanServerConnection connection =
                context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                JmxTestConfiguration.NAME);

            assertTrue(connection.isRegistered(name));

            MBeanInfo info = connection.getMBeanInfo(name);

            MBeanAttributeInfo jobs =
                Arrays.stream(info.getAttributes())
                    .filter(a -> a.getName().equals("ActiveJobs"))
                    .findFirst()
                    .orElseThrow();

            assertTrue(jobs.isReadable());
            assertFalse(jobs.isWritable());
            assertEquals("int", jobs.getType());

            MBeanAttributeInfo enabled =
                Arrays.stream(info.getAttributes())
                    .filter(a -> a.getName().equals("Enabled"))
                    .findFirst()
                    .orElseThrow();

            assertTrue(enabled.isReadable());
            assertTrue(enabled.isWritable());

            assertTrue(Arrays.stream(info.getOperations())
                .anyMatch(op -> op.getName()
                    .equals("resetCounters")));
        }
    }
}
```

This test proves an MBean is present on the server and its metadata matches the contract. However, it has not yet invoked the Spring proxy; the next steps cover that.

## 8. Testing Getters via Proxy and getAttribute

```java
@Test
void getterProxyReadsJmxAttribute() throws Exception {
    try (var context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        WorkerControl target =
            context.getBean(WorkerControl.class);

        WorkerControlMBean proxy =
            context.getBean(
                "workerProxy",
                WorkerControlMBean.class);

        MBeanServerConnection connection =
            context.getBean(MBeanServer.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.NAME);

        assertNotSame(target, proxy);

        assertEquals(0, proxy.getActiveJobs());
        assertEquals(0, connection.getAttribute(
            name, "ActiveJobs"));

        target.startedOneJob();

        assertEquals(1, proxy.getActiveJobs());
        assertEquals(
            connection.getAttribute(name, "ActiveJobs"),
            proxy.getActiveJobs());
    }
}
```

This test confirms the Java getter through the proxy returns the JMX value and reflects MBean state.

**Important note:** `assertNotSame(target, proxy)` proves two distinct references, which alone is not enough to prove the JMX path. Combining it with `getAttribute` and testing failure after unregistration (in a dedicated fixture) provides stronger proof.

### 8.1. Why Not Just Use `assertEquals(target.getActiveJobs(), proxy.getActiveJobs())`?

If you accidentally inject the target instead of the proxy, the result still matches. Always retrieve the proxy by name, assert distinct instances, and verify JMX registration/metadata.

## 9. Testing Setters via Proxy and setAttribute

If the management interface exposes `setEnabled(boolean)`, the Spring client proxy must translate the call into a JMX attribute write.

```java
@Test
void setterProxyWritesJmxAttribute() throws Exception {
    try (var context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        WorkerControlMBean proxy =
            context.getBean(
                "workerProxy",
                WorkerControlMBean.class);

        MBeanServerConnection connection =
            context.getBean(MBeanServer.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.NAME);

        assertTrue(proxy.isEnabled());

        proxy.setEnabled(false);

        assertEquals(false,
            connection.getAttribute(name, "Enabled"));

        assertFalse(proxy.isEnabled());

        connection.setAttribute(
            name, new Attribute("Enabled", true));

        assertTrue(proxy.isEnabled());
    }
}
```

This verifies bidirectional flow: proxy `setEnabled` updates the attribute, and a `setAttribute` via the JMX API is read back by the proxy.

Never add a setter to a read-only attribute in a real system just to test the write path. Use the `Enabled` property already designed as writable.

## 10. Testing Operations via Proxy and invoke

```java
@Test
void operationProxyInvokesMBean() throws Exception {
    try (var context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        WorkerControl target =
            context.getBean(WorkerControl.class);

        WorkerControlMBean proxy =
            context.getBean(
                "workerProxy",
                WorkerControlMBean.class);

        MBeanServerConnection connection =
            context.getBean(MBeanServer.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.NAME);

        target.startedOneJob();
        assertEquals(1, proxy.getActiveJobs());

        proxy.resetCounters();

        assertEquals(0,
            connection.getAttribute(name, "ActiveJobs"));

        target.startedOneJob();

        connection.invoke(
            name, "resetCounters",
            new Object[0], new String[0]);

        assertEquals(0, proxy.getActiveJobs());
    }
}
```

Calling `proxy.resetCounters()` is a Java interface call, while its effect must be observed through the MBeanServer. Calling `connection.invoke` tests the operation contract directly.

### 10.1. Signature of Parameterized Operations

If an interface declares:

```java
void setLimit(int limit);
```

by JavaBeans rules, `setLimit` may be treated as the setter for attribute `Limit`, not necessarily an operation. To illustrate an operation unambiguously, use:

```java
void resetForQueue(String queue);
```

JMX invocation:

```java
connection.invoke(
    name,
    "resetForQueue",
    new Object[]{"orders"},
    new String[]{String.class.getName()});
```

Do not pass arbitrary type names like `"String"` or `"Integer"`; the signature must match the actual `MBeanOperationInfo`.

## 11. Testing Read-Only Behavior and Attribute Write Errors

`ActiveJobs` has no setter in `WorkerControlMBean`, so metadata is expected to show `writable=false`.

```java
@Test
void activeJobsIsReadOnly() throws Exception {
    try (var context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        MBeanServerConnection connection =
            context.getBean(MBeanServer.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.NAME);

        assertThrows(
            AttributeNotFoundException.class,
            () -> connection.setAttribute(
                name, new Attribute("ActiveJobs", 99)));
    }
}
```

A JMX implementation may express a read-only write error according to its contract; to reduce coupling to exception messages, asserting `isWritable=false` metadata is equally important.

A client interface lacking a setter is **not enough** to conclude the server-side attribute is read-only: another client could call `setAttribute`. Therefore, protect it in MBean metadata.

## 12. Testing Wrong ObjectNames or Unregistered MBeans

An MBean proxy depends on an actual registration. In an isolated test fixture, you can prove the proxy fails when the object disappears from the server.

```java
@Test
void proxyFailsAfterMBeanUnregistration() throws Exception {
    try (var context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        MBeanServer server =
            context.getBean(MBeanServer.class);

        WorkerControlMBean proxy =
            context.getBean(
                "workerProxy",
                WorkerControlMBean.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.NAME);

        assertTrue(server.isRegistered(name));

        server.unregisterMBean(name);

        assertFalse(server.isRegistered(name));

        assertThrows(RuntimeException.class,
            proxy::getActiveJobs);
    }
}
```

This tests the negative path inside a **dedicated test server**, not on a shared platform server. Exceptions through a Spring proxy may be wrapped in a specific runtime exception; production tests should pin down the exact exception type for the project's Spring version and inspect the root cause rather than relying solely on a generic type.

**Cleanup note:** the exporter may attempt to unregister on context close, though implementations usually track registrations they created. A test that mutates the registry directly must account for/verify how exporter cleanup behaves in the version in use. To avoid interfering with the exporter's lifecycle, point a proxy at a non-existent ObjectName from the start.

## 13. Testing That the Proxy Does Not Point to the Wrong Server

A subtle wiring bug:

```text
MBeanExporter --> Server A
MBeanProxyFactoryBean --> Server B
```

Both servers are valid and in the same JVM, yet the proxy cannot find the MBean.

Test:

```java
MBeanServer serverA =
    MBeanServerFactory.newMBeanServer("A");

MBeanServer serverB =
    MBeanServerFactory.newMBeanServer("B");
```

Register the MBean on A while configuring the proxy to use B. Calls through the proxy will fail because the ObjectName is not registered on B.

To verify server identity in Spring configuration, inject the exact same `MBeanServer` bean into both exporter and proxy; integration tests can assert the same server reference before calling getters.

**Do not infer that matching default domains mean the same server.** Two MBeanServers can share a domain name while having completely separate registries.

## 14. Testing with AnnotationMBeanExporter and @ManagedAttribute

Standard MBeans provide an easy starting point. In real Spring Framework applications, beans often use annotations:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "training.spring:type=Queue,name=Orders")
public class QueueMonitor {

    private volatile int pending;

    @ManagedAttribute
    public int getPending() {
        return pending;
    }

    @ManagedOperation
    public void resetPending() {
        pending = 0;
    }
}
```

Spring can export the bean via `@EnableMBeanExport` or a compatible `AnnotationMBeanExporter`/assembler. Client interface:

```java
public interface QueueMonitorManagement {
    int getPending();
    void resetPending();
}
```

An `MBeanProxyFactoryBean` configured with `setProxyInterface(QueueMonitorManagement.class)` and the matching ObjectName will work **provided** the actual metadata exposes attribute `Pending` and operation `resetPending` accurately.

Verify:

- Is the annotation exporter enabled in the context containing the bean?
- Is the ObjectName taken from metadata or another naming strategy?
- Does another exporter collide on registration?
- Are methods visible to the assembler on the proxy/target interface?
- Does the proxy use the same MBeanServer?

Do not rely solely on annotations present in source code.

## 15. Testing with Spring AOP or @Transactional

When a bean is wrapped by a Spring AOP proxy, the actual class seen by the exporter may differ from the target class. With JDK dynamic proxies, management methods not declared on the proxied interface may be harder for certain assembler configurations to discover.

Helpful test matrix:

| Configuration | What to Verify |
|---|---|
| No AOP | MBean registration and proxy work |
| JDK dynamic proxy | Management interface remains exposed |
| Class-based proxy | Metadata does not change unintentionally |
| Transaction advice | Operations run through advice as designed |
| Custom MBeanInfoAssembler | Attributes/operations match contract |
| Multiple contexts | Exporter and client proxy share the right server |

If adding `@Transactional` breaks the JMX proxy, do not remove transactions just to make the test pass. Inspect target/proxy types, annotation metadata, and consider a dedicated management facade if needed.

## 16. Fixture Lifecycle: Avoiding Cross-Test Interference

Practical rules:

1. Create a fresh context and MBeanServer per test or isolated fixture.
2. Close the context with try-with-resources.
3. Never register MBeans under duplicate ObjectNames on the platform server when running in parallel.
4. Do not use `RegistrationPolicy.IGNORE_EXISTING` to mask collisions between tests.
5. Do not assume threads/executors created by JMX listeners automatically shut down.
6. Use `@AfterEach` for cleanup if the test creates resources outside Spring's lifecycle.
7. Separate remote connector tests from local proxy tests.
8. Never alter an MBeanServer in use by another application.

Single test run example:

```java
try (var context =
        new AnnotationConfigApplicationContext(
            JmxTestConfiguration.class)) {
    // assertions...
}
// Spring context close triggers exporter lifecycle cleanup.
```

Calling `context.close()` invokes exporter cleanup, which normally unregisters MBeans registered by that exporter. If a test manually unregisters or replaces MBeans, inspect the specific policy and implementation behavior.

## 17. Synchronization and Latency of Local Proxies

A local proxy does not cross the network, yet still incurs:

- JMX dispatch overhead.
- Reflection/adapter or Spring interceptor invocation.
- Name and signature validation.
- AOP proxy/interceptors on the managed bean, if any.
- Locks and execution time of the getter/operation.

Avoid using a local proxy for per-request metric access at ultra-high throughput when a direct Java method or metrics library is more suitable. For management/monitoring, proxies decouple the management contract at a measurable cost.

### 17.1. Measuring Relative Latency

```java
long started = System.nanoTime();
int active = proxy.getActiveJobs();
long elapsed = System.nanoTime() - started;

System.out.println(
    "Active=" + active + ", elapsed ns=" + elapsed);
```

This is only exploratory measurement, not a formal benchmark. Proper performance comparisons require warm-up, many iterations, statistics, and a controlled environment. Correctness tests should not enforce tight timing assertions on CI.

## 18. Troubleshooting by Error Type

| Symptom | Common Cause | Evidence |
|---|---|---|
| Proxy bean created, getter fails | MBean unregistered or wrong ObjectName | `isRegistered` |
| Getter reports missing attribute | Different JavaBeans/assembler naming | `MBeanInfo.getAttributes()` |
| Setter has no effect | Read-only attribute | `isWritable()` |
| Operation missing | Wrong metadata/signature | `MBeanInfo.getOperations()` |
| Proxy returns stale value | Target/caching/concurrency | Compare target vs. JMX read |
| Passes alone, fails in suite | Shared platform MBeanServer or collision | Server identity, names |
| Spring DI ambiguity | Target and proxy share interface | Inject by bean name/qualifier |
| MBean remains after context close | Missing lifecycle cleanup or manual registration | `isRegistered` after close |
| MBean disappears after enabling AOP | Proxy method visibility/assembler | `AopUtils` and `MBeanInfo` |
| Remote test fails, local passes | Connector, auth, TLS, RMI | Test remote layer separately |

### 18.1. Diagnostic Sequence

```text
1. Does context.getBean("workerProxy") return the expected proxy?
2. Which server did the exporter register the ObjectName into?
3. Is connection.isRegistered(name) true?
4. Does MBeanInfo contain the expected attributes/operations?
5. Do proxy getters/setters/operations execute?
6. What exception wrapper/cause is thrown?
7. Did test cleanup remove the registration?
```

Do not escalate permissions, enable remote JMX, or change collision policies before identifying the root cause.

## 19. Practice Exercises

### Exercise A — Getter and Attribute Metadata

Create `WorkerControl` with getter `ActiveJobs`. Use `MBeanProxyFactoryBean` to call `getActiveJobs()`, comparing with `getAttribute`. Assert `isReadable=true` and `isWritable=false`.

### Exercise B — Setter and Writable Attribute

Add `isEnabled()`/`setEnabled(boolean)`. Change the value via the proxy, read it back via the JMX API, then set it via the API and read via the proxy. Check metadata.

### Exercise C — Operation

Add `resetCounters()`, invoke it via the proxy and via `connection.invoke`. Verify state after each path.

### Exercise D — Wrong ObjectName

Create a proxy with an ObjectName different from the one the exporter registered. Call a getter and record the exception and cause. Use `queryNames` to locate the actual ObjectName.

### Exercise E — Server Isolation

Create two MBeanServers in the same JVM. Register into A while pointing the proxy at B. Demonstrate the failure. Then inject the same reference A into both exporter and proxy.

### Exercise F — Multiple Contexts

Place the exporter in a root context and the proxy in a child context. Ensure both use the same server and name. Close the root context and observe whether the proxy can still reach the MBean.

### Exercise G — AOP Regression

Take a bean exported via Spring JMX metadata. Enable an AOP proxy and re-run contract tests. If metadata disappears, inspect proxy interfaces/assembler or extract a management facade.

## 20. Self-Check Questions

1. How do `MBeanServerConnection` and `MBeanProxyFactoryBean` differ in role?
2. Why does a unit test calling the target directly fail to prove the proxy works?
3. Which test proves a getter maps to an attribute?
4. Why should you check `MBeanInfo` before trusting a proxy?
5. Why can DI ambiguity happen when both target and proxy implement the management interface?
6. What benefits does a dedicated MBeanServer bring to integration tests?
7. When the proxy calls `setEnabled`, how must the server expose the attribute?
8. Which JMX API invokes `resetCounters`?
9. If the ObjectName is unregistered, what issue will a proxy getter encounter?
10. Do local proxy tests verify TLS/RMI?
11. Why is `context.close()` critical for test isolation?
12. When AOP is enabled, which parts of the management contract can change?

## 21. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `MBeanProxyFactoryBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework API — `MBeanClientInterceptor`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanClientInterceptor.html
- Spring Framework API — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 API — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html

**Key takeaway:** Reliable local proxy tests must cross the real JMX boundary: the exporter registers the MBean into an MBeanServer, the proxy uses the same server and ObjectName, `MBeanServerConnection` verifies metadata and operation mapping, and the Spring proxy is invoked as a Java interface. Use isolated server fixtures and close contexts to keep tests independent, repeatable, and safe.
