# MBeanProxyFactoryBean for Creating Typed Proxies in Spring JMX

## 1. The problem: calling an MBean like a Java interface

In Java Management Extensions (**JMX**), an application can expose management attributes and operations through an **MBeanServer**. A traditional JMX client must know the `ObjectName`, attribute names, operations, parameter types, and how to use `MBeanServerConnection`.

Example of invoking an operation via plain JMX:

```java
ObjectName name = new ObjectName(
    "com.example.jobs:type=WorkerManager,name=background"
);

connection.invoke(
    name,
    "pause",
    new Object[0],
    new String[0]
);
```

This approach works, but forces business code or management code to deal with the JMX API, operation name strings, and parameter signatures. If a method is renamed, the error may only be detected at runtime.

Spring Framework provides **`MBeanProxyFactoryBean`**, a `FactoryBean` that creates a **Java proxy based on a declared interface**. Code calling the proxy looks like it is using a regular Java object:

```java
workerAdmin.pause();
boolean paused = workerAdmin.isPaused();
```

Meanwhile, the actual call is forwarded to the MBean registered in an MBeanServer. This is a way to reduce coupling between the caller and details of the JMX protocol.

**Lesson objectives:** understand how to configure `MBeanProxyFactoryBean`, identify the roles of the interface, ObjectName, and MBeanServerConnection, test a local typed proxy, and recognize its limitations and common pitfalls.

## 2. Architecture of a typed MBean proxy

```text
Spring ApplicationContext
     |
     +-- WorkerAdmin interface
     |       |
     |       v
     +-- MBeanProxyFactoryBean
             |
             +-- proxyInterface = WorkerAdmin
             +-- objectName = com.example.jobs:type=WorkerManager,name=background
             +-- server = MBeanServerConnection
             |
             v
          Typed proxy
             |
             | workerAdmin.pause()
             v
       MBeanServerConnection
             |
             v
          MBeanServer
             |
             +-- ObjectName
                    |
                    +-- WorkerManager MBean
                            |
                            +-- real worker resource
```

Concepts:

| Component | Role |
| --- | --- |
| **Proxy interface** | The Java contract that the caller uses to invoke methods. |
| **`MBeanProxyFactoryBean`** | Creates a proxy from the interface and forwards calls to JMX. |
| **`ObjectName`** | Identifies the target MBean in the MBeanServer. |
| **`MBeanServerConnection`** | Standard API for reading attributes, writing attributes, or invoking operations. |
| **MBeanServer** | The JMX registry containing registered MBeans. |
| **Target MBean** | Executes attributes/operations, which may be exported by Spring. |

**A local proxy does not mean methods are invoked directly on the Java object.** The proxy still goes through the JMX layer and must follow MBean metadata. It provides a typed Java API experience, but does not eliminate JMX rules.

## 3. Why is an interface needed?

`MBeanProxyFactoryBean` needs to know the Java interface that the proxy implements. The interface describes the methods the caller is permitted to invoke at the Java level:

```java
package com.example.management;

public interface WorkerAdmin {
    boolean isPaused();
    int getActiveWorkers();
    void pause();
    void resume();
}
```

The caller can program directly against the interface:

```java
public final class OperationsController {
    private final WorkerAdmin admin;

    public OperationsController(WorkerAdmin admin) {
        this.admin = admin;
    }

    public void ensurePaused() {
        if (!admin.isPaused()) {
            admin.pause();
        }
    }
}
```

Benefits:

- The IDE knows method names, parameter types, and return types.
- The Java compiler catches callers using wrong methods or types.
- Calling code does not need to import `javax.management.ObjectName` or `MBeanServerConnection`.
- The interface can be mocked in unit tests.
- Dependency injection can be used to swap the proxy for another implementation in testing.

**Limitation:** the interface does not by itself guarantee that the target MBean has the corresponding methods. A proxy being created successfully does not necessarily prove every runtime call will succeed. Therefore, metadata and integration behavior must be verified.

## 4. Server-side MBean for testing

To illustrate clearly, build a simple **Standard MBean**. When the class is named `WorkerManager`, the management interface by JMX convention is `WorkerManagerMBean`.

```java
package com.example.management;

public interface WorkerManagerMBean {
    boolean isPaused();
    int getActiveWorkers();
    void pause();
    void resume();
}
```

```java
package com.example.management;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class WorkerManager implements WorkerManagerMBean {
    private final AtomicBoolean paused = new AtomicBoolean();
    private final AtomicInteger activeWorkers = new AtomicInteger(4);

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public int getActiveWorkers() {
        return activeWorkers.get();
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

This is an illustrative resource. `pause()` only sets a status flag and does not yet stop a real scheduler. In a production application, management methods must be wired into worker control logic in a thread-safe and safe manner.

### Registering a Standard MBean with plain Java

```java
package com.example.management;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class LocalMBeanServerDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=WorkerManager,name=background"
        );

        server.registerMBean(new WorkerManager(), name);

        System.out.println("Registered " + name);
        Thread.sleep(10 * 60 * 1000L);
    }
}
```

The server registers `WorkerManager` as an MBean with a fixed ObjectName. If you run the app and open JConsole on the right JVM, you can find the `com.example.jobs` domain and its attributes/operations:

```text
Attributes:
  Paused         boolean
  ActiveWorkers  int

Operations:
  pause()
  resume()
```

## 5. Configuring MBeanProxyFactoryBean with Java configuration

Assume the Spring context manages an MBeanServer where the target MBean has already been registered.

An illustrative configuration:

```java
package com.example.management;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class LocalJmxProxyConfiguration {

    @Bean
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    MBeanProxyFactoryBean workerAdminProxyFactory(
            MBeanServer mbeanServer
    ) {
        MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();

        factory.setServer(mbeanServer);
        factory.setObjectName(
            "com.example.jobs:type=WorkerManager,name=background"
        );
        factory.setProxyInterface(WorkerAdmin.class);

        return factory;
    }
}
```

Meaning of the configuration:

1. `mbeanServer()` points to the platform MBeanServer in the JVM.
2. `setObjectName(...)` specifies the target MBean.
3. `setProxyInterface(WorkerAdmin.class)` selects the contract used by the caller.
4. Spring initializes the factory and provides a proxy implementing the interface instead of requiring callers to call `getAttribute` or `invoke` themselves.

In practice, **the MBean must be registered before the proxy actually interacts**; if the proxy is initialized before the MBean, behavior may depend on Spring's validation/initialization settings, and errors may occur during setup or at invocation time.

### Avoiding confusion about @Bean returning a FactoryBean

`MBeanProxyFactoryBean` is a `FactoryBean`. When registered as a Spring bean, retrieving the bean by name typically returns the **proxy product**, not the FactoryBean instance. You can access the factory itself via Spring's `&beanName` convention if infrastructure manipulation is needed.

Therefore, consuming code should inject the **proxy interface**:

```java
@Component
public class WorkerOperations {
    private final WorkerAdmin workerAdmin;

    public WorkerOperations(WorkerAdmin workerAdmin) {
        this.workerAdmin = workerAdmin;
    }

    public void pauseWork() {
        workerAdmin.pause();
    }
}
```

Depending on the bean name and the type exposed by the FactoryBean, injection configuration may require a qualifier to distinguish if there are multiple proxies with the same interface.

## 6. Configuring with traditional Spring XML style

In Spring XML projects, `MBeanProxyFactoryBean` can be declared as:

```xml
<bean id="workerAdmin"
      class="org.springframework.jmx.access.MBeanProxyFactoryBean">
    <property name="objectName"
              value="com.example.jobs:type=WorkerManager,name=background"/>
    <property name="proxyInterface"
              value="com.example.management.WorkerAdmin"/>
    <property name="server" ref="mbeanServer"/>
</bean>

<bean id="mbeanServer"
      class="org.springframework.jmx.support.MBeanServerFactoryBean">
    <property name="locateExistingServerIfPossible" value="true"/>
</bean>
```

The XML snippet illustrates the idea of wiring `objectName`, `proxyInterface`, and the MBeanServer. A real application should ensure that exact server is also where the target MBean is registered; it must not accidentally create a new MBeanServer and expect to see beans in the platform MBeanServer.

When designing modern systems, Java configuration is usually easier to type-check, though the wiring principles are the same.

## 7. How does a typed proxy translate getters and operations?

Suppose the proxy interface is:

```java
public interface WorkerAdmin {
    boolean isPaused();
    int getActiveWorkers();
    void pause();
    void resume();
}
```

The methods correspond to MBean metadata:

| Java interface method | JMX behavior | JMX name |
| --- | --- | --- |
| `isPaused()` | Read attribute | `Paused` |
| `getActiveWorkers()` | Read attribute | `ActiveWorkers` |
| `pause()` | Invoke operation | `pause` |
| `resume()` | Invoke operation | `resume` |

A setter method can also map to an attribute write operation:

```java
public interface QueueSettings {
    int getMaxParallelism();
    void setMaxParallelism(int value);
}
```

The proxy mechanism needs to rely on JMX metadata or appropriate accessor recognition conventions. With a Standard MBean, `getMaxParallelism()` and `setMaxParallelism(int)` create the `MaxParallelism` attribute.

### The interface does not need the same name as the server-side MBean interface in every design

The client-side interface `WorkerAdmin` serves as the **proxy contract**. The server-side can be `WorkerManagerMBean`, as long as the methods/attributes needed are actually compatible.

This is a benefit of a proxy: the client does not need to know the real server class. However, compatibility must be verified, not inferred merely because the two interfaces have similar names.

## 8. When Spring exports an MBean from a POJO

A Spring application can use `MBeanExporter` and annotations to export a plain bean without implementing a JMX interface.

Example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=WorkerManager,name=background"
)
public class SpringWorkerManagement {
    private volatile boolean paused;

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation
    public void pause() {
        paused = true;
    }

    @ManagedOperation
    public void resume() {
        paused = false;
    }
}
```

When using `AnnotationMBeanExporter` or an exporter with the corresponding assembler, the methods are exposed as MBean metadata.

The `WorkerAdmin` client proxy in the previous example only succeeds when **all methods used by the caller exist in the JMX interface**, whereas `getActiveWorkers()` has not been exposed by this class. If that method is called, a runtime error is likely.

Therefore, if the server-side bean only has `isPaused`, `pause`, `resume`, use a matching proxy interface:

```java
public interface WorkerControl {
    boolean isPaused();
    void pause();
    void resume();
}
```

**MBeanProxyFactoryBean does not invent attributes/operations that the server has not exported.**

## 9. How to inspect metadata before using a proxy

The MBeanServer can tell you what a target MBean exposes:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class WorkerMBeanInspector {
    public static void inspect(
            MBeanServerConnection connection,
            ObjectName name
    ) throws Exception {
        MBeanInfo info = connection.getMBeanInfo(name);

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                "ATTRIBUTE %s: type=%s, read=%s, write=%s%n",
                attribute.getName(),
                attribute.getType(),
                attribute.isReadable(),
                attribute.isWritable()
            );
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.println(
                "OPERATION " + operation.getName()
            );
        }
    }
}
```

For `WorkerAdmin`, at minimum you need:

```text
Paused: boolean, readable=true
ActiveWorkers: int, readable=true
pause(): void
resume(): void
```

In addition to operation names, parameter signatures and return types must be checked. An overload `pause(String)` is not `pause()`; whichever version the client proxy intends to call must have a matching contract.

Metadata verification is especially important after a Spring/JVM upgrade or management schema change because a typed interface is only checked by the compiler on the client side.

## 10. How are local proxies and remote proxies similar and different?

**Local:**

```text
Caller bean -> typed proxy -> local MBeanServer -> target MBean
```

**Remote:**

```text
Caller bean -> typed proxy -> MBeanServerConnection
                               |
                               +-- JMX connector/RMI
                                      |
                                      v
                                  remote MBeanServer
```

Both use:

- The `ObjectName` of the target MBean.
- A Java proxy interface.
- A metadata contract for attributes and operations.

Differences:

| Aspect | Local proxy | Remote proxy |
| --- | --- | --- |
| Connection | MBeanServer inside the JVM | JMXConnector creates a connection to another JVM |
| Network | No network required | Involves network, TLS, authentication, firewall |
| Common errors | Target not registered, wrong ObjectName | Additional timeout, connection failure, RMI endpoint |
| Serialization | Calls via JMX but within the JVM | Requires data compatible across JVM boundaries |
| Lifecycle | Same process, still requires registration order | Requires reconnection and remote state handling |
| Identity | ObjectName in the local server | ObjectName in the remote server |

Do not change the ObjectName just because the client runs on another machine. The ObjectName identifies the MBean in the connected server; host/port belong to connection configuration.

## 11. Remote connections with MBeanServerConnection

When moving from local to remote, a connection can be obtained from a JMX connector:

```java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
);

JMXConnector connector = JMXConnectorFactory.connect(url);

try {
    MBeanServerConnection connection =
            connector.getMBeanServerConnection();

    // Use connection in a JMX proxy or direct client.
} finally {
    connector.close();
}
```

This is a connector example for an endpoint that has already been enabled; do not assume every application opens port 9010. In production, configure appropriate authentication, TLS, network ACLs, and RMI hostname/port.

Spring can create a connection via infrastructure such as `MBeanServerConnectionFactoryBean`, then supply the connection to `MBeanProxyFactoryBean`:

```java
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Bean
MBeanServerConnectionFactoryBean remoteConnection() throws Exception {
    MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();
    factory.setServiceUrl(
        "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
    );
    return factory;
}

@Bean
MBeanProxyFactoryBean remoteWorkerProxy(
        MBeanServerConnection connection
) {
    MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
    factory.setServer(connection);
    factory.setObjectName(
        "com.example.jobs:type=WorkerManager,name=background"
    );
    factory.setProxyInterface(WorkerControl.class);
    return factory;
}
```

Beans and imports in the configuration must be aligned with the actual Spring version and how Spring exposes `FactoryBean`. The illustration is meant to clarify: **the proxy does not directly own the transport**, but instead calls through the configured connection.

## 12. When to use a typed proxy and when to call the JMX API directly?

### A typed proxy is suitable when

- A Java client frequently uses a set of MBeans with a stable contract.
- You want to inject an interface into a Spring service without putting ObjectNames in calling logic.
- You want the IDE and compiler to check method names and parameter types.
- You want to mock/stub management operations in unit tests.
- You want to separate connection/naming configuration from caller code.

### Direct JMX API is suitable when

- The tool is a generic JMX explorer that does not know MBean interfaces in advance.
- You need to dynamically list domains and MBeans using `queryNames`.
- You want to read metadata without a fixed Java contract.
- MBeans have interfaces that vary at runtime.
- The client is non-Java or needs to control via a custom protocol.

A typed proxy does not replace JMX's dynamic introspection capabilities. In operational systems, both can be used: typed proxies for routine operations and the JMX API for diagnostics/monitoring.

## 13. Do not confuse an MBean proxy with a Spring AOP proxy

Both concepts contain the word “proxy”, but their purposes are different:

| Proxy type | Primary goal | Call source |
| --- | --- | --- |
| Spring AOP proxy | Apply advice such as transactions, logging, security | Methods on a Spring bean |
| MBean proxy | Translate Java methods into JMX commands to an MBeanServer | Methods on a Java proxy interface |
| Remote RMI proxy | Represent an object/service over the network | RMI protocol or another abstraction |

An MBean proxy can be further wrapped by Spring AOP, but do not assume that `MBeanProxyFactoryBean` automatically grants transactions or authorization to a JMX operation.

If a target bean is proxied by Spring AOP before being exported, the MBeanServer may see different metadata depending on how the exporter handles proxies. Always inspect the actual registered interface.

## 14. ObjectName and Spring bean name

A Spring bean name, such as `workerAdminProxyFactory`, is not an ObjectName.

```text
Spring bean name: workerAdminProxyFactory
JMX ObjectName:   com.example.jobs:type=WorkerManager,name=background
```

`MBeanProxyFactoryBean` needs the ObjectName of the **MBean on the server**, not the Java bean name in the ApplicationContext.

If there are multiple targets of the same type:

```text
com.example.jobs:type=WorkerManager,name=background
com.example.jobs:type=WorkerManager,name=interactive
```

two proxies can be created with the same Java interface but different `ObjectName`s. When injecting, bean names or qualifiers are needed to distinguish them.

A stable ObjectName prevents clients from depending on server class names or runtime Spring proxy names. Do not base `type` on proxy class names that change with AOP.

## 15. Common errors and diagnostics

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `InstanceNotFoundException` | Target MBean not registered or wrong ObjectName | `isRegistered`, `queryNames`, actual server |
| Proxy bean not created | Missing `proxyInterface` or misconfiguration | Bean definition, type, initialization log |
| Injecting interface cannot find bean | Spring does not expose expected type or wrong qualifier | FactoryBean product type, bean name |
| Attribute cannot be read | Getter not exported or read permission missing | `MBeanInfo.getAttributes()` |
| `AttributeNotFoundException` | Attribute name differs from method convention | Compare attribute name in metadata |
| `ReflectionException` | Missing operation or signature mismatch | `MBeanInfo.getOperations()` |
| `MBeanException` | MBean logic threw an exception | Root cause, resource logs |
| Proxy call succeeds but state does not change | Method only flips a flag not applied to resource | Actual target implementation |
| Works locally, fails remotely | Network connection, TLS, auth, RMI endpoint | Test connection then metadata |
| Client deserialization error | Return type incompatible with client classpath | MXBean/Open Types or simple types |
| Newly added Java method causes proxy error | Client interface is newer than target MBean | Align versions and contracts |
| Same interface but calls wrong MBean | `ObjectName` points to another resource | Log canonical name and target |

### Systematic diagnosis

1. Confirm connection to the right `MBeanServerConnection`.
2. Check that the target `ObjectName` is registered.
3. Read `MBeanInfo` to confirm attributes and operations.
4. Check the proxy interface and method signatures.
5. Try reading a read-only attribute before invoking operations with side effects.
6. Inspect the root exception and Spring initialization logs.
7. If remote, check connector/security/serialization.
8. If errors occur after an upgrade, compare the server contract and client interface.

## 16. Important limitations of typed proxies

### 16.1. A proxy does not turn JMX into a direct Java call

Even though the syntax `workerAdmin.pause()` looks like an object call, the call still goes through `MBeanServerConnection`. Runtime exceptions and JMX management overhead can still occur.

### 16.2. Type safety is only on the client side

The compiler ensures the caller passes the right types according to the interface. However, if the server registers an MBean with a different contract, errors will still occur at call time.

### 16.3. A proxy does not create an MBean

`MBeanProxyFactoryBean` creates a **client** for an already-registered MBean. Exporting/registering the MBean is a separate responsibility, usually handled by `MBeanExporter`, `AnnotationMBeanExporter`, or direct JMX code.

### 16.4. A proxy does not handle business concurrency automatically

If multiple clients call `pause()`, `resetStatistics()`, `rebuildIndex()`, the target must ensure the operation is safe. Type-safe method invocation does not mean idempotent or thread-safe.

### 16.5. A proxy does not replace authorization

JMX connection permissions, access control, and business checks still apply. A method being present in the interface does not guarantee the caller is authorized to invoke it.

### 16.6. A proxy does not eliminate remote costs

With remote JMX, network latency, timeouts, retries, and intermittent connectivity affect every call. Do not use a remote proxy for methods called at extremely high frequency in business request processing flows.

## 17. Designing resilient proxy interfaces

A good proxy contract:

```java
public interface PaymentQueueAdmin {
    long getPendingCount();
    boolean isProcessingEnabled();
    void pauseProcessing();
    void resumeProcessing();
}
```

Desirable characteristics:

- **Clear method names:** avoid a vague `execute()` method.
- **Simple parameter types:** `String`, primitives, wrappers, or MXBean-compatible types when remoting is needed.
- **Getters with minimal side effects:** suitable for polling and diagnostics.
- **State-targeted operations:** `pause`/`resume` are easier to retry than `toggle`.
- **Stable versioned contract:** changing method names or types requires evaluating consumers.
- **Clear target ObjectName:** placed in config and not derived from runtime proxy classes.
- **Do not expose the entire service API:** only the management methods actually needed.

### When the API changes version

If the server removes `pauseProcessing()` and replaces it with `setProcessingEnabled(boolean)`, older client proxies will fail. Changes to an MBean contract should be treated as breaking changes unless there is an explicit compatibility mechanism.

One transition approach is to temporarily keep the old operation or use a versioned ObjectName for the new API. Depending on system scale, you can also add integration tests between server MBean metadata and the proxy interface.

## 18. Unit testing callers with a mock proxy interface

A key benefit of a typed proxy is that the caller does not depend on JMX mechanisms during unit tests.

```java
public class FakeWorkerAdmin implements WorkerAdmin {
    private boolean paused;

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public int getActiveWorkers() {
        return paused ? 0 : 4;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
```

Caller test:

```java
WorkerAdmin admin = new FakeWorkerAdmin();
OperationsController controller = new OperationsController(admin);

controller.ensurePaused();

assert admin.isPaused();
```

This unit test requires neither JMX nor a Spring context. It only verifies caller logic against the Java contract.

Conversely, a **separate integration test** is needed to verify that the proxy factory actually calls the right MBean through the MBeanServer.

## 19. Local integration testing with MBeanServer

A test should create a separate MBeanServer and register the target MBean in it:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server = MBeanServerFactory.createMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=WorkerManager,name=background"
);

server.registerMBean(new WorkerManager(), name);
```

Then initialize `MBeanProxyFactoryBean` pointing to `server` and the `WorkerAdmin` interface.

Illustrative example outside a Spring container:

```java
import org.springframework.jmx.access.MBeanProxyFactoryBean;

MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
factory.setServer(server);
factory.setObjectName(
    "com.example.jobs:type=WorkerManager,name=background"
);
factory.setProxyInterface(WorkerAdmin.class);

factory.afterPropertiesSet();

WorkerAdmin proxy = (WorkerAdmin) factory.getObject();
proxy.pause();

assert proxy.isPaused();
```

At the end of the test, unregister the MBean and release the MBeanServer if the test manages that lifecycle. When tests run multiple times, use ObjectNames that do not collide with other tests.

**Checkpoint:** the proxy can invoke getters and operations matching the metadata. Only this proves the typed client and target MBean connection works in practice.

## 20. FactoryBean and initialization lifecycle

`MBeanProxyFactoryBean` is a component initialized by the Spring container during the context lifecycle.

Things to note:

1. The target MBean must exist on the server when the proxy needs to make a call.
2. The ObjectName must be valid.
3. The declared interface must be an appropriate Java interface.
4. If the server MBean is replaced or unregistered, the proxy may encounter errors until the target reappears.
5. When closing the context, remote connections created by other factories need to be closed/released.
6. Initialization relationships may need to be declared if the exporter and proxy reside in the same context but dependency order is not guaranteed.

### If the exporter and proxy are in the same ApplicationContext

When you need to ensure the exporter registers the MBean before the proxy, an explicit dependency can be used, such as a `@DependsOn` relationship between the factory bean and the exporter. However, the bean name must be accurate and `FactoryBean` lifecycle semantics must be respected; verify with real integration tests rather than assuming arbitrary bean creation order will always hold.

## 21. A local proxy is not a copy of the MBean

A local proxy does not hold an independent copy of the MBean. It represents an ObjectName/connection:

```text
Proxy A -> ObjectName X -> Current MBean at X
Proxy B -> ObjectName X -> Current MBean at X
```

Two different proxies can act on the same resource. When an MBean is replaced under ObjectName X, a proxy can continue calling into the new MBean if the contract remains compatible.

Therefore:

- Avoid using a proxy as a state snapshot.
- Do not treat proxy identity as an immutable resource identity.
- When a snapshot is needed, call getters and intentionally store the resulting data.
- When detecting MBean replacement is needed, observe registrations or a version attribute if supported by the system.

## 22. Practical example: using a proxy to control a queue

Suppose the system has an MBean:

```text
com.example.orders:type=PaymentQueue,name=primary
```

Typed interface:

```java
public interface PaymentQueueControl {
    long getPendingCount();
    boolean isPaused();
    void pause();
    void resume();
}
```

A Spring service using the proxy:

```java
public class QueueSupervisor {
    private final PaymentQueueControl queue;

    public QueueSupervisor(PaymentQueueControl queue) {
        this.queue = queue;
    }

    public void pauseWhenBacklogTooHigh(long threshold) {
        if (queue.getPendingCount() > threshold) {
            queue.pause();
        }
    }
}
```

The code snippet illustrates how depending on an interface simplifies the caller. However, **automatically pausing the system when the backlog is high** can cause the queue to grow even larger; this is only a syntax example, not a recommended operational policy. In production, control logic must be designed around appropriate metrics, capacity, and operational procedures.

## 23. Checklist for deploying MBeanProxyFactoryBean

Before introducing a typed proxy into an application:

1. **Is the target MBean registered?** Use `isRegistered(ObjectName)`.
2. **Right MBeanServer?** The proxy and exporter point to the same server (or a remote connection to the target server).
3. **Stable ObjectName?** Use complete domain and key properties.
4. **Appropriate interface?** Getters, setters, and operations match `MBeanInfo`.
5. **Compatible data types?** Especially for remote clients.
6. **Sound initialization order?** Target is available when the proxy begins interacting.
7. **Multiple proxies with the same interface?** Use clear bean names/qualifiers.
8. **Runtime error handling?** Handle target, network, security, and MBean exceptions.
9. **Safe operations?** Do not confuse typed invocation with idempotency.
10. **Integration tests present?** Test the full proxy → MBeanServer → target path.
11. **Local/remote config separated?** Keep ObjectName stable, configure transport separately.
12. **Appropriate security?** Remote JMX requires authentication, TLS, and network restrictions.

## 24. Self-check questions

**1. Does MBeanProxyFactoryBean create an MBean or a client for an MBean?**

It creates a **client proxy** to invoke an already-registered MBean. An exporter or other JMX code is responsible for registering the target.

**2. Why is proxyInterface needed?**

So Spring can create an object implementing a Java interface, allowing callers to invoke typed methods and reducing dependency on the JMX API.

**3. Does a typed proxy guarantee the method exists on the server?**

Not absolutely. The compiler checks the interface on the client side; the actual MBean must still expose compatible metadata.

**4. Does a local proxy go through the MBeanServer?**

Yes. It forwards calls via `MBeanServerConnection`, not necessarily directly to the Java resource.

**5. Is a Spring bean name an ObjectName?**

No. A bean name is an identifier in the ApplicationContext; an ObjectName is an MBean identifier in the JMX registry.

**6. What happens when the server side changes the ObjectName?**

A client proxy using the old name may encounter `InstanceNotFoundException` or a corresponding error until its configuration is updated.

**7. Does using a typed proxy replace authentication or authorization?**

No. JMX access permissions and business controls still apply.

**8. When should you choose the direct JMX API?**

When the client needs to discover MBeans dynamically, read diverse metadata, or lacks a stable interface.

## 25. Summary

Spring Framework's **`MBeanProxyFactoryBean`** turns JMX operations into calls through a **typed Java interface**, making caller code more readable, testable, and less tied to `ObjectName`, `MBeanServerConnection`, or operation name strings.

The three key configuration properties are:

```text
server         -> MBeanServerConnection containing the target MBean
objectName     -> full name of the registered MBean
proxyInterface -> Java contract used by the caller
```

A local proxy is suitable when components within the same JVM need to call a JMX management interface in a structured way. However, the proxy does not create the MBean itself, does not guarantee server metadata always remains compatible with the client interface, and does not replace security or operation concurrency control.

**The most reliable way to verify** is an integration test that registers a concrete MBean, configures `MBeanProxyFactoryBean` pointing to the exact ObjectName, and confirms getters and operations execute through the proxy as expected.

### References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — JMX proxy: https://docs.spring.io/spring-framework/reference/integration/jmx/proxy.html
- Spring Framework API — `MBeanProxyFactoryBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework API — `MBeanServerConnectionFactoryBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerConnectionFactoryBean.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
