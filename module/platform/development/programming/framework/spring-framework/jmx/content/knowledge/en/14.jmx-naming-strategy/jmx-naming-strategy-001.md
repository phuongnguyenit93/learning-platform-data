# Spring Framework JMX: ObjectNamingStrategy and Its Role in MBeanExporter

## 1. Objective

In Spring Framework JMX, **\`MBeanExporter\`** registers Spring beans as MBeans so management tools can access them via \`MBeanServer\`. Every MBean needs a JMX name of type \`javax.management.ObjectName\`, for example:

\`\`\`text
com.example.app:type=WorkerPool,name=primary
\`\`\`

When an application exports many beans, a question must be answered: **How is the ObjectName of each bean determined?** Names can be assigned directly in the exporter configuration, in the \`@ManagedResource\` annotation, or via an **\`ObjectNamingStrategy\`** to build names consistently according to centralized rules.

This lesson explains the \`org.springframework.jmx.export.naming.ObjectNamingStrategy\` interface, its role in \`MBeanExporter\`, how to implement a naming strategy, cases where a strategy is or is not applied, as well as managing collisions, multiple instances, and the stability of management names.

Overview model:

\`\`\`text
ApplicationContext
  |
  +-- Bean "primaryPool"  -----------+
  +-- Bean "secondaryPool" ----------+--> MBeanExporter
  +-- Bean "cacheManager" -----------+          |
                                                v
                                     ObjectNamingStrategy
                                     (managedBean, beanKey)
                                                |
                                          ObjectName
                                                |
                                                v
                                           MBeanServer
                                                |
                                           JMX clients
\`\`\`

**Key point:** A naming strategy determines the **JMX identity** of a bean; it does not directly decide which attributes or operations are exposed. The management metadata part is typically the responsibility of the MBean contract or \`MBeanInfoAssembler\`.

## 2. Three Components to Distinguish

| Component | Question Solved | Example |
|---|---|---|
| \`MBeanExporter\` | Which beans are exposed to JMX and on which server are they registered? | Export the \`primaryPool\` bean |
| \`ObjectNamingStrategy\` | What ObjectName will the bean have? | \`com.example.app:type=WorkerPool,name=primary\` |
| \`MBeanInfoAssembler\` | Which attributes/operations do clients see? | \`ActiveCount\`, \`resize(int)\` |

In addition:

- \`MBeanServer\` is the actual registry storing registered MBeans.
- \`ObjectName\` is the identifier in the registry, consisting of a domain and key properties.
- \`MBeanExporter\` can use an explicit name or a naming strategy depending on how the bean is declared/configured.
- Beans that are already a Standard MBean/DynamicMBean have an existing JMX contract; POJOs typically need an assembler/model MBean adapter to publish their management interface.

Do not use a bean's name to infer that all public methods have been exported. Choosing an ObjectName and choosing the JMX surface are two separate concerns.

## 3. What Is an ObjectName?

An ObjectName has the form:

\`\`\`text
<domain>:<key>=<value>,<key>=<value>,...
\`\`\`

Examples:

\`\`\`text
com.example.app:type=WorkerPool,name=primary,service=orders
com.example.app:type=WorkerPool,name=secondary,service=orders
com.example.app:type=CacheManager,name=products,service=catalog
\`\`\`

The domain typically uses a namespace controlled by the application. Key properties describe the type, role, and identity of the resource.

Two technical points:

1. Within the same \`MBeanServer\`, one ObjectName can identify only one currently registered MBean. Duplicate registration typically causes \`InstanceAlreadyExistsException\`.
2. An ObjectName is structured, not a plain string. The order of key properties does not create a new identity: \`type=Cache,name=products\` and \`name=products,type=Cache\` are equivalent.

Therefore, a good naming strategy must generate names that are **valid**, **non-colliding within the server**, and **stably meaningful to management clients**.

## 4. The ObjectNamingStrategy Interface

Spring provides the interface:

\`\`\`java
package org.springframework.jmx.export.naming;

public interface ObjectNamingStrategy {
    ObjectName getObjectName(
        Object managedBean,
        String beanKey
    ) throws MalformedObjectNameException;
}
\`\`\`

The method receives:

- \`managedBean\`: the Spring object to be exported.
- \`beanKey\`: the key/name used by the exporter to identify the bean in the export configuration.
- Result: a \`javax.management.ObjectName\`.

\`beanKey\` is often related to the bean name or mapping key in the exporter, but you should not assume it is always a stable business name. When proxies, auto-generated bean keys, or different map configurations are involved, you must understand what supplies \`beanKey\` in the actual export setup.

Example of a conceptual strategy:

\`\`\`java
ObjectName getObjectName(Object bean, String beanKey) {
    // Convert beanKey into an ObjectName according to the naming contract.
}
\`\`\`

A strategy **does not register** the MBean itself. It returns the name for \`MBeanExporter\` to use during export.

## 5. Default Strategies and Explicit Names

Spring has naming mechanisms, including \`KeyNamingStrategy\` which uses the bean key and mappings if configured. An ObjectName can also be specified directly when registering beans:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setBeans(Map.of(
    "com.example.app:type=WorkerPool,name=primary",
    primaryPool
));
\`\`\`

In the configuration above, the map key is already an ObjectName in string form. In many cases, the exporter can interpret it directly according to the corresponding naming strategy or convention.

Some applications use annotations:

\`\`\`java
@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,name=primary"
)
public class WorkerPoolControl {
    // ...
}
\`\`\`

When \`MetadataNamingStrategy\`/annotation infrastructure is used, the metadata name can participate in determining the ObjectName.

**Do not assume a custom strategy always overrides every form of explicit name or annotation name.** The precedence and name-selection mechanism depend on the exporter, the configured strategy, and the bean type. When designing, choose one primary naming source, then verify the registered ObjectName using \`MBeanServer\`.

## 6. Example Implementation of a Custom ObjectNamingStrategy

A management application has beans named:

\`\`\`text
ordersPrimaryPool
ordersBackgroundPool
catalogProductCache
\`\`\`

We want a common convention:

\`\`\`text
com.example.platform:type=ManagedComponent,name=<beanKey>
\`\`\`

Example:

\`\`\`java
package com.example.jmx;

import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class ApplicationObjectNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey
    ) throws MalformedObjectNameException {

        if (beanKey == null || beanKey.isBlank()) {
            throw new MalformedObjectNameException(
                "beanKey must be non-blank"
            );
        }

        Hashtable<String, String> props = new Hashtable<>();
        props.put("type", "ManagedComponent");
        props.put("name", validateToken(beanKey));

        return new ObjectName(
            "com.example.platform",
            props
        );
    }

    private static String validateToken(String key)
            throws MalformedObjectNameException {

        if (!key.matches("[A-Za-z0-9][A-Za-z0-9._-]*")) {
            throw new MalformedObjectNameException(
                "Unsupported bean key in JMX name"
            );
        }
        return key;
    }
}
\`\`\`

The advantage of using \`Hashtable\` and the \`ObjectName(domain, properties)\` constructor is avoiding ad-hoc concatenation of \`:\`, \`,\`, and \`=\`. Validation is still necessary because dynamic values may contain special characters or fail to comply with the naming contract.

Note: \`getObjectName\` may be called during Spring's initialization of the exporter. If a key is invalid, the exception should let operators know where the error is without leaking sensitive data.

### Why Not Use Arbitrary \`replaceAll\`?

For example:

\`\`\`java
String safe = beanKey.replaceAll("[^A-Za-z0-9._-]", "_");
\`\`\`

\`orders/pool\` and \`orders:pool\` can both become \`orders_pool\`, causing a collision. If you want to replace characters, you must have a strategy that proves the mapping is one-to-one over the actual input set or assign a separate stable ID.

For names containing special characters that must be preserved, you can use \`ObjectName.quote\` according to JMX rules; however, align quoting between the exporter and clients, because quoted/unquoted representations have different meanings when matching names.

## 7. Configuring a Naming Strategy into MBeanExporter

Spring Java configuration:

\`\`\`java
package com.example.jmx;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfig {

    @Bean
    public ApplicationObjectNamingStrategy objectNamingStrategy() {
        return new ApplicationObjectNamingStrategy();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            ApplicationObjectNamingStrategy namingStrategy,
            WorkerPoolControl primaryPool,
            WorkerPoolControl backgroundPool) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setNamingStrategy(namingStrategy);
        exporter.setBeans(Map.of(
            "primaryPool", primaryPool,
            "backgroundPool", backgroundPool
        ));

        return exporter;
    }
}
\`\`\`

This is how you directly configure a naming strategy for an exporter. With the map keys \`primaryPool\` and \`backgroundPool\`, the strategy can generate:

\`\`\`text
com.example.platform:type=ManagedComponent,name=primaryPool
com.example.platform:type=ManagedComponent,name=backgroundPool
\`\`\`

In a real application, \`WorkerPoolControl\` beans must be defined as Spring beans, and an assembler must be provided if they are POJOs that do not yet follow the Standard/Dynamic MBean convention.

Example annotated bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(description = "Worker pool controls")
public class WorkerPoolControl {
    private int size = 8;

    @ManagedAttribute
    public int getSize() {
        return size;
    }
}
\`\`\`

If the exporter uses \`MetadataMBeanInfoAssembler\`, it will extract attributes/operations from annotations. The naming strategy above remains a separate component responsible for the ObjectName.

### Full Exporter and Assembler Configuration

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Bean
AnnotationJmxAttributeSource jmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
MetadataMBeanInfoAssembler jmxAssembler(
        AnnotationJmxAttributeSource source) {
    MetadataMBeanInfoAssembler assembler =
        new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}

@Bean
MBeanExporter exporter(
        ApplicationObjectNamingStrategy namingStrategy,
        MetadataMBeanInfoAssembler assembler,
        WorkerPoolControl primaryPool) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setNamingStrategy(namingStrategy);
    exporter.setAssembler(assembler);
    exporter.setBeans(Map.of("primaryPool", primaryPool));
    return exporter;
}
\`\`\`

This is an alternative configuration, not a second exporter to be added alongside the previous example configuration. When \`@EnableMBeanExport\` or Spring Boot auto-configuration is present, avoid having multiple exporters register the same bean.

## 8. Distinguishing Naming and Assembling

Suppose we have the same bean:

\`\`\`java
public class WorkerPoolControl {
    public int getActiveCount() { return 3; }
    public void resetCounters() { /* ... */ }
    public void internalShutdown() { /* ... */ }
}
\`\`\`

Even if a custom naming strategy returns:

\`\`\`text
com.example.platform:type=WorkerPool,name=primary
\`\`\`

it has no authority to decide whether \`ActiveCount\`, \`resetCounters\`, or \`internalShutdown\` is exposed.

To select JMX members, use an MBean contract or assembler:

- \`MetadataMBeanInfoAssembler\`: based on Spring annotation metadata.
- \`MethodNameBasedMBeanInfoAssembler\`: selects methods via a whitelist.
- \`InterfaceBasedMBeanInfoAssembler\`: selects via a management interface.
- Standard MBean: an \`XxxMBean\` interface defines the JMX surface.

**Summary:** Naming answers *"At what address is this MBean located?"*. Assembling answers *"Once at that address, what can clients do?"*.

## 9. Multi-Instance Scenarios

### 9.1. Two Beans of the Same Class in One JVM

\`\`\`java
@Bean("primaryPool")
WorkerPoolControl primaryPool() {
    return new WorkerPoolControl();
}

@Bean("backupPool")
WorkerPoolControl backupPool() {
    return new WorkerPoolControl();
}
\`\`\`

If the strategy only uses \`managedBean.getClass().getSimpleName()\`, both can become:

\`\`\`text
com.example.app:type=WorkerPoolControl
\`\`\`

and cause a collision. Add the bean key or a logical name:

\`\`\`text
com.example.app:type=WorkerPoolControl,name=primary
com.example.app:type=WorkerPoolControl,name=backup
\`\`\`

### 9.2. Multiple ApplicationContexts Sharing a Server

Two different contexts may both use the key \`workerPool\`. If they share the same MBeanServer and the same strategy, the ObjectNames can collide. You can add \`context\`:

\`\`\`text
com.example.app:type=WorkerPool,name=workerPool,context=admin
com.example.app:type=WorkerPool,name=workerPool,context=public
\`\`\`

Do not assume \`ApplicationContext.getId()\` is always stable across restarts. If you want durable names for monitoring, the context identifier should be controlled via configuration.

### 9.3. Multiple Replicas in Different JVMs

Each JVM has its own \`MBeanServer\`. Two replicas can export the same:

\`\`\`text
com.example.app:type=WorkerPool,service=orders,name=primary
\`\`\`

without direct collision. Monitoring typically distinguishes replicas by endpoint, pod, node, or target labels.

Do not put a random UUID into the ObjectName just because there are multiple pods; stable logical names make shared scripts easier to reuse.

### 9.4. Tenant/Shard Resources

If the same JVM has multiple per-tenant caches:

\`\`\`text
com.example.app:type=Cache,service=orders,tenant=tenant-a
com.example.app:type=Cache,service=orders,tenant=tenant-b
\`\`\`

A naming strategy can obtain the tenant ID from a bean identity interface. However, you must bound the number of MBeans and ensure unregistration when a tenant is removed. JMX is not suitable for exporting an MBean for each unbounded request/session.

## 10. Bean-Contract-Based Naming Strategy

When multiple key properties are needed, you can build a dedicated identity interface instead of inferring from the class name or bean key string:

\`\`\`java
package com.example.jmx;

public interface ManagedResourceIdentity {
    String getResourceType();
    String getServiceName();
    String getResourceName();
}
\`\`\`

A bean:

\`\`\`java
public class WorkerPoolControl implements ManagedResourceIdentity {
    @Override
    public String getResourceType() {
        return "WorkerPool";
    }

    @Override
    public String getServiceName() {
        return "orders";
    }

    @Override
    public String getResourceName() {
        return "async";
    }
}
\`\`\`

Naming strategy:

\`\`\`java
import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class IdentityNamingStrategy implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object bean,
            String beanKey) throws MalformedObjectNameException {

        if (!(bean instanceof ManagedResourceIdentity id)) {
            throw new MalformedObjectNameException(
                "Bean does not expose ManagedResourceIdentity: "
                    + beanKey
            );
        }

        Hashtable<String, String> props = new Hashtable<>();
        props.put("type", token(id.getResourceType()));
        props.put("service", token(id.getServiceName()));
        props.put("name", token(id.getResourceName()));

        return new ObjectName("com.example.platform", props);
    }

    private static String token(String value)
            throws MalformedObjectNameException {

        if (value == null ||
            !value.matches("[A-Za-z0-9][A-Za-z0-9._-]*")) {
            throw new MalformedObjectNameException(
                "Invalid JMX naming token"
            );
        }
        return value;
    }
}
\`\`\`

Benefits:
- The resource's ID is independent of the Java class name.
- Refactoring bean names or packages does not automatically change the ObjectName.
- Each component publishes its own logical identity by contract.
- The ObjectName structure reflects the dimensions operators use to search.

Drawbacks: management facade beans must implement the interface or have an adapter. With AOP proxies, the \`managedBean\` received by the strategy may be a proxy rather than the direct implementation class; ensure the contract is exposed through the proxy or use other stable metadata.

## 11. Using Annotation Metadata with a Naming Strategy

When managing via annotations:

\`\`\`java
@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,name=main"
)
public class WorkerPoolControl {
    @ManagedAttribute
    public int getSize() {
        return 8;
    }
}
\`\`\`

Spring has metadata-reading naming mechanisms, such as \`MetadataNamingStrategy\`. It differs from a custom strategy based on the bean key. A system should be consistent:

- Name **placed in \`@ManagedResource\`** if each bean has a clear static name.
- Name **generated by a naming strategy** if managing multiple instances or names depend on configuration.
- Name **explicit in \`setBeans\`** when a specific mapping is the source of truth.

Do not use all three naming sources without knowing the precedence order. Inspect the actual registered ObjectName rather than reading a single annotation and jumping to conclusions.

## 12. Checking Results in MBeanServer

After the exporter is running, you can query MBeans by pattern:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern = new ObjectName(
    "com.example.platform:type=ManagedComponent,*"
);

for (ObjectName name : server.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

If the exporter uses an MBeanServer other than the platform server, substitute the exact configured server. Two different servers do not automatically share a registry.

Verify an individual ObjectName:

\`\`\`java
ObjectName expected = new ObjectName(
    "com.example.platform:type=ManagedComponent,name=primaryPool"
);

boolean registered = server.isRegistered(expected);
System.out.println("Registered = " + registered);

if (registered) {
    var info = server.getMBeanInfo(expected);
    System.out.println("MBean class = " + info.getClassName());

    for (var attr : info.getAttributes()) {
        System.out.println(
            attr.getName() + " type=" + attr.getType()
        );
    }

    for (var operation : info.getOperations()) {
        System.out.println(operation.getName());
    }
}
\`\`\`

This is the runtime result verification step:
- Did the naming strategy generate the right name?
- Did the exporter actually register that name?
- Did the MBean contract/assembler expose the desired members?

If you only check \`isRegistered\` without inspecting the metadata, you cannot confirm the management interface is accurate.

## 13. Preventing Collisions and Handling InstanceAlreadyExistsException

Within a single \`MBeanServer\`, registering two MBeans with the same ObjectName can throw \`InstanceAlreadyExistsException\`. For example, a strategy that only uses type:

\`\`\`java
return new ObjectName("com.example.app:type=WorkerPool");
\`\`\`

If there are two worker pools, they will contend for the same name.

A naming strategy should include enough distinguishing keys, for example:

\`\`\`text
com.example.app:type=WorkerPool,service=orders,name=mailer
com.example.app:type=WorkerPool,service=orders,name=processor
\`\`\`

Before changing the exporter's collision policy, find the root cause:
1. Are there genuinely two different instances that need to be exported?
2. Are two exporters exporting the same bean?
3. Are two \`ApplicationContext\`s using the same server?
4. Is an old MBean still unregistered?
5. Is the strategy mapping multiple inputs to the same name?

Do not default to \`IGNORE_EXISTING\` or \`REPLACE_EXISTING\` as a fix. They can cause management tools to target the wrong resource or alter ownership on shutdown.

### Registration Race

\`\`\`java
if (!server.isRegistered(name)) {
    server.registerMBean(bean, name);
}
\`\`\`

Checking beforehand does not make registration an atomic operation. In a multi-threaded/multi-context environment, another party can register the same name after the check step. Exceptions at registration time must still be handled.

## 14. Naming Strategy and Exporter Lifecycle

An ObjectName generated at registration time must be used consistently to manage the MBean until the end of its lifecycle. When the Spring context stops, the exporter typically unregisters the MBeans it manages.

For dynamic beans or restarted contexts:
- Avoid names based on timestamps or random UUIDs if users need to query stable names.
- Keep a logical ID → ObjectName mapping for cleanup.
- Ensure only the owner is responsible for unregistering the MBean.
- If the name changes between two registrations, monitoring scripts will have to rediscover it.
- If multiple contexts share a server, a clear namespacing and ownership strategy is required.

Do not mechanically put IP, PID, ephemeral port, or pod UID into the name. Those can be JMX target metadata rather than components identifying an MBean inside a single JVM.

## 15. Security When Naming MBeans

ObjectNames frequently appear in JMX browsers, logs, metrics exporters, and monitoring. Do not put secrets or personal information directly into key properties.

Inappropriate examples:

\`\`\`text
com.example.app:type=ApiClient,token=secret-value
com.example.app:type=User,email=private@example.com
\`\`\`

Use non-sensitive management identifiers:

\`\`\`text
com.example.app:type=ApiClient,name=primary
com.example.app:type=TenantQuota,tenant=tenant-042
\`\`\`

If \`tenant\` is a sensitive internal identifier, evaluate its exposure level and separate protection mechanisms. A naming strategy is not an authorization mechanism; remote JMX must have appropriate authentication, authorization, and transport security.

## 16. Common Errors

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| \`MalformedObjectNameException\` | Invalid domain/key/value | Validate tokens and construct structured ObjectNames |
| \`InstanceAlreadyExistsException\` | Strategy generates duplicate names or duplicate export | Check mapping/owner and \`queryNames\` |
| MBean not found | Client uses a different name than the exporter registered | Query with a pattern, use canonical name |
| Only one MBean seen for the same class | Strategy uses only class name without distinguishing instances | Add \`name\` or a logical key |
| Name changes after restart | Name generated with timestamp/random ID | Use stable identifiers |
| Annotation states one name but runtime has another | Multiple naming sources coexist | Determine which strategy is actually in use |
| Proxy causes metadata lookup failure | Strategy casts to implementation class | Rely on interfaces or stable bean keys |
| Operations/attributes missing | This is not a naming error | Check \`MBeanInfoAssembler\` and MBean metadata |
| JConsole connects to the right JVM but still does not see it | Exporter uses a different MBeanServer | Check server configuration |
| MBean unexpectedly unregistered | Multiple exporters/contexts contend for ownership | Check lifecycle and duplicate registration |

**Distinguish naming errors from management interface errors:** \`ObjectNamingStrategy\` only returns an ObjectName. If the name exists but an attribute is missing or an operation cannot be invoked, investigate the assembler, the Standard MBean contract, or the operation signature.

## 17. Practice Exercises

### Exercise 1 — Same Class, Two Beans

Given \`primaryPool\` and \`secondaryPool\` as two beans of \`WorkerPoolControl\`. If the naming strategy only uses \`managedBean.getClass().getSimpleName()\`, what happens?

**Explanation:** Both beans may receive the same name and conflict in a single \`MBeanServer\`. Use the bean key or a logical resource ID to distinguish them.

### Exercise 2 — Querying with an ObjectName Pattern

Write Java code to find all worker pools in the domain \`com.example.platform\`:

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.example.platform:type=WorkerPool,*"
);

for (ObjectName candidate : server.queryNames(pattern, null)) {
    System.out.println(candidate);
}
\`\`\`

The pattern uses a wildcard property list, matching MBeans that have additional \`service\`, \`name\`, or other keys.

### Exercise 3 — Why Not Use the Class Name as the Sole Identifier?

Because a class can have multiple instances in one JVM. In addition, refactoring the class name can change the ObjectName even though the management role has not changed.

### Exercise 4 — Using Annotations and a Custom Strategy Together

A bean has \`@ManagedResource(objectName="...")\`, while the exporter is configured with a custom strategy based on the bean key. What needs to be done?

**Explanation:** Determine which naming source takes precedence according to the exporter/strategy in use and inspect the actual ObjectName using \`queryNames\`. In design, reduce the number of naming sources to avoid ambiguity.

### Exercise 5 — Do You Need to Add the Pod UID to Every ObjectName?

Not required. Pods/JVMs have independent MBeanServers. Monitoring usually distinguishes pods via target metadata; ObjectNames can keep the same logical name across replicas.

### Exercise 6 — Naming Strategy Produces the Right Name, but Clients Do Not See Operations

What should be investigated?

**Explanation:** Check \`MBeanInfo\`, the assembler, annotations, or the Standard MBean interface. A naming strategy does not select which methods are exposed.

## 18. Project Adoption Checklist

1. Define a fixed JMX domain owned by the organization.
2. Define consistent key properties: \`type\`, \`service\`, \`name\`, and optional \`context\`, \`tenant\`, \`shard\`.
3. Choose a single source of truth for names: explicit mapping, annotation metadata, or a custom naming strategy.
4. Ensure names are unique within each MBeanServer.
5. Do not depend on object identity, memory address, or random IDs when unnecessary.
6. Validate inputs to avoid malformed ObjectNames and post-normalization collisions.
7. Separate naming from MBean metadata assembling.
8. Verify the target MBeanServer and naming in a real runtime environment.
9. Define registration/unregistration ownership and avoid duplicate exports across multiple exporters.
10. Treat ObjectName changes as management API changes affecting dashboards/scripts.

## 19. Summary

**\`ObjectNamingStrategy\` is the set of rules that turns a bean and its identifying key into an \`ObjectName\`**. \`MBeanExporter\` uses that name to register the MBean in \`MBeanServer\`; \`MBeanInfoAssembler\` or the MBean contract determines what clients can read, write, and invoke.

Use a naming strategy when you need consistent names, many beans, or many instances, but do not make names depend on accidental runtime details. A good naming contract must be **valid, non-colliding, easy to query, stable, and free of sensitive data exposure**. After export, check \`queryNames\`, \`isRegistered\`, and \`MBeanInfo\` to confirm the application has published the right management resources.