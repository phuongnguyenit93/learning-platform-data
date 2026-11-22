# Test Cases for Constructors, Conditional Branches, Multiple Returns, Exceptions, and Synchronized Methods

> **Objective:** Testing Java instrumentation must go beyond asking “was the transformer invoked?”. A properly instrumented bytecode version must preserve **business results, exceptions, object state, classfile verifiability, and synchronization semantics**, while emitting accurate signals for **every method entry and exit**. The trickiest paths are typically found in constructors (`<init>`), multiple `if`/`switch` branches, multiple `return` opcodes, caught/propagated exceptions, and methods carrying the `ACC_SYNCHRONIZED` flag.

This lesson belongs to the **Testing and Diagnostics** topic of Java Advance – Instrumentation. We will build a test-case matrix to catch bytecode weaving bugs, explain the pitfalls of the JVM verifier and Java monitors, and then run a **real Java 17+ test suite** with a startup Java agent. The example has three modes: baseline, an agent that only observes class loading, and an agent that replaces the classfile with an instrumented version; assertions verify both business semantics and probe counters.

## 1. Properly Defining “Instrumentation Works”

A program running with a Java agent is not guaranteed to be successfully instrumented: `ClassFileTransformer.transform()` may receive the callback and return `null`, the replacement bytes may be rejected by the JVM, or a method may have a hook that only executes on one branch and misses another exit path.

**The test suite must verify five dimensions of correctness:**

| Testing Dimension | Question to Answer | Example Assertion |
| --- | --- | --- |
| **Business behavior** | Are results/exceptions/state preserved as before? | Same input produces the same return/exception message |
| **Control-flow coverage** | Are all branches, returns, and exception paths executed? | `x<0`, `x==0`, `x>0`; early and final returns |
| **Probe semantics** | Do entry/exit and success/failure have exact counts and boundaries? | Each invocation has exactly one entry and one exit |
| **JVM verification & loading** | Does the classfile have valid format/stack maps/constructor state? | Running `java -Xverify:all ...` produces no `VerifyError` |
| **Concurrency & monitor** | Is the lock held at the right time, with no deadlock/race/changed sync semantics? | `Thread.holdsLock(this)` inside synchronized method, final state |

We must distinguish between **test coverage** and **probe coverage**. For example, if a method has three returns and the probe only counts three entries, that does not by itself prove that exits were recorded three times. Similarly, an exception caught and handled inside the method is **not a failure at the method boundary** if the method returns normally. Only an exception that escapes the method constitutes an **abrupt completion** at that boundary.

An ideal state model for a single invocation:

~~~text
method entry
   |
   v
business code
   |
   +-- normal return ----------------> exit(success) exactly once
   |
   +-- exception caught internally --> continue -> exit(success) exactly once
   |
   +-- exception escapes ------------> exit(failure) exactly once
~~~

Do not assume a hook can always record everything under every failure such as process kill, `Runtime.halt`, or an error occurring before the hook insertion point. If the instrumentation helper itself throws an exception, it can **alter** control flow; a failure policy must be designed and tested.

## 2. Minimum Test-Case Matrix Before Bytecode Injection

| ID | Code Type | Input / Scenario | Business Output to Preserve | Probe to Observe |
| --- | --- | --- | --- | --- |
| CTOR-1 | Successful constructor | `new BoundaryCases(5)` | Object created, seed = 5 | Constructor 1 entry, 1 success exit |
| CTOR-2 | Constructor throws after `super()` | `new BoundaryCases(-1)` | `IllegalArgumentException("negative seed")`, no usable object | 1 entry, 1 failure exit |
| BR-1 | Negative branch | `branch(-1)` | `"NEG"` | Method 1 success exit |
| BR-2 | Zero branch | `branch(0)` | `"ZERO"` | Method 1 success exit |
| BR-3 | Positive branch | `branch(1)` | `"POS"` | Method 1 success exit |
| RET-1 | First early return | `multiple(-1)` | `-1` | 1 exit |
| RET-2 | Second early return | `multiple(0)` | `0` | 1 exit |
| RET-3 | Final return | `multiple(2)` with seed 5 | `7` | 1 exit |
| EX-1 | Normal computation | `divideOrFallback(2)` | `10` | Success exit |
| EX-2 | Internally caught exception | `divideOrFallback(0)` | `-20` | **Success**, not failure |
| EX-3 | Escaping exception | `failOrReturn(13)` | `IllegalStateException("unlucky")` | Failure exit, preserving type/message |
| EX-4 | Throwing-capable method running normally | `failOrReturn(2)` | `7` | Success exit |
| SYNC-1 | Normal synchronized | `increment(3)`, `increment(-1)` | State increments/decrements properly | Probe sees monitor held |
| SYNC-2 | Synchronized throws exception | `increment(Integer.MIN_VALUE)` | `IllegalArgumentException("bad delta")`, state unchanged | Failure exit **inside monitor** |
| SYNC-3 | Concurrent callers | 4 threads × 200 increments | Total has no lost updates | 800 success exits, no deadlock |
| SYNC-4 | Monitor release after exception | Call `increment` again after exception | Subsequent call succeeds | Monitor not held outside invocation |

In the final test suite, there is also one `increment(0)` call to read the state through the synchronized method itself. Therefore, the total for the sync method is **804 entries = 803 successes + 1 failure**, not just 803. Every count in the table and stdout must be traceable to specific calls; never “round” numbers for convenience.

### Invariants That Should Always Hold

1. **Do not alter output or exception contracts** when adding instrumentation.
2. **Do not drop or double-count** a method-level event when there are multiple branches/returns.
3. `entries == successes + failures` after all invocations complete, provided the probe itself operates normally and instrumentation is placed at valid entry/exit points.
4. **Internal catch** is not automatically classified as a method failure.
5. **The monitor** of a synchronized method is held by the JVM throughout the method body; whether returning or throwing, once the method invocation exits, the monitor is released.
6. The probe must not remove the `synchronized` modifier, alter descriptors, add business side effects, or cause the Java verifier to reject the class.

Do not turn invariants into assumptions that **hold for every possible hook**: they are **the contract we want to implement and test**. Instrumentation designed to record every throw event may have different semantics from instrumentation that only distinguishes **method-level success/failure**.

## 3. Constructors: Hook Placement and `uninitializedThis`

### 3.1. Why `<init>` Differs from Regular Methods

A constructor has the JVM name `<init>` and return type `void`, but it executes while the object is being initialized. Before completing the superclass initialization call or delegated constructor, the verifier may treat local variable 0 as **`uninitializedThis`**. You must not arbitrarily use `this` as a fully constructed instance at that point.

With Java 17 source:

~~~java
public BoundaryCases(int seed) {
    if (seed < 0) throw new IllegalArgumentException("negative seed");
    this.seed = seed;
}
~~~

The compiler generates the `Object.<init>()` call **before regular statements** in this constructor (because Java 17 requires constructor chaining at the appropriate position). In the instrumented version of this lesson, we insert `ProbeRecorder.enter(...)` **after the `invokespecial` call that initializes the superclass**.

Conceptual diagram:

~~~text
new BoundaryCases(seed)
    |
    v
<init> entry: this is not yet fully initialized
    |
    v
aload_0 / invokespecial java/lang/Object.<init>
    |
    v
safer to use this; probe.enter("ctor")
    |
    +-- seed < 0 -> throw IllegalArgumentException -> probe.exit(failure)
    |
    +-- seed >= 0 -> assign seed -> probe.exit(success)
~~~

**Verifier pitfall:** if a bytecode weaver “pushes” `ALOAD 0`, invokes a virtual method on `this`, or passes `uninitializedThis` to a helper before a valid constructor chain completes, the JVM may throw `VerifyError`. Wrapping the superclass `<init>` call in an exception handler is also tricky because the verifier's uninitialized state must be preserved.

**Coverage limitation to state honestly:** Because the probe is placed **after** the superclass constructor, if the superclass constructor throws an exception **before** the probe point, that is **not** a failure this probe can observe. Do not report “100% of `new` calls have an entry” when the advice placement does not allow it. If you need to measure the full initialization lifecycle, you must choose a different boundary or design instrumentation compatible with verifier/constructor chaining.

### 3.2. Constructor Chaining `this(...)` and Other Traps

If a class has:

~~~java
public Order() {
    this(0);
}

public Order(int amount) {
    this.amount = amount;
}
~~~

This is an **illustrative code snippet** inside a class with an `amount` field. A single `new Order()` call can execute **two `<init>` methods** along the delegation chain. If you instrument every constructor and count them as “one event per object”, you will get **two records for one object**. You must distinguish:

- **Constructor invocation**: each actual `<init>` invoked.
- **Object construction attempt**: an external attempt to create an object (which may pass through multiple `<init>`s).
- **Object successfully initialized**: the process succeeded and the object is valid.

Do not manually insert helper calls before `super()`/`this()` or add a catch handler covering the entire constructor chain without understanding `StackMapTable`/verifier semantics. With libraries like ASM/Byte Buddy, use APIs/hooks that provide explicit guarantees for constructor advice on the target library/JDK version rather than copying a regular method-exit transformer into `<init>`.

**Mandatory tests:** successful constructor, exception thrown **after** chaining, constructor delegation, a class whose superclass constructor throws an exception, and class verification with `-Xverify:all`. If a case cannot be observed due to hook placement, report the limitation clearly instead of silently ignoring it.

## 4. Conditional Branches: Method Count Is Not Branch Coverage

### 4.1. Three `if` Paths in the Example

~~~java
public String branch(int x) {
    if (x < 0) return "NEG";
    if (x == 0) return "ZERO";
    return "POS";
}
~~~

If a test only uses `x=-1`, it may get `"NEG"` and one probe success, but there is no evidence that the other two branches still work. We need at least:

~~~text
branch(-1) -> NEG
branch( 0) -> ZERO
branch( 1) -> POS
~~~

This is an **expected-value table**, not the output of a separate program.

Instrumentation can insert hooks at entry/exit or **before each branch/edge**. These are two different kinds of coverage:

| Measurement Type | What It Can Confirm | What It Cannot Confirm by Itself |
| --- | --- | --- |
| Method entry count | How many invocations reached the method | Whether each conditional branch was taken? |
| Method success/failure exit | Whether the method returned or threw | Which `if`/`else` branch was chosen? |
| Branch/edge coverage | Whether true/false edges executed | Whether output/business logic is right after transformation? |
| Line coverage | Which mapped source lines ran | Whether all branches on that line were tested? |

For `switch`, `tableswitch`/`lookupswitch`, and exception edges, add tests for **every case and default**, including null/default policies where appropriate. Bytecode optimizers/compilers may emit jump targets different from what the source suggests. The test suite should compare original and instrumented outputs, and if the goal is branch coverage, use a dedicated branch-coverage tool or counter rather than inferring from method entries.

### 4.2. Avoid Changing Evaluation Order

If the original condition is:

~~~java
if (a != null && a.isReady()) {
    process(a);
}
~~~

then `a.isReady()` must **not** be called when `a == null`, due to short-circuit evaluation. Instrumentation that rewrites the condition and calls a helper/`isReady()` unconditionally will alter behavior (even introducing a new `NullPointerException`). For `&&`, `||`, ternary, pattern matching, and `switch` expressions, preserve evaluation order, call counts, and exception types.

**A probe may observe the outcome of a condition** without modifying the outcome; however, logging with side effects or locks will still alter timing. Never evaluate an expression a second time for the sake of coverage.

## 5. Multiple Returns: Exit Hooks Must Cover All Exit Paths

### 5.1. `ireturn`, `areturn`, `return`, and Other Return Opcodes

A Java method can contain multiple `return` statements across branches:

~~~java
public int multiple(int x) {
    if (x < 0) return -1;
    if (x == 0) return 0;
    return x + seed;
}
~~~

At the bytecode level, the JVM has multiple return opcodes: `ireturn` for `int`/int-compatible types, `lreturn`, `freturn`, `dreturn`, `areturn` for references, and `return` for `void`. If a transformer only attaches advice before the last `return` in source or only handles one opcode, it will miss the other exit paths.

A semantically clear strategy is wrapping the body in `try/finally`:

~~~java
public int multiple(int x) {
    ProbeRecorder.enter("multiple", false);
    boolean ok = false;
    try {
        if (x < 0) { ok = true; return -1; }
        if (x == 0) { ok = true; return 0; }
        ok = true;
        return x + seed;
    } finally {
        ProbeRecorder.exit("multiple", ok, false);
    }
}
~~~

This is **a concrete instrumented method**, requiring a class with `seed` and `ProbeRecorder`; the full program is in Section 8. The `finally` block runs for **all three normal returns** with `ok=true`, and records a failure if an exception escapes before `ok=true` is set.

**However, simply looking for the `finally` keyword is not enough:** A bytecode weaver must emit valid exception tables, jump targets, max locals/max stack, and `StackMapTable` frames. Compilers may duplicate finally bytecode at exit sites or generate handlers; the **method invocation** counter must still be incremented exactly once, never multiplied because there are three return instructions.

### 5.2. Preserving Return Values and Exceptions

Advice around `areturn` must preserve reference/object identity, `ireturn` must preserve `int`, and `lreturn`/`dreturn` must preserve two-slot values. If instrumentation code drops a value on the operand stack, changes its type, or causes the verifier to merge frames incorrectly, you may hit `VerifyError` or corrupt business results.

`finally` can **overwrite a return value or exception** if the `ProbeRecorder.exit` callback itself throws an exception. Production systems need a clear hook failure policy—such as only handling expected errors from exporters/serialization—so telemetry never breaks business logic. Do not use blanket `catch(Throwable)` to swallow critical JVM errors without a safe policy.

**Important cases:** Test returning `null` objects, non-null objects, primitive values, `void` methods, and methods with early exits from loops if the transformer is broadly applied. The code below only tests `String` and `int`; extend it according to the actual signatures of your target classes.

## 6. Exceptions: Distinguishing Caught, Propagated, and Hook Failures

### 6.1. An Exception Caught Inside the Method

~~~java
public int divideOrFallback(int denominator) {
    try {
        return 20 / denominator;
    } catch (ArithmeticException expected) {
        return -20;
    }
}
~~~

With `denominator=0`, the JVM throws `ArithmeticException` at the division, but the method **catches it** and returns `-20`. Method-level instrumentation should record **success** on exit because the caller receives no exception. If the goal is to count internal exception occurrences, a different event type is needed, recorded inside the catch block or via an appropriate observation mechanism.

**Do not confuse throw-events with failure-events:**

- **Thrown exception event:** an exception created/thrown at a point in bytecode; it may subsequently be caught.
- **Method failure at boundary:** the method terminates abruptly and the exception escapes to the caller.
- **Business failure:** a method may return `Result.error` normally without throwing; this must be defined by the domain, rather than treating every normal return as business success.

### 6.2. An Exception Escaping the Method

~~~java
public int failOrReturn(int x) {
    if (x == 13) throw new IllegalStateException("unlucky");
    return x + seed;
}
~~~

Tests must verify the **exact exception type and message**, not just “an exception occurred”. Instrumentation must not unintentionally alter the exception's type, message, suppressed exceptions, or cause.

Instrumenting only `ATHROW` instructions inside a method is **not sufficient to catch all escaping exceptions**: an invocation or arithmetic operation can throw implicitly, and an exception can propagate without an explicit `ATHROW` in the method. Achieving **on-exit on throwable** requires creating an exception handler covering the proper logic region, with valid frames/handler structure, without accidentally catching it and turning it into a success.

### 6.3. `try/finally` and the Failure Flag in the Demo

~~~java
public int failOrReturn(int x) {
    ProbeRecorder.enter("throwing", false);
    boolean ok = false;
    try {
        if (x == 13) throw new IllegalStateException("unlucky");
        ok = true;
        return x + seed;
    } finally {
        ProbeRecorder.exit("throwing", ok, false);
    }
}
~~~

Here `finally` runs whether the method returns or throws, but the method does not catch `IllegalStateException`, so the caller still receives it. If the `exit` hook itself throws, it **can mask** the original exception; this is an instrumentation bug commonly missed in unit tests that only check the happy path.

**Additional tests:** errors from an internally called method, `RuntimeException`, checked exceptions, `Error` per policy, nested try/catch/finally, exception filters, suppressed exceptions in try-with-resources, and throws from constructors/helpers. Never promise that exception exits are recorded for every JVM termination/fatal failure scenario; the bytecode specification and advice scope determine what is observable.

## 7. `synchronized` Methods: Monitors and Exception Paths

### 7.1. `synchronized` Methods vs. `synchronized(this)` Blocks

For an instance synchronized method:

~~~java
public synchronized int increment(int delta) {
    total += delta;
    return total;
}
~~~

The compiler sets **`ACC_SYNCHRONIZED`** in `method_info` flags. According to JVMS 17, the JVM automatically **enters the monitor** when the method is invoked and automatically **exits the monitor** when the method returns normally or abruptly. The method's bytecode **does not necessarily contain `monitorenter`/`monitorexit`** like a `synchronized(obj) { ... }` block.

| Construct | Monitor Object | How the JVM Holds the Lock |
| --- | --- | --- |
| `public synchronized void instanceMethod()` | `this` | Implicit lock via `ACC_SYNCHRONIZED` |
| `public static synchronized void classMethod()` | `DeclaringClass.class` | Implicit lock via `ACC_SYNCHRONIZED` |
| `synchronized(lock) { ... }` | Object `lock` | `monitorenter`/`monitorexit` in bytecode |

**Do not** manually insert `monitorenter`/`monitorexit` into a method that already has `ACC_SYNCHRONIZED`: failing to maintain proper balance/structured locking can cause deadlocks or `IllegalMonitorStateException`.

### 7.2. Does the Probe Run Inside the Monitor?

Because the JVM acquires the lock before entering the body of a synchronized method, if the probe is inserted at the **start of the body**, `Thread.holdsLock(this)` must be `true` for an instance synchronized method. When the method exits (including via exception), the JVM releases the implicit monitor.

The lesson's variant code:

~~~java
public synchronized int increment(int delta) {
    ProbeRecorder.enter("sync", Thread.holdsLock(this));
    boolean ok = false;
    try {
        if (delta == Integer.MIN_VALUE) throw new IllegalArgumentException("bad delta");
        total += delta;
        ok = true;
        return total;
    } finally {
        ProbeRecorder.exit("sync", ok, Thread.holdsLock(this));
    }
}
~~~

Both entry and exit probes run **while the lock is still held**. Consequently, a blocking or locking recorder can **extend the critical section**, impacting contention and p99 latency even when the business body is very fast. The test's `sync_monitor_violations=0` output asserts that the monitor was held at both callback locations.

For static synchronized methods, do not use `Thread.holdsLock(this)` because there is no `this`; check the monitor of the appropriate `Class<?>` object if needed. For `synchronized(lock)` blocks, only advice placed **inside the block** is guaranteed to run while the `lock` monitor is held.

### 7.3. Correctness Under Multiple Threads

Test 4 threads × 200 `increment(1)` calls on the **same** instance. If no new race condition is introduced and the method remains synchronized, the state will increase by exactly 800. The test suite also performs:
1. `increment(3)` → total 3.
2. `increment(Integer.MIN_VALUE)` → throws; total remains 3.
3. `increment(-1)` → total 2.
4. 800 increments from 4 threads → total 802.
5. `increment(0)` → reads back total **802**.

Do not use `Thread.sleep` to guess concurrency ordering; `Future.get()` confirms worker tasks have finished and propagates worker errors to main, while `awaitTermination` ensures the executor is shut down within the scope of the example.

**Note:** A single passing test run **does not prove the absence of all races/deadlocks** under every schedule. For higher confidence, run repeatedly, stress across multiple JVMs/CPUs, add timeouts, and for complex locking consider concurrency testing tools. The probe must also be thread-safe; `LongAdder` helps with concurrent counting, but `sum()` while threads are actively updating is **not a strictly atomic snapshot**.

## 8. Complete Runnable Java 17+ Example: Baseline, Observe, and Inject

To focus on test semantics without depending on ASM/Byte Buddy libraries, we **precompile two versions with the same binary name `BoundaryCases`**:
- The original version at the root classpath, which does **not** call the probe.
- The variant version in `variant/`, which has `ProbeRecorder` calls placed in methods/constructors via Java source.
- A startup agent uses `ClassFileTransformer` to return the **variant classfile bytes** as soon as the JVM defines `BoundaryCases` in `inject` mode.

This is **real class-load-time instrumentation**, not a simulation via calling a subclass directly. However, **creating advice via a source variant** is only for pedagogical purposes; production tools typically need to patch incoming bytes per classloader/module, match method descriptors, and handle verifier/StackMapTable updates. Never return a single precompiled `.class` file for every class of the same name across different loaders.

### 8.1. `BoundaryCases.java` — Original Version

~~~java
public final class BoundaryCases {
    private final int seed;
    private int total;

    public BoundaryCases(int seed) {
        if (seed < 0) throw new IllegalArgumentException("negative seed");
        this.seed = seed;
    }

    public String branch(int x) {
        if (x < 0) return "NEG";
        if (x == 0) return "ZERO";
        return "POS";
    }

    public int multiple(int x) {
        if (x < 0) return -1;
        if (x == 0) return 0;
        return x + seed;
    }

    public int divideOrFallback(int denominator) {
        try { return 20 / denominator; }
        catch (ArithmeticException expected) { return -20; }
    }

    public int failOrReturn(int x) {
        if (x == 13) throw new IllegalStateException("unlucky");
        return x + seed;
    }

    public synchronized int increment(int delta) {
        if (delta == Integer.MIN_VALUE) throw new IllegalArgumentException("bad delta");
        total += delta;
        return total;
    }
}
~~~

There is no `main` method in this file; the program is tested by `CaseSuite`. The original constructor assigns `final int seed` on the success branch; on the negative branch it throws an exception.

### 8.2. `ProbeRecorder.java` — Thread-Safe Counters

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public final class ProbeRecorder {
    private static final ConcurrentHashMap<String, LongAdder> ENTER = new ConcurrentHashMap<>();
    private static final ConcurrentHashMap<String, LongAdder> OK = new ConcurrentHashMap<>();
    private static final ConcurrentHashMap<String, LongAdder> FAIL = new ConcurrentHashMap<>();
    private static final LongAdder BAD_MONITOR_OBSERVATIONS = new LongAdder();

    private ProbeRecorder() {}

    private static void add(ConcurrentHashMap<String, LongAdder> counters, String name) {
        counters.computeIfAbsent(name, ignored -> new LongAdder()).increment();
    }

    public static void enter(String name, boolean monitorHeld) {
        if ("sync".equals(name) && !monitorHeld) BAD_MONITOR_OBSERVATIONS.increment();
        add(ENTER, name);
    }

    public static void exit(String name, boolean succeeded, boolean monitorHeld) {
        if ("sync".equals(name) && !monitorHeld) BAD_MONITOR_OBSERVATIONS.increment();
        add(succeeded ? OK : FAIL, name);
    }

    private static long read(ConcurrentHashMap<String, LongAdder> map, String name) {
        LongAdder counter = map.get(name);
        return counter == null ? 0 : counter.sum();
    }

    public static long entered(String name) { return read(ENTER, name); }
    public static long succeeded(String name) { return read(OK, name); }
    public static long failed(String name) { return read(FAIL, name); }
    public static long invalidMonitorCount() { return BAD_MONITOR_OBSERVATIONS.sum(); }
}
~~~

These counters are **intentionally simple**: they only use a fixed set of method names, avoiding unbounded metric label cardinality. `ConcurrentHashMap` + `LongAdder` allow multiple threads to update concurrently. The `sum()` check runs **after** `Future.get()` and executor shutdown, because reading during concurrent updates only gives an approximate snapshot.

This recorder still incurs overhead from map lookups and counter updates; in synchronized methods, recorder operations run **inside the critical section**. Since the primary goal is correctness, do not infer production latency from this test suite's results.

### 8.3. `variant/BoundaryCases.java` — Probed Version

~~~java
public final class BoundaryCases {
    private final int seed;
    private int total;

    public BoundaryCases(int seed) {
        ProbeRecorder.enter("ctor", false);
        boolean ok = false;
        try {
            if (seed < 0) throw new IllegalArgumentException("negative seed");
            this.seed = seed;
            ok = true;
        } finally {
            ProbeRecorder.exit("ctor", ok, false);
        }
    }

    public String branch(int x) {
        ProbeRecorder.enter("branch", false);
        boolean ok = false;
        try {
            if (x < 0) { ok = true; return "NEG"; }
            if (x == 0) { ok = true; return "ZERO"; }
            ok = true;
            return "POS";
        } finally {
            ProbeRecorder.exit("branch", ok, false);
        }
    }

    public int multiple(int x) {
        ProbeRecorder.enter("multiple", false);
        boolean ok = false;
        try {
            if (x < 0) { ok = true; return -1; }
            if (x == 0) { ok = true; return 0; }
            ok = true;
            return x + seed;
        } finally {
            ProbeRecorder.exit("multiple", ok, false);
        }
    }

    public int divideOrFallback(int denominator) {
        ProbeRecorder.enter("caught", false);
        boolean ok = false;
        try {
            int result;
            try { result = 20 / denominator; }
            catch (ArithmeticException expected) { result = -20; }
            ok = true;
            return result;
        } finally {
            ProbeRecorder.exit("caught", ok, false);
        }
    }

    public int failOrReturn(int x) {
        ProbeRecorder.enter("throwing", false);
        boolean ok = false;
        try {
            if (x == 13) throw new IllegalStateException("unlucky");
            ok = true;
            return x + seed;
        } finally {
            ProbeRecorder.exit("throwing", ok, false);
        }
    }

    public synchronized int increment(int delta) {
        ProbeRecorder.enter("sync", Thread.holdsLock(this));
        boolean ok = false;
        try {
            if (delta == Integer.MIN_VALUE) throw new IllegalArgumentException("bad delta");
            total += delta;
            ok = true;
            return total;
        } finally {
            ProbeRecorder.exit("sync", ok, Thread.holdsLock(this));
        }
    }
}
~~~

Note: This is **the complete variant file**, but it must not be compiled at the same time as the root `BoundaryCases.java` into the same output directory. Both files declare `public class BoundaryCases`; the compiler will report a duplicate class if placed in the same source set. The build command in Section 8.7 uses a separate `-d variant` directory.

A constructor compiled from this file has the `Object.<init>` call **before** `ProbeRecorder.enter`, because the Java 17 compiler generates the implicit superclass constructor call. This preserves classfile verifiability. The same **does not happen automatically** if a hand-written bytecode weaver moves instructions around.

### 8.4. `ScopedTransformer.java` — Filtering the Target Class at Initial Definition

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ScopedTransformer implements ClassFileTransformer {
    private final byte[] bytes;

    public ScopedTransformer(byte[] bytes) { this.bytes = bytes == null ? null : bytes.clone(); }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String internalName,
            Class<?> redefining, ProtectionDomain protectionDomain, byte[] original) {
        if (!"BoundaryCases".equals(internalName)) return null;
        System.out.println("transform=BoundaryCases");
        return bytes == null ? null : bytes.clone();
    }
}
~~~

`internalName` is the JVM internal class name. Because `BoundaryCases` is in the default package, its name is simply `"BoundaryCases"`; for a class in package `org.demo`, the name uses slashes: `"org/demo/BoundaryCases"`.

- **observe** mode: the transformer receives the callback and returns `null`, so the JVM keeps the original class.
- **inject** mode: the transformer returns the precompiled variant classfile; the JVM uses the methods with probes.
- The transformer only runs on **first load**; `canRetransform=true` is not needed.
- This example does not address multiple loaders defining the same binary name; production code must filter by defining loader/module, preserve method descriptors, and respect classfile constraints.

Do not mutate the `original` byte array directly; the `ClassFileTransformer` Javadoc requires returning a new valid byte array or `null`. Do not load helpers from the callback in a way that triggers class-loading recursion.

### 8.5. `CaseAgent.java` — Startup Agent

~~~java
import java.io.IOException;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CaseAgent {
    public static void premain(String args, Instrumentation instrumentation) throws IOException {
        String mode = args == null ? "observe" : args;
        if (!"observe".equals(mode) && !"inject".equals(mode)) {
            throw new IllegalArgumentException("Expected observe or inject");
        }
        byte[] changed = "inject".equals(mode)
                ? Files.readAllBytes(Path.of("variant/BoundaryCases.class")) : null;
        instrumentation.addTransformer(new ScopedTransformer(changed));
        if ("inject".equals(mode)) System.setProperty("cases.instrumented", "true");
        System.out.println("agent-mode=" + mode);
    }
}
~~~

The agent reads the bytes **before** registering the transformer, avoiding I/O inside `transform`. The `cases.instrumented=true` property is **only a signal for the test suite's assertions**, not a production mechanism for verifying instrumentation. The test suite still verifies using counters and actual behavior.

If `variant/BoundaryCases.class` does not exist or the working directory is wrong, `Files.readAllBytes` will fail and the agent will not start properly. An agent startup failure in `premain` can prevent the JVM from reaching `main`; that is a setup failure and must not be reported as “tests passed”.

### 8.6. `CaseSuite.java` — Test Assertions, Exceptions, and Concurrency

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class CaseSuite {
    private static void eq(Object expected, Object actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError("expected=" + expected + " actual=" + actual);
        }
    }

    private static void count(String name, long entries, long ok, long fail) {
        eq(entries, ProbeRecorder.entered(name));
        eq(ok, ProbeRecorder.succeeded(name));
        eq(fail, ProbeRecorder.failed(name));
        System.out.println(name + "=" + entries + "/" + ok + "/" + fail);
    }

    public static void main(String[] args) throws Exception {
        try {
            new BoundaryCases(-1);
            throw new AssertionError("constructor should throw");
        } catch (IllegalArgumentException expected) {
            eq("negative seed", expected.getMessage());
        }
        BoundaryCases subject = new BoundaryCases(5);

        eq("NEG", subject.branch(-1));
        eq("ZERO", subject.branch(0));
        eq("POS", subject.branch(1));

        eq(-1, subject.multiple(-1));
        eq(0, subject.multiple(0));
        eq(7, subject.multiple(2));

        eq(10, subject.divideOrFallback(2));
        eq(-20, subject.divideOrFallback(0));

        eq(7, subject.failOrReturn(2));
        try {
            subject.failOrReturn(13);
            throw new AssertionError("method should throw");
        } catch (IllegalStateException expected) {
            eq("unlucky", expected.getMessage());
        }

        eq(3, subject.increment(3));
        try {
            subject.increment(Integer.MIN_VALUE);
            throw new AssertionError("synchronized method should throw");
        } catch (IllegalArgumentException expected) {
            eq("bad delta", expected.getMessage());
        }
        eq(false, Thread.holdsLock(subject));
        eq(2, subject.increment(-1));

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> work = new ArrayList<>();
            for (int thread = 0; thread < 4; thread++) {
                work.add(pool.submit(() -> {
                    for (int i = 0; i < 200; i++) subject.increment(1);
                }));
            }
            for (Future<?> task : work) task.get();
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new AssertionError("worker timeout");
            }
        }
        eq(802, subject.increment(0));

        boolean injected = Boolean.getBoolean("cases.instrumented");
        System.out.println("instrumented=" + injected);
        long factor = injected ? 1 : 0;
        count("ctor", 2 * factor, factor, factor);
        count("branch", 3 * factor, 3 * factor, 0);
        count("multiple", 3 * factor, 3 * factor, 0);
        count("caught", 2 * factor, 2 * factor, 0);
        count("throwing", 2 * factor, factor, factor);
        count("sync", 804 * factor, 803 * factor, factor);
        eq(0L, ProbeRecorder.invalidMonitorCount());
        System.out.println("sync_monitor_violations=0");
        System.out.println("final_total=802");
        System.out.println("ASSERTIONS_PASSED");
    }
}
~~~

The test suite uses `AssertionError` directly instead of requiring JUnit, so it can run with just the JDK. In production, you can convert it to **JUnit 5 tests** and add coverage/bytecode scanning, but this example requires no external libraries.

Details to note:

- `Future.get()` propagates worker exceptions back to main; if a thread corrupts state or throws, the test cannot silently pass.
- `ExecutorService.shutdown()` and `awaitTermination(...)` close the executor; the 5-second value is a timeout **for the demo** and can be adjusted for CI environments.
- `Thread.holdsLock(subject)` checks whether **the calling thread** owns the monitor. After the exception, main must no longer hold `subject`'s monitor.
- `eq(802, subject.increment(0))` adds **one** normal synchronized call. The sync counter therefore has **803 success exits**.
- `factor` only adjusts expected counts in baseline/observe; **business assertions are identical** across all three modes.

### 8.7. `agent.mf` File and Run Commands

Manifest:

~~~text
Manifest-Version: 1.0
Premain-Class: CaseAgent
~~~

Save the manifest with a trailing newline. File structure:

~~~text
demo/
  BoundaryCases.java
  ProbeRecorder.java
  ScopedTransformer.java
  CaseAgent.java
  CaseSuite.java
  agent.mf
  variant/
    BoundaryCases.java
~~~

From the `demo` directory, using **JDK 17+**:

~~~bash
javac --release 17 BoundaryCases.java ProbeRecorder.java ScopedTransformer.java CaseAgent.java CaseSuite.java

javac --release 17 -classpath . -d variant variant/BoundaryCases.java

jar --create --file case-agent.jar --manifest agent.mf CaseAgent.class ScopedTransformer.class

java CaseSuite

java -javaagent:case-agent.jar=observe CaseSuite

java -javaagent:case-agent.jar=inject CaseSuite
~~~

`-classpath .` in the variant compilation step lets the compiler see `ProbeRecorder` from root. `-d variant` places the **variant classfile** in the exact directory the agent reads at runtime. Do not copy `variant/BoundaryCases.class` over the root class before running; doing so means you are no longer testing byte replacement via the transformer.

### 8.8. Verified Execution Results

All code was compiled with `javac --release 17` and actually run on OpenJDK 24. The snippets below are stdout from **three separate JVM runs**.

**Baseline:**

~~~text
instrumented=false
ctor=0/0/0
branch=0/0/0
multiple=0/0/0
caught=0/0/0
throwing=0/0/0
sync=0/0/0
sync_monitor_violations=0
final_total=802
ASSERTIONS_PASSED
~~~

**Observe-only:**

~~~text
agent-mode=observe
transform=BoundaryCases
instrumented=false
ctor=0/0/0
branch=0/0/0
multiple=0/0/0
caught=0/0/0
throwing=0/0/0
sync=0/0/0
sync_monitor_violations=0
final_total=802
ASSERTIONS_PASSED
~~~

**Inject:**

~~~text
agent-mode=inject
transform=BoundaryCases
instrumented=true
ctor=2/1/1
branch=3/3/0
multiple=3/3/0
caught=2/2/0
throwing=2/1/1
sync=804/803/1
sync_monitor_violations=0
final_total=802
ASSERTIONS_PASSED
~~~

`name=entered/succeeded/failed`. Specifically:

| Kind | Entries | Successes | Failures | Meaning |
| --- | ---: | ---: | ---: | --- |
| `ctor` | 2 | 1 | 1 | One constructor threw, one succeeded |
| `branch` | 3 | 3 | 0 | Negative, zero, and positive |
| `multiple` | 3 | 3 | 0 | Three normal return paths |
| `caught` | 2 | 2 | 0 | Divide by zero **was caught**, so still success |
| `throwing` | 2 | 1 | 1 | One return and one uncaught `IllegalStateException` |
| `sync` | 804 | 803 | 1 | Main calls + 800 concurrent calls + final state read |

In all three modes, `final_total=802` and all behavior assertions passed. This is evidence that **the demo did not alter logic**, within the scope of the cases run. It does not prove a production weaver can transform every class, every JVM version, or every constructor pattern.

## 9. Inspecting the Classfile and JVM Verifier, Not Just Stdout

A transformation may expose bugs when the class is verified or when a rarely used branch is hit; additional checks on **artifact bytes** must be run.

### 9.1. `javap` for Constructors

~~~bash
javap -c -p -classpath variant BoundaryCases
~~~

In the tested variant, the constructor has `invokespecial java/lang/Object."<init>"` at the beginning of the body, followed by `ProbeRecorder.enter`. This proves **the compiler placed the hook after superclass initialization** in the Java source fixture. You must not infer that an arbitrary bytecode weaver will arrange this safely on its own.

When reading the output, distinguish:
- `invokespecial ... <init>`: superclass/constructor chain initialization path.
- `StackMapTable`: verifier state at branch/handler frames.
- `Exception table`: try/catch/finally regions; adding an incorrect handler can catch the wrong exception or produce invalid frames.
- `max_stack`/`max_locals`: instrumentation adds the local `ok` and may increase operand stack depth.
- `LineNumberTable`/source mapping: preserve useful metadata so stack traces remain helpful; not every transformer is required to preserve all debug attributes.

### 9.2. `ACC_SYNCHRONIZED` and Bytecode

~~~bash
javap -v -p -classpath . BoundaryCases
javap -v -p -classpath variant BoundaryCases
~~~

Verify that `increment(int)` still carries `ACC_SYNCHRONIZED` in **both versions**. For synchronized methods, the JVM handles the monitor implicitly; do not expect to see `monitorenter`/`monitorexit` pairs in the body just because the method has the `synchronized` keyword.

### 9.3. Forcing the Verifier to Check All Loaded Classes

~~~bash
java -Xverify:all CaseSuite
java -Xverify:all -javaagent:case-agent.jar=observe CaseSuite
java -Xverify:all -javaagent:case-agent.jar=inject CaseSuite
~~~

`-Xverify:all` expands the scope of bytecode verification; run it as a separate CI test pass, not for measuring production throughput. If `VerifyError`, `ClassFormatError`, `NoClassDefFoundError`, `IllegalAccessError`, or class loader linkage issues occur, stop and inspect the classfile/StackMapTable/helper visibility instead of removing flags to hide the error.

**Differences between failure types:**

| Symptom | Likely Cause |
| --- | --- |
| `VerifyError` | Invalid operand-stack/local types, constructor `uninitializedThis`, stack map frames, handler targets |
| `ClassFormatError` | Malformed classfile bytes/constant pool/attributes/Code structure |
| `NoClassDefFoundError` | Helper not visible from defining loader or wrong target class binary name |
| `IllegalAccessError` | Helper field/method inaccessible due to package/module/protection |
| `UnsupportedClassVersionError` | Classfile version exceeds running JVM |
| `ExceptionInInitializerError` | Helper/probe class initialization failed |
| Wrong business test result even though class loaded | Rewrite altered return/branch/throw semantics |
| Monitor contention/deadlock | Probe performs I/O, locking, or inserts wrong monitor operations |
| Counter `entries != exits` | Missed normal/exception exit, or probe itself failed/double-counted |

Do not mistakenly assume that `ClassFileTransformer` callback invocation means the classfile was definitely installed: if invalid bytes are returned, the JVM can reject class loading. If the callback throws an uncaught exception, the Javadoc notes that the JVM may still proceed to subsequent transformers and class definition; you must have logging and behavior assertions instead of just watching the callback.

## 10. Automating Tests for a Weaver Using ASM or Byte Buddy

The demo uses a precompiled variant, but when developing a real weaver, you must test **an actual bytecode pipeline**:

~~~text
Original class bytes
    |
    v
Transformer: select class/method by name + loader + descriptor
    |
    v
Inject entry/exit advice, rewrite branches/handlers
    |
    v
Recompute/maintain max_stack, max_locals, StackMapTable
    |
    v
ClassLoader.defineClass / JVM verify
    |
    v
Run behavior assertions + probe assertions
    |
    v
Concurrency & error-path stress
~~~

### 10.1. Exact Signatures and Filtering Conditions

For overloads, do not select by name `process` alone: check the descriptor, e.g., `process(I)I` differs from `process(Ljava/lang/String;)Ljava/lang/String;`. Constructors are named `<init>` and static initializers `<clinit>`; `native` and `abstract` methods have no Code attribute for injecting normal method-body advice. Bridge/synthetic methods may also exist, requiring a test policy to avoid accidentally double-instrumenting a single logical call.

**Transformer contract:** `transform(...)` receives the input bytes of the transformer chain and returns a valid classfile in a new `byte[]`, or `null` if skipped. Do not mutate `classfileBuffer` in-place. When retransforming/redefining already-loaded classes, you must also respect the structural restrictions of the API and not arbitrarily add/remove fields/methods.

### 10.2. Testing Bytecode of Exception and Return Paths

For a method body:
- Cover all actual `RETURN`/`IRETURN`/`LRETURN`/`FRETURN`/`DRETURN`/`ARETURN` instructions.
- Cover explicit `ATHROW` and exceptions that can arise **implicitly** from instructions or method calls.
- Order try/catch handlers properly; do not catch everything and cause an exception that business code would have caught to propagate instead.
- Do not corrupt the return value sitting on the operand stack when calling helpers.
- Do not turn an exception exit into a normal return; do not let a helper exception mask a business exception.
- Preserve proper handling of null, boxed primitives, method descriptors, and generic bridge semantics.

Just because a tool supports entry/exit advice does not mean every exception is observed by default. For example, advice configured for “normal exit only” will skip abrupt completion. **Configuration must match test semantics**, not just annotation/API names.

### 10.3. Dedicated Tests for Constructors and Synchronized Methods

- Constructors: after `super()/this()` chain, `uninitializedThis`, exception handlers, and overloads/chaining; do not miscount objects from constructor call counts.
- Synchronized instance methods: preserve `ACC_SYNCHRONIZED`, monitor `this` held in body, released on normal/abrupt completion.
- Synchronized static methods: monitor `DeclaringClass.class`.
- `synchronized(lock)` blocks: explicit `monitorenter/monitorexit`, balanced structured locking across all branches, including exceptions.
- `wait`/`notify` if business code uses monitors: test signaling/liveness as well, not just counters.
- Asynchronous or concurrent events: callbacks/probe thread-safety, worker task exceptions, per-invocation context cleanup, and exporter backpressure.

Never add `synchronized` to a global helper just to simplify metric recording without measuring contention: it can turn an acceptable multi-threaded method into a new bottleneck.

### 10.4. Running a Matrix on Real JVMs

| Dimension | Recommended Cases |
| --- | --- |
| Java runtime | Lowest supported JDK (lesson: 17), deployed JDK, multiple vendors when needed |
| JVM flags | Default, `-Xverify:all`, relevant GC/diagnostic modes |
| Class kind | Public/private methods, constructors, abstract/native exclusions, interface default, record/enum if tool supports |
| Method return | `void`, primitives, reference, `null`, multiple `return`s |
| Exceptions | Internal catch, explicit throw, implicit throw, nested finally, checked/unchecked |
| Monitor | Instance/static synchronized, synchronized block, normal + exceptional paths |
| Class loader | Application loader, custom loader, and bootstrap targets if intentional |
| Retransformation | First definition and existing class with `canRetransform=true` when tool requires |
| Race/performance | Concurrency stress, lock contention, p99 latency, and GC pressure |
| Application semantics | Results, side effects, ordering, state mutation, observable exceptions |

Do not treat a single run of a small fixture as sufficient proof for all combinations. However, a small suite with **baseline + inject comparison, exact event counts, and verifier pass** is a solid foundation for catching regressions early.

## 11. Mistakes That Easily Slip Through Code Review

| Mistake | Why It Is Wrong | How to Detect |
| --- | --- | --- |
| Testing only the final return | Early returns miss exit recording or return wrong values | `multiple(-1)`, `(0)`, `(2)` with output + counter |
| Counting every exception as method failure | Internally caught exceptions still return normally | `divideOrFallback(0)` must succeed at boundary |
| Instrumenting only `ATHROW` | Exceptions from divide/invoke can propagate without explicit `ATHROW` | Test uncaught implicit exceptions |
| Placing hook on `this` before `super()` | Constructor verifier sees `uninitializedThis` | `-Xverify:all`, `javap -c` constructor |
| Catch handler covering entire constructor chain | Invalid verifier state if superclass init fails | Test superclass throwing + frames |
| One object equals one `<init>` | Constructor delegation can invoke multiple `<init>`s | Test `this(...)` overload/chaining |
| Dropping `ACC_SYNCHRONIZED` during rewrite | Monitor semantics change, state races | `javap -v`, concurrency test |
| Adding `monitorenter` to synchronized method | JVM already locks implicitly; imbalance causes errors | Read flags/bytecode, monitor assertions |
| Hook swallows or replaces exception | Probe failure masks business failure | Assert exception type/message/cause |
| Single entry count proves branch coverage | Method-level metrics do not show true/false edges | Branch-specific cases and coverage tool |
| Assuming `LongAdder.sum()` is always atomic | Reading while multiple threads write is not a consistent snapshot | Wait for `Future.get()` before assertions |
| Watching only transformer callback | Callback may return `null` or invalid bytes | Verify class and test `ProbeRecorder` |
| Assuming `ASSERTIONS_PASSED` in baseline is enough | Baseline does not run hooks, may miss inject bugs | Run all three modes |
| Assuming Java source variant passing means ASM weaver is right | Bytecode injection has distinct verifier/handler issues | Test actual woven bytes with `-Xverify:all` |
| Assuming probe in synchronized method is free | Hook extends critical section/lock hold time | Stress, latency, and contention metrics |

## 12. Checklist and Practice Exercises

Before accepting an instrumentation release:

- [ ] Are baseline, observe-only, and inject compared on **the same business suite**?
- [ ] Are constructor success/failure, `this(...)` chaining, superclass initialization, and `uninitializedThis` tested?
- [ ] Do all key conditional branches and return sites have separate outputs/assertions?
- [ ] Are there test cases for primitive/reference/void returns if instrumentation is broadly applied?
- [ ] Does an exception caught **inside** a method still count as success under the method-boundary policy?
- [ ] Are both explicit throws and implicit exception propagation tested?
- [ ] Is probe exit called exactly once without masking/rewriting business exceptions?
- [ ] Do synchronized methods preserve `ACC_SYNCHRONIZED` and implicit monitor semantics?
- [ ] Are normal/exception synchronized exits, worker concurrency, and monitor release tested?
- [ ] Are `javap -c/-v`, `-Xverify:all`, and classfile verification run on the final transformed bytes?
- [ ] Are StackMapTable, max locals/max stack, branch targets, and exception tables checked after weaving?
- [ ] Are helper classes visible to the defining loader/module of the instrumented class?
- [ ] Are tests run on the actual deployed JDK/VM versions and compatible bytecode tools?
- [ ] If retransformation is supported, are already-loaded classes and structural change limits tested?
- [ ] Is probe overhead inside critical sections/GC/latency monitored in realistic usage?

**Question 1.** A method has three returns, but the probe records three entries and only two exits. Should the test pass because the business outputs are correct?

**Answer:** No. There must be exactly one exit per invocation; missing an exit corrupts telemetry when that branch runs, even if the method output is correct.

**Question 2.** `20/0` is caught and returns `-20`. Is this a method failure?

**Answer:** Not under this lesson's method-boundary policy. The method completed normally, even though an exception occurred internally. Counting throw events is a separate question.

**Question 3.** A constructor probe is placed after `Object.<init>`; the superclass constructor throws before that point. Why is no failure event seen?

**Answer:** The probe has not executed yet. You cannot assume an event placed after superclass initialization covers every construction attempt; you must clearly define instrumentation scope and verifier limits.

**Question 4.** Why does a `synchronized` method have no `monitorenter` yet still acquire a lock?

**Answer:** The JVM checks the `ACC_SYNCHRONIZED` flag and manages the monitor **implicitly** on method invocation and return. `monitorenter`/`monitorexit` is the bytecode mechanism typically used in synchronized blocks.

**Question 5.** In the demo there are 800 concurrent `increment(1)` calls and the final state is 802. Why is the sync probe count 804?

**Answer:** Besides the 800 concurrent calls, there were two earlier normal calls, one exception call, and one final `increment(0)` used to read the state: 800 + 2 + 1 + 1 = 804.

**Question 6.** Both baseline and observe-only test suites pass with all probe counters at 0. Can we stop here?

**Answer:** No. Those two modes do not have method-body instrumentation; inject mode is required to verify counters and monitor semantics.

**Question 7.** Should we measure latency of a synchronized method while ignoring the probe time inside the monitor?

**Answer:** No. Entry/exit advice runs while the monitor is still held, which can lengthen the critical section; benchmarks must compare baseline and inject under the same concurrency and observe tail latency.

**Conclusion:** A good instrumentation test suite must ask **“does the new bytecode still obey Java/JVM semantics?”** rather than just “was the callback invoked?”. Constructors require safe advice placement after the initialization chain; multiple branches/returns require exit coverage; exceptions require classification at the method boundary; synchronized methods require preserving monitor semantics. **Combining behavior tests, counter invariants, verifier checks, and concurrency testing** produces trustworthy evidence.

### Official References

- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback, returned bytes, `null`, and exception semantics.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, retransformation, and `removeTransformer`.
- [JVMS 17 — 2.11.10 Synchronization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.10): synchronized methods with `ACC_SYNCHRONIZED` and implicit monitors.
- [JVMS 17 — 4.6 Methods](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.6): method flags, Code attribute, semantics of `ACC_SYNCHRONIZED`.
- [JVMS 17 — 4.10 Verification](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10): type verification, `uninitializedThis`, `StackMapTable`, and exception handlers.
- [JVMS 17 — 6 Instructions](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): `ireturn`/`areturn`/`athrow`/`monitorenter`/`monitorexit` and operand stack semantics.
