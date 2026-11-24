# Description and Metadata for Operations with @ManagedOperation in Spring JMX

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain what an operation is in JMX and distinguish operations from attributes.
- Use \`@ManagedOperation\` to expose a Java method as an intentional administrative operation.
- Write a clear **description** for an operation, accurately describing its effect and risks when operators invoke it.
- Use \`@ManagedOperationParameter\` and \`@ManagedOperationParameters\` to attach names and descriptions to parameters.
- Understand the metadata JMX provides through \`MBeanOperationInfo\`, \`MBeanParameterInfo\`, \`MBeanInfo\`, and \`Descriptor\`.
- Verify actual metadata on the \`MBeanServer\`, rather than inferring it solely from annotations in source code.
- Distinguish settings like \`impact\`, \`currencyTimeLimit\`, and Model MBean-dependent descriptor attributes from business controls and access permissions.
- Design operation contracts with clear names, parameters, return types, error handling, and descriptions for JConsole and JMX clients.

## 2. Operations in the JMX Model

An MBean can expose **attributes** to read or write state and **operations** to perform administrative actions. Example:

\`\`\`text
ObjectName:
  com.example.orders:type=ImportJob,name=Daily

Attributes:
  Running          Boolean  read-only
  ProcessedCount   Long     read-only

Operations:
  requestPause()                  void
  retryFailedTasks(int maxTasks)  int
\`\`\`

From a JMX client's perspective, an operation consists of a **name**, **parameter list**, **return type**, **impact level (impact)**, and **description**. This information appears in \`MBeanOperationInfo\`.

In Spring Framework, \`@ManagedOperation\` is metadata for the Spring JMX exporter to determine which methods need to be exposed. For the annotation to take effect, the application must use an exporter/assembler that understands annotation metadata, such as \`MBeanExporter\` with \`MetadataMBeanInfoAssembler\` and \`AnnotationJmxAttributeSource\`.

Not every \`public\` method of a Spring bean will be exported over JMX if you use proper selective metadata configuration.

## 3. Why Does Description Matter?

The description helps operators know what an operation **does** before invoking it. This matters because many JMX operations have real side effects:

- Refreshing a cache causes the system to hit the data source.
- Pausing a consumer causes messages to back up.
- Triggering retries puts extra load on downstream systems.
- Resetting statistics can lose metrics accumulated since the last reset.
- Reloading configuration can change how the application behaves.

Example of a vague description:

\`\`\`java
@ManagedOperation(description = "Refresh")
public void refresh() { /* ... */ }
\`\`\`

A more meaningful description:

\`\`\`java
@ManagedOperation(
    description = "Reload the product cache from the current database snapshot"
)
public void refreshProductCache() {
    // Illustration only: the application implements the real action.
}
\`\`\`

A good description helps clients understand the action, but **is not an authorization or safety confirmation mechanism**. If a dangerous operation is exposed, anyone with permission to invoke JMX can still execute it; the description does not stop the call.

### 3.1. What Should Be Included in a Description

Depending on importance, a description should indicate:

1. **Action:** what does the operation change?
2. **Scope:** which cache, which worker, which resource?
3. **Side effects:** does it reset counters, add load, or pause tasks?
4. **Conditions:** when is it valid? Is it idempotent?
5. **Result:** what return value or state confirms the action?
6. **Latency:** is it synchronous or does it only submit an asynchronous request?

Example:

\`\`\`java
@ManagedOperation(
    description = "Request graceful pause of the import worker; " +
                  "returns before in-flight tasks finish"
)
public void requestPause() {
    // ...
}
\`\`\`

The description string can be longer than one sentence but should remain concise and clear for display in management tools. If there are complex operational procedures, store detailed runbooks in separate documentation and put only a short summary in JMX metadata.

## 4. @ManagedOperation: Basic Declaration

The annotation resides in the package:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
\`\`\`

Example with a management bean:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=Importer",
    description = "Import worker management"
)
public class ImportWorkerAdmin {

    @ManagedOperation(
        description = "Request a graceful stop of the import worker"
    )
    public void requestStop() {
        // Forward the request to the actual service.
    }
}
\`\`\`

In an exporter configuration using annotation-based metadata, \`requestStop\` will be described as an operation. Typically \`getMBeanInfo\` reports:

\`\`\`text
operation.name        = requestStop
operation.description = Request a graceful stop of the import worker
operation.signature   = []
operation.returnType  = void
\`\`\`

Invoking \`requestStop\` via JMX can trigger application logic. Therefore, only expose operations with predefined behavior; avoid exposing arbitrary methods like \`executeCommand(String)\` or \`deleteEverything()\` on the management surface.

## 5. Which Metadata Does Description Belong To?

Standard JMX defines \`MBeanOperationInfo\` with the main details:

| Component | API | Meaning |
| --- | --- | --- |
| Operation name | \`getName()\` | Name used by clients to invoke the operation. |
| Description | \`getDescription()\` | Operational description content. |
| Return type | \`getReturnType()\` | Java type name published by JMX. |
| Parameters | \`getSignature()\` | Array of \`MBeanParameterInfo\` in parameter order. |
| Impact | \`getImpact()\` | Action classification according to JMX metadata. |
| Descriptor | \`getDescriptor()\` | Additional metadata fields when provided. |

Clients can use this information to build UIs. For example, JConsole can display the operation with parameter input fields and an invoke button; custom clients can inspect the signature to pass the right types.

The description does not alter the Java method's logic. It helps human readers and tools understand the administrative meaning.

## 6. Metadata for Operation Parameters

Publishing only the operation description is sometimes not enough. For an operation with multiple parameters, clients need to know what each parameter represents.

Example method:

\`\`\`java
public int retryFailedTasks(int maxTasks, boolean dryRun) { /* ... */ }
\`\`\`

If Java parameter names are stripped from bytecode or introspection does not retain enough metadata, JMX clients may only see types or generic names. Spring provides \`@ManagedOperationParameter\` to describe each parameter.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(
    description = "Retry up to maxTasks failed items; dryRun counts without retrying"
)
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "maxTasks",
        description = "Maximum number of failed items to examine"
    ),
    @ManagedOperationParameter(
        name = "dryRun",
        description = "When true, return candidate count without retry"
    )
})
public int retryFailedTasks(int maxTasks, boolean dryRun) {
    return 0; // Real implementation calls a controlled service.
}
\`\`\`

With a metadata assembler supporting annotations, \`MBeanOperationInfo.getSignature()\` provides metadata for the two parameters in order:

\`\`\`text
Parameter 0:
    name = maxTasks
    type = int
    description = Maximum number of failed items to examine

Parameter 1:
    name = dryRun
    type = boolean
    description = When true, return candidate count without retry
\`\`\`

**Important:** parameter description annotations do not automatically enforce validation such as \`maxTasks > 0\`. Business code must still check bounds and reject invalid values.

## 7. Conventions for Writing Parameter Descriptions

Each parameter description should:

- Identify the business meaning, not just repeat the name.
- State the unit: seconds, milliseconds, bytes, item count.
- State the valid range if any, e.g., \`1..100\`.
- State the effect of special values like \`0\` or \`-1\`.
- Clarify \`null\` or empty string cases.
- Avoid vague descriptions like “parameter”, “value”, “the argument”.

Good example:

\`\`\`java
@ManagedOperationParameter(
    name = "timeoutMillis",
    description = "Maximum time to wait in milliseconds (100..10000)"
)
\`\`\`

However, the description \`100..10000\` is only a documentation contract. The implementation must enforce it:

\`\`\`java
if (timeoutMillis < 100 || timeoutMillis > 10_000) {
    throw new IllegalArgumentException(
        "timeoutMillis must be between 100 and 10000"
    );
}
\`\`\`

When changing validation, update the corresponding description to prevent operational tools from passing values that are no longer valid.

## 8. Impact Metadata: ACTION, INFO, and ACTION_INFO

JMX \`MBeanOperationInfo\` has common impact values:

| Impact | Descriptive Meaning | Example |
| --- | --- | --- |
| \`INFO\` | Operation intended to provide information. | Compute a snapshot or read state. |
| \`ACTION\` | Operation performs an action. | Reset counters, request pause. |
| \`ACTION_INFO\` | Operation both performs an action and returns information. | Start retry and return the number of accepted tasks. |
| \`UNKNOWN\` | Classification is not clearly specified. | Operation lacks appropriate metadata. |

The impact field helps describe the nature of the operation to clients. **It is not an authorization rule**: an operation marked \`INFO\` can still contain side effects if the implementation is written improperly; an \`ACTION\` operation is not automatically blocked for a read-only role unless the authorization mechanism checks appropriately.

In Spring JMX, annotation metadata and the assembler determine the published impact. When you need to verify or evaluate actual impact, read \`MBeanOperationInfo.getImpact()\` from the running MBeanServer.

### 8.1. Impact Metadata Example

Suppose:

\`\`\`java
public int retryFailedTasks(int maxTasks, boolean dryRun);
\`\`\`

This operation can return the number of processed tasks (information) while also triggering retries (action), so semantically it fits \`ACTION_INFO\`. However, do not assume Spring automatically infers that from the return type or method name. Inspect runtime metadata and use an appropriate assembler/metadata strategy if the project requires precise classification.

## 9. currencyTimeLimit and Operation Descriptors

Spring JMX supports certain metadata originating from JMX Model MBean descriptors. In that model, \`currencyTimeLimit\` can relate to the caching policy for an operation's return value in specific situations.

Three things must be distinguished:

1. **Description:** describes the operation.
2. **Descriptor field:** additional metadata that may be interpreted by the Model MBean implementation.
3. **Business behavior:** the operation code that executes and controls side effects.

If you see \`currencyTimeLimit\` in operation metadata, do not treat it as an invocation timeout, SLA, or a scheduler. It belongs to the Model MBean caching context, if the implementation supports and applies it.

Example descriptor structure:

\`\`\`text
name              = calculateStatus
descriptorType    = operation
currencyTimeLimit = 5
\`\`\`

This field can instruct the Model MBean to use cached results according to the implementation's semantics. For operations with side effects, caching results can change how many times the actual logic runs. Therefore, do not arbitrarily configure caching on state-changing operations.

If you need a real timeout, implement the timeout in service code, connector, or asynchronous task according to your specific architecture; do not use \`currencyTimeLimit\` as an invocation abort tool.

## 10. How Spring Creates Operation Metadata

A common processing path:

\`\`\`text
Spring bean
  @ManagedResource
  @ManagedOperation
  @ManagedOperationParameters
             |
             v
AnnotationJmxAttributeSource
             |
             v
MetadataMBeanInfoAssembler
             |
             v
ModelMBeanInfo / MBeanOperationInfo
             |
             v
MBeanExporter
             |
             v
MBeanServer
             |
             v
JConsole / JMX client
\`\`\`

\`AnnotationJmxAttributeSource\` reads annotations on classes and methods. \`MetadataMBeanInfoAssembler\` converts the metadata into \`MBeanInfo\` and descriptors suitable for the exporter to provide to the MBeanServer.

If the application uses \`InterfaceBasedMBeanInfoAssembler\` or another strategy, annotation metadata may not be applied as expected. Always check the actual assembler configuration.

### 10.1. Explicit Configuration Example

\`\`\`java
package example.springjmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {

    @Bean
    public MBeanExporter mBeanExporter(ImportJobAdmin admin) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setBeans(Map.of("importJobAdmin", admin));

        return exporter;
    }
}
\`\`\`

This is a plain Spring Framework example, meant solely to clarify the metadata pipeline. In Spring Boot, JMX auto-configuration may already exist; avoid duplicate exporters registering the same \`ObjectName\`.

### 10.2. Example of an Exposed Bean

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=ImportJob,name=Daily",
    description = "Import job management"
)
public class ImportJobAdmin {

    @ManagedOperation(
        description = "Request a graceful pause; in-flight items continue"
    )
    public void requestPause() {
        // Call the service to request a pause.
    }

    @ManagedOperation(
        description = "Retry up to maxTasks failed tasks; returns accepted count"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "maxTasks",
            description = "Maximum tasks to retry (1..100)"
        )
    })
    public int retryFailedTasks(int maxTasks) {
        if (maxTasks < 1 || maxTasks > 100) {
            throw new IllegalArgumentException(
                "maxTasks must be between 1 and 100"
            );
        }
        return 0; // Placeholder result for illustration.
    }

    // Public method without an operation annotation:
    public void internalRebuildAllIndexes() {
        // Not exposed via the annotation-based assembler.
    }
}
\`\`\`

This pattern keeps a small management surface. Do not expose full data restoration methods or arbitrary command execution to JMX without a clear operational need and explicit permission controls.

## 11. Example of Invoking an Operation via MBeanServer

Assuming the bean has been registered successfully by the exporter:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=ImportJob,name=Daily"
);

// Operation with no parameters:
server.invoke(
    name,
    "requestPause",
    new Object[0],
    new String[0]
);

// Operation taking int:
Object result = server.invoke(
    name,
    "retryFailedTasks",
    new Object[] { 10 },
    new String[] { "int" }
);

System.out.println("Accepted count: " + result);
\`\`\`

The signature \`new String[] { "int" }\` uses the primitive type name \`int\` matching the Java method declaration. For reference types, use the corresponding Java class name. JMX uses the signature to identify the matching operation, especially when overloads exist.

Ensure the operation is registered on the platform MBeanServer being accessed. If the exporter uses a different MBeanServer, retrieve that corresponding server.

## 12. Reading Actual Metadata

Do not conclude that annotations were applied just because the code compiles. Use the JMX API to inspect:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName objectName = new ObjectName(
    "com.example.jobs:type=ImportJob,name=Daily"
);

MBeanInfo info = server.getMBeanInfo(objectName);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s%nDescription: %s%n" +
        "Return type: %s%nImpact: %d%n",
        operation.getName(),
        operation.getDescription(),
        operation.getReturnType(),
        operation.getImpact()
    );

    for (MBeanParameterInfo parameter
            : operation.getSignature()) {
        System.out.printf(
            "  Parameter: %s (%s) - %s%n",
            parameter.getName(),
            parameter.getType(),
            parameter.getDescription()
        );
    }
}
\`\`\`

Expected output at a semantic level:

\`\`\`text
Operation: requestPause
Description: Request a graceful pause; in-flight items continue
Return type: void

Operation: retryFailedTasks
Description: Retry up to maxTasks failed tasks; returns accepted count
Return type: int
  Parameter: maxTasks (int) - Maximum tasks to retry (1..100)
\`\`\`

The numeric \`Impact\` corresponds to \`MBeanOperationInfo\` constants; clients can translate it to \`INFO\`, \`ACTION\`, \`ACTION_INFO\`, or \`UNKNOWN\`.

### 12.1. Reading the Operation Descriptor

\`\`\`java
for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        operation.getName() + " => "
            + operation.getDescriptor()
    );
}
\`\`\`

Descriptors can contain fields such as \`name\`, \`descriptorType\`, \`role\`, \`currencyTimeLimit\`, or other metadata depending on the Model MBean implementation. If a field is absent, do not assume its value was applied.

### 12.2. Metadata Is a Runtime Contract

When designing an automated client, you can inspect metadata before invoking:

\`\`\`java
boolean available = false;

for (MBeanOperationInfo operation : info.getOperations()) {
    if ("retryFailedTasks".equals(operation.getName())
            && operation.getSignature().length == 1
            && "int".equals(
                operation.getSignature()[0].getType())) {
        available = true;
    }
}

if (!available) {
    throw new IllegalStateException(
        "Expected JMX operation is not available"
    );
}
\`\`\`

This helps detect name/signature changes between versions. However, you still need to handle the case where the MBean is unregistered after the check (time-of-check/time-of-use).

## 13. Operation Metadata and JConsole

In JConsole, navigate to **MBeans → domain → MBean → Operations**. For an MBean exposing operations, you can typically view:

- Operation name.
- Parameters the user needs to enter.
- Return type.
- Operation and parameter descriptions, depending on how JConsole renders metadata.
- The button to execute the operation.

Do not assume every JConsole version or every JMX client displays all descriptor fields. Description/metadata can still be read via the JMX API even when the GUI is simplified.

**Clicking the invoke button is a real action.** For operations with side effects, confirm the right JVM, right environment, and right MBean before invoking. A \`requestPause\` operation can stop business processing, not merely change the UI.

### 13.1. Why Good Descriptions Help Operations

Two operations:

\`\`\`text
reset()
reload()
\`\`\`

are not enough for users to understand consequences. If metadata states:

\`\`\`text
reset()  - Reset request counters to zero; no business data is changed
reload() - Reload validated runtime configuration; active requests are unaffected
\`\`\`

operators can distinguish their effects. However, descriptions must match the implementation. Do not write “active requests are unaffected” if the code can cancel running requests.

## 14. Distinguishing Operations and Attributes

In Spring JMX, getters like \`getStatus()\` usually fit \`@ManagedAttribute\`; commands like \`restart()\` fit \`@ManagedOperation\`.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedAttribute(description = "Current worker status")
public String getStatus() {
    return "RUNNING";
}

@ManagedOperation(
    description = "Request the worker to restart gracefully"
)
public void requestRestart() {
    // ...
}
\`\`\`

A read-only method can still be exported as an operation if it needs computation or accepts parameters, but there should be a clear reason. For metrics polled frequently, a simple attribute getter integrates better with more management tools.

Do not use operations merely to expose a broader Java API than necessary; JMX is an operational surface, not a mechanism for automatically exporting all service methods.

## 15. Validation, Errors, and Operation Semantics

Metadata describes inputs but **does not automatically validate all business constraints**. For example, \`retryFailedTasks(1000000)\` can cause heavy load if the implementation does not check it.

You need to handle:

1. **Range validation:** limits on counts, durations, and string lengths.
2. **State validation:** in which states the operation is valid.
3. **Concurrency:** whether two administrators invoking simultaneously causes conflicts.
4. **Idempotency:** if a client retries due to a timeout, whether repeated execution causes issues.
5. **Error reporting:** exceptions or status codes that allow diagnosis without leaking sensitive data.
6. **Authorization:** who is allowed to invoke the operation, via JMX/connector security and the application layer when needed.
7. **Observability:** recording the timing and outcome of high-impact actions.

A generally safer pattern is a **request-style operation**:

\`\`\`java
@ManagedOperation(
    description = "Request a cache rebuild; returns a request ID"
)
public String requestCacheRebuild() {
    // Submit the request to an internal executor/queue.
    return "request-example";
}
\`\`\`

This way the call does not necessarily block JConsole until the rebuild completes. However, you must provide a way to view request status and handle duplicates using real identifiers when implementing.

## 16. Avoid Confusing Description with Authorization

A description is documentation, not something that stops a user from clicking invoke. Similarly:

- **Impact** is only classification metadata.
- **Parameter description** does not block invalid input on its own.
- **CurrencyTimeLimit** is not a security timeout.
- **ObjectName** is not an access permission.
- **Hiding an operation from documentation** does not mean the method cannot be invoked if a dynamic implementation still handles it.

Ensure safety through minimal MBean surface design, validation, connector permissions, authentication/TLS, and control over side-effecting actions.

A read-only client should have a policy prohibiting invocation of state-changing operations if the system supports such role separation. If fine-grained per-operation authorization is required, an appropriate authorization mechanism must be used, not just a description string.

## 17. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Operation does not appear | Bean not exported, annotation not read by assembler, wrong ObjectName. | Check \`MBeanExporter\`, assembler, \`getMBeanInfo\`. |
| Description not displayed | GUI client omits metadata or assembler did not transfer annotations. | Read \`getDescription()\` via the JMX API. |
| Parameters only have generic names | Parameter metadata not declared or annotations not applied. | Use \`@ManagedOperationParameters\`, verify \`getSignature()\`. |
| Invocation reports wrong signature | Type name or parameter order mismatch. | Read the signature from \`MBeanOperationInfo\`. |
| Invokes successfully but wrong result | Incorrect service logic, missing input/state validation. | Fix validation and business logic, not just the description. |
| Operation causes heavy load | Unbounded parameters, long synchronous execution. | Add limits, coordinate asynchronously, and expose progress status. |
| Duplicate operation names | Overloads exist and client chose the wrong signature. | Publish clear signatures, consider distinct administrative names. |
| Inappropriate impact | Default metadata or assembler configuration. | Inspect JMX runtime, adjust strategy if needed. |
| Changed description but JConsole shows old one | MBean not re-registered or connection not refreshed. | Check MBean lifecycle and reconnect/refresh client. |

## 18. Guidelines for Designing a Maintainable Administrative API

Example contract:

\`\`\`text
MBean:
  com.example.orders:type=Scheduler,name=Reconciliation

Attributes:
  State                String  read-only
  LastRunEpochMillis   Long    read-only

Operations:
  requestRunOnce()
    description: Queue one reconciliation run; returns immediately.
    returnType: String requestId

  cancelPendingRun(String requestId)
    description: Cancel a queued run if it has not started.
    parameter:
      requestId: ID returned by requestRunOnce
    returnType: boolean
\`\`\`

Principles:

- **Stable names:** avoid constantly changing names/signatures because automated clients may depend on them.
- **Accurate descriptions:** clearly state synchronous/asynchronous behavior and return values.
- **Minimal parameters:** do not accept paths, SQL, shell commands, or dangerous options unless necessary.
- **Simple types:** prefer JMX types that are easy to enter and inspect; consider MXBean/OpenType for complex data.
- **Controlled side effects:** validation, load limits, and operation state tracking.
- **No data leaks:** descriptions, parameter names, exceptions, and return values are all visible to clients.

## 19. Practice Exercises

### Exercise 1 — Simple Operation

Create a \`@ManagedResource\` bean with \`@ManagedOperation(description = "Reset request counters")\` on the \`resetCounters()\` method. Export the bean and read the description via \`MBeanServer.getMBeanInfo\`.

**Goal:** understand how a description travels from an annotation to runtime metadata.

### Exercise 2 — Parameter Metadata

Create an operation \`reconfigurePool(int minSize, int maxSize)\`. Use \`@ManagedOperationParameters\` to describe both parameters, units, and valid limits. Read \`getSignature()\` to inspect name, type, and description.

**Goal:** learn to manage parameter metadata instead of relying on Java variable names.

### Exercise 3 — Signature and Invoke

Register \`retryFailedTasks(int maxTasks)\`, use MBeanServer.invoke with signature \`"int"\`. Try signature \`"java.lang.Integer"\` and observe the behavior with the active JMX exporter.

**Goal:** understand that the signature parameter is identified by type according to JMX metadata.

### Exercise 4 — Operation with Side Effects

Design a \`clearCache()\` operation with a description stating the impact on the cache and database load after clearing. Add authorization and validation according to the application architecture.

**Goal:** understand that good metadata helps operations but does not replace protective mechanisms.

### Exercise 5 — Comparing Assemblers

In a lab, export the same bean using an annotation-based assembler and another suitable strategy. Compare \`MBeanInfo\`: which operations appear, which descriptions are preserved, and which parameters have metadata.

**Goal:** see that annotations only take effect when the exporter/assembler uses them properly.

### Exercise 6 — Client Self-Checking Metadata

Write a Java client that reads the operation list, finds \`retryFailedTasks\` with a single \`int\` parameter, and only then invokes it. If the operation is missing or the signature differs, report a clear error.

**Goal:** build administrative clients that are less tightly coupled to implementation details.

## 20. Review Questions

**1. What is \`@ManagedOperation\` used for?** Describing a method to be exported as a JMX operation when a compatible exporter/assembler processes annotations.

**2. What effect does \`description\` have?** Provides documentation helping clients/operators understand the operation's meaning; does not alter the Java method itself.

**3. Where is operation metadata read from?** \`MBeanInfo.getOperations()\` and each \`MBeanOperationInfo\`.

**4. Why is \`@ManagedOperationParameter\` needed?** To provide administrative parameter names and descriptions rather than having only types or generic names.

**5. Is impact authorization?** No. It is metadata describing the nature of the operation.

**6. Does description validate input?** No. The implementation must validate input data.

**7. Why does signature matter?** It helps clients select the exact operation, especially when there are overloads or differing parameter types.

**8. Does enabling JMX in Spring Boot automatically turn all public methods into operations?** No. What gets exposed depends on the exporter, assembler, and specific configuration.

**9. Why shouldn't currencyTimeLimit be set arbitrarily on state-changing operations?** Because result caching can affect how many times the method executes when the Model MBean interprets the descriptor.

**10. What should be included in the description of a high-risk operation?** Action, scope, invocation conditions, side effects, result, and important limits, while enforcing real controls in code/permissions.

## 21. Summary

**Operation metadata** is the contract that enables JMX clients to discover, display, and invoke administrative operations. In Spring Framework, \`@ManagedOperation\` describes the operation and description; \`@ManagedOperationParameters\` along with \`@ManagedOperationParameter\` help name and explain parameters.

Runtime metadata is represented via \`MBeanOperationInfo\` and \`MBeanParameterInfo\`; it should be inspected directly from the MBeanServer to confirm the exporter published it properly. Description, impact, and descriptor help explain manageability but do not replace validation, authorization, or safe action design.

## References

- Spring Framework Javadoc — \`ManagedOperation\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Spring Framework Javadoc — \`ManagedOperationParameter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperationParameter.html
- Spring Framework Javadoc — \`ManagedOperationParameters\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperationParameters.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 — \`MBeanOperationInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — \`MBeanParameterInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanParameterInfo.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html