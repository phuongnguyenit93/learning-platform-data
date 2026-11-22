# Omitted Stack Traces and JVM-Dependent Optimizations in Java

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **a stack trace abbreviated during display** from **a stack trace that is genuinely empty or unrecorded**.
- Explain the meaning of the `... N more` line in `Throwable.printStackTrace()` when a cause or suppressed exception is present.
- Understand the cost mechanics of creating, capturing, and displaying stack traces, especially on frequently executed error paths.
- Recognize the optimization commonly known as **FastThrow** in HotSpot, associated with the `-XX:+OmitStackTraceInFastThrow` option, and understand why this behavior should not be treated as a general guarantee across all JVMs.
- Distinguish internal JVM optimizations from **explicitly disabling the writable stack trace** in a custom `Throwable` class.
- Diagnose cases where logs show only the error name or a stack trace is missing frames: inspect the `getStackTrace()` API, logging approach, JVM configuration, and reproduction conditions.
- Balance performance and observability: avoid using exceptions for frequent control flow, and do not arbitrarily strip traces from important errors.
- Write and run Java 17+ examples with deterministic results without relying on whether the JIT triggers FastThrow.

**Scope:** Java Core Exceptions, performance and diagnostic aspects. The `-XX` options mentioned are options of **HotSpot/OpenJDK-compatible** runtimes, not part of the Java SE syntax or contract shared across all JVMs.

## 2. What is a stack trace, and when is it created?

In Java, `Throwable` stores information related to the execution location when the exception is created or when `fillInStackTrace()` is called under normal mechanisms. When throwing a pre-created `Throwable`, the JVM does not automatically capture a new trace on every `throw`.

Example:

~~~java
IllegalStateException failure = new IllegalStateException("invalid");
throw failure;
~~~

This is an **illustrative code snippet** inside a method permitted to throw `IllegalStateException`. The stack trace of `failure` normally reflects **where the exception object was instantiated**, not necessarily the `throw failure` line if the two locations differ.

Each `StackTraceElement` can contain the class name, method name, file name, line number, and module/class-loader-related information in supported Java versions. However, a frame may lack a line number or source file information if the runtime does not provide sufficient data.

Common operations:

| API | Meaning |
| --- | --- |
| `new IllegalStateException("...")` | Creates an exception; in normal cases, captures the execution trace |
| `throw exception` | Throws the object; there is no guarantee of automatically capturing a new trace when rethrowing |
| `exception.getStackTrace()` | Retrieves the `StackTraceElement[]` array currently exposed by the exception |
| `exception.printStackTrace()` | Prints the exception, frames, cause chain, and suppressed exceptions using the JDK's display format |
| `exception.getCause()` | Retrieves the underlying cause linked as the cause |
| `exception.getSuppressed()` | Retrieves retained secondary exceptions, such as resource-closing errors |
| `exception.fillInStackTrace()` | Re-records the stack trace at the current call site when writable, altering the stored trace |
| `exception.setStackTrace(elements)` | Replaces the published stack trace elements if writing is permitted |

**Do not equate** the frame array in `getStackTrace()` with the text printed by `printStackTrace()`. Printed text may apply abbreviation rules or be truncated by a log collection system.

## 3. Three phenomena of “not seeing the full stack trace”

Even when seeing the same short log output, you may be encountering very different root causes.

| Phenomenon | Nature | How to check |
| --- | --- | --- |
| Log shows `... N more` | `printStackTrace` abbreviates **common frames** between the exception and its cause/suppressed exception | Read the cause, compare the `getStackTrace()` arrays, and inspect the earlier part of the log |
| `getStackTrace().length == 0` | The exception may not record frames: custom `Throwable` design, JVM optimization for certain errors, or other configuration/adjustments | Inspect the exception class, how it is created, runtime, flags, and reproducibility |
| Log only records `exception.getMessage()` or is truncated | The logging/collector system did not render the full `Throwable` object | Compare the log with `getStackTrace()`, check logger/formatter configuration and size limits |

A fourth case is **a stack trace that has some frames, but fewer than expected**. The cause may lie in when the object was created, how it was rethrown, trace-rewriting methods, or capture/display limits. Do not automatically attribute every short trace to the JIT.

If you want to know whether frames were genuinely lost or simply not displayed, a reasonable first step is to check `getStackTrace().length` on **the exception object itself** before drawing conclusions.

## 4. The `... N more` line: abbreviated on print, not necessarily lost data

When one exception wraps another, the bottom portion of both stack traces often overlaps because they passed through the same outer calls.

Illustrative structure example:

~~~text
java.lang.RuntimeException: Unable to process
    at Example.service(Example.java:20)
    at Example.main(Example.java:30)
Caused by: java.lang.IllegalStateException: Corrupted data
    at Example.repository(Example.java:10)
    at Example.service(Example.java:18)
    ... 1 more
~~~

This is an **illustrative formatting example**, not the exact stdout of a program. In traditional JDK printing, `... 1 more` means **the last frame of the cause matches the tail of the enclosing stack trace being printed**, so that frame does not need to be repeated verbatim.

Mechanism:

1. `printStackTrace` prints the outer exception's information.
2. When printing the cause, it finds trailing elements of the cause that match the trailing elements of the nearest enclosing stack trace.
3. Trailing duplicate frames may be replaced with a `... N more` line.
4. The cause's `getStackTrace()` array may still contain all of those elements.

If the cause itself has a cause, each level may be abbreviated relative to the trace enclosing it. Suppressed exceptions may also be displayed with indentation and common-frame abbreviation.

**`... N more` is not proof of FastThrow or lost stack traces in the JVM.** It is a display format to reduce repetition. If you need to inspect the original frame count, read `getStackTrace()` directly on the exception at the corresponding level.

### When does `... N more` not appear?

If there are no trailing common frames, there may be no abbreviation line. If a logger uses a custom format, it may also choose to render differently from `printStackTrace`. Therefore, the presence or absence of this line should not be treated as a mandatory requirement across all logging systems.

## 5. Standalone Java 17 example: abbreviated print output while the cause still retains frames

Save the file **CommonFramesDemo.java**:

~~~java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.regex.Pattern;

public class CommonFramesDemo {

    static void repository() {
        throw new IllegalStateException("bad data");
    }

    static void service() {
        try {
            repository();
        } catch (IllegalStateException original) {
            throw new RuntimeException("service failure", original);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (RuntimeException outer) {
            Throwable cause = outer.getCause();
            int frameCountBefore = cause.getStackTrace().length;

            StringWriter buffer = new StringWriter();
            outer.printStackTrace(new PrintWriter(buffer));
            String rendered = buffer.toString();

            boolean abbreviated = Pattern
                    .compile("\\.\\.\\. \\d+ more")
                    .matcher(rendered)
                    .find();

            System.out.println("Outer has frames: "
                    + (outer.getStackTrace().length > 0));
            System.out.println("Cause has frames: "
                    + (frameCountBefore > 0));
            System.out.println("Print has Caused by: "
                    + rendered.contains("Caused by: "));
            System.out.println("Print abbreviates common frames: "
                    + abbreviated);
            System.out.println("Cause frames still available: "
                    + (cause.getStackTrace().length == frameCountBefore));
        }
    }
}
~~~

Compile and run on Java 17:

~~~bash
javac -encoding UTF-8 CommonFramesDemo.java
java CommonFramesDemo
~~~

**Expected stdout in standard Java 17 printing:**

~~~text
Outer has frames: true
Cause has frames: true
Print has Caused by: true
Print abbreviates common frames: true
Cause frames still available: true
~~~

Explanation:

- `repository()` creates `IllegalStateException`; `service()` catches it and creates `RuntimeException` with `original` as the cause.
- The stack traces of the wrapper and the cause share a common call tail, so standard printing abbreviates the duplicate frames.
- Building the string via `StringWriter` does not modify the cause's stack trace array.
- The program **does not require the JIT** and does not attempt to trigger any special HotSpot optimization.
- The final check line shows that text abbreviation does not erase the cause's `getStackTrace()` array.

**Portability note:** the `... N more` notation is the familiar rendering of `Throwable.printStackTrace` on standard JDKs; external logging systems may render in a different format. The example targets Java 17 with standard printing, not an arbitrary text protocol across all JVMs/loggers.

## 6. When the stack trace is genuinely empty: explicitly creating an exception without recording a trace

Java provides a protected constructor on `Throwable` and suitable subclasses with the signature:

~~~java
Throwable(String message, Throwable cause,
          boolean enableSuppression,
          boolean writableStackTrace)
~~~

The signature above **illustrates the protected API**, not a `Throwable` instantiation call in complete code.

In a custom exception class, you can use:

~~~java
public final class LightweightException extends RuntimeException {
    public LightweightException(String message) {
        super(message, null, true, false);
    }
}
~~~

This is a **standalone class**; save it as `LightweightException.java` if used separately. The `writableStackTrace=false` parameter instructs not to record a stack trace for the new object, so `getStackTrace()` returns an empty array. Subsequent calls to `fillInStackTrace()` and `setStackTrace(...)` do not restore frames in the normal way on an object whose writable stack trace has been disabled.

**This is a design decision of the exception class**, not FastThrow. It takes effect even the very first time the exception is created; it does not need thousands of iterations.

### Trade-offs

Potential benefits:

- Reduces work and overhead associated with capturing a stack trace for the exception object.
- Reasonable on certain well-known, high-frequency control paths that already have sufficient other context.

Drawbacks:

- Loses the exception creation site in its own stack trace.
- Makes it difficult to trace back the call flow when an unexpected error occurs.
- If used broadly, production logs may be reduced to only the error name and message.

**Do not optimize by disabling stack traces for all exceptions.** For rare errors with high diagnostic value, the measurement cost may be far smaller than the incident investigation time lost without a trace.

## 7. Standalone Java 17 example: writableStackTrace=false

Save the file **DisabledTraceDemo.java**:

~~~java
public class DisabledTraceDemo {

    static final class LightweightFailure extends RuntimeException {
        LightweightFailure(String message) {
            super(message, null, true, false);
        }
    }

    public static void main(String[] args) {
        LightweightFailure failure = new LightweightFailure("expected");

        System.out.println("Initial frames: "
                + failure.getStackTrace().length);
        System.out.println("Cause: " + failure.getCause());

        StackTraceElement fake = new StackTraceElement(
                "Example", "method", "Example.java", 42);
        failure.setStackTrace(new StackTraceElement[]{fake});

        System.out.println("Frames after setStackTrace: "
                + failure.getStackTrace().length);

        failure.fillInStackTrace();
        System.out.println("Frames after fillInStackTrace: "
                + failure.getStackTrace().length);

        System.out.println("Message is still present: "
                + "expected".equals(failure.getMessage()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 DisabledTraceDemo.java
java DisabledTraceDemo
~~~

**Exact stdout:**

~~~text
Initial frames: 0
Cause: null
Frames after setStackTrace: 0
Frames after fillInStackTrace: 0
Message is still present: true
~~~

Key takeaways:

- `super(message, null, true, false)` disables stack trace recording for **the `LightweightFailure` object itself**.
- `getMessage()` is still preserved; “having no frames” does not mean the `Throwable` loses all information.
- `getCause()` returns `null` because the example passes a `null` cause. Another custom exception may still retain a cause even when it does not store its own trace.
- `setStackTrace` and `fillInStackTrace` do not recreate frames because the writable stack trace was disabled at construction time.

Note: constructing a custom exception this way is an intentional choice that must be clearly documented in the API design. Do not use it merely to tidy up logs arbitrarily.

## 8. FastThrow: a HotSpot/JIT-dependent optimization

Beyond explicitly disabling the writable stack trace, some HotSpot builds include an optimization commonly called **FastThrow**, associated with the option:

~~~bash
-XX:+OmitStackTraceInFastThrow
~~~

General idea: when the JIT detects certain **implicit runtime exceptions** occurring repeatedly at the same bytecode location, the runtime may take a fast path and omit capturing detailed stack traces for the optimized throws. The goal is to reduce overhead on densely repeated exception paths.

Commonly discussed cases include certain errors arising from bytecode operations or checks, such as:

- `NullPointerException` on a null dereference.
- `ArithmeticException` on integer division by zero.
- `ArrayIndexOutOfBoundsException` on an out-of-bounds array access.
- `ClassCastException` on an invalid cast.

**Do not treat this list as a guaranteed rule that every throw of these classes will have its trace stripped.** The optimization depends on the JVM build, compiler, execution profile, bytecode context, flags, and warm-up state. Not all exceptions of these classes are created via implicit bytecode paths; an exception explicitly created with `new` does not necessarily behave the same way.

### Example of an implicit error

~~~java
static int divide(int divisor) {
    return 10 / divisor;
}
~~~

This is an **illustrative snippet**. Calling `divide(0)` throws `ArithmeticException` due to integer division by zero. If HotSpot optimizes the repeated error path after warm-up, some later throws may differ in cost and stack trace detail compared to the initial throws.

Do not conclude that a JVM has FastThrow merely because a particular exception has a short trace in one run; nor should you conclude that a JVM does not support FastThrow merely because a test loop still shows full traces. Optimization conditions and trigger thresholds **are not a stable Java SE API**.

## 9. HotSpot flags and portability limits

In a HotSpot/OpenJDK environment that supports this flag, you can test the difference by running the same program with:

~~~bash
java -XX:-OmitStackTraceInFastThrow YourMainClass
~~~

This is an **illustrative command syntax**. `YourMainClass` is the actual main class name to substitute when using it; it is not a standalone program of this lesson. The `-` prefix before the flag name disables the option in supporting HotSpot builds. Do not assume this flag exists on every JVM or every Java distribution.

To check which runtime is executing:

~~~bash
java -version
~~~

When investigating on a specific machine, record at least:

- JVM vendor and JDK version.
- Startup options related to optimization and stack traces.
- How the application is run (normal JIT, test harness, container/production configuration).
- Exception type, origin site, and repetition frequency characteristics.
- Raw output from `getStackTrace()` versus logger output.
- Whether a custom exception class with disabled writable stack trace is used, or whether code calls `setStackTrace`.

**Caution:** `-XX:-OmitStackTraceInFastThrow` only addresses one cause related to HotSpot optimization. It will not make a stack trace appear for an exception designed with `writableStackTrace=false`, will not undo a trace replaced by application code, and will not recover log lines truncated by a collector.

### Depth configuration flags and other optimizations

Some JVMs also have options related to the maximum number of frames recorded or diagnostic rendering. Exact names, default values, and meanings may vary by implementation/version. When changes are needed, consult the documentation and flag details of **the exact JVM being run**. Do not copy a set of `-XX` parameters from an old guide and treat them as a universal Java rule.

## 10. FastThrow probe example: output is not guaranteed to be identical

If you want to probe a specific HotSpot build, you can use the following program. This is **an observational probe**, not an assertion test proving FastThrow must definitely activate.

Save the file **FastThrowProbe.java**:

~~~java
public class FastThrowProbe {

    static int divideBy(int value) {
        return 100 / value;
    }

    public static void main(String[] args) {
        int total = 0;
        int emptyTraces = 0;

        for (int i = 0; i < 200_000; i++) {
            try {
                divideBy(0);
            } catch (ArithmeticException error) {
                total++;
                if (error.getStackTrace().length == 0) {
                    emptyTraces++;
                }
            }
        }

        System.out.println("Caught: " + total);
        System.out.println("Empty traces range valid: "
                + (emptyTraces >= 0 && emptyTraces <= total));
        System.out.println("Observed empty traces: " + emptyTraces);
    }
}
~~~

Run with Java 17+:

~~~bash
javac -encoding UTF-8 FastThrowProbe.java
java FastThrowProbe
java -XX:-OmitStackTraceInFastThrow FastThrowProbe
~~~

The first two lines of stdout always have the form:

~~~text
Caught: 200000
Empty traces range valid: true
~~~

The third line is an **actual measurement**, with no fixed stdout value that can be promised in advance:

~~~text
Observed empty traces: <measured count from 0 to 200000>
~~~

The line in the text block above is a **format illustration template**, not an exact stdout line; the program will print an integer. Depending on the runtime, optimization level, execution mode, and JDK version, the value may be 0 or greater than 0.

**Do not use the iteration count of 200,000 as a guaranteed reproduction formula.** The JIT might not generate the optimized throw path in a given environment. Calling `getStackTrace()` also adds overhead to the probe and can affect optimization/observation profiles. The goal is simply to create a measurable probe on a real machine.

If the command with `-XX:-OmitStackTraceInFastThrow` is rejected by the JVM, that indicates you need to consult the documentation for the current runtime, not that Java SE is “broken”. When comparing, keep the same source code, the same workload pattern, and record the runtime options.

## 11. NPE messages and diagnostic differences

Modern Java can provide more detailed messages for certain implicitly thrown `NullPointerException`s. This message is influenced by the runtime and diagnostic configuration. If an exception is created on a fast path that omits the stack trace, the level of message detail may differ from a normal throw.

The takeaway **is not** to memorize a particular NPE message string:

- Do not rely on `NullPointerException.getMessage()` text to define business contracts.
- Do not assume every NPE has a helpful message or the same format.
- An NPE explicitly created with `new NullPointerException("...")` differs from an NPE detected by the JVM at a dereference operation.
- In logging systems, preserve the exception type, operation context, and correlation information; messages may change across JDK versions.
- If you see an NPE missing its trace on a hot path, consider both the logging policy and possible HotSpot optimization, rather than suspecting only wrapper-creation bugs.

When diagnosing buggy code, find the origin from a trustworthy trace, reproduce in a configuration with full observability, and inspect the relevant inputs/state. Do not fix code based on the assumption that “every NPE belongs to the same line”.

## 12. Other reasons logs appear incomplete

### 12.1. Logging only the message

~~~java
logger.warning(error.getMessage());
~~~

This is an **illustrative snippet** assuming existing `logger` and `error` variables. A call that passes only the message will not automatically record the cause chain or stack trace. An under-informative log entry **does not prove the exception lost its stack trace**.

With `java.util.logging.Logger`, when data policies permit, you can pass the `Throwable` itself:

~~~java
logger.log(java.util.logging.Level.SEVERE,
        "operation.failed", error);
~~~

This is also an **illustrative snippet**. The logger and formatter determine how it is rendered; check the configuration, as stack traces or technical messages may contain sensitive information.

### 12.2. Logger or log collector size limits

Many logging systems impose limits on character count, line count, frame count, or record size; some UIs expand only the first part of a trace. If output is truncated at the display/collection layer, changing JIT flags will not fix it. Inspect raw logs, formatter settings, transmission limits, and the observability UI.

### 12.3. Exception created elsewhere

~~~java
static final RuntimeException CACHED =
        new RuntimeException("cached");

static void fail() {
    throw CACHED;
}
~~~

This is an **illustrative snippet**. The stack trace of `CACHED` typically reflects where it was initialized during class initialization, rather than pinpointing the exact site each time `fail()` rethrows that object. Do not reuse an exception with a trace for optimization without understanding that you lose the ability to tie errors to each occurrence.

### 12.4. Application modifying the stack trace itself

~~~java
error.setStackTrace(new StackTraceElement[0]);
~~~

This is an **illustrative snippet** with an existing `error`. If the exception allows modifying its trace, this call replaces the published array with an empty one. This is not a JIT optimization, but an intentional action by the application or a library.

### 12.5. Disabling the writable stack trace

A custom `Throwable` class may use the four-argument constructor with `writableStackTrace=false`. In this case, you must change the class design or how the exception is created if you want frames; simply toggling a HotSpot flag cannot restore them.

### 12.6. Abbreviating cause/suppressed on print

The `... N more` line only omits trailing duplicates. Many people mistake this for an empty trace and waste time tuning unrelated JVM options.

## 13. How to diagnose when a stack trace appears missing

Follow a process from least invasive to most invasive:

1. **Identify the object being observed.** Is it the root exception, a wrapper, a cause, or a transformed message?
2. **Check the log format.** Are there `Caused by`, `Suppressed:`, `... N more`, or signs of truncation due to line limits?
3. **Measure the actual frame count** using `error.getStackTrace().length` in a diagnostic environment, if you have access to the `Throwable` object.
4. **Inspect the cause chain in a controlled way.** A wrapper with frames but an empty cause, or vice versa, are two distinct situations.
5. **Inspect the exception class.** Does it have a constructor disabling the writable stack trace, override `fillInStackTrace()`, call `setStackTrace()`, or cache instances?
6. **Check the logging call.** Is it passing the `Throwable` or only `getMessage()`? Does the logger/collector limit frame counts?
7. **Record the JVM environment** using `java -version` and runtime options. Were there recent JDK or JIT mode changes around the time the issue appeared?
8. **If HotSpot FastThrow is suspected,** reproduce in a controlled environment and compare with a configuration supporting `-XX:-OmitStackTraceInFastThrow`.
9. **If JVM truncation is still suspected,** check the documentation of the exact runtime for stack trace depth limits and related settings.
10. **Ensure log security:** do not expose raw production stack traces containing sensitive data to public channels just for testing.

### Safe inspection pattern

~~~java
Throwable cause = error.getCause();
System.out.println("Top-level type: " + error.getClass().getName());
System.out.println("Top-level frames: " + error.getStackTrace().length);
System.out.println("Has cause: " + (cause != null));
if (cause != null) {
    System.out.println("Cause frames: " + cause.getStackTrace().length);
}
~~~

This is an **illustrative snippet**, assuming `error` already exists. The goal is to distinguish the wrapper's trace from the cause's trace; do not print sensitive technical messages to public output.

A check of `getStackTrace().length == 0` only describes the object's current state; it does not by itself prove the root cause. When you lack access to the actual `Throwable` and only have formatted logs, be cautious about drawing conclusions regarding JVM behavior.

## 14. The relationship between performance and diagnosability

Creating and handling exceptions can consume resources:

- Allocating the exception object.
- Capturing stack information when the implementation provides a writable trace.
- Constructing messages and creating wrappers.
- Materializing/copying frames when calling `getStackTrace()`.
- Formatting, writing, and transmitting stack traces through the logger/collector.
- I/O and storage costs of very long or repeated logs.

The cost depends on the runtime, JIT, call stack depth, throw frequency, logger, and collection pipeline. Do not assert a fixed figure such as “exceptions are always 100x slower” without measuring your actual workload.

**The first thing to optimize** is usually avoiding exceptions to represent frequent, expected/success-like branches. For example, if data may legitimately be missing in business logic, consider an API returning `Optional`, a structured result type, or checking conditions without throwing an exception every time. Do not turn genuine errors into fake success values just to boost throughput.

### When might a lightweight exception be considered?

- A **very hot** path where the state is clearly modeled as an internal signal.
- Appropriate benchmarks have been run and confirmed stack-capture overhead is the bottleneck.
- Another mechanism exists to record sufficient context when a real error occurs.
- Maintainers accept the diagnostic limitations and the API clearly documents the handling contract.

Even when using lightweight exceptions, avoid passing them across user-facing service boundaries without correlation information, error codes, and context. Truly unexpected exceptions should prioritize diagnosability.

### Why measure before disabling traces?

If an error occurs once every few hours, the cost of creating a stack trace is likely negligible, whereas losing the call stack makes investigation far more time-consuming. Conversely, throwing millions of exceptions per second can put pressure on GC and logging; even then, the better optimization is sometimes changing control flow, not disabling traces.

When benchmarking exceptions, avoid common pitfalls:

- Comparing two code snippets that do not perform the same work.
- Failing to warm up the JIT and treating measurements as steady state.
- Printing stack traces to the console inside a loop and assuming you are measuring exception creation cost alone.
- Failing to distinguish implicit JVM-thrown exceptions from exceptions explicitly created with `new`.
- Running a loop on one machine and extrapolating the result to all JVMs.
- Ignoring GC, allocation rate, tail latency, and log quality.

For serious benchmarking, you can use JMH in a properly configured project; JMH is not a built-in API available via `javac` alone in Java SE. Regardless of the tool used, record the runtime version, JIT flags, load, and collection methodology.

## 15. Logging: keeping essential information while avoiding floods

When exceptions repeat densely, logging a full stack trace for every occurrence can overload the logging system. Appropriate measures may include:

- Using metrics to count errors by type and component, instead of storing millions of identical stack traces.
- Applying intentional sampling or rate limiting at the logging/telemetry layer; retaining traces for sample errors needed for investigation.
- Recording correlation IDs, operation names, exception types, and safe context to tie errors to requests.
- Preserving the cause chain for important error samples; do not log only the message if root-cause debugging is needed.
- Never exposing raw stack traces or infrastructure details to end users or public logs.

**Sampling performed by the application/logger is different from JVM FastThrow.** With sampling, the `Throwable` may still retain its trace even though it is not sent to the collector every time. With FastThrow, the optimized exception path may not store a detailed trace at all. The two phenomena must be inspected and addressed at separate layers.

If a system is losing diagnostic information, rather than enabling full stack traces for every production request indefinitely, reproduce the issue in a controlled environment or apply a logging mode bounded by time, traffic volume, and access permissions.

## 16. Stack traces of causes and suppressed exceptions also matter

A wrapper can retain a cause:

~~~java
try {
    repositoryCall();
} catch (IllegalStateException original) {
    throw new RuntimeException("Operation failed", original);
}
~~~

This is an **illustrative snippet** with `repositoryCall()` defined in the application. The wrapper and the cause are **two separate objects** with their own traces. If the wrapper has a trace while the cause was optimized to empty, the logger may print the wrapper with full frames but a very short cause.

Conversely, if the wrapper is a lightweight exception without a writable stack trace yet retains a normal cause, the cause's trace can still be useful. Therefore, when investigating, **do not inspect `getStackTrace()` only on the outermost exception**.

With `try-with-resources`, an exception thrown while closing a resource may be stored in `getSuppressed()` of the primary error. `printStackTrace` has its own way of displaying suppressed exceptions and may also abbreviate common frames. A `... N more` line under `Suppressed:` does not mean the resource-closing error has vanished.

Do not manually add suppressed exceptions merely to “compensate” for missing traces. Cause and suppressed exceptions represent different error relationships; it is more important to preserve the right objects and their semantics.

## 17. fillInStackTrace and reusing Throwable instances

`Throwable.fillInStackTrace()` can update an exception's trace to reflect **the new call site** if the object permits writing its stack trace. It does not restore original frames omitted by FastThrow or truncated by a log collector.

Illustrative example:

~~~java
RuntimeException error = new RuntimeException("cached");
error.fillInStackTrace();
throw error;
~~~

This is a **code snippet** inside a Java method. Calling `fillInStackTrace` can alter the stored trace. Do not use this trick to try to recover the exact “true origin” of a previously occurring error; it only records the stack at the current call site according to the implementation.

If an exception object is reused across multiple threads, reading/writing its trace or context can cause confusion in logs; simply sharing a `Throwable` instance also does not mean each `throw` will record a complete, separate history for every error occurrence.

In general, for truly exceptional errors, create an appropriate exception and preserve its cause rather than reusing a shared instance just to reduce allocation. If a state is expected and frequent, an appropriate result type is clearer.

## 18. Testing stack traces reliably

Test **essential properties** rather than capturing verbatim stack traces and asserting exact line numbers.

| Goal | How to verify |
| --- | --- |
| Normal exception has a trace | Assert `getStackTrace().length > 0` under normal execution |
| Cause is preserved | Assert `wrapper.getCause() == original` |
| Cause retains frames after printing | Compare `getStackTrace().length` before and after `printStackTrace` |
| Lightweight exception has no writable trace | Assert `getStackTrace().length == 0` |
| Error ordering in application | Assert deterministic type/code/cause and context, without depending on stack line numbers |
| HotSpot FastThrow | Observe/benchmark on the target runtime; **do not** assert that a specific iteration must have an empty trace |
| Truncated logger | Compare raw `Throwable` data against actual logger/collector output |
| Public response | Assert it does not contain stack traces, file paths, hostnames, or secrets |

With JUnit 5, the following is an **illustrative snippet inside a test class with JUnit 5 and appropriate imports**:

~~~java
RuntimeException original = new RuntimeException("low-level");
RuntimeException wrapper = new RuntimeException("high-level", original);

assertSame(original, wrapper.getCause());
assertTrue(original.getStackTrace().length > 0);
assertTrue(wrapper.getStackTrace().length > 0);
~~~

There is no need to assert a specific frame count like 2 or 3 if the goal is simply preserving the cause: compilers, test frameworks, and call sites can change the frame count.

Do not write a unit test requiring that “after 10,000 `ArithmeticException`s, the stack trace must definitely be empty.” That turns an implementation's optimization detail into a business-logic correctness condition and makes tests flaky across JDK upgrades.

## 19. Common mistakes and fixes

1. **Seeing `... N more` and assuming the JVM deleted frames:** check the cause and `getStackTrace()`; it is usually just print abbreviation.
2. **Seeing an empty trace and immediately blaming FastThrow:** there are other causes such as a custom `Throwable` or a `setStackTrace` call.
3. **Assuming FastThrow applies to all exceptions:** the mechanism depends on bytecode, JIT, runtime, and specific conditions.
4. **Expecting HotSpot flags to work on every JVM:** `-XX` options are not a portable Java SE API contract.
5. **Using a fixed loop count to test FastThrow:** optimization has no guaranteed threshold for your program.
6. **Logging only `e.getMessage()`:** the stack trace is missing because of the logging call, not because the JVM did not capture it.
7. **Logging unlimited full traces for errors occurring millions of times:** can increase I/O, storage usage, and impact latency.
8. **Disabling writable stack traces to fix oversized logs:** can strip away data needed to investigate real errors.
9. **Creating one exception and throwing it repeatedly expecting the trace to update:** the trace may retain the original creation site.
10. **Calling `fillInStackTrace()` after an error and treating it as the original trace:** this operation can replace the trace with the new call site.
11. **Ignoring cause/suppressed exceptions:** the root error may be at a different level than the wrapper.
12. **Assuming the logger always preserves all data:** formatters, sampling, and collectors can shorten output.
13. **Treating stack traces as a stable public API:** class names, line numbers, formatting, and frame counts can change with optimizations or version upgrades.
14. **Exposing raw traces to end users:** can leak file paths and implementation details; return safe error codes/messages and a correlation ID instead.
15. **Measuring exceptions with benchmarks lacking warm-up and environment control:** results are unreliable for architectural decisions.
16. **Automatically ignoring exceptions without traces:** the error can still be severe; classify by semantics and actual impact.
17. **Equating `getStackTrace().length == 0` with `getCause() == null`:** these are two independent properties.
18. **Blaming every missing trace on a JVM bug:** check source code, logging configuration, exception creation site, and environment conditions first.

## 20. Operational checklist

When encountering an exception log that appears to be missing a stack trace, ask:

- Is this `... N more` abbreviation from matching trailing frames, or is the object's `getStackTrace()` actually empty?
- Are we looking at the wrapper, the cause, or a suppressed exception?
- Did the logger receive the `Throwable` or only the message?
- Was the trace truncated by a formatter, UI, or ingestion limit?
- Does the exception have a constructor disabling the writable stack trace, override `fillInStackTrace`, have `setStackTrace` called on it, or get cached and reused?
- Is it an implicit runtime error occurring densely on a hot bytecode path in HotSpot?
- Have the JVM version and flags been recorded before comparing?
- If disabling FastThrow for diagnosis, have you confirmed the runtime supports the flag and used a controlled test?
- Have you ensured logs/traces do not leak secrets or sensitive data?
- Is reducing exception cost backed by measurement and free of breaking investigation for critical errors?

**Conclusion:** “Omitted stack trace” does not describe a single phenomenon. The `... N more` line is usually just **abbreviation during printing**; a custom exception may **explicitly omit recording a trace**; and HotSpot may use **the FastThrow optimization** to reduce the cost of certain frequently occurring runtime errors. Identify the exact category of root cause before tuning the JVM or redesigning exceptions. For rare and critical errors, accurate diagnosability is usually worth far more than an unmeasured micro-optimization.
