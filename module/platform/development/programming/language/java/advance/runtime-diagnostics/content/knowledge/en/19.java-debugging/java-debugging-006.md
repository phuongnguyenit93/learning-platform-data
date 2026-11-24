# 19.6 Investigating Exceptions at the Origin and Distinguishing Handled Exceptions

## Goal and Scenario

When debugging a Java application, an IDE may pause at a `throw` line or exception constructor even though the request succeeds, the program keeps running, and no error is logged. Conversely, an exception that genuinely fails a task can be captured by a framework, `Future`, or thread pool and surface only as a wrapper exception somewhere else.

Therefore, **"an exception was created or thrown" does not equate to "an unhandled error"**, and **"caught" does not always mean "successfully recovered."**

This lesson teaches how to trace **origin**, **propagation path**, **final handler**, and **actual impact** of exceptions using a Java debugger, stack traces, cause chains, logging, and JFR (Java Flight Recorder). The goal is accurate diagnosis, reducing noise from expected exceptions, and avoiding accidentally hiding serious failures.

After this lesson, you will be able to:

- Distinguish exceptions that are **constructed**, **thrown**, **caught**, **handled via fallback**, **wrapped**, **rethrown**, **held in a future**, **escaping a thread**, and **logged**.
- Set the right **exception breakpoint** in an IDE or use `jdb` to pause near the throw site and inspect local variables, thread, and call stack.
- Read `Throwable.getStackTrace()`, `getCause()`, and `getSuppressed()` to find the root cause without mistaking a wrapper's stack for where the failure began.
- Inspect JFR `jdk.JavaExceptionThrow` cautiously: one event does not prove an exception went unhandled, and on HotSpot it can even be recorded when constructing an exception **without actually throwing it**.
- Distinguish recovered errors from "swallowed" errors, errors translated into failure outcomes, and uncaught errors that may terminate only one thread.
- Practice on Java 17+ with compilable/runnable programs and verified output.

**Scope:** Java SE 17+; JFR, `jdb`, and JDWP examples use HotSpot/OpenJDK. IntelliJ IDEA, Eclipse, or other tools may name break-on-throw features differently. JFR event counts, line numbers, stack frames, and framework behavior vary by JVM/version and are not fixed stdout in this lesson.

## 1. Lifecycle of an Exception: Construct, Throw, Catch, and Outcome

Consider the processing chain:

~~~text
Invalid input
       |
       v
new NumberFormatException(...)        [CONSTRUCT object]
       |
       v
throw exception                       [THROW]
       |
       v
exception unwinds call stack
       |
       +--> caught near origin?
       |       |
       |       +--> valid fallback    [HANDLED AND RECOVERED]
       |       +--> log then rethrow  [NOT YET RESOLVED]
       |       +--> wrap cause        [TYPE/CONTEXT TRANSLATED]
       |       +--> swallow & wrong   [LIKELY A BUG]
       |
       +--> boundary/framework layer?
       |       |
       |       +--> HTTP 4xx/5xx, failed future,
       |            retry or message NACK  [CAUGHT, YET TASK FAILED]
       |
       +--> escapes Thread.run()
               |
               v
          UncaughtExceptionHandler    [THREAD TERMINATED]
~~~

Key point: a Java `Throwable` is an **object**. You can construct an exception object without ever executing `throw` on it:

~~~java
new IllegalArgumentException("created but not thrown");
~~~

The line above is a valid Java statement, yet **it does not jump control flow into a catch block**. A debugger setting a breakpoint on throw events typically aims to pause when the exception is thrown; other event-recording tools can have broader semantics.

### 1.1 Practical Definitions for Each State

| Concept | Code signal | Impact |
| --- | --- | --- |
| **Constructed** | `new IOException("...")` | Object exists; not necessarily thrown |
| **Thrown / raised** | `throw ex;` or an API throws on your behalf | Normal execution is interrupted to search for a matching handler |
| **Caught** | `catch (X ex) { ... }` | A handler matched; unclear yet whether resolved or merely rethrown |
| **Recovered / handled** | `catch` chooses a safe fallback and returns a valid result | Work can proceed normally per policy |
| **Translated / wrapped** | `throw new ServiceException("...", ex);` | New exception propagates; cause preserves the original reason |
| **Rethrown** | `throw ex;` | Same object continues propagating |
| **Swallowed** | Empty `catch` or returning a fake "success" value | Exception disappears from logs while the bug may persist |
| **Captured in async result** | `CompletableFuture`/`Future` completes exceptionally | Does not necessarily escape the worker thread; error may surface only when observing the future |
| **Uncaught at thread boundary** | Exception escapes `Thread.run()` | That thread terminates; JVM/process does not necessarily exit |
| **Logged** | Logger writes message/stack | Observation only; logging proves neither handled nor unhandled |

**Never equate** "caught" with "successful." For example, an HTTP controller catches an exception and returns `500 Internal Server Error`: the exception was *caught*, yet the request still *failed*. Or a framework intentionally translates an exception into HTTP 404/400: that may be a valid business outcome, depending on the contract.

## 2. Exception Differs from Error, Checked Differs from Unchecked, Yet Both Require Verifying Impact

- **Checked exceptions**: subtypes of `Exception` excluding `RuntimeException` must be declared/handled per Java rules (e.g., `IOException`). "Checked" does not mean a more severe error.
- **Unchecked exceptions**: `RuntimeException` and `Error` (e.g., `IllegalArgumentException`, `NullPointerException`, `OutOfMemoryError`). The compiler does not require declaring them in `throws`.
- **`Error`** usually signals severe runtime/VM issues; never use `catch (Throwable)` as a default "recover from everything" mechanism. For instance, `OutOfMemoryError` can cause the logging or fallback code itself to fail.
- **Expected exceptions** can be used as control signals by libraries, though repeatedly creating/capturing stack traces at high frequency can still cost CPU/memory. Code changes should be driven by profiles and contracts, not just because a debugger paused often.

A class name alone such as `IllegalStateException` does not tell you whether it is a bug or an expected response. You need **input, code path, handler, and outcome**.

## 3. Setting an Exception Breakpoint to Pause at Throw Time

### 3.1 How Does It Differ from a Regular Line Breakpoint?

A line breakpoint pauses only when a specific source line runs. If you know "the request failed" without knowing whether the exception arose in JDBC, cache, validation, or application code, line breakpoints force you to guess where to stop.

An **exception breakpoint** uses the JVM's debug mechanism to pause when an exception of a given type is thrown, typically letting you:

- Enable **caught exceptions** (exceptions with a potential handler) and/or **uncaught exceptions** (exceptions lacking a matching handler as classified by the debugger/JDWP).
- Pause only for a specific class such as `java.lang.NumberFormatException` or its subtypes, rather than every `Throwable`.
- Add package/class filters, conditions, thread filters, and suspend policies per IDE to reduce noise.
- Inspect the current thread, throw location per debugger event, stack frames, and local variables before unwinding.

**Option names and caught/uncaught classification criteria vary by IDE and debug engine.** Therefore, after the debugger pauses, you must still verify the handler and execution outcome. In particular, a framework-level handler can make the IDE treat an exception as "caught" even when the request returns an error.

### 3.2 Workflow with an IDE (IntelliJ IDEA/Eclipse or JDWP-Capable IDE)

1. Run the program in **Debug** mode with debug symbols and source matching the running binary. If source mismatches the actual JAR, line numbers can mislead.
2. Open **Breakpoints → Java Exception Breakpoint** (or IDE equivalent), selecting a specific exception class instead of `java.lang.Throwable` whenever possible.
3. When unsure whether a handler exists, enable **caught + uncaught** for a brief window. If the IDE repeatedly pauses on normal library exceptions, add class filters, conditions, or temporarily disable caught to focus on severe errors; do not confuse "stopped pausing" with "stopped throwing."
4. Reproduce the issue with **fixed inputs and conditions**; record request ID, thread, timestamp, and outcome.
5. When paused, examine exception type/message, **top application frame**, local variables/arguments, invalid state, and caller frame order. If the stack is inside library code, walk up the stack to application code to see what arguments the app passed.
6. Continue stepping or place a line breakpoint at the matching `catch`/handler. Check whether the handler **returns a fallback, retries, wraps, rethrows, or returns a failure response**.
7. Verify the final outcome: HTTP status/body, future result, transaction rollback/commit, message ACK/NACK, metrics, and logs. Only then classify it as successfully recovered, intentionally mapped error, or still uncaught.

**Caution:** "Resume" after the debugger pauses does not mean "ignore" the exception in the program. It simply resumes the JVM thread normally; the exception will still propagate to a handler or escape the thread.

### 3.3 Quick Steps with `jdb`

Java includes the CLI tool `jdb` (JDK) using the Java Platform Debugger Architecture. Example running `ExceptionPathsDemo` in JDB:

~~~sh
jdb ExceptionPathsDemo
~~~

At the `jdb` prompt, you can set an exception breakpoint and run the program per your version's help:

~~~text
catch java.lang.NumberFormatException
run
~~~

`catch` is a **debugger command**, not the `catch` keyword in source; it tells the debugger to pause when that exception is thrown. Use `help`, `where`, `up`, `down`, `locals`, `cont`, and `ignore` accordingly to analyze/resume. Some `jdb` versions offer `catch caught|uncaught|all <exception-class>`; run `help catch` on your version rather than assuming identical syntax across all releases.

When attaching a debugger to a running JVM, JDWP can be enabled at startup. Example **binding loopback only for a lab environment**:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 ExceptionPathsDemo
jdb -attach 127.0.0.1:5005
~~~

The first command runs **in terminal A and waits for the debugger** because of `suspend=y`; the second runs **in terminal B**. In an IDE, use Remote Debug with the same address. **Never expose JDWP to the Internet or bind `0.0.0.0` in production without a secure channel and strict access control**: a debugger has deep privileges to interfere with the process and application data. Attaching/stop-the-world also impacts latency; use only when authorized.

## 4. Four Questions at the Exception Origin

When the debugger pauses, before editing code, answer in order:

1. **What actually went wrong?** For example, `Integer.parseInt("abc")` failed because input violated the contract, or should the caller have validated first? Record exception type and exact input (redacting secrets).
2. **Where was it constructed/thrown?** Trace the stack to application code; from there inspect which callers passed the data or state.
3. **Where is the handler?** Check local `catch`, boundary `catch`, async wrapper, or default uncaught handler. Do not stop investigating merely because you spotted a `catch`.
4. **What is the outcome?** Does the system use a valid fallback, return a validation error, retry, roll back, mark a job failed, or actually drop the request/thread? Compare against the contract.

This is the difference between an **exception event** and an **incident**. A system may throw many `NumberFormatException`s on bad inputs and map them to 400, fully honoring its contract; conversely, a single "swallowed" `IOException` can leave data partially written with zero error logs.

## 5. Stack Traces: Where a Throwable Was Constructed Is Not Always the Current Throw Site

### 5.1 Reading Stack and Cause Properly

On standard `Throwable`s, the stack trace is captured when the object is constructed or when `fillInStackTrace()` is called. Hence a trace from `printStackTrace()` can point to **where the exception was instantiated** rather than every `throw`/`rethrow` statement it passed through. The JVM/debugger can report the actual throw site via breakpoints, distinct from the stack stored in the object.

~~~java
IllegalStateException ex = new IllegalStateException("reused");
throw ex; // Object was created earlier; trace stored in ex may start at creation line.
~~~

This is a **non-standalone snippet**. Avoid constructing and broadly reusing exception instances because it complicates diagnosis, especially across multiple threads. When executing `throw ex` on the same object, do not expect a fresh stack on each throw; when executing `throw new ...`, the new wrapper has its own stack and can retain the old cause.

### 5.2 Wrappers and Cause Chains

~~~java
try {
    readConfig();
} catch (IOException original) {
    throw new IllegalArgumentException("startup failed", original);
}
~~~

This snippet belongs to a method with an appropriate `readConfig()`, with a complete example in section 8. It creates a new exception whose stack starts at the wrapping line, while `getCause()` remains `IOException("config missing")` with its original trace preserved.

To walk the chain:

~~~java
Throwable cursor = error;
while (cursor != null) {
    System.out.println(cursor.getClass().getSimpleName()
            + ": " + cursor.getMessage());
    cursor = cursor.getCause();
}
~~~

This is a **snippet** assuming a `Throwable error` variable. In practice, bound the chain length, guard against abnormal cycles, and use structured logging; never print messages containing tokens/PII. Never assume the last cause is the sole root cause: a single transaction can suffer multiple failures, and the root cause is one clue.

Common wrappers:

| Class/source | Investigation principle |
| --- | --- |
| `CompletionException` from `CompletableFuture.join()` | Inspect `getCause()` for the stage failure; the future may have failed while the thread kept running normally |
| `ExecutionException` from `Future.get()` | Inspect `getCause()`; the executor held the exception for the caller to observe later |
| `InvocationTargetException` from reflective `Method.invoke(...)` | Inspect `getCause()` or `getTargetException()` to reach the exception thrown by the invoked method |
| `ExceptionInInitializerError` | Inspect the cause inside the static initializer; do not fix only the caller that first touched the class |
| `UndeclaredThrowableException` in dynamic proxies | Inspect cause/undeclared throwable and the invoked method's contract |
| Framework-specific wrappers | Read the cause chain alongside boundary mapping (e.g., returning 4xx/5xx), not just the wrapper top frame |

### 5.3 Suppressed Exceptions: An Error Masked by Another Error

In `try-with-resources`, if the body throws an exception and then `close()` also throws, the exception from `close()` is typically **added to `getSuppressed()` on the primary error**, rather than becoming its cause. Do not inspect only `getCause()` when suspecting resource-closing failures.

Save **`SuppressedDemo.java`**:

~~~java
import java.io.IOException;

public final class SuppressedDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        } catch (IOException ex) {
            System.out.println("PRIMARY: " + ex.getMessage());
            System.out.println("SUPPRESSED: "
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Run:

~~~sh
javac --release 17 SuppressedDemo.java
java SuppressedDemo
~~~

Exact stdout:

~~~text
PRIMARY: read failed
SUPPRESSED: close failed
~~~

The program was compiled with `--release 17` and verified. Conclusion: `getSuppressed()` contains "close failed" while "read failed" remains the primary exception. Reading only the root cause or top-level message can miss critical cleanup failures.

## 6. "Caught" Has Three Very Different Outcomes

### 6.1 Valid Recovery

~~~java
try {
    return Integer.parseInt(value);
} catch (NumberFormatException ex) {
    return 8080; // Valid only if 8080 is an intentionally designed fallback.
}
~~~

The snippet above belongs to a method returning `int` with variable `value`. Whether a fallback is right depends on business requirements. For an optional config parameter, defaulting may be reasonable. For payment amounts or security IDs, silently substituting a value can create severe bugs; report invalid input instead.

### 6.2 Caught and Translated into a Failure Outcome

~~~java
try {
    service.execute();
} catch (IllegalStateException ex) {
    // Return error response or mark job FAILED (framework-dependent).
}
~~~

This is a **pseudo-snippet** with an undefined `service.execute()` API; it illustrates an exception that was **caught** yet **the operation failed**. Exception-handling middleware may translate it to HTTP 500, a message consumer may NACK to retry, or a transaction boundary may roll back. Do not mark "handled = success" on dashboards simply because a `catch` block exists.

### 6.3 Swallowed or Logged and Rethrown

~~~java
try {
    updateLedger();
} catch (Exception ignored) {
    // Do nothing; this can be a serious bug.
}
~~~

The snippet above is a pseudo-snippet. Returning success after ignoring an exception can cause **silent data corruption**, even though users see no stack trace. Conversely:

~~~java
try {
    updateLedger();
} catch (Exception ex) {
    logger.error("Update failed", ex);
    throw ex;
}
~~~

This is also a pseudo-snippet (requiring real `logger` and `updateLedger()`). It **caught** the exception without **resolving** it, so the exception keeps propagating to the caller. If every layer does `log + throw`, one failure appears as three or four stack traces and inflates false alerts. In practice, log thoroughly at the **decision-making boundary**, including correlation ID, error type/cause, and outcome; lower layers can add context via exception wrapping while preserving the cause.

**Do not mechanically catch broad `Throwable` or `Exception`.** Catch specifically as suited to the situation, and never swallow `InterruptedException`: if you do not rethrow it, restore the interrupt flag with `Thread.currentThread().interrupt()` and stop work per contract.

## 7. Asynchronous Exceptions: Worker Does Not Die, Yet the Task Still Fails

An error raised inside a `CompletableFuture` stage is usually **stored in the future result** instead of escaping the worker as an uncaught exception. When calling:

~~~java
CompletableFuture<Void> job =
        CompletableFuture.runAsync(() -> {
            throw new UnsupportedOperationException("async failure");
        });

try {
    job.join();
} catch (CompletionException ex) {
    System.out.println(ex.getCause().getMessage());
}
~~~

This is a snippet inside a Java method importing `CompletableFuture` and `CompletionException`. `join()` typically throws `CompletionException` (unchecked) wrapping the stage failure; `get()` uses `ExecutionException` (checked) when completion fails. If the caller **never observes the future**, the app may lack logs and metrics for the failed task even while the pool's worker thread keeps processing other jobs.

Similarly, `ExecutorService.submit(...)` stores errors in `Future` for `get()` to report; this differs from a manually created `Thread.run()` throwing an uncaught exception. Debug at **the lambda/task throw site**, inspect which stage/future holds the error, and check whether `handle`/`exceptionally`/`whenComplete`/`get`/`join` handles it per policy.

An `exceptionally(ex -> fallback)` callback can turn a future into a normal result **if it genuinely recovers**. A `whenComplete` callback that only logs does not automatically turn an exceptional future into a success: the outcome depends on stage logic and semantics.

### 7.1 Uncaught in a Thread Does Not Mean the Whole JVM Dies

Save file **`UncaughtThreadDemo.java`**:

~~~java
public final class UncaughtThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            throw new IllegalStateException("job failed");
        }, "worker-1");
        worker.setUncaughtExceptionHandler((thread, error) ->
                System.out.println("UNCAUGHT: " + thread.getName()
                        + " -> " + error.getMessage()));
        worker.start();
        worker.join();
        System.out.println("MAIN_STILL_RUNNING");
    }
}
~~~

Run:

~~~sh
javac --release 17 UncaughtThreadDemo.java
java UncaughtThreadDemo
~~~

Exact stdout:

~~~text
UNCAUGHT: worker-1 -> job failed
MAIN_STILL_RUNNING
~~~

In the tested run, the exit code was **0**, because `main` completed normally even though the worker threw an uncaught exception. `UncaughtExceptionHandler` is notified **after the exception escapes `run`**, without "rewinding" the failed task. Real programs may need to mark the job failed, restart the worker, or alert monitoring. Never infer from a live process that no uncaught exceptions occurred on other threads.

## 8. Comprehensive Java 17+ Practice: Exceptions Thrown, Caught, and Wrapped

The following program intentionally simulates four distinct paths:

1. Invalid input where the app has a **defined fallback**.
2. Service raises an error and a **boundary catch** reports local failure.
3. `IOException` is **wrapped** into `IllegalArgumentException`, preserving `cause`.
4. An async stage fails, `CompletableFuture` stores the error; `join()` throws `CompletionException` and the caller inspects the cause.

Save file **`ExceptionPathsDemo.java`**:

~~~java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public final class ExceptionPathsDemo {
    private static int parsePort(String input) {
        try {
            return Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            System.out.println("RECOVERED: port=8080");
            return 8080;
        }
    }

    private static void repository() {
        throw new IllegalStateException("database unavailable");
    }

    private static void requestBoundary() {
        try {
            repository();
        } catch (IllegalStateException ex) {
            System.out.println("BOUNDARY_HANDLED: " + ex.getMessage());
        }
    }

    private static void readConfig() throws IOException {
        throw new IOException("config missing");
    }

    private static void loadConfig() {
        try {
            readConfig();
        } catch (IOException ex) {
            throw new IllegalArgumentException("startup failed", ex);
        }
    }

    private static void asyncTask() {
        CompletableFuture<Void> job = CompletableFuture.runAsync(() -> {
            throw new UnsupportedOperationException("async failure");
        });
        try {
            job.join();
        } catch (CompletionException ex) {
            System.out.println("FUTURE_HANDLED: " + ex.getCause().getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("START");
        System.out.println("PORT=" + parsePort("not-a-number"));
        requestBoundary();
        try {
            loadConfig();
        } catch (IllegalArgumentException ex) {
            System.out.println("WRAPPED: " + ex.getMessage());
            System.out.println("ROOT_CAUSE: " + ex.getCause().getMessage());
        }
        asyncTask();
        System.out.println("END");
    }
}
~~~

Compile and run:

~~~sh
javac --release 17 ExceptionPathsDemo.java
java ExceptionPathsDemo
~~~

Exact stdout of the program:

~~~text
START
RECOVERED: port=8080
PORT=8080
BOUNDARY_HANDLED: database unavailable
WRAPPED: startup failed
ROOT_CAUSE: config missing
FUTURE_HANDLED: async failure
END
~~~

Verified with `javac --release 17` and HotSpot JDK 24. Even though multiple exceptions occurred, the program **prints no stack traces to stderr**, because all four paths have matching handlers. Nevertheless, that **does not prove every business operation succeeded**: `repository()` reported unavailable, and `asyncTask()` failed with its error observed.

### 8.1 Using Exception Breakpoints to Trace This Program

Enable caught + uncaught for these types:

- `NumberFormatException` → pauses in `parsePort`; after resuming, `catch` returns 8080. This counts as recovery per the lab's contract.
- `IllegalStateException` → pauses in `repository()`; after resuming, `requestBoundary()` catches and prints the error line. This is **boundary handling**, not a successful service result.
- `IOException` → pauses in `readConfig()`; `loadConfig()` wraps into `IllegalArgumentException`, which `main` later catches. Inspect the wrapper's `getCause()`.
- `UnsupportedOperationException` → pauses inside the lambda running on a worker; afterward `job.join()` throws `CompletionException` on the main thread. Inspect both the worker thread and `main`.
- `CompletionException` → note this is a wrapper from `CompletableFuture` mechanics, not the initial "async failure" root cause.

Set line breakpoints on each **`catch`** block and compare them against exception breakpoints at throw time. The two pause points answer different questions: **"where did it originate?"** and **"who decided how to handle it?"**.

### 8.2 Checklist of Details When the Debugger Pauses

Record a short investigation note without logging secrets:

~~~text
Timestamp / request ID / thread:
Exception class / message:
Creation site (Throwable stack) / actual throw site (debugger):
First relevant application frame:
Input/state causing the exception:
Catch / wrapper / handler chain:
Result: fallback | validation failure | retry | 5xx | failed future | uncaught
Evidence: test output / response code / metrics / logs:
Proposed fix and retest criteria:
~~~

This is a text template to fill out in an issue tracker, not Java code. Timestamps from debugger/JFR/logs must be aligned for timezone and clock skew across processes/hosts/containers.

## 9. JFR: Having `jdk.JavaExceptionThrow` Does Not Mean Thrown or Uncaught

This is a **critical trap**, especially when asked to "distinguish handled exceptions."

Depending on the JDK, JFR provides events such as:

- `jdk.JavaExceptionThrow`: details related to JVM exception creation/raising, including class, message, thread, and stack when recorded.
- `jdk.JavaErrorThrow`: similar for `Error` depending on template.
- `jdk.ExceptionStatistics`: aggregate/periodic counts depending on JDK and config; never use it to prove a specific request failed.

**Caution on actual HotSpot semantics:** in JDK 24 testing, `jdk.JavaExceptionThrow` was recorded **even when code only constructed `new IllegalArgumentException(...)` without executing `throw`**. The event stack begins inside `Throwable`'s constructor; therefore, an event name containing "Throw" **does not guarantee a `throw` expression executed, much less prove the exception went uncaught**. Use a debugger/JDWP or code/control-flow analysis to verify throwing and handler paths.

### 9.1 Enable Events Deliberately; Do Not Assume Default Records Everything

On a JDK supporting `jfr configure`, create a custom template from `default.jfc`:

~~~sh
jfr configure --input default.jfc --output throws.jfc 'jdk.JavaExceptionThrow#enabled=true' 'jdk.JavaExceptionThrow#stackTrace=true'
~~~

Run the demo and capture a short recording to a file:

~~~sh
java '-XX:StartFlightRecording=settings=throws.jfc,filename=throws.jfr,dumponexit=true' ExceptionPathsDemo
jfr summary throws.jfr
jfr print --events jdk.JavaExceptionThrow --stack-depth 12 throws.jfr
~~~

`jfr summary` shows how many events were actually recorded in the file; `jfr print` can display `thrownClass`, `message`, `eventThread`, and `stackTrace`. One test run on HotSpot JDK 24 with this custom template recorded **6 `jdk.JavaExceptionThrow` events**, covering `NumberFormatException`, `IllegalStateException`, `IOException`, `IllegalArgumentException`, `UnsupportedOperationException`, and `CompletionException`. These are **experimental numbers**, not numbers guaranteed on every JDK, because JVM internals and templates can emit different event counts.

In the same environment, running with `settings=default` without customization produced a test recording with **zero `jdk.JavaExceptionThrow` events**. Thus: **a file with zero events does not prove no exceptions occurred**; verify `enabled` settings, recording duration, and output.

Do not casually enable stack-captured exception events across all production traffic: if the application uses exceptions as high-frequency control flow, data volume and overhead can surge. Some JDKs support rate-limiting/throttling mechanisms, yet **do not assume a `throttle` setting exists for every event/JDK**. In the JDK 24 test environment, passing `jdk.JavaExceptionThrow#throttle=10000/s` to `jfr configure` was rejected. Use only event settings supported by the actual JVM; prefer **short recording windows, representative workloads, file size and cost checks**, or aggregated application counters when only rates are needed.

### 9.2 Experiment Distinguishing Exception Construction from Throwing

Save **`ExceptionConstructedDemo.java`**:

~~~java
public final class ExceptionConstructedDemo {
    public static void main(String[] args) {
        new IllegalArgumentException("constructed but not thrown");
        System.out.println("NO_THROW_REACHED");
    }
}
~~~

Run in the directory containing `throws.jfc` from above:

~~~sh
javac --release 17 ExceptionConstructedDemo.java
java '-XX:StartFlightRecording=settings=throws.jfc,filename=constructed.jfr,dumponexit=true' ExceptionConstructedDemo
jfr print --events jdk.JavaExceptionThrow --stack-depth 8 constructed.jfr
~~~

Stdout **printed by the Java demo itself** is:

~~~text
NO_THROW_REACHED
~~~

Yet in a HotSpot JDK 24 run, `constructed.jfr` **still contained one `jdk.JavaExceptionThrow` event** with:

~~~text
message = "constructed but not thrown"
thrownClass = java.lang.IllegalArgumentException
stackTrace includes ExceptionConstructedDemo.main(...)
~~~

This is an **abridged illustrative excerpt** omitting fields such as timestamp, thread, and constructor frames; full contents depend on the JVM. The actual program never threw this exception and exited with code 0. That is why **JFR exception events cannot replace exception breakpoints or handler analysis**.

### 9.3 Combining JFR with Debugger and Logs

JFR excels at revealing **trends, exception types, threads, and call sites** over capture windows where stepping through individual requests is impossible. When seeing an event spike:

1. Check the actual JFR configuration, event types, timestamps, stacks, threads, and system context.
2. Filter exception classes relevant to application code; separate wrapper messages from deepest causes.
3. Reproduce a small case with an exception breakpoint to observe **the real throw site** and **handler**.
4. Cross-check real outcome metrics: request failure ratio, retry rate, DLQ, timeouts, job failures, and fallback rate.
5. Call it an incident/bug only when evidence shows behavior violates the contract, not merely because an event count rose.

## 10. Smart Logging: Where to Log and What to Log?

A common mistake is logging the full stack at every layer and rethrowing, making a single exception look like multiple failures. Instead:

| Layer | What to do | Why |
| --- | --- | --- |
| Small library/parser | Throw a meaningful type; optionally add context while **preserving cause** | Lets the caller decide whether to fall back or fail |
| Service | Handle when safe recovery is known; otherwise rethrow/wrap with context | Avoids fake success or hiding the cause |
| HTTP boundary/job scheduler/message consumer | Log the error outcome once with correlation ID, status, operation, root cause | Provides business context and final decision |
| Metrics | Count recovered failures, validation errors, retries, hard failures by type | Avoids confusing thrown count with failed requests |
| APM/JFR | Capture diagnostic data over appropriate windows | Supplies stack/timeline context without logging everything |

Never log passwords, tokens, sensitive raw payloads, or full HTTP headers in exception logs. `ex.getMessage()` can also contain input data, so sanitize it. For log aggregation, include correlation IDs and consistent error codes across layers; keep full stacks at a trusted boundary and avoid duplicate logs.

**Important:** an exception caught to return an error response should still emit a corresponding failure metric; "caught" is only an implementation detail, not a measure of service quality.

## 11. Debugging Hard-to-See Exceptions in Multi-Layer Applications

### 11.1 Frameworks Catching Exceptions Automatically

In Spring MVC/Jakarta Servlet or HTTP middleware, exceptions from controllers can be caught by handler/resolver/filter layers and converted into responses. From the IDE's viewpoint, the exception may be **caught**, yet the request still returns 500. Inspect type → status mapping, body, transaction state, and single-log behavior. Do not equate "uncaught in user code" with "uncaught at thread boundary."

### 11.2 Retries Masking Failed Attempts

A client may throw a timeout on the first attempt, and the framework catches and succeeds on a retry. JFR/exception breakpoints see the timeout even though the final request succeeds. Still check retry rate, backoff, idempotency, and SLOs: heavy retries can raise latency and load. Conversely, an error that exhausts retries and surfaces to the caller is the final failure.

### 11.3 Transaction Marked Rollback Even Though Exception Was Caught

A transaction may be marked rollback-only in a lower layer while outer code catches the exception and thinks everything is fine. Depending on the framework, commit may fail later. Inspect transaction state/rollback markers rather than relying on no exception escaping the current `catch`.

### 11.4 Logging on the Wrong Thread or at the Wrong Time

In async code, where the exception originates can be on a worker thread, while `get()`/`join()` reports it on the request thread. Two different stacks are normal. Place debuggers on both the source task and the future boundary; propagate request context across async boundaries rather than expecting thread-locals to cross executors automatically.

### 11.5 Exceptions Replaced or Losing Their Cause

~~~java
catch (IOException ex) {
    throw new RuntimeException("Operation failed"); // Lost the cause.
}
~~~

This pseudo-snippet belongs in a method handling `IOException`. Preferred form when crossing abstraction levels:

~~~java
catch (IOException ex) {
    throw new RuntimeException("Operation failed", ex);
}
~~~

Preserve the original cause for debuggers/logs/APM. Avoid `throw new RuntimeException(ex.getMessage())` because it usually loses the original trace and adds no context.

## 12. End-to-End Investigation Workflow for a Real Incident

**Example:** users report "creating an invoice occasionally returns 500"; logs contain a few `IllegalArgumentException`s, and JFR shows many `NumberFormatException`s.

1. **Lock down scope:** grab 1–3 failing request IDs, endpoint, redacted payload, response status, timestamp, and build version. Confirm whether it is truly 500 or 400 validation.
2. **Build a timeline:** align access logs, error logs, traces, thread/request context, and JFR over the same window; verify clocks/timezones.
3. **Initial triage:** `NumberFormatException` may come from a parser trying formats with fallback, while `IllegalArgumentException` in the service may wrap an `IOException`. Do not pick the culprit solely by the loudest name.
4. **Reproduce:** construct a known test input and run a debugger with exception breakpoints for the relevant classes. Record input/state at throw time and the caller path.
5. **Follow the handler:** check whether the parser `catch` honors the contract; check whether wrappers preserve cause; verify how the controller/error handler maps status; check retries/transactions/futures.
6. **Pinpoint the concrete root bug:** e.g., "invalid `invoiceId` slipped past validator so repository received null; service wrapped the error and handler returned 500"—backed by stack, line, input, and propagation path.
7. **Fix at the right layer:** validate at the boundary to return 400; never use a catch-all returning 200; keep causes/metrics/logs at the boundary. Separate expected exceptions from hard failures where possible.
8. **Regression test:** same input before/after, unit/integration tests, right response status, no silent success, proper retry/rollback; check logs/metrics and diagnostic overhead.

### Evidence Table Before Concluding

| Observation | What you can claim | What you cannot claim yet |
| --- | --- | --- |
| Debugger pauses at `throw` | Exception was thrown on that code path | Request definitely failed |
| A `catch` exists for the exception | Exception has some handler | Handler successfully recovered |
| Java stdout has no stack trace | No stack trace printed to observed stdout/stderr | Zero exceptions occurred |
| JFR has `jdk.JavaExceptionThrow` | An event was recorded by that mechanism on that JVM | `Throwable` was definitely thrown or went uncaught |
| `CompletableFuture` completed exceptionally | Async operation failed per future contract | Worker thread died uncaught / process died |
| Thread uncaught handler invoked | Exception escaped the thread's `run` | Entire JVM definitely stopped |
| HTTP returns 200 after an exception | API ultimately returned 200 | Internal work succeeded and data is uncorrupted |
| HTTP returns 500, yet framework caught exception | Boundary built an error response | No bug exists just because IDE labeled it caught |

## 13. Mistakes to Avoid

1. **Pausing on every thrown exception and treating all as bugs.** Inspect handlers and outcomes; parsers, frameworks, and retries may use expected exceptions.
2. **Assuming caught means handled successfully.** A handler may rethrow, wrap, return 500, or roll back.
3. **Assuming uncaught always terminates the entire JVM.** Uncaught may kill only one thread; `main` and other threads continue running.
4. **Looking only at a wrapper's stack.** Check `getCause()` and `getSuppressed()`; the root cause may sit in an async/reflective layer below.
5. **Confusing creation stack with throw site.** `Throwable` normally captures trace at construction; JFR on HotSpot can emit events at construction before throwing.
6. **Treating JFR event count as failed request count.** One request can raise multiple exceptions; expected exceptions and wrappers can also be counted.
7. **Believing `default.jfc` always enables JavaExceptionThrow.** Verify actual settings; many default presets omit high-frequency events.
8. **Enabling detailed exception tracing across all production indefinitely.** It can incur CPU/file overhead and expose data.
9. **Logging and rethrowing at every layer.** Produces duplicate log entries for one error; pick a proper boundary, preserve cause and correlation ID.
10. **Swallowing exceptions and returning success to "reduce errors."** Hides bugs and risks corrupting data or losing transactions.
11. **Catching `Throwable` and ignoring `Error`.** Can mask severe runtime conditions and leave the system unsafe.
12. **Dropping `InterruptedException` without honoring its contract.** Can break task cancellation/application shutdown.
13. **Opening remote debuggers without strict controls.** JDWP carries high privileges; never expose the port to the Internet.
14. **Setting breakpoints on code mismatching the build/source.** Stepping leads to wrong lines and wrong conclusions.
15. **Failing to reproduce with the same request/build.** Exception types can match while causes or code paths differ.
16. **Forgetting the future.** Skipping `get/join` or observation callbacks can let jobs fail without clear logs.

## 14. Practice Exercises with Answers

**Exercise A.** `Integer.parseInt("x")` throws `NumberFormatException`; a `catch` returns fallback 8080, and the request succeeds per an optional-config requirement. You see the breakpoint in `parseInt`. Is this an incident?

**Answer:** No incident proven yet. This may be a validly handled fallback exception. Verify the contract (whether the port is truly optional), check rate if impacting performance; do not delete the handler merely because the debugger paused.

**Exercise B.** A controller throws `IllegalStateException`, middleware catches it and returns HTTP 500. The IDE labels it "caught." Did the request succeed?

**Answer:** No. The exception was caught at the boundary to build an error response, yet the request failed per HTTP contract. Fix the root cause or error mapping, and 5xx metrics must reflect it.

**Exercise C.** JFR has a `jdk.JavaExceptionThrow` event with message "constructed but not thrown"; code only ran `new IllegalArgumentException(...)`. Does this prove the code threw the exception?

**Answer:** No. On tested HotSpot, the event can fire upon constructing `Throwable`; use a debugger or inspect the code path to verify an actual `throw`.

**Exercise D.** `CompletableFuture.runAsync` throws `UnsupportedOperationException`, and `main` never calls `get`/`join`. Nothing appears on stderr. Did the task succeed?

**Answer:** You cannot conclude success; the future may have completed exceptionally. Observe the future result and ensure errors are recorded/handled per contract.

**Exercise E.** `new RuntimeException("failed", cause)` appears in the stack, while `cause` is `IOException("config missing")`. Where should you debug?

**Answer:** Inspect both the wrap site and the deeper cause at `readConfig`, checking inputs/configs/filesystem permissions; do not fix only where the wrapper was created.

**Exercise F.** A custom thread throws `IllegalStateException` out of `run()`. The uncaught handler logged it, and `main` keeps running. Is that a contradiction?

**Answer:** No. Uncaught is per thread; it does not force the JVM to exit. Mark the task failed and decide recovery/restart per business rules.

**Exercise G.** In `try-with-resources`, `read` throws `IOException("read failed")` and `close` throws `IOException("close failed")`. Where do you find the second error?

**Answer:** In `getSuppressed()` of the primary error, not in `getCause()` by default. `printStackTrace()` normally displays suppressed exceptions; do not forget to check cleanup errors.

**Exercise H.** You disabled caught exceptions in the IDE and the debugger stops pausing, while logs show rising retry rates. Can you conclude nothing is being thrown?

**Answer:** No. You only changed **the debugger filter**. Exceptions caught for retries may still occur continuously; check runtime metrics, logs, or appropriate breakpoint settings.

## Key Takeaways

- **Where did the exception originate?** Use exception breakpoints, local variables, stacks, and code paths to find the throw site; traces stored in `Throwable` sometimes reflect construction time.
- **Where does it go after being thrown?** Follow handlers, rethrows, wrappers/causes, async futures, and thread boundaries.
- **Which outcome is right?** Verify valid fallbacks, HTTP/job results, retries/rollbacks, logging, and tests. **Caught does not equal success; thrown does not equal incident.**
- **What evidence does JFR provide?** It records events per HotSpot/JDK template and semantics, without natively providing "handled/unhandled" status. `jdk.JavaExceptionThrow` can even appear when only constructing an exception.
- **Keep investigations bounded and reproducible**: filter exception types, capture short/timely data, preserve causes, avoid duplicate logs, and protect debugger access and sensitive data.

### References

- Oracle Java 21, `jdb` / Exceptions: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html
- Oracle Java 21, `Throwable` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html
- Oracle Java 21, `CompletableFuture` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Oracle Java 21, `CompletionException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionException.html
- Oracle Java 21, `Thread.UncaughtExceptionHandler`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html
- Oracle Java 21, `jdk.jfr` event configuration: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle Java 21, `jfr` command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
