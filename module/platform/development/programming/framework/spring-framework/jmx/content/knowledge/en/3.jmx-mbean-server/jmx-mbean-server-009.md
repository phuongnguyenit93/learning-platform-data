# Managing the MBeanServer Lifecycle in Spring Framework Applications

## Learning Objectives

`MBeanServer` is the heart of a **JMX agent** in a JVM: the place where managed MBeans are registered, looked up, and invoked. With the Spring Framework, the challenge is not only "getting an `MBeanServer`" but also determining **who creates it**, **who owns it**, **who registers MBeans**, **who cleans up on stop**, and what happens when the application is restarted in the same JVM.

After this lesson, you will be able to:

- Distinguish the lifecycles of `MBeanServer`, Spring `ApplicationContext`, exported MBeans, and remote JMX connectors.
- Decide when to use the platform `MBeanServer`, locate an existing server, or create a separate server.
- Explain the roles of Spring's `MBeanServerFactoryBean`, `MBeanExporter`, and unregistration mechanisms.
- Design registration, unregistration, and `ObjectName` checks to avoid collisions and resource leaks.
- Handle startup/shutdown, context refresh, multi-context deployments, test suites, and embedded applications.
- Distinguish verified lifecycle state from assumptions based on a single call or configuration.

## 1. Mental Model: MBeanServer Is a JVM-Scoped Registry, Not Tied by Default to Spring's Lifecycle

In JMX, an `MBeanServer` manages the mapping between `ObjectName`s and registered MBean objects. Management clients use `MBeanServerConnection` to query metadata, read attributes, invoke operations, and receive notifications according to each MBean's capabilities.

Simplified model:

\`\`\`text
JVM
├── Platform MBeanServer (shared)
│   ├── java.lang:type=Memory
│   ├── java.lang:type=Threading
│   ├── domain.application:type=Cache,name=ProductCache
│   └── domain.application:type=Worker,name=ImportWorker
│
├── Spring ApplicationContext A
│   ├── Spring bean: CacheMonitor
│   └── MBeanExporter A ── registers/unregisters A's MBeans
│
├── Spring ApplicationContext B
│   ├── Spring bean: WorkerMonitor
│   └── MBeanExporter B ── registers/unregisters B's MBeans
│
└── JMX Connector (optional)
    └── Provides remote access to an MBeanServer
\`\`\`

The lifecycles are related yet **not identical**:

| Component | When Is It Typically Created? | Who Is Responsible for Cleanup? |
|---|---|---|
| Platform `MBeanServer` | Via `ManagementFactory.getPlatformMBeanServer()` or initialized by runtime when needed | JVM/runtime; an application context normally does not destroy this server |
| Separate `MBeanServer` | When an application/management framework explicitly creates it | The component owning the server; can be released via `MBeanServerFactory` if managed by the factory |
| Spring `ApplicationContext` | During application bootstrap | Context closing mechanism; invokes destroy/disposable callbacks |
| `MBeanExporter` | When the context creates the export bean | The exporter normally cleans up registrations it manages upon destruction |
| MBean | When registered under an `ObjectName` | The component that registered it / holds registration ownership |
| JMX connector | When the management endpoint is started | The component that started the connector must stop/close it properly |

Always ask: **"Does this resource belong to the JVM, the Spring context, the exporter, or an infrastructure service?"** Failing to answer this often leads to two opposite mistakes: failing to clean up the registry when closing a context, or accidentally destroying a shared server.

## 2. Ways to Obtain MBeanServer and Their Lifecycle Implications

### 2.1 Using the Platform MBeanServer

This is the natural choice when sharing the space where the JVM publishes platform MXBeans for memory, threads, garbage collection, class loading, and runtime:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
\`\`\`

Key characteristics:

- Calling `getPlatformMBeanServer()` again gives access to the same JVM's platform server; do not treat each call as a new caller-owned server.
- Application MBeans can be registered into this server with their own `ObjectName`.
- When an `ApplicationContext` stops, it must not arbitrarily release the shared server just to remove application MBeans.
- Multiple Spring contexts and libraries can register MBeans on one platform server. Namespacing and ownership are prerequisites.

Example of a suitable name:

\`\`\`text
com.example.orders:type=Worker,name=ImportWorker,instance=node-01
\`\`\`

Actual names should be stable, sufficiently unique within the `MBeanServer`, and free of sensitive data or arbitrary random values that change without reason. `ObjectName` has its own syntax; use `new ObjectName(...)` to validate names rather than assuming every string is valid.

### 2.2 Creating a Separate MBeanServer

JMX provides a factory for servers:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer isolated = MBeanServerFactory.createMBeanServer("com.example.isolated");
try {
    // Register and manage MBeans belonging to this scope.
} finally {
    MBeanServerFactory.releaseMBeanServer(isolated);
}
\`\`\`

`createMBeanServer` places the new server in the list tracked by `MBeanServerFactory`; `releaseMBeanServer` removes the server from that list. This is **not a guarantee** that all MBeans, callbacks, JMX connectors, or thread resources automatically close. The software owning those components must still clean them up and stop serving connections before releasing.

In addition, `newMBeanServer` creates a server that the factory does not keep in its lookup list in the same way; do not blindly call `releaseMBeanServer` on a server created through another path.

Creating a separate server is useful when registry isolation or independent component testing is needed. However, creating multiple servers increases the need to route the right `MBeanServerConnection`; MBeans on server A do not automatically appear on server B.

### 2.3 Locating an Existing Server

An integrated application may want to find an existing JMX server from the runtime/container. `MBeanServerFactory.findMBeanServer(null)` lists servers tracked by the factory, while `ManagementFactory.getPlatformMBeanServer()` accesses the platform server.

Do not grab the "first element" of the found list and assume it is the right choice. Within one JVM there may be multiple servers with different domains and objects. Define a configuration contract: pick the platform server or a server designated by the runtime/container.

## 3. Spring MBeanServerFactoryBean: Configuring Lookup or Creation

Spring supports `org.springframework.jmx.support.MBeanServerFactoryBean` to bring an `MBeanServer` into the bean graph. The factory bean can locate an existing server or create one according to configuration. This is an explicit way to manage the JMX dependency at the Spring layer.

Example configuration using the platform server as a dependency:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxServerConfiguration {

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

The benefit of this approach is that the intent to use the platform server is crystal clear. The `mbeanServer` bean is only a **reference** to the JVM resource; do not assume Spring owns or has the right to release that resource. If managing a separate server with `MBeanServerFactoryBean`, the configuration should specify the locate/create behavior and shutdown lifecycle appropriately for your Spring version.

A configuration declaring the factory:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class IsolatedJmxConfiguration {

    @Bean
    public MBeanServerFactoryBean applicationMBeanServerFactory() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.application");
        // In a real design, explicitly choose the mode to locate an existing server
        // or create a new server according to the runtime contract.
        return factory;
    }
}
\`\`\`

`setDefaultDomain` sets the default domain for the created server; it **does not replace** each MBean's `ObjectName` namespace and does not guarantee uniqueness on its own. Check the server-selection properties of `MBeanServerFactoryBean` for the deployed Spring Framework version. When isolation is unnecessary, configuring the platform server is usually simpler.

## 4. MBean Registration Lifecycle: create → register → expose → unregister

Even if the server already exists, an MBean only appears when there is a **register** step with an `ObjectName`. There are two common approaches:

1. Register directly with `MBeanServer.registerMBean` and take responsibility for `unregisterMBean`.
2. Let Spring `MBeanExporter` register beans and perform cleanup for the registrations owned by the exporter.

### 4.1 Manual Registration: The Owner Must Perform Symmetric Cleanup

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.*;
import java.util.concurrent.atomic.AtomicLong;

public interface QueueStatsMBean {
    long getCompleted();
}

public final class QueueStats implements QueueStatsMBean {
    private final AtomicLong completed = new AtomicLong();
    @Override public long getCompleted() {
        return completed.get();
    }
    public void recordCompleted() {
        completed.incrementAndGet();
    }
}

public final class ManualRegistration implements AutoCloseable {
    private final MBeanServer server;
    private final ObjectName objectName;
    private boolean registered;

    public ManualRegistration() throws Exception {
        this.server = ManagementFactory.getPlatformMBeanServer();
        this.objectName = new ObjectName(
            "com.example.app:type=QueueStats,name=ImportQueue");
        server.registerMBean(new QueueStats(), objectName);
        registered = true;
    }

    @Override
    public void close() throws JMException {
        if (registered) {
            server.unregisterMBean(objectName);
            registered = false;
        }
    }
}
\`\`\`

The example above illustrates a registration resource, not a production-ready concurrency utility. If multiple threads can call `close` or manage `register`, add synchronization and ownership checks. More importantly, do not write blind "if name exists then unregister" logic: that name might belong to another component. Only clean up MBeans that your own instance successfully registered.

If `registerMBean` throws `InstanceAlreadyExistsException`, the cause may be a duplicate `ObjectName`, an uncleaned old context, or another application using the same name. This is a signal to identify the owner, **not** a reason to delete an existing entry.

### 4.2 Letting Spring MBeanExporter Manage Registration

Spring `MBeanExporter` maps Spring beans to MBeans directly or via annotation metadata. Concept:

\`\`\`text
ApplicationContext starts up
  ↓
Create business beans
  ↓
MBeanExporter takes bean + ObjectName
  ↓
Register into configured MBeanServer
  ↓
JMX client observes/operates
  ↓
ApplicationContext closes
  ↓
Exporter cleans up registrations it manages
\`\`\`

Example using annotations:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.app:type=QueueStats,name=ImportQueue",
    description = "Read-only queue statistics")
public class QueueMetrics {
    private volatile long completed;

    @ManagedAttribute
    public long getCompleted() {
        return completed;
    }
}
\`\`\`

Enable annotation-driven JMX export when appropriate:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfiguration {
}
\`\`\`

In Spring Boot, check the actual JMX auto-configuration to avoid simultaneously creating multiple exporters registering the same MBean. `@ManagedResource` only describes the MBean; it does not guarantee registration if the export mechanism is inactive. Parent/child application contexts can also scan or export different beans; the design should clearly establish an owner for each `ObjectName`.

### 4.3 Policies for Duplicate ObjectName

Spring `MBeanExporter` supports registration policies for when a name already exists (e.g., ignore existing, replace, or fail, depending on configuration/API version). Using the right policy must start from ownership:

| Scenario | Desired Behavior |
|---|---|
| Same context registers the same name twice due to misconfiguration | Detect and fix configuration |
| Contexts A and B share a server for two different instances | Assign unique, stable names per instance |
| Runtime/container MBean already exists | Do not overwrite to "solve" the collision |
| Hot reload creates new context before old context closes | Synchronize shutdown/startup order; verify owner |
| Intentional re-registration during component version swap | Design handoff, unregister/register timing, and client handling |

A "replace" policy can affect MBeans belonging to another party; do not choose it merely to silence startup errors.

## 5. A Simple Lifecycle State Machine

An MBean's registration state can be pictured as follows:

\`\`\`text
NEW
 └── bean created successfully → READY
                               ├── registration succeeds → REGISTERED
                               │                             ├── used via JMX
                               │                             └── unregister → REMOVED
                               └── registration fails → FAILED
\`\`\`

`REGISTERED` means the registry has an entry at the chosen name; it does not guarantee every operation works properly, that a remote connector is open, or that business dependencies are ready. Similarly, `REMOVED` means the entry was removed from the server; it does not mean the Java object was immediately GC'd or threads created by the object have stopped.

For a separate `MBeanServer`:

\`\`\`text
SERVER_CREATED → MBEANS_REGISTERED → CONNECTOR_STARTED
                         ↓                    ↓
                 UNREGISTER_OWNED ← CONNECTOR_STOPPED
                         ↓
                  SERVER_RELEASED
\`\`\`

The exact sequence depends on the runtime, but the invariant is **stopping management access and cleaning up what you own before releasing the server**. If using only the platform server, the `SERVER_RELEASED` step is not the application's responsibility.

## 6. Startup: Dependencies, Ordering, and Observability

A startup sequence may include:

1. Selecting/obtaining the target `MBeanServer`.
2. Initializing business beans holding management data.
3. Registering MBeans via an exporter or self-managed mechanism.
4. Starting a connector if remote access is truly needed and allowed by configuration.
5. Verifying registration status and readiness of management functions.

If an MBean is registered before the business bean is completely ready, a JMX client may see the MBean while operations fail. This should be stated in the contract: `registered` differs from `ready`.

Do not use a JMX getter to "lazily initialize" heavy dependencies on first read; observing the app right after startup could accidentally trigger heavy work. If you want to expose startup state, provide low-cost read-only attributes like `LifecycleState` and `LastStartupError`.

When startup fails midway, ensure symmetric cleanup. For example, if an exporter registers MBean A but fails on MBean B due to a name collision, the system needs to know which registrations completed and clean them up in the context destruction flow. Do not assume a startup exception automatically removes entries registered manually by external libraries.

## 7. Shutdown: Closing a Context Does Not Mean Stopping the JVM

Applications in the same JVM may have multiple contexts, test contexts, or redeploy mechanisms. When a context closes, distinguish:

- **MBeans registered by this context:** must be removed when the owning component ends its lifecycle.
- **MBeans from other contexts:** must remain untouched.
- **Platform MXBeans:** continue existing with the JVM.
- **Shared connectors:** only the component that truly owns them may stop them.
- **Separate MBeanServer created by the context:** may be released after stopping connectors and completing proper cleanup.
- **MBean threads, executors, timers, scheduled tasks:** must be shut down separately per resource contract; unregistering does not replace destroy.

A Spring bean registering an MBean itself can use `@PostConstruct` / `@PreDestroy` or `InitializingBean` / `DisposableBean`. With Spring Framework 6 and Jakarta EE, the lifecycle annotations belong to `jakarta.annotation`, not `javax.annotation`.

Example of a registration owner:

\`\`\`java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import javax.management.*;
import java.lang.management.ManagementFactory;
import org.springframework.stereotype.Component;

@Component
public class OwnedQueueMBeanRegistration {
    private final MBeanServer server = ManagementFactory.getPlatformMBeanServer();
    private final ObjectName name;
    private boolean registered;

    public OwnedQueueMBeanRegistration() throws MalformedObjectNameException {
        name = new ObjectName("com.example.app:type=Queue,name=LocalQueue");
    }

    @PostConstruct
    public void register() throws JMException {
        server.registerMBean(new LocalQueueStats(), name);
        registered = true;
    }

    @PreDestroy
    public void unregister() throws JMException {
        if (registered) {
            server.unregisterMBean(name);
            registered = false;
        }
    }
}
\`\`\`

Here `LocalQueueStats` is a valid application-defined MBean with a Standard MBean interface or equivalent JMX form. Do not register this same object twice via `MBeanExporter`. If startup fails before `registered` is set to true, handle any failure between registration and updating the flag if additional logic exists, rather than removing another component's name.

With shutdown hooks, avoid registering multiple hooks that trigger duplicate cleanup. Most Spring Boot applications already have a context shutdown mechanism; custom configurations must understand the existing lifecycle.

## 8. JMX Connectors: An Independent Lifecycle

`MBeanServer` is an in-JVM registry; remote connectivity does not exist just because a server was created. A JMX connector server can be started separately, e.g. via `JMXConnectorServerFactory`, or provided by the JVM/container. Connector management covers endpoint, authentication, encryption, network, port, and cleanup.

\`\`\`text
MBeanServer (registry)
    ↑
JMXConnectorServer (remote endpoint)
    ↑
JMXConnector/JMX client
\`\`\`

If the connector is running while an application context has removed its MBeans, clients can still connect to the server and will simply see the remaining MBeans. If the connector stops while the registry stays alive, in-process clients can still access the server directly. These two states are distinct.

When managing a connector yourself, the owner must call `stop()` on shutdown and ensure clients do not rely on a closed endpoint. Do not confuse releasing `MBeanServer` with closing sockets/connectors; a connector can hold its own resources.

Regarding security, do not expose JMX ports publicly on the Internet. Configure authentication, authorization, TLS/network protection, and verify the actual endpoint. JMX commands can deeply affect the JVM, not just read metrics.

## 9. Multiple Contexts in the Same JVM: Who Owns the Name?

An application server may have parent/child contexts; integration tests may reuse the JVM; modular systems may dynamically load/unload contexts. If two contexts register:

\`\`\`text
com.example.app:type=Cache,name=Catalog
\`\`\`

into the same server, names will collide unless configuration explicitly handles it. A naming rule based on deployment logic is needed:

\`\`\`text
com.example.app:type=Cache,name=Catalog,context=publicApi
com.example.app:type=Cache,name=Catalog,context=batchWorker
\`\`\`

If the JVM runs multiple similar instances, add a stable `instance` key for the process lifetime when truly needed. When running across separate JVMs, each server has an independent namespace; putting hostname into every `ObjectName` is not mandatory, though it can help identify entries when aggregating management results.

Minimum ownership rules:

- The component that successfully registers an entry has the right and responsibility to remove it.
- A component that did not register an entry must not delete it by name just because it looks "stale".
- Every name has a defined handling plan for hot reload or context restart.
- Shared servers outlive individual contexts; cleanup must never delete other registrations.

## 10. Verifying Lifecycle with the JMX API

Useful APIs:

\`\`\`java
boolean registered = server.isRegistered(objectName);
ObjectInstance instance = server.getObjectInstance(objectName);
Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.app:*"), null);
\`\`\`

Use `isRegistered` or `queryNames` to observe the registry, keeping in mind they are snapshots: results can change right after reading. In concurrent operations, do not write code assuming "saw it unregistered so registration is guaranteed to succeed"; `registerMBean` can still race and throw an exception.

When checking after shutdown:

1. `ObjectName`s owned by the context are no longer in the registry.
2. Other contexts' MBeans and platform MXBeans remain if the server stays alive.
3. The context's connector, if any, has stopped.
4. No worker threads or executors belonging to stopped resources remain.
5. A new context can re-register the same name without manually deleting "ghost" entries.

For automated tests, use an isolated namespace or a separate `MBeanServer` when appropriate, close the context after the test, and assert registration state. If testing against the platform server, avoid fixed names that collide with other tests running in parallel.

### 10.1 Simple Verification Example

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JmxRegistrationLifecycleTest {

    @Test
    void registrationIsRemovedWhenContextCloses() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name =
            new ObjectName("com.example.app:type=QueueStats,name=ImportQueue");

        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(JmxExportConfiguration.class)) {
            // Real configuration needs a QueueMetrics bean and MBeanExporter.
            assertTrue(server.isRegistered(name));
        }

        assertFalse(server.isRegistered(name));
    }
}
\`\`\`

This is a conceptual test template; to run standalone, configure the context with the proper `QueueMetrics` bean and JMX configuration and ensure the exporter uses the same platform server. When using Spring test context caching, tests do not actually close the context at the end of each test unless lifecycle annotations/configurations dictate it. When verifying cleanup, explicitly creating and closing the context is clear.

## 11. Common Lifecycle Failures

### 11.1 `InstanceAlreadyExistsException` on Context Restart

**Symptom:** a new startup run cannot register an MBean with the old `ObjectName`.

**Common causes:** old context not closed yet, manual registration without unregistration, or two exporters managing the same name.

**How to handle:** identify owner and registration source; fix cleanup or namespace. Do not use "unregister all" on a shared server.

### 11.2 MBean Disappears After Another Context Stops

**Symptom:** context B is still running, but an MBean that B expects is gone.

**Cause:** context A replaced or removed a shared `ObjectName` without clear ownership.

**How to handle:** separate namespaces and registration policies; only the official registering component has the right to clean up its own entry.

### 11.3 `MBeanServer` Exists but MBean Is Not Visible

**Symptom:** JConsole connects but does not show application beans.

**Possible causes:** exporter not enabled, bean not in the exported context, target server differs from the server the client connects to, annotations not processed by exporter, or registration failed.

**How to handle:** check the server instance, exporter configuration, `ObjectName`, startup logs, and `queryNames` on the right server.

### 11.4 Running Tests Repeatedly Leaves MBeans in the JVM

**Symptom:** subsequent tests fail due to leftover registrations even though the previous test finished.

**Cause:** manual registration or test context caching lasting longer than expected.

**How to handle:** fixtures with close/unregister, separate names or servers, and avoiding parallel tests using the same name.

### 11.5 Releasing Server Without Closing Resources

**Symptom:** server is released from factory, yet threads, sockets, or references remain.

**Cause:** confusing releasing the registry with disposing all objects.

**How to handle:** stop connectors, shut down application resources, unregister owner-managed MBeans, and only then release the owned server.

## 12. Startup, Operations, and Shutdown Runbook

### Startup

- Explicitly document server choice: platform/shared/isolated.
- Have one clear export path per MBean.
- Ensure `ObjectName` is valid, deterministic, and avoids collisions across contexts.
- Only expose operations safe for the current readiness state.
- If enabling a remote connector, authentication and network exposure must be actively configured.

### Runtime

- Observe MBean registration and actual component health separately.
- Maintain logs/audits of state-changing operations.
- Do not use an `isRegistered` snapshot as a synchronization lock.
- Distinguish "MBean present in registry" from "service is healthy".

### Shutdown

- Stop accepting new management requests if the connector is owned by the context.
- Clean up MBeans registered by the context/exporter.
- Close threads, executors, and resources created by MBeans/components.
- Only release a separate server when the application truly owns it.
- Verify absence of context-owned names in a surviving registry.

## 13. Applied Exercises

**Exercise 1 — Two Spring contexts sharing the platform MBeanServer.** Context A exports `com.demo:type=Metrics,name=Scheduler`. Context B also exports that exact name. State what can happen when B starts up, how to name them, and why a replace policy should not always be enabled. Hint: `ObjectName` collision is an ownership issue; add a context identifier or consolidate on a single exporter.

**Exercise 2 — Creating a separate server for a plugin.** A plugin is loaded/unloaded multiple times in the same JVM. Design the order of creating the server, registering MBeans, starting an optional connector, stopping the connector, unregistering, and releasing. Explain how to protect cleanup when startup fails midway. Hint: every resource successfully created must be tracked for symmetric disposal; a server must not be released if not owned by that party.

**Exercise 3 — Reviewing an implementation.** A `@PreDestroy` method calls `MBeanServerFactory.releaseMBeanServer(ManagementFactory.getPlatformMBeanServer())`. Analyze what is wrong and rewrite the responsibilities: the context only removes MBeans it owns; the platform server belongs to the JVM.

**Exercise 4 — Lifecycle testing.** Write an integration test that creates and closes `AnnotationConfigApplicationContext`, asserting the context's MBean appears while open and disappears when closed. Ensure names do not collide across parallel tests; do not assume a single `isRegistered` assertion verifies all resources were cleaned up.

## Summary

Managing the `MBeanServer` lifecycle in the Spring Framework is a problem of **ownership and resource boundaries**. An `MBeanServer` can outlive an `ApplicationContext`; an exporter only owns the registrations it performs; JMX connectors have their own lifecycle; and every `ObjectName` must have a clear owner. A sustainable design selects the server intentionally, registers with a well-defined namespace, cleans up the right objects when the context closes, and verifies results on the actual registry. This prevents both MBean leaks and accidentally removing another component's management resources.
