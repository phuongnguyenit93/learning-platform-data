# Timing Methods for Both Return Paths and Exception-Throwing Paths

## 1. Experiment Goal: Every Invocation Has Exactly One Completion

When a Java agent measures method execution time, **inserting a measurement point only before `return` is not enough**. A method can exit via a normal `return`, but it can also throw an exception explicitly (`throw`), throw an implicit exception from the JVM (such as division by zero, `NullPointerException`), or receive an exception from a method called inside it.

This experiment belongs to the **Agent Practice** group. We will build a **Java agent using the Class-File API on JDK 24** to insert:

- `TimingProbe.enter()` at the start of the method, recording the `System.nanoTime()` timestamp;
- `TimingProbe.success()` immediately before every `return` instruction;
- `TimingProbe.failure()` in a **catch-all exception handler** covering the method body, followed by `athrow` to rethrow **the exact original Throwable**.

We actually compile, run the agent with `-Xverify:all`, invoke both exit paths, and verify the instructions and exception table using `javap` and an **independent** Class-File API tool.

**Results to prove:**

1. A normal call to `Calculator.evaluate(4)` returns **25** and is recorded as `RETURN`.
2. `evaluate(-1)` throws `IllegalArgumentException` written explicitly in code; it is recorded as `THROW` and the caller still catches the exact exception.
3. `evaluate(0)` throws `ArithmeticException` when the `idiv` bytecode executes; **there is no `athrow` instruction written in Java source on this branch**, yet the catch-all still records `THROW`.
4. Three invocations produce **3 enter, 1 return, 2 throw**, with no pending `ThreadLocal` frames left behind; total duration is computed from the JVM's monotonic clock.
5. Bytecode **before** instrumentation has no hooks; the **after** version has exactly 1 `enter`, 1 `success`, 1 `failure`, and 1 catch-all handler.
6. Execution with `java -Xverify:all -javaagent:...` succeeds, while both return values and exception types are preserved in the test.

**Scope limit:** this experiment chooses **a single static method returning `int`**, not a constructor or native method. This tested code is not yet a framework for automatically instrumenting arbitrary classes, arbitrary exception-handler layouts, or all JDK versions. Points needed for production are explained separately without hiding them.

## 2. Why Is "Counting RETURN" Not Enough?

Consider the method:

~~~java
public static int evaluate(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("negative");
    }
    return 100 / n;
}
~~~

This is **an illustrative Java method**, whose complete file will appear in Section 7. Three invocations:

| Call | Execution path | Result |
| --- | --- | --- |
| `evaluate(4)` | `100 / 4` → `ireturn` | Returns `25` |
| `evaluate(-1)` | Creates exception → `athrow` | Throws `IllegalArgumentException` |
| `evaluate(0)` | `idiv` divides by 0 → JVM raises exception | Throws `ArithmeticException` |

If we only transform `ReturnInstruction`:

~~~text
method entry -> start timer
...
when seeing IRETURN -> record elapsed

evaluate(4)  -> recorded
evaluate(-1) -> does not go through IRETURN
evaluate(0)  -> JVM throws at IDIV, does not go through IRETURN
~~~

The "entered method" counter increments by 3, while "finished" increments by only 1. If start-time is stored in `ThreadLocal`, the two failing entries can also **leak context**, corrupting the duration of subsequent calls.

It is also not enough to only place probes before existing `ATHROW` instructions: exceptions can arise at `idiv`, `getfield`, `invokevirtual`, array accesses, or child methods. **An exception handler covering the code range** is the appropriate mechanism to catch cases where an exception *escapes the method scope*, without needing to predict every opcode that can fail.

### 2.1. "Throw" Means Escaping the Method, Not Every `throw` Counts as a Failure

A method may throw `IOException` and then **catch and handle** it internally, ultimately returning normally. When the goal is **method-exit outcome**, an internally handled exception must not be counted as a failed exit.

~~~java
try {
    operation();
} catch (RecoverableException e) {
    recover();
}
return normalResult;
~~~

This is **Java pseudocode**; the methods are not declared. The method's outcome is `RETURN` if the exception was handled and the method returns normally. To preserve this semantics, a catch-all added after existing handlers must respect the **order and ranges of the exception table**; do not arbitrarily turn every internal exception into `THROW`.

### 2.2. Normal Return Also Has Multiple Opcodes

In the JVM, a method can end with `RETURN` (void), `IRETURN` (int/boolean/byte/char/short), `LRETURN`, `FRETURN`, `DRETURN`, or `ARETURN`. The JDK 24 Class-File API provides the `ReturnInstruction` type to identify this group.

Filtering specifically for **`ReturnInstruction`** is better than searching only for the string `"return"` in source or only looking for `ARETURN`. However, inserting a hook before a return that has a value on the operand stack still requires the hook's stack effect to be compatible. This article chooses `success():void` **with no parameters**, so the static call neither pops nor alters the `int` value waiting on the stack.

## 3. Measurement Model: Entry, Success Exit, Exceptional Exit

~~~text
   JVM defines Calculator.evaluate
             |
             v
      TimingProbe.enter()
      push startNano onto per-thread stack
             |
             v
       Original method body
       /               \
   return                Throwable escapes
      |                         |
      v                         v
success()                 catch-all handler
  pop start                     |
  record elapsed                v
      |                    failure()
      v                      pop start
return value intact        record elapsed
                                  |
                                  v
                               athrow
                           same original Throwable
~~~

Approximate equivalent in Java source (to **explain semantics**, **not** source that the transformer generates via `javac`):

~~~java
TimingProbe.enter();
try {
    int value = originalEvaluate(n);
    TimingProbe.success();
    return value;
} catch (Throwable error) {
    TimingProbe.failure();
    throw error;
}
~~~

This is **pseudocode**: `originalEvaluate` is not declared in the file. The transformer in Section 9 actually **preserves the method's code elements**, inserts the hook before `ireturn`, and adds an exception table handler.

An important note: the pseudocode above places `success()` inside the `try` region. If the `success()` helper itself throws an error, the catch-all could subsequently invoke `failure()`, altering the outcome. The experiment uses a very simple, tested helper, **not a guarantee that the helper is infallible**. In production, the probe should be designed with fail-open protection to avoid telemetry errors masking business errors or causing double counting.

## 4. Choosing a Time Source and Defining Latency

Use `System.nanoTime()` to compute **elapsed time within the same JVM**:

~~~java
long start = System.nanoTime();
try {
    doWork();
} finally {
    long elapsedNanos = System.nanoTime() - start;
    record(elapsedNanos);
}
~~~

This is a **code snippet** assuming `doWork` and `record` exist. `nanoTime` is designed to compare **time differences**, not wall-clock calendar timestamps. Do not convert `nanoTime` to `Instant`, and do not compare `nanoTime` values across different JVMs/processes.

In a short invocation, `elapsedNanos` is normally non-negative; the JDK documentation notes that subtraction in this form can be used when the measured interval is smaller than the representable range of signed `long`. The value is **elapsed wall-clock/monotonic time**, including time the method was paused by the scheduler, waiting on locks/I/O/GC, and probe overhead—**not pure CPU time**.

| Metric | Definition | What not to infer |
| --- | --- | --- |
| Elapsed nanos | `nanoTime(exit) - nanoTime(entry)` | Does not automatically separate CPU, I/O, or lock time |
| Method invocation count | Number of entries into the instrumented method | Does not automatically represent system-wide request count |
| Success count | Number of invocations leaving the method via return | Not necessarily HTTP/business success |
| Throw count | Number of invocations escaping via Throwable | Not synonymous with total exceptions created/caught inside the method |
| Duration sum | Sum of elapsed time of completed invocations | Not process-wide wall-clock time when concurrency/nesting exists |
| Time histogram | Distribution of duration across buckets | Requires cardinality limits and sampling constraints |

A method returning normally can still return `null` or a business error code. **Method-exit outcome** differs from domain-level "success/failure" semantics. This article counts `RETURN`/`THROW` by **JVM control flow**; it does not classify HTTP 500 or a `false` return value as `THROW`.

## 5. Why Use JDK 24 for the Agent in This Article?

Java has had `java.lang.instrument` for a long time, but starting in **JDK 24**, `java.lang.classfile` was standardized (JEP 484). This API lets you parse, build, and transform class-file bytes directly without ASM or Byte Buddy.

**Experiment requirements:**

| Component | Version / condition |
| --- | --- |
| Compile agent/app/verifier | **JDK 24** with `javac --release 24` |
| Execution | **JDK 24** JVM, with `-javaagent` and `-Xverify:all` |
| Class-File API | `java.lang.classfile.*` in `java.base` |
| Java agent API | `java.lang.instrument` in `java.instrument` |
| Dependencies | No external bytecode libraries outside the JDK |
| Loading mechanism | `premain` at startup, transforming only **initial class definition** |
| Target class | `demo/app/Calculator`, method `evaluate(int):int` |

JDK 17 or JDK 21 **does not have the standard Class-File API under this package**. An application doing manual timing with `try/finally` can compile on Java 17, but **the Java agent code using `java.lang.classfile` in this article requires JDK 24**.

`ClassFile.of().parse(byte[])` creates a `ClassModel`; `ClassFile.transformClass(model, ClassTransform)` produces a new class byte array. `CodeTransform` processes each `CodeElement`, where `ReturnInstruction` represents a normal exit instruction. `CodeBuilder.exceptionCatchAll(start,end,handler)` adds an exception table entry catching any `Throwable` escaping the specified range.

**Not every bytecode transformation is accepted by the JVM**. The demo is tested under `-Xverify:all`, but extending it to code with existing handlers, stack maps, constructors, or `synchronized` requires dedicated verification.

## 6. Project File Structure

~~~text
method-time-agent/
  agent-src/demo/agent/
    TimingAgent.java
    TimingProbe.java
  app-src/demo/app/
    Calculator.java
    Main.java
  tool-src/
    VerifyTiming.java
  MANIFEST.MF
  agent-classes/       (generated by javac)
  app-classes/         (generated by javac)
  tool-classes/        (generated by javac)
  timing-agent.jar     (generated by jar)
  transformed/
    demo/app/Calculator.class  (dump for verification only)
~~~

**Responsibilities of each component:**

- `Calculator`: business method with one normal return, one explicit throw, and one implicit throw.
- `Main`: invokes all three paths, catches both exceptions at the caller, and prints the helper's counters.
- `TimingProbe`: per-thread stack of start times, measures duration, classifies `RETURN`/`THROW`, and cleans up `ThreadLocal` after the last exit.
- `TimingAgent`: receives `Instrumentation` and inserts entry/return/exception-handler hooks using the JDK Class-File API.
- `VerifyTiming`: reads **both the original and transformed versions** via a separate program; confirms the exact invocations and catch-all entry.

The `transformed/...` file is only **dumped** by the agent for use with `javap` and the independent verifier. The JVM **does not need a dump file** to load the class: the transformer returns `byte[]` directly. Do not copy synchronous disk writes inside the callback into production.

## 7. Application Code: One Normal Return and Two Exception Types

**File `app-src/demo/app/Calculator.java`**

~~~java
package demo.app;

public final class Calculator {
    public static int evaluate(int n) {
        if (n < 0) throw new IllegalArgumentException("negative");
        return 100 / n;
    }
}
~~~

**File `app-src/demo/app/Main.java`**

~~~java
package demo.app;
import demo.agent.TimingProbe;

public final class Main {
    public static void main(String[] args) {
        System.out.println("result=" + Calculator.evaluate(4));
        try {
            Calculator.evaluate(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("caught=" + expected.getClass().getSimpleName());
        }
        try {
            Calculator.evaluate(0);
        } catch (ArithmeticException expected) {
            System.out.println("caught=" + expected.getClass().getSimpleName());
        }
        TimingProbe.summary();
    }
}
~~~

Neither of these files **ever calls `TimingProbe.enter/success/failure`**. `Main` only reads `summary()` to verify the results after the business calls. This proves the measurement points were inserted by the agent.

`evaluate(-1)` constructs an `IllegalArgumentException` and uses `athrow`; `evaluate(0)` executes `idiv` and **the JVM creates `ArithmeticException`**. The second case is the decisive test: adding hooks only before existing `athrow` instructions would **not** be enough to catch this exit path.

## 8. Helper to Store Start-Time and Measure Full Duration

**File `agent-src/demo/agent/TimingProbe.java`**

~~~java
package demo.agent;

import java.util.ArrayDeque;
import java.util.concurrent.atomic.AtomicLong;

public final class TimingProbe {
    private static final ThreadLocal<ArrayDeque<Long>> START =
            ThreadLocal.withInitial(ArrayDeque::new);
    private static final AtomicLong ENTERED = new AtomicLong();
    private static final AtomicLong RETURNED = new AtomicLong();
    private static final AtomicLong THROWN = new AtomicLong();
    private static final AtomicLong NANOS = new AtomicLong();

    public static void enter() {
        START.get().push(System.nanoTime());
        ENTERED.incrementAndGet();
    }

    public static void success() {
        finish(false);
    }

    public static void failure() {
        finish(true);
    }

    private static void finish(boolean failed) {
        ArrayDeque<Long> stack = START.get();
        long elapsed = System.nanoTime() - stack.pop();
        if (stack.isEmpty()) START.remove();
        NANOS.addAndGet(elapsed);
        if (failed) THROWN.incrementAndGet();
        else RETURNED.incrementAndGet();
        System.out.println("probe.exit="
                + (failed ? "THROW" : "RETURN"));
    }

    public static void summary() {
        System.out.println("probe.entered=" + ENTERED.get());
        System.out.println("probe.returned=" + RETURNED.get());
        System.out.println("probe.thrown=" + THROWN.get());
        System.out.println("probe.timeCaptured=" + (NANOS.get() > 0));
    }
}
~~~

### 8.1. Why Use `ThreadLocal<ArrayDeque<Long>>`?

A shared `static long start` is **incorrect** when multiple threads call concurrently; thread A could overwrite thread B's timestamp. A `ThreadLocal<Long>` solves cross-thread sharing but is **still insufficient** for recursion and nesting on the same thread: an inner call would overwrite the outer call's start time.

This article uses **a separate stack per thread**:

~~~text
Thread T1:
  enter outer -> stack [startOuter]
  enter inner -> stack [startInner, startOuter]
  exit inner  -> pop startInner
  exit outer  -> pop startOuter
  stack empty -> ThreadLocal.remove()

Thread T2:
  has an independent stack, never touches T1's data
~~~

This is a **conceptual diagram**, not a direct trace of the demo (the demo has no nested calls). If recursion occurs, each instrumented invocation pushes/pops one frame, provided every enter has exactly one exit and no helper error breaks the stack.

### 8.2. Why Call `remove()` When the Stack Is Empty?

Thread pools reuse threads across many requests. An uncleaned `ThreadLocal` can retain expired objects, causing memory retention or exposing stale context to a subsequent request. Once the last frame is popped, `START.remove()` clears the value from the current thread.

**Important:** `ThreadLocal` is only valid when **the same thread** executes both enter and exit. If a method returns a `CompletableFuture` and work continues on another thread, the duration at the method boundary **does not** represent the end-to-end async operation. Different context propagation and lifecycle tracking are needed.

### 8.3. Why `AtomicLong`?

`AtomicLong` keeps counters and total nanoseconds thread-safe under concurrent calls. The demo prints deterministic values on a single thread. In very high-load applications, `LongAdder` can reduce contention for counters, and a histogram is usually more useful than a single sum; however, reading multiple `LongAdder.sum()` calls concurrently **does not** produce an atomic snapshot.

`NANOS.get() > 0` in stdout is a test assertion confirming positive elapsed time was captured on the test JVM, **not** an SLO or an exact duration value applicable to every machine. Avoid hardcoding actual nanosecond numbers because OS scheduling, JIT, and GC vary across runs.

### 8.4. Helper Overhead and Safety

The helper here prints `System.out.println` on every exit **purely for observability**. This is not a production solution: synchronous logging can spike tail latency, trigger logger class loading, cause recursion, and create bottlenecks.

In a real environment, you need to:

- Check enable/sampling flags before building heavy payloads.
- Never turn telemetry errors into business errors; especially avoid masking the original `Throwable`.
- Bound queue/exporter memory and label counts to prevent cardinality explosion.
- Avoid instrumenting `TimingProbe` itself, the agent, the logger, or the exporter.
- Use an appropriate duration histogram instead of printing every method call.

## 9. Transformer: Creating Exactly Three Hooks and One Catch-All Handler

**File `agent-src/demo/agent/TimingAgent.java`**, complete code compiled and run successfully on JDK 24:

~~~java
package demo.agent;

import java.lang.classfile.*;
import java.lang.classfile.instruction.ReturnInstruction;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TimingAgent {
    private static final ClassDesc PROBE =
            ClassDesc.of("demo.agent.TimingProbe");
    private static final MethodTypeDesc NO_ARGS_VOID =
            MethodTypeDesc.ofDescriptor("()V");

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new TimerTransformer(), false);
        System.out.println("agent=installed");
    }

    private static final class TimerTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(ClassLoader loader, String className,
                Class<?> redefining, ProtectionDomain domain, byte[] bytes) {
            if (!"demo/app/Calculator".equals(className)) return null;

            ClassFile cf = ClassFile.of();
            CodeTransform timer = CodeTransform.ofStateful(() ->
                    new CodeTransform() {
                Label from;
                Label to;
                Label handler;

                @Override
                public void atStart(CodeBuilder out) {
                    from = out.newLabel();
                    to = out.newLabel();
                    handler = out.newLabel();
                    out.invokestatic(PROBE, "enter", NO_ARGS_VOID);
                    out.labelBinding(from);
                }

                @Override
                public void accept(
                        CodeBuilder out, CodeElement element) {
                    if (element instanceof ReturnInstruction) {
                        out.invokestatic(PROBE, "success", NO_ARGS_VOID);
                    }
                    out.with(element);
                }

                @Override
                public void atEnd(CodeBuilder out) {
                    out.labelBinding(to);
                    out.labelBinding(handler);
                    out.invokestatic(PROBE, "failure", NO_ARGS_VOID);
                    out.athrow();
                    out.exceptionCatchAll(from, to, handler);
                }
            });

            byte[] transformed = cf.transformClass(cf.parse(bytes),
                    ClassTransform.transformingMethodBodies(
                        method -> method.methodName()
                                .equalsString("evaluate"),
                        timer));

            try {
                Path path = Path.of(
                        "transformed/demo/app/Calculator.class");
                Files.createDirectories(path.getParent());
                Files.write(path, transformed);
            } catch (java.io.IOException ex) {
                throw new RuntimeException(ex);
            }

            System.out.println("agent.transformed=" + className);
            return transformed;
        }
    }
}
~~~

### 9.1. `atStart`: Record Start Time, Then Start the Protected Region

~~~java
out.invokestatic(PROBE, "enter", NO_ARGS_VOID);
out.labelBinding(from);
~~~

This is **a snippet from the transformer**. `TimingProbe.enter()` runs at the beginning of the method; then the `from` label marks the **start of the catch-all range**. This means if **`enter()` itself throws an error**, that exception does not enter the handler added by the transform. This article does not claim the helper cannot fail; production code needs appropriate handling.

`ClassDesc.of("demo.agent.TimingProbe")` uses **dot-separated binary name**; the `className` callback compares against the **slash-separated internal name** `demo/app/Calculator`. Do not mix up the two formats.

### 9.2. `accept`: Insert Before Every Normal Return, Preserve Original Code

~~~java
if (element instanceof ReturnInstruction) {
    out.invokestatic(PROBE, "success", NO_ARGS_VOID);
}
out.with(element);
~~~

`ReturnInstruction` represents the family of `return` instructions by return value type. In the demo method returning `int`, that is `ireturn`. The `invokestatic` call to `success():()V` **consumes no arguments and returns no value**, so the `int` already on the operand stack remains intact for `ireturn`.

**Note:** this explanation applies to the demo method and the specific `()V` helper. If you change the helper to `success(long)`, you must push the start time onto the stack in the right position and check stack-map frames. If you want to pass the `int` result, you must know how to store/load the value to preserve the operand stack.

`out.with(element)` preserves all original code elements. If omitted, the transformer would drop instructions and break the method. If you only add `success` before return without a catch-all, every invocation that throws an exception will still be missed.

### 9.3. `atEnd`: Create a Handler for Any Escaping Exception

~~~java
out.labelBinding(to);
out.labelBinding(handler);
out.invokestatic(PROBE, "failure", NO_ARGS_VOID);
out.athrow();
out.exceptionCatchAll(from, to, handler);
~~~

This is **a snippet from the transformer**. The two labels `to`/`handler` mark the end of the original code range and the entry point of the handler. `exceptionCatchAll(from, to, handler)` creates an entry in the exception table with catch type **any**, rather than catching only `IllegalArgumentException`.

When an internally unhandled `Throwable` escapes from the method body:

1. The JVM places the **thrown Throwable** on top of the operand stack upon entering the handler.
2. `failure():()V` is invoked without popping the `Throwable` from the stack.
3. `athrow` rethrows **the exact same Throwable object**. The demo still preserves the exact subtypes `IllegalArgumentException` and `ArithmeticException` at the caller.

**Important:** this handler catches exceptions raised by `idiv`, not just visible `athrow` instructions in the class. That is why Section 7 includes both explicit and implicit exceptions.

### 9.4. Why `CodeTransform.ofStateful`?

The three labels `from`, `to`, and `handler` belong to **a single method body**. `CodeTransform.ofStateful(() -> new CodeTransform() {...})` creates a transform instance with dedicated state per traversal, avoiding accidentally reusing labels across multiple methods.

The example selects only one method, but this is the right pattern when scaling up. Do not store labels in a static field shared across concurrent transformations.

### 9.5. Experiment Scope and What Not to Overgeneralize

The transformer filters by `className=="demo/app/Calculator"` and `methodName()=="evaluate"`. The demo class has **one** `evaluate`, with no overloads, constructors, or native body.

In a real agent, you also need to filter by the exact descriptor, such as `(I)I`, and check method flags. If a method has original exception handlers, the design must preserve priority order, labels/ranges, stack maps, and exceptional execution paths. **Do not** blindly insert a catch-all ahead of original handlers, which would alter the semantics of exceptions handled by the method itself.

`Files.write` in the transformer is a **test-only dump**; production should remove synchronous I/O during class loading. `transform` returns a new byte array without mutating the `classfileBuffer` passed by the JVM.

## 10. Creating the Manifest and Compiling

**File `MANIFEST.MF`**

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.TimingAgent

~~~

The manifest has a trailing blank line ending the main attributes section. The class name `demo.agent.TimingAgent` must match; the JVM invokes `premain` before application `main`.

**From the `method-time-agent` directory, on Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force agent-classes, app-classes, tool-classes | Out-Null

javac --release 24 -d agent-classes agent-src/demo/agent/TimingAgent.java agent-src/demo/agent/TimingProbe.java

jar --create --file timing-agent.jar --manifest MANIFEST.MF -C agent-classes .

javac --release 24 -cp timing-agent.jar -d app-classes app-src/demo/app/Calculator.java app-src/demo/app/Main.java

java -cp "app-classes;timing-agent.jar" demo.app.Main

java -Xverify:all -javaagent:timing-agent.jar -cp "app-classes;timing-agent.jar" demo.app.Main
~~~

The first command creates the directories; `javac` produces `.class` files; `jar` packages all agent and helper classes; the application needs `timing-agent.jar` on the classpath to call `TimingProbe.summary()`.

**On Bash/Linux/macOS:** the directory creation command is `mkdir -p agent-classes app-classes tool-classes` and the classpath separator is `:`:

~~~bash
mkdir -p agent-classes app-classes tool-classes
javac --release 24 -d agent-classes \
  agent-src/demo/agent/TimingAgent.java \
  agent-src/demo/agent/TimingProbe.java
jar --create --file timing-agent.jar --manifest MANIFEST.MF \
  -C agent-classes .
javac --release 24 -cp timing-agent.jar -d app-classes \
  app-src/demo/app/Calculator.java app-src/demo/app/Main.java
java -cp "app-classes:timing-agent.jar" demo.app.Main
java -Xverify:all -javaagent:timing-agent.jar \
  -cp "app-classes:timing-agent.jar" demo.app.Main
~~~

Do not use `--add-exports` or `--enable-preview` to "enable" the Class-File API in JDK 24: the standard `java.lang.classfile` package is already built in. `Can-Retransform-Classes` is also unnecessary because this article only registers an initial-load transformer `addTransformer(..., false)` without retransforming already-loaded classes.

### 10.1. Why Are Two Runs Needed?

- **Without `-javaagent`:** the `Calculator` class runs unmodified; `Probe` receives no entry/exit because `Calculator` source contains no helper calls.
- **With `-javaagent`:** the JVM calls `premain` before `Calculator` is loaded, and the transformer returns class bytes with the hooks and exception table added.
- `-Xverify:all` instructs the JVM to verify bytecode more strictly during the test, useful for catching invalid output.
- Running in **two separate JVM processes** avoids loaded/transformed class state from the previous run. You cannot arbitrarily "unload `Calculator` and reload it" with a `Class.forName` call in the same loader.

## 11. Exact Execution Output on Zulu/OpenJDK 24.0.2

### 11.1. Baseline Without Agent

~~~text
result=25
caught=IllegalArgumentException
caught=ArithmeticException
probe.entered=0
probe.returned=0
probe.thrown=0
probe.timeCaptured=false
~~~

This is the output of `java -cp ... demo.app.Main`, with the helper on the classpath but no transformer. `Calculator.evaluate` still returns the right value and throws both exceptions; all counters are **0**.

### 11.2. With Agent

~~~text
agent=installed
agent.transformed=demo/app/Calculator
probe.exit=RETURN
result=25
probe.exit=THROW
caught=IllegalArgumentException
probe.exit=THROW
caught=ArithmeticException
probe.entered=3
probe.returned=1
probe.thrown=2
probe.timeCaptured=true
~~~

**Tested:** compiled with `javac --release 24`, packaged into the agent JAR, and run with `java -Xverify:all -javaagent:...` on Zulu/OpenJDK **24.0.2**. The stdout lines above match the experiment's exact output.

Analysis:

1. `agent=installed` appears before business calls because `premain` runs at startup.
2. `agent.transformed=demo/app/Calculator` shows the transformer touched only the target class, not the helper or logger.
3. `probe.exit=RETURN` appears **before** `result=25`, because the code inside `evaluate` invokes the helper before returning to the caller.
4. `probe.exit=THROW` before `caught=IllegalArgumentException` means the helper in the exception handler runs **before the Throwable is rethrown** to the caller.
5. `probe.exit=THROW` before `caught=ArithmeticException` proves the catch-all also handles exceptions from `idiv`.
6. `entered=3`, `returned=1`, `thrown=2`, and `timeCaptured=true`: all three invocations recorded entry/exit along their respective paths.

**Do not hardcode a specific duration** in stdout. Across runs, `elapsed nanoseconds` varies. The boolean `timeCaptured=true` is the test output in this environment, not a guarantee that duration is `> 0` for every method on every OS or timer resolution.

### 11.3. Accounting Invariant

After all invocations finish normally at the Java control-flow level:

~~~text
entered = returned + thrown
3       = 1        + 2
~~~

This invariant holds in the **single-threaded demo**, where every method exit passes completely through the helper. In production, helper errors, process crashes, `System.exit`/`Runtime.halt`, in-flight frames, sampling, queue drops, or races when reading multiple counters can cause a point-in-time observation not to match.

Do not use this equality to claim "no end-to-end telemetry loss": the helper's counters can still increment even if the exporter fails to send data. **Instrumented method counters** and **records received by the backend** must be tracked separately.

## 12. `javap`: Return Bytecode and Exception Table After Transformation

After running the agent, the test dump is located at:

~~~text
transformed/demo/app/Calculator.class
~~~

Run:

~~~bash
javap -c -p -classpath app-classes demo.app.Calculator
javap -c -p -classpath transformed demo.app.Calculator
~~~

**Excerpt of `evaluate` after transformation**, verified:

~~~text
public static int evaluate(int);
  Code:
     0: invokestatic  #27   // Method demo/agent/TimingProbe.enter:()V
     3: iload_0
     4: ifge          17
     7: new           #7    // class java/lang/IllegalArgumentException
    10: dup
    11: ldc           #9    // String negative
    13: invokespecial #11  // Method ...<init>:(Ljava/lang/String;)V
    16: athrow
    17: bipush        100
    19: iload_0
    20: idiv
    21: invokestatic  #30   // Method demo/agent/TimingProbe.success:()V
    24: ireturn
    25: invokestatic  #33   // Method demo/agent/TimingProbe.failure:()V
    28: athrow
  Exception table:
     from    to  target type
        3    25    25   any
~~~

Some long `javap` comments have been shortened for readability; **opcodes, offsets, and the exception table** are kept as observed in the test run. Constant-pool indexes `#27/#30/#33` are compiler/transformer build details, **not values to hardcode** when writing a cross-environment verifier.

Reading the output:

- Offset **0**: the `enter` call is added before the original instructions.
- Offset **21**: the `success` call is inserted before `ireturn`.
- Offset **25**: the new handler invokes `failure`.
- Offset **28**: `athrow` rethrows the caught `Throwable`.
- Exception table: range from **3 (inclusive)** to **25 (exclusive)**; the handler catches any `Throwable` type at offset **25**.
- `idiv` at offset 20 lies inside the catch-all range. On division by zero, the JVM transfers control to the handler even though the instruction at 20 **is not `athrow`**.

**Two important notes:** the catch-all range starts **after** `enter()`; exceptions thrown by the entry hook itself are not covered by this handler. It also covers `success()` inserted before return; therefore an error from the success hook can enter the handler and trigger unexpected measurement logic. That is why production helpers must have fail-open/error isolation and exception-semantics tests, not just "build succeeds."

## 13. Independent Verifier Using the Class-File API

Checks from the transformer itself or stdout logs are useful, but not sufficient. We create **another program** that reads both `.class` files and independently counts invocations and exception handlers.

**File `tool-src/VerifyTiming.java`**

~~~java
import java.lang.classfile.*;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.nio.file.Files;
import java.nio.file.Path;

public final class VerifyTiming {
    private static final ClassDesc PROBE =
            ClassDesc.of("demo.agent.TimingProbe");

    private static void verify(String label, Path path) throws Exception {
        ClassModel model = ClassFile.of()
                .parse(Files.readAllBytes(path));
        MethodModel method = model.methods().stream()
                .filter(m -> m.methodName().equalsString("evaluate"))
                .findFirst().orElseThrow();
        CodeModel code = method.code().orElseThrow();

        for (String name : new String[] {
                "enter", "success", "failure"}) {
            long n = code.elementStream()
                    .filter(e -> e instanceof InvokeInstruction call
                            && call.opcode() == Opcode.INVOKESTATIC
                            && call.owner().asSymbol().equals(PROBE)
                            && call.name().equalsString(name)
                            && call.typeSymbol()
                                    .descriptorString().equals("()V"))
                    .count();
            System.out.println(label + "." + name + "=" + n);
        }

        long all = code.exceptionHandlers().stream()
                .filter(e -> e.catchType().isEmpty()).count();
        System.out.println(label + ".catchAll=" + all);
    }

    public static void main(String[] args) throws Exception {
        verify("original",
                Path.of("app-classes/demo/app/Calculator.class"));
        verify("transformed",
                Path.of("transformed/demo/app/Calculator.class"));
    }
}
~~~

**Commands to run after running the agent and obtaining the dump:**

~~~bash
javac --release 24 -d tool-classes tool-src/VerifyTiming.java
java -cp tool-classes VerifyTiming
~~~

**Exact tested stdout:**

~~~text
original.enter=0
original.success=0
original.failure=0
original.catchAll=0
transformed.enter=1
transformed.success=1
transformed.failure=1
transformed.catchAll=1
~~~

The program checks **opcode, owner class, method name, and descriptor `()V`**, rather than just searching for `"TimingProbe"` in the constant pool. A class could contain the helper name as metadata/string without any instruction actually calling the helper. For `exceptionHandlers()`, `catchType().isEmpty()` identifies a catch-all entry, distinct from a handler that catches only a specific exception subtype.

**Verification limit:** this is a structural assertion. It does not measure actual duration or prove there is exactly one event for every JVM failure scenario; running `-Xverify:all` and testing normal/error paths form the complementary layer.

## 14. Verifying Exception Types and Preserving Semantics

A timing agent must not alter business semantics. In the demo:

~~~text
Before agent:
  evaluate(4)  -> int 25
  evaluate(-1) -> IllegalArgumentException
  evaluate(0)  -> ArithmeticException

With agent:
  evaluate(4)  -> int 25 + RETURN record
  evaluate(-1) -> IllegalArgumentException + THROW record
  evaluate(0)  -> ArithmeticException + THROW record
~~~

These are **tested** behaviors, not inferred from successful classfile parsing. `athrow` in the handler reuses the `Throwable` already on the operand stack, so it never constructs a different exception.

### 14.1. Why Not Catch Only `Exception`?

`catch (Exception)` covers many checked/unchecked exceptions but **does not cover all `Error`s**. If the goal is to measure a method exiting via any `Throwable`, the JVM's catch-all exception table (`any`) is more appropriate.

However, **recording** an `Error` in the helper does not mean **swallowing it**. The agent must avoid turning `OutOfMemoryError` or `StackOverflowError` into a successful return. Preserve the original `Throwable` and let the JVM/caller handle it under normal semantics, if sufficient resources remain.

### 14.2. Why Are Throws in Child Methods Also Counted?

Suppose:

~~~java
public static int parent() {
    return dependency.compute();
}
~~~

This is a **code snippet** with an undefined `dependency`. If `compute()` throws a `Throwable` that `parent` **does not catch**, the exception escapes across `parent`'s method boundary; `parent`'s catch-all will record `THROW`. If `parent` catches it and returns a value, `parent` is recorded as `RETURN`.

If **both parent and child** are instrumented, an error propagating from child to parent can produce **two method-exit THROW records**. This is accurate when the unit of measurement is each method's **invocation**, though it is not "two independent business errors." Distinguish **exception object**, **throw propagation**, and **method invocation outcome**.

## 15. Stack/Time Techniques Safe for Nesting and Recursion

A `ThreadLocal` stack separates invocations on the same thread:

~~~text
T1: enter outer at 100
T1: enter inner at 130
T1: exit inner at 145 (duration 15)
T1: exit outer at 190 (duration 90)

Sum of inclusive durations = 105,
not thread T1's wall-clock 90.
~~~

This is **an illustrative numerical example**, not real `nanoTime` values. Summing inclusive durations of nested methods can **double-count** inner intervals. To get **exclusive time**, you need a different mechanism that subtracts child time or accumulates segments as nested calls start and finish.

**Recursion case:** each recursive call creates its own frame—same method name, different invocation. If you only store a single `ThreadLocal<Long>`, the outer start time would be overwritten by the inner call. That is why the helper uses `ArrayDeque<Long>`.

**Async case:** `CompletableFuture`, thread pools, reactive pipelines, and callbacks can switch threads. `ThreadLocal` only describes **the Java method call boundary on the current thread**; if a method returns a `Future` before computation finishes, the measured time stops when the `Future` is returned, not when the `Future` completes. End-to-end latency requires attaching context to the async operation's lifecycle, rather than using a per-thread method timer and labeling it "total request time."

**Stack-skewing exception case:** if a success/failure hook fails to run, a frame can be left behind. `START.remove()` when the stack is empty cannot automatically clean up a frame that was never popped. This requires testing all exit paths and guarding against helper failures in production.

## 16. Limitations of the Example and Methods Requiring Special Handling

| Method kind | Why it cannot be applied verbatim | Required checks |
| --- | --- | --- |
| Simple `public static int evaluate(int)` | **Tested demo**, one `IRETURN` and one catch-all | Both return, explicit/implicit throws, verifier |
| `void`/`long`/`double`/object return | Different return opcodes and stack values | Proper `ReturnInstruction`, helper preserves stack |
| `<init>` constructor | `this` is uninitialized, verifier is strict | Do not insert arbitrary helpers before super/this init; choose insertion point |
| `<clinit>` | Class initialization order, helper may load more classes | Guard reentrancy and circular initialization |
| `native`/`abstract` | No `Code` attribute in the method itself | Instrument Java caller/wrapper or use native/JVMTI tools |
| Synchronized method/block | Holds monitor, exception flow, and overhead | Avoid blocking I/O, preserve monitor semantics |
| Methods with multiple catch/finally | Exception table order/ranges affect semantics | Test caught vs uncaught, propagation, labels/stack maps |
| Multiple returns/overloads | Name-only matcher can be too broad | Filter descriptor, test every return opcode |
| Methods with invokedynamic/lambda | Additional call stack and class loading complexity | Test bootstrap/class visibility |
| Bridge/synthetic | Can cause double counting | Understand method flags and sampling intent |
| Very frequently called methods | High probe overhead | Sampling, bounded queue, low-allocation helper |
| Instrumented JDK classes | Agent helper can cause recursion/circularity | Exclude or design a minimal bootstrap bridge |
| Already-loaded classes | Initial-load callback does not re-run | `retransformClasses` has capabilities/limits and requires idempotence |
| Asynchronous methods | Return reflects returned `Future`, not completion | Measure completion stage separately |
| Errors from the helper itself | Can mask exceptions, double-count, or skew balance | Fail-open helper and isolated failure paths |

### 16.1. A Real Risk: Helper Throws an Exception on the Success Path

In the demo transformer, `TimingProbe.success()` sits inside the catch-all region covering the entire method body. If `success()` throws, the `failure()` handler can also run. As a result, **a single invocation can record both RETURN and THROW or record wrong timing**, while also changing the return value or exception seen by the caller.

A production design should consider:

- Never letting collector/logging failures escape from the probe.
- Separating the protected region of **business code** from the hook region where possible, using labels and branches compliant with JVM rules.
- Using anti-recursion guards; avoiding excessive allocations even on the error path.
- Not catching `Throwable` and silently swallowing all errors indiscriminately, especially JVM critical errors.
- Adding unit tests that intentionally make the recorder/exporter throw, to verify the fail-open policy and preservation of the original exception.
- Exposing `activeScope`, `missingExit`, and `doubleFinish` counters in controlled diagnostics.

**Do not claim `-Xverify:all` proves flawless production behavior**. The verifier confirms bytecode validity under JVM rules on test inputs; semantic invariants must be separately tested and designed.

## 17. Instrumentation Overhead and Handling High Load

The actual measurement path includes:

~~~text
entry hook:
  ThreadLocal lookup + ArrayDeque.push + nanoTime + atomic count

exit hook:
  nanoTime + ArrayDeque.pop + ThreadLocal.remove if empty
  + atomic count + record/export
~~~

In the example, `println` can take significant time and make the measured duration far larger than pure business cost. Measure "uninstrumented" and "instrumented" methods with proper benchmarks including JIT/GC warmup, concurrency, and sample size. Do not take a single demo run and publish a fixed nanosecond overhead.

If sampling:

- **Decide once at entry** and store the decision in the frame; do not sample independently at return and throw.
- Maintain push/pop balance even when an invocation is not selected for recording; preferably use a token/frame indicating `sampled`.
- If dropped due to a full queue, distinguish `sampledOut` (intentional) from `queueDropped` (overload) and `exportFailed`.
- Use a bounded queue and fail-open `offer` on the hot path instead of `put` which can block indefinitely; enforce quotas for payload, retries, and shutdown.
- Keep total invocation/failure counters independent of raw trace sampling if accurate metrics are needed.

A business exception can be very rare and critical; 1% head sampling **does not guarantee** capturing every error. Prioritizing errors requires tail sampling or a bounded error-summary channel. Do not claim "sampling does not affect error rate" if the error rate is computed from sampled traces that were dropped.

### 17.1. Helper Time vs. Method Time

`enter` is called **before** the original method instructions. `success` is called **before** `ireturn`, so the measured duration covers the business code up to the exit hook, though it may not include the exit hook's own overhead after reading `nanoTime`; the timestamp is captured at the start of `finish` after the helper is entered.

`failure` runs when control transfers to the new handler—that is, after the exception has been constructed/raised/passed through any internal handlers. Therefore, failure duration may include part of exception dispatch. **The measurement definition** should explicitly state "elapsed from entry hook to exit hook" rather than "exact zero-overhead CPU time of the original method."

## 18. Troubleshooting: From Symptoms to Root Causes

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `package java.lang.classfile does not exist` | Using `javac` older than JDK 24 | `java -version`/`javac -version`, select JDK 24 |
| `ClassNotFoundException` / agent premain not running | Wrong manifest, JAR, or classpath | `jar tf timing-agent.jar`, check `Premain-Class` |
| No `agent.transformed` line | Target loaded too early, wrong internal-name matcher | Register in `premain`, name `demo/app/Calculator` |
| `helper.entered=0` even with agent | Transformer returned null/failed or did not match method | Inspect class bytes/JVM logs, add verifier |
| `returned=1` but `thrown=0` despite app errors | Inserted only before `ReturnInstruction`, missing catch-all | Check `Exception table` and `failure`/`athrow` |
| `NullPointerException`/`NoSuchMethodError` in helper | Wrong descriptor or classloader visibility | Verify `ClassDesc`/`()V`, classpath |
| `VerifyError` | Incorrect stack/handler labels, `StackMapTable`, or type flow | `-Xverify:all`, `javap -v`, minimize test method |
| `ClassFormatError` | Corrupted class-file bytes or invalid attribute | Parse output with Class-File API, do not mutate input |
| `ArrayDeque.pop` sees empty stack | Exit hook without matching enter or double finish | Check coverage, `ThreadLocal` nesting, error paths |
| An exception turns into a different type | Helper threw and masked business `Throwable` | Guard exit hook, preserve original exception |
| Enter/exit counters unbalanced mid-run | In-flight invocations, unsynchronized snapshot | Wait for quiescence or use consistent snapshots |
| Total elapsed too high under recursion | Inclusive duration sums child frames | Subtract child time for exclusive time |
| Measures only up to returning `CompletableFuture` | Measuring method boundary, not async completion | Instrument completion callback with context |
| `transformed/...` file does not appear | Transformer did not match or failed to write dump | Dump is test-only; check working directory |
| Multiple runs show missing/duplicated hooks | Retransform/redefine or multiple transformers | Idempotence, filtering, track registration |
| App slows down noticeably after enabling agent | Synchronous logging/collector, improper sampling/quota | Remove stdout in hook, benchmark, use bounded exporter |

### 18.1. Class-File API and Verifier Are Two Different Test Layers

`ClassFile.of().parse(bytes)` lets you inspect structure. Because the parser can be **lazy**, successful parsing does not guarantee all attributes/bytecode are valid. `java -Xverify:all` checks the class when the JVM loads it; integration tests demonstrate actual exception behavior and return values on concrete inputs.

A proper QA suite should include:

1. Structural checks (number of invoke instructions, opcode/owner/descriptor, catch-all entry).
2. JVM bytecode verification/loading.
3. Runtime normal return test.
4. Runtime explicit throw test.
5. Runtime implicit exception test.
6. Tests when the helper fails and when classes have complex handlers/branches.
7. Concurrency, nesting, error-rate, and performance tests.

## 19. Practice Checklist

- [ ] JDK 24 is actually used for both `javac` and `java`.
- [ ] Agent is launched with `-javaagent`; manifest has the right `Premain-Class`.
- [ ] Matcher selects only `demo/app/Calculator` and method `evaluate`.
- [ ] `enter()` is inserted before the original instructions.
- [ ] `success()` is inserted before `ReturnInstruction`.
- [ ] Catch-all handler has the proper range, calls `failure()`, then `athrow`.
- [ ] `out.with(element)` preserves all code elements of the original method.
- [ ] `CodeTransform.ofStateful` allocates separate labels/state per method traversal.
- [ ] Input `classfileBuffer` array is not mutated in place.
- [ ] Baseline without agent yields 0 probe calls.
- [ ] With agent: `evaluate(4) == 25`.
- [ ] With agent: caller still catches the exact `IllegalArgumentException`.
- [ ] With agent: caller still catches the exact `ArithmeticException` from `idiv`.
- [ ] `entered=3`, `returned=1`, `thrown=2` in the demo.
- [ ] `javap` shows the new `invokestatic` before `ireturn` and an exception table catching `any`.
- [ ] `VerifyTiming` reads both class files and verifies 0→1 for all three hooks and the catch-all.
- [ ] `-Xverify:all` runs successfully.
- [ ] No hardcoded nanosecond values are used as assertions.
- [ ] For production, add fail-open handling, helper-throw control, and multi-loader/JPMS support.
- [ ] For other methods, add descriptor filters and native/constructor/exception-handler/async tests.
- [ ] Exclude the agent, helper, logger, and exporter from instrumentation.
- [ ] Do not write dump files or print every invocation in callbacks/hot paths in production.

## 20. Self-Check Questions

1. Why does inserting a hook only before `IRETURN` miss `evaluate(-1)` and `evaluate(0)`?
2. Does `evaluate(0)` have an `athrow` instruction at the division-by-zero site? At which opcode does the JVM raise the exception?
3. Which return types does `ReturnInstruction` cover?
4. Why does `TimingProbe.success()` have descriptor `()V` in the example?
5. What structure does `exceptionCatchAll(from,to,handler)` add to the class file?
6. Why must the handler never swallow the original `Throwable` and return a fake value?
7. Why should an exception caught and handled inside the method not be counted as a method-level `THROW`?
8. When the helper's `success()` itself throws, what can the demo handler misrecord?
9. Why should time measured by `System.nanoTime()` not be used as an absolute timestamp?
10. Why is a stack needed in recursion instead of a single `ThreadLocal<Long>`?
11. Why can the sum of inclusive times of nested methods exceed the thread's elapsed time?
12. Why is the latency of a method returning `CompletableFuture` not equivalent to the completion time of the async task?
13. What is the meaning of `java -Xverify:all` and what are the limits of the JVM verifier?
14. Which new instructions and exception table entries does `javap` confirm?
15. Why is an independent check of `original.enter=0`, `transformed.enter=1` stronger than only reading transformer logs?
16. Why is the counter equality `entered=returned+thrown` not proof that the exporter lost no data?
17. Why should an agent not instrument its own logger and helper?
18. Why does JDK 17 fail to compile the article's `java.lang.classfile` agent verbatim?
19. How should the descriptor be filtered if `Calculator` has multiple `evaluate` overloads?
20. What additional tests would you run before deploying a duration-measuring agent on methods with multiple try/catch/finally blocks?

**Remember:** To measure **both normal return paths and exception-throwing paths**, instrumentation must track **every normal return** **and** an **exceptional-exit handler** covering the target code. Catching only explicit `ATHROW` instructions is insufficient because the JVM can throw exceptions from other opcodes. In the JDK 24 experiment, the Class-File API generates three helper calls and one catch-all entry; `javap`, the independent verifier, and JVM `-Xverify:all` confirm 1 return and 2 throws are recorded while business results remain unchanged. In real deployments, you must add guards for helper failures, class-loader/module visibility, nested/async consistency, sampling, overloads, and resource limits.

### Official Documentation

- [JDK 24 — java.lang.classfile package](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html)
- [JDK 24 — CodeTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeTransform.html)
- [JDK 24 — CodeBuilder: exceptionCatchAll and invokestatic](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html)
- [JDK 24 — ReturnInstruction](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/instruction/ReturnInstruction.html)
- [JDK 24 — ExceptionCatch](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/instruction/ExceptionCatch.html)
- [JDK 24 — ClassFile / ClassTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [JDK 24 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java 17+ — System.nanoTime](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html#nanoTime())
- [JEP 484 — Class-File API JDK 24](https://openjdk.org/jeps/484)
