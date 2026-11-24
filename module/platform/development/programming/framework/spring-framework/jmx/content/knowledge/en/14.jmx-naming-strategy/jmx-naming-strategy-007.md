# Ensuring Consistent JMX Names Between Local and Remote

## 1. Problem and Objective

In Spring Framework JMX, each MBean is registered in an **MBeanServer** using an **ObjectName**. Local or remote clients wanting to access the right MBean all need to know that ObjectName. A small change in domain, key properties, or naming rules can prevent JConsole, scripts, dashboards, and operational tools from finding the resource.

For example, an application exports an MBean:

```text
com.example.orders:type=Queue,application=checkout,name=payments
```

On a developer machine, a local tool can read this MBean. When deployed to another host, a remote client queries:

```text
com.example.orders:type=Queue,name=payments
```

The two strings above **are not the same ObjectName**, because the first has an extra key `application=checkout`. Having the client connect to the right JVM does not make two different names equivalent.

This lesson presents how to design a **stable naming strategy** so the Spring application and all JMX clients share the same naming contract, while separating MBean identity from per-environment connection details.

## 2. Local and Remote Use the Same JMX Identity Model

Overall architecture:

```text
Spring application / JVM
       |
       +-- Bean: PaymentQueueManagement
       |
       +-- MBeanExporter
               |
               +-- ObjectNamingStrategy
               |       |
               |       v
               |   ObjectName
               |
               v
           MBeanServer
             ^      ^
             |      |
       local client remote JMX connector
             |      |
          JConsole   remote script/dashboard
```

`MBeanServer` uses the same ObjectName to look up an MBean, regardless of whether the call comes from an in-JVM client or through a remote connector. The difference between local and remote lies mainly in **how the connection to `MBeanServer` is obtained**:

- **Local/in-process:** the application can use `MBeanServer` directly.
- **Remote:** clients use `JMXConnector` and `MBeanServerConnection`.
- **MBean identity:** remains the ObjectName registered in the target `MBeanServer`.

Being on another machine does not mean you must change the domain or add the host into the ObjectName. Host, port, authentication, and TLS belong to **connection configuration**. The resource name belongs to **management identity**.

## 3. What Does an ObjectName Consist Of?

General syntax:

```text
domain:key1=value1,key2=value2,...
```

Example:

```text
com.example.orders:type=Queue,application=checkout,name=payments
```

| Component | Example Value | Purpose |
| --- | --- | --- |
| Domain | `com.example.orders` | Namespace grouping MBeans |
| `type` | `Queue` | Resource type |
| `application` | `checkout` | Owning service or application |
| `name` | `payments` | Logical resource identifier |

**Identity rule:** domain and the set of key properties determine the ObjectName. Key property ordering does not determine equality.

The following two strings represent the same name:

```text
com.example.orders:type=Queue,application=checkout,name=payments
com.example.orders:name=payments,type=Queue,application=checkout
```

However, the following strings are different names:

```text
com.example.orders:type=Queue,application=checkout,name=payments
com.example.orders:type=Queue,application=inventory,name=payments
com.example.orders:type=Queue,name=payments
com.example.orders:type=Queue,application=checkout,name=shipping
```

When debugging, log `ObjectName.getCanonicalName()` to normalize key order and avoid raw string comparisons that differ only in order.

## 4. Agreeing on the Naming Contract Before Configuring Connections

A naming contract suitable for many applications could be:

```text
domain = com.example.<subsystem>

type        = logical resource type
application = stable application identifier
name        = stable resource identifier
```

Examples:

```text
com.example.orders:type=Queue,application=checkout,name=payments
com.example.orders:type=Queue,application=checkout,name=shipping
com.example.orders:type=Scheduler,application=checkout,name=background
com.example.inventory:type=Cache,application=inventory,name=products
```

This convention should be used consistently by:

1. The bean exporter creating ObjectNames.
2. Java clients using `ObjectName` to read attributes/invoke operations.
3. Operational scripts and dashboards needing exact queries.
4. Integration tests verifying the registry.
5. Documentation and operational runbooks.

**Do not duplicate naming logic via hand-written strings in many places** if a shared schema or helper can be used. If clients are in different languages, publish the ObjectName schema as a documented/tested contract.

### Fields That Should Not Be Put in Names When Unnecessary

- Hostnames or IPs that change across deployments.
- JMX remote ports.
- Random UUIDs regenerated on every startup.
- Short-lived container IDs.
- Request IDs or user IDs creating high-churn MBeans.
- Proxy class names generated by Spring AOP.
- Startup times or build timestamps.

These values make ObjectNames unstable and easily break queries and dashboards. If two instances live in **two different JVMs**, they normally have separate `MBeanServer`s and can use the same ObjectName. Distinguishing instances is done at the **monitoring target** layer.

## 5. Distinguishing ObjectName from JVM/Instance Identity

Suppose a service runs on three nodes:

```text
node-a:9010  -> com.example.orders:type=Queue,application=checkout,name=payments
node-b:9010  -> com.example.orders:type=Queue,application=checkout,name=payments
node-c:9010  -> com.example.orders:type=Queue,application=checkout,name=payments
```

This is a valid design when the three JVMs have separate `MBeanServer`s. To identify data in a monitoring system:

```text
target=node-a, ObjectName=...name=payments
target=node-b, ObjectName=...name=payments
target=node-c, ObjectName=...name=payments
```

If a collector merges data without keeping target labels, metrics across replicas can get mixed. That is a **collection-source identification** bug, not an ObjectName conflict in `MBeanServer`.

Only add `instance` to ObjectNames when you genuinely need to distinguish multiple logical instances **within the same `MBeanServer`** or when the management schema intentionally prescribes it. When added, the `instance` value should be stable over the resource's lifecycle and role.

### Two Layers of Identity

```text
Management target:
  cluster / environment / host / process / connector URL

Management resource:
  JMX ObjectName in the connected MBeanServer
```

Do not use host/port to identify the resource type, and do not expect the ObjectName itself to carry network routing details.

## 6. How Does Spring ObjectNamingStrategy Work?

Spring Framework provides the **`ObjectNamingStrategy`** interface to create ObjectNames for beans exported via `MBeanExporter`.

Related mechanisms can include:

- **`MetadataNamingStrategy`**: uses JMX metadata and fallback naming to build ObjectNames.
- **`KeyNamingStrategy`**: uses name mappings based on bean keys/configuration.
- **Custom `ObjectNamingStrategy`**: the application enforces its own naming contract.

An important issue is that annotations can declare a fixed ObjectName:

```java
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments"
)
public class PaymentQueueManagement {
}
```

If a new target schema requires `application=checkout`, beans still using the old annotation name will drift from the contract. When switching to a shared strategy, determine the prevailing naming source: annotation, explicit mapping, or naming strategy, according to the actual exporter.

Do not let two different name-generation mechanisms operate arbitrarily within the same application.

## 7. Example: Building ObjectNames from Stable Logical Identifiers

A Java helper standardizes how names are constructed:

```java
package com.example.management;

import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import java.util.Hashtable;

public final class ManagementNames {

    private ManagementNames() {
    }

    public static ObjectName queue(
            String application,
            String resourceName
    ) throws MalformedObjectNameException {
        Hashtable<String, String> properties = new Hashtable<>();
        properties.put("type", "Queue");
        properties.put("application", application);
        properties.put("name", resourceName);

        return new ObjectName("com.example.orders", properties);
    }
}
```

Caller usage:

```java
ObjectName payments = ManagementNames.queue(
        "checkout",
        "payments"
);

System.out.println(payments.getCanonicalName());
```

This function keeps the domain and key names fixed, helping avoid missing `application` or changing `type` across snippets.

**Note on input data:** ObjectName has special syntax for commas, equals signs, asterisks, question marks, and double quotes. In real systems, use logical identifiers validated against a stable character set or build names with quoting/escaping per JMX rules. Do not concatenate arbitrary strings directly into ObjectName expressions.

If a property value contains special characters, verify both `ObjectName.quote(value)` and the behavior of the constructor in use; avoid double quoting or producing unintended patterns.

## 8. Example Custom ObjectNamingStrategy in Spring

Suppose the application wants to determine names from `applicationId` and `beanKey`:

```java
package com.example.management;

import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class StableObjectNamingStrategy
        implements ObjectNamingStrategy {

    private final String applicationId;

    public StableObjectNamingStrategy(String applicationId) {
        this.applicationId = applicationId;
    }

    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {
        return new ObjectName(
            "com.example.management"
              + ":type=Component"
              + ",application=" + ObjectName.quote(applicationId)
              + ",name=" + ObjectName.quote(beanKey)
        );
    }
}
```

This is a conceptual example: `type=Component` is a simple choice; in a real application, `type` should reflect a **stable business resource type**, not a proxy class name.

It can be applied to `MBeanExporter`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

import java.util.Map;

@Configuration
public class ManagementExportConfiguration {

    @Bean
    StableObjectNamingStrategy stableNamingStrategy() {
        return new StableObjectNamingStrategy("checkout");
    }

    @Bean
    MBeanExporter queueMBeanExporter(
            PaymentQueueManagement paymentQueueManagement,
            StableObjectNamingStrategy strategy
    ) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
                "payments",
                paymentQueueManagement
        ));
        exporter.setNamingStrategy(strategy);
        return exporter;
    }
}
```

`PaymentQueueManagement` is an illustrative class. In this example, `payments` is the bean key supplied by the exporter to the naming strategy. If the application has many resource types, a real strategy should receive separate resource type metadata to avoid giving every bean `type=Component`.

**Point to verify:** Depending on how the exporter handles explicit names and metadata, a key already shaped like a full ObjectName might be used directly. Thus, when you want the naming strategy to take charge, use keys per the contract and verify the actual registered ObjectName with `MBeanServer`.

## 9. Using Configuration Instead of Hard-Coding Environment Info in ObjectNames

An application configuration might have:

```properties
management.jmx.application-id=checkout
management.jmx.domain=com.example.orders

management.jmx.remote.host=127.0.0.1
management.jmx.remote.port=9010
```

The two property groups have different roles:

- `management.jmx.application-id` and `management.jmx.domain`: determine management identity.
- `management.jmx.remote.host` and `management.jmx.remote.port`: details for clients to find the endpoint, not components of the ObjectName.

The property names above are **application-defined examples**; not all properties are standard Spring Boot or Java JMX settings. Declare/bind them yourself if used in code.

If you want identical ObjectNames across local/staging/production, keep the domain, type, and logical name under the same schema. The dashboard or collector layer can add `environment`, `cluster`, and `instance` labels when scraping.

### Spring Boot Configuration

Spring Boot can control JMX export capability via properties like `spring.jmx.enabled` depending on version. However, enabling JMX and selecting domains/bean names must be checked against actual configuration, especially if the application uses Actuator or multiple exporters.

Do not infer that enabling `spring.jmx.enabled` automatically applies the custom naming strategy shown above.

## 10. Local JMX: Verifying Registered Names

Inside the application JVM, you can query `MBeanServer`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "com.example.orders:type=Queue,application=checkout,name=payments"
);

System.out.println(server.isRegistered(expected));
```

If `true`, an MBean is registered under that exact name on that server. If `false`, check:

- Is `MBeanExporter` running?
- Was the bean selected for export?
- Does the actual ObjectName differ from the schema?
- Is the exporter using the platform `MBeanServer` or a different `MBeanServer`?
- Was there a registration or name-collision error at startup?

### Listing a Domain

```java
for (ObjectName name : server.queryNames(
        new ObjectName("com.example.orders:*"),
        null)) {
    System.out.println(name.getCanonicalName());
}
```

This is how to observe the actual registry. Use canonical names when diagnosing to avoid confusion from key property ordering.

## 11. Remote JMX: Connection Changes, ObjectName Stays the Same

A remote Java client uses `JMXConnectorFactory`:

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteQueueInspector {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
        );

        try (JMXConnector connector =
                     JMXConnectorFactory.connect(url)) {
            MBeanServerConnection connection =
                    connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "com.example.orders:type=Queue,"
                    + "application=checkout,name=payments"
            );

            System.out.println(
                    "Registered: " + connection.isRegistered(name)
            );
            System.out.println(
                    "PendingCount: "
                    + connection.getAttribute(name, "PendingCount")
            );
        }
    }
}
```

The URL is only an example if the real server has enabled and secured JMX RMI on that endpoint. Java does not enable a specific JMX remote port by default.

**Note:** `JMXConnector` supports closing via `close()` and is used with try-with-resources in supporting API environments. If a specific version or connector does not support the expected `AutoCloseable` condition, call `close()` in `finally`.

For remote JMX:

- Host/port, RMI endpoint, firewall, and NAT affect connectivity.
- Authentication and TLS protect access.
- Permissions to read attributes or invoke operations may vary by client.
- ObjectNames are looked up only **after** connecting to the right target `MBeanServer`.

Do not change `ObjectName` to fix network errors; first distinguish connection errors from MBean-not-found errors.

## 12. Comparing Local and Remote Names via Canonicalization

If two tools need to cross-check identity, use:

```java
ObjectName local = new ObjectName(
    "com.example.orders:type=Queue,application=checkout,name=payments"
);

ObjectName remote = new ObjectName(
    "com.example.orders:name=payments,application=checkout,type=Queue"
);

System.out.println(local.equals(remote)); // true
```

The right way to compare is using `ObjectName.equals` or canonical names. Avoid comparing raw input strings because key order can differ.

### When Two JVMs Have the Same Name

If local and remote both use:

```text
com.example.orders:type=Queue,application=checkout,name=payments
```

that indicates a consistent schema, not that the two MBeans share state. Each JVM has its own resource. To compare data, always retain JVM/target information.

### When Local and Remote Have Different Domains

For example:

```text
Local:  com.example.dev:type=Queue,name=payments
Remote: com.example.prod:type=Queue,name=payments
```

This may be an intentional policy separating environments, but scripts using a fixed ObjectName will need environment-specific logic.

It is usually easier to maintain when keeping business domains stable and attaching environment at the monitoring layer. However, if multiple environments coexist in the same JVM/`MBeanServer` or specific namespace rules apply, environment can be included in the name under thoroughly documented rules.

## 13. The Nature of Name Collisions

**ObjectNames only need to be unique within a single `MBeanServer`.**

Two Spring beans on the same `MBeanServer` cannot register under the same name:

```text
com.example.orders:type=Queue,name=primary
```

With multiple beans, distinguishing keys are needed:

```text
com.example.orders:type=Queue,name=payments
com.example.orders:type=Queue,name=shipping
```

Multiple Spring `ApplicationContext`s in the same JVM may share the platform `MBeanServer`, so the naming contract must also account for context or application if needed.

`MBeanExporter` has registration policies such as fail, ignore, or replace; using `REPLACE_EXISTING` to mask collision errors can overwrite another component's MBean. Establish ownership and unique naming first.

### Do Not Generate Random Names to Avoid Collisions

```text
com.example.orders:type=Queue,name=payments-<random-uuid>
```

This avoids collisions within a single run but makes dashboards and scripts hard to search, while potentially masking lifecycle bugs or orphaned MBeans after reload. Choose stable logical resource identities instead of arbitrary suffixes.

## 14. Spring Proxies and Unstable Class Names

In Spring, beans can be wrapped in proxies due to transactions, security, or AOP. If a naming strategy uses:

```java
managedBean.getClass().getName()
```

then the ObjectName may contain proxy names that change across configuration or versions.

Example of a name that should not be treated as a long-term management identity:

```text
com.example.orders:type=PaymentQueueManagement$$SpringCGLIB$$0
```

Instead, use application-defined identifiers:

```text
com.example.orders:type=Queue,application=checkout,name=payments
```

Resource types and logical names should come from metadata/bean keys with a stable contract, not runtime implementation details.

## 15. Using Wildcard Queries While Keeping a Consistent Schema

Clients do not always know every MBean's exact name. JMX supports ObjectName patterns:

```text
com.example.orders:type=Queue,*
```

Java:

```java
Set<ObjectName> queues = connection.queryNames(
        new ObjectName("com.example.orders:type=Queue,*"),
        null
);
```

This pattern finds MBeans with matching domain and type, along with any other key properties.

If local and remote schemas differ:

```text
Local:  com.example.orders:type=Queue,name=payments
Remote: com.example.orders:type=Queue,application=checkout,name=payments
```

the pattern `com.example.orders:type=Queue,*` might still find both. However, clients needing the `application` value for labeling or exact queries can fail when local omits that key.

**Wildcards help discover resources; they do not replace keeping a uniform naming schema.** If clients require a fixed set of keys, every exporter must supply all of those keys.

## 16. Testing Naming Strategy Consistency

A test should confirm that the same inputs produce the same ObjectName regardless of environment.

Example:

```java
import javax.management.ObjectName;

ObjectName expected = new ObjectName(
    "com.example.orders:type=Queue,application=checkout,name=payments"
);

ObjectName actual = ManagementNames.queue(
    "checkout",
    "payments"
);

if (!expected.equals(actual)) {
    throw new AssertionError(
        "Unexpected JMX ObjectName: " + actual
    );
}
```

Testing can be expanded by category:

| Check | Goal |
| --- | --- |
| Same logical resource | Name stays stable across runs |
| Different key order | Still the same ObjectName |
| Two differently named resources | No collision |
| Two applications on one server | Distinguishing keys present |
| Different proxy classes | ObjectName does not change |
| Inputs with special characters | Does not produce malformed ObjectName |
| Local and remote | Same name schema, only connection differs |
| Application context closes | MBean unregistered per lifecycle |

### Testing the Registry

Testing only string-building helpers is not enough. The exporter might use annotations or explicit mappings instead of the intended naming strategy.

In integration tests, verify:

```java
ObjectName expected = ManagementNames.queue(
    "checkout",
    "payments"
);

if (!mbeanServer.isRegistered(expected)) {
    throw new AssertionError("Expected MBean not registered");
}
```

`mbeanServer` is the `MBeanServer` configured for the test. Also verify no unexpected names exist in the application's domain/scope.

## 17. Diagnostic Workflow When Local Works but Remote Cannot Find It

Suppose a remote client throws `InstanceNotFoundException` when reading:

```text
com.example.orders:type=Queue,name=payments
```

Investigation steps:

1. **Confirm connection:** Is the remote client connected to the right JVM?
2. **Confirm target:** Do cluster, host, PID, and JMX connector point to the right instance?
3. **List domain:** Query `com.example.orders:*` to inspect actual ObjectNames.
4. **Compare canonical names:** Check `application`, `name`, `type` keys and domain.
5. **Check exporter:** Is Spring using metadata naming, key naming, or a custom strategy?
6. **Check configuration:** Do environment variables/properties alter the domain or logical name?
7. **Check lifecycle:** Did the bean register successfully or get unregistered?
8. **Check permissions:** Does the remote client have permission to query/read that MBean?
9. **Fix at the source:** Align the naming schema and client contract rather than automatically falling back to a similar-looking MBean that may belong to another resource.

If remote cannot connect at all in the first place, the issue is transport/security; do not confuse it with a JMX naming error.

## 18. Spring Boot, Actuator, and Management Namespaces

Spring Boot can expose application and Actuator MBeans via JMX depending on configuration and dependencies. Management endpoints may use their own domain and naming conventions.

When combining them:

- Do not arbitrarily give custom MBeans the same ObjectName as framework/Actuator MBeans.
- Clearly define the domain of application MBeans.
- Inspect actual domains in `MBeanServer`.
- Distinguish settings enabling JMX from settings naming MBeans.
- If sharing a namespace, define conventions distinguishing `type`, `application`, and `name`.

Do not assume a custom `MBeanExporter` naming strategy automatically applies to every MBean created by Boot, the JVM, or other libraries.

## 19. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Found locally, remote reports `InstanceNotFoundException` | Different ObjectName or wrong JVM | Query domain and compare canonical names |
| Remote cannot connect | JMX RMI host/port, firewall, authentication/TLS | Check transport first |
| Dashboard loses metrics after release | Domain, type, application, or name changed | Keep naming contract stable |
| Multiple MBeans of same type | Using only `type` as key | Add logical `name` |
| Duplicate MBean registration | Multiple beans/contexts use same ObjectName | Separate ownership and identifying keys |
| Name contains proxy class | Naming based on runtime class | Use stable resource type |
| Local has fewer keys than production | Environment config creates differing schemas | Standardize required keys |
| Wildcard query works but exact lookup fails | Inconsistent schema | Compare full ObjectNames |
| Remote client reads wrong instance | Missing target labels | Separate target identity from MBean identity |
| ObjectName has strange characters | Direct unescaped concatenation | Validate/quote property values |

## 20. Practical Design Principles

### 20.1. Define a Common Schema Across All Exporters

If modules use `type`, `application`, `name`, use the same key casing, semantics, and value rules. Domains organized by organization and subsystem should be documented.

### 20.2. Keep Logical Names Stable

A `products` cache should still be named `products` even when switching from Java class A to class B, changing proxies, or changing deployment config. Monitoring clients generally care about logical resources, not class names.

### 20.3. Ensure Ownership Within Each JVM

If multiple Spring contexts share the platform `MBeanServer`, clearly define which exporter/context registers which MBeans. If multiple similar instances genuinely need exporting, add meaningful distinguishing keys.

### 20.4. Separate Connection Routing from Naming

`JMXServiceURL`, host, and port tell you **where to connect**. ObjectName tells you **which object to access on that server**. The two concepts should not be mixed.

### 20.5. Cross-Check the Registry, Not Just Config

A naming strategy can be right yet the exporter never calls it because of an explicit name, annotation, or unexported bean. Always confirm the actual ObjectName with `queryNames` or JConsole.

### 20.6. Compatibility with Existing Clients

Changing an ObjectName can be a breaking change for dashboards and scripts. If a schema change is required, support a transition period by updating clients and monitoring first; avoid registering two MBeans controlling the same resource if that causes confusion or duplicate actions.

## 21. Practice Exercises

Create two Spring applications or two JVMs simulating local and remote, both exporting a management queue named `payments`.

**Requirements:**

1. Use domain `com.example.orders`.
2. Use keys `type=Queue`, `application=checkout`, `name=payments`.
3. Manage the business bean in the Spring context.
4. Configure the exporter with a suitable naming strategy or explicit ObjectName.
5. Use JConsole or a local JMX client to read `PendingCount`.
6. Enable remote JMX in a secured lab environment and connect to the other JVM.
7. Use the same ObjectName to read `PendingCount` on the remote JVM.
8. Compare `getCanonicalName()` of both ObjectNames.
9. Try changing `application=inventory` on the client and observe that exact lookup no longer points to the original MBean.
10. Query with pattern `com.example.orders:type=Queue,*` and inspect the actual keys.

**Expected:** different JVMs can share the same ObjectName while `PendingCount` values may differ; clients distinguish values using target/JVM metadata.

## 22. Self-Check Questions

**1. Does using the same ObjectName across two JVMs cause a conflict?**

Usually no. ObjectNames must be unique within each `MBeanServer`. Monitoring systems need target identity to distinguish JVMs.

**2. Should remote JMX host/port be included in an ObjectName?**

Usually no. Host/port belong to connection configuration and can change across deployments.

**3. Does key property order affect ObjectName equality?**

No. Use `ObjectName.equals` or canonical names for comparison.

**4. Why is naming by proxy class fragile?**

Proxy classes can change with AOP/configuration; logical resource types keep contracts more stable.

**5. Is a wildcard query alone enough to guarantee consistent naming?**

No. Wildcards can match MBeans missing keys, while exact client lookups or schema validation still fail.

**6. When a remote client does not find an MBean, what should you do first?**

Verify the connection to the right JVM, query the actual registry, and then compare ObjectNames. Distinguish transport errors from naming errors.

**7. Can annotation `objectName` and a custom naming strategy conflict?**

Yes, depending on the exporter and prioritized metadata source. Unify the naming source and inspect registered MBeans.

**8. Is an `instance` key required for every replica?**

Not necessarily if each replica has its own `MBeanServer`. Collectors can attach instance labels at the scraping layer.

## 23. Summary

To keep MBean names consistent between local and remote, define **a stable ObjectName contract** comprising a domain and business-meaningful key properties. Spring `ObjectNamingStrategy`, explicit exporter mappings, or annotations can all produce names, but must be configured under the same schema.

Remember the two layers:

```text
JMX connection: host / port / credentials / TLS / target JVM
JMX identity:   domain + key properties of ObjectName
```

When local and remote use the same ObjectName schema, scripts and dashboards are easy to reuse; when the same name exists across multiple JVMs, monitoring systems distinguish them by target identity. Finally, always verify the **actual canonical ObjectName from `MBeanServer`**, because that is the name real JMX clients query.

### References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `ObjectNamingStrategy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/ObjectNamingStrategy.html
- Java SE API — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE API — `JMXConnectorFactory`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
