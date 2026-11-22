# Execution Profiling from Invocation Counts, Loops, and Object Types

## 1. Why Must HotSpot Observe a Program While It Is Running?

A Java `.class` file contains bytecode that can be checked for syntax and data types, but it **does not tell in advance** which method will be called millions of times, which loop runs for a very long time, which branch is frequently taken, or which class of object an interface call actually receives in practice.

HotSpot uses **execution profiling** to collect part of the runtime execution behavior, from which it decides **which code is worth JIT compiling** and **under what assumptions the compilers should optimize**. Three important groups of data:

- **Invocation counters**: signals about how many times a method is called, used to evaluate method hotness.
- **Backedge/loop counters**: signals about looping activity in bytecode; help detect a method that is called only once but has a loop with millions of iterations, serving **On-Stack Replacement (OSR)**.
- **Type profiles**: statistics of receiver types actually encountered at bytecode call sites or corresponding profiling locations; support type speculation, **devirtualization**, **inlining**, and handling rare execution paths.

HotSpot can also collect **branch frequencies**, **type-check feedback**, information about **uncommon traps**, and other internal data; however, the focus of this article is invocations, loops, and object types.

This article uses **HotSpot/OpenJDK Java 17**, the interpreter, **C1**, **C2**, and tiered compilation. The metadata names, counters, thresholds, and compilation levels below are **HotSpot implementation details**, not a contract of the Java Language Specification (JLS) or Java Virtual Machine Specification (JVMS). Another compliant JVM may optimize differently while still having to preserve Java results.

**Distinguish immediately:** a “profile” is information for the runtime to make decisions, not definitive proof that a method has been inlined, that an object has changed type, or that a Java method currently has a number of calls exact to the counter value shown in internal structures.

## 2. From Bytecode to Machine Code: The Big Picture

```text
.java
  |
  | javac
  v
.class (bytecode)
  |
  | class loading / verification / linking
  v
Interpreter + counters/profile instrumentation
  |
  | hotness, branch and receiver feedback
  v
Tiered compilation policy
  |
  +--> C1: early compiled code, profiling depending on tier
  |
  +--> C2: deep optimization based on static + dynamic facts
           |
           v
       compiled machine code
           |
           | assumptions/guards
           v
    If assumptions no longer hold:
      fallback / deoptimization / reprofile / recompile
```

The steps can overlap in time:

1. An application thread is executing bytecode in the interpreter or a compiled nmethod.
2. The JVM updates counters or profile records depending on the execution level.
3. The compilation policy decides to enqueue a compile task.
4. A **compiler thread** (separate from the application thread) may process the task from the compile queue.
5. When compiled code is valid, the VM can let subsequent calls use the compiled entry, or if currently running in a loop, it can use the OSR entry.
6. A method can be compiled multiple times, with different compilation levels and assumptions.

You cannot rely on calling a method “hot” and then claim it **always** has C2 code after a fixed number of calls. Compilation timing also depends on compile queue load, profile maturity, flags, code cache, compiler availability, and JVM build.

## 3. Invocation Counter: Knowing a Method Is Called Many Times

Consider the methods:

```java
static int twice(int value) {
    return value * 2;
}

static long applyManyTimes() {
    long total = 0;
    for (int i = 0; i < 100_000; i++) {
        total += twice(i % 10);
    }
    return total;
}
```

These are **two method fragments**, not a standalone compilable file. In this model, `twice` is called many times from a loop. HotSpot can observe those calls to increment the **invocation counter** or update method usage signals appropriate to the compilation tier.

### What Do Counters Help the JVM Decide?

- Is the method “hot” enough for the compiler to invest time in?
- At which profiling level should it transition from the interpreter to C1?
- When is the data sufficient and the expected benefit justifies C2 compilation?
- Is a method likely to become cold or not yet useful to continue enqueueing compile requests?

**An invocation count is not a CPU profiler.** A very short getter called many times may consume less time than a method run only once that iterates over millions of elements. An inlined code path may not have a number of machine-level function calls equal to the number of calls written in Java source.

### Limitations of Counters

HotSpot's counters are **VM-internal**, not a `long invocationCount` placed inside every Java object. They can be read/adjusted by the tiered compilation policy and updated differently depending on the execution engine. No Java SE API specifies a threshold like “call exactly 10,000 times and it will definitely become C2”; those thresholds/notification frequencies can change with runtime state and JDK updates.

Do not use `AtomicLong` in an application to pretend it is a raw JVM invocation counter. That is **business instrumentation**, with its own overhead and semantics; the JIT may inline calls or optimize code, but business counters must reflect the operations requested by the application.

## 4. Backedge Counter: A Single Call Can Still Be a Very Hot Spot

A method can be called once yet contain a long loop inside:

```java
static long accumulate(int n) {
    long total = 0;
    for (int i = 0; i < n; i++) {
        total += i;
    }
    return total;
}
```

This is also a **method fragment**. At the bytecode level, a typical Java compiler generates a condition check and a branch jumping back to a lower bytecode offset (BCI) — called a **backward branch/backedge**.

```text
BCI 0:   init i = 0
BCI 4:   check i < n      <--- loop header
BCI 9:   body total += i
BCI 18:  increment i
BCI 21:  goto BCI 4       <--- backedge
```

The BCIs and instruction descriptions in the diagram are **illustrative**, not verbatim `javap` output. Actual bytecode content may differ depending on the compiler.

HotSpot can rely on **backedge notifications/counters** to detect time-consuming loops, even when the invocation counter is not high.

### Is “Backedge Count = Loop Iteration Count” Always True?

No. It depends on the bytecode control-flow graph and branch positions. A single `for` in source can turn into multiple bytecode edges; nested loops have multiple backedges; the JIT can **unroll**, **peel**, **vectorize**, **eliminate**, or transform loops when generating machine code. Therefore, do not treat backedge count as an exact source-iteration counting API for all situations.

## 5. On-Stack Replacement (OSR): JIT While the Loop Is Still Running

**OSR** enables the JVM to switch from the current interpretation/compiled representation to a compiled entry for **a location inside a method**, typically at a loop backedge, **even while that method invocation has not yet finished**.

```text
Method longTask() is called once
    |
    v
Interpreter starts loop
    |
    | backedge traversal count increases
    v
Runtime requests OSR compilation at the loop's BCI
    |
    | compiler thread prepares machine code
    v
Application transitions to OSR entry when conditions allow
    |
    v
Continue compiled loop -> return from method
```

Without OSR, a method with a long loop might have to wait until the **second call** to use a compiled entry, which is unhelpful for a batch job called only once. OSR is a way to reduce this limitation.

**How OSR differs from normal compilation:**

| Normal entry compilation | OSR compilation |
| --- | --- |
| Entry normally used when an invocation starts at the beginning of the method | Entry used to continue at a BCI belonging to an in-progress invocation |
| Usually related to invocation hotness | Usually related to loop/backedge hotness |
| Can apply to subsequent calls | Can help a very long in-progress call |
| A compiled version has an entry at the start of the method | May have an nmethod/entry dedicated to the loop's BCI |

Do not assume OSR definitely appears in **every** long loop. The JVM may compile before the loop runs, the code may be heavily optimized, or the compile policy/thresholds may not choose OSR in a specific test run.

## 6. Runnable Java 17 Example: Observing a Long Loop

Create **`BackedgeOsrDemo.java`**:

```java
public class BackedgeOsrDemo {
    static volatile long observed;

    static long calculate(int n) {
        long sum = 0;
        for (int i = 0; i < n; i++) {
            sum += (i & 7);
        }
        return sum;
    }

    public static void main(String[] args) {
        observed = calculate(8_000_000);
        System.out.println("iterations=8000000");
        System.out.println("sum=" + observed);
    }
}
```

```bash
javac --release 17 BackedgeOsrDemo.java
java BackedgeOsrDemo
```

**Deterministic stdout of the program itself:**

```text
iterations=8000000
sum=28000000
```

Because each group of 8 values `(i & 7)` is `0 + 1 + ... + 7 = 28`, and there are 1,000,000 groups, the sum equals 28,000,000.

To see compiler events on HotSpot:

```bash
java -XX:+PrintCompilation BackedgeOsrDemo
```

**There is no fixed compiler stdout:** the log may contain many JDK methods, different compilation levels, or not show OSR in the exact way you expect. The `%` symbol is commonly associated with OSR in HotSpot's `PrintCompilation` and an `@ BCI` segment indicates the starting point; you must read the actual compiler log, and not use the two `System.out` lines as proof that OSR occurred.

### Using javap to Find the Backedge

```bash
javap -c -p BackedgeOsrDemo
```

`javap -c` displays offsets and bytecode instructions. Look for the conditional branch and the jump back to an earlier BCI to understand the bytecode loop. This is not a C2 machine-code disassembler; the JIT may optimize the machine loop differently from the structure in `.class`.

## 7. Tiered Compilation: C1, C2, and Profiling Levels

HotSpot Java 17 commonly uses **compilation levels 0–4**:

| Level | Execution engine | Common purpose |
| --- | --- | --- |
| **0** | Interpreter | Executes bytecode, can update counters/profiling |
| **1** | C1 optimized code, no full profiling | Early native code when deep profiling is unnecessary |
| **2** | C1 with limited profiling | Invocation/backedge counting and limited hotness info |
| **3** | C1 with fuller profiling | Contributes MethodData/receiver and branch profiles for C2 to use |
| **4** | C2 | Deeply optimized native code based on static information and profile feedback |

A common path is `0 → 3 → 4`, but paths `0 → 2 → 3 → 4`, `0 → 1`, or other paths are all valid, depending on the compilation policy. Not **every** method goes through all levels, and compilation requests may wait in compiler queues.

### Why Do Tier 2 and Tier 3 Differ?

Full profiling has **runtime overhead**: updating metadata and counters costs CPU/cache bandwidth and sometimes affects compiled code size. C1 tier 2 provides a fast execution level with limited notifications; tier 3 collects additional feedback so C2 can speculate and optimize with higher quality.

Assuming “C1 = no profiling” is wrong, but “every C1 method always has a full receiver type profile” is also wrong.

### Factors Other Than Counters

Tier transitions also consider compiler queue load, method size (large/small), code cache, compiler state, whether the method is already compiled, profiling maturity, and policy/flags. A C2 compile may appear for a method with many invocations, or may not appear in a very short test run.

## 8. How Do MethodCounters and MethodData (MDO) Differ?

HotSpot has VM-internal structures for managing method activity and dynamic profiles:

- **MethodCounters** or counters located in runtime method metadata: invocation and backedge signals, and some state used by the compilation policy.
- **MethodData / MethodDataObject (MDO)**: a richer profile attached to a method, containing **records associated with specific BCIs**, such as type profiles at virtual call sites, branch-related counts, and other data kinds.
- Data collection can start in the interpreter and continue in compiled code with instrumentation at an appropriate level.
- There is no Java SE API for applications to directly read HotSpot's raw MDO receiver rows like a `Map<Class<?>, Long>`.

```text
Method com.example.Worker.process
   |
   +-- invocation/backedge counters
   |
   +-- MethodData (when created):
       |
       +-- @BCI 10: branch taken/not-taken tendencies
       |
       +-- @BCI 24: invokevirtual
       |            observed receiver: FastImpl, SafeImpl ...
       |
       +-- @BCI 52: invokeinterface
                    observed receiver distribution different from BCI 24
```

This is a **conceptual** structural diagram, not a layout/histogram extracted from a running JVM. MDO has limited record kinds/row counts depending on the build, and its contents can be updated/aged/reprofiled; it **is not a complete exact record of every object type that ever arrived at a call site**.

## 9. Where Is the Type Profile Collected?

In **virtual dispatch**, the target method depends on the **runtime class of the receiver**. For example:

```java
interface Converter {
    int convert(int x);
}

final class FastConverter implements Converter {
    public int convert(int x) {
        return x + 1;
    }
}

final class SafeConverter implements Converter {
    public int convert(int x) {
        return x * 2;
    }
}
```

These are interface/class fragments; there is no `main` to run standalone.

At an `invokeinterface Converter.convert` bytecode, HotSpot can collect observed receiver type feedback. A site receiving `FastConverter` almost all the time may be suitable for **speculative inlining**; a site receiving many implementations may lead to guarded multimorphic paths or generic dispatch.

### Monomorphic, Bimorphic, and Megamorphic

| Term | Model at **one call site** | Possible consequence |
| --- | --- | --- |
| **Monomorphic** | One common/single receiver class observed | Easy to specialize, direct/guarded call or inline |
| **Bimorphic** | Two common receiver classes | Can inline one or more paths with guards |
| **Polymorphic** | Multiple receiver classes | Optimization depends on frequency and inline budget |
| **Megamorphic** | Very many receiver classes | A single-type assumption is usually ineffective |

These are **explanatory models**, not bytecode types defined by the JVMS. “Monomorphic” does not guarantee the compiler always inlines; “megamorphic” does not guarantee the program is always slow. The JIT also considers receiver types, method size, call-site hotness, code-cache budget, CHA/static type information, and machine-code properties.

**Profiling is per-site, not just per-interface:** two call sites both calling `Converter.convert` can see completely different type distributions. A type profile is attached to a bytecode/method location, not a table counting all `Converter` instances across the entire heap.

## 10. Runnable Java 17 Example: One Call Site Seeing Two Receiver Types

Create file **`ReceiverProfileDemo.java`**:

```java
public class ReceiverProfileDemo {
    interface Operation {
        int apply(int x);
    }

    static final class AddOne implements Operation {
        public int apply(int x) {
            return x + 1;
        }
    }

    static final class DoubleIt implements Operation {
        public int apply(int x) {
            return x * 2;
        }
    }

    static int dispatch(Operation operation, int x) {
        return operation.apply(x);
    }

    static long run(Operation operation, int count) {
        long sum = 0;
        for (int i = 0; i < count; i++) {
            sum += dispatch(operation, i % 10);
        }
        return sum;
    }

    public static void main(String[] args) {
        long first = run(new AddOne(), 20_000);
        long second = run(new DoubleIt(), 5);

        System.out.println("addOne=" + first);
        System.out.println("double=" + second);
    }
}
```

```bash
javac --release 17 ReceiverProfileDemo.java
java ReceiverProfileDemo
```

**Deterministic stdout:**

```text
addOne=110000
double=20
```

`AddOne` for values from 0 to 9 sums `1+2+...+10=55` in one cycle, and there are 2,000 cycles, giving 110,000; `DoubleIt` for 5 inputs 0–4 sums to `0+2+4+6+8=20`.

At **the same site** `operation.apply(x)` in `dispatch`, the runtime is fed one receiver type many times and then another type. **Java semantics must always be correct**, even if the compiler chose a specialized path based on the earlier profile.

What the output **does not prove**:

- That method `dispatch` was C2 compiled.
- That the JIT definitely inlined `AddOne.apply`.
- That encountering `DoubleIt` definitely caused a deoptimization.
- That the receiver data in MDO has an exact 20,000:5 ratio.

Those must be proven using compiler diagnostics **on the running JVM**; the JIT might inline into the caller, not compile before the type switch, or choose a valid fallback.

## 11. Type Profiling and Speculative Inlining

If a call site mostly encounters receiver class `AddOne`, C2 can optimize the hot path along this model:

```text
Bytecode:
  invokeinterface Operation.apply

Observed at site:
  AddOne frequent
  DoubleIt rare

Optimized fast path (conceptual):
  if receiver is AddOne:
      inline AddOne.apply(x)
  else:
      correct dynamic dispatch behavior (fallback/deopt)
```

**The JIT is not required to emit an exact `if` instruction** like the diagram. The compiler may use inline caches, devirtualization via class hierarchy, exact types, or machine-code-level guards; the kind of guard and fallback mechanism depend on the build.

### Why Can Profile Data Stop Being Representative?

Application warmup only runs `AddOne`; after production rollout, it starts receiving requests using `DoubleIt` or adds new implementations. The initial profile is no longer representative of the current distribution.

If a speculative assumption becomes false, the JVM can:

- Go through a pre-generated **generic fallback**.
- Perform **deoptimization** to return execution to a safe representation.
- Continue profiling and **recompile** with new data.
- **Invalidate/make not entrant** an nmethod whose dependency no longer holds.

**It must never produce a wrong result** just because of an old profile. Guards/deopt/fallback are how HotSpot exploits speculation while preserving **Java-visible semantics**. Deopt is normal VM behavior, not a business Java exception.

## 12. Class Hierarchy Analysis (CHA) Differs from Dynamic Type Profiling

An interface call can be optimized because:

1. The compiler sees an **exact/final** target type through static information.
2. **Class Hierarchy Analysis** sees a suitable hierarchy/implementation at compile time and records the necessary dependency.
3. **Dynamic type profile** shows the most frequently encountered receiver type at the call site.
4. Other analyses (inlining, escape, call graph) show the call target is simple enough.

| Knowledge source | Example | Limitation |
| --- | --- | --- |
| Bytecode/static type | Variable declared as `Operation` | Does not always determine the implementation |
| `final`/exact inferred type | Receiver is definitely a specific class on the path | Does not decide inlining alone |
| CHA | Hierarchy in the VM at compile time | A new class can require dependency invalidation |
| Type profile | Site sees more `AddOne` than `DoubleIt` | Profile may be incomplete or skewed by warmup |
| Compiler heuristic | Small callee, hot call | Can change across JDKs/flags |

Therefore, a log showing a call was inlined **is not enough to prove** it was a direct result of the MDO type profile, if the JIT already knew the call target from static info/CHA.

## 13. What Do Branch Profiles and Type-Check Feedback Add?

This article focuses on three signals, but an MDO can contain other statistics that help select the hot path:

```java
static int normalize(int value) {
    if (value >= 0) {
        return value + 1;
    }
    return -1;
}
```

This is a **method fragment**. If most inputs are positive, the compiler can lay out code so the hot path has less overhead. However:

- A Java `if` does not correspond to a stable raw branch counter; bytecode and machine code can have different CFGs.
- A profile measures observed paths; it does not prove future inputs will keep the same distribution.
- Branch profiling does not replace data validation; every valid input must still be handled correctly.
- Certain type-check records and uncommon-trap feedback help the compiler avoid repeatedly making assumptions that have been broken too often.

Do not treat “99% true in tests” as a license to omit the other branch from Java behavior. If deoptimization/fallback occurs, the code must still produce the correct result.

## 14. Compiler Levels 0–4 Are Not a Stamp of Speed

A method compiled at level 4 can still be slow because:

- The algorithm has high complexity.
- The code has to access data not in CPU cache.
- It performs I/O, locks, or safepoints.
- There are many allocations/GC pressure.
- The receiver profile is diverse and compiled code needs generic virtual calls.
- The method suffers frequent deoptimization or code cache pressure.
- Startup JIT compilation cost is high relative to workload lifetime.

Conversely, a short helper in C1 or inlined into a caller can be fast enough. **Tier is a compilation state**, not a performance ranking on real data.

### A Method Can Be Compiled Multiple Times

Valid cases:

- Promotion from C1 tier 3 to C2 tier 4.
- OSR entry for a running loop.
- Recompilation after the profile matures or data changes.
- Invalidation/deoptimization due to a class hierarchy dependency.
- Replacing a compiled version that is no longer entrant.

Do not read a single `made not entrant` line and call it a memory leak or crash. You need the timeline and the reason for compile/deopt.

## 15. Observing with PrintCompilation

On HotSpot Java 17:

```bash
java -XX:+PrintCompilation BackedgeOsrDemo
```

Information that may appear: compile ID, timestamp, level, method name, bytecode size, `%` marker for OSR, `@ BCI`, `made not entrant` or `made zombie` status. Exact formatting and markers depend on the build.

| Observation | Grounded inference | Cannot conclude |
| --- | --- | --- |
| Level 3 | C1 compiled at a tier with appropriate profiling | C2 will definitely happen immediately |
| Level 4 | There is a C2 compilation task/result | Future calls will always only use this exact nmethod |
| `%` and `@ ...` | There is an OSR compilation at a BCI | Java loops always get OSR |
| `made not entrant` | The nmethod was withdrawn from new entry paths | The program has a semantics bug |
| Continuous compile IDs | There is compiler thread activity | The main CPU bottleneck is JIT |

**Warning:** `PrintCompilation` output typically includes internal JDK methods, not just classes you wrote. Do not write tests asserting the exact order of compiler events; HotSpot scheduling/tiering/JIT thresholds vary by machine and version.

## 16. Observing Inlining with PrintInlining

A method can be hot yet not inlined by the JIT because the code is too large, receiver information is missing, the call is not hot enough, or the inlining budget is exhausted. Use diagnostic options:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining ReceiverProfileDemo
```

This is a single command line that Bash, PowerShell, or CMD can all run on HotSpot builds supporting those options. `PrintInlining` is usually locked behind **diagnostic VM options**; place `UnlockDiagnosticVMOptions` before it.

Read the lines related to `ReceiverProfileDemo::dispatch`, `AddOne::apply`, and `DoubleIt::apply`, then cross-check with the compilation level. Seeing `inline (hot)` or a reason not to inline can help explain the decision, but **do not fabricate a fixed log**. The compiler might inline all of `dispatch` into `run` and distribute receiver profiles by inline context.

### More Logging Is Not Always Better

Diagnostic logging can generate heavy I/O, affecting startup and benchmarks; enable it only in appropriate environments, filter/collect within limits, and do not claim “enabling PrintInlining is a way to make the app faster”.

## 17. LogCompilation for Deeper Analysis

Some HotSpot JDK 17 builds support XML logging from the compiler:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=jit-log.xml ReceiverProfileDemo
```

You can analyze it with **JITWatch** or tools that understand HotSpot compilation logs to observe tier transitions, inline attempts, failure reasons, and trap/deoptimization patterns.

**Limitations to remember:**

- This is not a portable Java SE API.
- The file can be large, consume CPU/I/O, and contain information about class/method names.
- Record names/formats can vary by build.
- A compilation log is not a CPU sampled-stack profiler and does not provide per-business-request invocation counts.
- Do not interpret “method absent from log” as the method never having run; the method might not have been JIT compiled yet or might have been inlined into another caller.

## 18. JFR, JMC, and jcmd: Viewing Compilation on a Real Timeline

JDK 17's **Java Flight Recorder (JFR)** can record events related to the compiler, JVM runtime, GC, CPU, and application time. Example on a **running server** with a real PID:

```bash
jcmd <PID> JFR.start name=jit-observe settings=profile
jcmd <PID> JFR.dump name=jit-observe filename=jit-observe.jfr
jcmd <PID> JFR.stop name=jit-observe
```

`<PID>` is a placeholder; replace it with the PID of a running process that has attach permission and JFR enabled. The `jit-observe.jfr` file can be analyzed with Java Mission Control (JMC). The `settings=profile` configuration enables categories/events suited to the JDK's setting preset, though event thresholds/sampling also depend on the build and recording configuration.

JFR is useful for correlating compiler events with **CPU samples and allocation/GC**, but it is **not** a public API displaying **every raw MethodData counter/receiver record** from the interpreter/C1.

### Why Might JFR Miss a Compiler Event You Want?

- The application ran too fast and exited before recording became active.
- The JVM already compiled the method during startup before recording started.
- Profile settings do not record a particular event type/threshold.
- The method was inlined or the code was not hot enough to compile.
- Logging/sampling cost and data-loss conditions make observation non-absolute.

Do not take the absence of a JFR event as proof that Java bytecode was never executed.

## 19. Using javap to Identify Invokes and Backedges

`javap -c -p` displays **bytecode** in the class file, not JIT-generated machine code:

```bash
javap -c -p ReceiverProfileDemo
javap -c -p BackedgeOsrDemo
```

In `ReceiverProfileDemo.dispatch`, there is typically an `invokeinterface` to `Operation.apply`, though the **constant-pool index and BCI** depend on the build. In `BackedgeOsrDemo.calculate`, you can see the branch/jump back to the loop header.

**Distinguish clearly:**

| Tool | What can be observed |
| --- | --- |
| `javap` | Class-file bytecode, BCI, method descriptors, metadata |
| `PrintCompilation` | JIT compile events, levels, OSR hints |
| `PrintInlining` | Compiler inlining decisions/reasons |
| `LogCompilation`/JITWatch | More detailed timeline and compiler diagnostics |
| JFR/JMC | Runtime activity, compilation-related events, and sampled performance |
| CPU profiler | Code paths consuming CPU via sampling/instrumentation |
| Heap dump | Object graph/reachability, not callsite invocation/type profile |

A C2 log may mention a BCI taken from the method's bytecode, but it is **not** a Java source line. One source line can produce multiple bytecode instructions; you need `LineNumberTable` if you want to map back to source.

## 20. Role of Speculative Optimization and Deoptimization

When C2 uses a profile, it can prioritize a hot path with **guards**:

```text
C2 sees site is mostly AddOne:
   |
   v
Guard receiver type == AddOne
   | true                   | false
   v                        v
Inlined fast path      Generic call / deopt
   |                        |
   +------> correct Java result
```

If the assumption is broken, the JVM can use an **uncommon trap** to restore interpreter-compatible state, then reprofile/recompile. These events have a cost, but they are part of the mechanism that **keeps speculative optimization safe**.

Besides receiver types, HotSpot can invalidate compiled code when an assumption about the **class hierarchy** no longer holds after a new class is loaded. So do not always blame a `made not entrant` on a wrong receiver type profile; it could be due to another dependency.

A deoptimization event **is not a Java exception** and does not mean the Java application returned a wrong result. Only when it happens continuously in a steady workload should you investigate profile stability and compile policies.

## 21. Profile Pollution: Warmup Data Differs from Production

For example, a server initially processes only JSON through a `Serializer` interface, then 30 minutes later receives Binary and XML formats as well. The callsite type profile of a piece of code can change:

```text
Startup:
  Serializer.encode at BCI K
  JSON 100%

After rollout:
  JSON 50%
  Binary 30%
  XML 20%
```

These percentages are **illustrative**, not observed JVM metrics. If the JIT special-cased one receiver, a workload shift can increase generic fallback usage or trigger reoptimization.

A common wrong conclusion: “The JVM profile was wrong, so Java interfaces are the problem.” In reality, interface dispatch is the correct semantics; profile-guided optimization only helps when the statistical data aligns. You can improve things with a more stable callsite design **if a CPU profiler proves it is a bottleneck**, but do not break abstractions just to force monomorphism.

## 22. Avoid Confusing Java Benchmarks with JIT Profiles

A self-written loop measuring `System.nanoTime()` around the same method can be misleading due to:

- **Insufficient warmup:** class loading, C1/C2 compilation, and profile collection mix into the measured time.
- **Dead-code elimination (DCE):** the result is unused, so the JIT strips out logic.
- **Constant folding:** fixed inputs can be precomputed.
- **Loop unrolling/vectorization:** source iteration count does not correspond to machine operations.
- **Inlining:** the number of machine call instructions differs from source calls.
- **OSR:** mid-loop, execution can switch to a different compiled representation.
- **GC, CPU frequency, OS scheduling, and background work** add noise.
- **Diagnostic logging** skews timing.
- **Workload distribution** differing from reality makes the type profile unrepresentative.

Use **JMH** (Java Microbenchmark Harness) with proper warmup, measurement, forks, and result consumption for microbenchmarks. Use **load tests/JFR** for end-to-end performance. A microbenchmark testing only one implementation type may not represent a polymorphic production callsite.

### What Can Be Inferred from the Example Outputs?

- `BackedgeOsrDemo` prints 28,000,000: the loop computed correctly.
- `ReceiverProfileDemo` prints 110,000 and 20: dynamic dispatch computed correctly for both receiver types.
- You **cannot** conclude that C2 inlined, that OSR occurred, or that an object changed type. Those require **compiler diagnostics on the specific JDK build**.

## 23. Limitations of Counting and Sampling Methods

**Invocation/backedge counters** support tiering, but HotSpot can change how they are updated depending on the execution tier. **Type profiles** store distributions at certain sites, but not every event must be kept as a row. **JFR/JMC** and profilers use their own event/sampling semantics.

Factors that make measurements differ:

1. Interpreter, C1, and C2 have different instrumentation.
2. A method can be inlined or compiled in multiple versions.
3. Counters can be aggregated/decayed/reset according to policy.
4. MDO record capacity for receiver types is finite.
5. Compile policy may reduce profiling overhead at certain tiers.
6. JFR event sampling does not reflect every invocation in the same sense.
7. Java bytecode sites and machine-level control flow do not match after optimization.
8. Workload changes after the profile collection phase.

Do not compare “100,000 calls” in an application metric with a “hotness counter” in internal diagnostics and blame every difference on a JVM bug. The two numbers have **different purposes and definitions**.

## 24. When to Consider `-Xint` and `TieredStopAtLevel`?

In a learning environment, you can try:

```bash
java -Xint BackedgeOsrDemo
java -XX:TieredStopAtLevel=1 BackedgeOsrDemo
java -XX:+PrintCompilation BackedgeOsrDemo
```

- `-Xint` forces interpreted-only mode, so normal JIT compilation is not applied.
- `-XX:TieredStopAtLevel=1` caps compile levels at C1 level 1; it does not disable the JIT.
- `PrintCompilation` observes compilation activity while still using the default tiering policy.

These flags belong to the HotSpot/launcher implementation; they are not general production tuning advice. Do not take one measurement and conclude the interpreter is always slower by an exact fixed factor; CPU/JVM/benchmark setup strongly affects this.

### Do Not Tweak Thresholds Arbitrarily

Lowering thresholds can compile too early with an unrepresentative profile, increasing compiler CPU/code cache overhead and easily altering profiling behavior. Raising thresholds can cause short-lived applications to never use C2 during the measurement phase. Before tuning, prioritize looking at **real CPU hotspots, compile queue, inlining, and deoptimization evidence**.

## 25. A Step-by-Step Verification Scenario

Suppose a Java 17 service has a `PricingRule` interface, and each request applies one rule:

- **Symptom:** CPU increases after adding multiple rule implementations.
- **Hypothesis A:** the `rule.evaluate` callsite went from monomorphic to polymorphic, so C2 inlines less.
- **Hypothesis B:** the algorithm in a new rule is more complex, even though dispatch did not change.
- **Hypothesis C:** new requests allocate/parse more data; the bottleneck is in GC rather than virtual calls.
- **Hypothesis D:** during rollout, code temporarily deoptimized/recompiled, and stabilizes after warmup.

Verification process:

1. Fix the input mix and measure p95/p99 latency, CPU, GC, and throughput.
2. Use a CPU profiler/JFR to identify the code path actually consuming CPU.
3. Enable `PrintCompilation`/`PrintInlining` in an appropriate diagnostic environment.
4. Check whether `PricingRule.evaluate` is hot and compiled/inlined.
5. Compare the compilation profile before and after rollout **on the same JVM version**.
6. Check if/branches and call site type distributions with appropriate evidence.
7. Separate method implementation CPU from dispatch overhead with a separate benchmark.
8. Only refactor/tune if there is measurable improvement, not merely because you see a “virtual call” log.

A callsite with multiple receiver types is not a bug by itself. **Polymorphism is just one variable** in Java performance; sound design and maintainability still matter.

## 26. Disciplined Compiler Diagnostics Checklist

| Question | Tool/clue | Note |
| --- | --- | --- |
| Method is called often, but is it compiled? | `PrintCompilation`, JFR | Compiler events do not count every invocation |
| Does a long loop get OSR compilation? | `PrintCompilation` `%`/`@ BCI` marker | Not every loop is guaranteed OSR |
| Which bytecode site contains the invoke? | `javap -c -p` | Bytecode has no dynamic receiver distribution |
| Does C2 inline it? | `PrintInlining`, LogCompilation/JITWatch | Output varies with thresholds/call graph |
| Is the type profile stable? | JVM-specific diagnostics, workload tracing | No Java SE API reads raw MDO |
| Is there excessive deoptimization/recompilation? | Compilation logs, JFR events/VM diagnostics | Do not assume deopt is a bug |
| Is the method slow due to CPU or GC? | CPU profiler, JFR GC/CPU data | Compiler log is not a CPU flame graph |
| Is the compiler backed up on queue/code cache? | VM/compilation diagnostics | Hot methods may wait for the compiler |
| Is the optimization actually faster? | JMH or end-to-end load test | Warmup/forks/input mix determine this |

## 27. Common Misconceptions

| False claim | Truth |
| --- | --- |
| “The JIT only counts method calls” | HotSpot also observes loop backedges, receiver types, and branches |
| “A method called N times definitely becomes C2” | Tiers/thresholds/queues are dynamic VM policy |
| “A loop must call the method thousands of times to compile” | A single long-running loop can trigger OSR |
| “Backedge = source-level loop iteration” | It relates to bytecode CFG, not a source counter contract |
| “C1 does not support profiling” | C1 tiers have limited/full profiling depending on level |
| “C2 always continues recording full profiles like the interpreter” | Profiling strategy differs by tier |
| “MDO is a public Java Map” | MDO is HotSpot internal profiling metadata |
| “A type profile has only one table for the whole interface” | It is **site-specific** |
| “Monomorphic is always inlined” | There are also cost model, static type, code size, and budget |
| “Megamorphic is always slow” | Actual cost must be measured, especially when the callsite is not hot |
| “Inlining based on a type profile means another type will compute wrong” | Guards/fallback/deoptimization preserve Java semantics |
| “Deoptimization is a runtime error” | It can be a normal part of speculative JIT |
| “OSR is calling the method again from the start” | OSR resumes an in-progress invocation at a BCI |
| “`javap` shows JIT machine code” | `javap` disassembles **bytecode** |
| “PrintCompilation is a per-call trace” | It logs compiler events and state |
| “PrintInlining output is stable across all JDKs” | Diagnostic output and decisions vary by build |
| “Getting the right output proves the JIT performed OSR” | Correct Java semantics do not prove a compiler path |
| “A JFR profile is a raw MDO dump” | JFR has its own events/sampling |
| “Turning on more logs makes the app faster” | Logging has overhead; use only for diagnostics |
| “A benchmark without warmup is enough to conclude” | Warmup, DCE, JIT/OSR, and CPU noise can skew it |

## 28. Exercises and Self-Check Questions

**Question 1.** A method is called once but has a loop of 50 million iterations. Why might the JVM still want to compile it?

**Answer:** Backedge activity signals a hot loop, which can trigger **OSR**.

**Question 2.** Does the method invocation counter have to equal the exact number of Java source calls?

**No.** It is a VM-internal hotness/profiling signal and also depends on execution tiers, compilation/inlining.

**Question 3.** Where do C1 levels 2 and 3 fundamentally differ?

Level 2 typically collects **limited invocation/backedge signals**; level 3 produces **fuller profiling**, including type/branch feedback.

**Question 4.** Can two callsites for the same interface have different receiver distributions?

**Yes.** Type profiling at each callsite/BCI provides per-site data.

**Question 5.** The profile shows 99% `AddOne`. Must C2 definitely inline `AddOne.apply`?

**No.** Inlining also depends on hotness, code size, CHA, budget, and compiler policy.

**Question 6.** When encountering a new receiver class, is it allowed to return the old result of another class?

**No.** The JVM must use guards/fallback/deopt to ensure Java dynamic dispatch semantics.

**Question 7.** What does the `%` sign in a HotSpot compilation log usually suggest?

An **OSR compilation event**, usually accompanied by an `@ BCI` location.

**Question 8.** Does `javap -c` display C2 machine code?

**No.** It displays JVM bytecode from the class file.

**Question 9.** Does `BackedgeOsrDemo` printing the correct sum prove OSR occurred?

**No.** It only proves the calculation is correct; diagnostics are needed to know about OSR.

**Question 10.** Can `PrintInlining` be used directly as a latency benchmark?

**No.** It is a compiler diagnostic and has logging overhead; use JMH/load tests to measure latency.

**Question 11.** Is deoptimization always a Java exception or memory leak?

**No.** It is part of valid speculation/fallback.

**Question 12.** Warmup has only one receiver type; production has many types. What can change?

Type profile, inline guards, deoptimization/recompilation, and throughput; there is no fixed speed conclusion.

## Official References and Verification Sources

- [Oracle Java SE 17 — `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:+PrintCompilation`, `-XX:+LogCompilation`, JIT flags, and diagnostic options.
- [Oracle Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): bytecode BCI and invoke/branch instructions.
- [JVMS Java SE 17 — Instruction Set (`6.5`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5): `invokeinterface`, `invokevirtual`, `goto`, and control flow.
- [JVMS Java SE 17 — JVM Frames (`2.6`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): locals/operand stack for understanding OSR and deopt.
- [OpenJDK 17 MethodData source](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/oops/methodData.hpp): receiver/branch profile data and counters; details vary by build.
- [OpenJDK 17 tiered compilation policy](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/compiler/tieredThresholdPolicy.hpp): runtime levels/notification/counter heuristics.
- [How Tiered Compilation Works in OpenJDK — Microsoft Java Engineering](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): explanation of C1/C2, profiles, and transitions.
- [Java SE 17 — JFR](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html) and [`jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): compilation/runtime observation timeline.
- [JITWatch](https://github.com/AdoptOpenJDK/jitwatch): tool for analyzing HotSpot compilation logs and inline decisions.

**Remember:** HotSpot does not optimize solely based on “which method is called often”. **Invocation counters** detect repeated calls; **backedge counters** detect hot loops and help select **OSR**; **receiver type profiles** provide information at callsites for guarded/inlined dispatch. Tiered C1/C2 balances profiling cost with machine code speed, while **fallback/deoptimization** ensures Java results remain correct when profiles or class hierarchies change. When you want to prove what the JIT is doing, use compiler diagnostics on **the exact Java 17 JVM** and valid benchmarks, rather than guessing from source loop counts or single-run output.
