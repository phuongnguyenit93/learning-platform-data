# Documenting the Purpose of a Managed Resource with Spring @ManagedResource

## Objectives

After this lesson, you will be able to clearly describe the **purpose, scope, and operational contract** of a JMX-managed resource in Spring Framework; know how to use the `description` attribute of `@ManagedResource` and add documentation to `@ManagedAttribute` and `@ManagedOperation`; organize `ObjectName`, units of measurement, impact level, and security notes so JMX clients can understand the resource accurately; and inspect exported metadata through `MBeanInfo`.

## 1. What Is a Managed Resource and Why Document It?

In Spring JMX, an object can be exposed as an MBean so tools such as JConsole, Java Mission Control (JMC), or monitoring agents can read state and invoke management actions. The `@ManagedResource` annotation marks the managed object, while Spring's exporter decides how to place it into `MBeanServer`.

Example:

```java
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment",
    description = "Management view for the payment processing queue"
)
public class PaymentQueueMonitor {
    // ...
}
```

`objectName` answers **“where is this resource identified?”**; `description` answers **“what is this resource for?”**. If descriptions are omitted or generic phrases like `"JMX resource"` are used, operators may see an MBean without knowing which component it manages, what scope of data it covers, what values represent normal state, and which actions cause real changes.

Documentation helps:

- Operators locate the right MBean when there are multiple beans of the same class or multiple application instances.
- Dashboards and scripts understand the meaning of attributes/operations without reading source code.
- Maintainers understand why the management interface exists and avoid renaming or breaking contracts arbitrarily.
- Reviewers distinguish data that should be exposed to JMX from sensitive secrets.
- SRE/operations teams know limits, units of measurement, reset behavior, and side effects when invoking actions.

**An MBean is an operational interface, not merely an annotated Java class.** Therefore, descriptions should be written from the perspective of a management tool user, not simply describing technical implementation details.

## 2. Role of @ManagedResource in Spring

`org.springframework.jmx.export.annotation.ManagedResource` is a class-level annotation used to declare management metadata. During annotation-based export, Spring reads this information to construct MBean metadata and assign JMX names according to configuration.

Well-documented example:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.inventory:type=Cache,name=ProductCatalog",
    description = "Observes the product catalog cache and supports controlled eviction"
)
public class ProductCatalogCacheMonitor {
    // ...
}
```

The description contains key elements:

1. **Managed target:** product catalog cache.
2. **Observation purpose:** monitoring cache state.
3. **Control capability:** allows controlled eviction.
4. **Boundary:** only the product cache, not the entire application.

When `AnnotationMBeanExporter`, `@EnableMBeanExport`, or `<context:mbean-export/>` is configured properly, this metadata can appear in `MBeanInfo.getDescription()` displayed by JMX clients.

Keep clear: **having an annotation does not mean the MBean is registered**. The bean must reside in ApplicationContext and the exporter must operate on the `MBeanServer` to which the client connects.

## 3. What Makes a Good @ManagedResource Description?

Resource purpose can be structured using the formula:

```text
[What object the resource manages]
+ [key information/controls]
+ [important scope or boundary]
```

Weak example:

```java
@ManagedResource(
    objectName = "com.example:type=Worker",
    description = "Worker MBean"
)
```

This description only repeats the name; it does not tell operators which worker it is or what role it performs.

Better example:

```java
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Billing",
    description = "Monitors billing worker throughput, backlog and pause state"
)
```

This description identifies the service, component, and observation scope. If the MBean also has operations that mutate state, represent that capability accurately:

```java
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Billing",
    description = "Billing worker pool: read execution statistics and control pause/resume"
)
```

Length is not the only criterion. The description must be **functionally accurate** and **not promise capabilities the MBean does not expose**.

## 4. Documenting from Resource Down to Attributes and Operations

Resource documentation should be an overview; concrete details must be published directly on attributes and operations.

Spring provides:

- `@ManagedResource`: describes the resource.
- `@ManagedAttribute`: describes a readable/writable attribute, especially units, source, and meaning.
- `@ManagedOperation`: describes a management operation.
- `@ManagedOperationParameter` and `@ManagedOperationParameters`: describe operation parameter names/details when needed.

Example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment",
    description = "Payment queue status and limited operator controls"
)
public class PaymentQueueAdmin {
    private volatile boolean paused;
    private volatile int pendingCount = 10;

    @ManagedAttribute(
        description = "Number of payment messages waiting to be processed"
    )
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedAttribute(
        description = "Whether intake from this payment queue is paused"
    )
    public boolean isPaused() {
        return paused;
    }

    @ManagedAttribute(
        description = "Whether intake from this payment queue is paused"
    )
    public void setPaused(boolean paused) {
        this.paused = paused;
    }

    @ManagedOperation(
        description = "Attempts to reprocess at most maxCount failed messages"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "maxCount",
            description = "Maximum messages to retry; must be between 1 and 100"
        )
    })
    public int retryFailed(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException(
                "maxCount must be between 1 and 100"
            );
        }
        // Example: in a real application, call a service to handle retries.
        return 0;
    }
}
```

In this example, `@ManagedResource` explains the overall goal, `@ManagedAttribute` explains attributes, and `@ManagedOperation` specifies the action and valid parameter range.

**Note:** setters and operations with real effects must be implemented and access-controlled. Descriptive annotations do not automatically enforce validation, authentication, or authorization.

## 5. Writing Descriptions for Metrics: Name, Unit, Scope, Timing

An observed resource often exposes metrics like `ActiveConnections`, `PendingCount`, `ErrorRate`, `TotalProcessed`, `OldestJobAgeMillis`.

Documentation should answer:

| Question | Example |
| --- | --- |
| What does the value measure? | Number of jobs waiting in the queue |
| What is the measurement scope? | Only the Payment queue of the current JVM |
| What is the unit? | Count, milliseconds, bytes, percent |
| Is the value instantaneous or cumulative? | Waiting count at read time; total since startup |
| When does it reset? | Resets on JVM startup or when an operation is called |
| What do special values mean? | `-1` if unknown, if defined by the API |
| With what latency is data updated? | Snapshot refreshed every 5 seconds |

Example:

```java
@ManagedAttribute(
    description = "Age in milliseconds of the oldest pending payment; 0 when empty"
)
public long getOldestPendingAgeMillis() {
    return oldestPendingAgeMillis;
}
```

`OldestPendingAgeMillis` self-suggests the unit; the description adds the empty case. If it cannot be computed instantaneously, clearly state that the data is a snapshot or periodically updated.

Do not describe a cumulative counter as "current request count". The difference between a **gauge** and a **counter** strongly affects how operators interpret data and configure alerts.

## 6. Documenting Operations by Impact Level

A JMX operation may be read-only, may mutate state, or may cause serious impact if misused.

Example:

```java
@ManagedOperation(
    description = "Clears in-memory statistics; does not delete persisted orders"
)
public void resetStatistics() { /* ... */ }
```

A good description answers:

1. **Verb and target:** which statistics are reset?
2. **Impact:** does it delete business data or only clear counters?
3. **Scope:** only in the current instance or across the cluster?
4. **Preconditions:** are any specific states/roles required?
5. **Result:** what value is returned or when does it fail?
6. **Repeatability:** is calling it multiple times safe or does it have side effects?

Example table:

| Operation | Insufficient Description | Helpful Description |
| --- | --- | --- |
| `clearCache()` | Clears cache | Evicts product cache entries from this JVM; subsequent requests reload data |
| `pause()` | Pauses | Stops accepting new tasks in this worker pool; running tasks continue |
| `retryFailed(int maxCount)` | Retry errors | Retries up to maxCount failed jobs; invalid if maxCount is outside 1–100 |
| `resetCounters()` | Reset | Resets local counters only; historical metrics already exported are unchanged |

`MBeanOperationInfo` `impact` metadata can categorize `INFO`, `ACTION`, `ACTION_INFO`, or `UNKNOWN`. However, impact metadata **does not replace descriptions and is not a security barrier**. Any JMX client authorized to invoke an operation can execute the action regardless of how friendly its name/description is.

## 7. ObjectName Is Also Part of Management Documentation

`@ManagedResource` supports `objectName`, for example:

```java
@ManagedResource(
    objectName = "com.example.billing:type=Cache,name=ExchangeRates",
    description = "Monitors and refreshes the exchange-rate cache for billing"
)
```

ObjectName contains a domain and key properties, helping clients find the exact resource:

```text
com.example.billing:type=Cache,name=ExchangeRates
```

Naming guidelines:

- **Domain:** module or service namespace, e.g., `com.example.billing`.
- **type:** resource type, e.g., `Cache`, `Queue`, `WorkerPool`.
- **name:** stable logical name, e.g., `ExchangeRates`.
- **instance:** add only when needed to distinguish resources in the same `MBeanServer` and when the value has stable meaning.

Names should be independent of PID, hash codes, or UUIDs regenerated on every startup if the logical resource is unchanged. Stable naming prevents dashboards and automation from breaking connections on restart.

`ObjectName` is unique **only within one `MBeanServer`**, not across all JVMs. When documentation says "current cache", specify whether it means the cache in this JVM or cluster-wide.

## 8. MBeanInfo: Where Clients See Descriptions

When Spring exports an MBean, JMX clients retrieve metadata via `MBeanServerConnection.getMBeanInfo(ObjectName)` or `MBeanServer.getMBeanInfo`.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("Resource: " + info.getDescription());

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute %s: %s%n",
        attribute.getName(),
        attribute.getDescription()
    );
}

for (var operation : info.getOperations()) {
    System.out.printf(
        "Operation %s: %s%n",
        operation.getName(),
        operation.getDescription()
    );
}
```

The example above assumes the bean was registered into the platform `MBeanServer`. If the exporter uses another server, obtain the right server. `isRegistered(name)` can be checked before `getMBeanInfo` to avoid `InstanceNotFoundException`.

UIs like JConsole/JMC may display names, descriptions, attributes, and operations in their own ways. Not every UI displays every metadata field prominently; verifying that descriptions are properly exported should still be done through the JMX API.

### Descriptions Are Not Full Documentation Replacing a Runbook

`MBeanInfo.getDescription()` is great for discovering MBeans, yet usually holds only a short descriptive string. A runbook or system documentation is still needed to cover deeper details on permissions, production impact, operational scenarios, rollback procedures, and failure modes.

## 9. Configuring Spring to Export Annotation Metadata

In Spring Framework, annotation-driven JMX export can be enabled with Java configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Or in XML:

```xml
<context:mbean-export/>
```

with the Spring context namespace properly declared.

This mechanism uses the appropriate exporter and metadata infrastructure, where `AnnotationMBeanExporter` is a key component for annotation-driven JMX. Only discovered Spring beans with matching metadata are exported; the annotation does not automatically create a remote JMX endpoint.

If the application uses a manually configured `MBeanExporter`, ensure `MetadataMBeanInfoAssembler`, `AnnotationJmxAttributeSource`, and an appropriate naming strategy are wired if you want descriptions from annotations to appear in `MBeanInfo`.

Avoid registering the same ObjectName via both a manual exporter and auto-export. Two exporters registering into the same `MBeanServer` can collide on names.

## 10. Template for Fully Documenting a Resource

You can standardize on a concise documentation template placed in source code or operational docs:

```text
ObjectName:
  com.example.orders:type=Queue,name=Payment

Purpose:
  Monitors the Payment queue in the current JVM,
  allowing backlog inspection, intake pause/resume, and bounded retries.

Scope:
  Operates only within the connected instance;
  does not automatically affect other replicas.

Attributes:
  PendingCount (int, read-only):
    Number of messages waiting at read time.
  Paused (boolean, read-write):
    Whether intake of new messages is paused.
  OldestPendingAgeMillis (long, read-only):
    Age of the oldest waiting message, in milliseconds.

Operations:
  retryFailed(maxCount):
    Attempts to reprocess at most maxCount failed messages.
    Valid parameter: 1..100.
    May cause side effects and increase queue load.

Security:
  Only authorized operational roles may execute operations.

Lifecycle:
  MBean appears when the Spring context initializes and disappears when the context closes.
```

Part of the documentation goes into annotation descriptions so clients can read it immediately; the remainder belongs in a README/runbook for operator reference.

## 11. Common Documentation Mistakes

**Overly generic description:** `"Managed service"` or `"JMX MBean"` does not tell what the resource does. Specify the business domain, scope, and allowed actions.

**Repeating the method name:** `@ManagedOperation(description = "resetStatistics")` does not clarify impact. Explain what gets reset and what does not.

**Forgetting units of measurement:** `Timeout = 5000` does not say whether it is milliseconds or seconds. Include units in the name/description.

**Confusing local and cluster state:** `ActiveWorkers` in one JVM is not implicitly the total across all replicas. Descriptions must clarify scope.

**Omitting reset behavior:** A counter may restart at 0 when the JVM restarts; users may misread dashboards if they assume a permanent cumulative total.

**Failing to warn about operations with side effects:** `clearCache`, `purgeQueue`, `shutdown`, or `rebuildIndex` must not be described as read-only information actions.

**Putting sensitive information in descriptions:** Avoid recording passwords, access tokens, sensitive internal addresses, or personal data. JMX metadata can be read by many clients.

**Outdated descriptions:** If the implementation changes without updating metadata, operators will make decisions based on wrong information. Treat descriptive content as part of the management contract maintained alongside the code.

## 12. How to Define Safe Boundaries

A `@ManagedResource` used for management should not accidentally become an API accessing all business data.

Prefer:

- Aggregated metrics, status, uptime, error counts, latency.
- Clear names and units of measurement.
- Operations with bounded parameters and defined impact.
- Descriptions that do not leak secret data.
- Stable logical ObjectNames.
- Metadata consistent with actual permissions.

Avoid:

- Attributes returning user lists, session tokens, or personal data.
- Unbounded operations that can wipe bulk data.
- Getters executing extremely heavy queries while continuously polled by JMX clients.
- Misleading descriptions like “read-only” when a setter is still exported.
- Using annotations as if they provided authorization or auditing by default.

Remote JMX requires access control, authentication, transport security, and network exposure management independent of descriptions. Good documentation supports safe operations but does not replace security mechanisms.

## 13. A Test Verifying Published Documentation

Below is an integration test outline for a bean exported by Spring as an MBean:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.lang.management.ManagementFactory;
import javax.management.*;
import org.junit.jupiter.api.Test;

class JmxMetadataTest {
    @Test
    void exposesMeaningfulResourceDescription() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);
        assertNotNull(info.getDescription());
        assertTrue(info.getDescription().contains("Payment"));

        boolean hasPendingCount = false;
        for (MBeanAttributeInfo attr : info.getAttributes()) {
            if ("PendingCount".equals(attr.getName())) {
                hasPendingCount = true;
                assertTrue(attr.getDescription().contains("waiting"));
            }
        }
        assertTrue(hasPendingCount);
    }
}
```

The test must run after the Spring context has initialized, the MBean has been registered, and the exporter uses the platform `MBeanServer`. If descriptions in code use Vietnamese, adjust the keywords searched by assertions to match the chosen language.

The purpose of the test is to verify that **metadata was exported as declared**, not to evaluate overall prose quality.

## 14. Practice Improving a Resource

Given an under-documented class:

```java
@ManagedResource(objectName = "com.example:type=Pool")
public class PoolMonitor {
    @ManagedAttribute
    public int getSize() { return 12; }

    @ManagedOperation
    public void clear() { /* ... */ }
}
```

Redesign it:

1. Set an ObjectName expressing the pool's type and logical name.
2. Add a `description` specifying which service owns the pool and whether the scope is local or cluster-wide.
3. Rename or describe `getSize()` as "active connections", "idle connections", or "configured capacity" according to its true semantics.
4. Describe which connections `clear()` affects, whether it interrupts requests, and when it may be called.
5. Inspect metadata via `MBeanInfo`, checking whether JConsole/JMC displays useful information.
6. Write a runbook for dangerous operations instead of stuffing all instructions into one annotation string.

## 15. Self-Check Questions

- How does `@ManagedResource.description` differ from `@ManagedAttribute.description`?
- Why is `"Service MBean"` not a sufficiently useful description?
- Should an attribute returning `long` document its unit and reset semantics?
- When a resource manages one replica, what scope must the description clarify?
- Where in the JMX API can you read exported descriptions?
- Why does a well-described operation still need independent authorization?
- When changing the implementation class while keeping the ObjectName, which parts of the metadata contract must be verified?

**Key takeaway:** `@ManagedResource` does not merely mark a Spring bean for JMX export; through `description` and ObjectName, it also documents the purpose of the management interface. Clearly state what the resource manages, its scope, what its figures mean, and what impact its operations have; add detailed descriptions on attributes/operations and inspect the `MBeanInfo` that JMX clients actually receive.