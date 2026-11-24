# Impact of Classloaders and Multiple Applications in One JVM When Using a Custom MBeanServer

## 1. Context and Objectives

In Java, a single JVM can run multiple applications, multiple modules, multiple Spring `ApplicationContext` instances, or multiple deployments of the same application. Each application may have its own `ClassLoader`. When these applications all use Java Management Extensions (JMX), choosing between a **shared MBeanServer and a custom MBeanServer** determines not only where MBeans are registered, but also affects `ObjectName` uniqueness, object lifecycle, metadata access, cleanup on redeploy, and observability boundaries.

A Spring Framework application can use `MBeanExporter` to publish management beans to an MBeanServer. In simple cases, the exporter uses the platform MBeanServer. With multiple applications in the same JVM — such as an application server hosting multiple WARs, multiple Spring contexts, or a plugin host dynamically loading modules — that configuration requires more careful consideration.

After this lesson, you will be able to:

- Distinguish **MBeanServer namespaces** from **ClassLoader namespaces**.
- Understand why classes with the same name loaded by two classloaders can be two different Java types.
- Identify `ObjectName` collisions when multiple applications register MBeans into one server.
- Understand reference-retention risks causing **classloader leaks** during undeploy/redeploy.
- Choose between a platform/shared MBeanServer and a dedicated MBeanServer based on operational needs.
- Configure Spring `MBeanExporter` and `MBeanServerFactoryBean` with clear ownership.
- Build a verification workflow for registration, unregistration, and JMX connectivity in multi-application environments.

## 2. What is a Classloader and Why Does It Affect JMX?

Java's `ClassLoader` is responsible for loading class definitions. Inside the JVM, a class's identity depends not only on its fully qualified name, but also on **the classloader that defined it**.

Example:

```text
JVM
├── Shared / parent classloader
│   └── javax.management.MBeanServer
├── Application A classloader
│   └── com.example.monitoring.CacheMonitor
└── Application B classloader
    └── com.example.monitoring.CacheMonitor
```

Two `com.example.monitoring.CacheMonitor` classes with the same name but defined by two independent application classloaders **are not necessarily the same runtime type**.

This matters when JMX introspection inspects an MBean's interface, when clients access custom data types, and when a server retains references to an MBean after an application is undeployed.

### 2.1. Example: Same Name, Different Loaders

```java
Class<?> a = applicationALoader.loadClass(
    "com.example.monitoring.CacheMonitor");

Class<?> b = applicationBLoader.loadClass(
    "com.example.monitoring.CacheMonitor");

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b); // May be false
```

If each loader actually defines this class separately, `a == b` is `false`. An object created by loader A cannot implicitly be cast to the same class name defined by loader B.

The `javax.management` API itself belongs to the Java platform, so multiple applications can interact with it together. However, MBean implementations, custom management interfaces, `NotificationListener` instances, and much of the data passed through JMX often carry classes or objects loaded by application loaders.

## 3. MBeanServer Is Not Synonymous with ClassLoader

`MBeanServer` is the management registry in JMX. It stores MBeans by `ObjectName` and serves operations, attributes, and notifications.

`ClassLoader` is the class-loading component. The two concepts belong to different axes:

| Aspect | MBeanServer | ClassLoader |
| --- | --- | --- |
| Role | MBean registry and management API | Loads, links, and identifies classes |
| Primary identifier | `ObjectName` within one server | Class name combined with defining loader |
| Can be shared across apps? | Yes | Can have a shared loader or separate loaders |
| Lifecycle relation | Register/unregister MBeans | Loads classes; can be GC'd when no references remain |
| Common errors | Duplicate `ObjectName`, wrong server, MBean not found | `ClassCastException`, `ClassNotFoundException`, leaks on redeploy |

One MBeanServer can register MBeans coming from multiple classloaders. Conversely, one application using one classloader can register MBeans into multiple MBeanServers. **There is no mandatory one-to-one relationship.**

### 3.1. Two Applications Sharing the Platform MBeanServer

```text
Application A (ClassLoader A) --+
                                +--> Platform MBeanServer
Application B (ClassLoader B) --+         |
                                          +-- A MBeans
                                          +-- B MBeans
```

This is convenient for management tools: one connector can see MBeans registered by both applications into the same server. However, the ObjectName namespace is shared, so the two applications must avoid name collisions.

### 3.2. Each Application Using a Dedicated Server

```text
Application A --> MBeanServer A --> A MBeans
Application B --> MBeanServer B --> B MBeans
```

The two servers have independent registries. The same ObjectName can appear in both without collision. However, JConsole or clients connecting to the platform server **do not automatically see** dedicated servers: an appropriate access path is needed. Creating a dedicated server does not automatically enable a JMX Remote connector.

## 4. ObjectName Collisions Across Multiple Applications

In JMX, an ObjectName can only be registered to one MBean at a time **within a single MBeanServer**.

Suppose applications A and B both export:

```text
com.example.app:type=CacheMonitor,name=Main
```

If both use the platform server, the application registering later may receive `InstanceAlreadyExistsException`. The fact that the two MBean implementations are loaded by different classloaders **does not make their ObjectNames different**.

Example:

```java
ObjectName name = new ObjectName(
    "com.example.app:type=CacheMonitor,name=Main");

server.registerMBean(mbeanFromAppA, name);
server.registerMBean(mbeanFromAppB, name);
// The second call fails because the ObjectName already exists.
```

To avoid duplicates, establish a namespace convention including the application, module, or instance name:

```text
com.example.applicationA:type=CacheMonitor,name=Main
com.example.applicationB:type=CacheMonitor,name=Main
```

or:

```text
com.example.platform:type=CacheMonitor,app=orders,name=Main
com.example.platform:type=CacheMonitor,app=inventory,name=Main
```

Domains and key properties are application conventions; Java does not automatically add a classloader ID to ObjectNames. If multiple deployments share a JVM, assign a stable instance identifier that contains no secrets.

### 4.1. Same ObjectName in Two Dedicated Servers

```java
MBeanServer a =
    MBeanServerFactory.newMBeanServer("com.example.app");

MBeanServer b =
    MBeanServerFactory.newMBeanServer("com.example.app");

ObjectName sameName = new ObjectName(
    "com.example.app:type=CacheMonitor,name=Main");
```

You can register compatible MBeans under that name in both servers because their registries are independent. To identify a management target on a multi-server dashboard, the real identity must include both **connection/server identity** and ObjectName, not ObjectName alone.

## 5. Classloader Leaks on Undeploy or Redeploy

A prominent risk of JMX in application servers is **MBeans remaining registered after an application has stopped**.

An MBean registered in a server that outlives the application can retain references to:

- The MBean instance defined by the application classloader.
- Services, caches, executors, callbacks, and dependencies held by the MBean.
- Classes and metadata of the application layer.
- A `NotificationListener`, filter, or handback created by the application.
- Threads, timers, or auxiliary resources belonging to the application.

If references remain reachable from the platform/shared MBeanServer, the old classloader may not be garbage-collected after undeploy. When an application is redeployed multiple times, multiple old classloaders can remain alive, increasing memory usage and causing hard-to-diagnose errors.

```text
Platform MBeanServer (lives for JVM lifetime)
        |
        +--> Old MBean (forgotten to unregister)
                  |
                  +--> Old application service
                  |        |
                  |        +--> Old ClassLoader
                  |
                  +--> Old listener / callback
```

This is an example of a **classloader leak**: the persistence of an MBean in a shared registry can retain the entire object graph of a previous deployment.

Not every surviving `ClassLoader` is a leak; evidence is needed that old objects/loaders are still retained beyond their expected lifecycle. Nevertheless, unregistering MBeans promptly is an essential preventive measure.

### 5.1. Common Symptoms

- Several redeploys cause heap or metaspace to grow without a corresponding drop after GC.
- MBeans from an old deployment still appear in JConsole.
- `InstanceAlreadyExistsException` occurs immediately when deploying the new version.
- Old notification listeners keep processing events.
- Logs from the old classloader still appear after undeploy.
- Threads or timers belonging to the old module keep running.

These symptoms can have causes other than JMX. When investigating, inspect the MBean registry, listeners, threads, classloaders, and heap reference graph rather than jumping to conclusions solely from rising memory.

## 6. Role of Spring MBeanExporter in the Lifecycle

Spring `MBeanExporter` normally participates in the `ApplicationContext` lifecycle: registering MBeans on initialization and removing the registrations managed by the exporter when the context closes.

Configuration example:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfig {

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            CacheMonitor cacheMonitor,
            MBeanServer mbeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(
            "com.example.applicationA:type=CacheMonitor,name=Main",
            cacheMonitor
        ));
        return exporter;
    }
}
```

The example assumes `CacheMonitor` is a valid Standard MBean or configured with an appropriate assembler. If the context closes properly, the exporter gets the chance to clean up its registrations.

**Do not rely solely on the JVM shutting down.** In an application server, a WAR or a Spring context can be undeployed while the JVM and platform MBeanServer stay alive. Registration cleanup must be tied to the application lifecycle.

### 6.1. When Is the Exporter Not Enough?

MBeans registered **outside** `MBeanExporter` may not be automatically managed by the Spring exporter. Example:

```java
server.registerMBean(customMBean, customName);
```

If this code runs manually, the code owning the registration must ensure `unregisterMBean` is called when the module stops.

Similarly, a listener added by other code to a broadcaster or a manually created remote connector also needs to be removed/stopped according to its own lifecycle. Closing `ApplicationContext` does not implicitly clean up resources created outside Spring.

## 7. Shared MBeanServer or Custom Server?

### 7.1. Using a Shared/Platform MBeanServer

Pros:

- JVM management tools can access application MBeans alongside platform MXBeans.
- Little need for separate connector or discovery configuration.
- Unified observation of multiple modules in the same JVM.
- Makes sense when you want a single shared management surface.

Cons:

- Shared ObjectName namespace; name collisions are easier.
- Forgotten MBeans can retain the classloader of a stopped application.
- Must clearly define who owns each ObjectName registration.
- An overly broad JMX account can see multiple applications without proper authorization.

### 7.2. Using a Dedicated MBeanServer

Pros:

- Independent registry, reducing ObjectName collisions with other applications.
- Can manage server/connector at the application scope.
- Useful for tests, plugins, or environments needing separated management systems.

Cons:

- Clients must know to connect to the dedicated server; JConsole connected to the platform server will not automatically see these MBeans.
- Must manage server lifecycle and any related connectors.
- Multiple servers complicate discovery, monitoring, and alert configuration.
- Does not automatically guarantee security isolation or eliminate classloader leaks if references remain from shared components.

**Design conclusion:** a dedicated server is a tool for organizing registries, not a complete replacement for managing ObjectNames, lifecycles, and classloaders.

## 8. Creating a Dedicated Server with MBeanServerFactoryBean

Spring provides `org.springframework.jmx.support.MBeanServerFactoryBean` to supply an MBeanServer through the container.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class PrivateServerConfig {

    @Bean
    public MBeanServerFactoryBean privateJmxServer() {
        MBeanServerFactoryBean factory =
            new MBeanServerFactoryBean();

        factory.setDefaultDomain("com.example.private");
        factory.setLocateExistingServerIfPossible(false);
        factory.setRegisterWithFactory(false);
        return factory;
    }
}
```

The configuration above requests creating a new MBeanServer and not registering it in `MBeanServerFactory`'s lookup list. This reduces the risk of another component accidentally sharing the server via factory lookup. However, if a shared singleton or JMX connector still holds the server after the application context closes, the server and its MBeans can remain alive.

To export to the dedicated server, `MBeanExporter` must receive the exact `MBeanServer`:

```java
@Bean
MBeanExporter privateExporter(
        CacheMonitor monitor,
        MBeanServer privateJmxServer) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(privateJmxServer);
    exporter.setBeans(Map.of(
        "com.example.private:type=CacheMonitor,name=Main",
        monitor
    ));
    return exporter;
}
```

When the context has multiple beans of type `MBeanServer`, use `@Qualifier` or bean names to pick the exact instance. Do not rely on automatic server selection in an arbitrary order.

### 8.1. createMBeanServer and newMBeanServer

The JMX API provides:

```java
MBeanServer registered =
    MBeanServerFactory.createMBeanServer("com.example.registered");

MBeanServer unregistered =
    MBeanServerFactory.newMBeanServer("com.example.private");
```

`createMBeanServer` adds the new server to the list tracked by `MBeanServerFactory`; `newMBeanServer` creates a server without adding it to that list. Neither automatically creates a remote connector.

Do not view `newMBeanServer` as an automatic solution for classloader isolation. Memory reclaimability depends on the entire reference graph, not just whether the server is in the factory's list.

## 9. Classloader Repository and JMX Introspection

JMX has class-loading and introspection mechanisms related to MBeans. `MBeanServer` supports `ClassLoaderRepository` and operations for loading classes in defined JMX scenarios.

This is especially important when:

- An MBean is loaded through an application classloader while the server resides in a shared layer.
- JMX needs to introspect interfaces or method signatures.
- MBean operations use application classes as parameter/return types.
- A JMX client from another JVM lacks the corresponding classes.
- Two versions of the same class name exist across different applications.

The JMX API does not erase Java class identity boundaries. The same class name in two loaders remains two different definitions when not shared via delegation.

### 9.1. Standard MBeans and Interface Classloaders

A Standard MBean is recognized by interface convention, for example:

```java
package com.example.monitoring;

public interface CacheMonitorMBean {
    long getHitCount();
}
```

```java
package com.example.monitoring;

public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public long getHitCount() {
        return 0L;
    }
}
```

For a class to implement an interface with matching Java type identity, the interface it implements must align with classloader resolution. If two applications both carry copies of `CacheMonitorMBean`, they may be two distinct classes despite having the same name.

When MBean introspection fails, inspect not only the interface name but also which classloader actually defines the class and its dependency versions. Do not treat a `ClassCastException` between two classes with the same name as impossible.

### 9.2. Avoiding Custom DTO Types in Remote JMX

An MBean operation using an application-specific type:

```java
public CustomerOrderSummary getSummary();
```

may require the JMX client to know the class, matching package, version, and corresponding serialization contract. With multiple application classloaders, this easily becomes complex and hard to maintain.

For a stable management interface, prefer primitives, wrappers, `String`, `CompositeData`, `TabularData`, or appropriate Open MBean types. Do not export an entire domain entity whose structure depends on many application classes if the goal is simply monitoring.

## 10. Listeners and Cross-Application References

Notification listeners can create long reference chains that outlive the intended lifecycle.

Example:

```java
NotificationListener listener =
    (notification, handback) -> monitoringService.onEvent(notification);

server.addNotificationListener(
    objectName, listener, null, null);
```

If `monitoringService` belongs to application A, the listener lambda can retain a reference to service A. If the broadcaster MBean remains on the shared server after A is undeployed, this reference can retain classloader A.

When cleaning up:

```java
server.removeNotificationListener(objectName, listener);
```

However, this call only succeeds while the listener and MBean are still registered accordingly. If the MBean was already unregistered, removal may encounter `InstanceNotFoundException`. Organize cleanup in a logical order, catch cleanup errors selectively, and retain the original listener identity.

Be careful with other reference sources:

- Handback objects passed when registering listeners.
- Executors holding tasks or callbacks belonging to the application.
- Timers, schedulers, and thread-locals.
- Static collections in shared libraries storing application classes/instances.
- An MBeanServer or connector placed inside a JVM-lifetime singleton.

Registering listeners and MBeans from multiple applications requires a clear contract on who removes them upon termination.

## 11. Context Classloader and Thread Context Classloader

In Java, `Thread.currentThread().getContextClassLoader()` (TCCL) can affect class loading by certain frameworks or libraries. Application servers and some integrations may set TCCL to the application's loader before invoking code.

When a management operation is invoked from a JMX connector thread or background code, TCCL may differ from a normal request thread. A bean relying on TCCL to load resources, drivers, or service providers may behave differently when invoked via JMX.

Observational example:

```java
@ManagedOperation(description = "Print diagnostic classloader info")
public String classLoaderInfo() {
    ClassLoader ownLoader = getClass().getClassLoader();
    ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();

    return "own=" + ownLoader + ", context=" + contextLoader;
}
```

This is only a diagnostic example, not a recommendation to log every classloader structure in production. Do not arbitrarily change TCCL inside an operation and forget to restore it; if an operation must run with a specific loader, design it carefully and restore in `finally`.

Not every JMX operation changes TCCL; exact behavior depends on the connector, framework, and runtime environment. What must be verified is that **the management invocation path may differ from a normal HTTP/request thread**.

## 12. Multiple Applications in One JVM: Security Boundaries

One JVM hosting multiple applications does not mean the applications are security-isolated at the process level. If applications share an MBeanServer and a JMX client has broad administrative privileges, that client can observe or invoke operations on MBeans of multiple applications.

ObjectName domains and key properties **do not automatically create access control**:

```text
com.example.appA:type=CacheMonitor,name=Main
com.example.appB:type=CacheMonitor,name=Main
```

Two different domains help identify and avoid name collisions, but do not guarantee that a user allowed to access appA will be denied appB.

Keep in mind:

1. Remote JMX must be protected with appropriate authentication and transport security.
2. Access permissions to MBeans/operations must be based on real policies, not inferred from name prefixes.
3. Do not export dangerous operations just because users "only connect internally".
4. Do not return sensitive data of another application through attributes or notifications.
5. A dedicated server can narrow connector scope if deployed properly, yet still requires permission and lifecycle controls.

For mutually untrusted applications, process/JVM isolation generally provides a stronger boundary than merely separating MBeanServers within the same JVM.

## 13. Safe Deploy, Redeploy, and Undeploy Procedure

An operational procedure should include these steps:

### On Initialization

1. Choose the MBeanServer explicitly: platform, container-managed, or dedicated.
2. Assign domains and ObjectNames distinguishing application, module, and instance.
3. Initialize beans and exporters.
4. Register MBeans or let `MBeanExporter` manage registration.
5. Verify `isRegistered(ObjectName)` on the right server.
6. Register required notification listeners; record ownership for later removal.

### On Stop or Redeploy

1. Stop task sources or callbacks that could generate new registrations.
2. Remove listeners owned by the application.
3. Close the Spring `ApplicationContext` per its lifecycle.
4. Ensure manually registered MBeans are unregistered.
5. Stop connectors/executors/threads created by the application.
6. Verify no ObjectNames from the old deployment remain on the shared server.
7. Investigate if the old classloader is still referenced or if old MBeans still exist.

If the application uses a dedicated server, determine who holds references to that server after stopping. A new server created by an application context can be garbage-collected once no references point to it; however, if a singleton or connector still holds the server, the risk persists.

### 13.1. Code Cleanup When Registering Manually

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class ManualJmxRegistration
        implements AutoCloseable {

    private final MBeanServer server;
    private final ObjectName name;
    private boolean registered;

    public ManualJmxRegistration(
            MBeanServer server, ObjectName name, Object mbean)
            throws Exception {
        this.server = server;
        this.name = name;
        server.registerMBean(mbean, name);
        registered = true;
    }

    @Override
    public synchronized void close() throws Exception {
        if (!registered) {
            return;
        }
        if (server.isRegistered(name)) {
            server.unregisterMBean(name);
        }
        registered = false;
    }
}
```

This illustrates simple ownership. In concurrent environments, `isRegistered` followed by `unregisterMBean` is not an atomic transaction; another MBean could replace the registration between the two calls. Therefore, production cleanup must preserve strict ownership and avoid unregistering another component's MBean.

## 14. Verifying on the Right Server and Right Classloader

### 14.1. Checking the JMX Registry

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.applicationA:type=CacheMonitor,name=Main");

System.out.println(server.isRegistered(name));
```

If false:

- The exporter may not have run yet.
- The actual ObjectName may differ.
- The bean may already have been unregistered.
- You may be checking the wrong MBeanServer.
- Classloader or metadata configuration may have caused export to fail.

If true yet attributes cannot be accessed, proceed to check `MBeanInfo` and permissions/data types.

### 14.2. Printing Classloader Info During Diagnostics

```java
Class<?> type = monitor.getClass();
ClassLoader loader = type.getClassLoader();

System.out.println("MBean class=" + type.getName());
System.out.println("ClassLoader=" + loader);
```

In Spring AOP, `getClass()` may be a proxy class, so you may need to check the target class to identify the application's loader. Loader details should be used in controlled diagnostics and not arbitrarily exposed as a public endpoint.

### 14.3. Inspecting JMX Metadata

```java
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);
System.out.println(info.getClassName());
System.out.println(info.getDescription());
```

`MBeanInfo.getClassName()` is the class name published by metadata, not sole proof of which classloader loaded the instance. Two applications can have the same class name in metadata yet use different loaders.

## 15. Common Errors

| Symptom | Possible Cause | Approach |
| --- | --- | --- |
| `InstanceAlreadyExistsException` on redeploy | Old MBean not unregistered or ObjectName collision | Identify owner, check lifecycle, design instance key |
| MBean registered but JConsole does not see it | Exporter uses dedicated server; JConsole connects to platform server | Verify connector and target MBeanServer |
| `ClassNotFoundException` on operation call | Custom data type absent in client/loader | Use appropriate JMX/Open MBean types |
| `ClassCastException` between classes with the same name | Two classloaders define the class separately | Check loaders, versions, and dependencies |
| Heap/metaspace grows after redeploy | MBean/listener/thread retains old loader | Inspect heap reference graph and cleanup |
| Old listener keeps receiving notifications | Listener not removed or broadcaster still alive | Manage listener ownership/lifecycle |
| MBean operation behaves differently from HTTP request | Different TCCL, thread context, or security context | Check assumptions about invocation environment |
| Memory still leaks despite dedicated server | Connector/static reference holds server/bean | Stop connector and release references |

These errors can occur independently or simultaneously. Do not use "creating a dedicated MBeanServer" as a cure-all for classloader errors.

## 16. Practice Exercises

Suppose a JVM contains two Spring contexts, each creating a `CacheMonitor`.

### Part A — Same Platform MBeanServer

1. Configure both contexts A and B to use `ManagementFactory.getPlatformMBeanServer()`.
2. Have both attempt to export ObjectName `com.example.shared:type=CacheMonitor,name=Main`.
3. Observe the second registration being rejected or the exporter encountering a duplicate-name error.
4. Fix by adding `app=A` and `app=B` in the key properties.
5. Use `queryNames("com.example.shared:type=CacheMonitor,*")` to list both instances.

### Part B — Dedicated Servers

1. Create servers A and B using `MBeanServerFactory.newMBeanServer(...)` or Spring `MBeanServerFactoryBean`.
2. Export each `CacheMonitor` into its corresponding server.
3. Try using the exact same ObjectName in both servers.
4. Confirm each server has its own registry with no collision.
5. Explain why a JMX client connected only to the platform server does not automatically find the two MBeans on the dedicated servers.

### Part C — Lifecycle

1. Record the ObjectName owned by each context.
2. Close context A and confirm the MBean belonging to A is removed from the shared server.
3. Ensure listeners and connectors created by A are cleaned up.
4. Restart context A with the same ObjectName and observe no conflict remains if cleanup succeeded.
5. Use a profiler if needed to inspect loaders and object graphs of the old deployment.

An illustration of isolated registries:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer a = MBeanServerFactory.newMBeanServer("com.example.a");
MBeanServer b = MBeanServerFactory.newMBeanServer("com.example.b");

ObjectName name = new ObjectName(
    "com.example.shared:type=CacheMonitor,name=Main");

a.registerMBean(new CacheMonitor(), name);
b.registerMBean(new CacheMonitor(), name);

System.out.println(a.isRegistered(name)); // true
System.out.println(b.isRegistered(name)); // true
```

To run the illustration, `CacheMonitor` must be a valid MBean and you must handle lifecycle, errors, and cleanup appropriately in a real program.

## 17. Self-Check Questions

**1. Are two classes with the same package and name always the same runtime type?** No. Defining classloaders may differ.

**2. Is an ObjectName unique across all MBeanServers in a JVM?** No; it is unique within each server.

**3. Why do two applications sharing the platform MBeanServer easily hit duplicate-name errors?** Because both share the same ObjectName registry.

**4. Does a dedicated MBeanServer automatically solve classloader leaks?** No; references, listeners, connectors, and lifecycles still must be managed.

**5. Why can an MBean still registered after undeploy retain the old classloader?** Because the shared server still holds a reference to the MBean and the application's object graph.

**6. How does `MBeanExporter` help when a Spring context closes?** It manages unregistering MBeans owned by the exporter according to the context lifecycle.

**7. Why is `MBeanInfo.getClassName()` insufficient to prove which classloader loaded an MBean?** Because it only reports the class name in metadata, without identifying the loader.

**8. Does using different domains automatically separate access permissions?** No; a domain is only an identifier and namespace grouping.

**9. If a JMX client uses a remote connector with custom DTOs, what must be considered?** Class availability, serialization, versions, and appropriate management data types.

**10. After redeploy, what should be checked?** Old ObjectNames, listeners, connectors, threads, reference graphs, and classloader reclaimability.

## 18. Key Takeaways

- **Class identity** depends on the class name **and the defining classloader**.
- **MBeanServer** is a JMX registry, not a classloader; one server can hold MBeans from multiple applications.
- **ObjectName is unique only within one MBeanServer**, so multiple applications sharing a server need clear namespace/instance keys.
- **Shared platform server** is convenient for monitoring yet requires strict ownership and cleanup.
- **Private MBeanServer** separates registries, but does not automatically enable a remote connector or guarantee security isolation.
- **MBeans, listeners, and connectors still alive after undeploy** can retain old classloaders, causing memory leaks.
- **Spring MBeanExporter** assists the register/unregister lifecycle yet does not automatically clean up resources created outside Spring.
- **Classloader/TCCL** can affect introspection, data types, callbacks, and operation calls from JMX.
- Verify on the **exact MBeanServer**, with the exact ObjectName, and manage ownership clearly both at registration and on application shutdown.

Separating MBeanServer, ObjectName, classloader, and lifecycle allows running multiple Spring applications in the same JVM consistently, while limiting risks of name collisions, class-loading errors, and retained resources after redeploy.