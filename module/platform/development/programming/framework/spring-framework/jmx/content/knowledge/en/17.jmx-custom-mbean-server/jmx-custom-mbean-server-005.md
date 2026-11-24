# Sharing an MBeanServer Across Multiple Spring ApplicationContexts

## Learning Objectives

In Java Management Extensions (JMX), an **MBeanServer** is the registry and management access point: MBeans are registered by \`ObjectName\`, then queried by clients to read attributes, invoke operations, or receive notifications. In Spring Framework, each \`ApplicationContext\` can create its own \`MBeanExporter\`. A single JVM can simultaneously hold multiple contexts: parent/child contexts, web and batch contexts, multiple modules, integration tests, embedded applications, or dynamically created/closed contexts.

When contexts need to share **the same MBeanServer**, the problem is not simply injecting the same object. You must define server ownership, JMX domain namespaces, registration ownership, startup and shutdown order, behavior when a context restarts, as well as security and operational boundaries.

After this lesson, you will be able to:

- Distinguish sharing an MBeanServer from sharing Spring beans and sharing a JMX connector.
- Configure multiple ApplicationContexts to use the same platform MBeanServer or custom server.
- Define \`ObjectName\` namespaces for contexts to avoid collisions.
- Separate the server lifecycle from the exporter and individual MBean registration lifecycles.
- Understand limitations of parent/child contexts, bean visibility, and independence between sibling contexts.
- Handle \`InstanceAlreadyExistsException\`, hot reload, context refresh, and parallel tests.
- Verify that MBeans reside in the right server and are only removed by the owning context.
- Design the right topology when isolation is needed instead of sharing.

## 1. Mental Model: Three Different Lifecycles

An MBeanServer can be used by multiple contexts, yet usually **does not belong exclusively to any single child context**.

\`\`\`text
JVM
│
├── Shared MBeanServer
│   ├── java.lang:type=Memory
│   ├── com.example.web:type=Health,name=Api
│   ├── com.example.batch:type=Worker,name=Import
│   └── com.example.shared:type=Cache,name=Catalog
│
├── Parent ApplicationContext
│   ├── MBeanServer bean (reference to shared server)
│   └── Shared infrastructure
│
├── Web ApplicationContext
│   ├── WebMonitor
│   └── MBeanExporter(web) ── register/unregister WebMonitor
│
└── Batch ApplicationContext
    ├── BatchMonitor
    └── MBeanExporter(batch) ── register/unregister BatchMonitor
\`\`\`

When the Web context closes, its exporter needs to remove the MBeans it actually owns. **The MBeanServer remains alive**, and the Batch context's MBeans must remain intact. When the Batch context restarts, it can re-register its own ObjectNames once the old registrations have been cleaned up.

Distinguish:

| Subject | Function | Lifecycle Owner |
|---|---|---|
| \`MBeanServer\` | Shared registry | JVM or infrastructure/shared owner |
| Spring \`ApplicationContext\` | Module bean container | Module/runtime managing the context |
| \`MBeanExporter\` | Registers selected MBeans | Context that creates the exporter |
| Registration \`ObjectName -> MBean\` | One management entry | Exporter or component that registered it |
| \`JMXConnectorServer\` | Enables remote client connections | Infrastructure starting the connector |

Using the same server does not mean contexts co-own every MBean on it. An exporter must not remove a name simply because it shares the same domain if that registration belongs to another component.

## 2. When Should You Share a Server?

A shared MBeanServer is suitable when:

1. Modules run **in the same JVM** and need to be observed from one JMX connector.
2. Operations tooling wants to see JVM MXBeans and MBeans from multiple modules in one place.
3. Management namespaces are clear enough to distinguish modules/instances.
4. Contexts have independent lifecycles yet can manage registrations symmetrically.
5. There is no strict security isolation requirement forcing modules into separate endpoints or processes.

Cases worth considering a **separate server**:

- A plugin/tenant must isolate its management surface under a well-designed access and lifecycle model.
- There is a runtime/container managing multiple distinct registries and connectors.
- A module needs testing or experimentation without affecting the rest of the registry.
- There is potential for JMX contract conflicts that cannot be solved by namespace alone.

Even when using a separate server, the server still lives in the **same JVM**; that alone does not create a sandbox or security boundary equivalent to process isolation. Connectors and access policies must be configured separately.

## 3. Choosing a Shared Server: Platform or Custom?

### 3.1 Platform MBeanServer

Java provides:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer shared = ManagementFactory.getPlatformMBeanServer();
\`\`\`

The platform server is the common choice when an application wants to unify with standard JVM MXBeans. Multiple contexts can hold a reference to this object. Calling \`getPlatformMBeanServer()\` from multiple contexts in the same JVM does not create independent platform servers for each context.

Remember: the platform MBeanServer is JVM-scoped; do not release it when a child Spring context closes.

### 3.2 Custom Server Created Once

If a dedicated shared server is needed:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer shared =
    MBeanServerFactory.createMBeanServer("com.example.runtime");
\`\`\`

This server must be created **once** by the shared owner and its reference passed to consuming contexts. If each context calls \`createMBeanServer\`, you have created multiple different registries and are no longer "sharing a server".

\`MBeanServerFactory.createMBeanServer\` creates a server tracked by the factory. The shared owner can release it once all consumers and connectors have stopped:

\`\`\`java
MBeanServerFactory.releaseMBeanServer(shared);
\`\`\`

The release call does not automatically close threads, connectors, beans, or other resources. Their owning components must clean them up separately. Do not call release on a server not governed by the owner, and do not treat \`releaseMBeanServer\` as a safe command to delete all MBeans.

## 4. Parent/Child Context Configuration: One Server Bean in the Parent

If child contexts share a common parent, let the parent provide the server:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ParentJmxConfiguration {

    @Bean
    public MBeanServer sharedMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

The Web context and Batch context use the \`sharedMBeanServer\` bean from the parent, provided bean visibility and injection are designed appropriately. In Spring's context hierarchy model, a child can look up beans from the parent; the parent does not automatically see all private beans in children, and two sibling contexts do not automatically exchange beans with each other.

Web context exporter example:

\`\`\`java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class WebJmxConfiguration {

    @Bean
    public MBeanExporter webExporter(
            MBeanServer sharedMBeanServer,
            WebHealthMBeanAdapter webHealth) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(sharedMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.web:type=Health,name=Api", webHealth
        ));
        exporter.setAutodetect(false);
        return exporter;
    }
}
\`\`\`

Batch context exporter:

\`\`\`java
@Configuration
public class BatchJmxConfiguration {

    @Bean
    public MBeanExporter batchExporter(
            MBeanServer sharedMBeanServer,
            BatchWorkerMBeanAdapter batchWorker) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(sharedMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.batch:type=Worker,name=Import", batchWorker
        ));
        exporter.setAutodetect(false);
        return exporter;
    }
}
\`\`\`

The adapters in the examples are valid management beans: Standard MBeans/MXBeans or beans processed by an exporter using an appropriate assembler. To run the snippets in a project, the corresponding adapters and management interfaces must be fully declared. The configuration chooses explicit \`setBeans\` and disables autodetection to keep each module's MBean set clear.

**Key point:** both exporters receive the same \`sharedMBeanServer\` reference, yet each exporter only registers a list of ObjectNames belonging to its own module.

## 5. Without a Common Parent: Passing the Reference into Each Context

Two sibling contexts or two independent \`ApplicationContext\` instances do not automatically share beans via dependency injection. You can:

- Create the server in the bootstrap/root owner and pass the reference to each context.
- Register a reference to the same object in each context before refresh.
- Use the platform MBeanServer as the convergence point if appropriate.
- Have a shared configuration/factory supplied with the same server by the bootstrap rather than each place creating its own.

A skeleton with Spring \`AnnotationConfigApplicationContext\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

MBeanServer shared = ManagementFactory.getPlatformMBeanServer();

AnnotationConfigApplicationContext web =
    new AnnotationConfigApplicationContext();

AnnotationConfigApplicationContext batch =
    new AnnotationConfigApplicationContext();

web.getBeanFactory().registerSingleton("sharedMBeanServer", shared);
batch.getBeanFactory().registerSingleton("sharedMBeanServer", shared);

web.register(WebJmxConfiguration.class);
batch.register(BatchJmxConfiguration.class);

web.refresh();
batch.refresh();
\`\`\`

In a real application, each context also needs to configure its adapters, services, and appropriate dependencies. The bootstrap owner must close contexts on shutdown; merely registering the same reference does not define registration cleanup or server release.

Specifically avoid:

\`\`\`java
@Bean
public MBeanServer sharedMBeanServer() {
    return MBeanServerFactory.createMBeanServer();
}
\`\`\`

in **multiple** independent contexts if the intent is to use one server; each invocation of the factory creates a different server. If using the platform server, \`ManagementFactory.getPlatformMBeanServer()\` can be called from multiple contexts, though you must still ensure exporters are actually configured to use that platform server.

## 6. Server Bean and Exporter Server Are Two Separate Configurations

Simply creating a Spring bean of type \`MBeanServer\` does not guarantee every exporter automatically uses it if multiple candidates exist or an exporter is configured to pick another server. The design should specify explicitly:

\`\`\`java
exporter.setServer(sharedMBeanServer);
\`\`\`

Or with annotation-driven export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(
    server = "sharedMBeanServer",
    defaultDomain = "com.example.web"
)
public class WebAnnotationExportConfiguration {
}
\`\`\`

In \`@EnableMBeanExport\`, the \`server\` value is the **Spring bean name** of type \`MBeanServer\`, not a remote connection hostname or port. With \`MBeanExporter.setServer\`, the argument is a reference to the \`MBeanServer\` object.

Ensure annotation exporters across multiple contexts do not export the same bean or the same ObjectName. Use explicit \`@ManagedResource(objectName = "...")\` when a stable naming contract is needed.

### 6.1 defaultDomain Does Not Change the MBeanServer

Two exporters using the same server with different \`defaultDomain\` values are still sharing a registry. \`defaultDomain\` affects how the naming strategy builds an ObjectName when no explicit domain is given; it does not move registrations to a new server.

If two beans both declare:

\`\`\`java
@ManagedResource(
    objectName = "com.example.shared:type=Worker,name=Import")
\`\`\`

then changing \`defaultDomain\` on one exporter will not resolve the same-ObjectName conflict. You must change the published name or designate a single owner.

## 7. ObjectName is a Unique Key Within Each Server

MBeanServer uses \`ObjectName\` as the registry key. Two contexts both registering:

\`\`\`text
com.example:type=Worker,name=Main
\`\`\`

into the same server will create a collision. The error may manifest via \`InstanceAlreadyExistsException\` or the configured registration policy. You should not apply "replace" by default because exporter A could replace B's MBean and then context A shutting down would remove the entry B still needs.

Design names with scoped identifiers:

\`\`\`text
com.example.web:type=Health,name=Api
com.example.batch:type=Worker,name=Import
com.example.shared:type=Cache,name=Catalog
\`\`\`

If there are two identical instances **in the same JVM**, you can add an \`instance\` or \`context\` key:

\`\`\`text
com.example.batch:type=Worker,name=Import,instance=primary
com.example.batch:type=Worker,name=Import,instance=secondary
\`\`\`

When different JVMs use the same ObjectName, there is no collision because registries are separate; monitoring may need to attach JVM/node identity at the collection layer.

Key properties must be encoded per \`ObjectName\` syntax. Avoid putting tokens, user IDs, or sensitive data into MBean names.

## 8. One Registration, One Owner

The crux of sharing a server is **ownership**:

| Component | Required Responsibility |
|---|---|
| Server owner | Create, configure, manage connector, and release dedicated server when no consumers remain |
| Web exporter | Register/unregister MBeans belonging to the Web context |
| Batch exporter | Register/unregister MBeans belonging to the Batch context |
| Shared infrastructure exporter | Register/unregister shared MBeans belonging to the shared owner |
| Monitoring client | Read/invoke per permissions; does not own the server |

Do not call \`queryNames("com.example:*")\` and unregister everything when a context stops. A domain is a logical namespace, not proof of ownership. A context should only clean up the list of registrations **it successfully created itself** or that its exporter manages.

When using Spring \`MBeanExporter\`, the exporter normally removes its own registrations when destroyed. For manual registration via \`MBeanServer.registerMBean\`, the owning component must record success and remove it on close.

Example:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.JMException;

public final class OwnedRegistration implements AutoCloseable {

    private final MBeanServer server;
    private final ObjectName name;
    private boolean registered;

    public OwnedRegistration(MBeanServer server, ObjectName name, Object mbean)
            throws JMException {
        this.server = server;
        this.name = name;
        server.registerMBean(mbean, name);
        registered = true;
    }

    @Override
    public void close() throws JMException {
        if (registered) {
            server.unregisterMBean(name);
            registered = false;
        }
    }
}
\`\`\`

This is a single-owner illustration, not a complete concurrency implementation. In production, if multiple threads exist or registrations might be replaced between operations, sufficiently strong synchronization/lifecycle policies are required. Do not let another component overwrite an entry after the owner registered it and then still attempt to unregister by name on shutdown.

## 9. Multi-Context Startup and Dependency Order

A multi-context bootstrap might consist of:

\`\`\`text
1. Create shared MBeanServer (or obtain platform server)
2. Create shared context or provide reference
3. Create Web context + dedicated exporter
4. Create Batch context + dedicated exporter
5. Start JMX connector if needed
6. Verify expected ObjectNames on the right server
\`\`\`

Not every system must follow this exact order, but you must ensure **the server exists before exporters need it** and **the connector is not treated as the sole prerequisite for MBeanServer operation**.

If one context fails on startup:

- Ensure registrations that already succeeded are cleaned up by their owner.
- Do not release the shared server just because one module failed.
- Other contexts continue using the registry if the runtime contract allows.
- An \`InstanceAlreadyExistsException\` must be diagnosed by ObjectName and exporter, not handled by wiping an entire domain.

### 9.1 MBean Readiness Differs from Service Readiness

A registered MBean may appear in JConsole before the business-serving module is ready. Therefore, expose \`LifecycleState\`, \`RequestedState\`, \`EffectiveState\`, or a readiness summary when needed, instead of using \`server.isRegistered(name)\` as a healthy-service signal.

JMX getters should be low-cost. Do not put heavy diagnostic operations inside a getter that could stall bootstrap or critical processing paths.

## 10. Independent Shutdown and Restart

Suppose the Web context is redeployed while the Batch context keeps running:

\`\`\`text
Shared MBeanServer: alive
Web Context A:      RUNNING → CLOSED → new Web Context A'
Batch Context B:    RUNNING → RUNNING
\`\`\`

Expected behavior:

1. Web exporter A unregisters \`com.example.web:...\` owned by A.
2. Batch MBeans and shared MBeans remain present.
3. Web context A' re-registers the same names when ready.
4. The shared MBeanServer is not released during redeploy.
5. Management clients may see Web MBeans temporarily disappear and reappear; this can be a valid lifecycle.

If the new Web context starts before the old Web context has unregistered, a collision can occur. The solution is to synchronize the handoff or intentionally use an instance/generation namespace, rather than automatically replacing the old context's MBeans without clear ownership.

For a custom server, only the shared owner should release it after contexts/connectors have genuinely stopped using it. If the server was created by \`MBeanServerFactory.createMBeanServer\`, distinguish releasing factory tracking from cleaning up component resources.

## 11. JMX Connector Has an Independent Lifecycle

An \`MBeanServer\` does not automatically open a remote port. \`JMXConnectorServer\` can provide an endpoint to a specific server.

\`\`\`text
JMX client ── network ── JMXConnectorServer
                               |
                               v
                        Shared MBeanServer
                         /             \
                  Web MBeans         Batch MBeans
\`\`\`

Only **one connector** is needed if the architecture and permissions fit all MBeans in the shared server. Do not have each context start its own connector on the same port; that can cause bind errors or inconsistent endpoints.

If different user groups have different permissions, check the connector's authentication/authorization. Separating ObjectName domains does not automatically enforce access control; a user with appropriate JMX privileges can access MBeans across multiple domains. A separate server also does not replace access control or network isolation.

Do not leave an unprotected JMX endpoint open to the Internet. Control operations on MBeans can directly mutate application state.

## 12. Common Context Topologies

### 12.1 Parent/Child Context

\`\`\`text
Parent
  ├── sharedMBeanServer
  ├── sharedMonitor
  └── Child Web / Child Batch
\`\`\`

Children can see beans from the parent. Pay attention if an \`MBeanExporter\` in the parent autodetects beans; exact scope depends on the BeanFactory/exporter. Do not assume a parent exporter can manage all beans in children, or that two child exporters automatically share registration ownership.

The simple approach is a dedicated exporter per module with explicit beans, and the server bean in the parent.

### 12.2 Independent Contexts

No common parent, yet they receive the same server via bootstrap or use the platform server. Contexts do not automatically share Spring beans; only **the reference to the MBeanServer** is shared. Do not try to inject a bean from module A directly into B just because A's MBean appears in the registry.

### 12.3 Multi-Module Application in a Single Context

If all modules live in one ApplicationContext, you can use a single exporter with an explicit list or multiple exporters partitioned by group. Multiple exporters increase collision/lifecycle complexity; prefer the simpler design when there is no need to assign separate owners.

### 12.4 Integration Tests Sharing a JVM

Multiple tests may create and close contexts repeatedly, especially when tests run in parallel. Because the platform MBeanServer is shared, a fixed \`ObjectName\` can conflict across tests. You can use a separate server per test or a unique test namespace, clean up in finally, and avoid deleting MBeans not owned by the test.

## 13. Diagnosing MBeans Not Appearing in JConsole

Common causes:

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| Web MBean visible, Batch MBean not | Batch exporter uses a different server | Compare server references |
| MBean registered successfully but JConsole does not see it | Connector points to a different registry | Check connector/server |
| Context startup fails with collision | Two exporters use the same ObjectName | Check name, owner, policy |
| Web shutdown causes Batch MBean to disappear | A component mistakenly unregistered/replaced the registration | Check cleanup code and ownership |
| Context reloads and MBean does not return | New exporter has not run or old context did not clean up | Check lifecycle and logs |
| JConsole sees MBean but operation fails | Service not ready, wrong signature, or insufficient permissions | Check MBeanInfo/effective state |
| Two modules appear in the same domain | Naming strategy/defaultDomain too generic | Redesign namespace |

Do not fix a "missing MBean" error by indiscriminately creating another \`MBeanServer\`. First identify **which server** the MBean was registered into and which connector the JMX client connects through.

## 14. Inspecting the Registry and Metadata on the Right Server

Example:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.MBeanInfo;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> webNames = server.queryNames(
    new ObjectName("com.example.web:*"), null);

Set<ObjectName> batchNames = server.queryNames(
    new ObjectName("com.example.batch:*"), null);

System.out.println("Web MBeans = " + webNames);
System.out.println("Batch MBeans = " + batchNames);

for (ObjectName objectName : batchNames) {
    MBeanInfo info = server.getMBeanInfo(objectName);
    System.out.println(objectName + " -> " + info.getClassName());
}
\`\`\`

This queries the platform server; if sharing a custom server, pass that server reference instead of calling \`getPlatformMBeanServer()\`. The result of \`queryNames\` is a snapshot at read time, not a guarantee that state will not change while contexts are restarting.

A check after the Web context closes:

\`\`\`java
assertTrue(server.queryNames(
    new ObjectName("com.example.web:*"), null).isEmpty());

assertFalse(server.queryNames(
    new ObjectName("com.example.batch:*"), null).isEmpty());
\`\`\`

These two assertions are only appropriate when the test fixture genuinely has only Web MBeans from the Web context and Batch MBeans from the Batch context in the respective domains. In production there may be other MBeans belonging to those domains; assert the exact ObjectNames owned by the fixture.

## 15. Integration Test: Closing One Context Does Not Remove Another Context's MBeans

A fixture should create a shared server, start two different contexts, and verify registration and shutdown:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SharedMBeanServerTest {

    @Test
    void closingWebContextKeepsBatchMBean() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        ObjectName webName = new ObjectName(
            "com.example.web:type=Health,name=Api");
        ObjectName batchName = new ObjectName(
            "com.example.batch:type=Worker,name=Import");

        AnnotationConfigApplicationContext web =
            new AnnotationConfigApplicationContext();
        AnnotationConfigApplicationContext batch =
            new AnnotationConfigApplicationContext();

        try {
            web.getBeanFactory().registerSingleton(
                "sharedMBeanServer", server);
            batch.getBeanFactory().registerSingleton(
                "sharedMBeanServer", server);

            web.register(WebJmxConfiguration.class);
            batch.register(BatchJmxConfiguration.class);

            web.refresh();
            batch.refresh();

            assertTrue(server.isRegistered(webName));
            assertTrue(server.isRegistered(batchName));

            web.close();

            assertFalse(server.isRegistered(webName));
            assertTrue(server.isRegistered(batchName));
        } finally {
            web.close();
            batch.close();
        }
    }
}
\`\`\`

To run, valid \`WebHealthMBeanAdapter\` and \`BatchWorkerMBeanAdapter\` classes must be present and registered in their respective contexts. Names must not collide with tests running in parallel. The goal of the test is to verify **lifecycle ownership**, not to build a complete fixture for every application module.

In complex multi-context systems, also test:
- Restarting one context while another context keeps running.
- Two exporters intentionally registering duplicate ObjectNames and startup being clearly rejected.
- No duplicate MBeans after refresh.
- The connector (if present) stays alive when a consumer context closes.
- A custom server is only released when the shared owner terminates.

## 16. Mistakes to Avoid

### 16.1 Each Context Creates a New Server While Thinking It Is Sharing

\`\`\`java
@Bean
MBeanServer server() {
    return MBeanServerFactory.createMBeanServer();
}
\`\`\`

If the config is initialized independently in multiple contexts, each context gets a different registry. Solution: the platform server or a bootstrap owner creates and injects the same reference.

### 16.2 Assuming Same Domain Means Same Owner

Two MBeans \`com.example:type=Worker,name=A\` and \`com.example:type=Worker,name=B\` may belong to two contexts. Never unregister all MBeans by domain when one context shuts down.

### 16.3 Using the Replace Registration Policy to Fix Collisions

This can mask namespace errors or cause one context to replace another context's MBean. Fix ownership, ObjectNames, and lifecycle ordering instead.

### 16.4 Binding the Connector Lifecycle to Individual Module Contexts

Stopping one module could accidentally disconnect all JMX clients, even though the MBeanServer and other modules are still alive. A shared connector should have an owner with a sufficiently long lifecycle.

### 16.5 Setting defaultDomain and Assuming the Server Is Shared

Default domain is a naming concern; server selection is a separate decision. Two exporters with the same domain on different servers still do not share a registry.

### 16.6 Registering MBeans Manually Without Unregistering

A context may close while the MBean entry still holds a reference to the old bean, causing leaks and collisions on restart. Symmetrical cleanup by ownership is required.

### 16.7 Putting All MBeans in One Server Without Access Control

JMX is a powerful management surface. Sharing a server exposes many MBeans in one place, making authentication, authorization, TLS, management networks, and auditing even more important.

## 17. Design and Operations Runbook

### Before Deployment

1. Clearly choose **platform server** or **shared custom server**.
2. Identify the **shared owner** of the server and connector.
3. Document which group of MBeans each context/exporter manages.
4. Define \`ObjectName\` namespaces with module/instance identifiers when needed.
5. Enable explicit export or selective annotations, avoiding automatic export of the same bean by multiple exporters.
6. Secure the JMX endpoint and classify operations that have side effects.
7. Write integration tests for independent startup, shutdown, and restart.

### On Startup

1. Ensure the server reference is ready before exporters.
2. Watch for registration exceptions, especially \`InstanceAlreadyExistsException\`.
3. Read \`MBeanServer.queryNames\` on the right server.
4. Verify published ObjectNames and MBeanInfo.
5. Verify the connector points to the right server if using remote JMX.

### On Shutdown

1. Close contexts according to actual dependencies.
2. Each exporter unregisters the MBeans it registered.
3. Do not release the server while other contexts are still using it.
4. The shared owner stops the connector, cleans up, and releases the custom server if authorized and needed.
5. Verify no stale registrations remain and no MBeans from other modules were removed by mistake.

## 18. Practice Exercises

**Exercise 1 — Parent/child.** The parent context provides the platform MBeanServer. Web child and Batch child each have an MBeanExporter. Describe how to inject the same server and choose namespaces so Web shutdown does not affect Batch.

**Exercise 2 — Custom server.** Two independent contexts each call \`MBeanServerFactory.createMBeanServer()\`. Why does JConsole only see some of the MBeans when connected to one connector? The server must be created once and its reference passed to both.

**Exercise 3 — Collision.** Two exporters both register \`com.example:type=Worker,name=Main\` into the platform server. Propose new ObjectNames and explain why the replace policy is not the default answer.

**Exercise 4 — Ownership.** When the Web context closes, code calls \`queryNames("com.example:*")\` and unregisters everything. Point out the risk and replace it with cleanup of only the registrations belonging to the Web exporter.

**Exercise 5 — Testing.** Write an integration test creating two contexts sharing the same server, assert both MBeans exist, close one context, and assert the remaining MBean stays alive.

**Exercise 6 — Remote connector.** Name three reasons an MBean registers successfully yet a remote JMX client does not see it: connector points to another server, client connects to the wrong JVM, actual ObjectName differs from expectations.

## Summary

**Sharing an MBeanServer across multiple Spring ApplicationContexts** means having exporters from multiple contexts register into **the same JMX registry**, not merging Spring bean graphs or unifying context lifecycles. Proper design requires one owner for the shared server, an exporter/registration owner per module, unique ObjectNames within the registry, symmetrical cleanup, and a connector with an independent lifecycle. The platform MBeanServer makes sharing simple within a single JVM; a custom server should only be created once and released by the shared owner after all consumers have finished. With this model, multiple contexts can be observed together while starting, stopping, and redeploying independently without accidentally deleting each other's MBeans.
