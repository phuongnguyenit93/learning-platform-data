# @ManagedOperation and Exposing Methods via Spring JMX

## Objectives

After this lesson, you will be able to understand how `@ManagedOperation` exposes a Java method as a **JMX operation**, configure the exporter in Spring, select methods permitted for administration, describe parameters and return values, invoke operations via `MBeanServerConnection`, distinguish operations from attributes, and handle issues related to metadata, proxies, method versions, access permissions, and performance.

## 1. What Is Exposing a Method?

A Spring bean can contain dozens of methods serving business logic. Not every method should be invocable externally via JMX.

Example service:

```java
public class JobService {
    public void enqueue(Job job) { /* business logic */ }
    public int calculatePriority(Job job) { /* ... */ return 0; }
    public void pauseIntake() { /* ... */ }
    public void resumeIntake() { /* ... */ }
}
```

The `enqueue` and `calculatePriority` methods usually belong to the internal business API. Conversely, `pauseIntake` or `resumeIntake` can be administrative actions that are meaningful during incident handling.

`@ManagedOperation` belongs to the package:

```java
org.springframework.jmx.export.annotation.ManagedOperation
```

This annotation marks a method that the Spring JMX infrastructure can export as an operation on an MBean. Operators or JMX client programs can then invoke the operation via `MBeanServer.invoke` or `MBeanServerConnection.invoke`, provided the MBean is registered successfully and the client is permitted to access it.

Example:

```java
@ManagedOperation(description = "Pauses intake of new jobs")
public void pauseIntake() {
    intakePaused = true;
}
```

**Important point:** the annotation does not open a JMX port on its own, create a new MBeanServer, or protect the invocation. You need an active Spring JMX exporter, bean registration, and appropriate JMX connection infrastructure.

## 2. Relationship Between @ManagedResource and @ManagedOperation

In Spring's annotation-driven model:

- `@ManagedResource` marks a **bean/class** as a managed resource and provides metadata such as `objectName` and `description`.
- `@ManagedAttribute` marks a getter/setter to be exposed as a JMX attribute.
- `@ManagedOperation` marks a method to be exposed as a JMX operation.
- `@ManagedOperationParameter` / `@ManagedOperationParameters` add names and descriptions for operation parameters.

Example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=Queue,name=Billing",
    description = "Billing job queue administration"
)
public class BillingQueueAdmin {
    private volatile boolean paused;

    @ManagedAttribute(description = "Whether intake is paused")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Stops accepting new billing jobs")
    public void pause() {
        paused = true;
    }

    @ManagedOperation(description = "Allows new billing jobs again")
    public void resume() {
        paused = false;
    }
}
```

With an appropriate exporter and metadata assembler, the client can see:

```text
ObjectName: com.example.jobs:type=Queue,name=Billing

Attributes:
  Paused  boolean  read-only

Operations:
  pause()   void
  resume()  void
```

`isPaused()` is an attribute because it is annotated with `@ManagedAttribute`; `pause()` and `resume()` are operations because they are annotated with `@ManagedOperation`.

This classification helps clients understand what represents observable state and what represents an executable action.

## 3. Enabling the Annotation Export Mechanism in Spring

In Spring Framework using Java configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Ensure that the `BillingQueueAdmin` class is managed by the same ApplicationContext, for example via `@Component` and component scanning, or via `@Bean`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AdminBeans {
    @Bean
    public BillingQueueAdmin billingQueueAdmin() {
        return new BillingQueueAdmin();
    }
}
```

In XML configuration, the exporter can be enabled with:

```xml
<context:mbean-export/>
```

with the Spring `context` namespace declared properly.

`@EnableMBeanExport` and `<context:mbean-export/>` are ways to configure the annotation-driven export infrastructure; `AnnotationMBeanExporter` provides the mechanism for recognizing metadata from annotations.

Do not enable multiple independent exporters that register the same `ObjectName` without a clear ownership strategy. Conflicts within an `MBeanServer` can cause `InstanceAlreadyExistsException`.

## 4. An Example with Parameters and a Return Value

An operation often needs parameters, for example retrying up to a certain number of failed jobs.

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=RetryAdmin,name=Billing",
    description = "Limited retry controls for failed billing jobs"
)
public class RetryAdmin {
    @ManagedOperation(
        description = "Retries up to maxCount failed billing jobs"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "maxCount",
            description = "Maximum jobs to retry (1..100)"
        )
    })
    public int retryFailed(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException("maxCount must be 1..100");
        }

        // In practice: call the retry service and return the number of accepted jobs.
        return Math.min(maxCount, 3);
    }
}
```

What a JMX client needs to know:

| Component | Common Metadata |
| --- | --- |
| Operation name | `retryFailed` |
| Number of parameters | 1 |
| Parameter type | `int` |
| Parameter name | `maxCount`, if the exporter publishes this metadata |
| Return type | `int` |
| Description | Retries up to `maxCount` failed jobs |
| Constraint | `1..100`, needs to be validated in the implementation |

Parameter description annotations **do not enforce validation**. Validation must be performed in code, such as checking `maxCount`, especially for operations with side effects.

### Reading and Invoking via MBeanServer

Assuming the bean is registered in the platform MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.jobs:type=RetryAdmin,name=Billing"
);

Object result = server.invoke(
    name,
    "retryFailed",
    new Object[] { 5 },
    new String[] { "int" }
);

System.out.println("Accepted jobs: " + result);
```

The last array passes the **parameter type signature**, not parameter names. For primitive `int`, the signature is `"int"`, not `"java.lang.Integer"`. If the operation has no parameters, empty arrays can be used for parameters and signature.

When using `MBeanServerConnection` on a remote client, the `invoke` syntax is similar, but adds concerns around connectivity, authentication, serialization, and data type compatibility.

## 5. How Does an Operation Differ from an Attribute?

JMX provides two primary access models:

**Attribute** represents state that a client reads/writes:

```java
@ManagedAttribute(description = "Current pending job count")
public int getPendingCount() {
    return pendingCount;
}
```

**Operation** represents an intentional action or query:

```java
@ManagedOperation(description = "Rebuilds the local queue index")
public void rebuildIndex() {
    // ...
}
```

A client reads an attribute with:

```java
server.getAttribute(name, "PendingCount");
```

A client invokes an operation with:

```java
server.invoke(name, "rebuildIndex", new Object[0], new String[0]);
```

Generally useful guidelines:

- Use attributes for state that needs to be observed frequently.
- Use operations for actions with side effects, queries requiring parameters, or intentional processing.
- Attribute getters should be fast with minimal side effects, because monitoring tools may poll them periodically.
- Operations may take longer, but should have bounds and transparent feedback.
- Do not turn every public method into an operation; expose only the administrative API that is genuinely needed.

A `getStatus()` method can be annotated with `@ManagedOperation` if the project wants it to be a query action; however, if it returns simple state and is used frequently, `@ManagedAttribute` is usually more intuitive.

## 6. Reading MBeanOperationInfo Metadata

Spring converts annotation information into JMX metadata. After registering the MBean, it can be inspected using `MBeanInfo`:

```java
import javax.management.*;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Name: " + operation.getName());
    System.out.println("Description: " + operation.getDescription());
    System.out.println("Return: " + operation.getReturnType());
    System.out.println("Impact: " + operation.getImpact());

    for (MBeanParameterInfo p : operation.getSignature()) {
        System.out.printf("  %s : %s (%s)%n",
                p.getName(),
                p.getType(),
                p.getDescription());
    }
}
```

`MBeanOperationInfo` contains:

- `name`: operation name.
- `description`: description.
- `returnType`: return type at the JMX metadata level.
- `signature`: parameter list with name, type, and description.
- `impact`: one of the values `INFO`, `ACTION`, `ACTION_INFO`, `UNKNOWN`.

The `impact` field only describes intended purpose. It **does not restrict permissions on its own** or prevent clients from invoking the operation. An operation described as informational can still perform side effects if the code implements them.

JConsole and JMC can display operations based on this metadata; the UI and level of parameter input support depend on the tool version.

## 7. Overloading: Two Methods with the Same Name

Java allows overloading:

```java
@ManagedOperation
public void retry(int maxCount) { /* ... */ }

@ManagedOperation
public void retry(String jobId) { /* ... */ }
```

In JMX, the name `retry` alone is not enough to select the operation. When calling `invoke`, you must pass the exact **signature**:

```java
server.invoke(
    name, "retry",
    new Object[] { 10 },
    new String[] { "int" }
);

server.invoke(
    name, "retry",
    new Object[] { "job-42" },
    new String[] { "java.lang.String" }
);
```

Some client UIs can display multiple operations with the same name and distinguish them by parameter types. For an operational contract that needs to be easy to use, consider more specific names like `retryUpTo` and `retryById` instead of complex overloads.

Avoid overloading with closely related types such as `int`, `Integer`, `long` if users primarily operate via JConsole/JMC. An incorrect signature leads to `ReflectionException` or the corresponding invocation error depending on the MBean/exporter.

## 8. Which Data Types Are Suitable for JMX Operations?

An operation can accept and return primitives, wrappers, String, ObjectName, and complex types depending on the MBean contract. However, for remote JMX clients, arbitrary domain types can cause difficulties:

```java
@ManagedOperation
public Result submit(InternalRequest request) { /* ... */ }
```

Issues can include the client lacking the `InternalRequest` class, the object not being serializable, or tools not knowing how to construct an instance as a parameter.

Prefer a small administrative API:

```java
@ManagedOperation(description = "Cancels a pending job by its ID")
public boolean cancelJob(String jobId) { /* ... */ return false; }
```

For structured data, consider MXBeans/Open Types or a dedicated API (REST, messaging) if users need to send complex payloads. `@ManagedOperation` on a Spring class method does not automatically convert arbitrary domain types into `CompositeData`.

Design principles:

1. Keep parameters easy to enter from JMX tools.
2. Use clear names and units: `timeoutMillis`, `maxItems`.
3. Return interpretable results, such as `boolean`, `int`, `String`.
4. Do not return personal data or secrets.
5. Limit large structures due to serialization, memory, and network overhead.

## 9. Visibility and Proxies: Which Methods Are Actually Exposed?

A Spring bean can be wrapped by a JDK dynamic proxy or a CGLIB/class-based proxy due to AOP, transactions, security, or tracing.

```text
JMX client
    |
    v
Exported MBean metadata
    |
    v
Spring proxy (if exported)
    |
    v
Target method
```

If the annotation is on the target but a JDK proxy only implements an interface that does not contain the administrative method, the exporter may not be able to invoke the method or metadata may not reflect expectations. Conversely, if the exporter registers the target directly to avoid the proxy, JMX calls may bypass transaction/security advice.

A resilient approach is to create an administrative adapter:

```java
public interface BillingService {
    void pauseProcessing();
}

@ManagedResource(
    objectName = "com.example.billing:type=Admin",
    description = "Billing processing controls"
)
public class BillingAdmin {
    private final BillingService service;

    public BillingAdmin(BillingService service) {
        this.service = service;
    }

    @ManagedOperation(
        description = "Pauses the billing service through its normal proxy"
    )
    public void pause() {
        service.pauseProcessing();
    }
}
```

If `BillingService` is injected by Spring as a proxy, the adapter calls through that interface and keeps active advice in effect. Export the adapter instead of directly exporting the entire business service.

**Note:** `private`, `protected`, or `final` methods should not be assumed to be exportable/invocable via JMX like public methods. Different metadata and proxy models have different limitations; the administrative interface should have public methods with simple signatures.

## 10. Operational and Security Impact

A JMX operation is a control point that can directly affect the application. Dangerous example:

```java
@ManagedOperation
public void purgeQueue() {
    // Delete queue data
}
```

Without permission restrictions and proper confirmation mechanisms, anyone with a JMX connection can invoke this operation.

Safety rules:

- Only expose operations genuinely needed for operations.
- Apply authentication, authorization, and TLS for remote JMX appropriate to the environment.
- Restrict JMX port access within trusted networks; never expose it to the public Internet.
- Validate parameters and execution limits directly in the implementation.
- Log/audit important operations in accordance with system policies.
- Do not put `deleteAll`, `shutdown`, `resetDatabase` operations on a general interface without clear need and protection.
- Distinguish observation operations (query) from state-changing operations (action).
- Do not rely on `description`, `impact`, or method names as an authorization mechanism.

If the code uses Spring Security method advice, verify that the JMX call path goes through the security proxy or has an independent authorization layer at the JMX boundary.

## 11. Long-Running Operations: Asynchronous Design

A JMX invocation is inherently a call that can be synchronous and block the client until the method completes. If `reindexAll()` takes several minutes, the JMX client may time out or the user will not know whether the work is progressing.

A better pattern:

```java
@ManagedResource(
    objectName = "com.example.search:type=ReindexAdmin",
    description = "Controls background search reindexing"
)
public class ReindexAdmin {
    private volatile String state = "IDLE";

    @ManagedAttribute(description = "IDLE, RUNNING or FAILED")
    public String getState() {
        return state;
    }

    @ManagedOperation(description = "Starts a background reindex job")
    public String startReindex() {
        // Demo: real implementation needs an executor/job manager and a lock to prevent duplicate runs.
        state = "RUNNING";
        return "job-accepted";
    }
}
```

This is only a skeleton for the administrative API. A production implementation must actually dispatch work to an executor/job system and update `state` according to the lifecycle; changing a variable to `RUNNING` must not be treated as having run the task.

Practical pattern:

1. The `startReindex()` operation checks permissions, validity, and current state.
2. The operation returns quickly with a job ID or status code.
3. The job runs on a background worker/executor.
4. `State`, `ProgressPercent`, and `LastError` attributes provide status.
5. If needed, the MBean emits a notification when the job finishes.
6. There is a stop/cancel procedure and protection against creating duplicate jobs.

If an operation blocks for a long time, JMX connector thread resources and management tools can be impacted.

## 12. Direct Verification via Spring Integration Test

You can initialize a context with `@EnableMBeanExport`, then verify that the operation appears and is invocable:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.*;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class RetryAdminJmxTest {
    @Test
    void exportsAndInvokesOperation() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.jobs:type=RetryAdmin,name=Billing"
        );

        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class, RetryAdminConfig.class)) {

            assertTrue(server.isRegistered(name));

            Object value = server.invoke(
                name,
                "retryFailed",
                new Object[] { 5 },
                new String[] { "int" }
            );

            assertEquals(3, value);
        }
    }
}
```

The bean configuration added to the context:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RetryAdminConfig {
    @Bean
    public RetryAdmin retryAdmin() {
        return new RetryAdmin();
    }
}
```

The test assumes the exporter actually registers into the platform `MBeanServer`; if using another server, inject that server. The test should not run in parallel with another context registering the same ObjectName because it can cause `InstanceAlreadyExistsException`.

A good test can also verify the name, parameter signature, and description in `MBeanInfo`, and then confirm that the MBean is unregistered when the context closes.

## 13. Troubleshooting Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JConsole does not see method | Missing `@ManagedOperation`, exporter not enabled, or different metadata assembler | Check annotation, exporter, `MBeanInfo` |
| MBean does not appear | `@ManagedResource` missing/not detected; wrong ObjectName; different server | Check context, JMX server, and logs |
| `InstanceAlreadyExistsException` | Two exporters registering duplicate ObjectName | Choose a single registration mechanism with clear ownership |
| `NotCompliantMBeanException` | Incompatible MBean contract or affected proxy | Use annotation exporter/adapter/StandardMBean as appropriate |
| `ReflectionException` on invoke | Operation name or parameter signature mismatch | Retrieve signature from `MBeanOperationInfo` |
| `MBeanException` on invoke | Executed method threw an exception | Check root cause and validation |
| `SecurityException` or permission denied | Client lacks sufficient permissions or JMX security blocked it | Review authorization/authentication configuration |
| Operation bypasses aspects | Target registered instead of proxy | Export adapter or ensure delegate is a proxy |
| UI cannot enter parameters | Complex types or unsupported by client | Simplify signature, consider Open Types |
| Operation timeout | Long execution/blocking thread | Return quickly and use an asynchronous job |

When diagnosing, start with three questions: **Is the MBean registered? Is the operation in the metadata? Does the invocation signature match?**

## 14. @ManagedOperation Design Checklist

Before exposing a method as a JMX operation, consider:

1. **Purpose:** does the operation serve genuine observability or administrative needs?
2. **Scope:** does it affect one resource, one JVM, or the whole cluster?
3. **Name:** are the verb and target clear (e.g., `pauseProcessing` instead of `action1`)?
4. **Parameters:** are types, count, and value ranges bounded?
5. **Result:** how does the client know whether the operation succeeded or failed?
6. **Impact:** does it affect data, traffic, or service availability?
7. **Permissions:** who is allowed to call it, and is there appropriate auditing?
8. **Latency:** is the method fast, or does it use an asynchronous job if long-running?
9. **Versioning:** would renaming or changing parameter types break automated clients?
10. **Metadata:** are descriptions displayed usefully in JConsole/JMC?

## 15. Practice Exercises

1. Create a `@ManagedResource` named `com.example:type=Worker,name=Background`, add an `ActiveWorkers` attribute and `pause()`/`resume()` operations.
2. Create an operation `retryFailed(int maxCount)`, describe the parameter with `@ManagedOperationParameters`, then invoke it via `MBeanServer.invoke`.
3. Try invoking the operation with signature `"java.lang.Integer"` instead of `"int"` and observe the error caused by signature mismatch.
4. Overload `retry(int)` and `retry(String)`; use metadata to retrieve both signatures and invoke each operation.
5. Try exposing an operation that accepts a complex domain DTO; compare usability from JConsole/JMC against an operation accepting only String/int.
6. Create an adapter MBean that calls through a Spring AOP proxy; confirm that advice executes when the operation is invoked from JMX.
7. Write a test verifying that the operation appears in `MBeanInfo`, invokes successfully, and the MBean is unregistered after the context closes.

## 16. Self-Check Questions

- How does `@ManagedOperation` differ from `@ManagedAttribute`?
- Why does a class with `@ManagedResource` still need an active exporter?
- Why does `MBeanServer.invoke` require both the operation name and signature?
- Does `@ManagedOperationParameter` enforce parameter limits on its own?
- When should an asynchronous operation be used instead of long-running processing directly inside the JMX call?
- How can an AOP proxy affect the invocation path of an operation?
- Why is a method with `@ManagedOperation` not necessarily safe to open to all JMX clients?

**Key takeaway:** `@ManagedOperation` is how Spring marks a method to be exported as a JMX operation through an exporter with appropriate annotation configuration. Export selectively, describe impact clearly, use client-compatible signatures and data types, validate parameters, apply dedicated JMX security, and verify metadata as well as actual invocation capability via `MBeanServer`.