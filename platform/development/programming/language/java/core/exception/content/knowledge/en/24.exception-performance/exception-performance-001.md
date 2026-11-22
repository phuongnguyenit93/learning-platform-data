# The Cost of Creating `Throwable` and Collecting Stack Traces in Java

Exceptions help Java report a failure along with diagnostic context. When creating `new IllegalStateException(...)`, the program usually does more than allocate an object and store a message string: the `Throwable` initialization mechanism also **records call stack information (stack trace)** of the current thread. This is useful when a real error needs to be investigated, but it can become a significant cost if the application creates thousands or millions of exceptions for situations that are part of normal operation.

It is important to understand **at which step the cost arises**, **what data is retained**, and **how to optimize without blindly sacrificing troubleshooting capability**. There is no single fixed nanosecond number for exception creation across all JVMs: timing depends on the exception type, stack depth, how the program runs, JVM optimizations, and logging activity.

## 1. What is `Throwable` and why can creating it be costly?

`Throwable` is the root class of the two main branches `Exception` and `Error`. An error object can have:

- **Message** (`getMessage()`): a short description, which may be `null`.
- **Cause** (`getCause()`): the `Throwable` object that led to the current error.
- **Stack trace** (`getStackTrace()`): the call frames associated with the point in time when the stack information was recorded.
- **Suppressed exceptions** (`getSuppressed()`): additional errors, commonly encountered when closing resources with `try-with-resources`.

In normal construction, `Throwable`'s constructor calls `fillInStackTrace()` to record the state of the thread's stack. The JVM must perform work to capture this information; the work typically increases when many stack frames must be traversed. Creating the message string, cause, exception-specific fields, and memory allocation also contribute to the total cost.

Therefore, code such as:

```java
IllegalArgumentException error =
        new IllegalArgumentException("quantity must be positive");
```

is an **illustrative snippet inside a method**, and the `new` expression alone may already collect stack information. That work can happen before any `throw` statement or logger is involved.

**Do not assume that `new Throwable` always forces the JVM to immediately build the entire public `StackTraceElement[]` array.** Internal recording during construction and converting data into objects/arrays for `getStackTrace()` to return are two separate steps to distinguish. Storage details, laziness, and optimizations are JVM implementation matters; developers should rely on the API contract rather than guessing internal structures.

## 2. Separating the four cost categories

| Activity | Example | Costs to observe |
| --- | --- | --- |
| Creating the exception object | `new IllegalStateException("failed")` | Allocation, field initialization, recording the stack at creation time under normal configuration |
| Throwing and propagating the error | `throw error;`, finding a matching `catch` | Control transfer, unwinding active frames, running `finally`/related resource cleanup |
| Reading/transforming stack info | `error.getStackTrace()`, `fillInStackTrace()` | Obtaining the array of stack elements, copying/materializing the representation, or re-recording the stack at a new point |
| Formatting and logging | `printStackTrace()`, `logger.error("...", error)` | Converting stack/cause/suppressed into displayable output; passing through filters, formatters, queues, outputs, or centralized systems |

These activities can appear separately or together. For example, **creating an exception and never throwing it** can still incur stack collection cost. Conversely, **rethrowing an existing object** does not automatically re-record a whole new stack, although control transfer and error-branch handling still have a cost.

`getMessage()` only retrieves the message; it does not replace a stack trace when debugging is needed. However, calling `getStackTrace()` or formatting the entire stack on every status check can also cause unnecessary allocations and work. Collect and display details where they truly serve diagnostics.

## 3. Stack traces are normally recorded at creation, not when caught

A common misconception is that `catch` or `throw` automatically captures a new stack. For exception objects created in the standard way, the stack trace is recorded at construction time, or when code explicitly calls `fillInStackTrace()` to update it.

The following example can be run with Java 17 or later.

Create the file **`ThrowableCaptureDemo.java`**:

```java
public class ThrowableCaptureDemo {
    static IllegalArgumentException createFailure() {
        return new IllegalArgumentException("invalid input");
    }

    static void throwExisting(IllegalArgumentException error) {
        throw error;
    }

    public static void main(String[] args) {
        IllegalArgumentException failure = createFailure();
        System.out.println("createdAt="
                + failure.getStackTrace()[0].getMethodName());

        try {
            throwExisting(failure);
        } catch (IllegalArgumentException caught) {
            System.out.println("sameObject=" + (caught == failure));
            System.out.println("topAfterThrow="
                    + caught.getStackTrace()[0].getMethodName());
        }

        StackTraceElement[] first = failure.getStackTrace();
        StackTraceElement[] second = failure.getStackTrace();
        System.out.println("returnedArraysDistinct=" + (first != second));

        failure.fillInStackTrace();
        System.out.println("topAfterRefresh="
                + failure.getStackTrace()[0].getMethodName());
    }
}
```

Compile and run:

```bash
javac --release 17 ThrowableCaptureDemo.java
java ThrowableCaptureDemo
```

Output:

```text
createdAt=createFailure
sameObject=true
topAfterThrow=createFailure
returnedArraysDistinct=true
topAfterRefresh=main
```

Explanation:

1. `createFailure()` is where the object is created, so the first stack element describes that method.
2. `throwExisting()` rethrows **the same existing object**; `sameObject=true`. The top stack entry is still `createFailure`, because Java does not automatically refill a new stack every time the same object is rethrown.
3. The two calls to `getStackTrace()` return separate arrays so calling code can work with an array without directly mutating the exception's internal stack storage. **Calling it multiple times is not free** in typical implementations.
4. `fillInStackTrace()` is called from `main`, so the top of the stack afterward is `main`: this method **updates** the stack information attached to the object. This is an explicit action, not what happens by default when rethrowing.

This program tests **semantics**, not runtime performance. Calling `getStackTrace()[0]` assumes an exception with writable stack enabled and call frames like the example above. If the stack is disabled, truncated, or a special exception lacks frames, the array may be empty; do not access `[0]` in general error-handling code without checking the length first.

## 4. How do stack depth and exception volume affect performance?

Imagine two call paths:

```text
main -> parse                -> new IllegalArgumentException(...)
main -> service -> workflow -> repository -> parser -> new IllegalArgumentException(...)
```

In the second case, the path has more frames. Creating the stack trace may require traversing/recording more information. However, measurements do not necessarily scale strictly linearly with frame count, because the JVM may optimize, limit depth, or use different internal representations.

In a normal processing flow, a few genuine exceptions are usually not a problem. Risk arises when a system turns **normal control flow** into continuous exception creation:

```java
try {
    return Integer.parseInt(raw);
} catch (NumberFormatException error) {
    return DEFAULT_VALUE;
}
```

This is an illustrative snippet inside a method with a `raw` variable and a `DEFAULT_VALUE` constant. If invalid input is common on a high-frequency path, many `NumberFormatException` instances will be created. Consider a validation/parsing API that returns a structured result if the business contract treats parse failure as a normal branch. However, **do not build a custom parser just to avoid exceptions** when doing so compromises correctness or maintainability; measure real load first.

Certain exceptions such as network access errors, data write failures, or invariant violations are genuinely exceptional situations. For them, keeping the stack trace usually has far greater diagnostic value than the small savings from omitting it.

## 5. What overhead do `getStackTrace()` and `printStackTrace()` add?

`Throwable.getStackTrace()` returns a **`StackTraceElement[]` array** containing call sites. Calling code can read, filter, or sort this information. Creating/copying the array and materializing stack elements in JVM implementations can cause additional allocations; developers should not assume that reading the stack via this API is as trivial as reading a `boolean` field.

Example:

```java
for (StackTraceElement frame : error.getStackTrace()) {
    if (frame.getClassName().startsWith("com.example.")) {
        System.out.println(frame);
    }
}
```

This is an illustrative snippet inside a method that already has `Throwable error`, not a complete program. If placed in a repeated error-handling loop, repeatedly converting the entire stack into an array just to select a few frames can cause unnecessary overhead.

`printStackTrace()` must also build a human-readable representation including the exception name, message, stack frames, and `Caused by:`/`Suppressed:` information. Printing to the console, a file, a socket, or a log collector can take more time and cause more resource contention than creating the exception itself — depending on the platform and configuration.

If you only need the current call site and **do not want to create an exception just to obtain the stack**, Java 9+ provides `StackWalker`:

```java
String caller = StackWalker.getInstance().walk(stream ->
        stream.findFirst()
                .map(frame -> frame.getClassName()
                        + "#" + frame.getMethodName())
                .orElse("unknown"));
```

This snippet illustrates usage inside a method. `StackWalker` allows walking the current thread's stack frames on demand, though walking the stack **still has a cost** and does not replace `Throwable` when you need to preserve the cause of an error that already occurred. When you need the stack of a **previously created exception**, walking the current stack cannot reconstruct the exact stack from the time of the error.

## 6. Reducing cost with custom exceptions that do not record a stack

Java has a `protected` constructor on `Throwable` and subclasses such as `RuntimeException`:

```java
RuntimeException(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace);
```

The signature above is an **API description**, not a valid constructor call from code outside `RuntimeException`. A custom exception class can call `super(message, cause, enableSuppression, writableStackTrace)` to decide whether to record the stack and whether to allow suppressed exceptions.

Create the file **`StackTraceOptionsDemo.java`**:

```java
public class StackTraceOptionsDemo {
    static final class NormalFailure extends RuntimeException {
        NormalFailure(String message) {
            super(message);
        }
    }

    static final class LightweightSignal extends RuntimeException {
        LightweightSignal(String message) {
            super(message, null, false, false);
        }
    }

    public static void main(String[] args) {
        RuntimeException normal = new NormalFailure("expected");
        RuntimeException lightweight = new LightweightSignal("expected");

        normal.addSuppressed(new IllegalStateException("cleanup"));
        lightweight.addSuppressed(new IllegalStateException("cleanup"));

        System.out.println("normalHasStack="
                + (normal.getStackTrace().length > 0));
        System.out.println("lightweightStackLength="
                + lightweight.getStackTrace().length);
        System.out.println("normalSuppressed="
                + normal.getSuppressed().length);
        System.out.println("lightweightSuppressed="
                + lightweight.getSuppressed().length);

        lightweight.fillInStackTrace();
        System.out.println("lightweightAfterFill="
                + lightweight.getStackTrace().length);
        System.out.println("lightweightMessage="
                + lightweight.getMessage());
    }
}
```

Compile and run:

```bash
javac --release 17 StackTraceOptionsDemo.java
java StackTraceOptionsDemo
```

Output:

```text
normalHasStack=true
lightweightStackLength=0
normalSuppressed=1
lightweightSuppressed=0
lightweightAfterFill=0
lightweightMessage=expected
```

The `LightweightSignal` class disabled **both** stack recording and suppression with the two `false` arguments. As a result, `getStackTrace()` returns an empty array, `fillInStackTrace()` does not record a stack, and `addSuppressed(...)` does not store attached exceptions. The `"expected"` message is still present.

These two flags are **semantically independent**: if you only want to disable the stack trace while keeping suppressed exceptions, the constructor can use `super(message, cause, true, false)`. The example above intentionally disables both to show that reducing diagnostic data should be an explicit, deliberate decision.

**Important trade-off:** an object without a stack trace is hard to trace back to where it was created. Do not use `writableStackTrace=false` broadly for unexpected exceptions, programming bugs, data corruption, or errors requiring post-incident analysis. Only consider it for a **well-defined signal that occurs frequently and can be diagnosed through other information**. When using such a class, document the rationale and ensure maintainers do not mistake it for a critical failure.

## 7. Should you override `fillInStackTrace()` to return `this`?

A technique sometimes used is overriding:

```java
@Override
public synchronized Throwable fillInStackTrace() {
    return this;
}
```

This snippet **illustrates an overridden method in a `Throwable` subclass**, not a standalone program. In appropriate cases, it prevents the stack-recording step performed by `fillInStackTrace()`. However, the outcome depends on how the class is constructed, inheritance contracts, and diagnostic needs. Java already provides a constructor to disable `writableStackTrace`; prefer expressing this directly via the constructor when your exception class supports it.

In particular, do not override it just to "speed up" every exception before proving it is a hot path. Missing the error location can dramatically increase incident investigation time. You should also avoid using a **singleton `Throwable`** and rethrowing it from multiple threads just to save allocations: the stack tied to the original creation site is misleading, some exception state is mutable, and a shared object loses the per-occurrence context of each error.

## 8. `throw` does not automatically re-capture the stack, but exception handling still does work

A `throw` statement on an existing object usually does not repeat the work of `new Throwable()`. It transfers control flow to the appropriate handler, which may involve unwinding multiple frames, executing `finally`, releasing resources in `try-with-resources`, and running error-handling branches.

Therefore, avoid two extreme conclusions:

- "If you only rethrow, it's completely free." **False**: there is still the cost of control transfer, executing handler code, and related side effects.
- "Every `try/catch` is slow even when no error occurs." **Do not make that claim**. The main cost usually lies on the throwing and exception-handling path, not the mere presence of `try` syntax around a successful path. The JVM can optimize normal paths very well; measure rather than removing necessary error-handling structures.

Behavior also depends on the error type: there are JVM-generated exceptions (such as certain bytecode-operation errors) and exception objects created by application code with `new`. HotSpot has special optimizations for some JVM-thrown exceptions that occur repeatedly at the same site, which under certain conditions can omit stack information. This is an **implementation detail, not a general guarantee of the Java language**; do not rely on it when designing logging or predicting whether a stack trace will always be present or absent. If verification is needed, check the exact JVM version and current configuration.

## 9. Measure performance properly instead of assigning a fixed number

A poorly designed microbenchmark can easily lead to the false conclusion that `Throwable` "costs exactly X ns" or "disabling the stack is always Y times faster." Measurements are affected by:

- **Warm-up/JIT**: initial invocations differ from later ones after the code has been optimized and compiled.
- **Dead-code elimination / escape analysis**: unused results may be optimized away, making you think you are measuring object creation when you are actually not.
- **Stack depth**: creating an exception at depth 2, 20, or 100 can yield different results.
- **Exception class**: custom constructors and fields can change the amount of work.
- **Whether `getStackTrace()` is called**: merely constructing a `Throwable` differs from retrieving the stack array.
- **Whether it is formatted/logged to a real device**: formatter, synchronization, buffering, I/O, and drop/sampling policies can dominate the rest of the operation.
- **JVM environment**: JDK build, GC, CPU, VM flags, other work on the machine, and load profile.

For serious investigation, use **JMH (Java Microbenchmark Harness)** or a profiler with a clear methodology, reporting percentiles/variance where appropriate and allocation rates (e.g., bytes/op) if the tool supports it. Do not run a short `System.nanoTime()` loop and treat the result as universal.

You can split experiments into independent branches:

| Test | Goal | What to control |
| --- | --- | --- |
| `new NormalFailure(...)` | Cost of creating an exception with stack | Keep call depth constant, consume the object |
| `new LightweightSignal(...)` | Cost of creating an exception without stack | Same work and data, clearly note stack was sacrificed |
| `failure.getStackTrace()` | Cost of reading the stack array | Separate from object creation time |
| `failure.printStackTrace(writer)` | Cost of building text representation | Use an appropriate writer, isolate or separately report I/O |
| Logging with a Throwable | End-to-end logging pipeline cost | Explicit backend config, log level, sink, and sampling |

If JMH is needed, a minimal benchmark is typically structured as follows (this is an **outline**; it requires JMH dependencies/imports, state, and configuration, and is not a standalone runnable class):

```java
@Benchmark
public void constructThrowable(org.openjdk.jmh.infra.Blackhole sink) {
    sink.consume(new IllegalStateException("expected"));
}

@Benchmark
public void materializeStack(org.openjdk.jmh.infra.Blackhole sink) {
    sink.consume(existingThrowable.getStackTrace());
}
```

In the second branch, `existingThrowable` must be state created outside the measured method so you measure reading the stack rather than accidentally including construction. Design state appropriately for the thread count and avoid uncontrolled sharing of mutable state. JMH is an external library outside the JDK and is not included automatically just by using Java 17.

In real applications, combine microbenchmarks with profilers and metrics: exception rate per request, CPU cost of `Throwable.fillInStackTrace`, total bytes allocated, GC frequency, request latency, and log volume. An optimization that speeds up a microbenchmark will not necessarily improve system latency if the real bottleneck is I/O or locks.

## 10. Techniques to reduce overhead while preserving diagnostics

**(1) Do not use exceptions to replace expected result branches.** For example, check normal business conditions and return a structured result (`Optional`, status enum, dedicated result type) instead of throwing an exception for every not-found lookup, if the API contract treats "not found" as a normal outcome. For unexpected deviations, exceptions remain the right mechanism.

**(2) Do not create an exception just to get the caller name when a suitable API exists.** If the goal is the current stack or a specific caller, look at `StackWalker` or framework metadata/tracing mechanisms. Walking the stack still has a cost; measure and only do it where needed.

**(3) Keep the `Throwable` object when logging important errors.** With SLF4J, an illustrative call in an application with a logger is:

```java
logger.error("Failed to process order {}", orderId, exception);
```

This snippet requires SLF4J, `logger`, `orderId`, and `exception`. It passes the full exception to the backend so the stack/cause can be recorded; calling `exception.getMessage()` and discarding `exception` loses diagnostic data. If log volume is high, control log levels, rate limits, sampling, or aggregation at processing boundaries. Do not disable stack traces on serious errors just to save log bytes.

**(4) Choose the right logging point.** An error passing through repository → service → API can end up logged three times; it is usually better to log once where full context and handling responsibility reside, and propagate the error state through other layers. If a layer handles the error and returns a fallback, logging there may be more useful.

**(5) Do not catch and throw a new exception while losing the cause.** If wrapping is needed, use a constructor that preserves the cause, e.g., `new IllegalStateException("Could not save order", cause)`. If every layer unnecessarily calls `new ...`, the program both pays the cost of creating a new stack and makes the cause chain harder to read.

**(6) Avoid retrieving the stack multiple times.** If you need to inspect the stack to classify a specific error, read it once into a variable and process it as needed; avoid calling `getStackTrace()` repeatedly inside a loop looking for an element. Do not extract the full stack just to decide a log level if a more accurate business signal is available.

**(7) Only choose stackless exceptions after evaluating semantics.** A `LightweightSignal` can make sense for internal cancellation/control mechanisms with a dedicated contract. However, if external callers might treat it as an error requiring investigation, losing the stack can be costly.

**(8) Monitor asynchronous logging.** Logging backends can defer formatting or push events onto a queue, reducing caller-thread blocking in some configurations; this does not eliminate exception creation cost, does not remove total formatter/I/O work, and can create memory pressure or drop events depending on queue policy. Measure the whole system.

## 11. Stack trace cost and completeness in practice

There are situations where you should not assume every `Throwable` has a detailed stack trace:

1. **Writable stack trace disabled**: the four-argument constructor with `writableStackTrace=false` skips filling the stack; `getStackTrace()` returns an empty array.
2. **Code explicitly alters the stack**: `fillInStackTrace()` re-records at the current site, and `setStackTrace(...)` can change what stack is returned for an object with a writable stack. Do not edit the stack just to make logs look nicer without a clear technical reason.
3. **JVM limits/characteristics**: the stack may be limited, truncated, or absent in special VM cases; some optimizations for JVM-generated exceptions do not necessarily apply to user-created `new` exceptions.
4. **Severe errors**: when the JVM runs out of memory or the stack overflows, the system may lack resources to create and print logs normally. A complete stack trace cannot be treated as an absolute guarantee in all scenarios.
5. **Asynchronous task boundaries**: an exception's stack on a worker thread reflects the worker's context; when `CompletableFuture.join()` or `Future.get()` reports the failure to another thread, the wrapper and cause may carry different stacks. Preserve the cause and correlation IDs to connect contexts.

When analyzing performance, the number of frames in a trace does not always equal the full business history of a request. A stack describes the state of **one thread at the time the stack was recorded**, and does not automatically stitch together a request's path across multiple threads or message queues. Distributed tracing and correlation IDs supply that information, though they have their own costs.

## 12. Common misconceptions

| Misconception | Why it is inaccurate | Better understanding/practice |
| --- | --- | --- |
| "`throw` is when Java creates the stack trace." | `Throwable` construction usually already records the stack | Distinguish creating an exception from throwing an existing object |
| "`catch` always adds the catch site to the stack." | Catching an error does not automatically refill the stack | Use the existing cause and trace; only call `fillInStackTrace()` if you intentionally want to update it |
| "`getMessage()` is enough and cheaper, so always log only that." | Loses the error type, stack, cause, and suppressed exceptions | For errors needing diagnostics, pass the full `Throwable` to the logger |
| "`new Exception()` and `new Object()` have the same cost." | Exceptions typically include stack recording and extra metadata | Measure `Throwable` creation separately |
| "Calling `getStackTrace()` allocates nothing extra." | The API returns an array and may need to convert internal representations | Avoid pointless repeated calls; measure on your JVM |
| "Disabling stack traces for all errors is a guaranteed optimization." | Loses the failure origin and reduces diagnostic value | Only consider for expected signals with a dedicated contract |
| "A stackless `Throwable` cannot have a message or cause." | The writable-stack flag and other fields are independent | Check the constructor and retained data |
| "A short microbenchmark is enough to quantify production cost." | JIT, GC, stack depth, I/O load, and loggers can all change results | Combine JMH, profilers, and production metrics |
| "Reusing a singleton exception is always safe." | Each throw site's context differs and the object has mutable state | Avoid sharing mutable errors when per-occurrence tracing is needed |
| "Logging only costs anything if the ERROR level is enabled." | The `Throwable` object may already be constructed even if the log is filtered | Avoid creating exceptions just for unnecessary log messages |

## 13. Self-check scenarios

**Scenario A.** A function creates an `IllegalStateException` in method `create()`, and another function rethrows that object. Which location does the top frame of the default stack usually point to?  
**Answer:** Where the exception was created or most recently filled (`create()`), not necessarily the later `throw` site.

**Scenario B.** You call `error.fillInStackTrace()` at a new point. What changes?  
**Answer:** For a throwable with a writable stack, the stack information is updated to the thread's state at the call site. Doing so can lose the trace of the original creation site if the previous context is not preserved.

**Scenario C.** You use `super(message, null, true, false)` in a custom exception constructor. What happens to `getStackTrace()` and suppression?  
**Answer:** The stack is disabled; `getStackTrace()` is empty. Suppression is still enabled by the `true` argument, so suppressed exceptions can be added.

**Scenario D.** An endpoint returns many expected input validation errors per second. Should you replace all of them with stackless exceptions?  
**Answer:** First evaluate whether input errors are a normal API outcome that can be returned via a suitable result/status type. If exceptions must be kept, only disable the stack after measuring and confirming that stack information is not needed for diagnostics.

**Scenario E.** On every error, the program calls `getStackTrace()` inside a loop to find the first application method. What is worth reviewing?  
**Answer:** Repeatedly reading it can cause redundant work and allocations. You can fetch the array once and iterate over it, or use another API suited to the goal.

**Scenario F.** `logger.error("Bad: {}", new RuntimeException("x"))` is on a code path meant only for per-request debug logging. Even if the logger disables that level, is creating `RuntimeException` free?  
**Answer:** It cannot be assumed free: the exception-creation expression is evaluated before calling the logger, unless the entire branch is guarded/avoided or specifically optimized. Do not create throwables just to decorate routine log messages.

**Scenario G.** A JMH optimization shows that omitting the stack reduces allocations, but production failures become harder to investigate. What is the right decision?  
**Answer:** Weigh the real workload benefit against the loss of diagnostic information. Keep traces for unexpected errors; optimize by changing control flow, rate-limiting logs, or using lightweight exceptions only for signals that can genuinely be diagnosed without a stack.

## 14. References

- [Java 17 `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `fillInStackTrace`, `getStackTrace`, `printStackTrace`, `getSuppressed`, and the constructor with `writableStackTrace`.
- [Java 17 `RuntimeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): the `protected` constructor used in custom exception classes.
- [Java 17 `StackWalker`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.html): reading the current thread's stack frames on demand.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): JVM microbenchmarking toolset with warm-up and optimization controls.

Key takeaway: **creating a `Throwable` typically incurs extra work to record the stack; `getStackTrace()` and logging can add further cost; rethrowing the same object does not automatically capture a new stack.** Keep traces for errors that need investigation, measure in realistic environments, and only reduce or omit stack traces in cases with a clear contract.