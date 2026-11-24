# AutodetectCapableMBeanInfoAssembler and the Voting Mechanism in Spring JMX

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain **autodetection** in Spring JMX: the exporter automatically finds eligible Spring beans to register as JMX MBeans instead of only accepting an explicit list.
- Understand the role of the **\`AutodetectCapableMBeanInfoAssembler\`** interface and the **\`includeBean(Class<?> beanClass, String beanName)\`** method as an eligibility evaluation (*vote*) when \`MBeanExporter\` scans beans.
- Distinguish **a bean being selected for export** from **which attributes/operations of the bean are exposed**.
- Identify the relationships among \`MBeanExporter\`, \`MBeanInfoAssembler\`, \`MetadataMBeanInfoAssembler\`, \`AnnotationJmxAttributeSource\`, and standard MBean/MXBean detection mechanisms.
- Configure controlled autodetect and know when to select beans via an explicit list instead of scanning the entire \`ApplicationContext\`.
- Write configuration examples and runtime checks for bean selection, \`ObjectName\`, \`MBeanInfo\`, and the permitted exposed API surface.
- Recognize pitfalls caused by proxies, bean names, management interfaces, scan scope, duplicate registrations, and security boundaries.
- Know how to restrict and diagnose voting so that the JMX exporter does not accidentally expose internal beans.

## 2. What Is Autodetection in Spring JMX?

A Spring application can contain hundreds of beans: services, repositories, listeners, schedulers, HTTP controllers, caches, and management adapters. Registering every bean as an MBean is unnecessary and can create risk. Spring's \`MBeanExporter\` supports several ways to determine which beans will be exported:

1. **Explicitly declaring** the beans to export via a map, list, or appropriate configuration.
2. **Autodetecting** eligible beans according to the exporter's mechanism and/or information from a metadata assembler.
3. **Combining** explicit configuration and exporter-discovered beans according to an appropriate policy.

The core point of autodetection: the exporter needs to decide **which beans are management objects** before building JMX metadata and registering with \`MBeanServer\`.

\`\`\`text
Spring ApplicationContext
  |-- paymentService
  |-- orderRepository
  |-- importWorker
  |-- cacheManagement
  |-- healthController
            |
            v
       MBeanExporter
            |
            | Explicit list?
            | Autodetect mode?
            | Assembler capable of "voting"?
            v
    Candidate selection
       /          \
     YES           NO
      |             |
      v             +--> Do not export this bean
MBeanInfoAssembler
      |
      v
Naming strategy -> ObjectName
      |
      v
MBeanServer.registerMBean(...)
      |
      v
JConsole / JMX client
\`\`\`

“Autodetect” must not be understood as meaning every bean can be accessed by a JMX client. A bean only appears after the exporter selects it, creates the appropriate metadata/contract, and registers it successfully.

## 3. What Is AutodetectCapableMBeanInfoAssembler?

The Spring interface:

\`\`\`java
org.springframework.jmx.export.assembler.AutodetectCapableMBeanInfoAssembler
\`\`\`

extends the idea of \`MBeanInfoAssembler\`: besides building management information for a bean, the assembler can **cast an opinion** on whether a bean should be selected during the autodetection flow.

Key method:

\`\`\`java
boolean includeBean(Class<?> beanClass, String beanName);
\`\`\`

- **\`beanClass\`**: the class type currently being evaluated.
- **\`beanName\`**: the bean name in the Spring container.
- **\`true\`**: the assembler accepts this bean as an autodetectable candidate.
- **\`false\`**: the assembler does not select this bean in the corresponding vote.

Example of a class/name filter:

\`\`\`java
import org.springframework.jmx.export.assembler.AutodetectCapableMBeanInfoAssembler;

boolean eligible = assembler.includeBean(
    CacheManagement.class,
    "cacheManagement"
);
\`\`\`

This only illustrates the method. Calling \`includeBean\` manually does not register the bean; the exporter must run the discovery process and execute \`registerMBean\`.

**Important:** a value of \`true\` represents an *eligibility vote*, not a guarantee that the \`ObjectName\` will register successfully. Other conditions such as name collisions, naming strategy, MBeanServer, or context lifecycle can still cause export to fail or be skipped.

## 4. Why Is It Called a Vote?

In this context, “vote” means the assembler has the ability to decide whether a candidate fits the **management metadata construction strategy** it applies. An annotation-based assembler might select beans carrying a management marker; another assembler might not provide autodetection capability or might have its own rules.

This is not a majority vote across multiple services, not a Java SecurityManager authorization system, and not a scheduler algorithm. Usually only **one assembler configured on MBeanExporter** decides a bean's eligibility along the selected path.

\`\`\`text
Candidate bean
     |
     v
AutodetectCapableMBeanInfoAssembler?
     |
    YES
     |
     v
includeBean(beanClass, beanName)
     |
  +--+---+
  |      |
 true   false
  |      |
  v      v
accept  skip
        candidate
  |
  v
prepare metadata & ObjectName
  |
  v
attempt registration
\`\`\`

In practice, \`MBeanExporter\` also has an autodetection mechanism for beans conforming to Java/JMX standards. Therefore, you should not describe every candidate as going through an assembler vote. Distinguish **autodetecting standard MBeans** from **assembler-based autodetection**.

## 5. Two Detection Mechanism Groups to Distinguish

### 5.1. MBeans Following Existing JMX Rules

A class implementing a \`CacheMonitorMBean\` interface per Standard MBean convention or an MXBean interface can be recognized as a JMX-compliant bean by the exporter's detection logic, depending on the mode. In this case, the MBean's metadata follows the standard management interface contract, independent of the \`@ManagedResource\` annotation.

Example:

\`\`\`java
public interface QueueMonitorMBean {
    long getDepth();
}

public final class QueueMonitor implements QueueMonitorMBean {
    @Override
    public long getDepth() {
        return 12L;
    }
}
\`\`\`

If selected and registered, the MBean exposes \`Depth\`, rather than automatically exposing all public methods of the implementation.

### 5.2. Beans Selected Based on Assembler Metadata

A bean with Spring annotations:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example:type=Queue,name=Orders"
)
public final class QueueManagement {
    @ManagedAttribute
    public long getDepth() {
        return 12L;
    }
}
\`\`\`

If the exporter uses \`MetadataMBeanInfoAssembler\` combined with \`AnnotationJmxAttributeSource\`, the assembler can evaluate annotations to select the bean when the appropriate autodetect mode is enabled. Once selected, it uses that metadata to build the MBean interface.

A class with \`@ManagedResource\` that is outside the exporter's scan scope, or when the exporter does not use an appropriate metadata assembler, may **not** be registered.

## 6. MBeanExporter, Assembler, and Naming Strategy: Three Separate Roles

| Component | Question Answered |
| --- | --- |
| \`MBeanExporter\` | Which beans will be exposed to JMX, and when are they registered and unregistered? |
| \`AutodetectCapableMBeanInfoAssembler\` | Is this bean eligible for the assembler-based autodetect strategy? |
| \`MBeanInfoAssembler\` | Once a bean is selected, which attributes/operations/metadata are exposed? |
| \`JmxAttributeSource\` | What is the source metadata of the bean/method, e.g., Spring annotations? |
| \`ObjectNamingStrategy\` | What will the bean's \`ObjectName\` be? |
| \`MBeanServer\` | Which registry actually receives the MBean and serves JMX clients? |

These steps are related but do not replace one another:

- Voting true does **not** guarantee a valid MBean name.
- A valid MBean name does **not** guarantee successful registration if it is already taken.
- Successful registration does **not** guarantee attributes/operations match intent if the assembler is wrong.
- Proper assembler configuration does **not** replace protecting the remote JMX connector and authorization.

### 6.1. Why Inspect MBeanInfo After Export?

Runtime metadata is what clients see. Once registered:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(objectName);
\`\`\`

Compare the list of attributes/operations against the permitted contract, especially ensuring internal methods are not exposed. This verifies the effect of the configuration, not the effect of a single vote in isolation.

## 7. Autodetect Modes of MBeanExporter

Spring's \`MBeanExporter\` supports mode constants related to autodetection (names can be used via \`setAutodetectMode\` or \`setAutodetectModeName\` depending on the API version):

| Mode | General Meaning |
| --- | --- |
| \`AUTODETECT_NONE\` | Do not run autodetection; use only explicitly configured beans. |
| \`AUTODETECT_MBEAN\` | Detect beans with a JMX-compliant MBean contract via the exporter mechanism. |
| \`AUTODETECT_ASSEMBLER\` | Detect candidates based on the assembler's voting capability. |
| \`AUTODETECT_ALL\` | Combine the supported autodetection groups. |

Example:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_ASSEMBLER
);
\`\`\`

When choosing \`AUTODETECT_ASSEMBLER\`, you must configure an assembler that actually implements \`AutodetectCapableMBeanInfoAssembler\`. Otherwise, assembler-based autodetection cannot decide candidates as expected.

Modes may have different defaults depending on Spring version/configuration. Do not assume Spring Boot automatically enables every mode for every bean; always check the exporter configuration in use.

## 8. MetadataMBeanInfoAssembler and AnnotationJmxAttributeSource

Spring supports metadata annotations to define the JMX surface:

- \`@ManagedResource\`: marks a class as a JMX-managed resource.
- \`@ManagedAttribute\`: describes an exposed getter/setter.
- \`@ManagedOperation\`: describes an operation.
- \`@ManagedOperationParameter\`: describes an operation parameter.

\`AnnotationJmxAttributeSource\` reads metadata from these annotations. \`MetadataMBeanInfoAssembler\` uses the metadata source to build MBeanInfo and has the ability to vote for autodetection.

\`\`\`text
@ManagedResource class
        |
        v
AnnotationJmxAttributeSource
        |
        v
MetadataMBeanInfoAssembler
        |
        +--> includeBean(...) (eligibility)
        |
        +--> metadata attributes/operations
        |
        v
MBeanExporter + naming strategy
        |
        v
MBeanServer.registerMBean
\`\`\`

What matters is that **the annotations are read by the right attribute source**. If the assembler is configured without attaching the source, or uses a different source, the vote result and metadata might not match the annotations on the class.

## 9. Spring Java Configuration Example: Autodetecting with an Assembler

### 9.1. Bean with Management Annotations

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Cache,name=Products",
    description = "Product cache management"
)
public class ProductCacheManagement {

    @ManagedAttribute(description = "Number of cache entries")
    public long getEntryCount() {
        return 100L;
    }

    @ManagedOperation(description = "Request safe cache refresh")
    public void requestRefresh() {
        // Forward request to the cache management service.
    }

    // No @ManagedOperation:
    public void deleteAllInternalCacheFiles() {
        // Should not export internal methods.
    }
}
\`\`\`

### 9.2. Ordinary Bean Without Annotations

\`\`\`java
package example.springjmx;

import org.springframework.stereotype.Service;

@Service
public class BillingService {
    public void createInvoice() {
        // Business logic, no need to expose via JMX.
    }
}
\`\`\`

### 9.3. MBeanExporter Configuration

\`\`\`java
package example.springjmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxAutodetectConfiguration {

    @Bean
    public MBeanExporter jmxExporter() {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_ASSEMBLER
        );

        return exporter;
    }
}
\`\`\`

If \`ProductCacheManagement\` is created by the Spring container and is within the exporter's scan scope, the assembler can vote for the bean based on \`@ManagedResource\` metadata. \`BillingService\` has no management marker so it should not be selected by the annotation-based metadata mechanism.

**Important regarding Spring version:** detection behavior, constant names, and specific properties must match the Javadoc of the deployed version. In Spring Boot, an auto-configured JMX exporter may already exist; do not create an additional exporter that overrides or registers duplicate \`ObjectName\`s without controlling configuration.

## 10. Voting Mechanism via includeBean

In Java, whether an assembler is autodetect-capable is checked via the \`AutodetectCapableMBeanInfoAssembler\` interface:

\`\`\`java
import org.springframework.jmx.export.assembler.AutodetectCapableMBeanInfoAssembler;

public void inspectVote(
        AutodetectCapableMBeanInfoAssembler assembler,
        Class<?> type,
        String beanName) {

    boolean included = assembler.includeBean(type, beanName);

    System.out.printf(
        "JMX autodetect vote: bean=%s, type=%s, include=%s%n",
        beanName, type.getName(), included
    );
}
\`\`\`

The snippet above is only a diagnostic helper and does not alter the registry. During actual exporter execution, the bean class may be affected by proxies, factory beans, and how Spring resolves target types. Therefore, calling \`includeBean\` with an assumed class does not necessarily reproduce the entire exporter run accurately.

### 10.1. Conditions for true/false Votes to Understand

With a metadata assembler:

- If the class carries appropriate management metadata from \`JmxAttributeSource\`, the assembler has grounds to select it.
- If the bean does not carry corresponding metadata, the assembler may decline to select it.
- If annotations are on an interface or target class while the bean is a proxy, discoverability also depends on the introspection mechanism and Spring version.
- If the bean name is invalid for the naming strategy, the vote is still not the registration step.

Do not use voting as an authorization system. A bean selected by metadata still needs verification that the methods actually exposed are safe.

## 11. Example of a Voting-Capable Custom Assembler

To illustrate how an assembler implements a filter, you can extend an existing assembler and customize candidate selection by bean name prefix. Be clear that this is an **application-chosen** detection policy, not a Spring default.

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

public class RestrictedMetadataAssembler
        extends MetadataMBeanInfoAssembler {

    @Override
    public boolean includeBean(Class<?> beanClass, String beanName) {
        return beanName.startsWith("management")
            && super.includeBean(beanClass, beanName);
    }
}
\`\`\`

Configuration:

\`\`\`java
RestrictedMetadataAssembler assembler =
    new RestrictedMetadataAssembler();
assembler.setAttributeSource(source);

exporter.setAssembler(assembler);
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_ASSEMBLER
);
\`\`\`

The example requires both conditions: the bean name starts with \`management\`, and the base metadata assembler accepts the class. This is useful when a team wants to export only beans within a management namespace.

However, do not treat a bean name prefix as a strong security boundary. Bean names can change due to refactoring; JMX connector access permissions and minimal interface design are the essential layers of protection.

## 12. Difference Between Vote and Assembler Output

A bean can pass \`includeBean\` yet the final management interface still depends on \`MBeanInfoAssembler\`.

Example:

\`\`\`java
@ManagedResource(objectName = "com.example:type=Worker,name=Importer")
public class ImportWorkerManagement {

    @ManagedAttribute
    public long getProcessedCount() {
        return 100L;
    }

    public String getSecretToken() {
        return "sensitive";
    }
}
\`\`\`

If the metadata assembler exports only annotated methods, you expect the \`ProcessedCount\` attribute rather than \`SecretToken\`. However, the result is only confirmed by reading the actual \`MBeanInfo\` after export.

Distinguish:

\`\`\`text
includeBean(...) == true
    -> Candidate is eligible to attempt export.

getMBeanInfo(...) after register
    -> Actual management surface visible to the JMX client.
\`\`\`

A secure design controls **both**: selecting the right bean and selecting the right exposed API.

## 13. Checking Exported MBeans

After the Spring context starts:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName cacheName = new ObjectName(
    "com.example:type=Cache,name=Products"
);

System.out.println(
    "Cache management registered: "
        + server.isRegistered(cacheName)
);

if (server.isRegistered(cacheName)) {
    MBeanInfo info = server.getMBeanInfo(cacheName);

    System.out.println("MBean: " + info.getClassName());
    for (var attr : info.getAttributes()) {
        System.out.println("attribute: " + attr.getName());
    }
    for (var op : info.getOperations()) {
        System.out.println("operation: " + op.getName());
    }
}
\`\`\`

Expectations for the example:

- \`ProductCacheManagement\` is registered at \`com.example:type=Cache,name=Products\` when the exporter and assembler are configured properly.
- \`EntryCount\` appears as an attribute.
- \`requestRefresh\` appears as an operation.
- \`deleteAllInternalCacheFiles\` should not appear.
- \`BillingService\` has no corresponding management ObjectName because the assembler vote did not select it.

If \`isRegistered\` returns false, check which MBeanServer the exporter is using. An exporter may be configured with a separate server instead of the platform server.

## 14. Testing the Vote with a Unit Test

You can test the \`includeBean\` logic of a metadata assembler without starting a remote JMX connector.

Example checking a class with and without \`@ManagedResource\`:

\`\`\`java
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

public class VoteDemo {

    public static void main(String[] args) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        boolean management = assembler.includeBean(
            ProductCacheManagement.class,
            "productCacheManagement"
        );

        boolean service = assembler.includeBean(
            BillingService.class,
            "billingService"
        );

        System.out.println(
            "Management eligible: " + management
        );
        System.out.println(
            "Business service eligible: " + service
        );
    }
}
\`\`\`

This is a unit-level demonstration of voting. The expected result with an appropriate metadata source is that the bean with \`@ManagedResource\` is accepted and the ordinary bean is not. When putting this into project tests, write assertions according to the semantics of the actual Spring version.

**Do not equate a unit vote test with an exporter integration test**: a unit test only checks the assembler's eligibility decision and does not prove \`ObjectName\`, MBeanServer, registration policy, or exposed API.

## 15. Integration Testing: Exporter and MBeanServer

An end-to-end check needs to start an \`ApplicationContext\` containing the beans and exporter, then read the JMX registry.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class AutodetectIntegrationDemo {

    public static void main(String[] args) throws Exception {
        ObjectName name = new ObjectName(
            "com.example:type=Cache,name=Products"
        );

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        try (AnnotationConfigApplicationContext ctx =
                new AnnotationConfigApplicationContext()) {

            ctx.register(JmxAutodetectConfiguration.class);
            ctx.register(ProductCacheManagement.class);
            ctx.register(BillingService.class);
            ctx.refresh();

            if (!server.isRegistered(name)) {
                throw new AssertionError(
                    "Expected management MBean was not autodetected"
                );
            }

            MBeanInfo info = server.getMBeanInfo(name);
            boolean hasExpectedAttribute = false;

            for (var attribute : info.getAttributes()) {
                if ("EntryCount".equals(attribute.getName())) {
                    hasExpectedAttribute = true;
                }
                if ("SecretToken".equals(attribute.getName())) {
                    throw new AssertionError(
                        "Sensitive attribute unexpectedly exported"
                    );
                }
            }

            if (!hasExpectedAttribute) {
                throw new AssertionError(
                    "Missing expected EntryCount attribute"
                );
            }
        }
    }
}
\`\`\`

In an integration test, you can add a negative assertion for \`deleteAllInternalCacheFiles\`. When the Spring context closes normally, the exporter typically unregisters the MBeans it manages.

Note: when registering classes via \`ctx.register(...)\`, Spring must recognize annotations/configuration per the running Spring version; in large applications, duplicate default exporters must also be excluded so the test has clear ownership. Test in an isolated environment without altering production MBeans.

## 16. Proxy and Target Class Cases

Some Spring beans are proxied by AOP or transaction interceptors. In that case:

\`\`\`text
Bean name: productCacheManagement
Declared class: ProductCacheManagement
Runtime object: proxy class
Target class: ProductCacheManagement
\`\`\`

Annotations may reside on the target class, while the class examined by the exporter or assembler is the proxy. This affects how reflection locates \`@ManagedResource\` and method metadata.

Approaches to handle this:

1. Determine whether the exporter evaluates the target class or the proxy class.
2. Avoid relying on dynamically generated proxy class names to construct ObjectNames.
3. Use a Spring/JMX metadata source that understands target classes and annotations via supported mechanisms.
4. If discovery is unstable, export a **separate management adapter** not subject to AOP proxying or register explicitly.
5. Verify \`includeBean\` with the actual type the exporter uses, then inspect runtime \`MBeanInfo\`.

Do not assert that simply placing \`@ManagedResource\` on the original class guarantees every proxy configuration will automatically vote true. Verify according to the version and proxy type in use.

## 17. Registration Policy and Lifecycle

A selected candidate also needs to register with an unoccupied \`ObjectName\`, or follow the exporter's duplicate registration policy.

Common policies:

- \`FAIL_ON_EXISTING\`: reject when an MBean with the same ObjectName already exists.
- \`IGNORE_EXISTING\`: skip the candidate if the name already exists.
- \`REPLACE_EXISTING\`: replace according to policy if configured.

Example:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

If the vote is true but the ObjectName already exists, export may fail or be skipped depending on policy. Do not infer that an MBean appearing in JConsole is the new object just registered by the exporter.

When the Spring context closes, the exporter typically unregisters the MBeans it owns. If a bean was manually registered by another component, its lifecycle may differ.

## 18. Risks of Overly Broad Autodetection

Autodetection can save configuration, but it also creates a risk of unintentionally expanding the management surface.

Examples:

- A new bean is mistakenly annotated with \`@ManagedResource\` and automatically picked up by the exporter.
- A class inherits annotations or metadata unintentionally, resulting in a true vote.
- A bean with overly powerful management methods is exposed by the assembler.
- A broadly scanned package contains service/debug adapters not meant for production.
- Two modules export MBeans with the same ObjectName, causing a conflict.
- A JMX user with \`readwrite\` privileges invokes a dangerous operation.

Practical recommendations:

1. **Export only beans that genuinely serve operations.**
2. When there are few MBeans, prefer explicit mapping for easier review.
3. With autodetect, use marker annotations and the right assembler mechanism.
4. Use stable \`ObjectName\`s with clear namespaces and no PII/secrets.
5. Check the MBeanInfo allowlist after export.
6. Write negative tests for attributes/operations that must not be exposed.
7. Protect remote JMX connectors with authentication, TLS, and network restrictions.
8. Do not treat \`includeBean\` as authorization.

## 19. Diagnosing Unexpected Voting or Export Behavior

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| \`@ManagedResource\` bean does not appear | Autodetect mode does not use assembler or lacks appropriate assembler. | Check \`setAutodetectMode\`, \`setAssembler\`, \`AnnotationJmxAttributeSource\`. |
| \`includeBean\` returns false | Annotation not recognized by source, proxy class, or class lacks metadata. | Check actual class and attribute source. |
| \`includeBean\` returns true but MBean is not registered | Naming strategy, MBeanServer, or registration policy. | Check ObjectName, exporter logs, \`isRegistered\`. |
| Ordinary beans also appear | Autodetect mode combines JMX-compliant MBeans or exporter is broadly configured. | Check mode, scope, and MBean interfaces. |
| MBean has extra attributes/operations | Assembler introspects too broadly. | Use metadata or interface allowlist; inspect MBeanInfo. |
| MBean is exported with wrong name | Naming strategy, bean name, non-explicit ObjectName. | Inspect \`ObjectName\` in registry. |
| Duplicate name export | Multiple exporters or modules share the same ObjectName. | Define ownership, check registration policy. |
| Slow app startup | Scanning many beans, heavy introspection, or unsuitable logic. | Narrow candidates or export explicitly. |
| Spring Boot has duplicate MBean error | Auto-configured exporter and custom exporter both export. | Keep only the appropriate configuration, avoid two registrars. |
| Fails only when AOP is enabled | Metadata is not properly found through proxy. | Verify target class/metadata, use adapter or explicit mapping. |

## 20. When to Use Autodetect vs. Explicit Export?

| Situation | Usually Suitable Choice | Reason |
| --- | --- | --- |
| Small application with 2–3 MBeans | Explicit \`setBeans(...)\` | Easy to control, clear ownership. |
| Many modules with stable marker annotations | \`AUTODETECT_ASSEMBLER\` | Reduces repetitive config, uses shared metadata policy. |
| Only Standard MBeans/MXBeans with clear interfaces | \`AUTODETECT_MBEAN\` if desired by project | Detects according to compliant JMX contract. |
| Application risks exposing internal APIs | Explicit export and contract tests | Reduces unintended surface expansion. |
| Complex AOP proxies present | Management adapter or explicit registration | Avoids depending on runtime/proxy type names. |
| Multiple Spring contexts/exporters | Define one owner per ObjectName | Reduces collisions and incorrect cleanup. |

No mode automatically guarantees security. The exposed surface and remote connector permissions must be controlled separately.

## 21. Practice Exercises

### Exercise 1 — Direct Vote Inspection

Create one class with \`@ManagedResource\` and one class without annotations. Initialize \`MetadataMBeanInfoAssembler\` with \`AnnotationJmxAttributeSource\`, and call \`includeBean\` for both.

**Objective:** understand the assembler's eligibility decision.

### Exercise 2 — Run Exporter in Assembler Mode

Configure \`AUTODETECT_ASSEMBLER\` and a management bean with an explicit \`ObjectName\`. Start the Spring context and check \`MBeanServer.isRegistered(name)\`.

**Objective:** connect the vote to the actual export process.

### Exercise 3 — Compare Modes

Use one Standard MBean, one \`@ManagedResource\` bean, and one ordinary service bean. Try \`AUTODETECT_MBEAN\`, \`AUTODETECT_ASSEMBLER\`, and \`AUTODETECT_ALL\` in isolated contexts.

**Objective:** observe how mode changes the candidate set.

### Exercise 4 — Protect the Exposed Surface

Add an unannotated public method \`deleteAllInternalCacheFiles()\`. Write a check confirming that the method does not appear in \`MBeanInfo.getOperations()\`.

**Objective:** distinguish an eligible bean from an eligible API.

### Exercise 5 — Proxies

Wrap the bean with an AOP proxy in a lab application. Compare autodetect and metadata results with/without the proxy. If unstable, try an adapter or explicit export.

**Objective:** understand the impact of runtime type and target class.

### Exercise 6 — Registration Conflict

Create two exporters attempting to register the same \`ObjectName\`; test \`FAIL_ON_EXISTING\` and \`IGNORE_EXISTING\` policies. Observe callbacks, errors, and \`isRegistered\` results.

**Objective:** distinguish a true vote from successful registration.

## 22. Review Questions

**1. What problem does \`AutodetectCapableMBeanInfoAssembler\` solve?** It allows a metadata assembler to contribute to the decision of whether a bean should be autodetected for JMX export.

**2. What is the voting method?** \`includeBean(Class<?> beanClass, String beanName)\`.

**3. Does a true vote mean the MBean is already registered?** No. The exporter still has to name it, prepare metadata, and call register.

**4. Does a true vote mean every public method is exposed?** No. The API surface depends on the assembler and the MBean contract.

**5. How does \`AUTODETECT_ASSEMBLER\` differ from \`AUTODETECT_MBEAN\`?** One mechanism relies on the assembler's vote, while the other detects MBeans conforming to the JMX contract.

**6. What do metadata annotations do?** They provide management information so the assembler can select beans and build attributes/operations.

**7. Why do proxies cause difficulty?** The exporter may see a proxy class different from the target class containing the annotations, depending on the introspection mechanism.

**8. Why is \`includeBean\` not a security boundary?** It only selects candidates; access permissions and exposed operations must be controlled separately.

**9. How do you verify that export worked properly?** Check \`ObjectName\`, \`isRegistered\`, and \`MBeanInfo\` after the Spring context initializes.

**10. When should you choose explicit export?** When the number of MBeans is small, the API is sensitive, there are complex proxies, or precise per-bean control is needed.

## 23. Summary

**AutodetectCapableMBeanInfoAssembler** is the mechanism for the Spring JMX exporter to ask a metadata assembler whether a Spring bean should be selected during **autodetection**. The \`includeBean(beanClass, beanName)\` method acts as a vote, commonly used with metadata-based assemblers like \`MetadataMBeanInfoAssembler\`.

A vote only decides **whether a candidate is eligible**; it does not register the MBean by itself and does not grant permissions to JMX clients. For safe deployment, coordinate the autodetect mode, assembler, annotation source, naming strategy, and registration policy properly; finally, inspect runtime MBeanInfo to ensure only necessary attributes/operations are exposed.

## References

- Spring Framework Javadoc — \`AutodetectCapableMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/AutodetectCapableMBeanInfoAssembler.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`MetadataMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — \`AnnotationJmxAttributeSource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html