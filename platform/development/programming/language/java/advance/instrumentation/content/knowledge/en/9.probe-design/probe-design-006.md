# Preserving Original Return Values and Exception Objects When Designing Probes

When installing a Java agent or injecting bytecode to measure timing, trace execution, collect error statistics, or record events, **a probe must observe the method's outcome rather than becoming part of the business result itself**. Good instrumentation must never alter the return value, replace the thrown exception object, swallow a business error, or raise a telemetry error that causes the caller to observe a different outcome.

This is a core principle of **probe design in Java instrumentation**: on the success path, the method continues to return the exact same value/reference; on the failure path, the method continues to throw **the exact original `Throwable` object**. This article explains the exact meaning, Java `try/finally` rules, JVM bytecode-level exit paths, a runnable Java 17+ example, how to apply this with agents/Byte Buddy/ASM, and a suite of *non-interference invariants* tests.

## 1. What Does "Preserving" Mean?

Think of the original method as a computation with two possible completion forms:

~~~text
                      originalMethod(...)
                             |
                +------------+------------+
                |                         |
         Normal completion         Abnormal completion
                |                         |
       returns value R / void       throws Throwable T
                |                         |
          probe observes            probe observes
                |                         |
       returns exact R / void       throws exact same T
~~~

At a minimum, an acceptable probe must preserve the following invariants:

| Case | Invariant to Preserve |
| --- | --- |
| `int`, `long`, `boolean`, and other primitive types | The bit pattern/semantics of the result are not unintentionally altered |
| `float`, `double` | Special cases such as `-0.0` are not lost; pay attention to NaN if bit-level verification is needed |
| Returning an object/array | **The exact same reference** returned by the method; use `==` to verify identity |
| Returning `null` | Continues to return `null`; do not replace with a dummy object or `Optional` |
| `void` method | Completes normally as before, with no exception thrown from the hook |
| Throwing a checked exception | Caller catches **the same instance** of `IOException`/thrown exception type |
| Throwing an unchecked exception or `Error` | Caller receives **the same instance** of `Throwable`, not replaced by another exception |
| Method catches an error internally and returns normally | Exit hook sees the **final outcome** as success, and does not report an error that never escaped the method |
| Telemetry hook encounters an error | Hook failure must not replace the business return value or throwable |

For objects, "preserving identity" **does not mean the object is completely immutable**. If the hook calls `toString()` and that mutates the object's internal state, `returned == original` is still `true`, yet application behavior may have changed. Therefore, you must avoid both **replacing the reference** and **unintended side effects**.

Similarly, checking an exception with `actual.getClass() == expected.getClass()` or `actual.getMessage().equals(...)` is insufficient: two different instances can share the same type and message. When "the original exception object" is required, the central invariant is **`actual == originalThrowable`**.

## 2. Why Is `try/finally` Both Useful and Dangerous?

The Java Language Specification (JLS §14.20.2) describes the execution order of `try/finally`. When a `try` block is about to `return` or `throw`, the `finally` block executes before that completion reason propagates to the caller.

If `finally` **completes normally**, the prior completion reason is preserved. If `finally` itself **completes abruptly** (throws an exception or executes a `return`), the old reason can be **replaced**. This is a serious source of bugs when injecting instrumentation.

### 2.1. Correct pattern: isolated hook

~~~java
static int measured(int input) {
    long started = System.nanoTime();
    try {
        return input * 2;
    } finally {
        safeRecord(started);
    }
}
~~~

This is an **illustrative snippet** that requires defining `safeRecord(long)`; a full example is in Section 5. The expression `input * 2` is evaluated first, and then `safeRecord` runs. If `safeRecord` completes normally, the caller receives the exact original result without recomputation or overwriting the return value.

### 2.2. Broken pattern: `return` inside `finally`

~~~java
static int broken(int input) {
    try {
        return input * 2;
    } finally {
        return 0; // WRONG: every normal result is replaced with 0.
    }
}
~~~

If the `try` block throws an error, `return 0` in `finally` can also **swallow the exception completely**. This is not a logging technique; it changes the method contract.

### 2.3. Broken pattern: probe exception masks original exception

~~~java
static void brokenFailure() {
    try {
        throw new IllegalArgumentException("business");
    } finally {
        throw new IllegalStateException("telemetry"); // WRONG
    }
}
~~~

The caller sees `IllegalStateException("telemetry")`, **not** `IllegalArgumentException("business")`. If the agent's goal is non-intrusive observation, this outcome is unacceptable.

### 2.4. Safe pattern: isolate only probe-originated failures

~~~java
static void safeRecord(long startedNanos) {
    try {
        long elapsed = System.nanoTime() - startedNanos;
        recordMetric(elapsed);
    } catch (Throwable probeFailure) {
        // Intentionally do not throw telemetry errors out of the business method.
        // May increment a fail-safe counter if the counter itself is safe.
    }
}
~~~

This is a **code snippet** requiring a `recordMetric(long)` method. The key point is that `catch` wraps only the **probe operation**, not the business logic, so it never swallows real exceptions. In production, deciding to catch all `Throwable` (including `Error`) must be based on a fail-open policy for telemetry; when the JVM is severely out of resources, it cannot be guaranteed that every `OutOfMemoryError` or process termination is recoverable.

**Distinction:** "not letting telemetry corrupt the result" is different from "all errors in the system are ignored". Handle only errors originating from measurement code; never mask business errors.

## 3. What Must Be Preserved at the JVM Bytecode Level?

At the class-file level, each return type has its own instruction, and exceptional exits have their own control flow.

| Method Return Type | Typical JVM Instruction | Data to Preserve |
| --- | --- | --- |
| `boolean`, `byte`, `char`, `short`, `int` | `ireturn` | Int-category value on the operand stack |
| `long` | `lreturn` | `long` value (2 local-variable slots if stored temporarily) |
| `float` | `freturn` | `float` value |
| `double` | `dreturn` | `double` value (2 local-variable slots if stored temporarily) |
| Object, array, `null` | `areturn` | Reference on the operand stack |
| `void` | `return` | No return value |
| Throw object | `athrow` | Reference to **the existing `Throwable` object** |

**Normal exit flow design** when inserting measurement code right before a return instruction:

~~~text
Before:
  ... computation
  IRETURN

After (illustrating a method returning int):
  ... computation
  ISTORE tempReturn      ; preserve the value about to be returned
  invoke safe probe
  ILOAD tempReturn       ; reload the exact original value
  IRETURN
~~~

For `ARETURN`, replace `ISTORE/ILOAD` with `ASTORE/ALOAD`, preserving the **reference** without cloning the object. For `LRETURN` and `DRETURN`, use `LSTORE/LLOAD` or `DSTORE/DLOAD` and allocate two slots. `RETURN` for `void` needs no value saved.

**Exceptional exit design** can be represented logically as follows:

~~~text
Business error T occurs
        |
        v
handler catches exact T
        |
    ASTORE tempThrowable
        |
    invoke safe probe
        |
    ALOAD tempThrowable
        |
      ATHROW              ; rethrow the exact same object T
~~~

Both diagrams are **bytecode pseudocode**, not directly compilable assembler instructions. A real agent must emit valid instructions, local slots, branch targets, exception tables, and stack-map frames.

### Easy-to-miss point: it's not only explicit `ATHROW`

The JVM can raise exceptions from many other instructions, such as:

- `invokevirtual` can throw `NullPointerException` or an error inside the called method.
- `aaload`/`iaload` can throw array access errors.
- `checkcast` can throw `ClassCastException`.
- `idiv` can throw `ArithmeticException`.
- Class loading/linking can also fail at runtime.

Therefore, **injecting code only when encountering an `ATHROW` opcode is not enough to measure all exceptional exits**. An exception can escape a method whose body contains no explicit `ATHROW`. For an exit probe to handle these errors as well, you need an appropriate catch-all mechanism wrapping the method's execution region or an advice library supporting `onThrowable`.

An ASM construct like `AdviceAdapter.onMethodExit(int opcode)` is useful for handling explicit exit opcodes, but it does not automatically replace a catch-all handler for all implicitly raised exceptions. Be sure to test both instruction-raised errors and errors propagating from a called method.

## 4. Keep the Original `Throwable` Object, Not Just the Same Exception Type

The following two code paths **differ** in contract:

~~~java
catch (Throwable original) {
    recordFailureSafely(original);
    throw original; // Same instance (if recordFailureSafely does not throw an error).
}
~~~

~~~java
catch (Throwable original) {
    recordFailureSafely(original);
    throw new RuntimeException(original); // WRONG: caller sees a new instance.
}
~~~

These are **code snippets** for comparison, not complete classes. The second pattern creates a wrapper exception; the class, identity, `catch` matching, displayed stack trace, and caller behavior can all change.

Besides `new RuntimeException(original)`, the following operations can also break exception preservation:

- `throw new SomeException(original.getMessage())`: discards the original instance and may lose cause/suppressed exceptions.
- `return defaultValue` in the exceptional path: swallows the error completely.
- Assigning `null` or another exception to the `Throwable` storage slot in bytecode/advice.
- Calling `fillInStackTrace()`, `setStackTrace(...)`, `initCause(...)`, or `addSuppressed(...)` just for telemetry: this still **mutates the original object**.
- Arbitrarily calling `toString()` or `getMessage()` on a throwable/user object when building logs: overridden application code may be expensive, have side effects, or throw another exception.
- Using `getCause()` instead of the escaping exception itself: the cause is a different `Throwable` (if present), not the object being thrown.

If you want to classify errors, collect minimal metadata such as the presence of a `Throwable` and its error type via appropriate APIs, then emit the event to a bounded telemetry channel. **Observing does not grant permission to mutate the error object**.

### Do not automatically use `addSuppressed` for probe errors

There are cases where a framework wants to retain a secondary error as a `suppressed exception`. However, if the contract is to **preserve the original exception object and its state**, calling `original.addSuppressed(probeFailure)` also mutates the original object. Normally, telemetry errors should be recorded on a separate channel rather than attached to the business error; if recording is impossible because telemetry itself is broken, accept dropping the measurement data.

If the original method uses `try-with-resources`, errors occurring in `close()` may already be managed by Java into the business exception's suppressed list. A probe placed at the **exit of the entire method** should observe the final `Throwable` after resource cleanup logic, without altering the close order or interfering with the existing suppressed list.

## 5. Complete Java 17+ Example: Intentionally Broken Hook Yet Original Outcome Preserved

The following example uses `try/finally` at the **source-code level** to reproduce the principle that bytecode instrumentation must achieve. It does not require Byte Buddy, ASM, or a Java agent; thus it is easy to run to verify values/identity. The probe here **intentionally throws `IllegalStateException`** every time, yet `recordSafely` isolates that failure.

### 5.1. Create `ExitPreservationDemo.java`

~~~java
import java.io.IOException;

public final class ExitPreservationDemo {
    private static final IOException ORIGINAL_CHECKED =
            new IOException("business-checked");
    private static final IllegalArgumentException ORIGINAL_UNCHECKED =
            new IllegalArgumentException("business-unchecked");
    private static final AssertionError ORIGINAL_ERROR =
            new AssertionError("business-error");

    private static volatile boolean failTelemetry = true;
    private static volatile long lastElapsedNanos;
    private static int probeCalls;
    private static int probeFailures;

    private static void recordSafely(long startedNanos) {
        try {
            probeCalls++;
            lastElapsedNanos = System.nanoTime() - startedNanos;
            if (failTelemetry) {
                throw new IllegalStateException("simulated telemetry failure");
            }
        } catch (Throwable ignored) {
            probeFailures++;
        }
    }

    private static int intValue() {
        long started = System.nanoTime();
        try {
            return 42;
        } finally {
            recordSafely(started);
        }
    }

    private static long longValue() {
        long started = System.nanoTime();
        try {
            return Long.MAX_VALUE;
        } finally {
            recordSafely(started);
        }
    }

    private static double negativeZero() {
        long started = System.nanoTime();
        try {
            return -0.0d;
        } finally {
            recordSafely(started);
        }
    }

    private static Object sameReference(Object original) {
        long started = System.nanoTime();
        try {
            return original;
        } finally {
            recordSafely(started);
        }
    }

    private static Object nullable() {
        long started = System.nanoTime();
        try {
            return null;
        } finally {
            recordSafely(started);
        }
    }

    private static void completeVoid() {
        long started = System.nanoTime();
        try {
            // Business code that completes normally.
        } finally {
            recordSafely(started);
        }
    }

    private static String checkedFailure() throws IOException {
        long started = System.nanoTime();
        try {
            throw ORIGINAL_CHECKED;
        } finally {
            recordSafely(started);
        }
    }

    private static String uncheckedFailure() {
        long started = System.nanoTime();
        try {
            throw ORIGINAL_UNCHECKED;
        } finally {
            recordSafely(started);
        }
    }

    private static String errorFailure() {
        long started = System.nanoTime();
        try {
            throw ORIGINAL_ERROR;
        } finally {
            recordSafely(started);
        }
    }

    public static void main(String[] args) {
        System.out.println("int=" + intValue());
        System.out.println("longPreserved="
                + (longValue() == Long.MAX_VALUE));
        System.out.println("negativeZeroBits="
                + (Double.doubleToRawLongBits(negativeZero())
                == Double.doubleToRawLongBits(-0.0d)));

        Object original = new Object();
        System.out.println("referenceSame="
                + (sameReference(original) == original));
        System.out.println("nullPreserved=" + (nullable() == null));

        completeVoid();
        System.out.println("voidCompleted=true");

        try {
            checkedFailure();
        } catch (IOException actual) {
            System.out.println("checkedSame=" + (actual == ORIGINAL_CHECKED));
        }

        try {
            uncheckedFailure();
        } catch (IllegalArgumentException actual) {
            System.out.println("uncheckedSame="
                    + (actual == ORIGINAL_UNCHECKED));
        }

        try {
            errorFailure();
        } catch (AssertionError actual) {
            System.out.println("errorSame=" + (actual == ORIGINAL_ERROR));
        }

        System.out.println("probeCalls=" + probeCalls);
        System.out.println("probeFailures=" + probeFailures);
    }
}
~~~

### 5.2. Compile and run

Save the file with the exact name and run in the containing directory using **JDK 17+**:

~~~bash
javac ExitPreservationDemo.java
java ExitPreservationDemo
~~~

**Stdout verified with JDK 24:**

~~~text
int=42
longPreserved=true
negativeZeroBits=true
referenceSame=true
nullPreserved=true
voidCompleted=true
checkedSame=true
uncheckedSame=true
errorSame=true
probeCalls=9
probeFailures=9
~~~

Explanation of each test group:

- `int=42` and `longPreserved=true` confirm primitive values are unchanged.
- `negativeZeroBits=true` checks the **raw bit pattern** of `-0.0d`, which `== 0.0d` cannot distinguish.
- `referenceSame=true` confirms the exact input object is returned, not merely an object equal by `equals()`.
- `nullPreserved=true` confirms `null` is not converted into another value.
- `voidCompleted=true` confirms a `void` method's success path is not broken by a telemetry exception.
- The three lines `checkedSame`, `uncheckedSame`, and `errorSame` verify the identity of checked, unchecked, and `Error` exceptions using the `==` operator.
- `probeCalls=9`, `probeFailures=9` show all nine hook invocations intentionally failed, yet **no telemetry failure altered the business method's outcome**.

This is a sequential simulation, not a thread-safe metrics counter: `probeCalls++` and `probeFailures++` in the demo are unsafe under concurrent writes from multiple threads. In multithreaded applications, use an appropriate mechanism such as `LongAdder` or a non-blocking bounded queue, and test their failure modes.

### 5.3. Inspecting bytecode generated by `javac`

Run:

~~~bash
javap -c -p ExitPreservationDemo
~~~

Depending on compiler-emitted code, you will see temporary storage of the return value and **exception tables** to run cleanup in `finally`. When compiling the example above with JDK 24, `javap` shows `ireturn`, `lreturn`, `dreturn`, `areturn`, `athrow` instructions and exception tables matching the model in Section 3.

**Do not hardcode exact local slot indices or bytecode offsets as assumptions** for other compilers or JDKs. The invariant to test is the observable result/throwable after instrumentation, not that the bytecode shape matches a single `javap` output.

## 6. Using Byte Buddy: Keep Bindings in `readOnly` Mode

When using Byte Buddy `Advice`, an exit hook can observe normal and exceptional exits without manually building exception tables. However, **the default configuration of `@Advice.OnMethodExit` does not run when the method exits with an exception**. To observe both paths, you must configure `onThrowable`.

An **API illustration example, not a standalone program** (requires the Byte Buddy dependency and a `Metrics.recordExit(...)` method provided by you):

~~~java
import net.bytebuddy.asm.Advice;

public final class SafeExitAdvice {
    @Advice.OnMethodEnter(suppress = Throwable.class)
    static long enter() {
        return System.nanoTime();
    }

    @Advice.OnMethodExit(
            onThrowable = Throwable.class,
            suppress = Throwable.class)
    static void exit(
            @Advice.Enter long startedNanos,
            @Advice.Thrown(readOnly = true) Throwable originalFailure) {
        Metrics.recordExit(startedNanos, originalFailure);
    }
}
~~~

Critical details:

1. `onThrowable = Throwable.class` instructs the exit advice to run on the path where the method throws a `Throwable` as well. Omitting this configuration can cause you to **miss failure counts**.
2. `@Advice.Thrown(readOnly = true)` reads the object thrown on an exceptional exit; on a normal exit it is `null`. **Do not assign** another exception to the binding and do not set `readOnly=false` just to make mutating it convenient.
3. `suppress = Throwable.class` on **both enter and exit advice** is a fail-open choice: when telemetry code throws a `Throwable`, Byte Buddy suppresses it to the extent the advice can handle it. You should evaluate the feasibility of catching every `Error` under your environment's reliability policy; recovery cannot be guaranteed once the JVM is no longer operational.
4. `@Advice.Enter` passes data from enter advice to exit advice; here it is a timestamp, unrelated to the return value.
5. Do not use `@Advice.Return(readOnly = false)` or `@Advice.Thrown(readOnly = false)` when the goal is purely observation; writable mode creates the possibility of altering the business outcome.
6. The `Metrics.recordExit(...)` code is a **dependency that must be visible** in the class loader/module environment of the instrumented method. If a dependency cannot be loaded, the advice can still cause linkage errors or instrumentation failures before runtime suppression ever has a chance to run.

You can observe the return value via `@Advice.Return` in appropriate advice, but you must account for `void` methods, primitive types, boxing, `null`, and type-binding constraints. If you only measure latency and outcome (success/failure), **not touching the return value at all** is the lower-risk option.

**Do not set `repeatOn` or `skipOn`** when the requirement is to preserve executing the method exactly once. Those options can change how many times the business logic runs. Also do not turn exit advice into a place that calls back into the instrumented method—that can cause recursion and alter the outcome.

### Should telemetry errors be caught directly inside the advice?

`suppress` is a mechanism provided by Byte Buddy, but production code should still design `Metrics.recordExit(...)` to be fast, non-throwing, and never re-enter instrumented methods. For some pipelines, a standalone fail-safe telemetry helper is easier to test than relying solely on framework suppression.

Do not confuse the advice above with **suppressing the original `Throwable`**. `suppress = Throwable.class` applies to errors originating **inside the advice**; `@Advice.Thrown(readOnly=true)` is used to **observe the method's error**. These two error sources serve different roles.

## 7. Using ASM or the Class-File API: Both Exit Paths Must Be Covered

If you write a bytecode transformer yourself, design it as a **control-flow preservation** problem:

1. Inspect the method descriptor to choose the right return instruction group and local slot size.
2. At every normal return, **save the exact value currently on the operand stack**, invoke the safe helper, reload **that exact value**, and then execute the original return.
3. Create an appropriate catch-all path for any exception **escaping the business body**, not just explicit `ATHROW` instructions.
4. In the handler, save **the exact `Throwable` reference** into a local, run the safe helper, reload the same reference, and `ATHROW`.
5. Do not let the exception handler region cover the measurement code itself if that would re-catch hook errors, loop, or swallow exceptions.
6. Update the exception table, try ranges, stack-map frames, `maxStack`, and `maxLocals` appropriate for the class-file version.
7. Preserve the method's existing exception handlers and cleanup logic, especially `try-with-resources`, `synchronized`, `finally`, and code with multiple returns.

The steps above are a **design model**. Implementation details must follow the contract of ASM `AdviceAdapter` or the JDK Class-File API for the target version, and must pass the verifier. There is no single generic "insert before every return" operation that automatically handles all **implicitly JVM-raised exceptional exits**.

### Return instruction groups and local slot sizes

A common bytecode bug is using `ASTORE` for every result. `ASTORE` applies only to references; if `long`/`double` is on the stack, the type and slot count are completely different:

~~~text
int/boolean/byte/short/char -> ISTORE / ILOAD -> IRETURN
long                        -> LSTORE / LLOAD -> LRETURN
float                       -> FSTORE / FLOAD -> FRETURN
double                      -> DSTORE / DLOAD -> DRETURN
object/array/null           -> ASTORE / ALOAD -> ARETURN
void                        -> (no return slot needed) -> RETURN
Abnormal Throwable          -> ASTORE / ALOAD -> ATHROW
~~~

This is an **opcode mapping table**, not a runnable code fence. For `float`/`double`, do not convert to another numeric type "for convenient metrics recording"; conversion can lose raw-bit identity, NaN payloads, or the sign of zero. Do not call `equals()` or `toString()` on the returned object just to check identity.

### Special care with constructors and static initializers

A constructor `<init>` has object initialization rules and an `uninitializedThis` state before the `super(...)` call; inserting a catch-all or code calling an instance helper in the wrong place can cause verifier errors. `<clinit>` also has special class initialization semantics. Do not apply a recipe meant for normal methods blindly to all methods; test separately or exclude them from the initial probe scope.

In addition, instrumentation on `native`/`abstract` methods cannot simply add JVM instructions to a `Code` attribute that does not exist. If you want to observe them, a different wrapping technique or hook point is needed while preserving the contract.

## 8. Risks Beyond Return Value and Exception Identity

Even when the two main invariants hold, telemetry can still interfere with runtime behavior:

| Risk | Why It Is Dangerous | Mitigation |
| --- | --- | --- |
| Hook runs before business logic and throws | The real method may never be called | Protect enter advice as well or avoid pre-call failures |
| Hook logs synchronously / waits on network | Increases latency, alters lock contention, causes timeouts | Bounded queue, sampling, fail-open under overload |
| Hook calls the instrumented method itself | Infinite loop / stack overflow | Reentrancy guard, exclude helper/telemetry packages from transformation |
| Hook touches the return value | May call `toString()`/getters with side effects | Record only minimal metadata when payload is unnecessary |
| Hook mutates `Throwable` or cause/suppressed | Caller receives altered exception or state | `@Advice.Thrown(readOnly=true)`; do not mutate the exception |
| Hook calls `Thread.interrupted()` | That call can **clear the interrupt flag** | Do not read interrupt status via a side-effecting API; consider `isInterrupted()` |
| Hook placed inside a `synchronized` region | Lock hold time may increase | Keep measurement minimal, test contention, reconsider hook placement |
| Hook writes shared non-atomic counters | Lost updates, inaccurate metrics | `LongAdder`/appropriate synchronization |
| Using `catch(Exception)` instead of `catch(Throwable)` in hook | An `Error` from the hook can still replace the original exception | Choose an explicit fail-open policy; understand limits with fatal errors |
| Altering `try-with-resources` logic | Changes `close()` order or suppressed exceptions | Observe final outcome after business cleanup |
| Transformer emits invalid stack maps/handler ranges | `VerifyError`, `ClassFormatError`, or class load failure | Verify bytecode and test on target JDK |

**There is no physically "zero-impact" instrumentation**: measuring time and updating counters themselves consume CPU and can change thread scheduling or interleaving. The practical goal is to **preserve the observable business contract** and keep overhead and risk within controlled bounds.

Nor can `finally` be guaranteed to run when the process is killed, `Runtime.halt(...)` stops the JVM, power is lost, or the VM crashes. Claiming that "exit advice runs on every possible termination under all circumstances" is an overstatement.

## 9. Testing Strategy: Comparing Behavior Before and After Instrumentation

The test suite should compare the **exact same method** before and after, not just check a log saying "onExit was called". A practical matrix:

| Test Group | Input / Scenario | Essential Assertion |
| --- | --- | --- |
| Regular primitive | `int 42`, `long Long.MAX_VALUE` | Exact value comparison |
| Special primitive | `double -0.0`, `NaN`, `float` | Compare raw bits when bit-pattern preservation is required |
| Object | Returns exact object `o` | `assertSame(o, actual)` |
| Array | Returns original array object | `actual == originalArray` |
| Null | Returns `null` | `actual == null` |
| Void | Body completes normally | No `Throwable` from probe |
| Checked | `IOException original` | Caught exception `== original` |
| Runtime | `IllegalArgumentException original` | Caught exception `== original` |
| Error | `AssertionError original` | Caught object `== original` |
| Multiple return branches | Multiple `if`/`switch` branches | Every branch preserves the right outcome, probe records the right count |
| Implicit exceptional exit | `throw` from called method, NPE, division by zero | Still reports exit and throws the exact object |
| Telemetry failure | Hook throws exception on both enter and exit | Business outcome unchanged |
| Reentrant instrumentation | Helper is also transformed | No infinite recursion |
| Try-with-resources | Body fails, `close()` also fails | Original method's close order and suppressed exceptions are unchanged |
| Synchronized/concurrent | Multiple threads, interleaved exceptions and returns | No deadlock or swapped errors; metrics follow rules |

In JUnit, the identity invariant is typically written as:

~~~java
Throwable actual = org.junit.jupiter.api.Assertions.assertThrows(
        IOException.class, () -> instrumentedMethod());
org.junit.jupiter.api.Assertions.assertSame(originalThrowable, actual);
~~~

This is an **illustrative test snippet** requiring the JUnit 5 dependency, an `instrumentedMethod()` that actually throws a checked exception, and an `originalThrowable` variable provided in the test. In plain Java, the `==` operator as in the Section 5 program is sufficient to check identity.

Beyond identity, compare `getCause()` and `getSuppressed()` when the contract requires them to remain unchanged. Do not create a new stack trace or call `fillInStackTrace()` during measurement. If you must assert on stack frames, keep in mind that bytecode weaving can shift line-number mappings or add extra frames; do not equate every difference in stack trace presentation with replacing the `Throwable` object.

### Before/after testing with a reference oracle

A useful automation approach is to prepare two versions of the same business logic: **uninstrumented** and **instrumented**. Run the same input suite and record outcomes in pairs:

~~~text
Original invocation                 Instrumented invocation
returns primitive V       ---->    returns same V
returns object R          ---->    returns same R (identity)
returns null              ---->    returns null
completes void            ---->    completes void
throws Throwable T        ---->    throws exact same T reference
~~~

For exception identity, you should proactively create/hold a reference to an error instance before throwing it (as in the Section 5 example), rather than comparing two exceptions **created independently** across two runs. Two separate invocations can legitimately create two different `Throwable` instances; identity comparison is only meaningful when the same instance is routed through the instrumented path.

## 10. Checklist for Implementing Outcome-Preserving Probes

1. **Choose the right scope:** target methods that need monitoring; avoid probing telemetry/logger/class-loader internals themselves.
2. **Identify both exit paths:** normal return and exceptional exit **escaping the method**, not just explicit `ATHROW` instructions.
3. **Preserve return values:** preserve value for primitives; preserve reference for objects; produce no return value for `void`.
4. **Preserve `Throwable`:** do not wrap/replace/suppress, and do not mutate cause/suppressed/stack trace just to collect metrics.
5. **Keep telemetry code fail-open:** the hook must complete normally under errors it causes itself; have an explicit policy for fatal JVM errors.
6. **Do not re-execute business logic:** do not invoke the original method a second time to measure it, and do not use `repeatOn`/`skipOn` unless specifically required.
7. **Preserve valid bytecode:** locals/stack/handlers/frames and special constructor rules.
8. **Avoid extra side effects:** do not arbitrarily call getters/`toString()` on return values/`Throwable`; do not clear the interrupt flag.
9. **Test failure paths too:** checked, unchecked, `Error`, implicitly raised exceptions, hook failures, and multiple return branches.
10. **Measure operational impact:** latency, lock contention, reentrancy, sampling, and behavior when the telemetry system is overloaded.

In summary: **a probe should extract data from the final outcome of a call, not take control over deciding that outcome**. An instrumented method must continue to return the exact same value or throw the exact same original error object; telemetry's own failures must never alter the business contract.

## 11. Exercises and Answers

**Question 1.** A method returns `Object o` and exit advice calls `o.toString()` for logging. The returned object is still `o`. Can you conclude the probe completely avoids altering behavior?

**Question 2.** A method `int compute()` has `return 7` in `try` and `return 0` in `finally`. What does the caller see? What if `try` throws an exception?

**Question 3.** A hook catches the original exception `IOException original` and does `throw new RuntimeException(original)`. Is "preserving the exact exception object" satisfied?

**Question 4.** An agent only adds a callback before every `ATHROW` opcode. Can it measure every exceptional exit when the method calls another method and that method throws an error?

**Question 5.** While handling `LRETURN`, a bytecode transformer stores the value into a local using `ISTORE`, then calls the hook. What is the design bug?

**Question 6.** Byte Buddy `@Advice.OnMethodExit` does not specify `onThrowable`. Is the method's exception count guaranteed to be recorded?

**Question 7.** Does `catch(Throwable probeFailure)` inside `safeRecord` mean all business exceptions will be ignored?

**Question 8.** Two exceptions have the same class, message, and stack trace, but were created by two separate `new` calls. Is that proof they are the same object?

**Question 9.** For a method returning `double -0.0`, is checking `actual == -0.0` alone enough to verify the bit pattern?

### Answers

1. **No.** `toString()` can be overridden, throw an error, or cause side effects. Preserving identity alone is not enough to claim there is no other impact.
2. The caller receives **0**; `return 0` in `finally` overwrites the result and can even swallow an exception from `try`.
3. **No.** The caller receives a new `RuntimeException` wrapper, not `IOException original`.
4. **No.** An exception can be raised by or propagate from another instruction without the method containing an `ATHROW` at the exit path.
5. `long` must be stored/loaded via `LSTORE/LLOAD`, occupying two local slots; using `ISTORE` has the wrong type/stack and will likely be rejected by the verifier.
6. **No.** By default, exit advice is not invoked when a method exits via an exception; `onThrowable=Throwable.class` must be configured if you need to measure the failure path.
7. **No.** The `catch` only wraps the probe operation; business logic is outside `safeRecord`, and the original exception continues to propagate if `finally` completes normally.
8. **No.** You need the `==`/`assertSame` check on two references pointing to the exact same instance.
9. **No.** `0.0d == -0.0d` is `true`. To verify the bit pattern, use `Double.doubleToRawLongBits(...)`.

## 12. Official References

- [Java Language Specification 21 — §14.20.2, Execution of try-finally](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.2): rules for preserving or replacing completion reasons when `finally` runs.
- [Java Virtual Machine Specification 21 — §2.11.8–2.11.9](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.11.8): `ireturn/lreturn/freturn/dreturn/areturn/return` and exceptional completion.
- [JVM Specification 21 — §6.5, athrow](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.athrow): the `athrow` instruction and passing the `Throwable` reference in handlers.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer contract and valid class-bytes requirements.
- [Byte Buddy API 1.18.2 — Advice.OnMethodExit](https://javadoc.io/static/net.bytebuddy/byte-buddy/1.18.2/net/bytebuddy/asm/Advice.OnMethodExit.html): `onThrowable`, `suppress`, and exit advice semantics.
- [Byte Buddy API 1.18.2 — Advice.Thrown](https://javadoc.io/static/net.bytebuddy/byte-buddy/1.18.2/net/bytebuddy/asm/Advice.Thrown.html): exception binding on exit, `readOnly` mode, and risks of altering exceptions.
