# MetadataNamingStrategy Reads Names from Source Metadata

## 1. Context and Objectives

In Spring Framework JMX, exposing a Spring bean to a management system requires answering two separate questions:

- **How is the bean named in JMX?** The result must be a valid \`javax.management.ObjectName\`, unique within the \`MBeanServer\` in use.
- **Which attributes and operations does the bean expose?** This is the job of the management interface construction mechanism, typically via \`MBeanInfoAssembler\`.

\`org.springframework.jmx.export.naming.MetadataNamingStrategy\` solves the first question. It is an \`ObjectNamingStrategy\` that obtains MBean identification information from a **metadata source** (\`JmxAttributeSource\`), usually \`AnnotationJmxAttributeSource\` reading the \`@ManagedResource\` annotation on the class.

This lesson guides you through how this naming strategy works, how to configure it, and how to verify it, while clarifying boundaries with \`MBeanExporter\`, \`MetadataMBeanInfoAssembler\`, and Spring bean names.

After this lesson, you will be able to:

1. Explain the roles of \`ObjectNamingStrategy\` and \`MetadataNamingStrategy\`.
2. Distinguish Spring bean names, Java class names, and JMX \`ObjectName\`s.
3. Declare \`@ManagedResource(objectName=...)\` and configure the corresponding annotation source.
4. Understand what the metadata naming strategy reads from metadata and limitations when metadata is missing or invalid.
5. Use the \`ObjectName\` API to inspect names, wildcards, and equivalence.
6. Diagnose MBean registration failures caused by naming strategies or duplicate ObjectNames.
7. Choose between metadata-based naming and other naming approaches when dynamic instances exist.

## 2. Overview Model

\`\`\`text
Spring bean: ProductCacheMonitor
          |
          | @ManagedResource(
          |   objectName="com.example.monitoring:type=Cache,name=Products"
          | )
          v
AnnotationJmxAttributeSource
          |
          | resource metadata
          v
MetadataNamingStrategy
          |
          | getObjectName(bean, beanKey)
          v
javax.management.ObjectName
          |
          v
      MBeanExporter
          |
          | registerMBean
          v
       MBeanServer
          |
          v
    JConsole / JMX client
\`\`\`

A parallel flow:

\`\`\`text
@ManagedAttribute / @ManagedOperation
          |
          v
AnnotationJmxAttributeSource
          |
          v
MetadataMBeanInfoAssembler
          |
          v
     Management interface
\`\`\`

Both branches use the same metadata source but do different work. The naming strategy determines **what the object is called**; the assembler determines **what the object allows clients to see and invoke**.

## 3. What Is an ObjectName and Why Is a Naming Strategy Needed?

A JMX \`ObjectName\` typically has the syntax:

\`\`\`text
domain:key1=value1,key2=value2
\`\`\`

Examples:

\`\`\`text
com.example.monitoring:type=Cache,name=Products
com.example.monitoring:type=Worker,name=Import
java.lang:type=Memory
\`\`\`

An ObjectName has:

- **Domain:** an identifier group, such as \`com.example.monitoring\`.
- **Key properties:** e.g., \`type=Cache\`, \`name=Products\`.
- **Canonical representation:** a standardized ordering of key properties when comparing/logging.
- **Pattern semantics:** wildcards \`*\`, \`?\` can be used for queries but are unsuitable when registering a concrete MBean.

For example, the following two names represent the same ObjectName:

\`\`\`java
ObjectName first = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

ObjectName second = new ObjectName(
    "com.example.monitoring:name=Products,type=Cache"
);

System.out.println(first.equals(second)); // true
\`\`\`

Use \`ObjectName.equals()\` or \`getCanonicalName()\` when comparing. Do not rely on key order in the input string.

### Spring Bean Name vs. ObjectName

A class:

\`\`\`java
@Component("productCacheMonitor")
public class ProductCacheMonitor {
}
\`\`\`

has the Spring bean name \`productCacheMonitor\`. That name identifies the bean inside \`ApplicationContext\`.

In contrast:

\`\`\`text
com.example.monitoring:type=Cache,name=Products
\`\`\`

is the JMX ObjectName used in \`MBeanServer\`. \`MetadataNamingStrategy\` helps determine the JMX name based on management metadata, rather than simply taking the bean name and using it directly as the ObjectName.

## 4. What Contract Is ObjectNamingStrategy?

Spring defines \`ObjectNamingStrategy\` so exporters can swap MBean name-resolution rules without changing registration logic.

Concept:

\`\`\`java
ObjectName getObjectName(Object managedBean, String beanKey)
        throws MalformedObjectNameException;
\`\`\`

- \`managedBean\`: the object being exported.
- \`beanKey\`: the key or name corresponding to the export configuration.
- Result: a valid \`ObjectName\`.

Depending on the implementation, a naming strategy can use the class, bean key, metadata, or a custom convention.

Some implementations in Spring:

| Strategy | Primary Name Source | When Useful |
|---|---|---|
| \`MetadataNamingStrategy\` | Management metadata from \`JmxAttributeSource\` | Beans using \`@ManagedResource(objectName=...)\` |
| \`KeyNamingStrategy\` | Mapping key or configured mappings | Explicit naming from exporter configuration is needed |
| \`IdentityNamingStrategy\` | Object identity/type per strategy policy | When names should be tied to instance identity |
| Custom \`ObjectNamingStrategy\` | Application-defined rules | Dynamic names, multi-instance, custom conventions |

\`MetadataNamingStrategy\` fits when the ObjectName is part of the **management contract declared directly on the class**.

## 5. Metadata Source: JmxAttributeSource

\`JmxAttributeSource\` is Spring JMX's abstraction for looking up management metadata of a class/method.

For annotation-driven JMX, the source is typically:

\`\`\`java
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;

AnnotationJmxAttributeSource source =
    new AnnotationJmxAttributeSource();
\`\`\`

It reads annotations such as:

- \`@ManagedResource\` at the class level.
- \`@ManagedAttribute\` on getters/setters.
- \`@ManagedOperation\` on methods.
- \`@ManagedOperationParameter\` for parameter descriptions.
- \`@ManagedNotification\` for notification metadata.

**For naming**, the important data is primarily class-level resource metadata, especially \`@ManagedResource.objectName\`.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache management"
)
public class ProductCacheMonitor {
}
\`\`\`

The source recognizes resource metadata, the naming strategy extracts the appropriate JMX name information, and then the exporter registers the bean.

\`description\` describes the MBean for clients; it is not part of the ObjectName. Likewise, \`currencyTimeLimit\` or other descriptor attributes of \`@ManagedResource\` do not replace the \`objectName\` value.

## 6. Complete Example with Plain Spring Framework

### 6.1. Managed Bean

\`\`\`java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache administration"
)
public class ProductCacheMonitor {

    private final AtomicInteger entryCount = new AtomicInteger();

    @ManagedAttribute(description = "Current cached entries")
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedOperation(description = "Reset cached entry count")
    public void resetStatistics() {
        entryCount.set(0);
    }
}
\`\`\`

### 6.2. Configuring MetadataNamingStrategy

\`\`\`java
package com.example.monitoring;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfiguration {

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {

        MetadataNamingStrategy strategy =
            new MetadataNamingStrategy();
        strategy.setAttributeSource(source);
        return strategy;
    }

    @Bean
    public MBeanExporter mBeanExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_ASSEMBLER
        );
        return exporter;
    }
}
\`\`\`

Explanation:

1. \`ProductCacheMonitor\` is registered by Spring because of \`@Component\` and component scanning.
2. \`AnnotationJmxAttributeSource\` reads management metadata.
3. \`MetadataNamingStrategy\` gets the name from \`@ManagedResource\`.
4. \`MetadataMBeanInfoAssembler\` builds management attributes and operations.
5. \`MBeanExporter\` receives both components and registers the bean into \`MBeanServer\`.
6. Clients will find the MBean under \`com.example.monitoring:type=Cache,name=Products\` if export succeeds and they connect to the right server.

A real configuration needs component scanning or a corresponding \`@Bean\` to create \`ProductCacheMonitor\`. The example shows only the JMX configuration, omitting application bootstrap.

### 6.3. Concise Annotation-Driven Approach

If custom assembler/naming strategy configuration is not needed, Spring Framework provides:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class SimpleJmxConfiguration {
}
\`\`\`

Spring automatically sets up the appropriate annotation export support components. This is an **alternative** to the manual exporter configuration above.

In Spring Boot, check JMX auto-configuration and \`spring.jmx.enabled\` for the version in use before creating an additional exporter. Two exporters exporting the same ObjectName can conflict.

## 7. What Does MetadataNamingStrategy Actually Do?

When the exporter requests a name for a bean, the strategy reads resource metadata via the configured source and resolves the \`ObjectName\`.

With metadata:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products"
)
\`\`\`

the expected result is:

\`\`\`text
com.example.monitoring:type=Cache,name=Products
\`\`\`

Important facts:

- The strategy **does not select beans** to export by itself.
- The strategy **does not register the MBean** into the server.
- The strategy **does not create JMX attributes/operations**.
- The strategy **does not open a JMX remote port** by itself.
- The strategy **does not turn annotations into runtime data** unless the exporter and metadata source are wired together.

It supplies an \`ObjectName\` for \`MBeanExporter\` to use.

### When Metadata Lacks an ObjectName

Do not assume the strategy can always find a useful name for every class. If resource metadata is missing or \`objectName\` is not specified, exact behavior depends on the implementation and exporter/naming configuration. Check the actual error and the contract of the Spring version in use.

In architectures requiring stable names, the safe approach is declaring \`objectName\` explicitly or providing an application-designed fallback naming strategy, rather than relying on guesses about auto-generated names.

## 8. MetadataNamingStrategy vs. MetadataMBeanInfoAssembler

An easily confused pair is:

\`\`\`text
MetadataNamingStrategy
MetadataMBeanInfoAssembler
\`\`\`

Both can receive the same \`AnnotationJmxAttributeSource\`, yet have different responsibilities:

| Criterion | MetadataNamingStrategy | MetadataMBeanInfoAssembler |
|---|---|---|
| Question | What is the MBean named? | What management interface does the MBean have? |
| Output | \`ObjectName\` | \`ModelMBeanInfo\`/management metadata |
| Primary source | Class-level resource metadata | Resource, attribute, operation, notification metadata |
| Example annotations | \`@ManagedResource.objectName\` | \`@ManagedAttribute\`, \`@ManagedOperation\`, description |
| Used by | \`MBeanExporter\` | \`MBeanExporter\` |
| Direct impact | Identity in \`MBeanServer\` | Content clients can view/invoke |

A bean can receive the right ObjectName yet miss attributes because the assembler did not read annotations. Conversely, the assembler may find all operations yet the exporter fails registration due to a duplicate ObjectName.

Therefore, when debugging JMX, separate **naming** errors from **interface assembly** errors.

## 9. Inspecting ObjectName with the Java API

After declaring annotations or building names from metadata, you can verify:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

System.out.println(name.getDomain());
System.out.println(name.getKeyProperty("type"));
System.out.println(name.getKeyProperty("name"));
System.out.println(name.getCanonicalName());
System.out.println(name.isPattern()); // false
\`\`\`

Key APIs:

| API | Meaning |
|---|---|
| \`new ObjectName(text)\` | Parse and validate name syntax |
| \`getDomain()\` | Retrieve the domain |
| \`getKeyProperty(key)\` | Retrieve the value of the specified key |
| \`getKeyPropertyList()\` | Retrieve parsed key/value pairs |
| \`getCanonicalName()\` | Canonical form for comparison |
| \`equals(other)\` | Compare ObjectName identity |
| \`isPattern()\` | Check for wildcard/pattern |
| \`ObjectName.quote(value)\` | Escape dynamic property values |

The goal of \`MetadataNamingStrategy\` is to produce a name usable for **registering a concrete MBean**. Therefore, ObjectName configurations should not contain unintended wildcards.

For example:

\`\`\`java
ObjectName pattern =
    new ObjectName("com.example.monitoring:type=Cache,*");

System.out.println(pattern.isPattern()); // true
\`\`\`

That name is suitable for \`MBeanServer.queryNames()\`, not for registering a concrete MBean.

## 10. Dynamic Names: Limitations of Fixed Annotations

\`@ManagedResource(objectName=...)\` is an annotation attribute and must use a valid value under Java's compile-time constant rules.

For example:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import"
)
\`\`\`

This fits when an instance has a fixed name. But if an application has multiple workers of the same class:

\`\`\`text
Worker name = ImportEast
Worker name = ImportWest
\`\`\`

then **you cannot use the same fixed ObjectName** for both instances on the same \`MBeanServer\`.

Do not try to concatenate runtime variables directly into the annotation:

\`\`\`java
// Cannot use a runtime variable as an annotation value:
// @ManagedResource(objectName = DOMAIN + ":type=Worker,name=" + workerName)
\`\`\`

For multiple dynamic instances, typical solutions are:

- Build the ObjectName from runtime data using the \`ObjectName\` API.
- Choose an appropriate custom naming strategy.
- Or create programmatic export mappings per instance.
- Ensure each instance has a distinguishing key property (\`name\`, \`instance\`, ...).

Example of building a safe name:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

String workerName = "Import,Region=East";

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Worker");
properties.put("name", ObjectName.quote(workerName));

ObjectName objectName =
    new ObjectName("com.example.monitoring", properties);
\`\`\`

\`ObjectName.quote(workerName)\` keeps delimiters inside the worker name as data rather than new keys. If the domain/keys also come from external data, validate them separately.

Distinguish between using \`MetadataNamingStrategy\` for statically declared names and using another strategy for per-instance dynamic naming. Not every naming problem has to rely on annotations.

## 11. MBeanServer and ObjectName Collisions

\`MBeanServer\` can hold only one registration for a specific ObjectName at a time.

Example of two beans:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products"
)
class ProductCacheMonitorA { }

@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products"
)
class ProductCacheMonitorB { }
\`\`\`

If both are selected by the exporter on the same \`MBeanServer\`, a registration conflict can occur.

Handling options:

1. Assign distinct ObjectNames per scope/instance.
2. Restrict which beans are exported.
3. Review an appropriate \`RegistrationPolicy\` if there is a clear business reason.
4. Avoid configuring multiple exporters overlapping the same set of MBeans.
5. Standardize naming conventions across the application.

Spring supports registration policies such as \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\`, and \`REPLACE_EXISTING\`. Do not pick \`REPLACE_EXISTING\` just to mask errors; it can replace an MBean registered by another component.

### Note on Multiple Spring ApplicationContexts

Within the same JVM there can be multiple application contexts (parent/child or multiple modules). Each context may declare an exporter yet register into the same \`MBeanServer\`. Hence an ObjectName that is unique within one Spring context is not necessarily unique across the entire \`MBeanServer\`.

Naming conventions must account for module, application, or instance when multiple applications share a server.

## 12. Verifying Names on MBeanServer

After starting the application context with the JMX exporter, check:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

System.out.println(server.isRegistered(name));
\`\`\`

If \`true\`, that name is registered on the specified server at the time of the call.

You can read \`MBeanInfo\`:

\`\`\`java
var info = server.getMBeanInfo(name);

System.out.println(info.getDescription());

for (var attr : info.getAttributes()) {
    System.out.println(
        attr.getName() + ": " + attr.getType()
    );
}
\`\`\`

To look up all names in a domain:

\`\`\`java
ObjectName query = new ObjectName(
    "com.example.monitoring:*"
);

for (ObjectName registered : server.queryNames(query, null)) {
    System.out.println(registered.getCanonicalName());
}
\`\`\`

**Important:** \`ManagementFactory.getPlatformMBeanServer()\` returns the platform \`MBeanServer\` **of the JVM running that code**. If the exporter uses a different \`MBeanServer\` or the client is in another JVM, inspect the right server through the corresponding reference/connection.

## 13. Debugging MetadataNamingStrategy Issues

### 13.1. \`@ManagedResource\` Present, but MBean Not Visible

Possibilities:

- Spring bean was not created or component scan does not cover the class.
- JMX export is not enabled.
- Autodetect did not select the bean.
- Metadata source is not wired into the naming strategy.
- ObjectName is invalid, duplicated, or registered on a different server.
- Client is connecting to the wrong JVM.

Check along the chain: does the Spring bean exist → is the exporter active → does the source read metadata → what name does the naming strategy return → did registration succeed → which server is the client viewing.

### 13.2. Bean Appears in MBeanServer with Unexpected Name

Possibilities:

- Exporter is using a different naming strategy.
- An explicit mapping takes precedence due to exporter configuration.
- Multiple exporters or auto-configuration mechanisms exist.
- Annotation is not read due to target class/proxy.
- Fallback naming or implementation naming convention is used.

Inspect the actual configuration and the \`queryNames()\` list, rather than looking only at annotations in source code.

### 13.3. Invalid ObjectName

If the name contains syntactically invalid special characters or wildcards used out of context, the JMX parser/registration can report an error.

\`\`\`java
new ObjectName("com.example:type=Worker,name=Import,East");
\`\`\`

This is an example of a malformed key property list because \`East\` is not a valid \`key=value\` pair. If \`Import,East\` is a user-facing name, quote the value when building dynamic names.

### 13.4. Name Collision After Adding a New Bean

Do not change only \`description\` or the class name. Two MBeans can still have the same ObjectName. Check **the domain and the entire set of key properties**.

### 13.5. Annotation Present, but Proxy Causes Differences

Spring AOP can turn a runtime bean into a JDK proxy or CGLIB proxy. Metadata placed on the target implementation sometimes requires proper target-class/proxy detection. If errors occur, use an integration test to check the registered name; you can also separate a dedicated management facade bean for JMX.

### 13.6. MBean Registered, but JConsole Does Not Show It

The client may be connecting to the wrong process or the remote connector may not be enabled. \`MetadataNamingStrategy\` does not open remote JMX or configure network permissions.

## 14. Testing a Naming Strategy

A small test can verify the expected ObjectName from class metadata:

\`\`\`java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

class MetadataNamingStrategyTest {

    @Test
    void readsObjectNameFromManagedResource() throws Exception {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        ProductCacheMonitor bean = new ProductCacheMonitor();

        ObjectName actual = naming.getObjectName(
            bean, "productCacheMonitor"
        );

        ObjectName expected = new ObjectName(
            "com.example.monitoring:type=Cache,name=Products"
        );

        assertEquals(expected, actual);
        assertFalse(actual.isPattern());
    }
}
\`\`\`

This test confirms that the naming strategy reads the annotation under the created configuration. It does **not** prove the MBean has been exported because neither \`MBeanExporter\` nor \`MBeanServer\` participates.

To verify the full pipeline, use an integration test with a Spring context and \`MBeanServer\`, then check \`server.isRegistered(expected)\`.

### Useful Test Cases

| Case | Expectation |
|---|---|
| Class with valid \`@ManagedResource.objectName\` | Strategy returns the expected ObjectName |
| Key properties in reversed order | \`ObjectName.equals()\` still evaluates as equivalent |
| Two beans with the same ObjectName | Exporter/server reports conflict per registration policy |
| ObjectName is a pattern | Not accepted as a concrete registration name |
| No suitable source metadata | Must handle per strategy contract/error and configuration |
| Bean is an AOP proxy | Verify source reads the annotation and name properly |
| Dynamic name containing comma | Quote property value via the Java ObjectName API |

Do not rely solely on \`toString()\` to compare identities or write custom regexes simulating the entire JMX grammar.

## 15. When to Choose MetadataNamingStrategy?

Choose it when:

- MBeans have stable identities that can be declared directly on the class.
- The project already uses Spring JMX annotations to describe the management contract.
- You want a unified metadata source for both MBean names and interface metadata.
- The number of MBean types is moderate and naming conventions are directly maintainable.
- Simple annotation-driven configuration is desired.

Consider other approaches when:

- There are very many instances of the same class where each instance needs a different ObjectName.
- Names depend on tenant, node, dynamic configuration, or runtime lifecycle.
- A library is embedded across multiple contexts with different domain naming.
- Backward compatibility with legacy ObjectNames outside the class is needed.
- Name mappings must be centrally managed by infrastructure.

In those cases, you can choose \`KeyNamingStrategy\`, a custom \`ObjectNamingStrategy\`, or explicit mappings at the exporter. The choice depends on **which identity data source is the source of truth**.

## 16. Security and JMX Name Design

An ObjectName is not a credential or proof that the caller is authorized. Even with a valid name, restrict who can:

- Connect to remote JMX.
- Browse and read MBeans.
- Invoke operations.
- Modify writable attributes.
- Access sensitive diagnostic data.

Practical rules:

- Use stable domains per application/module.
- Choose meaningful \`type\`, \`name\`, and \`instance\`.
- Avoid personal data, passwords, and tokens in ObjectNames.
- Do not pass untrusted strings directly into domains/keys/values.
- Do not create an uncontrolled number of MBeans per user/session.
- Have a collision-avoidance strategy for multi-instance and multi-context setups.
- Check whether changing an ObjectName impacts existing monitoring scripts or JMX clients.

If an MBean changes its name, clients querying the old ObjectName may no longer find the object. Thus JMX identity is part of an operational contract requiring change management.

## 17. Practice Exercises

### Exercise A — Basic Metadata Naming

1. Create a \`QueueMonitor\` Spring bean.
2. Attach \`@ManagedResource(objectName="com.example.training:type=Queue,name=Orders")\`.
3. Create an \`AnnotationJmxAttributeSource\`.
4. Create a \`MetadataNamingStrategy\` and set the source.
5. Call \`getObjectName(bean, "queueMonitor")\`.
6. Check domain, key properties, and \`isPattern()\`.

### Exercise B — Exporter Integration

1. Create a \`MetadataMBeanInfoAssembler\` using the same source.
2. Configure \`MBeanExporter\` with the assembler and naming strategy.
3. Enable appropriate autodetection.
4. Start the Spring context.
5. Check \`MBeanServer.isRegistered(expectedObjectName)\`.
6. Read \`MBeanInfo\` to verify the management interface.

### Exercise C — Handling Name Collisions

1. Create two beans using the same ObjectName metadata.
2. Observe the error or registration policy behavior when exporting to a single \`MBeanServer\`.
3. Assign distinct \`instance\` keys.
4. Re-register and verify both are found via \`queryNames()\`.

### Exercise D — Dynamic Names

1. Suppose there are two workers named \`Import,East\` and \`Import,West\`.
2. Build ObjectNames using the constructor and \`ObjectName.quote()\`.
3. Compare with unescaped string concatenation.
4. Explain why dynamic names should be managed via a factory/naming strategy instead of a shared fixed annotation.

## 18. Self-Check Questions

**Question 1.** What is the responsibility of \`MetadataNamingStrategy\`?  
**Answer:** Determining the ObjectName for a bean from metadata provided by \`JmxAttributeSource\`.

**Question 2.** Which annotation holds the static ObjectName for a resource?  
**Answer:** \`@ManagedResource(objectName="...")\`.

**Question 3.** Does \`MetadataNamingStrategy\` register beans into \`MBeanServer\`?  
**Answer:** No. \`MBeanExporter\` performs registration.

**Question 4.** Which source can \`MetadataMBeanInfoAssembler\` and \`MetadataNamingStrategy\` share?  
**Answer:** \`AnnotationJmxAttributeSource\`.

**Question 5.** What happens if two beans have different Spring bean names but the same ObjectName?  
**Answer:** They can conflict when exported into the same \`MBeanServer\` because JMX uses ObjectName as the identifier.

**Question 6.** Should \`com.example:type=Queue,*\` be used as the registration name for an MBean?  
**Answer:** No, that is an ObjectName pattern for querying.

**Question 7.** With multiple instances of the same class where each instance has a different runtime name, what should you do?  
**Answer:** Use programmatic naming/mapping to produce a distinct ObjectName per instance, handling dynamic values safely.

## 19. Key Takeaways

- \`MetadataNamingStrategy\` is an \`ObjectNamingStrategy\` that reads **MBean names from resource metadata**.
- \`AnnotationJmxAttributeSource\` reads \`@ManagedResource.objectName\` and can be shared with \`MetadataMBeanInfoAssembler\`.
- The naming strategy determines **ObjectName**, the assembler determines the **management interface**, and the exporter performs **registration**.
- A Spring bean name is not synonymous with a JMX ObjectName.
- An ObjectName must be valid, concrete, and unique within the same \`MBeanServer\`.
- Annotations fit stable names; per-instance dynamic names require different naming rules or programmatic mapping.
- Inspect \`ObjectName\` using the JMX API and verify registration on the right \`MBeanServer\`.
- Design JMX names as an operational contract with clear stability and security boundaries.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`MetadataNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/MetadataNamingStrategy.html
- Spring Framework Javadoc — \`ObjectNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/ObjectNamingStrategy.html
- Spring Framework Javadoc — \`AnnotationJmxAttributeSource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
