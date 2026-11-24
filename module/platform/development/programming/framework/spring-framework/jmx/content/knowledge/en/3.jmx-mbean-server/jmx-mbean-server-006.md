# MBeanServer: Distinguishing Name Errors, Type Errors, and Operation Execution Errors

## 1. Why Distinguish the Three Error Groups?

In JMX, a management application calls MBeans through `MBeanServer` or `MBeanServerConnection`. A call can fail because of **selecting the wrong object or member**, **passing the wrong type/signature**, or **code inside the operation actually throwing an error**. These scenarios have different troubleshooting paths.

Imagine a JMX call passing through three gates:

\`\`\`text
JMX client
    |
    v
[1] Target Identification
    Does ObjectName have an MBean?
    Are attribute/operation names exact?
    |
    v
[2] Contract Matching
    Is attribute readable/writable?
    Is passed value the right type?
    Does operation have the right signature?
    |
    v
[3] Execution
    Getter / setter / operation is invoked
    Does business logic throw an exception?
    |
    v
Return result or exception to client
\`\`\`

The key point: **the same "JMX call failed" message is not enough to know where the failure occurred**. You need to examine the exception type, root cause (`cause`/`targetException`), ObjectName, attribute/operation name, parameter signature, and MBean metadata.

An illustrative MBean has the identifier:

\`\`\`text
com.example.app:type=WorkerControl,name=main
\`\`\`

and publishes:

| JMX Member | Kind | Contract |
|---|---|---|
| `MaxThreads` | Attribute | `int`, readable and writable, values from 1 to 64 |
| `Active` | Attribute | `boolean`, read-only |
| `ProcessedCount` | Attribute | `long`, read-only |
| `pause()` | Operation | No parameters, `void` |
| `resize(int)` | Operation | One primitive `int` parameter, `void` |
| `resetCounters()` | Operation | No parameters, `void` |

This is an illustrative contract; when working with real systems, read the metadata of the registered MBean instead of inferring from Java class names.

## 2. Java Foundation for Reproducing Errors

A standard MBean has an interface ending with `MBean`. The short example below has getters, setters, and operations to illustrate the error paths:

\`\`\`java
package com.example.jmx;

public interface WorkerControlMBean {
    int getMaxThreads();

    void setMaxThreads(int value);

    boolean isActive();

    long getProcessedCount();

    void pause();

    void resize(int threads);

    void resetCounters();
}
\`\`\`

\`\`\`java
package com.example.jmx;

public class WorkerControl implements WorkerControlMBean {
    private int maxThreads = 8;
    private boolean active = true;
    private long processedCount = 0;

    @Override
    public synchronized int getMaxThreads() {
        return maxThreads;
    }

    @Override
    public synchronized void setMaxThreads(int value) {
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException(
                "maxThreads must be in range 1..64"
            );
        }
        maxThreads = value;
    }

    @Override
    public synchronized boolean isActive() {
        return active;
    }

    @Override
    public synchronized long getProcessedCount() {
        return processedCount;
    }

    @Override
    public synchronized void pause() {
        active = false;
    }

    @Override
    public synchronized void resize(int threads) {
        setMaxThreads(threads);
    }

    @Override
    public synchronized void resetCounters() {
        processedCount = 0;
    }
}
\`\`\`

Registering with the JVM's MBeanServer in an example program:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RegisterWorkerMBean {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.app:type=WorkerControl,name=main"
        );

        if (!server.isRegistered(name)) {
            server.registerMBean(new WorkerControl(), name);
        }

        System.out.println(
            server.getAttribute(name, "MaxThreads")
        );
    }
}
\`\`\`

In a Spring Framework application, `MBeanExporter` can register a bean as a Standard MBean, or export it as a ModelMBean based on `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`. The adapter mechanism can change details of the returned exception; still, analyze by **failure step** first, then rely on the specific exception and metadata.

The examples below use `javax.management.*` (the JMX package in Java SE), which works with the JMX API even when the MBean is managed through Spring.

## 3. Group 1: Name and Identification Errors

Name errors occur when the client picks the wrong **ObjectName** or the wrong attribute/operation name.

### 3.1. Valid ObjectName but No Matching MBean

\`\`\`java
ObjectName wrongTarget = new ObjectName(
    "com.example.app:type=WorkerControl,name=secondary"
);

// Assume only MBean name=main is registered:
server.getAttribute(wrongTarget, "MaxThreads");
\`\`\`

With a standard `MBeanServer`, calling an unregistered MBean typically throws:

\`\`\`text
javax.management.InstanceNotFoundException
\`\`\`

Check:

\`\`\`java
boolean exists = server.isRegistered(wrongTarget);
System.out.println("registered=" + exists);

for (ObjectName candidate :
        server.queryNames(
            new ObjectName("com.example.app:type=WorkerControl,*"),
            null
        )) {
    System.out.println(candidate);
}
\`\`\`

Distinguish:

- `MalformedObjectNameException`: invalid `ObjectName` syntax, which can occur immediately when constructing `new ObjectName(...)`.
- `InstanceNotFoundException`: ObjectName parsed successfully, but no registered MBean was located at the time of the call.
- `InstanceAlreadyExistsException`: occurs when **registering** a duplicate ObjectName, not when reading an attribute.

If the application generates names automatically via a Spring exporter, retrieve the actual ObjectName from MBeanServer or the export configuration, especially when there are multiple beans of the same type.

### 3.2. MBean Exists but Attribute Name Is Wrong

\`\`\`java
server.getAttribute(name, "MaxThread"); // Missing trailing 's'
\`\`\`

Typical error:

\`\`\`text
javax.management.AttributeNotFoundException
\`\`\`

JMX attribute names are case-sensitive. `MaxThreads`, `maxThreads`, and `MaxThread` are not treated as the same attribute by default.

To view the exact names:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s | type=%s | read=%s | write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
\`\`\`

An attribute that exists but is not readable or not writable can also lead to `AttributeNotFoundException` on the corresponding interaction. Therefore, **seeing `AttributeNotFoundException` is not enough to conclude it is merely a typo**; check the read/write permissions in metadata.

### 3.3. Wrong Operation Name

\`\`\`java
server.invoke(
    name,
    "paus",                 // Wrong name: pause
    new Object[0],
    new String[0]
);
\`\`\`

Depending on the MBean implementation, a missing operation error may surface as `ReflectionException` (often containing a cause like `NoSuchMethodException`) or a dispatch-related exception. Unlike attributes, do not assume a misspelled operation name will throw `AttributeNotFoundException`.

Discovering operations:

\`\`\`java
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.print(operation.getName() + "(");
    MBeanParameterInfo[] signature = operation.getSignature();

    for (int i = 0; i < signature.length; i++) {
        if (i > 0) System.out.print(", ");
        System.out.print(signature[i].getType());
    }
    System.out.println(")");
}
\`\`\`

### 3.4. Quick Diagnosis of Name Errors

1. Can `ObjectName` be parsed? If not, fix the syntax.
2. Does `server.isRegistered(name)` return `true` at the time of checking?
3. Does `getMBeanInfo(name)` return metadata for the intended MBean?
4. Is the attribute/operation name **exact down to every character**?
5. For attributes, do the readable/writable flags allow the operation?
6. For operations, continue checking the signature in the type error group below.

Note: an MBean can be unregistered between the `isRegistered` check and the next call; pre-checking does not completely eliminate runtime errors.

## 4. Group 2: Value Type or Operation Signature Errors

Two common forms exist: **an attribute receives the wrong data type** and **an operation is invoked with a mismatched parameter type list**.

### 4.1. Writing an Attribute with the Wrong Type

Suppose `MaxThreads` has type `int`, which JMX represents when setting with the corresponding Java value:

\`\`\`java
import javax.management.Attribute;

server.setAttribute(
    name,
    new Attribute("MaxThreads", "16") // String, not Integer
);
\`\`\`

A Standard MBean may throw `InvalidAttributeValueException` because the value is incompatible with the attribute type. `"16"` is not automatically converted to an integer just because the string looks like a number.

Use the right type:

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxThreads", Integer.valueOf(16))
);
\`\`\`

Because Java primitive `int` is boxed into `Integer`, the object carrying the value for an `int` setter is normally `Integer`; this differs from passing a `String`.

### 4.2. Right Name, Wrong Operation Signature

Suppose the registered operation is:

\`\`\`java
void resize(int threads);
\`\`\`

A call with a wrong signature:

\`\`\`java
server.invoke(
    name,
    "resize",
    new Object[] { Integer.valueOf(12) },
    new String[] { "java.lang.Integer" } // Wrong declared signature
);
\`\`\`

The `params` array carries runtime values; the `signature` array describes the **declared parameter types** that MBeanServer uses to select the operation. For `resize(int)`, the type to send in the signature is `"int"`:

\`\`\`java
server.invoke(
    name,
    "resize",
    new Object[] { Integer.valueOf(12) },
    new String[] { "int" }
);
\`\`\`

Similarly:

| Java Declaration | JMX Signature String |
|---|---|
| `int` | `"int"` |
| `long` | `"long"` |
| `boolean` | `"boolean"` |
| `Integer` | `"java.lang.Integer"` |
| `String` | `"java.lang.String"` |

Do not replace `"int"` with `"Integer"`: that is neither a fully qualified type name nor a primitive.

### 4.3. Parameter Count and Overloading

The following calls do not match `resize(int)`:

\`\`\`java
// Missing parameters
server.invoke(name, "resize", new Object[0], new String[0]);

// Signature declares 2 parameters while operation declares 1
server.invoke(
    name,
    "resize",
    new Object[] { 12, 13 },
    new String[] { "int", "int" }
);
\`\`\`

Depending on the implementation, dispatch errors may produce `ReflectionException` or another wrapper. The metadata in `MBeanOperationInfo.getSignature()` is the most reliable source of truth.

If overloads `resize(int)` and `resize(long)` exist, `invoke` must specify the exact signature. Do not rely on implicit widening conversions like the Java compiler does when choosing overloads at compile time.

### 4.4. Type-Valid Value That Is Business-Invalid

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxThreads", Integer.valueOf(1000))
);
\`\`\`

`1000` is an `Integer`, so this is **not necessarily a JMX type error**. In the example, the setter checks the 1..64 range and throws `IllegalArgumentException`.

The error path may be wrapped by JMX into `RuntimeMBeanException` if a runtime exception escapes the MBean, or into another exception form when going through a Spring ModelMBean/adapter. You must inspect the cause to distinguish **a matched type contract where business validation failed** from a type mismatch at the JMX layer.

This is an important boundary: `InvalidAttributeValueException` usually suggests input incompatible with the attribute; however, an implementation may handle and map errors in its own way. You cannot accurately classify every case based on a single exception name while ignoring the cause.

## 5. Group 3: Errors During Operation Execution

Once the ObjectName exists, the operation is found, and parameters match, business logic can still fail: resource access failure, disallowed state, invalid data, or a bug in code.

Example of an operation throwing a checked exception:

\`\`\`java
package com.example.jmx;

public interface MaintenanceMBean {
    void refresh() throws Exception;
}
\`\`\`

\`\`\`java
package com.example.jmx;

public class Maintenance implements MaintenanceMBean {
    @Override
    public void refresh() throws Exception {
        throw new Exception("Could not read configuration source");
    }
}
\`\`\`

When `invoke` is called, a standard `MBeanServer` typically wraps a checked exception thrown by the operation in `MBeanException`:

\`\`\`java
import javax.management.MBeanException;
import javax.management.ObjectName;

try {
    server.invoke(
        new ObjectName("com.example.app:type=Maintenance"),
        "refresh",
        new Object[0],
        new String[0]
    );
} catch (MBeanException ex) {
    Throwable businessFailure = ex.getTargetException();
    System.err.println(
        "Operation was called but failed: "
            + businessFailure
    );
}
\`\`\`

If the operation throws an unchecked exception such as `IllegalStateException`, JMX typically uses `RuntimeMBeanException`:

\`\`\`java
import javax.management.RuntimeMBeanException;

try {
    server.invoke(name, "resize",
        new Object[] { Integer.valueOf(-2) },
        new String[] { "int" });
} catch (RuntimeMBeanException ex) {
    RuntimeException cause = ex.getTargetException();
    System.err.println("Runtime error inside MBean: " + cause);
}
\`\`\`

An implementation or exporter may map errors differently; when catching errors, do not rely on a single wrapper while ignoring the cause chain.

### 5.1. Viewing All Three Error Groups from the Same Operation

Using `resize(int)` to distinguish:

| Scenario | Example | Failing Step |
|---|---|---|
| Wrong name | Calling `"reszie"` | Operation lookup |
| Wrong type/signature | Calling `"resize"` with signature `"java.lang.String"` | Operation contract matching |
| Logic rejects value | Calling `resize(1000)` with valid signature `"int"` | Running setter/validation |
| Resource error during execution | Calling `refresh()` with valid contract but backend unreachable | Business execution |

For the third group, fixing the name and signature will not solve the error; check logs, preconditions, system state, and the root cause reported by the MBean.

### 5.2. Operations May Have Produced Side Effects Before Failing

An execution error occurs **after code has already started running**, so you must not assume the system remained unchanged. For example, an operation does:

\`\`\`text
1. Clear old cache
2. Load new configuration from external service
3. External service times out
4. Operation throws exception
\`\`\`

When the client receives the error, the cache was already cleared at step 1. Blindly retrying may increase load or make state harder to recover. Document idempotency, retry conditions, how to observe final state, and any rollback or compensation mechanisms.

Especially with remote JMX, a connection error or timeout does not tell you for sure whether the call was received and executed by the server. Verify the actual state before resending an operation with side effects.

## 6. Distinguishing Errors via Metadata API and Exceptions

Before calling, `MBeanInfo` can be used to eliminate many name/signature errors:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo metadata = server.getMBeanInfo(name);

for (MBeanOperationInfo operation : metadata.getOperations()) {
    System.out.print(operation.getName() + " signature=[");
    for (MBeanParameterInfo param : operation.getSignature()) {
        System.out.print(param.getType() + " ");
    }
    System.out.println("]");
}
\`\`\`

Example invoking an operation with specific exception branching:

\`\`\`java
import javax.management.InstanceNotFoundException;
import javax.management.MBeanException;
import javax.management.ReflectionException;
import javax.management.RuntimeMBeanException;

try {
    server.invoke(
        name,
        "resize",
        new Object[] { Integer.valueOf(12) },
        new String[] { "int" }
    );
    System.out.println("Invoke succeeded");
} catch (InstanceNotFoundException ex) {
    System.err.println("Wrong or missing ObjectName: " + name);
} catch (ReflectionException ex) {
    System.err.println(
        "Could not resolve/invoke method: " + ex.getCause()
    );
} catch (MBeanException ex) {
    System.err.println(
        "Checked exception in MBean: " + ex.getTargetException()
    );
} catch (RuntimeMBeanException ex) {
    System.err.println(
        "Runtime exception in MBean: " + ex.getTargetException()
    );
}
\`\`\`

The snippet above illustrates common Java JMX exceptions. In real code, handle other cases according to the API contract and specific `MBeanServerConnection` type, such as `IOException` for remote connections; check the exception declarations of the methods in use.

A diagnostic approach that does not depend too heavily on a specific wrapper:

\`\`\`java
static void printCauseChain(Throwable error) {
    int depth = 0;
    for (Throwable current = error;
         current != null && depth < 12;
         current = current.getCause(), depth++) {
        System.err.println(
            depth + ": " + current.getClass().getName()
                + ": " + current.getMessage()
        );
    }
}
\`\`\`

For JMX wrapper classes with `getTargetException()`, inspect the target exception explicitly; depending on the version and implementation, it may also appear in the cause chain.

### Decision Flow

\`\`\`text
Call failed
  |
  +-- ObjectName cannot be parsed?
  |      -> Fix ObjectName syntax
  |
  +-- InstanceNotFoundException?
  |      -> Verify registration and ObjectName
  |
  +-- AttributeNotFoundException?
  |      -> Check attribute name + read/write permissions
  |
  +-- InvalidAttributeValueException?
  |      -> Check type and value passed when setting
  |
  +-- ReflectionException / operation not found?
  |      -> Check name, parameter count, signature, and implementation
  |
  +-- MBeanException / RuntimeMBeanException?
  |      -> Check target exception, business logs, post-state
  |
  +-- IOException / remote timeout?
  |      -> Check transport; do not assume operation has not run
  |
  +-- Other error?
         -> Inspect full stack trace, cause chain, metadata, adapter
\`\`\`

The diagram suggests an investigation priority; in some cases a wrapper wraps another error, and the inspection order should follow the actual stack trace.

## 7. Mapping Errors by MBeanServer Operation

| API | Example Name Error | Example Type/Contract Error | Example Execution Error |
|---|---|---|---|
| `getAttribute` | Missing MBean; wrong attribute name; attribute not readable | Usually no value parameter; client casting result to wrong type can cause client-side `ClassCastException` | Getter throws exception |
| `setAttribute` | Missing MBean; wrong attribute name; attribute not writable | Passed value has wrong type or is rejected | Setter throws exception while processing |
| `invoke` | Missing MBean; wrong operation name | Wrong parameter count, signature, or invalid param value | Operation throws checked/unchecked exception or backend task fails |

A detail to note for **reading attributes**: `getAttribute` returns `Object`; the client can cause a `ClassCastException` itself if it assumes the result is `Integer` when it is actually `Long`. This is a **client-side decoding/casting error**, not necessarily MBeanServer reporting `InvalidAttributeValueException`.

\`\`\`java
Object value = server.getAttribute(name, "ProcessedCount");

// Wrong: this attribute has type long -> usually returns Long
// Integer processed = (Integer) value;

// Right according to the illustrative contract:
Long processed = (Long) value;
\`\`\`

For operations returning a value, the client must also use the return type declared in `MBeanOperationInfo.getReturnType()` to convert safely.

## 8. Special Cases When Using Spring Framework JMX

Spring can export beans using `MBeanExporter` and annotations:

\`\`\`java
@ManagedResource(
    objectName = "com.example.app:type=WorkerControl,name=main"
)
public class WorkerControlFacade {
    @ManagedAttribute
    public int getMaxThreads() { /* ... */ return 8; }

    @ManagedAttribute
    public void setMaxThreads(int value) { /* ... */ }

    @ManagedOperation
    public void resize(int value) { /* ... */ }
}
\`\`\`

The code above outlines how metadata is published, not a complete implementation class.

When troubleshooting JMX errors in Spring, determine where the failure occurs:

1. **Startup/export:** duplicate ObjectName, non-compliant MBean, server not found, misconfigured exporter. Error occurs before any client call.
2. **Client looking up the wrong name:** name produced by naming strategy or annotation export differs from the client's assumption. Inspect registered MBeans and metadata.
3. **Difference between Java methods and JMX interface:** not every public method of a Spring bean is exported; only members published by the MBean contract/assembler can be called via JMX.
4. **Adapter wrapper:** business errors may pass through a ModelMBean or Spring exporter; inspect target/cause and Spring logs instead of forcing every exception into a single type.
5. **Proxy:** if the bean is AOP-proxied or uses different exporter configurations, metadata and method dispatch may differ from expectations. Read metadata of the actually exported MBean.

Do not fix a failing operation by arbitrarily changing exception mapping. The goal is to preserve the root cause, provide diagnostic messages, and handle the issue at the actual source of failure.

## 9. Observability, Logging, and Production Handling

A useful error message should record:

- **Timestamp and correlation/request ID** if supported by the environment.
- **MBean ObjectName** and the MBeanServer/endpoint in use.
- **Operation:** `READ_ATTRIBUTE`, `WRITE_ATTRIBUTE`, or `INVOKE_OPERATION`.
- **Attribute/operation name**, declared signature, and passed value types.
- **Exception type**, message, cause chain; for JMX wrappers, also the target exception.
- **Post-error state** if safe to read, to avoid retries causing side effects.

Do not log tokens, passwords, JMX credentials, or sensitive data. For sensitive configuration values, log the type and field name instead of the raw value.

An illustrative log structure:

\`\`\`text
event=jmx.invoke.failed
objectName=com.example.app:type=WorkerControl,name=main
operation=resize
signature=[int]
exception=javax.management.RuntimeMBeanException
rootCause=java.lang.IllegalArgumentException
message="maxThreads must be in range 1..64"
\`\`\`

For remote connections, distinguish **JMX dispatch errors** from **transport/authentication errors**:

- Wrong credentials or missing permissions can block connection or operations depending on configuration.
- RMI/network timeouts can prevent the client from receiving a response even though the operation already started.
- Remote clients need a mechanism to check post-state via attributes/metrics or operation status before retrying.
- Do not expose remote JMX publicly without appropriate authentication, authorization, and transport protection.

## 10. Diagnostic Practice Exercises

Given the example MBean with `MaxThreads`, `ProcessedCount`, `resize(int)`, and `pause()`. Identify the failing step and how to fix it.

**Exercise 1 — Non-existent ObjectName**

\`\`\`java
server.invoke(
    new ObjectName("com.example.app:type=WorkerControl,name=backup"),
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

*Analysis:* The ObjectName is syntactically valid, but if no MBean with `name=backup` is registered, the error falls into the identification group, typically `InstanceNotFoundException`. Use `queryNames` or `isRegistered` to obtain the right name; do not change the `pause` operation.

**Exercise 2 — Wrong Attribute Name**

\`\`\`java
server.getAttribute(name, "MaxThread");
\`\`\`

*Analysis:* `MaxThread` differs from `MaxThreads`; expect `AttributeNotFoundException`. Obtain the attribute list from `getMBeanInfo`.

**Exercise 3 — Writing Attribute with Wrong Type**

\`\`\`java
server.setAttribute(name, new Attribute("MaxThreads", "12"));
\`\`\`

*Analysis:* `String` does not match type `int`; inspect `MBeanAttributeInfo.getType()` and pass `Integer.valueOf(12)`.

**Exercise 4 — Operation with Wrong Signature**

\`\`\`java
server.invoke(
    name, "resize",
    new Object[] { 12 },
    new String[] { "java.lang.Integer" }
);
\`\`\`

*Analysis:* `resize(int)` requires signature `"int"`, not `"java.lang.Integer"`. This is a dispatch/contract error, not proof that the business method ran.

**Exercise 5 — Valid Parameter Type but Out-of-Range Value**

\`\`\`java
server.invoke(
    name, "resize",
    new Object[] { 200 },
    new String[] { "int" }
);
\`\`\`

*Analysis:* Name and signature are valid; `WorkerControl.resize` enters validation and throws `IllegalArgumentException`. Check `RuntimeMBeanException.getTargetException()` when wrapped as a Standard MBean.

**Exercise 6 — Client Wrong Cast After Reading**

\`\`\`java
Integer count =
    (Integer) server.getAttribute(name, "ProcessedCount");
\`\`\`

*Analysis:* `ProcessedCount` has type `long`, so the result is normally `Long`. This is a Java client-side `ClassCastException` after JMX read succeeded.

**Exercise 7 — Operation Started but Connection Timed Out**

Client calls `refreshCache()`, then loses connection before receiving a response.

*Analysis:* You cannot conclude the operation did not run. Read post-state or metrics/job status using a new connection and determine whether the operation can be safely retried.

## 11. Pre-Fix Diagnostic Checklist

1. Record the exact call: `ObjectName`, method (`getAttribute`, `setAttribute`, or `invoke`), member name, parameters, and signature.
2. Confirm the ObjectName parses properly and the MBean is registered.
3. Read `MBeanInfo` to compare names, read/write flags, types, and signatures.
4. If the contract matches, inspect the full exception with target/cause and business logs.
5. For errors inside an operation, check whether the system changed state before the exception occurred.
6. For remote timeouts, verify state before retrying.
7. After fixing the root cause, re-run the JMX call with valid data and observe the actual result; do not just check that no exception was thrown.

## 12. Mental Model Summary

**Name error**: failed to locate the MBean or published member. Verify `ObjectName`, registration, and names in `MBeanInfo`.

**Type/contract error**: the member exists, but the value, parameter count, signature, or access permission does not match. Compare exact types, `isReadable/isWritable`, and `MBeanOperationInfo.getSignature()`.

**Execution error**: reached the MBean code, but the setter/getter/operation did not complete due to validation, state, or resources. Inspect the target exception, business logs, and post-state; consider side effects before calling again.

Good diagnosis means identifying **at which step the call failed**. The exception is a signal to narrow down the scope; metadata together with the cause chain and runtime state complete the conclusion.