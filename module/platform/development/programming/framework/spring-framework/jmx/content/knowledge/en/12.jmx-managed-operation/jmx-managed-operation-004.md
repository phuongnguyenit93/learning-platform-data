# Parameter Types, Return Types, and JMX Compatibility

> **Topic:** Spring Framework JMX
> **Knowledge Group:** ManagedOperation
> **Lesson:** Parameter Types, Return Types, and JMX Compatibility

## 1. Objectives

This lesson explains the data type contract of an operation published by Spring via Java Management Extensions (JMX). After studying, you will be able to:

- Read the exact method name, parameter type list, and return type of a JMX operation.
- Understand how `@ManagedOperation` and `@ManagedOperationParameters` form the management surface on a Spring bean.
- Distinguish primitives from wrappers, internal application Java types, and data types transportable across JMX connectors.
- Invoke `MBeanServer.invoke` with the correct `ObjectName`, value list, and parameter signature.
- Design operations using simple types or Open Types, minimizing dependencies on internal DTOs.
- Distinguish Standard MBean, Spring ModelMBean, and MXBean, especially when connecting remotely.

## 2. From a Java Method to a JMX Contract

A Java method can have any parameters and return type valid in the language. When exposed over JMX, the method becomes a contract that management clients must understand, with a name, ordered parameter types, and return type.

```text
Spring bean
    |
    | @ManagedResource + @ManagedOperation
    v
Spring AnnotationMBeanExporter / ModelMBean
    |
    | Operation name + parameter signature + return type
    v
MBeanServer
    |
    | invoke(ObjectName, operation, params, signature)
    v
JConsole / Java client / remote monitoring agent
```

Example of a Spring bean:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=WorkerControl,name=main"
)
public class WorkerControl {

    private volatile int workerLimit = 4;

    @ManagedOperation(description = "Set worker limit")
    public void resizeWorkers(int workers) {
        if (workers < 1 || workers > 128) {
            throw new IllegalArgumentException("workers must be 1..128");
        }
        workerLimit = workers;
    }

    @ManagedOperation(description = "Get worker limit")
    public int currentWorkerLimit() {
        return workerLimit;
    }
}
```

In an application with export configuration enabled, such as `@EnableMBeanExport`, JMX metadata publishes two operations:

```text
resizeWorkers(int) -> void
currentWorkerLimit() -> int
```

A JMX client does not guess types from the method name; it must send a signature matching the published metadata.

## 3. Signature in MBeanServer.invoke

The central method is:

```java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
);
```

| Argument | Meaning | Example |
|---|---|---|
| `name` | Exact identifier of the MBean | `learning.jmx:type=WorkerControl,name=main` |
| `operationName` | Published operation name | `resizeWorkers` |
| `params` | Argument values in order | `new Object[] { 8 }` |
| `signature` | Declared parameter type names in order | `new String[] { "int" }` |
| Result | Return value as Object | null for `void`, Integer for `int` |

How to invoke:

```java
ObjectName name = new ObjectName(
    "learning.jmx:type=WorkerControl,name=main"
);

server.invoke(
    name,
    "resizeWorkers",
    new Object[] { 8 },
    new String[] { "int" }
);
```

The `params` array holds **values**, while `signature` holds the **declared types of the method**. They must have the same number of elements and match in order. The Java value `8` is boxed to `Integer` in `Object[]`, yet the signature must still be `int` because the method declares primitive `int`.

## 4. Primitives and Wrappers Are Two Different Signatures

Primitive types have names like `int`, `long`, `boolean`, `double`. Wrappers are classes such as `java.lang.Integer`, `java.lang.Long`, `java.lang.Boolean`, `java.lang.Double`.

Suppose there are two overloads:

```java
public void setLimit(int value) { ... }

public void setLimit(Integer value) { ... }
```

Two different signatures:

```text
setLimit(int)
setLimit(java.lang.Integer)
```

The same object `Integer.valueOf(5)` can be used as the value in the `params` array, while `signature` selects the overload:

```java
server.invoke(
    name,
    "setLimit",
    new Object[] { Integer.valueOf(5) },
    new String[] { "int" }
);

server.invoke(
    name,
    "setLimit",
    new Object[] { Integer.valueOf(5) },
    new String[] { "java.lang.Integer" }
);
```

JMX should not be treated like a Java compiler that arbitrarily attempts boxing, widening, and overload resolution. If a method accepts `long`, pass `Long` and signature `long`. If it accepts `String`, the signature is `java.lang.String`, not `String`.

Wrapper types can accept null, whereas primitives cannot accept null. This affects validation and runtime behavior.

## 5. Types Suitable for Administrative Operations

| Type | Example | Points to Note |
|---|---|---|
| `boolean` | `setEnabled(boolean)` | Ensure only approved state transitions are allowed |
| `int` | `resize(int)` | Bound values and check for negative numbers |
| `long` | `setTimeoutMillis(long)` | Document units clearly so clients do not misunderstand |
| `double` | `setThreshold(double)` | Check for NaN, infinity, and valid range |
| `String` | `refreshCache(String)` | Validate allowlist, length, and input characters |
| `Integer` or `Boolean` | Optional parameter | Clearly define the meaning of null |
| `String[]` | List of names | Client must support constructing arrays of the right type |
| `CompositeData` | Multi-field state | Requires a clear Open MBean schema |
| `TabularData` | List of records | Requires a consistent type/index schema |

Simple types are generally more compatible with JConsole, scripts, and remote clients. However, "easy to transport" does not mean an operation is automatically safe: `deleteEverything()` has an empty signature yet is still a dangerous operation.

## 6. No Parameters and Multiple Parameters

Method with no parameters:

```java
@ManagedOperation
public void resetCounters() {
    // Only reset permitted counters.
}
```

Invoke with two empty arrays:

```java
server.invoke(
    name,
    "resetCounters",
    new Object[0],
    new String[0]
);
```

Do not pass `new Object[] { null }`, because that is **one** null argument rather than zero arguments.

Method with three parameters:

```java
@ManagedOperation
public String submit(
        String queue,
        int batchSize,
        boolean dryRun
) {
    return "accepted";
}
```

Client:

```java
Object result = server.invoke(
    name,
    "submit",
    new Object[] { "retry", 100, true },
    new String[] {
        "java.lang.String",
        "int",
        "boolean"
    }
);
```

Swapping the order of two elements in `signature` or `params` can prevent the server from finding the operation or invoking the method. `params.length == signature.length` is a necessary condition; each type and position must also match.

## 7. ManagedOperationParameters Is Only Metadata

Spring supports describing the name and purpose of each parameter:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(description = "Resize worker pool")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "workers",
        description = "Number of workers, from 1 to 128"
    )
})
public void resizeWorkers(int workers) {
    // ...
}
```

`@ManagedOperationParameters` does not coerce types, does not turn `int` into `String`, and does not change parameter order. It helps JMX tools display names and descriptions. If input is invalid, the method must still validate it or delegate to a service responsible for validation.

## 8. Return Types

For `void`, `MBeanServer.invoke` usually returns `null`. For primitives, the result is boxed, e.g., `int` returns `Integer`. For `String`, the client typically receives `String`.

```java
Object result = server.invoke(
    name,
    "currentWorkerLimit",
    new Object[0],
    new String[0]
);

Integer limit = (Integer) result;
```

The client should only cast when the MBean contract actually returns that type. This can be confirmed via `MBeanOperationInfo.getReturnType()`.

An operation with a `void` return type that launches asynchronous work does not mean the work has completed:

```java
@ManagedOperation
public void requestRefresh() {
    executor.submit(this::refreshInternal);
}
```

In this case, the success of the call only confirms that the method finished submitting the request. A more monitorable design can return a job ID:

```java
@ManagedOperation
public String requestRefresh(String cacheName) {
    return scheduleRefresh(cacheName);
}

@ManagedOperation
public String refreshStatus(String jobId) {
    return lookupRefreshStatus(jobId);
}
```

`scheduleRefresh` and `lookupRefreshStatus` are illustrative business components that require real implementations when used.

## 9. Complex Java Objects

An operation:

```java
@ManagedOperation
public JobResult submit(JobRequest request) {
    // ...
}
```

may be valid in Java yet difficult to use over JMX because:

- JConsole may not be able to construct an instance of `JobRequest` from the UI.
- External Java clients must know the class and a compatible version.
- Remote connectors may require serialization and matching classpaths.
- Changing packages, fields, or DTO structure can break older clients.
- Returned data can expose internal details or create large payloads.

JMX does not forbid all custom objects, but a contract using internal classes tightly couples clients to implementation details.

Instead of exposing the entire DTO, you can provide a management facade:

```java
@ManagedOperation(
    description = "Submit a predefined job configuration"
)
public String submitPredefinedJob(String definitionId) {
    JobRequest request = lookupDefinition(definitionId);
    JobResult result = jobService.submit(request);
    return result.id();
}
```

The client only needs a `String` to specify an allowlisted configuration and receives a job ID; `JobRequest`/`JobResult` remain in the business layer. Helper methods and classes in the example are hypothetical application code, not built-in Spring APIs.

## 10. Enums and Arrays

Enum:

```java
enum Mode {
    NORMAL, MAINTENANCE
}

@ManagedOperation
public void setMode(Mode mode) {
    // ...
}
```

The JMX signature of the parameter is the fully qualified enum class name, such as `example.jmx.Mode`. Remote clients must have a compatible type to construct the value; JConsole may not be able to enter it directly.

An easier-to-use option is a validated `String`:

```java
@ManagedOperation
public void setMode(String rawMode) {
    Mode selected = Mode.valueOf(rawMode);
    // Check permissions and execute the transition.
}
```

For arrays, JMX metadata may use JVM-style descriptor representations such as `[Ljava.lang.String;`, depending on the operation type and registration model. Do not assume `String[]` is the exact signature string; read `MBeanParameterInfo.getType()`.

## 11. Standard MBean, ModelMBean, and MXBean

**Standard MBean** uses a management interface by convention, such as `CacheControlMBean`. Operations come from methods in the interface.

**Spring annotation ModelMBean** uses metadata from `@ManagedResource`, `@ManagedOperation`, and related annotations to describe the bean's management interface. Annotations do not automatically convert all business DTOs into neutral types.

**MXBean** uses mapping rules between Java types and JMX Open Types. Certain compatible composite, collection, or map types can be represented as `CompositeData` or `TabularData`, helping reduce client dependency on implementation classes.

```text
Standard MBean:
  Java interface -> JMX operation

Spring ModelMBean:
  Annotation metadata -> JMX operation

MXBean:
  Java management interface -> MXBean type mapping
                             -> JMX Open Types
```

Do not treat adding `@ManagedOperation` as having created an MXBean. When Open Type mapping is desired, use the MXBean or Open MBean model with the proper contract.

## 12. CompositeData and TabularData

Open MBeans provide data representations with publicly described schemas:

- `SimpleType`: standard values such as `String`, `Integer`, `Long`, and `Boolean`.
- `ArrayType`: arrays whose elements belong to valid Open Types.
- `CompositeType` and `CompositeData`: records with named fields and specific types.
- `TabularType` and `TabularData`: sets of records in a table structure with index keys.

Example of building a status record:

```java
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

String[] keys = { "active", "maximum", "healthy" };

CompositeType type = new CompositeType(
    "WorkerStatus",
    "Worker pool status",
    keys,
    new String[] {
        "Active workers",
        "Maximum workers",
        "Healthy"
    },
    new OpenType<?>[] {
        SimpleType.INTEGER,
        SimpleType.INTEGER,
        SimpleType.BOOLEAN
    }
);

CompositeData data = new CompositeDataSupport(
    type,
    keys,
    new Object[] { 3, 16, true }
);
```

To return this data from an operation, expose an appropriate method via an MBean/MXBean. `CompositeData` lets clients read structured data without internal DTO classes, though the schema must still be kept stable.

## 13. Reading the Actual Signature via MBeanInfo

Use `MBeanServerConnection.getMBeanInfo` to view the management contract after the exporter has registered it:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    MBeanParameterInfo[] parameters = op.getSignature();

    for (int i = 0; i < parameters.length; i++) {
        if (i > 0) System.out.print(", ");
        System.out.print(parameters[i].getType());
    }

    System.out.println(") -> " + op.getReturnType());
}
```

Example output:

```text
resizeWorkers(int) -> void
currentWorkerLimit() -> int
```

The type names in metadata are the basis for clients to construct `signature`, especially when there are overloads, arrays, or non-simple types.

When multiple methods share the same name, match the full name and type sequence; never arbitrarily pick the first overload.

## 14. Verifying an Operation Against Metadata

A client or integration test can verify the contract before invoking:

```java
import java.util.Arrays;
import javax.management.MBeanOperationInfo;

MBeanOperationInfo op = Arrays.stream(
    connection.getMBeanInfo(name).getOperations()
)
    .filter(candidate ->
        candidate.getName().equals("resizeWorkers"))
    .filter(candidate ->
        candidate.getSignature().length == 1)
    .filter(candidate ->
        "int".equals(candidate.getSignature()[0].getType()))
    .findFirst()
    .orElseThrow();

if (!"void".equals(op.getReturnType())) {
    throw new IllegalStateException("Unexpected return type");
}
```

This is an illustrative snippet used inside a method where `connection` and `name` are already initialized. You can use `MBeanInfo` for contract checks during releases to avoid accidentally changing types of operations used by monitoring clients.

## 15. Wrong Signatures and Exceptions

Common related errors:

| Issue | Symptom | Resolution |
|---|---|---|
| Wrong ObjectName | `InstanceNotFoundException` | Check registration and connected MBeanServer |
| Wrong name/signature | `ReflectionException` or routing error | Read `MBeanInfo` and match types in order |
| Method throws checked exception | `MBeanException` | Inspect root exception |
| Method throws runtime exception | `RuntimeMBeanException` | Check validation and operation logic |
| Remote connector failure | `IOException`, RMI/serialization error | Check connection and data types |
| Wrong return type expectation | `ClassCastException` on client | Read `getReturnType()` |
| Missing permissions | `SecurityException` | Check JMX access configuration |

Example of a wrong signature:

```java
// resizeWorkers(int) but the client sends the wrapper type.
connection.invoke(
    name,
    "resizeWorkers",
    new Object[] { 8 },
    new String[] { "java.lang.Integer" }
);
```

Fix it to `new String[] { "int" }`. If `ReflectionException` occurs, this is just one line of investigation; reflection errors can have other causes, so inspect the cause.

## 16. Compatibility with JMX Tools

In JConsole, you can:

1. Open the MBeans tab and locate the right `ObjectName`.
2. View Operations to see operation names and parameters.
3. Invoke no-arg methods or use types supported by the UI.
4. Check the displayed result, then read related attributes.
5. If a method accepts complex DTOs, use a compatible Java client or redesign the management contract.

A valid operation whose parameters cannot be entered in the GUI is not necessarily registered incorrectly. However, if the goal is operating from JConsole, hard-to-enter types make the administrative API less useful.

Both local and remote JMX route via `ObjectName` and operation signatures. With remote access, passing objects can introduce additional serialization and class compatibility requirements. `@EnableMBeanExport` only enables MBean export; it does not open a remote JMX connector on its own.

## 17. Designing Stable Operations

When writing `@ManagedOperation`, prioritize:

- Method names expressing specific actions, such as `resizeWorkers`, `refreshCache`.
- Clear units: `setTimeoutMillis(long)` is better than an ambiguous name like `setTimeout(long)`.
- Small inputs, common types, and bounds validation.
- Interpretable return values containing no secrets or full object graphs.
- Avoiding dependence on internal classes when clients operate independently.
- Avoiding complex overloads when the primary client is a GUI.
- Not using exception messages as a channel that leaks sensitive configuration.
- For long-running tasks, returning a job ID and providing status instead of holding the call open indefinitely.

Example:

```java
@ManagedOperation(description = "Set timeout in milliseconds")
public void setTimeoutMillis(long value) {
    if (value < 100L || value > 60_000L) {
        throw new IllegalArgumentException(
            "timeout must be 100..60000 ms"
        );
    }
    // Apply the actual configuration.
}
```

When remote connections exist, authentication, authorization, TLS, and network restrictions must be configured at the management connection layer; annotations do not provide those policies out of the box.

## 18. Practice Exercise

A service has the API:

```java
JobResult submit(JobRequest request);
void resize(int workers);
Map<String, JobStatus> listJobs();
```

Design a JMX facade so operators do not need the `JobRequest`, `JobResult`, or `JobStatus` classes.

Hint:

```java
@Component
@ManagedResource(
    objectName = "app.monitoring:type=SchedulerControl,name=main"
)
public class SchedulerControl {

    private final SchedulerService service;

    public SchedulerControl(SchedulerService service) {
        this.service = service;
    }

    @ManagedOperation
    public void resizeWorkers(int workers) {
        if (workers < 1 || workers > 64) {
            throw new IllegalArgumentException("workers must be 1..64");
        }
        service.resize(workers);
    }

    @ManagedOperation
    public String submitPredefinedJob(String definitionId) {
        JobRequest request = lookupDefinition(definitionId);
        JobResult result = service.submit(request);
        return result.id();
    }
}
```

The classes `SchedulerService`, `JobRequest`, `JobResult`, and helper `lookupDefinition` are hypothetical application components. In a real system, the facade should use an allowlist for `definitionId`, check permissions, limit side effects, and audit administrative actions.

A JMX client invokes:

```java
connection.invoke(
    name,
    "resizeWorkers",
    new Object[] { 12 },
    new String[] { "int" }
);
```

This operation is easy to test and does not force clients to depend on business DTOs.

## 19. Self-Check Questions

1. Why does `@ManagedOperation` on a Java method not guarantee JConsole can enter every parameter?
2. Why are `int` and `java.lang.Integer` two different JMX signatures?
3. Does `@ManagedOperationParameters` change parameter types or only describe metadata?
4. Why should `MBeanInfo` be read before building a generic JMX client?
5. What does a `void` return type mean for an operation that launches an asynchronous job?
6. What risks arise when exposing `JobRequest` and `JobResult` directly?
7. How does MXBean differ from Spring ModelMBean regarding type mapping?
8. When should `CompositeData` and `TabularData` be used?
9. How can replacing `resize(int)` with `resize(long)` break older clients?
10. Why do simple data types still require validation and authorization?

## 20. Key Takeaways

```text
@ManagedOperation
     |
     v
MBeanOperationInfo
  - name
  - parameter types
  - return type
     |
     v
MBeanServer.invoke(
  ObjectName,
  operationName,
  Object[] values,
  String[] declaredTypes
)
     |
     v
Method invoked and result returned
```

**Core principle:** `@ManagedOperation` determines which methods are published. `MBeanInfo` reveals the actual types and signatures. Clients must use the exact signature, while data transportability and tool input capabilities determine compatibility. Keep JMX contracts small, stable, and prefer simple types or Open Types when needed.