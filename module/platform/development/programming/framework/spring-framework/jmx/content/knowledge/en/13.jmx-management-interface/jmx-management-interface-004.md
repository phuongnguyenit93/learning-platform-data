# InterfaceBasedMBeanInfoAssembler in Spring Framework JMX

## 1. The problem: not every bean method should be published

In a Spring application, a service typically has many methods: business processing, status checks, repository access, cache refreshes, configuration updates, or internal methods for testing. When exporting a service as an MBean, operators should only see **the attributes and operations selected for management purposes**.

Example service:

```java
public class OrderService {
    public long getProcessedOrders() { /* ... */ }
    public boolean isHealthy() { /* ... */ }
    public void resetStatistics() { /* ... */ }

    public void deleteAllOrders() { /* ... */ }
    public void processPayment(String cardToken) { /* ... */ }
    public String getInternalSecret() { /* ... */ }
}
```

If the export mechanism publishes too broadly, a JMX client can invoke methods that have no reason to exist on the management plane. The issue is not only a cluttered JConsole UI; over-exporting can leak data, mutate state, or provide a call path that bypasses the business API.

**`InterfaceBasedMBeanInfoAssembler`** in Spring JMX allows using a **management interface** as the source that defines the set of methods to be published. Spring inspects the methods present in the specified interface to build `ModelMBeanInfo`; from there, valid accessors are recognized as attributes and the remaining methods can be exported as operations.

The core point is an **allowlist by interface contract**: adding a method to the implementation does not automatically mean it is exposed to JMX.

## 2. Where the assembler fits in the export architecture

Spring JMX consists of components with distinct responsibilities:

```text
                  Spring ApplicationContext
                            |
                  Business/monitor bean
                            |
                     MBeanExporter
                     /     |      \
                    /      |       \
             assembler    naming   MBeanServer
                 |       strategy     |
                 v           |        v
     InterfaceBasedMBeanInfoAssembler
                 |
         management interface
                 |
       select attributes / operations
                 |
             ModelMBeanInfo
                 |
                 +---------> Spring ModelMBean
                                    |
                              register ObjectName
                                    |
                              JMX client
```

- **`MBeanExporter`** manages bean export, resource selection, registration lifecycle, and interaction with `MBeanServer`.
- **`MBeanInfoAssembler`** builds management metadata: which attributes and operations are published.
- **`InterfaceBasedMBeanInfoAssembler`** is an assembler that uses configured interfaces to select methods.
- **`ObjectNamingStrategy`** determines the MBean registration name; it does not decide which methods are allowed to be exported.
- **`MBeanServer`** hosts registered MBeans and serves client requests.
- **`MBeanInfo` / `ModelMBeanInfo`** describes the management interface that clients can discover.

This is the **Spring ModelMBean export** mechanism. It is conceptually related to JDK Standard MBeans, but the two configuration paths should not be equated. Standard MBeans use the `SomethingMBean` naming convention by default; the Spring assembler can pick an explicitly specified interface without requiring the implementation to follow the same naming convention.

## 3. Why is a management interface a good boundary?

A dedicated interface can express exactly what operators need:

```java
public interface OrderManagement {
    long getProcessedOrders();
    boolean isHealthy();
    void resetStatistics();
}
```

The implementation can have many other methods:

```java
public class OrderService implements OrderManagement {
    @Override
    public long getProcessedOrders() { /* ... */ }

    @Override
    public boolean isHealthy() { /* ... */ }

    @Override
    public void resetStatistics() { /* ... */ }

    public void processOrder(Order order) { /* ... */ }

    public String getInternalSecret() { /* ... */ }
}
```

When the assembler is configured to use `OrderManagement`, JMX metadata focuses on `getProcessedOrders()`, `isHealthy()`, and `resetStatistics()`. Both `processOrder(...)` and `getInternalSecret()` do not belong to the interface and are therefore not selected.

This approach offers several benefits:

1. **Clear scope:** reviewers only need to inspect the interface to know the intended management capabilities.
2. **Stability:** changing the implementation does not necessarily change the JMX API.
3. **Separation of concerns:** a business service can contain many methods without expanding the management surface.
4. **Easy inventory:** method names and return types in the interface form a controlled contract.
5. **Custom-designed:** a management interface differs from a business interface and does not need to contain every business operation.

Even so, an interface is only a **method exposure boundary**, not a replacement for authentication, authorization, or validation. If the interface intentionally includes `deleteAllOrders()`, the assembler can still publish that operation; reviewing its suitability remains the designer's responsibility.

## 4. How attributes and operations are recognized

The assembler does not simply dump all method names into a single list. For accessors following JavaBean conventions, Spring JMX can describe attributes:

```java
public interface CacheManagement {
    long getHitCount();
    boolean isEnabled();
    int getMaxEntries();
    void setMaxEntries(int value);
    void clearCache();
}
```

Expected contract:

| Method | JMX representation | Capability |
|---|---|---|
| `getHitCount()` | Attribute `HitCount` | Read-only |
| `isEnabled()` | Attribute `Enabled` | Read-only |
| `getMaxEntries()` | Attribute `MaxEntries` | Read-write when corresponding setter exists |
| `setMaxEntries(int)` | Setter for `MaxEntries` | Writable |
| `clearCache()` | Operation `clearCache` | Invocable action |

A read–write attribute needs a getter/setter matching in name and type. Do not expect the assembler to guess that two differently named methods belong to the same property.

Return data is also part of the contract. If `getHitCount()` changes from `long` to `String`, JMX clients and monitoring scripts reading the attribute can break. Treat the management interface as an API with version compatibility.

## 5. Complete example: selecting methods via InterfaceBasedMBeanInfoAssembler

The example below presents a standalone Spring Framework application context. We have an implementing service, a management interface, and an `MBeanExporter` configuration to export only selected methods.

### 5.1. Management interface

```java
// JobManagement.java
public interface JobManagement {
    long getCompletedJobs();
    int getConcurrencyLimit();
    void setConcurrencyLimit(int limit);
    void resetStatistics();
}
```

The interface above has only four methods; `CompletedJobs` is read-only, `ConcurrencyLimit` is read-write, and `resetStatistics()` is an operation.

### 5.2. Implementing bean

```java
// JobService.java
import java.util.concurrent.atomic.AtomicLong;

public class JobService implements JobManagement {
    private final AtomicLong completedJobs = new AtomicLong();
    private volatile int concurrencyLimit = 4;

    public void recordCompletedJob() {
        completedJobs.incrementAndGet();
    }

    @Override
    public long getCompletedJobs() {
        return completedJobs.get();
    }

    @Override
    public int getConcurrencyLimit() {
        return concurrencyLimit;
    }

    @Override
    public void setConcurrencyLimit(int limit) {
        if (limit < 1 || limit > 32) {
            throw new IllegalArgumentException(
                "Concurrency limit must be between 1 and 32"
            );
        }
        concurrencyLimit = limit;
    }

    @Override
    public void resetStatistics() {
        completedJobs.set(0L);
    }

    // Internal method, not part of the management interface.
    public String getInternalCredential() {
        return "example-only-internal-value";
    }

    // Business method, not exported via JMX.
    public void executeJob(String jobId) {
        recordCompletedJob();
    }
}
```

The string in `getInternalCredential()` is only used to illustrate an unexposed method; real applications must store secrets using proper secret management practices rather than hard-coding credentials in source code.

### 5.3. Spring exporter and assembler configuration

```java
// JmxConfig.java
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.InterfaceBasedMBeanInfoAssembler;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class JmxConfig {

    @Bean
    public JobService jobService() {
        return new JobService();
    }

    @Bean
    public MBeanServerFactoryBean mbeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setLocateExistingServerIfPossible(true);
        return factory;
    }

    @Bean
    public InterfaceBasedMBeanInfoAssembler interfaceAssembler() {
        InterfaceBasedMBeanInfoAssembler assembler =
            new InterfaceBasedMBeanInfoAssembler();
        assembler.setManagedInterfaces(JobManagement.class);
        return assembler;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            JobService jobService,
            InterfaceBasedMBeanInfoAssembler assembler,
            MBeanServer mbeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "demo.jobs:type=JobService,name=main",
            jobService
        ));
        return exporter;
    }
}
```

In the configuration above:

- `setManagedInterfaces(JobManagement.class)` tells the assembler to derive the contract only from the selected management interface.
- `setBeans(...)` explicitly specifies the object and ObjectName to export.
- `setAssembler(...)` attaches the metadata-building strategy to the exporter.
- `MBeanServer` is the registry queried by JConsole or clients.
- `MBeanServerFactoryBean` helps configure the MBeanServer in Spring; the platform server can be used depending on application requirements.

**Configuration note:** a real application may already have an `MBeanServer` provided by Spring Boot or the infrastructure. In that case, reuse that server and avoid creating multiple registries that make MBeans hard to locate. This example illustrates the relationship between beans in Spring; choose an MBeanServer policy consistent with your environment.

### 5.4. Starting the context and reading metadata

```java
// Main.java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(JmxConfig.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                "demo.jobs:type=JobService,name=main"
            );

            MBeanInfo info = server.getMBeanInfo(name);

            for (MBeanAttributeInfo attribute : info.getAttributes()) {
                System.out.printf(
                    "Attribute %s: type=%s, read=%s, write=%s%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable()
                );
            }

            for (MBeanOperationInfo operation : info.getOperations()) {
                System.out.println("Operation " + operation.getName());
            }

            Thread.sleep(60_000L);
        }
    }
}
```

The goal when reading metadata is to observe `CompletedJobs`, `ConcurrencyLimit`, and `resetStatistics`, and confirm that `getInternalCredential` is not published. Metadata listing order should not be relied upon as a contract.

For convenient local JConsole connection, the MBean should be registered in the JVM's platform MBeanServer. In environments using a separate server, local JConsole attach may only see the default platform server; verify which server the exporter actually registers with.

## 6. Why use a separate management interface?

There are two different design strategies:

**A. Service directly implements the management interface**

```java
public class QueueService implements QueueManagement {
    // Business logic + management methods
}
```

The advantage is fewer classes, which is convenient for small services. The disadvantage is that the management interface is coupled to the business class and may expand due to unrelated needs.

**B. Dedicated management facade**

```java
public class QueueManagementFacade implements QueueManagement {
    private final QueueService service;

    public QueueManagementFacade(QueueService service) {
        this.service = service;
    }

    @Override
    public int getQueueDepth() {
        return service.currentQueueDepth();
    }

    @Override
    public void pause() {
        service.pauseProcessing();
    }
}
```

A facade can check application-layer permissions, validation, readiness, and impact limits. It makes clear that the JMX API is distinct from the business API.

```text
Business API ---> QueueService <--- ManagementFacade
                                        |
                                   QueueManagement
                                        |
                                     assembler
                                        |
                                    MBeanServer
```

If an application has many management rules, a facade usually helps keep the interface small and avoid exporting unnecessary business methods. However, a facade does not secure JMX access by itself; the connector and environment still need protection.

## 7. ManagedInterfaces and managing multiple interfaces

`InterfaceBasedMBeanInfoAssembler` can be configured with a shared set of management interfaces for eligible beans. Example:

```java
assembler.setManagedInterfaces(
    MonitoringManagement.class,
    MaintenanceManagement.class
);
```

The idea is that methods in the specified interfaces form the set of management capabilities published by the assembler when a bean supports the corresponding methods.

Ensure that every bean sharing the assembler has an appropriate contract. Do not use a global list of interfaces containing sensitive operations and attach the same assembler to every service merely for configuration convenience.

If MBeans require different contracts, configure them separately per bean or use per-bean interface mappings as appropriate. That avoids a “one-size-fits-all” configuration from broadening the management interface.

## 8. InterfaceMappings: dedicated contracts per bean

When exporting multiple beans, you may need a **bean key → management interface** mapping instead of a shared interface list. Spring supports configuring `interfaceMappings` on the assembler.

Conceptual example:

```java
InterfaceBasedMBeanInfoAssembler assembler =
    new InterfaceBasedMBeanInfoAssembler();

java.util.Properties mappings = new java.util.Properties();
mappings.setProperty(
    "inventoryMonitor",
    "com.example.jmx.InventoryManagement"
);
mappings.setProperty(
    "paymentMonitor",
    "com.example.jmx.PaymentManagement"
);

assembler.setInterfaceMappings(mappings);
```

The class names in the example are illustrative; they must point to real interfaces on the classpath. Mapping keys must match how the exporter identifies exported beans in the actual configuration. Because key lookup depends on the export mechanism, verify with `MBeanInfo` to confirm the right interface was applied.

Key point: **a single assembler can apply different contracts to individual resources**, helping manage a diverse set of MBeans without exposing every method from all interfaces.

## 9. Comparing MBeanInfoAssembler types

Spring JMX provides several assemblers:

| Assembler | Method selection mechanism | When appropriate |
|---|---|---|
| `SimpleReflectiveMBeanInfoAssembler` | Based on eligible public methods | Small demos or when exported classes are tightly controlled |
| `MethodNameBasedMBeanInfoAssembler` | Allowlist by method name | Small set of methods, do not want to create an interface |
| `InterfaceBasedMBeanInfoAssembler` | Based on management interfaces | Management API needing a clear, type-checkable contract |
| `MetadataMBeanInfoAssembler` | Based on annotation metadata | Want `@ManagedAttribute`, `@ManagedOperation`, and descriptions on methods |

For example, `MethodNameBasedMBeanInfoAssembler` selects method names from configuration, while `InterfaceBasedMBeanInfoAssembler` uses Java interfaces reflecting both signatures and types. The metadata assembler is convenient when placing annotations directly on managed methods.

Choose an assembler based on clarity and code organization. Do not enable multiple assemblers expecting them to merge automatically: `MBeanExporter` uses its configured assembler to generate metadata.

## 10. Distinguishing Standard MBean and Spring interface-based export

In plain Java JMX, a Standard MBean typically uses an interface by convention:

```java
public interface CacheMonitorMBean {
    int getCacheSize();
}
public class CacheMonitor implements CacheMonitorMBean {
    public int getCacheSize() { return 42; }
}
```

Registering the object with `MBeanServer` causes JMX to introspect the `CacheMonitorMBean` interface.

In Spring, a service may not want to name its interface according to that convention. When using `InterfaceBasedMBeanInfoAssembler`, Spring explicitly picks the configured interface and builds metadata via the exporter.

The difference:

```text
Standard MBean:
  Java class + SomethingMBean
     -> JMX standard introspection
     -> MBeanInfo

Spring ModelMBean:
  Spring bean + management interface
     -> InterfaceBasedMBeanInfoAssembler
     -> ModelMBeanInfo
     -> ModelMBean
```

Both expose attributes/operations to clients, but the method selection and registration processes are not identical. Do not infer that `setManagedInterfaces(...)` changes how the JDK recognizes MXBeans or Standard MBeans across all registration paths.

## 11. Spring proxies and the management interface

A Spring bean may be AOP-proxied for transactions, caching, security, or scope. If you configure exporting a proxy directly, the visible set of interfaces may differ from the implementation class.

Example:

```java
@Transactional
public class PaymentService implements PaymentManagement {
    // ...
}
```

When Spring creates a JDK dynamic proxy, the proxy typically exposes the relevant interfaces. The management interface must be properly supported by the proxy if the exporter relies on the proxy. With a CGLIB proxy, many implementation methods may be present, yet the assembler still restricts the contract according to the interface.

Things to check:

- Is the exported bean a proxy or the target?
- Does the proxy implement the selected management interface?
- Are management methods routed through the expected advice?
- Does the configured interface use the right parameter/return types?
- Are any operations restricted by transactions or authentication differently than expected?

Do not resolve this by switching to a reflective assembler to “see all methods”, as that can accidentally publish many unwanted capabilities. Inspect the proxy and the actual export contract.

## 12. Dependencies and initialization order

The exporter is created during the ApplicationContext lifecycle. If a managed MBean depends on a database, cache, or another service, Spring must resolve dependencies when creating the bean. However, successful MBean registration does not necessarily prove an external service is READY.

A safe getter:

```java
@Override
public String getServiceState() {
    return lifecycleState.currentState().name();
}
```

is usually preferable to a getter that queries a database or a slow remote endpoint just to “check right now”. A management interface can contain both `getServiceState()` and `resetStatistics()`, but operations should check readiness conditions and have appropriate guards.

If an MBean is not registered, check the exporter, ObjectName, interface mapping, initialization exceptions, and name conflicts. Do not automatically conclude this is an assembler bug: the assembler is only one link in the export pipeline.

## 13. Security: an interface is an allowlist, not authorization

A management interface helps **reduce the surface** by publishing only selected methods. It does not decide which users are allowed to call them.

Separate these concerns:

1. **Exposure:** which methods appear in `MBeanInfo`?
2. **Authentication:** which clients can connect to JMX?
3. **Authorization:** which operations can a client read/invoke?
4. **Validation:** are the values or actions valid?
5. **Audit:** how does the system record management activities?

For example, `setConcurrencyLimit(int)` can legitimately be exposed, yet must still reject invalid values. If remote JMX is enabled, secure the connection, network boundaries, and access permissions. An interface is not a security wall against someone who already has broader Java process manipulation privileges.

Do not export passwords, tokens, raw configuration, user data, or dangerous operations just because they live in a Java interface. Separate a dedicated JMX interface and evaluate each method.

## 14. Verifying results via MBeanInfo

After the application starts and the exporter registers the MBean, metadata is the factual evidence of the public interface.

```java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "ATTRIBUTE %s read=%s write=%s type=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable(),
        attribute.getType()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        "OPERATION " + operation.getName()
    );
}
```

The snippet needs imports:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
```

`connection` is an `MBeanServerConnection`, and `objectName` is the registered `ObjectName`. With Spring, verify how getter names are converted to attributes and which operations remain visible.

In particular, verify the **absence** of methods that do not belong to the management interface. A practical test can compare the expected method set against the metadata and fail if a sensitive getter appears.

### 14.1. Reading attributes and invoking operations

```java
Object count = connection.getAttribute(
    objectName,
    "CompletedJobs"
);

connection.setAttribute(
    objectName,
    new javax.management.Attribute("ConcurrencyLimit", 8)
);

connection.invoke(
    objectName,
    "resetStatistics",
    new Object[0],
    new String[0]
);
```

When `ConcurrencyLimit` has compatible getter and setter, clients can read/write it. `CompletedJobs` is read-only; attempting `setAttribute` on it will be rejected. `resetStatistics` is an operation with side effects, so in production it requires commensurate permissions and auditing.

## 15. Common pitfalls

### 15.1. Interface mapping does not match the bean

You configure an interface mapping with key `inventoryMonitor`, but the exporter uses a different key to identify the resource. In that case the assembler may not find the expected interface. Check how mapping keys are resolved under the actual exporter configuration; do not guess from Java class names.

### 15.2. Bean does not implement the expected interface

The assembler selects `OrderManagement`, but the bean does not provide the corresponding methods or the proxy does not expose the matching interface. Export may fail or fail to produce the desired metadata. Ensure the bean explicitly implements the contract.

### 15.3. Getter does not appear

Verify the getter is in the management interface, follows JavaBean signature conventions, and uses a data type supported by JMX/exporter. Methods existing only on the implementation will not be selected if the assembler uses an interface.

### 15.4. Over-exporting operations

A management interface accidentally extends a business interface containing methods that should not be published. When the assembler selects the extended interface, inherited methods enter the management contract. Keep the management interface small and separate from business contracts if needed.

### 15.5. MBean appears but operations cannot be invoked

Check method types and signatures, proxies, exceptions in the implementation, service state, and connector access permissions. MBeanInfo shows the contract, yet invoking an operation still executes real code with its own runtime conditions.

### 15.6. Duplicate ObjectName registration

Two MBeans registering the same name `demo.jobs:type=JobService,name=main` can collide. Fix naming/mapping or registration policy intentionally, avoiding hiding errors by overwriting MBeans not owned by the exporter.

### 15.7. Enabling both annotation exporter and manual exporter

If `@EnableMBeanExport` or auto-configuration already creates an exporter, adding a manual `MBeanExporter` can create two registration mechanisms. Plan ownership and ObjectNames clearly for each exporter.

### 15.8. Confusing “not exported” with “unreachable by any path”

An interface allowlist only limits a specific MBean surface. If the same data is exposed via logs, HTTP endpoints, a debugger, or another MBean, the risk still exists. Look at the whole system, not just one assembler.

## 16. Practice exercises

**Exercise 1 — Create an allowlist.** Create `CacheService` with five methods: `getHitCount()`, `getCacheSize()`, `clearCache()`, `getInternalToken()`, `loadUserDetails(String)`. Create `CacheManagement` containing only the two metric getters and `clearCache()`, configure the assembler, and inspect `MBeanInfo`.

**Exercise 2 — Test implementation changes.** Add `getInternalDebugState()` to the implementation class without adding it to the management interface. Restart and confirm that interface-based export does not automatically publish the new method.

**Exercise 3 — Compare assemblers.** For the same bean, configure `MethodNameBasedMBeanInfoAssembler` and `InterfaceBasedMBeanInfoAssembler` in turn. Note differences in configuration style, type-checking capability, and actual metadata.

**Exercise 4 — Use interfaceMappings.** Export two beans with different management contracts. Create per-bean-key mappings, then verify each MBean has only the attributes/operations of its selected interface.

**Exercise 5 — Handle proxies.** Use a service with transaction advice and a small management interface. Inspect the proxy type, interfaces implemented by the proxy, and exported metadata. Explain why implementation methods outside the interface should not be published merely for debugging convenience.

**Exercise 6 — Verify attribute access flags.** Create `getLimit()` + `setLimit(int)` in the management interface, plus `getCount()` with only a getter. Read `MBeanAttributeInfo.isReadable()` and `isWritable()`, and test writing valid and invalid values.

## 17. Self-check questions

1. What responsibility does `InterfaceBasedMBeanInfoAssembler` have in the Spring JMX pipeline?
2. How does it differ from `MBeanExporter`?
3. Why does a dedicated management interface help limit the management surface?
4. Is a method appearing only in the implementation automatically published when using an interface-based assembler?
5. How are getters/setters interpreted as attributes?
6. When should you use `interfaceMappings` instead of a shared `managedInterfaces`?
7. Why does interface-based management not replace authentication/authorization?
8. How do JDK Standard MBeans and Spring ModelMBean exports differ in interface selection source?
9. If an MBean is missing methods or has extra methods, which component do you check first?
10. Why should you verify `MBeanInfo` after configuring the exporter?

## 18. Key takeaways

**`InterfaceBasedMBeanInfoAssembler` uses management interfaces to define the boundary of methods published through Spring JMX.** Configuring appropriate interfaces, attaching the assembler to `MBeanExporter`, and verifying actual `MBeanInfo` helps build an intentional management API and reduces the risk of leaking internal methods when implementations change.

Keep management interfaces small, stable, and easy to review; clearly distinguish attributes and operations, choose a consistent export strategy, and protect remote JMX. An interface is a mechanism for **limiting what can be called**, while who is allowed to call it, validation, and auditing still need to be designed independently.
