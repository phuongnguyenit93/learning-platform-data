# Managing Custom MBeanServer Lifecycle in the Spring Container

## Learning Objectives

After this lesson, you will be able to explain the lifecycle of an `MBeanServer` managed by Spring Framework, distinguish a Spring-created server from an existing JVM server, use `MBeanServerFactoryBean` or `@Bean` to supply a server to `MBeanExporter`, handle MBean initialization/registration/unregistration when `ApplicationContext` closes, and avoid losing MBeans or leaking retained resources when the application restarts in the same JVM.

The content focuses on a **custom MBeanServer** inside the Spring IoC container, not Docker container lifecycles. "Container" here primarily refers to `ApplicationContext` and how Spring manages beans.

## 1. Distinguishing MBean, MBeanServer, and ApplicationContext Lifecycles

JMX (Java Management Extensions) provides `MBeanServer` to manage objects (MBeans) registered under a unique `ObjectName`. In a Spring application:

- `ApplicationContext` manages the lifecycle of Spring beans.
- `MBeanExporter` registers managed beans into an `MBeanServer` and can unregister the MBeans it is responsible for when the exporter is destroyed.
- `MBeanServer` holds the management registry until the server is released or the JVM terminates; the actual lifecycle depends on who created the server.
- JMX clients such as JConsole read the registry through a connection to the appropriate server.

These are three separate responsibilities. Closing `ApplicationContext` does not always mean releasing the platform `MBeanServer`, and releasing a server should not be treated as a substitute for having the exporter clean up registrations it owns.

Lifecycle diagram:

```text
Spring ApplicationContext.start/refresh
       |
       +--> create or obtain MBeanServer
       |
       +--> create managed Spring beans
       |
       +--> initialize MBeanExporter
                 |
                 +--> registerMBean(bean, ObjectName)
       |
       v
Application running: JConsole/JMX client reads MBeans
       |
Spring ApplicationContext.close
       |
       +--> destroy exporter -> unregister MBeans managed by exporter
       |
       +--> destroy server-managing bean (if server was created by bean)
                 |
                 +--> release server according to ownership
```

Bean destruction order also depends on the dependency graph; therefore, express the exporter → server relationship explicitly rather than assuming an arbitrary order.

## 2. Application-Created or JVM-Provided MBeanServer?

Two commonly confused cases:

### Platform MBeanServer

```java
MBeanServer platform = ManagementFactory.getPlatformMBeanServer();
```

This is the JVM's platform server. Standard platform MXBeans are published through this server. If Spring merely **borrows** the platform server, Spring is not its owner and should not release the platform server when the context closes.

If declared as:

```java
@Bean
public MBeanServer platformMBeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
```

then the `MBeanServer` bean simply returns an existing server. In terms of ownership, the Spring context is using the server rather than creating an independent JMX server that needs to be released.

### Custom Server

```java
MBeanServer custom =
        MBeanServerFactory.createMBeanServer("custom.monitoring");
```

This is a new `MBeanServer`, separate from the platform server. If created with `MBeanServerFactory.createMBeanServer`, the server is added to the list tracked by the JMX factory so it can be located and released later. The component that creates the server should clearly determine when to call `MBeanServerFactory.releaseMBeanServer(custom)`.

**Important:** `releaseMBeanServer` only applies validly to servers created by the factory and still managed by the factory under the corresponding mechanism. It is not a generic contract command to "delete all MBeans" or "close all JMX connections".

In Spring, `MBeanServerFactoryBean` is the appropriate utility to make server creation/lookup and lifecycle part of the IoC container.

## 3. Using MBeanServerFactoryBean So Spring Owns the Custom Server

`org.springframework.jmx.support.MBeanServerFactoryBean` is a `FactoryBean<MBeanServer>` that provides a JMX server to other beans. It supports configuring `defaultDomain`, existing-server lookup mode, and the release lifecycle of a server it creates itself.

Example:

```java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class CustomServerConfiguration {

    @Bean(name = "applicationMBeanServer")
    public MBeanServerFactoryBean applicationMBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.management");
        factory.setLocateExistingServerIfPossible(false);
        return factory;
    }
}
```

Here, Spring manages the **factory bean**, while beans wanting an `MBeanServer` injected receive the object provided by the factory. Because `locateExistingServerIfPossible=false`, the configuration requests creating a new server instead of attempting to find an existing one.

`defaultDomain` is the default domain for `ObjectName` instances created without a domain per the corresponding JMX rules; it does not automatically place all application MBeans into one domain or guarantee system-wide uniqueness.

Returning `MBeanServerFactoryBean` directly from `@Bean` allows Spring to manage the factory's lifecycle. Conversely, if you manually do `new MBeanServerFactoryBean()`, call `afterPropertiesSet()`, and return only `factory.getObject()`, the container may not know about the factory to invoke destroy and release the server. If you take that approach, you must implement cleanup yourself.

## 4. Providing a Custom Server to MBeanExporter

Create a Standard MBean to observe registration:

**JobMonitorMBean.java**

```java
package com.example.jmx;

public interface JobMonitorMBean {
    int getCompletedJobs();
    void recordCompletedJob();
}
```

**JobMonitor.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger completed = new AtomicInteger();

    @Override
    public int getCompletedJobs() {
        return completed.get();
    }

    @Override
    public void recordCompletedJob() {
        completed.incrementAndGet();
    }
}
```

Put the exporter and server into the same Spring configuration:

```java
package com.example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class CustomJmxConfiguration {

    @Bean(name = "applicationMBeanServer")
    public MBeanServerFactoryBean applicationMBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.management");
        factory.setLocateExistingServerIfPossible(false);
        return factory;
    }

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanExporter jobMonitorExporter(
            JobMonitor jobMonitor,
            MBeanServer applicationMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(applicationMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.management:type=JobMonitor,name=primary",
                jobMonitor
        ));
        return exporter;
    }
}
```

At this point `MBeanExporter` registers into the **custom server** rather than defaulting to the platform server. The two servers have independent registries, even within the same JVM.

To avoid ambiguity if the context contains multiple beans of type `MBeanServer`, use `@Qualifier("applicationMBeanServer")` on the exporter factory method parameter. This dependency also helps Spring recognize that the exporter needs the server during lifecycle management.

## 5. Running the ApplicationContext and Reading the Registry

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class CustomServerDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer capturedServer;

        try (var context = new AnnotationConfigApplicationContext(
                CustomJmxConfiguration.class)) {

            capturedServer = context.getBean(
                    "applicationMBeanServer", MBeanServer.class);

            ObjectName name = new ObjectName(
                    "com.example.management:type=JobMonitor,name=primary");

            System.out.println(
                    "Custom registered: " + capturedServer.isRegistered(name));

            JobMonitor monitor = context.getBean(JobMonitor.class);
            monitor.recordCompletedJob();

            System.out.println(
                    "CompletedJobs: "
                    + capturedServer.getAttribute(name, "CompletedJobs"));

            System.out.println(
                    "Default domain: " + capturedServer.getDefaultDomain());
        }

        // Context has closed: both exporter and factory have been destroyed.
        // Do not use capturedServer as a still-living management service.
    }
}
```

Before closing the context, the server can return `Custom registered: true` and `CompletedJobs: 1`.

When the context closes properly, the exporter must unregister the MBeans it manages and the factory is responsible for releasing the server it created. Do not continue using the `capturedServer` reference as a server guaranteed to remain in the application's managed lifecycle after the context has closed.

An `MBeanServer` released from the factory registry may still exist as a Java object if references remain, but that does not mean its lifecycle is valid or that it is still managed by JMX discovery. Tests must verify policy and ownership rather than assuming immediate garbage collection of the object.

## 6. Spring Lifecycle: Bean Init and Destroy

`ApplicationContext.refresh()` initializes beans according to the dependency graph. `MBeanServerFactoryBean` performs server initialization when created. `MBeanExporter` also uses Spring lifecycle callbacks to register MBeans.

When `ApplicationContext.close()` runs:

1. The container emits the close signal.
2. The lifecycle processor stops any `Lifecycle` or `SmartLifecycle` beans.
3. Singleton beans are destroyed according to dependency relationships and container rules.
4. The exporter unregisters the MBeans it manages.
5. The factory managing the server is destroyed/released if it owns the created server.

In an exporter configuration taking an `MBeanServer` parameter, Spring knows the exporter depends on the server. This helps destruction keep the server available while the exporter still needs to unregister. If configured using references not clearly tracked by the container, verify the actual lifecycle; `@DependsOn` or explicit dependency injection can be used instead of relying solely on method declaration order in a Java file.

**Do not call `MBeanServerFactory.releaseMBeanServer` from an arbitrary `@PreDestroy` of a business bean** while the exporter may still need to unregister MBeans. Let the server-owning component perform cleanup at the appropriate time.

## 7. locateExistingServerIfPossible: Borrowing a Server or Creating a New One?

`MBeanServerFactoryBean` has a setting that determines whether to look for an existing server first.

```java
factory.setLocateExistingServerIfPossible(true);
```

When locating an existing server is enabled, the factory can use an existing `MBeanServer` if suitable, or create a new one when none is found. This changes ownership:

| Scenario | Server Source | Lifecycle Principle |
| --- | --- | --- |
| Factory creates a new server | Custom JMX server belonging to the factory | Factory may release the server it created |
| Factory finds an existing server | Server created/managed by another component | Do not arbitrarily release a server the factory does not own |
| App gets platform MBeanServer directly | JVM platform server | Do not release when Spring context closes |

Server lookup behavior can depend on the list of existing servers and lookup criteria. If testing or production requires a dedicated server to isolate the registry, configure it explicitly instead of relying on automatic lookup results.

An application with multiple `ApplicationContext` instances in the same JVM must align on server ownership. If both contexts borrow a shared server, neither should release that server when only one context closes.

## 8. Multiple ApplicationContexts Sharing an MBeanServer

Suppose a JVM has a root context and a child context:

```text
JVM
  |
  +-- Root ApplicationContext
  |      |
  |      +-- sharedMBeanServer
  |      +-- exporterA -> ObjectName A
  |
  +-- Child ApplicationContext
         |
         +-- exporterB -> ObjectName B
         +-- inject sharedMBeanServer
```

This model is valid if both exporters manage separate names. However, if the root context closes before the child context and releases the root-created server, the child exporter may lose the registry infrastructure it is still using.

There are two design directions:

- Place the server in a layer with a longer lifecycle than every context using it; child contexts only reference/borrow the server.
- Create a dedicated server for each context so closing one context does not affect the other context's registry.

In either direction, define the `ObjectName` and owner of each registration. Using `RegistrationPolicy.IGNORE_EXISTING` to mask name conflicts does not solve lifecycle issues if remaining contexts depend on a server that has already been released.

## 9. Custom Server and JConsole: Why Might It Not Be Visible?

The platform `MBeanServer` is where JConsole normally displays platform MXBeans and many managed JVM objects. A custom server created by the application may **not be automatically selected or listed by a local JConsole connection's MBean viewer in the way you expect**.

The fact that `server.isRegistered(name)=true` on a custom server does not prove JConsole is connected to that exact server.

When diagnosing:

1. Check which `MBeanServer` is injected into the exporter.
2. Check `isRegistered(name)` on **that exact server**.
3. Identify which server the connector/client is connecting to.
4. If remote management of the custom server is needed, create and manage an appropriate `JMXConnectorServer` attached to that server.
5. Control transport, authentication, and networking before opening a JMX endpoint.

If the goal is simply to view MBeans with local JConsole by process, using the platform server is usually less complex. A custom server is useful when registry isolation, lifecycle isolation, or special management requirements are needed, but client connectivity must be intentionally designed.

## 10. JMXConnectorServer Has Its Own Lifecycle

`MBeanServer` manages the registry; `JMXConnectorServer` provides an endpoint for clients to connect over a protocol such as JMX RMI. The two components are not the same.

```text
ApplicationContext
   |
   +-- MBeanServer (registry)
   |
   +-- MBeanExporter (register MBeans)
   |
   +-- JMXConnectorServer (network endpoint)
              |
              v
        Remote JMX clients
```

If the application creates a connector for a custom server, it must be started/stopped with the application lifecycle. Do not assume `MBeanServerFactoryBean` automatically creates and manages a remote connector.

A lifecycle wrapper bean can execute `connector.start()` during the start phase and `connector.stop()` on destroy. With Spring, `@Bean(initMethod="start", destroyMethod="stop")` can be used if the object and endpoint configuration meet requirements, or `SmartLifecycle` can be implemented for complex start/stop ordering and state.

Opening remote JMX carries high administrative risk because it can allow reading attributes or invoking operations with side effects. Authentication, encryption, and environment-appropriate network access control are required. Do not expose a management endpoint to a public network just for testing.

## 11. Cleaning Up MBeans on Context Close and Ownership Issues

`MBeanExporter` normally manages unregistering the MBeans that it registered itself. When multiple exporters share a server, each exporter needs clear responsibility for its own `ObjectName` entries.

Example:

```text
Exporter A -> com.example:type=Cache,name=primary
Exporter B -> com.example:type=Cache,name=secondary
```

If both are registered successfully, closing the context containing exporter A should only remove MBean A, and must not arbitrarily remove B.

If two exporters try to register under the same name, the registration policy (`FAIL_ON_EXISTING`, `IGNORE_EXISTING`, `REPLACE_EXISTING`) affects ownership and cleanup. In particular, `REPLACE_EXISTING` can alter the MBean residing under the same name, while `IGNORE_EXISTING` can leave the new exporter without true ownership of that registration.

Therefore, before handling complex lifecycle scenarios, use a naming strategy that produces unique `ObjectName` values. Registration policy is not a replacement for owner management.

## 12. Testing with a Dedicated Server Without Polluting the Platform Registry

An integration test can create a dedicated `MBeanServer` for a fixture and release it upon completion.

JUnit example:

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class CustomMBeanServerLifecycleTest {

    @Test
    void contextRegistersAndUnregistersMBeans() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("isolated-test");

        ObjectName name = new ObjectName(
                "com.example.management:type=JobMonitor,name=primary");

        try {
            try (var context = new AnnotationConfigApplicationContext()) {
                context.registerBean(
                        "externalTestServer",
                        MBeanServer.class,
                        () -> server);

                context.registerBean(JobMonitor.class);

                context.registerBean(
                        MBeanExporter.class,
                        () -> {
                            MBeanExporter exporter = new MBeanExporter();
                            exporter.setServer(server);
                            exporter.setBeans(
                                    java.util.Map.of(
                                            name.toString(),
                                            context.getBean(JobMonitor.class)));
                            return exporter;
                        });

                context.refresh();

                assertTrue(server.isRegistered(name));
            }

            assertFalse(server.isRegistered(name));
        } finally {
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

This example illustrates managing **the server outside** the Spring context, while the exporter is managed by the container. When the context closes, the exporter unregisters the MBean; finally the test releases the server it created itself. The primary goal is separating the two cleanup obligations.

When applying this, use bean registration methods appropriate for your Spring version, ensuring the exporter has clear dependencies on the managed bean and server. If the Spring context also has an automatic MBean exporter, remove or isolate that mechanism in the test to avoid duplicate registrations.

## 13. How to Test the Lifecycle of MBeanServerFactoryBean

Another test may use a server created and managed by the Spring factory. Because after `context.close()` the server may already have been released, do not rely solely on `server.isRegistered(...)` to conclude the server disappeared from the factory registry.

You can check the list of servers tracked by `MBeanServerFactory`, while avoiding confusion from identical default domains or other pre-existing servers. Isolated tests should have a dedicated domain:

```java
MBeanServer server;
try (var context = new AnnotationConfigApplicationContext(
        CustomJmxConfiguration.class)) {
    server = context.getBean(
            "applicationMBeanServer", MBeanServer.class);
    // assert registered ...
}
// After context closes, it is no longer managed by the Spring factory.
// If needed, inspect MBeanServerFactory's registry by server identity.
```

Having `releaseMBeanServer` remove the server from the JMX factory's managed list does not require the Java object to be GC'd immediately. Therefore, lifecycle tests must verify **contractual cleanup**, not physical disappearance of the object.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Custom server not visible in JConsole | JConsole connects to platform server, not custom server | Query the right server or configure a connector to the custom server |
| MBean still appears after Spring context closes | Another exporter owns the name or context did not close | Check lifecycle, owner, and which server is being read |
| Server released while another context still uses it | Ownership placed at the wrong layer | Move server to a longer-lived scope or separate servers |
| Registry exists but MBean disappears | Exporter unregistered on context close | Check context closing order |
| Test passes alone, fails in parallel | Shared platform server/`ObjectName` | Create dedicated server, separate domain/instance name |
| Error releasing server | Not in factory registry, already released, or wrong ownership | Only release servers created and managed by the component |
| `InstanceAlreadyExistsException` | Two exporters use the same `ObjectName` | Fix naming strategy, owner, and registration policy |
| MBean not seen even though exporter exists | Exporter uses a different server or bean not in mapping | Check injected server and `setBeans` |
| Context cannot shut down cleanly | Connector not stopped, tasks still running, or wrong cleanup order | Design lifecycle for connector and dependencies |
| Multiple servers created unintentionally | Factory defaults to creating new across multiple contexts | Use a shared server with clear owner or enable appropriate lookup |

## 15. Principles for Sustainable Lifecycle Design

1. **Define ownership from the start.** Whoever creates a server is responsible for releasing it, unless lifecycle is explicitly handed over.
2. **Distinguish borrowed servers from newly created servers.** Never release the JVM's platform server simply because a Spring context closes.
3. **Inject the server into the exporter.** Avoid having the exporter pick a server different from the one verification code or connectors use.
4. **Use one owner per `ObjectName`.** Multiple exporters can share a server, but should not register duplicate names.
5. **Leverage Spring destroy callbacks.** Ensure exporters unregister before the owner releases the server.
6. **Manage connectors separately.** Remote connectors have independent start/stop from the registry.
7. **Avoid arbitrary static server references.** Static references can extend lifecycles beyond the Spring context and cause resource leaks.
8. **Isolate tests.** Dedicated servers and JMX names prevent cross-test interference.
9. **Verify against the right JVM/server when debugging.** `isRegistered` on the platform server cannot prove custom server state.
10. **Verify shutdown.** After closing the context, verify exporter MBeans are unregistered and the server owner performed contractual cleanup.

## 16. Practice Exercises

**Exercise 1 — Dedicated server.** Create an `MBeanServerFactoryBean` with domain `training.jmx`, and register `JobMonitor` via `MBeanExporter`. Use the server API to verify the `ObjectName` exists, then close the context.

**Exercise 2 — Comparing platform vs. custom.** Register an MBean only in a custom server. Run `ManagementFactory.getPlatformMBeanServer().isRegistered(name)` and custom `server.isRegistered(name)`. Explain the difference.

**Exercise 3 — Two contexts.** Create a custom server in a root context, have a child context use the same server with a different `ObjectName`. Close the child before the root; verify only MBeans managed by the child exporter are unregistered.

**Exercise 4 — Wrong ownership.** Design a fixture that intentionally releases the server before the exporter closes. Observe the consequence and fix the dependency graph so the exporter is destroyed before the server owner.

**Exercise 5 — Remote connector lifecycle.** Sketch a `JMXConnectorServer` managed by `SmartLifecycle`. List the start, stop, authentication, and connection-verification steps needed before using it in a real environment.

## Conclusion

Managing a custom `MBeanServer` lifecycle in Spring Framework means clearly distinguishing **who creates the server, who uses it, who registers MBeans, and who is responsible for cleanup**. `MBeanServerFactoryBean` brings custom server lifecycle into `ApplicationContext`, while `MBeanExporter` manages registration of exported managed beans. When using a shared server, multiple contexts, or remote JMX connectors, ownership and shutdown order must be designed clearly to avoid lost MBeans, duplicate registrations, resource leaks, or management tools reading the wrong registry.
