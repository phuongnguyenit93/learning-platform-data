# Do Not Let the Java Class Name Be the Sole Management Contract

> **Topic:** Spring Framework JMX  
> **Knowledge group:** Naming strategy  
> **Lesson:** Do Not Let the Java Class Name Be the Sole Management Contract

## 1. Objectives

After this lesson, you will be able to:

- Explain why a **Java class name** should not be the sole management contract of an MBean.
- Distinguish **Spring bean name**, **Java class name**, **JMX ObjectName**, and **management interface**.
- Design ObjectNames with stable domains, key properties, and versioning conventions.
- Use \`@ManagedResource(objectName = "...")\`, \`MetadataNamingStrategy\`, or an appropriate naming mechanism when exporting MBeans.
- Understand how refactoring Java classes, using proxies/AOP, moving packages, creating multiple instances, and changing implementation technologies can affect MBean names if identity depends on implementation.
- Build management contracts based on **resource, role, environment, and compatibility**, rather than solely on class names.
- Inspect actual ObjectNames and JMX metadata to protect monitoring clients from accidental changes.

## 2. The Problem: Class Name Is an Implementation Detail, ObjectName Is the Management Entry Point

In JMX, clients do not look up Spring beans by the implementation's Java class. They interact with an MBean registered in \`MBeanServer\` via \`javax.management.ObjectName\`.

An example ObjectName:

\`\`\`text
app.monitoring:type=Cache,name=primary
\`\`\`

An example class:

\`\`\`text
com.example.cache.RedisBackedCacheService
\`\`\`

The two strings serve two different purposes:

| Component | Role | Desired Stability |
|---|---|---|
| Java class name | Expresses implementation and code structure | Can change during refactoring |
| Java package | Groups source code and modules | Can change during restructuring |
| Spring bean name | Identifies bean in \`ApplicationContext\` | Depends on DI configuration |
| JMX ObjectName | Identifies MBean in \`MBeanServer\` | Should stay stable if external clients use it |
| Management interface | Attribute/operation/notification contract | Should be managed compatibly like an API |

If ObjectNames are generated directly from the class name:

\`\`\`text
com.example.cache:type=RedisBackedCacheService
\`\`\`

then switching to:

\`\`\`text
com.example.cache:type=CaffeineCacheService
\`\`\`

can break queries, dashboards, or automation looking for the old MBean, even though the application's "primary cache" function did not change.

**Rule:** ObjectNames should represent the **management resource**, not merely mirror the class name currently doing the work.

## 3. ObjectName Is an Identity Contract

ObjectName structure:

\`\`\`text
domain:key1=value1,key2=value2,...
\`\`\`

Examples:

\`\`\`text
app.monitoring:type=Cache,name=primary
app.monitoring:type=WorkerPool,name=background
app.monitoring:type=MessageConsumer,name=orders
\`\`\`

Here:

- \`domain\` groups MBeans by application or management space.
- \`type\` describes the resource type, not necessarily matching the class name.
- \`name\` describes the instance or role.
- Additional keys such as \`node\`, \`region\`, or \`tenant\` can be added when distinguishing multiple instances is genuinely needed.

ObjectNames must be unique within **a single \`MBeanServer\`**. Two different JVMs can share the same ObjectName; clients select the JVM/server via the connection, and then the ObjectName selects the MBean inside that server.

For clients, ObjectName is the lookup point:

\`\`\`java
ObjectName name = new ObjectName(
    "app.monitoring:type=Cache,name=primary"
);

Object entries = connection.getAttribute(
    name,
    "EntryCount"
);
\`\`\`

If the ObjectName changes accidentally, clients may encounter \`InstanceNotFoundException\`, even though an MBean with the same functionality is still running under another name.

## 4. Anti-Pattern Example: Class Name Dictates the Entire Management API

Suppose initially there is a class:

\`\`\`java
package com.example.cache;

public class RedisCacheManager {
    // ...
}
\`\`\`

An automatic naming mechanism generates:

\`\`\`text
com.example.cache:type=RedisCacheManager
\`\`\`

After a refactoring pass, the class is renamed to \`DistributedCacheManager\`. If the strategy auto-generates names from the class, the JMX ObjectName also changes.

\`\`\`text
Before refactoring:
  RedisCacheManager
  -> com.example.cache:type=RedisCacheManager

After refactoring:
  DistributedCacheManager
  -> com.example.cache:type=DistributedCacheManager
\`\`\`

Consequences can include:

- JConsole no longer sees the MBean under the familiar name.
- Monitoring agents querying the old ObjectName get no results.
- Alerting rules fail to find the right attributes.
- Automation invoking operations via MBean proxies fails.
- Runbooks, operational docs, and charts no longer match.

Renaming classes is a frequent implementation change. If such an internal change breaks management clients, the design has coupled the operational contract too tightly to code.

## 5. Proper Design: Stable Names by Role

Keep the resource name:

\`\`\`text
app.monitoring:type=Cache,name=primary
\`\`\`

even as the implementation changes:

\`\`\`text
RedisCacheManager
       |
       v
DistributedCacheManager
       |
       v
InMemoryCacheManager
\`\`\`

\`\`\`text
                 Stable ObjectName
      app.monitoring:type=Cache,name=primary
                         |
                         v
                    MBeanServer
                         |
                         v
                   Spring JMX adapter
                         |
                         v
               Cache management facade
                         |
                 +-------+--------+
                 |                |
             Redis impl       Caffeine impl
\`\`\`

Clients only need to know the management contract: resource name, attributes, and operations. Implementations can change as long as compatibility is maintained for what clients actually use.

However, **name stability alone is not enough**. If the same ObjectName is kept yet the \`EntryCount\` attribute is deleted or the \`clear()\` operation is changed to \`purge(String)\`, clients can still fail. The management contract includes both ObjectName and \`MBeanInfo\`.

## 6. Declaring Explicit Names with @ManagedResource

Spring JMX supports specifying the ObjectName directly:

\`\`\`java
package com.example.monitoring;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.monitoring:type=Cache,name=primary",
    description = "Primary application cache management"
)
public class CacheManagementFacade {

    private final CacheService cacheService;

    public CacheManagementFacade(
            CacheService cacheService
    ) {
        this.cacheService = cacheService;
    }

    @ManagedAttribute(
        description = "Current number of cache entries"
    )
    public long getEntryCount() {
        return cacheService.entryCount();
    }

    @ManagedOperation(
        description = "Request cache refresh"
    )
    public void refresh() {
        cacheService.refresh();
    }
}
\`\`\`

\`CacheService\` is an illustrative business dependency. The facade class can be renamed while the ObjectName stays unchanged because the metadata uses a stable string.

Enabling export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

The example assumes component scanning brings \`CacheManagementFacade\` into the Spring context and the exporter is configured with the desired \`MBeanServer\`.

### Why Use a Dedicated Facade?

A business service can change as implementation needs evolve. A management facade acts as an adapter:

\`\`\`text
JMX contract -> facade -> business service
\`\`\`

A facade allows you to:

- Keep ObjectNames consistent.
- Select attributes and operations suited to operations.
- Avoid directly exposing internal methods.
- Adjust implementations without forcing JMX clients to update.
- Add input validation, scope limits, and side-effect controls.
- Prevent proxy/AOP classes from dictating management identity.

## 7. MetadataNamingStrategy in Spring

In Spring JMX, MBean naming can be delegated to \`org.springframework.jmx.export.naming.ObjectNamingStrategy\`. One implementation is \`MetadataNamingStrategy\`, which uses management metadata provided by \`JmxAttributeSource\`, typically alongside \`AnnotationJmxAttributeSource\`.

For a bean with:

\`\`\`java
@ManagedResource(
    objectName = "app.monitoring:type=WorkerPool,name=main"
)
public class WorkerPoolFacade {
}
\`\`\`

the metadata naming strategy can use this name when the exporter registers it.

Things to distinguish:

- **\`ObjectNamingStrategy\`** determines the ObjectName.
- **\`JmxAttributeSource\`** supplies annotation/descriptor metadata.
- **\`MBeanExporter\`** registers the bean as an MBean.
- **\`MBeanServer\`** holds the registry and executes JMX operations.
- **\`MBeanInfo\`** tells clients which attributes/operations/notifications are published.

Not every naming strategy prioritizes \`@ManagedResource.objectName\` in the same way. If changing strategies, read that strategy's contract and verify the actual ObjectName after export.

## 8. Custom Rule-Based Naming Strategy

In a multi-module application, a unified ObjectName rule may be needed. Spring allows configuring \`ObjectNamingStrategy\` on the exporter.

Example of a strategy illustrating mapping predefined bean keys:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class StableNamingStrategy
        implements ObjectNamingStrategy {

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey
    ) throws MalformedObjectNameException {

        if ("primaryCacheManagement".equals(beanKey)) {
            return new ObjectName(
                "app.monitoring:type=Cache,name=primary"
            );
        }

        if ("workerPoolManagement".equals(beanKey)) {
            return new ObjectName(
                "app.monitoring:type=WorkerPool,name=main"
            );
        }

        throw new IllegalArgumentException(
            "No managed ObjectName mapping for " + beanKey
        );
    }
}
\`\`\`

Here, mapping follows explicitly managed **management roles**, not \`managedBean.getClass().getName()\`. Choosing fail-fast behavior on invalid keys avoids automatically publishing names outside the agreed contract.

Note that \`getObjectName\` is invoked in the export context, and the actual \`beanKey\` depends on how the exporter is configured; if code uses an explicit bean map, we can control this key more easily.

Example of explicit \`MBeanExporter\` configuration:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    public MBeanExporter mbeanExporter(
            CacheManagementFacade cacheFacade
    ) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "primaryCacheManagement",
            cacheFacade
        ));
        exporter.setNamingStrategy(
            new StableNamingStrategy()
        );

        return exporter;
    }
}
\`\`\`

This is an **explicit configuration path instead of the default annotation-driven exporter**. Avoid enabling \`@EnableMBeanExport\` at the same time as another exporter registering the facade under the same ObjectName unless duplicate handling has been designed.

In simple cases, declaring explicit ObjectNames via \`@ManagedResource\` is usually sufficient. A custom naming strategy fits better when enforcing conventions across many MBeans.

## 9. Spring Bean Name Is Not ObjectName

A Spring bean may be named:

\`\`\`text
primaryCacheManagement
\`\`\`

The corresponding JMX ObjectName:

\`\`\`text
app.monitoring:type=Cache,name=primary
\`\`\`

The two names do not need to match. A Spring bean name can change due to DI configuration while the JMX contract stays stable.

Also avoid confusing \`ObjectName\` with \`javax.management.MBeanInfo.getClassName()\`. \`MBeanInfo\` may describe a JMX adapter or implementation class depending on the model, while clients should use the ObjectName and published operation/attribute metadata to make management calls.

## 10. Impact of Spring AOP and Proxies

Spring beans can be wrapped by a JDK dynamic proxy or CGLIB proxy due to \`@Transactional\`, \`@Cacheable\`, \`@Async\`, or other advisors.

\`\`\`text
Business implementation
         |
         v
Spring AOP proxy
         |
         v
JMX exporter
\`\`\`

If the runtime class name of a proxy is used as the ObjectName, the name may contain dynamic suffixes or unstable implementation names:

\`\`\`text
com.example.CacheService$$SpringCGLIB$$...
\`\`\`

This is unsuitable as a public management interface. A JMX system should name by stable resources and verify metadata collected by the exporter from the actual bean/proxy.

At the same time, do not assume annotations on an implementation are always detected identically by a custom exporter when a JDK proxy is present. Check the export strategy and actual \`MBeanInfo\`, especially when management interfaces and implementations are separated.

## 11. Multiple Instances of the Same Class

One \`WorkerPoolFacade\` class can manage multiple pools:

\`\`\`text
WorkerPoolFacade (instance A)
WorkerPoolFacade (instance B)
WorkerPoolFacade (instance C)
\`\`\`

If identity is based solely on the class:

\`\`\`text
app.monitoring:type=WorkerPoolFacade
\`\`\`

then instances cannot be distinguished. Registering multiple MBeans with the same ObjectName in one \`MBeanServer\` can cause duplicate-registration errors.

A better convention:

\`\`\`text
app.monitoring:type=WorkerPool,name=primary
app.monitoring:type=WorkerPool,name=background
app.monitoring:type=WorkerPool,name=scheduled
\`\`\`

Or when deploying multiple nodes into the same registry:

\`\`\`text
app.monitoring:type=WorkerPool,name=primary,node=n1
app.monitoring:type=WorkerPool,name=primary,node=n2
\`\`\`

Keys like \`node\` are only needed when solving an actual identity problem. Do not automatically put \`pod UID\` or \`UUID\` values that change on every restart into ObjectNames that dashboards expect to remain stable, unless monitoring is designed for dynamic instances.

## 12. Role-Based Identity and Extensibility

A convention can include dimensions:

\`\`\`text
<domain>:type=<role>,name=<logical-name>,node=<node-id>
\`\`\`

Examples:

\`\`\`text
myapp.management:type=Queue,name=orders
myapp.management:type=Queue,name=payments
myapp.management:type=Cache,name=catalog
myapp.management:type=WorkerPool,name=ingestion,node=n1
\`\`\`

Notes:

- Domain should stay consistent across versions.
- \`type\` should be a durable management term.
- \`name\` should represent a logical role/instance.
- Extra keys must solve a real disambiguation need.
- Avoid putting passwords, tokens, or user-identifying data into names.
- Escape values containing special characters using the appropriate \`ObjectName\` API.
- Define rules for name changes and migration windows for clients.

## 13. Constructing ObjectNames Safely

Special characters such as commas, equals signs, colons, quotes, or wildcards have syntax meaning in ObjectNames.

Do not concatenate strings arbitrarily:

\`\`\`java
String rawName = userProvidedName;
String objectName =
    "app.monitoring:type=Queue,name=" + rawName;
\`\`\`

If \`rawName\` contains \`,\`, \`=\`, \`*\`, or special characters, the result may be invalid or interpreted as a pattern.

You can construct an ObjectName with a quoted value:

\`\`\`java
String rawName = "orders,high-priority";

ObjectName name = new ObjectName(
    "app.monitoring:type=Queue,name="
        + ObjectName.quote(rawName)
);
\`\`\`

If using user input, in addition to escaping, validation and length limits are needed. A valid ObjectName can still cause excessive cardinality or leak inappropriate data to monitoring systems.

## 14. Querying by Pattern Without Depending on Classes

Monitoring clients can find all queues:

\`\`\`java
ObjectName pattern = new ObjectName(
    "app.monitoring:type=Queue,*"
);

Set<ObjectName> names =
    connection.queryNames(pattern, null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

The pattern is based on **resource type**, without needing to know which Java class implements the queue. Clients can then read attributes defined in the shared management contract.

\`queryNames\` returns a snapshot of currently registered MBeans; if a new MBean appears later, the client must re-query or track registry lifecycle.

Distinguish:

\`\`\`text
app.monitoring:type=Queue
\`\`\`

which is an exact ObjectName with no additional properties, from:

\`\`\`text
app.monitoring:type=Queue,*
\`\`\`

which is a property-list pattern that can match names with \`name\`, \`node\`, or other keys.

## 15. Managing Operation and Attribute Contracts

Stabilizing the ObjectName is the first step. A dashboard might also be using:

\`\`\`text
Attribute: QueueDepth
Operation: pause()
Notification: app.queue.depth.high
\`\`\`

If \`QueueDepth\` is renamed to \`PendingMessages\` without a compatibility plan, the dashboard can still break even if the ObjectName remains unchanged.

The management contract includes:

| Component | Example | Risk When Changed |
|---|---|---|
| ObjectName | \`app.monitoring:type=Queue,name=orders\` | Client cannot find MBean |
| Attribute name | \`QueueDepth\` | Metric polling fails |
| Attribute type | \`long\` | Data conversion fails |
| Operation name | \`pause\` | Invocation becomes invalid |
| Operation signature | \`setLimit(int)\` | Client sends old signature |
| Notification type | \`app.queue.depth.high\` | Listener filter misses events |
| Return type | \`java.lang.String\` | Client fails to decode as expected |

If a contract already used externally must change, you can support the old and new names side-by-side during a transition period, or release a clearly documented version.

## 16. Managing Compatibility When Renaming

Suppose an old convention is:

\`\`\`text
app.monitoring:type=LegacyQueueManager,name=orders
\`\`\`

and you want to migrate to:

\`\`\`text
app.monitoring:type=Queue,name=orders
\`\`\`

A migration strategy can include:

1. Inventory clients, dashboards, alerts, runbooks, and automation using the old name.
2. Provide the new MBean with compatible attributes/operations.
3. Maintain the old name as an alias or adapter during the transition period if infrastructure allows.
4. Announce the deprecation schedule and update clients.
5. Remove the old name in a controlled way after verifying usage has migrated.

JMX \`MBeanServer\` does not automatically create aliases from two ObjectNames alone. If both names must coexist, register an appropriate adapter or MBean under each name and manage lifecycle, registration conflicts, and state consistency.

Do not arbitrarily unregister an MBean that other tools are using just to "clean up names".

## 17. Verifying Actual Names with MBeanServer

After the Spring exporter is active, you can check:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "app.monitoring:type=Cache,name=primary"
);

System.out.println(
    "Registered: " + server.isRegistered(expected)
);
\`\`\`

The example uses the platform \`MBeanServer\`. If the exporter configures a dedicated server, access that exact server; not seeing the MBean on the platform server does not prove export failed.

Inspecting metadata:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(expected);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(
        a.getName() + ": " + a.getType()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        op.getName() + " -> " + op.getReturnType()
    );
}
\`\`\`

Snippets using \`MBeanInfo\`, \`MBeanAttributeInfo\`, and \`MBeanOperationInfo\` require importing the corresponding classes from \`javax.management\`.

Cross-checking both the ObjectName and the operation/attribute surface is how you validate the contract of a registered MBean.

## 18. Integration Tests Protecting Stable ObjectNames

You can write a test on a Spring context with JMX export to ensure the expected name exists:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class JmxNamingContractTest {

    private final MBeanServer server;

    JmxNamingContractTest(MBeanServer server) {
        this.server = server;
    }

    @Test
    void stableCacheNameIsRegistered() throws Exception {
        ObjectName expected = new ObjectName(
            "app.monitoring:type=Cache,name=primary"
        );

        assertTrue(server.isRegistered(expected));
    }
}
\`\`\`

This is an assertion template for a naming contract; in a real test, bootstrap the Spring context and provide the \`MBeanServer\` used by the exporter. Do not assume JUnit automatically injects \`MBeanServer\` into test constructors under every configuration.

When the service implementation is renamed, this test must still pass if the JMX contract remains intact.

A higher-level test can read \`MBeanInfo\` to confirm required attributes/operations still exist with compatible types.

## 19. Do Not Let Java Packages Become the Sole Management Namespace

Example of a domain taken directly from a package:

\`\`\`text
com.example.orders.infrastructure.cache:type=RedisCache
\`\`\`

This may suit short-lived developer tools, but it easily ties operational clients to module structure.

A more stable domain:

\`\`\`text
com.example.app.management:type=Cache,name=orders
\`\`\`

A JMX domain does not have to be a Java package. You can use a string following organizational and application conventions, as long as the name is valid and does not collide unintentionally.

Avoid embedding deployment versions or build hashes in ObjectNames if the goal is continuously managing a logical resource. You can expose the version as a \`Version\` attribute if observability is needed; that does not force changing the resource's identity.

## 20. Versioning in Management Contracts

When an incompatible change is genuinely required, versioning can be managed via:

- A new versioned domain, e.g., \`app.management.v2\`.
- A version key property, e.g., \`version=2\`.
- A new MBean type with a separate contract, e.g., \`type=QueueControlV2\`.
- Supporting new operations/attributes side-by-side if compatible.

There is no single versioning rule for every application. What matters is that clients can distinguish old/new contracts, and there is a migration plan rather than accidental renames during refactoring.

For internal changes that do not alter management behavior, **do not bump the version or change the ObjectName just because a class was renamed**.

## 21. Caution with Cardinality and MBean Lifecycle

Some applications create dynamic MBeans per connection, request, tenant, or worker. If ObjectNames contain random IDs or unboundedly growing properties, \`MBeanServer\` can accumulate too many names and dashboards must manage a large number of instances.

Consider:

- MBeans per logical resource rather than per short-lived object.
- Adding key properties only when operationally needed to distinguish them.
- Registering/unregistering along clear lifecycles.
- Aggregating metrics for very short-lived objects instead of exporting each individually.
- Avoiding personal information or secrets in domains/key properties.

If tens of thousands of dynamic objects need monitoring, dedicated JMX MBeans per object may not be the best design.

## 22. Common Errors

### MBean Disappears After Refactoring

The cause may be a strategy using class name, package name, Spring bean name, or proxy class. Compare before/after ObjectNames and replace with a stable identity contract.

### MBean Registered Twice

Two beans assigned the same ObjectName will conflict in one server. Check uniqueness of \`domain + key properties\`, especially when multiple instances use the same class.

### Dashboard Cannot Find It, Yet JConsole Still Sees the MBean

The MBean may have been registered under a new name. Use \`queryNames\` to locate it, then determine whether the client hard-coded the old name or whether \`MBeanServer\`/connections differ.

### Attribute Still Exists, Yet Client Errors

Check data types, readability, operation signatures, and access rights. A stable name does not substitute for management interface compatibility.

### Dynamic Proxy Name Used in ObjectName

Replace name generation with metadata or a naming strategy based on logical resources, avoiding a proxy's \`getClass().getName()\` as a contract.

### Key Value Has Commas or Special Characters

Use \`ObjectName.quote\` and input validation instead of uncontrolled string concatenation.

## 23. Practice Exercises

Suppose an application has three classes:

\`\`\`text
com.example.redis.RedisCacheService
com.example.queue.RabbitMqQueueService
com.example.workers.FixedThreadPoolService
\`\`\`

Propose ObjectNames independent of class names:

\`\`\`text
app.management:type=Cache,name=catalog
app.management:type=Queue,name=orders
app.management:type=WorkerPool,name=background
\`\`\`

Next, suppose:

- Redis cache is replaced with Caffeine.
- RabbitMQ is replaced with another message transport.
- The thread pool changes implementation.

If the management surface stays unchanged, the ObjectNames above can remain intact. Changing technology does not have to be a breaking change for JMX clients.

**Follow-up exercise:** Write a test querying ObjectName \`app.management:type=Queue,name=orders\`, checking that the MBean has attribute \`QueueDepth\` of type \`long\`, and verifying an operation \`pause()\` with an empty signature. If the internal Java method changes from \`pauseQueue\` to \`stopConsumer\` while JMX clients already invoke the operation under the name \`pause\`, how would you design a facade to preserve the contract?

## 24. Self-Check Questions

1. Why is a Java class name not a sufficiently stable identifier for JMX clients?
2. How does a Spring bean name differ from a JMX ObjectName?
3. In an ObjectName, what roles do domain, type, and name play?
4. Why do CGLIB/JDK proxies make runtime classes poorly suited for naming contracts?
5. When multiple instances share the same class, which properties should be added to avoid conflicts?
6. Why should user IDs or tokens not be put in ObjectNames?
7. How does \`@ManagedResource(objectName = "...")\` help decouple contracts from implementations?
8. When is a custom \`ObjectNamingStrategy\` needed instead of declaring names directly?
9. What errors can keeping the old ObjectName while changing an operation signature cause?
10. Should the JMX domain be changed on every build version increment? Why?

## 25. Key Takeaways

\`\`\`text
Implementation detail:
    Java class / package / proxy / bean name
                    |
                    v
         Can change during refactoring

Management contract:
    ObjectName + attributes + operations + notifications
                    |
                    v
      Needs stability and versioning
     when external clients depend on it
\`\`\`

**Core principle:** name MBeans by **management resource and role**, not merely by Java class. Maintain ObjectNames and metadata as an API contract, choose a rule-governed naming strategy, verify registered names in \`MBeanServer\`, and plan compatibility when making changes.