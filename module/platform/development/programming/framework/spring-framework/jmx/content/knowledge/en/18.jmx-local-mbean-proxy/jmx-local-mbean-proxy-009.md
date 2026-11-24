# Testing a Local MBean Proxy with a Fake or Real MBeanServer

## Objectives

This lesson belongs to **Spring Framework JMX → Local MBean Proxy**, focusing on how to test a Spring-created client proxy that accesses an MBean in the same JVM. After this lesson, you will be able to:

- Understand how `MBeanProxyFactoryBean` creates a proxy based on a management interface and `ObjectName`.
- Distinguish a mock `MBeanServerConnection` from a real `MBeanServer` in testing.
- Write tests that read attributes, invoke operations, verify parameter signatures, and check JMX error propagation.
- Create an isolated `MBeanServer`, register a Standard MBean, run end-to-end tests, and clean up safely.
- Recognize risks when using the platform server, unstable naming, parallel test execution, and false assumptions about proxy calls.

## 1. What is a local MBean proxy?

JMX operates through an `MBeanServer`. A client can call JMX methods directly:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

Object count = server.getAttribute(name, "PendingCount");

server.invoke(
    name, "resetStatistics",
    new Object[0], new String[0]
);
```

Spring lets you use a **Java interface-typed proxy** so client code does not need to repeat `getAttribute`, `setAttribute`, and `invoke` calls.

```text
Spring client
  |
  v
QueueAdminMBean interface
  |
  v
MBeanProxyFactoryBean
  |
  v
MBeanServerConnection (local)
  |
  v
MBeanServer -> MBean registered under ObjectName
```

Developers can write:

```java
QueueAdminMBean proxy = ...;
int count = proxy.getPendingCount();
proxy.resetStatistics();
```

The proxy translates interface calls into the corresponding JMX operations. Because there is an extra mapping layer from interface → JMX metadata → MBean implementation, tests that only call the target class directly are **not enough** to verify the proxy works properly.

## 2. Components to verify

| Component | Role in testing |
| --- | --- |
| `MBeanProxyFactoryBean` | Creates the proxy and holds `ObjectName`, management interface, and connection config |
| `MBeanServerConnection` | Client API used to fetch attributes and invoke operations |
| `MBeanServer` | Real JMX registry; also implements `MBeanServerConnection` |
| `ObjectName` | Identifies the MBean the proxy must access |
| Management interface | Client-side Java contract |
| MBean implementation | Actual behavior returning values and executing operations |
| `MBeanInfo` | Metadata showing published attributes/operations |

Key point: **a local proxy still goes through the JMX API**, even with no network hop. It is not a Spring AOP proxy calling the target directly in every case.

## 3. Preparing the management interface and Standard MBean

For the demo, define a management interface:

```java
package com.example.jmx;

public interface QueueAdminMBean {
    int getPendingCount();
    boolean isPaused();
    void setPaused(boolean paused);
    void resetStatistics();
}
```

Create the implementation:

```java
package com.example.jmx;

public class QueueAdmin implements QueueAdminMBean {
    private int pendingCount = 17;
    private boolean paused;

    @Override
    public synchronized int getPendingCount() {
        return pendingCount;
    }

    @Override
    public synchronized boolean isPaused() {
        return paused;
    }

    @Override
    public synchronized void setPaused(boolean paused) {
        this.paused = paused;
    }

    @Override
    public synchronized void resetStatistics() {
        pendingCount = 0;
    }
}
```

`QueueAdmin` implements `QueueAdminMBean`, so it can be registered under the JMX Standard MBean convention. `getPendingCount` and the `isPaused`/`setPaused` pair are represented as attributes, while `resetStatistics` is an operation.

Example ObjectName:

```text
com.example.orders:type=Queue,name=Payment
```

In tests, do not treat class name and ObjectName as equivalent: the **management name** registered by the server may be completely different from the Spring bean name or class name.

## 4. Creating a proxy with MBeanProxyFactoryBean

An illustrative Spring Java configuration:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class QueueClientJmxConfiguration {

    @Bean
    public MBeanProxyFactoryBean queueProxyFactory(
            MBeanServer mbeanServer) throws Exception {

        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
        factory.setServer(mbeanServer);
        factory.setObjectName(
            new ObjectName("com.example.orders:type=Queue,name=Payment")
        );
        factory.setProxyInterface(QueueAdminMBean.class);
        return factory;
    }
}
```

Properties to verify:

- `server`: the `MBeanServerConnection` object the proxy talks to. For local proxies, a real `MBeanServer` can be used.
- `objectName`: the specific MBean being invoked.
- `proxyInterface`: the management interface the application sees.
- Other settings, if used, must match the Spring version and factory initialization mechanism.

When the factory bean is managed by Spring, the `FactoryBean` lifecycle supplies a proxy implementing the specified interface. If created manually in a unit test, the corresponding initialization step must be called before calling `getObject()`.

## 5. Testing strategy: mock or real server?

The two testing levels complement each other:

| Aspect | Mock `MBeanServerConnection` | Real `MBeanServer` |
| --- | --- | --- |
| Cost | Lightweight, no MBean registration | Requires registry setup/teardown |
| Call mapping check | Good, verifies `getAttribute`/`invoke` | Good, uses real JMX metadata |
| Standard MBean compliance check | No | Yes |
| Real `ObjectName` registration check | No | Yes |
| Connector/JMX API error check | Can be simulated | Can observe real errors |
| JavaBeans attribute mapping check | Requires appropriate stubs | More natural, exact protocol |
| Risk of affecting other tests | Low | Low if creating a dedicated server |
| Integration confidence | Limited by stub behavior | Higher for local JMX path |

**Recommendation:** mock to test call mapping and error branches quickly; use several integration tests with a real server to ensure interface contracts, metadata, naming, and lifecycle match.

Do not rely solely on mock unit tests and conclude that a real MBean is guaranteed to export properly.

## 6. Unit testing with a mock MBeanServerConnection

You can mock the JMX client API with Mockito. This example assumes a Spring version supporting `MBeanProxyFactoryBean.setServer(MBeanServerConnection)` and standard bean initialization.

```java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

class QueueProxyMockTest {
    @Test
    void readsAttributeThroughConnection() throws Exception {
        MBeanServerConnection connection =
            mock(MBeanServerConnection.class);

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        when(connection.getAttribute(name, "PendingCount"))
            .thenReturn(42);

        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
        factory.setServer(connection);
        factory.setObjectName(name);
        factory.setProxyInterface(QueueAdminMBean.class);
        factory.afterPropertiesSet();

        QueueAdminMBean proxy =
            (QueueAdminMBean) factory.getObject();

        assertEquals(42, proxy.getPendingCount());

        verify(connection).getAttribute(name, "PendingCount");
    }
}
```

In some versions or configurations, the factory may inspect `MBeanInfo` or MBean status during initialization. If that happens, the mock must simulate those metadata calls with consistent fixtures, or a real server should be used to avoid building a semantically incomplete mock.

The test does not invoke the `QueueAdmin` implementation: it only verifies how the proxy interacts with `MBeanServerConnection`.

### Testing operation invocation

```java
@Test
void invokesOperationThroughConnection() throws Exception {
    MBeanServerConnection connection =
        mock(MBeanServerConnection.class);
    ObjectName name = new ObjectName(
        "com.example.orders:type=Queue,name=Payment"
    );

    MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
    factory.setServer(connection);
    factory.setObjectName(name);
    factory.setProxyInterface(QueueAdminMBean.class);
    factory.afterPropertiesSet();

    QueueAdminMBean proxy =
        (QueueAdminMBean) factory.getObject();

    proxy.resetStatistics();

    verify(connection).invoke(
        eq(name),
        eq("resetStatistics"),
        aryEq(new Object[0]),
        aryEq(new String[0])
    );
}
```

Depending on how the factory performs introspection and how Mockito matches arrays, verify the exact signature the client sends. For operations with parameters, JMX requires signatures to be type-name arrays, such as `"int"`, not `"java.lang.Integer"` when the method uses a primitive.

## 7. Why can an overly simple mock mislead?

A mock only returns whatever values the test supplies. It does not enforce JMX rules itself:

- Does not confirm the target class is a valid Standard MBean.
- Does not verify published attribute names on its own.
- Does not know `setPaused` is a writable attribute unless you stub related behavior.
- Does not prove operation signatures are compatible with the real MBean.
- Does not guarantee the target `ObjectName` is registered.
- Does not accurately simulate exception wrapping if stubbing is wrong.

For example, the mock:

```java
when(connection.getAttribute(name, "PendingCount"))
    .thenReturn(42);
```

still passes even if in the real server the attribute is named `PendingJobs`. Without integration tests, the mismatch may only surface at deployment time.

For factories/clients with metadata validation, the mock also needs `getMBeanInfo` to return an `MBeanInfo` matching the interface. Never disable validation just to make tests pass if production enables validation.

## 8. Integration testing with a real, isolated MBeanServer

JMX provides a factory to create servers for testing:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.createMBeanServer("test.management");
```

A server created this way is not the JVM's default platform MBeanServer. You can register test MBeans without affecting system MBeans.

JUnit 5 example:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.*;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

class QueueProxyIntegrationTest {

    @Test
    void proxiesRealLocalMBean() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        try {
            QueueAdmin target = new QueueAdmin();
            server.registerMBean(target, name);

            MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
            factory.setServer(server);
            factory.setObjectName(name);
            factory.setProxyInterface(QueueAdminMBean.class);
            factory.afterPropertiesSet();

            QueueAdminMBean proxy =
                (QueueAdminMBean) factory.getObject();

            assertEquals(17, proxy.getPendingCount());
            assertFalse(proxy.isPaused());

            proxy.setPaused(true);
            assertTrue(proxy.isPaused());

            proxy.resetStatistics();
            assertEquals(0, proxy.getPendingCount());

        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

This test covers the full path:

1. Register a real MBean in an `MBeanServer`.
2. Create a proxy for the JMX interface.
3. Read the `PendingCount` attribute.
4. Read/write the `Paused` attribute.
5. Invoke the `resetStatistics` operation.
6. Verify state actually changed.
7. Unregister and release the test server.

**Do not use `ManagementFactory.getPlatformMBeanServer()` in every test** if you can create a dedicated server. The platform server is shared by multiple frameworks/tests in the same JVM, easily causing collisions and leaking MBeans if cleanup is missed.

## 9. Testing with a Spring ApplicationContext

Beyond testing the factory directly, you can start a context to verify the actual wiring of exporter and proxy.

Configuration example:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;
import org.springframework.jmx.export.MBeanExporter;
import java.util.Map;

@Configuration
public class QueueJmxTestConfig {

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("test.management");
    }

    @Bean
    public QueueAdmin queueAdmin() {
        return new QueueAdmin();
    }

    @Bean
    public MBeanExporter queueExporter(
            MBeanServer testMBeanServer, QueueAdmin queueAdmin) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=Payment",
            queueAdmin
        ));
        return exporter;
    }

    @Bean
    public MBeanProxyFactoryBean queueClientFactory(
            MBeanServer testMBeanServer) throws Exception {
        MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
        proxy.setServer(testMBeanServer);
        proxy.setObjectName(new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        ));
        proxy.setProxyInterface(QueueAdminMBean.class);
        return proxy;
    }
}
```

Context test:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class QueueJmxContextTest {

    @Test
    void clientProxyReadsBeanExportedBySpring() {
        try (var context = new AnnotationConfigApplicationContext(
                QueueJmxTestConfig.class)) {

            QueueAdminMBean proxy =
                context.getBean(QueueAdminMBean.class);

            assertEquals(17, proxy.getPendingCount());

            MBeanServer server = context.getBean(MBeanServer.class);
            assertTrue(server.isRegistered(
                new ObjectName(
                    "com.example.orders:type=Queue,name=Payment"
                )
            ));
        }
    }
}
```

In real code, the test method must declare `throws Exception` or handle the checked exception when constructing `ObjectName`. In addition, initialization order of proxy and exporter can affect startup metadata checks: if the factory inspects the MBean during initialization, configure initialization dependencies so the exporter completes registration first.

For instance, add `@DependsOn("queueExporter")` to the `queueClientFactory` bean, or structure bean dependencies explicitly. Never rely accidentally on the declaration order of `@Bean` methods.

## 10. Creating metadata fixtures for mocks

When proxy code needs to inspect MBean metadata, the mock must return valid data for `getMBeanInfo`.

Sketch example:

```java
import javax.management.*;

MBeanAttributeInfo countAttribute = new MBeanAttributeInfo(
    "PendingCount", "int", "Pending queue entries",
    true, false, false
);

MBeanOperationInfo resetOperation = new MBeanOperationInfo(
    "resetStatistics",
    "Resets queue statistics",
    new MBeanParameterInfo[0],
    "void",
    MBeanOperationInfo.ACTION
);

MBeanInfo info = new MBeanInfo(
    QueueAdmin.class.getName(),
    "Queue admin",
    new MBeanAttributeInfo[] { countAttribute },
    null,
    new MBeanOperationInfo[] { resetOperation },
    null
);

when(connection.getMBeanInfo(name)).thenReturn(info);
```

Metadata fixtures must reflect the interface the proxy is exposing. If the test also uses `isPaused` and `setPaused`, add the `Paused` attribute (type `boolean`, readable/writable) so the mock does not contradict itself.

## 11. Testing errors when ObjectName does not exist

A local proxy can be created with a nonexistent name. Depending on the factory's initialization/validation mode, the error may appear immediately during proxy initialization or when a method is invoked.

Using a real `MBeanServer`:

```java
MBeanServer server =
    MBeanServerFactory.createMBeanServer("test.management");

ObjectName missing = new ObjectName(
    "com.example.orders:type=Queue,name=Missing"
);

assertFalse(server.isRegistered(missing));
```

Then configure the proxy with `missing` and assert the exception at the timing governed by the Spring version/configuration. Do not write tests assuming the exception is always a direct `InstanceNotFoundException`: the proxy may wrap the JMX error in a Spring `JmxException` or corresponding runtime exception.

Inspecting the exception chain and related `ObjectName` is more resilient than hardcoding the entire message.

## 12. Testing errors when metadata does not match the interface

Suppose the client interface expects:

```java
int getPendingCount();
void retryFailed(int maxCount);
```

yet the MBean server only exposes `PendingCount` and `resetStatistics()`. When the proxy calls `retryFailed`, the server cannot find the corresponding operation.

You can check `MBeanInfo` first:

```java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
    for (MBeanParameterInfo param : op.getSignature()) {
        System.out.println(param.getType());
    }
}
```

If operation `retryFailed(int)` is absent from `MBeanInfo`, the error belongs to the JMX contract, not the network.

With overloaded methods, the signature is decisive. Primitive `int` requires signature `"int"`, not `"java.lang.Integer"`. A mock can miss this difference if stubbing is overly permissive.

## 13. Testing exception behavior from operations

An operation can throw a business exception:

```java
public void resetStatistics() {
    throw new IllegalStateException("Reset is currently blocked");
}
```

When called through JMX, the server and proxy can wrap the exception. The testing goals are:

- Verify the exception actually reaches the client in a handleable form.
- Inspect the root cause, rather than assuming the client receives the exact implementation exception class.
- Verify data state was not unexpectedly modified.
- Avoid leaving MBeans leaked by the test after an exception occurs.

When mocking `MBeanServerConnection`, you can simulate `MBeanException`, `ReflectionException`, `InstanceNotFoundException`, or `IOException` per the real API, and verify how the proxy wraps those errors.

Do not write assertions against message substrings that vary across JDKs or Spring versions when what matters is the error type and `ObjectName` context.

## 14. Concurrency in tests and stability

A dedicated `MBeanServer` reduces the risk of cross-test interference, yet care is still needed:

- Use unique `ObjectName`s within each server.
- Clean up in `finally` or `@AfterEach`.
- Do not run tests sharing the global platform server with the same `ObjectName` in parallel.
- Do not rely on PIDs, timestamps, or test order for naming MBeans without good reason.
- Ensure no Spring context/connector retains a reference and keeps calling the MBean after teardown.
- If the test creates `MBeanProxyFactoryBean` under Spring's lifecycle, close the context properly.
- Do not call `releaseMBeanServer` on a server not created by `createMBeanServer`.

Example:

```java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("test.management");
```

`newMBeanServer` creates a server not registered in the list managed by the factory, suitable when discovery is unneeded and calling `releaseMBeanServer` is unnecessary.

## 15. When should you use a fully mocked MBeanServer?

A real `MBeanServer` does not need to be created every time. Mocks fit when requirements need to verify:

1. The proxy translates getters into `getAttribute` with the right name.
2. Setters become `setAttribute` with the right `Attribute`.
3. Operations use `invoke` and exact signatures.
4. When the JMX API reports an error, the client application does not lose error context.
5. The client does not invoke an operation if input validation fails beforehand.

If you are only testing the business logic of `QueueAdmin`, unit-test the class directly. If you need to know whether the implementation obeys the Standard MBean contract and the proxy can invoke it, use a real `MBeanServer`.

**Mocks must not completely replace integration tests**, because errors in naming, signatures, metadata, registration, and MBean compliance can slip through.

## 16. Testing against MBeanServerConnection instead of a concrete server

A benefit of the JMX API is that local and remote can appear behind the same `MBeanServerConnection` interface.

```java
MBeanServerConnection local = server;
```

When testing code with an `MBeanServerConnection` dependency, you can inject a mock or a real local server without sockets/RMI.

If the application uses a remote `JMXConnector`, tests with a local `MBeanServer` do not cover:

- Connector authentication and authorization.
- TLS/certificates and network ports.
- Serialization/classloaders across two JVMs.
- Connection timeouts, disconnects, and retries.
- RMI hostname/port, firewalls, or service URLs.

Those are separate integration/e2e requirements. A **real local `MBeanServer`** verifies the JMX contract, not the entire remote transport.

## 17. Recommended test pyramid

A balanced test suite can include:

| Test layer | What to verify | Tools |
| --- | --- | --- |
| Implementation unit test | Queue admin logic | JUnit, no JMX needed |
| Proxy mapping test | Getter/setter/operation translated to JMX API | Mockito + `MBeanServerConnection` |
| JMX compliance test | MBean registers properly, accurate metadata | Real `MBeanServer` |
| Spring wiring test | Exporter and proxy in context use same server/name | `AnnotationConfigApplicationContext` |
| Fault test | Missing MBean, metadata mismatch, operation exception | Mock or real server |
| Remote connectivity test | Auth/TLS/network and serialization | Separately configured JMX connector |

A small demo does not need every single layer, yet there should be at least one local end-to-end test with a real server when MBean proxies are an important part of the system.

## 18. Hands-on exercises

1. Create Standard MBean `QueueAdmin` and proxy `QueueAdminMBean` via `MBeanProxyFactoryBean`; verify `getPendingCount()`.
2. Mock `MBeanServerConnection` and verify the proxy calls `getAttribute(name, "PendingCount")`.
3. Add `setPaused(boolean)` and verify the proxy constructs `Attribute("Paused", true)` when writing.
4. Add operation `retryFailed(int maxCount)`; verify `invoke` passes signature `"int"`.
5. Create an isolated server, register the MBean, then test the client proxy executing operations and check state.
6. Intentionally configure the wrong `ObjectName` to observe errors during initialization or invocation.
7. Use an interface differing from the real MBean's metadata, read `MBeanInfo`, and fix the mismatch.
8. Write a Spring integration test with `MBeanExporter` and `MBeanProxyFactoryBean` in one context; establish dependencies so the exporter initializes before the proxy.
9. Ensure cleanup and run the full test suite repeatedly to catch name collisions or leaks.

## 19. Self-check questions

- Why does testing the implementation directly not prove the MBean proxy works?
- What is a mock `MBeanServerConnection` best at testing?
- Which bugs are only easy to catch when using a real `MBeanServer`?
- What does `MBeanProxyFactoryBean` use `ObjectName` and the management interface for?
- When does a proxy fail because the MBean is not yet registered?
- Why can tests using the platform `MBeanServer` be affected by parallel tests?
- Does using a local `MBeanServer` verify TLS or remote JMX authentication?
- Why must the context be closed and MBeans unregistered after tests?

**Key takeaway:** Spring's local MBean proxy lets clients interact with an MBean using a Java interface while still traversing the JMX API. Use a mock `MBeanServerConnection` to verify call mapping and error branches, combined with a real `MBeanServer` to verify registration, metadata, and execution. Always control `ObjectName`, initialization order, JMX errors, and cleanup so tests remain stable and independent.