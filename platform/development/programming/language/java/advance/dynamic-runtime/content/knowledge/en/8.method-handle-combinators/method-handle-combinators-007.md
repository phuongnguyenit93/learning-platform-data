# 8.7 Wrapping Error Handling with catchException and Cleanup with tryFinally

**Module:** Java Advance - dynamic-runtime  
**Parent topic:** 8. Method Handle Combinators  
**Scope:** Two combinators of `java.lang.invoke.MethodHandles`: `catchException` and `tryFinally` (Java 17+).

## 1. Learning Objectives

When a program must create dynamic calls using `MethodHandle`, we often want to execute the target logic while preserving familiar policies: recovering when a certain type of exception occurs, logging, releasing resources, and not leaving partial state behind. Two combinators solve those needs without turning every target method into a separate `try/catch/finally` block.

After this lesson, you will:

1. Understand **which exact group of exceptions** `MethodHandles.catchException(target, exType, handler)` handles, which arguments it passes to the handler, and how it preserves the `MethodType` of the adapter.
2. Understand that `MethodHandles.tryFinally(target, cleanup)` invokes cleanup on both the **normal return** and **exception-throwing** paths, including the required signature of cleanup.
3. Distinguish between **recovering into a value** (`catchException`) and **cleaning up after a call** (`tryFinally`); know why `tryFinally` itself does not turn an exception into a successful result.
4. Choose the wrapping order of the two combinators to determine whether cleanup observes the exception **before or after recovery**.
5. Know the impact of exceptions thrown inside cleanup, the `MethodType` rules for target/handler/cleanup, and the case where the target method returns `void`.
6. Compile and run Java 17+ examples, verifying the actual output rather than inferring from API names.

## 2. A Combinator Is a Transformation on a Method Handle

A `MethodHandle` describes how to invoke an operation, while also carrying a `MethodType`: the list of parameter types and the return type. `MethodHandles` provides **combinators** to build new handles with additional behavior from existing handles:

~~~text
target:        (A, B, ...) -> R
                      |
             +--------+--------+
             |                 |
        catchException      tryFinally
             |                 |
        handler if error   cleanup on both
        matches type       success and error
             |                 |
           adapter: (A, B, ...) -> R
~~~

This is a conceptual diagram, not bytecode. Both combinators **return a new handle** without modifying the body or `MethodType` of the original target. Both adapter handles usually keep **the exact invocation type of the target**; only the auxiliary handles (handler/cleanup) require additional signatures to receive information about the exception or result.

It is necessary to distinguish:

- **Errors when combining handles:** `IllegalArgumentException` (or `NullPointerException` for null inputs) can be thrown immediately when calling the combinator if the `MethodType`s do not satisfy the contract.
- **Errors when executing the target:** can be handled by `catchException`, or pass through `tryFinally` after cleanup is invoked.
- **Errors when calling the adapter with the wrong descriptor:** `MethodHandle.invokeExact` may throw `WrongMethodTypeException` if the call site does not match `adapter.type()`. This is a separate invocation check and does not mean the handler/cleanup is wrong.

## 3. `catchException`: Recovering When Encountering the Right Error Type

API:

~~~java
MethodHandle recovered =
        MethodHandles.catchException(target, exceptionType, handler);
~~~

This is an illustrative snippet assuming `target`, `exceptionType`, and `handler` variables already exist; it is not a standalone program.

### 3.1. Exact Signature Rules

Suppose target has the form:

~~~text
R target(A, B, C)
~~~

The handler can accept only the exception, or the exception plus **a contiguous leading part (prefix)** of the target's parameters:

~~~text
R handler(E)
R handler(E, A)
R handler(E, A, B)
R handler(E, A, B, C)
~~~

Where `E` is **`exceptionType` itself or a compatible supertype** in the first parameter position. The return type `R` of the handler **must match** the return type `R` of the target, even if the handler branch always throws an error. The parameters following the exception must match **in exact type and order** with the corresponding leading part of the target.

You cannot arbitrarily skip a middle parameter and take the last one. If the target takes `(String, int)`, then a handler `(IllegalArgumentException, int)` does **not** mean "only take the second int parameter": it has an invalid prefix because the first target argument is `String`.

Concrete example:

~~~text
target:  (String, int)String
exType:  IllegalArgumentException
handler: (IllegalArgumentException, String)String
adapter: (String, int)String
~~~

This handler takes the exception and the first `String` argument of the target; the second `int` argument is omitted. When the target returns normally, the handler **does not run**. When the target throws `IllegalArgumentException` or a subtype of it, the handler runs and the value returned by the handler becomes the result of the adapter.

### 3.2. Semantics in Pseudocode

~~~java
String adapted(String text, int count) {
    try {
        return target(text, count);
    } catch (IllegalArgumentException error) {
        return handler(error, text);
    }
}
~~~

This is **illustrative pseudocode**, not a real declaration that can be compiled standalone because the names `target`/`handler` represent method handles. Important characteristics:

- The exception type is matched by its actual runtime type just like the corresponding `catch`: subtypes of `exType` also match.
- An exception **not matching `exType`** propagates outward and is not turned into a success.
- **If the handler throws an error**, the new error propagates outward; `catchException` does not re-invoke the handler itself to handle that error.
- The arguments supplied to the handler are the **original arguments of the adapter call**, not state modified inside the target's stack frame.
- The handler does not have to return the thrown exception; if the goal is to log and rethrow, you need a handler with the proper nominal return type and a clearly designed throwing path (for example, using the `throwException` combinator when appropriate).
- Do not catch `Throwable`/`Exception` indiscriminately in systems requiring consistency: infrastructure failures, bugs, and business errors usually require different policies.

## 4. `tryFinally`: Cleanup on Both Paths

API:

~~~java
MethodHandle withCleanup =
        MethodHandles.tryFinally(target, cleanup);
~~~

`tryFinally` runs the target and then executes cleanup **whether the target returns normally or throws an exception**, following logic equivalent to Java `try/finally`. You need to fully understand the call structure to avoid creating an incorrect cleanup.

### 4.1. Signature of Cleanup When the Target Has a Result

Suppose:

~~~text
R target(A, B, C)
~~~

then cleanup must have the **required leading parameters**:

~~~text
R cleanup(Throwable, R)
~~~

and may take **a prefix** of the target's parameters:

~~~text
R cleanup(Throwable, R, A)
R cleanup(Throwable, R, A, B)
R cleanup(Throwable, R, A, B, C)
~~~

The first two parameters are:

1. `Throwable failure`: **`null` if the target returns normally**, or the exception that the target threw. Using `Throwable` is the safe choice; using a narrower type may cause an unexpected exception not to be assignable to the cleanup parameter and be masked by a `ClassCastException`.
2. `R result`: **the value returned by the target** on success; when the target throws an exception, the JVM provides **the default value of type `R`**: `null` for reference types, `0` for numeric types, `false` for boolean.

`cleanup` must **return the exact same type `R` as the target**. The value returned by cleanup is the final result of the adapter when the target completes normally; this allows logging, normalizing, tagging, or validating data before the caller receives the result. If the target throws an exception, **the return value of cleanup does not turn the failed call into a success**.

For a target taking `(String, int)String`, a suitable cleanup can have the type:

~~~text
(Throwable, String, String, int)String
~~~

Where the first `String` after `Throwable` is **result**, the next `String` is the **first target argument**, and `int` is the second target argument. Confusing result with the first target argument is a very common design mistake because both types can be `String`.

### 4.2. Target Returning `void`: No Result Parameter

For:

~~~text
void target(A, B)
~~~

cleanup must have a `void` return type, start with `Throwable`, and may then take a prefix of the target's parameters:

~~~text
void cleanup(Throwable)
void cleanup(Throwable, A)
void cleanup(Throwable, A, B)
~~~

Do **not** add a "`void result`" or `Object result` parameter to cleanup. The `void` type has no value to pass as a Java argument. The `CleanupEdgeDemo` program in section 7 illustrates this case.

### 4.3. Where Do Exceptions Go?

High-level semantics:

~~~text
target returns R
    -> cleanup(null, R, originalArgs...)
    -> returns the value returned by cleanup

target throws Throwable T
    -> cleanup(T, default value of R, originalArgs...)
    -> if cleanup returns normally: rethrows T
    -> if cleanup throws Throwable U: U is the exiting error
~~~

Key takeaway: `tryFinally` **does not automatically catch an error into a fallback result**. If recovery is desired, you must add `catchException` or a separate handling policy.

When cleanup **also throws an error**, the cleanup error can mask the original error, similar to a regular `finally` block that throws an exception. `tryFinally` does not by default record the original error into `Throwable.getSuppressed()` of the cleanup error. If both errors must be preserved, you need to design an explicit policy: log/report the cleanup error, actively manage suppressed exceptions when appropriate, or use `try-with-resources` in regular Java code.

### 4.4. Cleanup Does **Not** Manage Resources Automatically

The name `tryFinally` can create the impression that it automatically closes files/sockets/connections. That is not true. It only **invokes the cleanup handle you provide**. Only when the cleanup logic actually calls `close()`, releases a lock/lease, or updates state are resources cleaned up.

It also does not guarantee cleanup when the JVM is forcibly terminated, on power loss, `Runtime.halt`, process crash, or when a task is returned as a `CompletableFuture` and runs asynchronously after the target has already returned. `tryFinally` wraps **the synchronous call to the handle**, and does not automatically track the lifecycle of async tasks.

## 5. Java 17+ Practice: Handle Errors Then Clean Up

This exercise creates a target with two parameters and three cases:

- `"good"`: the target returns a normal result.
- `"bad"`: the target throws `IllegalArgumentException`, which the handler turns into a fallback.
- `"fatal"`: the target throws `IllegalStateException`, which is not of the caught type and will continue propagating after cleanup runs.

We also swap the **wrapping order** to see at which point cleanup observes the error.

**Standalone Java file:** `HandleErrorCleanupDemo.java`

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HandleErrorCleanupDemo {
    public static String work(String key, int attempt) {
        System.out.println("work:" + key + ":" + attempt);
        if ("bad".equals(key)) {
            throw new IllegalArgumentException("bad-input");
        }
        if ("fatal".equals(key)) {
            throw new IllegalStateException("server-down");
        }
        return "ok:" + key;
    }

    public static String recover(IllegalArgumentException error, String key) {
        System.out.println("recover:" + key + ":" + error.getMessage());
        return "fallback:" + key;
    }

    public static String cleanup(Throwable failure, String result,
                                 String key, int attempt) {
        String state = failure == null
                ? "success"
                : failure.getClass().getSimpleName();
        System.out.println("cleanup:" + key + ":" + state + ":" + result);
        return result == null ? null : result + "|closed";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle target = lookup.findStatic(
                HandleErrorCleanupDemo.class, "work",
                MethodType.methodType(String.class, String.class, int.class));
        MethodHandle handler = lookup.findStatic(
                HandleErrorCleanupDemo.class, "recover",
                MethodType.methodType(
                        String.class, IllegalArgumentException.class, String.class));
        MethodHandle cleaner = lookup.findStatic(
                HandleErrorCleanupDemo.class, "cleanup",
                MethodType.methodType(
                        String.class, Throwable.class, String.class,
                        String.class, int.class));

        MethodHandle recoverFirst = MethodHandles.tryFinally(
                MethodHandles.catchException(
                        target, IllegalArgumentException.class, handler),
                cleaner);
        MethodHandle cleanupFirst = MethodHandles.catchException(
                MethodHandles.tryFinally(target, cleaner),
                IllegalArgumentException.class, handler);

        System.out.println("type=" + recoverFirst.type());
        System.out.println("normal=" + (String) recoverFirst.invokeExact("good", 1));
        System.out.println("handled=" + (String) recoverFirst.invokeExact("bad", 2));
        try {
            String unused = (String) recoverFirst.invokeExact("fatal", 3);
            System.out.println("unexpected=" + unused);
        } catch (IllegalStateException error) {
            System.out.println("propagate=" + error.getMessage());
        }
        System.out.println("alternate=" + (String) cleanupFirst.invokeExact("bad", 4));
    }
}
~~~

**Compile and run with JDK 17+:**

~~~bash
javac --release 17 -d out HandleErrorCleanupDemo.java
java -cp out HandleErrorCleanupDemo
~~~

`javac -d out` creates the output directory if needed. **Verified stdout with the exact source above:**

~~~text
type=(String,int)String
work:good:1
cleanup:good:success:ok:good
normal=ok:good|closed
work:bad:2
recover:bad:bad-input
cleanup:bad:success:fallback:bad
handled=fallback:bad|closed
work:fatal:3
cleanup:fatal:IllegalStateException:null
propagate=server-down
work:bad:4
cleanup:bad:IllegalArgumentException:null
recover:bad:bad-input
alternate=fallback:bad
~~~

### 5.1. Reading the Output Accurately

**Call 1 — normal:**

~~~text
work:good:1
cleanup:good:success:ok:good
normal=ok:good|closed
~~~

Target returns `"ok:good"`, cleanup receives `failure == null` and `result == "ok:good"`, then returns `"ok:good|closed"`. The post-cleanup value becomes the final result.

**Call 2 — recovered before cleanup:**

~~~text
work:bad:2
recover:bad:bad-input
cleanup:bad:success:fallback:bad
handled=fallback:bad|closed
~~~

The **inner** `catchException` turned `IllegalArgumentException` into `"fallback:bad"`. Therefore, the outer `tryFinally` sees **its own target complete normally** and passes `failure == null` to cleanup. There is no contradiction: the exception was already consumed by the handler earlier.

**Call 3 — uncaught exception:**

~~~text
work:fatal:3
cleanup:fatal:IllegalStateException:null
propagate=server-down
~~~

The handler only applies to `IllegalArgumentException`, so `IllegalStateException` still escapes. `tryFinally` runs cleanup with the corresponding exception and `result == null` (default for `String`); whether cleanup returns `null` or another `String`, the original exception is still rethrown if cleanup does not throw a new error.

**Call 4 — cleanup first, handler second:**

~~~text
work:bad:4
cleanup:bad:IllegalArgumentException:null
recover:bad:bad-input
alternate=fallback:bad
~~~

In this pipeline, the **inner** `tryFinally` sees `IllegalArgumentException` and runs cleanup first; only after that does the outer `catchException` receive the error and produce the fallback. Because cleanup does not receive the fallback value, the final result **does not append `|closed`** in the example. This is an ordering difference, not nondeterminism.

## 6. Combinator Wrapping Order Has Business Meaning

### 6.1. Two Different Pipelines

**Pipeline A — Recovery then cleanup**

~~~java
MethodHandle pipelineA = MethodHandles.tryFinally(
        MethodHandles.catchException(target, IllegalArgumentException.class, handler),
        cleaner);
~~~

Diagram:

~~~text
CALL -> target
          | success -> result ---------------------+
          | IllegalArgumentException -> handler --+
          | other exception ----------------------+
                                                   |
                                               cleanup
                                                   |
                                               RETURN/THROW
~~~

If the handler **returns normally**, cleanup receives `failure == null` and **the recovered result**. If the handler throws another exception, cleanup observes the new exception. For systems that need "every result including fallbacks to go through a post-processing step", pipeline A is usually easier to understand.

**Pipeline B — Cleanup then recovery**

~~~java
MethodHandle pipelineB = MethodHandles.catchException(
        MethodHandles.tryFinally(target, cleaner),
        IllegalArgumentException.class,
        handler);
~~~

Diagram:

~~~text
CALL -> target -> cleanup -> success result
                       |
                       +-- exception -> catchException -> handler -> fallback
                       |
                       +-- unhandled exception -> propagate
~~~

Cleanup receives the exact **unrecovered** exception, which is useful when you need to log the original error or record failure metrics right at the target boundary. However, pipeline B's cleanup **does not run after the handler**. If the handler needs to release another resource, another appropriate policy must be in place.

**Comparison:**

| Question | Pipeline A: `tryFinally(catchException(...), cleaner)` | Pipeline B: `catchException(tryFinally(...), ..., handler)` |
| --- | --- | --- |
| Does cleanup run after the target succeeds? | Yes | Yes |
| Does the handler run when the selected error type occurs? | Yes | Yes, after cleanup |
| Does cleanup see the original error already turned into a fallback by the handler? | No, if the handler returns normally | Yes, because cleanup runs before the handler |
| Can cleanup transform the handler's fallback? | Yes | No, because the handler runs after cleanup |
| Do exceptions from the handler go through the same cleanup? | Yes | No; the `tryFinally` adapter has already completed before the handler |
| Can exceptions from cleanup be caught by the outer handler? | There is no outer catch in this expression | Yes, **if** the exception type thrown by cleanup matches `exType` |

Choose the pipeline based on the **meaning** of cleanup: is it a "post-processing of the final result" step or a "clean up state right after target" step? In real code, sometimes both are needed — but you should not nest combinators when a regular Java `try/catch/finally` block design is easier to read.

### 6.2. Which **Prefix** Do Handler and Cleanup Receive?

Example target `(String key, int attempt)String`:

- Handler `(IllegalArgumentException, String)String`: receives the exception + `key`, omitting `attempt`.
- Cleanup `(Throwable, String result, String key, int attempt)String`: receives the exception + result + **both** target arguments.
- If cleanup only needs the result, it can use `(Throwable, String)String` without knowing `key`/`attempt`.
- If cleanup needs `attempt` but does not need `key`, it cannot simply skip `key` and take `attempt` as the next parameter. Use additional argument-reordering/combining adapters (`dropArguments`, `permuteArguments`, `filterArguments`, etc., depending on requirements) or change the design so the signature matches.

**Do not use omitted arguments of handler/cleanup to infer data modified inside the target:** combinators pass the **original arguments**, and do not capture all local variables of the target.

## 7. Two Edge Cases to Know: Cleanup Throws an Error and Target Returns `void`

The following standalone example verifies both scenarios. Run it in the same project directory with the file `CleanupEdgeDemo.java`.

~~~java
import java.lang.invoke.*;

public class CleanupEdgeDemo {
    public static String failing() {
        throw new IllegalArgumentException("primary");
    }

    public static String failingCleanup(Throwable cause, String result) {
        throw new IllegalStateException("secondary");
    }

    public static void perform(String value) {
        System.out.println("perform:" + value);
    }

    public static void performCleanup(Throwable cause, String value) {
        System.out.println("performCleanup:"
                + (cause == null ? "ok" : "error") + ":" + value);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup l = MethodHandles.lookup();
        MethodHandle f = l.findStatic(
                CleanupEdgeDemo.class, "failing",
                MethodType.methodType(String.class));
        MethodHandle c = l.findStatic(
                CleanupEdgeDemo.class, "failingCleanup",
                MethodType.methodType(String.class, Throwable.class, String.class));
        MethodHandle wrapped = MethodHandles.tryFinally(f, c);

        try {
            String ignored = (String) wrapped.invokeExact();
        } catch (IllegalStateException e) {
            System.out.println("observed=" + e.getMessage()
                    + ",suppressed=" + e.getSuppressed().length);
        }

        MethodHandle a = l.findStatic(
                CleanupEdgeDemo.class, "perform",
                MethodType.methodType(void.class, String.class));
        MethodHandle b = l.findStatic(
                CleanupEdgeDemo.class, "performCleanup",
                MethodType.methodType(void.class, Throwable.class, String.class));
        MethodHandles.tryFinally(a, b).invokeExact("job");
    }
}
~~~

Run:

~~~bash
javac --release 17 -d out CleanupEdgeDemo.java
java -cp out CleanupEdgeDemo
~~~

Verified stdout:

~~~text
observed=secondary,suppressed=0
perform:job
performCleanup:ok:job
~~~

Meaning:

- `failing()` throws `IllegalArgumentException("primary")`, but cleanup throws `IllegalStateException("secondary")`. The exception seen outside is **the cleanup error**, and in this example no suppressed exception is automatically added (`suppressed=0`).
- `perform` returns `void`, so cleanup has the exact signature **`void(Throwable, String)`**, with no result parameter. `tryFinally` still runs cleanup after `perform("job")`.
- Do not use `tryFinally` as a default replacement for `try-with-resources`: `try-with-resources` has its own suppressed-exception handling policy when automatically closing resources.

## 8. Design Mistakes and How to Diagnose Them

| Issue | Common Reason | How to Fix |
| --- | --- | --- |
| Combining `catchException` throws `IllegalArgumentException` | Handler returns a different type than target or parameters after exception do not match target prefix | Print `target.type()` and `handler.type()`; check exact return type and argument order |
| Combining `tryFinally` throws `IllegalArgumentException` | Cleanup is missing `Throwable`/result, uses wrong return type, or passes target arguments with wrong prefix | Print `cleaner.type()`; cross-check non-void/void rules |
| Handler is not called | Target does not throw an exception or the error is not of `exType` | Check the actual exception class and wrapping position; do not catch broadly just to "make it run" |
| Cleanup receives `failure == null` even though the original target threw an error | An inner handler already recovered into a normal result | Check the `tryFinally(catchException(...), cleanup)` order |
| Cleanup receives `result == null` even though target has return type `String` | Target threw an exception; `null` is the placeholder for `String` | Check `failure` before using `result`; avoid dereferencing the placeholder |
| Original error disappears when cleanup throws a new error | The finally exception replaced the initial exception | Design a logging/propagation policy; do not let a close error unintentionally mask the primary error |
| `WrongMethodTypeException` on `invokeExact` | Static call-site types do not match `adapter.type()` | Cast the return value and pass arguments with exact types, or adapt the handle intentionally with `asType` |
| `NullPointerException` inside cleanup | Calling `failure.getMessage()` when `failure` is null or `result.length()` when `result` is null | Branch on `failure`/`result`; null has special semantics |
| Cleanup does not run after an async task | The handle only returns a `Future`/`CompletionStage` without waiting for work to finish | Attach cleanup to the async lifecycle at the appropriate layer |
| `ClassCastException` inside cleanup | The `Throwable` parameter type is too narrow for the actual error | Prefer declaring `Throwable` as the first parameter |
| Resources are still open | Cleanup only logs and does not actually call close/release | Check cleanup logic; measure resource lifecycle in tests |

### 8.1. Step-by-Step Investigation Pattern

1. Print `target.type()`, `handler.type()`, and `cleanup.type()` **before combining**.
2. Ensure the handler accepts the exception and **an argument prefix**, with the same return type as the target.
3. Ensure cleanup accepts `Throwable`, `result` if the target is not `void`, then an optional prefix, with the right return type.
4. Explicitly state the combinator order: recovery first or cleanup first; model the three paths **success / caught error / uncaught error**.
5. Check exceptions from **target**, from **handler**, and from **cleanup** separately; a cleanup error can replace the primary error.
6. Print `adapter.type()` after combining; check casts at the `invokeExact` call site. When valid type conversions are needed, use `asType` explicitly.
7. Test that resources are released **exactly once** on every execution path, including failures inside cleanup. `tryFinally` only guarantees the invocation mechanism, not that `close()` succeeds.

### 8.2. Safety and Operational Responsibility

- **Do not swallow all errors** with a generic fallback when losing connections, receiving bad data, or corrupting internal state. Only recover errors that have a valid policy.
- **Do not catch `Throwable` indiscriminately** just to keep the system from reporting errors. Some `Error`s reflect conditions where normal execution cannot continue; the handler must know its scope.
- **Cleanup should be simple, predictable, and idempotent when possible**. If cleanup throws a new exception, define precedence rules and how the initial error is recorded.
- **Do not use cleanup to trust unvalidated data**. Arguments passed to cleanup come from the caller; authorization, input validation, and isolation policies still belong at the appropriate layer.
- **Understand checked exceptions:** `MethodHandle.invokeExact`/`invoke` calls declare `throws Throwable`; the compiler does not infer the target's actual exception set from `handle.type()` alone. The example chooses `main throws Throwable` for teaching purposes.
- **Do not assume it is superior to regular Java by default:** when resources follow a lexical block, a direct `try-with-resources` block is easier to read and has clear suppressed-exception semantics. Combinators are most useful when a **dynamic invocation pipeline** needs to compose policies without being able to modify the target method.

## 9. Practice Exercises

1. **Simplify the handler:** Change `recover` to the signature `String recover(IllegalArgumentException error)`. Update `MethodType` in `findStatic`. Predict which output changes and which stays the same.
2. **Simplify cleanup:** Change `cleanup` to `String cleanup(Throwable failure, String result)`. Remove the logs using `key`/`attempt` and update `MethodType`. Prove that `recoverFirst.type()` still remains `(String,int)String`.
3. **Catch the right type:** Have the target throw `IllegalArgumentException`, then change `exType` to `RuntimeException.class`; update the handler to accept `RuntimeException` or a supertype. Observe the fallback. If you keep the handler parameter type as `IllegalArgumentException`, explain why combining can fail.
4. **Change the order:** Run both pipelines A/B with `"bad"`, and make a table of `work`/`recover`/`cleanup` in exact order. Why does only pipeline A return `fallback:bad|closed`?
5. **Error during cleanup:** Modify cleanup to always throw `IllegalStateException("close-failed")`. When the target also throws `IllegalArgumentException`, which exception reaches the caller? How can you design preserving the root cause without losing the cleanup-failure warning?
6. **The `void` type:** Replace `perform` in `CleanupEdgeDemo` with a method that throws `IllegalStateException` for a specific input value. Add logging in `performCleanup` to see `failure` non-null; determine whether there is a `result` parameter or not.
7. **Business pipeline:** A document-processing plugin can throw recoverable data errors or unrecoverable storage errors. Propose a concrete `exType`, a suitable handler, and a cleanup that releases a lease. Describe the difference between a cleanup that needs to see the original error and a cleanup that needs to see the fallback data.

## 10. Key Takeaways

- `catchException(target, exType, handler)` creates an adapter with the same `MethodType` as the target, only invokes the handler when **the target throws an exception of `exType`**, and can turn that exception into a fallback value.
- The handler receives **the exception first, then an optional prefix of the target's arguments**; it must return the exact return type of the target.
- `tryFinally(target, cleanup)` also preserves the target's `MethodType`; cleanup runs after the target on **both success and error**.
- Cleanup receives **`Throwable`**, then **result if the target does not return `void`**, then an optional argument prefix; it returns the same type as the target. When the target throws, `result` is the default value.
- `tryFinally` **does not turn an exception into a normal result**; if cleanup throws a new error, that error can replace the initial error.
- **Wrapping order matters:** `tryFinally(catchException(...), cleaner)` lets cleanup see the fallback result; `catchException(tryFinally(...), ..., handler)` lets cleanup see the error before recovery.
- Do not confuse "cleanup was called" with "the resource was closed successfully". Resources, asynchronicity, and exception policies must still be tested separately.

## Official References

- [Java SE 17 — `MethodHandles.catchException` and `MethodHandles.tryFinally`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#catchException(java.lang.invoke.MethodHandle,java.lang.Class,java.lang.invoke.MethodHandle))
- [Java SE 17 — `MethodHandles.tryFinally`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#tryFinally(java.lang.invoke.MethodHandle,java.lang.invoke.MethodHandle))
- [Java SE 17 — `java.lang.invoke.MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — `java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java Language Specification — `try / catch / finally`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20)
