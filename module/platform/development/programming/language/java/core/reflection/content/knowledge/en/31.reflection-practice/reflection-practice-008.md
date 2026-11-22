# Practice: Dynamic Proxy for Timing Execution and Preserving Target Exceptions

## 1. Problem Statement and Completion Criteria

Suppose a Java service has an interface `Job`. We want to wrap each call to the service with a **JDK dynamic proxy** to measure execution time, record success/failure status, and **not distort exceptions thrown by the target code**.

These are two separate concerns:

- **Timing:** capture `System.nanoTime()` before forwarding the call, and compute the elapsed time in `finally` so both success and failure paths are always recorded.
- **Preserving exceptions:** when invoking target code via `Method.invoke`, Java Reflection wraps any `Throwable` thrown by the target method inside `InvocationTargetException`. The handler must **extract `getCause()` and rethrow that exact object**, provided it complies with the proxy interface contract.

After this lesson, you will be able to build the proxy, verify the result/identity of `IOException`, `RuntimeException`, and `Error`, understand when `UndeclaredThrowableException` appears, and recognize risks when logging code alters business exceptions.

**Scope:** JDK 17+; `java.lang.reflect.Proxy` wraps only **interfaces**. The example uses no external libraries; for a concrete class without an interface, you need a different approach such as a manual decorator or an appropriate bytecode proxy tool.

## 2. Execution Flow of `InvocationHandler`

When the application calls `proxy.execute("A")`:

~~~text
Caller
  |
  v
Proxy implements Job
  |
  v
InvocationHandler.invoke(proxy, method, args)
  |
  +--> start = System.nanoTime()
  |
  +--> method.invoke(realTarget, args)
  |       |
  |       +--> normal return ---------> return result
  |       |
  |       +--> target throws ---------> InvocationTargetException
  |                                         |
  |                                         +--> throw ex.getCause()
  |
  +--> finally: elapsed = System.nanoTime() - start
  |              record method name, elapsed, status
  |
  v
Caller receives result or original exception
~~~

`InvocationHandler.invoke(Object proxy, Method method, Object[] args)` declares `throws Throwable`. This lets the handler rethrow checked exceptions, unchecked exceptions, and `Error`s **without forcing them into `RuntimeException`**.

Parameters:

| Parameter | Meaning | Notes |
| --- | --- | --- |
| `proxy` | The proxy instance being invoked | **Do not** call the same method back on `proxy` to delegate; easily causes infinite recursion |
| `method` | The `Method` object for the dispatched call | May be declared on a parent interface or be an `Object` method |
| `args` | Argument values, boxed if primitive | May be `null` when the method takes no parameters |
| Return value of `invoke` | Value sent back to the caller through the proxy | Must be compatible with the return type; `void` methods receive `null` |

Core pattern:

~~~java
long started = System.nanoTime();
try {
    return method.invoke(target, args);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordTime(method, elapsedNanos);
}
~~~

This is a **fragment**, assuming `target`, `method`, `args`, and `recordTime` already exist. The practice section below provides the complete program.

## 3. Why Must `InvocationTargetException` Be Unwrapped?

`java.lang.reflect.Method.invoke` uses Reflection to call the target method. If the target code executes:

~~~java
throw new IOException("disk offline");
~~~

then a direct Java call receives `IOException`; whereas `method.invoke(target, args)` throws **`InvocationTargetException`**, with `getCause()` pointing to the original `IOException`.

If a handler is written incorrectly:

~~~java
// Wrong when trying to preserve Job's exception contract
(proxy, method, args) -> method.invoke(target, args)
~~~

`InvocationTargetException` is a **checked exception**. If the interface method only declares `throws IOException`, the proxy cannot legally throw an `InvocationTargetException` from the handler as a valid checked exception. The proxy call will then typically throw `UndeclaredThrowableException`, burying the business exception under multiple wrapper layers.

The right way is:

~~~java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
}
~~~

Key properties of `throw ex.getCause()`:

1. Rethrows the **exact `Throwable` object** thrown by the target method; does not change the message or create a new exception instance.
2. Preserves the cause and suppressed exceptions attached to the original object.
3. Callers can continue catching `IOException`, `IllegalStateException`, or `AssertionError` according to the contract.
4. Do not unwrap every `getCause()` unconditionally. If **the target code itself actually threw a wrapper** such as `CompletionException`, that is the target code's behavior; an interceptor should not arbitrarily strip that wrapper away.

`Method.invoke` itself can raise errors due to bad arguments, insufficient access, or a wrong receiver. Errors occurring **before the target method runs** are not `InvocationTargetException`s representing business failures, and must be diagnosed separately.

## 4. Complete Java 17+ Program: Timing Proxy Preserving All Three Throwable Kinds

Create a file named **`TimedProxyDemo.java`**:

~~~java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class TimedProxyDemo {
    public interface Job {
        String execute(String input);
        void failChecked() throws IOException;
        void failRuntime();
        void failError();
    }

    public static final class RealJob implements Job {
        final IOException checked = new IOException("disk offline");
        final IllegalStateException unchecked =
                new IllegalStateException("bad state");
        final AssertionError error = new AssertionError("fatal");

        public String execute(String input) {
            return "done:" + input;
        }

        public void failChecked() throws IOException {
            throw checked;
        }

        public void failRuntime() {
            throw unchecked;
        }

        public void failError() {
            throw error;
        }
    }

    record Sample(String method, long nanos, boolean succeeded) {}

    static <T> T timedProxy(Class<T> contract, T target, List<Sample> samples) {
        if (!contract.isInterface() || !contract.isInstance(target)) {
            throw new IllegalArgumentException("Wrong contract or target");
        }

        Object proxy = Proxy.newProxyInstance(
                contract.getClassLoader(),
                new Class<?>[] { contract },
                (self, method, args) -> {
                    // Object methods are handled explicitly and not measured in this example.
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "toString" ->
                                    "TimedProxy(" + contract.getSimpleName() + ")";
                            case "hashCode" -> System.identityHashCode(self);
                            case "equals" -> self == args[0];
                            default ->
                                    throw new UnsupportedOperationException(
                                            method.toString());
                        };
                    }

                    long start = System.nanoTime();
                    boolean succeeded = false;
                    try {
                        Object result = method.invoke(target, args);
                        succeeded = true;
                        return result;
                    } catch (InvocationTargetException ex) {
                        // Preserve the exact IOException, RuntimeException,
                        // or Error thrown by the target method.
                        throw ex.getCause();
                    } finally {
                        long nanos = System.nanoTime() - start;
                        samples.add(new Sample(method.getName(), nanos, succeeded));
                    }
                });

        return contract.cast(proxy);
    }

    public static void main(String[] args) {
        RealJob target = new RealJob();
        List<Sample> samples = new ArrayList<>();
        Job proxy = timedProxy(Job.class, target, samples);

        System.out.println(proxy.execute("A"));

        try {
            proxy.failChecked();
        } catch (IOException ex) {
            System.out.println("checked preserved: "
                    + (ex == target.checked));
        }

        try {
            proxy.failRuntime();
        } catch (IllegalStateException ex) {
            System.out.println("runtime preserved: "
                    + (ex == target.unchecked));
        }

        try {
            proxy.failError();
        } catch (AssertionError ex) {
            System.out.println("error preserved: "
                    + (ex == target.error));
        }

        System.out.println(proxy);
        System.out.println("samples: " + samples.stream()
                .map(s -> s.method() + ":"
                        + (s.succeeded() ? "ok" : "fail"))
                .toList());
        System.out.println("durations recorded: " + samples.stream()
                .allMatch(s -> s.nanos() >= 0));

        for (Sample s : samples) {
            System.out.printf("timing %s: %d ns%n",
                    s.method(), s.nanos());
        }
    }
}
~~~

Compile/run commands (from the directory containing the file):

~~~bash
javac --release 17 TimedProxyDemo.java
java TimedProxyDemo
~~~

**Fixed output portion, verified with OpenJDK 21 and `javac --release 17`:**

~~~text
done:A
checked preserved: true
runtime preserved: true
error preserved: true
TimedProxy(Job)
samples: [execute:ok, failChecked:fail, failRuntime:fail, failError:fail]
durations recorded: true
~~~

Then the program prints four timing lines, for example:

~~~text
timing execute: 2029596 ns
timing failChecked: 1850957 ns
timing failRuntime: 164227 ns
timing failError: 69275 ns
~~~

**The numbers above are from a single run**; they are not fixed stdout values. On another machine or run, timings vary with JIT, scheduler, GC, and system load. The correctness of the lesson does not depend on specific nanosecond numbers.

## 5. Why Does the Program Truly Preserve Exceptions?

`RealJob` pre-allocates three error objects and stores them in the `checked`, `unchecked`, and `error` fields. The corresponding methods throw **those exact created objects**, so the check:

~~~java
ex == target.checked
~~~

proves the **identity** of the exception is preserved, not merely that it happens to share the same class or message.

Four cases:

| Call | Target behavior | Caller observes | Timing record |
| --- | --- | --- | --- |
| `execute("A")` | Returns `done:A` | Receives result string | `succeeded=true` |
| `failChecked()` | Throws `IOException` | Catches the original `IOException` directly | `succeeded=false` |
| `failRuntime()` | Throws `IllegalStateException` | Catches the original unchecked exception | `succeeded=false` |
| `failError()` | Throws `AssertionError` | Catches the original `Error` | `succeeded=false` |

Every branch passes through `finally`. This guarantees a record is written even when business logic fails, **provided that metric recording itself does not throw an exception disrupting the flow**. When using a real logger/metric backend, guard the recording operation against new exceptions so business errors are not masked.

`succeeded` is set to `true` **only after `Method.invoke` returns normally**. It describes the status of the **target method invocation**, not necessarily the outcome of any outer adapter: the proxy may still need to cast/unbox the return value per the signature. Therefore, do not use this flag to declare that an entire HTTP request/transaction committed successfully.

## 6. Measuring Time Properly

### 6.1. Use `System.nanoTime()`, not the wall-clock time

`System.nanoTime()` is suited for computing **elapsed duration**:

~~~java
long start = System.nanoTime();
try {
    return method.invoke(target, args);
} finally {
    long elapsedNanos = System.nanoTime() - start;
}
~~~

- A single value of `nanoTime()` is **not** a calendar timestamp; do not convert it directly to date/time.
- Take the **difference** between two readings within the same JVM; never compare `nanoTime` timestamps across two JVMs.
- Its unit of representation is nanoseconds, **without guaranteeing one-nanosecond hardware resolution**.
- Placing the start mark before `method.invoke` means the duration includes **Reflection invocation overhead and dispatch inside the method**, not pure business CPU time.
- For async calls returning `CompletableFuture` or `Mono`, this time may only measure **work initiation**; to measure until completion, hook into the moment the task actually finishes.

Convert units for display (without inaccurate rounding from double division):

~~~java
long micros = java.util.concurrent.TimeUnit.NANOSECONDS.toMicros(elapsedNanos);
long millis = java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

This statement is a fragment requiring the `elapsedNanos` variable. Use an elapsed-time clock for operational timing; use `Instant.now()` or a logging timestamp when recording **when an event occurred**.

### 6.2. `finally` is necessary, yet not immune to errors

Putting logging in `finally` runs whether the target returns or throws. However, if `samples.add(...)`, a metric backend, or a logger **itself throws an exception**, the new exception from `finally` can **overwrite** the business result or exception.

To ensure logging failures do not mask business exceptions in normal cases, you can isolate a *best-effort* sink:

~~~java
// Fragment inside finally, assuming metricSink.record(...) is available.
long elapsed = System.nanoTime() - start;
try {
    metricSink.record(method.getName(), elapsed, succeeded);
} catch (RuntimeException loggingFailure) {
    // Log telemetry's own failure to another safe channel if available.
    // Do not throw the logger's error over the business exception.
}
~~~

This is only a **policy template**: in production, proactively decide how to detect and monitor telemetry failures; do not stay silent forever when logging breaks. Catching `RuntimeException` here does not protect against severe `Error`s (such as out-of-memory), nor is it an absolute guarantee that nothing can ever mask the original error.

In the single-threaded demo, `ArrayList` suffices. If the proxy is called concurrently, **do not share an unsynchronized `ArrayList`**; choose `ConcurrentLinkedQueue<Sample>`, `CopyOnWriteArrayList` (only if write frequency fits), or a thread-safe metrics system.

## 7. Checked Exception Rules at the Proxy Boundary

`InvocationHandler.invoke` can `throw Throwable`, yet the generated proxy class must obey the contract of the **interface method**.

| Handler throws | Interface method declares | Caller receives |
| --- | --- | --- |
| `IOException` | `throws IOException` (or compatible supertype) | Original `IOException` |
| `IOException` | Does not declare compatible checked exception | `UndeclaredThrowableException` wrapping `IOException` |
| `IllegalStateException` | With or without `throws` | Original unchecked exception |
| `AssertionError` | With or without `throws` | Original `Error` |
| Unwrapped `InvocationTargetException` | Only `throws IOException` | Typically `UndeclaredThrowableException` wrapping `InvocationTargetException` |

Therefore, **unwrapping the Reflection wrapper is a necessary condition, not a sufficient condition** for every checked exception to emerge untouched. The interface must permit that exception type.

Example of a handler intentionally throwing an undeclared checked exception:

~~~java
interface NoChecked {
    void work();
}

NoChecked proxy = (NoChecked) Proxy.newProxyInstance(
        NoChecked.class.getClassLoader(),
        new Class<?>[] { NoChecked.class },
        (p, m, a) -> { throw new java.io.IOException("I/O"); });

try {
    proxy.work();
} catch (java.lang.reflect.UndeclaredThrowableException ex) {
    System.out.println(ex.getUndeclaredThrowable().getClass().getSimpleName());
}
~~~

This is a **Java 17+ fragment** to place in a suitable method with `Proxy` imported or fully qualified. It prints `IOException`; `getUndeclaredThrowable()` references the checked exception thrown by the handler.

If a proxy implements **multiple interfaces with the same method name/parameters**, the allowed checked exceptions are those satisfying the `throws` clauses of **all** matching declarations, not just the first interface in the list. This can cause an exception to be wrapped in `UndeclaredThrowableException` even when one individual interface declares it.

**Recommendation:** write proxies against clear interface contracts; do not "fix" undeclared exceptions by forcing all errors into `RuntimeException` if the goal is preserving target-code semantics.

## 8. Handling `equals`, `hashCode`, and `toString`

A JDK dynamic proxy also routes the three public, non-final methods of `Object` into `InvocationHandler`. For them, `method.getDeclaringClass() == Object.class`.

If the handler uses:

~~~java
return method.invoke(proxy, args); // Wrong: invokes the proxy itself again!
~~~

then the new call re-enters the same handler and can lead to infinite recursion/`StackOverflowError`.

The demo chooses a **proxy identity** policy:

- `equals(other)` returns `self == other`.
- `hashCode()` returns `System.identityHashCode(self)`.
- `toString()` returns `TimedProxy(Job)`.
- Does not time these `Object` calls; the `Sample` list contains only business methods.

Another decorator might choose to delegate `Object` calls to the target, but must weigh **equality symmetry, transitivity**, and the hash contract. Do not assume `target.equals(proxy)` will hold if `proxy.equals(target)` is decided by a custom handler; `equals`/`hashCode` consistency is what matters.

## 9. Do Not Lose Error Information When Logging

An error-observing interceptor must separate **business cause** from **measurement system errors**.

Practices to follow:

1. **Do not recreate exceptions** just to log: `throw new IOException(ex.getMessage())` loses identity, the original stack trace, and potentially cause/suppressed exceptions.
2. **Do not use `throw new RuntimeException(ex)`** when the interface has a checked exception contract that callers need to catch directly.
3. **Do not write `catch (Exception ex) { return null; }`**: it both swallows errors and causes a `NullPointerException` later if the method returns a primitive.
4. **Do not forget `finally`**: if metrics are recorded only after `return method.invoke(...)`, throwing branches go unmeasured.
5. **Avoid logging sensitive data in `args` or return values**; this practice exercise records only method name and duration.
6. **Do not re-invoke the business method** to "retry timing" unless retry is an independent, explicitly decided contract. Calling twice can duplicate side effects.
7. **Do not label an async task "succeeded"** merely because it returned a future; the result may fail later.

When correlation is needed in multi-request applications, attach a trace/request ID to metrics, rather than calling `proxy.toString()` inside the handler itself to format log messages.

## 10. Typical Mistakes When Using `Method.invoke`

### 10.1. Invoking on the wrong receiver

A `method` forwarded by a proxy is usually a method on an **interface**. `target` must implement the corresponding interface; passing an incompatible instance causes Reflection to throw `IllegalArgumentException`. `timedProxy` checks upfront using:

~~~java
contract.isInterface() && contract.isInstance(target)
~~~

to catch misconfiguration before creating the proxy. This check does not replace full verification of class loaders, interface/module visibility, or method accessibility.

### 10.2. Method overloads and metric identification

`method.getName()` suffices for demonstrating the example, yet **does not distinguish** overloads such as `run(String)` and `run(int)`. For proper telemetry, keys may need:

~~~java
String signature =
        method.getDeclaringClass().getName()
        + "#" + method.getName()
        + java.util.Arrays.toString(method.getParameterTypes());
~~~

This is a fragment; you can add return type or module/classloader identity in systems with multiple proxy kinds if metric identification genuinely needs them. Avoid creating per-request input-specific labels because high cardinality exhausts metric backend memory.

### 10.3. `null` and primitive types

When an interface method takes no arguments, `args` may be `null`; `Method.invoke(target, args)` validly accepts a null argument array for zero-parameter methods. When a method returns `void`, Reflection returns `null`. Conversely, if a handler returns `null` for a proxy method declared to return `int`, the proxy can throw `NullPointerException` during unboxing; that is an adapter bug, not an exception from the target method.

### 10.4. Access permissions

`Method.invoke` still obeys Java access checks and JPMS encapsulation. Creating a proxy does not automatically open private packages or bypass `IllegalAccessException`. When using a public interface whose implementation or lookup is in another module, ensure proper receiver, declaring type, and visibility. The demo intentionally uses `public interface Job` and `public static final class RealJob` to avoid permission-related noise.

## 11. Tests with Practical Value

Instead of only checking exception class names, verify **object identity** and recorded telemetry:

| Case | What to verify |
| --- | --- |
| Returning call | Correct value and exactly one successful timing record |
| Declared checked exception | Caller catches the exact type directly, `caught == original` |
| Runtime exception | Caller catches the exact original object, unwrapped |
| `Error` | Caller receives the exact `Error`, timing still recorded |
| `Object.toString` | No infinite recursion, matches defined logging policy |
| Metric sink failure | Does not replace the business exception when logging errors can be handled |
| Two overloaded methods | Metric key distinguishes them if signature-level observation is required |
| Concurrent calls | Thread-safe data sink and counters, no lost records |
| Multiple interfaces with overlapping methods | Checked exceptions must satisfy every contract |

In the demo, `checked preserved: true` is stronger proof than printing `IOException`. For performance benchmarking, run multiple iterations and use **JMH** when quantitative conclusions are needed; the short example only demonstrates the timing logic flow, not stable nanosecond figures or proxy overhead.

## 12. Advanced Scenarios and Design Limits

**Nested proxies:** If the target is itself another proxy, total time at the outer layer includes the inner layer. If the inner layer alters/wraps an exception, the outer handler only sees the exception actually thrown by the target proxy; you cannot reliably recover a "deeper exception" without knowing multi-layer contracts.

**Default methods:** Calls to interface default methods are also routed to the handler. `Method.invoke(target,args)` is only right when you **intentionally delegate to a target** implementing the interface. If you want to execute the default body **on the proxy itself** in Java 17, see `InvocationHandler.invokeDefault` and its specific access/override conditions; do not call the default method back on the proxy as a delegate call.

**`MethodHandle`:** You can use `MethodHandle` instead of `Method.invoke` on some call paths after setting up proper lookup/access. `MethodHandle` generally propagates target exceptions without wrapping them in `InvocationTargetException` like `Method.invoke`, yet you must still preserve exception contracts, measure timing, and handle adapter errors.

**Spring AOP:** Timing can be done with around advice using `ProceedingJoinPoint.proceed()`, where join-point exceptions can pass through via `throws Throwable`. Unwrapping rules differ across proxy/advice implementations; **do not unconditionally apply** `InvocationTargetException` unwrapping in every framework — only when you invoke `Method.invoke` yourself.

**Async/reactive:** To measure end-to-end business completion rather than just returning a future/reactive publisher, design metrics at completion/error/subscribe hooks suited to the concurrency model. Never "block" async calls just to reuse the synchronous interceptor in this example.

## 13. Self-Check Questions

1. Why does `method.invoke` make callers see unexpected exceptions if the handler does not unwrap? Because exceptions from the target method are wrapped in `InvocationTargetException`, and the proxy may wrap them further in `UndeclaredThrowableException`.
2. What is the right way to preserve the original throwable? **`catch (InvocationTargetException ex) { throw ex.getCause(); }`**.
3. Why is preserving a checked exception not guaranteed when the interface lacks a matching `throws` clause? Because the proxy bytecode must respect the interface's checked exception contract; undeclared cases are wrapped in `UndeclaredThrowableException`.
4. Is using `System.nanoTime()` to capture the "date/time a method was called" right? **No**; it measures elapsed intervals by subtraction, not wall-clock timestamps.
5. Why record metrics in `finally`? To record both return and exception paths. Still, prevent errors in the metric sink itself from masking the primary error.
6. What does `ex == target.checked` verify? **The exact same `Throwable` instance identity**, not just the same class or message text.
7. Should you call `method.invoke(proxy, args)` from the handler? **No**, as it can recurse infinitely into the handler. Delegate to `target`.
8. Is sharing an `ArrayList` to record timings across multiple threads safe? **No**; use a concurrent structure or a thread-safe recorder.
9. Why is the measured time not always purely "real method" time? Because the interval includes Reflective invocation and related overhead; async methods may finish later.
10. Why do `toString`/`equals`/`hashCode` need an explicit policy? Because JDK proxies also route those three methods through the handler.

## 14. Official Java 17 Documentation References

- [Oracle Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): method dispatch, `Object` method handling, and checked exception limits.
- [Oracle Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): `invoke` and `invokeDefault` contracts.
- [Oracle Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `invoke` and exception wrapping behavior.
- [Oracle Java SE 17 — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): `getCause()` returns the target method's exception.
- [Oracle Java SE 17 — UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): wrapper for checked exceptions not declared by the interface.

**Key takeaway:** A dynamic proxy can time calls and forward transparently when the handler uses `System.nanoTime()` in `try/finally`, calls the **real target**, and **rethrows the exact `InvocationTargetException.getCause()`**. Checked exceptions must still be permitted by the interface; metric/logging code must never discard business results or throwables.