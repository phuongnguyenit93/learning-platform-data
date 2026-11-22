# Trade-offs of Disabling writableStackTrace or Reusing Exception Objects

## 1. The Performance Problem and Diagnostic Value

In Java, creating a regular exception does not just mean allocating an object containing a message. Depending on the implementation and configuration, when constructing a **Throwable**, the JVM may also collect a stack trace so that it can later indicate where the error object was created, through which methods, and at which source file and line. Creating a very large number of exceptions can incur CPU cost, allocation overhead, garbage collector pressure, and logging cost when printing stack traces.

Some systems try to optimize very hot execution paths using two techniques:

1. **Disabling writableStackTrace** for a specialized exception type, causing the object not to collect or retain a stack trace via the standard mechanism.
2. **Reusing a pre-created exception object**, avoiding allocating a new object and collecting a new stack trace on each throw.

Both can reduce overhead in specific measured scenarios, but they strip away or distort the data needed to investigate failures. The greatest danger is not merely “fewer lines in the log,” but **no longer being able to determine where the actual failure occurred, in which request, or which invocation’s suppressed exceptions are attached**.

**Design principle:** prefer keeping full exceptions for abnormal errors that require diagnosis; only optimize the exception path after measuring that it is a performance bottleneck, verifying the impact, and having an alternative observability channel to compensate for the lost data. Do not turn exceptions into a frequent control-flow path just because stackless exceptions exist.

This lesson belongs to the **Performance** group in **Java Core — Exception**: the focus is on Throwable semantics, the benefits and costs of optimization, and how to make decisions, not unconditional speed tricks.

## 2. How Is a Stack Trace Created and Used?

A **Throwable** contains independent yet related components:

| Component | Purpose | Common API |
| --- | --- | --- |
| Error type | Classifies the failure condition | **getClass()**, catch by class |
| Detail message | Explains the situation or error data | **getMessage()** |
| Cause | A Throwable that is the root cause of another Throwable | **getCause()**, constructors accepting cause |
| Suppressed exceptions | Secondary errors, typically from cleanup | **addSuppressed()**, **getSuppressed()** |
| Stack trace | Call trace recorded for the Throwable | **getStackTrace()**, **printStackTrace()** |
| Writable stack trace | Controls whether Throwable retains/modifies a stack trace via the standard mechanism | Protected constructor of **Throwable** |

When creating an exception through the normal path, Throwable's constructor typically invokes **fillInStackTrace()** logic to record the execution context into the object. The time of trace capture is **typically when constructing the Throwable**, not each time the **throw** keyword is executed on the same object.

Afterward, **getStackTrace()** returns an array of **StackTraceElement**, while **printStackTrace()** presents the frames along with cause and suppressed exceptions. Printing/logging the stack trace also has its own cost, separate from the initial trace collection cost. Therefore, benchmarks must distinguish between:

- **Creating the exception:** allocating the object, executing the constructor, and possibly collecting the trace.
- **Throwing and catching:** control-flow cost, unwinding to the handler.
- **Retrieving the stack:** calling getStackTrace and converting data into readable frames.
- **Formatting and outputting logs:** converting Throwable to a string, writing to file/console/network.
- **GC:** reclaiming repeatedly created exceptions.

Disabling writableStackTrace can affect trace collection and storage, but it **does not eliminate all exception costs**, does not remove all object allocations, and does not change checked/unchecked rules or how catch works.

## 3. Throwable's Four-Parameter Constructor

Java provides a **protected** constructor on Throwable:

~~~java
// API signature of java.lang.Throwable:
protected Throwable(String message, Throwable cause,
                    boolean enableSuppression,
                    boolean writableStackTrace);
~~~

The two booleans are not synonymous:

- **enableSuppression:** allows the Throwable to record exceptions added via **addSuppressed()**.
- **writableStackTrace:** allows the Throwable to collect and maintain a stack trace via the standard mechanism.

Exception subclasses can expose this configuration through an appropriate constructor. **Throwable** does not expose this constructor as a public factory for all callers; the usual approach is to extend **Exception**, **RuntimeException**, or a class with a corresponding protected constructor, such as **RuntimeException(String, Throwable, boolean, boolean)**.

A typical custom class:

~~~java
// Illustrative code in a separate file or as a nested class.
final class LightweightFailure extends RuntimeException {
    LightweightFailure(String message, Throwable cause) {
        super(message, cause, true, false);
        //                  ^ suppression enabled
        //                        ^ writableStackTrace disabled
    }
}
~~~

The **true, false** configuration here **preserves suppressed exceptions** while **not retaining a standard stack trace**. If set to **false, true**, it **disables suppression** while keeping the stack trace. The two configuration axes must be chosen based on diagnostic requirements, not arbitrarily lumped into a single “lightweight” flag.

For an exception with writableStackTrace=false, the Throwable contract states that the constructor does not call fillInStackTrace in the normal way, and subsequent **fillInStackTrace()** or **setStackTrace(...)** calls do not add a standard trace; **getStackTrace()** returns an empty array. The behavior of subclasses that override these methods themselves may differ, so the statements here apply to the standard Throwable/JDK mechanism and the example class.

## 4. Complete Java 17+ Example: Three Configurations and One Reused Exception

This program verifies with clear output, avoiding noisy microbenchmarks:

- A **fresh** exception has a trace reflecting the method that created/threw it in that call.
- A **stackless** exception has a cause and suppressed exception, but an empty trace even after fill/set calls.
- A **suppression-disabled** exception still has a stack trace but does not store secondary errors.
- A **shared** exception is thrown twice: same object, the trace still points to the original creation site, and the suppressed exception from the previous attempt persists.

Create the file **StackTraceTradeoffDemo.java**:

~~~java
import java.io.IOException;

public class StackTraceTradeoffDemo {
    static final class ConfiguredFailure extends RuntimeException {
        ConfiguredFailure(String message, Throwable cause,
                          boolean suppression, boolean writableStackTrace) {
            super(message, cause, suppression, writableStackTrace);
        }
    }

    private static final ConfiguredFailure SHARED = makeShared();

    static ConfiguredFailure makeShared() {
        return new ConfiguredFailure("shared failure", null, true, true);
    }

    static void throwNew() {
        throw new ConfiguredFailure("new failure", null, true, true);
    }

    static void throwShared() {
        throw SHARED;
    }

    static String firstAppFrame(Throwable failure) {
        for (StackTraceElement frame : failure.getStackTrace()) {
            if (frame.getClassName().equals(StackTraceTradeoffDemo.class.getName())) {
                return frame.getMethodName();
            }
        }
        return "(none)";
    }

    public static void main(String[] args) {
        try {
            throwNew();
        } catch (ConfiguredFailure failure) {
            System.out.println("fresh origin=" + firstAppFrame(failure));
            System.out.println("fresh has frames=" + (failure.getStackTrace().length > 0));
        }

        ConfiguredFailure stackless = new ConfiguredFailure(
                "stackless", new IOException("root"), true, false);
        System.out.println("stackless frames=" + stackless.getStackTrace().length);
        System.out.println("stackless cause=" + stackless.getCause().getMessage());
        stackless.addSuppressed(new IllegalStateException("cleanup"));
        System.out.println("stackless suppressed=" + stackless.getSuppressed().length);
        stackless.fillInStackTrace();
        stackless.setStackTrace(new StackTraceElement[] {
                new StackTraceElement("Demo", "method", "Demo.java", 1)
        });
        System.out.println("stackless after fill/set=" + stackless.getStackTrace().length);

        ConfiguredFailure noSuppression = new ConfiguredFailure(
                "no suppression", null, false, true);
        noSuppression.addSuppressed(new IOException("secondary"));
        System.out.println("suppression disabled=" + noSuppression.getSuppressed().length);
        System.out.println("suppression-off has frames="
                + (noSuppression.getStackTrace().length > 0));

        ConfiguredFailure first = null;
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                throwShared();
            } catch (ConfiguredFailure failure) {
                if (first == null) {
                    first = failure;
                    failure.addSuppressed(new IOException("from attempt 1"));
                }
                System.out.println("reuse " + attempt + " same=" + (first == failure)
                        + " origin=" + firstAppFrame(failure)
                        + " suppressed=" + failure.getSuppressed().length);
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 StackTraceTradeoffDemo.java
java StackTraceTradeoffDemo
~~~

Verified stdout when run on Java 17+:

~~~text
fresh origin=throwNew
fresh has frames=true
stackless frames=0
stackless cause=root
stackless suppressed=1
stackless after fill/set=0
suppression disabled=0
suppression-off has frames=true
reuse 1 same=true origin=makeShared suppressed=1
reuse 2 same=true origin=makeShared suppressed=1
~~~

### Interpreting the Output

**Fresh origin = throwNew:** the constructor was called inside the throwNew method. Because this is a new object with writableStackTrace=true, the first recorded application frame is named throwNew. It helps log readers trace where the exception was created.

**Stackless frames = 0:** the constructor was called with writableStackTrace=false; there are no standard frames to identify the creation site. However, **getCause()** still returns the IOException with message **root**; **getSuppressed()** still has one cleanup error. Disabling the **wrapper**'s stack trace does not automatically disable the traces of its cause or suppressed exceptions, which are separate Throwables.

**Stackless after fill/set = 0:** in the tested implementation, calling fillInStackTrace and setStackTrace does not give the exception a trace again when the writableStackTrace flag is disabled. Therefore, this is not a feature that can be arbitrarily toggled on/off on the same object at a later point.

**Suppression disabled = 0:** the IOException was passed to addSuppressed but was not stored. Meanwhile, the trace still exists. This demonstrates that the two constructor flags are independent.

**Reuse origin = makeShared:** SHARED was created in makeShared, not on each call to throwShared. When rethrowing the same object, the trace does not automatically update for the new throw. **Suppressed=1** on the second attempt is not a new cleanup error; it is data added from the previous attempt that remains on the same object.

This last point is a serious reason to be cautious with **singleton exceptions shared across multiple requests**.

## 5. What Does writableStackTrace=false Actually Trade Off?

Potential benefits of stackless exceptions:

- Avoids collecting a full stack trace in Throwable's standard constructor.
- Can reduce CPU cost and part of the memory pressure when creating exceptions at very high frequency.
- When individual throw sites are genuinely not needed, avoids collecting unused data.
- An empty trace also makes the stack data of that exception itself shorter when logged.

However, the cost in lost information:

- No source frames to indicate the class/method/line that created the exception.
- When the error propagates across multiple layers, the caller only has the type, message, cause, and additional context if any.
- Cannot later call **fillInStackTrace()** to recover the trace that was omitted at the original error time.
- Distinguishing between two different places throwing the same exception type can become difficult.
- Logging/APM tools or error aggregation systems may misgroup multiple incidents that only share the same type and message.
- If the exception is wrapped at a higher layer, the wrapper's trace shows where it was wrapped, but cannot reconstruct the origin of the stackless exception.

**Trade-off:** You save some overhead on the error path, but lose high-value technical evidence at the exact moment you need to investigate. For rare errors or errors affecting data integrity, it is usually not worth it.

### A Stackless Wrapper Does Not Mean All Traces Are Empty

In the example:

~~~java
// Illustrative code inside an appropriate method.
RuntimeException stackless =
    new LightweightFailure("operation failed", new IOException("disk error"));
~~~

This illustrates using the **LightweightFailure** class from Section 3. The trace of **stackless** is empty, but the **cause** IOException is constructed normally and therefore can have its own stack trace. If you disable writableStackTrace on the wrapper to reduce overhead while still creating a heavy cause and printing the full exception tree, the actual benefit will differ from the case where there is no trace at all.

Conversely, if both the cause and the wrapper are replaced with traceless objects, the amount of diagnostic information lost is even greater. Benchmarks must use the system's **actual Throwable chain**, not just a mock object.

## 6. enableSuppression and writableStackTrace Are Completely Independent

The four configuration combinations must be clearly understood:

| enableSuppression | writableStackTrace | Expected Result in Standard Throwable Mechanism |
| --- | --- | --- |
| true | true | Can retain both suppressed exceptions and stack trace |
| true | false | Retains suppressed exceptions; the Throwable's own stack trace is empty |
| false | true | Does not store errors via addSuppressed; still has stack trace |
| false | false | Neither stores suppressed exceptions nor retains stack trace |

**Suppressed exceptions** are especially important when using **try-with-resources**. If the try body throws error A and **close()** throws error B, the standard mechanism prioritizes A and adds B to A.getSuppressed() when A supports suppression.

If **A** is a Throwable with **enableSuppression=false**, error B is not retained via **addSuppressed()** on A. When inspecting only A's stack trace/cause, you may **lose the trace of the cleanup failure**. This is not just a matter of “less log info”—it can hide failed resource reclamation, rollback, or close operations.

Therefore, **do not disable suppression just to shave off a bit more overhead** when the API may still be used with try-with-resources or have secondary errors attached. If secondary errors carry business significance, keeping suppression enabled is an essential observability requirement.

**Reading the code:** In the constructor **super(message, cause, suppression, writable)**, the first boolean refers to suppression, and the second refers to the stack trace. Using clear parameter names and named factories helps reduce parameter-order mistakes.

## 7. Reusing the Same Exception Object vs. Reusing an Exception Type

Two patterns that are easily conflated:

~~~java
// Illustrative code; method placed in an appropriate class.
throw new IllegalStateException("invalid state");
~~~

Each execution creates **a new Throwable**, usually with a stack trace tied to that creation.

~~~java
// Illustrative code; SHARED variable has been pre-created.
throw SHARED;
~~~

Each throw uses **the same pre-existing Throwable**. The reference, message, cause, suppressed list, and trace all belong to **that object**. The throw keyword **does not copy the Throwable** and does not automatically record a new trace on each throw.

Reusing can reduce allocations, but in return:

1. The stack trace reflects where the object was first created, not each failure occurrence.
2. A fixed message cannot easily carry request-specific context.
3. The cause may be unrelated to the new throw or cannot be safely changed.
4. Suppressed exceptions can accumulate across multiple executions.
5. Multiple threads may simultaneously observe or mutate the single exception.
6. Diagnostic tools, logging, and error-grouping features may fail to distinguish individual events.

**Especially dangerous:** Reusing a regular exception **that has a stack trace** while assuming the trace will automatically update on each throw. That produces an error with both a misleading trace and an appearance of high credibility.

## 8. Why Not Call fillInStackTrace() on a Shared Exception Each Time It Is Thrown?

One might encounter this idea:

~~~java
// Illustrative anti-pattern; SHARED is the same mutable Throwable.
SHARED.fillInStackTrace();
throw SHARED;
~~~

This no longer preserves the benefit of “not collecting a trace”: **fillInStackTrace()** performs the work of capturing a new stack. In a multithreaded environment, two requests can concurrently overwrite the stack trace of the same object. Request A's error can have its stack overwritten by Request B before A finishes logging or collecting the trace.

Furthermore, **fillInStackTrace()** does not clear suppressed exceptions, does not change the cause, and does not create an independent copy for each throw. “Refreshing the stack” does not fix the fundamental nature of **sharing mutable state** on a Throwable.

If you want an accurate trace for each incident, the normal and clearest approach is to **create a separate exception for that incident**. If you have truly decided you do not need a trace, a fresh stackless exception per occurrence may also be more appropriate than a shared singleton, because it preserves the independence of message/cause/suppressed.

**Exception with writableStackTrace=false:** With the standard Throwable mechanism, fillInStackTrace is disabled and cannot be used to recover a trace; it is not a remedy for lost data once disabled.

## 9. Cause, Suppressed, and Message Create Risks When Shared

Throwable-related fields should not be assumed to be “completely read-only” just because your code has no message setter:

- Some Throwables can have **cause** configured at construction or via **initCause()** subject to JDK constraints.
- **addSuppressed()** appends a new exception to the suppressed list if suppression is enabled.
- **setStackTrace()** modifies the stack trace representation for Throwables with an appropriate writableStackTrace.
- **fillInStackTrace()** can mutate the trace on each call.
- Custom subclasses may also have their own mutable fields.

For example, SHARED in Section 4 was created with **suppression=true**. After the first processing pass, the catch block attached IOException “from attempt 1”. In the second pass, **getSuppressed()** still returns that IOException, even though the second pass did not encounter a corresponding close error.

This can lead to:

- The second request's log containing cleanup errors from the first request.
- Sensitive information from one tenant/request leaking into another tenant/request's logs.
- Secondary error counters inflating with the number of uses.
- Observability tools reporting the wrong root cause.
- Saving a tiny object allocation at the cost of long-term operational confusion.

Even though **addSuppressed()** has internal JDK synchronization to manage its list, that **does not turn a shared Throwable into an accurate representation of multiple independent incidents**. Business correctness and distinguishing individual failures are separate concerns from whether a method is internally synchronized.

## 10. Concurrency Case: Same Throwable Across Multiple Threads

Suppose two requests A and B both use a singleton exception:

~~~java
// Illustrative code; a shared exception is held in a static field.
static final RuntimeException REJECTED =
        new RuntimeException("rejected");

static void reject() {
    throw REJECTED;
}
~~~

When both A and B call reject(), they receive **the exact same object**. If a catch branch for A calls addSuppressed, setStackTrace, or fillInStackTrace, branch B can observe those mutations. Multiple loggers recording the Throwable object at different times can also produce different outputs.

With a stackless singleton and suppression disabled, the risk of data accumulation decreases because both mechanisms are disabled, yet issues remain:

- No stack trace for each event.
- The same cause and message do not describe individual requests.
- Cannot attach per-event context via suppressed exceptions.
- A subclass with mutable fields can still share state.
- Logic that uses object identity to group or count exceptions may mistake multiple events for one.

Therefore, a **stackless singleton exception** can only be a specialized choice when every throw has **the exact same meaning, requires no per-request context**, shares no additional mutable data, and already has alternative observability. For critical data errors, prefer a separate exception per failure.

## 11. Is the Exception an Abnormal Condition or Control Flow?

A performance question even more important than disabling traces: **why are exceptions occurring at high frequency?**

If code uses exceptions to traverse a branch expected to occur millions of times, the system is paying throw/catch overhead and possibly trace overhead to do what a normal check result can handle.

Anti-pattern example when input is frequently non-numeric:

~~~java
// Illustrative code inside a method that receives text.
int parseOrZero(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ignored) {
        return 0;
    }
}
~~~

This snippet compiles when placed in an appropriate class. It may be reasonable in a small application, but if invalid data is **very common on a hot path**, repeatedly creating exceptions can be worth measuring. Do not immediately look for a way to turn it into a “stackless NumberFormatException,” because that exception is created by the JDK and you do not control its constructor.

Better improvements depend on the problem:

1. Use a parser that returns a **status/value** instead of throwing an exception for expected cases.
2. Pre-validate conditions that can be checked cheaply, while avoiding duplicating the entire parser twice and incurring higher cost.
3. Categorize invalid input into an explicit result type, such as Optional, Result, or an error code.
4. Only use exceptions when **the contract cannot be fulfilled normally** or the error is genuinely abnormal.
5. Re-measure performance and complexity after changing.

**Note:** Pre-checking is not guaranteed to always be faster than direct parsing. If error cases are very rare, adding a validation pass may slow down the success path. Base the decision on **actual error frequency** and properly configured benchmarks.

## 12. Where Stackless Exceptions Can Be Considered

Not every use of stackless exceptions is wrong. Some high-performance libraries use well-known, high-frequency internal signals or APIs to convey an anticipated termination state. However, the exact scope must be examined:

| Scenario | Can Be Considered? | Mandatory Conditions |
| --- | --- | --- |
| Purely internal state, no per-request data, measured as a hot path | Yes, cautiously | Event is well understood, alternative observability is sufficient |
| User input parsing error needing source location | Usually no | Keep trace, type, and message/cause sufficient for investigation |
| Exception signaling an unexpected invariant violation bug | No | Trace is core data for fixing the bug |
| Unstable database/network error | Usually no | Needs trace, cause, retry context, idempotency |
| Internal stop mechanism not exposed across public API | Possible | Encapsulated, documented, thoroughly tested |
| Singleton exception in a multi-tenant server | High risk | No cross-request data leak, no suppressed/context usage |
| Exception used in a hot loop as a normal condition | Prefer redesign | Use return/result instead of throw for expected paths |

When applying stackless exceptions to a public API, library consumers may not know you removed the stack trace, making error investigation harder. An optimization decision in a library can shift incident-handling costs onto many downstream systems. This must be clearly described in the contract or operational documentation.

## 13. Distinguishing Exception-Type Optimization from Per-Instance Optimization

There are at least three distinct options:

**A. Regular exception, newly created:**

~~~java
// Illustrative code.
throw new IllegalStateException("config changed unexpectedly");
~~~

Preferred for genuinely abnormal errors; has an accurate trace, and the message can describe the situation.

**B. Stackless exception, newly created:**

~~~java
// Illustrative code; LightweightFailure from Section 3.
throw new LightweightFailure("operation not permitted", cause);
~~~

Still allocates an object for the new event, but skips trace collection for that object. A separate cause and separate suppressed exceptions can preserve context. This option is not a singleton and carries lower risk of “cross-request mixing.”

**C. A single reused exception:**

~~~java
// Illustrative code; SHARED is already defined in the class.
throw SHARED;
~~~

Can avoid allocation per throw, but trace/message/cause/suppressed belong to the same object. If SHARED has a stack trace, the trace location is not updated automatically; if SHARED is stackless, there is no location in the main trace to identify the throw site.

Choose A as the default. If A has a measured problem, consider changing control flow or B before considering C. There is no guarantee that B is always fast enough or C is always fastest, because costs depend on the JVM, compiler, exception shape, catch path, and workload.

## 14. Misconceptions About fillInStackTrace()

**Throwable.fillInStackTrace()** is a method that can be called or overridden. It is not a guarantee that every exception can always reconstruct the trace of a past throw.

For a regular object:

~~~java
// Illustrative code; failure is a Throwable with writableStackTrace=true.
failure.fillInStackTrace();
~~~

This call refreshes the stack trace at the location **currently calling fillInStackTrace**, rather than going back to an earlier point that the JVM did not record. If called from a high-level catch/logging layer, the new trace may point to that high-level layer and lose the original failure site.

With writableStackTrace=false, **fillInStackTrace()** in the standard implementation does not add a trace; this was demonstrated in the Java 17 example in Section 4.

Nor should you override **fillInStackTrace()** just to return **this** on every custom exception without evaluating the impact:

~~~java
// Illustrative code for a specialized custom exception type.
final class NoTraceFailure extends RuntimeException {
    @Override
    public synchronized Throwable fillInStackTrace() {
        return this;
    }
}
~~~

This is an optimization technique that has been used in the past, but it has differences regarding the constructor calling an overridable method, inheritance, stack trace behavior, and maintainability. A constructor with **writableStackTrace=false** expresses intent more clearly when appropriate for a Throwable type you control. Avoid treating this override as a mandatory optimization recipe for every exception class.

## 15. Measuring Performance Properly Before Making a Decision

A short measurement using **System.nanoTime()** around a throw/catch loop is not sufficient to conclude that disabling traces or using singleton exceptions is always better. JIT, escape analysis, class initialization, tiered compilation, CPU scheduling, GC, and logging can cause runs to vary.

A more standard approach is a warmed-up benchmark with controlled workload, typically using **JMH**. If JMH cannot be used, simple measurements should only be treated as preliminary information, not the basis for architectural decisions.

Benchmarks should separate the alternatives:

1. **Normal condition returning a status/boolean**.
2. **Creating a new regular exception**, throwing and catching.
3. **Creating a new custom stackless exception**, throwing and catching.
4. **Reusing a regular exception**, throwing and catching.
5. **Reusing a stackless exception**, throwing and catching.

At the same time, there should be two workload groups:

- **Common success path:** may create no exceptions at all.
- **Error path at realistic frequency:** e.g., 0.01%, 1%, or 50% errors depending on real measurements.

### Metrics to Track

| Metric | Why It Matters |
| --- | --- |
| Throughput/operations per second | Overall processing capacity of the code path |
| p50/p95/p99 latency | Variance and tail latency |
| Allocation bytes/op | Allocated bytes related to GC |
| GC collections/time | Memory reclamation pressure |
| CPU sampling/profiling | Whether constructor, fillInStackTrace, formatting/logging are real bottlenecks |
| Error rate and error types | Frequency of exceptions by type and source |
| Observability cost | Stack logging, sending APM data, storage/network |
| Incident diagnosability | Whether class/method/line and related request can be identified |

Measure on the same JDK, same heap/GC configuration, same build type, inputs, load level, and an environment close to production. **Do not put an “X times faster” figure into documentation without a benchmark applicable to the actual application**, because trace collection cost and optimization impact depend on the environment.

### Measuring Exception Creation Separately from Log Printing

If a benchmark only throws and catches without printing the stack trace, it may miss the real logging cost. Conversely, if a benchmark writes the entire stack to the console in a loop, I/O cost can easily overwhelm the Throwable constructor cost. Both are valuable when asking the right question, but they cannot substitute for each other.

For the stackless option, benchmarks must also consider that missing traces can make debugging or grouping in APM harder. The operational cost when a rare bug is hard to reproduce can outweigh the nanoseconds saved on a hot path.

## 16. Impact of JVM, JIT, and Internal Optimizations

Do not assert that stack trace construction has the exact same cost across every Java version. HotSpot/JVM may use different optimizations, internal representations, or fast throw paths. Some exceptions generated repeatedly by the JVM in special situations may be optimized according to implementation policies, causing observed stack traces to differ from exceptions created by Java code.

Therefore, keep in mind:

- The cost of **new RuntimeException(...)** created by application code does not represent all JVM-generated exceptions.
- A benchmark result on one JDK version may not carry over unchanged to another version.
- Optimizations related to JIT/hot throw sites can differ between warming-up code and steady-state code.
- A missing message or trace under special conditions does not prove that Throwables in general always disable traces.
- JVM flags related to exception optimization are implementation details; they should not be used as a substitute for clear exception contract design.

If you suspect the JVM has optimized away some stack traces on an extremely hot error path, cross-check the JDK version, runtime flags, occurrence count, and how the exception is created and logged. Do not assume it is proof of a bug in the logging pipeline or the JDK.

## 17. Stackless Exceptions and Logging/APM

Error observability software typically relies on a combination of:

- Exception class and message.
- Top application frame.
- Full stack trace.
- Cause/suppressed chain.
- Service name, operation, request ID/trace ID.
- Thread/async context and deployment version.

When writableStackTrace=false, **the top application frame on the exception itself does not exist**. Tools that group errors solely by type and message may:

- Merge different errors into a single group.
- Increase false positives in generic alerts.
- Fail to show which code path produces the error most frequently.
- Make post-deployment investigation less accurate.
- Make it difficult to prove that a fix eliminated the exact throw site.

If stackless exceptions are strictly necessary, replace the missing trace with **pre-designed metadata**, such as error code, event name, operation identifier, correlation ID, and dedicated structured logs. This metadata is usually lighter than a full stack trace, but **is not equivalent** to an actual stack trace; it depends on code authors logging at the right place and with the right context.

**Do not put sensitive raw input into the message** just to compensate for a missing stack trace. Data in errors and logs must still be protected, especially when a singleton exception may be used across multiple requests/tenants.

## 18. When to Create a New Exception Instead of Reusing

Prefer a new object whenever any of the following apply:

- Each failure needs a message containing a distinct ID or state.
- The actual root cause differs and an accurate cause must be stored.
- Suppressed exceptions may arise when closing resources.
- Two requests/threads can fail concurrently.
- A stack trace pointing to the exact call site is needed.
- External code may call **initCause**, **setStackTrace**, **fillInStackTrace**, or **addSuppressed**.
- Error state needs to be serialized, retried, or passed across service boundaries with its own context.
- The error represents an invariant violation, a bug, or a failure that impacts data.

If performance is genuinely critical, a **fresh stackless custom exception** can be an intermediate solution: each event still has its own identity/cause/suppressed, while omitting the main trace. If conditional traces are needed, you can consider sampling only a percentage of errors with stack traces while keeping overall metrics, though sampling must be designed clearly to avoid losing rare critical incidents.

There is no standard Throwable API that automatically guarantees “record a trace once every 100 throws.” This must be an application policy, tested alongside performance and observability.

## 19. Common Mistakes with Custom Stackless Classes

**Confusing the order of the two constructor booleans.** **super(message, cause, false, true)** disables suppression while keeping the trace enabled, not the other way around. Name parameters and constructors clearly.

**Assuming stackless also drops the cause.** Cause is a separate link; **getCause()** can still work. What needs checking is how the cause object itself was constructed.

**Assuming disabling trace automatically disables suppression.** The two options are independent. Disabling suppression can lose important cleanup errors.

**Assuming rethrowing the same exception automatically records a new location.** The stack trace typically reflects object creation time. Throw is not synonymous with fillInStackTrace.

**Creating a singleton with a trace and using it across all requests.** Logs will always point to the initializing constructor/factory, not the current error path.

**Calling fillInStackTrace on a shared singleton.** This can negate performance benefits and introduce races in debug information.

**Using a same-object singleton together with addSuppressed.** Cleanup errors from multiple executions can mix and leak data across contexts.

**Benchmarking only the error path without considering the success path.** If errors are actually rare, optimizing the exception path may not noticeably change overall latency.

**Dropping stack traces before having an alternative.** When a rare incident occurs, the operations team is left with only a generic message and cannot find the throw site.

**Treating a console microbenchmark as a production conclusion.** Logging I/O and warm-up can overshadow the costs being measured.

**Using exceptions as loop flags.** If a situation occurs frequently and is not an error, consider a result-returning API instead of repeatedly throwing.

**Optimizing without data.** If the hotspot is not in the Throwable constructor/stack capture, removing the trace only loses debuggability without bringing significant benefit.

## 20. Testing: Correct Semantics Before Measuring Speed

Before using a custom stackless or reused exception, write tests for the following contracts:

| Scenario | What to Verify |
| --- | --- |
| Normal fresh exception | Has frames corresponding to the creation site |
| Stackless exception | getStackTrace() is empty |
| Stackless with cause | getCause() still retains the cause as designed |
| Stackless with suppression=true | addSuppressed stores secondary errors |
| Suppression=false, trace=true | getSuppressed() is empty even when addSuppressed is called; trace is still present |
| Calling fill/set on stackless | Trace remains empty per the standard Throwable mechanism |
| Rethrowing a shared exception | Same object identity, trace does not change per throw |
| Shared exception with suppressed | Subsequent throw still sees errors from previous attempt; test detects leak |
| Multiple threads using shared | Must not assume error info belongs to individual requests |
| Caller wraps exception | Cause/suppressed are traced accurately without losing the original error |

In the main example, the comparison **first == failure** confirms object reuse. **firstAppFrame** only reads frames belonging to the application class, allowing observation of the creation site without depending on JDK line numbers.

Do not write fixed-time tests like “creating an exception must take under X nanoseconds” in regular CI. To check speed, use benchmarks with controlled environmental conditions and report error margins. Unit tests should focus on **API correctness and error information**.

### Checking Real Logs

If the application has a formatter or APM, trigger a test error scenario and verify:

1. The stackless object is represented properly without crashing the formatter due to an empty trace.
2. Its cause and suppressed exceptions are still displayed if present.
3. Regular errors still have sufficient frames/source lines for investigation.
4. Shared exceptions (if any) are not logged with another request's context.
5. Sensitive data in message/cause/suppressed is masked according to policy.

## 21. Decision-Making Process for Hot Paths

A sound engineering decision should follow this sequence:

**Step 1 — Determine whether the exception is on a normal processing path.** If so, consider redesigning the API to return a status/value before optimizing Throwable.

**Step 2 — Measure actual exception frequency.** Collect counts by type, request, endpoint, version, load, and time. If it occurs very rarely, the overhead may be negligible.

**Step 3 — Profile the exact costly part.** Is it Throwable construction, stack capture, catch handling, log formatting, log I/O, or GC? The solution must target the measured cause.

**Step 4 — Choose the change that loses the least information.** For example, reducing duplicate logs, throttling excessive logging, replacing exceptions with normal results, or creating a fresh specialized stackless exception instead of a singleton.

**Step 5 — Maintain a diagnostic policy.** If stackless is needed, add error code, operation, version, and correlation ID, along with a way to enable logging/tracing when needed.

**Step 6 — Test correctness.** Verify cause, suppressed, trace policy, thread safety, absence of data leaks, and rethrow semantics.

**Step 7 — Benchmark.** Use a realistic workload, the same JDK/GC and load level, examining throughput, latency, allocation, logging, and error paths.

**Step 8 — Roll out in a controlled manner.** Use gradual rollout, metrics, and the ability to revert to full traces when an incident is detected. A small change in Throwable can have a major impact on operability.

## 22. Practice Questions and Reasoning

**Question 1: If an exception's stack trace is empty, was writableStackTrace=false definitely used?**

No. It could be a customized Throwable, a reconfigured stack trace, a JVM optimization, or logging that only displays partial data. Inspect the exception creation code, JVM type, and actual object state before concluding.

**Question 2: Can fillInStackTrace() be called to recover an omitted trace?**

You cannot accurately recover a past call stack that was never saved. With writableStackTrace=false on a standard Throwable, fillInStackTrace does not add a trace. With a regular Throwable, calling the method captures the stack of **the new call site**, which may not be the original error site.

**Question 3: If suppression is disabled, does try-with-resources still close the resource?**

Yes. Calling close and **storing the cleanup exception in suppressed** are two different things. When the primary error has suppression=false, an error from close may not be stored on it, but the resource-closing mechanism still executes along the exit path.

**Question 4: Does reusing an exception always produce wrong results?**

Not in every case. Some internal mechanisms use a singleton exception solely to signal an expected state, with no per-event information to store. However, this kind of API must be intentionally designed, contain no shared state that can be corrupted, and have appropriate observability. Do not use it as the default for errors requiring diagnosis.

**Question 5: Why does a shared exception still have suppressed exceptions from the previous attempt?**

Because **addSuppressed()** mutates the shared Throwable object itself. When rethrown, that object is not recreated, so its suppressed list is not automatically cleared.

**Question 6: When writableStackTrace=false is set on a wrapper, does the cause still have a stack trace?**

It can, if the cause was constructed normally. The wrapper's stack trace configuration does not automatically apply to every Throwable it references.

**Question 7: Why shouldn't this be applied immediately to every IllegalArgumentException?**

IllegalArgumentException often provides evidence that a caller violated the API contract. Removing the trace can leave you unable to tell which caller passed invalid input. If the error count is high, first find and fix the caller or validation before removing diagnostic information.

## 23. Checklist Before Accepting the Optimization

1. **Necessity:** Has profiling proven that Throwable construction/stack trace capture is on the hot path?
2. **Frequency:** How often is the exception occurring, and is it on a rare error path or a normal case?
3. **Scope:** Is the custom exception used only internally, or is it exposed across an API to other systems?
4. **Configuration:** Have enableSuppression and writableStackTrace been distinguished in the constructor parameter order?
5. **Trace:** Do users still need class/method/line per incident?
6. **Cause:** Is the appropriate cause preserved for each failure?
7. **Suppressed:** Can cleanup errors occur, and is retaining that information mandatory?
8. **Object identity:** Is the same Throwable being reused across multiple requests/threads?
9. **Thread safety:** Is there a risk of fillInStackTrace/setStackTrace/addSuppressed mixing information?
10. **Observability:** Are there error codes, request IDs, operations, and logging to replace the lost trace information?
11. **Benchmark:** Have you measured on the same JDK/workload and separated exception creation, throw/catch, format/log, and GC costs?
12. **Tests:** Have you tested stackless, suppressed, cause, reuse, and dual-error cases?
13. **Rollout:** Can full traces be re-enabled when investigating hard-to-reproduce incidents?
14. **Security:** Have you verified that shared Throwable context does not leak information across users/tenants?

**Conclusion:** Disabling **writableStackTrace** trades **stack collection cost** for **losing the trace of where the error originated**. Reusing a Throwable trades even more: sharing the same object, cause/message/trace/suppressed across different events, making diagnostic information prone to distortion or cross-request mixing. Neither technique is a default optimization choice. In most application code, **keep regular exceptions**, fix the root cause making exceptions appear too frequently, and only use stackless exceptions or reuse after measuring the benefit and determining how to preserve accurate error semantics, state, and operability.
