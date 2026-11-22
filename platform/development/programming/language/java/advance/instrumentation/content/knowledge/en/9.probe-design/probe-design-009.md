# Counting Nested Calls, Recursion, and Keeping Event Pairs Consistent

## 1. Why Is This Problem Harder Than a Counter Variable?

When instrumenting a Java method, we often want to know **how many times it was called**, **how many times it completed**, **how many times it failed**, and **how those calls are nested**. Simply incrementing a counter upon entering a method is not enough if you need to reconstruct the call tree, compute the number of in-flight calls, or detect lost events.

A simple example:

~~~text
root()
  -> sumDown(2)
       -> sumDown(1)
            -> sumDown(0)
  -> fail()   // throws exception, root catches and handles it
~~~

Here:

- `sumDown` is called **three times**, not once just because it has the same method name.
- The entire chain has **five invocations**: `root`, three `sumDown`, and one `fail`.
- `fail` fails, but `root` can **complete successfully** because it caught the exception.
- `ENTER` and `EXIT` events **do not necessarily alternate**: you can see three consecutive `ENTER` events before seeing a single `EXIT`.
- If each `ENTER` does not store its own **invocation ID**, you cannot reliably pair the entry and exit of recursive calls to a method with the same name.

This lesson falls within the scope of **probe design**: defining the meaning of counters, creating and ending per-invocation context, handling nested/recursive calls, preserving event pairs even when exceptions occur, and choosing thread-safe mechanisms when multiple threads run concurrently.

## 2. Defining Quantities Before Writing Instrumentation

| Quantity | Incremented when? | Interpretation |
| --- | --- | --- |
| `started` / `attempted` | An invocation passes the `ENTER` point successfully | Number of **calls**, including recursive and nested ones |
| `ended` / `completed` | The invocation passes the `EXIT` point exactly once | Number of times execution has left the observed scope |
| `success` | The invocation ends via a normal return | Outcome at that exact method boundary |
| `failure` | The invocation leaves the method via an observed exception/error | Not necessarily the number of **root errors** of a request |
| `active` / `inFlight` | `+1` on start, `-1` on end | Number of currently active invocations |
| `depth` | Current stack depth on entry | `0` for the thread's root call, `1` for its direct child |
| `parentId` | ID of the frame above on entry | Used to reconstruct the nested call tree |
| `invocationId` | Newly allocated for **each call** | Distinguishes calls to the same method, including recursion |

**Do not confuse a method name with an invocation ID.** Two invocations of `sumDown(int)` have the same class, name, and descriptor, but must have different IDs. If you want to aggregate call counts *per method*, group metrics by **method key** (for example, owner + name + descriptor + class loader type when needed); if you want to pair *events*, you must rely on **invocation ID**.

Counting `started` at method entry counts "actually entered the method past the probe," **not** the number of times the caller *intended* to call it. Exceptions occurring before reaching the entry hook or methods excluded from instrumentation will not be counted. Therefore, you must clearly document the **observation boundary** of the dashboard.

### 2.1. Consistency Conditions When No Invocations Are Running

After all tasks have finished and no events have been lost:

~~~text
started = ended
ended   = success + failure
active  = 0

While running:
started = ended + active
~~~

These three equalities are **logical invariants under an atomic snapshot and guaranteed scope**. In a multi-threaded system, reading `LongAdder.sum()` at different instants **does not produce an atomic snapshot**; therefore, reporting while work is active may show temporary discrepancies even when the code is correct. Verify exact counts after all tasks finish or use a more consistent snapshot mechanism.

Do not treat `ENTER` and `EXIT` as two separate calls: they are **two events of the same invocation**. An `EXIT` event reports the end of a call, not an additional call count.

## 3. What Must an ENTER/EXIT Event Pair Carry?

A minimal structure can be represented by the following data:

~~~text
ENTER {
  invocationId, parentId, methodKey, depth,
  threadId, startTime?, traceId?
}

EXIT {
  invocationId, parentId, depth,
  outcome: OK | ERROR,
  endTime?, errorType?
}
~~~

This is an **illustrative schema**, not Java code. Which fields are required depends on your monitoring goals. For nested/recursive calls, **invocationId** and **parentId** are the most important; `depth` helps validate the call tree.

Pairing rules:

1. **Each instrumented invocation has one `ENTER` and at most one `EXIT`**; if it has not exited yet, it is in the active state.
2. `EXIT.invocationId == ENTER.invocationId`; **do not** pair by method name, thread ID, or timestamp.
3. For synchronous calls on the same thread, each child `ENTER` sets `parentId` to the ID of the frame currently at the top of the stack; when finishing, the child frame must leave the stack **before** the parent frame (LIFO).
4. A recursive invocation is a **new frame**; it must not overwrite the ID, start time, or outcome state of the previous frame.
5. When an exception unwinds across multiple methods, each method can have its own `EXIT ERROR`; when a method catches the exception and returns normally, that method itself is `OK`.
6. Do not emit `EXIT` again inside `catch` if `finally` logic is already responsible for ending the invocation.

**A call can have multiple children, but only one direct parent.** For cross-thread tracing via an executor, you must carry the parent context explicitly; `ThreadLocal` on its own does not propagate tree context to another thread.

### 3.1. Stack Illustration of Recursive Calls

~~~text
Step                        Active Stack (bottom -> top)
ENTER root [id=1]            [1]
ENTER sumDown(2) [id=2]      [1,2]
ENTER sumDown(1) [id=3]      [1,2,3]
ENTER sumDown(0) [id=4]      [1,2,3,4]
EXIT sumDown(0) [id=4]       [1,2,3]
EXIT sumDown(1) [id=3]       [1,2]
EXIT sumDown(2) [id=2]       [1]
ENTER fail [id=5]            [1,5]
EXIT fail ERROR [id=5]       [1]
EXIT root OK [id=1]          []
~~~

Here, the `depth` of `root` is 0; the three `sumDown` calls have depths 1, 2, and 3 respectively. The representation uses a **stack frame**, not just a `ThreadLocal<Integer> depth`. Counting depth alone cannot preserve `parentId`, start time, or outcome for each invocation.

## 4. Scope Design for Java: begin at Entry, end in finally

Basic implementation pattern:

~~~java
Frame frame = begin(methodKey);
String outcome = "OK";
try {
    return callOriginalMethod();
} catch (RuntimeException | Error failure) {
    outcome = "ERROR";
    throw failure;
} finally {
    end(frame, outcome);
}
~~~

This is only **Java pseudocode inside a suitable wrapper method**, because `begin`, `end`, `methodKey`, and `callOriginalMethod` are APIs defined by the instrumentation author. The goal is to emphasize: entry creates the frame **once**, outcome is recorded according to how the method actually leaves the scope, and **`finally` is the single place that emits the end event**.

Points to remember:

- If the body returns early via `return`, `finally` still runs before the method actually returns the result.
- If the body throws an unchecked exception or `Error`, `finally` still executes during normal stack unwinding.
- If a parent catches an error from a child, the child ends with `ERROR` while the parent can be `OK`.
- `finally` has no execution guarantee if the JVM/process terminates abnormally, via `Runtime.halt`, power loss, or certain severe runtime failures; do not claim "events are always sent" in all situations.
- `finally` calling instrumentation code can also **throw an exception**. In production, event emission must be designed with a **fail-open** policy, minimizing allocations/logging and avoiding instrumentation errors masking business exceptions.
- If using `Supplier<T>`, the body does not declare checked exceptions; `catch (RuntimeException | Error)` covers errors that can escape under the normal contract. If using `Callable<T>`, you must also handle/rethrow checked `Exception` matching the signature.

### 4.1. Why Not Increment `end` in Both catch and finally?

Incorrect pattern:

~~~java
try {
    business();
} catch (RuntimeException ex) {
    ended.increment(); // WRONG: will double-count if finally also increments
    throw ex;
} finally {
    ended.increment();
}
~~~

If `business()` throws an error, `ended` increments **twice**, causing `started < ended`. The right way is for `catch` to only **mark the outcome**, while `finally` increments `ended` **once**.

If using `try-with-resources` with `AutoCloseable.close()` as the exit hook, remember that `close()` **does not automatically know** whether the body just returned or threw. To distinguish `OK`/`ERROR`, you must store the state explicitly in a wrapper or design the corresponding advice/error hook. Do not infer that `close` was called because of an error.

## 5. Standalone Runnable Java 17+ Example

The example below requires no Java agent or libraries outside the JDK. It uses a **probe-creating wrapper** to accurately simulate the method-entry/method-exit flow that an agent would generate. The goal is to clearly observe event pairing under **nested calls, recursion, exceptions, and exceptions caught by a parent**.

**File: `NestedInvocationDemo.java`**

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;
import java.util.function.Supplier;

public final class NestedInvocationDemo {
    private static final Trace TRACE = new Trace();

    private static int sumDown(int n) {
        return TRACE.call("sumDown", () ->
                n == 0 ? 0 : n + sumDown(n - 1));
    }

    private static int root() {
        return TRACE.call("root", () -> {
            int result = sumDown(2);
            try {
                TRACE.call("fail", () -> {
                    throw new IllegalStateException("boom");
                });
            } catch (IllegalStateException expected) {
                // root has handled the child's error.
            }
            return result;
        });
    }

    public static void main(String[] args) {
        int result = root();
        TRACE.events.forEach(System.out::println);
        System.out.println("result=" + result);
        System.out.println("started=" + TRACE.started.sum());
        System.out.println("ended=" + TRACE.ended.sum());
        System.out.println("ok=" + TRACE.ok.sum());
        System.out.println("error=" + TRACE.error.sum());
        System.out.println("active=" + TRACE.active.sum());
        if (TRACE.started.sum() != TRACE.ended.sum()
                || TRACE.active.sum() != 0) {
            throw new AssertionError("Unpaired calls");
        }
    }

    private record Frame(long id, long parentId, int depth, String name) {}

    private static final class Trace {
        private final AtomicLong nextId = new AtomicLong();
        private final ThreadLocal<Deque<Frame>> stack =
                ThreadLocal.withInitial(ArrayDeque::new);
        private final Queue<String> events = new ConcurrentLinkedQueue<>();
        private final LongAdder started = new LongAdder();
        private final LongAdder ended = new LongAdder();
        private final LongAdder ok = new LongAdder();
        private final LongAdder error = new LongAdder();
        private final LongAdder active = new LongAdder();

        private <T> T call(String name, Supplier<T> operation) {
            Deque<Frame> frames = stack.get();
            Frame parent = frames.peek();
            Frame current = new Frame(
                    nextId.incrementAndGet(),
                    parent == null ? 0 : parent.id(),
                    frames.size(), name);
            frames.push(current);
            started.increment();
            active.increment();
            events.add("ENTER id=" + current.id()
                    + " parent=" + current.parentId()
                    + " depth=" + current.depth()
                    + " name=" + current.name());
            String outcome = "OK";
            try {
                return operation.get();
            } catch (RuntimeException | Error failure) {
                outcome = "ERROR";
                throw failure;
            } finally {
                Frame finished = frames.pop();
                if (finished != current) {
                    throw new AssertionError("Stack order violated");
                }
                ended.increment();
                active.decrement();
                if ("OK".equals(outcome)) {
                    ok.increment();
                } else {
                    error.increment();
                }
                events.add("EXIT id=" + current.id()
                        + " parent=" + current.parentId()
                        + " depth=" + current.depth()
                        + " outcome=" + outcome);
                if (frames.isEmpty()) {
                    stack.remove();
                }
            }
        }
    }
}
~~~

In the demo, `Frame` is an **immutable record** storing ID, parent, depth, and method name. `Trace` has a `ThreadLocal<Deque<Frame>>`: each thread gets its own stack. `AtomicLong` generates unique IDs within a single `Trace` instance. `LongAdder` instances collect counts and `ConcurrentLinkedQueue` holds events; the queue buffers them before printing, avoiding calling a logger directly inside the callback.

**Important detail:** `AssertionError("Stack order violated")` at the end is an **invariant check for demo/testing**. In a production agent, you should not throw additional exceptions from telemetry that mask application exceptions; when designing fail-open behavior, separate the diagnostic channel, record instrumentation failures, and recover context according to a safe policy. The demo assumes internal event/counter recording succeeds.

### 5.1. Compiling and Running

With JDK 17 or newer:

~~~bash
javac --release 17 NestedInvocationDemo.java
java NestedInvocationDemo
~~~

**Exact stdout** of the example above when run on a single thread:

~~~text
ENTER id=1 parent=0 depth=0 name=root
ENTER id=2 parent=1 depth=1 name=sumDown
ENTER id=3 parent=2 depth=2 name=sumDown
ENTER id=4 parent=3 depth=3 name=sumDown
EXIT id=4 parent=3 depth=3 outcome=OK
EXIT id=3 parent=2 depth=2 outcome=OK
EXIT id=2 parent=1 depth=1 outcome=OK
ENTER id=5 parent=1 depth=1 name=fail
EXIT id=5 parent=1 depth=1 outcome=ERROR
EXIT id=1 parent=0 depth=0 outcome=OK
result=3
started=5
ended=5
ok=4
error=1
active=0
~~~

Meaning of each line:

- ID 1 is assigned to `root`; IDs 2–4 are **three distinct recursive invocations** of `sumDown`.
- `sumDown(0)` exits before `sumDown(1)` and then `sumDown(2)`, obeying the LIFO order of a synchronous stack.
- ID 5 (method `fail`) throws `IllegalStateException`, resulting in `EXIT ERROR`.
- `root` **catches** the child exception and continues to return the sum `2 + 1 + 0 = 3`, so ID 1 has `EXIT OK`.
- There are five `ENTER` events, five `EXIT` events, four `OK`, one `ERROR`, and zero active scopes remaining.

This output was **verified with `javac --release 17` and `java`**, not assumed stdout. Running concurrently across multiple threads will produce different ID/event ordering; **do not** treat the global ordering of a single-threaded example as a contract for concurrent cases.

### 5.2. Why Is `ThreadLocal.remove()` Called When the Stack Is Empty?

When an outermost invocation finishes, there are no active frames left on the current thread. `stack.remove()` removes the ThreadLocal variable's copy bound to that thread, helping avoid retaining old request/context data in long-lived thread pools. When the thread calls `stack.get()` next time, `ThreadLocal.withInitial` can create a new deque.

Do not call `remove()` after **every** nested call: if a parent remains in the deque, removing the ThreadLocal will lose the parent stack. Only remove when **the entire thread stack is empty**.

## 6. Two Different Types of Counting: Invocation and Root Request

Suppose an HTTP request calls:

~~~text
request()
  -> dao.query()
  -> retry()
       -> dao.query()
       -> dao.query()
~~~

If counting **each method invocation** of `dao.query`, there are three. If counting **logical database operations** that the retry handles, there may be only one or two business-level operations, depending on how it is defined; if counting **HTTP requests**, there is only one. Different counters answer different questions.

Therefore, before instrumenting, you must choose:

| Question | Correct entity to count |
| --- | --- |
| How many times was method `foo` entered? | Each `ENTER` at the method boundary |
| How many requests completed? | Each completed root request |
| Average retries per operation? | Number of attempts divided by number of logical operations |
| How many methods are currently running? | Number of active frames in that scope |
| How many method calls failed? | Number of `EXIT ERROR` across invocations |
| How many independent business errors? | By error/request ID or root-cause event, **not** simply summing errors at every stack level |

When an exception passes through three frames uncaught, **three `EXIT ERROR` events can be correct** for a method failure metric. However, if a dashboard says "three independent production errors" from those three events, that is semantically wrong. To aggregate root causes, you need correlation/trace IDs and a deduplication policy.

**Recursion** makes counting mistakes obvious: every time a method calls itself, it is still a valid invocation. You cannot use a `ThreadLocal<Boolean> insideMethod` flag to skip all nested calls if the goal is to count **every individual call**.

## 7. Distinguishing Business Recursion from Agent Self-Reentrancy

Two phenomena must be separated:

1. **Business recursion:** `factorial(3) -> factorial(2) -> factorial(1)`. If measuring invocation counts, all three frames must be counted.
2. **Instrumentation reentrancy:** advice/transformer calls a logger or helper, and that logger/helper is itself instrumented by the agent, leading to an infinite chain of self-triggering hooks.

A common mistake is preventing self-instrumentation with a condition like "skip if `depth > 0`." That drops **all** valid child methods and corrupts recursive metrics.

Better approaches:

- **Exclude agent, helper, logger, exporter, and instrumentation framework namespaces** from the transformer's matcher.
- For recorders/advice at risk of self-reentrancy, use a **reentrancy guard dedicated to the event-recording process**, separate from the business invocation stack.
- When the guard indicates the recorder is active, do not instrument **recorder code**; however, nested business methods must still create their own frames when permitted.
- Do not allocate an ID or push a frame when deciding to **skip** an invocation completely, to avoid creating an `ENTER` without an `EXIT`. If you still need to preserve parent context across a skipped segment, you must have clear rules for a "transparent scope."

`ThreadLocal<Boolean> guard` and `ThreadLocal<Deque<Frame>> callStack` serve **two different purposes**; do not use a single Boolean variable to replace both.

## 8. Method Entry/Exit in Bytecode or a Java Agent

The example in Section 5 uses a wrapper for ease of running. In real bytecode instrumentation, the equivalent logic must be inserted as **a pair of hooks**:

~~~text
METHOD_ENTRY:
    frame = recorder.begin(methodKey, currentContext)
    save frame in invocation-local state

METHOD_EXIT (normal return OR thrown exception):
    outcome = method threw ? ERROR : OK
    recorder.end(frame, outcome)
~~~

This is **pseudocode**, not standard syntax of a specific library. If using Byte Buddy Advice, you must ensure the exit advice covers thrown exceptions via the proper library options, passes the entry hook's token to the exit hook, and avoids emitting events in multiple places. If using ASM or the Class-File API, you must handle return paths and exceptional control flow according to bytecode rules, including the exception table and frame verification.

### 8.1. Do Not Insert Only at Every `return`

A method can exit via:

- `return`, `ireturn`, `areturn`, ... across multiple branches.
- `athrow` inside the method.
- An exception from a child method or any instruction, **with no explicit `athrow` opcode in the instrumented method**.
- An exception caught **inside the method**, followed by a normal return.

Adding `EXIT` only before return opcodes **misses exceptional exit paths**. Adding an `EXIT ERROR` immediately whenever a child method throws can also be wrong because the exception may be caught and handled internally by the parent method. Hooks must follow the **method boundary** and the actual outcome when the method leaves scope.

When instrumenting bytecode directly, the semantically safe approach is usually to transform the method body within an equivalent `try/finally` region (with proper return/exception handling and stack map frames). Do not add arbitrary catch-all blocks without understanding the bytecode verifier, synchronized methods, constructors, and initialization order.

### 8.2. The Entry Token Must Be **Per-Invocation**

With recursion, a global variable such as:

~~~java
static long lastStartNanos; // WRONG if shared across all invocations
~~~

will be overwritten by the child call. When unwinding, the parent receives the child's start time, leading to wrong durations and unpaired events.

Instead, the token/scope must be stored in a local variable specific to **each invocation** or in a LIFO `ThreadLocal<Deque<Frame>>`. The token contains at least `id`; when timing is needed, it also contains `startNanos` and the `parentId` link. Do not use a single `ThreadLocal<Long>` if there are nested calls where you need to store separate start timestamps.

### 8.3. Inclusive and Exclusive Duration

If adding timing:

~~~text
inclusiveTime(frame) = time from ENTER to EXIT of the frame
exclusiveTime(frame) = inclusiveTime(frame) - total synchronous child time attributed to the frame
~~~

Nested child calls can be subtracted from the parent by adding `childDuration` to the parent frame **when the child finishes**. This is a separate calculation from invocation counting. Be careful when children run asynchronously or in parallel: simple subtraction can be wrong or negative because child durations **overlap**, so the calculation must be redefined.

Use `System.nanoTime()` for elapsed time within a single JVM, not `System.currentTimeMillis()` to infer short durations. Do not mix `nanoTime` values from two different JVMs and take their difference because their origin is not shared.

## 9. Multiple Threads, Executors, and Asynchronous Calls

`ThreadLocal<Deque<Frame>>` works when calls are **synchronous on the same thread**. However, it does not automatically propagate parent context across `ExecutorService`, `CompletableFuture`, or a callback on another thread.

~~~text
Thread A: HTTP request id=10
    -> submit task ------------+
                               |
Thread B:                      +-> task id=11, parentId=10
                                   -> DB call id=12, parentId=11
~~~

If Thread B starts with an empty stack, `parentId` will be 0 unless explicitly propagated; the tree loses its link. You must **capture context** at the submit point, carry it through a task wrapper, restore it onto Thread B before running, and clean up/restore the previous context in `finally`. A shared trace/correlation ID should be distinguished from an individual **invocation ID**.

Do not assume `InheritableThreadLocal` solves thread pools: threads are reused, not always created fresh per request. Context can leak or be misattributed. You can use the context propagation mechanism of an existing tracing library, but you still need to understand its contract and cleanup points.

### 9.1. Does "Method Ended" Mean the Async Operation Ended?

Not necessarily. For a method:

~~~java
CompletableFuture<String> fetchAsync() {
    return startRemoteCall();
}
~~~

This is an **illustrative snippet** assuming `startRemoteCall()` exists. The `fetchAsync` method ends **when it returns the future**, not when the remote call completes. If measuring *method invocations*, placing `EXIT` at return is correct. If you want to measure the *async operation*, you must create **a separate logical scope** that ends when the future completes/cancels/fails and pair it by the operation's ID, rather than keeping the method frame on the ThreadLocal stack after return.

Synchronous and asynchronous lifecycles differ. Avoid sharing a single `active` counter without clearly distinguishing boundaries, because you may see `active=0` even while many futures are still running (correct for the method metric, wrong for the operation metric).

### 9.2. Event Order in Concurrent Systems

Within a single synchronous thread, the stack naturally has LIFO order. However, events from multiple threads can interleave:

~~~text
T1 ENTER id=100
T2 ENTER id=200
T2 EXIT  id=200
T1 EXIT  id=100
~~~

Do not interpret these as two nested calls simply because they interleave on a single stream. You must include `threadId`, `parentId`, `traceId`, and `invocationId` accordingly. When sent over queues, networks, or distributed systems, timestamps/event order may also not reflect exact real-time ordering across nodes.

## 10. Maintaining Consistency When Events Can Be Lost

Even if code inside a JVM always calls the end hook properly, the collection pipeline outside the JVM can still lose an event: full queues, exporter timeouts, process restarts, network failures, or mismatched sampling at both ends.

You must distinguish three layers of guarantees:

| Layer | Question | How to verify |
| --- | --- | --- |
| **Method lifecycle** | Does an invocation trigger the end hook exactly once? | Unit/integration tests for normal, exception, nested, and recursive cases |
| **Recorder/buffer** | Are both events recorded internally? | Check IDs, dropped-event counters, queue/backpressure |
| **Transport/backend** | Do both events reach the analytics system? | Dedupe by event key, reconciliation, bounded retries |

**Event pairs are not naturally atomic when emitted independently.** A backend might see `ENTER` without seeing `EXIT` yet because the invocation is still active, or because the event arrived late or was lost. Do not immediately equate an "open span" with a "memory leak." You can apply a TTL and an `UNKNOWN/TIMED_OUT` state for invocations whose exit is not seen after a threshold, instead of fabricating a fake `EXIT OK`.

### 10.1. Sampling Must Be Consistent Per Invocation

Wrong:

~~~text
onEnter: random() < 0.1 -> emit ENTER
onExit:  random() < 0.1 -> emit EXIT
~~~

Two independent decisions produce orphan `ENTER` events or `EXIT` events without an `ENTER`. The right way is to decide **once** at entry, store `sampled` on the frame/token, and use **the same decision** at exit. If skipping an invocation while still needing to preserve the tree of selected children, a "nearest recorded ancestor" or virtual root parent convention must be documented.

With deep recursion, per-invocation sampling can drop some frames. If the goal is to reconstruct **an entire call tree**, you typically need consistent sampling at the trace/root level and a mechanism ensuring recorded segments have valid parents.

### 10.2. Avoiding Double Emission and Duplicate Retries

For each invocation, you can use `eventId = (processRunId, invocationId, phase)` so the backend can deduplicate the two `ENTER`/`EXIT` phases. An `invocationId` from an `AtomicLong` is only unique **within a recorder/process instance**; after a restart, IDs can repeat. Add `processRunId` or a trace namespace when persisting long-term or aggregating across multiple JVMs.

If an exporter retries after a timeout, the backend may receive two copies of an `EXIT`. Deduplicating by event ID keeps counts accurate, rather than adding every received event without checking for duplicates.

## 11. Counters and Performance Under High Call Rates

The demo uses `LongAdder` because it performs well when many threads update counters concurrently. However:

- `LongAdder.sum()` **is not an atomic snapshot** while concurrent updates are occurring; use it after quiescence or account for transient skew.
- `AtomicLong` is suitable for generating monotonic sequence IDs within a recorder and for values requiring atomic updates; it is not necessary to use `AtomicLong` for every metric.
- Do not push data for **every invocation** into an unbounded `ConcurrentLinkedQueue` like the demo does in production. Real systems need bounded buffers, drop policies, and exporters with backpressure.
- If you only need total calls per method, **direct counting** has lower overhead than storing every `ENTER`/`EXIT`. Only store frames/events at an appropriate sampling rate if you need flame graphs, trees, profiling, or durations.
- Metric labels should have bounded cardinality: normalized method name, outcome, service; do not add `invocationId` as a metric counter label because it creates a new time series for every call.
- A Java agent can instrument many classes, including its own logger/recorder. You should exclude these packages and guard hooks against reentrancy; otherwise, counting events will generate even more events.

### 11.1. Per-Method Counters and Per-Invocation Context Are Two Layers

A real system might use:

~~~text
methodKey -> LongAdder started/ended/success/failure (aggregated)
thread    -> Deque<Frame> (current synchronous execution context)
eventBus  -> ENTER/EXIT carrying invocationId/parentId (if tracing is needed)
~~~

Do not combine all three goals into a single map keyed only by method name. A per-method statistics map is **insufficient** to reconstruct individual calls; conversely, putting every invocation ID into metric labels causes cardinality to grow out of control.

## 12. Common Implementation Mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Only one `lastStartTime` per thread | Recursive child overwrites parent's timestamp | Per-frame on stack or local token per invocation |
| Pairing only by method name | Recursive frames with the same name are indistinguishable | Unique `invocationId` |
| Calling `end` in both `catch` **and** `finally` | One error produces two `EXIT` events | Single exit in `finally` |
| Inserting hooks at `return` opcodes while forgetting exceptions | Method throws without emitting `EXIT` | Cover both normal and exceptional exits |
| Crediting an error to the parent even when the parent caught it | Wrong outcome at the parent boundary | Determine whether the error escaped the method |
| Counting each recursive method only once per request | Wrong method invocation metric | Count every entry or design a separate logical request metric |
| Using guard `if (depth > 0) skip` | Drops valid nested/recursive invocations | Dedicated guard for self-instrumentation |
| Sharing a single `ArrayDeque` across multiple threads | Race conditions and wrong `parentId` | `ThreadLocal<Deque<Frame>>` or properly managed context |
| Forgetting `ThreadLocal.remove` when stack is empty | Context can linger across tasks in a thread pool | Clean up properly after the outermost exit |
| Emitting verbose logs inside hooks | Increases overhead, risks recorder reentrancy | Rate-limit and decouple the exporter from the hook |
| Calling `LongAdder.sum` while threads are updating and asserting equality | Measurements are not a point-in-time snapshot | Assert after quiescence or take a synchronized snapshot |
| Independent sampling on enter/exit | Orphan events | Store sampling decision on the frame |
| Treating `CompletableFuture` return as operation completion | Wrong duration/active count for async tasks | Separate method scope from logical async scope |
| Treating orphan events as always a code bug | Could be in-flight, slow exporter, or loss | Check TTL, task status, and dropped-event metrics |
| Swallowing instrumentation errors and reporting success | Masks lost data | Fail-open explicitly, report dropped/skipped events |

## 13. Testing Checklist for a Probe Design

Before deploying a Java agent/recorder to an application, verify at least:

- [ ] **Single normal call:** one `ENTER`, one `EXIT OK`, exact single increment of `started`/`ended`.
- [ ] **Multiple early returns:** every branch closes the frame once.
- [ ] **Method throws:** one `EXIT ERROR` and the business exception preserves its original type/stack/cause.
- [ ] **Child throws, parent catches:** child is `ERROR` while parent is `OK` if it returns normally.
- [ ] **Exception propagates across multiple levels:** each frame exiting via exception has `ERROR`; distinguish method failure from logical error.
- [ ] **Recursion:** each call has a different ID; depth increments on entry and decrements on exit; `parentId` is accurate.
- [ ] **Sibling calls:** two children share the same parent without being confused with each other.
- [ ] **Multiple threads:** stacks and parents do not mix; counters are accurate after tasks complete.
- [ ] **Thread pool reuse:** after the outermost exit, old context is cleared.
- [ ] **Async context:** trace/parent is propagated explicitly; there is a clear convention for when the operation ends.
- [ ] **Sampling/backpressure:** does not produce inconsistent event pairs the backend cannot explain; dropped counts are tracked.
- [ ] **Agent self-exclusion:** does not instrument its own logger, helper, exporter, or recorder.
- [ ] **Telemetry error path:** policy when recorder/exporter fails does not break business calls.
- [ ] **After quiescence:** reconcile `started = ended`, `ended = success + failure`, and `active = 0`.
- [ ] **Overhead:** benchmark CPU, allocation, GC, stack depth, and cardinality before/after enabling instrumentation.

With the sample program in Section 5, try changing `sumDown(2)` to `sumDown(3)`: you will get **one new `sumDown` invocation** with its parent/child IDs linked properly, rather than merely increasing depth while keeping the call count unchanged.

## 14. Self-Check Questions

1. Why does `sumDown(2)` in the example produce **three** `sumDown` calls instead of one?
2. If a child throws an exception and the parent catches it and returns normally, what is the `EXIT` outcome of each invocation?
3. Why is a single `lastStartTime` in a `ThreadLocal` insufficient for recursive methods?
4. When can the equalities `started=ended` and `success+failure=ended` be verified accurately?
5. Why can a `CompletableFuture` call have a method `EXIT` before the asynchronous task completes?
6. If a dispatcher runs on Thread B, what context must be carried from Thread A to determine `parentId`?
7. Why does independent random sampling at entry/exit produce invalid event pairs?
8. If the backend receives two copies of `EXIT` due to a retry, should it add both?
9. Why is excluding all `depth > 0` not a valid way to avoid self-instrumentation?
10. Does a missing `EXIT` event over a time window definitely mean the hook failed to run?

**Conclusion:** Accurately counting nested and recursive calls requires **one frame/ID per invocation**. Use `ThreadLocal<Deque<Frame>>` or a local token for synchronous calls; emit `ENTER` when actually starting and guarantee **a single `EXIT` from `finally`** based on the outcome at that exact call boundary. When scaling to multiple threads, async, sampling, or networks, you must actively propagate context, keep the sampling decision on the frame, and handle delayed/lost events. Only then will aggregated metrics and event trees remain consistent and meaningful.

### Official References

- [Java 17 — ThreadLocal, withInitial, and remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java 17 — LongAdder, sum is not an atomic snapshot](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Java 17 — AtomicLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [Java 17 — java.lang.instrument and transformer lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
