# Limiting Autodetection Scope in Large Contexts — Spring Framework JMX

## Objectives

In Spring Framework JMX, **autodetection** is the mechanism allowing \`MBeanExporter\` to automatically find eligible beans and register them as MBeans. This mechanism is convenient for small applications: there is no need to list every bean manually in the export configuration. However, a large \`ApplicationContext\` can contain hundreds or thousands of beans, multiple modules, AOP proxies, Spring infrastructure, lazy-initialized beans, parent/child contexts, and integrated libraries. When autodetection is enabled too broadly, the risk is not just slower startup: beans can be exported by mistake, ObjectNames can collide, the management surface grows, bean lifecycles can change, and it becomes hard to tell which exporter owns a registration.

This lesson explains how to define and narrow the set of discovered beans so that JMX exposes only deliberately chosen management components.

After this lesson, you will be able to:

- Distinguish \`MBeanExporter\` bean autodetection, explicit-list export, and \`AnnotationMBeanExporter\` using metadata annotations.
- Understand the role of \`autodetect\`, \`autodetectMode\`, and the modes \`AUTODETECT_NONE\`, \`AUTODETECT_MBEAN\`, \`AUTODETECT_ASSEMBLER\`, and \`AUTODETECT_ALL\` in Spring API versions that support them.
- Recognize the effects of BeanFactory, bean names, proxies, parent/child contexts, and lazy initialization.
- Choose between explicit registration, management adapters, metadata naming strategies, restricted assemblers, and context scoping.
- Manage \`ObjectName\`, registration policies, lifecycle, and JMX access permissions.
- Verify exactly which MBeans are actually exported using \`MBeanServer.queryNames\` and \`MBeanInfo\`.
- Build a predictable export strategy for large Spring applications.

## 1. What Is Autodetection and Why Must Scope Be Limited?

A typical exporter can work in two directions:

\`\`\`text
Approach A: Explicit declaration
  MBeanExporter
    ├── workerStatus  → com.example:type=Worker,name=Import
    └── cacheStatus   → com.example:type=Cache,name=Catalog

Approach B: Autodetection
  ApplicationContext / BeanFactory
    ├── workerService
    ├── cacheService
    ├── paymentService
    ├── dataSource
    ├── taskExecutor
    ├── metricsRegistry
    ├── workerStatus
    └── ...
          |
          v
    MBeanExporter autodetection
          |
          v
    Select beans by exporter / assembler / metadata criteria
          |
          v
    MBeanServer
\`\`\`

**Autodetection does not necessarily mean exporting every Spring bean.** It means the exporter evaluates a set of candidates from the BeanFactory against configured criteria. Which subset gets exposed depends on the exporter type, MBean type, \`MBeanInfoAssembler\`, naming strategy, and autodetect mode.

In large contexts, the main concern is two sets:

- **The set of beans existing in the Spring context**: serving full application needs.
- **The set of beans that should be managed via JMX**: only a small subset, chosen for operational needs.

The goal is to ensure the second set does not automatically swell with every change to the first set.

## 2. Four Scope Dimensions to Distinguish

### 2.1 BeanFactory/ApplicationContext Scope

An exporter is created inside a Spring context and can look up beans in the corresponding BeanFactory according to its mechanism. In systems with parent/child contexts, do not assume the exporter sees only the beans you directly wrote in one package.

A large context can combine many configuration classes and imported modules. When multiple exporters are created in related contexts, a bean may be evaluated for export multiple times if scope and naming are not clearly organized.

### 2.2 MBean Candidate Scope

Not every bean is a Standard MBean, MXBean, or carries metadata annotations. The autodetect mode determines which kind of candidate set is evaluated. This is the first limiting layer: only beans matching a management contract should belong to the candidate set.

### 2.3 JMX Name Scope

Each exported candidate needs a unique \`ObjectName\` in the **target MBeanServer**. An \`ObjectName\` consists of a domain and key properties:

\`\`\`text
com.example.operations:type=Worker,name=Import,instance=node01
\`\`\`

Two different beans can be assigned the same name if the naming strategy does not distinguish instances. Changing \`defaultDomain\` does not automatically make bean names unique if key properties still collide.

### 2.4 Control Privilege Scope

A bean with state-mutating methods, if exported, can add control operations over JMX. Even when autodetection scope is narrowed, you still must decide which attributes/operations are permitted to be exposed and which roles have permission to invoke them. Limiting bean detection is a surface-reduction step, **not** the entire security mechanism.

## 3. MBeanExporter Mechanism and Autodetection Modes

Spring's \`org.springframework.jmx.export.MBeanExporter\` is the component that registers beans into an \`MBeanServer\`. Alongside explicit \`beans\` mapping, Spring JMX offers autodetection options appropriate to each API generation.

Known mode constants in \`MBeanExporter\`:

| Mode | Idea |
|---|---|
| \`AUTODETECT_NONE\` | Do not automatically scan for beans to export |
| \`AUTODETECT_MBEAN\` | Focus on beans already meeting standard MBean forms, such as eligible Standard MBeans/MXBeans |
| \`AUTODETECT_ASSEMBLER\` | Use \`MBeanInfoAssembler\` to determine which beans can be exported |
| \`AUTODETECT_ALL\` | Combine the corresponding autodetection paths |

The exact activation method and available setters/constants must match the Spring Framework version you are running. In configurations using \`AnnotationMBeanExporter\`, bean selection is guided by \`@ManagedResource\` metadata and the corresponding assembler, rather than merely by a mode name.

Decision model:

\`\`\`text
Bean candidate
    |
    +--> Is it an MBean by JMX convention?
    |       |
    |       +--> May belong to autodetect MBEAN
    |
    +--> Does the Assembler support this bean?
            |
            +--> May belong to autodetect ASSEMBLER
\`\`\`

**Do not enable \`AUTODETECT_ALL\` just “to be safe”.** In a large context, this can expand the MBean list beyond plan. Start from the management needs to expose and choose the smallest mode that meets the requirement.

## 4. Explicit Export: The Clearest Boundary

When JMX is treated as an intentional operational API, the surest approach is declaring each management bean individually:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public MBeanExporter mbeanExporter(
            WorkerStatus workerStatus,
            CacheStatus cacheStatus) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(ManagementFactory.getPlatformMBeanServer());

        exporter.setBeans(Map.of(
            "com.example.ops:type=Worker,name=Import", workerStatus,
            "com.example.ops:type=Cache,name=Catalog", cacheStatus
        ));

        exporter.setAutodetect(false);
        return exporter;
    }
}
\`\`\`

Here \`WorkerStatus\` and \`CacheStatus\` are management adapters or beans conforming to an appropriate MBean contract. The example uses \`setAutodetect(false)\` to express that only the \`setBeans(...)\` list is within export scope. Check the API and configuration used in your Spring version; if the beans are just plain POJOs, the exporter needs an appropriate \`MBeanInfoAssembler\` or corresponding JMX interface to register validly.

Benefits:

- Code reviews show every \`ObjectName\` explicitly.
- Adding a new Spring bean does not automatically increase the number of MBeans.
- Management adapters can be separated from business services.
- Registration ownership is easy to identify when the context closes.
- You can test the expected list of names rather than just counting totals.

Drawback: adding or removing an MBean requires updating configuration. This is usually an acceptable cost if the JMX surface needs stability and is operated by multiple tools.

## 5. Selective Annotation Usage

In applications standardized on annotation-based JMX, one way to limit scope is to **attach \`@ManagedResource\` only to beans genuinely used for management**, rather than marking every service broadly.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Worker,name=Import",
    description = "Read-only import worker monitoring")
public class ImportWorkerMonitor {

    private final ImportWorkerService worker;

    public ImportWorkerMonitor(ImportWorkerService worker) {
        this.worker = worker;
    }

    @ManagedAttribute
    public long getCompletedCount() {
        return worker.completedCount();
    }

    @ManagedAttribute
    public String getEffectiveState() {
        return worker.effectiveState();
    }
}
\`\`\`

\`ImportWorkerService\` is the business processing service and does not necessarily have JMX metadata. The \`ImportWorkerMonitor\` adapter is a small object dedicated to reading state and exporting only the necessary attributes.

Enabling export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(
    server = "jmxServer",
    defaultDomain = "com.example.ops"
)
public class JmxAnnotationsConfiguration {
}
\`\`\`

With this configuration, a Spring bean named \`jmxServer\` of type \`MBeanServer\` is required, and you must ensure no other exporter registers \`ImportWorkerMonitor\` under the same \`ObjectName\`. \`defaultDomain\` helps set the domain for names generated by the naming strategy; it does not override a full ObjectName already declared in \`@ManagedResource\`.

**Important note:** annotation-driven export helps select beans by metadata, but you still need to limit the number of annotated beans, the context scope where the exporter operates, and other auto-configuration mechanisms. Putting annotations on hundreds of services can still create a large management surface.

## 6. Limiting Based on Naming/Assembler

An \`MBeanInfoAssembler\` determines attribute and operation metadata for exported beans. In some configurations, the assembler's \`includeBean\` capability is used to select beans eligible for autodetection.

You can build a strategy where only beans belonging to a management group are allowed through the assembler. Conceptual example:

\`\`\`text
ApplicationContext
  ├── domain.*        → do not export
  ├── repositories.*  → do not export
  ├── integrations.*  → do not export
  └── management.*    → evaluated for export
\`\`\`

However, do not assume **Spring component scanning** and **JMX autodetection** share the same package filter. \`@ComponentScan\` decides which beans are registered in the ApplicationContext, not which beans the exporter allows. If you exclude \`domain.*\` from Spring component scanning just to restrict JMX, you can accidentally drop business beans and break application startup.

Instead, control via:

1. Explicit export lists.
2. Clearly annotated management adapters.
3. An appropriate \`MBeanInfoAssembler\` or \`AutodetectCapableMBeanInfoAssembler\` with specific inclusion criteria.
4. Module-level or dedicated context exporter configuration.
5. Tests verifying the actually registered \`ObjectName\`s and operations.

### 6.1 Why Not Filter by Package Using Simple Reflection?

A Spring bean may be created by a JDK proxy, CGLIB proxy, or factory. \`bean.getClass().getPackageName()\` can return the proxy's package rather than reflecting the target service's package. When selecting beans by name, type metadata, or annotations, you must understand how Spring handles proxies/target classes and factory beans.

In large organizations, a dedicated management marker or interface is usually more reliable than complex heuristic logic on class names. If using a custom assembler/filter, test it with normal beans, proxied beans, and lazy beans.

## 7. Multiple ApplicationContexts: Scan Boundaries and Responsibility

An application can have:

\`\`\`text
JVM
├── Parent ApplicationContext
│    ├── common metrics
│    └── shared services
├── Web ApplicationContext
│    ├── controllers
│    └── web monitors
└── Batch ApplicationContext
     ├── workers
     └── batch monitors
\`\`\`

If each context has an automatic exporter, some beans or names may be exposed multiple times depending on bean visibility and configuration. Common collision:

\`\`\`text
Parent exporter:
  com.example:type=Worker,name=Import

Batch exporter:
  com.example:type=Worker,name=Import
\`\`\`

Because both register into the same platform MBeanServer, \`ObjectName\` collides. Replacement registration policies should not be used as a default solution because one context could unregister another context's registration during shutdown.

A safer structure:

- Shared infrastructure MBeans are owned by the parent context.
- Web module MBeans are owned by the web context with a dedicated namespace.
- Batch module MBeans are owned by the batch context with a dedicated namespace.
- Each registration has exactly one exporter/owner.
- When a context stops, only the MBeans managed by that context are removed.

There is no need to create a new MBeanServer per module just to separate namespaces; multiple domains/key properties can coexist on one server. However, when isolation is genuinely needed, a separate server also requires properly managed connectors and lifecycles.

## 8. Lazy Initialization and Autodetection Side Effects

In large contexts, many beans are configured as lazy to reduce startup time and initial resource usage. Scanning or creating MBean wrappers can instantiate beans earlier than expected, depending on how the exporter looks up candidates and initializes instances.

Example:

\`\`\`java
@Lazy
@Component
public class ExpensiveDiagnosticService {
    public ExpensiveDiagnosticService() {
        // Initialize connections, warm up caches, or large structures.
    }
}
\`\`\`

If the exporter autodetects and creates this bean during startup, the benefits of lazy initialization can be lost. Furthermore, an MBean getter performing I/O on first call can allocate resources operators did not expect.

To avoid this:

- Do not export heavy services just for one or two metrics.
- Use lightweight adapters reading metrics from existing sources.
- Clearly decide whether eager MBean registration is needed.
- Avoid JMX getters that allocate large objects or trigger network calls.
- Monitor bootstrap time, number of initialized beans, and CPU/heap after enabling JMX.

Do not claim every autodetection mode always initializes all lazy beans; exact behavior depends on the BeanFactory, exporter, assembler, and framework version. Yet in production design, this is a risk worth measuring and testing.

## 9. MBeanExporter, AnnotationMBeanExporter, and Boot Auto-Configuration

A common issue is multiple mechanisms running together:

\`\`\`text
@SpringBootApplication
  |
  +-- Boot JMX auto-configuration (if enabled)
  |
  +-- @EnableMBeanExport declared by project
  |
  +-- @Bean MBeanExporter declared by module
\`\`\`

Without demarcated scope, the same bean can be evaluated for export by multiple exporters. When both register the same ObjectName on the same server, \`InstanceAlreadyExistsException\` can arise, or if policy allows replacement, ownership problems occur.

Before adding a new exporter to a large context, know:

- Which export mechanisms are currently enabled?
- Which MBeanServer does each exporter use?
- Which ObjectNames does each exporter manage?
- Is any bean being exported twice?
- Who manages Spring Boot/Actuator or library MBeans?

Spring Boot has JMX-related properties depending on version, but do not copy a property from an old example without checking actual behavior. Specifically, \`spring.jmx.enabled\` affects JMX export via auto-configuration in supported Boot versions; it is not a substitute for namespace/authorization design.

## 10. Which Choice Fits Context Size?

| Context | Recommended Choice | Reason |
|---|---|---|
| Small app, few MBeans with clear contracts | Selective annotation-based autodetection | Simple, minimal declarations |
| Multi-module app, hundreds of beans | Explicit \`setBeans\` or dedicated adapter set | Scope is easy to verify |
| Libraries providing Standard MBeans/MXBeans | Limited MBEAN autodetect or explicit registration | Matches pre-defined contract |
| Multiple contexts sharing platform server | Dedicated namespace + exporter ownership | Avoids collisions and wrong cleanup |
| Services with sensitive business operations | Read-only adapter / small interface | Reduces control surface |
| Heavy lazy beans present | Lightweight adapter, measure bootstrap, avoid broad scanning | Keeps initialization cost under control |
| Strict security requirements | Export allowlist + connector access control | Autodetection is not a security boundary |
| Many clients depending on stable ObjectNames | Explicit names and contract tests | Prevents unintended changes in generated names |

A helpful guiding question: **“If another team adds 50 Spring beans next week, does it make sense for the number of MBeans to grow with them?”** If not, autodetection configuration should be narrowed until adding ordinary beans does not automatically change the JMX API.

## 11. Assigning Clear ObjectNames to Reduce Risks When Scanning Broadly

When an exporter generates names, they often depend on bean name, naming strategy, default domain, and metadata. Across many modules, short names easily collide:

\`\`\`text
workerMonitor
cacheMonitor
status
health
\`\`\`

These names are insufficient to distinguish beans if multiple contexts share one server. ObjectNames by domain and key properties are clearer:

\`\`\`text
com.example.inventory:type=Worker,name=Import,context=batch
com.example.orders:type=Worker,name=Fulfillment,context=web
com.example.shared:type=Cache,name=Catalog,context=parent
\`\`\`

Not every system is required to have a \`context\` key; choose semantically stable keys that distinguish instances actually coexisting in one server. If an application has multiple separate JVMs, identical ObjectNames in two JVMs do not collide, though monitoring may need host/instance metadata to distinguish sources.

Some naming mistakes:

- Misunderstanding default domain as the domain for every bean including those with explicit ObjectNames.
- Names with special characters without using \`ObjectName.quote\`/appropriate constructors.
- Putting user IDs, tokens, request parameters, or personal data in ObjectNames.
- Using a random UUID per startup, preventing dashboards from tracking MBeans stably.
- Two exporters generating the same \`type/name\` in the same domain and MBeanServer.

## 12. Narrowing Operation Scope, Not Just Bean Scope

An exporter might select only the right three beans, yet one of those three exposes a \`purgeAllData()\` operation. Therefore, two control dimensions must remain independent:

\`\`\`text
Dimension 1 — Bean selection
   Should this bean become an MBean?

Dimension 2 — Member selection
   If yes, which attributes/operations are exposed?
\`\`\`

Standard MBean/MXBean interfaces restrict members by contract. Spring annotations specify methods via \`@ManagedAttribute\`, \`@ManagedOperation\` when using the right metadata assembler. For beans using other assemblers, check the member inclusion policy.

Even after narrowing the MBean set, do not expose getters revealing secrets or state-changing operations without permissions, input validation, and auditing. Separate read-only management adapters or control adapters when needed, though splitting MBeans does not automatically enforce authorization if clients still have invoke permissions on the same connector.

## 13. Verifying Actual Scope on MBeanServer

The best way to know what the exporter registered is querying the right server:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.ops:*"),
    null
);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

This result only reflects MBeans in the **platform server** queried at that moment. If the exporter uses a separate server, query that exact separate server. \`queryNames\` is a snapshot: it may differ while a context is starting up or shutting down.

To check members:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

for (ObjectName name : names) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("MBean: " + name.getCanonicalName());
    for (MBeanOperationInfo op : info.getOperations()) {
        System.out.println("  operation: " + op.getName());
    }
}
\`\`\`

If only two operations were expected but more appear, it may indicate the assembler/export path differs from the contract. Avoid merely counting total JVM MBeans because the server also holds Java platform MXBeans and other libraries' MBeans.

## 14. Integration Testing to Lock Down Export Scope

In a large application context, tests should verify the expected set of ObjectNames in the dedicated domain rather than merely asserting that the exporter bean exists.

Skeleton example:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JmxScopeIntegrationTest {

    @Test
    void onlyExpectedOperationsMBeansAreVisible() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxExportConfiguration.class,
                    WorkerStatus.class,
                    CacheStatus.class)) {

            Set<ObjectName> actual = server.queryNames(
                new ObjectName("com.example.ops:*"), null);

            Set<ObjectName> expected = Set.of(
                new ObjectName(
                    "com.example.ops:type=Worker,name=Import"),
                new ObjectName(
                    "com.example.ops:type=Cache,name=Catalog")
            );

            assertEquals(expected, actual);
        }
    }
}
\`\`\`

This is a conceptual test pattern: \`WorkerStatus\` and \`CacheStatus\` must be defined and must be valid MBeans; the test context fixture must avoid registering beans twice; and the \`com.example.ops\` namespace must not contain MBeans from other tests. For parallel tests, create a separate MBeanServer or assign independent namespaces. Tests should not delete all ObjectNames sharing a domain during cleanup as that may remove unowned MBeans.

Test extensions:
- Assert the absence of forbidden MBeans.
- Assert the list of operations/attributes via \`MBeanInfo\`.
- Close the context and verify the exporter's registrations are removed.
- Assert the platform MBeanServer remains active; do not release the shared server.
- If proxies/lazy beans exist, verify startup behavior with dedicated fixtures.

## 15. Monitoring Performance When Changing Autodetection

A JMX configuration change should have at least several observations:

| Signal | Meaning |
|---|---|
| Number of registered application MBeans | Detects abnormal growth in management surface |
| Context startup time | Measures autodetection/registration overhead |
| Number of lazy beans initialized at boot | Detects scanning side effects |
| MBean registration exceptions | Detects ObjectName collisions and config errors |
| CPU/heap allocation during export | Identifies heavy introspection or wrappers |
| Number of active exporters | Detects double-export from auto-configuration |
| Number of management operations with side effects | Controls the control surface |

These numbers must be measured against an actual application baseline; there is no universal threshold like “more than 100 MBeans is too many”. A multi-module system may intentionally expose hundreds of MBeans, provided that stems from a clear contract rather than indiscriminate scanning.

## 16. Common Mistakes

### 16.1 Enabling autodetect and relying on defaults

**Problem:** the exporter may discover more beans than the author realized, especially when new libraries or modules are added.

**How to handle:** determine the actual mode, use \`AUTODETECT_NONE\`/disable autodetect when needed, and declare explicit lists or selective annotations.

### 16.2 Using @ComponentScan exclude to “hide from JMX”

**Problem:** beans excluded from the Spring context may be required business dependencies.

**How to handle:** restrict the exporter or assembler; never alter Spring bean registration just to narrow JMX.

### 16.3 Believing @ManagedResource on a bean has zero overhead

**Problem:** too many management beans, especially heavy/lazy ones, can increase bootstrap and metadata costs.

**How to handle:** lightweight management adapters, intentional annotations, and performance measurement.

### 16.4 Multiple exporters detecting the same bean

**Problem:** collisions or one context shutting down accidentally removing another context's registrations.

**How to handle:** one owner per registration, clear namespaces, and clear exporter scopes.

### 16.5 Checking ObjectName only and forgetting operations

**Problem:** the MBean has the right name but contains operations that should not be exposed.

**How to handle:** check \`MBeanInfo.getOperations()\`, writable attributes, and negative contract tests.

### 16.6 Assuming domains are security boundaries

**Problem:** all MBeans in the same server can be viewed by any client with sufficient privileges regardless of domain.

**How to handle:** authentication, authorization, TLS, network isolation, and separating servers/connectors when truly necessary.

### 16.7 Deleting all domain-matching MBeans on startup error

**Problem:** may delete MBeans belonging to another context, library, or application.

**How to handle:** only unregister ObjectNames that this exporter/component successfully registered and owns.

## 17. Runbook for Limiting Autodetection Scope

### Before deployment

1. List the exact management capabilities needed, rather than starting from the entire bean list.
2. Choose export mode: explicit, annotation-based, or limited MBean autodetect.
3. Define domain/ObjectName, owner, MBeanServer, and connector used by clients.
4. Classify side-effecting operations and remove methods that should not be exported.
5. Inspect related contexts and active auto-configurations.
6. Have integration tests for expected/forbidden ObjectNames and metadata.

### On startup

1. Watch for \`NotCompliantMBeanException\`, \`InstanceAlreadyExistsException\`, or naming errors.
2. Inspect actual MBeans on the right server with \`queryNames\`.
3. Compare the name set against the expected contract, not just total registry count.
4. Check startup time/lazy bean initialization if the exporter changed.

### On shutdown and redeploy

1. Close the module's context/exporter.
2. Ensure registrations owned by that context are removed.
3. Keep platform MXBeans and other contexts' MBeans intact.
4. Restart to verify there are no collisions and no stale MBeans.

## 18. Applied Exercises

**Exercise 1 — Large context.** A context has 800 beans, but only 6 beans need management. Would you choose broad autodetect or explicit export? Explain maintenance cost and ObjectName contract testability.

**Exercise 2 — Two exporters.** Spring Boot auto-configuration already enabled JMX, and a new module declares \`@EnableMBeanExport\`. What can happen? Design how to determine which exporter is responsible, avoid duplicate MBeans, and verify \`ObjectName\`.

**Exercise 3 — Lazy bean.** A diagnostic service is marked \`@Lazy\` yet starts initializing at startup after autodetection is enabled. Propose how to measure it and replace it with a lightweight management adapter.

**Exercise 4 — Negative contract.** Write a test proving the \`com.example.ops\` domain contains only the 2 permitted ObjectNames and does not have the \`deleteAllData\` operation. State why negative tests matter.

**Exercise 5 — Parent/child contexts.** The parent context holds shared metrics, and the child context holds batch workers. Design namespaces, owners, and cleanup so child shutdown does not make parent MBeans disappear.

**Exercise 6 — MBeanInfoAssembler.** A custom assembler can export many public methods on a bean. Explain why selecting the right bean is not enough to protect the management API and how checking metadata reveals risks.

## Summary

In Spring Framework JMX, autodetection is useful for reducing configuration but should not turn a large \`ApplicationContext\` into an uncontrolled management surface. Limit scope through **explicit export, selective annotations, management adapters, appropriate assemblers, and clear ownership**. Alongside that, separate bean selection from attribute/operation selection, define stable ObjectNames, check impact on lazy beans/proxies, and verify the actual registry via \`MBeanServer\`. The design succeeds when adding new business beans does not accidentally create new MBeans or management operations and when each registration has a single owner responsible throughout its lifecycle.
