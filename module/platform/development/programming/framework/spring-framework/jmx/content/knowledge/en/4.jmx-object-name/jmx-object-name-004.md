# Avoiding Name Collisions Across Multiple Beans or Applications in JMX

## 1. The Problem: Why Do ObjectNames Collide?

In Java Management Extensions (**JMX**), each MBean is registered in an `MBeanServer` under an **`ObjectName`**. The `ObjectName` serves as the unique identifier of the MBean within the scope of that MBeanServer.

An application may have multiple Spring beans of the same type, multiple application contexts in a single JVM, or multiple modules exporting MBeans. If all of them register using a generic name:

```text
com.example:type=CacheManager
```

then the first bean succeeds, while the next bean with the same `ObjectName` may encounter:

```text
javax.management.InstanceAlreadyExistsException:
com.example:type=CacheManager
```

A name collision does not mean the Java objects or Spring bean names are identical. A **Spring bean name** is managed within a Spring `ApplicationContext`, whereas a **JMX ObjectName** is managed within an `MBeanServer`. These two namespaces are independent and have separate rules.

### Scope of Uniqueness

- Within the **same MBeanServer**, two MBeans cannot coexist with the exact same `ObjectName`.
- Across **different MBeanServers**, the same `ObjectName` can appear on both servers without directly causing `InstanceAlreadyExistsException`.
- Across **two separate JVM processes**, using the same `ObjectName` generally does not collide directly if each has its own MBeanServer. However, a centralized monitoring system still needs to clearly distinguish processes/instances so metrics from different sources are not merged erroneously.
- Multiple Spring `ApplicationContext` instances in the same JVM may share the **platform MBeanServer**, so name collisions remain a risk even across separate contexts.

The goal is to design names that are **stable, easy to query, and distinct enough for the managed entities**, while establishing a clear policy for duplicate registrations.

## 2. ObjectName Structure You Must Master

`ObjectName` has the general syntax:

```text
domain:key1=value1,key2=value2,...
```

Examples:

```text
com.example.orders:type=Queue,name=payment
com.example.orders:type=Queue,name=shipping
com.example.cache:type=CacheManager,name=primary
```

The **domain** usually represents the application or organization namespace. **Key properties** describe the resource type and specific identity.

Several rules:

1. The `domain` and the set of key properties together form the identity of an ObjectName; `name` alone does not determine uniqueness.
2. Key order in the input string does not change identity. For example, `domain:type=Cache,name=main` and `domain:name=main,type=Cache` represent the same ObjectName.
3. Two key properties with the same name in a single ObjectName are invalid.
4. Special characters in values—such as comma, colon, equals sign, double quote, asterisk, and question mark—must be handled according to ObjectName syntax. For arbitrary values, use `ObjectName.quote(value)` to escape properly when constructing a quoted value.
5. `*` and `?` can carry pattern meaning in an ObjectName. Avoid unintentionally creating a pattern when the goal is to register an MBean with a concrete name.
6. MBeans must be registered with a non-pattern ObjectName; patterns are useful for `queryNames` operations.

### Building Names in Java

```java
import javax.management.ObjectName;
import java.util.Hashtable;

public final class JmxNames {
    private JmxNames() {}

    public static ObjectName cache(
            String application,
            String cacheName
    ) throws Exception {
        Hashtable<String, String> properties = new Hashtable<>();
        properties.put("type", "Cache");
        properties.put("application", application);
        properties.put("name", cacheName);
        return new ObjectName("com.example.management", properties);
    }
}
```

With values constrained to naming standards (letters, digits, hyphens, underscores), building names from key properties is straightforward. If arbitrary data can contain special characters, you must construct a properly quoted value or restrict it to valid identifier characters before creating the ObjectName; never concatenate untrusted data strings directly.

Example pattern to find caches:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;
import java.util.Set;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> caches = server.queryNames(
    new ObjectName("com.example.management:type=Cache,*"),
    null
);

for (ObjectName name : caches) {
    System.out.println(name.getCanonicalName());
}
```

`getCanonicalName()` is useful for logging and comparing names in a normalized key order.

## 3. Common Collisions with Multiple Beans in One Application

Suppose there are two beans of the same type:

```java
@Bean
CacheService productCache() {
    return new CacheService("product");
}

@Bean
CacheService customerCache() {
    return new CacheService("customer");
}
```

If both are exported under:

```text
com.example:type=CacheService
```

the MBeanServer cannot distinguish which bean is being managed.

More appropriate names are:

```text
com.example.cache:type=CacheService,name=product
com.example.cache:type=CacheService,name=customer
```

In systems where multiple application contexts share one server, you may also need `context` or `application`:

```text
com.example.cache:type=CacheService,application=storefront,name=product
com.example.cache:type=CacheService,application=backoffice,name=product
```

Add only the dimensions truly needed for disambiguation. Creating a new MBean for every request or every user causes very high registry cardinality, consuming memory and complicating management. An MBean should represent a resource with a relatively stable lifecycle.

## 4. Collisions Across Multiple Applications in the Same JVM

In a JVM with multiple modules or multiple `ApplicationContext` instances, using an overly broad domain such as `app`, `spring`, or `monitoring` easily leads to collisions.

A design strategy:

```text
<namespace>:type=<ResourceType>,application=<AppId>,name=<ResourceId>
```

Examples:

```text
com.acme.platform:type=ThreadPool,application=checkout,name=async
com.acme.platform:type=ThreadPool,application=inventory,name=async
com.acme.platform:type=DataSource,application=checkout,name=primary
```

Define conventions clearly:

| Name Component | Purpose | Example |
| --- | --- | --- |
| Domain | Organization or product namespace | `com.acme.platform` |
| `type` | Resource category | `Cache`, `ThreadPool`, `DataSource` |
| `application` | Owning service or application | `checkout`, `inventory` |
| `context` | Distinguishes Spring contexts if genuinely needed | `root`, `admin` |
| `name` | Stable resource identifier | `primary`, `scheduler` |
| `instance` | Distinguishes replicas when they actually share an MBeanServer | `worker-1` |

Do not make `instance` a random UUID in every environment. A UUID that changes on every restart destroys the stability of queries and dashboards. If each replica runs in its own JVM, it is usually sufficient for the monitoring system to attach an instance label at the collection layer rather than embedding a replica ID in the `ObjectName`.

### Important Principle

**Keep MBean names stable within an instance, and distinguish different instances at the monitoring layer when appropriate.** This keeps JMX queries simple and avoids generating excessive volatile names.

## 5. Policies for Handling Duplicate Names

When `MBeanServer.registerMBean(mbean, objectName)` encounters an existing name, the operation typically throws `InstanceAlreadyExistsException`. In Spring Framework, `MBeanExporter` supports name collision handling policies, depending on the Spring version in use.

Three common conceptual choices:

| Policy | Meaning | When to Use |
| --- | --- | --- |
| Fail/error | Reject duplicate name registration; catch misconfiguration | Systems needing a strict identity contract |
| Ignore | Keep existing MBean, skip duplicate registration | Multiple contexts accidentally export a shared system MBean and ownership is clear |
| Replace | Unregister existing MBean and register the new MBean | Only when lifecycle and ownership are firmly established |

**Do not choose replace as a default fix for bad naming.** One module could delete another module's MBean, leaving clients holding stale references or broken subscriptions, or losing management state while the application is running.

### 5.1. Default to Early Detection

For application-managed MBeans, failing on duplicates usually catches configuration mistakes early and prevents silent shadowing.

### 5.2. Ignore Requires a Clear Justification

Ignore can prevent a component from re-registering a shared MBean when another owner has already registered it. However, if two beans have distinct business roles, ignore causes one bean to lose manageability instead of receiving its own name.

### 5.3. Replace Demands Clear Ownership

If one context unregisters an MBean registered by another context, lifecycle conflicts can arise when the older context shuts down. Only use replace when an ownership policy guarantees the operation is intentional.

## 6. Spring Framework: Explicit ObjectName Assignment

Spring Framework provides `MBeanExporter` to export beans to JMX.

Java configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

import java.util.LinkedHashMap;
import java.util.Map;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public MBeanExporter applicationMBeanExporter(
            ProductCacheAdmin productCacheAdmin,
            CustomerCacheAdmin customerCacheAdmin
    ) {
        MBeanExporter exporter = new MBeanExporter();

        Map<String, Object> beans = new LinkedHashMap<>();
        beans.put(
            "com.acme.shop:type=Cache,application=storefront,name=product",
            productCacheAdmin
        );
        beans.put(
            "com.acme.shop:type=Cache,application=storefront,name=customer",
            customerCacheAdmin
        );

        exporter.setBeans(beans);
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING
        );
        return exporter;
    }
}
```

This illustrates naming and export policies. `ProductCacheAdmin` and `CustomerCacheAdmin` are illustrative classes not defined in the snippet; in a real application they must be valid MBeans or paired with an appropriate assembler to produce the JMX interface.

Common `RegistrationPolicy` values include:

- `FAIL_ON_EXISTING`: raises an error if the MBean already exists.
- `IGNORE_EXISTING`: skips registration when the name already exists.
- `REPLACE_EXISTING`: replaces the existing MBean with the new MBean.

Choose `FAIL_ON_EXISTING` for application MBeans unless there is a formal reason to share an ObjectName.

## 7. Spring @ManagedResource and Name Collision Risks

Spring supports annotation-based MBean export via `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`.

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.acme.shop:type=Cache,name=product",
    description = "Product cache management"
)
public class ProductCacheAdmin {

    private volatile int entryCount;

    @ManagedAttribute
    public int getEntryCount() {
        return entryCount;
    }
}
```

If one class is instantiated as multiple beans and all take the fixed `objectName` from the annotation, exporting multiple instances can cause collisions.

Approaches to resolve this:

1. **Single instance:** ensure only one bean is exported under the fixed annotation name.
2. **Multiple independently managed instances:** configure distinct names per instance through an appropriate exporter or naming strategy.
3. **Multiple application contexts:** define which context owns the MBean, or add a context identifier if each context must export.
4. **Shared components:** avoid hardcoding a fixed service identifier in reusable libraries; let each application supply its own namespace.

Annotations do not automatically guarantee unique names per instance. Verify how `AnnotationMBeanExporter` and the naming strategy behave in your actual configuration.

## 8. ObjectNamingStrategy and KeyNamingStrategy

Spring's `ObjectNamingStrategy` provides an extension point to determine the `ObjectName` for a bean. This is the right place to enforce a uniform naming policy.

Some common strategies:

- **MetadataNamingStrategy:** relies on JMX metadata (such as annotations) and an appropriate fallback strategy.
- **KeyNamingStrategy:** uses a mapping from bean keys to ObjectNames or applies a configured naming format.
- **Custom strategy:** implements `ObjectNamingStrategy` and builds the `ObjectName` from namespace, resource type, and bean key.

Custom implementation example:

```java
import org.springframework.jmx.export.naming.ObjectNamingStrategy;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class ApplicationObjectNamingStrategy
        implements ObjectNamingStrategy {

    private final String application;

    public ApplicationObjectNamingStrategy(String application) {
        this.application = application;
    }

    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {
        String type = managedBean.getClass().getSimpleName();

        return new ObjectName(
            "com.acme.management:type=" + ObjectName.quote(type)
                + ",application=" + ObjectName.quote(application)
                + ",name=" + ObjectName.quote(beanKey)
        );
    }
}
```

The strategy above illustrates incorporating `application` and `beanKey` into the name. In a real system, you must control the stability of bean keys, proxy classes, and ObjectName syntax. When Spring AOP creates a proxy, `managedBean.getClass().getSimpleName()` may reflect the proxy class name rather than the business class. To remain stable across proxy changes, obtain the **resource type from metadata or stable configuration** instead of the runtime class name.

`ObjectName.quote` escapes values within ObjectName syntax; avoid concatenating raw user-supplied values without sanitization.

## 9. Avoiding Volatile Names Caused by Proxies, Profiles, and Runtime

### 9.1. Spring Proxies

Beans may be wrapped in proxies when using AOP, transactions, or scoped proxies. If a naming algorithm uses the runtime class name directly, the MBean name can change once advice is added. It is better to use:

```text
domain=fixed namespace
type=business resource name
application=stable service ID
name=stable bean/resource ID
```

### 9.2. Profiles and Environments

In separate-JVM deployments, sharing the same ObjectName across dev, staging, and production does not necessarily collide at the MBeanServer level. The monitoring layer should attach environment/cluster labels. Include the environment in the ObjectName only if multiple environments genuinely share a server/namespace and must be separated there.

### 9.3. Multiple Spring Contexts

A web application may have a parent context and child contexts, or multiple deployments in the same container. Those contexts may share the platform MBeanServer. You need:

- An exporter with clear ownership.
- Context-scoped namespaces when each context needs independent MBeans.
- Registration/unregistration policies aligned with each context's lifecycle.

Avoid setting `REPLACE_EXISTING` in every context, as a later-starting context could replace an earlier context's MBeans.

## 10. MBean Registration and Unregistration Lifecycle

Consistent naming solves only half the problem. An MBean can be left behind if shutdown or hot reload fails to unregister it properly, causing collisions on the next deployment.

Basic operations:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxLifecycle {
    public static void unregisterIfOwned(ObjectName name)
            throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        if (server.isRegistered(name)) {
            // Only do this when this component owns the registration.
            server.unregisterMBean(name);
        }
    }
}
```

**Ownership warning:** `server.isRegistered(name)` only tells you that the name is registered; it does not prove that the current MBean belongs to your component. The snippet above is only appropriate when the application has previously guaranteed ownership through its lifecycle, not to remove another application's MBean.

When using Spring `MBeanExporter`, prefer letting the exporter manage registration/unregistration within the application lifecycle. For manual registration, track the exact ObjectNames that the component successfully registered, unregister those exact names on close, and handle possible race-condition errors.

### Race Condition in Check-Then-Register

Code like the following is not strictly safe when multiple threads or contexts register concurrently:

```java
if (!server.isRegistered(name)) {
    server.registerMBean(bean, name);
}
```

Between the two statements, another component can register the same name. Handle `InstanceAlreadyExistsException` according to your ownership policy or serialize registration if the system truly shares a server.

## 11. Naming Architecture Recommendations for Multi-Module Applications

A naming contract can be standardized in a shared management library:

```text
domain = com.acme.<product>
key properties:
  type        = resource group
  application = service/module name
  name        = logical resource name
  context     = optional, if contexts need to be distinguished
```

Examples:

```text
com.acme.retail:type=Cache,application=catalog,name=products
com.acme.retail:type=Cache,application=pricing,name=rules
com.acme.retail:type=ThreadPool,application=catalog,name=background
com.acme.retail:type=DataSource,application=orders,name=primary
```

Benefits:

- Easy to find MBeans by `type` or `application`.
- Prevents collisions between two beans of the same type.
- Reduces dependency on Java class or proxy names.
- Keeps ObjectNames stable across implementation changes.
- Enables building pattern-based queries for dashboards and alerts.

Every application sharing a namespace should follow the same convention; a single module inventing a different key name can fragment monitoring queries.

## 12. Observing and Diagnosing Collisions

### Listing Existing MBeans

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(
        new ObjectName("com.acme.*:*"), null)) {
    System.out.println(name.getCanonicalName());
}
```

The pattern above is illustrative only: domain and key patterns must be tailored to your actual domain. You can use JConsole or VisualVM to browse the MBean tree and compare actual ObjectNames.

### Checklist When Encountering InstanceAlreadyExistsException

1. Read the full ObjectName in the exception.
2. Identify which MBeanServer is being used (platform server or custom server).
3. Trace which component or context already registered that ObjectName.
4. Check exporters or annotations that produce the same name.
5. Inspect bean keys, naming strategy configuration, and proxy-induced changes.
6. Fix the root cause: adjust the naming schema, separate ownership, or prevent duplicate exports.
7. Use ignore/replace only when lifecycle and ownership are thoroughly understood.

Avoid resolving collisions by generating random names on each run, as that makes MBeans hard for management tools to locate and can mask registry leaks.

## 13. Common Mistakes

| Mistake | Consequence | Better Approach |
| --- | --- | --- |
| Naming every bean `type=Service` | Multiple beans share the same ObjectName | Add a `name` key per resource |
| Using the proxy class name directly | Name changes after adding AOP | Use a stable logical type |
| Using random UUIDs for each MBean | Dashboards are hard to query, too many names to track | Use a stable resource ID |
| `IGNORE_EXISTING` on every exporter | New beans may become unmanageable | Fail fast and fix naming |
| `REPLACE_EXISTING` across all contexts | One context can overwrite another context's MBean | Define clear ownership |
| Not unregistering on shutdown | Old MBeans occupy the name | Manage lifecycle and ownership |
| Ignoring special characters in values | `MalformedObjectNameException` or unintended patterns | Quote/validate values syntactically |
| Assuming different Spring contexts mean different MBeanServers | Still collides if sharing the platform server | Verify which MBeanServer is used |
| Confusing Spring bean names with ObjectNames | Editing the wrong identifier layer | Check exporter/naming strategy |
| Putting request/user IDs in ObjectNames | High cardinality, resource exhaustion | Export stable aggregated metrics |

## 14. Self-Check Questions

**1. Can two MBeans in two different JVMs have the same ObjectName?**

Yes. Uniqueness is managed per MBeanServer. In centralized observability, you still need to identify the source (host, process, instance) at the monitoring layer.

**2. Why is `type=Cache` not enough?**

Because an application can have multiple distinct caches. Add `name=products`, `name=prices`, or another resource identifier to distinguish them.

**3. What does `ObjectName.quote` do?**

It escapes a value according to ObjectName syntax, handling special characters inside a key property value.

**4. Must a Spring bean name equal the `name` key in its ObjectName?**

No. The naming strategy or exporter configuration determines the ObjectName; using the bean key as part of the identifier is an optional design choice.

**5. Why should `REPLACE_EXISTING` not be used by default?**

Because one component could overwrite or destroy a managed object belonging to another component, especially when multiple application contexts exist.

**6. When should `context` be added to an ObjectName?**

When multiple contexts genuinely share one MBeanServer and each context must export its own MBeans of the same type and name.

**7. Is checking `isRegistered` before `registerMBean` enough to prevent races?**

No. They are two separate operations; another thread can register the name between the two calls.

## 15. Conclusion

Avoiding JMX name collisions requires a consistent `ObjectName` strategy based on **namespace + resource type + application + logical resource**, along with a clear understanding of **MBeanServer uniqueness scope**. In Spring Framework, combine `MBeanExporter`, `ObjectNamingStrategy`, `@ManagedResource`, and `RegistrationPolicy` to control names and duplicate behavior.

Practical rule: **Design stable, sufficiently distinct names from the start; resolve collisions through namespace design and ownership rather than defaulting to ignoring or replacing MBeans.**

### References

- Java SE API — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE API — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `RegistrationPolicy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
