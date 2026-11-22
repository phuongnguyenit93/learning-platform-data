# Stack Trace Cost in Java Logging

## 1. What Is a Stack Trace and Why Does It Have a Cost?

A **stack trace** is a list of frames describing the chain of method calls at a specific point in time. Each frame typically contains the class name, method name, file name, and source line number when that information is available. In Java applications, stack traces serve two different logging purposes:

1. **`Throwable` stack trace:** indicates where an exception/`Error` was created and the calls that led to that location. For example, `logger.error("Save failed", exception)`.
2. **Caller location:** used when a log pattern requests the class, method, file, or line number of the logging call itself, such as `%class`, `%method`, `%file`, `%line`, or `%caller` in Logback.

Both types of data relate to the call stack, but **they are collected at different times and for different purposes**. An existing exception's stack trace generally does not have to be created from scratch every time it is logged. Conversely, computing the logger caller location may require walking the stack even when the event carries no exception.

A typical example:

```text
ERROR OrderService - Failed to save order
java.io.IOException: Connection reset
    at example.Storage.save(Storage.java:42)
    at example.OrderService.submit(OrderService.java:18)
    ...
```

The snippet above is **illustrative**, not the fixed output of a specific program. The number of frames, file names, and line numbers vary depending on the code, JDK, and runtime environment.

The cost to evaluate is not just "is calling `printStackTrace` slow?". A log event with an exception may have to: create/capture the trace, materialize frames, format the message and exception chain, create/push the event through a queue, encode it as text/JSON, and then write it to the console, a file, or the network. **Each stage has its own cost**; an optimization at one layer does not automatically eliminate costs at another layer.

## 2. When Is a `Throwable`'s Stack Trace Created?

For a standard `Throwable` in Java, the constructor invokes the `fillInStackTrace()` mechanism to record the stack at the **time the object is created**. This matters more than many people realize:

```java
Exception error = new Exception("diagnostic"); // Captures the stack here.
logger.debug("Diagnostic only", error);         // May be filtered out by DEBUG.
```

If `DEBUG` is disabled, `logger.debug(...)` may not emit an event; **however, `new Exception(...)` has already executed**, because it is a standalone statement before the logger call.

This situation also occurs when creating an exception directly inside an argument expression:

```java
logger.debug("Current call stack", new Exception("trace"));
```

Java evaluates arguments before calling `debug`. The logger cannot turn back time to prevent `new Exception` from executing. Level filtering can only avoid work that happens **inside** the logging call afterward.

Several important characteristics:

- Throwing (`throw`) an existing exception **does not automatically refresh** its stack trace to the rethrow location. Changing the trace requires an explicit operation, such as `fillInStackTrace()`, which itself has a cost and can lose the original context.
- `getStackTrace()` produces a `StackTraceElement[]` array for inspecting frames; materializing and copying this information can allocate additional objects.
- `printStackTrace()` must convert the exception, stack frames, `cause`, and `suppressed` exceptions into a readable format and write them to a `PrintStream` or `PrintWriter`. It is not merely reading a pre-built string.
- Some implementations/JVMs have techniques to defer materializing frame details, but **you must not infer that `new Exception()` is free**.
- `Throwable` has a protected constructor to disable a writable stack trace; this is a specialized design choice for certain kinds of exceptions, **not a default optimization** for errors that need diagnosis.

### Stack traces are recorded at the creation site, not the log site

```java
IllegalStateException failure =
        new IllegalStateException("Bad state");

// Some other processing...

logger.error("Operation failed", failure);
```

The frames in `failure` are tied to where the exception was instantiated. Passing this object through another method before logging does not turn its stack into the stack at `logger.error`. If you need information about where the log call occurred, that is **caller location**, which has its own collection mechanism.

## 3. Cost Breakdown Table

| Component | When It Occurs | Symptoms / Impact |
| --- | --- | --- |
| Standard `new Throwable/Exception` | When creating an exception, even if logging is disabled when created outside a guard | Stack walking, allocation, GC pressure |
| `fillInStackTrace()` | When a standard exception is constructed or called explicitly | Capturing/recording the current call stack |
| `getStackTrace()` | When code needs to read individual frames | Materializing/copying frame info, extra allocations |
| `printStackTrace()` or formatter | When rendering error details to text/JSON | Iterating frames, handling cause/suppressed, producing many characters |
| Event caller information | When a pattern/API requests file, line, method, or caller | Stack walking to determine the logger call site |
| File, console, or network writes | When an appender/sink outputs the event | I/O, encoding, locking, network, storage volume |
| Async appender queue | When decoupling the producer from the sink | Memory, queue coordination, backpressure/drops under overload |
| Expensive message construction | When code concatenates strings, serializes objects, or calls heavy functions | Still incurred even if the logger discards the event once the expression is evaluated |

There is no fixed cost ratio that holds true for every system. A short exception written to an in-memory sink has a different profile from an exception with hundreds of frames, multiple `cause`s, and output to the console or network. You need to measure under the right load and with the right backend.

### Stack depth and error frequency

A deeper trace can require more work to capture, convert, and print. A single error rarely causes a problem. **Repeated errors in a hot loop** are what matter: thousands of exceptions per second can drive up allocations, formatting CPU, GC, and logged byte volume.

Example of three wrapping layers:

```text
ServiceException
  caused by RepositoryException
    caused by IOException
```

When formatting, the backend may also print the cause chain and suppressed exceptions. Logging **the full stack trace at every layer** increases duplicated data: the application may log the same root cause three times for a single business failure. Prefer logging concise business context at intermediate layers and logging the full exception at the appropriate handling boundary.

## 4. Standalone Java 17 Example: Disabled Logging Still Pays Exception Creation Cost

The following example uses `java.util.logging` (JUL), which is built into the JDK. It **counts how many times code creates an exception or builds a message**, without pretending to measure exact nanoseconds. The logger is set to `OFF` so all `FINE`-level calls are filtered out.

Create `StackTraceCostDemo.java`:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

public class StackTraceCostDemo {
    private static int exceptionsCreated;
    private static int messagesBuilt;

    private static Exception diagnosticException() {
        exceptionsCreated++;
        return new Exception("diagnostic stack");
    }

    private static String expensiveMessage() {
        messagesBuilt++;
        return "details computed";
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.stack.cost");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.OFF);

        // Arguments are evaluated before logger.log(...) is called.
        logger.log(Level.FINE, "Hidden diagnostic", diagnosticException());
        System.out.println("Eager exceptions: " + exceptionsCreated);

        // Only create the exception if the log level is enabled.
        if (logger.isLoggable(Level.FINE)) {
            logger.log(Level.FINE, "Guarded diagnostic",
                    diagnosticException());
        }
        System.out.println("Guarded exceptions: " + exceptionsCreated);

        // Supplier<String> is only invoked if the logger decides to log.
        logger.log(Level.FINE, () -> expensiveMessage());
        System.out.println("Supplier messages: " + messagesBuilt);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac StackTraceCostDemo.java
java StackTraceCostDemo
```

**Exact stdout:**

```text
Eager exceptions: 1
Guarded exceptions: 1
Supplier messages: 0
```

Explanation:

1. `diagnosticException()` runs in the argument expression of the first call, incrementing `exceptionsCreated` and instantiating `Exception` (which normally captures the stack). The logger then discards the event because of `Level.OFF`.
2. `isLoggable(Level.FINE)` returns `false`, so the branch containing the second `diagnosticException()` does not run.
3. JUL's `Logger.log(Level, Supplier<String>)` overload does not need to invoke the supplier when the level is disabled; `messagesBuilt` remains `0`.
4. To keep stdout deterministic, the example prints only the three counters, without printing stack traces or machine-dependent timings.

**Note:** the counters are evidence of **whether object creation/function execution occurred**, not of frame count, allocated bytes, or wall-clock time. Use a profiler/JMH to measure performance cost.

### Why not just use `new Exception` on every debug line?

`new Exception("where am I")` is one way to obtain the call stack location, but if used across many debug events or inside a loop, the price is paid at object creation time. If the goal is simply to log a few business fields, there is no need to construct a `Throwable`. If caller location is needed, use the caller/location mechanism supported by the backend and enable it only in profiles where it is needed.

## 5. Logging Properly with SLF4J

In many Java applications, code calls the SLF4J API while Logback or Log4j2 handles the backend.

### 5.1. Use parameterized logging

```java
logger.debug("Order {} status {}", orderId, status);
```

The `{}` placeholders allow the backend to skip most of the message formatting when `DEBUG` is disabled. However, **Java still evaluates argument expressions before invoking the method**. If `orderId` and `status` are already available values, the cost is usually small. If an argument requires serialization, computation, or a complex query, it will still execute:

```java
// expensiveReport(order) runs even when DEBUG is disabled.
logger.debug("Report: {}", expensiveReport(order));
```

In that case, guard it:

```java
if (logger.isDebugEnabled()) {
    logger.debug("Report: {}", expensiveReport(order));
}
```

The snippets above **illustrate code in an application where variables, logger, and methods already exist**, not a standalone Java file. With SLF4J 2.x, the fluent API `logger.atDebug().addArgument(() -> expensiveReport(order)).log("Report: {}");` can also support lazy arguments via a supplier, provided you use the right version and API call path. Do not pass `expensiveReport(order)` as a precomputed value and call it lazy.

### 5.2. When a real exception occurs, preserve the error object

```java
try {
    operation.run();
} catch (Exception failure) {
    logger.error("Order operation failed, orderId={}", orderId, failure);
    throw failure;
}
```

This is an **illustrative snippet** inside a method that has `operation` and `orderId` in scope; it cannot be compiled standalone. With standard SLF4J/Logback, a `Throwable` in the final argument position is recognized as the cause so the appender renders the stack trace, rather than just calling `failure.toString()`.

Avoid:

```java
logger.error("Order operation failed: " + failure.getStackTrace());
```

`Throwable.getStackTrace()` returns an array of frames; concatenating the array directly into a `String` usually yields unhelpful output, while eagerly materializing/allocating before the logger even checks the level. If you only need a short message, pick `failure.getMessage()` and a few safe fields; if you need the stack, pass the `Throwable` itself so the backend formats it consistently.

### 5.3. Create diagnostic traces only when needed

```java
if (logger.isDebugEnabled()) {
    logger.debug("Diagnostic stack for operationId={}",
            operationId, new Throwable("diagnostic only"));
}
```

Thanks to the guard, no `Throwable` is created when `DEBUG` is disabled. However, this approach still creates a new stack trace whenever `DEBUG` logging is enabled; use it only at points useful for investigation. Choose configuration-based caller/location mechanisms if you need to continuously inspect log emission sources.

Do not confuse **logging a real exception** with **deliberately creating a synthetic exception to get a stack**: a real exception was already created as part of the error path; a synthetic exception incurs cost purely for observation.

## 6. Cost of Caller Location in Logging Patterns

Many patterns only need the timestamp, log level, logger name, thread, and message:

```text
%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n
```

Some Logback patterns also request the call site:

```text
%class.%method(%file:%line) - %msg%n
```

To obtain `%class`, `%method`, `%file`, `%line`, or `%caller`, the backend may have to locate **the exact caller frame** in the call stack. This is extra work, even when the message contains no exception.

**`%logger` is not the same as `%class`:** the logger name is already known from the logger instance; the class name at the call site must be derived from the stack, unless the backend has a dedicated mechanism for providing location. If you only need to know the logical component, the logger/package name is sufficient in many cases.

| Field | Role | Cost Notes |
| --- | --- | --- |
| `%logger` | Logger name chosen by the application | Usually cheaper than walking the stack for the caller |
| `%thread` | Source thread name for the event | Useful for concurrency debugging, but does not identify a request |
| `%X{requestId}` | Correlation ID from MDC | Does not imply a stack walk; requires context to be set/propagated properly |
| `%class`/`%method`/`%line` | Code location calling the logger | Can be expensive due to determining the caller stack |
| `Throwable` stack trace | Exception creation site and error chain | Specific capture/formatting cost; not a substitute for caller location |

In systems that persist logs frequently, prioritize fields with practical query value. Only enable caller location on the loggers/profiles where the diagnostic benefit outweighs the cost.

### Combining with async logging

With Logback `AsyncAppender`, the business thread enqueues the event and a worker thread processes it in the background. One detail that is easy to miss:

- To know the **logger call site of the business thread**, the backend must collect caller data while still in the source thread's context. Once the event is handed off to the worker, the worker's stack is **not** the source stack.
- Logback `AsyncAppender` has an `includeCallerData` option. When enabled, it prepares caller data on the producer side so async events still show the appropriate call site. This option incurs synchronous cost on the business thread.
- If file/line/method are not needed, do not enable `includeCallerData` just because all logs go through an async appender.
- Logging a real exception still requires processing the `Throwable` information that was already created/captured earlier. Pushing the event into a queue does not erase the cost the application already paid to create the exception.

For Log4j2 `AsyncLogger` or `AsyncAppender`, the caller location concept can also be expensive and requires configuration specific to the API/version. **Do not copy Logback option names into Log4j2** without checking the backend in use.

Async logging keeps the business thread from having to wait for full sink I/O on every event, but it is **not free**: the queue consumes memory, has backpressure/discard thresholds, and preparing the message/context/caller data on the producer still takes time.

## 7. Logging Many Stack Traces in Rapid Succession: What Happens?

Suppose a system hits a timeout error 10,000 times in a short window. If each occurrence:

1. creates a new exception,
2. stores a long stack trace,
3. formats the message along with many frames,
4. pushes kilobytes of data to a file/collector,

then in addition to handling the timeout itself, the system bears the extra CPU, allocation, and I/O of logging. During an incident, excessive logging can slow the system down further and grow queue backlogs, leading to dropped logs depending on the policy.

### Rules for avoiding duplicate traces while keeping sufficient information

- Log the full stack trace at **the error-handling boundary** that has enough context, such as the final request/job handler layer.
- At lower layers, rethrow the exception or wrap it with additional semantics via `cause` when needed, instead of logging the same stack at every layer.
- If logging at an intermediate layer is necessary to diagnose a recovery action, use a short message and appropriate context; do not automatically print the full stack multiple times.
- Keep request/trace identifiers and error types consistent so events sharing the same root cause can be grouped.
- For repeated errors, consider rate limiting, sampling, or aggregating counts over time **if that satisfies operational and audit requirements**. Do not arbitrarily drop critical errors that must be stored in full.
- If the sink has a quota, understand the drop policy before deciding how to trim events; losing the entire error trail is different from trimming redundant stack portions.

Example of logging without duplicating at every layer:

```java
// Repository layer: propagate the error, keeping the cause.
throw new RepositoryException("Cannot save record", originalFailure);

// Request/job handling layer: log once with a correlation ID.
logger.error("Request failed, requestId={}", requestId, failure);
```

This is an **illustrative pattern**, assuming `RepositoryException` and the declared variables exist. Creating a new `RepositoryException` still incurs stack capture cost; only wrap an exception when it genuinely adds meaning or satisfies a contract, not across multiple layers just to reword a message.

## 8. When Should Stackless Exceptions Be Used?

`Throwable` has a protected constructor that allows disabling suppression and a writable stack trace. For example:

```java
public final class LightweightSignal extends RuntimeException {
    public LightweightSignal(String message) {
        super(message, null, false, false);
    }
}
```

This is a **standalone Java class that compiles if saved in `LightweightSignal.java`**. The parameter `writableStackTrace=false` leaves the stack trace information empty and avoids the cost of recording the stack through this mechanism. In return, when an issue occurs, you lose the creation/throw call chain for that exception. `enableSuppression=false` also disables recording suppressed exceptions.

This approach is only suitable for **special-purpose, pre-designed signals with a clear handling path that do not require a stack for investigation**. It is not a default choice for application errors, I/O, database issues, or abnormal conditions that need diagnosis. Do not turn every exception into a stackless one just to make a benchmark look good; micro-level gains can be outweighed by much longer debugging time.

An even better design choice when there is no actual error is to avoid using exceptions for normal control flow: return a clearly typed result, validate preconditions upfront, or use a data structure that expresses the expected state.

## 9. How to Measure the Cost

Do not rely on a word-of-mouth nanosecond number to optimize every system. Performance is affected by call stack depth, JDK version, JIT, CPU, GC, log level, backend, pattern, appender, encoder, and actual workload.

### 9.1. Separate the measurements

| Scenario | What You Want to Measure | Do Not Mix In |
| --- | --- | --- |
| `new Exception(...)` | Cost to create/capture a `Throwable` | Console I/O, rendering the full trace |
| `exception.getStackTrace()` | Cost to materialize/copy frames | File/network writes |
| `exception.printStackTrace(PrintWriter)` | Cost to render the trace and causes to a writer | Production sink sync/flush if using `StringWriter` |
| Disabled logger with existing arguments | Normal filtered logging path | Expensive argument construction outside |
| Disabled logger with inline `new Throwable(...)` | Eager argument cost + filtered call | Cost of actual backend writes |
| Caller location enabled/disabled | Overhead of obtaining class/method/line for an event | `Throwable` cost if there is no exception |
| Sync/async appender with the same payload | Producer latency, throughput, queue, drain | Concluding "async never drops logs" without checking discards |

Measure **p50, p95, and p99** for latency, throughput, allocation rate, and GC; if a real collector is involved, measure bytes/s and ingestion time. Keep the payload, exception count, and stack depth identical when comparing.

### 9.2. JMH benchmark template

JMH helps avoid many pitfalls from warm-up, JIT, and Dead Code Elimination. The template below is a **benchmark class**, not a standalone Java program you can run with just `javac`: running it requires a project with JMH dependencies and annotation processing properly configured.

```java
package example;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3)
@Measurement(iterations = 5)
@Fork(2)
public class StackTraceBenchmark {
    @Benchmark
    public Exception captureOnly() {
        return new Exception("sample");
    }

    @Benchmark
    public StackTraceElement[] captureAndReadFrames() {
        return new Exception("sample").getStackTrace();
    }

    @Benchmark
    public String captureAndFormatInMemory() {
        Exception e = new Exception("sample");
        StringWriter buffer = new StringWriter();
        PrintWriter out = new PrintWriter(buffer);
        e.printStackTrace(out);
        out.flush();
        return buffer.toString();
    }
}
```

These benchmarks progressively include more work (capture → capture + read frames → capture + format text); **they are not three independent measurements from which you can subtract two numbers to deduce the exact cost of each API**. Quantitative results depend on stack depth, memory, and the JVM; `StringWriter` itself does not reflect filesystem or network costs.

To run it, use compatible versions of `jmh-core` and `jmh-generator-annprocess`, ensure the annotation processor has generated `META-INF/BenchmarkList` metadata, and then run `org.openjdk.jmh.Main` via the classpath/JAR built by the project. Reference actual JMH results and environment specifications rather than publishing numbers from a single run as a universal guarantee.

### 9.3. Measuring in a real application

Once you have microbenchmark numbers, continue with:

1. CPU profiling (Java Flight Recorder/JFR or a suitable profiler) to see time spent in `Throwable.fillInStackTrace`, stack walking, formatting, encoders, and appenders.
2. Allocation/GC profiling: counts of `Throwable`, `StackTraceElement`, `String`, buffers, and log events.
3. Comparing under the same traffic/error rate, log level, and sink; avoid comparing a dev environment writing to console against prod sending to a different collector.
4. Monitoring async queues, drop counts, producer wait times, and drain time on shutdown if applicable.
5. Ensuring tests do not expose production data and do not create uncontrolled load effects.

**Do not put assertions like `assertTrue(elapsedNanos < 1000)` in functional JUnit tests**. JVM speed, scheduler, GC, and CI machines vary; use JMH for quantitative comparisons and JUnit for verifying correct/incorrect behavior.

## 10. Testing to Prevent Optimizations from Losing Error Information

Stack trace optimization must preserve the diagnostic contract. A test suite should verify:

- **When the level is disabled:** expensive diagnostic exception constructors guarded by `isDebugEnabled` or an appropriate supplier do not run; this can be checked with a counter like in `StackTraceCostDemo`.
- **When a real error is logged:** the appender receives the right `Throwable`, `cause`, and message; not just `exception.toString()` if a stack trace is required.
- **When going through an async appender:** the log has been consumed by the worker before asserting; use a test sink with a `BlockingQueue`/latch and timeout, avoiding `Thread.sleep`.
- **When caller location is enabled:** the class/file/line comes from the source thread per the backend's contract; specific tests can check the class without hardcoding line numbers that shift as code changes.
- **When rate limiting/sampling:** results match the agreed policy; mandatory events are not dropped.
- **When logging repeated errors:** the application does not recreate multiple synthetic stack traces in hot code paths; events retain enough IDs for correlation.
- **When formatting exception chains:** the root cause and important causes remain visible; investigation-critical information is not lost due to trace truncation.
- **When protecting data:** file paths, exception messages, request context, and suppressed exceptions do not accidentally contain tokens or private data.

For log-capturing tests, attach a dedicated appender to a specifically named logger, detach the appender, and restore level/MDC in `finally`. Tests sharing a logger/backend should not mutate the root configuration in parallel unless properly isolated.

## 11. Common Mistakes When Evaluating Stack Trace Cost

| Misconception | Reality | How to Handle It |
| --- | --- | --- |
| "If DEBUG logging is off, `new Exception` in an argument is free" | Java still evaluates the argument | Guard before constructing a synthetic trace |
| "`throw e` refreshes the stack at the rethrow site" | An exception's trace is normally tied to creation time | Preserve the cause, log appropriate context |
| "Having `%logger` already gives the caller line number" | Logger name and caller location are different data | Enable file/line only when needed |
| "Async logging eliminates all stack trace cost" | Event capture/preparation may still happen on the producer | Measure producer latency, queue, and sink separately |
| "`printStackTrace` just fetches a pre-built String" | It must format frames, cause/suppressed, and write to a writer | Measure capture, formatting, and I/O separately |
| "Wrapping errors at every layer gives more information for free" | Creating new exceptions and duplicate logs increases cost | Wrap only when adding a new contract/context; log fully at the boundary |
| "Stackless exceptions are always better" | Diagnostic information is lost | Use intentionally for pre-designed signals |
| "One local benchmark is the standard nanosecond cost" | JIT, CPU, stack depth, GC, and backend differ | Run JMH multiple times + profile real workloads |
| "Just turning off TRACE/DEBUG removes all sensitive logs" | `INFO/ERROR` and exception messages can also leak data | Inspect content and redact at the sink |
| "The longer the logged stack, the easier the incident is to investigate" | Repeated data can obscure the main signal, increasing cost and storage fees | Use correlation IDs, error categorization, and selective cause retention |

### Balancing performance and investigability

When optimization is needed, prioritize in a reasoned order:

1. Verify that repeated errors are actually occurring and stack traces are consuming significant CPU/GC/I/O.
2. Eliminate **synthetic traces** in disabled log branches and unnecessary expensive message builders.
3. Avoid logging a full exception at every layer; keep one context-rich log at the key boundary.
4. Optimize caller location patterns in high-volume logging spots; do not strip stacks from critical errors just to save cost.
5. Consider sampling/rate limiting, log aggregation, size limits, and pipelines aligned with operational policy.
6. Re-measure in an equivalent environment after changes, while verifying that diagnostic information remains complete.

## 12. Takeaways

**A stack trace does not have just one cost.** A `Throwable` typically captures the stack when created; `getStackTrace()` may materialize frames; formatters build text/JSON; appenders handle I/O. Caller location separately may require a stack walk right on the logging path, which is especially notable when using async loggers.

Full stacks should be logged for important errors, but avoid creating synthetic exceptions on hot paths, avoid unnecessary formatting/capturing when a level is disabled, and avoid duplicating the same error across multiple layers. Use guards/lazy APIs appropriate to your version, configure caller data intentionally, and measure with a profiler/JMH under realistic load before concluding which solution is optimal.
