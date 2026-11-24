# Unable to Invoke JMX Operation Due to Wrong Signature or Parameter Types in Spring Framework

## 1. Context and Objectives

An MBean has been successfully registered and JConsole displays the operation, yet a Java client calling `MBeanServerConnection.invoke(...)` encounters `ReflectionException`, `IllegalArgumentException`, a type conversion error, or an "operation not found" message. This is a common issue when Spring Framework exports managed beans via JMX and the client passes **the wrong operation name, the wrong parameter type signature, or incompatible values**.

A seemingly reasonable but wrong example:

```java
connection.invoke(
    objectName,
    "setLimit",
    new Object[]{10},
    new String[]{"java.lang.Integer"});
```

If the actual operation takes a Java primitive `int` parameter, JMX metadata may record the signature as `"int"`, not `"java.lang.Integer"`. Those two types are related via autoboxing in Java source code, but **they are not the same type name in a JMX signature**.

This lesson helps you:

1. Understand the structure of `invoke(ObjectName, String, Object[], String[])`.
2. Distinguish operation names from attribute getters/setters.
3. Read `MBeanInfo`, `MBeanOperationInfo`, and `MBeanParameterInfo` to retrieve the real signature.
4. Spot mismatches in primitives, wrappers, arrays, enums, overloads, and `null`.
5. Understand the impact of Spring annotations, exporters, and proxies.
6. Distinguish dispatch failures before method execution from exceptions thrown by the business method.
7. Write client helpers, integration tests, and a safe diagnostic workflow.

## 2. How Does JMX Identify an Operation?

With the API:

```java
Object result = connection.invoke(
    objectName,
    operationName,
    params,
    signature);
```

the meaningful components are:

| Component | Example | Role |
|---|---|---|
| `objectName` | `training.spring:type=Queue,name=Orders` | Selects the registered MBean |
| `operationName` | `"resetForQueue"` | Selects the operation name |
| `params` | `new Object[]{"orders"}` | Actual argument values |
| `signature` | `new String[]{"java.lang.String"}` | Java type names of each argument |
| Return value | `Object` | Operation result or JMX/Open Type conversion |

Required relationship:

```text
params.length == signature.length
```

Each position `signature[i]` describes the type of `params[i]` according to the exposed method. Do not mechanically let the type name in the signature reflect the runtime class of the argument: a method accepting `long` can receive a boxed Java `Long` value, yet the signature still requires `"long"`.

### 2.1. Dispatch Flow

```text
JMX client
   |
   v
invoke(objectName, operationName, params, signature)
   |
   +-- Does MBean exist?
   |
   +-- Is operation in MBeanInfo?
   |
   +-- Do name and signature match?
   |
   +-- Are argument types valid?
   |
   v
MBean implementation / Spring adapter
   |
   v
Business method
```

If the name or signature is wrong, the call typically fails **before the method executes**. This differs from a business method being invoked and intentionally throwing an exception.

## 3. The Primitive and Wrapper Problem

One of the most frequent mistakes is confusing `int` with `Integer`, or `boolean` with `Boolean`.

| Method declaration | Common JMX signature |
|---|---|
| `reset(int count)` | `"int"` |
| `reset(Integer count)` | `"java.lang.Integer"` |
| `setEnabled(boolean value)` if exposed as operation | `"boolean"` |
| `setEnabled(Boolean value)` if exposed as operation | `"java.lang.Boolean"` |
| `sample(long duration)` | `"long"` |
| `sample(Long duration)` | `"java.lang.Long"` |
| `notify(String text)` | `"java.lang.String"` |
| `configure(double ratio)` | `"double"` |

Correct example for method `reset(int)`:

```java
connection.invoke(
    name,
    "reset",
    new Object[]{Integer.valueOf(10)},
    new String[]{"int"});
```

The `params` array holds a boxed value because `Object[]` cannot hold primitives directly, whereas `signature` describes the method declaration.

Wrong example when the method declares `reset(int)`:

```java
connection.invoke(
    name,
    "reset",
    new Object[]{10},
    new String[]{Integer.class.getName()});
```

`Integer.class.getName()` returns `"java.lang.Integer"`, which does not match the `int` declaration when the JMX dispatcher requires an exact signature.

### 3.1. Why Doesn't Autoboxing Save You?

When calling a Java method in source code, the compiler can perform boxing/unboxing and select the matching overload. However, `MBeanServerConnection.invoke` is not a compiler-resolved Java source-level call. JMX receives **an array of type names** and uses corresponding metadata/dispatch. Do not assume "Java converts it automatically so JMX must work too."

## 4. Retrieving the Exact Signature via MBeanInfo

This is the most important diagnostic technique: **read the runtime contract before modifying client code**.

```java
import javax.management.*;
import java.util.Arrays;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    String argsText = Arrays.stream(op.getSignature())
        .map(p -> p.getType() + " " + p.getName())
        .reduce((a, b) -> a + ", " + b)
        .orElse("");

    System.out.print(argsText);
    System.out.println(") -> " + op.getReturnType());
}
```

Illustrative example output:

```text
reset(int p1) -> void
rename(java.lang.String p1) -> void
updateThreshold(long p1, boolean p2) -> void
rebuildIndex() -> java.lang.String
```

What you can rely on is `MBeanOperationInfo.getSignature()[i].getType()`. Parameter names like `p1` are only metadata, may vary by assembler, and do not have to match the parameter name in Java source code.

### 4.1. Helper to Build the Signature

```java
static String[] signature(MBeanOperationInfo op) {
    return Arrays.stream(op.getSignature())
        .map(MBeanParameterInfo::getType)
        .toArray(String[]::new);
}
```

Once the right operation is selected, this helper prevents guessing primitives vs. wrappers.

However, the client must still select the **right overload** before using that signature; matching only the operation name is insufficient when multiple methods share the same name.

## 5. Operation Overloads: Same Name, Multiple Signatures

A Java class may declare:

```java
public void reset(int count) { ... }
public void reset(String category) { ... }
```

If both are exposed via JMX, the metadata may contain:

```text
reset(int)
reset(java.lang.String)
```

The client must pass the signature of the desired overload:

```java
connection.invoke(
    name,
    "reset",
    new Object[]{10},
    new String[]{"int"});

connection.invoke(
    name,
    "reset",
    new Object[]{"orders"},
    new String[]{"java.lang.String"});
```

If you pass `new String[0]` for an operation taking parameters, JMX will not infer the signature from `params`.

### 5.1. Overloads and Spring Annotations

A Spring bean may annotate two methods:

```java
@ManagedOperation
public void refresh(String cacheName) { ... }

@ManagedOperation
public void refresh(String cacheName, boolean force) { ... }
```

Even with the same name, they have distinct signatures. When using Spring `MBeanExporter` with an annotation assembler, verify that both appear in `MBeanInfo` instead of making assumptions from source code.

### 5.2. Avoiding Overly Complex Overloads in Management APIs

If an operation has many similar overloads, tooling and operators can easily choose the wrong one. A clear management API can use distinct names:

```java
refreshCache(String cacheName)
refreshCacheForcefully(String cacheName)
```

This reduces reliance on overload metadata, especially for client scripts or dashboards.

## 6. Attribute Setters Are Not Operations

This is an easily overlooked mistake: a Java method named `setEnabled(boolean)` is typically interpreted by JMX as **the setter of attribute `Enabled`**, not as an operation named `setEnabled`.

With a Standard MBean:

```java
public interface ServiceControlMBean {
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
```

Metadata usually contains:

```text
Attribute: Enabled
  readable=true
  writable=true
  type=boolean
```

Yet `setEnabled` is not necessarily present in `MBeanInfo.getOperations()`.

The right way:

```java
connection.setAttribute(
    name,
    new Attribute("Enabled", Boolean.TRUE));
```

Instead of:

```java
connection.invoke(
    name,
    "setEnabled",
    new Object[]{true},
    new String[]{"boolean"});
```

A Spring annotation-based MBean might expose a setter as an operation if metadata is intentionally configured that way, but you must confirm from `MBeanInfo` rather than assuming based on Java method names.

### 6.1. Getters Work the Same Way

`getCount()` may be exposed as attribute `Count`. Clients should use:

```java
Object count = connection.getAttribute(name, "Count");
```

rather than automatically treating `getCount` as an operation to `invoke`.

## 7. Wrong Parameter Count or Order

Suppose an operation declares:

```java
@ManagedOperation
public void updateThreshold(long millis, boolean enabled) { ... }
```

Correct:

```java
connection.invoke(
    name,
    "updateThreshold",
    new Object[]{1500L, true},
    new String[]{"long", "boolean"});
```

Wrong count:

```java
new Object[]{1500L};
new String[]{"long", "boolean"};
```

Wrong order:

```java
new Object[]{true, 1500L};
new String[]{"boolean", "long"};
```

Wrong type:

```java
new Object[]{"1500", true};
new String[]{"java.lang.String", "boolean"};
```

JMX does not parse the string `"1500"` into a `long` by default. A UI like JConsole may allow text entry and convert it based on metadata, but the Java `invoke` API must not rely on such conversion.

## 8. Arrays, Varargs, and Class Names

Arrays in Java reflection have names different from source-code syntax.

```java
public void replaceTags(String[] tags) { ... }
```

Appropriate signature using Java reflection naming:

```java
String[] signature = {
    String[].class.getName()
};
```

`String[].class.getName()` returns `"[Ljava.lang.String;"`.

For a primitive array:

```java
int[].class.getName(); // "[I"
```

Client:

```java
connection.invoke(
    name,
    "replaceTags",
    new Object[]{new String[]{"urgent", "review"}},
    new String[]{String[].class.getName()});
```

Do not write `"java.lang.String[]"` out of habit if MBeanInfo reports a different JVM reflection descriptor name. **Always read the actual type from metadata**.

### 8.1. Varargs

Method:

```java
public void addTags(String... tags) { ... }
```

takes a `String[]` in bytecode, so the signature is fundamentally an array type. JMX does not automatically accept multiple loose values like Java varargs syntax; you must pass a single element in `Object[]` that is the `String[]` itself.

## 9. Null Arguments and Overloads

`null` poses a challenge because there is no runtime class from which to infer the type:

```java
connection.invoke(
    name,
    "rename",
    new Object[]{null},
    new String[]{String.class.getName()});
```

If the method accepts a nullable `String`, the signature is still declared as `java.lang.String`. However, if there are multiple overloads `rename(String)` and `rename(CharSequence)`, the `null` value alone is insufficient to select the right method; the client must specify the signature.

Do not pass `null` for primitive `int`, `long`, or `boolean` if the method has no mechanism to accept it. The dispatch/adapter may throw a reflection or argument type error depending on the implementation.

## 10. Enums and Complex Data Types

Method:

```java
public void changeMode(Mode mode) { ... }
```

with enum:

```java
enum Mode { NORMAL, MAINTENANCE }
```

A local client can pass an enum instance of the exact class if the Standard MBean interface allows that type:

```java
connection.invoke(
    name,
    "changeMode",
    new Object[]{Mode.MAINTENANCE},
    new String[]{Mode.class.getName()});
```

With remote JMX, however, custom types require serialization support and classpath compatibility. MXBeans have a mechanism to convert types into Open Types; for example, an enum may be represented as a `String` at the Open Data layer, though how it maps across an MXBean proxy and metadata must be verified. Do not assume all custom types are safe or portable over JMX/RMI.

### 10.1. DTOs and MXBeans

When an operation takes complex structures, `CompositeData`, `TabularData`, or MXBean mapping may be needed. If metadata advertises an Open Type, a client passing a raw Java DTO to `invoke` may fail to match.

Solutions:

1. Inspect `MBeanInfo` and Open MBean metadata if present.
2. Check whether it is a Standard MBean, MXBean, or DynamicMBean.
3. Use an MXBean client proxy and appropriate mapping when possible.
4. Avoid sending arbitrary Java domain objects over remote JMX without a clear serialization contract.

## 11. Spring MBeanExporter and Metadata Can Differ from Java Source

Spring can export beans via:

- A Standard MBean interface.
- `@ManagedResource`, `@ManagedOperation`, `@ManagedAttribute`.
- `MBeanExporter` with a custom `MBeanInfoAssembler`.
- A DynamicMBean or framework-managed adapter.

Annotation example:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "training.spring:type=Queue,name=Orders")
public class QueueMaintenance {

    @ManagedOperation
    public void rebalance(String queue, int batchSize) {
        // Controlled maintenance operation.
    }
}
```

The MBean must be exported via `@EnableMBeanExport` or an `MBeanExporter` configured with suitable annotation metadata. JMX metadata typically shows:

```text
rebalance(java.lang.String, int)
```

Client:

```java
connection.invoke(
    name,
    "rebalance",
    new Object[]{"orders", 100},
    new String[]{"java.lang.String", "int"});
```

If the exporter does not expose the method or an AOP proxy alters method visibility, the problem is not the `batchSize` value, but that **the operation does not exist in MBeanInfo**. Always check registration and metadata first.

## 12. AOP Proxies and Methods Not on an Interface

Spring AOP with JDK dynamic proxies may expose only interface methods. A method carrying `@ManagedOperation` on the implementation class that is absent from the interface used by the exporter can be omitted from JMX metadata, depending on how the exporter/assembler handles the target class and proxy.

Diagnostics:

```java
Object bean = context.getBean("queueMaintenance");

System.out.println(
    org.springframework.aop.support.AopUtils.isAopProxy(bean));

System.out.println(
    org.springframework.aop.support.AopUtils
        .getTargetClass(bean).getName());
```

Then read `MBeanInfo`. If the method is completely missing, changing the signature in the JMX client will not help. Fix exposure/the management interface or use a dedicated management facade.

Do not disable transaction or security advice just to make the method appear; preserve operational contracts and business semantics.

## 13. Distinguishing ReflectionException from MBeanException

| Exception | Typical Context | Diagnosis |
|---|---|---|
| `InstanceNotFoundException` | ObjectName not registered in server | Query MBeans/server/lifecycle |
| `ReflectionException` | Operation/signature not found or reflection failure | Inspect `MBeanInfo.getOperations()` |
| `MBeanException` | Checked exception thrown in managed method/adapter | Inspect `getTargetException()` |
| `RuntimeMBeanException` | Runtime exception in MBean path | Inspect `getTargetException()` |
| `InvalidAttributeValueException` | Writing attribute with invalid value | Check setter/type/range |
| `AttributeNotFoundException` | Attribute does not exist or is not writable/readable | Inspect `MBeanAttributeInfo` |
| `IOException` | Remote transport/connector failure | Check network, operation state |
| `SecurityException` | Insufficient permissions | Check policy, do not bypass |

The actual error may be wrapped differently by a Spring adapter/proxy. `ReflectionException` usually indicates a metadata/dispatch issue, yet you should not definitively claim the business method never ran without checking the cause and stack trace in the specific implementation.

### 13.1. Reading the Cause

```java
try {
    connection.invoke(
        name, "rebalance",
        new Object[]{"orders", 100},
        new String[]{"java.lang.String", "int"});

} catch (ReflectionException ex) {
    System.err.println(
        "Dispatch/reflection failed: " +
        ex.getTargetException());

} catch (MBeanException ex) {
    System.err.println(
        "MBean operation failed: " +
        ex.getTargetException());

} catch (RuntimeMBeanException ex) {
    System.err.println(
        "Runtime failure: " +
        ex.getTargetException());
}
```

This is an error-classification example; production code should not merely log to `System.err` and continue as if the operation succeeded. Return a clear error status, log safely, and avoid exposing sensitive data.

## 14. JConsole and GUI Tools Can Mask Type Conversions

In JConsole, the **MBeans → Operations** tab displays operation names and parameters. When a user types digits `100`, the tool can convert the text input into an `Integer` matching the `int` signature.

Therefore:

- JConsole succeeding does not prove a Java client is sending the right signature.
- A Java client can fail because it automatically uses `args[i].getClass().getName()`.
- GUIs may limit the kinds of parameters supported.
- GUI error messages differ across JDK/tool versions.
- Runtime metadata is more reliable than guessing from UI labels.

If the same operation runs in JConsole yet fails in a Java client, log **the operation name, the actually sent signature, and the signature from MBeanInfo** (without logging secrets inside values).

## 15. Client Helper: Selecting an Operation by Expected Signature

A simple helper to verify an operation exists:

```java
import javax.management.*;
import java.util.Arrays;

public final class OperationContract {

    public static boolean hasOperation(
            MBeanServerConnection connection,
            ObjectName name,
            String operation,
            String... signature) throws Exception {

        MBeanInfo info = connection.getMBeanInfo(name);

        return Arrays.stream(info.getOperations())
            .anyMatch(op ->
                op.getName().equals(operation) &&
                Arrays.equals(
                    Arrays.stream(op.getSignature())
                        .map(MBeanParameterInfo::getType)
                        .toArray(String[]::new),
                    signature));
    }
}
```

Usage:

```java
if (!OperationContract.hasOperation(
        connection, name, "rebalance",
        "java.lang.String", "int")) {
    throw new IllegalStateException(
        "Expected JMX operation signature is missing");
}

connection.invoke(
    name, "rebalance",
    new Object[]{"orders", 100},
    new String[]{"java.lang.String", "int"});
```

This helper does not perform type conversion and does not solve permissions, MBean unregistration between lookup and invocation (TOCTOU), remote transport issues, or business exceptions. It helps detect mismatches early and surface meaningful messages.

### 15.1. Do Not Automatically Invoke the First Overload

An anti-pattern:

```java
MBeanOperationInfo operation =
    Arrays.stream(info.getOperations())
        .filter(op -> op.getName().equals("refresh"))
        .findFirst()
        .orElseThrow();
```

If multiple overloads exist, the first element is not necessarily the intended overload. Specify the full signature or design the management API to avoid ambiguous overloads.

## 16. Integration Testing with an Isolated MBeanServer

An example using a Standard MBean to demonstrate signature errors without depending on annotation scanning.

### 16.1. Management Interface

```java
public interface QueueControlMBean {
    int getCapacity();
    void rebalance(String queue, int batchSize);
}
```

Implementation:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class QueueControl implements QueueControlMBean {
    private final AtomicInteger calls = new AtomicInteger();

    @Override
    public int getCapacity() {
        return 500;
    }

    @Override
    public void rebalance(String queue, int batchSize) {
        calls.incrementAndGet();
    }

    public int internalCallCount() {
        return calls.get();
    }
}
```

### 16.2. Testing Wrong vs. Right Signatures

```java
import org.junit.jupiter.api.Test;
import javax.management.*;
import static org.junit.jupiter.api.Assertions.*;

class OperationSignatureTest {

    @Test
    void wrongSignatureFailsBeforeMethodInvocation()
            throws Exception {

        MBeanServer server =
            MBeanServerFactory.newMBeanServer("test");

        QueueControl target = new QueueControl();

        ObjectName name = new ObjectName(
            "training.test:type=QueueControl,name=Orders");

        server.registerMBean(target, name);

        assertThrows(
            ReflectionException.class,
            () -> server.invoke(
                name, "rebalance",
                new Object[]{"orders", 10},
                new String[]{
                    "java.lang.String",
                    "java.lang.Integer"}));

        assertEquals(0, target.internalCallCount());

        server.invoke(
            name, "rebalance",
            new Object[]{"orders", 10},
            new String[]{"java.lang.String", "int"});

        assertEquals(1, target.internalCallCount());
    }
}
```

In a specific JVM/JMX implementation, a wrong signature typically raises `ReflectionException`. If a framework adapter reports a different exception, inspect the cause and MBeanInfo, then pin the test to the active implementation's contract.

### 16.3. Testing Operation Metadata

```java
MBeanInfo info = server.getMBeanInfo(name);

MBeanOperationInfo rebalance =
    java.util.Arrays.stream(info.getOperations())
        .filter(op -> op.getName().equals("rebalance"))
        .findFirst()
        .orElseThrow();

String[] actual = java.util.Arrays.stream(
        rebalance.getSignature())
    .map(MBeanParameterInfo::getType)
    .toArray(String[]::new);

assertArrayEquals(
    new String[]{"java.lang.String", "int"},
    actual);
```

This is a useful regression test in case a method declaration change or Spring metadata assembler change breaks client scripts.

## 17. Recommended Negative Tests

| Case | Expectation |
|---|---|
| Wrong ObjectName | `InstanceNotFoundException` |
| Wrong operation name | Dispatch/reflection error |
| Wrong parameter count | Pre-method invocation error |
| `int` vs `Integer` | Signature mismatch |
| Swapped argument order | Mismatch or argument type failure |
| `null` for primitive | Type error on invocation |
| Wrong array signature | Operation not found |
| Setter exposed as attribute | Use `setAttribute` instead of `invoke` |
| Business method throws exception | Appropriate JMX wrapper/target cause |
| MBean unregistered between lookup/call | Lookup/lifecycle error |

No need to test using destructive actions on real data. Use a test MBean with counters or in-memory state.

## 18. Production Diagnostic Procedure

When a Java client reports "operation not found":

**Step 1 — Confirm the right MBeanServer.** A remote connection may reach a different JVM or the exporter may register to a custom server.

**Step 2 — Check ObjectName.**

```java
boolean exists = connection.isRegistered(name);
```

**Step 3 — Print the operation metadata list.** Use `getMBeanInfo` and `getOperations`.

**Step 4 — Match name and signature position by position.** Pay special attention to primitives/wrappers, arrays, overloads, and ordering.

**Step 5 — Distinguish attributes from operations.** `setXxx` or `getXxx` may belong to attributes.

**Step 6 — Check values.** Count, nulls, boxed values, enums/complex types.

**Step 7 — Check Spring exporter/assembler/AOP.** If the operation is missing from metadata, the fault may not be on the client.

**Step 8 — Read the exception chain and server logs.** Distinguish dispatch failure from business exceptions.

**Step 9 — Test using an MBeanServer fixture.** Lock in a regression test against the runtime contract.

**Step 10 — Consider updating the management API.** If awkward overloads exist, design clearer operation names instead of continuing to rely on implicit conversions.

## 19. Anti-Patterns to Avoid

1. Building signatures with `args[i].getClass().getName()` for every argument.
2. Using `"Integer"` or `"String"` instead of fully qualified type names.
3. Passing a `String` for a number and expecting the server to parse it automatically.
4. Using `invoke` for every `getXxx`/`setXxx`.
5. Picking an overload by taking the first match from `getOperations`.
6. Ignoring `MBeanInfo` and guessing changes to arguments.
7. Enabling unprotected remote JMX for testing.
8. Automatically retrying side-effecting operations when a client hits a network timeout.
9. Logging all parameter values when they may contain secrets.
10. Changing business method signatures without checking the JMX client contract.

## 20. Hands-on Exercises

### Exercise A — Primitives and Wrappers

Create a `limit(int)` method and invoke it over JMX with signature `"java.lang.Integer"`, then fix it to `"int"`. Record the exception and verify the method only runs with the right signature.

### Exercise B — Setter or Operation?

Create a Standard MBean with `setEnabled(boolean)`, read `MBeanInfo`, and check whether `Enabled` appears in attributes. Try `invoke("setEnabled")` and then switch to `setAttribute`.

### Exercise C — Overloads

Create `refresh(String)` and `refresh(String, boolean)` and expose both. Write a client that reads metadata and selects the right overload by full signature.

### Exercise D — Arrays

Create `replaceTags(String[])`, print `String[].class.getName()`, invoke with an array inside `Object[]`, then try the wrong signature `"java.lang.String[]"` to observe the difference.

### Exercise E — Annotations and Proxies

Create a Spring bean with `@ManagedOperation rebalance(String, int)`. Enable an AOP proxy and check whether `MBeanInfo` still contains the operation. Write a test protecting the signature against refactors.

### Exercise F — Remote Client

In a lab with a secured connector, invoke the operation from another JVM. Compare a signature error with a transport error by testing a wrong operation name and dropping the connection. Do not perform this in production.

## 21. Self-Check Questions

1. How do `params` and `signature` differ?
2. Why is `int` not equivalent to `java.lang.Integer` in a JMX signature?
3. Which classes of the JMX API read the actual signature?
4. Is a Java getter always a JMX operation?
5. When overloads exist, is knowing only the operation name sufficient?
6. What does `String[].class.getName()` return?
7. Why does `null` fail to determine an overload?
8. How do you distinguish a dispatch failure from a business method exception?
9. If `MBeanInfo` lacks the operation, will changing `params` help?
10. How can an AOP proxy affect exported metadata?
11. Why does JConsole succeeding not guarantee a Java client has the right signature?
12. Which test proves a method did not run when the signature is wrong?

## 22. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `@ManagedOperation`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — `MBeanOperationInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — `MBeanParameterInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanParameterInfo.html
- Java SE 21 — `ReflectionException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ReflectionException.html
- Java SE 21 — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html

**Key Takeaway:** When `invoke` fails to call an operation, retrieve the running MBean's `MBeanInfo` and compare **operation name, parameter count, order, and type names**. Do not infer signatures from the runtime classes of arguments. Distinguish attribute setters/getters from operations and separate dispatch errors from business errors.
