# Resolving Bean Names, ObjectNames, and Display Names in Spring Framework JMX

## 1. Objectives

When exposing a Spring bean to Java Management Extensions (JMX), there are at least three ways of "naming" the same object:

- **Bean name**: the bean's identifier within the Spring ApplicationContext.
- **ObjectName**: the MBean identifier in the MBeanServer, using JMX syntax consisting of a domain and key properties.
- **Display name**: the label or description shown by management tools such as JConsole, VisualVM, or dashboards; it may come from ObjectName, MBean metadata, or the tool's own logic.

For example, a Spring bean might be named \`checkoutMonitor\`, exported under ObjectName \`com.example.shop:type=Queue,name=Checkout\`, while JConsole displays a node \`Queue\` → \`Checkout\` or the description \`Checkout queue monitor\`.

These three ways of naming **do not automatically match**. Unclear configuration easily leads to missing MBeans, duplicate ObjectNames, unstable names after restarts, or UI displays differing from operator expectations.

After this lesson, you will be able to:

1. Distinguish the three layers of names and their uniqueness scopes.
2. Know which Spring component determines bean names and ObjectNames.
3. Use \`@ManagedResource\`, \`MBeanExporter\`, and naming strategies to control names.
4. Diagnose differences between names in the Spring context and names in the MBeanServer.
5. Design stable domains/key properties for monitoring.
6. Verify displayed names using \`ObjectName\` and \`MBeanInfo\`.
7. Handle collisions, AOP proxies, and multiple ApplicationContexts.

## 2. Three Layers of Names in One Diagram

\`\`\`text
Spring ApplicationContext
    |
    +-- bean name: "checkoutMonitor"
    |         |
    |         v
    |    Java bean object
    |         |
    |         v
    |    MBeanExporter
    |         |
    |         +--> ObjectNamingStrategy / @ManagedResource
    |                  |
    |                  v
    +---------- MBeanServer -------------------+
               ObjectName:                    |
               com.example.shop:              |
                 type=Queue,name=Checkout     |
                                              |
                                   JMX client / JConsole
                                              |
                                              v
                                 Labels and tree grouping
                                 from ObjectName + metadata
\`\`\`

| Name Type | Example | Managed By | Scope |
|---|---|---|---|
| Spring bean name | \`checkoutMonitor\` | Spring BeanFactory/ApplicationContext | Context bean namespace |
| JMX ObjectName | \`com.example.shop:type=Queue,name=Checkout\` | MBeanServer + exporter | Unique within one MBeanServer |
| Display name/description | \`Checkout queue monitor\` | MBean metadata or JMX client | Depends on tool and UI rendering |

**Key point:** a bean name is not an ObjectName, and a description in MBeanInfo is not the JMX key used to invoke \`getAttribute\` or \`invoke\`.

## 3. Bean Name in Spring

Spring manages beans by name within the context. With Java configuration:

\`\`\`java
@Bean("checkoutMonitor")
public CheckoutMonitor monitor() {
    return new CheckoutMonitor();
}
\`\`\`

Or component scanning:

\`\`\`java
@Component("checkoutMonitor")
public class CheckoutMonitor {
    // ...
}
\`\`\`

Although both name the bean \`checkoutMonitor\`, they do not determine on their own which ObjectName the MBean will be registered under.

You can retrieve the bean:

\`\`\`java
Object bean = context.getBean("checkoutMonitor");
\`\`\`

This call is a Spring container lookup, completely different from:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
server.getAttribute(
    new ObjectName("com.example.shop:type=Queue,name=Checkout"),
    "PendingCount");
\`\`\`

The second is a JMX lookup on an MBeanServer.

### 3.1. Bean names, aliases, and context hierarchy

A bean can have aliases in Spring. Aliases do not automatically create multiple MBeans. Root and child contexts may contain beans with the same name or shadow each other's names; however, if both exporters register the same ObjectName into the same server, a JMX collision occurs regardless of the two contexts being separate.

**Rule:** uniqueness of bean names and ObjectNames is enforced by different registries.

## 4. ObjectName in JMX

General syntax:

\`\`\`text
<domain>:<key>=<value>,<key>=<value>
\`\`\`

Example:

\`\`\`text
com.example.shop:type=Queue,name=Checkout
\`\`\`

Where:

- \`com.example.shop\`: domain.
- \`type=Queue\`: resource group.
- \`name=Checkout\`: logical instance or resource.
- Additional properties like \`module=orders\`, \`region=vn\`, \`instance=node-1\` can be added if differentiation is needed.

An ObjectName is not an arbitrary string. Java JMX has special-character and quoting rules. Constructing via the Java API:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.shop:type=Queue,name=Checkout");
\`\`\`

Two ObjectNames with the same domain and the same set of key-value pairs are equal, even if property order differs:

\`\`\`java
ObjectName a = new ObjectName(
    "com.example.shop:type=Queue,name=Checkout");
ObjectName b = new ObjectName(
    "com.example.shop:name=Checkout,type=Queue");

System.out.println(a.equals(b)); // true
\`\`\`

When naming from data that may contain special characters, use validation and \`ObjectName.quote\` where appropriate. Never concatenate untrusted request values directly into an ObjectName.

### 4.1. Default domain does not override every ObjectName

An \`MBeanServer\` has a default domain, but if an MBean is registered with an ObjectName that already specifies a domain, the default domain does not overwrite that domain. Do not set \`defaultDomain\` on the server and expect it to change all ObjectNames of Spring beans.

### 4.2. ObjectName is a public contract

JMX clients locate MBeans by ObjectName. When changing:

\`\`\`text
com.example.shop:type=Queue,name=Checkout
\`\`\`

to:

\`\`\`text
com.example.shop:type=Queue,name=CheckoutV2
\`\`\`

dashboards and automation using the old name can break even though the bean name is still \`checkoutMonitor\`. For long-lived monitored MBeans, choose a stable name based on the logical resource.

## 5. Where Does the Display Name Come From?

For JMX tools, "display name" is not a single mandatory field standardized across all MBeans. A UI may rely on:

1. The domain and key properties of \`ObjectName\` to build the MBeans tree.
2. \`MBeanInfo.getDescription()\` to describe the resource.
3. \`MBeanAttributeInfo.getDescription()\` and \`MBeanOperationInfo.getDescription()\`.
4. Sorting/grouping rules of JConsole, VisualVM, or dashboard products.
5. Custom configuration in the monitoring tool.

Example:

\`\`\`java
@ManagedResource(
    objectName = "com.example.shop:type=Queue,name=Checkout",
    description = "Checkout queue operational view")
public class CheckoutMonitor {
    // ...
}
\`\`\`

Here \`description\` is metadata for humans; **it does not replace ObjectName**. JConsole may display the resource by \`type\`, \`name\`, or its own tool structure; there is no guarantee every JMX client will display \`description\` as the primary label.

### 5.1. Do not use UI labels as connection keys

An operator seeing "Checkout queue operational view" in the UI might think that is the MBean name. However, client code must use the real ObjectName:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.shop:type=Queue,name=Checkout");
\`\`\`

Do not call:

\`\`\`java
new ObjectName("Checkout queue operational view");
\`\`\`

because it is not valid ObjectName syntax.

## 6. Spring @ManagedResource Example: Full, Explicit Name

A monitoring bean:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component("checkoutMonitor")
@ManagedResource(
    objectName = "com.example.shop:type=Queue,name=Checkout",
    description = "Checkout queue operational view")
public class CheckoutMonitor {

    private final AtomicInteger pending =
        new AtomicInteger();

    @ManagedAttribute(
        description = "Number of pending checkout tasks")
    public int getPendingCount() {
        return pending.get();
    }

    @ManagedOperation(
        description = "Reset demonstration counter")
    public void resetDemoCounter() {
        pending.set(0);
    }

    public void recordPendingTask() {
        pending.incrementAndGet();
    }
}
\`\`\`

Spring configuration:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = CheckoutMonitor.class)
@EnableMBeanExport
public class AppConfig {
}
\`\`\`

The Spring exporter reads metadata when configured appropriately and registers the object under the declared ObjectName. An application with multiple exporters or MBeanServers must specify the server/ownership to avoid duplicate registrations.

To run in a demo:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    AppConfig.class)) {

            CheckoutMonitor monitor =
                context.getBean("checkoutMonitor",
                    CheckoutMonitor.class);

            monitor.recordPendingTask();

            System.out.println(
                "Spring bean name: checkoutMonitor");
            System.out.println(
                "PID: " + ProcessHandle.current().pid());

            Thread.sleep(120_000);
        }
    }
}
\`\`\`

Use local JConsole to observe the exported MBean. **Do not equate the name \`checkoutMonitor\` with ObjectName** just because both point to the same resource in the example.

## 7. Explicit MBeanExporter Configuration

When you need to control ObjectName from configuration instead of annotations, use \`MBeanExporter\`:

\`\`\`java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Configuration
public class ExplicitJmxConfig {

    @Bean("checkoutMonitor")
    public CheckoutMonitor checkoutMonitor() {
        return new CheckoutMonitor();
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler assembler() {
        MethodNameBasedMBeanInfoAssembler a =
            new MethodNameBasedMBeanInfoAssembler();
        a.setManagedMethods(
            "getPendingCount", "resetDemoCounter");
        return a;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer server,
            CheckoutMonitor checkoutMonitor,
            MethodNameBasedMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.shop:type=Queue,name=Checkout",
            checkoutMonitor));
        return exporter;
    }
}
\`\`\`

The example assumes the context already has exactly one \`MBeanServer\` bean; you can declare:

\`\`\`java
@Bean
public MBeanServer mbeanServer() {
    return java.lang.management.ManagementFactory
        .getPlatformMBeanServer();
}
\`\`\`

In the explicit configuration:

- Bean key \`checkoutMonitor\` serves Spring DI.
- The \`setBeans\` mapping sets the JMX ObjectName.
- The assembler selects exposed methods/attributes.
- \`MBeanServer\` is the target registry.

**Do not inadvertently also enable \`@EnableMBeanExport\` for the same bean when an explicit exporter already exists**, because two exporters may register the same ObjectName.

## 8. ObjectNamingStrategy: When You Don't Want to Hardcode Every Name

Spring provides \`ObjectNamingStrategy\` to determine ObjectNames by strategy. Common types include:

| Strategy | Name Source | Scenario |
|---|---|---|
| \`KeyNamingStrategy\` | Mapping key/bean key converted to ObjectName | Stable names managed by config |
| \`MetadataNamingStrategy\` | \`@ManagedResource\` metadata | Names declared on managed classes |
| \`IdentityNamingStrategy\` | Identity of the managed object | Need to distinguish instances at runtime |
| Custom strategy | Normalized module ID/resource ID | Custom naming conventions |

When using a naming strategy, understand the interaction between keys in \`setBeans\`, annotation metadata, and explicit ObjectNames.

### 8.1. Bean name need not equal the ObjectName returned by the strategy

Example:

\`\`\`text
Spring bean name = checkoutMonitor
ObjectNamingStrategy -> com.example.shop:type=Queue,name=Checkout
\`\`\`

This is a valid mapping. A naming strategy can use the bean name as part of its input, yet it still must produce a valid and unique \`ObjectName\`.

### 8.2. Identity naming and stability

A strategy based on object identity can generate a different name after restart or when an AOP proxy is recreated. That is useful for distinguishing Java instances, but not ideal for dashboards with hardcoded ObjectNames. If you need to track the same logical resource, use stable keys/metadata.

## 9. Debugging via API: Viewing Bean Names and ObjectNames

Do not rely on the UI alone. Query the two respective registries.

### 9.1. Listing relevant Spring bean names

\`\`\`java
String[] names =
    context.getBeanNamesForType(CheckoutMonitor.class);

for (String beanName : names) {
    System.out.println("Spring bean: " + beanName);
}
\`\`\`

This only provides bean names by type in the context; it does not automatically return JMX ObjectNames.

### 9.2. Listing JMX ObjectNames

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server =
    context.getBean(MBeanServer.class);

Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.shop:*"), null);

for (ObjectName name : names) {
    System.out.println("JMX ObjectName: " +
        name.getCanonicalName());
}
\`\`\`

If the context has no MBeanServer bean, retrieve the actual server used by the exporter or the platform server when appropriate. Do not call \`getBean(MBeanServer.class)\` assuming it is available in every configuration.

### 9.3. Reading MBean metadata to inspect description

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.shop:type=Queue,name=Checkout");

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("MBean class: " + info.getClassName());
System.out.println("Description: " + info.getDescription());

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(
        "Attribute " + a.getName() +
        " description=" + a.getDescription());
}
\`\`\`

The description may differ from the JConsole node name and may be empty depending on the assembler or implementation.

## 10. Diagnosing Mismatches Between Names

| Symptom | Common Cause | How to Confirm |
|---|---|---|
| Spring bean exists, but no JMX MBean | Export not enabled or bean not selected | Check exporter, annotations, context |
| JConsole displays a name other than \`checkoutMonitor\` | UI uses ObjectName instead of bean name | Inspect \`queryNames\` and metadata |
| \`getAttribute\` throws \`InstanceNotFoundException\` | Wrong ObjectName or server | Check \`isRegistered\` |
| MBean name changes after enabling AOP | Naming strategy relies on proxy class/identity | Compare ObjectNames and proxy types |
| Two differently named beans collide in JMX | Same ObjectName in exporter | Inspect mappings and registration |
| UI description does not change | Metadata assembler is not using annotations | Read \`MBeanInfo\` directly |
| Display name disappears after restart | Identity-generated name used | Switch to stable naming |
| Remote client sees different MBeans than local | Connected to a different server/endpoint | Compare ObjectNames and server identity |

An effective diagnostic sequence:

\`\`\`text
1. Does the Spring bean exist?
2. Which exporter manages the bean?
3. Which naming strategy is used?
4. What is the actual ObjectName?
5. Which MBeanServer contains the ObjectName?
6. What does MBeanInfo describe?
7. Where is the JMX client connecting and how does it build the UI?
\`\`\`

## 11. Collisions: Different Bean Names Can Still Share an ObjectName

Two beans:

\`\`\`text
Bean A: inventoryCheckoutMonitor
Bean B: billingCheckoutMonitor
\`\`\`

yet both exported under:

\`\`\`text
com.example:type=Monitor,name=Primary
\`\`\`

When entering the same MBeanServer, they conflict despite different bean names. The Spring exporter's \`RegistrationPolicy\` has behaviors such as:

- \`FAIL_ON_EXISTING\`: reports an error.
- \`IGNORE_EXISTING\`: skips the new registration.
- \`REPLACE_EXISTING\`: replaces the existing registration.

Policies only handle collisions; they do not replace a good naming convention. Using \`IGNORE_EXISTING\` can cause the new MBean not to appear without immediate detection; using \`REPLACE_EXISTING\` can affect objects managed by another context.

To have two independent MBeans, use independent ObjectNames:

\`\`\`text
com.example:type=Monitor,module=inventory,name=Primary
com.example:type=Monitor,module=billing,name=Primary
\`\`\`

When naming from input that may contain commas, colons, or wildcards, validate and quote according to JMX syntax. In multi-tenant systems, never include private data or secrets in ObjectNames.

## 12. Multiple ApplicationContexts and a Single MBeanServer

One JVM can contain root and child contexts or multiple independent module contexts:

\`\`\`text
RootContext
  - sharedMonitor
  - rootExporter

ChildContext
  - checkoutMonitor
  - childExporter
\`\`\`

Bean names may be valid within each context, yet a shared MBeanServer still requires unique ObjectNames.

Principles:

1. Each context/exporter has clear ownership.
2. Do not automatically export the same shared bean in two contexts.
3. Include module-distinguishing information in JMX names when needed.
4. Closing a context must unregister only MBeans belonging to it.
5. A local client connecting to the platform server will not automatically find MBeans in a custom server.
6. Do not use identity/proxy classes as a long-term naming contract if clients need stable names.

## 13. AOP Proxies and Name Changes

Spring AOP can change the class of the object seen by the exporter. With JDK dynamic proxies, the runtime class is not the target class; with class-based proxies, the proxy class is a subclass.

If a naming strategy uses the class name or identity, the ObjectName may change after enabling \`@Transactional\`, \`@Cacheable\`, or other advice. However, if using an explicitly declared ObjectName:

\`\`\`java
@ManagedResource(
    objectName = "com.example.shop:type=Queue,name=Checkout")
\`\`\`

the name is designed to remain stable, provided the exporter selects the right metadata and registration succeeds.

Do not guess names by reading \`bean.getClass().getName()\`; query actual ObjectNames and inspect \`MBeanInfo\`.

## 14. Should Display Names Be Translated into Multiple Languages?

JMX ObjectNames should be stable, follow easy-to-query conventions, and not change by locale. If the UI needs Vietnamese or English, translate the **display label** at the dashboard/application UI layer rather than turning ObjectName into mutable natural-language strings.

Example:

\`\`\`text
ObjectName (stable):
  com.example.shop:type=Queue,name=Checkout

Vietnamese UI label:
  Hàng đợi thanh toán

English UI label:
  Checkout queue
\`\`\`

This keeps automation and monitoring working when switching interface languages. \`description\` in metadata can assist operators, though it is not a full multilingual localization system.

## 15. Protecting the Naming Contract with Tests

An integration test should verify ObjectName, metadata, and Spring bean mapping.

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;

import static org.junit.jupiter.api.Assertions.*;

class JmxNamingContractTest {

    @Test
    void exportedNameRemainsStable() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    AppConfig.class)) {

            assertNotNull(context.getBean("checkoutMonitor"));

            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "com.example.shop:type=Queue,name=Checkout");

            assertTrue(server.isRegistered(name));

            assertEquals(
                0,
                server.getAttribute(name, "PendingCount"));

            String description =
                server.getMBeanInfo(name).getDescription();

            assertNotNull(description);
        }
    }
}
\`\`\`

The example assumes the exporter uses the platform MBeanServer and the test does not run in parallel with another test registering the same ObjectName. If using a dedicated server, use the exact server passed to the exporter. Do not assert \`description\` against a hardcoded string unless the business contract requires fixed description content.

Other valuable tests:

- Two different Spring beans must export to two ObjectNames if they are two resources.
- Closing one context does not unregister another context's MBeans.
- Enabling AOP does not change the expected ObjectName.
- Querying by domain/type returns the right group of MBeans.
- A JMX client relying solely on ObjectName continues to access it after upgrades.

## 16. Designing Naming Conventions for Production

A consistent convention:

\`\`\`text
<reverse-domain>:type=<resourceType>,module=<module>,name=<resourceName>
\`\`\`

Examples:

\`\`\`text
com.example.platform:type=Cache,module=orders,name=Products
com.example.platform:type=Queue,module=orders,name=Checkout
com.example.platform:type=Worker,module=billing,name=Invoice
\`\`\`

Practical rules:

- Use a Java-namespace-like domain or a stable system name.
- \`type\` represents the resource kind; \`name\` represents the logical instance.
- Add \`module\` or \`instance\` only when disambiguation is needed.
- Do not use timestamps, thread IDs, or constantly changing counters as keys.
- Do not put emails, access tokens, or secrets into ObjectNames.
- Do not depend on key property ordering when comparing.
- Write tests to prevent accidental renames across releases.
- Keep UI labels separate from technical identity.

An ObjectName with too many keys complicates queries; a name with too few keys can cause collisions. Pick just enough identifying information for actual requirements.

## 17. Practice Exercises

### Exercise A — Distinguishing the three names

Create a Spring bean named \`inventoryMonitor\`, export it as \`training.shop:type=Inventory,name=Primary\`, and declare description \`Inventory status monitor\`. Print the bean name from ApplicationContext, ObjectName from MBeanServer, and description from MBeanInfo. Explain the differences.

### Exercise B — Collision

Create two beans \`monitorA\` and \`monitorB\` and try to export them with the same ObjectName. Note the registration error. Fix it using a \`module\` key and verify both ObjectNames coexist simultaneously.

### Exercise C — Renaming bean without changing JMX

Rename the Spring bean from \`checkoutMonitor\` to \`checkoutStatusMonitor\` while keeping \`@ManagedResource.objectName\` fixed. Observe that JMX clients still find the MBean under the old name if export is properly configured.

### Exercise D — Changing description

Change the description from English to Vietnamese while keeping ObjectName unchanged. Inspect metadata and JConsole; explain why automation should not depend on description.

### Exercise E — Querying by group

Register three MBeans in domain \`training.shop\`. Use pattern \`training.shop:type=Queue,*\` to find all queues. Explain why \`,*\` is needed when ObjectNames have additional key properties.

## 18. Self-Check Questions

1. Is a bean name an ObjectName?
2. Who decides the bean name in Spring and who decides the JMX ObjectName?
3. Where does the display name in JConsole come from?
4. Can a description be used instead of \`ObjectName\` when calling \`getAttribute\`?
5. Can two different bean names collide on the same ObjectName?
6. Why should ObjectName remain stable across restarts?
7. When should \`IdentityNamingStrategy\` be chosen?
8. Why can AOP proxies cause generated JMX names to change?
9. How do you know which MBeanServer the exporter registered into?
10. Why shouldn't multilingual UI labels alter JMX technical identity?

## 19. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — \`ObjectNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/ObjectNamingStrategy.html
- Spring Framework API — \`@ManagedResource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html

**Takeaway:** bean names serve Spring DI, ObjectNames serve the JMX registry and automation, and display names serve humans. Designing these three naming layers clearly helps prevent collisions, reduces MBean lookup errors, and keeps management contracts stable as the application evolves.
