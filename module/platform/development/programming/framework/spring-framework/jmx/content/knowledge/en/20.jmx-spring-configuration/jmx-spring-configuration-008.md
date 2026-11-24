# Inspecting Effective Configuration from ApplicationContext in Spring Framework JMX

## 1. Why Shouldn't You Only Read Configuration Files?

In Spring Framework, JMX configuration can be declared via `@Configuration`, `@Bean`, `@EnableMBeanExport`, XML, Spring Boot auto-configuration, or a set of configurations imported from multiple modules. When an application runs, what matters is not only **what was written in source code**, but **which beans and settings actually exist in the initialized ApplicationContext**.

For example, you might see:

```java
@Configuration
@EnableMBeanExport
class JmxConfig {}
```

yet JConsole does not show the expected MBean. Or a bean has `@ManagedResource` yet still does not appear because component scan missed it, a different context is being queried, the ObjectName changed, the exporter did not run, a registration collision occurred, or the application used a different MBeanServer.

**Inspecting effective configuration** means querying Spring and JMX state after context refresh to answer verifiable questions:

1. How many `MBeanExporter` / `AnnotationMBeanExporter` beans exist in the context?
2. Which exporter is actually used, and which context owns it?
3. Is the managed bean registered in Spring?
4. Which `MBeanServer` is used: the platform server or another server?
5. Which ObjectNames exist in the MBeanServer?
6. Which attributes, operations, and notifications are exposed?
7. Do any profiles/properties/conditions alter the export path from what was expected?

This lesson provides an observation workflow from **ApplicationContext → bean → exporter → MBeanServer → MBeanInfo**, avoiding guesswork from annotations alone.

## 2. Diagram of Declared Configuration vs. Runtime Configuration

```text
application.yml / environment / @Configuration / XML
                         |
                         v
                    BeanFactory
                         |
            conditional / profile / imports
                         |
                         v
                ApplicationContext
                  /       |       \
                 /        |        \
        business bean   exporter   MBeanServer
             |             |            |
             +-------------+------------+
                           |
                  registration attempt
                           |
                           v
                       ObjectName
                           |
                        MBeanInfo
                           |
                    JConsole/client
```

Each arrow is a step where errors or discrepancies can occur. A bean being created successfully does not mean it was exported; an exporter existing does not mean it registered the expected name; an ObjectName existing does not necessarily represent the right target bean in a multi-context system.

Distinguish three datasets:

| Where to Check | Tells You | Does Not Guarantee by Itself |
|---|---|---|
| `Environment` / property sources | Resolved configuration values | Beans were created using those values |
| `ApplicationContext` | Beans, types, scopes, lifecycles, definition sources | MBeans are registered in JMX |
| `MBeanServer` and `MBeanInfo` | Actual registrations, attributes, operations | Business dependencies are healthy |

They complement each other rather than replacing one another.

## 3. Minimal Hands-On: Creating an MBean from Spring

To illustrate, create an explicit managed bean:

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "lab.spring:type=TaskMonitor,name=primary",
    description = "Task monitor"
)
public class TaskMonitor {
    private final AtomicLong completed = new AtomicLong();
    private volatile int warningThreshold = 100;

    @ManagedAttribute(description = "Completed task count")
    public long getCompleted() {
        return completed.get();
    }

    @ManagedAttribute(description = "Warning threshold")
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @ManagedAttribute
    public void setWarningThreshold(int value) {
        if (value < 1 || value > 1000) {
            throw new IllegalArgumentException("Range: 1..1000");
        }
        warningThreshold = value;
    }

    @ManagedOperation(description = "Reset statistics")
    public void reset() {
        completed.set(0);
    }

    public void recordCompleted() {
        completed.incrementAndGet();
    }
}
```

The bean above has annotations but requires an appropriate export mechanism. In plain Spring Framework:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = TaskMonitor.class)
@EnableMBeanExport
public class LabConfiguration {
}
```

`@ComponentScan` helps the bean get discovered in the context. `@EnableMBeanExport` enables annotation-based JMX export infrastructure. In a Spring Boot application, JMX export may also be affected by auto-configuration and `spring.jmx.enabled`; do not copy multiple exporter mechanisms with overlapping scope into one application simultaneously.

The goal of this step is not writing a REST API or running a web server. All you need is a Spring `ApplicationContext` with the bean, exporter, and appropriate MBeanServer.

## 4. Checking Whether a Bean Exists in ApplicationContext

After the context initializes:

```java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(LabConfiguration.class)) {

    boolean present = context.containsBean("taskMonitor");
    System.out.println("taskMonitor bean present = " + present);

    String[] names = context.getBeanNamesForType(TaskMonitor.class);
    System.out.println("Bean names = " + java.util.Arrays.toString(names));
}
```

Import:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
```

Two different checks:

- `containsBean("taskMonitor")` asks whether the context can resolve a bean by that name (including ancestor lookup per API semantics).
- `getBeanNamesForType(TaskMonitor.class)` finds bean names matching the type via BeanFactory/type lookup, affected by proxies, FactoryBeans, and lookup options.

The bean name generated by `@Component` by convention is usually `taskMonitor`, though if you use `@Component("customName")`, declare another `@Bean`, or configure custom naming, the actual name may differ. **Do not guess the bean name from the class name and treat that as proof.**

If the bean is not in the context, checking JMX registration will not resolve the root cause. Inspect component scan, `@Import`, profiles, conditional configuration, and how the context is created.

## 5. Finding Active JMX Exporters

Spring uses `MBeanExporter` as the core export component; `AnnotationMBeanExporter` is the variant for annotation metadata.

You can list them by type:

```java
import java.util.Map;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

Map<String, MBeanExporter> exporters =
    context.getBeansOfType(MBeanExporter.class);

System.out.println("MBeanExporter count = " + exporters.size());
exporters.forEach((name, bean) ->
    System.out.println(name + " -> " + bean.getClass().getName())
);

Map<String, AnnotationMBeanExporter> annotated =
    context.getBeansOfType(AnnotationMBeanExporter.class);

System.out.println(
    "AnnotationMBeanExporter count = " + annotated.size()
);
```

This is an important step because an application can end up with multiple exporters due to:

- An `@EnableMBeanExport` in an imported configuration.
- A manually declared `MBeanExporter` bean.
- Spring Boot auto-configuration.
- A submodule creating its own exporter.
- Multiple independent or parent/child `ApplicationContext` instances.

If two exporters register the same ObjectName, refresh may hit a collision, or the outcome depends on the registration policy `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, `REPLACE_EXISTING`.

**Note:** `getBeansOfType` on one context has specific type-lookup semantics and is not automatically an inventory of every exporter across all other contexts in the JVM. With parent/child or multiple independent contexts, inspect each context that owns the relevant configuration.

## 6. Do Not Confuse Registered Bean Definitions with Initialized Beans

A `BeanDefinition` can exist before a singleton is created. Lazy beans or scoped beans can be instantiated later. Thus the question "does the configuration contain this bean?" differs from "has the actual instance been created and initialized?".

Example:

```java
@Lazy
@Component
public class LazyMonitor {
    // ...
}
```

A lazy bean may have its definition registered by Spring without instantiating the object immediately on context refresh. Whether the exporter touches the bean, triggers initialization, or registers it depends on the autodetection/export mechanism and how the bean is configured.

Good to know:

- `containsBeanDefinition` / `getBeanDefinitionNames` report local definitions when using an appropriate BeanFactory/ConfigurableApplicationContext.
- `getBean(...)` retrieves the actual bean and **may trigger initialization**.
- `getBeansOfType(...)` may affect eager initialization depending on the API overload and FactoryBean types.
- A singleton being created does not mean its external dependencies are READY.

When diagnosing startup, prefer reading metadata and lifecycle logs before proactively calling `getBean` on lazy beans, because the investigation itself could alter the state you want to observe.

## 7. Identifying the Exact MBeanServer in Use

One of the most common reasons JConsole does not see an MBean is that the exporter registered it into a different MBeanServer than the one the tool is reading.

The JDK provides the platform server:

```java
MBeanServer platformServer =
    ManagementFactory.getPlatformMBeanServer();
```

Spring also supports creating or looking up servers via `MBeanServerFactoryBean`, `MBeanServerFactory`, or an application-declared `MBeanServer` bean.

Listing server beans in the context:

```java
import javax.management.MBeanServer;
import java.util.Map;

Map<String, MBeanServer> servers =
    context.getBeansOfType(MBeanServer.class);

servers.forEach((name, server) -> {
    System.out.println(
        "MBeanServer bean=" + name +
        ", identity=" + System.identityHashCode(server) +
        ", defaultDomain=" + server.getDefaultDomain()
    );
});
```

`System.identityHashCode` is an indicator for in-process debugging; it is not a durable identifier or guaranteed to be strictly unique. `getDefaultDomain()` also does not distinguish every server.

Compare object references when appropriate:

```java
boolean same =
    serverBean == ManagementFactory.getPlatformMBeanServer();
System.out.println("Using platform server bean = " + same);
```

**Important:** having an `MBeanServer` bean in the context does not prove every exporter uses it. If an exporter is explicitly configured with `setServer(...)`, or looks up a different server itself, inspect the actual configuration and registration on the right registry.

## 8. Querying ObjectName: Actual Proof of Registration

With the right `MBeanServer`, use:

```java
import javax.management.ObjectName;

ObjectName expected = new ObjectName(
    "lab.spring:type=TaskMonitor,name=primary"
);

System.out.println(
    "Registered = " + server.isRegistered(expected)
);
```

Or list a domain:

```java
for (ObjectName name : server.queryNames(
        new ObjectName("lab.spring:*"), null)) {
    System.out.println("MBean: " + name);
}
```

Using `queryNames` is better than inferring from bean names, because an ObjectName may come from:

- `@ManagedResource(objectName = "...")`.
- Explicit bean mapping via `MBeanExporter.setBeans(...)`.
- `ObjectNamingStrategy`.
- Naming based on bean key or domain.
- An MBean already registered by another module.

An MBean existing in the registry also **does not prove by itself that the exporter you are checking registered it**. In a multi-context system, another exporter may be behind the same ObjectName, or a registration policy kept/replaced an earlier object.

To verify identity, combine registration checks with metadata, attribute behavior, and exporter ownership logs.

## 9. Using MBeanInfo to Verify the Management Contract

After confirming the ObjectName exists:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(expected);

System.out.println("MBean class: " + info.getClassName());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "ATTR %s type=%s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("OP " + operation.getName());
}
```

For the `TaskMonitor` example, you expect to see attributes such as `Completed` and `WarningThreshold`, and operation `reset`, if the annotation metadata assembler/exporter is properly configured. The `recordCompleted()` method is not marked for export so it does not appear in the intended annotation-based management interface.

With Spring ModelMBeans, `MBeanInfo.getClassName()` may reflect the ModelMBean/wrapper class rather than the original business class. Therefore, do not use className in metadata alone to conclude ownership.

Reading `MBeanInfo` is a safer check than fetching every attribute value, especially if an MBean might hold sensitive data. **Do not dump all JMX values just to inventory MBeans**, because that can leak tokens, credentials, configuration, or user data.

## 10. Viewing Effective Configuration from Environment

Spring `Environment` combines property sources in priority order. For a property:

```java
import org.springframework.core.env.Environment;

Environment env = context.getEnvironment();

String value = env.getProperty("spring.jmx.enabled");
System.out.println("spring.jmx.enabled = " + value);
```

This example fits **Spring Boot** when the application uses that property. In plain Spring Framework, a property named `spring.jmx.enabled` does not automatically control `@EnableMBeanExport` unless you write configuration reading that property.

Things to distinguish:

- `Environment.getProperty(...)` returns the **resolved value** according to property sources.
- A property existing does not prove it was applied by auto-configuration.
- A property may be ignored due to conditions/profiles/versions.
- A manual exporter may still run even if an auto-configuration property has no effect on it.

Thus, the question "is JMX enabled?" cannot be answered solely from an `Environment` value. You must inspect exporter beans and the MBean registry.

### 10.1. Do not print secrets when debugging property sources

`Environment` may contain passwords, tokens, URIs with credentials, or internal details. Avoid printing all property keys/values to stdout or a JMX attribute. When you need to determine a property's source, log only non-sensitive names and configuration sources, using appropriate masking/redaction; never log secret values.

## 11. Profiles and Conditional Configuration

Spring can enable/disable beans based on `@Profile`, `@Conditional`, `@ConditionalOnProperty` in Boot, or other conditions.

Example:

```java
@Configuration
@Profile("ops")
@EnableMBeanExport
public class OpsJmxConfiguration {
}
```

If the `ops` profile is not active, this configuration is not applied as you expect. You can check:

```java
String[] profiles = context.getEnvironment().getActiveProfiles();
System.out.println(
    "Active profiles = " + java.util.Arrays.toString(profiles)
);
```

However, `getActiveProfiles()` only reports active profiles; it does not confirm that the exporter bean was created. Continue checking by bean type.

With Spring Boot, the condition evaluation report and Actuator endpoints can aid diagnostics if properly configured and secured. Never expose management endpoints to public networks. In plain Spring Framework, rely on bean definitions, logs, and runtime inspection of the context.

## 12. Parent/Child ApplicationContexts and Multiple Independent Contexts

A traditional Spring web application may have a root context and a child servlet context. A modular application may have multiple independent contexts in the same JVM.

```text
Root ApplicationContext
    +-- business services
    +-- exporter A

Child WebApplicationContext
    +-- controllers
    +-- exporter B

Both may point to the same platform MBeanServer.
```

Inspecting one context does not mean you have inspected every context. Beans in the parent can be seen by the child via lookup mechanics, whereas the parent does not automatically see child beans. Moreover, a normal `getBeansOfType` call is not always a search across the entire hierarchy.

When listing beans across a hierarchy is needed, Spring offers `BeanFactoryUtils.beansOfTypeIncludingAncestors(...)`, keeping in mind that local beans can shadow parent beans by name. However, when the goal is exporter ownership, inspect **each context individually** to know which bean belongs to which context.

With multiple independent contexts, you need actual references to each context; there is no default global API for all ApplicationContexts in a JVM.

When both exporters register the same `ObjectName` into one server, the registration policy affects the outcome. Thus "JMX works in context A" does not prove context B's MBean exported properly.

## 13. @EnableMBeanExport vs. Manual Exporter Configuration

Spring allows enabling annotation export:

```java
@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
```

Or creating a dedicated exporter:

```java
@Bean
public MBeanExporter mBeanExporter(
        MBeanServer server,
        TaskMonitor taskMonitor) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(java.util.Map.of(
        "lab.spring:type=TaskMonitor,name=primary",
        taskMonitor
    ));
    return exporter;
}
```

The two approaches can serve different needs. If both coexist and register the same ObjectName, collisions, ignored registrations, or replacements can occur depending on `RegistrationPolicy`.

Effective-configuration inspection must answer:

1. Which export mechanisms are present in the context?
2. How many exporters actually initialize?
3. Does each exporter select beans via annotations, autodetect, or explicit mapping?
4. Do target ObjectNames overlap with another exporter?
5. Which MBeanServer do they use?

A bean exported by a manual exporter may not need `@ManagedResource` if it is a Standard MBean/JMX-compliant object or configured with a suitable assembler. Conversely, annotations may have no effect without a matching metadata export mechanism.

## 14. MBeanExporter and RegistrationPolicy

An `ObjectName` must be unique within an MBeanServer. Spring `RegistrationPolicy` decides how to handle an already-existing name:

| Policy | Core Meaning |
|---|---|
| `FAIL_ON_EXISTING` | Throws an error when registration hits an existing name |
| `IGNORE_EXISTING` | Keeps the existing MBean and skips the new registration |
| `REPLACE_EXISTING` | Replaces the existing registration per exporter behavior |

Example:

```java
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

With `IGNORE_EXISTING`, a context can start successfully while the visible MBean belongs to an old module. With `REPLACE_EXISTING`, metadata and state can change under the same ObjectName. Therefore, to check "effective configuration", do not just count exporter beans—read the registry and verify post-registration behavior.

Define clear ObjectName ownership; do not use policies to mask naming bugs in multi-context systems.

## 15. Diagnostic Pattern Usable at Startup

A convenient approach is creating a diagnostic component that runs after context refresh and prints **non-sensitive metadata**.

```java
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jmx.export.MBeanExporter;

public final class JmxDiagnostics {

    public static void inspect(ConfigurableApplicationContext context)
            throws Exception {

        System.out.println("Context id: " + context.getId());
        System.out.println("Active profiles: " + Arrays.toString(
            context.getEnvironment().getActiveProfiles()
        ));

        Map<String, MBeanExporter> exporters =
            context.getBeansOfType(MBeanExporter.class);

        System.out.println("Exporters: " + exporters.keySet());

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        for (ObjectName name : server.queryNames(
                new ObjectName("lab.spring:*"), null)) {
            System.out.println("Registered MBean: " + name);
        }
    }
}
```

Call after the context has refreshed:

```java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(LabConfiguration.class)) {

    JmxDiagnostics.inspect(context);
}
```

`AnnotationConfigApplicationContext` must be imported from `org.springframework.context.annotation`. This tool inspects the **platform MBeanServer**; if the exporter uses a different server, pass that exact server to diagnostics rather than only using the platform server.

When applying this in a real application, use a logger at an appropriate debug level, and avoid printing excessive sensitive information or dumping all system properties.

## 16. Confirming with an Actual JMX Operation

Once the right MBean is identified, you can read a non-sensitive operational attribute:

```java
ObjectName name = new ObjectName(
    "lab.spring:type=TaskMonitor,name=primary"
);

Object completed = server.getAttribute(name, "Completed");
System.out.println("Completed = " + completed);
```

If the attribute exists and can be read, you confirm more than `isRegistered`: JMX actually routes calls through to the MBean.

For operations with side effects such as `reset()`, do not invoke them just to "test" in production. Run those in test environments or build a suitable read/status-returning operation. The goal of configuration inspection is not mutating live production data.

If `getAttribute` fails, distinguish between:

- Wrong ObjectName or MBean was unregistered.
- Attribute does not exist / is not readable.
- Getter threw an exception.
- Target bean is not READY yet.
- Caller lacks access permissions.
- Querying a different MBeanServer.

## 17. Spring Boot: Condition Report and Actuator

In Spring Boot, additional tools may be available to inspect effective configuration:

- Condition evaluation report shows which auto-configurations matched or did not match conditions.
- `/actuator/beans` helps view bean definitions/relationships if the endpoint is enabled.
- `/actuator/conditions` helps inspect auto-configuration conditions.
- `/actuator/env` or `/actuator/configprops` can show configuration, though they must be properly secured and sanitized.
- `spring.jmx.enabled` is a common configuration to control Boot's JMX export.

Do not rely on Actuator as the sole source of truth. Endpoints may be disabled, vary by version, or not fully reflect registrations inside the MBeanServer. **ApplicationContext inspection and JMX registry inspection must be combined.**

Actuator provides powerful observability; do not expose endpoints that leak environment details or configuration publicly. If your organization has a security policy, follow it rather than turning on all actuator endpoints for debugging.

## 18. Common Mistakes When Inspecting Effective Configuration

### 18.1. "I see @ManagedResource in code so the MBean must exist"

Incorrect. The bean might not be component-scanned or exporter metadata might not be active. Check the context first, then the registry.

### 18.2. "I see an MBeanExporter bean so every MBean must appear"

An exporter existing does not guarantee it selected the right beans, the naming strategy generated the right names, or registration succeeded. Read `queryNames` and `MBeanInfo`.

### 18.3. "JConsole does not show the MBean so the bean does not exist"

JConsole might be connected to the wrong JVM, wrong MBeanServer, or the UI hasn't refreshed. Separate Spring bean checks from JMX registration checks.

### 18.4. "Environment returning spring.jmx.enabled=true is enough"

In Spring Boot, that property relates to auto-configuration; in plain Spring Framework it does not enable JMX export by itself. Check exporter beans and actual conditions.

### 18.5. "I called getBeansOfType so I found all exporters across all contexts"

Incorrect in multi-context applications. Know which context/hierarchy is being inspected, and avoid confusing parent/child beans with independent modules.

### 18.6. "The MBean is present so the service is READY"

An MBean can be exported before background initialization finishes. Getters should report `STARTING`/`READY` when needed; operations with side effects must guard themselves.

### 18.7. "MBeanInfo className is the target bean"

With ModelMBeans/wrappers, className may be an adapter class. Combine metadata, ObjectName, bean source, and exporter logs.

### 18.8. "I'll invoke every operation to see if it works"

This is a dangerous way to check. Operations can restart workers, clear caches, or reset counters. Only read metadata and safe attributes in production.

### 18.9. "There are two exporters but no errors, so everything is fine"

One exporter may be using IGNORE_EXISTING, or the two exporters may select different MBeans. Check actual ObjectNames and ownership; do not infer from bean counts alone.

## 19. Step-by-Step Inspection Workflow

Apply sequentially when a Spring MBean does not appear or behaves unexpectedly:

1. **Identify JVM and context:** which process/PID is running, and which root or child context needs inspection?
2. **Identify profiles/properties:** are active profiles and relevant properties correct?
3. **Check managed bean:** are the bean definition and instance present in the context?
4. **Check exporters:** is there an `MBeanExporter`/annotation exporter bean, and are there multiple exporters?
5. **Check MBeanServer:** which registry does the exporter use; platform or custom server?
6. **Check ObjectName:** under what name is the MBean registered?
7. **Check MBeanInfo:** do attributes/operations match the contract?
8. **Read a safe attribute:** confirm runtime calls pass through JMX.
9. **Check lifecycle and collisions:** are there other contexts, registration policies, lazy startup, or proxies?
10. **Record findings:** bean name, context ID, ObjectName, and relevant exceptions; avoid printing secrets.

This workflow narrows down the cause layer by layer instead of making arbitrary changes to multiple configurations at once.

## 20. Practice Exercises

**Exercise 1 — Context and exporter.** Create a context with `@EnableMBeanExport` and a `@ManagedResource` bean. Print `MBeanExporter` bean names, verify ObjectName via `isRegistered`, then list `MBeanInfo` attributes.

**Exercise 2 — Wrong component scan.** Move `TaskMonitor` outside the scanned package, start the context, and observe the difference between "bean missing" and "exporter exists with no resources to export". Then fix component scan.

**Exercise 3 — Two MBeanServers.** Create servers A and B in a test JVM; export the MBean to A but query B. Record the result, then pass the right server to diagnostics. Explain why multiple registries can exist in the same JVM.

**Exercise 4 — Changing profile.** Put `@Profile("ops")` on the JMX configuration. Run with and without the profile, comparing `getActiveProfiles()`, exporter beans, and ObjectNames.

**Exercise 5 — Duplicate ObjectName.** Create two exporters trying to register the same ObjectName in a test environment. Observe `FAIL_ON_EXISTING` and `IGNORE_EXISTING`, noting which bean is actually visible via JMX.

**Exercise 6 — Spring Boot conditions.** In a Boot application with secured Actuator, compare JMX export condition evaluation with `spring.jmx.enabled`, exporter beans, and actual `MBeanInfo`.

**Exercise 7 — Metadata instead of dumping values.** Write diagnostics logging only attribute names and read/write flags. Explain why you should not automatically call `getAttribute` on every field when secrets may be present.

## 21. Self-Check Questions

1. Why is reading `@Configuration` files not enough to conclude JMX is working?
2. What does `getBeansOfType(MBeanExporter.class)` tell you, and what are its limitations?
3. Can a bean with `@ManagedResource` that is not in the context be picked up by the exporter?
4. Is an `MBeanServer` bean in the context always the registry the exporter uses?
5. What proof do `queryNames` and `isRegistered` provide?
6. Why is `MBeanInfo.getClassName()` not always the business bean class?
7. Does plain Spring Framework automatically understand `spring.jmx.enabled`?
8. How do parent/child contexts affect finding exporters?
9. If an ObjectName already has an MBean, how do you know it represents the expected target object?
10. Why is checking metadata safer than invoking every operation to test?

## 22. Takeaways

**The effective configuration of Spring JMX is the actual runtime result of the ApplicationContext and MBeanServer after initialization**, not merely the annotations or properties written in files. Follow the chain `Environment → bean → exporter → MBeanServer → ObjectName → MBeanInfo`, checking the right context, right registry, and right management contract.

Good diagnostics always separate whether a bean exists in Spring from whether an MBean is registered in JMX, avoid dumping secrets, and avoid calling operations with side effects just to verify configuration. When using multiple contexts or exporters, ownership and registration policy must be clearly defined so monitoring data accurately reflects the application.
