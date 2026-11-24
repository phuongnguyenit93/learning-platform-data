# Choosing Domains by Product, Module, and Environment in JMX ObjectName

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the role of the **domain** in \`javax.management.ObjectName\` and distinguish the domain from key properties.
- Design a systematic domain convention for **products**, **modules**, and **deployment environments**.
- Decide when to put the environment in the domain, when to make it a key property, and when not to encode the environment in the ObjectName at all.
- Avoid name collisions across multiple MBeans, libraries, applications, and instances.
- Implement naming conventions in plain Java and Spring JMX.
- Plan queries, renames, and dashboard operations without losing the ability to locate MBeans.

## 2. Why Design Domains from the Beginning?

JMX (Java Management Extensions) provides a mechanism to monitor and manage running Java applications. An MBean is registered in an \`MBeanServer\` under an \`ObjectName\` identifier:

\`\`\`text
domain:key=value,key2=value2
\`\`\`

For example:

\`\`\`text
com.example.shop.orders:type=Queue,name=paymentEvents
\`\`\`

Where:

- **Domain**: \`com.example.shop.orders\`.
- **Key properties**: \`type=Queue\`, \`name=paymentEvents\`.
- **MBeanServer**: the registration and lookup scope for the ObjectName.

The domain helps **organize namespaces** under a consistent convention. If a product has multiple modules—such as \`catalog\`, \`orders\`, and \`payments\`—you want operators to recognize immediately which subsystem an MBean belongs to:

\`\`\`text
com.example.shop.catalog:type=Cache,name=products
com.example.shop.orders:type=Queue,name=outbox
com.example.shop.payments:type=ConnectionPool,name=primary
\`\`\`

When opening JConsole or querying via \`MBeanServer.queryNames()\`, the domain serves as the starting point for grouping and finding resources.

However, **domains do not create security boundaries**. Two different domains in the same MBeanServer remain subject to the same registration and access-control mechanisms of the server. Separating domains does not replace JMX authorization, authentication, and limiting network exposure.

## 3. Domains in the ObjectName Specification

An \`ObjectName\` consists of two parts separated by the first colon:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox
|---------------------| |--------------------|
         domain             key properties
\`\`\`

A domain is a logical string and **does not have to be an actual Java package name or real DNS name**. Using reverse DNS style (e.g., \`com.example...\`) is a useful convention because it reduces the chance of two organizations picking the same name.

Things to remember:

1. The domain is part of the ObjectName: changing the domain produces a different JMX identity.
2. A domain may contain dots \`.\`; dots convey hierarchy by convention and do not turn it into a mandatory substructure.
3. ObjectNames are case-sensitive; \`com.example.Shop\` and \`com.example.shop\` are two different domains.
4. \`*\` and \`?\` in a domain can create a **domain pattern** for querying; registered names must be concrete ObjectNames.
5. One domain can contain many MBeans. Uniqueness at registration depends on the **entire ObjectName**—domain plus the set of key properties—within the scope of one MBeanServer.

Use \`getDomain()\` to retrieve the domain and \`isDomainPattern()\` to check whether a name uses a domain pattern.

Example:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
        "com.example.shop.orders:type=Queue,name=outbox");

System.out.println(name.getDomain());
// com.example.shop.orders

System.out.println(name.isDomainPattern());
// false
\`\`\`

In practice, if an \`ObjectName\` has an empty domain, the MBeanServer may apply its default domain during registration. For multi-module applications, declaring the domain explicitly avoids depending on each server's default domain.

## 4. Three Axes to Define Before Naming

In a multi-application system, it is easy to conflate these three classification dimensions:

| Axis | Question | Examples |
|---|---|---|
| **Product / system** | Which product does the MBean belong to? | \`shop\`, \`billing\`, \`learning\` |
| **Module / component** | Which functional area owns the resource? | \`orders\`, \`catalog\`, \`payments\` |
| **Environment** | Where is the instance running? | \`dev\`, \`staging\`, \`prod\` |

You need to design an **operable convention**, not cram every piece of information into a single domain string.

Example of a short domain:

\`\`\`text
com.example.shop.orders
\`\`\`

and a key property for the environment:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox,env=prod
\`\`\`

Or representing the environment inside the domain:

\`\`\`text
com.example.shop.prod.orders:type=Queue,name=outbox
\`\`\`

Both options can be valid, but they have different consequences for **querying, renaming, monitoring charts, and configuration reuse**. You should not vary this arbitrarily across applications in the same organization.

## 5. Product-Based Domains: Stable Namespaces

A baseline convention is:

\`\`\`text
<reverse-dns>.<product>
\`\`\`

Examples:

\`\`\`text
com.example.shop:type=Cache,name=products
com.example.shop:type=Queue,name=orders
com.example.billing:type=BatchJob,name=settlement
\`\`\`

This approach works well when each product has a moderate number of MBeans or when you want to keep domains relatively short.

**Advantages:**

- Easy to identify the owning unit.
- Low risk of domain collisions with third-party libraries.
- The domain stays stable even when Java packages are reorganized.
- A query like \`com.example.shop:*\` can find the product's MBeans within that domain (when using an appropriate pattern).

**Limitations:**

- The domain only distinguishes down to the product level; MBeans from multiple modules appear under one group.
- Key properties such as \`module\`, \`type\`, and \`name\` are needed for further classification.

If you choose a single product-wide domain, you can add a \`module\` key:

\`\`\`text
com.example.shop:module=catalog,type=Cache,name=products
com.example.shop:module=orders,type=Queue,name=outbox
com.example.shop:module=payments,type=Pool,name=primary
\`\`\`

This model is especially suitable when dashboards want to query against a single fixed domain and group by module using a key.

## 6. Module-Based Domains: Convenient for Large-Scale Observability

With many modules or multiple development teams, you can use:

\`\`\`text
<reverse-dns>.<product>.<module>
\`\`\`

Examples:

\`\`\`text
com.example.shop.catalog:type=Cache,name=products
com.example.shop.orders:type=Queue,name=outbox
com.example.shop.payments:type=ConnectionPool,name=primary
\`\`\`

This design groups MBeans by module directly in the domain. JMX tools typically display the list of domains, making it easy for operators to locate the right group.

Conventions to align on:

- Keep product/module names lowercase and stable.
- Name according to ownership or operational boundaries, not necessarily Java package structure.
- Avoid overly granular names such as \`com.example.shop.orders.application.service.impl\` if package layers may change frequently.
- Keep semantics consistent: \`orders\` always refers to one module; do not alternate between \`order\` and \`order-service\`.
- Use \`type\` and \`name\` keys to distinguish resources within the module.

**Important:** Dots in a domain do not make JMX treat \`com.example.shop\` as the structural parent of \`com.example.shop.orders\`. It is merely a name string. To query by prefix, you must use a **domain pattern**.

For example:

\`\`\`text
com.example.shop.*:type=Queue,*
\`\`\`

is used to find domains starting with \`com.example.shop.\` that contain MBeans with \`type=Queue\`. This query does not include the exact domain \`com.example.shop\` because the pattern has a dot after \`shop\`.

## 7. Should Environment Go in the Domain or a Key Property?

There is no single right answer for every system. The decision should be based on how MBeanServers are organized, monitoring requirements, and existing conventions.

### Option A: Domain Includes Environment

\`\`\`text
com.example.shop.dev.orders:type=Queue,name=outbox
com.example.shop.staging.orders:type=Queue,name=outbox
com.example.shop.prod.orders:type=Queue,name=outbox
\`\`\`

Advantages:

- The domain name itself expresses the environment.
- Domains can be viewed by environment if multiple environments are registered in one MBeanServer or aggregated together in a monitoring system.
- Querying with \`com.example.shop.prod.*:type=Queue,*\` is intuitive.

Trade-offs:

- Every environment has a different domain; scripts/dashboards must use patterns or environment-specific configuration parameters.
- Placing the environment between product and module means querying all domains of a single module requires wildcards on both sides.
- Renaming \`stage\` to \`staging\` changes the identity, potentially breaking dashboards or clients using static names.

### Option B: Environment as a Key Property

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox,env=dev
com.example.shop.orders:type=Queue,name=outbox,env=staging
com.example.shop.orders:type=Queue,name=outbox,env=prod
\`\`\`

Advantages:

- The module domain remains stable across environments.
- Easy to query across all environments with \`com.example.shop.orders:type=Queue,*\`.
- Systems can filter or group by the \`env\` key.

Trade-offs:

- Querying by domain alone does not isolate a single environment.
- When making \`env\` a mandatory key, all registration code must agree on it; omitting the key produces a name outside the convention.
- Names become longer, especially when many classification dimensions exist.

### Option C: Do Not Encode Environment in the ObjectName

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox
\`\`\`

Common case: each JVM and MBeanServer belongs to exactly one deployment environment; the monitoring system knows the environment from the **connection, host, cluster, Kubernetes namespace, or collector metadata**.

Advantages:

- Identical ObjectName for the same resource across dev, staging, and production.
- Scripts and dashboards reuse names easily.
- Code building \`ObjectName\` does not depend on environment variables.

Trade-offs:

- When exporting a list of JMX names outside the MBeanServer context, the ObjectName alone does not reveal the environment.
- The collection and observability pipeline must attach the environment from external metadata.

**Important distinction:** An ObjectName is unique within *one MBeanServer*, not across all hosts, clusters, or the entire company. Two different JVMs can register the exact same string \`com.example.shop.orders:type=Queue,name=outbox\` completely normally. Therefore, there is no need to add \`env\` solely to prevent name collisions between two separate JVMs.

## 8. Practical Decision Matrix

| Context | Recommended Organization | Why |
|---|---|---|
| Single product, few MBeans | Domain by product; \`type\`, \`name\` keys | Simple and stable |
| Multi-module product | Domain by \`product.module\` | Clear grouping in JConsole |
| Dashboard aggregating multiple modules | Shared product domain + \`module\` key | Convenient single-domain queries |
| Each JVM belongs to a single environment | No need to put \`env\` in ObjectName | Server/collector already supplies context |
| One MBeanServer genuinely hosts MBeans representing multiple environments | Environment in domain or \`env\` key | Need to distinguish otherwise identically named resources |
| Operations tools frequently filter by environment | Consistent \`env\` convention, in domain or key | Predictable queries |
| Multiple instances of the same type in one MBeanServer | Distinguishing \`instance\` or \`name\` key | Avoid \`InstanceAlreadyExistsException\` |

This matrix is a design guideline, not a mandatory JMX rule. It is best to publish a naming convention and apply it consistently across the entire product.

## 9. A Complete Convention for the Shop Product

Suppose the product has three modules: \`catalog\`, \`orders\`, and \`payments\`. Each module has its own caches, queues, or pools.

### Domain Template

\`\`\`text
com.example.shop.<module>
\`\`\`

### ObjectName Template

\`\`\`text
com.example.shop.<module>:type=<type>,name=<logical-name>
\`\`\`

Add extra keys when there is a specific reason:

\`\`\`text
com.example.shop.<module>:type=<type>,name=<logical-name>,instance=<id>
\`\`\`

Example list:

\`\`\`text
com.example.shop.catalog:type=Cache,name=productDetails
com.example.shop.catalog:type=Cache,name=categoryTree
com.example.shop.orders:type=Queue,name=outbox
com.example.shop.orders:type=WorkerPool,name=delivery
com.example.shop.payments:type=ConnectionPool,name=primary
\`\`\`

If recording environment within the same server is needed:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox,env=prod
\`\`\`

An internal convention might specify:

1. Domains use \`com.example.shop.<module>\`, lowercase, with module taken from an official list.
2. The \`type\` key describes the resource category in PascalCase (\`Cache\`, \`Queue\`, \`ConnectionPool\`).
3. The \`name\` key describes a stable logical name; never derived from a random ID or timestamp.
4. The \`instance\` key appears only when multiple resources with the same \`type\` and \`name\` coexist in one MBeanServer.
5. The \`env\` key appears only when distinguishing environments inside the ObjectName is genuinely necessary; its value comes from validated deployment configuration.
6. Never put passwords, tokens, card numbers, customer emails, or sensitive data into domains or key properties.

The **list of module values** must be standardized at the product level. If \`checkout\` is renamed to \`payments\`, treat it as a JMX identity contract change and plan corresponding client migrations.

## 10. Java: Building ObjectNames from Configuration

Example of a centralized naming factory, avoiding ad-hoc string concatenation in every module.

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import java.util.Hashtable;
import java.util.Set;

public final class ShopJmxNames {
    private static final String ROOT_DOMAIN = "com.example.shop";
    private static final Set<String> MODULES =
            Set.of("catalog", "orders", "payments");

    private ShopJmxNames() {}

    public static ObjectName forResource(
            String module,
            String type,
            String logicalName) throws MalformedObjectNameException {

        if (!MODULES.contains(module)) {
            throw new IllegalArgumentException(
                    "Unsupported JMX module: " + module);
        }

        Hashtable<String, String> keys = new Hashtable<>();
        keys.put("type", requireSafeValue(type));
        keys.put("name", requireSafeValue(logicalName));

        ObjectName result = new ObjectName(
                ROOT_DOMAIN + "." + module, keys);

        if (result.isPattern()) {
            throw new IllegalArgumentException(
                    "Registration name must be concrete");
        }
        return result;
    }

    private static String requireSafeValue(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "JMX key value must not be blank");
        }

        // Simple convention for controlled logical names.
        if (!value.matches("[A-Za-z0-9_.-]+")) {
            throw new IllegalArgumentException(
                    "Unsupported JMX key characters: " + value);
        }
        return value;
    }
}
\`\`\`

Usage:

\`\`\`java
ObjectName queueName = ShopJmxNames.forResource(
        "orders", "Queue", "outbox");

System.out.println(queueName.getCanonicalName());
// com.example.shop.orders:name=outbox,type=Queue
\`\`\`

Why use an allowlist in the example? In an ObjectName, \`,\`, \`=\`, \`:\`, \`*\`, \`?\`, and other special characters have syntactic or pattern roles. Values from arbitrary configuration need careful handling. If you want to support user-facing names containing special characters, you can use \`ObjectName.quote()\` and appropriate handling, while still checking \`isPattern()\` before registration.

The factory above chooses a **restrictive convention** instead of supporting arbitrary Unicode strings; that is a design choice for the example, not a universal Java JMX limitation.

## 11. Registering an MBean with the Chosen Domain

Suppose there is a Standard MBean managing a queue:

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
    void pause();
}

public class QueueMonitor implements QueueMonitorMBean {
    private int pendingCount = 5;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void pause() {
        // Pause the queue per application logic.
    }
}
\`\`\`

Registering with the platform MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName objectName =
        ShopJmxNames.forResource("orders", "Queue", "outbox");

server.registerMBean(new QueueMonitor(), objectName);

try {
    Object pending =
            server.getAttribute(objectName, "PendingCount");
    System.out.println("Pending: " + pending);
} finally {
    server.unregisterMBean(objectName);
}
\`\`\`

In a long-running program, do not unregister immediately after reading an attribute; tie unregistration to the component's shutdown lifecycle. If the name is already in use, \`registerMBean()\` throws \`InstanceAlreadyExistsException\`. The factory only ensures consistent naming; **it does not by itself prevent two objects from registering under the same ObjectName**.

## 12. Filtering by Product, Module, and Environment

You can use an \`ObjectName\` pattern in \`MBeanServer.queryNames()\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

// Find Queues across all modules belonging to the Shop product.
ObjectName allShopQueues = new ObjectName(
        "com.example.shop.*:type=Queue,*");

Set<ObjectName> result =
        server.queryNames(allShopQueues, null);

result.stream()
        .map(ObjectName::getCanonicalName)
        .sorted()
        .forEach(System.out::println);
\`\`\`

When \`env\` is a key property:

\`\`\`java
ObjectName prodQueues = new ObjectName(
        "com.example.shop.*:type=Queue,env=prod,*");

Set<ObjectName> prod = server.queryNames(prodQueues, null);
\`\`\`

When \`env\` is in the domain:

\`\`\`java
ObjectName prodDomainQueues = new ObjectName(
        "com.example.shop.prod.*:type=Queue,*");
\`\`\`

The \`,*\` suffix is crucial: it allows names to have additional key properties beyond those listed in the pattern.

### Domain Pattern Pitfall

If a product mixes:

\`\`\`text
com.example.shop:type=Cache,name=root
com.example.shop.orders:type=Queue,name=outbox
\`\`\`

then the pattern:

\`\`\`text
com.example.shop.*:*
\`\`\`

only matches domains starting with \`com.example.shop.\` and excludes the exact domain \`com.example.shop\`. If you need to list both forms, write appropriate queries for each group or standardize domains from the start. Do not assume dots imply parent/child relationships handled automatically by the API.

### Pitfall When Environment Lives Outside the MBeanServer

An MBeanServer in a \`prod\` JVM will not automatically return MBeans from a \`staging\` JVM even with the pattern \`env=*\`. \`queryNames\` queries only the **currently connected server**. Querying across a cluster or across environments is the responsibility of a collector that connects to multiple JVMs.

## 13. Spring Framework: Using Consistent Domains When Exporting

Spring Framework supports exporting beans to JMX via \`MBeanExporter\` and annotations such as \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\`.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.shop.orders:type=Queue,name=outbox",
        description = "Order outbox monitor")
public class OrderOutboxManagement {

    private volatile int pendingCount;

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }
}
\`\`\`

\`@ManagedResource.objectName\` specifies the expected JMX name. For the MBean to appear, the object must be managed and exported by an appropriate Spring JMX mechanism. Simply adding the annotation to a class does not guarantee MBean registration in every Spring context.

### Configuration-Driven Dynamic Names

Some projects require environment-dependent domains or keys. Avoid hardcoding \`prod\` in classes reused across staging and dev. Instead, configure a single place to construct ObjectNames or a naming strategy and supply deployment info at registration time.

With Spring \`MBeanExporter\`, you can map explicit ObjectNames during configuration:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    MBeanExporter queueExporter(QueueMonitor queueMonitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
                "com.example.shop.orders:type=Queue,name=outbox",
                queueMonitor));
        return exporter;
    }
}
\`\`\`

This example assumes a \`QueueMonitor\` bean is defined elsewhere and implements the Standard MBean interface \`QueueMonitorMBean\`. In a real application, use only one export mechanism for the same ObjectName to avoid double registration. Spring manages registration and lifecycle, but conflicts between exporters or manual MBeans still must be controlled.

To derive the domain from configuration, you can read values from \`@ConfigurationProperties\` or \`Environment\`, validate the module/environment list, and then construct the name with a factory before registration. Never concatenate arbitrary deployment data into an ObjectName while skipping syntax validation.

## 14. Designing for Multiple Instances and Multiple JVMs

A frequent question: "If I run three replicas of the same service, must I add \`instance\` to the ObjectName?"

The answer depends on the **MBeanServer** scope:

- If each replica is a separate JVM, each replica has its own platform MBeanServer; registering the same ObjectName in each JVM is completely normal.
- If **within the same JVM/MBeanServer** there are multiple queue monitors with the same \`type\` and \`name\`, you must have a distinguishing key such as \`instance\`.
- When monitoring aggregates metrics from multiple JVMs, external identity also includes target/connection/instance metadata and should not rely solely on ObjectName.

Example of two queue instances in the same JVM:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox,instance=primary
com.example.shop.orders:type=Queue,name=outbox,instance=retry
\`\`\`

Example of two replicas in separate JVMs both having:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox
\`\`\`

There is no registration collision because they belong to two different MBeanServers.

**Avoid putting random pod IDs into the domain by default.** If a pod ID is only deployment metadata, embedding it in the name makes the ObjectName change on every rollout, which can break dashboards using static names. If a single JVM genuinely holds multiple instances that need distinction, an \`instance\` key may be more appropriate. Choose dynamic IDs only when your observability workflow is explicitly designed to handle that identity.

## 15. Domains and Operational Contract Stability

An ObjectName is part of the **operational contract** between the application and monitoring tools. Changing a domain can impact:

- JConsole/JMC or JMX tools looking up MBeans by a fixed domain.
- Dashboards, alert rules, and exporters selecting metrics based on ObjectName.
- Admin scripts calling \`MBeanServer.getAttribute\`, \`invoke\`, or \`queryNames\`.
- Operational runbooks and incident response procedures.

For example:

\`\`\`text
Old name:
com.example.shop.orders:type=Queue,name=outbox

New name:
com.example.shop.fulfillment:type=Queue,name=outbox
\`\`\`

Even if the Java class name or operations do not change, clients using the old ObjectName will not automatically find the new name.

### Name Migration Procedure

1. Inventory existing ObjectNames and the clients using them.
2. Choose the new naming convention and document the reason for the change.
3. Update queries/dashboards so they understand the new name.
4. When appropriate, use a controlled transition period; consider registering an alias MBean or exporting in parallel through a separate management layer, if the deployment design allows it without conflict.
5. Verify queries and alerts after rollout, then remove the old name path once no consumers remain.

Registering a single **MBean instance** under multiple ObjectNames can be affected by implementation lifecycle and registration rules; do not assume aliasing is available for every MBean. It is better to treat a naming change as a contract change and test it in a suitable environment before rollout.

## 16. Common Mistakes

| Issue | Why It Happens | How to Avoid It |
|---|---|---|
| Overly generic domain like \`app\` | Multiple libraries/modules share the same namespace | Use an organization/product prefix |
| Domain contains \`impl\` package details | Java refactoring changes management names | Name after stable logical modules |
| Same product mixes \`order\` and \`orders\` | Inconsistent conventions | Standardize the module catalog |
| Hardcoding \`prod\` in source code | Not reusable across environments | Use configuration or collector metadata |
| Adding \`env\` out of fear of cross-JVM collisions | Misunderstanding ObjectName uniqueness scope | Remember identity is scoped per MBeanServer |
| Querying subdomains misses root domain | Pattern \`com.example.shop.*\` only matches dotted prefixes | Separate queries or normalize naming |
| \`MalformedObjectNameException\` | Unhandled syntax characters | Validate/encode domain and key values |
| \`InstanceAlreadyExistsException\` | Two MBeans share domain + key properties in one server | Add a distinguishing key or fix lifecycle |
| Dashboards lose metrics after domain rename | Clients look up the old ObjectName | Migrate and update queries/alerts |
| Name contains customer info | ObjectNames may appear in admin tools/logs | Keep secrets/PII out of identity |

## 17. Practice

### Exercise 1 — Designing Domains for a Product

A \`learning\` product has modules \`course\`, \`enrollment\`, and \`notification\`. Assign ObjectNames for:

- Course list cache.
- Notification email queue.
- Counter of in-progress enrollments.

A reference solution:

\`\`\`text
com.example.learning.course:type=Cache,name=courseList
com.example.learning.notification:type=Queue,name=email
com.example.learning.enrollment:type=Counter,name=inProgress
\`\`\`

Explain the reasoning behind using a module-based domain and a resource-based \`name\` key.

### Exercise 2 — Comparing Environment Models

Given two naming approaches:

\`\`\`text
com.example.shop.prod.orders:type=Queue,name=outbox
com.example.shop.orders:type=Queue,name=outbox,env=prod
\`\`\`

Write a query selecting \`prod\` queues for each model and explain why the two queries are not interchangeable.

Reference answers:

\`\`\`text
com.example.shop.prod.*:type=Queue,*
com.example.shop.*:type=Queue,env=prod,*
\`\`\`

The first pattern assumes \`prod\` is in the domain; the second assumes \`env\` is a key. Both search only the MBeanServer that the client is querying.

### Exercise 3 — Detecting Name Collisions

A JVM registers:

\`\`\`text
com.example.shop.orders:type=Queue,name=outbox
com.example.shop.orders:type=Queue,name=outbox
\`\`\`

The second registration will fail if the first name still exists. Propose \`instance=primary\` and \`instance=retry\` if there are genuinely two independent queues with the same logical name.

### Exercise 4 — Designing a Factory

Write an \`ObjectNameFactory\` with three parameters: \`module\`, \`type\`, and \`name\`. Rules:

- Root domain: \`com.example.shop\`.
- Valid modules: \`orders\`, \`payments\`, \`catalog\`.
- Keys \`type\` and \`name\` must not be blank.
- If a value contains special characters, reject or encode it intentionally.
- After constructing the name, verify \`isPattern() == false\`.

Create 3 ObjectNames and print \`getCanonicalName()\`; explain why the printed key order may differ from the declaration order.

### Exercise 5 — Planning a Domain Rename

An application renames the \`orders\` module to \`fulfillment\`. Describe the artifacts outside Java code that must be checked: dashboards, JMX exporters, alerts, scripts, operational docs, and consumers using static ObjectNames.

## 18. Self-Check Questions

**1. Is it mandatory to add the environment to the domain so JMX names are unique across a cluster?**

No. Uniqueness of an ObjectName at registration is scoped to a single MBeanServer. A cluster has multiple independent JVMs and MBeanServers.

**2. Must the domain \`com.example.shop.orders\` be a real Java package?**

No. It can be a logical name by convention, without needing to match a package.

**3. Does \`com.example.shop.*:type=Queue,*\` match MBeans in the \`com.example.shop\` domain?**

No, because the pattern requires the prefix \`com.example.shop.\`.

**4. When should the environment be an \`env\` key?**

When you need to distinguish or filter environments directly within the ObjectName in the same management context, and the organization has agreed on that convention.

**5. If you change the domain while keeping all keys the same, is it still the same ObjectName?**

No. The domain is part of the identity.

**6. Do different domains isolate JMX permissions?**

No. Access control resides in the security mechanisms and connection/MBeanServer management.

## 19. Key Takeaways

- The domain is a **logical namespace** in \`ObjectName\`, and should reflect products and modules with a readable, stable convention.
- Splitting by product or module is an operational architecture decision; there is no single mandatory JMX hierarchy.
- Environment can live in the domain, in a key property, or in metadata outside JMX; choose based on query needs and MBeanServer scope.
- The same ObjectName can exist in different JVMs; within the same MBeanServer, two MBeans cannot be registered concurrently under the same concrete name.
- Domain querying is **string pattern matching**, with no awareness of a directory tree; do not overlook the dot in a domain prefix.
- Naming conventions should be backed by a consistent factory/configuration, rules against dynamic names, and a migration plan if domains change.
- Never put sensitive information in an ObjectName; domains are not authorization boundaries either.

## 20. References

- Java SE 21 API — \`javax.management.ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Oracle JMX Tutorial: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
