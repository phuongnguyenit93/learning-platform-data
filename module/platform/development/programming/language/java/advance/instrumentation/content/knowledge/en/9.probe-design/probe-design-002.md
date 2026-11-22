# Recording Start and End Events for a Call

**Topic:** Java Advance → instrumentation → **Probe Design**.

A call probe (*call instrumentation*) typically emits two events: **START** when a call enters the observed region and **END** when that region finishes. The two events must carry enough information to **correlate the exact same invocation**, even when the method is called recursively, multiple threads run concurrently, or an exception occurs. From this event pair, the system can compute duration, success/failure rates, parent–child relationships, and slow execution segments.

The challenge does not lie in placing two `println` statements. You need to define **which exact boundary is measured**, **when END is recorded**, **how return values and exceptions are preserved**, and **how to ensure the event-recording system does not introduce additional errors or excessive overhead**.

This lesson uses **Java 17+** for standalone runnable examples, then connects directly to bytecode instrumentation with `ClassFileTransformer`/ASM. The runnable Java examples illustrate the START/END contract; the opcode diagrams and ASM sections show the instruction-injection techniques used to implement that same contract in bytecode.

## 1. What Is "One Call"?

Consider two methods:

```java
static int add(int a, int b) {
    return a + b;
}

static int total() {
    return add(2, 3) + add(4, 5);
}
```

This is a **fragment**, not a standalone program. `total()` has **two calls** to `add` even though both share the same method name. If we record events on entry/exit of `add`, we must produce **two distinct START/END pairs**.

```text
time ─────────────────────────────────────────────────────────►

total():  ├───────────────────────────────────────────────────┤
add(2,3):      START #1 ───────────── END #1
add(4,5):                                  START #2 ── END #2

Events:
  START(callId=1, method=add(II)I)
  END  (callId=1, outcome=OK, elapsedNanos=...)
  START(callId=2, method=add(II)I)
  END  (callId=2, outcome=OK, elapsedNanos=...)
```

**A method name is not a call ID.** A valid ID must distinguish each *invocation instance*; the ID can be a monotonically increasing number **within a single process** in learning examples, or `traceId` + `spanId` in distributed systems.

### 1.1. Two Ways to Define Probe Boundaries

| Boundary | When It Starts/Ends | What It Covers | Key Considerations |
| --- | --- | --- | --- |
| **Callee boundary** (method entry/exit) | Starts when the target method actually enters; ends when the method returns or throws an exception outward | Executions that enter the instrumented method, from many callers | Does not observe exceptions occurring **before the method starts**, e.g. a null receiver failing at the caller |
| **Caller / invocation site** (around `invoke*`) | Starts right before the call bytecode; ends after the result or exception of that specific call site | One specific call site in caller code; can include dispatch or call-resolution failures | Must distinguish when receiver/arguments are evaluated; instrumenting one call site does not automatically cover other callers |

For example, `String s = null; s.length();`: the `invokevirtual` instruction can throw `NullPointerException` at the call site; the body of `String.length()` **does not run**, so a probe on the **callee** does not emit START for this call. A probe at the **caller** can record START and END(ERROR) around the invocation.

In this lesson, the runnable examples measure the boundary **around a synchronous call** (*call span*). When instrumenting a method directly, equivalent logic is inserted at entry, at all normal returns, and via a catch-all exception handler. Choose a consistent boundary before evaluating results.

### 1.2. Decisions That Must Be Explicitly Specified

- **Unit of measurement:** one actual invocation, not a method name or a source line.
- **START position:** before transferring control to the callee, or after entering the method body?
- **END position:** after the callee returns **successfully** or when an exception escapes the boundary.
- **END status:** at least `OK` and `ERROR`; `CANCELLED`/`TIMEOUT` may be added when domain semantics define them.
- **Timing semantics:** measures wall-clock time from the start to the end of the invocation—do not automatically infer CPU time, self-time of the method, or async task completion time.
- **Nested calls:** a child START can occur before the parent END; two calls to the same method still require separate IDs.
- **Exclusion conditions:** how are paths that never enter the probe (filtered methods, unsampled calls, JVM termination before END) handled?

## 2. Designing the Event Schema

A minimal observability schema might look like this:

| Field | START | END | Rationale |
| --- | --- | --- | --- |
| `eventType` | `CALL_START` | `CALL_END` | Distinguish the two points in time |
| `callId` / `spanId` | Required | **That exact ID** | Correlate a single invocation |
| `traceId` | If part of a trace | Unchanged | Link calls belonging to the same request |
| `parentSpanId` | If a parent exists | May be omitted if START already recorded it | Reconstruct the call tree |
| `methodId` | Owner + name + descriptor | May be repeated | Distinguish overloads / methods with the same name |
| `timeUtc` | UTC timestamp for log correlation | UTC timestamp if needed | Correlate with external systems |
| `startedNanos` / internal | Read from `System.nanoTime()` | Do not export raw timestamps across multiple JVMs | Compute duration within the same JVM |
| `elapsedNanos` | Not yet available | Present | Exact duration of the measured region |
| `outcome` | Not yet known | `OK`/`ERROR` | Count successes/failures |
| `errorType` | Absent | If `ERROR` | Exception type, e.g. `IllegalArgumentException` |
| `threadId`, process/service identity | As needed | As needed | Multi-thread / multi-process diagnostics |

**Log example illustrating the format**, not the output of a specific JDK:

```json
{"eventType":"CALL_START","traceId":"trace-abc","spanId":"span-17",
 "parentSpanId":"span-3","methodId":"demo/Service.save(Ljava/lang/String;)V",
 "threadId":22,"timeUtc":"2026-01-01T00:00:00Z"}
{"eventType":"CALL_END","traceId":"trace-abc","spanId":"span-17",
 "outcome":"OK","elapsedNanos":187400}
```

Distinguish **`spanId`**, **`traceId`**, and **method name**: `spanId` identifies one invocation; `traceId` identifies an entire request/trace that may cross multiple services; `methodId` only identifies the code being called. For an in-JVM tracer, an incrementing numeric ID works for demos; in multi-process systems, IDs/namespaces must be sufficient to avoid collisions.

Do not put `password`, access tokens, customer data, full parameters/return objects, or full stack traces directly into every event. **High-cardinality** fields (user IDs, URLs with arbitrary query strings, arguments) should not become metric labels; apply security policies, sampling, and data limits before emitting.

## 3. Measuring Duration Correctly: Which Clock?

Java provides two groups of time sources for different purposes:

- `Instant.now()` or a UTC clock is for **timestamps correlated with external logs**. Wall clocks can be adjusted by time synchronization or system administration.
- **`System.nanoTime()`** is the high-resolution time source for **elapsed intervals** within the **same JVM**. Its absolute value has an arbitrary origin, is not a Unix timestamp, and can be negative; only the difference `end - start` is meaningful.

Standard pattern:

```java
long startNanos = System.nanoTime();
try {
    doWork();
} finally {
    long elapsedNanos = System.nanoTime() - startNanos;
    // Emit elapsedNanos with CALL_END (if the collector is reliable).
}
```

This is an **illustrative fragment**; `doWork()` represents application code. `nanoTime` has nanosecond precision in its representation but does not guarantee nanosecond resolution from the underlying timer, and differences spanning more than roughly 292 years can overflow `long`. Avoid computing elapsed time with `Instant.now().toEpochMilli()` when you need a stable interval clock.

**The measurement boundary affects the numbers:** placing START before synchronous logging includes the cost of logging START; reading `startNanos` after the logging step can exclude hook overhead. Decide according to your goal and benchmark the overhead before comparing latencies of very short methods. `elapsedNanos` is the **elapsed wall time** of the chosen region, not CPU time.

## 4. The START/END Contract and Exit Paths

A call can terminate via:

| Exit Path | Event to Record | Program Behavior That Must Be Preserved |
| --- | --- | --- |
| Normal `return` | `CALL_END(outcome=OK)` | Return the **exact value**, including `null` |
| `void return` | `CALL_END(outcome=OK)` | Do not fabricate a new return value |
| `throw new ...` inside the method | `CALL_END(outcome=ERROR)` if the exception **escapes the boundary** | Rethrow the exact exception |
| Child callee throws an uncaught exception | `CALL_END(outcome=ERROR)` for the parent method during unwinding | Do not turn an error into success |
| Exception caught and handled inside the method | `CALL_END(outcome=OK)` if the method still returns normally | Do not mark an already-handled exception as ERROR |
| Method returns an incomplete `CompletableFuture` | END of the **method return** is `OK` if returning the stage succeeds | Must not be confused with END when the **async task** completes |
| JVM killed/aborted before END | May **miss END** | Collector must detect dangling/lost spans and timeouts |

**`try/finally`** is the clearest model at the Java level:

```java
long callId = onStart("methodName");
Throwable error = null;
try {
    return callOriginal();
} catch (Throwable failure) {
    error = failure;
    throw failure;
} finally {
    onEnd(callId, error);
}
```

The snippet above is **Java-syntax pseudocode** (not standalone): `onStart`, `callOriginal`, and `onEnd` are defined according to the actual design. `finally` runs when code leaves the block via `return` or exception, aside from process/JVM termination mechanisms; it does not guarantee log delivery from a disconnected collector. If **`onEnd` itself throws an exception**, it can **mask the original return value or exception**—this is a serious instrumentation bug that must be controlled at the sink level.

Another important point: **the timing of recording END** must be consistent. If END is emitted prematurely before the return value/exception is determined, the reporter must not record a success status while the measured region can still fail.

## 5. First Runnable Java 17+ Example: START/END Pairs for Nested Calls and Exceptions

The first example is a wrapper that instruments code in plain Java. It does not modify bytecode yet, but it captures the exact **event contract** that bytecode instrumentation must produce: unique IDs per invocation, parent/child relationships, `nanoTime` duration, `ThreadLocal` cleanup, and recording ERROR while still rethrowing the exception.

Save **`TraceCallsDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicLong;

public final class TraceCallsDemo {
    private TraceCallsDemo() {}

    private record Frame(
            long id, long parentId, String method, long startedNanos) {}
    private record Completed(
            long id, String status, long elapsedNanos, String errorType) {}

    private static final AtomicLong NEXT_ID = new AtomicLong();
    private static final ThreadLocal<Deque<Frame>> STACK =
            ThreadLocal.withInitial(ArrayDeque::new);
    private static final Queue<Completed> HISTORY =
            new ConcurrentLinkedQueue<>();

    @FunctionalInterface
    interface Work<T> {
        T run() throws Throwable;
    }

    static <T> T traced(String method, Work<T> work) throws Throwable {
        Deque<Frame> frames = STACK.get();
        Frame parent = frames.peek();

        Frame current = new Frame(
                NEXT_ID.incrementAndGet(),
                parent == null ? 0 : parent.id(),
                method,
                System.nanoTime());
        frames.push(current);

        System.out.println("START id=" + current.id()
                + " parent=" + current.parentId()
                + " method=" + current.method());

        String status = "OK";
        String errorType = null;
        try {
            return work.run();
        } catch (Throwable failure) {
            status = "ERROR";
            errorType = failure.getClass().getSimpleName();
            throw failure;
        } finally {
            long elapsedNanos = System.nanoTime() - current.startedNanos();
            frames.pop();
            if (frames.isEmpty()) {
                STACK.remove();
            }
            HISTORY.add(new Completed(
                    current.id(), status, elapsedNanos, errorType));
            System.out.println("END id=" + current.id()
                    + " status=" + status);
        }
    }

    public static void main(String[] args) throws Throwable {
        int answer = traced("outer", () ->
                traced("inner", () -> 5) + 3);
        System.out.println("RESULT=" + answer);

        try {
            traced("fail", () -> {
                throw new IllegalArgumentException("bad");
            });
        } catch (IllegalArgumentException e) {
            System.out.println("CAUGHT=" + e.getMessage());
        }

        System.out.println("COMPLETED=" + HISTORY.size());
    }
}
```

Run with JDK 17 or later:

```bash
javac TraceCallsDemo.java
java TraceCallsDemo
```

**Exact stdout in this sequential run** (durations are stored in `HISTORY` rather than printed, so machine-dependent numbers do not vary the output):

```text
START id=1 parent=0 method=outer
START id=2 parent=1 method=inner
END id=2 status=OK
END id=1 status=OK
RESULT=8
START id=3 parent=0 method=fail
END id=3 status=ERROR
CAUGHT=bad
COMPLETED=3
```

**Reading the output:**

1. `outer` starts with `id=1` and has no parent, so `parent=0` by **demo convention**.
2. `inner` runs inside `outer`, so it gets `id=2, parent=1`. `END 2` occurs **before `END 1`** because of stack nesting.
3. `RESULT=8` proves the wrapper returns the exact `5+3` result without altering computation logic.
4. `fail` has `id=3`, END records `ERROR`, and the exception **still propagates** to the `catch` in `main`, producing `CAUGHT=bad`.
5. `COMPLETED=3` confirms all three calls were recorded. `HISTORY` stores both `elapsedNanos` and `errorType`; the demo omits duration from stdout to keep output deterministic.

**Limitations of this example:** `System.out.println` is a synchronous sink for learning purposes. If the logger fails during START/END, the demo does not yet implement a fail-open policy to protect the application. `AtomicLong` guarantees distinct IDs within a single running process, **not** uniqueness across multiple processes or restarts. `ThreadLocal` only preserves parent relationships automatically when calls stay on the same thread; it must not be treated as a distributed trace context.

### 5.1. Why Must `ThreadLocal` Be Cleaned Up?

When using worker threads from a thread pool, a thread can handle many requests sequentially. Leaving behind the stack/trace context from an old request causes wrong parent correlation on subsequent requests and retains unnecessary references.

In the demo, `frames.pop()` balances `frames.push(current)`, and `STACK.remove()` clears the entry when the stack becomes empty. This is the rule of using `ThreadLocal` at **exact lifecycle boundaries**. With asynchronous callbacks, virtual threads, `Executor`, or reactive streams, context must be propagated/restored explicitly rather than relying implicitly on whichever thread runs the final callback.

## 6. Second Runnable Java 17+ Example: Automatic Events Around Interface Calls

To show how to instrument without **modifying the target method body**, the next example uses a **JDK Dynamic Proxy** for an interface. The proxy only records calls that go **through the proxy**; it does not instrument the entire JVM and does not capture `this.otherMethod()` self-invocations inside the implementation that bypass the proxy.

Save **`ProxyEventsDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicLong;

public final class ProxyEventsDemo {
    private ProxyEventsDemo() {}

    public interface Calculator {
        int add(int a, int b);
        void fail();
    }

    public static final class CalculatorImpl implements Calculator {
        public int add(int a, int b) {
            return a + b;
        }

        public void fail() {
            throw new IllegalStateException("stop");
        }
    }

    private static final AtomicLong IDS = new AtomicLong();

    public static void main(String[] args) {
        Calculator target = new CalculatorImpl();

        Calculator proxy = (Calculator) Proxy.newProxyInstance(
                Calculator.class.getClassLoader(),
                new Class<?>[] {Calculator.class},
                (proxyObject, method, arguments) -> {
                    long id = IDS.incrementAndGet();
                    String status = "OK";
                    System.out.println("START id=" + id
                            + " method=" + method.getName());

                    try {
                        return method.invoke(target, arguments);
                    } catch (InvocationTargetException failure) {
                        status = "ERROR";
                        throw failure.getCause();
                    } catch (ReflectiveOperationException failure) {
                        status = "ERROR";
                        throw new IllegalStateException(failure);
                    } finally {
                        System.out.println("END id=" + id
                                + " status=" + status);
                    }
                });

        System.out.println("VALUE=" + proxy.add(2, 3));
        try {
            proxy.fail();
        } catch (IllegalStateException e) {
            System.out.println("CAUGHT=" + e.getMessage());
        }
    }
}
```

Commands:

```bash
javac ProxyEventsDemo.java
java ProxyEventsDemo
```

Stdout:

```text
START id=1 method=add
END id=1 status=OK
VALUE=5
START id=2 method=fail
END id=2 status=ERROR
CAUGHT=stop
```

Here `Method.invoke` wraps exceptions from the target in `InvocationTargetException`; the handler unwraps **`getCause()`** and rethrows it so the caller still sees `IllegalStateException("stop")`. `finally` emits a single END for both paths in the example.

**Boundary:** Dynamic Proxy applies to **interfaces whose calls pass through the proxy**. It does not automatically intercept `private`/`static` methods, constructors, or self-invocations on the real object. When you need to measure all entries to a method regardless of caller, you must choose **bytecode entry/exit** probes or an equivalent instrumentation mechanism.

## 7. From Java `try/finally` to Bytecode Instrumentation

A `ClassFileTransformer` modifies `.class` definitions at load/retransform time; ASM or the Class-File API can help insert instructions around methods or call sites. The transformer must **read the input `classfileBuffer` without mutating it in place**, and return a new valid class file byte array when transforming.

In the JVM, method calls can use opcodes such as:

- `invokevirtual`: instance method with virtual dispatch.
- `invokeinterface`: call through an interface.
- `invokestatic`: static method.
- `invokespecial`: special invocations, including constructors and certain private/super methods.
- `invokedynamic`: dynamic call site (lambda metafactory, string concatenation, and related mechanisms); not like a regular `invokevirtual`.

With method-level instrumentation, **entry** can be placed right after the prologue generated by the instrumentation library; **normal exit** occurs before these instructions:

| Return Opcode | Value on Operand Stack Before Return | Requirement When Inserting END |
| --- | --- | --- |
| `ireturn` | `int` (including boolean/byte/char/short in bytecode) | One `int` must remain intact after calling the hook |
| `lreturn` | `long` (category 2) | Preserve one `long`; if duplicating via opcode, use category-2 operations such as `dup2` |
| `freturn` | `float` | Preserve `float` |
| `dreturn` | `double` (category 2) | Preserve `double` |
| `areturn` | reference | Preserve reference, including `null` |
| `return` | No return value | Hook must not consume a return operand |

**Do not** lose the return value. For example, before `ireturn`, the operand stack holds `[result:int]`:

```text
...                           stack = [result]
getstatic System.out          stack = [result, out]
ldc "END"                     stack = [result, out, "END"]
invokevirtual println(String) stack = [result]
ireturn                       return result to caller
```

This is a **bytecode diagram**, not a standalone Java program; `getstatic`/`invokevirtual` in a real class file require exact owner/name/descriptor and constant-pool references. The `println(String)` hook consumes `out` and `"END"`, leaving `result` in place. If the logger consumes the result itself, use `dup`/`dup2` or store the value in a temporary local variable and reload it. The same applies to `lreturn`/`dreturn` and all return opcodes.

For **caller-site instrumentation**, the receiver/arguments may already be on the operand stack before `invoke*`. Inserting logger instructions that alter that order can cause the verifier to reject the class or invoke the wrong method. After `invoke*`, preserve the return value on the stack while emitting END. In the exception case, END(ERROR) must execute along the unwind path.

## 8. Why Inserting at Every `return` and `athrow` Is Still Not Enough

ASM provides `org.objectweb.asm.commons.AdviceAdapter` with:

- `onMethodEnter()` to emit code at method start (for constructors, the callback is deferred until after the super/this constructor call).
- `onMethodExit(int opcode)` to emit code **before explicit exit instructions**: the six `return` opcodes and `ATHROW`.

A common pitfall: **`onMethodExit(ATHROW)` does not automatically catch all implicit exceptions occurring during execution**, for example:

```java
static int parseNumber(String s) {
    return Integer.parseInt(s);
}
```

This is a **fragment**. If `Integer.parseInt(s)` throws `NumberFormatException` and the exception propagates directly out of `parseNumber`, the bytecode of `parseNumber` may **not contain an `athrow` opcode** along that exit path. It only has `invokestatic parseInt` followed by `ireturn` on the normal path. Therefore, an `AdviceAdapter` that only inserts “exit before return/ATHROW” can **miss the END(ERROR) event** for this call.

To observe *every exception escaping the region* with Java semantics, a common bytecode design adds a **catch-all exception handler** around the measured body and then rethrows:

```text
on method entry:
    callId = Trace.start(methodId)
tryStart:
    <original method instructions>
    ... at each normal return:
        Trace.end(callId, OK)
        return originalValue
tryEnd:
catch (Throwable t):
    Trace.end(callId, ERROR, typeOf(t))
    throw t
```

**This is ASM algorithm pseudocode**, not Java source or standalone bytecode assembly. Ensure the try region starts **after START succeeds**, covers the region to be measured, has accurate label boundaries, and the handler does not fall inside its own catch range. Use a single END(ERROR) strategy for the same exception: if you both record END(ERROR) in `onMethodExit(ATHROW)` **and** record END(ERROR) in the catch-all handler, one exception can produce **two ENDs**.

Exceptions caught and handled by an **internal** handler before the method returns normally should ultimately record `OK`. If you also want to count every *thrown* exception, that is a separate event type (`EXCEPTION_THROWN`) and must not be conflated with invocation failure status.

### 8.1. Mandatory Class File Updates After Injection

- **`max_stack`:** extra instructions and hook parameters can increase peak stack depth.
- **`max_locals`:** a new call ID, start timestamp, or `Throwable` local needs valid slots; `long`/`double` values occupy two slots.
- **`StackMapTable` / verification frames:** must be valid at branch targets and handler entries after adding try/catch branches.
- **`exception_table`:** `[start_pc,end_pc)` and `handler_pc` must point to the updated offsets; the catch-all handler needs the right precedence relative to original handlers.
- **Jump targets, switch padding, debug tables:** adjust when `code_length`/offsets change.
- **Method descriptor and return opcode:** preserve exact types. Bytecode returning the wrong type can cause `VerifyError`.
- **Constructor `<init>`:** do not access `this` before the object is fully initialized; use `AdviceAdapter` in accordance with constructor semantics.
- **`abstract`/`native` methods:** have no `Code` attribute for direct instruction injection; use another strategy if needed.
- **Synchronized methods:** start/end points relative to monitor acquisition/release differ depending on placement; avoid mismeasuring lock-wait time.

With ASM, `ClassWriter.COMPUTE_MAXS`/`COMPUTE_FRAMES` can help compute metadata, but it cannot fix broken **hook logic**, does not solve all class loader/hierarchy cases, and does not guarantee semantic preservation. Verify with `javap -c -v` and run the transformed class.

## 9. At the Call Site (Caller): When Should START Be Placed?

Consider the source:

```java
int result = service.calculate(expensiveArgument());
```

Bytecode typically evaluates the receiver and arguments **before** executing `invokevirtual`. If START is inserted **right before `invokevirtual`**, it **excludes** the time spent in `expensiveArgument()`. If START is inserted **before argument evaluation**, it includes preparation time and pre-call side effects.

```text
aload service
invokestatic expensiveArgument()I  // evaluate argument
START(callId)                      // probe point A: call dispatch
invokevirtual calculate(I)I
END_OK(callId)
...                                // use result
```

This is a **sequence diagram**, not a complete opcode listing: the receiver and arguments are already on the operand stack, so the injected code must preserve them. If `expensiveArgument()` throws an exception, point A has not emitted START yet because `calculate` was never dispatched. If you want to measure the whole expression, place START earlier according to your intent.

With **callee method entry**, END corresponds to when the method finishes. With **caller call-site**, END can also include failures at `invokevirtual` due to a null receiver or resolution/linking happening at the call site. Both measurements **can legitimately differ** because the boundaries differ.

Do not blindly instrument every `invoke*`: a single method may call loggers, JDK internals, tiny helpers millions of times, or `invokedynamic`. Select targets by owner/name/descriptor or configuration policy, and exclude telemetry classes themselves to prevent recursive instrumentation.

## 10. Synchronous Return vs. Async Task Completion

Example:

```java
CompletionStage<String> submit() {
    return CompletableFuture.supplyAsync(() -> slowWork());
}
```

This is a **fragment**; imports and `slowWork()` are omitted. If instrumented at **method entry/return**, END(OK) occurs **when `submit` returns the stage**, while `slowWork()` is still running. That measurement is the **submit / stage-creation time**, not the actual task completion time.

If the goal is **asynchronous task completion time**, attach a callback to the stage:

```java
// Illustrative fragment: assumes id was created and Trace.end does not throw.
CompletionStage<String> stage = submit();
return stage.whenComplete((value, error) ->
        Trace.end(id, error == null ? "OK" : "ERROR"));
```

This is a **fragment**, not a complete program. You must also handle cases where **`submit()` throws before returning a stage**, the stage completes via cancellation, runs on another executor, or the callback itself fails. `whenComplete` creates a dependent stage; **if the callback throws an exception**, it can affect the completion path of the new stage. Design the reporter to be **non-throwing** or isolate telemetry errors appropriately.

When context crosses threads, `ThreadLocal` does not automatically follow `CompletableFuture`, `Executor`, or reactive pipelines. Propagate the ID/context explicitly and decide who owns END; if you instrument both method return **and** stage completion, create **two distinct span types** rather than sharing one `spanId` and emitting duplicate ENDs.

## 11. Correctness Under Exceptions and Reporter Failures

A logger/hook can throw an exception itself (serialization failure, connection error, `OutOfMemoryError`), block on I/O, or call into a method that is itself instrumented. Consequences can include:

- END(OK) is recorded and then the hook throws, causing the caller to see ERROR even though the original code succeeded.
- END(ERROR) throws a second error, masking the original exception.
- START succeeds but END is dropped due to a full queue, leaving an "orphan" span in the system.
- The hook calls a service that the probe instruments again, creating an infinite logging loop.
- START and END use different sampling/filter decisions, making them impossible to correlate.

**The design needs an explicit policy:** telemetry can be fail-open to preserve behavior, or use an owner-approved fail-closed mode. In typical monitoring, the goal is to preserve application results and exceptions, so isolate data recording, guard against reentrancy, use bounded buffers/queues, and track dropped-event counts.

If you need to log errors from the tracer itself, use a separate channel, rate limiting, and guards; do not put overlapping logging on the hot path. Never catch `Throwable` and **swallow application errors**: in `TraceCallsDemo`, the `catch` only marks `ERROR` and **rethrows the exact same object**.

### 11.1. "Exactly Once" Is a Local Condition, Not a Network Guarantee

In normal code execution, the goal is that **each accepted START produces at most one corresponding END**, and every exit path is covered. However, across a distributed collector, queues, crashes, restarts, and retries can still cause lost, duplicate, or out-of-order events.

Therefore, events should carry `spanId` and event kind; the ingestion pipeline should deduplicate where appropriate, set timeouts for spans missing END, and mark incomplete traces. **Do not** claim exactly-once event delivery just because the code has a `finally` block.

## 12. Analyzing Multi-Threaded and Recursive Events

### 12.1. Two Threads Calling the Same Method

```text
Thread-A: START(id=31, method=fetch) ───────── END(id=31)
Thread-B:     START(id=32, method=fetch) ─ END(id=32)

Event arrival:
START 31
START 32
END   32
END   31
```

If you match "the nearest END with the same method name", both pairs will be mismatched. Correlate by **ID**, not by timestamp order or method name. For nested calls on a single thread, a LIFO stack can assist parent tracking, but IDs are still required when events flow through queues/collectors.

### 12.2. Recursion

```text
factorial(3) START span1
  factorial(2) START span2, parent=span1
    factorial(1) START span3, parent=span2
    factorial(1) END span3
  factorial(2) END span2
factorial(3) END span1
```

All three calls share the same `methodId` but have different `spanId`s. If you only use the method name as the key in a `startTime` map, the inner call **overwrites** the outer call's start time. To preserve parent relationships, use a scope stack or explicit nesting context; for async calls crossing threads, pass context across task boundaries.

### 12.3. Synchronous Nested Spans and Time

For a parent span `P` containing child `C`, typically:

- **Inclusive duration of P:** time from START(P) to END(P), including time waiting for children and all work within that interval.
- **Exclusive time of P:** the portion of the parent's time not spent in child intervals within the corresponding measurement scope; simply subtracting `sum(duration(children))` can be **wrong** when child spans overlap or execute in parallel.
- **Wall time** differs from CPU time, I/O wait, and lock wait. Do not label `nanoTime` data as "CPU cost".

Explicitly specify whether a metric/trace represents **inclusive**, **exclusive**, **service time**, **queue wait**, or **end-to-end latency**.

## 13. Sampling, Cardinality, and Performance Limits

Recording START/END for every tiny call can cost more than the work being measured. Before production deployment, decide:

| Decision | How to Apply |
| --- | --- |
| **Target selection** | Instrument service boundaries or appropriate methods; avoid every getter/setter in the JVM |
| **Sampling** | Decide whether to collect **at START**, and keep that decision for END; avoid sampling START and END independently |
| **Buffering** | Use bounded async queues/batches; define drop behavior when full |
| **Cardinality** | Use normalized method names; do not create metric labels from arbitrary arguments/`userId` |
| **Stack cost** | Minimize local allocations/boxing, logging, and injected branches |
| **Reentrancy** | Exclude collector/logger/agent helper classes from instrumentation |
| **Privacy** | Record only exception types and necessary metadata; redact sensitive data |
| **Clock & IDs** | Monotonic time for duration; trace/span identifiers for correlation; never correlate by timestamp |
| **Resilience** | Distinguish dropped events, exporter failures, service crashes, and timeouts |

If an invocation **is not sampled**, typically **emit neither START nor END** for that span. However, the sampling decision may need to be kept in a very lightweight scope so child spans and parent relationships remain consistent.

`System.out.println` in the examples makes learning easy to inspect; when instrumenting hot methods, use a real sink with asynchronous batching and backpressure. Avoid "one END = one HTTP request", which skews latency and risks error amplification.

## 14. Testing the Probe Before Production

### 14.1. Mandatory Test Scenarios

1. **Normal single call:** exactly one START and one END(OK), with the same ID.
2. **`void` and all return types:** `int`, `long`, `double`, reference, and `null` still return the exact value; operand stack is intact.
3. **Explicit exception:** `throw new ...` escapes the region, END(ERROR), original `Throwable` preserved.
4. **Implicit exception:** method calls another method and the callee throws; END(ERROR) still appears if the exception escapes the instrumented method.
5. **Caught exception:** error is handled internally and the method returns normally => END(OK) for the invocation.
6. **Multiple return branches:** `if/else`, early returns, loops all emit one END.
7. **Nested & recursion:** distinct IDs, correct `parentSpanId`, and ENDs can close in reverse order according to nesting.
8. **Concurrency:** no shared timestamp overwritten; do not correlate events by thread name.
9. **Async:** distinguish method return time from future/publisher completion time.
10. **Logger failure:** hook must not mask the original exception when fail-open is required.
11. **Bytecode verifier:** transformed class loads successfully; stack map frames, handler ranges, and offsets are valid.
12. **Coverage:** do not accidentally instrument logger/JDK core classes, abstract/native methods, or classes from unsupported loaders.

### 14.2. Using `javap` to Verify Injection

After capturing **BEFORE** and **AFTER** class snapshots from the transformer:

```bash
javap -classpath before -c -v -p demo.Target > before.javap.txt
javap -classpath after  -c -v -p demo.Target > after.javap.txt
diff -u before.javap.txt after.javap.txt
```

This is a **command pattern for Linux/macOS** when the `before` and `after` directories exist and contain `demo/Target.class`. On Windows, use the appropriate path separator and optionally `Compare-Object`. Key items to inspect in the diff: START at entry or before the call site, END on **every normal return**, exception handler covering the exact range, recomputed stack maps/`max_stack`/`max_locals`, and correct runtime execution.

With a Java agent instrumenting at runtime, `javap` on the original class file **does not automatically read the transformed bytecode in the JVM**. To compare, dump a snapshot of the **actual output bytes from the transformer** to a separate location in a test environment. Do not overwrite the original file and treat it as the agent's output.

### 14.3. Easy-to-Check QA Metrics

- `starts - ends` for **completed and fully delivered spans** must equal 0; currently active spans are the expected exception.
- Each `spanId` has one START and **at most one valid END** after deduplication.
- `elapsedNanos` is the difference of two `nanoTime` reads in the same JVM, not a subtraction of UTC timestamps across hosts.
- An exception terminating the method must produce END(ERROR), and the caller must still observe the exact `Throwable`; if caught internally and returned, END(OK).
- Given the same inputs, method results before/after instrumentation are identical, aside from approved telemetry side effects.
- When instrumentation is disabled, overhead and behavior return to expected levels; monitor dropped-event metrics, queue pressure, and recursion guards.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging START/END with only the method name | Cannot correlate concurrent/recursive calls | Unique ID per invocation |
| Recording END only before `return` | Missing END when an exception escapes | Properly scoped catch-all/finally |
| Relying on `onMethodExit(ATHROW)` for all errors | Misses implicit exceptions from other calls | Catch-all handler over the measured region |
| Emitting END twice: at `ATHROW` and catch-all | Duplicate events, double-counted duration | Single path recording ERROR |
| Pushing logger calls that clobber stack values | `VerifyError` or altered return value | Preserve stack and return operand |
| Using `currentTimeMillis` as the elapsed clock | Affected by wall-clock adjustments / resolution | Use `System.nanoTime()` difference |
| Using `nanoTime` as a UTC timestamp | Cannot compare across JVMs/hosts | Use a separate UTC timestamp |
| Treating a method returning a future as task completion | Measured latency misses the async portion | Create a separate span around the completion stage |
| Not removing `ThreadLocal` on thread pools | Context leaks, wrong parent correlation | Pop and remove when the scope ends |
| Sampling START and END independently | One-sided spans | Keep the sampling decision per invocation |
| Reporter throws an exception inside `finally` | Masks original error or turns success into failure | Non-throwing/fail-open reporter per policy |
| Instrumenting logger classes too | Reentrancy and stack overflow | Exclusions/filters + recursion guard |
| Putting arguments/`toString` in metric labels | Data exposure, cardinality explosion | Use normalized method names only, sanitization |
| Computing parent `duration` as sum of child durations | Wrong when spans overlap/run in parallel | Measure via START(P)/END(P) boundaries |
| Testing only normal returns | Production misses END(ERROR) | Test explicit/implicit exceptions and branches |
| Assuming `finally` guarantees exactly-once delivery | Crashes/network/queues can still drop/duplicate | Span IDs, deduplication, timeouts & exporter metrics |

## 16. Self-Check Exercises

1. **In `total()`, there are two calls to `add`. If you only store the start time under the key `add`, what goes wrong?**  
   **Answer:** calls—especially nested or concurrent ones—can overwrite the same key. Use distinct `callId`/`spanId` values and a scope context.

2. **A method contains only `return Integer.parseInt(s);`. When `s="x"`, is inserting END before `IRETURN` enough?**  
   **Answer:** no. `parseInt` throws an exception so `IRETURN` never executes; a handler for exceptional exits is required.

3. **A method catches `IOException` and returns a fallback value normally. Should END be OK or ERROR?**  
   **Answer:** if END describes the **invocation's exit status**, it is `OK`. A separate `EXCEPTION_HANDLED` event can be recorded if needed.

4. **For a `long` return, can you use `dup` the same way as for an `int` return?**  
   **Answer:** no. `long` is category 2 and requires appropriate operations such as `dup2` or storing/loading a properly typed `long` slot.

5. **Two threads log START(id=1), START(id=2), END(id=2), END(id=1). Are the logs out of order?**  
   **Answer:** no. Overlapping calls can finish in any order; correlate by ID.

6. **START is placed right before `invokevirtual`, after evaluating arguments. Is argument evaluation time included in duration?**  
   **Answer:** no, unless the START boundary is placed earlier.

7. **A `CompletableFuture` is returned immediately, and the task finishes after 500 ms. Does a method-level END measure 500 ms?**  
   **Answer:** no. END at method return only measures creating/returning the future; measuring completion requires a separate span tied to the future's lifecycle.

8. **Why is it dangerous to call END(ERROR) in both `onMethodExit(ATHROW)` and a catch-all handler?**  
   **Answer:** the same exception can emit two ENDs; choose a single exit path.

9. **Does `try/finally` guarantee that the event has reached the collector?**  
   **Answer:** no. It only guarantees the local hook is called on normal Java exit paths; queues, network issues, or crashes can still lose events.

10. **To correlate spans across two microservices, should you use a local `AtomicLong`?**  
    **Answer:** not sufficient. You need properly scoped trace/span IDs across processes, context propagation over network headers, and distinct service/process identities.

11. **Why must the logger in END be designed not to throw exceptions when transparency is the goal?**  
    **Answer:** because END typically runs right around `return`/exception unwinding; a logger failure can alter the return value or mask the root cause.

12. **Why shouldn't “END(ERROR)” be recorded every time code executes a `throw`?**  
    **Answer:** the exception may be caught internally and the invocation may still complete successfully. END status must reflect exceptions **escaping the measurement boundary**.

## 17. Official References

- Oracle JDK 17 — **`System.nanoTime()`** (elapsed time measurement, arbitrary origin): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()
- Oracle JDK 17 — **`ThreadLocal`** and `remove()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Oracle JDK 17 — **`java.lang.reflect.Proxy`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html
- Oracle JDK 17 — **`Method.invoke` / `InvocationTargetException`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Oracle JDK 17 — **`ClassFileTransformer`** and `Instrumentation.addTransformer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- ASM Javadoc — **`AdviceAdapter`**, `onMethodEnter`, `onMethodExit`, and constructor behavior: https://asm.ow2.io/javadoc/org/objectweb/asm/commons/AdviceAdapter.html
- JVM Specification 17 — **`Code` attribute, exception table (`4.7.3)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3
- JVM Specification 17 — **`invoke*`, `ireturn`/`lreturn`/`areturn`/`athrow` instructions**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- W3C — **Trace Context** (trace-id, parent-id, and distributed tracing): https://www.w3.org/TR/trace-context/

When designing a probe, clearly define the **boundary**, generate **one ID per invocation**, record **START** once, record **END** on both normal and exceptional exits, compute duration using **`nanoTime` differences**, and preserve return values/exceptions intact. Only these decisions make event pairs meaningful and reliable enough for performance analysis.
