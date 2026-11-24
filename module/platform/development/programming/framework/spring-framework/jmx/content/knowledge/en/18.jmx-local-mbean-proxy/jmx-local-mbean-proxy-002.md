# ProxyInterface and Caller-Side Java Contract in Spring JMX Local MBean Proxy

## 1. Goal: calling an MBean like a Java interface

JMX provides `MBeanServerConnection` to read attributes and invoke operations on an MBean via an `ObjectName`. The raw API requires the caller to work with attribute names, parameter lists, type signatures, and JMX exceptions.

Direct read example:

```java
ObjectName name =
    new ObjectName("com.example.jobs:type=Worker,name=Primary");

boolean paused = (Boolean) mbeanServer.getAttribute(
    name, "Paused"
);

mbeanServer.invoke(
    name, "pause", new Object[0], new String[0]
);
```

This works, but makes calling code depend on strings and infrastructure APIs. Spring Framework supports **local MBean proxies**: define a **client-side Java interface** and then use `MBeanProxyFactoryBean` to map calls on that interface to JMX.

`proxyInterface` is the contract implemented by the proxy object so the caller can invoke `getQueueDepth()` or `pause()` like an ordinary Java method. It is **not an MBean name**, nor is it a switch that automatically exports a bean to JMX.

This lesson helps distinguish:

- The **server-side** management interface: the attributes/operations actually exported by the MBean.
- The **caller-side** `proxyInterface`: the Java calls accepted by the Spring proxy.
- `ObjectName`: identifies the target MBean within an `MBeanServer`.
- `MBeanServerConnection`: the JMX execution channel, which can be local or remote.
- How to verify both sides agree on names, parameter types, return types, and semantics.

## 2. Call flow through a local proxy

```text
Business/operations caller
         |
         v
WorkerManagementClient (Java interface)
         |
         v
Spring MBeanProxyFactoryBean
         |
         v
MBeanClientInterceptor
         |
         v
MBeanServerConnection (local server)
         |
         v
ObjectName -> exported MBean
         |
         v
Attribute / operation / exception
```

The proxy removes string mapping from most calling code, but does not bypass JMX. At method invocation time, the proxy must still look up the MBean name, translate getters/setters into attribute accesses, dispatch operations, and handle results or errors.

**Local** means the caller and `MBeanServer` run in the same JVM. It has no network overhead like remote JMX, but still incurs reflection, metadata, type-checking, and JMX handling overhead. Calls can also still fail if the MBean is not yet registered, has been unregistered, or has a different contract than the client interface.

## 3. Creating the server-side MBean

To illustrate, use a Java SE Standard MBean:

```java
package com.example.jobs.jmx;

public interface WorkerControlMBean {
    int getQueueDepth();
    boolean isPaused();
    void pause();
    void resume();
}
```

Implementation:

```java
package com.example.jobs.jmx;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class WorkerControl implements WorkerControlMBean {
    private final AtomicBoolean paused = new AtomicBoolean();
    private final AtomicInteger queued = new AtomicInteger(7);

    @Override
    public int getQueueDepth() {
        return queued.get();
    }

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void pause() {
        paused.set(true);
    }

    @Override
    public void resume() {
        paused.set(false);
    }
}
```

Registration:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName objectName = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

server.registerMBean(new WorkerControl(), objectName);
```

In this example, `WorkerControlMBean` is the standard JMX contract; public methods outside this interface do not appear automatically just because they exist on the implementation.

In a real Spring application, registration and unregistration should be managed by an exporter or infrastructure component with clear ownership, avoiding duplicate registration or leaving MBeans behind when the context closes.

## 4. Designing the caller-side proxyInterface

The client can use its own Java interface with a different name from the server interface, as long as the management signatures match the actual JMX surface:

```java
package com.example.jobs.client;

public interface WorkerManagementClient {
    int getQueueDepth();
    boolean isPaused();
    void pause();
    void resume();
}
```

This interface expresses what the caller is permitted to use. It does not need to extend `WorkerControlMBean`, nor does it need the `@ManagedResource` annotation.

Several benefits:

1. **Typed calls**: the compiler checks declared method names and Java types.
2. **Reduced coupling**: the caller does not have to construct `ObjectName`, `AttributeList`, or signature arrays on every call.
3. **Surface restriction**: only expose the methods the caller needs on the client interface.
4. **Easy adapter substitution**: the caller can use a fake implementation of the interface in unit tests.
5. **Versionable contract**: server-side changes must consider compatibility with already-deployed clients.

Even though the two interfaces may have identical signatures, they are **not automatically synchronized**. If the server renames `getQueueDepth()` to `getPendingCount()` while the client is not updated, client Java code still compiles, but the JMX call may fail at runtime.

## 5. Spring MBeanProxyFactoryBean with proxyInterface

Java configuration example:

```java
package com.example.jobs.config;

import com.example.jobs.client.WorkerManagementClient;
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class LocalJmxClientConfig {

    @Bean
    public MBeanServer localMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanProxyFactoryBean workerManagementClient(
            MBeanServer localMBeanServer) throws Exception {

        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
        factory.setServer(localMBeanServer);
        factory.setObjectName(new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        ));
        factory.setProxyInterface(WorkerManagementClient.class);
        return factory;
    }
}
```

`MBeanProxyFactoryBean` is a Spring `FactoryBean`. The Spring container initializes the factory and publishes a proxy object of type `WorkerManagementClient` for other beans to use:

```java
package com.example.jobs.application;

import com.example.jobs.client.WorkerManagementClient;
import org.springframework.stereotype.Component;

@Component
public class OperationsConsole {
    private final WorkerManagementClient worker;

    public OperationsConsole(WorkerManagementClient worker) {
        this.worker = worker;
    }

    public void inspectAndPause() {
        int pending = worker.getQueueDepth();

        if (pending > 0 && !worker.isPaused()) {
            worker.pause();
        }
    }
}
```

In this example, `new WorkerManagementClient()` is not called; Spring provides a dynamic proxy for that interface. The factory bean name in the container is `workerManagementClient`, whereas `ObjectName` identifies the target MBean as `com.example.jobs:type=Worker,name=Primary`. The two names serve two different registries.

Practical precondition: the MBean must be registered on the right `MBeanServer`. If `WorkerControl` is not yet registered when the client proxy is initialized or invoked, connection settings and lookup timing choices can lead to startup errors or runtime errors. Do not assume every proxy always waits until the first call to check the server.

## 6. Why must proxyInterface be configured?

`proxyInterface` tells Spring which **interface the proxy object must implement**. That interface provides the list of methods callable from Java code and the return types the caller expects.

If the interface is missing or mis-specified, the factory may fail to create a proxy of the right type, or the application cannot inject the bean by the expected interface. If the chosen interface contains a method that does not exist as an attribute/operation on the target MBean, the proxy may still be created, but calling it will fail at execution time.

Example of an incorrect interface:

```java
public interface IncorrectWorkerClient {
    String getQueueDepth(); // Server attribute is actually int.
    void resetEverything(); // MBean does not export this operation.
}
```

These methods look valid to the Java compiler, but are invalid against the **MBean's runtime contract**:

- `getQueueDepth` needs to read a `QueueDepth` attribute of a compatible type.
- `resetEverything` needs a JMX operation named `resetEverything` with a matching parameter signature, which does not exist.

The typical failure mode is an exception when the proxy performs the JMX invocation, not a compile-time error in the caller. Hence integration tests calling through the proxy itself are necessary.

## 7. Mapping getters, setters, and operations

A client interface can have:

```java
public interface CacheManagementClient {
    int getSize();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void clearExpired();
}
```

By JavaBeans conventions and the JMX model:

| Caller-side method | Required MBean element | Notes |
| --- | --- | --- |
| `getSize()` | Readable attribute `Size` | Return type must be compatible |
| `isEnabled()` | Readable boolean attribute `Enabled` | The `is...` form fits boolean |
| `setEnabled(boolean)` | Writable attribute `Enabled` | MBean must allow writes and accept a compatible type |
| `clearExpired()` | Operation `clearExpired` | Requires the exact operation signature |

Depending on the contract and the Spring MBean client interceptor, getter/setter methods map to JMX attributes, while other methods map to operations. Not every method starting with `get` automatically creates an attribute in the MBean if the server does not export that property.

If the MBean exposes `Size` as read-only, `setSize(int)` in the client interface cannot turn it into a writable attribute. `proxyInterface` **does not alter the server's permissions or capabilities**; it only describes the caller's expectations.

## 8. ObjectName and proxyInterface are two independent axes

A factory has two primary settings:

```java
factory.setObjectName(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
);
factory.setProxyInterface(WorkerManagementClient.class);
```

- `objectName` answers: **which MBean is being called?**
- `proxyInterface` answers: **which methods may the Java caller invoke?**

You can create two proxies with the same interface targeting two different MBeans:

```java
ObjectName primary = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

ObjectName secondary = new ObjectName(
    "com.example.jobs:type=Worker,name=Secondary"
);
```

Conversely, you can create different narrow client interfaces for the same MBean (for example, a read-only interface and an interface with management operations), but splitting interfaces **is not a JMX security mechanism**. A caller with access to `MBeanServerConnection` can still invoke other operations if not restricted at the server/connector level.

In systems with multiple JVMs, the same `ObjectName` can exist in each JVM. To call the right MBean, you also need to connect to the right `MBeanServer`.

## 9. How local proxies differ from remote proxies

`MBeanProxyFactoryBean` operates on top of an `MBeanServerConnection`. A local `MBeanServer` also implements this connection interface, so it can be used directly:

```java
factory.setServer(
    java.lang.management.ManagementFactory
        .getPlatformMBeanServer()
);
```

When using remote JMX, the client typically has a `JMXConnector` and obtains a connection:

```java
MBeanServerConnection connection =
    connector.getMBeanServerConnection();

factory.setServer(connection);
```

Here `connector` is a `JMXConnector` created, connected, and lifecycle-managed by infrastructure. With remote connections, authentication, SSL/TLS, dropped connections, reconnection, and closing the connector must be handled. With local connections, there is no network hop, though startup/shutdown ordering and MBean names still matter.

**Do not treat a Java interface proxy as a promise to handle all remote errors automatically.** If the connection is lost, Java methods can still throw runtime exceptions from Spring JMX or the connection infrastructure. Retries must suit the operation's semantics; repeating a side-effecting command can cause a state change twice.

## 10. Distinguishing MBeanProxyFactoryBean from JDK dynamic proxies for Spring AOP

A Spring application can contain two types of proxies with different goals:

1. **AOP proxy** wraps a service to add transactions, security, or caching.
2. **JMX client proxy** created by `MBeanProxyFactoryBean` forwards Java calls to JMX.

Both may use dynamic proxies and interfaces, but their mechanisms, call targets, and failure modes differ.

```text
JMX caller
   |
   +--> JMX proxy -> MBeanServer -> MBean
                                   |
                                   +--> May be a Spring-managed bean
                                        or management adapter
```

A server-side MBean can be exported from a Spring bean wrapped by an AOP proxy. In that case, you must ensure the JMX surface is determined properly via target/interface/assembler. Client-side `proxyInterface` does not fix a server-side AOP proxy hiding methods or annotations.

Keep two questions separate when diagnosing:

- Does the client have an interface compatible with `MBeanInfo`?
- Has the server actually registered the MBean with the right attributes/operations?

## 11. Designing small and stable client contracts

Do not use a large business interface as `proxyInterface` merely for injection convenience. For example:

```java
public interface OrderService {
    String placeOrder(String customerId);
    void cancelOrder(String orderId);
    long getPendingTotal();
    void pauseBackgroundWorker();
}
```

If the MBean server only manages workers, having a JMX client depend on `OrderService` makes callers expect business operations that are not exported.

Create a separate interface:

```java
public interface OrderWorkerAdmin {
    long getPendingTotal();
    boolean isPaused();
    void pause();
    void resume();
}
```

Benefits of a small contract:

- Avoids accidentally exposing business actions via management tooling.
- Reduces the number of methods that must remain compatible.
- Makes it easy to separate read-only attributes from side-effecting operations.
- Reduces dependence on domain types that are hard to map over JMX.
- Makes it easy to create fakes in unit tests and integration-test with `MBeanInfo`.

Avoid putting `ObjectName`, `MBeanInfo`, `AttributeList`, or `JMException` into an application-wide shared interface if callers do not need to know about JMX infrastructure. If a completely clean separation is needed, define a JMX-independent application port and build an adapter using the proxy to implement that port.

## 12. Data types and signatures must match

JMX supports simple types such as `boolean`, `int`, `long`, `String`, and certain complex types via MXBean/Open MBean mapping. A client Java interface should use types that the MBean actually exposes and the client can convert.

Example of an operation with parameters:

```java
public interface WorkerTuningClient {
    int getConcurrencyLimit();
    void setConcurrencyLimit(int value);
    void requestDrain(String reason);
}
```

The MBean side must have readable/writable `ConcurrencyLimit` to use the getter/setter, plus an operation `requestDrain` accepting `java.lang.String`.

If the server only has a no-argument `requestDrain()`, calling `requestDrain("maintenance")` is invalid. Java overloading and type promotion do not automatically apply over JMX the way ordinary local method calls do: JMX identifies operations by name and signature list.

When overloads exist, inspect `MBeanOperationInfo.getSignature()` to know the exact parameter types, parameter order, and return type.

## 13. Call errors and how to handle them

Several scenarios:

| Symptom | Common cause | Investigation direction |
| --- | --- | --- |
| Proxy bean cannot be created | Wrong `proxyInterface` kind or missing configuration | Inspect exception during factory creation |
| `InstanceNotFoundException` / wrapped exception | `ObjectName` not registered or already unregistered | `isRegistered`, exporter lifecycle |
| Attribute not found | Client getter does not match MBean attribute | `getMBeanInfo` and attribute name |
| Read-only attribute | Client tries to call setter, MBean disallows writes | `isWritable` in `MBeanInfo` |
| Operation does not exist | Name or signature differs | `getOperations()`, parameter signature |
| Wrong return type | `MBeanInfo` type differs from client interface | Standardize contract and JMX mapping |
| Proxy works then fails after restart | Server unregisters/re-registers on context change | Check `ObjectName` and call timing |
| Local test passes but prod remote fails | Contract is right, connection differs | Check connector, TLS, authentication |

Exceptions are wrapped or translated by the Spring JMX interceptor depending on the situation; do not rely on a single exception class for every failure. When logging, record the `ObjectName` and operation/attribute being called, while avoiding exposing sensitive parameters.

A management client should have an appropriate timeout/failure policy when using remote connections. Do not automatically retry state-changing operations without designing idempotency or a result-verification mechanism.

## 14. Reading MBeanInfo to inspect the actual interface

Before concluding the bug is in the proxy, query the server:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanInfo info = server.getMBeanInfo(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
);

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "attribute=%s type=%s readable=%s writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println("operation=" + operation.getName());
}
```

`server` must be the exact `MBeanServer` used by the exporter; if exported to a custom server, reading the platform server may not find it. `MBeanInfo` is the source of truth for the contract that a JMX client actually sees.

With `WorkerManagementClient`, expect:

- `QueueDepth`: readable integer.
- `Paused`: readable boolean.
- `pause`: no-argument operation.
- `resume`: no-argument operation.

Calls through the Spring proxy must also be tested, because matching metadata alone does not guarantee the server-side adapter executes the operation without throwing errors.

## 15. Testing a local proxy with JUnit and an isolated MBeanServer

Testing does not require a network port or JConsole. Use a dedicated test server and the same `ObjectName` on both sides:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

class WorkerLocalProxyTest {

    @Test
    void proxyCallsTheRegisteredMBean() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("jmx-test");

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        );

        try {
            server.registerMBean(new WorkerControl(), name);

            MBeanProxyFactoryBean factory =
                new MBeanProxyFactoryBean();

            factory.setServer(server);
            factory.setObjectName(name);
            factory.setProxyInterface(WorkerManagementClient.class);
            factory.afterPropertiesSet();

            WorkerManagementClient client =
                (WorkerManagementClient) factory.getObject();

            assertNotNull(client);
            assertEquals(7, client.getQueueDepth());
            assertFalse(client.isPaused());

            client.pause();
            assertTrue(client.isPaused());

            client.resume();
            assertFalse(client.isPaused());
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

This is a local JMX test through an actual proxy object, not a mock. The classes/interfaces must be placed in appropriate packages and source sets, with Spring JMX and JUnit dependencies present. Across different Spring versions, lifecycle callbacks or configuration APIs may vary; when running inside a container, `FactoryBean` is usually initialized by Spring.

To avoid cross-talk between parallel tests, create a dedicated server or use uniquely namespaced ObjectNames; always unregister test MBeans. Never wipe all MBeans from the platform server.

## 16. Unit testing the caller without an MBeanServer

The caller should depend on the interface rather than fetching an `MBeanServer` itself. Example:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OperationsConsoleTest {

    @Test
    void pausesOnlyWhenWorkExists() {
        class Fake implements WorkerManagementClient {
            int queued = 3;
            boolean paused = false;

            public int getQueueDepth() {
                return queued;
            }

            public boolean isPaused() {
                return paused;
            }

            public void pause() {
                paused = true;
            }

            public void resume() {
                paused = false;
            }
        }

        Fake fake = new Fake();
        OperationsConsole console = new OperationsConsole(fake);

        console.inspectAndPause();
        assertTrue(fake.paused);
    }
}
```

This unit test proves the caller's logic, but does not prove `proxyInterface` matches the MBean server. Therefore **both layers** should exist:

1. Caller tests with fakes to verify application decisions.
2. Integration tests against a real `MBeanServer` to verify JMX mapping and lifecycle.

## 17. Important limitations

### 17.1. Type-safe in Java does not mean contract-safe at runtime

The compiler only knows `WorkerManagementClient`. It cannot verify at build time that another JVM or another context exports an MBean with matching attributes/operations. Integration tests, runtime health checks, and version management are needed.

### 17.2. A client interface does not create permissions

A getter-only interface does not prevent a caller with a JMX connection from accessing other operations. Access rights are determined by the connector/server and infrastructure policies. Side-effecting operations must be protected and audited.

### 17.3. Local does not always mean fast

An MBean getter might query a database, hold locks, or make network calls; thus a local proxy can still block the caller. Design getters to return short snapshots, bound operations, and avoid placing risky calls on critical request paths.

### 17.4. Do not confuse the Spring bean name with the ObjectName

`workerManagementClient` is the proxy bean name in the Spring container; `com.example.jobs:type=Worker,name=Primary` is the MBean name. Configuring the right `proxyInterface` with the wrong `ObjectName` still fails.

### 17.5. Lifecycle must have an owner

When the context exporting the MBean closes, the MBean may be unregistered. A client proxy that outlives that point will not be able to continue making calls unless the MBean is re-registered under the matching name. Decide whether the caller should fail, wait for readiness, or reinitialize the proxy depending on the architecture.

## 18. Checklist before introducing a local MBean proxy into an application

- [ ] Accurately identified the `MBeanServer` used by the exporter.
- [ ] `ObjectName` has the right domain and key properties, with no unintended wildcards.
- [ ] `proxyInterface` is a sufficiently small Java interface suited to the caller.
- [ ] Getters/setters map accurately to JMX attributes and read/write flags.
- [ ] Operation names, parameter types, and return types match `MBeanInfo`.
- [ ] JMX client proxy is not confused with a business service's AOP proxy.
- [ ] Behavior is defined when the MBean is missing or unregistered.
- [ ] Side-effecting commands have appropriate validation/authorization/auditing.
- [ ] Caller unit tests and `MBeanServer` integration tests are in place.
- [ ] Tests clean up registrations/servers/connectors according to ownership.

## 19. Key takeaways

**`proxyInterface` is the caller-side Java contract**, while `ObjectName` selects the target MBean and `MBeanServerConnection` executes the JMX call. `MBeanProxyFactoryBean` lets callers write interface-based code, but does not alter the MBean's real capabilities, create security automatically, or eliminate runtime errors. For a reliable proxy, keep the interface small, cross-check directly against `MBeanInfo`, test getters/operations on a real server, and manage lifecycle explicitly.
