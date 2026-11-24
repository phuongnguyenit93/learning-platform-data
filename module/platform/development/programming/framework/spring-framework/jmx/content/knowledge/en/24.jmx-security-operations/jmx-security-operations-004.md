# Reducing Surface Area by Exporting Only Necessary MBeans in Spring Framework JMX

## 1. Why Is Export Scope a Security Decision?

JMX (Java Management Extensions) helps monitor and control a running Java application. When using Spring Framework, beans can be exported to an `MBeanServer` via `MBeanExporter`, `AnnotationMBeanExporter`, `@ManagedResource`, or an equivalent configuration mechanism. Tools such as JConsole and JMX collectors can then discover ObjectNames, read attributes, and invoke operations.

What is convenient for operations also creates a **privileged management surface**: the more MBeans, attributes, and operations are exposed, the more internal capabilities are opened to clients with JMX access. This is the **management attack surface**, distinct from the HTTP API yet still requiring design, inventory, and protection.

For example, a service has these methods:

```java
public class PaymentService {
    public long getProcessedPayments() { /* ... */ }
    public String getStatus() { /* ... */ }
    public String getApiToken() { /* ... */ }
    public void clearPendingPayments() { /* ... */ }
    public void retryFailedPayment(String id) { /* ... */ }
}
```

Operators might only need `ProcessedPayments` and `Status`. If you accidentally export `ApiToken`, `clearPendingPayments`, and `retryFailedPayment` as well, JMX expands the ability to read sensitive data and mutate business state.

**Core principle:** only export MBeans genuinely needed for management, and inside each MBean only expose approved attributes/operations.

This lesson explains how to reduce surface area at three levels: **the number of MBeans**, **the capabilities of each MBean**, and **which clients can access them**.

## 2. Three Layers of the JMX Surface Area

```text
                JVM / Spring Application
                         |
           +-------------+-------------+
           |                           |
   Spring business beans         Platform MXBeans
           |                           |
     MBeanExporter                     |
           |                           |
           +---------- MBeanServer ----+
                           |
                     JMX connector
                           |
                JConsole / monitoring
```

Layers to control:

| Layer | Examples | Design Question |
|---|---|---|
| **Resource exposure** | `OrderMonitor`, `CacheAdmin`, `PaymentConfig` | Which beans actually need to become MBeans? |
| **Method/data exposure** | `getQueueDepth()`, `resetCounters()`, `getPassword()` | Which metrics and operations should be exposed? |
| **Connection exposure** | Local attach, remote JMX RMI, monitoring agent | Which clients are allowed to connect, read, or control? |

Reducing the number of MBeans does not replace connector authentication. Conversely, having authentication does not mean you should export every bean. Good design uses **defense in depth**: reduce exposed data and capabilities first, then restrict clients and transport paths.

In addition to application-created MBeans, the JVM has platform MXBeans for memory, threads, class loading, runtime, and garbage collection. Therefore, even without exporting any custom MBean, a JMX connector can still provide substantial diagnostic information. “Only exporting necessary MBeans” is an important measure, yet **it does not make the entire JMX interface disappear**.

## 3. Classifying MBeans Before Deciding to Export

Do not export every bean merely because it exists in the `ApplicationContext`. Group them into categories:

### 3.1. Operational Observability Group

MBeans that only expose status and aggregated metrics:

```text
QueueMonitor
  QueueDepth
  ProcessedTotal
  ConsumerState

CacheMonitor
  HitCount
  MissCount
  EstimatedEntryCount
```

This is typically the preferred group when there is a clear monitoring goal. Getters should be fast, avoid accessing raw user data, and avoid running long tasks.

### 3.2. Restricted Control Group

MBeans with operations or writable attributes:

```text
QueueControl
  pause()
  resume()

CacheAdmin
  clearCache()
```

These actions can be legitimate, yet must be treated as administrative APIs with side effects. They need validation, authorization, auditing, concurrency limits, and lifecycle checks. An accidental `clearCache()` can spike database load or degrade performance immediately.

### 3.3. Data That Should Not Be Exported

Typically do not export:

- Credentials, passwords, API tokens, private keys, refresh tokens.
- Sessions, cookies, authorization headers, request bodies.
- Personal data and individual customer business records.
- The entire `Environment`, system properties, or configuration objects.
- Stack traces or raw exception messages that may contain internal details.
- Internal repositories/services with many data-manipulating methods.

If credential diagnostics are needed, export states such as `CONFIGURED` or `VALIDATION_FAILED` rather than secret values. If user observability is needed, export total request counts or error rates rather than identifying data.

## 4. Explicit Export: Allowlisting MBeans

When strict control is needed, an easily auditable strategy is **explicitly specifying which beans are exported** using `MBeanExporter.setBeans(...)`.

Spring Framework example:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ControlledJmxConfiguration {

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public PaymentService paymentService() {
        return new PaymentService();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            QueueMonitor queueMonitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);

        exporter.setBeans(Map.of(
            "company.ops:type=QueueMonitor,name=primary",
            queueMonitor
        ));
        return exporter;
    }
}
```

Suppose `QueueMonitor` is a JMX-compliant MBean or configured with a suitable assembler. Only `queueMonitor` is in the mapping; `paymentService` remains a Spring bean serving business logic, yet **is not designated for registration by this exporter**.

Distinguish clearly: a bean absent from this mapping can still be exported by another exporter in the same JVM if the application also enables autodetection or annotation export. Therefore, an explicit allowlist must be paired with **inventorying all exporters** and how they select beans.

### 4.1. Why Explicit Mapping Fits Sensitive Systems

A reviewer can immediately see:

```text
ObjectName                               Spring bean
company.ops:type=QueueMonitor,name=primary -> queueMonitor
company.ops:type=CacheMonitor,name=main    -> cacheMonitor
```

When a team adds a new service, it does not automatically appear in the list just because of a class name or annotation. This makes **expanding the JMX surface an intentional configuration change**.

On the other hand, explicit mapping takes more effort when there are many MBeans. At large scale, you can standardize a centralized JMX configuration module and require review whenever a new mapping is added.

## 5. Limiting Autodetection

`MBeanExporter` supports autodetection. When enabled, Spring can discover beans matching JMX criteria or metadata assemblers in the application context.

For example:

```java
MBeanExporter exporter = new MBeanExporter();
exporter.setAutodetect(true);
```

Autodetection is convenient for demos, small applications, or environments with an already controlled set of MBeans. However, in a large codebase, changes not intended to expand management APIs can still cause new MBeans to appear:

- A class begins implementing an interface following the Standard MBean convention.
- A component gets annotated with `@ManagedResource`.
- A new auto-configuration creates an additional exporter.
- A module is imported into another application context.
- Proxies/lifecycle hooks change the object seen by the exporter.

**Autodetection does not mean exporting all Spring beans**, yet you still need to restrict scope and inventory which beans actually qualify. If security requirements dictate permitting only an approved set of ObjectNames, explicit export is usually easier to prove.

When choosing to use autodetect, maintain a process that checks `MBeanInfo` and ObjectNames after every deployment to detect unexpected changes.

## 6. Annotation-Based Export Also Needs an Allowlist

Spring allows:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "company.ops:type=Status")
public class OperationalStatus {

    @ManagedAttribute
    public String getState() {
        return "READY";
    }
}
```

With an appropriately configured annotation exporter, `OperationalStatus` becomes an MBean candidate. This is a class/bean-level allowlist style: only classes carrying management annotations are selected under the corresponding strategy.

However, if a team places `@ManagedResource` on a huge business class, ensure only safe methods are selected via `@ManagedAttribute`/`@ManagedOperation`. Do not export sensitive data or dangerous operations just for debugging convenience.

**Two levels of allowlist are needed:**

1. Which beans are allowed to become MBeans?
2. Within each MBean, which methods/attributes are allowed to be exposed?

Annotations aid intentional selection, yet do not replace reviewing the exposed information and behavior.

## 7. Management Interfaces to Restrict Methods

A JDK Standard MBean uses a management interface by convention:

```java
public interface QueueMonitorMBean {
    int getQueueDepth();
    long getProcessedCount();
}
```

Implementation:

```java
import java.util.concurrent.atomic.AtomicLong;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicLong processed = new AtomicLong();

    @Override
    public int getQueueDepth() {
        return 5;
    }

    @Override
    public long getProcessedCount() {
        return processed.get();
    }

    public String getInternalToken() {
        return "do-not-export-real-secret";
    }

    public void deleteAllPendingJobs() {
        // Business method not intended for JMX.
    }
}
```

If the object is registered as a Standard MBean, JMX only exposes the contract from `QueueMonitorMBean`, without automatically exporting `getInternalToken()` or `deleteAllPendingJobs()`.

With Spring ModelMBean, `InterfaceBasedMBeanInfoAssembler` can also use a management interface as the source for selecting methods. This is a clearer surface-reduction technique than an assembler that broadly reflects all public methods.

### 7.1. Do Not Use Business Interfaces as Management Interfaces

An interface:

```java
public interface PaymentService {
    Receipt charge(CardData data);
    void refund(String transactionId);
    void deleteDraft(String id);
}
```

should not be turned directly into a JMX management contract merely for reuse convenience. These operations carry strong business semantics and complex types that may not suit JMX. Create a dedicated management interface instead:

```java
public interface PaymentMonitoring {
    long getCompletedPayments();
    String getServiceState();
}
```

A thin facade can implement this interface and read status from the service. Separation restricts exported methods and reduces the risk of leaking data or unintended actions.

## 8. Be Careful with Reflective Assemblers

Spring provides `MBeanInfoAssembler` with different method selection strategies. An assembler that reflects an entire public API can expose more methods than intended.

Conceptual comparison:

| Strategy | Control Level | Risk |
|---|---|---|
| Broad reflective assembler | Low if the class has many methods | Over-exposing getters/operations |
| `MethodNameBasedMBeanInfoAssembler` | Allowlist by method name | Config must be updated when APIs change |
| `InterfaceBasedMBeanInfoAssembler` | Allowlist by interface | Clear contract, easy to review |
| `MetadataMBeanInfoAssembler` | Selected by metadata/annotations | Must verify annotations are not misplaced |
| Standard MBean interface | Standard JMX contract | Requires managing a separate interface |

Do not try to “fix” a missing method by switching to a broader reflective exporter, as that can simultaneously expose sensitive methods.

A project may use multiple export mechanisms; choose an explicit approach for each set of beans and inspect actual runtime metadata.

## 9. Separating Read-Only Monitoring from Write Operations

One way to reduce surface area is separating **monitoring** and **management**.

```text
QueueMonitoringMBean
  QueueDepth (read-only)
  ProcessedTotal (read-only)
  State (read-only)

QueueAdministrationMBean
  pause()
  resume()
  clearCache()
```

Not every system needs two separate MBeans, yet if read access for metrics is granted more broadly than runtime mutation permissions, separating interfaces and ObjectNames helps define clear policies.

Still, splitting into two MBeans **does not create authorization by itself**. If the same connector lets every client invoke all operations, users can still control the management MBean. Configure proper authorization at the JMX access layer or use a better-controlled separate administration mechanism.

### 9.1. Writable Attributes Are Also a Control Surface

```java
void setWarningThreshold(int value);
```

even though it is just an attribute setter, is still a state-mutating action. Apply:

- Value range validation.
- Write permission control.
- Auditing when operationally significant.
- Lifecycle state checks, such as disallowing edits during STOPPING.
- Never using JMX setters to pass or update unprotected secrets.

Read-only attributes help limit control capabilities, yet you must still evaluate **what data is being read out**.

## 10. Do Not Export Secrets, Configuration Dumps, or User Data

A getter like:

```java
@ManagedAttribute
public String getApiKey() {
    return settings.getApiKey();
}
```

can leak credentials over JMX, even if the underlying field is `private`, the getter is read-only, and the application has no corresponding HTTP endpoint.

Other anti-patterns:

```java
@ManagedAttribute
public String getFullConfiguration() {
    return config.toString();
}

@ManagedAttribute
public java.util.Map<String, String> getEnvironment() {
    return System.getenv();
}

@ManagedAttribute
public String getLastRequestBody() {
    return lastRequest.getBody();
}
```

If operational information is needed, expose aggregated state:

```java
@ManagedAttribute
public boolean isCredentialConfigured() {
    return credentialHealth.isConfigured();
}

@ManagedAttribute
public String getLastErrorCategory() {
    return failureState.getCategory().name();
}

@ManagedAttribute
public long getFailedRequestsTotal() {
    return counters.getFailedRequests();
}
```

Even an error message can contain endpoints, usernames, or sensitive payloads. Do not export raw exceptions and do not assume `toString()` always masks secrets.

**Data minimization right at the MBean** is a strong defense layer: data that is not exported cannot be read by JMX clients via that attribute, even if the client has broad connection access.

## 11. Controlling ObjectNames and Naming Strategy

ObjectNames identify MBeans inside the `MBeanServer`:

```text
company.orders:type=QueueMonitor,name=primary
company.cache:type=CacheStatus,name=product
```

A consistent naming convention supports allowlist auditing:

```text
Allowed:
  company.orders:type=QueueMonitor,name=primary
  company.cache:type=CacheStatus,name=product

Unexpected:
  company.payment:type=SecretConfig
  company.internal:type=DebugEverything
```

Understand that an ObjectName's domain and key properties are also metadata discoverable by JMX clients. Never put tokens, sensitive user IDs, passwords, or URLs with credentials into an ObjectName.

The effective set of ObjectNames can change due to `ObjectNamingStrategy`, `@ManagedResource(objectName=...)`, explicit mappings, or other modules. Therefore, a solid governance policy inspects **the actual registry** rather than inferring solely from bean names in source code.

## 12. Inventorying Registered MBeans

You can query `MBeanServer` in Java:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(
    new ObjectName("company.*:*"),
    null
);

names.stream()
    .map(ObjectName::toString)
    .sorted()
    .forEach(System.out::println);
```

This example inspects the platform server in the running JVM. If the exporter uses a dedicated MBeanServer, query that server instead.

Inventory goals:

1. Record actual ObjectNames after startup.
2. Compare against the approved MBean list.
3. Flag new or unexpected ObjectNames.
4. Inspect `MBeanInfo` of application-scoped MBeans.
5. Investigate causes across exporters, annotations, autodetection, dependencies, or new modules.

Do not automatically unregister an unfamiliar ObjectName just because it is absent from your custom MBean list; it could be a platform MXBean or a needed library MBean. Inventorying detects drift before deciding on configuration fixes.

## 13. Inspecting MBeanInfo to See Actual Attributes and Operations

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "ATTR %s type=%s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("OP " + op.getName());
}
```

`MBeanInfo` shows the actual surface seen by clients. This is better evidence than reading source code, since an MBean may be created via ModelMBean, proxies, annotation exporters, or Standard MBean interfaces with different metadata.

**Do not automatically invoke every getter/operation for inventorying.** Reading metadata is usually enough for the first step; a getter could return secrets or trigger heavy queries, and an operation can cause side effects. If value verification is needed, choose safe attributes in an appropriate environment.

### 13.1. Allowlist Testing

In an integration test, define the set of MBean names owned by the application:

```java
Set<String> expected = Set.of(
    "company.orders:type=QueueMonitor,name=primary",
    "company.cache:type=CacheStatus,name=product"
);
```

Retrieve actual ObjectNames in application-owned domains, normalize with `getCanonicalName()` if key-order-independent comparison is needed, and assert no unlisted names exist.

Conceptual example:

```java
Set<String> actual = server.queryNames(
    new ObjectName("company.*:*"), null
).stream()
 .map(ObjectName::getCanonicalName)
 .collect(java.util.stream.Collectors.toSet());
```

Note that `ObjectName` canonicalization affects string comparison. Normalize both expected and actual sets the same way when running real tests.

In production, legitimate new MBeans may come from runtime platforms/libraries; apply strict allowlists only to application-owned domains, not to all of `java.lang`, `com.sun.management`, or domains managed by other parties.

## 14. Checking Which Exporters Actually Exist in ApplicationContext

An application can have multiple `MBeanExporter` beans:

```java
Map<String, MBeanExporter> exporters =
    context.getBeansOfType(MBeanExporter.class);

exporters.forEach((name, exporter) ->
    System.out.println(
        name + " -> " + exporter.getClass().getName()
    )
);
```

If Spring Boot auto-configures an exporter and the project also declares a manual exporter, both might select the same MBean. Determine:

- Which exporters have annotation autodetection enabled.
- Which exporters use explicit `setBeans`.
- Whether multiple contexts share the same platform server.
- Whether duplicate ObjectNames exist and what registration policy applies.
- Whether modules or libraries register MBeans outside Spring exporters.

To truly reduce surface area, account for **all registration sources**, not just the single `@Configuration` open in your IDE.

## 15. RegistrationPolicy Is Not a Security Filter

Spring has policies for handling duplicate ObjectNames:

```java
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

Common options:

| Policy | When ObjectName Already Exists |
|---|---|
| `FAIL_ON_EXISTING` | Throws a collision error |
| `IGNORE_EXISTING` | Ignores the new registration, keeping the existing MBean |
| `REPLACE_EXISTING` | Replaces the old registration per exporter behavior |

Do not use `IGNORE_EXISTING` to “reduce the number of MBeans” if the real goal is deciding which beans are exported. Policies handle **name collisions**, not which beans are safe to publish.

`REPLACE_EXISTING` is also not a way to fix naming collisions without checking ownership. Replacing another module's MBean can cause dashboards to observe the wrong object.

Solve the root cause: explicit mapping, naming conventions, ownership separation, and a single responsible exporter per set of ObjectNames.

## 16. Spring Boot Actuator and the JMX Surface Area

In Spring Boot, JMX export can be influenced by:

```properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
```

This example restricts **Actuator endpoint exposure over JMX**, which does not mean only two MBeans remain in the JVM. Platform MXBeans and other MBeans can still exist.

Distinguish:

- Spring `@ManagedResource` → custom MBeans via matching annotation export.
- Standard MBean → MBean with a JMX management interface.
- Actuator `@Endpoint` → endpoint that can be exported as an MBean via Actuator JMX infrastructure.
- Platform MXBean → provided by the JVM, existing independently of custom Spring MBeans.

If you want to reduce surface area, control **each export source**. Disabling an Actuator endpoint does not remove other custom MBeans. Conversely, removing `@ManagedResource` from a bean does not remove platform MXBeans.

### 16.1. Do Not Use Uncontrolled Wildcard Exposure

```properties
management.endpoints.jmx.exposure.include=*
```

can be useful in isolated test environments, yet should not be the production default. New endpoints introduced during a Boot/dependency upgrade can automatically appear if enabled and covered by the exposure wildcard. Prefer listing specific endpoints.

If the application uses HTTP Actuator, `management.endpoints.web.exposure.include` is a **separate** configuration; the two lists do not stay in sync automatically.

## 17. Local JMX and Remote Connectors

Reducing MBean exports controls only part of management capability. When remote JMX is enabled, a client elsewhere can query the MBeanServer exposed by the connector.

Necessary measures:

1. Never open the JMX port to the public Internet.
2. Restrict access sources via firewall/network policies.
3. Use proper authentication and authorization.
4. Protect transport with TLS or a clearly designed encrypted channel.
5. Limit write/operation-invocation permissions for monitoring accounts.
6. Manage credentials, truststores, and keystores securely.
7. Audit sensitive management actions.
8. Verify RMI topology, hostnames, and ports if using JMX RMI.

If a connector lets clients read the entire MBeanServer, removing only a few custom beans does not prove the system is safe. Platform MXBeans and library MBeans can also hold information that needs protection.

**Local JMX is not “risk-free” either.** Users with permission to attach or interact with the local JVM can inspect diagnostic data; follow OS permission boundaries and minimize exposed data.

## 18. Tracking Surface Area Changes in CI/CD

A useful workflow:

```text
Code change
    |
    +--> Build/test Spring context
    |
    +--> Query MBeanServer
    |
    +--> Collect ObjectNames + MBeanInfo
    |
    +--> Compare approved inventory
    |
    +--> Review additions/removals
    |
    +--> Deploy with monitoring
```

When adding a `@ManagedResource`, management interface, or changing annotations, the set of attributes/operations can change even when the HTTP contract stays unchanged. Therefore, treat the JMX API as a versioned, reviewed surface.

Checks that can be automated:

- No ObjectNames outside the allowlist appear in application domains.
- No readable attributes have suspicious names like `Password`, `Secret`, `Token`, `Authorization`.
- Monitoring-group MBeans have no writable attributes or disallowed operations.
- Type/return/parameter metadata does not change unexpectedly.
- No unreviewed exporters appear from auto-configuration or dependencies.

Checking names alone is not enough to prove safety: an attribute named `Details` can still contain secrets. Review source code and data flow to verify where actual values originate.

## 19. A Design Pattern: Thin Observability Facade

To avoid exporting an entire business service, create a management facade:

```text
PaymentService
   |
   +--> performs payments, refunds, calls gateway
   |
   +--> updates OperationalState
                   |
                   v
             PaymentMonitor
                   |
             @ManagedResource
                   |
             MBeanServer
```

Example:

```java
import java.util.concurrent.atomic.AtomicLong;

public class PaymentOperationalState {
    private final AtomicLong successful = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();

    public void success() {
        successful.incrementAndGet();
    }

    public void failure() {
        failed.incrementAndGet();
    }

    public long successfulCount() {
        return successful.get();
    }

    public long failedCount() {
        return failed.get();
    }
}
```

Facade:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "company.payment:type=PaymentMonitor"
)
public class PaymentMonitor {
    private final PaymentOperationalState state;

    public PaymentMonitor(PaymentOperationalState state) {
        this.state = state;
    }

    @ManagedAttribute
    public long getSuccessfulPayments() {
        return state.successfulCount();
    }

    @ManagedAttribute
    public long getFailedPayments() {
        return state.failedCount();
    }
}
```

`PaymentMonitor` has no knowledge of tokens or customer records. It only returns aggregated counts. When exporter configuration is explicit, this JMX surface is far smaller than exporting `PaymentService` directly.

## 20. Checklist for Evaluating an MBean Before Exporting

For each planned MBean, answer:

1. **Purpose:** What problem needs monitoring or control?
2. **Users:** Which clients will access it, and with what permissions?
3. **Data:** What information do attributes return, and is any of it sensitive?
4. **Behavior:** What side effects do operations/setters have?
5. **Frequency:** If JConsole/collectors poll getters continuously, will it cause load?
6. **Lifecycle:** Does the MBean operate during STARTING/STOPPING?
7. **Naming:** Is the ObjectName unique and stable?
8. **Authorization:** Are read/write permissions properly enforced?
9. **Audit:** Do management actions need to be logged?
10. **Alternative:** Can a safer metric/health endpoint be used instead of a JMX operation?

If you cannot identify the operational purpose of an attribute/operation, do not export it just because the framework supports doing so. Fewer unnecessary capabilities make verification and operations easier.

## 21. Common Mistakes

### 21.1. Exporting Services Directly and Exposing Too Many Public Methods

Using a broad reflective assembler can expose many unintended methods. Create a management interface/metadata allowlist or a separate facade.

### 21.2. Enabling Autodetect on a Large Codebase Without Inventory

New MBeans can appear when modules or annotations change. Record and review ObjectNames/`MBeanInfo` in CI and after deployment.

### 21.3. Treating Read-Only Attributes as Non-Sensitive

Read-only still allows reading. Secrets must never be exposed via getters, even without a setter.

### 21.4. Using Wildcard Actuator JMX Exposure

This can unintentionally expand management endpoints when adding dependencies or upgrading. List endpoints explicitly based on need.

### 21.5. Having Multiple Exporters While Inspecting Only One

Another exporter may register the same MBean or add additional MBeans. Inventory the full relevant ApplicationContext and actual MBeanServer.

### 21.6. Using IGNORE_EXISTING to Mask Naming Bugs

`IGNORE_EXISTING` can retain an older module's MBean, causing monitoring to read from the wrong source. Fix ObjectNames and ownership rather than merely changing policy.

### 21.7. Overlooking Notifications and Operations

Even when attributes are safe, operations can mutate state, and notification userData can leak payloads. Inspect the full `MBeanInfo`, not just getters.

### 21.8. Getters Running Heavy Network or Database Queries

Monitoring collectors can poll at high frequency and create load. Export precomputed state or controlled caches with appropriate timestamps/staleness.

## 22. Practice Exercises

**Exercise 1 — Explicit Allowlist.** Create three Spring beans `QueueMonitor`, `CacheMonitor`, `PaymentService`; configure `MBeanExporter.setBeans` with only the two monitors. Start the context and verify `PaymentService` has no ObjectName created by this exporter.

**Exercise 2 — Method-Level Allowlist.** Create a bean with `getQueueDepth()`, `getApiToken()`, `clearCache()`. Use a management interface containing only `getQueueDepth()` and inspect `MBeanInfo`.

**Exercise 3 — Annotation Review.** Create a `@ManagedResource` with two safe `@ManagedAttribute` properties. Add a new public method without annotations; confirm the management interface does not expand unintentionally.

**Exercise 4 — Actuator Exposure.** In Spring Boot, configure `management.endpoints.jmx.exposure.include=health,info` and observe Actuator MBeans. Compare when adding an endpoint in a test environment and record the change.

**Exercise 5 — Inventory.** Write a test calling `queryNames("company.*:*")`, compare against an ObjectName allowlist, and print attribute/operation metadata without reading values.

**Exercise 6 — Separating Monitoring/Admin.** Design two interfaces, one read-only and one with `pause()`/`resume()`. Explain how connector authorization or an external management solution must be added to enforce real permission boundaries.

**Exercise 7 — Secret Leak.** Write an unsafe MBean returning `config.toString()`, identify the leakage path, and refactor it to report only `CredentialConfigured` and `ServiceState`.

**Exercise 8 — Runtime Review.** After enabling a new dependency that self-registers MBeans, record the new ObjectName and evaluate whether it falls under application, library, or JVM ownership.

## 23. Self-Check Questions

1. Why does the number of MBeans affect the management attack surface?
2. How does explicit `setBeans(...)` differ from autodetection?
3. Why does using a separate management interface reduce method exposure?
4. What risks arise from placing `@ManagedResource` on a large business class?
5. Can read-only attributes leak sensitive data?
6. Why should `System.getenv()` or full config objects not be exported?
7. Why is `RegistrationPolicy` not a security filter?
8. Are platform MXBeans removed when you stop exporting custom Spring MBeans?
9. Why inspect `MBeanInfo` instead of looking only at annotations in source code?
10. When should monitoring MBeans be separated from administration MBeans?
11. What protection layers does remote JMX need besides reducing MBean count?
12. How can CI/CD detect JMX surface expansion?

## 24. Key Takeaways

**Reducing JMX surface area starts with deciding not to export unnecessary capabilities.** Prefer explicit mappings or annotation/management-interface allowlists, expose only operational state and metrics, avoid secrets and dangerous operations, and verify actual ObjectNames/`MBeanInfo`.

Combine resource/method restrictions with connector, network, authorization, audit protections, and post-deploy inventory checks. A small management surface with clear ownership and runtime verification is far easier to protect than an MBeanServer packed with every service solely for export convenience.
