# Keeping Attribute Names Stable When Refactoring Methods in Spring Framework JMX

## Lesson Objectives

After this lesson, you will be able to:

- Understand how JMX determines **attribute** names from accessor methods exposed with \`@ManagedAttribute\` in Spring Framework.
- Distinguish Java method names, JMX attribute names, and MBean \`ObjectName\`s.
- Recognize that an apparent internal code refactor can alter the contract used by JMX clients.
- Keep attribute names stable when renaming business methods by using a management adapter layer or compatibility accessor.
- Establish a refactoring workflow, verify \`MBeanInfo\`, and migrate clients to avoid deployment breakage.
- Know the limitations of \`@ManagedAttribute\` and avoid relying on a nonexistent attribute-renaming parameter on this annotation.

## 1. The Problem: Method Names Are Part of the JMX Contract

In Java, renaming a method during refactoring is usually considered an internal change, especially when the IDE updates all call sites within the same repository. However, when a method is exported via JMX, its name can help determine **the attribute name seen by JConsole, monitoring tools, or custom JMX clients**.

For example:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return queue.size();
}
\`\`\`

In Spring's JMX metadata assembly model, the getter above is typically exposed as the attribute:

\`\`\`text
QueueDepth
\`\`\`

A client might call:

\`\`\`java
connection.getAttribute(objectName, "QueueDepth");
\`\`\`

If a developer renames the method to:

\`\`\`java
@ManagedAttribute
public int getPendingTasks() {
    return queue.size();
}
\`\`\`

then the exposed attribute may change from \`QueueDepth\` to \`PendingTasks\`. Clients still requesting \`QueueDepth\` will receive an error indicating the attribute does not exist, even though the business logic returns the exact same count.

**Key takeaway:** When exposing a JMX attribute, the published name is part of the management interface and must be managed like an API contract.

## 2. Three Kinds of Names Not to Confuse

| Element | Example | Role |
|---|---|---|
| Java method name | \`getQueueDepth()\` | Method in Java code |
| JMX attribute name | \`QueueDepth\` | Name passed by clients to \`getAttribute\` |
| MBean ObjectName | \`learning.jmx:type=QueueMonitor,name=Primary\` | MBean identifier within an MBeanServer |

These are distinct parts:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=QueueMonitor,name=Primary"
);

Object depth = connection.getAttribute(
    name,
    "QueueDepth"
);
\`\`\`

The ObjectName locates the target MBean. The string \`"QueueDepth"\` locates the attribute on that MBean. Renaming \`getQueueDepth()\` to \`getPendingTasks()\` does not necessarily change the ObjectName, but it can change the exposed attribute.

One MBean can have many attributes under the same ObjectName. A stable ObjectName is not enough if attribute names have changed.

## 3. What Does Spring @ManagedAttribute Expose?

\`@ManagedAttribute\` belongs to:

\`\`\`java
org.springframework.jmx.export.annotation.ManagedAttribute
\`\`\`

It marks a managed getter or setter in Spring's annotation-driven JMX model. A Spring JMX exporter with \`AnnotationJmxAttributeSource\` and a corresponding assembler reads the annotation to form \`MBeanInfo\`.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=QueueMonitor,name=Primary"
)
public class QueueMonitor {

    private volatile int depth = 0;

    @ManagedAttribute(description = "Current queue depth")
    public int getQueueDepth() {
        return depth;
    }
}
\`\`\`

Once the exporter successfully registers the MBean, clients read the \`QueueDepth\` attribute.

### An Attribute Is Not a Java Field

The JMX attribute name typically comes from the accessor naming convention, not necessarily matching a Java field:

\`\`\`java
private int pendingCount;

@ManagedAttribute
public int getQueueDepth() {
    return pendingCount;
}
\`\`\`

The exposed attribute remains \`QueueDepth\`. This is an advantage: you can refactor internal fields and implementation without changing the managed getter.

### Getters and Setters

Example:

\`\`\`java
@ManagedAttribute
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute
public void setMaxWorkers(int maxWorkers) {
    if (maxWorkers < 1 || maxWorkers > 256) {
        throw new IllegalArgumentException("Invalid maxWorkers");
    }
    this.maxWorkers = maxWorkers;
}
\`\`\`

A \`MaxWorkers\` attribute is readable and writable when the exporter metadata exposes both getter and setter. If only observation is needed, do not annotate the setter to avoid opening state modification over JMX.

### Boolean Getters

\`\`\`java
@ManagedAttribute
public boolean isPaused() {
    return paused;
}
\`\`\`

The attribute name is typically \`Paused\`, not \`IsPaused\`.

When refactoring between \`isPaused()\` and \`getPaused()\`, verify actual metadata; both can follow boolean conventions, yet specific rules and duplicate-getter cases can affect the outcome.

## 4. What Happens When an Accessor Is Renamed?

Suppose the initial code is:

\`\`\`java
@ManagedAttribute
public long getCompletedJobs() {
    return completedJobs.get();
}
\`\`\`

JMX tools read:

\`\`\`text
CompletedJobs
\`\`\`

After refactoring:

\`\`\`java
@ManagedAttribute
public long getProcessedJobs() {
    return completedJobs.get();
}
\`\`\`

The new attribute name may become:

\`\`\`text
ProcessedJobs
\`\`\`

This change can impact:

- JConsole or VisualVM displaying attributes by name.
- Custom JMX clients calling \`MBeanServerConnection.getAttribute(...)\`.
- Operational scripts querying JMX via libraries or CLI tooling.
- JMX exporter systems with mapping rules referencing attribute names.
- Dashboards/alert pipelines ingesting JMX data and relying on attribute names or metrics derived from them.
- Incident runbooks or automation explicitly specifying the ObjectName and attribute.

Renaming a Java method may be updated everywhere in the repository by an IDE, yet **JMX clients outside the repository** still hold the old string name. That is the source of silent breaking changes.

## 5. Best Practice: Separate the Management Facade from Implementation

When defining a stable JMX interface, treat managed accessors as a small **adapter** translating information from internal services to the JMX contract.

Example business service:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueService {
    private final AtomicInteger pendingTasks = new AtomicInteger();

    public int pendingTaskCount() {
        return pendingTasks.get();
    }

    public void recordPendingTask() {
        pendingTasks.incrementAndGet();
    }
}
\`\`\`

Management facade:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=QueueMonitor,name=Primary",
    description = "Stable JMX management view for queue"
)
public class QueueManagement {

    private final QueueService queueService;

    public QueueManagement(QueueService queueService) {
        this.queueService = queueService;
    }

    @ManagedAttribute(description = "Queue depth")
    public int getQueueDepth() {
        return queueService.pendingTaskCount();
    }
}
\`\`\`

Here, a developer can refactor \`pendingTaskCount()\`, change algorithms, or rename fields inside \`QueueService\` while keeping \`getQueueDepth()\` as the management API.

Spring configuration example:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {

    @Bean
    public QueueService queueService() {
        return new QueueService();
    }

    @Bean
    public QueueManagement queueManagement(QueueService queueService) {
        return new QueueManagement(queueService);
    }
}
\`\`\`

Spring manages \`QueueManagement\` and the appropriate exporter when annotation export is enabled. The ObjectName and managed getter stay stable, while the underlying implementation can evolve.

**Mindset:** The Java service API and JMX management API can evolve at different paces. There is no need to force an internal business method name to survive forever just because management clients rely on the legacy JMX name.

## 6. Can You Specify an Arbitrary Attribute Name Directly in @ManagedAttribute?

This is a common point of confusion because many other annotations and frameworks support a \`name\` parameter.

In Spring Framework, \`@ManagedAttribute\` typically supports metadata like \`description\`, \`currencyTimeLimit\`, \`defaultValue\`, \`persistPolicy\`, and \`persistPeriod\`. **There is no \`name\` attribute to directly rename the JMX attribute to an arbitrary string.**

The following example is **invalid**:

\`\`\`java
// Wrong: @ManagedAttribute has no name element.
@ManagedAttribute(name = "QueueDepth")
public int getPendingTasks() {
    return queueService.pendingTaskCount();
}
\`\`\`

Do not use this example as working code.

If you want to preserve the \`QueueDepth\` JMX attribute while renaming internal methods, retain a managed getter \`getQueueDepth()\`, use a facade/adapter, or configure management metadata through an appropriate strategy instead of assuming the annotation has a rename alias.

### Why Avoid Premature Custom Configuration?

Spring JMX provides \`MBeanInfoAssembler\`, \`AbstractReflectiveMBeanInfoAssembler\`, \`MetadataMBeanInfoAssembler\`, and other mechanisms, but customizing attribute name mapping can make the contract harder to read and maintain. Keeping a clearly named getter on a facade is usually the more transparent choice.

If a problem genuinely demands non-conventional name mapping, design and verify an assembler/custom \`MBeanInfo\` or \`DynamicMBean\` with an explicit contract.

## 7. Keeping the Old Name with a Compatibility Accessor

If a method is currently being renamed inside the exported class itself, you can retain the old accessor as an adapter:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueMonitor,name=Primary"
)
public class QueueMonitor {

    private final QueueService service;

    public QueueMonitor(QueueService service) {
        this.service = service;
    }

    // Stable public JMX contract:
    @ManagedAttribute(description = "Current queue depth")
    public int getQueueDepth() {
        return service.pendingTaskCount();
    }

    // New internal method, not exposed via JMX:
    public int getPendingTasks() {
        return service.pendingTaskCount();
    }
}
\`\`\`

Both methods can return the same value while only one is annotated. This allows refactoring internal code without changing the JMX attribute.

### Should You Annotate Both Getters?

This can support a transition period, but should be done deliberately:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return service.pendingTaskCount();
}

@ManagedAttribute
public int getPendingTasks() {
    return service.pendingTaskCount();
}
\`\`\`

Then the exporter can expose two attributes: \`QueueDepth\` and \`PendingTasks\`. This situation fits when you want old and new clients to operate concurrently during a migration period.

However, you must document:

- Which name is canonical.
- Which name is the compatibility alias.
- The planned deprecation/removal timeline for the old name.
- Which monitoring rules and scripts must be updated.
- Ensure both getters share the same semantics, unit, and data type.

Do not accidentally expose two attributes simply because of an uncontrolled refactor.

## 8. Verifying the Contract with MBeanInfo

Relying solely on \`@ManagedAttribute\` being present on a method is not enough; the real contract seen by JMX clients resides in the metadata of the registered MBean.

Example:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectAttributes {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "learning.jmx:type=QueueMonitor,name=Primary"
        );

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                "MBean not registered: " + name
            );
        }

        MBeanInfo info = server.getMBeanInfo(name);
        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                "name=%s type=%s read=%s write=%s%n",
                attribute.getName(),
                attribute.getType(),
                attribute.isReadable(),
                attribute.isWritable()
            );
        }
    }
}
\`\`\`

When run in **the exact JVM where the MBean is registered**, the output may include:

\`\`\`text
name=QueueDepth type=int read=true write=false
\`\`\`

Note: if you spawn a standalone Java process and call \`ManagementFactory.getPlatformMBeanServer()\`, you are reading the new process's MBeanServer, which does not automatically see MBeans in the application's JVM. To verify from another process, use an \`MBeanServerConnection\` via a JMX connector to the target JVM.

### What Should a Contract Test Check?

For important JMX attributes, verify:

1. The expected ObjectName is registered.
2. The legacy attribute name still exists.
3. The attribute has the right type.
4. Read/write permissions match intent.
5. Read values reflect actual state properly.
6. If migration uses aliases, both old and new names behave consistently.

A test can inspect metadata:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

boolean hasQueueDepth = java.util.Arrays.stream(
        info.getAttributes()
    ).anyMatch(a ->
        "QueueDepth".equals(a.getName())
        && "int".equals(a.getType())
        && a.isReadable()
    );

if (!hasQueueDepth) {
    throw new AssertionError(
        "JMX attribute QueueDepth contract changed"
    );
}
\`\`\`

This is a useful contract test because it catches a name change that could break clients while remaining invisible to the Java compiler.

## 9. Step-by-Step Safe Refactoring Example

Suppose the current version of the application exposes:

\`\`\`text
ObjectName: learning.jmx:type=WorkerPool,name=Primary
Attribute: ActiveThreads
Type: int
Readable: true
Writable: false
\`\`\`

Current code:

\`\`\`java
@ManagedAttribute
public int getActiveThreads() {
    return executor.getActiveCount();
}
\`\`\`

You want to rename the service representation to \`getRunningTaskCount()\`.

### Step 1 — Lock Down the Active JMX Contract

Record the ObjectName, attribute name, type, read/write semantics, unit, and meaning of the value. Locate consumers: scripts, monitoring configurations, alert rules, dashboards, runbooks.

### Step 2 — Refactor the Implementation

\`\`\`java
public int runningTaskCount() {
    return executor.getActiveCount();
}
\`\`\`

### Step 3 — Keep the Managed Getter

\`\`\`java
@ManagedAttribute(description = "Currently executing tasks")
public int getActiveThreads() {
    return runningTaskCount();
}
\`\`\`

### Step 4 — If a New API Is Needed, Create an Intentional Alias

\`\`\`java
@ManagedAttribute(description = "Currently executing tasks")
public int getRunningTaskCount() {
    return runningTaskCount();
}
\`\`\`

### Step 5 — Verify MBeanInfo

Ensure the \`ActiveThreads\` attribute still exists. If an alias is added, \`RunningTaskCount\` must also have the right type and identical semantics.

### Step 6 — Deploy and Migrate Clients

Have new clients use the new canonical name, while retaining the old name for the announced support period. Once all consumers are confirmed migrated, removing the old alias is a **managed breaking change**, not a pure refactor.

## 10. Other Changes That Can Break the Contract

The attribute name is critical, but not the only part.

### Changing the Return Type

From:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() { ... }
\`\`\`

to:

\`\`\`java
@ManagedAttribute
public long getQueueDepth() { ... }
\`\`\`

keeps the name \`QueueDepth\` but changes the type from \`int\` to \`long\`. Clients casting to \`Integer\` will fail even though the name still exists.

### Changing Units

Changing \`getRetryDelay()\` from returning milliseconds to returning seconds without changing the name or documentation is a dangerous semantic change. Keep the old unit or introduce a new name with an explicit unit, such as \`RetryDelaySeconds\`, with an intentional migration.

### Changing Read-Only to Writable

Adding:

\`\`\`java
@ManagedAttribute
public void setQueueDepth(int value) { ... }
\`\`\`

can open state modification over JMX. This is a security/operational change requiring permission and validation controls, not a harmless refactor.

### Changing ObjectName

From:

\`\`\`text
learning.jmx:type=WorkerPool,name=Primary
\`\`\`

to:

\`\`\`text
learning.jmx:type=Executor,name=Primary
\`\`\`

changes MBean identity and can prevent old clients from finding the MBean, even when the \`ActiveThreads\` attribute has not changed.

### Changing Writable/Readable Semantics

Removing a getter or adding a setter can alter an attribute's read/write permissions. Check \`MBeanAttributeInfo.isReadable()\` and \`isWritable()\`.

## 11. @ManagedAttribute with Interfaces/Proxies and Exporter Configuration

In Spring Framework, JMX metadata is typically processed by:

- \`AnnotationJmxAttributeSource\`: reads annotations.
- \`MetadataMBeanInfoAssembler\`: constructs MBean metadata.
- \`MetadataNamingStrategy\`: selects ObjectNames when using annotation metadata.
- \`MBeanExporter\`: registers MBeans into the server.
- \`@EnableMBeanExport\` or \`<context:mbean-export />\`: activates annotation-driven configuration.

If a bean has a proxy from AOP, Transactional, or other mechanisms, the exporter must recognize metadata from the appropriate class/target. When refactoring classes or interfaces, verify annotation effectiveness via actual metadata, especially if moving \`@ManagedAttribute\` between an interface and its implementation.

Do not rely solely on Java reflection on the class while overlooking how the Spring assembler handles proxies.

**Principle:** The JMX contract must be confirmed via \`MBeanInfo\` after Spring exports the bean, as that is the final result consumed by clients.

## 12. When to Maintain the Legacy Accessor Long-Term

Keeping a managed accessor with the legacy name is often sensible when:

- The name is already published in runbooks or critical monitoring systems.
- Multiple teams/units consume JMX and cannot upgrade simultaneously.
- The attribute is used in alerting, automation, or SRE playbooks.
- The old name, though no longer matching internal naming, remains stable and not semantically wrong.
- The cost of maintaining a wrapper getter is tiny compared to the risk of breaking compatibility.

For example, a service changes terminology from "job" to "task," yet \`CompletedJobs\` remains a widespread management metric. If semantics are unchanged, keeping the legacy management name can be a good choice.

If semantics truly change, do not swap meaning under the old name. Publish a new attribute and run a transparent migration.

## 13. Anti-Pattern: Refactoring Classes and Changing the JMX Contract Simultaneously

A change like the following can cause outages:

**Before:**

\`\`\`java
@ManagedAttribute
public int getActiveSessions() { ... }
\`\`\`

**After:**

\`\`\`java
@ManagedAttribute
public int getOpenConnections() { ... }
\`\`\`

If consumers read \`ActiveSessions\`, entire dashboards or scripts can stop collecting data immediately upon deployment.

Safe approach when the value is identical:

\`\`\`java
@ManagedAttribute
public int getActiveSessions() {
    return countOpenConnections();
}

public int countOpenConnections() {
    // Implementation can be refactored separately.
    return connectionRegistry.activeCount();
}
\`\`\`

During a rename transition, if you want to expose both, annotate the new accessor intentionally, recognizing it as a management API expansion.

**Distinction:** When two terms are no longer business-equivalent, creating a disguised alias can lead to misleading data. In that case, redefine the contract and perform a versioned migration or announce a breaking change.

## 14. Checklist When Refactoring ManagedAttribute

Verification checklist:

| Question | How to Check |
|---|---|
| Did ObjectName change? | Compare names before/after export |
| Does the legacy attribute name still exist? | \`getMBeanInfo().getAttributes()\` |
| Is the type preserved? | \`MBeanAttributeInfo.getType()\` |
| Are readable/writable flags preserved? | \`isReadable()\`, \`isWritable()\` |
| Are semantics and units preserved? | Read values with test data |
| Do external clients use the old string name? | Search monitoring rules, scripts, runbooks |
| Is there a new alias? | Check metadata and documentation |
| Did proxy/assembler behavior change from refactoring? | Inspect \`MBeanInfo\` after starting Spring context |
| Were new sensitive management operations introduced? | Review JMX surface and access permissions |

For internal-only code changes, if all factors above remain stable, the JMX contract is preserved.

## 15. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| \`AttributeNotFoundException\` after deploy | Getter renamed, changing attribute name | Keep compatibility getter or migrate consumers |
| JConsole shows new attribute, old name missing | Annotated accessor refactored directly | Add adapter accessor with legacy name |
| Dashboard loses series | JMX exporter mapping references legacy attribute | Restore contract or update mapping in controlled rollout |
| Client cast failure | Getter changed \`int\` to \`long\` or different Open Type | Check type/semantics in \`MBeanInfo\` |
| Attribute unintentionally writable | Newly annotated setter | Review read/write metadata and permissions |
| Annotated getter not visible | Bean not exported, annotation lost on proxy/refactor, or wrong assembler | Check \`MBeanExporter\` and \`MBeanInfo\` |
| \`@ManagedAttribute(name=...)\` fails to compile | Annotation lacks \`name\` element | Use stable accessor or custom metadata strategy |
| Client uses right name, wrong MBean | ObjectName changed or connected to wrong JVM | Verify ObjectName, MBeanServer, and connector |
| Two equivalent attributes return different results | Aliases implemented inconsistently | Delegate both to the same data source, verify semantics |
| Alias removed too early | Consumers not yet migrated | Follow a clear deprecation/migration plan |

## 16. Practice Exercises

### Exercise 1 — Predict Attribute Names

Given the methods:

\`\`\`java
@ManagedAttribute
public int getPendingJobs() { return 10; }

@ManagedAttribute
public boolean isPaused() { return false; }

@ManagedAttribute
public long getTotalErrors() { return 5L; }
\`\`\`

Predict the attribute names.

**Answer:** \`PendingJobs\`, \`Paused\`, \`TotalErrors\`.

### Exercise 2 — Refactor Without Breaking Compatibility

Initially:

\`\`\`java
@ManagedAttribute
public int getCurrentConnections() {
    return pool.getActiveCount();
}
\`\`\`

Requirement: change the service interface to call \`activeConnectionCount()\` while JMX clients continue reading \`CurrentConnections\`.

**Approach:** Keep \`getCurrentConnections()\` as a compatibility accessor calling the new service method internally. No need to change the attribute name.

### Exercise 3 — Spot the Breaking Change

A patch changes:

\`\`\`java
@ManagedAttribute
public long getRequestCount() { ... }
\`\`\`

to:

\`\`\`java
@ManagedAttribute
public long getProcessedRequests() { ... }
\`\`\`

Describe the impact on a client calling \`getAttribute(name, "RequestCount")\`. Propose two transition strategies:

1. Keep the \`getRequestCount()\` getter as a compatibility layer.
2. During migration, expose both \`RequestCount\` and \`ProcessedRequests\`; announce the removal timeline for the legacy name.

### Exercise 4 — Contract Test

Write a check against \`MBeanInfo\` ensuring \`QueueDepth\` remains a read-only \`int\` attribute. Then intentionally rename the getter and observe the test failing; fix it using an adapter.

### Exercise 5 — Design Analysis

A team wants to rename \`getCpuUsagePercent()\` to \`getCpuUsage()\` while simultaneously changing the return range from 0–100 to 0–1.

Answer: why is this more than just a rename? How would you preserve the old name, introduce the new attribute, and document units so clients are not misled?

## 17. Conclusion

- **A JMX attribute name is part of the management API contract.**
- With Spring \`@ManagedAttribute\`, names are typically derived from getter/setter methods following JavaBeans/JMX rules.
- Refactoring an annotated method can change the attribute name even when business logic is unchanged.
- \`@ManagedAttribute\` does not provide a \`name\` parameter to arbitrarily rename attributes.
- Maintaining a **management facade/compatibility accessor** lets you refactor internal code while keeping JMX names stable.
- When changing the contract intentionally, use a planned migration rather than silent renaming.
- Verify through \`MBeanInfo\` after the Spring exporter runs and cross-check dependent clients.

## References

- Spring Framework JMX Reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework ManagedAttribute API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework MetadataMBeanInfoAssembler API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Java SE 21 MBeanAttributeInfo API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 MBeanServer API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
