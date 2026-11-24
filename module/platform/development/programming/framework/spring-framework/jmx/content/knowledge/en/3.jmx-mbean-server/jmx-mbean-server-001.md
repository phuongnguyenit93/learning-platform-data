# Registering and Unregistering MBeans in MBeanServer

## Learning Objectives

After this lesson, you will be able to explain the role of `MBeanServer` in Java Management Extensions (JMX); perform `registerMBean` and `unregisterMBean`; use `ObjectName` to properly identify objects; check registration status; handle common errors; and organize the MBean management lifecycle when integrating with the Spring Framework.

## 1. MBeanServer Is Where MBeans Are Registered

In JMX, an MBean is a component that exposes attributes, operations, and sometimes notifications for monitoring and operating a Java application. `MBeanServer` acts as a **registry and management access point**: each MBean is registered under an `ObjectName`, and JMX clients can then query that object through the server's API.

Typical steps:

1. Create an object that satisfies a JMX contract (Standard MBean, MXBean, Dynamic MBean, or another valid form).
2. Choose the `MBeanServer` that will hold the object.
3. Create an `ObjectName` that distinguishes the object from other MBeans.
4. Call `registerMBean(instance, objectName)`.
5. While the application is running, inspect and interact with the object through the server.
6. When the object no longer needs to be managed, call `unregisterMBean(objectName)` or use the corresponding lifecycle management mechanism.

A single instance can only be registered under a specific name in the same `MBeanServer` without causing a name collision. MBeans of the same type can still coexist if they have different `ObjectName`s.

**Important distinction:** creating a Spring bean in `ApplicationContext` does not automatically guarantee that the bean has become a JMX MBean. `MBeanServer` is the JMX registry; the Spring IoC container is the registry of Spring beans. `MBeanExporter` can bridge the two mechanisms.

## 2. Preparing a Simple Standard MBean

Example declaring a task counter management contract:

**TaskCounterMBean.java**

```java
package com.example.jmx;

public interface TaskCounterMBean {
    long getCompletedCount();
    void increment();
    void reset();
}
```

**TaskCounter.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class TaskCounter implements TaskCounterMBean {
    private final AtomicLong completed = new AtomicLong();

    @Override
    public long getCompletedCount() {
        return completed.get();
    }

    @Override
    public void increment() {
        completed.incrementAndGet();
    }

    @Override
    public void reset() {
        completed.set(0L);
    }
}
```

With a Standard MBean, the `TaskCounter` class implements the `TaskCounterMBean` interface according to JMX conventions. When properly registered, the `CompletedCount` attribute will be read-only; `increment` and `reset` will be operations. `AtomicLong` is used because JMX calls and application processing threads may access the counter concurrently.

## 3. Registering with registerMBean

You can obtain the platform MBean server provided by the JVM:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
```

Complete registration example:

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectInstance;
import javax.management.ObjectName;

public class RegisterDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        TaskCounter counter = new TaskCounter();
        ObjectName name = new ObjectName(
                "com.example.jmx:type=TaskCounter,name=main"
        );

        ObjectInstance registered = server.registerMBean(counter, name);

        System.out.println("Registered: " + registered.getObjectName());
        counter.increment();

        Object value = server.getAttribute(name, "CompletedCount");
        System.out.println("CompletedCount: " + value);

        server.invoke(name, "reset", new Object[0], new String[0]);
        System.out.println(server.getAttribute(name, "CompletedCount"));
    }
}
```

Explanation:

- `ManagementFactory.getPlatformMBeanServer()` retrieves the platform MBean server, which is usually the natural choice so JVM management tools can see application MBeans.
- `ObjectName` is the JMX identifier, structured as `domain:key=value,...`. Here, the domain is `com.example.jmx` and the keys distinguish the type from the instance.
- `registerMBean` validates that the object is a valid MBean and adds it to the server. If successful, the result is an `ObjectInstance`, containing the class name and object name according to JMX metadata.
- `getAttribute` and `invoke` access the MBean contract through the server, without needing to pass a Java reference of the object to the JMX client.

Within a single server, `ObjectName` must be unique. Two different objects cannot share `com.example.jmx:type=TaskCounter,name=main` at the same time. Conversely, `name=worker-1` and `name=worker-2` can be used to represent two independent counters.

## 4. Checking Before Registering

`MBeanServer.isRegistered(ObjectName)` indicates whether a name is currently in the registry:

```java
if (!server.isRegistered(name)) {
    server.registerMBean(counter, name);
}
```

However, **checking beforehand does not make the operation atomic**. Another thread could register the same name after `isRegistered` but before `registerMBean`. Therefore, you need to handle `InstanceAlreadyExistsException` at the registration call if there is contention:

```java
import javax.management.InstanceAlreadyExistsException;

try {
    server.registerMBean(counter, name);
} catch (InstanceAlreadyExistsException duplicate) {
    // The name already has an owner in MBeanServer.
    // Decide explicitly: keep the existing MBean, report an error, or choose another name.
    throw duplicate;
}
```

You should not arbitrarily call `unregisterMBean` to reclaim the name if you do not know which component owns the current object. In an application containing multiple contexts or libraries, doing so could remove another module's MBean.

You can use `queryNames(ObjectName pattern, QueryExp query)` to find MBeans matching a pattern, for example:

```java
ObjectName pattern =
        new ObjectName("com.example.jmx:type=TaskCounter,*");

for (ObjectName match : server.queryNames(pattern, null)) {
    System.out.println(match.getCanonicalName());
}
```

When creating an `ObjectName` dynamically from data containing special characters, use the quoting/escaping syntax supported by JMX and avoid uncontrolled string concatenation.

## 5. Unregistering with unregisterMBean

An MBean ceases to be available through the registry after calling:

```java
server.unregisterMBean(name);
```

Example:

```java
if (server.isRegistered(name)) {
    server.unregisterMBean(name);
}
```

`unregisterMBean` only removes the JMX registration entry. It **does not mean** the Java object is destroyed, threads are stopped, or external resources (sockets, executors, database connections) are automatically closed. If the application still holds a reference to `TaskCounter`, the object continues to exist normally and direct Java method calls still work.

Similarly to registration, calling `isRegistered` before unregistering is only a point-in-time check. If the object has already been removed by another thread, `unregisterMBean` may throw `InstanceNotFoundException`. Design your cleanup policy around ownership and lifecycle, rather than relying on the assumption that a pre-check is sufficient.

```java
import javax.management.InstanceNotFoundException;

try {
    server.unregisterMBean(name);
} catch (InstanceNotFoundException alreadyGone) {
    // Only ignore if "already unregistered" behavior is considered valid
    // under this component's cleanup policy.
}
```

For MBeans with lifecycle callbacks (`MBeanRegistration`), the server may invoke `preRegister`, `postRegister`, `preDeregister`, and `postDeregister` at the corresponding stages. These are JMX hooks and do not replace closing resources according to the application lifecycle.

## 6. Safe Lifecycle Management Pattern in Plain Java

When a component creates an MBean, that component should also be responsible for cleaning it up. Use `try/finally` in exercises to ensure unregistration if registration succeeded.

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class LifecycleDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.jmx:type=TaskCounter,name=demo"
        );
        TaskCounter counter = new TaskCounter();

        boolean registered = false;
        try {
            server.registerMBean(counter, name);
            registered = true;

            counter.increment();
            System.out.println(
                    server.getAttribute(name, "CompletedCount")
            );
        } finally {
            if (registered) {
                server.unregisterMBean(name);
            }
        }
    }
}
```

The `registered` flag prevents unregistering a same-named MBean previously registered by another component: if `registerMBean` throws an error, `registered` remains `false`. This example assumes no other party replaces or unregisters the same `ObjectName` at runtime; real applications require sufficiently strict ownership conventions.

If an MBean needs to live for the entire lifetime of a service, the registration point can be service startup, and the unregistration point can be a shutdown hook or component stop callback. Do not use a request-scoped `try/finally` if the MBean is intended to be accessed long-term.

## 7. Integrating Spring Framework with MBeanExporter

Spring provides `org.springframework.jmx.export.MBeanExporter` to manage registering/exporting managed objects. This is usually the right approach when the object is a Spring bean and needs the same lifecycle as the `ApplicationContext`.

Plain Spring Framework configuration example:

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {
    @Bean
    public TaskCounter taskCounter() {
        return new TaskCounter();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            TaskCounter taskCounter,
            MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
                "com.example.jmx:type=TaskCounter,name=main",
                taskCounter
        ));
        return exporter;
    }
}
```

When Spring initializes the context, `MBeanExporter` exports/registers the configured MBeans; when the context is properly closed at the end of its lifecycle, the exporter handles unregistering the MBeans within its scope of management. There is no need to manually call `server.registerMBean` for the same object and `ObjectName` when already using the exporter; otherwise, a registration conflict will occur.

**Spring Boot note:** JMX exposure can be controlled via Boot's configuration and auto-configuration. Check what the context is already creating before defining additional `MBeanServer` or `MBeanExporter` beans. With plain Spring Framework, the example above creates the necessary beans directly in the configuration.

### Manual Registration Following the Spring Lifecycle

When full control over `registerMBean` and `unregisterMBean` is needed, lifecycle callbacks can be used. Example of a bean managing registration through `InitializingBean` and `DisposableBean`:

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

public class TaskCounterRegistration
        implements InitializingBean, DisposableBean {

    private final MBeanServer server;
    private final TaskCounter counter;
    private final ObjectName name;
    private boolean registered;

    public TaskCounterRegistration(
            MBeanServer server, TaskCounter counter
    ) throws Exception {
        this.server = server;
        this.counter = counter;
        this.name = new ObjectName(
                "com.example.jmx:type=TaskCounter,name=manual"
        );
    }

    @Override
    public void afterPropertiesSet() throws Exception {
        server.registerMBean(counter, name);
        registered = true;
    }

    @Override
    public void destroy() throws Exception {
        if (registered) {
            server.unregisterMBean(name);
            registered = false;
        }
    }
}
```

Register the lifecycle manager bean with `@Bean`, passing in the two dependencies `MBeanServer` and `TaskCounter`. The callbacks are invoked by Spring when the bean is initialized and when the context is closed. The example intentionally uses `name=manual` to avoid colliding with the exporter in the previous example; in real applications, choose **one registration ownership mechanism** per MBean.

The manual pattern is useful when registration depends on a runtime condition or requires controlling specific hooks. When you only need to export Spring beans, `MBeanExporter` typically reduces lifecycle management boilerplate.

## 8. Errors and Scenarios to Handle

| Scenario | Exception or Symptom | How to Think About It |
| --- | --- | --- |
| Registering an existing `ObjectName` | `InstanceAlreadyExistsException` | Check who owns the name; do not remove another party's object |
| Class does not meet an MBean contract | `NotCompliantMBeanException` | Check the Standard MBean interface, MXBean, or Dynamic MBean |
| Invalid JMX name syntax | `MalformedObjectNameException` when creating the name | Fix domain/key/value; quote data containing special characters |
| Removing a non-existent object | `InstanceNotFoundException` | Determine whether this is a lifecycle bug or an idempotent cleanup |
| MBean invocation at runtime throws an exception | `MBeanException`, `ReflectionException`, or related errors | Check method, signature, business errors, metadata |
| Bean exported via Spring and also registered manually | Duplicate `ObjectName` | Choose a single party responsible for registration/unregistration |
| MBean not visible in JConsole | MBean not yet registered, different name, or wrong JVM selected | Check `isRegistered`, `queryNames`, and the connection |

For remote JMX, add authentication, restrict access permissions, and secure the connection. JMX operations can alter system state, so do not expose dangerous operations or sensitive data by default.

## 9. Hands-on Exercises and Observations

1. Create `TaskCounterMBean` and `TaskCounter` following the example.
2. Register with `com.example.jmx:type=TaskCounter,name=lab`. Confirm `server.isRegistered(name)` returns `true`.
3. Call `increment()`, read `CompletedCount` via `getAttribute`, and verify the result.
4. Open JConsole on the same JVM and observe the attribute and the two operations `increment` and `reset`.
5. Try registering another `TaskCounter` under the **same** `ObjectName`; observe `InstanceAlreadyExistsException`.
6. Register a second instance with `name=lab2`; use `queryNames` to find both.
7. Unregister `name=lab`, confirm `isRegistered(name)` returns `false`, while `name=lab2` still exists.
8. Try unregistering `name=lab` again; explain `InstanceNotFoundException`. Clean up the remaining instance.

Self-check questions:

- Why can multiple MBeans of the same class coexist in the same server?
- Why is `isRegistered` not sufficient to guarantee no errors from concurrent registration?
- After `unregisterMBean`, is the Java object immediately garbage collected?
- When using `MBeanExporter`, who should be responsible for unregistration?
- How do a Spring bean name and a JMX `ObjectName` differ?

## 10. Key Takeaways

`registerMBean` adds a valid managed object to `MBeanServer` under an `ObjectName`; `unregisterMBean` removes that registration. `ObjectName` must be unique within a server, registration state can change concurrently, and the party creating the registration must clearly define cleanup responsibility. In the Spring Framework, `MBeanExporter` helps tie MBean export to the application context lifecycle; if you perform registration manually, you must ensure a corresponding unregistration mechanism.
