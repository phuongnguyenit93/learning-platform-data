# Distinguishing a Local MBean Proxy from Calling a Spring Bean Directly

## Learning objectives

This lesson belongs to the **Local MBean Proxy** group of Spring Framework JMX. After completing it, you will be able to:

- Explain the path of an ordinary Java call to a Spring bean versus a call through a JMX MBean proxy in the same JVM.
- Distinguish a **Spring bean**, a **registered MBean**, a **JMX `ObjectName`**, and an **MBean proxy**.
- Configure `MBeanExporter` on the publishing side and `MBeanProxyFactoryBean` on the consuming side.
- Use the same management interface to call the bean directly or through the registry, then verify both paths.
- Understand differences in type checking, metadata, errors, overhead, lifecycle, and AOP effects.
- Know when to inject a Spring bean directly and when a local JMX proxy is the right choice.

## 1. Two calls that look similar but take different paths

Suppose a Spring application has a `JobMonitor` object with methods `getProcessedCount()`, `isEnabled()`, `setEnabled(boolean)`, and `reset()`. There are two ways to access it:

**Calling the Spring bean directly:** the consuming component receives the dependency via `@Autowired`, constructor injection, or `ApplicationContext.getBean(...)`, then calls methods on the Java reference.

**Calling through a local JMX proxy:** the consuming component holds a reference to a Java proxy representing the MBean. The proxy connects to an `MBeanServerConnection` in the same JVM, uses `ObjectName` to locate the registration, and translates method calls into JMX operations such as `getAttribute`, `setAttribute`, or `invoke`.

Diagram:

```text
A. Direct path
   Spring Service
        |
        | jobMonitor.reset()
        v
   Spring bean reference
        |
        v
   JobMonitor instance

B. Local JMX proxy path
   Spring Service
        |
        | jobMonitorProxy.reset()
        v
   MBean proxy
        |
        | MBeanServerConnection.invoke(ObjectName, ...)
        v
   MBeanServer registry
        |
        | look up MBean by ObjectName
        v
   Exported JobMonitor
```

The difference does not lie in Java call syntax: both can be `monitor.reset()`. The difference lies in **what kind of object the reference points to** and the intermediate mechanisms the call traverses.

“Local” here means the proxy accesses an `MBeanServerConnection` in the same process, without creating a JMX connection over TCP. However, a local proxy still goes through the JMX contract rather than turning into a direct call on the bean.

## 2. Components to distinguish

| Component | Role | Example |
| --- | --- | --- |
| Spring bean | Object managed by the IoC container | `JobMonitor` |
| Management interface | Methods permitted to be published and invoked via JMX | `JobMonitorMBean` |
| MBeanExporter | Registers beans into the JMX server | `MBeanExporter` |
| MBeanServer | MBean registry and access gateway | Platform `MBeanServer` |
| ObjectName | Identifies a registration within a server | `com.example.jobs:type=JobMonitor,name=primary` |
| MBean proxy | Java object translating method calls into JMX requests | `MBeanProxyFactoryBean` |
| Spring AOP proxy | Object standing in for a bean to apply interceptors like transactions, security, logging | Proxy created by Spring AOP |

**A JMX MBean proxy is not equivalent to a Spring AOP proxy.** Both may appear as Java proxies, but they have different purposes and processing paths. An MBean proxy acts as a **client of a JMX management interface**; a Spring AOP proxy is a mechanism for applying cross-cutting advice inside the application.

## 3. Standard MBean example used by both approaches

So that the exercise has the same Java contract on both sides, create a Standard MBean.

**JobMonitorMBean.java**

```java
package com.example.jmx;

public interface JobMonitorMBean {
    int getProcessedCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void reset();
}
```

**JobMonitor.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger processed = new AtomicInteger();
    private volatile boolean enabled = true;

    public void recordCompletedJob() {
        if (enabled) {
            processed.incrementAndGet();
        }
    }

    @Override
    public int getProcessedCount() {
        return processed.get();
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
    public void reset() {
        processed.set(0);
    }
}
```

The `JobMonitorMBean` interface has the exact suffix required by the JMX Standard MBean convention for class `JobMonitor`. Four methods belong to the management interface; `recordCompletedJob()` is not in the management interface, so it is not automatically exposed as an operation.

In the registry, management elements typically include:

| Java method | JMX element | Meaning |
| --- | --- | --- |
| `getProcessedCount()` | Attribute `ProcessedCount`, read-only | Task counter |
| `isEnabled()` and `setEnabled(boolean)` | Attribute `Enabled`, read/write | Change state |
| `reset()` | Operation `reset` | Reset counter |
| `recordCompletedJob()` | Not part of Standard MBean API | Only callable directly via the appropriate class |

Creating a shared interface for both access paths makes comparison possible without confusing missing-method errors with JMX configuration errors.

## 4. Configuring MBeanExporter and local MBeanProxyFactoryBean

The example below uses Spring Framework Java configuration, a single `MBeanServer`, and a single registration.

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JobJmxConfiguration {

    @Bean("jobMonitor")
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter jobMonitorExporter(
            JobMonitor jobMonitor,
            MBeanServer platformMBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.jobs:type=JobMonitor,name=primary",
                jobMonitor));
        return exporter;
    }

    @Bean("jobMonitorJmxProxy")
    public MBeanProxyFactoryBean jobMonitorJmxProxy(
            MBeanServer platformMBeanServer) throws Exception {
        MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
        proxy.setServer(platformMBeanServer);
        proxy.setObjectName(new ObjectName(
                "com.example.jobs:type=JobMonitor,name=primary"));
        proxy.setProxyInterface(JobMonitorMBean.class);
        return proxy;
    }
}
```

**Configuration explanation:**

1. `jobMonitor()` creates a real Spring bean with container lifecycle.
2. `platformMBeanServer()` supplies the current JVM's JMX server.
3. `jobMonitorExporter()` registers **that `JobMonitor` instance** in the server with a specific `ObjectName`.
4. `jobMonitorJmxProxy()` creates a `FactoryBean` producing a proxy object implementing `JobMonitorMBean`. It does not create another business `JobMonitor`.
5. When a method is called on the proxy, the Spring JMX access layer interacts with the MBean registered under the same `ObjectName`.

In real configurations, ensure the MBean has already been registered by the exporter before the proxy checks connectivity or is used. If initialization order causes errors, declare an explicit dependency with `@DependsOn("jobMonitorExporter")` on the proxy bean or design an appropriate lifecycle order.

If Spring Boot JMX auto-configuration or another exporter is already active, do not register the same `ObjectName` twice. Use only one registration mechanism per name.

## 5. Calling directly and calling via proxy in the same ApplicationContext

To see both references clearly, retrieve them by bean name.

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class LocalProxyDemo {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JobJmxConfiguration.class)) {

            JobMonitor direct = context.getBean(
                    "jobMonitor", JobMonitor.class);

            JobMonitorMBean viaJmx = context.getBean(
                    "jobMonitorJmxProxy", JobMonitorMBean.class);

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            System.out.println("Registered: " + server.isRegistered(name));

            direct.recordCompletedJob();
            direct.recordCompletedJob();

            System.out.println("Direct count: "
                    + direct.getProcessedCount());
            System.out.println("JMX proxy count: "
                    + viaJmx.getProcessedCount());

            viaJmx.reset();

            System.out.println("Direct count after proxy reset: "
                    + direct.getProcessedCount());
        }
    }
}
```

Expected output when the exporter registers the right instance:

```text
Registered: true
Direct count: 2
JMX proxy count: 2
Direct count after proxy reset: 0
```

Both references **observe the same target object** when the exporter registers `jobMonitor`. However:

- `direct` is a direct reference to the Spring bean.
- `viaJmx` is a reference to a client proxy accessing the object via `MBeanServer`.
- The two references are not necessarily the same Java object; comparing `direct == viaJmx` is not a valid check for sharing the same target.
- Only the methods belonging to `JobMonitorMBean` exist on the proxy; `recordCompletedJob()` is not in that interface.

Value consistency is guaranteed because both paths point to the same managed instance, **not** because the proxy keeps its own state memory and syncs with the bean.

## 6. Detailed behavioral comparison

| Criterion | Calling the Spring bean directly | Calling through a local MBean proxy |
| --- | --- | --- |
| How target is located | Bean reference from IoC container | `MBeanServerConnection` + `ObjectName` |
| Call interface | Methods visible on the injected Java type | Only methods in the JMX proxy interface |
| Call path | Java method call (possibly via Spring AOP) | Proxy → JMX attribute/operation → registered MBean |
| Requires MBean registration | No | Yes |
| Requires network? | No | No when connecting to a local server |
| JMX metadata | Not needed | Per the published MBean contract |
| Performance | Fewer intermediate layers in the normal case | Adds dispatch, metadata checks, and conversion |
| Error when name is missing | No concept of `ObjectName` | Can fail with MBean connection/access errors |
| Unexported methods | Still callable if Java type allows | Not callable through JMX interface |
| Suitable for | Internal business flows | Management interfaces, testing JMX path, MBean integration |

Key takeaway: **a local JMX proxy is not just another way to inject a Spring bean**. It is a client going through the JMX management API even within the same process.

## 7. ObjectName determines the target, not the Spring bean name

A Spring bean might be named `jobMonitor` or `primaryMonitor`, yet the JMX name registered by the exporter is an independent `ObjectName`:

```text
com.example.jobs:type=JobMonitor,name=primary
```

If there are two instances of the same kind:

```text
com.example.jobs:type=JobMonitor,name=primary
com.example.jobs:type=JobMonitor,name=secondary
```

a local proxy configured with `primary` will control the primary MBean, regardless of what the component injecting that proxy is named in the Spring context.

Conversely, injecting `JobMonitor` with `@Qualifier` retrieves the exact Spring bean by the name/qualifier known to the container. The two identity resolution mechanisms differ and have no mandatory automatic mapping between them.

If a proxy is configured with the wrong `ObjectName`, it can read or control a different MBean than intended, especially in JVMs containing multiple exporters and multiple contexts. Always verify the full `ObjectName`.

## 8. How are getters and setters translated by the proxy into JMX calls?

JavaBean methods in the management interface can be mapped to JMX attributes:

```java
int count = viaJmx.getProcessedCount();
boolean enabled = viaJmx.isEnabled();
viaJmx.setEnabled(false);
```

At the JMX layer, the corresponding meaning is typically:

```java
server.getAttribute(name, "ProcessedCount");
server.getAttribute(name, "Enabled");
server.setAttribute(
        name, new javax.management.Attribute("Enabled", false));
```

Operation:

```java
viaJmx.reset();
```

corresponds to an invoke operation such as:

```java
server.invoke(
        name, "reset", new Object[0], new String[0]);
```

Spring `MBeanProxyFactoryBean` is responsible for hiding those dispatch details behind a Java interface. Do not mistakenly believe it invokes Java methods on `JobMonitor` by reflecting directly on the Spring bean: the call must be resolved by the JMX server according to the registration and management metadata.

For methods with parameters, JMX uses a list of values and parameter type signatures. The Spring proxy can perform necessary client-side conversions. For custom types, Standard MBeans or MXBeans have different data requirements; the client proxy does not automatically make arbitrary Java DTOs transmissible over JMX.

## 9. Direct calls can still pass through Spring AOP

“Calling a Spring bean directly” does not always mean calling the raw underlying object with zero interceptors. If the bean is proxied by Spring AOP for transactions, security, or other aspects, the dependency received by the service may already be an **AOP proxy**.

Example:

```text
Service
  |
  | directBean.execute()
  v
Spring AOP proxy
  |
  | transaction/security/logging advice
  v
Target bean
```

Meanwhile, a local MBean proxy has its own path:

```text
Service
  |
  | jmxProxy.execute()
  v
JMX client proxy
  |
  v
MBeanServer
  |
  v
MBean registration / adapter
  |
  v
Target object
```

If `MBeanExporter` registered a Spring AOP proxy as the managed object, the JMX path may pass through AOP advice depending on how the exporter builds the adapter and what object was registered. If the exporter registered the raw target instance, advice may not apply in the same way.

Therefore, do not state categorically that a JMX proxy “always bypasses AOP” or “always applies all Spring advice”. Determine **which object** the exporter registered and test behavior under the running configuration.

For business flows requiring Spring transactions/security, inject services according to application architecture; do not use a JMX proxy as a substitute call path merely because it shares the same interface.

## 10. Lifecycle issues of proxy and exporter

The proxy may be created in the context, yet the corresponding MBean might not yet be registered or might be removed at runtime.

Scenarios to consider:

1. **Proxy initializes before exporter:** if the proxy checks connection or metadata early, it may not find the MBean. Use explicit dependencies.
2. **Exporter starts successfully but picks a different server:** proxy uses `MBeanServer` A while exporter uses B, so `ObjectName` may not exist on A.
3. **Context containing exporter closes:** the MBean is unregistered, while a proxy reference still exists in another component. Subsequent calls can fail.
4. **MBean is replaced under the same name:** the proxy may continue resolving the same `ObjectName` yet point to a different implementation, as long as the contract remains compatible.
5. **Custom server is released:** the proxy cannot assume the server remains active or the registration valid after the owner closes it.

A safe design pattern is keeping the exporter, server, and proxy with clear lifecycles in the same Spring context scope, and avoiding retaining a proxy beyond the lifetime of the server it accesses.

## 11. How the proxy verifies MBean attributes and operations

Before invoking, JMX tools or diagnostic code can query metadata:

```java
MBeanServer server = context.getBean(MBeanServer.class);

ObjectName name = new ObjectName(
        "com.example.jobs:type=JobMonitor,name=primary");

if (!server.isRegistered(name)) {
    throw new IllegalStateException("JobMonitor MBean is missing");
}

var info = server.getMBeanInfo(name);

for (var attribute : info.getAttributes()) {
    System.out.println("Attribute: " + attribute.getName());
}

for (var operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
```

This is how you verify the actual management interface. A proxy interface containing a method not exposed by the MBean may still be created successfully in some configurations, yet errors arise at invocation or metadata verification time.

Checking `isRegistered(name)` alone is not enough to prove contract compatibility. Another MBean may already have registered under the same `ObjectName`; inspect attributes, operations, and instance-identifying data.

## 12. Error categories and how to handle them

| Symptom | When calling directly | When using local JMX proxy |
| --- | --- | --- |
| Bean missing | Dependency injection error or `NoSuchBeanDefinitionException` | Proxy bean may exist while target MBean is missing |
| Wrong target | Wrong bean of same type injected | Proxy points to wrong `ObjectName` or server |
| Method missing | Java type/interface does not declare the method | Proxy interface or MBean management metadata does not expose it |
| Error inside business method | Java exception per AOP or target call path | Exception may be wrapped or translated by JMX/Spring access layer into an access exception |
| MBean unregistered | Does not affect direct bean if bean is still alive | Proxy calls can fail because target registration vanished |
| No JMX server | Direct call still works | Proxy requires a suitable `MBeanServerConnection` |
| JMX signature error | No separate layer for this | Operation signature/attribute mapping may not match |
| Wrong server across contexts | Depends on bean injection scope | Proxy and exporter may use two different servers |

You may encounter `InstanceNotFoundException`, `AttributeNotFoundException`, `ReflectionException`, or exceptions mapped/wrapped by the Spring JMX access layer. To diagnose, read the root cause, verify `ObjectName`, `MBeanInfo`, and registry state. Do not assume a client error proves an operation definitely did not execute: for operations with side effects, actual state may need to be re-read before retrying.

## 13. Performance advantages and limitations

A direct call via a Java reference usually has fewer steps than a call via a local JMX proxy. A JMX client proxy must build a management-layer request, resolve the method to an attribute/operation, and pass through `MBeanServer`.

Even within the same JVM and without networking, those steps still consume processing. Therefore:

- Use direct bean references for hot paths such as per-request processing, per-item batch loops, or very frequent calls.
- Use local JMX proxies when exercising the management path, reusing management contracts, or integrating with components that naturally work via JMX.
- Do not assume a JMX proxy is a good default for business-to-business dependencies inside a Spring application.
- Do not judge performance by intuition alone if the system has strict latency requirements; measure in actual runtime when needed.

A local proxy having no network does not mean zero overhead; conversely, that overhead does not mean every JMX call is unusably slow. Suitability depends on frequency and purpose.

## 14. Tests comparing both call paths

An integration test should verify shared target state yet distinct references.

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class LocalJmxProxyTest {

    @Test
    void localProxyAndSpringBeanReachSameMBeanState() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JobJmxConfiguration.class)) {

            JobMonitor direct = context.getBean(
                    "jobMonitor", JobMonitor.class);

            JobMonitorMBean proxy = context.getBean(
                    "jobMonitorJmxProxy", JobMonitorMBean.class);

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            assertTrue(server.isRegistered(name));

            direct.recordCompletedJob();
            direct.recordCompletedJob();

            assertEquals(2, direct.getProcessedCount());
            assertEquals(2, proxy.getProcessedCount());

            proxy.setEnabled(false);
            direct.recordCompletedJob();

            assertEquals(2, direct.getProcessedCount());
            assertFalse(direct.isEnabled());

            proxy.reset();
            assertEquals(0, direct.getProcessedCount());
        }
    }
}
```

The test compares behavior between the direct reference and JMX proxy via shared attribute values, rather than checking `==` identity. If multiple tests share the platform `MBeanServer` and the same `ObjectName` when running in parallel, `InstanceAlreadyExistsException` can occur. Use a dedicated test server or distinct names to isolate fixtures.

### Testing a wrong ObjectName

Create a proxy pointing to:

```text
com.example.jobs:type=JobMonitor,name=missing
```

then call `getProcessedCount()`. Verify the MBean access error or metadata check error, while noting the direct bean remains accessible as usual. That proves the JMX proxy requires the registry while direct calls do not.

## 15. Using MBeanServerConnection directly to understand the proxy

If you want to strip away Spring's convenience layer to observe the underlying mechanism:

```java
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = context.getBean(MBeanServer.class);
ObjectName name = new ObjectName(
        "com.example.jobs:type=JobMonitor,name=primary");

JobMonitorMBean jmxProxy = JMX.newMBeanProxy(
        server, name, JobMonitorMBean.class);

int count = jmxProxy.getProcessedCount();
jmxProxy.reset();
```

`JMX.newMBeanProxy(...)` belongs to the JDK and creates a proxy for a Standard MBean interface. `MBeanProxyFactoryBean` is a Spring utility that manages the proxy as a bean, configures server/name/interface, and integrates with dependency injection.

In a local environment, `MBeanServer` also implements `MBeanServerConnection`, so it can be passed directly to the proxy mechanism. In a remote environment, `MBeanServerConnection` is obtained from a `JMXConnector` after connecting to the server. Even with the same management interface, remote calls add networking, authentication, serialization, and timeouts.

## 16. When to choose each approach?

**Choose direct Spring bean injection when:**

- The caller is part of internal business processing flows.
- The full bean API is needed, not only the management interface.
- You want to leverage dependency injection, Spring AOP, and transaction boundaries per the application architecture.
- Methods are called frequently and unnecessary JMX dispatch should be avoided.
- There is no need to treat an `ObjectName` as the access contract.

**Choose a local MBean proxy when:**

- Building an admin tool or module based on a JMX contract.
- Wanting to verify the path through `MBeanServer` like JConsole/JMX clients.
- The client component should not depend on the target's implementation class.
- Needing to access an MBean registered by `ObjectName`, even without a direct Spring bean reference.
- Wanting to simulate a JMX client in the same JVM without a remote connector.

If the application already holds the bean directly and does not need the JMX path, adding a local proxy merely to call a business method usually complicates the architecture unnecessarily.

## 17. Common misconceptions

### “Same JVM means the proxy is the bean”

False. A local JMX proxy is a different client object that forwards calls through the registry. It can access the **same target**, yet is not the same reference or the same call path.

### “A JMX proxy can call any public method”

False. The proxy is constrained by the configured interface and the MBean contract published by the server. Methods present only on the implementation and not in the management interface are not automatically exposed to JMX.

### “Having a Spring bean means having an MBean”

False. The bean must be registered by an exporter or brought into the server by another JMX registration mechanism. `ApplicationContext` itself is not automatically a JMX registry.

### “Direct calls always bypass proxies”

False. A Spring dependency can be an AOP proxy when aspects are applied to the bean. Distinguish AOP proxies from JMX proxies by purpose and processing path.

### “Right ObjectName guarantees the right instance”

Not enough. Another exporter may have registered or replaced the MBean under that name. If critical, check identifying attributes, metadata, and registration ownership.

### “Local proxies do not need to care about lifecycle”

False. The MBean can be unregistered, the server can be released, and the context can close. A surviving proxy reference does not guarantee the JMX target remains accessible.

## 18. Hands-on exercises

**Exercise 1 — Two call paths.** Create `JobMonitor`, the exporter, and the local proxy as shown. Call `recordCompletedJob()` directly twice and then read `ProcessedCount` via the proxy. Reset via the proxy and verify the direct bean returns 0.

**Exercise 2 — Unexported method.** Try calling `recordCompletedJob()` on a variable of type `JobMonitorMBean`. Explain why the Java compiler forbids it even though the method exists on the implementation class, then cross-check with JMX `MBeanInfo`.

**Exercise 3 — Wrong target.** Configure the proxy with the wrong `ObjectName`, determine whether the error occurs at initialization or invocation in your configuration, and then fix the name. Verify the actual server rather than only changing the bean name.

**Exercise 4 — Two instances.** Register `primary` and `secondary` under two different names. Create two local JMX proxies sharing the same interface, each pointing to one `ObjectName`. Prove resetting `primary` does not alter `secondary`'s count.

**Exercise 5 — AOP.** Add a logging aspect around `reset()` and compare behavior between direct calls and the JMX proxy. Identify which object the exporter actually registered before explaining why advice was or was not applied.

## Conclusion

**Calling a Spring bean directly** follows a reference supplied by the IoC container and is the normal path for application logic. **A local MBean proxy** is a JMX client in the same JVM: it uses `MBeanServerConnection` and `ObjectName` to access a registered management interface. Both paths can reach the same target and state, yet differ in object resolution, permitted API, metadata, error handling, lifecycle, and overhead. Choose direct injection for internal business logic; use a local JMX proxy when you genuinely need to operate through a JMX contract.
