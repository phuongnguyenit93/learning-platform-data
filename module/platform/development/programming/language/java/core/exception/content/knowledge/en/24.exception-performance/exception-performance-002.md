# Distinguishing the Costs of Creating, Throwing, Catching, and Logging Exceptions in Java

When analyzing Java exception-handling performance, the statement "`try/catch` is very slow" is usually oversimplified and easily leads to misplaced optimization. A real error path consists of several distinct operations: **creating the exception object**, **capturing stack trace information**, **throwing and transferring control flow**, **finding and executing `catch`**, **running cleanup**, and then possibly **formatting and logging**. These operations have different costs, occur at different times, and do not always appear together.

For example, a `try` block executing successfully does not mean the JVM created an exception. A `new IllegalArgumentException(...)` object may already incur the cost of capturing a stack trace **at creation time**, even if it is never `throw`n. Conversely, a `catch` clause that is never executed does not have error-handling costs equivalent to throwing an exception. In production, printing stack traces to logs at a very high frequency can consume significantly more CPU, allocations, I/O, and storage than the catch itself.

This article explains each phase, how to measure properly, logging pitfalls, and design decisions so that you only pay the cost of exceptions when truly necessary. Examples use **Java 17+**.

## 1. An exception has at least four cost phases

Consider the following handling path:

```java
try {
    validate(request);
} catch (InvalidRequestException ex) {
    logger.log(Level.WARNING, "Invalid request", ex);
}
```

This is an **illustrative snippet**, with `validate`, `request`, `InvalidRequestException`, and `logger` defined by the application. If `validate` runs normally, no handler needs to process an exception. If it throws, the following steps may occur:

| Phase | When it occurs | Work that may incur cost |
| --- | --- | --- |
| **Exception creation** | When calling a `Throwable` constructor/factory | Object allocation; message/cause creation; capturing the backtrace by default at construction time. |
| **Throwing the exception** | When executing `throw` | Changing control flow; searching for a matching handler; unwinding the necessary frames; executing `finally` blocks and closing resources if present. |
| **Catching and handling** | When reaching a matching `catch` | Running classification logic, translation, fallback computation, metrics/statistics, or business handling inside the handler. |
| **Logging** | When code calls a logger/`printStackTrace` or another observability system | Formatting the message and stack trace, processing cause/suppressed, string allocations, synchronization/buffering, writing to console/file/network, impact on log queues. |

Beyond the four main steps, there are indirect costs: garbage collection, JIT optimization changes, allocation pressure, and observability layer effects (tracing, metrics, log exporters). Cost levels depend on the JVM, exception type, stack depth, error frequency, and logging configuration; **there is no single fixed nanosecond number that holds true for every application**.

A helpful mental model:

```text
Success path:
  check → normal processing → return result
           (no need to create/throw/catch/log an exception)

Failure path:
  detect error
       ↓
  create Throwable (+ default stack capture)
       ↓
  throw / unwind / finally
       ↓
  catch and recovery/error-reporting policy
       ↓
  [possibly] format and log
```

This diagram is conceptual. You can **create without throwing**, **throw an existing object**, **catch and rethrow**, or **log an object that was never thrown**. Separating the phases helps measure accurately.

## 2. Exception creation cost: constructor and backtrace

Most Java exceptions extend `Throwable`. When constructing a typical `Throwable`, `Throwable`'s constructor invokes the mechanism to capture the current stack state via `fillInStackTrace()`, except in special configurations/implementations. That is why **creating an exception can be more expensive than creating a simple data object**, even before it is thrown.

```java
IllegalArgumentException error =
        new IllegalArgumentException("quantity must be positive");

// No throw statement yet, but error has already been instantiated.
```

The snippet above is valid inside a Java method. In a typical JVM, the exception creation site information has already been recorded; `getStackTrace()` can convert that data into a readable `StackTraceElement` array. **Capturing the backtrace** and **materializing/formatting the stack trace for display** are separate tasks: `new Exception` and `printStackTrace` should not be assumed to have the same cost.

Key components of construction:

- **Allocation:** allocating the object; cost varies by allocation/JIT/GC mechanisms.
- **Message:** the string may already exist or be built from string concatenation, `String.format`, JSON serialization, or other computations. Computing the message before the constructor call can also be expensive.
- **Cause:** linking to the root `Throwable`. Keeping the cause aids diagnosis, but the cause chain can make logged stack traces longer.
- **Stack capture:** inspecting the execution context when creating the exception. Frame count and JIT/runtime characteristics affect the cost.
- **Suppressed exceptions:** related structure when multiple errors occur, especially with `try-with-resources`. Significant work is only incurred when secondary errors actually need to be tracked.

Not every runtime builds the stack trace representation the same way; some JVM optimizations apply to specific error types or throw sites. **The safe design guarantee** is not to rely on the JVM always optimizing away the stack-capture cost of every created exception.

### Expensive message construction even without throwing

```java
IllegalStateException error =
        new IllegalStateException(
                "Invalid payload: " + expensiveSerialization(payload));
```

This is an illustrative snippet, with `payload` and `expensiveSerialization` defined by the application. The serialization function may run **before** the exception constructor receives the string. If this code is called frequently while rarely throwing, you may have introduced message construction cost into the *hot path*.

Better yet, only create the exception after the error condition is actually confirmed:

```java
if (!isValid(payload)) {
    throw new IllegalStateException("Invalid payload");
}
```

Here `isValid` and `payload` are illustrative symbols. Validation still has a cost and is needed for business logic, but the exception is only created on the error branch. If deeper diagnosis is needed, log additional data according to security policy and log level rather than serializing the entire payload into every error message.

## 3. Throwing cost: control flow and unwinding

The `throw` statement transfers control out of the normal path to a compatible handler, or continues propagating through caller frames until a handler is found or the uncaught exception boundary is reached. Along the way, Java must execute applicable `finally` blocks and `try-with-resources` cleanup operations before leaving each scope.

Example:

```java
void outer() {
    try {
        inner();
    } finally {
        releaseOwnedResource();
    }
}

void inner() {
    throw new IllegalStateException("failed");
}
```

This is an illustrative snippet, with `releaseOwnedResource` undefined. When `inner` throws, exiting through `outer` triggers `finally`. If cleanup involves I/O or locks, **the observed cost of a failure includes the cleanup work**, not merely the `athrow` opcode.

Two things should be distinguished:

- `throw new MyException(...)`: creates **and then** throws. Measuring around this statement includes constructor, stack capture, and throw/unwind.
- `throw existingException`: rethrows **the same existing object**; does not invoke a new constructor just for executing `throw`.

Rethrowing an object does not automatically update its stack trace to the new throw site. This can make debugging information less useful. **Do not cache/reuse a global exception as a general optimization trick**: the stack trace may only reflect where the object was created, the exception data can be shared across threads, and cause/suppressed information becomes difficult to manage.

Instead of optimizing at the expense of diagnosability, determine whether you really need to use an exception as a signal for a situation that occurs millions of times.

## 4. Catching cost: don't confuse `try/catch` with the throw path

A `try` block containing a success path:

```java
int result;
try {
    result = Integer.parseInt("123");
} catch (NumberFormatException ex) {
    result = 0;
}
```

In this case, no `NumberFormatException` is created and thrown just because a `catch` statement exists. The JVM/JIT can optimize the normal execution path, although exception structure and branch likelihood may affect certain optimizations depending on the code and JVM.

When execution actually enters `catch`:

```java
catch (NumberFormatException ex) {
    failedRecords.incrementAndGet();
    return defaultValue;
}
```

This is an illustrative snippet, with `failedRecords` and `defaultValue` defined elsewhere. The cost of **logic inside catch** (counters, building a fallback value, logging, synchronization, DB access, etc.) can be far greater than assigning the exception reference to the variable `ex`.

Do not measure `try/catch` by always throwing an exception and calling that "the cost of catch". That is the **combined cost of the failure path**, not just the handler.

A `catch` construct that does not execute on the success path is usually not a valid reason to omit error handling. Conversely, throwing an exception to represent normal loop termination or an expected outcome that happens millions of times can be a design decision that causes unnecessary overhead.

## 5. Logging cost is a separate phase

Logging is not a mandatory operation of `throw` or `catch`. It is triggered when code records the exception:

```java
try {
    work();
} catch (IOException ex) {
    logger.log(Level.WARNING, "Failed to read file", ex);
    throw ex;
}
```

This snippet assumes `work`, `logger`, and `IOException` are declared/imported. The handler both logs and rethrows, so **the caller still receives the error**. If a higher layer also logs it, the same incident can produce multiple stack trace records.

A single error log entry can incur costs in multiple places:

1. Computing the message, concatenating strings, or building context objects.
2. Retrieving and rendering the stack trace; potentially traversing `cause` and `getSuppressed()`.
3. Formatting timestamp, thread, MDC/correlation ID, JSON, or structured logging fields.
4. Enqueuing the record or synchronizing with an appender.
5. Writing to console, file, network, or a centralized system.
6. Expanding log volume, consuming CPU, bandwidth, disk, retention, and operational cost.

With an async logger, part of the cost may shift to another thread, but **it does not disappear**. A full queue can block, drop logs depending on policy, or increase latency; the specific configuration determines the behavior.

`Throwable.toString()` primarily represents the type and message, **not the equivalent of printing the full stack trace**. `printStackTrace()` or logging a `Throwable` with its stack trace can generate significantly more lines. `getStackTrace()` may also materialize frame data before formatting it into text.

### "Logger disabled" does not mean every argument is free

Consider:

```java
logger.fine("Trace: " + serializeExpensiveObject(value));
```

This is an illustrative snippet; `logger` belongs to an appropriate logger and `serializeExpensiveObject` is assumed to exist. Java must evaluate arguments before calling the method, so serialization/string concatenation **can still happen** even when the `FINE` level is not enabled.

When using `java.util.logging.Logger`, you can pass a `Supplier<String>` in the appropriate API to build the message lazily:

```java
logger.log(Level.FINE, () -> "Trace: " + serializeExpensiveObject(value));
```

This snippet requires importing `java.util.logging.Level` and the corresponding logger. When the level is not enabled, lazy logging allows skipping message construction. That **does not mean there is zero overhead**: there is still the log-level check, lambda creation/dispatch depending on JIT, and the logger call itself.

When you want to log a `Throwable`, choose the overload appropriate for your framework, such as `logger.log(Level.WARNING, "Read error", ex)` in `java.util.logging`. Avoid formatting the stack trace into a string before knowing whether the log entry needs to be emitted.

## 6. Java 17 example: counting phases without pretending to measure time

The example below separates "object creation", "throwing", "catching", and "logging" using counters. This is an **illustration of order and where operations occur**, not a nanosecond benchmark.

Create `ExceptionPhasesDemo.java`:

```java
public class ExceptionPhasesDemo {

    private static final class InvalidQuantityException
            extends RuntimeException {
        static int constructed;

        InvalidQuantityException(String message) {
            super(message);
            constructed++;
        }
    }

    private static int thrown;
    private static int caught;
    private static int logged;

    private static int addOne(int quantity) {
        if (quantity < 0) {
            InvalidQuantityException error =
                    new InvalidQuantityException("quantity < 0");
            thrown++;
            throw error;
        }
        return quantity + 1;
    }

    private static void recordLog(InvalidQuantityException error) {
        logged++;
        System.out.println("LOG " +
                error.getClass().getSimpleName() +
                ": " + error.getMessage());
    }

    public static void main(String[] args) {
        System.out.println("normal: " + addOne(2));

        InvalidQuantityException onlyCreated =
                new InvalidQuantityException("created only");
        System.out.println("created without throw: "
                + onlyCreated.getMessage());

        try {
            addOne(-1);
        } catch (InvalidQuantityException error) {
            caught++;
            recordLog(error);
        }

        System.out.println("constructed: "
                + InvalidQuantityException.constructed);
        System.out.println("thrown: " + thrown);
        System.out.println("caught: " + caught);
        System.out.println("logged: " + logged);
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 ExceptionPhasesDemo.java
java ExceptionPhasesDemo
```

Stdout:

```text
normal: 3
created without throw: created only
LOG InvalidQuantityException: quantity < 0
constructed: 2
thrown: 1
caught: 1
logged: 1
```

Why do these counts occur?

- `addOne(2)` succeeds without creating `InvalidQuantityException`.
- `new InvalidQuantityException("created only")` invokes the constructor once without throwing or logging.
- `addOne(-1)` creates another exception, increments the `thrown` counter, and then throws.
- `catch` catches once and calls `recordLog` once.
- Therefore, the creation count is **2**, while the throw, catch, and log counts are each **1**.

The `thrown` counter in the demo is incremented manually right before `throw`; it is **not an automatic JVM exception-counting mechanism**. Do not read these numbers as timing benchmark results. The goal is to demonstrate the four distinct operations under inspectable execution conditions.

## 7. Demonstrating eager vs. lazy message formatting

To demonstrate that message construction costs can occur even when no log is printed, use a minimal logger with `Supplier<String>`. This demo does not represent the internal structure of real logging frameworks.

Create `LazyLogDemo.java`:

```java
import java.util.function.Supplier;

public class LazyLogDemo {

    private static int formattingCalls;

    private static String format(Throwable error) {
        formattingCalls++;
        return error.getClass().getSimpleName()
                + ": " + error.getMessage();
    }

    private static void log(boolean enabled, Supplier<String> message) {
        if (enabled) {
            System.out.println("LOG " + message.get());
        }
    }

    public static void main(String[] args) {
        Throwable error = new IllegalStateException("bad data");

        log(false, () -> format(error));
        System.out.println("lazy disabled: " + formattingCalls);

        String eager = format(error);
        log(false, () -> eager);
        System.out.println("eager disabled: " + formattingCalls);

        log(true, () -> format(error));
        System.out.println("enabled: " + formattingCalls);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 LazyLogDemo.java
java LazyLogDemo
```

Stdout:

```text
lazy disabled: 0
eager disabled: 1
LOG IllegalStateException: bad data
enabled: 2
```

The first line shows that the `format(error)` lambda is not invoked when the mock logger is disabled. In the eager example, `format(error)` is called **before `log`**, so the counter increments even though nothing is printed. When enabled, the supplier is evaluated and one record is printed.

The `error` object itself was already created before the log calls and has its own creation cost. **Lazy logging only defers/skips message evaluation**; it does not undo the cost of an exception that has already been created.

With a production logger, prefer APIs that support parameterized/lazy messages or check the level before an expensive context-building operation. Manual level checks for every tiny log line are not necessarily worth the effort; measure the actual hot spots.

## 8. Capturing a stack trace and formatting a stack trace are not the same thing

Error location information is very useful. However, in certain special designs, developers want to reduce stack trace creation cost for a signal that occurs an extremely large number of times.

`Throwable` has a protected constructor that allows configuring **suppression** and stack trace writability (*writable stack trace*). If a subclass constructor calls `super(message, cause, enableSuppression, writableStackTrace)` with `writableStackTrace=false`, the standard implementation will not record a stack trace for that object. This is a choice with a **major trade-off in diagnosability**, not a default to use.

Create `StackTraceChoiceDemo.java`:

```java
public class StackTraceChoiceDemo {

    private static final class LightweightFailure
            extends RuntimeException {
        LightweightFailure(String message) {
            super(message, null, true, false);
        }
    }

    public static void main(String[] args) {
        RuntimeException normal =
                new RuntimeException("normal failure");
        RuntimeException lightweight =
                new LightweightFailure("light failure");

        System.out.println("normal has frames: "
                + (normal.getStackTrace().length > 0));
        System.out.println("light frames: "
                + lightweight.getStackTrace().length);
        System.out.println("light message: "
                + lightweight.getMessage());
    }
}
```

Commands:

```bash
javac -encoding UTF-8 StackTraceChoiceDemo.java
java StackTraceChoiceDemo
```

On a typical JDK 17, stdout:

```text
normal has frames: true
light frames: 0
light message: light failure
```

`normal` has a backtrace from creation time. `lightweight` intentionally omits the stack trace; it still has a message and is still a valid exception. However, a later log will not reveal the exact call chain that created that exception. When investigating a production bug, the cost of losing the error location can outweigh the CPU saved.

**Only consider stackless exceptions when** it is an intentional design choice, other diagnostic context exists, measurements prove the cost is a problem, and the error is not an unexpected state requiring full investigation. Do not disable stack traces for all exceptions or important public exceptions just to "make it fast".

Java also allows overriding `fillInStackTrace()` in a subclass; doing so changes semantics and can make diagnosis difficult. Do not use that technique as a general optimization trick without tests and contract documentation.

## 9. Reusing exceptions can mislead error diagnostics

A common trick:

```java
private static final RuntimeException BAD_INPUT =
        new IllegalArgumentException("bad input");

void validate(boolean valid) {
    if (!valid) {
        throw BAD_INPUT;
    }
}
```

This is an illustrative snippet placed inside a class. Each failure does not allocate a new object, but `BAD_INPUT` typically has the stack trace from where the field was initialized, not from the specific check that failed. The same object can also be used across multiple threads; if one place adds a suppressed exception or mutates object state, investigation becomes confusing.

Do not automatically turn exceptions into singletons just because constructors are expensive. If the "bad input" situation is expected to occur at high frequency, consider **returning a typed validation result** instead of throwing an exception for every case.

Reused exceptions, no-stack exceptions, and altered stack trace semantics should only appear after understanding diagnostic needs, API contracts, and profiling data.

## 10. When should exceptions not be used for frequent control flow?

Exceptions are well suited for representing **failure paths, violated preconditions, or special states per the API contract**. However, if an event occurs frequently and is considered a normal outcome, a non-throwing API can be used.

For example, a lookup that can very frequently find "nothing":

```java
Optional<String> found = lookup(key);
if (found.isEmpty()) {
    // This is a valid query outcome.
}
```

This is an illustrative snippet assuming `lookup` returns `Optional<String>`. If absence is a normal state, `Optional.empty()` or a result type can be clearer than creating/throwing `NoSuchElementException` on every miss.

A data-parsing API receiving bulk user input can return:

```java
record ParseResult<T>(T value, String errorCode) {
    boolean isSuccess() {
        return errorCode == null;
    }
}
```

This is an illustrative data-type example using `record` (supported in Java 17), without building a full parser. A real API needs to define invariants (for example, only one of `value`/`errorCode` is present) and avoid ambiguous `null` cases.

However, not every `NumberFormatException` should be replaced with a result type. If a program rarely receives invalid data, exception-based code can be simpler, semantically accurate, and not worth optimizing. **Performance is not a reason to skip validation or hide errors.**

Comparison:

| Situation | Approach worth considering |
| --- | --- |
| An API request rarely violates a precondition | Throw an exception with a clear type and message. |
| A parser processes millions of values where invalid data is expected | Per-record result/status, collecting errors and reporting at the end of the batch. |
| A network connection unexpectedly fails | Contextual exception/I/O error; handle retries according to policy. |
| Optional key lookup very frequently finds no data | `Optional`/absent result, rather than turning normal misses into an exception burst. |
| Internal invariant bug is violated | Keep the exception/stack trace for diagnosis; do not "optimize" with a fake fallback. |

## 11. Why can logging a stack trace be very expensive?

Creating a stack trace and **logging a stack trace** are different. `Throwable#printStackTrace` can traverse the frame list, cause, and suppressed exceptions, converting them to text and writing them through `PrintStream`/`PrintWriter`. Logging frameworks may do the same along with JSON formatting, MDC, and custom exporters.

Logging cost can grow with:

- Exceptions per second.
- Stack trace depth and the number of `caused by`/`suppressed` chains.
- Log metadata size and message length.
- Synchronous console I/O, disk speed, network, or collector throughput.
- Full async queues or switching to block/drop mode.
- The number of times the same exception is logged across layers.

An error repeating 10,000 times per minute does not just cost exception allocations; if each occurrence writes dozens of lines, logging can become a heavy load and trigger a feedback loop: a system already slowed by errors slows down further because of logging.

### Log at the responsible boundary

A pattern prone to **double logging**:

```java
try {
    repository.save(entity);
} catch (IOException ex) {
    logger.log(Level.SEVERE, "Repository failed", ex);
    throw ex;
}
```

If the service and request handler above also log the full stack trace, one incident can become three log entries. This snippet is illustrative only; `repository`, `entity`, and `logger` must be defined in proper context.

One design approach is:

- Lower layers **throw/translate with a cause** when needed, without always logging.
- The layer with sufficient business context decides the message and log level.
- The outermost layer or workflow owner writes one error log with a stack trace if truly needed.
- For expected input errors, typically log at an appropriate level, possibly without a stack trace on every request.
- Use counters/metrics for expected error frequencies; do not replace monitoring with millions of identical log records.

There is no universal "log strictly once" rule for every system; some errors require distinct audit and operational logging. However, **every log entry needs a clear purpose**, not just defensive "log here too" duplication.

## 12. Choosing log levels and sampling by error meaning

A practical guide:

| Event type | Recording approach |
| --- | --- |
| Common invalid input validation | Return an error code to the caller, increment a metric; log selectively and avoid exposing payloads. |
| Unexpected system error with impact | Log with stack trace and correlation ID at the responsible layer. |
| Transient network error that retried successfully | Retry/error-rate metric; log at an appropriate level, avoiding full stack traces on every attempt unless needed. |
| Programming bug breaking an invariant | Preserve original stack/cause; log for investigation and alerting. |
| Exception burst due to a down dependency | Increment metrics, alert, optionally rate-limit/sample logs per policy; do not obscure aggregate signals. |

Sampling/rate limiting helps prevent log storms, but you must keep **total event counts** to know the scale. If you only log 1% without a corresponding metric, log dashboards easily underestimate severity.

Do not use error messages or raw stack traces as high-cardinality metric labels. Prefer error types, error codes, subsystem groups, or bounded operation names. Sensitive data in messages must be filtered or masked according to security policy.

## 13. `try-with-resources`, suppressed exceptions, and cleanup cost

When an operation fails, the cost measured at the call site may include cleanup. With `try-with-resources`:

```java
try (InputStream in = Files.newInputStream(path)) {
    parse(in);
}
```

This is an illustrative snippet requiring imports for `InputStream`, `Files`, plus `path` and `parse`. If `parse` throws an exception, Java still calls `in.close()`. If `close` also throws, the close exception is typically attached via `addSuppressed` to the primary exception.

Therefore, a benchmark measuring `throw new IOException` inside a resource scope may actually be measuring:
1. Constructor and stack capture of the primary `IOException`.
2. Throw/unwind.
3. I/O cleanup (`close`), which can be much more expensive.
4. If `close` fails, creating/allocating another exception and recording suppressed state.
5. Outer catch/log if invoked.

Do not treat that result as the pure cost of the `throw` opcode or handler.

More importantly: **do not skip cleanup to reduce latency**. Leaking file descriptors, connections, sockets, or locks is usually worse than exception-handling cost. Proper optimization means organizing ownership, closing timing, and appropriate error handling.

## 14. Do checked and unchecked exceptions differ in performance?

`IOException` is checked; `IllegalStateException` is unchecked. Compile-time checking rules differ: checked exceptions must be declared or caught per Java's rules; unchecked exceptions do not. However, **there is no general rule** that checked exceptions always have higher or lower runtime cost than unchecked exceptions merely because of the `throws` signature.

Cost differences usually come from:
- Exception type, constructor/message, and how stack traces are handled.
- Frequency of creation/throwing.
- Stack depth or cleanup during unwinding.
- Handler logic and logging.
- JIT optimization techniques and runtime characteristics.

Do not convert every `IOException` into a `RuntimeException` solely on the grounds that "unchecked is faster". Translating exceptions can make sense at boundaries to stabilize contracts or add context, but creating a new wrapper may capture another stack trace; if the cause is preserved, full logs may print both chains.

## 15. Benchmarking pitfalls for exception performance

A hand-written microbenchmark like:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    try {
        throw new RuntimeException("failed");
    } catch (RuntimeException ignored) {
    }
}
System.out.println(System.nanoTime() - start);
```

This is an illustrative snippet of an **unreliable benchmark**, not a measurement for making production decisions. It mixes **construction + throw + catch**, and is subject to JIT/GC optimizations, warm-up effects, CPU environment, varying log levels, and dead-code elimination when the compiler proves there are no useful side effects. Running it once and taking a nanosecond number is inconclusive.

### Why naive benchmarks are wrong

**Warm-up and JIT:** Early iterations often include class loading, compilation, and unoptimized code states. Exception paths are usually rare in production, whereas the benchmark throws continuously, creating a completely different profile.

**Escape analysis and optimizations:** The JIT may optimize allocations/paths differently than expected from source code, or eliminate code with no observable result. A benchmark must ensure meaningful work is performed.

**HotSpot fast-throw:** Some HotSpot builds have a special optimization for certain **JVM-generated** exceptions at repeated failure sites (e.g., implicit null/bounds checks); stack traces may be omitted under certain conditions. Results must not be generalized to `throw new MyDomainException(...)` or all JVMs/JDKs. Flags/runtime/version affect behavior; verify on the target JVM before drawing conclusions.

**Stack depth and location:** Creating an error in a deep method can differ from creating one at the top of the stack; throwing across multiple frames/`finally` blocks differs from catching locally.

**Log level:** A benchmark writing stack traces to console/file cannot be compared directly with a path that only catches and returns a fallback. Logging to stdout/stderr also depends on buffering and terminal environment.

**GC and allocation:** Loops creating many `Throwable`s create allocation pressure; you should also measure throughput/allocations/GC, not just single-call latency.

**Branch probability:** If 0.001% of requests fail, the average per-request cost is very different from a test that throws 100% of the time. Measure both the successful hot path and error bursts.

### How to measure more accurately

For Java microbenchmarks, use **JMH (Java Microbenchmark Harness)**, which provides warm-up, multiple iterations/forks, and mechanisms to mitigate several JIT/benchmark pitfalls. JMH is an external library/harness outside the JDK, not included with `javac` alone; set up an appropriate project/dependency before running.

Design separate measurements:

1. **Successful path:** has `try/catch` but does not create an exception.
2. **Construct-only:** creates a `Throwable` without `throw` or logging; ensure the object is an observable result.
3. **Throw pre-created:** throws an existing object to better isolate throw/catch, while noting that stack trace semantics differ from the normal path.
4. **Throw new:** creates and throws on the same branch; represents the common case but is not pure "throw cost".
5. **Catch + lightweight handling:** classifies/returns a fallback without logging.
6. **Catch + log disabled:** checks the overhead of the logging call and argument evaluation.
7. **Catch + log enabled:** measures formatting and actual appender; for async, account for consumer/queue load.
8. **Different stack depths/error rates:** checks the impact of frame depth, exception types, and error frequency.

Distinguish **microbenchmarks** from **real application profiling**. A constructor optimization might have zero impact on p95 latency if network/I/O is the real bottleneck. Combine CPU profiles, allocation profiles, GC logs, log throughput, and error-path metrics before deciding.

## 16. Illustrative measurement code: organizing tests without extrapolating fixed numbers

The example below prints operation counts rather than trying to build a benchmark from `System.nanoTime`:

Create `ErrorPathClassificationDemo.java`:

```java
public class ErrorPathClassificationDemo {

    private static int created;
    private static int handled;

    private static IllegalArgumentException newFailure() {
        created++;
        return new IllegalArgumentException("invalid");
    }

    private static boolean validate(int value) {
        if (value >= 0) {
            return true;
        }
        throw newFailure();
    }

    private static void process(int[] input) {
        for (int value : input) {
            try {
                validate(value);
            } catch (IllegalArgumentException ex) {
                handled++;
            }
        }
    }

    public static void main(String[] args) {
        process(new int[] {1, 2, -1, 3, -2, 4});
        System.out.println("items: 6");
        System.out.println("created: " + created);
        System.out.println("handled: " + handled);
    }
}
```

Run:

```bash
javac -encoding UTF-8 ErrorPathClassificationDemo.java
java ErrorPathClassificationDemo
```

Stdout:

```text
items: 6
created: 2
handled: 2
```

The test checks six inputs, and only two negative values take the exception path. For benchmarking, you would need to run multiple error rates (0%, 1%, 50%, 100%) with meaningful data and an appropriate harness. **Do not take 2/6 and conclude that 33% of CPU is spent on exceptions**; that is only the ratio of invalid items in the sample data.

When checking production performance, measure **errors per request, exception objects allocated, logging cost, and added latency**, rather than just counting how many `catch` blocks appear in source code.

## 17. Designing APIs for low error overhead while staying diagnosable

A balanced design usually follows these principles:

**Use exceptions for failures that deserve to be treated as exceptional.** Any serious constraint violation or unexpected error needs a clear handling path. Do not remove `throw` out of fear of overhead if it occurs rarely.

**Use result types for high-frequency expected situations.** For example, a batch parser where per-record errors are normal; returning a status instead of throwing exceptions millions of times can be beneficial and helps callers classify errors accurately.

**Create exceptions when the failure is known.** Avoid pre-constructing objects or formatting expensive messages on the successful path.

**Preserve the cause when translating exceptions.** The persistence layer can translate `SQLException` into `RepositoryUnavailableException` to stabilize the contract, while keeping `cause` for diagnosis. Creating a wrapper has a cost; only do it when it adds real abstraction value.

**Log at sensible boundaries.** When catching and rethrowing, you do not have to log an extra stack trace in place. The caller usually has better context to decide severity and response.

**Preserve errors and cleanup.** Use `try-with-resources`/`finally` with clear ownership, distinguishing primary/cause/suppressed. Do not sacrifice cleanup to improve benchmark numbers.

**Do not let logging turn validation errors into a data leak.** Never put raw tokens, credentials, or personal payloads into exception messages or logs.

**Observe with stable-cardinality metrics.** Count errors by type and subsystem rather than attaching raw messages/stacks as labels.

## 18. Comparing strategies on real-world scenarios

### Scenario A: An API receives invalid input at a low frequency

A suitable solution can be:

```java
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
```

This is a clear precondition. If callers rarely send invalid input, creation/throwing cost only occurs on the error branch. The HTTP handler can return a 400 response, track validation rates, and avoid printing a full stack trace for every request when unnecessary.

### Scenario B: Importing one million records where 30% are invalid

Turning every invalid record into an exception and logging a full stack trace will create many objects and duplicate log entries. You can use a per-record result/status, collect error codes, and emit a summary/report per batch. When an unexpected system error occurs during the import, an exception with a stack trace remains useful.

### Scenario C: A network dependency fails in bursts

Sometimes the network call itself is much slower than exception constructors. However, during widespread failures, repeated logging at every layer creates a log storm. Use bounded retries, circuit breakers if needed, error-rate metrics, log sampling, and a single place that logs a message with sufficient context. Do not claim a "speedup" just by dropping stack traces if the real bottleneck is the network or queue.

### Scenario D: A library pre-creates exceptions for reuse across requests

When errors are rare, pre-constructing exceptions may shift creation cost to startup and lose the stack trace of the specific request site. If a shared exception is cached, diagnostics can be misleading and suppressed/cause state can be shared. Only do this with a clear contract and after actual measurement/verification; in most cases, create the exception upon failure.

### Scenario E: DEBUG-level logger is disabled in production

If code still calls a very heavy formatter before the logger, disabling the log level may not eliminate message preparation cost. Use lazy/parameterized logging or guard the level for expensive expressions; profile after the change to confirm the benefit.

## 19. Common mistakes and fixes

**"Merely having `try/catch` makes the program as slow as throwing errors."** False. The non-error path usually does not create or throw exceptions; distinguish normal processing from the exception path.

**"Throw cost equals `new` cost."** False. Constructor/backtrace and throw/unwind are different phases; `throw new` combines both.

**"Catch is the most expensive phase."** There is no such rule. Logic inside catch, stack trace logging, I/O, and cleanup can dominate the cost.

**"Log level OFF means zero cost."** Arguments evaluated before the call can still consume CPU/allocations. Use lazy/parameterized APIs to avoid expensive formatting when unnecessary.

**"`error.toString()` already prints the stack trace."** No. `toString` usually returns type + message; `printStackTrace` and full Throwable logging include frames/cause/suppressed.

**"Logging exceptions at every layer is safer."** It can create multiple records for the same failure and bury real signals in a log storm. Log at the responsible boundary and preserve the cause when propagating.

**"Just disable stack traces to speed things up."** This can lose information needed to investigate critical bugs. Use no-stack optimizations only when the contract allows and profiling proves the benefit.

**"Reusing a singleton exception is always fast and safe."** It easily leads to wrong stack traces and shared mutable state across threads. Avoid unless there is a clear reason.

**"Checked exceptions are slower than unchecked exceptions because the compiler requires catching them."** That is a compile-time type rule, not a ranking of runtime overhead.

**"Using `System.nanoTime` in a loop is enough to prove it."** Microbenchmarks need warm-up, multiple samples, protection against JIT elimination, and a consistent environment; use JMH and verify on real workloads.

**"Few exceptions but lots of logs must mean the bottleneck is at `throw`."** No. Measure formatting, stack rendering, and log appenders/queues separately.

**"Skip `finally`/close to reduce error-path cost."** Proper cleanup is part of the invariant. Optimizations that leak resources miss the point.

## 20. Pre-optimization checklist

1. **Where is the cost actually located?** Constructor/stack capture, unwind, catch logic, cleanup, message formatting, or log appender?
2. **What is the actual error-branch frequency?** 0.001%, 1%, 50%, or a 100% error burst? What is the application's hot path?
3. **Is the exception a frequently expected outcome?** If so, would `Optional`/status/result type make the contract clearer?
4. **Are you building messages/formatting JSON before knowing an error/log is needed?** Can it be built lazily?
5. **Are you logging the same failure across multiple layers?** Can you keep a single event/metric with clear ownership?
6. **Are you printing full stack traces for every expected input error?** Can you use metrics and appropriate log sampling?
7. **Are cause, suppressed, cleanup, and thread state preserved?** Do not trade away correctness.
8. **Is the stack trace needed for production debugging?** If so, do not rush into no-stack exceptions.
9. **Does the benchmark separate phases and guard against JIT/GC skew?** Use JMH when microbenchmark numbers are needed.
10. **Does the result improve production?** Compare p95/p99 latency, allocation rate, CPU, GC, log throughput, queue drops, and processing speed.
11. **Are there new operational or security risks?** Rate-limit logs while keeping metrics; do not put sensitive data into messages.
12. **Do regression tests still verify the right errors?** Performance optimizations must not turn failures into false successes or unintentionally alter public contracts.

## 21. Summary

**Creating, throwing, catching, and logging an exception are four distinct operations**. In standard Java, `Throwable`'s constructor can capture the stack at creation time; `throw` transfers control flow and unwinds; `catch` runs handling logic; and the logger may format the stack trace and push data through I/O or queues. A success path passing through `try` has not paid all the costs of an exception path.

Effective optimization usually starts with **not creating exceptions on the normal hot path**, **not using exceptions for high-frequency expected outcomes**, **not formatting logs pointlessly**, and **not logging duplicate stack traces across layers**. When numbers are needed, separate components in benchmarks, use JMH appropriately, and verify with real-workload profiling. Invariants, cleanup, necessary cause/stack trace information, and error observability must still be preserved: good performance only matters when the system remains correct and diagnosable.
