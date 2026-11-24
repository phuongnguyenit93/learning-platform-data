# Creating a Local Proxy to Read and Invoke MBeans in Spring Framework JMX

## Practice Objectives

After completing this lab, you will be able to:

- Understand how a **local JMX proxy** lets Java code call an MBean through a Java interface instead of manually writing \`MBeanServer.getAttribute(...)\` and \`invoke(...)\` for every call.
- Distinguish between **an MBean exported to an MBeanServer** and **a proxy created on the client side** to invoke that MBean.
- Use Spring Framework's \`MBeanProxyFactoryBean\` with an explicit \`ObjectName\`, \`MBeanServer\`, and management interface.
- Read a JMX attribute via a Java getter, invoke a JMX operation via a Java method, and understand how methods map to JMX.
- Configure everything with Java \`@Configuration\` and consume the proxy as a Spring bean via dependency injection.
- Verify behavior with JUnit 5, compare against the \`MBeanServer\` API, and handle \`InstanceNotFoundException\`, wrong ObjectNames, wrong interfaces, or wrong servers.
- Understand the scope of a local proxy and when you need a remote JMX client using \`MBeanServerConnection\`.

## 1. The Problem

Suppose an application has an MBean managing a queue with the following capabilities:

- Reading the number of pending jobs: \`PendingJobs\`.
- Checking whether the queue is paused: \`Paused\`.
- Invoking the \`pauseProcessing()\` operation.
- Invoking the \`resumeProcessing()\` operation.

Calling the JMX API directly:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=Queue,name=Primary"
);

long pending = (Long) server.getAttribute(
    name,
    "PendingJobs"
);

server.invoke(
    name,
    "pauseProcessing",
    new Object[0],
    new String[0]
);
\`\`\`

The inconvenience is that the client has to repeat the ObjectName, attribute and operation names, data types, and signatures. With many operations, code becomes verbose and prone to typos.

A local proxy lets you write:

\`\`\`java
long pending = queueJmxClient.getPendingJobs();
queueJmxClient.pauseProcessing();
\`\`\`

The proxy translates interface calls into interactions with the MBeanServer.

### Diagram

\`\`\`text
Business/JMX consumer in the same JVM
            |
            | Java interface call
            v
     Local MBean proxy
            |
            | getAttribute / invoke
            v
        MBeanServer
            |
            | ObjectName
            v
       QueueMonitor MBean
\`\`\`

**Important:** A proxy is not a copy of the MBean's state. It is an adapter for calls routed to the resource registered in the MBeanServer.

## 2. Two Directions of JMX Interaction

There are two independent directions:

**Export direction:** Spring bean → MBeanExporter → MBeanServer.

**Client direction:** Java interface → MBeanProxyFactoryBean → MBeanServer → MBean.

The same application can use both directions:

\`\`\`text
Spring ApplicationContext
    |
    +-- QueueMonitor bean
    |       |
    |       v
    |   MBeanExporter
    |       |
    |       v
    |   MBeanServer
    |       ^
    |       |
    |   MBean proxy
    |       ^
    |       |
    +-- QueuePollingService
\`\`\`

Because it is a **local proxy**, the MBean proxy in this lab is configured with an \`MBeanServer\` available inside the same JVM. Creating a proxy does not open a remote JMX endpoint.

## 3. Dependencies and Environment

Examples use:

- Java 17+.
- Spring Framework 6.x or a version compatible with your project.
- The \`spring-context\` module containing Spring JMX components and bean configuration.
- JUnit Jupiter if writing integration tests.
- The Java \`java.management\` module containing the JMX API.

Maven example for Spring Context, with versions managed via BOM or project dependency management:

\`\`\`xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
</dependency>

<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
\`\`\`

If the project does not use a BOM, declare compatible versions in dependency management. Do not mix arbitrary Spring module versions.

## 4. Define the Queue Management MBean

We create a Standard MBean so the example stays focused on the proxy.

### 4.1. Server-side management interface

\`\`\`java
package example.jmx;

public interface QueueMonitorMBean {

    long getPendingJobs();

    boolean isPaused();

    void pauseProcessing();

    void resumeProcessing();
}
\`\`\`

The name \`QueueMonitorMBean\` follows the Standard MBean convention because the implementation class will be named \`QueueMonitor\`.

### 4.2. MBean implementation

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public class QueueMonitor implements QueueMonitorMBean {

    private final AtomicLong pendingJobs = new AtomicLong(5);
    private final AtomicBoolean paused = new AtomicBoolean();

    @Override
    public long getPendingJobs() {
        return pendingJobs.get();
    }

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void pauseProcessing() {
        paused.set(true);
    }

    @Override
    public void resumeProcessing() {
        paused.set(false);
    }
}
\`\`\`

This is a Standard MBean: the management interface defines the exposed attributes and operations.

Mapping:

| Java method | JMX contract |
|---|---|
| \`getPendingJobs()\` | Attribute \`PendingJobs\`, type \`long\`, readable |
| \`isPaused()\` | Attribute \`Paused\`, type \`boolean\`, readable |
| \`pauseProcessing()\` | Operation \`pauseProcessing\` |
| \`resumeProcessing()\` | Operation \`resumeProcessing\` |

Do not use runtime bean class names or proxy names to form the ObjectName; we will specify a fixed management name.

## 5. Client-Side Management Interface

A local proxy needs an interface that the client side calls.

\`\`\`java
package example.jmx;

public interface QueueJmxClient {

    long getPendingJobs();

    boolean isPaused();

    void pauseProcessing();

    void resumeProcessing();
}
\`\`\`

This interface has the same management method signatures as the MBean contract.

Why might you separate \`QueueJmxClient\` from \`QueueMonitorMBean\`?

- Avoids coupling consumers to the server's implementation.
- Lets you maintain a purpose-built client interface.
- Illustrates that the proxy is an independent adapter, not an instance of \`QueueMonitor\`.

In simple cases, the client can also use \`QueueMonitorMBean\` directly as the proxy interface. Choose whichever level of decoupling you need, as long as the proxy methods map accurately to JMX attributes and operations.

## 6. Create a Local MBeanServer in Spring

To prevent integration tests from colliding with the JVM's shared platform MBeanServer, we use an isolated server:

\`\`\`java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxServerConfiguration {

    @Bean
    public MBeanServer lessonMBeanServer() {
        return MBeanServerFactory.createMBeanServer(
            "learning.local"
        );
    }
}
\`\`\`

\`MBeanServerFactory.createMBeanServer(...)\` creates an isolated JMX registry. Ensure both the exporter and the proxy receive **this exact server instance**.

If using the platform server, replace with:

\`\`\`java
@Bean
public MBeanServer lessonMBeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

For servers created via the factory, establish a release policy once the application/test finishes using them; never release the platform MBeanServer or shared servers you do not own.

## 7. Export QueueMonitor as an MBean

Configure \`MBeanExporter\` and an explicit ObjectName:

\`\`\`java
package example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class QueueExportConfiguration {

    public static final String QUEUE_OBJECT_NAME =
        "learning.jmx:type=Queue,name=Primary";

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanExporter queueMBeanExporter(
            @Qualifier("lessonMBeanServer") MBeanServer server,
            QueueMonitor queueMonitor) {

        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(server);

        exporter.setBeans(Map.of(
            QUEUE_OBJECT_NAME,
            queueMonitor
        ));

        return exporter;
    }
}
\`\`\`

Effects:

1. Creates \`QueueMonitor\`.
2. Creates a Spring-managed exporter.
3. Selects the custom MBeanServer.
4. Registers the MBean under a fixed ObjectName.
5. Manages unexport when the exporter closes.

If there are multiple \`MBeanServer\` beans, use \`@Qualifier\` so the wrong server is not injected.

**Note:** Do not enable another exporter that also registers \`QueueMonitor\` under the same ObjectName on the same server without clear ownership.

## 8. Create a Local Proxy with MBeanProxyFactoryBean

Spring Framework provides \`org.springframework.jmx.access.MBeanProxyFactoryBean\` to create a proxy implementing a management interface and routing calls to the MBean.

Example:

\`\`\`java
package example.jmx;

import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class QueueProxyConfiguration {

    @Bean(name = "queueJmxClient")
    public MBeanProxyFactoryBean queueJmxClientFactory(
            @Qualifier("lessonMBeanServer") MBeanServer server) {

        MBeanProxyFactoryBean factory =
                new MBeanProxyFactoryBean();

        factory.setServer(server);

        factory.setObjectName(
            QueueExportConfiguration.QUEUE_OBJECT_NAME
        );

        factory.setProxyInterface(QueueJmxClient.class);

        return factory;
    }
}
\`\`\`

Here \`MBeanProxyFactoryBean\` is a **FactoryBean**. When the bean named \`queueJmxClient\` is injected as type \`QueueJmxClient\`, Spring supplies the proxy object produced by the factory.

Key properties:

| Property | Value | Purpose |
|---|---|---|
| \`server\` | Local MBeanServer | Holds the target MBean |
| \`objectName\` | \`learning.jmx:type=Queue,name=Primary\` | Target MBean |
| \`proxyInterface\` | \`QueueJmxClient.class\` | Contract implemented by the proxy |

Do not confuse \`setServer\` with a hostname/port. This local proxy lab uses a Java \`MBeanServer\` directly, not a remote URL.

## 9. Combined Spring Configuration

You can combine the configurations into one context:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration
@Import({
    JmxServerConfiguration.class,
    QueueExportConfiguration.class,
    QueueProxyConfiguration.class
})
public class LocalJmxApplicationConfiguration {
}
\`\`\`

Application:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class LocalJmxProxyDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    LocalJmxApplicationConfiguration.class)) {

            QueueJmxClient client =
                context.getBean(QueueJmxClient.class);

            long pending = client.getPendingJobs();

            System.out.println(
                "Pending jobs = " + pending
            );

            System.out.println(
                "Initially paused = " + client.isPaused()
            );

            client.pauseProcessing();

            System.out.println(
                "After pause = " + client.isPaused()
            );

            client.resumeProcessing();

            System.out.println(
                "After resume = " + client.isPaused()
            );
        }
    }
}
\`\`\`

Expected output:

\`\`\`text
Pending jobs = 5
Initially paused = false
After pause = true
After resume = false
\`\`\`

These are Java calls routed through the proxy to the JMX MBean, not direct calls to \`QueueMonitor\`. The proxy uses the configured \`MBeanServer\` and \`ObjectName\` to map methods.

## 10. Comparing the Proxy to the MBeanServer API

To understand the mechanism clearly, compare:

**Direct JMX API approach:**

\`\`\`java
MBeanServer server =
    context.getBean("lessonMBeanServer", MBeanServer.class);

ObjectName name = new ObjectName(
    "learning.jmx:type=Queue,name=Primary"
);

long pending =
    (Long) server.getAttribute(name, "PendingJobs");

server.invoke(
    name,
    "pauseProcessing",
    new Object[0],
    new String[0]
);
\`\`\`

**Proxy approach:**

\`\`\`java
QueueJmxClient proxy =
    context.getBean(QueueJmxClient.class);

long pending = proxy.getPendingJobs();
proxy.pauseProcessing();
\`\`\`

The proxy makes client code easier to read and avoids repeating string names. However, the JMX operations must still exist with matching signatures in the MBeanServer.

The proxy will not automatically fix a wrong ObjectName or an unregistered MBean.

## 11. Why Must the Proxy Interface Match the Management Contract?

Suppose the client declares:

\`\`\`java
public interface QueueJmxClient {
    int getPendingJobs();
}
\`\`\`

While the MBean exposes \`PendingJobs\` with type \`long\`.

Even though the attribute name matches, the Java return type is incompatible with the value JMX returns, and proxy invocation can fail.

Similarly:

\`\`\`java
void pauseProcessing(boolean force);
\`\`\`

is not equivalent to the no-argument JMX operation \`pauseProcessing()\`.

Elements that must match:

1. Attribute/operation names.
2. Java return types.
3. Parameter types and order.
4. Primitive vs. wrapper semantics.
5. Read-only/writable behavior.
6. Contract and exceptions the client may receive.

Do not rely on an interface guessed from source code when the actual exported MBean has a different schema. Inspect \`MBeanInfo\` before finalizing the proxy interface.

## 12. Verifying Metadata with MBeanInfo

Using \`MBeanServer.getMBeanInfo\`:

\`\`\`java
MBeanServer server =
    context.getBean("lessonMBeanServer", MBeanServer.class);

ObjectName name = new ObjectName(
    QueueExportConfiguration.QUEUE_OBJECT_NAME
);

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, type=%s%n",
        attribute.getName(),
        attribute.getType()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s%n",
        operation.getName()
    );
}
\`\`\`

Expected:

\`\`\`text
Attribute: PendingJobs, type=long
Attribute: Paused, type=boolean
Operation: pauseProcessing
Operation: resumeProcessing
\`\`\`

The order of metadata lines is not guaranteed to be fixed; tests should match by name/signature rather than array index.

## 13. JUnit 5 Integration Test

A test verifying the full local proxy path:

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class LocalJmxProxyTest {

    @Test
    void readsAttributesAndInvokesOperations() throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    LocalJmxApplicationConfiguration.class)) {

            QueueJmxClient client =
                context.getBean(QueueJmxClient.class);

            MBeanServer server =
                context.getBean(
                    "lessonMBeanServer",
                    MBeanServer.class
                );

            ObjectName name = new ObjectName(
                "learning.jmx:type=Queue,name=Primary"
            );

            assertTrue(server.isRegistered(name));
            assertEquals(5L, client.getPendingJobs());
            assertFalse(client.isPaused());

            client.pauseProcessing();
            assertTrue(client.isPaused());
            assertEquals(
                true,
                server.getAttribute(name, "Paused")
            );

            client.resumeProcessing();
            assertFalse(client.isPaused());
            assertEquals(
                false,
                server.getAttribute(name, "Paused")
            );
        }
    }
}
\`\`\`

This test verifies:

- The context creates both the MBean and the proxy.
- The MBean is registered under the right ObjectName.
- The proxy reads attributes successfully.
- The proxy invokes operations that change state.
- The direct JMX API and the proxy observe the same state.

For actions with side effects, only test against test fixtures or controlled environments.

## 14. Testing Distinguishing the Right MBeanServer

If there are two MBeanServers:

\`\`\`java
MBeanServer first =
    MBeanServerFactory.createMBeanServer("first");

MBeanServer second =
    MBeanServerFactory.createMBeanServer("second");
\`\`\`

And the MBean is only registered in \`first\`, then a proxy configured with \`second\` cannot access the MBean under the same ObjectName unless there is a separate registration.

Common mistake:

\`\`\`java
proxyFactory.setServer(
    ManagementFactory.getPlatformMBeanServer()
);
\`\`\`

when the exporter uses a different custom MBeanServer.

When troubleshooting, compare:

\`\`\`java
first.isRegistered(name);
second.isRegistered(name);
\`\`\`

An ObjectName is meaningful only within the registry the client is querying. Do not change the ObjectName randomly before checking server identity.

## 15. Lifecycle: The Proxy Depends on Registration

A local proxy can exist as a Spring bean, yet calls will fail if the target MBean is unregistered.

Example:

\`\`\`text
Context start
   -> MBeanExporter registers MBean
   -> MBean proxy created
   -> proxy methods work
Context shutdown
   -> MBeanExporter unregisters MBean
   -> proxy can no longer access it
\`\`\`

Do not store a proxy in a static singleton outside the `ApplicationContext` lifecycle if the target MBean can be unregistered or recreated.

When using an MBeanServer created via factory, the application/test needs a release policy once consumers finish. The exporter unregistering an MBean does not automatically destroy the MBeanServer.

### Startup order issues

If the proxy is validated too early before the exporter registers the MBean, context initialization may fail depending on configuration and the proxy factory's checking behavior.

A predictable organization is creating the exporter/managed resource first, then using the proxy once the context has refreshed. When managing multiple contexts, design explicit initialization order or dependencies between components.

## 16. Common Errors

| Error | Possible Cause | How to Check |
|---|---|---|
| \`InstanceNotFoundException\` | ObjectName absent in selected server | \`isRegistered\`, server identity |
| Proxy bean cannot be injected | Wrong bean name, interface, or FactoryBean wiring | \`getBean(QueueJmxClient.class)\`, configuration |
| \`AttributeNotFoundException\` | Client getter does not match JMX attribute | \`getMBeanInfo\` |
| \`ReflectionException\` or operation mismatch | Different method name/signature | Operation signature metadata |
| \`ClassCastException\` | Getter Java return type mismatches JMX value | \`MBeanAttributeInfo.getType()\` |
| Startup fails with duplicate ObjectName | Two exporters registering the same name | Ownership and RegistrationPolicy |
| Proxy reads stale value | Client calling wrong MBean/server or target caches state | ObjectName, server, and resource identity |
| Operation called but state unchanged | Proxy called wrong target or method logic fails to update | \`getAttribute\`, business logic |
| MBean already unregistered | Context closed or exporter lifecycle changed | Check registration after close |
| Remote client cannot access | Local proxy does not create a remote connector | Use \`JMXConnector\` and proper security |
| Method with `@Transactional` not applied | JMX invocation bypasses Spring proxy or self-invocation | Check management facade/service call path |

## 17. Local Proxy vs. Spring AOP Proxy Are Not the Same Concept

Two kinds of proxies are commonly discussed in Spring projects:

**Spring AOP proxy:**

\`\`\`text
Caller -> AOP proxy -> advice -> target service
\`\`\`

Used for transactions, security, logging, caching, and other cross-cutting concerns.

**JMX local proxy:**

\`\`\`text
Caller -> MBean proxy -> MBeanServer -> MBean
\`\`\`

Used to turn Java interface calls into JMX attribute/operation accesses.

Both can coexist. An MBean facade can invoke a Spring service proxy internally. Never assume an AOP proxy is automatically a JMX proxy or vice versa.

If method-level security is enforced on a service, ensure the call path through JMX ultimately goes through the proper service proxy, rather than exporting a raw target that bypasses advice.

## 18. Local Proxy vs. Remote JMX Client

The local proxy in this lesson uses an \`MBeanServer\` in the same JVM:

\`\`\`java
factory.setServer(localMBeanServer);
\`\`\`

A remote JMX client requires a connector:

\`\`\`java
JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://example-host:9010/jmxrmi"
);

JMXConnector connector =
    JMXConnectorFactory.connect(url, environment);

MBeanServerConnection connection =
    connector.getMBeanServerConnection();
\`\`\`

Never use this snippet as an unprotected remote configuration. In production, connectors require authentication, TLS, network isolation, and least privilege.

If you want a Spring client proxy over a remote connection, you can use corresponding Spring JMX connector/client components such as \`MBeanClientInterceptor\` with \`MBeanServerConnection\` depending on your version and requirements. This lesson focuses on local proxies via \`MBeanProxyFactoryBean\`.

## 19. When Should You Use a Local Proxy?

A local proxy fits well when:

- A Java component in the same JVM wants to consume an MBean contract.
- You want to test an MBean's contract through a Java interface.
- You want to avoid repeating \`ObjectName\`, attribute name, and operation signature strings.
- You want to decouple consumer code from the MBean's implementation class.
- The project already uses a Spring application context and manages proxies as beans.

Consider using the MBeanServer API directly when:

- You need to discover MBeans dynamically via \`queryNames\`.
- You need to inspect \`MBeanInfo\` and work with detailed metadata.
- No stable interface exists.
- You need to process many MBeans with dynamically changing ObjectNames.

If logic simply needs to call a service inside the same JVM, **you do not necessarily need a JMX proxy**. Direct dependency injection is simpler with less overhead; a proxy is useful when you want clients to interact across the management boundary or need compatibility with a JMX contract.

## 20. Performance and Stability

Every proxy call still passes through JMX infrastructure. A getter may run heavy code, hold a lock, or query a database.

Principles:

- Read only the attributes you need.
- Do not poll too frequently.
- Avoid getters with I/O or expensive computation.
- Do not invoke operations with side effects from unbounded background tasks.
- Use appropriate timeouts/backoff when traversing a remote connector.
- Do not assume a local proxy is a direct Java field read.
- Test state and lifecycle when the target can be unregistered.

A JMX proxy improves the client's interface; it does not turn heavy operations into lightweight ones.

## 21. Practice Exercises

### Exercise 1 — Read an attribute

Create \`QueueJmxClient\` with \`getPendingJobs()\`. Export \`QueueMonitor\` and use the proxy to read the value 5. Compare with \`MBeanServer.getAttribute\`.

### Exercise 2 — Invoke an operation

Add \`pauseProcessing()\` and \`resumeProcessing()\`. Use the proxy to invoke each operation, then read \`isPaused()\` to prove state changed.

### Exercise 3 — Test a mismatched interface

Change \`getPendingJobs()\` in the client interface from \`long\` to \`int\`. Run the integration test and record the error or type mismatch behavior. Explain using \`MBeanInfo\`.

### Exercise 4 — Test the wrong server

Create two MBeanServers, export \`QueueMonitor\` into server A, and create the proxy pointing to server B. Identify why the proxy cannot reach the MBean.

### Exercise 5 — Test lifecycle

Create the context, call the proxy successfully, close the context, and verify the MBean is no longer registered. Explain why you should not keep using the proxy after the target MBean is unregistered.

## 22. Checklist Before Using MBeanProxyFactoryBean

1. Is the MBean already registered in the MBeanServer?
2. Does the ObjectName on the proxy match exactly?
3. Do the proxy and exporter use the same MBeanServer?
4. Does the proxy interface match method names?
5. Do return types and parameter signatures match?
6. Is the attribute getter readable?
7. Is the operation exposed and permitted to be invoked?
8. Are there duplicate exporters or ObjectName collisions?
9. Did you test \`MBeanInfo\` and \`getAttribute\` directly?
10. Did you test proxy invocation and actual state?
11. Is there lifecycle cleanup for the exporter/server?
12. Is the proxy used only within a scope where the MBean still exists?
13. If remote access is required, are connector/auth/TLS configured separately?

## 23. Core Takeaways

- **MBeanProxyFactoryBean** creates a Java interface proxy to call a JMX MBean using familiar methods.
- A proxy is not a new MBean and does not automatically create a remote endpoint.
- The client interface is a contract and must match JMX attribute/operation names and types.
- \`server\` and \`objectName\` specify precisely where and which object the proxy calls.
- A local JMX proxy differs from a Spring AOP proxy; each solves a different job.
- Use \`MBeanInfo\` and integration tests to verify the contract rather than guessing from Java code.
- Manage lifecycle carefully; a proxy cannot keep calling its target after the MBean is unregistered.

## References

- Spring Framework JMX Reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — MBeanProxyFactoryBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework API — MBeanClientInterceptor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanClientInterceptor.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
