# Optimization Assumptions, Deoptimization, and Recompilation When Assumptions No Longer Hold

The JVM's **JIT compiler** (Just-In-Time) does not merely translate bytecode into machine code. In HotSpot, the JIT can **observe the running program**, learn commonly encountered object types, frequently taken branches, and "hot" methods, and then generate specialized machine code to run faster. The subtle point: some optimizations are based on **assumptions that appear true at compile time but are not immutable truths**.

For example: in 100,000 calls to `operator.apply(value)`, the receivers all belong to class `AddOne`. The JIT can place a **type guard** and inline the call as `AddOne.apply`, instead of performing virtual dispatch in the general way. But on the 100,001st call, the program might pass `TimesTwo`; the JVM must still correctly execute `TimesTwo.apply`. One way to handle this is **deoptimization**: leaving the overly specialized machine code version, reconstructing the necessary Java state, and continuing with the interpreter or an appropriate level of compiled code; the JVM can collect a new profile and **recompile** with more suitable assumptions.

> **Speculative optimization does not mean the JVM guesses and accepts wrong results.** Every valid optimization must preserve the behavior required by the Java Language Specification and the JVM Specification, even when an assumption fails.

This lesson belongs to the **Interpretation and JIT** group. The focus is on distinguishing **profiling → speculation → guard/dependency → deoptimization → interpreter/fallback → recompilation**, understanding uncommon traps, type profiles, and class hierarchy assumptions, distinguishing **invalidated compiled code** from **garbage-collected Java objects**, and practicing on **Java 17/HotSpot** without fabricating JIT event counts.

## 1. Java bytecode, interpreter, and compiled nmethod

Java source is usually compiled by `javac` into **class file bytecode**. At runtime, HotSpot can:

- Execute bytecode using the **interpreter**.
- Collect **invocation counts, backedge counts, and type/branch profiles** while the program runs.
- Compile "hot" methods/loops using **C1** (client compiler, with instrumentation/optimization levels) or **C2** (server optimizing compiler), depending on tiered compilation configuration.
- Transition from interpreted to compiled code, or between compiled code levels, when the profile has sufficient information and compilation completes.
- If compiled code is no longer safe/valid or a "rare" branch unexpectedly appears, **deoptimize**, transferring control to an execution path that still preserves Java semantics.
- Possibly **reprofile and recompile** if the method remains hot and the JVM determines that another code version would be more suitable.

**The term `nmethod`** in HotSpot typically refers to a unit of **native machine code** generated to execute a Java method (including appropriate optimized/OSR-supporting versions). It resides in the **Code Cache**, not a new "Java source method" and not an instance on the Java heap.

```text
Java source
    │ javac
    ▼
Java bytecode  ───────────────────────────────────────┐
    │                                                │
    ▼                                                │
Interpreter / tiered runtime                         │
    │ collect profile (hotness, types, branches)     │
    ▼                                                │
C1 / C2 JIT compilation                              │
    │                                                │
    ▼                                                │
Optimized machine code (nmethod)                     │
    │                                                │
    ├── assumption still holds → fast path           │
    │                                                │
    └── guard/dependency invalidated                 │
            │                                        │
            ▼                                        │
        DEOPTIMIZATION                               │
          ├─ reconstruct Java-level execution state  │
          ├─ resume interpreter/fallback             │
          └─ profile/recompile when appropriate ─────┘
```

**Warning:** This is a logical diagram for learning. Compiler decisions, code entrypoints, safepoints, on-stack replacement, and the ability to fall back to another compiled code level have implementation-specific details; there is no rule that "every deopt is guaranteed to have an immediate new compile."

## 2. Proven optimizations vs. assumption-based optimizations

Not every JIT optimization is speculative.

| Category | Idea | When is a fallback needed? |
| --- | --- | --- |
| **Proven-safe optimization** | The compiler knows the reduction always preserves semantics, e.g., valid constant folding or elimination under proven conditions | No deopt needed just because a profile assumption about a branch no longer holds |
| **Speculative optimization by type profile** | "Most receivers at this call site are `AddOne`" | If a receiver belongs to another type, a guard must handle the general path or deopt |
| **Class hierarchy assumption** | "Currently there is no subtype/override changing the uniqueness of the target" | When class loading/linking invalidates the dependency, the VM must stop using compiled assumptions that no longer hold |
| **Rare branch, uncommon path** | "Normally the condition is never true in the observed profile" | When the path appears it must be handled correctly; an uncommon trap may be used |
| **Guarded hoisting/check elimination** | "The object/value satisfies this condition in the optimized code region" | If the guard fails, avoid continuing execution based on the false assumption |
| **Escape-analysis-based optimization** | Allocation/lock can be reduced or eliminated if it does not affect observable behavior | Upon deopt, the JVM must preserve equivalent Java state, possibly materializing virtual objects from metadata |

A **proven** assumption based on language/bytecode rules does not have the same nature as an assumption that is **mostly true due to a profile**. Using `-XX:-TieredCompilation` or disabling JIT for comparison does not change Java bytecode semantics; however, it can change how the runtime collects profiles, warm-up time, and performance.

### 2.1. Speculation is not blind guessing

C2 does not "guess an arbitrary class." It has sources of information:

- **MethodData/profile information** collected at certain bytecode sites.
- Frequency of target receiver types at `invokevirtual`/`invokeinterface`.
- Branches commonly true/false at a condition.
- Throw history of certain checks, such as null/type checks.
- Class hierarchy/dependency state that the VM can track.
- Invariants proven by bytecode analysis and compiler optimizations.

Even if a profile says "100% of calls are type A" during the warm-up phase, it only describes the past. The JVM must maintain appropriate **guards or dependencies** so the program remains correct when type B appears in the future.

## 3. Type profiling, monomorphic, and polymorphic call sites

Consider Java:

```java
interface Operation {
    int apply(int value);
}

final class AddOne implements Operation {
    public int apply(int value) { return value + 1; }
}

final class TimesTwo implements Operation {
    public int apply(int value) { return value * 2; }
}

static int evaluate(Operation op, int value) {
    return op.apply(value);
}
```

This is an **illustrative snippet**. A standalone runnable file is in section 10.

- **Monomorphic profile:** at a call site, the runtime mainly observes **one receiver type**. The JIT can devirtualize and inline the target.
- **Bimorphic/polymorphic profile:** the site observes two or more receiver types; the compiler can choose a few guarded inlines, type tests, or virtual dispatch depending on thresholds/heuristics.
- **Megamorphic site:** many receiver types make specialization via a series of guarded inlines potentially inefficient; generic dispatch may be reasonable.

The terms "mono/bi/mega" describe characteristics of the **call site and profile** in a context, not a permanent property of an interface. The same interface method called at different bytecode sites can yield different profiles.

### 3.1. Illustration of guard-based speculative inlining

Suppose all `evaluate` calls initially receive `AddOne`:

```text
Bytecode:
  load op, value
  invokeinterface Operation.apply(I)I

MODEL optimized code:
  if (receiver.type == AddOne) {
      return value + 1;         // inline AddOne.apply
  } else {
      uncommon_trap_or_slow_path(); // must not blindly return value + 1
  }

First time encountering TimesTwo:
  fast-path guard is false
  → fallback/deopt must ensure returning TimesTwo.apply(value)
```

This is **pseudocode illustrating the strategy**, not actual Java source/assembly of a HotSpot build. C2 may choose a slow path instead of an uncommon trap or choose not to speculate at that site; it may inline both targets if the profile/heuristics are appropriate.

### 3.2. Do `final` and `sealed` guarantee no deopt?

No. A `final class` cannot be subclassed under Java rules, which can make some type analyses easier. But a method called virtually can still receive different object classes that implement the same interface, or compilation may depend on other assumptions. `sealed` restricts direct permitted subclasses at the language level but does not automatically turn every dynamic call into a monomorphic one.

The compiler can statically prove a call target or use speculation depending on available information; do not infer "a method in a final class is always inlined" or "with a sealed class there is definitely no deoptimization."

## 4. Rare branches (uncommon branch) and uncommon trap

A method frequently called with positive numbers:

```java
static int normalize(int n) {
    if (n < 0) {
        return -n;
    }
    return n + 1;
}
```

If for a long time only `n >= 0` appears, the JIT can optimize for the main branch and reduce the burden of the negative branch. One HotSpot C2 strategy is an **uncommon trap**: when a rarely encountered branch/condition is triggered, the compiler lets the JVM transition from optimized code to a runtime path that can re-execute the correct bytecode logic.

**Important point:** having an `if` and mostly positive data **does not guarantee** C2 will emit an uncommon trap. The compiler might generate two normal machine branches, use a conditional move, or optimize differently. This is an example of a **situation that has the potential** to create speculation, not a promise about the trace of every JVM.

### 4.1. A guard failure is not necessarily an application error

A guard checking a receiver type failing does not mean a `ClassCastException` in Java source. It can be a signal that **JIT-generated code needs to fall back to a more general version**.

```text
Fast path assumes: n >= 0
                   │
                   ├─ true  → optimized calculation
                   │
                   └─ false → uncommon trap / general fallback
                               │
                               ▼
                        Java negative branch
                        runs the correct result
```

With `normalize(-7)`, the result matching Java semantics is `7` (since `-(-7)==7`), even though the method was previously compiled and optimized for positive numbers. Deoptimization is a **mechanism to preserve correctness**, not meaning the application has to catch a Java exception named "DeoptimizationException".

### 4.2. Synchronous and asynchronous deoptimization

Two cases are commonly distinguished in HotSpot discussions:

- **Synchronous deoptimization:** execution actually reaches a guard/uncommon path and requests runtime support for deopt. The trigger is tied to executing compiled code.
- **Asynchronous invalidation/deoptimization:** an event from another thread, such as class loading breaking a class hierarchy dependency, causes the compiled method to no longer be used and active frames must be handled by VM mechanisms.

"Asynchronous" here does not mean arbitrary instructions can be modified unconditionally; the JVM coordinates safepoints, dependency tracking, and metadata to transition to valid state. Detailed documentation is **HotSpot implementation**, not a public `Thread.deoptimize()` method.

## 5. Class Hierarchy Analysis (CHA) and invalidated assumptions

C2 can observe at compile time that an interface/abstract method has only one possible receiver target in the already loaded/linked hierarchy, or an appropriate target has been identified via profile. It can leverage this to inline and reduce virtual dispatch.

A dependency based on the **currently loaded set of classes** may no longer hold after the JVM loads another valid class.

```text
Initially:
  interface Formatter
      └── PlainFormatter

C2 may specialize formatter.format(...) calls for PlainFormatter
when profile/hierarchy allows.

Later:
  interface Formatter
      ├── PlainFormatter
      └── HtmlFormatter       (newly loaded/linked)

If assumptions depending on a unique target no longer hold:
  JVM invalidates/deoptimizes related compiled code.
  Subsequent calls perform proper dispatch by runtime type.
```

**Do not claim** every class load causes the entire JVM to deopt. The JVM tracks **specific dependencies**, and only nmethods whose assumptions are affected need appropriate handling. If compiled code already has a guard and slow path handling the new type, it may remain valid.

### 5.1. Hierarchy example does not mean loading a class is an exception

Classes are loaded via class loaders, reflection, or normal execution. Valid class loading must not cause a Java program to fail just because the JIT previously saw fewer types. A correct implementation preserves `invokevirtual`/`invokeinterface` according to bytecode semantics.

Errors like `NoClassDefFoundError`, `LinkageError`, or `ClassCastException`, if they occur, have **actual language/linkage causes**, not "the JIT saw a new class so it threw an exception."

### 5.2. Recompilation after hierarchy changes

After invalidation, HotSpot can:

1. Stop the old nmethod version from receiving new calls (`not entrant`).
2. Handle active compiled frames according to deoptimization rules.
3. Continue in the interpreter or appropriate code.
4. Collect a new profile with classes A and B.
5. When the method is still sufficiently "hot" and compiler policy allows, recompile; the new version may contain **two guarded targets** or generic dispatch.

Recompilation **does not necessarily happen immediately at the moment the class is loaded**. There are queues, thresholds, compiler threads, profiling heuristics, and limits such as the code cache.

## 6. What is deoptimization really?

**Deoptimization** is the process of leaving compiled code execution that relies on assumptions/optimization state and restoring an **execution state suitable for continuing Java semantics**. This is completely different from:

- The garbage collector reclaiming unreachable objects.
- Java code throwing a `RuntimeException`.
- The JVM terminating the process.
- The build system re-running `javac`.
- HotSpot simply "clearing the CPU cache."

An optimized compiled frame may **not have a 1–1 structure** with interpreter frames in Java source. The compiler can:

- Inline multiple Java methods into a single machine frame.
- Keep local values in registers instead of stack slots as in the bytecode interpreter model.
- Eliminate non-escaping intermediates or represent objects in a scalarized/virtual form.
- Perform valid loop transformations or hoisting.
- Remove or combine checks in regions with guarded assumptions.

Upon deopt, the JVM must reconstruct the **logical frames**, local variables, operand stack values, and object states needed for correct resumption. HotSpot stores metadata/debug information at possible deopt points to serve this process.

### 6.1. On-stack replacement and deoptimization are not synonymous

**OSR (On-Stack Replacement)** allows a loop currently being executed by the interpreter to transition to compiled code **while the loop has not yet finished**, instead of waiting for the next method invocation.

```text
Interpreter starts a very long-running loop
      │ backedge counter / hotness
      ▼
JIT generates a compatible OSR nmethod
      │
      ▼
runtime transfers execution to the optimized loop body

Deoptimization:
optimized execution → interpreter/fallback
when assumptions no longer fit or per VM policy
```

OSR is a transition **to compiled execution**, while deopt is a mechanism to exit an optimization state. Both can appear in the lifetime of a loop/method, but they are not exact inverse operations in every detail.

### 6.2. How are inlined stack frames reconstructed?

Suppose C2 has inlined:

```text
Java source call stack:
  main()
    → service()
       → validate()
          → compute()

JIT optimized:
  one compiled frame containing inlined code of
  service(), validate(), compute()
```

Upon deopt, the VM needs to be able to restore the relevant logical frames so that exception handling, bytecode execution, and stack traces continue with correct semantics. Inlining must not lose Java information that needs to be observable in a valid fallback case.

This is one of the reasons **deoptimization has a cost**: it needs to transfer control, unpack/reconstruct frames, and sometimes materialize data that the compiler had optimized away.

### 6.3. Escape analysis and materialization

An object seemingly created with `new` can be **scalar replaced** by the JIT if the compiler proves it does not escape the appropriate scope, and its fields are kept as scalar values instead of an independent heap allocation.

```java
record Point(int x, int y) {}

static int compute() {
    Point p = new Point(2, 3);
    return p.x() + p.y();
}
```

This is an **illustrative snippet**. The compiler can optimize `p` away when safe; it is not guaranteed to eliminate it in every build/config. If deoptimization/Java state requires the equivalent object, the VM must ensure semantics through appropriate metadata and materialization.

Do not look at `new` in bytecode and infer that every `new` in Java source creates a heap allocation seen by GC. Similarly, do not claim every scalar-replaced object will materialize at every deopt: only when execution/observable state requires it.

## 7. Uncommon trap, invalidation, and `nmethod` lifecycle

Three terms are often conflated:

| Term | Conceptual meaning | What should NOT be inferred |
| --- | --- | --- |
| **Uncommon trap** | Rare branch/check triggering a VM path that can cause deoptimization | Does not mean a Java exception |
| **Deoptimization** | Transitioning an active optimized execution to a state that can continue correctly | Does not require the nmethod to be deleted immediately |
| **Invalidation / made not entrant** | Compiled code version is no longer selected as an entrypoint for new calls | Does not mean all active frames or memory are deleted instantly |
| **Recompilation** | Compiler generates new code based on new profile/assumptions | Not guaranteed to happen immediately after every deopt |
| **Code cache reclamation** | VM reclaims unused compiled code according to its lifecycle | Not GC reclaiming the Java object heap |

In `-XX:+PrintCompilation` output, you may see states related to compiled methods such as `made not entrant` or `made zombie`, depending on HotSpot build/runtime events. They **are not a 1–1 indicator** proving exactly which kind of uncommon trap occurred; there are many reasons compiled code gets replaced/no longer used.

### 7.1. Does deopt mean "returning to the interpreter from the start of the method"?

No. Deoptimization must continue at the **exact appropriate position and semantic state**, and must not arbitrarily re-run side effects from the beginning of the method. If a method already wrote to a file, updated a database, or incremented a counter, deopt cannot arbitrarily redo them just because the runtime needs to switch implementations.

An **uncommon trap** can lead to re-executing a bytecode at a chosen point, but that must fit the JVM state and only operations permitted to re-execute safely. Do not infer "deopt re-runs the entire function" from the word "reexecute" in low-level HotSpot documentation.

### 7.2. Java exceptions differ from internal traps

When Java source is supposed to throw `NullPointerException`, `ArrayIndexOutOfBoundsException`, `ClassCastException`, or `ArithmeticException`, compiled execution must preserve equivalent Java behavior.

HotSpot can:

- Generate an explicit machine check and throw the exact exception.
- Use a safe implicit hardware fault according to the runtime contract.
- Send a rare path back to the interpreter via deoptimization so the interpreter executes exception semantics.

These choices are implementation details; **do not read "uncommon trap" in a compiler log as an exception that the program swallowed**.

## 8. Why is recompilation not always good?

A hot method can go through these states:

```text
interpreter → profiled C1 → optimized C2
                   │             │
                   │             ├─ trap/invalidated → fallback
                   │             │                       │
                   │             │                       ▼
                   │             └──────────► new profile/recompile
                   │                                     │
                   └──────────────────────► different optimized code
```

JIT compilation consumes CPU, memory, and code cache. Deoptimization usually has the cost of **transferring execution + reconstructing state** and can lose the benefit of compiled code for a period of time. If the program continuously changes type distributions, the compiler might "thrash" between multiple versions without seeing a stable profile.

HotSpot has policies to limit endlessly re-optimizing a site that repeatedly triggers traps; some paths may be deemed unsuitable for further speculation, or the compiler will emit more general code.

**Do not** assume every nmethod invalidation is a JVM bug. In dynamic workloads, changing optimizations is a normal part of runtime adaptive compilation.

### 8.1. Profile pollution and warm-up

A service warmed up with 99% requests of data type A may lead the JIT to pick fast path A. After rollout, production traffic contains a significant proportion of types B/C, and the code may deopt, recompile, or switch to generic dispatch.

This explains:

- Why a microbenchmark with a single type can be overly optimistic.
- Why A/B testing workload distribution affects latency.
- Why performance "was fast and then suddenly slowed down" is sometimes due to class loading, profiles, or invalidation.
- Why performance regression should not be defined solely from the first 100 ms or a few requests.

Warm-up should reflect the **diversity of receiver types and branch outcomes** of production, not just the number of iterations.

### 8.2. Tiered compilation is not fixed levels per second

HotSpot tiered compilation in common configurations consists of:

- **Interpreter (level 0)**.
- Various **C1** levels with or without full profiling.
- **C2 optimized compilation** (typically level 4 in tiered design).

Compiler policy decides transitions based on hotness, compiler availability, code size, profiles, and heuristics. There is no contract saying "after exactly 10,000 calls C2 compiles" or "after 2 seconds JIT turns on" across all JVMs/builds.

`-XX:-TieredCompilation` changes the compilation policy, not "disables all JIT." To run most bytecode with the interpreter and skip JIT for experiments, HotSpot supports `-Xint`; performance can drop drastically.

## 9. Sequence of an assumption failure

A plausible timeline:

1. Interpreter/C1 observes `Operation.apply` receiving `AddOne` most of the time.
2. C2 uses the profile to generate a fast path and possibly inline `AddOne.apply`.
3. Runtime starts receiving `TimesTwo` at the same call site.
4. A guard fails or a compiler dependency is invalidated, depending on the actual code structure.
5. If the compiled path cannot handle the new case directly, HotSpot may deopt, reconstruct frames/state, and continue the correct logic.
6. The old C2 nmethod may become not entrant if policy considers its assumptions invalid.
7. Profiling can now also reflect type `TimesTwo`.
8. If the method is still hot, the JIT may compile a new version: type checks for both, virtual dispatch, or another strategy.
9. Every request must still receive the **same Java semantic result** as unoptimized execution.

```text
Time
  │
  ├─ profile A A A A A A A ...
  │
  ├─ compile specialized code for A
  │
  ├─ call with B
  │    └─ type guard fails
  │          └─ deopt / fallback if needed
  │
  ├─ profile A and B ...
  │
  ├─ potential recompile for A+B / generic path
  │
  └─ continue same Java semantics
```

That is a **scenario that is allowed to happen**, not a mandatory synchronous sequence of 9 events that the JVM "must" print on every run.

## 10. Java 17 practice: warming up one type then switching to another

Standalone file **`SpeculationDemo.java`**:

```java
public class SpeculationDemo {
    interface Operation {
        int apply(int value);
    }

    static final class AddOne implements Operation {
        @Override
        public int apply(int value) {
            return value + 1;
        }
    }

    static final class TimesTwo implements Operation {
        @Override
        public int apply(int value) {
            return value * 2;
        }
    }

    // This call site can receive multiple receiver types.
    static int evaluate(Operation op, int value) {
        return op.apply(value);
    }

    public static void main(String[] args) {
        Operation first = new AddOne();
        Operation second = new TimesTwo();

        long phaseOne = 0;
        for (int i = 0; i < 100_000; i++) {
            phaseOne += evaluate(first, i);
        }

        long phaseTwo = 0;
        for (int i = 0; i < 1_000; i++) {
            phaseTwo += evaluate(second, i);
        }

        System.out.println("phaseOne=" + phaseOne);
        System.out.println("phaseTwo=" + phaseTwo);
        System.out.println("semanticsOK=" +
                (phaseOne == 5_000_050_000L && phaseTwo == 999_000L));
    }
}
```

Compile:

```bash
javac --release 17 SpeculationDemo.java
```

Run normally:

```bash
java SpeculationDemo
```

**Stdout of the Java program (without JIT diagnostic output enabled):**

```text
phaseOne=5000050000
phaseTwo=999000
semanticsOK=true
```

**Explanation of results:**

- Phase one computes the sum `1+2+...+100000 = 5_000_050_000` in a `long` variable, avoiding `int` overflow in the sum.
- Phase two computes the sum `2×0+2×1+...+2×999 = 999_000`.
- `evaluate` is a call site that can be monomorphic in phase one and then receive a second type in phase two.
- The **Java-level** result must be identical whether `evaluate` is executed by the interpreter, C1, or C2.

**Experiment limitation:** There is no guarantee of `deoptimization` just by switching `Operation` from AddOne to TimesTwo. The compiler might predict early, handle polymorphism via a slow path, inline both, not finish compiling before phase two, or optimize loops/call sites differently. To claim a specific trap occurred, you must have **diagnostic evidence** from that exact run.

### 10.1. Running with the interpreter to compare semantics

```bash
java -Xint SpeculationDemo
```

Running `-Xint` on HotSpot causes normal bytecode execution to rely on the interpreter instead of JIT-compiled application methods. **Stdout is still the exact three lines above**, though execution time can differ greatly.

Do not use the time difference of a **single run** with a small loop to conclude "JIT speeds up by X times": startup overhead, interpreter/JIT policy, and optimizations vary; use JMH or a well-designed benchmark if the goal is measuring microperformance.

### 10.2. Do not confuse diagnostic output with business stdout

When `PrintCompilation` is enabled, the JVM may print many compiler event lines before/between application lines. Do not treat compilation event log lines as fixed stdout of the `SpeculationDemo` class.

## 11. Second Java 17 practice: rare branch must still be correct

Create file **`RareBranchDemo.java`**:

```java
public class RareBranchDemo {
    static int normalize(int value) {
        if (value < 0) {
            return -value;
        }
        return value + 1;
    }

    public static void main(String[] args) {
        long checksum = 0;
        for (int i = 0; i < 100_000; i++) {
            checksum += normalize(i);
        }

        System.out.println("warmupSum=" + checksum);
        System.out.println("rareNegative=" + normalize(-7));
        System.out.println("nextPositive=" + normalize(10));
    }
}
```

Compile and run:

```bash
javac --release 17 RareBranchDemo.java
java RareBranchDemo
```

**Exact stdout:**

```text
warmupSum=5000050000
rareNegative=7
nextPositive=11
```

The result for the `-7` branch remains correct regardless of whether C2 guessed "the negative branch never occurs" or the compiler kept code for that branch. The example only demonstrates **correctness across execution paths**; it does not confirm the number of `uncommon_trap`s.

**`int` boundary warning:** `normalize(Integer.MIN_VALUE)` returns `Integer.MIN_VALUE` due to Java `int` overflow under two's complement semantics. This is Java behavior, **not a deoptimization bug**. If business logic requires the mathematical absolute value of every `int`, overflow handling must be designed using `long` or `Math.negateExact` appropriately.

## 12. Observing JIT with Java 17 HotSpot flags

### 12.1. `-XX:+PrintCompilation`

```bash
java -XX:+PrintCompilation SpeculationDemo
```

This flag prints information whenever HotSpot compiles a method according to the JDK 17 `java` documentation. Lines can contain:

- Relative timestamp.
- Compilation identifier.
- Compilation level (depending on tiered mode).
- Class and method.
- Compiled nmethod state (such as made not entrant), depending on the event.

**There is no fixed output**. If you do not see `evaluate`, it does not necessarily mean the code is wrong: the VM may have inlined/optimized it or the sample run ended before the method was compiled at the desired tier.

### 12.2. Inlining decisions — requires diagnostic unlock

```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+PrintCompilation -XX:+PrintInlining \
     SpeculationDemo
```

`PrintInlining` can explain why the compiler inlined a method or not (code too big, hotness, profile, call site...). Note:

- Output across different HotSpot builds can vary.
- PrintInlining reports **compile decisions**, not self-proving that deopt occurred when type distribution changed.
- A `final` method can still fail to inline due to compiler budgets/cost model.
- An inlined method may not appear as a separate machine stack frame in optimized execution.

### 12.3. `LogCompilation` records detailed information

Oracle JDK 17 supports XML-formatted diagnostic compilation logging, commonly used to investigate uncommon traps and compile decisions:

```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+LogCompilation -XX:LogFile=jit-hotspot.xml \
     SpeculationDemo
```

The file `jit-hotspot.xml` is written in the current working directory when supported by the JVM/runtime. You must read the **actual XML/compiler log** before concluding:

- Whether there is an `uncommon_trap` or not?
- What is the trap reason/bytecode index?
- By which event was the method `made not entrant`?
- Did the compiler generate new code after the event or not?
- For which types was the call site optimized/inlined?

**Important:** Field names, tags, and reason/action codes are **HotSpot internals**, not a stable public logging API. Some flags are only present in certain builds, diagnostic builds, or require `-XX:+UnlockDiagnosticVMOptions`. If the JVM reports "Unrecognized VM option", check the vendor/release; **do not fabricate that every JVM always has a `TraceDeoptimization` flag in a production build**.

### 12.4. Comparing interpreter, tiered, and non-tiered

```bash
# Interpreter-oriented baseline:
java -Xint RareBranchDemo

# Default HotSpot tiered compilation in common configurations:
java RareBranchDemo

# Changes compilation policy, NOT disabling all JIT:
java -XX:-TieredCompilation RareBranchDemo
```

The three commands have the **same Java-level stdout** in the example. However, they do not necessarily have the same compiler events, code cache usage, or execution time.

`-XX:-TieredCompilation` is **not** equivalent to `-Xint`: it changes the tiering policy, and HotSpot can still use the JIT compiler.

### 12.5. Do not rely on internal flags as a production API

Public JDK 17 documentation lists `-XX:+PrintCompilation`, `-XX:+LogCompilation`, `-XX:+PrintInlining`, `-XX:+UnlockDiagnosticVMOptions`. Other flags like `PrintOptoAssembly`, `TraceDeoptimization`, or instrumentation from debug builds likely depend very heavily on the HotSpot flavor/platform. Only use them after confirming `java -XX:+PrintFlagsFinal -version`/build docs; some flags will not exist in a production JVM.

### 12.6. JFR and profile timeline

**Java Flight Recorder** supports observing compilation activities and application runtime events according to configured event types, via JDK Mission Control or corresponding tooling. It is useful for correlating timelines:

- Compiler warm-up/compilation queue.
- CPU pressure when many compiled tasks run.
- Request latency spikes.
- Class loading and safepoints.
- GC events, heap allocations, code cache, and runtime behavior.

Do not assume every JFR recording contains every deopt event or C2 speculation details: event availability, settings, and JVM builds differ. To inspect details of a specific uncommon trap, `LogCompilation`/compiler diagnostic metadata is usually more suitable if HotSpot supports it.

## 13. Distinguish "saw compilation" from "saw deoptimization"

| Observation | Permitted conclusion | Cannot conclude from this alone |
| --- | --- | --- |
| `PrintCompilation` has the method name | JVM had a compilation event for the method | Compiler definitely speculatively inlined a receiver type |
| `PrintInlining` reports inlined target | Compiler decided to inline a call/target during compilation | An uncommon trap occurred at runtime |
| Log has `made not entrant` | A version of an nmethod is no longer used as a normal entrypoint | All active frames were lost immediately or the only reason is type profile |
| Log has `uncommon_trap` reason/action | HotSpot recorded trap metadata/event with the corresponding reason | Java code had wrong semantics or needed to throw an exception to the caller |
| No traps seen in a run | That run has no evidence of traps at that logging level | The program cannot deopt in the future |
| Runtime p99 latency increased after rollout | There is a performance change | Deopt is definitely the sole cause |
| `javap -c` has `invokeinterface` | Bytecode semantically has an interface call | JIT cannot inline the target into machine code |

**`javap` inspects bytecode**, whereas compiled nmethod behavior requires compiler/runtime diagnostics. Java source has no `deoptimize` keyword, and a Java method does not know whether it is running on C1 or C2 through any standard public Java API.

## 14. What is the cost of deoptimization?

Possible sources of overhead include:

- Transitioning from compiled code to a runtime handler/fallback.
- Determining the bytecode position to resume and **reconstructing deoptimized frames**.
- Materializing objects or undoing/reconciling scalarized state when needed.
- Operations to invalidate/mark compiled code if a dependency becomes invalid.
- Collecting a new profile in interpreter/C1.
- CPU and memory for the JIT to **recompile**.
- Code cache footprint and reclaiming obsolete nmethods.
- Losing the effectiveness of some optimizations until the runtime has an appropriate profile.

**A single deopt does not necessarily slow down the application noticeably**. Transitioning execution has overhead, but it may have saved a lot of CPU beforehand thanks to the fast path. When deopt happens rarely, the net benefit remains positive.

What is worth investigating is **repeatedly deopting/recompiling at the same point in hot code**, unstable profiles, or compiled code being invalidated frequently causing CPU spikes/tail latency.

### 14.1. Why can a benchmark be polluted by warm-up?

A microbenchmark running for only a few tens of milliseconds can include:

- Class loading, bytecode verification, and interpreter startup.
- JIT compilation running concurrently with the work being measured.
- Speed changes when C1/C2 code becomes active.
- OSR when a loop gets hot.
- Deoptimization/recompilation when data distribution changes.
- GC, CPU scheduling, and thermal throttling.

That is why **JMH** is commonly used for Java microbenchmarks: the framework supports warm-up, forks, multiple iterations, and avoids several compiler pitfalls. However, JMH also cannot replace a production workload or by itself prove deadline/latency SLOs.

### 14.2. Profiling overhead and tier transitions

C1 code has instrumentation/profiling to supply data to C2. When a method is hot enough, tiered policy can replace profiled code with more optimized code. These transitions are not "recompiling because the compiler got it wrong"; they can simply be the **normal path** to better performance.

Conversely, a C2 nmethod optimized under an old assumption can be invalidated, and code recompiled under a different assumption. They are **two different reasons for having multiple compilation events on the same method**.

## 15. Real-world scenarios: services, plugins, and polymorphism

### 15.1. Service with multiple strategy implementations

An application uses a `PaymentStrategy` interface, initially most calls belong to `CardStrategy`. After adding a `WalletStrategy` plugin, the number of receiver types increases. The JIT can:

- Previously inline `CardStrategy`.
- Encounter a different type profile and deopt/fallback or use polymorphic dispatch.
- Compile a version suitable for the new traffic.
- Decrease or increase throughput depending on inlining, code size, CPU caches, and branch predictions.

Loading a plugin does **not always** cause a deopt. Only related compiled dependencies/specializations are at risk; code that already handles generic types may not need to change.

### 15.2. Workload changing after warm-up

Scenario:

```text
T0-T1  warm-up with only type A data
T1-T2  production traffic A + B + C
T2     p99 latency spike, compiler activity increases
T3     throughput stabilizes after runtime adapts
```

This is a **simulated model**. To determine the cause, correlate:

- Compilation logs near T2.
- Deopt/trap reasons if available.
- Class loading timeline and method code cache transitions.
- Request traces and CPU/GC metrics.
- Changes in input mix (receiver types/branch distributions).

Do not disable all JIT just to eliminate a spike and ignore long-term throughput regression. Measure and fix the cause of the changing data shape/inlining profile if it truly matters.

### 15.3. Proxy, reflection, lambda, dynamic languages

Dynamic proxies, multiple call site adapters, lambdas, and method handles can create dispatch shapes different from direct Java class calls. The JIT still has many optimization mechanisms, but type profiles or hierarchy assumptions can be more complex.

Do not conclude "using reflection means JIT optimizes nothing" or "interface calls are always slower than static calls." Method handles, inlining, and profile-guided optimizations can produce counter-intuitive results. Benchmark the exact API path on the JDK you are running.

## 16. Semantic safety: deopt must not break the program

Three important invariants:

1. **Correct return values:** `TimesTwo.apply(7)` must return `14` even if `evaluate` previously only saw `AddOne`.
2. **Side effects are not arbitrarily re-run:** if `counter++` or `socket.write` already happened, deopt must not duplicate the effect.
3. **Java exceptions and synchronization remain correct:** optimized code must preserve contracts regarding NPEs, bounds checks, object monitors, happens-before, and exception handlers per JVM rules.

```java
static int compute(int value, java.util.concurrent.atomic.AtomicInteger c) {
    c.incrementAndGet();   // observable side effect
    return value < 0 ? -value : value + 1;
}
```

This is an **illustrative snippet**. If the method is JIT-compiled and deopts on the negative branch, Java logic must still record `c.incrementAndGet()` exactly **once per invocation**, not twice because the compiler had to return to the interpreter.

### 16.1. Why is deopt more complex than a generic fallback?

If the compiler simply generates two guarded general code paths, it can handle the new type **right inside compiled code** without deopting. But when C2 has aggressively inlined, scalar-replaced, and validly reordered, a rare branch may need the **full interpreter state** to continue correctly. Deoptimization handles that situation through cooperation between compiler metadata and the runtime.

Therefore "guard failed ⇒ always deopt" is also wrong: a guard can lead to a normal compiled slow path. Only when the compiler/runtime decides to fall back to a more general execution path is there a deopt in the sense considered here.

### 16.2. On-stack compiled frames and invalidation

A method can have many active invocations across threads. When the VM detects an invalid dependency:

- It cannot assume dropping all running frames on all threads instantaneously.
- The VM must use appropriate mechanisms to ensure no frames continue executing under the **wrong assumption**.
- The nmethod can be marked **not entrant** for new calls.
- Active frames needing deopt/invalidation can be handled at points supported by the VM.
- Code cache reclamation only happens when code is no longer in use according to its lifecycle.

Do not equate "class loader loaded a new class" with "GC reclaimed the nmethod in the same millisecond."

## 17. Debugging performance when seeing too many deopts

**Step 1 — Confirm the symptom.** Collect p95/p99 latency, throughput, CPU, and compiler activity; distinguish startup from steady state.

**Step 2 — Record JDK and flags.** Fix `java -version`, vendor, architecture, tiered compilation policy, heap/code cache settings, and CPU quota.

**Step 3 — Observe compilation.** Enable `-XX:+PrintCompilation` in a test environment and check hot methods being compiled multiple times.

**Step 4 — Observe inlining.** Enable `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` to see compiler assessments of targets and code size; output is large so log/split to files.

**Step 5 — Collect compiler logs if needed.** Use `-XX:+LogCompilation` on a supported HotSpot build, cross-referencing uncommon trap reason, compile id, bci, and not-entrant transitions.

**Step 6 — Correlate event timeline.** Look at class load/unload, JFR/compiler activity, GC, safepoints, and workload mix near the time of the latency spike.

**Step 7 — Separate causes.** Normal tier transitions, speculative guard failures, code cache pressure, class hierarchy invalidation, or benchmark noise are different.

**Step 8 — Controlled benchmarking.** Use JMH or representative load, with warm-up containing A/B/C types and branch outcomes similar to production.

**Step 9 — Minimal evidence-based tuning.** For example, reduce pathological megamorphic call sites in hot loops, stabilize dispatch data, or adjust pipeline structure; do not disable all inlining/JIT unless there is a measured reason.

**Step 10 — Verify correctness.** Run unit/integration tests with the interpreter and appropriate HotSpot flags to ensure logic does not accidentally depend on timing/profiling.

### 17.1. `made not entrant` is not always a big issue

When C1 profiled code is replaced by more optimized C2 code in the tiered pipeline, an old nmethod may no longer be an appropriate entrypoint. The same status can also appear when a class hierarchy dependency is invalidated. Just seeing the words `not entrant` **does not tell you the exact cause**; you need to correlate compile id, level, and log events.

### 17.2. Avoid "self-measuring JIT" microbenchmarks done wrong

```java
long start = System.nanoTime();
for (int i = 0; i < 10_000; i++) {
    normalize(i);
}
System.out.println(System.nanoTime() - start);
```

This is an **anti-pattern snippet** for learning benchmarking. If the result of `normalize(i)` is not used, the JIT can eliminate the computation; 10,000 iterations may not be enough warm-up or the profile may change, and `System.nanoTime` has its own overhead. Do not take the result of a single run and declare whether the compiler deopted or not.

## 18. Common misconceptions

1. **"JIT just translates bytecode to machine code once."** False. HotSpot does adaptive profiling, tiering, optimization, and can recompile.
2. **"JIT speculation means accepting wrong results when an assumption fails."** False. Guards/dependencies/deopt preserve Java semantics.
3. **"A call site that is initially monomorphic will always be monomorphic."** False. Workload or class loading can change type distribution.
4. **"Using an interface definitely prevents inlining."** False. Profiling and CHA can enable devirtualization/inlining.
5. **"Every time a new receiver type is passed, a deopt is mandatory."** False. The compiler may already have a generic fallback, polymorphic inline, or not have compiled yet.
6. **"A `final` class never needs a fallback."** False. There are other assumptions, and interface call sites can still be polymorphic.
7. **"Deoptimization is a Java exception."** False. It is a runtime/compiler mechanism.
8. **"Uncommon trap means JIT crash."** False. It can be a safe state-transition path for a rare branch.
9. **"If JIT eliminates a null check, Java NPE disappears."** False. Optimized code must still preserve semantics.
10. **"Deopt re-runs from the beginning of the method, including side effects."** False. The VM restores state to continue correctly.
11. **"Inlining 3 Java methods creates 3 separate machine frames."** Not necessarily. A single compiled frame can contain logical inlined scopes.
12. **"After deopt, the JVM cannot reconstruct scalar-replaced objects."** False. The VM/compiler coordinate metadata/materialization when needed.
13. **"`made not entrant` = compiled code memory is reclaimed immediately."** False. Nmethod lifecycle and active frames must be handled.
14. **"Every compilation event is caused by deoptimization."** False. Tiered level upgrades/OSR also generate compilations.
15. **"An uncommon trap will always recompile immediately."** False. Runtime policy decides.
16. **"A newly loaded class invalidates all JIT code."** False. Only related dependencies.
17. **"OSR is deoptimization."** False. OSR lets execution enter compiled code in a loop; deopt exits optimized code.
18. **"`-XX:-TieredCompilation` disables all JIT."** False. `-Xint` is the interpreter-oriented mode.
19. **"`PrintCompilation` always reports the exact trap reason."** False. Deeper diagnostics are needed.
20. **"`javap -c` prints JIT-compiled machine code."** False. It prints Java bytecode.
21. **"Seeing no traps in one run proves it will never deopt."** False. Depends on profile/JDK/configuration and logging.
22. **"Good performance in a single-type warm-up represents multi-type production."** Not necessarily.
23. **"JIT compiling is GC collecting old code."** False. Code cache management is different from Java heap GC.
24. **"Changing an interface implementation always requires rebuilding source."** False. Java dynamic dispatch and runtime/JIT support other types.
25. **"JIT has the right to change `System.identityHashCode` results after deopt."** Not according to Java semantics of object identity.
26. **"Increasing `-Xmx` guarantees reducing all deopts."** False. Heap GC memory and JIT assumptions/profiles are different.
27. **"Increasing compiler threads infinitely will increase throughput."** False. CPU/cache/memory and compilation policy have trade-offs.
28. **"`-XX:+LogCompilation` is a Java Language Specification API."** False. It is a HotSpot-specific diagnostic interface.
29. **"When JIT inlines, Java stack traces can no longer show logical methods."** False. The VM has scope metadata to support Java behavior at appropriate points.
30. **"Speculation is an optimization bug."** No. It is an intentional technique, with cost/correctness trade-offs.

## 19. Self-check and answers

**Q1.** The compiler profile sees the receiver is always `AddOne`. Why can it not assume all future calls are `AddOne` without a safeguard?

**Answer:** A `TimesTwo` receiver can validly appear later. A guard/valid dependency or generic fallback ensures correct dynamic dispatch.

**Q2.** If a speculative guard fails, does the Java user have to catch `DeoptimizationException`?

**Answer:** No. Deopt is a HotSpot runtime mechanism, not a public checked/unchecked Java exception.

**Q3.** Can deopt return right into the middle of a running method instead of re-running the method from the start?

**Answer:** Yes. JVM/compiler metadata supports reconstruction and resumption at the appropriate state/semantics.

**Q4.** Why does the JIT need metadata for inlined methods?

**Answer:** A single compiled frame can contain multiple logical Java scopes; during deopt/exception/stack walking, the VM needs to reconstruct the scopes and values accurately.

**Q5.** Why does `made not entrant` not mean the compiler has deleted all active frames of the method?

**Answer:** It is an entrypoint/lifecycle state of a compiled nmethod; active frames must be handled separately and safely before reclamation.

**Q6.** Is `-XX:-TieredCompilation` equal to `-Xint`?

**Answer:** No. Non-tiered can still JIT compile; `-Xint` mainly uses the interpreter for experiments.

**Q7.** What does `SpeculationDemo` print for `phaseTwo`?

**Answer:** **999000**, which is the sum of `2×i` for `i=0..999`.

**Q8.** Seeing `-XX:+PrintInlining` report an inlined target. Does that prove a deopt when B appears?

**Answer:** Not yet. Actual trap/deopt evidence is needed; the code could have a guard + generic fallback.

**Q9.** Can class loading invalidate a compiled CHA assumption?

**Answer:** Yes, if the corresponding dependency is affected; not every class load invalidates every nmethod.

**Q10.** Why might the compiler materialize an object after escape-analysis-based scalar replacement during deopt?

**Answer:** Java-level state requires the equivalent object to remain observable/usable after returning to the interpreter; the compiler stores metadata to support reconstruction.

**Q11.** If the JIT deopts, should the computation result change compared to `-Xint`?

**Answer:** No. For valid code, the interpreter and optimized code must preserve Java semantics.

**Q12.** Why does the `RareBranchDemo` experiment not guarantee an uncommon trap?

**Answer:** C2 might not compile in time or might generate normal compiled branches; type/branch speculation is a heuristic choice, not an obligation.

**Q13.** When benchmarking a polymorphic hot method, what kind of input should be used for warm-up?

**Answer:** With a distribution of types/branch outcomes representative of the real workload, avoiding warming up with only one type and inferring production performance.

**Q14.** Should a single `made not entrant` at startup be treated as a memory leak?

**Answer:** No. This is usually a valid transition in the compiled code lifecycle; check repetition rate, code cache/CPU, and event reasons first.

## 20. Summary mechanism map

```text
           Java bytecode / interpreter
                      │
                      ▼
             Runtime profiling
          receiver types, branches,
           invocations, backedges
                      │
                      ▼
              C1/C2 compiler
                      │
               speculative code
                      │
       ┌──────────────┴────────────────┐
       │                               │
   Assumption OK                  Assumption FAIL
       │                               │
       ▼                               ▼
   Optimized fast path        guard fails / invalid dependency
                                       │
                              ┌────────┴─────────┐
                              │                  │
                          compiled           DEOPTIMIZE
                          slow path          reconstruct state
                              │                  │
                              │                  ▼
                              │           interpreter / fallback
                              │                  │
                              │           new profiles/heat
                              │                  │
                              │           possible recompile
                              │                  │
                              └────────┬─────────┘
                                       ▼
                            SAME JAVA SEMANTICS

In every branch:
  - return values correct
  - exceptions correct
  - side effects correct
  - object identity correct
```

**Remember:** The JIT optimizes based on **profiles and assumptions**, because knowing commonly taken paths can be faster than generic bytecode execution. HotSpot maintains **guards and class-dependency checks** so it does not run incorrectly when the world changes. **Deoptimization** restores Java execution state from compiled/inlined/scalarized representations and allows continuing correctly via interpreter/fallback; the runtime may reprofile and **recompile**, though not necessarily after every trap. When diagnosing performance issues, inspect **compile levels, inlining, actual uncommon traps, class loading, code-cache events, and workload input mix** instead of guessing from a single run's result.

### References

- [Oracle JDK 17 — `java` command / JIT flags](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `PrintCompilation`, `PrintInlining`, `LogCompilation`, `TieredCompilation`, `Xint`.
- [OpenJDK HotSpot Wiki — Compiler](https://wiki.openjdk.org/display/HotSpot/Compiler): overview of optimizing compilers and HotSpot internals.
- [OpenJDK HotSpot Wiki — Deoptimization](https://wiki.openjdk.org/display/HotSpot/Deoptimization): deoptimization concepts in HotSpot.
- [Red Hat Developer — How JIT Compiler Boosts Java Performance](https://developers.redhat.com/articles/2021/06/23/how-jit-compiler-boosts-java-performance-openjdk): type profiles, speculation, traps, and class hierarchy invalidation.
- [Red Hat Developer — Runtime Profiling in OpenJDK's HotSpot JVM](https://developers.redhat.com/articles/2021/11/18/runtime-profiling-openjdks-hotspot-jvm): branch/type profiling for C2 speculation.
- [JVMS Java SE 17 — `invokevirtual` and `invokeinterface`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): bytecode invocation semantics that the JIT must preserve.
- [Java SE 17 — `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspecting bytecode/class files, not JIT native code.
