# Dedicated Domains and Avoiding Cross-Application MBean Mixing in Spring JMX

## Objectives

After this lesson, you will be able to design a JMX namespace for Spring applications, distinguish a **JMX domain** from a **dedicated MBeanServer**, decide when to use the platform MBeanServer versus a custom MBeanServer, configure `MBeanExporter` to register into the right server, and verify the separation of MBeans across multiple applications or modules to avoid name collisions and operational confusion.

## 1. The Problem When Multiple Applications Share JMX Infrastructure

A single JVM can have multiple Spring `ApplicationContext` instances, multiple libraries, and multiple modules exporting MBeans. These objects are often registered into a single `MBeanServer`.

Example:

```text
JVM
  |
  +-- ApplicationContext: billing
  |     +-- BillingQueueMonitor
  |     +-- BillingCacheMonitor
  |
  +-- ApplicationContext: inventory
  |     +-- InventoryQueueMonitor
  |     +-- InventoryCacheMonitor
  |
  +-- JVM built-in management MBeans
        +-- java.lang:type=Memory
        +-- java.lang:type=Threading
```

If every module arbitrarily uses a name like `app:type=Queue,name=Main`, two groups of risks can arise:

1. **Technical collisions:** two MBeans attempt to use the same ObjectName in the same MBeanServer, causing `InstanceAlreadyExistsException` or triggering another registration policy.
2. **Operational confusion:** clients or scripts cannot tell which application an MBean belongs to, leading to reading the wrong metrics or invoking operations on the wrong target.

The problem of "avoiding mixing" is not just about preventing startup errors, but also about designing **boundaries of identity, ownership, and observability**.

## 2. What is a JMX Domain?

A `javax.management.ObjectName` has the structure:

```text
domain:key=value[,key=value...]
```

Example:

```text
com.example.billing:type=Queue,name=Payment
com.example.inventory:type=Queue,name=StockSync
java.lang:type=Memory
```

The domain is the part before the `:`. It serves as the namespace for the MBean.

In the example above:

| ObjectName | Domain | Resource |
| --- | --- | --- |
| `com.example.billing:type=Queue,name=Payment` | `com.example.billing` | Payment queue |
| `com.example.inventory:type=Queue,name=StockSync` | `com.example.inventory` | Stock synchronization queue |
| `java.lang:type=Memory` | `java.lang` | JVM memory |

A dedicated domain helps clients:

- Group MBeans belonging to the same application or module.
- Query MBeans accurately using an `ObjectName` pattern.
- Reduce the risk of two modules picking identical names.
- Easily build dashboards, scripts, and monitoring rules per namespace.
- Distinguish application MBeans from standard JVM and library MBeans.

**A domain is not an isolated security container.** Two different domains can still belong to the same MBeanServer and be accessed through the same JMX connection if the client has permissions.

## 3. How Does a Dedicated Domain Differ from a Dedicated MBeanServer?

This is the most important distinction.

### Dedicated Domains in the Same MBeanServer

```text
Platform MBeanServer
  |
  +-- java.lang:type=Memory
  +-- com.example.billing:type=Queue,name=Payment
  +-- com.example.inventory:type=Queue,name=StockSync
```

ObjectNames have different domains yet coexist on one server.

Benefits:

- Easy to observe the entire JVM through a single JMX connection.
- No need for additional MBeanServers or connectors.
- Familiar tools such as JConsole/JMC can typically view application MBeans when they use the platform MBeanServer.
- Easy to group by domain.

Limitations:

- Clients with access to the whole server can still see MBeans from multiple applications.
- Names within the same server must be unique.
- A domain does not guarantee that one module cannot query or invoke MBeans of another module.

### Dedicated MBeanServers

```text
JVM
  |
  +-- Platform MBeanServer
  |     +-- java.lang:*
  |
  +-- Billing MBeanServer
  |     +-- com.example.billing:*
  |
  +-- Inventory MBeanServer
        +-- com.example.inventory:*
```

A dedicated MBeanServer creates an independent JMX registry. The same ObjectName can appear in two different servers without colliding because uniqueness is checked **within each server**.

Benefits:

- Separates registration namespaces at the server level.
- Controls registry lifecycle per module/context.
- Can build separate connectors/access policies when appropriate infrastructure is designed.

Limitations:

- JConsole/JMC connecting to the platform MBeanServer will not necessarily see MBeans in a dedicated server automatically.
- Must precisely manage which server exporters and clients are using.
- Creating multiple servers/connectors increases operational complexity.
- Separating servers does not automatically create security: access depends on connector, authentication, authorization, and network configuration.

**Rule:** a dedicated domain is a way to organize names within one registry; a dedicated MBeanServer is a way to separate registries. Do not confuse the two concepts.

## 4. How Should You Choose a Domain?

A simple naming convention:

```text
<organization>.<application>[.<module>]:type=<type>,name=<logical-name>
```

Example:

```text
com.acme.billing:type=Cache,name=TaxRate
com.acme.billing:type=Queue,name=Invoices
com.acme.inventory:type=Queue,name=Replenishment
com.acme.inventory:type=WorkerPool,name=StockSync
```

Guidelines:

- Use a namespace with clear ownership, such as your organization's reverse-DNS.
- Include the application/module name in the domain when separation is needed.
- Use `type` to categorize the resource; `name` to identify the logical resource.
- If a JVM has multiple instances of the same module, add a stable, meaningful key property.
- Do not put PIDs, per-run generated UUIDs, or startup timestamps into the ObjectName of a stable logical resource.
- Do not use JVM domains like `java.lang` for arbitrary application MBeans.
- Do not rely on domains as a mechanism for hiding resources or granting permissions.

The name `com.acme.billing:type=Queue,name=Invoices` should retain the same meaning across restarts, even if the implementation class changes.

## 5. ObjectName and Uniqueness Within the Same Server

These two ObjectNames have different domains so they do not collide:

```text
com.acme.billing:type=Queue,name=Main
com.acme.inventory:type=Queue,name=Main
```

However, these two strings represent the exact same name:

```text
com.acme.billing:type=Queue,name=Main
com.acme.billing:name=Main,type=Queue
```

Key property order does not create a new identity.

```java
import javax.management.ObjectName;

ObjectName first = new ObjectName(
    "com.acme.billing:type=Queue,name=Main"
);
ObjectName second = new ObjectName(
    "com.acme.billing:name=Main,type=Queue"
);

System.out.println(first.equals(second)); // true
```

Therefore, collision checks should not rely solely on raw string comparison. Use `ObjectName.equals()` or `getCanonicalName()` when checking names.

Within the same server, `MBeanServer.registerMBean` can throw `InstanceAlreadyExistsException` on duplicate registration attempts. A dedicated domain reduces collision likelihood but does not replace full name management.

## 6. Designing with the Platform MBeanServer

In many Spring applications running in a single JVM, using the **platform MBeanServer** with a dedicated domain per module is the simplest choice.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer platform =
        ManagementFactory.getPlatformMBeanServer();
```

With this setup, standard JVM MBeans and application MBeans are registered together in one server; clients observing the JVM can access them by their respective domains.

### Standard MBean Example

```java
package com.example.billing.jmx;

public interface BillingQueueMonitorMBean {
    int getPendingJobs();
}
```

```java
package com.example.billing.jmx;

public final class BillingQueueMonitor
        implements BillingQueueMonitorMBean {

    @Override
    public int getPendingJobs() {
        return 12;
    }
}
```

Registering under the billing domain:

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.billing:type=Queue,name=Invoices"
);

platform.registerMBean(new BillingQueueMonitor(), name);
```

Direct registration in the snippet above is for illustration only. In a Spring application, let `MBeanExporter` manage the lifecycle to avoid scattered register/unregister calls in code.

## 7. Configuring Spring MBeanExporter with a Dedicated Domain

Java-based configuration:

```java
package com.example.billing.config;

import com.example.billing.jmx.BillingQueueMonitor;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class BillingJmxConfiguration {

    @Bean
    public BillingQueueMonitor billingQueueMonitor() {
        return new BillingQueueMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter billingExporter(
            BillingQueueMonitor monitor,
            MBeanServer platformMBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.billing:type=Queue,name=Invoices",
            monitor
        ));
        return exporter;
    }
}
```

Here, the `com.example.billing` domain is part of the ObjectName in the `beans` map. `setServer` selects the target registry. These two decisions are independent: you can change the domain while keeping the same server, or use the same domain on two different servers.

If another `MBeanExporter` is autodetecting the same bean, remove the duplicate configuration or define clear ownership.

## 8. Configuring a Custom MBeanServer

When there is a valid reason to separate registries, Spring supports connecting an exporter to an application-created MBeanServer.

Spring Java configuration example:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class IsolatedJmxServerConfiguration {

    @Bean
    public MBeanServer billingMBeanServer() {
        return MBeanServerFactory.newMBeanServer(
            "com.example.billing.management"
        );
    }
}
```

`newMBeanServer` creates a new server not included in the list managed by `MBeanServerFactory.findMBeanServer`. For applications needing JMX's server discovery mechanism to find the server, consider `createMBeanServer` and manage lifecycle/release appropriately. Either way, clients must know the exact endpoint serving this registry.

Exporter attached to the dedicated server:

```java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;

@Bean
public MBeanExporter billingExporter(
        BillingQueueMonitor monitor,
        @Qualifier("billingMBeanServer") MBeanServer server) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(
        "com.example.billing:type=Queue,name=Invoices",
        monitor
    ));
    return exporter;
}
```

**Important:** creating a dedicated server does not automatically create a remote JMX connector. If remote clients are needed, an appropriate management endpoint must be published and security configured for the connector; JConsole/JMC connecting to the default JVM is not guaranteed to see the new server.

## 9. Domain Separation Is Not Security Separation

A common misconception:

> If the billing MBean is in `com.example.billing` and the inventory MBean is in `com.example.inventory`, a billing client will not be able to invoke the inventory MBean.

That is **false** if both are in the same MBeanServer and the client has server-wide permissions. A domain is a naming structure, not an access-control list.

To achieve security boundaries, design:

- Authentication when connecting to JMX, especially over a remote connector.
- Authorization for read/write/invoke operations with appropriate permissions.
- Network restrictions, TLS, and policy-compliant secret management.
- Small MBean interfaces exposing only necessary state and operations.
- Connecting to the right MBeanServer/connector, if deploying multiple servers.
- Auditing for operations with side effects.

Also do not assume a dedicated server already provides isolation equivalent to a process or classloader: objects in the same JVM still share process resources and are affected by other code and security decisions.

## 10. When Should You Split into Multiple MBeanServers?

You might consider a dedicated server if:

1. One JVM embeds multiple independent applications needing different registry lifecycles.
2. There is a plugin/multi-tenant system in one process with a clear management mechanism.
3. A subsystem needs to actively publish its registry over a dedicated connector.
4. You need to isolate registration names or avoid application modules depending on a global registry.
5. Frameworks maintain their own server registries per established architecture.

However, you **should not** create a dedicated server merely to make the MBean Browser screen have fewer entries. Proper domains and good naming conventions are usually enough.

A dedicated server increases configuration, discovery, connector, monitoring, and testing overhead. For typical Spring Boot or Spring Framework applications, the platform MBeanServer + dedicated domains is the easier model to operate.

## 11. Dedicated Domains and Annotation-Driven Export Configuration

If the project uses `@ManagedResource`:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.billing:type=Queue,name=Invoices",
    description = "Billing invoice queue monitor"
)
public class AnnotatedBillingMonitor {

    @ManagedAttribute
    public int getPendingJobs() {
        return 12;
    }
}
```

and enables the exporter with:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxAnnotationConfiguration {
}
```

The annotation can explicitly specify the ObjectName, including domain and key properties. However, **actual registration** still depends on the exporter and the MBeanServer that the exporter uses.

Applications with multiple contexts/beans must agree on conventions so two MBeans with the same ObjectName are not produced in the same server. A single `@ManagedResource` on a class does not guarantee unique names if multiple instances share fixed name metadata.

For multiple instances, a naming strategy or separate management adapters can be used to produce names with distinct logical values.

## 12. Inspecting Domains with queryNames

`MBeanServer` supports querying `ObjectName` patterns.

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> billing = server.queryNames(
    new ObjectName("com.example.billing:*"), null
);

for (ObjectName name : billing) {
    System.out.println(name.getCanonicalName());
}
```

The pattern `com.example.billing:*` only matches MBeans with domain `com.example.billing`. If you use subdomains such as `com.example.billing.cache`, that pattern **does not** automatically expand to all subdomains. You can design patterns matching JMX syntax to query the needed domains, or standardize on one domain with a `module` key for easier querying.

Example:

```text
com.example.billing:type=Cache,name=TaxRate,module=Pricing
com.example.billing:type=Queue,name=Invoices,module=Settlement
```

Then you can query by key property such as:

```java
server.queryNames(
    new ObjectName("com.example.billing:module=Pricing,*"),
    null
);
```

This is a way to group by module **within the same domain**.

Do not use overly broad patterns when invoking state-mutating operations: retrieve the list, verify each exact ObjectName, and then act.

## 13. Reading Managed Domains

To view the domains currently present in an MBeanServer:

```java
String[] domains = server.getDomains();

for (String domain : domains) {
    System.out.println(domain);
}
```

Distinguish clearly:

- `getDomains()` reflects domains that currently have registered MBeans at the time of the call.
- A domain is not a pre-"authorized" or pre-"created" configuration.
- There is no standard API requiring you to "create domain" before registering an MBean.
- A domain can disappear from the list if no MBeans remain under that domain.

Thus, to establish an application domain, you register an MBean with an ObjectName using that domain.

## 14. Testing with a Dedicated MBeanServer

In tests, prefer `MBeanServerFactory.createMBeanServer` or `newMBeanServer` to avoid affecting running platform MBeans.

Example:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.*;
import org.junit.jupiter.api.Test;

class JmxDomainIsolationTest {

    @Test
    void separatesApplicationDomains() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("test.management");

        ObjectName billingName = new ObjectName(
            "com.example.billing:type=Queue,name=Invoices"
        );
        ObjectName inventoryName = new ObjectName(
            "com.example.inventory:type=Queue,name=StockSync"
        );

        try {
            server.registerMBean(new BillingQueueMonitor(), billingName);
            server.registerMBean(new BillingQueueMonitor(), inventoryName);

            assertTrue(server.isRegistered(billingName));
            assertTrue(server.isRegistered(inventoryName));

            assertEquals(
                1,
                server.queryNames(
                    new ObjectName("com.example.billing:*"), null
                ).size()
            );
            assertEquals(
                1,
                server.queryNames(
                    new ObjectName("com.example.inventory:*"), null
                ).size()
            );
        } finally {
            if (server.isRegistered(billingName)) {
                server.unregisterMBean(billingName);
            }
            if (server.isRegistered(inventoryName)) {
                server.unregisterMBean(inventoryName);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

For production-like tests, use two MBean implementations from their respective modules instead of reusing the same demo class as above. The test here proves that different domains allow querying the exact sets without collision.

## 15. Testing Two Independent MBeanServers

To clearly see that a domain is not a registry, create two servers:

```java
import javax.management.*;

MBeanServer billingServer =
    MBeanServerFactory.newMBeanServer("billing.management");
MBeanServer inventoryServer =
    MBeanServerFactory.newMBeanServer("inventory.management");

ObjectName sameName = new ObjectName(
    "com.example.shared:type=Health,name=Main"
);

billingServer.registerMBean(
    new BillingQueueMonitor(), sameName
);
inventoryServer.registerMBean(
    new BillingQueueMonitor(), sameName
);

System.out.println(billingServer.isRegistered(sameName));   // true
System.out.println(inventoryServer.isRegistered(sameName)); // true
```

The two registrations do not collide because they reside in two separate servers. However, using **the same ObjectName for two different resources** is a poor naming choice if a client aggregator will merge data without recording the server/endpoint.

A complete identifier in a multi-source observability system usually consists of:

```text
(target JVM / connector identity, ObjectName)
```

Do not treat an `ObjectName` on a single MBeanServer as a global identifier across all JVMs and servers.

## 16. Spring Integration Test: Exporter Registers into the Right Server

With two different servers, you can verify an exporter only registers MBeans on the configured server.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import javax.management.*;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.jmx.export.MBeanExporter;

class ExporterServerSelectionTest {
    @Test
    void exportsOnlyToConfiguredServer() throws Exception {
        MBeanServer billingServer =
                MBeanServerFactory.newMBeanServer("billing.management");
        MBeanServer otherServer =
                MBeanServerFactory.newMBeanServer("other.management");

        ObjectName name = new ObjectName(
            "com.example.billing:type=Queue,name=Invoices"
        );

        try (GenericApplicationContext context =
                new GenericApplicationContext()) {

            context.registerBean("exporter", MBeanExporter.class, () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(billingServer);
                exporter.setBeans(Map.of(
                    name.toString(), new BillingQueueMonitor()
                ));
                return exporter;
            });

            context.refresh();

            assertTrue(billingServer.isRegistered(name));
            assertFalse(otherServer.isRegistered(name));
        }
    }
}
```

The test confirms `setServer` takes effect. With configurations using `@EnableMBeanExport` or the XML namespace, tests should also verify that the exporter created by that mechanism actually selects the intended server.

If a client does not see the MBean even though `isRegistered(name)` returns true on the dedicated server, the client may be connected to the platform server or a different connector.

## 17. Preventing MBean Mixing When Using Multiple Spring Contexts

Multiple Spring contexts in one JVM can all see the platform server:

```text
Root ApplicationContext
  +-- shared infrastructure
  +-- JMX exporter A

Child ApplicationContext (billing)
  +-- billing beans
  +-- JMX exporter B

Child ApplicationContext (inventory)
  +-- inventory beans
  +-- JMX exporter C
```

Best practices:

1. Define one or more exporters with transparent ownership.
2. Specify domains/key properties for each module.
3. Avoid letting a parent exporter autodetect beans already registered by a child exporter if visibility rules permit it.
4. Use an intentional registration policy; do not let `IGNORE_EXISTING` hide the fact that clients are seeing an old MBean.
5. Ensure exporters unregister their MBeans when the context closes.
6. Verify name stability across restarts/redeploys.
7. Write an integration test creating two contexts simultaneously on a test server and checking expected `queryNames`.

If the contexts are truly independent applications with separate access/management requirements, consider separate servers or separate processes per operational architecture rather than merely changing domains.

## 18. Classloader and Lifecycle Issues

In embedded server applications or containers managing multiple applications, the following can occur:

- A module's classloader is unloaded while old MBeans remain unregistered.
- A new context tries to register an ObjectName still held by an old module.
- Clients continue reading a stale MBean or receive errors when invoking methods on the old object.
- The Spring exporter and another library both believe they own the same MBean.

These problems are not solved merely by changing the domain. Proper lifecycle teardown and registration owner checks are required.

A naming convention aids traceability. For example, the `com.example.billing` domain indicates which component should be responsible, but does not automatically unregister resources or enforce ownership.

## 19. Design and Operations Checklist

| Item | Question to Answer |
| --- | --- |
| Domain | Does the domain clearly belong to one application/module? |
| ObjectName | Are `type`, `name`, or appropriate logical distinguishing keys present? |
| Stability | Does the ObjectName stay the same across restarts of the same resource? |
| Registry | Does the exporter use the platform server or a dedicated MBeanServer? |
| Client | Is JConsole/JMC/monitoring agent connected to the right server? |
| Ownership | Who registers, who unregisters, and when? |
| Collision | Is another exporter registering the same canonical ObjectName? |
| Security | Who has read/write/invoke permissions; is domain being mistaken for an ACL? |
| Multi-context | Do parent/child contexts overlap in registrations? |
| Testing | Are `queryNames`, `getMBeanInfo`, lifecycle, and server selection verified? |

## 20. Practice Exercises

1. Register two Standard MBeans into the same server with domains `com.example.billing` and `com.example.inventory`. Query each domain and confirm only the corresponding MBean is returned.
2. Attempt to register two MBeans with the same ObjectName in the same server to observe `InstanceAlreadyExistsException`.
3. Create two separate MBeanServers and register the same ObjectName; explain why there is no collision.
4. Configure `MBeanExporter.setServer` to use a dedicated server and verify the MBean does not appear in the platform server.
5. Use `@ManagedResource` to publish an MBean under a business domain with a stable name.
6. Write an integration test running two Spring contexts sharing an MBeanServer with separate domains; verify lifecycle when closing each context.
7. In JConsole/JMC, connect to the right JVM and find the application domain. Explain why an MBean on a custom server might not be displayed.
8. Design a naming convention for three modules—Billing, Inventory, Shipping—and specify keys to distinguish resources.

## 21. Self-Check Questions

- Is a JMX domain a separate MBeanServer?
- Does a domain automatically create access permissions or security isolation?
- Is an ObjectName unique across different MBeanServers?
- Why are the platform MBeanServer and dedicated domains usually sufficient for a typical Spring application?
- What happens if the exporter registers into a different server than the one the client is connected to?
- Does `getDomains()` mean "authorized domains" or "domains currently having MBeans"?
- When an application redeploys and hits a duplicate ObjectName, is changing the domain always the right solution?
- Why must both target JVM/connector identity and ObjectName be identified when monitoring multiple JVMs?

**Key takeaway:** **Dedicated domains** organize and distinguish MBeans within the same MBeanServer; **dedicated MBeanServers** create independent management registries. The two mechanisms serve different goals. In Spring JMX, set domains by application/module, select the right server for `MBeanExporter`, control ownership and lifecycle, verify with `queryNames` and `isRegistered`, and never confuse namespaces with security.