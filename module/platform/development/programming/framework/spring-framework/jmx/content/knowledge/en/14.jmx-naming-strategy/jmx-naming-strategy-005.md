# @ManagedResource Sets the ObjectName for a Bean in Spring Framework JMX

## Lesson Objectives

After this lesson, you will be able to:

- Explain what an \`ObjectName\` is and why an MBean needs a valid, unique name within an \`MBeanServer\`.
- Use \`@ManagedResource(objectName = "...")\` to specify a JMX name for a Spring bean.
- Distinguish **Spring bean name**, **Java class name**, and **JMX ObjectName**.
- Understand the roles of \`MetadataNamingStrategy\`, \`AnnotationJmxAttributeSource\`, \`MBeanExporter\`, and the autodetection mechanism.
- Know how to verify the actual exported ObjectName using \`MBeanServer\`.
- Design a naming scheme that remains maintainable when refactoring Java code or deploying multiple beans/instances.
- Diagnose errors related to invalid ObjectNames, name collisions, wrong servers, and exporter configuration.

## 1. ObjectName Is the Management Identity of an MBean

In Java Management Extensions (JMX), MBeans are registered in \`MBeanServer\` under a \`javax.management.ObjectName\` value. JMX clients use the ObjectName to locate the right MBean before reading attributes or invoking operations.

Example:

\`\`\`text
learning.jmx:type=CacheMonitor,name=Products
\`\`\`

This name consists of:

- **Domain:** \`learning.jmx\`.
- **Key properties:** \`type=CacheMonitor\` and \`name=Products\`.

A query example:

\`\`\`java
ObjectName name = new ObjectName(
        "learning.jmx:type=CacheMonitor,name=Products"
);

Object value = server.getAttribute(name, "EntryCount");
\`\`\`

ObjectName finds **which MBean**, while \`EntryCount\` specifies **which attribute** on that MBean.

ObjectName is **not a URL or a remote JMX address**. If a client lives in another JVM, it still needs an \`MBeanServerConnection\` pointing to the right \`MBeanServer\` through an authorized connection mechanism.

### Uniqueness of ObjectName

Within a single \`MBeanServer\`, an ObjectName can be bound to only one MBean at a time. Two beans registering the same name can cause \`InstanceAlreadyExistsException\` or be handled according to the configured registration policy.

Two different JVMs can still have the same ObjectName without direct conflict because each JVM has its own registry. When aggregating management data from multiple JVMs, you must also retain the instance/connection identity.

## 2. How Does @ManagedResource Set the ObjectName?

Spring Framework supports the annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
\`\`\`

You can place the ObjectName directly on the class:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=Products",
    description = "Product cache management"
)
public class ProductCacheMonitor {
    // ...
}
\`\`\`

When an exporter uses the corresponding metadata strategy, \`objectName\` on \`@ManagedResource\` is used to name the MBean.

Visualization:

\`\`\`text
Spring bean: productCacheMonitor
    |
    | class has @ManagedResource(objectName=...)
    v
AnnotationJmxAttributeSource
    |
    v
MetadataNamingStrategy
    |
    | creates javax.management.ObjectName
    v
MBeanExporter
    |
    | registers with MBeanServer
    v
learning.jmx:type=CacheMonitor,name=Products
\`\`\`

Point to understand: the annotation only **provides naming metadata**. A bean actually obtains an ObjectName in \`MBeanServer\` only after the exporter is enabled, detects or receives the bean, and registers it successfully.

### Does the Annotation Change the Bean Name?

No. Suppose a Spring bean is named \`cacheManagerForProducts\`, the Java class is \`ProductCacheMonitor\`, and the annotation says:

\`\`\`text
learning.jmx:type=CacheMonitor,name=Products
\`\`\`

The three values serve three systems:

| Concept | Example | Purpose |
|---|---|---|
| Spring bean name | \`cacheManagerForProducts\` | Identifies the bean in \`ApplicationContext\` |
| Java class name | \`ProductCacheMonitor\` | Implementation type in code |
| JMX ObjectName | \`learning.jmx:type=CacheMonitor,name=Products\` | Published MBean identifier |

They can differ and remain completely valid. One reason to use a fixed ObjectName is so **JMX clients do not have to change their configuration just because a developer renames a Spring bean or Java class**.

## 3. Complete Spring Framework Example

We build a cache management bean with one attribute and one operation.

### 3.1. Managed Resource

File \`ProductCacheMonitor.java\`:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=Products",
    description = "Product cache monitor"
)
public class ProductCacheMonitor {

    private final AtomicInteger entryCount = new AtomicInteger(20);

    @ManagedAttribute(description = "Current cache entry count")
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedOperation(description = "Clear product cache")
    public void clear() {
        entryCount.set(0);
    }
}
\`\`\`

\`@ManagedResource\` describes the MBean and registration name. \`@ManagedAttribute\` describes the \`EntryCount\` attribute; \`@ManagedOperation\` publishes the \`clear\` operation.

### 3.2. Configuring JMX with @EnableMBeanExport

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean(name = "cacheManagerForProducts")
    ProductCacheMonitor productCacheMonitor() {
        return new ProductCacheMonitor();
    }
}
\`\`\`

Here:

- The Spring bean is named \`cacheManagerForProducts\`.
- The Java class is named \`ProductCacheMonitor\`.
- The JMX ObjectName is \`learning.jmx:type=CacheMonitor,name=Products\`.

When the \`ApplicationContext\` initializes successfully, the Spring exporter can read the metadata and export the bean into the corresponding \`MBeanServer\`.

### 3.3. Observing Registration

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxDemo {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxConfiguration.class)) {

            MBeanServer server =
                    ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "learning.jmx:type=CacheMonitor,name=Products"
            );

            System.out.println("Registered: "
                    + server.isRegistered(name));

            if (server.isRegistered(name)) {
                System.out.println("EntryCount: "
                        + server.getAttribute(name, "EntryCount"));
            }

            System.out.println("Press Enter to close");
            System.in.read();
        }
    }
}
\`\`\`

**Condition:** The example reads the JVM's platform \`MBeanServer\`. If the exporter has been configured to use a different \`MBeanServer\`, you must obtain that exact server. How \`@EnableMBeanExport\` selects a server may depend on configuration, any provided \`MBeanServer\` bean, or the framework version.

With a configuration exporting to the platform server, example output:

\`\`\`text
Registered: true
EntryCount: 20
Press Enter to close
\`\`\`

In JConsole, connect to the right Java process, find the domain \`learning.jmx\`, and select the MBean with key properties \`type=CacheMonitor,name=Products\`.

## 4. Where Does MetadataNamingStrategy Read objectName From?

Spring has the class \`org.springframework.jmx.export.naming.MetadataNamingStrategy\`. When used together with \`AnnotationJmxAttributeSource\`, it can read a bean's \`@ManagedResource\` metadata and convert the \`objectName\` value into an \`ObjectName\`.

Three roles commonly go together:

1. **AnnotationJmxAttributeSource:** reads JMX annotations on the managed resource.
2. **MetadataNamingStrategy:** determines the ObjectName according to metadata.
3. **MetadataMBeanInfoAssembler:** determines attributes, operations, and management info.

\`MBeanExporter\` uses them during export.

Explicit configuration example:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler mbeanInfoAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy namingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming =
                new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter mbeanExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(
                ManagementFactory.getPlatformMBeanServer()
        );
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectMode(
                MBeanExporter.AUTODETECT_ASSEMBLER
        );
        return exporter;
    }

    @Bean
    ProductCacheMonitor productCacheMonitor() {
        return new ProductCacheMonitor();
    }
}
\`\`\`

This configuration illustrates the path from annotation to ObjectName when not using \`@EnableMBeanExport\`. In a real application, choose only one suitable exporter configuration mechanism to avoid accidentally registering the same managed resource multiple times.

### How Do NamingStrategy and Assembler Differ?

- NamingStrategy decides only **the MBean's name**.
- Assembler decides only **the published JMX metadata**.
- Exporter is responsible for **registering and cleaning up registrations**.

If the annotation is right but the MBean does not appear, the bug may be in the exporter/autodetection; if the MBean appears under a different name, check NamingStrategy; if the MBean has the right name but lacks attributes/operations, check the assembler.

## 5. ObjectName Syntax and Important Rules

A JMX ObjectName has the general form:

\`\`\`text
domain:key1=value1,key2=value2
\`\`\`

Examples:

\`\`\`text
learning.jmx:type=Queue,name=Primary
learning.jmx:type=Cache,name=Products
learning.jmx:type=Scheduler,name=Nightly
\`\`\`

Some principles:

- Domain comes before the colon, key properties come after.
- Key properties are comma-separated \`key=value\` pairs.
- An ObjectName must follow Java JMX syntax; special characters may require quoting.
- Key properties can be reordered in the string while still representing the same ObjectName when the corresponding keys/values match.
- No two MBeans may share the same ObjectName in one \`MBeanServer\` at the same time.
- The keys \`type\` and \`name\` are useful conventions, not mandatory keys for every ObjectName.

Example of two strings:

\`\`\`text
learning.jmx:type=Cache,name=Products
learning.jmx:name=Products,type=Cache
\`\`\`

They represent the same set of key properties and the same ObjectName under JMX semantics. Do not use raw string comparison when you can construct \`ObjectName\`s and compare via the API.

### Quoting Needed When Values Have Special Characters

A value such as a cache name containing a comma may be invalid if placed directly into the string:

\`\`\`java
String cacheName = "Products,Featured";
\`\`\`

When constructing an ObjectName in code, use the quoting helper API:

\`\`\`java
ObjectName objectName = new ObjectName(
    "learning.jmx:type=Cache,name="
        + ObjectName.quote(cacheName)
);
\`\`\`

With \`@ManagedResource(objectName = "...")\`, the annotation value is a compile-time constant; use a verified valid ObjectName. Do not concatenate runtime values into annotations.

### Can an ObjectName Contain Wildcards?

JMX supports ObjectName patterns for **querying**, for example:

\`\`\`java
ObjectName pattern = new ObjectName(
    "learning.jmx:type=Cache,*"
);

Set<ObjectName> names =
        server.queryNames(pattern, null);
\`\`\`

However, **registration** requires a concrete ObjectName, not a pattern to register multiple MBeans. Do not use \`*\` expecting \`@ManagedResource\` to auto-register multiple instances.

## 6. Stable Naming During Code Refactoring

Suppose the Java class changes from \`ProductCacheMonitor\` to \`ProductCacheManagementFacade\`, and the Spring bean name changes from \`cacheManagerForProducts\` to \`productsCacheAdmin\`.

If the annotation keeps:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=Products"
)
\`\`\`

JMX clients continue querying the same ObjectName. This is an important benefit of explicit identification at the management layer: the operational contract stays stable while the implementation is refactored.

**Do not change the ObjectName just because the Java class name changed.** If the team needs to change a management name, treat it as a contract change and plan a migration for dependent scripts, monitoring rules, and runbooks.

### An MBean Facade Reduces Coupling

Instead of annotating a frequently changing business service directly, you can create a facade:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=Products"
)
public class ProductCacheManagement {

    private final ProductCacheService service;

    public ProductCacheManagement(ProductCacheService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getEntryCount() {
        return service.estimatedEntryCount();
    }

    @ManagedOperation
    public void clear() {
        service.clear();
    }
}
\`\`\`

The facade keeps the JMX contract stable while \`ProductCacheService\` evolves for business needs. Separating this boundary also prevents accidentally publishing unnecessary internal methods.

## 7. Setting ObjectNames with Multiple Instances

If you have two queue monitors:

\`\`\`text
Primary queue
Secondary queue
\`\`\`

You cannot register both into the same \`MBeanServer\` under one ObjectName. Use key properties to distinguish them:

\`\`\`text
learning.jmx:type=QueueMonitor,name=Primary
learning.jmx:type=QueueMonitor,name=Secondary
\`\`\`

Then each instance's ObjectName is clear and stable.

### When an Annotated Class Is Used Multiple Times

Suppose \`QueueMonitor\` has:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueMonitor,name=Primary"
)
public class QueueMonitor {
    // ...
}
\`\`\`

And Spring creates two beans of the same class. If both are autodetected by the exporter with the same ObjectName taken from the annotation, a name collision can occur.

Solutions:

1. Export only one representative bean when that satisfies management needs.
2. Use a separate facade class for each resource with an appropriate ObjectName.
3. Use explicit bean mappings on \`MBeanExporter\` or a custom \`ObjectNamingStrategy\` when naming must depend on bean identity/runtime instance.
4. Design namespaced ObjectNames for genuinely independent instances.

This is a limitation to remember: an annotation on a **class** carries a fixed ObjectName value; it does not automatically turn into different names just because Spring creates two instances.

### When Deploying Across Multiple JVMs/Pods

Each JVM can have its own \`MBeanServer\`, so the same ObjectName can appear across multiple pods without conflict. This lets JMX tooling use the same logical name on every instance.

If a centralized system collects JMX from multiple JVMs, keep both **instance identity** and ObjectName. Do not treat ObjectName as a unique ID across the whole cluster.

## 8. RegistrationPolicy: Handling Duplicate ObjectNames

\`MBeanExporter\` supports \`RegistrationPolicy\` to decide behavior when an ObjectName already exists.

| Policy | Effect | When to Consider |
|---|---|---|
| \`FAIL_ON_EXISTING\` | Throws an error if the name is already registered | Wanting to detect duplicate configurations and wrong ownership |
| \`IGNORE_EXISTING\` | Skips the new registration when the name already exists | Intentionally keeping the old MBean without replacing it |
| \`REPLACE_EXISTING\` | Replaces the already-registered MBean | Only when ownership of the name is certain and impact is controlled |

For lessons on naming, start with \`FAIL_ON_EXISTING\` to catch errors early.

\`\`\`java
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

**Do not use \`REPLACE_EXISTING\` to hide all collision errors**; a new context may overwrite an MBean belonging to a running context, causing JMX clients to see a different object under the old name.

When an MBean has already been registered by another exporter or manual code, setting \`IGNORE_EXISTING\` does not mean the new bean was successfully exported either.

## 9. Verifying ObjectNames from MBeanServer

The simplest way is checking registration on **the right \`MBeanServer\`**:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "learning.jmx:type=CacheMonitor,name=Products"
);

System.out.println(
    "Registered: " + server.isRegistered(expected)
);
\`\`\`

If unsure of the registered name, search by domain:

\`\`\`java
Set<ObjectName> names = server.queryNames(
    new ObjectName("learning.jmx:*"),
    null
);

names.forEach(System.out::println);
\`\`\`

Once results are returned, inspect the actual ObjectName and attributes/operations:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(expected);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("Attribute: " + attribute.getName());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
\`\`\`

Required imports:

\`\`\`java
import java.util.Set;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
\`\`\`

**Practical warning:** \`ManagementFactory.getPlatformMBeanServer()\` gets the server of the current JVM. If checking code runs from a separate Java process, it will not automatically see the target application's MBeans. To inspect remotely, use \`MBeanServerConnection\` over an appropriate connector.

## 10. Testing the JMX Naming Contract

MBean names can be referenced in scripts and monitoring systems. Therefore, you can write an integration test verifying the ObjectName after the Spring context starts.

JUnit 5 example:

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ObjectNameContractTest {

    @Test
    void managedResourceUsesExpectedObjectName()
            throws Exception {

        ObjectName expected = new ObjectName(
            "learning.jmx:type=CacheMonitor,name=Products"
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxConfiguration.class)) {

            MBeanServer server =
                    ManagementFactory.getPlatformMBeanServer();

            assertTrue(server.isRegistered(expected));

            assertEquals(
                20,
                server.getAttribute(expected, "EntryCount")
            );
        }
    }
}
\`\`\`

This test is meaningful when \`JmxConfiguration\` actually exports to the platform \`MBeanServer\`. For better isolation, create a dedicated \`MBeanServer\` for the test and configure the exporter to point to that server.

### What Should Be Tested?

A naming contract test should verify:

- The managed resource is registered after context startup.
- The ObjectName equals the expected name.
- No unexpected extra names exist when using a custom naming strategy.
- Important attributes/operations are published correctly.
- After context close, the exporter unregisters the MBeans it manages.
- Tests running in parallel do not share the same ObjectName in one \`MBeanServer\` if conflicts are possible.

There is no need to write unit tests purely for annotation string values. Testing at the JMX boundary is more valuable because it catches configuration, exporter, metadata, and registry bugs.

## 11. ObjectName When Using Explicit Exporter Mapping

An alternative to annotation metadata is specifying names in \`MBeanExporter\`'s map:

\`\`\`java
exporter.setBeans(Map.of(
    "learning.jmx:type=CacheMonitor,name=Products",
    productCacheMonitor
));
\`\`\`

In this case, the name may come from the explicit mapping rather than a naming strategy reading \`@ManagedResource.objectName\`.

Do not conclude that every MBean with \`@ManagedResource\` is guaranteed to be registered with the annotation's name if the exporter configuration overrides it via another naming source/registration path.

**Principle:** Determine the final name by querying the actual \`MBeanServer\`, not just by reading source code annotations.

If you want a single naming source and use annotation-driven export, letting the naming strategy read from \`@ManagedResource.objectName\` is easy to follow. If per-instance or per-environment names are needed, explicit mapping or a custom strategy may fit better.

## 12. Real-World Naming Scenarios

### Scenario A — Renaming a Class While Keeping JMX Clients

Class \`ProductCacheMonitor\` is renamed to \`ProductCacheManagement\`. The ObjectName in the annotation stays:

\`\`\`text
learning.jmx:type=CacheMonitor,name=Products
\`\`\`

Expected outcome: JMX clients continue querying the same name after the exporter starts successfully. Of course, attributes/operations must also preserve the contract for full compatibility.

### Scenario B — Two Beans of the Same Class

Two \`QueueMonitor\` instances are auto-detected, yet the class has only one \`objectName\` annotation. Using the same name causes a collision. Per-instance explicit naming or exporting a representative facade is required.

### Scenario C — Invalid ObjectName Syntax

A developer puts:

\`\`\`text
learning.jmx:type=Cache,name=Products,Featured
\`\`\`

The comma in the value can cause the parser to misinterpret it as a key property. When setting names containing special characters, quote/escape properly per ObjectName syntax.

### Scenario D — Multiple Contexts in the Same JVM

Parent and child contexts both have exporters registering the same logical MBean. Giving each context its own bean name does not resolve duplicate ObjectNames in the same server. Only one context should own the registration, or the ObjectNames must reflect two different resources.

### Scenario E — Monitoring Across Multiple Pods

Each pod has the same ObjectName \`learning.jmx:type=CacheMonitor,name=Products\`. No conflict occurs if each pod has its own \`MBeanServer\`. The collector needs to add pod/JVM identity when aggregating.

## 13. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| MBean not seen under expected ObjectName | Exporter not running, different naming strategy, wrong JVM/server | Use \`queryNames\` on the right \`MBeanServer\` |
| \`MalformedObjectNameException\` | Invalid domain or key properties | Check syntax and quoting |
| \`InstanceAlreadyExistsException\` | Two MBeans share the same ObjectName | Identify owner, context, and registration policy |
| Bean has \`@ManagedResource\` but is not exported | Exporter/autodetection not enabled or bean outside context | Check \`@EnableMBeanExport\`/\`MBeanExporter\` and Spring bean |
| Renaming Java class makes tool lose MBean | Naming strategy generates name from class instead of fixed name | Use a stable ObjectName or intentional migration |
| Two instances of same class contend for same name | Fixed class-level annotation | Choose explicit mapping/custom naming |
| MBean has right name but misses attributes | Metadata assembler does not publish getter/operation | Check \`@ManagedAttribute\`, \`@ManagedOperation\`, \`MBeanInfo\` |
| JConsole sees name in another JVM | Connected to wrong process | Check PID, instance identity, and connector |
| Context closed yet ObjectName persists | Another exporter or manual code owns registration | Trace where register/unregister happens |
| Monitoring tools break after rename | ObjectName is part of the contract | Keep old name or migrate consumers on a plan |

## 14. Checklist When Designing @ManagedResource.objectName

Before exporting a new bean, ask:

1. **Domain:** Is it consistent with the application/module?
2. **Type:** Does it describe the type of management resource?
3. **Key properties:** Do they distinguish instances of the same type within one \`MBeanServer\`?
4. **Stability:** Does the name remain stable across code refactors?
5. **Ownership:** Which context or exporter is responsible for registering and unregistering?
6. **Collision:** Could two beans, contexts, or modules use the same name?
7. **Environment:** Do JVMs/pods have separate servers or share a registry?
8. **Security:** Does the ObjectName avoid putting secrets/sensitive information into metadata?
9. **Discoverability:** Can management tools easily query by domain/type?
10. **Compatibility:** Which scripts, dashboards, or runbooks depend on this name?

If names need to vary with runtime data, a fixed class-level annotation may be unsuitable. In that case, use explicit registration or a clearly designed \`ObjectNamingStrategy\`.

## 15. Practice Exercises

### Exercise 1 — Differences Among Three Types of Names

Given:

\`\`\`java
@Bean(name = "inventoryCacheAdmin")
ProductCacheMonitor productCacheMonitor() {
    return new ProductCacheMonitor();
}
\`\`\`

and:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Cache,name=Inventory"
)
public class ProductCacheMonitor {
    // ...
}
\`\`\`

Identify the bean name, Java class name, and JMX ObjectName. Explain why the three names do not have to match.

### Exercise 2 — Verifying with MBeanServer

Start a context containing \`ProductCacheMonitor\`. Use \`isRegistered\`, \`queryNames\`, and \`getMBeanInfo\` to find the exact ObjectName, the \`EntryCount\` attribute, and the \`clear\` operation.

### Exercise 3 — Handling Collisions

Create two Spring beans of the same class with the same \`@ManagedResource.objectName\`. Observe the error or registration policy behavior. Redesign the names so both instances can coexist without overwriting each other.

### Exercise 4 — Valid ObjectNames

Evaluate:

\`\`\`text
learning.jmx:type=Cache,name=Products
learning.jmx:type=Cache,name=Products,Featured
learning.jmx:type=Cache,name="Products,Featured"
\`\`\`

The second name has an unquoted comma in the value, making it prone to syntax errors. The third illustrates how to quote a value containing a delimiter; verify with \`new ObjectName(...)\` when applying.

### Exercise 5 — Refactoring Without Breaking Clients

A developer renames the class \`QueueMonitor\` to \`QueueRuntimeInspector\`. Keep the \`ObjectName\` unchanged, verify \`isRegistered\` with the old name is still true, and then check that operations/attributes preserve the contract.

## 16. Core Takeaways

- \`@ManagedResource(objectName = "...")\` is a way to declare the **JMX identity** for a Spring-managed bean.
- The annotation does not open a JMX server or register a bean without an exporter.
- \`MetadataNamingStrategy\` can read \`objectName\` from the annotation and supply the name to \`MBeanExporter\`.
- Spring bean name, Java class name, and JMX ObjectName are three independent concepts.
- ObjectNames must be valid and unique within each \`MBeanServer\`.
- Fixed naming keeps the JMX contract stable during refactoring, while multiple instances of the same class may need a different naming strategy.
- Verify actual registration with \`MBeanServer.isRegistered\`, \`queryNames\`, and \`getMBeanInfo\`.
- When changing an ObjectName, treat it as a management API contract change; migrate clients and tooling according to a plan.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework API — MetadataNamingStrategy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/MetadataNamingStrategy.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — ObjectName: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
