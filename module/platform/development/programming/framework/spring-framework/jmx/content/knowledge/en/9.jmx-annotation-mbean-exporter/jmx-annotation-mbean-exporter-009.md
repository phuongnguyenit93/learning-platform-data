# Customizing the Exporter When Multiple ApplicationContexts Exist in Spring Framework JMX

## 1. Objectives and Scenarios

A Spring application can have **multiple \`ApplicationContext\` instances**: a root context, per-module contexts, a child web context, dynamically created plugin contexts, or isolated contexts for integration tests. If multiple contexts enable JMX export simultaneously, they can register MBeans into the same \`MBeanServer\`, use colliding ObjectNames, or mismanage the unregistration lifecycle.

With annotation-based configuration, Spring provides \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, \`@EnableMBeanExport\`, and export components like \`AnnotationMBeanExporter\` / \`MBeanExporter\`. When multiple contexts exist, the key question is no longer "how do I enable JMX?" but rather:

- Which context owns the exporter?
- Which beans does each exporter see?
- Do the exporters share the same \`MBeanServer\`?
- Do ObjectNames clearly distinguish module/context/instance?
- When a context closes, who unregisters the registered MBeans?
- How do we maintain a stable management contract for clients?

This lesson helps you design and test JMX configuration when an application has multiple Spring contexts, avoiding both duplicate registrations and loss of observability.

## 2. Concept Map

\`\`\`text
                   One JVM process
                           |
              Platform MBeanServer (shared)
                           |
          +----------------+----------------+
          |                |                |
       Root Context    Module A Context  Module B Context
          |                |                |
       Exporter R      Exporter A       Exporter B
          |                |                |
     root:* MBeans   module=A,*        module=B,*
\`\`\`

This is one way to organize it. Having multiple contexts does not force you to create multiple exporters or multiple MBeanServers. You can use **one centralized exporter**, one exporter per context, or dedicated servers for groups of contexts, depending on requirements. The difference lies in *ownership* and bean discovery scope.

| Component | Scope of Meaning |
|---|---|
| \`ApplicationContext\` | Container holding Spring bean definitions/instances and lifecycle |
| \`BeanFactory\` | Where the exporter looks up beans or autodetects candidates |
| \`MBeanExporter\` | Registers selected objects into an \`MBeanServer\` |
| \`AnnotationMBeanExporter\` | Supports exporting beans based on Spring management annotations |
| \`MBeanServer\` | JMX registry, which may be shared by multiple contexts |
| \`ObjectName\` | Unique MBean identifier within an \`MBeanServer\` |
| \`RegistrationPolicy\` | Exporter behavior when an MBean with the same name already exists |
| \`@EnableMBeanExport\` | Enables JMX export support via Java configuration |

**Foundational principle:** ObjectName uniqueness is evaluated within the **\`MBeanServer\`**, not along \`ApplicationContext\` boundaries. Two beans with the same name in two different contexts can still collide if exporters place them into the same server.

## 3. Common Multi-Context Architectures

### 3.1. One root context and child contexts

For example, a web application with a root context holding shared services and a child context for MVC.

\`\`\`text
RootApplicationContext
  - commonCacheMonitor
  - commonExporter

  └── WebApplicationContext
        - requestMonitor
        - optionalWebExporter
\`\`\`

A child context can see parent beans during lookup, whereas the parent does not automatically see child beans. Meanwhile, exporter candidate autodetection depends on the exporter mechanism and configured \`BeanFactory\`. Do not simplistically assume "an exporter in root will automatically register all child beans" or "an exporter in child sees every parent bean without risk of collision."

Explicitly decide who is responsible for exporting each resource and test against \`MBeanServer\`.

### 3.2. Independent module contexts

For example, an application loads modules A and B using two separate \`AnnotationConfigApplicationContext\` instances.

\`\`\`text
Module A context --> Exporter A --+
                                  +--> Shared MBeanServer
Module B context --> Exporter B --+
\`\`\`

In this case, each exporter only knows its own module, yet ObjectNames must have clear namespaces, for example:

\`\`\`text
com.example.app:type=Worker,module=inventory,name=Primary
com.example.app:type=Worker,module=billing,name=Primary
\`\`\`

Keeping \`type/name\` while omitting \`module\` in both contexts will cause a collision.

### 3.3. Plugin contexts with dynamic lifecycles

A plugin being enabled/disabled can create/close an \`ApplicationContext\`. The plugin's JMX resources should appear and disappear accordingly:

\`\`\`text
Plugin enabled  -> context created -> exporter registers MBeans
Plugin disabled -> context closed  -> exporter unregisters owned MBeans
\`\`\`

If the context is not closed, or MBeans are registered manually without cleanup, the JMX registry will retain stale objects and may hold references to the plugin's classloader.

### 3.4. Integration tests running in parallel

Multiple test contexts in a single JVM may share the platform \`MBeanServer\`. Tests creating fixed \`ObjectName\` values without cleanup easily cause \`InstanceAlreadyExistsException\` in other tests. One way to reduce interference is giving each fixture/context its own \`MBeanServer\` or unique names, and closing the context after the test.

## 4. Why Can AnnotationMBeanExporter Cause Duplicate Registrations?

With Spring annotation export, objects with JMX metadata can be autodetected and registered when the context initializes the exporter. When multiple contexts have similar configurations, sources of duplication can include:

1. The same class/bean is instantiated in two contexts while both use a fixed \`@ManagedResource(objectName = "...")\`.
2. A shared bean from the parent is exported in root and registered again by the child's exporter.
3. A configuration class enabling \`@EnableMBeanExport\` is imported into multiple contexts.
4. Both an annotation-config exporter and an explicit \`MBeanExporter\` are declared for the same object.
5. A plugin reloads before old registrations have been unregistered.
6. A naming strategy generates names that do not distinguish module/instance.

Example:

\`\`\`java
@ManagedResource(objectName = "example.jmx:type=Worker,name=Primary")
public class WorkerMonitor {
    // ...
}
\`\`\`

If modules A and B both export this object into one \`MBeanServer\`, the names will collide regardless of their living in two independent \`ApplicationContext\` instances.

**Make a clear distinction:** having annotations on a bean does not guarantee it is already exported. An initialized and properly configured exporter is required. Collision errors typically occur when more than one actual registration takes place, not merely because metadata looks identical.

## 5. Three Export Strategy Options

| Strategy | Design | When Appropriate | What Must Be Controlled |
|---|---|---|---|
| One centralized exporter | One context manages registrations for the whole app | Stable modular systems, centralized management | Accessible bean set and lifecycle |
| One exporter per context | Each module exports its own MBeans | Plugins or independent modules | ObjectName namespaces and cleanup |
| Dedicated server per context | Each context has its own server and exporter | Test isolation or intentional management separation | Clients connecting to right server and connector |

A centralized exporter does not automatically collect beans from every child context. If modules are loaded dynamically, you need an explicit mechanism to pass/register resources or use module-local exporters.

A dedicated server also does not expose a remote endpoint automatically; a connector is still needed if clients in another JVM must access it.

## 6. Example: Two Contexts Sharing an MBeanServer, Each Owning Its Exporter

The example below uses explicit registration to make ownership clear. You can extend it to an annotation exporter once the architecture is clear.

### 6.1. MBean contract

\`\`\`java
// ModuleMonitorMBean.java
public interface ModuleMonitorMBean {
    String getModule();
    int getCompletedTasks();
}
\`\`\`

\`\`\`java
// ModuleMonitor.java
import java.util.concurrent.atomic.AtomicInteger;

public final class ModuleMonitor implements ModuleMonitorMBean {
    private final String module;
    private final AtomicInteger completed = new AtomicInteger();

    public ModuleMonitor(String module) {
        this.module = module;
    }

    @Override
    public String getModule() {
        return module;
    }

    @Override
    public int getCompletedTasks() {
        return completed.get();
    }

    public void recordCompletion() {
        completed.incrementAndGet();
    }
}
\`\`\`

### 6.2. Providing a shared MBeanServer

In the Java configuration example, use the platform server or a server created once outside the contexts. Each context is supplied the same instance:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer sharedServer =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

Each module does not need to call \`MBeanServerFactory.newMBeanServer()\` if the requirement is for all modules to appear under the same JMX endpoint.

### 6.3. Per-module configuration

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

import javax.management.MBeanServer;
import java.util.Map;

@Configuration(proxyBeanMethods = false)
public class ModuleJmxConfiguration {
    private final MBeanServer server;
    private final String moduleName;

    public ModuleJmxConfiguration(
            MBeanServer server, String moduleName) {
        this.server = server;
        this.moduleName = moduleName;
    }

    @Bean
    public ModuleMonitor moduleMonitor() {
        return new ModuleMonitor(moduleName);
    }

    @Bean
    public MBeanExporter moduleExporter(ModuleMonitor monitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
            "example.jmx:type=ModuleMonitor,module=" + moduleName,
            monitor
        ));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING);
        return exporter;
    }
}
\`\`\`

Initializing separate contexts:

\`\`\`java
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class MultipleContextsDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            java.lang.management.ManagementFactory
                .getPlatformMBeanServer();

        try (var inventory =
                 new AnnotationConfigApplicationContext();
             var billing =
                 new AnnotationConfigApplicationContext()) {

            inventory.registerBean(
                ModuleJmxConfiguration.class,
                () -> new ModuleJmxConfiguration(
                    server, "inventory"));
            inventory.refresh();

            billing.registerBean(
                ModuleJmxConfiguration.class,
                () -> new ModuleJmxConfiguration(
                    server, "billing"));
            billing.refresh();

            ObjectName a = new ObjectName(
                "example.jmx:type=ModuleMonitor,module=inventory");
            ObjectName b = new ObjectName(
                "example.jmx:type=ModuleMonitor,module=billing");

            System.out.println(server.isRegistered(a)); // true
            System.out.println(server.isRegistered(b)); // true
        }
    }
}
\`\`\`

The example uses a Spring Context with bean definitions registered before \`refresh()\`. Both exporters share one server, yet each context manages distinct registrations. When the contexts close, Spring invokes each exporter's lifecycle cleanup to unregister the MBeans it registered according to the exporter's policy.

**Design note:** if \`moduleName\` comes from a plugin or external config, validate and/or escape it for valid \`ObjectName\` syntax. Do not directly concatenate untrusted data that may contain characters like \`:,=*?\` into an ObjectName.

## 7. Adding Annotation Export to a Multi-Context Model

A Spring-managed bean can use:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "example.jmx:type=Service,module=inventory,name=Primary")
public class InventoryStatus {
    private volatile boolean healthy = true;

    @ManagedAttribute
    public boolean isHealthy() {
        return healthy;
    }
}
\`\`\`

For the exporter to discover annotation metadata, configure \`AnnotationMBeanExporter\` or \`MBeanExporter\` with the corresponding annotation metadata assembler. One option is placing \`@EnableMBeanExport\` on the exact context that needs export.

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
class InventoryJmxConfig {
}
\`\`\`

This configuration illustrates how to enable annotation export. In an application using a shared \`MBeanServer\`, connect the exporter created by annotation configuration to the desired server per the Spring API and version in use. Avoid enabling the same configuration in both parent and child without planned ownership.

### 7.1. Assigning ObjectName from annotations or naming strategy?

With a few stable beans, \`@ManagedResource(objectName = "...")\` is explicit. However, when the same class is reused across multiple modules/contexts, a hardcoded ObjectName easily collides.

Approaches:

- Declare distinct classes with separate ObjectNames when domains are clear and counts are small.
- Use a naming strategy on the exporter to include \`module/context\` in the name.
- Create explicit export configuration per bean with an ObjectName computed from a validated module identifier.
- Let annotation metadata describe the management interface while the exporter/naming strategy determines the instance name if that combination is supported by your configuration.

Do not rely on a bean name in the Spring container to automatically produce a unique ObjectName without verifying the actual naming strategy.

## 8. Choosing a Naming Convention for Multiple Contexts

Example convention:

\`\`\`text
<domain>:type=<type>,context=<context>,name=<resource>
\`\`\`

Example:

\`\`\`text
com.example.platform:type=Cache,context=root,name=ProductCache
com.example.platform:type=Worker,context=inventory,name=Primary
com.example.platform:type=Worker,context=billing,name=Primary
\`\`\`

For multiple instances of the same module:

\`\`\`text
com.example.platform:type=Worker,context=inventory,instance=node-1
com.example.platform:type=Worker,context=inventory,instance=node-2
\`\`\`

Choose stable keys, avoid embedding sensitive data, and avoid continuously changing values such as current queue size. If a process only runs a single instance of a module, do not invent dummy keys that needlessly complicate names.

### 8.1. Canonical name and collisions

Two ObjectNames with the same domain and same key/value pairs are equivalent even if key order differs:

\`\`\`text
demo:type=Worker,module=billing
demo:module=billing,type=Worker
\`\`\`

Do not try to solve a collision by reordering keys. Only changing the namespace or identity creates a distinct ObjectName.

### 8.2. Querying by module/context

\`\`\`java
import javax.management.ObjectName;

ObjectName inventoryPattern = new ObjectName(
    "com.example.platform:context=inventory,*");
\`\`\`

The \`,*\` allows additional keys such as \`type\` and \`name\`. Without \`,*\`, the pattern may require the key set to contain only \`context\`, returning empty results even when many resources exist.

## 9. Parent–Child Contexts: Bean Visibility and Lifecycle

Parent/child contexts have an asymmetric lookup relationship:

\`\`\`text
Parent can see its own beans.
Child may resolve beans from parent.
Parent does not automatically enumerate child beans.
\`\`\`

If the root context has an autodetecting exporter, do not assume it automatically discovers beans declared only in the child. If the child has its own exporter, verify scan and registration scope to prevent re-exporting management beans owned by the parent.

A clear division of responsibilities:

- The root exporter owns MBeans of shared services in root.
- The child exporter only registers MBeans specific to the child.
- ObjectNames distinguish root/child.
- Each exporter only unregisters MBeans it manages.
- Child contexts are closed before the parent closes if application lifecycle depends on the parent.

In a complex Spring application, tests should compare \`queryNames\` on the same server before and after creating and closing the child context to confirm accurate ownership.

## 10. RegistrationPolicy Does Not Replace Namespace Design

Spring provides policies when an exporter encounters an already-existing ObjectName:

| Policy | Behavior | Impact in Multiple Contexts |
|---|---|---|
| \`FAIL_ON_EXISTING\` | Fails on duplicate name | Detects collisions quickly |
| \`IGNORE_EXISTING\` | Skips new registration | Can hide that the new context was not exported |
| \`REPLACE_EXISTING\` | Replaces MBean with the same name | Can overwrite another context's resource, complicating cleanup |

\`FAIL_ON_EXISTING\` is a good illustrative choice because errors have clear semantics. \`IGNORE_EXISTING\` does not solve the case where another context wants to expose its own MBean. \`REPLACE_EXISTING\` requires extreme caution when contexts have independent lifecycles; closing one context after it replaced another context's registration can produce unpredictable outcomes.

If both modules A and B need MBeans, give each module a unique ObjectName instead of relying on a policy to decide who wins.

## 11. Exporter Lifecycle and Cleanup

With \`MBeanExporter\`, the Spring lifecycle typically includes:

\`\`\`text
Context refresh
    |
    v
Exporter initialized
    |
    v
Register owned MBeans
    |
    v
Context running
    |
    v
Context closes
    |
    v
Exporter unregisters owned MBeans
\`\`\`

Practical situations that can complicate the lifecycle:

- An exporter registers objects on an \`MBeanServer\` shared by multiple contexts.
- A plugin becomes unreferenced without its context being closed.
- An object was registered via manual code outside the exporter.
- An MBean already existed before the exporter initialized.
- Context initialization fails partway through and registration only partially completes.
- A policy replaces another exporter's registration.

Therefore, verify directly via \`MBeanServer.isRegistered\` and \`queryNames\` after each context creation/close milestone. Do not unregister every name sharing a domain when a module stops, because those names may belong to another context.

## 12. Separating MBeanServer per Context: When Is It Needed?

Having multiple contexts does not force creating multiple \`MBeanServer\` instances. However, dedicated servers are useful in certain cases:

### 12.1. Isolated testing

A dedicated server avoids colliding with the platform \`MBeanServer\`:

\`\`\`java
MBeanServer isolated =
    javax.management.MBeanServerFactory.newMBeanServer();
\`\`\`

Inject this server into the test's exporter. When the test finishes, close the context and release the fixture.

### 12.2. Isolated module management

A plugin system can assign each plugin its own server, though you must solve how clients find those servers and whether separate connectors are needed. JConsole attaching to the platform \`MBeanServer\` does not automatically browse other servers.

### 12.3. A unified management endpoint

If the operational requirement is one place to view all MBeans, using a shared server is usually simpler. Splitting servers complicates operations/monitoring because multiple sources must be attached or aggregated.

Weigh observability, access permissions, and lifecycle before choosing.

## 13. Integration Testing for Multiple ApplicationContexts

The goal is testing **registration results in \`MBeanServer\`**, not merely checking that the \`ApplicationContext\` contains beans.

Conceptual test example:

\`\`\`java
import org.junit.jupiter.api.Test;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;

import static org.junit.jupiter.api.Assertions.*;

class MultiContextJmxTest {
    @Test
    void eachModuleOwnsItsRegistration() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName inventoryName = new ObjectName(
            "example.jmx:type=ModuleMonitor,module=inventory");
        ObjectName billingName = new ObjectName(
            "example.jmx:type=ModuleMonitor,module=billing");

        // Create contexts per MultipleContextsDemo, retaining references.
        // After both contexts refresh:
        assertTrue(server.isRegistered(inventoryName));
        assertTrue(server.isRegistered(billingName));

        // After closing the inventory context:
        // assertFalse(server.isRegistered(inventoryName));
        // assertTrue(server.isRegistered(billingName));

        // After closing the billing context:
        // assertFalse(server.isRegistered(billingName));
    }
}
\`\`\`

This snippet presents the core assertions; wire actual context setup/teardown from the earlier example to make it runnable. For parallel tests, use a dedicated \`MBeanServer\` instead of the platform server; avoid having two tests write to the global registry simultaneously.

Cases to include:

1. Two contexts start successfully with distinct ObjectNames.
2. Querying by module returns the right set of MBeans.
3. Closing context A removes only A's MBeans.
4. Context B continues serving attribute reads normally.
5. Restarting A does not report a duplicate error.
6. Intentionally collide names and observe the \`FAIL_ON_EXISTING\` error.
7. If annotation exporters are enabled in parent/child, verify shared beans are not exported twice.
8. If using a dedicated server, verify clients must connect to the right server to see the objects.

## 14. Troubleshooting Multiple ApplicationContexts

| Symptom | Typical Cause | Inspection Step |
|---|---|---|
| \`InstanceAlreadyExistsException\` | Multiple exporters use the same ObjectName | Check exporters, naming strategy, server |
| MBean appears once, but module B is missing | \`IGNORE_EXISTING\` masks collision | Compare names and policy, fix namespace |
| Root MBean present, child MBean missing | Root exporter does not see child beans | Check \`BeanFactory\` scope and child's exporter |
| Child closed yet MBean remains | Context not closed or manual registration | Check exporter ownership/unregistration |
| Closing A removes B's MBean | Shared name and replace policy | Avoid cross-replacement; assign distinct names |
| MBean exists in dedicated server but missing in JConsole | Client connected to platform server | Check \`MBeanServer\` selected by exporter |
| Same MBean appears twice under different names | Two exporters both export one resource | Assign a single owner |
| Remote JMX does not see bean | Connector attached to wrong server or transport error | Check connector and server reference |
| Context reload fails | Old MBean not cleaned up or name unchanged | Trace lifecycle and registration policy |

When debugging, gather evidence in order:

\`\`\`text
1. How many ApplicationContexts are active?
2. Which exporter does each context define?
3. Which MBeanServer does each exporter use?
4. Which ObjectNames does each exporter register?
5. Which beans belong to which context?
6. After close/reload, which names remain registered?
7. Is the client connecting to the right server?
\`\`\`

Do not change \`RegistrationPolicy\` immediately upon seeing a duplicate error before identifying the true owner.

## 15. Security Boundaries and Remote Connectors

Multiple contexts do not automatically create JMX security boundaries. If all exporters share one \`MBeanServer\` and remote connector, a client connecting to that server may see multiple modules, depending on security mechanisms and access controls.

- Namespaces in ObjectNames aid organization and search; they **do not enforce authorization**.
- \`RegistrationPolicy\` does not grant access permissions.
- Creating a dedicated server only creates a registry boundary; you must still design connections and authorization if exposed remotely.
- Management operations with side effects should restrict permissions and include appropriate auditing.
- Do not put secrets or sensitive data into ObjectNames or attributes.
- Remote JMX must use a dedicated management network, authentication, and encryption per operational policy.

If modules have vastly different trust levels, design access control at the connector layer or appropriate management mechanism; do not assume having separate \`ApplicationContext\` instances isolates privileges.

## 16. Hands-On Exercises

### Exercise A — Two contexts, one server

Create modules A and B sharing the platform \`MBeanServer\`. Each module has a \`ModuleMonitor\` and \`MBeanExporter\`. Register:

\`\`\`text
training.multictx:type=Module,name=A
training.multictx:type=Module,name=B
\`\`\`

Verify both MBeans coexist and attributes can be read. Close A and verify B still works.

### Exercise B — Intentional collision

Change A and B's ObjectNames to match. Use \`FAIL_ON_EXISTING\` and record the error; try \`IGNORE_EXISTING\` in a lab environment and explain why B is not exported as intended.

### Exercise C — Parent/child contexts

Create a parent holding a shared service and a child holding a module service. Enable annotation export in each context per your chosen strategy. Check \`queryNames\` to confirm each MBean is registered once and who owns cleanup.

### Exercise D — Plugin reload

Create and close a plugin context three times. Use the same ObjectName across runs, though not concurrently. After each close, verify \`isRegistered=false\`. If it fails, trace cleanup instead of hiding the bug with \`REPLACE_EXISTING\`.

### Exercise E — Test isolation

Run two integration tests using the same ObjectName while injecting a separate \`MBeanServerFactory.newMBeanServer()\` into each test. Explain why there is no collision and why JConsole does not see these test registries by default.

## 17. Self-Check Questions

1. Why can ObjectNames collide even when two beans belong to different \`ApplicationContext\` instances?
2. Does a root exporter automatically see every bean in a child context?
3. When should a single centralized exporter be used?
4. Does \`IGNORE_EXISTING\` solve a missing namespace?
5. Why is \`REPLACE_EXISTING\` dangerous when contexts have independent lifecycles?
6. Does closing a context automatically unregister an MBean registered manually outside the exporter?
7. Does a dedicated \`MBeanServer\` make platform JMX clients see its beans?
8. What problem does a naming strategy solve when the same class is reused?
9. In Spring, which exporter is responsible for unregistering MBeans when a plugin stops?
10. Does separating contexts equate to separating remote JMX access permissions?

## 18. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`AnnotationMBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — \`@EnableMBeanExport\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html

**Key takeaway:** across multiple \`ApplicationContext\` instances, each exporter needs clear ownership, connection to the right \`MBeanServer\`, unique ObjectNames, and lifecycle-aligned cleanup. When these boundaries are properly designed, annotation export becomes a reliable management mechanism across the entire application.
