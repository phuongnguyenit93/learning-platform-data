# Reading Attributes as Java Method Calls via a Local MBean Proxy in Spring Framework JMX

## 1. Learning objectives

In plain Java JMX, to retrieve an attribute's value we typically use \`MBeanServerConnection.getAttribute(ObjectName, String)\`. Spring Framework lets you create a **local proxy** for an MBean so application code calls a familiar Java method like \`monitor.getActiveJobs()\`, while behind the scenes the proxy translates that call into a JMX request to the MBeanServer.

Conceptual example:

\`\`\`java
int jobs = monitor.getActiveJobs();
\`\`\`

It looks like a call to a regular Java object, yet in reality it can pass through:

\`\`\`text
Java caller
    |
    v
MBean proxy: monitor.getActiveJobs()
    |
    v
MBeanServerConnection.getAttribute(objectName, "ActiveJobs")
    |
    v
MBeanServer → Registered MBean
    |
    v
Attribute value returned to Java caller
\`\`\`

After this lesson, you will be able to:

1. Distinguish calling a getter directly on a target object from calling a getter through a JMX proxy.
2. Explain the roles of \`MBeanProxyFactoryBean\` and \`MBeanClientInterceptor\`.
3. Define a Java management interface compatible with JMX attributes.
4. Configure a local proxy using the right \`MBeanServer\` and \`ObjectName\`.
5. Verify that calling \`getXxx()\` or \`isXxx()\` actually reads the \`Xxx\` attribute.
6. Understand how to handle types, exceptions, lifecycle, timeouts, and connections.
7. Write integration tests verifying both metadata and observed behavior through the proxy.

## 2. What is a local MBean proxy?

A local MBean proxy is a Java object created by Spring that can be injected into another bean under a **management interface**. When the caller invokes a method on the proxy, Spring translates the call into the JMX API.

Example:

\`\`\`java
public interface WorkerManagement {
    int getActiveJobs();
    boolean isEnabled();
}
\`\`\`

A consuming component:

\`\`\`java
@Service
public class WorkerDashboardService {
    private final WorkerManagement management;

    public WorkerDashboardService(WorkerManagement management) {
        this.management = management;
    }

    public int currentJobs() {
        return management.getActiveJobs();
    }
}
\`\`\`

If \`management\` is a JMX proxy, \`getActiveJobs()\` does not necessarily run on the same Java instance as business logic. The proxy calls into the MBeanServer using the configured ObjectName.

**“Local”** here refers to the connection mode: the proxy can directly use an \`MBeanServer\` in the same JVM. No RMI or network endpoint is required. Spring also supports JMX clients using remote connections under different configurations; the caller-side Java interface behavior can look similar, but transport errors and security differ greatly.

## 3. Distinguishing three ways to read the same metric

Suppose the MBean holds an \`ActiveJobs\` attribute.

### 3.1. Direct Java object read

\`\`\`java
int count = workerStatus.getActiveJobs();
\`\`\`

This is a direct call if \`workerStatus\` actually refers to the target object. It does not check whether the MBean is registered or the attribute is published via JMX.

### 3.2. Reading with MBeanServerConnection

\`\`\`java
Object value = connection.getAttribute(
    new ObjectName("training.spring:type=Worker,name=Primary"),
    "ActiveJobs");
int count = (Integer) value;
\`\`\`

This works at the JMX client layer and requires knowing the ObjectName, attribute name, and return type.

### 3.3. Reading through a Spring MBean proxy

\`\`\`java
int count = managementProxy.getActiveJobs();
\`\`\`

The Spring proxy uses the interface to expose a Java API, yet the call is still forwarded to \`MBeanServerConnection\`. Proxy consumers do not have to write \`getAttribute\` at every call site.

| Criterion | Direct Java object | MBeanServerConnection | Spring MBean proxy |
|---|---|---|---|
| Needs MBean registration? | No | Yes | Yes |
| Caller must know ObjectName? | No | Yes | No, if proxy config already holds it |
| Goes through JMX metadata/dispatch? | No | Yes | Yes |
| Checks actual management contract? | No | Yes | Yes |
| Return type at caller | Per Java method | Usually \`Object\` | Per Java interface |
| Can use a remote connection? | Not by default | Yes | Yes if client interceptor is configured |
| Error when MBean disappears | Not applicable | JMX exception | Usually forwarded/wrapped by Spring proxy |

Using a proxy does not mean reading an attribute is free or guaranteed to succeed. Lookup failures, access permissions, type mapping issues, or MBean unregistration can still occur.

## 4. Java getters become JMX attributes

In JMX, management interface methods such as:

\`\`\`java
int getActiveJobs();
boolean isEnabled();
String getVersion();
\`\`\`

are interpreted by property conventions:

\`\`\`text
getActiveJobs() → ActiveJobs attribute
isEnabled()    → Enabled attribute
getVersion()   → Version attribute
\`\`\`

These attributes must actually exist in the \`MBeanInfo\` of the registered MBean.

Example metadata:

\`\`\`text
ObjectName: training.spring:type=Worker,name=Primary

ActiveJobs:
  type=int
  readable=true
  writable=false

Enabled:
  type=boolean
  readable=true
  writable=true

Version:
  type=java.lang.String
  readable=true
  writable=false
\`\`\`

If the interface has \`getActiveJobs()\` while the MBean only exposes \`RunningTasks\`, the proxy cannot infer that the two names are synonymous. The naming contract must be kept in sync.

### 4.1. What is read-only?

If the MBean only exposes the getter \`getActiveJobs()\`, JMX clients can read it but cannot use \`setAttribute\` for \`ActiveJobs\`. A proxy with only a getter likewise gives callers read-only access. However, true read-only enforcement must be guaranteed by MBean metadata \`isWritable=false\`, not solely by one client's interface lacking a setter.

### 4.2. Boolean getters

\`boolean isEnabled()\` typically maps to \`Enabled\`. \`boolean getEnabled()\` can also be used. If choosing \`isXxx()\`, use primitive \`boolean\` and stay consistent with JavaBeans conventions. When mismatches happen, inspect \`MBeanAttributeInfo\` to see the actual name/type.

## 5. Complete example: Standard MBean and Spring local proxy

We build an MBean with two attributes and a corresponding interface.

### 5.1. Management interface

File \`WorkerStatusMBean.java\`:

\`\`\`java
package example.jmx;

public interface WorkerStatusMBean {
    int getActiveJobs();
    boolean isEnabled();
}
\`\`\`

### 5.2. Implementation

File \`WorkerStatus.java\`:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class WorkerStatus implements WorkerStatusMBean {
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

    public void jobStarted() {
        if (enabled) {
            activeJobs.incrementAndGet();
        }
    }

    public void jobFinished() {
        activeJobs.updateAndGet(previous ->
            Math.max(0, previous - 1));
    }
}
\`\`\`

This is a Standard MBean: the class name \`WorkerStatus\` and interface \`WorkerStatusMBean\` follow JMX naming conventions. Since the interface only has getters, both attributes are read-only over JMX.

### 5.3. Spring configuration creating server, MBean, and proxy

File \`JmxConfig.java\`:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

import java.util.Map;

@Configuration
public class JmxConfig {

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public WorkerStatus workerStatus() {
        return new WorkerStatus();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            WorkerStatus workerStatus) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(
            "example.jmx:type=WorkerStatus,name=Primary",
            workerStatus));
        return exporter;
    }

    @Bean
    public MBeanProxyFactoryBean workerStatusProxy(
            MBeanServer mbeanServer) throws Exception {

        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(mbeanServer);
        factory.setObjectName(new ObjectName(
            "example.jmx:type=WorkerStatus,name=Primary"));
        factory.setProxyInterface(WorkerStatusMBean.class);
        return factory;
    }
}
\`\`\`

Spring \`MBeanProxyFactoryBean\` creates a Java proxy based on the management interface and ObjectName. Typically, client beans are injected with the **type of the FactoryBean's product**, meaning \`WorkerStatusMBean\`, not the \`MBeanProxyFactoryBean\` instance itself.

If the context already has the \`workerStatus()\` bean also implementing \`WorkerStatusMBean\`, injecting \`WorkerStatusMBean\` by type may become ambiguous because both target and proxy exist. Use \`@Qualifier("workerStatusProxy")\` or an explicit bean name to ensure receiving the proxy.

### 5.4. Consumer program

\`\`\`java
package example.jmx;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JmxConfig.class)) {

            WorkerStatus target =
                context.getBean(WorkerStatus.class);

            WorkerStatusMBean proxy =
                context.getBean(
                    "workerStatusProxy",
                    WorkerStatusMBean.class);

            System.out.println(
                "Before: " + proxy.getActiveJobs()); // 0

            target.jobStarted();
            target.jobStarted();

            System.out.println(
                "After: " + proxy.getActiveJobs()); // 2
            System.out.println(
                "Enabled: " + proxy.isEnabled());  // true
        }
    }
}
\`\`\`

In the example, \`proxy.getActiveJobs()\` is a Java API call, yet the value travels through the MBeanServer. \`target.jobStarted()\` is internal logic used to change state; the management client only needs getters.

**Lifecycle limitation:** the proxy requires the MBean to be registered before calls are made. If the server does not yet hold the ObjectName, the proxy getter fails even though the Java interface and proxy bean were created successfully.

## 6. Why should you not treat the proxy as the target object?

The two objects have different roles:

\`\`\`text
WorkerStatus target:
    implements business/management methods

WorkerStatusMBean proxy:
    implements interface for JMX client,
    forwards calls through MBeanServer
\`\`\`

If the caller receives the target directly, \`getActiveJobs()\` runs straight on the Java object and can succeed even if the exporter is not working. If it receives the proxy, the call depends on MBean registration. This is useful when you want to test the JMX contract or decouple consumers from the implementation.

A common mistake in Spring is injecting by type \`WorkerStatusMBean\` without a qualifier and accidentally receiving the target. In that case, a “proxy works” test yields a false conclusion.

### 6.1. How to verify you are using the proxy

In a test environment:

\`\`\`java
System.out.println(proxy.getClass().getName());
System.out.println(target.getClass().getName());
System.out.println(proxy == target); // false
\`\`\`

The proxy class name is an implementation detail and should not be hard-coded. You can assert that the proxy instance differs from the target and read JMX metadata to prove data comes from the server.

## 7. MBeanProxyFactoryBean and MBeanClientInterceptor

In Spring JMX:

- \`MBeanProxyFactoryBean\` provides a client proxy bean with a management interface.
- \`MBeanClientInterceptor\` handles invocations from the proxy and communicates with \`MBeanServerConnection\`.
- \`MBeanExporter\` is responsible for registering the server-side MBean.
- \`MBeanServer\` receives and dispatches attribute read or operation invocation requests.

\`\`\`text
Spring caller
    |
    v
MBeanProxyFactoryBean-created proxy
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
Managed MBean
\`\`\`

Do not configure \`MBeanExporter\` in place of \`MBeanProxyFactoryBean\`: the exporter and proxy serve opposite sides of the JMX connection. The exporter is server-side; the proxy is client-side.

### 7.1. Local vs remote

When \`setServer(mbeanServer)\` provides an \`MBeanServerConnection\` in the same JVM, the proxy reads directly through the local JMX server. If instead of injecting a server you use \`JMXServiceURL\` with \`JMXConnector\` in the Spring-supported way, a remote MBeanServer can be accessed.

The remote path adds authentication, networking, TLS, RMI, and timeouts; do not assume it has the same availability as local calls.

## 8. Return values and type mapping

The Java caller expects the types declared on the management interface:

\`\`\`java
int getActiveJobs();
boolean isEnabled();
\`\`\`

However, the underlying JMX API returns \`Object\`. The Spring proxy converts the result to the method's return type. Therefore, metadata and return types must be compatible.

Cases requiring caution:

- MBean returns \`Integer\` for an \`int\` attribute — normal boxing/unboxing.
- MBean returns \`null\` for a primitive \`int\` getter — cannot unbox to \`int\`.
- MBean exposes \`String\` while interface declares \`int\` — type mismatch.
- MXBean returns \`CompositeData\` for a complex type — requires appropriate proxy/interface and Open Types mapping.
- Attribute renamed after an exporter upgrade — proxy getter can no longer find the expected name.

Do not confuse a Spring JMX proxy with a REST client capable of arbitrarily converting any data type. The JMX contract must remain explicit and tested.

## 9. Checking metadata before calling the proxy

Before expecting \`getActiveJobs()\` to work, check the MBean:

\`\`\`java
import javax.management.*;
import java.util.Arrays;

ObjectName objectName = new ObjectName(
    "example.jmx:type=WorkerStatus,name=Primary");

MBeanInfo info = server.getMBeanInfo(objectName);

MBeanAttributeInfo attribute =
    Arrays.stream(info.getAttributes())
        .filter(a -> a.getName().equals("ActiveJobs"))
        .findFirst()
        .orElseThrow();

System.out.println(attribute.getType());       // int
System.out.println(attribute.isReadable());    // true
System.out.println(attribute.isWritable());    // false
\`\`\`

If \`ActiveJobs\` is absent from \`MBeanInfo\`, the issue may lie in the Standard MBean interface, annotation assembler, ObjectName, or exporter configuration rather than in the caller's Java getter.

## 10. Reading an attribute with \`isEnabled()\`

A management interface can declare:

\`\`\`java
public interface FeatureManagement {
    boolean isEnabled();
}
\`\`\`

When the corresponding MBean is exported with the right contract, the Spring proxy reads the \`Enabled\` attribute.

Verify the name and \`isIs()\`/boolean semantics in metadata, especially when using MXBeans or annotation-exported beans with a custom metadata assembler. Avoid placing both \`getEnabled()\` and \`isEnabled()\` inconsistently on the same interface.

A client can write:

\`\`\`java
boolean active = featureManagement.isEnabled();
\`\`\`

There is no need to construct \`new ObjectName(...)\` in every business caller, because the proxy is configured centrally.

## 11. Reading attributes from a Spring-exported bean instead of a Standard MBean

A proxy can also work with an MBean exported via \`@ManagedResource\` and \`@ManagedAttribute\`, as long as the client interface matches the **actually published JMX interface**.

Bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "example.jmx:type=QueueView,name=Orders")
public class QueueView {
    private volatile int pendingCount;

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }
}
\`\`\`

Client interface:

\`\`\`java
public interface QueueViewManagement {
    int getPendingCount();
}
\`\`\`

Proxy configuration:

\`\`\`java
@Bean
public MBeanProxyFactoryBean queueViewProxy(MBeanServer server)
        throws Exception {
    MBeanProxyFactoryBean factory =
        new MBeanProxyFactoryBean();
    factory.setServer(server);
    factory.setObjectName(new ObjectName(
        "example.jmx:type=QueueView,name=Orders"));
    factory.setProxyInterface(QueueViewManagement.class);
    return factory;
}
\`\`\`

Note: \`QueueView\` must actually be registered by \`MBeanExporter\` or annotation export infrastructure. Having \`@ManagedResource\` on the class alone is not enough. If the Spring application already uses \`@EnableMBeanExport\`, inspect the framework-created exporter and avoid adding another exporter registering the same ObjectName.

## 12. Common errors when a proxy getter fails

### 12.1. \`InstanceNotFoundException\` / MBean not registered

If the MBean has been unregistered or the proxy points to the wrong ObjectName, the call cannot reach the target.

How to handle:

1. Check \`server.isRegistered(name)\`.
2. Query names by domain.
3. Verify the exporter ran.
4. Check the ApplicationContext or plugin lifecycle.
5. Check whether the proxy and exporter use the same \`MBeanServer\`.

### 12.2. \`AttributeNotFoundException\`

The proxy looks for \`ActiveJobs\`, but the MBean does not expose that attribute or uses a different name.

How to handle: inspect \`getMBeanInfo(name).getAttributes()\`, check getter naming in the interface and metadata assembler.

### 12.3. Type mismatch

The interface getter declares \`int\`, while the JMX attribute actually has type \`String\` or \`CompositeData\`. Keep contract types consistent or use an interface properly designed for MXBean/Open Types.

### 12.4. Wrong bean injected instead of proxy

If the context has both the \`WorkerStatus\` target and the \`MBeanProxyFactoryBean\` product both implementing \`WorkerStatusMBean\`, injection by type may pick the wrong one or cause ambiguity. Use a clear qualifier or bean name.

### 12.5. Wrong MBeanServer

\`MBeanExporter\` uses a newly created custom server, while the MBean proxy is injected with the platform server. The client sees the MBean as nonexistent.

How to handle: configure both the exporter and proxy to receive the **same MBeanServer reference**.

### 12.6. Permission or remote transport errors

With remote JMX, a getter can also fail due to authentication, authorization, TLS, network, or lost connector. Do not assume identical Java method signatures guarantee identical exception semantics. Inspect the error chain and determine whether the failure happened before or after sending the request.

## 13. Testing the proxy as a JMX client

Unit tests calling \`target.getActiveJobs()\` directly do not verify proxy routing. Tests must boot the Spring context, retrieve the proxy bean by exact name, and read through JMX.

JUnit 5 example:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class LocalProxyTest {
    @Test
    void proxyReadsAttributeViaMBeanServer() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JmxConfig.class)) {

            MBeanServer server =
                context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                "example.jmx:type=WorkerStatus,name=Primary");

            assertTrue(server.isRegistered(name));

            WorkerStatus target =
                context.getBean(WorkerStatus.class);

            WorkerStatusMBean proxy =
                context.getBean(
                    "workerStatusProxy",
                    WorkerStatusMBean.class);

            assertNotSame(target, proxy);

            assertEquals(0, proxy.getActiveJobs());

            target.jobStarted();
            assertEquals(1, proxy.getActiveJobs());

            assertEquals(
                server.getAttribute(name, "ActiveJobs"),
                proxy.getActiveJobs());
        }
    }
}
\`\`\`

This test proves the value from the proxy matches the value on the MBeanServer. If stronger proof is needed that the proxy actually uses JMX, you can temporarily unregister the MBean in an isolated test fixture and verify the proxy getter fails, then clean up. Never perform destructive unregistration on a shared production MBeanServer.

### 13.1. Testing read-only

A client interface without a setter is not enough to conclude the MBean is read-only. Check:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);
MBeanAttributeInfo active =
    java.util.Arrays.stream(info.getAttributes())
        .filter(a -> a.getName().equals("ActiveJobs"))
        .findFirst()
        .orElseThrow();

assertTrue(active.isReadable());
assertFalse(active.isWritable());
\`\`\`

If an exporter changes metadata to allow writes, another client can still call \`setAttribute\` even if the current proxy only has a getter. Hence the server-side contract must be checked.

## 14. Proxies and multiple ApplicationContexts

In multi-context applications, the exporter and client proxy may live in different places:

\`\`\`text
Root context:
  MBeanServer
  MBeanExporter
  WorkerStatus MBean

Child context:
  MBeanProxyFactoryBean
  DashboardController
\`\`\`

The child can inject the server bean from the parent if the context hierarchy permits. Ensure the child proxy references the exact ObjectName registered by the root exporter.

Conversely, if the exporter lives in a child context and the proxy lives in root, root does not automatically look up child beans. In that case, explicit wiring or restructuring ownership is required.

If a plugin context closes and the MBean is unregistered, a surviving proxy in another context does not automatically recreate the MBean. Subsequent calls may fail. Consumers should handle lifecycle and discovery appropriately.

## 15. Relationship to Spring AOP proxies

A local JMX proxy is a **client proxy** pointing toward an MBeanServer; whereas a Spring AOP proxy is usually a proxy around a business bean to apply transactions, caching, security, or tracing. Both layers can coexist, but serve different roles.

\`\`\`text
Client bean
    |
    v
JMX client proxy
    |
    v
MBeanServer
    |
    v
Exported MBean adapter
    |
    v
Spring business bean (may be an AOP proxy)
    |
    v
Target logic
\`\`\`

Do not confuse \`MBeanProxyFactoryBean\` with \`@Transactional\` configuration. A JMX client proxy does not automatically guarantee target transactions; transactions depend on the bean and whether the call passes through AOP advice properly.

If a getter proxy stops working after enabling AOP, check both sides:

1. Does the client proxy have the right interface/ObjectName/server?
2. Does the MBean exporter still expose the attribute?
3. Did the AOP proxy alter method visibility/metadata?
4. Does the actual \`MBeanInfo\` still contain that attribute?

## 16. When to use a local proxy?

**Consider using it** when:

- A component wants to read MBean attributes through a strongly typed Java interface.
- You need consumers decoupled from the implementation, or even lacking the target class on the classpath.
- The same client contract may be used locally today and remotely by configuration later.
- You want to test the real management path, not just direct Java object calls.

**Not strictly necessary** when:

- The same service already has a suitable direct Java API and no JMX boundary is needed.
- You only need frequent metric reads and can obtain them directly from a metrics API.
- Dispatch overhead, JMX errors, and configuration complexity bring no benefit.
- A proxy is used as a way to bypass access controls or business service boundaries.

For high-throughput monitoring, dedicated metrics tools may be more appropriate than reading JMX attributes on every business request.

## 17. Hands-on exercises

### Exercise A — Reading an attribute through two paths

Run the \`WorkerStatus\` example. Read \`ActiveJobs\` via \`server.getAttribute\` and \`proxy.getActiveJobs()\`. Prove the results are equal and explain how the two APIs differ.

### Exercise B — Setting a wrong ObjectName

Change the proxy ObjectName to \`example.jmx:type=WorkerStatus,name=Missing\`, keeping the exporter unchanged. Call the getter and observe the error. Restore the right ObjectName and verify again.

### Exercise C — Changing the getter name

Rename \`getActiveJobs()\` in the client interface to \`getRunningJobs()\` without changing the MBean. Observe the error and determine the actual attribute via \`MBeanInfo\`.

### Exercise D — Read-only metadata

Use \`MBeanAttributeInfo\` to confirm \`ActiveJobs\` is read-only. Attempt to set the attribute from \`MBeanServer\` in an isolated test and record the appropriate error.

### Exercise E — Two ApplicationContexts

Place the exporter/server in a root context and the proxy in a child context. Verify the proxy can call the getter. After closing root, verify calls from the child proxy fail or follow the lifecycle contract.

### Exercise F — Annotation-based MBean

Replace the Standard MBean with \`@ManagedResource\` and \`@ManagedAttribute\` using an equivalent ObjectName. Configure annotation export and check that the client proxy still reads properly when \`MBeanInfo\` exposes \`ActiveJobs\`.

## 18. Self-check questions

1. How do \`MBeanProxyFactoryBean\` and \`MBeanExporter\` differ in responsibility?
2. Which JMX API does \`getActiveJobs()\` on a client proxy map to?
3. Why does a direct Java getter succeeding not prove an MBean proxy works?
4. What is the attribute name from \`isEnabled()\` usually?
5. Why must the proxy and exporter use the same \`MBeanServer\`?
6. What does \`MBeanInfo\` help verify before calling a proxy?
7. If the MBean is unregistered, does the proxy continue working normally?
8. Why can injecting \`WorkerStatusMBean\` by type suffer from ambiguity?
9. How does a local JMX proxy differ from an AOP transaction proxy?
10. Why must return types and JMX metadata be compatible?

## 19. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`MBeanProxyFactoryBean\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework API — \`MBeanClientInterceptor\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanClientInterceptor.html
- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html

**Key takeaway:** A Spring local MBean proxy turns a getter call such as \`getActiveJobs()\` into a JMX attribute read. The proxy interface must match MBean metadata, and the proxy and exporter must target the same MBeanServer and ObjectName. Proxies make client code easier to use, but do not eliminate the need to manage registration, JMX errors, and management contract compatibility.
