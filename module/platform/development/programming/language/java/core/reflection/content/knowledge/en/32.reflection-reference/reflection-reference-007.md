# Java Reflection Exception Reference Table and What to Inspect

## 1. Objective and Scope

When using Java Reflection to find classes, look up `Method`/`Field`/`Constructor`, read metadata, or execute methods, errors typically belong to **different stages**. If you see an exception name and randomly try to fix it with `setAccessible(true)`, change overloads, or catch every `Exception`, you can obscure the real root cause.

This article provides a practical reference table: **which API throws the error, common causes, what information to inspect first, and how to handle it appropriately**. Examples run on Java 17+.

Distinguish between:

- **Lookup errors:** target metadata could not be obtained yet (e.g., `ClassNotFoundException`, `NoSuchMethodException`).
- **Access or argument errors at call time:** metadata was found, but the call is invalid (`IllegalAccessException`, `IllegalArgumentException`, `NullPointerException`).
- **Errors inside the target method:** Java Reflection wraps a `Throwable` thrown by the target in `InvocationTargetException`; inspect `getCause()`.
- **Module, class initialization, or JVM linking errors:** can be runtime exceptions or `Error`s, **not necessarily** subclasses of `ReflectiveOperationException`.

Not every kind of `Throwable` should be "caught at all costs." The goal is to detect programming/configuration errors early, report data errors clearly, and avoid masking business exceptions.

## 2. Quick Lookup Table: Error → Location → What to Check

| Exception / Error | Where Commonly Encountered | What to Check First |
| --- | --- | --- |
| `ClassNotFoundException` (checked) | `Class.forName("...")`, `ClassLoader.loadClass` | Full binary name, classpath/module path, class loader used to load |
| `NoSuchMethodException` (checked) | `getMethod`, `getDeclaredMethod`, `getConstructor`, `getDeclaredConstructor` | Name, **exact parameter type sequence**, public/declared, inheritance, erased types |
| `NoSuchFieldException` (checked) | `getField`, `getDeclaredField` | Field name, public vs. declared distinction, class being queried |
| `IllegalAccessException` (checked) | `Method.invoke`, `Field.get/set`, `Constructor.newInstance` | Modifiers, declaring class, caller/module, Java and JPMS accessibility |
| `InaccessibleObjectException` (runtime) | `setAccessible(true)` when requesting to suppress access checks | Whether the package is `opens`ed to the caller module; whether non-public member access is actually needed |
| `SecurityException` (runtime) | Certain lookup/accessibility changes, permission-controlled environments | Reflection permissions and environment policy (if any), avoiding permission-bypass assumptions |
| `IllegalArgumentException` (runtime) | `invoke`/`set`/`newInstance` | Correct receiver type, argument count/order/types, primitive conversions, varargs |
| `NullPointerException` (runtime) | Calling an **instance** method on a `null` receiver, certain null operations | Missing receiver or missing value? Is the method static or instance? |
| `InvocationTargetException` (checked) | `Method.invoke`, `Constructor.newInstance` | `getCause()`; stack trace and message of the target exception, not just the wrapper |
| `InstantiationException` (checked) | `Constructor.newInstance` with an abstract class | Is the target abstract? Can the type be instantiated directly? |
| `ExceptionInInitializerError` (`Error`) | Static initialization of a class, possibly triggered during loading/invocation | Static initializer/static fields, **cause**, class initialization state |
| `LinkageError` (`Error`) | Loading/linking classes | Mismatched JAR/class versions, dependency conflicts, binary compatibility |
| `WrongMethodTypeException` (runtime) | `MethodHandle.invokeExact/invoke` | `handle.type()`, static type of each argument **and return type at the call site** |
| `UndeclaredThrowableException` (runtime) | JDK dynamic proxy propagating an undeclared checked exception | `getUndeclaredThrowable()`, `throws` contract on interface, handler logic |
| `StackOverflowError` (`Error`) | Proxy/reflective dispatch handler calling back into itself | Repeating frame chain, `method.invoke(proxy, args)`, logging `proxy.toString()` |

The table above summarizes **common scenarios**, rather than listing every throwable the APIs can throw. Some exceptions also have multiple other causes; always read the API documentation and the actual stack trace.

## 3. Looking Up Classes, Methods, Fields, and Constructors

### 3.1. ClassNotFoundException: Class Not Found

```java
Class<?> type = Class.forName("com.example.Tool");
```

When getting `ClassNotFoundException`, check:

1. Is the name in the right **binary name** format (`com.example.Tool`)? For nested classes, binary names usually contain `$` (e.g., `Outer$Inner`).
2. Is the class actually present in the built artifact and current classpath/module path?
3. Which **class loader** is being asked to load the class? The same name across different class loaders can represent different runtime classes.
4. With JPMS, has the module containing the class been resolved into the module graph? Do not automatically conclude `ClassNotFoundException` always means "forgot a JAR."

`Class.forName(String)` also triggers class initialization according to this overload's semantics; errors in static initializers can throw `ExceptionInInitializerError`, while linking errors can throw `LinkageError`. They are **not** `ClassNotFoundException`. When you need to look up a class without intentionally initializing it, there is an overload:

```java
// Code snippet in a context with ClassLoader loader:
Class<?> type = Class.forName("com.example.Tool", false, loader);
```

The `false` argument requests not initializing the class at this step; subsequent operations can still trigger initialization.

### 3.2. NoSuchMethodException: Wrong Name or Signature

```java
Method m = Service.class.getMethod("save", int.class, String.class);
```

`getMethod` searches for **public** methods, including inherited public methods. `getDeclaredMethod` searches for methods **declared directly in the class itself**, including private ones, but does not automatically search inherited methods. The parameter type sequence must match exactly after erasure; `int.class` differs from `Integer.class`, and `List.class` does not represent `List<String>` separately.

On error, record:

- The `declaring class`/queried class and `getName()`.
- Method name, **count, order, and `Class<?>` of each parameter**; not just the method name.
- Whether the lookup API used `getMethod` or `getDeclaredMethod`, and whether the method is inherited/non-public.
- Whether there are overloads or bridge/synthetic methods generated by generics/compilation.
- Return type **does not participate in `getMethod` parameters**; after resolving, check `method.getReturnType()` separately if the contract requires it.

Do not use `getMethods()[0]` or pick "the first method matching the name" to dodge `NoSuchMethodException`.

### 3.3. NoSuchFieldException: Wrong Lookup Scope

`getField("code")` searches for public fields, including inherited fields per Reflection rules. `getDeclaredField("code")` searches for fields declared directly on the class, including non-public ones; finding private metadata **does not automatically grant read/write access**.

Check the exact name, declaring class, whether the field is inherited or directly declared, modifiers, and whether the metadata class matches the runtime class you intend to manipulate. Fields have no parameters like `Method`, yet field type (`field.getType()`), static/instance, and `final` must be checked before `get/set`.

### 3.4. Constructor: Matching Arity Does Not Guarantee Instantiation

```java
Constructor<?> ctor = type.getDeclaredConstructor(String.class, int.class);
Object obj = ctor.newInstance("x", 3);
```

Lookup can throw `NoSuchMethodException`; invoking the constructor can throw `InstantiationException` (e.g., an abstract class), `IllegalAccessException`, `IllegalArgumentException`, and `InvocationTargetException` due to the constructor body throwing an exception. `ExceptionInInitializerError` can also occur if static initialization of the class fails.

Do not confuse `Class.newInstance()` with `Constructor.newInstance()`. `Class.newInstance()` is deprecated; `Constructor.newInstance` lets you distinguish target exceptions via `InvocationTargetException` more clearly.

## 4. Method Was Found, but `invoke` Fails

Suppose we have:

```java
Method m = Worker.class.getMethod("repeat", String.class, int.class);
Object out = m.invoke(new Worker(), "go", 2);
```

On failure, check in sequence:

| What to Check | API or Check Method | Why |
| --- | --- | --- |
| Was the right method resolved? | `m.getName()`, `m.getDeclaringClass()` | Avoid calling the wrong class/overload |
| Static or instance method? | `Modifier.isStatic(m.getModifiers())` | Static can take a `null` receiver; instance requires a valid receiver |
| Correct receiver type? | `m.getDeclaringClass().isInstance(target)` for instance | Wrong receiver can lead to `IllegalArgumentException` |
| Is receiver null? | `target == null` | Instance invoke on a null receiver throws `NullPointerException` |
| Arity and types? | `m.getParameterCount()`, `m.getParameterTypes()` | Wrong argument count/order/type usually causes `IllegalArgumentException` |
| Accessibility? | `m.getModifiers()`, `m.canAccess(target)` if valid | May hit `IllegalAccessException`; `canAccess` requires a suitable receiver for instance cases |
| Has varargs? | `m.isVarArgs()` | `Method.invoke` still expects an array argument in that slot; pack the target array |
| Expected return value? | `m.getReturnType()` | `void` returns `null` via `Method.invoke`, primitive results are boxed |
| Did target itself throw an error? | `InvocationTargetException.getCause()` | The real cause lies inside the target |

**Numeric conversions:** `Method.invoke` allows appropriate unboxing and **primitive widening**, but does not arbitrarily narrow and does not parse `"2"` into `int`. A tool receiving String input must apply an explicit converter **before invoking**.

**Varargs:** When the target method declares `String... items`, the final parameter at the Reflection level is `String[]`. `Method.invoke` is a varargs API, but that does not mean it automatically packs user arguments into the target's varargs in every shape. Build an `Object[]` whose final element is a properly typed `String[]`, pass the argument array intentionally, and test it.

**Access:** `getDeclaredMethod` finds private methods, yet `Method.invoke` can still throw `IllegalAccessException`. Check class/module boundaries and API design before deciding whether deep access is needed. `setAccessible(true)` is not a universal fix for every exception.

## 5. Errors Inside the Target: InvocationTargetException

This is the most important distinction in Reflection debugging:

```java
try {
    Object result = method.invoke(target, args);
    // Handle result.
} catch (InvocationTargetException ex) {
    Throwable original = ex.getCause();
    // Log/rethrow according to the application's policy.
    throw original;
}
```

This snippet is a **code fragment inside a method declaring `throws Throwable`**. When the target method actually executes and throws `IOException`, `IllegalStateException`, or even an `Error`, `Method.invoke` can wrap the `Throwable` from the target in `InvocationTargetException`. `ex.getCause()` (or `getTargetException()`) reveals the real error.

Distinguish:

- `IllegalArgumentException` **thrown directly by `Method.invoke`**: usually an invalid receiver/argument; the target may not have been executed yet.
- `InvocationTargetException` whose cause is `IllegalArgumentException`: **the target method itself** threw that error during its execution.
- `InvocationTargetException` whose cause is a checked exception: do not strip the cause or blindly classify it as a parser error.
- For logging, inspect **the cause's stack trace and message**; logging the wrapper alone can omit useful frames.

If there are multiple wrapper layers, you can inspect the `getCause()` chain, but do not automatically drop business boundaries, retry an action with side effects, or expose sensitive stack traces to callers.

## 6. Standalone Java 17+ Example: An Experimental Exception Table

Save the entire code below in `ReflectionExceptionDemo.java`. It triggers error cases that are **deliberate, catchable, and print stable labels**, without needing to trigger hard-to-control JPMS errors or `StackOverflowError`.

```java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ReflectionExceptionDemo {
    public static class Worker {
        public String repeat(String word, int times) {
            return word.repeat(times);
        }
        public void fail() throws IOException {
            throw new IOException("storage unavailable");
        }
    }

    public static abstract class AbstractJob {
        public AbstractJob() {}
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Worker.class;
        Method repeat = type.getMethod("repeat", String.class, int.class);
        System.out.println("method=" + repeat.getName());
        System.out.println("parameters=" + repeat.getParameterCount());
        System.out.println("return=" + repeat.getReturnType().getSimpleName());
        System.out.println("static=" + Modifier.isStatic(repeat.getModifiers()));
        System.out.println("success=" + repeat.invoke(new Worker(), "go", 2));

        try {
            type.getMethod("repeat", int.class, int.class);
        } catch (NoSuchMethodException ex) {
            System.out.println("lookup: " + ex.getClass().getSimpleName());
        }
        try {
            type.getField("missing");
        } catch (NoSuchFieldException ex) {
            System.out.println("field: " + ex.getClass().getSimpleName());
        }
        try {
            repeat.invoke(new Worker(), "go", "2");
        } catch (IllegalArgumentException ex) {
            System.out.println("arguments: " + ex.getClass().getSimpleName());
        }
        try {
            repeat.invoke(null, "go", 2);
        } catch (NullPointerException ex) {
            System.out.println("receiver: " + ex.getClass().getSimpleName());
        }
        try {
            Method hidden = ExternalHelper.class.getDeclaredMethod("secret");
            hidden.invoke(new ExternalHelper());
        } catch (IllegalAccessException ex) {
            System.out.println("access: " + ex.getClass().getSimpleName());
        }
        try {
            Method fail = type.getMethod("fail");
            fail.invoke(new Worker());
        } catch (InvocationTargetException ex) {
            System.out.println("target: " + ex.getCause().getClass().getSimpleName());
            System.out.println("message=" + ex.getCause().getMessage());
        }
        try {
            Constructor<AbstractJob> ctor = AbstractJob.class.getDeclaredConstructor();
            ctor.newInstance();
        } catch (InstantiationException ex) {
            System.out.println("construct: " + ex.getClass().getSimpleName());
        }
        try {
            Class.forName("missing.example.NotOnClasspath");
        } catch (ClassNotFoundException ex) {
            System.out.println("load: " + ex.getClass().getSimpleName());
        }
    }
}

class ExternalHelper {
    private String secret() {
        return "hidden";
    }
}
```

Compile and run:

```bash
javac ReflectionExceptionDemo.java
java ReflectionExceptionDemo
```

Stdout verified with JDK:

```text
method=repeat
parameters=2
return=String
static=false
success=gogo
lookup: NoSuchMethodException
field: NoSuchFieldException
arguments: IllegalArgumentException
receiver: NullPointerException
access: IllegalAccessException
target: IOException
message=storage unavailable
construct: InstantiationException
load: ClassNotFoundException
```

**Why is this example noteworthy?**

1. Looking up `repeat` with `(String,int)` succeeds, whereas looking up `(int,int)` throws `NoSuchMethodException` despite matching the name.
2. `getField("missing")` fails at the field lookup step, unrelated to the invocation step.
3. Passing `"2"` instead of `int` when calling `repeat` causes `IllegalArgumentException`; Reflection does not parse Strings into integers.
4. A `null` receiver for the instance method `repeat` causes `NullPointerException`; static methods have different receiver rules.
5. `ExternalHelper.secret` is a `private` method of **another top-level class**; `getDeclaredMethod` finds the metadata, yet code in `ReflectionExceptionDemo` is not allowed to invoke it without permission.
6. `Worker.fail()` actually executes and throws `IOException`; the Reflective API wraps it in `InvocationTargetException`, so the sample inspects `getCause()`.
7. `AbstractJob` is abstract; constructor lookup succeeds, yet `newInstance` cannot instantiate it, producing `InstantiationException`.
8. `Class.forName` with a nonexistent name throws `ClassNotFoundException`.

These are **intentional errors in the demo**. In real applications, classify and handle errors properly instead of letting callers trigger batches of errors and catching them afterward.

## 7. Diagnosing Access and JPMS Errors with the Right API

Once you have a `Method`, `Field`, or `Constructor` but the operation fails, separate **current access permission** from **requesting to bypass access checks**:

| Symptom | What to Clarify |
| --- | --- |
| `IllegalAccessException` at `invoke/get/set/newInstance` | Caller, declaring class, modifiers, runtime package/nest, and module; the member exists, but manipulation is not yet permitted |
| `member.canAccess(receiver) == false` | Current access check fails; use `null` for static members/constructors, while instance members require a properly typed receiver |
| `member.trySetAccessible() == false` | Cannot enable suppression across module boundaries; this method returns `false` when disallowed, instead of throwing `InaccessibleObjectException` |
| `InaccessibleObjectException` from `setAccessible(true)` | The package belongs to a named module not `opens`ed to the caller (or another granting condition is unmet) |
| `SecurityException` when changing access | Runtime policy denies the relevant permission, distinct from an `opens` error |

`exports` allows using public APIs under Java/JPMS rules; **deep reflection** to private members from another module typically requires `opens` for the exact package and caller. `getDeclaredMethod` only finds metadata and does not automatically allow invocation. For example, opening `java.base/java.lang` to read a JDK private member merely due to an access error is usually a sign you should choose a more appropriate public API.

After resolving access, you still must validate receiver, arity, and parameter types: `setAccessible(true)` does not fix `IllegalArgumentException`, `NoSuchMethodException`, or errors thrown by the target. The access control matrix by package, nest, and module is presented separately in the access-focused article; the table here is for **isolating exceptions** during debugging.

## 8. Do Not Lump `Method.invoke` Together with `MethodHandle` and Dynamic Proxy

Although all belong to the reflective/dynamic invocation ecosystem, **their error-throwing mechanisms differ**.

### 8.1. MethodHandle: WrongMethodTypeException

With `MethodHandle`, the signature lives in `handle.type()`. `invokeExact` requires the argument types and return type **at the call site** to match exactly. `invoke` allows valid type adaptations; if adaptation is impossible, it throws `WrongMethodTypeException`. If a reference cast fails at runtime, `ClassCastException` may be seen.

Illustrative snippet, not a standalone program:

```java
// h has MethodType (long,long)long.
long ok = (long) h.invokeExact(1L, 2L);
long bad = (long) h.invokeExact(1, 2L); // WrongMethodTypeException
```

Do not handle `WrongMethodTypeException` by catching `InvocationTargetException`: it is a different exception type and does not represent a target error wrapped by `Method.invoke`.

### 8.2. Dynamic Proxy: UndeclaredThrowableException

With JDK dynamic proxies, `InvocationHandler.invoke` can throw `Throwable`. If the handler throws a **checked exception** not declared in the `throws` clause of the interface method, the proxy can wrap it into `UndeclaredThrowableException`. Check:

- Which interface the method belongs to, and which checked exceptions `getExceptionTypes()` declares.
- Whether the handler unwraps, converts, or throws a checked exception outside the contract.
- `UndeclaredThrowableException.getUndeclaredThrowable()` or `getCause()` to see the original error.
- If `StackOverflowError` occurs, check whether the handler calls `method.invoke(proxy, args)` back on the proxy or logs the proxy itself causing `toString()` re-entry.

`InvocationTargetException` can appear **inside the handler** if the handler uses `Method.invoke(target, args)`, whereas `UndeclaredThrowableException` is the wrapper the dynamic proxy creates when an uncontracted checked exception escapes to the caller. Do not conflate the two layers.

### 8.3. Generic Metadata Can Fail Separately

When reading `getGenericParameterTypes()` or `getGenericReturnType()`, some APIs can encounter `TypeNotPresentException`, `MalformedParameterizedTypeException`, or `GenericSignatureFormatError` because a type signature fails to resolve or is invalid. That does not necessarily mean the method does not exist. If a tool depends on generic metadata, log both raw and generic signatures and the module/classpath of the referenced type, without inventing false substitute values.

## 9. Ordered Error Investigation Checklist

When receiving a failed Reflective Invocation log, collect structured information:

1. **Stage:** class load, lookup, accessibility, input mapping, invocation, target execution, or initialization?
2. **Actual exception and cause:** `ex.getClass().getName()`, `ex.getMessage()`, `ex.getCause()`; for `InvocationTargetException`, inspect the cause directly.
3. **Class identity:** `type.getName()`, `type.getModule()`, `type.getClassLoader()` if appropriate. Two classes with the same name but different class loaders are not the same type.
4. **Method/field signature:** name, declaring class, modifiers, parameter types in order, return type or field type, `isVarArgs()`.
5. **Receiver:** null or not; actual runtime class via `receiver.getClass()` (only call when non-null); compatible with declaring class or not.
6. **Arguments:** count, runtime types displayable as type names, offending index, primitive/wrapper, and whether converters ran. For null, a schema is needed to know the expected type.
7. **Access/module:** public/private, package, `module-info.java`, `exports/opens`, caller module, and `canAccess(...)` as appropriate.
8. **API contract:** which methods are allowed to be called, whether the caller has permission, what data error to report, and whether transactions/side effects occurred if the target already ran.
9. **Stack trace:** which frames repeat or lie inside the target; do not look only at the outermost wrapper line.
10. **Reproduction:** write a minimal test with equivalent class/method/arguments, blocking bad input before invocation.

You can use the following **metadata** logging helper for debugging; this is a snippet inside a method with a `Method method` variable and `Arrays`, `Modifier` imported:

```java
System.out.println("declaring=" + method.getDeclaringClass().getName());
System.out.println("method=" + method.getName());
System.out.println("static=" + Modifier.isStatic(method.getModifiers()));
System.out.println("parameters=" +
        java.util.Arrays.toString(method.getParameterTypes()));
System.out.println("returns=" + method.getReturnType().getTypeName());
System.out.println("varargs=" + method.isVarArgs());
```

**Data protection:** do not log raw credentials, tokens, passwords, request bodies containing sensitive data, or raw argument values in production systems unless authorized. Logging type names, index, error code, and correlation ID is usually enough to investigate most mapping errors.

## 10. Error Handling and Reporting Principles

Do not write:

```java
try {
    // Find Method, convert data, invoke...
} catch (Exception ignored) {
    return null; // Wrong: loses the cause, turns an error into a fake result.
}
```

Instead, define **error boundaries**:

| Group | Appropriate Handling |
| --- | --- |
| Configuration error / method not found in a trusted contract | Fail-fast at startup; fix name/signature/dependency |
| Caller data error: arity, type, format | Validate/convert before invocation; report parameter and expected type |
| Access/module error | Review public API design and permissions; only open packages intentionally and when authorized |
| Target error | Unwrap cause from `InvocationTargetException`; handle according to business contract |
| Severe JVM/linkage/initialization error | Log full context, handle at an appropriate system boundary; do not blindly swallow `Error` |
| Dynamic proxy/MethodHandle error | Diagnose by handler/call-site signature separately; do not force into `Method.invoke` mechanics |

**Do not blindly retry** once the target has been invoked: the method may have written data, sent network requests, or performed side effects before throwing. Only retry if the business contract allows it and appropriate idempotency/transaction mechanisms exist.

## 11. Common Mistakes

1. Immediately calling `getDeclaredMethods()[0]` upon hitting `NoSuchMethodException`, easily picking the wrong overload or wrong visibility.
2. Matching only by method name, ignoring `int.class` versus `Integer.class` parameters.
3. Calling `setAccessible(true)` whenever seeing a private member without evaluating modules/API design.
4. Assuming `Method.invoke` parses `String` into primitives or DTOs.
5. Failing to distinguish static/instance and passing a null or wrong-typed receiver.
6. Catching `InvocationTargetException` and logging only the wrapper, losing `getCause()`.
7. Catching all `Throwable` and continuing as if no error happened, masking serious `Error`s.
8. Thinking `ReflectiveOperationException` covers `InaccessibleObjectException`, `SecurityException`, `WrongMethodTypeException`, or `LinkageError`.
9. Calling `Class.forName` and assuming every failure means "class missing": initialization/linkage are also possibilities to distinguish.
10. With proxies, calling back into the proxy itself inside the handler causing `StackOverflowError`.
11. Assuming a method found via `getDeclaredMethod` can definitely be invoked.
12. Printing all arguments/requests for debugging without considering sensitive data exposure.

## 12. Self-Check Questions

**Question 1.** `getMethod("save", int.class)` throws `NoSuchMethodException` even though the code has `save(Integer)`. Why?

Because `int.class` differs from `Integer.class`; lookup matches by **exact type signature**. Boxing does not make `getMethod` automatically pick an overload.

**Question 2.** `getDeclaredMethod("secret")` finds the method, yet `invoke` throws `IllegalAccessException`. Is this a "method does not exist" error?

No. The metadata was found, but the caller lacks permission to invoke it. Check visibility/module/access design.

**Question 3.** The target throws `IOException` when `Method.invoke` calls it. Which exception should be caught at the reflection layer to find `IOException`?

Catch `InvocationTargetException`, and inspect `getCause()` or `getTargetException()`.

**Question 4.** Does `Method.invoke(target, "5")` calling a method accepting `int` automatically convert the string to a number?

No. You must parse explicitly beforehand and place a valid `Integer` value into `Object[]`.

**Question 5.** `Class.forName` throws `ExceptionInInitializerError`. Should you fix it by adding a JAR like for `ClassNotFoundException`?

Not by default. `ExceptionInInitializerError` indicates an error while running static initialization. Inspect the cause and static initializer code.

**Question 6.** `setAccessible(true)` throws `InaccessibleObjectException`. Does finding the `private` method prove the module permits deep access?

No. Finding metadata and having deep access permission are two different things; check JPMS `opens` rules and public API alternatives.

**Question 7.** A proxy throws `UndeclaredThrowableException` instead of the handler's checked exception. What should you inspect?

Inspect cause/`getUndeclaredThrowable()` and the checked exceptions declared on the interface method.

**Question 8.** With `WrongMethodTypeException` during `invokeExact`, do you need to check the return type too?

Yes. The return type **at the call site** must also match `MethodHandle.type()`, in addition to the argument types.

## 13. Takeaways

**Identify the stage where the error occurred first, then match against the right metadata and contract.** `NoSuchMethodException` points to a signature lookup error; `IllegalAccessException` points to access rights; `IllegalArgumentException` at `Method.invoke` usually points to receiver/arguments; `InvocationTargetException` indicates the target threw a `Throwable` and **the cause is what needs investigation**. JPMS, `MethodHandle`, and dynamic proxy errors each have their own mechanisms.

Java 17 documentation for direct reference:

- [Class (getMethod/getField/forName)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Constructor.newInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...))
- [AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html)
