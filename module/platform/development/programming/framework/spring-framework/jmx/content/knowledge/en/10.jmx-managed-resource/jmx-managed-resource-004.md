# Where currencyTimeLimit and Persistence Metadata Still Fit in Spring JMX ManagedResource

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the meaning of **\`currencyTimeLimit\`** in JMX metadata and distinguish "freshness" metadata from an actual caching mechanism.
- Recognize the **\`persistPolicy\`**, **\`persistPeriod\`**, **\`persistName\`**, and **\`persistLocation\`** fields in the Model MBean descriptor model related to persistence.
- Determine when Spring Framework's \`@ManagedResource\` annotation can supply these values to **ModelMBeanInfo** and **Descriptor**.
- Understand that declaring metadata does not mean Spring or the JVM automatically provides application-grade caching, snapshots, storage, and durability suitable for every application.
- Distinguish metadata values at **resource**, **attribute**, and **operation** levels; inspect actually exported metadata using \`MBeanServer.getMBeanInfo\`.
- Decide when to use legacy JMX metadata, when to implement caching/persistence yourself in a service, or when to use modern metrics and configuration systems.
- Avoid operational mistakes caused by misunderstanding \`currencyTimeLimit\`, state persistence policies, and MBean lifecycles in Spring applications.

## 2. Context: ManagedResource and Model MBean

In Spring Framework, \`@ManagedResource\` marks a bean as a resource eligible for JMX export when the application configures **\`MBeanExporter\`** with an appropriate annotation-reading mechanism. Together with \`@ManagedAttribute\` and \`@ManagedOperation\`, Spring can construct management metadata for the bean.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Cache,name=Products",
    description = "Cache management resource"
)
public class CacheManagement {
    // ...
}
\`\`\`

Several \`@ManagedResource\` attributes have historical names such as \`currencyTimeLimit\`, \`persistPolicy\`, \`persistPeriod\`, \`persistName\`, and \`persistLocation\`. They originate from the **JMX Model MBean metadata** model, specifically descriptor fields describing how management, caching, or persistence might be handled.

Separate three layers:

\`\`\`text
Spring bean / application service
          |
          | @ManagedResource, @ManagedAttribute,
          | @ManagedOperation
          v
Spring JMX exporter + metadata assembler
          |
          | translates info into MBeanInfo,
          | ModelMBeanInfo / Descriptor
          v
MBeanServer / Model MBean
          |
          | JMX client queries metadata
          v
JConsole, custom JMX client, management tool
\`\`\`

Annotations are **descriptive inputs**. Actual observed behavior depends on the Spring exporter, assembler, ModelMBean type, JMX version, configuration, and how clients use metadata.

**Do not infer that simply adding an annotation sets up full application-level business caching or persistence.**

## 3. What Is currencyTimeLimit?

\`currencyTimeLimit\` is a standard descriptor field in JMX Model MBeans, related to how long a value is considered fresh enough to reuse. This field is typically expressed in **seconds** and can appear on the descriptor of an attribute, operation, or MBean.

In the Model MBean model, \`currencyTimeLimit\` affects the policy for reusing an already-cached value versus invoking the underlying data source again, according to the semantics of the JMX Model MBean implementation.

One way to visualize this:

\`\`\`text
Client calls getAttribute("CacheSize")
                 |
                 v
      Model MBean checks descriptor
                 |
           currencyTimeLimit
                 |
           +-----+------+
           |            |
     cached value   needs refresh
     still valid?   or uncached
           |            |
           v            v
    return old value  call source getter
                         |
                         v
                    update value
                         |
                         v
                    return to client
\`\`\`

Do not assume every **Standard MBean**, **MXBean**, or Java getter uses this field. It is specifically meaningful when running through a Model MBean or an implementation that actually interprets descriptors. If an MBean is exported via another mechanism, the descriptor may only be passive metadata or absent altogether.

### 3.1. Common Values

In JMX Model MBean semantics, commonly encountered values are:

| Value | Common Meaning |
| --- | --- |
| \`-1\` | No caching: fetch a fresh value when needed. |
| \`0\` | Cached value may be retained indefinitely without time-based expiration. |
| Positive number \`N\` | Cached value is considered valid for \`N\` seconds. |

This is Model MBean convention; check the actual descriptor and the implementation in use. In particular, \`0\` does not mean "refresh every 0 seconds"; in this model it represents an infinite cache policy, which can produce long-lived stale values if there is no invalidation mechanism.

### 3.2. Example Reading Changing State

Suppose a bean has a getter:

\`\`\`java
public long getQueueDepth() {
    return queue.size();
}
\`\`\`

If a Model MBean applies \`currencyTimeLimit=15\` on the attribute, closely spaced reads may receive the same cached value even though the queue has changed. This may suit moderately changing operational metrics, but is unsuitable for figures requiring immediate freshness.

In a dashboard polling continuously:

\`\`\`text
12:00:00   actual queue depth = 20 -> JMX reads 20
12:00:05   actual queue depth = 50 -> JMX may still return 20
12:00:16   actual queue depth = 12 -> JMX re-fetches and returns 12
\`\`\`

This illustrates a caching policy, not a guarantee of exact refresh timing: when data is re-fetched still depends on read timing, the descriptor, and the implementation.

### 3.3. What currencyTimeLimit Does Not Do

- Does not enable HTTP caching, Spring Cache, or business data caching.
- Does not guarantee all JMX clients synchronize refreshes on a fixed schedule.
- Does not automatically turn an expensive getter into a metering system with backpressure.
- Does not govern the TTL of Redis, Caffeine, Ehcache, or external caches.
- Does not guarantee thread safety or snapshot consistency of getter code.
- Does not replace designing metrics data with explicit timestamps or freshness.

Therefore, when optimizing a JMX getter, consider the data source, computation cost, cache scope, and operators' freshness requirements together.

## 4. Resource, Attribute, and Operation Metadata

Spring JMX annotations exist at multiple levels. Where metadata is placed determines which management element receives the descriptor field.

**Resource-level** uses \`@ManagedResource\`, describing the MBean as a whole:

\`\`\`java
@ManagedResource(
    objectName = "com.example:type=Cache,name=Products",
    currencyTimeLimit = 10
)
public class CacheManagement {
    // ...
}
\`\`\`

**Attribute-level** uses \`@ManagedAttribute\`, describing a specific attribute:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;

@ManagedAttribute(
    description = "Number of cache entries",
    currencyTimeLimit = 5
)
public int getEntryCount() {
    return cache.size();
}
\`\`\`

**Operation-level** uses \`@ManagedOperation\` to describe an operation; metadata attributes supported by Spring depend on the annotation type and version. With Model MBeans, currencyTimeLimit can also belong to an operation descriptor exposed by the JMX Model MBean.

Key distinctions:

| Level | Usage Example | Meaning to Verify |
| --- | --- | --- |
| MBean/resource | \`@ManagedResource.currencyTimeLimit\` | General metadata for the resource. |
| Attribute | \`@ManagedAttribute.currencyTimeLimit\` | Metadata applied specifically to a single attribute. |
| Operation | Operation descriptor | May affect operation result caching strategy if supported by the Model MBean. |

When setting both resource-level and attribute-level values, do not guess precedence rules. Inspect the generated \`ModelMBeanInfo\` and descriptors in the running Spring/JMX version, then test attribute reading behavior.

## 5. What Is Persistence Metadata?

Persistence descriptor fields in Model MBeans describe **state-saving policies and locations** that an implementation may use. This is a different concept from transactions, database persistence, or Spring Data configuration.

Common fields:

| Field | General Meaning |
| --- | --- |
| \`persistPolicy\` | Policy for when or under what condition to persist. |
| \`persistPeriod\` | Persistence interval, typically in seconds when the policy requires a period. |
| \`persistName\` | Suggested name for the stored object/file. |
| \`persistLocation\` | Suggested location for storage. |

For Model MBeans per the JMX specification, \`persistPolicy\` can take values indicating how storage is triggered, such as \`Never\`, \`OnUpdate\`, \`OnTimer\`, \`NoMoreOftenThan\`, \`Always\`, or policies supported by the implementation.

However, **actual persistence capability depends on the ModelMBean implementation**, save/restore hooks, file permissions, storage mechanisms, and lifecycle. There is no guarantee that populating a descriptor will create a file or database record as expected.

### 5.1. persistPolicy

\`persistPolicy\` describes *when* a value or state should be saved:

- \`Never\`: do not request persistence under this policy.
- \`OnUpdate\`: tie saving to updates.
- \`OnTimer\`: time/periodic-based policy.
- \`NoMoreOftenThan\`: throttle persistence frequency.
- \`Always\`: describes frequent persistence according to implementation semantics.

Policy names do not replace checking the code and documentation of the Model MBean actually in use.

### 5.2. persistPeriod

\`persistPeriod\` supplies the time parameter for periodic policies, usually in seconds in the Model MBean descriptor model. If persistPolicy does not use a period, this field may have no significant effect.

Example of configuration intent:

\`\`\`text
persistPolicy = OnTimer
persistPeriod = 60
\`\`\`

Understand this as **policy request/selection metadata**, not a Spring \`@Scheduled(fixedRate=...)\` task schedule, and it does not guarantee a background timer is writing files.

### 5.3. persistName and persistLocation

These two fields can describe the name and location for saving state. However, using them to construct file paths and create storage resources is the responsibility of the implementation.

Example of metadata intent:

\`\`\`text
persistName     = cache-management.snapshot
persistLocation = /var/lib/app/jmx
\`\`\`

This is only an example of a name/path on a Unix-like host. Do not put secrets or sensitive data directly into descriptors. On Windows, containers, or cloud systems without stable local disks, paths must be determined according to the deployment environment.

## 6. What Values Does @ManagedResource Offer?

When working with Spring JMX, \`@ManagedResource\` provides identity/description attributes such as \`objectName\`, \`description\`, and certain fields related to Model MBean descriptors such as \`currencyTimeLimit\`, \`persistPolicy\`, \`persistPeriod\`, \`persistName\`, and \`persistLocation\` depending on the API version.

Descriptive example:

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example:type=Maintenance,name=Cache",
    description = "Cache maintenance resource",
    currencyTimeLimit = 5,
    persistPolicy = "Never"
)
public class CacheMaintenanceAdmin {

    // Exported attributes/operations require
    // @ManagedAttribute/@ManagedOperation or
    // the corresponding assembler and configuration.
}
\`\`\`

**Note when using Spring 6.x:** the API may vary across minor versions; when applying to code, consult the Javadoc of the running Spring version to verify exact attribute names and default values. These fields stem from JMX Model MBean metadata; do not treat them as the Spring Cache abstraction.

An annotation on a class also does not guarantee export by itself. An MBeanExporter (or appropriate auto-configuration) must select that class along with an assembler supporting annotation metadata.

## 7. Configuring Exporter and Metadata Assembler

For \`@ManagedResource\` and \`@ManagedAttribute\` to be interpreted, Spring typically uses \`AnnotationJmxAttributeSource\` together with \`MetadataMBeanInfoAssembler\`.

Configuration example:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfiguration {

    @Bean
    public MBeanExporter exporter(CacheManagementBean bean) {
        AnnotationJmxAttributeSource attributeSource =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(attributeSource);

        MetadataNamingStrategy namingStrategy =
            new MetadataNamingStrategy();
        namingStrategy.setAttributeSource(attributeSource);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setBeans(Map.of("cacheManagementBean", bean));
        return exporter;
    }
}
\`\`\`

This is an illustrative configuration showing how metadata travels from annotations to MBeanInfo. In applications already using Spring Boot JMX auto-configuration, avoid creating an additional exporter with the same \`ObjectName\` without understanding ownership; \`InstanceAlreadyExistsException\` may occur.

\`CacheManagementBean\` in the example is an application-provided bean; you must declare its actual implementation and annotations. In a Spring application, you may prefer \`@EnableMBeanExport\` or the corresponding Spring configuration when it fits the project.

## 8. Inspect Runtime Metadata Instead of Guessing

The best source of truth for what a JMX client can see is \`MBeanInfo\` from the running MBeanServer.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.Descriptor;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Maintenance,name=Cache"
);

MBeanInfo info = server.getMBeanInfo(name);

Descriptor descriptor = info.getDescriptor();
System.out.println(
    "MBean currencyTimeLimit = "
        + descriptor.getFieldValue("currencyTimeLimit")
);
System.out.println(
    "MBean persistPolicy = "
        + descriptor.getFieldValue("persistPolicy")
);
\`\`\`

The snippet above reads the descriptor at the MBean level. Some fields may be placed on an attribute or operation descriptor rather than the MBean descriptor. Therefore, checking only \`info.getDescriptor()\` may not be enough.

### 8.1. Reading Each Attribute's Descriptor

\`\`\`java
import javax.management.MBeanAttributeInfo;

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    Descriptor d = attribute.getDescriptor();

    System.out.printf(
        "%s: currencyTimeLimit=%s, persistPolicy=%s%n",
        attribute.getName(),
        d.getFieldValue("currencyTimeLimit"),
        d.getFieldValue("persistPolicy")
    );
}
\`\`\`

### 8.2. Reading Operation Descriptors

\`\`\`java
import javax.management.MBeanOperationInfo;

for (MBeanOperationInfo operation : info.getOperations()) {
    Descriptor d = operation.getDescriptor();

    System.out.printf(
        "%s: currencyTimeLimit=%s%n",
        operation.getName(),
        d.getFieldValue("currencyTimeLimit")
    );
}
\`\`\`

If a field returns \`null\`, it may be because the field was not set, the descriptor lacks that entry, or the export mechanism did not produce Model MBean metadata as expected. Do not conclude that Spring has automatically enabled or disabled an actual cache solely from this \`null\`.

### 8.3. Checking MBean Info Type

\`\`\`java
import javax.management.modelmbean.ModelMBeanInfo;

System.out.println(
    "Is ModelMBeanInfo = " + (info instanceof ModelMBeanInfo)
);
\`\`\`

If \`true\`, you can inspect descriptors further according to Model MBean semantics. If \`false\`, do not apply all Model MBean rules to that MBean.

## 9. Practical Example: Choosing currencyTimeLimit for Metrics

Suppose a Spring service retrieves figures from a queue:

\`\`\`java
public interface QueueStatsService {
    long pendingMessages();
    long processedMessages();
    boolean isHealthy();
}
\`\`\`

A JMX adapter has lightweight getters:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example:type=Queue,name=Orders",
    description = "Order queue monitoring"
)
public class OrderQueueManagement {

    private final QueueStatsService stats;

    public OrderQueueManagement(QueueStatsService stats) {
        this.stats = stats;
    }

    @ManagedAttribute(
        description = "Current pending messages",
        currencyTimeLimit = 5
    )
    public long getPendingMessages() {
        return stats.pendingMessages();
    }

    @ManagedAttribute(
        description = "Total processed messages",
        currencyTimeLimit = -1
    )
    public long getProcessedMessages() {
        return stats.processedMessages();
    }

    @ManagedAttribute(
        description = "Whether the queue is healthy",
        currencyTimeLimit = -1
    )
    public boolean isHealthy() {
        return stats.isHealthy();
    }
}
\`\`\`

Here the value \`5\` on the PendingMessages attribute expresses the intent to accept cached data for roughly 5 seconds if the Model MBean implementation applies the descriptor. With \`-1\` values, the intent is not to cache at the Model MBean layer.

**Things to verify**:
1. Does the Spring exporter actually use Model MBeans and a metadata assembler that reads annotations?
2. Does each attribute's descriptor contain the expected currencyTimeLimit?
3. Do values read via MBeanServer over short intervals reflect the desired caching policy?
4. Should caching live in the service/collector instead of JMX, so it has timestamps, consistent behavior, and easy testability?

A modern monitoring system usually prefers having the metrics source emit an explicit snapshot; the JMX getter simply reads the current value from it. \`currencyTimeLimit\` remains useful when compatibility or verified Model MBean caching behavior is needed by design.

## 10. Persistence Metadata Example and Limitations

Consider a management object for a job's state:

\`\`\`java
@ManagedResource(
    objectName = "com.example:type=Job,name=Importer",
    persistPolicy = "OnUpdate",
    persistName = "importer-state",
    persistLocation = "/var/lib/app/jmx"
)
public class ImportJobManagement {
    // ...
}
\`\`\`

The metadata intent is to support a persistence policy tied to updates and a state storage location. However:

- A standalone \`MBeanExporter\` does not replace a database or storage service.
- There is no guarantee the standard Model MBean in use will write to this file simply because the descriptor contains a path.
- If the Model MBean implementation does not support persistence, the declaration may create no storage at all.
- Business state persistence usually requires transactions, schema migrations, concurrency, durability, and recovery; those cannot be solved by JMX metadata alone.
- With containers/cloud, local paths may be lost on restart unless backed by a managed volume.

Therefore, if the problem is **saving a job's checkpoint**, implement it in the appropriate service/database. JMX persistence metadata is mainly intended for Model MBeans or management frameworks that actually include a corresponding persistence engine.

## 11. Design History and Why These Fields Still Exist

JMX Model MBeans were built to describe managed resources via standard metadata, allowing tools and management agents to use descriptors to drive caching, persistence, and management information under a single contract.

In Spring JMX, \`@ManagedResource\` and \`ManagedResource\` metadata retain these fields to support ModelMBean semantics and compatibility with traditional Java management systems.

These fields **still fit** when:

- The application uses Model MBeans or a JMX agent that interprets descriptors according to JMX semantics.
- Compatibility is required with legacy enterprise management tools reading currencyTimeLimit/persistPolicy.
- There is a specific requirement to throttle how often a Model MBean invokes a getter and caching behavior has been tested.
- A Model MBean implementation has a persistence engine supporting descriptors and the application needs to follow that contract.
- You want to describe/publish metadata for standard JMX clients, even if not every feature is actively used.

They are **less suitable** when:

- Using simple Standard MBeans/MXBeans with direct getters where Model MBean caching is not applied.
- The application only needs metrics scraped by a collector for Prometheus/OpenTelemetry.
- Business caching, Redis TTLs, or the Spring Cache abstraction are needed.
- Job states, transactions, checkpoints, or critical data require strict durability mechanisms.
- Systems run on ephemeral containers without a compatible persistence backend.
- No client or implementation reads or interprets these descriptor fields.

An annotation's continued existence in the API does not mean it is the best solution for every modern problem.

## 12. Comparison with Spring Cache and Metrics Systems

| Need | Suitable Tool | Why |
| --- | --- | --- |
| Limit repeated attribute reads via Model MBean | \`currencyTimeLimit\` if supported by implementation | Standard JMX metadata; behavior depends on Model MBean. |
| Cache service/DAO data | Spring Cache, Caffeine, Redis | Manages keys/TTL/invalidation in the business layer. |
| Collect real-time/near-real-time metrics | Micrometer, OpenTelemetry, metrics collectors | Metrics carry tags, timestamps, aggregation, and pipelines. |
| Save batch job checkpoints | Database or durable storage | Provides transactions, recovery, and clear schemas. |
| Save legacy Model MBean state | \`persistPolicy\` + supporting implementation | Compatible with management engines that implement persistence semantics. |
| Inspect MBean configuration | JMX \`MBeanInfo\` / \`Descriptor\` | Reads runtime management metadata. |

A JMX attribute reading \`getCacheHitRate()\` can still pull data from Caffeine/Redis through a separate service; JMX metadata does not govern that cache's TTL.

## 13. Risks of Misusing currencyTimeLimit

### 13.1. Stale Data Leading to Wrong Decisions

If \`currencyTimeLimit=0\` leads to non-expiring caching, a \`Healthy=true\` state may stay true after the system has already failed, depending on Model MBean behavior. Therefore, statuses used for control or incident response generally require tightly controlled freshness.

### 13.2. Relying on Cache Without Recording Timestamps

A JMX client may see a value without knowing when it was computed. Consider exposing \`LastSampleEpochMillis\` or \`LastUpdatedAt\` as well to distinguish stale data from fresh data.

### 13.3. Multi-Layer Caching

Caching can exist in the service, in the Model MBean, and in the collector. Stacked TTLs can make dashboards lag more than expected. Do not optimize by adding \`currencyTimeLimit\` without examining the entire data path.

### 13.4. When a Getter Has Side Effects

JMX getters should minimize side effects. If a getter refreshes data or mutates state, Model MBean result caching can change how often that code executes, causing unpredictable behavior.

## 14. Risks of Misusing Persistence Metadata

- **Confusion about durability:** metadata does not guarantee files or transactions exist.
- **Resource impact:** an actual persistence engine can introduce I/O, locking, or increased write frequency.
- **Non-portable paths:** \`persistLocation\` depends on OS, container images, and volume mappings.
- **Filesystem permissions:** if real writing occurs, files and process accounts must be secured.
- **Data exposure:** do not persist secrets or user data through an uncontrolled JMX mechanism.
- **Unclear recovery:** the ability to reload state after restart must be tested independently, not inferred from descriptor fields.
- **Consistency:** persisting state across multiple components requires explicit transaction boundaries.

A practical rule: if nothing actually processes \`persistPolicy\`, adding this field is more likely to mislead readers and operational tools than to provide value.

## 15. Verifying Cache Semantics with Controlled Experiments

You can create a bean with a counter of how many times the getter is invoked:

\`\`\`java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example:type=Counter,name=GetterProbe"
)
public class GetterProbe {

    private final AtomicInteger invocations =
        new AtomicInteger();

    @ManagedAttribute(currencyTimeLimit = 5)
    public int getValue() {
        return invocations.incrementAndGet();
    }
}
\`\`\`

After the exporter registers the MBean, a client reads via \`MBeanServer\`:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example:type=Counter,name=GetterProbe"
);

Object first = server.getAttribute(name, "Value");
Object second = server.getAttribute(name, "Value");

System.out.println(first);
System.out.println(second);
\`\`\`

If the Model MBean executes caching according to the descriptor, two consecutive reads may return the same value. If the getter is called every time, the values will differ. When running the experiment, you should:

1. Read the descriptor of the \`Value\` attribute to verify the actual metadata.
2. Read twice within an interval shorter than the TTL.
3. Wait past the TTL and read again.
4. Observe the number of getter executions and refresh timestamps.
5. Ensure no other caching layer affects the measurement.

This is an experiment to verify the behavior of your runtime environment, not a replacement for the Javadoc/Model MBean specification.

## 16. Practical Decision Guide

When encountering \`currencyTimeLimit\` or \`persistPolicy\` in a Spring Framework project, ask:

1. **What kind of MBean is it?** Standard MBean, MXBean, Dynamic MBean, or Model MBean?
2. **Where does metadata come from?** Spring annotations, XML, custom assembler, or manually constructed \`Descriptor\`?
3. **Which implementation consumes the metadata?** The JVM's Model MBean implementation, Spring's exporter, or a custom agent?
4. **What is the real goal?** Reduce getter load, communicate freshness metadata, or persist state?
5. **Which clients care?** JConsole, a JMX collector, a custom JMX client, or an enterprise tool?
6. **Has the behavior been tested?** Inspect MBeanInfo/descriptors, test caching or persistence in a lab environment.
7. **Is there a clearer alternative?** Cache service, metrics collector, configuration management, or database.
8. **Is there a risk of data loss or stale information?** Define SLAs for freshness and durability.

If no consumer reads the metadata, it is better to keep configuration minimal and express caching/persistence policies directly in the layer that actually implements them.

## 17. Hands-On Exercises

### Exercise 1 — Inspect the Resource Descriptor

Create a \`@ManagedResource(currencyTimeLimit=5)\` bean, export it via \`MBeanExporter\` with \`MetadataMBeanInfoAssembler\`, read \`MBeanInfo.getDescriptor()\`, and locate the \`currencyTimeLimit\` field.

**Objective:** identify where metadata is generated.

### Exercise 2 — Attribute-Level TTL

Create a \`getValue()\` getter that increments a counter, annotate with \`@ManagedAttribute(currencyTimeLimit=5)\`. Read it via MBeanServer multiple times within 5 seconds and after 5 seconds. Record the actual implementation's behavior.

**Objective:** understand that annotations and runtime behavior must be verified together.

### Exercise 3 — Compare Standard MBean and Model MBean

Create a Standard MBean with a getter of the same meaning without using Spring's metadata assembler; compare \`MBeanInfo\` and getter invocation counts when a client polls repeatedly.

**Objective:** do not apply \`currencyTimeLimit\` to all MBean types by default.

### Exercise 4 — Persistence Metadata

Declare \`persistPolicy\`, \`persistPeriod\`, \`persistName\`, and \`persistLocation\` in an appropriate environment. Read the descriptor and check whether any real file or storage is created. If not, determine what implementation would be required for persistence to occur.

**Objective:** distinguish metadata from an actual storage engine.

### Exercise 5 — Real-World Application Design

An application has metrics \`QueueDepth\`, \`LastErrorAt\`, \`DatabaseHealthy\`, and an ingestion checkpoint. Choose where to apply caching/TTL, where to store the checkpoint, and how to expose them via JMX.

**Hint:** metrics and health states need explicit freshness; checkpoints must be stored in durable storage; JMX can serve simply as a read port.

## 18. Review Questions

**1. What unit does \`currencyTimeLimit\` use in a Model MBean descriptor?** Usually seconds, per Model MBean semantics.

**2. What does \`currencyTimeLimit=0\` mean?** In common Model MBean semantics, the cached value may be kept indefinitely over time.

**3. What does \`currencyTimeLimit=-1\` mean?** Specifies not to cache the value under Model MBean rules.

**4. Does this annotation automatically configure Spring Cache?** No. It belongs to the JMX metadata model.

**5. Is \`persistPolicy\` equivalent to \`@Transactional\`?** No. It is metadata about a Model MBean's persistence policy, not a business transaction.

**6. Does \`persistPeriod\` automatically create a \`@Scheduled\` task?** No. Any timer behavior depends on the Model MBean implementation.

**7. How do you know what metadata is actually exported?** Read \`MBeanInfo\`, \`ModelMBeanInfo\`, and the descriptors of the resource/attribute/operation on the MBeanServer.

**8. When should persistence metadata be used?** When the application has a Model MBean or management framework that actually supports and consumes it.

**9. When should a database be used instead of JMX persistence?** When durability, recovery, transactions, or critical business data are required.

**10. If JConsole shows an attribute whose value updates slowly, what should be checked?** Data source, service-layer caching, Model MBean currencyTimeLimit, collector/client polling interval, and snapshot timestamp.

## 19. Summary

\`currencyTimeLimit\` and persistence metadata in \`@ManagedResource\` are intentional artifacts of the **JMX Model MBean descriptor model**. \`currencyTimeLimit\` describes freshness/caching policy in a Model MBean context; \`persistPolicy\`, \`persistPeriod\`, \`persistName\`, and \`persistLocation\` describe state-storage intent when supported by the implementation.

They remain valuable in JMX/Model MBean systems requiring standard metadata or legacy compatibility. For modern Spring applications, verify runtime descriptors and behavior before relying on these fields; business caching, observability, and durable state storage are usually best handled by dedicated mechanisms.

## References

- Spring Framework Javadoc — \`ManagedResource\` annotation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — \`ManagedAttribute\` annotation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 — \`ModelMBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/modelmbean/ModelMBeanInfo.html
- Java SE 21 — \`Descriptor\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Descriptor.html
- Java SE 21 — \`RequiredModelMBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/modelmbean/RequiredModelMBean.html