# 7.9. Target Throwable Exceptions and Differences from Reflection Wrapping

## Learning Objectives

After this lesson, you will be able to:

1. Explain why `MethodHandle.invokeExact(...)`, `MethodHandle.invoke(...)`, and `invokeWithArguments(...)` can propagate a `Throwable` thrown by the target method **directly**.
2. Distinguish exceptions thrown by the **invocation target** from errors arising during lookup, signature checking, argument conversion, access checks, and call-site linkage.
3. Describe accurately how `java.lang.reflect.Method.invoke(...)` wraps target exceptions in `InvocationTargetException` and how to retrieve the cause using `getCause()`.
4. Recognize the differences among checked exceptions, unchecked exceptions, and `Error`; handle exceptions properly when building adapters or frameworks.
5. Write runnable Java 17+ code to compare both invocation paths and avoid losing stack traces or causes.

**Scope:** This lesson focuses on **method handle invocation** (Chapter 7) and compares it directly with the reflection mechanism. Creating handles via `Lookup` is only mentioned to the extent needed to clarify the source of exceptions.

## 1. The Problem: Where Does the Error Actually Come From?

Suppose the following business method can fail:

```java
public static String read(String key) throws java.io.IOException {
    if (key.isBlank()) {
        throw new java.io.IOException("empty key");
    }
    return "value:" + key;
}
```

This is an **illustrative method**, not a standalone Java program.

A normal call `read("")` can throw `IOException` directly. However, if a framework invokes this method indirectly, the exception seen by the outer layer also depends on **the API used to perform the invocation**:

- `MethodHandle.invokeExact(...)` or `invoke(...)`: when the target actually throws `IOException`, that `IOException` object propagates through the handle invocation **without being automatically wrapped by the method handle API** in `InvocationTargetException`.
- `Method.invoke(...)`: if the target method throws `IOException`, the caller receives **`InvocationTargetException`**, with `getCause()` being the original `IOException`.
- An error that occurs **before the target runs** (method not found, wrong signature, invalid arguments, insufficient access rights, etc.) must be handled separately; you must not assume that every caught exception is a business error.

Visualize the two paths:

```text
Method handle:
caller -> invokeExact/invoke -> target method -> IOException
caller catches IOException

Core reflection:
caller -> Method.invoke -> target method -> IOException
caller catches InvocationTargetException
                                  |
                                  +-- getCause() -> IOException
```

Reflection's wrapper object helps distinguish "a reflective call failed because **the target threw an error**" from errors thrown by the reflection API itself. Conversely, method handles have a model closer to a normal call: target errors go straight to the caller, but the caller must know how to classify the error source.

## 2. What Is `Throwable` in the Method Handle Invocation Path?

`java.lang.Throwable` is the root class of the throwable hierarchy in Java; its two main branches are `Error` and `Exception`. `RuntimeException` sits under `Exception`.

| Group | Examples | Meaning in dynamic invocation |
| --- | --- | --- |
| Checked exception | `IOException`, `SQLException`, `Exception` | With static calls, the compiler typically requires declaring/catching according to the method signature; with handles, the invocation API already declares `throws Throwable` |
| Unchecked exception | `IllegalStateException`, `IllegalArgumentException`, `NullPointerException` | May come from the target itself or be caused by the adapter/invocation API |
| `Error` | `AssertionError`, `LinkageError`, `OutOfMemoryError` | Also a `Throwable`; should not be caught and swallowed in production flows |
| Invocation/linkage failure | `WrongMethodTypeException`, `ClassCastException`, `NoSuchMethodException`, `IllegalAccessException` | Need to distinguish whether it arose at the call site/lookup/adaptation or was thrown by the target itself |

**Note:** An exception class such as `IllegalArgumentException` may be **intentionally thrown by business code**, or it may be thrown by the invocation API to report invalid arguments. Looking only at the exception class name is usually not enough to determine the source.

### 2.1. Why Do Handle Invocations Declare `throws Throwable`?

In Java SE 17, the **signature-polymorphic** methods `MethodHandle.invokeExact` and `MethodHandle.invoke` are declared as `throws Throwable`. A handle can point to many very different targets, and the JVM does not encode the full list of checked exceptions into `MethodType`.

When writing:

```java
String result = (String) handle.invokeExact("ready");
```

This is an **illustrative line of code** inside a method that has a `MethodHandle handle` variable of type `(String)String`. The compiler knows the handle invocation expression can throw `Throwable` because of the API declaration, even if the specific target only declares `throws IOException` or declares no checked exceptions at all. Therefore, the method containing the call must handle it appropriately with `try/catch` or declare `throws Throwable`.

Do not infer that because the API declares `throws Throwable`, it will always create an extra `Throwable` wrapper. **Declaring `throws` and wrapping exceptions are two different things.**

### 2.2. What Does "Direct Propagation" Mean?

If the target method body executes `throw original;`, the handle invocation delivers that throwable directly to the caller without creating an `InvocationTargetException` to wrap it. This includes:

- checked exceptions (`IOException`);
- unchecked exceptions (`IllegalStateException`);
- `Error` (`AssertionError` in the verification example).

You can `catch (IOException ex)` directly in the caller when you know the target may produce that kind of error. If code catches `Throwable` for diagnostics, you must understand that it will also catch `Error` and throwables that should not be arbitrarily handled and continued past.

### 2.3. Do `invokeExact` and `invoke` Have the Same Target Error Propagation Rules?

Yes. Both propagate throwables thrown by the target directly. The main difference is **the invocation mode**:

- `invokeExact` requires the call-site descriptor (the static types of the arguments and return value at the call site) to match `handle.type()` exactly; a mismatch can throw `WrongMethodTypeException` **before** entering the target.
- `invoke` allows type conversions supported by the method handle contract, similar to adapting with `asType`. If a conversion is invalid, the caller receives an error from the adaptation/conversion process, which is also **not** `InvocationTargetException`.
- `invokeWithArguments` is convenient when arguments are in `Object[]`/`List<?>` form, and also declares `throws Throwable`. It has an argument/result adaptation step with corresponding costs and conversion errors; you should not assume every exception from this call comes from the target method body.

A handle can also be constructed from combinators such as `filterArguments`, `catchException`, `throwException`, or custom adapters. In that case, **the entire handle pipeline** is the observed target, and custom-built logic may intentionally alter exceptions. The statement "no default `InvocationTargetException` wrapper" applies to **standard handle invocation behavior**, and does not prevent your own code from actively wrapping errors.

## 3. Reflection Wraps Target Errors in `InvocationTargetException`

`java.lang.reflect.Method.invoke(Object receiver, Object... args)` invokes a method through class metadata. It declares reflective errors such as `IllegalAccessException`, `IllegalArgumentException`, and `InvocationTargetException`.

When **the target method actually throws a throwable**, `Method.invoke` throws `InvocationTargetException`. This wrapper is a **checked exception** (a subclass of `ReflectiveOperationException`), while the original throwable is stored in its cause.

```java
try {
    Object value = reflectedMethod.invoke(null, "bad");
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable original = ex.getCause();
    // Handle based on the actual exception type of the target method.
}
```

This is an **illustrative snippet**: `reflectedMethod` must be a `Method` object for a static method taking `String`. For an instance method, the receiver parameter is an appropriate instance instead of `null`.

### 3.1. `getCause()` or `getTargetException()`?

Both access the original throwable inside `InvocationTargetException`. `getTargetException()` is the historical API that predates the general cause-chaining mechanism; **`getCause()` is preferred** in new code.

If classification is needed:

```java
Throwable cause = ex.getCause();
if (cause instanceof java.io.IOException io) {
    // Actual I/O error from the target.
} else if (cause instanceof IllegalStateException state) {
    // Actual state error from the target.
}
```

This is an illustrative snippet inside `catch (InvocationTargetException ex)`. Pattern matching for `instanceof` has been supported since Java 16, so it works on Java 17. A wrapper constructed manually by other code may have a `null` cause; when unwrapping in a general-purpose library, account for this unusual case.

### 3.2. Does Reflection Wrap Unchecked Exceptions and Errors from the Target Too?

Yes. If a reflected method throws `IllegalStateException` or `AssertionError`, `Method.invoke` still uses `InvocationTargetException` to report that **the target threw an error**. Do not assume that only checked exceptions are wrapped.

However, **not every throwable that occurs when calling `Method.invoke` is wrapped**. For example: passing invalid arguments can cause `IllegalArgumentException` from the reflection API before the target runs; a `null` receiver for an instance method causes `NullPointerException`; failed static class initialization can cause `ExceptionInInitializerError`. You must read the API contract and distinguish the layer where the error occurred.

## 4. Comparison Table: MethodHandle vs. Method.invoke

| Scenario | `MethodHandle.invokeExact/invoke` | `Method.invoke` |
| --- | --- | --- |
| Target throws `IOException` | Caller receives `IOException` directly | Caller receives `InvocationTargetException`, `getCause()` is `IOException` |
| Target throws `IllegalStateException` | `IllegalStateException` directly | `InvocationTargetException` containing `IllegalStateException` |
| Target throws `AssertionError` | `AssertionError` directly | `InvocationTargetException` containing `AssertionError` |
| Call-site type does not match handle | May throw `WrongMethodTypeException`, target not executed | No `invokeExact`; reflection API checks arguments by its own rules |
| Wrong arguments with `Method.invoke` | Handle may fail due to type/conversion before target | `IllegalArgumentException` directly, no default wrapper |
| Lookup with wrong method name/signature | `Lookup.find...` may throw `NoSuchMethodException`/`IllegalAccessException` before obtaining handle | `Class.getMethod(...)` may throw `NoSuchMethodException` before obtaining `Method` |
| Result type | Determined by `MethodType` and call-site descriptor | API returns `Object`; void target yields `null`; primitive return is boxed |
| Checked exception checking at caller | `invokeExact/invoke` API declares `throws Throwable` | `Method.invoke` API declares `InvocationTargetException` and other reflective errors |
| When logging business errors | Record the original throwable; do not unwrap a nonexistent wrapper | Unwrap one layer of `InvocationTargetException` at the appropriate boundary, preserving the cause |

This structure has a direct impact on monitoring: the exact same business error has a different **top-level exception class** depending on whether the framework uses MethodHandle or core reflection. If a system counts errors by top-level class name, reflection tends to lump many real errors under the `InvocationTargetException` label. Group by **the controlled root/target cause** while still preserving information about the invocation boundary.

## 5. Standalone Runnable Java 17+ Example: Comparing All Three Throwable Groups

Save the file **`ThrowableCallDemo.java`**:

```java
import java.io.IOException;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ThrowableCallDemo {
    public static String work(String kind) throws IOException {
        switch (kind) {
            case "checked":
                throw new IOException("disk");
            case "runtime":
                throw new IllegalStateException("state");
            case "error":
                throw new AssertionError("assertion");
            default:
                return "ok:" + kind;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandle handle = MethodHandles.lookup()
                .findStatic(ThrowableCallDemo.class, "work", type);
        Method reflected = ThrowableCallDemo.class.getMethod("work", String.class);

        System.out.println("handleType=" + handle.type());
        System.out.println("mh-ok=" + (String) handle.invokeExact("ready"));
        System.out.println("reflect-ok=" + reflected.invoke(null, "ready"));

        for (String kind : new String[]{"checked", "runtime", "error"}) {
            try {
                String ignored = (String) handle.invokeExact(kind);
            } catch (Throwable ex) {
                System.out.println("mh-" + kind + "="
                        + ex.getClass().getSimpleName() + ":" + ex.getMessage());
            }

            try {
                Object ignored = reflected.invoke(null, kind);
            } catch (InvocationTargetException ex) {
                Throwable cause = ex.getCause();
                System.out.println("reflect-" + kind + "="
                        + ex.getClass().getSimpleName()
                        + ",cause=" + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage());
            }
        }

        try {
            Object wrongResult = handle.invokeExact("ready");
        } catch (WrongMethodTypeException ex) {
            System.out.println("mh-wrong-type=" + ex.getClass().getSimpleName());
        }
        try {
            reflected.invoke(null, 42);
        } catch (IllegalArgumentException ex) {
            System.out.println("reflect-bad-args=" + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac --release 17 ThrowableCallDemo.java
java ThrowableCallDemo
```

**Exact stdout:**

```text
handleType=(String)String
mh-ok=ok:ready
reflect-ok=ok:ready
mh-checked=IOException:disk
reflect-checked=InvocationTargetException,cause=IOException:disk
mh-runtime=IllegalStateException:state
reflect-runtime=InvocationTargetException,cause=IllegalStateException:state
mh-error=AssertionError:assertion
reflect-error=InvocationTargetException,cause=AssertionError:assertion
mh-wrong-type=WrongMethodTypeException
reflect-bad-args=IllegalArgumentException
```

### 5.1. Why Do Both Successful Paths Look the Same?

`work("ready")` returns `"ok:ready"`. The handle has type `(String)String`. `Method.invoke(null, "ready")` accepts a `null` receiver because `work` is a **static method**; the return value is an `Object` holding a `String` reference, so string concatenation still displays the same result.

### 5.2. Why Does Checked `IOException` Pass Directly Through the Handle?

In the body of `work("checked")`, the method throws `new IOException("disk")`. `invokeExact` does not create an `InvocationTargetException`; `catch (Throwable ex)` receives the `IOException` itself, resulting in the line `mh-checked=IOException:disk`. Reflection catches `InvocationTargetException` on the outside; its cause is `IOException:disk`. The results are similar for `IllegalStateException` and `AssertionError`.

The demo **intentionally catches `Throwable`** to observe checked exceptions, runtime exceptions, and `Error` in a single loop. **Do not copy this catch-and-continue strategy into production**, especially for serious `Error`s or errors that leave application state untrustworthy.

### 5.3. The Last Two Errors Were Not Thrown by the Body of `work`

- `Object wrongResult = handle.invokeExact("ready")` sets the call-site result type to `Object`, whereas the handle returns `String`. `invokeExact` requires exact types, so it throws `WrongMethodTypeException` before the target executes. If you use `String result = (String) handle.invokeExact("ready")`, the requested type is `String` and the call succeeds.
- `reflected.invoke(null, 42)` passes an `Integer` when the target method declares `String`, so reflection throws `IllegalArgumentException`. There is no `InvocationTargetException` because the target was never run.

This is why you should **never classify errors solely by the API called**. Ask: did the error occur when looking up the method, when checking/converting types, inside the target's code, or at an application-added wrapper layer?

## 6. Error Sources: Dividing into Clear Phases

### 6.1. Phase A — Lookup and Access Checks

For example:

```java
MethodHandle handle = MethodHandles.lookup().findStatic(
        SomeClass.class,
        "operation",
        MethodType.methodType(String.class, String.class));
```

This is an **illustrative snippet**; `SomeClass` is just a placeholder name. At this point, the target has not been called yet. If the method does not exist or the signature is wrong, `Lookup` may throw `NoSuchMethodException`; if access is insufficient, it may throw `IllegalAccessException`. When a `Method` is obtained via `Class.getMethod(...)`, resolving an incorrect name/signature also throws `NoSuchMethodException` right at the lookup step.

These errors belong to **configuration, classpath, module/access, or adapter construction**, not to the business invocation itself. Validate them at startup and report the requested method name and descriptor.

### 6.2. Phase B — Call-Site Checking, Conversion, and Linkage

With a method handle:

- `invokeExact` can throw `WrongMethodTypeException` if the parameter or return types at the call site do not match.
- `invoke` or a handle adapted with `asType` can throw `ClassCastException`, `NullPointerException`, `WrongMethodTypeException`, or related errors depending on the conversion and invocation.
- If the target has not executed yet, this is an error at the invocation boundary. Do not report "the business method threw an exception" when the adapter actually passed the wrong types.

With `Method.invoke`:

- Passing the wrong receiver, argument count, or argument types can cause `IllegalArgumentException`; a `null` receiver when calling an instance method can cause `NullPointerException`.
- Insufficient access rights cause `IllegalAccessException`.
- Failed static class initialization can cause `ExceptionInInitializerError`.

These errors typically occur outside the target method body, so they do not follow the `InvocationTargetException` wrapping rule reserved for throwables **thrown by the target itself**.

### 6.3. Phase C — The Target Actually Runs and Throws a Throwable

In this phase, the central difference takes effect:

- **MethodHandle:** the throwable passes through directly, unless an adapter pipeline you built intentionally catches/transforms it.
- **Reflection:** `Method.invoke` presents the target's throwable via `InvocationTargetException`.

A target method can also throw `ClassCastException`, `IllegalArgumentException`, or `WrongMethodTypeException` itself, since those are all types that can be thrown from Java code. Therefore, to determine the source when types overlap, rely on **the call path, stack trace, context, and check location**. Exceptions of the same class do not necessarily originate from the same phase.

## 7. Reasonable Exception Handling in Production Adapters

### 7.1. Preserving the Checked Exception Contract

Suppose a boundary has a contract that only exposes `IOException`, while the actual handle invoked is configured to execute `String work(String) throws IOException`. You can narrow `throws Throwable` back to a clearer contract:

```java
static String viaHandle(MethodHandle handle, String key) throws IOException {
    try {
        return (String) handle.invokeExact(key);
    } catch (IOException expected) {
        throw expected;
    } catch (RuntimeException | Error unchecked) {
        throw unchecked;
    } catch (Throwable unexpectedChecked) {
        throw new IllegalStateException(
                "Unexpected checked Throwable from handle", unexpectedChecked);
    }
}
```

**This is an illustrative method** that must be placed in a class importing `MethodHandle` and `IOException`; it is not a standalone file. It assumes `handle.type()` is `(String)String`. Rules:

1. Let the expected checked exception (`IOException`) pass through untouched.
2. Propagate runtime exceptions and `Error`s outward without disguising them as "I/O errors".
3. For any other checked `Throwable` outside the contract, wrap it at the boundary according to a clear policy and **preserve the original cause**.

Another application might deliberately declare `throws Throwable`, define its own domain exception, or return a `Result` type; the choice depends on the contract. However, do not use `catch (Throwable ignored)` to turn every error into `null` or a success status code.

### 7.2. Unwrapping Reflection Exactly One Layer at the Boundary

For the corresponding `Method`, you can write:

```java
static String viaReflection(Method method, String key) throws IOException {
    try {
        return (String) method.invoke(null, key);
    } catch (InvocationTargetException wrapper) {
        Throwable cause = wrapper.getCause();

        if (cause instanceof IOException io) {
            throw io;
        }
        if (cause instanceof RuntimeException runtime) {
            throw runtime;
        }
        if (cause instanceof Error error) {
            throw error;
        }
        throw new IllegalStateException(
                "Unexpected checked Throwable from target", cause);
    } catch (IllegalAccessException access) {
        throw new IllegalStateException("Cannot access target method", access);
    }
}
```

This is an illustrative method in a class that imports `Method`, `InvocationTargetException`, and `IOException`. Ensure `method` is a static method returning `String` and taking `String`, and that inputs/call paths have been validated. An `IllegalArgumentException` caused by passing invalid arguments is still thrown directly and does not enter `catch (InvocationTargetException)`.

At the boundary, properly unwrapping `InvocationTargetException` allows the error policy to handle the same `IOException` just like the method handle side. If you catch and rethrow the cause without changing the object, the cause's stack trace still describes the original location; if you translate it to a different exception, pass the cause into the constructor to preserve that information.

### 7.3. Do Not Unwrap Every `cause` Unconditionally

Ask: **which API created the wrapper?**

- `InvocationTargetException` from `Method.invoke` is core reflection's standard wrapper for target errors.
- `CompletionException` and `ExecutionException` have their own wrapper contracts in asynchronous processing.
- `UndeclaredThrowableException` can arise in proxies when a checked throwable is not declared in the interface.
- `InvocationTargetException` can also be **thrown by business code itself**. If a method handle invokes a target that throws `InvocationTargetException`, the handle caller receives that exact type; there is no evidence the method handle API wrapped it itself.
- Frameworks or callbacks may intentionally add wrappers. Check the contract of that layer before deciding how to unwrap.

Avoid loops that "unwrap `getCause()` all the way to the bottom" without preserving boundary information: wrapper layers sometimes contain necessary business context. Prefer unwrapping where you know the exact source of the wrapper and record sufficient diagnostic information.

### 7.4. Preserving Information When Logging and Translating Errors

Typically, a useful log entry should describe:

- module/class/method name and `handle.type()` or method signature;
- safe input context (request ID, operation type), without logging secrets or sensitive data;
- **the actual throwable type** and message, including `cause` after unwrapping reflection;
- the stack trace of the original throwable, relevant wrappers, and the phase where the error occurred (lookup, adaptation, or target).

If translating a checked exception into an unchecked exception, use a constructor that accepts a cause, such as `new IllegalStateException("Invocation failed", original)`. Do not create `new RuntimeException(original.getMessage())` and discard the original stack trace. Do not rely solely on `InvocationTargetException.getMessage()`, because many wrappers do not have a useful detail message.

In environments with retries, distinguish **retryable business errors** (such as transient I/O) from **unrecoverable configuration/type errors** (wrong method signature, missing permissions) to avoid infinite retries.

## 8. Special Cases

### 8.1. `Error` and Dangerous Throwables

The example uses `AssertionError` to test the wrapping mechanism without breaking the JVM. In practice, `OutOfMemoryError`, `StackOverflowError`, and critical runtime errors should not be swallowed just to "avoid interrupting the request". A `catch (Throwable)` at a boundary may be needed for very careful cleanup/telemetry, but it should normally rethrow according to an appropriate policy.

### 8.2. Target Throws a Checked Exception Not Declared by the Caller

Method handles allow a target to throw a checked exception because `invokeExact/invoke` declares `throws Throwable`. That does not mean every outer layer is permitted to arbitrarily throw checked exceptions missing from its Java contract. In adapters with stricter signatures, catch, declare, or translate errors intentionally while preserving the cause.

With reflection, the compiler also does not infer `IOException` from a `Method` object: the caller only sees the checked exceptions of `Method.invoke`, including `InvocationTargetException`, and must resolve the cause according to the application contract.

### 8.3. Method Handle Obtained from Reflection

`lookup.unreflect(method)` creates a handle corresponding to `Method` subject to access checks. **Once the handle is successfully created and invoked**, it uses **method handle** invocation semantics and does not automatically inherit `Method.invoke`'s `InvocationTargetException` wrapper. However, the target itself may intentionally throw that exception type, and the `unreflect` step can encounter its own access errors.

### 8.4. Proxies or Frameworks May Add Their Own Wrappers

When an invocation passes through a dynamic proxy, interceptor, transaction layer, or async layer, exceptions may be transformed according to each layer's contract. For example, a JDK dynamic proxy can wrap an undeclared checked exception in `UndeclaredThrowableException`. This is **a different layer** from `Method.invoke` and does not change the rule that standard method handles propagate target errors directly.

### 8.5. When the Target Returns Normally

For a target returning `void`, `Method.invoke` returns `null`; a method handle with a `void` return signature requires the caller to use it according to the corresponding call-site contract, without casting the result to `Object` at `invokeExact`. If the target finishes normally, there is no exception to propagate or wrap. Avoid confusing `Method.invoke` boxing/wrapping the return value with **wrapping exceptions**: those are two different mechanisms.

## 9. Checklist When Debugging an Invocation Error

1. **Was the target found?** If not, check the method name, `MethodType`, receiver, module access, and lookup exceptions.
2. **Does the call site match?** For `invokeExact`, check the static types of the arguments and **the return type** at the invocation expression, then compare against `handle.type()`.
3. **Did the target run?** If not, review conversions/bounds/access or class initialization exceptions.
4. **Which API did the call use?** `MethodHandle.invokeExact/invoke` or `Method.invoke`? Only unwrap `InvocationTargetException` at a reflection boundary or when that wrapper was intentionally created.
5. **Is there an original exception in the cause?** If it is a reflection wrapper, get `getCause()` and preserve the stack trace; if it is a handle, usually catch the target throwable directly.
6. **Is the error classified properly?** Checked domain errors, runtime programming errors, `Error`, lookup failures, and conversion failures have different policies.
7. **Did any framework layer alter the error?** Proxies, asynchronous execution, or adapters may add wrappers; do not attribute every wrapper to method handles.
8. **Was any information lost?** Avoid dropping `cause`, replacing stack traces with messages, logging redundantly at every layer, or leaking sensitive data.

## 10. Common Pitfalls

- **"MethodHandle always throws `InvocationTargetException` just like reflection."** False. Standard handles propagate the target's throwable directly.
- **"`throws Throwable` means every error is wrapped in `Throwable`."** False. That is a declaration of what may be thrown, not a wrapping action.
- **"`Method.invoke` only wraps checked exceptions."** False. It also wraps unchecked exceptions and `Error`s thrown by the target.
- **"Any error during `Method.invoke` is `InvocationTargetException`."** False. Wrong arguments, receiver issues, access rights, or class initialization have their own error paths.
- **"`WrongMethodTypeException` is definitely thrown by business logic."** False. It usually indicates a mismatch between the call site and the handle before the target runs, though target code could also throw this type itself.
- **"Logging just the `InvocationTargetException` class name is enough."** Insufficient. You need the actual cause and invocation context.
- **"You can catch `Throwable` and ignore it so the application keeps running."** Dangerous. This can mask critical `Error`s and leave data in a corrupted state.
- **"Always unwrapping down to the root cause is always right."** Not necessarily. Wrappers can capture important context, and not every `cause` is a purely technical wrapper.
- **"Switching to `Lookup.unreflect` keeps `Method.invoke` semantics."** False. The resulting handle operates under method handle invocation semantics, while lookup/access exceptions belong to a separate phase.

## 11. Exercises and Answers

### Exercise 1 — Predict the Exception

A target method throws `new java.io.FileNotFoundException("missing")`. One caller uses `invokeExact` with the correct call-site type and the target runs; the other caller uses `Method.invoke`.

**Answer:** The handle caller receives `FileNotFoundException` directly. The reflection caller receives `InvocationTargetException` with `getCause()` equal to `FileNotFoundException`. `FileNotFoundException` is a checked exception subclass of `IOException`.

### Exercise 2 — Identify the Error Phase

A handle has type `(String)String`; the code writes `Object result = handle.invokeExact("x");` and encounters `WrongMethodTypeException` even though the target has no bugs.

**Answer:** The return type at the call site is `Object`, which differs from `String`. The error occurs at the signature-checking step **before the target runs**. Fix it to `String result = (String) handle.invokeExact("x");` if that matches the handle's actual contract.

### Exercise 3 — Does Reflection Wrap It or Not?

When `method.invoke(null, Integer.valueOf(3))` calls a method that only accepts `String`, it encounters `IllegalArgumentException`. Should you access `((InvocationTargetException) ex).getCause()`?

**Answer:** No. `IllegalArgumentException` here comes from the reflection API during argument validation. It is not an `InvocationTargetException`; such a cast would fail.

### Exercise 4 — Design an Adapter

A service exposes `String load(String key) throws IOException` but invokes a handle underneath. Write an adapter to:
- let `IOException` pass through untouched;
- not swallow `RuntimeException` and `Error`;
- translate any other checked `Throwable` into an exception with context while preserving the original cause.

**Hint:** Use the `viaHandle` pattern in Section 7.1. Also write an integration test where the target throws `IOException` and a test for a call-site mismatch.

### Exercise 5 — Finding the Root Cause Without Losing Context

A framework uses reflection, catches `InvocationTargetException`, and then throws `new RuntimeException("failed")`. Why is debugging harder?

**Answer:** The framework dropped `getCause()`, including the actual error type, message, and original stack trace. At a minimum, use `new RuntimeException("failed", wrapper.getCause())`, while also keeping the method/configuration details in the message or structured log.

## Official Documentation

- [Java SE 17 — MethodHandle: invokeExact, invoke, and Exceptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — java.lang.reflect.Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [Java SE 17 — Throwable and cause chaining](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)

## Conclusion

**MethodHandle** invokes targets with direct `Throwable` propagation semantics: checked exceptions, unchecked exceptions, and `Error`s from the target reach the caller without a default `InvocationTargetException` wrapper. **Core reflection** uses `Method.invoke` to wrap throwables thrown by the target in `InvocationTargetException`; the caller retrieves the original error with `getCause()`. When building frameworks or adapters, classify **lookup → conversion/call-site → target**, preserve causes and stack traces, and apply checked-exception policies that match the contract rather than lumping all invocation errors into a single bucket.
