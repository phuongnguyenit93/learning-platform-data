# Invoking Operations with Signatures and Parameters in MBeanServer

> **Topic:** Spring Framework JMX  
> **Knowledge Area:** MBeanServer  
> **Lesson:** Invoking Operations with Signatures and Parameters

## 1. Objectives

After this lesson, you will be able to:

- Explain the **`MBeanServer.invoke(ObjectName, String, Object[], String[])`** mechanism for invoking an operation published by an MBean.
- Distinguish the **operation name**, **parameter value array** (`params`), and **parameter type name array** (`signature`).
- Read `MBeanInfo`/`MBeanOperationInfo` to find the actual contract before invoking.
- Invoke operations with zero, one, or multiple parameters and handle return values.
- Identify errors caused by wrong names, parameter counts/types, unregistered MBeans, or exceptions thrown by the executed method.
- Understand the roles of the Spring JMX exporter and JMX client in the call path.

## 2. Mental Model: invoke Is a Call Against a Management Contract

When a Spring bean is registered as an MBean, the exposed operations form its **management contract**. A JMX client does not look up arbitrary methods on a Java object directly; the client sends a request to `MBeanServer`, uses `ObjectName` to identify the MBean, and then uses **operation name + parameter signature** to locate the corresponding operation.

\`\`\`text
Spring Bean
  |
  | MBeanExporter / ModelMBean or Standard MBean
  v
MBeanServer
  |
  +-- ObjectName: training.jmx:type=JobController,name=primary
  |       +-- Attributes
  |       +-- Operations
  |             +-- refresh()
  |             +-- resize(int)
  |             +-- move(java.lang.String, int)
  |
  ^ MBeanServer.invoke(ObjectName, name, params, signature)
  |
JMX client / JConsole / remote JMX connector
\`\`\`

In this model, `MBeanServer` is the routing and execution point. It needs to know **which MBean**, **which operation**, and **how to interpret each argument**. Having Spring create a bean or export an MBean does not replace the JMX contract: the client must still invoke the exact published operation.

Do not confuse `invoke(...)` with `getAttribute(...)` or `setAttribute(...)`. A getter exported as a JMX attribute should usually be accessed with `getAttribute`, whereas an action such as `reset`, `refresh`, or `resize` can be exposed as a JMX operation.

## 3. Core API

The key method in `javax.management.MBeanServer`:

\`\`\`java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
) throws InstanceNotFoundException,
         MBeanException,
         ReflectionException;
\`\`\`

Meaning of each argument:

| Argument | Role | Example |
|---|---|---|
| `name` | `ObjectName` identifying the registered MBean | `training.jmx:type=JobController,name=primary` |
| `operationName` | Name of the operation published by the MBean | `"resize"` |
| `params` | Argument values in the exact order of the signature | `new Object[] { 8 }` |
| `signature` | Fully qualified Java type names corresponding to each parameter | `new String[] { "int" }` |
| Return value | `Object`, depending on the operation's return type; `void` operations usually return `null` | `Integer`, `String`, `null` |

**The two arrays `params` and `signature` must align positionally.** Element `i` of `params` is the value for the parameter whose type is described at element `i` of `signature`.

Example:

\`\`\`java
server.invoke(
    objectName,
    "move",
    new Object[] { "retry", 3 },
    new String[] { "java.lang.String", "int" }
);
\`\`\`

This call requests an operation matching the signature `move(String, int)`. The two types in `signature` are **not** variable names like `queueName` or `count`; they are type names according to JMX metadata.

## 4. Why Must signature Be Passed?

Java supports overloading: methods can share the same name while differing in parameter type lists.

\`\`\`java
void resize(int size)
void resize(long size)
void resize(String profile)
\`\`\`

If a client only sends the name `resize`, the system lacks enough information to select one overload unambiguously. `signature` describes the intended types:

\`\`\`java
new String[] { "int" }                  // resize(int)
new String[] { "long" }                 // resize(long)
new String[] { "java.lang.String" }     // resize(String)
\`\`\`

In JMX, matching relies on the published operation signature rather than attempting arbitrary type coercions as during Java compilation. Therefore, passing `Integer.valueOf(8)` with signature `"java.lang.Integer"` **does not substitute** for `"int"` if the operation declares an `int` parameter.

Distinguish two layers of information:

- **Declared parameter type**: `int`, `long`, `boolean`, `java.lang.String`, ...
- **Actual object carried inside `Object[]`**: primitives like `int` are boxed into wrappers (`Integer`), while strings are `String`.

Example for `resize(int)`:

\`\`\`java
Object[] params = { Integer.valueOf(8) };
String[] signature = { "int" };

server.invoke(objectName, "resize", params, signature);
\`\`\`

Do not write `"Integer"` just because `params[0]` is an `Integer`. For reference types, use the fully qualified class name (such as `java.lang.String`), not the short name `String`.

## 5. Complete Example: Creating a Standard MBean and Invoking Operations

The example below runs within a single JVM using the platform MBeanServer and does not require enabling remote JMX. A Standard MBean is defined through an interface with the `MBean` suffix and a corresponding implementation class.

### 5.1. Management Contract

\`\`\`java
package example.jmx;

public interface JobControllerMBean {
    void refresh();

    void resize(int workers);

    String move(String queueName, int batchSize);

    int getWorkerCount();
}
\`\`\`

### 5.2. Implementation

\`\`\`java
package example.jmx;

public class JobController implements JobControllerMBean {

    private int workerCount = 2;

    @Override
    public void refresh() {
        System.out.println("Refreshing scheduler");
    }

    @Override
    public void resize(int workers) {
        if (workers <= 0) {
            throw new IllegalArgumentException(
                "workers must be greater than zero"
            );
        }
        workerCount = workers;
    }

    @Override
    public String move(String queueName, int batchSize) {
        if (queueName == null || queueName.isBlank()) {
            throw new IllegalArgumentException("queueName is required");
        }
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be positive");
        }
        return "Moved " + batchSize + " item(s) to " + queueName;
    }

    @Override
    public int getWorkerCount() {
        return workerCount;
    }
}
\`\`\`

The methods in the `JobControllerMBean` interface form the management surface. `getWorkerCount()` is represented as attribute `WorkerCount`; the methods `refresh`, `resize`, and `move` are operations. Having additional public methods in the MBean implementation does not mean those methods are exposed as well.

### 5.3. Registering and Invoking

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxInvokeDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "training.jmx:type=JobController,name=primary"
        );

        // Register Standard MBean; this example assumes this name is not yet in use.
        server.registerMBean(new JobController(), name);

        try {
            // 1) Operation with no parameters
            server.invoke(
                name,
                "refresh",
                new Object[0],
                new String[0]
            );

            // 2) Operation taking int
            server.invoke(
                name,
                "resize",
                new Object[] { 8 },
                new String[] { "int" }
            );

            // 3) Operation taking String + int and returning String
            Object outcome = server.invoke(
                name,
                "move",
                new Object[] { "retry", 3 },
                new String[] { "java.lang.String", "int" }
            );
            System.out.println(outcome);

            // Attribute read: different from operation invoke
            Object current = server.getAttribute(
                name,
                "WorkerCount"
            );
            System.out.println("workers = " + current);
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Illustrative output:

\`\`\`text
Refreshing scheduler
Moved 3 item(s) to retry
workers = 8
\`\`\`

Processing sequence:

\`\`\`text
invoke("resize", [8], ["int"])
      |
      v
MBeanServer locates ObjectName
      |
      v
MBeanServer routes operation resize(int)
      |
      v
JobController.resize(8)
      |
      v
workerCount state is updated
      |
      v
getAttribute("WorkerCount") -> 8
\`\`\`

Remember: even though the example runs through the JMX API, `workerCount` is state on the implementation object. When an operation mutates state, subsequent attribute reads reflect the new state.

## 6. Zero-Parameter Calls and Empty Arrays vs. null

A parameterless operation is invoked cleanly with:

\`\`\`java
server.invoke(
    name,
    "refresh",
    new Object[0],
    new String[0]
);
\`\`\`

The JMX API allows passing `null` for `params` and `signature` when there are no parameters, but using two empty arrays makes the client's intent easier to read, especially when building calls from metadata. Do not pass a single-element array containing `null` if the operation takes **no parameters**: `new Object[]{ null }` means one argument, not zero arguments.

Comparison:

\`\`\`java
// refresh(): correct
new Object[0];
new String[0];

// setLabel(String): one argument with value null
new Object[] { null };
new String[] { "java.lang.String" };
\`\`\`

For an operation taking a primitive type, `null` cannot be unboxed into a valid primitive value. For reference parameters, whether `null` is accepted depends on the MBean implementation.

## 7. Reading Metadata Before Calling

Do not guess signatures from source code or display names in a UI. For a registered MBean, `MBeanServer.getMBeanInfo(ObjectName)` returns metadata containing the list of operations and their corresponding parameters.

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

// server and name have already been initialized.
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    MBeanParameterInfo[] parameters = op.getSignature();
    for (int i = 0; i < parameters.length; i++) {
        if (i > 0) {
            System.out.print(", ");
        }
        System.out.print(parameters[i].getType());
    }

    System.out.println(") -> " + op.getReturnType());
}
\`\`\`

With the example above, the metadata essentially has:

\`\`\`text
refresh() -> void
resize(int) -> void
move(java.lang.String, int) -> java.lang.String
\`\`\`

The operation name and type names in `MBeanOperationInfo`/`MBeanParameterInfo` are the reference point for building an exact `signature`. Generic client code can filter by `op.getName()`, parameter count, and `getType()` to pick the right operation, then convert UI input into Java objects of the proper types.

### Building signature Directly from MBeanOperationInfo

\`\`\`java
import java.util.Arrays;
import javax.management.MBeanOperationInfo;

MBeanOperationInfo moveOperation = Arrays.stream(
        server.getMBeanInfo(name).getOperations()
    )
    .filter(op -> op.getName().equals("move"))
    .filter(op -> op.getSignature().length == 2)
    .findFirst()
    .orElseThrow();

String[] signature = Arrays.stream(
        moveOperation.getSignature()
    )
    .map(param -> param.getType())
    .toArray(String[]::new);
\`\`\`

This example simply picks the first two-parameter overload named `move`; in an application supporting actual overloading, you must match the **entire type list** rather than arbitrarily taking the first overload.

## 8. Wrong Signatures and Common Errors

### Primitive/Wrapper Type Mismatch

\`\`\`java
// Actual operation is resize(int)
server.invoke(
    name,
    "resize",
    new Object[] { 8 },
    new String[] { "java.lang.Integer" } // Does not match "int"
);
\`\`\`

An `Integer` in `params` does not change the declared signature from `int` to `java.lang.Integer`. You must use `new String[]{"int"}`.

### Wrong Parameter Order

\`\`\`java
// Actual: move(String, int)
server.invoke(
    name,
    "move",
    new Object[] { 3, "retry" },
    new String[] { "int", "java.lang.String" }
);
\`\`\`

This describes a different contract `move(int, String)`, which does not match the `move(String, int)` operation.

### Missing Parameters or Mismatched Array Lengths

\`\`\`java
server.invoke(
    name,
    "move",
    new Object[] { "retry", 3 },
    new String[] { "java.lang.String" }
);
\`\`\`

`params.length` and `signature.length` do not match. Clients should validate this before sending. Even when lengths match, every type must still match the published operation signature.

### Correct Signature but Implementation Throws an Exception

\`\`\`java
server.invoke(
    name,
    "resize",
    new Object[] { -1 },
    new String[] { "int" }
);
\`\`\`

JMX located `resize(int)`, but business logic rejected `-1`. With a Standard MBean, an exception from the invoked method may be wrapped in `MBeanException` if it is a checked exception, or `RuntimeMBeanException` if it is a runtime exception. Therefore, distinguish **routing/signature errors** from **errors during method execution**.

## 9. Layered Exception Handling

Important exceptions for `MBeanServer.invoke`:

| Exception | Practical Meaning | How to Handle |
|---|---|---|
| `InstanceNotFoundException` | MBean not found for `ObjectName`. | Check registration, name, and the right MBeanServer. |
| `ReflectionException` | Reflection error or unable to route/match operation. | Compare `getMBeanInfo` and `signature`; inspect the inner cause. |
| `MBeanException` | MBean method threw a checked exception wrapped by JMX. | Read `getTargetException()` or cause. |
| `RuntimeMBeanException` | Runtime exception occurred in MBean, wrapped by JMX. | Inspect the underlying exception and business inputs. |
| `RuntimeErrorException` | An `Error` occurred during MBean execution and was wrapped by JMX. | Inspect the severe error from implementation/runtime. |
| `SecurityException` | Invocation blocked by current security mechanism. | Check policy, permissions, and connection setup. |

Targeted handling pattern:

\`\`\`java
import javax.management.InstanceNotFoundException;
import javax.management.MBeanException;
import javax.management.ReflectionException;
import javax.management.RuntimeMBeanException;

try {
    Object result = server.invoke(
        name,
        "resize",
        new Object[] { 8 },
        new String[] { "int" }
    );
    System.out.println("Result: " + result);
} catch (InstanceNotFoundException e) {
    System.err.println("MBean is not registered: " + name);
} catch (ReflectionException e) {
    System.err.println("Operation/signature mismatch: " + e);
} catch (MBeanException e) {
    System.err.println(
        "MBean checked exception: " + e.getTargetException()
    );
} catch (RuntimeMBeanException e) {
    System.err.println(
        "MBean runtime exception: " + e.getTargetException()
    );
}
\`\`\`

The message "operation/signature mismatch" is a **diagnostic hint** when receiving `ReflectionException`, not a guarantee that every `ReflectionException` is caused by a wrong signature. Inspect the cause and metadata to determine the real root cause.

## 10. Relation to Spring Framework JMX

In Spring, `MBeanExporter` can publish regular beans as MBeans using metadata from `@ManagedResource`, `@ManagedOperation`, `@ManagedAttribute`, or assembler configuration. JMX clients still call `MBeanServer` according to the JMX contract.

Spring bean example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.jmx:type=JobController,name=spring"
)
public class SpringJobController {

    private int workerCount = 2;

    @ManagedOperation(description = "Resize worker pool")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "workers",
            description = "New worker count"
        )
    })
    public void resize(int workers) {
        if (workers <= 0) {
            throw new IllegalArgumentException(
                "workers must be positive"
            );
        }
        this.workerCount = workers;
    }
}
\`\`\`

Export configuration:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {
}
\`\`\`

Once the bean is exported successfully, a client calls:

\`\`\`java
ObjectName springBean = new ObjectName(
    "training.jmx:type=JobController,name=spring"
);

server.invoke(
    springBean,
    "resize",
    new Object[] { 6 },
    new String[] { "int" }
);
\`\`\`

Here `server` must be **the exact MBeanServer used by the Spring exporter**. When using the platform MBeanServer, you can obtain it via `ManagementFactory.getPlatformMBeanServer()`; when exporting to another MBeanServer, you must connect to that server.

Call path:

\`\`\`text
JMX Client
  -> MBeanServer.invoke(name, "resize", [6], ["int"])
  -> MBean implementation / Spring ModelMBean adapter
  -> SpringJobController.resize(6)
  -> state is updated
\`\`\`

`@ManagedOperationParameters` describes parameter **names and meanings** for metadata-reading tools; it does not change the Java type `int` or parameter order. `signature` in `invoke` still uses the type names published by JMX.

### JConsole and Operations

In the MBeans tab, JConsole displays published operations along with input fields for supported parameter types. When clicking the invoke button, the tool sends a JMX request with the operation name and corresponding signature. The ability to input and convert a specific data type depends on the client; not all Java types are directly supported by the JConsole UI. For automation, `MBeanServerConnection.invoke(...)` usually gives more precise control over arguments/signatures.

## 11. MBeanServerConnection and Remote Invocation

A remote client typically holds an `MBeanServerConnection` rather than a local `MBeanServer`. `MBeanServerConnection` provides the same `invoke` operation.

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

// Illustrative URL: depends on actual RMI connector configuration.
JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName name = new ObjectName(
        "training.jmx:type=JobController,name=primary"
    );

    Object result = connection.invoke(
        name,
        "move",
        new Object[] { "retry", 3 },
        new String[] { "java.lang.String", "int" }
    );

    System.out.println(result);
}
\`\`\`

The example assumes a JMX connector has been configured separately and is listening at the URL above. `@EnableMBeanExport` itself **does not open a remote endpoint**. Remote JMX must have proper access protection such as authentication, authorization, TLS, and network restrictions; state-mutating operations should be granted deliberately.

For remote JMX, parameter/return data must satisfy connector transport requirements, usually involving serialization and class availability; prefer simple, standard JMX types when designing MBean APIs.

## 12. Designing Operations That Are Easy to Call and Operate

A good JMX operation should have:

- **Clear naming**: `refreshCache`, `pauseScheduler`, `resizePool`, instead of `doIt`.
- **Simple and stable parameters**: primitives, `String`, or suitable JMX types. Avoid depending on complex internal classes for remote clients.
- **Input validation**: negative numbers, empty strings, and invalid states must be rejected with clear messages.
- **Deterministic feedback**: can return a result or status; a `void` operation typically signals completion by not throwing an error.
- **Controlled side effects**: operations that clear caches, stop services, or modify resources need appropriate permissions, timeouts, and logging.
- **Helpful metadata**: describe operations/parameters with annotations or an MBean interface so operators see their meaning.
- **Avoid hard-to-distinguish overloads**: if management clients are mainly GUIs, distinct names like `resizeWorkers` and `resizeQueues` are usually easier to operate than overloading `resize`.

A long-running operation can block management threads. Consider an operation that triggers work and returns a job ID/status, while providing an attribute/operation to query progress. Make sure the result clearly reflects whether the request was "accepted" or "completed".

## 13. Practice Exercise

Suppose `MBeanInfo` publishes the following operations:

\`\`\`text
reload() -> void
setThrottle(int) -> void
send(java.lang.String, long, boolean) -> java.lang.String
\`\`\`

Fill in the corresponding JMX calls.

**A.** Call `reload()`:

\`\`\`java
server.invoke(
    name,
    "reload",
    new Object[0],
    new String[0]
);
\`\`\`

**B.** Call `setThrottle(25)`:

\`\`\`java
server.invoke(
    name,
    "setThrottle",
    new Object[] { 25 },
    new String[] { "int" }
);
\`\`\`

**C.** Call `send("orders", 100L, true)`:

\`\`\`java
Object response = server.invoke(
    name,
    "send",
    new Object[] { "orders", 100L, true },
    new String[] {
        "java.lang.String",
        "long",
        "boolean"
    }
);
\`\`\`

**D.** Explain why the following signature is incorrect for `send(String, long, boolean)`:

\`\`\`java
new String[] {
    "String",
    "java.lang.Long",
    "java.lang.Boolean"
}
\`\`\`

Because `String` lacks the fully qualified type name (`java.lang.String`), and `Long`/`Boolean` are wrapper types that differ from the declared primitive types `long`/`boolean`. Obtain the actual types from `MBeanOperationInfo.getSignature()` rather than guessing from the runtime value's class.

## 14. Checklist When invoke Fails

1. **Is it the right MBeanServer?** Is local/remote accessing the same registry where the MBean was registered?
2. **Is it the right ObjectName?** `isRegistered(name)` for a local server or `isRegistered` on `MBeanServerConnection` helps verify.
3. **Is the operation exposed?** Inspect `getMBeanInfo(name).getOperations()` instead of inferring from public methods.
4. **Does the operation name match exactly?** JMX is exact about names and types; do not use arbitrary display names.
5. **Does the parameter count match?** `params.length == signature.length` and equals the declared parameter count.
6. **Are types and order exact?** Use `int`, `long`, `boolean` for primitives; FQCN for objects like `java.lang.String`.
7. **Are the values valid?** Valid types can still violate business rules.
8. **Which layer failed?** Distinguish missing MBean, mismatched operation, method-thrown exception, and remote connector failure.
9. **Are access permissions sufficient?** Especially for administrative operations with state-changing effects.
10. **Is the result interpreted properly?** A `void` operation normally returns `null`; the new state may require reading back an attribute.

## 15. Model Summary

A JMX operation call is determined by the quadruple:

\`\`\`text
ObjectName + OperationName + Params[] + Signature[]
\`\`\`

Typical example:

\`\`\`java
server.invoke(
    new ObjectName("training.jmx:type=JobController,name=primary"),
    "move",
    new Object[] { "retry", 3 },
    new String[] { "java.lang.String", "int" }
);
\`\`\`

**The most important rule:** `params` holds **values**, `signature` holds **declared type names**, and both arrays must match in **count, order, and the operation contract published by the MBean**. Use `MBeanInfo` as the source of truth to verify signatures, then inspect exceptions at the right layer to diagnose failures.