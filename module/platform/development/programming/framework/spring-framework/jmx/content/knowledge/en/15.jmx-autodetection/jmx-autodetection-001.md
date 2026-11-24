# Autodetecting MBeans That Implement a JMX Interface in Spring Framework

## 1. What Problem Does Autodetection Solve?

In a Java application, JMX (Java Management Extensions) allows exposing managed objects to an `MBeanServer` so that tools such as JConsole, Java Mission Control, or a JMX client can read attributes and invoke operations. The pure Java approach typically registers each MBean individually:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName("demo.orders:type=OrderMonitor");
server.registerMBean(new OrderMonitor(), name);
```

When an application uses Spring, objects are already managed by the `ApplicationContext`. If there are many MBeans, writing separate registration code for each object both repeats configuration and complicates the lifecycle. `MBeanExporter` **autodetection** allows Spring to find eligible beans and automatically export them as JMX MBeans, instead of requiring all of them to be listed via `setBeans(...)`.

However, the term “autodetection” must be understood accurately: Spring is not supposed to expose **every** bean in the container. MBeans that already conform to a standard JMX interface, beans with management metadata, and ordinary beans are different cases.

Lesson objectives:

- Understand which MBeans an exporter can autodetect.
- Distinguish Standard MBeans, MXBeans, Dynamic MBeans, and beans with management annotations.
- Configure autodetection with `MBeanExporter` and understand the role of `AnnotationMBeanExporter`.
- Understand how `ObjectName` is determined, the registration lifecycle, and conflict-handling policies.
- Verify results using `MBeanServer.queryNames(...)` and `MBeanInfo`.
- Recognize the impact of proxies, lazy initialization, and security scope.

## 2. Mental Model: Spring Bean → JMX Registry

```text
       Spring ApplicationContext
                  |
            managed beans
                  |
                  v
             MBeanExporter
                  |
        +---------+---------+
        |                   |
   Explicit beans       Autodetection
   setBeans(...)        check eligible beans
        |                   |
        +---------+---------+
                  |
          select ObjectName
                  |
        MBeanServer.registerMBean(...)
                  |
                  v
        JMX management surface
                  |
            JConsole / client
```

Autodetection has two dimensions that should be kept separate:

1. **Candidate selection:** which beans belong to the set of MBeans that the exporter will manage?
2. **MBean construction/registration:** is the bean registered directly as a standard MBean or must it be adapted into a ModelMBean, and which ObjectName is used?

The fact that a bean exists in Spring does not prove it has been registered in JMX. The fact that a class has an interface named `SomethingMBean` also does not guarantee that the application has enabled the right exporter and bound it to the MBeanServer that the tool is observing.

## 3. What Does a JMX-Compliant MBean Mean?

A JMX-compliant object has a form that JMX can directly understand and manage, typically:

| Form | Basic Identification | Meaning |
|---|---|---|
| Standard MBean | Class implements an interface named `ClassNameMBean` or is wrapped appropriately | JMX infers attributes and operations from the interface |
| MXBean | Class implements an `*MXBean` interface, `@MXBean`, or a valid MXBean wrapper | JMX interface with type mapping to Open Types |
| Dynamic MBean | Class implements `DynamicMBean` | Supplies metadata and handles access/invoke itself |
| ModelMBean | `ModelMBean` implementation or one created by Spring when exporting an ordinary bean | Uses flexible descriptive management metadata |

In Spring JMX, autodetecting an object that is already a valid MBean is a different purpose from autodetecting a bean annotated with `@ManagedResource`. An ordinary Java object does not automatically become a Standard MBean just because its class name contains the word `Monitor`.

Example:

```java
public interface QueueMonitorMBean {
    int getQueueDepth();
    void resetStatistics();
}

public class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getQueueDepth() {
        return 42;
    }

    @Override
    public void resetStatistics() {
        // Reset application-managed metrics.
    }
}
```

`QueueMonitor` is a Standard MBean by JMX convention because it implements `QueueMonitorMBean`. In Spring, if an instance of it is managed as a bean and selected by the exporter, JMX can read the `QueueDepth` attribute and invoke the `resetStatistics` operation.

Conversely:

```java
public class InternalQueueService {
    public int getQueueDepth() { return 42; }
    public void deleteAllJobs() { /* ... */ }
}
```

This class has no management interface or special metadata. Autodetection should not default to registering it as an MBean where every public method can be invoked. Exporting an ordinary bean is an explicit configuration decision, usually through a corresponding assembler/metadata.

## 4. Using MBeanExporter with Autodetect

`org.springframework.jmx.export.MBeanExporter` is the core component of Spring JMX export. It can export a specified list of beans and/or autodetect eligible beans in the application context.

Java configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public MBeanServerFactoryBean mBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setLocateExistingServerIfPossible(true);
        return factory;
    }

    @Bean
    public MBeanExporter mBeanExporter(javax.management.MBeanServer server) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setAutodetect(true);
        return exporter;
    }
}
```

This configuration expresses three points:

- `setAutodetect(true)` enables automatic MBean discovery.
- `setServer(server)` specifies the target `MBeanServer`.
- Spring manages the exporter's lifecycle in the `ApplicationContext`.

In a real application, a platform MBeanServer may already be configured. You can also create an `MBeanServer` bean from `ManagementFactory.getPlatformMBeanServer()` instead of using `MBeanServerFactoryBean` if the application wants to register on the default JVM server. Do not unintentionally create multiple `MBeanServer` instances because JConsole may be observing a different server than the one the exporter writes data to.

Alternative example:

```java
@Bean
public javax.management.MBeanServer platformMBeanServer() {
    return java.lang.management.ManagementFactory
        .getPlatformMBeanServer();
}
```

**Choose exactly one server bean according to the application model.** If multiple `MBeanServer` beans of the same type exist, injection by type can become ambiguous; in that case, use `@Qualifier` or design the configuration clearly.

## 5. Runnable Example: Standard MBean Discovered by Spring

### 5.1. Management interface

Create `TaskMonitorMBean.java`:

```java
public interface TaskMonitorMBean {
    long getCompletedCount();
    int getWarningThreshold();
    void setWarningThreshold(int threshold);
    void resetCounters();
}
```

`CompletedCount` is a read-only attribute; `WarningThreshold` is a read-write attribute; `resetCounters()` is an operation.

### 5.2. Implementation

Create `TaskMonitor.java`:

```java
import java.util.concurrent.atomic.AtomicLong;

public class TaskMonitor implements TaskMonitorMBean {
    private final AtomicLong completed = new AtomicLong();
    private volatile int warningThreshold = 100;

    @Override
    public long getCompletedCount() {
        return completed.get();
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int value) {
        if (value < 1 || value > 10_000) {
            throw new IllegalArgumentException(
                "WarningThreshold must be 1..10000"
            );
        }
        warningThreshold = value;
    }

    @Override
    public void resetCounters() {
        completed.set(0);
    }

    // Internal: not in the management interface.
    public void recordCompletedTask() {
        completed.incrementAndGet();
    }
}
```

### 5.3. Spring Configuration

Create `LabConfig.java`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.naming.IdentityNamingStrategy;

@Configuration
public class LabConfig {

    @Bean
    public TaskMonitor taskMonitor() {
        return new TaskMonitor();
    }

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(MBeanServer jmxServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(jmxServer);
        exporter.setAutodetect(true);
        exporter.setNamingStrategy(new IdentityNamingStrategy());
        return exporter;
    }
}
```

Here `IdentityNamingStrategy` is an example Spring naming strategy; you should not hard-code an ObjectName that you do not yet know is generated by the chosen naming strategy. In practice, the most reliable way to verify is to query the MBeanServer to find the actual ObjectName after the context refreshes.

A different naming strategy, including a custom naming strategy or key mapping, can produce different results. **Autodetection selects the object**, whereas the naming strategy chooses the registration name; do not conflate those two things into one.

### 5.4. Starting Up and Listing MBeans

Create `Main.java`:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(LabConfig.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            System.out.println("Spring JMX context started");

            for (ObjectName name : server.queryNames(null, null)) {
                if (name.toString().contains("TaskMonitor")) {
                    MBeanInfo info = server.getMBeanInfo(name);
                    System.out.println("Found: " + name);
                    System.out.println("Class: " + info.getClassName());
                }
            }

            Thread.sleep(90_000L);
        }
    }
}
```

You need the corresponding Spring Context and Spring JMX module dependencies in the project. This code snippet is intended to illustrate registration and discovery. You can replace the filter condition on `TaskMonitor` with an ObjectName pattern matching the actual naming strategy.

A principled expected result is that an MBean representing `TaskMonitor` is registered; the exact name depends on the naming strategy and exporter configuration.

**Do not infer from a successful compilation that the exporter has registered properly:** reading `MBeanServer.queryNames` and `MBeanInfo` is what confirms actual registration.

## 6. If You Need a Stable ObjectName

An ObjectName is how a client locates an MBean, in the form:

```text
domain:key1=value1,key2=value2
```

Example:

```text
demo.tasks:type=TaskMonitor,name=primary
```

For production, a stable name keeps monitoring queries, alerting, and dashboards from breaking when a Spring bean or class is renamed.

For beans exported via explicit mapping, you can specify the name:

```java
@Bean
public MBeanExporter explicitMBeanExporter(
        MBeanServer server,
        TaskMonitor taskMonitor) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(java.util.Map.of(
        "demo.tasks:type=TaskMonitor,name=primary",
        taskMonitor
    ));
    return exporter;
}
```

This example is an **explicit export** configuration to contrast with autodetection. Do not simultaneously use two exporters that both register `TaskMonitor` with the same ObjectName without an intentional policy. In a real project, choose a consistent naming approach and check for collisions.

**Trade-off:** autodetection reduces per-bean configuration; explicit mapping makes it easy to control exactly which beans are exported and their names. When compliance or security requires a strict allowlist, explicit mapping is often worth considering.

## 7. Autodetecting Objects That Implement a JMX Interface

An object with a standard management interface is a clear candidate for autodetection:

```java
public interface CacheMonitorMBean {
    int getCacheSize();
}

public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public int getCacheSize() {
        return 64;
    }
}
```

If this class is a Spring bean examined by the exporter, it can be recognized as a Standard MBean and exported according to the `CacheMonitorMBean` interface.

With MXBean:

```java
public interface WorkerPoolMXBean {
    int getActiveWorkers();
}

public class WorkerPool implements WorkerPoolMXBean {
    @Override
    public int getActiveWorkers() {
        return 4;
    }
}
```

An MXBean is a JMX management MBean type with type mapping to OpenData; compliant classes can be registered via the appropriate mechanism. However, autodetection policy and how Spring identifies MBeans can depend on the version, proxy objects, and bean type. When an MXBean does not appear as expected, check `MBeanInfo`, exporter logs, and the JMX-compliance of the actual object, rather than automatically switching to exporting all methods.

With `DynamicMBean`:

```java
public class DynamicMonitor implements javax.management.DynamicMBean {
    // Implement getMBeanInfo, getAttribute, setAttribute,
    // getAttributes, setAttributes, and invoke according to the JMX contract.
}
```

A Dynamic MBean supplies its own metadata; it is also a form usable in JMX. However, this skeleton example is not yet a complete implementation. If you need hands-on practice, start with a Standard MBean because the contract is short and easy to cross-check.

### One Thing to Avoid

Do not infer that **just any interface** makes a bean JMX-compliant. For example, `Runnable`, `Closeable`, `OrderRepository`, or `TaskService` are not JMX management interfaces. The JMX specification recognizes Standard MBean/MXBean/DynamicMBean rules and appropriate wrappers.

## 8. AnnotationMBeanExporter and @ManagedResource: A Different Mechanism to Distinguish

Spring supports annotation-based export:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "demo.cache:type=CacheStatus")
public class CacheStatus {
    @ManagedAttribute
    public int getSize() {
        return 42;
    }
}
```

With `@EnableMBeanExport` or an appropriately configured `AnnotationMBeanExporter`, Spring can find beans annotated with `@ManagedResource`, read `@ManagedAttribute`/`@ManagedOperation` metadata, and register them via JMX.

This is a path of **autodetection based on annotation metadata**, which is not synonymous with the class implementing a `CacheStatusMBean` interface per standard JMX. A bean with `@ManagedResource` might not implement a Standard MBean interface yet still be turned into a Spring ModelMBean by an appropriate exporter.

Two typical cases:

```text
Standard MBean autodetection:
  Spring bean implements SomethingMBean
       -> MBeanExporter detects compliant MBean
       -> MBeanServer registration

Annotation-based autodetection:
  Spring bean annotated @ManagedResource
       -> AnnotationMBeanExporter / metadata assembler
       -> ModelMBean registration
```

In an application already using Spring Boot, auto-configuration may also participate in creating an exporter. Avoid enabling two overlapping mechanisms simultaneously for the same set of beans without a clear ownership and ObjectName strategy.

## 9. Autodetect Does Not Mean Exporting Every Bean

A common misconception:

```java
@Component
public class PaymentService {
    public String getApiKey() { /* ... */ }
    public void chargeCustomer() { /* ... */ }
}
```

If it only has `@Component`, without a JMX contract or appropriate management metadata, the bean should not be treated as an MBean merely because it has public getters. This has major security implications.

Yet autodetection should not be treated as a perfect security filter either. When a codebase has many beans implementing MBean interfaces or annotated with `@ManagedResource`, enabling autodetection can cause the number of exposed MBeans to grow whenever the team adds new beans.

Rules to apply:

1. Define a clear policy: which types of MBeans are allowed to be auto-exported.
2. Keep management interfaces small and containing only operationally meaningful attributes/operations.
3. Avoid getters that return secrets, raw configuration, user data, or large object graphs.
4. Choose stable ObjectNames; control collisions.
5. Inventory actual MBeanInfo after changes.
6. Restrict remote JMX using network access, authentication, TLS, and least privilege.

If strict boundaries are needed, use explicit `setBeans(...)` or an appropriate naming/filtering strategy instead of enabling autodetect without inventorying.

## 10. Configuration Variants of Autodetect

`MBeanExporter` supports configuring autodetection. Besides `setAutodetect(true)`, some Spring versions provide autodetect modes via constants such as `AUTODETECT_MBEAN` and `AUTODETECT_ASSEMBLER`. Constants and APIs used should be checked against the Spring version in use.

Conceptually:

| Mode | General Meaning |
|---|---|
| No autodetect | Export only explicitly listed/configured beans |
| Detect MBeans | Find beans that are already JMX-compliant MBeans |
| Detect assembler candidates | Find beans matching the metadata assembler, typically used for annotation-based export |
| Combined | Use all appropriate discovery sources |

Some Spring versions clearly distinguish autodetecting compliant MBeans from beans with metadata; therefore, you should not infer that enabling a single flag will select the exact same set of candidates across every version.

Whichever mode is chosen, the final result needs to be verified against the ObjectNames actually present in the MBeanServer. Changing the mode can expand the management surface, cause duplicate registrations, or alter startup behavior.

## 11. When Are MBeans Registered and Unregistered?

Spring typically initializes and exports MBeans during the ApplicationContext lifecycle. For non-lazy singleton beans, the exporter can discover and register them when the context refreshes. When the context closes, the exporter is responsible for unregistering the MBeans within its management scope according to the appropriate lifecycle mechanism.

However, there are exceptions to think about:

- Lazy beans might not have been created yet at the stage when the exporter runs autodetect.
- Proxied beans may have a different type/interface than the implementation.
- Prototype beans do not have the same lifecycle as singletons.
- Two ApplicationContexts sharing one MBeanServer may register duplicate names.
- An MBean registered directly outside Spring does not automatically become owned by the exporter.
- A remote client may invoke an operation while the service is `STARTING` or `STOPPING`.

Do not confuse **MBean registered** with **service ready**. An MBean can return a `STARTING` status to help operations know why the system is not ready yet; getters must handle this state safely.

If a management operation requires dependencies to be READY, check the runtime condition before executing.

## 12. Spring Proxies and Type-Checking Issues

Spring AOP can create a JDK dynamic proxy or a class-based proxy. With a JDK dynamic proxy, the proxy object typically exposes the proxied interfaces; methods only present on the target class might not appear through the proxy. With a class-based proxy, type relationships can differ.

Example:

```java
public interface WorkerManagementMBean {
    int getActiveWorkers();
}
```

If the `WorkerService` implementation implements the interface following MBean conventions, but Spring returns a proxy that does not preserve it or cannot be introspected by JMX as desired, autodetection might fail to recognize the bean as compliant or registration might fail.

How to diagnose:

- Determine whether the bean seen by the exporter is the target or a proxy.
- Inspect the actual list of interfaces on the proxy.
- Check the management interface and naming conventions.
- Read the root exception from registration.
- If a Spring annotation exporter is being used, check the metadata assembler and ObjectName.

Do not bypass the issue by changing the management interface to export all public methods, as that can inadvertently expose business functionality.

## 13. ObjectName and Conflict Policies

A JMX `ObjectName` must be unique within an `MBeanServer`. If an MBean is already registered with:

```text
demo.tasks:type=TaskMonitor,name=primary
```

another exporter trying to register the same name may receive an `InstanceAlreadyExistsException` or be subject to the exporter's registration policy, depending on configuration.

Spring supports configuring behavior when an MBean already exists. Conceptual options include: failing with an error, ignoring the new exporter's registration, or replacing the old MBean in permitted scenarios.

Do not use replace behavior just to “make the error go away” if it is unclear who owns the original MBean. Replacing an MBean belonging to the platform or another component can break monitoring tools.

To minimize conflicts:

- Plan dedicated domains, such as `company.orders`, `company.cache`.
- Have stable `type` and `name` keys.
- Ensure the naming strategy generates unique names for different beans.
- Control the number of exporters and the autodetection scope.
- Verify on the actual MBeanServer.

## 14. Inspecting the Registration List Using the JMX API

Once the exporter is running, you can use verification code:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(
        new ObjectName("demo.*:*"), null)) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println(
        name + " -> " + info.getClassName()
    );
}
```

The code above only looks at the **platform MBeanServer**. If the exporter uses a separate MBeanServer, you must query the exact instance managed by Spring. `queryNames` returns a set of results; do not rely on ordering to infer “which bean was exported first”.

### 14.1. Viewing Attributes and Operations

```java
MBeanInfo info = server.getMBeanInfo(objectName);

for (var attribute : info.getAttributes()) {
    System.out.println(
        attribute.getName() +
        " readable=" + attribute.isReadable() +
        " writable=" + attribute.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println("operation: " + operation.getName());
}
```

`objectName` must be the actual discovered name. Metadata helps distinguish:

- Whether the MBean has been registered.
- Which attributes are readable/writable.
- Which operations can be invoked.
- Whether there are extra or missing management methods compared to the management interface.

Do not rely solely on the MBean name appearing in JConsole: successful registration does not mean the contract is correct or the exported data is safe.

## 15. Hands-on Comparison of Three Configurations

**Scenario A — autodetection disabled.** Configure `MBeanExporter` with a `setBeans(...)` list containing only `TaskMonitor`. Verify that only the explicitly mapped MBean is registered. Add a bean implementing `CacheMonitorMBean` without adding it to the mapping; verify the result.

**Scenario B — autodetection enabled.** Enable `setAutodetect(true)`. With compliant beans in the context, query the MBeanServer to see which additional MBeans appear. Record the actual ObjectNames and inspect their metadata. If a bean is missing, check compliance rules, lifecycle, and proxies.

**Scenario C — annotation-based export.** Add a `@ManagedResource` bean that does not implement a Standard MBean interface. Use `@EnableMBeanExport` or the corresponding `AnnotationMBeanExporter` and compare how the MBean is recognized. Avoid running conflicting configurations with the same ObjectName simultaneously.

The scenarios should be run separately to clearly see the differences. Enabling an additional exporter in the same context can lead to conflicts rather than a useful comparison.

## 16. Common Errors and How to Handle Them

### 16.1. Bean has an MBean interface but is not visible in JConsole

Check whether the bean actually exists in the context, whether the exporter has autodetect enabled, and whether it connects to the right MBeanServer. Check proxies and the actual ObjectName rather than searching only by class name.

### 16.2. Spring reports NotCompliantMBeanException

Check Standard MBean naming rules, methods in the interface, Java types, and compatibility between target/proxy. An interface with a nearly matching name is not necessarily considered compliant by JMX.

### 16.3. Bean has @ManagedResource but is not detected

Check whether there is an `AnnotationMBeanExporter` or appropriate metadata export infrastructure, whether the bean is Spring-managed, and whether the autodetection configuration includes annotated candidates. A regular `MBeanExporter` in compliant-MBean detection mode does not mean an annotation exporter is fully enabled.

### 16.4. Expected ObjectName not found

Autodetection and naming strategy are two different things. Query the actual name, check the naming strategy and configured properties/domain, and then construct an appropriate query.

### 16.5. Duplicate MBeans when enabling multiple exporters

Identify which exporter owns each ObjectName, remove redundant configuration, or clearly partition resources. Avoid replacing another component's MBean unintentionally.

### 16.6. Bean is found but not yet ready

An MBean may register during startup before background initialization finishes. Getters should report a state such as `STARTING`; operations with side effects must check readiness.

### 16.7. MBean appears and then disappears

Check whether the application context was closed, whether the bean/exporter has an abnormal lifecycle, whether the JVM restarted, or whether the ObjectName was re-registered. JConsole being connected to an old process can also be misleading.

### 16.8. Number of MBeans grows unexpectedly after adding code

With autodetection, a new class implementing a JMX interface or a new annotated bean may be automatically exported. Inventory new MBeans and ensure management policies are followed.

## 17. Security When Using Autodetection

Autodetection is convenient, but it can cause **the management surface to grow without a single new explicit mapping line**. Therefore, every management interface and `@ManagedResource` must be reviewed like a privileged API.

Operational principles:

1. Never expose credentials, API keys, session tokens, private keys, or user data through getters.
2. Do not export dangerous operations just for debugging convenience.
3. Add validation for writable attributes and state-changing operations.
4. Do not expose remote JMX to public networks; control authentication, TLS, network access, and permissions.
5. Distinguish read-only JMX attributes from user authorization mechanisms: read-only can still leak data.
6. Inventory ObjectName/MBeanInfo after deployment.
7. Keep management interfaces small, clearly describing semantics and metric units.
8. If a compliance environment requires an explicit allowlist, consider disabling autodetection and using explicit mappings.

**Autodetection is not a security boundary.** It is a mechanism for finding and registering candidates. Connection/invocation permissions, data safety, and business behavior must still be designed independently.

## 18. Practice Exercises

### Exercise 1 — Autodetected Standard MBean

Create `CounterMBean` with `getCount()` and `reset()`. Write `Counter` implementing that interface and declare it as a Spring bean. Enable `MBeanExporter.setAutodetect(true)`, find the ObjectName on the MBeanServer, read the attribute, and invoke the operation.

### Exercise 2 — Is an ordinary bean exported?

Add `BillingService` with no MBean interface and no JMX annotations, even though it has multiple public methods. Verify that it does not automatically appear as a Standard MBean when using only compliant-MBean autodetection.

### Exercise 3 — MXBean and type mapping

Create `WorkerPoolMXBean` with `int getActiveWorkers()` and `Map<String,Integer> getByQueue()`. Verify the compliant class and how the Map value is presented through JMX when registered by the exporter.

### Exercise 4 — Annotation-based export

Create a `CacheStatus` bean using `@ManagedResource`/`@ManagedAttribute` without a `CacheStatusMBean` interface. Enable annotation export and observe the difference from Standard MBean autodetection.

### Exercise 5 — Naming collision

Export two beans under the same ObjectName using two different configurations in a test environment. Observe the registration error, then fix the naming strategy or key mapping so that names are unique. Do not attempt to replace an MBean not owned by the application.

### Exercise 6 — MBeanInfo inventory

Write code that retrieves `MBeanInfo` and prints attributes/operations for every ObjectName in the `demo.*` domain. Compare against the management interfaces in source, marking methods that should not be exposed.

### Exercise 7 — Proxy effect

Enable Spring AOP for a service implementing a management interface. Observe the proxy type and the interfaces it exposes; verify whether the MBean is detected/registered as before.

## 19. Self-Check Questions

1. What manual step does `MBeanExporter.setAutodetect(true)` help reduce?
2. By what rules is a Standard MBean recognized?
3. How do MXBean and DynamicMBean differ from Standard MBean at the contract level?
4. Why does `@Component` alone not mean a bean will become an MBean?
5. How does `AnnotationMBeanExporter` differ from the compliant-MBean detection mechanism?
6. Which two tasks do autodetection and `ObjectNamingStrategy` solve?
7. Why can enabling two exporters cause ObjectName collisions?
8. How can a proxied bean change MBean discoverability?
9. Why is `MBeanInfo` an important verification step?
10. What security risks need to be considered if many new MBeans are automatically exported?

## 20. Takeaways

**Autodetection in Spring JMX helps the exporter find eligible management beans without requiring explicit per-bean mapping.** Objects that already implement a JMX-compliant contract are central to MBean detection; beans annotated with `@ManagedResource` go through the corresponding metadata export mechanism. Autodetection does not mean exporting all Spring beans.

Good design requires clearly separating selection, naming, registration, and lifecycle; verifying the actual `ObjectName` and `MBeanInfo`; keeping the management surface small; and protecting JMX connections. When transparency or strict control matters more than reducing configuration, use explicit mapping instead of unrestricted autodetection.
