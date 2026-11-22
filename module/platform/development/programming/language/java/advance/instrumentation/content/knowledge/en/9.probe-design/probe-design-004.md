# Distinguishing All `return` Instructions from Exception Exit Paths When Designing Java Probes

When designing a Java agent to measure **execution time, invocation count, success/failure outcomes, or tracing**, placing a probe at the end of a method seems simple. However, at the bytecode level, a method invocation can terminate through **two different mechanisms**:

1. **Normal completion**: execution reaches one of the **six return opcodes** (`ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn`, `return`).
2. **Abrupt completion**: an exception or `Error` **exits the method's frame** without being handled inside that method.

The two mechanisms are not equivalent. **Intercepting all `return`s still misses invocations that terminate due to an exception**; meanwhile, placing a probe at every `athrow` can **misrecord internally caught and handled exceptions** as method failures. This is the boundary that must be clarified in the **Probe Design** section of Java instrumentation.

Learning objectives after this lesson:

- Accurately identify the **six normal return opcodes**.
- Understand why `athrow` does **not** mean "this method definitely fails".
- See **implicit** exceptions from JVM instructions and **propagated** exceptions from callees.
- Design probes to classify **NORMAL / EXCEPTIONAL** based on the **final outcome of an invocation**, not on `return`/`throw` syntax in the source.
- Choose an appropriate bytecode/Advice strategy and avoid breaking the operand stack, exception table, `finally`, constructors, or the bytecode verifier.
- Run the Java 17+ example yourself, inspect `javap`, and interpret stdout.

## 1. You Must Define What You Are Measuring

There are at least three different kinds of events:

| Event | Question answered | Does it mean the method terminates abnormally? |
|---|---|---|
| A `return` opcode is executed | Did any branch return normally? | No; this is a normal completion branch |
| An exception is **thrown** at an instruction | Where did a throw action occur? | Not necessarily; the exception may be caught right inside the method |
| A method invocation **completes abruptly** | Which exception was not resolved inside the method and exited to the caller? | **Yes**; this is the exceptional outcome of the invocation |

Example:

```java
static int handled() {
    try {
        throw new IllegalStateException("inside");
    } catch (IllegalStateException problem) {
        return 9;
    }
}
```

The source has `throw` and the bytecode has `athrow`, but the caller receives **the value 9**. If `athrow` is counted as an "exceptional method exit", the measurement will be **wrong**.

Opposite example:

```java
static int callee(int x) {
    return 100 / x;
}

static int caller(int x) {
    return callee(x);
}
```

With `x == 0`, the JVM raises `ArithmeticException` at the integer division `idiv` in `callee`. When the exception propagates to `caller`, `caller` also terminates abruptly even though `caller`'s bytecode **does not necessarily contain an `athrow` instruction**. Searching only for `athrow` in `caller` will **miss** that failure.

**Definition used for probes:** an invocation is recorded as `NORMAL` if it actually completes normally; it is recorded as `EXCEPTIONAL` if a `Throwable` not handled internally causes the invocation to complete abruptly. These two labels describe the **final outcome**, not all exceptions that occurred internally.

## 2. The Six JVM `return` Opcodes: "Every Return" Means All Six

According to the Java Virtual Machine Specification, the normal return opcodes are:

| Opcode | Return type in bytecode | Notes |
|---|---|---|
| `ireturn` | `int`, `boolean`, `byte`, `char`, `short` | All five of these Java types use an `int`-form operand stack value at the JVM level |
| `lreturn` | `long` | The value occupies two slots on the operand stack |
| `freturn` | `float` | One slot |
| `dreturn` | `double` | Two slots |
| `areturn` | Object reference or array reference | One slot |
| `return` | `void`, instance initializer `<init>`, class initializer `<clinit>` | No return value |

In ASM, the corresponding commonly seen constant names are:

```java
Opcodes.IRETURN
Opcodes.LRETURN
Opcodes.FRETURN
Opcodes.DRETURN
Opcodes.ARETURN
Opcodes.RETURN
```

This is an **illustrative list of ASM constants**, not a standalone program. With a `MethodVisitor`, to place a "normal exit" call on every return path, you must check **all six opcodes**, not just uppercase `RETURN`.

There is no separate JVM opcode named `breturn`, `creturn`, `sreturn`, or `booleanreturn`. The types `boolean`/`byte`/`char`/`short` use `ireturn`.

### `return` in Java source is not a single bytecode probe point

A method with multiple branches:

```java
static int choose(int x) {
    if (x < 0) return -1;
    if (x == 0) return 0;
    return 1;
}
```

The compiler can generate **multiple `ireturn` instructions**. A probe placed "after the last `return` line in source" cannot cover branches that returned earlier.

Conversely, with `try/finally`, the compiler may **duplicate `finally` code into multiple branches**, change control flow structure, or hold temporary return values. Analyzing source to count `return` locations **does not replace** identifying the actual opcodes of the compiled class.

> Principle: if choosing **instruction-level instrumentation**, traverse and handle every **post-compilation return instruction** belonging to the target method, not just the last occurrence or each `return` keyword in the source code.

## 3. `athrow` Is a Throw Instruction, Not a "Seventh Return Opcode"

`athrow` (opcode `0xbf`) pops a `Throwable` reference from the operand stack and triggers the exception handler search process.

There are two outcomes:

1. **A matching handler exists in the same method:** control transfers to the handler. The method can recover and eventually **return normally**.
2. **No matching handler exists in the method:** the current frame is unwound, and the exception continues up to the caller. The invocation terminates **abruptly**.

Example with a local handler:

```java
static int recovered(int n) {
    try {
        return 100 / n;
    } catch (ArithmeticException problem) {
        return 42;
    }
}
```

When `n == 0`, `idiv` raises `ArithmeticException`, but the handler catches it and the method completes with **`42`**. You must not record the method exit as `EXCEPTIONAL` just because an intermediate exception occurred.

**More importantly:** an exception does not necessarily start with `athrow` in the bytecode of the method being measured itself. The JVM can raise exceptions while executing instructions:

| Instruction / situation | Example exception | Does `athrow` need to be present in that method? |
|---|---|---|
| `idiv`, `ldiv` with divisor 0 | `ArithmeticException` | No |
| `arraylength`, `getfield`, `invokevirtual` on a `null` reference | `NullPointerException` | No |
| Out-of-bounds array element access | `ArrayIndexOutOfBoundsException` | No |
| Incompatible `checkcast` | `ClassCastException` | No |
| `new` when allocation fails | `OutOfMemoryError` | No |
| `invokestatic`/`invokevirtual` calls a callee method and the callee throws an exception | Exception propagated back from callee | No |
| `athrow` from `throw new ...` in source | Throwable explicitly thrown by code | Yes, in the corresponding compiled branch |

These examples are **potential occurrences**, not that every execution of the instruction throws an exception. An `invoke*` can also fail during resolution, class initialization, or runtime according to JVM rules.

### What happens if the caller does not catch the exception?

```text
caller() is invoked
    |
    v
invokestatic callee()
    |
    v
callee(): idiv, divisor = 0
    |
    v
JVM creates ArithmeticException
    |
    +-- does callee have a matching catch? -- No -> unwind callee
    |
    +-- does caller have a matching catch? -- No -> unwind caller
    |
    v
caller() completes EXCEPTIONAL
```

`caller()` does not need to `new` an exception itself or execute `athrow`. Counting `athrow` opcodes **in the caller** is not enough to observe the caller's abrupt exit path.

## 4. Classifying by Final Outcome: Four Situations to Separate

| Code/execution flow | Did an exception ever occur? | How does the method end? | Correct exit label |
|---|---:|---|---|
| Reaches `ireturn`/`areturn`/`return` | Possibly not | Returns normally | `NORMAL` |
| `throw`, no catch in the method | Yes | Unwinds to caller | `EXCEPTIONAL` |
| `throw` or failing `idiv`, **caught** then `return` | Yes | Returns normally | `NORMAL` |
| Callee throws, current method does not catch | Yes | Unwinds without executing a return opcode of the current method | `EXCEPTIONAL` |

In addition, there are cases that alter the final outcome:

**`finally` replaces a `return` value:**

```java
static int finallyThrows() {
    try {
        return 8;
    } finally {
        throw new IllegalStateException("finally");
    }
}
```

At the source level there is `return 8`, but the invocation **does not return 8**: `finally` throws an exception before normal completion, so the label is `EXCEPTIONAL`.

**`finally` replaces an exception with a return:** a `finally` with a `return` can swallow/override an exception waiting to propagate out. This style should be avoided because it is hard to understand, but when instrumenting the **final outcome**, you must observe the actual return rather than labeling it a failure from the old exception that was replaced.

**Try-with-resources:** if closing a resource throws an exception while another exception already exists, Java can keep the primary exception and add the resource-closing error to the **suppressed exceptions** list. An invocation that terminates abruptly has only **one Throwable propagating out** (which may carry suppressed ones); it does not mean the number of internal errors equals the number of `EXCEPTIONAL` events of the method.

**Catch then rethrow:** if a method catches an exception and `throw`s it onward outside, the invocation is still `EXCEPTIONAL`. Classification must be based on whether the exception **exits** the method or not.

## 5. Runnable Java 17+ Example: Nine Execution Paths, One Result Table

The following example intentionally **requires no instrumentation library**: it clarifies method semantics before implementing bytecode weaving. This is a useful test oracle step: if a Java agent classifies differently from these results, the probe needs to be re-examined.

Create the directory:

```text
exit-path-demo/
└── src/
    ├── ExitCases.java
    └── ReturnKinds.java
```

### 5.1. `src/ExitCases.java` — normal/exceptional and caught exceptions

```java
import java.util.function.IntSupplier;

public final class ExitCases {
    private ExitCases() {}

    static int multi(int n) {
        if (n < 0) return -1;
        if (n == 0) return 0;
        return 1;
    }

    static int explicit(int n) {
        if (n < 0) throw new IllegalArgumentException("negative");
        return n;
    }

    static int nullArray(int[] values) {
        return values.length;
    }

    static int helper(int n) {
        return 100 / n;
    }

    static int propagate(int n) {
        return helper(n);
    }

    static int recovered(int n) {
        try {
            return helper(n);
        } catch (ArithmeticException exception) {
            return 42;
        }
    }

    static int localThrowCaught() {
        try {
            throw new IllegalStateException("inside");
        } catch (IllegalStateException exception) {
            return 9;
        }
    }

    static int finallyThrows() {
        try {
            return 8;
        } finally {
            throw new IllegalStateException("finally");
        }
    }

    static void observe(String name, IntSupplier action) {
        try {
            int value = action.getAsInt();
            System.out.println(name + " => NORMAL " + value);
        } catch (Throwable problem) {
            System.out.println(name + " => EXCEPTION "
                    + problem.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        observe("multi(-1)", () -> multi(-1));
        observe("multi(0)", () -> multi(0));
        observe("multi(3)", () -> multi(3));
        observe("explicit(-1)", () -> explicit(-1));
        observe("nullArray(null)", () -> nullArray(null));
        observe("propagate(0)", () -> propagate(0));
        observe("recovered(0)", () -> recovered(0));
        observe("localThrowCaught()", ExitCases::localThrowCaught);
        observe("finallyThrows()", ExitCases::finallyThrows);
    }
}
```

Note: `observe(...)` is a **caller-side wrapper** to verify the final outcome of the call, **not a `ClassFileTransformer`**, nor does it analyze bytecode itself. When the caller uses `observe`, it only sees the value/exception that reached the caller; it does not see the exact internal instructions or the number of exceptions caught inside.

Each scenario in the code:

- `multi`: three normal `ireturn` branches.
- `explicit`: `throw new ...` creates an uncaught `athrow` path.
- `nullArray`: `arraylength` on `null` produces a `NullPointerException` from a JVM instruction.
- `propagate`: callee `helper` divides by 0, and the exception propagates to `propagate` **without needing `athrow` in `propagate`**.
- `recovered`: division error is `catch`ed, returning `42` normally.
- `localThrowCaught`: has an explicit `throw` but catches it right inside the method, returning `9` normally.
- `finallyThrows`: `finally` throws and overrides the pending return value, so it terminates abruptly.

### 5.2. `src/ReturnKinds.java` — seeing all six return opcodes

```java
public final class ReturnKinds {
    private ReturnKinds() {}

    public static boolean flag() { return true; }
    public static byte small() { return 7; }
    public static char letter() { return 'A'; }
    public static short shortValue() { return 3; }
    public static int number() { return 5; }
    public static long longValue() { return 10L; }
    public static float floatValue() { return 1.5f; }
    public static double doubleValue() { return 2.5; }
    public static String text() { return "ok"; }
    public static void nothing() {}
}
```

The methods `flag`, `small`, `letter`, `shortValue`, `number` all have a terminating opcode belonging to the **`ireturn` family**. The remaining methods demonstrate `lreturn`, `freturn`, `dreturn`, `areturn`, `return`, respectively.

### 5.3. Compile and Run with JDK 17+

Open a terminal in the `exit-path-demo` directory and run:

```bash
mkdir out

javac --release 17 -encoding UTF-8 -d out src/ExitCases.java src/ReturnKinds.java
java -cp out ExitCases
```

`--release 17` requires JDK 17+ with a compiler. `mkdir out` only needs to be created once; if the directory already exists, you can skip this step.

**Exact stdout:**

```text
multi(-1) => NORMAL -1
multi(0) => NORMAL 0
multi(3) => NORMAL 1
explicit(-1) => EXCEPTION IllegalArgumentException
nullArray(null) => EXCEPTION NullPointerException
propagate(0) => EXCEPTION ArithmeticException
recovered(0) => NORMAL 42
localThrowCaught() => NORMAL 9
finallyThrows() => EXCEPTION IllegalStateException
```

Key takeaways:

- `localThrowCaught()` had `athrow` on the executed path, **but is not an exceptional exit**.
- `propagate(0)` terminates exceptionally even though the `propagate` method **has no `throw` statement in source**.
- `finallyThrows()` has `return` in source, **but is not a normal exit**.
- `recovered(0)` had an ArithmeticException internally, but the final outcome is `NORMAL 42`.

### 5.4. Using `javap` to Inspect Bytecode

```bash
javap -c -p -classpath out ReturnKinds
javap -c -p -classpath out ExitCases
```

`javap -c` prints bytecode, `-p` also shows non-`public` methods. In the output of `ReturnKinds`, check the corresponding **last opcode**:

```text
flag()        -> ireturn
small()       -> ireturn
letter()      -> ireturn
shortValue()  -> ireturn
number()      -> ireturn
longValue()   -> lreturn
floatValue()  -> freturn
doubleValue() -> dreturn
text()        -> areturn
nothing()     -> return
```

This is a **summary comparison table**, not verbatim `javap` output (offsets and constant-pool indices may vary).

In `ExitCases`, inspect the methods:

- `explicit(int)`: branch creates the exception and has `athrow`.
- `nullArray(int[])`: `arraylength` operation can throw NPE without needing an explicit `athrow`.
- `helper(int)`: integer division `idiv` can throw `ArithmeticException`.
- `propagate(int)`: has a call to `helper` followed by a normal return path; when `helper` throws, `propagate`'s return branch **is not executed**.
- `localThrowCaught()`: has `athrow`, **Exception table** leads to the handler and then the method returns `9`.
- `finallyThrows()`: inspect the `finally` code block; the outcome is an exception even though the source in `try` contains `return`.

`javap` lets you see why "counting every `athrow`" and "counting every `return`" **cannot replace the definition of method invocation outcome**.

## 6. Designing a Semantically Correct Method Exit Probe

First define the **event contract** for each eligible instrumented *method invocation*:

```text
METHOD_ENTER(methodId, invocationId, startTime)

METHOD_EXIT_NORMAL(methodId, invocationId, elapsed, returnValue?)
    or
METHOD_EXIT_EXCEPTIONAL(methodId, invocationId, elapsed, throwableType?)
```

When the agent operates normally and the instrumented code region runs through to a defined termination, the goals are:

- One **enter**.
- Exactly **one** of the two **exit** types.
- Elapsed time is computed from the same start timestamp to the actual termination time.
- `NORMAL` may or may not include a return value.
- `EXCEPTIONAL` includes the `Throwable` object exiting the method, if it can be safely observed.
- Do not count errors **that were caught and recovered** as an exceptional exit of the method.
- Must not alter the return value, original exception, or control flow due to instrumentation.

These are **design goals**, not absolute guarantees for JVM termination, VM crashes, or failures of the agent itself. Paths that stop outside Java method completion such as `Runtime.halt`, `System.exit` when the JVM exits, native crashes, or process kills do not necessarily trigger exit advice.

### 6.1. Combining Normal and Exceptional Probes

```text
                           Method entered
                                  |
                                  v
                           Original bytecode
                                  |
                   +--------------+--------------+
                   |                             |
                   v                             v
          Normal return opcode         Throwable not handled
          (one of the six kinds)       inside the method
                   |                             |
                   v                             v
          save return value            catch-all exception handler
          if needed                    observes Throwable
                   |                             |
                   v                             v
          record NORMAL                 record EXCEPTIONAL
                   |                             |
                   v                             v
          restore return value           rethrow original Throwable
          emit original return           (athrow)
```

**Two observation regions** are needed: the six return opcodes for normal, and a mechanism covering **exceptions exiting the method**. If you only implement the first half, the measurement is biased: failing methods lose exit events, and latency/success-rate statistics become inaccurate.

### 6.2. Metrics That Should Be Separated

| Metric | Meaning | Source |
|---|---|---|
| `invocations` | Number of times the method started | Entry hook |
| `normal_exits` | Number of normal completions | Hooks on the six return opcodes |
| `exceptional_exits` | Number of Throwables not handled in the method | Exceptional-exit handler/advice |
| `duration` | Duration of each invocation with an enter-exit pair | Timestamps before/after an invocation |
| `internal_exceptions` | Exceptions that occurred *internally*, including caught ones | Separate exception probe, **distinct from** method exit |

You must not assert `internal_exceptions == exceptional_exits`. One method can catch and handle multiple exceptions and then return normally; or a single exception can lead to the exceptional exit of **multiple frames** on the call stack.

If aggregating `normal_exits + exceptional_exits` to reconcile against `invocations`, you must also account for *in-flight* calls and those that did not complete due to process termination, sampling, or instrumentation errors.

## 7. Why Hooking Every `athrow` Is Still Wrong

A naive strategy is often written as:

```text
if opcode in {IRETURN, LRETURN, FRETURN, DRETURN, ARETURN, RETURN}:
    record NORMAL
else if opcode == ATHROW:
    record EXCEPTIONAL
```

This strategy has **two independent bugs**.

### Bug A: false positive — `athrow` caught in the same method

```java
static int handled() {
    try {
        throw new IllegalArgumentException();
    } catch (IllegalArgumentException problem) {
        return 7;
    }
}
```

The bytecode executes `athrow`, the handler receives the object and then returns `7`. If the `athrow` hook records exceptional, and then the `ireturn` hook records normal, **one invocation gets two exit labels**, violating the contract.

### Bug B: false negative — exception does not pass through `athrow` of the current method

```java
static int wrong(int[] values) {
    return values.length;
}
```

`values == null` causes an NPE at `arraylength`, causing the method to unwind **before reaching `ireturn`**, and this method does not need to have an `athrow`. Hooking the two instruction types misses the exceptional exit.

Similarly, an `invoke*` can cause the current method to unwind because a callee throws. A listener seeing an exception in the callee **does not prove** the current method has ended—the caller can still catch and return.

**Conclusion:** `athrow` is a **throw-mechanism instruction**, whereas an exceptional method exit is **the result of handler lookup and unwinding**. To measure invocation outcomes, probes must be placed at **frame** boundaries, not just on the `athrow` opcode.

## 8. Bytecode Strategy: Normal Returns + Catch-All for the Method Region

A typical bytecode-level implementation has two complementary parts.

### 8.1. Normal exit: handle all six opcodes

With an ASM `MethodVisitor` or equivalent bytecode-building API:

```text
for each instruction in method body:
    if opcode == IRETURN or LRETURN or FRETURN
       or DRETURN or ARETURN or RETURN:
        emit NORMAL probe immediately before this opcode
    emit original instruction
```

This is **conceptual pseudocode**, not standalone runnable Java.

Before `ireturn`/`freturn`/`areturn`, there is **a one-slot value** at the top of the operand stack; before `lreturn`/`dreturn`, there are **two slots**; before `return`, there is no return value.

If the probe needs to read the return value, it must:

- Store it into an appropriate local slot and reload it, or use `dup`/`dup2` operations while preserving proper stack discipline.
- Not mutate references, widening/narrowing, or operand stack types.
- For `void`, not attempt to pop a non-existent value.
- Pay attention to generic type erasure, bridge methods, method descriptors, and the verifier.

Instrumentation with an incorrect stack size will produce a `VerifyError` or corrupt program semantics. Therefore, with ASM you should use appropriate helpers such as `AdviceAdapter`/`LocalVariablesSorter` or **properly conditioned** frame computation, rather than inserting instructions manually without understanding the stack.

**Very important:** the normal probe must avoid throwing exceptions itself. If the logger itself throws while preparing to return, the method turns into an exceptional exit caused by **instrumentation**, not by the original logic.

### 8.2. Exceptional exit: catch-all handler for **escaping** Throwables

Idea:

```text
START_OF_INSTRUMENTED_BODY:
    ... original code, including original exception handlers ...
END_OF_INSTRUMENTED_BODY:

CATCH_ALL_HANDLER(Throwable t):
    recordExceptional(t)
    throw t
```

The model above is **pseudocode**, not sufficient to mechanically write ASM `tryCatchBlock` calls. In a real class file, exception handlers are entries in the **exception table** with a protected bytecode range and a handler location. How the protected range is constructed, the handler order, and when code is added must be calculated correctly.

Mandatory rules:

1. **Do not break original handlers:** the program's `try/catch`, `finally`, `synchronized`, and try-with-resources must remain intact.
2. **Do not "steal" exceptions that would be handled by an original handler:** if the catch-all is prioritized before an original handler, an internal exception that never left the method is misrecorded as an exceptional exit. For overlapping ranges, the order of entries in the exception table matters.
3. **Cover regions that can exit from original handler code as well:** an exception can occur right inside a `catch` or `finally`; covering only the "first try body" is not enough for all exceptional exits.
4. **Do not catch your own probe and create a loop:** typically keep measurement code and the synthetic handler outside the appropriate protected region, and have a defensive strategy if the probe fails.
5. **Preserve the original Throwable:** after recording, rethrow the exact exiting object; do not replace it with a new exception if the goal is non-intrusive measurement.
6. **Update stack map frames/max stack/max locals properly**, especially when adding branches and handlers. A valid class file is the minimum requirement.
7. **Handle constructor `<init>` regions properly:** before calling super/another constructor, `this` is still uninitialized; not every handler and advice pattern can be applied as on an ordinary method.
8. **Respect synchronization:** `synchronized` methods and `synchronized` blocks have rules for releasing monitors on normal/exceptional completion; do not break `monitorexit` and compiler-generated handlers.

If you do not have direct experience writing exception tables, prefer libraries that support method advice and test on diverse class bytecodes. Do not implement a single catch-all handler and assume it covers every Java method.

### 8.3. Single-exit strategy after merging control flow

Some tools can rewrite multiple `return`s into jumps to a common epilogue. Then the normal probe can reside in the epilogue. However, this is a **real control-flow transformation**:

- Must preserve each return's result, including two-slot `long`/`double`.
- Must not corrupt exception tables, `finally`, frames, and monitors.
- Must not turn an exceptional unwind into normal completion.
- Merging all branches is not always necessary or worthwhile.

If you only need exit counts and timing, an advice at each return is usually easier to control than rewriting the entire CFG.

## 9. Byte Buddy: `OnMethodExit` Does Not Cover Exceptional Exits by Default

Byte Buddy provides the `Advice` abstraction to add logic at method entry and exit. A very important detail in the API:

**`@Advice.OnMethodExit` by default runs only when a method completes normally.** To request the advice to also run when a method terminates with a `Throwable`, specify:

```java
@Advice.OnMethodExit(onThrowable = Throwable.class)
public static void onExit(@Advice.Thrown Throwable thrown) {
    if (thrown == null) {
        System.out.println("[advice] NORMAL");
    } else {
        System.out.println("[advice] EXCEPTIONAL "
                + thrown.getClass().getSimpleName());
    }
}
```

This is an **illustrative advice method**, not a standalone program. It must reside in a class importing `net.bytebuddy.asm.Advice` and must be **actually applied** to target methods via Byte Buddy/an agent or an appropriate class-generation process.

`@Advice.Thrown` receives the throwable exiting the instrumented method, or `null` if the method returned normally. `onThrowable = Throwable.class` requests inclusion of `Error` subclasses as well, not just `Exception`. In recent Byte Buddy versions, this configuration is clearly documented in the `Advice.OnMethodExit` Javadoc.

Notes:

- **Without** `onThrowable = Throwable.class`, normal-completion advice is **not sufficient** to measure method failure counts.
- Do not modify `@Advice.Thrown` (e.g., via writable binding) to swallow exceptions unless that is an intentional business requirement; changing the exception alters semantics.
- Do not assume the advice has the same coverage on special constructors, native/abstract methods, or methods that were not actually instrumented.
- Logging via `System.out` in advice is only suitable for learning. In production environments, use a lightweight tracer/metric recorder with reentrancy protection and avoid throwing exceptions.
- This is **an implementation choice**, not an inherent property of the JVM's `ClassFileTransformer`.

With an ASM-based instrumenter, you must ensure both exit path types yourself as in section 8. With properly configured Byte Buddy Advice, the library provides an abstraction for the exit contract, but you still must test edge cases.

## 10. Is `finally` the Best Exit Probe Point?

`finally` runs when leaving a `try` region in normal cases and many abrupt cases. However, **a plain `finally` hook does not distinguish the cause on its own**:

```java
static int sample(int x) {
    try {
        if (x == 0) return 0;
        return 100 / x;
    } finally {
        System.out.println("finally");
    }
}
```

With `x == 0`, `finally` runs and then the method returns normally; with `x != 0` and normal division, it also runs; if the division throws, `finally` still runs and then the exception continues out. **The exact same log line** does not tell whether the final event is `NORMAL` or `EXCEPTIONAL`.

In Java source, you can design a wrapper using `try`, `catch(Throwable)`, and `finally` with a status variable, but you must be careful:

- If the status variable is set to "success" **before `finally` finishes**, and then `finally` itself throws an exception, the label can be wrong.
- If logging in `finally` throws, it can **override the original exception**.
- With `try-with-resources`, closing resources can change the outcome or add suppressed exceptions.
- Reconstructing exact semantics in bytecode requires more than a single call at the end of `try`.

When measuring **method exit**, confirm the outcome after all related cleanup has actually occurred, following the control flow of the compiled class file.

## 11. How to Preserve Semantics and Reliability for Probes

A good observability agent should have clear invariants:

### 11.1. Do not alter the outcome

- If the original code returns value `v`, the caller must still receive `v`.
- If the original code throws Throwable object `t`, the caller must still receive that exact `t` (unless there is a specific modification policy).
- Advice must not arbitrarily change `null` to another value, swallow exceptions, or wrap a Throwable in a new exception.
- When measuring a `void` method, the outcome can still be `NORMAL` even though there is no return value.

### 11.2. Do not double-count

If a method has a local `athrow` that is caught and then proceeds to `ireturn`, only **one normal exit** must be recorded for that invocation. If the method does not catch and unwinds, only **one exceptional exit** must be recorded for that invocation.

If multiple agents or duplicate advices are registered, events can be duplicated; you must manage instrumentation configuration and invocation identity.

### 11.3. Do not let the probe throw exceptions

In real production systems, avoid complex synchronous logging right at a return or exception handler; it is better to use a lightweight recorder, bounded buffers, sampling, and error handling that does not break the program. A logger error can turn a normal exit into an exceptional exit, corrupting **both** data and application behavior.

Use `Throwable` in observation handlers to cover `Error`s as well, but do not unconditionally **swallow** severe errors such as `OutOfMemoryError`. Distinguish "record and propagate" from "catch and handle".

### 11.4. Correlating enter and exit

Record an ID or context for the invocation, for example:

```text
traceId | invocationId | methodId | outcome | durationNs | errorType
```

Avoid putting `Throwable` or full stack traces as *high cardinality* metric labels. You can record the exception type name in sampled traces/logs, while aggregate metrics use stable labels.

One exception can unwind through **multiple instrumented methods**: each method has **its own exceptional exit** if the exception actually leaves that method's frame. That is **multiple failed invocations**, not throwing multiple different exception objects.

## 12. Limitations to State Clearly: "Every Return" Still Is Not Every Way the JVM Stops

Some special cases:

| Case | Consequence when instrumenting |
|---|---|
| `native` or `abstract` method | No Java bytecode `Code` attribute to hook the return instructions of that method |
| Constructor `<init>` | Constrained by uninitialized `this` before `super(...)`; requires specialized advice logic |
| Class initializer `<clinit>` | Has a `return` opcode on success; initialization failure has special exception semantics |
| `synchronized` method | Monitor must be properly released on normal/abrupt completion |
| `try-with-resources` | Cleanup can throw, replace the primary Throwable, or add suppressed exceptions |
| Reflection, lambda, method handle, bridge method | Must identify which method/class is actually instrumented; do not infer solely from the source name |
| JVM crash, `Runtime.halt`, process kill | No guarantee of receiving a method exit event |
| `System.exit` permitted to terminate the JVM | May stop the process before any return/exceptional hook runs |
| Agent attached after class was loaded | Merely registering a transformer does not transform already-loaded classes; requires retransform/redefine when supported |
| Multiple class loaders/module boundaries | The same method name can have multiple class definitions, so identify by appropriate loader/module |

**Opcode-level probes** must be separated from **Java-source-level probes**. JIT and runtime optimizations may change internal execution, but the bytecode contract and exception paths that the JVM must preserve are the foundation for semantically correct agents. Do not rely on fixed instruction offsets across compiler versions.

Additionally, a long-running method or one that has not returned yet also has no exit yet; having more `enter`s than `normal + exceptional` at a point in time does not automatically prove lost events.

## 13. QA Checklist for a Method-Exit Measuring Agent

Use this table when reviewing instrumentation code:

| Check item | Expectation |
|---|---|
| Covers all six return opcodes? | Includes `IRETURN`, `LRETURN`, `FRETURN`, `DRETURN`, `ARETURN`, `RETURN` |
| Exceptional exits observed? | Has handler/advice covering Throwables **exiting the method** |
| Mistaking local `athrow` for method failure? | No |
| Implicit exceptions from `idiv`/`arraylength`/`invoke*` detected? | Yes, if they actually cause abrupt completion |
| Exception caught inside method then returned? | Recorded as `NORMAL` |
| Exception rethrown to caller? | Recorded as `EXCEPTIONAL` |
| `finally` changes final outcome? | Classified by outcome after cleanup |
| Return value preserved? | Correct for both one-slot and two-slot |
| Original Throwable preserved? | Yes; not swallowed/altered if only measuring |
| New handler breaks original handlers? | No; exception table priority and protected ranges must be correct |
| Risk of recursion or logger throwing? | Safeguards in place |
| Verifier/StackMapTable passes? | Modified class is loaded and tested by the JVM |
| Overloads, bridges, constructors, native methods? | Scope/exceptions documented |
| Observed results match tests? | Covers normal, explicit, implicit, propagated, caught, finally cases |

### Suggested automated test suite

A serious test suite should include at least:

1. Multi-branch `int` with multiple `ireturn`s.
2. `void` method and Object-returning method (`return`/`areturn`).
3. `long` and `double`, ensuring no two-slot stack errors.
4. Uncaught `throw new ...`.
5. Implicit exception `arraylength` on `null`.
6. Implicit exception `idiv` divide by 0.
7. Exception thrown in callee and propagated through caller.
8. Exception caught internally and method returns normally.
9. Exception caught and rethrown.
10. `finally` overriding return, `finally` overriding exception, or suppressed exceptions.
11. Constructors/synchronized/try-with-resources if actually within agent scope.
12. Run with and without the agent; compare result/Throwable type and event counts for **each invocation**.

Simply asserting "the agent runs without crashing" is not enough. What must be proven is that **each in-scope invocation is labeled accurately according to its actual outcome**.

## 14. Review Questions

**Question 1.** How many opcodes are used for normal return in the JVM, and which opcode does `boolean` belong to?

**Answer:** Six: `ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn`, `return`. `boolean` uses `ireturn`.

**Question 2.** A method has `throw` in `try`, `catch` inside, and then `return 9`. Should an exceptional method exit be recorded when `athrow` is seen?

**Answer:** No. The method completes normally with 9; `athrow` is an internal throw event that was handled.

**Question 3.** Does the method `return values.length;` with `values == null` necessarily contain `athrow` in bytecode?

**Answer:** No. The JVM can raise `NullPointerException` at `arraylength`; the method does not reach `ireturn` and has an exceptional exit.

**Question 4.** Method `caller()` only calls `helper()` and returns the result. If `helper()` throws and `caller()` does not catch, is `athrow` needed in `caller()` to measure the failure?

**Answer:** No. The exception propagates through the `caller` frame, causing the invocation to complete abruptly.

**Question 5.** Why is instrumenting only `RETURN` wrong?

**Answer:** `RETURN` is only used for void/initializers; methods returning primitives/references use the other five opcodes.

**Question 6.** Why should a catch-all handler be placed after original handler logic and have its protected region designed carefully?

**Answer:** If the catch-all catches first, an exception that should have been handled by original code will be mislabeled as an exceptional exit, and control flow may be altered.

**Question 7.** If `@Advice.OnMethodExit` does not declare `onThrowable`, which cases does it measure by default?

**Answer:** Only normal method completion. To observe abrupt completion as well, use an appropriate configuration such as `onThrowable = Throwable.class`.

**Question 8.** There are 100 method invocations, of which 10 catch an exception and return normally, and 5 other invocations let an exception propagate out. How many exceptional exits?

**Answer:** 5, assuming all 100 invocations completed and the 5 exceptional ones are five distinct invocations; the 10 caught/returned cases count as normal.

**Question 9.** A method has `return 8` in `try`, but `finally` throws `IllegalStateException`. What is the final event?

**Answer:** `EXCEPTIONAL`; the pending return was replaced by the exception from finally.

**Question 10.** Why can a single `Throwable` lead to multiple `EXCEPTIONAL` method-exit events?

**Answer:** It can unwind sequentially through multiple method frames that do not catch it; each of those invocations terminates abruptly, even though the exception object is one.

## 15. Key Takeaways

- **All normal returns in bytecode have six opcodes**, not one.
- **`athrow` is not an exceptional method exit**: the exception may be caught right inside the same method.
- **An exceptional exit does not necessarily have `athrow` in the method**: the JVM can throw implicitly or an exception from a callee can propagate through.
- Classification must be based on the **final outcome of the invocation** after `catch`, `finally`, cleanup, and unwinding.
- A proper instrumentation design usually needs **normal-return advice + exceptional-exit advice/handler**, not just inserting logging at `return`.
- Maintaining correctness of the stack, exception table, verifier, constructor/monitor semantics, and original Throwable is mandatory.
- The Java 17+ example together with `javap` helps verify both exit path groups before deploying a real agent.

## References

- Oracle Java SE 17, [The Java Virtual Machine Specification — Normal and Abrupt Method Invocation Completion (§2.6.4–§2.6.5)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html).
- Oracle Java SE 17, [The Java Virtual Machine Specification — Method Invocation and Return Instructions (§2.11.8)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.8).
- Oracle Java SE 17, [The Java Virtual Machine Specification — Instruction Set, including `athrow` and return opcodes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html).
- Oracle Java SE 17, [Exception handlers and their search order (§2.10)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.10).
- Oracle Java SE 17, [The Java Language Specification — Exceptions and handling](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html).
- Byte Buddy, [`Advice.OnMethodExit` — `onThrowable` behavior](https://javadoc.io/static/net.bytebuddy/byte-buddy/1.18.2/net/bytebuddy/asm/Advice.OnMethodExit.html).
- Byte Buddy, [`Advice.Thrown` — observed thrown value or null](https://javadoc.io/static/net.bytebuddy/byte-buddy/1.18.2/net/bytebuddy/asm/Advice.Thrown.html).
